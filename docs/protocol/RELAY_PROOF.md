# Relay 配对、队列、未知结果与撤销的字节证明

五个 `relay.*` 操作已接入 [RelayHarness](relay_harness.py)。组合入口由 32/37 增至
**37/37**，但 Relay 与游戏是独立 authority、独立事务和不同凭据域。入口数量不是全配置
符合性声明，也不代表把 37 项操作全部开放给 Relay 提交者。

## 1. 装配边界

```text
请求字节 -> codec/schema
          -> relay.* -> Relay authority 的队列/claim/外层凭据/回执事务
          -> 其他操作 -> PrivacyHarness 及既有游戏/本地/隐私角色入口

relay.pull 的 claim 字节
  -> 固定游戏端口验证原 claim/route/deadline
  -> 独立 inner proof 和游戏原有凭据
  -> 派发标记 -> 同一个游戏语义入口 -> 游戏结果日志
  -> relay.reply 字节 -> 原提交者用 relay.call 读取原结果
```

[RelayGamePort](relay_game_port.py) 是可信内存假端口，不是新公开操作、HTTP handler 或
自动执行器。它不会将外层凭据转换成玩家批准，不会替游戏执行 `action.claim`，也不自动
重新派发无结果的 claim。游戏原有的外部效果域不参与 Relay 的快照回滚。

## 2. 固定配对和三类凭据

内部 `RelayPairingAuthorization` 来自预置可信配对表，绑定完整 instance/epoch、Relay
origin/operator、原 controller、玩家/伙伴列表、限额、游戏控制证明、玩家同意证据及有效期。
请求只提供 `pairing_proof_ref`；知道一个引用或 mailbox ID 都不是认证。字段按规范字节
精确比较，时间/revision 通过整数 schema，不能用 Python 的 `True == 1` 混过检查。

注册的 OperationRequest.request_id 是 nonce。一次事务建立邮箱、nonce 回执和三类外层
capability。注册响应只有 mailbox ID、route revision 和 expiry，**不包含任何 token**。
`credential_for` 是可信交付端口：每个已认证接收方只能取到自己的一个凭据，不能传任意
目标主体来索取别人的凭据。原 pairing 不能用新 nonce 重建第二个邮箱。

| 外层角色 | Relay 权限 | 内层允许角色 |
| --- | --- | --- |
| relay_agent | 提交自己的请求 | agent / companion_control / results_reader |
| relay_controller | 注册、提交玩家请求、原 controller 撤销 | player |
| relay_game | 领取和回复 | 不得作为提交角色 |

内层只允许 control/data/results 三条 lane。management/local/privacy 和递归 relay 请求
在内层 schema 即拒绝；游戏仍使用自己的身份/Grant/代次/来源/当前状态检查。
`privacy.request/receipt` 保持独立 data_subject/privacy 入口，不随本次 Relay 装配扩大权限。

撤销会作废邮箱的全部 capability。预置的 fresh enrollment 身份不是邮箱写权：它只用于
配对交付、控制以及关闭后读取**本人已有请求的无秘密终态**，不能新建队列或取回旧 token。

## 3. call 的冻结与有界队列

去重键为 `(mailbox, authenticated principal, relay_request_id)`。摘要覆盖完整内层
OperationRequest（含内层 request_id 和扩展）以及外层 Relay 扩展；不覆盖传输关联 ID、
inner proof 和重试时自报的 deadline。inner proof 每次单独验证，主体/角色不能换绑。
首次接受的请求、内层 ID、proof 和有效 deadline 保存为独立快照，之后不会因重试刷新。

有效 deadline 是请求期限、注册期限、原 proof 期限和 `now + 30000` 的最小值。换一个
有效 proof 或更晚期限，只能读取原记录，不能延长它。已过期 ID 保留终态，不恢复为新请求。
嵌套请求重新执行完整 `validate_request`，不是只检查 JSON Schema 而漏掉条件字段关系。

队列容量不足返回 `resource_limit/not_accepted`，不会留下半条记录。接受前还检查该请求
能否放入一条 claim 的回包，预留最长关联 ID；不能先接受一个永远无法领取的大请求。

当前固定 profile 的上限：8 个邮箱；每邮箱 32 个 inflight、128 条保留记录、128 个 pull
nonce；一次最多 16 项，且请求和回复都不超过 `min(65536, negotiated message_bytes)`。
这些是本地假实现的硬限制，不把 `max_pending_actions` 偷换成 Relay 排队承诺。

## 4. pull 和 reply

领取采用**同主体 FIFO、主体间轮转**；当前配对只含一个伙伴和一个玩家，不宣称任意规模
的公平调度证明。批次同时按项数和最终编码字节数截断。claim、队列状态、nonce 回执必须
同事务提交后才能返回。原 nonce 重试只返回原批次，包括原空批次；新 nonce 不再领取 claimed。
如果旧 claim 已过期或路由/凭据无效，拒绝重放含 inner proof 的旧批次。

reply 必须来自精确邮箱的游戏主体和原 claim owner，关联原内层 request_id，并通过原
操作的输出/错误 schema。先检查内层及外层包装大小，再提交 `replied` 和冻结响应。
相同响应幂等，矛盾响应为 `reply_conflict`；本地游戏日志已有结果时还必须与其完全一致。
过期/关闭后的迟到回复为 `request_gone`，不能拿它触发新的游戏调用。

