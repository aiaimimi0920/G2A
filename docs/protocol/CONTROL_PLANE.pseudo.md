# 控制面与会话伪代码

依据：[协议总设计](PROTOCOL.md)。这是结构化伪代码，不是可运行 Python；`atomic`、时钟、身份和存储由下列端口提供。未协商的能力一律拒绝，而不是运行空函数后宣称成功。

## 1. 外部端口的必要契约

| 端口 | 输入与输出 | 保证/失败 |
| --- | --- | --- |
| Identity.verify | transport proof、expected audience、所选 trust profile → VerifiedPrincipal | 验证签发者/受众/期限/角色；失败 AuthError；测试端口仅接受预登记表，不接受自报 ID |
| Consent.verify_decision | 已认证玩家交互、offer_id、scope_digest、allow、remember、launch_permission → ConsentEvidence | 验证玩家对 offer 归属与一次交互 nonce；Agent 文本不算确认；重复返回原证据 |
| Launcher.start | 已验证应用注册 ID、一次启动许可 → VerifiedProcess、LaunchError 或 unknown | 固定程序/参数；独立消费/效果账本，未知只查原事务；真实凭据管道另验，失败不创建 session |
| Provider.complete | server-side transaction ID、验证回调证明 → player↔agent 委托 | 校验发起方、受众、state/nonce、有效期、单次事务；重复回调复用结果；任意 URL 不可改目的地 |
| Store.atomic | 有序的作用域锁 + 事务函数 → 原子结果 | 同事务写状态、收据、outbox；异常全回滚；持久能力需重启后完整，不完整报告 LedgerUnavailable |
| Clock.now | 无 → 单调可比较时间；持久模式有受信到期策略 | 时钟回退或无法判定期限时不延长权限 |
| Secrets.issue/verify/revoke | principal/audience/role/generation/expiry → opaque credential | 不输出到日志；比较/签名交给成熟实现；假实现是表映射且仅用于推演 |
| Presentation | session、设备证明、批准条款、租约 → 占用回执或错误 | 独立 CAS/revision；失败关闭新会话，不影响其他会话；详细算法后续数据面文档提供 |
| Outbox.deliver | 已原子提交的事件 → 可重复投递 | 不保证网络 exactly-once；消费者用 event/request ID 去重 |

假实现必须可以注入：认证失败、存储提交失败、启动失败、回调超时、时钟推进、发送丢失和重启。禁止为方便把这些端口永久固定为成功。

事务伪代码约定：普通 `require` 失败回滚本次尚未接受的修改；`commit_and_return` 则原子提交明确的失效/关闭维护状态并立即退出外层处理器。到期维护发生在接受新操作之前，不能在写入新动作后使用它提交半个请求。不得让“检查到期→闭会→抛异常回滚闭会”造成过期会话仍可写。

## 2. 状态容器与公共检查

```text
State:
  identities, descriptors, instances, auto_rules
  offers, grants, invitations, sessions, write_credentials, result_handles
  receipts, actions, events, outbox, provider_transactions
  // key/role/epoch/generation 约束与 PROTOCOL 对象一致

function authenticate(proof, audience, role, profile):
  identity = Identity.verify(proof, audience, profile)
  require identity.role allows role else permission_denied
  return identity

function assert_current_scope(scope):
  instance = instances[scope.instance.instance_id]
  require instance.epoch == scope.instance.epoch else approval_stale
  descriptor = descriptors[scope.instance]
  require descriptor.revision == scope.descriptor_revision else approval_stale
  require descriptor still supports scope.version/features/binding/trust_profile
  require scope.action_ids subset descriptor.actions
  require scope.expires_at > Clock.now() else invitation_expired
  // scope_digest 来自版本化 canonical 编码，不比较 UI 显示文本

function assert_grant(grant):
  require grant.state == active and Clock.now() < grant.expires_at
  assert_current_scope(grant.scope)

function close_expired_before_read(session):
  if session.state == active and Clock.now() >= session.lease_deadline:
    close_in_transaction(session, expired)
    commit_and_return(session_closed)  // 提交失效，不由后续 require 回滚
  // 查询不能意外为过期会话续租
```

