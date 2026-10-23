# Relay 会话控制提交查证

## 支持范围与身份

`settle_session_control` 查证 session.heartbeat、session.close，以及会话侧
permission.revoke 的 session/result_read/capability 分支。它是可信端口维护方法，
不新增 wire 操作；grant/invitation/auto_rule/relay 等其他 authority 分支不混用该账本。

端口要求健康、当前代次、邮箱已封闭，且完整 claim/binding 匹配原派发见证。
原 inner proof 仍须有效。另提供当前有效的同主体 reader_proof，角色只能为 agent
或 player；原 companion_control 身份不能自行转换为 reader，也不能借另一主体查询。

## 证据与知识边界

会话控制按 `(principal, operation, OperationRequest.request_id)` 索引，不使用
action 的 Envelope.id。查证读取独立游戏 session_controls 账本，比对原请求的
version/operation/payload/extensions 摘要，并复用原主体 operation.get 投影。
回执缺失返回 outcome_unknown，摘要冲突返回 id_conflict，均不解除 unresolved。

成功只返回 `{"settled":true,"acceptance":"committed"}`。不返回历史 session
正文、租期、控制凭据或撤权结果正文。历史 heartbeat 提交事实不代表当前租期仍然
有效；close/revoke 提交事实不授予任何重新打开会话或恢复权限的能力。

## 独立维护与提交

查证不调用原控制操作，所以不会续租、重复发布关闭事件或再次增加撤权 revision。
与既有查询一致，可信时间维护可能先关闭到期会话；不把这一步误报为查询重执行。
查证提交前故障保留未知，提交后响应丢失可以重新查证；重试仍要求当前授权与回执。
关闭屏障与代次隔离始终禁止原 claim 再派发，journal GC 不清理未知派发见证。

会话控制回执沿用当前固定模型的保留策略，不借用 action.read_until。此方法没有
新增无限保留承诺；未来独立清理控制账本后，没有证据就保持未知，不推断未执行。

## 验证

四个新增测试方法覆盖：heartbeat/close 的实际提交后丢回复、关闭/GC、查证提交
前后故障、假重启和轮换；三种撤权分支查证不改变原 session 状态或 revision；
更晚时间查证 heartbeat 不延长 lease；错误 reader、缺失和冲突回执拒绝。

这些是固定内存模型场景。尚未证明跨进程可信查询、防快照回滚、长期控制回执 GC、
全部并发交错、其他控制 authority 或第三方互通。不能由此宣称整个协议恢复完成。
