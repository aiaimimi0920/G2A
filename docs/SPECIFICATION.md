# G2A 0.1.0-dev 实验性规范

状态：开发草案，不能宣称稳定兼容或生产安全。完整目标见 [实施台账](IMPLEMENTATION_PLAN.md)。本文件和 `src/g2a/schema.json` 共同约束当前实验绑定；结构以 schema 为准，语义以本文件为准，二者冲突视为缺陷，不允许实现静默选一份。

这里的 MUST、MUST NOT、SHOULD、MAY 分别表示必须、禁止、建议和可选，是本草案的要求，不是对尚未实现功能的完成声明。

## 1. 角色与身份

- **游戏宿主**：拥有世界信息开放、参与者集合、能力定义和行动执行权。
- **伙伴 Agent**：用户的固定伙伴，不得因此接管任意 NPC。
- **玩家**：伙伴当前陪伴的用户；玩家身份、Agent 身份和游戏身份必须区分。
- **会话**：一次游戏接入。会话 ID 不等于 Agent 身份，也不是认证凭据。

Agent 身份可跨游戏延续，但本协议不创建全局账号中心，不强制共享内部记忆。当前参考实现由可信宿主预先绑定身份，尚无跨服务身份认证或 OAuth 委托实现。

## 2. 协议与能力描述

描述文档包含 `protocol`、`game_id`、`name`、`bindings`、`avatar_formats`、`presentation`、`policy`、`actions`，可选 `game_avatar`。版本字符串当前必须精确匹配 `0.1.0-dev`，未知版本返回 `version_not_supported`；不得静默按别的版本解释。

能力由游戏开放。每个 action 包含 `name`、`description`、JSON Schema `parameters` 和 `timeout_ms`。参考实现禁止能力参数 schema 中的 `$ref`/`$dynamicRef`，不访问网络或文件解析外部引用。该约束是首个绑定的安全边界，不表示所有未来绑定都不能采用安全的本地引用。

游戏可以少给、不提供或额外提供背景；协议不要求完整世界状态，也不强制截图或视频。这里的“可观察”由游戏选择开放，不保证 Agent 没有先验知识。

## 3. 加入与授权

宿主必须在用户确认或既有自动加入授权之后发出短期邀请。邀请绑定 Agent、玩家、队伍成员和行动授权集合。Agent 不能自己创建邀请或用请求字段扩大邀请权限。

加入请求包含身份、版本、默认形象、加入前桌面是否可见、用户策略和用户允许的行动集合，可含强制形象和首选呈现方式。实际行动授权为邀请允许与用户允许的交集，并受当前游戏能力约束。

邀请凭据与会话凭据必须分离。相同邀请和相同加入请求在有效期内重试返回同一会话；改变已消费邀请的请求返回 `invitation_used`。身份不匹配必须拒绝，拒绝时不得改变桌面状态。

当前参考宿主允许每个 Agent 在该宿主最多一个活动会话；多游戏客户端的呈现协调尚未定义。这不是完整目标中的永久限制。

## 4. 呈现与形象

形象选择顺序：`forced_avatar` > `game_avatar` > `default_avatar`。选中格式不在 `avatar_formats` 时必须返回 `avatar_incompatible`，不得回退到较低优先级形象。用户可提交新的兼容选择。

`presentation` 为 `hide_desktop`、`coexist` 或 `user_choice`。前两者是本次接入条件，后者采用用户首选，缺省共存。隐藏形象不是关闭智能核心，共存不是创建第二个 Agent。

当前 avatar 仅是带 `id`、`format`、`label` 的描述对象，不传模型或下载远端资源，不应宣称支持完整跨引擎形象导入。

加入成功后客户端保存自己的加入前状态。离开或租约失效后恢复该状态，而非简单设置为显示。恢复呈现不得清除记忆。参考 Client 只演示状态值恢复，真实窗口控制和跨进程崩溃持久化尚未实现。

## 5. 策略不是权限

`policy` 支持 `spoilers`、`advice`、`proactive_chat`、`proactive_actions`。对于这些陪伴策略，用户明确设置覆盖游戏默认策略。未知策略键在当前版本中拒绝，避免被解释为授权扩展。

这些是发给 Agent 的行为要求，不是游戏能力授权。用户允许剧透不能让 `reveal-boss` 等未开放行动通过校验。Agent 应根据共同经历和玩家讲述判断已知范围，不能因为当前第一关就强制否认二周目记忆。

策略遵从属于 Agent 实现责任；当前参考宿主不通过文本内容判断 Agent 是否剧透，也不能证明不受信任 Agent 遵守策略。真正的数据/动作限制必须由游戏执行端实施。

## 6. 消息与路由

消息包含 `id`、`type`、`sender` 和 `data`。ID 在同一会话、同一认证角色下唯一。相同 ID 与相同内容重复提交返回原收据，不重复排入事件流；内容变化返回 `id_conflict`。

支持：

| type | 发送方 | 含义 |
| --- | --- | --- |
| `game.context` | 游戏 | 游戏选择开放的情境/事件 |
| `chat.message` | Agent 或游戏代表的已登记玩家 | 明确受众的文字表达 |
| `action.request` | Agent | 请求执行已授权能力，不等于已执行 |
| `action.result` | 游戏 | 实际行动结果 |
| `capability.update` | 游戏 | 替换能力集合，提升 revision |
| `action.cancel` | Agent | 请求取消，不等于取消成功 |

宿主还产生 `session.closed`、`action.expired` 事件。消息不要求有一条先行的玩家问题，Agent 可主动发言或请求动作，游戏也可主动提供事件。

### 6.1 受众

