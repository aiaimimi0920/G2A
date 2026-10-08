"""动作 bytes 装配与独立消费端状态检查。"""

from copy import deepcopy
import importlib.util
from itertools import permutations
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "docs/protocol"


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = load("pipeline_action", "action_harness.py")
E = load("pipeline_events", "event_consumer.py")
F = load("pipeline_fixture", "fixtures.py")


class ActionPipelineTests(unittest.TestCase):
    def setUp(self):
        self.f = F.core_fixture()
        self.h = A.ActionHarness(self.f)
        self.request = F.wire_request("action.request", {"version": "fixture-only", "session_id": "s1",
                     "id": "a1", "type": "action.request", "sender": self.f["agent"], "audience": [self.f["player"]],
                     "expected_capabilities_revision": 1, "extensions": {},
                     "payload": {"action": "find-key", "arguments": {"room": "hall"}, "deadline": 30000}})

    def send(self, request=None, now=1000):
        return A.C.codec.decode(self.h.submit(A.C.codec.canonical(request or self.request), "agent-fixture", now=now))

    def query(self, now=1000):
        return self.send(F.wire_request("action.query", {"session_id": "s1", "action_id": "a1"}), now)["result"]

    def test_complete_action_bytes_to_effect_query_and_consumer(self):
        self.send()
        reducer = E.ResultReducer("s1")
        reducer.apply(self.query())
        ticket = self.h.execute("claim", "worker-1", now=1000)
        for step in (1, 2):
            self.h.execute("step", "worker-1", ticket=ticket, step=step, now=1001)
            reducer.apply(self.query(now=1001))
        self.assertEqual(self.query()["effect"], "committed")
        self.h.execute("finish", "worker-1", ticket=ticket, now=1002)
        result = self.query(now=1002)
        reducer.apply(result)
        self.assertEqual(result["state"], "succeeded")
        self.assertEqual(len(self.h.model.world), 2)

    def test_retry_and_id_conflict_before_new_effect(self):
        self.send()
        revision = self.h.revision
        self.assertTrue(self.send()["result"]["duplicate"])
        self.assertEqual(self.h.revision, revision)
        self.request["payload"]["payload"]["deadline"] = 25000
        with self.assertRaises(A.C.ContractError) as caught:
            self.send()
        self.assertEqual(caught.exception.code, "id_conflict")

    def test_revocation_stops_next_step_but_preserves_read_and_fact(self):
        self.send()
        ticket = self.h.execute("claim", "worker-1", now=1000)
        self.h.execute("step", "worker-1", ticket=ticket, step=1, now=1001)
        self.h.revoke(now=1002)
        with self.assertRaises(A.C.ContractError):
            self.h.execute("step", "worker-1", ticket=ticket, step=2, now=1003)
        self.h.execute("finish", "worker-1", ticket=ticket, now=1003)
        self.assertEqual(self.query(now=1003)["effect"], "partial")
        self.h.read_revoked = True
        with self.assertRaises(A.C.ContractError):
            self.query(now=1004)

    def test_invalid_action_inputs_do_not_create_action(self):
        for change in (lambda r: r["payload"].update(expected_capabilities_revision=2),
                       lambda r: r["payload"]["payload"].update(deadline=1000),
                       lambda r: r["payload"]["payload"].update(arguments={"room": "vault"}),
                       lambda r: r["payload"].update(sender=self.f["player"])):
            self.setUp()
            change(self.request)
            with self.assertRaises(A.C.ContractError):
                self.send()
            self.assertIsNone(self.h.model.action)
            self.assertEqual(self.h.receipts, {})

    def test_definition_changes_and_deadline_checked_at_effect_boundary(self):
        self.send()
        ticket = self.h.execute("claim", "worker-1", now=1000)
        self.h.definition["effect_class"] = "read_only"
        with self.assertRaises(A.C.ContractError):
            self.h.execute("step", "worker-1", ticket=ticket, step=1, now=1001)
        self.h.definition = deepcopy(self.f["action"])
        with self.assertRaises(A.C.ContractError):
            self.h.execute("step", "worker-1", ticket=ticket, step=1, now=30000)
        self.assertEqual(self.h.model.world, {})

    def test_cancel_bytes_keeps_partial_effect(self):
        self.send()
        ticket = self.h.execute("claim", "worker-1", now=1000)
        self.h.execute("step", "worker-1", ticket=ticket, step=1, now=1001)
        cancel = deepcopy(self.request)
        cancel.update(operation="action.cancel", request_id="cancel-transport")
        cancel["payload"].update(id="cancel-1", type="action.cancel", payload={"request_id": "a1"})
        self.send(cancel)
        self.h.execute("finish", "worker-1", ticket=ticket, now=1002)
        result = self.query(now=1002)
        self.assertEqual((result["state"], result["effect"]), ("cancelled", "partial"))


