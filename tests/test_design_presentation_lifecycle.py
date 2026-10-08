"""设备租约、独立重启与补偿调度的反例；只使用可信内存夹具。"""

from copy import deepcopy
import importlib.util
from itertools import permutations
from pathlib import Path
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("lifecycle_presentation_cases", Path(__file__).with_name("test_design_presentation.py"))
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)
C, P = BASE.C, BASE.P


class PresentationLifecycleTests(unittest.TestCase):
    def setUp(self):
        # 复用已有准入/转移夹具，不重复继承并统计其历史测试。
        self.case = BASE.PresentationTests()
        self.case.setUp()

    @property
    def h(self):
        return self.case.h

    def queue(self, now=2000, *, rid=None, fault=None):
        self.case.send("session.heartbeat", {"session_id": "s1"}, self.case.token,
                       rid=rid or "heartbeat-" + str(now), now=now, fault=fault)
        return self.case.job()["renewal_id"]

    def renew(self, rid=None, *, now=2000, fault=None):
        rid = rid or self.case.job()["renewal_id"]
        return self.case.send("presentation.renew", deepcopy(self.h.state["presentation_renewals"][rid]["payload"]),
                              "presentation-fixture", rid=rid, now=now, fault=fault)

    def close(self, now=1000):
        return self.case.send("session.close", {"session_id": "s1", "reason": "left"}, "player-fixture", now=now)

    def status(self, operation, rid, *, now=2000, credential="player-fixture"):
        return self.case.send("operation.get", {"operation": operation, "original_request_id": rid}, credential, now=now)

    def test_renew_is_an_explicit_local_authority_operation(self):
        self.assertIn("presentation.renew", C.catalog.OPERATIONS)
        self.assertIn("presentation.renew", self.h.WIRE_OPERATIONS)

    def test_heartbeat_commits_a_revisioned_intent_without_touching_device(self):
        self.case.ready()
        original = deepcopy(self.h.devices["device-a"].occupations)
        self.case.send("session.heartbeat", {"session_id": "s1"}, self.case.token, now=2000)
        self.assertEqual(self.h.devices["device-a"].occupations, original)
        renewals = self.h.state["presentation_renewals"]
        self.assertEqual(len(renewals), 1)
        self.assertEqual(next(iter(renewals.values()))["payload"]["lease_revision"], 2)

    def test_device_restart_is_distinct_and_invalidates_old_observation(self):
        original = self.h.devices["device-a"]
        self.h.restart_device("device-a", now=1000)
        self.assertIsNot(self.h.devices["device-a"], original)
        self.case.error("approval_stale", self.case.join)

    def test_background_compensation_restores_closed_session(self):
        self.case.ready()
        self.case.send("session.close", {"session_id": "s1", "reason": "left"}, "player-fixture")
        self.h.sweep_presentation(now=1000, budget=1)
        self.assertFalse(self.case.job()["release_pending"])
        self.assertTrue(self.h.devices["device-a"].actual_visible)

    def test_receipts_report_effective_revision_epoch_and_no_lease_after_release(self):
        self.case.join()
        acquired = self.case.acquire()
        self.assertEqual((acquired["device_epoch"], acquired["lease_revision"], acquired["lease_deadline"]),
                         (1, 1, self.case.job()["acquire"]["deadline"]))
        released = self.case.release()
        self.assertEqual((released["device_epoch"], released["lease_revision"], released["lease_deadline"]), (1, 1, 0))
        C.validate_type("PresentationReceipt", released)

    def test_heartbeat_intent_rolls_back_or_replays_with_its_game_lease(self):
        self.case.ready()
        original = self.h.session.state["session"]["lease_deadline"]
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.queue(fault="before_commit")
        self.assertEqual(self.h.state["presentation_renewals"], {})
        self.assertEqual(self.h.session.state["session"]["lease_deadline"], original)
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.queue(rid="kept-heartbeat", fault="after_commit")
        deadline = self.h.session.state["session"]["lease_deadline"]
        self.queue(3000, rid="kept-heartbeat")
        self.assertEqual(len(self.h.state["presentation_renewals"]), 1)
        self.assertEqual(self.h.session.state["session"]["lease_deadline"], deadline)

    def test_applied_renewal_survives_original_deadline_without_rerender(self):
        self.case.ready()
        old_deadline = self.case.job()["acquire"]["deadline"]
        rid = self.queue()
        game_lease = self.h.session.state["session"]["lease_deadline"]
        receipt = self.renew(rid)
        self.assertEqual(receipt["lease_deadline"], game_lease)
        self.assertEqual(receipt["lease_revision"], 2)
        self.assertEqual(self.renew(rid, now=3000), receipt)
        self.assertEqual(self.h.devices["device-a"].render_calls, 1)
        self.assertEqual(self.h.session.state["session"]["lease_deadline"], game_lease)
        self.assertTrue(self.h.finish_admission(now=old_deadline)["ready"])
        self.assertFalse(self.h.devices["device-a"].actual_visible)
        self.assertEqual(self.case.job()["acquire"]["deadline"], old_deadline)

    def test_renewal_effect_precedes_ack_and_exact_retry_recovers(self):
        for fault in ("before_commit", "after_commit"):
            with self.subTest(fault=fault):
                self.setUp()
                self.case.ready()
                rid = self.queue()
                with self.assertRaises(P.U.S.H.InjectedFailure):
                    self.renew(rid, fault=fault)
                device = self.h.devices["device-a"]
                self.assertEqual(device.occupations[("s1", 1)]["lease_revision"], 2)
                self.assertEqual(self.case.job()["lease_ack"]["lease_revision"], 1 if fault == "before_commit" else 2)
                self.renew(rid, now=3000)
                self.assertEqual(self.case.job()["lease_ack"]["lease_revision"], 2)
                self.assertEqual(device.render_calls, 1)
                self.assertEqual(len(self.h.state["presentation_jobs"]), 1)

    def test_stale_unapplied_revision_is_rejected_but_historical_receipt_cannot_downgrade(self):
        self.case.ready()
        stale = self.queue()
        newer = self.queue(3000)
        self.case.error("approval_stale", lambda: self.renew(stale, now=3000))
        historical = self.renew(newer, now=3000)
        newest = self.queue(4000)
        current = self.renew(newest, now=4000)
        self.assertEqual(self.renew(newer, now=4000), historical)
        self.assertEqual(self.case.job()["lease_ack"], current)
        self.assertEqual(self.h.devices["device-a"].occupations[("s1", 1)]["lease_revision"], 4)

    def test_renewal_proof_content_role_and_id_are_not_self_asserted(self):
        self.case.ready()
        rid = self.queue()
        payload = deepcopy(self.h.state["presentation_renewals"][rid]["payload"])
        for field, value in (("deadline", payload["deadline"] + 1), ("scope_digest", "0" * 64),
                             ("authority_proof_ref", "forged"), ("lease_revision", 9),
                             ("terms", {"mode": "coexist", "device_id": "device-a"})):
            self.case.error("permission_denied", lambda: self.case.send("presentation.renew", {**payload, field: value},
                            "presentation-fixture", rid=rid, now=2000))
        for role in ("agent-identity", "game-fixture", "player-fixture"):
            self.case.error("permission_denied", lambda: self.case.send("presentation.renew", payload, role, rid=rid, now=2000))
        self.renew(rid)
        self.case.error("id_conflict", lambda: self.case.send("presentation.renew", {**payload, "deadline": payload["deadline"] + 1},
                        "presentation-fixture", rid=rid, now=2000))

    def test_read_only_and_rejected_requests_do_not_issue_lease_updates(self):
        self.case.ready()
        self.case.send("session.snapshot", {"session_id": "s1"}, self.case.token, now=2000)
        self.case.error("unauthenticated", lambda: self.case.send("session.heartbeat", {"session_id": "s1"}, "bad-token", now=2000))
        self.assertEqual(self.h.state["presentation_renewals"], {})
        state = self.h.session.state["session"]
        cursor = {"session_id": "s1", "instance_epoch": state["instance_epoch"], "sequence": 0}
        self.case.send("session.events", {"session_id": "s1", "cursor": cursor, "page_size": 64}, self.case.token, now=2000)
        self.assertEqual(len(self.h.state["presentation_renewals"]), 1)

    def test_expired_occupation_is_not_revived_by_an_unapplied_newer_proof(self):
        self.case.ready()
        old_deadline = self.case.job()["acquire"]["deadline"]
        rid = self.queue(old_deadline - 1)
        with self.assertRaises(C.ContractError):
            self.renew(rid, now=old_deadline)
        self.assertIn(("s1", 1), self.h.devices["device-a"].tombstones)
        self.assertEqual(self.h.session.state["session"]["state"], "closed")
        self.assertTrue(self.h.devices["device-a"].actual_visible)

    def test_manual_show_and_revoke_stop_pending_renewals(self):
        for stop in ("manual", "revoke"):
            with self.subTest(stop=stop):
                self.setUp()
                self.case.ready()
                rid = self.queue()
                if stop == "manual":
                    self.h.devices["device-a"].manual_change(True, now=2000)
                else:
                    self.case.send("permission.revoke", {"object_type": "grant", "object_id": "grant-1", "expected_revision": 1},
                                   "player-fixture", now=2000)
                with self.assertRaises(C.ContractError):
                    self.renew(rid)
                self.h.sweep_presentation(now=2000)
                self.assertEqual(self.h.devices["device-a"].occupations, {})
                self.assertNotEqual(self.h.state["presentation_renewals"][rid]["state"], "pending")

    def test_transfer_cannot_use_original_deadline_after_unknown_newer_effect(self):
        self.case.ready()
        deadline = self.case.job()["acquire"]["deadline"]
        rid = self.queue(deadline - 2)
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.renew(rid, now=deadline - 2, fault="before_commit")
        transfer = self.case.handoff(now=deadline - 1)
        self.assertEqual(self.h.advance_transfer(transfer["transfer_id"], now=deadline)["status"], "releasing")
        self.assertNotIn("release_evidence", self.case.job())
        self.assertIn(("s1", 1), self.h.devices["device-a"].occupations)
        self.case.release(now=deadline)
        self.assertEqual(self.h.advance_transfer(transfer["transfer_id"], now=deadline)["status"], "acquiring")

    def test_verified_expiry_tombstone_fences_even_unapplied_higher_revision(self):
        self.case.ready()
        deadline = self.case.job()["acquire"]["deadline"]
        rid = self.queue(deadline - 2)
        transfer = self.case.handoff(now=deadline - 1)
        self.assertEqual(self.h.advance_transfer(transfer["transfer_id"], now=deadline)["status"], "acquiring")
        proof = self.case.job()["release_evidence"]
        self.assertGreater(proof["proof_deadline"], proof["verified_at"])
        self.assertIn(("s1", 1), self.h.devices["device-a"].tombstones)
        with self.assertRaises(C.ContractError):
            self.renew(rid, now=deadline)

    def test_unconfirmed_renewal_does_not_keep_current_writer_past_acknowledged_deadline(self):
        self.case.ready()
        deadline = self.case.job()["acquire"]["deadline"]
        rid = self.queue(deadline - 2)
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.renew(rid, now=deadline - 2, fault="before_commit")
        self.h.finish_admission(now=deadline)
        self.assertEqual(self.h.session.state["session"]["state"], "closed")
        self.assertFalse(self.h.devices["device-a"].actual_visible)
        self.h.sweep_presentation(now=deadline)
        self.assertTrue(self.h.devices["device-a"].actual_visible)

    def test_device_restart_revalidates_without_extending_and_next_update_uses_new_epoch(self):
        self.case.ready()
        rid = self.queue()
        receipt = self.renew(rid)
        original = self.h.devices["device-a"]
        report = self.h.restart_device("device-a", now=2000)
        self.assertEqual(report["kept_occupations"], 1)
        self.assertTrue(original.retired)
        self.case.error("presentation_unavailable", lambda: original.manual_change(True, now=2000))
        self.assertEqual(self.case.job()["lease_ack"]["lease_deadline"], receipt["lease_deadline"])
        self.assertEqual(self.case.job()["lease_ack"]["device_epoch"], 2)
        self.case.error("approval_stale", lambda: self.renew(rid))
        fresh = self.queue(3000)
        self.assertEqual(self.renew(fresh, now=3000)["device_epoch"], 2)

    def test_repeated_device_restarts_preserve_latest_manual_baseline(self):
        self.case.ready()
        self.h.devices["device-a"].manual_change(False, now=1000)
        self.h.restart_device("device-a", now=1000)
        report = self.h.restart_device("device-a", now=1000)
        self.assertEqual((report["observation"]["device_epoch"], report["observation"]["manual_revision"]), (3, 2))
        self.assertFalse(report["observation"]["baseline_visible"])
        self.assertEqual(report["kept_occupations"], 1)
        self.assertFalse(self.case.release()["actual_visible"])

    def test_unavailable_or_unhealthy_authority_cannot_retain_saved_occupation(self):
        for available, healthy in ((False, True), (True, False)):
            with self.subTest(available=available, healthy=healthy):
                self.setUp()
                self.case.ready()
                self.h.state["ledger_healthy"] = healthy
                report = self.h.restart_device("device-a", now=1000, authority_available=available)
                self.assertEqual(report["kept_occupations"], 0)
                self.assertIn(("s1", 1), self.h.devices["device-a"].tombstones)
                self.assertEqual(self.h.session.state["session"]["state"], "closed")
                self.assertTrue(report["actual_visible"])

    def test_restart_drops_old_generation_without_opening_target_from_guessed_ack(self):
        self.case.ready()
        transfer = self.case.handoff()
        self.assertEqual(self.h.restart_device("device-a", now=1000)["kept_occupations"], 0)
        self.assertEqual(self.h.advance_transfer(transfer["transfer_id"], now=1000)["status"], "releasing")
        self.h.sweep_presentation(now=1000, budget=1)
        self.assertEqual(self.h.advance_transfer(transfer["transfer_id"], now=1000)["status"], "acquiring")

    def test_restart_freshly_verifies_unknown_acquire_instead_of_replaying_old_epoch(self):
        self.case.join()
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.case.acquire(fault="before_commit")
        self.h.restart_device("device-a", now=2000)
        self.assertNotIn("acquire_ack", self.case.job())
        self.assertEqual(self.case.job()["lease_ack"]["device_epoch"], 2)
        self.assertTrue(self.h.finish_admission(now=2000)["ready"])
        self.case.error("approval_stale", lambda: self.case.acquire(now=2000))

    def test_restart_keeps_unknown_renewal_by_fresh_proof_without_fabricating_original_ack(self):
        self.case.ready()
        rid = self.queue()
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.renew(rid, fault="before_commit")
        self.h.restart_device("device-a", now=2000)
        self.assertNotIn(("presentation.renew", rid), self.h.state["presentation_receipts"])
        self.assertEqual(self.h.state["presentation_renewals"][rid]["state"], "verified")
        self.assertEqual(self.status("presentation.renew", rid)["state"], "done")
        self.assertEqual(self.h.sweep_presentation(now=2000)["attempted"], [])

    def test_restart_reissues_unapplied_pending_update_with_higher_revision_new_epoch(self):
        self.case.ready()
        stale = self.queue()
        self.h.restart_device("device-a", now=2000)
        fresh = self.case.job()["renewal_id"]
        self.assertNotEqual(stale, fresh)
        self.assertEqual(self.h.state["presentation_renewals"][stale]["state"], "superseded")
        receipt = self.renew(fresh)
        self.assertEqual((receipt["lease_revision"], receipt["device_epoch"]), (3, 2))

    def test_renderer_failure_during_restart_never_claims_recovery(self):
        self.case.ready()
        self.h.devices["device-a"].renderer_outcomes.append((False, False))
        report = self.h.restart_device("device-a", now=1000)
        self.assertFalse(report["applied"])
        self.assertFalse(report["actual_visible"])
        self.assertEqual(self.h.session.state["session"]["state"], "closed")
        self.assertTrue(self.case.job()["release_pending"])
        self.h.sweep_presentation(now=1000)
        self.assertTrue(self.h.devices["device-a"].actual_visible)

    def test_lost_restart_ack_does_not_restore_retired_device_or_trust_old_epoch(self):
        self.case.ready()
        original = self.h.devices["device-a"]
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.h.restart_device("device-a", now=1000, fault="before_commit")
        self.assertIsNot(self.h.devices["device-a"], original)
        self.assertTrue(original.retired)
        self.assertEqual(self.case.job()["device_epoch"], 1)
        self.assertFalse(self.h.finish_admission(now=1000)["ready"])
        self.h.sweep_presentation(now=1000)
        self.assertFalse(self.case.job()["release_pending"])

    def test_authority_restart_preserves_pending_revision_and_independent_effect(self):
        self.case.ready()
        rid = self.queue()
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.renew(rid, fault="before_commit")
        device = self.h.devices["device-a"]
        self.case.h = self.h.restart_from_mock_ledger(now=2000)
        self.assertIs(self.h.devices["device-a"], device)
        self.renew(rid)
        self.assertEqual(len(self.h.state["presentation_renewals"]), 1)
        self.assertEqual(device.occupations[("s1", 1)]["lease_revision"], 2)

    def test_background_worker_dispatches_only_latest_pending_renewal(self):
        self.case.ready()
        stale = self.queue()
        current = self.queue(3000)
        result = self.h.sweep_presentation(now=3000, budget=1)
        self.assertEqual(result["attempted"][0]["request_id"], current)
        self.assertEqual(result["pending_renewals"], 0)
        self.assertNotIn(("presentation.renew", stale), self.h.devices["device-a"].receipts)
        self.assertEqual(self.h.devices["device-a"].render_calls, 1)

    def test_compensation_unknown_ack_retries_original_id_after_authority_restart(self):
        self.case.ready()
        self.close()
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.h.sweep_presentation(now=1000, fault="before_commit")
        original_id = self.case.job()["release_attempt"]
        calls = self.h.devices["device-a"].render_calls
        self.assertNotIn("release_ack", self.case.job())
        self.case.h = self.h.restart_from_mock_ledger(now=1000)
        report = self.h.sweep_presentation(now=1000)
        self.assertEqual(report["attempted"][0]["request_id"], original_id)
        self.assertEqual(self.h.devices["device-a"].render_calls, calls)
        self.assertEqual(report["pending_releases"], 0)

    def test_compensation_postcommit_loss_does_not_repeat_renderer(self):
        self.case.ready()
        self.close()
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.h.sweep_presentation(now=1000, fault="after_commit")
        self.assertEqual(self.h.sweep_presentation(now=1000)["attempted"], [])
        self.assertEqual(self.h.devices["device-a"].render_calls, 2)

    def test_known_renderer_failure_waits_then_uses_new_id_and_old_failure_cannot_downgrade(self):
        self.case.ready()
        self.close()
        self.h.devices["device-a"].renderer_outcomes.append((False, False))
        first = self.h.sweep_presentation(now=1000)["attempted"][0]
        self.assertTrue(self.case.job()["release_pending"])
        self.assertEqual(self.h.sweep_presentation(now=1000)["attempted"], [])
        second = self.h.sweep_presentation(now=2000)["attempted"][0]
        self.assertNotEqual(first["request_id"], second["request_id"])
        self.assertFalse(self.case.job()["release_pending"])
        payload = {key: self.case.job()["acquire"][key] for key in ("session_id", "generation", "device_id")}
        historical = self.case.send("presentation.release", payload, "presentation-fixture", rid=first["request_id"], now=2000)
        self.assertFalse(historical["applied"])
        self.assertFalse(self.case.job()["release_pending"])

    def test_offline_timeout_and_clock_expiry_alone_never_finish_compensation(self):
        self.case.ready()
        self.close()
        device = self.h.devices["device-a"]
        device.reachable = False
        self.assertEqual(self.h.sweep_presentation(now=1000)["pending_releases"], 1)
        deadline = self.case.job()["lease"]["deadline"]
        report = self.h.sweep_presentation(now=deadline)
        self.assertTrue(device.actual_visible)  # 夹具知道本地时钟已恢复，不代表远端收到证明。
        self.assertEqual(report["pending_releases"], 1)
        self.assertNotIn("release_evidence", self.case.job())
        device.reachable = True
        report = self.h.sweep_presentation(now=deadline + 1000)
        self.assertEqual(report["attempted"][0]["outcome"], "verified_expiry")
        self.assertEqual(report["pending_releases"], 0)
        self.assertEqual(device.render_calls, 2)

    def test_normal_receipt_exhaustion_preserves_release_reserve(self):
        self.case.ready()
        for i in range(255):
            key = ("presentation.renew", "fixture-padding-" + str(i))
            self.h.state["presentation_receipts"][key] = {"fixture_padding": True}
            self.h.devices["device-a"].receipts[key] = {"fixture_padding": True}
        self.close()
        self.assertEqual(self.h.sweep_presentation(now=1000)["pending_releases"], 0)
        self.assertTrue(self.h.devices["device-a"].actual_visible)

    def test_bounded_worker_rotates_past_offline_generation_and_prioritizes_stops(self):
        self.case.ready()
        self.queue()
        self.case.handoff(now=2000)
        self.close(now=2000)
        self.h.devices["device-a"].reachable = False
        first = self.h.sweep_presentation(now=2000, budget=1)
        second = self.h.sweep_presentation(now=2000, budget=1)
        self.assertEqual(len(first["attempted"]), 1)
        self.assertEqual(len(second["attempted"]), 1)
        self.assertNotEqual(first["attempted"][0]["job_id"], second["attempted"][0]["job_id"])
        self.assertEqual(second["pending_releases"], 1)
        self.assertEqual(second["pending_renewals"], 0)

    def test_pending_operation_views_are_player_only_and_contain_no_secrets(self):
        self.case.join()
        self.assertEqual(self.status("presentation.acquire", "admission-s1", now=1000)["state"], "pending")
        self.case.acquire()
        self.h.finish_admission(now=1000)
        self.case.token = self.case.retry_join()["control_credential"]
        rid = self.queue()
        self.assertEqual(self.status("presentation.renew", rid)["state"], "pending")
        self.case.error("permission_denied", lambda: self.status("presentation.renew", rid, credential="agent-identity"))
        self.renew(rid)
        status = self.status("presentation.renew", rid)
        self.assertEqual(status["state"], "done")
        self.assertNotIn("credential", str(status))
        self.assertNotIn("authority_proof", str(status))

    def test_invalid_worker_budget_and_clock_regression_do_not_mutate_effects(self):
        self.case.ready()
        self.queue()
        device = self.h.devices["device-a"]
        original = deepcopy(device.occupations)
        for budget in (True, 0, 33):
            self.case.error("invalid_arguments", lambda: self.h.sweep_presentation(now=2000, budget=budget))
        self.case.error("temporarily_unavailable", lambda: self.h.sweep_presentation(now=1999))
        self.assertEqual(device.occupations, original)

    def test_release_tombstone_survives_reboot_and_stale_success_is_not_new_epoch_evidence(self):
        self.case.ready()
        self.case.release()
        self.h.restart_device("device-a", now=1000)
        self.assertIn(("s1", 1), self.h.devices["device-a"].tombstones)
        historical = self.case.release()
        self.assertEqual(historical["device_epoch"], 1)
        self.assertTrue(self.case.job()["release_pending"])
        self.h.sweep_presentation(now=1000)
        self.assertFalse(self.case.job()["release_pending"])
        self.assertEqual(self.case.job()["release_ack"]["device_epoch"], 2)

    def test_exhausted_stop_receipts_do_not_prevent_later_local_recovery(self):
        self.case.ready()
        self.close()
        device = self.h.devices["device-a"]
        # 缩小同一容量门，保留两次真实失败回执；不伪造成功或删除旧回执。
        with patch.object(P.D.PresentationDevice, "RELEASE_RECEIPTS", 2):
            device.renderer_outcomes.extend([(False, False), (False, False)])
            self.h.sweep_presentation(now=1000)
            self.h.sweep_presentation(now=2000)
            receipts = deepcopy(device.receipts)
            device.reachable = False
            self.assertEqual(self.h.sweep_presentation(now=3000)["pending_releases"], 1)
            device.reachable = True
            result = self.h.sweep_presentation(now=4000)
            self.assertEqual(result["pending_releases"], 0)
            self.assertTrue(device.actual_visible)
            self.assertEqual(device.receipts, receipts)
            self.assertEqual(self.case.job()["release_evidence"]["kind"], "local_reconciliation")
            self.assertFalse(self.case.job()["release_ack"]["applied"])

    def test_device_can_reconcile_stop_after_all_128_receipts_are_used(self):
        self.case.ready()
        device = self.h.devices["device-a"]
        payload = {"session_id": "s1", "generation": 1, "device_id": "device-a"}
        device.renderer_outcomes.extend([(False, False)] * device.RELEASE_RECEIPTS)
        for number in range(device.RELEASE_RECEIPTS):
            device.apply("presentation.release", payload, "failed-" + str(number), "digest-" + str(number), now=1000)
        self.assertFalse(device.render_verified)
        evidence = device.reconcile_stop(payload, now=1000)
        self.assertTrue(evidence["receipt"]["applied"])
        self.assertEqual(len(device.receipts), device.RELEASE_RECEIPTS + 1)
        self.assertTrue(device.actual_visible)

    def test_local_reconciliation_lost_ack_preserves_effect_without_rerender(self):
        for fault in ("before_commit", "after_commit"):
            with self.subTest(fault=fault):
                self.setUp()
                self.case.ready()
                self.close()
                device = self.h.devices["device-a"]
                with patch.object(P.D.PresentationDevice, "RELEASE_RECEIPTS", 1):
                    device.renderer_outcomes.append((False, False))
                    self.h.sweep_presentation(now=1000)
                    with self.assertRaises(P.U.S.H.InjectedFailure):
                        self.h.sweep_presentation(now=2000, fault=fault)
                    self.assertTrue(device.actual_visible)
                    calls = device.render_calls
                    self.assertEqual(self.h.sweep_presentation(now=2000)["pending_releases"], 0)
                    self.assertEqual(device.render_calls, calls)

    def test_superseding_or_closing_unknown_renewal_does_not_claim_effect_failed(self):
        self.case.ready()
        rid = self.queue()
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.renew(rid, fault="before_commit")
        self.queue(3000)
        self.assertEqual(self.status("presentation.renew", rid, now=3000)["state"], "pending")
        self.close(3000)
        self.assertEqual(self.status("presentation.renew", rid, now=3000)["state"], "pending")
        self.assertEqual(self.h.devices["device-a"].occupations[("s1", 1)]["lease_revision"], 2)

    def test_renew_close_restart_orders_never_resurrect_occupation(self):
        for order in permutations(("renew", "close", "restart")):
            with self.subTest(order=order):
                self.setUp()
                self.case.ready()
                rid = self.queue()
                for step in order:
                    if step == "renew":
                        try:
                            self.renew(rid)
                        except C.ContractError:
                            pass
                    elif step == "close":
                        self.close(2000)
                    else:
                        self.h.restart_device("device-a", now=2000)
                self.h.sweep_presentation(now=2000)
                self.assertEqual(self.h.devices["device-a"].occupations, {})
                self.assertTrue(self.h.devices["device-a"].actual_visible)
                self.assertFalse(self.h.session.state["session"]["ready"])


if __name__ == "__main__":
    unittest.main()