聊天必须带 `channel` 和显式 `recipients`。`private` 仅允许当前玩家与伙伴；`team` 仅允许宿主预先登记的队员和伙伴，禁止通配广播到任意用户。

游戏宿主是可信路由者，能看到经过它的消息，这不是端到端加密私聊。参考绑定只有游戏端与 Agent 端连接，游戏负责将消息递交给实际玩家。不会给 Agent 投递没有把它列为接收者的玩家聊天。向玩家提供网络连接/队伍转发是游戏集成责任，不能将内存队伍列表当成已实现多人游戏。

### 6.2 来源

`provenance` 区分 `shared_experience`、`player_report`、`external_reference`，包含来源标识和玩家标识。前两者可进入与玩家相关的已知背景，但玩家讲述不意味着 Agent 当时在场。外部参考不得伪装成共同经历。

游戏观察消息必须声明 `shared_experience`，身份必须属于当前玩家；聊天可标记其他来源。字段是来源声明，不是密码学证明，协议无法阻止恶意端点虚报经历。具体记忆保存、事实核查及公开披露策略由 Agent 负责，后续须提供跨游戏记忆例程验证这些边界。

## 7. 行动生命周期

请求携带能力名、参数与 `capability_revision`。宿主逐次校验身份、会话、能力版本、游戏能力、邀请/用户交集授权与参数 schema。任何一点不满足均不得执行。

参考状态：`pending` → `executing` → `succeeded` / `failed` / `cancelled`。无法确定结果使用 `unknown`，不能把超时等同于失败，更不能自行重试有副作用动作。

本地游戏执行器使用 claim 操作在产生副作用前再次检查能力版本及授权。重复领取不再授予执行许可；能力撤销或版本变化会阻止旧待执行请求被领取。真实执行器仍须在效果生效处检查世界条件；已领取操作的撤销竞态、事务和持久化去重不是内存参考宿主能独立解决的。

取消只是请求，最终状态由游戏报告。退出或超时不能虚构动作回滚。会话关闭时未确定的操作保留为 `unknown`。结果可通过 action 查询取回，不能依赖有限事件窗口作为唯一结果账本。

## 8. 事件、断线与资源限制

序号按会话单调增长。轮询返回快照、当前页事件和下一 cursor；cursor 可能跨过对调用者不可见的事件，因此客户端不得假定序号连续。当前页不等于整个历史，须用返回 cursor 继续。

参考宿主每会话保留 256 条事件，单次最多 32 条并限制分页大小；过旧 cursor 返回 `cursor_expired`，不得静默跳过。提交收据最多 1024 个，满后明确拒绝，不悄悄淘汰幂等记录。宿主最多 64 会话、256 邀请；当前没有持久化或清理接口，容量满需由集成方处理。

成功轮询或新 Agent 消息更新服务端租约；游戏端轮询不替 Agent 续租。客户端只根据加入和有效轮询快照延长呈现租约，因为旧提交收据不能证明会话仍活跃。

短暂断线不立即表示动作失败。租约到期结束会话，不允许旧令牌重新开启；新接入必须重新授权。当前参考宿主重启会丢失内存状态，不能保证跨进程“恰好一次”；生产实现必须定义持久化与未知结果恢复。

## 9. HTTP+JSON 实验绑定

| 方法与路径 | 凭据 | 返回 |
| --- | --- | --- |
| `GET /.well-known/g2a.json` | 无 | 游戏公开描述 |
| `POST /sessions` | 邀请 Bearer | 会话快照、会话令牌、租约 |
| `GET /sessions/{id}/events?cursor=N` | 会话或游戏 Bearer | 按角色筛选的事件页及快照 |
| `POST /sessions/{id}/events` | 会话或游戏 Bearer | 接收收据，非执行完成 |
| `POST /sessions/{id}/leave` | 会话或游戏 Bearer | 关闭后的快照 |
| `GET /sessions/{id}/actions/{request_id}` | 会话或游戏 Bearer | 当前行动状态及已知结果 |
| `POST /sessions/{id}/actions/{request_id}/claim` | 仅游戏 Bearer | 一次执行领取；请求体 `{}` |

请求 JSON UTF-8，`Content-Type: application/json`。只接受一条有效 Content-Length，拒绝 chunked、压缩、重复 JSON 键、NaN/Infinity；请求体最多 64 KiB。认证凭据不放 URL，不记录到默认日志；响应 `Cache-Control: no-store`。

参考服务器只监听 `127.0.0.1` 随机端口，拒绝浏览器 Origin；它不是公网生产服务器。当前客户端明文 HTTP 仅允许显式 IPv4 回环地址，禁用重定向和代理环境继承，不下载形象 URL。云端接入、浏览器授权、发现注册和唤起协议未实现，不能用关闭安全检查代替这些设计。

### 错误

错误为 `{"error":{"code":"…","message":"…"}}`。主要分类：

- 401 `unauthenticated`：凭据无效，不暴露会话是否存在。
- 403 `permission_denied` / `origin_denied`：越权或来源不允许。
- 409 `version_not_supported` / `avatar_incompatible` / `id_conflict` / `session_closed` / `stale_capabilities` / `cursor_expired` / `not_executable`：需调用方处理，不能盲目重试。
- 400 `invalid_message` / `invalid_arguments` / `invalid_provenance`：结构或语义不成立。
- 413 `message_too_large`、415 类型/编码不支持、429 `resource_limit`：资源或绑定限制。

调用者只在安全条件下重发原 ID、原内容；SDK 不自动重试有副作用请求。当前还没有 Retry-After、长期结果保留期和多绑定恢复承诺。
