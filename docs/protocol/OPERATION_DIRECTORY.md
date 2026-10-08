# 操作与错误目录（生成文件）

由 contracts.py 生成；使用规则和语义边界见 [契约使用说明](OPERATION_CONTRACT.md)。
字段精确定义见 [本地 schema](contracts.schema.json) 的 `$defs`；本文不代替授权检查。

## describe

- 角色：`agent / player`；入口：`control`；能力：`core.session`；重试族：`read`。
- 输入：`describe_input`；必需字段：`instance`；可选字段：`无`。
- 成功输出：`describe_output`。
- 语义条件：验证 endpoint 身份并按主体过滤；公开发现只返回 PublicDescriptor，不调用此完整描述接口。

## offer.create

- 角色：`agent / player`；入口：`control`；能力：`core.session`；重试族：`control`。
- 输入：`offer_create_input`；必需字段：`entry / descriptor_id / expected_descriptor_revision / requested`；可选字段：`无`。
- 成功输出：`offer_create_output`。
- 语义条件：companion 入口 actor=agent；game 入口为玩家或经验证委托；固定 Scope 后不能替换身份。

## offer.get

- 角色：`agent / player`；入口：`control`；能力：`core.session`；重试族：`read`。
- 输入：`offer_get_input`；必需字段：`offer_id`；可选字段：`无`。
- 成功输出：`offer_get_output`。
- 语义条件：仅绑定主体可读。

## offer.decide

- 角色：`player`；入口：`control`；能力：`core.session`；重试族：`control`。
- 输入：`offer_decide_input`；必需字段：`offer_id / scope_digest / allow / remember / launch_permission / decision_ref`；可选字段：`rule_expires_at / maximum_grant_duration_ms`。
- 成功输出：`offer_decide_output`。
- 语义条件：decision_ref 验证真实玩家交互；remember=true 必须同时提供规则期限与授权时长，false 禁止两字段；拒绝时两许可均为 false。

## invitation.redeem

- 角色：`agent`；入口：`control`；能力：`core.session`；重试族：`control`。
- 输入：`invitation_redeem_input`；必需字段：`offer_id / join_intent`；可选字段：`无`。
- 成功输出：`invitation_redeem_output`。
- 语义条件：仅 scope.agent；同 intent 重试；邀请秘密只交本人，绑定 Scope、玩家、实例及设备。

## session.join

- 角色：`agent`；入口：`control`；能力：`core.session`；重试族：`control`。
- 输入：`session_join_input`；必需字段：`invitation_id / join_intent`；可选字段：`无`。
- 成功输出：`session_join_output`。
- 语义条件：邀请 proof 由认证适配器验证，不只凭 invitation_id；准备成功前不返回 control secret。

## session.heartbeat

- 角色：`companion_control`；入口：`data`；能力：`core.session`；重试族：`lease`。
- 输入：`session_heartbeat_input`；必需字段：`session_id`；可选字段：`无`。
- 成功输出：`session_heartbeat_output`。
- 语义条件：request_id 为 fresh_nonce；相同 ID 不续租；当前 transport_epoch/generation/ready。

## session.snapshot

- 角色：`companion_control`；入口：`data`；能力：`core.session`；重试族：`read`。
- 输入：`session_snapshot_input`；必需字段：`session_id`；可选字段：`无`。
- 成功输出：`session_snapshot_output`。
- 语义条件：同一快照切点返回会话、cursor、可见动作/情境/定义/成员；按当前读权过滤，不返回写凭据，不续租。

## session.events

- 角色：`companion_control`；入口：`data`；能力：`core.events`；重试族：`lease`。
- 输入：`session_events_input`；必需字段：`session_id / cursor / page_size`；可选字段：`无`。
- 成功输出：`session_events_output`。
- 语义条件：request_id 为 poll_nonce；cursor 绑定 session/epoch；冻结及当前受众双检查，重复不续租。

## session.close

