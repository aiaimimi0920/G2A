# 操作字段契约与使用规则

状态：下一版工作草案的结构契约。不是生产 wire 版本，不升级旧 `0.1.0-dev`。
规范入口为 [操作与错误目录](OPERATION_DIRECTORY.md)、[机器目录](operations.json) 和
[JSON Schema](contracts.schema.json)。三者由 [contracts.py](contracts.py) 生成。

## 1. 如何读取与执行契约

每个操作有固定的名称、验证后的角色、入口、能力、重试族、输入类型、成功输出类型和
语义条件。所有标准对象默认 `additionalProperties=false`，可缺失字段不因此接受 null。
schema `$defs` 是字段权威定义；`?` 只在 Python 声明源中表示可选，不是 wire 字段名。

顺序必须为：限制原始字节 → [严格 codec](WIRE_CONTRACT.md) → 操作 schema → 验证传输与身份 →
角色/入口/能力 → 主体与对象关系 → 期限/revision/状态 → 原子去重与状态变化。
不能把 `validate_request` 的成功理解为该请求已经授权、被接受或执行。
`contract_checks.py` 仅实现结构及有限关系检查；身份/状态/世界效果仍按伪代码端口兑现。

`Version` 保持非空有界字符串，是为了容纳协商选定的精确版本，不以字符串格式推断兼容。
测试使用 `fixture-only`，不注册或发布此版本；部署时必须检查支持集合与 Scope 中的版本。
ID 字段本草案固定为 1–128 个 ASCII 字母/数字/`._~-`，首字符为字母或数字。
Principal 的 issuer/subject 是独立有界字符串，不应用上述 ID 格式或擅自归一化。

schema 中长度是 Unicode 标量数量；codec 还限制 UTF-8 字节数，两项同时满足。
整个 schema 只使用本地 `$defs` 引用，校验不访问网络。旧 schema 与本文件没有自动转换关系。

## 2. 入口、角色与秘密

| lane | 用途 | 约束 |
| --- | --- | --- |
| control | 玩家/伙伴接入、审批、恢复与控制查询 | 验证原主体和目标受众；不能由伙伴自批 |
| data | 当前伙伴写权、事件与心跳 | transport_epoch、generation、租约、Grant、ready 必须有效 |
| results | 已批准结果只读 | 独立读权/撤销/保留期，不依赖写权仍有效 |
| management | 游戏及已登记执行器 | 不映射到公开伙伴入口或 Relay 内层 |
| local | Launcher、资源、设备适配器 | 专用端口，不是可通过公网请求任意执行的 API |
| privacy | 实际数据控制者的请求/查询 | 验证来源主体权与独立受众，不从游戏任意跨域代理 |
| relay | 已配对 Relay 外层 | 内外层分别验证；外层角色不能代替内层权限 |

`session.close` 和 `permission.revoke` 的 game 角色只能从 management 进入；目录中的
control 是玩家/伙伴路径，不代表向公网开放 game token。验证角色由可信适配器产生，
不能从 Principal.kind 或 payload 自报字段直接填入。

SessionView、TransferView、OfferView、OperationView、PublicDescriptor 均不含凭据。
只有专门的邀请赎领响应和 ControlDelivery 可携带对应接收者秘密，必须满足认证、受众、
设备、当前代次、ready、未撤销条件。Secret 的字符串 schema 只是结构约束，不证明熵或有效性。
Grant/完整内部 Session/原始票据存储不能直接 JSON dump 成公开视图。

`proof_ref`/`decision_ref` 是可信适配器中已验证、受众绑定、有期限的记录引用，不是“知道一个 ID
就有权”。例如 session.join 还需要认证适配器验证 invitation credential；其秘密不是以
invitation_id 代替，也不写入普通 payload/log。具体 HTTP/IPC 凭据承载属于绑定适配器契约。

## 3. 重试族与响应

- `read`：读取时重新检查授权；相同请求可看到较新状态，不承诺冻结结果，不续租。
- `control`：按主体/受众/operation/request_id 保存 OperationReceipt；相同内容复用结果，
  不同内容冲突；长事务继续同一 saga，不能重复升代、启动或批准。