## 3. 发现与协商

伙伴侧的 AgentController 负责跨游戏接入 slot；游戏服务端自己的唯一性锁只能约束其授权域。

```text
function reserve_companion_slot(agent_proof, offer_id, deadline):
  verify agent belongs to this authenticated controller domain
  atomic(agent):
    expire only slots whose authoritative admission/session lease has ended
    if same offer has slot: return existing_slot
    if multi-session not negotiated: require no other live slot else session_conflict
    require total slots < negotiated and local maximum
    create slot(offer_id, state=preparing, expires_at=deadline)
    return slot

function attach_slot(slot, verified_join_response):
  atomically bind session_id/authority/epoch/generation/lease to same offer
  renew only from authenticated fresh heartbeat/ready response, never old receipt

function release_slot(slot, reason):
  idempotently mark released; do not erase memory or another session's slot
  if slot.session still active: request close and locally stop sending
```

```text
function discover(candidate):
  // candidate 可来自本地注册、游戏入口或提供者列表，不信任其自述
  public = Binding.read_minimal_descriptor(candidate)
  verified_peer = Identity.verify_endpoint(candidate, public.claimed_identity)
  require verified_peer succeeded else unauthenticated
  return VerifiedCandidate(public, verified_peer)  // 尚无加入/读取世界权限

function negotiate(candidate, player, agent, requested, endpoint_capabilities):
  descriptor = authenticated_describe(candidate, player, agent)
  version = highest_exact_common_version(descriptor, endpoint_capabilities)
  require version exists else unsupported_version
  features = intersection(descriptor.supported, endpoint_capabilities.supported)
  require all dependencies satisfied and descriptor.required subset features
  require requested.required subset features else feature_unsupported
  binding = choose_mutually_accepted_verified_binding(descriptor, endpoint_capabilities)
  trust = choose_mutually_accepted_trust_profile(descriptor, endpoint_capabilities)
  reject silent security downgrade
  avatar = select_avatar_if_negotiated(features, requested, descriptor)
  presentation = select_terms_if_negotiated(features, requested, descriptor)
  // 未协商则 omit，不填假 false 或假形象
  scope = Scope(player, agent, descriptor.instance, version, binding, trust,
    features, descriptor.revision,
    intersect(requested.actions, descriptor.actions),
    approved_action_digests = exact selected definitions hashed in action-definition domain,
    intersect(requested.context_categories, descriptor.allowed_context),
    verified_audience_set(player, agent, requested, descriptor),
    resolve_user_policy(requested.policy, descriptor.policy_defaults, requested.companion_defaults),
    avatar?, approved_resource_policy_from_manifest_and_local_policy?,
    presentation?, descriptor.privacy_model,
    mutually_supported_retention_and_limits, created_at=Clock.now(), bounded_expiry,
    extensions=exact negotiated extension selection)
  require requested hard constraints satisfied else negotiation_failed
  return freeze(scope)
```

## 4. 两个入口、批准与启动