- 角色：`companion_control / player / game`；入口：`control`；能力：`core.session`；重试族：`control`。
- 输入：`session_close_input`；必需字段：`session_id / reason`；可选字段：`无`。
- 成功输出：`session_close_output`。
- 语义条件：按主体关闭权验证；game 仅走管理入口；closed 不复活，保留已授权结果。

## session.resume

- 角色：`agent`；入口：`control`；能力：`resume`；重试族：`control`。
- 输入：`session_resume_input`；必需字段：`session_id / expected_generation`；可选字段：`device_id`。
- 成功输出：`session_resume_output`。
- 语义条件：fresh 原主体、持久账本和未过期租约；同设备，控制回执先于 expected_generation 重试检查。

## session.handoff

- 角色：`player`；入口：`control`；能力：`handoff`；重试族：`control`。
- 输入：`session_handoff_input`；必需字段：`session_id / expected_generation / target_device / decision_ref / target_proof_ref`；可选字段：`无`。
- 成功输出：`session_handoff_output`。
- 语义条件：玩家决定绑定目标；先撤旧代写权；玩家只取 transfer 状态，不能取得 agent secret。

## session.claim_control

- 角色：`agent`；入口：`control`；能力：`handoff`；重试族：`control`。
- 输入：`session_claim_control_input`；必需字段：`session_id / transfer_id / target_device`；可选字段：`无`。
- 成功输出：`session_claim_control_output`。
- 语义条件：仅 transfer 中原 agent+已验证目标设备，ready/当前代次/未撤销；未 ready 返回 pending；闭会或后续升代不回放旧 secret。

## operation.get

- 角色：`agent / player`；入口：`control`；能力：`core.session`；重试族：`read`。
- 输入：`operation_get_input`；必需字段：`operation / original_request_id`；可选字段：`无`。
- 成功输出：`operation_get_output`。
- 语义条件：同主体/受众查询；control/lease 用原 request_id，action.request/cancel 用 Envelope.id。done 是原请求完成，不等于当前仍可写或动作成功；动作视图重验结果读权；无秘密、不执行或赎领。

## chat.send

- 角色：`companion_control`；入口：`data`；能力：`core.events`；重试族：`message`。
- 输入：`chat_send_input`；必需字段：`version / session_id / id / type / sender / audience / payload / extensions`；可选字段：`correlation_id / expected_capabilities_revision / expected_membership_revision`。
- 成功输出：`chat_send_output`。
- 语义条件：sender 由凭据验证；team 需能力和 expected_membership_revision，受众冻结成员代次。

## action.request

- 角色：`companion_control`；入口：`data`；能力：`actions`；重试族：`message`。
- 输入：`action_request_input`；必需字段：`version / session_id / id / type / sender / audience / payload / extensions / expected_capabilities_revision`；可选字段：`correlation_id / expected_membership_revision`。
- 成功输出：`action_request_output`。
- 语义条件：Envelope.id 是 action ID；校验能力 revision/参数/一次确认，在效果临界区再次核权。

## action.cancel

- 角色：`companion_control`；入口：`data`；能力：`actions`；重试族：`message`。
- 输入：`action_cancel_input`；必需字段：`version / session_id / id / type / sender / audience / payload / extensions`；可选字段：`correlation_id / expected_capabilities_revision / expected_membership_revision`。
- 成功输出：`action_cancel_output`。
- 语义条件：仅原 actor；取消收据不证明未发生效果；目标 payload.request_id 不等于取消消息 ID。

## action.query

- 角色：`results_reader / agent / player / companion_control`；入口：`results`；能力：`actions`；重试族：`read`。
- 输入：`action_query_input`；必需字段：`session_id / action_id`；可选字段：`无`。
- 成功输出：`action_query_output`。
- 语义条件：原只读授权/期限/撤销/可见动作；不要求会话写权有效；重新认证原主体不扩大读权。

## action.confirm

- 角色：`player`；入口：`control`；能力：`actions`；重试族：`control`。
- 输入：`action_confirm_input`；必需字段：`session_id / action_request_id / action / arguments_digest / definition_digest / expires_at / decision_ref`；可选字段：`无`。
- 成功输出：`action_confirm_output`。
- 语义条件：一次玩家确认绑定 session、action、原请求 ID、参数与定义摘要；不能由 agent 代签。

