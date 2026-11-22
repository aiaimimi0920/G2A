"""Installable SDK + real HTTP: game-owned perception and bounded actions.

No model, design harness, credentials, engine or Mot service is required.
"""
from copy import deepcopy
import json

from g2a.client import Client
from g2a.http import serve
from g2a.runtime import GameHost
from g2a.validation import ProtocolError


def run_demo():
    parameters = {"type": "object", "properties": {"room": {"type": "string"}},
                  "required": ["room"], "additionalProperties": False}
    descriptor = dict(protocol="0.1.0-dev", game_id="bounded-game", name="Bounded game",
        bindings=["http-poll"], avatar_formats=["text"], presentation="coexist", policy={},
        actions=[dict(name=name, description=name, parameters=parameters, timeout_ms=5000)
                 for name in ("observe", "take-key")])
    # The game retains full state; neither discovery nor the Agent gets this object.
    world = {"hall": {"visible_items": ["key"], "hidden_trap": "west wall"},
             "vault": {"visible_items": ["treasure"], "secret_code": "not disclosed"}}
    host = GameHost(descriptor)
    room_limit = {"properties": {"room": {"const": "hall"}}}
    invitation = host.invite("fox", "alice", allowed_actions=["observe", "take-key"],
                             action_constraints={name: room_limit for name in ("observe", "take-key")})
    effects = []
    with serve(host) as endpoint:
        agent = Client(endpoint, expected_game_id="bounded-game")
        agent.join(invitation, dict(protocol="0.1.0-dev", agent_id="fox", player_id="alice",
            default_avatar={"id": "fox", "format": "text", "label": "Fox"}, desktop_visible=True,
            user_policy={}, allowed_actions=["observe", "take-key"]))
        sid = agent.session["id"]

        def request(ident, name, room):
            return agent.send("action.request", dict(action=name, arguments={"room": room},
                                                     capability_revision=1), message_id=ident)

        def execute(ident):
            # A real game executor holds admin authority, never the Agent process.
            claim = host.claim_action(sid, host.admin_token, ident)
            room = claim["arguments"]["room"]
            if claim["action"] == "observe":
                # Explicit projection: hidden state is not sent for an LLM to redact.
                details = {"room": room, "visible_items": deepcopy(world[room]["visible_items"])}
            else:
                world[room]["visible_items"].remove("key")
                effects.append("key_taken")
                details = {"item": "key"}
            host.send(sid, host.admin_token, dict(id="result-" + ident, type="action.result",
                sender="bounded-game", data=dict(request_id=ident, status="succeeded", details=details)))
            return agent.call(f"/sessions/{sid}/actions/{ident}", token=agent.token)["details"]

        denied = []
        for name in ("observe", "take-key"):
            try:
                request("forbidden-" + name, name, "vault")
            except ProtocolError as error:
                assert error.code == "permission_denied"
                denied.append(name)
            else:
                raise AssertionError("Out-of-scope request was accepted")
        request("view", "observe", "hall")
        observation = execute("view")
        request("take", "take-key", "hall")
        result = execute("take")
        request("queued-view", "observe", "hall")
        host.restrict_action(sid, "observe", False)
        try:
            execute("queued-view")
        except ProtocolError as error:
            assert error.code == "not_executable"
        else:
            raise AssertionError("Tightened grant allowed a pending request")
        agent.leave()
    return {"observation": observation, "action_result": result, "effects": effects,
            "denied_actions": denied, "pending_after_revoke": "not_executable",
            "real_http": True, "policy": "game-local; unchanged 0.1.0-dev wire"}


if __name__ == "__main__":
    print(json.dumps(run_demo(), ensure_ascii=False, indent=2))
