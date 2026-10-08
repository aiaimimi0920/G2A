# 传输绑定、控制请求幂等与出站 Relay

本文件实现 [总设计](PROTOCOL.md) 的抽象操作到边界接口的映射。所有代码为协议伪代码：真正 HTTPS、OS IPC、身份签名验证由已声明端口承担；角色、受众、幂等和未知结果处理不能被端口跳过。

## 1. 操作封装与入口分区

```text
OperationRequest = {version, operation, request_id, payload, extensions}
OperationReply = {request_id, result | error}
RouteContext = {verified_transport_peer, auth_proof, endpoint_audience,
  arrival_time, body_size, direct_or_relay}
OperationReceipt = {principal, operation, request_id, input_digest,
  state: pending|done|failed, outcome_ref, secret_ref?, original_generation?, expiry}
```

`request_id` 为调用方选择的稳定随机 ID，重试必须保持 operation/payload 不变。HTTP 头承载认证，不能把 token 放进 URL 或日志；绑定附带的 inner proof 作为秘密处理，不参与业务请求内容摘要，但验证出的主体必须与去重记录一致。每个操作仍独立执行字段校验，不能因绑定解析成功而直接执行。

公开 `GET /.well-known/g2a.json` 只返回最小候选描述及支持版本，不含玩家/队伍/邮箱/许可。完整描述和所有操作走已验证端点 `POST /g2a/operations`；普通游戏管理、执行器接口和本机 Launcher 不在这个公网入口。

| 入口/角色 | 允许操作 | 输入校验重点 |
| --- | --- | --- |
| 认证伙伴控制面 | describe、offer.create/get、invitation.redeem、session.join、session.resume、session.claim_control、operation.get | 主体必须是 scope.agent；玩家归属通过认证委托，不能自报 |
| 认证玩家控制面 | offer.create/get/decide、permission.revoke、session.handoff、action.confirm、operation.get | 玩家只能处理其授权范围；审批证据绑定完整 scope |
| 独立数据主体隐私面 | privacy.request、privacy.receipt | data_subject/privacy；每条来源的主体权与实际数据控制者 audience，不借游戏 Grant |
| 会话伙伴数据面 | heartbeat、snapshot、events、chat.send、action.request/cancel | session、当前 generation、租约、ready、能力与受众 |
| 结果读取 | action.query | 原主体、session/action 读取范围、保留期、撤销 revision；不授写权 |
| 关闭 | session.close | 当前伙伴或原玩家/游戏控制权；闭会后允许同已认证控制面读取关闭回执，不恢复写权限 |
| 游戏受控管理面 | context.publish、player_chat.forward、capability.replace、membership.replace、action.claim/commit_result | GameAuthority/执行器证明、玩家席位映射；不从 Relay 外部伙伴入口调用 |
| 本地受控界面 | launch.request、presentation.acquire/renew/release、单次行动确认 | 本地应用/设备身份，可信玩家交互；不接受网页传入执行路径 |

操作不存在于允许目录即拒绝，未协商 capability 的操作拒绝。`operation.get` 只读本人控制请求的进度；不是任意服务器对象查询。snapshot/events 可由游戏另有管理读通道读取，不用伙伴凭据，更不能替伙伴续租。

privacy.request/receipt 发给实际数据控制者（游戏或伙伴存储方）的已验证 privacy endpoint，不把游戏 endpoint 当作能删除所有提供者数据的中心。请求凭据 audience 必须是该数据控制者；本版 Relay 内层不开放 privacy lane，也不接受任意 origin 作为隐私转发目标。另一数据控制者需要独立已验证隐私连接和主体授权映射。

## 2. 严格解析和错误映射

