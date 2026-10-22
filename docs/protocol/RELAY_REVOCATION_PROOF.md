# 通用 Relay 对象撤销与 owner 边界

本增量不更改既有消息 schema 或新增操作；沿用既有 Relay 撤销合同，补齐通用对象入口。

## 规范合同

`permission.revoke` 的 `object_type=relay` MUST 在 Relay authority 解析，
而不是把游戏的 player/game 凭据提升为 Relay 控制身份。对象 owner 分派先于普通
游戏入口角色检查：本分支 MUST 使用 `relay.revoke` 的 `relay_controller` 角色、
`relay` lane、`core.session` feature 和同一原 controller 归属检查。
操作目录中的 player/game 与 control/management 描述保留为其他对象的游戏入口默认值。
这不是允许所有 permission.revoke 对象进入 Relay lane 的授权通配符。

`object_id` 对应 mailbox_id，`expected_revision` 对应 route_revision；失败 CAS 与原
Relay 接口一致报 `approval_stale`。成功返回 `RevocationResult`：
`{object_type: relay, object_id, revision, state: closed}`。
两个入口共享 `_close`、事务、凭据作废、终态与止损回执容量；只发生一次 revision 增长。
不撤销游戏 Grant、不取消已进入游戏的动作，也不伪造世界效果回滚。

回执键仍包含 principal、owner、operation 与 request_id。同一 ID 用于两个不同操作
不构成相同请求重试；第二个操作必须通过当前 revision CAS。原操作相同 ID 改 payload
报 `id_conflict`。已关闭对象以新 ID、当前 revision 查询只返回固定终态，不无限占用回执。
提交前故障整体回滚；提交后响应丢失可用原字节和仍有效的 enrolled controller 身份恢复。
已作废 mailbox token MUST NOT 因为“重试”而再次获得认证。

通用撤销不新增 Relay `operation.get` 路由；恢复使用原请求重放，不可把游戏的查询
凭据或回执读取权限套到另一 authority。游戏内层请求不会再次进入 Relay owner 分派。
queued 且 never_sent 只证明该 Relay 路径未投递；claimed 关闭只能保留 unknown。

## 本地可执行证据

`tests/test_design_relay.py` 新增八个场景：

- 通用结果结构、同一终态、全部外层凭据作废、游戏状态不变。
- 拒绝游戏内层凭据及 Relay agent/game 外层角色。
- 提交前回滚、提交后丢包、完整假账本重启、原回执、改参冲突和过期 CAS。
- 两个操作同 ID 的隔离，以及先通用后专用撤销的单次 revision。
- 先专用后通用撤销的固定终态。
- 普通控制账本占满时的止损预留，以及关闭后查询不增长账本。
- queued 与 claimed 的 not_accepted/unknown 区分。
- mailbox controller token 失效后拒绝重试；有效 enrolled controller 可恢复原回执。

这些是独立 authority 的内存模型证明，不是网络服务、真实身份发行、持久存储或长期
回收证明。已有并发 dispatch/revoke 场景继续验证共享 `_close` 的效果保留边界。

JS/Python 互通增加独立新配对链，实际跨语言发送通用撤销，覆盖拒绝两种错误身份、
提交前后故障、假重启恢复、同 ID 改参冲突，以及专用入口的旧/新 revision。
