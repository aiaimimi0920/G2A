# 数据面、行动账本与恢复伪代码

依据：[总设计](PROTOCOL.md) 与 [控制面](CONTROL_PLANE.pseudo.md)。本文件落实 I02、I04–I07、I09–I10；不是旧 SDK 源码，也不声称模型已在真实引擎执行。

## 1. 共享记录与执行端口

补充模型记录：

```text
Session.runtime:
  admission_ready, admission_deadline, transport_epoch, control_generation
  approved_action_digests, current_actions, membership, policy_revision
  receipt_index, action_index, event_floor, event_high_watermark
  privacy_read_revision, recovery_contract_digest
ActionRecord.execution:
  ticket_id, execution_fence, worker_identity, last_step, effect_journal[]
  deadline, acceptance_generation, acceptance_transport_epoch, stop_requested, terminal_result_digest?
ReceiptIndex[(session_id, principal, message_id)] = {request_digest, original_receipt}
ResultHandle = {session_id, authorized_readers, allowed_action_ids,
  access_revision, until_session_close_plus_retention, revoked}
```

`WorldGate` 必须与 grant/session/capability 撤销使用同一串行化边界。跨进程实现不能只在网络请求到达时检查一次，然后声称游戏效果受保护。它有两种明确模式：

| 模式 | 端口保证 | 允许的恢复 |
| --- | --- | --- |
| journaled | `WorldGate.effect` 在同一可恢复事务记录效果和结果证据，按 action/ticket/step 去重 | 查询相同 effect key 取得原事实；不能换 ID 重做 |
| fenced-nonatomic | 先持久消耗执行 step 权，随后一次调用引擎；原临界区防止新撤权先通过却又产生新效果 | 崩溃窗口返回 unknown；没有效果账本时禁止重做该 step |

WorldGate 输入为当前执行 ticket、step 编号、固定动作参数与游戏世界条件；输出 committed/denied/failed/uncertain 及 effect=none/partial/committed/undetermined。日志凭证标识执行事实，不包含管理员令牌。游戏执行器属于已验证 GameAuthority；伙伴无法生成 ticket 或选择 WorldGate 模式。

伪代码 `transaction domain` 意味着同一权限/效果排序域，不强制特定数据库。若真实实现不能提供该排序，不能宣称具有本设计的执行中撤权保证，必须拒绝接入要求该保证的动作，而非偷偷降级。

## 2. 数据入口、去重与内容边界

```text
function authorized_control_in_tx(proof, session_id):
  identity = Secrets.verify(proof, audience=instance, role=companion_control)
  session = sessions.lookup_for(identity.principal, session_id)  // 失败不暴露存在性
  require identity.transport_epoch == current_transport_epoch
  require identity.generation == session.control_generation else stale_controller
  close_expired_before_read(session)
  require session.active and session.admission_ready else session_not_writable
  require grant(session).active and now < grant(session).expires_at
  return identity, session

function submit(proof, envelope):
  validate_bounded_envelope(envelope)  // UTF-8、大小、嵌套、类型，先限制解析成本
  atomic(instance_authority, envelope.session_id):
    identity, session = authorized_control_in_tx(proof, envelope.session_id)
    require envelope.version == session.scope.version
    require envelope.sender == identity.principal
    key = (session.id, identity.principal, envelope.id)
    digest = canonical_digest(envelope)
    if key in receipts:
      require receipts[key].request_digest == digest else id_conflict
      return receipts[key].original_receipt with duplicate=true
      // 不续租、不重新触发事件或效果；结果另外 query
    require request deadline not expired if supplied
    activated = validate_frozen_message_extensions(envelope.extensions,
      session.scope.extensions, local_implemented_extension_versions)
    validate_activated_extension_semantics_without_expanding_core_authority(activated)
    // 新请求必须检查；旧收据重放不再执行扩展。空扩展 action.cancel 走核心止损路径。
    reserve_bounded_capacity_for_receipt_event_and_record_or_reject()
    if envelope.type == chat.message:
      event = accept_chat(session, identity, envelope)
    else if envelope.type == action.request:
      event = accept_action(session, identity, envelope)
    else if envelope.type == action.cancel:
      event = accept_cancel(session, identity, envelope)
    else:
      reject unsupported_operation  // context、能力更新、结果不能由伙伴伪造
    receipt = Receipt(envelope.id, now, digest, event.outcome_ref, duplicate=false)
    receipts[key] = {digest, receipt}
    append_event_in_tx(session, event)
    renew_lease_for_new_accepted_companion_message(session)
    commit record + receipt + event + outbox
    return receipt
```

