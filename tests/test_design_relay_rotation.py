"""真实 Relay 状态机的动态轮换、旧回执窗口及未知派发保留。"""

from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest
from test_design_relay import F

spec = importlib.util.spec_from_file_location("test_rotating_relay", Path(__file__).resolve().parents[1] / "docs/protocol/relay_rotation.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
C = M.C


class RelayRotationTests(unittest.TestCase):
    def setUp(self):
        self.f = F.relay_fixture()
        self.f.update(relay_epoch_profile=0, relay_pairing_epochs={"pairing-fixture": 0})
        self.h = M.RotatingRelayHarness(self.f)
        self.proof = deepcopy(self.f["relay_pairings"]["pairing-fixture"])
        self.now = 1000

    def send(self, operation, payload, credential, *, rid="request", extensions=None, fault=None):
        request = F.wire_request(operation, payload, rid)
        request["extensions"] = deepcopy(self.h.epoch_extensions if extensions is None else extensions)
        return C.codec.decode(self.h.submit(C.codec.canonical(request), credential, now=self.now, fault=fault))

    def register(self, index=1):
        epoch = self.h.route_epoch
        ref = "pairing-fixture" if (epoch, index) == (0, 1) else "pair-" + str(epoch) + "-" + str(index)
        if ref not in self.h.pairings:
            proof = deepcopy(self.proof); proof.update(proof_ref=ref, consent_evidence_ref="consent-" + ref)
            self.h.enroll_epoch_pairing(proof, epoch)
        self.registration = {"instance": self.f["scope"]["instance"], "relay_identity": self.proof["relay_identity"],
            "relay_origin": self.f["relay_origin"], "agent_principals": [self.f["agent"]], "control_principals": [self.f["player"]],
            "registration_expiry": self.now + 20000, "pairing_proof_ref": ref, "limits": self.f["scope"]["limits"]}
        self.reg_id = "reg-" + str(epoch) + "-" + str(index)
        result = self.send("relay.register", self.registration, "relay-player-identity", rid=self.reg_id)["result"]
        self.mid = result["mailbox_id"]
        self.tokens = {role: self.h.credential_for(self.mid, "relay-" + role + "-identity", now=self.now)
                       for role in ("agent", "game", "player")}
        return result

    def queued(self, operation="describe", body=None, *, role="agent", proof="inner-agent-fixture"):
        inner = F.wire_request(operation, {"instance": self.f["scope"]["instance"]} if body is None else body, "inner")
        payload = {"mailbox_id": self.mid, "call": {"relay_request_id": "call", "operation_request": inner,
            "inner_auth_proof": proof, "deadline": self.now + 10000, "route_revision": 1}}
        self.send("relay.call", payload, self.tokens[role])
        return payload

    def claim(self):
        return self.send("relay.pull", {"mailbox_id": self.mid, "pull_nonce": "pull", "maximum_items": 1},
                         self.tokens["game"])["result"]["claims"][0]

    def close(self):
        return self.send("relay.revoke", {"mailbox_id": self.mid, "expected_route_revision": 1},
                         "relay-player-identity", rid="close-" + self.mid)

    def rotate(self):
        target = self.h.route_epoch + 1
        self.h.seal_epoch(target - 1, now=self.now)
        self.h.advance_game_epoch(target, now=self.now)
        self.h.advance_relay_epoch(target, now=self.now)

    def rejected(self, code, call):
        with self.assertRaises(C.ContractError) as raised:
            call()
        self.assertEqual(raised.exception.code, code)

    def test_rotation_keeps_old_queued_receipt_and_requires_new_consent(self):
        registered = self.register(); payload = self.queued()
        old_ext, old_registration, old_id = deepcopy(self.h.epoch_extensions), deepcopy(self.registration), self.reg_id
        self.close(); before = deepcopy(self.h.game.state); self.rotate()
        self.assertEqual(self.h.game.state, before)
        self.assertEqual(self.h.route_epoch, 1)
        self.assertEqual(self.send("relay.call", payload, "relay-agent-identity", extensions=old_ext)["error"]["outcome"], "not_accepted")
        self.assertEqual(self.send("relay.register", old_registration, "relay-player-identity", rid=old_id, extensions=old_ext)["result"], registered)
        self.rejected("permission_denied", lambda: self.send("relay.register", old_registration, "relay-player-identity", rid="new-old-proof"))
        self.assertEqual(self.register()["mailbox_id"], "mailbox-e1-1")
        self.assertEqual(self.h.port.route_epoch, 1)

    def test_completed_dispatch_is_not_reexecuted_after_rotation(self):
        self.register(); payload = self.queued(); claim = self.claim()
        record = next(iter(self.h.state["mailboxes"][self.mid]["requests"].values()))
        binding = {key: deepcopy(record[key]) for key in ("principal", "outer_role", "inner_role")}
        reply = C.codec.decode(self.h.dispatch_claim(C.codec.canonical(claim), self.tokens["game"], now=self.now))
        self.send("relay.reply", {"mailbox_id": self.mid, "claim_id": claim["claim_id"], "reply": reply}, self.tokens["game"])
        old_ext = deepcopy(self.h.epoch_extensions)
        self.close(); self.rotate()
        self.rejected("request_gone", lambda: self.h.port.dispatch(claim, binding, now=self.now))
        self.assertEqual(self.send("relay.call", payload, "relay-agent-identity", extensions=old_ext)["error"]["outcome"], "unknown")
        self.assertEqual(self.h.port.dispatch_calls, 1)

    def test_unresolved_dispatch_blocks_rotation_even_after_journal_gc(self):
        self.register(); self.queued(); claim = self.claim()
        with self.assertRaises(M.H.InjectedFailure):
            self.h.dispatch_claim(C.codec.canonical(claim), self.tokens["game"], now=self.now, fault="after_mark")
        self.close(); self.h.retire_closed_game_journal(self.mid, now=self.now)
        self.h.port.compact_retired_journal()
        self.assertEqual(self.h.port.journal, {})
        self.assertTrue(self.h.port.unresolved)
        self.h.seal_epoch(0, now=self.now)
        self.rejected("outcome_unknown", lambda: self.h.advance_game_epoch(1, now=self.now))
        self.h = self.h.restart_from_mock_ledger(now=self.now)
        self.rejected("outcome_unknown", lambda: self.h.advance_game_epoch(1, now=self.now))

    def test_three_commit_points_fault_and_restart_recovery(self):
        for stage in ("seal_epoch", "advance_game_epoch", "advance_relay_epoch"):
            for fault in ("before_commit", "after_commit"):
                with self.subTest(stage=stage, fault=fault):
                    self.setUp(); self.register(); self.close()
                    if stage != "seal_epoch": self.h.seal_epoch(0, now=self.now)
                    if stage == "advance_relay_epoch": self.h.advance_game_epoch(1, now=self.now)
                    with self.assertRaises(M.H.InjectedFailure):
                        getattr(self.h, stage)(0 if stage == "seal_epoch" else 1, now=self.now, fault=fault)
                    self.h = self.h.restart_from_mock_ledger(now=self.now)
                    getattr(self.h, stage)(0 if stage == "seal_epoch" else 1, now=self.now)
                    if self.h.route_epoch == 0:
                        self.h.advance_game_epoch(1, now=self.now); self.h.advance_relay_epoch(1, now=self.now)
                    self.assertEqual(self.register()["mailbox_id"], "mailbox-e1-1")

    def test_active_and_gap_admission_and_wrong_order_are_rejected(self):
        self.register()
        self.rejected("permission_denied", lambda: self.h.seal_epoch(0, now=self.now))
        self.close(); self.h.seal_epoch(0, now=self.now)
        self.rejected("generation_conflict", lambda: self.h.advance_relay_epoch(1, now=self.now))
        self.rejected("temporarily_unavailable", lambda: self.send("relay.register", self.registration, "relay-player-identity", rid="gap"))
        self.h.advance_game_epoch(1, now=self.now)
        self.rejected("temporarily_unavailable", lambda: self.send("relay.register", self.registration, "relay-player-identity", rid="gap"))

    def test_archive_expiry_and_gc_do_not_reopen_old_registration(self):
        self.register(); payload = self.queued()
        old_ext = deepcopy(self.h.epoch_extensions)
        self.close(); self.rotate()
        self.now = 61000
        self.rejected("request_gone", lambda: self.send("relay.call", payload, "relay-agent-identity", extensions=old_ext))
        with self.assertRaises(M.H.InjectedFailure):
            self.h.compact_archives(now=self.now, fault="before_commit")
        self.assertEqual(len(self.h.state["archives"]), 1)
        with self.assertRaises(M.H.InjectedFailure):
            self.h.compact_archives(now=self.now, fault="after_commit")
        self.assertEqual(self.h.compact_archives(now=self.now)["removed"], 0)
        self.assertEqual(self.h.state["registrations"], {})
        self.assertEqual(self.h.state["credentials"], {})
        self.rejected("permission_denied", lambda: self.send("relay.call", payload, "relay-agent-identity", extensions=old_ext))

    def test_archive_capacity_is_bounded_and_expiry_releases_rotation(self):
        for index in range(1, 9):
            self.register(index); self.close()
        self.rotate()
        self.register(); self.close()
        self.rejected("resource_limit", lambda: self.h.seal_epoch(1, now=self.now))
        self.assertEqual(self.h.port.route_epoch, 1)
        self.now = 61000
        self.assertEqual(self.h.compact_archives(now=self.now)["removed"], 8)
        self.h.seal_epoch(1, now=self.now); self.h.advance_game_epoch(2, now=self.now)
        self.h.advance_relay_epoch(2, now=self.now)
        self.assertEqual(self.register()["mailbox_id"], "mailbox-e2-1")
        self.assertEqual(len(self.h.state["archives"]), 1)

    def test_unstarted_settlement_survives_gc_and_lost_response(self):
        for fault in ("before_commit", "after_commit"):
            with self.subTest(fault=fault):
                self.setUp(); self.register(); self.queued(); claim = self.claim()
                with self.assertRaises(M.H.InjectedFailure):
                    self.h.dispatch_claim(C.codec.canonical(claim), self.tokens["game"], now=self.now, fault="after_mark")
                self.close(); self.h.retire_closed_game_journal(self.mid, now=self.now)
                self.h.port.compact_retired_journal()
                with self.assertRaises(M.H.InjectedFailure):
                    self.h.port.settle_unstarted(self.mid, claim["claim_id"], fault=fault)
                self.h = self.h.restart_from_mock_ledger(now=self.now)
                self.assertEqual(self.h.port.settle_unstarted(self.mid, claim["claim_id"]),
                                 {"settled": True, "outcome": "not_accepted"})
                self.assertEqual(self.h.port.dispatch_calls, 0)
                self.rotate()
                self.assertEqual(self.register()["mailbox_id"], "mailbox-e1-1")

    def test_settlement_requires_closed_mailbox_and_exact_unstarted_claim(self):
        self.register(); self.queued(); claim = self.claim()
        with self.assertRaises(M.H.InjectedFailure):
            self.h.dispatch_claim(C.codec.canonical(claim), self.tokens["game"], now=self.now, fault="after_mark")
        self.rejected("permission_denied", lambda: self.h.port.settle_unstarted(self.mid, claim["claim_id"]))
        self.close(); self.h.retire_closed_game_journal(self.mid, now=self.now)
        self.rejected("outcome_unknown", lambda: self.h.port.settle_unstarted(self.mid, "invented"))
        self.assertTrue(self.h.port.unresolved)

    def committed_offer_gap(self):
        self.register()
        self.h.game.launcher.running = {"binding": self.h.game.launcher.binding(), "verified": True}
        self.queued("offer.create", {"entry": "companion", "descriptor_id": "fixture-descriptor",
            "expected_descriptor_revision": 1, "requested": self.f["requested"]})
        claim = self.claim()
        record = next(iter(self.h.state["mailboxes"][self.mid]["requests"].values()))
        binding = {key: deepcopy(record[key]) for key in ("principal", "outer_role", "inner_role")}
        with self.assertRaises(M.H.InjectedFailure):
            self.h.dispatch_claim(C.codec.canonical(claim), self.tokens["game"], now=self.now, fault="after_game")
        self.close(); self.h.retire_closed_game_journal(self.mid, now=self.now)
        self.h.port.compact_retired_journal()
        return claim, binding

    def test_admission_commit_settlement_after_gc_fault_and_restart(self):
        for fault in ("before_commit", "after_commit"):
            with self.subTest(fault=fault):
                self.setUp(); claim, binding = self.committed_offer_gap()
                self.assertEqual(len(self.h.game.state["offers"]), 1)
                before = deepcopy(self.h.game.state)
                with self.assertRaises(M.H.InjectedFailure):
                    self.h.port.settle_admission_commit(claim, binding, now=self.now, fault=fault)
                self.h = self.h.restart_from_mock_ledger(now=self.now)
                self.assertEqual(self.h.port.settle_admission_commit(claim, binding, now=self.now),
                                 {"settled": True, "acceptance": "committed"})
                self.assertEqual(self.h.game.state, before)
                self.assertEqual(self.h.port.dispatch_calls, 1)
                self.rotate()
                self.assertEqual(self.register()["mailbox_id"], "mailbox-e1-1")

    def test_admission_settlement_rejects_changed_claim_and_missing_or_wrong_receipt(self):
        claim, binding = self.committed_offer_gap()
        changed = deepcopy(claim); changed["call"]["operation_request"]["request_id"] = "other"
        self.rejected("id_conflict", lambda: self.h.port.settle_admission_commit(changed, binding, now=self.now))
        key = next(iter(self.h.game.state["receipts"]))
        receipt = self.h.game.state["receipts"].pop(key)
        self.rejected("outcome_unknown", lambda: self.h.port.settle_admission_commit(claim, binding, now=self.now))
        self.h.game.state["receipts"][key] = {**receipt, "digest": "wrong"}
        self.rejected("id_conflict", lambda: self.h.port.settle_admission_commit(claim, binding, now=self.now))
        self.assertTrue(self.h.port.unresolved)

    def test_admission_settlement_requires_current_inner_authorization(self):
        claim, binding = self.committed_offer_gap()
        self.h.port.proofs["inner-agent-fixture"]["state"] = "revoked"
        self.rejected("unauthenticated", lambda: self.h.port.settle_admission_commit(claim, binding, now=self.now))
        self.assertTrue(self.h.port.unresolved)
        self.setUp(); claim, binding, reader = self.session_control_gap("session.close")
        self.h.game.identities["agent-identity"]["expires_at"] = self.now
        self.rejected("unauthenticated", lambda:
            self.h.port.settle_session_control(claim, binding, reader_proof=reader, now=self.now))
        self.assertTrue(self.h.port.unresolved)

    def admission_stage_gap(self, operation):
        self.register()
        self.h.game.launcher.running = {"binding": self.h.game.launcher.binding(), "verified": True}
        def game(op, payload, credential):
            return C.codec.decode(self.h.game.submit(C.codec.canonical(F.wire_request(op, payload, "setup-" + op)),
                                                    credential, now=self.now))["result"]
        offer = game("offer.create", {"entry": "companion", "descriptor_id": "fixture-descriptor",
            "expected_descriptor_revision": 1, "requested": self.f["requested"]}, "agent-identity")
        decision = {"offer_id": offer["offer_id"], "scope_digest": offer["scope_digest"], "allow": True,
            "remember": False, "launch_permission": False, "decision_ref": "decision"}
        self.h.game.decisions["decision"] = {"player": self.f["player"], "payload": deepcopy(decision)}
        payload, role, proof = decision, "player", "inner-player-fixture"
        if operation != "offer.decide":
            game("offer.decide", decision, "player-fixture")
            payload = {"offer_id": offer["offer_id"], "join_intent": {"scope_digest": offer["scope_digest"]}}
            role, proof = "agent", "inner-agent-fixture"
            if operation == "session.join":
                invitation = game("invitation.redeem", payload, "agent-identity")
                self.h.port.enroll("inner-invitation", invitation["invitation_credential"])
                payload = {key: invitation[key] for key in ("invitation_id", "join_intent")}
                proof = "inner-invitation"
        self.queued(operation, payload, role=role, proof=proof)
        claim = self.claim()
        record = next(iter(self.h.state["mailboxes"][self.mid]["requests"].values()))
        binding = {key: deepcopy(record[key]) for key in ("principal", "outer_role", "inner_role")}
        with self.assertRaises(M.H.InjectedFailure):
            self.h.dispatch_claim(C.codec.canonical(claim), self.tokens["game"], now=self.now, fault="after_game")
        self.close(); self.h.retire_closed_game_journal(self.mid, now=self.now)
        self.h.port.compact_retired_journal()
        return claim, binding

    def test_remaining_admission_commit_paths_preserve_state_and_secrets(self):
        for operation in ("offer.decide", "invitation.redeem", "session.join"):
            with self.subTest(operation=operation):
                self.setUp(); claim, binding = self.admission_stage_gap(operation)
                self.h = self.h.restart_from_mock_ledger(now=self.now)
                before = deepcopy(self.h.game.state)
                child = None if self.h.game.session is None else deepcopy(self.h.game.session.state)
                result = self.h.port.settle_admission_commit(claim, binding, now=self.now)
                self.assertEqual(result, {"settled": True, "acceptance": "committed"})
                self.assertEqual(self.h.game.state, before)
                if child is not None:
                    self.assertEqual(self.h.game.session.state, child)
                self.assertEqual(self.h.port.dispatch_calls, 1)
                self.rotate()
                self.assertEqual(self.register()["mailbox_id"], "mailbox-e1-1")

    def test_join_commit_settlement_does_not_publish_ready(self):
        claim, binding = self.admission_stage_gap("session.join")
        self.assertFalse(self.h.game.session.state["session"]["ready"])
        before = deepcopy(self.h.game.session.state)
        self.h.port.settle_admission_commit(claim, binding, now=self.now)
        self.assertEqual(self.h.game.session.state, before)
        self.assertFalse(self.h.game.session.state["session"]["ready"])
        self.rotate()
        self.assertFalse(self.h.game.session.state["session"]["ready"])
        self.h.game.finish_admission(now=self.now)
        self.assertTrue(self.h.game.session.state["session"]["ready"])

    def test_settlement_expiry_and_time_regression_preserve_unknown(self):
        claim, binding = self.admission_stage_gap("session.join")
        before = deepcopy(self.h.game.state)
        self.rejected("temporarily_unavailable", lambda:
            self.h.port.settle_admission_commit(claim, binding, now=self.now - 1))
        self.assertEqual(self.h.game.state, before)
        proof = self.h.port.proofs["inner-invitation"]
        self.rejected("unauthenticated", lambda:
            self.h.port.settle_admission_commit(claim, binding, now=proof["expires_at"]))
        self.assertEqual(self.h.game.state, before)
        self.assertTrue(self.h.port.unresolved)

    def action_acceptance_gap(self, *, cancel=False):
        join_claim, binding = self.admission_stage_gap("session.join")
        self.h.port.settle_admission_commit(join_claim, binding, now=self.now)
        self.rotate(); self.register()
        self.h.game.finish_admission(now=self.now)
        join = join_claim["call"]["operation_request"]
        credential = self.h.port.proofs["inner-invitation"]["credential"]
        joined = C.codec.decode(self.h.game.submit(C.codec.canonical(join), credential, now=self.now))["result"]
        self.h.port.enroll("inner-control", joined["control_credential"])
        session = self.h.game.session.state["session"]
        envelope = {"version": "fixture-only", "session_id": session["session_id"], "id": "action-envelope",
            "type": "action.request", "sender": self.f["agent"], "audience": [self.f["player"]],
            "expected_capabilities_revision": session["capabilities_revision"], "extensions": {},
            "payload": {"action": "find-key", "arguments": {"room": "hall"}, "deadline": 10000}}
        operation = "action.request"
        if cancel:
            self.h.game.submit(C.codec.canonical(F.wire_request(operation, envelope, "setup-action")),
                               joined["control_credential"], now=self.now)
            operation = "action.cancel"
            envelope.update(id="cancel-envelope", type=operation, payload={"request_id": "action-envelope"})
        self.queued(operation, envelope, proof="inner-control")
        claim = self.claim()
        record = next(iter(self.h.state["mailboxes"][self.mid]["requests"].values()))
        binding = {key: deepcopy(record[key]) for key in ("principal", "outer_role", "inner_role")}
        with self.assertRaises(M.H.InjectedFailure):
            self.h.dispatch_claim(C.codec.canonical(claim), self.tokens["game"], now=self.now, fault="after_game")
        self.close(); self.h.retire_closed_game_journal(self.mid, now=self.now)
        self.h.port.compact_retired_journal()
        return claim, binding

    def test_action_acceptance_uses_envelope_id_without_executing_effects(self):
        for fault in ("before_commit", "after_commit"):
            with self.subTest(fault=fault):
                self.setUp(); claim, binding = self.action_acceptance_gap()
                action = self.h.game.session.action_model
                self.assertEqual(action.model.action["state"], "pending")
                self.assertNotEqual(claim["call"]["operation_request"]["request_id"], action.model.action["id"])
                with self.assertRaises(M.H.InjectedFailure):
                    self.h.port.settle_action_acceptance(claim, binding, reader_proof="inner-agent-fixture", now=self.now, fault=fault)
                self.h = self.h.restart_from_mock_ledger(now=self.now)
                action = self.h.game.session.action_model
                before = deepcopy(action.model.action), deepcopy(action.model.world)
                self.assertEqual(self.h.port.settle_action_acceptance(claim, binding, reader_proof="inner-agent-fixture", now=self.now),
                                 {"settled": True, "acceptance": "committed"})
                self.assertEqual((action.model.action, action.model.world), before)
                self.rotate()
                self.assertEqual(action.model.action["state"], "pending")

    def test_action_acceptance_respects_result_revocation_and_receipt_digest(self):
        claim, binding = self.action_acceptance_gap()
        action = self.h.game.session.action_model
        action.read_revoked = True
        self.rejected("permission_denied", lambda: self.h.port.settle_action_acceptance(claim, binding, reader_proof="inner-agent-fixture", now=self.now))
        action.read_revoked = False
        action.receipts["action-envelope"]["record_digest"] = "wrong"
        self.rejected("id_conflict", lambda: self.h.port.settle_action_acceptance(claim, binding, reader_proof="inner-agent-fixture", now=self.now))
        self.assertTrue(self.h.port.unresolved)

    def test_action_cancel_acceptance_does_not_execute_or_disclose(self):
        claim, binding = self.action_acceptance_gap(cancel=True)
        action = self.h.game.session.action_model
        before = deepcopy(action.model.action), deepcopy(action.model.world)
        self.assertEqual(self.h.port.settle_action_acceptance(claim, binding,
            reader_proof="inner-agent-fixture", now=self.now), {"settled": True, "acceptance": "committed"})
        self.assertEqual((action.model.action, action.model.world), before)
        self.rotate()
        self.assertEqual(action.model.world, {})

    def test_action_settlement_requires_separate_same_subject_reader(self):
        claim, binding = self.action_acceptance_gap()
        for proof in ("inner-control", "inner-player-fixture"):
            with self.subTest(proof=proof):
                self.rejected("permission_denied", lambda:
                    self.h.port.settle_action_acceptance(claim, binding, reader_proof=proof, now=self.now))
        self.h.port.proofs["inner-agent-fixture"]["state"] = "revoked"
        self.rejected("unauthenticated", lambda:
            self.h.port.settle_action_acceptance(claim, binding, reader_proof="inner-agent-fixture", now=self.now))
        self.assertTrue(self.h.port.unresolved)

    def test_action_settlement_result_retention_boundary(self):
        for after in (False, True):
            with self.subTest(after=after):
                self.setUp(); claim, binding = self.action_acceptance_gap()
                action = self.h.game.session.action_model
                now = action.read_until + int(after)
                # 独立登记新的有效 reader；不能用早已到期的原身份测结果保留期。
                self.h.game.identities["retention-reader"] = {**deepcopy(self.h.game.identities["agent-identity"]),
                                                            "expires_at": now + 1}
                self.h.port.enroll("retention-reader-proof", "retention-reader", now=now, expires_at=now + 1)
                before = deepcopy(action.model.world)
                call = lambda: self.h.port.settle_action_acceptance(claim, binding,
                    reader_proof="retention-reader-proof", now=now)
                if after:
                    self.rejected("permission_denied", call)
                    self.assertTrue(self.h.port.unresolved)
                else:
                    self.assertEqual(call(), {"settled": True, "acceptance": "committed"})
                self.assertEqual(action.model.world, before)

    def test_action_settlement_does_not_restore_read_rights_on_member_rejoin(self):
        for rejoined in (False, True):
            with self.subTest(rejoined=rejoined):
                self.setUp(); claim, binding = self.action_acceptance_gap()
                child = self.h.game.session
                key = M.R.principal_key(self.f["agent"])
                generation = child.members.pop(key)
                if rejoined:
                    child.members[key] = generation + 1
                self.rejected("permission_denied", lambda: self.h.port.settle_action_acceptance(claim, binding,
                    reader_proof="inner-agent-fixture", now=self.now))
                self.assertTrue(self.h.port.unresolved)

    def test_action_settlement_does_not_flush_pending_sync(self):
        claim, binding = self.action_acceptance_gap()
        child = self.h.game.session
        child.pending_sync = True
        before = deepcopy(child.state), deepcopy(child.action_model.model.world)
        self.rejected("temporarily_unavailable", lambda: self.h.port.settle_action_acceptance(claim, binding,
            reader_proof="inner-agent-fixture", now=self.now))
        self.assertTrue(child.pending_sync)
        self.assertEqual((child.state, child.action_model.model.world), before)
        self.assertTrue(self.h.port.unresolved)

    def test_worker_management_operations_cannot_enter_relay_route(self):
        features = self.h.game.fixture["descriptor"]["supported_features"]
        for operation in ("action.claim", "action.commit_result"):
            for outer in ("relay_agent", "relay_controller"):
                for inner in ("executor", "agent", "companion_control", "player"):
                    with self.subTest(operation=operation, outer=outer, inner=inner):
                        self.rejected("permission_denied", lambda:
                            C.authorize_relay_inner(outer, inner, operation, features))
        self.assertEqual(self.h.port.dispatch_calls, 0)
        self.assertEqual(self.h.port.dispatch_witnesses, {})

    def session_control_gap(self, operation, target=None):
        join_claim, binding = self.admission_stage_gap("session.join")
        self.h.port.settle_admission_commit(join_claim, binding, now=self.now)
        self.rotate(); self.register()
        self.h.game.finish_admission(now=self.now)
        credential = self.h.port.proofs["inner-invitation"]["credential"]
        joined = C.codec.decode(self.h.game.submit(C.codec.canonical(join_claim["call"]["operation_request"]),
                                                  credential, now=self.now))["result"]
        self.h.port.enroll("inner-control", joined["control_credential"])
        child = self.h.game.session
        session = child.state["session"]
        payload, role, proof = {"session_id": session["session_id"]}, "agent", "inner-control"
        if operation == "session.close":
            payload["reason"] = "left"
        elif operation == "permission.revoke":
            payload = {"object_type": target, "object_id": "find-key" if target == "capability" else session["session_id"],
                "expected_revision": session["capabilities_revision"] if target == "capability" else
                    child.state["result_access_revision"] if target == "result_read" else child.state["grant"]["revision"]}
            role, proof = "player", "inner-player-fixture"
        self.queued(operation, payload, role=role, proof=proof)
        claim = self.claim()
        record = next(iter(self.h.state["mailboxes"][self.mid]["requests"].values()))
        binding = {key: deepcopy(record[key]) for key in ("principal", "outer_role", "inner_role")}
        with self.assertRaises(M.H.InjectedFailure):
            self.h.dispatch_claim(C.codec.canonical(claim), self.tokens["game"], now=self.now, fault="after_game")
        self.close(); self.h.retire_closed_game_journal(self.mid, now=self.now)
        self.h.port.compact_retired_journal()
        return claim, binding, "inner-player-fixture" if role == "player" else "inner-agent-fixture"

    def test_session_control_settlement_faults_do_not_repeat_writes(self):
        for operation in ("session.heartbeat", "session.close"):
            for fault in ("before_commit", "after_commit"):
                with self.subTest(operation=operation, fault=fault):
                    self.setUp(); claim, binding, reader = self.session_control_gap(operation)
                    before = deepcopy(self.h.game.session.state)
                    with self.assertRaises(M.H.InjectedFailure):
                        self.h.port.settle_session_control(claim, binding, reader_proof=reader, now=self.now, fault=fault)
                    self.h = self.h.restart_from_mock_ledger(now=self.now)
                    self.assertEqual(self.h.port.settle_session_control(claim, binding, reader_proof=reader, now=self.now),
                                     {"settled": True, "acceptance": "committed"})
                    self.assertEqual(self.h.game.session.state, before)
                    self.rotate()

    def test_revocation_settlement_does_not_advance_revision_again(self):
        for target in ("session", "result_read", "capability"):
            with self.subTest(target=target):
                self.setUp(); claim, binding, reader = self.session_control_gap("permission.revoke", target)
                before = deepcopy(self.h.game.session.state)
                self.assertEqual(self.h.port.settle_session_control(claim, binding, reader_proof=reader, now=self.now),
                                 {"settled": True, "acceptance": "committed"})
                self.assertEqual(self.h.game.session.state, before)
                self.rotate()

    def test_heartbeat_settlement_at_later_time_does_not_extend_lease(self):
        claim, binding, reader = self.session_control_gap("session.heartbeat")
        lease = self.h.game.session.state["session"]["lease_deadline"]
        self.h.port.settle_session_control(claim, binding, reader_proof=reader, now=self.now + 1)
        self.assertEqual(self.h.game.session.state["session"]["lease_deadline"], lease)

    def test_session_control_settlement_rejects_wrong_reader_and_receipt(self):
        claim, binding, reader = self.session_control_gap("session.close")
        for wrong in ("inner-control", "inner-player-fixture"):
            self.rejected("permission_denied", lambda:
                self.h.port.settle_session_control(claim, binding, reader_proof=wrong, now=self.now))
        receipts = self.h.game.session.state["session_controls"]
        key = next(iter(receipts)); receipt = receipts.pop(key)
        self.rejected("outcome_unknown", lambda:
            self.h.port.settle_session_control(claim, binding, reader_proof=reader, now=self.now))
        receipts[key] = {**receipt, "digest": "wrong"}
        self.rejected("id_conflict", lambda:
            self.h.port.settle_session_control(claim, binding, reader_proof=reader, now=self.now))
        self.assertTrue(self.h.port.unresolved)

    def test_expired_underlying_reader_cannot_settle_action(self):
        claim, binding = self.action_acceptance_gap()
        self.h.game.identities["agent-identity"]["expires_at"] = self.now
        self.assertGreater(self.h.port.proofs["inner-agent-fixture"]["expires_at"], self.now)
        self.rejected("unauthenticated", lambda: self.h.port.settle_action_acceptance(claim, binding,
            reader_proof="inner-agent-fixture", now=self.now))
        self.assertTrue(self.h.port.unresolved)

    def test_inner_proof_cannot_extend_underlying_identity_lifetime(self):
        identity = self.h.game.identities["agent-identity"]
        for expiry in (self.now, self.now - 1, True, "900000", None):
            with self.subTest(expiry=expiry):
                identity["expires_at"] = expiry
                self.rejected("unauthenticated", lambda: self.h.port.verify("inner-agent-fixture", now=self.now))
        identity["expires_at"] = self.now + 1
        self.assertEqual(self.h.port.verify("inner-agent-fixture", now=self.now)["principal"], self.f["agent"])
        del identity["expires_at"]
        self.assertEqual(self.h.port.verify("inner-agent-fixture", now=self.now)["principal"], self.f["agent"])

    def test_expired_underlying_identity_blocks_admission_and_control_settlement(self):
        claim, binding = self.committed_offer_gap()
        self.h.game.identities["agent-identity"]["expires_at"] = self.now
        self.rejected("unauthenticated", lambda: self.h.port.settle_admission_commit(claim, binding, now=self.now))
        self.assertTrue(self.h.port.unresolved)

    def test_expired_underlying_identity_is_rechecked_before_dispatch(self):
        self.register(); self.queued(); claim = self.claim()
        self.h.game.identities["agent-identity"]["expires_at"] = self.now
        self.rejected("unauthenticated", lambda:
            self.h.dispatch_claim(C.codec.canonical(claim), self.tokens["game"], now=self.now))
        self.assertEqual(self.h.port.dispatch_calls, 0)
        self.assertEqual(self.h.port.journal, {})
        self.assertEqual(self.h.port.unresolved, set())

    def test_entered_game_cannot_be_settled_as_unstarted(self):
        self.register(); self.queued(); claim = self.claim()
        with self.assertRaises(M.H.InjectedFailure):
            self.h.dispatch_claim(C.codec.canonical(claim), self.tokens["game"], now=self.now, fault="after_game")
        self.close(); self.h.retire_closed_game_journal(self.mid, now=self.now)
        self.h.port.compact_retired_journal()
        self.h = self.h.restart_from_mock_ledger(now=self.now)
        self.rejected("outcome_unknown", lambda: self.h.port.settle_unstarted(self.mid, claim["claim_id"]))
        self.h.seal_epoch(0, now=self.now)
        self.rejected("outcome_unknown", lambda: self.h.advance_game_epoch(1, now=self.now))
        self.assertEqual(self.h.port.dispatch_calls, 1)


if __name__ == "__main__":
    unittest.main()
