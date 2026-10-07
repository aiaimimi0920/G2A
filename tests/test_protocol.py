"""不调用模型或旧 Mot 服务的协议行为与真实 HTTP 测试。"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from g2a.client import Client
from g2a.http import serve, strict_json
from g2a.runtime import GameHost
from g2a.validation import ProtocolError, validate


def descriptor():
    return dict(protocol="0.1.0-dev", game_id="game-a", name="钥匙探险", bindings=["http-poll"],
        avatar_formats=["text", "image"], presentation="hide_desktop", policy={"spoilers": "avoid_unknown"},
        actions=[dict(name="find-key", description="精灵探索钥匙", timeout_ms=5000,
            parameters={"type": "object", "properties": {"room": {"type": "string"}}, "required": ["room"], "additionalProperties": False})])


def join_request():
    return dict(protocol="0.1.0-dev", agent_id="companion-a", player_id="player-a",
        default_avatar={"id": "fox", "format": "text", "label": "小狐狸"}, desktop_visible=True,
        user_policy={"spoilers": "allow"}, allowed_actions=["find-key"])


def message(ident, kind, data, sender="companion-a"):
    return dict(id=ident, type=kind, sender=sender, data=data)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.host = GameHost(descriptor(), clock=lambda: self.now)
        self.invite = self.host.invite("companion-a", "player-a", team=["player-b"], allowed_actions=["find-key"])
        joined = self.host.join(self.invite, join_request())
        self.sid, self.token = joined["session"]["id"], joined["session_token"]

    def send(self, msg, game=False):
        return self.host.send(self.sid, self.host.admin_token if game else self.token, msg)

    def assert_error(self, code, fn):
        with self.assertRaises(ProtocolError) as error:
            fn()
        self.assertEqual(code, error.exception.code)

    def request(self, ident="action-1"):
        return message(ident, "action.request", {"action": "find-key", "arguments": {"room": "hall"}, "capability_revision": self.host.revision})

    def test_policy_override_does_not_grant_action(self):
        snapshot = self.host.poll(self.sid, self.token)["session"]
        self.assertEqual(snapshot["policy"]["spoilers"], "allow")
        request = self.request()
        request["data"]["action"] = "reveal-boss"
        self.assert_error("permission_denied", lambda: self.send(request))

    def test_user_can_restrict_invitation_permissions(self):
        other = GameHost(descriptor())
        invitation = other.invite("companion-a", "player-a", allowed_actions=["find-key"])
        req = join_request(); req["allowed_actions"] = []
        self.assertEqual(other.join(invitation, req)["session"]["allowed_actions"], [])

    def test_join_retry_and_identity_binding(self):
        self.assertEqual(self.host.join(self.invite, join_request())["session"]["id"], self.sid)
        req = join_request(); req["player_id"] = "player-b"
        self.assert_error("permission_denied", lambda: self.host.join(self.invite, req))
        req = join_request(); req["desktop_visible"] = False
        self.assert_error("invitation_used", lambda: self.host.join(self.invite, req))

    def test_unsupported_version(self):
        req = join_request(); req["protocol"] = "1.0"
        self.assert_error("version_not_supported", lambda: self.host.join(self.invite, req))

    def test_avatar_priority_and_incompatibility(self):
        d = descriptor(); d["game_avatar"] = {"id": "fairy", "format": "image", "label": "精灵"}
        h = GameHost(d)
        inv = h.invite("companion-a", "player-a")
        r = join_request(); r["forced_avatar"] = {"id": "fox-3d", "format": "model", "label": "狐狸"}
        self.assert_error("avatar_incompatible", lambda: h.join(inv, r))
        self.assertEqual(len(h.sessions), 0)
        r["forced_avatar"] = r["default_avatar"]
        self.assertEqual(h.join(inv, r)["session"]["avatar"]["id"], "fox")
        h2 = GameHost(d)
        inv2 = h2.invite("companion-a", "player-a")
        self.assertEqual(h2.join(inv2, join_request())["session"]["avatar"]["id"], "fairy")

    def test_normal_exit_restore_both_original_states(self):
        self.assertFalse(self.host.poll(self.sid, self.token)["session"]["desktop_visible"])
        self.assertTrue(self.host.leave(self.sid, self.token, "exit")["desktop_visible"])
        self.assertTrue(self.host.leave(self.sid, self.token, "again")["desktop_visible"])
        h = GameHost(descriptor()); inv = h.invite("companion-a", "player-a")
        r = join_request(); r["desktop_visible"] = False
        j = h.join(inv, r)
        self.assertFalse(h.leave(j["session"]["id"], j["session_token"], "exit")["desktop_visible"])

    def test_lease_expiry_cannot_be_revived(self):
        self.now = 31
        self.assertEqual(self.host.poll(self.sid, self.token)["session"]["state"], "closed")
        self.assert_error("session_closed", lambda: self.send(self.request()))
        self.assert_error("session_closed", lambda: self.host.join(self.invite, join_request()))

    def test_expired_unpolled_session_does_not_block_new_invitation(self):
        self.now = 31
        invite = self.host.invite("companion-a", "player-a", allowed_actions=["find-key"])
        new = self.host.join(invite, join_request())
        self.assertNotEqual(new["session"]["id"], self.sid)
        self.assertEqual(self.host.sessions[self.sid].state, "closed")

    def test_sender_and_result_spoofing(self):
        r = self.request(); r["sender"] = "another-agent"
        self.assert_error("permission_denied", lambda: self.send(r))
        r = message("r", "action.result", {"request_id": "x", "status": "succeeded", "details": {}})
        self.assert_error("permission_denied", lambda: self.send(r))

    def test_duplicate_and_conflicting_messages(self):
        r = self.request()
        with ThreadPoolExecutor(max_workers=8) as pool:
            receipts = list(pool.map(lambda _: self.send(r), range(16)))
        self.assertEqual(len({x["sequence"] for x in receipts}), 1)
        self.assertEqual(len(self.host.sessions[self.sid].actions), 1)
        r["data"]["arguments"]["room"] = "other"
        self.assert_error("id_conflict", lambda: self.send(r))

    def test_game_claim_only_once(self):
        self.send(self.request())
        claim = lambda: self.host.claim_action(self.sid, self.host.admin_token, "action-1")
        self.assertEqual(claim()["state"], "executing")
        self.assert_error("not_executable", claim)

    def test_dynamic_revoke_and_stale_request(self):
        old = self.request("old")
        self.send(self.request())
        self.send(message("revoke", "capability.update", {"actions": []}, "game-a"), game=True)
        self.assert_error("not_executable", lambda: self.host.claim_action(self.sid, self.host.admin_token, "action-1"))
        self.assert_error("stale_capabilities", lambda: self.send(old))

    def test_cancellation_is_request_not_success(self):
        self.send(self.request())
        self.send(message("cancel", "action.cancel", {"request_id": "action-1"}))
        action = self.host.sessions[self.sid].actions["action-1"]
        self.assertEqual(action["state"], "pending")
        self.assertTrue(action["cancel_requested"])
        self.assert_error("not_executable", lambda: self.host.claim_action(self.sid, self.host.admin_token, "action-1"))
        self.send(message("result", "action.result", {"request_id": "action-1", "status": "cancelled", "details": {}}, "game-a"), game=True)
        self.assertEqual(action["state"], "cancelled")

    def test_timeout_unknown_not_failed_or_reexecuted(self):
        self.send(self.request())
        self.now = 6
        value = self.host.poll(self.sid, self.token)
        self.assertEqual(value["events"][-1]["message"]["data"]["status"], "unknown")
        self.assert_error("not_executable", lambda: self.host.claim_action(self.sid, self.host.admin_token, "action-1"))

    def test_recipient_filtering(self):
        data = {"text": "队伍消息", "channel": "team", "recipients": ["player-b"]}
        self.send(message("team", "chat.message", data, "player-a"), game=True)
        self.assertEqual(self.host.poll(self.sid, self.token)["events"], [])
        data["channel"] = "private"
        self.assert_error("permission_denied", lambda: self.send(message("bad", "chat.message", data)))

    def test_proactive_team_chat_and_provenance(self):
        data = {"text": "你之前告诉过我这个结局", "channel": "team", "recipients": ["player-a", "player-b"],
                "provenance": {"kind": "player_report", "source_id": "conversation-1", "player_id": "player-a"}}
        self.send(message("proactive", "chat.message", data))
        event = self.host.poll(self.sid, self.host.admin_token)["events"][0]["message"]
        self.assertEqual(event["data"]["provenance"]["kind"], "player_report")
        data["provenance"]["player_id"] = "player-b"
        self.assert_error("permission_denied", lambda: self.send(message("cross-player", "chat.message", data)))

    def test_external_reference_not_relabelled_as_game_observation(self):
        data = {"summary": "攻略内容", "facts": {}, "provenance": {"kind": "external_reference", "source_id": "book", "player_id": "player-a"}}
        self.assert_error("invalid_provenance", lambda: self.send(message("context", "game.context", data, "game-a"), game=True))

    def test_parameter_validation_and_no_external_schema_fetch(self):
        r = self.request(); r["data"]["arguments"] = {"room": 3}
        self.assert_error("invalid_arguments", lambda: self.send(r))
        a = descriptor()["actions"]; a[0]["parameters"] = {"$ref": "http://127.0.0.1/private"}
        self.assert_error("invalid_capabilities", lambda: self.send(message("update", "capability.update", {"actions": a}, "game-a"), game=True))

    def test_cursor_gap_and_batching(self):
        for i in range(260):
            self.send(message(str(i), "chat.message", {"text": "hi", "channel": "private", "recipients": ["player-a"]}))
        self.assert_error("cursor_expired", lambda: self.host.poll(self.sid, self.host.admin_token, 0))
        page = self.host.poll(self.sid, self.host.admin_token, 4)
        self.assertEqual(len(page["events"]), 32)
        self.assertEqual(page["cursor"], 36)

    def test_unknown_session_does_not_leak_existence(self):
        self.assert_error("unauthenticated", lambda: self.host.poll("missing", "bad"))
        self.assert_error("unauthenticated", lambda: self.host.poll(self.sid, "bad"))


class HttpTests(unittest.TestCase):
    def test_real_transport_event_action_result_and_restore(self):
        h = GameHost(descriptor())
        invite = h.invite("companion-a", "player-a", allowed_actions=["find-key"])
        with serve(h) as url:
            c = Client(url, expected_game_id="game-a")
            c.join(invite, join_request())
            self.assertFalse(c.desktop_visible)
            sid = c.session["id"]
            context = {"summary": "钥匙在大厅", "facts": {"room": "hall"}, "provenance": {"kind": "shared_experience", "source_id": "event-1", "player_id": "player-a"}}
            c.call(f"/sessions/{sid}/events", message("world", "game.context", context, "game-a"), h.admin_token)
            self.assertEqual(c.poll()["events"][0]["message"]["type"], "game.context")
            c.send("action.request", {"action": "find-key", "arguments": {"room": "hall"}, "capability_revision": 1}, message_id="a")
            claimed = c.call(f"/sessions/{sid}/actions/a/claim", {}, h.admin_token)
            self.assertEqual(claimed["action"], "find-key")
            c.call(f"/sessions/{sid}/events", message("result", "action.result", {"request_id": "a", "status": "succeeded", "details": {"key": "gold"}}, "game-a"), h.admin_token)
            self.assertEqual(c.poll()["events"][0]["message"]["data"]["status"], "succeeded")
            c.leave()
            self.assertTrue(c.desktop_visible)

    def test_auth_origin_and_bad_json(self):
        h = GameHost(descriptor())
        with serve(h) as url:
            for path,body,headers,code in [
                ("/sessions", b'{}', {}, 401),
                ("/sessions", b'{}', {"Origin": "https://evil.example"}, 403),
                ("/sessions", b'{"x":1,"x":2}', {}, 400),
                ("/sessions", b'x'*65537, {}, 413),
            ]:
                req = Request(url+path, body, {"Content-Type": "application/json", **headers})
                with self.assertRaises(HTTPError) as error:
                    urlopen(req, timeout=5)
                self.assertEqual(error.exception.code, code)

    def test_crash_lease_restore_without_remote_reply(self):
        now = [0]
        h = GameHost(descriptor())
        invite = h.invite("companion-a", "player-a")
        with serve(h) as url:
            c = Client(url, expected_game_id="game-a", clock=lambda: now[0])
            c.join(invite, join_request())
            self.assertFalse(c.desktop_visible)
        now[0] = 31
        self.assertTrue(c.check_lease())
        self.assertTrue(c.desktop_visible)

    def test_poll_reapplies_presentation_after_local_lease_fallback(self):
        now = [0]
        h = GameHost(descriptor(), clock=lambda: now[0])
        invite = h.invite("companion-a", "player-a")
        with serve(h) as url:
            c = Client(url, expected_game_id="game-a", clock=lambda: now[0])
            c.join(invite, join_request())
            now[0] = 20
            c.send("chat.message", {"text": "still here", "channel": "private", "recipients": ["player-a"]})
            now[0] = 31
            self.assertTrue(c.check_lease())
            self.assertTrue(c.desktop_visible)
            self.assertEqual(c.poll()["session"]["state"], "active")
            self.assertFalse(c.desktop_visible)

    def test_action_query_preserves_result_after_cursor_loss(self):
        h = GameHost(descriptor())
        inv = h.invite("companion-a", "player-a", allowed_actions=["find-key"])
        with serve(h) as url:
            c = Client(url, expected_game_id="game-a")
            c.join(inv, join_request()); sid = c.session["id"]
            c.send("action.request", {"action": "find-key", "arguments": {"room": "hall"}, "capability_revision": 1}, message_id="a")
            c.call(f"/sessions/{sid}/events", message("r", "action.result", {"request_id": "a", "status": "succeeded", "details": {"key": "gold"}}, "game-a"), h.admin_token)
            for i in range(260):
                h.send(sid, c.token, message(str(i), "chat.message", {"text": "hi", "channel": "private", "recipients": ["player-a"]}))
            with self.assertRaises(ProtocolError): c.poll()
            result = c.call(f"/sessions/{sid}/actions/a", token=c.token)
            self.assertEqual(result["state"], "succeeded")
            self.assertEqual(result["details"], {"key": "gold"})

    def test_strict_json_rejects_nonfinite_and_arrays(self):
        for raw in [b'{"x":NaN}', b'{"x":Infinity}', b'[]', b'null']:
            with self.assertRaises(ValueError): strict_json(raw)

    def test_client_rejects_unsafe_plaintext_and_wrong_game(self):
        with self.assertRaises(ValueError): Client("http://example.com", expected_game_id="a")
        with serve(GameHost(descriptor())) as url:
            c = Client(url, expected_game_id="not-game-a")
            with self.assertRaises(ProtocolError) as error:
                c.join("unused", join_request())
            self.assertEqual(error.exception.code, "wrong_game")


if __name__ == "__main__":
    unittest.main()
