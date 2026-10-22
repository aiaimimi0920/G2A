# 固定会话的动作能力撤销

本包补齐 `permission.revoke(object_type="capability")` 的固定会话模型路径，不增加公开
操作，不修改旧 SDK。先前该对象已有结构契约和语义声明，但装配入口返回
`unsupported_operation`；新增 10 个测试方法在实现前实际得到 9 个错误和 1 个失败。
这是已声明而未装配的路径，不是已上线服务的缺陷证明。

## 对象、权限和版本域

- 本受限 profile 的请求接收方已绑定唯一会话；`object_id` 是该 Scope 已批准的 action ID，
  `expected_revision` 是该会话的 `capabilities_revision`，与 `capability.replace` 共用 CAS 域。
  未批准 ID 拒绝，未协商 actions 返回 `feature_unsupported`。
- 仅原玩家或当前 GameAuthority 可撤销，沿用既有 control/management 身份检查。
  伙伴不能通过自报对象类型获得撤权能力。
- 撤销增加 revision，持久于模型账本的 `revoked_capabilities` 集合；它收窄当前 Scope 的
  有效权限，不改写批准时的 Scope、摘要、Grant 或结果读取权限，不关闭整个会话。
- 后续 `capability.replace` 即使再次提交相同定义，也不能移除撤销屏障或恢复权限。
  重新授权应建立新的批准范围；本包没有“撤销撤销”操作。

这里不是实例级广播撤销。多会话路由、同名 capability 的全局对象命名和跨 authority
传播仍需单独合同，不能把唯一会话夹具中的 action ID 解释为全局撤权标识。

## 提交和副作用边界

撤销屏障、可见定义列表、revision、停止动作、`capability.update` 事件及原请求回执
在既有会话锁和事务内提交。待领取动作取消；已领取动作停止后续效果。WorldGate 继续
在每次新效果前检查可用性，返回 `stale_capabilities`，不靠客户端停止发送来保证安全。

已发生效果绝不回滚。部分效果仍可经原 ticket 的 `action.commit_result` 收敛并由
`action.query` 读取；能力撤销不等于 `result_read` 撤销，不抹掉历史事实。

提交前故障回滚屏障、动作、事件和回执；提交后丢回包重试返回原结果、不增加事件或
revision。同 ID 改正文返回 `id_conflict`；新 ID 携旧 revision 返回 `generation_conflict`。
新 ID 携当前 revision 可再次确认撤销并增加 revision，但不能恢复权限。

`operation.get` 沿用原主体的控制回执账本，报告原撤销请求 `done`，不建立新查询索引。
原玩家可查，伙伴不可读取玩家收据；不因此开放 GameAuthority 的私有管理查询。

## 验证与限制

[test_design_capability_revoke.py](../../tests/test_design_capability_revoke.py) 的 10 个方法覆盖：

1. 撤销后拒绝新动作，同时保持会话、Grant、Scope 和结果读权。
2. pending 动作不可领取但仍可读取取消结果。
3. 已执行一步后撤销，第二步被拒，原 ticket 可提交 partial 事实且世界效果不减少。
4. 定义替换不能恢复撤销的权限。
5. 提交前回滚，原动作仍可领取。
6. 提交后重试、ID 冲突、陈旧 CAS。
7. 错误对象和伙伴角色拒绝且无状态修改。
8. 游戏管理撤销，以及最小 core 的功能拒绝。
9. 内存账本复制恢复后仍保留屏障及原回执。
10. 完整准入链后的撤销/原玩家 `operation.get` 字节查询和伙伴拒绝。

本轮完整门禁预期 537 个设计测试方法、42 条原模型轨迹；既有 JS/Python 互通回归
另行运行。没有新增 JS capability 撤销场景，不把 Python 新场景称为跨语言新证据。
实际结果见 `C:/Users/Public/nas_home/AI/GameEditor/linshi/g2a-capability-revoke-20261022/`
中的 `red.log` 和 `final-verification.json`。

停止条件是上述撤销路径、事实保留、回滚/重试和回归通过。仍未验证多动作/多会话、
实例级传播、真实持久数据库恢复或全部并发调度；auto_rule 与通用 permission.revoke
到 Relay owner 的路由仍未装配，不能把本包计为所有撤权对象完成。
