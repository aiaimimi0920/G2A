"""恢复/转移的字节请求、固定身份和内存账本假端口；不证明真实设备或磁盘。"""

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


H = load("control_test", "control_harness.py")
F = load("control_fixture", "fixtures.py")
C = H.C


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.f = F.core_fixture(["core.session", "core.events", "actions", "resume", "handoff"])
        self.h = H.ControlHarness(self.f)
        self.h.identities["agent-b"] = {"role": "agent", "principal": self.f["agent"], "fresh": True,
                                        "device_id": "device-b", "expires_at": 300000}
        offer = self.send("offer.create", {"entry": "companion", "descriptor_id": "fixture-descriptor", "expected_descriptor_revision": 1,
                                          "requested": self.f["requested"]})
        decision = {"offer_id": offer["offer_id"], "scope_digest": offer["scope_digest"], "allow": True, "remember": False,
                    "launch_permission": False, "decision_ref": "approve-1"}
        self.h.decisions["approve-1"] = {"player": self.f["player"], "payload": decision}
        self.send("offer.decide", decision, "player-fixture")
        self.invitation = self.send("invitation.redeem", {"offer_id": offer["offer_id"], "join_intent": {"scope_digest": offer["scope_digest"]}})
        self.join_payload = {key: self.invitation[key] for key in ("invitation_id", "join_intent")}
        self.send("session.join", self.join_payload, self.invitation["invitation_credential"])
        self.h.finish_admission(now=1000)
        self.initial = self.send("session.join", self.join_payload, self.invitation["invitation_credential"])
        self.token = self.initial["control_credential"]

    def send(self, operation, payload, credential="agent-identity", rid="r1", now=1000, fault=None):
        request = F.wire_request(operation, payload, rid)
        return C.codec.decode(self.h.submit(C.codec.canonical(request), credential, now=now, fault=fault))["result"]

    def resume(self, generation=1, **kwargs):
        return self.send("session.resume", {"session_id": "s1", "expected_generation": generation}, **kwargs)

    def handoff_payload(self, generation=1):
        payload = {"session_id": "s1", "expected_generation": generation, "target_device": "device-b",
                   "decision_ref": "handoff-decision", "target_proof_ref": "target-proof"}
        digest = C.codec.digest("scope", self.h.session.state["session"]["scope"])
        self.h.decisions["handoff-decision"] = {"player": self.f["player"], "payload": deepcopy(payload), "scope_digest": digest}
        self.h.target_proofs["target-proof"] = {"agent": self.f["agent"], "device_id": "device-b", "session_id": "s1",
                                                "scope_digest": digest, "expires_at": 100000}
        return payload

    def handoff(self, generation=1, **kwargs):
        return self.send("session.handoff", self.handoff_payload(generation), "player-fixture", **kwargs)

    def claim(self, transfer, credential="agent-b", **kwargs):
        return self.send("session.claim_control", {"session_id": "s1", "transfer_id": transfer["transfer_id"], "target_device": "device-b"}, credential, **kwargs)

    def snapshot(self, token=None):
        return self.send("session.snapshot", {"session_id": "s1"}, token or self.token)

    def error(self, code, call):
        with self.assertRaises(C.ContractError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)

    def accept_claim_step(self):
        action = {"version": "fixture-only", "session_id": "s1", "id": "a1", "type": "action.request", "sender": self.f["agent"],
                  "audience": [self.f["player"]], "expected_capabilities_revision": 1, "extensions": {},
                  "payload": {"action": "find-key", "arguments": {"room": "hall"}, "deadline": 30000}}
        self.send("action.request", action, self.token)
        ticket = self.send("action.claim", {"session_id": "s1", "action_id": "a1", "worker": F.principal("worker-1", "service")}, "worker-1-fixture")["ticket"]
        self.h.execute("step", "worker-1", now=1000, ticket=ticket, step=1)
        return ticket

    def test_resume_rotates_once_preserves_lease_and_publishes_control_event(self):
        before = self.snapshot()
        result = self.resume()
        self.assertEqual(result["session"]["control_generation"], 2)
        self.assertEqual(result["session"]["lease_deadline"], before["session"]["lease_deadline"])
        self.assertEqual(self.resume(), result)
        self.error("generation_conflict", lambda: self.resume(rid="new-request"))
        self.error("stale_controller", lambda: self.snapshot())
        consumer = H.U.S.E.BusinessConsumer(before, self.f["agent"])
        page = self.send("session.events", {"session_id": "s1", "cursor": before["cursor"], "page_size": 64}, result["control_credential"])
        consumer.apply_page(page, before["cursor"])
        self.assertEqual(consumer.view["session"]["control_generation"], 2)
        self.assertEqual(page["events"][0]["envelope"]["type"], "session.control_changed")

    def test_resume_precommit_rollback_and_lost_reply_do_not_duplicate_rotation(self):
        before = deepcopy(self.h.session.state)
        with self.assertRaises(H.U.S.H.InjectedFailure):
            self.resume(fault="before_commit")
        self.assertEqual(self.h.session.state, before)
        self.assertEqual(self.h.state["transfers"], {})
        with self.assertRaises(H.U.S.H.InjectedFailure):
            self.resume(fault="after_commit")
        sequence = self.h.session.state["session"]["sequence"]
        self.assertEqual(self.resume()["session"]["control_generation"], 2)
        self.assertEqual(self.h.session.state["session"]["sequence"], sequence)

    def test_fresh_device_and_ledger_checks_apply_to_resume(self):
        self.h.identities["not-fresh"] = {**self.h.identities["agent-identity"], "fresh": False}
        self.error("unauthenticated", lambda: self.resume(credential="not-fresh"))
        self.error("permission_denied", lambda: self.resume(credential="agent-b"))
        self.error("handoff_required", lambda: self.send("session.resume", {"session_id": "s1", "expected_generation": 1, "device_id": "device-b"}))
        self.h.state["ledger_healthy"] = False
        self.error("resume_denied", lambda: self.resume())
        self.assertEqual(self.h.session.state["session"]["control_generation"], 1)

    def test_handoff_is_pending_until_target_ready_and_claim_requires_target(self):
        before = self.snapshot()
        transfer = self.handoff()
        self.assertEqual(transfer["status"], "acquiring")
        self.assertNotIn("control_credential", transfer)
        self.assertFalse(self.h.session.state["session"]["ready"])
        self.assertNotIn("controller_device", self.h.session.state["session"])
        self.error("session_not_writable", lambda: self.snapshot())
        self.error("permission_denied", lambda: self.claim(transfer, "agent-identity"))
        self.error("permission_denied", lambda: self.claim(transfer, "player-fixture"))
        self.assertEqual(self.claim(transfer)["status"], "pending")
        self.h.advance_transfer(transfer["transfer_id"], now=1000)
        result = self.claim(transfer)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["session"]["controller_device"], "device-b")
        consumer = H.U.S.E.BusinessConsumer(before, self.f["agent"])
        page = self.send("session.events", {"session_id": "s1", "cursor": before["cursor"], "page_size": 64}, result["control_credential"])
        consumer.apply_page(page, before["cursor"])
        self.assertEqual([e["envelope"]["type"] for e in page["events"]], ["session.control_changed", "session.ready"])
        self.assertEqual(consumer.view["session"]["controller_device"], "device-b")

    def test_handoff_requires_exact_player_decision_and_target_proof(self):
        payload = self.handoff_payload()
        for field in ("agent", "device_id", "scope_digest", "session_id", "expires_at"):
            proof = deepcopy(self.h.target_proofs["target-proof"])
            self.h.target_proofs["target-proof"][field] = 0 if field == "expires_at" else self.f["player"] if field == "agent" else "wrong"
            self.error("permission_denied", lambda: self.send("session.handoff", payload, "player-fixture"))
            self.h.target_proofs["target-proof"] = proof
        self.h.decisions["handoff-decision"]["scope_digest"] = "0" * 64
        self.error("consent_required", lambda: self.send("session.handoff", payload, "player-fixture"))
        self.assertEqual(self.h.session.state["session"]["control_generation"], 1)

    def test_handoff_commit_and_ready_faults_preserve_single_generation(self):
        with self.assertRaises(H.U.S.H.InjectedFailure):
            self.handoff(fault="before_commit")
        self.assertTrue(self.h.session.state["session"]["ready"])
        with self.assertRaises(H.U.S.H.InjectedFailure):
            self.handoff(fault="after_commit")
        transfer = self.handoff()
        with self.assertRaises(H.U.S.H.InjectedFailure):
            self.h.advance_transfer(transfer["transfer_id"], now=1000, fault="before_commit")
        self.assertEqual(self.claim(transfer)["status"], "pending")
        with self.assertRaises(H.U.S.H.InjectedFailure):
            self.h.advance_transfer(transfer["transfer_id"], now=1000, fault="after_commit")
        sequence = self.h.session.state["session"]["sequence"]
        self.h.advance_transfer(transfer["transfer_id"], now=1000)
        self.assertEqual(self.claim(transfer)["session"]["control_generation"], 2)
        self.assertEqual(self.h.session.state["session"]["sequence"], sequence)

    def test_failed_or_timed_out_transfer_closes_without_restoring_old_writer(self):
        for timeout in (False, True):
            self.setUp()
            transfer = self.handoff()
            now = transfer["deadline"] if timeout else 1000
            self.h.advance_transfer(transfer["transfer_id"], now=now, success=timeout)
            self.assertEqual(self.h.session.state["session"]["state"], "closed")
            self.assertEqual(self.h.session.state["session"]["control_generation"], 2)
            self.assertEqual(self.claim(transfer, now=now)["status"], "completed_without_secret")
            self.assertEqual(self.h.advance_transfer(transfer["transfer_id"], now=now)["status"], "failed")

    def test_old_resume_and_claim_receipts_do_not_replay_newer_generation_secrets(self):
        original = self.resume()
        transfer = self.handoff(2)
        self.assertEqual(self.resume()["status"], "completed_without_secret")
        self.h.advance_transfer(transfer["transfer_id"], now=1000)
        target = self.claim(transfer)
        next_resume = self.send("session.resume", {"session_id": "s1", "expected_generation": 3, "device_id": "device-b"}, "agent-b", rid="resume-b")
        self.assertEqual(next_resume["session"]["control_generation"], 4)
        self.assertEqual(self.claim(transfer)["status"], "completed_without_secret")
        self.assertNotEqual(original["control_credential"], target["control_credential"])

    def test_public_operation_status_is_subject_isolated_and_contains_no_secrets(self):
        transfer = self.handoff()
        lookup = {"operation": "session.handoff", "original_request_id": "r1"}
        view = self.send("operation.get", lookup, "player-fixture")
        self.assertEqual(view["state"], "pending")
        self.error("permission_denied", lambda: self.send("operation.get", lookup))
        self.h.advance_transfer(transfer["transfer_id"], now=1000)
        target = self.claim(transfer)
        view = self.send("operation.get", lookup, "player-fixture")
        self.assertEqual(view["state"], "done")
        self.assertNotIn(target["control_credential"].encode(), C.codec.canonical(view))
        self.assertNotIn(target["result_read_handle"].encode(), C.codec.canonical(view))

    def test_rotation_stops_old_effects_but_preserves_partial_fact_and_result_read(self):
        ticket = self.accept_claim_step()
        result = self.resume()
        with self.assertRaises(C.ContractError):
            self.h.execute("step", "worker-1", now=1000, ticket=ticket, step=2)
        self.h.execute("finish", "worker-1", now=1000, ticket=ticket)
        final = self.send("action.query", {"session_id": "s1", "action_id": "a1"}, self.initial["result_read_handle"])
        self.assertEqual((final["state"], final["effect"]), ("cancelled", "partial"))
        self.assertEqual(len(self.h.session.action_model.model.world), 1)
        self.assertEqual(self.snapshot(result["control_credential"])["actions"], [final])

    def test_mock_restart_changes_transport_and_preserves_action_and_control_receipts(self):
        ticket = self.accept_claim_step()
        old = self.h
        self.h = self.h.restart_from_mock_ledger(now=1000)
        self.error("resume_denied", lambda: old.submit(C.codec.canonical(F.wire_request("session.snapshot", {"session_id": "s1"})), self.token, now=1000))
        self.error("stale_transport", lambda: self.snapshot())
        self.error("stale_transport", lambda: self.h.execute("step", "worker-1", now=1000, ticket=ticket, step=2))
        self.assertEqual(self.send("session.join", self.join_payload, self.invitation["invitation_credential"])["status"], "completed_without_secret")
        result = self.resume()
        self.assertEqual(result["session"]["transport_epoch"], "transport-2")
        self.assertEqual(len(self.h.session.action_model.model.world), 1)
        self.h.execute("step", "worker-1", now=1000, ticket=ticket, step=1)
        self.assertEqual(len(self.h.session.action_model.model.world), 1)
        self.h = self.h.restart_from_mock_ledger(now=1000)
        self.assertEqual(self.resume()["status"], "completed_without_secret")
        self.assertEqual(self.resume(2, rid="after-second-restart")["session"]["control_generation"], 3)

    def test_mock_ledger_loss_refuses_resume_and_unverifiable_result_reads(self):
        self.accept_claim_step()
        self.h = self.h.restart_from_mock_ledger(now=1000, intact=False)
        self.error("resume_denied", lambda: self.resume())
        self.error("result_unavailable", lambda: self.send("action.query", {"session_id": "s1", "action_id": "a1"}, self.initial["result_read_handle"]))

    def test_restart_during_pending_transfer_fails_closed(self):
        transfer = self.handoff()
        self.h = self.h.restart_from_mock_ledger(now=1000)
        self.assertEqual(self.h.session.state["session"]["state"], "closed")
        self.assertEqual(self.claim(transfer)["status"], "completed_without_secret")

    def test_expired_fresh_identity_cannot_replay_a_cached_control_secret(self):
        self.resume()
        self.h.identities["agent-identity"]["expires_at"] = 1000
        self.error("unauthenticated", lambda: self.resume())

    def test_recovery_window_is_not_extended_by_heartbeat_or_old_receipt(self):
        deadline = self.h.session.state["session"]["resume_until"]
        self.send("session.heartbeat", {"session_id": "s1"}, self.token, now=100000)
        self.assertGreater(self.h.session.state["session"]["lease_deadline"], deadline)
        self.error("resume_denied", lambda: self.resume(now=deadline))

    def test_actual_competing_resumes_have_one_winner_and_no_extra_generation(self):
        for _ in range(6):
            self.setUp()
            barrier = Barrier(2)
            def resume(rid):
                barrier.wait(timeout=5)
                try:
                    return self.resume(rid=rid)["status"]
                except C.ContractError as error:
                    return error.code
            with ThreadPoolExecutor(max_workers=2) as pool:
                one, two = pool.submit(resume, "one"), pool.submit(resume, "two")
                results = [one.result(timeout=5), two.result(timeout=5)]
            self.assertCountEqual(results, ["ready", "generation_conflict"])
            self.assertEqual(self.h.session.state["session"]["control_generation"], 2)

    def test_resume_rejects_inconsistent_business_snapshot_without_rotation(self):
        self.h.session.state["definitions"][0]["revision"] += 1
        self.error("resume_denied", lambda: self.resume())
        self.assertEqual(self.h.session.state["session"]["control_generation"], 1)

    def test_resume_unresolved_actions_obey_current_result_read_revocation(self):
        self.accept_claim_step()
        self.send("permission.revoke", {"object_type": "result_read", "object_id": "s1", "expected_revision": 1}, "player-fixture")
        result = self.resume()
        self.assertEqual(result["unresolved_actions"], [])
        self.assertEqual(self.snapshot(result["control_credential"])["actions"], [])

    def test_actual_close_and_target_ready_race_never_reopens_session(self):
        for _ in range(6):
            self.setUp()
            transfer = self.handoff()
            barrier = Barrier(2)
            def advance():
                barrier.wait(timeout=5)
                return self.h.advance_transfer(transfer["transfer_id"], now=1000)
            def close():
                barrier.wait(timeout=5)
                return self.send("session.close", {"session_id": "s1", "reason": "left"}, "player-fixture")
            with ThreadPoolExecutor(max_workers=2) as pool:
                a, b = pool.submit(advance), pool.submit(close)
                a.result(timeout=5)
                b.result(timeout=5)
            self.assertEqual(self.h.session.state["session"]["state"], "closed")
            self.assertEqual(self.claim(transfer)["status"], "completed_without_secret")
            kinds = [event["wire"]["envelope"]["type"] for event in self.h.session.state["events"]]
            closed = kinds.index("session.closed")
            self.assertNotIn("session.ready", kinds[closed + 1:])

    def test_full_outbox_rotation_keeps_state_and_notices_atomic(self):
        self.accept_claim_step()
        while len(self.h.session.state["events"]) < 64:
            sequence = self.h.session.state["session"]["sequence"]
            self.send("context.publish", {"version": "fixture-only", "session_id": "s1", "id": "context-" + str(sequence),
                "type": "game.context", "sender": self.f["game"], "audience": [self.f["agent"]], "extensions": {},
                "payload": {"category": "room", "content": "hall", "provenance": []}}, "game-fixture")
        before = deepcopy(self.h.session.state)
        with self.assertRaises(H.U.S.H.InjectedFailure):
            self.resume(fault="before_commit")
        self.assertEqual(self.h.session.state, before)
        resumed = self.resume()
        self.assertEqual(self.h.session.state["events"][-1]["wire"]["envelope"]["type"], "session.control_changed")
        self.assertEqual(len(self.h.session.action_model.model.world), 1)
        self.assertGreater(self.h.session.state["event_floor"], 0)
        self.assertEqual(self.snapshot(resumed["control_credential"])["session"]["control_generation"], 2)


if __name__ == "__main__":
    unittest.main()
