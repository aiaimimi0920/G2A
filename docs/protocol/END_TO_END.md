# 全流程装配与首轮轨迹

状态：假实现装配设计与轨迹输入；不是实际网络执行日志。本文件保留输入、调用顺序、预期状态和异常出口；实际模型断言与人工符号推演结果见 [验证记录](WALKTHROUGH_RESULTS.md)，不能把本表本身冒充执行日志。

## 1. 可替换假端口与组合方式

```text
FixtureIdentity:
  map preregistered proofs to exact (issuer,subject,role,audience,expiry)
  unknown proof / mismatched audience / expired proof -> AuthError
  provider fixture additionally requires server-side transaction nonce and player consent
FixtureStore:
  transaction rollback, per-authority serial ordering, optional durable snapshot
  inject commit failure before or after external effect; never silently fabricate a ledger
FixtureWorld:
  world = {key_available:true, key_owner:none, effect_count:0}
  effect(ticket,step=1,args={room:hall}) under gate:
    require key_available and no prior claim for same effect key
    set key_owner=player; key_available=false; effect_count++
    optionally drop response after change
FixtureDevice:
  baseline_visible=true, manual_revision=0, occupations={}, released={}
  apply desired visibility or injected renderer failure; no actual GUI required
FixtureResources:
  controlled byte fixtures and exact manifests; inject digest mismatch/redirect/cycle
FixtureTransport:
  dispatch allowlisted operations to the same authority; inject loss/duplicate/reordering
  cloud/relay fixture models trust boundaries, not real internet connectivity
```

业务状态在协议模型中更新，不把 fixture 直接输出 `success` 当作绕过批准/WorldGate 的捷径。所有主体、scope、受众、ticket 与 generation 检查仍执行于伪代码路径。

## 2. 四种位置组合与两个入口

入口不是部署地点：每种组合均支持伙伴发起或游戏发起。差异止于身份解析/唤起/连接方式，批准后的抽象流程保持一致。

| 游戏 / 伙伴 | 验证与连接方式 | 游戏发起的额外步骤 | 伙伴发起的额外步骤 |
| --- | --- | --- | --- |
| 本地 / 本地 | 两端 local-verified，或明确标注的 test-enrolled；回环受控通道 | 已验证注册表选伙伴，未运行则明确启动许可 | 伙伴已运行，选择验证后的游戏候选 |
| 本地 / 云端 | provider-verified；直连游戏主动连接提供者或经已批准 relay 出站 | 选择提供者、完成玩家↔伙伴委托，不使用 Launcher | 云端伙伴选择玩家已登记的游戏出站端点，不扫描内网 |
| 云端 / 本地 | 远端游戏 TLS+提供者身份，本地伙伴通过出站连接游戏 | 提供者给出受验证的本地注册入口，由本机可信 Launcher 确认启动 | 已运行伙伴直接选择远端游戏并验证玩家席位 |
| 云端 / 云端 | 双方 provider-verified，受众绑定的直连或 relay | 玩家在可信控制面选择伙伴提供者并完成委托 | 伙伴在玩家已验证席位范围发起申请 |

云端伙伴无桌面时不协商 presentation；如果游戏硬性要求桌面隐藏，则 feature_unsupported，而非填 false 伪装。cloud fixture 的成功只证明抽象流程一致，不证明某家提供者身份协议或公网部署已实现。

## 3. 完整装配伪代码