## context.publish

- 角色：`game`；入口：`management`；能力：`core.events`；重试族：`message`。
- 输入：`context_publish_input`；必需字段：`version / session_id / id / type / sender / audience / payload / extensions`；可选字段：`correlation_id / expected_capabilities_revision / expected_membership_revision`。
- 成功输出：`context_publish_output`。
- 语义条件：只写批准开放类别；game 不续伙伴租约；来源绑定当前共享经历。

## player_chat.forward

- 角色：`game`；入口：`management`；能力：`core.events`；重试族：`message`。
- 输入：`player_chat_forward_input`；必需字段：`seat_proof_ref / envelope`；可选字段：`无`。
- 成功输出：`player_chat_forward_output`。
- 语义条件：当前 GameAuthority/Scope/成员代次席位证明绑定玩家 sender；按玩家/Envelope.id 去重，不续伙伴租约。

## capability.replace

- 角色：`game`；入口：`management`；能力：`actions`；重试族：`control`。
- 输入：`capability_replace_input`；必需字段：`instance / expected_revision / definitions`；可选字段：`无`。
- 成功输出：`capability_replace_output`。
- 语义条件：CAS；定义 ID 唯一；新增/改义不扩旧 Grant，执行中旧 fence 失效。

## membership.replace

- 角色：`game`；入口：`management`；能力：`core.events`；重试族：`control`。
- 输入：`membership_replace_input`；必需字段：`instance / expected_revision / verified_members / membership_proof_ref`；可选字段：`无`。
- 成功输出：`membership_replace_output`。
- 语义条件：基础席位也有成员代次；新增队伍席位需 team；重加入增加代次且不扩旧 Scope。

## permission.revoke

- 角色：`player / game`；入口：`control`；能力：`core.session`；重试族：`control`。
- 输入：`permission_revoke_input`；必需字段：`object_type / object_id / expected_revision`；可选字段：`无`。
- 成功输出：`permission_revoke_output`。
- 语义条件：按对象验证撤销权；game 只走管理入口；result_read 单独撤销不伪造不存在。

## action.claim

- 角色：`executor`；入口：`management`；能力：`actions`；重试族：`control`。
- 输入：`action_claim_input`；必需字段：`session_id / action_id / worker`；可选字段：`无`。
- 成功输出：`action_claim_output`。
- 语义条件：worker 必须登记；同控制请求可读原 ticket，ticket/step 仍唯一；新请求不领取已 executing 动作。

## action.commit_result

- 角色：`executor`；入口：`management`；能力：`actions`；重试族：`control`。
- 输入：`action_commit_result_input`；必需字段：`ticket / fact`；可选字段：`无`。
- 成功输出：`action_commit_result_output`。
- 语义条件：原可信 ticket 只报告事实；terminal 同摘要幂等，冲突拒绝；旧代不能执行新效果。

## launch.request

- 角色：`player`；入口：`local`；能力：`core.session`；重试族：`control`。
- 输入：`launch_request_input`；必需字段：`offer_id / application_registration / launch_permission_ref`；可选字段：`无`。
- 成功输出：`launch_request_output`。
- 语义条件：固定注册应用，禁止任意命令/路径；单次启动许可与接入批准分开。

## asset.resolve

- 角色：`resource_owner`；入口：`local`；能力：`assets`；重试族：`control`。
- 输入：`asset_resolve_input`；必需字段：`session_id / manifest / scope_digest`；可选字段：`无`。
- 成功输出：`asset_resolve_output`。
- 语义条件：批准来源/依赖闭包/大小/摘要/解析沙箱；不携带会话 secret 下载。

## presentation.acquire

- 角色：`presentation_authority`；入口：`local`；能力：`presentation`；重试族：`control`。
- 输入：`presentation_acquire_input`；必需字段：`session_id / generation / device_id / device_epoch / lease_revision / terms / deadline / scope_digest / authority_proof_ref`；可选字段：`无`。
- 成功输出：`presentation_acquire_output`。
- 语义条件：request_id 是 operation_id；绑定当前设备 epoch，初始 lease_revision=1；设备身份/条款/期限/tombstone 校验；重试不延长占用。

