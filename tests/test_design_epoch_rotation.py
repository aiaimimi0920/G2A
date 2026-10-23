"""代次切换顺序、独立提交故障与有限交错的参考模型证明。"""

from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("epoch_model", Path(__file__).resolve().parents[1] / "docs/protocol/epoch_rotation.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


class EpochRotationTests(unittest.TestCase):
    def setUp(self):
        self.m = M.EpochRotation()

    def ready(self):
        identity = self.m.register(0, "consent")
        claim = self.m.claim(identity, "request")
        self.m.close(identity)
        return identity, claim

    def rejected(self, code, function):
        with self.assertRaises(M.RotationError) as raised:
            function()
        self.assertEqual(str(raised.exception), code)

    def test_identity_slots_reused_only_under_new_epoch(self):
        old, claim = self.ready()
        self.m.begin(claim); self.m.finish(claim)
        self.m.seal(0); self.m.advance_game(1); self.m.advance_relay(1)
        new = self.m.register(1, "consent")
        self.assertEqual(old[1], new[1])
        self.assertNotEqual(old, new)
        self.assertEqual(self.m.game["effects"], 1)
        self.assertEqual(self.m.game["journal"], set())
        self.rejected("request_gone", lambda: self.m.begin(claim))
        self.rejected("permission_denied", lambda: self.m.register(0, "fresh-looking-id"))
        self.m.begin(self.m.claim(new, "request"))

    def test_active_boxes_and_inflight_effects_gate_rotation(self):
        identity = self.m.register(0, "consent")
        claim = self.m.claim(identity, "request")
        self.rejected("not_drained", lambda: self.m.seal(0))
        self.m.begin(claim); self.m.close(identity); self.m.seal(0)
        self.rejected("not_drained", lambda: self.m.advance_game(1))
        self.m.finish(claim); self.m.advance_game(1); self.m.advance_relay(1)
        self.assertEqual(self.m.game["effects"], 1)

    def test_delayed_claim_before_and_after_game_fence(self):
        for enters_first in (True, False):
            self.setUp()
            _, claim = self.ready(); self.m.seal(0)
            if enters_first:
                self.m.begin(claim)
                self.rejected("not_drained", lambda: self.m.advance_game(1))
                self.m.finish(claim)
            self.m.advance_game(1)
            self.rejected("request_gone", lambda: self.m.begin(claim))
            self.assertEqual(self.m.game["effects"], int(enters_first))

    def test_no_admission_during_cross_authority_gap(self):
        self.ready(); self.m.seal(0)
        self.rejected("generation_conflict", lambda: self.m.advance_relay(1))
        self.m.advance_game(1)
        self.rejected("permission_denied", lambda: self.m.register(0, "old"))
        self.rejected("permission_denied", lambda: self.m.register(1, "new"))
        self.m.advance_relay(1)
        self.assertEqual(self.m.register(1, "new"), (1, 1))

    def test_each_commit_fault_is_recoverable_after_restart(self):
        for stage in ("seal", "advance_game", "advance_relay"):
            for fault in ("before_commit", "after_commit"):
                with self.subTest(stage=stage, fault=fault):
                    self.setUp(); _, claim = self.ready()
                    if stage != "seal":
                        self.m.seal(0)
                    if stage == "advance_relay":
                        self.m.advance_game(1)
                    before = (deepcopy(self.m.relay), deepcopy(self.m.game))
                    with self.assertRaises(M.RotationFault):
                        getattr(self.m, stage)(0 if stage == "seal" else 1, fault=fault)
                    if fault == "before_commit":
                        self.assertEqual((self.m.relay, self.m.game), before)
                    self.m = self.m.restart()
                    getattr(self.m, stage)(0 if stage == "seal" else 1)
                    if self.m.relay["epoch"] == 0:
                        self.m.advance_game(1); self.m.advance_relay(1)
                    self.rejected("request_gone", lambda: self.m.begin(claim))
                    self.assertEqual(self.m.game["epoch"], 1)

    def test_multiple_rotations_remain_bounded_and_old_claims_stay_rejected(self):
        old_claims = []
        for epoch in range(20):
            for index in range(8):
                identity = self.m.register(epoch, str(index))
                claim = self.m.claim(identity, "request")
                old_claims.append(claim)
                self.m.begin(claim); self.m.finish(claim); self.m.close(identity)
            self.rejected("resource_limit", lambda: self.m.register(epoch, "overflow"))
            self.m.seal(epoch); self.m.advance_game(epoch + 1); self.m.advance_relay(epoch + 1)
            self.assertEqual(len(self.m.relay["boxes"]), 0)
            self.assertEqual(len(self.m.relay["pairings"]), 0)
            self.assertEqual(len(self.m.game["journal"]), 0)
        for claim in old_claims:
            self.rejected("request_gone", lambda: self.m.begin(claim))
        self.assertEqual(self.m.game["effects"], 160)

    def test_restart_does_not_erase_unresolved_inflight_or_reexecute(self):
        _, claim = self.ready()
        self.m.begin(claim); self.m.seal(0)
        self.m = self.m.restart()
        self.rejected("not_drained", lambda: self.m.advance_game(1))
        self.rejected("already_seen", lambda: self.m.begin(claim))
        self.assertEqual(self.m.game["effects"], 0)
        self.assertIn(claim, self.m.game["inflight"])

    def test_strict_epoch_no_jump_no_wrap_and_fail_closed_restart(self):
        for value in (True, -1, 1.5, "1", 2**53):
            self.rejected("invalid_arguments", lambda: self.m.seal(value))
        self.ready(); self.m.seal(0)
        self.rejected("generation_conflict", lambda: self.m.advance_game(2))
        old = self.m
        self.m = self.m.restart(intact=False)
        self.rejected("temporarily_unavailable", lambda: self.m.advance_game(1))
        self.rejected("temporarily_unavailable", lambda: old.advance_game(1))
        self.setUp()
        self.m.relay["epoch"] = self.m.MAX_EPOCH
        self.rejected("resource_limit", lambda: self.m.seal(self.m.MAX_EPOCH))


    def test_restore_rejects_old_epoch_without_retiring_current_instance(self):
        _, claim = self.ready()
        old = self.m.snapshot()
        self.m.seal(0); self.m.advance_game(1); self.m.advance_relay(1)
        current = self.m.snapshot()
        self.rejected("snapshot_mismatch", lambda: self.m.restart(snapshot=old))
        self.assertEqual(self.m.snapshot(), current)
        self.m = self.m.restart(snapshot=current)
        self.rejected("request_gone", lambda: self.m.begin(claim))

    def test_restore_rejects_same_epoch_snapshot_before_dispatch_marker(self):
        _, claim = self.ready()
        old = self.m.snapshot()
        self.m.begin(claim)
        self.rejected("snapshot_mismatch", lambda: self.m.restart(snapshot=old))
        self.m = self.m.restart(snapshot=self.m.snapshot())
        self.rejected("already_seen", lambda: self.m.begin(claim))
        self.assertIn(claim, self.m.game["inflight"])

    def test_restore_rejects_foreign_instance_even_if_states_match(self):
        other = M.EpochRotation()
        self.assertEqual(self.m.relay, other.relay)
        self.rejected("snapshot_mismatch", lambda: self.m.restart(snapshot=other.snapshot()))

    def test_restore_rejects_mixed_and_modified_snapshot(self):
        self.ready(); old = self.m.snapshot()
        self.m.seal(0); self.m.advance_game(1)
        current = self.m.snapshot()
        mixed = deepcopy(current); mixed["game"] = old["game"]
        self.rejected("snapshot_mismatch", lambda: self.m.restart(snapshot=mixed))
        modified = deepcopy(current); modified["game"]["effects"] += 1
        self.rejected("snapshot_mismatch", lambda: self.m.restart(snapshot=modified))
        self.m = self.m.restart(snapshot=current)
        self.m.advance_relay(1)

    def test_checkpoint_and_owner_commit_have_same_fault_boundary(self):
        self.ready()
        before, anchors = self.m.snapshot(), deepcopy(self.m.checkpoints)
        with self.assertRaises(M.RotationFault):
            self.m.seal(0, fault="before_commit")
        self.assertEqual(self.m.checkpoints, anchors)
        self.m = self.m.restart(snapshot=before)
        with self.assertRaises(M.RotationFault):
            self.m.seal(0, fault="after_commit")
        self.assertNotEqual(self.m.checkpoints["relay"], anchors["relay"])
        self.assertEqual(self.m.checkpoints["game"], anchors["game"])
        self.rejected("snapshot_mismatch", lambda: self.m.restart(snapshot=before))
        self.m = self.m.restart(snapshot=self.m.snapshot())
        self.assertTrue(self.m.relay["sealed"])

    def test_restore_rejects_map_disguised_as_old_normalized_list(self):
        current = self.m.snapshot()
        forged = deepcopy(current)
        forged["relay"] = ["map", [["boxes", ["map", []]], ["epoch", 0],
                                  ["pairings", ["set", []]], ["sealed", False]]]
        self.rejected("snapshot_mismatch", lambda: self.m.restart(snapshot=forged))
        self.assertFalse(self.m.retired)
        self.assertEqual(self.m.snapshot(), current)
        self.m = self.m.restart(snapshot=current)
        self.assertEqual(self.m.register(0, "still-valid"), (0, 1))

    def test_restore_requires_checkpoint_not_snapshot_supplied_override(self):
        current = self.m.snapshot()
        injected = deepcopy(current); injected["checkpoints"] = deepcopy(self.m.checkpoints)
        self.rejected("invalid_snapshot", lambda: self.m.restart(snapshot=injected))
        del self.m.checkpoints["game"]  # 模拟独立恢复锚点丢失，不信任快照自证完整。
        self.rejected("snapshot_mismatch", lambda: self.m.restart(snapshot=current))

    def test_checkpoint_digest_distinguishes_all_container_and_leaf_types(self):
        digest = self.m._digest
        for left, right in (({"a": 1}, ["map", [["a", 1]]]), ((1, 2), ["tuple", [1, 2]]),
                            ({1, 2}, ["set", [1, 2]]), ([1, 2], (1, 2)), (True, 1),
                            (b"a", "61"), (b"a", ["bytes", "61"]), (None, ["null"])):
            self.assertNotEqual(digest(left), digest(right))
        self.assertEqual(digest({"a": 1, "b": 2}), digest({"b": 2, "a": 1}))
        self.assertEqual(digest({"a", "b"}), digest(set(["b", "a"])))

    def test_checkpoint_digest_rejects_unsupported_types_without_retiring(self):
        for value in (1.0, float("nan"), bytearray(b"a"), object()):
            snapshot = self.m.snapshot(); snapshot["relay"] = value
            self.rejected("invalid_snapshot", lambda: self.m.restart(snapshot=snapshot))
            self.assertFalse(self.m.retired)

    def test_snapshot_copy_isolated_and_stale_instance_cannot_export(self):
        self.ready()
        snapshot = self.m.snapshot()
        snapshot["relay"]["boxes"].clear()
        self.assertEqual(len(self.m.relay["boxes"]), 1)
        old = self.m
        self.m = self.m.restart(snapshot=self.m.snapshot())
        self.rejected("temporarily_unavailable", old.snapshot)
        self.rejected("temporarily_unavailable", old.restart)


if __name__ == "__main__":
    unittest.main()
