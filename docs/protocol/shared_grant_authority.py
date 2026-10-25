"""候选共享 Grant owner：固定预批准 Scope、可信邀请、现有 session/action 字节链。

一个锁域内原子撤销；不提供真实认证、磁盘事务或跨 authority 原子性。
"""

from copy import deepcopy
from hashlib import sha256
import importlib.util
from pathlib import Path
from threading import RLock
from uuid import uuid4


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


U = load("shared_grant_sessions", "session_harness.py")
E = load("shared_grant_snapshot_types", "epoch_rotation.py")
C, R = U.C, U.R


class SharedGrantFault(RuntimeError):
    pass


class SharedActionHarness(U.A.ActionHarness):
    """内部执行端口也受 owner 生命周期约束，不能绕过时钟、事务及恢复屏障。"""

    def _owner_entry(self):
        self.authority.owner._live()
        R.require(self.authority.owner._depth > 0, "temporarily_unavailable")

    def submit(self, raw, credential, *, now, fault=None):
        with self.lock:
            self._owner_entry()
            world = self.model.world
            try:
                return super().submit(raw, credential, now=now, fault=fault)
            finally:
                # staged 只提交协议知识，成功或异常都不能替换外部世界和 owner 锁。
                self.model.world = world
                self.model.lock = self.lock

    def execute(self, operation, worker, *, now, **kwargs):
        with self.lock:
            self._owner_entry()
            return super().execute(operation, worker, now=now, **kwargs)

    def revoke(self, *, now, revoke_grant=True):
        with self.lock:
            self._owner_entry()
            return super().revoke(now=now, revoke_grant=revoke_grant)

    def operation_view(self, payload, identity, *, now):
        with self.lock:
            self.authority.owner._live()
            return super().operation_view(payload, identity, now=now)


class SharedSession(U.SessionHarness):
    """只通过 owner 进入的子会话端口；身份、读权与动作账本仍按会话独立。"""

    _ACTION_HARNESS = SharedActionHarness

    def __init__(self, owner, fixture):
        self.owner = owner
        self.session_revocation_revision = 1
        super().__init__(fixture, {})

    def _transaction(self, operation, fault):
        return self.owner._transaction(operation, fault)

    @property
    def grant_owner_id(self):
        """可信协调器的授权域标识；不是请求方声明或网络认证凭据。"""
        return self.owner.owner_id

    def _trusted_recovery_of(self, previous):
        self.owner._live()
        return (type(previous) is type(self) and previous.owner is not self.owner and previous.owner.retired
                and self.owner.owner_id == previous.owner.owner_id
                and self.owner.checkpoints is previous.owner.checkpoints)

    def _identity(self, credential):
        self.owner._live()
        return super()._identity(credential)

    def _revoke_write(self, now):
        self.action_model.revoke(now=now, revoke_grant=False)

    def _revocation_binding(self, target):
        if target == "session":
            return self.session_revocation_revision, self.state["session"]["session_id"]
        return super()._revocation_binding(target)

    def _revoke_closed_object(self, target, now):
        R.require(target == "session", "unsupported_operation")
        self._close("revoked", now)
        self.session_revocation_revision += 1

    def submit(self, raw, credential, *, now, fault=None):
        return self.owner.submit(raw, credential, now=now,
                                 session_id=self.state["session"]["session_id"], fault=fault)

    def execute(self, operation, worker, *, now, **kwargs):
        return self.owner.execute(self.state["session"]["session_id"], operation, worker, now=now, **kwargs)

    def delivery(self, verified_principal, *, now):
        with self.owner.lock:
            self.owner._maintain(now)
            return super().delivery(verified_principal, now=now)

    def revoke(self, *, now, fault=None):
        self.owner._live()
        R.require(False, "unsupported_operation")  # Grant 撤销必须走有身份、CAS 和全局回执的入口。

    def revoke_result_read(self, principal, action_id):
        return self.owner._transaction(lambda: super(SharedSession, self).revoke_result_read(principal, action_id))

    def compact_through(self, sequence):
        return self.owner._transaction(lambda: super(SharedSession, self).compact_through(sequence))

    def compact_closed_receipts(self, *, now, max_items=64, fault=None):
        with self.owner.lock:
            self.owner._maintain(now)
            return super().compact_closed_receipts(now=now, max_items=max_items, fault=fault)


