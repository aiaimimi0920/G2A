"""单会话 chat.send 的可执行装配，固定凭据、内存事务、无网络/插件/持久化。

管理方法是测试夹具端口而不是公开 API；不能将其当作真实撤权认证实现。
"""

from copy import deepcopy
import importlib.util
from pathlib import Path
from threading import RLock


SPEC = importlib.util.spec_from_file_location("chat_sources", Path(__file__).with_name("source_authorization.py"))
S = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(S)
R, C = S.R, S.C
EXT_SPEC = importlib.util.spec_from_file_location("chat_extensions", Path(__file__).with_name("extension_runtime.py"))
EXT = importlib.util.module_from_spec(EXT_SPEC)
EXT_SPEC.loader.exec_module(EXT)


class InjectedFailure(RuntimeError):
    pass


class ChatHarness:
    def __init__(self, fixture, records):
        self.lock = RLock()
        self.state = deepcopy({"session": fixture["session"], "grant": fixture["grant"],
                               "records": records, "receipts": {}, "events": []})
        self.members = {R.principal_key(fixture[name]): 1 for name in ("agent", "player")}
        self.credentials = {"agent-fixture": {"principal": deepcopy(fixture["agent"]),
                            "role": "companion_control", "generation": 1,
                            "transport_epoch": "transport-1", "device_id": None}}

    def submit(self, raw, credential, *, now, fault=None):
        # fault 是测试驱动参数，不属于线上请求或客户端可控字段。
        if fault not in (None, "before_commit", "after_commit"):
            raise ValueError("invalid_fault")
        request = C.validate_request(raw)
        R.require(request["operation"] == "chat.send", "unsupported_operation")
        with self.lock:
            identity = self.credentials.get(credential)
            R.require(identity is not None, "unauthenticated")
            staged = deepcopy(self.state)
            session, grant = staged["session"], staged["grant"]
            C.authorize_route("chat.send", identity["role"], "data", session["scope"]["features"])
            R.validate_session_write(session, grant, now=now, **{key: value for key, value in identity.items() if key != "role"})
            envelope = request["payload"]
            R.require(envelope["session_id"] == session["session_id"] and envelope["version"] == session["scope"]["version"], "permission_denied")
            R.require(envelope["sender"] == identity["principal"], "permission_denied")
            R.require(len(raw) <= session["scope"]["limits"]["message_bytes"], "resource_limit")
            key = (session["session_id"], R.principal_key(identity["principal"]), envelope["id"])
            digest = C.codec.digest("message", envelope)
            if key in staged["receipts"]:
                receipt = staged["receipts"][key]
                R.require(receipt["record_digest"] == digest, "id_conflict")
                reply = {"request_id": request["request_id"], "result": {**receipt, "duplicate": True}}
            else:
                _, activated = C.validate_active_request(raw, selected_extensions=session["scope"]["extensions"], supported_extensions=EXT.SUPPORTED)
                EXT.enforce(C, activated, "chat.send", envelope)
                EXT.enforce(C, session["scope"]["effective_policy"]["extensions"], "chat.send", envelope)
                frozen = R.validate_envelope_audience(envelope, session, authenticated_sender=identity["principal"], current_members=self.members)
                revisions = S.validate_disclosure(envelope, session, staged["records"], now=now)
                R.require(len(staged["events"]) < 64, "resource_limit")
                sequence = session["sequence"] + 1
                event = {"sequence": sequence, "envelope": deepcopy(envelope), "created_at": now}
                C.validate_type("Event", event)
                receipt = {"id": envelope["id"], "accepted_at": now, "record_digest": digest, "duplicate": False}
                staged["receipts"][key] = receipt
                staged["events"].append({"wire": event, "members": frozen, "sources": revisions})
                session["sequence"] = sequence
                session["lease_deadline"] = min(now + session["scope"]["limits"]["lease_period_ms"], grant["expires_at"])
                reply = {"request_id": request["request_id"], "result": receipt}
            C.validate_reply("chat.send", request["request_id"], reply)
            encoded = C.codec.canonical(reply)
            if fault == "before_commit":
                raise InjectedFailure("before_commit")
            self.state = staged
            if fault == "after_commit":
                raise InjectedFailure("after_commit")
            return encoded

    def delivery(self, verified_principal, *, now):
        """可信投递端口读，不是公开 session.events API；不续租、不消费游标。"""
        with self.lock:
            session = self.state["session"]
            if session["state"] != "active" or self.state["grant"]["state"] != "active":
                return []
            if now >= min(session["lease_deadline"], self.state["grant"]["expires_at"]):
                return []
            visible = []
            for item in self.state["events"]:
                if R.can_deliver(verified_principal, item["members"], self.members, session["scope"]["audiences"]) and S.disclosure_still_allowed(
                        item["wire"]["envelope"], session, self.state["records"], item["sources"], now=now):
                    visible.append(deepcopy(item["wire"]))
            return visible

    def revoke_source(self, source_id):
        with self.lock:
            record = self.state["records"][source_id]
            record["state"] = "revoked"
            record["revision"] += 1

    def replace_member_generation(self, principal, generation):
        with self.lock:
            self.members[R.principal_key(principal)] = generation
