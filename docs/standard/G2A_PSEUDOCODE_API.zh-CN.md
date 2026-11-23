# G2A 伪代码 API 与流程实现规范

**Game-to-Agent Pseudocode API & Implementation Blueprint**

面向跨引擎 SDK 与协议节点实现者的语言无关 API 契约、宿主适配端口与核心状态机伪代码规范。

协议版本：`V0.0.1`｜发布日期：2026 年 11 月 23 日｜上位规范：[G2A 协议规范（V0.0.1）](G2A_SPECIFICATION.zh-CN.md)｜双语对照：[English Pseudocode API](G2A_PSEUDOCODE_API.md)

## 目录

1. [实现准则、公共数据契约与基础工具](#section-1)
   - [1.1 规范定位与伪代码语法约定](#section-1-1)
   - [1.2 统一消息信封、标准回复与错误枚举](#section-1-2)
   - [1.3 核心业务数据结构定义](#section-1-3)
   - [1.4 RFC 8785（JCS）规范化摘要工具伪代码](#section-1-4)
2. [第一层：交互源点 SDK（Interaction Origin SDK）伪代码规范](#section-2)
   - [2.1 引擎宿主适配端口（Engine & Host Ports）](#section-2-1)
   - [2.2 面向游戏开发者的接入 API（信号快照模式 + 具身空间差分模式）](#section-2-2)
   - [2.3 后台脏差分与海量对象聚合器伪代码](#section-2-3)
   - [2.4 源点接口（Origin Interface）四大原语处理器伪代码](#section-2-4)
3. [第二层：智能枢纽核心（Intelligent Hub Engine）伪代码规范](#section-3)
   - [3.1 枢纽持久化账本与受信任交互端口](#section-3-1)
   - [3.2 会话授权、租约续期、双层闪断恢复与玩家离线即停状态机](#section-3-2)
   - [3.3 状态合并器、活跃方法投影与静默期自适应节流器](#section-3-3)
   - [3.4 方法调用队列调度器（QueueScheduler）完整状态机伪代码](#section-3-4)
4. [第三层：演算中枢 SDK（Computation Core SDK）伪代码规范](#section-4)
   - [4.1 模型推理与长期记忆适配端口](#section-4-1)
   - [4.2 会话接入、心跳与断线重连客户端状态机](#section-4-2)
   - [4.3 感知消费、队列提交、确认重提与超时对账标准流程](#section-4-3)
   - [4.4 伴游记忆开放格式导出与保守导入接口伪代码](#section-4-4)
5. [跨三层端到端联调走查序列](#section-5)
   - [5.1 走查一：具身空间游戏玩家主动指令（寻路 + 直达开箱效果）](#section-5-1)
   - [5.2 走查二：无实体模拟经营信号告警与整队单次确认补货](#section-5-2)
   - [5.3 第三方 SDK 互通自检清单](#section-5-3)

---

<a id="section-1"></a>

## 1. 实现准则、公共数据契约与基础工具

<a id="section-1-1"></a>

### 1.1 规范定位与伪代码语法约定

本文档是 [G2A 协议规范（V0.0.1）](G2A_SPECIFICATION.zh-CN.md) 的配套工程实现蓝图，用于指导官方参考实现及第三方引擎团队（Godot / GDScript、Unity / C#、Unreal / C++、Rust、Python、TypeScript、Go 等）开发彼此 **100% 线上互通** 的 SDK 与协议节点：

- **必须保持一致的部分（流程与线上契约相关）：** JSON 字段命名、枚举字面量、RFC 8785 摘要输入结构、鉴权与策略校验先后顺序、幂等去重键、错误码映射及熔断/停机时序。
- **允许自由发挥的部分（实现无关）：** 内存布局、并发原语（协程 / 线程锁 / Actor 模型）、引擎节点树或 ECS 挂载方式、数据库选型（SQLite / 嵌入式 KV / 服务端存储）以及本地进程间传输细节。

本文伪代码采用中立强类型表示法，映射到各宿主语言的规则如下：

| 伪代码记号 | 规范含义 | 各语言典型映射 |
| --- | --- | --- |
| `struct` / `enum` | 纯数据结构或闭合枚举字面量（序列化为 RFC 8259 UTF-8 JSON） | C# `record/class`、C++ `struct`、GDScript `Dictionary/Resource`、Rust `struct/enum`、TS `interface` |
| `interface XXXPort` | 需要由游戏引擎、操作系统或外围基础设施注入的**适配端口** | 接口（Interface / Trait / 纯虚类 / 回调函数表） |
| `Option<T>` | 可选值（JSON 中缺失或 `null`，推荐省略空可选键） | `T?` / `std::optional<T>` / `Option<T>` / `null` |
| `Result<T, G2AError>` | 显式成功或携带标准 `G2AError` 失败，禁止吞掉异常冒充成功 | 返回值对、异常捕获转换或 `Result<T, E>` |
| `require COND else ERR` | 前置断言；不满足时立即中止当前未提交变更并返回标准 `ERR` | 条件守卫（Guard Clause） |
| `atomic(scope_key) { ... }` | 在指定锁域与持久化账本内原子提交状态变更；抛错自动回滚 | 互斥锁 + 事务日志 / 数据库事务 |

---

<a id="section-1-2"></a>

### 1.2 统一消息信封、标准回复与错误枚举

所有跨层请求、响应与实时推送帧均封装在统一顶层信封中（线上版本号字面量固定为 `"0.0.1"`，对应规范版本 `V0.0.1`）：

```text
const G2A_WIRE_VERSION = "0.0.1"

enum AcceptanceState {
  "accepted",      // HTTP 200：请求已受理（含队列部分执行后熔断，具体看各步状态）
  "not_accepted",  // HTTP 4xx / 503：在产生新业务副作用前明确拒绝或挂起待确认
  "unknown"        // HTTP 504：提交结果未决，调用方必须先调用 queue.query 对账
}

enum ErrorCode {
  "invalid_request",         // 400
  "invalid_arguments",       // 400
  "unsupported_version",     // 400
  "unsupported_capability",  // 400
  "unauthenticated",         // 401
  "permission_denied",       // 403
  "revoked",                 // 403
  "not_found",               // 404
  "stale_context",           // 409
  "conflict",                // 409
  "confirmation_required",   // 409
  "resource_limit",          // 429
  "unavailable",             // 503
  "outcome_unknown"          // 504
}

struct RequestEnvelope<TPayload> {
  g2a_version: String,          // 必填，当前基线为 "0.0.1"
  request_id: String,           // 必填，调用方生成的单次传输追踪 ID（UUID / ULID）
  session_id: Option<String>,   // 除 session.authorize 与入局首次注册外均必填
  timestamp_ms: Int64,          // 发送方 Unix 毫秒时间戳
  operation: String,            // 如 "origin.sync" / "queue.submit"
  payload: TPayload,
  extensions: Map<String, Any>  // 可选扩展命名空间，默认 {}
}

struct ReplyEnvelope<TResult> {
  g2a_version: String,
  request_id: String,           // 原样回显对应请求的 request_id
  session_id: Option<String>,
  timestamp_ms: Int64,
  acceptance: AcceptanceState,
  result: Option<TResult>,      // acceptance == "accepted" 时存在
  error: Option<G2AError>       // acceptance != "accepted" 时存在
}

struct EventEnvelope<TEvent> {
  g2a_version: String,
  event_id: String,             // 推送端唯一事件 ID，供接收端幂等去重
  session_id: String,
  timestamp_ms: Int64,
  event: String,                // 如 "context.push" / "queue.confirmed" / "session.resumed" / "session.closed"
  payload: TEvent
}

struct G2AError {
  code: ErrorCode,
  http_status: Int32,
  message: String,              // 面向调试/UI 的安全说明，严禁包含未授权隐藏实体或谜底
  retry_after_ms: Option<Int64>,
  cooldown_ms: Option<Int64>,   // confirmation_required 拒绝/超时冷却时长
  fresh_context: Option<ProjectedContext> // stale_context 时附带最新活跃方法供重规划
}
```

标准线上请求与确认拦截响应 JSON 报文示例：

```json
{
  "g2a_version": "0.0.1",
  "request_id": "req-01JDX8K9M2",
  "session_id": "sess-9f31c8",
  "timestamp_ms": 1795416000120,
  "operation": "queue.submit",
  "payload": {
    "queue_id": "Q-205",
    "based_on_rev": 42,
    "epoch": 1,
    "trigger": "proactive",
    "supersedes": false,
    "intent_summary": "采购 20 份木料并恢复 1 号木工台生产",
    "steps": [
      { "step_index": 0, "method_id": "#05", "actor": "player", "args": { "item": "timber", "qty": 20 } },
      { "step_index": 1, "method_id": "#06", "actor": "player", "args": { "line_id": "Bench_1" } }
    ]
  },
  "extensions": {}
}
```

```json
{
  "g2a_version": "0.0.1",
  "request_id": "req-01JDX8K9M2",
  "session_id": "sess-9f31c8",
  "timestamp_ms": 1795416000128,
  "acceptance": "not_accepted",
  "result": null,
  "error": {
    "code": "confirmation_required",
    "http_status": 409,
    "message": "Awaiting single-prompt player confirmation",
    "retry_after_ms": null,
    "cooldown_ms": 60000,
    "fresh_context": null
  }
}
```

---

<a id="section-1-3"></a>

### 1.3 核心业务数据结构定义

以下结构体在**交互源点**、**智能枢纽**与**演算中枢**三层之间共享语义：

```text
// 角色槽位类型与计费归属
enum RoleKind { "companion", "independent_npc" }
enum BillingMode { "player_metered", "developer_sponsored" }

// 执行主体标识："companion"（伴游自身实体或非侵入辅助图层）、"player"（受权玩家本体或主席位）
// 在 independent_npc 槽位下，仅允许其绑定自身的 npc_id（严禁出现 "player"）
type ActorId = String

// 通用规则前置就绪态
enum Readiness {
  "ready",   // 当前规则条件已齐备，可立即单步执行
  "staged"   // 当前局势可见，需同队列前置步骤完成后解锁为 ready
}

// 单步执行状态机
enum StepState {
  "pending",     // 已排入队列，尚未下发至交互源点
  "executing",   // 交互源点正在执行耗时动作（寻路/蓄力/持续踩踏），可随时响应取消
  "succeeded",   // 业务效果已在交互源点权威生效
  "failed",      // 业务规则不满足或中途受阻失败
  "cancelled",   // 执行前或 executing 期间被抢占/撤权/玩家叫停取消
  "aborted"      // 因前置步骤失败或取消，被智能枢纽熔断跳过（未下发至源点）
}

// 1. 静态能力表项（入局同步，智能枢纽与演算中枢缓存）
struct CapabilityEntry {
  method_id: String,               // 稳定短序号，如 "#01", "#02"
  name: String,                    // 领域通用动词名，如 "move_to", "interact", "craft", "mark_board"
  description: String,             // 供推理引擎理解的简洁语义说明
  permitted_actors: List<ActorId>, // 该方法允许绑定的主体，如 ["companion"] 或 ["companion", "player"]
  params_schema: JsonSchema,       // 标准 JSON Schema（支持 target_id、密码字符串、滑块数值、坐标、数组）
  sustained: Bool,                 // false=瞬时动作；true=可能返回 executing 持续态
  risk_flags: List<String>,        // 如 ["economy_spend", "irreversible", "real_money"]
  default_policy: PolicyMode       // 游戏建议默认门禁："allow" | "confirm" | "prohibit"
}

enum PolicyMode { "allow", "confirm", "prohibit" }

// 2. 上下文锚点（兼容具身空间双视角、XR 指向射线与无实体面板焦点）
struct TargetCandidate {
  target_id: String,               // 如 "chest_R", "Bench_1", "clue_C3"
  label: String,                   // 显示标签（属不可信游戏内文本，严禁拼接进控制指令）
  readiness: Readiness,            // 相对于该 actor 的就绪态："ready" | "staged"
  prerequisite_hint: Option<String>, // 如 "requires_proximity" / "requires_resource:timber"
  actor_anchor: Option<String>,    // 相对执行主体锚点，如 "1.0m ahead"
  player_anchor: Option<String>,   // 相对玩家方位/视线/VR射线/悬停/选中分区，如 "right 4m" / "pointed_ray"
  alert_tag: Option<String>        // 大型经营/策略聚合告警标签，如 "halted_no_material"
}

struct ActiveMethodGrant {
  method_id: String,               // 引用 CapabilityEntry.method_id（省去重复传 Schema）
  actor: ActorId,                  // 明确针对哪个主体/席位可用
  readiness: Readiness,            // 无特定 target_id 的纯参数型方法直接使用此就绪态
  targets: List<TargetCandidate>   // 聚合后的候选目标列表（大型游戏仅放告警/焦点目标，禁倾倒静默实体）
}

struct MethodActorKey {
  method_id: String,
  actor: ActorId
}

// 3. 动态同步帧（源点 -> 枢纽支持 full / delta，并原子捎带已异步完结的耗时步骤回执）
struct OriginSyncFrame {
  slot_id: String,                 // 关联角色槽位 ID
  epoch: Int64,                    // 世界代次（读档/切图/重置回合时递增，旧代次自动作废）
  rev: Int64,                      // 同代次内严格递增的状态修订号
  base_rev: Option<Int64>,         // mode == "delta" 时必填，必须等于枢纽当前最新 rev
  mode: "full" | "delta",
  significant_event: Bool,         // 是否跨越关键事件阈值（用于唤醒常驻静默休眠的慢节奏/挂机游戏）
  state_brief: Map<String, Any>,   // 轻量状态摘要（血量/回合/账本快照/新解锁线索；严禁含隐藏秘密或谜底）
  upserted_methods: List<ActiveMethodGrant>, // full 时为全集，delta 时为新增或变更项
  removed_methods: List<MethodActorKey>,     // delta 时移除的 {method_id, actor} 键列表
  settled_executions: List<OriginExecuteReply> // 与状态变更同帧原子送达的异步耗时步骤终态回执
}

// 4. 投影至演算中枢的精简上下文（枢纽 -> 中枢）
struct ProjectedContext {
  slot_id: String,
  epoch: Int64,
  rev: Int64,
  capability_table_digest: String, // 校验静态能力表缓存一致性
  player_command: Option<String>,  // 若由玩家主动下令触发，直接随包附带口令文本
  state_brief: Map<String, Any>,
  active_methods: List<ActiveMethodGrant>, // 仅包含当前 ready / staged 的活跃子集
  visual_ref: Option<MediaFrameRef>,       // 玩家开启画面模块时附带
  audio_ref: Option<MediaFrameRef>         // 玩家开启音频模块时附带
}

// 5. 方法调用队列与执行回执
struct QueueStep {
  step_index: Int32,
  method_id: String,
  actor: ActorId,
  args: Map<String, Any>
}

struct MethodCallQueue {
  queue_id: String,                // 演算中枢生成的幂等队列 ID
  epoch: Int64,
  based_on_rev: Int64,
  trigger: "player_command" | "proactive",
  supersedes: Bool,                // true 时抢占并取消同槽位正在运行的旧队列
  intent_summary: String,          // 供整队单次确认弹窗展示给玩家的简明意图摘要
  steps: List<QueueStep>           // 支持 1..N 步（单步操作即为长度 1 的队列）
}

struct StepReceipt {
  step_index: Int32,
  method_id: String,
  actor: ActorId,
  state: StepState,
  effect_summary: Option<Map<String, Any>>, // 如 {"loot": ["gold_50", "potion_1"]}
  failure_reason: Option<String>
}

struct QueueReceipt {
  queue_id: String,
  queue_state: "awaiting_confirmation" | "running" | "completed" | "aborted" | "cancelled",
  step_receipts: List<StepReceipt>,
  latest_context: Option<ProjectedContext>  // 完成或熔断时附带最新活跃方法，省一次往返拉取
}

// 6. 冻结授权范围（Scope）
struct FrozenScope {
  player_id: String,
  core_id: String,
  game_instance_id: String,
  slot_id: String,
  role_kind: RoleKind,
  billing_mode: BillingMode,
  permitted_methods: Map<String, List<ActorId>>, // method_id -> 允许的 actor 集合
  capability_table_digest: String,
  allow_visual: Bool,
  allow_audio: Bool,
  allow_chat: Bool
}
```

---

<a id="section-1-4"></a>

### 1.4 RFC 8785（JCS）规范化摘要工具伪代码

静态能力表缓存校验、冻结 `Scope` 绑定与整队玩家确认防篡改凭证**必须**共用以下域分离摘要函数：

```text
fn validate_strict_json_value(val: Any) -> Result<Void, G2AError> {
  // 递归校验：拒绝 NaN、+Infinity、-Infinity 及同层重复对象键；允许标准整数与有限 IEEE-754 浮点数
  if is_float(val) and (is_nan(val) or is_infinite(val)) {
    return Err(G2AError("invalid_request", 400, "Non-finite float is forbidden"))
  }
  if is_object(val) {
    require not has_duplicate_keys(val) else G2AError("invalid_request", 400, "Duplicate JSON key")
    for (_, child) in val { validate_strict_json_value(child)? }
  } else if is_array(val) {
    for item in val { validate_strict_json_value(item)? }
  }
  return Ok()
}

fn jcs_sha256(domain_tag: String, value: Any) -> Result<String, G2AError> {
  validate_strict_json_value(value)?
  canonical_utf8: Bytes = rfc8785_canonicalize_utf8(value)
  // 域分离前缀防止跨对象摘要碰撞：如 "g2a.cap.v1\0" / "g2a.scope.v1\0" / "g2a.confirm.v1\0"
  digest_hex: String = sha256_hex(utf8_bytes(domain_tag + "\0") + canonical_utf8)
  return Ok("sha256:" + digest_hex)
}
```

---

<a id="section-2"></a>

## 2. 第一层：交互源点 SDK（Interaction Origin SDK）伪代码规范

本章面向**游戏引擎 SDK 开发者**与**游戏接入程序员**，展示如何以极薄代码同时支持“无实体信号快照游戏”与“具身空间漫游游戏”，并将物理按键表现层与业务效果结算层彻底解耦。

<a id="section-2-1"></a>

### 2.1 引擎宿主适配端口（Engine & Host Ports）

各游戏引擎（Godot / Unity / Unreal / 自研 C++）实现专属 SDK 时，仅需对接以下三个轻量宿主接口：

```text
// 单步业务效果回调返回值：瞬时终态，或挂起一个可取消的持续动作句柄
enum EffectInvocationResult {
  ImmediateSucceeded(effect_summary: Map<String, Any>),
  ImmediateFailed(reason: String),
  StartedExecuting(cancel_fn: Fn() -> Void) // 耗时动作启动成功，完成后由引擎调 OriginSDK.complete_step(...)
}

interface EngineDispatcherPort {
  // 确保单步效果回调安全切回游戏逻辑主线程（如 Godot call_deferred / Unity MainThreadQueue）执行
  fn run_on_game_thread<T>(task: Fn() -> T) -> T
}

interface SpatialAdapterPort {
  // 仅具身空间/XR 游戏需要实现；纯面板/策略/经营/推理解谜游戏传入 NullSpatialAdapter 即可
  fn get_actor_pose(actor: ActorId) -> Option<Pose3D>
  fn get_player_focus() -> PlayerFocusInfo // 含玩家位置、朝向、头部视线、VR 手柄指向射线或鼠标悬停目标
  fn query_nearby_interactables(origin: Pose3D, perception_radius: Float) -> List<InteractableRef>
}

interface HubTransportClientPort {
  // 单机：本机回环 HTTP / Named Pipe / Unix Socket；网游：服务端内网 HTTP/2 或 mTLS
  fn post_to_hub<TReq, TRes>(operation: String, payload: TReq) -> Result<TRes, G2AError>
}
```

---

<a id="section-2-2"></a>

### 2.2 面向游戏开发者的接入 API（信号快照模式 + 具身空间差分模式）

游戏业务代码只和 `OriginSDK` 的声明式注册函数打交道，**无需编写任何网络通信、JSON 拼接或 `if (actor == "player")` 分支**：

```text
// 动作效果处理器签名：直接绑定游戏底层业务生效函数（严禁绑定带按键互斥锁或手部前摇动画的按键包装层！）
type DomainEffectHandler = Fn(
  actor: ActorId,
  subject_instance: Any,          // SDK 自动按 actor 路由出的角色实例、分管沙盘或玩家主席位控制器
  args: Map<String, Any>,
  step_token: StepExecutionToken  // 持续型动作保存此 token，结束时调用 complete_step
) -> EffectInvocationResult

class OriginSDK {
  state capabilities: Map<String, RegisteredCapability> = {}
  state actors: Map<ActorId, Any> = {}               // "player" -> 玩家控制器/主角; "companion" -> 伴游实例或辅助图层
  state signal_modules: Map<String, SignalModule> = {} // 信号驱动模块表（策略/经营/卡牌/解谜）
  state in_flight_steps: Map<String, ActiveStepCtx> = {}
  state current_epoch: Int64 = 1
  state current_rev: Int64 = 0
  state last_sent_methods: Map<(String, ActorId), ActiveMethodGrant> = {}
  state last_sent_brief_digest: String = ""
  state pending_settled_executions: List<OriginExecuteReply> = []

  // [接入 API 1] 入局注册通用领域原语（如 #01 move_to, #02 interact, #04 toggle_flashlight, #05 trade_resource）
  fn register_capability(def: CapabilityEntry, effect_handler: DomainEffectHandler,
                         readiness_check: Option<Fn(ActorId, Any) -> Option<Readiness>>) {
    // 安全铁律：独立 NPC 槽位注册时自动剥离 "player" 主体权限
    if this.slot_role_kind == "independent_npc" {
      def.permitted_actors = def.permitted_actors.filter(a => a != "player")
    }
    this.capabilities[def.method_id] = RegisteredCapability(def, effect_handler, readiness_check)
  }

  // 入局完成全部原语注册（或章节解锁新系统）后调用一次，向智能枢纽发布静态能力总表并推送首帧全量状态
  fn publish_capabilities_and_baseline() -> Result<Void, G2AError> {
    defs = [reg.def for (_, reg) in sorted_by_id(this.capabilities)]
    cap_digest = jcs_sha256("g2a.cap.v1", defs)?
    this.hub_transport.post_to_hub("origin.capabilities", {
      "slot_id": this.slot_id, "role_kind": this.slot_role_kind,
      "billing_mode": this.billing_mode, "capability_table_digest": cap_digest,
      "capabilities": defs
    })?
    return this.flush_full_sync()
  }

  // [接入 API 2] 绑定执行主体或作用席位实例（具身预制体或无实体席位控制器各调一次）
  fn bind_actor_subject(actor: ActorId, instance: Any) {
    this.actors[actor] = instance
  }

  // [接入 API 3A · 面向策略/模拟经营/卡牌/推理解谜] 绑定信号快照数据模块（零空间坐标）
  // 示例：对接经济钱包、合成台、日程时钟或线索管理器，当模块发出 changed 信号时调 notify_module_changed
  fn bind_state_module(module_name: String,
                       snapshot_fn: Fn() -> Map<String, Any>,
                       active_methods_fn: Fn() -> List<ActiveMethodGrant>) {
    this.signal_modules[module_name] = SignalModule(snapshot_fn, active_methods_fn, dirty = true)
  }

  fn notify_module_changed(module_name: String, significant_event: Bool = false) {
    if module_name in this.signal_modules {
      this.signal_modules[module_name].dirty = true
      this.flush_dirty_sync(significant_event)
    }
  }

  // [接入 API 4] 读档回退、切换关卡、重置回合或切换阵营时推进世界代次
  fn advance_epoch() {
    this.current_epoch += 1
    this.current_rev = 0
    this.last_sent_methods.clear()
    this.cancel_all_in_flight_steps("epoch_advanced")
    this.flush_full_sync()
  }

  // [接入 API 5] 玩家席位权威信号上报（由游戏原生输入/会话生命周期调用）
  fn report_player_command(command_text: String) {
    this.flush_dirty_sync(significant_event = true) // 先确保最新状态已同步至智能枢纽
    this.hub_transport.post_to_hub("origin.player_event", {
      "slot_id": this.slot_id, "kind": "player_command", "text": command_text
    })
  }

  fn report_player_presence(online: Bool, remaining_online_humans_in_room: Int32 = 0) {
    if not online and remaining_online_humans_in_room == 0 {
      // 当本槽位关联玩家离线且局内已无真人玩家时，停止后续状态采集（已在执行中的最后单步自然收尾）
      this.sync_enabled = false
    } else {
      this.sync_enabled = true
    }
    this.hub_transport.post_to_hub("origin.player_event", {
      "slot_id": this.slot_id, "kind": "presence_changed",
      "online": online, "remaining_online_humans": remaining_online_humans_in_room
    })
  }

  fn report_emergency_stop() {
    this.cancel_all_in_flight_steps("player_emergency_stop")
    this.hub_transport.post_to_hub("origin.player_event", {
      "slot_id": this.slot_id, "kind": "emergency_stop"
    })
  }

  // 当全屏主机/VR 游戏采用局内已验证玩家席位审批面板时，向智能枢纽上报非真实法币队列的整队审批结果
  fn report_queue_approval(session_id: String, queue_id: String, queue_digest: String,
                           fingerprint: String, approved: Bool) {
    this.hub_transport.post_to_hub("origin.player_event", {
      "slot_id": this.slot_id, "kind": "queue_approval",
      "session_id": session_id, "queue_id": queue_id, "queue_digest": queue_digest,
      "fingerprint": fingerprint, "approved": approved
    })
  }
}
```

---

<a id="section-2-3"></a>

### 2.3 后台脏差分与海量对象聚合器伪代码

无论游戏采用信号快照模式、空间差分模式还是两者混合（如带化身生活模拟），SDK 统一通过 `collect_and_diff` 生成最小 `delta` 帧（**状态与可用方法均无变化时零发包**）：

```text
const MAX_CANDIDATE_TARGETS_PER_METHOD = 24 // 防止大型经营/策略游戏倾倒数千静默建筑

// 合并同一 (method_id, actor) 来自多信号模块或空间扫描器的目标集，防止混合品类相互覆盖
fn merge_method_grant(grants: Map<(String, ActorId), ActiveMethodGrant>, incoming: ActiveMethodGrant) {
  key = (incoming.method_id, incoming.actor)
  if Some(existing) = grants.get(key) {
    merged_targets = deduplicate_by_target_id(existing.targets + incoming.targets)
    overall = if existing.readiness == "ready" or incoming.readiness == "ready"
                 or any(t.readiness == "ready" for t in merged_targets) { "ready" } else { "staged" }
    grants[key] = ActiveMethodGrant(
      incoming.method_id, incoming.actor, overall,
      prioritize_alerts_and_focus(merged_targets, limit = MAX_CANDIDATE_TARGETS_PER_METHOD)
    )
  } else {
    incoming.targets = prioritize_alerts_and_focus(incoming.targets, limit = MAX_CANDIDATE_TARGETS_PER_METHOD)
    grants[key] = incoming
  }
}

fn OriginSDK.collect_current_view() -> (Map<String, Any>, Map<(String, ActorId), ActiveMethodGrant>) {
  brief: Map<String, Any> = {}
  grants: Map<(String, ActorId), ActiveMethodGrant> = {}

  // 1. 汇总信号驱动模块快照与可用方法（模拟经营账本、策略手牌、已解锁推理线索；绝不含未揭晓谜底！）
  for (mod_name, mod) in this.signal_modules {
    brief[mod_name] = mod.snapshot_fn()
    for g in mod.active_methods_fn() {
      merge_method_grant(grants, g)
    }
  }

  // 2. 汇总具身组件与空间感知（若注入了 SpatialAdapterPort）
  if this.spatial != null {
    player_focus = this.spatial.get_player_focus()
    for (method_id, reg) in this.capabilities {
      for actor in reg.def.permitted_actors {
        if actor not in this.actors { continue } // 例如无实体伴游不存在 companion 肉身，自动跳过！
        subject = this.actors[actor]

        // 2a. 非空间目标类角色装备能力（如 #04 toggle_flashlight 分别检查伴游和玩家各自是否有手电筒）
        if reg.readiness_check != null {
          if Some(r) = reg.readiness_check(actor, subject) {
            merge_method_grant(grants, ActiveMethodGrant(method_id, actor, r, targets = []))
          }
        }

        // 2b. 空间目标类能力（以当前 actor 自身位置为距离/可达性校验原点，同时附带相对玩家的双视角锚点！）
        if reg.is_spatial_target_verb and Some(actor_pose) = this.spatial.get_actor_pose(actor) {
          candidates: List<TargetCandidate> = []
          for obj in this.spatial.query_nearby_interactables(actor_pose, this.perception_radius) {
            if obj.is_hidden_secret_unrevealed() { continue } // 严禁外泄未揭晓暗门或隐藏宝箱
            dist_to_actor = distance(actor_pose, obj.pose)
            readiness = if dist_to_actor <= obj.interact_range { "ready" } else { "staged" }
            candidates.append(TargetCandidate(
              target_id = obj.id,
              label = obj.display_name,
              readiness = readiness,
              prerequisite_hint = if readiness == "staged" { Some("requires_proximity") } else { None },
              actor_anchor = format_distance_bearing(actor_pose, obj.pose),
              player_anchor = compute_player_deictic_label(player_focus, obj), // 如 "right 4m" / "pointed_ray"
              alert_tag = obj.alert_tag
            ))
          }
          if not candidates.is_empty() {
            overall = if any(c.readiness == "ready" for c in candidates) { "ready" } else { "staged" }
            merge_method_grant(grants, ActiveMethodGrant(method_id, actor, overall, candidates))
          }
        }
      }
    }
  }
  return (brief, grants)
}

fn OriginSDK.flush_dirty_sync(significant_event: Bool) {
  if not this.sync_enabled and this.pending_settled_executions.is_empty() { return }
  (brief, current_grants, settled_batch) = this.engine_dispatcher.run_on_game_thread(() => {
    (b, g) = this.collect_current_view()
    s = this.pending_settled_executions.drain_all()
    return (b, g, s)
  })
  brief_digest = jcs_sha256("g2a.brief.v1", brief).unwrap()

  upserted: List<ActiveMethodGrant> = []
  removed: List<MethodActorKey> = []

  for (key, grant) in current_grants {
    if key not in this.last_sent_methods or this.last_sent_methods[key] != grant {
      upserted.append(grant)
    }
  }
  for ((m_id, act), _) in this.last_sent_methods {
    if (m_id, act) not in current_grants { removed.append(MethodActorKey(m_id, act)) }
  }

  // 完全无变化且无异步完结步骤时零发包！
  if brief_digest == this.last_sent_brief_digest and upserted.is_empty()
     and removed.is_empty() and settled_batch.is_empty() {
    return
  }

  prev_rev = this.current_rev
  this.current_rev += 1
  frame = OriginSyncFrame(
    slot_id = this.slot_id, epoch = this.current_epoch, rev = this.current_rev,
    base_rev = Some(prev_rev), mode = "delta", significant_event = significant_event,
    state_brief = brief, upserted_methods = upserted, removed_methods = removed,
    settled_executions = settled_batch
  )
  this.last_sent_brief_digest = brief_digest
  this.last_sent_methods = current_grants
  this.hub_transport.post_to_hub("origin.sync", frame)
}

fn OriginSDK.flush_full_sync() -> Result<Void, G2AError> {
  (brief, current_grants, settled_batch) = this.engine_dispatcher.run_on_game_thread(() => {
    (b, g) = this.collect_current_view()
    s = this.pending_settled_executions.drain_all()
    return (b, g, s)
  })
  this.current_rev += 1
  frame = OriginSyncFrame(
    slot_id = this.slot_id, epoch = this.current_epoch, rev = this.current_rev,
    base_rev = None, mode = "full", significant_event = true,
    state_brief = brief, upserted_methods = values(current_grants), removed_methods = [],
    settled_executions = settled_batch
  )
  this.last_sent_brief_digest = jcs_sha256("g2a.brief.v1", brief)?
  this.last_sent_methods = current_grants
  return this.hub_transport.post_to_hub("origin.sync", frame)
}
```

---

<a id="section-2-4"></a>

### 2.4 源点接口（Origin Interface）四大原语处理器伪代码

当**智能枢纽**向**交互源点**下发 `origin.execute` 时，SDK 在游戏逻辑线程中直接调用业务效果函数，并原生管理持续型动作的异步收尾与中途取消：

```text
struct OriginExecuteRequest {
  slot_id: String,
  epoch: Int64,
  kind: "invoke" | "cancel" | "deliver_chat", // 统一收敛于单个 origin.execute 原语，不增设私有旁路接口
  execution_id: String,                       // 智能枢纽生成的唯一执行/消息票据 ID
  method_id: Option<String>,                  // kind == "invoke" 时必填
  actor: Option<ActorId>,                     // kind == "invoke" 时必填
  args: Map<String, Any>                      // invoke 时为方法参数；deliver_chat 时含 audience/text/ai_provenance
}

struct OriginExecuteReply {
  execution_id: String,
  state: "executing" | "succeeded" | "failed" | "cancelled",
  effect_summary: Option<Map<String, Any>>,
  failure_reason: Option<String>
}

// 接收来自智能枢纽的请求（仅接受本机认证通道或隔离服务端内网，严格遵循源点接口 4 原语契约）
fn OriginSDK.handle_origin_execute(req: OriginExecuteRequest) -> Result<OriginExecuteReply, G2AError> {
  if req.kind == "cancel" {
    return Ok(this.cancel_in_flight_step(req.execution_id))
  }
  if req.kind == "deliver_chat" {
    return this.engine_dispatcher.run_on_game_thread(() => {
      this.chat_ui_handler(req.args["audience"], req.args["text"], verified_ai = true)
      return Ok(OriginExecuteReply(req.execution_id, "succeeded", None, None))
    })
  }

  // kind == "invoke"：1. 幂等保护
  if req.execution_id in this.execution_ledger {
    return Ok(this.execution_ledger[req.execution_id])
  }

  return this.engine_dispatcher.run_on_game_thread(() => {
    method_id = req.method_id.unwrap()
    actor = req.actor.unwrap()
    // 2. 校验世界代次、方法存在性与主体合法性
    require req.epoch == this.current_epoch else G2AError("stale_context", 409, "Epoch mismatch")
    require method_id in this.capabilities else G2AError("invalid_arguments", 400, "Unknown method_id")
    reg = this.capabilities[method_id]
    require actor in reg.def.permitted_actors else G2AError("permission_denied", 403, "Actor not permitted")
    require actor in this.actors else G2AError("not_found", 404, "Actor subject not present")
    validate_against_json_schema(req.args, reg.def.params_schema)?

    subject_instance = this.actors[actor]
    token = StepExecutionToken(req.execution_id)

    // 3. 绕过物理键位锁与玩家手部前摇动画，直达业务效果层！
    match reg.effect_handler(actor, subject_instance, req.args, token) {
      ImmediateSucceeded(summary) => {
        reply = OriginExecuteReply(req.execution_id, "succeeded", Some(summary), None)
        this.execution_ledger[req.execution_id] = reply
        this.flush_dirty_sync(significant_event = false) // 效果生效后立即增量同步最新可用方法（如 #06 变为 ready）
        return Ok(reply)
      }
      ImmediateFailed(reason) => {
        reply = OriginExecuteReply(req.execution_id, "failed", None, Some(reason))
        this.execution_ledger[req.execution_id] = reply
        this.flush_dirty_sync(significant_event = false)
        return Ok(reply)
      }
      StartedExecuting(cancel_fn) => {
        // 耗时动作（如寻路 5m、跃迁蓄力 5s、持续踩踏双人压力板）：先返回 executing，不阻塞帧循环
        this.in_flight_steps[req.execution_id] = ActiveStepCtx(cancel_fn)
        reply = OriginExecuteReply(req.execution_id, "executing", None, None)
        this.execution_ledger[req.execution_id] = reply
        return Ok(reply)
      }
    }
  })
}

// 供引擎异步任务（如 NavigationAgent 寻路抵达或蓄力完成回调）结束时调用
fn OriginSDK.complete_step(execution_id: String, succeeded: Bool,
                           summary: Option<Map<String, Any>>, reason: Option<String>) {
  this.engine_dispatcher.run_on_game_thread(() => {
    if execution_id not in this.in_flight_steps { return } // 若已被取消结算则忽略迟到回调
    this.in_flight_steps.remove(execution_id)
    final_state = if succeeded { "succeeded" } else { "failed" }
    reply = OriginExecuteReply(execution_id, final_state, summary, reason)
    this.execution_ledger[execution_id] = reply
    // 将完结回执放入待发队列，随同最新可用方法在同一个 origin.sync 增量帧内原子送达智能枢纽，彻底消除时序竞态！
    this.pending_settled_executions.append(reply)
  })
  this.flush_dirty_sync(significant_event = false)
}

fn OriginSDK.cancel_in_flight_step(execution_id: String) -> OriginExecuteReply {
  return this.engine_dispatcher.run_on_game_thread(() => {
    if execution_id in this.in_flight_steps {
      ctx = this.in_flight_steps.remove(execution_id)
      ctx.cancel_fn() // 立即停止伴游寻路或中断引擎蓄力
      reply = OriginExecuteReply(execution_id, "cancelled", None, Some("cancelled_by_hub"))
      this.execution_ledger[execution_id] = reply
      this.pending_settled_executions.append(reply)
      this.flush_dirty_sync(significant_event = false)
      return reply
    }
    return this.execution_ledger.get_or_default(
      execution_id, OriginExecuteReply(execution_id, "cancelled", None, None)
    )
  })
}
```

---

<a id="section-3"></a>

## 3. 第二层：智能枢纽核心（Intelligent Hub Engine）伪代码规范

**智能枢纽**是整个协议的安全盾牌与状态机中心（单机模式下全电脑共享单实例；网游模式下部署于服务端集群）。本章伪代码完整定义其会话生命周期、视图投影与 `QueueScheduler` 调度逻辑。

<a id="section-3-1"></a>

### 3.1 枢纽持久化账本与受信任交互端口

```text
interface HubPersistencePort {
  // 提供按 slot_id / session_id 隔离的原子读写事务（崩溃重启后保留去重账本与已生效权限状态）
  fn atomic<T>(lock_key: String, tx: Fn(HubStore) -> Result<T, G2AError>) -> Result<T, G2AError>
}

interface TrustedPlayerConsentPort {
  // 唯一合法的玩家授权与整队确认通道（本地枢纽原生安全弹窗或经认证的游戏内原生审批面板）
  // 严禁将此端口挂载到面向演算中枢的中枢接口路由上！
  fn prompt_session_scope(scope: FrozenScope) -> AsyncDecision<Bool>
  fn prompt_session_resume(session_id: String) -> AsyncDecision<Bool>
  fn prompt_queue_confirmation(session_id: String, queue_id: String, queue_digest: String,
                               intent_summary: String, steps_preview: List<StepPreview>,
                               require_native_real_money_ui: Bool) -> AsyncDecision<Bool>
}

interface OriginClientPort {
  // 通过源点接口向交互源点下发唯一指令原语 "origin.execute"（含 invoke / cancel / deliver_chat）
  fn execute(req: OriginExecuteRequest) -> Result<OriginExecuteReply, G2AError>
}

interface CorePushStreamPort {
  // 向已认证演算中枢的 SSE / WebSocket 连接推送实时事件帧
  fn push_event(session_id: String, event_name: String, payload: Any) -> Void
}

struct SessionRecord {
  session_id: String,
  scope: FrozenScope,
  scope_digest: String,
  state: "active" | "disconnected_grace" | "paused_awaiting_player" | "closed",
  player_online: Bool,
  local_fallback_activated: Bool,
  lease_deadline_ms: Int64,
  active_queue_id: Option<String>,
  consumption_used: Int64,
  consumption_cap: Option<Int64>
}

struct QueueLedgerRecord {
  session_id: String,
  queue_id: String,
  queue_digest: String,            // jcs_sha256("g2a.confirm.v1", {session_id, queue_id, steps})
  queue: MethodCallQueue,
  state: "awaiting_confirmation" | "running" | "completed" | "aborted" | "cancelled",
  requires_real_money_ui: Bool,    // true 时仅接受本地/平台原生安全界面确认，拒绝局内普通面板代批
  approved_digest: Option<String>, // 玩家在受信任通道批准后写入
  step_receipts: List<StepReceipt>,
  current_execution_id: Option<String>
}
```

---

<a id="section-3-2"></a>

### 3.2 会话授权、租约续期、双层闪断恢复与玩家离线即停状态机

```text
// 1. 中枢接口：session.authorize
fn HubEngine.handle_session_authorize(caller_principal: VerifiedPrincipal,
                                      req: AuthorizeRequest) -> Result<AuthorizeReply, G2AError> {
  require req.g2a_version == G2A_WIRE_VERSION else G2AError("unsupported_version", 400, "Require 0.0.1")
  for ext in req.extensions {
    if ext.required and not this.supports_extension(ext.name) {
      return Err(G2AError("unsupported_capability", 400, "Unsupported required extension: " + ext.name))
    }
  }

  slot = this.get_slot_or_err(req.slot_id)?
  require slot.player_online else G2AError("permission_denied", 403, "Associated player is offline")

  // 若该槽位配置了合规/反外挂白名单（FRAND 对等准则），校验 caller_principal
  if slot.allowlist_enabled {
    require slot.is_allowed_core(caller_principal.core_id) else G2AError("permission_denied", 403, "Core not allowlisted")
  }

  // 计算能力表摘要与交集冻结 Scope（支持不等于授权：求 请求范围 ∩ 游戏开放范围）
  cap_digest = slot.capability_table_digest
  narrowed_scope = intersect_with_origin_capabilities(req.requested_scope, slot, caller_principal.core_id, cap_digest)
  scope_digest = jcs_sha256("g2a.scope.v1", narrowed_scope)?

  // 经受信任玩家通道审批（除非命中玩家本人预先为完全相同 scope_digest 设置的未过期自动加入规则）
  approved = this.consent_port.prompt_session_scope(narrowed_scope).await_result()
  require approved else G2AError("permission_denied", 403, "Player declined authorization")

  return this.persistence.atomic(req.slot_id, store => {
    require slot.player_online else G2AError("permission_denied", 403, "Player went offline during consent")
    session_id = generate_id("sess")
    store.sessions[session_id] = SessionRecord(
      session_id = session_id, scope = narrowed_scope, scope_digest = scope_digest,
      state = "active", player_online = true, local_fallback_activated = false,
      lease_deadline_ms = clock.now_ms() + LEASE_TTL_MS,
      active_queue_id = None, consumption_used = 0, consumption_cap = req.consumption_cap
    )
    // 若演算中枢已缓存相同 cap_digest，免重传完整静态能力表以节省带宽
    table_to_send = if req.cached_capability_digest == Some(cap_digest) { None } else { Some(slot.capabilities) }
    return Ok(AuthorizeReply(session_id, scope_digest, cap_digest, table_to_send))
  })
}

// 2. 玩家在线即停铁律（由 origin.player_event(presence_changed) 触发）
fn HubEngine.on_player_presence_changed(slot_id: String, online: Bool, remaining_online_humans: Int32) {
  this.persistence.atomic(slot_id, store => {
    slot = store.slots[slot_id]
    slot.player_online = online
    // 铁律 A：若局内所有真人玩家均已离线（remaining_online_humans == 0），无论 companion 还是 developer_sponsored NPC 一律立即停机！
    // 铁律 B：若关联玩家本人离线，其个人 companion 与 player_metered NPC 立即停止原持有者计费与未发队列！
    if not online {
      for sess in store.sessions_for_slot(slot_id) {
        sess.player_online = false
        should_stop = (remaining_online_humans == 0)
                      or (sess.scope.role_kind == "companion")
                      or (sess.scope.billing_mode == "player_metered")
        if should_stop {
          // 注意：清空所有未下发的 pending 步骤；已在交互源点处于 executing 的最后单步按游戏规则自然收尾
          this.clear_undispatched_queues_in_tx(store, sess, reason = "player_offline")
          sess.state = "closed"
          this.push_stream.push_event(sess.session_id, "session.closed", {"reason": "player_offline"})
        }
      }
    }
    return Ok()
  })
}

// 3. 游玩期间双层闪断恢复（session.resume 与受信任继续确认回调）
fn HubEngine.handle_session_resume(caller: VerifiedPrincipal, session_id: String) -> Result<ResumeReply, G2AError> {
  need_prompt = false
  reply = this.persistence.atomic(session_id, store => {
    sess = store.get_session_for_caller(session_id, caller)?
    require sess.player_online and sess.state != "closed" else G2AError("revoked", 403, "Session closed")

    if clock.now_ms() < sess.lease_deadline_ms and not sess.local_fallback_activated {
      // 第一层：活动租约内且本地脚本未接管 -> 无缝恢复！
      sess.state = "active"
      sess.lease_deadline_ms = clock.now_ms() + LEASE_TTL_MS
      return Ok(ResumeReply(actions_paused = false, latest_context = this.project_context(store, sess)))
    } else {
      // 第二层：已超时或本地脚本已接管 -> 保持行动暂停，必须等待真人玩家确认继续（零断线补录）
      sess.state = "paused_awaiting_player"
      sess.lease_deadline_ms = clock.now_ms() + LEASE_TTL_MS
      need_prompt = true
      return Ok(ResumeReply(actions_paused = true, latest_context = this.project_context(store, sess)))
    }
  })?
  if need_prompt { this.trigger_player_resume_prompt_async(session_id) }
  return Ok(reply)
}

fn HubEngine.on_trusted_resume_decision(session_id: String, approved: Bool) {
  this.persistence.atomic(session_id, store => {
    sess = store.sessions.get(session_id)
    if sess == null or sess.state != "paused_awaiting_player" { return Ok() }
    if approved and sess.player_online {
      sess.state = "active"
      sess.local_fallback_activated = false
      sess.lease_deadline_ms = clock.now_ms() + LEASE_TTL_MS
      this.push_stream.push_event(session_id, "session.resumed", this.project_context(store, sess))
    } else {
      sess.state = "closed"
      this.push_stream.push_event(session_id, "session.closed", {"reason": "resume_declined"})
    }
    return Ok()
  })
}

// 4. 中枢接口：session.heartbeat（续期控制租约，严禁延长离线玩家的在线状态！）& session.close（幂等关闭）
fn HubEngine.handle_session_heartbeat(caller: VerifiedPrincipal, session_id: String) -> Result<HeartbeatReply, G2AError> {
  return this.persistence.atomic(session_id, store => {
    sess = store.get_session_for_caller(session_id, caller)?
    require sess.player_online and sess.state != "closed" else G2AError("revoked", 403, "Player offline or session closed")
    sess.lease_deadline_ms = clock.now_ms() + LEASE_TTL_MS
    return Ok(HeartbeatReply(lease_deadline_ms = sess.lease_deadline_ms))
  })
}

fn HubEngine.handle_session_close(caller: VerifiedPrincipal, session_id: String) -> Result<Void, G2AError> {
  execs_to_cancel: List<(String, Int64, String)> = []
  this.persistence.atomic(session_id, store => {
    sess = store.get_session_for_caller(session_id, caller)?
    if sess.state != "closed" {
      execs_to_cancel = this.cancel_and_fence_session_queues_in_tx(store, sess, reason = "session_closed")
      sess.state = "closed"
    }
    return Ok() // 重复关闭幂等返回成功
  })?
  for (slot_id, epoch, exec_id) in execs_to_cancel {
    this.origin_client.execute(OriginExecuteRequest(slot_id, epoch, "cancel", exec_id, None, None, {}))
  }
  return Ok()
}

// 5. 源点接口：origin.capabilities 与 origin.player_event 处理器
fn HubEngine.handle_origin_capabilities(payload: OriginCapabilitiesPayload) -> Result<Void, G2AError> {
  verified_digest = jcs_sha256("g2a.cap.v1", payload.capabilities)?
  require verified_digest == payload.capability_table_digest
    else G2AError("invalid_arguments", 400, "Capability table digest mismatch")
  return this.persistence.atomic(payload.slot_id, store => {
    slot = store.get_or_create_slot(payload.slot_id, payload.role_kind, payload.billing_mode)
    slot.capabilities = payload.capabilities
    slot.capability_table_digest = verified_digest
    return Ok()
  })
}

fn HubEngine.handle_origin_player_event(ev: OriginPlayerEvent) -> Result<Void, G2AError> {
  match ev.kind {
    "presence_changed" => {
      this.on_player_presence_changed(ev.slot_id, ev.online, ev.remaining_online_humans)
      return Ok()
    }
    "emergency_stop" => {
      execs_to_cancel: List<(String, Int64, String)> = []
      this.persistence.atomic(ev.slot_id, store => {
        for sess in store.active_sessions_for_slot(ev.slot_id) {
          execs_to_cancel.extend(this.cancel_and_fence_session_queues_in_tx(store, sess, reason = "player_emergency_stop"))
        }
        return Ok()
      })?
      for (slot_id, epoch, exec_id) in execs_to_cancel {
        this.origin_client.execute(OriginExecuteRequest(slot_id, epoch, "cancel", exec_id, None, None, {}))
      }
      return Ok()
    }
    "player_command" => {
      // 免回查游戏：直接拼装【玩家口令 + 最新活跃可用方法】推送至演算中枢！
      return this.persistence.atomic(ev.slot_id, store => {
        for sess in store.active_sessions_for_slot(ev.slot_id) {
          ctx = this.project_context(store, sess, player_command = Some(ev.text))
          this.push_stream.push_event(sess.session_id, "context.push", ctx)
        }
        return Ok()
      })
    }
    "queue_approval" => {
      // 局内认证玩家席位整队审批上报（仅允许普通游戏动作队列；涉及真实法币交易强制走平台原生安全界面）
      this.persistence.atomic(ev.session_id, store => {
        rec = store.queues.get((ev.session_id, ev.queue_id))
        require rec != null and not rec.requires_real_money_ui
          else G2AError("permission_denied", 403, "Real-money confirmation requires native platform security UI")
        return Ok()
      })?
      this.on_trusted_confirmation_result(ev.session_id, ev.queue_id, ev.queue_digest, ev.fingerprint, ev.approved)
      return Ok()
    }
  }
}
```

---

<a id="section-3-3"></a>

### 3.3 状态合并器、活跃方法投影与静默期自适应节流器

```text
fn HubEngine.handle_origin_sync(frame: OriginSyncFrame) -> Result<Void, G2AError> {
  return this.persistence.atomic(frame.slot_id, store => {
    view = store.slot_views[frame.slot_id]

    // 代次变更或全量帧：原子替换视图并作废旧代次在途未发步骤
    if frame.mode == "full" or frame.epoch > view.epoch {
      view.epoch = frame.epoch
      view.rev = frame.rev
      view.last_significant_rev = frame.rev
      view.state_brief = frame.state_brief
      view.methods = map_by_method_actor(frame.upserted_methods)
      this.abort_obsolete_epoch_queues_in_tx(store, frame.slot_id, frame.epoch)
    } else {
      require frame.epoch == view.epoch and frame.base_rev == Some(view.rev)
        else G2AError("stale_context", 409, "Origin delta base_rev mismatch; resend full frame")
      view.rev = frame.rev
      if frame.significant_event { view.last_significant_rev = frame.rev }
      view.state_brief = frame.state_brief
      for k in frame.removed_methods { view.methods.remove((k.method_id, k.actor)) }
      for g in frame.upserted_methods { view.methods[(g.method_id, g.actor)] = g }
    }

    // 同一帧内原子消费已完结的异步耗时步骤回执，唤醒等待下一步就绪的 QueueScheduler
    for settled in frame.settled_executions {
      this.notify_execution_waiter_in_tx(store, settled)
    }
    this.notify_view_updated_waiters(frame.slot_id)

    // 静默期自适应降频休眠控制（针对放置挂机 / 电子宠物 / 慢节奏经营）：
    // 仅当 significant_event == true，或距离上次推送已超过自适应退避间隔时，才主动唤醒中枢
    for sess in store.active_sessions_for_slot(frame.slot_id) {
      if frame.significant_event {
        sess.idle_backoff_ms = MIN_SYNC_INTERVAL_MS
        this.push_stream.push_event(sess.session_id, "context.push", this.project_context(store, sess))
      } else {
        sess.idle_backoff_ms = min(sess.idle_backoff_ms * 2, MAX_IDLE_SLEEP_INTERVAL_MS)
      }
    }
    return Ok()
  })
}

// 按冻结 Scope 裁剪并仅投影当前活跃（ready / staged）方法序号，大幅压缩推理上下文体积
fn HubEngine.project_context(store: HubStore, sess: SessionRecord,
                             player_command: Option<String> = None) -> ProjectedContext {
  view = store.slot_views[sess.scope.slot_id]
  projected: List<ActiveMethodGrant> = []
  for ((method_id, actor), grant) in view.methods {
    allowed_actors = sess.scope.permitted_methods.get_or_default(method_id, [])
    if actor in allowed_actors and grant.readiness in ["ready", "staged"] {
      projected.append(grant)
    }
  }
  return ProjectedContext(
    slot_id = sess.scope.slot_id, epoch = view.epoch, rev = view.rev,
    capability_table_digest = sess.scope.capability_table_digest,
    player_command = player_command, state_brief = view.state_brief,
    active_methods = projected,
    visual_ref = if sess.scope.allow_visual { view.latest_visual } else { None },
    audio_ref = if sess.scope.allow_audio { view.latest_audio } else { None }
  )
}

// 中枢接口：context.pull（含静默节流保护）与 chat.send（含受众与 AI 来源标记约束）
fn HubEngine.handle_context_pull(caller: VerifiedPrincipal, session_id: String) -> Result<ProjectedContext, G2AError> {
  return this.persistence.atomic(session_id, store => {
    sess = store.get_session_for_caller(session_id, caller)?
    require sess.player_online and sess.state == "active" else G2AError("permission_denied", 403, "Session not active")
    if clock.now_ms() < sess.next_allowed_pull_ms {
      return Err(G2AError("resource_limit", 429, "Adaptive idle sleep active",
                          retry_after_ms = Some(sess.next_allowed_pull_ms - clock.now_ms())))
    }
    sess.next_allowed_pull_ms = clock.now_ms() + sess.idle_backoff_ms
    return Ok(this.project_context(store, sess))
  })
}

fn HubEngine.handle_chat_send(caller: VerifiedPrincipal, session_id: String, msg: ChatMessage) -> Result<Void, G2AError> {
  chat_req = this.persistence.atomic(session_id, store => {
    sess = store.get_session_for_caller(session_id, caller)?
    require sess.player_online and sess.state == "active" and sess.scope.allow_chat
      else G2AError("permission_denied", 403, "Chat not authorized or player offline")
    if (session_id, msg.message_id) in store.chat_dedup { return Ok(None) }
    store.chat_dedup.insert((session_id, msg.message_id))
    // 强制注入可信 AI 来源标记，在事务锁外复用统一 origin.execute(kind="deliver_chat") 送达交互源点
    return Ok(Some(OriginExecuteRequest(
      slot_id = sess.scope.slot_id, epoch = store.slot_views[sess.scope.slot_id].epoch,
      kind = "deliver_chat", execution_id = "chat-" + msg.message_id,
      method_id = None, actor = None,
      args = {"audience": msg.audience, "text": msg.text, "ai_provenance": true}
    )))
  })?
  if Some(req) = chat_req {
    this.origin_client.execute(req)?
  }
  return Ok()
}
```

---

<a id="section-3-4"></a>

### 3.4 方法调用队列调度器（QueueScheduler）完整状态机伪代码

本节是**智能枢纽**最核心的控制逻辑，完整覆盖：**幂等去重 → 新指令抢占 → 三态门禁与 `actor = player` 防抢控制权 → 受信任确认摘要绑定与冷却 → 逐步重验 `ready` 与失败熔断**：

```text
// 精确解析某一步骤在当前视图中的目标级就绪态（防止将远距 staged 宝箱误判为近处另一 ready 宝箱）
fn resolve_step_readiness(grant: Option<ActiveMethodGrant>, args: Map<String, Any>) -> Option<Readiness> {
  if grant == null { return None }
  g = grant.unwrap()
  if g.targets.is_empty() { return Some(g.readiness) } // 无离散 target_id 的参数型方法（如开手电筒、输入密码）
  if Some(tid) = args.get("target_id") {
    for cand in g.targets {
      if cand.target_id == tid { return Some(cand.readiness) }
    }
    return None // 请求了不在当前合法可见候选列表中的目标（如隐藏宝箱或已消失目标）
  }
  return Some(g.readiness)
}

fn HubEngine.handle_queue_submit(caller: VerifiedPrincipal, session_id: String,
                                 q: MethodCallQueue) -> Result<QueueReceipt, G2AError> {
  queue_digest = jcs_sha256("g2a.confirm.v1", {
    "session_id": session_id, "queue_id": q.queue_id, "steps": q.steps
  })?

  // 阶段 A：事务内做鉴权、幂等检查、策略判定与入账
  // 关键事务准则：当命中 confirm 时必须先在事务内返回 Ok(NeedsConfirmation) 正常提交 awaiting_confirmation 账本记录，
  // 随后在事务外唤起确认弹窗并返回 409 confirmation_required，绝不能在事务内直接抛错导致账本回滚丢失！
  decision = this.persistence.atomic(session_id, store => {
    sess = store.get_session_for_caller(session_id, caller)?
    require sess.player_online and sess.state == "active"
      else G2AError("permission_denied", 403, "Session inactive, paused, or player offline")
    if Some(cap) = sess.consumption_cap {
      require sess.consumption_used < cap else G2AError("resource_limit", 429, "Player consumption cap reached")
    }

    view = store.slot_views[sess.scope.slot_id]
    require q.epoch == view.epoch and q.based_on_rev <= view.rev and q.based_on_rev >= view.last_significant_rev
      else G2AError("stale_context", 409, "Epoch or based_on_rev expired",
                    fresh_context = Some(this.project_context(store, sess)))
    require not q.steps.is_empty() and q.steps.len() <= MAX_QUEUE_STEPS
      else G2AError("invalid_arguments", 400, "Invalid step count")

    // 1. 前置防重放屏障：(session_id, queue_id) 精确去重
    if Some(existing) = store.queues.get((session_id, q.queue_id)) {
      // 严禁复用相同 queue_id 偷换步骤参数！
      require existing.queue_digest == queue_digest
        else G2AError("conflict", 409, "queue_id reused with different steps or arguments")

      if existing.state != "awaiting_confirmation" {
        return Ok(EarlyReturnReceipt(this.to_receipt(store, sess, existing)))
      }
      // 若处于 awaiting_confirmation：检查受信任确认通道是否已写入匹配的 approved_digest
      if existing.approved_digest != Some(queue_digest) {
        return Ok(StillAwaitingConfirmation)
      }
      existing.state = "running"
      return Ok(ReadyToDispatch(existing))
    }

    // 2. 逐条核验权限范围、三态策略（allow / confirm / prohibit）、目标级就绪态与冷却期
    needs_confirm = false
    requires_real_money_ui = false
    cooldown_fingerprint = compute_target_fingerprint(q.steps)
    if store.is_in_confirm_cooldown(session_id, cooldown_fingerprint, clock.now_ms()) {
      return Err(G2AError("resource_limit", 429, "Target confirmation is in refusal cooldown"))
    }

    for step in q.steps {
      allowed_actors = sess.scope.permitted_methods.get_or_default(step.method_id, [])
      require step.actor in allowed_actors else G2AError("permission_denied", 403, "Method or actor outside Scope")
      if sess.scope.role_kind == "independent_npc" {
        require step.actor != "player" else G2AError("permission_denied", 403, "NPC cannot target player seat")
      }

      cap_def = store.get_capability_def(sess.scope.slot_id, step.method_id)?
      validate_against_json_schema(step.args, cap_def.params_schema)?
      effective_policy = evaluate_step_policy(sess, cap_def, step, q.trigger)

      // 核心保护规则：
      // (a) 真实法币/外部钱包交易永远强制真人原生安全确认，绝不自动放行；
      // (b) 伴游无指令主动发起 (trigger == "proactive") 却试图触碰玩家主席位 (actor == "player")，
      //     若未禁止则强制升级为 confirm，防止抢夺控制权、乱花资金或擅自提交谜底！
      if "real_money" in cap_def.risk_flags {
        effective_policy = "confirm"
        requires_real_money_ui = true
      } else if q.trigger == "proactive" and step.actor == "player" and effective_policy == "allow" {
        effective_policy = "confirm"
      }

      require effective_policy != "prohibit" else G2AError("permission_denied", 403, "Prohibited by policy")
      if effective_policy == "confirm" { needs_confirm = true }

      // 目标级就绪态校验：首步目标必须当前已 ready；后续步骤目标必须当前处于 ready 或 staged
      step_readiness = resolve_step_readiness(view.methods.get((step.method_id, step.actor)), step.args)
      require step_readiness != None else G2AError("stale_context", 409, "Method or target not currently available",
                                                   fresh_context = Some(this.project_context(store, sess)))
      if step.step_index == 0 {
        require step_readiness == Some("ready") else G2AError("stale_context", 409, "First step target is not ready",
                                                              fresh_context = Some(this.project_context(store, sess)))
      }
    }

    // 3. 持久化入账（即便需要确认也先提交 awaiting_confirmation 记录，保留原 queue_id 不作废！）
    rec = QueueLedgerRecord(
      session_id = session_id, queue_id = q.queue_id, queue_digest = queue_digest, queue = q,
      state = if needs_confirm { "awaiting_confirmation" } else { "running" },
      requires_real_money_ui = requires_real_money_ui,
      approved_digest = None,
      step_receipts = [StepReceipt(s.step_index, s.method_id, s.actor, "pending", None, None) for s in q.steps],
      current_execution_id = None
    )
    store.queues[(session_id, q.queue_id)] = rec

    if needs_confirm {
      return Ok(NeedsConfirmation(rec, cooldown_fingerprint, requires_real_money_ui))
    }
    return Ok(ReadyToDispatch(rec))
  })?

  match decision {
    EarlyReturnReceipt(r) => return Ok(r)
    StillAwaitingConfirmation => return Err(G2AError("confirmation_required", 409, "Still awaiting player confirmation"))
    NeedsConfirmation(rec, fp, real_money_ui) => {
      // 账本已安全落盘后再异步拉起受信任确认框，并返回 409 confirmation_required
      this.spawn_single_queue_confirmation_async(session_id, rec, fp, real_money_ui)
      return Err(G2AError("confirmation_required", 409, "Awaiting single-prompt player confirmation"))
    }
    ReadyToDispatch(rec) => return this.dispatch_queue_steps(session_id, rec.queue_id)
  }
}

// 受信任确认通道异步回调（绝不由中枢接口调用！）
fn HubEngine.on_trusted_confirmation_result(session_id: String, queue_id: String, queue_digest: String,
                                            fingerprint: String, approved: Bool) {
  this.persistence.atomic(session_id, store => {
    rec = store.queues.get((session_id, queue_id))
    if rec == null or rec.state != "awaiting_confirmation" { return Ok() }
    if approved {
      // 写入与步骤参数强绑定的摘要凭证，并通知演算中枢可凭原 queue_id 重提
      rec.approved_digest = Some(queue_digest)
      this.push_stream.push_event(session_id, "queue.confirmed", {"queue_id": queue_id})
    } else {
      // 玩家拒绝或确认超时：作废该队列并在 cooldown_ms 内禁止对同一目标重复弹窗！
      rec.state = "cancelled"
      store.set_confirm_cooldown(session_id, fingerprint, clock.now_ms() + DEFAULT_CONFIRM_COOLDOWN_MS)
      this.push_stream.push_event(session_id, "queue.declined", {
        "queue_id": queue_id, "cooldown_ms": DEFAULT_CONFIRM_COOLDOWN_MS
      })
    }
    return Ok()
  })
}

// 阶段 B：单槽位串行与新指令抢占 + 逐条重验目标级 ready + 算力计量 + 异常立即熔断
fn HubEngine.preempt_or_acquire_slot_queue(session_id: String, queue_id: String) -> Result<Void, G2AError> {
  exec_to_cancel: Option<(String, Int64, String)> = None
  this.persistence.atomic(session_id, store => {
    sess = store.sessions[session_id]
    incoming = store.queues[(session_id, queue_id)]
    if Some(prev_qid) = sess.active_queue_id and prev_qid != queue_id {
      prev = store.queues[(session_id, prev_qid)]
      if prev.state == "running" {
        require incoming.queue.supersedes
          else G2AError("conflict", 409, "Another queue is already running on this slot; set supersedes=true to preempt")
        prev.state = "aborted"
        for sr in prev.step_receipts {
          if sr.state == "pending" { sr.state = "aborted" }
          if sr.state == "executing" { sr.state = "cancelled" }
        }
        if Some(exec_id) = prev.current_execution_id {
          exec_to_cancel = Some((sess.scope.slot_id, store.slot_views[sess.scope.slot_id].epoch, exec_id))
        }
      }
    }
    sess.active_queue_id = Some(queue_id)
    return Ok()
  })?
  if Some((slot_id, epoch, exec_id)) = exec_to_cancel {
    this.origin_client.execute(OriginExecuteRequest(slot_id, epoch, "cancel", exec_id, None, None, {}))
  }
  return Ok()
}

fn HubEngine.wait_until_step_ready_or_abort(session_id: String, queue_id: String, step_index: Int32) -> StepPrepOutcome {
  deadline_ms = clock.now_ms() + (if step_index == 0 { 0 } else { STEP_TRANSITION_GRACE_MS })
  loop {
    check = this.persistence.atomic(session_id, store => {
      sess = store.sessions[session_id]
      rec = store.queues[(session_id, queue_id)]
      view = store.slot_views[sess.scope.slot_id]
      if not sess.player_online or sess.state != "active" or rec.state != "running" or rec.queue.epoch != view.epoch {
        return Ok(AbortStep("session_or_queue_interrupted"))
      }
      if Some(cap) = sess.consumption_cap and sess.consumption_used >= cap {
        return Ok(AbortStep("consumption_cap_reached"))
      }
      step = rec.queue.steps[step_index]
      r = resolve_step_readiness(view.methods.get((step.method_id, step.actor)), step.args)
      if r == Some("ready") {
        exec_id = generate_id("exec")
        rec.current_execution_id = Some(exec_id)
        rec.step_receipts[step_index].state = "executing"
        sess.consumption_used += 1 // 计量已实际调度的受控步骤配额
        return Ok(StepReady(OriginExecuteRequest(
          sess.scope.slot_id, view.epoch, "invoke", exec_id, Some(step.method_id), Some(step.actor), step.args
        )))
      }
      if r == None { return Ok(AbortStep("target_disappeared_or_invalid")) }
      return Ok(WaitNextSync) // 当前仍为 staged（等待前一步引发的增量帧送达）
    }).unwrap()

    match check {
      StepReady(req)    => return StepPrepOutcome(should_abort = false, exec_req = Some(req), reason = "")
      AbortStep(reason) => return StepPrepOutcome(should_abort = true, exec_req = None, reason = reason)
      WaitNextSync      => {
        if clock.now_ms() >= deadline_ms {
          return StepPrepOutcome(should_abort = true, exec_req = None, reason = "prerequisite_did_not_turn_ready")
        }
        this.await_view_update_signal(timeout_ms = 50)
      }
    }
  }
}

fn HubEngine.dispatch_queue_steps(session_id: String, queue_id: String) -> Result<QueueReceipt, G2AError> {
  // 1. 处理同槽位串行与 supersedes 抢占
  this.preempt_or_acquire_slot_queue(session_id, queue_id)?

  for i in 0 .. step_count(session_id, queue_id) {
    // 2. 每下发下一步前重验：玩家仍在线、队列未被取消/抢占，且当前目标级步骤已变为 ready！
    step_prep = this.wait_until_step_ready_or_abort(session_id, queue_id, step_index = i)
    if step_prep.should_abort {
      return Ok(this.abort_remaining_steps(session_id, queue_id, from_index = i, reason = step_prep.reason))
    }

    // 3. 下发单步至交互源点（origin.execute(kind="invoke")）
    exec_reply = this.origin_client.execute(step_prep.exec_req.unwrap())?

    // 4. 若返回持续进行中状态（executing），挂起等待同帧捎带在 origin.sync.settled_executions 中的终态回执或取消信号
    if exec_reply.state == "executing" {
      exec_reply = this.await_step_settlement_or_cancel(session_id, queue_id, exec_reply.execution_id)
    }

    // 5. 记录单步回执；一旦失败或被取消，立即触发熔断（abort），绝不继续下发后续步骤！
    this.record_step_outcome(session_id, queue_id, i, exec_reply)
    if exec_reply.state != "succeeded" {
      return Ok(this.abort_remaining_steps(session_id, queue_id, from_index = i + 1,
                                           reason = exec_reply.failure_reason.unwrap_or("step_not_succeeded")))
    }
  }

  return Ok(this.finalize_completed_queue(session_id, queue_id))
}

// 中枢接口：queue.cancel（中断未完队列及在途 executing 步骤）与 queue.query（超时无副作用对账）
fn HubEngine.handle_queue_cancel(caller: VerifiedPrincipal, session_id: String,
                                 queue_id: String) -> Result<QueueReceipt, G2AError> {
  cancel_target: Option<(String, Int64, String)> = None
  receipt = this.persistence.atomic(session_id, store => {
    sess = store.get_session_for_caller(session_id, caller)?
    rec = store.queues.get((session_id, queue_id))
    require rec != null else G2AError("not_found", 404, "Unknown queue_id")
    if rec.state in ["awaiting_confirmation", "running"] {
      if Some(exec_id) = rec.current_execution_id {
        cancel_target = Some((sess.scope.slot_id, store.slot_views[sess.scope.slot_id].epoch, exec_id))
      }
      rec.state = "cancelled"
      for sr in rec.step_receipts {
        if sr.state in ["pending", "executing"] { sr.state = "cancelled" }
      }
    }
    return Ok(this.to_receipt(store, sess, rec))
  })?
  if Some((slot_id, epoch, exec_id)) = cancel_target {
    this.origin_client.execute(OriginExecuteRequest(slot_id, epoch, "cancel", exec_id, None, None, {}))
  }
  return Ok(receipt)
}

fn HubEngine.handle_queue_query(caller: VerifiedPrincipal, session_id: String,
                                queue_id: String) -> Result<QueueReceipt, G2AError> {
  return this.persistence.atomic(session_id, store => {
    sess = store.get_session_for_caller(session_id, caller)?
    rec = store.queues.get((session_id, queue_id))
    require rec != null else G2AError("not_found", 404, "Unknown queue_id")
    return Ok(this.to_receipt(store, sess, rec))
  })
}
```

---

<a id="section-4"></a>

## 4. 第三层：演算中枢 SDK（Computation Core SDK）伪代码规范

本章面向**自研认知引擎（如 `MotCore`）及第三方智能体服务商**，规定如何零引擎耦合地接入**中枢接口（Core Interface）**，安全处理队列确认重提、网络超时对账与记忆可携导出/导入。

<a id="section-4-1"></a>

### 4.1 模型推理与长期记忆适配端口

```text
interface CognitivePlannerPort {
  // 输入：仅包含静态能力表定义 + 当前投影的活跃方法序号与状态摘要（隔离游戏内不可信文本与系统指令！）
  // 输出：可选回复文本，及可选的有序方法调用队列方案
  fn plan(capabilities: List<CapabilityEntry>, context: ProjectedContext,
          recalled_memories: List<MemoryRecord>) -> PlanDecision
}

interface MemoryStorePort {
  fn recall_safe(player_id: String, current_epoch_guard: SpoilerGuard) -> List<MemoryRecord>
  fn export_all(verified_player_id: String) -> MemoryBundleV1
  fn import_selected(verified_player_id: String, bundle: MemoryBundleV1,
                     selected_ids: List<String>) -> ImportReceiptV1
}
```

---

<a id="section-4-2"></a>

### 4.2 会话接入、心跳与断线重连客户端状态机

```text
class CoreSDK {
  state capability_cache: Map<String, List<CapabilityEntry>> = {} // cap_digest -> 静态能力表缓存
  state actions_paused: Bool = false

  fn connect_and_run(hub_endpoint: String, auth_token: SecretToken, slot_id: String) -> Result<Void, G2AError> {
    validate_outbound_url_against_ssrf(hub_endpoint)? // 强制校验 https:// 协议、主机与端口策略，防 SSRF / DNS 重绑定
    cached_digest = this.last_known_digest_for_slot(slot_id)

    reply = this.https_post(hub_endpoint, "session.authorize", {
      "slot_id": slot_id,
      "requested_scope": this.desired_scope,
      "cached_capability_digest": cached_digest
    }, auth_token)?

    if Some(table) = reply.capability_table {
      this.capability_cache[reply.capability_table_digest] = table
    }
    this.session_id = reply.session_id
    this.start_heartbeat_loop_async()
    this.open_event_stream_with_recovery(hub_endpoint, auth_token)
    return Ok()
  }

  // 网络闪断后的标准恢复流程
  fn on_stream_reconnected() {
    match this.https_post_authed("session.resume", {}) {
      Ok(res) => {
        // 若断线期间已超时或触发本地脚本接管，actions_paused == true，必须静默等待玩家确认事件，严禁擅自发队列！
        this.actions_paused = res.actions_paused
        this.latest_context = res.latest_context
      }
      Err(err) if err.code in ["revoked", "permission_denied"] => {
        this.shutdown_session_cleanly() // 玩家已离线或撤权，立即彻底停止，严禁死循环重连！
      }
      Err(_) => this.backoff_and_retry_resume()
    }
  }

  // 当长时断线或本地脚本接管后，收到玩家在受信任面板批准继续的通知时解除行动暂停
  fn on_event_session_resumed(fresh_ctx: ProjectedContext) {
    this.actions_paused = false
    this.on_context_received(fresh_ctx)
  }
}
```

---

<a id="section-4-3"></a>

### 4.3 感知消费、队列提交、确认重提与超时对账标准流程

**演算中枢**在提交队列后遇到 `409 confirmation_required` 或 `504 outcome_unknown` 时，**必须**严格按以下恢复状态机处理，严禁换新 `queue_id` 绕过或盲目重发副作用：

```text
fn CoreSDK.on_context_received(ctx: ProjectedContext) {
  if this.actions_paused { return }
  caps = this.capability_cache[ctx.capability_table_digest]
  memories = this.memory_port.recall_safe(this.player_id, SpoilerGuard(ctx.epoch))

  decision = this.planner.plan(caps, ctx, memories)
  if Some(chat_msg) = decision.reply_text and this.scope.allow_chat {
    this.https_post_authed("chat.send", {
      "message_id": generate_id("msg"), "audience": decision.audience,
      "text": chat_msg, "provenance": "ai_companion"
    })
  }

  if Some(steps) = decision.planned_steps and not steps.is_empty() {
    queue = MethodCallQueue(
      queue_id = generate_id("Q"),
      epoch = ctx.epoch,
      based_on_rev = ctx.rev,
      trigger = if ctx.player_command != null { "player_command" } else { "proactive" },
      supersedes = (ctx.player_command != null), // 玩家明确下达新指令时，自动抢占旧队列
      intent_summary = decision.intent_summary,
      steps = steps
    )
    this.submit_queue_with_standard_recovery(queue)
  }
}

fn CoreSDK.submit_queue_with_standard_recovery(queue: MethodCallQueue) {
  match this.https_post_authed("queue.submit", queue) {
    Ok(receipt) => {
      this.handle_queue_receipt(receipt)
    }
    Err(err) if err.code == "confirmation_required" => {
      // 保留原 queue 对象不丢弃！挂起等待事件流推来 queue.confirmed 或 queue.declined
      this.pending_confirm_queues[queue.queue_id] = queue
    }
    Err(err) if err.code == "stale_context" => {
      // 世界状态已变：直接使用回包随附的 fresh_context 重新规划（严禁拿旧参数硬重试）
      if Some(fresh) = err.fresh_context { this.on_context_received(fresh) }
    }
    Err(err) if err.code == "outcome_unknown" => {
      // 504 超时铁律：严禁盲目重发 queue.submit 或换新 ID！必须先调 queue.query 核对权威进度
      this.reconcile_unknown_queue(queue.queue_id)
    }
    Err(err) if err.code == "resource_limit" => {
      this.sleep_ms(err.retry_after_ms.unwrap_or(2000))
    }
    Err(_) => { /* invalid_arguments / permission_denied / conflict：停止重试并记录诊断 */ }
  }
}

// 收到智能枢纽受信任通道发来的玩家批准通知后，以完全相同的原 queue（原 queue_id + 原参数）重提！
fn CoreSDK.on_event_queue_confirmed(queue_id: String) {
  if Some(original_queue) = this.pending_confirm_queues.remove(queue_id) {
    this.submit_queue_with_standard_recovery(original_queue)
  }
}

fn CoreSDK.reconcile_unknown_queue(queue_id: String) {
  receipt = this.https_post_authed_with_backoff("queue.query", {"queue_id": queue_id})?
  this.handle_queue_receipt(receipt)
}
```

---

<a id="section-4-4"></a>

### 4.4 伴游记忆开放格式导出与保守导入接口伪代码

```text
struct MemoryRecord {
  memory_id: String,
  created_at_ms: Int64,
  imported_at_ms: Option<Int64>,
  epistemic_source: "game_observed" | "player_stated" | "agent_summary" | "player_edited",
  game_origin_id: Option<String>,
  timeline_tag: Option<String>,    // 防读档回退剧透标签
  pinned_by_player: Bool,          // true 时自主整理任务严禁压缩覆盖或删除！
  max_disclosure_scope: "private_player_only" | "same_game_companion" | "cross_game_companion",
  content: String
}

struct MemoryBundleV1 {
  format: "g2a.memory.bundle.v1",
  exported_at_ms: Int64,
  persona_settings: Map<String, Any>,
  autonomy_preferences: Map<String, PolicyMode>,
  records: List<MemoryRecord>
}

// 源服务商导出：仅校验玩家本人身份，严禁审查或限制导出包的目标去向！
fn MemoryService.export_bundle(player_auth: VerifiedPlayerIdentity) -> MemoryBundleV1 {
  return this.store.export_all(player_auth.player_id)
}

// 接收端服务商导入：保留来源元数据与置顶状态，严禁因迁移而扩大对外披露边界，并返回真实逐条回执
fn MemoryService.import_bundle(player_auth: VerifiedPlayerIdentity, bundle: MemoryBundleV1,
                               selected_ids: List<String>) -> ImportReceiptV1 {
  statuses: Map<String, "imported" | "transformed" | "rejected"> = {}
  for rec in bundle.records {
    if rec.memory_id not in selected_ids { continue }
    rec.imported_at_ms = Some(clock.now_ms())
    // 保守披露收敛：取 源记录上限 与 本地平台默认最严上限 的交集，绝不扩大披露范围
    rec.max_disclosure_scope = min_disclosure(rec.max_disclosure_scope, this.platform_ceiling)
    this.store.upsert_preserving_pins(player_auth.player_id, rec)
    statuses[rec.memory_id] = "imported"
  }
  applied_settings, unsupported_settings = this.apply_supported_persona(player_auth.player_id, bundle)
  return ImportReceiptV1(statuses, applied_settings, unsupported_settings)
}
```

---

<a id="section-5"></a>

## 5. 跨三层端到端联调走查序列

本节使用第 2～4 章定义的真实函数名串联两类代表性游戏场景，供第三方 SDK 与枢纽实现者逐跳对照验证。

<a id="section-5-1"></a>

### 5.1 走查一：具身空间游戏玩家主动指令（寻路 + 直达开箱效果）

```text
[入局阶段]
1. 游戏启动 -> OriginSDK.bind_actor_subject("player", PlayerPawn)
            -> OriginSDK.bind_actor_subject("companion", CompanionPawn)
            -> OriginSDK.register_capability(#01 move_to [sustained=true], NavEffect, ...)
            -> OriginSDK.register_capability(#02 interact [sustained=false], ChestOpenEffect, ...)
            -> 发送 origin.capabilities 缓存至 HubEngine (cap_digest = "sha256:8a1f...")
2. CoreSDK.connect_and_run() -> HubEngine.handle_session_authorize() -> 建立 sess-01 并缓存能力表

[运行期空间差分与玩家指令阶段]
3. OriginSDK.flush_dirty_sync() -> 发送 origin.sync(rev=18, mode="delta"):
     #01 move_to(actor="companion", target="chest_R", player_anchor="right 4m", readiness="ready")
     #02 interact(actor="companion", target="chest_R", readiness="staged")
4. 玩家一边按住 E 键喝药播放动画，一边语音喊：“打开右侧的宝箱”
   -> OriginSDK.report_player_command("打开右侧的宝箱")
   -> HubEngine.project_context(player_command="打开右侧的宝箱")
   -> CorePushStreamPort.push_event("context.push") 直达 CoreSDK（零额外回查！）

[单次推理与逐条调度阶段]
5. CoreSDK.on_context_received() -> 编排并提交 MethodCallQueue(Q-101, trigger="player_command", supersedes=true):
     Step 0: #01 move_to(actor="companion", args={"target_id": "chest_R"})
     Step 1: #02 interact(actor="companion", args={"target_id": "chest_R"})
6. HubEngine.handle_queue_submit(Q-101) -> 核验通过，进入 dispatch_queue_steps:
   • Step 0 下发 OriginSDK.handle_origin_execute(kind="invoke", exec-1, #01) -> 返回 executing（伴游开始寻路）
   • 伴游寻路到位 -> OriginSDK.complete_step(exec-1, succeeded=true)
     -> 在同一个 origin.sync(rev=19) 增量帧内原子上报【#02 chest_R 变为 ready + settled_executions=[exec-1]】
   • Step 1 经 wait_until_step_ready_or_abort 确认 #02(chest_R) 已处于 ready！
     -> 下发 OriginSDK.handle_origin_execute(kind="invoke", exec-2, #02)
     -> 直接调用 ChestOpenEffect(actor="companion")，绕过玩家 E 键互斥锁与按键动画，并行开箱成功！
7. HubEngine 返回 QueueReceipt(Q-101, state="completed", loot=["gold_50", "potion_1"]) -> CoreSDK 调 chat.send 播报收获
```

---

<a id="section-5-2"></a>

### 5.2 走查二：无实体模拟经营信号告警与整队单次确认补货

```text
[入局阶段]
1. 上帝视角经营游戏（无任何角色实体，spatial=null）：
   OriginSDK.bind_actor_subject("companion", BlueprintOverlayController) // 伴游虚影规划层
   OriginSDK.bind_actor_subject("player", WorkshopLedgerController)      // 玩家主账本控制器
   OriginSDK.bind_state_module("workshop", Workshop.snapshot, Workshop.active_methods)

[信号触发与主动队列门禁阶段]
2. 1号木工台木料耗尽 -> 触发 changed 信号 -> OriginSDK.notify_module_changed("workshop", significant_event=true)
   -> 发送 origin.sync(rev=42, significant_event=true):
        #05 trade_resource(actor="player", readiness="ready")
        #06 resume_line(actor="player", target="Bench_1", readiness="staged", alert_tag="halted_no_material")
3. HubEngine 因 significant_event==true 立即唤醒静默节流器，推送 context.push 至 CoreSDK
4. CoreSDK.on_context_received() -> 提交主动队列 Q-205(trigger="proactive"):
     Step 0: #05 trade_resource(actor="player", args={"item": "timber", "qty": 20})
     Step 1: #06 resume_line(actor="player", args={"line_id": "Bench_1"})
5. HubEngine.handle_queue_submit(Q-205):
   • 识别 trigger=="proactive" 且 actor=="player" -> 自动命中 confirm 门禁！
   • 计算 queue_digest = jcs_sha256("g2a.confirm.v1", {sess, "Q-205", steps})
   • 调 TrustedPlayerConsentPort.prompt_queue_confirmation() 向玩家展示合并确认框（仅弹窗一次）
   • 向 CoreSDK 返回 HTTP 409 confirmation_required（Q-205 状态记为 awaiting_confirmation，不作废 ID）
6. 玩家点击“同意” -> HubEngine.on_trusted_confirmation_result(approved=true)
   -> 写入 approved_digest 并向 CoreSDK 推送事件 queue.confirmed("Q-205")
7. CoreSDK.on_event_queue_confirmed("Q-205") -> 凭原 Q-205 原参重提 queue.submit
   -> HubEngine 校验 queue_digest 完全一致 -> 依次执行 #05 购料入库（rev=43 使 #06 变 ready）与 #06 复工！
```

---

<a id="section-5-3"></a>

### 5.3 第三方 SDK 互通自检清单

任何第三方团队完成自定义引擎的**交互源点 SDK** 或自定义语言的**演算中枢 SDK** 后，上线前逐项核对以下 8 条最小互通底线：

| 序号 | 必检项 | 通过判据 |
| --- | --- | --- |
| 01 | **严格 JSON 与 JCS 摘要** | 拒绝 `NaN`/`Infinity`/重复键；相同对象计算出的 `jcs_sha256` 与标准向量逐字节一致。 |
| 02 | **零变化零发包** | 游戏静止或账本无变化时，`OriginSDK` 不产生任何冗余 `origin.sync` 报文。 |
| 03 | **效果层直绑免互斥** | 玩家长按任意动作键播放动画期间，`origin.execute` 仍能并发完成效果结算而不卡死状态机。 |
| 04 | **耗时步骤可取消** | `StartedExecuting` 动作收到 `origin.execute(kind="cancel")` 时能立即停止寻路/蓄力并收敛为 `cancelled`。 |
| 05 | **保密红线裁剪** | 未揭晓谜底、战争迷雾外敌情与牌库未抽牌序在序列化前已被 `OriginSDK` 彻底剔除。 |
| 06 | **确认不烧毁 `queue_id`** | 收到 `409 confirmation_required` 时保留原 `queue_id`，待批准通知到达后原参重提；被拒后遵守 `cooldown_ms`。 |
| 07 | **`504` 超时先对账** | 收到 `504 outcome_unknown` 时先调用 `queue.query`，绝不换新 `queue_id` 盲目重发副作用。 |
| 08 | **离线即停响应** | 玩家离线或返回 `403 revoked` 时立即终止后台轮询与重连循环，零空转消耗。 |