class SharedGrantAuthority:
    PROFILE = frozenset({"core.session", "core.events", "actions", "multi-session"})
    MAX_INVITATIONS = 16
    MAX_RECEIPTS = 64

    def __init__(self, fixture):
        self.fixture = deepcopy(fixture)
        scope = fixture["scope"]
        R.validate_scope(scope, fixture["descriptor"], fixture["requested"], now=scope["created_at"],
                         verified_audiences=[fixture["player"], fixture["agent"]])
        R.validate_grant(fixture["grant"], scope, now=scope["created_at"])
        R.require(set(scope["features"]) <= self.PROFILE and scope["ledger_durability"] == "volatile",
                  "feature_unsupported")
        R.require(scope["limits"]["session_count"] <= 8, "resource_limit")
        self.lock = RLock()
        self.owner_id = str(uuid4())
        self.healthy, self.retired, self._depth, self._transactions = True, False, 0, 0
        self.sessions = {}
        self.identities = {name + "-fixture": {"role": name, "principal": deepcopy(fixture[name])}
                           for name in ("player", "game")}
        self.identities["agent-identity"] = {"role": "agent", "principal": deepcopy(fixture["agent"])}
        self.invitation_credentials = {}
        self.state = {"grant": deepcopy(fixture["grant"]), "invitations": {}, "receipts": {},
                      "last_now": scope["created_at"]}
        # 独立可信锚点不由输入快照提供；world 是另一个独立受信效果账本。
        self.checkpoints = {}
        self._checkpoint()

    @staticmethod
    def _digest(value):
        try:
            return E.EpochRotation._digest(value)
        except E.RotationError:
            raise C.ContractError("invalid_snapshot") from None

    def _export(self):
        children = {}
        for sid, child in self.sessions.items():
            action = child.action_model
            children[sid] = {"state": deepcopy(child.state), "members": deepcopy(child.members),
                "pending_sync": child.pending_sync, "session_revision": child.session_revocation_revision,
                "action": deepcopy({name: getattr(action, name) for name in action.STATE_FIELDS}),
                "model": deepcopy({"steps": action.model.steps, "authorized": action.model.authorized,
                                   "action": action.model.action})}
        return {"owner_id": self.owner_id, "state": deepcopy(self.state), "sessions": children}

    def _auth_digest(self):
        return self._digest([self.fixture, self.identities, self.invitation_credentials,
                             {sid: child.credentials for sid, child in self.sessions.items()}])

    def _checkpoint(self):
        self.checkpoints.update(ledger=self._digest(self._export()), auth=self._auth_digest())

    def _live(self):
        R.require(self.healthy and not self.retired, "temporarily_unavailable")
        if self._depth == 0:
            try:
                intact = (self._digest(self._export()) == self.checkpoints.get("ledger") and
                          self._auth_digest() == self.checkpoints.get("auth"))
            except C.ContractError:
                intact = False
            if not intact:
                self.healthy = False
                R.require(False, "temporarily_unavailable")

    def _bind(self):
        for child in self.sessions.values():
            child.state["grant"] = self.state["grant"]
            child.lock = child.action_model.lock = child.action_model.model.lock = self.lock

    def _transaction(self, operation, fault=None):
        R.require(fault in (None, "before_commit", "after_first_close", "after_commit"), "invalid_arguments")
        with self.lock:
            self._live()
            if self._transactions:
                # 内层协议操作加入同一提交，不能换掉调用栈中仍持有的 session/Grant 引用。
                # execute 只提升 _depth；其效果后的发布仍会创建独立可回滚协议事务。
                R.require(fault is None, "invalid_arguments")
                return operation()
            original, children, auth = self.state, dict(self.sessions), dict(self.invitation_credentials)
            saved = {}
            for sid, child in children.items():
                checkpoint = child.action_model.checkpoint()
                checkpoint[0].world = child.action_model.model.world  # 世界事实绝不随协议事务复制/回滚。
                saved[sid] = (child.state, deepcopy(child.members), deepcopy(child.credentials),
                              child.pending_sync, child.session_revocation_revision, checkpoint)
                child.state = deepcopy(child.state)
            self.state = deepcopy(original)
            self._bind()
            self._depth += 1
            self._transactions += 1
            try:
                result = operation()
                if fault == "before_commit":
                    raise SharedGrantFault(fault)
            except BaseException:
                self.state, self.sessions, self.invitation_credentials = original, children, auth
                for sid, child in children.items():
                    (child.state, child.members, child.credentials, child.pending_sync,
                     child.session_revocation_revision, checkpoint) = saved[sid]
                    child.action_model.restore(checkpoint)
                self._bind()
                raise
            finally:
                self._depth -= 1
                self._transactions -= 1
            self._bind()
            if self._depth == 0:
                self._checkpoint()
            if fault == "after_commit":
                raise SharedGrantFault(fault)
            return result

    def _maintain(self, now):
        self._live()
        C.validate_type("Nat", now)
        R.require(now >= self.state["last_now"], "temporarily_unavailable")
        def expire():
            self.state["last_now"] = now
            for invitation in self.state["invitations"].values():
                if invitation["state"] == "issued" and now >= invitation["expires_at"]:
                    invitation["state"] = "expired"
            for child in self.sessions.values():
                session = child.state["session"]
                if session["state"] == "active" and now >= min(session["lease_deadline"], self.state["grant"]["expires_at"]):
                    child._close("expired", now)
        self._transaction(expire)

    def _identity(self, credential, operation, session_id):
        iid = self.invitation_credentials.get(credential)
        if iid is not None:
            R.require(operation == "session.join", "permission_denied")
            return {"role": "agent", "principal": self.fixture["agent"], "invitation_id": iid}
        identity = self.identities.get(credential)
        if identity is None and session_id in self.sessions:
            identity = self.sessions[session_id].credentials.get(credential)
        R.require(identity is not None, "unauthenticated")
        if "expires_at" in identity:
            R.require(type(identity["expires_at"]) is int and self.state["last_now"] < identity["expires_at"], "unauthenticated")
        expected = {"agent": "agent", "companion_control": "agent", "results_reader": "agent", "player": "player", "game": "game"}
        if identity["role"] in expected:
            R.require(identity["principal"] == self.fixture[expected[identity["role"]]], "permission_denied")
        return identity

    def _reply(self, request, result):
        reply = {"request_id": request["request_id"], "result": deepcopy(result)}
        C.validate_reply(request["operation"], request["request_id"], reply)
        return C.codec.canonical(reply)

    def issue_invitation(self, session_id, *, now, ttl_ms=60000, fault=None):
        """预批准 Grant 的可信邀请端口；不是新公开操作，也不代替玩家同意。"""
        with self.lock:
            self._maintain(now)
            C.validate_type("Id", session_id)
            C.validate_type("Revision", ttl_ms)
            def issue():
                grant = self.state["grant"]
                R.validate_grant(grant, self.fixture["scope"], now=now)
                R.require(all(i["session_id"] != session_id for i in self.state["invitations"].values()), "id_conflict")
                R.require(len(self.state["invitations"]) < self.MAX_INVITATIONS, "resource_limit")
                iid, token = str(uuid4()), "fixture-invitation-" + str(uuid4())
                invitation = {"id": iid, "session_id": session_id, "state": "issued", "grant_revision": grant["revision"],
                    "expires_at": min(now + ttl_ms, grant["expires_at"]), "intent": {"scope_digest": grant["scope_digest"]}}
                self.state["invitations"][iid] = invitation
                self.invitation_credentials[token] = iid
                return {"invitation_id": iid, "invitation_credential": token,
                        "expires_at": invitation["expires_at"], "join_intent": deepcopy(invitation["intent"])}
            return self._transaction(issue, fault)

    def _join(self, payload, identity, now):
        iid = payload["invitation_id"]
        R.require(identity.get("invitation_id") == iid, "permission_denied")
        invitation = self.state["invitations"][iid]
        R.require(C.codec.canonical(invitation["intent"]) == C.codec.canonical(payload["join_intent"]), "invitation_used")
        if invitation["state"] == "consumed":
            return iid
        R.require(invitation["state"] == "issued" and now < invitation["expires_at"], "invitation_expired")
        grant, scope = self.state["grant"], self.fixture["scope"]
        R.validate_grant(grant, scope, now=now)
        R.require(invitation["grant_revision"] == grant["revision"], "grant_revoked")
        limit = scope["limits"]["session_count"] if "multi-session" in scope["features"] else 1
        R.require(sum(c.state["session"]["state"] == "active" for c in self.sessions.values()) < limit, "session_conflict")
        sid = invitation["session_id"]
        R.require(sid not in self.sessions, "id_conflict")
        fixture = deepcopy(self.fixture)
        fixture["grant"] = deepcopy(grant)
        fixture["session"] = {"session_id": sid, "scope": deepcopy(scope), "grant_id": grant["grant_id"],
            "state": "active", "instance_epoch": scope["instance"]["epoch"], "transport_epoch": "transport-1",
            "control_generation": 1, "lease_deadline": min(now + scope["limits"]["lease_period_ms"], grant["expires_at"]),
            "capabilities_revision": 1, "membership_revision": 1, "sequence": 0, "ready": False}
        child = SharedSession(self, fixture)
        control, results = "fixture-control-" + str(uuid4()), "fixture-results-" + str(uuid4())
        child.credentials[control] = child.credentials.pop("agent-fixture")
        child.credentials[results] = {"role": "results_reader", "principal": deepcopy(scope["agent"])}
        invitation.update(state="consumed", control=control, results=results, admission="pending")
        self.sessions[sid] = child
        self._bind()
        return iid

    def _join_result(self, iid, now):
        invitation = self.state["invitations"][iid]
        child = self.sessions[invitation["session_id"]]
        session = child.state["session"]
        if (self.state["grant"]["state"] != "active" or session["state"] != "active" or
                now >= min(invitation["expires_at"], self.state["grant"]["expires_at"], session["lease_deadline"])):
            return {"status": "completed_without_secret", "outcome_ref": session["session_id"], "reauth_required": True}
        if not session["ready"]:
            return {"status": "join_pending", "session_id": session["session_id"]}
        visible = child._snapshot(session["scope"]["agent"], now)["actions"]
        return {"status": "ready", "session": deepcopy(session), "control_credential": invitation["control"],
            "result_read_handle": invitation["results"], "event_high_watermark": {"session_id": session["session_id"],
            "instance_epoch": session["instance_epoch"], "sequence": session["sequence"]},
            "unresolved_actions": [a["request_id"] for a in visible if a["state"] in {"pending", "executing", "unknown"}]}

    def finish_admission(self, session_id, *, now, success=True, fault=None):
        with self.lock:
            self._maintain(now)
            R.require(type(success) is bool and session_id in self.sessions, "invalid_arguments")
            def finish():
                child = self.sessions[session_id]
                session = child.state["session"]
                invitation = next(i for i in self.state["invitations"].values() if i["session_id"] == session_id)
                if session["state"] != "closed" and invitation["admission"] == "pending":
                    if success and now < invitation["expires_at"]:
                        session["ready"] = True
                        invitation["admission"] = "ready"
                        child._notice("session.ready", {"session": session}, now)
                    else:
                        invitation["admission"] = "failed"
                        child._close("admission_failed", now)
                return deepcopy(session)
            return self._transaction(finish, fault)

    def _revoke_grant(self, payload, now, fault):
        grant = self.state["grant"]
        R.require(payload["object_id"] == grant["grant_id"], "permission_denied")
        R.require(payload["expected_revision"] == grant["revision"], "generation_conflict")
        if grant["state"] != "revoked":
            grant.update(state="revoked", revision=grant["revision"] + 1)
            for invitation in self.state["invitations"].values():
                if invitation["state"] == "issued":
                    invitation["state"] = "revoked"
            for number, child in enumerate(self.sessions.values()):
                child._close("revoked", now)
                if number == 0 and fault == "after_first_close":
                    raise SharedGrantFault(fault)
        return {"object_type": "grant", "object_id": grant["grant_id"], "revision": grant["revision"], "state": "revoked"}

    def submit(self, raw, credential, *, now, session_id=None, fault=None):
        with self.lock:
            self._maintain(now)
            request = C.validate_request(raw)
            op, payload = request["operation"], request["payload"]
            identity = self._identity(credential, op, session_id)
            scope = self.fixture["scope"]
            R.require(request["version"] == scope["version"], "unsupported_version")
            R.require(len(raw) <= scope["limits"]["message_bytes"], "resource_limit")
            global_revoke = op == "permission.revoke" and payload["object_type"] == "grant"
            if op not in {"session.join", "operation.get"} and not global_revoke:
                R.require(session_id in self.sessions, "session_not_writable")
                return U.SessionHarness.submit(self.sessions[session_id], raw, credential, now=now, fault=fault)
            lane = "management" if identity["role"] == "game" else "control"
            C.authorize_route(op, identity["role"], lane, scope["features"])
            key = (R.principal_key(identity["principal"]), op, request["request_id"])
            if op == "operation.get":
                _, active = C.validate_active_request(raw, selected_extensions=scope["extensions"], supported_extensions=U.S.H.EXT.SUPPORTED)
                U.S.H.EXT.enforce(C, active, op, payload)
                U.S.H.EXT.enforce(C, scope["effective_policy"]["extensions"], op, payload)
                original = self.state["receipts"].get((key[0], payload["operation"], payload["original_request_id"]))
                if original is None:
                    R.require(session_id in self.sessions, "permission_denied")
                    return self._reply(request, self.sessions[session_id]._operation_view(payload, identity, now=now))
                result = {"operation": payload["operation"], "request_id": payload["original_request_id"], "state": "done"}
                if original["kind"] == "grant":
                    result.update(outcome_ref=original["result"]["object_id"], revocation=original["result"])
                else:
                    child = self.sessions[self.state["invitations"][original["iid"]]["session_id"]]
                    session = child.state["session"]
                    admission = self.state["invitations"][original["iid"]]["admission"]
                    result.update(outcome_ref=session["session_id"], session=deepcopy(session),
                        state="done" if admission == "ready" else "failed" if session["state"] == "closed" else "pending")
                return self._reply(request, result)
            old = self.state["receipts"].get(key)
            digest = sha256(raw).hexdigest()
            if old is not None:
                R.require(old["digest"] == digest, "id_conflict")
                return self._reply(request, old["result"] if old["kind"] == "grant" else self._join_result(old["iid"], now))
            _, active = C.validate_active_request(raw, selected_extensions=scope["extensions"], supported_extensions=U.S.H.EXT.SUPPORTED)
            U.S.H.EXT.enforce(C, active, op, payload)
            if not global_revoke or request["extensions"]:
                U.S.H.EXT.enforce(C, scope["effective_policy"]["extensions"], op, payload)
            def apply():
                R.require(len(self.state["receipts"]) < self.MAX_RECEIPTS + int(global_revoke), "resource_limit")
                if global_revoke:
                    result = self._revoke_grant(payload, now, fault)
                    record = {"kind": "grant", "result": result}
                else:
                    iid = self._join(payload, identity, now)
                    result, record = self._join_result(iid, now), {"kind": "join", "iid": iid}
                self.state["receipts"][key] = {**record, "digest": digest}
                return self._reply(request, result)
            return self._transaction(apply, fault)

    def execute(self, session_id, operation, worker, *, now, **kwargs):
        with self.lock:
            self._maintain(now)
            R.require(session_id in self.sessions, "session_not_writable")
            self._depth += 1
            try:
                return U.SessionHarness.execute(self.sessions[session_id], operation, worker, now=now, **kwargs)
            finally:
                # 效果或发布失败都保存协议知识；绝不把异常当成无效果或重建 world。
                self._depth -= 1
                self._bind()
                self._checkpoint()

    def snapshot(self):
        with self.lock:
            self._live()
            return self._export()

    def restart_from_mock_ledger(self, *, snapshot=None, intact=True):
        with self.lock:
            self._live()
            R.require(type(intact) is bool, "invalid_arguments")
            candidate = self._export() if snapshot is None else deepcopy(snapshot)
            R.require(type(candidate) is dict and set(candidate) == {"owner_id", "state", "sessions"}, "invalid_snapshot")
            R.require(candidate["owner_id"] == self.owner_id and self._digest(candidate) == self.checkpoints["ledger"], "snapshot_mismatch")
            restored = type(self)(self.fixture)
            restored.owner_id, restored.state = self.owner_id, candidate["state"]
            restored.identities = deepcopy(self.identities)
            restored.invitation_credentials = deepcopy(self.invitation_credentials)
            for sid, record in candidate["sessions"].items():
                child = SharedSession(restored, self.fixture)
                child.state, child.members = record["state"], record["members"]
                child.pending_sync, child.session_revocation_revision = record["pending_sync"], record["session_revision"]
                child.credentials = deepcopy(self.sessions[sid].credentials)  # 来自可信 live 端口，不由快照重建凭据。
                for name, value in record["action"].items():
                    setattr(child.action_model, name, value)
                for name, value in record["model"].items():
                    setattr(child.action_model.model, name, value)
                child.action_model.model.world = self.sessions[sid].action_model.model.world
                restored.sessions[sid] = child
            restored._bind()
            restored.checkpoints, restored.healthy = self.checkpoints, intact
            self.retired = True
            return restored
