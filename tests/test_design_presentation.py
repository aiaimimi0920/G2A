"""呈现假设备的独立提交、ACK、补偿与控制权字节链；不操作真实窗口。"""

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


P = load("test_presentation_harness", "presentation_harness.py")
F = load("test_presentation_fixture", "fixtures.py")
C = P.C


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.f = F.core_fixture(["core.session", "core.events", "actions", "resume", "handoff", "presentation"])
        self.f["requested"]["presentation_terms"] = {"mode": "hide_desktop", "device_id": "device-a"}
        self.h = P.PresentationHarness(self.f)
        self.observation = self.h.enroll_device("device-a")
        self.h.enroll_device("device-b")
        self.h.identities["agent-identity"]["device_id"] = "device-a"
        self.h.identities["agent-b"] = {**self.h.identities["agent-identity"], "device_id": "device-b"}
        self.offer = self.send("offer.create", {"entry": "companion", "descriptor_id": "fixture-descriptor", "expected_descriptor_revision": 1,
                                               "requested": self.f["requested"]})
        decision = {"offer_id": self.offer["offer_id"], "scope_digest": self.offer["scope_digest"], "allow": True, "remember": False,
                    "launch_permission": False, "decision_ref": "allow-presentation"}
        self.h.decisions[decision["decision_ref"]] = {"player": self.f["player"], "payload": decision}
        self.send("offer.decide", decision, "player-fixture")
        self.intent = {"scope_digest": self.offer["scope_digest"], "selected_device": "device-a", "presentation_observation": self.observation}

    def send(self, op, payload, credential="agent-identity", rid="r1", now=1000, fault=None):
        return C.codec.decode(self.h.submit(C.codec.canonical(F.wire_request(op, payload, rid)), credential, now=now, fault=fault))["result"]

    def error(self, code, call):
        with self.assertRaises(C.ContractError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)

    def join(self):
        self.invitation = self.send("invitation.redeem", {"offer_id": self.offer["offer_id"], "join_intent": self.intent})
        self.join_payload = {key: self.invitation[key] for key in ("invitation_id", "join_intent")}
        return self.retry_join()

    def retry_join(self, **kwargs):
        return self.send("session.join", self.join_payload, self.invitation["invitation_credential"], **kwargs)

    def job(self, jid="admission-s1"):
        return self.h.state["presentation_jobs"][jid]

    def acquire(self, jid="admission-s1", **kwargs):
        return self.send("presentation.acquire", deepcopy(self.job(jid)["acquire"]), "presentation-fixture", rid=jid, **kwargs)

    def release(self, jid="admission-s1", **kwargs):
        p = self.job(jid)["acquire"]
        return self.send("presentation.release", {key: p[key] for key in ("session_id", "generation", "device_id")},
                         "presentation-fixture", rid="release-" + jid, **kwargs)

    def ready(self):
        self.join()
        self.acquire()
        self.h.finish_admission(now=1000)
        self.token = self.retry_join()["control_credential"]
        return self.token

    def handoff(self, *, now=1000):
        session = self.h.session.state["session"]
        payload = {"session_id": "s1", "expected_generation": session["control_generation"], "target_device": "device-b",
                   "decision_ref": "move", "target_proof_ref": "target"}
        digest = C.codec.digest("scope", session["scope"])
        self.h.decisions["move"] = {"player": self.f["player"], "payload": payload, "scope_digest": digest}
        self.h.target_proofs["target"] = {"agent": self.f["agent"], "device_id": "device-b", "session_id": "s1",
                                          "scope_digest": digest, "expires_at": 300000}
        return self.send("session.handoff", payload, "player-fixture", now=now)

    def claim(self, transfer, **kwargs):
        return self.send("session.claim_control", {"session_id": "s1", "transfer_id": transfer["transfer_id"], "target_device": "device-b"},
                         "agent-b", **kwargs)

    def test_join_requires_verified_device_and_exact_observation(self):
        for field, value in (("selected_device", "device-b"), ("presentation_observation", {**self.observation, "baseline_visible": False})):
            intent = {**self.intent, field: value}
            self.error("permission_denied" if field == "selected_device" else "approval_stale",
                       lambda: self.send("invitation.redeem", {"offer_id": self.offer["offer_id"], "join_intent": intent}))
        self.assertIsNone(self.h.session)

    def test_join_rechecks_observation_after_invitation_issued(self):
        invitation = self.send("invitation.redeem", {"offer_id": self.offer["offer_id"], "join_intent": self.intent})
        self.h.devices["device-a"].manual_change(False, now=1000)
        self.error("approval_stale", lambda: self.send("session.join", {key: invitation[key] for key in ("invitation_id", "join_intent")},
                                                     invitation["invitation_credential"]))
        self.assertIsNone(self.h.session)

    def test_pending_join_requires_ack_before_secret_and_ready_event(self):
        self.assertEqual(self.join()["status"], "join_pending")
        self.assertFalse(self.h.finish_admission(now=1000)["ready"])
        self.assertEqual(self.h.session.state["session"]["sequence"], 0)
        receipt = self.acquire()
        C.validate_type("PresentationReceipt", receipt)
        self.assertTrue(receipt["applied"])
        self.assertFalse(receipt["actual_visible"])
        self.assertEqual(self.retry_join()["status"], "join_pending")
        self.h.finish_admission(now=1000)
        result = self.retry_join()
        self.assertEqual(result["session"]["controller_device"], "device-a")
        self.send("session.snapshot", {"session_id": "s1"}, result["control_credential"])
        self.assertEqual(result["session"]["sequence"], 1)

    def test_device_effect_survives_authority_precommit_failure_and_retry_is_once(self):
        self.join()
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.acquire(fault="before_commit")
        device = self.h.devices["device-a"]
        self.assertFalse(device.actual_visible)
        self.assertEqual(device.render_calls, 1)
        self.assertNotIn("acquire_ack", self.job())
        self.assertFalse(self.h.finish_admission(now=1000)["ready"])
        self.acquire()
        self.assertEqual(device.render_calls, 1)
        self.assertTrue(self.h.finish_admission(now=1000)["ready"])

    def test_lost_acquire_reply_replays_without_new_render_or_lease(self):
        self.join()
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.acquire(fault="after_commit")
        old = deepcopy(self.h.devices["device-a"].occupations)
        self.acquire(now=2000)
        self.assertEqual(self.h.devices["device-a"].render_calls, 1)
        self.assertEqual(self.h.devices["device-a"].occupations, old)

    def test_proof_terms_deadline_role_and_unknown_generation_are_rejected(self):
        self.join()
        p = self.job()["acquire"]
        for field, value in (("authority_proof_ref", "forged"), ("deadline", p["deadline"] + 1),
                             ("scope_digest", "0" * 64), ("terms", {"mode": "coexist", "device_id": "device-a"})):
            self.error("permission_denied", lambda: self.send("presentation.acquire", {**p, field: value}, "presentation-fixture", rid="admission-s1"))
        for credential in ("player-fixture", "game-fixture", "agent-identity"):
            self.error("permission_denied", lambda: self.send("presentation.acquire", p, credential, rid="admission-s1"))
        self.error("permission_denied", lambda: self.send("presentation.release", {"session_id": "s1", "generation": 88, "device_id": "device-a"}, "presentation-fixture"))
        self.assertEqual(self.h.devices["device-a"].render_calls, 0)

    def test_release_before_acquire_tombstones_even_without_original_ack(self):
        self.join()
        self.release()
        self.assertIn(("s1", 1), self.h.devices["device-a"].tombstones)
        self.error("grant_revoked", self.acquire)
        self.assertEqual(self.retry_join()["status"], "completed_without_secret")

    def test_renderer_failure_reports_actual_state_and_closes_without_false_restore(self):
        self.join()
        self.h.devices["device-a"].renderer_outcomes.append((False, False))
        receipt = self.acquire()
        self.assertFalse(receipt["applied"])
        self.assertFalse(receipt["actual_visible"])
        self.assertEqual(self.h.session.state["session"]["state"], "closed")
        self.assertTrue(self.job()["release_pending"])
        self.h.devices["device-a"].renderer_outcomes.append((False, False))
        release = self.release()
        self.assertFalse(release["applied"])
        self.assertFalse(release["actual_visible"])
        self.assertNotIn(("s1", 1), self.h.devices["device-a"].occupations)

    def test_close_queues_compensation_and_release_uses_latest_baseline(self):
        self.ready()
        device = self.h.devices["device-a"]
        device.manual_change(False, now=1000)
        self.send("session.close", {"session_id": "s1", "reason": "left"}, "player-fixture")
        self.assertTrue(self.job()["release_pending"])
        self.assertIn(("s1", 1), device.occupations)
        receipt = self.release()
        self.assertEqual(receipt["manual_revision"], 2)
        self.assertFalse(receipt["actual_visible"])
        self.assertTrue(receipt["applied"])

    def test_manual_show_prevents_late_acquire_before_or_after_original_effect(self):
        for applied in (False, True):
            self.setUp()
            self.join()
            if applied:
                with self.assertRaises(P.U.S.H.InjectedFailure):
                    self.acquire(fault="before_commit")
            device = self.h.devices["device-a"]
            device.manual_change(True, now=1000)
            self.error("grant_revoked", self.acquire)
            self.assertTrue(device.actual_visible)
            self.assertFalse(self.h.finish_admission(now=1000)["ready"])

    def test_handoff_requires_old_release_then_target_ack(self):
        self.ready()
        transfer = self.handoff()
        tid = transfer["transfer_id"]
        jid = self.h.state["transfers"][tid]["presentation_job"]
        self.assertEqual(transfer["status"], "releasing")
        self.assertEqual(self.claim(transfer)["status"], "pending")
        self.error("transfer_in_progress", lambda: self.acquire(jid))
        self.assertEqual(self.h.advance_transfer(tid, now=2000)["status"], "releasing")
        self.release(now=2000)
        self.assertEqual(self.h.advance_transfer(tid, now=2000)["status"], "acquiring")
        self.acquire(jid, now=2000)
        self.assertEqual(self.claim(transfer, now=2000)["status"], "pending")
        self.assertEqual(self.h.advance_transfer(tid, now=2000)["status"], "ready")
        result = self.claim(transfer, now=2000)
        self.assertEqual(result["session"]["controller_device"], "device-b")
        self.assertTrue(self.h.devices["device-a"].actual_visible)
        self.assertFalse(self.h.devices["device-b"].actual_visible)
        # 重试旧 release 不触碰新设备/新代占用。
        self.release(now=2000)
        self.assertIn(("s1", 2), self.h.devices["device-b"].occupations)

    def test_resume_rebind_is_pending_and_retries_do_not_rotate_again(self):
        self.ready()
        payload = {"session_id": "s1", "expected_generation": 1, "device_id": "device-a"}
        result = self.send("session.resume", payload)
        self.assertEqual(result["status"], "pending")
        tid = result["outcome_ref"]
        jid = self.h.state["transfers"][tid]["presentation_job"]
        self.release()
        self.h.advance_transfer(tid, now=1000)
        self.acquire(jid)
        self.h.advance_transfer(tid, now=1000)
        result = self.send("session.resume", payload)
        self.assertEqual(result["session"]["control_generation"], 2)
        self.assertEqual(result["session"]["sequence"], 3)
        self.assertEqual(len(self.h.state["transfers"]), 1)

    def test_target_effect_survives_lost_ack_then_close_compensates_both_generations(self):
        self.ready()
        transfer = self.handoff()
        tid = transfer["transfer_id"]
        jid = self.h.state["transfers"][tid]["presentation_job"]
        self.release()
        self.h.advance_transfer(tid, now=1000)
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.acquire(jid, fault="before_commit")
        self.send("session.close", {"session_id": "s1", "reason": "left"}, "player-fixture")
        self.assertFalse(self.job()["release_pending"])
        self.assertTrue(self.job(jid)["release_pending"])
        self.assertEqual(self.h.advance_transfer(tid, now=1000)["status"], "failed")
        self.assertEqual(self.claim(transfer)["status"], "completed_without_secret")
        self.release(jid)
        self.assertTrue(self.h.devices["device-b"].actual_visible)
        self.error("grant_revoked", lambda: self.acquire(jid))

    def test_heartbeat_cannot_silently_extend_device_occupation(self):
        self.ready()
        deadline = self.job()["acquire"]["deadline"]
        self.send("session.heartbeat", {"session_id": "s1"}, self.token, now=deadline - 1)
        self.assertGreater(self.h.session.state["session"]["lease_deadline"], deadline)
        self.h.finish_admission(now=deadline)
        self.assertTrue(self.h.devices["device-a"].actual_visible)
        self.assertEqual(self.h.session.state["session"]["state"], "closed")

    def test_transfer_timeout_does_not_assume_old_release_or_restore_old_writer(self):
        self.ready()
        transfer = self.handoff()
        self.h.advance_transfer(transfer["transfer_id"], now=transfer["deadline"])
        self.assertEqual(self.h.session.state["session"]["state"], "closed")
        self.assertEqual(self.h.session.state["session"]["control_generation"], 2)
        self.assertIn(("s1", 1), self.h.devices["device-a"].occupations)
        self.assertEqual(self.claim(transfer, now=transfer["deadline"])["status"], "completed_without_secret")

    def test_restart_keeps_independent_device_and_rebinds_without_old_ticket_authority(self):
        self.ready()
        device = self.h.devices["device-a"]
        self.h = self.h.restart_from_mock_ledger(now=1000)
        self.assertIs(self.h.devices["device-a"], device)
        result = self.send("session.resume", {"session_id": "s1", "expected_generation": 1, "device_id": "device-a"})
        self.assertEqual(result["status"], "pending")
        self.release()
        self.h.advance_transfer(result["outcome_ref"], now=1000)
        self.assertEqual(device.render_calls, 2)

    def test_local_operation_status_is_player_visible_and_does_not_contain_secrets(self):
        self.join()
        self.acquire()
        payload = {"operation": "presentation.acquire", "original_request_id": "admission-s1"}
        result = self.send("operation.get", payload, "player-fixture")
        self.assertEqual(result["state"], "done")
        self.assertNotIn("credential", str(result))
        self.error("permission_denied", lambda: self.send("operation.get", payload))

    def test_acquire_retry_after_transfer_ready_returns_original_receipt(self):
        self.ready()
        transfer = self.handoff()
        tid = transfer["transfer_id"]
        jid = self.h.state["transfers"][tid]["presentation_job"]
        self.release()
        self.h.advance_transfer(tid, now=1000)
        original = self.acquire(jid)
        self.h.advance_transfer(tid, now=1000)
        self.assertEqual(self.acquire(jid), original)
        self.assertEqual(self.h.devices["device-b"].render_calls, 1)

    def test_expired_old_occupation_with_renderer_failure_cannot_open_target(self):
        self.ready()
        deadline = self.job()["acquire"]["deadline"]
        self.send("session.heartbeat", {"session_id": "s1"}, self.token, now=deadline - 2)
        # 旧占用即将到期，但会话租约仍有效；不能把 Renderer 失败当作成功释放。
        transfer = self.handoff(now=deadline - 1)
        self.h.devices["device-a"].renderer_outcomes.append((False, False))
        result = self.h.advance_transfer(transfer["transfer_id"], now=deadline)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.h.session.state["session"]["state"], "closed")

    def test_release_ack_loss_waits_for_exact_retry_not_device_side_guess(self):
        self.ready()
        transfer = self.handoff()
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.release(fault="before_commit")
        self.assertTrue(self.h.devices["device-a"].actual_visible)
        self.assertEqual(self.h.advance_transfer(transfer["transfer_id"], now=1000)["status"], "releasing")
        self.release()
        self.assertEqual(self.h.advance_transfer(transfer["transfer_id"], now=1000)["status"], "acquiring")
        self.assertEqual(self.h.devices["device-a"].render_calls, 2)

    def test_verified_local_expiry_can_replace_missing_release_ack(self):
        self.ready()
        deadline = self.job()["acquire"]["deadline"]
        self.send("session.heartbeat", {"session_id": "s1"}, self.token, now=deadline - 2)
        transfer = self.handoff(now=deadline - 1)
        self.assertEqual(self.h.advance_transfer(transfer["transfer_id"], now=deadline)["status"], "acquiring")
        self.assertNotIn("release_ack", self.job())
        self.assertTrue(self.h.devices["device-a"].actual_visible)

    def test_revocation_commit_boundary_and_release_compensation_are_atomic(self):
        self.ready()
        payload = {"object_type": "grant", "object_id": "grant-1", "expected_revision": 1}
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.send("permission.revoke", payload, "player-fixture", fault="before_commit")
        self.assertTrue(self.h.session.state["session"]["ready"])
        self.assertFalse(self.job()["release_pending"])
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.send("permission.revoke", payload, "player-fixture", fault="after_commit")
        self.assertTrue(self.job()["release_pending"])
        self.assertFalse(self.h.devices["device-a"].actual_visible)
        self.release()
        self.assertTrue(self.h.devices["device-a"].actual_visible)

    def test_coexist_does_not_override_manual_visibility(self):
        self.f["requested"]["presentation_terms"]["mode"] = "coexist"
        # 独立新 offer；已批准的旧 Scope 不被改写。
        self.offer = self.send("offer.create", {"entry": "companion", "descriptor_id": "fixture-descriptor", "expected_descriptor_revision": 1,
                                               "requested": self.f["requested"]}, rid="coexist")
        decision = {"offer_id": self.offer["offer_id"], "scope_digest": self.offer["scope_digest"], "allow": True, "remember": False,
                    "launch_permission": False, "decision_ref": "coexist"}
        self.h.decisions["coexist"] = {"player": self.f["player"], "payload": decision}
        self.send("offer.decide", decision, "player-fixture", rid="coexist")
        self.intent["scope_digest"] = self.offer["scope_digest"]
        self.ready()
        device = self.h.devices["device-a"]
        self.assertTrue(device.actual_visible)
        device.manual_change(False, now=1000)
        self.send("session.snapshot", {"session_id": "s1"}, self.token)
        self.assertTrue(self.h.session.state["session"]["ready"])
        self.assertFalse(self.release()["actual_visible"])

    def test_core_profile_is_not_forced_to_enroll_or_apply_presentation(self):
        self.h = P.PresentationHarness(F.core_fixture())
        offer = self.send("offer.create", {"entry": "companion", "descriptor_id": "fixture-descriptor", "expected_descriptor_revision": 1,
                                          "requested": F.core_fixture()["requested"]})
        self.assertNotIn("presentation", offer["immutable_scope"]["features"])
        self.assertNotIn("presentation_terms", offer["immutable_scope"])
        self.assertEqual(self.h.devices, {})

    def test_close_and_acquire_race_never_returns_ready_or_revives_tombstone(self):
        for _ in range(6):
            self.setUp()
            self.join()
            barrier = Barrier(2)
            def acquire():
                barrier.wait()
                try:
                    return self.acquire()
                except C.ContractError as error:
                    return error.code
            def close():
                barrier.wait()
                return self.send("session.close", {"session_id": "s1", "reason": "left"}, "player-fixture")
            with ThreadPoolExecutor(max_workers=2) as pool:
                a, b = pool.submit(acquire), pool.submit(close)
                a.result(timeout=5), b.result(timeout=5)
            self.release()
            self.assertFalse(self.h.finish_admission(now=1000)["ready"])
            self.error("grant_revoked", self.acquire)
            self.assertTrue(self.h.devices["device-a"].actual_visible)


if __name__ == "__main__":
    unittest.main()
