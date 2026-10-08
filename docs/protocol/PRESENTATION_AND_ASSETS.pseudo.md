# 接入提交、形象资源、呈现与设备转移伪代码

依据：[协议总设计](PROTOCOL.md)、[控制面](CONTROL_PLANE.pseudo.md)、[数据面](DATA_PLANE.pseudo.md)。本文件处理“会话已创建但尚未允许交互”的中间窗口，不把跨设备副作用伪装成数据库原子事务。

当前固定假设备和资源的字节装配分别见 [呈现证明](PRESENTATION_PROOF.md) 和
[资源准备证明](ASSET_PROOF.md)。租约 revision、设备自身重启和有界补偿批次见
[设备生命周期证明](DEVICE_LIFECYCLE_PROOF.md)；更多资源格式/preinstalled、长期回收和真实后台服务另验。

## 1. 必要端口与记录

```text
DeviceState = {verified_device, device_epoch, baseline_visible, manual_revision,
  occupations: map[(session_id, generation) -> Occupation],
  release_tombstones, last_authority_epoch}
Occupation = {terms, expires_at, scope_digest, device_epoch, lease_revision, apply_receipt, active}
Admission = {session_id, generation, operation_id, status: pending|ready|failed,
  deadline, resource_receipts[], presentation_receipt?, failure_reason?}
Transfer = {transfer_id, session_id, old_device, target_device,
  old_generation, new_generation, scope_digest,
  status: releasing|acquiring|ready|failed, deadline,
  old_release_ack?, target_acquire_ack?}
ResourceManifest = {asset_id, content_digest, byte_size, media_type, format_version,
  compatibility, dependency_manifests[], locator?, approved_origins[], license_claim,
  issuer, sandbox_requirements}
```

端口契约：Device.verify 验证设备与玩家绑定，不能只接受 device_id；Renderer.apply 只改变本设备呈现、回报实际状态或失败，不控制游戏世界；ResourceTransport 逐跳验证 HTTPS/origin/DNS/连接目标，按字节上限流式下载；Archive.inspect 禁止路径逃逸、符号链接逃逸与解压炸弹；Parser.open 在受限环境仅解析已支持格式，默认不运行嵌入脚本；Cache 按内容摘要隔离，只有 verified 状态可见。

这些端口允许假实现，但必须可返回拒绝/损坏/超限/超时，且伪数据明确标为 fixture，不得把“存在 model 字段”当真实加载完成。

## 2. 形象选择与资源闭包

```text
function select_avatar_if_negotiated(features, requested, descriptor):
  if avatar not in features:
    require avatar not in descriptor.required_features else feature_unsupported
    return absent
  selected = first_present(requested.forced_avatar,
    descriptor.game_avatar, requested.default_avatar)
  require selected exists else avatar_required
  require compatible(selected.type, format_version, skeleton/animation_contract,
    descriptor.accepted_avatar_contracts) else avatar_incompatible
  // 不在不兼容时自动尝试第二候选；用户改选后重新协商
  if selected is verified preinstalled reference:
    require descriptor renderer resolves exact content ID and compatible revision
  else:
    require assets negotiated else feature_unsupported
    validate_manifest_shape_and_dependency_limits(selected.manifest)
  return frozen selected

function prepare_resources(selected_avatar, approved_scope):
  if absent: return no_resource_required
  if preinstalled: return Renderer.verify_existing(selected_avatar.exact_id)
  manifests = walk_dependency_graph_with_cycle_detection(selected_avatar.manifest)
  require unique content IDs and depth/count/total_declared_size within approved limits
  receipts = []
  for manifest in topological_order(manifests):
    require manifest.digest algorithm in local_allowlist and size finite
    require manifest.issuer/license_claim present
    require user's/game's local rights policy accepts claim else resource_policy_denied
    // 不是对第三方许可真实性的法律保证
    if Cache.has_verified(manifest.digest, parser_version, policy_version):
      receipts += cache receipt; continue
    stream = ResourceTransport.open(manifest.locator, approved_scope.resource_policy.approved_origins,
      no_session_secrets=true, no_cross_origin_credentials=true)
    for every redirect and connection:
      enforce TLS identity and approved origin
      resolve then pin/verify actual target against SSRF network policy
      reject loopback/private/link-local/metadata addresses unless explicitly approved
    bytes = bounded_read(stream, manifest.byte_size, negotiated_total_remaining)
    require exact size and digest match else resource_integrity_error
    Archive.inspect(bytes, no_path_escape, no_active_scripts, bounded_unpacked_size)
    parsed = Parser.open(bytes, manifest.media_type, manifest.format_version,
      isolated=true, capabilities=none)
    require parsed.compatibility matches approved avatar and dependencies
    Cache.publish_verified_atomically(digest, parsed, validation_receipt)
    receipts += validation_receipt
  return receipts
```

