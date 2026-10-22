"""原请求恢复决策：未知不被后续拒绝抹掉，不产生新的效果 ID。"""
from copy import deepcopy
import importlib.util
from itertools import permutations
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


F = load("recovery_fixture", "docs/protocol/fixtures.py")
E = load("recovery_errors", "docs/protocol/error_mapping.py")
C = E.checks


class RequestRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.M = load("request_recovery_test", "docs/protocol/request_recovery.py")
        self.f = F.core_fixture()
        self.request = F.wire_request("action.request", {"version": "fixture-only", "session_id": "s1", "id": "a1",
            "type": "action.request", "sender": self.f["agent"], "audience": [self.f["player"]],
            "extensions": {}, "expected_capabilities_revision": 1,
            "payload": {"action": "find-key", "arguments": {"room": "hall"}, "deadline": 30000}}, "outer-a1")
        self.raw = C.codec.canonical(self.request)
        self.h = self.M.RequestRecovery(self.raw, context="fixture-authority-agent")

    def error(self, code, *, delay=None, rid="outer-a1"):
        error = E.boundary_error(code, knowledge=C.catalog.ERRORS[code]["outcome"])
        if delay is not None:
            error["retry_after_ms"] = delay
        return C.codec.canonical({"request_id": rid, "error": error})

    def observe(self, raw, now=1000):
        return self.h.observe_reply(raw, context="fixture-authority-agent", now=now)

    def lost(self, now=1000):
        return self.h.transport_lost(context="fixture-authority-agent", now=now)

    def query(self, qid="q1", now=1000):
        return self.h.query_bytes(qid, context="fixture-authority-agent", now=now)

    def deny(self, fn):
        with self.assertRaises(self.M.C.ContractError):
            fn()

    def test_unknown_then_rejected_is_not_proof_of_never_accepted(self):
        self.assertEqual(self.lost()["outcome"], "unknown")
        plan = self.observe(self.error("rate_limited"))
        self.assertEqual((plan["outcome"], plan["next"]), ("unknown", "query_original"))
        self.deny(lambda: self.h.retry_bytes(context="fixture-authority-agent", now=1000))

    def test_known_accepted_failure_survives_later_timeout_and_rejection(self):
        self.observe(self.error("operation_failed"))
        self.lost()
        plan = self.observe(self.error("permission_denied"))
        self.assertEqual((plan["outcome"], plan["next"]), ("accepted", "query_original"))

    def test_same_request_retry_preserves_exact_bytes_and_honors_delay(self):
        self.observe(self.error("rate_limited", delay=20))
        self.deny(lambda: self.h.retry_bytes(context="fixture-authority-agent", now=1019))
        self.assertEqual(self.h.retry_bytes(context="fixture-authority-agent", now=1020), self.raw)
        self.assertEqual(self.h.plan()["next"], "await_response")

    def test_timeout_does_not_generate_cancel_or_change_action_id(self):
        self.lost()
        request = C.codec.decode(self.query())
        self.assertEqual(request["operation"], "operation.get")
        self.assertEqual(request["payload"], {"operation": "action.request", "original_request_id": "a1"})
        self.assertEqual(self.h.original_bytes, self.raw)

    def test_cancel_lookup_uses_cancel_id_not_target_action_id(self):
        request = F.wire_request("action.cancel", {"version": "fixture-only", "session_id": "s1", "id": "cancel-a1",
            "type": "action.cancel", "sender": self.f["agent"], "audience": [self.f["player"]],
            "extensions": {}, "payload": {"request_id": "a1"}}, "outer-cancel")
        self.h = self.M.RequestRecovery(C.codec.canonical(request), context="fixture-authority-agent")
        self.lost()
        self.assertEqual(C.codec.decode(self.query())["payload"]["original_request_id"], "cancel-a1")

    def test_control_lookup_uses_outer_request_id(self):
        self.h = self.M.RequestRecovery(C.codec.canonical(F.wire_request("session.close",
            {"session_id": "s1", "reason": "left"}, "close-outer")), context="fixture-authority-agent")
        self.lost()
        self.assertEqual(C.codec.decode(self.query())["payload"]["original_request_id"], "close-outer")

    def test_malformed_mismatched_and_injected_error_reply_are_unknown(self):
        for raw in (b"<html>503 retry now</html>", self.error("rate_limited", rid="other"),
                    C.codec.canonical({"request_id": "outer-a1", "error": {"code": "rate_limited"}})):
            self.setUp()
            self.assertEqual(self.observe(raw)["outcome"], "unknown")
            self.assertEqual(self.h.plan()["next"], "query_original")

    def test_error_operation_ref_cannot_redirect_original_lookup(self):
        error = C.codec.decode(self.error("outcome_unknown"))
        error["error"]["details"]["operation_ref"] = "another-action"
        self.observe(C.codec.canonical(error))
        self.assertEqual(C.codec.decode(self.query())["payload"]["original_request_id"], "a1")

    def test_reauth_and_renegotiation_do_not_mint_new_request(self):
        for code, action in (("unauthenticated", "reauth_required"), ("approval_stale", "renegotiate_required"),
                             ("permission_denied", "stop")):
            self.setUp()
            self.assertEqual(self.observe(self.error(code))["next"], action)
            self.deny(lambda: self.h.retry_bytes(context="fixture-authority-agent", now=1000))
            self.assertEqual(self.h.original_bytes, self.raw)

    def test_retry_budget_and_query_budget_are_bounded(self):
        self.h = self.M.RequestRecovery(self.raw, context="fixture-authority-agent", max_retries=1, max_queries=1)
        self.observe(self.error("temporarily_unavailable"))
        self.h.retry_bytes(context="fixture-authority-agent", now=1000)
        self.assertEqual(self.observe(self.error("temporarily_unavailable"))["next"], "stop")
        self.lost()
        self.query()
        self.deny(lambda: self.query("q2"))
        self.assertEqual(self.h.plan()["outcome"], "unknown")

    def test_query_response_checks_both_outer_and_original_correlation(self):
        self.lost()
        self.query()
        for op, rid in (("session.close", "a1"), ("action.request", "other-action")):
            before = self.h.plan()
            reply = {"request_id": "q1", "result": {"operation": op, "request_id": rid, "state": "done", "outcome_ref": "a1"}}
            self.deny(lambda: self.h.observe_query(C.codec.canonical(reply), context="fixture-authority-agent", now=1000))
            self.assertEqual(self.h.plan(), before)

    def test_denied_or_expired_query_does_not_erase_original_uncertainty(self):
        for code in ("permission_denied", "result_expired", "result_unavailable"):
            self.setUp()
            self.lost()
            self.query()
            plan = self.h.observe_query(self.error(code, rid="q1"), context="fixture-authority-agent", now=1000)
            self.assertEqual((plan["outcome"], plan["next"]), ("unknown", "unresolved"))

    def test_pending_and_done_query_report_acceptance_not_world_success(self):
        self.lost()
        for state, advice in (("pending", "query_original"), ("done", "resolved")):
            self.query("q-" + state)
            result = {"operation": "action.request", "request_id": "a1", "state": state, "outcome_ref": "a1"}
            plan = self.h.observe_query(C.codec.canonical({"request_id": "q-" + state, "result": result}),
                                       context="fixture-authority-agent", now=1000)
            self.assertEqual((plan["outcome"], plan["next"]), ("accepted", advice))
            self.assertNotIn("effect", plan)

    def test_foreign_context_and_clock_rollback_are_rejected_without_mutation(self):
        self.lost()
        before = self.h.plan()
        self.deny(lambda: self.h.transport_lost(context="other-authority", now=1000))
        self.deny(lambda: self.h.transport_lost(context="fixture-authority-agent", now=999))
        self.assertEqual(self.h.plan(), before)

    def test_unsupported_owner_operations_and_boolean_budgets_fail_closed(self):
        for op, payload in (("privacy.receipt", {"privacy_request_id": "p1"}),
                            ("action.query", {"session_id": "s1", "action_id": "a1"})):
            with self.assertRaises(self.M.C.ContractError):
                self.M.RequestRecovery(C.codec.canonical(F.wire_request(op, payload)), context="ctx")
        with self.assertRaises(self.M.C.ContractError):
            self.M.RequestRecovery(self.raw, context="ctx", max_retries=True)

    def test_byte_chain_lost_accept_query_and_duplicate_do_not_repeat_effect(self):
        helper = load("recovery_status_helper", "tests/test_design_operation_status.py")
        case = helper.OperationStatusTests()
        case.setUp()
        raw = helper.C.codec.canonical(self.request)
        with self.assertRaises(helper.H.U.S.H.InjectedFailure):
            case.h.submit(raw, case.token, now=1000, fault="after_commit")
        self.lost()
        query = self.query()
        response = case.h.submit(query, "agent-identity", now=1000)
        self.assertEqual(self.h.observe_query(response, context="fixture-authority-agent", now=1000)["outcome"], "accepted")
        ticket = case.claim()
        case.h.execute("step", "worker-1", now=1000, ticket=ticket, step=1)
        before = deepcopy(case.h.session.action_model.model.world)
        reply = case.h.submit(self.h.original_bytes, case.token, now=1000)
        self.assertEqual(self.observe(reply)["outcome"], "accepted")
        self.assertEqual(case.h.session.action_model.model.world, before)
        self.assertEqual(len(before), 1)

    def test_lost_query_and_late_old_reply_do_not_cross_poll_generations(self):
        self.lost()
        self.query("q1")
        self.assertEqual(self.h.query_lost(context="fixture-authority-agent", now=1000)["outcome"], "unknown")
        self.query("q2")
        before = self.h.plan()
        result = {"operation": "action.request", "request_id": "a1", "outcome_ref": "a1", "state": "done"}
        self.deny(lambda: self.h.observe_query(C.codec.canonical({"request_id": "q1", "result": result}),
                  context="fixture-authority-agent", now=1000))
        self.assertEqual(self.h.plan(), before)
        self.assertEqual(self.h.observe_query(C.codec.canonical({"request_id": "q2", "result": result}),
                         context="fixture-authority-agent", now=1000)["next"], "resolved")

    def test_unknown_response_backoff_applies_to_queries_not_just_retries(self):
        self.observe(self.error("transport_timeout", delay=30))
        self.deny(lambda: self.query(now=1029))
        self.query(now=1030)
        self.h.observe_query(self.error("temporarily_unavailable", delay=40, rid="q1"),
                             context="fixture-authority-agent", now=1030)
        self.deny(lambda: self.query("q2", now=1069))
        self.assertEqual(C.codec.decode(self.query("q2", now=1070))["payload"]["original_request_id"], "a1")

    def test_receipt_must_bind_original_id_and_digest_then_late_errors_do_not_erase_it(self):
        receipt = {"id": "other", "accepted_at": 1000, "record_digest": C.codec.digest("message", self.request["payload"]),
                   "duplicate": False}
        self.assertEqual(self.observe(C.codec.canonical({"request_id": "outer-a1", "result": receipt}))["outcome"], "unknown")
        receipt["id"] = "a1"
        receipt["record_digest"] = "0" * 64
        self.assertEqual(self.observe(C.codec.canonical({"request_id": "outer-a1", "result": receipt}))["outcome"], "unknown")
        receipt["record_digest"] = C.codec.digest("message", self.request["payload"])
        self.assertEqual(self.observe(C.codec.canonical({"request_id": "outer-a1", "result": receipt}))["next"], "response_received")
        self.assertEqual(self.lost()["next"], "response_received")
        self.assertEqual(self.observe(self.error("permission_denied"))["outcome"], "accepted")

    def test_all_six_error_orders_preserve_strongest_acceptance_evidence(self):
        for order in permutations(("rate_limited", "transport_timeout", "operation_failed")):
            self.setUp()
            for code in order:
                self.observe(self.error(code))
            self.assertEqual(self.h.plan()["outcome"], "accepted")
            self.assertEqual(self.h.plan()["next"], "query_original")

    def test_retry_deadline_over_wire_clock_range_never_wraps_to_immediate_retry(self):
        end = C.codec.MAX_INTEGER
        self.observe(self.error("rate_limited", delay=20), now=end - 1)
        self.assertGreater(self.h.plan()["not_before"], end)
        self.deny(lambda: self.h.retry_bytes(context="fixture-authority-agent", now=end))


if __name__ == "__main__":
    unittest.main()
