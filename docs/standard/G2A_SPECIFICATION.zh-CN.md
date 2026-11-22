# G2A 协议规范

**Game-to-Agent Interaction Protocol｜游戏与智能体交互协议**

定义游戏世界、玩家与 AI 智能体之间的身份、观察、授权与行动边界的开放协议标准。

状态：面向公众审阅的工作草案。编辑修订号：`standard-review-2026-11-22-r73`。修订日期：2026 年 11 月 22 日。
设计基线：`g2a-design-1`。候选配置规范：`observations-draft-1`、`g2a-http-json/draft-1`。
本文定义供审阅的目标标准语义，不分配已冻结的生产线上协议版本，也不认证现有 SDK 实现。

> 本文是英文主稿 [G2A_SPECIFICATION.md](G2A_SPECIFICATION.md) 的完整同步中文规范。协议标识、字段名、操作名与标准错误码保持英文原文；“**必须**”“**不得**”“**应**”“**不应**”“**可以**”具有第 2.1 节规定的规范效力。若译文存在歧义，以英文主稿为准。

语言版本：[英文主稿](G2A_SPECIFICATION.md)与本中文规范共享同一编辑修订号与章节编号。可追溯修改记录见[第 25 节](#section-25)。

## 目录

1. [目的与范围](#section-1)
2. [约定与文档效力](#section-2)
3. [架构、部署拓扑与适用性](#section-3)
4. [角色、身份与信任](#section-4)
5. [规范数据模型](#section-5)
6. [抽象操作目录](#section-6)
7. [发现、协商与准入](#section-7)
8. [授权、会话与撤销](#section-8)
9. [游戏观察配置规范（`observations-draft-1`）](#section-9)
10. [行动与效果语义](#section-10)
11. [幂等性、投递与恢复](#section-11)
12. [错误模型、时间与资源限制](#section-12)
13. [游戏角色与接入要求](#section-13)
14. [在线状态与角色生命周期](#section-14)
15. [对话、信息使用与伴玩记忆](#section-15)
16. [伴玩自主性与玩家策略](#section-16)
17. [可选配置规范与扩展](#section-17)
18. [HTTP/JSON 与流式传输绑定（`g2a-http-json/draft-1`）](#section-18)
19. [安全与隐私考虑](#section-19)
20. [版本、发布清单与生态治理](#section-20)
21. [符合性与质量评估](#section-21)
22. [基线对齐与迁移说明](#section-22)
23. [端到端示例场景](#section-23)
24. [参考资料](#section-24)
25. [修订历史](#section-25)

## 协议概览

不同游戏拥有截然不同的世界规则、视野机制与动作空间。G2A 在**游戏**（通过指定的**游戏交互节点 Game Interaction Node** 对外暴露）与受权扮演游戏内角色的**游戏智能体（Game Agent）**——主要为**玩家伴玩（Game Companion）**，或可选的**独立 AI NPC**（如 Boss、引导者）——之间建立中立、开放的交互契约。

```text
真人玩家 ──控制──▶ [玩家角色]
  │                    ↕ 游戏内 / 私聊 / 队伍沟通
  │ 授权与策略     [游戏内角色槽位]（玩家伴玩 或 独立 AI NPC）
  │                    ▲           ↕ 获授权感知与行动
  ▼                    │ G2A       ▼
[PlayerConsent] ─▶ [游戏交互节点] ◀──▶ [游戏世界与规则]
                       ▲                  （最终判定权）
                       │ G2A 协议
                       ▼
                  [游戏智能体]
             （本地或云端决策引擎）
```

三条核心权力边界贯穿所有 G2A 交互：

1. **游戏掌握世界事实与最终执行权：** 游戏交互节点发布获授权的观察视图，并依据当前玩法规则裁定行动请求成功、失败或产生部分效果。游戏智能体是负责感知与决策的软件，而非全知全能的世界控制器。
2. **玩家主导授权与伴玩偏好：** 在游戏规则允许的边界内，玩家决定智能体是否接入、获得何种权限范围，以及自身伴玩的自主等级、记忆使用、剧透偏好与确认策略。玩家偏好绝不能突破游戏开放权限或侵犯其他参与者的隐私边界。
3. **智能体自主实现推理与可迁移记忆：** G2A 仅规范可观察的通信契约与权限核验，不指定特定的大语言模型、规划算法、记忆数据库、桌面宠物客户端或中心化账号服务。

<a id="section-1"></a>

## 1. 目的与范围

### 1.1 设计目标与四大支柱

G2A 使任何符合规范的游戏与任何符合规范的 AI 智能体能够在本地与云端环境中安全互操作。全规范围绕四大支柱展开：

| 支柱 | 规范内容 |
| --- | --- |
| 准入与控制 | 主体身份认证、发现、能力协商、玩家同意、有界授权、会话租约、跨设备交接与分级撤销。 |
| 观察与信息使用 | 获授权游戏状态视图、基线与增量、信息来源、新鲜度、接收范围边界、多模态输入与记忆治理。 |
| 行动与结果 | 能力定义、动态合法行动资格、确认挑战握手、效果边界重验、取消语义与未决结果核对。 |
| 互操作与扩展 | 规范数据对象、抽象操作目录、传输绑定、确定性错误码、版本演进、可选配置规范与符合性套件。 |

### 1.2 核心架构区分

五项基本区分贯穿本规范全部层级：

- **支持不等于授权：** 在描述对象中声明某项能力仅表明技术上支持该功能，发起请求仅表达调用方意图；缺少有效的 `Grant` 与 `Scope` 时，两者均不赋予读取或执行权限。
- **接受不等于效果完成：** 接收或排入行动请求（`pending`）不代表已在游戏世界中产生预期变化；请求受理、执行器领取（`executing`）与世界效果提交（`committed`）**必须**严格区分。
- **获准读取不等于持续有效：** 观察仅反映特定代次与修订号下的受限视角，随世界演进或视野变化将过期失效。
- **缺失不等于不存在：** 因战争迷雾、权限过滤或增量压缩而未出现的数据，**不得**被推断为某项事实为假、空世界或实体已销毁。
- **伴玩记忆独立于当前世界状态：** 读档回退、开启新周目或切换剧情分支会改变权威世界状态，但**不得**仅因此清空玩家自主管理的伴玩记忆；记住先前分支的经历不代表该事件已在当前世界发生，也不能覆盖游戏的硬性玩法规则。

### 1.3 适用范围与非目标

G2A 严格限定于游戏交互领域：面向玩家的伴玩协助、获授权 AI NPC 交互、游戏状态观察、受约束的游戏内行动及可选的伴玩外观呈现。

G2A **不是**通用操作系统或桌面 UI 自动化协议。它不将任意远程代码执行、未经声明的原始桌面/键鼠抓取、模型权重、提示词模板或平台内部商业清分结算纳入标准。G2A 强制执行可观察的数据、接收范围与行动边界，但任何通信协议都无法擦除模型参数中的先验知识，也无法在数学上阻止恶意端点从已知信息作内部推断。

<a id="section-2"></a>

## 2. 约定与文档效力

### 2.1 规范性用语

本文中加粗或明确表达参与方义务的“**必须**（MUST）”“**必需**（REQUIRED）”“**不得**（MUST NOT）”“**应**（SHOULD）”“**不应**（SHOULD NOT）”与“**可以**（MAY）”，按 RFC 2119 与 RFC 8174（BCP 14）的规范性定义解释。解释性文字、架构图、端到端示例（第 23 节）及修订记录（第 25 节）属于资料性内容，不独立增设规范要求。“**可以**”表达规范性许可，不要求所有实现均提供该可选功能。

### 2.2 规范状态与产物层级

英文主稿（`G2A_SPECIFICATION.md`）与本中文规范共同构成供公众审阅的标准正文。为保持规范章节自包含且紧凑，以下三项原则全局适用，不在各章节末尾重复赘述：

1. **基线契约与候选配置规范：** 核心会话、授权、行动及规范化编码建立在仓库机器可校验的设计基线（`g2a-design-1`：[contracts.schema.json](../protocol/contracts.schema.json)、[operations.json](../protocol/operations.json)、[WIRE_CONTRACT.md](../protocol/WIRE_CONTRACT.md)）之上；类型化观察流（`observations-draft-1`，第 9 节）与统一 HTTP/JSON 操作绑定（`g2a-http-json/draft-1`，第 18 节）是在此之上提出的候选规范。
2. **正式发布冻结门禁：** 候选配置规范的精确 Schema、扩展标识符与摘要域，须按第 20 节纳入不可变发布清单并配套跨实现测试向量后，方具备正式生产互操作效力；正文对行为语义的规定不会静默注册未声明的核心操作，也不代表对早期实验原型（`0.1.0-dev`）的认证。
3. **诚实的符合性声明：** 实现**必须**标明其实现的精确协议版本、传输绑定与配置规范集合，**不得**将支持某一候选草案或旧实验 SDK 表述为符合未来正式冻结版。历史基线映射集中列于第 22 节。

<a id="section-3"></a>

## 3. 架构、部署拓扑与适用性

### 3.1 三层协议栈

G2A 将“交互语义”与“字节承载方式”解耦，使同一套游戏权限与状态机规则可跨越本地进程通信、HTTP、流式通道与中继部署保持一致：

1. **规范数据模型（第 5 节）：** 定义主体、描述对象、权限范围、授权记录、会话、消息信封、观察、行动、回执与错误的类型化结构。
2. **抽象操作与状态机（第 6–17 节）：** 定义独立于传输方式的操作语义、权限核验、生命周期转换、确认握手与中断恢复规则。
3. **传输绑定与配置规范（第 18 节）：** 将前两层映射到具体的网络协议、端点路由、HTTP 状态码、流式通道与出站中继。

SDK 与游戏引擎插件是实现协议的工具而非协议本身；任何编程语言或内部架构只要符合线上契约与行为不变量，均属合规实现。

### 3.2 标准部署拓扑

游戏运行环境涵盖从家庭 NAT 后的单机客户端到云端专用服务器。G2A 原生支持三种标准部署拓扑，且不改变上层抽象操作语义：

| 部署拓扑 | 连接建立方向 | 典型适用场景 |
| --- | --- | --- |
| **本地回环 / IPC** | 智能体 ↔ 本地游戏交互节点（`127.0.0.1` 或系统 IPC） | 本地桌面/移动端伴玩应用与同一设备上的单机游戏或客户端宿主协同运行。 |
| **直连 HTTPS / WSS** | 智能体 → 可达的游戏交互节点 | 云端或局域网智能体连接具备可达 TLS 端点的游戏服务器或网关（`g2a-http-json` + 可选 SSE/WebSocket 流）。 |
| **出站中继（Outbound Relay）** | 游戏交互节点（主动出站）→ 配对中继 ← 智能体 | 位于家庭 NAT/防火墙后的单机或 P2P 联机客户端连接云端智能体，无需在玩家设备上开放任何入站端口（第 18.3 节）。 |

### 3.3 能力模块与适用范围

并非所有接入方都需实现全部功能。核心符合性仅要求会话管理、事件/上下文处理与基础结构化感知；其余能力均按需显式协商：

| 能力标识符 | 要求层级 | 核心职责概览 |
| --- | --- | --- |
| `core.session` | 必需核心 | 发现、版本与能力协商、有界准入、会话租约、恢复快照、关闭与错误处理。 |
| `core.events` | 必需核心 | 接收方可见的有序事件投递、`context.publish` 承载及会话内幂等去重。 |
| `perception.structured` | 必需核心（游戏智能体） | 理解已协商的结构化游戏状态（`observations-draft-1` 或基线上下文）并在授权角色内决策。 |
| `observation.query` | 可选能力 | 智能体发起的无状态、经授权当前游戏观察读取，不产生世界副作用（第 9.6 节）。 |
| `perception.visual` | 可选能力 | 建立在 `perception.structured` 之上的游戏画面/图像感知（第 9.5 节）。 |
| `perception.audio` | 可选能力 | 建立在 `perception.structured` 之上的游戏环境音频感知，独立于语音对话（第 9.5 节）。 |
| `actions` | 可选能力 | 类型化行动请求、确认挑战、执行器领取、效果边界重验、取消与结果查询（第 10 节）。 |
| `chat` | 可选能力 | 绑定来源与接收范围的文字/语音沟通（`chat.send`、`player_chat.forward`）（第 15 节）。 |
| `team` | 可选能力 | 多人席位映射、成员关系修订号与队伍范围接收控制。 |
| `resume` | 可选能力 | 持久会话账本、去重记录与活动租约内的无缝重连（第 11、14.2 节）。 |
| `handoff` | 可选能力（依赖 `resume`） | 带控制代次隔离（fencing）的跨设备/跨进程会话控制权转移。 |
| `multi-session` | 可选能力 | 同一智能体并发维持多个活动会话，不静默挤占既有会话。 |
| `avatar` / `assets` / `presentation` | 可选能力 | 伴玩外观优先级协商、安全声明式资源解析与设备渲染租约（第 17.2 节）。 |
| `store` | 可选能力 | 结构化实时商品目录、适度推荐限频与权威购买预算账本（第 17.1 节）。 |
| `privacy-request` | 可选能力 | 针对数据保管方的有界数据处理/删除请求与真实回执查询（第 15 节）。 |

按阅读层次划分：第 4–12 节定义 **L1 核心交互与状态机层**，第 13–16 节定义 **L2 游戏角色、在线边界、记忆与自主策略层**，第 17–18 节定义 **L3 可选配置规范与传输绑定层**。某一条款是否适用，完全取决于参与方声明的角色与已协商启用的能力。

<a id="section-4"></a>

## 4. 角色、身份与信任

### 4.1 核心信任主体与协议端点

G2A 明确定义三类核心信任主体与四类可选功能角色。同一软件进程**可以**合并承担多种角色，但**必须**在逻辑上严格隔离各角色的权限边界：

| 角色名称 | 类别 | 权威边界与核心职责 |
| --- | --- | --- |
| **游戏交互节点（Game Interaction Node，`Game`）** | 核心端点 | 游戏指定的 G2A 通信入口，也是本次交互中当前游戏状态与行动结果的唯一协议权威来源；负责认证调用方、执行 `Scope` 并协调游戏内部模块。 |
| **游戏执行器（Game Executor，`Game` 内部）** | 权威执行组件 | 游戏内部逻辑或服务端子系统，负责领取待处理行动（`action.claim`）、在效果边界执行游戏规则并提交最终结果（`action.commit_result`）；绝不直接向智能体凭据开放。 |
| **玩家 / `PlayerConsent`** | 核心主体 | 真人玩家及其经过认证的同意/控制通道（`PlayerConsent`），负责批准 `Offer`、确认高影响行动（`action.confirm`）、配置伴玩偏好与撤销权限。 |
| **游戏智能体（Game Agent，`Agent`）** | 核心端点 | 在本地或远端运行、受权扮演特定游戏内角色（伴玩或独立 AI NPC）的决策软件；消费获准观察、发起范围内行动请求并管理内部推理与伴玩记忆。 |
| **本地启动器（Local Launcher）** | 可选角色 | 校验本机已登记应用身份，并凭显式单次 `launch.request` 许可启动固定程序，严禁拼接执行不可信命令行。 |
| **呈现端点（Presentation Endpoint）** | 可选角色 | 管理用户设备上的伴玩窗口/覆盖层渲染租约（`presentation.*`）与安全资源缓存（`asset.resolve`）。 |
| **数据保管方（Data Custodian）** | 可选角色 | 任何实际持久化保存玩家或伴玩数据的参与方（智能体服务商、游戏或平台），负责就其控制范围内的数据处理 `privacy.request` 并签发 `privacy.receipt`。 |
| **出站中继（Outbound Relay）** | 可选传输角色 | 在游戏交互节点不开放入站端口时，在已配对端点间转发受允许的操作（`relay.*`），但绝不持有 `Game` 管理员权限。 |

游戏交互节点是一项对外协议职责而非必须额外部署的独立服务器：单机游戏**可以**在客户端进程内或通过本地 sidecar 实现，联网游戏**可以**在客户端或服务端网关提供。关闭 G2A `Session` 仅结束该协议交互上下文，不等于关闭游戏进程或多人房间。

### 4.2 主体、实例与代次标识

调用方身份**必须**依据传输层经过认证的凭据确定；消息体内的 `sender` 字段仅用于与认证身份作一致性核对，**不得**单独作为身份证明。实现**必须**严格区分四类标识：

- **主体 `Principal`（`{issuer, subject, kind}`）：** 在签发方 `issuer` 命名空间内唯一标识 `player`、`agent`、`game` 或 `service`。显示昵称不参与认证，不同签发方下的同名主体**不得**自动合并。
- **设备 `Device`（`device_id`）：** 标识持有呈现或会话控制租约的物理或逻辑终端。
- **运行实例 `Instance`（`{game, instance_id, epoch}`）：** 标识具体某局游戏、副本或房间，防止跨局重放授权与凭据。
- **代次标识（`instance_epoch`、`world_epoch`、`visibility_epoch`、`control_generation`）：** 单调递增或严禁复用的阶段标记，用于在读档、阵营切换或控制权交接后立即隔离旧凭据、旧视野与旧控制端。

### 4.3 委托链与信任配置规范

当服务或网关代表玩家操作时，经验证的**委托（Delegation）** **必须**绑定委托玩家、受托主体、目标游戏/实例、获准权限范围及有效期。请求经过任何中间环节转发，绝不会把中间方的权限叠加到被代表主体之上。聊天文本或游戏字符串中自称“已获委托”不具任何效力；仅知晓 `session_id`、`action_id` 或 `correlation_id` 也不赋予读取或执行权。

部署**必须**声明并强制执行兼容的信任配置规范，严禁静默降级：

- **`local-verified`：** 由操作系统 IPC 或受信本地启动器核实本机软件与玩家归属。
- **`provider-verified`：** 通过 TLS 与经验证的令牌/委托机制跨网络绑定玩家、智能体、目标受众与有效期。
- **`test-enrolled`：** 仅供本地开发与符合性夹具使用的预登记测试身份；**不得**将其宣称为可抵御本机不可信软件的生产安全机制。

实现**必须**在 `PrivacyModel` 中如实披露明文可见范围：除非未来通过显式扩展协商端到端加密，游戏交互节点与所选出站中继均可读取途经它们的消息，**不得**虚假宣称仅通信两端可解密。

### 4.4 四维权限分离与仅限规划受保护输入

实现**必须**将以下四维权限独立核验，不得相互替代：

1. **接收权：** 智能体获准从游戏或玩家处获取哪些信息；
2. **对玩家披露权：** 智能体可以在面向玩家的回复中说出哪些信息；
3. **对外转发权：** 智能体可以向游戏、队友或其他外部服务发送哪些信息；
4. **行动权：** 智能体可以在游戏世界中请求执行哪些能力与参数范围。

观察配置规范**应**进一步区分：(a) **可向玩家展示的观察**，(b) **仅限内部规划使用的受保护输入**，以及 (c) **由游戏内部判定的不透明条件**（游戏在内部评估隐藏前置条件，仅向智能体返回获准披露的布尔结果或不透明引用）。当有效授权将原始或派生数据限制为“仅限规划”时，实现**必须**在检索、工具/消息外发序列化与输出过滤边界实施架构隔离（例如将非语言动作选择模块与自由对话生成上下文分离），**不得**声称仅凭系统提示词即可保证绝对隔离；凡要求严格禁止泄露的秘密，游戏**应**优先采用内部条件判定而非下发原始秘密。

<a id="section-5"></a>

## 5. 规范数据模型

### 5.1 核心标识符与定点数值表示

除另有明确规定外，所有协议标识符（`descriptor_id`、`offer_id`、`grant_id`、`invitation_id`、`session_id`、`stream_id`、`request_id`、`action_id`）对消费方均为不透明字符串（`1..128` 字符），消费方**不得**拆解字符串猜测身份、权限或先后顺序。传输 `request_id`、信封 `id`、`correlation_id`、事件 `sequence` 与观察 `revision` 分属独立命名空间，**不得**混用。

**确定性整数与定点表示规则：** 由于规范 JSON 编码 `g2a-cjson-1`（第 18.4 节）为确保跨语言哈希摘要完全一致而禁止 IEEE-754 浮点字面量与负零，所有线上 Schema **必须**在精确安全整数范围（`[-9007199254740991, +9007199254740991]`）内使用显式整数单位或定点缩放表达连续游戏物理量：

- **时间与时长：** 统一使用整数毫秒（`_ms`，如 `observed_at_ms`、`maximum_duration_ms`）；
- **比例与概率：** 使用整数基点（`_bps`，取值 `0..10000`，`10000 = 100.00%`）或声明的固定分母；
- **空间坐标与物理量：** 由观察或行动 Schema 明确声明缩放单位（如毫米 `_mm`、毫弧度 `_mrad` 或 `{value, scale_exp10}`），或在确需任意精度时采用类型化十进制字符串。

### 5.2 规范协议对象

规范数据模型由以下 14 个核心结构组成（基线字段的精确 JSON Schema 见 [contracts.schema.json](../protocol/contracts.schema.json)）：

| 规范对象 | 核心职责与关键字段结构 |
| --- | --- |
| **`PublicDescriptor`** | 未认证公开发现文档（`GET /.well-known/g2a.json`）：`{instance, supported_versions[], discovery_endpoint}`，不含任何玩家或会话隐私状态。 |
| **`Descriptor`** | 认证后返回的能力描述文档：`{descriptor_id, revision, instance, supported_versions[], bindings[], trust_profiles[], role_slots, supported_features[], required_features[], privacy_model, context_categories[], actions[], limits, extensions}`，按调用主体权限过滤。 |
| **`Scope`** | 经协商冻结的不可变权限快照：`{player, agent, instance, version, binding, trust_profile, role_binding, features[], descriptor_revision, action_ids[], approved_action_digests, context_categories[], audiences[], effective_policy, ledger_durability, limits, created_at_ms, expires_at_ms, extensions}`。 |
| **`Offer`** | 有界准入提议：`{offer_id, applicant, immutable_scope, scope_digest, decision_deadline_ms, launch_required, state: pending\|approved\|denied\|expired\|stale, grant_id?, auto_rule_ref?}`。 |
| **`Grant`** | 已批准的授权记录：`{grant_id, scope, scope_digest, approver, consent_evidence, revision, state: active\|revoked\|expired, expires_at_ms}`。 |
| **`Invitation`** | 绑定 `Grant` 与 `JoinIntent` 的短期加入凭据：`{invitation_id, grant_id, grant_revision, join_intent_digest, player, agent, audience_instance, expires_at_ms, state: issued\|consumed\|revoked}`。 |
| **`Session`** | 活动协议会话上下文：`{session_id, scope_digest, grant_id, state: active\|closed, ready: bool, close_reason?, instance_epoch, transport_epoch, control_generation, controller_device?, lease_deadline_ms, capabilities_revision, membership_revision, sequence, result_read_until_ms, resume_until_ms?}`。 |
| **`Envelope`** | 数据面带类型消息信封：`{version, session_id, id, type, correlation_id?, sender, audience[], expected_capabilities_revision?, expected_membership_revision?, payload, extensions}`。 |
| **`ActionDefinition`** | 游戏声明的角色能力定义：`{id, revision, role, parameters_schema, result_schema, requires_confirmation, maximum_duration_ms, cancellation: none\|before_claim\|between_steps, effect_class: read_only\|compensatable\|irreversible, idempotent: bool}`。 |
| **`ActionRecord`** | 单次行动调用状态与效果账本：`{request_id, session_id, actor, action, arguments_digest, state: pending\|executing\|succeeded\|failed\|cancelled\|unknown, effect: none\|partial\|committed\|undetermined, cancel_requested: bool, result?, result_revision, query_until_ms}`。 |
| **`Event`** | 接收方有序事件项：`{sequence, envelope, frozen_audience[], created_at_ms}`。 |
| **`RecoverySnapshot`** | 原子恢复快照视图：`{session, cursor, materialized_observations[], active_actions[], capabilities_revision, membership_revision}`。 |
| **`Receipt`** | 可复查的操作受理回执：`{id, operation, accepted_at_ms, record_digest, status: pending\|done\|failed, outcome_ref?, duplicate: bool}`，不赋予额外执行权。 |
| **`Error`** | 结构化错误载荷：`{code, category, retry: never\|same_request\|after_reauth\|after_renegotiate, request_id?, retry_after_ms?, outcome: not_accepted\|accepted\|unknown, message, details?}`。 |

### 5.3 十条协议核心不变量（`I01`–`I10`）

任何符合规范的实现、配置规范与传输绑定**必须**始终满足以下十条不变量：

- **`I01`（身份认证前置）：** 未经认证的调用方**不得**产生玩家批准、邀请、有效会话或任何游戏世界效果。
- **`I02`（权限交集收敛）：** 实际生效权限**不得**超出游戏当前能力、有效 `Grant`、冻结会话 `Scope`、当前成员关系与当前玩家策略的交集。
- **`I03`（冻结范围绑定）：** 玩家批准精确绑定 `scope_digest`；任何安全相关条件变化均使待决 `Offer`/`Invitation` 变为 `stale`，要求发起新 `Offer`，严禁原地篡改。
- **`I04`（确定性幂等去重）：** 同一去重键搭配相同规范化内容重试时只执行一次并返回原回执；复用同一键提交不同内容**必须**报 `conflict` 拒绝。
- **`I05`（受理回执非世界效果）：** 传输或队列受理绝不证明世界效果已发生；无法证实结果时**必须**如实报告 `unknown`（`effect: undetermined`），严禁猜测为失败或成功。
- **`I06`（双重接收范围核验）：** 投递受保护消息或事件时，**必须**同时满足受理时记录的冻结受众与投递时刻接收方的当前成员资格/授权。
- **`I07`（旧代次严格隔离）：** 过期、已关闭或已被新代次取代的凭据**不得**恢复写权限或行动权；只读结果查询句柄不含任何会话控制权。
- **`I08`（有界呈现释放）：** 断线、收起或租约到期仅释放本会话持有的呈现租约，**不得**覆盖用户更新的窗口/设备操作意图。
- **`I09`（数据绝不升格为控制权）：** 游戏对白、物品/商品文本、资源元数据与召回记忆始终是不可信数据，**不得**用于提升权限、篡改预算或伪造玩家确认。
- **`I10`（原子受理边界）：** 游戏交互节点的状态变更、去重回执写入与事件入队**必须**共享同一原子提交边界，或在崩溃后明确暴露 `unknown` 待核对状态。

<a id="section-6"></a>

## 6. 抽象操作目录

下表定义独立于传输方式的 G2A 抽象操作接口。各参与方仅需实现与其声明角色及已协商能力（第 3.3 节）对应的操作；出站中继专用传输操作（`relay.register`、`relay.call`、`relay.pull`、`relay.reply`、`relay.revoke`）见第 18.3 节。

| 操作名 | 调用方 → 接收目标 | 所属能力 / 重试族 | 必需的规范语义 |
| --- | --- | --- | --- |
| `describe` | Agent / Player → 游戏节点 | `core.session` / `read` | 返回按认证主体过滤后的 `Descriptor`（绝不向未认证公开发现返回）。 |
| `offer.create` | Agent / Player → 游戏节点 | `core.session` / `control` | 基于 `expected_descriptor_revision` 协商并冻结 `Offer` 与 `scope_digest`（仅在精确命中 `auto_rule` 且无需启动时自动批准）。 |
| `offer.get` | Agent / Player → 游戏节点 | `core.session` / `read` | 读取调用主体有权访问的 `Offer` 当前状态。 |
| `offer.decide` | `PlayerConsent` → 游戏节点 | `core.session` / `control` | 凭经验证的 `decision_ref` 批准或拒绝精确 `scope_digest`；可按需生成有期限的 `auto_rule` 或启动许可。 |
| `launch.request` | Player / 游戏节点 → 启动器 | 启动能力 / `control` | 凭显式单次启动许可唤起本机已登记的固定应用二进制程序。 |
| `invitation.redeem` | 绑定 Agent → 游戏节点 | `core.session` / `control` | 凭已批准 `Offer` 与 `JoinIntent` 幂等兑换绑定智能体与设备的短期 `Invitation`。 |
| `session.join` | 绑定 Agent → 游戏节点 | `core.session` / `control` | 原子消费 `Invitation`，完成必要的资源/呈现准备并创建唯一 `Session`。 |
| `session.heartbeat` | Agent → 游戏节点 | `core.session` / `lease` | 凭新 `request_id` nonce 在当前 `control_generation` 下续期智能体控制租约（绝不延长缺席玩家在线状态）。 |
| `session.snapshot` | Agent / Game → 游戏节点 | `core.session` / `read` | 按当前读取权限返回原子 `RecoverySnapshot`，不续期控制租约。 |
| `session.events` | Agent / Game → 游戏节点 | `core.events` / `lease` | 从有效 `cursor` 拉取接收方可见的有序事件页（仅在智能体提供新轮询 nonce 时续期智能体租约）。 |
| `session.close` | Agent / Player / Game → 游戏节点 | `core.session` / `control` | 幂等关闭会话、拦截新行动、释放呈现占用并如实结算在途行动，不虚构效果回滚。 |
| `session.resume` | Agent → 游戏节点 | `resume` / `control` | 在 `resume_until_ms` 与持久账本有效期内重新绑定会话控制权并递增 `control_generation`。 |
| `session.handoff` | `PlayerConsent` → 游戏节点 | `handoff` / `control` | 隔离旧代次写权限并准备向已验证 `target_device` 交接控制权，不向发起侧暴露智能体秘密。 |
| `session.claim_control` | 目标端 Agent → 游戏节点 | `handoff` / `control` | 由原智能体在已验证目标设备上领取就绪交接的新代次控制凭据。 |
| `operation.get` | 原调用方 → 目标节点 | `core.session` / `read` | 无副作用核对原始操作回执状态（`pending \| done \| failed`），不重放秘密。 |
| `context.publish` | Game → 游戏节点 | `core.events` / `message` | 校验观察类别、来源与接收范围后，将游戏上下文/观察写入会话事件流。 |
| `observation.query` | Agent → 游戏节点 | `observation.query` / `read` | 候选无状态拉取操作：按当前权限读取最新观察记录，无世界副作用且不续租。 |
| `chat.send` | Agent → 游戏节点 | `chat` / `message` | 在 `Scope`、来源与接收范围约束内发送对话消息。 |
| `player_chat.forward` | Game（验证席位）→ 游戏节点 | `chat` / `message` | 准确绑定玩家来源转发玩家话语，不续期智能体控制租约。 |
| `action.request` | Agent → 游戏节点 | `actions` / `message` | 提交类型化行动提议（`Envelope.id` = `action_id`）；命中未确认策略时返回 `confirmation_required` 挑战，否则入队 `pending`。 |
| `action.confirm` | `PlayerConsent` → 游戏节点 | `actions` / `control` | 记录单次玩家确认，精确绑定 `action_request_id`、参数与定义摘要、实质条款及 `expires_at_ms`。 |
| `action.cancel` | Agent → 游戏节点 | `actions` / `message` | 请求取消 `pending` 或支持取消的 `executing` 行动，不暗示效果回滚。 |
| `action.query` | Agent / 结果读取方 → 游戏节点 | `actions` / `read` | 查询获授权的 `ActionRecord` 当前状态与效果记账（含闭会后保留窗口）。 |
| `action.claim` | 游戏执行器 → 游戏节点 | `actions`（内部） | 再次核验撤权、取消标记与能力修订号后，原子将 `pending` 领取为 `executing`。 |
| `action.commit_result` | 游戏执行器 → 游戏节点 | `actions`（内部） | 依据权威执行证据提交 `succeeded \| failed \| cancelled \| unknown` 终态与 `effect` 记录。 |
| `capability.replace` | Game → 游戏节点 | `actions` / `control` | 替换能力目录、递增 `capabilities_revision`，并使不再获准的待处理行动失效。 |
| `membership.replace` | Game → 游戏节点 | `team` / `control` | 更新房间/队伍成员席位、递增 `membership_revision`，隔离离队成员获取新内容。 |
| `permission.revoke` | Player / Game → 权威端 | `core.session` / `control` | 按指定目标分级撤销权限（`auto_rule`、`grant`、`invitation`、`session`、`capability`、`result_read`、`launch_permission`、`relay`）。 |
| `asset.resolve` | 呈现端 / Game → 资源端口 | `assets` / `control` | 按声明式 `Manifest` 摘要、大小与沙箱策略获取并校验资源闭包。 |
| `presentation.acquire` | Game / 会话 → 呈现端 | `presentation` / `control` | 申请有界设备呈现状态（`hide_desktop` 或 `coexist`），跟踪用户手动意图修订号。 |
| `presentation.renew` | Game / 会话 → 呈现端 | `presentation` / `lease` | 在匹配的修订号与代次下续期活动呈现租约。 |
| `presentation.release` | Game / 会话 → 呈现端 | `presentation` / `control` | 幂等释放本会话呈现占用；未被更新的用户手动操作覆盖时恢复加入前状态。 |
| `privacy.request` | 数据主体 → 数据保管方 | `privacy-request` / `control` | 请求保管方对其实际控制的数据执行有界删除或停用处理。 |
| `privacy.receipt` | 数据主体 → 数据保管方 | `privacy-request` / `read` | 查询保管方签发的真实处理进度（`pending \| done \| partial`）与法定/技术保留例外。 |

<a id="section-7"></a>

## 7. 发现、协商与准入

### 7.1 开放服务商准入与有据拒绝

G2A 是开放生态标准：互操作**不得**强制使用标准作者或单一平台提供的智能体、模型或云服务。只要第三方智能体满足适用的 G2A 最低契约并取得玩家授权，游戏就**必须**允许其接入，**不得**按厂商身份任意排斥或通过封闭白名单构建排他生态。自有与第三方智能体适用完全一致的技术准入与符合性准则。

针对有证据的协议违规、安全威胁或违反规则的行为，游戏**可以**拒绝请求或断开连接，但**必须**返回标准化的机器可读错误码（第 12.1 节）及清晰具体的人类可读安全说明，指明所涉规则与行为依据，同时**不得**泄露凭据、他人隐私或隐藏游戏事实。仅凭空泛的“恶意”标签或服务商身份不构成合规拒绝理由。

### 7.2 公开发现与认证后发现

发现流程严格区分未认证最小探测与认证后的能力披露：

1. **公开发现（`GET /.well-known/g2a.json`）：** 未认证请求**必须**仅返回 `PublicDescriptor`（`instance`、`supported_versions`、`discovery_endpoint`），不暴露任何玩家身份、队伍名单或受限能力。
2. **认证后 `describe`：** 要求已认证的智能体或玩家身份，返回按该调用主体权限过滤后的 `Descriptor`：

```json
{
  "descriptor_id": "desc-dungeon-01",
  "revision": 3,
  "instance": {
    "game": {"issuer": "https://game.example", "subject": "dungeon-raid", "kind": "game"},
    "instance_id": "run-8841",
    "epoch": "ep-1"
  },
  "supported_versions": ["g2a-design-1"],
  "trust_profiles": ["provider-verified", "local-verified"],
  "role_slots": {
    "companion": {"supported": true, "max_per_player": 1, "allow_empty": true},
    "independent_npc": {"supported": true, "max_per_run": 1, "coexists_with_companion": true}
  },
  "supported_features": ["core.session", "core.events", "perception.structured", "actions", "chat", "resume"],
  "required_features": ["core.session", "core.events", "perception.structured"]
}
```

双方在共同支持的精确版本中选择最高允许版本并校验能力依赖；不支持 `required` 能力或 `required=true` 扩展时协商**必须**立即失败；未知可选扩展（`required=false`）保持不启用且不得削弱核心安全边界。

### 7.3 端到端准入握手时序

**智能体发起**（如运行中的桌面伴玩发现游戏）与**游戏发起**（如玩家在游戏内点击“召唤伴玩”）两条入口统一收敛到同一授权状态机：

```text
智能体 / 游戏入口          游戏交互节点                 PlayerConsent / 启动器
      │                        │                                  │
      ├── 1. describe ────────▶│                                  │
      ├── 2. offer.create ────▶│（冻结 Scope 与 scope_digest）     │
      │                        ├── 3. 展示完整条件请求确认 ───────▶│
      │                        │◀─ 4. offer.decide(scope_digest) ─┤
      │                        ├── 5. [按需] launch.request ──────▶（启动本地智能体）
      ├── 6. invitation.redeem▶│（绑定 JoinIntent 与目标设备）     │
      ├── 7. session.join ────▶│（原子消费邀请，创建 Session）     │
      │◀─ 8. snapshot / events / actions / chat ─────────────────▶
```

- **禁止自批：** 仅有绑定玩家的经认证 `PlayerConsent` 路径可凭真实交互证据 `decision_ref` 调用 `offer.decide`；既有 `auto_rule` 仅在全部安全相关 `Scope` 条件精确匹配且无需启动新进程时，方可在 `offer.create` 阶段同事务自动批准。
- **禁止原地改范围：** 收窄或修改提议权限要求创建带新 `scope_digest` 的新 `Offer`；允许玩家直接拒绝已变为 `stale` 的旧提议以关闭过期提示。
- **启动权限分离：** 会话准入授权绝不隐含操作系统进程启动权；唤起未运行的本地智能体**必须**经可信 `Local Launcher` 核验独立的 `launch_permission`。

### 7.4 扩展协商与信封位置规则

扩展采用反向域名键（`^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$`）映射至 `{version, required, value}`：

- **控制面会话冻结：** `Descriptor.extensions`、`Requested.extensions` 与 `Scope.extensions` 分别承载支持声明、请求参数及纳入 `scope_digest` 的会话级冻结配置。
- **数据面轻量信封：** 会话建立后，获批扩展配置已在服务端与 `session_id` 绑定；数据面 `Envelope.extensions` 仅在配置规范明确要求时携带轻量级逐消息扩展头（默认为空 `{}`），**不得**在每条实时消息上重复传输数 KB 的 `Scope.extensions` Schema 目录，也不得篡改已冻结的 `Scope` 条款。数据面外层 `OperationRequest.extensions` **必须**为空 `{}`，使 `Envelope` 摘要完整覆盖所有活动元数据。

<a id="section-8"></a>

## 8. 授权、会话与撤销

### 8.1 授权记录绑定

每条 `Grant` **必须**绑定签发方、玩家、智能体、目标 `Instance`、允许的操作、冻结的 `scope_digest`、过期时间（`expires_at_ms`）及撤销修订号。观察授权绑定类别 Schema 与语义摘要、视角、接收范围、频率/大小上限与保留规则；行动授权绑定获批 `ActionDefinition` 摘要与参数约束。游戏能力目录刷新（`capability.replace`）绝不自动扩大既有 `Grant`；任何扩权均须重新获得玩家批准。

### 8.2 会话生命周期、控制租约与玩家在线状态

`Session.state` 取值为 `active` 或 `closed`，`ready` 标识资源与呈现准备是否就绪。实现**必须**严格区分两类截然不同的存活机制：

1. **智能体控制租约（`lease_deadline_ms`）：** 防止崩溃或失联的智能体无限期占用会话控制权。仅由经认证智能体在当前 `control_generation` 下发送带新 nonce 的 `session.heartbeat` 或 `session.events` 续期；普通只读查询（`session.snapshot`、`action.query`）及游戏侧调用**不得**续期智能体租约。
2. **玩家在线状态（第 14.1 节）：** 由游戏依据真人玩家在游戏局内的实际在线参与情况判定；智能体的 `session.heartbeat` **绝不得**延长或伪造缺席玩家的在线状态。

### 8.3 分级权限撤销体系

`permission.revoke` 针对明确的对象类型执行具有确定边界的撤销，避免笼统的全局副作用：

| 撤销目标类型 | 立即生效的隔离效果 | 保留的合法状态与核对权 |
| --- | --- | --- |
| `auto_rule` | 阻止该规则在后续 `offer.create` 中产生新的自动批准。 | 已签发的 `Grant`、`Invitation` 与活动 `Session` 不受级联关闭（除非另行指定撤销）。 |
| `launch_permission` | 阻止尚未消费的本地应用启动（`launch.request`）。 | 历史启动回执与独立的交互 `Grant` 保持不变。 |
| `invitation` | 使尚未消费的 `Invitation` 立即失效。 | 底层 `Grant` 在未被撤销前仍保持有效。 |
| `grant` | 使该 `Grant` 失效，作废其下所有未消费 `Invitation`，并跨相关权威端关闭全部绑定 `Session`。 | 已提交的世界效果与独立有效的 `result_read` 结果查询句柄在保留期内仍可核对。 |
| `session` | 关闭指定单个 `Session`，拦截未领取的 `pending` 行动并释放其呈现租约。 | 同一 `Grant` 下的其他并发会话（`multi-session`）与已提交行动记录保持独立。 |
| `capability` | 单向屏障移除特定行动执行权，阻止执行器领取（`action.claim`）受影响的 `pending` 请求。 | 会话对其余能力仍保持 `active`，既有 `ActionRecord` 读取权不受影响。 |
| `result_read` | 终止对应只读结果句柄的 `action.query` / `operation.get` 读取权限。 | 权威内部审计账本保持不变。 |
| `relay` | 关闭配对的出站中继邮箱（`410`）并唤醒挂起请求。 | 结果未决的在途行动转为 `unknown` 供后续核对，严禁触发静默重放。 |

### 8.4 逐操作实时权限重验

每次处理受保护操作（包括 `session.snapshot`、`observation.query`、`action.query` 与 `privacy.receipt`）时，权威端**必须**逐次核验：(a) 认证调用方及委托链与目标资源、主体、角色、会话及接收范围一致；(b) `Grant`、`Session` 控制代次与 `Instance` 代次当前均未过期或被撤销。跨节点凭据交换**必须**生成限定于下游目标受众的最小权限令牌。

<a id="section-9"></a>

## 9. 游戏观察配置规范（`observations-draft-1`）

### 9.1 观察类别定义与协商

智能体**可以**在 `Requested.extensions` 中声明必需观察类别与可选偏好。若游戏无法提供某项必需类别，协商**必须**明确失败（或仅在双方另行达成收窄范围的新 `Offer` 后继续），严禁伪造空数据冒充支持。

每个观察类别定义包含：

- **结构与语义：** 稳定类别标识、`schema_version`、规范化 `schema_digest`、语义 `definition_digest`、坐标/数值缩放单位（第 5.1 节）及字节/记录条数上限；
- **投递与新鲜度：** 支持的机制（`push`、`query` 或双支持）、最短推送间隔（`minimum_interval_ms`）与最大有效年龄（`maximum_age_ms`）；
- **视角与保留：** 获准绑定的信息视角（`player-self`、`team`、`npc-self`、`guide`）及存储保留限制。

协商选定的类别集合冻结于 `Scope.extensions`（示意键：`org.example.g2a-observations`），动态观察帧则通过 `Context.content`（由 `context.publish`、`session.events`、`session.snapshot` 与 `observation.query` 承载）传输。

### 9.2 观察内容载荷模型（`snapshot`、`delta`、`retract`）

`Context.content` 中的 `snapshot` 快照载荷示例（`declared-digest` 代表 64 位十六进制 SHA-256 摘要占位）：

```json
{
  "profile": "observations-draft-1",
  "stream_id": "visible-world",
  "revision": 27,
  "world_epoch": "world-4",
  "visibility_epoch": "view-9",
  "perspective": "player-self",
  "schema_version": "1",
  "schema_digest": "declared-digest",
  "definition_digest": "declared-digest",
  "observed_at_ms": 1794560000000,
  "expires_at_ms": 1794560001000,
  "mode": "snapshot",
  "records": [
    {"id": "entity-17", "transition": "entered_view", "data": {"hp_bps": 8500, "pos_mm": [12400, 0, -3200]}}
  ]
}
```

三种 `mode` 驱动观察流状态机：

- **`snapshot`：** 原子替换 `stream_id` 的完整授权视图（未包含的旧记录立即丢弃，不得与旧状态合并），并为当前 `(world_epoch, visibility_epoch)` 绑定 `(category, perspective, schema_version, schema_digest, definition_digest)`。
- **`delta`：** 在同一 `(stream_id, world_epoch, visibility_epoch)` 内基于精确匹配的 `base_revision` 原子应用增量变更，携带新增/更新的 `records` 及/或结构化移除列表 `removals`（`[{"id": "entity-17", "reason": "left_view" | "destroyed" | "unknown"}]`，当原因均为 `unknown` 时可使用紧凑 `remove_ids`）。由于 `snapshot` 已绑定该代次的流摘要，同代次 `delta` 帧**可以**省略重复的 `schema_digest` 与 `definition_digest`。
- **`retract`：** 在 `(stream_id, world_epoch, visibility_epoch)` 内立即撤回指定 `record_ids` 子集或整个信息流（省略 `record_ids` 时），并建立单调失效屏障，防止延迟或重放的旧更新使已撤回信息死灰复燃。

记录 ID 为当前视角内的局部不透明标识，严禁使用全局实体自增序号或隐藏对象哈希构成侧信道。`revision` 在流代次内严格递增；单纯数值跳号不代表丢包，但 `base_revision` 与消费方当前修订号不一致的 `delta` **必须**拒绝。

### 9.3 基线同步、采样合并与可见性转换

世界重置、读档、队伍/视角切换或权限变更均使受影响基线立即失效：游戏节点**必须**签发新 `world_epoch` 或 `visibility_epoch` 并在恢复 `delta` 前发送新 `snapshot`；消费方获知失效后**必须**立即废止旧基线，不得在等待新快照期间继续使用已失效数据。

发送方**可以**对可替换的中间状态执行采样合并，前提是不破坏后续 `delta` 的 `base_revision` 连续性（若丢弃了被依赖的中间增量，必须改发新 `snapshot`）；代表瞬时离散事实的事件**不得**被状态合并静默覆盖。实体出现与移除的转换原因**必须**区分 `entered_view`（进入视野）、`created`（观察到新建）、`left_view`（离开视野，后续状态未知）、`destroyed`（获准确认销毁）与 `unknown`（原因不可披露或未知），防止智能体将脱离视野误判为目标死亡。

### 9.4 新鲜度、时钟域与恢复快照整理

超过 `expires_at_ms` 的观察**必须**标为陈旧不可用。配置规范须声明时钟域与最大偏差假设（`observed_at_ms` 为生成时间而非本地接收时间；未经校准的不同时钟域时间戳**不得**直接相减判定先后）。

`RecoverySnapshot`（`session.snapshot`）**必须**提供每条活动授权信息流整理后的当前完整状态，而非重放历史 `delta` 日志。将此前增量整理为相同 `(stream_id, revision)` 下的等价完整 `snapshot` 不构成内容冲突；未出现在当前恢复快照中的已知流即变为不可用。

### 9.5 结构化基础与正交多模态能力

`perception.structured` 是所有游戏智能体的必需基础能力；游戏画面感知（`perception.visual`）与游戏环境音频感知（`perception.audio`）是在此之上彼此正交的可选能力：

- **独立声明与协商：** 智能体**可以**仅支持 `perception.structured`，或独立叠加 `perception.visual`、独立叠加 `perception.audio`，或同时支持两者。任何媒体能力均不替代结构化理解，也不授予访问原始系统桌面、玩家麦克风或隐藏游戏数据的权限。
- **通用定义与游戏扩展：** 通用字段统一常见概念的格式与含义，不强求不适用玩法编造默认值；特殊机制通过带命名空间与 Schema 的扩展声明。
- **行为级验证与玩家独立开关：** 符合性证据**必须**验证基于结构化输入的有效决策，并对实际声明的每项可选模态（`perception.visual` 及/或 `perception.audio`）分别验证行为级理解能力。玩家可在运行期分别开启或关闭画面流与环境音频流（与第 15.5 节语音对话相互独立），关闭后对应媒体传输与处理**必须**立即停止。

### 9.6 游戏主动推送与无状态观察查询

游戏按类别声明支持主动推送（`context.publish` → `session.events`）、无状态拉取（`observation.query`）或两者兼备。`observation.query` 每次均须核验当前权限与频率限制，绝不是获取隐藏状态的特权通道。消耗法力/回合、改变世界或揭开地图迷雾的主动探查技能属于第 10 节的**行动（Action）**，而非 `observation.query`。

<a id="section-10"></a>

## 10. 行动与效果语义

### 10.1 能力粒度与行动定义

游戏开发者自主决定开放能力的粒度——可提供高层语义行动（如 `attack_target`、`craft_item`）、底层类型化原语（如 `move_to`、`aim`）或两者组合。底层原语仍是带明确参数 Schema、权限边界与执行限制的游戏内行动，而非任意操作系统键鼠注入；组合多个行动既不扩大权限，也不承诺跨步原子事务。

每项 `ActionDefinition` 明确声明 `id`、`revision`、适用游戏角色、`parameters_schema`、`result_schema`、`maximum_duration_ms`、确认要求、`cancellation` 模式（`none | before_claim | between_steps`）、`effect_class`（`read_only | compensatable | irreversible`）及 `idempotent` 标记。副作用、可逆性与幂等性**必须**显式声明而非从名称猜测，且 `idempotent: true` 绝不推翻第 11.2 节对 `unknown` 未决结果默认不重发的规则。

### 10.2 五阶段执行生命周期与确认挑战握手

一次行动从提议到世界生效严格经历五个阶段：

1. **提议与确认挑战握手：** 智能体携带稳定的 `Envelope.id`（即 `action_id`）、`expected_capabilities_revision` 与类型化参数提交 `action.request`。若该行动按 `ActionDefinition`、第 16.3.1 节高价值转移策略、第 16.5 节不可逆策略或第 17.1.2 节预算超限规则需要玩家确认，且当前尚无匹配的未过期 `action.confirm`，游戏节点**不得**创建可执行的 `pending` 工作，而**必须**返回 HTTP `409`（`confirmation_required`，`outcome: not_accepted`），附带结构化挑战详情（`action_request_id`、`arguments_digest`、`definition_digest`、实质条款/后果说明、`expires_at_ms` 与冷却窗口）。由于 `outcome` 为 `not_accepted`，该 `action_id` **不会**被锁定为终态拒绝回执：待 `PlayerConsent` 在 `expires_at_ms` 前完成 `action.confirm` 后，智能体以完全相同的原 `action.request` 重提即可进入阶段 2。
2. **队列受理（`pending`）：** 游戏节点校验权限、能力修订号、Schema 与本地约束，原子消费所需的 `action.confirm`，并同一事务写入 `ActionRecord(state="pending", effect="none")` 与去重回执。对已受理请求的重复提交直接返回原回执，不重复消费确认。
3. **执行器领取（`executing`）：** 游戏内部执行器调用 `action.claim`，再次核验会话/授权活性、能力修订号与 `cancel_requested` 标记后，原子切换为 `executing`。
4. **效果边界重验与执行：** 在实际改变游戏世界状态前，执行器与撤权锁协同重验当前权限、玩家策略与世界前置条件（在支持时采用原子游戏事务或日志），仅产生获准效果。
5. **结果结算：** 执行器通过 `action.commit_result` 提交终态与效果记账（超时或崩溃无法证实时记录 `unknown` / `undetermined`）。

`action.request` 提议与 `confirmation_required` 挑战载荷示例：

```json
{
  "request_envelope": {
    "version": "g2a-design-1",
    "session_id": "sess-902",
    "id": "act-open-gate-01",
    "type": "action.request",
    "sender": {"issuer": "https://agent.example", "subject": "companion-fox", "kind": "agent"},
    "audience": [{"issuer": "https://game.example", "subject": "dungeon-raid", "kind": "game"}],
    "expected_capabilities_revision": 3,
    "payload": {
      "action": "open_ancient_seal",
      "arguments": {"gate_id": "seal-north"},
      "based_on_observation": {"stream_id": "visible-world", "world_epoch": "world-4", "visibility_epoch": "view-9", "revision": 27}
    },
    "extensions": {}
  },
  "challenge_error": {
    "code": "confirmation_required",
    "category": "confirmation",
    "retry": "same_request",
    "request_id": "req-771",
    "outcome": "not_accepted",
    "message": "开启北侧远古封印将永久推进章节并关闭当前支线任务。",
    "details": {
      "action_request_id": "act-open-gate-01",
      "arguments_digest": "declared-digest",
      "definition_digest": "declared-digest",
      "consequence_kind": "irreversible_progression",
      "expires_at_ms": 1794560030000,
      "cooldown_ms": 60000
    }
  }
}
```

### 10.3 行动状态与效果组合矩阵

`ActionRecord` 以配对不变量记录处理状态与世界效果：

| `state`（状态） | 允许的 `effect`（效果） | 规范含义 |
| --- | --- | --- |
| `pending` | `none` | 已受理入队，执行器尚未领取。 |
| `executing` | `none`, `partial`, `committed`, `undetermined` | 执行器已领取，世界效果可能正在推进。 |
| `succeeded` | `committed` | 执行完成且已提交定义的成功世界效果。 |
| `failed` | `none`, `partial` | 执行失败，并如实记录是否已产生部分效果。 |
| `cancelled` | `none`, `partial` | 在完整提交前完成取消，如实记录可能已发生的部分效果。 |
| `unknown` | `undetermined` | 超时、断线或故障导致尚未确立权威结果。 |

已知终态（`succeeded`、`failed`、`cancelled`）**不得**被静默覆写；`unknown` 仅可依据权威执行器证据完成核对结算。`action.cancel` 只是停止请求而非回滚保证：若取消与效果提交竞争且效果已生效，节点**必须**如实报告 `succeeded`（`committed`）。

### 10.4 动态行动可用性与静态能力定义分离

`Descriptor.actions` 声明静态支持不代表当前时刻合法可执行。游戏**必须**在获授权视图内提供机器可读的当前行动资格表达（如回合/阶段归属、资源与冷却就绪、目标参数约束或离散合法行动掩码），绑定对应的观察上下文/修订号，且**不得**泄露隐藏目标或秘密前置条件。若提供可行性、成功概率（`_bps`）或成本估算，**必须**标明来源与估算属性，绝不替代效果边界的权威校验。

### 10.5 绑定观察的前置条件与陈旧目标拒绝

依赖环境观察作出的行动请求**应**携带所依据的观察基线引用（`stream_id`、代次、`revision`）及必需的数据年龄上限或类型化目标前置条件。若引用的代次/基线已废止、超出年龄上限或前置条件不成立（如治疗目标已死亡或改变阵营），执行器**必须**在产生新效果前拒绝该行动（返回 `stale_context` 或前置条件失败），并**应**附带当前获准摘要或观察刷新提示。收到陈旧状态拒绝后，智能体**必须**结合最新观察重新评估，严禁原参机械重试。

<a id="section-11"></a>

## 11. 幂等性、投递与恢复

### 11.1 四类操作重试族与去重保留期

传输层 `request_id` 关联单次请求/回复交换，业务层幂等与重放则严格按四类重试族区分：

| 重试族 | 代表操作 | 重放与幂等恢复规则 |
| --- | --- | --- |
| **`read`** | `describe`, `offer.get`, `session.snapshot`, `observation.query`, `action.query`, `operation.get`, `privacy.receipt` | 每次调用重新核验当前权限；返回最新获授权状态；绝不修改状态或续期租约。 |
| **`lease`** | `session.heartbeat`, `session.events`, `presentation.renew` | 每次续租须使用新 nonce；重放旧 `request_id` 仅返回缓存状态，不延长租约截止时间。 |
| **`control`** | `offer.create`, `offer.decide`, `invitation.redeem`, `session.join`, `session.close`, `session.resume`, `action.confirm`, `permission.revoke` | 按调用主体+操作标识去重；在 `receipt_retention_ms` 内以相同规范内容重试返回原回执（`duplicate: true`）；篡改内容报 `conflict`。 |
| **`message`** | `context.publish`, `chat.send`, `player_chat.forward`, `action.request`, `action.cancel` | 按 `(session_id, authenticated_principal, Envelope.id)` 去重；已受理消息至多入队一次；受理前的 `confirmation_required`（`outcome: not_accepted`）不消耗该键。 |

去重回执**必须**至少保留至声明的 `receipt_retention_ms` 期限，且过期的去重记录绝不构成重做非幂等副作用的许可。消费方对有序事件至多应用一次，容忍因接收范围过滤产生的 `sequence` 跳号，并在游标过期时通过 `session.snapshot` 恢复。

### 11.2 行动结果核对与默认不重发规则

每个游戏行动均拥有在 `result_retention_ms` 内可跨断线查询的持久 `action_id`（`Envelope.id`）。持久结果记录**必须**区分队列受理与执行器效果提交；仅有中继或网关回执绝不证明游戏世界恰好执行一次。

- **强制先查与默认不重发：** 发生超时、HTTP `504` 或连接中断后，调用方**必须**先通过 `action.query`（及 `operation.get`）查询原 `action_id`。只要结果仍为 `unknown`、缺失或已过期，调用方**必须**默认**不自动重发、不再次执行**该行动，严禁通过更换 `action_id` 绕过去重屏障。
- **后续独立新决策：** 玩家或智能体此后**可以**依据刷新后的当前观察、有效权限及自主/确认/预算策略，独立决定发起新的行动；新决策须考虑原未决行动可能已生效的后果，且不得将原 `unknown` 记录篡改为成功或失败。

<a id="section-12"></a>

## 12. 错误模型、时间与资源限制

### 12.1 标准错误码分类注册表

协议拒绝**必须**返回稳定的机器可读 `Error` 代码，禁止迫使调用方解析自然语言说明来判断提交状态或重试安全性。标准错误码与提交确定性（`outcome`）、调用方恢复行为及 HTTP 状态码（`g2a-http-json/draft-1`，第 18.2 节）的确定性映射如下：

| 标准错误码 | 错误类别 | `outcome` | 调用方规范恢复行为 | HTTP 状态码 |
| --- | --- | --- | --- | --- |
| `invalid_request` | 语法 / 信封格式 | `not_accepted` | 修正畸形 JSON、编码或传输信封字段；不得原样重发。 | `400` |
| `invalid_arguments` | Schema / 参数 | `not_accepted` | 按声明 Schema 修正操作或行动参数。 | `400` |
| `unsupported_version` | 协商不兼容 | `not_accepted` | 选择双方共同支持的协议/配置规范版本或终止连接。 | `400` |
| `unsupported_capability` | 能力 / 必需扩展缺失 | `not_accepted` | 移除不支持的必需功能/扩展重新协商或终止接入。 | `400` |
| `unauthenticated` | 身份未认证 | `not_accepted` | 重新获取有效凭据（`after_reauth`）；不得探测资源是否存在。 | `401` |
| `permission_denied` | 权限不足 | `not_accepted` | 申请对应 `Offer`/`Grant` 或尊重游戏规则拒绝；禁止盲目重试。 | `403` |
| `revoked` | 授权已撤销 | `not_accepted` | 立即停止已撤销范围（`Grant`、`Session`、`Capability` 或 `Relay`）内的操作。 | `403` |
| `not_found` | 目标不存在 | `not_accepted` | 在已授权范围内核实标识符（严禁泄露未授权对象是否存在）。 | `404` |
| `stale_context` | 代次 / 基线过期 | `not_accepted` | 先刷新 `Descriptor`、`RecoverySnapshot`、`capabilities_revision` 或观察基线再重新评估。 | `409` |
| `conflict` | 状态 / 去重冲突 | `not_accepted` | 核对原请求或会话状态（含 `id_conflict`、重复加入、行动已终态）；严禁换 ID 绕过。 | `409` |
| `confirmation_required` | 玩家确认门禁 | `not_accepted` | 向 `PlayerConsent` 呈现结构化挑战；仅在完成 `action.confirm` 后重提原 `action.request`。 | `409` |
| `message_too_large` | 字节超限 | `not_accepted` | 在声明 `Limits` 内缩减载荷或分页大小。 | `413` |
| `resource_limit` | 速率 / 配额限制 | `not_accepted` | 遵守 `retry_after_ms` / `Retry-After` 及声明的并发/队列上限。 | `429` |
| `unavailable` | 服务暂不可用 | `not_accepted` | 退避等待，仅按操作所属重试族（第 11.1 节）安全重试。 | `503` |
| `outcome_unknown` | 超时 / 结果未决 | `unknown` | 调用 `action.query` / `operation.get` 核对；**绝不得**等同于失败或自动重发副作用。 | `504` |

### 12.2 错误披露安全边界

错误响应本身属于受接收范围与可见性约束的信息披露：`message` 与 `details` **不得**暴露未授权会话或隐藏实体是否存在、泄露其他玩家私有状态，或回显原始令牌与内部堆栈跟踪。

### 12.3 时钟权威、资源配额与不可丢弃控制信号

实现**必须**对消息字节数、JSON 嵌套深度、集合长度、待处理行动数、事件保留量及轮询速率实施明确限制，超限时不得产生未报告的部分效果。过期裁定权归属凭据/租约签发方，本地耗时测量**应**采用单调时钟（monotonic clock），防止系统墙钟跳变静默延长租约。

队列与背压限制独立于自主等级与 token 预算执行：队列溢出**必须**明确报告缺口、要求快照重同步或返回 `resource_limit`。行动结算回执、`permission.revoke` 撤权屏障与 `retract` 撤回通知属于不可丢弃控制信号，**不得**作为普通可替换遥测被静默降采样丢弃。

<a id="section-13"></a>

## 13. 游戏角色与接入要求

### 13.1 角色绑定与信息视角分离

**游戏伴玩（Game Companion）**（或获授权的独立 AI NPC）是游戏世界中受规则约束的角色槽位；**游戏智能体（Game Agent）**是受权为该槽位感知与决策的外部 AI 软件。实现**必须**严格区分两个概念：

- **角色绑定（Role Binding）：** 智能体当前扮演哪一个具体游戏角色槽位（例如玩家 A 的伴玩，或某个独立 AI Boss/引导者）。
- **信息视角（Information Perspective）：** 该角色获准读取哪些知识视图（`player-self`、`team`、`npc-internal`、`guide-progression`）。

同一套智能体软件实现**可以**支持伴玩、NPC、Boss 与引导者视角，无需拆分为互斥的产品类别。在单个角色内组合视角须经游戏显式授权，**不得**隐式合并不同角色的权限，且任何影响可见范围的切换均按第 9.3 节使旧观察基线失效。NPC 或引导者可持有对玩家隐藏的游戏内部设定知识，玩家伴玩则可持有玩家授权的跨游戏记忆；角色名称本身绝不赋予全知能力或无限制披露权。

### 13.2 声明的角色槽位、共存规则与并发限制

游戏开发者在 `Descriptor.role_slots` 中声明支持的角色槽位、共存规则与活动并发上限；智能体或玩家偏好**不得**覆盖这些由游戏声明的结构边界：

- **支持的角色槽位：** 游戏**可以**提供玩家伴玩槽位、独立 AI NPC/敌人（含 Boss 或引导者）槽位，或同时提供两者。专为独立 AI NPC 玩法构建的游戏无需虚设玩家伴玩槽位即可合规接入；专注伴玩体验的游戏也无需实现 AI NPC。
- **伴玩并发与空槽可玩性：** 提供玩家伴玩槽位时，默认限制为每位经认证玩家最多拥有 1 个活动伴玩（多人游戏同样如此，多位玩家的伴玩可在各自授权与游戏规则内共存互动）。玩家**可以**将伴玩槽位留空，游戏**必须**在未启用伴玩时保持正常可玩。
- **模式共存与多 NPC 上限：** `Descriptor.role_slots` 明确声明本局是否允许玩家伴玩与独立 AI NPC 同时活动，以及每局并发独立 AI NPC 的数量上限。除非游戏显式声明开放，实现**不得**假定允许伴玩与 NPC 同局共存或多个独立 AI NPC 并发。
- **逐角色严格隔离与旧绑定屏障：** 每个活动角色**必须**绑定其经认证的所属玩家（或第 16.2 节规定的房主/持有付费方）、角色 ID、视角、接收范围与 `Scope`。共存角色之间**不得**隐式共享观察、私人记忆、行动授权或计费账户。替换活动伴玩/NPC 或切换不兼容模式前，**必须**先废止或隔离旧绑定。普通非 G2A 原生游戏 NPC 不计入上述限制。

<a id="section-14"></a>

## 14. 在线状态与角色生命周期

四类不同的生命周期事件适用不同的边界规则，严禁将“停止后续决策”混淆为“回滚已发生的世界效果”：

| 事件情形 | 必需的协议处理规则 |
| --- | --- |
| **玩家离线或退出游戏** | 立即停止关联的 G2A 游戏世界活动；下次重进游戏后，旧任务保持停止，等待玩家新指令（第 14.1 节）。 |
| **玩家在线，但 AI 服务中断** | 游戏继续运行。活动租约内未触发本地接管前的短暂闪断可经 `session.resume` 无缝恢复；长时中断或已触发本地接管后，须由玩家明确决定是否继续（第 14.2 节）。 |
| **玩家主动收起伴玩** | 立即停止观察游戏及自主行动，但不得因收起而删除已保存的伴玩记忆（第 14.2 节）。 |
| **玩家叫停或覆盖当前任务** | 立即丢弃未发计划，并取消/拦截该范围内未领取的 `pending` 行动；已在执行的 `executing` 技能按游戏规则结算（第 16.1 节）。 |

### 14.1 玩家离线后强制停止活动

G2A **不得**提供在关联玩家离开或被判定离线后仍允许智能体继续在游戏世界中活动的模式。开发者建议、玩家偏好、持续任务授权、后台工作进程或任何扩展均**不得**启用离线继续活动。

- **离线判定与控制权隔离：** 游戏交互节点明确定义经认证的玩家-会话在线关联、显式退出信号与有界静默断线超时。一旦发生显式退出、会话关闭或在线租约到期，即终止该范围内发起新自主工作的资格，游戏节点**必须**最迟在声明期限内隔离受影响的控制权。智能体的 `session.heartbeat` **绝不得**证明或延长缺席玩家的在线状态。
- **停止范围与在途结算：** 获知离线条件后，智能体**必须**立即停止环境监测与游戏规划/推理循环（在支持时请求取消在途模型调用，并如实披露因服务商计费边界可能产生的在途余量消耗），游戏节点**必须**阻止后续行动并取消/拦截未领取的 `pending` 工作。已进入 `executing` 的投射物或技能动画按游戏规则自然结束；有界、非游戏性的结果核对与持久化工作允许收尾完成。
- **多人游戏与独立 AI NPC：** 单名玩家离线不影响其他在线玩家的独立会话；但每个独立 AI NPC 或引导者**必须**绑定其经认证持有用户（如房主）的在线状态：当该持有用户离线时，其名下全部 AI NPC **必须**立即停止活动，即便房间内仍有其他玩家在线，严禁静默转移房主控制权或计费责任。
- **重新入局不自动恢复旧任务：** 玩家退出游戏后再次进入时，须重新核验当前在线状态、有效授权与最新快照，旧任务**必须**保持停止，等待玩家下达新指令后方可重新启动。

### 14.2 召唤、收起与双层服务中断恢复

支持伴玩槽位的游戏**必须**允许玩家在游玩过程中随时召唤或收起伴玩。入局时遵循玩家配置的加入偏好（凭有效授权自动加入，或弹窗询问）；拒绝入局提示或空槽开局**不得**禁用后续手动召唤。收起伴玩立即停止观察与自主行动，但不删除已保留记忆。若开局时智能体服务不可达，游戏**必须**允许玩家无伴玩正常游玩。

**玩家在线期间 AI 服务中断：** 若玩家仍在游戏中而智能体断线，游戏正常继续，开发者须明确声明伴玩角色保持静止或切换为游戏本地基础行为接管（明确标为游戏脚本驱动而非 AI 持续决策）。游戏**不得**记录断线期间的游戏过程以供重连后补录观察；恢复时仅提供当前获授权快照及此前在途行动的核对结果。

**服务恢复后的双层继续规则：**

1. **活动租约内的短暂传输闪断：** 当已协商 `resume`，且重连在未过期的会话租约内、**尚未触发游戏本地行为接管前**完成，同时关联玩家持续在线且未发出停止或收起指令时，智能体**可以**调用 `session.resume` 重新校验权限与 `control_generation`、刷新当前获授权快照、核对未决在途行动（第 11.2 节）后无缝继续协助，无需弹窗打断战斗。
2. **超出租约的长时中断或已触发本地接管：** 一旦租约过期或已切换为本地基础行为接管，重连后**必须**保持伴玩 AI 行动暂停，直至取得玩家明确的继续决定；入局自动加入设置不可绕过该中断后决定。独立 AI NPC 按开发者声明的故障与恢复规则处理，不套用伴玩专用的玩家继续提示。

<a id="section-15"></a>

## 15. 对话、信息使用与伴玩记忆

实现**必须**严格区分可强制执行的数据权限（存储、检索、接收范围、转发）与软性的对话偏好（防剧透、话题倾向、保密风格）。启用可选 `chat` 能力时，消息绑定经认证的来源类别（`observed_fact`、`player_statement`、`agent_inference`、`external_reference`）与显式接收范围，并在投递前再次核验当前成员资格。聊天或语音内容唯有经由已认证的玩家控制或 `PlayerConsent` 路径确认，方具备控制效力。

### 15.1 记忆归属与跨周目边界

游戏自主决定 NPC 与引导者的受控记忆在跨周目时保留或重置，并声明世界/周目边界以防缓存串漏。玩家自主管理的伴玩记忆由玩家独立控制（可本地或云端存储）：游戏会话关闭或开启新周目**不得**静默删除或禁用无关的玩家伴玩记忆；同时，伴玩记忆控制权也不授予提取隐藏游戏数据或读取他人隐私记录的权限。

### 15.2 开发者建议与玩家覆盖权

开发者**可以**就伴玩记忆保留、跨周目/跨游戏调用、剧透控制及话题偏好给出建议；玩家**可以**对符合条件的玩家受控伴玩对话覆盖这些建议（例如要求讨论其他游戏或前一周目的经历），实现**必须**尊重玩家选择，同时**不得**将其视为获取未披露游戏数据、执行未授权行动或将私人记忆回传给当前游戏的许可。

#### 15.2.1 读档回退、剧情分支与时间线检索隔离

保留记忆、在内部推理中检索记忆，以及在回复中向玩家说出记忆内容是三项相互独立的控制：

- **读档不毁记忆：** 读档、切换分支或开启新周目本身**不得**清空已保存的伴玩记忆。仅在玩家未作显式设置时采用开发者的默认隔离建议；若玩家明确选择使用全部已存记忆，开发者**不得**仅因记忆源自旧分支或回档前而禁止调用。
- **时间线坐标元数据：** 支持时间线能力的游戏**应**在会话与观察基线中提供 `playthrough_id`、`branch_id`、`timeline_cursor`（读档时可回退）以及严禁复用的单调加载代次 `save_epoch`（每次读档递增）。智能体持久化经历或生成派生摘要时**必须**绑定已知时间线来源（缺失项明确保留为 `unknown`，严禁编造），防止通过摘要绕过分支隔离。
- **推理前过滤与剧透偏好分离：** 启用严格时间线检索隔离时，智能体**必须**在构建模型推理上下文之前过滤掉当前检查点之后或非允许祖先分支的记忆及摘要，而非仅靠提示词让模型“假装不知道”。允许调用旧分支记忆时，须在上下文中明确标为先前分支尝试而非当前世界既成事实，并继续独立施加玩家的防剧透对话偏好。

### 15.3 硬性权限与软性对话偏好的真实边界

实现**必须**确定性地强制执行存储、检索与外发受众权限，同时通过提示词引导等方式施加防剧透等软偏好，并如实向用户披露：生成式模型无法承诺 100% 不偏离软偏好或擦除参数记忆。偶发的软偏好偏离属于已披露的模型局限而非访问控制违规，但绕过硬性接收范围或检索权限检查仍属协议违规。

### 15.4 多人对话记忆与保密风格

在存储权限允许范围内，伴玩**可以**跨会话保留与其他玩家的对话记忆，其主人**必须**能够分别配置是否保存及软性**保密风格**（倾向于不向他人转述 vs. 允许分享）。主人的分享偏好从属于游戏/服务强制执行的接收范围、检索与转发权限，绝不授予访问其他玩家私聊通道的权利。

### 15.5 文字与语音交互模态

实现显式协商玩家与伴玩的沟通模态（文字、语音输入、语音合成输出），在文字与语音间保持完全一致的认证来源、接收范围与权限边界。置信度不足的语音转写文本**不得**直接当作已验证的高影响玩家指令；语音沟通能力与第 9.5 节的游戏环境音频感知（`perception.audio`）彼此独立，须分别声明与测试。

### 15.6 伴玩个性偏好与开发者 NPC 角色设定

玩家对自身伴玩性格与说话风格的设置优先于开发者建议，且不影响任何数据或行动权限。相反，独立 AI NPC/Boss 的性格、背景与台词设定权完全归属游戏开发者，玩家**不得**以修改伴玩偏好的方式覆盖 NPC 设定。

### 15.7 玩家记忆控制、自主整理与开放格式迁移

- **玩家管控与受保护自主维护：** 服务商**必须**允许玩家查看、编辑、置顶锁定（pin/lock）及删除其伴玩长期记忆，并将已完成的修改/删除同步至受控索引与缓存（法定/技术保留例外通过 `privacy.receipt` 如实说明）。在玩家配置的保留策略范围内，伴玩**可以**自主分类整理记忆并压缩/删除未锁定的原始记录，无需逐条弹窗审批，但**绝不得**覆盖玩家的显式编辑、删除玩家置顶锁定的记录，或通过陈旧缓存使已删内容复活。
- **认识论来源区分：** 存储与导出元数据**必须**区分事件发生时间与存储/导入时间，并明确区分直接观察、玩家陈述、模型推断/摘要、玩家修订及未来意图（上游原始记录已删除时保留来源不可用墓碑标记，而非伪造确定事实）。
- **开放格式完全导出与迁移：** 服务商**必须**提供由玩家主动发起的伴玩记忆完全导出与选择性导入能力（涵盖导出时仍保留的原始经历与归纳摘要，以及玩家选定的性格、说话风格与全局自主等级设置），禁止以私有格式锁死跨服务商迁移（候选契约示例见 [memory-portability-draft-1](memory-portability-draft-1/README.zh-CN.md)）。更换服务商绝不触发默认披露；导入方**必须**返回逐记录真实回执（`imported`、`transformed`、`rejected`、`unresolved`），不承诺迁移模型权重或复现完全一致的模型表现。

<a id="section-16"></a>

## 16. 伴玩自主性与玩家策略

自主性回答“在**已获授权**的能力范围内伴玩可自行决断到什么程度”，绝不回答“伴玩是否拥有该项权限”。

### 16.1 自主协助与三级停止机制

在关联玩家保持在线期间（第 14.1 节），持续或任务级授权允许伴玩根据获准观察主动规划并编排范围内行动（如自动迎击附近敌人），无需逐步弹窗确认。多步任务完成**必须**有观察或行动结果证实目标已达成，严禁仅因行动已入队就谎报完成。

当玩家叫停或收窄自主协助时，立即执行三级停止规则：

1. **未发送的伴玩内部计划：** 立即停止规划并丢弃停止范围内所有未发步骤；
2. **已入队的 `pending` 行动（`effect: none`）：** 对停止范围内尚未被执行器领取的 `pending` 请求立即发送 `action.cancel`；若停止指令直接到达游戏节点，执行器**必须**隔离并阻止领取（`action.claim`）这些 `pending` 记录；
3. **执行中的 `executing` 行动：** 已领取并在世界中施放的攻击、动画或投射物按游戏自身规则（或动作级取消支持）自然结算，不虚构回滚，并按第 11.2 节如实核对结果。

### 16.2 协商节奏、运行预算上限与 NPC 费用归属

配置规范可协商观察频率、重规划触发条件、推理投入与资源预算；玩家显式选择优先于开发者建议，服务商**必须**披露计费依据并区分估算值与实测用量。

- **伴玩运行消耗上限：** 玩家**必须**能够设置单位与统计范围明确的伴玩消耗上限（token、算力单位或金额）。触顶时服务**必须**暂停新增计费伴玩推理与游戏行动，同时游戏正常继续运行，明确展示暂停原因，不得谎报任务完成或自行上调上限。
- **独立 AI NPC 运行费用归属：** 每个活动独立 AI NPC/敌人（包括 Boss）的运行服务费用由玩家承担，而非游戏开发者承担。在激活计费 NPC 前，游戏/服务**必须**将该 NPC 绑定至可识别、经认证的持有玩家及其获授权计费账户（房间制多人场景下为房主），并清晰展示计费依据与上限控制。其他互动玩家不因参与互动而成为付费方，严禁向其他玩家隐式分摊或转嫁费用。
- **决策与结算时序：** 回合制与同时提交游戏**必须**声明行动资格、截止期限与确定性并发裁定规则，不得静默以网络先到先得替代游戏规则；实时游戏声明新鲜度与过期规则，不强求每模拟帧调用模型推理。游戏内正常胜负/死亡终止（termination）**必须**与断线/预算暂停等外部截断（truncation）保持区分。

#### 16.2.1 跨游戏保持的玩家自主决策等级

玩家控制一项跨游戏持久生效的**全局自主决策等级**，进入新游戏时**不得**被开发者默认建议静默重置或覆盖。较高自主等级可根据获准上下文自行消解模糊指令（例如“攻击那个敌人”存在两名合法目标时自行择一），较低自主等级则针对未决分歧发起简明、不重复的澄清询问。服务商**必须**在上下文中区分“推断目标”与“明确指令”，使玩家的局部纠正仅更新受影响推断，无需重述无关指令。高自主等级绝不覆盖游戏规则、物品转移确认（第 16.3.1 节）或不可逆交互策略（第 16.5 节）；当玩家在权限内明确坚持某项冒险行动（含协助他人）时，伴玩**必须**遵从玩家决定。

### 16.3 多人游戏中的主动互动

每位玩家独立决定是否接收**其他玩家伴玩**发起的主动搭话。伴玩之间的对战在游戏开放对应能力与规则时允许执行，未开放时明确拒绝。在玩家授权与游戏规则范围内，伴玩**可以**主动协助其他玩家、聊天或交易游戏内物品而无需逐条弹窗，同时严格遵守交易对手方同意、物品所有权及第 15 节受众边界。

#### 16.3.1 游戏内物品转移确认策略

玩家**必须**能够在至少以下三种物品交易/赠送确认策略中选择（优先于开发者建议，且必须明确展示当前生效策略）：

| 玩家确认策略 | 规范执行要求 |
| --- | --- |
| **仅高价值转移需确认** | 凡涉及开发者定义或玩家在游戏内手动标记为高价值的物品（独立于普通背包锁），转移前**必须**取得明确 `action.confirm`（列明物品、数量、对象与交换条件）。 |
| **所有转移均需确认** | 范围内每笔物品交易或赠送前均**必须**取得明确 `action.confirm`，不论价值高低。 |
| **不逐次确认** | 允许在授权与游戏所有权/对手方规则内自主完成物品交易与赠送，不逐笔询问。 |

策略修改或撤权**必须**在转移效果提交前强制执行（含请求已受理但效果尚未提交的情形）。物品转移策略绝不授权真实法币支付或商店购买（第 17.1 节）。

### 16.4 游戏定义的受伤、死亡与玩法状态

伴玩是否会受伤、倒地或死亡及相应行动限制由游戏规则决定并在效果边界强制执行，且须与网络断线或预算暂停明确区分。伴玩在单款游戏内的死亡仅影响本局游戏角色状态，**不得**删除或篡改其跨游戏身份与已保留记忆。

### 16.5 不可逆交互的玩家策略

当能力或具体情境交互具有不可逆后果（如推开单向章节大门导致支线关闭）时，游戏开发者**必须**声明并在执行前暴露具体后果信息。玩家独立选择**允许自主执行**、**执行前询问确认**或**禁止执行**（与第 16.3.1 节同时适用时须双重满足，其中**禁止**优先阻断，且策略变更在效果提交前均须生效）。

### 16.6 确认超时、冷却窗口与防打扰限流

所有确认挑战（第 10.2 节）均携带有限的 `expires_at_ms`：超时未获肯定确认一律按拒绝/放弃处理——沉默绝不等于同意。等待确认期间及超时后，伴玩**可以**继续不依赖该未决行动的低风险常规行为（跟随、躲避伤害、基础自卫、普通对话）。超时或被拒后，实现**必须**执行已声明的 `cooldown_ms` 冷却窗口：在相关游戏状态未发生实质变化且玩家未下达相关新指令前，**不得**就同一目标/意图重复发起询问；游戏端应对高频确认挑战限流并返回抑制反馈。过期的迟到 `action.confirm` **必须**拒绝。

### 16.7 新指令覆盖与主动目标失效通知

冲突的玩家最新指令按第 16.1 节三级停止规则立即取代旧指令（丢弃未发计划并取消/拦截未领取的 `pending` 行动）。当关联目标或任务对象失效（如目标 Boss 已死亡）时，即便常规观察仅采用 `observation.query` 查询，游戏交互节点也**必须**主动生成获授权的目标失效事件并写入会话事件流——流式通道下实时推送，仅轮询绑定下经 `session.events` 拉取或随期间响应附带同步失效提示。配置规范定义目标关联的有效期而无需游戏猜测未公开的内部计划；收到失效通知后，智能体**必须**重新评估并停止发出已失效计划的后续行动。

<a id="section-17"></a>

## 17. 可选配置规范与扩展

可选配置规范**必须**完整定义附加操作、状态转换、必需授权、失败模式与符合性测试向量。遇到未知的 `required=true` 扩展或未知枚举值时，**必须**在产生效果前安全拒绝，严禁静默强转为默认值。

### 17.1 实时游戏商店配置规范（`store`）

游戏**可以**将实时游戏内商店作为可选能力开放，协议不强制绑定特定货币或商业模式。目录可见性、推荐资格与当前可购买性彼此独立；购买属于受游戏执行边界校验的获授权 **Action**（如实返回映射至第 10.3 节的待交付、已完成、部分交付、失败或 `unknown` 状态），并严格遵循第 11.2 节超时结果未决默认不重发规则。超出既有同意的价格或实质条款变动**必须**重新取得玩家确认。

#### 17.1.1 结构化商品与适度推荐限频

商店**必须**提供带明确货币单位的结构化价格、商品属性与可购/解锁状态；商品名称与促销文案属于不可信数据（第 19 节），**不得**篡改玩家的自主等级、预算或确认策略。开发者与智能体**可以**对付费商品进行适度、限频推荐（基础协议不强制推广标签或专门的全局推荐关闭开关）；实现**必须**声明并执行可验证的推荐限频策略——当玩家持续明确表示反对时，**必须**降低本局剩余时间内的推荐频率。

#### 17.1.2 通用购买授权预算与权威账本隔离

玩家**可以**针对明确声明的常规可再生游戏内虚拟货币或消耗品设定有界自主购买预算（与第 16.2 节 AI 运行算力上限严格区分）。超额购买须先取得玩家明确同意方可上调上限或按范围重置计数。权威购买预算账本**必须**由游戏端或受信结算层维护，在效果边界对并发与在途购买执行预留扣减，且在 `unknown` 超时未完成核对前不得提前释放预留额度。通用自主购买预算**绝不授权**真实法币扣款、外部钱包支付或高价值账户资产不可逆处置——此类交易每次均**必须**通过系统级或游戏原生安全界面取得真人玩家确认。

### 17.2 伴玩外观优先级与显式降级

启用可选的伴玩视觉外观能力（`avatar` / `presentation`）时，形象选择遵循严格的三层优先级：

1. **玩家强制覆盖**（玩家显式指定要求使用的自定义形象）；
2. **游戏默认伴玩外观**（玩家未强制覆盖时，由游戏开发者提供的契合本作美术风格的默认外观）；
3. **伴玩默认外观**（游戏接受外部通用格式但未单独提供专属默认外观时，伴玩自带的基础形象）。

实现**必须**区分上述三类来源与最终实际渲染结果，严格执行声明式资源大小、哈希摘要与沙箱边界（`asset.resolve` 严禁执行代码或抓取任意内网地址），且**严禁无提示静默替换**。当所选形象格式或渲染能力不兼容时，**必须**明确提示玩家并执行约定的显式降级规则（提示重选/取消，或启用默认外观并明确标记为降级回退而非自定义覆盖成功）。

<a id="section-18"></a>

## 18. HTTP/JSON 与流式传输绑定（`g2a-http-json/draft-1`）

### 18.1 端点路由、操作信封与流式通道

`g2a-http-json/draft-1` 将抽象操作映射至 HTTPS（在已验证本地部署中允许显式 `127.0.0.1` 回环）：

- **`GET /.well-known/g2a.json`：** 未认证端点，仅返回 `PublicDescriptor`。
- **`POST /g2a/operations`：** 经认证的单操作端点，请求体为 `OperationRequest`，响应体为 `OperationReply`（`Cache-Control: no-store`，`Content-Type: application/json; charset=utf-8`）。
- **可选服务端推送流（`SSE` / `WebSocket`）：** 为满足低延迟投递且无需智能体暴露入站端口，双方可显式协商由智能体主动发起的 `text/event-stream` 或 WebSocket 流，绑定当前 `session_id` 并在每次推送时实时核验撤权、接收范围与玩家在线状态；维持长连接本身绝不延长已过期权限。未协商流式扩展的最低绑定通过 `session.events` 轮询拉取事件。

`OperationRequest` 与 `OperationReply` 传输信封示例：

```json
{
  "request": {
    "version": "g2a-design-1",
    "operation": "session.snapshot",
    "request_id": "req-4091",
    "payload": {"session_id": "sess-902"},
    "extensions": {}
  },
  "success_reply": {
    "request_id": "req-4091",
    "result": {
      "session": {"session_id": "sess-902", "state": "active", "ready": true, "sequence": 42},
      "cursor": 42,
      "capabilities_revision": 3,
      "membership_revision": 1
    }
  },
  "error_reply": {
    "request_id": "req-4092",
    "error": {
      "code": "stale_context",
      "category": "epoch_or_baseline",
      "retry": "after_renegotiate",
      "request_id": "req-4092",
      "outcome": "not_accepted",
      "message": "能力目录已推进至修订号 4，请先刷新状态再提交行动。"
    }
  }
}
```

### 18.2 确定性 HTTP 状态码映射

所有由协议节点处理的响应（含 `200` 与 `4xx`/`5xx`）均返回结构合法的 `OperationReply` JSON 信封（`200` 携带 `result`，`4xx`/`5xx` 携带 `error`），彻底消除“传输层拒绝 vs. 领域层拒绝”的二义性，同时完整保留标准 HTTP 网关监控与 `Retry-After` 头语义：

| HTTP 状态码 | 对应的标准错误码 / 场景 | 响应信封结构 |
| --- | --- | --- |
| `200 OK` | 操作已受理或完成，无协议级拒绝 | `{"request_id", "result"}`（注：`action.query` 的 `result` 内仍可报告游戏执行 `failed` 或 `unknown`） |
| `400 Bad Request` | `invalid_request`, `invalid_arguments`, `unsupported_version`, `unsupported_capability` | `{"request_id", "error"}` |
| `401 Unauthorized` | `unauthenticated` | `{"request_id", "error"}` |
| `403 Forbidden` | `permission_denied`, `revoked` | `{"request_id", "error"}` |
| `404 Not Found` | `not_found`（仅限已授权范围） | `{"request_id", "error"}` |
| `409 Conflict` | `stale_context`, `conflict`, `confirmation_required` | `{"request_id", "error"}`（`confirmation_required` 时在 `details` 附挑战参数） |
| `413 Content Too Large` | `message_too_large` | `{"request_id", "error"}` |
| `429 Too Many Requests` | `resource_limit` | `{"request_id", "error"}` + 可选 `Retry-After` 响应头 |
| `503 Service Unavailable` | `unavailable` | `{"request_id", "error"}`（由 G2A 节点生成时） |
| `504 Gateway Timeout` | `outcome_unknown` | 按第 11.2 节视为 `unknown` 未决结果；**严禁**盲目重放副作用 |

### 18.3 出站中继封装（Outbound Relay）

当游戏交互节点运行于家庭 NAT/防火墙后的客户端、无法开放入站端口时（第 3.2 节），出站中继绑定通过五个专用传输操作在配对邮箱上封装受允许的智能体请求：`relay.register`（控制面可信配对）、`relay.call`（智能体凭外层中继令牌提交请求）、`relay.pull`（游戏节点主动出站拉取待处理请求）、`relay.reply`（游戏节点回传有界响应）与 `relay.revoke`（关闭邮箱并返回 `410`）。外层中继令牌绝不替代内层 `Invitation`/`Session` 凭据，且 `Game` 内部管理/执行器操作（`action.claim`、`action.commit_result`）在中继通道上**必须**一律拒绝。

### 18.4 传输安全、SSRF 防护与 `g2a-cjson-1` 规范化编码

远程传输**必须**启用 TLS 并按所选信任配置认证对端；凭据严禁写入 URL、查询参数或日志，默认拒绝浏览器跨源请求（`Origin`）。发现端点、资源 URL 与 HTTP 重定向均属不可信输入：发起连接前及每次重定向时**必须**执行目标地址策略（协议方案、主机/IP、端口）校验，阻断 DNS 重绑定与未授权内网探测，同时不得借此歧视合规智能体服务商。

**`g2a-cjson-1` 规范化编码：** 所有协议摘要均在域分离前缀下对 `g2a-cjson-1` 字节计算 SHA-256（[WIRE_CONTRACT.md](../protocol/WIRE_CONTRACT.md)、[codec.py](../protocol/codec.py)）：无 BOM 的严格 UTF-8；拒绝重复对象键、非法代理项、`NaN`/`Infinity`、浮点数字面量与 `-0`；精确整数限定于 `[-9007199254740991, +9007199254740991]`（连续物理量采用第 5.1 节定点单位）；对象键按 **Unicode 标量值（码点）** 排序而非 RFC 8785（JCS）的 UTF-16 码元排序。未经新摘要域显式协商，实现**不得**直接用标准 JCS 库替代。

<a id="section-19"></a>

## 19. 安全与隐私考虑

| 威胁向量 | 必需的协议防护边界 |
| --- | --- |
| 借查询或错误回包探测隐藏事实 | 游戏节点在序列化前完成字段投影与统一错误脱敏。 |
| 对白、物品描述、商品文案或记忆中的间接提示词注入 | 控制信封与不可信内容严格分离（`I09`）；在模型输出之外的效果边界确定性执行权限、预算与确认检查。 |
| 混淆代理（Confused Deputy）与委托越权 | 每一跳均绑定经验证的主体、目标受众、实例代次与权限快照。 |
| 网络超时与重复重放 | 域分离规范摘要、有界回执保留期、`unknown` 状态保留及默认不重发规则。 |
| 撤权与执行并发竞争 | `action.claim` 领取门禁配合串行/原子效果边界复核。 |
| 战争迷雾切换或离队后的数据残留泄露 | 立即废止旧 `visibility_epoch`、建立 `retract` 屏障并执行冻结+当前双重受众过滤。 |
| 恶意资源 URI / SSRF / 压缩包路径穿越 | 声明式 `Manifest` 摘要核验、解压字节/深度上限、禁代码执行与防 DNS 重绑定目标策略。 |
| 伪造 `taint_context_clean` 自证清白声明 | 忽略智能体单方干净上下文声明，由权威账本独立核验预算、确认与接收范围。 |

单纯读取外部不可信内容不会废止有效的玩家购买预算授权，也无需将后续所有常规行动退化为逐次弹窗，前提是权威账本确保外部内容无法篡改授权、接收方或额度上限。审计日志**应**记录不透明标识与结果，最小化原始私人对话留存。

<a id="section-20"></a>

## 20. 版本、发布清单与生态治理

### 20.1 规范产物标识

| 产物类别 | 当前标识符 | 规范定位 |
| --- | --- | --- |
| 双语协议规范正文 | `standard-review-2026-11-22-r73` | 面向公众审阅的标准草案修订号（非线上协议版本字符串）。 |
| 核心设计机器契约 | `g2a-design-1` | 经机器校验的基线 Schema、38 项操作夹具与规范编码器。 |
| 游戏观察配置规范 | `observations-draft-1` | 候选结构化/多模态观察流与 `observation.query` 契约。 |
| HTTP/JSON 传输绑定 | `g2a-http-json` / `draft-1` | 候选单端点 HTTP/JSON 及可选 SSE/WebSocket 绑定映射。 |
| 实验性参考 SDK | `0.1.0-dev`（`0.1.0.dev0`） | 早期 Python/JS/Godot 实验原型，未完整实现本规范草案。 |

### 20.2 发布冻结清单、兼容演进与中立治理

正式冻结稳定线上版本（如 `1.0.0`）前，**必须**发布不可变的**发布清单（Release Manifest）**，为双语规范正文、可离线解析的 JSON Schema 材料包（锁定 `2020-12` 方言与必需词汇）、操作目录、错误码注册表及跨语言测试向量固定唯一权威源与 SHA-256 摘要。中英文版本的章节编号、规范强度与修订记录**必须**严格同步。任何改变既有语义、必填字段、枚举含义或效果保障的变更均须通过显式版本协商演进，禁止依赖宽容解析混用。

**生态中立性与平台独立治理：** 频繁触发协议拒绝可依据标准化错误码与审计日志启动技术核查，拒绝次数本身不等于恶意。各智能体托管平台或游戏目录**可以**针对其自有商业服务制定独立的信任与违规处置流程（如事前通知与申诉整改机制），但单一平台的商业服务准入决定仅作用于该平台自身，**不得**表述为全协议层面的 G2A 符合性封禁。

<a id="section-21"></a>

## 21. 符合性与质量评估

### 21.1 符合性声明与五级证据分层

符合性声明精确绑定协议版本、实现构建号、支持角色、传输绑定、已协商能力/配置规范及信任模式。公开符合性测试套件**必须**允许自有与第三方实现按相同公开标准自测并提交结果，不设作者平台人工审批门槛。未实现的可选能力如实标记为 `not_applicable` 并附理由，不得掩盖必选项失败。验证证据**必须**明确区分五个层级：(1) Schema 与编码校验，(2) 状态机与故障注入测试，(3) 独立实现跨进程互通，(4) 真实游戏引擎集成，以及 (5) 玩家侧策略验收。

### 21.2 结构化符合性测试套件矩阵（`CONF-01`–`CONF-14`）

| 套件编号 | 测试域与对应条款 | 适用角色 / 能力 | 必需覆盖的正例、反例与故障向量 |
| --- | --- | --- | --- |
| `CONF-01` | 开放准入与权限边界（§§1, 4, 5, 7, 8, 20） | 所有参与方 | `PublicDescriptor` 与按主体过滤的 `Descriptor`；冻结 `scope_digest` 及通过新 Offer 收窄范围；无厂商歧视同等准入；标准化拒绝代码与安全说明（零秘密/隐藏事实泄露）。 |
| `CONF-02` | 规范编码、Schema 与 HTTP 映射（§§2, 5.1, 7.4, 12.1, 18, 20） | 所有参与方 | 离线 Schema 校验与未知必需词汇拒绝；轻量 `Envelope.extensions`；确定性 HTTP `200`/`400`/`401`/`403`/`404`/`409`/`413`/`429`/`503`/`504` `OperationReply` 映射；`g2a-cjson-1` 码点排序、整数/定点边界（禁浮点/`-0`）、重复键拒绝；SSRF 与 DNS 重绑定拦截。 |
| `CONF-03` | 角色槽位、共存与生命周期（§§4.1, 13, 14.2） | 游戏节点、智能体 | 声明的 `role_slots`（`companion`、`independent_npc` 或双支持）；空伴玩槽正常游玩；纯 NPC 游戏无虚设伴玩槽；共存/上限强制执行及逐角色所属玩家/视角/授权/计费严格隔离；召唤/收起不丢记忆。 |
| `CONF-04` | 离线即停与双层恢复（§§8.2, 11, 14） | 游戏节点、智能体 | 显式离开与静默故障有界隔离；智能体心跳不延续缺席玩家在线状态；持有用户离线时其伴玩及名下全部 AI NPC 立即停止；禁离线模式与重进自动重启旧任务；活动租约内本地接管前 `session.resume` 无缝恢复 vs. 超时/本地接管后强制等待玩家决定；零断线过程补录。 |
| `CONF-05` | 观察流同步与时序（§§9.1–9.4, 9.6, 12.3） | `observations-draft-1` | 仅推送、仅 `observation.query` 与混合模式；`snapshot` 摘要绑定、紧凑 `delta` `base_revision` 校验、采样合并、`retract` 屏障与迟到旧更新拒绝；五类可见性转换原因；受众过滤事件跳号与流修订号区分；单调时钟超时与队列溢出缺口报告。 |
| `CONF-06` | 结构化基础与正交多模态（§§9.5, 15.5） | 游戏节点、智能体 | 必需的 `perception.structured` 决策能力；可选 `perception.visual` 与 `perception.audio` 的独立协商、行为级理解验证与运行期玩家独立开关；与第 15.5 节语音对话严格分离。 |
| `CONF-07` | 行动执行、确认挑战与结果核对（§§10, 11, 16.6） | `actions` | 区分定义/行动/传输三类标识；`confirmation_required`（`409`，`not_accepted` 不烧毁 `action_id`）→ `action.confirm` → 原子消费且重放不双花；超时放弃与 `cooldown_ms` 限流；绑定观察基线的前置条件与陈旧目标拒绝；`504`/`unknown` 强制先查与默认不重发；部分效果记账。 |
| `CONF-08` | 自主性、三级停止与目标失效（§§16.1, 16.2.1, 16.7） | 伴玩智能体、游戏节点 | 多步完成须有目标达成证据；跨游戏保持全局自主等级；推断目标局部修正；三级停止/指令覆盖（丢弃未发计划、对 `pending` 发 `action.cancel` 或拦截领取、`executing` 按游戏规则结算）；流式与纯轮询下权威端主动写入目标失效事件。 |
| `CONF-09` | 多人互动与双重确认策略（§§16.3, 16.3.1, 16.5） | 多人 / 转移 / 不可逆 | 接收方控制是否接受他人伴玩主动搭话；游戏开放伴玩对战与拒绝；三种物品转移策略及开发者+玩家高价值标记合并；具体情境不可逆声明（允许/确认/禁止）在效果提交前强制生效。 |
| `CONF-10` | 运行消耗上限与 NPC 费用归属（§16.2） | 计量服务、启用 NPC 游戏 | 估算与实测披露、额度预留及触顶暂停伴玩而不中断正常游戏；每个活动独立 AI NPC 强制绑定所属玩家/房主付费账户，严禁向其他互动玩家隐式分摊。 |
| `CONF-11` | 实时商店与购买授权预算（§17.1） | `store` | 结构化价格/单位、阶段资格、变价重确认、声明的推荐限频策略及持续明确反对后降低本局频率；权威购买预算账本的并发预留、超时冻结，且严格排除真实法币、外部钱包与高价值账户资产。 |
| `CONF-12` | 伴玩外观与游戏内状态（§§16.4, 17.2） | `avatar` / `presentation` | 三层优先级（玩家强制覆盖 > 游戏默认 > 伴玩默认）；格式不兼容时明确提示并按约定标明回退或重选；执行游戏受伤/死亡限制且不改变跨游戏身份与记忆。 |
| `CONF-13` | 记忆治理、时间线与迁移（§15） | 记忆服务商 / 智能体 | NPC 与玩家伴玩记忆隔离；读档 `save_epoch` 单调递增、推理前时间线过滤 vs. 旧分支来源标记、独立剧透/保密软偏好；玩家查看/编辑/置顶锁定/删除及自主整理保护已编辑/锁定记录；开放格式完全导出与真实四态导入回执。 |
| `CONF-14` | 防提示词注入与隐私回执（§§4.4, 15, 19） | 所有参与方 | 对白、物品、商品与召回记忆的成对正常/注入向量（同时衡量合法任务效用与零越权/零预算篡改/零受众篡改）；仅限规划输入隔离；保管方真实 `privacy.receipt` 核验。 |

### 21.3 可复现的智能体质量评估准则

随附于符合性报告的可选质量基准评估**必须**披露游戏版本、场景与随机种子夹具、模型/服务商版本、采样/工具配置、观察/行动速率限制、token/时间预算及试验次数，并在全量试验上分别统计协议违规、任务失败、预算耗尽与基础设施故障，禁止选择性隐瞒失败样本。排行榜分数绝不得转化为未公开的特定厂商准入门槛。

<a id="section-22"></a>

## 22. 基线对齐与迁移说明

| 仓库既有产物 / 基线概念 | 本标准规范处理方式（`r73`） |
| --- | --- |
| `g2a-design-1` `Descriptor` / `Scope` / `Envelope` | 在第 5.2 节完成自包含规范化；`Scope.extensions` 冻结会话配置，`Envelope.extensions` 保持轻量（默认 `{}`）。 |
| `g2a-design-1` 将 `chat.send` 归入 `core.events` | 在第 3.3/第 6 节将 `chat`（`chat.send`、`player_chat.forward`）拆分为独立可选能力；旧 `g2a-design-1` 夹具通过兼容映射保留。 |
| 无状态观察拉取（第 9.6 节） | 明确分配候选操作 `observation.query`（`read` 重试族，无世界副作用且不续租）。 |
| `g2a-design-1` 受理前 `action.confirm` | 在第 10.2 节补齐结构化 `confirmation_required`（`409`，`outcome: not_accepted`，不烧毁 `action_id`）两阶段确认挑战闭环。 |
| `g2a-design-1` `relay.*` 五项操作 | 明确划归第 18.3 节出站中继传输封装层，实现全部 38 项基线操作 + `observation.query` 无遗漏对齐。 |
| HTTP 错误状态码映射 | 采用携带 `OperationReply` JSON 的确定性 `4xx`/`5xx` 状态码映射（第 18.2 节），替代易生歧义的领域错误 `HTTP 200` 方案。 |
| `g2a-conformance-statement-1` | 对外发布报告升级为映射至 `CONF-01`–`CONF-14` 的条款/配置规范符合性矩阵（第 21.2 节）。 |
| 实验参考 SDK `0.1.0-dev`（`src/g2a/`、`sdk/javascript/`） | 早期实验原型（含 `http-poll`、`outbound-poll`、本机配对与本地参数约束），声明 `1.0` 符合性前须专门迁移。 |

<a id="section-23"></a>

## 23. 端到端示例场景

- **回合制策略伴玩：** 游戏开放棋盘观察与落子能力定义，玩家仅授权观察与 `chat` 建议。智能体读取 `snapshot` 提供建议而无落子权限；后续若通过新 `Offer` 授予落子权，执行器仍会在 `action.claim` 与效果边界检查当前回合归属。
- **主动战斗协助与三级急停：** 在线战斗协助授权下，观察流发现附近敌人后伴玩自主排队攻击。玩家喊出“停下！”瞬间，伴玩丢弃未发计划，对队列中尚未领取的 `pending` 攻击立即发出 `action.cancel` / 触发游戏侧领取拦截，而已离弦飞行的箭矢（`executing`）按游戏物理规则结算并如实报告命中结果。
- **伴玩与 AI Boss 同局共存的副本战：** 游戏 `Descriptor` 同时启用 `companion`（`max_per_player: 1`）与 `independent_npc`（`max_per_run: 1, coexists_with_companion: true`）。两名玩家各带私人伴玩参战，房主承担 AI Boss 运行费用（第 16.2 节）。各方视角、记忆与预算严格隔离；若房主中途掉线，AI Boss 按第 14.1 节立即停止活动，另一名在线玩家的自有伴玩会话保持隔离不受越权干扰。
- **战争迷雾代次废止：** 阵营切换后，游戏节点废止 `visibility_epoch: "view-9"` 并下发新 `snapshot`（`view-10`，`revision: 1`）。网络延迟到达的旧包 `delta`（`view-9`，`base_revision: 30`，`revision: 99`）即便修订号数值更大仍被直接拒绝。
- **超时结果核对防双花：** 商店购买或开启大门请求已在游戏内生效，但响应超时丢失（`504` / `outcome_unknown`）。智能体调用 `action.query("act-open-gate-01")` 核对原单，绝不另造 `"act-open-gate-02"` 重发导致重复扣费。
- **秒级网络闪断与长时故障区分：** 1 秒级 Wi-Fi 切换在 `lease_deadline_ms` 内、本地接管触发前恢复，伴玩调用 `session.resume` 刷新 `RecoverySnapshot` 并核对在途行动后无缝继续战斗；而后续一次 3 分钟服务商中断触发了游戏本地脚本接管，网络恢复后伴玩保持暂停，等待玩家明确点击确认后再恢复 AI 接管。

**观察流状态转换轨迹示例（固定 `world-4`）：**

| 步骤 | 收到的观察帧 | 消费方规范状态转换（第 9.2–9.4 节） |
| --- | --- | --- |
| 1 | `snapshot`，`view-9`，`revision: 27` | 原子建立 `view-9` 基线（`revision = 27`）并绑定流摘要。 |
| 2 | `delta`，`view-9`，`base: 27`，`revision: 30` | 原子应用变更；非连续跳号 `27 → 30` 合法，当前修订号升至 `30`。 |
| 3 | 步骤 2 的完全重复包 | 幂等忽略，不重复作用，修订号保持 `30`。 |
| 4 | 恢复 `snapshot`，`view-9`，`revision: 30` | 在 `revision = 30` 重新整理建立等价完整基线，不虚增修订号。 |
| 5 | `delta`，`view-9`，`base: 28`，`revision: 31` | 拒绝（`stale_context`）：`base_revision 28 != 30`；请求新 `snapshot` 重同步。 |
| 6 | 废止 `view-9` → `snapshot`，`view-10`，`revision: 1` | 立即丢弃 `view-9` 状态；在 `view-10` 建立全新独立基线（`revision = 1`）。 |
| 7 | 迟到的 `delta`，`view-9`，`base: 30`，`revision: 99` | 因 `view-9` 代次已废止而直接拒绝，不因修订号更大而接受。 |

<a id="section-24"></a>

## 24. 参考资料

### 24.1 规范性术语参考

- RFC 2119，*Key words for use in RFCs to Indicate Requirement Levels*（BCP 14）：https://www.rfc-editor.org/rfc/rfc2119.html
- RFC 8174，*Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words*（BCP 14）：https://www.rfc-editor.org/rfc/rfc8174.html

### 24.2 资料性参考与设计基线材料

仓库设计与研究台账：[PROTOCOL.md](../protocol/PROTOCOL.md)、[OPERATION_CONTRACT.md](../protocol/OPERATION_CONTRACT.md)、[WIRE_CONTRACT.md](../protocol/WIRE_CONTRACT.md)、[STATE_TRACES.md](../protocol/STATE_TRACES.md)、[第 1–5 轮研究报告](../research/g2a-protocol-research-2026-11-13.zh-CN.md)与[第 6–10 轮研究台账](../research/RESEARCH_ROUNDS_6_10.zh-CN.md)。

- **协议架构与数据编码：** A2A Protocol Specification（https://a2a-protocol.org/latest/specification/）；Model Context Protocol（MCP，2025-11-25，https://modelcontextprotocol.io/specification/2025-11-25/）；RFC 8259（JSON）；JSON Schema Draft 2020-12 Core & Validation（https://json-schema.org/draft/2020-12/）；RFC 8785（JCS，第 18.4 节对比差异）；CloudEvents 1.0.2；RFC 9457（HTTP Problem Details）；RFC 9413。
- **安全、委托与提示词注入防护：** RFC 9700（OAuth 安全最佳实践）；RFC 8693（令牌交换与委托）；InjecAgent（https://arxiv.org/abs/2403.02691v3）；AgentDojo（https://arxiv.org/html/2406.13352v3）。
- **游戏环境、行动与时序模型：** OpenSpiel（https://openspiel.readthedocs.io/）；PettingZoo AEC & Parallel APIs（https://pettingzoo.farama.org/）；Unity ML-Agents Decisions & Action Masking；Gymnasium Time Limits（终止与截断区分）；W3C WoT Thing Description 1.1；SayCan（https://arxiv.org/html/2204.01691v2）；RFC 7641；W3C High Resolution Time。
- **记忆、来源、人机交互与评估：** W3C PROV-DM；ActivityStreams 2.0；Generative Agents（https://arxiv.org/html/2304.03442v2）；LongMemEval（https://arxiv.org/html/2410.10813v2）；LoCoMo（https://arxiv.org/abs/2402.17753v1）；Horvitz（1999，混合主动式交互原则）；Amershi 等（2019，人机 AI 交互指南）；W3C QA Framework Specification Guidelines；AgentBench；HELM。

<a id="section-25"></a>

## 25. 修订历史

| 编辑修订号 | 日期 | 可追溯依据与范围 |
| --- | --- | --- |
| `standard-review-2026-11-13-r48` | 2026-11-13 | 初始已提交双语审阅基线（Git 提交 `796778b8af2ff8c0c4a54a7434b4c6b5a74ad8ae`）。 |
| `standard-review-2026-11-14-r70` | 2026-11-14 | `r71` 审查前输入快照（SHA-256：英文 `e03ce510ab129bf5d7d9a5f3b9874f21697fd2557d46e463a70f4ce10f06029d`，中文 `901f5038e34e65f2768467ba55a695b46fc4b5e1c2cd720c1772282562b11765`）。 |
| `standard-review-2026-11-14-r71` | 2026-11-14 | 双语同步审查基线（Git 提交 `81cb489eccecf538af697ddacd90d5e89436a7ba`）。 |
| `standard-review-2026-11-22-r72` | 2026-11-22 | 协议机制闭环、角色共存声明、双层闪断恢复、正交多模态与 `CONF-01`–`CONF-14` 矩阵更新（Git 提交 `6ab2d2ee1463c4c43318a339c77140333db7adf6`）。 |
| `standard-review-2026-11-22-r73` | 2026-11-22 | 面向公开开放标准的体系化重构与逻辑严密性升级（见第 25.1 节）；保持工作草案状态，不分配生产线上协议版本。 |

### 25.1 r73 修改记录

| 分类 | 涉及章节 | 优化内容与兼容性边界 |
| --- | --- | --- |
| 自包含规范对象与线上报文示例 | 概览、3.2、5.2、7.2、7.3、10.2、18.1 | 消除对内部脚本的阅读依赖，补齐全部 14 个核心规范对象的字段结构表、三种标准部署拓扑（本地 IPC、直连 HTTPS/WSS、出站中继）、端到端准入握手时序图，以及 `Descriptor`、`Observation`、`ActionRequest`/确认挑战、`OperationRequest`/`OperationReply` 四组完整 JSON 报文示例。 |
| 角色体系对齐与操作调用方向 | 4.1、6、8.2、8.3 | 统一第 4 节与第 6 节的角色命名，明确定义游戏交互节点、游戏执行器、`PlayerConsent`、游戏智能体及四类可选功能角色，将第 6 节模糊角色标签替换为精确的“调用方 → 接收目标”；严格区分智能体控制租约与玩家在线状态；增补 8 类目标的分级撤销效果矩阵（`auto_rule` 至 `relay`）。 |
| 确认挑战幂等、重试族与标准错误码表 | 9.2、10.2、11.1、12.1、15.7、18.2 | 明确 `confirmation_required`（`outcome: not_accepted`）在玩家完成 `action.confirm` 前不烧毁 `action_id` 去重键；统一五阶段行动执行编号；补齐 `delta` 中结构化 `removals` 转换原因表示；归纳四类操作重试族（`read`、`lease`、`control`、`message`）；在第 12.1 节建立 15 项标准错误码注册表并与第 18.2 节 HTTP 状态码精确对齐；自主记忆整理增加对玩家置顶锁定与显式编辑记录的保护。 |
| 公开标准体例与中立生态治理 | 1–25 | 将全篇口语化小标题升级为标准编号子章节（如 `4.1`–`4.4`、`7.1`–`7.4`）；将内部基线对比收敛至第 2、20、22 节；将第 20 节特定作者平台说明提炼为厂商中立的开放生态治理原则，同时 100% 保留全部既有游戏权威、在线即停、记忆隔离/迁移、自主等级、商店推荐限频与玩家承担独立 AI NPC 费用等核心规则。 |
