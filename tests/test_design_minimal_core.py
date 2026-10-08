"""无虚构 action 定义的最小 core；字节入口、能力拒绝与准入回滚。"""

from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / "docs/protocol"


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


H = load("minimal_core_control", "control_harness.py")
F = load("minimal_core_fixture", "fixtures.py")
C = H.C


class MinimalCoreTests(unittest.TestCase):
    def setUp(self):
        self.f = F.core_fixture(["core.session", "core.events"])
        self.definition = self.f.pop("action")
        self.h = H.ControlHarness(self.f)

    def send(self, op, payload, credential="agent-identity", *, rid="r1", fault=None):
        raw = C.codec.canonical(F.wire_request(op, payload, rid))
        return C.codec.decode(self.h.submit(raw, credential, now=1000, fault=fault))["result"]

    def invitation(self, entry="companion"):
        offer = self.send("offer.create", {"entry": entry, "descriptor_id": "fixture-descriptor",
            "expected_descriptor_revision": 1, "requested": self.f["requested"]},
            "agent-identity" if entry == "companion" else "player-fixture")
        payload = {"offer_id": offer["offer_id"], "scope_digest": offer["scope_digest"], "allow": True,
                   "remember": False, "launch_permission": False, "decision_ref": "approve"}
        self.h.decisions["approve"] = {"player": self.f["player"], "payload": deepcopy(payload)}
        self.send("offer.decide", payload, "player-fixture")
        self.invite = self.send("invitation.redeem", {"offer_id": offer["offer_id"],
                               "join_intent": {"scope_digest": offer["scope_digest"]}})

    def join(self, **kwargs):
        return self.send("session.join", {k: self.invite[k] for k in ("invitation_id", "join_intent")},
                         self.invite["invitation_credential"], **kwargs)

    def ready(self, entry="companion"):
        self.invitation(entry)
        self.assertEqual(self.join()["status"], "join_pending")
        self.h.finish_admission(now=1000)
        self.delivery = self.join()
        self.token = self.delivery["control_credential"]

    def deny(self, op, payload, credential, code="feature_unsupported"):
        before = deepcopy(self.h.session.state)
        with self.assertRaises(C.ContractError) as caught:
            self.send(op, payload, credential)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.h.session.state, before)

    def test_both_entries_complete_chat_events_and_close_without_action_fixture(self):
        for entry in ("companion", "game"):
            with self.subTest(entry=entry):
                self.setUp()
                self.ready(entry)
                snapshot = self.send("session.snapshot", {"session_id": "s1"}, self.token)
                self.assertEqual(snapshot["definitions"], [])
                self.assertEqual(snapshot["actions"], [])
                self.assertEqual(set(snapshot["session"]["scope"]["features"]), {"core.session", "core.events"})
                message = {"version": "fixture-only", "session_id": "s1", "id": "chat-1", "type": "chat.message",
                    "sender": self.f["agent"], "audience": [self.f["agent"], self.f["player"]], "extensions": {},
                    "payload": {"channel": "private", "text": "最小会话", "source_refs": [], "provenance": []}}
                self.send("chat.send", message, self.token)
                self.assertTrue(self.send("chat.send", message, self.token)["duplicate"])
                page = self.send("session.events", {"session_id": "s1", "cursor": snapshot["cursor"], "page_size": 64}, self.token)
                self.assertEqual([e["envelope"]["type"] for e in page["events"]], ["chat.message"])
                self.send("session.heartbeat", {"session_id": "s1"}, self.token)
                self.assertEqual(self.send("session.close", {"session_id": "s1", "reason": "left"}, "player-fixture")["state"], "closed")
                self.assertEqual(self.h.session.action_model.model.world, {})

    def test_standalone_session_needs_no_action_definition(self):
        session = H.U.SessionHarness(self.f, {})
        self.assertEqual(session.state["definitions"], [])
        self.assertFalse(session.action_model.definition_available)

    def test_unnegotiated_action_operations_cannot_mutate_state(self):
        self.ready()
        envelope = {"version": "fixture-only", "session_id": "s1", "id": "a1", "type": "action.request",
            "sender": self.f["agent"], "audience": [self.f["agent"], self.f["player"]], "extensions": {},
            "expected_capabilities_revision": 1, "payload": {"action": "find-key", "arguments": {"room": "hall"}, "deadline": 30000}}
        self.deny("action.request", envelope, self.token)
        self.deny("action.query", {"session_id": "s1", "action_id": "a1"}, self.delivery["result_read_handle"])
        self.deny("capability.replace", {"instance": self.f["scope"]["instance"], "expected_revision": 1,
                                       "definitions": [self.definition]}, "game-fixture")

    def test_unnegotiated_control_operations_cannot_mutate_state(self):
        self.ready()
        self.deny("session.resume", {"session_id": "s1", "expected_generation": 1}, "agent-identity")
        self.deny("session.handoff", {"session_id": "s1", "expected_generation": 1, "target_device": "device-b",
                  "decision_ref": "missing", "target_proof_ref": "missing"}, "player-fixture")

    def test_join_before_commit_rolls_back_and_retry_reaches_ready(self):
        self.invitation()
        before = deepcopy(self.h.state)
        with self.assertRaises(H.U.S.H.InjectedFailure):
            self.join(fault="before_commit")
        self.assertIsNone(self.h.session)
        self.assertEqual(self.h.state, before)
        self.join()
        self.h.finish_admission(now=1000)
        self.assertEqual(self.join()["status"], "ready")

    def test_rich_descriptor_can_negotiate_down_to_core_without_action_fixture(self):
        rich = F.core_fixture()
        self.f["descriptor"] = rich["descriptor"]
        self.h = H.ControlHarness(self.f)
        self.ready()
        self.assertEqual(self.h.session.state["definitions"], [])
        self.assertFalse(self.h.session.action_model.definition_available)

    def test_negotiated_action_profile_still_requires_its_model_definition(self):
        for action_ids in (["find-key"], []):
            with self.subTest(action_ids=action_ids):
                rich = F.core_fixture()
                rich.pop("action")
                rich["scope"]["action_ids"] = action_ids
                with self.assertRaises(C.ContractError) as caught:
                    H.U.SessionHarness(rich, {})
                self.assertEqual(caught.exception.code, "invalid_arguments")


if __name__ == "__main__":
    unittest.main()
