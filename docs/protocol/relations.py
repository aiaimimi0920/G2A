"""跨对象契约参考检查；输入的身份/描述/成员记录必须来自可信端口。

这些函数不验证密码学、不读取网络、不替换原子状态机。传入一组自洽但伪造的
记录并不代表获得授权；调用者必须在同一权威事务快照中使用它们。
"""

import importlib.util
from pathlib import Path
from urllib.parse import urlsplit


SPEC = importlib.util.spec_from_file_location("g2a_relations_checks", Path(__file__).with_name("contract_checks.py"))
checks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checks)
codec = checks.codec
ContractError = checks.ContractError


def require(condition, code):
    if not condition:
        raise ContractError(code)


def principal_key(value):
    checks.validate_type("Principal", value)
    return value["issuer"], value["subject"], value["kind"]


def principal_set(values):
    return {principal_key(value) for value in values}


def validate_descriptor(descriptor):
    checks.validate_type("Descriptor", descriptor)
    require(descriptor["instance"]["game"]["kind"] == "game", "invalid_message")
    checks.validate_features(descriptor["supported_features"], durable=True)
    require("resume" not in descriptor["supported_features"] or "durable" in descriptor["ledger_durabilities"], "feature_unsupported")
    require(set(descriptor["required_features"]) <= set(descriptor["supported_features"]), "feature_unsupported")
    require({"core.session", "core.events"} <= set(descriptor["required_features"]), "feature_unsupported")
    ids = [item["id"] for item in descriptor["actions"]]
    require(len(ids) == len(set(ids)), "invalid_message")
    require(not ids or "actions" in descriptor["supported_features"], "feature_unsupported")
    for definition in descriptor["actions"]:
        checks.validate_value_schema(definition["parameters"], require_object=True)
        checks.validate_value_schema(definition["result_schema"])
    for feature, field in (("avatar", "avatar_requirements"), ("presentation", "presentation_requirements")):
        require(field not in descriptor or feature in descriptor["supported_features"], "feature_unsupported")


def _extensions(selected, left, right):
    for name in left.keys() | right.keys():
        lhs, rhs = left.get(name), right.get(name)
        compatible = lhs is not None and rhs is not None and lhs["version"] == rhs["version"] and lhs["value"] == rhs["value"]
        required = (lhs or {}).get("required", False) or (rhs or {}).get("required", False)
        if required:
            require(compatible and name in selected, "feature_unsupported")
        if name in selected:
            require(compatible, "feature_unsupported")
            require(selected[name] == {"version": lhs["version"], "value": lhs["value"], "required": required}, "approval_stale")
    require(selected.keys() <= left.keys() & right.keys(), "feature_unsupported")


