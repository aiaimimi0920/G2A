"""客户端原请求恢复的有界内存模型；不发网络、不保存凭据、不推断世界效果。"""
import importlib.util
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("recovery_contracts", Path(__file__).with_name("contract_checks.py"))
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)


class RequestRecovery:
    # 先固定动作/取消/关闭这三个恢复场景；不把相同查询名当作全 owner/秘密回放策略。
    OPERATIONS = frozenset({"action.request", "action.cancel", "session.close"})

    def __init__(self, raw, *, context, max_retries=2, max_queries=8):
        request = C.validate_request(raw)
        self._require(request["operation"] in self.OPERATIONS, "unsupported_operation")
        C.validate_type("Id", context)
        self._require(type(max_retries) is int and 0 <= max_retries <= 8 and
                      type(max_queries) is int and 1 <= max_queries <= 16, "invalid_arguments")
        self._raw, self._request, self._context = bytes(raw), request, context
        self._original_id = (request["payload"]["id"] if request["operation"] in {"action.request", "action.cancel"}
                             else request["request_id"])
        self._outcome, self._next = "unobserved", "await_response"
        self._last_now, self._not_before = 0, 0
        self._retries, self._queries = 0, set()
        self._max_retries, self._max_queries = max_retries, max_queries
        self._query_id, self._terminal = None, None

    @staticmethod
    def _require(condition, code):
        if not condition:
            raise C.ContractError(code)

    @property
    def original_bytes(self):
        return self._raw

    def plan(self):
        # not_before 是内部单调时间计算，不编码为公开 Nat；溢出 wire 时钟范围时不能提前重试。
        return {"outcome": self._outcome, "next": self._next, "not_before": self._not_before,
                "in_flight": self._next in {"await_response", "await_query"},
                "retries": self._retries, "queries": len(self._queries)}

    def _check(self, context, now):
        self._require(context == self._context, "permission_denied")
        C.validate_type("Nat", now)
        self._require(now >= self._last_now, "invalid_arguments")

    def _merge(self, outcome):
        order = {"unobserved": 0, "not_accepted": 1, "unknown": 2, "accepted": 3}
        if order[outcome] > order[self._outcome]:
            self._outcome = outcome

    def _query_next(self):
        return "query_original" if len(self._queries) < self._max_queries else "unresolved"

    def _advice(self, error):
        if self._terminal:
            return self._terminal
        if self._outcome in {"unknown", "accepted"}:
            return self._query_next()
        return {"never": "stop", "after_reauth": "reauth_required", "after_renegotiate": "renegotiate_required",
                "same_request": "retry_same" if self._retries < self._max_retries else "stop"}[error["retry"]]

    def transport_lost(self, *, context, now):
        self._check(context, now)
        self._last_now = now
        self._merge("unknown")
        self._next = self._terminal or self._query_next()
        return self.plan()

    def observe_reply(self, raw, *, context, now):
        self._check(context, now)
        try:
            reply = C.validate_reply(self._request["operation"], self._request["request_id"], C.codec.decode(raw))
            if "result" in reply and self._request["operation"] in {"action.request", "action.cancel"}:
                receipt = reply["result"]
                self._require(receipt["id"] == self._original_id and
                    receipt["record_digest"] == C.codec.digest("message", self._request["payload"]), "invalid_message")
        except (C.ContractError, C.codec.CodecError):
            # HTML、破损 JSON、错关联及不合约错误均不提供提交知识，也不回显输入。
            return self.transport_lost(context=context, now=now)
        self._last_now = now
        if "result" in reply:
            self._merge("accepted")
            self._terminal = self._next = "response_received"
        else:
            error = reply["error"]
            self._merge(error["outcome"])
            self._not_before = max(self._not_before, now + error.get("retry_after_ms", 0))
            self._next = self._advice(error)
        return self.plan()

    def retry_bytes(self, *, context, now):
        self._check(context, now)
        self._require(self._next == "retry_same" and now >= self._not_before and
                      self._retries < self._max_retries, "operation_rejected")
        self._last_now = now
        self._retries += 1
        self._next = "await_response"
        return self._raw

    def query_bytes(self, query_id, *, context, now):
        self._check(context, now)
        C.validate_type("Id", query_id)
        self._require(self._next == "query_original" and now >= self._not_before and
                      len(self._queries) < self._max_queries and query_id not in self._queries, "operation_rejected")
        query = {"version": self._request["version"], "operation": "operation.get", "request_id": query_id,
                 "payload": {"operation": self._request["operation"], "original_request_id": self._original_id},
                 "extensions": {}}
        raw = C.codec.canonical(query)
        C.validate_request(raw)
        self._last_now, self._query_id = now, query_id
        self._queries.add(query_id)
        self._next = "await_query"
        return raw

    def query_lost(self, *, context, now):
        self._check(context, now)
        self._require(self._next == "await_query", "operation_rejected")
        self._last_now = now
        self._query_id = None
        self._next = self._terminal or self._query_next()
        return self.plan()

    def observe_query(self, raw, *, context, now):
        self._check(context, now)
        self._require(self._next == "await_query" and self._query_id is not None, "operation_rejected")
        reply = C.validate_reply("operation.get", self._query_id, C.codec.decode(raw))
        if "result" in reply:
            view = reply["result"]
            self._require(view["operation"] == self._request["operation"] and
                          view["request_id"] == self._original_id, "invalid_message")
        # 验证全部关联后才提交客户端状态；查询拒绝不提供原变更的 not_accepted 证明。
        self._last_now, self._query_id = now, None
        if "result" in reply:
            self._merge("accepted")
            if view["state"] in {"done", "failed"}:
                self._terminal = "resolved"
            self._next = self._terminal or self._query_next()
        else:
            error = reply["error"]
            self._not_before = max(self._not_before, now + error.get("retry_after_ms", 0))
            self._next = self._query_next() if error["retry"] == "same_request" else "unresolved"
        return self.plan()