## presentation.renew

- 角色：`presentation_authority`；入口：`local`；能力：`presentation`；重试族：`control`。
- 输入：`presentation_renew_input`；必需字段：`session_id / generation / device_id / device_epoch / lease_revision / terms / deadline / scope_digest / authority_proof_ref`；可选字段：`无`。
- 成功输出：`presentation_renew_output`。
- 语义条件：仅当前游戏存活租约产生更高 revision；绑定设备 epoch/原条款，不续游戏租约；旧 revision/重试不延长占用，tombstone 不可复活。

## presentation.release

- 角色：`presentation_authority`；入口：`local`；能力：`presentation`；重试族：`control`。
- 输入：`presentation_release_input`；必需字段：`session_id / generation / device_id`；可选字段：`无`。
- 成功输出：`presentation_release_output`。
- 语义条件：仅清理自己的 generation；先写 tombstone，再按最新 baseline 重算，失败报告实际状态。

## privacy.request

- 角色：`data_subject`；入口：`privacy`；能力：`privacy-request`；重试族：`control`。
- 输入：`privacy_request_input`；必需字段：`source_refs / desired_action`；可选字段：`无`。
- 成功输出：`privacy_request_output`。
- 语义条件：发送实际数据控制者；验证每条来源主体权；仅对可控副本承诺。

## privacy.receipt

- 角色：`data_subject`；入口：`privacy`；能力：`privacy-request`；重试族：`read`。
- 输入：`privacy_receipt_input`；必需字段：`privacy_request_id`；可选字段：`无`。
- 成功输出：`privacy_receipt_output`。
- 语义条件：读取本人已提交请求的当前处理状态；不能由数据主体伪造存储方回执。

## relay.register

- 角色：`relay_controller`；入口：`relay`；能力：`core.session`；重试族：`control`。
- 输入：`relay_register_input`；必需字段：`instance / relay_identity / relay_origin / agent_principals / control_principals / registration_expiry / pairing_proof_ref / limits`；可选字段：`无`。
- 成功输出：`relay_register_output`。
- 语义条件：角色凭据由验证过的配对渠道分别交付，不把 game/agent/controller 三种 secret 同时交给注册者。

## relay.call

- 角色：`relay_agent / relay_controller`；入口：`relay`；能力：`core.session`；重试族：`relay`。
- 输入：`relay_call_input`；必需字段：`mailbox_id / call`；可选字段：`无`。
- 成功输出：`relay_call_output`。
- 语义条件：外层 lane 与内层主体都校验；固定 instance，无任意 URL；重复 call 不延长 deadline；inner reply 按原操作 schema 校验。

## relay.pull

- 角色：`relay_game`；入口：`relay`；能力：`core.session`；重试族：`control`。
- 输入：`relay_pull_input`；必需字段：`mailbox_id / pull_nonce / maximum_items`；可选字段：`无`。
- 成功输出：`relay_pull_output`。
- 语义条件：同 pull_nonce 返回原 claim；claimed 不重入队；凭据仅有领取/回复权限。

## relay.reply

- 角色：`relay_game`；入口：`relay`；能力：`core.session`；重试族：`control`。
- 输入：`relay_reply_input`；必需字段：`mailbox_id / claim_id / reply`；可选字段：`无`。
- 成功输出：`relay_reply_output`。
- 语义条件：精确 claim owner；reply 必须通过原 operation 的输出 schema 和 request_id 校验；重复相同结果幂等。

## relay.revoke

- 角色：`relay_controller`；入口：`relay`；能力：`core.session`；重试族：`control`。
- 输入：`relay_revoke_input`；必需字段：`mailbox_id / expected_route_revision`；可选字段：`无`。
- 成功输出：`relay_revoke_output`。
- 语义条件：queued 原子关闭可证明本路径未投递；claimed 只能 unknown；作废全部外层凭据但不伪造世界回滚。