已经接受的旧请求再次发送时，在当前身份、会话和控制代次验证后返回旧收据，不因当前能力 revision 已改变而再次执行。已经关闭会话的旧请求不能写入；用户用结果句柄读取原动作，而不是以重复提交恢复写权限。

`resource_limit` 若发生在 reserve 阶段，整项未接受；若提交已成功但响应丢失，调用方只知道 unknown，应使用相同 ID/内容查证。服务端为 close/query/revoke 预留控制容量，不能因收据区满阻止退出或撤权。

## 3. 情境、聊天和动态成员

```text
function freeze_audience(session, sender, envelope):
  require envelope.audience nonempty and contains no wildcard
  require every recipient is verified and present in session.membership
  require envelope.audience subset session.scope.audiences
  require sender allowed to address this channel
  if envelope.type == chat.message:
    validate Chat schema, not merely generic Envelope
    require sender in session.scope.audiences and current session.membership
    if channel == private:
      require sender in {session.player, session.agent}
    // game.context 使用独立 GameAuthority，不要求游戏身份为聊天成员
  if channel == private:
    require recipients subset {session.player, session.agent}
  if channel == team:
    require team negotiated
    require envelope.expected_membership_revision == session.membership_revision
  return immutable_copy(recipients paired with current membership_generation)
  // audience on wire 是 Principal；冻结记录另带成员 incarnation，不能由调用方填

function accept_chat(session, sender, envelope):
  require payload is negotiated content type  // 核心为纯文本，不执行 HTML/脚本
  recipients = freeze_audience(session, sender, envelope)
  validate_provenance_declaration(payload.provenance, sender, session)
  enforce_declared_disclosure_scope(payload.source_refs, recipients)
  source_revisions = validate_disclosure(envelope, session, trusted_source_imports, now)
  // 所需读者还包含 privacy_model.visible_to；冻结来源 revision，投递时再检查。
  // 发送方须在发出正文前预检；接收端拒绝不能撤销已经收到的明文。
  // 不能证明模型暗中泄密；可检查显式标签，且不能扩大宿主数据权限
  return Event(chat.message, payload, frozen_audience=recipients)

function publish_context(game_proof, session_id, envelope):
  atomic(instance_authority, session_id):
    game = authenticate_game_authority(game_proof, instance)
    session = writable_game_session(session_id)  // 不续伙伴租约
    require envelope.sender == game or valid_game_delegation
    require envelope.type == game.context
    require payload.category in session.scope.context_categories
    check_per_role_dedup_before_creating_event()
    recipients = freeze_audience(session, game, envelope)
    payload.provenance = declared_shared_experience_for_this_session
    // 声明不是密码学事实证明，不编造其他玩家经历
    commit context event + game receipt + outbox

function game_forward_player_chat(game_proof, seat_proof_ref, envelope):
  atomic(instance_authority, session_id):
    authenticate exact GameAuthority on management lane; require writable session/Grant
    seat = trusted_seat_registry.lookup(seat_proof_ref)  // wire cannot provide this record
    require seat binds game/instance/session/scope_digest and active issued_at <= now < expires_at
    require seat.player == envelope.sender and sender.kind == player
    require seat.membership_revision and incarnation equal current member facts
    require sender in current approved audience; recheck this even for duplicate messages
    key = (session, player, Envelope.id); digest = canonical_envelope_digest(envelope)
    if old Receipt exists: require same digest; return original non-content Receipt(duplicate=true)
    validate active/frozen extensions, current channel/audience and all source disclosures
    reserve bounded capacity; commit player chat event + Receipt + outbox
    never renew companion lease
  // 固定可信席位映射不证明正文由真人实际输入；真实输入端口另验。

function membership_replace(game_proof, expected_revision, new_verified_members):
  atomic(instance_authority):
    authenticate GameAuthority; require current revision == expected_revision
    validate player/agent mapping; membership_revision++
    removed = old - new; added = new - old
    increment membership_generation for every new/rejoined principal
    for affected session:
      replace current_membership; do not expand scope.audiences
      expire pending team deliveries to removed members
      append capability-neutral membership notice to still-authorized recipients
    // 新成员不会因加入队伍进入旧 Grant；要向新增主体披露需新批准范围
    return new revision
```

