# Relay action 受理事实查证

`settle_action_acceptance` 为可信内存端口维护方法，覆盖 action.request 与
action.cancel，不是新增公开操作。沿用关闭邮箱、当前代次、精确派发见证及原 inner
proof 验证；不会重新提交原请求。

## 正确的业务键与授权

action 消息按 `Envelope.id` 去重，外层 OperationRequest.request_id 只是传输身份。
查证使用 Envelope.id 查询原会话 action 账本，并将回执 record_digest 与完整
Envelope 的 message digest 比对。完整 claim/binding 另由派发见证绑定，不能修改
传输字段后借用其他请求的受理记录。

派发的 companion_control 权限不自动变成结果读取权限。调用者必须另提供当前
有效的 `reader_proof`，由可信登记解析，主体必须与原派发主体相同；查询复用
`SessionHarness._operation_view` 的 agent 角色、原成员代次、结果撤权、保留期和
pending_sync 检查。不能直接把 companion_control 角色改名成 agent 绕过这些边界。
撤销读取授权后，即使存在原回执也不能通过此入口查证。

游戏可信时间维护可能先推进到期状态，与现有查询边界一致；后续失败不回滚已
发生的独立维护。pending_sync 时不主动发布结果，不借查询补做动作同步。

## 受理、执行、结果三者分离

成功只返回 `{"settled":true,"acceptance":"committed"}`，移除该 claim 的
unresolved；不把 action 状态、参数、票据、结果正文或部分效果证据交付给调用者。
原 action 仍可以是 pending。代次轮换不停止、重启或完成该 action；其后续执行
继续遵守原会话与 WorldGate 规则。取消请求被受理也不等于先前效果已经撤销。

查证前后故障沿用独立提交语义：提交前保持阻断；提交后丢响应可再次验证授权和
账本，不能通过重执行业务取回结果。保留派发见证直到成功轮换；journal GC 和
假重启不能使其丢失或变成新的派发许可。

## 证据与剩余范围

四个新增测试方法覆盖 request 提交后丢回复、两种查证提交故障、GC/重启、与传输
ID 不同的 Envelope.id、pending 动作无效果查证及轮换；cancel 受理无重执行；
结果撤权、回执摘要冲突、控制角色不能冒充 reader、其他主体与撤销 reader 拒绝。

后续四个测试方法补齐以下边界：

| 条件 | 结果与不可改变的事实 |
| --- | --- |
| now 等于 read_until | 当前 reader 身份仍有效时可查证；不新增游戏效果 |
| now 大于 read_until | permission_denied，保留 unresolved；不得把过期等同于未受理 |
| 原成员已退出 | permission_denied，原有效 reader 身份不能替代成员读权 |
| 同主体以新成员代次重入 | permission_denied，不能恢复旧 origin_members 的读取资格 |
| pending_sync 为 true | temporarily_unavailable，查询不清除同步标记、不发布结果、不执行效果 |
| worker 管理操作经 Relay 路由 | authorize_relay_inner 拒绝，不新增派发见证 |

成员退出/重入反例直接设置可信成员表来隔离查证条件，不宣称完整 membership.replace
字节链已在这些新测试中执行。保留期测试允许独立可信时间维护关闭到期会话；它只
断言没有新效果，不声称时间维护不会改变会话状态。
底层身份期限修复后，保留期场景显式可信登记新的同主体 reader，不再依赖已到期
身份；详情见 [身份有效期交集修复](RELAY_IDENTITY_EXPIRY_FIX.md)。

这是固定内存模型证明，不是跨语言新维护接口或真实持久化证明。特别是
action.claim/action.commit_result 属于 worker 管理通道，当前 Relay 只允许 agent/
controller 的 control/data/results 路由；这两项不应被列为“待开放的 Relay 操作”。
其直接 worker 通道的效果未知及 partial/unknown 收敛仍应依据独立执行合同验证，
不能为覆盖率而放宽 Relay 路由。控制账本等合法 Relay 操作仍需各自的查证规则。
