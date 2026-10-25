"""共享授权域的真实 join、原子撤销、世界效果、容量与可信恢复反例。"""

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


M = load("shared_grant_test_model", "shared_grant_authority.py")
F = load("shared_grant_test_fixtures", "fixtures.py")
C = M.C


class SharedGrantTests(unittest.TestCase):
    def setUp(self):
        self.fixture = F.core_fixture(["core.session", "core.events", "actions", "multi-session"])
        self.owner = M.SharedGrantAuthority(self.fixture)

    def send(self, request, credential="player-fixture", *, sid=None, now=1000, fault=None):
        return C.codec.decode(self.owner.submit(C.codec.canonical(request), credential,
                                               session_id=sid, now=now, fault=fault))["result"]

    def invitation(self, sid, **kwargs):
        return self.owner.issue_invitation(sid, now=1000, **kwargs)

    def join_request(self, invitation, rid=None):
        return F.wire_request("session.join", {key: invitation[key] for key in ("invitation_id", "join_intent")},
                              rid or "join-" + invitation["invitation_id"])

    def join(self, sid, *, ready=True):
        invitation = self.invitation(sid)
        request = self.join_request(invitation)
        self.assertEqual(self.send(request, invitation["invitation_credential"])["status"], "join_pending")
        if ready:
            self.owner.finish_admission(sid, now=1000)
        result = self.send(request, invitation["invitation_credential"])
        return self.owner.sessions[sid], result, invitation

    def revoke(self, kind="grant", oid="g1", revision=1, rid="revoke"):
        return F.wire_request("permission.revoke", {"object_type": kind, "object_id": oid,
                              "expected_revision": revision}, rid)

    def action(self, sid, control):
        request = F.wire_request("action.request", {"version": "fixture-only", "session_id": sid,
            "id": "a1", "type": "action.request", "sender": self.fixture["agent"], "audience": [self.fixture["player"]],
            "expected_capabilities_revision": 1, "extensions": {},
            "payload": {"action": "find-key", "arguments": {"room": "hall"}, "deadline": 30000}})
        self.send(request, control, sid=sid)
        claim = F.wire_request("action.claim", {"session_id": sid, "action_id": "a1",
                               "worker": F.principal("worker-1", "service")}, "claim")
        return self.send(claim, "worker-1-fixture", sid=sid)["ticket"]

    def rejected(self, code, function):
        with self.assertRaises(C.ContractError) as caught:
            function()
        self.assertEqual(caught.exception.code, code)

    def test_one_grant_revoke_closes_ready_and_pending_and_invalidates_unconsumed_invitation(self):
        left, _, _ = self.join("left")
        right, _, _ = self.join("right", ready=False)
        invitation = self.invitation("late")
        result = self.send(self.revoke())
        self.assertEqual(result, {"object_type": "grant", "object_id": "g1", "revision": 2, "state": "revoked"})
        for child in (left, right):
            self.assertIs(child.state["grant"], self.owner.state["grant"])
            self.assertEqual(child.state["session"]["state"], "closed")
            self.assertFalse(child.action_model.model.authorized)
        self.assertEqual(self.owner.state["invitations"][invitation["invitation_id"]]["state"], "revoked")
        self.rejected("invitation_expired", lambda: self.send(self.join_request(invitation), invitation["invitation_credential"]))
        self.assertEqual(self.owner.finish_admission("right", now=1000)["state"], "closed")

    def test_session_close_and_session_revoke_do_not_revoke_shared_grant_or_sibling(self):
        for kind in ("session.close", "session"):
            with self.subTest(kind=kind):
                self.setUp()
                left, _, _ = self.join("left")
                right, ready, _ = self.join("right")
                request = (F.wire_request("session.close", {"session_id": "left", "reason": "left"})
                           if kind == "session.close" else self.revoke("session", "left"))
                self.send(request, sid="left")
                self.assertEqual(self.owner.state["grant"]["state"], "active")
                self.assertEqual(self.owner.state["grant"]["revision"], 1)
                self.assertEqual(left.state["session"]["state"], "closed")
                self.assertEqual(right.state["session"]["state"], "active")
                self.action("right", ready["control_credential"])

    def test_session_revision_is_independent_from_grant_and_other_session(self):
        left, _, _ = self.join("left")
        right, _, _ = self.join("right")
        self.send(self.revoke("session", "left"), sid="left")
        self.rejected("generation_conflict", lambda: self.send(self.revoke("session", "left", rid="stale"), sid="left"))
        self.assertEqual(self.send(self.revoke("session", "right", rid="right"), sid="right")["revision"], 2)
        self.assertEqual((left.session_revocation_revision, right.session_revocation_revision), (2, 2))
        self.assertEqual(self.send(self.revoke())["revision"], 2)

    def test_independent_capability_and_result_read_rights(self):
        left, lready, _ = self.join("left")
        right, rready, _ = self.join("right")
        self.action("left", lready["control_credential"])
        self.action("right", rready["control_credential"])
        self.send(self.revoke("capability", "find-key", rid="cap"), sid="left")
        self.send(self.revoke("result_read", "left", rid="read"), sid="left")
        query = lambda sid: F.wire_request("action.query", {"session_id": sid, "action_id": "a1"})
        self.rejected("permission_denied", lambda: self.send(query("left"), lready["result_read_handle"], sid="left"))
        self.assertEqual(self.send(query("right"), rready["result_read_handle"], sid="right")["state"], "executing")
        self.assertTrue(right.action_model.definition_available)
        self.assertEqual(right.state["session"]["capabilities_revision"], 1)
        self.assertEqual(self.owner.state["grant"]["revision"], 1)

    def test_prior_world_effects_survive_common_fence_and_rollback(self):
        tickets, worlds = {}, {}
        for sid in ("left", "right"):
            child, ready, _ = self.join(sid)
            tickets[sid] = self.action(sid, ready["control_credential"])
            child.execute("step", "worker-1", now=1000, ticket=tickets[sid], step=1)
            worlds[sid] = child.action_model.model.world
        with self.assertRaises(M.SharedGrantFault):
            self.send(self.revoke(), fault="after_first_close")
        for sid, child in self.owner.sessions.items():
            self.assertIs(child.action_model.model.world, worlds[sid])
            self.assertEqual(len(worlds[sid]), 1)
            self.assertEqual(child.state["session"]["state"], "active")
        self.send(self.revoke())
        for sid, child in self.owner.sessions.items():
            self.rejected("grant_revoked", lambda: child.execute("step", "worker-1", now=1000, ticket=tickets[sid], step=2))
            self.assertEqual(child.execute("step", "worker-1", now=1000, ticket=tickets[sid], step=1)["effect"], "committed")
            self.assertEqual(child.execute("finish", "worker-1", now=1000, ticket=tickets[sid]), ("cancelled", "partial"))
            self.assertEqual(len(worlds[sid]), 1)

    def test_effect_unknown_after_revoke_and_restart_is_reconciled_without_reexecution(self):
        child, ready, _ = self.join("left")
        ticket = self.action("left", ready["control_credential"])
        with self.assertRaises(M.U.A.M.SimulatedCrash):
            child.execute("step", "worker-1", now=1000, ticket=ticket, step=1, crash="after_effect")
        world = child.action_model.model.world
        self.send(self.revoke())
        self.owner = self.owner.restart_from_mock_ledger()
        child = self.owner.sessions["left"]
        self.assertIs(child.action_model.model.world, world)
        self.assertEqual(child.execute("reconcile", "worker-1", now=1000, ticket=ticket), "reconciled")
        self.assertEqual(child.execute("finish", "worker-1", now=1000, ticket=ticket), ("cancelled", "partial"))
        self.rejected("grant_revoked", lambda: child.execute("step", "worker-1", now=1000, ticket=ticket, step=2))
        self.assertEqual(len(world), 1)

    def test_both_precommit_faults_rollback_whole_authority(self):
        for fault in ("before_commit", "after_first_close"):
            with self.subTest(fault=fault):
                self.setUp(); self.join("left"); self.join("right"); self.invitation("late")
                before = self.owner.snapshot()
                with self.assertRaises(M.SharedGrantFault):
                    self.send(self.revoke(), fault=fault)
                self.assertEqual(self.owner.snapshot(), before)
                self.owner = self.owner.restart_from_mock_ledger(snapshot=before)
                self.assertEqual(self.send(self.revoke())["revision"], 2)

    def test_lost_response_replays_global_receipt_from_other_child_without_new_events(self):
        left, _, _ = self.join("left")
        self.join("right")
        with self.assertRaises(M.SharedGrantFault):
            left.submit(C.codec.canonical(self.revoke()), "player-fixture", now=1000, fault="after_commit")
        before = self.owner.snapshot()
        self.owner = self.owner.restart_from_mock_ledger(snapshot=before)
        reply = self.owner.sessions["right"].submit(C.codec.canonical(self.revoke()), "player-fixture", now=1000)
        self.assertEqual(C.codec.decode(reply)["result"]["revision"], 2)
        self.assertEqual(self.owner.snapshot(), before)

    def test_join_lost_response_after_revoke_is_redacted_not_resurrected(self):
        invitation = self.invitation("left")
        request = self.join_request(invitation)
        with self.assertRaises(M.SharedGrantFault):
            self.send(request, invitation["invitation_credential"], fault="after_commit")
        self.send(self.revoke())
        result = self.send(request, invitation["invitation_credential"])
        self.assertEqual(result["status"], "completed_without_secret")
        self.assertNotIn("control_credential", result)
        self.owner.finish_admission("left", now=1000)
        self.assertFalse(self.owner.sessions["left"].state["session"]["ready"])

    def test_both_join_revoke_serial_orders_and_concurrent_race_are_safe(self):
        for first in ("join", "revoke", "race"):
            with self.subTest(first=first):
                self.setUp()
                invitation = self.invitation("left")
                def join():
                    try:
                        return self.send(self.join_request(invitation), invitation["invitation_credential"])
                    except C.ContractError as error:
                        self.assertEqual(error.code, "invitation_expired")
                if first == "join":
                    join(); self.send(self.revoke())
                elif first == "revoke":
                    self.send(self.revoke()); join()
                else:
                    barrier = Barrier(2)
                    def synchronized(fn):
                        barrier.wait(timeout=10)
                        return fn()
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures = [pool.submit(synchronized, join), pool.submit(synchronized, lambda: self.send(self.revoke()))]
                        for future in futures:
                            future.result(timeout=20)
                self.assertEqual(self.owner.state["grant"]["state"], "revoked")
                self.assertTrue(all(c.state["session"]["state"] == "closed" for c in self.owner.sessions.values()))

    def test_capacity_counts_pending_sessions_and_single_session_profile_rejects_second(self):
        for multi in (True, False):
            with self.subTest(multi=multi):
                self.fixture = F.core_fixture(["core.session", "core.events", "actions", "multi-session"] if multi else None)
                self.owner = M.SharedGrantAuthority(self.fixture)
                self.join("left", ready=False)
                if multi:
                    self.join("right", ready=False)
                invitation = self.invitation("overflow")
                self.rejected("session_conflict", lambda: self.send(self.join_request(invitation), invitation["invitation_credential"]))
                self.assertEqual(self.owner.state["invitations"][invitation["invitation_id"]]["state"], "issued")

    def test_closed_slot_allows_fresh_session_but_never_reuses_old_id(self):
        self.join("left"); self.join("right")
        invitation = self.invitation("fresh")
        self.send(self.revoke("session", "left"), sid="left")
        self.assertEqual(self.send(self.join_request(invitation), invitation["invitation_credential"])["status"], "join_pending")
        self.rejected("id_conflict", lambda: self.invitation("left"))
        self.assertEqual(self.owner.state["grant"]["state"], "active")

    def test_wrong_player_game_grant_revision_and_same_id_changed_bytes_are_rejected(self):
        self.join("left")
        for role in ("player", "game"):
            token = "wrong-" + role
            self.owner.identities[token] = {"role": role, "principal": F.principal("other", role)}
            self.owner._checkpoint()  # 仅可信身份夹具登记；请求不能登记。
            self.rejected("permission_denied", lambda: self.send(self.revoke(), token))
        self.rejected("permission_denied", lambda: self.send(self.revoke(oid="foreign")))
        self.rejected("generation_conflict", lambda: self.send(self.revoke(revision=2)))
        self.send(self.revoke())
        self.rejected("id_conflict", lambda: self.send(self.revoke(revision=2)))

    def test_child_control_credentials_cannot_cross_session_and_agent_cannot_revoke_grant(self):
        _, left, _ = self.join("left")
        self.join("right")
        heartbeat = F.wire_request("session.heartbeat", {"session_id": "right"})
        self.rejected("unauthenticated", lambda: self.send(heartbeat, left["control_credential"], sid="right"))
        self.rejected("permission_denied", lambda: self.send(self.revoke(), "agent-identity"))

    def test_operation_get_reports_original_global_commit_without_secrets(self):
        self.join("left")
        self.send(self.revoke())
        query = F.wire_request("operation.get", {"operation": "permission.revoke", "original_request_id": "revoke"})
        result = self.send(query)
        self.assertEqual(result["state"], "done")
        self.assertEqual(result["revocation"]["revision"], 2)
        self.assertNotIn("credential", repr(result))
        self.rejected("permission_denied", lambda: self.send(query, "agent-identity"))

    def test_old_foreign_mixed_and_tampered_snapshots_do_not_retire_current_owner(self):
        self.join("left")
        old = self.owner.snapshot()
        self.join("right")
        current = self.owner.snapshot()
        candidates = [old, M.SharedGrantAuthority(self.fixture).snapshot()]
        for field in ("grant", "invitations", "receipts"):
            mixed = deepcopy(current); mixed["state"][field] = deepcopy(old["state"][field])
            if mixed != current:
                candidates.append(mixed)
        tampered = deepcopy(current); tampered["sessions"]["left"]["session_revision"] = True
        candidates.append(tampered)
        for candidate in candidates:
            self.rejected("snapshot_mismatch", lambda: self.owner.restart_from_mock_ledger(snapshot=candidate))
            self.assertFalse(self.owner.retired)
            self.assertEqual(self.owner.snapshot(), current)

    def test_successful_restart_retires_old_owner_and_all_old_child_ports(self):
        old = self.owner
        child, ready, _ = self.join("left")
        self.owner = old.restart_from_mock_ledger()
        heartbeat = F.wire_request("session.heartbeat", {"session_id": "left"})
        self.rejected("temporarily_unavailable", lambda: child.submit(C.codec.canonical(heartbeat), ready["control_credential"], now=1000))
        self.rejected("temporarily_unavailable", lambda: child.execute("claim", "worker-1", now=1000))
        self.rejected("temporarily_unavailable", lambda: child.delivery(self.fixture["agent"], now=1000))
        self.rejected("temporarily_unavailable", lambda: old.issue_invitation("late", now=1000))
        self.assertEqual(self.send(heartbeat, ready["control_credential"], sid="left")["state"], "active")

    def test_unhealthy_restore_and_corrupted_auth_fail_closed(self):
        self.join("left")
        self.owner = self.owner.restart_from_mock_ledger(intact=False)
        self.rejected("temporarily_unavailable", lambda: self.send(self.revoke()))
        self.setUp(); self.join("left")
        self.owner.identities["player-fixture"]["principal"] = F.principal("other", "player")
        self.rejected("temporarily_unavailable", lambda: self.send(self.revoke()))
        self.assertFalse(self.owner.healthy)

    def test_full_regular_receipts_do_not_block_grant_revocation_or_replay(self):
        self.join("left"); self.join("right")
        while len(self.owner.state["receipts"]) < self.owner.MAX_RECEIPTS:
            self.owner.state["receipts"][("trusted-dummy", str(len(self.owner.state["receipts"])))] = {"fixture": True}
        self.owner._checkpoint()
        self.assertEqual(self.send(self.revoke())["revision"], 2)
        self.assertEqual(self.send(self.revoke())["revision"], 2)
        self.assertTrue(all(c.state["session"]["state"] == "closed" for c in self.owner.sessions.values()))

    def test_expiry_is_committed_before_invalid_request_and_cannot_be_rolled_back(self):
        self.join("left", ready=False)
        self.rejected("unauthenticated", lambda: self.send(self.revoke(), "unknown", now=121001))
        self.assertEqual(self.owner.sessions["left"].state["session"]["state"], "closed")
        self.rejected("temporarily_unavailable", lambda: self.send(self.revoke(), now=1000))

    def test_expired_invitation_cannot_join_or_finish_pending_admission(self):
        invitation = self.invitation("left", ttl_ms=1)
        self.send(self.join_request(invitation), invitation["invitation_credential"])
        self.assertEqual(self.owner.finish_admission("left", now=1001)["state"], "closed")
        late = self.owner.issue_invitation("late", now=1001, ttl_ms=1)
        self.rejected("invitation_expired", lambda: self.send(self.join_request(late), late["invitation_credential"], now=1002))

    def test_join_before_commit_does_not_consume_invitation_or_leave_orphan_port(self):
        invitation = self.invitation("left")
        before = self.owner.snapshot()
        with self.assertRaises(M.SharedGrantFault):
            self.send(self.join_request(invitation), invitation["invitation_credential"], fault="before_commit")
        self.assertEqual(self.owner.snapshot(), before)
        self.assertNotIn("left", self.owner.sessions)
        self.assertEqual(self.send(self.join_request(invitation), invitation["invitation_credential"])["status"], "join_pending")

    def test_invitation_identity_and_frozen_scope_cannot_be_substituted(self):
        left, right = self.invitation("left"), self.invitation("right")
        self.rejected("permission_denied", lambda: self.send(self.join_request(left), right["invitation_credential"]))
        self.rejected("permission_denied", lambda: self.send(self.join_request(left), "agent-identity"))
        changed = deepcopy(left); changed["join_intent"]["scope_digest"] = "0" * 64
        self.rejected("invitation_used", lambda: self.send(self.join_request(changed), left["invitation_credential"]))
        self.assertFalse(self.owner.sessions)

    def test_expired_authenticated_identity_cannot_replay_global_receipt(self):
        self.owner.identities["player-fixture"]["expires_at"] = 1001
        self.owner._checkpoint()
        self.send(self.revoke())
        self.rejected("unauthenticated", lambda: self.send(self.revoke(), now=1001))
        self.assertEqual(self.owner.state["grant"]["revision"], 2)

    def test_local_control_lost_response_uses_original_session_operation_view(self):
        self.join("left"); self.join("right")
        with self.assertRaises(M.SharedGrantFault):
            self.send(self.revoke("session", "left", rid="local"), sid="left", fault="after_commit")
        query = F.wire_request("operation.get", {"operation": "permission.revoke", "original_request_id": "local"})
        self.assertEqual(self.send(query, sid="left")["revocation"]["object_id"], "left")
        self.rejected("permission_denied", lambda: self.send(query, sid="right"))
        self.assertEqual(self.owner.state["grant"]["state"], "active")

    def test_full_child_event_outboxes_do_not_block_atomic_grant_stop(self):
        for sid in ("left", "right"):
            child, ready, _ = self.join(sid)
            self.action(sid, ready["control_credential"])
            while len(child.state["events"]) < 64:
                number = child.state["session"]["sequence"]
                context = F.wire_request("context.publish", {"version": "fixture-only", "session_id": sid,
                    "id": "context-" + str(number), "type": "game.context", "sender": self.fixture["game"],
                    "audience": [self.fixture["agent"]], "payload": {"category": "room", "content": "hall", "provenance": []},
                    "extensions": {}})
                self.send(context, "game-fixture", sid=sid)
        before = self.owner.snapshot()
        with self.assertRaises(M.SharedGrantFault):
            self.send(self.revoke(), fault="after_first_close")
        self.assertEqual(self.owner.snapshot(), before)
        self.send(self.revoke())
        for child in self.owner.sessions.values():
            self.assertEqual(child.state["session"]["state"], "closed")
            self.assertLessEqual(len(child.state["events"]), 64)
            self.assertEqual(child.state["events"][-1]["wire"]["envelope"]["type"], "session.closed")

    def test_invitation_capacity_does_not_block_revoke_or_delete_original_bindings(self):
        first = self.invitation("first")
        for number in range(self.owner.MAX_INVITATIONS - 1):
            self.invitation("slot-" + str(number))
        self.rejected("resource_limit", lambda: self.invitation("overflow"))
        self.send(self.revoke(), "game-fixture")
        self.assertEqual(len(self.owner.state["invitations"]), self.owner.MAX_INVITATIONS)
        self.assertTrue(all(i["state"] == "revoked" for i in self.owner.state["invitations"].values()))
        self.rejected("invitation_expired", lambda: self.send(self.join_request(first), first["invitation_credential"]))

    def test_snapshot_container_or_credential_injection_cannot_replace_trusted_bindings(self):
        self.join("left")
        before = self.owner.snapshot()
        injected = deepcopy(before); injected["credentials"] = {"fake": "player"}
        self.rejected("invalid_snapshot", lambda: self.owner.restart_from_mock_ledger(snapshot=injected))
        forged = deepcopy(before); forged["sessions"]["left"]["state"]["revoked_capabilities"] = ["set", []]
        self.rejected("snapshot_mismatch", lambda: self.owner.restart_from_mock_ledger(snapshot=forged))
        self.assertEqual(self.owner.snapshot(), before)

    def test_publish_failure_after_effect_keeps_world_and_pending_knowledge_on_restart(self):
        child, ready, _ = self.join("left")
        ticket = self.action("left", ready["control_credential"])
        world = child.action_model.model.world
        with self.assertRaises(M.SharedGrantFault):
            child.execute("step", "worker-1", now=1000, ticket=ticket, step=1, publish_fault="before_commit")
        self.assertTrue(child.pending_sync)
        self.assertIs(child.action_model.model.world, world)
        self.assertEqual(len(world), 1)
        self.owner = self.owner.restart_from_mock_ledger()
        query = F.wire_request("action.query", {"session_id": "left", "action_id": "a1"})
        self.assertEqual(self.send(query, ready["result_read_handle"], sid="left")["effect"], "partial")
        self.assertFalse(self.owner.sessions["left"].pending_sync)
        self.assertIs(self.owner.sessions["left"].action_model.model.world, world)

    def test_retained_action_port_cannot_bypass_owner_or_execute_after_restart_revocation(self):
        child, ready, _ = self.join("left")
        ticket = self.action("left", ready["control_credential"])
        old = child.action_model
        world = old.model.world
        step = lambda: old.execute("step", "worker-1", now=1000, ticket=ticket, step=1)
        self.rejected("temporarily_unavailable", step)  # 活动内部端口也不能跳过 owner 的入口。
        self.assertFalse(world)
        self.owner = self.owner.restart_from_mock_ledger()
        self.send(self.revoke())
        query = F.wire_request("action.query", {"session_id": "left", "action_id": "a1"})
        for operation in (step,
                lambda: old.submit(C.codec.canonical(query), ready["result_read_handle"], now=1000),
                lambda: old.revoke(now=1000),
                lambda: old.operation_view({"operation": "action.request", "original_request_id": "r1"},
                    {"principal": self.fixture["agent"]}, now=1000)):
            self.rejected("temporarily_unavailable", operation)
        self.assertFalse(world)

    def test_wire_action_commits_keep_external_world_binding_across_faults_and_restart(self):
        for terminal in ("action.cancel", "action.commit_result"):
            for fault in (None, "before_commit", "after_commit"):
                with self.subTest(terminal=terminal, fault=fault):
                    self.setUp()
                    child, ready, _ = self.join("left")
                    world = child.action_model.model.world  # 首次 request/claim 之前保存外部对象。
                    request = F.wire_request("action.request", {"version": "fixture-only", "session_id": "left",
                        "id": "a1", "type": "action.request", "sender": self.fixture["agent"],
                        "audience": [self.fixture["player"]], "expected_capabilities_revision": 1, "extensions": {},
                        "payload": {"action": "find-key", "arguments": {"room": "hall"}, "deadline": 30000}})
                    self.send(request, ready["control_credential"], sid="left")
                    self.assertIs(child.action_model.model.world, world)
                    self.assertIs(child.action_model.model.lock, self.owner.lock)
                    claim = F.wire_request("action.claim", {"session_id": "left", "action_id": "a1",
                        "worker": F.principal("worker-1", "service")}, "claim")
                    ticket = self.send(claim, "worker-1-fixture", sid="left")["ticket"]
                    self.assertIs(child.action_model.model.world, world)
                    steps = (1,) if terminal == "action.cancel" else (1, 2)
                    for step in steps:
                        child.execute("step", "worker-1", now=1000, ticket=ticket, step=step)
                    if terminal == "action.cancel":
                        finish = deepcopy(request)
                        finish.update(operation=terminal, request_id="cancel")
                        finish["payload"].update(id="cancel-1", type=terminal, payload={"request_id": "a1"})
                        credential = ready["control_credential"]
                    else:
                        finish = F.wire_request(terminal, {"ticket": ticket, "fact": {
                            "state": "succeeded", "effect": "committed", "result": {"item": "gold-key"},
                            "steps": [{"step": step, "effect": "committed",
                                       "evidence_ref": ticket["proof_ref"] + "-step-" + str(step)} for step in steps]}}, "commit")
                        credential = "worker-1-fixture"
                    before = self.owner.snapshot()
                    if fault is not None:
                        with self.assertRaises(M.SharedGrantFault):
                            self.send(finish, credential, sid="left", fault=fault)
                        self.assertIs(child.action_model.model.world, world)
                        if fault == "before_commit":
                            self.assertEqual(self.owner.snapshot(), before)
                    result = self.send(finish, credential, sid="left")
                    committed = self.owner.snapshot()
                    self.assertIs(child.action_model.model.world, world)
                    self.assertIs(child.action_model.model.lock, self.owner.lock)
                    self.owner = self.owner.restart_from_mock_ledger()
                    child = self.owner.sessions["left"]
                    replay = self.send(finish, credential, sid="left")
                    if terminal == "action.cancel":
                        self.assertEqual(replay, {**result, "duplicate": True})
                    else:
                        self.assertEqual(replay, result)
                    self.assertEqual(child.action_model.revision, committed["sessions"]["left"]["action"]["revision"])
                    self.assertEqual(child.state["events"], committed["sessions"]["left"]["state"]["events"])
                    self.assertEqual(self.owner.snapshot()["sessions"]["left"]["model"], committed["sessions"]["left"]["model"])
                    self.assertIs(child.action_model.model.world, world)
                    self.assertIs(child.action_model.model.lock, self.owner.lock)
                    for step in steps:
                        child.execute("step", "worker-1", now=1000, ticket=ticket, step=step)
                    self.assertEqual(len(world), len(steps))


if __name__ == "__main__":
    unittest.main()
