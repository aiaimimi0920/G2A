"""启动许可撤销不级联接入批准，不抹掉未知或已产生效果。"""

from copy import deepcopy
import unittest
import test_design_launch as T

L, C = T.L, T.C


class LaunchRevocationTests(unittest.TestCase):
    def setUp(self):
        self.case = T.LaunchTests(); self.case.setUp()
        self.offer = self.case.approved(); self.h = self.case.h
        self.ref = self.case.payload(self.offer)["launch_permission_ref"]
        self.payload = {"object_type": "launch_permission", "object_id": self.ref, "expected_revision": 1}

    def revoke(self, **kwargs):
        return self.case.send("permission.revoke", self.payload, rid="revoke-launch", **kwargs)

    def grant(self):
        oid = self.h.state["offers"][self.offer["offer_id"]]["view"]["grant_id"]
        return self.h.state["grants"][oid]

    def test_revoke_before_acceptance_preserves_separate_grant(self):
        before = deepcopy(self.grant())
        self.assertEqual(self.revoke(), {"object_type": "launch_permission", "object_id": self.ref,
                                       "revision": 2, "state": "revoked"})
        self.case.error("consent_required", lambda: self.case.launch(self.offer))
        self.assertEqual(self.grant(), before)
        self.assertEqual(self.h.launcher.start_calls, 0)

    def test_revoke_between_acceptance_and_dispatch_does_not_cascade(self):
        with self.assertRaises(L.U.S.H.InjectedFailure):
            self.case.launch(self.offer, fault="after_accept")
        before = deepcopy(self.grant())
        self.revoke()
        self.assertEqual(self.case.launch(self.offer)["error"]["outcome"], "accepted")
        self.assertEqual(self.h.state["launch_records"]["r1"]["failure_reason"], "launch_permission_revoked")
        self.assertEqual(self.grant(), before)
        self.assertEqual(self.h.launcher.start_calls, 0)

    def test_revoke_after_dispatch_keeps_unknown_and_does_not_retry_effect(self):
        with self.assertRaises(L.U.S.H.InjectedFailure):
            self.case.launch(self.offer, fault="after_dispatch")
        self.revoke()
        self.assertEqual(self.case.launch(self.offer)["error"]["outcome"], "unknown")
        self.assertEqual(self.case.status()["state"], "pending")
        self.assertEqual(self.h.launcher.start_calls, 0)

    def test_revoke_after_effect_does_not_erase_launch_receipt(self):
        with self.assertRaises(L.U.S.H.InjectedFailure):
            self.case.launch(self.offer, fault="after_effect")
        self.revoke()
        self.assertEqual(self.case.launch(self.offer)["result"], {"status": "started"})
        self.assertEqual(self.h.launcher.start_calls, 1)
        self.assertEqual(len(self.h.launcher.effects), 1)
        self.assertEqual(self.grant()["state"], "active")

    def test_revocation_commit_faults_restart_and_query_are_idempotent(self):
        for fault in ("before_commit", "after_commit"):
            with self.subTest(fault=fault):
                self.setUp()
                with self.assertRaises(L.U.S.H.InjectedFailure):
                    self.revoke(fault=fault)
                self.h = self.h.restart_from_mock_ledger(now=1000); self.case.h = self.h
                result = self.revoke()
                self.assertEqual(result["revision"], 2)
                self.assertEqual(self.revoke(), result)
                query = self.case.send("operation.get", {"operation": "permission.revoke",
                    "original_request_id": "revoke-launch"}, rid="query-revoke")
                self.assertEqual(query["revocation"], result)

    def test_revoke_authority_and_revision_are_checked(self):
        for credential in ("agent-identity", "game-fixture"):
            self.case.error("permission_denied", lambda: self.revoke(credential=credential))
        self.case.error("generation_conflict", lambda: self.case.send("permission.revoke",
            {**self.payload, "expected_revision": 2}, rid="wrong-revision"))
        self.case.error("permission_denied", lambda: self.case.send("permission.revoke",
            {**self.payload, "object_id": "missing"}, rid="missing"))
        self.assertEqual(self.h.state["launch_permits"][self.ref]["state"], "active")

    def test_revoke_after_join_does_not_close_existing_session(self):
        self.case.launch(self.offer)
        invitation = self.case.invite(self.offer)
        payload = {key: invitation[key] for key in ("invitation_id", "join_intent")}
        self.case.send("session.join", payload, invitation["invitation_credential"])
        self.h.finish_admission(now=1000)
        before = deepcopy(self.h.session.state)
        self.revoke()
        self.assertEqual(self.h.session.state, before)
        self.assertTrue(self.h.session.state["session"]["ready"])


if __name__ == "__main__":
    unittest.main()