普通控制回执最多 256 格，reply 可用到 512 格，首次 revoke 独占第 513 格。已关闭邮箱
的新只读请求不继续消耗止损预留格，避免普通流量把撤销阻塞。相关反例先复现后修复：
批量回包曾达到 4517 字节而上限为 2200；普通回执填满时 revoke 曾返回 resource_limit。

### 旧回复的重新披露

冻结响应不等于永久可读。假游戏端口为响应保存授权状态指纹，覆盖 Grant/代次/成员、
来源 revision/expiry、结果读权、隐私 cutoff 和当前存活状态。改变后保守返回
`request_gone/unknown`，不从缓存再交付旧快照或秘密，也不重执行原请求。
pending join 的旧 Relay 回包不会被偷偷升级成新的 control token；调用者可以显式用
**原内层 request_id** 发起新的 Relay 传输，向游戏的原语义回执查询当前受保护视图。

这是固定假端口的保守读屏障，不是完整跨服务撤销协议。它可能使仍可安全读取的旧响应
也需要重新查询；真实传输的身份签名、屏障传播、在途发送及缓存清理仍需独立设计和验证。

## 5. 非事务派发与提交知识

| 观察点 | 可以做什么 | 不允许声称什么 |
| --- | --- | --- |
| 游戏派发标记之前故障 | 重试同一已验证 claim | 不能更换业务 ID |
| 标记之后、游戏调用之前故障 | 保留 unknown；不自动再调用 | 不能根据实际调用次数为 0 猜测可重试 |
| 游戏提交后、本地结果日志前故障 | 原业务收据可由显式查询恢复；claim 仍 unknown | 不能把 Relay/结果事务回滚当成游戏回滚 |
| 游戏结果日志已提交、返回丢失 | 重读同一日志，不再调用游戏 | 不能再次执行外部效果 |
| Relay reply 提交后丢 ACK | 同 reply/原 call 恢复冻结响应 | 不能重新入队 |

游戏返回后出现坏字节、错误关联或输出 schema 失败，同样保持 unknown；不会将它误报为
`not_accepted`。未知异常的原文、秘密和栈不回显给调用者。

测试实际交错“游戏端口已开始、Relay 随后撤销、游戏再接受消息”：消息仍只接受一次，
邮箱里的 claimed 请求保持 unknown，迟到 reply 被撤销凭据拒绝。这正是两个 authority
不能假装拥有一个共同回滚事务的原因。

## 6. 到期、撤销和重启

- queued 记录只有在本 Relay 已原子终止且 `known_dispatch=never_sent` 时返回
  `relay_not_dispatched/not_accepted`。它只证明**这条 Relay 路径**，不能推翻同一业务 ID
  在直连或其他传输上的提交事实。
- claimed 超时为 `transport_timeout/unknown`；关闭为 `request_gone/unknown`。有没有实际
  世界效果不能由“没收到 reply”推断，必须查原 action/control ID。
- revoke 使用原 controller 和 expected route revision；关闭、revision 增加、凭据撤销、
  queued/claimed 分类及回执同事务。注册到期也会关闭；均不刷新游戏 lease、Grant 或设备占用。
- 假账本重启保留 queued/claimed/replied/终态、撤销和 pull 回执，claimed 不重入队。
  独立游戏端口的派发标记/结果日志也保留；原 facade 退休，游戏 authority 和世界效果不重建。
  账本被标记为不可信时关闭旧 route 并拒绝继续操作，不将缺失状态解释为“从未执行”。

这些是内存快照恢复，不是磁盘崩溃或跨进程持久性证明；长期 tombstone 回收与重新配对
epoch 的生产策略尚未装配，满额时拒绝新请求而不删除旧拒重证据。

## 7. 实际验证与停止边界

[52 个 Relay 专项方法](../../tests/test_design_relay.py) 覆盖五个字节操作、完整准入/消息链、
三类凭据、双角色、嵌套条件校验、最小 core、两类容量、提交前后故障、6 种有界顺序、
双线程领取、派发与撤销交错以及两种假重启。全量入口累计 **435 个设计方法、42 条原模型轨迹**。

[独立 JS 客户端](../../scripts/design_interop_client.mjs) 与
[Python 假服务](../../scripts/verify_design_interop.py) 通过子进程管道实际执行 **23 组 codec、
268 次 wire、35 个不同公开操作**。新增链留下 1 个邮箱、1 条聊天消息、2 个已提交假世界
步骤；派发丢回复及重启后仍只调用一次，撤销后 route revision 为 2、世界步骤仍为 2，
游戏租约不被中继轮询或撤销续期。35 是夹具实际调用的操作数，不是全角色/全配置覆盖。

最终回执位于 `linshi/g2a-protocol-design-20261007/`：
`relay-final-verification.json`、`relay-cross-language-final-verification.json` 和
`relay-final-hygiene.json`。`relay-start-manifest.json` 保留与上一包一致的 96 文件基线；
`relay-before-assembly.json` 和 `relay-size-stop-before.log` 保留装配缺口与修复前反例。

本包完成了五个操作在固定可信配置中的可重放字节链，**没有**接真实 Relay、TLS/OAuth、
数据库、玩家账户、SDK、OS 或游戏引擎。Relay 可见明文，不是 E2EE；接收端拒绝内容不能
收回已经披露的明文，发送前的来源批准也不由本队列证明。独立厂商互通、全部能力组合、
长期公平性/清理、真实缓存撤销及部署继续是独立门禁，不因 37/37 入口而自动完成。
