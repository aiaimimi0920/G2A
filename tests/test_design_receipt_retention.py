"""关闭会话的有界回执清理；仅内存，不删除文件或世界效果账本。"""

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


U = load("receipt_retention_session", "session_harness.py")
F = load("receipt_retention_fixtures", "fixtures.py")
C = U.C


class ReceiptRetentionTests(unittest.TestCase):
    def setUp(self):
        self.f = F.core_fixture()
        self.h = U.SessionHarness(self.f, {})
        self.end = 1000 + self.f["scope"]["limits"]["receipt_retention_ms"]

    def send(self, operation, payload, credential="agent-fixture", *, now=1000, rid="r1"):
        return C.codec.decode(self.h.submit(C.codec.canonical(F.wire_request(operation, payload, rid)),
                                           credential, now=now))["result"]

    def chat(self, mid="m1", text="保留边界", *, now=1000):
        return self.send("chat.send", {"version": "fixture-only", "session_id": "s1", "id": mid,
            "type": "chat.message", "sender": self.f["agent"], "audience": [self.f["agent"], self.f["player"]],
            "extensions": {}, "payload": {"channel": "private", "text": text, "source_refs": [], "provenance": []}}, now=now)

    def close(self):
        self.send("session.close", {"session_id": "s1", "reason": "left"}, "player-fixture")

    def denied(self, function, code):
        with self.assertRaises(C.ContractError) as caught:
            function()
        self.assertEqual(caught.exception.code, code)

    def test_naive_active_eviction_would_accept_same_message_twice(self):
        self.chat()
        self.h.state["receipts"].clear()  # 故意模拟不安全的内存淘汰，不是清理实现。
        self.assertFalse(self.chat()["duplicate"])
        self.assertEqual(len(self.h.state["events"]), 2)

    def test_active_session_never_compacts_even_with_far_future_clock(self):
        self.chat()
        before = deepcopy(self.h.state)
        self.denied(lambda: self.h.compact_closed_receipts(now=self.end + 1), "invalid_arguments")
        self.assertEqual(self.h.state, before)

    def test_closed_retention_deadline_is_inclusive(self):
        self.chat()
        self.close()
        for now in (1000, self.end):
            self.assertEqual(self.h.compact_closed_receipts(now=now)["removed"], 0)
            self.assertEqual(len(self.h.state["receipts"]), 1)
        self.assertEqual(self.h.compact_closed_receipts(now=self.end + 1)["removed"], 1)
        self.assertEqual(self.h.state["receipts"], {})

    def test_bounded_batches_and_idempotent_retry_keep_terminal_tombstone(self):
        for mid in ("m3", "m1", "m2"):
            self.chat(mid)
        self.close()
        terminal = deepcopy(self.h.state["session"])
        grant = deepcopy(self.h.state["grant"])
        result = self.h.compact_closed_receipts(now=self.end + 1, max_items=2)
        self.assertEqual((result["removed"], result["remaining"]), (2, 1))
        self.assertEqual([key[2] for key in self.h.state["receipts"]], ["m3"])
        self.assertEqual(self.h.compact_closed_receipts(now=self.end + 1, max_items=2)["removed"], 1)
        self.assertEqual(self.h.compact_closed_receipts(now=self.end + 1)["removed"], 0)
        self.assertEqual(self.h.state["session"], terminal)
        self.assertEqual(self.h.state["grant"], grant)

    def test_old_changed_and_new_ids_cannot_write_after_compaction(self):
        self.chat()
        self.close()
        self.h.compact_closed_receipts(now=self.end + 1)
        before = deepcopy(self.h.state)
        for mid, text in (("m1", "保留边界"), ("m1", "改写"), ("new", "新请求")):
            for now in (1000, self.end + 1):
                self.denied(lambda: self.chat(mid, text, now=now), "grant_revoked")
        self.assertEqual(self.h.state, before)

    def test_faults_rollback_both_indexes_and_after_commit_retry_is_noop(self):
        self.chat()
        self.close()
        before = deepcopy(self.h.state)
        with self.assertRaises(U.S.H.InjectedFailure):
            self.h.compact_closed_receipts(now=self.end + 1, fault="before_commit")
        self.assertEqual(self.h.state, before)
        with self.assertRaises(U.S.H.InjectedFailure):
            self.h.compact_closed_receipts(now=self.end + 1, fault="after_commit")
        self.assertEqual(self.h.state["receipts"], {})
        self.assertEqual(self.h.compact_closed_receipts(now=self.end + 1)["removed"], 0)

    def test_action_receipts_wait_for_read_window_and_keep_partial_effect(self):
        request = {"version": "fixture-only", "session_id": "s1", "id": "a1", "type": "action.request",
            "sender": self.f["agent"], "audience": [self.f["player"]], "extensions": {},
            "expected_capabilities_revision": 1, "payload": {"action": "find-key", "arguments": {"room": "hall"}, "deadline": 30000}}
        self.send("action.request", request)
        ticket = self.send("action.claim", {"session_id": "s1", "action_id": "a1", "worker": F.principal("worker-1", "service")},
                           "worker-1-fixture")["ticket"]
        self.h.execute("step", "worker-1", now=1000, ticket=ticket, step=1)
        self.close()
        # 受信模型端口延长结果读取承诺，证明清理同时受两种保留窗口约束。
        self.h.action_model.read_until = self.end + 100
        self.assertEqual(self.h.compact_closed_receipts(now=self.end + 1)["removed"], 0)
        world = deepcopy(self.h.action_model.model.world)
        action = deepcopy(self.h.action_model.model.action)
        events = deepcopy(self.h.state["events"])
        controls = deepcopy(self.h.action_model.control_receipts)
        before = deepcopy(self.h.state)
        with self.assertRaises(U.S.H.InjectedFailure):
            self.h.compact_closed_receipts(now=self.end + 101, fault="before_commit")
        self.assertEqual(self.h.state, before)
        self.assertIn("a1", self.h.action_model.receipts)
        self.assertEqual(self.h.compact_closed_receipts(now=self.end + 101)["removed"], 1)
        self.assertEqual(self.h.action_model.receipts, {})
        self.assertEqual(self.h.action_model.model.world, world)
        self.assertEqual(len(world), 1)
        self.assertEqual(self.h.action_model.model.action, action)
        self.assertEqual(self.h.state["events"], events)
        self.assertEqual(self.h.action_model.control_receipts, controls)
        self.denied(lambda: self.send("action.request", request, now=self.end + 101), "grant_revoked")
        self.denied(lambda: self.send("action.query", {"session_id": "s1", "action_id": "a1"}, now=self.end + 101), "result_expired")

    def test_invalid_clock_batch_and_pending_sync_do_not_erase_receipts(self):
        self.chat()
        self.close()
        before = deepcopy(self.h.state)
        for size in (0, True, 65):
            self.denied(lambda: self.h.compact_closed_receipts(now=self.end + 1, max_items=size), "invalid_arguments")
        self.assertEqual(self.h.state, before)
        self.h.pending_sync = True
        self.denied(lambda: self.h.compact_closed_receipts(now=self.end + 1), "temporarily_unavailable")
        self.assertEqual(self.h.state, before)

    def test_compaction_clock_cannot_move_backwards(self):
        self.chat()
        self.close()
        self.h.compact_closed_receipts(now=self.end)
        before = deepcopy(self.h.state)
        self.denied(lambda: self.h.compact_closed_receipts(now=self.end - 1), "invalid_arguments")
        self.assertEqual(self.h.state, before)

    def test_game_receipt_id_does_not_alias_agent_action_receipt(self):
        self.send("action.request", {"version": "fixture-only", "session_id": "s1", "id": "a1", "type": "action.request",
            "sender": self.f["agent"], "audience": [self.f["player"]], "extensions": {},
            "expected_capabilities_revision": 1, "payload": {"action": "find-key", "arguments": {"room": "hall"}, "deadline": 30000}})
        self.send("context.publish", {"version": "fixture-only", "session_id": "s1", "id": "a1", "type": "game.context",
            "sender": self.f["game"], "audience": [self.f["agent"]], "extensions": {},
            "payload": {"category": "room", "content": "hall", "provenance": []}}, "game-fixture")
        self.close()
        self.h.action_model.read_until = self.end + 100
        self.assertEqual(self.h.compact_closed_receipts(now=self.end + 1)["removed"], 1)
        self.assertIn("a1", self.h.action_model.receipts)
        self.assertEqual(len(self.h.state["receipts"]), 1)
        self.assertEqual(next(iter(self.h.state["receipts"]))[1], U.R.principal_key(self.f["agent"]))


if __name__ == "__main__":
    unittest.main()
