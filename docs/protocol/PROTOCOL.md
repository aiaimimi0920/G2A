# G2A 协议总设计：g2a-design-1

状态：可推演的下一版设计草案；不取代 `0.1.0-dev`。本文“必须/禁止”约束本草案模型，不声称现有 SDK 已实现。

## 1. 范围与设计选择

G2A 连接游戏世界与玩家的固定伙伴。双方可由不同厂商实现，可本地运行或云端运行；不依赖中心账号、统一 LLM、指定记忆存储或 Mot。游戏拥有世界事实、信息开放及动作执行权；玩家决定其伙伴接入及陪伴偏好；Agent 决定内部理解、规划与记忆实现，但不得超越授予它的权限。

本版对原 Q01–Q06 作出以下**草案选择**，以便不再停留在问题清单：

| 决策 | 选择 | 理由/代价 |
| --- | --- | --- |
| Q01 | 必需核心 + 显式可选能力；无动作、无桌面、无形象的伙伴可以符合核心 | 接入不应依赖特定呈现；需要协商和依赖校验 |
| Q02 | 分部署配置验证身份，不建立 G2A 全局账号中心 | 保持独立；各信任配置的适配器和互信关系必须明确 |
| Q03 | 范围绑定、可到期、可撤销授权；高风险动作可要求额外一次确认 | 避免全授权或逐次无差别弹窗；多对象撤销语义必须区分 |
| Q04 | 核心只承诺会话内去重和诚实的未知结果；持久恢复须显式协商 | 不虚构跨崩溃恰好一次；恢复能力需要持久账本和身份连续性 |
| Q05 | 桌面呈现和形象为可选能力；缺少能力是 absent，不是 false | 云端无需伪造桌面；要求形象的游戏可明确拒绝接入 |
| Q06 | 精确选择共同版本及扩展；关键未知项拒绝；可选未知扩展不启用 | 不把忽略安全字段当兼容；需要版本化描述和授权快照 |

不提供任意 NPC 接管、每帧渲染同步、模型内部统一、跨游戏世界回滚或对恶意端点的“保证不剧透”。规范定义可观察通信和权限，不声称控制别人脑内或数据库中的所有信息。

## 2. 角色与可信边界

| 角色/职责 | 权威与输入 | 不允许 |
| --- | --- | --- |
| GameAuthority | 验证游戏身份/玩家席位；发布情境、能力；验证并执行世界动作 | 以自报文本代替用户对伙伴的同意；把不知情玩家加入私聊 |
| Companion | 持有 Agent 身份，接收授权数据，主动交流/请求动作 | 自行批准申请、扩大 scope、以数据文本提升指令权限 |
| PlayerConsent | 通过可信交互确认玩家意图，拥有自己的偏好 | 替其他玩家批准记忆披露；授予游戏未开放的动作 |
| AccessAuthority | 为一个已验证游戏实例管理 offer/grant/invitation/session | 只凭客户端自报 sender/ID 认证；跨游戏转用令牌 |
| Provider | 托管游戏或伙伴，完成其控制域内身份验证与委托 | 被游戏随意指定后即自动获得用户凭据 |
| LocalLauncher | 验证本地软件身份并按明确启动许可唤起固定应用 | 从不可信 descriptor 拼接 shell 命令或执行路径 |
| Relay | 转发已配对双方的允许操作；本版按可信终点处理 | 获得 GameAuthority 管理令牌，扩大内层会话权力 |
| PresentationOwner | 管理一个设备上的呈现和用户操作 revision | 因旧会话退出覆盖更新的用户选择 |

职责可以由同一程序承担，合并不消除逻辑权限隔离。AccessAuthority 可与游戏同进程，不要求额外中心服务。云端、浏览器或本机认证适配器必须说明凭据持有者、验证方、受众及剩余风险。

### 信任配置

- `local-verified`：可信启动通道/OS IPC 适配器确认应用与玩家归属。仅有随机端口、进程 ID 或软件名称不符合该保证。
- `provider-verified`：TLS 验证远端，使用提供者既有、经验证的身份/委托流程，将玩家、伙伴、游戏受众和有效期绑定；不自行发明加密协议。
- `test-enrolled`：可信测试启动器固定登记身份，仅用于本地推演/实验，不能宣称抵御恶意本机进程。
- 直连或 relay 是传输拓扑，不是身份配置；身份可信不意味着伙伴可信遵守全部文本偏好。

