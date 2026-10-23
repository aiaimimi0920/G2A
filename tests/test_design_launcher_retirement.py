"""独立 Launcher 不可逆退役与有界回收；旧快照不恢复派发权。"""

from copy import deepcopy
import unittest
import test_design_launch as T


class LauncherRetirementTests(unittest.TestCase):
    def setUp(self):
        self.case = T.LaunchTests(); self.case.setUp(); self.h = self.case.h

    def launched(self, outcome="started"):
        self.h.launcher.outcomes = [outcome]
        self.offer = self.case.approved()
        self.case.launch(self.offer)

    def exit_process(self):
        ref = next(iter(self.h.launcher.effects.values()))["process_ref"]
        self.h.launcher.record_exit(ref)

    def test_live_or_unobserved_process_cannot_be_retired(self):
        self.launched()
        self.case.error("temporarily_unavailable", lambda: self.h.retire_launcher(now=1000))
        self.h.launcher.running = None
        self.case.error("temporarily_unavailable", lambda: self.h.retire_launcher(now=1000))
        self.assertFalse(self.h.launcher.sealed)
        self.exit_process()
        self.assertEqual(self.h.retire_launcher(now=1000), {"sealed": True, "acknowledged": True})

    def test_unknown_and_dispatch_gap_block_retirement_even_without_process(self):
        for fault in ("after_accept", "after_dispatch"):
            with self.subTest(fault=fault):
                self.setUp(); offer = self.case.approved()
                with self.assertRaises(T.L.U.S.H.InjectedFailure):
                    self.case.launch(offer, fault=fault)
                self.case.error("temporarily_unavailable", lambda: self.h.retire_launcher(now=1000))
                self.assertFalse(self.h.launcher.sealed)
        self.setUp(); self.launched("unknown_after_effect"); self.exit_process()
        self.case.error("temporarily_unavailable", lambda: self.h.launcher.seal())
        self.case.error("temporarily_unavailable", lambda: self.h.retire_launcher(now=1000))

    def test_active_session_requires_independent_close_before_retirement(self):
        self.launched(); invitation = self.case.invite(self.offer)
        self.case.send("session.join", {key: invitation[key] for key in ("invitation_id", "join_intent")},
                       invitation["invitation_credential"])
        self.h.finish_admission(now=1000); self.exit_process()
        self.case.error("permission_denied", lambda: self.h.retire_launcher(now=1000))
        self.h.reconcile_application(now=1000)
        self.h.retire_launcher(now=1000)
        self.assertEqual(self.h.compact_retired_launcher(now=1000)["removed"], 1)
        self.assertEqual(self.h.reconcile_application(now=1000), {"process_state": "unknown", "session_state": "closed"})

    def test_seal_ack_fault_windows_and_restart_do_not_unseal(self):
        for fault in ("before_seal", "after_seal", "before_commit", "after_commit"):
            with self.subTest(fault=fault):
                self.setUp(); self.launched("failed")
                with self.assertRaises(T.L.U.S.H.InjectedFailure):
                    self.h.retire_launcher(now=1000, fault=fault)
                self.assertEqual(self.h.launcher.sealed, fault != "before_seal")
                self.assertEqual(self.h.state["launcher_retired"], fault == "after_commit")
                self.h = self.h.restart_from_mock_ledger(now=1000); self.case.h = self.h
                if fault != "after_commit":
                    self.case.error("permission_denied", lambda: self.h.compact_retired_launcher(now=1000))
                self.h.retire_launcher(now=1000)
                self.assertEqual(self.h.compact_retired_launcher(now=1000)["removed"], 1)

    def test_gc_preserves_authority_receipt_and_rejects_late_start_and_stale_snapshot(self):
        self.launched(); stale = deepcopy(self.h.launcher.running)
        other = self.case.create(rid="other-offer"); self.case.decide(other)
        authority_snapshot = deepcopy(self.h.state)
        self.exit_process(); self.h.retire_launcher(now=1000)
        self.assertEqual(self.h.compact_retired_launcher(now=1000), {"removed": 1, "remaining": 0, "sealed": True})
        self.assertEqual(self.h.launcher.effects, {}); self.assertEqual(self.h.launcher.exited, set())
        self.assertEqual(self.case.launch(self.offer)["result"], {"status": "started"})
        self.assertEqual(self.case.status()["state"], "done")
        self.case.error("temporarily_unavailable", lambda: self.h.launcher.start("new-permit", self.h.launcher.binding()))
        self.case.error("temporarily_unavailable", lambda: self.case.create(rid="new-offer"))
        self.h.launcher.running = stale
        self.assertFalse(self.h.launcher.available(self.h.launcher.binding()))
        self.h.state = authority_snapshot
        self.assertFalse(self.h.state["launcher_retired"])
        self.case.error("temporarily_unavailable", lambda: self.case.launch(other, rid="late-launch"))
        self.assertNotIn("late-launch", self.h.state["launch_records"])
        self.assertEqual(self.h.launcher.start_calls, 1)

    def test_budget_partial_gc_and_damaged_authority(self):
        port = self.h.launcher
        port.outcomes = ["failed", "failed"]
        port.start("one", port.binding()); port.start("two", port.binding())
        self.case.error("permission_denied", lambda: port.compact_sealed())
        self.h.retire_launcher(now=1000)
        for budget in (True, 0, 129, 1.5):
            self.case.error("invalid_arguments", lambda: self.h.compact_retired_launcher(now=1000, maximum=budget))
        self.assertEqual(self.h.compact_retired_launcher(now=1000, maximum=1)["remaining"], 1)
        self.h = self.h.restart_from_mock_ledger(now=1000)
        self.assertEqual(self.h.compact_retired_launcher(now=1000)["removed"], 1)
        self.assertEqual(self.h.compact_retired_launcher(now=1000)["removed"], 0)
        self.h = self.h.restart_from_mock_ledger(now=1000, intact=False)
        self.case.error("temporarily_unavailable", lambda: self.h.retire_launcher(now=1000))
        self.case.error("temporarily_unavailable", lambda: self.h.compact_retired_launcher(now=1000))


if __name__ == "__main__":
    unittest.main()
