"""下一版草案的声明式字段/操作目录；仅生成规范，不是服务器或旧 SDK。

schema 负责结构，授权、身份、关系约束和状态转移仍按语义契约检查。
运行本文件只在 stdout 输出 JSON；生成产物由独立命令显式写入。
"""

import json


def ref(name):
    return {"$ref": "#/$defs/" + name}


def enum(*values):
    return {"enum": list(values)}


def array(item, minimum=0, maximum=4096, unique=False):
    return {"type": "array", "items": ref(item) if isinstance(item, str) else item,
            "minItems": minimum, "maxItems": maximum, "uniqueItems": unique}


def obj(**fields):
    return {"type": "object", "additionalProperties": False,
            "properties": {key.rstrip("?"): ref(value) if isinstance(value, str) else value
                           for key, value in fields.items()},
            "required": [key for key in fields if not key.endswith("?")]}


def choice(*items):
    return {"oneOf": [ref(item) if isinstance(item, str) else item for item in items]}


TYPES = {
    "Id": {"type": "string", "minLength": 1, "maxLength": 128,
           "pattern": "^[A-Za-z0-9][A-Za-z0-9._~-]*$"},
    "Text": {"type": "string", "maxLength": 65536},
    "Name": {"type": "string", "minLength": 1, "maxLength": 256},
    "Version": {"type": "string", "minLength": 1, "maxLength": 64},
    "Digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    "Nat": {"type": "integer", "minimum": 0, "maximum": 9007199254740991},
    "Revision": {"type": "integer", "minimum": 1, "maximum": 9007199254740991},
    "Bool": {"type": "boolean"},
    "Null": {"type": "null"},
    "Secret": {"type": "string", "minLength": 1, "maxLength": 4096},
    "Json": {"anyOf": [{"type": "null"}, {"type": "boolean"}, ref("Text"),
                         {"type": "integer", "minimum": -9007199254740991,
                          "maximum": 9007199254740991},
                         array("Json"), ref("JsonObject")]},
    "JsonObject": {"type": "object", "maxProperties": 4096,
                   "propertyNames": ref("Name"), "additionalProperties": ref("Json")},
    "ValueSchema": obj(type=enum("null", "boolean", "string", "integer", "array", "object"),
                       **{"enum?": array("Json", 1, 256, True), "const?": "Json",
                          "properties?": {"type": "object", "maxProperties": 256, "propertyNames": ref("Name"),
                                          "additionalProperties": ref("ValueSchema")},
                          "required?": array("Name", 0, 256, True), "additionalProperties?": {"const": False},
                          "items?": "ValueSchema", "minItems?": "Nat", "maxItems?": "Nat",
                          "minLength?": "Nat", "maxLength?": "Nat",
                          "minimum?": {"type": "integer", "minimum": -9007199254740991, "maximum": 9007199254740991},
                          "maximum?": {"type": "integer", "minimum": -9007199254740991, "maximum": 9007199254740991}}),
    "Extensions": {"type": "object", "maxProperties": 64,
                   "propertyNames": {"type": "string", "maxLength": 256,
                                     "pattern": "^[a-z][a-z0-9-]*(\\.[a-z][a-z0-9-]*)+$"},
                   "additionalProperties": obj(version="Version", required="Bool", value="Json")},
    "Principal": obj(issuer="Name", subject="Name", kind=enum("player", "agent", "game", "service")),
    "Instance": obj(game="Principal", instance_id="Id", epoch="Id"),
    "Binding": obj(kind=enum("direct-http", "outbound-relay", "local-ipc"), endpoint="Name",
                   peer_identity="Principal", **{"relay_identity?": "Principal"}),
    "TrustProfile": enum("local-verified", "provider-verified", "test-enrolled"),
    "Feature": enum("core.session", "core.events", "actions", "team", "avatar", "assets",
                    "presentation", "resume", "multi-session", "handoff", "privacy-request"),
    "Features": array("Feature", 2, 11, True),
    "Principals": array("Principal", 1, 256, True),
    "Limits": obj(message_bytes="Revision", event_page_size="Revision", max_pending_actions="Nat",
                  session_count="Revision", event_retention_ms="Nat", receipt_retention_ms="Revision",
                  result_retention_ms="Nat", lease_period_ms="Revision", resume_window_ms="Nat"),
    "PrivacyModel": obj(visible_to=array("Principal", 1, 256, True),
                        relay_plaintext="Bool", retention_notice="Text"),
    "Policy": obj(**{"spoilers?": enum("avoid_unknown", "allow"),
                     "proactive_chat?": "Bool", "extensions": "Extensions"}),
    "PresentationTerms": obj(mode=enum("hide_desktop", "coexist"), device_id="Id"),
    "ResourcePolicy": obj(approved_origins=array("Name", 1, 64, True), max_total_bytes="Revision",
                          max_unpacked_bytes="Revision", max_dependencies="Nat", max_depth="Revision",
                          accepted_media_types=array("Name", 1, 64, True), allow_private_network="Bool"),
    "Compatibility": obj(profile="Name", revision="Version", properties="JsonObject"),
    "Manifest": obj(asset_id="Id", content_digest="Digest", byte_size="Nat", media_type="Name",
                    format_version="Version", compatibility="Compatibility",
                    dependency_manifests=array("Manifest", 0, 128),
                    approved_origins=array("Name", 1, 64, True), license_claim="Text", issuer="Principal",
                    sandbox_requirements=array("Name", 0, 64, True), **{"locator?": "Name"}),
    "Avatar": choice(obj(kind=enum("preinstalled"), asset_id="Id", revision="Revision", format="Name"),
                     obj(kind=enum("manifest"), manifest="Manifest")),
    "ActionDefinition": obj(id="Id", revision="Revision", schema_profile={"const": "g2a-value-schema-1"}, parameters="ValueSchema", result_schema="ValueSchema",
                            allowed_actors="Principals", requires_per_action_consent="Bool",
                            maximum_duration_ms="Revision", cancellation=enum("before_claim", "between_steps"),
                            effect_class=enum("read_only", "compensatable", "irreversible")),
    "ActionDigests": {"type": "object", "maxProperties": 256, "propertyNames": ref("Id"),
                      "additionalProperties": ref("Digest")},
    "Descriptor": obj(descriptor_id="Id", revision="Revision", instance="Instance",
                      supported_versions=array("Version", 1, 32, True), bindings=array("Binding", 1, 16),
                      ledger_durabilities=array(enum("volatile", "durable"), 1, 2, True),
                      trust_profiles=array("TrustProfile", 1, 3, True), supported_features="Features",
                      required_features=array("Feature", 2, 11, True), privacy_model="PrivacyModel",
                      policy_defaults="Policy",
                      context_categories=array("Name", 0, 256, True), actions=array("ActionDefinition", 0, 256),
                      limits="Limits", extensions="Extensions", **{"avatar_requirements?": "AvatarRequirements",
                      "presentation_requirements?": "PresentationTerms"}),
    "Scope": obj(player="Principal", agent="Principal", instance="Instance", version="Version",
                 binding="Binding", trust_profile="TrustProfile", features="Features",
                 descriptor_revision="Revision", action_ids=array("Id", 0, 256, True), approved_action_digests="ActionDigests",
                 context_categories=array("Name", 0, 256, True), audiences="Principals", effective_policy="Policy",
                 privacy_model="PrivacyModel", result_retention_ms="Nat", ledger_durability=enum("volatile", "durable"),
                 limits="Limits", created_at="Nat", expires_at="Nat", extensions="Extensions", **{"avatar_selection?": "Avatar",
                 "resource_policy?": "ResourcePolicy", "presentation_terms?": "PresentationTerms"}),
    "Requested": obj(player="Principal", agent="Principal", supported_versions=array("Version", 1, 32, True),
                     bindings=array("Binding", 1, 16), trust_profiles=array("TrustProfile", 1, 3, True), privacy_model="PrivacyModel",
                     supported_features="Features", required_features=array("Feature", 0, 11, True),
                     action_ids=array("Id", 0, 256, True), context_categories=array("Name", 0, 256, True),
                     audiences="Principals", policy="Policy", companion_defaults="Policy", limits="Limits", maximum_grant_duration_ms="Revision",
                     ledger_durability=enum("volatile", "durable"), extensions="Extensions", **{"forced_avatar?": "Avatar",
                     "default_avatar?": "Avatar", "presentation_terms?": "PresentationTerms"}),
    "GrantRecord": obj(grant_id="Id", scope="Scope", scope_digest="Digest", approver="Principal", consent_evidence_ref="Id",
                       revision="Revision", state=enum("active", "revoked", "expired"), expires_at="Nat"),
    "OfferView": obj(offer_id="Id", applicant="Principal", immutable_scope="Scope", scope_digest="Digest",
                     decision_deadline="Nat", launch_required="Bool",
                     state=enum("pending", "approved", "denied", "expired", "stale"), **{"grant_id?": "Id"}),
    "JoinIntent": obj(scope_digest="Digest", **{"selected_device?": "Id", "presentation_observation?": "DeviceObservation"}),
    "DeviceObservation": obj(device_id="Id", device_epoch="Revision", baseline_visible="Bool", manual_revision="Revision", proof_ref="Id"),
    "Cursor": obj(session_id="Id", instance_epoch="Id", sequence="Nat"),
    "Source": obj(source_kind=enum("shared_experience", "player_report", "external_reference"),
                  source_id="Id", source_principals="Principals", original_disclosure_scope="Principals"),
    # 权威端内部记录，不是客户端可自行提交的授权或新增 wire 操作。
    "SourceAuthorization": obj(instance="Instance", session_id="Id", source="Source", controller="Principal",
                               evidence_ref="Id", revision="Revision", state=enum("active", "revoked"),
                               publishers="Principals", allowed_readers="Principals", expires_at="Nat"),
    # 受信游戏输入端口的内部席位登记；wire 仅携带引用，不接受调用者自报该证明。
    "PlayerSeatAuthorization": obj(proof_ref="Id", instance="Instance", session_id="Id", scope_digest="Digest",
                                    game="Principal", player="Principal", membership_revision="Revision",
                                    membership_generation="Revision", issued_at="Nat", expires_at="Nat",
                                    state=enum("active", "revoked")),
    "Envelope": obj(version="Version", session_id="Id", id="Id", type="Name", sender="Principal",
                    audience="Principals", payload="JsonObject", extensions="Extensions",
                    **{"correlation_id?": "Id", "expected_capabilities_revision?": "Revision",
                       "expected_membership_revision?": "Revision"}),
    "Receipt": obj(id="Id", accepted_at="Nat", record_digest="Digest", duplicate="Bool", **{"outcome_ref?": "Id"}),
    "SessionView": obj(session_id="Id", scope="Scope", grant_id="Id", state=enum("active", "closed"),
                       instance_epoch="Id", transport_epoch="Id", control_generation="Revision",
                       lease_deadline="Nat", capabilities_revision="Revision", membership_revision="Revision",
                       sequence="Nat", ready="Bool", **{"close_reason?": "Name", "controller_device?": "Id",
                       "result_read_until?": "Nat", "resume_until?": "Nat"}),
    "ControlDelivery": obj(status=enum("ready"), session="SessionView", control_credential="Secret",
                           result_read_handle="Secret", event_high_watermark="Cursor", unresolved_actions=array("Id")),
    "SecretStatus": obj(status=enum("pending", "completed_without_secret"), outcome_ref="Id", reauth_required="Bool"),
    "JoinResponse": choice("ControlDelivery", "SecretStatus",
                           obj(status=enum("join_pending", "already_joined"), session_id="Id")),
    "ActionState": enum("pending", "executing", "succeeded", "failed", "cancelled", "unknown"),
    "Effect": enum("none", "partial", "committed", "undetermined"),
    "ActionResult": obj(request_id="Id", session_id="Id", state="ActionState", effect="Effect",
                        result_revision="Nat", query_until="Nat", **{"known_result?": "Json"}),
    "Event": obj(sequence="Revision", envelope="Envelope", created_at="Nat"),
    "EventPage": obj(events=array("Event"), next_cursor="Cursor", high_watermark="Cursor", lease_deadline="Nat"),
    "TransferView": obj(transfer_id="Id", session_id="Id", old_generation="Revision", new_generation="Revision",
                        target_device="Id", status=enum("releasing", "acquiring", "ready", "failed"),
                        deadline="Nat", **{"failure_reason?": "Name"}),
    "OperationView": obj(operation="Name", request_id="Id", state=enum("pending", "done", "failed"),
                         outcome_ref="Id", **{"session?": "SessionView", "transfer?": "TransferView",
                         "offer?": "OfferView", "error?": "Error", "receipt?": "Receipt",
                         "action?": "ActionResult", "revocation?": "RevocationResult"}),
    "ReadGrant": obj(session_id="Id", action_ids=array("Id"), access_revision="Revision", read_until="Nat"),
    "Revocation": obj(object_type=enum("auto_rule", "grant", "invitation", "session", "capability", "relay", "result_read"),
                      object_id="Id", expected_revision="Revision"),
    "RevocationResult": obj(object_type="Name", object_id="Id", revision="Revision", state=enum("revoked", "consumed", "closed")),
    "PrivacyCompleted": obj(privacy_request_id="Id", status=enum("done", "partial", "denied"),
                            controlled_scope=array("Id"), exceptions=array("RetentionException")),
    "PrivacyReceipt": choice("PrivacyCompleted", obj(privacy_request_id="Id", status=enum("pending"),
                                                     controlled_scope=array("Id"), poll_after_ms="Nat")),
    "RetentionException": obj(source_id="Id", reason="Text", **{"retain_until?": "Nat"}),
    "ExecutionTicket": obj(ticket_id="Id", session_id="Id", request_id="Id", worker="Principal",
                           generation="Revision", fence="Revision", deadline="Nat", proof_ref="Id"),
    "ExecutionFact": obj(state=enum("succeeded", "failed", "cancelled", "unknown"), effect="Effect",
                         steps=array("StepFact"), **{"result?": "Json"}),
    "StepFact": obj(step="Nat", effect="Effect", evidence_ref="Id"),
    "PresentationLease": obj(session_id="Id", generation="Revision", device_id="Id", device_epoch="Revision",
                              lease_revision="Revision", terms="PresentationTerms", deadline="Nat",
                              scope_digest="Digest", authority_proof_ref="Id"),
    "PresentationReceipt": obj(session_id="Id", generation="Revision", operation_id="Id", device_id="Id",
                               device_epoch="Revision", lease_revision="Nat", lease_deadline="Nat",
                               manual_revision="Revision", actual_visible="Bool", applied="Bool"),
    "AssetReceipt": obj(asset_id="Id", content_digest="Digest", validation_receipt="Id", parser_revision="Name", policy_revision="Name"),
}
TYPES["AvatarRequirements"] = obj(accepted_formats=array("Name", 1, 64, True), **{"game_avatar?": "Avatar"})


