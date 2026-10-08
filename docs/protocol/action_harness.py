"""六个动作操作的字节入口装配；固定凭据与受信执行端口，无网络。

单会话单动作，复用 MultiStepModel。玩家决定只来自预置可信证据，不信任自报确认。
"""

from copy import deepcopy
import importlib.util
from pathlib import Path


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


H = load("action_chat_authority", "chat_harness.py")
M = load("action_multistep", "multistep_model.py")
C, R = H.C, H.R


class ActionHarness:
    STATE_FIELDS = ("definition", "definition_available", "receipts", "deadline", "read_until", "read_revoked", "revision",
                    "confirmations", "control_receipts", "accepted", "wire_ticket", "committed_fact")

    def __init__(self, fixture, *, decisions=None, authority=None):
        self.authority = H.ChatHarness(fixture, {}) if authority is None else authority
        self.lock = self.authority.lock
        self.model = M.MultiStepModel()
        # 最小 core 不需要虚构动作定义；已批准动作的固定模型仍必须提供定义。
        self.definition = deepcopy(fixture.get("action"))
        R.require(("actions" not in fixture["scope"]["features"] and not fixture["scope"]["action_ids"]) or
                  self.definition is not None, "invalid_arguments")
        self.definition_available = ("actions" in fixture["scope"]["features"] and self.definition is not None and
            self.definition["id"] in fixture["scope"]["action_ids"] and
            C.codec.digest("action-definition", self.definition) == fixture["scope"]["approved_action_digests"].get(self.definition["id"]))
        self.receipts = {}
        self.deadline = None
        self.read_until = fixture["scope"]["expires_at"] + fixture["scope"]["result_retention_ms"]
        self.read_revoked = False
        self.revision = 0
        self.decisions = deepcopy(decisions or {})
        self.confirmations = {}
        self.control_receipts = {}
        self.accepted = None
        self.wire_ticket = None
        self.committed_fact = None
        self.authority.credentials["player-fixture"] = {"role": "player", "principal": deepcopy(fixture["player"])}
        for worker in ("worker-1", "worker-2"):
            self.authority.credentials[worker + "-fixture"] = {
                "role": "executor", "worker": worker,
                "principal": {"issuer": "fixture-enrollment", "subject": worker, "kind": "service"}}

    def _scope(self):
        return self.authority.state["session"]["scope"]

    def checkpoint(self):
        """仅供无外部效果的上层协议事务回滚；不能用它撤销 WorldGate 副作用。"""
        return self.model.recover_copy(), deepcopy({key: getattr(self, key) for key in self.STATE_FIELDS})

    def restore(self, checkpoint):
        self.model, values = checkpoint
        for key, value in values.items():
            setattr(self, key, value)

    def _write(self, identity, now):
        R.validate_session_write(self.authority.state["session"], self.authority.state["grant"], now=now,
                                 **{k: v for k, v in identity.items() if k != "role"})

    def _result(self, model=None, revision=None, fact=None):
        a = (model or self.model).action
        R.require(a is not None, "not_found")
        result = {"session_id": self.authority.state["session"]["session_id"], "request_id": a["id"],
                  "state": a["state"], "effect": a["effect"],
                  "result_revision": self.revision if revision is None else revision, "query_until": self.read_until}
        known = self.committed_fact if fact is None else fact
        if known is not None and "result" in known:
            result["known_result"] = deepcopy(known["result"])
        return result

    def submit(self, raw, credential, *, now, fault=None):
        if fault not in (None, "before_commit", "after_commit"):
            raise ValueError("invalid_fault")
        request = C.validate_request(raw)
        op = request["operation"]
        R.require(op in {"action.request", "action.cancel", "action.query", "action.confirm",
                         "action.claim", "action.commit_result"}, "unsupported_operation")
        with self.lock:
            identity = self.authority.credentials.get(credential)
            R.require(identity is not None, "unauthenticated")
            session = self.authority.state["session"]
            scope = session["scope"]
            R.require(request["version"] == scope["version"], "unsupported_version")
            C.authorize_route(op, identity["role"], C.catalog.OPERATIONS[op]["lane"], scope["features"])
            payload = request["payload"]
            if op in {"action.confirm", "action.claim", "action.commit_result"}:
                return self._control(raw, request, identity, now, fault)
            R.require(payload["session_id"] == session["session_id"], "permission_denied")
            if op == "action.query":
                R.require(not self.read_revoked and identity["principal"] == scope["agent"], "permission_denied")
                R.require(now <= self.read_until, "result_expired")
                result = self._result()
                R.require(payload["action_id"] == result["request_id"], "permission_denied")
                self._authorize_result_reader(identity["principal"])
                R.require(not request["extensions"], "feature_unsupported")
            else:
                self._write(identity, now)
                R.require(payload["sender"] == identity["principal"], "permission_denied")
                R.require(len(raw) <= scope["limits"]["message_bytes"], "resource_limit")
                key = payload["id"]
                digest = C.codec.digest("message", payload)
                if key in self.receipts:
                    old = self.receipts[key]
                    R.require(old["record_digest"] == digest, "id_conflict")
                    result = {**old, "duplicate": True}
                else:
                    R.require(len(self.receipts) < (65 if op == "action.cancel" else 64), "resource_limit")
                    _, activated = C.validate_active_request(raw, selected_extensions=scope["extensions"], supported_extensions=H.EXT.SUPPORTED)
                    H.EXT.enforce(C, activated, op, payload)
                    if op != "action.cancel" or payload["extensions"]:
                        H.EXT.enforce(C, scope["effective_policy"]["extensions"], op, payload)
                    R.validate_envelope_audience(payload, session, authenticated_sender=identity["principal"], current_members=self.authority.members)
                    R.require(R.principal_set(payload["audience"]) <= R.principal_set([scope["agent"], scope["player"]]), "permission_denied")
                    staged = self.model.recover_copy()
                    confirmation_id = None
                    accepted = self.accepted
                    try:
                        if op == "action.request":
                            body = payload["payload"]
                            R.require(self.definition_available, "stale_capabilities")
                            R.require(payload["expected_capabilities_revision"] == session["capabilities_revision"], "stale_capabilities")
                            R.require(body["action"] == self.definition["id"] and body["action"] in scope["action_ids"], "permission_denied")
                            R.require(C.codec.digest("action-definition", self.definition) == scope["approved_action_digests"][body["action"]], "approval_stale")
                            R.require(identity["principal"] in self.definition["allowed_actors"], "permission_denied")
                            C.validate_action_value(self.definition["parameters"], body["arguments"])
                            if self.definition["requires_per_action_consent"]:
                                confirmation_id = body.get("confirmation")
                                confirmation = self.confirmations.get(confirmation_id)
                                R.require(confirmation is not None and not confirmation["consumed"], "action_consent_required")
                                binding = confirmation["payload"]
                                R.require(binding["action_request_id"] == key and binding["session_id"] == session["session_id"]
                                          and binding["action"] == body["action"]
                                          and binding["arguments_digest"] == C.codec.digest("action-arguments", body["arguments"])
                                          and binding["definition_digest"] == C.codec.digest("action-definition", self.definition)
                                          and now < binding["expires_at"], "action_consent_required")
                            deadline = min(body["deadline"], now + self.definition["maximum_duration_ms"],
                                           session["lease_deadline"], self.authority.state["grant"]["expires_at"])
                            R.require(now < deadline, "request_expired")
                            R.require(R.principal_set([scope["agent"], scope["player"]]) <= self.authority.members.keys(), "permission_denied")
                            staged.accept(key, body["arguments"])
                            accepted = {"definition": deepcopy(self.definition), "generation": session["control_generation"],
                                        "instance_epoch": session["instance_epoch"],
                                        "transport_epoch": session["transport_epoch"],
                                        "origin_members": {R.principal_key(p): self.authority.members[R.principal_key(p)]
                                                           for p in (scope["agent"], scope["player"])}}
                        else:
                            R.require(staged.action is not None and payload["payload"]["request_id"] == staged.action["id"], "permission_denied")
                            staged.stop()
                            deadline = self.deadline
                    except M.Rejected as error:
                        raise C.ContractError(error.code) from None
                    result = {"id": key, "accepted_at": now, "record_digest": digest, "duplicate": False}
                    reply = {"request_id": request["request_id"], "result": result}
                    C.validate_reply(op, request["request_id"], reply)
                    encoded = C.codec.canonical(reply)
                    self._fault(fault, "before_commit")
                    self.model, self.deadline = staged, deadline
                    self.accepted = accepted
                    if confirmation_id is not None:
                        self.confirmations[confirmation_id]["consumed"] = True
                    self.receipts[key] = deepcopy(result)
                    self.revision += 1
                    session["lease_deadline"] = min(now + scope["limits"]["lease_period_ms"], self.authority.state["grant"]["expires_at"])
                    self._fault(fault, "after_commit")
                    return encoded
            reply = {"request_id": request["request_id"], "result": result}
            C.validate_reply(op, request["request_id"], reply)
            return C.codec.canonical(reply)

    @staticmethod
    def _fault(fault, point):
        if fault == point:
            raise H.InjectedFailure(point)

    def _active_session(self, now):
        """执行权来自会话权威，不依赖伙伴当前 transport 凭据是否仍在线。"""
        session = self.authority.state["session"]
        R.validate_session_write(session, self.authority.state["grant"], now=now,
                                 principal=self._scope()["agent"], generation=session["control_generation"],
                                 transport_epoch=session["transport_epoch"], device_id=session.get("controller_device"))

    def _execution_gate(self, now):
        self._active_session(now)
        R.require(self.definition_available, "stale_capabilities")
        session = self.authority.state["session"]
        R.require(self.accepted is not None, "permission_denied")
        R.require(session["control_generation"] == self.accepted["generation"]
                  and session["instance_epoch"] == self.accepted["instance_epoch"], "stale_controller")
        R.require(session["transport_epoch"] == self.accepted["transport_epoch"], "stale_transport")
        R.require(self.deadline is not None and now < self.deadline, "request_expired")
        digest = C.codec.digest("action-definition", self.definition)
        R.require(digest == C.codec.digest("action-definition", self.accepted["definition"])
                  and digest == self._scope()["approved_action_digests"].get(self.definition["id"]), "stale_capabilities")

    def _control(self, raw, request, identity, now, fault):
        op, payload = request["operation"], request["payload"]
        session, scope = self.authority.state["session"], self._scope()
        sid = payload["ticket"]["session_id"] if op == "action.commit_result" else payload["session_id"]
        R.require(sid == session["session_id"], "permission_denied")
        R.require(len(raw) <= scope["limits"]["message_bytes"], "resource_limit")
        R.require(now <= self.read_until, "result_expired")
        if op == "action.confirm":
            R.require(identity["principal"] == scope["player"], "permission_denied")
        elif op == "action.claim":
            R.require(payload["worker"] == identity["principal"] and identity.get("worker") in {"worker-1", "worker-2"}, "permission_denied")
            R.require(self.model.action is not None and payload["action_id"] == self.model.action["id"], "permission_denied")
        else:
            self._verify_ticket(payload["ticket"], identity.get("worker"))
        # 固定单会话/端点实例；主体、操作及 request_id 构成控制去重键。
        key = (R.principal_key(identity["principal"]), op, request["request_id"])
        digest = C.codec.digest("control", {k: request[k] for k in ("version", "operation", "payload", "extensions")})
        old = self.control_receipts.get(key)
        if old is not None:
            R.require(old["digest"] == digest, "id_conflict")
            return self._encode(request, old["result"])
        R.require(len(self.control_receipts) < (65 if op == "action.commit_result" else 64), "resource_limit")
        _, active = C.validate_active_request(raw, selected_extensions=scope["extensions"], supported_extensions=H.EXT.SUPPORTED)
        H.EXT.enforce(C, active, op, payload)
        H.EXT.enforce(C, scope["effective_policy"]["extensions"], op, payload)
        staged = self.model.recover_copy()
        confirmations, ticket = deepcopy(self.confirmations), deepcopy(self.wire_ticket)
        fact, revision = deepcopy(self.committed_fact), self.revision
        if op == "action.confirm":
            self._active_session(now)
            R.require(payload["action"] == self.definition["id"] and payload["action"] in scope["action_ids"]
                      and self.definition["requires_per_action_consent"], "permission_denied")
            R.require(payload["definition_digest"] == C.codec.digest("action-definition", self.definition)
                      == scope["approved_action_digests"].get(payload["action"]), "approval_stale")
            R.require(now < payload["expires_at"] <= min(session["lease_deadline"], self.authority.state["grant"]["expires_at"]), "request_expired")
            evidence = self.decisions.get(payload["decision_ref"])
            R.require(evidence is not None and evidence.get("allow") is True and evidence.get("player") == identity["principal"]
                      and evidence.get("payload") == payload, "action_consent_required")
            # 相同真实交互不能因换 transport request_id 再签发一次许可。
            confirmation_id = next((cid for cid, value in confirmations.items() if value["payload"] == payload), None)
            if confirmation_id is None:
                R.require(len(confirmations) < 64, "resource_limit")
                confirmation_id = "fixture-confirm-" + str(len(confirmations) + 1)
                confirmations[confirmation_id] = {"payload": deepcopy(payload), "consumed": False}
            result = {"confirmation_id": confirmation_id, "expires_at": payload["expires_at"]}
        elif op == "action.claim":
            if staged.action["state"] == "pending":
                try:
                    self._execution_gate(now)
                except C.ContractError as error:
                    if error.code not in {"grant_revoked", "session_closed", "session_not_writable", "stale_controller", "stale_transport", "request_expired", "stale_capabilities"}:
                        raise
                    staged.stop()
                if staged.action["state"] == "pending":
                    staged.claim(identity["worker"])
                    ticket = {"ticket_id": "fixture-ticket-1", "session_id": session["session_id"],
                              "request_id": staged.action["id"], "worker": deepcopy(identity["principal"]),
                              "generation": self.accepted["generation"], "fence": 1,
                              "deadline": self.deadline, "proof_ref": "fixture-execution-1"}
                revision += 1
            result = ({"status": "claimed", "ticket": ticket, "arguments": deepcopy(staged.action["arguments"])}
                      if self.model.action["state"] == "pending" and ticket is not None
                      else {"status": "not_executable", "action": self._result(staged, revision)})
        else:
            submitted = payload["fact"]
            if fact is not None and fact["state"] != "unknown":
                R.require(C.codec.canonical(submitted) == C.codec.canonical(fact), "execution_conflict")
            else:
                try:
                    staged.finish(identity["worker"], staged.action["ticket"])
                except M.Rejected:
                    raise C.ContractError("execution_conflict") from None
                verified = self._verified_fact(staged)
                R.require(C.codec.canonical(submitted) == C.codec.canonical(verified), "execution_conflict")
                if "result" in submitted:
                    C.validate_action_value(self.accepted["definition"]["result_schema"], submitted["result"])
                R.require(submitted["state"] != "succeeded" or "result" in submitted, "invalid_arguments")
                if fact != submitted or staged.action != self.model.action:
                    revision += 1
                fact = deepcopy(submitted)
            result = self._result(staged, revision, fact)
        encoded = self._encode(request, result)
        self._fault(fault, "before_commit")
        self.model, self.confirmations, self.wire_ticket = staged, confirmations, ticket
        self.committed_fact, self.revision = fact, revision
        self.control_receipts[key] = {"digest": digest, "result": deepcopy(result)}
        self._fault(fault, "after_commit")
        return encoded

    @staticmethod
    def _encode(request, result):
        reply = {"request_id": request["request_id"], "result": result}
        C.validate_reply(request["operation"], request["request_id"], reply)
        return C.codec.canonical(reply)

    def _authorize_result_reader(self, principal):
        """两个结果读取入口共用成员代次与撤权屏障；关闭会话不等于撤销结果读权。"""
        action, scope = self.model.action, self._scope()
        R.require(principal == scope["agent"] and not self.read_revoked and
                  action is not None and self.accepted is not None and
                  (R.principal_key(principal), action["id"]) not in self.authority.state.get("result_read_revoked", set()) and
                  R.can_deliver(principal, self.accepted["origin_members"], self.authority.members, scope["audiences"]),
                  "permission_denied")

    def operation_view(self, payload, identity, *, now):
        """可信控制查询的原主体投影；message 按 Envelope.id，不把传输 ID 变成业务键。"""
        op, rid = payload["operation"], payload["original_request_id"]
        scope = self._scope()
        if op == "action.confirm":
            R.require(identity["role"] == "player" and identity["principal"] == scope["player"], "permission_denied")
            key = (R.principal_key(identity["principal"]), op, rid)
            record = self.control_receipts.get(key)
            R.require(record is not None and now <= self.read_until, "permission_denied")
            return {"operation": op, "request_id": rid, "state": "done", "outcome_ref": record["result"]["confirmation_id"]}
        R.require(op in {"action.request", "action.cancel"} and identity["role"] == "agent" and
                  identity["principal"] == scope["agent"], "permission_denied")
        action = self.model.action
        receipt = self.receipts.get(rid)
        R.require(action is not None and receipt is not None and
                  (rid == action["id"]) == (op == "action.request"), "permission_denied")
        # ID、受理收据及正文同样受读权保护；重新入队/续租/结果对账均不在读取路径执行。
        R.require(now <= self.read_until, "permission_denied")
        self._authorize_result_reader(identity["principal"])
        return {"operation": op, "request_id": rid, "state": "done", "outcome_ref": action["id"],
                "receipt": deepcopy(receipt), "action": self._result()}

    def _verify_ticket(self, ticket, worker):
        R.require(self.wire_ticket is not None and ticket == self.wire_ticket and worker in {"worker-1", "worker-2"}
                  and self.model.action["ticket"][1] == worker, "permission_denied")

    def _verified_fact(self, model):
        """仅从已保存的可信效果账本生成报告期望值，不接收请求方自造 evidence。"""
        a = model.action
        steps = []
        for number, value in sorted(a["journal"].items()):
            R.require(model.world.get((a["ticket"], number)) == value, "execution_conflict")
            steps.append({"step": number, "effect": value["effect"],
                          "evidence_ref": self.wire_ticket["proof_ref"] + "-step-" + str(number)})
        if a.get("denial") is not None:
            steps.append({"step": a["denial"], "effect": "none",
                          "evidence_ref": self.wire_ticket["proof_ref"] + "-denied-" + str(a["denial"])})
        fact = {"state": a["state"], "effect": a["effect"], "steps": steps}
        if a["state"] == "succeeded":
            fact["result"] = deepcopy(a["journal"][model.steps]["result"])
        return fact

    def execute(self, operation, worker, *, now, ticket=None, step=None, crash=None):
        """受信 WorldGate 夹具。wire ticket 仍须匹配已登记 worker；从不从请求自报事实执行。"""
        with self.lock:
            R.require(operation in {"claim", "step", "deny", "reconcile", "finish"}, "unsupported_operation")
            if isinstance(ticket, dict):
                self._verify_ticket(ticket, worker)
                ticket = self.model.action["ticket"]
            cached = operation == "step" and self.model.action is not None and step in self.model.action["journal"]
            if operation in {"claim", "step", "deny"} and not cached:
                self._execution_gate(now)
            before = deepcopy(self.model.action)
            try:
                if operation == "claim":
                    return self.model.claim(worker)
                if operation == "step":
                    return self.model.step(worker, ticket, step, crash=crash)
                if operation == "deny":
                    return self.model.deny_step(worker, ticket, step)
                if operation == "reconcile":
                    return self.model.reconcile(worker, ticket)
                return self.model.finish(worker, ticket)
            finally:
                if self.model.action != before:
                    self.revision += 1

    def revoke(self, *, now):
        """已认证管理端口夹具。写权与结果读权分开。"""
        with self.lock:
            self.authority.state["grant"]["state"] = "revoked"
            self.model.stop(revoke=True)
            self.read_until = min(self.read_until, now + self._scope()["result_retention_ms"])
            self.revision += 1
