"""动作字节链与 outbox 同事务，以及外部效果不可回滚的组合验证。"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import importlib.util
from pathlib import Path
from threading import Barrier
import unittest


ROOT = Path(__file__).resolve().parents[1] / "docs/protocol"


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


U = load("unified_session_test", "session_harness.py")
F = load("unified_session_fixture", "fixtures.py")
C = U.C


class SessionHarnessTests(unittest.TestCase):
    def setUp(self):
        self.f = F.core_fixture()
        self.h = U.SessionHarness(self.f, {})
        self.request = F.wire_request("action.request", {"version": "fixture-only", "session_id": "s1",
            "id": "a1", "type": "action.request", "sender": self.f["agent"], "audience": [self.f["player"]],
            "expected_capabilities_revision": 1, "extensions": {},
            "payload": {"action": "find-key", "arguments": {"room": "hall"}, "deadline": 30000}})

    def send(self, request, credential="agent-fixture", fault=None, now=1000):
        return C.codec.decode(self.h.submit(C.codec.canonical(request), credential, now=now, fault=fault))

    def snapshot(self):
        return self.send(F.wire_request("session.snapshot", {"session_id": "s1"}))["result"]

    def claim(self):
        request = F.wire_request("action.claim", {"session_id": "s1", "action_id": "a1",
                                 "worker": F.principal("worker-1", "service")}, "claim-1")
        return self.send(request, "worker-1-fixture")["result"]["ticket"]

    def report(self, ticket):
        return F.wire_request("action.commit_result", {"ticket": ticket, "fact": {
            "state": "succeeded", "effect": "committed", "result": {"item": "gold-key"},
            "steps": [{"step": n, "effect": "committed", "evidence_ref": ticket["proof_ref"] + "-step-" + str(n)}
                      for n in (1, 2)]}}, "commit-1")

    def complete_steps(self, ticket):
        for step in (1, 2):
            self.h.execute("step", "worker-1", now=1000, ticket=ticket, step=step)

    def fill_outbox(self):
        while len(self.h.state["events"]) < 64:
            number = self.h.state["session"]["sequence"]
            request = F.wire_request("context.publish", {"version": "fixture-only", "session_id": "s1",
                "id": "c" + str(number), "type": "game.context", "sender": self.f["game"],
                "audience": [self.f["agent"]], "payload": {"category": "room", "content": "hall", "provenance": []}, "extensions": {}})
            self.send(request, "game-fixture")

    def test_action_request_to_query_snapshot_and_events_without_import_port(self):
        consumer = U.S.E.BusinessConsumer(self.snapshot(), self.f["agent"])
        self.send(self.request)
        ticket = self.claim()
        self.complete_steps(ticket)
        final = self.send(self.report(ticket), "worker-1-fixture")["result"]
        snapshot = self.snapshot()
        self.assertEqual(snapshot["actions"], [final])
        self.assertEqual(snapshot["cursor"]["sequence"], 5)
        poll = F.wire_request("session.events", {"session_id": "s1", "cursor": consumer.stream.cursor, "page_size": 64}, "poll-1")
        page = self.send(poll)["result"]
        consumer.apply_page(page, deepcopy(consumer.stream.cursor))
        self.assertEqual(consumer.view["results"].results["a1"], final)
        self.assertEqual(len(self.h.action_model.model.world), 2)
        self.assertFalse(self.h.pending_sync)

    def test_accept_and_claim_before_commit_restore_action_and_outbox(self):
        before = deepcopy(self.h.state)
        with self.assertRaises(U.S.H.InjectedFailure):
            self.send(self.request, fault="before_commit")
        self.assertEqual(self.h.state, before)
        self.assertIsNone(self.h.action_model.model.action)
        self.send(self.request)
        before = deepcopy(self.h.state)
        request = F.wire_request("action.claim", {"session_id": "s1", "action_id": "a1",
                                 "worker": F.principal("worker-1", "service")}, "claim-1")
        with self.assertRaises(U.S.H.InjectedFailure):
            self.send(request, "worker-1-fixture", fault="before_commit")
        self.assertEqual(self.h.state, before)
        self.assertEqual(self.h.action_model.model.action["state"], "pending")
        self.assertIsNone(self.h.action_model.wire_ticket)

    def test_result_commit_rollback_does_not_roll_back_prior_world_effects(self):
        self.send(self.request)
        ticket = self.claim()
        self.complete_steps(ticket)
        before = deepcopy(self.h.state)
        with self.assertRaises(U.S.H.InjectedFailure):
            self.send(self.report(ticket), "worker-1-fixture", fault="before_commit")
        self.assertEqual(self.h.state, before)
        self.assertEqual(self.h.action_model.model.action["state"], "executing")
        self.assertEqual(len(self.h.action_model.model.world), 2)
        self.assertIsNone(self.h.action_model.committed_fact)
        self.send(self.report(ticket), "worker-1-fixture")
        self.assertEqual(self.snapshot()["actions"][0]["known_result"], {"item": "gold-key"})

    def test_lost_reply_retries_neither_reexecute_nor_duplicate_event(self):
        with self.assertRaises(U.S.H.InjectedFailure):
            self.send(self.request, fault="after_commit")
        self.assertTrue(self.send(self.request)["result"]["duplicate"])
        ticket = self.claim()
        self.complete_steps(ticket)
        with self.assertRaises(U.S.H.InjectedFailure):
            self.send(self.report(ticket), "worker-1-fixture", fault="after_commit")
        sequence = self.h.state["session"]["sequence"]
        self.send(self.report(ticket), "worker-1-fixture")
        self.h.execute("step", "worker-1", now=1000, ticket=ticket, step=1)
        self.assertEqual(self.h.state["session"]["sequence"], sequence)
        self.assertEqual(len(self.h.action_model.model.world), 2)

    def test_full_outbox_rejects_accept_and_effect_before_they_happen(self):
        self.fill_outbox()
        with self.assertRaises(C.ContractError):
            self.send(self.request)
        self.assertIsNone(self.h.action_model.model.action)
        self.h.compact_through(self.h.state["session"]["sequence"])
        self.send(self.request)
        ticket = self.claim()
        self.fill_outbox()
        with self.assertRaises(C.ContractError):
            self.h.execute("step", "worker-1", now=1000, ticket=ticket, step=1)
        self.assertEqual(self.h.action_model.model.world, {})
        self.assertEqual(self.h.action_model.model.action["consumed"], set())

    def test_after_effect_publish_failure_preserves_fact_and_repairs_before_read(self):
        self.send(self.request)
        ticket = self.claim()
        with self.assertRaises(U.S.H.InjectedFailure):
            self.h.execute("step", "worker-1", now=1000, ticket=ticket, step=1, publish_fault="before_commit")
        self.assertEqual(len(self.h.action_model.model.world), 1)
        self.assertTrue(self.h.pending_sync)
        snapshot = self.snapshot()
        self.assertEqual(snapshot["actions"][0]["effect"], "partial")
        self.assertFalse(self.h.pending_sync)
        sequence = snapshot["cursor"]["sequence"]
        self.h.execute("step", "worker-1", now=1000, ticket=ticket, step=1)
        self.assertEqual(self.h.state["session"]["sequence"], sequence)
        self.assertEqual(len(self.h.action_model.model.world), 1)

    def test_consumed_unknown_is_in_snapshot_and_outbox_without_reexecution(self):
        self.send(self.request)
        ticket = self.claim()
        with self.assertRaises(U.A.M.SimulatedCrash):
            self.h.execute("step", "worker-1", now=1000, ticket=ticket, step=1, crash="after_effect")
        self.assertEqual(self.snapshot()["actions"][0]["state"], "unknown")
        self.assertEqual(len(self.h.action_model.model.world), 1)
        self.h.execute("reconcile", "worker-1", now=1000, ticket=ticket)
        self.assertEqual(self.snapshot()["actions"][0]["effect"], "partial")
        self.assertEqual(len(self.h.action_model.model.world), 1)

    def test_shared_message_namespace_rejects_chat_action_id_collision(self):
        chat = F.wire_request("chat.send", {"version": "fixture-only", "session_id": "s1", "id": "a1",
            "type": "chat.message", "sender": self.f["agent"], "audience": [self.f["player"]], "extensions": {},
            "payload": {"channel": "private", "text": "hello", "source_refs": [], "provenance": []}})
        for action_first in (False, True):
            self.setUp()
            self.send(self.request if action_first else chat)
            before = deepcopy(self.h.state)
            with self.assertRaises(C.ContractError) as caught:
                self.send(chat if action_first else self.request)
            self.assertEqual(caught.exception.code, "id_conflict")
            self.assertEqual(self.h.state, before)
            self.assertEqual(self.h.action_model.model.action is None, not action_first)

    def test_actual_accept_snapshot_race_has_no_orphan_action_or_event(self):
        for _ in range(8):
            self.setUp()
            barrier = Barrier(2)
            def accept():
                barrier.wait(timeout=5)
                return self.send(self.request)
            def snapshot():
                barrier.wait(timeout=5)
                return self.snapshot()
            with ThreadPoolExecutor(max_workers=2) as pool:
                writer, reader = pool.submit(accept), pool.submit(snapshot)
                writer.result(timeout=5)
                result = reader.result(timeout=5)
            self.assertIn((result["cursor"]["sequence"], len(result["actions"])), {(0, 0), (1, 1)})

    def control(self, operation, payload, credential="game-fixture", request_id="control-1", **kwargs):
        return self.send(F.wire_request(operation, payload, request_id), credential, **kwargs)

    def test_removed_capability_cannot_accept_a_first_action(self):
        self.control("capability.replace", {"instance": self.f["scope"]["instance"], "expected_revision": 1, "definitions": []})
        self.request["payload"]["expected_capabilities_revision"] = 2
        with self.assertRaises(C.ContractError):
            self.send(self.request)
        self.assertIsNone(self.h.action_model.model.action)

    def test_result_read_revocation_before_accept_also_filters_future_events(self):
        self.control("permission.revoke", {"object_type": "result_read", "object_id": "s1", "expected_revision": 1}, "player-fixture")
        self.send(self.request)
        self.assertEqual(self.snapshot()["actions"], [])
        with self.assertRaises(C.ContractError):
            self.control("action.query", {"session_id": "s1", "action_id": "a1"}, "agent-fixture")

    def test_close_at_full_outbox_is_atomic_and_preserves_partial_world_fact(self):
        self.send(self.request)
        ticket = self.claim()
        self.h.execute("step", "worker-1", now=1000, ticket=ticket, step=1)
        self.fill_outbox()
        result = self.control("session.close", {"session_id": "s1", "reason": "left"}, "player-fixture")["result"]
        self.assertEqual(result["state"], "closed")
        self.assertGreater(self.h.state["event_floor"], 0)
        self.assertEqual(len(self.h.action_model.model.world), 1)
        with self.assertRaises(C.ContractError):
            self.h.execute("step", "worker-1", now=1001, ticket=ticket, step=2)
        self.h.execute("finish", "worker-1", now=1001, ticket=ticket)
        final = self.control("action.query", {"session_id": "s1", "action_id": "a1"}, "agent-fixture")["result"]
        self.assertEqual((final["state"], final["effect"]), ("cancelled", "partial"))

    def test_heartbeat_retry_does_not_renew_and_revoke_prevents_replay(self):
        heartbeat = F.wire_request("session.heartbeat", {"session_id": "s1"}, "heartbeat-1")
        self.send(heartbeat, now=1000)
        lease = self.h.state["session"]["lease_deadline"]
        self.send(heartbeat, now=2000)
        self.assertEqual(self.h.state["session"]["lease_deadline"], lease)
        self.control("permission.revoke", {"object_type": "grant", "object_id": "g1", "expected_revision": 1}, "player-fixture")
        with self.assertRaises(C.ContractError):
            self.send(heartbeat, now=2001)

    def test_capability_change_stops_existing_action_without_expanding_approval(self):
        self.send(self.request)
        ticket = self.claim()
        changed = deepcopy(self.f["action"])
        changed["maximum_duration_ms"] = 99999
        self.control("capability.replace", {"instance": self.f["scope"]["instance"], "expected_revision": 1, "definitions": [changed]})
        self.assertEqual(self.snapshot()["definitions"], [])
        with self.assertRaises((C.ContractError, U.A.M.Rejected)):
            self.h.execute("step", "worker-1", now=1000, ticket=ticket, step=1)
        self.assertEqual(self.h.action_model.model.world, {})

    def test_membership_proof_cas_and_rejoin_generation_are_atomic(self):
        first = {"instance": self.f["scope"]["instance"], "expected_revision": 1,
                 "verified_members": [self.f["player"]], "membership_proof_ref": "proof-1"}
        with self.assertRaises(C.ContractError):
            self.control("membership.replace", first)
        self.assertEqual(self.h.state["session"]["membership_revision"], 1)
        self.h.membership_proofs["proof-1"] = deepcopy(first)
        self.control("membership.replace", first)
        self.assertNotIn(U.R.principal_key(self.f["agent"]), self.h.members)
        second = {"instance": self.f["scope"]["instance"], "expected_revision": 2,
                  "verified_members": [self.f["player"], self.f["agent"]], "membership_proof_ref": "proof-2"}
        self.h.membership_proofs["proof-2"] = deepcopy(second)
        self.control("membership.replace", second, request_id="control-2")
        self.assertEqual(self.h.members[U.R.principal_key(self.f["agent"])], 2)
        self.assertEqual(self.snapshot()["session"]["membership_revision"], 3)

    def test_close_failure_rolls_back_grant_action_history_compaction_and_receipt(self):
        self.send(self.request)
        self.fill_outbox()
        before = deepcopy(self.h.state)
        with self.assertRaises(U.S.H.InjectedFailure):
            self.control("session.close", {"session_id": "s1", "reason": "left"}, "player-fixture", fault="before_commit")
        self.assertEqual(self.h.state, before)
        self.assertEqual(self.h.action_model.model.action["state"], "pending")
        with self.assertRaises(U.S.H.InjectedFailure):
            self.control("session.close", {"session_id": "s1", "reason": "left"}, "player-fixture", fault="after_commit")
        sequence = self.h.state["session"]["sequence"]
        self.control("session.close", {"session_id": "s1", "reason": "left"}, "player-fixture")
        self.assertEqual(self.h.state["session"]["sequence"], sequence)

    def test_action_uses_presented_credential_not_another_current_credential(self):
        current = self.h.credentials["agent-fixture"]
        for field, stale in (("generation", 2), ("transport_epoch", "old-transport"), ("device_id", "other-device")):
            self.h.credentials["stale-agent"] = {**current, field: stale}
            with self.subTest(field=field), self.assertRaises(C.ContractError):
                self.send(self.request, "stale-agent")
            self.assertIsNone(self.h.action_model.model.action)
        self.send(self.request)

    def test_cancel_has_a_reserved_slot_in_shared_message_receipts(self):
        self.send(self.request)
        # 直接构造容量边界；不冒充 256 次网络提交的验证。
        self.h.state["receipts"].update({("fixture", "saturation", str(n)): {} for n in range(255)})
        cancel = F.wire_request("action.cancel", {"version": "fixture-only", "session_id": "s1",
            "id": "cancel-1", "type": "action.cancel", "sender": self.f["agent"],
            "audience": [self.f["player"]], "payload": {"request_id": "a1"}, "extensions": {}})
        self.send(cancel)
        self.assertEqual(self.h.action_model.model.action["state"], "cancelled")
        self.assertEqual(len(self.h.state["receipts"]), 257)

    def test_result_commit_has_a_reserved_control_receipt_slot(self):
        self.send(self.request)
        ticket = self.claim()
        self.complete_steps(ticket)
        self.h.action_model.control_receipts.update({("fixture", "saturation", str(n)): {} for n in range(63)})
        final = self.send(self.report(ticket), "worker-1-fixture")["result"]
        self.assertEqual(final["known_result"], {"item": "gold-key"})
        self.assertEqual(len(self.h.action_model.control_receipts), 65)


if __name__ == "__main__":
    unittest.main()
