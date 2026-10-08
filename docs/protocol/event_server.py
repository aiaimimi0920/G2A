"""固定会话的事件服务模型：同一内存锁域捕获状态、outbox、权限和恢复快照。

不启动网络，不提供持久事务。动作结果生产端口只接收外部已经验证的事实，不能代替 WorldGate。
"""

from copy import deepcopy
import importlib.util
from pathlib import Path


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


H = load("event_server_chat", "chat_harness.py")
E = load("event_server_consumer", "event_consumer.py")
C, R, S = H.C, H.R, H.S


class EventServer(H.ChatHarness):
    def __init__(self, fixture, records, *, scan_budget=64):
        super().__init__(fixture, records)
        R.require(type(scan_budget) is int and 1 <= scan_budget <= 256, "invalid_arguments")
        self.scan_budget = scan_budget
        definition, scope = fixture.get("action"), fixture["scope"]
        R.require(("actions" not in scope["features"] and not scope["action_ids"]) or
                  definition is not None, "invalid_arguments")
        enabled = ("actions" in scope["features"] and definition is not None and
                   definition["id"] in scope["action_ids"] and
                   C.codec.digest("action-definition", definition) == scope["approved_action_digests"].get(definition["id"]))
        self.state.update(contexts={}, actions={}, result_events={}, result_read_revoked=set(),
                          polls={}, event_floor=0, definitions=[deepcopy(definition)] if enabled else [])
        self.credentials["game-fixture"] = {"principal": deepcopy(fixture["game"]), "role": "game"}

    def _transaction(self, operation, fault):
        if fault not in (None, "before_commit", "after_commit"):
            raise ValueError("invalid_fault")
        with self.lock:
            original = self.state
            self.state = deepcopy(original)
            try:
                result = operation()
                if fault == "before_commit":
                    raise H.InjectedFailure(fault)
            except BaseException:
                self.state = original
                raise
            if fault == "after_commit":
                raise H.InjectedFailure(fault)
            return result

    def _identity(self, credential):
        identity = self.credentials.get(credential)
        R.require(identity is not None, "unauthenticated")
        return identity

    def _current_reader(self, identity, now):
        R.validate_session_write(self.state["session"], self.state["grant"], now=now,
                                 **{key: value for key, value in identity.items() if key != "role"})
        R.require(R.principal_key(identity["principal"]) in self.members, "permission_denied")

    def _reply(self, request, **body):
        reply = {"request_id": request["request_id"], **body}
        C.validate_reply(request["operation"], request["request_id"], reply)
        return C.codec.canonical(reply)

    def _append(self, envelope, now, *, sources=None, origin_members=None):
        R.require(len(self.state["events"]) < 64, "resource_limit")
        session = self.state["session"]
        frozen = R.validate_envelope_audience(envelope, session, authenticated_sender=envelope["sender"],
                                             current_members=self.members if origin_members is None else origin_members)
        sequence = session["sequence"] + 1
        event = {"sequence": sequence, "created_at": now, "envelope": deepcopy(envelope)}
        C.validate_type("Event", event)
        item = {"wire": event, "members": frozen, "sources": deepcopy(sources or {})}
        self.state["events"].append(item)
        session["sequence"] = sequence
        return item

    def _visible(self, item, principal, now):
        session = self.state["session"]
        if not R.can_deliver(principal, item["members"], self.members, session["scope"]["audiences"]):
            return False
        envelope = item["wire"]["envelope"]
        if envelope["type"] in {"chat.message", "game.context"}:
            return S.disclosure_still_allowed(envelope, session, self.state["records"], item["sources"], now=now)
        if envelope["type"] == "action.state":
            action = envelope["payload"]["action"]
            return (now <= action["query_until"] and
                    (R.principal_key(principal), action["request_id"]) not in self.state["result_read_revoked"])
        return True

    def _snapshot(self, principal, now):
        # 所有读取发生在持有同一锁的事务内，不在得到 cursor 后另读业务数据。
        session = deepcopy(self.state["session"])
        cursor = {"session_id": session["session_id"], "instance_epoch": session["instance_epoch"], "sequence": session["sequence"]}
        result = {"snapshot_version": "g2a-recovery-1", "session": session, "cursor": cursor,
                  "actions": [deepcopy(item["wire"]["envelope"]["payload"]["action"]) for item in self.state["actions"].values()
                              if self._visible(item, principal, now) and now <= item["wire"]["envelope"]["payload"]["action"]["query_until"]],
                  "contexts": [deepcopy(item["wire"]["envelope"]) for item in self.state["contexts"].values() if self._visible(item, principal, now)],
                  "definitions": deepcopy(self.state["definitions"]),
                  "members": [deepcopy(p) for p in session["scope"]["audiences"] if R.principal_key(p) in self.members]}
        C.validate_type("RecoverySnapshot", result)
        return result

    def submit(self, raw, credential, *, now, fault=None):
        request = C.validate_request(raw)
        op = request["operation"]
        R.require(op in {"chat.send", "context.publish", "session.snapshot", "session.events"}, "unsupported_operation")
        def apply():
            identity = self._identity(credential)
            session, scope = self.state["session"], self.state["session"]["scope"]
            R.require(request["version"] == scope["version"], "unsupported_version")
            C.authorize_route(op, identity["role"], C.catalog.OPERATIONS[op]["lane"], scope["features"])
            R.require(request["payload"]["session_id"] == session["session_id"], "permission_denied")
            R.require(len(raw) <= scope["limits"]["message_bytes"], "resource_limit")
            if op == "chat.send":
                key = (session["session_id"], R.principal_key(identity["principal"]), request["payload"]["id"])
                R.require(key in self.state["receipts"] or len(self.state["receipts"]) < 256, "resource_limit")
                return super(EventServer, self).submit(raw, credential, now=now)
            if op == "context.publish":
                return self._context(raw, request, identity, now)
            self._current_reader(identity, now)
            _, active = C.validate_active_request(raw, selected_extensions=scope["extensions"], supported_extensions=H.EXT.SUPPORTED)
            H.EXT.enforce(C, active, op, request["payload"])
            if op == "session.snapshot":
                return self._reply(request, result=self._snapshot(identity["principal"], now))
            return self._poll(request, identity, now)
        return self._transaction(apply, fault)

    def _context(self, raw, request, identity, now):
        session, scope = self.state["session"], self.state["session"]["scope"]
        R.require(identity["principal"] == scope["instance"]["game"], "permission_denied")
        R.validate_session_write(session, self.state["grant"], now=now, principal=scope["agent"],
                                 generation=session["control_generation"], transport_epoch=session["transport_epoch"],
                                 device_id=session.get("controller_device"))
        envelope = request["payload"]
        R.require(envelope["sender"] == identity["principal"], "permission_denied")
        key = (session["session_id"], R.principal_key(identity["principal"]), envelope["id"])
        digest = C.codec.digest("message", envelope)
        old = self.state["receipts"].get(key)
        if old is not None:
            R.require(old["record_digest"] == digest, "id_conflict")
            return self._reply(request, result={**old, "duplicate": True})
        R.require(len(self.state["receipts"]) < 256, "resource_limit")
        _, active = C.validate_active_request(raw, selected_extensions=scope["extensions"], supported_extensions=H.EXT.SUPPORTED)
        H.EXT.enforce(C, active, "context.publish", envelope)
        H.EXT.enforce(C, scope["effective_policy"]["extensions"], "context.publish", envelope)
        category = envelope["payload"]["category"]
        R.require(category in scope["context_categories"], "permission_denied")
        sources = S.validate_disclosure(envelope, session, self.state["records"], now=now)
        item = self._append(envelope, now, sources=sources)
        self.state["contexts"][category] = item
        result = {"id": envelope["id"], "accepted_at": now, "record_digest": digest, "duplicate": False}
        self.state["receipts"][key] = result
        return self._reply(request, result=result)

    def _poll(self, request, identity, now):
        session, payload = self.state["session"], request["payload"]
        cursor = payload["cursor"]
        R.require(cursor["instance_epoch"] == session["instance_epoch"] and cursor["sequence"] <= session["sequence"], "invalid_cursor")
        R.require(payload["page_size"] <= session["scope"]["limits"]["event_page_size"], "resource_limit")
        key = (R.principal_key(identity["principal"]), request["request_id"])
        digest = C.codec.digest("control", {k: request[k] for k in ("version", "operation", "payload", "extensions")})
        old = self.state["polls"].get(key)
        if old is not None:
            R.require(old["digest"] == digest, "id_conflict")
        if cursor["sequence"] < self.state["event_floor"]:
            snapshot = self._snapshot(identity["principal"], now)
            rule = C.catalog.ERRORS["history_gap"]
            error = {k: v for k, v in rule.items() if k != "http_status"}
            error.update(code="history_gap", details={"snapshot": snapshot, "next_cursor": snapshot["cursor"],
                "unresolved_actions": [value["request_id"] for value in snapshot["actions"] if value["state"] in {"pending", "executing", "unknown"}]})
            return self._reply(request, error=error)
        R.require(old is not None or len(self.state["polls"]) < 256, "resource_limit")
        high = old["high"] if old else session["sequence"]
        stop = old["end"] if old else high
        end, scanned, visible = cursor["sequence"], 0, []
        for item in self.state["events"]:
            sequence = item["wire"]["sequence"]
            if not cursor["sequence"] < sequence <= stop:
                continue
            scanned += 1
            end = sequence
            if self._visible(item, identity["principal"], now):
                visible.append(deepcopy(item["wire"]))
            if old is None and (len(visible) == payload["page_size"] or scanned == self.scan_budget):
                break
        if old is not None:
            end = old["end"]
            lease = old["lease"]
        else:
            lease = min(now + session["scope"]["limits"]["lease_period_ms"], self.state["grant"]["expires_at"])
            self.state["polls"][key] = {"digest": digest, "end": end, "high": high, "lease": lease}
            session["lease_deadline"] = lease
        result = {"events": visible, "next_cursor": {**cursor, "sequence": end},
                  "high_watermark": {**cursor, "sequence": high}, "lease_deadline": lease}
        return self._reply(request, result=result)

    def record_verified_action_result(self, result, *, origin_members, now, fault=None, reason=None):
        """受信动作账本及原始受众端口；两者均不得从 executor 请求自报字段取得。"""
        def record():
            C.validate_type("ActionResult", result)
            session, scope = self.state["session"], self.state["session"]["scope"]
            R.require(result["session_id"] == session["session_id"] and "actions" in scope["features"], "permission_denied")
            R.require(type(origin_members) is dict and origin_members and
                      origin_members.keys() <= R.principal_set(scope["audiences"]) and
                      all(type(value) is int and value > 0 for value in origin_members.values()), "permission_denied")
            previous = self.state["actions"].get(result["request_id"])
            R.require(previous is None or origin_members == previous["members"], "permission_denied")
            key = (result["request_id"], result["result_revision"])
            old = self.state["result_events"].get(key)
            if old is not None:
                R.require(C.codec.canonical(old["result"]) == C.codec.canonical(result), "reply_conflict")
                R.require(reason is None or reason == old["event"]["envelope"]["payload"]["reason"], "reply_conflict")
                return deepcopy(old["event"])
            R.require(len(self.state["result_events"]) < 256, "resource_limit")
            reducer = E.ResultReducer(session["session_id"])
            try:
                if previous is not None:
                    reducer.apply(previous["wire"]["envelope"]["payload"]["action"])
                R.require(reducer.apply(result) != "stale", "reply_conflict")
            except E.C.ContractError as error:
                raise C.ContractError(error.code) from None
            event_reason = reason or ("accepted" if result["state"] == "pending" else "claimed" if result["state"] == "executing" else "result")
            envelope = {"version": scope["version"], "session_id": session["session_id"], "id": "server-action-" + str(session["sequence"] + 1),
                        "type": "action.state", "sender": scope["instance"]["game"],
                        "audience": [p for p in scope["audiences"] if R.principal_key(p) in origin_members],
                        "payload": {"reason": event_reason, "action": deepcopy(result)}, "extensions": {}}
            item = self._append(envelope, now, origin_members=origin_members)
            self.state["actions"][result["request_id"]] = item
            self.state["result_events"][key] = {"result": deepcopy(result), "event": item["wire"]}
            return deepcopy(item["wire"])
        return self._transaction(record, fault)

    def compact_through(self, sequence):
        """测试用可信日志保留端口；只裁剪本模型内存，不删除任何本地文件。"""
        with self.lock:
            R.require(type(sequence) is int and self.state["event_floor"] <= sequence <= self.state["session"]["sequence"], "invalid_cursor")
            self.state["events"] = [item for item in self.state["events"] if item["wire"]["sequence"] > sequence]
            self.state["event_floor"] = sequence

    def revoke_result_read(self, principal, action_id):
        with self.lock:
            R.require(principal in self.state["session"]["scope"]["audiences"] and action_id in self.state["actions"], "permission_denied")
            self.state["result_read_revoked"].add((R.principal_key(principal), action_id))
