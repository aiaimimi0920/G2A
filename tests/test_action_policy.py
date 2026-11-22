from copy import deepcopy
from pathlib import Path
import runpy
import unittest

from g2a.runtime import GameHost
from g2a.validation import ProtocolError
from test_protocol import descriptor, join_request, message


class ActionPolicyTests(unittest.TestCase):
    def host(self, constraints):
        host = GameHost(descriptor(), clock=lambda: 0)
        token = host.invite("companion-a", "player-a", allowed_actions=["find-key"],
                            action_constraints=constraints)
        joined = host.join(token, join_request())
        return host, joined["session"]["id"], joined["session_token"]

    def request(self, host, sid, token, room="hall", ident="req"):
        return host.send(sid, token, message(ident, "action.request", dict(
            action="find-key", arguments={"room": room}, capability_revision=1)))

    def test_parameter_scope_denies_before_acceptance(self):
        host, sid, token = self.host({"find-key": {"properties": {"room": {"const": "hall"}}}})
        before = deepcopy(host.sessions[sid])
        with self.assertRaises(ProtocolError) as caught:
            self.request(host, sid, token, "vault")
        self.assertEqual(caught.exception.code, "permission_denied")
        self.assertEqual(host.sessions[sid], before)
        self.request(host, sid, token)
        self.assertEqual(host.claim_action(sid, host.admin_token, "req")["state"], "executing")

    def test_tightening_rechecked_at_claim_and_cannot_be_widened(self):
        host, sid, token = self.host({})
        self.request(host, sid, token)
        host.restrict_action(sid, "find-key", False)
        host.restrict_action(sid, "find-key", True)
        with self.assertRaises(ProtocolError) as caught:
            host.claim_action(sid, host.admin_token, "req")
        self.assertEqual(caught.exception.code, "not_executable")
        self.assertEqual(host.sessions[sid].actions["req"]["state"], "pending")
        with self.assertRaises(ProtocolError):
            self.request(host, sid, token, ident="new")

    def test_caller_mutation_does_not_widen_frozen_policy(self):
        constraints = {"find-key": False}
        host, sid, token = self.host(constraints)
        constraints["find-key"] = True
        with self.assertRaises(ProtocolError):
            self.request(host, sid, token)

    def test_invitation_and_tightening_freeze_nested_schemas(self):
        host = GameHost(descriptor(), clock=lambda: 0)
        rule = {"properties": {"room": {"const": "hall"}}}
        inv = host.invite("companion-a", "player-a", allowed_actions=["find-key"],
                          action_constraints={"find-key": rule})
        rule["properties"]["room"]["const"] = "vault"
        joined = host.join(inv, join_request())
        sid, token = joined["session"]["id"], joined["session_token"]
        self.request(host, sid, token)
        with self.assertRaises(ProtocolError):
            self.request(host, sid, token, "vault", "vault")
        rule = {"not": {"properties": {"room": {"const": "hall"}}}}
        host.restrict_action(sid, "find-key", rule)
        rule.clear()
        with self.assertRaises(ProtocolError):
            host.claim_action(sid, host.admin_token, "req")

    def test_constraints_do_not_grant_capabilities_or_fetch_references(self):
        for constraints in ({"undeclared": True}, {"find-key": {"$ref": "https://example.invalid/schema"}},
                            {"find-key": {"type": "not-a-json-type"}},
                            {"find-key": {"minimum": float("nan")}},
                            {"find-key": {"pattern": "["}}):
            with self.subTest(constraints=constraints), self.assertRaises(ProtocolError):
                self.host(constraints)

    def test_invalid_tightening_preserves_existing_policy_and_pending_action(self):
        host, sid, token = self.host({})
        self.request(host, sid, token)
        before = deepcopy(host.sessions[sid])
        with self.assertRaises(ProtocolError):
            host.restrict_action(sid, "find-key", {"properties": []})
        self.assertEqual(host.sessions[sid], before)
        host.claim_action(sid, host.admin_token, "req")

    def test_remote_join_cannot_inject_local_policy(self):
        host = GameHost(descriptor())
        inv = host.invite("companion-a", "player-a", allowed_actions=["find-key"])
        req = join_request(); req["action_constraints"] = {"find-key": True}
        with self.assertRaises(ProtocolError) as caught:
            host.join(inv, req)
        self.assertEqual(caught.exception.code, "invalid_message")
        self.assertEqual(host.sessions, {})

    def test_other_sessions_remain_independent(self):
        host, sid, token = self.host({})
        inv = host.invite("companion-b", "player-b", allowed_actions=["find-key"])
        req = join_request(); req.update(agent_id="companion-b", player_id="player-b")
        other = host.join(inv, req)
        host.restrict_action(sid, "find-key", False)
        host.send(other["session"]["id"], other["session_token"], message("other", "action.request", dict(
            action="find-key", arguments={"room": "hall"}, capability_revision=1), "companion-b"))

    def test_real_http_observation_action_and_revocation(self):
        demo = runpy.run_path(str(Path(__file__).resolve().parents[1] / "examples/scoped_observation.py"))
        result = demo["run_demo"]()
        self.assertEqual(result["observation"], {"room": "hall", "visible_items": ["key"]})
        self.assertEqual(result["action_result"], {"item": "key"})
        self.assertEqual(result["effects"], ["key_taken"])
        self.assertEqual(result["denied_actions"], ["observe", "take-key"])
        self.assertEqual(result["pending_after_revoke"], "not_executable")


if __name__ == "__main__":
    unittest.main()
