"""Relay 的可信游戏端口：独立身份表、一次派发标记和响应日志；无网络或自动效果重试。"""

from copy import deepcopy
from threading import RLock


class RelayGamePort:
    def __init__(self, checks, relations, errors, fault_type, game, audience, *, route_epoch=None):
        self.C, self.R, self.E, self.Failure = checks, relations, errors, fault_type
        self.game, self.audience = game, audience
        self.instance = deepcopy(game.fixture["scope"]["instance"])
        self.lock = RLock()
        self.proofs, self.journal = {}, {}
        self.closed_mailboxes = set()
        self.unresolved = set()
        self.unstarted = set()
        self.dispatch_witnesses = {}
        self.dispatch_calls = 0
        self.healthy = True
        if route_epoch is not None:
            self.C.validate_type("Nat", route_epoch)
        self.route_epoch = route_epoch

    def _route(self, mailbox_id):
        if self.route_epoch is not None:
            prefix = "mailbox-e" + str(self.route_epoch) + "-"
            self.R.require(type(mailbox_id) is str and mailbox_id.startswith(prefix), "request_gone")
            suffix = mailbox_id[len(prefix):]
            self.R.require(suffix in {str(index) for index in range(1, 9)}, "request_gone")

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
            self.R.require(self.healthy, "temporarily_unavailable")
            identity = self._identity(credential)
            proof = {"proof_ref": proof_ref, "credential": credential, "principal": identity["principal"],
                "role": identity["role"], "instance": deepcopy(self.instance), "audience": self.audience,
                "issued_at": now, "expires_at": expires_at, "state": "active"}
            self.C.validate_type("RelayInnerAuthorization", proof)
            self.R.require(now < expires_at and proof_ref not in self.proofs, "permission_denied")
            self.proofs[proof_ref] = proof

    def verify(self, proof_ref, *, now):
        with self.lock:
            self.R.require(self.healthy, "temporarily_unavailable")
            proof = deepcopy(self.proofs.get(proof_ref))
            try:
                self.C.validate_type("RelayInnerAuthorization", proof)
            except (self.C.ContractError, self.C.codec.CodecError):
                raise self.C.ContractError("unauthenticated") from None
            self.R.require(proof["proof_ref"] == proof_ref and proof["instance"] == self.instance and
                           proof["audience"] == self.audience, "permission_denied")
            self.R.require(proof["state"] == "active" and proof["issued_at"] <= now < proof["expires_at"], "unauthenticated")
            identity = self._identity(proof["credential"])
            # proof 只绑定身份，不能延长底层 enrolled 凭据自身的有效期。
            if "expires_at" in identity:
                self.R.require(type(identity["expires_at"]) is int and now < identity["expires_at"], "unauthenticated")
            self.R.require(identity["role"] == proof["role"] and identity["principal"] == proof["principal"], "permission_denied")
            return proof

    def guard(self, *, now):
        """假端口的保守再披露栅栏。发生授权变化则拒绝旧缓存，不重执行原请求。"""
        with self.lock, self.game.lock:
            self.R.require(self.healthy, "temporarily_unavailable")
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
            self._route(claim["mailbox_id"])
            self.R.require(claim["mailbox_id"] not in self.closed_mailboxes, "request_gone")
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
            self.unresolved.add(key)
            self.unstarted.add(key)
            self.dispatch_witnesses[key] = frozen
            if fault == "after_mark":
                raise self.Failure(fault)
            # 在调用游戏之前先撤去未调用见证；此后任何未知都不能据此收敛。
            self.unstarted.discard(key)
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
            self.unresolved.discard(key)
            self.dispatch_witnesses.pop(key, None)
            if fault == "after_commit":
                raise self.Failure(fault)
            return deepcopy(reply)

    def response_guard(self, claim, reply, *, now):
        with self.lock:
            self.R.require(self.healthy, "temporarily_unavailable")
            self._route(claim["mailbox_id"])
            self.R.require(claim["mailbox_id"] not in self.closed_mailboxes, "request_gone")
            record = self.journal.get((claim["mailbox_id"], claim["claim_id"]))
            if record is not None and record["reply"] is not None:
                self.R.require(self.C.codec.canonical(record["reply"]) == self.C.codec.canonical(reply), "reply_conflict")
                return record["guard"]
            # 独立游戏主体也可直接提交合法回复；真实性仍是已声明的 GameAuthority 端口保证。
            return self.guard(now=now)

    def retire_mailbox(self, mailbox_id, *, fault=None):
        """仅接收可信 Relay owner 的关闭见证；与 Relay 账本不是同一事务。"""
        self.R.require(fault in (None, "before_commit", "after_commit"), "invalid_arguments")
        with self.lock:
            self.R.require(self.healthy, "temporarily_unavailable")
            if mailbox_id in self.closed_mailboxes:
                return {"retired": True, "compacted": 0}
            self.R.require(len(self.closed_mailboxes) < 8, "resource_limit")
            keys = [key for key in self.journal if key[0] == mailbox_id]
            if fault == "before_commit":
                raise self.Failure(fault)
            # 同一端口锁串行化在途派发；即使原调用已产生效果，也只移除缓存回复。
            for key in keys:
                self.journal[key] = {"digest": self.journal[key]["digest"], "reply": None, "guard": None}
            self.closed_mailboxes.add(mailbox_id)
            if fault == "after_commit":
                raise self.Failure(fault)
            return {"retired": True, "compacted": len(keys)}

    def compact_retired_journal(self, *, maximum=128, fault=None):
        """仅永久关闭屏障覆盖的 claim 可回收；身份屏障本身不回收。"""
        self.R.require(type(maximum) is int and 1 <= maximum <= 128, "invalid_arguments")
        self.R.require(fault in (None, "before_commit", "after_commit"), "invalid_arguments")
        with self.lock:
            self.R.require(self.healthy, "temporarily_unavailable")
            eligible = [key for key in self.journal if key[0] in self.closed_mailboxes]
            selected = eligible[:maximum]
            if fault == "before_commit":
                raise self.Failure(fault)
            # 先构造完整新表再替换；故障不会留下一半索引。dispatch 在查表前检查屏障。
            removed = set(selected)
            self.journal = {key: record for key, record in self.journal.items() if key not in removed}
            if fault == "after_commit":
                raise self.Failure(fault)
            return {"removed": len(selected), "remaining": len(eligible) - len(selected)}

    def settle_unstarted(self, mailbox_id, claim_id, *, fault=None):
        """可信维护：仅收敛已封闭邮箱且端口自身证明尚未调用游戏的派发。"""
        self.R.require(fault in (None, "before_commit", "after_commit"), "invalid_arguments")
        with self.lock:
            self.R.require(self.healthy, "temporarily_unavailable")
            self._route(mailbox_id)
            self.R.require(mailbox_id in self.closed_mailboxes, "permission_denied")
            key = (mailbox_id, claim_id)
            self.R.require(key in self.unstarted, "outcome_unknown")
            if fault == "before_commit":
                raise self.Failure(fault)
            # 关闭屏障先存在，旧请求不能在收敛后重新进入 dispatch。
            self.unresolved.discard(key)
            if fault == "after_commit":
                raise self.Failure(fault)
            return {"settled": True, "outcome": "not_accepted"}

    def settle_admission_commit(self, claim, binding, *, now, fault=None):
        """可信查证准入提交事实；不重放原请求，也不披露业务结果。"""
        self.R.require(fault in (None, "before_commit", "after_commit"), "invalid_arguments")
        key = (claim["mailbox_id"], claim["claim_id"])
        request = claim["call"]["operation_request"]
        with self.lock, self.game.lock:
            self.R.require(self.healthy, "temporarily_unavailable")
            self._route(key[0])
            self.R.require(key[0] in self.closed_mailboxes, "permission_denied")
            self.R.require(key not in self.unstarted and key in self.dispatch_witnesses, "outcome_unknown")
            frozen = self.C.codec.digest("control", {"claim": claim, "binding": binding})
            self.R.require(self.dispatch_witnesses[key] == frozen, "id_conflict")
            proof = self.verify(claim["call"]["inner_auth_proof"], now=now)
            self.R.require(proof["principal"] == binding["principal"] and proof["role"] == binding["inner_role"], "permission_denied")
            self.R.require(request["operation"] in {"offer.create", "offer.decide", "invitation.redeem", "session.join"},
                           "unsupported_operation")
            self.game._maintain(now)
            receipt_key = (self.R.principal_key(proof["principal"]), request["operation"], request["request_id"])
            receipt = self.game.state["receipts"].get(receipt_key)
            self.R.require(receipt is not None, "outcome_unknown")
            digest = self.C.codec.digest("control", {field: request[field]
                for field in ("version", "operation", "payload", "extensions")})
            self.R.require(receipt["digest"] == digest and receipt["operation"] == request["operation"]
                           and receipt["request_id"] == request["request_id"], "id_conflict")
            if fault == "before_commit":
                raise self.Failure(fault)
            self.unresolved.discard(key)
            if fault == "after_commit":
                raise self.Failure(fault)
            return {"settled": True, "acceptance": "committed"}

    def settle_action_acceptance(self, claim, binding, *, reader_proof, now, fault=None):
        """按 Envelope 身份查证受理；复用当前结果读权，不宣称动作效果完成。"""
        self.R.require(fault in (None, "before_commit", "after_commit"), "invalid_arguments")
        key = (claim["mailbox_id"], claim["claim_id"])
        request = claim["call"]["operation_request"]
        with self.lock, self.game.lock:
            self.R.require(self.healthy, "temporarily_unavailable")
            self._route(key[0])
            self.R.require(key[0] in self.closed_mailboxes, "permission_denied")
            self.R.require(key not in self.unstarted and key in self.dispatch_witnesses, "outcome_unknown")
            self.R.require(self.dispatch_witnesses[key] == self.C.codec.digest("control", {"claim": claim, "binding": binding}),
                           "id_conflict")
            proof = self.verify(claim["call"]["inner_auth_proof"], now=now)
            self.R.require(proof["principal"] == binding["principal"] and proof["role"] == binding["inner_role"], "permission_denied")
            self.R.require(request["operation"] in {"action.request", "action.cancel"}, "unsupported_operation")
            self.game._maintain(now)
            child = self.game.session
            self.R.require(child is not None, "outcome_unknown")
            with child.lock:
                envelope = request["payload"]
                self.R.require(envelope["session_id"] == child.state["session"]["session_id"], "permission_denied")
                reader = self.verify(reader_proof, now=now)
                self.R.require(reader["principal"] == proof["principal"], "permission_denied")
                view = child._operation_view({"operation": request["operation"], "original_request_id": envelope["id"]},
                                             reader, now=now)
                self.R.require(view["receipt"]["record_digest"] == self.C.codec.digest("message", envelope), "id_conflict")
                if fault == "before_commit":
                    raise self.Failure(fault)
                self.unresolved.discard(key)
                if fault == "after_commit":
                    raise self.Failure(fault)
                return {"settled": True, "acceptance": "committed"}

    def settle_session_control(self, claim, binding, *, reader_proof, now, fault=None):
        """仅查证会话控制账本的原提交，不续租、不重复关闭/撤权。"""
        self.R.require(fault in (None, "before_commit", "after_commit"), "invalid_arguments")
        key = (claim["mailbox_id"], claim["claim_id"])
        request = claim["call"]["operation_request"]
        with self.lock, self.game.lock:
            self.R.require(self.healthy, "temporarily_unavailable")
            self._route(key[0])
            self.R.require(key[0] in self.closed_mailboxes, "permission_denied")
            self.R.require(key not in self.unstarted and key in self.dispatch_witnesses, "outcome_unknown")
            self.R.require(self.dispatch_witnesses[key] == self.C.codec.digest("control", {"claim": claim, "binding": binding}),
                           "id_conflict")
            proof = self.verify(claim["call"]["inner_auth_proof"], now=now)
            self.R.require(proof["principal"] == binding["principal"] and proof["role"] == binding["inner_role"], "permission_denied")
            reader = self.verify(reader_proof, now=now)
            self.R.require(reader["principal"] == proof["principal"] and reader["role"] in {"agent", "player"}, "permission_denied")
            self.R.require(request["operation"] in {"session.heartbeat", "session.close", "permission.revoke"}, "unsupported_operation")
            if request["operation"] == "permission.revoke":
                self.R.require(request["payload"]["object_type"] in {"session", "result_read", "capability"}, "unsupported_operation")
            self.game._maintain(now)
            child = self.game.session
            self.R.require(child is not None, "outcome_unknown")
            with child.lock:
                receipt_key = (self.R.principal_key(reader["principal"]), request["operation"], request["request_id"])
                receipt = child.state["session_controls"].get(receipt_key)
                self.R.require(receipt is not None, "outcome_unknown")
                digest = self.C.codec.digest("control", {field: request[field]
                    for field in ("version", "operation", "payload", "extensions")})
                self.R.require(receipt["digest"] == digest, "id_conflict")
                # 只验证原主体查询资格；不返回其中的 session 或 revocation 正文。
                child._operation_view({"operation": request["operation"], "original_request_id": request["request_id"]},
                                      reader, now=now)
                if fault == "before_commit":
                    raise self.Failure(fault)
                self.unresolved.discard(key)
                if fault == "after_commit":
                    raise self.Failure(fault)
                return {"settled": True, "acceptance": "committed"}

    def advance_route_epoch(self, target_epoch, *, fault=None):
        """可信封存协调器调用；独立提交，不能清掉未知派发来强制切换。"""
        self.C.validate_type("Nat", target_epoch)
        self.R.require(fault in (None, "before_commit", "after_commit"), "invalid_arguments")
        with self.lock:
            self.R.require(self.healthy and self.route_epoch is not None, "temporarily_unavailable")
            if target_epoch == self.route_epoch:
                return {"epoch": target_epoch}
            self.R.require(target_epoch == self.route_epoch + 1, "generation_conflict")
            self.R.require(not self.unresolved, "outcome_unknown")
            if fault == "before_commit":
                raise self.Failure(fault)
            self.route_epoch = target_epoch
            self.journal, self.closed_mailboxes = {}, set()
            self.unstarted = set()
            self.dispatch_witnesses = {}
            if fault == "after_commit":
                raise self.Failure(fault)
            return {"epoch": target_epoch}

    def restart(self, *, intact=True):
        self.R.require(type(intact) is bool, "invalid_arguments")
        with self.lock:
            self.R.require(self.healthy, "temporarily_unavailable")
            restored = type(self)(self.C, self.R, self.E, self.Failure, self.game, self.audience,
                                  route_epoch=self.route_epoch)
            restored.proofs, restored.journal = deepcopy(self.proofs), deepcopy(self.journal)
            restored.closed_mailboxes = set(self.closed_mailboxes)
            restored.unresolved = set(self.unresolved)
            restored.unstarted = set(self.unstarted)
            restored.dispatch_witnesses = deepcopy(self.dispatch_witnesses)
            restored.dispatch_calls = self.dispatch_calls
            restored.healthy = intact and self.healthy
            self.healthy = False
            return restored
