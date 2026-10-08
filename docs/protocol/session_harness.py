"""动作账本与事件服务的单锁域装配；无网络和磁盘，外部效果绝不随协议事务回滚。"""

from copy import deepcopy
import importlib.util
from pathlib import Path


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


S = load("session_events", "event_server.py")
A = load("session_actions", "action_harness.py")
C, R = S.C, S.R


class SessionHarness(S.EventServer):
    WIRE_OPERATIONS = frozenset({"chat.send", "context.publish", "session.snapshot", "session.events",
        "action.request", "action.cancel", "action.query", "action.confirm", "action.claim", "action.commit_result",
        "session.heartbeat", "session.close", "permission.revoke", "capability.replace", "membership.replace", "player_chat.forward"})

    def __init__(self, fixture, records, *, decisions=None, membership_proofs=None, player_seat_proofs=None):
        super().__init__(fixture, records)
        self.action_model = A.ActionHarness(fixture, decisions=decisions, authority=self)
        self.pending_sync = False
        self.membership_proofs = deepcopy(membership_proofs or {})
        self.player_seat_proofs = deepcopy(player_seat_proofs or {})
        self.state.update(session_controls={}, member_generations=deepcopy(self.members), result_access_revision=1)

    def _transaction(self, operation, fault):
        if fault not in (None, "before_commit", "after_commit"):
            raise ValueError("invalid_fault")
        with self.lock:
            original, members, pending = self.state, deepcopy(self.members), self.pending_sync
            checkpoint = self.action_model.checkpoint()
            self.state = deepcopy(original)
            try:
                result = operation()
                if fault == "before_commit":
                    raise S.H.InjectedFailure(fault)
            except BaseException:
                self.state, self.members, self.pending_sync = original, members, pending
                self.action_model.restore(checkpoint)
                raise
            if fault == "after_commit":
                raise S.H.InjectedFailure(fault)
            return result

    def _sync_action(self, now, *, fault=None):
        action = self.action_model
        if action.model.action is not None:
            reason = "cancel_requested" if action.model.action["stopped"] and action.model.action["state"] == "executing" else None
            self.record_verified_action_result(action._result(), origin_members=action.accepted["origin_members"], now=now, fault=fault, reason=reason)
            if action.read_revoked:
                self.state["result_read_revoked"].add((R.principal_key(self.state["session"]["scope"]["agent"]), action.model.action["id"]))
        self.pending_sync = False

    def submit(self, raw, credential, *, now, fault=None):
        request = C.validate_request(raw)
        R.require(request["operation"] in self.WIRE_OPERATIONS, "unsupported_operation")
        def apply():
            if request["operation"] in {"session.close", "permission.revoke", "action.cancel", "action.commit_result"}:
                self._reserve_stop()
            if self.pending_sync:
                self._sync_action(now)
            if request["operation"] == "player_chat.forward":
                return self._player_chat(raw, request, credential, now)
            if request["operation"] in {"session.heartbeat", "session.close", "permission.revoke", "capability.replace", "membership.replace"}:
                return self._session_control(raw, request, credential, now)
            if not request["operation"].startswith("action."):
                return super(SessionHarness, self).submit(raw, credential, now=now)
            before = self.action_model.revision
            try:
                encoded = self.action_model.submit(raw, credential, now=now)
            except A.C.ContractError as error:
                raise C.ContractError(error.code) from None
            if request["operation"] in {"action.request", "action.cancel"}:
                envelope = request["payload"]
                key = (envelope["session_id"], R.principal_key(envelope["sender"]), envelope["id"])
                digest = C.codec.digest("message", envelope)
                old = self.state["receipts"].get(key)
                R.require(old is None or old["record_digest"] == digest, "id_conflict")
                limit = 257 if request["operation"] == "action.cancel" else 256
                R.require(old is not None or len(self.state["receipts"]) < limit, "resource_limit")
                self.state["receipts"][key] = deepcopy(C.codec.decode(encoded)["result"])
            if self.action_model.revision != before:
                self._sync_action(now)
            return encoded
        return self._transaction(apply, fault)

    def _player_seat(self, proof_ref, sender, now):
        """每次调用（含重复消息）重验当前席位；该表只能由可信夹具端口登记。"""
        record = deepcopy(self.player_seat_proofs.get(proof_ref))
        try:
            C.validate_type("PlayerSeatAuthorization", record)
        except (C.ContractError, C.codec.CodecError):
            raise C.ContractError("permission_denied") from None
        session, scope = self.state["session"], self.state["session"]["scope"]
        R.require(record["proof_ref"] == proof_ref and record["instance"] == scope["instance"] and
                  record["session_id"] == session["session_id"] and
                  record["scope_digest"] == self.state["grant"]["scope_digest"], "permission_denied")
        R.require(record["game"] == scope["instance"]["game"] and record["player"] == sender and
                  sender["kind"] == "player", "permission_denied")
        R.require(record["state"] == "active" and record["issued_at"] <= now < record["expires_at"], "permission_denied")
        R.require(record["membership_revision"] == session["membership_revision"] and
                  record["membership_generation"] == self.members.get(R.principal_key(sender)) and
                  R.principal_key(sender) in R.principal_set(scope["audiences"]), "permission_denied")

    def _operation_view(self, payload, identity, *, now):
        """供准入控制查询调用的安全投影；复用原账本，不创建索引、收据或执行任务。"""
        op, rid = payload["operation"], payload["original_request_id"]
        if op == "session.events":
            R.require((R.principal_key(identity["principal"]), rid) in self.state["polls"], "permission_denied")
            # 只报告原 poll 已提交；历史正文必须重新走事件过滤，不能由控制查询重放。
            return {"operation": op, "request_id": rid, "state": "done", "outcome_ref": self.state["session"]["session_id"]}
        if op in {"action.request", "action.cancel", "action.confirm"}:
            R.require(not self.pending_sync, "temporarily_unavailable")
            try:
                return self.action_model.operation_view(payload, identity, now=now)
            except A.C.ContractError as error:
                raise C.ContractError(error.code) from None
        R.require(op in {"session.heartbeat", "session.close", "permission.revoke"}, "permission_denied")
        key = (R.principal_key(identity["principal"]), op, rid)
        record = self.state["session_controls"].get(key)
        R.require(record is not None, "permission_denied")
        result = record["result"]
        if op == "permission.revoke":
            return {"operation": op, "request_id": rid, "state": "done", "outcome_ref": result["object_id"],
                    "revocation": deepcopy(result)}
        return {"operation": op, "request_id": rid, "state": "done", "outcome_ref": result["session_id"],
                "session": deepcopy(result)}

    def _player_chat(self, raw, request, credential, now):
        """游戏管理身份与玩家席位分别验证；复用聊天事件/来源/收据，不伪造伙伴身份。"""
        C.validate_type("Nat", now)
        identity = self._identity(credential)
        session, scope = self.state["session"], self.state["session"]["scope"]
        C.authorize_route("player_chat.forward", identity["role"], "management", scope["features"])
        R.require(identity["principal"] == scope["instance"]["game"], "permission_denied")
        R.require(request["version"] == scope["version"], "unsupported_version")
        R.require(len(raw) <= scope["limits"]["message_bytes"], "resource_limit")
        R.validate_session_write(session, self.state["grant"], now=now, principal=scope["agent"],
                                 generation=session["control_generation"], transport_epoch=session["transport_epoch"],
                                 device_id=session.get("controller_device"))
        envelope = request["payload"]["envelope"]
        R.require(envelope["session_id"] == session["session_id"], "permission_denied")
        self._player_seat(request["payload"]["seat_proof_ref"], envelope["sender"], now)
        key = (session["session_id"], R.principal_key(envelope["sender"]), envelope["id"])
        digest = C.codec.digest("message", envelope)
        old = self.state["receipts"].get(key)
        if old is not None:
            R.require(old["record_digest"] == digest, "id_conflict")
            return self._reply(request, result={**old, "duplicate": True})
        R.require(len(self.state["receipts"]) < 256, "resource_limit")
        _, active = C.validate_active_request(raw, selected_extensions=scope["extensions"], supported_extensions=S.H.EXT.SUPPORTED)
        S.H.EXT.enforce(C, active, "player_chat.forward", envelope)
        S.H.EXT.enforce(C, scope["effective_policy"]["extensions"], "player_chat.forward", envelope)
        revisions = S.S.validate_disclosure(envelope, session, self.state["records"], now=now)
        self._append(envelope, now, sources=revisions)
        result = {"id": envelope["id"], "accepted_at": now, "record_digest": digest, "duplicate": False}
        self.state["receipts"][key] = result
        # 管理面代玩家转发不代表伙伴仍存活，不续伙伴 lease，也不消费席位证明。
        return self._reply(request, result=result)

    def execute(self, operation, worker, *, now, ticket=None, step=None, crash=None, publish_fault=None):
        """可信 WorldGate 调用。先预留发布容量；效果后发布失败只阻塞读取，绝不回滚世界。"""
        with self.lock:
            if operation in {"finish", "reconcile"}:
                self._reserve_stop()
            if self.pending_sync:
                self._sync_action(now)
            action = self.action_model.model.action
            cached = operation == "step" and action is not None and step in action["journal"]
            terminal = operation == "finish" and action is not None and action["terminal"] is not None
            if not cached and not terminal:
                R.require(len(self.state["events"]) < 64 and len(self.state["result_events"]) < 256, "resource_limit")
            before = self.action_model.revision
            try:
                result = self.action_model.execute(operation, worker, now=now, ticket=ticket, step=step, crash=crash)
            except A.M.SimulatedCrash:
                self.pending_sync = True
                self._sync_action(now)
                raise
            except A.C.ContractError as error:
                raise C.ContractError(error.code) from None
            if self.action_model.revision != before:
                self.pending_sync = True
                self._sync_action(now, fault=publish_fault)
            return result

    def revoke(self, *, now, fault=None):
        def apply():
            self._reserve_stop()
            self.action_model.revoke(now=now)
            self._sync_action(now)
        return self._transaction(apply, fault)

    def _reserve_stop(self):
        """为取消/关闭保留空间：裁剪事件历史而不丢弃业务结果和消息拒重记录。"""
        count = max(0, len(self.state["events"]) + 2 - 64)
        if count:
            self.compact_through(self.state["events"][count - 1]["wire"]["sequence"])
        if len(self.state["result_events"]) >= 256:
            latest = {}
            for key, value in self.state["result_events"].items():
                if key[0] not in latest or key[1] > latest[key[0]][0][1]:
                    latest[key[0]] = (key, value)
            self.state["result_events"] = dict(latest.values())

    def _notice(self, kind, payload, now):
        session, scope = self.state["session"], self.state["session"]["scope"]
        audience = [p for p in scope["audiences"] if R.principal_key(p) in self.members]
        if not audience:
            return
        if "session" in payload:
            payload = {"session": deepcopy(payload["session"])}
            payload["session"]["sequence"] = session["sequence"] + 1
        self._append({"version": scope["version"], "session_id": session["session_id"],
                      "id": "server-control-" + str(session["sequence"] + 1), "type": kind,
                      "sender": scope["instance"]["game"], "audience": audience,
                      "payload": payload, "extensions": {}}, now)

    def _stop_action(self, now):
        before = deepcopy(self.action_model.model.action)
        self.action_model.model.stop()
        if before != self.action_model.model.action:
            self.action_model.revision += 1
            self._sync_action(now)

    def _close(self, reason, now):
        session = self.state["session"]
        if session["state"] == "closed":
            return
        self._reserve_stop()
        session.update(state="closed", ready=False, close_reason=reason)
        self.action_model.revoke(now=now)
        self._sync_action(now)
        self._notice("session.closed", {"session": self.state["session"]}, now)

    def _session_control(self, raw, request, credential, now):
        identity = self._identity(credential)
        op, payload = request["operation"], request["payload"]
        session, scope = self.state["session"], self.state["session"]["scope"]
        lane = "management" if identity["role"] == "game" else C.catalog.OPERATIONS[op]["lane"]
        C.authorize_route(op, identity["role"], lane, scope["features"])
        expected = scope["instance"]["game"] if identity["role"] == "game" else scope["player"] if identity["role"] == "player" else scope["agent"]
        R.require(identity["principal"] == expected, "permission_denied")
        R.require(request["version"] == scope["version"], "unsupported_version")
        R.require(len(raw) <= scope["limits"]["message_bytes"], "resource_limit")
        if "session_id" in payload:
            R.require(payload["session_id"] == session["session_id"], "permission_denied")
        if "instance" in payload:
            R.require(payload["instance"] == scope["instance"], "permission_denied")
        key = (R.principal_key(identity["principal"]), op, request["request_id"])
        digest = C.codec.digest("control", {k: request[k] for k in ("version", "operation", "payload", "extensions")})
        old = self.state["session_controls"].get(key)
        if op == "session.heartbeat":
            self._current_reader(identity, now)
        if old is not None:
            R.require(old["digest"] == digest, "id_conflict")
            return self._reply(request, result=old["result"])
        stop = op in {"session.close", "permission.revoke"}
        R.require(len(self.state["session_controls"]) < (256 if stop else 128), "resource_limit")
        _, active = C.validate_active_request(raw, selected_extensions=scope["extensions"], supported_extensions=S.H.EXT.SUPPORTED)
        S.H.EXT.enforce(C, active, op, payload)
        if not stop or request["extensions"]:
            S.H.EXT.enforce(C, scope["effective_policy"]["extensions"], op, payload)
        if op == "session.heartbeat":
            session["lease_deadline"] = min(now + scope["limits"]["lease_period_ms"], self.state["grant"]["expires_at"])
            result = deepcopy(session)
        elif op == "session.close":
            if identity["role"] == "companion_control" and session["state"] != "closed":
                self._current_reader(identity, now)
            self._close(payload["reason"], now)
            result = deepcopy(self.state["session"])
        elif op == "permission.revoke":
            target, oid = payload["object_type"], payload["object_id"]
            R.require(target in {"grant", "session", "result_read"}, "unsupported_operation")
            revision = self.state["result_access_revision"] if target == "result_read" else self.state["grant"]["revision"]
            target_id = self.state["grant"]["grant_id"] if target == "grant" else session["session_id"]
            R.require(oid == target_id, "permission_denied")
            R.require(payload["expected_revision"] == revision, "generation_conflict")
            if target == "result_read":
                self.action_model.read_revoked = True
                for action_id in self.state["actions"]:
                    self.state["result_read_revoked"].add((R.principal_key(scope["agent"]), action_id))
                self.state["result_access_revision"] += 1
            else:
                self._close("revoked", now)
                self.state["grant"]["revision"] += 1
            result = {"object_type": target, "object_id": oid, "revision": revision + 1,
                      "state": "closed" if target == "session" else "revoked"}
        else:
            R.require(session["state"] == "active", "session_closed")
            revision_key = "capabilities_revision" if op == "capability.replace" else "membership_revision"
            R.require(payload["expected_revision"] == session[revision_key], "generation_conflict")
            session[revision_key] += 1
            if op == "capability.replace":
                effective = [d for d in payload["definitions"] if d["id"] in scope["action_ids"] and
                             C.codec.digest("action-definition", d) == scope["approved_action_digests"].get(d["id"])]
                self.state["definitions"] = deepcopy(effective)
                self.action_model.definition_available = any(d["id"] == self.action_model.definition["id"] for d in effective)
                if not self.action_model.definition_available:
                    self._stop_action(now)
                self._notice("capability.update", {"revision": self.state["session"][revision_key], "definitions": effective}, now)
            else:
                R.require(self.membership_proofs.get(payload["membership_proof_ref"]) == payload, "permission_denied")
                new_keys = R.principal_set(payload["verified_members"])
                if "team" not in scope["features"]:
                    R.require(new_keys <= R.principal_set([scope["agent"], scope["player"]]), "feature_unsupported")
                new_members = {}
                for member in new_keys:
                    if member in self.members:
                        new_members[member] = self.members[member]
                    else:
                        new_members[member] = self.state["member_generations"].get(member, 0) + 1
                        self.state["member_generations"][member] = new_members[member]
                self.members = new_members
                if not R.principal_set([scope["agent"], scope["player"]]) <= new_keys:
                    self._stop_action(now)
                visible = [p for p in scope["audiences"] if R.principal_key(p) in new_keys]
                self._notice("membership.update", {"revision": self.state["session"][revision_key], "members": visible}, now)
            result = {"revision": self.state["session"][revision_key]}
        encoded = self._reply(request, result=result)
        self.state["session_controls"][key] = {"digest": digest, "result": deepcopy(result)}
        return encoded

    def compact_closed_receipts(self, *, now, max_items=64, fault=None):
        """可信维护端口：仅清理关闭会话的过期消息回执，保留终态和世界效果；不删除文件。"""
        C.validate_type("Nat", now)
        R.require(type(max_items) is int and 1 <= max_items <= 64, "invalid_arguments")

        def compact():
            session, grant = self.state["session"], self.state["grant"]
            R.require(session["state"] == "closed" and grant["state"] == "revoked", "invalid_arguments")
            R.require(not self.pending_sync, "temporarily_unavailable")
            R.require(now >= self.state.get("receipt_compaction_now", 0), "invalid_arguments")
            retention = session["scope"]["limits"]["receipt_retention_ms"]
            actor = R.principal_key(session["scope"]["agent"])
            removed = 0
            for key, receipt in sorted(self.state["receipts"].items()):
                if removed == max_items:
                    break
                if now <= receipt["accepted_at"] + retention:
                    continue
                action_receipt = (key[:2] == (session["session_id"], actor) and
                                  key[2] in self.action_model.receipts)
                if action_receipt and now <= self.action_model.read_until:
                    continue
                if action_receipt:
                    del self.action_model.receipts[key[2]]
                del self.state["receipts"][key]
                removed += 1
            self.state["receipt_compaction_now"] = now
            return {"removed": removed, "remaining": len(self.state["receipts"])}

        return self._transaction(compact, fault)

    def revoke_result_read(self, principal, action_id):
        with self.lock:
            super().revoke_result_read(principal, action_id)
            if principal == self.state["session"]["scope"]["agent"] and self.action_model.model.action is not None and action_id == self.action_model.model.action["id"]:
                self.action_model.read_revoked = True
