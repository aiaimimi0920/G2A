"""两独立 authority 的同名会话撤销；不把部分提交当全局原子事务。"""

from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest
import test_design_session_harness as T

spec = importlib.util.spec_from_file_location("test_fanout", Path(__file__).resolve().parents[1] / "docs/protocol/revoke_fanout.py")
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)


class RevokeFanoutTests(unittest.TestCase):
    def setUp(self):
        self.player = T.F.principal("alice", "player")
        self.coordinator = M.SessionRevokeFanout(self.player)
        self.ports, self.keys = [], []
        for subject in ("game-a", "game-b"):
            fixture = T.F.core_fixture()
            old_game = fixture["game"]
            def replace(value):
                if value == old_game:
                    return T.F.principal(subject, "game")
                if isinstance(value, dict):
                    return {key: replace(item) for key, item in value.items()}
                if isinstance(value, list):
                    return [replace(item) for item in value]
                return value
            fixture = replace(fixture)
            fixture["grant"]["scope_digest"] = M.C.codec.digest("scope", fixture["scope"])
            port = M.S.SessionHarness(fixture, {})
            self.ports.append(port)
            self.keys.append(self.coordinator.register(port, "player-fixture"))
        self.selection = dict.fromkeys(self.keys, 1)

    def begin(self):
        return self.coordinator.begin("revoke-both", self.selection, catalogue_revision=self.coordinator.catalogue_revision, player=self.player)

    def test_independent_coordinators_do_not_reuse_receiver_request_id(self):
        key, port = self.keys[0], self.ports[0]
        self.coordinator.begin("same-id", {key: 1}, catalogue_revision=self.coordinator.catalogue_revision, player=self.player, object_type="result_read")
        self.assertEqual(self.coordinator.deliver("same-id", key, player=self.player, now=1000)["state"], "done")
        other = M.SessionRevokeFanout(self.player)
        self.assertEqual(other.register(port, "player-fixture"), key)
        other.begin("same-id", {key: 1}, catalogue_revision=other.catalogue_revision, player=self.player, object_type="session")
        first = self.coordinator.records["same-id"]["items"][key]
        second = other.records["same-id"]["items"][key]
        self.assertNotEqual(first["request_id"], second["request_id"])
        self.assertEqual(other.deliver("same-id", key, player=self.player, now=1000)["state"], "done")
        self.assertEqual(port.state["session"]["state"], "closed")
        self.assertEqual(port.state["result_access_revision"], 2)

    def deliver(self, index, **kwargs):
        return self.coordinator.deliver("revoke-both", self.keys[index], player=self.player, now=1000, **kwargs)

    def rejected(self, code, function):
        with self.assertRaises(M.C.ContractError) as caught:
            function()
        self.assertEqual(caught.exception.code, code)

    def test_snapshot_recovery_keeps_identity_original_bytes_and_independent_receivers(self):
        for kind in ("session", "grant", "result_read", "capability"):
            for fault in ("before_commit", "after_commit"):
                with self.subTest(kind=kind, fault=fault):
                    self.setUp()
                    self.coordinator.begin("revoke-both", self.selection, catalogue_revision=self.coordinator.catalogue_revision, player=self.player, object_type=kind,
                        capability_ids=dict.fromkeys(self.keys, "find-key") if kind == "capability" else None)
                    self.deliver(0); self.deliver(1, remote_fault=fault)
                    old = self.coordinator; snapshot = old.snapshot()
                    self.coordinator = old.restart_from_mock_ledger(snapshot=snapshot)
                    self.assertEqual(self.coordinator.coordinator_id, snapshot["coordinator_id"])
                    self.assertEqual(self.coordinator.records, snapshot["records"])
                    self.assertIs(self.coordinator.checkpoints, old.checkpoints)
                    for key, port in zip(self.keys, self.ports):
                        self.assertIs(self.coordinator.targets[key]["port"], port)
                    self.assertEqual(self.deliver(1)["state"], "done")
                    states = [deepcopy(port.state) for port in self.ports]
                    self.deliver(0); self.deliver(1)
                    self.assertEqual([port.state for port in self.ports], states)

    def test_pre_registration_and_pre_begin_snapshots_cannot_erase_intent(self):
        empty = M.SessionRevokeFanout(self.player)
        before_register = empty.snapshot()
        empty.register(self.ports[0], "player-fixture")
        self.rejected("snapshot_mismatch", lambda: empty.restart_from_mock_ledger(snapshot=before_register))
        before_begin = self.coordinator.snapshot()
        self.begin()
        self.rejected("snapshot_mismatch", lambda: self.coordinator.restart_from_mock_ledger(snapshot=before_begin))
        self.assertFalse(empty.retired)
        self.assertFalse(self.coordinator.retired)
        self.assertEqual(self.coordinator.view("revoke-both", player=self.player)["state"], "pending")

    def test_dispatch_and_ack_checkpoint_windows_reject_rollback(self):
        from unittest.mock import patch
        self.begin(); before_dispatch = self.coordinator.snapshot()
        port = self.ports[0]; original = port.submit; observed = []
        def submit(*args, **kwargs):
            snapshot = self.coordinator.snapshot()
            self.assertEqual(snapshot["records"]["revoke-both"]["items"][self.keys[0]]["state"], "unknown")
            self.assertEqual(self.coordinator._digest(snapshot), self.coordinator.checkpoints["ledger"])
            observed.append(snapshot)
            return original(*args, **kwargs)
        with patch.object(port, "submit", side_effect=submit):
            self.deliver(0, lose_ack=True)
        self.rejected("snapshot_mismatch", lambda: self.coordinator.restart_from_mock_ledger(snapshot=before_dispatch))
        self.coordinator = self.coordinator.restart_from_mock_ledger(snapshot=observed[0])
        committed = deepcopy(port.state)
        self.deliver(0)
        self.assertEqual(port.state, committed)
        self.rejected("snapshot_mismatch", lambda: self.coordinator.restart_from_mock_ledger(snapshot=observed[0]))
        self.coordinator = self.coordinator.restart_from_mock_ledger(snapshot=self.coordinator.snapshot())
        self.assertEqual(self.deliver(1)["state"], "done")

    def test_checkpoint_covers_owner_target_selection_bytes_and_progress(self):
        self.begin(); current = self.coordinator.snapshot(); key = self.keys[0]
        changes = [(('player', 'subject'), 'bob'),
                   (('targets', key, 'session_id'), 'replacement'),
                   (('records', 'revoke-both', 'selection', key), True),
                   (('records', 'revoke-both', 'object_type'), 'grant'),
                   (('records', 'revoke-both', 'capability_ids'), {}),
                   (('records', 'revoke-both', 'items', key, 'state'), 'acknowledged'),
                   (('records', 'revoke-both', 'items', key, 'request_id'), 'forged'),
                   (('records', 'revoke-both', 'items', key, 'raw'), b'{}'),
                   (('records', 'revoke-both', 'items', key, 'revision'), True)]
        for path, value in changes:
            with self.subTest(path=path):
                forged = deepcopy(current); target = forged
                for part in path[:-1]:
                    target = target[part]
                target[path[-1]] = value
                self.rejected("snapshot_mismatch", lambda: self.coordinator.restart_from_mock_ledger(snapshot=forged))
                self.assertEqual(self.coordinator.snapshot(), current)
        self.assertFalse(self.coordinator.retired)

    def test_foreign_or_mixed_ledger_never_replaces_current_progress(self):
        other = M.SessionRevokeFanout(self.player)
        for port in self.ports:
            other.register(port, "player-fixture")
        self.assertEqual(other.snapshot()["targets"], self.coordinator.snapshot()["targets"])
        self.rejected("snapshot_mismatch", lambda: self.coordinator.restart_from_mock_ledger(snapshot=other.snapshot()))
        self.begin(); before = self.coordinator.snapshot(); self.deliver(0)
        mixed = self.coordinator.snapshot(); mixed["records"] = before["records"]
        self.rejected("snapshot_mismatch", lambda: self.coordinator.restart_from_mock_ledger(snapshot=mixed))
        self.assertFalse(self.coordinator.retired)

    def test_snapshot_cannot_supply_ports_credentials_or_checkpoint(self):
        self.begin(); current = self.coordinator.snapshot()
        for name in ("checkpoints", "ports", "credentials"):
            forged = deepcopy(current); forged[name] = {}
            self.rejected("invalid_snapshot", lambda: self.coordinator.restart_from_mock_ledger(snapshot=forged))
        for snapshot in ({}, [], True):
            self.rejected("invalid_snapshot", lambda: self.coordinator.restart_from_mock_ledger(snapshot=snapshot))
        del self.coordinator.checkpoints["ledger"]
        self.rejected("snapshot_mismatch", lambda: self.coordinator.restart_from_mock_ledger(snapshot=current))
        self.assertFalse(self.coordinator.retired)

    def test_snapshot_and_restored_binding_are_detached_from_caller_copies(self):
        self.begin(); snapshot = self.coordinator.snapshot(); key = self.keys[0]
        self.coordinator = self.coordinator.restart_from_mock_ledger(snapshot=snapshot)
        snapshot["targets"][key]["session_id"] = "caller-mutated"
        snapshot["records"].clear(); snapshot["player"]["subject"] = "bob"
        self.assertEqual(self.coordinator.targets[key]["binding"]["session_id"], "s1")
        self.assertEqual(self.deliver(0)["state"], "partial")
        exported = self.coordinator.snapshot(); exported["records"].clear()
        self.assertIn("revoke-both", self.coordinator.records)

    def test_unhealthy_and_retired_objects_fail_closed_on_all_entrypoints(self):
        self.begin()
        for value in (1, 0, None, "true"):
            self.rejected("invalid_arguments", lambda: self.coordinator.restart_from_mock_ledger(intact=value))
        old = self.coordinator
        self.coordinator = old.restart_from_mock_ledger(intact=False)
        for model in (old, self.coordinator):
            for function in (model.snapshot, model.restart_from_mock_ledger,
                             lambda: model.register(self.ports[0], "player-fixture"),
                             lambda: model.begin("new", self.selection, catalogue_revision=model.catalogue_revision, player=self.player),
                             lambda: model.view("revoke-both", player=self.player),
                             lambda: model.deliver("revoke-both", self.keys[0], player=self.player, now=1000)):
                self.rejected("temporarily_unavailable", function)
        self.assertEqual([port.state["session"]["state"] for port in self.ports], ["active", "active"])

    def test_checkpoint_digest_separates_types_and_rejects_unsupported_values(self):
        digest = self.coordinator._digest
        for left, right in (({"a": 1}, ["map", [["a", 1]]]), (True, 1), (b"a", "61"),
                            (b"a", ["bytes", "61"]), (None, ["null"]), ([], {})):
            self.assertNotEqual(digest(left), digest(right))
        self.assertEqual(digest({"a": 1, "b": 2}), digest({"b": 2, "a": 1}))
        for value in (1.0, float("nan"), set(), (), bytearray(b"a")):
            self.rejected("invalid_snapshot", lambda: digest(value))

    def test_full_instance_binding_disambiguates_same_local_ids(self):
        self.assertNotEqual(*self.keys)
        self.assertEqual([p.state["session"]["session_id"] for p in self.ports], ["s1", "s1"])
        self.assertEqual(self.begin()["state"], "pending")
        self.assertEqual(self.deliver(0)["state"], "partial")
        self.assertEqual([p.state["session"]["state"] for p in self.ports], ["closed", "active"])
        self.assertEqual(self.deliver(1)["state"], "done")
        revisions = [p.state["grant"]["revision"] for p in self.ports]
        self.assertEqual(revisions, [2, 2])
        self.deliver(0); self.deliver(1)
        self.assertEqual([p.state["grant"]["revision"] for p in self.ports], revisions)

    def test_remote_commit_faults_keep_partial_and_retry_original(self):
        for fault in ("before_commit", "after_commit"):
            with self.subTest(fault=fault):
                self.setUp(); self.begin(); self.deliver(0)
                original = self.coordinator.records["revoke-both"]["items"][self.keys[1]]["raw"]
                view = self.deliver(1, remote_fault=fault)
                self.assertEqual(view["state"], "partial")
                self.assertEqual(view["targets"][self.keys[1]], "unknown")
                self.assertEqual(self.ports[1].state["session"]["state"], "active" if fault == "before_commit" else "closed")
                old = self.coordinator
                self.coordinator = old.restart_from_mock_ledger()
                self.assertEqual(self.coordinator.records["revoke-both"]["items"][self.keys[1]]["raw"], original)
                self.assertEqual(self.deliver(1)["state"], "done")
                self.assertEqual([p.state["grant"]["revision"] for p in self.ports], [2, 2])
                with self.assertRaises(M.C.ContractError):
                    old.view("revoke-both", player=self.player)

    def test_lost_coordinator_ack_does_not_repeat_remote_close(self):
        self.begin(); self.deliver(0, lose_ack=True)
        sequence = self.ports[0].state["session"]["sequence"]
        self.coordinator = self.coordinator.restart_from_mock_ledger()
        self.assertEqual(self.deliver(0)["state"], "partial")
        self.assertEqual(self.ports[0].state["session"]["sequence"], sequence)

    def test_revision_conflict_is_not_global_success_or_automatic_cas_rebase(self):
        self.selection[self.keys[1]] = 2
        self.begin(); self.deliver(0)
        self.assertEqual(self.deliver(1)["state"], "partial")
        self.assertEqual(self.ports[1].state["session"]["state"], "active")
        self.selection[self.keys[1]] = 1
        with self.assertRaises(M.C.ContractError):
            self.begin()
        self.assertEqual(self.deliver(1)["state"], "partial")

    def test_owner_scope_and_response_binding_are_checked(self):
        self.begin()
        with self.assertRaises(M.C.ContractError):
            self.coordinator.view("revoke-both", player=T.F.principal("bob", "player"))
        self.ports[1].state["session"]["scope"]["instance"]["epoch"] = "epoch-2"
        with self.assertRaises(M.C.ContractError):
            self.deliver(1)
        self.assertEqual(self.ports[1].state["session"]["state"], "active")
        from unittest.mock import patch
        wrong = {"request_id": "another-request", "result": {"object_type": "session", "object_id": "s1", "revision": 2, "state": "closed"}}
        with patch.object(self.ports[0], "submit", return_value=M.C.codec.canonical(wrong)):
            self.assertEqual(self.deliver(0)["targets"][self.keys[0]], "unknown")

    def test_partial_world_effect_and_result_read_revocation_remain_local(self):
        tickets = []
        for port in self.ports:
            case = T.SessionHarnessTests(); case.setUp()
            request = case.request
            port.submit(M.C.codec.canonical(request), "agent-fixture", now=1000)
            claim = T.F.wire_request("action.claim", {"session_id": "s1", "action_id": "a1",
                                    "worker": T.F.principal("worker-1", "service")}, "claim")
            ticket = M.C.codec.decode(port.submit(M.C.codec.canonical(claim), "worker-1-fixture", now=1000))["result"]["ticket"]
            tickets.append(ticket)
            port.execute("step", "worker-1", now=1000, ticket=ticket, step=1)
        self.begin(); self.deliver(0)
        with self.assertRaises(M.C.ContractError):
            self.ports[0].execute("step", "worker-1", now=1000, ticket=tickets[0], step=2)
        self.ports[1].execute("step", "worker-1", now=1000, ticket=tickets[1], step=2)
        self.assertEqual([len(p.action_model.model.world) for p in self.ports], [1, 2])
        self.deliver(1)
        for port, ticket in zip(self.ports, tickets):
            port.execute("finish", "worker-1", now=1000, ticket=ticket)
        query = M.C.codec.canonical(T.F.wire_request("action.query", {"session_id": "s1", "action_id": "a1"}, "query"))
        self.assertIn("result", M.C.codec.decode(self.ports[0].submit(query, "agent-fixture", now=1000)))
        revoke = T.F.wire_request("permission.revoke", {"object_type": "result_read", "object_id": "s1", "expected_revision": 1}, "read-revoke")
        self.ports[0].submit(M.C.codec.canonical(revoke), "player-fixture", now=1000)
        with self.assertRaises(M.C.ContractError):
            self.ports[0].submit(query, "agent-fixture", now=1000)
        self.assertIn("result", M.C.codec.decode(self.ports[1].submit(query, "agent-fixture", now=1000)))

    def test_trusted_registration_owner_and_strict_selection(self):
        self.assertEqual(self.coordinator.register(self.ports[0], "player-fixture"), self.keys[0])
        with self.assertRaises(M.C.ContractError):
            self.coordinator.register(self.ports[0], "game-fixture")
        for selection in ({}, {self.keys[0]: True}, {self.keys[0]: 0}, {"unregistered": 1}):
            with self.assertRaises(M.C.ContractError):
                self.coordinator.begin("bad-selection", selection, catalogue_revision=self.coordinator.catalogue_revision, player=self.player)
        with self.assertRaises(M.C.ContractError):
            self.coordinator.begin("wrong-owner", self.selection, catalogue_revision=self.coordinator.catalogue_revision, player=T.F.principal("bob", "player"))
        self.assertEqual(self.coordinator.records, {})

    def test_target_rotation_cannot_enter_between_binding_check_and_receive(self):
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch
        self.begin()
        port = self.ports[0]
        original_binding = self.coordinator.binding
        entered = []
        def rotate_if_unlocked():
            if not port.lock.acquire(blocking=False):
                return False
            try:
                scope = port.state["session"]["scope"]
                scope["instance"]["epoch"] = "replacement-epoch"
                port.state["session"]["instance_epoch"] = "replacement-epoch"
                port.state["grant"]["scope"] = deepcopy(scope)
                port.state["grant"]["scope_digest"] = M.C.codec.digest("scope", scope)
                return True
            finally:
                port.lock.release()
        with ThreadPoolExecutor(max_workers=1) as pool:
            def observed_binding(target):
                value = original_binding(target)
                if target is port:
                    entered.append(pool.submit(rotate_if_unlocked).result(timeout=5))
                return value
            with patch.object(self.coordinator, "binding", side_effect=observed_binding):
                self.deliver(0)
        self.assertEqual(entered, [False], "target rotated after binding check but before accepting revoke")
        self.assertEqual(port.state["session"]["instance_epoch"], "epoch-1")
        self.assertEqual(port.state["session"]["state"], "closed")

    def test_receiver_lock_is_released_after_rejection_or_commit_fault(self):
        from concurrent.futures import ThreadPoolExecutor
        for fault in (None, "before_commit", "after_commit", "binding_changed"):
            with self.subTest(fault=fault):
                self.setUp(); self.begin(); port = self.ports[0]
                if fault == "binding_changed":
                    port.state["session"]["scope"]["instance"]["epoch"] = "new-epoch"
                    with self.assertRaises(M.C.ContractError):
                        self.deliver(0)
                else:
                    self.deliver(0, remote_fault=fault)
                def available():
                    acquired = port.lock.acquire(blocking=False)
                    if acquired:
                        port.lock.release()
                    return acquired
                with ThreadPoolExecutor(max_workers=1) as pool:
                    self.assertTrue(pool.submit(available).result(timeout=5))

    def test_grant_fanout_commit_faults_recover_without_revision_rebase(self):
        for fault in ("before_commit", "after_commit"):
            with self.subTest(fault=fault):
                self.setUp()
                self.coordinator.begin("revoke-both", self.selection, catalogue_revision=self.coordinator.catalogue_revision, player=self.player, object_type="grant")
                self.assertEqual(self.deliver(0)["state"], "partial")
                view = self.deliver(1, remote_fault=fault)
                self.assertEqual(view["object_type"], "grant")
                self.assertEqual(view["state"], "partial")
                self.assertEqual(self.ports[1].state["grant"]["state"], "active" if fault == "before_commit" else "revoked")
                self.coordinator = self.coordinator.restart_from_mock_ledger()
                self.assertEqual(self.deliver(1)["state"], "done")
                self.assertEqual([p.state["grant"]["revision"] for p in self.ports], [2, 2])
                self.assertEqual([p.state["session"]["state"] for p in self.ports], ["closed", "closed"])

    def test_result_read_fanout_does_not_close_sessions_or_stop_world_steps(self):
        tickets = []
        case = T.SessionHarnessTests(); case.setUp()
        for port in self.ports:
            port.submit(M.C.codec.canonical(case.request), "agent-fixture", now=1000)
            claim = T.F.wire_request("action.claim", {"session_id": "s1", "action_id": "a1",
                                    "worker": T.F.principal("worker-1", "service")}, "claim")
            ticket = M.C.codec.decode(port.submit(M.C.codec.canonical(claim), "worker-1-fixture", now=1000))["result"]["ticket"]
            tickets.append(ticket)
            port.execute("step", "worker-1", now=1000, ticket=ticket, step=1)
        self.coordinator.begin("revoke-both", self.selection, catalogue_revision=self.coordinator.catalogue_revision, player=self.player, object_type="result_read")
        self.assertEqual(self.deliver(0)["state"], "partial")
        query = M.C.codec.canonical(T.F.wire_request("action.query", {"session_id": "s1", "action_id": "a1"}, "query"))
        with self.assertRaises(M.C.ContractError):
            self.ports[0].submit(query, "agent-fixture", now=1000)
        self.assertIn("result", M.C.codec.decode(self.ports[1].submit(query, "agent-fixture", now=1000)))
        self.assertEqual(self.deliver(1, lose_ack=True)["state"], "partial")
        self.coordinator = self.coordinator.restart_from_mock_ledger()
        self.assertEqual(self.deliver(1)["state"], "done")
        for port, ticket in zip(self.ports, tickets):
            port.execute("step", "worker-1", now=1000, ticket=ticket, step=2)
            self.assertEqual(len(port.action_model.model.world), 2)
            self.assertEqual(port.state["session"]["state"], "active")
            self.assertEqual(port.state["grant"]["state"], "active")
            self.assertEqual(port.state["grant"]["revision"], 1)
            self.assertEqual(port.state["result_access_revision"], 2)
            with self.assertRaises(M.C.ContractError):
                port.submit(query, "agent-fixture", now=1000)

    def test_object_type_is_frozen_and_unknown_types_never_downgrade(self):
        self.begin()
        for kind in ("grant", "result_read"):
            with self.assertRaises(M.C.ContractError) as caught:
                self.coordinator.begin("revoke-both", self.selection, catalogue_revision=self.coordinator.catalogue_revision, player=self.player, object_type=kind)
            self.assertEqual(caught.exception.code, "id_conflict")
        for kind in (None, True, [], "invitation", "unknown"):
            with self.assertRaises(M.C.ContractError) as caught:
                self.coordinator.begin("unsupported", self.selection, catalogue_revision=self.coordinator.catalogue_revision, player=self.player, object_type=kind)
            self.assertEqual(caught.exception.code, "invalid_arguments")
        self.assertNotIn("unsupported", self.coordinator.records)

    def test_replaced_grant_with_same_scope_is_not_original_target(self):
        self.coordinator.begin("revoke-both", self.selection, catalogue_revision=self.coordinator.catalogue_revision, player=self.player, object_type="grant")
        self.ports[0].state["grant"]["grant_id"] = "replacement-grant"
        self.ports[0].state["session"]["grant_id"] = "replacement-grant"
        with self.assertRaises(M.C.ContractError):
            self.deliver(0)
        self.assertEqual(self.ports[0].state["grant"]["state"], "active")

    def test_matching_id_with_wrong_revocation_kind_or_state_is_not_ack(self):
        from unittest.mock import patch
        self.coordinator.begin("revoke-both", self.selection, catalogue_revision=self.coordinator.catalogue_revision, player=self.player, object_type="result_read")
        item = self.coordinator.records["revoke-both"]["items"][self.keys[0]]
        for kind, state, oid in (("session", "closed", "s1"), ("result_read", "closed", "s1"),
                                 ("result_read", "revoked", "another-session")):
            reply = {"request_id": item["request_id"], "result": {"object_type": kind, "object_id": oid,
                     "state": state, "revision": 2}}
            with patch.object(self.ports[0], "submit", return_value=M.C.codec.canonical(reply)):
                self.assertEqual(self.deliver(0)["targets"][self.keys[0]], "unknown")
        self.assertEqual(self.ports[0].state["result_access_revision"], 1)

    def test_capability_fanout_stops_only_selected_authority_steps_and_keeps_read_right(self):
        tickets = []
        case = T.SessionHarnessTests(); case.setUp()
        for port in self.ports:
            port.submit(M.C.codec.canonical(case.request), "agent-fixture", now=1000)
            claim = T.F.wire_request("action.claim", {"session_id": "s1", "action_id": "a1",
                                    "worker": T.F.principal("worker-1", "service")}, "claim")
            ticket = M.C.codec.decode(port.submit(M.C.codec.canonical(claim), "worker-1-fixture", now=1000))["result"]["ticket"]
            tickets.append(ticket)
            port.execute("step", "worker-1", now=1000, ticket=ticket, step=1)
        ids = dict.fromkeys(self.keys, "find-key")
        self.coordinator.begin("revoke-both", self.selection, catalogue_revision=self.coordinator.catalogue_revision, player=self.player, object_type="capability", capability_ids=ids)
        self.assertEqual(self.deliver(0)["state"], "partial")
        with self.assertRaises(M.C.ContractError):
            self.ports[0].execute("step", "worker-1", now=1000, ticket=tickets[0], step=2)
        self.ports[1].execute("step", "worker-1", now=1000, ticket=tickets[1], step=2)
        self.assertEqual(self.deliver(1)["state"], "done")
        query = M.C.codec.canonical(T.F.wire_request("action.query", {"session_id": "s1", "action_id": "a1"}, "query"))
        for port, ticket in zip(self.ports, tickets):
            port.execute("finish", "worker-1", now=1000, ticket=ticket)
            self.assertIn("result", M.C.codec.decode(port.submit(query, "agent-fixture", now=1000)))
            self.assertEqual(port.state["session"]["state"], "active")
            self.assertEqual(port.state["grant"]["state"], "active")
            self.assertEqual(port.state["result_access_revision"], 1)
            self.assertEqual(port.state["session"]["capabilities_revision"], 2)
        self.assertEqual([len(p.action_model.model.world) for p in self.ports], [1, 2])

    def test_capability_commit_loss_and_replacement_cannot_restore_revoked_definition(self):
        original = deepcopy(self.ports[0].state["definitions"])
        self.coordinator.begin("revoke-both", self.selection, catalogue_revision=self.coordinator.catalogue_revision, player=self.player, object_type="capability",
                               capability_ids=dict.fromkeys(self.keys, "find-key"))
        self.assertEqual(self.deliver(0, remote_fault="after_commit")["state"], "pending")
        self.coordinator = self.coordinator.restart_from_mock_ledger()
        self.assertEqual(self.deliver(0)["state"], "partial")
        port = self.ports[0]
        self.assertEqual(port.state["session"]["capabilities_revision"], 2)
        update = T.F.wire_request("capability.replace", {"instance": port.state["session"]["scope"]["instance"],
                                  "expected_revision": 2, "definitions": original}, "replace-after-revoke")
        port.submit(M.C.codec.canonical(update), "game-fixture", now=1000)
        self.assertEqual(port.state["definitions"], [])
        self.assertEqual(self.ports[1].state["definitions"], original)

    def test_capability_requires_explicit_complete_approved_selection(self):
        for ids in (None, {}, {self.keys[0]: "find-key"},
                    {**dict.fromkeys(self.keys, "find-key"), "extra": "find-key"},
                    dict.fromkeys(self.keys, True), dict.fromkeys(self.keys, "not-approved")):
            with self.subTest(ids=ids):
                with self.assertRaises(M.C.ContractError):
                    self.coordinator.begin("bad", self.selection, catalogue_revision=self.coordinator.catalogue_revision, player=self.player,
                                           object_type="capability", capability_ids=ids)
                self.assertEqual(self.coordinator.records, {})
        with self.assertRaises(M.C.ContractError):
            self.coordinator.begin("bad", self.selection, catalogue_revision=self.coordinator.catalogue_revision, player=self.player,
                                   object_type="session", capability_ids=dict.fromkeys(self.keys, "find-key"))

    def test_capability_selection_is_copied_and_does_not_expand_after_begin(self):
        ids = dict.fromkeys(self.keys, "find-key")
        self.coordinator.begin("revoke-both", self.selection, catalogue_revision=self.coordinator.catalogue_revision, player=self.player,
                               object_type="capability", capability_ids=ids)
        ids[self.keys[0]] = "changed-by-caller"
        stored = self.coordinator.records["revoke-both"]
        self.assertEqual(stored["capability_ids"][self.keys[0]], "find-key")
        self.assertEqual(M.C.codec.decode(stored["items"][self.keys[0]]["raw"])["payload"]["object_id"], "find-key")
        self.assertEqual(self.deliver(0)["state"], "partial")

    def test_distinct_local_action_ids_are_explicitly_bound_per_target(self):
        fixture = T.F.core_fixture()
        fixture["action"]["id"] = "open-door"
        definition = fixture["action"]
        fixture["descriptor"]["actions"] = [deepcopy(definition)]
        fixture["requested"]["action_ids"] = ["open-door"]
        for scope in (fixture["scope"], fixture["grant"]["scope"], fixture["session"]["scope"]):
            scope["action_ids"] = ["open-door"]
            scope["approved_action_digests"] = {"open-door": M.C.codec.digest("action-definition", definition)}
        fixture["grant"]["scope_digest"] = M.C.codec.digest("scope", fixture["scope"])
        port = M.S.SessionHarness(fixture, {})
        key = self.coordinator.register(port, "player-fixture")
        selection = {self.keys[0]: 1, key: 1}
        self.coordinator.begin("different-actions", selection, catalogue_revision=self.coordinator.catalogue_revision, player=self.player, object_type="capability",
                               capability_ids={self.keys[0]: "find-key", key: "open-door"})
        for target in selection:
            view = self.coordinator.deliver("different-actions", target, player=self.player, now=1000)
        self.assertEqual(view["state"], "done")
        self.assertEqual(self.ports[0].state["revoked_capabilities"], {"find-key"})
        self.assertEqual(port.state["revoked_capabilities"], {"open-door"})
        self.assertEqual(self.ports[1].state["revoked_capabilities"], set())


if __name__ == "__main__":
    unittest.main()