下载失败不改变 scope/action 权限，不自动回退形象。资源 URL 不是身份，也不能附带 G2A 会话令牌。允许某一个 origin 不允许它自动给出任意依赖 origin；追加来源需要新批准。资源获取完成后尚需 Renderer 验证，解析成功不保证当前设备能渲染。

完整 Manifest 与冻结批准的匹配、同一 asset_id 的重复声明、解析后的 compatibility 及
冻结 ResourcePolicy 的重验采用 `g2a-cjson-1` 规范字节等价。不得使用会将 `true` 与 `1`、
`false` 与 `0` 合并的宿主语言相等性；对象键的排列顺序仍不影响等价性。

## 3. 呈现占用与最新用户意图

```text
function recompute_visible(device):
  remove locally expired occupations without reactivating credentials
  active = occupations with verified current generation and unexpired lease
  if any active.terms == hide_desktop: return false
  return device.baseline_visible

function acquire(authority_proof, device_proof, session_id, generation,
                 terms, deadline, scope_digest, operation_id):
  verify authority and device owner; require approved scope binds this device/terms
  atomic_local(device):
    key = (session_id, generation)
    if key in release_tombstones: return occupation_released  // 迟到 acquire 不复活
    if key exists:
      require operation/scope/terms digest matches original else id_conflict
      return original apply receipt  // 不凭重试延长租约
    require now < deadline and authority admission/transfer proof still valid
    occupations[key] = Occupation(terms, min(deadline, local_max_lease), scope_digest)
    desired = recompute_visible(device)
    result = Renderer.apply(desired, expected_manual_revision=device.manual_revision)
    if failure:
      remove this tentative occupation; return presentation_unavailable
    persist occupation + apply_receipt + effective_state
    return apply_receipt(key, operation_id, manual_revision, actual_state)

function release(authority_or_local_expiry, session_id, generation, operation_id):
  verify own session generation or local lease expiry
  atomic_local(device):
    release_tombstones[(session_id,generation)] = bounded_retained_marker
    remove only occupations[(session_id,generation)] if exists
    desired = recompute_visible(device)
    apply desired with latest manual_revision; record renderer failure if any
    return release_receipt including actual visible and retained_revision

function manual_change(player_device_proof, desired_visible):
  verify player controls device
  atomic_local(device):
    baseline_visible = desired_visible; manual_revision++
    conflicts = hide occupations if desired_visible == true else []
    for occupation in conflicts:
      mark released and tombstone immediately
      enqueue close_session(occupation.session_id, presentation_terms_rejected)
    Renderer.apply(recompute_visible(device), expected_manual_revision)
  // 用户本地显示意图立即生效；远端可能到达前仍认为会话 active，按租约/通知收敛
  // 不宣称跨网络瞬时原子地终止游戏；伙伴端必须立刻停止冲突会话的交互

function renew(authority_lease_proof, operation_id):
  require local PresentationAuthority, current Scope/generation/device_epoch
  require exact issued proof and current game lease; device occupation still live
  atomic_local(device):
    if exact original receipt exists: return historical receipt without extending
    reject tombstone or revision <= applied_revision or revision != latest_issued_revision
    require unchanged terms/scope and old_deadline < new_deadline <= game_lease_deadline
    persist revision + deadline + receipt without Renderer call
  authority records ACK separately; failed ACK commit cannot undo device lease

function device_restart(persisted_device_state):
  load latest baseline/manual_revision/occupations/tombstones
  increment device_epoch; retire old device object
  keep only occupations whose authority/generation/lease can be freshly verified
  unresolved occupation is released, not trusted by saved token alone
  Renderer.apply(recompute_visible(device))
  record fresh current-epoch evidence separately from any missing original operation ACK

function bounded_compensation_tick(now, budget):
  prioritize releases, rotate among jobs, respect retry_at and finite budget
  unknown ACK: retry original operation ID, do not invent a new effect
  known failed release: a later explicit attempt may use a new ID
  release receipt capacity exhausted: trusted local stop reconciliation remains available
  local reconciliation never overwrites original receipts; fresh evidence commits after device effect
  no reachable device evidence or verified local expiry: keep pending
  closing/superseding an outbox intent does not prove its original device effect failed
```

