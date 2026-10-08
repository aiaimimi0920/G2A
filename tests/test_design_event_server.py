"""事件服务字节链、权限重验、事务故障与有界真实线程排序。"""

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


S = load("server_test", "event_server.py")
F = load("server_fixture", "fixtures.py")
C = S.C


class EventServerTests(unittest.TestCase):
    def setUp(self):
        self.f = F.core_fixture()
        self.source = {"source_kind": "shared_experience", "source_id": "room-1",
                       "source_principals": [self.f["game"]],
                       "original_disclosure_scope": [self.f[name] for name in ("player", "agent", "game")]}
        record = {"instance": self.f["scope"]["instance"], "session_id": "s1", "source": self.source,
                  "controller": self.f["game"], "evidence_ref": "room-evidence", "revision": 1,
                  "state": "active", "publishers": [self.f["game"], self.f["agent"]],
                  "allowed_readers": self.source["original_disclosure_scope"], "expires_at": 90000}
        self.h = S.EventServer(self.f, {"room-1": record})
        self.origin_members = deepcopy(self.h.members)

    def send(self, request, credential="agent-fixture", now=1000, fault=None):
        return C.codec.decode(self.h.submit(C.codec.canonical(request), credential, now=now, fault=fault))

    def context(self, name="c1", content="hall", audience=None, sourced=False):
        return F.wire_request("context.publish", {"version": "fixture-only", "session_id": "s1", "id": name,
            "type": "game.context", "sender": self.f["game"], "audience": audience or [self.f["agent"]],
            "payload": {"category": "room", "content": content, "provenance": [self.source] if sourced else []}, "extensions": {}})

    def poll_request(self, sequence=0, request_id="poll-1", size=64):
        return F.wire_request("session.events", {"session_id": "s1", "page_size": size,
            "cursor": {"session_id": "s1", "instance_epoch": "epoch-1", "sequence": sequence}}, request_id)

    def snapshot(self, now=1000):
        return self.send(F.wire_request("session.snapshot", {"session_id": "s1"}), now=now)["result"]

    def result(self, revision=1, state="pending", effect="none", query_until=200000):
        return {"session_id": "s1", "request_id": "a1", "state": state, "effect": effect,
                "result_revision": revision, "query_until": query_until}

    def record_action(self, result, *, now, fault=None):
        return self.h.record_verified_action_result(result, origin_members=self.origin_members, now=now, fault=fault)

    def test_publish_poll_snapshot_and_business_consumer_same_cut(self):
        consumer = S.E.BusinessConsumer(self.snapshot(), self.f["agent"])
        self.send(self.context(sourced=True), "game-fixture")
        self.record_action(self.result(), now=1000)
        page = self.send(self.poll_request())["result"]
        consumer.apply_page(page, deepcopy(consumer.stream.cursor))
        snapshot = self.snapshot()
        self.assertEqual(snapshot["cursor"]["sequence"], snapshot["session"]["sequence"])
        self.assertEqual(snapshot["cursor"]["sequence"], 2)
        self.assertEqual(snapshot["contexts"][0], consumer.view["contexts"]["room"])
        self.assertEqual(snapshot["actions"][0], consumer.view["results"].results["a1"])

    def test_context_and_chat_rollback_outbox_receipt_and_current_state(self):
        context = self.context(sourced=True)
        for fault in ("before_commit",):
            before = deepcopy(self.h.state)
            with self.assertRaises(S.H.InjectedFailure):
                self.send(context, "game-fixture", fault=fault)
            self.assertEqual(self.h.state, before)
        with self.assertRaises(S.H.InjectedFailure):
            self.send(context, "game-fixture", fault="after_commit")
        self.assertTrue(self.send(context, "game-fixture")["result"]["duplicate"])
        self.assertEqual(len(self.h.state["events"]), 1)
        chat = F.wire_request("chat.send", {"version": "fixture-only", "session_id": "s1", "id": "m1",
            "type": "chat.message", "sender": self.f["agent"], "audience": [self.f["player"]],
            "payload": {"channel": "private", "text": "hello", "source_refs": [], "provenance": []}, "extensions": {}})
        before = deepcopy(self.h.state)
        with self.assertRaises(S.H.InjectedFailure):
            self.send(chat, fault="before_commit")
        self.assertEqual(self.h.state, before)
        self.send(chat)
        self.assertEqual(len(self.h.state["events"]), 2)

    def test_context_source_authority_and_role_are_not_self_declared(self):
        request = self.context(sourced=True)
        for credential in ("agent-fixture", "unknown-fixture"):
            with self.assertRaises(C.ContractError):
                self.send(request, credential)
        self.h.state["records"]["room-1"]["publishers"] = [self.f["agent"]]
        with self.assertRaises(C.ContractError):
            self.send(request, "game-fixture")
        self.assertEqual(self.h.state["session"]["sequence"], 0)
        self.assertEqual(self.h.state["contexts"], {})

    def test_only_fresh_successful_poll_renews_lease(self):
        lease = self.h.state["session"]["lease_deadline"]
        self.send(self.context(), "game-fixture", now=1000)
        self.snapshot(now=1000)
        self.assertEqual(self.h.state["session"]["lease_deadline"], lease)
        request = self.poll_request()
        first = self.send(request, now=1000)["result"]
        self.assertEqual(first["lease_deadline"], 121000)
        self.send(self.context("c2", "vault"), "game-fixture", now=2000)
        second = self.send(request, now=2000)["result"]
        self.assertEqual(second["next_cursor"], first["next_cursor"])
        self.assertEqual(second["high_watermark"], first["high_watermark"])
        self.assertEqual(self.h.state["session"]["lease_deadline"], 121000)
        self.assertEqual(len(second["events"]), 1)

    def test_poll_encoding_failure_rolls_back_nonce_and_lease(self):
        self.send(self.context(), "game-fixture")
        before = deepcopy(self.h.state)
        with patch.object(C, "validate_reply", side_effect=C.ContractError("invalid_message")):
            with self.assertRaises(C.ContractError):
                self.send(self.poll_request())
        self.assertEqual(self.h.state, before)
        with self.assertRaises(S.H.InjectedFailure):
            self.send(self.poll_request(), fault="after_commit")
        deadline = self.h.state["session"]["lease_deadline"]
        self.send(self.poll_request(), now=2000)
        self.assertEqual(self.h.state["session"]["lease_deadline"], deadline)

    def test_duplicate_poll_rechecks_source_revision_and_expiry(self):
        for change in ("revoke", "revision", "expiry"):
            self.setUp()
            self.send(self.context(sourced=True), "game-fixture")
            request = self.poll_request()
            self.assertEqual(len(self.send(request)["result"]["events"]), 1)
            if change == "revoke":
                self.h.revoke_source("room-1")
            elif change == "revision":
                self.h.state["records"]["room-1"]["revision"] += 1
            else:
                self.h.state["records"]["room-1"]["expires_at"] = 1001
            page = self.send(request, now=1001)["result"]
            self.assertEqual(page["events"], [])
            self.assertEqual(page["next_cursor"]["sequence"], 1)
            self.assertEqual(self.snapshot(now=1001)["contexts"], [])

    def test_rejoined_member_cannot_read_old_event_or_current_context(self):
        self.send(self.context(), "game-fixture")
        request = self.poll_request()
        self.send(request)
        self.h.replace_member_generation(self.f["agent"], 2)
        self.assertEqual(self.send(request)["result"]["events"], [])
        self.assertEqual(self.snapshot()["contexts"], [])
        self.send(self.context("c2", "new-room"), "game-fixture")
        self.assertEqual(len(self.send(self.poll_request(1, "poll-2"))["result"]["events"]), 1)

    def test_scan_budget_counts_invisible_events_and_does_not_skip_visible(self):
        self.h.scan_budget = 2
        for i in (1, 2):
            self.send(self.context("c" + str(i), audience=[self.f["player"]]), "game-fixture")
        self.send(self.context("c3"), "game-fixture")
        first = self.send(self.poll_request(size=1))["result"]
        self.assertEqual(first["events"], [])
        self.assertEqual(first["next_cursor"]["sequence"], 2)
        second = self.send(self.poll_request(2, "poll-2", size=1))["result"]
        self.assertEqual([event["sequence"] for event in second["events"]], [3])

    def test_full_outbox_rejects_new_write_but_preserves_retry_and_snapshot(self):
        for number in range(64):
            self.send(self.context("c" + str(number)), "game-fixture")
        before = deepcopy(self.h.state)
        with self.assertRaises(C.ContractError) as caught:
            self.send(self.context("overflow"), "game-fixture")
        self.assertEqual(caught.exception.code, "resource_limit")
        self.assertEqual(self.h.state, before)
        self.assertTrue(self.send(self.context("c0"), "game-fixture")["result"]["duplicate"])
        self.assertEqual(self.snapshot()["cursor"]["sequence"], 64)
        self.h.compact_through(64)
        self.send(self.context("after-gc"), "game-fixture")
        self.assertTrue(self.send(self.context("c0"), "game-fixture")["result"]["duplicate"])
        self.assertEqual(self.h.state["session"]["sequence"], 65)
        self.assertEqual(len(self.h.state["events"]), 1)

    def test_history_gap_contains_filtered_state_and_does_not_renew(self):
        consumer = S.E.BusinessConsumer(self.snapshot(), self.f["agent"])
        self.send(self.context(sourced=True), "game-fixture")
        self.record_action(self.result(), now=1000)
        self.h.compact_through(2)
        self.h.revoke_source("room-1")
        lease = self.h.state["session"]["lease_deadline"]
        reply = self.send(self.poll_request())
        self.assertEqual(reply["error"]["code"], "history_gap")
        details = reply["error"]["details"]
        self.assertEqual(details["snapshot"]["contexts"], [])
        self.assertEqual(details["next_cursor"]["sequence"], 2)
        self.assertEqual(details["unresolved_actions"], ["a1"])
        self.assertEqual(self.h.state["session"]["lease_deadline"], lease)
        token = consumer.history_gap()
        consumer.recover_reply(C.codec.canonical(reply), "session.events", "poll-1", token)
        self.assertIn("a1", consumer.view["results"].results)

    def test_compaction_of_original_poll_never_replays_cached_plaintext(self):
        self.send(self.context(sourced=True), "game-fixture")
        request = self.poll_request()
        self.send(request)
        self.h.compact_through(1)
        self.h.revoke_source("room-1")
        reply = self.send(request)
        self.assertEqual(reply["error"]["details"]["snapshot"]["contexts"], [])
        self.assertNotIn("events", reply["error"]["details"])

    def test_action_state_outbox_atomic_and_read_revocation_is_current(self):
        result = self.result()
        before = deepcopy(self.h.state)
        with self.assertRaises(S.H.InjectedFailure):
            self.record_action(result, now=1000, fault="before_commit")
        self.assertEqual(self.h.state, before)
        with self.assertRaises(S.H.InjectedFailure):
            self.record_action(result, now=1000, fault="after_commit")
        event = self.record_action(result, now=1000)
        self.assertEqual(event["sequence"], 1)
        self.assertEqual(len(self.h.state["events"]), 1)
        request = self.poll_request()
        self.assertEqual(len(self.send(request)["result"]["events"]), 1)
        self.h.revoke_result_read(self.f["agent"], "a1")
        self.assertEqual(self.send(request)["result"]["events"], [])
        self.assertEqual(self.snapshot()["actions"], [])

    def test_action_origin_membership_and_query_expiry_apply_to_new_notifications(self):
        self.record_action(self.result(query_until=2000), now=1000)
        self.h.replace_member_generation(self.f["agent"], 2)
        self.record_action(self.result(2, "succeeded", "committed", query_until=2000), now=1001)
        self.assertEqual(self.send(self.poll_request())["result"]["events"], [])
        self.assertEqual(self.snapshot()["actions"], [])
        self.setUp()
        self.record_action(self.result(query_until=2000), now=1000)
        self.assertEqual(self.send(self.poll_request(), now=2001)["result"]["events"], [])

    def test_delayed_first_action_notice_cannot_refreeze_rejoined_members(self):
        self.h.replace_member_generation(self.f["agent"], 2)
        self.record_action(self.result(2, "succeeded", "committed"), now=1001)
        self.assertEqual(self.send(self.poll_request())["result"]["events"], [])
        with self.assertRaises(C.ContractError):
            self.h.record_verified_action_result(self.result(3, "succeeded", "committed"),
                                                 origin_members=deepcopy(self.h.members), now=1002)
        self.assertEqual(self.h.state["session"]["sequence"], 1)

    def test_no_current_recipient_still_records_fact_without_disclosure(self):
        self.h.members.clear()
        self.record_action(self.result(2, "succeeded", "committed"), now=1000)
        self.assertEqual(self.h.state["session"]["sequence"], 1)
        self.h.replace_member_generation(self.f["agent"], 2)
        self.assertEqual(self.send(self.poll_request())["result"]["events"], [])

    def test_cursor_identity_digest_and_closed_session_fail_before_content(self):
        self.send(self.context(), "game-fixture")
        request = self.poll_request()
        self.send(request)
        changed = deepcopy(request)
        changed["payload"]["page_size"] = 1
        with self.assertRaises(C.ContractError) as caught:
            self.send(changed)
        self.assertEqual(caught.exception.code, "id_conflict")
        for change in (lambda r: r["payload"]["cursor"].update(sequence=99),
                       lambda r: r["payload"]["cursor"].update(instance_epoch="other"),
                       lambda r: r["payload"].update(session_id="other")):
            bad = deepcopy(request)
            change(bad)
            with self.assertRaises((C.ContractError, C.codec.CodecError)):
                self.send(bad)
        self.h.state["grant"]["state"] = "revoked"
        with self.assertRaises(C.ContractError):
            self.send(request)

    def test_actual_publish_snapshot_race_never_mixes_cursor_and_context(self):
        for _ in range(12):
            self.setUp()
            self.send(self.context("c1", "old"), "game-fixture")
            barrier = Barrier(2)
            def publish():
                barrier.wait(timeout=5)
                return self.send(self.context("c2", "new"), "game-fixture")
            def snapshot():
                barrier.wait(timeout=5)
                return self.snapshot()
            with ThreadPoolExecutor(max_workers=2) as pool:
                writer, reader = pool.submit(publish), pool.submit(snapshot)
                writer.result(timeout=5)
                value = reader.result(timeout=5)
            pair = (value["cursor"]["sequence"], value["contexts"][0]["payload"]["content"])
            self.assertIn(pair, {(1, "old"), (2, "new")})
            self.assertEqual(value["session"]["sequence"], value["cursor"]["sequence"])

    def test_actual_revoke_poll_race_has_one_order_and_future_retries_are_filtered(self):
        for _ in range(12):
            self.setUp()
            self.send(self.context(sourced=True), "game-fixture")
            request = self.poll_request()
            barrier = Barrier(2)
            def revoke():
                barrier.wait(timeout=5)
                self.h.revoke_source("room-1")
            def poll():
                barrier.wait(timeout=5)
                return self.send(request)
            with ThreadPoolExecutor(max_workers=2) as pool:
                revoker, reader = pool.submit(revoke), pool.submit(poll)
                revoker.result(timeout=5)
                result = reader.result(timeout=5)
            self.assertIn(len(result["result"]["events"]), (0, 1))
            self.assertEqual(self.send(request)["result"]["events"], [])


if __name__ == "__main__":
    unittest.main()