## 边界错误目录

| code | category | retry | outcome | HTTP |
| --- | --- | --- | --- | --- |
| unauthenticated | authentication | after_reauth | not_accepted | 401 |
| permission_denied | authorization | never | not_accepted | 403 |
| invalid_message | validation | never | not_accepted | 400 |
| invalid_arguments | validation | never | not_accepted | 400 |
| invalid_cursor | validation | never | not_accepted | 400 |
| unsupported_media_type | validation | never | not_accepted | 415 |
| message_too_large | limit | never | not_accepted | 413 |
| unsupported_operation | negotiation | after_renegotiate | not_accepted | 409 |
| unsupported_version | negotiation | after_renegotiate | not_accepted | 409 |
| feature_unsupported | negotiation | after_renegotiate | not_accepted | 409 |
| trust_profile_unsupported | negotiation | after_renegotiate | not_accepted | 409 |
| negotiation_failed | negotiation | after_renegotiate | not_accepted | 409 |
| id_conflict | conflict | never | not_accepted | 409 |
| redemption_conflict | conflict | never | not_accepted | 409 |
| invitation_used | conflict | never | not_accepted | 409 |
| generation_conflict | conflict | never | not_accepted | 409 |
| stale_capabilities | conflict | never | not_accepted | 409 |
| membership_conflict | conflict | never | not_accepted | 409 |
| execution_conflict | conflict | never | not_accepted | 409 |
| reply_conflict | conflict | never | not_accepted | 409 |
| approval_stale | authorization | after_renegotiate | not_accepted | 409 |
| offer_expired | authorization | after_renegotiate | not_accepted | 409 |
| grant_revoked | authorization | after_renegotiate | not_accepted | 409 |
| invitation_expired | authorization | after_renegotiate | not_accepted | 409 |
| consent_required | authorization | after_renegotiate | not_accepted | 409 |
| action_consent_required | authorization | after_renegotiate | not_accepted | 409 |
| handoff_required | authorization | after_renegotiate | not_accepted | 409 |
| session_closed | state | never | not_accepted | 409 |
| session_conflict | state | never | not_accepted | 409 |
| session_not_writable | state | never | not_accepted | 409 |
| transfer_in_progress | state | never | not_accepted | 409 |
| resume_denied | state | never | not_accepted | 409 |
| request_expired | state | never | not_accepted | 409 |
| occupation_released | state | never | not_accepted | 409 |
| stale_controller | authentication | after_reauth | not_accepted | 401 |
| stale_transport | authentication | after_reauth | not_accepted | 401 |
| avatar_required | resource | after_renegotiate | not_accepted | 409 |
| avatar_incompatible | resource | after_renegotiate | not_accepted | 409 |
| resource_policy_denied | resource | after_renegotiate | not_accepted | 409 |
| resource_integrity_error | resource | after_renegotiate | not_accepted | 409 |
| resource_limit | limit | same_request | not_accepted | 429 |
| rate_limited | limit | same_request | not_accepted | 429 |
| result_expired | retention | never | not_accepted | 409 |
| result_unavailable | retention | never | not_accepted | 409 |
| history_gap | history | never | not_accepted | 409 |
| launch_failed | lifecycle | never | accepted | 409 |
| presentation_unavailable | lifecycle | never | accepted | 409 |
| admission_failed | lifecycle | never | accepted | 409 |
| transfer_failed | lifecycle | never | accepted | 409 |
| temporarily_unavailable | availability | same_request | not_accepted | 503 |
| transport_timeout | uncertain | same_request | unknown | 504 |
| internal_failure | uncertain | same_request | unknown | 503 |
| request_gone | state | never | unknown | 409 |
| relay_not_dispatched | transport | same_request | not_accepted | 503 |
| action_not_executable | state | never | not_accepted | 409 |
| operation_rejected | state | never | not_accepted | 409 |
| operation_failed | lifecycle | never | accepted | 409 |
| outcome_unknown | uncertain | same_request | unknown | 409 |
