"""控制权恢复/转移的内存账本端口模型；无设备呈现、无真实持久化或密钥服务。"""

from copy import deepcopy
import importlib.util
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("control_admission", Path(__file__).with_name("admission_harness.py"))
A = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(A)
C, R, U = A.C, A.R, A.U


class ControlHarness(A.AdmissionHarness):
    CONTROL = frozenset({"session.resume", "session.handoff", "session.claim_control"})
    WIRE_OPERATIONS = A.AdmissionHarness.WIRE_OPERATIONS | CONTROL
    PROFILE = A.AdmissionHarness.PROFILE | {"resume", "handoff"}
    LEDGERS = {"volatile", "durable"}

    def __init__(self, fixture, records=None, *, decisions=None, target_proofs=None):
        super().__init__(fixture, records, decisions=decisions)
        self.target_proofs = deepcopy(target_proofs or {})
        self.identities["agent-identity"].update(fresh=True, device_id=None, expires_at=fixture["scope"]["expires_at"])
        self.state.update(transfers={}, ledger_healthy=True, transport_counter=1, retired=False)

    def _maintain(self, now):
        R.require(not self.state["retired"], "resume_denied")
        super()._maintain(now)
        def expire():
            for record in self.state["transfers"].values():
                if record["view"]["status"] in {"releasing", "acquiring"}:
                    if (not self.state["ledger_healthy"] or self.session.state["session"]["state"] == "closed" or
                            now >= record["view"]["deadline"]):
                        self._fail(record, "transfer_failed", now)
        self._transaction(expire)

    def _fresh(self, identity, now, device):
        R.require(identity["role"] == "agent" and identity.get("fresh") is True and
                  type(identity.get("expires_at")) is int and now < identity["expires_at"], "unauthenticated")
        R.require(identity.get("device_id") == device, "permission_denied")

    def _live(self, now, *, ready=True):
        R.require(self.session is not None, "permission_denied")
        R.require(self.state["ledger_healthy"], "resume_denied")
        session = self.session.state["session"]
        R.validate_grant(self.session.state["grant"], session["scope"], now=now)
        R.require(session["scope"]["ledger_durability"] == "durable", "resume_denied")
        R.require(session["state"] == "active" and now < session["lease_deadline"], "session_closed")
        R.require(session["instance_epoch"] == session["scope"]["instance"]["epoch"], "resume_denied")
        R.require(not ready or session["ready"], "transfer_in_progress")
        # 恢复的是完整业务快照，不只检查一个健康标志。
        try:
            snapshot = self.session._snapshot(session["scope"]["agent"], now)
            U.S.E.BusinessConsumer(snapshot, session["scope"]["agent"])
        except (C.ContractError, U.S.E.C.ContractError, C.codec.CodecError, KeyError, TypeError):
            raise C.ContractError("resume_denied") from None
        return session

    def submit(self, raw, credential, *, now, fault=None):
        request = C.validate_request(raw)
        op, payload = request["operation"], request["payload"]
        if not self.state["ledger_healthy"] and op not in {"session.close", "permission.revoke"}:
            raise C.ContractError("resume_denied" if op in self.CONTROL else "result_unavailable" if op == "action.query" else "temporarily_unavailable")
        if op not in self.CONTROL:
            return super().submit(raw, credential, now=now, fault=fault)
        with self.lock:
            self._maintain(now)
            def apply():
                identity = self._identity(credential, op)
                R.require(self.session is not None, "permission_denied")
                session = self.session.state["session"]
                C.authorize_route(op, identity["role"], "control", session["scope"]["features"])
                R.require(payload["session_id"] == session["session_id"], "permission_denied")
                R.require(request["version"] == session["scope"]["version"], "unsupported_version")
                R.require(len(raw) <= session["scope"]["limits"]["message_bytes"], "resource_limit")
                C.validate_active_request(raw, selected_extensions=session["scope"]["extensions"], supported_extensions=())
                key = (R.principal_key(identity["principal"]), op, request["request_id"])
                digest = C.codec.digest("control", {key: request[key] for key in ("version", "operation", "payload", "extensions")})
                old = self.state["receipts"].get(key)
                if old is not None:
                    R.require(old["digest"] == digest, "id_conflict")
                    return self._reply(request, self._receipt_result(old, identity, now))
                R.require(len(self.state["receipts"]) < 128, "resource_limit")
                if op == "session.resume":
                    session = self._live(now)
                    self._fresh(identity, now, session.get("controller_device"))
                    R.require(payload.get("device_id") == session.get("controller_device"), "handoff_required")
                    R.require(now < session.get("resume_until", 0), "resume_denied")
                    R.require(payload["expected_generation"] == session["control_generation"], "generation_conflict")
                    record = self._rotate("resume", session.get("controller_device"), now, session["lease_deadline"])
                    kind = "resume"
                elif op == "session.handoff":
                    session = self._live(now)
                    R.require(payload["expected_generation"] == session["control_generation"], "generation_conflict")
                    evidence = self.decisions.get(payload["decision_ref"])
                    scope_digest = C.codec.digest("scope", session["scope"])
                    R.require(evidence is not None and evidence.get("player") == identity["principal"] and
                              evidence.get("scope_digest") == scope_digest and
                              C.codec.canonical(evidence.get("payload")) == C.codec.canonical(payload), "consent_required")
                    proof = self.target_proofs.get(payload["target_proof_ref"])
                    R.require(proof is not None and proof.get("agent") == session["scope"]["agent"] and
                              proof.get("device_id") == payload["target_device"] and proof.get("session_id") == session["session_id"] and
                              proof.get("scope_digest") == scope_digest and type(proof.get("expires_at")) is int and now < proof["expires_at"], "permission_denied")
                    R.require(payload["target_device"] != session.get("controller_device"), "handoff_required")
                    record = self._rotate("handoff", payload["target_device"], now, min(now + 30000, proof["expires_at"], session["lease_deadline"]))
                    kind = "handoff"
                else:
                    record = self.state["transfers"].get(payload["transfer_id"])
                    R.require(record is not None and record["kind"] == "handoff", "permission_denied")
                    R.require(payload["target_device"] == record["view"]["target_device"], "permission_denied")
                    self._fresh(identity, now, record["device"])
                    kind = "claim"
                receipt = {"kind": kind, "ref": record["id"], "digest": digest, "operation": op, "request_id": request["request_id"]}
                self.state["receipts"][key] = receipt
                return self._reply(request, self._receipt_result(receipt, identity, now))
            return self._transaction(apply, fault)

    def _rotate(self, kind, device, now, deadline):
        child = self.session
        if child.pending_sync:
            child._sync_action(now)
        child._reserve_stop()
        session = child.state["session"]
        previous = session["control_generation"]
        generation = previous + 1
        R.require(generation <= C.codec.MAX_INTEGER, "resource_limit")
        cid = "control-" + str(len(self.state["transfers"]) + 1)
        token = "fixture-control-s1-" + str(generation) + "-" + session["transport_epoch"]
        session.update(control_generation=generation, ready=kind == "resume")
        if kind == "resume" and device is not None:
            session["controller_device"] = device
        child._stop_action(now)  # Grant 仍有效；只阻止旧动作产生新效果。
        session = child.state["session"]  # 动作同步可能提交了新的状态副本。
        child.credentials[token] = {"role": "companion_control", "principal": deepcopy(session["scope"]["agent"]),
            "generation": generation, "transport_epoch": session["transport_epoch"], "device_id": device}
        record = {"id": cid, "kind": kind, "device": device, "credential": token,
                  "transport_epoch": session["transport_epoch"], "result_handle": "fixture-results-s1",
                  "view": {"transfer_id": cid, "session_id": session["session_id"], "old_generation": previous,
                    "new_generation": generation, "target_device": device if device is not None else "fixture-no-device",
                    "status": "ready" if kind == "resume" else "acquiring", "deadline": deadline}}
        self.state["transfers"][cid] = record
        self._prepare_rotation(record, session, now)
        child._notice("session.control_changed", {"session": session}, now)
        return record

    def _prepare_rotation(self, record, session, now):
        """无呈现配置的准备阶段为空；设备 profile 可在发事件前进入 releasing。"""

    def _secret_view(self, record, identity, now):
        self._fresh(identity, now, record["device"])
        view, session = record["view"], self.session.state["session"]
        safe = {"status": "completed_without_secret", "outcome_ref": view["session_id"], "reauth_required": True}
        if (not self.state["ledger_healthy"] or session["state"] != "active" or self.session.state["grant"]["state"] != "active" or
                now >= min(session["lease_deadline"], self.session.state["grant"]["expires_at"]) or
                view["new_generation"] != session["control_generation"] or record["transport_epoch"] != session["transport_epoch"] or
                view["status"] == "failed"):
            return safe
        if view["status"] != "ready" or not session["ready"]:
            return {"status": "pending", "outcome_ref": record["id"], "reauth_required": False}
        R.require(session.get("controller_device") == record["device"], "permission_denied")
        return self._delivery(record["credential"], record["result_handle"], now)

    def _receipt_result(self, receipt, identity, now):
        if receipt["kind"] in {"resume", "handoff", "claim"}:
            record = self.state["transfers"][receipt["ref"]]
            return deepcopy(record["view"]) if receipt["kind"] == "handoff" else self._secret_view(record, identity, now)
        return super()._receipt_result(receipt, identity, now)

    def _operation_view(self, payload, identity):
        key = (R.principal_key(identity["principal"]), payload["operation"], payload["original_request_id"])
        receipt = self.state["receipts"].get(key)
        if receipt is None or receipt["kind"] not in {"resume", "handoff", "claim"}:
            return super()._operation_view(payload, identity)
        record = self.state["transfers"][receipt["ref"]]
        view, session = record["view"], self.session.state["session"]
        # 已到达 ready 是原控制请求的终态；后来关闭不证明原转移失败。
        failed = view["status"] != "ready" and (view["status"] == "failed" or session["state"] == "closed")
        return {"operation": receipt["operation"], "request_id": receipt["request_id"], "outcome_ref": record["id"],
                "state": "failed" if failed else "done" if view["status"] == "ready" else "pending",
                **({"transfer": deepcopy(view)} if record["kind"] == "handoff" else {"session": deepcopy(session)})}

    def _fail(self, record, reason, now):
        record["view"].update(status="failed", failure_reason=reason)
        self.session._close(reason, now)

    def advance_transfer(self, transfer_id, *, now, success=True, fault=None):
        """可信目标准备假端口；此 profile 无 presentation，旧呈现释放为空，不接收网络自报 ACK。"""
        R.require(type(success) is bool, "invalid_arguments")
        with self.lock:
            self._maintain(now)
            def advance():
                record = self.state["transfers"].get(transfer_id)
                R.require(record is not None and record["kind"] == "handoff", "permission_denied")
                view = record["view"]
                if view["status"] in {"ready", "failed"}:
                    return deepcopy(view)
                session = self._live(now, ready=False)
                if (not success or now >= view["deadline"] or session["control_generation"] != view["new_generation"] or
                        session["transport_epoch"] != record["transport_epoch"]):
                    self._fail(record, "transfer_failed", now)
                else:
                    self.session._reserve_stop()
                    session["ready"] = True
                    session["controller_device"] = record["device"]
                    view["status"] = "ready"
                    self.session._notice("session.ready", {"session": session}, now)
                return deepcopy(record["view"])
            return self._transaction(advance, fault)

    def restart_from_mock_ledger(self, *, now, intact=True):
        """复制完整内存假账本到新 authority 并退休旧实例；不是磁盘/进程崩溃恢复证据。"""
        R.require(type(intact) is bool, "invalid_arguments")
        with self.lock:
            self._maintain(now)
            R.require(self.session is not None, "permission_denied")
            restored = type(self)(self.fixture, self.records, decisions=self.decisions, target_proofs=self.target_proofs)
            restored.state, restored.identities = deepcopy(self.state), deepcopy(self.identities)
            fixture = deepcopy(self.fixture)
            fixture.update(scope=deepcopy(self.session.state["session"]["scope"]), session=deepcopy(self.session.state["session"]),
                           grant=deepcopy(self.session.state["grant"]))
            restored.session = U.SessionHarness(fixture, self.records)
            restored.session.state = deepcopy(self.session.state)
            restored.session.members = deepcopy(self.session.members)
            restored.session.credentials = deepcopy(self.session.credentials)
            restored.session.pending_sync = self.session.pending_sync
            restored.session.scan_budget = self.session.scan_budget
            restored.session.membership_proofs = deepcopy(self.session.membership_proofs)
            restored.session.player_seat_proofs = deepcopy(self.session.player_seat_proofs)
            restored.session.action_model.decisions = deepcopy(self.session.action_model.decisions)
            restored.session.action_model.restore(self.session.action_model.checkpoint())
            restored.session.lock = restored.session.action_model.lock = restored.lock
            restored.state["transport_counter"] += 1
            restored.session.state["session"]["transport_epoch"] = "transport-" + str(restored.state["transport_counter"])
            restored.state["ledger_healthy"] = intact and self.state["ledger_healthy"]
            for record in restored.state["transfers"].values():
                if record["view"]["status"] in {"releasing", "acquiring"}:
                    restored._fail(record, "transfer_failed", now)
            self.state["retired"] = True
            return restored
