# 来源披露与聊天请求装配验证

状态：设计参考实现；供后续人工复核，不是生产隐私认证。承接
[外部协议研究](PROTOCOL_RESEARCH.md) 的来源权威性及分层装配问题。

## 1. 这次具体解决什么

此前 `Source` 只有声明字段，而数据面伪代码中的来源校验没有可执行的权威解析。
一个消息即使 sender、会话、接收者都合法，也不能因此被允许把 player_report 改称
shared_experience，或给一条未授权来源增加接收者。

本次增加两层：

- [source_authorization.py](source_authorization.py)：将显式声明与可信来源授权记录匹配。
- [chat_harness.py](chat_harness.py)：只装配一个会话的 chat.send，由原始 bytes 到编码回复、
  原子内存提交与后续投递检查。复用既有 codec、schema、路由、Grant、成员和扩展检查。

不是新建 SDK/服务器；不替代原 FlowModel，也不把 37 个操作全部标为完成装配。

## 2. 来源授权记录与信任边界

`SourceAuthorization` 是权威端内部契约，包含：

| 字段 | 含义 |
| --- | --- |
| instance / session_id | 此导入授权绑定的目标实例与会话 |
| source | 完整不可变 Source 声明，source_id 是目标会话解析表中的本地句柄 |
| controller / evidence_ref | 数据控制者及其授权证据引用；必须由可信导入端验证，不是自签名凭证 |
| publishers | 获准再次发送该来源的主体，拥有阅读资格不自动拥有转述资格 |
| allowed_readers | 当前仍允许的明文读者，必须是 original_disclosure_scope 子集 |
| revision / state / expires_at | 单调修订、active/revoked 状态与独占期限上界 |

这不是客户端可调用的创建授权操作。`records` 不能从请求 provenance 直接构造；
source_id 不当作全局唯一事实 ID，也不能在另一个实例/会话中直接复用。
跨游戏导入须先通过目标端可信导入表建立新句柄和授权，不能根据原游戏 URL 自动联网信任。

本次窄规则不支持把原始披露范围扩大。若用户以后希望显式授权新的读者，需要另行定义
可追溯的新披露授权，而不是原地改写 original_disclosure_scope。
原始事实是否真实、控制者是否有权代表所有来源主体，属于导入证据验证责任，本函数不证明。

## 3. 接受新消息时的检查

1. chat 的 source_refs 和 provenance.source_id 集合必须完全相同，两边都不能重复。
2. 每条声明必须与可信授权记录中的完整 Source 精确一致；不能升级来源种类、替换主体或
   扩张原始披露范围。无权、未知、跨实例、已撤销、已过期统一 permission_denied。
3. 发送者必须在 publishers 中且仍能读取来源。
4. 所需明文读者 = 消息 audience 与 Scope.privacy_model.visible_to 的并集。
5. 对每一条来源分别检查所需读者集合。多个来源取权限交集，不是把允许读者相加。
6. 成功后冻结 source_id → revision，与事件、成员代次和回执一并提交。

第 4 点是这次明确的设计选择：私聊 recipient 只有玩家，也不代表游戏端和明文 Relay
看不到正文。如果来源只允许玩家和伙伴阅读，就不应通过会暴露给游戏端的通道发送。
若需要真正的端到端私密通道，应独立设计，不给当前明文 Relay 虚构 E2EE 保证。

**必须先在发送端做披露检查，再由接收端复核。** 接收端已经拿到正文后拒绝入账，
不能撤销已经发生的网络披露。本次 harness 验证的是接收、入账和后续投递边界；
不证明恶意发送方不会先发送，也不证明真实发送适配器已经正确执行预检。

## 4. 执行顺序与原子提交

```text
bounded UTF-8 bytes
  → strict codec + OperationRequest schema
  → fixed fixture credential + role/lane
  → current Grant / session / generation / transport / device
  → session/version/sender binding + negotiated size limit
  → message ID + complete Envelope digest lookup
      duplicate: original receipt only, no new event and no lease renewal
      fresh: extensions → audience → source authorization → bounded capacity
  → stage receipt + event + membership/source revisions + lease
  → validate reply and encode bytes
  → commit the complete memory snapshot
  → return bytes (or simulate lost reply)
```

`RLock` 串行化提交、来源撤销和投递检查；内存暂存副本通过单次 state 替换提交。
这只是单进程参考事务，不证明磁盘断电恢复、数据库隔离或跨进程 fencing。
测试夹具管理方法不是公开 API，不允许将它们当作无需授权的撤销入口。

固定限制：最多 64 个事件，不驱逐去重记录；现有两个测试收紧型处理器见
[后续装配](PIPELINE_AND_CONSUMER.md)，对不能执行的已选策略扩展拒绝。
自然语言剧透/主动发言策略判断不在本模型范围，不能把结构检查冒充行为策略合规。
成功回复实际经过 schema 和编码；异常直接交给测试驱动，不声称已实现完整 HTTP 错误绑定。

## 5. 故障、撤销及旧回执

| 情况 | 本次断言 |
| --- | --- |
| commit 前故障 | 回执、事件、序号、租约都不改变；原请求可首次成功 |
| commit 后响应丢失 | 相同消息重试返回原收据；新 transport request_id 可以改变；不重复事件/续租 |
| 同消息 ID 改正文 | id_conflict，不覆盖原记录 |
| 来源在接受后撤销 | 停止未投递事件；旧收据仍能恢复，收据不携带正文 |
| Grant 撤销或控制代次失效 | 连旧写入收据重放也不能绕过当前身份/写权限检查 |
| 成员退出重加 | 新 incarnation 不恢复旧事件 |
| 来源被重新激活但 revision 改变 | 保守停止旧事件，不把重新授权当作恢复旧投递资格 |
| 来源到期 | 接受和投递都检查；期限边界拒绝 |

撤销不意味着删除已经交付给收件人的内容或 LLM 已有记忆；真实删除仍走隐私请求及回执。
投递检查的线性化点是受锁保护的交付快照。真正网络发送与撤销的排序需要输出端口兑现；
不能把返回 Python 列表声称为现实网络已阻止在途数据。

## 6. 已执行测试与未证明项

[test_design_chat_harness.py](../../tests/test_design_chat_harness.py) 包含 17 个测试方法：
来源伪造、未知/撤销/到期、跨会话/实例、发布者限制、引用不匹配、读者交集、游戏/Relay
明文可见方、丢包重试、提交回滚、成员代次与来源修订，以及正常 bytes/响应闭环。
其中一个方法枚举 accept/revoke/deliver 的全部 6 个顺序；它不是任意并发系统的形式证明。

明确保留一个负能力示例：空 source_refs 与空 provenance 可以发送普通聊天。
因此，即使检查通过也不能证明正文没有暗中引用未声明来源；检测自然语言来源和模型
记忆泄漏不属于本协议字段校验能力。不能向人工复核者隐藏这个边界。

## 7. 人工复核的明确选择

1. 是否接受把所有 declared plaintext observers 都纳入来源披露范围，而不仅检查 recipients。
2. 是否接受当前来源授权只缩权，扩张范围必须另立新授权的保守边界。
3. 是否接受来源任何 revision 变化都暂停旧事件，牺牲少量可用性避免恢复越权。
4. 是否保留来源错误统一拒绝，避免探测其他会话来源存在性。

这些是已实现的工作草案默认值，不等同于用户已最终批准，也不阻止后续按人工复核结果调整。
