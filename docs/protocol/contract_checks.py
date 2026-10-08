"""契约的结构与有限关系检查；不冒充身份适配器、数据库或世界执行器。

verified role/lane 必须由外部认证路由提供，不能从网络 payload 直接取值。
jsonschema 使用项目已有依赖范围；此模块不访问远程 schema。
"""

import importlib.util
from copy import deepcopy
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


ROOT = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


catalog = _load("g2a_design_catalog", "contracts.py")
codec = _load("g2a_design_contract_codec", "codec.py")
SCHEMA = catalog.schema()


class ContractError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def validate_type(name, value):
    if name not in SCHEMA["$defs"]:
        raise ContractError("unknown_contract")
    # 先排除 Python 的 float/bool 误作整数及 codec 不允许的其他值。
    codec.canonical(value)
    try:
        Draft202012Validator({**SCHEMA, "$ref": "#/$defs/" + name}).validate(value)
    except ValidationError:
        raise ContractError("invalid_message") from None


def validate_features(features, *, durable=False):
    validate_type("Features", features)
    chosen = set(features)
    if not {"core.session", "core.events"} <= chosen:
        raise ContractError("feature_unsupported")
    for feature in chosen:
        if not set(catalog.FEATURE_DEPENDENCIES[feature]) <= chosen:
            raise ContractError("feature_unsupported")
    if "resume" in chosen and not durable:
        raise ContractError("resume_denied")


def authorize_route(operation, verified_role, actual_lane, features):
    metadata = catalog.OPERATIONS.get(operation)
    if metadata is None:
        raise ContractError("unsupported_operation")
    if verified_role not in metadata["roles"]:
        raise ContractError("permission_denied")
    expected_lane = "management" if verified_role == "game" else metadata["lane"]
    if actual_lane != expected_lane:
        raise ContractError("permission_denied")
    if metadata["feature"] not in features:
        raise ContractError("feature_unsupported")


def authorize_relay_inner(outer_role, inner_role, operation, features):
    metadata = catalog.OPERATIONS.get(operation)
    if metadata is None:
        raise ContractError("unsupported_operation")
    # outer/inner 均为独立验证结果；不能信任请求自报角色。
    if outer_role == "relay_agent":
        permitted = {"agent", "companion_control", "results_reader"}
    elif outer_role == "relay_controller":
        permitted = {"player"}
    else:
        raise ContractError("permission_denied")
    if inner_role not in permitted or metadata["lane"] not in {"control", "data", "results"}:
        raise ContractError("permission_denied")
    authorize_route(operation, inner_role, metadata["lane"], features)


def validate_request(raw):
    """结构及有限字段关系检查；不代表运行扩展已获批准或已执行。"""
    request = codec.decode(raw)
    validate_type("OperationRequest", request)
    name, payload = request["operation"], request["payload"]
    if name == "offer.decide":
        has_expiry = "rule_expires_at" in payload
        has_duration = "maximum_grant_duration_ms" in payload
        if has_expiry != payload["remember"] or has_duration != payload["remember"]:
            raise ContractError("invalid_message")
        if not payload["allow"] and (payload["remember"] or payload["launch_permission"]):
            raise ContractError("invalid_message")
    envelope = payload.get("envelope") if name == "player_chat.forward" else payload
    if name in {"chat.send", "action.request", "action.cancel", "context.publish", "player_chat.forward"}:
        if envelope["version"] != request["version"]:
            raise ContractError("unsupported_version")
        if envelope["type"] == "chat.message" and envelope["payload"]["channel"] == "team":
            if "expected_membership_revision" not in envelope:
                raise ContractError("invalid_message")
    if name == "session.events" and payload["session_id"] != payload["cursor"]["session_id"]:
        raise ContractError("invalid_cursor")
    if name in {"presentation.acquire", "presentation.renew"} and payload["device_id"] != payload["terms"]["device_id"]:
        raise ContractError("invalid_message")
    if name == "relay.call":
        inner = validate_request(codec.canonical(payload["call"]["operation_request"]))
        if inner["version"] != request["version"]:
            raise ContractError("unsupported_version")
    if name == "capability.replace":
        ids = [definition["id"] for definition in payload["definitions"]]
        if len(ids) != len(set(ids)):
            raise ContractError("invalid_message")
        for definition in payload["definitions"]:
            validate_value_schema(definition["parameters"], require_object=True)
            validate_value_schema(definition["result_schema"])
    return request


