"""互通门禁必须包含新 profile 的实际执行证据。"""

import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("interop_gate", Path(__file__).resolve().parents[1] / "scripts/verify_design_interop.py")
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)


class InteropGateTests(unittest.TestCase):
    def valid(self):
        return {"passed": True, "relay_epoch_profile": {"passed": True, "epoch": 0, "wire_calls": 9},
            "launch_revocation": {"passed": True, "phases": 2, "wire_calls": 16},
            "revoke_fanout": {"passed": True, "kinds": ["session", "grant", "result_read", "capability"],
                              "scope": "candidate-coordinator-fixture", "completed": 4, "wire_calls": 28,
                              "fixture_calls": 119, "snapshots_rejected": 8, "namespace_isolated": True,
                              "dynamic_catalogue": {"passed": True, "faults": ["before_commit", "after_commit"],
                                  "completed": 2, "stale_selections": 2, "unresolved_retirements": 4,
                                  "retired_replays": 2, "multi_session": True}},
            "launcher_retirement": {"passed": True, "faults": ["after_seal", "after_commit"],
                                    "late_start_blocked": True, "sealed_ports": 2, "start_calls": 2, "wire_calls": 22},
            "launch_retention": {"passed": True, "faults": ["before_commit", "after_commit"],
                                 "pending_preserved": True, "removed": 3, "start_calls": 3, "wire_calls": 24},
            "launch_monitor": {"passed": True, "faults": ["before_commit", "after_commit"],
                               "closed_sessions": 2, "start_calls": 2, "wire_calls": 20},
            "preinstalled": {"passed": True, "ready": True, "fetch_hops": 0, "parse_calls": 0,
                             "render_calls": 1, "wire_calls": 11},
            "relay_rotation": {"passed": True, "epoch": 1, "archive_removed": 1, "wire_calls": 13},
            "relay_settlement": {"passed": True, "modes": ["unstarted", "admission", "action", "control"],
                "settled": 4, "wire_calls": 26},
            "epoch_binding": {"passed": True, "profile": "g2a-epoch-binding-1",
            "wire_calls": 26, "fixture_calls": 51, "archived_receipt": True,
            "relay_epoch": 1, "game_epoch": 1, "effects": 2}}

    def test_legacy_or_missing_summary_does_not_pass(self):
        for value in (None, [], True, {}, {"passed": True}, {"passed": True, "epoch_binding": []}):
            self.assertFalse(V.peer_passed(value))

    def test_current_summary_passes(self):
        self.assertTrue(V.peer_passed(self.valid()))

    def test_fanout_requires_all_four_independent_object_kinds(self):
        for field, value in (("passed", False), ("kinds", ["session"]), ("scope", "public-api"),
                             ("completed", True), ("completed", 3), ("wire_calls", True), ("wire_calls", 15)):
            summary = self.valid(); summary["revoke_fanout"][field] = value
            self.assertFalse(V.peer_passed(summary))
        for value in (None, [], {}, True):
            summary = self.valid(); summary["revoke_fanout"] = value
            self.assertFalse(V.peer_passed(summary))
        summary = self.valid(); del summary["revoke_fanout"]
        self.assertFalse(V.peer_passed(summary))

    def test_fanout_requires_checkpoint_and_namespace_evidence(self):
        for field, value in (("snapshots_rejected", True), ("snapshots_rejected", 7),
                             ("namespace_isolated", 1), ("namespace_isolated", False),
                             ("wire_calls", 17), ("fixture_calls", True), ("fixture_calls", 62)):
            summary = self.valid(); summary["revoke_fanout"][field] = value
            self.assertFalse(V.peer_passed(summary))
        for field in ("snapshots_rejected", "namespace_isolated", "fixture_calls"):
            summary = self.valid(); del summary["revoke_fanout"][field]
            self.assertFalse(V.peer_passed(summary))

    def test_launch_revocation_evidence_is_required(self):
        for field, value in (("passed", False), ("phases", True), ("phases", 1), ("wire_calls", True), ("wire_calls", 15)):
            summary = self.valid(); summary["launch_revocation"][field] = value
            self.assertFalse(V.peer_passed(summary))
        for value in (None, [], {}):
            summary = self.valid(); summary["launch_revocation"] = value
            self.assertFalse(V.peer_passed(summary))

    def test_fanout_dynamic_catalogue_requires_full_independent_lifecycle(self):
        for field, value in (("passed", False), ("faults", ["after_commit"]), ("completed", True),
                             ("completed", 1), ("stale_selections", True), ("stale_selections", 1),
                             ("unresolved_retirements", True), ("unresolved_retirements", 3),
                             ("retired_replays", True), ("retired_replays", 1), ("multi_session", 1), ("multi_session", False)):
            summary = self.valid(); summary["revoke_fanout"]["dynamic_catalogue"][field] = value
            self.assertFalse(V.peer_passed(summary))
        for value in (None, {}, [], True):
            summary = self.valid(); summary["revoke_fanout"]["dynamic_catalogue"] = value
            self.assertFalse(V.peer_passed(summary))
        summary = self.valid(); del summary["revoke_fanout"]["dynamic_catalogue"]
        self.assertFalse(V.peer_passed(summary))
        for field, value in (("wire_calls", 27), ("fixture_calls", 118)):
            summary = self.valid(); summary["revoke_fanout"][field] = value
            self.assertFalse(V.peer_passed(summary))

    def test_launch_monitor_requires_both_commit_windows_and_no_restart(self):
        for field, value in (("passed", False), ("faults", ["before_commit"]),
                             ("closed_sessions", True), ("closed_sessions", 1),
                             ("start_calls", True), ("start_calls", 3),
                             ("wire_calls", True), ("wire_calls", 19)):
            summary = self.valid(); summary["launch_monitor"][field] = value
            self.assertFalse(V.peer_passed(summary))
        for value in (None, [], {}, True):
            summary = self.valid(); summary["launch_monitor"] = value
            self.assertFalse(V.peer_passed(summary))
        summary = self.valid(); del summary["launch_monitor"]
        self.assertFalse(V.peer_passed(summary))

    def test_launch_retention_requires_unknown_barrier_and_both_faults(self):
        for field, value in (("passed", False), ("faults", ["before_commit"]),
                             ("pending_preserved", 1), ("pending_preserved", False),
                             ("removed", True), ("removed", 2), ("start_calls", True),
                             ("start_calls", 4), ("wire_calls", True), ("wire_calls", 23)):
            summary = self.valid(); summary["launch_retention"][field] = value
            self.assertFalse(V.peer_passed(summary))
        for value in (None, [], {}, True):
            summary = self.valid(); summary["launch_retention"] = value
            self.assertFalse(V.peer_passed(summary))
        summary = self.valid(); del summary["launch_retention"]
        self.assertFalse(V.peer_passed(summary))

    def test_launcher_retirement_requires_independent_seal_and_no_late_start(self):
        for field, value in (("passed", False), ("faults", ["after_commit"]),
                             ("late_start_blocked", 1), ("late_start_blocked", False),
                             ("sealed_ports", True), ("sealed_ports", 1), ("start_calls", True),
                             ("start_calls", 3), ("wire_calls", True), ("wire_calls", 21)):
            summary = self.valid(); summary["launcher_retirement"][field] = value
            self.assertFalse(V.peer_passed(summary))
        for value in (None, [], {}, True):
            summary = self.valid(); summary["launcher_retirement"] = value
            self.assertFalse(V.peer_passed(summary))
        summary = self.valid(); del summary["launcher_retirement"]
        self.assertFalse(V.peer_passed(summary))

    def test_preinstalled_evidence_cannot_be_missing_or_coerced(self):
        for field, value in (("passed", False), ("ready", 1), ("fetch_hops", False), ("fetch_hops", 1),
                             ("parse_calls", False), ("parse_calls", 1), ("render_calls", True),
                             ("render_calls", 2), ("wire_calls", True), ("wire_calls", 10)):
            summary = self.valid(); summary["preinstalled"][field] = value
            self.assertFalse(V.peer_passed(summary))
        for value in (None, [], {}, True):
            summary = self.valid(); summary["preinstalled"] = value
            self.assertFalse(V.peer_passed(summary))

    def test_settlement_evidence_is_required_and_strict(self):
        for field, value in (("passed", False), ("settled", True), ("settled", 3),
                             ("wire_calls", True), ("wire_calls", 25),
                             ("modes", ["admission", "action", "control"])):
            summary = self.valid(); summary["relay_settlement"][field] = value
            self.assertFalse(V.peer_passed(summary))
        for value in (None, [], {}, True):
            summary = self.valid(); summary["relay_settlement"] = value
            self.assertFalse(V.peer_passed(summary))

    def test_partial_wrong_or_boolean_evidence_does_not_pass(self):
        for field, value in (("wire_calls", 25), ("fixture_calls", 50), ("archived_receipt", False), ("relay_epoch", True),
                             ("game_epoch", 0), ("effects", 1), ("profile", "legacy"), ("passed", False)):
            summary = self.valid()
            summary["epoch_binding"][field] = value
            self.assertFalse(V.peer_passed(summary))
        for value in (None, {}, {"passed": True, "epoch": False, "wire_calls": 9},
                      {"passed": True, "epoch": 0, "wire_calls": 8}):
            summary = self.valid(); summary["relay_epoch_profile"] = value
            self.assertFalse(V.peer_passed(summary))
        for field, value in (("passed", False), ("epoch", True), ("epoch", 0),
                             ("archive_removed", True), ("archive_removed", 0),
                             ("wire_calls", True), ("wire_calls", 12)):
            summary = self.valid(); summary["relay_rotation"][field] = value
            self.assertFalse(V.peer_passed(summary))
        for value in (None, {}, []):
            summary = self.valid(); summary["relay_rotation"] = value
            self.assertFalse(V.peer_passed(summary))


if __name__ == "__main__":
    unittest.main()