```text
function companion_game_flow(entry, topology, player_choice, fault_plan):
  configure_fixture_or_real_ports(topology, fault_plan)
  player = verify_player_seat_in_game(player_choice)
  candidate = discover(player_choice.game_candidate)
  if topology has provider:
    provider_tx = begin_server_side_identity_transaction(player, candidate,
      exact_agent_choice, bounded_return_destination)
    delegation = Provider.complete(provider_tx.id, verified_callback)
    if rejected/expired/mismatch: return no_offer_no_session
  agent = verified_companion_identity(topology, player_choice)
  offer = create_offer(proof_for_entry(entry), entry, candidate,
    negotiated_requests(player,agent), stable_offer_nonce)
  outcome = attempt_automatic(offer)
  if outcome != approved:
    outcome = decide(trusted_player_proof, offer.id, offer.scope_digest,
      allow=player_choice.allow, remember=player_choice.remember,
      launch_permission=player_choice.launch_permission)
  if denied/expired/stale: return no_invitation_no_session
  channel = ensure_companion_available(offer)
  if launch/delegation failure: return no_session_and_unused_grant_revoked
  slot = reserve_companion_slot(agent_proof, offer.id, offer.decision_deadline)
  // 从此以后所有失败/超时分支 finally release_slot；已创建 session 则先本地停止并闭会
  intent = freeze_join_intent(offer.scope_digest, verified_device_observation_if_applicable)
  invitation = redeem(agent_proof, offer.id, intent)
  join_reply = join(agent_proof, invitation.secret, intent)
  while join_reply == join_pending and before_original_deadline:
    inspect_or_advance_same_admission(join_reply.session_id)
    join_reply = join(agent_proof, same_invitation, same_intent)
  if admission failed: return closed_and_occupation_released
  session = join_reply.session
  require session.admission_ready
  attach_slot(slot, join_reply)

  game.publish_context(session, id=c1, category=room, explicit_audience={player,agent})
  agent.read_events(session, cursor=0)
  agent.submit(chat.message(id=m1, audience={player}, text="我可以帮你找钥匙"))
  // 主动表达，无须此前有玩家问题；文本不是动作批准
  if actions negotiated:
    action = submit(action.request(id=a1, capability=find_key,
      revision=current, arguments={room:hall}))
    ticket = claim_action(game_proof, session.id, a1, registered_worker)
    fact = world_step(worker_proof, ticket, step=1, game_condition=key_available)
    commit_result(worker_proof, ticket, report_from_actual_fact(fact))
    result = query_action(join_reply.result_read_handle, session.id, a1)
    if result unknown: reconcile_by_original_ticket_without_reexecuting()
  close_session(current_control_proof, session.id, reason=left)
  release_slot(slot, left)
  dispatch_close_outbox_until_ack_or_occupation_lease_expiry()
  assert session.closed and no_new_effect_permission
  assert device_has_no_occupation_for_this_session when applicable
  return final_receipts_and_actual_known_results
```

`begin_server_side_identity_transaction` 分配一次不可预测 nonce，持久绑定 initiating_player/game/agent_provider/audience、受限回调目的地、到期、used=false；Provider.complete 验证后原子标为 completed并保存固定委托结果。失败/重放不同结果拒绝，同结果回放只返回原委托。它不签发 Grant，不代表玩家已批准游戏接入；之后仍经过 offer.decide。

## 4. 主路径逐步状态表：游戏发起、本机伙伴未运行

固定假输入：player=`fixture/player/alice`，agent=`fixture/agent/fox`，game=`fixture/game/key-quest`，instance=`room-1/e1`；采用 test-enrolled 并明确非生产；features=core+actions+presentation；hide_desktop 条款；Grant 到期 t=300，offer 截止 t=60；invitation_ttl=30，在 t=3 签发的邀请截止 t=33；初始 session lease=t=120；baseline_visible=true；无可下载 avatar。动作 a1 最晚 t=30，任何超时不得新增 ID 重做。

| 时间 | 调用与输入 | 应观察到的状态/结果 | 不得发生 |
| --- | --- | --- | --- |
| t=0 | 验证候选身份，create_offer nonce=n1 | O1=pending，Grant=0，Session=0，伙伴进程=0 | 发现即授权/启动 |
| t=1 | 玩家批准 O1 原摘要，并单独允许启动 | O1=approved，G1=active，Session=0 | 把 remember 当启动许可 |
| t=2 | Launcher 按固定注册信息启动 | 伙伴进程=1，绑定 fox；仍 Session=0 | 执行 offer 中的任意字符串命令 |
| t=3 | fox redeem O1 + 原 JoinIntent | I1=issued，绑定 G1、e1、fox、alice | 控制台领取伙伴邀请 |
| t=4 | join I1 | I1=consumed，S1=active/ready=false，占用准备中 | 发送行动或领取新邀请 |
| t=5 | acquire(S1,g1) ACK，ready 提交 | 占用=1，实际可见=false，S1.ready=true，发放 g1 写凭据和只读结果句柄 | 就绪前发送可用凭据 |
| t=6 | game.context c1；fox poll | 授权受众收到情境；无副作用 | 给未授权队员投递 |
| t=7 | fox 主动 chat m1 | 收据存在，玩家收到一条聊天 | 以聊天文本直接执行动作 |
| t=8 | action.request a1 → claim → world_step | a1=pending→executing，effect_count=1 | claim 重复授予执行权 |
| t=9 | commit_result a1，query a1 | succeeded/committed，key_owner=alice | 把接收收据提前当成功 |
| t=10 | 相同 a1 原消息重发 | 原收据 duplicate=true，effect_count 仍 1 | 重复事件/领取/效果 |
| t=11 | close S1，release(S1,g1) | S1=closed，占用=0，可见=true；结果查询仍按句柄有效期 | 重启旧会话或抹除共同经历 |

