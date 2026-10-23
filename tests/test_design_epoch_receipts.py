"""跨代次回执保留、独立读权、过期清理及防重放。"""

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


M, B = load("receipt_rotation", "epoch_rotation.py"), load("receipt_binding", "epoch_binding.py")


class EpochReceiptTests(unittest.TestCase):
    def setUp(self):
        self.m = M.EpochRotation()
        self.p = B.EpochBoundPort(self.m, "relay")
        pairing = self.p.enroll_pairing("player")
        self.identity = self.p.register(self.p.binding_bytes(pairing), pairing)
        self.agent = self.p.enroll_mailbox(self.identity, "agent", "agent")
        self.control = self.p.enroll_mailbox(self.identity, "player", "controller")
        self.claim = self.p.claim(self.p.binding_bytes(self.agent), self.agent, "request")
        self.m.begin(self.claim, now=0, retain_ms=10)
        self.reader = self.p.enroll_receipt_reader(self.claim, "agent", now=0, expires_at=20)
        self.raw = self.p.binding_bytes(self.reader)

    def rejected(self, code, call):
        with self.assertRaises(M.RotationError) as raised:
            call()
        self.assertEqual(str(raised.exception), code)

    def query(self, now=0):
        return self.p.query_receipt(self.raw, self.reader, "request", now=now)

    def rotate(self):
        self.p.close(self.p.binding_bytes(self.control), self.control)
        self.m.seal(0); self.m.advance_game(1); self.m.advance_relay(1)

    def test_receipt_survives_epoch_and_credential_recovery(self):
        self.assertEqual(self.query(), {"phase": "accepted", "retain_until": 10})
        self.m.finish(self.claim); self.rotate()
        self.assertEqual(self.query()["phase"], "completed")
        self.assertEqual(self.m.game["journal"], set())
        snapshot = self.p.snapshot()
        restored = self.m.restart()
        self.p = self.p.restart(restored, snapshot=snapshot); self.m = restored
        self.assertEqual(self.query()["phase"], "completed")
        self.rejected("request_gone", lambda: self.m.begin(self.claim))

    def test_reader_is_independent_exact_subject_and_request_authority(self):
        self.rejected("permission_denied", lambda: self.p.enroll_receipt_reader(self.claim, "player", now=0, expires_at=20))
        self.rejected("unauthenticated", lambda: self.p.query_receipt(self.p.binding_bytes(self.agent), self.agent, "request", now=0))
        self.rejected("permission_denied", lambda: self.p.query_receipt(self.raw, self.reader, "other", now=0))
        self.rejected("unauthenticated", lambda: self.p.claim(self.raw, self.reader, "new"))
        bad = B.codec.decode(self.raw); bad["epoch"] = 1
        self.rejected("permission_denied", lambda: self.p.query_receipt(B.codec.canonical(bad), self.reader, "request", now=0))

    def test_expiry_is_gone_not_nonacceptance_and_does_not_extend(self):
        self.m.finish(self.claim)
        self.assertEqual(self.query(9)["retain_until"], 10)
        self.rejected("request_gone", lambda: self.query(10))
        self.assertEqual(self.m.compact_receipts(now=10), {"removed": 1, "remaining": 0})
        self.rejected("request_gone", lambda: self.query(11))
        self.rejected("already_seen", lambda: self.m.begin(self.claim))
        self.assertEqual(self.m.game["effects"], 1)

    def test_revocation_does_not_change_receipt_and_survives_restart(self):
        before = deepcopy(self.m.game["receipts"])
        self.p.revoke_receipt_reader(self.reader)
        snapshot = self.p.snapshot(); restored = self.m.restart()
        self.p = self.p.restart(restored, snapshot=snapshot); self.m = restored
        self.rejected("permission_denied", self.query)
        self.assertEqual(self.m.game["receipts"], before)
        self.assertEqual(self.p.compact_receipt_readers(now=0)["removed"], 1)
        self.rejected("unauthenticated", self.query)

    def test_pending_expired_receipt_cannot_be_compacted_until_settled(self):
        self.rejected("request_gone", lambda: self.query(10))
        self.assertEqual(self.m.compact_receipts(now=10)["removed"], 0)
        self.assertIn(self.claim, self.m.game["inflight"])
        self.m.finish(self.claim)
        self.assertEqual(self.m.compact_receipts(now=10)["removed"], 1)
        self.assertEqual(self.m.game["effects"], 1)

    def test_archive_gc_faults_are_atomic_and_do_not_erase_replay_fence(self):
        self.m.finish(self.claim)
        before = deepcopy(self.m.game["receipts"])
        with self.assertRaises(M.RotationFault):
            self.m.compact_receipts(now=10, fault="before_commit")
        self.assertEqual(self.m.game["receipts"], before)
        with self.assertRaises(M.RotationFault):
            self.m.compact_receipts(now=10, fault="after_commit")
        self.m = self.m.restart()
        self.assertEqual(self.m.compact_receipts(now=10)["removed"], 0)
        self.rejected("already_seen", lambda: self.m.begin(self.claim))

    def test_read_clock_is_strict_and_reader_expiry_is_separate(self):
        for now in (True, -1, 1.5):
            self.rejected("invalid_arguments", lambda: self.query(now))
        self.query(5)
        self.rejected("temporarily_unavailable", lambda: self.query(4))
        self.rejected("permission_denied", lambda: self.query(20))
        self.assertEqual(self.p.compact_receipt_readers(now=20)["removed"], 1)
        self.assertIn(self.claim, self.m.game["receipts"])

    def test_receipt_capacity_does_not_silently_evict_older_queries(self):
        self.m.finish(self.claim)
        for index in range(1023):
            self.m.game["receipts"][((0, 8), ("fixture", str(index)))] = {"phase": "completed", "retain_until": 10}
        other = self.p.claim(self.p.binding_bytes(self.agent), self.agent, "other")
        self.rejected("resource_limit", lambda: self.m.begin(other))
        self.assertEqual(self.query()["phase"], "completed")
        self.assertEqual(self.m.compact_receipts(now=10, maximum=1), {"removed": 1, "remaining": 1023})
        self.m.begin(other)
        self.assertEqual(len(self.m.game["receipts"]), 1024)


if __name__ == "__main__":
    unittest.main()
