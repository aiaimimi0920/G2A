# 外部端口失败、提交知识与收敛矩阵

本文为伪代码必须兑现的端口责任，不是生产适配器的测试成绩。端口可以用 fixture 实现，
但不能把所有失败固定返回成功。错误映射依据事务/效果事实，不凭异常类型猜回滚。
`pre`=权威层证明确未接受本请求，`post`=已接受，`?`=无法确定提交或效果。

| 端口 | 故障注入位置与已知事实 | 边界/后态 | 重试、清理及禁止事项 |
| --- | --- | --- | --- |
| Identity.verify / endpoint | pre：签发者、受众、角色、期限或委托无效 | unauthenticated 或 permission_denied；无 Grant/动作 | 拒绝前不查询并泄露别人的收据；重新验证不能换主体领取原结果 |
| PlayerSeat.verify | pre：引用缺失/畸形、跨游戏/Scope/主体、过期或成员代次变化 | permission_denied；无新事件/收据/续租 | [玩家转发证据](PLAYER_FORWARD_PROOF.md)：当前游戏管理身份与席位分别核验；换有效证明仅可读原非正文收据，真实输入真实性另验 |
| Consent.verify_decision | pre：nonce 重放且内容不同、摘要不符、非可信玩家交互 | id_conflict / approval_stale / consent_required | 普通聊天不算决定；同内容已提交的重复先读原回执，不再次签许可 |
| Provider.complete | pre：state/nonce/受众不匹配或回调过期 | unauthenticated / offer_expired；不创建可批准 offer | 重试关联同一服务端事务，不接受新 return URL，不在批准后换 agent |
| Store.atomic | pre：明确回滚，未发布 outbox/秘密 | temporarily_unavailable/not_accepted | 原 key 重试；不保留半个 action 或消费一半的邀请 |
| Store.atomic | ?：提交应答丢失，不能证明已回滚 | internal_failure/unknown；状态由原账本查询决定 | 相同主体/ID/内容查证；不能新 ID 重做效果，不能清空账本“恢复” |
| Clock.now | pre：回退或不能证明有效期 | temporarily_unavailable；停止新授权/续租/恢复 | 不采用客户端时间延长期限；已有未知执行事实不能被重写为未执行 |
| Secrets.issue/verify/revoke | pre：签发/存储失败或校验失败 | 未提交则回滚原事务；无有效秘密或 unauthenticated | 秘密存储与状态关联；未 ready 不交付；关闭后读权与写权分别处理 |
| Secrets.issue/verify/revoke | post：凭据回包丢失或后续代次变化 | 原回执的当前代秘密，或 SecretStatus/completed_without_secret | 同请求不再升代；不在旧回执中替换成其他设备的新秘密 |
| AgentController slot | pre：无 multi-session 且已有未过期活动/准备 slot | session_conflict；不创建第二 slot | 失败释放本 offer 的 slot；重启先核实旧期限，不把单游戏锁说成全厂商锁 |
| Launcher.start | pre：无单独启动许可、注册应用不匹配 | consent_required / permission_denied；不启动 | 不拼接外部命令；接入许可不隐含启动许可 |
| Launcher.start | post/?：消费许可后启动失败、结果不明或回包丢失 | 确知失败 launch_failed/accepted 并撤未用 Grant；未知 internal_failure/unknown | [假端口证据](LAUNCH_PROOF.md)：查询同启动事务/当前绑定进程；历史记录不足，不自动再启动一个实例；OS 仍未实测 |
| ResourceTransport | pre/post：来源、重定向、实际连接目标、字节数或摘要不符 | resource_policy_denied / resource_integrity_error；admission_failed 后闭会 | 清理本次临时资源、释放本次占用；不携带会话 secret 下载，不静默换头像 |
| Archive.inspect / Parser.open | post：路径逃逸、解压超限、脚本、格式不兼容或解析异常 | 资源验证失败，缓存不标 verified，admission 不 ready | 隔离解析；按批准策略拒绝；不能以 fixture hash 通过宣称真实 parser 安全 |
| Cache.publish | post/?：发布失败或崩溃，验证回执/索引不完整 | 不可见或待重新验证；不得当已验证资源复用 | 同 content/parser/policy revision 验证；只有原子 verified 条目可读 |
| Device.verify / Renderer.apply | pre：设备归属/条款无效；post：CAS 冲突或应用失败 | permission_denied / presentation_unavailable；失败撤本次 tentative 占用 | 保留最新 baseline/manual_revision；不能用旧会话快照覆盖手动操作 |
| Presentation release/lease | post/?：release ACK 丢失、乱序 acquire、网络断开 | 幂等 release+tombstone；无可信 ACK 时等待旧租约到期 | 新设备不提前获取；墓碑覆盖旧证明期限，迟到 acquire 不复活占用 |
| WorldGate journaled | post：效果与事实同事务成功但返回丢失 | 原 action unknown，查询原 effect key 后恢复实际结果 | 不换 ticket/step 重做；撤权阻止新效果，不抹除既有事实 |
| WorldGate fenced-nonatomic | ?：已持久消耗 step 后引擎结果不明 | unknown/undetermined；禁止再次执行该 step | 没有可信事实就保持 unknown；不能承诺 exactly-once，也不伪造 none |
| Executor.commit_result | post：原可信 fact 迟到；或报告与已记录事实冲突 | 允许原 ticket 结算；矛盾 execution_conflict | 旧代 ticket 不获得新写权；已发生 partial 不被后续拒绝覆盖成 none |
| Outbox.deliver | post：通知发送失败、重复或 ACK 丢失 | 业务接受状态不回滚；同 event/operation 重试通知 | outbox 与业务同事务；不新建 ActionRecord；关闭通知失败按本地停止/租约收敛 |
| MemoryStore.apply | post/?：尚在处理、派发无回执、部分副本不可删、结果提交失败 | cutoff 不回退；未知 pending，有可信证据才 done/partial/denied；共享/外部/保留副本列例外 | [隐私假端口证据](PRIVACY_PROOF.md)：同 provider operation 查证，不换 ID 重删；authority 回滚不恢复副本，真实存储仍未实测 |
| Relay queue/pull/reply | pre：queued 已原子作废且未领取 | relay_not_dispatched/not_accepted，仅证明该路径 | 不否定另一连接已提交相同业务 ID |
| Relay queue/pull/reply | post/?：已 claimed、回复丢失、重启丢账本 | outcome_unknown / request_gone；无持久账本则废旧 route | claimed 不自动入队；游戏按原内层回执查询；重配不延长旧 Grant |
| Maintenance/recovery | post：会话/动作/邀请到期或保留期回收 | 闭会/取消/unknown/expired 的已提交维护状态 | 不因后续拒绝回滚维护；不删业务记忆；旧 epoch 不建空账本冒充恢复 |

