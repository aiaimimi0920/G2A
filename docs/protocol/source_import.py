"""测试身份端口后的来源导入：固定权威证据表，不实现远程签名验证或授权 UI。"""

from copy import deepcopy
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("import_sources", Path(__file__).with_name("source_authorization.py"))
S = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(S)
C, R = S.C, S.R


class SourceImporter:
    def __init__(self, verified_evidence):
        # 证据表只能由可信端口提供，不能从待导入 record 自行构造。
        self.evidence = deepcopy(verified_evidence)
        self.records = {}

    def import_record(self, record, *, verified_controller, session, now):
        C.validate_type("SourceAuthorization", record)
        R.require(record["controller"] == verified_controller, "permission_denied")
        proof = self.evidence.get(record["evidence_ref"])
        R.require(proof is not None, "permission_denied")
        R.require(proof["controller"] == verified_controller and not proof["revoked"] and now < proof["expires_at"], "permission_denied")
        R.require(record["instance"] == session["scope"]["instance"] == proof["instance"] and
                  record["session_id"] == session["session_id"] == proof["session_id"], "permission_denied")
        R.require(C.codec.canonical(record["source"]) == C.codec.canonical(proof["source"]), "permission_denied")
        R.require(record["state"] == "active" and now < record["expires_at"] <= proof["expires_at"], "permission_denied")
        R.require(R.principal_set(record["publishers"]) <= R.principal_set(proof["publishers"]), "permission_denied")
        R.require(R.principal_set(record["allowed_readers"]) <= R.principal_set(proof["allowed_readers"]) &
                  R.principal_set(record["source"]["original_disclosure_scope"]), "permission_denied")
        # 单导入器按 (instance, session, local handle) 隔离；不把 source_id 当全局 ID。
        key = (C.codec.canonical(record["instance"]), record["session_id"], record["source"]["source_id"])
        old = self.records.get(key)
        if old is not None:
            R.require(old["controller"] == record["controller"], "permission_denied")
            if old["revision"] == record["revision"]:
                R.require(C.codec.canonical(old) == C.codec.canonical(record), "id_conflict")
                return deepcopy(old)
            R.require(record["revision"] > old["revision"], "approval_stale")
            R.require(C.codec.canonical(record["source"]) == C.codec.canonical(old["source"]), "approval_stale")
            R.require(R.principal_set(record["allowed_readers"]) <= R.principal_set(old["allowed_readers"]) and
                      R.principal_set(record["publishers"]) <= R.principal_set(old["publishers"]) and
                      record["expires_at"] <= old["expires_at"], "permission_denied")
        self.records[key] = deepcopy(record)
        return deepcopy(record)

    def snapshot(self, session, *, now):
        """接收事务从可信端口重新取快照；真实跨服务撤销同步仍需 adapter 兑现。"""
        result = {}
        prefix = (C.codec.canonical(session["scope"]["instance"]), session["session_id"])
        for key, record in self.records.items():
            if key[:2] != prefix:
                continue
            proof = self.evidence.get(record["evidence_ref"])
            if (proof is None or proof["revoked"] or now >= proof["expires_at"]) and record["state"] == "active":
                record["state"] = "revoked"
                record["revision"] += 1
            result[key[2]] = deepcopy(record)
        return result
