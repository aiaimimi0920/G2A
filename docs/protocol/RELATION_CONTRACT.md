# 跨对象关系、错误映射与状态接缝

本文件补充 [字段契约](OPERATION_CONTRACT.md)。JSON 结构合法不代表身份、授权和状态关系合法。
参考检查见 [relations.py](relations.py)，独立手写输入见 [fixtures.py](fixtures.py)。
所有输入必须来自同一权威快照；把一组自洽的伪造 JSON 传入检查器并不能获得授权。

## 1. 冻结 Scope 必须包含的批准条件

本轮跨对象复核发现，原逻辑短表未完整带入动作定义摘要、扩展选择和创建时点。因此补齐：

- `approved_action_digests`：键恰好对应 action_ids，值是完整 ActionDefinition 的
  `action-definition` 域摘要。只固定动作名称不足以固定其权限含义。
- `extensions`：固定启用的扩展及精确版本/值；required 在两端取逻辑或。
  只声明扩展机制，却不把选择放入批准摘要，不能满足不可变 Scope。
- `created_at`：固定授权时长的起算点。验证 expires_at 时不能每次用新的 now 加允许时长，
  否则旧申请被延后读取可能悄悄获得更长授权。created_at/expires_at 都进入 scope_digest。
- Descriptor 补 policy_defaults、ledger_durabilities；Requested 补双方可接受的绑定、
  身份配置、隐私模型、companion_defaults 和扩展。不能凭 Scope 自称双方已支持某项保证。

自动规则比较排除本次 created_at 和 expires_at 两个绝对时间，保留明确的最大授权时长。
这只影响规则匹配，不从实际 Scope/Grant 摘要删除时间。该选择修正了增加 created_at 后
可能让自动规则永不复用的问题；不能借此排除身份、动作定义摘要或隐私范围。

## 2. 校验分层与责任

| 检查 | 必须满足 | 失败不应导致 |
| --- | --- | --- |
| validate_descriptor | game 身份类型、支持/必需能力、动作 ID 唯一、动作值 schema 合法 | 自动启用未声明能力 |
| validate_scope | 双方身份/实例/revision/版本/绑定/信任/能力；动作和情境子集；受众经验证；隐私与策略；期限/限额 | 刷新 now 后延长原期限，或仅凭 action ID 复用同意 |
| validate_grant | 原 Scope、scope_digest、原玩家批准、active、created_at <= now < expires_at | 把另一授权、未到起始时点或失效授权用于新会话 |
| validate_session_write | 原 Grant、active/ready、租约、实例 epoch、传输 epoch、generation、设备及原伙伴 | 用结果读权或旧设备凭据恢复写权 |
| validate_envelope_audience | Envelope 与会话/认证发送者一致；聊天字段符合 Chat，发送者为批准范围内的当前成员且有频道资格；受众在冻结范围与当前成员中，团队 revision 正确 | 把认证成功等同于有权发言，或仅凭客户端自报 sender/受众投递 |
| SessionHarness._player_seat | 固定游戏管理身份另行核验；可信席位绑定原 Scope、instance/session、玩家和当前成员 revision/incarnation、有效期；重复请求也重验 | 游戏冒充伙伴、猜引用取得玩家权、旧席位重入或绕过去重；不证明真人实际输入正文 |
| can_deliver | 冻结成员代次与当前代次一致且仍有读权 | 同名主体退出重加后恢复旧消息资格 |
| validate_result_read | 原主体解析出的独立读授权、session/action 范围、撤销 revision 和保留期 | 关闭后把读结果当续租或执行授权 |
| validate_manifest_closure | 所有依赖的来源/大小/深度/数量/内容标识/精确格式 profile | 主资源可信就自动信任任意依赖 |

validate_scope 用于创建/批准/首次加入，**不能**在每个活动会话消息上重新要求完整
descriptor_revision 相等。活动期能力缩减使用原批准摘要与当前能力的交集，成员变更使用
成员 revision/代次；改变身份/信任/隐私等核心条件则关闭并重新批准。

Scope 中 features/action_ids/context_categories 按字符串排序，audiences 按 canonical
对象字节排序，拒绝重复；创建后保留原快照。Policy 核心键按 companion defaults → game
defaults → 用户显式键覆盖，false 不当作缺失。策略扩展需要精确协商，不因默认字典有值就启用。

limits 中容量与保留能力不能超过双方声明值；result_retention_ms 与对应 limit 一致。
回执保留至少覆盖 `expires_at-created_at+resume_window_ms`，不在重试窗口中淘汰去重记录。
未协商 resume 时 resume_window_ms=0；未协商 multi-session 时 session_count=1。
这里的数值关系不证明实现确实提供了磁盘持久化或存储容量。

## 3. 资源关系检查的边界

声明阶段逐个访问依赖节点，检测活动路径重复 ID、同 ID 冲突、重复内容标识、总大小与深度。
每个 locator 必须是无用户凭据/fragment 的 HTTPS URL，origin 属于本节点声明且在已批准
来源集合中；端口 443 归并到规范 origin。未知资源 compatibility profile/revision 拒绝。