通过新授权扩大 audience 时，本版使用新 Grant/新 Session，旧 Session 关闭并保留结果读取；不原地改写旧 scope。未来可加 reauthorize 扩展，但不能假定它已存在。对同一队伍中的不同玩家，不能用一人的批准替代另一人的私聊披露同意。

## 4. 事件分页与历史缺口

结构修订见 [事件与业务快照恢复](EVENT_RECOVERY_PROOF.md)：current_visible_snapshot 返回
完整 RecoverySnapshot（不是裸 SessionView）。session、cursor、可见动作/情境/定义/成员
必须从同一权限/状态切点捕获；unresolved_actions 与该快照内未确定终态的动作集合一致。
八类核心通知有闭合 schema；请求/取消/结果通知统一 action.state。

```text
function read_events(proof, session_id, cursor, page_size, poll_nonce):
  atomic(instance_authority, session_id):
    identity, session = authorized_control_in_tx(proof, session_id)
    require cursor belongs to session/epoch and is not future_cursor
    page_size = clamp_to_negotiated_limit(page_size)
    if cursor < session.event_floor:
      return history_gap(snapshot=current_visible_snapshot(identity, session),
        next_cursor=session.event_high_watermark,
        unresolved_actions=visible_action_refs(identity, session))
      // 错误响应不续租；客户端可另发有效 heartbeat
    visible=[]; scanned=0; last_scanned_cursor=cursor
    while sequence <= captured_high_watermark and scanned < scan_budget:
      event = next event; scanned++; last_scanned_cursor=event.sequence
      if (identity.principal,current_membership_generation) in event.frozen_audience
        and currently_authorized_for_event(identity, session, event)
        and source_disclosure_not_revoked(event):
          visible.append(event)
      if len(visible) == page_size: break  // 不越过本页未返回的可见事件
    renew lease once per fresh authenticated poll_nonce, not per duplicate receipt
    return visible and last_scanned_cursor and captured_high_watermark
```

返回的 cursor 是最后扫描位置，不是最后可见消息的序号；空页也可推进 cursor。必须先限制扫描量再过滤，不能因大量不可见事件导致无界扫描。分页不得因省略受众检查而泄露消息正文；cursor 不是凭据，不能跨会话查询。

重复 poll 保存原扫描窗口和原租约，不存一份可无条件重播的正文响应。重试必须在当前
授权/来源/成员代次下重新过滤原窗口，不续租；窗口已裁剪时返回新鲜过滤的 history_gap。
该规则的服务端可执行证据见 [事件服务与一致快照](EVENT_SERVER_PROOF.md)。

成员退出再加入使用新的 membership_generation，因此即使 Principal 相同，也不会自动恢复旧队伍事件的领取资格。核心玩家/伙伴席位同样由服务端分配成员代次；显式历史授权若未来实现，应是独立能力，不直接改旧事件的冻结受众。

关闭通知是 best-effort outbox；即使写凭据已撤销，下一次 poll 返回 session_closed，客户端释放呈现占用。服务端无需为了投递关闭事件恢复旧凭据。正常心跳和结果读取分别有独立操作，不依赖事件流保留期。

