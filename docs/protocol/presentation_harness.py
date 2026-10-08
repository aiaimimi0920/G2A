"""呈现字节入口与准入/恢复/转移 saga；只有可信内存设备，无真实窗口或资源加载。"""

from copy import deepcopy
import importlib.util
from pathlib import Path


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


H = load("presentation_control", "control_harness.py")
D = load("presentation_device", "presentation_device.py")
REC = load("presentation_recovery", "presentation_recovery.py")
C, R, U = H.C, H.R, H.U


class PresentationHarness(H.ControlHarness):
    PRESENTATION = frozenset({"presentation.acquire", "presentation.renew", "presentation.release"})
    WIRE_OPERATIONS = H.ControlHarness.WIRE_OPERATIONS | PRESENTATION
    PROFILE = H.ControlHarness.PROFILE | {"presentation"}

    def __init__(self, fixture, records=None, *, decisions=None, target_proofs=None):
        super().__init__(fixture, records, decisions=decisions, target_proofs=target_proofs)
        self.devices, self.observations = {}, {}
        self.state.update(presentation_jobs={}, presentation_receipts={}, presentation_renewals={}, presentation_sweep_cursor=0)

    def enroll_device(self, device_id, *, visible=True):
        """固定登记的 Device.verify 假端口，不是公开 wire 操作。"""
        C.validate_type("Id", device_id)
        R.require(type(visible) is bool, "invalid_arguments")
        R.require(len(self.devices) < 4, "resource_limit")
        R.require(device_id not in self.devices, "id_conflict")
        self.devices[device_id] = D.PresentationDevice(device_id, self.fixture["player"], R.require, visible=visible)
        return self.observe_device(device_id)

    def observe_device(self, device_id):
        device = self.devices[device_id]
        ref = "observation-" + device_id + "-" + str(device.epoch) + "-" + str(device.manual_revision)
        value = {"device_id": device_id, "device_epoch": device.epoch, "baseline_visible": device.baseline_visible,
                 "manual_revision": device.manual_revision, "proof_ref": ref}
        self.observations[ref] = deepcopy(value)
        return value

    def _scope_extras(self, scope, requested):
        if "presentation" in scope["features"] and "presentation_terms" in requested:
            scope["presentation_terms"] = deepcopy(requested["presentation_terms"])

    def _validate_intent(self, intent, scope, identity, now):
        if "presentation" not in scope["features"]:
            return super()._validate_intent(intent, scope, identity, now)
        R.require(set(intent) == {"scope_digest", "selected_device", "presentation_observation"}, "permission_denied")
        device = self.devices.get(intent["selected_device"])
        observation = intent["presentation_observation"]
        R.require(device is not None and device.player == scope["player"] and
                  device.device_id == scope["presentation_terms"]["device_id"], "permission_denied")
        R.require(self.observations.get(observation["proof_ref"]) == observation and
                   observation["device_id"] == device.device_id and observation["manual_revision"] == device.manual_revision and
                  observation["device_epoch"] == device.epoch and
                  observation["baseline_visible"] == device.baseline_visible, "approval_stale")

    def _join(self, payload, identity, now):
        invitation = super()._join(payload, identity, now)
        session = self.session.state["session"]
        if "presentation" in session["scope"]["features"] and "presentation_job" not in self.state["admission"]:
            device = invitation["intent"]["selected_device"]
            session["controller_device"] = device
            self.session.credentials[invitation["control"]]["device_id"] = device
            job = self._new_job("admission-s1", device, session["control_generation"], session["lease_deadline"])
            self.state["admission"]["presentation_job"] = job["id"]
        return invitation

    def _new_job(self, jid, device, generation, deadline):
        session = self.session.state["session"]
        R.require(device in self.devices and self.devices[device].player == session["scope"]["player"], "permission_denied")
        R.require(len(self.state["presentation_jobs"]) < 128, "resource_limit")
        terms = {**session["scope"]["presentation_terms"], "device_id": device}
        job = {"id": jid, "acquire": {"session_id": session["session_id"], "generation": generation, "device_id": device,
                "device_epoch": self.devices[device].epoch, "lease_revision": 1,
                "terms": terms, "deadline": deadline, "scope_digest": C.codec.digest("scope", session["scope"]),
                "authority_proof_ref": "proof-" + jid}, "release_pending": False,
               "device_epoch": self.devices[device].epoch, "release_attempts": 0, "retry_at": 0,
                "manual_revision": self.devices[device].manual_revision,
                "render_failures": self.devices[device].render_failures}
        job["lease"] = deepcopy(job["acquire"])
        self.state["presentation_jobs"][jid] = job
        return job

    def _transaction(self, function, fault=None):
        def apply():
            result = function()
            self._queue_closed()
            self._queue_leases()
            return result
        return super()._transaction(apply, fault)

    def _queue_closed(self):
        if self.session is not None and self.session.state["session"]["state"] == "closed":
            for job in self.state.get("presentation_jobs", {}).values():
                job["release_pending"] = not self._release_complete(job)
            for renewal in self.state["presentation_renewals"].values():
                if renewal["state"] == "pending":
                    renewal["state"] = "failed"
            for record in self.state.get("transfers", {}).values():
                if record["view"]["status"] in {"releasing", "acquiring"}:
                    record["view"].update(status="failed", failure_reason="transfer_failed")

    def _queue_leases(self):
        """与已经验证的游戏租约同事务发布意图；发布本身绝不延长设备占用。"""
        if self.session is None or not self.state["ledger_healthy"]:
            return
        session = self.session.state["session"]
        if session["state"] != "active" or not session["ready"]:
            return
        for job in self.state["presentation_jobs"].values():
            lease, ack = job["lease"], job.get("lease_ack")
            if job["release_pending"] or lease["generation"] != session["control_generation"] or not ack:
                continue
            deadline = session["lease_deadline"]
            rebind_pending = lease["device_epoch"] != job["device_epoch"] and deadline > ack["lease_deadline"]
            if deadline <= lease["deadline"] and not rebind_pending:
                continue
            revision = lease["lease_revision"] + 1
            R.require(len(self.state["presentation_renewals"]) < 256 and revision <= C.codec.MAX_INTEGER, "resource_limit")
            previous = self.state["presentation_renewals"].get(job.get("renewal_id"))
            if previous is not None and previous["state"] == "pending":
                previous["state"] = "superseded"
            rid = "renew-" + job["id"] + "-" + str(revision)
            payload = {**lease, "deadline": deadline, "lease_revision": revision,
                       "device_epoch": job["device_epoch"], "authority_proof_ref": "proof-" + rid}
            self.state["presentation_renewals"][rid] = {"job_id": job["id"], "payload": deepcopy(payload), "state": "pending"}
            job.update(lease=payload, renewal_id=rid)

    def _release_complete(self, job):
        epoch = self.devices[job["acquire"]["device_id"]].epoch
        receipts = [job.get("release_ack", {}), job.get("release_evidence", {}).get("receipt", {})]
        return any(r.get("applied") and r.get("device_epoch") == epoch and r.get("lease_deadline") == 0 for r in receipts)

    def _verify_expiry(self, job, now):
        p = job["acquire"]
        evidence = self.devices[p["device_id"]].prove_expiry(p, job["lease"]["deadline"], now=now)
        if evidence is not None:
            job.update(release_evidence=evidence, release_pending=False)
        return evidence is not None

    def _maintain(self, now):
        R.require(not self.state["retired"], "resume_denied")
        R.require(type(now) is int and now >= self.state["last_now"], "temporarily_unavailable")
        for device in self.devices.values():
            device.tick(now)
        super()._maintain(now)
        def reconcile():
            if self.session is None or self.session.state["session"]["state"] == "closed":
                return
            current = self.session.state["session"]["control_generation"]
            for job in self.state["presentation_jobs"].values():
                p = job["acquire"]
                # 旧代正常释放不关闭新代；当前代手动取消/本地租约到期必须停写。
                device = self.devices[p["device_id"]]
                key = (p["session_id"], current)
                manual_conflict = (device.reachable and p["terms"]["mode"] == "hide_desktop" and key not in device.occupations and
                                    device.manual_revision != job["manual_revision"])
                render_failure = (device.reachable and device.render_failures != job["render_failures"] and
                                   (p["generation"] == current or job["release_pending"]))
                ack = job.get("lease_ack")
                expired_ack = ack is not None and now >= ack["lease_deadline"]
                lost_epoch = device.reachable and device.epoch != job["device_epoch"]
                released = device.reachable and key in device.tombstones
                if render_failure or (p["generation"] == current and (released or manual_conflict or expired_ack or lost_epoch)):
                    self.session._close("presentation_unavailable", now)
                    break
        self._transaction(reconcile)

    def _find_job(self, payload):
        matches = [j for j in self.state["presentation_jobs"].values()
                   if all(j["acquire"][key] == payload[key] for key in ("session_id", "generation", "device_id"))]
        R.require(len(matches) == 1, "permission_denied")
        return matches[0]

    def submit(self, raw, credential, *, now, fault=None):
        request = C.validate_request(raw)
        op, p = request["operation"], request["payload"]
        if op not in self.PRESENTATION:
            return super().submit(raw, credential, now=now, fault=fault)
        R.require(fault in (None, "before_commit", "after_commit"), "invalid_arguments")
        with self.lock:
            self._maintain(now)
            R.require(self.session is not None, "permission_denied")
            session = self.session.state["session"]
            R.require(credential == "presentation-fixture", "permission_denied")
            C.authorize_route(op, "presentation_authority", "local", session["scope"]["features"])
            R.require(request["version"] == session["scope"]["version"], "unsupported_version")
            R.require(len(raw) <= session["scope"]["limits"]["message_bytes"], "resource_limit")
            C.validate_active_request(raw, selected_extensions=session["scope"]["extensions"], supported_extensions=())
            job = self._find_job(p)
            rid = request["request_id"]
            digest = C.codec.digest("control", {key: request[key] for key in ("version", "operation", "payload", "extensions")})
            key = (op, rid)
            old = self.state["presentation_receipts"].get(key)
            R.require(old is None or old["digest"] == digest, "id_conflict")
            releases = sum(operation == "presentation.release" for operation, _ in self.state["presentation_receipts"])
            R.require(old is not None or (releases < D.PresentationDevice.RELEASE_RECEIPTS if op == "presentation.release" else
                      len(self.state["presentation_receipts"]) - releases < D.PresentationDevice.NORMAL_RECEIPTS), "resource_limit")
            if op != "presentation.release":
                if op == "presentation.acquire":
                    R.require(p == job["acquire"], "permission_denied")
                    R.require(rid == job["id"], "id_conflict")
                else:
                    renewal = self.state["presentation_renewals"].get(rid)
                    R.require(renewal is not None and renewal["job_id"] == job["id"] and p == renewal["payload"], "permission_denied")
                    R.require(session["ready"] and not job["release_pending"], "presentation_unavailable")
                R.validate_grant(self.session.state["grant"], session["scope"], now=now)
                R.require(session["state"] == "active" and p["generation"] == session["control_generation"] and
                          now < p["deadline"] <= session["lease_deadline"] and self.state["ledger_healthy"], "presentation_unavailable")
                if "transfer" in job:
                    R.require(self.state["transfers"][job["transfer"]]["view"]["status"] in {"acquiring", "ready"}, "transfer_in_progress")
            device = self.devices[p["device_id"]]
            R.require(device.device_id == p["device_id"] and device.player == session["scope"]["player"], "permission_denied")
            if op != "presentation.release":
                R.require(p["device_epoch"] == device.epoch == job["device_epoch"], "approval_stale")
                self._before_acquire(job, now)
            # 设备事务先提交；接下来的 authority fault 不得撤销物理效果或设备 tombstone。
            receipt = device.apply(op, p, rid, digest, now=now, current_revision=job["lease"]["lease_revision"])
            def record():
                current = self.state["presentation_jobs"][job["id"]]
                if op == "presentation.release":
                    if not self._release_complete(current) and receipt["device_epoch"] == device.epoch:
                        current["release_ack"] = deepcopy(receipt)
                    current["release_pending"] = not self._release_complete(current)
                else:
                    if op == "presentation.acquire":
                        current["acquire_ack"] = deepcopy(receipt)
                    else:
                        self.state["presentation_renewals"][rid]["state"] = "done" if receipt["applied"] else "failed"
                    if receipt["applied"] and receipt["lease_revision"] >= current.get("lease_ack", {}).get("lease_revision", 0):
                        current["lease_ack"] = deepcopy(receipt)
                self.state["presentation_receipts"][key] = {"digest": digest, "receipt": deepcopy(receipt), "ref": job["id"]}
                if not receipt["applied"] or (op == "presentation.release" and p["generation"] == session["control_generation"]):
                    self.session._close("presentation_unavailable", now)
                return self._reply(request, receipt)
            return self._transaction(record, fault)

    def _before_acquire(self, job, now):
        """无资源 profile 的准备阶段为空；资源装配层在设备效果前验证其准备收据。"""

    def _ack_ready(self, job, now):
        p, ack = job["acquire"], job.get("lease_ack")
        device = self.devices[p["device_id"]]
        return (ack is not None and ack["applied"] and now < ack["lease_deadline"] and
                device.reachable and device.render_verified and ack["device_epoch"] == device.epoch == job["device_epoch"] and
                (p["session_id"], p["generation"]) in device.occupations and
                (p["terms"]["mode"] != "hide_desktop" or not device.actual_visible))

    def finish_admission(self, *, now, success=True, fault=None):
        with self.lock:
            self._maintain(now)
            admission = self.state["admission"]
            if admission and "presentation_job" in admission and success:
                if not self._ack_ready(self.state["presentation_jobs"][admission["presentation_job"]], now):
                    return deepcopy(self.session.state["session"])
            return super().finish_admission(now=now, success=success, fault=fault)

    def _prepare_rotation(self, record, session, now):
        if "presentation" not in session["scope"]["features"]:
            return
        old = self._find_job({"session_id": session["session_id"], "generation": record["view"]["old_generation"],
                              "device_id": session["controller_device"]})
        old["release_pending"] = True
        renewal = self.state["presentation_renewals"].get(old.get("renewal_id"))
        if renewal is not None and renewal["state"] == "pending":
            renewal["state"] = "superseded"
        job = self._new_job("presentation-" + record["id"], record["device"], record["view"]["new_generation"], record["view"]["deadline"])
        job["transfer"] = record["id"]
        record.update(presentation_job=job["id"], previous_job=old["id"])
        record["view"]["status"] = "releasing"
        session["ready"] = False

    def advance_transfer(self, transfer_id, *, now, success=True, fault=None):
        with self.lock:
            self._maintain(now)
            original = self.state["transfers"].get(transfer_id)
            if original is None or "presentation_job" not in original:
                return super().advance_transfer(transfer_id, now=now, success=success, fault=fault)
            R.require(type(success) is bool, "invalid_arguments")
            def advance():
                record = self.state["transfers"][transfer_id]
                view = record["view"]
                if view["status"] in {"ready", "failed"}:
                    return deepcopy(view)
                if not success:
                    self._fail(record, "transfer_failed", now)
                    return deepcopy(view)
                session = self._live(now, ready=False)
                old = self.state["presentation_jobs"][record["previous_job"]]
                if not (self._release_complete(old) or self._verify_expiry(old, now)):
                    return deepcopy(view)
                view["status"] = "acquiring"
                job = self.state["presentation_jobs"][record["presentation_job"]]
                if self._ack_ready(job, now):
                    self.session._reserve_stop()
                    session.update(ready=True, controller_device=record["device"])
                    view["status"] = "ready"
                    self.session._notice("session.ready", {"session": session}, now)
                return deepcopy(view)
            return self._transaction(advance, fault)

    def _operation_view(self, payload, identity):
        if payload["operation"] not in self.PRESENTATION:
            return super()._operation_view(payload, identity)
        R.require(identity["principal"] == self.fixture["player"], "permission_denied")
        receipt = self.state["presentation_receipts"].get((payload["operation"], payload["original_request_id"]))
        if receipt is None:
            rid, op = payload["original_request_id"], payload["operation"]
            renewal = self.state["presentation_renewals"].get(rid) if op == "presentation.renew" else None
            jobs = [j for j in self.state["presentation_jobs"].values() if
                    (op == "presentation.acquire" and j["id"] == rid) or
                    (op == "presentation.release" and j.get("release_attempt") == rid)]
            R.require(renewal is not None or len(jobs) == 1, "permission_denied")
            if renewal is not None and renewal["state"] == "verified":
                return {"operation": op, "request_id": rid, "outcome_ref": renewal["job_id"], "state": "done"}
            # outbox 的停止/被替代不证明原设备请求从未执行；无原 ACK 或 fresh 证明仍是未知 pending。
            return {"operation": op, "request_id": rid, "outcome_ref": renewal["job_id"] if renewal else jobs[0]["id"],
                    "state": "pending"}
        return {"operation": payload["operation"], "request_id": payload["original_request_id"], "outcome_ref": receipt["ref"],
                 "state": "done" if receipt["receipt"]["applied"] else "failed"}

    def restart_device(self, device_id, *, now, authority_available=True, fault=None):
        return REC.restart_device(self, C, R, device_id, now=now, authority_available=authority_available, fault=fault)

    def sweep_presentation(self, *, now, budget=8, fault=None):
        return REC.sweep(self, C, R, now=now, budget=budget, fault=fault)

    def restart_from_mock_ledger(self, *, now, intact=True):
        restored = super().restart_from_mock_ledger(now=now, intact=intact)
        # 设备是独立效果域；不复制成新设备，也不回滚其已发生状态。
        restored.devices, restored.observations = self.devices, deepcopy(self.observations)
        restored._queue_closed()
        return restored