def validate_scope(scope, descriptor, requested, *, now, verified_audiences, supported_resource_profiles=()):
    """只用于批准/邀请/首次加入的冻结检查；活动会话动态缩权不能复用完整 revision 检查。"""
    checks.validate_type("Scope", scope)
    checks.validate_type("Requested", requested)
    checks.validate_features(requested["supported_features"], durable=True)
    require(set(requested["required_features"]) <= set(requested["supported_features"]), "feature_unsupported")
    validate_descriptor(descriptor)
    require(scope["player"]["kind"] == "player" and scope["agent"]["kind"] == "agent", "permission_denied")
    require(scope["player"] == requested["player"] and scope["agent"] == requested["agent"], "permission_denied")
    require(scope["instance"] == descriptor["instance"], "approval_stale")
    require(scope["descriptor_revision"] == descriptor["revision"], "approval_stale")
    require(scope["version"] in descriptor["supported_versions"] and scope["version"] in requested["supported_versions"], "unsupported_version")
    require(scope["binding"] in descriptor["bindings"] and scope["binding"] in requested["bindings"], "negotiation_failed")
    require(scope["trust_profile"] in descriptor["trust_profiles"] and scope["trust_profile"] in requested["trust_profiles"], "trust_profile_unsupported")
    require(scope["ledger_durability"] == requested["ledger_durability"], "negotiation_failed")
    require(scope["ledger_durability"] in descriptor["ledger_durabilities"], "negotiation_failed")
    checks.validate_features(scope["features"], durable=scope["ledger_durability"] == "durable")
    features = set(scope["features"])
    require(features <= set(descriptor["supported_features"]) & set(requested["supported_features"]), "feature_unsupported")
    require(set(descriptor["required_features"]) | set(requested["required_features"]) <= features, "feature_unsupported")
    require(scope["features"] == sorted(features), "invalid_message")
    definitions = {item["id"]: item for item in descriptor["actions"]}
    require(set(scope["action_ids"]) <= definitions.keys() & set(requested["action_ids"]), "permission_denied")
    require(not scope["action_ids"] or "actions" in features, "feature_unsupported")
    require(scope["approved_action_digests"] == {
        name: codec.digest("action-definition", definitions[name]) for name in scope["action_ids"]
    }, "approval_stale")
    for name in scope["action_ids"]:
        require(scope["agent"] in definitions[name]["allowed_actors"], "permission_denied")
    require(set(scope["context_categories"]) <= set(descriptor["context_categories"]) & set(requested["context_categories"]), "permission_denied")
    audience = principal_set(scope["audiences"])
    require(audience <= principal_set(requested["audiences"]) & principal_set(verified_audiences), "permission_denied")
    require({principal_key(scope["player"]), principal_key(scope["agent"])} <= audience, "permission_denied")
    if "team" not in features:
        require(audience == {principal_key(scope["player"]), principal_key(scope["agent"])}, "feature_unsupported")
    for field in ("action_ids", "context_categories"):
        require(scope[field] == sorted(scope[field]), "invalid_message")
    require(scope["audiences"] == sorted(scope["audiences"], key=codec.canonical), "invalid_message")
    require(scope["privacy_model"] == descriptor["privacy_model"] == requested["privacy_model"], "negotiation_failed")
    visible = principal_set(scope["privacy_model"]["visible_to"])
    require(principal_key(scope["instance"]["game"]) in visible and principal_key(scope["agent"]) in visible, "negotiation_failed")
    if scope["binding"]["kind"] == "outbound-relay":
        require("relay_identity" in scope["binding"] and scope["privacy_model"]["relay_plaintext"], "negotiation_failed")
        require(principal_key(scope["binding"]["relay_identity"]) in visible, "negotiation_failed")
    else:
        require("relay_identity" not in scope["binding"] and not scope["privacy_model"]["relay_plaintext"], "negotiation_failed")
    expected_policy = {}
    for policy in (requested["companion_defaults"], descriptor["policy_defaults"], requested["policy"]):
        expected_policy.update({key: value for key, value in policy.items() if key != "extensions"})
    require({key: value for key, value in scope["effective_policy"].items() if key != "extensions"} == expected_policy, "approval_stale")
    # 扩展内容需双方精确协商；不由默认字典浅拷贝悄悄启用新策略。
    _extensions(scope["extensions"], descriptor["extensions"], requested["extensions"])
    _extensions(scope["effective_policy"]["extensions"], descriptor["policy_defaults"]["extensions"], requested["policy"]["extensions"])
    for name, extension in requested["companion_defaults"]["extensions"].items():
        if extension["required"]:
            chosen = scope["effective_policy"]["extensions"].get(name)
            require(chosen is not None and chosen["version"] == extension["version"] and chosen["value"] == extension["value"], "negotiation_failed")
    require(scope["created_at"] <= now < scope["expires_at"] <= scope["created_at"] + requested["maximum_grant_duration_ms"], "invitation_expired")
    for field, value in scope["limits"].items():
        require(value <= min(descriptor["limits"][field], requested["limits"][field]), "negotiation_failed")
    require(scope["result_retention_ms"] == scope["limits"]["result_retention_ms"], "negotiation_failed")
    require(scope["limits"]["receipt_retention_ms"] >= scope["expires_at"] - scope["created_at"] + scope["limits"]["resume_window_ms"], "negotiation_failed")
    if "resume" not in features:
        require(scope["limits"]["resume_window_ms"] == 0, "feature_unsupported")
    if "multi-session" not in features:
        require(scope["limits"]["session_count"] == 1, "feature_unsupported")
    for feature, field in (("avatar", "avatar_selection"), ("assets", "resource_policy"), ("presentation", "presentation_terms")):
        require(field not in scope or feature in features, "feature_unsupported")
    if "avatar" in features:
        require("avatar_selection" in scope, "avatar_required")
        game_avatar = descriptor.get("avatar_requirements", {}).get("game_avatar")
        selected = requested.get("forced_avatar", game_avatar or requested.get("default_avatar"))
        require(scope["avatar_selection"] == selected, "avatar_incompatible")
        accepted_formats = descriptor.get("avatar_requirements", {}).get("accepted_formats", [])
        if selected["kind"] == "manifest":
            require("assets" in features and "resource_policy" in scope, "feature_unsupported")
            require(selected["manifest"]["media_type"] in accepted_formats, "avatar_incompatible")
            validate_manifest_closure(selected["manifest"], scope["resource_policy"], supported_profiles=supported_resource_profiles)
        else:
            require(selected["format"] in accepted_formats, "avatar_incompatible")
    if "presentation" in features:
        terms = requested.get("presentation_terms")
        require(terms is not None and scope.get("presentation_terms") == terms, "negotiation_failed")
        if "presentation_requirements" in descriptor:
            require(scope["presentation_terms"] == descriptor["presentation_requirements"], "negotiation_failed")


