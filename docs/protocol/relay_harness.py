"""独立 Relay authority 与游戏字节入口的组合；固定配对、内存队列，不是中继服务。"""

from copy import deepcopy
import importlib.util
from pathlib import Path
from threading import RLock


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P = load("relay_privacy", "privacy_harness.py")
E = load("relay_errors", "error_mapping.py")
PORT = load("relay_game_port", "relay_game_port.py")
C, R, U = P.C, P.R, P.U
InjectedFailure = U.S.H.InjectedFailure


class RelayHarness:
    RELAY = frozenset({"relay.register", "relay.call", "relay.pull", "relay.reply", "relay.revoke"})
    WIRE_OPERATIONS = P.PrivacyHarness.WIRE_OPERATIONS | RELAY
    MAX_WAIT_MS, MAX_INFLIGHT, MAX_RECORDS = 30000, 32, 128
    MAX_PULL_ITEMS, MAX_PULLS, MAX_MAILBOXES = 16, 128, 8

    def __init__(self, fixture, records=None, *, game=None):
        self.fixture = deepcopy(fixture)
        self.game = game if game is not None else P.PrivacyHarness(fixture, records or {})
        binding = fixture["scope"]["binding"]
        R.require(binding["kind"] == "outbound-relay" and fixture["scope"]["privacy_model"]["relay_plaintext"] is True,
                  "negotiation_failed")
        self.instance, self.relay_identity = deepcopy(fixture["scope"]["instance"]), deepcopy(binding["relay_identity"])
        self.origin = fixture["relay_origin"]
        R.require(binding["endpoint"] == self.origin + "/g2a/operations" and binding["peer_identity"] == self.instance["game"] and
                  self.relay_identity in fixture["scope"]["privacy_model"]["visible_to"], "negotiation_failed")
        self.pairings = deepcopy(fixture["relay_pairings"])
        self.enrollments = deepcopy(fixture["relay_enrollments"])
        self.lock = RLock()
        self.state = {"mailboxes": {}, "credentials": {}, "registrations": {}, "pairings_used": {},
                      "last_now": 0, "retired": False, "ledger_healthy": True}
        self.port = PORT.RelayGamePort(C, R, E, InjectedFailure, self.game, fixture["relay_game_audience"])
        self.port.enroll("inner-agent-fixture", "agent-identity")
        self.port.enroll("inner-player-fixture", "player-fixture")

    def _transaction(self, function, fault=None):
        R.require(fault in (None, "before_commit", "after_commit"), "invalid_arguments")
        original = self.state
        self.state = deepcopy(original)
        try:
            result = function()
            if fault == "before_commit":
                raise InjectedFailure(fault)
        except BaseException:
            self.state = original
            raise
        if fault == "after_commit":
            raise InjectedFailure(fault)
        return result

    def _close(self, box):
        if box["state"] == "closed":
            return
        box["state"], box["route_revision"] = "closed", box["route_revision"] + 1
        for token in box["credentials"].values():
            self.state["credentials"][token]["state"] = "revoked"
        for record in box["requests"].values():
            if record["state"] in {"queued", "claimed"}:
                record["state"] = "closed"
        # 不触碰 game 的 lease、Grant、动作或不可回滚效果。

    def _maintain(self, now):
        C.validate_type("Nat", now)
        R.require(not self.state["retired"] and now >= self.state["last_now"], "temporarily_unavailable")
        def maintain():
            self.state["last_now"] = now
            for box in self.state["mailboxes"].values():
                if now >= box["registration_expiry"]:
                    self._close(box)
                for record in box["requests"].values():
                    if record["state"] in {"queued", "claimed"} and now >= record["call"]["deadline"]:
                        record["state"] = "expired"
        self._transaction(maintain)

    def _identity(self, token, operation, now):
        enrolled = token in self.enrollments
        identity = deepcopy(self.enrollments.get(token) if enrolled else self.state["credentials"].get(token))
        try:
            C.validate_type("RelayCredential", identity)
        except (C.ContractError, C.codec.CodecError):
            raise C.ContractError("unauthenticated") from None
        R.require(identity["state"] == "active" and identity["issued_at"] <= now < identity["expires_at"], "unauthenticated")
        R.require(identity["instance"] == self.instance and identity["relay_identity"] == self.relay_identity and
                  identity["relay_origin"] == self.origin, "permission_denied")
        R.require(("mailbox_id" in identity) == ("route_revision" in identity) and
                  enrolled == ("mailbox_id" not in identity), "permission_denied")
        if operation is not None:
            C.authorize_route(operation, identity["role"], "relay", self.fixture["descriptor"]["supported_features"])
        identity["enrolled"] = enrolled
        return identity

    def _box(self, mailbox_id, identity):
        box = self.state["mailboxes"].get(mailbox_id)
        R.require(box is not None, "permission_denied")
        allowed = {"relay_agent": box["registration"]["agent_principals"],
                   "relay_controller": box["registration"]["control_principals"], "relay_game": [self.instance["game"]]}
        R.require(identity["principal"] in allowed[identity["role"]], "permission_denied")
        if not identity["enrolled"]:
            R.require(identity["mailbox_id"] == mailbox_id and identity["route_revision"] == box["route_revision"], "permission_denied")
        return box

    def credential_for(self, mailbox_id, authenticated_recipient, *, now):
        """可信配对交付端口，不是 wire 操作；只向已认证接收方返回自己的一个凭据。"""
        with self.lock:
            self._maintain(now)
            R.require(self.state["ledger_healthy"], "temporarily_unavailable")
            identity = self._identity(authenticated_recipient, None, now)
            R.require(identity["enrolled"], "permission_denied")
            box = self._box(mailbox_id, identity)
            R.require(box["state"] == "open", "request_gone")
            return box["credentials"][(identity["role"], R.principal_key(identity["principal"]))]

    @staticmethod
    def _digest(request):
        return C.codec.digest("control", {key: request[key] for key in ("version", "operation", "payload", "extensions")})

    def _reply(self, request, result=None, *, code=None, knowledge="not_accepted"):
        reply = {"request_id": request["request_id"]}
        if code is None:
            reply["result"] = deepcopy(result)
        else:
            reply["error"] = E.boundary_error(code, knowledge=knowledge)
        C.validate_reply(request["operation"], request["request_id"], reply)
        encoded = C.codec.canonical(reply)
        box = self.state["mailboxes"].get(request["payload"].get("mailbox_id"))
        limits = self.fixture["scope"]["limits"] if box is None else box["registration"]["limits"]
        R.require(len(encoded) <= min(65536, limits["message_bytes"]), "resource_limit")
        return encoded

    def _control(self, box, request, identity):
        key = (R.principal_key(identity["principal"]), request["operation"], request["request_id"])
        prior = box["controls"].get(key)
        if prior is not None:
            R.require(prior["digest"] == self._digest(request), "id_conflict")
        return key, prior

    def _save_control(self, box, key, request, result):
        limit = 513 if request["operation"] == "relay.revoke" else 512 if request["operation"] == "relay.reply" else 256
        R.require(len(box["controls"]) < limit, "resource_limit")
        box["controls"][key] = {"digest": self._digest(request), "result": deepcopy(result)}
        return self._reply(request, result)

    def _register(self, request, identity, now):
        R.require(identity["enrolled"] and identity["principal"] == self.fixture["player"], "permission_denied")
        key = (R.principal_key(identity["principal"]), request["request_id"])
        prior = self.state["registrations"].get(key)
        if prior is not None:
            R.require(prior["digest"] == self._digest(request), "id_conflict")
            return self._reply(request, prior["result"])
        payload = request["payload"]
        pairing = self.pairings.get(payload["pairing_proof_ref"])
        try:
            C.validate_type("RelayPairingAuthorization", pairing)
        except (C.ContractError, C.codec.CodecError):
            raise C.ContractError("permission_denied") from None
        R.require(pairing["proof_ref"] == payload["pairing_proof_ref"] and pairing["controller"] == identity["principal"] and
                  pairing["state"] == "active" and pairing["issued_at"] <= now < pairing["expires_at"], "permission_denied")
        for field in ("instance", "relay_identity", "relay_origin", "agent_principals", "control_principals", "limits"):
            R.require(C.codec.canonical(payload[field]) == C.codec.canonical(pairing[field]), "permission_denied")
        R.require(payload["instance"] == self.instance and payload["relay_identity"] == self.relay_identity and
                  payload["relay_origin"] == self.origin and payload["agent_principals"] == [self.fixture["agent"]] and
                  payload["control_principals"] == [self.fixture["player"]], "permission_denied")
        R.require(now < payload["registration_expiry"] <= min(pairing["expires_at"], now + 300000), "request_expired")
        R.require(payload["pairing_proof_ref"] not in self.state["pairings_used"], "id_conflict")
        R.require(len(self.state["mailboxes"]) < self.MAX_MAILBOXES, "resource_limit")
        mailbox_id = "mailbox-" + str(len(self.state["mailboxes"]) + 1)
        box = {"mailbox_id": mailbox_id, "registration": deepcopy(payload), "controller": deepcopy(identity["principal"]),
            "route_revision": 1, "registration_expiry": payload["registration_expiry"], "state": "open",
            "requests": {}, "claims": {}, "pulls": {}, "controls": {}, "credentials": {}, "last_principal": None}
        for role, principal in (("relay_controller", self.fixture["player"]), ("relay_agent", self.fixture["agent"]),
                                ("relay_game", self.fixture["game"])):
            token = mailbox_id + "-" + role + "-fixture-secret"
            credential = {"role": role, "principal": deepcopy(principal), "instance": deepcopy(self.instance),
                "relay_identity": deepcopy(self.relay_identity), "relay_origin": self.origin, "issued_at": now,
                "expires_at": payload["registration_expiry"], "state": "active", "mailbox_id": mailbox_id, "route_revision": 1}
            C.validate_type("RelayCredential", credential)
            self.state["credentials"][token] = credential
            box["credentials"][(role, R.principal_key(principal))] = token
        result = {key: box[key] for key in ("mailbox_id", "route_revision", "registration_expiry")}
        self.state["mailboxes"][mailbox_id] = box
        self.state["registrations"][key] = {"digest": self._digest(request), "result": deepcopy(result)}
        self.state["pairings_used"][payload["pairing_proof_ref"]] = mailbox_id
        return self._reply(request, result)

    def _call(self, request, identity, box, now):
        call = request["payload"]["call"]
        inner = call["operation_request"]
        proof = self.port.verify(call["inner_auth_proof"], now=now)
        C.authorize_relay_inner(identity["role"], proof["role"], inner["operation"], self.fixture["descriptor"]["supported_features"])
        R.require(proof["principal"] == identity["principal"], "permission_denied")
        key = (R.principal_key(identity["principal"]), call["relay_request_id"])
        digest = C.codec.digest("control", {"request": inner, "outer_extensions": request["extensions"]})
        prior = box["requests"].get(key)
        if prior is not None:
            R.require(prior["digest"] == digest and prior["inner_role"] == proof["role"], "id_conflict")
            R.require(call["route_revision"] == prior["call"]["route_revision"], "approval_stale")
            if prior["state"] in {"expired", "closed"} or box["state"] == "closed":
                code = "relay_not_dispatched" if prior["known_dispatch"] == "never_sent" else (
                    "transport_timeout" if prior["state"] == "expired" else "request_gone")
                return self._reply(request, code=code, knowledge="not_accepted" if prior["known_dispatch"] == "never_sent" else "unknown")
            R.require(not identity["enrolled"], "permission_denied")
            if prior["state"] == "replied":
                if prior["response_guard"] != self.port.guard(now=now):
                    return self._reply(request, code="request_gone", knowledge="unknown")
                return self._reply(request, {"state": "replied", "relay_request_id": call["relay_request_id"], "reply": prior["response"]})
            return self._reply(request, {"state": prior["state"], "relay_request_id": call["relay_request_id"]})
        R.require(not identity["enrolled"], "permission_denied")
        R.require(box["state"] == "open", "request_gone")
        R.require(call["route_revision"] == box["route_revision"], "approval_stale")
        deadline = min(call["deadline"], now + self.MAX_WAIT_MS, box["registration_expiry"], proof["expires_at"])
        R.require(now < deadline, "request_expired")
        R.require(len(box["requests"]) < self.MAX_RECORDS and
                  sum(item["state"] in {"queued", "claimed"} for item in box["requests"].values()) < self.MAX_INFLIGHT, "resource_limit")
        frozen = deepcopy(call)
        frozen["deadline"] = deadline
        # 单条 claim 必须能装进最坏关联 ID 的 pull 回包，否则接受后会永久无法领取。
        preview = {"claim_id": "claim-" + str(self.MAX_RECORDS), "mailbox_id": box["mailbox_id"],
                   "game_identity": self.instance["game"], "call": frozen}
        R.require(len(C.codec.canonical({"request_id": "r" * 128, "result": {"claims": [preview]}})) <=
                  min(65536, box["registration"]["limits"]["message_bytes"]), "resource_limit")
        box["requests"][key] = {"call": frozen, "digest": digest, "state": "queued", "known_dispatch": "never_sent",
            "principal": deepcopy(identity["principal"]), "outer_role": identity["role"], "inner_role": proof["role"],
            "claim": None, "response": None, "response_guard": None}
        return self._reply(request, {"state": "queued", "relay_request_id": call["relay_request_id"]})

    def _pull(self, request, identity, box):
        R.require(not identity["enrolled"] and box["state"] == "open", "permission_denied")
        key, control = self._control(box, request, identity)
        nonce_key = (R.principal_key(identity["principal"]), request["payload"]["pull_nonce"])
        old = box["pulls"].get(nonce_key)
        if old is not None:
            R.require(old["digest"] == self._digest(request), "id_conflict")
            for claim in old["result"]["claims"]:
                record = box["requests"][box["claims"][claim["claim_id"]]]
                R.require(record["state"] in {"claimed", "replied"} and self.state["last_now"] < claim["call"]["deadline"], "request_gone")
            return self._reply(request, old["result"]) if control else self._save_control(box, key, request, old["result"])
        R.require(len(box["pulls"]) < self.MAX_PULLS, "resource_limit")
        maximum = request["payload"]["maximum_items"]
        R.require(maximum <= min(self.MAX_PULL_ITEMS, box["registration"]["limits"]["event_page_size"]), "resource_limit")
        claims = []
        # 同主体 FIFO；每次在剩余主体间轮转，上一批不能一直占据下一批首位。
        while len(claims) < maximum:
            queued = [(k, value) for k, value in box["requests"].items() if value["state"] == "queued"]
            if not queued:
                break
            chosen = next(((k, value) for k, value in queued if k[0] != box["last_principal"]), queued[0])
            request_key, record = chosen
            claim_id = "claim-" + str(len(box["claims"]) + 1)
            claim = {"claim_id": claim_id, "mailbox_id": box["mailbox_id"], "game_identity": deepcopy(identity["principal"]),
                     "call": deepcopy(record["call"])}
            if len(C.codec.canonical({"request_id": request["request_id"], "result": {"claims": claims + [claim]}})) > min(
                    65536, box["registration"]["limits"]["message_bytes"]):
                R.require(bool(claims), "resource_limit")
                break
            record.update(state="claimed", known_dispatch="claimed", claim=claim)
            box["claims"][claim_id] = request_key
            box["last_principal"] = request_key[0]
            claims.append(claim)
        result = {"claims": claims}
        box["pulls"][nonce_key] = {"digest": self._digest(request), "result": deepcopy(result)}
        return self._save_control(box, key, request, result)

    def _record(self, box, claim_id, identity):
        request_key = box["claims"].get(claim_id)
        R.require(request_key is not None, "permission_denied")
        record = box["requests"][request_key]
        R.require(record["claim"]["game_identity"] == identity["principal"], "permission_denied")
        return record

    def _accept_reply(self, request, identity, box, now):
        R.require(not identity["enrolled"], "permission_denied")
        record = self._record(box, request["payload"]["claim_id"], identity)
        inner, reply = record["call"]["operation_request"], request["payload"]["reply"]
        C.validate_reply(inner["operation"], inner["request_id"], reply)
        R.require(len(C.codec.canonical(reply)) <= min(65536, box["registration"]["limits"]["message_bytes"]), "resource_limit")
        wrapped = {"request_id": "r" * 128, "result": {"state": "replied",
                   "relay_request_id": record["call"]["relay_request_id"], "reply": reply}}
        R.require(len(C.codec.canonical(wrapped)) <= min(65536, box["registration"]["limits"]["message_bytes"]), "resource_limit")
        if record["state"] == "replied":
            R.require(C.codec.canonical(record["response"]) == C.codec.canonical(reply), "reply_conflict")
        R.require(box["state"] == "open" and record["state"] in {"claimed", "replied"} and
                  now < record["call"]["deadline"], "request_gone")
        key, prior = self._control(box, request, identity)
        if prior is not None:
            return self._reply(request, prior["result"])
        if record["state"] != "replied":
            record.update(state="replied", response=deepcopy(reply),
                          response_guard=self.port.response_guard(record["claim"], reply, now=now))
        return self._save_control(box, key, request, {"status": "accepted"})

    def _revoke(self, request, identity, box):
        R.require(identity["principal"] == box["controller"], "permission_denied")
        key, prior = self._control(box, request, identity)
        if prior is not None:
            return self._reply(request, prior["result"])
        R.require(request["payload"]["expected_route_revision"] == box["route_revision"], "approval_stale")
        if box["state"] == "closed":
            # 已关闭对象的新 ID 只读固定终态；不能无限消耗专为止损保留的一格。
            return self._reply(request, {"mailbox_id": box["mailbox_id"], "route_revision": box["route_revision"], "state": "closed"})
        self._close(box)
        return self._save_control(box, key, request,
            {"mailbox_id": box["mailbox_id"], "route_revision": box["route_revision"], "state": "closed"})

    def submit(self, raw, credential, *, now, fault=None):
        request = C.validate_request(raw)
        R.require(not self.state["retired"], "temporarily_unavailable")
        if request["operation"] not in self.RELAY:
            return self.game.submit(raw, credential, now=now, fault=fault)
        with self.lock:
            self._maintain(now)
            R.require(self.state["ledger_healthy"], "temporarily_unavailable")
            identity = self._identity(credential, request["operation"], now)
            R.require(request["version"] == self.fixture["scope"]["version"], "unsupported_version")
            C.validate_active_request(raw, selected_extensions={}, supported_extensions=())
            box = None if request["operation"] == "relay.register" else self._box(request["payload"]["mailbox_id"], identity)
            limit = self.fixture["scope"]["limits"]["message_bytes"] if box is None else box["registration"]["limits"]["message_bytes"]
            R.require(len(raw) <= min(limit, 65536), "resource_limit")
            def apply():
                current = None if box is None else self.state["mailboxes"][box["mailbox_id"]]
                if request["operation"] == "relay.register":
                    return self._register(request, identity, now)
                if request["operation"] == "relay.call":
                    return self._call(request, identity, current, now)
                if request["operation"] == "relay.pull":
                    return self._pull(request, identity, current)
                if request["operation"] == "relay.reply":
                    return self._accept_reply(request, identity, current, now)
                return self._revoke(request, identity, current)
            return self._transaction(apply, fault)

    def dispatch_claim(self, raw_claim, game_credential, *, now, fault=None):
        """固定游戏端口消费 pull 字节；不是第 38 项操作，也不自动执行 reply。"""
        claim = C.codec.decode(raw_claim)
        C.validate_type("RelayClaim", claim)
        with self.lock:
            self._maintain(now)
            R.require(self.state["ledger_healthy"], "temporarily_unavailable")
            identity = self._identity(game_credential, "relay.pull", now)
            box = self._box(claim["mailbox_id"], identity)
            R.require(not identity["enrolled"] and box["state"] == "open", "request_gone")
            record = self._record(box, claim["claim_id"], identity)
            R.require(C.codec.canonical(record["claim"]) == C.codec.canonical(claim), "permission_denied")
            R.require(record["state"] in {"claimed", "replied"} and now < claim["call"]["deadline"] and
                      claim["call"]["route_revision"] == box["route_revision"], "request_gone")
            binding = {key: deepcopy(record[key]) for key in ("principal", "outer_role", "inner_role")}
        # 与 Relay 事务明确分离；撤销可在游戏调用期间发生，结果仍只能保守地标记 unknown。
        return C.codec.canonical(self.port.dispatch(claim, binding, now=now, fault=fault))

    def restart_from_mock_ledger(self, *, now, intact=True):
        R.require(type(intact) is bool, "invalid_arguments")
        with self.lock:
            self._maintain(now)
            restored = type(self)(self.fixture, game=self.game)
            restored.state = deepcopy(self.state)
            restored.enrollments, restored.pairings = deepcopy(self.enrollments), deepcopy(self.pairings)
            restored.port = self.port.restart(intact=intact)
            restored.state["ledger_healthy"] = intact and self.state["ledger_healthy"]
            if not restored.state["ledger_healthy"]:
                for box in restored.state["mailboxes"].values():
                    restored._close(box)
            self.state["retired"] = True
            return restored
