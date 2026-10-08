"""隐私字节链的权限、cutoff、可信副本回执及故障恢复；不处理真实数据。"""

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


P = load("test_privacy", "privacy_harness.py")
F = load("privacy_fixtures", "fixtures.py")
I = load("privacy_importer", "source_import.py")
C = P.C


class PrivacyTests(unittest.TestCase):
    def setUp(self):
        self.f = F.core_fixture(["core.session", "core.events", "privacy-request"])
        self.other = F.principal("bob", "player")
        self.records = {}
        for ref, subject in (("source-1", self.f["player"]), ("source-2", self.other)):
            source = {"source_id": ref, "source_kind": "player_report", "source_principals": [subject],
                      "original_disclosure_scope": [self.f[name] for name in ("player", "agent", "game")]}
            self.records[ref] = {"source": source, "controller": self.f["agent"], "instance": self.f["scope"]["instance"],
                "session_id": "s1", "evidence_ref": "proof-" + ref, "revision": 1, "state": "active",
                "publishers": [self.f["agent"]], "allowed_readers": source["original_disclosure_scope"], "expires_at": 80000}
        self.copies = {key: {"source_id": ref, "controller": self.f["agent"], "subjects": [subject], "state": "present"}
            for key, ref, subject in (("owned-1", "source-1", self.f["player"]), ("backup-1", "source-1", self.f["player"]),
                                      ("bob-copy", "source-2", self.other))}
        self.rebuild()

    def rebuild(self):
        evidence = {r["evidence_ref"]: {**deepcopy(r), "revoked": False} for r in self.records.values()}
        self.importer = I.SourceImporter(evidence)
        for record in self.records.values():
            self.importer.import_record(record, verified_controller=record["controller"], session=self.f["session"], now=1000)
        self.h = P.PrivacyHarness(self.f, self.importer.snapshot(self.f["session"], now=1000), memory_copies=self.copies)

    def wire(self, op, payload, *, credential="subject-fixture", rid="r1", now=1000, fault=None):
        return C.codec.decode(self.h.submit(C.codec.canonical(F.wire_request(op, payload, rid)), credential, now=now, fault=fault))

    def send(self, *args, **kwargs):
        reply = self.wire(*args, **kwargs)
        self.assertIn("result", reply)
        return reply["result"]

    def request(self, *, refs=None, action="delete_owned_copies", **kwargs):
        return self.send("privacy.request", {"source_refs": refs or ["source-1"], "desired_action": action}, **kwargs)

    def receipt(self, pid="privacy-1", **kwargs):
        return self.send("privacy.receipt", {"privacy_request_id": pid}, **kwargs)

    def fail(self, code, function):
        with self.assertRaises(C.ContractError) as caught:
            function()
        self.assertEqual(caught.exception.code, code)

    def provider(self, pid="privacy-1"):
        return self.h.state["privacy_requests"][pid]["binding"]["provider_operation_ref"]

    def join(self):
        self.h.launcher.running = {"binding": self.h.launcher.binding(), "verified": True}
        offer = self.send("offer.create", {"entry": "game", "descriptor_id": "fixture-descriptor", "expected_descriptor_revision": 1,
            "requested": self.f["requested"]}, credential="player-fixture", rid="offer")
        payload = {"offer_id": offer["offer_id"], "scope_digest": offer["scope_digest"], "allow": True,
                   "remember": False, "launch_permission": False, "decision_ref": "consent"}
        self.h.decisions["consent"] = {"player": self.f["player"], "payload": deepcopy(payload)}
        self.send("offer.decide", payload, credential="player-fixture", rid="decide")
        invitation = self.send("invitation.redeem", {"offer_id": offer["offer_id"], "join_intent": {"scope_digest": offer["scope_digest"]}},
                               credential="agent-identity", rid="invite")
        payload = {key: invitation[key] for key in ("invitation_id", "join_intent")}
        self.send("session.join", payload, credential=invitation["invitation_credential"], rid="join")
        self.h.finish_admission(now=1000)
        return self.send("session.join", payload, credential=invitation["invitation_credential"], rid="join")

    def chat(self, control, mid="m1"):
        return self.send("chat.send", {"version": "fixture-only", "session_id": "s1", "id": mid, "type": "chat.message",
            "sender": self.f["agent"], "audience": [self.f["player"], self.f["agent"]], "extensions": {},
            "payload": {"channel": "private", "text": "仅存在于内存的测试内容", "source_refs": ["source-1"],
                        "provenance": [deepcopy(self.records["source-1"]["source"])]}}, credential=control, rid=mid,
                        now=self.h.state["last_now"])

    def test_delete_has_real_fake_effects_and_only_controlled_source_receipt(self):
        result = self.request()
        self.assertEqual(result, {"privacy_request_id": "privacy-1", "status": "done", "controlled_scope": ["source-1"], "exceptions": []})
        self.assertEqual(set(self.h.memory.effects), {"owned-1", "backup-1"})
        self.assertEqual(self.h.memory.copies["bob-copy"]["state"], "present")
        self.assertEqual(self.h.state["privacy_sources"]["source-1"]["state"], "revoked")
        self.assertIsNone(self.h.session)

    def test_stop_disclosure_keeps_copies_and_future_delete_is_separate(self):
        self.assertEqual(self.request(action="stop_disclosure")["status"], "done")
        cutoff = deepcopy(self.h.state["privacy_cutoffs"])
        self.assertEqual(self.h.memory.effects, {})
        self.assertEqual(self.request(rid="delete-next")["status"], "done")
        self.assertEqual(self.h.state["privacy_cutoffs"], cutoff)
        self.assertEqual(len(self.h.memory.effects), 2)

    def test_wrong_roles_lanes_endpoint_and_expired_identity_do_not_apply(self):
        for credential in ("player-fixture", "game-fixture", "agent-identity", "unknown"):
            self.fail("permission_denied", lambda: self.request(credential=credential))
        original = deepcopy(self.h.privacy_identities["subject-fixture"])
        for key, value, error in (("role", "player", "permission_denied"), ("lane", "data", "permission_denied"),
                                  ("controller", self.f["game"], "permission_denied"), ("fresh", False, "unauthenticated"),
                                  ("expires_at", 1000, "unauthenticated"), ("expires_at", True, "unauthenticated")):
            self.h.privacy_identities["subject-fixture"] = {**deepcopy(original), key: value}
            self.fail(error, self.request)
        self.assertEqual(self.h.state["privacy_requests"], {})
        self.assertEqual(self.h.memory.apply_calls, 0)

    def test_feature_must_be_negotiated_on_independent_privacy_route(self):
        self.f["requested"]["supported_features"].remove("privacy-request")
        self.rebuild()
        self.fail("feature_unsupported", self.request)
        self.assertEqual(self.h.memory.apply_calls, 0)
        self.setUp()
        self.f["scope"]["features"].remove("privacy-request")
        self.rebuild()
        self.fail("feature_unsupported", self.request)

    def test_unknown_other_subject_or_mixed_sources_denied_atomically(self):
        for refs in (["missing"], ["source-2"], ["source-1", "source-2"], ["source-1", "missing"]):
            self.fail("permission_denied", lambda: self.request(refs=refs))
            self.assertEqual(self.h.state["privacy_cutoffs"], {})
        self.assertEqual(self.h.memory.effects, {})

    def test_source_controller_context_and_declaration_cannot_be_substituted(self):
        for field, value in (("controller", self.f["game"]), ("session_id", "other-session"),
                             ("instance", {**self.f["scope"]["instance"], "epoch": "other"}),
                             ("source", {**self.records["source-1"]["source"], "source_kind": "external_reference"})):
            self.setUp()
            self.h.state["privacy_sources"]["source-1"][field] = value
            self.fail("permission_denied", self.request)
            self.assertEqual(self.h.memory.apply_calls, 0)

    def test_source_disclosure_expiry_does_not_remove_privacy_rights(self):
        self.h.state["privacy_sources"]["source-1"].update(state="revoked", expires_at=999)
        self.assertEqual(self.request()["status"], "done")

    def test_requester_cannot_submit_source_claim_or_completion(self):
        payload = {"source_refs": ["source-1"], "desired_action": "delete_owned_copies"}
        for extra in ({"controller": self.f["agent"]}, {"subject": self.other}, {"status": "done"}, {"cutoff": 1}):
            self.fail("invalid_message", lambda: self.send("privacy.request", {**payload, **extra}))
        self.fail("invalid_message", lambda: self.send("privacy.receipt", {"privacy_request_id": "privacy-1", "status": "done"}))
        self.fail("invalid_message", lambda: self.request(refs=["source-1", "source-1"]))
        self.assertEqual(self.h.memory.apply_calls, 0)

    def test_dedup_and_digest_conflicts_include_optional_extensions(self):
        first = self.request()
        self.assertEqual(self.request(), first)
        self.fail("id_conflict", lambda: self.request(action="stop_disclosure"))
        request = F.wire_request("privacy.request", {"source_refs": ["source-1"], "desired_action": "delete_owned_copies"})
        request["extensions"] = {"example.optional": {"version": "1", "required": False, "value": True}}
        self.fail("id_conflict", lambda: self.h.submit(C.codec.canonical(request), "subject-fixture", now=1000))
        self.assertEqual(self.h.memory.apply_calls, 1)

    def test_required_extension_is_rejected_before_cutoff(self):
        request = F.wire_request("privacy.request", {"source_refs": ["source-1"], "desired_action": "delete_owned_copies"})
        request["extensions"] = {"example.required": {"version": "1", "required": True, "value": 1}}
        self.fail("feature_unsupported", lambda: self.h.submit(C.codec.canonical(request), "subject-fixture", now=1000))
        self.assertEqual(self.h.state["privacy_cutoffs"], {})

    def test_partial_preserves_shared_remote_and_retained_copies_with_deadline(self):
        self.copies["shared"] = {**self.copies["owned-1"], "subjects": [self.f["player"], self.other]}
        self.copies["outside"] = {**self.copies["owned-1"], "controller": self.f["game"]}
        self.copies["held"] = {**self.copies["owned-1"], "retention": {"reason": "legal_hold", "retain_until": 5000}}
        self.rebuild()
        result = self.request()
        self.assertEqual(result["status"], "partial")
        self.assertEqual({e["reason"] for e in result["exceptions"]}, {"shared_copy", "outside_control", "legal_hold"})
        self.assertIn({"source_id": "source-1", "reason": "legal_hold", "retain_until": 5000}, result["exceptions"])
        for ref in ("shared", "outside", "held"):
            self.assertEqual(self.h.memory.copies[ref]["state"], "present")

    def test_storage_denied_keeps_cutoff_and_is_not_full_rollback(self):
        self.h.memory.outcomes = ["denied"]
        result = self.request()
        self.assertEqual(result["status"], "denied")
        self.assertEqual(result["exceptions"], [{"source_id": "source-1", "reason": "storage_denied"}])
        self.assertEqual(self.h.memory.effects, {})
        self.assertEqual(self.h.state["privacy_sources"]["source-1"]["state"], "revoked")

    def test_known_empty_inventory_is_done_not_unknown(self):
        self.copies = {"bob-copy": self.copies["bob-copy"]}
        self.rebuild()
        self.assertEqual(self.request()["status"], "done")
        self.assertEqual(self.h.memory.effects, {})

    def test_retention_expiry_needs_new_request_not_mutating_old_receipt(self):
        for copy in self.copies.values():
            copy["retention"] = {"reason": "security_hold", "retain_until": 5000}
        self.rebuild()
        first = self.request()
        self.assertEqual(first["status"], "denied")
        self.assertEqual(self.receipt(now=5000), first)
        self.assertEqual(self.request(rid="after-hold", now=5000)["status"], "done")
        self.assertEqual(self.receipt(now=5000), first)

    def test_receipt_requires_original_subject_not_known_id_or_game_credential(self):
        first = self.request()
        self.h.privacy_identities["bob"] = {**deepcopy(self.h.privacy_identities["subject-fixture"]), "principal": self.other}
        before = self.h.memory.query_calls
        for pid, credential in (("privacy-1", "bob"), ("missing", "subject-fixture"), ("privacy-1", "player-fixture")):
            self.fail("permission_denied", lambda: self.receipt(pid, credential=credential))
        self.assertEqual(self.h.memory.query_calls, before)
        self.assertEqual(self.receipt(), first)
        # 相同 request_id 在两个已验证主体下不串结果，也不删除对方的来源。
        self.assertEqual(self.request(refs=["source-2"], credential="bob")["privacy_request_id"], "privacy-2")

    def test_before_accept_commit_fault_rolls_back_cutoff_and_inventory_untouched(self):
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.request(fault="before_commit")
        self.assertEqual(self.h.state["privacy_cutoffs"], {})
        self.assertEqual(self.h.state["privacy_requests"], {})
        self.assertEqual(self.h.memory.apply_calls, 0)
        self.assertEqual(self.request()["status"], "done")

    def test_accepted_undispatched_query_never_starts_but_original_request_can_continue(self):
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.request(fault="after_accept")
        self.assertEqual(self.receipt()["status"], "pending")
        self.assertEqual(self.h.memory.apply_calls, 0)
        self.assertEqual(self.request()["status"], "done")
        self.assertEqual(self.h.memory.apply_calls, 1)

    def test_dispatch_gap_stays_pending_and_new_id_cannot_bypass_it(self):
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.request(fault="after_dispatch")
        for _ in range(2):
            self.assertEqual(self.request()["status"], "pending")
            self.assertEqual(self.receipt()["status"], "pending")
        self.fail("temporarily_unavailable", lambda: self.request(rid="bypass"))
        self.assertEqual(self.h.memory.apply_calls, 0)
        self.assertEqual(len(self.h.state["privacy_cutoffs"]), 1)

    def test_effect_and_result_commit_faults_preserve_effects_and_same_operation(self):
        for fault, status in (("after_effect", "pending"), ("before_result_commit", "pending"), ("after_commit", "done")):
            self.setUp()
            with self.assertRaises(P.U.S.H.InjectedFailure):
                self.request(fault=fault)
            self.assertEqual(len(self.h.memory.effects), 2)
            self.assertEqual(self.h.state["privacy_requests"]["privacy-1"]["receipt"]["status"], status)
            self.assertEqual(self.receipt()["status"], "done")
            self.assertEqual(self.request()["status"], "done")
            self.assertEqual(self.h.memory.apply_calls, 1)

    def test_pending_store_job_completes_only_through_original_provider_receipt(self):
        self.h.memory.outcomes = ["pending"]
        self.assertEqual(self.request()["status"], "pending")
        self.assertEqual(self.receipt()["status"], "pending")
        self.assertEqual(self.h.memory.effects, {})
        self.h.memory.complete(self.provider(), now=1001)
        self.assertEqual(self.receipt(now=1001)["status"], "done")
        self.assertEqual(self.h.memory.apply_calls, 1)

    def test_unknown_or_hidden_receipt_never_fabricates_done_or_redelivers(self):
        for mode, count in (("unknown", 0), ("lost_receipt", 2)):
            self.setUp()
            self.h.memory.outcomes = [mode]
            self.assertEqual(self.request()["status"], "pending")
            self.assertEqual(self.request()["status"], "pending")
            self.assertEqual(len(self.h.memory.effects), count)
            self.assertEqual(self.h.memory.apply_calls, 1)
            self.h.memory.complete(self.provider(), now=1001)
            self.h.memory.operations[self.provider()]["hidden"] = False
            self.assertEqual(self.receipt(now=1001)["status"], "done")

    def test_port_exception_after_accept_is_pending_not_not_accepted(self):
        with patch.object(self.h.memory, "apply", side_effect=RuntimeError("storage_offline")):
            self.assertEqual(self.request()["status"], "pending")
        self.assertEqual(self.request()["status"], "pending")
        self.assertEqual(self.h.memory.apply_calls, 0)

    def test_reply_encoding_failure_before_and_after_accept_has_correct_knowledge(self):
        with patch.object(self.h, "_reply", side_effect=C.ContractError("invalid_message")):
            self.fail("invalid_message", self.request)
        self.assertEqual(self.h.state["privacy_cutoffs"], {})
        self.assertEqual(self.h.memory.apply_calls, 0)
        original = self.h._reply
        def encode(request, receipt):
            if receipt["status"] != "pending":
                raise C.ContractError("invalid_message")
            return original(request, receipt)
        with patch.object(self.h, "_reply", side_effect=encode):
            reply = self.wire("privacy.request", {"source_refs": ["source-1"], "desired_action": "delete_owned_copies"})
            self.assertEqual(reply["error"]["outcome"], "unknown")
        self.assertEqual(len(self.h.memory.effects), 2)
        self.assertEqual(self.receipt()["status"], "done")

    def test_untrusted_malformed_wrong_binding_and_boolean_receipts_stay_pending(self):
        self.h.memory.outcomes = ["pending"]
        self.request()
        self.h.memory.complete(self.provider(), now=1001)
        good = self.h.memory.query(self.provider())
        mutations = [None, {}, {**good, "evidence_ref": "forged"}]
        for field, value in (("privacy_request_id", "someone-elses"), ("controlled_scope", ["source-2"]),
                             ("status", "done"), ("exceptions", [{"source_id": "source-2", "reason": "leak"}])):
            bad = deepcopy(good)
            bad["receipt"][field] = value
            if bad != good:
                mutations.append(bad)
        bad = deepcopy(good)
        bad["binding"]["inventory"]["source-1"]["authorization"]["revision"] = True
        mutations.append(bad)
        for bad in mutations:
            with patch.object(self.h.memory, "query", return_value=bad):
                self.assertEqual(self.receipt(now=1001)["status"], "pending")
        with patch.object(self.h.memory, "query", side_effect=RuntimeError("query_offline")):
            self.assertEqual(self.receipt(now=1001)["status"], "pending")
        self.assertEqual(self.receipt(now=1001)["status"], "done")

    def test_inventory_rebinding_while_pending_cannot_delete_new_copy(self):
        self.h.memory.outcomes = ["pending"]
        self.request()
        self.h.memory.copies["new-copy"] = deepcopy(self.copies["owned-1"])
        self.h.memory.complete(self.provider(), now=1001)
        result = self.receipt(now=1001)
        self.assertEqual(result["status"], "denied")
        self.assertEqual(result["exceptions"], [{"source_id": "source-1", "reason": "inventory_changed"}])
        self.assertEqual(self.h.memory.effects, {})

    def test_cutoff_blocks_new_and_queued_chat_without_extending_game_lease(self):
        delivery = self.join()
        control = delivery["control_credential"]
        self.chat(control)
        lease = self.h.session.state["session"]["lease_deadline"]
        sequence = self.h.session.state["session"]["sequence"]
        self.assertEqual(len(self.h.session.delivery(self.f["player"], now=1000)), 1)
        self.h.memory.outcomes = ["pending"]
        self.request(now=1001)
        self.assertEqual(self.h.session.delivery(self.f["player"], now=1001), [])
        self.fail("permission_denied", lambda: self.chat(control, "m2"))
        self.assertEqual(self.h.session.state["session"]["lease_deadline"], lease)
        self.assertEqual(self.h.session.state["session"]["sequence"], sequence)

    def test_prejoin_cutoff_cannot_be_reenabled_by_session_join(self):
        self.request(action="stop_disclosure")
        delivery = self.join()
        self.fail("permission_denied", lambda: self.chat(delivery["control_credential"]))

    def test_known_game_outbox_copy_remains_an_exception_after_compaction(self):
        delivery = self.join()
        self.chat(delivery["control_credential"])
        self.h.session.compact_through(self.h.session.state["session"]["sequence"])
        result = self.request()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["exceptions"], [{"source_id": "source-1", "reason": "outside_control"}])
        self.assertEqual(len(self.h.memory.effects), 2)

    def test_replayed_poll_is_filtered_again_after_privacy_cutoff(self):
        delivery = self.join()
        control = delivery["control_credential"]
        self.chat(control)
        payload = {"session_id": "s1", "cursor": {"session_id": "s1", "instance_epoch": "epoch-1", "sequence": 0}, "page_size": 64}
        first = self.send("session.events", payload, credential=control, rid="poll")
        self.assertTrue(any(e["envelope"]["type"] == "chat.message" for e in first["events"]))
        self.request(action="stop_disclosure")
        repeated = self.send("session.events", payload, credential=control, rid="poll")
        self.assertFalse(any(e["envelope"]["type"] == "chat.message" for e in repeated["events"]))
        self.assertEqual(first["next_cursor"], repeated["next_cursor"])

    def test_cutoff_filters_published_context_from_recovery_snapshot(self):
        self.records["source-1"]["source"]["source_kind"] = "shared_experience"
        self.records["source-1"]["publishers"] = [self.f["game"]]
        self.rebuild()
        control = self.join()["control_credential"]
        payload = {"version": "fixture-only", "session_id": "s1", "id": "context", "type": "game.context",
            "sender": self.f["game"], "audience": [self.f["player"], self.f["agent"]], "extensions": {},
            "payload": {"category": "room", "content": "测试大厅", "provenance": [self.records["source-1"]["source"]]}}
        self.send("context.publish", payload, credential="game-fixture", rid="context")
        before = self.send("session.snapshot", {"session_id": "s1"}, credential=control, rid="before")
        self.assertEqual(len(before["contexts"]), 1)
        self.request(action="stop_disclosure")
        after = self.send("session.snapshot", {"session_id": "s1"}, credential=control, rid="after")
        self.assertEqual(after["contexts"], [])
        self.assertEqual(before["cursor"], after["cursor"])

    def test_limits_and_clock_checks_leave_privacy_unaccepted(self):
        self.h.privacy_route["message_bytes"] = 10
        self.fail("resource_limit", self.request)
        self.assertEqual(self.h.state["privacy_cutoffs"], {})
        self.setUp()
        self.request()
        record = deepcopy(self.h.state["privacy_requests"]["privacy-1"])
        for i in range(2, 129):
            self.h.state["privacy_requests"]["privacy-" + str(i)] = deepcopy(record)
        self.fail("resource_limit", lambda: self.request(rid="overflow"))
        self.fail("temporarily_unavailable", lambda: self.receipt(now=999))
        self.assertEqual(self.h.memory.apply_calls, 1)

    def test_cutoff_rollback_preserves_prior_lost_chat_reply_fact(self):
        delivery = self.join()
        control = delivery["control_credential"]
        # 正常聊天的 after_commit 丢回复仍与已知外部副本事实同事务。
        request = F.wire_request("chat.send", {"version": "fixture-only", "session_id": "s1", "id": "lost-chat", "type": "chat.message",
            "sender": self.f["agent"], "audience": [self.f["player"]], "extensions": {},
            "payload": {"channel": "private", "text": "已提交但回复丢失", "source_refs": ["source-1"],
                        "provenance": [self.records["source-1"]["source"]]}})
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.h.submit(C.codec.canonical(request), control, now=1000, fault="after_commit")
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.request(fault="before_commit")
        self.assertEqual(self.h.state["privacy_cutoffs"], {})
        self.assertEqual(self.h.session.state["records"]["source-1"]["state"], "active")
        self.assertIn("source-1", self.h.state["privacy_disclosed"])

    def test_game_close_and_revoked_grant_do_not_revoke_independent_subject_rights(self):
        self.join()
        self.send("session.close", {"session_id": "s1", "reason": "left"}, credential="player-fixture", rid="close")
        self.h.session.state["grant"]["state"] = "revoked"
        self.assertEqual(self.request()["status"], "done")
        self.assertEqual(self.receipt()["status"], "done")
        self.assertEqual(self.h.session.state["session"]["state"], "closed")

    def test_import_refresh_higher_revision_cannot_resurrect_source_or_rebind_handle(self):
        self.request(action="stop_disclosure")
        record = deepcopy(self.records["source-1"])
        record["revision"] = 5
        self.importer.import_record(record, verified_controller=self.f["agent"], session=self.f["session"], now=1000)
        self.h.refresh_disclosures(self.importer, now=1000)
        self.assertEqual(self.h.state["privacy_sources"]["source-1"]["state"], "revoked")
        changed = deepcopy(self.importer.snapshot(self.f["session"], now=1000))
        changed["source-1"]["source"]["source_kind"] = "external_reference"
        with patch.object(self.importer, "snapshot", return_value=changed):
            self.fail("permission_denied", lambda: self.h.refresh_disclosures(self.importer, now=1000))

    def test_two_simultaneous_retries_share_one_cutoff_and_effect(self):
        barrier = Barrier(2)
        def run(_):
            barrier.wait()
            return self.request()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = list(pool.map(run, range(2)))
        self.assertEqual(first, second)
        self.assertEqual(self.h.memory.apply_calls, 1)
        self.assertEqual(len(self.h.state["privacy_cutoffs"]), 1)

    def test_mock_restart_keeps_cutoff_and_independent_storage_effects(self):
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.request(fault="after_effect")
        old, memory = self.h, self.h.memory
        self.h = old.restart_from_mock_ledger(now=1001)
        self.assertIs(self.h.memory, memory)
        self.assertEqual(self.receipt(now=1001)["status"], "done")
        self.assertEqual(self.request(now=1001)["status"], "done")
        self.fail("resume_denied", lambda: old.submit(C.codec.canonical(F.wire_request("privacy.receipt", {"privacy_request_id": "privacy-1"})), "subject-fixture", now=1001))
        self.assertEqual(self.h.memory.apply_calls, 1)

    def test_corrupt_ledger_does_not_infer_success_from_missing_authority(self):
        self.request()
        self.h = self.h.restart_from_mock_ledger(now=1001, intact=False)
        self.fail("temporarily_unavailable", lambda: self.receipt(now=1001))
        self.fail("temporarily_unavailable", lambda: self.request(rid="new", now=1001))

    def test_postjoin_restart_keeps_outbox_cutoff_and_result_query_after_lease_expiry(self):
        control = self.join()["control_credential"]
        self.chat(control)
        with self.assertRaises(P.U.S.H.InjectedFailure):
            self.request(fault="after_effect")
        self.h = self.h.restart_from_mock_ledger(now=1001)
        result = self.receipt(now=200000)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(self.h.session.state["session"]["state"], "closed")
        self.assertEqual(self.h.session.state["records"]["source-1"]["state"], "revoked")
        self.assertEqual(self.h.memory.apply_calls, 1)


if __name__ == "__main__":
    unittest.main()
