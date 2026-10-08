"""Relay 字节链的配对、双角色、排队/领取、未知结果、撤销与假账本证明。"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import importlib.util
from itertools import permutations
from pathlib import Path
from threading import Barrier, Event
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1] / "docs/protocol"


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


H, F = load("test_relay", "relay_harness.py"), load("relay_fixture", "fixtures.py")
C, R = H.C, H.R


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.f = F.relay_fixture()
        self.h = H.RelayHarness(self.f)
        self.h._maintain(1000)
        self.counter = 0
        self.registration = {"instance": deepcopy(self.f["scope"]["instance"]),
            "relay_identity": deepcopy(self.f["scope"]["binding"]["relay_identity"]), "relay_origin": self.f["relay_origin"],
            "agent_principals": [deepcopy(self.f["agent"])], "control_principals": [deepcopy(self.f["player"])],
            "registration_expiry": 90000, "pairing_proof_ref": "pairing-fixture", "limits": deepcopy(self.f["scope"]["limits"])}

    def send(self, operation, payload, credential, *, rid="r1", now=1000, fault=None, extensions=None):
        request = F.wire_request(operation, payload, rid)
        request["extensions"] = extensions or {}
        return C.codec.decode(self.h.submit(C.codec.canonical(request), credential, now=now, fault=fault))

    def register(self, *, fault=None):
        result = self.send("relay.register", self.registration, "relay-player-identity", rid="registration", fault=fault)["result"]
        self.mid = result["mailbox_id"]
        self.tokens = {role: self.h.credential_for(self.mid, "relay-" + role + "-identity", now=1000)
                       for role in ("player", "agent", "game")}
        return result

    @property
    def box(self):
        return self.h.state["mailboxes"][self.mid]

    def call_payload(self, inner=None, *, relay_id="relay-1", proof="inner-agent-fixture", deadline=20000, revision=1):
        inner = inner or F.wire_request("describe", {"instance": self.f["scope"]["instance"]}, "describe")
        return {"mailbox_id": self.mid, "call": {"relay_request_id": relay_id, "operation_request": deepcopy(inner),
            "inner_auth_proof": proof, "deadline": deadline, "route_revision": revision}}

    def call(self, payload=None, *, role="agent", rid="outer", now=1000, fault=None, credential=None, extensions=None):
        return self.send("relay.call", payload or self.call_payload(), credential or self.tokens[role],
                         rid=rid, now=now, fault=fault, extensions=extensions)

    def pull(self, nonce="pull-1", maximum=1, *, rid=None, now=1000, fault=None):
        return self.send("relay.pull", {"mailbox_id": self.mid, "pull_nonce": nonce, "maximum_items": maximum},
                         self.tokens["game"], rid=rid or nonce, now=now, fault=fault)["result"]["claims"]

    def dispatch(self, claim, *, now=1000, fault=None):
        return C.codec.decode(self.h.dispatch_claim(C.codec.canonical(claim), self.tokens["game"], now=now, fault=fault))

    def reply(self, claim, reply, *, rid="reply-1", now=1000, fault=None, credential=None):
        return self.send("relay.reply", {"mailbox_id": self.mid, "claim_id": claim["claim_id"], "reply": reply},
                         credential or self.tokens["game"], rid=rid, now=now, fault=fault)

    def revoke(self, *, rid="revoke", revision=1, now=1000, fault=None):
        return self.send("relay.revoke", {"mailbox_id": self.mid, "expected_route_revision": revision},
                         "relay-player-identity", rid=rid, now=now, fault=fault)

    def rejected(self, code, function):
        try:
            value = function()
        except C.ContractError as error:
            self.assertEqual(error.code, code)
            return None
        self.assertEqual(value["error"]["code"], code)
        return value["error"]

    def roundtrip(self, operation, payload, *, role="agent", proof="inner-agent-fixture", inner_id=None):
        self.counter += 1
        rid = "rt-" + str(self.counter)
        call = self.call_payload(F.wire_request(operation, payload, inner_id or rid), relay_id=rid, proof=proof)
        self.assertEqual(self.call(call, role=role)["result"]["state"], "queued")
        claim = self.pull("pull-" + rid)[0]
        reply = self.dispatch(claim)
        self.assertEqual(self.reply(claim, reply, rid="reply-" + rid)["result"], {"status": "accepted"})
        self.assertEqual(self.call(call, role=role)["result"]["reply"], reply)
        return reply, call, claim

    def admit(self):
        self.register()
        self.h.game.launcher.running = {"binding": self.h.game.launcher.binding(), "verified": True}
        offer = self.roundtrip("offer.create", {"entry": "companion", "descriptor_id": "fixture-descriptor",
            "expected_descriptor_revision": 1, "requested": self.f["requested"]})[0]["result"]
        decision = {"offer_id": offer["offer_id"], "scope_digest": offer["scope_digest"], "allow": True,
                    "remember": False, "launch_permission": False, "decision_ref": "decision"}
        self.h.game.decisions["decision"] = {"player": self.f["player"], "payload": deepcopy(decision)}
        self.roundtrip("offer.decide", decision, role="player", proof="inner-player-fixture")
        invitation = self.roundtrip("invitation.redeem", {"offer_id": offer["offer_id"],
            "join_intent": {"scope_digest": offer["scope_digest"]}})[0]["result"]
        self.h.port.enroll("inner-invitation", invitation["invitation_credential"])
        join = {key: invitation[key] for key in ("invitation_id", "join_intent")}
        self.roundtrip("session.join", join, proof="inner-invitation", inner_id="join")
        self.h.game.finish_admission(now=1000)
        joined = self.roundtrip("session.join", join, proof="inner-invitation", inner_id="join")[0]["result"]
        self.h.port.enroll("inner-control", joined["control_credential"])
        self.h.port.enroll("inner-results", joined["result_read_handle"])
        return joined

    def chat(self, message_id="chat-1"):
        return {"version": "fixture-only", "session_id": "s1", "id": message_id, "type": "chat.message",
            "sender": self.f["agent"], "audience": [self.f["player"]], "extensions": {},
            "payload": {"channel": "private", "text": "经中继一起找钥匙 🗝", "source_refs": [], "provenance": []}}

    def test_catalog_has_37_real_facade_operations_not_37_relay_lanes(self):
        self.assertEqual(H.RelayHarness.WIRE_OPERATIONS, set(C.catalog.OPERATIONS))
        self.assertEqual(len(H.RelayHarness.RELAY), 5)
        self.register()
        self.rejected("unauthenticated", lambda: self.send("describe", {"instance": self.f["scope"]["instance"]}, self.tokens["agent"]))

    def test_register_dedup_and_three_separate_recipient_deliveries(self):
        result = self.register()
        self.assertEqual(result, self.register())
        self.assertEqual(set(result), {"mailbox_id", "route_revision", "registration_expiry"})
        self.assertEqual(len(self.h.state["mailboxes"]), 1)
        self.assertEqual(len(set(self.tokens.values())), 3)
        for role, token in self.tokens.items():
            self.assertEqual(self.h.state["credentials"][token]["principal"], self.f[role])
        self.rejected("unauthenticated", lambda: self.h.credential_for(self.mid, self.mid, now=1000))
        self.rejected("permission_denied", lambda: self.h.credential_for(self.mid, self.tokens["player"], now=1000))

    def test_register_requires_exact_instance_origin_operator_and_participants(self):
        for field, value in (("instance", {**self.registration["instance"], "epoch": "wrong"}),
                ("relay_origin", "https://attacker.invalid/forward"), ("relay_identity", F.principal("other", "service")),
                ("agent_principals", [F.principal("other", "agent")]), ("control_principals", [F.principal("bob", "player")]),
                ("limits", {**self.registration["limits"], "message_bytes": 65535})):
            with self.subTest(field=field):
                payload = {**deepcopy(self.registration), field: value}
                self.rejected("permission_denied", lambda: self.send("relay.register", payload, "relay-player-identity"))
                self.assertFalse(self.h.state["mailboxes"])

    def test_pairing_current_controller_time_and_typed_evidence(self):
        original = deepcopy(self.h.pairings["pairing-fixture"])
        for changes in ({"controller": self.f["agent"]}, {"state": "revoked"}, {"issued_at": 1001},
                        {"expires_at": 1000}, {"expires_at": True}, {"proof_ref": "other"}):
            with self.subTest(changes=changes):
                self.h.pairings["pairing-fixture"] = {**deepcopy(original), **changes}
                self.rejected("permission_denied", self.register)
        self.h.pairings["pairing-fixture"] = original
        self.registration["registration_expiry"] = 1000
        self.rejected("request_expired", self.register)

    def test_pairing_not_reused_and_registration_id_cannot_change_content(self):
        self.register()
        self.rejected("id_conflict", lambda: self.send("relay.register", self.registration, "relay-player-identity", rid="other"))
        self.registration["registration_expiry"] += 1
        self.rejected("id_conflict", self.register)

    def test_register_transaction_includes_credentials_and_receipt(self):
        before = deepcopy(self.h.state)
        with self.assertRaises(H.InjectedFailure):
            self.register(fault="before_commit")
        self.assertEqual(before, self.h.state)
        with self.assertRaises(H.InjectedFailure):
            self.register(fault="after_commit")
        self.assertEqual(len(self.h.state["credentials"]), 3)
        self.register()
        self.assertEqual(len(self.h.state["registrations"]), 1)

    def test_serialization_failure_rolls_back_new_mailbox_and_secrets(self):
        with patch.object(C, "validate_reply", side_effect=C.ContractError("invalid_message")):
            self.rejected("invalid_message", self.register)
        self.assertFalse(self.h.state["mailboxes"])
        self.assertFalse(self.h.state["credentials"])

    def test_outer_roles_cannot_exchange_submit_pull_or_register_rights(self):
        self.register()
        self.rejected("permission_denied", lambda: self.call(credential=self.tokens["game"]))
        self.rejected("permission_denied", lambda: self.send("relay.pull", {"mailbox_id": self.mid, "pull_nonce": "p", "maximum_items": 1}, self.tokens["agent"]))
        self.rejected("permission_denied", lambda: self.send("relay.register", self.registration, self.tokens["player"]))
        self.rejected("permission_denied", lambda: self.call(credential="relay-agent-identity"))
        self.rejected("unauthenticated", lambda: self.call(credential=self.mid))
        self.rejected("permission_denied", lambda: self.send("relay.revoke", {"mailbox_id": self.mid, "expected_route_revision": 1}, self.tokens["agent"]))

    def test_outer_credential_binding_and_bool_time_cannot_be_forged(self):
        self.register()
        token = self.tokens["agent"]
        original = deepcopy(self.h.state["credentials"][token])
        for changes, code in (({"relay_origin": "https://other.invalid"}, "permission_denied"),
                ({"instance": {**self.h.instance, "epoch": "wrong"}}, "permission_denied"),
                ({"mailbox_id": "other"}, "permission_denied"), ({"route_revision": True}, "unauthenticated"),
                ({"expires_at": True}, "unauthenticated"), ({"principal": F.principal("bob", "agent")}, "permission_denied")):
            with self.subTest(changes=changes):
                self.h.state["credentials"][token] = {**deepcopy(original), **changes}
                self.rejected(code, self.call)
        self.h.state["credentials"][token] = original
        self.assertFalse(self.box["requests"])

    def test_call_dedup_freezes_inner_id_deadline_and_original_proof(self):
        self.register()
        self.call(self.call_payload(deadline=100000))
        self.h.port.enroll("fresh-agent", "agent-identity")
        repeated = self.call_payload(deadline=200000, proof="fresh-agent")
        self.assertEqual(self.call(repeated, rid="outer-new", now=1001)["result"]["state"], "queued")
        record = next(iter(self.box["requests"].values()))
        self.assertEqual(record["call"]["deadline"], 31000)
        self.assertEqual(record["call"]["inner_auth_proof"], "inner-agent-fixture")
        self.assertEqual(len(self.box["requests"]), 1)
        repeated["call"]["operation_request"]["request_id"] = "changed"
        self.rejected("id_conflict", lambda: self.call(repeated, now=1001))

    def test_call_commit_fault_rolls_back_or_recovers_one_queued_record(self):
        self.register()
        with self.assertRaises(H.InjectedFailure):
            self.call(fault="before_commit")
        self.assertFalse(self.box["requests"])
        with self.assertRaises(H.InjectedFailure):
            self.call(fault="after_commit")
        self.assertEqual(self.call()["result"]["state"], "queued")
        self.assertEqual(len(self.box["requests"]), 1)

    def test_minimal_core_profile_does_not_gain_actions_from_relay(self):
        self.f = F.relay_fixture(["core.session", "core.events"])
        self.h = H.RelayHarness(self.f)
        self.registration["limits"] = deepcopy(self.f["scope"]["limits"])
        self.register()
        query = F.wire_request("action.query", {"session_id": "s1", "action_id": "a1"})
        self.rejected("feature_unsupported", lambda: self.call(self.call_payload(query)))
        self.assertFalse(self.box["requests"])

    def test_single_call_reserves_space_for_claim_and_long_pull_correlation(self):
        self.register()
        payload = self.call_payload()
        raw = C.codec.canonical(F.wire_request("relay.call", payload, "outer"))
        self.box["registration"]["limits"]["message_bytes"] = len(raw) + 1
        self.rejected("resource_limit", lambda: self.call(payload))
        self.assertFalse(self.box["requests"])

    def test_call_inner_principal_and_role_are_not_replaced_by_outer(self):
        self.register()
        self.rejected("permission_denied", lambda: self.call(self.call_payload(proof="inner-player-fixture")))
        self.rejected("permission_denied", lambda: self.call(role="player"))
        self.h.port.enroll("inner-game", "game-fixture")
        self.rejected("permission_denied", lambda: self.call(self.call_payload(proof="inner-game")))
        self.assertFalse(self.box["requests"])

    def test_inner_proof_audience_instance_state_and_current_identity(self):
        self.register()
        original = deepcopy(self.h.port.proofs["inner-agent-fixture"])
        for changes, code in (({"audience": "https://other.invalid"}, "permission_denied"),
                ({"instance": {**self.h.instance, "epoch": "wrong"}}, "permission_denied"),
                ({"state": "revoked"}, "unauthenticated"), ({"expires_at": 1000}, "unauthenticated"),
                ({"issued_at": True}, "unauthenticated"), ({"proof_ref": "other"}, "permission_denied"),
                ({"principal": F.principal("bob", "agent")}, "permission_denied")):
            with self.subTest(changes=changes):
                self.h.port.proofs["inner-agent-fixture"] = {**deepcopy(original), **changes}
                self.rejected(code, self.call)
        self.h.port.proofs["inner-agent-fixture"] = original
        self.assertFalse(self.box["requests"])

    def test_inner_conditional_checks_and_outer_version_are_not_bypassed(self):
        self.register()
        decision = F.wire_request("offer.decide", {"offer_id": "o", "scope_digest": "0" * 64,
            "allow": True, "remember": True, "launch_permission": False, "decision_ref": "d"})
        self.rejected("invalid_message", lambda: self.call(self.call_payload(decision, proof="inner-player-fixture"), role="player"))
        payload = self.call_payload()
        payload["call"]["operation_request"]["version"] = "wrong"
        self.rejected("unsupported_version", lambda: self.call(payload))

    def test_management_local_privacy_and_nested_relay_not_in_inner_schema(self):
        self.register()
        for operation, payload in (("launch.request", {"offer_id": "o", "application_registration": "a", "launch_permission_ref": "l"}),
                ("privacy.receipt", {"privacy_request_id": "p"}), ("action.claim", {"session_id": "s1", "action_id": "a", "worker": self.f["game"]}),
                ("relay.revoke", {"mailbox_id": self.mid, "expected_route_revision": 1})):
            with self.subTest(operation=operation):
                self.rejected("invalid_message", lambda: self.call(self.call_payload(F.wire_request(operation, payload))))
        self.assertFalse(self.box["requests"])

    def test_route_revision_extensions_and_message_limits_are_checked(self):
        self.register()
        self.rejected("approval_stale", lambda: self.call(self.call_payload(revision=2)))
        ext = {"example.relay": {"version": "1", "required": True, "value": {}}}
        self.rejected("feature_unsupported", lambda: self.call(extensions=ext))
        ext["example.relay"]["required"] = False
        self.call(extensions=ext)
        self.rejected("id_conflict", self.call)
        self.box["registration"]["limits"]["message_bytes"] = 100
        self.rejected("resource_limit", self.call)

    def test_queue_capacity_rejects_new_but_not_duplicate_request(self):
        self.register()
        for i in range(self.h.MAX_INFLIGHT):
            self.call(self.call_payload(relay_id="q-" + str(i)))
        self.rejected("resource_limit", lambda: self.call(self.call_payload(relay_id="overflow")))
        self.call(self.call_payload(relay_id="q-0"))
        self.assertEqual(len(self.box["requests"]), self.h.MAX_INFLIGHT)

    def test_queued_expiry_proves_only_this_relay_path_not_dispatched(self):
        self.register()
        payload = self.call_payload(deadline=1001)
        self.call(payload)
        error = self.rejected("relay_not_dispatched", lambda: self.call(payload, now=1001))
        self.assertEqual(error["outcome"], "not_accepted")
        self.assertEqual(self.pull(now=1001), [])
        payload["call"]["deadline"] = 80000
        self.rejected("relay_not_dispatched", lambda: self.call(payload, now=1001))
        self.assertEqual(self.h.port.dispatch_calls, 0)

    def test_claimed_expiry_is_unknown_even_if_game_was_never_called(self):
        self.register()
        payload = self.call_payload(deadline=1001)
        self.call(payload)
        claim = self.pull()[0]
        error = self.rejected("transport_timeout", lambda: self.call(payload, now=1001))
        self.assertEqual(error["outcome"], "unknown")
        self.rejected("request_gone", lambda: self.dispatch(claim, now=1001))
        self.rejected("request_gone", lambda: self.pull(now=1001))
        self.assertEqual(self.h.port.dispatch_calls, 0)

    def test_pull_nonce_replay_empty_receipt_and_no_requeue(self):
        self.register()
        self.assertEqual(self.pull("empty"), [])
        self.call()
        self.assertEqual(self.pull("empty", rid="new-outer"), [])
        claims = self.pull()
        self.assertEqual(self.pull(rid="new-pull-id"), claims)
        self.assertEqual(self.pull("next"), [])
        self.assertEqual(len(self.box["claims"]), 1)
        self.rejected("id_conflict", lambda: self.pull(maximum=2))

    def test_pull_limits_and_nonce_receipts_are_bounded(self):
        self.register()
        self.rejected("resource_limit", lambda: self.pull(maximum=17))
        with patch.object(self.h, "MAX_PULLS", 1):
            self.pull()
            self.rejected("resource_limit", lambda: self.pull("new"))
            self.assertEqual(self.pull(), [])

    def test_pull_batch_is_bounded_by_encoded_reply_bytes_not_only_item_count(self):
        self.register()
        self.box["registration"]["limits"]["message_bytes"] = 2200
        for i in range(4):
            inner = F.wire_request("describe", {"instance": self.f["scope"]["instance"]}, "large-" + str(i))
            inner["extensions"] = {"example.padding": {"version": "1", "required": False, "value": "x" * 550}}
            self.call(self.call_payload(inner, relay_id="large-" + str(i)))
        claims = self.pull(maximum=4)
        encoded = C.codec.canonical({"request_id": "pull-1", "result": {"claims": claims}})
        self.assertLessEqual(len(encoded), 2200)
        self.assertTrue(0 < len(claims) < 4)
        self.assertEqual(sum(item["state"] == "queued" for item in self.box["requests"].values()), 4 - len(claims))

    def test_revoke_has_reserved_receipt_even_when_ordinary_control_slots_are_full(self):
        self.register()
        self.call()
        for i in range(512):
            self.box["controls"][(R.principal_key(self.f["game"]), "relay.reply", "full-" + str(i))] = {
                "digest": "0" * 64, "result": {"status": "accepted"}}
        self.assertEqual(self.revoke()["result"]["state"], "closed")
        self.assertEqual(len(self.box["controls"]), 513)
        for i in range(3):
            self.revoke(rid="closed-" + str(i), revision=2)
        self.assertEqual(len(self.box["controls"]), 513)

    def test_fifo_with_per_principal_round_robin_fairness(self):
        self.register()
        for rid in ("a1", "a2", "a3"):
            self.call(self.call_payload(relay_id=rid))
        self.call(self.call_payload(relay_id="p1", proof="inner-player-fixture"), role="player")
        ids = [self.pull("p-" + str(i))[0]["call"]["relay_request_id"] for i in range(4)]
        self.assertEqual(ids, ["a1", "p1", "a2", "a3"])

    def test_pull_commit_failure_does_not_publish_half_claim(self):
        self.register()
        self.call()
        before = deepcopy(self.box)
        with self.assertRaises(H.InjectedFailure):
            self.pull(fault="before_commit")
        self.assertEqual(self.box, before)
        with self.assertRaises(H.InjectedFailure):
            self.pull(fault="after_commit")
        self.assertEqual(self.pull()[0]["claim_id"], "claim-1")
        self.assertEqual(len(self.box["claims"]), 1)

    def test_reply_owner_request_correlation_and_schema(self):
        self.register()
        self.call()
        claim = self.pull()[0]
        reply = self.dispatch(claim)
        self.rejected("permission_denied", lambda: self.reply(claim, reply, credential=self.tokens["agent"]))
        self.rejected("invalid_message", lambda: self.reply(claim, {**reply, "request_id": "wrong"}))
        self.rejected("invalid_message", lambda: self.reply(claim, {"request_id": reply["request_id"], "result": {"redirect": "https://other.invalid"}}))
        self.rejected("permission_denied", lambda: self.reply({**claim, "claim_id": "missing"}, reply))
        self.assertEqual(next(iter(self.box["requests"].values()))["state"], "claimed")

    def test_reply_exact_duplicate_and_conflicting_reply(self):
        self.register()
        self.call()
        claim = self.pull()[0]
        reply = self.dispatch(claim)
        self.assertEqual(self.reply(claim, reply), self.reply(claim, reply))
        self.assertEqual(self.reply(claim, reply, rid="reply-new")["result"], {"status": "accepted"})
        changed = deepcopy(reply)
        changed["result"]["revision"] += 1
        self.rejected("reply_conflict", lambda: self.reply(claim, changed, rid="conflict"))
        self.assertEqual(self.call()["result"]["reply"], reply)

    def test_reply_must_match_existing_trusted_game_journal_before_first_accept(self):
        self.register()
        self.call()
        claim = self.pull()[0]
        reply = self.dispatch(claim)
        reply["result"]["revision"] += 1
        self.rejected("reply_conflict", lambda: self.reply(claim, reply))
        self.assertEqual(next(iter(self.box["requests"].values()))["state"], "claimed")

    def test_inner_reply_reserves_space_for_outer_result_before_accept(self):
        self.register()
        self.call()
        claim = self.pull()[0]
        reply = self.dispatch(claim)
        request = F.wire_request("relay.reply", {"mailbox_id": self.mid, "claim_id": claim["claim_id"], "reply": reply}, "reply-1")
        self.box["registration"]["limits"]["message_bytes"] = len(C.codec.canonical(request)) + 1
        self.rejected("resource_limit", lambda: self.reply(claim, reply))
        self.assertEqual(next(iter(self.box["requests"].values()))["state"], "claimed")

    def test_reply_commit_fault_preserves_actual_game_result(self):
        self.register()
        self.call()
        claim = self.pull()[0]
        reply = self.dispatch(claim)
        with self.assertRaises(H.InjectedFailure):
            self.reply(claim, reply, fault="before_commit")
        self.assertEqual(next(iter(self.box["requests"].values()))["state"], "claimed")
        with self.assertRaises(H.InjectedFailure):
            self.reply(claim, reply, fault="after_commit")
        self.assertEqual(self.call()["result"]["reply"], reply)
        self.assertEqual(self.h.port.dispatch_calls, 1)

    def test_replied_claim_not_reissued_or_late_acknowledged_after_deadline(self):
        self.register()
        payload = self.call_payload(deadline=1001)
        self.call(payload)
        claim = self.pull()[0]
        reply = self.dispatch(claim)
        self.reply(claim, reply)
        self.rejected("request_gone", lambda: self.reply(claim, reply, now=1001))
        self.rejected("request_gone", lambda: self.pull(now=1001))

    def test_revoke_classifies_queued_and_claimed_without_touching_game(self):
        self.register()
        self.call()
        claim = self.pull()[0]
        queued = self.call_payload(relay_id="queued")
        self.call(queued)
        game_before = deepcopy(self.h.game.state)
        result = self.revoke()["result"]
        self.assertEqual(result["route_revision"], 2)
        self.assertEqual(self.h.game.state, game_before)
        self.assertTrue(all(value["state"] == "revoked" for value in self.h.state["credentials"].values()))
        error = self.rejected("request_gone", lambda: self.call(credential="relay-agent-identity"))
        self.assertEqual(error["outcome"], "unknown")
        error = self.rejected("relay_not_dispatched", lambda: self.call(queued, credential="relay-agent-identity"))
        self.assertEqual(error["outcome"], "not_accepted")
        self.rejected("unauthenticated", lambda: self.dispatch(claim))
        self.rejected("unauthenticated", self.call)
        self.rejected("request_gone", lambda: self.h.credential_for(self.mid, "relay-agent-identity", now=1000))

    def test_revoke_faults_revision_cas_and_receipt_recovery(self):
        self.register()
        self.call()
        before = deepcopy(self.box)
        with self.assertRaises(H.InjectedFailure):
            self.revoke(fault="before_commit")
        self.assertEqual(before, self.box)
        with self.assertRaises(H.InjectedFailure):
            self.revoke(fault="after_commit")
        self.assertEqual(self.revoke()["result"]["route_revision"], 2)
        self.rejected("approval_stale", lambda: self.revoke(rid="new-revoke"))
        self.assertEqual(self.box["route_revision"], 2)

    def test_registration_expiry_closes_route_and_does_not_replay_secrets(self):
        self.registration["registration_expiry"] = 1001
        self.register()
        self.call()
        self.rejected("unauthenticated", lambda: self.call(now=1001))
        self.assertEqual(self.box["state"], "closed")
        self.assertEqual(self.box["route_revision"], 2)
        self.rejected("relay_not_dispatched", lambda: self.call(now=1001, credential="relay-agent-identity"))

    def test_claim_tampering_rejected_before_game_dispatch(self):
        self.register()
        self.call()
        claim = self.pull()[0]
        for field, value in (("claim_id", "missing"), ("game_identity", F.principal("other", "game")),
                             ("call", {**claim["call"], "relay_request_id": "different"})):
            with self.subTest(field=field):
                self.rejected("permission_denied", lambda: self.dispatch({**deepcopy(claim), field: value}))
        self.assertEqual(self.h.port.dispatch_calls, 0)

    def test_inner_proof_rechecked_when_game_dispatches(self):
        self.register()
        self.call()
        claim = self.pull()[0]
        self.h.port.proofs["inner-agent-fixture"]["state"] = "revoked"
        self.rejected("unauthenticated", lambda: self.dispatch(claim))
        self.assertFalse(self.h.port.journal)
        self.assertEqual(self.h.port.dispatch_calls, 0)

    def test_before_dispatch_can_retry_but_dispatch_mark_gap_never_reexecutes(self):
        self.register()
        self.call()
        claim = self.pull()[0]
        with self.assertRaises(H.InjectedFailure):
            self.dispatch(claim, fault="before_dispatch")
        self.assertFalse(self.h.port.journal)
        with self.assertRaises(H.InjectedFailure):
            self.dispatch(claim, fault="after_mark")
        result = self.dispatch(claim)
        self.assertEqual(result["error"]["outcome"], "unknown")
        self.assertEqual(self.h.port.dispatch_calls, 0)
        self.reply(claim, result)
        self.assertEqual(self.call()["result"]["reply"]["error"]["code"], "outcome_unknown")

    def test_after_game_crash_keeps_chat_once_and_original_business_id(self):
        self.admit()
        inner = F.wire_request("chat.send", self.chat(), "chat-request")
        payload = self.call_payload(inner, relay_id="chat", proof="inner-control")
        self.call(payload)
        claim = self.pull("chat-pull")[0]
        before = self.h.port.dispatch_calls
        with self.assertRaises(H.InjectedFailure):
            self.dispatch(claim, fault="after_game")
        self.assertEqual(self.dispatch(claim)["error"]["outcome"], "unknown")
        self.assertEqual(self.h.port.dispatch_calls, before + 1)
        self.assertEqual(len(self.h.game.session.state["receipts"]), 1)
        # 由客户端显式重用业务 ID，而非中继自动重新生成 ID 或重执行。
        repeated = self.roundtrip("chat.send", self.chat(), proof="inner-control", inner_id="chat-request")[0]
        self.assertTrue(repeated["result"]["duplicate"])
        self.assertEqual(len(self.h.game.session.state["receipts"]), 1)

    def test_game_reply_log_survives_lost_return_without_second_dispatch(self):
        self.register()
        self.call()
        claim = self.pull()[0]
        with self.assertRaises(H.InjectedFailure):
            self.dispatch(claim, fault="after_commit")
        result = self.dispatch(claim)
        self.assertIn("result", result)
        self.assertEqual(self.h.port.dispatch_calls, 1)

    def test_bad_game_reply_after_execution_stays_unknown_and_is_not_retried(self):
        self.register()
        self.call()
        claim = self.pull()[0]
        with patch.object(self.h.game, "submit", return_value=b'{}') as called:
            self.assertEqual(self.dispatch(claim)["error"]["outcome"], "unknown")
            self.assertEqual(self.dispatch(claim)["error"]["outcome"], "unknown")
            self.assertEqual(called.call_count, 1)

    def test_unexpected_game_exception_does_not_echo_secret_or_imply_rejection(self):
        self.register()
        self.call()
        claim = self.pull()[0]
        with patch.object(self.h.game, "submit", side_effect=RuntimeError("secret-should-not-escape")):
            result = self.dispatch(claim)
        self.assertEqual(result["error"]["outcome"], "unknown")
        self.assertNotIn("secret-should-not-escape", C.codec.canonical(result).decode())

    def test_full_relay_admission_chat_and_no_lease_renewal_from_polling(self):
        self.admit()
        result, payload, claim = self.roundtrip("chat.send", self.chat(), proof="inner-control")
        self.assertFalse(result["result"]["duplicate"])
        state = self.h.game.session.state
        lease = state["session"]["lease_deadline"]
        dispatches = self.h.port.dispatch_calls
        self.call(payload, now=2000)
        self.pull("idle", now=2000)
        self.assertEqual(state["session"]["lease_deadline"], lease)
        self.assertEqual(self.h.port.dispatch_calls, dispatches)
        self.assertTrue(self.h.game.session.state["session"]["ready"])

    def test_game_revalidates_grant_not_just_relay_lane(self):
        self.admit()
        self.h.game.session.state["grant"]["state"] = "revoked"
        result = self.roundtrip("chat.send", self.chat(), proof="inner-control")[0]
        self.assertEqual(result["error"]["code"], "grant_revoked")
        self.assertEqual(len(self.h.game.session.state["receipts"]), 0)

    def test_cached_reply_suppressed_after_authorization_change_without_reexecution(self):
        self.admit()
        _, payload, _ = self.roundtrip("session.snapshot", {"session_id": "s1"}, proof="inner-control")
        before = self.h.port.dispatch_calls
        self.h.game.session.state["grant"].update(state="revoked", revision=2)
        self.rejected("request_gone", lambda: self.call(payload))
        self.assertEqual(self.h.port.dispatch_calls, before)

    def test_restart_preserves_queued_claimed_replied_and_exact_pull_receipts(self):
        self.register()
        self.call()
        claim = self.pull()[0]
        result = self.dispatch(claim)
        self.reply(claim, result)
        claimed = self.call_payload(relay_id="claimed")
        self.call(claimed)
        other = self.pull("second")[0]
        queued = self.call_payload(relay_id="queued")
        self.call(queued)
        before, game = deepcopy(self.box), self.h.game
        old = self.h
        self.h = self.h.restart_from_mock_ledger(now=1000)
        self.assertEqual(self.box, before)
        self.assertIs(self.h.game, game)
        self.assertEqual(self.pull("second"), [other])
        self.assertEqual(self.pull("third")[0]["call"]["relay_request_id"], "queued")
        self.assertEqual(self.call()["result"]["reply"], result)
        self.assertEqual(self.h.port.dispatch_calls, 1)
        with self.assertRaises(C.ContractError) as caught:
            old.submit(C.codec.canonical(F.wire_request("describe", {"instance": self.f["scope"]["instance"]})), "agent-identity", now=1000)
        self.assertEqual(caught.exception.code, "temporarily_unavailable")

    def test_restart_preserves_dispatch_gap_and_revocation_tombstones(self):
        self.register()
        self.call()
        claim = self.pull()[0]
        with self.assertRaises(H.InjectedFailure):
            self.dispatch(claim, fault="after_mark")
        self.h = self.h.restart_from_mock_ledger(now=1000)
        self.assertEqual(self.dispatch(claim)["error"]["outcome"], "unknown")
        self.assertEqual(self.h.port.dispatch_calls, 0)
        self.revoke()
        self.h = self.h.restart_from_mock_ledger(now=1000)
        self.assertEqual(self.box["route_revision"], 2)
        self.rejected("unauthenticated", self.call)
        self.rejected("request_gone", lambda: self.call(credential="relay-agent-identity"))

    def test_untrusted_lost_ledger_closes_routes_and_never_recreates_requests(self):
        self.register()
        self.call()
        self.pull()
        game = self.h.game
        self.h = self.h.restart_from_mock_ledger(now=1000, intact=False)
        self.rejected("temporarily_unavailable", lambda: self.call(credential="relay-agent-identity"))
        self.assertEqual(self.box["state"], "closed")
        self.assertEqual(len(self.box["claims"]), 1)
        self.assertIs(game, self.h.game)
        self.assertEqual(self.h.port.dispatch_calls, 0)

    def test_two_threads_duplicate_calls_and_competing_pulls_have_one_claim(self):
        self.register()
        gate = Barrier(2)
        def call_worker(index):
            gate.wait()
            return self.call(rid="thread-" + str(index))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(call_worker, range(2)))
        self.assertEqual(results[0]["result"], results[1]["result"])
        self.assertEqual(len(self.box["requests"]), 1)
        gate = Barrier(2)
        def pull_worker(index):
            gate.wait()
            return self.pull("thread-pull-" + str(index))
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(pull_worker, range(2)))
        self.assertEqual(sum(map(len, claims)), 1)
        self.assertEqual(len(self.box["claims"]), 1)

    def test_revoke_during_game_dispatch_keeps_effect_and_unknown_not_rollback(self):
        self.admit()
        payload = self.call_payload(F.wire_request("chat.send", self.chat(), "racing-chat"), relay_id="race", proof="inner-control")
        self.call(payload)
        claim = self.pull("race-pull")[0]
        entered, proceed = Event(), Event()
        original = self.h.game.submit
        def paused(*args, **kwargs):
            entered.set()
            if not proceed.wait(5):
                raise RuntimeError("test_dispatch_gate_timeout")
            return original(*args, **kwargs)
        with patch.object(self.h.game, "submit", side_effect=paused), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.dispatch, claim)
            try:
                self.assertTrue(entered.wait(5))
                self.revoke()
            finally:
                proceed.set()
            reply = future.result(timeout=5)
        self.assertIn("result", reply)
        self.assertEqual(len(self.h.game.session.state["receipts"]), 1)
        self.rejected("unauthenticated", lambda: self.reply(claim, reply))
        error = self.rejected("request_gone", lambda: self.call(payload, credential="relay-agent-identity"))
        self.assertEqual(error["outcome"], "unknown")

    def test_bounded_call_pull_revoke_orders_keep_dispatch_knowledge(self):
        for order in permutations(("call", "pull", "revoke")):
            with self.subTest(order=order):
                self.setUp()
                self.register()
                for op in order:
                    try:
                        {"call": self.call, "pull": self.pull, "revoke": self.revoke}[op]()
                    except C.ContractError as error:
                        self.assertIn(error.code, {"unauthenticated", "permission_denied"})
                self.assertEqual(self.box["state"], "closed")
                for record in self.box["requests"].values():
                    self.assertEqual(record["state"], "closed")
                    expected = "claimed" if order.index("call") < order.index("pull") < order.index("revoke") else "never_sent"
                    self.assertEqual(record["known_dispatch"], expected)
                self.assertEqual(self.h.port.dispatch_calls, 0)


if __name__ == "__main__":
    unittest.main()