def validate_grant(grant, scope, *, now):
    checks.validate_type("GrantRecord", grant)
    require(grant["scope"] == scope and grant["scope_digest"] == codec.digest("scope", scope), "approval_stale")
    require(grant["approver"] == scope["player"], "permission_denied")
    require(grant["state"] == "active", "grant_revoked")
    require(scope["created_at"] <= now < grant["expires_at"] <= scope["expires_at"], "grant_revoked")


def validate_session_write(session, grant, *, now, principal, generation, transport_epoch, device_id=None):
    checks.validate_type("SessionView", session)
    validate_grant(grant, session["scope"], now=now)
    require(session["grant_id"] == grant["grant_id"], "permission_denied")
    require(session["state"] == "active", "session_closed")
    require(session["ready"], "session_not_writable")
    require(now < session["lease_deadline"] <= grant["expires_at"], "session_closed")
    require(session["instance_epoch"] == session["scope"]["instance"]["epoch"], "stale_controller")
    require(principal == session["scope"]["agent"], "permission_denied")
    require(session["transport_epoch"] == transport_epoch, "stale_transport")
    require(session["control_generation"] == generation, "stale_controller")
    require(session.get("controller_device") == device_id, "permission_denied")


def validate_envelope_audience(envelope, session, *, authenticated_sender, current_members):
    """current_members 的 key 为身份三元组，value 为权威成员代次；不接受客户端的成员映射。"""
    checks.validate_type("Envelope", envelope)
    if envelope["type"] == "chat.message":
        checks.validate_type("Chat", envelope)
    require(envelope["session_id"] == session["session_id"] and envelope["version"] == session["scope"]["version"], "permission_denied")
    require(envelope["sender"] == authenticated_sender, "permission_denied")
    if envelope["type"] == "chat.message":
        sender = principal_key(authenticated_sender)
        require(sender in current_members and sender in principal_set(session["scope"]["audiences"]), "permission_denied")
        if envelope["payload"]["channel"] == "private":
            require(sender in {principal_key(session["scope"]["player"]), principal_key(session["scope"]["agent"])},
                    "permission_denied")
    audience = principal_set(envelope["audience"])
    require(audience <= principal_set(session["scope"]["audiences"]) & current_members.keys(), "permission_denied")
    if envelope["payload"].get("channel") == "team":
        require("team" in session["scope"]["features"], "feature_unsupported")
        require(envelope.get("expected_membership_revision") == session["membership_revision"], "membership_conflict")
    if envelope["payload"].get("channel") == "private":
        require(audience <= {principal_key(session["scope"]["player"]), principal_key(session["scope"]["agent"])}, "permission_denied")
    return {key: current_members[key] for key in audience}


