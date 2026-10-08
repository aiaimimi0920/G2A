"""Relay 的可信游戏端口：独立身份表、一次派发标记和响应日志；无网络或自动效果重试。"""

from copy import deepcopy
from threading import RLock


class RelayGamePort:
    def __init__(self, checks, relations, errors, fault_type, game, audience):
        self.C, self.R, self.E, self.Failure = checks, relations, errors, fault_type
        self.game, self.audience = game, audience
        self.instance = deepcopy(game.fixture["scope"]["instance"])
        self.lock = RLock()
        self.proofs, self.journal = {}, {}
        self.dispatch_calls = 0
        self.healthy = True

    def _identity(self, credential):
        """从游戏已有可信登记取身份，绝不从内层 payload 推断角色。"""
        with self.game.lock:
            if self.game.session is not None and credential in self.game.session.credentials:
                return deepcopy(self.game.session.credentials[credential])
            if credential in self.game.identities:
                return deepcopy(self.game.identities[credential])
            invitation_id = self.game.state["invitation_credentials"].get(credential)
            if invitation_id is not None:
                invitation = self.game.state["invitations"][invitation_id]
                return {"role": "agent", "principal": deepcopy(invitation["agent"]), "invitation_id": invitation_id}
            self.R.require(False, "unauthenticated")

    def enroll(self, proof_ref, credential, *, now=0, expires_at=900000):
        """仅可信测试适配器调用；客户端只能提交 proof_ref，不能自建本表。"""
        with self.lock:
            identity = self._identity(credential)
            proof = {"proof_ref": proof_ref, "credential": credential, "principal": identity["principal"],
                "role": identity["role"], "instance": deepcopy(self.instance), "audience": self.audience,
                "issued_at": now, "expires_at": expires_at, "state": "active"}
            self.C.validate_type("RelayInnerAuthorization", proof)
            self.R.require(now < expires_at and proof_ref not in self.proofs, "permission_denied")
            self.proofs[proof_ref] = proof

    def verify(self, proof_ref, *, now):
        with self.lock:
            proof = deepcopy(self.proofs.get(proof_ref))
            try:
                self.C.validate_type("RelayInnerAuthorization", proof)
            except (self.C.ContractError, self.C.codec.CodecError):
                raise self.C.ContractError("unauthenticated") from None
            self.R.require(proof["proof_ref"] == proof_ref and proof["instance"] == self.instance and
                           proof["audience"] == self.audience, "permission_denied")
            self.R.require(proof["state"] == "active" and proof["issued_at"] <= now < proof["expires_at"], "unauthenticated")
            identity = self._identity(proof["credential"])
            self.R.require(identity["role"] == proof["role"] and identity["principal"] == proof["principal"], "permission_denied")
            return proof

    def guard(self, *, now):
        """假端口的保守再披露栅栏。发生授权变化则拒绝旧缓存，不重执行原请求。"""
        with self.game.lock:
            child = self.game.session
            view = {"descriptor": self.game.state["descriptor"]["revision"],
                "grants": sorted([[key, value["revision"], value["state"], now < value["expires_at"]]
                                  for key, value in self.game.state["grants"].items()]),
                "privacy_cutoffs": deepcopy(self.game.state.get("privacy_cutoffs", {})), "session": None}
            if child is not None:
                session, grant = child.state["session"], child.state["grant"]
                view["session"] = {"state": session["state"], "ready": session["ready"],
                    "generation": session["control_generation"], "transport": session["transport_epoch"],
                    "membership": session["membership_revision"], "capabilities": session["capabilities_revision"],
                    "scope": grant["scope_digest"], "grant_state": grant["state"], "grant_revision": grant["revision"],
                    "live": now < min(session["lease_deadline"], grant["expires_at"]),
                    "result_access": child.state["result_access_revision"],
                    "result_revoked": sorted([[list(principal), action] for principal, action in child.state["result_read_revoked"]]),
                    "sources": sorted([[key, source["revision"], source["state"], now < source["expires_at"]]
                                       for key, source in child.state["records"].items()])}
            return self.C.codec.digest("control", view)

    def _error(self, request, code, knowledge):
        reply = {"request_id": request["request_id"], "error": self.E.boundary_error(code, knowledge=knowledge)}
        self.C.validate_reply(request["operation"], request["request_id"], reply)
        return reply

    def dispatch(self, claim, binding, *, now, fault=None):
        """binding 必须是 Relay 已提交 claim 的可信见证；本方法不会调用 relay.reply。"""
        self.R.require(fault in (None, "before_dispatch", "after_mark", "after_game", "after_commit"), "invalid_arguments")
        key = (claim["mailbox_id"], claim["claim_id"])
        request = claim["call"]["operation_request"]
        frozen = self.C.codec.digest("control", {"claim": claim, "binding": binding})
        with self.lock:
            self.R.require(self.healthy, "temporarily_unavailable")
            proof = self.verify(claim["call"]["inner_auth_proof"], now=now)
            self.R.require(proof["principal"] == binding["principal"] and proof["role"] == binding["inner_role"], "permission_denied")
            self.C.authorize_relay_inner(binding["outer_role"], proof["role"], request["operation"],
                                         self.game.fixture["descriptor"]["supported_features"])
            old = self.journal.get(key)
            if old is not None:
                self.R.require(old["digest"] == frozen, "id_conflict")
                if old["reply"] is None:
                    return self._error(request, "outcome_unknown", "unknown")
                self.R.require(old["guard"] == self.guard(now=now), "request_gone")
                return deepcopy(old["reply"])
            self.R.require(len(self.journal) < 1024, "resource_limit")
            if fault == "before_dispatch":
                raise self.Failure(fault)
            # 该标记独立于游戏事务；标记后任何不确定异常均不自动再次执行。
            self.journal[key] = {"digest": frozen, "reply": None, "guard": None}
            if fault == "after_mark":
                raise self.Failure(fault)
            self.dispatch_calls += 1
            try:
                raw = self.game.submit(self.C.codec.canonical(request), proof["credential"], now=now)
            except self.C.ContractError as error:
                # 游戏字节入口自身的拒绝；不是从 transport timeout 猜测业务失败。
                reply = self._error(request, error.code, "not_accepted")
            except Exception:
                return self._error(request, "outcome_unknown", "unknown")
            else:
                try:
                    reply = self.C.codec.decode(raw)
                    self.C.validate_reply(request["operation"], request["request_id"], reply)
                except Exception:
                    # 游戏已返回；此后的坏字节或坏 schema 不证明它没有提交。
                    return self._error(request, "outcome_unknown", "unknown")
            if fault == "after_game":
                raise self.Failure(fault)
            self.journal[key].update(reply=deepcopy(reply), guard=self.guard(now=now))
            if fault == "after_commit":
                raise self.Failure(fault)
            return deepcopy(reply)

    def response_guard(self, claim, reply, *, now):
        with self.lock:
            record = self.journal.get((claim["mailbox_id"], claim["claim_id"]))
            if record is not None and record["reply"] is not None:
                self.R.require(self.C.codec.canonical(record["reply"]) == self.C.codec.canonical(reply), "reply_conflict")
                return record["guard"]
            # 独立游戏主体也可直接提交合法回复；真实性仍是已声明的 GameAuthority 端口保证。
            return self.guard(now=now)

    def restart(self, *, intact=True):
        with self.lock:
            restored = type(self)(self.C, self.R, self.E, self.Failure, self.game, self.audience)
            restored.proofs, restored.journal = deepcopy(self.proofs), deepcopy(self.journal)
            restored.dispatch_calls = self.dispatch_calls
            restored.healthy = intact and self.healthy
            self.healthy = False
            return restored