共享依赖按唯一 asset_id 计数量和字节，但深度按每条根到叶路径计算，根深度为 1。
缓存节点时保存完整子树高度，再次引用须验证 `当前深度 + 子树高度 - 1 <= max_depth`。
不得因为节点曾从较浅路径访问过就跳过较深路径检查；交换兄弟依赖的顺序不能改变接受结果。

这只是下载前检查，**不证明** DNS/连接目标、重定向、实际字节、解压或 parser 安全。
ResourceTransport 仍须逐次固定并检查真实目标，Archive/Parser 仍执行隔离和限制；
allow_private_network=false 必须由连接端口兑现，不能由这里的 URL 字符串检查冒充。
预装形象仍需 Renderer 验证精确 ID/revision；格式名字相同不代表真实资源已加载。

## 4. 错误不能只按字符串翻译

[error_mapping.py](error_mapping.py) 为现有 FlowModel 的字面错误登记公开映射，同时接受
权威事务层给出的 `knowledge=not_accepted|accepted|unknown`。

| 情况 | 边界结果 |
| --- | --- |
| 接受前容量不足且事务确知未接受 | resource_limit / not_accepted |
| 已提交后才发现后续处理失败 | operation_failed / accepted，客户端查询原 outcome |
| 无法确认提交或效果事实 | internal_failure 或 outcome_unknown / unknown |
| Relay 已关闭但不知道是否领取 | request_gone / unknown |
| queued 已原子作废并有未领取证明 | relay_not_dispatched / not_accepted，仅对本转发路径有效 |
| 未登记的内部异常 | internal_failure / unknown，不回显异常字符串 |

例如 unproven_result 映射 execution_conflict，session_not_ready 映射 session_not_writable；
错误别名不自动代表回滚。即使上层捕获器误传 not_accepted，也不能把已知 outcome_unknown
降成未执行。没有事务证据时必须用 unknown，而不是根据 Exception 类名推测。

action.claim 对已领取/终态动作优先返回规定的 not_executable 成功状态；若某个执行边界
以拒绝返回，则使用 action_not_executable，不能签发第二个 ticket。
history_gap 的快照/游标/未解决动作必须先过滤权限后作为白名单 details 传入；普通错误
禁止携带这类快照。没有合法关联 ID 的解析错误仍走无敏感信息的 HTTP 边界拒绝。

AST 测试证明 FlowModel 当前所有字面错误已有目录或别名，不证明每个运行分支的提交知识
都已被实际故障注入。其他伪代码适配器的失败契约已在 [端口失败矩阵](PORT_FAILURES.md)
逐类核对；未来真实适配器必须提供新证据，不能用未知错误兜底掩盖未实现分支。

## 5. 实际修正的模型接缝

新增结果投影检查发现：FlowModel 在 executing 动作遇到 close/resume/handoff 时改变了
state=unknown，却遗留 effect=none。这与新 schema 和原语义不一致，会误导调用者认为
世界没有变化。现已同步设置 effect=undetermined；pending→cancelled 仍保持 none。

测试实际调用模型创建/批准/加入/接受/领取，再执行三种转换，把模型的 state/effect
投影到 ActionResult 校验。另有 pending 关闭的无效果反例。该接缝不是完整 wire adapter：
逻辑 tick、固定身份和内部记录仍不能冒充真实网络消息或生产认证。

本轮还包含独立手写 Scope/Grant/Session 输入，避免只用 schema 自动生成的结构见证
验证 schema 自己。新的跨对象检查与错误映射测试已执行；后续全操作状态追溯、统一
符合性入口与交叉审计现已补齐，见 [最终审计](FINAL_AUDIT.md)。

## 6. 反向审查发现的分层缺口

后续复核新增 4 个反例测试，修改前均实际失败（预期 ContractError 未抛出）：
未到 Scope.created_at 的写入、无频道资格/已退出的聊天发送者、缺失聊天字段的通用
Envelope，以及共享子树浅路径缓存导致的深路径漏检。修复在 relations.py，未改旧 SDK。

私聊发送者必须为该会话原玩家或原伙伴；团队聊天发送者必须在批准受众与当前成员交集中，
并遵守已协商 team 与当前 membership_revision。只验证 sender 等于已认证身份不够。
游戏发布情境不套用聊天成员规则：GameAuthority 可能不是聊天受众，仍由管理入口独立认证。
正例覆盖合法团队成员和非聊天成员的游戏情境来源，避免用一刀切的限制修复越权。

本函数仍不是完整入口：调用方须先做操作 schema、认证/路由及对应状态检查，并在同一事务
内冻结受众和提交；来源披露限制、动态能力、扩展处理也不能因为本函数返回成功而省略。
这些反例说明此前“交付形成”不等于分层装配无漏洞；完整 wire 到状态机的装配仍需单独证明。