def message(kind, payload, revisions=()):
    result = obj(**{**{key: value for key, value in TYPES["Envelope"]["properties"].items()
                       if key in TYPES["Envelope"]["required"]},
                    "correlation_id?": "Id", "expected_capabilities_revision?": "Revision",
                    "expected_membership_revision?": "Revision"})
    result["properties"]["type"] = {"const": kind}
    result["properties"]["payload"] = payload
    result["required"] += list(revisions)
    return result


TYPES.update({
    "Chat": message("chat.message", obj(channel=enum("private", "team"), text="Text",
                                        provenance=array("Source"), source_refs=array("Id"))),
    "Context": message("game.context", obj(category="Name", content="Json", provenance=array("Source"))),
    "ActionRequest": message("action.request", obj(action="Id", arguments="JsonObject", deadline="Nat",
                                                    **{"confirmation?": "Id"}), ("expected_capabilities_revision",)),
    "ActionCancel": message("action.cancel", obj(request_id="Id")),
    "ActionStateEvent": message("action.state", obj(reason=enum("accepted", "claimed", "cancel_requested", "result"), action="ActionResult")),
    "CapabilityEvent": message("capability.update", obj(revision="Revision", definitions=array("ActionDefinition", 0, 256))),
    "MembershipEvent": message("membership.update", obj(revision="Revision", members=array("Principal", 0, 256, True))),
    "SessionReadyEvent": message("session.ready", obj(session="SessionView")),
    "SessionClosedEvent": message("session.closed", obj(session="SessionView")),
    "ControlChangedEvent": message("session.control_changed", obj(session="SessionView")),
})

