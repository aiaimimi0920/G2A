"""一次启动许可、独立效果与准入的字节装配；不启动真实应用。"""

from copy import deepcopy
import importlib.util
from pathlib import Path


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = load("launch_assets", "asset_harness.py")
L = load("launch_port", "launcher_port.py")
C, R, U, E = A.C, A.R, A.U, A.E


class LaunchHarness(A.AssetHarness):
    WIRE_OPERATIONS = A.AssetHarness.WIRE_OPERATIONS | {"launch.request"}

    def __init__(self, fixture, records=None, *, decisions=None, target_proofs=None):
        super().__init__(fixture, records, decisions=decisions, target_proofs=target_proofs)
        self.launcher = L.LauncherPort(C, R, fixture["player"], fixture["agent"])
        self.identities["agent-identity"]["device_id"] = self.launcher.registration["device_id"]
        self.state.update(launch_permits={}, launch_records={})
        self.before_dispatch = self.after_effect = None  # 可信调度注入点；不由请求指定。

    def _create(self, payload, identity, now):
        binding = self.launcher.binding()
        R.require(binding["player"] == self.fixture["player"] and binding["agent"] == self.fixture["agent"], "permission_denied")
        if payload["entry"] == "companion":
            R.require(self.launcher.available(binding), "consent_required")
            self._fresh(identity, now, binding["device_id"])
        record = super()._create(payload, identity, now)
        record["launch_binding"] = binding
        record["view"]["launch_required"] = not self.launcher.available(binding)
        return record

    def _decision_options(self, record, payload, evidence, now):
        R.require(not payload["remember"], "feature_unsupported")
        if payload["launch_permission"]:
            binding = record["launch_binding"]
            R.require(C.codec.canonical(binding) == C.codec.canonical(self.launcher.binding()), "approval_stale")
            R.require(C.codec.canonical(evidence.get("launch_binding")) == C.codec.canonical(binding), "consent_required")
            ref, view = payload["decision_ref"], record["view"]
            R.require(ref not in self.state["launch_permits"], "id_conflict")
            self.state["launch_permits"][ref] = {"offer_id": view["offer_id"], "player": deepcopy(view["immutable_scope"]["player"]),
                "scope_digest": view["scope_digest"], "binding": deepcopy(binding), "expires_at": view["decision_deadline"],
                "request_id": None}

    def _available_for_offer(self, record):
        return self.launcher.available(record["launch_binding"])

    def _redeem(self, payload, identity, now):
        record = self._offer(payload["offer_id"], identity)
        R.require(self._available_for_offer(record), "temporarily_unavailable")
        self._fresh(identity, now, record["launch_binding"]["device_id"])
        return super()._redeem(payload, identity, now)

    def _join(self, payload, identity, now):
        invitation = self.state["invitations"].get(payload["invitation_id"])
        R.require(invitation is not None, "permission_denied")
        record = self.state["offers"][invitation["offer_id"]]
        R.require(self._available_for_offer(record), "temporarily_unavailable")
        first_join = self.session is None
        invitation = super()._join(payload, identity, now)
        if first_join:
            device = record["launch_binding"]["device_id"]
            control = self.session.credentials[invitation["control"]]
            R.require(self.session.state["session"].get("controller_device") in (None, device) and
                      control.get("device_id") in (None, device), "permission_denied")
            self.session.state["session"]["controller_device"] = control["device_id"] = device
        return invitation

    def _receipt_result(self, receipt, identity, now):
        result = super()._receipt_result(receipt, identity, now)
        if receipt["kind"] in {"invitation", "join"} and ("invitation_credential" in result or "control_credential" in result):
            invitation = self.state["invitations"][receipt["ref"]]
            record = self.state["offers"][invitation["offer_id"]]
            valid = self._available_for_offer(record)
            if receipt["kind"] == "invitation":
                try:
                    self._fresh(identity, now, record["launch_binding"]["device_id"])
                except C.ContractError:
                    valid = False
            if not valid:
                return {"status": "completed_without_secret", "outcome_ref": invitation.get("session_id", invitation["id"]), "reauth_required": True}
        return result

    def finish_admission(self, *, now, success=True, fault=None):
        R.require(type(success) is bool, "invalid_arguments")
        with self.lock:
            if self.state["admission"] is not None:
                invitation = self.state["invitations"][self.state["admission"]["invitation"]]
                success = success and self._available_for_offer(self.state["offers"][invitation["offer_id"]])
            return super().finish_admission(now=now, success=success, fault=fault)

    def _authorize_launch(self, payload, identity, now, rid):
        record = self._offer(payload["offer_id"], identity)
        view = record["view"]
        R.require(view["state"] == "approved", "consent_required")
        self._current_scope(record, now)
        R.validate_grant(self._grant(view["grant_id"]), view["immutable_scope"], now=now)
        R.require(now < view["decision_deadline"], "offer_expired")
        R.require("invitation" not in record, "invitation_used")
        permit = self.state["launch_permits"].get(payload["launch_permission_ref"])
        R.require(permit is not None and permit["offer_id"] == view["offer_id"] and permit["player"] == identity["principal"] and
                  permit["scope_digest"] == view["scope_digest"] and now < permit["expires_at"], "consent_required")
        R.require(payload["application_registration"] == permit["binding"]["application_registration"], "permission_denied")
        R.require(C.codec.canonical(permit["binding"]) == C.codec.canonical(record["launch_binding"]) ==
                  C.codec.canonical(self.launcher.binding()), "approval_stale")
        R.require(permit["request_id"] in (None, rid), "id_conflict")
        return permit

    def _record_outcome(self, rid, observation):
        record = self.state["launch_records"][rid]
        if record["state"] in {"done", "failed"}:
            return
        if observation is None or observation["state"] == "unknown":
            record.update(state="pending", error=E.boundary_error("internal_failure", knowledge="unknown",
                          safe_details={"operation_ref": rid}))
        elif observation["state"] == "done":
            record.update(state="done", result=deepcopy(observation["result"]))
            record.pop("error", None)
        else:
            record.update(state="failed", failure_reason=observation.get("reason", "launch_failed"),
                          error=E.boundary_error("launch_failed", knowledge="accepted", safe_details={"operation_ref": rid}))
            offer = self.state["offers"][record["payload"]["offer_id"]]
            grant = self._grant(offer["view"]["grant_id"])
            if grant["state"] == "active":
                self._revoke({"object_type": "grant", "object_id": grant["grant_id"], "expected_revision": grant["revision"]}, self.state["last_now"])

    def _observation(self, record):
        """异常/畸形效果见证只能降为 unknown，不能漏到外层被写成 not_accepted。"""
        try:
            value = self.launcher.query(record["payload"]["launch_permission_ref"], record["binding"])
            if type(value) is not dict or value.get("state") not in {"unknown", "done", "failed"}:
                return None
            if C.codec.canonical(value.get("binding")) != C.codec.canonical(record["binding"]):
                return None
            if value["state"] == "done":
                C.validate_reply("launch.request", "fixture-observation", {"request_id": "fixture-observation", "result": value.get("result")})
            return value
        except Exception:
            return None

    def _launch_reply(self, request):
        record = self.state["launch_records"][request["request_id"]]
        field = "result" if record["state"] == "done" else "error"
        reply = {"request_id": request["request_id"], field: deepcopy(record[field])}
        C.validate_reply("launch.request", request["request_id"], reply)
        return C.codec.canonical(reply)

    def submit(self, raw, credential, *, now, fault=None):
        request = C.validate_request(raw)
        if request["operation"] != "launch.request":
            return super().submit(raw, credential, now=now, fault=fault)
        R.require(fault in (None, "before_commit", "after_accept", "after_dispatch", "after_effect", "before_result_commit", "after_commit"), "invalid_arguments")
        with self.lock:
            self._maintain(now)
            R.require(self.state["ledger_healthy"], "temporarily_unavailable")
            identity = self._identity(credential, "launch.request")
            C.authorize_route("launch.request", identity["role"], "local", self.PROFILE)
            R.require(request["version"] == self.fixture["scope"]["version"], "unsupported_version")
            R.require(len(raw) <= self.state["descriptor"]["limits"]["message_bytes"], "resource_limit")
            C.validate_active_request(raw, selected_extensions={}, supported_extensions=())
            rid, payload = request["request_id"], request["payload"]
            digest = C.codec.digest("control", {key: request[key] for key in ("version", "operation", "payload", "extensions")})
            old = self.state["launch_records"].get(rid)
            if old is not None:
                R.require(old["digest"] == digest and old["player"] == identity["principal"], "id_conflict")
            else:
                self._authorize_launch(payload, identity, now, rid)
                R.require(len(self.state["launch_records"]) < 128, "resource_limit")
                def accept():
                    permit = self._authorize_launch(payload, identity, now, rid)
                    permit["request_id"] = rid
                    self.state["launch_records"][rid] = {"digest": digest, "player": deepcopy(identity["principal"]),
                        "payload": deepcopy(payload), "binding": deepcopy(permit["binding"]), "dispatched": False,
                        "state": "pending", "error": E.boundary_error("internal_failure", knowledge="unknown", safe_details={"operation_ref": rid})}
                self._transaction(accept, "before_commit" if fault == "before_commit" else None)
            if fault == "after_accept":
                raise U.S.H.InjectedFailure(fault)
            record = self.state["launch_records"][rid]
            if record["state"] == "pending" and not record["dispatched"]:
                if self.before_dispatch is not None:
                    callback, self.before_dispatch = self.before_dispatch, None
                    callback()
                try:
                    def mark_dispatch():
                        self._authorize_launch(payload, identity, max(now, self.state["last_now"]), rid)
                        # authority 已标派发但端口无记录也属于未决，不能换一份许可绕过去。
                        R.require(self.launcher.available(self.state["launch_records"][rid]["binding"]) or not any(
                            key != rid and prior["state"] == "pending" and prior["dispatched"]
                            for key, prior in self.state["launch_records"].items()), "temporarily_unavailable")
                        self.state["launch_records"][rid]["dispatched"] = True
                    self._transaction(mark_dispatch)
                except C.ContractError as error:
                    self._transaction(lambda: self._record_outcome(rid, {"state": "failed", "reason": error.code}))
                    return self._launch_reply(request)
                if fault == "after_dispatch":
                    raise U.S.H.InjectedFailure(fault)
                record = self.state["launch_records"][rid]
                try:
                    self.launcher.start(payload["launch_permission_ref"], record["binding"])
                except Exception:
                    # 派发标记已提交。即使端口抛出异常，也只能查原账本，不再调用 start。
                    pass
                if self.after_effect is not None:
                    callback, self.after_effect = self.after_effect, None
                    callback()
                if fault == "after_effect":
                    raise U.S.H.InjectedFailure(fault)
            def finish():
                current = self.state["launch_records"][rid]
                self._record_outcome(rid, self._observation(current))
                return self._launch_reply(request)
            return self._transaction(finish, "before_commit" if fault == "before_result_commit" else "after_commit" if fault == "after_commit" else None)

    def _operation_view(self, payload, identity):
        if payload["operation"] != "launch.request":
            return super()._operation_view(payload, identity)
        record = self.state["launch_records"].get(payload["original_request_id"])
        R.require(record is not None and record["player"] == identity["principal"], "permission_denied")
        self._record_outcome(payload["original_request_id"], self._observation(record))
        record = self.state["launch_records"][payload["original_request_id"]]
        return {"operation": "launch.request", "request_id": payload["original_request_id"], "state": record["state"],
                "outcome_ref": record["payload"]["offer_id"], **({"error": deepcopy(record["error"])} if "error" in record else {})}

    def restart_from_mock_ledger(self, *, now, intact=True):
        with self.lock:
            if self.session is not None:
                restored = super().restart_from_mock_ledger(now=now, intact=intact)
            else:
                R.require(type(intact) is bool, "invalid_arguments")
                self._maintain(now)
                restored = type(self)(self.fixture, self.records, decisions=self.decisions, target_proofs=self.target_proofs)
                restored.state, restored.identities = deepcopy(self.state), deepcopy(self.identities)
                restored.state["ledger_healthy"] = intact and self.state["ledger_healthy"]
                restored.devices, restored.observations = self.devices, deepcopy(self.observations)
                restored.resources, restored.resource_policy = self.resources, deepcopy(self.resource_policy)
                self.state["retired"] = True
            restored.launcher = self.launcher  # 启动效果域独立，不随 authority 回滚或复制成新进程。
            return restored