端点必须同时接受所选身份配置，否则 `trust_profile_unsupported`。从强配置退到测试配置禁止静默发生。Relay 及游戏宿主可读经它们传递的消息；本版不声明 E2EE。需要不信任路由者的应用必须拒绝这个隐私范围，而不是偷偷改变 private 含义。

## 3. 能力分层与协商

能力名仅是草案中的逻辑标识，发布时须随精确 wire 版本冻结。

| 能力 | 核心/可选 | 保证与依赖 |
| --- | --- | --- |
| `core.session` | 必需 | 描述、协商、批准加入、退出、续租、状态查询、错误语义 |
| `core.events` | 必需 | 游戏情境、伙伴主动文本、显式受众、收据、有限事件历史、会话内去重 |
| `actions` | 可选 | 依赖核心；请求/取消/结果查询、动态能力版本、执行前校验 |
| `team` | 可选 | 依赖核心；多人身份映射、成员 revision、授权受众 |
| `avatar` | 可选 | 描述协商；资源交付可用双方已有的已验证资源或另协商 `assets` |
| `assets` | 可选 | 资源清单、格式/大小/完整性/许可声明、安全获取与本地验证；依赖 avatar |
| `presentation` | 可选 | 设备上覆盖/共存/恢复；不要求伙伴核心在同一设备 |
| `resume` | 可选 | 持久会话 epoch、去重账本、动作/结果保留、认证恢复和旧控制权隔离 |
| `multi-session` | 可选 | 同一伙伴并发会话；无此能力时第二次加入明确冲突，不自动踢掉第一会话 |
| `handoff` | 可选 | 依赖 resume；显式同意后的设备控制权转移与 fencing，不复制无限控制权 |
| `privacy-request` | 可选 | 请求停止后续使用/删除已存副本的回执；不构成不可验证的全局删除证明 |

最低伙伴必须理解会话、允许的文本/情境、身份/受众、错误/退出；不要求执行游戏动作、具备身体、窗口或内部长期记忆。游戏可在 descriptor.required_features 中要求 avatar/actions 等，缺少时拒绝当前接入，但不能宣称对方不符合 G2A 核心。

协商：在双方精确支持版本的交集中，选择双方策略允许的最高版本；预发布版本只精确匹配，不从版本字符串猜兼容。能力取交集并验证依赖，required_features 必须全部满足。控制面必须把最终版本、绑定、身份配置、能力、限制、隐私范围写入待批准快照。无交集即拒绝，不自动回退到旧 HTTP 接口。

### 扩展

标准字段严格校验，未知标准字段拒绝。扩展仅允许放在 `extensions` 下，以反向域名命名空间及精确版本标识；声明 `required=true` 的未知扩展在授权前拒绝，其他未知扩展不启用。扩展不能覆盖核心身份、权限或状态含义；改变这些含义需新协议版本。禁止把敏感字段藏入任意扩展绕过同意。

活动期的支持、批准和本次启用必须分别检查，精确规则见
[协议研究与活动扩展决策](PROTOCOL_RESEARCH.md) §3。当前扩展 value 为冻结配置；
数据操作扩展只位于 Envelope，外层 OperationRequest.extensions 必须为空，防止绕过
message 摘要。无扩展的核心止损操作不得依赖扩展处理器可用性，原授权检查不豁免。

## 4. 规范对象与作用域

所有对象为有界 UTF-8 结构；序列化规则见 §15。以下是逻辑类型，不是现有 JSON Schema 的别名。

