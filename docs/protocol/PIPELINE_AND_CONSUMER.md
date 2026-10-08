# 请求装配、消费恢复与权威端口闭环

后续增量：[动作字节装配](ACTION_WIRE_PROOF.md) 已补本文留下的 confirm/claim/commit_result
及业务结果校验。本文的 122 方法和“尚未装配”描述保留为该轮历史边界，不代表最新停点。
事件类型与业务恢复后来由 [事件恢复增量](EVENT_RECOVERY_PROOF.md) 补到完整可见消费模型；
生产端快照/事件一致性仍未验证。

本轮在原模型基础上补装配，不增加真实服务或改旧 SDK。人工复核的重点是各层规则
是否真正串联，而非各自存在函数。当前范围如下，不能把局部闭环写成全操作互通。

## 1. 动作入口

[action_harness.py](action_harness.py) 实际解码并处理 action.request/action.cancel/action.query：

- 结构、固定凭据角色、session/version/sender、Grant 与控制代次。
- 完整 Envelope 摘要去重；相同消息 ID 修改期限也冲突，重复不再次执行或续租。
- 动作必须在批准集合中，完整定义摘要匹配，actor 合法，参数符合有限值 schema。
- 接受时冻结请求/定义最大时长/租约/授权期限的最严截止时间。
- 执行新步骤前再次检查当前写权、期限和定义摘要；读取既有步骤事实不产生新效果。
- 新请求先在模型副本中暂存，回复通过 schema/编码后再提交，失败不留半动作。
- 写权撤销后按独立只读保留期读取结果；结果读权可另行撤销。
- 结果实际序列化后交给独立 ResultReducer，而非仅检查内部字典。

限制：固定单会话、单动作、两步执行；claim/step/reconcile/finish 仍是可信执行端口，
不是 action.claim/action.commit_result 全 wire 路由。高风险一次确认尚未装配，
requires_per_action_consent=true 时明确 action_consent_required，不静默批准。
完整动作业务结果值和确认工作流仍待装配，不能宣称 action 生命周期全部 wire 化。

本轮接缝测试实际发现：上一轮模型允许 executing/committed，但 ActionResult schema
仍拒绝。先复现 invalid_message，再补允许组合，并让该状态实际经过结果 schema。

## 2. 事件消费者与结果状态归并

[event_consumer.py](event_consumer.py) 仅消费已认证且按当前权限过滤的响应。

ResultReducer 的键为 session_id + request_id：

- 较低 result_revision 忽略；相同 revision 内容不同为 reply_conflict。
- 较高 revision 不能改变已确定终态及已知结果，不能退回 pending 或把已发生效果报 none。
- unknown 不是确定终态，可以被更高 revision 的可信事实解决。
- 返回副本/保存独立数据，防止调用者改写已经接受的状态。

EventConsumer 的窄 profile 支持 chat.message 与 game.context：

- cursor、high_watermark、请求 cursor 同 session/epoch，事件版本也必须一致。
- 单页事件序号严格递增且位于请求/返回 cursor 区间内，先检查整页再提交。
- 权限过滤可以产生序号间隔和空页；不以“不连续”自动推断历史丢失。
- 旧 poll 回复不使 cursor 倒退，也不重复应用事件。
- 未知事件类型明确停止，不自动推进 cursor 丢弃未知语义。
- history_gap 后阻止继续消费，直到可信恢复端口提供同 epoch、不倒退的快照 cursor。

快照接口不验证远端签名，只接收外部已验证结果；它清空本地旧事件缓存，保留快照之后
的事件，不声称重建所有业务状态。换 epoch 必须重新建立消费者。缓存固定最多 256 条，
满时拒绝而不是无界增长。本实现没有网络确认、磁盘 checkpoint 或完整事件类型目录。

## 3. 扩展与策略处理器

[extension_runtime.py](extension_runtime.py) 提供两个明确标为测试用的收紧型处理器：

| fixture 扩展 | 效果 |
| --- | --- |
| example.max-chat-bytes / 1 | 按 UTF-8 字节限制聊天正文，不是按字符计数 |
| example.deny-action / 1 | 拒绝指定动作，不授予任何新权限 |

它们在聊天/动作提交之前实际执行，处理器只拒绝或通过，不修改原请求、不执行任意插件。
Policy.extensions 来自冻结 Scope 并独立执行，不能被请求省略。未知配置、错误版本、
不适用操作都拒绝，不假装“校验了扩展结构”就等于执行了策略。
空扩展的核心 action.cancel 不依赖策略处理器可用性；原身份及动作归属检查仍有效。

这不是正式扩展注册，不实现任意插件加载，也不证明自然语言剧透/主动发言等策略合规。

## 4. 来源导入权威端口

[source_import.py](source_import.py) 在预置可信证据表之后增加可执行导入检查：

- 已验证 controller、证据引用、目标实例/会话、完整来源声明必须匹配。
- 发布者/读者/有效期不能超过证据，也不能超出原始披露范围。
- 同 revision 同内容幂等、异内容冲突；旧 revision 拒绝；更新仅缩权。
- 解析键包含实例、会话、本地 source_id，避免跨游戏句柄碰撞。
- 可信事务重新取 snapshot 时，已撤销或到期证据使导入记录撤销并升 revision。

测试实际运行导入→chat.submit→delivery，再撤销证据并刷新权威快照→停止投递。
这验证固定认证端口之后的授权处理，不是远程签名认证。生产证据验证、撤销同步和
快照与提交的原子排序仍由真实 adapter 负责；导入器自身未提供并发数据库。

## 5. 实测与剩余项

本轮新增 test_design_pipeline.py 的 11 个方法、test_design_authority_ports.py 的 6 个方法，
并加强既有 executing/committed 的 schema 接缝测试。累计 122 个设计测试方法、42 条原
模型轨迹通过。结果到达顺序另枚举 6 种排列，不与方法数相加。
回执：linshi/g2a-protocol-design-20261007/pipeline-verification.json。

| 上轮剩余项 | 当前状态 | 尚缺 |
| --- | --- | --- |
| 动作完整请求链 | request/cancel/query 已装配 | confirm、claim、commit_result 的完整字节入口及业务结果 schema |
| 事件恢复 | 窄消费 profile 与结果 reducer 已验证 | 全事件类型、真实快照内容、网络/持久恢复 |
| 扩展/策略和来源认证 | 两个收紧处理器及固定证据端口后的导入闭环 | 通用扩展、自然语言策略、真实认证/撤销同步 |
| 全操作互通 | 仍仅全操作 schema/符号轨迹，局部可执行闭环 | 独立实现间互通，不能以共享检查器自测代替 |

人工复核前仍需继续完成表中协议假实现范围的缺口；生产部署和实际外部认证不属于本轮
已完成内容。本文件不会将这些剩余项换名为“完成后的优化”。
