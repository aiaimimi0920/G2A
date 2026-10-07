"""独立于 Mot 的最小回环演示；不需要账号、模型或网络业务服务。"""
import json

from g2a.client import Client
from g2a.http import serve
from g2a.runtime import GameHost


def main():
    descriptor = dict(protocol="0.1.0-dev", game_id="key-quest", name="钥匙探险",
        bindings=["http-poll"], avatar_formats=["text"], presentation="hide_desktop",
        policy={"spoilers": "avoid_unknown", "proactive_actions": True},
        actions=[dict(name="find-key", description="探索房间中的钥匙", timeout_ms=5000,
            parameters={"type": "object", "properties": {"room": {"enum": ["hall"]}},
                        "required": ["room"], "additionalProperties": False})])
    host = GameHost(descriptor)
    invitation = host.invite("fox", "alice", team=["bob"], allowed_actions=["find-key"])
    with serve(host) as endpoint:
        agent = Client(endpoint, expected_game_id="key-quest")
        agent.join(invitation, dict(protocol="0.1.0-dev", agent_id="fox", player_id="alice",
            default_avatar={"id": "fox", "format": "text", "label": "小狐狸"}, desktop_visible=True,
            user_policy={"spoilers": "allow"}, allowed_actions=["find-key"]))
        sid = agent.session["id"]
        agent.call(f"/sessions/{sid}/events", dict(id="observed-hall", type="game.context", sender="key-quest",
            data={"summary": "玩家正在挡住怪，大厅有钥匙", "facts": {"room": "hall"},
                  "provenance": {"kind": "shared_experience", "source_id": "hall-1", "player_id": "alice"}}), host.admin_token)
        agent.poll()
        agent.send("chat.message", {"text": "你撑一下，我去拿钥匙。", "channel": "team", "recipients": ["alice", "bob"]})
        agent.send("action.request", {"action": "find-key", "arguments": {"room": "hall"}, "capability_revision": 1}, message_id="find-1")
        claim = agent.call(f"/sessions/{sid}/actions/find-1/claim", {}, host.admin_token)
        # 这是演示游戏的确定性规则，不是 Agent 谎报完成；实际游戏在此执行世界逻辑。
        assert claim["arguments"]["room"] == "hall"
        agent.call(f"/sessions/{sid}/events", dict(id="found-1", type="action.result", sender="key-quest",
            data={"request_id": "find-1", "status": "succeeded", "details": {"item": "gold-key"}}), host.admin_token)
        result = agent.poll()["events"][-1]["message"]["data"]
        agent.leave()
        print(json.dumps({"action_result": result, "desktop_restored": agent.desktop_visible,
                          "mot_services_used": False, "real_http": True}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