```text
function receive_http(request, endpoint):
  enforce_tls_or_explicit_test_loopback(request, endpoint)
  enforce_content_length_and_absolute_body_limit_before_allocation()
  reject duplicate JSON keys, NaN/Infinity, excessive depth/arrays/strings
  reject unsupported content encoding, conflicting framing, ambiguous auth headers
  require Content-Type application/json; decode UTF-8 strictly
  op = validate_operation_envelope(request.body)
  require op.version in endpoint.exact_supported_versions
  principal = authenticate_for_route(request.auth, endpoint.audience, op.operation)
  authorize_operation_class(principal, op.operation)
  validate_exact_payload_shape(op.operation, op.payload)
  check_feature_and_request_limits(principal, op)
  result = dispatch_to_unique_semantic_handler(principal, op)
  return JSON reply with Cache-Control:no-store and no secrets in default logs

function reply_error(error):
  map authentication -> 401; authorization -> 403
  map invalid structure -> 400; unsupported content -> 415; oversized -> 413
  map version/state/id/revision conflicts -> 409
  map rate/resource limit -> 429; unavailable -> 503; transport deadline -> 504
  always include semantic code/category/retry/outcome
  do not translate 504 into action failed
```

框架不得从 Exception 文本拼接秘密或内部栈回给伙伴。可以用相关 request_id 关联本地受限审计，不记录 Authorization 和记忆全文。核心纯文本不能作为 HTML 执行；默认 JSON `$ref` 解析只能使用本地受信 schema 注册表，不访问请求携带的 URL/文件。

## 3. 控制请求幂等、长操作与秘密回放

所有会改变控制状态的操作均使用同一 OperationReceipt 规则，包括批准、撤销、resume 和 handoff。不能只对 action.request 去重。控制回执保留至少覆盖该操作的有效期和可恢复窗口；过期 ID 留拒绝重用 tombstone，或以作用域 epoch 作废，不能接受为新决定。

```text
function control_mutation(principal, op):
  key = (principal, endpoint_audience, op.operation, op.request_id)
  digest = canonical_digest(op.version, op.operation, op.payload, op.extensions)
  atomic(authority_scope, key):
    if receipt exists:
      require receipt.input_digest == digest else id_conflict
      require principal still entitled to observe outcome_ref
      return protected_receipt_view(receipt, principal)
    if expired tombstone exists: reject request_expired
    require fresh operation-specific preconditions
    reserve receipt and transition/saga in same transaction
    receipt = pending if external work remains else done
    persist input digest, outcome ref and all semantic state changes
  drive_same_saga_if_needed()
  return protected_receipt_view(receipt, principal)

function protected_receipt_view(receipt, principal):
  if no secret: return bounded current outcome view
  require principal == secret.intended_recipient
  require secret audience/session/device still matches
  if original_generation != session.control_generation or secret revoked:
    return completed_without_secret(outcome_ref, reauth_required=true)
  if admission/transfer/rebind not ready: return pending(outcome_ref)
  return original_secret_from_secure_store + current_snapshot
```

例如 resume 已提升 g1→g2 但回包丢失：同主体、同 request_id、同 expected_generation=g1 的重试首先匹配已提交控制回执，返回原 g2 结果，不再次提升 generation，也不错误返回 generation_conflict。换 request_id 仍带 g1 则冲突。若随后已 handoff 到 g3，旧 resume 回执不能再泄露当前写凭据。

handoff 的发起玩家可以读取 transfer 状态，但目标写凭据只能由目标 Agent+已验证设备赎领。玩家界面不直接取得伙伴写 token。闭会后的结果句柄同样按独立读取范围回放，不能从普通状态响应暴露秘密。

数据消息使用 DATA_PLANE 中会话级 Receipt；绑定 request_id 只用于传输关联，不能替换 Envelope.id。若两个传输请求封装同一个业务消息，仍只接受一次业务消息。操作去重不能在身份验证之前执行，否则会成为结果枚举入口。

## 4. Relay 配对与可信范围

本版 Relay 是用户已批准的可信终点，会看到转发消息和内层凭据；它不是 E2EE 中继。选择 Relay 必须在 Scope 里固定 operator identity、origin 和隐私条款。两个程序能出站连接不等于已完成用户授权。

```text
Mailbox = {mailbox_id, instance, relay_origin, relay_identity, route_revision,
  allowed_control_principals[], allowed_agent_principals[], state:open|closed,
  registration_expiry, game_pull_credential, agent_submit_credential,
  controller_submit_credential, limits, requests, receipts}
RelayCall = {relay_request_id, operation_request, inner_auth_proof,
  deadline, route_revision}
RelayRecord = {caller_principal, input_digest, operation_class,
  state:queued|claimed|replied|expired|closed, claim_id?, claim_game_identity?,
  response?, known_dispatch:never_sent|claimed, deadline}
```