EVENT_TYPES = {"chat.message": "Chat", "game.context": "Context", "action.state": "ActionStateEvent",
               "capability.update": "CapabilityEvent", "membership.update": "MembershipEvent",
               "session.ready": "SessionReadyEvent", "session.closed": "SessionClosedEvent",
               "session.control_changed": "ControlChangedEvent"}
TYPES["CoreEventEnvelope"] = choice(*EVENT_TYPES.values())
TYPES["Event"]["properties"]["envelope"] = ref("CoreEventEnvelope")
TYPES["RecoverySnapshot"] = obj(snapshot_version={"const": "g2a-recovery-1"}, session="SessionView", cursor="Cursor",
                                actions=array("ActionResult", 0, 256), contexts=array("Context", 0, 256),
                                definitions=array("ActionDefinition", 0, 256), members=array("Principal", 0, 256, True))

# 这些字段关系可以机器判定；跨对象身份、有效期和权限交集仍属语义检查。
TYPES["ActionResult"]["allOf"] = [
    {"if": {"properties": {"state": {"const": state}}},
     "then": {"properties": {"effect": enum(*effects)}}}
    for state, effects in {"pending": ["none"], "executing": ["none", "partial", "committed", "undetermined"],
                           "succeeded": ["committed"], "failed": ["none", "partial"],
                           "cancelled": ["none", "partial"], "unknown": ["undetermined"]}.items()
]
TYPES["SessionView"]["allOf"] = [
    {"if": {"properties": {"state": {"const": "closed"}}},
     "then": {"required": ["close_reason"], "properties": {"ready": {"const": False}}},
     "else": {"not": {"required": ["close_reason"]}}}
]
TYPES["ControlDelivery"]["properties"]["session"] = {
    "allOf": [ref("SessionView"), {"properties": {"state": {"const": "active"}, "ready": {"const": True}}}]
}
TYPES["SecretStatus"]["allOf"] = [{
    "if": {"properties": {"status": {"const": "pending"}}},
    "then": {"properties": {"reauth_required": {"const": False}}},
    "else": {"properties": {"reauth_required": {"const": True}}},
}]

