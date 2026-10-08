"""准入字节链与 SessionHarness 的单锁域装配；固定登记、无外部资源的 admission 假端口。"""

from copy import deepcopy
import importlib.util
from pathlib import Path
from threading import RLock


SPEC = importlib.util.spec_from_file_location("admission_sessions", Path(__file__).with_name("session_harness.py"))
U = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(U)
C, R = U.C, U.R


class AdmissionHarness:
    LIFECYCLE = frozenset({"describe", "offer.create", "offer.get", "offer.decide", "invitation.redeem",
                           "session.join", "operation.get"})
    WIRE_OPERATIONS = U.SessionHarness.WIRE_OPERATIONS | LIFECYCLE
    PROFILE = {"core.session", "core.events", "actions", "team"}
    LEDGERS = {"volatile"}
    RESOURCE_PROFILES = ()

    def __init__(self, fixture, records=None, *, decisions=None):
        self.fixture = deepcopy(fixture)
        R.validate_descriptor(fixture["descriptor"])
        R.require(set(fixture["descriptor"]["supported_features"]) <= self.PROFILE, "feature_unsupported")
        self.lock = RLock()
        self.session = None
        self.records = deepcopy(records or {})
        # 固定可信登记，不从 Requested.audiences 取得玩家席位或披露授权。
        self.verified_audiences = deepcopy(fixture.get("verified_audiences", [fixture["agent"], fixture["player"]]))
        C.validate_type("Principals", self.verified_audiences)
        R.require(all(p["kind"] in {"player", "agent"} for p in self.verified_audiences) and
                  R.principal_set([fixture["agent"], fixture["player"]]) <= R.principal_set(self.verified_audiences), "permission_denied")
        self.decisions = deepcopy(decisions or {})
        self.identities = {"agent-identity": {"role": "agent", "principal": deepcopy(fixture["agent"])},
                           "player-fixture": {"role": "player", "principal": deepcopy(fixture["player"])},
                           "game-fixture": {"role": "game", "principal": deepcopy(fixture["game"])}}
        self.state = {"descriptor": deepcopy(fixture["descriptor"]), "offers": {}, "grants": {},
                      "invitations": {}, "invitation_credentials": {}, "receipts": {},
                      "decision_used": {}, "admission": None, "last_now": 0}

    def _transaction(self, function, fault=None):
        R.require(fault in (None, "before_commit", "after_commit"), "invalid_arguments")
        with self.lock:
            original, child = self.state, self.session
            saved = None if child is None else (deepcopy(child.state), deepcopy(child.members),
                deepcopy(child.credentials), child.pending_sync, child.action_model.checkpoint())
            self.state = deepcopy(original)
            try:
                result = function()
                if fault == "before_commit":
                    raise U.S.H.InjectedFailure(fault)
            except BaseException:
                self.state, self.session = original, child
                if child is not None:
                    child.state, child.members, child.credentials, child.pending_sync, checkpoint = saved
                    child.action_model.restore(checkpoint)
                raise
            if fault == "after_commit":
                raise U.S.H.InjectedFailure(fault)
            return result

    def _grant(self, grant_id):
        if self.session is not None and self.session.state["grant"]["grant_id"] == grant_id:
            return self.session.state["grant"]
        return self.state["grants"][grant_id]

    def _maintain(self, now):
        """受信时钟维护先独立提交，后续无权/失败请求不能回滚已经到期的会话。"""
        C.validate_type("Nat", now)
        R.require(now >= self.state["last_now"], "temporarily_unavailable")
        def expire():
            self.state["last_now"] = now
            for record in self.state["offers"].values():
                offer = record["view"]
                if offer["state"] == "pending":
                    if now >= offer["decision_deadline"]:
                        offer["state"] = "expired"
                    elif offer["immutable_scope"]["descriptor_revision"] != self.state["descriptor"]["revision"]:
                        offer["state"] = "stale"
            if self.session is not None:
                session = self.session.state["session"]
                if session["state"] == "active" and now >= min(session["lease_deadline"], self.session.state["grant"]["expires_at"]):
                    self.session._close("expired", now)
        self._transaction(expire)

    def _identity(self, credential, operation):
        invitation_id = self.state["invitation_credentials"].get(credential)
        if invitation_id is not None:
            R.require(operation == "session.join", "permission_denied")
            invitation = self.state["invitations"][invitation_id]
            return {"role": "agent", "principal": invitation["agent"], "invitation_id": invitation_id}
        identity = self.identities.get(credential)
        R.require(identity is not None, "unauthenticated")
        expected = {"agent": self.fixture["agent"], "player": self.fixture["player"], "game": self.fixture["game"]}
        R.require(identity["role"] in expected and identity["principal"] == expected[identity["role"]], "permission_denied")
        return identity

    def _reply(self, request, result):
        reply = {"request_id": request["request_id"], "result": deepcopy(result)}
        C.validate_reply(request["operation"], request["request_id"], reply)
        return C.codec.canonical(reply)

    def _offer(self, offer_id, identity):
        record = self.state["offers"].get(offer_id)
        R.require(record is not None, "permission_denied")
        scope = record["view"]["immutable_scope"]
        R.require(identity["principal"] in (scope["agent"], scope["player"]), "permission_denied")
        return record

    def _current_scope(self, record, now):
        scope = record["view"]["immutable_scope"]
        R.validate_scope(scope, self.state["descriptor"], record["requested"], now=now,
                         verified_audiences=self.verified_audiences,
                         supported_resource_profiles=self.RESOURCE_PROFILES)

    def _negotiate(self, requested, now):
        d = self.state["descriptor"]
        R.require(requested["agent"] == self.fixture["agent"] and requested["player"] == self.fixture["player"], "permission_denied")
        R.require(requested["ledger_durability"] in self.LEDGERS, "negotiation_failed")
        features = sorted(set(d["supported_features"]) & set(requested["supported_features"]) & self.PROFILE)
        definitions = {item["id"]: item for item in d["actions"]}
        actions = sorted(set(requested["action_ids"]) & definitions.keys()) if "actions" in features else []
        limits = {key: min(value, requested["limits"][key]) for key, value in d["limits"].items()}
        limits["session_count"] = 1
        if "resume" not in features:
            limits["resume_window_ms"] = 0
        duration = min(requested["maximum_grant_duration_ms"], 300000)
        policy = {}
        for source in (requested["companion_defaults"], d["policy_defaults"], requested["policy"]):
            policy.update({key: deepcopy(value) for key, value in source.items() if key != "extensions"})
        policy["extensions"] = {}  # 本 profile 不协商活动扩展；required 项由关系校验拒绝。
        scope = {"player": deepcopy(requested["player"]), "agent": deepcopy(requested["agent"]),
                 "instance": deepcopy(d["instance"]), "version": self.fixture["scope"]["version"],
                 "binding": deepcopy(self.fixture["scope"]["binding"]), "trust_profile": "test-enrolled",
                 "features": features, "descriptor_revision": d["revision"], "action_ids": actions,
                 "approved_action_digests": {name: C.codec.digest("action-definition", definitions[name]) for name in actions},
                 "context_categories": sorted(set(requested["context_categories"]) & set(d["context_categories"])),
                 "audiences": sorted([deepcopy(p) for p in requested["audiences"]
                                      if R.principal_key(p) in R.principal_set(self.verified_audiences) and
                                      ("team" in features or p in [requested["agent"], requested["player"]])], key=C.codec.canonical),
                 "effective_policy": policy, "privacy_model": deepcopy(d["privacy_model"]),
                 "result_retention_ms": limits["result_retention_ms"], "ledger_durability": requested["ledger_durability"], "limits": limits,
                 "created_at": now, "expires_at": now + duration, "extensions": {}}
        self._scope_extras(scope, requested)
        R.validate_scope(scope, d, requested, now=now, verified_audiences=self.verified_audiences,
                         supported_resource_profiles=self.RESOURCE_PROFILES)
        return scope

    def _scope_extras(self, scope, requested):
        """受限 profile 在最终关系检查前补充已协商字段。"""

    def _validate_intent(self, intent, scope, identity, now):
        R.require(set(intent) == {"scope_digest"}, "feature_unsupported")

    def submit(self, raw, credential, *, now, fault=None):
        request = C.validate_request(raw)
        op, payload = request["operation"], request["payload"]
        R.require(op in self.WIRE_OPERATIONS, "unsupported_operation")
        with self.lock:
            self._maintain(now)
            def apply():
                prejoin_revoke = op == "permission.revoke" and payload["object_type"] in {"grant", "invitation", "auto_rule"}
                if op not in self.LIFECYCLE and not prejoin_revoke:
                    R.require(self.session is not None, "session_not_writable")
                    if op == "permission.revoke":
                        principal = self.session._identity(credential)["principal"]
                        key = (R.principal_key(principal), op, request["request_id"])
                        R.require(key not in self.state["receipts"], "id_conflict")
                    return self.session.submit(raw, credential, now=now)
                identity = self._identity(credential, op)
                lane = "management" if identity["role"] == "game" else C.catalog.OPERATIONS[op]["lane"]
                C.authorize_route(op, identity["role"], lane, self.PROFILE)
                R.require(request["version"] == self.fixture["scope"]["version"], "unsupported_version")
                R.require(len(raw) <= self.state["descriptor"]["limits"]["message_bytes"], "resource_limit")
                _, activated = C.validate_active_request(raw, selected_extensions={}, supported_extensions=())
                R.require(not activated, "feature_unsupported")
                if op == "describe":
                    R.require(payload["instance"] == self.state["descriptor"]["instance"], "permission_denied")
                    return self._reply(request, self.state["descriptor"])
                if op == "offer.get":
                    return self._reply(request, self._offer(payload["offer_id"], identity)["view"])
                if op == "operation.get":
                    if "expires_at" in identity:
                        R.require(type(identity["expires_at"]) is int and now < identity["expires_at"], "unauthenticated")
                    return self._reply(request, self._operation_view(payload, identity))
                key = (R.principal_key(identity["principal"]), op, request["request_id"])
                if prejoin_revoke and self.session is not None:
                    R.require(key not in self.session.state["session_controls"], "id_conflict")
                digest = C.codec.digest("control", {key: request[key] for key in ("version", "operation", "payload", "extensions")})
                old = self.state["receipts"].get(key)
                if old is not None:
                    R.require(old["digest"] == digest, "id_conflict")
                    return self._reply(request, self._receipt_result(old, identity, now))
                R.require(len(self.state["receipts"]) < (256 if prejoin_revoke else 128), "resource_limit")
                if op == "offer.create":
                    record = self._create(payload, identity, now)
                    receipt = {"kind": "offer", "ref": record["view"]["offer_id"]}
                elif op == "offer.decide":
                    record = self._decide(payload, identity, now)
                    receipt = {"kind": "offer", "ref": record["view"]["offer_id"]}
                elif op == "invitation.redeem":
                    invitation = self._redeem(payload, identity, now)
                    receipt = {"kind": "invitation", "ref": invitation["id"]}
                elif op == "session.join":
                    invitation = self._join(payload, identity, now)
                    receipt = {"kind": "join", "ref": invitation["id"]}
                else:
                    receipt = {"kind": "revocation", "ref": payload["object_id"], "result": self._revoke(payload, now)}
                receipt.update(digest=digest, operation=op, request_id=request["request_id"])
                self.state["receipts"][key] = receipt
                return self._reply(request, self._receipt_result(receipt, identity, now))
            return self._transaction(apply, fault)

    def _create(self, payload, identity, now):
        expected = self.fixture["agent"] if payload["entry"] == "companion" else self.fixture["player"]
        R.require(identity["principal"] == expected, "permission_denied")
        d = self.state["descriptor"]
        R.require(payload["descriptor_id"] == d["descriptor_id"] and payload["expected_descriptor_revision"] == d["revision"], "approval_stale")
        R.require(len(self.state["offers"]) < 16, "resource_limit")
        scope = self._negotiate(payload["requested"], now)
        oid = "offer-" + str(len(self.state["offers"]) + 1)
        view = {"offer_id": oid, "applicant": deepcopy(identity["principal"]), "immutable_scope": scope,
                "scope_digest": C.codec.digest("scope", scope), "decision_deadline": min(now + 60000, scope["expires_at"]),
                "launch_required": False, "state": "pending"}
        record = {"view": view, "requested": deepcopy(payload["requested"])}
        self.state["offers"][oid] = record
        return record

    def _decide(self, payload, identity, now):
        record = self._offer(payload["offer_id"], identity)
        view = record["view"]
        R.require(identity["principal"] == view["immutable_scope"]["player"], "permission_denied")
        evidence = self.decisions.get(payload["decision_ref"])
        R.require(evidence is not None and evidence["player"] == identity["principal"] and
                  C.codec.canonical(evidence["payload"]) == C.codec.canonical(payload), "consent_required")
        decision = C.codec.digest("control", {"version": self.fixture["scope"]["version"], "operation": "offer.decide",
                                            "payload": payload, "extensions": {}})
        prior = self.state["decision_used"].get(payload["decision_ref"])
        R.require(prior is None or prior == (view["offer_id"], decision), "id_conflict")
        if "decision" in record:
            R.require(record["decision"] == decision, "id_conflict")
            return record
        R.require(view["state"] != "expired" and now < view["decision_deadline"], "offer_expired")
        R.require(view["state"] == "pending" and payload["scope_digest"] == view["scope_digest"], "approval_stale")
        self._current_scope(record, now)
        if payload["allow"]:
            self._decision_options(record, payload, evidence, now)
            gid = "grant-" + str(len(self.state["grants"]) + 1)
            scope = deepcopy(view["immutable_scope"])
            self.state["grants"][gid] = {"grant_id": gid, "scope": scope, "scope_digest": view["scope_digest"],
                "approver": deepcopy(identity["principal"]), "consent_evidence_ref": payload["decision_ref"],
                "revision": 1, "state": "active", "expires_at": scope["expires_at"]}
            view.update(state="approved", grant_id=gid)
        else:
            view["state"] = "denied"
        record["decision"] = decision
        self.state["decision_used"][payload["decision_ref"]] = (view["offer_id"], decision)
        return record

    def _decision_options(self, record, payload, evidence, now):
        """默认准入配置不支持自动规则或启动；专门的本地启动层在同一事务中绑定许可。"""
        R.require(not payload["remember"] and not payload["launch_permission"], "feature_unsupported")

    def _redeem(self, payload, identity, now):
        record = self._offer(payload["offer_id"], identity)
        offer, intent = record["view"], payload["join_intent"]
        R.require(identity["principal"] == offer["immutable_scope"]["agent"], "permission_denied")
        R.require(offer["state"] == "approved", "consent_required")
        self._current_scope(record, now)
        R.validate_grant(self._grant(offer["grant_id"]), offer["immutable_scope"], now=now)
        R.require(now < offer["decision_deadline"], "offer_expired")
        R.require(intent["scope_digest"] == offer["scope_digest"], "approval_stale")
        self._validate_intent(intent, offer["immutable_scope"], identity, now)
        if "invitation" in record:
            invitation = self.state["invitations"][record["invitation"]]
            R.require(invitation["intent"] == intent, "redemption_conflict")
            return invitation
        iid = "invite-" + str(len(self.state["invitations"]) + 1)
        secret = "fixture-invitation-" + iid
        invitation = {"id": iid, "offer_id": offer["offer_id"], "grant_id": offer["grant_id"],
                      "grant_revision": self._grant(offer["grant_id"])["revision"], "agent": deepcopy(identity["principal"]),
                      "intent": deepcopy(intent), "secret": secret, "expires_at": min(now + 15000, offer["decision_deadline"]),
                      "state": "issued", "revision": 1, "generation": 1}
        self.state["invitations"][iid] = invitation
        self.state["invitation_credentials"][secret] = iid
        record["invitation"] = iid
        return invitation

    def _join(self, payload, identity, now):
        iid = payload["invitation_id"]
        R.require(identity.get("invitation_id") == iid, "permission_denied")
        invitation = self.state["invitations"][iid]
        R.require(invitation["intent"] == payload["join_intent"], "invitation_used")
        if invitation["state"] == "consumed":
            return invitation
        R.require(invitation["state"] == "issued" and now < invitation["expires_at"], "invitation_expired")
        record = self.state["offers"][invitation["offer_id"]]
        self._current_scope(record, now)
        grant = self._grant(invitation["grant_id"])
        R.validate_grant(grant, record["view"]["immutable_scope"], now=now)
        self._validate_intent(invitation["intent"], grant["scope"], identity, now)
        R.require(grant["revision"] == invitation["grant_revision"], "grant_revoked")
        R.require(self.session is None, "session_conflict")
        fixture = deepcopy(self.fixture)
        scope = deepcopy(grant["scope"])
        fixture.update(scope=scope, grant=deepcopy(grant))
        fixture["session"] = {"session_id": "s1", "scope": deepcopy(scope), "grant_id": grant["grant_id"],
            "state": "active", "instance_epoch": scope["instance"]["epoch"], "transport_epoch": "transport-1",
            "control_generation": 1, "lease_deadline": min(now + scope["limits"]["lease_period_ms"], grant["expires_at"]),
            "capabilities_revision": 1, "membership_revision": 1, "sequence": 0, "ready": False}
        if "resume" in scope["features"]:
            fixture["session"]["resume_until"] = min(fixture["session"]["lease_deadline"], now + scope["limits"]["resume_window_ms"])
        self.session = U.SessionHarness(fixture, self.records)
        self.session.lock = self.session.action_model.lock = self.lock
        identity = self.session.credentials.pop("agent-fixture")
        token, handle = "fixture-control-s1-1", "fixture-results-s1"
        self.session.credentials[token] = identity
        self.session.credentials[handle] = {"role": "results_reader", "principal": deepcopy(scope["agent"])}
        invitation.update(state="consumed", session_id="s1", control=token, results=handle,
                          transport_epoch=fixture["session"]["transport_epoch"])
        self.state["admission"] = {"invitation": iid, "state": "pending"}
        return invitation

    def finish_admission(self, *, now, success=True, fault=None):
        """可信准备端口：无资源/呈现的 profile 也必须通过一次 ready 提交；不是公开操作。"""
        R.require(type(success) is bool, "invalid_arguments")
        with self.lock:
            self._maintain(now)
            def apply():
                R.require(self.session is not None, "permission_denied")
                session = self.session.state["session"]
                if session["state"] == "closed":
                    return deepcopy(session)
                if self.state["admission"]["state"] != "pending":
                    return deepcopy(session)
                if success:
                    invitation = self.state["invitations"][self.state["admission"]["invitation"]]
                    try:
                        self._current_scope(self.state["offers"][invitation["offer_id"]], now)
                        R.validate_grant(self.session.state["grant"], session["scope"], now=now)
                    except C.ContractError:
                        success_now = False
                    else:
                        success_now = True
                else:
                    success_now = False
                if success_now:
                    session["ready"] = True
                    self.session._notice("session.ready", {"session": session}, now)
                    self.state["admission"]["state"] = "ready"
                else:
                    self.session._close("admission_failed", now)
                    self.state["admission"]["state"] = "failed"
                return deepcopy(self.session.state["session"])
            return self._transaction(apply, fault)

    def _receipt_result(self, receipt, identity, now):
        kind = receipt["kind"]
        if kind == "offer":
            return self._offer(receipt["ref"], identity)["view"]
        if kind == "revocation":
            return receipt["result"]
        invitation = self.state["invitations"][receipt["ref"]]
        R.require(identity["principal"] == invitation["agent"], "permission_denied")
        if kind == "join":
            R.require(identity.get("invitation_id") == invitation["id"], "permission_denied")
        safe = {"status": "completed_without_secret", "outcome_ref": invitation.get("session_id", invitation["id"]), "reauth_required": True}
        grant = self._grant(invitation["grant_id"])
        if grant["state"] != "active" or now >= min(grant["expires_at"], invitation["expires_at"]) or invitation["state"] == "revoked":
            return safe
        if invitation["state"] == "consumed":
            session = self.session.state["session"]
            if (session["state"] != "active" or now >= session["lease_deadline"] or session["control_generation"] != invitation["generation"] or
                    session["transport_epoch"] != invitation["transport_epoch"]):
                return safe
        if kind == "invitation":
            record = self.state["offers"][invitation["offer_id"]]
            try:
                self._current_scope(record, now)
            except C.ContractError:
                return safe
            return {"invitation_id": invitation["id"], "invitation_credential": invitation["secret"],
                    "expires_at": invitation["expires_at"], "join_intent": deepcopy(invitation["intent"])}
        session = self.session.state["session"]
        if not session["ready"]:
            return {"status": "join_pending", "session_id": session["session_id"]}
        return self._delivery(invitation["control"], invitation["results"], now)

    def _delivery(self, credential, result_handle, now):
        """仅在调用方完成身份/代次/设备/秘密有效性检查后生成；恢复清单服从当前结果读权。"""
        session = self.session.state["session"]
        visible = self.session._snapshot(session["scope"]["agent"], now)["actions"]
        return {"status": "ready", "session": deepcopy(session), "control_credential": credential,
                "result_read_handle": result_handle, "event_high_watermark": {"session_id": session["session_id"],
                "instance_epoch": session["instance_epoch"], "sequence": session["sequence"]},
                "unresolved_actions": [item["request_id"] for item in visible if item["state"] in {"pending", "executing", "unknown"}]}

    def _operation_view(self, payload, identity):
        key = (R.principal_key(identity["principal"]), payload["operation"], payload["original_request_id"])
        receipt = self.state["receipts"].get(key)
        if receipt is None:
            R.require(self.session is not None, "permission_denied")
            return self.session._operation_view(payload, identity, now=self.state["last_now"])
        result = {"operation": receipt["operation"], "request_id": receipt["request_id"], "state": "done", "outcome_ref": receipt["ref"]}
        if receipt["kind"] == "offer":
            result["offer"] = deepcopy(self._offer(receipt["ref"], identity)["view"])
        elif receipt["kind"] == "join":
            session = self.session.state["session"]
            admission = self.state["admission"]["state"]
            # 首次 ready 的原提交事实不因之后 handoff/close 改写；session 是当前视图。
            result.update(session=deepcopy(session), outcome_ref=session["session_id"],
                          state="done" if admission == "ready" else "failed" if admission == "failed" or session["state"] == "closed" else "pending")
        elif receipt["kind"] == "revocation":
            result["revocation"] = deepcopy(receipt["result"])
        return result

    def _revoke(self, payload, now):
        kind, oid = payload["object_type"], payload["object_id"]
        R.require(kind in {"grant", "invitation"}, "unsupported_operation")
        collection = self.state["grants"] if kind == "grant" else self.state["invitations"]
        R.require(oid in collection, "permission_denied")
        target = self._grant(oid) if kind == "grant" else collection[oid]
        R.require(target["revision"] == payload["expected_revision"], "generation_conflict")
        if kind == "invitation" and target["state"] == "consumed":
            return {"object_type": kind, "object_id": oid, "revision": target["revision"], "state": "consumed"}
        target.update(state="revoked", revision=target["revision"] + 1)
        if kind == "grant":
            for invitation in self.state["invitations"].values():
                if invitation["grant_id"] == oid and invitation["state"] == "issued":
                    invitation.update(state="revoked", revision=invitation["revision"] + 1)
            if self.session is not None and self.session.state["session"]["grant_id"] == oid:
                self.session._close("revoked", now)
        return {"object_type": kind, "object_id": oid, "revision": target["revision"], "state": "revoked"}

    def execute(self, *args, **kwargs):
        with self.lock:
            self._maintain(kwargs["now"])
            R.require(self.session is not None, "session_not_writable")
            return self.session.execute(*args, **kwargs)