## 5. 接受动作、额外确认与取消

```text
function confirm_action(player_proof, session_id, action_request_id, action_id,
                        arguments_digest, definition_digest, expires_at, decision_ref):
  // action.confirm：外层 control_mutation 保证同请求不重复签发
  player = authenticate_verified_player(player_proof)
  atomic(instance_authority, session_id):
    require session belongs to player and is active/ready with actions negotiated
    require action_id in current approved actions and definition.requires_per_action_consent
    require definition_digest == digest(action-definition, exact current ActionDefinition)
    require now < expires_at <= min(grant.expires_at, session.lease_deadline)
    verify decision_ref binds player/session/action_request_id/action_id/
      arguments_digest/definition_digest/expires_at and explicit allow
    persist confirmation bound to exact tuple, unconsumed=true
    return confirmation_id + expires_at
    // 不创建 action、不消耗执行 step、不续租；客户端后续提交原 action_request_id

function accept_action(session, agent, envelope):
  require actions negotiated and envelope.expected_capabilities_revision == current_revision
  definition = session.current_actions[envelope.payload.action]
  require definition exists and action_id in session.scope.action_ids
    require digest(action-definition, entire definition) == session.scope.approved_action_digests[action_id]
  require definition.parameters accepts envelope.payload.arguments
  require session.scope permits actor, arguments and current limits
  deadline = min(requested_deadline, now + definition.maximum_duration,
    session.lease_deadline, grant.expires_at)
  require deadline > now
  if definition.requires_per_action_consent:
    confirmation = verified_one_time_action_decision(envelope.payload.confirmation)
    require binds(player, session, envelope.id, arguments_digest, definition_digest)
    require confirmation valid and unconsumed else action_consent_required
    consume confirmation in this transaction
  action = ActionRecord(request_id=envelope.id, actor=agent, state=pending,
    capability=definition.id, arguments=immutable_copy(arguments),
    arguments_digest, authorization_revision=current_revision,
    acceptance_generation=session.control_generation,
    acceptance_transport_epoch=session.transport_epoch, deadline,
    effect=none, cancel_requested=false)
  store action; return private_action_accepted_event(action, player_and_agent)

function accept_cancel(session, agent, envelope):
  action = lookup_owned_action(session, agent, envelope.payload.request_id)
  if action terminal: return action_state_event(action)  // 不伪造成功取消
  action.cancel_requested = true
  if action.pending:
    action.state = cancelled; action.effect = none; finalize_result(action)
  else:
    action.stop_requested = true; advance_execution_fence(action)
    // 与 WorldGate 排序：阻止新的 effect step，已开始的一步可能完成
    outbox executor.stop(action.ticket_id)
  return cancel_requested_event(action)  // 收据只证明已接收取消
```

额外一次确认由控制面生成，明确 `action_id + 参数摘要 + request_id + 能力摘要 + session`；普通授权不得自动签发高风险单次确认。伙伴可以先选择 request_id 再申请确认，但申请确认不是执行请求，不预占世界效果。确认超时则不接受动作；重复同消息依靠入口去重复用收据，不再次消耗确认。

## 6. 领取与实际效果的排序