# 角色是认证适配器输出的 route role，不是客户端自报 Principal.kind。
# mode 决定重试/去重族；输入/成功输出为精确 schema，关系检查另外声明。
OPERATIONS = {}


def operation(name, roles, lane, feature, mode, request, response, guard):
    key = name.replace(".", "_")
    TYPES[key + "_input"] = request
    TYPES[key + "_output"] = response
    OPERATIONS[name] = {"roles": roles.split(), "lane": lane, "feature": feature,
                        "mode": mode, "input": key + "_input", "output": key + "_output",
                        "semantic_guard": guard}


operation("describe", "agent player", "control", "core.session", "read", obj(instance="Instance"), ref("Descriptor"),
          "验证 endpoint 身份并按主体过滤；公开发现只返回 PublicDescriptor，不调用此完整描述接口。")
operation("offer.create", "agent player", "control", "core.session", "control", obj(entry=enum("game", "companion"),
          descriptor_id="Id", expected_descriptor_revision="Revision", requested="Requested"), ref("OfferView"),
          "companion 入口 actor=agent；game 入口为玩家或经验证委托；固定 Scope 后不能替换身份。")
operation("offer.get", "agent player", "control", "core.session", "read", obj(offer_id="Id"), ref("OfferView"), "仅绑定主体可读。")
operation("offer.decide", "player", "control", "core.session", "control", obj(offer_id="Id", scope_digest="Digest",
          allow="Bool", remember="Bool", launch_permission="Bool", decision_ref="Id",
          **{"rule_expires_at?": "Nat", "maximum_grant_duration_ms?": "Revision"}), ref("OfferView"),
          "decision_ref 验证真实玩家交互；remember=true 必须同时提供规则期限与授权时长，false 禁止两字段；拒绝时两许可均为 false。")