矩阵覆盖 CONTROL 的身份/批准/启动/提供者/存储/时钟/秘密/呈现/outbox 端口，DATA 的
WorldGate/执行器/记忆/维护，PRESENTATION 的设备/网络/归档/解析/缓存，以及 Relay 队列。
具体生产实现如果不能提供这些保证，应拒绝要求该能力的接入或明确不声明该能力，不能
改变核心授权语义后仍声称符合。

## 提交知识如何进入返回值

```text
on precondition failure before accepting operation:
  rollback only new request writes
  return boundary_error(code, knowledge=not_accepted)

on external saga failure after accepted operation:
  persist failure/current outcome and idempotent cleanup outbox
  return boundary_error(code, knowledge=accepted)

on lost commit acknowledgement or uncertain world effect:
  persist/retrieve unknown outcome if possible
  return boundary_error(code, knowledge=unknown)
  never turn timeout into a new effect request
```

上面的知识由存储/效果端口给出，不由客户端选择。效果已经发生但返回 JSON 序列化失败时，
同样是 unknown 或可查询的已接受结果，不能退回 invalid_message/not_accepted。
固定目录无法识别的内部错误保守映射 internal_failure/unknown，日志只记录受限诊断，
不能把 Exception 文本塞入公开 details。

## 证据级别

此表是对每类端口故障的设计审查，自动证据来自错误映射、状态接缝、资源图、身份/范围
关系、T01–T25 和 M01–M10；并非每一个真实端口都有故障注入程序。按照当前允许伪代码
的范围，这里完成失败契约；未来实现端仍须提供对应真实证据才能声明 adapter/deployment。