```text
function claim_action(game_proof, session_id, request_id, worker_identity):
  atomic(instance_authority, session_id, request_id):
    authenticate GameAuthority and registered execution worker
    session = sessions[session_id]; close_expired_before_read(session)
    action = actions[session_id, request_id]
    if action.state != pending:
      return already_claimed_or_final(action.state)  // 不再授予执行许可
    if not session.active or not session.admission_ready or not grant.active:
      finalize cancelled/none; return not_executable
    if action.cancel_requested or now >= action.deadline:
      finalize cancelled/none; return not_executable
    if capability_removed_or_contract_changed(action):
      finalize cancelled/none; return stale_capabilities
    if action.acceptance_generation != session.control_generation:
      finalize cancelled/none; return stale_controller
    action.state = executing
    action.ticket_id = unique_unforgeable_ticket()
    action.execution_fence = current_authority_fence
    action.worker_identity = worker_identity
    persist ticket consumed=false, step_counter=0
    return ticket + immutable_arguments + execution_constraints

function world_step(worker_proof, ticket, step_no, game_condition):
  enter WorldGate.transaction_domain(instance_authority):
    authenticate registered worker bound to action.ticket_id
    verify ticket binds exact action and immutable argument digest
    if journal contains same (ticket, step_no): return original_step_fact
    require step_no == action.last_step + 1 else execution_conflict
    require action.state == executing and not stop_requested
    require session.active and session.admission_ready
    require now < action.deadline and now < session.lease_deadline
    require grant.active and ticket.fence == action.execution_fence
    require current_definition_digest == approved_digest(action)
    require acceptance_generation == current_control_generation
    require acceptance_transport_epoch == current_transport_epoch
    // 进程重启后即使尚未完成 resume 升代，旧 ticket 也只能查证/报告旧事实，不能执行新 step。
    if not game_condition or not current_world_permission:
      return WorldGate.denied_without_effect(ticket, step_no, reason=world_rejected)
      // 证明本 step 未执行，不覆盖此前 step 已发生的 partial 效果
    persist one-time step_claim before external effect
    result = WorldGate.effect(ticket, step_no, immutable_args, mode)
    if result uncertain:
      action.state = unknown; effect=undetermined; prohibit next effect
    else:
      append result proof; action.last_step=step_no
      record actual cumulative effect
    commit or preserve consumed step_claim after nonatomic crash
    return result
```

执行器不能在丢失 world_step 回包后直接发下一步，必须查询原 step。非事务模式存在 consumed claim 而无事实时，得到 unknown，不把 claim 当作“肯定没执行”。长动作每个可能产生效果的阶段都经过 gate；不能一次批准后无限执行。撤销与效果先后由同一排序域决定：效果先获得临界区则可发生，撤销先提交则之后的效果必须被拒绝。

`advance_execution_fence(action)` 只提升该动作记录要求的 fence，原 ticket 携带旧 fence，后续 world_step 因不匹配被拒绝；不能把新 fence 自动写回旧 worker 的 ticket。commit_result 则允许原 ticket 报告已经产生的事实，不能调用 world_step。

执行器收到 gate 的已验证拒绝后，汇总该 ticket 的既有 step 事实：之前无效果则 failed/none，已有部分效果则 failed/partial；收到取消/撤权停止则 cancelled/none 或 cancelled/partial。无完整既有事实则 unknown/undetermined，不能把“这一步未执行”推广成“整个动作没发生”。这个汇总仍通过 commit_result，不由伙伴提交终态。

## 7. 提交结果与未知状态恢复