```text
Principal = {issuer, subject, kind: player|agent|game|service}
  // 身份唯一键为整个三元组；display_name 不参与认证
Instance = {game: Principal, instance_id, epoch}
Descriptor = {descriptor_id, revision, instance, supported_versions[],
  bindings[], trust_profiles[], ledger_durabilities[], supported_features[], required_features[],
  privacy_model, context_categories[], actions[], avatar_requirements?,
  presentation_requirements?, policy_defaults, limits, extensions}
Binding = {kind, endpoint, peer_identity, relay_identity?}
Scope = {player, agent, instance, version, binding, trust_profile, features[],
  descriptor_revision, action_ids[], approved_action_digests, context_categories[], audiences[],
  effective_policy, avatar_selection?, resource_policy?, presentation_terms?, privacy_model,
  result_retention, ledger_durability: volatile|durable, limits, created_at, expires_at, extensions}
Offer = {offer_id, applicant, immutable_scope, scope_digest, decision_deadline,
  launch_required, state: pending|approved|denied|expired|stale, grant_id?}
Grant = {grant_id, scope, scope_digest, approver, consent_evidence,
  revision, state: active|revoked|expired, expires_at}
Invitation = {invitation_id, grant_id, grant_revision, join_intent_digest,
  player, agent, audience_instance, expires_at, state: issued|consumed|revoked,
  consumed_session_id?, consumed_intent_digest?}
JoinIntent = {scope_digest, selected_device?, presentation_observation?}
Session = {session_id, scope, grant_id, state: active|closed, close_reason?,
  instance_epoch, transport_epoch, control_generation, controller_device?, lease_deadline,
  capabilities_revision, membership_revision, sequence,
  result_read_handle, result_read_until, resume_until?}
Credential = {opaque_secret}  // 服务端映射到 principal/audience/role/generation/expiry
Envelope = {version, session_id, id, type, correlation_id?, sender, audience[],
  expected_capabilities_revision?, expected_membership_revision?, payload, extensions}
Receipt = {id, accepted_at, record_digest, outcome_ref?, duplicate}
Event = {sequence, envelope, frozen_audience[], created_at}
ActionRecord = {request_id, session_id, actor, capability, arguments_digest,
  state: pending|executing|succeeded|failed|cancelled|unknown,
  authorization_revision, execution_ticket?, cancel_requested,
  effect: none|partial|committed|undetermined, result?, result_revision,
  query_until}
Error = {code, category, retry: never|same_request|after_reauth|after_renegotiate,
  request_id?, retry_after_ms?, outcome: not_accepted|accepted|unknown, details}
```

所有认证角色来自验证凭据，不来自 Envelope.sender；sender 必须与认证身份及服务端代理玩家映射匹配。principal 不具全局自然人唯一性；跨提供者身份合并需玩家验证两端控制权及显式关联，不靠相同名字/邮箱自动合并。伙伴历史连续性可以由提供者证明映射，但不自动搬运旧记忆或旧授权。

ID：offer/grant/invitation/session 全局不可预测；message 去重键为 `(session_id, authenticated_principal, id)`；action ID 就是被接受的 action.request ID，不另造不相关执行 ID；correlation_id 只用于关联，不授予权限。执行凭证另有一次性 ticket 和 fencing generation。只按“相同字符串 ID”跨玩家或会话复用结果是错误。

## 5. 通用不变量

- I01：未验证身份不能产生用户批准、邀请、有效会话或世界动作。
- I02：实际授权不超过游戏当前能力、有效 Grant、用户允许范围的交集；发现、形象和偏好均不能扩权。
- I03：批准绑定不可变完整 Scope；任何安全相关变化必须使待加入流程 stale，不能重用旧 scope_digest。
- I04：同一去重键+相同内容只接收一次；同键不同内容必须冲突；认证失败者不能探测旧收据。
- I05：接收收据不是执行完成；无法证明世界效果时返回 unknown，不自动发新动作 ID。
- I06：数据投递同时满足原冻结受众与当前授权，不能借分页或新队员身份暴露旧数据。
- I07：失效/关闭/旧 epoch 或旧 generation 凭据不能恢复行动权；结果读取权限不含会话写权限。
- I08：客户端断线、关闭或租约过期只释放自己的呈现占用，不覆盖新的用户意图或其他活动会话。
- I09：上下文/玩家文字/资源元数据是输入数据，不是提升角色、修改系统指令或跳过审批的依据。
- I10：状态变更、去重收据和事件发布必须具有同一原子提交边界；世界副作用另由执行器保证或明确降为 unknown。

## 6. 操作目录与权限

描述可以公开一个无敏感数据的最小版本；完整能力/参与者/授权范围只在身份验证后提供。管理员操作只能在游戏自身受控通道调用，不能成为伙伴或 relay 的公开 API。

