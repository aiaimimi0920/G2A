"""玩家转发字节链：可信席位、当前成员、来源披露与消息事务，不认证真实玩家输入。"""

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


U = load("forward_session", "session_harness.py")
F = load("forward_fixture", "fixtures.py")
C, R = U.C, U.R


class PlayerForwardTests(unittest.TestCase):
    def setUp(self):
        self.f = F.core_fixture(["core.session", "core.events"])
        self.h = U.SessionHarness(self.f, {})
        self.h.player_seat_proofs = {}
        self.bob = F.principal("bob", "player")
        self.enroll(self.f["player"])

    def enroll(self, player, ref="seat-alice", **changes):
        session, scope = self.h.state["session"], self.h.state["session"]["scope"]
        record = {"proof_ref": ref, "instance": deepcopy(scope["instance"]), "session_id": session["session_id"],
            "scope_digest": C.codec.digest("scope", scope), "game": deepcopy(self.f["game"]), "player": deepcopy(player),
            "membership_revision": session["membership_revision"],
            "membership_generation": self.h.members.get(R.principal_key(player), 1),
            "issued_at": 100, "expires_at": 100000, "state": "active"}
        record.update(deepcopy(changes))
        self.h.player_seat_proofs[ref] = record
        return record

    def request(self, *, sender=None, audience=None, channel="private", message_id="p1", rid="r1", proof="seat-alice"):
        envelope = {"version": "fixture-only", "session_id": "s1", "id": message_id, "type": "chat.message",
            "sender": deepcopy(sender or self.f["player"]), "audience": deepcopy(audience or [self.f["agent"]]),
            "payload": {"channel": channel, "text": "玩家说：一起找钥匙 🗝", "source_refs": [], "provenance": []}, "extensions": {}}
        if channel == "team":
            envelope["expected_membership_revision"] = self.h.state["session"]["membership_revision"]
        return F.wire_request("player_chat.forward", {"seat_proof_ref": proof, "envelope": envelope}, rid)

    def send(self, request=None, credential="game-fixture", *, now=1000, fault=None):
        return C.codec.decode(self.h.submit(C.codec.canonical(request or self.request()), credential, now=now, fault=fault))

    def reject(self, code, request=None, credential="game-fixture", **kwargs):
        before = deepcopy(self.h.state)
        with self.assertRaises(C.ContractError) as caught:
            self.send(request, credential, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.h.state, before)

    def bind_scope(self, change):
        scope = self.h.state["session"]["scope"]
        change(scope)
        self.h.state["grant"]["scope"] = deepcopy(scope)
        self.h.state["grant"]["scope_digest"] = C.codec.digest("scope", scope)
        self.enroll(self.f["player"])

    def replace_members(self, members):
        revision = self.h.state["session"]["membership_revision"]
        payload = {"instance": self.f["scope"]["instance"], "expected_revision": revision,
                   "verified_members": members, "membership_proof_ref": "members-" + str(revision)}
        self.h.membership_proofs[payload["membership_proof_ref"]] = deepcopy(payload)
        return self.send(F.wire_request("membership.replace", payload, "replace-" + str(revision)))["result"]

    def team(self, *, approve_bob=True):
        def change(scope):
            scope["features"] = sorted(set(scope["features"]) | {"team"})
            if approve_bob:
                scope["audiences"] = sorted(scope["audiences"] + [self.bob], key=C.codec.canonical)
        self.bind_scope(change)
        self.replace_members([self.f["player"], self.f["agent"], self.bob])
        self.enroll(self.f["player"])
        self.enroll(self.bob, "seat-bob")

    def sourced(self):
        source = {"source_id": "player-source", "source_kind": "player_report", "source_principals": [self.f["player"]],
                  "original_disclosure_scope": [self.f[key] for key in ("player", "agent", "game")]}
        self.h.state["records"]["player-source"] = {"source": deepcopy(source), "controller": self.f["agent"],
            "instance": self.f["scope"]["instance"], "session_id": "s1", "evidence_ref": "source-proof", "revision": 1,
            "state": "active", "publishers": [self.f["player"]], "allowed_readers": source["original_disclosure_scope"], "expires_at": 90000}
        request = self.request()
        request["payload"]["envelope"]["payload"].update(source_refs=["player-source"], provenance=[source])
        return request

    def outer_send(self, outer, operation, payload, credential="player-fixture", *, rid="r1", now=1000, fault=None):
        return C.codec.decode(outer.submit(C.codec.canonical(F.wire_request(operation, payload, rid)), credential, now=now, fault=fault))

    def admitted(self, *, team=False, records=None, verified_bob=True, request_bob=True):
        privacy = load("forward_privacy", "privacy_harness.py")
        features = ["core.session", "core.events", "privacy-request", "resume"] + (["team"] if team else [])
        fixture = F.core_fixture(features)
        fixture["verified_audiences"] = [fixture["player"], fixture["agent"]] + ([self.bob] if verified_bob else [])
        if team and request_bob:
            fixture["requested"]["audiences"].append(self.bob)
        outer = privacy.PrivacyHarness(fixture, records or {})
        outer.launcher.running = {"binding": outer.launcher.binding(), "verified": True}
        offer = self.outer_send(outer, "offer.create", {"entry": "game", "descriptor_id": "fixture-descriptor",
            "expected_descriptor_revision": 1, "requested": fixture["requested"]}, rid="offer")["result"]
        decision = {"offer_id": offer["offer_id"], "scope_digest": offer["scope_digest"], "allow": True,
                    "remember": False, "launch_permission": False, "decision_ref": "decision"}
        outer.decisions["decision"] = {"player": fixture["player"], "payload": deepcopy(decision)}
        self.outer_send(outer, "offer.decide", decision, rid="decision")
        invitation = self.outer_send(outer, "invitation.redeem", {"offer_id": offer["offer_id"],
            "join_intent": {"scope_digest": offer["scope_digest"]}}, "agent-identity", rid="invite")["result"]
        join = {key: invitation[key] for key in ("invitation_id", "join_intent")}
        self.outer_send(outer, "session.join", join, invitation["invitation_credential"], rid="join")
        outer.finish_admission(now=1000)
        delivery = self.outer_send(outer, "session.join", join, invitation["invitation_credential"], rid="join")["result"]
        self.f, self.h = fixture, outer.session
        self.enroll(fixture["player"])
        return outer, delivery["control_credential"]

    def test_private_forward_preserves_player_identity_receipt_and_lease(self):
        request = self.request()
        lease = self.h.state["session"]["lease_deadline"]
        receipt = self.send(request)["result"]
        self.assertEqual(receipt, {"id": "p1", "accepted_at": 1000, "duplicate": False,
                                  "record_digest": C.codec.digest("message", request["payload"]["envelope"])})
        event = self.h.delivery(self.f["agent"], now=1001)[0]
        self.assertEqual(event["envelope"], request["payload"]["envelope"])
        self.assertEqual(self.h.state["session"]["lease_deadline"], lease)
        self.assertTrue(self.send(self.request(rid="transport-retry"), now=2000)["result"]["duplicate"])
        self.assertEqual(len(self.h.state["events"]), 1)
        self.assertEqual(self.h.state["session"]["lease_deadline"], lease)

    def test_game_cannot_relabel_its_companion_as_a_player(self):
        self.enroll(self.f["agent"], "agent-seat")
        self.reject("permission_denied", self.request(sender=self.f["agent"], proof="agent-seat"))

    def test_only_exact_game_management_identity_can_forward(self):
        for credential in ("agent-fixture", "player-fixture"):
            self.reject("permission_denied", credential=credential)
        self.reject("unauthenticated", credential="not-enrolled")
        self.h.credentials["wrong-game"] = {"role": "game", "principal": F.principal("other-game", "game")}
        self.reject("permission_denied", credential="wrong-game")
        self.h.credentials["game-alias"] = deepcopy(self.h.credentials["game-fixture"])
        self.assertFalse(self.send(credential="game-alias")["result"]["duplicate"])

    def test_missing_malformed_or_unbound_proof_is_uniformly_denied(self):
        self.reject("permission_denied", self.request(proof="missing"))
        original = deepcopy(self.h.player_seat_proofs["seat-alice"])
        for value in (None, {}, {**original, "proof_ref": "other"}, {**original, "extra": True}):
            with self.subTest(value=value):
                self.h.player_seat_proofs["seat-alice"] = value
                self.reject("permission_denied")

    def test_seat_binding_checks_game_scope_instance_session_and_player(self):
        original = deepcopy(self.h.player_seat_proofs["seat-alice"])
        changes = [{"game": F.principal("other", "game")}, {"scope_digest": "sha256:" + "0" * 64},
                   {"session_id": "other"}, {"player": self.bob},
                   {"instance": {**original["instance"], "epoch": "other-epoch"}}]
        for change in changes:
            with self.subTest(change=change):
                self.h.player_seat_proofs["seat-alice"] = {**original, **change}
                self.reject("permission_denied")

    def test_seat_revocation_expiry_and_future_issuance_are_checked_on_retries(self):
        self.send()
        original = deepcopy(self.h.player_seat_proofs["seat-alice"])
        for change in ({"state": "revoked"}, {"expires_at": 1000}, {"issued_at": 1001}):
            with self.subTest(change=change):
                self.h.player_seat_proofs["seat-alice"] = {**original, **change}
                self.reject("permission_denied")
        self.h.player_seat_proofs["seat-alice"] = original
        self.assertTrue(self.send()["result"]["duplicate"])

    def test_boolean_revision_or_times_cannot_impersonate_integer_attestation(self):
        original = deepcopy(self.h.player_seat_proofs["seat-alice"])
        for field in ("membership_revision", "membership_generation", "issued_at", "expires_at"):
            self.h.player_seat_proofs["seat-alice"] = {**original, field: True}
            self.reject("permission_denied")

    def test_same_message_with_refreshed_proof_or_transport_id_is_not_reaccepted(self):
        first = self.send()["result"]
        self.enroll(self.f["player"], "fresh-seat", issued_at=500)
        duplicate = self.send(self.request(proof="fresh-seat", rid="new-transport"), now=2000)["result"]
        self.assertEqual(duplicate, {**first, "duplicate": True})
        self.assertEqual(len(self.h.state["events"]), 1)

    def test_envelope_mutations_conflict_even_when_seat_reference_changes(self):
        self.send()
        for field, value in (("text", "别的内容"), ("channel", "team")):
            request = self.request()
            request["payload"]["envelope"]["payload"][field] = value
            if field == "channel":
                request["payload"]["envelope"]["expected_membership_revision"] = 1
            self.reject("id_conflict", request)
        request = self.request(audience=[self.f["player"]])
        self.reject("id_conflict", request)

    def test_optional_inner_extensions_participate_in_message_digest(self):
        request = self.request()
        extension = {"version": "1", "required": False, "value": {"n": 1}}
        request["payload"]["envelope"]["extensions"]["example.opaque"] = extension
        receipt = self.send(request)["result"]
        self.assertEqual(receipt["record_digest"], C.codec.digest("message", request["payload"]["envelope"]))
        extension["value"]["n"] = True
        self.reject("id_conflict", request)

    def test_outer_extensions_or_inline_seat_claim_cannot_bypass_contract(self):
        request = self.request()
        request["extensions"]["example.opaque"] = {"version": "1", "required": False, "value": {}}
        self.reject("invalid_message", request)
        request = self.request()
        request["payload"]["seat"] = self.h.player_seat_proofs["seat-alice"]
        self.reject("invalid_message", request)

    def test_required_extension_rejects_before_acceptance(self):
        request = self.request()
        request["payload"]["envelope"]["extensions"]["example.missing"] = {"version": "1", "required": True, "value": {}}
        self.reject("feature_unsupported", request)

    def test_negotiated_and_policy_chat_limits_apply_to_player_forward(self):
        extension = {"version": "1", "required": True, "value": {"maximum": 3}}
        self.bind_scope(lambda scope: scope["extensions"].update({"example.max-chat-bytes": extension}))
        request = self.request()
        request["payload"]["envelope"]["extensions"] = {"example.max-chat-bytes": deepcopy(extension)}
        self.reject("resource_limit", request)
        request["payload"]["envelope"]["payload"]["text"] = "你"
        self.assertFalse(self.send(request)["result"]["duplicate"])
        self.bind_scope(lambda scope: scope["effective_policy"]["extensions"].update({"example.max-chat-bytes": extension}))
        request = self.request(message_id="p2")
        request["payload"]["envelope"]["extensions"] = {"example.max-chat-bytes": deepcopy(extension)}
        self.reject("resource_limit", request)

    def test_core_private_channel_cannot_address_unapproved_or_nonmember(self):
        self.reject("permission_denied", self.request(audience=[self.bob]))
        self.h.members.pop(R.principal_key(self.f["agent"]))
        self.reject("permission_denied")

    def test_team_requires_feature_and_current_envelope_revision(self):
        self.reject("feature_unsupported", self.request(channel="team"))
        self.team()
        request = self.request(channel="team", audience=[self.bob])
        request["payload"]["envelope"]["expected_membership_revision"] -= 1
        self.reject("membership_conflict", request)
        request["payload"]["envelope"].pop("expected_membership_revision")
        self.reject("invalid_message", request)

    def test_team_player_and_companion_cannot_be_impersonated_or_private_channel_reused(self):
        self.team()
        self.reject("permission_denied", self.request(sender=self.bob, proof="seat-alice", channel="team"))
        self.reject("permission_denied", self.request(sender=self.bob, proof="seat-bob"))
        self.reject("permission_denied", self.request(audience=[self.bob]))
        result = self.send(self.request(sender=self.bob, proof="seat-bob", channel="team"))["result"]
        self.assertFalse(result["duplicate"])

    def test_membership_addition_does_not_expand_frozen_scope(self):
        self.team(approve_bob=False)
        self.reject("permission_denied", self.request(sender=self.bob, proof="seat-bob", channel="team"))
        self.reject("permission_denied", self.request(audience=[self.bob], channel="team"))

    def test_same_message_id_from_different_verified_players_has_separate_receipts(self):
        self.team()
        self.send(self.request(channel="team"))
        self.send(self.request(sender=self.bob, proof="seat-bob", channel="team"))
        self.assertEqual(len(self.h.state["receipts"]), 2)
        self.assertEqual([e["wire"]["envelope"]["sender"] for e in self.h.state["events"] if e["wire"]["envelope"]["type"] == "chat.message"],
                         [self.f["player"], self.bob])

    def test_leave_rejoin_requires_new_seat_generation_even_with_updated_revision(self):
        old = deepcopy(self.h.player_seat_proofs["seat-alice"])
        self.replace_members([self.f["agent"]])
        self.reject("permission_denied")
        self.replace_members([self.f["agent"], self.f["player"]])
        old["membership_revision"] = self.h.state["session"]["membership_revision"]
        self.h.player_seat_proofs["seat-alice"] = old
        self.reject("permission_denied")
        self.enroll(self.f["player"], "rejoined")
        self.assertEqual(self.h.player_seat_proofs["rejoined"]["membership_generation"], 2)
        self.assertFalse(self.send(self.request(proof="rejoined"))["result"]["duplicate"])

    def test_queued_team_event_not_delivered_to_rejoined_recipient(self):
        self.team()
        self.send(self.request(channel="team", audience=[self.bob]))
        self.assertTrue(any(e["envelope"]["type"] == "chat.message" for e in self.h.delivery(self.bob, now=1000)))
        self.replace_members([self.f["player"], self.f["agent"]])
        self.replace_members([self.f["player"], self.f["agent"], self.bob])
        self.assertFalse(any(e["envelope"]["type"] == "chat.message" for e in self.h.delivery(self.bob, now=1000)))

    def test_source_requires_player_publisher_and_all_plaintext_observers(self):
        request = self.sourced()
        record = self.h.state["records"]["player-source"]
        record["publishers"] = [self.f["game"]]
        self.reject("permission_denied", request)
        record["publishers"] = [self.f["player"]]
        record["allowed_readers"] = [self.f["player"], self.f["agent"]]
        self.reject("permission_denied", request)

    def test_revoked_source_blocks_new_forward_and_old_delivery_not_noncontent_receipt(self):
        request = self.sourced()
        self.send(request)
        self.h.revoke_source("player-source")
        self.assertEqual(self.h.delivery(self.f["agent"], now=1000), [])
        self.assertTrue(self.send(request)["result"]["duplicate"])
        request["payload"]["envelope"]["id"] = "p2"
        self.reject("permission_denied", request)

    def test_before_commit_and_reply_encoding_failure_leave_no_receipt_or_event(self):
        before = deepcopy(self.h.state)
        with self.assertRaises(U.S.H.InjectedFailure):
            self.send(fault="before_commit")
        self.assertEqual(self.h.state, before)
        with patch.object(self.h, "_reply", side_effect=C.ContractError("invalid_message")):
            self.reject("invalid_message")
        self.assertEqual(self.h.state, before)

    def test_after_commit_lost_reply_retries_once_without_new_lease(self):
        lease = self.h.state["session"]["lease_deadline"]
        with self.assertRaises(U.S.H.InjectedFailure):
            self.send(fault="after_commit")
        self.assertEqual(len(self.h.state["events"]), 1)
        self.assertTrue(self.send(now=2000)["result"]["duplicate"])
        self.assertEqual(self.h.state["session"]["lease_deadline"], lease)

    def test_receipt_and_outbox_limits_do_not_partially_accept(self):
        self.h.state["receipts"] = {("s1", ("fixture", "other", "player"), str(n)): {} for n in range(256)}
        self.reject("resource_limit")
        self.h.state["receipts"].clear()
        self.send()
        self.h.state["events"] *= 64
        self.reject("resource_limit", self.request(message_id="new"))
        self.assertTrue(self.send()["result"]["duplicate"])

    def test_expired_closed_revoked_or_not_ready_session_rejects_even_cached_message(self):
        self.send()
        saved = deepcopy(self.h.state)
        for field, value, code in (("ready", False, "session_not_writable"), ("lease_deadline", 1000, "session_closed")):
            self.h.state = deepcopy(saved)
            self.h.state["session"][field] = value
            self.reject(code)
        self.h.state = deepcopy(saved)
        self.h.state["session"].update(state="closed", ready=False, close_reason="left")
        self.reject("session_closed")
        self.h.state = deepcopy(saved)
        self.h.state["grant"]["state"] = "revoked"
        self.reject("grant_revoked")

    def test_version_namespace_size_and_clock_limits_apply(self):
        request = self.request()
        request["payload"]["envelope"]["session_id"] = "other"
        self.reject("permission_denied", request)
        request = self.request()
        request["version"] = request["payload"]["envelope"]["version"] = "not-supported"
        self.reject("unsupported_version", request)
        self.reject("invalid_message", now=True)
        self.bind_scope(lambda scope: scope["limits"].update(message_bytes=128))
        self.reject("resource_limit")

    def test_two_simultaneous_retries_have_one_event_and_one_receipt(self):
        barrier = Barrier(2)
        def submit():
            barrier.wait()
            return self.send()["result"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = list(pool.map(lambda _: submit(), range(2)))
        self.assertEqual(sorted(r["duplicate"] for r in receipts), [False, True])
        self.assertEqual(len(self.h.state["receipts"]), 1)
        self.assertEqual(len(self.h.state["events"]), 1)

    def test_relay_outer_credentials_never_authorize_management_forward(self):
        for role, inner in (("relay_agent", "agent"), ("relay_controller", "player")):
            with self.assertRaises(C.ContractError) as caught:
                C.authorize_relay_inner(role, inner, "player_chat.forward", ["core.session", "core.events"])
            self.assertEqual(caught.exception.code, "permission_denied")

    def test_admitted_core_session_forwards_through_privacy_composition_and_event_poll(self):
        outer, control = self.admitted()
        request = self.request()
        lease = self.h.state["session"]["lease_deadline"]
        result = self.outer_send(outer, "player_chat.forward", request["payload"], "game-fixture")["result"]
        self.assertFalse(result["duplicate"])
        self.assertEqual(self.h.state["session"]["lease_deadline"], lease)
        page = self.outer_send(outer, "session.events", {"session_id": "s1", "cursor": {
            "session_id": "s1", "instance_epoch": "epoch-1", "sequence": 0}, "page_size": 64}, control, rid="poll")["result"]
        self.assertEqual([e["envelope"]["sender"] for e in page["events"] if e["envelope"]["type"] == "chat.message"], [self.f["player"]])

    def test_admission_team_audiences_require_trusted_enrollment_and_frozen_request(self):
        for verified, requested, included in ((False, True, False), (True, False, False), (True, True, True)):
            with self.subTest(verified=verified, requested=requested):
                outer, _ = self.admitted(team=True, verified_bob=verified, request_bob=requested)
                self.assertEqual(self.bob in self.h.state["session"]["scope"]["audiences"], included)
                self.replace_members([self.f["agent"], self.f["player"], self.bob])
                self.enroll(self.bob, "seat-bob")
                request = self.request(sender=self.bob, proof="seat-bob", channel="team")
                if included:
                    self.assertFalse(self.outer_send(outer, "player_chat.forward", request["payload"], "game-fixture")["result"]["duplicate"])
                else:
                    with self.assertRaises(ValueError) as caught:
                        self.outer_send(outer, "player_chat.forward", request["payload"], "game-fixture")
                    self.assertEqual(caught.exception.code, "permission_denied")

    def test_privacy_cutoff_filters_forwarded_source_and_records_known_game_copy(self):
        request = self.sourced()
        records = deepcopy(self.h.state["records"])
        outer, control = self.admitted(records=records)
        self.outer_send(outer, "player_chat.forward", request["payload"], "game-fixture")
        poll = {"session_id": "s1", "cursor": {"session_id": "s1", "instance_epoch": "epoch-1", "sequence": 0}, "page_size": 64}
        before = self.outer_send(outer, "session.events", poll, control, rid="poll")["result"]
        receipt = self.outer_send(outer, "privacy.request", {"source_refs": ["player-source"], "desired_action": "delete_owned_copies"},
                                  "subject-fixture", rid="delete")["result"]
        self.assertEqual(receipt["status"], "partial")
        self.assertEqual(receipt["exceptions"], [{"source_id": "player-source", "reason": "outside_control"}])
        after = self.outer_send(outer, "session.events", poll, control, rid="poll")["result"]
        self.assertEqual(len(before["events"]) - len(after["events"]), 1)
        self.assertEqual(before["next_cursor"], after["next_cursor"])

    def test_mock_restart_keeps_seat_and_forward_receipts_without_duplicate_delivery(self):
        outer, _ = self.admitted()
        request = self.request()
        first = self.outer_send(outer, "player_chat.forward", request["payload"], "game-fixture")["result"]
        outer = outer.restart_from_mock_ledger(now=1000)
        self.assertEqual(outer.session.player_seat_proofs["seat-alice"], self.h.player_seat_proofs["seat-alice"])
        duplicate = self.outer_send(outer, "player_chat.forward", request["payload"], "game-fixture")["result"]
        self.assertEqual(duplicate, {**first, "duplicate": True})
        self.assertEqual(sum(item["wire"]["envelope"]["type"] == "chat.message" for item in outer.session.state["events"]), 1)


if __name__ == "__main__":
    unittest.main()
