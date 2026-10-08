"""密封清单的可信内存存储端口；只改假副本，不访问文件、数据库或远端。"""

from copy import deepcopy


class MemoryStore:
    """控制者/副本主体来自可信登记，不由 privacy.request 的 source_refs 声明。

    sources 和 copies 是启动时的完整固定清单。未实现持续写入、备份发现或来源拆分；
    真实适配器必须将 cutoff 接入这些路径，不能拿本模型的 done 作为全局删除证明。
    """

    def __init__(self, checks, relations, controller, sources, copies):
        self.C, self.R = checks, relations
        self.controller = deepcopy(controller)
        self.sources = deepcopy(sources)
        self.copies = deepcopy(copies)
        self.operations, self.effects = {}, {}
        self.apply_calls = self.query_calls = 0
        self.outcomes = []  # complete / pending / unknown / lost_receipt / denied，可信故障驱动。
        checks.validate_type("Principal", controller)
        for ref, record in self.sources.items():
            checks.validate_type("SourceAuthorization", record)
            relations.require(ref == record["source"]["source_id"], "invalid_arguments")
        for ref, copy in self.copies.items():
            checks.validate_type("Id", ref)
            relations.require(copy["source_id"] in self.sources, "invalid_arguments")
            checks.validate_type("Principal", copy["controller"])
            checks.validate_type("Principals", copy["subjects"])
            relations.require(copy["state"] in {"present", "deleted"}, "invalid_arguments")
            hold = copy.get("retention")
            if hold is not None:
                relations.require(hold["reason"] in {"legal_hold", "security_hold"}, "invalid_arguments")
                if "retain_until" in hold:
                    checks.validate_type("Nat", hold["retain_until"])

    def plan(self, source_refs):
        """仅取可信清单快照；没有删除、派发或自报主体权。"""
        return {ref: {"authorization": deepcopy(self.sources[ref]),
                      "copies": {key: deepcopy(value) for key, value in sorted(self.copies.items())
                                 if value["source_id"] == ref}}
                for ref in sorted(source_refs)}

    def apply(self, binding, *, now):
        op = binding["provider_operation_ref"]
        old = self.operations.get(op)
        if old is not None:
            self.R.require(self.C.codec.canonical(old["binding"]) == self.C.codec.canonical(binding), "id_conflict")
            return
        self.R.require(binding["controller"] == self.controller, "permission_denied")
        self.R.require(self.C.codec.canonical(binding["inventory"]) == self.C.codec.canonical(self.plan(binding["source_refs"])), "approval_stale")
        mode = self.outcomes.pop(0) if self.outcomes else "complete"
        self.R.require(mode in {"complete", "pending", "unknown", "lost_receipt", "denied"}, "invalid_arguments")
        self.apply_calls += 1
        self.operations[op] = {"binding": deepcopy(binding), "observation": None, "hidden": mode in {"unknown", "lost_receipt"}}
        if mode == "pending":
            self._publish(op, {"privacy_request_id": binding["privacy_request_id"], "status": "pending",
                               "controlled_scope": binding["source_refs"], "poll_after_ms": 1000})
        elif mode != "unknown":
            self.complete(op, now=now, denied=mode == "denied")

    def _publish(self, op, receipt):
        self.C.validate_type("PrivacyReceipt", receipt)
        record = self.operations[op]
        record["observation"] = {"binding": deepcopy(record["binding"]), "receipt": deepcopy(receipt),
                                 "evidence_ref": op + "-receipt"}

    def complete(self, op, *, now, denied=False):
        """原作业的可信存储完成通知，不是新 privacy 操作，也不消费第二次派发。"""
        self.C.validate_type("Nat", now)
        self.R.require(type(denied) is bool, "invalid_arguments")
        record = self.operations[op]
        old = record["observation"]
        if old is not None and old["receipt"]["status"] != "pending":
            return
        binding = record["binding"]
        self.R.require(now >= binding["accepted_at"], "temporarily_unavailable")
        exceptions, succeeded = [], 0
        for ref in binding["source_refs"]:
            expected = binding["inventory"][ref]
            current = self.plan([ref])[ref]
            # 密封清单/源声明被换掉就不能用旧操作擦除新数据或声称旧副本已清理。
            metadata = lambda value: {**value, "copies": {key: {k: v for k, v in copy.items() if k != "state"}
                                                          for key, copy in value["copies"].items()}}
            if self.C.codec.canonical(metadata(current)) != self.C.codec.canonical(metadata(expected)):
                exceptions.append({"source_id": ref, "reason": "inventory_changed"})
                continue
            if denied:
                exceptions.append({"source_id": ref, "reason": "storage_denied"})
                continue
            if binding["desired_action"] == "stop_disclosure":
                succeeded += 1
                continue
            if ref in binding["external_sources"]:
                exceptions.append({"source_id": ref, "reason": "outside_control"})
            if not current["copies"]:
                succeeded += 1  # 可信完整清单的空集合，不是失联或未知。
            for copy_id, copy in current["copies"].items():
                reason = None
                if copy["controller"] != self.controller:
                    reason = "outside_control"
                elif self.R.principal_set(copy["subjects"]) != {self.R.principal_key(binding["subject"])}:
                    reason = "shared_copy"
                elif copy["state"] == "deleted":
                    succeeded += 1
                    continue
                hold = copy.get("retention")
                active_hold = hold is not None and ("retain_until" not in hold or now < hold["retain_until"])
                if reason is not None or active_hold:
                    exception = {"source_id": ref, "reason": reason or hold["reason"]}
                    if reason is None and "retain_until" in hold:
                        exception["retain_until"] = hold["retain_until"]
                    if exception not in exceptions:
                        exceptions.append(exception)
                    continue
                if copy["state"] != "deleted":
                    # 这是不可回滚的假存储效果；authority 的结果事务失败不能恢复此副本。
                    self.copies[copy_id]["state"] = "deleted"
                    self.effects[copy_id] = {"operation_ref": op, "source_id": ref, "at": now}
                succeeded += 1
        status = "done" if not exceptions else "partial" if succeeded else "denied"
        self._publish(op, {"privacy_request_id": binding["privacy_request_id"], "status": status,
                           "controlled_scope": binding["source_refs"], "exceptions": exceptions})

    def query(self, op):
        self.query_calls += 1
        record = self.operations.get(op)
        return None if record is None or record["hidden"] else deepcopy(record["observation"])

    def verify_observation(self, observation, binding):
        """固定受信回执表代替生产端口认证；网络请求不能写入该表。"""
        record = self.operations.get(binding["provider_operation_ref"])
        return (record is not None and record["observation"] is not None and not record["hidden"] and
                self.C.codec.canonical(record["binding"]) == self.C.codec.canonical(binding) and
                self.C.codec.canonical(observation) == self.C.codec.canonical(record["observation"]))
