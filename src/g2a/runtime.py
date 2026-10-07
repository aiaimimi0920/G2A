"""游戏权威的内存参考宿主；不执行游戏动作，也不保存 Agent 记忆。"""
from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
import secrets
import threading
import time
import uuid

from jsonschema import Draft202012Validator, SchemaError

from .validation import ProtocolError, validate


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def action_map(actions):
    result = {}
    for action in actions:
        if action["name"] in result:
            raise ProtocolError("invalid_capabilities", "Duplicate action name")
        try:
            Draft202012Validator.check_schema(action["parameters"])
        except SchemaError:
            raise ProtocolError("invalid_capabilities", "Invalid action parameter schema") from None
        # 参考宿主不进行网络 schema 解析，避免游戏提供的引用触发 SSRF。
        def references(value):
            if isinstance(value, dict):
                return any(k in {"$ref", "$dynamicRef"} or references(v) for k, v in value.items())
            return isinstance(value, list) and any(references(v) for v in value)
        if references(action["parameters"]):
            raise ProtocolError("invalid_capabilities", "Reference schemas are not supported by this binding")
        result[action["name"]] = deepcopy(action)
    return result


@dataclass
class Session:
    id: str
    token: str
    agent: str
    player: str
    team: set
    permissions: set
    policy: dict
    avatar: dict
    desktop_before: bool
    desktop_during: bool
    last_seen: float
    state: str = "active"
    sequence: int = 0
    events: deque = field(default_factory=lambda: deque(maxlen=256))
    accepted: dict = field(default_factory=dict)
    actions: dict = field(default_factory=dict)


