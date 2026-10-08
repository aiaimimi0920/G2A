"""单步动作的有界顺序验证；不是线程、网络或真实世界事务证明。"""

from copy import deepcopy
import importlib.util
from itertools import permutations
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / "docs" / "protocol"
SPEC = importlib.util.spec_from_file_location("action_orders_model", ROOT / "flow_model.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def opened():
    model = M.FlowModel(["actions", "resume", "handoff"], durable=True)
    oid = model.create_offer("player-proof", "game")
    model.decide("player-proof", oid)
    iid = model.redeem("agent-proof", oid, device=None)
    sid, _ = model.join("agent-proof", iid)
    model.request(sid)
    return model, oid, sid


class ActionOrderTests(unittest.TestCase):
    def test_missing_world_fact_is_not_a_valid_result(self):
        for uncertain in (False, True):
            m, _, sid = opened()
            ticket = m.claim("game-proof", sid)
            if uncertain:
                with self.assertRaises(M.Rejected):
                    m.effect("game-proof", ticket, uncertain=True)
            before = deepcopy(m.actions)
            with self.assertRaises(M.Rejected) as caught:
                m.result("game-proof", ticket, None)
            self.assertEqual(caught.exception.code, "unproven_result")
            self.assertEqual(m.actions, before)

    def test_committed_world_fact_is_visible_before_final_report(self):
        m, _, sid = opened()
        ticket = m.claim("game-proof", sid)
        m.effect("game-proof", ticket)
        self.assertEqual(m.query("agent-proof", sid)["effect"], "committed")
        self.assertEqual(m.query("agent-proof", sid)["state"], "executing")
        spec = importlib.util.spec_from_file_location("action_order_contract", ROOT / "contract_checks.py")
        checks = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checks)
        checks.validate_type("ActionResult", {"session_id": sid, "request_id": "a1", "state": "executing",
                             "effect": "committed", "result_revision": 1, "query_until": 300000})

    def test_uncertain_consumed_step_is_never_executed_again(self):
        m, _, sid = opened()
        ticket = m.claim("game-proof", sid)
        for attempt in range(3):
            with self.assertRaises(M.Rejected) as caught:
                m.effect("game-proof", ticket, uncertain=attempt == 0)
            self.assertEqual(caught.exception.code, "outcome_unknown")
        self.assertEqual(m.effects, 0)  # 模型没有可证明效果，不代表真实引擎必然未执行。
        self.assertEqual(m.query("agent-proof", sid)["effect"], "undetermined")

    def test_all_720_barrier_claim_effect_result_retry_orders(self):
        barriers = ("revoke", "cancel", "capability", "resume", "deadline", "restart")
        visited = 0
        for barrier in barriers:
            for order in permutations(("claim", "effect", "result", "barrier", "retry")):
                with self.subTest(barrier=barrier, order=order):
                    m, oid, sid = opened()
                    ticket = fact = None
                    fenced = False
                    for operation in order:
                        before_effects = m.effects
                        try:
                            if operation == "barrier":
                                if barrier == "revoke":
                                    m.revoke(oid)
                                elif barrier == "cancel":
                                    m.cancel(sid)
                                elif barrier == "capability":
                                    m.capabilities_changed()
                                elif barrier == "resume":
                                    m.resume("agent-proof", sid, 1, "resume-1")
                                elif barrier == "deadline":
                                    m.now = 30
                                else:
                                    m.restart()
                                fenced = True
                            elif operation == "claim":
                                ticket = m.claim("game-proof", sid)
                            elif operation in ("effect", "retry") and ticket is not None:
                                fact = m.effect("game-proof", ticket)
                            elif operation == "result" and ticket is not None and fact is not None:
                                m.result("game-proof", ticket, fact)
                        except M.Rejected as error:
                            self.assertIn(error.code, {"not_executable", "session_closed", "grant_revoked",
                                                       "stale_controller", "stale_transport"})
                        if fenced:
                            self.assertEqual(m.effects, before_effects)
                        self.assertLessEqual(m.effects, 1)
                        action = m.actions[(sid, "a1")]
                        if action["state"] == "succeeded":
                            self.assertEqual(m.effects, 1)
                            self.assertEqual(action["effect"], "committed")
                        if action["state"] == "cancelled":
                            self.assertEqual(m.effects, 0)
                    visited += 1
        self.assertEqual(visited, 720)

    def test_late_result_after_revocation_uses_fact_without_new_effect(self):
        m, oid, sid = opened()
        ticket = m.claim("game-proof", sid)
        fact = m.effect("game-proof", ticket)
        m.revoke(oid)
        self.assertEqual(m.query("agent-proof", sid)["state"], "unknown")
        m.result("game-proof", ticket, fact)
        m.result("game-proof", ticket, fact)
        self.assertEqual(m.effects, 1)
        self.assertEqual(m.query("agent-proof", sid)["state"], "succeeded")