class ConsumerTests(unittest.TestCase):
    def result(self, revision, state="executing", effect="partial"):
        return {"session_id": "s1", "request_id": "a1", "result_revision": revision,
                "state": state, "effect": effect, "query_until": 300000}

    def test_all_six_result_arrival_orders_converge(self):
        values = [self.result(1, "pending", "none"), self.result(2), self.result(3, "succeeded", "committed")]
        for order in permutations(values):
            reducer = E.ResultReducer("s1")
            for value in order:
                reducer.apply(value)
                self.assertEqual(reducer.apply(value), "duplicate" if value["result_revision"] == reducer.results["a1"]["result_revision"] else "stale")
            self.assertEqual(reducer.results["a1"], values[2])

    def test_equal_revision_conflict_and_terminal_regression(self):
        reducer = E.ResultReducer("s1")
        reducer.apply(self.result(2, "succeeded", "committed"))
        for value in (self.result(2), self.result(3)):
            with self.assertRaises(E.C.ContractError):
                reducer.apply(value)
        self.assertEqual(reducer.results["a1"]["state"], "succeeded")

    def page(self, sequences, end, kind="chat.message"):
        f = F.core_fixture()
        events = [{"sequence": s, "created_at": 1000, "envelope": {"version": "fixture-only", "session_id": "s1",
                   "id": "m" + str(s), "type": kind, "sender": f["agent"], "audience": [f["player"]],
                   "payload": {"channel": "private", "text": "hello", "source_refs": [], "provenance": []}, "extensions": {}}} for s in sequences]
        cursor = {"session_id": "s1", "instance_epoch": "epoch-1", "sequence": end}
        return {"events": events, "next_cursor": cursor, "high_watermark": deepcopy(cursor), "lease_deadline": 10000}

    def test_filtered_sequence_gaps_and_stale_pages_are_not_data_loss(self):
        c = E.EventConsumer("s1", "epoch-1", "fixture-only")
        initial = deepcopy(c.cursor)
        page = self.page([2, 7], 9)
        c.apply_page(page, initial)
        self.assertEqual(c.cursor["sequence"], 9)
        self.assertEqual(c.apply_page(page, initial), "stale")
        self.assertEqual(len(c.events), 2)
        c.apply_page(self.page([], 12), deepcopy(c.cursor))
        self.assertEqual(c.cursor["sequence"], 12)

    def test_bad_page_never_partially_advances(self):
        for page in (self.page([2, 1], 2), self.page([1, 1], 2), self.page([3], 2), self.page([1], 1, "unknown.critical")):
            c = E.EventConsumer("s1", "epoch-1", "fixture-only")
            with self.assertRaises(E.C.ContractError):
                c.apply_page(page, deepcopy(c.cursor))
            self.assertEqual(c.cursor["sequence"], 0)
            self.assertEqual(c.events, [])

    def test_history_gap_requires_verified_same_epoch_snapshot(self):
        c = E.EventConsumer("s1", "epoch-1", "fixture-only")
        c.history_gap()
        with self.assertRaises(E.C.ContractError):
            c.apply_page(self.page([], 2), deepcopy(c.cursor))
        with self.assertRaises(E.C.ContractError):
            c.reset_from_verified_snapshot({**c.cursor, "instance_epoch": "other", "sequence": 3})
        c.reset_from_verified_snapshot({**c.cursor, "sequence": 3})
        c.apply_page(self.page([4], 4), deepcopy(c.cursor))
        self.assertEqual(c.cursor["sequence"], 4)