operation("invitation.redeem", "agent", "control", "core.session", "control", obj(offer_id="Id", join_intent="JoinIntent"),
          choice(obj(invitation_id="Id", invitation_credential="Secret", expires_at="Nat", join_intent="JoinIntent"), "SecretStatus"),
          "仅 scope.agent；同 intent 重试；邀请秘密只交本人，绑定 Scope、玩家、实例及设备。")
operation("session.join", "agent", "control", "core.session", "control", obj(invitation_id="Id", join_intent="JoinIntent"),
          ref("JoinResponse"), "邀请 proof 由认证适配器验证，不只凭 invitation_id；准备成功前不返回 control secret。")
operation("session.heartbeat", "companion_control", "data", "core.session", "lease", obj(session_id="Id"),
          ref("SessionView"), "request_id 为 fresh_nonce；相同 ID 不续租；当前 transport_epoch/generation/ready。")
operation("session.snapshot", "companion_control", "data", "core.session", "read", obj(session_id="Id"),
          ref("RecoverySnapshot"), "同一快照切点返回会话、cursor、可见动作/情境/定义/成员；按当前读权过滤，不返回写凭据，不续租。")
operation("session.events", "companion_control", "data", "core.events", "lease", obj(session_id="Id", cursor="Cursor", page_size="Revision"),
          ref("EventPage"), "request_id 为 poll_nonce；cursor 绑定 session/epoch；冻结及当前受众双检查，重复不续租。")
operation("session.close", "companion_control player game", "control", "core.session", "control", obj(session_id="Id", reason=enum("left", "revoked", "host_shutdown")),
          ref("SessionView"), "按主体关闭权验证；game 仅走管理入口；closed 不复活，保留已授权结果。")
operation("session.resume", "agent", "control", "resume", "control", obj(session_id="Id", expected_generation="Revision", **{"device_id?": "Id"}),
          ref("JoinResponse"), "fresh 原主体、持久账本和未过期租约；同设备，控制回执先于 expected_generation 重试检查。")
operation("session.handoff", "player", "control", "handoff", "control", obj(session_id="Id", expected_generation="Revision", target_device="Id", decision_ref="Id", target_proof_ref="Id"),
          ref("TransferView"), "玩家决定绑定目标；先撤旧代写权；玩家只取 transfer 状态，不能取得 agent secret。")
operation("session.claim_control", "agent", "control", "handoff", "control", obj(session_id="Id", transfer_id="Id", target_device="Id"),
          choice("ControlDelivery", "SecretStatus"), "仅 transfer 中原 agent+已验证目标设备，ready/当前代次/未撤销；未 ready 返回 pending；闭会或后续升代不回放旧 secret。")
operation("operation.get", "agent player", "control", "core.session", "read", obj(operation="Name", original_request_id="Id"),
          ref("OperationView"), "同主体/受众查询；control/lease 用原 request_id，action.request/cancel 用 Envelope.id。done 是原请求完成，不等于当前仍可写或动作成功；动作视图重验结果读权；无秘密、不执行或赎领。")
operation("chat.send", "companion_control", "data", "core.events", "message", ref("Chat"), ref("Receipt"),
          "sender 由凭据验证；team 需能力和 expected_membership_revision，受众冻结成员代次。")
operation("action.request", "companion_control", "data", "actions", "message", ref("ActionRequest"), ref("Receipt"),
          "Envelope.id 是 action ID；校验能力 revision/参数/一次确认，在效果临界区再次核权。")
operation("action.cancel", "companion_control", "data", "actions", "message", ref("ActionCancel"), ref("Receipt"),
          "仅原 actor；取消收据不证明未发生效果；目标 payload.request_id 不等于取消消息 ID。")
operation("action.query", "results_reader agent player companion_control", "results", "actions", "read", obj(session_id="Id", action_id="Id"),
          ref("ActionResult"), "原只读授权/期限/撤销/可见动作；不要求会话写权有效；重新认证原主体不扩大读权。")