```text
function commit_result(worker_proof, ticket, report):
  atomic(instance_authority, session_id, action_id):
    worker = authenticate registered result-reporter for this ticket
    // 不需要仍有效的伙伴写凭据；旧执行 ticket 只允许报告此动作的事实
    action = lookup_ticket_record(ticket)
    verify report action/parameters/ticket/step proofs match stored execution
    require report.final_status in {succeeded, failed, cancelled, unknown}
    require effect matches available_world_evidence(report)
    if action.state in {succeeded, failed, cancelled}:
      if digest(report)==action.terminal_result_digest: return old_result
      record security audit; reject execution_conflict
    if report.final_status != unknown:
      require trustworthy_proof_of_outcome_or_executor_attestation(report)
      require result conforms to recorded_result_schema
    // unknown 可以被原执行器/受信对账者以原事实解决，不能通过重执行解决
    action.state = report.final_status
    action.effect = report.effect; action.result = frozen(report)
    action.result_revision++
    if terminal: action.terminal_result_digest = digest(report)
    append event for currently authorized frozen readers
    commit action + result notification outbox
    return result

function query_action(read_proof, session_id, action_id):
  atomic(session_id):
    reader = verify_current_control_or_results_only_handle(read_proof)
      or verify_fresh_original_principal_against_persisted_result_read_grant(read_proof)
    // 第二种仅由重新认证控制面进入，用于原句柄回包丢失；绝不授写权
    require reader subject/session/access_revision permits exact action
    require result_read_permission not revoked
    if now > recorded_result_read_until: return result_expired
    action = owned_action_lookup_without_existence_leak(reader, action_id)
    return {state, effect, result_revision, known_result, query_until}
    // 不续租、不恢复写权、不执行动作

function recover_execution_ledger(instance):
  require trusted recovery authority and intact identity/grant/store state
  for action with executing or unknown:
    fact = WorldGate.query_existing_effects(action.ticket_id)
    if fact complete and verifiable: commit_result(recovery_identity, ticket, fact)
    else: persist unknown/undetermined and block effect replay
  for pending action:
    if session/grant/lease/generation no longer valid: finalize cancelled/none
    else leave pending for normal one-time claim; never claim automatically on behalf of Agent
```

执行器的可信报告保证取决于游戏权威；协议不证明恶意游戏在现实中没有说谎。`effect=partial` 的 failed/cancelled 仍是结果，不应简化为“什么都没发生”。查询截止后保留只读 tombstone 或等价安全拒绝，不能把旧 ID 当全新动作接受。

## 8. 动态能力、scope 不变与恢复边界

```text
function replace_capabilities(game_proof, expected_revision, definitions):
  atomic(instance_authority):
    authenticate GameAuthority
    require expected_revision == current_capability_revision
    validate definitions and unique IDs; current_capability_revision++
    changed = compare security_contract_digests(old, definitions)
    update authoritative definitions
    invalidate pending offers/invitations bound to old descriptor revision
    for active session:
      effective = definitions whose IDs are in scope.action_ids
        and digest matches approved_action_digests
      session.current_actions = effective  // 新增/改义动作不扩权
      session.capabilities_revision = current_capability_revision
      for affected action:
        if pending and not in effective: finalize cancelled/none
        if executing and not in effective:
          stop_requested=true; advance_execution_fence(action)
      append capability.update event with authorized effective definitions

function validate_recovery_contract(session, current_descriptor):
  require identity/instance/transport trust/privacy/version/presentation terms unchanged
  require no security limit reduction invalidates committed retention
  require current_membership and current_actions reconstructed from persisted updates
  // 能力/队伍动态缩减按其 revision 恢复，不因 descriptor.revision 不同一概误判
  // 新增能力/受众不加进旧 scope；需要新批准/会话
  if core contract changed: return resume_denied and close old session
  return recoverable
```

等待 join 的授权使用完整 descriptor revision，已活动会话则对允许的动态缩减维护独立 revision。模型中区分这两个阶段：不能把“批准后改描述必 stale”错误用于拒绝所有正常动态撤权，也不能借动态更新更换隐私模型或提供者。

## 9. 跨游戏来源与隐私请求

本节来源声明/权威授权的可执行补充见 [来源与聊天验证](SOURCE_AND_CHAT_PROOF.md)，
隐私字节链及固定假存储见 [隐私请求与回执](PRIVACY_PROOF.md)。显式来源可用于
chat/context 接受和投递过滤，不将跨游戏导入认证或自然语言内容安全记为通过。

