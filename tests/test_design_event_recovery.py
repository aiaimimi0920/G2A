"""核心八类事件与完整可见业务快照；不模拟服务器认证/网络/磁盘。"""

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


E = load("recovery_consumer", "event_consumer.py")
F = load("recovery_fixtures", "fixtures.py")


class EventRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.f = F.core_fixture()
        self.snapshot = {"snapshot_version": "g2a-recovery-1", "session": deepcopy(self.f["session"]),
                         "cursor": {"session_id": "s1", "instance_epoch": "epoch-1", "sequence": 0},
                         "actions": [], "contexts": [], "definitions": [deepcopy(self.f["action"])],
                         "members": [self.f["agent"], self.f["player"]]}
        self.c = E.BusinessConsumer(self.snapshot, self.f["agent"])

    def result(self, revision=1, state="pending", effect="none"):
        return {"session_id": "s1", "request_id": "a1", "state": state, "effect": effect,
                "result_revision": revision, "query_until": 300000}

    def event(self, kind, payload, sequence, sender=None):
        return {"sequence": sequence, "created_at": 1000, "envelope": {
            "version": "fixture-only", "session_id": "s1", "id": "event-" + str(sequence), "type": kind,
            "sender": deepcopy(sender or self.f["game"]), "audience": [self.f["agent"]],
            "payload": deepcopy(payload), "extensions": {}}}

    def context(self, sequence=1, content="hall"):
        return self.event("game.context", {"category": "room", "content": content, "provenance": []}, sequence)

    def page(self, events, end=None):
        cursor = {**self.c.stream.cursor, "sequence": end if end is not None else events[-1]["sequence"]}
        return {"events": events, "next_cursor": cursor, "high_watermark": deepcopy(cursor), "lease_deadline": 100000}

    def apply(self, events, end=None):
        return self.c.apply_page(self.page(events, end), deepcopy(self.c.stream.cursor))

    def snapshot_at(self, sequence):
        snapshot = deepcopy(self.snapshot)
        snapshot["session"]["sequence"] = sequence
        snapshot["cursor"]["sequence"] = sequence
        return snapshot

    def test_all_eight_core_events_update_business_view(self):
        session = deepcopy(self.f["session"])
        session["sequence"] = 1
        events = [self.event("session.ready", {"session": session}, 1),
                  self.event("chat.message", {"channel": "private", "text": "hello", "source_refs": [], "provenance": []}, 2, self.f["player"]),
                  self.context(3), self.event("action.state", {"reason": "accepted", "action": self.result()}, 4),
                  self.event("capability.update", {"revision": 2, "definitions": []}, 5),
                  self.event("membership.update", {"revision": 2, "members": [self.f["agent"]]}, 6)]
        session.update(control_generation=2, capabilities_revision=2, membership_revision=2, sequence=7)
        events.append(self.event("session.control_changed", {"session": session}, 7))
        session.update(state="closed", ready=False, close_reason="revoked", sequence=8)
        events.append(self.event("session.closed", {"session": session}, 8))
        self.apply(events)
        self.assertEqual({event["envelope"]["type"] for event in events}, set(E.C.catalog.EVENT_TYPES))
        self.assertEqual(self.c.view["session"]["state"], "closed")
        self.assertEqual(self.c.view["session"]["control_generation"], 2)
        self.assertEqual(self.c.view["definitions"], [])
        self.assertEqual(self.c.view["members"], [self.f["agent"]])
        self.assertEqual(self.c.view["contexts"]["room"]["payload"]["content"], "hall")
        self.assertEqual(self.c.view["results"].results["a1"]["state"], "pending")
        self.assertNotIn("control_credential", self.c.view["session"])

    def test_invalid_later_event_rolls_back_whole_page_and_cursor(self):
        events = [self.context(1), self.event("action.state", {"reason": "result", "action": self.result()}, 2)]
        with self.assertRaises(E.C.ContractError):
            self.apply(events)
        self.assertEqual(self.c.stream.cursor["sequence"], 0)
        self.assertEqual(self.c.view["contexts"], {})
        self.assertEqual(self.c.stream.events, [])

    def test_server_event_cannot_be_forged_by_agent_or_widen_scope(self):
        bad_definition = deepcopy(self.f["action"])
        bad_definition["maximum_duration_ms"] = 99999
        cases = [self.event("action.state", {"reason": "accepted", "action": self.result()}, 1, self.f["agent"]),
                 self.event("capability.update", {"revision": 2, "definitions": [bad_definition]}, 1),
                 self.event("membership.update", {"revision": 2, "members": [F.principal("outsider", "player")]}, 1)]
        for event in cases:
            with self.assertRaises(E.C.ContractError):
                self.apply([event])
        self.assertEqual(self.c.stream.cursor["sequence"], 0)

    def test_unknown_event_and_required_extension_do_not_advance_cursor(self):
        unknown = self.context()
        unknown["envelope"]["type"] = "unknown.critical"
        extension = self.context()
        extension["envelope"]["extensions"] = {"unknown.required": {"version": "1", "required": True, "value": None}}
        for event in (unknown, extension):
            with self.assertRaises(E.C.ContractError):
                self.apply([event])
        self.assertEqual(self.c.stream.cursor["sequence"], 0)

    def test_team_feature_and_actual_recipient_are_not_inferred_from_event(self):
        team = self.event("chat.message", {"channel": "team", "text": "hello", "source_refs": [], "provenance": []}, 1, self.f["player"])
        team["envelope"]["expected_membership_revision"] = 1
        hidden = self.context()
        hidden["envelope"]["audience"] = [self.f["player"]]
        for event in (team, hidden):
            with self.assertRaises(E.C.ContractError):
                self.apply([event])
        self.assertEqual(self.c.stream.cursor["sequence"], 0)

    def test_bare_session_view_is_not_a_business_recovery_snapshot(self):
        token = self.c.history_gap()
        raw = E.C.codec.canonical({"request_id": "snapshot-1", "result": self.f["session"]})
        with self.assertRaises(E.C.ContractError):
            self.c.recover_reply(raw, "session.snapshot", "snapshot-1", token)
        self.assertTrue(self.c.stream.needs_snapshot)
        self.assertEqual(self.c.stream.cursor["sequence"], 0)

    def test_filtered_gaps_and_duplicate_pages_preserve_business_view(self):
        page = self.page([self.context(4)], end=9)
        original = deepcopy(self.c.stream.cursor)
        self.c.apply_page(page, original)
        self.assertEqual(self.c.apply_page(page, original), "stale")
        self.assertEqual(len(self.c.stream.events), 1)
        self.apply([], end=12)
        self.assertEqual(self.c.view["session"]["sequence"], 12)

    def test_complete_snapshot_replaces_visible_state_not_only_cursor(self):
        self.apply([self.context(1), self.event("action.state", {"reason": "accepted", "action": self.result()}, 2)])
        token = self.c.history_gap()
        snapshot = self.snapshot_at(10)
        snapshot["actions"] = [self.result(3, "succeeded", "committed")]
        snapshot["actions"][0]["known_result"] = {"item": "gold-key"}
        snapshot["contexts"] = [self.context(10, "vault")["envelope"]]
        snapshot["definitions"] = []
        snapshot["session"]["capabilities_revision"] = 2
        snapshot["members"] = [self.f["agent"]]
        snapshot["session"]["membership_revision"] = 2
        raw = E.C.codec.canonical({"request_id": "snapshot-1", "result": snapshot})
        self.c.recover_reply(raw, "session.snapshot", "snapshot-1", token)
        self.assertEqual(self.c.view["results"].results["a1"]["known_result"], {"item": "gold-key"})
        self.assertEqual(self.c.view["contexts"]["room"]["payload"]["content"], "vault")
        self.assertEqual(self.c.view["definitions"], [])
        self.assertEqual(self.c.stream.events, [])
        self.apply([self.context(11, "exit")])
        self.assertEqual(self.c.stream.cursor["sequence"], 11)

    def test_bad_snapshot_is_atomic_and_keeps_recovery_required(self):
        self.apply([self.event("action.state", {"reason": "result", "action": self.result(3, "succeeded", "committed")}, 1)])
        token = self.c.history_gap()
        mutations = (lambda s: s["cursor"].update(instance_epoch="other"),
                     lambda s: s["actions"].extend([self.result(), self.result()]),
                     lambda s: s["actions"].append(self.result(2)),
                     lambda s: s["session"]["scope"].update(expires_at=999999),
                     lambda s: s["contexts"].append(self.event("game.context", {"category": "room", "content": "secret", "provenance": []}, 2, self.f["agent"])["envelope"]))
        for mutate in mutations:
            snapshot = self.snapshot_at(10)
            mutate(snapshot)
            with self.assertRaises(E.C.ContractError):
                self.c.reset_from_verified_snapshot(snapshot, token)
            self.assertTrue(self.c.stream.needs_snapshot)
            self.assertEqual(self.c.stream.cursor["sequence"], 1)
            self.assertEqual(self.c.view["results"].results["a1"]["state"], "succeeded")

    def test_delayed_recovery_and_wrong_reply_id_are_rejected(self):
        old_token = self.c.history_gap()
        token = self.c.history_gap()
        raw = E.C.codec.canonical({"request_id": "snapshot-2", "result": self.snapshot_at(10)})
        for request_id, recovery in (("snapshot-1", token), ("snapshot-2", old_token)):
            with self.assertRaises(E.C.ContractError):
                self.c.recover_reply(raw, "session.snapshot", request_id, recovery)
        self.assertTrue(self.c.stream.needs_snapshot)
        self.c.recover_reply(raw, "session.snapshot", "snapshot-2", token)
        self.assertFalse(self.c.stream.needs_snapshot)

    def test_history_gap_error_requires_consistent_snapshot_cursor_and_unresolved_set(self):
        snapshot = self.snapshot_at(10)
        snapshot["actions"] = [self.result()]
        rule = E.C.catalog.ERRORS["history_gap"]
        error = {k: v for k, v in rule.items() if k != "http_status"}
        error.update(code="history_gap", details={"snapshot": snapshot, "next_cursor": snapshot["cursor"], "unresolved_actions": ["a1"]})
        for field, value in (("next_cursor", {**snapshot["cursor"], "sequence": 20}), ("unresolved_actions", [])):
            bad = deepcopy(error)
            bad["details"][field] = value
            with self.assertRaises(E.C.ContractError):
                E.C.validate_error(bad)
        token = self.c.history_gap()
        self.c.recover_reply(E.C.codec.canonical({"request_id": "poll-1", "error": error}), "session.events", "poll-1", token)
        self.assertEqual(self.c.stream.cursor["sequence"], 10)
        self.assertIn("a1", self.c.view["results"].results)

    def test_recovery_drops_objects_no_longer_in_authorized_snapshot(self):
        self.apply([self.context(1), self.event("action.state", {"reason": "accepted", "action": self.result()}, 2)])
        token = self.c.history_gap()
        self.c.reset_from_verified_snapshot(self.snapshot_at(10), token)
        self.assertEqual(self.c.view["contexts"], {})
        self.assertEqual(self.c.view["results"].results, {})

    def test_closed_session_and_terminal_result_cannot_regress(self):
        session = deepcopy(self.f["session"])
        session.update(state="closed", ready=False, close_reason="revoked", sequence=1)
        self.apply([self.event("session.closed", {"session": session}, 1)])
        session.update(state="active", ready=True, sequence=2)
        session.pop("close_reason")
        with self.assertRaises(E.C.ContractError):
            self.apply([self.event("session.ready", {"session": session}, 2)])
        self.apply([self.event("action.state", {"reason": "result", "action": self.result(2, "succeeded", "committed")}, 2)])
        with self.assertRaises(E.C.ContractError):
            self.apply([self.event("action.state", {"reason": "accepted", "action": self.result(3)}, 3)])
        self.assertEqual(self.c.stream.cursor["sequence"], 2)


if __name__ == "__main__":
    unittest.main()