operation("action.confirm", "player", "control", "actions", "control", obj(session_id="Id", action_request_id="Id", action="Id",
          arguments_digest="Digest", definition_digest="Digest", expires_at="Nat", decision_ref="Id"),
          obj(confirmation_id="Id", expires_at="Nat"), "一次玩家确认绑定 session、action、原请求 ID、参数与定义摘要；不能由 agent 代签。")
operation("context.publish", "game", "management", "core.events", "message", ref("Context"), ref("Receipt"),
          "只写批准开放类别；game 不续伙伴租约；来源绑定当前共享经历。")
operation("player_chat.forward", "game", "management", "core.events", "message", obj(seat_proof_ref="Id", envelope="Chat"),
          ref("Receipt"), "当前 GameAuthority/Scope/成员代次席位证明绑定玩家 sender；按玩家/Envelope.id 去重，不续伙伴租约。")
operation("capability.replace", "game", "management", "actions", "control", obj(instance="Instance", expected_revision="Revision", definitions=array("ActionDefinition", 0, 256)),
          obj(revision="Revision"), "CAS；定义 ID 唯一；新增/改义不扩旧 Grant，执行中旧 fence 失效。")
operation("membership.replace", "game", "management", "core.events", "control", obj(instance="Instance", expected_revision="Revision", verified_members="Principals", membership_proof_ref="Id"),
          obj(revision="Revision"), "基础席位也有成员代次；新增队伍席位需 team；重加入增加代次且不扩旧 Scope。")
operation("permission.revoke", "player game", "control", "core.session", "control", ref("Revocation"), ref("RevocationResult"),
          "按对象验证撤销权；game 只走管理入口；result_read 单独撤销不伪造不存在。")
operation("action.claim", "executor", "management", "actions", "control", obj(session_id="Id", action_id="Id", worker="Principal"),
          choice(obj(status=enum("claimed"), ticket="ExecutionTicket", arguments="JsonObject"), obj(status=enum("not_executable"), action="ActionResult")),
          "worker 必须登记；同控制请求可读原 ticket，ticket/step 仍唯一；新请求不领取已 executing 动作。")
operation("action.commit_result", "executor", "management", "actions", "control", obj(ticket="ExecutionTicket", fact="ExecutionFact"),
          ref("ActionResult"), "原可信 ticket 只报告事实；terminal 同摘要幂等，冲突拒绝；旧代不能执行新效果。")
operation("launch.request", "player", "local", "core.session", "control", obj(offer_id="Id", application_registration="Id", launch_permission_ref="Id"),
          obj(status=enum("started", "already_running")), "固定注册应用，禁止任意命令/路径；单次启动许可与接入批准分开。")
operation("asset.resolve", "resource_owner", "local", "assets", "control", obj(session_id="Id", manifest="Manifest", scope_digest="Digest"),
          ref("AssetReceipt"), "批准来源/依赖闭包/大小/摘要/解析沙箱；不携带会话 secret 下载。")
operation("presentation.acquire", "presentation_authority", "local", "presentation", "control", ref("PresentationLease"),
          ref("PresentationReceipt"), "request_id 是 operation_id；绑定当前设备 epoch，初始 lease_revision=1；设备身份/条款/期限/tombstone 校验；重试不延长占用。")
operation("presentation.renew", "presentation_authority", "local", "presentation", "control", ref("PresentationLease"),
          ref("PresentationReceipt"), "仅当前游戏存活租约产生更高 revision；绑定设备 epoch/原条款，不续游戏租约；旧 revision/重试不延长占用，tombstone 不可复活。")
operation("presentation.release", "presentation_authority", "local", "presentation", "control", obj(session_id="Id", generation="Revision", device_id="Id"),
          ref("PresentationReceipt"), "仅清理自己的 generation；先写 tombstone，再按最新 baseline 重算，失败报告实际状态。")
operation("privacy.request", "data_subject", "privacy", "privacy-request", "control", obj(source_refs=array("Id", 1, 4096, True), desired_action=enum("stop_disclosure", "delete_owned_copies")),
          ref("PrivacyReceipt"), "发送实际数据控制者；验证每条来源主体权；仅对可控副本承诺。")
operation("privacy.receipt", "data_subject", "privacy", "privacy-request", "read", obj(privacy_request_id="Id"),
          ref("PrivacyReceipt"), "读取本人已提交请求的当前处理状态；不能由数据主体伪造存储方回执。")