```text
function resolve_user_policy(user_explicit, game_defaults, companion_defaults={}):
  require all keys negotiated; reject unknown standard policy keys
  effective = copy(companion_defaults)
  overlay game_defaults then user_explicit, without truthiness-based omission
  // 显式 false 是用户选择；只有 absent 才继承默认值
  if effective conflicts with declared non-permission admission requirement:
    return negotiation_failed with incompatible terms
  return effective  // 不修改 action_ids、audiences 或数据开放范围

function companion_memory_ingest(event, local_memory_policy):
  verify received event was authorized for this principal
  record source_kind/source_id/source_principals/original_disclosure_scope
  do not upgrade player_report or external_reference to shared_experience
  optional persist under user's storage policy; no mandated database

function companion_prepare_disclosure(memory_refs, target_session, recipients):
  for ref:
    require target use allowed by user's explicit disclosure rule
    require recipients subset permitted_disclosure_scope(ref)
    require not revoked and no other participant's private data included without authority
    minimize to needed summary; attach source metadata
  if any check uncertain: withhold affected content, explain insufficient permission
  return sanitized_message  // 实现端负责，不由协议虚构文本泄漏可完全验证

function privacy_request(subject_proof, request_id, source_refs, desired_action):
  verify fresh data_subject on privacy lane at actual controller; require negotiated privacy-request
  // 主体隐私权独立于游戏 Grant；不能使用游戏写凭据或披露到期来取得/剥夺该权。
  if same subject/request_id exists:
    require same canonical digest; reuse original privacy_request_id and provider operation
  else:
    verify every source belongs to exact controller/context and subject; reject mixed invalid batch
    require no overlapping unresolved request and bounded capacity
    atomic:
      persist exact source/copy scope, cutoff revision, provider operation and pending receipt
      stop future controlled disclosure; fence old events and subsequent source reimports
  if not dispatched:
    persist dispatch marker before MemoryStore.apply_to_owned_copies(original frozen binding)
  // 一旦标记派发，只查原作业；缺失回执不证明可安全重删。
  return verified original storage receipt or pending(original id, controlled_scope, bounded poll)
  // 只处理受控且主体权限足够的副本；共享/外部/保留/未知必须如实报告，效果不回滚。

function privacy_receipt(subject_proof, privacy_request_id):
  verify fresh original data subject and exact controller/request ownership, independent of game Grant
  read persisted terminal result or query same stored provider operation id
  verify trusted receipt evidence and canonical exact binding before committing current progress
  return pending or actual done/partial/denied receipt
  // 不重新发起删除、不扩大 source_refs、不因查询而新签授权
```

删除请求不是删除其他参与者所有记忆或游戏存档的权限。已经投递给另一终点的数据不可由撤销事件强制追回；只对本方可控制的后续披露/副本作承诺。第三方汇总内容无法确定来源时，拒绝虚构删除成功。

## 10. 时钟推进与有界回收

```text
function maintenance_tick(now):
  for bounded batch of sessions in expiry index:
    atomic(instance_authority, session_id):
      if session.active and lease/grant expired: close_in_transaction(session, expired)
      for pending action with deadline <= now:
        finalize cancelled/none
      for executing action with deadline <= now:
        advance_execution_fence(action)
        set unknown/undetermined, stop_requested=true
      expire event history according to advertised retention; move event_floor
      do not remove receipts during writable session or negotiated resume window
      after closed + all retry windows expired:
        remove large request bodies; retain denial tombstones or retire scope epoch
      after result_read_until and no authorized preservation requirement:
        discard large result content; keep authorized result_expired classification
  for pending admissions/transfers expired: fail and enqueue releases
  expire offers, unused invitations, auto rules and provider transactions
  reclaim expired relay requests without re-enqueueing claimed work
```

时钟推进可以由定时器及查询/写操作入口触发，不能依赖客户端正常退出。回收不删除玩家业务记忆或游戏存档；只处理协议声明的有界运行记录。没有完整 ledger 的旧 epoch 请求返回 unavailable/reauth，不创建空白同名会话来“恢复”。错误退出提交的语义见控制面事务说明。

## 11. 复核点

数据面已与 admission/presentation/handoff 的关键崩溃窗口及 S01–S14 场景交叉复核，见 [推演记录](WALKTHROUGH_RESULTS.md)。其中模型执行与人工符号推演分别标明；没有运行引擎、实施真网络认证或改变现有实验 schema。后续真实实现仍须兑现 WorldGate、Store 和身份端口的保证。