```text
function create_offer(caller_proof, entry, candidate, requested, nonce):
  actor = authenticate(caller_proof, access_authority, request_join, trust)
  if entry == companion:
    require actor == requested.agent
  else if entry == game:
    require actor == requested.player or verified_player_delegate(actor)
    // GameAuthority 单凭管理员身份不能伪造玩家的选择
  else reject invalid_message
  scope = negotiate(candidate, verified_player, verified_agent, requested, support)
  atomic(actor, nonce):
    return_same_or_conflict(offer_nonce_key(actor, entry, nonce), digest(requested))
    offer = new pending Offer(freeze(scope), digest(scope), bounded_deadline,
      launch_required = verified_local_companion_not_running)
    persist offer and nonce receipt
    return offer_without_secrets

function decide(player_proof, offer_id, digest_seen, allow, remember, launch_permission):
  player = authenticate(player_proof, access_authority, consent, trust)
  atomic(offer_id):
    offer = require_owned_offer(player, offer_id)
    if offer.state == denied and allow == false: return denied
    require offer.state == pending else return idempotent_prior_or_conflict
    evidence = Consent.verify_decision(player, offer_id, digest_seen, allow,
      remember, launch_permission)
    if not allow:
      offer.state = denied; emit offer.denied; return denied
    require Clock.now() < offer.decision_deadline else offer_expired
    require digest_seen == offer.scope_digest else approval_stale
    assert_current_scope(offer.scope)
    grant = new active Grant(offer.scope, evidence, revision=1)
    offer.state = approved; offer.grant_id = grant.id
    if remember:
      save revocable auto_rule(player, rule_scope_key(grant.scope),
        explicit_rule_expiry, maximum_grant_duration, original_consent_evidence)
    save launch_permission separately; it is not implied by remember
    commit grant + offer + receipt + outbox
    return approved  // 不包含伙伴邀请或管理员令牌

function attempt_automatic(offer):
  atomic(offer.id, auto_rule_owner):
    rule = find_active_exact_rule(rule_scope_key(offer.scope), player, agent, instance)
    if not rule or offer.launch_required: return needs_explicit_consent
    assert_current_scope(offer.scope)
    require rule permits offer.scope.expires_at and duration else needs_explicit_consent
    // 不在批准后偷偷缩短/改写 offer；创建 offer 时即可按 rule 上限协商到期
    grant = create_grant_from_prior_consent(rule, offer.scope)
    offer.state = approved; offer.grant_id = grant.id
    commit and return approved

function ensure_companion_available(offer):
  if companion_is_verified_cloud:
    delegation = Provider.complete(server_stored_transaction, verified_callback)
    require delegation.player/agent/audience match offer.scope else unauthenticated
    return authenticated_companion_channel
  if companion_verified_running: return authenticated_companion_channel
  permit = require_unused_valid_launch_permission(offer, player, application)
  process = Launcher.start(fixed_application_registration, permit)
  if process failed:
    record launch_failed; revoke unused offer grant; return launch_failed
  return bind_process_to_expected_identity(process, offer.scope.agent)
```

提供者回调事务应在创建最终 offer 前完成身份解析；如果用户取消委托，不生成可批准 offer。`ensure_companion_available` 的 Provider.complete 只允许确认/幂等读取同一既有委托，不在批准后替换伙伴身份。桌面伙伴与云端伙伴共用后续邀请流程。

上述 `ensure_companion_available` 是业务决策概要，不能把 Launcher.start 包进可回滚的
authority 事务。`launch.request` 必须进一步拆成：精确批准/登记绑定与原请求去重 → 原子
消费许可并记接受 → 以当前可信时间重新核权并提交派发标记 → 独立 Launcher 消费/效果
账本 → 结果与失败撤权事务。已标派发而无端口证据时不补启动，保持 pending/unknown；
有证据时查询原许可，不以再次执行探测结果。成功事实不直接交付会话秘密。

本地可执行展开、故障点及限制见 [本地启动验证](LAUNCH_PROOF.md)。其 Consent 假端口
额外绑定用户所见的完整应用登记，邀请还验证 fresh 原伙伴及登记设备；不能只凭历史
进程记录进入 ready。生产适配器仍须兑现进程身份与受控凭据管道，不由内存夹具代证。

## 5. 邀请领取与加入