| 操作 | 调用角色 | 输入/效果 |
| --- | --- | --- |
| discover / describe | 访客读最小描述；认证申请者读授权范围内完整描述 | 发现仅提供候选，必须另行验证 endpoint 身份 |
| offer.create / offer.get | 对应伙伴；经验证玩家控制面可代表选定伙伴发起 | 根据当前 descriptor 协商生成 offer；只读本人范围 |
| offer.decide | PlayerConsent 对应玩家 | 批准 scope_digest 或拒绝；批准不等于已启动应用 |
| launch.request | 已确认玩家通过可信 Launcher | 固定注册应用身份+一次启动许可；输入不含可执行命令 |
| invitation.redeem | offer 绑定伙伴 | JoinIntent + grant；幂等领取，秘密不交给旁观者 |
| session.join | 邀请绑定伙伴且验证设备（若有） | 原子消费邀请并创建唯一 session，必要时申请呈现占用 |
| session.heartbeat / snapshot / events | 当前控制凭据；游戏读权限分开 | 续租仅由对应伙伴有效存活证明，游戏轮询不续伙伴租约 |
| session.close | 当前伙伴、玩家撤销者或 GameAuthority | 幂等关闭，禁止新行动，释放呈现，不伪造回滚 |
| session.resume / handoff | 已重新验证身份和必要玩家同意的控制面 | 仅已协商能力；持久账本完整时才恢复/转移，提升 generation |
| session.claim_control | 重新认证的目标伙伴及目标设备 | 从 ready transfer 领取该代写权；不重复升代，不向发起玩家暴露秘密 |
| context.publish | GameAuthority | 服务端验证开放类别和受众，写入事件 |
| chat.send | 伙伴；游戏通过已验证玩家映射发送 | 显式受众，过滤且不扩大 scope |
| action.request / cancel / query | 伙伴；query 也接受只读结果凭据 | request 受能力约束，cancel 只是意图；query 不能执行 |
| action.claim / commit_result | GameAuthority/受信执行器 | 执行 ticket、fencing、世界条件检查；不暴露给伙伴 |
| action.confirm | PlayerConsent 对应玩家 | 单次确认绑定原动作请求、参数/定义摘要和期限；本身不执行动作 |
| capability.replace / membership.replace | GameAuthority | 提升 revision；新增能力不自动进入 Grant，新成员不自动继承历史 |
| permission.revoke | 所属玩家或 GameAuthority 按对象权限 | 明确 auto_rule/grant/invitation/session/capability/relay 对象 |
| asset.resolve / presentation.acquire/renew/release | 仅已协商能力的受信资源/设备端 | 验证元数据与本地安全策略，不能通过其扩大动作授权 |
| privacy.request / privacy.receipt | 数据主体通过已验证映射；实际存储方回执 | 范围、保存例外及结果明确，不冒充全球删除证明 |

## 7. 授权与两个接入入口

共同顺序：发现候选 → 验证双方身份/受众 → 协商版本/能力/绑定 → 冻结 Scope → 玩家批准或有效自动许可 → 按需明确启动 → 伙伴领取短期邀请 → 加入 → 返回完整 Session/限制/租约/结果读取凭据 → 数据交互。

伙伴发起：伙伴必须已能证明自己的身份；不能自己调用 decide。游戏发起：玩家从已验证候选中选择伙伴/提供者；伙伴未运行时批准接入和允许启动是两个权限，界面可以同次确认但证据必须区分。云端无需 Launcher，但 Provider 必须完成玩家对伙伴的委托绑定；回调仅关联服务器保存的单次事务，校验 state/nonce、受众与超时，拒绝任意 return URL 或客户端自报已登录。具体标准适配器可替换，不把某 OAuth 流程名称当作实现证明。

自动规则匹配完整已批准权限条件（身份、实例 epoch、descriptor revision、绑定信任、能力、呈现及隐私）。规则使用 `rule_scope_key`，从 Scope 中排除本次生成的绝对 created_at 和 expires_at，但保留可授权最长时长、所有权限条件和限制；规则本身有独立到期时间。不能排除身份、实例或描述 revision 来换取命中。本版为安全和确定性选择严格匹配：改变权限条件即重新批准，包含收缩；后续可单独设计可证明的子集复用，不在本版隐含。新的 grant 到期不超过规则剩余有效期、用户允许最长时长和当前描述允许时长。规则可持久保存，但必须绑定身份验证根及撤销 revision，不能以保存某个 IP 即永久信任。自动加入不授权自动启动新应用或转移设备。

邀请有效期 `min(grant.expires_at, offer.decision_deadline, issue_time + invitation_ttl)`；批准、领取、加入三个时点均检查 scope/grant/instance。加入请求的形象/策略不能覆盖已批准值；可变的呈现观察是设备端授权的事实，单独写入 JoinIntent 后固定，重取若变化则冲突，不改变批准条款。

拒绝、超时、认证失败、启动失败均不产生有效会话。允许用户拒绝已经 stale 的 offer；拒绝不强迫先刷新描述。申请/邀请在批准后过期也不意味着必须自动重复弹窗。

### 撤销对象的明确效果