def can_deliver(principal, frozen_members, current_members, currently_allowed):
    key = principal_key(principal)
    return (key in frozen_members and frozen_members[key] == current_members.get(key)
            and key in principal_set(currently_allowed))


def validate_result_read(grant, session_id, action_id, *, now, access_revision, revoked=False):
    checks.validate_type("ReadGrant", grant)
    require(not revoked and grant["access_revision"] == access_revision, "permission_denied")
    require(grant["session_id"] == session_id and action_id in grant["action_ids"], "permission_denied")
    require(now <= grant["read_until"], "result_expired")
    # 本函数只接收认证层为原主体解析的读授权，不恢复写权，也不续租。


def validate_manifest_closure(manifest, policy, *, supported_profiles):
    """只验证下载前的图/来源声明，不证明 DNS、实际字节、解压或 parser 安全。"""
    checks.validate_type("Manifest", manifest)
    checks.validate_type("ResourcePolicy", policy)
    approved = set(policy["approved_origins"])
    seen_ids, seen_contents, active, heights = {}, set(), set(), {}
    total, count = 0, 0

    def origin(url):
        try:
            parsed = urlsplit(url)
            port = parsed.port
        except ValueError:
            raise ContractError("resource_policy_denied") from None
        require(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password,
                "resource_policy_denied")
        require(not parsed.fragment, "resource_policy_denied")
        host = parsed.hostname.lower()
        if ":" in host:
            host = "[" + host + "]"
        return "https://" + host + (":" + str(port) if port not in (None, 443) else "")

    for value in approved:
        parsed = urlsplit(value)
        require(origin(value) == value and parsed.path in ("", "/") and not parsed.query, "resource_policy_denied")

    def visit(item, depth):
        nonlocal total, count
        require(depth <= policy["max_depth"], "resource_policy_denied")
        asset_id, content = item["asset_id"], item["content_digest"]
        require(asset_id not in active, "resource_policy_denied")
        if asset_id in seen_ids:
            require(codec.canonical(seen_ids[asset_id]) == codec.canonical(item), "resource_integrity_error")
            # 缓存可免重复计费，不能免除新路径上整棵子树的深度检查。
            require(depth + heights[asset_id] - 1 <= policy["max_depth"], "resource_policy_denied")
            return heights[asset_id]
        require(content not in seen_contents, "resource_policy_denied")
        seen_ids[asset_id] = item
        seen_contents.add(content)
        active.add(asset_id)
        count += 1
        total += item["byte_size"]
        require(count - 1 <= policy["max_dependencies"] and total <= policy["max_total_bytes"], "resource_policy_denied")
        require(item["media_type"] in policy["accepted_media_types"], "avatar_incompatible")
        require((item["compatibility"]["profile"], item["compatibility"]["revision"]) in supported_profiles, "avatar_incompatible")
        require(set(item["approved_origins"]) <= approved and "locator" in item, "resource_policy_denied")
        require(origin(item["locator"]) in set(item["approved_origins"]), "resource_policy_denied")
        height = 1
        for child in item["dependency_manifests"]:
            height = max(height, 1 + visit(child, depth + 1))
        active.remove(asset_id)
        heights[asset_id] = height
        return height

    visit(manifest, 1)
    return {"manifest_count": count, "declared_bytes": total}