```text
function redeem(agent_proof, offer_id, join_intent):
  agent = authenticate(agent_proof, access_authority, redeem_own, trust)
  atomic(offer_id, grant_id):
    offer = require_offer_for_agent(offer_id, agent)
    require offer.state == approved else consent_required
    grant = grants[offer.grant_id]; assert_grant(grant)
    require Clock.now() < offer.decision_deadline else offer_expired
    require join_intent.scope_digest == offer.scope_digest else approval_stale
    validate_device_observation_if_present(join_intent, offer.scope)
    if offer.invitation_id exists:
      prior = invitations[offer.invitation_id]
      require prior.join_intent_digest == digest(join_intent) else redemption_conflict
      require prior.state != revoked and prior.expires_at > now else invitation_expired
      return same_invitation_secret_for_same_authenticated_agent(prior)
    invite = Invitation(grant.id, grant.revision, digest(join_intent), agent,
      offer.scope.player, offer.scope.instance,
      min(grant.expires_at, offer.decision_deadline, now + configured_invitation_ttl))
    store invite + encrypted_redeem_response + offer.invitation_id
    return invite_credential + join_intent  // 只给对应伙伴的安全通道

function join(agent_proof, invitation_secret, join_intent):
  agent = authenticate(agent_proof, instance, join, trust)
  invitation = Secrets.verify(invitation_secret, agent, instance, invitation_role)
  atomic(invitation.id, grant.id, agent_session_scope):
    require invitation belongs to authenticated agent/player/instance
    if invitation.state == consumed:
      require invitation.consumed_intent_digest == digest(join_intent) else invitation_used
      session = sessions[invitation.consumed_session_id]
      close_expired_before_read(session)
      require session.state == active else session_closed
      if not session.admission_ready: return join_pending(session.id)
      if session.control_generation != invitation.original_generation:
        return already_joined(session.id)  // 不返回轮换/转移后的新凭据
      require verified_device == session.controller_device when device is applicable
      return current_snapshot(session) + stored_original_join_secrets(invitation)
      // 不延长租约、不建第二 session，不返回新 generation 凭据
    require invitation.state == issued and Clock.now() < invitation.expires_at
    grant = grants[invitation.grant_id]; assert_grant(grant)
    require grant.revision == invitation.grant_revision
    require digest(join_intent) == invitation.join_intent_digest
    if multi-session not negotiated:
      close_expired_sessions_for_agent()
      require no conflicting active session else session_conflict
    session = create_active_session(grant.scope, epoch, generation=1, bounded_lease,
      admission_ready = false)
    create_write_credential(session, role=companion_control)
    create_result_read_handle(session, role=results_only)
    invitation.state = consumed
    invitation.consumed_session_id = session.id
    invitation.consumed_intent_digest = digest(join_intent)
    invitation.original_generation = 1
    store_original_join_secrets_transactionally(invitation, control_credential,
      result_read_handle)  // 加密/受控 secret store，未 ready 时不可读取给调用方
    commit session + invitation + credentials + joined_receipt + outbox
  return finish_admission(session.id)
  // 见资源/呈现伪代码；无可选资源也通过同一 ready 提交，不复制另一条加入路径
```

并发 join、资源准备与呈现占用统一使用 [Admission saga](PRESENTATION_AND_ASSETS.pseudo.md)。会话创建后直到准备成功，数据面必须阻止动作/伙伴发言，使用 `admission_ready=false` 内部标志，不新增公共 active 子状态。成功 CAS 为 true；失败或超时关闭。幂等 join 在未就绪时返回 `join_pending`，不能提前交付可用控制凭据；内部创建的凭据只在就绪后返回。重复 join 可唤醒同一 admission worker，不能创建另一个准备事务。

## 6. 续租、关闭与撤销