配对由控制面完成：验证 GameAuthority 对 instance 的控制权、用户选择的 Relay，以及玩家/Agent 归属；分别发放游戏领取、伙伴提交和玩家控制提交凭据，权限不互换。邮箱 ID 不当凭据。玩家控制通道可转发经验证的 offer.decide 等必要操作到只出站的游戏，但伙伴提交凭据绝不能调用它；游戏仍验证内层玩家审批证据。Relay 不自行替用户批准。

```text
function register_mailbox(control_proof, verified_pairing, nonce):
  verify control proof owns instance and permits approved relay origin/operator
  verify pairing participants and expiry; reject untrusted arbitrary target URL
  atomically dedup nonce, create open mailbox and separate outer credentials
  bind route to fixed instance handler; no arbitrary URL forwarding
  return each credential only through its intended authenticated recipient channel

function relay_call(outer_proof, mailbox_id, call):
  outer = verify_submit_role(outer_proof, mailbox_id)
  require outer principal registered for exact agent/control lane
  require call.operation belongs to this lane and never game_management/launcher
  inner = independently_verify_inner_proof_for_fixed_game_audience(call.inner_auth_proof)
  require inner principal == outer principal and allowed inner role for outer lane
  validate complete inner request, including conditional fields and exact version
  key = (mailbox_id, outer.principal, call.relay_request_id)
  digest = canonical_digest(complete_inner_request, outer_extensions)
  atomic(mailbox_id, key):
    if prior:
      require digest == prior.digest and inner.role == prior.inner_role else id_conflict
      require call.route_revision == prior.original_route_revision
      if expired/closed: return actual_dispatch_knowledge_without_secrets()
      require active mailbox submit capability
      return protected prior reply or bounded current state, without extending deadline
    require active mailbox submit capability and mailbox.open
    require call.route_revision == mailbox.route_revision
    require capacity available else resource_limit(outcome=not_accepted)
    require single claim and reply envelope fit negotiated byte limit
    enqueue RelayRecord(queued, known_dispatch=never_sent,
      frozen_inner_proof=call.inner_auth_proof,
      deadline=min(call.deadline, now+mailbox.maximum_wait, registration_expiry, inner.expiry))
  wait until replied/deadline/closed without unbounded thread allocation
  if replied: return exact semantic reply after envelope validation
  return timeout_or_closed_with_actual_dispatch_knowledge()

function game_pull(game_outer_proof, mailbox_id, pull_nonce):
  verify registered game identity and pull-only role
  atomic(mailbox_id):
    require mailbox.open; expire queued past deadline
    if same pull_nonce already processed:
      require unchanged payload and no expired/closed claim in original batch
      return same bounded claim response, including original empty batch
    choose per-principal FIFO queued requests with round-robin fairness
    stop at both maximum_items and encoded response byte limit
    mark each claimed, assign one claim_id and exact game_identity
    persist claim response and receipts before returning
    return claims  // 不把 claimed 记录重新入队给其他 worker

function game_dispatch_claim(game_identity, claim):
  verify fixed mailbox/instance/route revision and claim proof
  check deadline before dispatch; reject if already too late
  authenticate inner principal with intended game endpoint audience
  authorize operation against inner role and current state
  dispatch through same semantic handlers as direct binding
  // Relay 领取并不保证业务已接受；管理操作必须在这里再次拒绝
  persist/retrieve semantic receipt; submit_reply_using_game_outer_role()

function relay_reply(game_outer_proof, mailbox_id, claim_id, reply):
  verify pull/reply-only credential for exact mailbox game
  atomic(mailbox_id):
    record = require_claim_owned_by_game(claim_id)
    require response.request_id == original.operation_request.request_id
    validate original output/error schema; enforce inner and wrapped response size
    if record.expired or mailbox.closed or now >= record.deadline: return request_gone
    if record.replied:
      require digest(reply)==digest(record.response) else reply_conflict
      return original acknowledgement
    record.state=replied; store frozen response; wake original waiter
    return accepted
```