class GameHost:
    def __init__(self, descriptor, *, lease_seconds=30, clock=time.monotonic):
        validate("descriptor", descriptor)
        self.descriptor = deepcopy(descriptor)
        self.capabilities = action_map(descriptor["actions"])
        if not 0 < lease_seconds <= 300:
            raise ValueError("Lease must be between zero and 300 seconds")
        self.revision = 1
        self.admin_token = secrets.token_urlsafe(32)
        self.lease_seconds = lease_seconds
        self.clock = clock
        self.sessions = {}
        self.invitations = {}
        self.lock = threading.RLock()

    def invite(self, agent_id, player_id, *, team=(), allowed_actions=(), ttl=120):
        """由宿主在用户确认或既有自动加入授权之后调用，不能由 Agent 自授。"""
        with self.lock:
            if len(self.invitations) >= 256:
                raise ProtocolError("resource_limit", "Invitation capacity reached", 429)
            if len({agent_id, player_id, self.descriptor["game_id"]}) != 3:
                raise ProtocolError("invalid_identity", "Roles require distinct identities")
            if not set(allowed_actions) <= self.capabilities.keys():
                raise ProtocolError("permission_denied", "Invitation exceeds game capabilities", 403)
            token = secrets.token_urlsafe(32)
            self.invitations[token] = dict(agent=agent_id, player=player_id, team=set(team) | {player_id},
                                           permissions=set(allowed_actions), expires=self.clock() + ttl,
                                           session=None, fingerprint=None)
            return token

    def join(self, token, request):
        with self.lock:
            invitation = self.invitations.get(token)
            if invitation is None or self.clock() >= invitation["expires"]:
                raise ProtocolError("unauthenticated", "Invalid invitation", 401)
            if request.get("protocol") != self.descriptor["protocol"]:
                raise ProtocolError("version_not_supported", "Protocol version does not match", 409)
            validate("join", request)
            if (request["agent_id"], request["player_id"]) != (invitation["agent"], invitation["player"]):
                raise ProtocolError("permission_denied", "Invitation identity mismatch", 403)
            mark = fingerprint(request)
            if invitation["session"]:
                if mark != invitation["fingerprint"]:
                    raise ProtocolError("invitation_used", "Invitation already bound", 409)
                s = self.sessions[invitation["session"]]
                self._tick(s)
                if s.state != "active":
                    raise ProtocolError("session_closed", "Invitation session has ended", 409)
                return self._joined(s)
            if len(self.sessions) >= 64:
                raise ProtocolError("resource_limit", "Session capacity reached", 429)
            for previous in self.sessions.values():
                self._tick(previous)
            if any(s.agent == request["agent_id"] and s.state == "active" for s in self.sessions.values()):
                raise ProtocolError("already_joined", "Agent already has an active session in this host", 409)
            selected = request.get("forced_avatar", self.descriptor.get("game_avatar", request["default_avatar"]))
            if selected["format"] not in self.descriptor["avatar_formats"]:
                raise ProtocolError("avatar_incompatible", "Selected avatar format is unsupported", 409)
            presentation = self.descriptor["presentation"]
            if presentation == "user_choice":
                presentation = request.get("preferred_presentation", "coexist")
            policy = dict(self.descriptor["policy"])
            policy.update(request["user_policy"])
            permissions = set(request["allowed_actions"]) & invitation["permissions"]
            s = Session(uuid.uuid4().hex, secrets.token_urlsafe(32), request["agent_id"], request["player_id"],
                        invitation["team"], permissions, policy, deepcopy(selected), request["desktop_visible"],
                        request["desktop_visible"] if presentation == "coexist" else False, self.clock())
            self.sessions[s.id] = s
            invitation.update(session=s.id, fingerprint=mark)
            return self._joined(s)

    def _joined(self, s):
        return dict(session=self.snapshot(s), session_token=s.token, lease_seconds=self.lease_seconds)

    def snapshot(self, s):
        return dict(id=s.id, state=s.state, game_id=self.descriptor["game_id"], agent_id=s.agent,
                    player_id=s.player, avatar=deepcopy(s.avatar), policy=deepcopy(s.policy),
                    desktop_visible=s.desktop_during if s.state == "active" else s.desktop_before,
                    restore_desktop_visible=s.desktop_before, capability_revision=self.revision,
                    allowed_actions=sorted(s.permissions & self.capabilities.keys()), sequence=s.sequence)

    def authorize(self, session_id, token):
        s = self.sessions.get(session_id)
        if not s or not token:
            raise ProtocolError("unauthenticated", "Invalid session credentials", 401)
        if secrets.compare_digest(token, s.token):
            return s, "agent"
        if secrets.compare_digest(token, self.admin_token):
            return s, "game"
        raise ProtocolError("unauthenticated", "Invalid session credentials", 401)

    def _emit(self, s, kind, data, audience, message=None):
        s.sequence += 1
        entry = dict(sequence=s.sequence, message=deepcopy(message) if message else
                     dict(id=uuid.uuid4().hex, type=kind, sender=self.descriptor["game_id"], data=deepcopy(data)))
        s.events.append((entry, audience))
        return s.sequence

    def _close(self, s, reason):
        if s.state == "closed":
            return
        s.state = "closed"
        for action in s.actions.values():
            if action["state"] not in {"succeeded", "failed", "cancelled", "unknown"}:
                action["state"] = "unknown"
        self._emit(s, "session.closed", {"reason": reason, "restore_desktop_visible": s.desktop_before}, {"agent", "game"})

    def _tick(self, s):
        if s.state == "active" and self.clock() - s.last_seen >= self.lease_seconds:
            self._close(s, "lease_expired")
        for ident, action in s.actions.items():
            if action["state"] in {"pending", "executing"} and self.clock() >= action["deadline"]:
                action["state"] = "unknown"
                self._emit(s, "action.expired", {"request_id": ident, "status": "unknown"}, {"agent", "game"})

    def poll(self, session_id, token, cursor=0):
        with self.lock:
            s, role = self.authorize(session_id, token)
            self._tick(s)
            if cursor < 0 or cursor > s.sequence:
                raise ProtocolError("invalid_cursor", "Cursor outside stream range", 409)
            if s.events and cursor < s.events[0][0]["sequence"] - 1:
                raise ProtocolError("cursor_expired", "Retained event history no longer includes cursor", 409)
            if s.state == "active" and role == "agent":
                s.last_seen = self.clock()
            page, size, next_cursor = [], 0, cursor
            for event, audience in s.events:
                if event["sequence"] <= cursor:
                    continue
                if role in audience:
                    event_size = len(json.dumps(event, ensure_ascii=False).encode("utf-8"))
                    if page and (size + event_size > 131072 or len(page) >= 32):
                        break
                    page.append(deepcopy(event))
                    size += event_size
                next_cursor = event["sequence"]
            return dict(session=self.snapshot(s), events=page, cursor=next_cursor)

    def leave(self, session_id, token, reason):
        with self.lock:
            s, _ = self.authorize(session_id, token)
            self._close(s, reason)
            return self.snapshot(s)

    def get_action(self, session_id, token, request_id):
        with self.lock:
            s, _ = self.authorize(session_id, token)
            self._tick(s)
            action = s.actions.get(request_id)
            if action is None:
                raise ProtocolError("action_not_found", "No such action in this session", 404)
            return deepcopy(action)

    def send(self, session_id, token, message):
        with self.lock:
            s, role = self.authorize(session_id, token)
            self._tick(s)
            validate("message", message)
            if len(json.dumps(message, ensure_ascii=False).encode("utf-8")) > 65536:
                raise ProtocolError("message_too_large", "Message exceeds binding size limit", 413)
            key = (role, message["id"])
            mark = fingerprint(message)
            if key in s.accepted:
                saved, receipt = s.accepted[key]
                if saved != mark:
                    raise ProtocolError("id_conflict", "Message id reused with different content", 409)
                return deepcopy(receipt)
            if s.state != "active":
                raise ProtocolError("session_closed", "Session is no longer active", 409)
            if len(s.accepted) >= 1024:
                raise ProtocolError("resource_limit", "Session message capacity reached", 429)
            kind, data, sender = message["type"], message["data"], message["sender"]
            if role == "agent" and sender != s.agent:
                raise ProtocolError("permission_denied", "Sender identity mismatch", 403)
            if role == "game" and sender not in s.team | {self.descriptor["game_id"]}:
                raise ProtocolError("permission_denied", "Sender not a game participant", 403)
            if kind != "chat.message" and role == "game" and sender != self.descriptor["game_id"]:
                raise ProtocolError("permission_denied", "Game authority required", 403)
            if kind in {"game.context", "capability.update", "action.result"} and role != "game":
                raise ProtocolError("permission_denied", "Game authority required", 403)
            if kind in {"action.request", "action.cancel"} and role != "agent":
                raise ProtocolError("permission_denied", "Agent role required", 403)
            provenance = data.get("provenance")
            if provenance and provenance["player_id"] != s.player:
                raise ProtocolError("permission_denied", "Provenance belongs to a different player", 403)
            if kind == "game.context" and provenance["kind"] != "shared_experience":
                raise ProtocolError("invalid_provenance", "Game observation requires shared-experience provenance")
            if kind == "chat.message":
                recipients = set(data["recipients"])
                allowed = {s.player, s.agent} if data["channel"] == "private" else s.team | {s.agent}
                if not recipients <= allowed or (data["channel"] == "private" and sender not in {s.agent, s.player}):
                    raise ProtocolError("permission_denied", "Recipients or sender outside channel", 403)
            elif kind == "capability.update":
                capabilities = action_map(data["actions"])
                self.capabilities = capabilities
                self.descriptor["actions"] = deepcopy(data["actions"])
                self.revision += 1
                # 能力属于游戏，不只属于提交更新的单个会话。
                for other in self.sessions.values():
                    if other is not s and other.state == "active":
                        self._emit(other, "capability.update", data, {"agent", "game"})
            elif kind == "action.request":
                if data["capability_revision"] != self.revision:
                    raise ProtocolError("stale_capabilities", "Refresh capabilities before requesting an action", 409)
                if data["action"] not in self.capabilities or data["action"] not in s.permissions:
                    raise ProtocolError("permission_denied", "Action is not authorized", 403)
                definition = self.capabilities[data["action"]]
                if not Draft202012Validator(definition["parameters"]).is_valid(data["arguments"]):
                    raise ProtocolError("invalid_arguments", "Action arguments do not match capability schema")
                s.actions[message["id"]] = dict(state="pending", action=data["action"], revision=self.revision,
                    arguments=deepcopy(data["arguments"]), deadline=self.clock() + definition["timeout_ms"] / 1000,
                    cancel_requested=False)
            elif kind in {"action.result", "action.cancel"}:
                action = s.actions.get(data["request_id"])
                if not action:
                    raise ProtocolError("action_not_found", "No such action in this session", 404)
                if action["state"] not in {"pending", "executing"}:
                    raise ProtocolError("action_terminal", "Action already has a terminal or unknown outcome", 409)
                if kind == "action.result":
                    action["state"] = data["status"]
                    action["details"] = deepcopy(data["details"])
                else:
                    action["cancel_requested"] = True
            audience = {"game"} if role == "agent" else {"agent", "game"}
            if kind == "chat.message" and role == "game" and s.agent not in data["recipients"]:
                audience = {"game"}
            seq = self._emit(s, kind, data, audience, message)
            receipt = dict(accepted=True, sequence=seq)
            s.accepted[key] = (mark, receipt)
            if role == "agent":
                s.last_seen = self.clock()
            return deepcopy(receipt)

    def claim_action(self, session_id, token, request_id):
        """游戏执行器在产生副作用前领取；重复领取不返回执行许可。"""
        with self.lock:
            s, role = self.authorize(session_id, token)
            self._tick(s)
            if role != "game":
                raise ProtocolError("permission_denied", "Game authority required", 403)
            action = s.actions.get(request_id)
            if s.state != "active" or not action or action["state"] != "pending":
                raise ProtocolError("not_executable", "Action is not pending in an active session", 409)
            if action["cancel_requested"] or action["revision"] != self.revision or action["action"] not in s.permissions & self.capabilities.keys():
                raise ProtocolError("not_executable", "Action requires renewed permission or was cancelled", 409)
            action["state"] = "executing"
            return deepcopy(action)
