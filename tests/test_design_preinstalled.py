"""精确预装形象的准入与目标设备门禁；不加载真实资源。"""

from copy import deepcopy
import unittest
from test_design_assets import A, F, C


class PreinstalledTests(unittest.TestCase):
    def start(self, *, presentation=False, installed=True):
        features = ["core.session", "core.events", "avatar", "resume", "handoff"]
        if presentation:
            features.append("presentation")
        self.f = F.core_fixture(features)
        self.avatar = {"kind": "preinstalled", "asset_id": "builtin-fox", "revision": 1, "format": "fixture-installed-1"}
        self.f["descriptor"]["avatar_requirements"] = {"accepted_formats": [self.avatar["format"]]}
        self.f["requested"]["forced_avatar"] = deepcopy(self.avatar)
        if presentation:
            self.f["requested"]["presentation_terms"] = {"mode": "hide_desktop", "device_id": "device-a"}
        self.h = A.AssetHarness(self.f)
        if installed:
            self.h.resources.register_installed(self.avatar, "device-a" if presentation else "fixture-headless", "a" * 64)
        observation = self.h.enroll_device("device-a") if presentation else None
        self.h.identities["agent-identity"]["device_id"] = "device-a" if presentation else None
        offer = self.send("offer.create", {"entry": "companion", "descriptor_id": "fixture-descriptor",
            "expected_descriptor_revision": 1, "requested": self.f["requested"]})
        self.scope = offer["immutable_scope"]
        decision = {"offer_id": offer["offer_id"], "scope_digest": offer["scope_digest"], "allow": True,
            "remember": False, "launch_permission": False, "decision_ref": "approve-installed"}
        self.h.decisions["approve-installed"] = {"player": self.f["player"], "payload": decision}
        self.send("offer.decide", decision, "player-fixture")
        intent = {"scope_digest": offer["scope_digest"]}
        if presentation:
            intent.update(selected_device="device-a", presentation_observation=observation)
        invite = self.send("invitation.redeem", {"offer_id": offer["offer_id"], "join_intent": intent})
        self.join = {key: invite[key] for key in ("invitation_id", "join_intent")}
        self.credential = invite["invitation_credential"]
        self.send("session.join", self.join, self.credential)

    def send(self, operation, payload, credential="agent-identity", *, rid=None, **kwargs):
        reply = C.codec.decode(self.h.submit(C.codec.canonical(F.wire_request(operation, payload, rid or operation)),
                                            credential, now=1000, **kwargs))
        self.assertNotIn("error", reply)
        return reply["result"]

    def rejected(self, code, fn):
        with self.assertRaises(C.ContractError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def test_preinstalled_admission_without_assets_or_network(self):
        self.start()
        self.assertNotIn("assets", self.scope["features"])
        self.assertNotIn("resource_policy", self.scope)
        self.assertEqual(self.scope["avatar_selection"], self.avatar)
        self.assertTrue(self.h.finish_admission(now=1000)["ready"])
        self.assertEqual(self.send("session.join", self.join, self.credential)["status"], "ready")
        self.assertEqual(self.h.resources.trace, [])
        self.assertEqual(self.h.resources.parse_calls, 0)
        self.assertEqual(self.h.state["asset_cache"], {})

    def test_missing_or_wrong_revision_never_falls_back(self):
        for wrong in (None, {"revision": 2}, {"format": "other-format"}):
            with self.subTest(wrong=wrong):
                self.start(installed=False)
                if wrong:
                    self.h.resources.register_installed({**self.avatar, **wrong}, "fixture-headless", "a" * 64)
                state = self.h.finish_admission(now=1000)
                self.assertFalse(state["ready"])
                self.assertEqual(state["state"], "closed")

    def test_same_version_content_binding_is_immutable_across_devices(self):
        self.start()
        self.h.resources.register_installed(self.avatar, "device-b", "a" * 64)
        self.rejected("id_conflict", lambda: self.h.resources.register_installed(self.avatar, "device-c", "b" * 64))
        self.assertFalse(self.h.resources.preinstalled_accepts(self.avatar, "device-c"))
        self.assertTrue(self.h.resources.preinstalled_accepts(self.avatar, "device-b"))

    def test_presentation_requires_exact_target_device_inventory(self):
        self.start(presentation=True, installed=False)
        job = self.h.state["presentation_jobs"]["admission-s1"]["acquire"]
        self.h.resources.register_installed(self.avatar, "device-b", "a" * 64)
        self.rejected("avatar_incompatible", lambda: self.send("presentation.acquire", job, "presentation-fixture", rid="admission-s1"))
        self.h.resources.register_installed(self.avatar, "device-a", "a" * 64)
        self.send("presentation.acquire", job, "presentation-fixture", rid="admission-s1")
        self.assertTrue(self.h.finish_admission(now=1000)["ready"])

    def test_restart_rechecks_independent_inventory_before_ready(self):
        self.start()
        self.h = self.h.restart_from_mock_ledger(now=1000)
        self.h.resources.installed_devices["fixture-headless"].clear()
        self.assertEqual(self.h.finish_admission(now=1000)["state"], "closed")

    def test_installed_catalog_capacity_and_boolean_revision_are_rejected(self):
        self.start()
        with self.assertRaises(C.ContractError):
            self.h.resources.register_installed({**self.avatar, "revision": True}, "device-a", "a" * 64)
        for index in range(1, 128):
            self.h.resources.register_installed({**self.avatar, "asset_id": "builtin-" + str(index)}, "fixture-headless", "a" * 64)
        self.rejected("resource_limit", lambda:
            self.h.resources.register_installed({**self.avatar, "asset_id": "overflow"}, "fixture-headless", "a" * 64))
        self.h.resources.register_installed(self.avatar, "fixture-headless", "a" * 64)

    def test_resume_rechecks_inventory_without_rotating_on_failure(self):
        self.start()
        self.h.finish_admission(now=1000)
        self.h.resources.installed_devices["fixture-headless"].clear()
        self.rejected("avatar_incompatible", lambda:
            self.send("session.resume", {"session_id": "s1", "expected_generation": 1}))
        self.assertEqual(self.h.session.state["session"]["control_generation"], 1)

    def test_handoff_checks_target_inventory_and_never_restores_old_writer(self):
        for installed in (False, True):
            with self.subTest(installed=installed):
                self.start(presentation=True)
                self.h.enroll_device("device-b")
                self.send("presentation.acquire", self.h.state["presentation_jobs"]["admission-s1"]["acquire"],
                          "presentation-fixture", rid="admission-s1")
                self.h.finish_admission(now=1000)
                if installed:
                    self.h.resources.register_installed(self.avatar, "device-b", "a" * 64)
                payload = {"session_id": "s1", "expected_generation": 1, "target_device": "device-b",
                           "decision_ref": "move", "target_proof_ref": "target"}
                digest = C.codec.digest("scope", self.scope)
                self.h.decisions["move"] = {"player": self.f["player"], "payload": payload, "scope_digest": digest}
                self.h.target_proofs["target"] = {"agent": self.f["agent"], "device_id": "device-b", "session_id": "s1",
                                                  "expires_at": 100000, "scope_digest": digest}
                transfer = self.send("session.handoff", payload, "player-fixture")
                if installed:
                    self.send("presentation.release", {"session_id": "s1", "generation": 1, "device_id": "device-a"},
                              "presentation-fixture")
                    self.h.advance_transfer(transfer["transfer_id"], now=1000)
                    jid = "presentation-" + transfer["transfer_id"]
                    self.send("presentation.acquire", self.h.state["presentation_jobs"][jid]["acquire"],
                              "presentation-fixture", rid=jid)
                result = self.h.advance_transfer(transfer["transfer_id"], now=1000)
                self.assertEqual(result["status"], "ready" if installed else "failed")
                self.assertEqual(self.h.session.state["session"]["control_generation"], 2)
                self.assertEqual(self.h.resources.trace, [])


if __name__ == "__main__":
    unittest.main()