def validate_active_request(raw, *, selected_extensions, supported_extensions):
    """仅装配请求结构与扩展启用检查，不替代认证、事务或扩展自身语义执行。

    selected_extensions 来自已验证的冻结授权；supported_extensions 为本地已实现的
    (name, exact_version) 集合，均不得由请求自报。本版 value 是冻结配置，不是动态载荷。
    """
    request = validate_request(raw)
    validate_type("Extensions", selected_extensions)
    supported = set(supported_extensions)
    if request["operation"] in catalog.MESSAGE_OPERATIONS:
        envelope = request["payload"].get("envelope") if request["operation"] == "player_chat.forward" else request["payload"]
        offered = envelope["extensions"]
    else:
        offered = request["extensions"]
    # 核心止损路径不依赖可选处理器存活；仅空扩展请求可走此路径，认证/归属照常。
    if not offered and request["operation"] in {
            "session.close", "permission.revoke", "action.cancel", "presentation.release", "relay.revoke"}:
        return request, {}
    for name, selected in selected_extensions.items():
        if selected["required"] and (name not in offered or (name, selected["version"]) not in supported):
            raise ContractError("feature_unsupported")
    activated = {}
    for name, value in offered.items():
        selected = selected_extensions.get(name)
        if selected is not None and codec.canonical(value) != codec.canonical(selected):
            raise ContractError("approval_stale")
        if selected is None or (name, value["version"]) not in supported:
            if value["required"]:
                raise ContractError("feature_unsupported")
            continue
        activated[name] = deepcopy(value)
    # 未激活扩展仍保留在 request 中参与摘要；返回独立快照，不让处理器改写原请求。
    return request, activated


def validate_value_schema(schema, *, require_object=False):
    """有限无引用/正则/组合器子集；与 g2a-value-schema-1 一致。"""
    validate_type("ValueSchema", schema)
    kind = schema["type"]
    if require_object and kind != "object":
        raise ContractError("invalid_arguments")
    allowed = {"type", "enum", "const"}
    specific = {"object": {"properties", "required", "additionalProperties"},
                "array": {"items", "minItems", "maxItems"},
                "string": {"minLength", "maxLength"},
                "integer": {"minimum", "maximum"}, "null": set(), "boolean": set()}
    if not schema.keys() <= allowed | specific[kind]:
        raise ContractError("invalid_arguments")
    if kind == "object":
        if not specific[kind] <= schema.keys():
            raise ContractError("invalid_arguments")
        if not set(schema["required"]) <= schema["properties"].keys():
            raise ContractError("invalid_arguments")
        for child in schema["properties"].values():
            validate_value_schema(child)
    if kind == "array":
        if "items" not in schema or "maxItems" not in schema:
            raise ContractError("invalid_arguments")
        validate_value_schema(schema["items"])
    if kind == "string" and "maxLength" not in schema:
        raise ContractError("invalid_arguments")
    for lower, upper in (("minimum", "maximum"), ("minLength", "maxLength"), ("minItems", "maxItems")):
        if lower in schema and upper in schema and schema[lower] > schema[upper]:
            raise ContractError("invalid_arguments")
    # enum/const 必须可满足字段自身约束，不能发布永远无解的动作参数定义。
    bare = {key: value for key, value in schema.items() if key not in {"enum", "const"}}
    validator = Draft202012Validator(bare)
    values = schema.get("enum", []) + ([schema["const"]] if "const" in schema else [])
    if any(not validator.is_valid(value) for value in values):
        raise ContractError("invalid_arguments")
    if "const" in schema and "enum" in schema and not Draft202012Validator({"enum": schema["enum"]}).is_valid(schema["const"]):
        raise ContractError("invalid_arguments")


def validate_action_value(schema, value):
    validate_value_schema(schema)
    codec.canonical(value)
    if not Draft202012Validator(schema).is_valid(value):
        raise ContractError("invalid_arguments")