```text
function heartbeat(control_proof, session_id, fresh_nonce):
  principal = authenticate_control(control_proof, session_id)
  atomic(session_id, principal, fresh_nonce):
    session = sessions[session_id]; close_expired_before_read(session)
    require session.active and session.admission_ready
    require token.transport_epoch == current_transport_epoch
    require token.generation == session.control_generation
    require grant still active  // 不要求世界 description 永远不变；动态变更走数据面
    if nonce already processed: return original_heartbeat_without_extending
    session.lease_deadline = min(now + agreed_lease, grant.expires_at)
    save heartbeat receipt and snapshot
    outbox presentation_lease_update(session, deadline)
    return snapshot

function close_in_transaction(session, reason):
  if session.closed: return existing_close_receipt
  session.state = closed; session.close_reason = reason
  session.admission_ready = false
  revoke companion write credentials; keep bounded result read permissions
  for action in session.actions:
    if action.pending: set cancelled, effect=none
    if action.executing: set unknown, effect=undetermined, forbid future effects
  finalize_result_read_until(session, now + agreed_result_retention)
  append session.closed event
  outbox Presentation.release for all recorded occupations/generations of this session
  return closed_receipt

function revoke(caller, object_type, object_id):
  authenticate and verify caller owns revocation authority for exact object
  atomic(affected_scope):
    if auto_rule: mark revoked; no implicit session close
    if invitation: mark unconsumed invitation revoked; report consumed if already joined
    if grant:
      mark revoked; revision++
      revoke all unused linked invitations
      for active linked session: close_in_transaction(session, revoked)
    if session: close_in_transaction(session, revoked)
    if capability: apply capability revision and fence pending/executing effects
    if relay: revoke outer relay credentials, stop delivery; no invented world rollback
    append revocation audit without secrets
```

## 7. 持久恢复与控制权转移

```text
function resume(new_identity_proof, session_id, expected_generation, device):
  agent = Identity.verify(new_identity_proof, instance, negotiated_profile)
  atomic(session_id, agent):
    require durable_ledger_healthy else resume_denied
    session = authorized_session_lookup(agent, session_id)
    require resume negotiated and session.active and now < session.resume_until
    require now < session.lease_deadline and grant active else resume_denied
    require session.control_generation == expected_generation else generation_conflict
    require device == session.controller_device else handoff_required
    restore_required_receipts_actions_membership_and_scope_or_fail()
    validate_recovery_contract(session, current_descriptor)
    session.control_generation++
    session.transport_epoch = current_transport_epoch
    revoke old write credentials
    fence old-generation actions: pending -> cancelled/none,
      executing -> unknown/undetermined with no new effect permission
    new_secret = issue control credential(session, session.control_generation)
    do not change action IDs or replay pending effects
    if presentation negotiated:
      session.admission_ready = false
      create same-device rebind using new generation,
        release old occupation then acquire new under existing approved terms
      persist new_secret but do not deliver before rebind ready
  if presentation negotiated: return finish_same_device_rebind_or_close(session)
  return new_secret + current_snapshot + event_high_watermark + unresolved_action_refs

function handoff(player_decision, new_identity_proof, session_id,
                 target_device, expected_generation):
  return begin_handoff(player_decision, verified_target(new_identity_proof,target_device),
    session_id, expected_generation)
  // 唯一算法见 PRESENTATION_AND_ASSETS；不并行交付两个控制者的写权

function claim_control(fresh_agent_proof, verified_device, session_id, transfer_id):
  // session.claim_control 的控制回执包装适用；此函数绝不再次升代
  agent = Identity.verify(fresh_agent_proof, instance, negotiated_profile)
  atomic(session_id, transfer_id):
    t = lookup_transfer_for_verified_agent(agent, transfer_id)
    require t.session_id == session_id and agent == session.scope.agent
    require verified_device == t.target_device else permission_denied
    require t.status == ready and session.active and session.admission_ready
    require session.control_generation == t.new_generation and grant still active
    require now < session.lease_deadline and now < grant.expires_at
    return stored_target_control_delivery_for_exact_generation(t)
    // PlayerConsent 的 operation.get 不返回此秘密；关闭/后续升代后不回放
```

## 8. 组合验证入口

接入/设备状态算法见 [资源与呈现](PRESENTATION_AND_ASSETS.pseudo.md)，动作、结果查询和动态 revision 算法见 [数据面](DATA_PLANE.pseudo.md)。组合复核结果见 [推演记录](WALKTHROUGH_RESULTS.md)，其中单独标明模型未覆盖的异步窗口及其符号推演。真实安全适配器和生产代码不在本次可运行要求内。
