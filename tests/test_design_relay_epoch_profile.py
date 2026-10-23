"""现有 Relay 五操作接入固定代次 profile，不静默升级旧请求。"""

from copy import deepcopy
import unittest
from test_design_relay import H, F

C = H.C


class RelayEpochProfileTests(unittest.TestCase):
    def setUp(self):
        self.f = F.relay_fixture()
        self.f["relay_epoch_profile"] = 0
        self.f["relay_pairing_epochs"] = {"pairing-fixture": 0}
        self.h = H.RelayHarness(self.f)
        self.registration = {"instance": deepcopy(self.f["scope"]["instance"]),
            "relay_identity": deepcopy(self.f["scope"]["binding"]["relay_identity"]),
            "relay_origin": self.f["relay_origin"], "agent_principals": [deepcopy(self.f["agent"])],
            "control_principals": [deepcopy(self.f["player"])], "registration_expiry": 90000,
            "pairing_proof_ref": "pairing-fixture", "limits": deepcopy(self.f["scope"]["limits"])}

    def send(self, operation, payload, credential, *, rid="request", extensions=None, fault=None):
        request = F.wire_request(operation, payload, rid)
        request["extensions"] = deepcopy(self.h.epoch_extensions if extensions is None else extensions)
        return C.codec.decode(self.h.submit(C.codec.canonical(request), credential, now=1000, fault=fault))

    def register(self):
        result = self.send("relay.register", self.registration, "relay-player-identity", rid="register")["result"]
        self.mid = result["mailbox_id"]
        self.tokens = {role: self.h.credential_for(self.mid, "relay-" + role + "-identity", now=1000)
                       for role in ("agent", "game", "player")}
        return result

    def rejected(self, code, call):
        with self.assertRaises(C.ContractError) as raised:
            call()
        self.assertEqual(raised.exception.code, code)

    def queued_claim(self):
        inner = F.wire_request("describe", {"instance": self.f["scope"]["instance"]}, "inner")
        call = {"mailbox_id": self.mid, "call": {"relay_request_id": "call", "operation_request": inner,
            "inner_auth_proof": "inner-agent-fixture", "deadline": 20000, "route_revision": 1}}
        self.assertEqual(self.send("relay.call", call, self.tokens["agent"])["result"]["state"], "queued")
        claim = self.send("relay.pull", {"mailbox_id": self.mid, "pull_nonce": "pull", "maximum_items": 1},
                          self.tokens["game"], rid="pull")["result"]["claims"][0]
        return call, claim

    def test_profile_runs_register_call_pull_dispatch_reply_and_revoke(self):
        self.assertEqual(self.register()["mailbox_id"], "mailbox-e0-1")
        call, claim = self.queued_claim()
        reply = C.codec.decode(self.h.dispatch_claim(C.codec.canonical(claim), self.tokens["game"], now=1000))
        self.assertIn("result", reply)
        self.send("relay.reply", {"mailbox_id": self.mid, "claim_id": claim["claim_id"], "reply": reply}, self.tokens["game"])
        self.assertEqual(self.send("relay.call", call, self.tokens["agent"])["result"]["reply"], reply)
        result = self.send("relay.revoke", {"mailbox_id": self.mid, "expected_route_revision": 1}, "relay-player-identity")["result"]
        self.assertEqual(result["state"], "closed")

    def test_missing_or_downgraded_profile_cannot_register(self):
        self.rejected("feature_unsupported", lambda: self.send("relay.register", self.registration, "relay-player-identity", extensions={}))
        changed = deepcopy(self.h.epoch_extensions)
        changed[self.h.EPOCH_EXTENSION]["required"] = False
        self.rejected("approval_stale", lambda: self.send("relay.register", self.registration, "relay-player-identity", extensions=changed))
        self.assertEqual(self.h.state["mailboxes"], {})

    def test_wrong_epoch_instance_operator_origin_or_version_cannot_select_profile(self):
        for field, value in (("epoch", 1), ("epoch", False), ("instance", {}),
                             ("relay_identity", {}), ("relay_origin", "https://other.invalid"), ("profile", "legacy")):
            changed = deepcopy(self.h.epoch_extensions)
            changed[self.h.EPOCH_EXTENSION]["value"][field] = value
            self.rejected("approval_stale", lambda: self.send("relay.register", self.registration, "relay-player-identity", extensions=changed))
        changed = deepcopy(self.h.epoch_extensions)
        changed[self.h.EPOCH_EXTENSION]["version"] = "2"
        self.rejected("approval_stale", lambda: self.send("relay.register", self.registration, "relay-player-identity", extensions=changed))

    def test_legacy_endpoint_does_not_ignore_required_epoch_extension(self):
        extensions = deepcopy(self.h.epoch_extensions)
        legacy = deepcopy(self.f); del legacy["relay_epoch_profile"]
        self.h = H.RelayHarness(legacy)
        self.rejected("feature_unsupported", lambda: self.send("relay.register", self.registration, "relay-player-identity", extensions=extensions))
        self.assertEqual(self.register()["mailbox_id"], "mailbox-1")

    def test_stop_operations_require_identity_binding_too(self):
        self.register()
        payload = {"object_type": "relay", "object_id": self.mid, "expected_revision": 1}
        self.rejected("feature_unsupported", lambda: self.send("permission.revoke", payload, "relay-player-identity", extensions={}))
        self.assertEqual(self.send("permission.revoke", payload, "relay-player-identity")["result"]["state"], "closed")

    def test_foreign_epoch_claim_rejected_at_game_port_before_dispatch(self):
        self.register(); _, claim = self.queued_claim()
        record = next(iter(self.h.state["mailboxes"][self.mid]["requests"].values()))
        binding = {key: deepcopy(record[key]) for key in ("principal", "outer_role", "inner_role")}
        fresh = deepcopy(self.f); fresh["relay_epoch_profile"] = 1
        other = H.RelayHarness(fresh, game=self.h.game)
        self.rejected("request_gone", lambda: other.port.dispatch(claim, binding, now=1000))
        self.assertEqual(other.port.dispatch_calls, 0)
        self.assertEqual(other.port.journal, {})

    def test_profile_and_namespace_survive_restart_and_commit_fault(self):
        with self.assertRaises(H.InjectedFailure):
            self.send("relay.register", self.registration, "relay-player-identity", rid="register", fault="after_commit")
        self.h = self.h.restart_from_mock_ledger(now=1000)
        self.assertEqual(self.register()["mailbox_id"], "mailbox-e0-1")
        self.assertEqual(self.h.port.route_epoch, 0)
        self.rejected("feature_unsupported", lambda: self.send("relay.register", self.registration, "relay-player-identity", rid="register", extensions={}))

    def test_pairing_requires_independent_trusted_epoch_binding(self):
        for mapping in ({}, {"pairing-fixture": 1}, {"pairing-fixture": False}):
            fixture = deepcopy(self.f); fixture["relay_pairing_epochs"] = mapping
            self.h = H.RelayHarness(fixture)
            self.rejected("permission_denied", self.register)
            self.assertEqual(self.h.state["mailboxes"], {})

    def test_profile_configuration_requires_exact_nonnegative_integer(self):
        for value in (True, -1, None, "1"):
            fixture = deepcopy(self.f); fixture["relay_epoch_profile"] = value
            with self.assertRaises(C.ContractError):
                H.RelayHarness(fixture)


if __name__ == "__main__":
    unittest.main()