def validate_error(error):
    validate_type("Error", error)
    rule = catalog.ERRORS[error["code"]]
    for key in ("category", "retry", "outcome"):
        if error[key] != rule[key]:
            raise ContractError("invalid_error_contract")
    if "retry_after_ms" in error and error["retry"] != "same_request":
        raise ContractError("invalid_error_contract")
    history_keys = {"snapshot", "next_cursor", "unresolved_actions"}
    if error["code"] == "history_gap":
        if not history_keys <= error["details"].keys():
            raise ContractError("invalid_error_contract")
        details = error["details"]
        snapshot = details["snapshot"]
        unresolved = [value["request_id"] for value in snapshot["actions"]
                      if value["state"] in {"pending", "executing", "unknown"}]
        if (details["next_cursor"] != snapshot["cursor"]
                or len(details["unresolved_actions"]) != len(set(details["unresolved_actions"]))
                or set(details["unresolved_actions"]) != set(unresolved)):
            raise ContractError("invalid_error_contract")
    elif history_keys & error["details"].keys():
        raise ContractError("invalid_error_contract")
    return rule["http_status"]


def validate_reply(operation, original_request_id, reply):
    # operation 来自已保存请求，不要求在实际响应中增加 operation 字段。
    if type(reply) is not dict or "operation" in reply:
        raise ContractError("invalid_message")
    validate_type("ReplyEnvelope", {"operation": operation, **reply})
    if reply["request_id"] != original_request_id:
        raise ContractError("invalid_message")
    if "error" in reply:
        error = reply["error"]
        if "request_id" in error and error["request_id"] != original_request_id:
            raise ContractError("invalid_error_contract")
        validate_error(error)
    return reply


def validate_statement(statement):
    """校验声明逻辑，不能替代对 artifact 内容或签署者身份的独立复核。"""
    validate_type("ConformanceStatement", statement)
    validate_features(statement["features"], durable=statement["ledger_durability"] == "durable")
    records = statement["coverage"]
    operations = [entry["operation"] for entry in records]
    if len(operations) != len(set(operations)):
        raise ContractError("invalid_conformance_statement")
    evidence = {entry["id"]: entry for entry in statement["evidence"]}
    if len(evidence) != len(statement["evidence"]):
        raise ContractError("invalid_conformance_statement")
    for record in records:
        if not set(record["evidence_ids"]) <= evidence.keys():
            raise ContractError("invalid_conformance_statement")
        if record["verdict"] == "passed" and not record["evidence_ids"]:
            raise ContractError("invalid_conformance_statement")
        if record["verdict"] == "passed":
            cited = [evidence[key] for key in record["evidence_ids"]]
            if any(not item["case_refs"] for item in cited):
                raise ContractError("invalid_conformance_statement")
            kinds = {item["kind"] for item in cited}
            if statement["assurance"] == "design" and not kinds & {"symbolic", "model"}:
                raise ContractError("invalid_conformance_statement")
            if statement["assurance"] == "mock" and "model" not in kinds:
                raise ContractError("invalid_conformance_statement")
        if record["verdict"] == "passed" and statement["assurance"] in {"adapter", "deployment"}:
            kinds = {evidence[key]["kind"] for key in record["evidence_ids"]}
            required = statement["assurance"]
            if required not in kinds:
                raise ContractError("invalid_conformance_statement")
    if statement["assurance"] in {"adapter", "deployment"}:
        if statement["subject"]["artifact_kind"] != "implementation" or not statement["wire_versions"]:
            raise ContractError("invalid_conformance_statement")
    if statement["assurance"] == "deployment" and statement["trust_profiles"] == ["test-enrolled"]:
        raise ContractError("invalid_conformance_statement")
    if statement["status"] == "passed":
        if statement["reviewed_by"] == "not-reviewed":
            raise ContractError("invalid_conformance_statement")
        if not records or any(entry["verdict"] != "passed" for entry in records):
            raise ContractError("invalid_conformance_statement")
        required_operations = set(catalog.OPERATIONS) if statement["subject"]["artifact_kind"] == "design" else {
            name for name, metadata in catalog.OPERATIONS.items()
            if metadata["feature"] in statement["features"] and set(metadata["roles"]) & set(statement["roles"])
        }
        if not required_operations <= set(operations):
            raise ContractError("invalid_conformance_statement")
        if statement["subject"]["artifact_kind"] != "design" and not statement["roles"]:
            raise ContractError("invalid_conformance_statement")
        if statement["subject"]["artifact_kind"] != "design" and not all(
                statement[field] for field in ("wire_versions", "bindings", "trust_profiles")):
            raise ContractError("invalid_conformance_statement")