TYPES.update({
    "PublicDescriptor": obj(instance="Instance", supported_versions=array("Version", 1, 32, True),
                            discovery_endpoint="Name"),
    # 下面三种是可信夹具端口的内部证明，不是新的公开操作或调用方可自报的身份。
    "RelayPairingAuthorization": obj(proof_ref="Id", instance="Instance", relay_identity="Principal", relay_origin="Name",
        controller="Principal", agent_principals="Principals", control_principals="Principals", limits="Limits",
        game_authority_ref="Id", consent_evidence_ref="Id", issued_at="Nat", expires_at="Nat", state=enum("active", "revoked")),
    "RelayCredential": obj(role=enum("relay_controller", "relay_agent", "relay_game"), principal="Principal",
        instance="Instance", relay_identity="Principal", relay_origin="Name", issued_at="Nat", expires_at="Nat",
        state=enum("active", "revoked"), **{"mailbox_id?": "Id", "route_revision?": "Revision"}),
    "RelayInnerAuthorization": obj(proof_ref="Secret", credential="Secret", principal="Principal", role="Name",
        instance="Instance", audience="Name", issued_at="Nat", expires_at="Nat", state=enum("active", "revoked")),
    "RelayCall": obj(relay_request_id="Id", operation_request="RelayInnerRequest", inner_auth_proof="Secret",
                     deadline="Nat", route_revision="Revision"),
    "RelayClaim": obj(claim_id="Id", mailbox_id="Id", game_identity="Principal", call="RelayCall"),
    "RelayOutcome": choice(obj(state=enum("queued", "claimed"), relay_request_id="Id"),
                           obj(state=enum("replied"), relay_request_id="Id", reply="JsonObject")),
})
operation("relay.register", "relay_controller", "relay", "core.session", "control", obj(instance="Instance",
          relay_identity="Principal", relay_origin="Name", agent_principals="Principals", control_principals="Principals",
          registration_expiry="Nat", pairing_proof_ref="Id", limits="Limits"),
          obj(mailbox_id="Id", route_revision="Revision", registration_expiry="Nat"),
          "角色凭据由验证过的配对渠道分别交付，不把 game/agent/controller 三种 secret 同时交给注册者。")
operation("relay.call", "relay_agent relay_controller", "relay", "core.session", "relay", obj(mailbox_id="Id", call="RelayCall"),
          ref("RelayOutcome"), "外层 lane 与内层主体都校验；固定 instance，无任意 URL；重复 call 不延长 deadline；inner reply 按原操作 schema 校验。")
operation("relay.pull", "relay_game", "relay", "core.session", "control", obj(mailbox_id="Id", pull_nonce="Id", maximum_items="Revision"),
          obj(claims=array("RelayClaim")), "同 pull_nonce 返回原 claim；claimed 不重入队；凭据仅有领取/回复权限。")
operation("relay.reply", "relay_game", "relay", "core.session", "control", obj(mailbox_id="Id", claim_id="Id", reply="JsonObject"),
          obj(status=enum("accepted")), "精确 claim owner；reply 必须通过原 operation 的输出 schema 和 request_id 校验；重复相同结果幂等。")
operation("relay.revoke", "relay_controller", "relay", "core.session", "control", obj(mailbox_id="Id", expected_route_revision="Revision"),
          obj(mailbox_id="Id", route_revision="Revision", state=enum("closed")),
          "queued 原子关闭可证明本路径未投递；claimed 只能 unknown；作废全部外层凭据但不伪造世界回滚。")

FEATURE_DEPENDENCIES = {
    "core.session": [], "core.events": ["core.session"],
    "actions": ["core.session", "core.events"], "team": ["core.session", "core.events"],
    "avatar": ["core.session", "core.events"], "assets": ["avatar"],
    "presentation": ["core.session", "core.events"], "resume": ["core.session", "core.events"],
    "multi-session": ["core.session", "core.events"], "handoff": ["resume"],
    "privacy-request": ["core.session", "core.events"],
}

# 此目录列出边界错误，内部异常必须映射后再公开，不把异常文本当协议错误码。
ERRORS = {}


def errors(codes, category, retry, status, outcome="not_accepted"):
    for code in codes.split():
        ERRORS[code] = {"category": category, "retry": retry, "http_status": status, "outcome": outcome}


errors("unauthenticated", "authentication", "after_reauth", 401)
errors("permission_denied", "authorization", "never", 403)
errors("invalid_message invalid_arguments invalid_cursor", "validation", "never", 400)
errors("unsupported_media_type", "validation", "never", 415)
errors("message_too_large", "limit", "never", 413)
errors("unsupported_operation unsupported_version feature_unsupported trust_profile_unsupported negotiation_failed", "negotiation", "after_renegotiate", 409)
errors("id_conflict redemption_conflict invitation_used generation_conflict stale_capabilities membership_conflict execution_conflict reply_conflict", "conflict", "never", 409)
errors("approval_stale offer_expired grant_revoked invitation_expired consent_required action_consent_required handoff_required", "authorization", "after_renegotiate", 409)
errors("session_closed session_conflict session_not_writable transfer_in_progress resume_denied request_expired occupation_released", "state", "never", 409)
errors("stale_controller stale_transport", "authentication", "after_reauth", 401)
errors("avatar_required avatar_incompatible resource_policy_denied resource_integrity_error", "resource", "after_renegotiate", 409)
errors("resource_limit rate_limited", "limit", "same_request", 429)
errors("result_expired result_unavailable", "retention", "never", 409)
errors("history_gap", "history", "never", 409)
errors("launch_failed presentation_unavailable admission_failed transfer_failed", "lifecycle", "never", 409, "accepted")
errors("temporarily_unavailable", "availability", "same_request", 503)
errors("transport_timeout", "uncertain", "same_request", 504, "unknown")
errors("internal_failure", "uncertain", "same_request", 503, "unknown")
errors("request_gone", "state", "never", 409, "unknown")
errors("relay_not_dispatched", "transport", "same_request", 503)
errors("action_not_executable operation_rejected", "state", "never", 409)
errors("operation_failed", "lifecycle", "never", 409, "accepted")
errors("outcome_unknown", "uncertain", "same_request", 409, "unknown")
TYPES["ErrorDetails"] = obj(**{"field?": "Name", "resource?": "Name", "snapshot?": "RecoverySnapshot",
                              "next_cursor?": "Cursor", "unresolved_actions?": array("Id"), "operation_ref?": "Id"})
