"""真实 bytes 到内存提交和编码回复的窄闭环；不是 HTTP 或生产认证测试。"""

from copy import deepcopy
import importlib.util
from itertools import permutations
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / "docs" / "protocol"


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


H = load("chat_harness_test", "chat_harness.py")
F = load("chat_harness_fixture", "fixtures.py")
C = H.C


class ChatHarnessTests(unittest.TestCase):
    def setUp(self):
        self.f = F.core_fixture()
        self.source = {"source_kind": "player_report", "source_id": "local-source-1",
                       "source_principals": [self.f["player"]],
                       "original_disclosure_scope": [self.f[n] for n in ("player", "agent", "game")]}
        self.record = {"instance": self.f["scope"]["instance"], "session_id": "s1", "source": self.source,
                       "controller": self.f["player"], "evidence_ref": "consent-fixture-1", "revision": 1,
                       "state": "active", "publishers": [self.f["agent"]],
                       "allowed_readers": self.source["original_disclosure_scope"], "expires_at": 90000}
        self.h = H.ChatHarness(self.f, {"local-source-1": self.record})
        self.request = F.wire_request("chat.send", {"version": "fixture-only", "session_id": "s1", "id": "m1",
                     "type": "chat.message", "sender": self.f["agent"], "audience": [self.f["player"]],
                     "payload": {"channel": "private", "text": "玩家说钥匙在大厅",
                     "provenance": [deepcopy(self.source)], "source_refs": ["local-source-1"]}, "extensions": {}})

    def submit(self, **kwargs):
        return C.codec.decode(self.h.submit(C.codec.canonical(self.request), "agent-fixture", now=1000, **kwargs))

    def reject_without_mutation(self, code):
        before = deepcopy(self.h.state)
        with self.assertRaises(C.ContractError) as caught:
            self.submit()
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.h.state, before)

    def test_bytes_to_receipt_event_and_delivery(self):
        reply = self.submit()
        C.validate_reply("chat.send", "r1", reply)
        self.assertFalse(reply["result"]["duplicate"])
        events = self.h.delivery(self.f["player"], now=1001)
        self.assertEqual(len(events), 1)
        C.validate_type("Event", events[0])
        self.assertEqual(events[0]["envelope"], self.request["payload"])
        events[0]["envelope"]["payload"]["text"] = "changed"
        self.assertNotEqual(events, self.h.delivery(self.f["player"], now=1001))

    def test_unknown_or_revoked_source_is_denied_without_commit(self):
        for mutation in (lambda r: r.clear(), lambda r: r["local-source-1"].update(state="revoked")):
            self.setUp()
            mutation(self.h.state["records"])
            self.reject_without_mutation("permission_denied")

    def test_source_declaration_cannot_upgrade_kind_or_change_owner(self):
        for mutation in (lambda s: s.update(source_kind="shared_experience"),
                         lambda s: s.update(source_principals=[self.f["game"]]),
                         lambda s: s["original_disclosure_scope"].append(F.principal("bob", "player"))):
            self.setUp()
            mutation(self.request["payload"]["payload"]["provenance"][0])
            self.reject_without_mutation("permission_denied")

    def test_source_reference_and_declaration_must_match_exactly(self):
        for field, value in (("source_refs", []), ("provenance", []),
                             ("source_refs", ["local-source-1", "local-source-1"]),
                             ("provenance", [self.source, self.source])):
            self.setUp()
            self.request["payload"]["payload"][field] = deepcopy(value)
            self.reject_without_mutation("invalid_message")

    def test_source_is_bound_to_target_instance_session_publisher_and_time(self):
        for mutation in (lambda r: r.update(session_id="s2"),
                         lambda r: r["instance"].update(epoch="other"),
                         lambda r: r.update(publishers=[self.f["player"]]),
                         lambda r: r.update(expires_at=1000)):
            self.setUp()
            mutation(self.h.state["records"]["local-source-1"])
            self.reject_without_mutation("permission_denied")

    def test_plaintext_game_observer_is_checked_not_only_recipient(self):
        record = self.h.state["records"]["local-source-1"]
        record["allowed_readers"] = [self.f["player"], self.f["agent"]]
        self.reject_without_mutation("permission_denied")

    def test_source_grant_cannot_expand_original_disclosure(self):
        record = self.h.state["records"]["local-source-1"]
        record["allowed_readers"].append(F.principal("bob", "player"))
        self.reject_without_mutation("permission_denied")

    def test_multiple_sources_use_intersection_not_union(self):
        second = deepcopy(self.record)
        second["source"]["source_id"] = "local-source-2"
        second["allowed_readers"] = [self.f["agent"], self.f["game"]]
        self.h.state["records"]["local-source-2"] = second
        self.request["payload"]["payload"]["source_refs"].append("local-source-2")
        self.request["payload"]["payload"]["provenance"].append(deepcopy(second["source"]))
        self.reject_without_mutation("permission_denied")

    def test_source_expiry_after_acceptance_stops_delivery(self):
        self.submit()
        self.assertEqual(self.h.delivery(self.f["player"], now=90000), [])

    def test_plaintext_relay_requires_separate_disclosure_permission(self):
        relay = F.principal("relay", "service")
        # 可信会话快照夹具；不把此处更新当作活动会话允许变更隐私模型。
        for scope in (self.h.state["session"]["scope"], self.h.state["grant"]["scope"]):
            scope["privacy_model"]["visible_to"].append(relay)
            scope["privacy_model"]["relay_plaintext"] = True
            scope["binding"].update(kind="outbound-relay", relay_identity=relay)
        self.h.state["grant"]["scope_digest"] = C.codec.digest("scope", self.h.state["grant"]["scope"])
        self.reject_without_mutation("permission_denied")

    def test_before_commit_failure_leaves_no_partial_state(self):
        before = deepcopy(self.h.state)
        with self.assertRaises(H.InjectedFailure):
            self.submit(fault="before_commit")
        self.assertEqual(self.h.state, before)
        self.assertFalse(self.submit()["result"]["duplicate"])
        self.assertEqual(len(self.h.state["events"]), 1)

    def test_lost_reply_retries_same_receipt_without_renewing_or_double_event(self):
        with self.assertRaises(H.InjectedFailure):
            self.submit(fault="after_commit")
        before = deepcopy(self.h.state)
        self.request["request_id"] = "r2"
        reply = self.submit()
        self.assertTrue(reply["result"]["duplicate"])
        self.assertEqual(reply["request_id"], "r2")
        self.assertEqual(self.h.state, before)
        self.request["payload"]["payload"]["text"] = "different"
        self.reject_without_mutation("id_conflict")

    def test_revocation_after_acceptance_stops_delivery_not_receipt_recovery(self):
        self.submit()
        self.h.revoke_source("local-source-1")
        self.assertEqual(self.h.delivery(self.f["player"], now=1001), [])
        self.assertTrue(self.submit()["result"]["duplicate"])
        self.request["payload"]["id"] = "m2"
        self.reject_without_mutation("permission_denied")

    def test_membership_or_source_revision_change_does_not_restore_old_event(self):
        self.submit()
        self.h.replace_member_generation(self.f["player"], 2)
        self.assertEqual(self.h.delivery(self.f["player"], now=1001), [])
        self.setUp()
        self.submit()
        self.h.revoke_source("local-source-1")
        self.h.state["records"]["local-source-1"].update(state="active")
        self.assertEqual(self.h.delivery(self.f["player"], now=1001), [])

    def test_stale_credential_and_revoked_grant_cannot_recover_receipt(self):
        for mutation, code in ((lambda h: h.credentials["agent-fixture"].update(generation=2), "stale_controller"),
                               (lambda h: h.state["grant"].update(state="revoked"), "grant_revoked")):
            self.setUp()
            self.submit()
            mutation(self.h)
            self.reject_without_mutation(code)

    def test_all_six_accept_revoke_deliver_orders(self):
        for order in permutations(("accept", "revoke", "deliver")):
            with self.subTest(order=order):
                self.setUp()
                accepted = revoked = False
                for operation in order:
                    if operation == "revoke":
                        self.h.revoke_source("local-source-1")
                        revoked = True
                    elif operation == "accept":
                        if revoked:
                            self.reject_without_mutation("permission_denied")
                        else:
                            self.submit()
                            accepted = True
                    else:
                        self.assertEqual(len(self.h.delivery(self.f["player"], now=1001)), int(accepted and not revoked))

    def test_empty_declared_sources_is_not_claimed_as_content_safety(self):
        self.request["payload"]["payload"].update(provenance=[], source_refs=[])
        self.submit()
        self.assertEqual(len(self.h.delivery(self.f["player"], now=1001)), 1)
        # 协议检查显式标签，不证明自然语言文本没有引用未声明来源。


if __name__ == "__main__":
    unittest.main()
