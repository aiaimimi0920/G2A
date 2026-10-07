"""小型原生客户端；不自动重试有副作用请求、不执行资源 URL。"""
from copy import deepcopy
import json
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener
import uuid

from .validation import ProtocolError, validate


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


class Client:
    def __init__(self, endpoint, *, expected_game_id, clock=time.monotonic, ssl_context=None):
        url = urlsplit(endpoint)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}:
            raise ValueError("An explicit HTTP(S) origin without credentials is required")
        if url.scheme == "http" and url.hostname != "127.0.0.1":
            raise ValueError("Plain HTTP is restricted to explicit IPv4 loopback")
        self.endpoint = endpoint.rstrip("/")
        self.expected_game_id = expected_game_id
        self.opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPSHandler(context=ssl_context))
        self.clock = clock
        self.session = None
        self.token = None
        self.desktop_visible = None
        self.desktop_before = None
        self.cursor = 0
        self.deadline = 0

    def call(self, path, body=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        data = None if body is None else json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        req = Request(self.endpoint + path, data=data, headers=headers)
        try:
            with self.opener.open(req, timeout=5) as response:
                raw = response.read(262145)
                if len(raw) > 262144:
                    raise ProtocolError("response_too_large", "Response exceeds client limit")
                return json.loads(raw)
        except HTTPError as error:
            raw = error.read(65536)
            try:
                detail = json.loads(raw)["error"]
                raise ProtocolError(detail["code"], detail["message"], error.code) from None
            except (ValueError, KeyError, TypeError):
                raise ProtocolError("transport_error", "Peer returned a non-protocol error", error.code) from None

    def join(self, invitation, request):
        if self.session:
            raise ProtocolError("already_joined", "Create a new client for another presentation session", 409)
        descriptor = validate("descriptor", self.call("/.well-known/g2a.json"))
        if descriptor["game_id"] != self.expected_game_id:
            raise ProtocolError("wrong_game", "Descriptor does not match selected game", 409)
        validate("join", request)
        joined = validate("joined", self.call("/sessions", request, invitation))
        if joined["session"]["game_id"] != self.expected_game_id or joined["session"]["agent_id"] != request["agent_id"] or joined["session"]["player_id"] != request["player_id"]:
            raise ProtocolError("identity_mismatch", "Join response changed participant identities", 409)
        self.session = joined["session"]
        self.token = joined["session_token"]
        self.desktop_before = request["desktop_visible"]
        self.desktop_visible = self.session["desktop_visible"]
        self.lease = joined["lease_seconds"]
        self.deadline = self.clock() + self.lease
        return deepcopy(self.session)

    def poll(self):
        try:
            value = validate("poll", self.call(f"/sessions/{self.session['id']}/events?cursor={self.cursor}", token=self.token))
            if any(value["session"][key] != self.session[key] for key in ("id", "game_id", "agent_id", "player_id")):
                raise ProtocolError("identity_mismatch", "Poll response changed session identity", 409)
            sequences = [event["sequence"] for event in value["events"]]
            if sequences != sorted(set(sequences)) or any(seq <= self.cursor or seq > value["cursor"] for seq in sequences) or value["cursor"] < self.cursor or value["cursor"] > value["session"]["sequence"]:
                raise ProtocolError("invalid_cursor", "Poll response has invalid event ordering", 409)
        except Exception:
            self.check_lease()
            raise
        self.session = value["session"]
        self.cursor = value["cursor"]
        if self.session["state"] == "closed":
            self.desktop_visible = self.desktop_before
        else:
            self.desktop_visible = self.session["desktop_visible"]
            self.deadline = self.clock() + self.lease
        return value

    def send(self, kind, data, *, message_id=None):
        message = dict(id=message_id or uuid.uuid4().hex, type=kind, sender=self.session["agent_id"], data=data)
        validate("message", message)
        receipt = validate("receipt", self.call(f"/sessions/{self.session['id']}/events", message, self.token))
        # 历史重复提交可返回旧收据；它不能证明会话当前仍存活。
        # 只有已验证的 poll 快照用于延长客户端呈现租约。
        return receipt

    def check_lease(self):
        """客户端集成方必须周期调用；此内存示例并非实际桌面窗口控制。"""
        if self.session and self.clock() >= self.deadline:
            self.desktop_visible = self.desktop_before
            return True
        return False

    def leave(self, reason="user_left"):
        try:
            return self.call(f"/sessions/{self.session['id']}/leave", {"reason": reason}, self.token)
        finally:
            self.desktop_visible = self.desktop_before
