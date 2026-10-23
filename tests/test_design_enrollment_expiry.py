"""公共准入/启动身份不能用已到期的 enrolled 凭据继续读写。"""

import unittest
import test_design_launch as T

C = T.C


class EnrollmentExpiryTests(unittest.TestCase):
    def setUp(self):
        self.case = T.LaunchTests(); self.case.setUp()
        self.offer = self.case.approved(); self.h = self.case.h

    def test_expired_player_cannot_launch_or_revoke_permission(self):
        self.h.identities["player-fixture"]["expires_at"] = 1000
        self.case.error("unauthenticated", lambda: self.case.launch(self.offer))
        payload = {"object_type": "launch_permission", "object_id": self.case.payload(self.offer)["launch_permission_ref"],
                   "expected_revision": 1}
        self.case.error("unauthenticated", lambda: self.case.send("permission.revoke", payload))
        self.assertEqual(self.h.launcher.start_calls, 0)
        self.assertEqual(self.h.state["launch_records"], {})

    def test_expired_player_cannot_read_cached_launch_or_revocation(self):
        self.case.launch(self.offer)
        payload = {"object_type": "launch_permission", "object_id": self.case.payload(self.offer)["launch_permission_ref"],
                   "expected_revision": 1}
        self.case.send("permission.revoke", payload, rid="revoke")
        self.h.identities["player-fixture"]["expires_at"] = 1000
        self.case.error("unauthenticated", lambda: self.case.launch(self.offer))
        self.case.error("unauthenticated", lambda: self.case.send("permission.revoke", payload, rid="revoke"))
        self.case.error("unauthenticated", self.case.status)
        self.assertEqual(self.h.launcher.start_calls, 1)

    def test_expired_agent_cannot_read_descriptor_or_offer(self):
        self.h.identities["agent-identity"]["expires_at"] = 1000
        self.case.error("unauthenticated", lambda: self.case.send("describe", {"instance": self.case.f["scope"]["instance"]}, "agent-identity"))
        self.case.error("unauthenticated", lambda: self.case.send("offer.get", {"offer_id": self.offer["offer_id"]}, "agent-identity"))

    def test_strict_expiry_types_and_optional_field_compatibility(self):
        identity = self.h.identities["player-fixture"]
        for expiry in (True, "600000", None, 999, 1000):
            with self.subTest(expiry=expiry):
                identity["expires_at"] = expiry
                self.case.error("unauthenticated", lambda: self.case.send("offer.get", {"offer_id": self.offer["offer_id"]}))
        identity["expires_at"] = 1001
        self.assertEqual(self.case.send("offer.get", {"offer_id": self.offer["offer_id"]})["state"], "approved")
        del identity["expires_at"]
        self.assertEqual(self.case.send("offer.get", {"offer_id": self.offer["offer_id"]})["state"], "approved")

    def test_independent_invitation_credential_is_not_ambient_enrollment(self):
        self.case.launch(self.offer)
        invitation = self.case.invite(self.offer)
        self.h.identities["agent-identity"]["expires_at"] = 1000
        result = self.case.send("session.join", {key: invitation[key] for key in ("invitation_id", "join_intent")},
                                invitation["invitation_credential"])
        self.assertEqual(result["status"], "join_pending")


if __name__ == "__main__":
    unittest.main()
