"""Exhaustive role gate checks; independent of models and external services."""
from copy import deepcopy
import unittest

from g2a.authority import MESSAGE_ROLES, require_message_role
from g2a.runtime import GameHost
from g2a.validation import ProtocolError, SCHEMA
from test_protocol import descriptor, join_request, message


class MessageAuthorityTests(unittest.TestCase):
    def test_matrix_matches_every_wire_message(self):
        kinds = {item["properties"]["type"]["const"]
                 for item in SCHEMA["$defs"]["message"]["oneOf"]}
        self.assertEqual(kinds, set(MESSAGE_ROLES))

    def test_roles_are_explicit_and_unknowns_fail_closed(self):
        expected = {
            "game.context": {"game"}, "chat.message": {"game", "agent"},
            "action.request": {"agent"}, "action.result": {"game"},
            "capability.update": {"game"}, "action.cancel": {"agent"},
        }
        for kind in [*expected, "future.message"]:
            for role in ("game", "agent", "player", "unknown"):
                with self.subTest(kind=kind, role=role):
                    if role in expected.get(kind, set()):
                        require_message_role(kind, role)
                    else:
                        with self.assertRaises(ProtocolError) as caught:
                            require_message_role(kind, role)
                        self.assertEqual(caught.exception.code, "permission_denied")
                        self.assertEqual(caught.exception.status, 403)

    def test_host_rejects_wrong_role_without_mutating_authority_or_events(self):
        data = {
            "game.context": {"summary": "visible", "facts": {}, "provenance": {
                "kind": "shared_experience", "source_id": "e", "player_id": "player-a"}},
            "capability.update": {"actions": []},
            "action.result": {"request_id": "missing", "status": "succeeded", "details": {}},
            "action.request": {"action": "find-key", "arguments": {"room": "hall"},
                               "capability_revision": 1},
            "action.cancel": {"request_id": "missing"},
        }
        for kind, body in data.items():
            with self.subTest(kind=kind):
                host = GameHost(descriptor(), clock=lambda: 0)
                inv = host.invite("companion-a", "player-a", allowed_actions=["find-key"])
                joined = host.join(inv, join_request())
                sid = joined["session"]["id"]
                wrong_game = kind in {"action.request", "action.cancel"}
                token = host.admin_token if wrong_game else joined["session_token"]
                sender = "game-a" if wrong_game else "companion-a"
                before = deepcopy(host.sessions[sid])
                with self.assertRaises(ProtocolError) as caught:
                    host.send(sid, token, message("denied", kind, body, sender))
                self.assertEqual(caught.exception.code, "permission_denied")
                self.assertEqual(host.sessions[sid], before)
                self.assertEqual(host.revision, 1)
                self.assertEqual(host.descriptor, descriptor())


if __name__ == "__main__":
    unittest.main()
