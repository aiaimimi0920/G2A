"""已认证响应的消费参考模型；不执行事件内容、不认证远端、不提供磁盘持久化。"""

from copy import deepcopy
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("consumer_relations", Path(__file__).with_name("relations.py"))
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)
C = R.checks


class ResultReducer:
    def __init__(self, session_id):
        self.session_id = session_id
        self.results = {}

    def apply(self, result):
        C.validate_type("ActionResult", result)
        R.require(result["session_id"] == self.session_id, "permission_denied")
        old = self.results.get(result["request_id"])
        R.require(old is not None or len(self.results) < 256, "resource_limit")
        if old is not None:
            if result["result_revision"] < old["result_revision"]:
                return "stale"
            if result["result_revision"] == old["result_revision"]:
                R.require(C.codec.canonical(old) == C.codec.canonical(result), "reply_conflict")
                return "duplicate"
            if old["state"] in {"succeeded", "failed", "cancelled"}:
                keys = {"state", "effect", "known_result"}
                R.require(C.codec.canonical({k: v for k, v in old.items() if k in keys}) ==
                          C.codec.canonical({k: v for k, v in result.items() if k in keys}), "execution_conflict")
            R.require(not (old["state"] != "pending" and result["state"] == "pending"), "execution_conflict")
            R.require(not (old["effect"] in {"partial", "committed"} and result["effect"] == "none"), "execution_conflict")
        self.results[result["request_id"]] = deepcopy(result)
        return "applied"


class EventConsumer:
    def __init__(self, session_id, epoch, version, *, supported_types=("chat.message", "game.context")):
        self.cursor = {"session_id": session_id, "instance_epoch": epoch, "sequence": 0}
        self.version = version
        self.supported_types = frozenset(supported_types)
        self.events = []
        self.needs_snapshot = False

    def history_gap(self):
        self.needs_snapshot = True

    def reset_from_verified_snapshot(self, cursor):
        """仅可信恢复端口调用；快照已经独立认证、按当前读权过滤，不从错误任意字段采信。"""
        C.validate_type("Cursor", cursor)
        R.require(cursor["session_id"] == self.cursor["session_id"] and
                  cursor["instance_epoch"] == self.cursor["instance_epoch"], "invalid_cursor")
        R.require(self.needs_snapshot and cursor["sequence"] >= self.cursor["sequence"], "invalid_cursor")
        self.cursor = deepcopy(cursor)
        self.events = []  # 本窄模型只保留快照之后事件；不声称重建了业务快照内容。
        self.needs_snapshot = False

    def apply_page(self, page, requested_cursor):
        C.validate_type("EventPage", page)
        C.validate_type("Cursor", requested_cursor)
        R.require(not self.needs_snapshot, "history_gap")
        for cursor in (requested_cursor, page["next_cursor"], page["high_watermark"]):
            R.require(all(cursor[k] == self.cursor[k] for k in ("session_id", "instance_epoch")), "invalid_cursor")
        if requested_cursor["sequence"] < self.cursor["sequence"]:
            return "stale"  # 旧 poll 回复不得倒退 cursor 或再次应用事件。
        R.require(requested_cursor == self.cursor, "invalid_cursor")
        end = page["next_cursor"]["sequence"]
        R.require(self.cursor["sequence"] <= end <= page["high_watermark"]["sequence"], "invalid_cursor")
        last = self.cursor["sequence"]
        staged = []
        for event in page["events"]:
            envelope = event["envelope"]
            R.require(last < event["sequence"] <= end, "invalid_cursor")
            R.require(envelope["session_id"] == self.cursor["session_id"] and envelope["version"] == self.version, "permission_denied")
            R.require(envelope["type"] in self.supported_types, "unsupported_operation")
            kind = C.catalog.EVENT_TYPES.get(envelope["type"])
            R.require(kind is not None, "unsupported_operation")
            C.validate_type(kind, envelope)
            staged.append(deepcopy(event))
            last = event["sequence"]
        R.require(len(self.events) + len(staged) <= 256, "resource_limit")
        # 先校验整页，再更新 cursor，不能半页错误却越过未处理事件。
        self.events.extend(staged)
        self.cursor = deepcopy(page["next_cursor"])
        return "applied"


