"""记住批准到自动批准/撤销的字节链；固定可信身份和内存账本。"""

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


A = load("auto_rule_admission", "admission_harness.py")
F = load("auto_rule_fixtures", "fixtures.py")
C = A.C


class AutoRuleTests(unittest.TestCase):
    def setUp(self):
        self.f = F.core_fixture()
        self.h = A.AdmissionHarness(self.f)
        self.error_type, self.fault_type = C.ContractError, A.U.S.H.InjectedFailure
        self.now = 1000
        self.serial = 0

    def send(self, op, payload, credential="agent-identity", *, rid=None, fault=None):
        self.serial += 1
        raw = C.codec.canonical(F.wire_request(op, payload, rid or "auto-" + str(self.serial)))
        return C.codec.decode(self.h.submit(raw, credential, now=self.now, fault=fault))["result"]

    def create(self, *, entry="companion", requested=None, **kwargs):
        return self.send("offer.create", {"entry": entry, "descriptor_id": "fixture-descriptor",
            "expected_descriptor_revision": self.h.state["descriptor"]["revision"],
            "requested": deepcopy(requested or self.f["requested"])},
            "agent-identity" if entry == "companion" else "player-fixture", **kwargs)

    def decision(self, offer, *, expiry=900000, duration=300000, remember=True):
        payload = {"offer_id": offer["offer_id"], "scope_digest": offer["scope_digest"], "allow": True,
            "remember": remember, "launch_permission": False, "decision_ref": "consent-" + offer["offer_id"]}
        if remember:
            payload.update(rule_expires_at=expiry, maximum_grant_duration_ms=duration)
        self.h.decisions[payload["decision_ref"]] = {"player": self.f["player"], "payload": deepcopy(payload)}
        return payload

    def remember(self, **kwargs):
        self.original = self.create()
        self.payload = self.decision(self.original, **kwargs)
        result = self.send("offer.decide", self.payload, "player-fixture", rid="remember")
        self.rule = result["auto_rule"]
        return result

    def revoke(self, *, revision=1, credential="player-fixture", **kwargs):
        return self.send("permission.revoke", {"object_type": "auto_rule", "object_id": self.rule["rule_id"],
                         "expected_revision": revision}, credential, **kwargs)

    def invite(self, offer):
        return self.send("invitation.redeem", {"offer_id": offer["offer_id"],
                         "join_intent": {"scope_digest": offer["scope_digest"]}})

    def join(self, invitation):
        return self.send("session.join", {k: invitation[k] for k in ("invitation_id", "join_intent")},
                         invitation["invitation_credential"])

    def deny(self, code, fn):
        with self.assertRaises(self.error_type) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def test_both_entries_automatically_issue_new_grant_with_frozen_scope(self):
        first = self.remember()
        for entry in ("companion", "game"):
            self.now += 1
            result = self.create(entry=entry)
            self.assertEqual(result["state"], "approved")
            self.assertNotEqual(result["grant_id"], first["grant_id"])
            self.assertEqual(result["auto_rule"], self.rule)
            self.assertEqual(result["scope_digest"], C.codec.digest("scope", result["immutable_scope"]))
            self.assertEqual(result["immutable_scope"]["created_at"], self.now)
            grant = self.h.state["grants"][result["grant_id"]]
            self.assertEqual(grant["consent_evidence_ref"], self.payload["decision_ref"])
            self.assertNotIn("invitation_credential", result)

    def test_rule_matches_exact_policy_even_when_requested_permission_is_smaller(self):
        self.remember()
        for field, value in (("action_ids", []), ("context_categories", []),
                             ("maximum_grant_duration_ms", 299999)):
            requested = deepcopy(self.f["requested"])
            requested[field] = value
            self.assertEqual(self.create(requested=requested)["state"], "pending")
        requested = deepcopy(self.f["requested"])
        requested["policy"]["proactive_chat"] = True
        self.assertEqual(self.create(requested=requested)["state"], "pending")

    def test_descriptor_revision_change_requires_new_consent(self):
        self.remember()
        self.h.state["descriptor"]["revision"] += 1
        self.assertEqual(self.create()["state"], "pending")

    def test_rule_expiry_does_not_mutate_offer_deadline_or_scope(self):
        self.remember(expiry=301001)
        self.now = 1001
        self.assertEqual(self.create()["state"], "approved")  # grant 到期恰好等于 rule 到期。
        self.now = 1002
        result = self.create()
        self.assertEqual(result["state"], "pending")
        self.assertEqual(result["immutable_scope"]["expires_at"], 301002)
        self.now = 301001
        self.assertEqual(self.create()["state"], "pending")

    def test_explicit_shorter_rule_duration_requires_matching_future_request(self):
        self.remember(duration=100000)
        self.assertEqual(self.create()["state"], "pending")
        requested = deepcopy(self.f["requested"])
        requested["maximum_grant_duration_ms"] = 100000
        self.assertEqual(self.create(requested=requested)["state"], "approved")

    def test_rule_options_must_be_live_bounded_and_bound_to_consent(self):
        for expiry, duration in ((1000, 300000), (999, 300000), (900000, 300001)):
            with self.subTest(expiry=expiry, duration=duration):
                self.setUp()
                offer = self.create()
                payload = self.decision(offer, expiry=expiry, duration=duration)
                before = deepcopy(self.h.state)
                self.deny("invalid_arguments", lambda: self.send("offer.decide", payload, "player-fixture"))
                self.assertEqual(self.h.state, before)
        payload = self.decision(offer)
        payload["rule_expires_at"] += 1
        self.deny("consent_required", lambda: self.send("offer.decide", payload, "player-fixture"))

    def test_revoke_blocks_future_not_previously_issued_grant_invitation_or_session(self):
        self.remember()
        automatic = self.create()
        invitation = self.invite(automatic)
        grants = deepcopy(self.h.state["grants"])
        self.revoke()
        self.assertEqual(self.h.state["grants"], grants)
        self.assertEqual(self.join(invitation)["status"], "join_pending")
        self.h.finish_admission(now=self.now)
        self.assertEqual(self.join(invitation)["status"], "ready")
        self.revoke(revision=2)
        self.assertEqual(self.h.session.state["session"]["state"], "active")
        self.assertEqual(self.create()["state"], "pending")

    def test_grant_revoke_does_not_revoke_future_auto_approval(self):
        first = self.remember()
        self.send("permission.revoke", {"object_type": "grant", "object_id": first["grant_id"],
                  "expected_revision": 1}, "player-fixture")
        self.assertEqual(self.create()["state"], "approved")

    def test_game_and_agent_cannot_revoke_player_rule_or_query_player_receipt(self):
        self.remember()
        before = deepcopy(self.h.state)
        for credential in ("game-fixture", "agent-identity"):
            self.deny("permission_denied", lambda: self.revoke(credential=credential))
        self.assertEqual(self.h.state, before)
        result = self.revoke(rid="revoke-rule")
        payload = {"operation": "permission.revoke", "original_request_id": "revoke-rule"}
        self.assertEqual(self.send("operation.get", payload, "player-fixture")["revocation"], result)
        self.deny("permission_denied", lambda: self.send("operation.get", payload))

    def test_remember_before_commit_and_after_commit_are_atomic(self):
        offer = self.create()
        payload = self.decision(offer)
        before = deepcopy(self.h.state)
        with self.assertRaises(self.fault_type):
            self.send("offer.decide", payload, "player-fixture", rid="remember", fault="before_commit")
        self.assertEqual(self.h.state, before)
        with self.assertRaises(self.fault_type):
            self.send("offer.decide", payload, "player-fixture", rid="remember", fault="after_commit")
        committed = deepcopy(self.h.state)
        result = self.send("offer.decide", payload, "player-fixture", rid="remember")
        self.assertEqual(result["state"], "approved")
        self.assertEqual(self.h.state, committed)

    def test_automatic_create_faults_do_not_leave_or_duplicate_grants(self):
        self.remember()
        before = deepcopy(self.h.state)
        with self.assertRaises(self.fault_type):
            self.create(rid="automatic", fault="before_commit")
        self.assertEqual(self.h.state, before)
        with self.assertRaises(self.fault_type):
            self.create(rid="automatic", fault="after_commit")
        committed = deepcopy(self.h.state)
        self.assertEqual(self.create(rid="automatic")["state"], "approved")
        self.assertEqual(self.h.state, committed)

    def test_revoke_fault_retry_cas_and_changed_id_content(self):
        self.remember()
        before = deepcopy(self.h.state)
        with self.assertRaises(self.fault_type):
            self.revoke(rid="revoke-rule", fault="before_commit")
        self.assertEqual(self.h.state, before)
        with self.assertRaises(self.fault_type):
            self.revoke(rid="revoke-rule", fault="after_commit")
        committed = deepcopy(self.h.state)
        self.assertEqual(self.revoke(rid="revoke-rule")["revision"], 2)
        self.assertEqual(self.h.state, committed)
        self.deny("generation_conflict", lambda: self.revoke())
        self.deny("id_conflict", lambda: self.revoke(revision=2, rid="revoke-rule"))

    def test_replaying_original_consent_cannot_resurrect_revoked_rule(self):
        self.remember()
        self.revoke()
        self.send("offer.decide", self.payload, "player-fixture", rid="remember")
        self.send("offer.decide", self.payload, "player-fixture", rid="new-transport")
        self.assertEqual(len(self.h.state["auto_rules"]), 1)
        self.assertEqual(self.create()["state"], "pending")

    def test_pending_offer_reads_and_retries_never_retroactively_auto_approve(self):
        pending = self.create(rid="pending")
        self.remember()
        self.assertEqual(self.create(rid="pending"), pending)
        self.assertEqual(self.send("offer.get", {"offer_id": pending["offer_id"]}), pending)
        self.assertEqual(self.create()["state"], "approved")

    def test_fresh_consent_can_create_new_rule_but_not_unrevoke_old_rule(self):
        self.remember()
        old = self.rule["rule_id"]
        self.revoke()
        offer = self.create()
        result = self.send("offer.decide", self.decision(offer), "player-fixture")
        self.assertNotEqual(result["auto_rule"]["rule_id"], old)
        self.assertEqual(self.h.state["auto_rules"][old]["state"], "revoked")
        self.assertEqual(self.create()["state"], "approved")

    def test_create_and_revoke_race_has_only_two_serializable_outcomes(self):
        for _ in range(4):
            self.setUp()
            self.remember()
            barrier = Barrier(2)
            def create():
                barrier.wait(timeout=5)
                return self.create(rid="race-create")
            def revoke():
                barrier.wait(timeout=5)
                return self.revoke(rid="race-revoke")
            with ThreadPoolExecutor(max_workers=2) as pool:
                created, revoked = pool.submit(create), pool.submit(revoke)
                offer = created.result(timeout=5)
                self.assertEqual(revoked.result(timeout=5)["state"], "revoked")
            self.assertIn(offer["state"], ("pending", "approved"))
            self.assertEqual(len(self.h.state["grants"]), 2 if offer["state"] == "approved" else 1)
            self.assertEqual(self.create()["state"], "pending")

    def test_mock_ledger_copy_keeps_revocation_and_receipt(self):
        self.remember()
        self.revoke(rid="revoke-rule")
        restored = A.AdmissionHarness(self.f)
        restored.state = deepcopy(self.h.state)
        restored.decisions = deepcopy(self.h.decisions)
        self.h = restored
        self.assertEqual(self.revoke(rid="revoke-rule")["revision"], 2)
        self.assertEqual(self.create()["state"], "pending")

    def launch_profile(self):
        module = load("auto_rule_launch", "launch_harness.py")
        self.f = F.core_fixture(["core.session", "core.events"])
        self.h = module.LaunchHarness(self.f)
        self.error_type, self.fault_type = module.C.ContractError, module.U.S.H.InjectedFailure
        self.h.launcher.running = {"binding": self.h.launcher.binding(), "verified": True}
        offer = self.create(entry="game")
        payload = self.decision(offer)
        self.h.decisions[payload["decision_ref"]]["launch_binding"] = self.h.launcher.binding()
        result = self.send("offer.decide", payload, "player-fixture")
        self.rule = result["auto_rule"]
        return result

    def test_remember_never_implicitly_launches_or_signs_launch_permission(self):
        self.launch_profile()
        self.assertEqual(self.create(entry="game")["state"], "approved")
        self.h.launcher.running = None
        result = self.create(entry="game")
        self.assertTrue(result["launch_required"])
        self.assertEqual(result["state"], "pending")
        self.assertEqual(self.h.state["launch_permits"], {})
        self.assertEqual(self.h.launcher.start_calls, 0)

    def test_local_registration_and_device_are_frozen_rule_context(self):
        self.launch_profile()
        for field, value in (("revision", 2), ("device_id", "device-b")):
            self.h.launcher.registration[field] = value
            self.h.launcher.running = {"binding": self.h.launcher.binding(), "verified": True}
            self.assertEqual(self.create(entry="game")["state"], "pending")

    def test_local_remember_requires_explicit_binding_evidence(self):
        self.launch_profile()
        self.revoke()
        offer = self.create(entry="game")
        payload = self.decision(offer)
        before = deepcopy(self.h.state)
        self.deny("consent_required", lambda: self.send("offer.decide", payload, "player-fixture"))
        self.assertEqual(self.h.state, before)

    def test_launch_and_remember_permissions_commit_together_but_remain_separate(self):
        self.launch_profile()
        self.h.launcher.running = None
        offer = self.create(entry="game")
        payload = self.decision(offer)
        payload["launch_permission"] = True
        self.h.decisions[payload["decision_ref"]].update(payload=deepcopy(payload), launch_binding=self.h.launcher.binding())
        before = deepcopy(self.h.state)
        with self.assertRaises(self.fault_type):
            self.send("offer.decide", payload, "player-fixture", fault="before_commit")
        self.assertEqual(self.h.state, before)
        approved = self.send("offer.decide", payload, "player-fixture")
        self.rule = approved["auto_rule"]
        self.revoke()
        self.assertEqual(self.send("launch.request", {"offer_id": offer["offer_id"],
            "application_registration": "fixture-companion", "launch_permission_ref": payload["decision_ref"]},
            "player-fixture")["status"], "started")
        self.assertEqual(self.h.launcher.start_calls, 1)

    def test_control_restart_preserves_active_rule_then_revocation(self):
        module = load("auto_rule_control", "control_harness.py")
        self.f = F.core_fixture(["core.session", "core.events", "actions", "resume"])
        self.h = module.ControlHarness(self.f)
        self.error_type, self.fault_type = module.C.ContractError, module.U.S.H.InjectedFailure
        self.remember()
        invitation = self.invite(self.create())
        self.join(invitation)
        self.h.finish_admission(now=self.now)
        self.h = self.h.restart_from_mock_ledger(now=self.now)
        self.assertEqual(self.create()["state"], "approved")
        self.revoke(rid="revoke-restart")
        self.h = self.h.restart_from_mock_ledger(now=self.now)
        self.assertEqual(self.revoke(rid="revoke-restart")["revision"], 2)
        self.assertEqual(self.create()["state"], "pending")

    def test_prejoin_and_session_revoke_ids_share_conflict_boundary(self):
        self.remember()
        invitation = self.invite(self.create())
        self.join(invitation)
        self.h.finish_admission(now=self.now)
        self.revoke(rid="shared")
        self.deny("id_conflict", lambda: self.send("permission.revoke", {"object_type": "capability",
            "object_id": "find-key", "expected_revision": 1}, "player-fixture", rid="shared"))
        self.send("permission.revoke", {"object_type": "capability", "object_id": "find-key",
                  "expected_revision": 1}, "player-fixture", rid="shared-back")
        self.deny("id_conflict", lambda: self.revoke(revision=2, rid="shared-back"))

    def test_rule_key_keeps_identity_epoch_binding_and_privacy(self):
        self.remember()
        scope = self.original["immutable_scope"]
        key = self.h._rule_key(scope, 300000)
        later = deepcopy(scope)
        later["created_at"] += 10
        later["expires_at"] += 10
        self.assertEqual(self.h._rule_key(later, 300000), key)
        for field in ("player", "agent", "instance", "binding", "trust_profile", "privacy_model",
                      "approved_action_digests", "effective_policy", "audiences", "limits"):
            changed = deepcopy(scope)
            changed[field] = {"changed": True}
            self.assertNotEqual(self.h._rule_key(changed, 300000), key)


if __name__ == "__main__":
    unittest.main()