| 对象 | 生效后 | 不代表 |
| --- | --- | --- |
| auto_rule | 不再自动批准未来 offer | 已有 grant/session 立即失效 |
| invitation | 不能再 join，已消费时返回对应状态 | 关闭已建立 session |
| grant | 关联未消费邀请失效；关联活动会话立即关闭 | 回滚已发生动作 |
| session | 停止新数据/行动提交，查询已授权结果仍按结果读取范围 | 删除伙伴记忆 |
| capability | 新请求/未领取请求不可执行；已领取动作在副作用时点再次检查 | 已发生的效果能被消除 |
| relay | 停止转发且废止外层凭据；会话显式关闭或按租约收敛 | relay 代替游戏判定世界结果 |

## 8. 会话、租约与持久恢复

核心 session 只有 active/closed；“暂时失联”是连接观察状态，不创建第二种可绕过租约的权限。创建 session 时设 lease_deadline；有效 heartbeat/events polling 或新接受的伙伴提交可续租，旧重复收据不能续租。闭会原因包括 left/revoked/expired/host_shutdown/protocol_violation。closed 不能被 heartbeat 重新激活。

时间以 AccessAuthority 的受信时间源为准：进程内使用单调时间，跨重启使用持久到期时间和不可回退的受信时钟策略。不能确认有效期则拒绝恢复。客户端显示截止时间只作提示，不自行续权。

区分逻辑实例 epoch 与传输进程 transport_epoch：有完整持久状态的恢复保留逻辑实例 epoch，但新进程必更新 transport_epoch，旧网络写凭据不能直接复用；未协商恢复或账本丢失时连逻辑实例 epoch 也更新。旧只读结果句柄在可验证的持久记录内按独立读取权限检查，不赋予新传输写权。

未协商 resume：重启产生新逻辑 epoch，旧会话/写令牌失效，重新授权；未知动作不因重启自动重做。已协商 resume：在 resume_until 内重新认证，检查持久 Scope、Grant、租约、capabilities/membership 及账本，成功时保持 session_id 和旧去重键，提升 control_generation，轮换凭据；原会话已 closed、Grant 失效或账本不完整时拒绝恢复。恢复不是建立同 ID 的空账本。旧 generation 未执行动作取消，正在执行动作转为 unknown 并禁止新增效果，原 ticket 仍可报告已发生事实。

结果查询：join 返回只读、不续租的结果句柄，绑定原玩家/伙伴/会话和 action 可见集合；敏感部署须再验证原 Principal。其 read_until 从会话关闭时起至少覆盖协商 result_retention；句柄续期只能由重新认证控制面在保留期内完成。撤销会话写权不自动阻断已批准结果查询；若玩家显式撤销结果读权或法律/隐私删除，则返回权限错误而不是假造不存在。过保留期返回 `result_expired`，不谎报 failed/未执行。

若 join/恢复回包丢失导致未取得结果句柄，原主体可通过重新认证控制面调用 action.query：服务端从仍有效的原结果读取授权和账本建立本次只读上下文，不要求已关闭的写凭据，也不新建 Grant。只允许原获准读取者，仍检查读取撤销与保留期。会话 ID 可由本人 operation.get 的 outcome_ref 恢复；没有原授权或账本时明确拒绝，不凭知道 ID 授权。

Scope 还必须声明 `ledger_durability=volatile|durable`。volatile 的保留期只保证该实例账本存活期间，重启丢失时返回 `result_unavailable`（若无法认证旧主体，则先返回认证错误），不是 not_found 或未执行；禁止声称跨重启结果保证。durable 支持关闭后的约定保留，resume 必须依赖 durable。即使某实现支持 durable 结果保留，也可不支持会话 resume，两种能力不混同。

## 9. 行动与世界效果

每个 ActionDefinition 至少含标识、输入 schema、结果 schema、revision、允许主体、是否需一次确认、deadline 上限、可取消边界及效果类别（只读/可补偿/不可逆）。可补偿不意味着自动回滚；补偿是独立已授权动作。

| 原状态 | 触发 | 新状态/效果 |
| --- | --- | --- |
| 无记录 | 经权限和参数校验接受请求 | pending，返回收据而非成功结果 |
| pending | 有效一次执行 claim | executing，产生 execution_ticket |
| pending | 用户取消、撤权或执行前到期 | cancelled，effect=none |
| executing | 游戏权威确认完成 | succeeded，effect=committed |
| executing | 游戏确认失败或取消并报告实际效果 | failed/cancelled，effect 为 none/partial，不能抹掉部分效果 |
| executing | 断线/崩溃/期限届满且无可信事实 | unknown，effect=undetermined；查询而非重新执行 |
| unknown | 原执行器/受信恢复者提交带原 ticket 和效果账本证明的结果 | succeeded/failed/cancelled，提升 result_revision |
| succeeded/failed/cancelled | 同结果重复上报 | 返回旧结果；矛盾结果拒绝并进入审计，不覆盖事实 |

