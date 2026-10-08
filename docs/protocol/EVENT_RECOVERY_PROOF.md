# 核心事件目录与业务快照恢复

后续：[事件服务与一致快照](EVENT_SERVER_PROOF.md) 已补部分服务端事务和分页/快照字节
入口；本文第 4 节保留该轮历史边界，最新未完成项以新文为准。

本增量补足 [动作字节装配](ACTION_WIRE_PROOF.md) 之后的消费端缺口。新增设计选择仍是
`g2a-design-1` 工作草案，不声称来自其他协议的强制规则，也不升级旧 SDK/wire。

## 1. 原契约缺口和修订

原 session.snapshot 只返回 SessionView，history_gap.details.snapshot 也只有该视图。
它能说明会话状态，但没有动作结果、当前情境、有效定义和成员，不能据此恢复业务状态。

现改为闭合的 RecoverySnapshot，固定 snapshot_version=`g2a-recovery-1`：

| 字段 | 内容与约束 |
| --- | --- |
| session | 无秘密 SessionView，保留不可变 Scope、控制代次和各 revision |
| cursor | 与 session 同 session/epoch，sequence 必须等于 session.sequence |
| actions | 当前仍获读权的完整动作结果列表，ID 唯一；含终态及 unknown |
| contexts | 当前可见的各类别最新 game.context；每个类别最多一项，不是全部聊天历史 |
| definitions | 当前仍有效且与冻结批准摘要一致的动作定义；删除/变化不能扩大旧 Scope |
| members | 当前获准可见的成员子集；不扩大 Scope.audiences，不授予新席位权限 |

每个集合最多 256 项，另受 codec 总体限额约束。超限必须拒绝或另行设计分页，不截断后
自称完整。缺失集合不等于空集合；六个业务字段均为必需。全量视图的空集合有明确清空含义。

session.snapshot 成功返回该结构；history_gap 错误附带相同结构。错误 next_cursor 必须
等于 snapshot.cursor，unresolved_actions 必须恰好等于其中 pending/executing/unknown
动作集合，不能用另一个时间点的 cursor 越过未恢复数据。

这是新设计结构的收紧，已修改 contracts.py 并重新生成 schema/目录。旧实验 src/schema
及 SDK 不受影响；不可把此修订直接发给旧 SDK，也不声称草案此前外部兼容。

## 2. 八类核心事件

Event.envelope 现在是闭合 CoreEventEnvelope，而不是任意 type + 任意 JsonObject。
扩展事件未实现时必须拒绝；不能靠 supported_types 配置跳过语义处理。

| type | payload | 消费语义 |
| --- | --- | --- |
| chat.message | 已有 Chat 载荷 | 保存已认证/已过滤内容；team 需已协商，不能执行文字 |
| game.context | 已有 Context 载荷 | 替换相应开放类别的当前情境 |
| action.state | reason + ActionResult | accepted/claimed/cancel_requested/result；按 result_revision 归并 |
| capability.update | revision + definitions | 更新有效定义；不允许不同定义偷换冻结批准摘要 |
| membership.update | revision + members | 更新可见成员；不因通知授予旧事件访问权 |
| session.ready | session | active/ready=true，不能复活 closed |
| session.closed | session | closed/ready=false；通知丢失时仍需靠会话权威拒写 |
| session.control_changed | session | 控制代次严格增加；通知不是新的控制凭据 |

非聊天通知必须来自快照中固定的 GameAuthority，audience 必须包含当前消费者且不超出
Scope；聊天发送者也必须位于批准集合。此检查仍依赖上游已经认证和过滤当前成员代次/
来源授权，不能验证真实网络身份、来源事实或收回已经发送的明文。

动作请求、取消请求本身不作为事件广播：它们的可见状态统一为 action.state。就绪、关闭、
升代通知携带的能力/成员 revision 不得自行跳过对应完整数据通知，否则拒绝并等待快照。
查询结果和 action.state 共享 ResultReducer，旧结果不覆盖新结果，终态不能倒退。

## 3. 完整消费与恢复行为

[event_consumer.py](event_consumer.py) 新增 BusinessConsumer：

1. 从可信且已经按当前读权过滤的完整快照初始化。
2. 将整页结构/类型/cursor 校验和业务归并放到临时副本；任一后续事件失败，整页不提交。
3. 过滤产生的序号间隔和空页正常推进扫描 cursor；旧分页回复不重复应用。
4. history_gap 开启新的本地恢复轮次并阻止继续应用分页。
5. 已认证 session.snapshot 或 session.events/history_gap 响应字节同时检查操作、request_id、
   本地恢复轮次、epoch/cursor、不可变 Scope 和状态/revision，再原子替换业务视图。
6. 快照后仅缓存新事件；旧可见对象若已不在完整授权快照中则移除，不永久保留过期/撤权数据。
   仍可见的同一动作必须保持结果 revision 与确定终态不倒退。

旧 EventConsumer 仍用于原来的窄测试。其 cursor-only 重置不提供业务恢复保证；新的完整
路径必须使用 BusinessConsumer，不能把旧接口的测试当作完整快照验证。

快照不重建丢失的全部聊天历史，也不补造 shared_experience。它恢复的是当前授权可见
状态；持久记忆、第三方已留存数据和历史导出不是此接口可逆清空的范围。

## 4. 实测与尚未完成

新增 [test_design_event_recovery.py](../../tests/test_design_event_recovery.py) 的 13 个方法，
覆盖八类事件、后半页失败回滚、伪造发送者/扩权、未知类型与 required 扩展、过滤间隔、
快照业务替换、错误快照保留恢复态、迟到回复、history_gap 三字段一致性、撤权可见集合
移除、closed/终态不回退、team/受众边界，以及旧裸 SessionView 不能冒充业务快照。

统一验证累计 151 个设计测试方法，0 失败/错误/跳过；42 条原模型轨迹通过。
回执：`linshi/g2a-protocol-design-20261007/event-recovery-verification.json`。

未完成项没有消失：服务端需在同一权限/状态排序域内捕获快照和 cursor，并按来源与成员
incarnation 过滤；生产者所有操作的原子 outbox、真实分页服务/撤销重验及客户端落盘仍
未装配。剩余操作字节链、独立实现互通也待推进。本文仅证明 schema 与已认证消费端的
装配，不以受信快照 fixture 假装已证明服务器不会混用两个切点。