当 Relay 认为请求从未出队且已原子作废，错误可声明 not_accepted_by_relay；仍不能用它覆盖其他路径可能已提交的同一业务 ID。claimed 后任何超时均为 outcome=unknown。客户端通过原 action ID/控制 request_id 查证，或在语义允许时重发原 ID/内容。不得为“网络重试”创建新的 action ID。

固定可执行装配见 [Relay 字节证明](RELAY_PROOF.md)：等待以 queued/claimed 有界轮询表示，不分配等待线程。缓存响应通过当前授权读屏障，失效时只报告 request_gone，不重新执行或升级旧秘密。关闭后的 fresh enrollment 只读取本人已有请求的无秘密终态，不能代替已撤销的邮箱 capability 新建队列。

## 5. 出站循环、崩溃与撤销

```text
function outbound_game_loop():
  while mailbox open and registration valid:
    claims = game_pull(same_pending_nonce_until_response)
    for claim:
      if local claim journal has response: retry same relay_reply
      else if local claim journal has dispatch/unknown marker:
        report unknown or explicitly query original semantic ID; never redispatch claim
      else:
        persist claim identity and dispatch marker before semantic dispatch
        result = game_dispatch_claim(game_identity, claim)
        persist result or unknown marker
        relay_reply(original_claim_id, result)
    on transport failure: bounded backoff; do not reexecute an uncertain operation

function revoke_mailbox(controller_proof, mailbox_id, expected_route_revision):
  verify ownership and expected route revision
  atomic(mailbox_id):
    use reserved stop receipt capacity, not ordinary admission quota
    mailbox.state=closed; revoke all outer credentials; route_revision++
    for queued: mark closed/not_dispatched
    for claimed: mark closed/outcome_unknown
    preserve bounded receipts and wake waiters
  notify authorized game control plane if available
  sessions close explicitly or expire by their lease; no invented world rollback
```

游戏进程在 dispatch 后、保存 reply 前崩溃：有 durable 语义账本就按原业务 ID 查询，不重新执行 effect；无账本则报告 unknown。Relay 重启无持久状态时关闭旧 route 并重新配对，不能把旧 request ID 当从未执行。支持持久 Relay 时恢复 queued/claimed/replied 和凭据撤销记录，claimed 仍不自动二次分发。

控制面审批回包丢失也走 OperationReceipt；不能仅凭 Relay 的 claim 状态认定已经批准。客户端的退避有上限，且没有响应不得刷新会话或呈现租约。Relay 不能替代游戏续租，也不能通过重新配对延长旧 Grant。

## 6. 本地与云端端点安全规则

- HTTP 回环例外仅用于显式 test-enrolled；local-verified 仍须受控身份通道，不能因为 127.0.0.1 就信任任意程序。
- 非回环 TLS 验证服务端身份及配置的信任根，默认不接受重定向。资源下载的受控重定向是独立策略，不套用为携带会话凭据的 API 跳转许可。
- 浏览器入口只在明确提供者授权绑定中开放，Origin/CSRF/state/nonce 按该入口校验；不能直接解除实验 HTTP 全局 Origin 拒绝规则。
- 代理使用必须显式配置且进入 Scope 信任说明；默认不继承可能转发秘密的环境变量代理。
- 请求/回复/资源分别有协商大小限制；解码前硬上限不可由客户端提高。回包过大返回明确错误，已接受动作的结果可按授权引用查询，不伪造执行失败。
- 假端口通过这些规则推演，但具体 TLS/OAuth/OS IPC 标准版本及实现需真实接入阶段核实，不能凭本设计宣称已获得安全认证。

## 7. 对应场景

本地/云端两端均出站经 Relay 的装配：先验证身份与 Relay → 注册邮箱并分角色交付凭据 → 通过控制 lane 创建/批准 offer → 伙伴 lane 领取/加入 → 游戏 pull 执行内层协议 → reply 返回同一语义结果 → close/revoke 或租约收敛。管理面 action.claim/commit_result 留在游戏内部，不通过外层伙伴 lane。

该流程与 [端到端装配](END_TO_END.md) 的差异仅是调用经由此绑定；内层 scope、控制 request_id、Envelope.id、动作 ticket 和结果句柄不重新生成。审计必须额外检查重复 pull、迟到 reply、丢失审批响应、关闭 mailbox、Relay 重启和跨 lane 越权，不能只证明“消息能传过去”。
