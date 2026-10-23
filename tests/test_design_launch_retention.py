"""启动回执有界回收与独立消费屏障；不清理真实进程或磁盘。"""

from copy import deepcopy
import unittest
import test_design_launch as T


class LaunchRetentionTests(unittest.TestCase):
    def setUp(self):
        self.case = T.LaunchTests(); self.case.setUp(); self.h = self.case.h
        self.case.f["requested"]["limits"]["receipt_retention_ms"] = 100
        self.case.f["requested"]["maximum_grant_duration_ms"] = 100

    def start(self, outcome="started", rid="r1"):
        self.h.launcher.outcomes = [outcome]
        offer = self.case.create(rid="offer-" + rid)
        self.case.decide(offer)
        self.case.launch(offer, rid=rid)
        return offer

    def test_boundary_retry_and_consumed_permit_block_reacceptance(self):
        offer = self.start()
        self.assertEqual(self.h.state["launch_records"]["r1"]["gc_after"], 1100)
        self.case.launch(offer, now=1099)
        self.assertEqual(self.h.compact_launch_receipts(now=1099)["removed"], 0)
        self.assertEqual(self.h.compact_launch_receipts(now=1100), {"removed": 1, "remaining": 0})
        self.case.error("request_gone", lambda: self.case.launch(offer, now=1100))
        with self.assertRaises(T.C.ContractError):
            self.case.launch(offer, rid="new-id", now=1100)
        self.case.error("permission_denied", lambda: self.case.status(now=1100))
        self.assertEqual(self.h.launcher.start_calls, 1)
        self.assertEqual(len(self.h.launcher.effects), 1)

    def test_pending_is_not_age_based_garbage_and_can_still_settle(self):
        self.start("unknown_after_effect")
        self.assertEqual(self.h.compact_launch_receipts(now=1100)["removed"], 0)
        self.assertEqual(self.case.status(now=1100)["state"], "pending")
        ref = self.h.state["launch_records"]["r1"]["payload"]["launch_permission_ref"]
        self.assertTrue(self.h.launcher.verify_existing_effect(ref))
        self.assertEqual(self.case.status(now=1100)["state"], "done")
        self.assertEqual(self.h.compact_launch_receipts(now=1100)["removed"], 1)
        self.assertEqual(self.h.launcher.start_calls, 1)

    def test_process_and_binding_survive_natural_session_expiry_and_receipt_gc(self):
        offer = self.start(); invitation = self.case.invite(offer)
        self.case.send("session.join", {key: invitation[key] for key in ("invitation_id", "join_intent")},
                       invitation["invitation_credential"])
        self.h.finish_admission(now=1000)
        process = deepcopy(self.h.state["admission_process"])
        effects = deepcopy(self.h.launcher.effects)
        self.assertEqual(self.h.compact_launch_receipts(now=1100)["removed"], 1)
        self.assertEqual(self.h.session.state["session"]["state"], "closed")
        self.assertTrue(self.h.launcher.available(self.h.launcher.binding()))
        self.assertEqual(self.h.state["admission_process"], process)
        self.assertEqual(self.h.launcher.effects, effects)
        self.h.launcher.record_exit(process["process_ref"])
        self.assertEqual(self.h.reconcile_application(now=1100)["session_state"], "closed")

    def test_budget_failed_records_and_independent_effects(self):
        self.start("failed", "r1"); self.start("failed", "r2")
        entries = deepcopy(self.h.launcher.entries)
        self.assertEqual(self.h.compact_launch_receipts(now=1100, maximum=1), {"removed": 1, "remaining": 1})
        self.assertEqual(self.h.compact_launch_receipts(now=1100, maximum=1), {"removed": 1, "remaining": 0})
        self.assertEqual(self.h.compact_launch_receipts(now=1100)["removed"], 0)
        self.assertEqual(self.h.launcher.entries, entries)
        self.assertEqual(len(self.h.state["launch_permits"]), 2)

    def test_commit_faults_restart_preserve_consumption(self):
        for fault in ("before_commit", "after_commit"):
            with self.subTest(fault=fault):
                self.setUp(); offer = self.start()
                with self.assertRaises(T.L.U.S.H.InjectedFailure):
                    self.h.compact_launch_receipts(now=1100, fault=fault)
                self.h = self.h.restart_from_mock_ledger(now=1100); self.case.h = self.h
                self.assertEqual(len(self.h.state["launch_records"]), 1 if fault == "before_commit" else 0)
                self.h.compact_launch_receipts(now=1100)
                self.case.error("request_gone", lambda: self.case.launch(offer, now=1100))
                self.assertEqual(self.h.launcher.start_calls, 1)

    def test_invalid_budget_unhealthy_or_missing_barrier_refuses_gc(self):
        self.start()
        for budget in (True, 0, 129, 1.5):
            self.case.error("invalid_arguments", lambda: self.h.compact_launch_receipts(now=1100, maximum=budget))
        permit = next(iter(self.h.state["launch_permits"].values()))
        permit["request_id"] = None
        self.case.error("temporarily_unavailable", lambda: self.h.compact_launch_receipts(now=1100))
        self.assertEqual(len(self.h.state["launch_records"]), 1)
        self.h = self.h.restart_from_mock_ledger(now=1100, intact=False)
        self.case.error("temporarily_unavailable", lambda: self.h.compact_launch_receipts(now=1100))

    def test_missing_historical_deadline_is_not_invented_and_changed_request_cannot_reuse_id(self):
        offer = self.start()
        record = self.h.state["launch_records"]["r1"]
        deadline = record.pop("gc_after")
        self.assertEqual(self.h.compact_launch_receipts(now=1100)["removed"], 0)
        self.h.state["launch_records"]["r1"]["gc_after"] = deadline
        self.assertEqual(self.h.compact_launch_receipts(now=1100)["removed"], 1)
        payload = self.case.payload(offer)
        payload["launch_permission_ref"] = "another-permission"
        self.case.error("request_gone", lambda: self.case.send("launch.request", payload, now=1100))
        self.assertEqual(self.h.launcher.start_calls, 1)


if __name__ == "__main__":
    unittest.main()
