"""来源披露的权威快照检查；不认证声明、不识别正文隐藏来源、不连接真实数据控制者。"""

import importlib.util
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("source_relations", Path(__file__).with_name("relations.py"))
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)
C = R.checks


def validate_disclosure(envelope, session, records, *, now):
    """records 来自目标会话的可信导入表，不允许从请求 provenance 构造。

    返回 source_id -> revision，提交时与事件一起冻结，投递时再次核对。
    只验证 chat.message 与 game.context 的显式来源，其他类别需独立入口。
    """
    kind = envelope.get("type") if isinstance(envelope, dict) else None
    R.require(kind in {"chat.message", "game.context"}, "invalid_message")
    C.validate_type("Chat" if kind == "chat.message" else "Context", envelope)
    R.require(envelope["session_id"] == session["session_id"], "permission_denied")
    sources = envelope["payload"]["provenance"]
    ids = [source["source_id"] for source in sources]
    refs = envelope["payload"]["source_refs"] if kind == "chat.message" else ids
    if kind == "game.context":
        R.require(all(source["source_kind"] == "shared_experience" for source in sources), "permission_denied")
    R.require(len(ids) == len(set(ids)) and len(refs) == len(set(refs)) and set(ids) == set(refs), "invalid_message")
    readers = R.principal_set(envelope["audience"]) | R.principal_set(session["scope"]["privacy_model"]["visible_to"])
    sender = R.principal_key(envelope["sender"])
    revisions = {}
    for source in sources:
        record = records.get(source["source_id"])
        # 缺失、跨会话、失效均不向客户端泄露来源是否存在。
        R.require(record is not None, "permission_denied")
        C.validate_type("SourceAuthorization", record)
        R.require(record["instance"] == session["scope"]["instance"] and record["session_id"] == session["session_id"], "permission_denied")
        R.require(C.codec.canonical(record["source"]) == C.codec.canonical(source), "permission_denied")
        R.require(record["state"] == "active" and now < record["expires_at"], "permission_denied")
        original = R.principal_set(source["original_disclosure_scope"])
        allowed = R.principal_set(record["allowed_readers"])
        R.require(allowed <= original and readers <= allowed, "permission_denied")
        R.require(sender in R.principal_set(record["publishers"]) and sender in allowed, "permission_denied")
        revisions[source["source_id"]] = record["revision"]
    return revisions


def disclosure_still_allowed(envelope, session, records, frozen_revisions, *, now):
    """修订变化保守停止旧事件投递；不把重新授权解释成恢复旧事件资格。"""
    try:
        return validate_disclosure(envelope, session, records, now=now) == frozen_revisions
    except (C.ContractError, C.codec.CodecError):
        return False
