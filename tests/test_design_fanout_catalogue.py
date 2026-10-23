"""动态撤权目录、退休屏障与同 authority 多会话的固定组合。"""

from copy import deepcopy
import unittest
from unittest.mock import patch
import test_design_revoke_fanout as T

M = T.M


class FanoutCatalogueTests(unittest.TestCase):
    def setUp(self):
        case = T.RevokeFanoutTests(); case.setUp()
        self.model, self.player, self.ports, self.keys = case.coordinator, case.player, case.ports, case.keys

    def port(self, *, session="s1", grant="g1", epoch="epoch-1", game="key-quest", multi=False):
        fixture = T.T.F.core_fixture(["core.session", "core.events", "actions", "multi-session"] if multi else None)
        old_game = fixture["game"]
        def replace(value):
            if value == old_game:
                return T.T.F.principal(game, "game")
            if isinstance(value, dict):
                return {key: replace(item) for key, item in value.items()}
            if isinstance(value, list):
                return [replace(item) for item in value]
            return value
        fixture = replace(fixture)
        for scope in (fixture["scope"], fixture["session"]["scope"], fixture["grant"]["scope"]):
            scope["instance"]["epoch"] = epoch
        fixture["descriptor"]["instance"]["epoch"] = epoch
        fixture["grant"]["grant_id"] = grant
        fixture["grant"]["scope_digest"] = M.C.codec.digest("scope", fixture["scope"])
        fixture["session"].update(session_id=session, grant_id=grant, instance_epoch=epoch)
        return M.S.SessionHarness(fixture, {})

    def begin(self, operation="revoke", selection=None, revision=None, kind="session"):
        return self.model.begin(operation, selection or {self.keys[0]: 1}, player=self.player,
            catalogue_revision=self.model.catalogue_revision if revision is None else revision, object_type=kind)

    def deliver(self, operation="revoke", key=None, **options):
        return self.model.deliver(operation, key or self.keys[0], player=self.player, now=1000, **options)

    def retire(self, key=None, revision=None, **options):
        return self.model.retire_target(key or self.keys[0], player=self.player,
            expected_catalogue_revision=self.model.catalogue_revision if revision is None else revision, **options)

    def rejected(self, code, function):
        with self.assertRaises(M.C.ContractError) as caught:
            function()
        self.assertEqual(caught.exception.code, code)

    def test_new_target_invalidates_late_selection_but_never_expands_accepted_intent(self):
        selected = dict.fromkeys(self.keys, 1)
        directory = self.model.catalogue(player=self.player)
        original = self.begin(selection=selected, revision=directory["revision"])
        port = self.port(); added = self.model.register(port, "player-fixture")
        self.rejected("generation_conflict", lambda: self.begin("late", selected, directory["revision"]))
        self.assertNotIn("late", self.model.records)
        self.assertEqual(self.begin(selection=selected, revision=directory["revision"]), original)
        self.rejected("id_conflict", lambda: self.begin(selection={**selected, added: 1}, revision=directory["revision"]))
        self.rejected("id_conflict", lambda: self.begin(selection=selected))
        for key in self.keys:
            view = self.deliver(key=key)
        self.assertEqual(view["state"], "done")
        self.assertEqual(set(view["targets"]), set(self.keys))
        self.assertEqual(port.state["session"]["state"], "active")

    def test_unreferenced_retirement_is_not_remote_revocation_and_is_idempotent(self):
        revision = self.model.catalogue_revision
        before = deepcopy(self.ports[0].state)
        receipt = self.retire(revision=revision)
        self.assertEqual(receipt["state"], "retired")
        self.assertEqual(self.ports[0].state, before)
        self.assertNotIn(self.keys[0], self.model.targets)
        self.assertEqual(self.retire(revision=revision), receipt)
        self.assertEqual(self.model.catalogue_revision, revision + 1)
        self.rejected("id_conflict", lambda: self.retire())
        self.rejected("request_gone", lambda: self.model.register(self.ports[0], "player-fixture"))
        self.rejected("request_gone", self.begin)

    def test_every_pending_and_unknown_reference_blocks_retirement(self):
        self.begin("closed"); self.begin("read", kind="result_read")
        self.deliver("closed")
        current = self.model.snapshot()
        self.rejected("not_drained", self.retire)
        self.assertEqual(self.model.snapshot(), current)
        self.deliver("read", remote_fault="after_commit")
        current = self.model.snapshot()
        self.rejected("not_drained", self.retire)
        self.assertEqual(self.model.snapshot(), current)
        before = deepcopy(self.ports[0].state)
        self.assertEqual(self.deliver("read")["state"], "done")
        self.assertEqual(self.ports[0].state, before)
        self.assertEqual(self.retire()["state"], "retired")

    def test_completed_replay_for_each_kind_never_needs_retired_port(self):
        for kind in ("session", "grant", "result_read", "capability"):
            with self.subTest(kind=kind):
                self.setUp(); revision = self.model.catalogue_revision; key = self.keys[0]
                options = {"player": self.player, "catalogue_revision": revision, "object_type": kind,
                           "capability_ids": {key: "find-key"} if kind == "capability" else None}
                self.model.begin("revoke", {key: 1}, **options)
                done = self.deliver(); self.retire()
                with patch.object(self.ports[0], "submit", side_effect=AssertionError("retired port accessed")), \
                     patch.object(self.model, "binding", side_effect=AssertionError("retired binding accessed")):
                    self.assertEqual(self.model.begin("revoke", {key: 1}, **options), done)
                    self.assertEqual(self.deliver(), done)
                    self.assertEqual(self.model.view("revoke", player=self.player), done)
                    self.rejected("id_conflict", lambda: self.model.begin("revoke", {key: 2}, **options))

    def test_new_epoch_same_local_ids_requires_new_key_and_explicit_selection(self):
        old = self.port(game="replacement-game"); key = self.model.register(old, "player-fixture")
        selection = {key: 1}; revision = self.model.catalogue_revision
        self.begin(selection=selection); done = self.deliver(key=key); self.retire(key=key)
        replacement = self.port(game="replacement-game", epoch="epoch-2")
        fresh = self.model.register(replacement, "player-fixture")
        self.assertNotEqual(key, fresh)
        self.assertEqual(self.begin(selection=selection, revision=revision), done)
        self.assertEqual(self.deliver(key=key), done)
        self.assertEqual(replacement.state["session"]["state"], "active")
        self.begin("fresh", {fresh: 1}); self.deliver("fresh", fresh)
        self.assertEqual(replacement.state["session"]["state"], "closed")

    def test_retirement_commit_faults_restore_same_catalogue_and_barrier(self):
        for fault in ("before_commit", "after_commit"):
            with self.subTest(fault=fault):
                self.setUp(); before = self.model.snapshot(); revision = self.model.catalogue_revision
                with self.assertRaises(M.FanoutFault):
                    self.retire(revision=revision, fault=fault)
                if fault == "before_commit":
                    self.assertEqual(self.model.snapshot(), before)
                else:
                    self.rejected("snapshot_mismatch", lambda: self.model.restart_from_mock_ledger(snapshot=before))
                self.model = self.model.restart_from_mock_ledger(snapshot=self.model.snapshot())
                receipt = self.retire(revision=revision)
                self.assertEqual(receipt["catalogue_revision"], revision + 1)
                self.rejected("request_gone", lambda: self.model.register(self.ports[0], "player-fixture"))

    def test_directory_and_tombstone_tampering_cannot_undo_retirement(self):
        before = self.model.snapshot(); self.retire(); current = self.model.snapshot()
        self.rejected("snapshot_mismatch", lambda: self.model.restart_from_mock_ledger(snapshot=before))
        for field, value in (("catalogue_revision", 2), ("retired_targets", {}), ("targets", before["targets"])):
            forged = deepcopy(current); forged[field] = value
            self.rejected("snapshot_mismatch", lambda: self.model.restart_from_mock_ledger(snapshot=forged))
        self.model = self.model.restart_from_mock_ledger(snapshot=current)
        self.rejected("request_gone", self.begin)
        self.assertNotIn(self.keys[0], self.model.catalogue(player=self.player)["targets"])

    def test_catalogue_is_owner_only_detached_and_no_credentials(self):
        current = self.model.catalogue(player=self.player)
        self.assertEqual(current["revision"], 2)
        self.assertEqual(set(current), {"revision", "targets"})
        current["targets"][self.keys[0]]["session_id"] = "changed"
        self.assertEqual(self.model.targets[self.keys[0]]["binding"]["session_id"], "s1")
        self.assertNotIn("credential", repr(current))
        bob = T.T.F.principal("bob", "player")
        self.rejected("permission_denied", lambda: self.model.catalogue(player=bob))
        self.rejected("permission_denied", lambda: self.model.retire_target(self.keys[0], player=bob, expected_catalogue_revision=2))

    def test_catalogue_revision_strictness_idempotent_register_and_exhaustion(self):
        before = self.model.snapshot()
        for value in (True, -1, 1.0, "2", 2**53):
            self.rejected("invalid_arguments", lambda: self.begin(revision=value))
            self.rejected("invalid_arguments", lambda: self.retire(revision=value))
        self.model.register(self.ports[0], "player-fixture")
        self.assertEqual(self.model.snapshot(), before)
        self.rejected("generation_conflict", lambda: self.retire(revision=1))
        self.model.catalogue_revision = M.C.codec.MAX_INTEGER; self.model._checkpoint()
        maximum = self.model.snapshot()
        self.rejected("resource_limit", lambda: self.model.register(self.port(), "player-fixture"))
        self.rejected("resource_limit", self.retire)
        self.model.register(self.ports[0], "player-fixture")
        self.assertEqual(self.model.snapshot(), maximum)

    def test_retirement_frees_active_slot_without_forgetting_identity(self):
        for index in range(14):
            self.model.register(self.port(game="slot-" + str(index)), "player-fixture")
        extra = self.port(game="overflow")
        self.rejected("resource_limit", lambda: self.model.register(extra, "player-fixture"))
        self.retire()
        self.model.register(extra, "player-fixture")
        self.assertEqual(len(self.model.targets), 16)
        self.rejected("request_gone", lambda: self.model.register(self.ports[0], "player-fixture"))

    def test_tombstone_capacity_is_bounded_and_never_silently_evicted(self):
        self.model = M.SessionRevokeFanout(self.player)
        for index in range(64):
            port = self.port(game="retired-" + str(index))
            key = self.model.register(port, "player-fixture")
            self.retire(key=key)
            if index == 0:
                first_key = key
        self.assertEqual(len(self.model.retired_targets), 64)
        key = self.model.register(self.port(game="last-active"), "player-fixture")
        before = self.model.snapshot()
        self.rejected("resource_limit", lambda: self.retire(key=key))
        self.assertEqual(self.model.snapshot(), before)
        self.assertIn(key, self.model.targets)
        self.begin(selection={key: 1}); self.assertEqual(self.deliver(key=key)["state"], "done")
        self.assertEqual(self.retire(first_key, revision=1)["catalogue_revision"], 2)
        self.model = self.model.restart_from_mock_ledger()
        self.assertEqual(len(self.model.retired_targets), 64)

    def test_full_operation_ledger_preserves_existing_control_and_retirement(self):
        for index in range(64):
            self.begin("op-" + str(index))
        self.rejected("resource_limit", lambda: self.begin("overflow"))
        self.assertEqual(self.deliver("op-0")["state"], "done")
        self.assertEqual(self.begin("op-0")["state"], "done")
        self.retire(self.keys[1])
        self.assertEqual(self.begin("op-0", revision=2)["state"], "done")
        self.model = self.model.restart_from_mock_ledger()
        self.assertEqual(len(self.model.records), 64)
        self.assertEqual(self.deliver("op-0")["state"], "done")

    def test_begin_and_retirement_order_never_drops_accepted_work(self):
        revision = self.model.catalogue_revision
        self.begin(); self.rejected("not_drained", self.retire)
        self.setUp(); self.retire()
        self.rejected("generation_conflict", lambda: self.begin(revision=revision))
        self.rejected("request_gone", self.begin)
        self.assertEqual(self.model.records, {})

    def test_unhealthy_and_old_coordinators_cannot_observe_or_modify_catalogue(self):
        old = self.model; self.model = old.restart_from_mock_ledger(intact=False)
        for model in (old, self.model):
            self.rejected("temporarily_unavailable", lambda: model.catalogue(player=self.player))
            self.rejected("temporarily_unavailable", lambda: model.retire_target(self.keys[0], player=self.player,
                                                                                 expected_catalogue_revision=2))

    def test_same_authority_sessions_keep_actions_results_and_retirement_independent(self):
        self.model = M.SessionRevokeFanout(self.player)
        ports = [self.port(session="s" + str(i), grant="g" + str(i), multi=True) for i in (1, 2)]
        keys = [self.model.register(port, "player-fixture") for port in ports]
        self.assertNotEqual(*keys)
        self.assertEqual(ports[0].state["session"]["scope"]["instance"], ports[1].state["session"]["scope"]["instance"])
        case = T.T.SessionHarnessTests(); case.setUp()
        for index, port in enumerate(ports, 1):
            scope = port.state["session"]["scope"]
            self.assertIn("multi-session", scope["features"]); self.assertEqual(scope["limits"]["session_count"], 2)
            request = deepcopy(case.request); request["payload"]["session_id"] = "s" + str(index)
            port.submit(M.C.codec.canonical(request), "agent-fixture", now=1000)
        self.begin("read", {keys[0]: 1}, kind="result_read"); self.deliver("read", keys[0])
        for index, port in enumerate(ports, 1):
            query = M.C.codec.canonical(T.T.F.wire_request("action.query", {"session_id": "s" + str(index), "action_id": "a1"}, "query"))
            if index == 1:
                with self.assertRaises(M.C.ContractError):
                    port.submit(query, "agent-fixture", now=1000)
            else:
                self.assertIn("result", M.C.codec.decode(port.submit(query, "agent-fixture", now=1000)))
        self.model.begin("cap", {keys[1]: 1}, player=self.player, catalogue_revision=2,
                         object_type="capability", capability_ids={keys[1]: "find-key"})
        self.deliver("cap", keys[1])
        self.assertEqual([len(port.state["definitions"]) for port in ports], [1, 0])
        self.assertEqual([port.state["result_access_revision"] for port in ports], [2, 1])
        self.retire(keys[0]); self.begin("close", {keys[1]: 1}); self.deliver("close", keys[1])
        self.assertEqual([port.state["session"]["state"] for port in ports], ["active", "closed"])


if __name__ == "__main__":
    unittest.main()