Renderer 如果失败，记录实际状态并停止相关会话，不声称已恢复窗口。多设备不共享一个全局 bool；相同伙伴在不同设备的 baseline 各自独立。只有已批准的 PresentationOwner 可操作该设备。

release tombstone 至少保留到该 generation 所有 admission/lease 证明过期；删除后过期证明也必须被拒绝，因此不会无限增长却又允许迟到 acquire 复活。租约更新使用单调 authority revision，旧更新不延长新 lease，也不消除 tombstone。

## 4. Admission saga：先准备，再开放数据面

创建 Session 后统一进入内部 `admission_ready=false`。没有形象/呈现时也经过这个函数，只是准备阶段为空；准备成功前不交出可用写凭据。邀请状态和 Session 创建在一个事务中，之后以 durable operation_id 执行可重试准备。

```text
function finish_admission(session_id):
  admission = load_or_create_single_admission(session_id)
  if admission.ready: return original_join_response_if_current_generation()
  if admission.failed: return session_closed(admission.failure_reason)
  if not still_authorized(session_id) or now >= admission.deadline:
    return fail_admission(session_id, expired_or_revoked)
  receipts = prepare_resources(session.scope.avatar_selection, session.scope)
  if receipts failed: return fail_admission(session_id, resource_failure)
  if presentation negotiated:
    occupation = acquire(authority, device, session.id, session.control_generation,
      approved_terms, min(admission.deadline, lease_deadline), scope_digest,
      admission.operation_id)
    if occupation failed: return fail_admission(session_id, presentation_failure)
  atomic(instance_authority, session_id):
    if grant revoked/session closed/deadline reached/generation changed:
      commit fail_admission_in_tx + outbox release_generation
      return admission_failed
    store verified resource/presentation receipts
    admission.status = ready; session.admission_ready = true
    extend occupation only with valid current lease revision
    append session.ready event and join_ready_receipt
  return stored_original_join_secrets + current_snapshot

function fail_admission(session_id, reason):
  atomic(instance_authority, session_id):
    admission.status = failed; failure_reason = reason
    close_in_transaction(session, reason)
    outbox release(session_id, admission.generation) even if acquire outcome unknown
  return reason

function sweep_admissions():
  for pending admission:
    if expired or no longer authorized: fail_admission()
    else finish_admission()  // 幂等准备，不创建新 Session/邀请/动作
  outbox retry release only until receipt or device lease expiry proves nonoccupation
```

关键崩溃窗口：