执行器在世界副作用生效的临界区核验 capability/grant/session/generation 与当前世界条件；claim 只是领取，不保证稍后仍有权限。世界引擎不能提供同事务写入效果与账本时，承诺降为“最多一次领取 + 可能 unknown”，不能称 exactly-once。进入 executing 后，关闭会话禁止新增效果；已发生效果仍可由可信执行器记录，其旧 ticket 只能报告该动作事实，不能执行新动作或续租。

动作参数中嵌入 URL、文件路径或脚本不会自动授权对应资源访问；GameAuthority 在能力 schema 及执行器中限定。限制动作还需额外批准时，单次确认绑定 request_id/参数摘要/revision，不能由聊天文本“允许”直接替代可信审批。

## 10. 事件、聊天、队伍与来源

事件序号在 session 内递增，不要求接收者看到连续序号。写入事件时冻结受众及其成员代次，投递时再与当前身份/会话/成员授权相交。退出再加入同一 Principal 也使用新成员代次，不自动恢复旧投递资格。新增队员不自动获得旧事件；离队者不再获排队团队消息；历史离线导出需独立明确授权，不由 event cursor 绕过。

core 私聊为当前玩家和伙伴，经宿主路由；team 能力允许更多已验证成员。GameAuthority 代表玩家发送消息前必须验证该玩家席位，不用客户端填写 player_id 代替。Agent 只能代表自己说话，转述必须标明来源。游戏情境可以不完整；协议不要求游戏公开全部地图/存档/敌人信息。

cursor 过期返回 `history_gap` 和当前可见 snapshot/高水位，不伪造漏失聊天。snapshot 包含当前 session、权限、成员 revision 和可查询动作摘要，不要求重建所有历史。客户端展示缺口，单独查询重要动作；不能因没见到 action.result 再发新动作。

来源至少区分 shared_experience/player_report/external_reference，并绑定 source_id、相关主体、scope、可披露受众。来源声明不是签名事实。跨游戏只传当前获准的摘要，不自动复制全部记忆；玩家允许向游戏 B 披露自己的经历不等于可披露游戏 A 其他人的私聊。

偏好优先级：用户明确偏好 > 游戏给出的陪伴默认值 > 伙伴默认值；始终受游戏数据/动作权限及其他参与者隐私约束。用户偏好与游戏接入硬要求冲突时拒绝/重新协商，不能静默降权假装遵从。对话/不剧透遵从由伙伴负责，不能以内容无法证明就放松世界权限。

privacy-request 若支持：请求绑定数据主体、来源/副本范围和行为（停止后续披露/删除可控副本）；存储方处理中返回 pending，完成后返回 done/partial/denied 及保留例外。禁止把回执当成所有提供者、备份或其他人的脑内信息已删除证明。不支持时明确返回 feature_unsupported，不假装成功。

## 11. 形象、资源与呈现

不协商 avatar 时不存在形象字段；游戏若硬性要求 avatar 则协商失败。已协商时仍按用户强制 > 游戏替代 > 伙伴默认选择；优先候选不兼容就返回不兼容和允许格式，不自动选较低优先级。玩家可显式改选并重新批准。

资源格式不能只用“model”判断兼容。Manifest 至少含资源 ID、内容类型/格式版本、字节大小、内容哈希、声明来源/许可、骨骼/动画或静态要求、依赖清单；远端定位符独立于身份。验证大小/哈希不等于许可证真实或资源安全。下载仅允许双方批准 origin，校验 TLS、禁凭据跨 origin 转发、逐跳重定向检查和 SSRF 地址策略，依赖同样校验；解包限制路径/文件数/总大小，禁止自动执行脚本。格式解析器需隔离，失败拒绝当前资源，不修改游戏权限。

呈现属于 PresentationOwner，不属于云端伙伴的一个布尔值。一个设备管理用户 baseline 和 manual_revision，以及多个有效 session 占用。`hide_desktop` 是游戏接入条件；用户拒绝隐藏则不加入或退出该会话，不把反对意图静默覆盖。`coexist` 不要求强制显示原本隐藏的桌面；`user_choice` 在批准时解析为明确条款。

