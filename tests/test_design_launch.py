"""本地启动的许可、外部效果与未知结果反例；不启动真实程序。"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import importlib.util
from pathlib import Path
from threading import Barrier
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1] / "docs/protocol"


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


L = load("test_launch", "launch_harness.py")
F = load("test_launch_fixture", "fixtures.py")
C = L.C


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.f = F.core_fixture(["core.session", "core.events"])
        self.h = L.LaunchHarness(self.f)

    def wire(self, operation, payload, credential="player-fixture", rid="r1", now=1000, fault=None):
        return C.codec.decode(self.h.submit(C.codec.canonical(F.wire_request(operation, payload, rid)), credential, now=now, fault=fault))

    def send(self, *args, **kwargs):
        reply = self.wire(*args, **kwargs)
        self.assertIn("result", reply)
        return reply["result"]

    def error(self, code, fn):
        with self.assertRaises(C.ContractError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def create(self, entry="game", rid="offer"):
        return self.send("offer.create", {"entry": entry, "descriptor_id": "fixture-descriptor", "expected_descriptor_revision": 1,
            "requested": self.f["requested"]}, "agent-identity" if entry == "companion" else "player-fixture", rid=rid)

    def decide(self, offer, *, allow=True, permission=True, fault=None):
        ref = "decision-" + offer["offer_id"]
        payload = {"offer_id": offer["offer_id"], "scope_digest": offer["scope_digest"], "allow": allow,
                   "remember": False, "launch_permission": permission, "decision_ref": ref}
        self.h.decisions[ref] = {"player": self.f["player"], "payload": deepcopy(payload),
                                "launch_binding": deepcopy(self.h.state["offers"][offer["offer_id"]]["launch_binding"])}
        return self.send("offer.decide", payload, rid=ref, fault=fault)

    def approved(self):
        offer = self.create()
        self.decide(offer)
        return offer

    def payload(self, offer):
        return {"offer_id": offer["offer_id"], "application_registration": "fixture-companion",
                "launch_permission_ref": "decision-" + offer["offer_id"]}

    def launch(self, offer, **kwargs):
        return self.wire("launch.request", self.payload(offer), **kwargs)

    def status(self, rid="r1", **kwargs):
        return self.send("operation.get", {"operation": "launch.request", "original_request_id": rid}, **kwargs)

    def invite(self, offer):
        return self.send("invitation.redeem", {"offer_id": offer["offer_id"], "join_intent": {"scope_digest": offer["scope_digest"]}},
                         "agent-identity", rid="redeem")

    def test_game_entry_launch_is_separate_from_consent_invitation_and_ready(self):
        offer = self.create()
        self.assertTrue(offer["launch_required"])
        self.decide(offer)
        self.assertEqual(self.h.launcher.start_calls, 0)
        self.error("temporarily_unavailable", lambda: self.invite(offer))
        self.assertEqual(self.launch(offer)["result"], {"status": "started"})
        self.assertIsNone(self.h.session)
        invitation = self.invite(offer)
        payload = {key: invitation[key] for key in ("invitation_id", "join_intent")}
        self.assertEqual(self.send("session.join", payload, invitation["invitation_credential"])["status"], "join_pending")
        self.h.finish_admission(now=1000)
        delivery = self.send("session.join", payload, invitation["invitation_credential"])
        self.assertEqual(delivery["status"], "ready")
        self.assertEqual(self.h.session.credentials[delivery["control_credential"]]["device_id"], self.h.launcher.registration["device_id"])
        self.assertTrue(self.send("session.snapshot", {"session_id": "s1"}, delivery["control_credential"])["session"]["ready"])
        self.assertEqual(self.h.launcher.start_calls, 1)

    def test_verified_running_companion_needs_no_implicit_launch_permission(self):
        self.h.launcher.running = {"binding": self.h.launcher.binding(), "verified": True}
        offer = self.create(entry="companion")
        self.assertFalse(offer["launch_required"])
        self.decide(offer, permission=False)
        self.assertIn("invitation_credential", self.invite(offer))
        self.assertEqual(self.h.launcher.start_calls, 0)
        self.assertEqual(self.h.launcher.effects, {})

    def test_explicit_request_reports_already_running_without_new_effect(self):
        self.h.launcher.running = {"binding": self.h.launcher.binding(), "verified": True}
        offer = self.approved()
        self.assertEqual(self.launch(offer)["result"], {"status": "already_running"})
        self.assertEqual(self.h.launcher.effects, {})

    def test_approval_without_launch_permission_and_denial_never_start(self):
        for allow in (True, False):
            self.setUp()
            offer = self.create()
            self.decide(offer, allow=allow, permission=False)
            self.error("consent_required", lambda: self.launch(offer))
            self.assertEqual(self.h.state["launch_permits"], {})
            self.assertEqual(self.h.launcher.start_calls, 0)
        self.error("consent_required", lambda: self.create(entry="companion", rid="absent-companion"))

    def test_launch_consent_requires_exact_trusted_application_binding(self):
        offer = self.create()
        with self.assertRaises(L.U.S.H.InjectedFailure):
            self.decide(offer, fault="before_commit")
        self.assertEqual(self.h.state["grants"], {})
        self.assertEqual(self.h.state["launch_permits"], {})
        ref = "decision-" + offer["offer_id"]
        evidence = self.h.decisions[ref]
        for binding in (None, {**evidence["launch_binding"], "device_id": "other-device"}):
            evidence["launch_binding"] = binding
            self.error("consent_required", lambda: self.send("offer.decide", evidence["payload"], rid=ref))
        self.assertEqual(self.h.state["grants"], {})

    def test_registration_revision_identity_and_types_cannot_drift_after_approval(self):
        for change in ({"revision": 2}, {"revision": True}, {"device_id": "device-b"},
                       {"fixed_program": "different-program"}, {"agent": F.principal("other", "agent")}):
            self.setUp()
            offer = self.approved()
            self.h.launcher.registration.update(change)
            self.error("approval_stale", lambda: self.launch(offer))
            self.assertEqual(self.h.launcher.start_calls, 0)

    def test_cross_offer_permit_wrong_registration_and_role_are_denied(self):
        offer = self.approved()
        other = self.create(rid="other-offer")
        self.decide(other)
        payload = {**self.payload(offer), "offer_id": other["offer_id"]}
        self.error("consent_required", lambda: self.wire("launch.request", payload))
        payload = {**self.payload(offer), "application_registration": "arbitrary-application"}
        self.error("permission_denied", lambda: self.wire("launch.request", payload))
        for credential in ("agent-identity", "game-fixture"):
            self.error("permission_denied", lambda: self.launch(offer, credential=credential))
        self.assertEqual(self.h.launcher.start_calls, 0)

    def test_acceptance_and_final_reply_commit_faults_never_reuse_permit(self):
        offer = self.approved()
        with self.assertRaises(L.U.S.H.InjectedFailure):
            self.launch(offer, fault="before_commit")
        self.assertEqual(self.h.state["launch_records"], {})
        self.assertIsNone(self.h.state["launch_permits"][self.payload(offer)["launch_permission_ref"]]["request_id"])
        with self.assertRaises(L.U.S.H.InjectedFailure):
            self.launch(offer, fault="after_accept")
        self.assertEqual(self.status()["state"], "pending")
        self.assertEqual(self.h.launcher.start_calls, 0)
        with self.assertRaises(L.U.S.H.InjectedFailure):
            self.launch(offer, fault="after_commit")
        self.assertEqual(self.launch(offer)["result"]["status"], "started")
        self.assertEqual(self.h.launcher.start_calls, 1)

    def test_effect_and_result_commit_are_separate_query_recovers_known_fact(self):
        for fault in ("after_effect", "before_result_commit"):
            self.setUp()
            offer = self.approved()
            with self.assertRaises(L.U.S.H.InjectedFailure):
                self.launch(offer, fault=fault)
            self.assertEqual(self.h.state["launch_records"]["r1"]["state"], "pending")
            self.assertEqual(len(self.h.launcher.effects), 1)
            self.assertEqual(self.status()["state"], "done")
            self.assertEqual(self.launch(offer)["result"]["status"], "started")
            self.assertEqual(self.h.launcher.start_calls, 1)

    def test_unknown_before_effect_stays_pending_and_never_launches_on_retry(self):
        offer = self.approved()
        self.h.launcher.outcomes = ["unknown_before_effect"]
        reply = self.launch(offer)
        self.assertEqual(reply["error"]["outcome"], "unknown")
        self.assertEqual(self.launch(offer), reply)
        self.assertEqual(self.status()["state"], "pending")
        self.assertFalse(self.h.launcher.verify_existing_effect(self.payload(offer)["launch_permission_ref"]))
        self.assertEqual(self.h.launcher.effects, {})
        self.assertEqual(self.h.launcher.start_calls, 1)

    def test_new_offer_cannot_launch_again_while_previous_launch_is_unresolved(self):
        for outcome in ("unknown_before_effect", "unknown_after_effect", "after_dispatch"):
            self.setUp()
            first = self.approved()
            if outcome == "after_dispatch":
                with self.assertRaises(L.U.S.H.InjectedFailure):
                    self.launch(first, fault=outcome)
            else:
                self.h.launcher.outcomes = [outcome]
                self.assertEqual(self.launch(first)["error"]["outcome"], "unknown")
            effects = len(self.h.launcher.effects)
            other = self.create(rid="other-offer")
            self.decide(other)
            self.assertEqual(self.launch(other, rid="other-launch")["error"]["code"], "launch_failed")
            self.assertEqual(len(self.h.launcher.effects), effects)
            self.assertEqual(self.h.state["grants"]["grant-1"]["state"], "active")
            self.assertEqual(self.h.state["grants"]["grant-2"]["state"], "revoked")

    def test_unknown_after_effect_requires_bound_process_proof_not_relaunch(self):
        offer = self.approved()
        self.h.launcher.outcomes = ["unknown_after_effect"]
        self.assertEqual(self.launch(offer)["error"]["outcome"], "unknown")
        self.error("temporarily_unavailable", lambda: self.invite(offer))
        self.assertTrue(self.h.launcher.verify_existing_effect(self.payload(offer)["launch_permission_ref"]))
        self.assertEqual(self.status()["state"], "done")
        self.assertEqual(self.launch(offer)["result"]["status"], "started")
        self.assertIn("invitation_credential", self.invite(offer))
        self.assertEqual(self.h.launcher.start_calls, 1)

    def test_historical_effect_cannot_resurrect_a_missing_or_different_process(self):
        offer = self.approved()
        self.h.launcher.outcomes = ["unknown_after_effect"]
        self.launch(offer)
        ref = self.payload(offer)["launch_permission_ref"]
        process = deepcopy(self.h.launcher.running)
        self.h.launcher.running = None
        self.assertFalse(self.h.launcher.verify_existing_effect(ref))
        process["process_ref"] = "unrelated-process"
        self.h.launcher.running = process
        self.assertFalse(self.h.launcher.verify_existing_effect(ref))
        self.assertEqual(self.status()["state"], "pending")

    def test_known_start_failure_commits_failed_receipt_and_revokes_unused_grant(self):
        for fault in (None, "before_result_commit", "after_commit"):
            self.setUp()
            offer = self.approved()
            self.h.launcher.outcomes = ["failed"]
            if fault is not None:
                with self.assertRaises(L.U.S.H.InjectedFailure):
                    self.launch(offer, fault=fault)
                self.assertEqual(self.h.state["grants"]["grant-1"]["state"], "active" if fault == "before_result_commit" else "revoked")
            reply = self.launch(offer)
            self.assertEqual((reply["error"]["code"], reply["error"]["outcome"]), ("launch_failed", "accepted"))
            self.assertEqual(self.h.state["grants"]["grant-1"]["state"], "revoked")
            self.assertEqual(self.status()["state"], "failed")
            self.assertEqual(self.launch(offer), reply)
            self.assertEqual(self.h.launcher.start_calls, 1)
            self.assertIsNone(self.h.session)
            self.assertEqual(self.h.state["invitations"], {})

    def test_wrong_process_identity_does_not_hide_existing_effect_or_allow_join(self):
        offer = self.approved()
        self.h.launcher.outcomes = ["wrong_identity"]
        self.assertEqual(self.launch(offer)["error"]["code"], "launch_failed")
        self.assertEqual(len(self.h.launcher.effects), 1)
        self.assertFalse(self.h.launcher.available(self.h.launcher.binding()))
        self.error("temporarily_unavailable", lambda: self.invite(offer))
        self.assertIsNone(self.h.session)

    def test_permit_cannot_be_consumed_by_another_id_and_original_digest_is_frozen(self):
        offer = self.approved()
        self.launch(offer)
        self.error("id_conflict", lambda: self.launch(offer, rid="second"))
        request = F.wire_request("launch.request", self.payload(offer))
        request["extensions"] = {"fixture.note": {"version": "1", "required": False, "value": 1}}
        self.error("id_conflict", lambda: self.h.submit(C.codec.canonical(request), "player-fixture", now=1000))
        self.assertEqual(self.h.launcher.start_calls, 1)

    def test_revocation_before_dispatch_blocks_effect_and_after_effect_keeps_fact(self):
        for before in (True, False):
            self.setUp()
            offer = self.approved()
            callback = lambda: self.send("permission.revoke", {"object_type": "grant", "object_id": "grant-1", "expected_revision": 1}, rid="revoke")
            if before:
                self.h.before_dispatch = callback
            else:
                self.h.after_effect = callback
            reply = self.launch(offer)
            self.assertEqual(self.h.state["grants"]["grant-1"]["state"], "revoked")
            if before:
                self.assertEqual(reply["error"]["outcome"], "accepted")
                self.assertEqual(self.h.launcher.start_calls, 0)
            else:
                self.assertEqual(reply["result"]["status"], "started")
                self.error("grant_revoked", lambda: self.invite(offer))
                self.assertEqual(len(self.h.launcher.effects), 1)

    def test_accepted_request_expiry_cannot_start_and_is_not_reported_not_accepted(self):
        offer = self.approved()
        with self.assertRaises(L.U.S.H.InjectedFailure):
            self.launch(offer, fault="after_accept")
        reply = self.launch(offer, now=offer["decision_deadline"])
        self.assertEqual(reply["error"]["outcome"], "accepted")
        self.assertEqual(self.h.launcher.start_calls, 0)
        self.setUp()
        offer = self.approved()
        self.h.before_dispatch = lambda: self.h._maintain(offer["decision_deadline"])
        self.assertEqual(self.launch(offer)["error"]["outcome"], "accepted")
        self.assertEqual(self.h.launcher.start_calls, 0)

    def test_prejoin_ledger_restart_keeps_effect_and_blocks_retired_or_corrupt_writer(self):
        offer = self.approved()
        with self.assertRaises(L.U.S.H.InjectedFailure):
            self.launch(offer, fault="after_effect")
        retired = self.h
        self.h = retired.restart_from_mock_ledger(now=1000)
        self.error("resume_denied", lambda: retired.submit(C.codec.canonical(F.wire_request("launch.request", self.payload(offer))), "player-fixture", now=1000))
        self.assertEqual(self.status()["state"], "done")
        self.assertEqual(self.launch(offer)["result"]["status"], "started")
        self.assertEqual(self.h.launcher.start_calls, 1)
        self.h = self.h.restart_from_mock_ledger(now=1000, intact=False)
        self.error("temporarily_unavailable", lambda: self.launch(offer))
        self.error("temporarily_unavailable", self.status)

    def test_dispatch_crash_without_port_evidence_is_conservative_unknown(self):
        offer = self.approved()
        with self.assertRaises(L.U.S.H.InjectedFailure):
            self.launch(offer, fault="after_dispatch")
        self.h = self.h.restart_from_mock_ledger(now=1000)
        self.assertEqual(self.launch(offer)["error"]["outcome"], "unknown")
        self.assertEqual(self.status()["state"], "pending")
        self.assertEqual(self.h.launcher.start_calls, 0)

    def test_status_ownership_and_history_do_not_disclose_secrets_or_reauthorize(self):
        offer = self.approved()
        original = self.launch(offer)
        self.error("permission_denied", lambda: self.status(credential="agent-identity"))
        self.send("permission.revoke", {"object_type": "grant", "object_id": "grant-1", "expected_revision": 1}, rid="revoke")
        self.h.launcher.registration["revision"] = 2
        self.assertEqual(self.launch(offer), original)
        view = self.status()
        self.assertEqual(view["state"], "done")
        self.assertEqual(set(view), {"operation", "request_id", "state", "outcome_ref"})
        self.assertEqual(self.h.launcher.start_calls, 1)

    def test_invitation_delivery_requires_fresh_identity_of_the_registered_device(self):
        offer = self.approved()
        self.launch(offer)
        self.h.identities["agent-identity"]["device_id"] = "device-b"
        self.error("permission_denied", lambda: self.invite(offer))
        self.h.identities["agent-identity"]["device_id"] = "device-a"
        self.invite(offer)
        self.h.identities["agent-identity"]["fresh"] = False
        self.assertEqual(self.invite(offer)["status"], "completed_without_secret")

    def test_launched_device_binding_survives_join_and_same_device_resume(self):
        self.f = F.core_fixture(["core.session", "core.events", "resume"])
        self.h = L.LaunchHarness(self.f)
        offer = self.approved()
        self.launch(offer)
        invitation = self.invite(offer)
        self.send("session.join", {key: invitation[key] for key in ("invitation_id", "join_intent")}, invitation["invitation_credential"])
        self.h.finish_admission(now=1000)
        self.h = self.h.restart_from_mock_ledger(now=1000)
        result = self.send("session.resume", {"session_id": "s1", "expected_generation": 1, "device_id": "device-a"}, "agent-identity")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["session"]["controller_device"], "device-a")
        self.assertEqual(self.h.launcher.start_calls, 1)

    def test_two_threads_cannot_start_twice_with_same_or_different_request_ids(self):
        for same in (True, False):
            self.setUp()
            offer = self.approved()
            barrier = Barrier(2)
            def send(index):
                barrier.wait(timeout=5)
                try:
                    return self.launch(offer, rid="race" if same else "race-" + str(index))["result"]["status"]
                except C.ContractError as error:
                    return error.code
            with ThreadPoolExecutor(max_workers=2) as workers:
                outcomes = list(workers.map(send, range(2)))
            self.assertEqual(sorted(outcomes), ["started", "started"] if same else ["id_conflict", "started"])
            self.assertEqual(self.h.launcher.start_calls, 1)
            self.assertEqual(len(self.h.launcher.effects), 1)

    def test_launch_composes_with_resource_and_presentation_readiness(self):
        from test_design_assets import asset
        self.f = F.core_fixture(["core.session", "core.events", "avatar", "assets", "presentation"])
        manifest, response = asset("launch-avatar", self.f["game"])
        self.f["descriptor"]["avatar_requirements"] = {"accepted_formats": [L.A.PORTS.MEDIA]}
        self.f["requested"].update(forced_avatar={"kind": "manifest", "manifest": manifest},
                                  presentation_terms={"mode": "hide_desktop", "device_id": "device-a"})
        self.h = L.LaunchHarness(self.f)
        self.h.resources.responses[manifest["locator"]] = response
        self.h.resources.renderer_profiles["device-a"] = {L.A.PORTS.PROFILE}
        observation = self.h.enroll_device("device-a")
        self.h.identities["agent-identity"]["device_id"] = "device-a"
        offer = self.approved()
        self.launch(offer)
        invitation = self.send("invitation.redeem", {"offer_id": offer["offer_id"], "join_intent": {"scope_digest": offer["scope_digest"],
            "selected_device": "device-a", "presentation_observation": observation}}, "agent-identity")
        payload = {key: invitation[key] for key in ("invitation_id", "join_intent")}
        self.send("session.join", payload, invitation["invitation_credential"])
        self.assertFalse(self.h.finish_admission(now=1000)["ready"])
        self.send("asset.resolve", {"session_id": "s1", "scope_digest": offer["scope_digest"], "manifest": manifest}, "resource-fixture")
        self.assertFalse(self.h.finish_admission(now=1000)["ready"])
        self.send("presentation.acquire", self.h.state["presentation_jobs"]["admission-s1"]["acquire"], "presentation-fixture", rid="admission-s1")
        self.assertTrue(self.h.finish_admission(now=1000)["ready"])
        self.assertEqual(self.send("session.join", payload, invitation["invitation_credential"])["status"], "ready")

    def test_wire_shape_forbids_command_arguments_and_required_unknown_extension(self):
        offer = self.approved()
        request = F.wire_request("launch.request", {**self.payload(offer), "command": "not-an-allowed-field"})
        self.error("invalid_message", lambda: self.h.submit(C.codec.canonical(request), "player-fixture", now=1000))
        request = F.wire_request("launch.request", self.payload(offer))
        request["extensions"] = {"fixture.exec": {"version": "1", "required": True, "value": {}}}
        self.error("feature_unsupported", lambda: self.h.submit(C.codec.canonical(request), "player-fixture", now=1000))
        self.assertEqual(self.h.launcher.start_calls, 0)

    def test_port_exception_or_malformed_receipt_cannot_relabel_dispatched_request(self):
        for bad_query in (False, True):
            self.setUp()
            offer = self.approved()
            with patch.object(self.h.launcher, "query", return_value={}) if bad_query else patch.object(self.h.launcher, "start", side_effect=RuntimeError("fixture port failure")):
                reply = self.launch(offer)
            self.assertEqual(reply["error"]["outcome"], "unknown")
            self.assertEqual(self.h.state["launch_records"]["r1"]["state"], "pending")
            calls = self.h.launcher.start_calls
            self.assertEqual(self.launch(offer)["error"]["outcome"], "unknown")
            self.assertEqual(self.h.launcher.start_calls, calls)

    def test_lost_process_before_join_neither_leaks_secret_nor_autostarts(self):
        offer = self.approved()
        self.launch(offer)
        invitation = self.invite(offer)
        self.h.launcher.running = None
        self.assertEqual(self.invite(offer)["status"], "completed_without_secret")
        payload = {key: invitation[key] for key in ("invitation_id", "join_intent")}
        self.error("temporarily_unavailable", lambda: self.send("session.join", payload, invitation["invitation_credential"]))
        self.assertEqual(self.h.launcher.start_calls, 1)
        self.assertIsNone(self.h.session)

    def test_process_loss_during_preparation_cannot_commit_ready(self):
        offer = self.approved()
        self.launch(offer)
        invitation = self.invite(offer)
        payload = {key: invitation[key] for key in ("invitation_id", "join_intent")}
        self.send("session.join", payload, invitation["invitation_credential"])
        self.h.launcher.running = None
        session = self.h.finish_admission(now=1000)
        self.assertEqual(session["state"], "closed")
        self.assertFalse(session["ready"])
        self.assertEqual(self.send("session.join", payload, invitation["invitation_credential"])["status"], "completed_without_secret")
        self.assertEqual(self.h.launcher.start_calls, 1)


if __name__ == "__main__":
    unittest.main()