class BusinessConsumer:
    """已认证且按当前权限过滤的完整可见视图；不反向授予控制或成员权限。"""
    def __init__(self, snapshot, principal):
        self.principal = deepcopy(principal)
        self._validate_snapshot(snapshot)
        session = snapshot["session"]
        self.stream = EventConsumer(session["session_id"], session["instance_epoch"], session["scope"]["version"],
                                    supported_types=C.catalog.EVENT_TYPES)
        self.stream.cursor = deepcopy(snapshot["cursor"])
        self.recovery_token = 0
        self.view = self._view(snapshot)

    def _validate_snapshot(self, snapshot):
        C.validate_type("RecoverySnapshot", snapshot)
        session, cursor = snapshot["session"], snapshot["cursor"]
        scope = session["scope"]
        R.require(cursor == {"session_id": session["session_id"], "instance_epoch": session["instance_epoch"],
                             "sequence": session["sequence"]}, "invalid_cursor")
        R.require(session["instance_epoch"] == scope["instance"]["epoch"], "stale_controller")
        R.require(self.principal in scope["audiences"], "permission_denied")
        self._definitions(snapshot["definitions"], scope)
        self._members(snapshot["members"], scope)
        ids, categories = set(), set()
        for result in snapshot["actions"]:
            R.require(result["session_id"] == session["session_id"] and result["request_id"] not in ids, "reply_conflict")
            ids.add(result["request_id"])
        R.require("actions" in scope["features"] or not snapshot["actions"], "feature_unsupported")
        for context in snapshot["contexts"]:
            self._envelope(context, session)
            category = context["payload"]["category"]
            R.require(category in scope["context_categories"] and category not in categories, "reply_conflict")
            categories.add(category)

    @staticmethod
    def _definitions(definitions, scope):
        ids = set()
        for definition in definitions:
            name = definition["id"]
            R.require("actions" in scope["features"], "feature_unsupported")
            R.require(name not in ids and name in scope["action_ids"], "permission_denied")
            R.require(C.codec.digest("action-definition", definition) == scope["approved_action_digests"].get(name), "approval_stale")
            C.validate_value_schema(definition["parameters"], require_object=True)
            C.validate_value_schema(definition["result_schema"])
            ids.add(name)

    @staticmethod
    def _members(members, scope):
        R.require(R.principal_set(members) <= R.principal_set(scope["audiences"]), "permission_denied")

    def _envelope(self, envelope, session):
        scope = session["scope"]
        R.require(envelope["session_id"] == session["session_id"] and envelope["version"] == scope["version"], "permission_denied")
        R.require(self.principal in envelope["audience"] and R.principal_set(envelope["audience"]) <= R.principal_set(scope["audiences"]), "permission_denied")
        if envelope["type"] != "chat.message":
            R.require(envelope["sender"] == scope["instance"]["game"], "permission_denied")
        else:
            R.require(envelope["sender"] in scope["audiences"], "permission_denied")
            if envelope["payload"]["channel"] == "team":
                R.require("team" in scope["features"], "feature_unsupported")
                R.require("expected_membership_revision" in envelope and
                          envelope["expected_membership_revision"] <= session["membership_revision"], "membership_conflict")
        # 本消费 profile 无扩展处理器；未知 optional 只作为数据，required 不可静默跳过。
        R.require(not any(value["required"] for value in envelope["extensions"].values()), "feature_unsupported")

    @staticmethod
    def _view(snapshot):
        reducer = ResultReducer(snapshot["session"]["session_id"])
        for result in snapshot["actions"]:
            reducer.apply(result)
        return {"session": deepcopy(snapshot["session"]), "results": reducer,
                "contexts": {value["payload"]["category"]: deepcopy(value) for value in snapshot["contexts"]},
                "definitions": deepcopy(snapshot["definitions"]), "members": deepcopy(snapshot["members"])}

    @staticmethod
    def _session_transition(old, new):
        R.require(old["session_id"] == new["session_id"] and old["instance_epoch"] == new["instance_epoch"]
                  and C.codec.canonical(old["scope"]) == C.codec.canonical(new["scope"])
                  and old["grant_id"] == new["grant_id"], "approval_stale")
        R.require(not (old["state"] == "closed" and new["state"] != "closed"), "session_closed")
        for key in ("control_generation", "capabilities_revision", "membership_revision", "sequence"):
            R.require(new[key] >= old[key], "reply_conflict")

    def history_gap(self):
        self.stream.history_gap()
        self.recovery_token += 1
        return self.recovery_token

    def reset_from_verified_snapshot(self, snapshot, recovery_token):
        R.require(self.stream.needs_snapshot and recovery_token == self.recovery_token, "history_gap")
        self._validate_snapshot(snapshot)
        self._session_transition(self.view["session"], snapshot["session"])
        R.require(snapshot["cursor"]["sequence"] >= self.stream.cursor["sequence"], "invalid_cursor")
        staged = self._view(snapshot)
        # 全量可见视图会移除已失去读权/已过期对象；仍可见的对象不能借快照倒退。
        for key, result in staged["results"].results.items():
            old = self.view["results"].results.get(key)
            if old is not None:
                R.require(result["result_revision"] >= old["result_revision"], "reply_conflict")
                check = ResultReducer(snapshot["session"]["session_id"])
                check.apply(old)
                check.apply(result)
        self.stream.reset_from_verified_snapshot(snapshot["cursor"])
        self.view = staged

    def recover_reply(self, raw, operation, request_id, recovery_token):
        """认证后的响应字节；关联 ID 与本地恢复轮次都必须匹配，不采信任意错误附带内容。"""
        R.require(operation in {"session.snapshot", "session.events"}, "unsupported_operation")
        reply = C.codec.decode(raw)
        C.validate_reply(operation, request_id, reply)
        if operation == "session.events":
            R.require("error" in reply and reply["error"]["code"] == "history_gap", "history_gap")
            snapshot = reply["error"]["details"]["snapshot"]
        else:
            R.require("result" in reply, "history_gap")
            snapshot = reply["result"]
        self.reset_from_verified_snapshot(snapshot, recovery_token)

    def apply_page(self, page, requested_cursor):
        stream, view = deepcopy(self.stream), deepcopy(self.view)
        status = stream.apply_page(page, requested_cursor)
        if status == "stale":
            return status
        for event in page["events"]:
            envelope = event["envelope"]
            session, scope = view["session"], view["session"]["scope"]
            kind, payload = envelope["type"], envelope["payload"]
            self._envelope(envelope, session)
            R.require(session["state"] != "closed" or kind in {"action.state", "session.closed"}, "session_closed")
            if kind == "game.context":
                R.require(payload["category"] in scope["context_categories"], "permission_denied")
                view["contexts"][payload["category"]] = deepcopy(envelope)
            elif kind == "action.state":
                R.require("actions" in scope["features"], "feature_unsupported")
                reason, action = payload["reason"], payload["action"]
                allowed = {"accepted": {"pending"}, "claimed": {"executing"}, "cancel_requested": set(C.catalog.TYPES["ActionState"]["enum"]),
                           "result": {"succeeded", "failed", "cancelled", "unknown"}}
                R.require(action["state"] in allowed[reason], "invalid_message")
                view["results"].apply(action)
            elif kind in {"capability.update", "membership.update"}:
                is_capability = kind == "capability.update"
                revision_key = "capabilities_revision" if is_capability else "membership_revision"
                key = "definitions" if is_capability else "members"
                (self._definitions if is_capability else self._members)(payload[key], scope)
                R.require(payload["revision"] >= session[revision_key], "reply_conflict")
                if payload["revision"] == session[revision_key]:
                    R.require(C.codec.canonical(payload[key]) == C.codec.canonical(view[key]), "reply_conflict")
                session[revision_key], view[key] = payload["revision"], deepcopy(payload[key])
            elif kind.startswith("session."):
                new = payload["session"]
                self._session_transition(session, new)
                R.require(new["sequence"] == event["sequence"], "invalid_cursor")
                if kind == "session.closed":
                    R.require(new["state"] == "closed" and not new["ready"], "invalid_message")
                elif kind == "session.ready":
                    R.require(new["state"] == "active" and new["ready"], "invalid_message")
                else:
                    R.require(new["control_generation"] > session["control_generation"], "stale_controller")
                # revision 变化必须由带完整数据的相应通知或快照完成，不能只改版本号。
                R.require(new["capabilities_revision"] == session["capabilities_revision"] and
                          new["membership_revision"] == session["membership_revision"], "reply_conflict")
                view["session"] = deepcopy(new)
            view["session"]["sequence"] = event["sequence"]
        view["session"]["sequence"] = stream.cursor["sequence"]
        self.stream, self.view = stream, view
        return "applied"
