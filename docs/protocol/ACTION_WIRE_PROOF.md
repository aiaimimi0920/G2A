# 动作确认、领取与结果提交的字节装配

本增量接续 [请求装配](PIPELINE_AND_CONSUMER.md)，补齐其中第一个剩余项的固定夹具闭环。
它不是新 SDK、通用游戏引擎或六个动作操作的所有配置组合认证。

## 1. 已装配路径

[action_harness.py](action_harness.py) 现在接收六个操作的原始 JSON 字节：

```text
action.confirm（玩家）→ action.request（伙伴）→ action.claim（已登记执行器）
→ 可信 WorldGate 两步效果 → action.commit_result（原 ticket 执行器）
→ action.query（伙伴）→ ResultReducer
                         ↘ action.cancel（伙伴）→ 汇总真实 partial/none
```

所有成功响应都经过对应操作 schema 和规范编码。拒绝以 ContractError 返回给测试驱动；
真实 HTTP 错误绑定、错误回包和事件 outbox 尚未在这条链里装配。

## 2. 单次确认

- 固定的 player 凭据与可信 decision 表分开。知道 decision_ref 或自报玩家身份不足以授权。
- 证据绑定玩家、会话、原动作请求 ID、动作 ID、参数摘要、完整定义摘要、期限和明确 allow。
- 确认不创建动作、不领取执行资格、不续租；同一交互换外层 request_id 也只返回原确认。
- 接受动作时再次检查确认元组和期限；确认消费、动作、数据收据在回复校验后一起提交。
- 接受前失败不消耗确认；提交后丢回复，重试原 Envelope.id 复用收据，不二次消费或执行。

decision 表是已验证交互之后的固定端口，不证明真实 UI 展示、签名或远程认证正确。

## 3. 执行器领取和执行边界

- 预登记两个执行器；请求中的 worker 必须匹配已认证执行器，不能借别人的 ticket 执行。
- ticket 固定绑定会话、动作、worker、接受控制代次、fence、deadline 和证明引用。
- 控制去重键为固定端点/会话内的主体、操作和 request_id；摘要覆盖 version/operation/payload/extensions。
- 原领取请求可重读原 ticket；新的领取请求面对 executing/terminal 只得到 not_executable。
- pending 动作失去授权、到期、升代或定义改变后，提交 cancelled/none 和 not_executable，不签发 ticket。
  此夹具将这些已知失效统一为该状态响应；未实现各原因的独立错误回包/审计事件。
- 接受时冻结定义、控制代次和实例 epoch。执行新步骤检查这些快照，不能用已刷新的伙伴
  凭据把旧动作带进新代次。读取原步骤事实不执行新效果。

ticket_id/proof_ref 使用固定可读夹具值，只能由表匹配测试解释；不是不可伪造的生产凭据。
单会话单动作、两步 find-key 是明确限制；实际 WorldGate 仍是可信函数端口，不是网络 API。

## 4. 结果、证明和业务值

原 ticket 可在写权撤销后报告已有事实；报告端口不会调用新效果，也不续租。执行器凭据
必须仍有效，报告及重读受本夹具记录保留期约束；伙伴结果读权另行控制。

报告的完整 ExecutionFact 必须与保存的效果账本和可信拒绝记录一致，包含步骤顺序、
effect、evidence_ref 及业务返回值。仅 schema 合法、仅声称 succeeded 或知道证明引用都
不能制造效果事实。终态新请求要求完整事实一致；旧 request_id 则按控制摘要恢复原回执。

成功的 known_result 来自最后一步 WorldGate 保存的 `{item: "gold-key"}`，不是复制请求方
自报内容。提交时按**接受时冻结**的 result_schema 校验；后续目录变更不能反向改写原结果
合同。成功要求 result；failed/cancelled/unknown 可以没有业务值，不填伪造的成功数据。

| 已保存事实 | 允许提交的结果 |
| --- | --- |
| 全部步骤已成功 | succeeded/committed，包括之后才撤权的情况 |
| 可信世界条件拒绝，之前无效果/有一步效果 | failed/none 或 failed/partial |
| 停止后未执行/已有一步效果 | cancelled/none 或 cancelled/partial |
| 已消费步骤资格但缺乏事实 | unknown/undetermined，禁止重做 |
| 外部事实已存在但账本曾未记录 | reconcile 原事实，再提交可信终态，不产生新效果 |

真实引擎即使提供可信结果，返回值违反业务 schema 仍须拒绝终态提交；已经发生的世界效果
不会因此回滚。测试断言保留 executing/committed 和原效果账本，避免假报 none。

## 5. 反例与原子性

本轮实际发现并修复了新的恢复反例：已接收 unknown 后，可信对账已经发现 partial 事实，
若调用者用新 request_id 再提交旧 unknown，原分支曾因“与旧报告相同”跳过当前事实验证。
负例出现 `AssertionError: ContractError not raised`；修复后，新请求重新校验当前事实并
拒绝过时报告。原 request_id 仍允许返回原 revision 的历史回执，消费者以 revision 忽略。

故障注入覆盖确认、接受、领取、结果提交：回复校验/提交前异常不留下半状态；提交后丢回复
保留动作、确认消费、ticket 或结果与对应回执。重复不延长租约或重新执行。

这些原子性结论只对单进程锁和内存暂存成立，不代表磁盘持久化或跨进程事务。

## 6. 可复核证据与剩余项

新增 [test_design_action_wire.py](../../tests/test_design_action_wire.py) 的 16 个测试方法。
其中包含真实双线程领取竞争、六字段 ticket 篡改、三处效果崩溃切点、结果 schema 接缝、
确认/控制去重、撤权/到期/升代、编码失败及提交前后故障。参数子例不与方法数相加。

统一验证：138 个设计测试方法，0 失败/错误/跳过；42 条原模型重放通过。
回执：`linshi/g2a-protocol-design-20261007/action-wire-verification.json`。

尚未完成的协议假实现任务仍保留：全事件类型和业务快照恢复、其余操作链装配，以及不共享
参考检查器的独立互通证明。本动作夹具未覆盖全部 actor/reader、任意多动作调度、全部
扩展和取消策略组合，也未生成动作事件 outbox，不能据六个操作入口宣称全操作互通。
真实认证、网络、存储和引擎保证需要另行验证；本轮未改旧 SDK，也未提交、推送或部署。
