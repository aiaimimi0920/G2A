# 游戏端口生命周期复核：旧实例与不健康账本

## 已复现的问题

`RelayGamePort.restart()` 会将旧实例 healthy 置为 false，但原先只有 dispatch、
retire 和 compact 入口检查该状态。旧实例仍可 enroll/verify 身份、计算 guard，
甚至为没有 journal 记录的 reply 生成 response_guard。Relay 本身健康、游戏端口
单独不健康时，原缓存回复也可能继续返回。这里不是证明世界效果重复执行，而是
证明生命周期拒绝规则在身份与结果再披露路径上不一致。

## 修复合同

enroll、verify、guard、response_guard 和 restart 必须在端口锁下检查 healthy；
退役或账本不健康均返回 `temporarily_unavailable`，不能继续签发内部身份记录或
提供结果再披露依据。dispatch、关闭屏障和回收保持相同拒绝规则。

guard 采用 port → game 的锁顺序，与 dispatch/verify 一致。健康检查与状态读取
不可跨越 restart 提交点。内部 `_identity`、`_error` 不是独立服务入口。

restart 的 intact 参数必须为 bool；非法值在修改原实例之前被拒绝。完整重启仍
允许新实例使用原证明和原 journal；不完整账本生成的不健康实例不可通过再次 restart
自愈。恢复必须来自独立可信流程，本增量没有添加该流程或对外接口。

## 回归证据

新增四个参数化场景：

- 保留旧实例引用，逐项验证身份、披露、派发、维护和再次重启均拒绝，新实例仍可读原回复。
- 不完整重启后，无 journal 记录的 response_guard 分支也拒绝，不能绕过账本失效。
- 拒绝 0、1、None、字符串、列表和对象形式的 intact，原健康状态不变。
- 仅游戏端口失效时，Relay 的新请求和原缓存读取均拒绝，邮箱状态不改变。

这些是内存模型回归，不是生产事故或独立安全认证。此前关闭屏障、批次清理、在途
效果保留和完整重启测试继续执行；全协议设计缺口仍见 SCENARIO_ACCEPTANCE.md。
