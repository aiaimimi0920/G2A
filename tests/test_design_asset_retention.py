"""资源内容回收必须晚于独立呈现释放；不删除文件。"""

from copy import deepcopy
import unittest
import test_design_assets as T

A, C = T.A, T.C


class AssetRetentionTests(unittest.TestCase):
    def setUp(self):
        self.case = T.AssetTests()
        self.case.setUp()
        self.case.ready()
        self.h = self.case.h

    def rejected(self, code, fn):
        with self.assertRaises(C.ContractError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def close(self):
        self.case.send("session.close", {"session_id": "s1", "reason": "left"}, "player-fixture", rid="close")

    def release(self, **kwargs):
        self.case.send("presentation.release", {"session_id": "s1", "generation": 1, "device_id": "device-a"},
                       "presentation-fixture", rid="release", **kwargs)

    def test_live_or_unreleased_cache_is_not_collectable(self):
        before = deepcopy(self.h.state["asset_cache"])
        self.rejected("permission_denied", lambda: self.h.compact_closed_asset_cache(now=1000))
        self.close()
        self.h.devices["device-a"].reachable = False
        self.rejected("temporarily_unavailable", lambda: self.h.compact_closed_asset_cache(now=1000))
        self.assertEqual(self.h.state["asset_cache"], before)

    def test_partial_gc_preserves_receipts_and_cannot_reopen_session(self):
        self.close(); self.release()
        receipts = deepcopy(self.h.state["asset_receipts"])
        self.assertEqual(self.h.compact_closed_asset_cache(now=1000, maximum=1), {"removed": 1, "remaining": 1})
        self.assertIsNone(self.h.state["asset_binding"])
        self.assertEqual(self.h.compact_closed_asset_cache(now=1000), {"removed": 1, "remaining": 0})
        self.assertEqual(self.h.compact_closed_asset_cache(now=1000), {"removed": 0, "remaining": 0})
        self.assertEqual(self.h.state["asset_receipts"], receipts)
        self.rejected("grant_revoked", self.case.resolve)
        self.assertEqual(self.h.finish_admission(now=1000)["state"], "closed")

    def test_gc_commit_faults_and_restart_keep_bounded_state(self):
        for fault in ("before_commit", "after_commit"):
            with self.subTest(fault=fault):
                self.setUp(); self.close(); self.release()
                with self.assertRaises(A.U.S.H.InjectedFailure):
                    self.h.compact_closed_asset_cache(now=1000, maximum=1, fault=fault)
                self.h = self.h.restart_from_mock_ledger(now=1000)
                self.assertEqual(len(self.h.state["asset_cache"]), 2 if fault == "before_commit" else 1)
                self.h.compact_closed_asset_cache(now=1000)
                self.assertEqual(self.h.state["asset_cache"], {})

    def test_device_release_without_authority_ack_does_not_allow_gc(self):
        self.close()
        with self.assertRaises(A.U.S.H.InjectedFailure):
            self.release(fault="before_commit")
        self.assertEqual(self.h.devices["device-a"].occupations, {})
        self.rejected("temporarily_unavailable", lambda: self.h.compact_closed_asset_cache(now=1000))
        self.release()
        self.assertEqual(self.h.compact_closed_asset_cache(now=1000)["removed"], 2)

    def test_gc_rejects_boolean_budget_and_unhealthy_restored_ledger(self):
        self.close(); self.release()
        for maximum in (True, 0, 129):
            self.rejected("invalid_arguments", lambda: self.h.compact_closed_asset_cache(now=1000, maximum=maximum))
        self.h = self.h.restart_from_mock_ledger(now=1000, intact=False)
        self.rejected("temporarily_unavailable", lambda: self.h.compact_closed_asset_cache(now=1000))
        self.assertEqual(len(self.h.state["asset_cache"]), 2)

    def test_headless_gc_and_preinstalled_catalog_have_separate_lifetimes(self):
        self.case.start(presentation=False); self.case.ready(); self.h = self.case.h
        self.close()
        self.assertEqual(self.h.compact_closed_asset_cache(now=1000)["removed"], 2)
        from test_design_preinstalled import PreinstalledTests
        installed = PreinstalledTests(); installed.start(); installed.h.finish_admission(now=1000)
        catalog = deepcopy(installed.h.resources.installed_catalog)
        inventory = deepcopy(installed.h.resources.installed_devices)
        installed.send("session.close", {"session_id": "s1", "reason": "left"}, "player-fixture")
        self.assertEqual(installed.h.compact_closed_asset_cache(now=1000), {"removed": 0, "remaining": 0})
        self.assertEqual(installed.h.resources.installed_catalog, catalog)
        self.assertEqual(installed.h.resources.installed_devices, inventory)


if __name__ == "__main__":
    unittest.main()
