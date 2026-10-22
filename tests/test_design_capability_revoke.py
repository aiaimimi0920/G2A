"""固定会话的能力撤销；不扩展到实例级多会话传播。"""

from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


U = load("capability_revoke_session", "docs/protocol/session_harness.py")
F = load("capability_revoke_fixture", "docs/protocol/fixtures.py")
C = U.C


class CapabilityRevokeTests(unittest.TestCase):
    def setUp(self):
        self.f = F.core_fixture()
        self.h = U.SessionHarness(self.f, {})

    def send(self, op, payload, credential="agent-fixture", rid="r1", fault=None):
        return C.codec.decode(self.h.submit(C.codec.canonical(F.wire_request(op, payload, rid)),
                             credential, now=1000, fault=fault))["result"]

    def revoke(self, revision=1, **kwargs):
        return self.send("permission.revoke", {"object_type": "capability", "object_id": "find-key",
                         "expected_revision": revision}, **{"credential": "player-fixture", **kwargs})

    def action(self, revision=1):
        return self.send("action.request", {"version": "fixture-only", "session_id": "s1", "id": "a1",
            "type": "action.request", "sender": self.f["agent"], "audience": [self.f["player"]],
            "extensions": {}, "expected_capabilities_revision": revision,
            "payload": {"action": "find-key", "arguments": {"room": "hall"}, "deadline": 30000}})

    def claim(self):
        return self.send("action.claim", {"session_id": "s1", "action_id": "a1",
            "worker": F.principal("worker-1", "service")}, "worker-1-fixture", rid="claim")

    def query(self):
        return self.send("action.query", {"session_id": "s1", "action_id": "a1"})

    def deny(self, call, code):
        with self.assertRaises(C.ContractError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)

    def test_revoke_keeps_session_grant_and_result_read_scope(self):
        grant = deepcopy(self.h.state["grant"])
        scope = deepcopy(self.h.state["session"]["scope"])
        self.assertEqual(self.revoke(), {"object_type": "capability", "object_id": "find-key",
                                       "revision": 2, "state": "revoked"})
        self.assertEqual(self.h.state["grant"], grant)
        self.assertEqual(self.h.state["session"]["scope"], scope)
        self.assertEqual(self.h.state["session"]["state"], "active")
        self.assertEqual(self.h.state["definitions"], [])
        self.assertFalse(self.h.action_model.read_revoked)
        self.deny(lambda: self.action(2), "stale_capabilities")

    def test_pending_action_cannot_be_claimed_but_remains_readable(self):
        self.action()
        self.revoke()
        self.assertEqual(self.claim()["status"], "not_executable")
        self.assertEqual(self.query()["state"], "cancelled")
        self.assertEqual(self.h.action_model.model.world, {})

    def test_claimed_partial_effect_survives_and_later_step_is_denied(self):
        self.action()
        ticket = self.claim()["ticket"]
        self.h.execute("step", "worker-1", now=1000, ticket=ticket, step=1)
        world = deepcopy(self.h.action_model.model.world)
        self.revoke()
        self.deny(lambda: self.h.execute("step", "worker-1", now=1000, ticket=ticket, step=2), "stale_capabilities")
        self.h.execute("finish", "worker-1", now=1000, ticket=ticket)
        self.assertEqual(self.query()["effect"], "partial")
        fact = {"state": "cancelled", "effect": "partial", "steps": [
            {"step": 1, "effect": "committed", "evidence_ref": ticket["proof_ref"] + "-step-1"}]}
        self.assertEqual(self.send("action.commit_result", {"ticket": ticket, "fact": fact},
                                  "worker-1-fixture", rid="commit")["effect"], "partial")
        self.assertEqual(self.h.action_model.model.world, world)
        self.assertEqual(len(world), 1)

    def test_replace_cannot_restore_revoked_scope_permission(self):
        self.revoke()
        self.send("capability.replace", {"instance": self.f["scope"]["instance"], "expected_revision": 2,
                  "definitions": [self.f["action"]]}, "game-fixture", rid="replace")
        self.assertEqual(self.h.state["definitions"], [])
        self.assertFalse(self.h.action_model.definition_available)
        self.deny(lambda: self.action(3), "stale_capabilities")

    def test_before_commit_rolls_back_barrier_action_event_and_receipt(self):
        self.action()
        before = deepcopy(self.h.state)
        action = deepcopy(self.h.action_model.model.action)
        with self.assertRaises(U.S.H.InjectedFailure):
            self.revoke(fault="before_commit")
        self.assertEqual(self.h.state, before)
        self.assertEqual(self.h.action_model.model.action, action)
        self.assertTrue(self.h.action_model.definition_available)
        self.assertEqual(self.claim()["status"], "claimed")

    def test_after_commit_retry_returns_original_without_new_event(self):
        with self.assertRaises(U.S.H.InjectedFailure):
            self.revoke(fault="after_commit")
        before = deepcopy(self.h.state)
        self.assertEqual(self.revoke()["revision"], 2)
        self.assertEqual(self.h.state, before)
        self.deny(lambda: self.revoke(2), "id_conflict")
        self.deny(lambda: self.revoke(rid="stale"), "generation_conflict")

    def test_wrong_object_and_role_have_no_mutation(self):
        before = deepcopy(self.h.state)
        self.deny(lambda: self.send("permission.revoke", {"object_type": "capability", "object_id": "other",
            "expected_revision": 1}, "player-fixture"), "permission_denied")
        self.deny(lambda: self.revoke(credential="agent-fixture"), "permission_denied")
        self.assertEqual(self.h.state, before)

    def test_game_can_revoke_and_core_without_actions_rejects(self):
        self.assertEqual(self.revoke(credential="game-fixture")["state"], "revoked")
        f = F.core_fixture(["core.session", "core.events"])
        f.pop("action")
        self.h = U.SessionHarness(f, {})
        before = deepcopy(self.h.state)
        self.deny(lambda: self.revoke(), "feature_unsupported")
        self.assertEqual(self.h.state, before)

    def test_recovered_ledger_keeps_barrier_and_original_receipt(self):
        self.revoke()
        old = self.h
        self.h = U.SessionHarness(self.f, {})
        self.h.state = deepcopy(old.state)
        self.h.action_model.restore(old.action_model.checkpoint())
        self.assertEqual(self.revoke()["revision"], 2)
        self.send("capability.replace", {"instance": self.f["scope"]["instance"], "expected_revision": 2,
                  "definitions": [self.f["action"]]}, "game-fixture", rid="replace")
        self.deny(lambda: self.action(3), "stale_capabilities")

    def test_admission_wire_query_reports_original_player_receipt(self):
        helper = load("capability_revoke_status_helper", "tests/test_design_operation_status.py")
        case = helper.OperationStatusTests()
        case.setUp()
        result = case.send("permission.revoke", {"object_type": "capability", "object_id": "find-key",
                           "expected_revision": 1}, "player-fixture", rid="revoke-capability")
        view = case.query("permission.revoke", "revoke-capability", "player-fixture")
        self.assertEqual((view["state"], view["revocation"]), ("done", result))
        case.deny(lambda: case.query("permission.revoke", "revoke-capability"))


if __name__ == "__main__":
    unittest.main()