无活动占用时呈现 baseline；有有效 hide 占用时隐藏，否则保持当前 baseline。用户主动更改更新 baseline/manual_revision；与 hide 条件冲突时先解除/结束对应会话再应用，不默许会话条件失真。释放单一占用只重算当前集合，不恢复旧 session 快照。应用重启后从持久占用中删除无法证明租约仍有效的项，保留最新用户 baseline；未协商持久恢复不能靠旧快照复活权限。

## 12. 多会话与设备转移

无 multi-session 时，服务端在伙伴作用域锁内拒绝第二个活动会话；不能覆盖第一个。支持该能力时，各 session 的权限、消息 ID、受众和记忆披露独立；共享伙伴身份不共享游戏授权。

上述服务端锁只约束该授权域，不声称能观察所有厂商游戏。符合协议的伙伴控制器还需在其所属 Agent 管理域执行会话 slot 预留：无 multi-session 时跨游戏也只保留一个活动/接入中 slot，加入失败释放，重启先核实旧 slot 的授权期限再新建；支持 multi-session 时按已声明上限分配。不同提供者没有共享验证根时不能声称全局唯一控制者，不把这个限制偷偷变成强制中央服务。

同一 session 的控制写权只有一个 generation。handoff 必须由玩家确认目标已验证设备，控制面原子提升 generation、轮换凭据并给旧设备发送失效事件；收不到事件也因 generation 检查无法再写。只读观察若允许须另发只读凭据。转移前正在 executing 的动作不重新执行，仍用原 ticket 结算；新设备仅查询原记录。呈现占用从旧设备释放、新设备经确认后获取；失败时记录未完成转移，不能让旧写权悄悄复活。

## 13. 限制、保留与错误

双方在 Scope 固定 message_bytes、event_page_size、max_pending_actions、session_count、event_retention、receipt_retention、result_retention、lease_period、resume_window 等边界。容量可按可支持范围协商，安全上限不可由客户端抬高。receipt_retention 至少覆盖有效会话及其恢复窗口；不能淘汰仍可重试请求的去重记录，满额拒绝新请求，仍允许退出/结果查询等控制操作。

关闭会话的消息回执可在约定保留期之后有界清理，但必须保留禁止旧会话写入的终态；
“回执已清理”不证明从未接受，也不允许旧 ID 或换 ID 重执行。动作回执还须覆盖其独立
结果读取承诺。当前模型仅实现这一受限维护路径，见 [回执清理证明](RECEIPT_RETENTION_PROOF.md)，
不据此允许活跃会话淘汰、终态回收或跨会话 ID 复用。

限额变化影响已批准 scope 时需重新协商；紧急安全收紧可关闭会话并说明原因，不默默改变去重承诺。慢消费者遇到历史过期按 history_gap 处理；禁止通过无限缓存保证可靠。生产部署另需公平队列和每主体速率限制，不把这些策略写成固定示例常数。

| 类别/示例 | 语义与处理 |
| --- | --- |
| unauthenticated / permission_denied | 不泄露对象是否存在，不重试扩大权限；按流程重新验证 |
| unsupported_version / feature_unsupported / trust_profile_unsupported | 授权前协商失败；不能自动退到弱版本/身份配置 |
| approval_stale / grant_revoked / invitation_expired | 不创建会话；刷新条件/重新批准，不能重放旧同意 |
| id_conflict / invalid_message / invalid_arguments | 请求未被重新接收；修正调用错误不能改已接受请求内容 |
| stale_capabilities / membership_changed | 先刷新事实，不能把旧授权当仍然有效 |
| session_closed / resume_denied | 不可用旧写凭据恢复；结果读取按独立权限 |
| history_gap / result_expired | 历史/结果不再可获得，不代表未执行 |
| resource_limit / rate_limited | 未接收时可按 retry_after 重发同请求；已接收状态必须查询 |
| transport_timeout / peer_unavailable | 接收或执行结果可能未知；原 ID 查询/重发，不发新动作 ID |
| execution_conflict / outcome_unknown | 世界效果不确定或证明冲突；隔离并人工/权威对账，不自动重做 |

错误必须带 outcome 和 request_id（若已知）；网络完全无响应视为 unknown，而不是伪造 not_accepted。重试退避和截止时间有界，超出截止时间只查询结果。客户端不因收到任意服务器 message 文本而执行命令。

## 14. 安全与信息最小化

令牌不在 URL、日志、argv 或资源 URL 中传递；服务端只保存可验证引用或摘要，客户端秘密存储交给身份适配器。邀请、会话写、结果读、执行 ticket、relay、控制面凭据分离。轮换旧写令牌时撤旧 generation，避免两把钥匙无限共存；若确需短期读兼容，权限必须只读且受限。

