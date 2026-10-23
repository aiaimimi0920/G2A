"""代次字节绑定与可信证据登记的组合拒绝场景。"""

import importlib.util
from copy import deepcopy
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "docs/protocol"


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M, B = load("binding_rotation", "epoch_rotation.py"), load("binding_port", "epoch_binding.py")


class EpochBindingTests(unittest.TestCase):
    def setUp(self):
        self.m = M.EpochRotation()
        self.p = B.EpochBoundPort(self.m, "relay-authority")
        self.pairing = self.p.enroll_pairing("player")
        self.pairing_raw = self.p.binding_bytes(self.pairing)
        self.identity = self.p.register(self.pairing_raw, self.pairing)
        self.control = self.p.enroll_mailbox(self.identity, "player", "controller")
        self.agent = self.p.enroll_mailbox(self.identity, "agent", "agent")
        self.raw = self.p.binding_bytes(self.agent)

    def rejected(self, code, function):
        with self.assertRaises(M.RotationError) as raised:
            function()
        self.assertEqual(str(raised.exception), code)

    def changed(self, **fields):
        value = B.codec.decode(self.raw)
        value.update(fields)
        return B.codec.canonical(value)

    def rotate(self):
        self.p.close(self.p.binding_bytes(self.control), self.control)
        self.m.seal(0); self.m.advance_game(1); self.m.advance_relay(1)

    def test_byte_binding_roundtrip_dispatch_and_rotation(self):
        claim = self.p.claim(self.raw, self.agent, "request")
        self.m.begin(claim); self.m.finish(claim)
        self.rotate()
        self.rejected("generation_conflict", lambda: self.p.claim(self.raw, self.agent, "request"))
        pairing = self.p.enroll_pairing("player")
        new = self.p.register(self.p.binding_bytes(pairing), pairing)
        self.assertEqual(new, (1, 1))
        new_agent = self.p.enroll_mailbox(new, "agent", "agent")
        self.m.begin(self.p.claim(self.p.binding_bytes(new_agent), new_agent, "request"))
        self.assertEqual(self.m.game["effects"], 1)
        self.rejected("request_gone", lambda: self.m.begin(claim))

    def test_client_cannot_relabel_old_evidence_to_new_epoch(self):
        self.rotate()
        self.rejected("unauthenticated", lambda: self.p.claim(self.changed(epoch=1), self.agent, "request"))
        self.rejected("generation_conflict", lambda: self.p.register(self.pairing_raw, self.pairing))
        self.assertEqual(self.p.records, {})

    def test_missing_epoch_and_unknown_version_are_not_defaulted(self):
        value = B.codec.decode(self.raw); del value["epoch"]
        self.rejected("invalid_arguments", lambda: self.p.claim(B.codec.canonical(value), self.agent, "request"))
        self.rejected("unsupported_version", lambda: self.p.claim(self.changed(version="g2a-design-1"), self.agent, "request"))
        self.rejected("invalid_arguments", lambda: self.p.claim(self.changed(extra="ignored?"), self.agent, "request"))

    def test_cross_authority_instance_mailbox_principal_and_role_rejected(self):
        for field, value in (("authority", "other"), ("instance_id", "other"), ("mailbox_id", 2),
                             ("principal", "player"), ("role", "controller")):
            with self.subTest(field=field):
                self.rejected("permission_denied", lambda: self.p.claim(self.changed(**{field: value}), self.agent, "request"))
        self.assertEqual(self.m.game["journal"], set())

    def test_exact_integer_binding_rejects_boolean_aliases(self):
        for fields in ({"epoch": False}, {"mailbox_id": True}, {"epoch": -1}, {"mailbox_id": 0}):
            self.rejected("invalid_arguments", lambda: self.p.claim(self.changed(**fields), self.agent, "request"))
        self.rejected("invalid_arguments", lambda: self.p.enroll_mailbox((False, True), "agent", "agent"))

    def test_roles_and_pairing_evidence_are_not_interchangeable(self):
        self.rejected("permission_denied", lambda: self.p.close(self.raw, self.agent))
        self.rejected("permission_denied", lambda: self.p.enroll_mailbox(self.identity, "other", "controller"))
        game = self.p.enroll_mailbox(self.identity, "game", "game")
        self.rejected("permission_denied", lambda: self.p.claim(self.p.binding_bytes(game), game, "request"))
        self.rejected("permission_denied", lambda: self.p.claim(self.pairing_raw, self.pairing, "request"))
        self.rejected("id_conflict", lambda: self.p.register(self.pairing_raw, self.pairing))

    def test_same_request_id_is_principal_scoped(self):
        agent_claim = self.p.claim(self.raw, self.agent, "same")
        player_claim = self.p.claim(self.p.binding_bytes(self.control), self.control, "same")
        self.assertNotEqual(agent_claim, player_claim)
        self.m.begin(agent_claim); self.m.begin(player_claim)
        self.rejected("already_seen", lambda: self.m.begin(agent_claim))

    def test_rotation_gap_does_not_issue_future_pairing_or_mutate_old_token(self):
        self.p.close(self.p.binding_bytes(self.control), self.control)
        self.m.seal(0); self.m.advance_game(1)
        self.rejected("request_gone", lambda: self.p.enroll_pairing("player"))
        self.assertEqual(self.p.binding_bytes(self.agent), self.raw)
        self.rejected("request_gone", lambda: self.p.claim(self.raw, self.agent, "request"))

    def test_binding_codec_and_size_limits_reject_ambiguous_bytes(self):
        for raw in (b'{"epoch":0,"epoch":1}', b'{"epoch":NaN}', b'[]'):
            with self.assertRaises((B.codec.CodecError, M.RotationError)):
                self.p.claim(raw, self.agent, "request")
        self.rejected("invalid_arguments", lambda: self.p.claim(b" " * 4097, self.agent, "request"))
        self.assertEqual(self.m.game["journal"], set())

    def test_trusted_registry_is_bounded_and_rotation_releases_old_entries(self):
        while len(self.p.records) < 64:
            self.p.enroll_mailbox(self.identity, "agent", "agent")
        self.rejected("resource_limit", lambda: self.p.enroll_pairing("player"))
        self.rotate()
        token = self.p.enroll_pairing("player")
        self.assertEqual(len(self.p.records), 1)
        self.assertNotIn(self.agent, self.p.records)
        self.assertEqual(B.codec.decode(self.p.binding_bytes(token))["epoch"], 1)

    def test_restart_requires_fresh_trusted_enrollment_not_copied_tokens(self):
        old = self.p
        self.m = self.m.restart()
        self.rejected("temporarily_unavailable", lambda: old.claim(self.raw, self.agent, "request"))
        fresh = B.EpochBoundPort(self.m, "relay-authority")
        self.rejected("unauthenticated", lambda: fresh.claim(self.raw, self.agent, "request"))


    def test_checked_binding_recovery_preserves_credentials_and_original_owner(self):
        snapshot = self.p.snapshot()
        restored = self.m.restart()
        port = self.p.restart(restored, snapshot=snapshot)
        self.assertEqual(port.binding_bytes(self.agent), self.raw)
        restored.begin(port.claim(self.raw, self.agent, "recovered"))
        self.rejected("permission_denied", lambda: port.enroll_mailbox(self.identity, "intruder", "controller"))
        port.close(port.binding_bytes(self.control), self.control)
        self.assertEqual(restored.relay["boxes"][self.identity], "closed")
        self.rejected("temporarily_unavailable", lambda: self.p.restart(restored, snapshot=snapshot))

    def test_binding_recovery_rejects_stale_registry_snapshot(self):
        old = self.p.snapshot()
        fresh_token = self.p.enroll_mailbox(self.identity, "agent-two", "agent")
        current = self.p.snapshot()
        restored = self.m.restart()
        self.rejected("snapshot_mismatch", lambda: self.p.restart(restored, snapshot=old))
        port = self.p.restart(restored, snapshot=current)
        self.assertEqual(B.codec.decode(port.binding_bytes(fresh_token))["principal"], "agent-two")

    def test_binding_recovery_rejects_changed_owner_role_and_token(self):
        snapshot = self.p.snapshot()
        restored = self.m.restart()
        for mutation in ("owner", "role", "token"):
            candidate = deepcopy(snapshot)
            if mutation == "owner":
                candidate["binding"]["owners"][self.identity] = "intruder"
            elif mutation == "role":
                candidate["binding"]["records"][self.agent]["role"] = "controller"
            else:
                candidate["binding"]["records"]["forged-token"] = candidate["binding"]["records"].pop(self.agent)
            self.rejected("snapshot_mismatch", lambda: self.p.restart(restored, snapshot=candidate))
        self.assertFalse(self.p.retired)

    def test_binding_recovery_requires_matching_model_checkpoint(self):
        old = self.p.snapshot()
        claim = self.p.claim(self.raw, self.agent, "inflight")
        self.m.begin(claim)
        current = self.p.snapshot()
        restored = self.m.restart()
        self.rejected("snapshot_mismatch", lambda: self.p.restart(restored, snapshot=old))
        port = self.p.restart(restored, snapshot=current)
        self.rejected("already_seen", lambda: restored.begin(port.claim(self.raw, self.agent, "inflight")))

    def test_binding_recovery_keeps_closed_mailbox_and_consumed_pairing(self):
        self.p.close(self.p.binding_bytes(self.control), self.control)
        snapshot = self.p.snapshot()
        restored = self.m.restart()
        port = self.p.restart(restored, snapshot=snapshot)
        self.rejected("request_gone", lambda: port.claim(self.raw, self.agent, "late"))
        self.rejected("id_conflict", lambda: port.register(self.pairing_raw, self.pairing))

    def test_binding_recovery_rejects_foreign_unhealthy_and_missing_anchor(self):
        snapshot = self.p.snapshot()
        restored = self.m.restart()
        foreign = M.EpochRotation()
        self.rejected("snapshot_mismatch", lambda: self.p.restart(foreign, snapshot=snapshot))
        restored.healthy = False
        self.rejected("temporarily_unavailable", lambda: self.p.restart(restored, snapshot=snapshot))
        restored.healthy = True  # 仅恢复本测试的可信故障注入标记。
        self.p.checkpoint = None
        self.rejected("snapshot_mismatch", lambda: self.p.restart(restored, snapshot=snapshot))

    def test_binding_recovery_never_relabels_snapshot_after_epoch_rotation(self):
        old = self.p.snapshot()
        self.rotate()
        current = self.p.snapshot()  # 同步已完成的代次切换并清理旧凭据。
        restored = self.m.restart()
        self.rejected("snapshot_mismatch", lambda: self.p.restart(restored, snapshot=old))
        port = self.p.restart(restored, snapshot=current)
        self.assertEqual(port.records, {})
        self.rejected("generation_conflict", lambda: port.claim(self.raw, self.agent, "old"))


if __name__ == "__main__":
    unittest.main()