- `lease`：request_id 就是 heartbeat fresh_nonce / events poll_nonce；保存内容摘要和原响应，
  重试不重复续租，相同 nonce 改内容拒绝。读取历史缺口失败也不续租。
- `message`：业务去重使用 Envelope.id，外层 request_id 只关联本次传输；玩家转发使用
  payload.envelope。相同业务 ID 不再产生世界效果，取消消息有自己的 ID。
- `relay`：按 mailbox、外层主体、RelayCall.relay_request_id 去重；原 deadline 不延长；
  内层仍保留原 OperationRequest 和 Envelope.id，禁止用新业务 ID 修复未知结果。

线上 OperationReply 仍为 `{request_id,result}` 或 `{request_id,error}`，二者恰选一。
schema 的 ReplyEnvelope 是测试/校验用封装，额外 operation 来自服务器已保存请求，
**不得因此要求客户端在线上响应增加 operation 字段**。`validate_reply` 检查这层映射。
完全无法解析合法 request_id 的 HTTP 边界错误不伪造 OperationReply，可用无敏感信息的
HTTP 错误拒绝；客户端按未取得语义回执处理，不能推断既有业务动作未发生。

### operation.get 的回执与业务状态

固定装配范围和逐项查询权限见 [回执汇总证明](OPERATION_STATUS_PROOF.md)。控制/lease 族的
original_request_id 是原外层 request_id；action.request/cancel 则使用 Envelope.id，不能
把仅用于传输关联的 ID 变成第二个业务键。OperationView.request_id 回显这个查询键，
OperationReply.request_id 仍回显本次查询请求 ID。

OperationView.state 表示原请求的提交/流程结果，不表示对象现在仍可用或世界效果已成功。
已 ready 的 join/resume/handoff 之后关闭仍为 done；未 ready 就失败才为 failed。动作的
done 是受理/取消收据完成，实际 pending/unknown/partial 等在可选 ActionResult 中报告。
动作 ID、Receipt 和结果均重验当前结果读权、保留期和原成员代次；无权不能只泄露 ID。
session.heartbeat/close 附带原响应快照，join/resume 附带当前会话视图；均不赋予控制权。
未知/无权的查询拒绝不证明未接受；不通过查询重新执行、签发许可或跨域读取私有回执。

## 4. 补齐两个原先未命名的控制入口

### action.confirm

高风险一次确认不再只以“外部帮助函数”出现。玩家通过可信交互提交 session、预先选定
action_request_id、action、参数摘要、能力定义摘要、到期时间与 decision_ref；权威端先
核对有效 Scope/能力，再保存一次 confirmation_id。该 ID 仅对上述元组有效。
动作接受时原子消费它；重复动作走业务去重，不消费第二次。确认不创建 ActionRecord、
不领取 ticket、不产生世界效果。拒绝用户操作由可信 UI 结束，不伪造通过确认的结果。

### session.claim_control

handoff 的玩家只接收 TransferView；目标伙伴不能读取玩家的 operation.get 私有回执。
目标伙伴以 fresh 身份、目标设备证明、session_id/transfer_id/target_device 赎领已保存的
ControlDelivery。要求 transfer.ready、当前 generation、active/ready 和 Grant 有效。
同请求仅重放该代秘密；后续升代/关闭不提供秘密。这个操作不再升代，也不重新执行转移。
未 ready 时返回不含秘密的 SecretStatus/pending；后续以原控制请求继续观察同一操作，
不重新升代。已完成但不能再回放秘密时返回 completed_without_secret，不伪造新凭据。

## 5. 字段命名与适配规则

伪代码中的语义短名在字段契约中明确映射：

| 伪代码短名 | 结构契约 | 说明 |
| --- | --- | --- |
| result_retention / event_retention / lease_period / resume_window | 对应 `_ms` 字段 | 非负毫秒；租约和回执保留要求正值 |
| maximum_duration | maximum_duration_ms | 动作定义的时长上限 |
| nonce / fresh_nonce / poll_nonce | 外层 request_id | Relay pull 仍独立保留 pull_nonce |
| admission_ready | SessionView.ready | 内部状态投影；closed 必为 false |
| action ID / 原 request_id | action_id 或 action_request_id | 不与外层 request_id 混淆；取消 payload.request_id 保持原动作 ID |
| asset format compatibility | `{profile,revision,properties}` | 只由双方支持的精确资源格式 profile 解释 |
| privacy.receipt | 本人回执查询操作 | 不是由请求方写入一个自称存储方的删除证明 |

