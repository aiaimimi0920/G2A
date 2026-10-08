"""内部错误到公开错误的保守映射；提交知识必须由权威事务层提供。

不从异常字符串或 HTTP 超时猜测事务回滚。不会将未知错误原文回显。
"""

import importlib.util
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("g2a_error_contract_checks", Path(__file__).with_name("contract_checks.py"))
checks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checks)


ALIASES = {
    "bridge_closed": "request_gone",  # 没有 queued 原子作废证明时，不保证未投递
    "decision_conflict": "id_conflict",
    "delegation_mismatch": "unauthenticated",
    "extension_unsupported": "feature_unsupported",
    "invalid_provenance": "invalid_message",
    "invalid_state": "operation_rejected",
    "launch_consent_required": "consent_required",
    "not_executable": "action_not_executable",
    "not_found": "permission_denied",  # 不按输入 ID 区分缺失对象与无权对象
    "resource_cycle": "resource_policy_denied",
    "resource_failure": "admission_failed",
    "resource_origin_denied": "resource_policy_denied",
    "resource_size_mismatch": "resource_integrity_error",
    "session_not_ready": "session_not_writable",
    "unproven_result": "execution_conflict",
    # 严格解析器的内部诊断在 wire 上不暴露输入内容。
    "invalid_number": "invalid_message", "integer_out_of_range": "invalid_message",
    "duplicate_key": "invalid_message", "invalid_unicode": "invalid_message",
    "invalid_utf8": "invalid_message", "bom_forbidden": "invalid_message",
    "invalid_json": "invalid_message", "bytes_required": "invalid_message",
    "invalid_key": "invalid_message", "invalid_type": "invalid_message",
    "depth_limit": "message_too_large", "byte_limit": "message_too_large",
    "node_limit": "message_too_large", "container_limit": "message_too_large",
    "string_limit": "message_too_large",
}


def boundary_error(internal_code, *, knowledge, request_id=None, safe_details=None):
    """knowledge = not_accepted / accepted / unknown；来自事务/效果账本而非调用方报文。"""
    if knowledge not in {"not_accepted", "accepted", "unknown"}:
        raise ValueError("invalid_commit_knowledge")
    code = ALIASES.get(internal_code, internal_code)
    if code not in checks.catalog.ERRORS:
        code = "internal_failure"
    rule = checks.catalog.ERRORS[code]
    # 已知 unknown 诊断不能被较弱的异常捕获层改写成未接受。
    if rule["outcome"] != "unknown":
        if knowledge == "unknown":
            code = "internal_failure"
        elif knowledge == "accepted" and rule["outcome"] != "accepted":
            code = "operation_failed"
        elif knowledge == "not_accepted" and rule["outcome"] == "accepted":
            code = "operation_rejected"
    rule = checks.catalog.ERRORS[code]
    error = {"code": code, **{k: rule[k] for k in ("category", "retry", "outcome")},
             "details": {} if safe_details is None else safe_details}
    if request_id is not None:
        error["request_id"] = request_id
    # safe_details 不是任意异常字典；history_gap 的视图必须先完成读权过滤。
    checks.validate_error(error)
    return error


def describe_aliases():
    return {code: {"boundary_code": target, "commit_knowledge_still_required": True}
            for code, target in sorted(ALIASES.items())}
