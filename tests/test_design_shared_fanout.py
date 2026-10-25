"""共享 Grant 与跨 authority fanout 的组合反例；只使用独立内存世界。"""

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


G = load("shared_fanout_grant", "shared_grant_authority.py")
M = load("shared_fanout_coordinator", "revoke_fanout.py")
F = load("shared_fanout_fixtures", "fixtures.py")
C = M.C


class SharedFanoutTests(unittest.TestCase):
    def setUp(self):
        self.fixture = F.core_fixture(["core.session", "core.events", "actions", "multi-session"])
        self.player = self.fixture["player"]
        self.owner = G.SharedGrantAuthority(self.fixture)
        self.fanout = M.SessionRevokeFanout(self.player)
        self.keys, self.ready = {}, {}
        for sid in ("left", "right"):
            child, ready = self.join(self.owner, sid)
            self.ready[sid] = ready
            self.keys[sid] = self.fanout.register(child, "player-fixture")

    def send(self, owner, request, credential="player-fixture", sid=None):
        return C.codec.decode(owner.submit(C.codec.canonical(request), credential, now=1000, session_id=sid))["result"]

    def join(self, owner, sid):
        invitation = owner.issue_invitation(sid, now=1000)
        request = F.wire_request("session.join", {key: invitation[key] for key in ("invitation_id", "join_intent")}, "join-" + sid)
        self.send(owner, request, invitation["invitation_credential"])
        owner.finish_admission(sid, now=1000)
        return owner.sessions[sid], self.send(owner, request, invitation["invitation_credential"])

    def begin(self, *, kind="grant", selection=None, operation="revoke", **kwargs):
        return self.fanout.begin(operation, selection or {key: 1 for key in self.keys.values()}, player=self.player,
                                 catalogue_revision=self.fanout.catalogue_revision, object_type=kind, **kwargs)

    def deliver(self, sid, *, operation="revoke", **kwargs):
        return self.fanout.deliver(operation, self.keys[sid], player=self.player, now=1000, **kwargs)

    def rejected(self, code, operation):
        with self.assertRaises((C.ContractError, G.C.ContractError)) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)

    def effect(self, sid):
        request = F.wire_request("action.request", {"version": "fixture-only", "session_id": sid,
            "id": "a1", "type": "action.request", "sender": self.fixture["agent"], "audience": [self.player],
            "expected_capabilities_revision": 1, "extensions": {},
            "payload": {"action": "find-key", "arguments": {"room": "hall"}, "deadline": 30000}})
        self.send(self.owner, request, self.ready[sid]["control_credential"], sid)
        claim = F.wire_request("action.claim", {"session_id": sid, "action_id": "a1",
            "worker": F.principal("worker-1", "service")}, "claim")
        ticket = self.send(self.owner, claim, "worker-1-fixture", sid)["ticket"]
        child = self.owner.sessions[sid]
        child.execute("step", "worker-1", now=1000, ticket=ticket, step=1)
        return ticket, child.action_model.model.world

    def test_same_grant_has_one_wire_and_one_ack_for_all_selected_sessions(self):
        self.begin()
        result = self.deliver("left")
        self.assertEqual(result["state"], "done")
        items = self.fanout.records["revoke"]["items"]
        self.assertEqual(items[self.keys["left"]]["raw"], items[self.keys["right"]]["raw"])
        before = self.owner.snapshot()
        self.assertEqual(self.deliver("right"), result)
        self.assertEqual(self.owner.snapshot(), before)
        self.assertEqual(self.owner.state["grant"]["revision"], 2)
        self.assertTrue(all(child.state["session"]["state"] == "closed" for child in self.owner.sessions.values()))

    def test_identical_named_grants_on_different_owners_are_not_merged(self):
        other = G.SharedGrantAuthority(self.fixture)
        child, _ = self.join(other, "left")
        self.keys["other"] = self.fanout.register(child, "player-fixture")
        self.assertNotEqual(self.keys["left"], self.keys["other"])
        view = self.begin()
        self.assertEqual(len(view["grant_groups"]), 2)
        self.assertEqual(self.deliver("left")["state"], "partial")
        self.assertEqual(other.state["grant"]["state"], "active")
        self.assertEqual(self.deliver("other")["state"], "done")
        self.assertEqual(other.state["grant"]["revision"], 2)

    def test_shared_revision_disagreement_rejects_before_any_intent_or_effect(self):
        before = self.fanout.snapshot()
        self.rejected("invalid_arguments", lambda: self.begin(selection={self.keys["left"]: 1, self.keys["right"]: 2}))
        self.assertEqual(self.fanout.snapshot(), before)
        self.assertEqual(self.owner.state["grant"]["revision"], 1)

    def test_remote_fault_and_ack_loss_keep_whole_group_unknown_until_original_replay(self):
        for fault, lose_ack in (("before_commit", False), ("after_commit", False), (None, True)):
            with self.subTest(fault=fault, lose_ack=lose_ack):
                self.setUp()
                ticket, world = self.effect("left")
                self.begin()
                raw = self.fanout.records["revoke"]["items"][self.keys["left"]]["raw"]
                result = self.deliver("left", remote_fault=fault, lose_ack=lose_ack)
                self.assertEqual(result["state"], "pending")
                self.assertEqual(set(result["targets"].values()), {"unknown"})
                self.assertEqual(self.owner.state["grant"]["state"], "active" if fault == "before_commit" else "revoked")
                self.fanout = self.fanout.restart_from_mock_ledger()
                self.assertEqual(self.fanout.records["revoke"]["items"][self.keys["right"]]["raw"], raw)
                self.assertEqual(self.deliver("right")["state"], "done")
                before = self.owner.snapshot()
                self.deliver("left")
                self.assertEqual(self.owner.snapshot(), before)
                child = self.owner.sessions["left"]
                self.assertIs(child.action_model.model.world, world)
                self.assertEqual(len(world), 1)
                self.rejected("grant_revoked", lambda: child.execute("step", "worker-1", now=1000, ticket=ticket, step=2))
                query = F.wire_request("action.query", {"session_id": "left", "action_id": "a1"})
                self.assertEqual(self.send(self.owner, query, self.ready["left"]["result_read_handle"], "left")["effect"], "partial")

    def test_group_fault_never_rolls_back_independent_acknowledged_authority(self):
        other = G.SharedGrantAuthority(self.fixture)
        child, _ = self.join(other, "left")
        self.keys["other"] = self.fanout.register(child, "player-fixture")
        self.begin()
        self.deliver("other")
        result = self.deliver("left", remote_fault="before_commit")
        self.assertEqual(result["state"], "partial")
        self.assertEqual(other.state["grant"]["state"], "revoked")
        self.assertEqual(self.owner.state["grant"]["state"], "active")
        self.assertEqual(self.deliver("right")["state"], "done")

    def test_grant_wide_impact_includes_unselected_and_later_sessions_and_invitations(self):
        self.send(self.owner, F.wire_request("session.close", {"session_id": "right", "reason": "left"}), sid="right")
        selection, revision = {self.keys["left"]: 1}, self.fanout.catalogue_revision
        original = self.begin(selection=selection)
        group = next(iter(original["grant_groups"].values()))
        self.assertEqual(group["impact"], "entire_grant")
        child, _ = self.join(self.owner, "late")
        self.fanout.register(child, "player-fixture")
        invitation = self.owner.issue_invitation("unused", now=1000)
        self.assertEqual(self.fanout.begin("revoke", selection, player=self.player,
            catalogue_revision=revision, object_type="grant"), original)
        done = self.deliver("left")
        self.assertEqual(set(done["targets"]), {self.keys["left"]})
        self.assertEqual(child.state["session"]["state"], "closed")
        self.assertEqual(self.owner.state["invitations"][invitation["invitation_id"]]["state"], "revoked")
        self.rejected("grant_revoked", lambda: self.owner.issue_invitation("after", now=1000))

    def test_non_grant_objects_remain_session_local(self):
        for kind in ("session", "result_read", "capability"):
            with self.subTest(kind=kind):
                self.setUp()
                self.begin(kind=kind, **({"capability_ids": {key: "find-key" for key in self.keys.values()}} if kind == "capability" else {}))
                right = deepcopy(self.owner.sessions["right"].state)
                result = self.deliver("left")
                self.assertEqual(result["state"], "partial")
                self.assertNotIn("grant_groups", result)
                self.assertEqual(result["targets"][self.keys["right"]], "pending")
                self.assertEqual(self.owner.sessions["right"].state, right)
                self.assertEqual(self.owner.state["grant"]["revision"], 1)
                self.assertEqual(self.deliver("right")["state"], "done")

    def test_owner_restart_requires_trusted_rebind_and_preserves_original_group_wire(self):
        _, world = self.effect("left")
        self.begin()
        self.deliver("left", lose_ack=True)
        before = self.fanout.snapshot()
        old_owner = self.owner
        self.owner = self.owner.restart_from_mock_ledger()
        intermediate = self.owner
        self.owner = self.owner.restart_from_mock_ledger()
        self.assertEqual(set(self.deliver("right")["targets"].values()), {"unknown"})
        self.assertTrue(old_owner.retired)
        self.assertTrue(intermediate.retired)
        self.rejected("temporarily_unavailable", lambda: intermediate.issue_invitation("stale", now=1000))
        self.fanout.rebind_target(self.keys["right"], self.owner.sessions["right"], "player-fixture", player=self.player)
        self.assertEqual(self.fanout.snapshot(), before)
        self.fanout = self.fanout.restart_from_mock_ledger(snapshot=before)
        self.assertIs(self.fanout.targets[self.keys["right"]]["port"], self.owner.sessions["right"])
        old_owner.sessions["right"].submit = lambda *a, **kw: self.fail("retired port was used")
        self.assertEqual(self.deliver("right")["state"], "done")
        self.assertIs(self.owner.sessions["left"].action_model.model.world, world)
        self.assertEqual(len(world), 1)

    def test_rebind_rejects_foreign_anchor_even_with_same_owner_id_and_binding(self):
        self.begin()
        self.owner = self.owner.restart_from_mock_ledger()
        foreign = G.SharedGrantAuthority(self.fixture)
        foreign.owner_id = self.owner.owner_id
        foreign._checkpoint()  # 模拟可伪造 UUID；它不是可信恢复链。
        child, _ = self.join(foreign, "left")
        before = self.fanout.snapshot()
        self.rejected("permission_denied", lambda: self.fanout.rebind_target(self.keys["left"], child, "player-fixture", player=self.player))
        self.rejected("unauthenticated", lambda: self.fanout.rebind_target(self.keys["left"], self.owner.sessions["left"], "bad", player=self.player))
        self.rejected("permission_denied", lambda: self.fanout.rebind_target(self.keys["left"], self.owner.sessions["right"], "player-fixture", player=self.player))
        self.assertEqual(self.fanout.snapshot(), before)
        self.fanout.rebind_target(self.keys["left"], self.owner.sessions["left"], "player-fixture", player=self.player)
        self.owner.identities["player-fixture"]["expires_at"] = 1000
        self.owner._checkpoint()
        self.assertEqual(set(self.deliver("left")["targets"].values()), {"unknown"})
        self.assertEqual(self.owner.state["grant"]["state"], "active")  # 重绑不恢复已到期的实际 wire 身份。

    def test_snapshot_group_members_identity_wire_and_progress_cannot_be_forged(self):
        self.begin()
        before = self.fanout.snapshot()
        group_id = next(iter(before["records"]["revoke"]["grant_groups"]))
        mutations = [lambda r: r["grant_groups"][group_id]["members"].pop(),
                     lambda r: r["grant_groups"][group_id]["binding"].update(grant_owner_id="foreign"),
                     lambda r: r["items"][self.keys["right"]].update(raw=b"{}"),
                     lambda r: r["items"][self.keys["right"]].update(state="acknowledged")]
        for mutate in mutations:
            forged = deepcopy(before)
            mutate(forged["records"]["revoke"])
            self.rejected("snapshot_mismatch", lambda: self.fanout.restart_from_mock_ledger(snapshot=forged))
        self.deliver("left", lose_ack=True)
        self.rejected("snapshot_mismatch", lambda: self.fanout.restart_from_mock_ledger(snapshot=before))

    def test_group_retirement_waits_for_ack_then_history_survives_port_removal(self):
        for fault in ("before_commit", "after_commit"):
            with self.subTest(fault=fault):
                self.setUp()
                selection, revision = {key: 1 for key in self.keys.values()}, self.fanout.catalogue_revision
                self.begin()
                self.deliver("left", lose_ack=True)
                for key in self.keys.values():
                    self.rejected("not_drained", lambda: self.fanout.retire_target(key, player=self.player, expected_catalogue_revision=revision))
                done = self.deliver("right")
                with self.assertRaises(M.FanoutFault):
                    self.fanout.retire_target(self.keys["left"], player=self.player, expected_catalogue_revision=revision, fault=fault)
                self.fanout = self.fanout.restart_from_mock_ledger()
                self.fanout.retire_target(self.keys["left"], player=self.player, expected_catalogue_revision=revision)
                self.assertIn(self.keys["right"], self.fanout.targets)
                before = self.owner.snapshot()
                self.assertEqual(self.deliver("left"), done)
                self.assertEqual(self.fanout.begin("revoke", selection, player=self.player, catalogue_revision=revision, object_type="grant"), done)
                self.assertEqual(self.owner.snapshot(), before)

    def test_dispatch_checkpoints_all_group_members_before_remote_call_and_rejects_bad_ack(self):
        self.begin()
        child = self.owner.sessions["left"]
        original = child.submit
        def observe(*args, **kwargs):
            snapshot = self.fanout.snapshot()
            self.assertEqual({v["state"] for v in snapshot["records"]["revoke"]["items"].values()}, {"unknown"})
            self.assertEqual(self.fanout._digest(snapshot), self.fanout.checkpoints["ledger"])
            result = C.codec.decode(original(*args, **kwargs))
            result["request_id"] = "wrong-request"
            return C.codec.canonical(result)
        child.submit = observe
        self.assertEqual(set(self.deliver("left")["targets"].values()), {"unknown"})
        self.assertEqual(self.deliver("right")["state"], "done")

    def test_already_revoked_shared_grant_can_ack_current_revision_without_increment(self):
        self.send(self.owner, F.wire_request("permission.revoke", {"object_type": "grant", "object_id": "g1", "expected_revision": 1}))
        self.begin(selection={key: 2 for key in self.keys.values()})
        self.assertEqual(self.deliver("right")["state"], "done")
        self.assertEqual(self.owner.state["grant"]["revision"], 2)

    def test_active_grant_cannot_ack_unchanged_revision_from_uncommitted_reply(self):
        self.begin()
        item = self.fanout.records["revoke"]["items"][self.keys["left"]]
        fake = {"request_id": item["request_id"], "result": {"object_type": "grant", "object_id": "g1",
                "state": "revoked", "revision": 1}}
        self.owner.sessions["left"].submit = lambda *a, **kw: C.codec.canonical(fake)
        self.assertEqual(set(self.deliver("left")["targets"].values()), {"unknown"})
        self.assertEqual(self.owner.state["grant"]["state"], "active")
        self.assertEqual(self.deliver("right")["state"], "done")

    def test_rebind_acquires_distinct_locks_in_stable_order_and_rejects_reverse_recovery(self):
        old = self.owner.sessions["left"]
        self.owner = self.owner.restart_from_mock_ledger()
        new = self.owner.sessions["left"]
        trace = []
        class ObservedLock:
            def __init__(self, lock):
                self.lock = lock
            def __enter__(self):
                self.lock.acquire()
                trace.append(id(self))
            def __exit__(self, *args):
                self.lock.release()
        old.lock, new.lock = ObservedLock(old.lock), ObservedLock(new.lock)
        self.fanout.rebind_target(self.keys["left"], new, "player-fixture", player=self.player)
        self.assertEqual(trace, sorted([id(old.lock), id(new.lock)]))
        trace.clear()
        self.fanout.rebind_target(self.keys["left"], new, "player-fixture", player=self.player)
        self.assertEqual(trace, [id(new.lock)])
        self.rejected("temporarily_unavailable", lambda: self.fanout.rebind_target(self.keys["left"], old, "player-fixture", player=self.player))


if __name__ == "__main__":
    unittest.main()