云端伙伴主路径复用这张表，移除 Launcher/presentation 两类步骤；不能伪造不存在的进程/窗口。伙伴发起则其进程在 t=0 前已存在，使用伙伴证明 create_offer，批准仍只能由玩家完成。

## 5. 错误注入的预期轨迹

这些是后续审计的可检验预期，不是已经执行的自动测试结果。

| 轨迹 | 注入点 | 预期终点和计数 | 所需审计入口 |
| --- | --- | --- | --- |
| T01 拒绝 | O1.pending → allow=false | 无 Grant/邀请/Session/启动；effect_count=0 | decide |
| T02 条件变化 | 批准后 descriptor revision 改变，再 redeem/join | approval_stale，Session=0 | assert_current_scope |
| T03 启动失败 | 明确批准后 Launcher 失败 | 无 Session，未使用 Grant 撤销 | ensure_companion_available |
| T04 重复加入 | 第一个 ready 回包丢失，两次相同 join | 同 S1、同 g1 secret、占用=1 | join/finish_admission |
| T05 准备中撤权 | acquire 已隐藏，ready 前 revoke G1 | S1.closed，数据面从未开放，最终占用=0 | fail_admission/release tombstone |
| T06 领取前取消 | a1.pending 时 cancel | cancelled/none，effect_count=0 | accept_cancel/claim_action |
| T07 效果前撤权 | claim 后、world_step 前撤能力 | step 拒绝，effect_count=0；执行器报告取消 | execution_fence/commit_result |
| T08 效果后失联 | world_step 完成，结果回包丢失 | 先 unknown，再以原 ticket 查询/事实报告得到 succeeded；effect_count=1 | recover_execution_ledger |
| T09 非事务执行崩溃 | 消耗 step 权后失联，事实不可查 | unknown，禁止重执行；不能断言 effect_count 为 0 或 1 | fenced-nonatomic |
| T10 事件历史过期 | cursor 小于 event_floor | history_gap + 当前受限快照；不补造聊天、不重做动作 | read_events |
| T11 退队 | 私聊/团队事件排队后成员退出 | 退出者不获新投递；新增队员不读旧数据 | freeze_audience/membership_replace |
| T12 双会话退出 | S1 hide、S2 hide，先退出 S1 | 仍隐藏；退出 S2 才恢复最新 baseline | occupations/recompute_visible |
| T13 用户改显示 | hide 会话中用户明确选择显示 | 本机释放冲突占用并停止交互、发起闭会；manual_revision 上升 | manual_change |
| T14 设备转移后旧邀请重试 | handoff g1→g2 后重放 I1 | 返回 already_joined，不得取得 g2 secret；旧 g1 无写权 | join/begin_handoff |
| T15 资源校验失败 | 字节/hash/依赖/来源不符合批准清单 | admission 失败、Session.closed、effect_count=0 | prepare_resources |
| T16 会话重启 | 完整 durable 账本/丢失账本各一条 | 前者可在期限内恢复并撤旧代次；后者拒绝恢复、结果诚实 unavailable/unknown | resume/recover_execution_ledger |
| T17 未知版本/必需扩展 | 协商前输入未知版本/required extension | 无 Offer/授权，明确拒绝 | negotiate |
| T18 超限 | 新动作到达前收据/队列满 | not_accepted，可原 ID 重试；close/query 仍可用 | reserve capacity |

## 6. 全流程证据入口

Relay 请求/回复/撤销及输入路由见 [绑定伪代码](BINDINGS_AND_RELAY.pseudo.md)。D01–D16/R01–R17/S01–S14/I01–I10 对应关系见 [审计台账](CONFORMANCE_AUDIT.md)；轨迹执行与边界推演见 [验证记录](WALKTHROUGH_RESULTS.md)。两者共同限定完成范围，不把本文件的“应观察到”当实际执行证据。