防重放依赖认证主体、受众、epoch/generation、期限和去重账本的组合，不依赖随机 ID 一项。发现描述仅是候选；TLS 的合法证书也不代表游戏对玩家私密信息具有授权。任何网页文本、游戏情境或 Agent 生成文字不能调用玩家审批、更新认证根或执行本地应用。

审计记录只保留 ID、角色、scope 摘要、状态转换、错误类型和必要时间；不默认收集聊天全文、模型提示、令牌或记忆。敏感详细日志需单独授权和保留期限。安全事件可撤销 grant/会话、隔离执行记录，但不得虚构未知动作已回滚。

## 15. 传输绑定与序列化

抽象操作独立于传输。本草案选择 HTTP+JSON 请求/轮询作为可推演的共同基础绑定；未来 WebSocket 等需要版本化映射，不能宣称当前已互通。出站 relay 复用同一操作封装和内层授权，禁止 relay 提交管理操作。

请求完整形式为 `{version, operation, request_id, payload, extensions}`，五个字段必需，空扩展为 `{}`；HTTP Authorization 承载对应凭据；响应为 `{request_id, result}` 或 `{request_id, error}`。伙伴数据操作使用 Envelope；控制操作的 payload 使用上述对象。每个 operation 必须按目录限定角色，未知 operation 拒绝。建议路由 `POST /g2a/operations`，公开最小描述 `GET /.well-known/g2a.json`；这不是旧绑定地址的兼容替换。

JSON 必须是 UTF-8，拒绝重复键、NaN/Infinity、超深结构及超大整数。整数限制在双方共同精确表示范围，时间/序号越界明确拒绝。摘要使用固定版本的规范编码：对象键按 Unicode 标量顺序排序，数组保序，字符串不偷偷 Unicode 归一化，整数十进制、禁止浮点；有小数需求时用明确单位整数或规范字符串。具体字节、范围、限额与摘要投影见 [编码与摘要契约](WIRE_CONTRACT.md)。该编码用于比较 scope/request，不自行充当跨厂商签名标准；身份适配器若签名需固定成熟标准及算法白名单。

非回环必须 TLS 且验证身份，绑定中声明是否允许代理和重定向；默认禁止令牌跨 origin 发送。HTTP 状态只是错误类别映射，不能取代 Error.outcome；relay 超时仍可能已执行内层操作。批处理逐项返回收据，不隐含整个批次原子性；事件与动作按会话内定义排序，不宣称跨游戏全局顺序。

## 16. 演进、迁移与发布门禁

状态流：working-draft → reviewed-draft → experimental-release → stable；每次格式/语义变化记录决策、受影响场景、兼容性和本地验证。规范版本、schema 版本、SDK 包版本分开，SDK 必须声明支持的精确协议集合。破坏性变化新版本、明确弃用窗口；窗口时长在实际稳定发布决定时固定，不以草案日期暗中开始计时。

旧 `0.1.0-dev` 不能假装自动理解本版：旧 descriptor 无能力/身份配置时只进入旧隔离适配器，标明 test-enrolled、单会话、无跨重启恢复、既有私聊信任边界；不把旧 desktop_visible 直接推断为 presentation 能力充分证明。新端点可以并行提供旧绑定，但不得将新 token 交给旧 endpoint；任何转换都必须有字段/错误/权限逐项映射和负例。

符合性按角色+版本+能力+身份配置+绑定声明，不给单一“全部支持”勾选。测试向量应覆盖 I01–I10、两个入口、四种本地/云端组合及关键失败时点；不能用己方两个语言实现当第三方采纳证明。

规范、继承代码、SDK、示例、第三方资源权利分别清点，现有许可保持；名称/域名/商标未核实不宣称独占。权利人对许可和对外发布的决定是发布门禁，不由伪代码代替。安全报告渠道在公开发布前落实，私密漏洞不默认发公共 Issue。

## 17. 交付状态与审计边界

本文的语义草案、控制面、数据面、呈现/资源/恢复及 Relay 伪代码已形成，并完成 [符合性审计](CONFORMANCE_AUDIT.md) 所列范围的 [模型重放与逐步推演](WALKTHROUGH_RESULTS.md)。身份、数据库、世界执行、资源沙箱使用明确契约的端口，失败路径不能固定返回成功。交付是协议工作草案与假实现级全流程，不是实际部署或稳定发布；外部认证标准适配器的具体技术版本需真实接入时核实，不宣称已完成某 OAuth/IPC/TLS 产品集成。
