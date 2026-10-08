"""设备恢复和有界 outbox 驱动；复用呈现字节入口，不另造设备效果或 ACK。"""

from copy import deepcopy


def restart_device(h, C, R, device_id, *, now, authority_available, fault):
    R.require(type(authority_available) is bool and device_id in h.devices, "invalid_arguments")
    R.require(fault in (None, "before_commit", "after_commit"), "invalid_arguments")
    with h.lock:
        h._maintain(now)
        old = h.devices[device_id]
        R.require(old.epoch < C.codec.MAX_INTEGER, "resource_limit")

        def verify(occupation):
            try:
                R.require(authority_available and h.state["ledger_healthy"] and h.session is not None, "temporarily_unavailable")
                session = h.session.state["session"]
                R.validate_grant(h.session.state["grant"], session["scope"], now=now)
                job = h._find_job(occupation)
                R.require(session["state"] == "active" and occupation["generation"] == session["control_generation"] and
                          now < occupation["deadline"] <= session["lease_deadline"] and not job["release_pending"] and
                          occupation["device_epoch"] == old.epoch == job["device_epoch"], "presentation_unavailable")
                issued = [job["acquire"]] + [v["payload"] for v in h.state["presentation_renewals"].values() if v["job_id"] == job["id"]]
                # 已验证重启可以只重绑定 epoch；原 authority 证明、revision 和 deadline 仍须精确匹配。
                R.require(any({**p, "device_epoch": old.epoch} == occupation for p in issued), "permission_denied")
                h._before_acquire(job, now)
                return True
            except C.ContractError:
                return False

        device = old.restart_from_mock_ledger(now=now, verify=verify)
        h.devices[device_id] = device  # 独立设备事务已经提交；authority 回滚也不得恢复旧设备对象。

        def record():
            for job in h.state["presentation_jobs"].values():
                p = job["acquire"]
                if p["device_id"] != device_id:
                    continue
                job["device_epoch"] = device.epoch
                occupation = device.occupations.get((p["session_id"], p["generation"]))
                if occupation is not None and device.render_verified:
                    job["lease_ack"] = device._receipt(p, "restart-" + str(device.epoch), True)
                    job["render_failures"] = device.render_failures
                    for renewal in h.state["presentation_renewals"].values():
                        if (renewal["job_id"] == job["id"] and renewal["state"] in {"pending", "superseded"} and
                                {**renewal["payload"], "device_epoch": device.epoch} == occupation):
                            # 新鲜设备证明确认当前效果，不伪造丢失的原请求 ACK。
                            renewal.update(state="verified", verification=deepcopy(job["lease_ack"]))
                elif h.session is not None and p["generation"] == h.session.state["session"]["control_generation"]:
                    h.session._close("presentation_unavailable", now)
            return {"observation": h.observe_device(device_id), "kept_occupations": len(device.occupations),
                    "applied": device.render_verified, "actual_visible": device.actual_visible}
        return h._transaction(record, fault)


def sweep(h, C, R, *, now, budget, fault):
    """一次有限批次：先停止义务，后当前更新；未知结果始终重试同一 ID。"""
    R.require(type(budget) is int and 1 <= budget <= 32 and fault in (None, "before_commit", "after_commit"), "invalid_arguments")
    with h.lock:
        h._maintain(now)
        jobs = sorted(h.state["presentation_jobs"])
        if not jobs:
            return {"attempted": [], "pending_releases": 0, "pending_renewals": 0}
        start = h.state["presentation_sweep_cursor"] % len(jobs)
        order = jobs[start:] + jobs[:start]
        eligible = [jid for jid in order if h.state["presentation_jobs"][jid]["release_pending"]]
        eligible += [jid for jid in order if jid not in eligible and
                     h.state["presentation_renewals"].get(h.state["presentation_jobs"][jid].get("renewal_id"), {}).get("state") == "pending"]
        attempted = []
        for jid in eligible:
            if len(attempted) >= budget:
                break
            job = h.state["presentation_jobs"][jid]
            if now < job["retry_at"]:
                continue

            def prepare():
                job = h.state["presentation_jobs"][jid]
                h.state["presentation_sweep_cursor"] = (jobs.index(jid) + 1) % len(jobs)
                if job["release_pending"]:
                    if h._verify_expiry(job, now):
                        return None
                    op = "presentation.release"
                    device = h.devices[job["acquire"]["device_id"]]
                    authority_full = sum(operation == op for operation, _ in h.state["presentation_receipts"]) >= device.RELEASE_RECEIPTS
                    device_full = sum(operation == op for operation, _ in device.receipts) >= device.RELEASE_RECEIPTS
                    if authority_full or device_full:
                        # 本地收敛独立于 wire 收据容量；事实只覆盖当前代，不伪造旧 ACK。
                        return {"local_reconciliation": True}
                    rid = job.get("release_attempt")
                    prior = h.state["presentation_receipts"].get((op, rid))
                    if rid is None or prior is not None:
                        job["release_attempts"] += 1
                        rid = "compensate-" + jid + "-" + str(job["release_attempts"])
                        job["release_attempt"] = rid
                    payload = {key: job["acquire"][key] for key in ("session_id", "generation", "device_id")}
                else:
                    op, rid = "presentation.renew", job["renewal_id"]
                    payload = deepcopy(h.state["presentation_renewals"][rid]["payload"])
                return {"version": h.session.state["session"]["scope"]["version"], "operation": op,
                        "request_id": rid, "payload": payload, "extensions": {}}

            request = h._transaction(prepare)
            if request is None:
                attempted.append({"job_id": jid, "outcome": "verified_expiry"})
                continue
            if "local_reconciliation" in request:
                device = h.devices[job["acquire"]["device_id"]]
                evidence = device.reconcile_stop(job["acquire"], now=now)
                applied = evidence is not None
                def record_reconciliation():
                    current = h.state["presentation_jobs"][jid]
                    if applied:
                        current.update(release_evidence=evidence, release_pending=False)
                    current["retry_at"] = now if applied else now + 1000
                h._transaction(record_reconciliation, fault)
                attempted.append({"job_id": jid, "outcome": "verified_reconciliation" if applied else "retry_pending"})
                continue
            try:
                reply = C.codec.decode(h.submit(C.codec.canonical(request), "presentation-fixture", now=now, fault=fault))
                receipt = reply["result"]
                epoch = h.devices[request["payload"]["device_id"]].epoch
                outcome = "applied" if receipt["applied"] and receipt["device_epoch"] == epoch else "retry_pending"
            except C.ContractError as error:
                outcome = error.code  # 只有可信 ACK/到期证明才能完成；错误和超时不生成成功回执。

            def schedule():
                current = h.state["presentation_jobs"][jid]
                current["retry_at"] = now + 1000 if outcome != "applied" else now
                current["last_attempt_outcome"] = outcome
            h._transaction(schedule)
            attempted.append({"job_id": jid, "operation": request["operation"], "request_id": request["request_id"], "outcome": outcome})
        return {"attempted": attempted,
                "pending_releases": sum(j["release_pending"] for j in h.state["presentation_jobs"].values()),
                "pending_renewals": sum(v["state"] == "pending" for v in h.state["presentation_renewals"].values())}
