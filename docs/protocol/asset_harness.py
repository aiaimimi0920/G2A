"""资源解析字节链、闭包缓存发布与准入/呈现的装配；不下载真实资源。"""

from copy import deepcopy
import importlib.util
from pathlib import Path


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P = load("asset_presentation", "presentation_harness.py")
PORTS = load("asset_ports", "resource_ports.py")
E = load("asset_errors", "error_mapping.py")
C, R, U = P.C, P.R, P.U


class AssetHarness(P.PresentationHarness):
    WIRE_OPERATIONS = P.PresentationHarness.WIRE_OPERATIONS | {"asset.resolve"}
    PROFILE = P.PresentationHarness.PROFILE | {"avatar", "assets"}
    RESOURCE_PROFILES = {PORTS.PROFILE}

    def __init__(self, fixture, records=None, *, decisions=None, target_proofs=None):
        super().__init__(fixture, records, decisions=decisions, target_proofs=target_proofs)
        self.resource_policy = {"approved_origins": ["https://assets.fixture.invalid"], "max_total_bytes": 65536,
            "max_unpacked_bytes": 16384, "max_dependencies": 16, "max_depth": 8,
            "accepted_media_types": [PORTS.MEDIA], "allow_private_network": False}
        self.resources = PORTS.ResourcePorts(C, R, fixture["game"])
        self.state.update(asset_cache={}, asset_receipts={}, asset_binding=None)

    def _scope_extras(self, scope, requested):
        super()._scope_extras(scope, requested)
        if "avatar" in scope["features"]:
            selected = requested.get("forced_avatar", self.state["descriptor"].get("avatar_requirements", {}).get("game_avatar") or requested.get("default_avatar"))
            R.require(selected is not None, "avatar_required")
            R.require(selected["kind"] == "manifest" and "assets" in scope["features"], "feature_unsupported")
            scope["avatar_selection"] = deepcopy(selected)
            scope["resource_policy"] = deepcopy(self.resource_policy)

    def _asset_scope(self, now):
        R.require(self.session is not None, "permission_denied")
        session = self.session.state["session"]
        R.validate_grant(self.session.state["grant"], session["scope"], now=now)
        R.require(session["state"] == "active" and now < session["lease_deadline"], "session_closed")
        R.require(self.state["ledger_healthy"], "temporarily_unavailable")
        R.require(C.codec.canonical(session["scope"]["resource_policy"]) == C.codec.canonical(self.resource_policy), "approval_stale")
        return session["scope"]

    def _asset_reply(self, request, receipt):
        reply = {"request_id": request["request_id"], "error" if "error" in receipt else "result":
                 deepcopy(receipt.get("error", receipt.get("result")))}
        C.validate_reply(request["operation"], request["request_id"], reply)
        return C.codec.canonical(reply)

    def submit(self, raw, credential, *, now, fault=None):
        request = C.validate_request(raw)
        if request["operation"] != "asset.resolve":
            return super().submit(raw, credential, now=now, fault=fault)
        R.require(fault in (None, "before_commit", "after_commit"), "invalid_arguments")
        with self.lock:
            self._maintain(now)
            R.require(credential == "resource-fixture" and self.session is not None, "permission_denied")
            scope = self.session.state["session"]["scope"]
            C.authorize_route("asset.resolve", "resource_owner", "local", scope["features"])
            R.require(self.state["ledger_healthy"], "temporarily_unavailable")
            R.require(request["version"] == scope["version"], "unsupported_version")
            R.require(len(raw) <= scope["limits"]["message_bytes"], "resource_limit")
            C.validate_active_request(raw, selected_extensions=scope["extensions"], supported_extensions=())
            payload = request["payload"]
            R.require(payload["session_id"] == self.session.state["session"]["session_id"] and
                      payload["scope_digest"] == C.codec.digest("scope", scope) and
                      C.codec.canonical(payload["manifest"]) == C.codec.canonical(scope["avatar_selection"]["manifest"]), "permission_denied")
            rid = request["request_id"]
            digest = C.codec.digest("control", {key: request[key] for key in ("version", "operation", "payload", "extensions")})
            old = self.state["asset_receipts"].get(rid)
            R.require(old is None or old["digest"] == digest, "id_conflict")
            if old is not None and "error" in old:
                return self._asset_reply(request, old)
            self._asset_scope(now)
            manifest, policy = payload["manifest"], scope["resource_policy"]
            root_key = self.resources.cache_key(manifest, policy)
            if old is not None:
                R.require(old["cache_key"] == root_key, "approval_stale")
                return self._asset_reply(request, old)
            R.require(len(self.state["asset_receipts"]) < 128, "resource_limit")
            try:
                staged = self.resources.prepare(manifest, policy, self.state["asset_cache"])
                failure = None
            except C.ContractError as error:
                failure, staged = error.code, {}
            def publish():
                # 即使可信端口在准备后通知了撤权/策略变化，也不能发布旧批准的缓存或 ready。
                self._asset_scope(now)
                R.require(root_key == self.resources.cache_key(manifest, policy), "approval_stale")
                receipt = {"digest": digest, "cache_key": root_key, "outcome_ref": manifest["asset_id"]}
                if failure is not None:
                    receipt["failure_reason"] = failure
                    receipt["error"] = E.boundary_error("operation_failed", knowledge="accepted",
                        safe_details={"resource": manifest["asset_id"], "operation_ref": rid})
                    self.session._close("admission_failed", now)
                else:
                    R.require(len(self.state["asset_cache"].keys() | staged.keys()) <= 128, "resource_limit")
                    self.state["asset_cache"].update(staged)
                    self.state["asset_binding"] = {"root": root_key, "keys": sorted(staged)}
                    receipt["result"] = deepcopy(staged[root_key]["receipt"])
                self.state["asset_receipts"][rid] = receipt
                return self._asset_reply(request, receipt)
            return self._transaction(publish, fault)

    def _resources_ready(self, now):
        scope = self._asset_scope(now)
        binding = self.state["asset_binding"]
        root = self.resources.cache_key(scope["avatar_selection"]["manifest"], scope["resource_policy"])
        return (binding is not None and binding["root"] == root and
                all(key in self.state["asset_cache"] for key in binding["keys"]))

    def _has_assets(self):
        return self.session is not None and "assets" in self.session.state["session"]["scope"]["features"]

    def _before_acquire(self, job, now):
        if self._has_assets():
            R.require(self._resources_ready(now), "temporarily_unavailable")
            manifest = self.session.state["session"]["scope"]["avatar_selection"]["manifest"]
            R.require(self.resources.renderer_accepts(manifest, job["acquire"]["device_id"]), "avatar_incompatible")

    def _prepare_rotation(self, record, session, now):
        super()._prepare_rotation(record, session, now)
        if self._has_assets() and record["kind"] == "resume" and "presentation" not in session["scope"]["features"]:
            # 无呈现配置也不能沿用已失效的 parser/policy 收据直接返回 ready。
            R.require(self._resources_ready(now), "temporarily_unavailable")
            R.require(self.resources.renderer_accepts(session["scope"]["avatar_selection"]["manifest"], record["device"]), "avatar_incompatible")

    def finish_admission(self, *, now, success=True, fault=None):
        R.require(type(success) is bool, "invalid_arguments")
        with self.lock:
            self._maintain(now)
            if self._has_assets() and success and self.session.state["session"]["state"] == "active":
                try:
                    ready = self._resources_ready(now)
                except C.ContractError:
                    success = False
                else:
                    if not ready:
                        return deepcopy(self.session.state["session"])
                    session = self.session.state["session"]
                    success = self.resources.renderer_accepts(session["scope"]["avatar_selection"]["manifest"], session.get("controller_device"))
            return super().finish_admission(now=now, success=success, fault=fault)

    def advance_transfer(self, transfer_id, *, now, success=True, fault=None):
        R.require(type(success) is bool, "invalid_arguments")
        with self.lock:
            self._maintain(now)
            record = self.state["transfers"].get(transfer_id)
            if self._has_assets() and record and record["view"]["status"] not in {"ready", "failed"}:
                try:
                    ready = self._resources_ready(now)
                except C.ContractError:
                    ready = False
                manifest = self.session.state["session"]["scope"]["avatar_selection"]["manifest"]
                success = success and ready and self.resources.renderer_accepts(manifest, record["device"])
            return super().advance_transfer(transfer_id, now=now, success=success, fault=fault)

    def _operation_view(self, payload, identity):
        if payload["operation"] != "asset.resolve":
            return super()._operation_view(payload, identity)
        R.require(identity["principal"] == self.fixture["player"], "permission_denied")
        receipt = self.state["asset_receipts"].get(payload["original_request_id"])
        R.require(receipt is not None, "permission_denied")
        return {"operation": "asset.resolve", "request_id": payload["original_request_id"], "outcome_ref": receipt["outcome_ref"],
                "state": "failed" if "error" in receipt else "done", **({"error": deepcopy(receipt["error"])} if "error" in receipt else {})}

    def restart_from_mock_ledger(self, *, now, intact=True):
        restored = super().restart_from_mock_ledger(now=now, intact=intact)
        restored.resources, restored.resource_policy = self.resources, deepcopy(self.resource_policy)
        return restored
