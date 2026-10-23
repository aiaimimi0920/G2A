"""精确进程退出与历史启动事实分离；可信假观察，不运行进程。"""

from copy import deepcopy
import unittest
from unittest.mock import patch
import test_design_launch as T

L, C = T.L, T.C


class LaunchMonitorTests(unittest.TestCase):
    def start(self, *, ready=True):
        self.case = T.LaunchTests(); self.case.setUp(); self.h = self.case.h
        self.offer = self.case.approved(); self.case.launch(self.offer)
        self.invitation = self.case.invite(self.offer)
        self.join = {key: self.invitation[key] for key in ("invitation_id", "join_intent")}
        self.case.send("session.join", self.join, self.invitation["invitation_credential"])
        self.process = self.h.state["admission_process"]["process_ref"]
        if ready:
            self.h.finish_admission(now=1000)

    def test_known_exit_closes_session_without_erasing_launch_effect(self):
        self.start()
        self.h.launcher.record_exit(self.process)
        self.assertEqual(self.h.reconcile_application(now=1000), {"process_state": "exited", "session_state": "closed"})
        sequence = self.h.session.state["session"]["sequence"]
        self.h.reconcile_application(now=1000)
        self.assertEqual(self.h.session.state["session"]["sequence"], sequence)
        self.assertEqual(self.case.launch(self.offer)["result"], {"status": "started"})
        self.assertEqual(self.h.launcher.start_calls, 1)
        self.assertEqual(len(self.h.launcher.effects), 1)

    def test_missing_malformed_or_failed_observation_does_not_prove_exit(self):
        self.start()
        self.h.launcher.running = None
        before = deepcopy(self.h.session.state)
        self.assertEqual(self.h.reconcile_application(now=1000)["process_state"], "unknown")
        for value in (None, {}, [], True, "stopped"):
            with patch.object(self.h.launcher, "observe_process", return_value=value):
                self.assertEqual(self.h.reconcile_application(now=1000)["process_state"], "unknown")
        with patch.object(self.h.launcher, "observe_process", side_effect=RuntimeError("observer unavailable")):
            self.assertEqual(self.h.reconcile_application(now=1000)["process_state"], "unknown")
        self.assertEqual(self.h.session.state, before)

    def test_exit_commit_faults_restart_and_retry_preserve_independent_fact(self):
        for fault in ("before_commit", "after_commit"):
            with self.subTest(fault=fault):
                self.start(); self.h.launcher.record_exit(self.process)
                with self.assertRaises(L.U.S.H.InjectedFailure):
                    self.h.reconcile_application(now=1000, fault=fault)
                self.h = self.h.restart_from_mock_ledger(now=1000)
                self.assertIn(self.process, self.h.launcher.exited)
                self.assertEqual(self.h.session.state["session"]["state"], "active" if fault == "before_commit" else "closed")
                self.assertEqual(self.h.reconcile_application(now=1000)["session_state"], "closed")
                self.assertEqual(self.h.launcher.start_calls, 1)

    def test_unrelated_or_late_exit_does_not_clear_new_process(self):
        self.start()
        self.case.error("permission_denied", lambda: self.h.launcher.record_exit("unknown-process"))
        self.assertTrue(self.h.launcher.available(self.h.launcher.binding()))
        self.h.launcher.record_exit(self.process)
        self.h.launcher.start("independent-new-permit", self.h.launcher.binding())
        new_process = deepcopy(self.h.launcher.running)
        self.h.launcher.record_exit(self.process)
        self.assertEqual(self.h.launcher.running, new_process)
        self.assertEqual(self.h.reconcile_application(now=1000)["session_state"], "closed")

    def test_replacement_process_cannot_complete_old_admission(self):
        self.start(ready=False)
        self.h.launcher.record_exit(self.process)
        self.h.launcher.start("new-process", self.h.launcher.binding())
        self.assertTrue(self.h.launcher.available(self.h.launcher.binding()))
        self.assertEqual(self.h.finish_admission(now=1000)["state"], "closed")
        result = self.case.send("session.join", self.join, self.invitation["invitation_credential"])
        self.assertEqual(result["status"], "completed_without_secret")

    def test_unbound_legacy_running_fixture_does_not_invent_exit_identity(self):
        self.case = T.LaunchTests(); self.case.setUp(); self.h = self.case.h
        self.h.launcher.running = {"binding": self.h.launcher.binding(), "verified": True}
        offer = self.case.create(entry="companion"); self.case.decide(offer, permission=False)
        invitation = self.case.invite(offer)
        self.case.send("session.join", {key: invitation[key] for key in ("invitation_id", "join_intent")}, invitation["invitation_credential"])
        self.h.finish_admission(now=1000)
        self.assertIsNone(self.h.state["admission_process"])
        self.assertEqual(self.h.reconcile_application(now=1000), {"process_state": "unknown", "session_state": "active"})

    def test_unhealthy_authority_cannot_reconcile_exit(self):
        self.start(); self.h.launcher.record_exit(self.process)
        self.h = self.h.restart_from_mock_ledger(now=1000, intact=False)
        self.case.error("temporarily_unavailable", lambda: self.h.reconcile_application(now=1000))

    def test_exit_tombstone_prevents_stale_running_snapshot_handshake(self):
        self.case = T.LaunchTests(); self.case.setUp(); self.h = self.case.h
        self.h.launcher.outcomes = ["unknown_after_effect"]
        offer = self.case.approved(); self.case.launch(offer)
        ref = self.case.payload(offer)["launch_permission_ref"]
        stale = deepcopy(self.h.launcher.running)
        self.h.launcher.record_exit(stale["process_ref"])
        self.h.launcher.running = stale
        self.assertFalse(self.h.launcher.verify_existing_effect(ref))
        self.assertFalse(self.h.launcher.available(self.h.launcher.binding()))

    def test_maximum_length_permission_can_join_exit_and_reconcile(self):
        case = T.LaunchTests(); case.setUp(); h = case.h
        offer = case.create()
        ref = "p" * 128
        payload = {"offer_id": offer["offer_id"], "scope_digest": offer["scope_digest"],
                   "allow": True, "remember": False, "launch_permission": True, "decision_ref": ref}
        h.decisions[ref] = {"player": case.f["player"], "payload": deepcopy(payload),
                            "launch_binding": h.launcher.binding()}
        case.send("offer.decide", payload, rid="long-permit-approval")
        launch = {"offer_id": offer["offer_id"], "application_registration": "fixture-companion",
                  "launch_permission_ref": ref}
        self.assertEqual(case.send("launch.request", launch, rid="long-launch"), {"status": "started"})
        invitation = case.invite(offer)
        join = {key: invitation[key] for key in ("invitation_id", "join_intent")}
        case.send("session.join", join, invitation["invitation_credential"])
        h.finish_admission(now=1000)
        process_ref = h.state["admission_process"]["process_ref"]
        h.launcher.record_exit(process_ref)
        h = h.restart_from_mock_ledger(now=1000)
        self.assertEqual(h.reconcile_application(now=1000)["session_state"], "closed")
        self.assertEqual(h.launcher.start_calls, 1)

    def test_long_permission_references_do_not_alias_at_shared_prefix(self):
        case = T.LaunchTests(); case.setUp(); port = case.h.launcher
        refs = ["p" * 127 + suffix for suffix in ("a", "b")]
        processes = []
        for ref in refs:
            port.start(ref, port.binding())
            process = port.effects[ref]["process_ref"]
            C.validate_type("Id", process)
            processes.append(process)
            port.record_exit(process)
        self.assertNotEqual(*processes)
        port.start(refs[0], port.binding())
        self.assertEqual(port.start_calls, 2)
        self.assertEqual(len(port.exited), 2)


if __name__ == "__main__":
    unittest.main()