| 中断位置 | 恢复动作 | 禁止发生 |
| --- | --- | --- |
| Session 创建前 | 相同邀请重试 join | 产生半个有效 Session |
| 已消费邀请，准备未开始 | 返回 join_pending；恢复同 admission | 再消费一次邀请或创建第二 Session |
| 设备已隐藏，服务器未记录 receipt | 重试相同 acquire；若撤销则 release+tombstone/本地租约 | 凭“没收到 ACK”认定窗口未改变 |
| ready 提交前撤权 | 提交失败/闭会，释放占用 | 发送写凭据后才补查 grant |
| ready 已提交，join 回包丢失 | 同身份、同 generation 返回原 secrets 与当前 snapshot | 续租、重复占用或返回 handoff 后新代凭据 |
| 控制端重启且账本丢失 | 不支持 resume 时作废 epoch，设备租约收敛 | 从窗口隐藏状态推断会话仍有效 |

## 5. Handoff saga：不重叠授予两个写控制者

```text
function begin_handoff(player_proof, target_proof, session_id, expected_generation):
  verify explicit decision binds target device/session/scope/current generation
  require handoff/resume negotiated and target presentation capabilities compatible
  atomic(instance_authority, session_id):
    require session.active and session.admission_ready and intact durable ledger
    require session.control_generation == expected_generation
    require no transfer pending else transfer_in_progress
    session.admission_ready = false
    session.control_generation++
    revoke old write credentials
    fence all old-generation pending/executing actions against new effects
    transfer = persist Transfer(old_device,target_device,old_generation,new_generation,
      status=releasing,deadline=min(now+transfer_timeout,lease_deadline,grant_expiry))
    outbox release(old_device, session_id, old_generation)
    create target credential but do not deliver until transfer.ready
  return transfer_pending

function advance_transfer(transfer_id):
  t = load transfer; require not failed/expired/closed else fail_transfer
  if t.status == releasing:
    if verified old_release_ack or authoritative old_occupation_lease_expired:
      CAS releasing -> acquiring
    else return pending  // 不凭网络超时猜旧设备已经释放
  resource_receipts = prepare_resources_for_target_if_needed()
  if failure: return fail_transfer(resource_failure)
  if presentation negotiated:
    ack = acquire(target, session_id, new_generation, terms, transfer.deadline,
      scope_digest, operation_id=transfer_id)
    if failure: return fail_transfer(presentation_failure)
  atomic(instance_authority, session_id):
    require grant/session/deadline/generation still valid else fail_transfer_in_tx
    session.controller_device = target_device
    session.admission_ready = true; t.status = ready
    store target acknowledgement and immutable handoff response
  return target-only credential + unchanged action ledger + current snapshot

function fail_transfer(reason):
  atomic(instance_authority, session_id):
    mark transfer.failed; close_in_transaction(session, reason)
    outbox release old_generation and new_generation occupations
  // 不恢复旧写凭据或旧 generation；用户可重新授权新会话
```

handoff 暂停期间单独的已认证控制事务可观察 transfer 状态，但不会无限续租；若等旧占用过期时已超过 session lease，则失败闭会。没有 presentation 能力时旧呈现释放阶段为空，但依然撤旧写凭据、提升 generation，再交付新写权。正常同设备 resume 不执行 handoff；其旧执行 ticket 只能报告原事实，不能因 resume 继续产生新效果。

同设备 resume 的 `finish_same_device_rebind_or_close` 复用 advance_transfer 的释放→获取→ready 阶段，source/target 是同一已验证设备，授权条款不变，operation_id 单独记录为 resume ID；它不是新的设备迁移，不要求新的跨设备许可。网络回包丢失则查询相同 operation，不再增加 generation；任一阶段到期/失败就闭会。这里复用阶段算法，不再次调用 begin_handoff 或递增 generation。

## 6. 本轮验证边界

已给出资源、呈现、接入提交和转移的算法及关键崩溃分支，并按 [推演记录](WALKTHROUGH_RESULTS.md) M01/M02/M05 核对。不会据此宣称任意资源格式安全、所有设备实际可渲染或真实网络恢复已验证。
