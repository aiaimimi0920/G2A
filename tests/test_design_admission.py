"""准入到数据面字节链；假认证/批准/准备端口，不伪装成外部适配器。"""

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


A = load("admission_test", "admission_harness.py")
F = load("admission_test_fixture", "fixtures.py")
C = A.C


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.f = F.core_fixture()
        self.h = A.AdmissionHarness(self.f)

    def send(self, operation, payload, credential="agent-identity", request_id="r1", now=1000, fault=None):
        req = F.wire_request(operation, payload, request_id)
        return C.codec.decode(self.h.submit(C.codec.canonical(req), credential, now=now, fault=fault))["result"]

    def create(self, *, entry="companion", **kwargs):
        payload = {"entry": entry, "descriptor_id": "fixture-descriptor", "expected_descriptor_revision": 1,
                   "requested": deepcopy(self.f["requested"])}
        credential = "agent-identity" if entry == "companion" else "player-fixture"
        return self.send("offer.create", payload, credential, **kwargs)

    def decide(self, offer, allow=True, **kwargs):
        payload = {"offer_id": offer["offer_id"], "scope_digest": offer["scope_digest"], "allow": allow,
                   "remember": False, "launch_permission": False, "decision_ref": "decision-" + offer["offer_id"]}
        self.h.decisions[payload["decision_ref"]] = {"player": self.f["player"], "payload": deepcopy(payload)}
        return self.send("offer.decide", payload, "player-fixture", **kwargs)

    def invite(self, offer=None):
        if offer is None:
            offer = self.create()
            self.decide(offer)
        payload = {"offer_id": offer["offer_id"], "join_intent": {"scope_digest": offer["scope_digest"]}}
        return self.send("invitation.redeem", payload)

    def join(self, invitation, **kwargs):
        return self.send("session.join", {key: invitation[key] for key in ("invitation_id", "join_intent")},
                         invitation["invitation_credential"], **kwargs)

    def ready(self):
        invitation = self.invite()
        self.join(invitation)
        self.h.finish_admission(now=1000)
        return invitation, self.join(invitation)

    def assert_error(self, code, function):
        with self.assertRaises(C.ContractError) as caught:
            function()
        self.assertEqual(caught.exception.code, code)

    def test_both_entries_reach_ready_then_chat_and_business_event_consumer(self):
        for entry in ("companion", "game"):
            with self.subTest(entry=entry):
                self.setUp()
                descriptor = self.send("describe", {"instance": self.f["scope"]["instance"]})
                self.assertEqual(descriptor["descriptor_id"], "fixture-descriptor")
                offer = self.create(entry=entry)
                self.assertEqual(self.decide(offer)["state"], "approved")
                invitation = self.invite(offer)
                self.assertEqual(self.join(invitation), {"status": "join_pending", "session_id": "s1"})
                pending = deepcopy(self.h.session.state["session"])
                snapshot = {"snapshot_version": "g2a-recovery-1", "session": pending,
                    "cursor": {"session_id": "s1", "instance_epoch": "epoch-1", "sequence": 0},
                    "actions": [], "contexts": [], "definitions": [self.f["action"]], "members": self.f["scope"]["audiences"]}
                consumer = A.U.S.E.BusinessConsumer(snapshot, self.f["agent"])
                self.h.finish_admission(now=1000)
                delivery = self.join(invitation)
                token = delivery["control_credential"]
                self.assertEqual(delivery["event_high_watermark"]["sequence"], 1)
                message = {"version": "fixture-only", "session_id": "s1", "id": "m1", "type": "chat.message",
                    "sender": self.f["agent"], "audience": [self.f["agent"], self.f["player"]], "extensions": {},
                    "payload": {"channel": "private", "text": "已经加入", "source_refs": [], "provenance": []}}
                self.send("chat.send", message, token)
                page = self.send("session.events", {"session_id": "s1", "cursor": snapshot["cursor"], "page_size": 64}, token)
                consumer.apply_page(page, snapshot["cursor"])
                self.assertTrue(consumer.view["session"]["ready"])
                self.assertEqual([event["envelope"]["type"] for event in page["events"]], ["session.ready", "chat.message"])

    def test_identity_is_verified_before_describe_or_offer_lookup(self):
        self.assert_error("unauthenticated", lambda: self.send("describe", {"instance": self.f["scope"]["instance"]}, "unknown"))
        self.h.identities["outsider"] = {"role": "agent", "principal": F.principal("other", "agent")}
        offer = self.create()
        self.assert_error("permission_denied", lambda: self.send("offer.get", {"offer_id": offer["offer_id"]}, "outsider"))
        self.assert_error("permission_denied", lambda: self.send("describe", {"instance": self.f["scope"]["instance"]}, "game-fixture"))

    def test_unapproved_missing_proof_and_identity_swap_cannot_join(self):
        offer = self.create()
        self.assert_error("consent_required", lambda: self.invite(offer))
        payload = {"offer_id": offer["offer_id"], "scope_digest": offer["scope_digest"], "allow": True,
                   "remember": False, "launch_permission": False, "decision_ref": "invented"}
        self.assert_error("consent_required", lambda: self.send("offer.decide", payload, "player-fixture"))
        self.decide(offer)
        invitation = self.invite(offer)
        payload = {key: invitation[key] for key in ("invitation_id", "join_intent")}
        self.assert_error("permission_denied", lambda: self.send("session.join", payload))
        self.assert_error("permission_denied", lambda: self.send("session.join", payload, "player-fixture"))
        self.assertIsNone(self.h.session)

    def test_create_and_decide_faults_restore_nonce_and_consent_consumption(self):
        self.h._maintain(1000)
        before = deepcopy(self.h.state)
        with self.assertRaises(A.U.S.H.InjectedFailure):
            self.create(fault="before_commit")
        self.assertEqual(self.h.state, before)
        with self.assertRaises(A.U.S.H.InjectedFailure):
            self.create(fault="after_commit")
        offer = self.create()
        self.assertEqual(len(self.h.state["offers"]), 1)
        with self.assertRaises(A.U.S.H.InjectedFailure):
            self.decide(offer, fault="before_commit")
        self.assertEqual(self.h.state["grants"], {})
        self.assertEqual(self.h.state["decision_used"], {})
        with self.assertRaises(A.U.S.H.InjectedFailure):
            self.decide(offer, fault="after_commit")
        self.assertEqual(self.decide(offer)["state"], "approved")
        self.decide(offer, request_id="new-transport-id")
        self.assertEqual(len(self.h.state["grants"]), 1)

    def test_immutable_scope_digest_and_request_content_conflict(self):
        offer = self.create()
        self.assertEqual(offer["scope_digest"], C.codec.digest("scope", offer["immutable_scope"]))
        changed = deepcopy(self.f["requested"])
        changed["maximum_grant_duration_ms"] -= 1
        self.assert_error("id_conflict", lambda: self.send("offer.create", {"entry": "companion", "descriptor_id": "fixture-descriptor",
            "expected_descriptor_revision": 1, "requested": changed}))
        self.assertEqual(self.create(now=2000)["immutable_scope"]["created_at"], 1000)

    def test_deny_and_unsupported_remember_do_not_create_grant(self):
        offer = self.create()
        self.assertEqual(self.decide(offer, allow=False)["state"], "denied")
        self.assert_error("consent_required", lambda: self.invite(offer))
        self.assertEqual(self.h.state["grants"], {})
        self.setUp()
        offer = self.create()
        payload = {"offer_id": offer["offer_id"], "scope_digest": offer["scope_digest"], "allow": True,
                   "remember": True, "launch_permission": False, "decision_ref": "remember",
                   "rule_expires_at": 600000, "maximum_grant_duration_ms": 300000}
        self.h.decisions["remember"] = {"player": self.f["player"], "payload": payload}
        self.assert_error("feature_unsupported", lambda: self.send("offer.decide", payload, "player-fixture"))
        self.assertEqual(self.h.state["grants"], {})

    def test_descriptor_change_or_expired_offer_cannot_be_approved(self):
        offer = self.create()
        self.h.state["descriptor"]["revision"] = 2
        self.assert_error("approval_stale", lambda: self.decide(offer))
        self.assertEqual(self.send("offer.get", {"offer_id": offer["offer_id"]})["state"], "stale")
        self.setUp()
        offer = self.create()
        self.assert_error("offer_expired", lambda: self.decide(offer, now=61000))
        self.assertEqual(self.h.state["offers"][offer["offer_id"]]["view"]["state"], "expired")

    def test_redeem_retry_is_same_secret_and_no_second_invitation(self):
        offer = self.create()
        self.decide(offer)
        payload = {"offer_id": offer["offer_id"], "join_intent": {"scope_digest": offer["scope_digest"]}}
        with self.assertRaises(A.U.S.H.InjectedFailure):
            self.send("invitation.redeem", payload, fault="before_commit")
        self.assertEqual(self.h.state["invitations"], {})
        with self.assertRaises(A.U.S.H.InjectedFailure):
            self.send("invitation.redeem", payload, fault="after_commit")
        first = self.send("invitation.redeem", payload)
        second = self.send("invitation.redeem", payload, request_id="different-id", now=2000)
        self.assertEqual(first, second)
        self.assertEqual(len(self.h.state["invitations"]), 1)
        self.assert_error("permission_denied", lambda: self.send("invitation.redeem", payload, "player-fixture", now=2000))
        expired = self.send("invitation.redeem", payload, now=first["expires_at"])
        self.assertEqual(expired["status"], "completed_without_secret")
        self.assert_error("invitation_expired", lambda: self.join(first, now=first["expires_at"]))

    def test_join_and_ready_faults_do_not_leak_or_duplicate_credentials(self):
        invitation = self.invite()
        with self.assertRaises(A.U.S.H.InjectedFailure):
            self.join(invitation, fault="before_commit")
        self.assertIsNone(self.h.session)
        self.assertEqual(self.h.state["invitations"][invitation["invitation_id"]]["state"], "issued")
        with self.assertRaises(A.U.S.H.InjectedFailure):
            self.join(invitation, fault="after_commit")
        self.assertEqual(self.join(invitation)["status"], "join_pending")
        internal_token = self.h.state["invitations"][invitation["invitation_id"]]["control"]
        self.assert_error("session_not_writable", lambda: self.send("session.snapshot", {"session_id": "s1"}, internal_token))
        self.assert_error("unauthenticated", lambda: self.send("session.snapshot", {"session_id": "s1"}, "agent-fixture"))
        with self.assertRaises(A.U.S.H.InjectedFailure):
            self.h.finish_admission(now=1000, fault="before_commit")
        self.assertFalse(self.h.session.state["session"]["ready"])
        self.assertEqual(self.h.session.state["events"], [])
        with self.assertRaises(A.U.S.H.InjectedFailure):
            self.h.finish_admission(now=1000, fault="after_commit")
        self.h.finish_admission(now=1000)
        self.assertEqual(self.h.session.state["session"]["sequence"], 1)
        ready = self.join(invitation)
        self.assertEqual(ready["status"], "ready")
        self.assertEqual(self.join(invitation, now=2000)["session"]["lease_deadline"], ready["session"]["lease_deadline"])

    def test_admission_failure_or_changed_descriptor_closes_without_secret(self):
        for failure in ("prepare", "stale"):
            with self.subTest(failure=failure):
                self.setUp()
                invitation = self.invite()
                self.join(invitation)
                if failure == "stale":
                    self.h.state["descriptor"]["revision"] = 2
                result = self.h.finish_admission(now=1000, success=failure != "prepare")
                self.assertEqual(result["state"], "closed")
                self.assertEqual(self.join(invitation)["status"], "completed_without_secret")
                self.h.finish_admission(now=1000)
                self.assertFalse(self.h.session.state["session"]["ready"])

    def test_revoked_invitation_and_grant_prevent_join_and_secret_replay(self):
        for kind in ("grant", "invitation"):
            with self.subTest(kind=kind):
                self.setUp()
                invitation = self.invite()
                oid = "grant-1" if kind == "grant" else invitation["invitation_id"]
                result = self.send("permission.revoke", {"object_type": kind, "object_id": oid, "expected_revision": 1}, "player-fixture")
                self.assertEqual(result["state"], "revoked")
                with self.assertRaises(C.ContractError):
                    self.join(invitation)
                replay = self.send("invitation.redeem", {"offer_id": "offer-1", "join_intent": invitation["join_intent"]})
                self.assertEqual(replay["status"], "completed_without_secret")
                self.assertIsNone(self.h.session)

    def test_consumed_invitation_revoke_does_not_close_active_session(self):
        invitation, delivery = self.ready()
        result = self.send("permission.revoke", {"object_type": "invitation", "object_id": invitation["invitation_id"], "expected_revision": 1}, "player-fixture")
        self.assertEqual(result["state"], "consumed")
        self.assertTrue(self.send("session.snapshot", {"session_id": "s1"}, delivery["control_credential"])["session"]["ready"])

    def test_operation_get_is_current_and_secret_free_and_subject_isolated(self):
        invitation = self.invite()
        self.join(invitation)
        lookup = {"operation": "session.join", "original_request_id": "r1"}
        self.assertEqual(self.send("operation.get", lookup)["state"], "pending")
        self.h.finish_admission(now=1000)
        view = self.send("operation.get", lookup)
        self.assertEqual(view["state"], "done")
        encoded = C.codec.canonical(view)
        self.assertNotIn(b"fixture-control", encoded)
        self.assertNotIn(b"fixture-results", encoded)
        self.assert_error("permission_denied", lambda: self.send("operation.get", lookup, "player-fixture"))
        self.assert_error("permission_denied", lambda: self.send("operation.get", {"operation": "offer.decide", "original_request_id": "r1"}))

    def test_expiry_maintenance_commits_even_when_request_fails(self):
        invitation, delivery = self.ready()
        deadline = delivery["session"]["lease_deadline"]
        with self.assertRaises(C.ContractError):
            self.send("session.snapshot", {"session_id": "s1"}, "unknown", now=deadline)
        self.assertEqual(self.h.session.state["session"]["state"], "closed")
        self.assertEqual(self.join(invitation, now=deadline)["status"], "completed_without_secret")
        self.assert_error("temporarily_unavailable", lambda: self.join(invitation, now=deadline - 1))

    def test_closed_or_new_generation_never_replays_original_control_secret(self):
        invitation, delivery = self.ready()
        self.h.session.state["session"]["control_generation"] += 1  # 可信代次变化夹具，不冒充 resume 实现。
        self.assertEqual(self.join(invitation)["status"], "completed_without_secret")
        replay = self.send("invitation.redeem", {"offer_id": "offer-1", "join_intent": invitation["join_intent"]})
        self.assertEqual(replay.get("status"), "completed_without_secret")
        self.send("session.close", {"session_id": "s1", "reason": "left"}, "player-fixture")
        self.assertEqual(self.join(invitation)["status"], "completed_without_secret")
        # 原加入已 ready；停止回放秘密不把原提交事实改成失败。
        view = self.send("operation.get", {"operation": "session.join", "original_request_id": "r1"})
        self.assertEqual((view["state"], view["session"]["state"]), ("done", "closed"))

    def test_actual_duplicate_join_and_ready_close_races(self):
        for _ in range(6):
            self.setUp()
            invitation = self.invite()
            barrier = Barrier(2)
            def join():
                barrier.wait(timeout=5)
                return self.join(invitation)
            with ThreadPoolExecutor(max_workers=2) as pool:
                first, second = pool.submit(join), pool.submit(join)
                self.assertEqual(first.result(timeout=5), second.result(timeout=5))
            self.assertEqual(len(self.h.state["invitations"]), 1)
            barrier = Barrier(2)
            def ready():
                barrier.wait(timeout=5)
                return self.h.finish_admission(now=1000)
            def close():
                barrier.wait(timeout=5)
                return self.send("session.close", {"session_id": "s1", "reason": "left"}, "player-fixture")
            with ThreadPoolExecutor(max_workers=2) as pool:
                first, second = pool.submit(ready), pool.submit(close)
                first.result(timeout=5)
                second.result(timeout=5)
            self.assertEqual(self.h.session.state["session"]["state"], "closed")
            self.assertEqual(self.join(invitation)["status"], "completed_without_secret")
            types = [e["wire"]["envelope"]["type"] for e in self.h.session.state["events"]]
            self.assertIn(types, [["session.closed"], ["session.ready", "session.closed"]])

    def test_narrow_profile_negotiation_fails_required_features_and_keeps_core_usable(self):
        for field, value in (("required_features", ["resume"]), ("bindings", [{**self.f["scope"]["binding"], "endpoint": "https://other.invalid"}])):
            requested = deepcopy(self.f["requested"])
            requested[field] = value
            with self.assertRaises(C.ContractError):
                self.send("offer.create", {"entry": "companion", "descriptor_id": "fixture-descriptor", "expected_descriptor_revision": 1, "requested": requested})
            self.assertEqual(self.h.state["offers"], {})
        self.f = F.core_fixture(["core.session", "core.events"])
        self.h = A.AdmissionHarness(self.f)
        _, delivery = self.ready()
        snapshot = self.send("session.snapshot", {"session_id": "s1"}, delivery["control_credential"])
        self.assertEqual(snapshot["definitions"], [])

    def test_negotiated_empty_action_selection_does_not_advertise_unapproved_definition(self):
        self.f["requested"]["action_ids"] = []
        _, delivery = self.ready()
        snapshot = self.send("session.snapshot", {"session_id": "s1"}, delivery["control_credential"])
        self.assertEqual(snapshot["definitions"], [])
        A.U.S.E.BusinessConsumer(snapshot, self.f["agent"])

    def test_ready_delivery_runs_real_action_pipeline_and_result_handle_is_read_only(self):
        _, delivery = self.ready()
        token, handle = delivery["control_credential"], delivery["result_read_handle"]
        payload = {"version": "fixture-only", "session_id": "s1", "id": "a1", "type": "action.request",
            "sender": self.f["agent"], "audience": [self.f["player"]], "expected_capabilities_revision": 1,
            "extensions": {}, "payload": {"action": "find-key", "arguments": {"room": "hall"}, "deadline": 30000}}
        self.assert_error("permission_denied", lambda: self.send("action.request", payload, handle))
        self.send("action.request", payload, token)
        ticket = self.send("action.claim", {"session_id": "s1", "action_id": "a1", "worker": F.principal("worker-1", "service")}, "worker-1-fixture")["ticket"]
        for step in (1, 2):
            self.h.execute("step", "worker-1", now=1000, ticket=ticket, step=step)
        fact = {"state": "succeeded", "effect": "committed", "result": {"item": "gold-key"},
                "steps": [{"step": step, "effect": "committed", "evidence_ref": ticket["proof_ref"] + "-step-" + str(step)} for step in (1, 2)]}
        final = self.send("action.commit_result", {"ticket": ticket, "fact": fact}, "worker-1-fixture")
        self.send("session.close", {"session_id": "s1", "reason": "left"}, "player-fixture")
        self.assertEqual(self.send("action.query", {"session_id": "s1", "action_id": "a1"}, handle)["known_result"], final["known_result"])

    def test_grant_revoke_after_join_is_atomic_with_session_and_no_secret_replay(self):
        invitation, delivery = self.ready()
        payload = {"object_type": "grant", "object_id": "grant-1", "expected_revision": 1}
        before = deepcopy(self.h.session.state)
        with self.assertRaises(A.U.S.H.InjectedFailure):
            self.send("permission.revoke", payload, "player-fixture", fault="before_commit")
        self.assertEqual(self.h.session.state, before)
        self.assertEqual(self.join(invitation)["status"], "ready")
        result = self.send("permission.revoke", payload, "player-fixture")
        self.assertEqual(result["revision"], 2)
        self.assertEqual(self.h.session.state["grant"]["revision"], 2)
        self.assertEqual(self.join(invitation)["status"], "completed_without_secret")
        self.assertEqual(self.h.session.state["session"]["state"], "closed")


if __name__ == "__main__":
    unittest.main()