TYPES["Error"] = obj(code=enum(*ERRORS), category=enum(*sorted({e["category"] for e in ERRORS.values()})),
                     retry=enum("never", "same_request", "after_reauth", "after_renegotiate"),
                     outcome=enum("not_accepted", "accepted", "unknown"), details="ErrorDetails",
                     **{"request_id?": "Id", "retry_after_ms?": "Nat"})

TYPES["ConformanceStatement"] = obj(
    statement_version={"const": "g2a-conformance-statement-1"},
    subject=obj(name="Name", revision="Name", artifact_kind=enum("design", "mock", "implementation")),
    status=enum("not_evaluated", "partial", "passed", "failed"),
    assurance=enum("design", "mock", "adapter", "deployment"),
    design_revision={"const": "g2a-design-1"}, wire_versions=array("Version", 0, 32, True),
    roles=array(enum(*sorted({r for op in OPERATIONS.values() for r in op["roles"]})), 0, 32, True),
    features="Features", trust_profiles=array("TrustProfile", 0, 3, True),
    bindings=array(enum("direct-http", "outbound-relay", "local-ipc"), 0, 3, True),
    ledger_durability=enum("volatile", "durable"),
    evidence=array(obj(id="Id", kind=enum("schema", "unit", "model", "symbolic", "adapter", "deployment"),
                       artifact="Name", case_refs=array("Name"), **{"sha256?": "Digest"})),
    coverage=array(obj(operation=enum(*OPERATIONS), verdict=enum("not_evaluated", "partial", "passed", "failed"),
                       evidence_ids=array("Id", 0, 64, True), limitations=array("Text"))),
    exclusions=array("Text"), reviewed_by="Name")


def statement_template():
    return {"statement_version": "g2a-conformance-statement-1",
            "subject": {"name": "replace-with-subject", "revision": "replace-with-exact-revision", "artifact_kind": "design"},
            "status": "not_evaluated", "assurance": "design", "design_revision": "g2a-design-1", "wire_versions": [],
            "roles": [], "features": ["core.session", "core.events"], "trust_profiles": [], "bindings": [],
            "ledger_durability": "volatile", "evidence": [],
            "coverage": [{"operation": name, "verdict": "not_evaluated", "evidence_ids": [], "limitations": []}
                         for name in OPERATIONS],
            "exclusions": ["Not a certification; replace placeholders and independently review evidence."],
            "reviewed_by": "not-reviewed"}


MESSAGE_OPERATIONS = frozenset({"chat.send", "action.request", "action.cancel", "context.publish", "player_chat.forward"})


def schema():
    """本地引用的 JSON Schema 2020-12；根为 OperationRequest。"""
    definitions = dict(TYPES)
    request_variants, reply_variants = [], []
    for name, metadata in OPERATIONS.items():
        request_variants.append(obj(version="Version", operation={"const": name}, request_id="Id",
                                    payload=ref(metadata["input"]),
                                    extensions={"const": {}} if name in MESSAGE_OPERATIONS else "Extensions"))
        reply_variants.append(obj(operation={"const": name}, request_id="Id", result=ref(metadata["output"])))
    definitions["OperationRequest"] = {"oneOf": request_variants}
    definitions["RelayInnerRequest"] = {"oneOf": [request for request, metadata in zip(request_variants, OPERATIONS.values())
                                                   if metadata["lane"] in ("control", "data", "results")]}
    # ReplyEnvelope 是按已知 operation 校验的本地测试封装；operation 不添加到线上响应。
    definitions["ReplyEnvelope"] = {"oneOf": reply_variants + [obj(operation=enum(*OPERATIONS), request_id="Id", error="Error")]}
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "urn:g2a:design:contracts:1", "$comment": "工作草案的本地结构契约，不是已部署 wire 版本；先严格 codec，再 schema，再语义授权。",
            "$defs": definitions, "$ref": "#/$defs/OperationRequest"}


if __name__ == "__main__":
    print(json.dumps(schema(), ensure_ascii=False, indent=2))
