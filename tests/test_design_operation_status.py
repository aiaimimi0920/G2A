"""原回执查询与当前业务状态分离；固定身份、单动作和内存恢复，不执行真实设备。"""

from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / "docs/protocol"


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


H = load("operation_status_control", "control_harness.py")
F = load("operation_status_fixtures", "fixtures.py")
C = H.C


class OperationStatusTests(unittest.TestCase):
    def setUp(self):
        self.start()

    def start(self, *, ready=True, high_risk=False):
        self.f = F.core_fixture(["core.session", "core.events", "actions", "resume", "handoff"])
        if high_risk:
            self.f["action"]["requires_per_action_consent"] = True
            self.f["descriptor"]["actions"] = [deepcopy(self.f["action"])]
        self.h = H.ControlHarness(self.f)
        offer = self.send("offer.create", {"entry": "companion", "descriptor_id": "fixture-descriptor",
            "expected_descriptor_revision": 1, "requested": self.f["requested"]}, rid="create")
        decision = {"offer_id": offer["offer_id"], "scope_digest": offer["scope_digest"], "allow": True,
                    "remember": False, "launch_permission": False, "decision_ref": "approve"}
        self.h.decisions["approve"] = {"player": self.f["player"], "payload": decision}
        self.send("offer.decide", decision, "player-fixture", rid="decide")
        self.invitation = self.send("invitation.redeem", {"offer_id": offer["offer_id"],
            "join_intent": {"scope_digest": offer["scope_digest"]}}, rid="redeem")
        self.join_payload = {key: self.invitation[key] for key in ("invitation_id", "join_intent")}
        self.send("session.join", self.join_payload, self.invitation["invitation_credential"], rid="join")
        if ready:
            self.h.finish_admission(now=1000)
            self.delivery = self.send("session.join", self.join_payload, self.invitation["invitation_credential"], rid="join")
            self.token = self.delivery["control_credential"]

    def send(self, operation, payload, credential="agent-identity", *, rid="r1", now=1000, fault=None):
        return C.codec.decode(self.h.submit(C.codec.canonical(F.wire_request(operation, payload, rid)),
            credential, now=now, fault=fault))["result"]

    def query(self, operation, original, credential="agent-identity", **kwargs):
        return self.send("operation.get", {"operation": operation, "original_request_id": original}, credential, **kwargs)

    def close(self, credential="player-fixture", **kwargs):
        return self.send("session.close", {"session_id": "s1", "reason": "left"}, credential, rid="close", **kwargs)

    def deny(self, call, code="permission_denied"):
        with self.assertRaises(C.ContractError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)

    def action(self, *, rid="transport-action", fault=None, confirmation=None):
        payload = {"version": "fixture-only", "session_id": "s1", "id": "a1", "type": "action.request",
            "sender": self.f["agent"], "audience": [self.f["player"]], "expected_capabilities_revision": 1,
            "extensions": {}, "payload": {"action": "find-key", "arguments": {"room": "hall"}, "deadline": 30000}}
        if confirmation:
            payload["payload"]["confirmation"] = confirmation
        return self.send("action.request", payload, self.token, rid=rid, fault=fault)

    def claim(self):
        return self.send("action.claim", {"session_id": "s1", "action_id": "a1", "worker": F.principal("worker-1", "service")},
                         "worker-1-fixture", rid="claim")["ticket"]

    def cancel(self):
        return self.send("action.cancel", {"version": "fixture-only", "session_id": "s1", "id": "cancel-a1",
            "type": "action.cancel", "sender": self.f["agent"], "audience": [self.f["player"]], "extensions": {},
            "payload": {"request_id": "a1"}}, self.token, rid="transport-cancel")

    def handoff(self):
        payload = {"session_id": "s1", "expected_generation": 1, "target_device": "device-b",
                   "decision_ref": "transfer-decision", "target_proof_ref": "target-proof"}
        digest = C.codec.digest("scope", self.h.session.state["session"]["scope"])
        self.h.decisions["transfer-decision"] = {"player": self.f["player"], "payload": payload, "scope_digest": digest}
        self.h.target_proofs["target-proof"] = {"agent": self.f["agent"], "device_id": "device-b", "session_id": "s1",
                                                "scope_digest": digest, "expires_at": 100000}
        self.h.identities["agent-b"] = {"role": "agent", "principal": self.f["agent"], "fresh": True,
                                        "device_id": "device-b", "expires_at": 100000}
        return self.send("session.handoff", payload, "player-fixture", rid="handoff")

    def revoke_read(self):
        return self.send("permission.revoke", {"object_type": "result_read", "object_id": "s1", "expected_revision": 1},
                         "player-fixture", rid="revoke-read")

    def test_join_done_is_not_rewritten_to_failed_after_close(self):
        self.close()
        view = self.query("session.join", "join")
        self.assertEqual((view["state"], view["session"]["state"]), ("done", "closed"))

    def test_join_done_is_not_rewritten_to_pending_during_later_handoff(self):
        self.handoff()
        self.assertEqual(self.query("session.join", "join")["state"], "done")

    def test_unfinished_join_closed_before_ready_is_failed(self):
        self.start(ready=False)
        self.assertEqual(self.query("session.join", "join")["state"], "pending")
        self.close()
        self.assertEqual(self.query("session.join", "join")["state"], "failed")

    def test_resume_done_survives_close_and_new_transport(self):
        self.send("session.resume", {"session_id": "s1", "expected_generation": 1}, rid="resume")
        self.close()
        self.h = self.h.restart_from_mock_ledger(now=1000)
        view = self.query("session.resume", "resume")
        self.assertEqual((view["state"], view["session"]["state"]), ("done", "closed"))

    def test_handoff_and_claim_done_survive_later_close(self):
        transfer = self.handoff()
        claim = {"session_id": "s1", "transfer_id": transfer["transfer_id"], "target_device": "device-b"}
        self.send("session.claim_control", claim, "agent-b", rid="target-claim")
        self.h.advance_transfer(transfer["transfer_id"], now=1000)
        self.close()
        self.assertEqual(self.query("session.handoff", "handoff", "player-fixture")["state"], "done")
        self.assertEqual(self.query("session.claim_control", "target-claim", "agent-b")["state"], "done")

    def test_unfinished_handoff_closed_before_ready_remains_failed(self):
        self.handoff()
        self.close()
        self.assertEqual(self.query("session.handoff", "handoff", "player-fixture")["state"], "failed")

    def test_heartbeat_lookup_returns_original_receipt_without_renewal(self):
        original = self.send("session.heartbeat", {"session_id": "s1"}, self.token, rid="heartbeat")
        view = self.query("session.heartbeat", "heartbeat", now=1001)
        self.assertEqual(view["session"], original)
        self.assertEqual(self.h.session.state["session"]["lease_deadline"], original["lease_deadline"])
        self.assertEqual(view["state"], "done")

    def test_event_poll_receipt_does_not_replay_old_event_bodies_or_renew(self):
        cursor = {"session_id": "s1", "instance_epoch": "epoch-1", "sequence": 0}
        original = self.send("session.events", {"session_id": "s1", "cursor": cursor, "page_size": 64}, self.token, rid="poll")
        self.close()
        view = self.query("session.events", "poll")
        self.assertEqual(view, {"operation": "session.events", "request_id": "poll", "state": "done", "outcome_ref": "s1"})
        self.assertEqual(self.h.session.state["session"]["lease_deadline"], original["lease_deadline"])

    def test_revoke_request_id_conflicts_across_admission_and_session_ledgers(self):
        for lower_first in (False, True):
            self.start()
            invitation = {"object_type": "invitation", "object_id": self.invitation["invitation_id"], "expected_revision": 1}
            result_read = {"object_type": "result_read", "object_id": "s1", "expected_revision": 1}
            first, second = (result_read, invitation) if lower_first else (invitation, result_read)
            original = self.send("permission.revoke", first, "player-fixture", rid="same-id")
            self.deny(lambda: self.send("permission.revoke", second, "player-fixture", rid="same-id"), "id_conflict")
            self.assertEqual(self.query("permission.revoke", "same-id", "player-fixture")["revocation"], original)

    def test_action_result_sync_failure_does_not_return_stale_view(self):
        self.action()
        ticket = self.claim()
        with self.assertRaises(H.U.S.H.InjectedFailure):
            self.h.execute("step", "worker-1", now=1000, ticket=ticket, step=1, publish_fault="before_commit")
        self.deny(lambda: self.query("action.request", "a1"), "temporarily_unavailable")
        self.assertEqual(len(self.h.session.action_model.model.world), 1)

    def test_close_receipt_is_owner_scoped(self):
        self.close()
        self.assertEqual(self.query("session.close", "close", "player-fixture")["state"], "done")
        self.deny(lambda: self.query("session.close", "close"))

    def test_agent_close_receipt_uses_identity_not_stale_writer(self):
        self.close(self.token)
        self.assertEqual(self.query("session.close", "close")["state"], "done")
        self.deny(lambda: self.query("session.close", "close", self.token), "unauthenticated")

    def test_result_read_revocation_receipt_and_prejoin_grant_receipt(self):
        revoked = self.revoke_read()
        self.assertEqual(self.query("permission.revoke", "revoke-read", "player-fixture")["revocation"], revoked)
        grant = self.h.session.state["grant"]
        revoked = self.send("permission.revoke", {"object_type": "grant", "object_id": grant["grant_id"], "expected_revision": grant["revision"]},
                            "player-fixture", rid="revoke-grant")
        self.assertEqual(self.query("permission.revoke", "revoke-grant", "player-fixture")["revocation"], revoked)

    def test_action_lookup_uses_envelope_id_and_separates_acceptance_from_effect(self):
        receipt = self.action()
        view = self.query("action.request", "a1")
        self.assertEqual((view["state"], view["action"]["state"]), ("done", "pending"))
        self.assertEqual(view["receipt"], receipt)
        self.deny(lambda: self.query("action.request", "transport-action"))
        self.assertTrue(self.action(rid="different-transport")["duplicate"])
        self.assertEqual(self.query("action.request", "a1"), view)

    def test_action_operation_name_cannot_be_relabelled(self):
        self.action()
        self.cancel()
        self.deny(lambda: self.query("action.cancel", "a1"))
        self.deny(lambda: self.query("action.request", "cancel-a1"))

    def test_cancel_lookup_reports_partial_fact_without_undo(self):
        self.action()
        ticket = self.claim()
        self.h.execute("step", "worker-1", now=1000, ticket=ticket, step=1)
        self.cancel()
        self.h.execute("finish", "worker-1", now=1000, ticket=ticket)
        view = self.query("action.cancel", "cancel-a1")
        self.assertEqual((view["state"], view["action"]["state"], view["action"]["effect"]), ("done", "cancelled", "partial"))
        self.assertEqual(len(self.h.session.action_model.model.world), 1)

    def test_unknown_effect_query_does_not_reconcile_or_repeat_effect(self):
        self.action()
        ticket = self.claim()
        with self.assertRaises(H.U.A.M.SimulatedCrash):
            self.h.execute("step", "worker-1", now=1000, ticket=ticket, step=1, crash="after_effect")
        self.close()
        view = self.query("action.request", "a1")
        self.assertEqual((view["state"], view["action"]["state"], view["action"]["effect"]), ("done", "unknown", "undetermined"))
        self.assertEqual(len(self.h.session.action_model.model.world), 1)
        self.assertEqual(self.h.session.action_model.model.action["journal"], {})

    def test_committed_action_view_retains_result_after_close(self):
        self.action()
        ticket = self.claim()
        for step in (1, 2):
            self.h.execute("step", "worker-1", now=1000, ticket=ticket, step=step)
        fact = {"state": "succeeded", "effect": "committed", "steps": [
            {"step": n, "effect": "committed", "evidence_ref": ticket["proof_ref"] + "-step-" + str(n)} for n in (1, 2)],
            "result": {"item": "gold-key"}}
        self.send("action.commit_result", {"ticket": ticket, "fact": fact}, "worker-1-fixture", rid="commit")
        self.close()
        self.assertEqual(self.query("action.request", "a1")["action"]["known_result"], {"item": "gold-key"})

    def test_action_view_does_not_bypass_result_revocation(self):
        self.action()
        self.cancel()
        self.revoke_read()
        for operation, original in (("action.request", "a1"), ("action.cancel", "cancel-a1"), ("action.request", "missing")):
            self.deny(lambda: self.query(operation, original))

    def test_action_view_does_not_bypass_retention(self):
        self.action()
        self.h.identities["agent-identity"]["expires_at"] = 900000
        self.close()
        self.deny(lambda: self.query("action.request", "a1", now=self.h.session.action_model.read_until + 1))

    def test_action_view_does_not_revive_after_member_reentry(self):
        self.action()
        key = H.R.principal_key(self.f["agent"])
        self.h.session.members.pop(key)
        self.deny(lambda: self.query("action.request", "a1"))
        self.h.session.members[key] = 2
        self.deny(lambda: self.query("action.request", "a1"))

    def replace_members(self, members, revision, *, fault=None):
        proof = "read-boundary-members-" + str(revision)
        payload = {"instance": self.f["scope"]["instance"], "expected_revision": revision,
                   "verified_members": members, "membership_proof_ref": proof}
        self.h.session.membership_proofs[proof] = deepcopy(payload)
        return self.send("membership.replace", payload, "game-fixture", rid=proof, fault=fault)

    def direct_action_query(self, credential, **kwargs):
        return self.send("action.query", {"session_id": "s1", "action_id": "a1"}, credential, **kwargs)

    def test_direct_query_denies_departed_member_for_both_credentials(self):
        self.action()
        self.replace_members([self.f["player"]], 1)
        for credential in (self.token, self.delivery["result_read_handle"]):
            with self.subTest(credential=credential):
                self.deny(lambda: self.direct_action_query(credential))
        self.deny(lambda: self.query("action.request", "a1"))

    def test_direct_query_denies_rejoined_member_for_both_credentials(self):
        self.action()
        self.replace_members([self.f["player"]], 1)
        self.replace_members([self.f["player"], self.f["agent"]], 2)
        self.assertEqual(self.h.session.members[H.R.principal_key(self.f["agent"])], 2)
        for credential in (self.token, self.delivery["result_read_handle"]):
            with self.subTest(credential=credential):
                self.deny(lambda: self.direct_action_query(credential))
        self.deny(lambda: self.query("action.request", "a1"))

    def test_direct_query_retains_access_after_close_without_membership_change(self):
        self.action()
        self.close()
        before = deepcopy(self.h.session.state)
        expected = self.query("action.request", "a1")["action"]
        for credential in (self.token, self.delivery["result_read_handle"]):
            self.assertEqual(self.direct_action_query(credential), expected)
        self.assertEqual(self.h.session.state, before)

    def test_direct_query_and_operation_view_share_revocation_boundary(self):
        self.action()
        self.revoke_read()
        for credential in (self.token, self.delivery["result_read_handle"]):
            self.deny(lambda: self.direct_action_query(credential))
        self.deny(lambda: self.query("action.request", "a1"))

    def test_failed_membership_commit_does_not_revoke_original_result_reader(self):
        self.action()
        expected = self.direct_action_query(self.delivery["result_read_handle"])
        with self.assertRaises(H.U.S.H.InjectedFailure):
            self.replace_members([self.f["player"]], 1, fault="before_commit")
        self.assertEqual(self.h.session.members[H.R.principal_key(self.f["agent"])], 1)
        self.assertEqual(self.direct_action_query(self.delivery["result_read_handle"]), expected)

    def test_confirmation_lookup_is_player_only_and_not_a_new_confirmation(self):
        self.start(high_risk=True)
        payload = {"session_id": "s1", "action_request_id": "a1", "action": "find-key",
            "arguments_digest": C.codec.digest("action-arguments", {"room": "hall"}),
            "definition_digest": C.codec.digest("action-definition", self.f["action"]), "expires_at": 5000, "decision_ref": "confirm-decision"}
        self.h.session.action_model.decisions["confirm-decision"] = {"player": self.f["player"], "allow": True, "payload": payload}
        result = self.send("action.confirm", payload, "player-fixture", rid="confirm")
        self.action(confirmation=result["confirmation_id"])
        self.close()
        view = self.query("action.confirm", "confirm", "player-fixture")
        self.assertEqual((view["state"], view["outcome_ref"]), ("done", result["confirmation_id"]))
        self.assertEqual(len(self.h.session.action_model.confirmations), 1)
        self.assertTrue(self.h.session.action_model.confirmations[result["confirmation_id"]]["consumed"])
        self.deny(lambda: self.query("action.confirm", "confirm"))

    def test_precommit_failure_has_no_receipt_and_postcommit_loss_is_queryable(self):
        with self.assertRaises(H.U.S.H.InjectedFailure):
            self.action(fault="before_commit")
        self.deny(lambda: self.query("action.request", "a1"))
        with self.assertRaises(H.U.S.H.InjectedFailure):
            self.action(fault="after_commit")
        self.assertEqual(self.query("action.request", "a1")["state"], "done")
        self.assertEqual(self.h.session.action_model.model.world, {})

    def test_privileged_receipts_and_arbitrary_missing_ids_are_not_exposed(self):
        self.action()
        self.claim()
        for operation, original in (("action.claim", "claim"), ("action.commit_result", "commit"),
                ("privacy.request", "private"), ("relay.call", "relay"), ("session.close", "missing")):
            for identity in ("agent-identity", "player-fixture"):
                self.deny(lambda: self.query(operation, original, identity))

    def test_control_and_worker_credentials_cannot_enter_identity_query_route(self):
        self.action()
        for identity in (self.token, self.delivery["result_read_handle"], "worker-1-fixture", "game-fixture"):
            self.deny(lambda: self.query("action.request", "a1", identity), "permission_denied" if identity == "game-fixture" else "unauthenticated")

    def test_expired_identity_cannot_read_even_nonsecret_receipts(self):
        self.h.identities["agent-identity"]["expires_at"] = 1000
        self.deny(lambda: self.query("session.join", "join"), "unauthenticated")

    def test_full_control_ledger_does_not_block_read_or_consume_new_slots(self):
        self.send("session.heartbeat", {"session_id": "s1"}, self.token, rid="heartbeat")
        controls = self.h.session.state["session_controls"]
        while len(controls) < 256:
            controls[("fixture", "unused", str(len(controls)))] = {}
        for _ in range(3):
            self.assertEqual(self.query("session.heartbeat", "heartbeat")["state"], "done")
        self.assertEqual(len(self.h.session.state["session_controls"]), 256)

    def test_mock_restart_preserves_receipts_but_untrusted_ledger_is_denied(self):
        self.action()
        self.h = self.h.restart_from_mock_ledger(now=1000)
        self.assertEqual(self.query("action.request", "a1")["action"]["state"], "pending")
        self.h = self.h.restart_from_mock_ledger(now=1000, intact=False)
        self.deny(lambda: self.query("action.request", "a1"), "temporarily_unavailable")

    def test_query_is_read_only_and_contains_no_control_or_execution_secrets(self):
        self.action()
        ticket = self.claim()
        state = deepcopy(self.h.session.state)
        checkpoint = deepcopy(self.h.session.action_model.control_receipts)
        view = self.query("action.request", "a1")
        raw = C.codec.canonical(view)
        for secret in (self.token, self.delivery["result_read_handle"], self.invitation["invitation_credential"], ticket["proof_ref"], ticket["ticket_id"]):
            self.assertNotIn(secret.encode(), raw)
        self.assertEqual(self.h.session.state, state)
        self.assertEqual(self.h.session.action_model.control_receipts, checkpoint)


if __name__ == "__main__":
    unittest.main()
