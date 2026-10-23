"""关闭会话的资源回执期限、查询知识与幂等屏障。"""

from copy import deepcopy
import unittest
import test_design_assets as T

A, C, F = T.A, T.C, T.F


class AssetReceiptRetentionTests(unittest.TestCase):
    def setUp(self):
        self.case = T.AssetTests(); self.case.setUp(); self.case.ready()
        self.h = self.case.h
        self.until = self.h.state["asset_receipts"]["r1"]["retain_until"]
        # 结果期限不续身份；独立可信登记允许在长保留期末查询的当前 player 身份。
        self.h.identities["receipt-player"] = {**deepcopy(self.h.identities["player-fixture"]), "expires_at": self.until + 1000}

    def close(self):
        self.case.send("session.close", {"session_id": "s1", "reason": "left"}, "player-fixture", rid="close")

    def query(self, now):
        raw = C.codec.canonical(F.wire_request("operation.get", {"operation": "asset.resolve", "original_request_id": "r1"}, "query"))
        return C.codec.decode(self.h.submit(raw, "receipt-player", now=now))

    def rejected(self, code, fn):
        with self.assertRaises(C.ContractError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def test_retry_does_not_extend_frozen_receipt_deadline(self):
        self.case.resolve()
        self.assertEqual(self.h.state["asset_receipts"]["r1"]["retain_until"], self.until)
        self.close()
        self.assertEqual(self.query(self.until - 1)["result"]["state"], "done")
        self.rejected("request_gone", lambda: self.query(self.until))

    def test_gc_expiry_boundary_and_absence_do_not_mean_not_accepted(self):
        self.close()
        cache = deepcopy(self.h.state["asset_cache"])
        self.assertEqual(self.h.compact_closed_asset_receipts(now=self.until - 1)["removed"], 0)
        self.assertEqual(self.h.compact_closed_asset_receipts(now=self.until), {"removed": 1, "remaining": 0})
        self.rejected("permission_denied", lambda: self.query(self.until))
        raw = C.codec.canonical(F.wire_request("asset.resolve", self.case.payload, "r1"))
        self.rejected("grant_revoked", lambda: self.h.submit(raw, "resource-fixture", now=self.until))
        self.assertEqual(self.h.state["asset_cache"], cache)

    def test_gc_failure_before_and_after_commit_and_restart(self):
        for fault in ("before_commit", "after_commit"):
            with self.subTest(fault=fault):
                self.setUp(); self.close()
                with self.assertRaises(A.U.S.H.InjectedFailure):
                    self.h.compact_closed_asset_receipts(now=self.until, fault=fault)
                self.h = self.h.restart_from_mock_ledger(now=self.until)
                self.assertEqual(len(self.h.state["asset_receipts"]), 1 if fault == "before_commit" else 0)
                self.h.compact_closed_asset_receipts(now=self.until)
                self.assertEqual(self.h.state["asset_receipts"], {})

    def test_active_receipts_and_strict_budget_are_protected(self):
        self.rejected("permission_denied", lambda: self.h.compact_closed_asset_receipts(now=1000))
        for maximum in (True, 0, 129):
            self.rejected("invalid_arguments", lambda: self.h.compact_closed_asset_receipts(now=1000, maximum=maximum))
        self.assertEqual(len(self.h.state["asset_receipts"]), 1)

    def test_failure_receipt_expires_without_reexecution(self):
        self.case.start(mutate=lambda value: value.update(fixture_format="unsupported"))
        self.h = self.case.h
        self.assertEqual(self.case.resolve()["error"]["outcome"], "accepted")
        until = self.h.state["asset_receipts"]["r1"]["retain_until"]
        calls = self.h.resources.parse_calls
        raw = C.codec.canonical(F.wire_request("asset.resolve", self.case.payload, "r1"))
        self.rejected("request_gone", lambda: self.h.submit(raw, "resource-fixture", now=until))
        self.h.compact_closed_asset_receipts(now=until)
        self.rejected("grant_revoked", lambda: self.h.submit(raw, "resource-fixture", now=until))
        self.assertEqual(self.h.resources.parse_calls, calls)

    def test_gc_budget_is_per_receipt_not_per_shared_cache_entry(self):
        self.case.resolve(rid="r2")
        self.assertEqual(len(self.h.state["asset_cache"]), 2)
        self.close()
        self.assertEqual(self.h.compact_closed_asset_receipts(now=self.until, maximum=1), {"removed": 1, "remaining": 1})
        self.assertEqual(self.h.compact_closed_asset_receipts(now=self.until, maximum=1), {"removed": 1, "remaining": 0})
        self.assertEqual(len(self.h.state["asset_cache"]), 2)


if __name__ == "__main__":
    unittest.main()
