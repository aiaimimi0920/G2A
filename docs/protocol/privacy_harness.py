"""独立主体隐私通道与可信假存储的字节装配；不借游戏 Grant 签发删除权。"""

from copy import deepcopy
import importlib.util
from pathlib import Path


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


L = load("privacy_launch", "launch_harness.py")
M = load("privacy_memory", "memory_store.py")
C, R, U = L.C, L.R, L.U


class PrivacyHarness(L.LaunchHarness):
    PRIVACY = {"privacy.request", "privacy.receipt"}
    WIRE_OPERATIONS = L.LaunchHarness.WIRE_OPERATIONS | PRIVACY
    PROFILE = L.LaunchHarness.PROFILE | {"privacy-request"}

    def __init__(self, fixture, records=None, *, decisions=None, target_proofs=None, memory_copies=None):
        super().__init__(fixture, records, decisions=decisions, target_proofs=target_proofs)
        # 固定且独立协商的隐私 endpoint 上下文。不是由调用者填写 controller/session。
        self.privacy_route = {"controller": deepcopy(fixture["agent"]), "instance": deepcopy(fixture["scope"]["instance"]),
            "session_id": fixture["session"]["session_id"], "version": fixture["scope"]["version"],
            "features": sorted(set(fixture["scope"]["features"]) & set(fixture["descriptor"]["supported_features"]) &
                               set(fixture["requested"]["supported_features"])),
            "message_bytes": fixture["scope"]["limits"]["message_bytes"]}
        self.privacy_identities = {"subject-fixture": {"role": "data_subject", "lane": "privacy",
            "principal": deepcopy(fixture["player"]), "controller": deepcopy(fixture["agent"]),
            "fresh": True, "expires_at": 900000}}
        self.memory = M.MemoryStore(C, R, self.privacy_route["controller"], records or {}, memory_copies or {})
        self.state.update(privacy_sources=deepcopy(records or {}), privacy_requests={}, privacy_keys={}, privacy_cutoffs={},
                          privacy_disclosed=set())

    def _transaction(self, function, fault=None):
        def apply():
            result = function()
            if "privacy_disclosed" in self.state and self.session is not None:
                # 游戏 authority 的 outbox 不属于伙伴存储；接受时永久记下已知外部副本。
                # 与 outbox 接受同事务，历史压缩/丢回复不能抹除这一例外事实。
                for item in self.session.state["events"]:
                    self.state["privacy_disclosed"].update(set(item["sources"]) & self.state["privacy_sources"].keys())
            return result
        return super()._transaction(apply, fault)

    @staticmethod
    def _source_binding(record):
        return {key: deepcopy(record[key]) for key in ("instance", "session_id", "source", "controller")}

    def _subject(self, credential, operation, now):
        identity = self.privacy_identities.get(credential)
        R.require(identity is not None, "permission_denied")
        C.authorize_route(operation, identity["role"], identity["lane"], self.privacy_route["features"])
        R.require(identity.get("fresh") is True and type(identity.get("expires_at")) is int and now < identity["expires_at"], "unauthenticated")
        C.validate_type("Principal", identity["principal"])
        R.require(identity["controller"] == self.privacy_route["controller"] == self.memory.controller, "permission_denied")
        return identity["principal"]

    def _sources(self, refs, subject):
        for ref in refs:
            record = self.state["privacy_sources"].get(ref)
            stored = self.memory.sources.get(ref)
            R.require(record is not None and stored is not None, "permission_denied")
            C.validate_type("SourceAuthorization", record)
            R.require(record["source"]["source_id"] == ref and record["instance"] == self.privacy_route["instance"] and
                      record["session_id"] == self.privacy_route["session_id"] and record["controller"] == self.privacy_route["controller"], "permission_denied")
            R.require(R.principal_key(subject) in R.principal_set(record["source"]["source_principals"]), "permission_denied")
            R.require(C.codec.canonical(self._source_binding(record)) == C.codec.canonical(self._source_binding(stored)), "permission_denied")
            if self.session is not None:
                active = self.session.state["records"].get(ref)
                R.require(active is not None and C.codec.canonical(self._source_binding(active)) == C.codec.canonical(self._source_binding(record)), "permission_denied")
        # 披露授权的 expiry/revocation 不撤销数据主体的独立隐私权。
        return self.memory.plan(refs)

    def _cutoff(self, refs, now):
        for ref in refs:
            record = self.state["privacy_sources"][ref]
            cutoff = self.state["privacy_cutoffs"].get(ref)
            if cutoff is None:
                cutoff = {"revision": record["revision"] + 1, "at": now,
                          "binding": self._source_binding(record)}
                C.validate_type("Revision", cutoff["revision"])
                self.state["privacy_cutoffs"][ref] = cutoff
            record.update(state="revoked", revision=max(record["revision"], cutoff["revision"]))
            if self.session is not None:
                current = self.session.state["records"][ref]
                current.update(state="revoked", revision=max(current["revision"], cutoff["revision"]))

    def _join(self, payload, identity, now):
        first_join = self.session is None
        result = super()._join(payload, identity, now)
        if first_join:
            self.session.state["records"] = deepcopy(self.state["privacy_sources"])
        # privacy 可在尚无游戏 Session 时受理；首次 join 不能复活旧来源。
        for ref, cutoff in self.state["privacy_cutoffs"].items():
            if ref in self.session.state["records"]:
                record = self.session.state["records"][ref]
                record.update(state="revoked", revision=max(record["revision"], cutoff["revision"]))
        return result

    def refresh_disclosures(self, importer, *, now):
        """可信导入器刷新；固定 source handle 不换绑，cutoff 胜过更高 revision 的重新授权。"""
        with self.lock:
            self._maintain(now)
            records = importer.snapshot(self.fixture["session"], now=now)
            def refresh():
                R.require(set(records) == set(self.state["privacy_sources"]), "permission_denied")
                for ref, incoming in records.items():
                    C.validate_type("SourceAuthorization", incoming)
                    old = self.state["privacy_sources"][ref]
                    R.require(C.codec.canonical(self._source_binding(old)) == C.codec.canonical(self._source_binding(incoming)), "permission_denied")
                    updated = deepcopy(incoming)
                    if ref in self.state["privacy_cutoffs"]:
                        updated.update(state="revoked", revision=max(old["revision"], incoming["revision"]))
                    else:
                        R.require(incoming["revision"] >= old["revision"], "approval_stale")
                    self.state["privacy_sources"][ref] = updated
                    if self.session is not None:
                        self.session.state["records"][ref] = deepcopy(updated)
            return self._transaction(refresh)

    def _read(self, request_id, subject):
        record = self.state["privacy_requests"].get(request_id)
        R.require(record is not None and record["binding"]["subject"] == subject, "permission_denied")
        return record

    def _observe(self, request_id):
        record = self.state["privacy_requests"][request_id]
        if record["receipt"]["status"] != "pending" or not record["dispatched"]:
            return
        try:
            binding = record["binding"]
            observation = self.memory.query(binding["provider_operation_ref"])
            if not self.memory.verify_observation(observation, binding):
                return
            receipt = observation["receipt"]
            C.validate_type("PrivacyReceipt", receipt)
            R.require(receipt["privacy_request_id"] == request_id and receipt["controlled_scope"] == binding["source_refs"], "invalid_message")
            if receipt["status"] == "pending":
                R.require(type(receipt["poll_after_ms"]) is int and 1 <= receipt["poll_after_ms"] <= 60000, "invalid_message")
            else:
                R.require(all(item["source_id"] in binding["source_refs"] for item in receipt["exceptions"]), "invalid_message")
                R.require((receipt["status"] == "done") == (not receipt["exceptions"]), "invalid_message")
            record["receipt"] = deepcopy(receipt)
        except Exception:
            # 已受理后的失联、畸形/矛盾回执只保留 pending，不谎报 not_accepted 或 done。
            return

    def submit(self, raw, credential, *, now, fault=None):
        request = C.validate_request(raw)
        if request["operation"] not in self.PRIVACY:
            return super().submit(raw, credential, now=now, fault=fault)
        R.require(fault in (None, "before_commit", "after_accept", "after_dispatch", "after_effect", "before_result_commit", "after_commit"), "invalid_arguments")
        with self.lock:
            self._maintain(now)
            R.require(self.state["ledger_healthy"], "temporarily_unavailable")
            subject = self._subject(credential, request["operation"], now)
            R.require(request["version"] == self.privacy_route["version"], "unsupported_version")
            R.require(len(raw) <= self.privacy_route["message_bytes"], "resource_limit")
            C.validate_active_request(raw, selected_extensions={}, supported_extensions=())
            if request["operation"] == "privacy.receipt":
                pid = request["payload"]["privacy_request_id"]
                self._read(pid, subject)
            else:
                key = (R.principal_key(subject), request["request_id"])
                digest = C.codec.digest("control", {key: request[key] for key in ("version", "operation", "payload", "extensions")})
                pid = self.state["privacy_keys"].get(key)
                if pid is not None:
                    R.require(self._read(pid, subject)["digest"] == digest, "id_conflict")
                else:
                    refs = sorted(request["payload"]["source_refs"])
                    inventory = self._sources(refs, subject)
                    R.require(not any(record["receipt"]["status"] == "pending" and set(refs) & set(record["binding"]["source_refs"])
                                      for record in self.state["privacy_requests"].values()), "temporarily_unavailable")
                    R.require(len(self.state["privacy_requests"]) < 128, "resource_limit")
                    pid = "privacy-" + str(len(self.state["privacy_requests"]) + 1)
                    def accept():
                        self._cutoff(refs, now)
                        binding = {"privacy_request_id": pid, "provider_operation_ref": "memory-" + pid,
                            "controller": deepcopy(self.privacy_route["controller"]), "subject": deepcopy(subject),
                            "source_refs": refs, "desired_action": request["payload"]["desired_action"],
                            "inventory": inventory, "accepted_at": now,
                            "external_sources": sorted(set(refs) & self.state["privacy_disclosed"]),
                            "cutoffs": {ref: deepcopy(self.state["privacy_cutoffs"][ref]) for ref in refs}}
                        self.state["privacy_keys"][key] = pid
                        self.state["privacy_requests"][pid] = {"digest": digest, "binding": binding, "dispatched": False,
                            "receipt": {"privacy_request_id": pid, "status": "pending", "controlled_scope": refs, "poll_after_ms": 1000}}
                        return self._reply(request, self.state["privacy_requests"][pid]["receipt"])
                    self._transaction(accept, "before_commit" if fault == "before_commit" else None)
                if fault == "after_accept":
                    raise U.S.H.InjectedFailure(fault)
                record = self.state["privacy_requests"][pid]
                if not record["dispatched"]:
                    self._transaction(lambda: self.state["privacy_requests"][pid].update(dispatched=True))
                    if fault == "after_dispatch":
                        raise U.S.H.InjectedFailure(fault)
                    try:
                        self.memory.apply(self.state["privacy_requests"][pid]["binding"], now=now)
                    except Exception:
                        pass  # 派发标记已经提交；只查原存储 operation，不猜测安全重发。
                    if fault == "after_effect":
                        raise U.S.H.InjectedFailure(fault)
            def finish():
                self._observe(pid)
                return self._reply(request, self.state["privacy_requests"][pid]["receipt"])
            try:
                return self._transaction(finish, "before_commit" if fault in {"before_result_commit", "before_commit"} else
                                         "after_commit" if fault == "after_commit" else None)
            except (C.ContractError, C.codec.CodecError):
                # 接受后的序列化/响应校验失败不能落入外层 not_accepted 映射。
                reply = {"request_id": request["request_id"], "error": L.E.boundary_error("internal_failure", knowledge="unknown",
                         safe_details={"operation_ref": pid})}
                C.validate_reply(request["operation"], request["request_id"], reply)
                return C.codec.canonical(reply)

    def restart_from_mock_ledger(self, *, now, intact=True):
        with self.lock:
            restored = super().restart_from_mock_ledger(now=now, intact=intact)
            restored.memory = self.memory  # 真实效果域不因 authority 重启而复原、复制或重新删除。
            restored.privacy_route = deepcopy(self.privacy_route)
            restored.privacy_identities = deepcopy(self.privacy_identities)
            return restored