Policy 的本版核心键仅 spoilers、proactive_chat 和 extensions；其他行为键必须通过已协商
扩展定义，不默许任意标准键。用户 false 覆盖默认值，不改变动作或受众。
资源 profile 的 properties 是格式专用开放点，不是绕过 parser/兼容检查的任意权限对象。
未知 profile 拒绝；本轮没有宣称已标准化或验证真实骨骼、动画和多引擎资源格式。

## 6. 动作值 schema 的有限配置

ActionDefinition 必须声明 `schema_profile=g2a-value-schema-1`。这是 JSON Schema 的受限
数据子集：单一 type（null/boolean/string/integer/array/object）、enum/const、对象
properties/required/additionalProperties=false、数组 items/minItems/maxItems、字符串
minLength/maxLength、整数 minimum/maximum。禁止 `$ref`、远程解析、正则、组合器与自定义代码。

对象三个结构关键字全部必需；数组必须有 items 与 maxItems；字符串必须有 maxLength。
参数根必须为 object；结果根可以是任意允许类型。所有界限仍受 codec/已批准限额约束，
schema 中更大的数值不提升硬上限。required 必须指向已定义字段，min<=max，enum/const
必须满足自身约束。字段类型不适用的关键字拒绝，而非静默忽略。
真实动作参数/结果在使用此子集校验后仍要检查 Scope、当前能力和世界条件。

## 7. 错误目录与时序

错误目录固定 code/category/retry/outcome/HTTP 的组合，`validate_error` 检查组合，不能只
各自命中 enum 就通过。Error.details 只允许已定义安全字段；不能塞原始 Exception、
Authorization、任意内存内容或堆栈。history_gap 的 snapshot/cursor/action refs 再按读权过滤。
snapshot 现使用 RecoverySnapshot，不再仅为 SessionView；session.snapshot 也返回同一
结构。next_cursor 和 unresolved_actions 必须与该快照一致，详见
[事件与业务快照恢复](EVENT_RECOVERY_PROOF.md)。这是设计草案修订，不改变旧 SDK。

outcome 说明**本次操作请求**的接收知识，不否定其他路径或历史动作。result_expired /
result_unavailable 不能解释成原动作未执行；unknown 不得变成 failed。已提交后的回包故障
统一使用 unknown，而不是复用提交前 resource_limit 的 not_accepted。内部失败无法确认
事务提交时返回 internal_failure/unknown；不得凭异常类型猜状态已回滚。

同 code 的 retry 不是自动化授权：same_request 仅在主体仍有效、期限内和退避允许时重发
原内容；after_reauth 不允许改用另一身份领取原结果；after_renegotiate 不是自动同意新 Scope。
模型字面错误已登记映射，其他端口的提交知识与收敛见 [端口失败矩阵](PORT_FAILURES.md)；
未登记内部错误保守映射 internal_failure，具体实现新增异常仍须补映射和相应测试，
不能把兜底当作真实适配器已经通过故障注入。

## 8. 当前证据与尚未闭合部分

38 个操作已有输入/成功输出 schema，能力依赖图、路由角色和 58 个边界错误已登记。
测试对全部操作生成结构见证并做必需字段删除/未知字段注入；另外有独立字节 fixture、
闭会凭据泄露/动作结果关系/Relay 越权/动作 schema 负例。能力依赖全枚举 2^11 个集合，
不代表所有业务、故障与时间交错被穷尽。

后续新增的逐操作设计推演见 [状态轨迹](STATE_TRACES.md)，跨对象与错误知识见
[关系契约](RELATION_CONTRACT.md)。仍须汇总符合性声明和最终审计；schema 通过
不是对恶意输入资源安全和真实身份适配器的认证。隐私存储处理允许 pending 回执，
不得为满足完成类型而伪造 done；资源验证回执同时绑定 parser_revision 和 policy_revision。
