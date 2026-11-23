# G2A Pseudocode API & Implementation Blueprint

**Game-to-Agent Pseudocode API & Flow Implementation Specification**

A language- and engine-agnostic API contract, host-adapter port definition, and state-machine pseudocode blueprint for cross-engine SDK authors and protocol node implementers.

Version: `V0.0.1` | Release Date: November 23, 2026 | Normative Parent: [G2A Specification (V0.0.1)](G2A_SPECIFICATION.md) | Language Pair: [中文伪代码规范](G2A_PSEUDOCODE_API.zh-CN.md)

## Table of Contents

1. [Implementation Principles, Common Data Contracts, and Core Utilities](#section-1)
   - [1.1 Scope of This Blueprint and Pseudocode Conventions](#section-1-1)
   - [1.2 Unified Message Envelopes, Standard Replies, and Error Enumeration](#section-1-2)
   - [1.3 Core Domain Data Schemas](#section-1-3)
   - [1.4 RFC 8785 (JCS) Canonical Digest Utility Pseudocode](#section-1-4)
2. [Tier 1: Interaction Origin SDK Pseudocode Specification](#section-2)
   - [2.1 Engine & Host Adapter Ports](#section-2-1)
   - [2.2 Game-Developer Integration APIs (Signal-Snapshot Mode + Embodied Spatial-Diff Mode)](#section-2-2)
   - [2.3 Background Dirty-Diff & Mass-Entity Aggregator Pseudocode](#section-2-3)
   - [2.4 Origin Interface Four-Primitive Handler Pseudocode](#section-2-4)
3. [Tier 2: Intelligent Hub Engine Pseudocode Specification](#section-3)
   - [3.1 Hub Persistence Ledger and Trusted Interaction Ports](#section-3-1)
   - [3.2 Session Authorization, Lease Renewal, Two-Tier Reconnect, and Offline-Stop State Machine](#section-3-2)
   - [3.3 State Merger, Active-Method Projection, and Idle-Game Adaptive Throttler](#section-3-3)
   - [3.4 Method Call Queue Scheduler (`QueueScheduler`) Full State-Machine Pseudocode](#section-3-4)
4. [Tier 3: Computation Core SDK Pseudocode Specification](#section-4)
   - [4.1 Cognitive Reasoning and Long-Term Memory Adapter Ports](#section-4-1)
   - [4.2 Session Connection, Heartbeat, and Stream Reconnect Client State Machine](#section-4-2)
   - [4.3 Context Consumption, Queue Submission, Confirmation Resubmission, and Timeout Reconciliation](#section-4-3)
   - [4.4 Open-Format Companion Memory Export and Conservative Import Pseudocode](#section-4-4)
5. [End-to-End Cross-Tier Integration Walkthroughs](#section-5)
   - [5.1 Walkthrough 1: Embodied Spatial Player Command (Pathfinding + Direct Chest-Open Effect)](#section-5-1)
   - [5.2 Walkthrough 2: Avatar-Less Management Signal Alert & Single-Prompt Queue Confirmation](#section-5-2)
   - [5.3 Third-Party SDK Interoperability Self-Check Checklist](#section-5-3)

---

<a id="section-1"></a>

## 1. Implementation Principles, Common Data Contracts, and Core Utilities

<a id="section-1-1"></a>

### 1.1 Scope of This Blueprint and Pseudocode Conventions

This document is the companion engineering implementation blueprint to [G2A Specification (V0.0.1)](G2A_SPECIFICATION.md). It guides both official reference implementations and third-party engine or platform teams (Godot / GDScript, Unity / C#, Unreal / C++, Rust, Python, TypeScript, Go, etc.) in building **100% wire-interoperable** SDKs and protocol nodes:

- **Normative & Wire-Relevant (MUST match across implementations):** JSON property names, closed enum string literals, RFC 8785 digest input structures, authorization and policy evaluation order, idempotency deduplication keys, standard error-code mappings, and failure-abort / offline-stop ordering.
- **Implementation-Agnostic (free to tailor per host):** In-memory data layouts, concurrency primitives (coroutines, mutexes, actor mailboxes), engine scene-tree or ECS attachment patterns, storage engines (SQLite, embedded KV, clustered backend stores), and local IPC transport internals.

This blueprint uses a neutral strongly typed pseudocode notation mapped to host languages as follows:

| Pseudocode Notation | Normative Meaning | Typical Host-Language Mapping |
| --- | --- | --- |
| `struct` / `enum` | Plain data record or closed string enum serialized as RFC 8259 UTF-8 JSON | C# `record/class`, C++ `struct`, GDScript `Dictionary/Resource`, Rust `struct/enum`, TS `interface` |
| `interface XXXPort` | Host-injected **adapter port** provided by the game engine, OS, or runtime infrastructure | Interface / Trait / Pure virtual class / Callback table |
| `Option<T>` | Optional value (`null` or omitted in JSON; omitting empty optional keys is recommended) | `T?` / `std::optional<T>` / `Option<T>` / `null` |
| `Result<T, G2AError>` | Explicit success value or typed `G2AError`; never swallow failures as silent success | Result tuple, exception-to-error boundary, or `Result<T, E>` |
| `require COND else ERR` | Guard assertion; immediately aborts uncommitted mutations and returns standard `ERR` | Guard clause / early return |
| `atomic(scope_key) { ... }` | Commits state mutations atomically under `scope_key` in the durable ledger; rolls back on error | Mutex + write-ahead log / database transaction |

---

<a id="section-1-2"></a>

### 1.2 Unified Message Envelopes, Standard Replies, and Error Enumeration

Every cross-tier request, response, and real-time push frame is wrapped in a unified top-level envelope (the wire version string literal is `"0.0.1"`, corresponding to specification baseline `V0.0.1`):

```text
const G2A_WIRE_VERSION = "0.0.1"

enum AcceptanceState {
  "accepted",      // HTTP 200: Request accepted (including partial queue execution followed by abort; inspect step receipts)
  "not_accepted",  // HTTP 4xx / 503: Rejected or held for confirmation before causing new domain side effects
  "unknown"        // HTTP 504: Outcome indeterminate; caller MUST reconcile via queue.query before retrying
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
  g2a_version: String,          // Required; baseline literal is "0.0.1"
  request_id: String,           // Required; caller-generated per-request correlation ID (UUID / ULID)
  session_id: Option<String>,   // Required on all calls except session.authorize and initial Origin registration
  timestamp_ms: Int64,          // Sender Unix timestamp in milliseconds
  operation: String,            // e.g. "origin.sync" / "queue.submit"
  payload: TPayload,
  extensions: Map<String, Any>  // Optional reverse-DNS extension map; defaults to {}
}

struct ReplyEnvelope<TResult> {
  g2a_version: String,
  request_id: String,           // Echoes the corresponding RequestEnvelope.request_id verbatim
  session_id: Option<String>,
  timestamp_ms: Int64,
  acceptance: AcceptanceState,
  result: Option<TResult>,      // Present when acceptance == "accepted"
  error: Option<G2AError>       // Present when acceptance != "accepted"
}

struct EventEnvelope<TEvent> {
  g2a_version: String,
  event_id: String,             // Unique push event ID for receiver idempotency deduplication
  session_id: String,
  timestamp_ms: Int64,
  event: String,                // e.g. "context.push" / "queue.confirmed" / "session.resumed" / "session.closed"
  payload: TEvent
}

struct G2AError {
  code: ErrorCode,
  http_status: Int32,
  message: String,              // Safe diagnostic/UI text; MUST NOT leak unauthorized hidden entities or puzzle solutions
  retry_after_ms: Option<Int64>,
  cooldown_ms: Option<Int64>,   // Refusal/timeout cooldown duration for confirmation_required
  fresh_context: Option<ProjectedContext> // Attached on stale_context so the Core can replan immediately
}
```

Standard wire JSON examples for a queue submission request and a single-prompt confirmation hold reply:

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
    "intent_summary": "Buy 20 timber and resume production on Bench 1",
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

### 1.3 Core Domain Data Schemas

The following schemas share identical semantics across **Interaction Origin**, **Intelligent Hub**, and **Computation Core**:

```text
// Slot role kind and billing ownership
enum RoleKind { "companion", "independent_npc" }
enum BillingMode { "player_metered", "developer_sponsored" }

// Execution subject identifier: "companion" (AI's own body or non-intrusive helper layer) or "player" (authorized player body or primary seat)
// Under an independent_npc slot, only its own npc_id is permitted ("player" MUST NEVER be exposed)
type ActorId = String

// Universal rule-precondition readiness
enum Readiness {
  "ready",   // All preconditions satisfied right now; immediately executable as a single step
  "staged"   // Legitimately visible now; unlocks into "ready" once preceding steps in the same queue succeed
}

// Per-step execution lifecycle state
enum StepState {
  "pending",     // Queued in Hub, not yet dispatched to Interaction Origin
  "executing",   // Sustained action running in Interaction Origin (pathfinding/charging/holding plate); interruptible via cancel
  "succeeded",   // Domain effect authoritatively applied in Interaction Origin
  "failed",      // Rejected by domain rules or obstructed mid-execution
  "cancelled",   // Cancelled before or during executing due to preemption, revocation, or player stop
  "aborted"      // Skipped by Intelligent Hub circuit-breaker after an earlier step failed or was cancelled (never sent to Origin)
}

// 1. Static capability entry (synced on entry, cached by Intelligent Hub and Computation Core)
struct CapabilityEntry {
  method_id: String,               // Stable short identifier, e.g. "#01", "#02"
  name: String,                    // Universal domain verb, e.g. "move_to", "interact", "craft", "mark_board"
  description: String,             // Concise semantic summary for reasoning engines
  permitted_actors: List<ActorId>, // Subjects eligible for this verb, e.g. ["companion"] or ["companion", "player"]
  params_schema: JsonSchema,       // Standard JSON Schema (supports target_id, passcodes, sliders, grid coords, recipe arrays)
  sustained: Bool,                 // false = instantaneous effect; true = may enter sustained "executing" state
  risk_flags: List<String>,        // e.g. ["economy_spend", "irreversible", "real_money"]
  default_policy: PolicyMode       // Origin-recommended baseline gate: "allow" | "confirm" | "prohibit"
}

enum PolicyMode { "allow", "confirm", "prohibit" }

// 2. Context anchors (supporting embodied dual-perspective space, XR pointing rays, and avatar-less board focus)
struct TargetCandidate {
  target_id: String,               // e.g. "chest_R", "Bench_1", "clue_C3"
  label: String,                   // Display label (untrusted in-game text; MUST NOT be interpolated into control instructions)
  readiness: Readiness,            // Readiness relative to this specific actor: "ready" | "staged"
  prerequisite_hint: Option<String>, // e.g. "requires_proximity" / "requires_resource:timber"
  actor_anchor: Option<String>,    // Anchor relative to execution subject, e.g. "1.0m ahead"
  player_anchor: Option<String>,   // Anchor relative to player bearing/gaze/VR ray/hover/selected zone, e.g. "right 4m" / "pointed_ray"
  alert_tag: Option<String>        // Aggregated anomaly tag for large-scale sim/strategy games, e.g. "halted_no_material"
}

struct ActiveMethodGrant {
  method_id: String,               // References CapabilityEntry.method_id without retransmitting its JSON Schema
  actor: ActorId,                  // Explicitly identifies which subject/seat this grant applies to
  readiness: Readiness,            // Direct readiness for target-less parameterized verbs
  targets: List<TargetCandidate>   // Aggregated candidate targets (alerts & focus only in large games; never dump silent entities)
}

struct MethodActorKey {
  method_id: String,
  actor: ActorId
}

// 3. Dynamic sync frame (Origin -> Hub supports full / delta and atomically piggybacks settled sustained-step receipts)
struct OriginSyncFrame {
  slot_id: String,                 // Associated character/companion slot ID
  epoch: Int64,                    // World epoch (increments on save reload, map change, or match reset; invalidates older epochs)
  rev: Int64,                      // Strictly monotonic state revision within the same epoch
  base_rev: Option<Int64>,         // Required when mode == "delta"; MUST equal the Hub's current rev
  mode: "full" | "delta",
  significant_event: Bool,         // True when crossing a notable domain threshold (wakes idle-game adaptive sleep)
  state_brief: Map<String, Any>,   // Compact state brief (HP/turn/ledger snapshot/unlocked clues; NEVER hidden secrets or answers)
  upserted_methods: List<ActiveMethodGrant>, // Full grant set when mode == "full"; added/changed grants when "delta"
  removed_methods: List<MethodActorKey>,     // Removed {method_id, actor} keys when mode == "delta"
  settled_executions: List<OriginExecuteReply> // Terminal receipts for sustained executing steps delivered atomically in the same frame
}

// 4. Compact context projected to Computation Core (Hub -> Core)
struct ProjectedContext {
  slot_id: String,
  epoch: Int64,
  rev: Int64,
  capability_table_digest: String, // Verifies static capability-table cache consistency
  player_command: Option<String>,  // Attached directly when triggered by an active player command
  state_brief: Map<String, Any>,
  active_methods: List<ActiveMethodGrant>, // Filtered to currently "ready" / "staged" grants within FrozenScope
  visual_ref: Option<MediaFrameRef>,       // Present only when orthogonal visual module is enabled by player
  audio_ref: Option<MediaFrameRef>         // Present only when orthogonal audio module is enabled by player
}

// 5. Method Call Queue and execution receipts
struct QueueStep {
  step_index: Int32,
  method_id: String,
  actor: ActorId,
  args: Map<String, Any>
}

struct MethodCallQueue {
  queue_id: String,                // Idempotency key generated by Computation Core
  epoch: Int64,
  based_on_rev: Int64,
  trigger: "player_command" | "proactive",
  supersedes: Bool,                // When true, preempts and cancels any currently running queue on the same slot
  intent_summary: String,          // Concise human-readable summary shown in the single-prompt confirmation UI
  steps: List<QueueStep>           // 1..N ordered steps (a single action is a 1-step queue)
}

struct StepReceipt {
  step_index: Int32,
  method_id: String,
  actor: ActorId,
  state: StepState,
  effect_summary: Option<Map<String, Any>>, // e.g. {"loot": ["gold_50", "potion_1"]}
  failure_reason: Option<String>
}

struct QueueReceipt {
  queue_id: String,
  queue_state: "awaiting_confirmation" | "running" | "completed" | "aborted" | "cancelled",
  step_receipts: List<StepReceipt>,
  latest_context: Option<ProjectedContext>  // Attached on completion or abort to save an extra pull round-trip
}

// 6. Frozen authorization scope (Scope)
struct FrozenScope {
  player_id: String,
  core_id: String,
  game_instance_id: String,
  slot_id: String,
  role_kind: RoleKind,
  billing_mode: BillingMode,
  permitted_methods: Map<String, List<ActorId>>, // method_id -> authorized actor set
  capability_table_digest: String,
  allow_visual: Bool,
  allow_audio: Bool,
  allow_chat: Bool
}
```

---

<a id="section-1-4"></a>

### 1.4 RFC 8785 (JCS) Canonical Digest Utility Pseudocode

Static capability-table cache verification, frozen `Scope` binding, and tamper-evident single-prompt queue confirmation tokens **MUST** all share the following domain-separated canonical digest helper:

```text
fn validate_strict_json_value(val: Any) -> Result<Void, G2AError> {
  // Recursive check: reject NaN, +Infinity, -Infinity, and duplicate object keys; allow integers and finite IEEE-754 floats
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
  // Domain-separation prefix prevents cross-type digest collisions: "g2a.cap.v1\0" / "g2a.scope.v1\0" / "g2a.confirm.v1\0"
  digest_hex: String = sha256_hex(utf8_bytes(domain_tag + "\0") + canonical_utf8)
  return Ok("sha256:" + digest_hex)
}
```

---

<a id="section-2"></a>

## 2. Tier 1: Interaction Origin SDK Pseudocode Specification

This chapter targets **engine SDK authors** and **game gameplay programmers**, demonstrating how a thin SDK layer supports both entity-less signal-snapshot games and embodied spatial roaming games while cleanly decoupling physical input/animation wrappers from authoritative domain effects.

<a id="section-2-1"></a>

### 2.1 Engine & Host Adapter Ports

To build a native G2A Origin SDK for any engine (Godot, Unity, Unreal, or custom C++), an engine adapter only needs to implement three lightweight ports:

```text
// Return type of a domain effect callback: immediate terminal state, or an interruptible sustained handle
enum EffectInvocationResult {
  ImmediateSucceeded(effect_summary: Map<String, Any>),
  ImmediateFailed(reason: String),
  StartedExecuting(cancel_fn: Fn() -> Void) // Sustained action started; engine calls OriginSDK.complete_step(...) upon settlement
}

interface EngineDispatcherPort {
  // Marshals effect execution onto the authoritative game-logic main thread (e.g. Godot call_deferred / Unity MainThreadQueue)
  fn run_on_game_thread<T>(task: Fn() -> T) -> T
}

interface SpatialAdapterPort {
  // Implemented ONLY by embodied spatial / XR games; pure board, strategy, management, or deduction games pass NullSpatialAdapter
  fn get_actor_pose(actor: ActorId) -> Option<Pose3D>
  fn get_player_focus() -> PlayerFocusInfo // Player position, forward vector, gaze, VR controller pointing ray, or cursor hover target
  fn query_nearby_interactables(origin: Pose3D, perception_radius: Float) -> List<InteractableRef>
}

interface HubTransportClientPort {
  // Standalone: loopback HTTP / Named Pipe / Unix Domain Socket; Online multiplayer: isolated backend HTTP/2 or mTLS
  fn post_to_hub<TReq, TRes>(operation: String, payload: TReq) -> Result<TRes, G2AError>
}
```

---

<a id="section-2-2"></a>

### 2.2 Game-Developer Integration APIs (Signal-Snapshot Mode + Embodied Spatial-Diff Mode)

Gameplay code interacts solely with declarative `OriginSDK` registration methods — **without writing networking glue, manual JSON serialization, or per-method `if (actor == "player")` branches**:

```text
// Domain effect callback signature: bind directly to authoritative gameplay settlement functions
// (NEVER bind to physical hotkey wrappers blocked by single-key mutexes or hand-animation windups!)
type DomainEffectHandler = Fn(
  actor: ActorId,
  subject_instance: Any,          // Automatically routed by SDK to the companion pawn, helper overlay, or primary player controller
  args: Map<String, Any>,
  step_token: StepExecutionToken  // Retained by sustained actions to call complete_step when finished
) -> EffectInvocationResult

class OriginSDK {
  state capabilities: Map<String, RegisteredCapability> = {}
  state actors: Map<ActorId, Any> = {}               // "player" -> PlayerController/Pawn; "companion" -> CompanionPawn or HelperOverlay
  state signal_modules: Map<String, SignalModule> = {} // Signal-driven state modules (strategy/management/card/deduction)
  state in_flight_steps: Map<String, ActiveStepCtx> = {}
  state current_epoch: Int64 = 1
  state current_rev: Int64 = 0
  state last_sent_methods: Map<(String, ActorId), ActiveMethodGrant> = {}
  state last_sent_brief_digest: String = ""
  state pending_settled_executions: List<OriginExecuteReply> = []

  // [Integration API 1] Register universal domain primitives on entry (e.g. #01 move_to, #02 interact, #04 toggle_flashlight, #05 trade_resource)
  fn register_capability(def: CapabilityEntry, effect_handler: DomainEffectHandler,
                         readiness_check: Option<Fn(ActorId, Any) -> Option<Readiness>>) {
    // Hard safety rule: automatically strip "player" subject from independent_npc slots at registration time
    if this.slot_role_kind == "independent_npc" {
      def.permitted_actors = def.permitted_actors.filter(a => a != "player")
    }
    this.capabilities[def.method_id] = RegisteredCapability(def, effect_handler, readiness_check)
  }

  // Call once after registering entry primitives (or unlocking a new chapter system) to publish the capability table and initial full frame
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

  // [Integration API 2] Bind an execution subject or seat controller (one call per embodied pawn or avatar-less seat controller)
  fn bind_actor_subject(actor: ActorId, instance: Any) {
    this.actors[actor] = instance
  }

  // [Integration API 3A · Strategy / Management / Card / Deduction] Bind a signal-snapshot state module (zero spatial coordinates)
  // Example: wire wallet, crafting bench, day clock, or clue board modules; call notify_module_changed whenever their `changed` signal fires
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

  // [Integration API 4] Advance world epoch on save reload, map transition, round reset, or faction switch
  fn advance_epoch() {
    this.current_epoch += 1
    this.current_rev = 0
    this.last_sent_methods.clear()
    this.cancel_all_in_flight_steps("epoch_advanced")
    this.flush_full_sync()
  }

  // [Integration API 5] Report authoritative player-seat events (invoked by native game input & presence lifecycle)
  fn report_player_command(command_text: String) {
    this.flush_dirty_sync(significant_event = true) // Ensure latest world state reaches Hub before the command event
    this.hub_transport.post_to_hub("origin.player_event", {
      "slot_id": this.slot_id, "kind": "player_command", "text": command_text
    })
  }

  fn report_player_presence(online: Bool, remaining_online_humans_in_room: Int32 = 0) {
    if not online and remaining_online_humans_in_room == 0 {
      // When the associated player disconnects and zero human players remain in the match, halt state collection
      // (any final step already executing in Origin settles naturally under game rules)
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

  // Report verified in-game player-seat approval for non-real-money queues (e.g. fullscreen console/gamepad/VR HUD approval panel)
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

### 2.3 Background Dirty-Diff & Mass-Entity Aggregator Pseudocode

Whether a game uses signal snapshots, spatial scanning, or a hybrid of both (such as embodied farming/life sims), `OriginSDK` funnels updates through a unified dirty-diff pipeline (**emitting zero network packets whenever state and active methods are unchanged**):

```text
const MAX_CANDIDATE_TARGETS_PER_METHOD = 24 // Prevents large management/strategy games from dumping thousands of silent buildings

// Merges candidate targets for the same (method_id, actor) across signal modules and spatial scanners without overwriting
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

  // 1. Collect signal-driven module snapshots & grants (management ledgers, card hands, unlocked clues; NEVER unrevealed answers!)
  for (mod_name, mod) in this.signal_modules {
    brief[mod_name] = mod.snapshot_fn()
    for g in mod.active_methods_fn() {
      merge_method_grant(grants, g)
    }
  }

  // 2. Collect embodied equipment & spatial perception (when SpatialAdapterPort is provided)
  if this.spatial != null {
    player_focus = this.spatial.get_player_focus()
    for (method_id, reg) in this.capabilities {
      for actor in reg.def.permitted_actors {
        if actor not in this.actors { continue } // Disembodied companions lack a physical pawn; automatically skipped!
        subject = this.actors[actor]

        // 2a. Non-target equipment verbs (e.g. #04 toggle_flashlight checks each actor's own equipment independently)
        if reg.readiness_check != null {
          if Some(r) = reg.readiness_check(actor, subject) {
            merge_method_grant(grants, ActiveMethodGrant(method_id, actor, r, targets = []))
          }
        }

        // 2b. Spatial target verbs (reachability measured from THIS actor's pose, paired with player-relative deictic anchors!)
        if reg.is_spatial_target_verb and Some(actor_pose) = this.spatial.get_actor_pose(actor) {
          candidates: List<TargetCandidate> = []
          for obj in this.spatial.query_nearby_interactables(actor_pose, this.perception_radius) {
            if obj.is_hidden_secret_unrevealed() { continue } // Never leak unrevealed secret doors or hidden chests
            dist_to_actor = distance(actor_pose, obj.pose)
            readiness = if dist_to_actor <= obj.interact_range { "ready" } else { "staged" }
            candidates.append(TargetCandidate(
              target_id = obj.id,
              label = obj.display_name,
              readiness = readiness,
              prerequisite_hint = if readiness == "staged" { Some("requires_proximity") } else { None },
              actor_anchor = format_distance_bearing(actor_pose, obj.pose),
              player_anchor = compute_player_deictic_label(player_focus, obj), // e.g. "right 4m" / "pointed_ray"
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

  // Zero-change zero-packet rule!
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

### 2.4 Origin Interface Four-Primitive Handler Pseudocode

When the **Intelligent Hub** sends `origin.execute` to the **Interaction Origin**, `OriginSDK` invokes the bound domain effect directly on the game-logic thread and manages asynchronous settlement and mid-flight cancellation for sustained steps:

```text
struct OriginExecuteRequest {
  slot_id: String,
  epoch: Int64,
  kind: "invoke" | "cancel" | "deliver_chat", // Unified under the single origin.execute primitive without private side-channels
  execution_id: String,                       // Unique execution/delivery ticket ID generated by Intelligent Hub
  method_id: Option<String>,                  // Required when kind == "invoke"
  actor: Option<ActorId>,                     // Required when kind == "invoke"
  args: Map<String, Any>                      // Method args for "invoke"; audience/text/ai_provenance for "deliver_chat"
}

struct OriginExecuteReply {
  execution_id: String,
  state: "executing" | "succeeded" | "failed" | "cancelled",
  effect_summary: Option<Map<String, Any>>,
  failure_reason: Option<String>
}

// Handles Hub -> Origin calls (accepted ONLY over authenticated local IPC/loopback or isolated backend network, honoring the 4-primitive Origin Interface)
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

  // kind == "invoke": 1. Idempotency guard
  if req.execution_id in this.execution_ledger {
    return Ok(this.execution_ledger[req.execution_id])
  }

  return this.engine_dispatcher.run_on_game_thread(() => {
    method_id = req.method_id.unwrap()
    actor = req.actor.unwrap()
    // 2. Verify world epoch, method registration, and subject eligibility
    require req.epoch == this.current_epoch else G2AError("stale_context", 409, "Epoch mismatch")
    require method_id in this.capabilities else G2AError("invalid_arguments", 400, "Unknown method_id")
    reg = this.capabilities[method_id]
    require actor in reg.def.permitted_actors else G2AError("permission_denied", 403, "Actor not permitted")
    require actor in this.actors else G2AError("not_found", 404, "Actor subject not present")
    validate_against_json_schema(req.args, reg.def.params_schema)?

    subject_instance = this.actors[actor]
    token = StepExecutionToken(req.execution_id)

    // 3. Bypass physical hotkey mutexes and player hand-animation windups — invoke domain effect directly!
    match reg.effect_handler(actor, subject_instance, req.args, token) {
      ImmediateSucceeded(summary) => {
        reply = OriginExecuteReply(req.execution_id, "succeeded", Some(summary), None)
        this.execution_ledger[req.execution_id] = reply
        this.flush_dirty_sync(significant_event = false) // Immediately sync newly unlocked ready methods (e.g. #06 turning ready)
        return Ok(reply)
      }
      ImmediateFailed(reason) => {
        reply = OriginExecuteReply(req.execution_id, "failed", None, Some(reason))
        this.execution_ledger[req.execution_id] = reply
        this.flush_dirty_sync(significant_event = false)
        return Ok(reply)
      }
      StartedExecuting(cancel_fn) => {
        // Sustained action (e.g. 5m pathfinding, 5s warp charge, holding a co-op pressure plate): return "executing" without blocking frame tick
        this.in_flight_steps[req.execution_id] = ActiveStepCtx(cancel_fn)
        reply = OriginExecuteReply(req.execution_id, "executing", None, None)
        this.execution_ledger[req.execution_id] = reply
        return Ok(reply)
      }
    }
  })
}

// Invoked by engine async callbacks (e.g. NavigationAgent target_reached or charge timer completion)
fn OriginSDK.complete_step(execution_id: String, succeeded: Bool,
                           summary: Option<Map<String, Any>>, reason: Option<String>) {
  this.engine_dispatcher.run_on_game_thread(() => {
    if execution_id not in this.in_flight_steps { return } // Ignore late callback if already cancelled
    this.in_flight_steps.remove(execution_id)
    final_state = if succeeded { "succeeded" } else { "failed" }
    reply = OriginExecuteReply(execution_id, final_state, summary, reason)
    this.execution_ledger[execution_id] = reply
    // Queue receipt to ride atomically in the SAME origin.sync delta frame as the updated ready grants, eliminating ordering races!
    this.pending_settled_executions.append(reply)
  })
  this.flush_dirty_sync(significant_event = false)
}

fn OriginSDK.cancel_in_flight_step(execution_id: String) -> OriginExecuteReply {
  return this.engine_dispatcher.run_on_game_thread(() => {
    if execution_id in this.in_flight_steps {
      ctx = this.in_flight_steps.remove(execution_id)
      ctx.cancel_fn() // Immediately halt pathfinding or abort engine charge-up
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

## 3. Tier 2: Intelligent Hub Engine Pseudocode Specification

The **Intelligent Hub** serves as the security shield and state-machine coordinator of the protocol (installed once per PC across standalone games, or deployed in a backend cluster for server-authoritative online games). This chapter specifies its session lifecycle, view projection, and `QueueScheduler` state machine.

<a id="section-3-1"></a>

### 3.1 Hub Persistence Ledger and Trusted Interaction Ports

```text
interface HubPersistencePort {
  // Provides atomic read-modify-write transactions isolated per slot_id / session_id (preserving dedup ledgers & revocations across restarts)
  fn atomic<T>(lock_key: String, tx: Fn(HubStore) -> Result<T, G2AError>) -> Result<T, G2AError>
}

interface TrustedPlayerConsentPort {
  // Exclusive trusted player consent & single-prompt queue confirmation channel (native Hub security UI or verified in-game approval panel)
  // MUST NEVER be exposed on the Core Interface facing Computation Cores!
  fn prompt_session_scope(scope: FrozenScope) -> AsyncDecision<Bool>
  fn prompt_session_resume(session_id: String) -> AsyncDecision<Bool>
  fn prompt_queue_confirmation(session_id: String, queue_id: String, queue_digest: String,
                               intent_summary: String, steps_preview: List<StepPreview>,
                               require_native_real_money_ui: Bool) -> AsyncDecision<Bool>
}

interface OriginClientPort {
  // Dispatches the sole Hub -> Origin primitive "origin.execute" (covering invoke / cancel / deliver_chat) over the Origin Interface
  fn execute(req: OriginExecuteRequest) -> Result<OriginExecuteReply, G2AError>
}

interface CorePushStreamPort {
  // Pushes real-time EventEnvelope frames over the authenticated SSE / WebSocket stream to a Computation Core
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
  requires_real_money_ui: Bool,    // When true, ONLY native OS/platform security UI is accepted; ordinary in-game panels are rejected
  approved_digest: Option<String>, // Written only after player approval via a trusted channel
  step_receipts: List<StepReceipt>,
  current_execution_id: Option<String>
}
```

---

<a id="section-3-2"></a>

### 3.2 Session Authorization, Lease Renewal, Two-Tier Reconnect, and Offline-Stop State Machine

```text
// 1. Core Interface: session.authorize
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

  // Enforce FRAND anti-cheat / compliance allowlist if configured on this slot
  if slot.allowlist_enabled {
    require slot.is_allowed_core(caller_principal.core_id) else G2AError("permission_denied", 403, "Core not allowlisted")
  }

  // Compute capability digest and narrowed FrozenScope (Support != Authorization: intersect requested scope with Origin table)
  cap_digest = slot.capability_table_digest
  narrowed_scope = intersect_with_origin_capabilities(req.requested_scope, slot, caller_principal.core_id, cap_digest)
  scope_digest = jcs_sha256("g2a.scope.v1", narrowed_scope)?

  // Obtain approval via trusted player channel (unless matched by an unexpired player-configured auto-join rule for the exact scope_digest)
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
    // Skip retransmitting the full static capability table when the Computation Core already caches the matching cap_digest
    table_to_send = if req.cached_capability_digest == Some(cap_digest) { None } else { Some(slot.capabilities) }
    return Ok(AuthorizeReply(session_id, scope_digest, cap_digest, table_to_send))
  })
}

// 2. Mandatory player-offline stop rule (triggered by origin.player_event(presence_changed))
fn HubEngine.on_player_presence_changed(slot_id: String, online: Bool, remaining_online_humans: Int32) {
  this.persistence.atomic(slot_id, store => {
    slot = store.slots[slot_id]
    slot.player_online = online
    // Rule A: When zero human players remain in the match (remaining_online_humans == 0), ALL slots — including developer_sponsored NPCs — stop immediately!
    // Rule B: When the associated player disconnects, personal companions and player_metered NPCs immediately stop billing and clear undispatched queues!
    if not online {
      for sess in store.sessions_for_slot(slot_id) {
        sess.player_online = false
        should_stop = (remaining_online_humans == 0)
                      or (sess.scope.role_kind == "companion")
                      or (sess.scope.billing_mode == "player_metered")
        if should_stop {
          // Clear all undispatched pending steps; any final step already executing in Origin settles naturally under game rules
          this.clear_undispatched_queues_in_tx(store, sess, reason = "player_offline")
          sess.state = "closed"
          this.push_stream.push_event(sess.session_id, "session.closed", {"reason": "player_offline"})
        }
      }
    }
    return Ok()
  })
}

// 3. Two-tier transient disconnect recovery during active play (session.resume & trusted player resume callback)
fn HubEngine.handle_session_resume(caller: VerifiedPrincipal, session_id: String) -> Result<ResumeReply, G2AError> {
  need_prompt = false
  reply = this.persistence.atomic(session_id, store => {
    sess = store.get_session_for_caller(session_id, caller)?
    require sess.player_online and sess.state != "closed" else G2AError("revoked", 403, "Session closed")

    if clock.now_ms() < sess.lease_deadline_ms and not sess.local_fallback_activated {
      // Tier 1: Within active lease and local fallback has not taken over -> seamless resume!
      sess.state = "active"
      sess.lease_deadline_ms = clock.now_ms() + LEASE_TTL_MS
      return Ok(ResumeReply(actions_paused = false, latest_context = this.project_context(store, sess)))
    } else {
      // Tier 2: Lease expired or local fallback took over -> keep actions paused until human player confirms resume (zero offline backfill)
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

// 4. Core Interface: session.heartbeat (renews control lease; MUST NOT extend an offline player's presence!) & session.close (idempotent)
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
    return Ok() // Idempotent success on repeated close
  })?
  for (slot_id, epoch, exec_id) in execs_to_cancel {
    this.origin_client.execute(OriginExecuteRequest(slot_id, epoch, "cancel", exec_id, None, None, {}))
  }
  return Ok()
}

// 5. Origin Interface: origin.capabilities & origin.player_event handlers
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
      // Zero Origin callback needed: bundle [player command + latest active methods] straight to Computation Core!
      return this.persistence.atomic(ev.slot_id, store => {
        for sess in store.active_sessions_for_slot(ev.slot_id) {
          ctx = this.project_context(store, sess, player_command = Some(ev.text))
          this.push_stream.push_event(sess.session_id, "context.push", ctx)
        }
        return Ok()
      })
    }
    "queue_approval" => {
      // Verified in-game player-seat queue approval (permitted ONLY for ordinary gameplay queues; real_money requires native platform security UI)
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

### 3.3 State Merger, Active-Method Projection, and Idle-Game Adaptive Throttler

```text
fn HubEngine.handle_origin_sync(frame: OriginSyncFrame) -> Result<Void, G2AError> {
  return this.persistence.atomic(frame.slot_id, store => {
    view = store.slot_views[frame.slot_id]

    // Epoch transition or full baseline frame: atomically replace view and abort obsolete-epoch queues
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

    // Atomically consume settled sustained-step receipts in the same frame and wake waiting QueueScheduler workers
    for settled in frame.settled_executions {
      this.notify_execution_waiter_in_tx(store, settled)
    }
    this.notify_view_updated_waiters(frame.slot_id)

    // Adaptive quiet-period sleep throttling (for desktop idle games, virtual pets, and slow-paced management sims):
    // Push proactively ONLY when significant_event == true; otherwise exponentially back off idle polling intervals
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

// Filters to FrozenScope and projects ONLY currently active ("ready" / "staged") method IDs to keep reasoning context compact
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

// Core Interface: context.pull (with adaptive idle sleep enforcement) & chat.send (with audience & AI provenance enforcement)
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
    // Force verified AI provenance tag and dispatch via unified origin.execute(kind="deliver_chat") outside the persistence lock
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

### 3.4 Method Call Queue Scheduler (`QueueScheduler`) Full State-Machine Pseudocode

This section specifies the core control logic of the **Intelligent Hub**, covering **idempotent deduplication → command preemption → tri-state policy & `actor = player` control-hijack protection → digest-bound single-prompt confirmation & refusal cooldown → per-step target-level `ready` revalidation & failure abort**:

```text
// Resolves target-level readiness for a specific step (prevents mistaking a distant "staged" chest for a nearby "ready" chest on the same method_id)
fn resolve_step_readiness(grant: Option<ActiveMethodGrant>, args: Map<String, Any>) -> Option<Readiness> {
  if grant == null { return None }
  g = grant.unwrap()
  if g.targets.is_empty() { return Some(g.readiness) } // Target-less parameterized verb (e.g. toggle_flashlight, enter passcode)
  if Some(tid) = args.get("target_id") {
    for cand in g.targets {
      if cand.target_id == tid { return Some(cand.readiness) }
    }
    return None // Requested target_id is absent from the authorized visible candidate set (e.g. hidden or despawned object)
  }
  return Some(g.readiness)
}

fn HubEngine.handle_queue_submit(caller: VerifiedPrincipal, session_id: String,
                                 q: MethodCallQueue) -> Result<QueueReceipt, G2AError> {
  queue_digest = jcs_sha256("g2a.confirm.v1", {
    "session_id": session_id, "queue_id": q.queue_id, "steps": q.steps
  })?

  // Phase A: Authenticate, deduplicate, evaluate policy, and record ledger entry inside atomic transaction.
  // Critical transaction rule: when confirmation is needed, return Ok(NeedsConfirmation) inside atomic() so the
  // awaiting_confirmation ledger record commits durably, then trigger the prompt and return 409 confirmation_required OUTSIDE!
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

    // 1. Pre-execution anti-replay barrier: exact deduplication on (session_id, queue_id)
    if Some(existing) = store.queues.get((session_id, q.queue_id)) {
      // Never allow reusing the same queue_id with altered steps or arguments!
      require existing.queue_digest == queue_digest
        else G2AError("conflict", 409, "queue_id reused with different steps or arguments")

      if existing.state != "awaiting_confirmation" {
        return Ok(EarlyReturnReceipt(this.to_receipt(store, sess, existing)))
      }
      // In awaiting_confirmation: check whether a trusted confirmation channel wrote a matching approved_digest
      if existing.approved_digest != Some(queue_digest) {
        return Ok(StillAwaitingConfirmation)
      }
      existing.state = "running"
      return Ok(ReadyToDispatch(existing))
    }

    // 2. Validate scope, tri-state policy (allow / confirm / prohibit), target-level readiness, and refusal cooldown per step
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

      // Core safety invariants:
      // (a) Real-money / external-wallet transactions ALWAYS require native human confirmation and NEVER auto-execute;
      // (b) Unprompted companion queues (trigger == "proactive") targeting the primary player seat (actor == "player"),
      //     if not prohibited, MUST escalate to "confirm" to prevent control hijacking, unauthorized spending, or answer spoiling!
      if "real_money" in cap_def.risk_flags {
        effective_policy = "confirm"
        requires_real_money_ui = true
      } else if q.trigger == "proactive" and step.actor == "player" and effective_policy == "allow" {
        effective_policy = "confirm"
      }

      require effective_policy != "prohibit" else G2AError("permission_denied", 403, "Prohibited by policy")
      if effective_policy == "confirm" { needs_confirm = true }

      // Target-level readiness check: step 0 MUST already be "ready"; subsequent steps MUST be "ready" or "staged"
      step_readiness = resolve_step_readiness(view.methods.get((step.method_id, step.actor)), step.args)
      require step_readiness != None else G2AError("stale_context", 409, "Method or target not currently available",
                                                   fresh_context = Some(this.project_context(store, sess)))
      if step.step_index == 0 {
        require step_readiness == Some("ready") else G2AError("stale_context", 409, "First step target is not ready",
                                                              fresh_context = Some(this.project_context(store, sess)))
      }
    }

    // 3. Persist ledger entry (even when confirmation is required, commit awaiting_confirmation without burning queue_id!)
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
      // Ledger is durably committed; now spawn the single-prompt confirmation UI asynchronously and return 409 confirmation_required
      this.spawn_single_queue_confirmation_async(session_id, rec, fp, real_money_ui)
      return Err(G2AError("confirmation_required", 409, "Awaiting single-prompt player confirmation"))
    }
    ReadyToDispatch(rec) => return this.dispatch_queue_steps(session_id, rec.queue_id)
  }
}

// Asynchronous callback from trusted confirmation channel (MUST NEVER be callable from the Core Interface!)
fn HubEngine.on_trusted_confirmation_result(session_id: String, queue_id: String, queue_digest: String,
                                            fingerprint: String, approved: Bool) {
  this.persistence.atomic(session_id, store => {
    rec = store.queues.get((session_id, queue_id))
    if rec == null or rec.state != "awaiting_confirmation" { return Ok() }
    if approved {
      // Record tamper-bound digest approval and notify Computation Core to resubmit with the same queue_id
      rec.approved_digest = Some(queue_digest)
      this.push_stream.push_event(session_id, "queue.confirmed", {"queue_id": queue_id})
    } else {
      // Player declined or confirmation timed out: cancel queue and enforce refusal cooldown on the same target!
      rec.state = "cancelled"
      store.set_confirm_cooldown(session_id, fingerprint, clock.now_ms() + DEFAULT_CONFIRM_COOLDOWN_MS)
      this.push_stream.push_event(session_id, "queue.declined", {
        "queue_id": queue_id, "cooldown_ms": DEFAULT_CONFIRM_COOLDOWN_MS
      })
    }
    return Ok()
  })
}

// Phase B: Per-slot serialization & supersedes preemption + per-step target-level ready revalidation + metering + failure abort
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
        sess.consumption_used += 1 // Meter actually dispatched controlled steps against player cap
        return Ok(StepReady(OriginExecuteRequest(
          sess.scope.slot_id, view.epoch, "invoke", exec_id, Some(step.method_id), Some(step.actor), step.args
        )))
      }
      if r == None { return Ok(AbortStep("target_disappeared_or_invalid")) }
      return Ok(WaitNextSync) // Still "staged" while awaiting delta sync from the preceding step
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
  // 1. Acquire per-slot execution ownership (preempting any running queue when supersedes == true)
  this.preempt_or_acquire_slot_queue(session_id, queue_id)?

  for i in 0 .. step_count(session_id, queue_id) {
    // 2. Before dispatching each step, revalidate that player is online, queue wasn't cancelled, and target is now "ready"!
    step_prep = this.wait_until_step_ready_or_abort(session_id, queue_id, step_index = i)
    if step_prep.should_abort {
      return Ok(this.abort_remaining_steps(session_id, queue_id, from_index = i, reason = step_prep.reason))
    }

    // 3. Dispatch single step to Interaction Origin via origin.execute(kind="invoke")
    exec_reply = this.origin_client.execute(step_prep.exec_req.unwrap())?

    // 4. If step entered sustained "executing" state, await terminal receipt piggybacked on origin.sync.settled_executions or cancel signal
    if exec_reply.state == "executing" {
      exec_reply = this.await_step_settlement_or_cancel(session_id, queue_id, exec_reply.execution_id)
    }

    // 5. Record step receipt; on any failure or cancellation, immediately abort all remaining steps!
    this.record_step_outcome(session_id, queue_id, i, exec_reply)
    if exec_reply.state != "succeeded" {
      return Ok(this.abort_remaining_steps(session_id, queue_id, from_index = i + 1,
                                           reason = exec_reply.failure_reason.unwrap_or("step_not_succeeded")))
    }
  }

  return Ok(this.finalize_completed_queue(session_id, queue_id))
}

// Core Interface: queue.cancel (interrupts unfinished queue & in-flight executing step) & queue.query (side-effect-free reconciliation)
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

## 4. Tier 3: Computation Core SDK Pseudocode Specification

This chapter targets **in-house cognitive engines (such as `MotCore`) and third-party AI agent providers**, specifying how to connect to the **Core Interface** with zero game-engine coupling while properly handling confirmation holds, timeout reconciliation, and open-format companion memory portability.

<a id="section-4-1"></a>

### 4.1 Cognitive Reasoning and Long-Term Memory Adapter Ports

```text
interface CognitivePlannerPort {
  // Input: ONLY static capability definitions + projected active method IDs and state brief (isolating untrusted in-game text from control policy!)
  // Output: optional chat response text, plus an optional ordered MethodCallQueue plan
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

### 4.2 Session Connection, Heartbeat, and Stream Reconnect Client State Machine

```text
class CoreSDK {
  state capability_cache: Map<String, List<CapabilityEntry>> = {} // cap_digest -> cached static capability table
  state actions_paused: Bool = false

  fn connect_and_run(hub_endpoint: String, auth_token: SecretToken, slot_id: String) -> Result<Void, G2AError> {
    validate_outbound_url_against_ssrf(hub_endpoint)? // Enforce https:// scheme, host/IP & port policy against SSRF / DNS rebinding
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

  // Standard recovery procedure after a transient stream disconnect
  fn on_stream_reconnected() {
    match this.https_post_authed("session.resume", {}) {
      Ok(res) => {
        // When lease expired or local fallback took over, actions_paused == true; wait quietly for session.resumed without submitting queues!
        this.actions_paused = res.actions_paused
        this.latest_context = res.latest_context
      }
      Err(err) if err.code in ["revoked", "permission_denied"] => {
        this.shutdown_session_cleanly() // Player went offline or revoked access; stop immediately without reconnect loops!
      }
      Err(_) => this.backoff_and_retry_resume()
    }
  }

  // Clears action pause once the human player approves resuming after a prolonged disconnect or fallback takeover
  fn on_event_session_resumed(fresh_ctx: ProjectedContext) {
    this.actions_paused = false
    this.on_context_received(fresh_ctx)
  }
}
```

---

<a id="section-4-3"></a>

### 4.3 Context Consumption, Queue Submission, Confirmation Resubmission, and Timeout Reconciliation

When `queue.submit` returns `409 confirmation_required` or `504 outcome_unknown`, the **Computation Core** **MUST** follow the recovery state machine below — never minting a fresh `queue_id` to bypass a hold or blindly resending side effects:

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
      supersedes = (ctx.player_command != null), // Automatically preempt running queues on explicit new player commands
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
      // Retain the original queue object intact! Await queue.confirmed or queue.declined on the push stream
      this.pending_confirm_queues[queue.queue_id] = queue
    }
    Err(err) if err.code == "stale_context" => {
      // World state changed: replan directly from the attached fresh_context (never retry stale arguments)
      if Some(fresh) = err.fresh_context { this.on_context_received(fresh) }
    }
    Err(err) if err.code == "outcome_unknown" => {
      // 504 timeout rule: NEVER blindly resend queue.submit or mint a new queue_id! Reconcile via queue.query first
      this.reconcile_unknown_queue(queue.queue_id)
    }
    Err(err) if err.code == "resource_limit" => {
      this.sleep_ms(err.retry_after_ms.unwrap_or(2000))
    }
    Err(_) => { /* invalid_arguments / permission_denied / conflict: halt retries and log diagnostic */ }
  }
}

// Upon receiving player approval from the Hub's trusted consent channel, resubmit the EXACT original queue (same queue_id + identical steps)!
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

### 4.4 Open-Format Companion Memory Export and Conservative Import Pseudocode

```text
struct MemoryRecord {
  memory_id: String,
  created_at_ms: Int64,
  imported_at_ms: Option<Int64>,
  epistemic_source: "game_observed" | "player_stated" | "agent_summary" | "player_edited",
  game_origin_id: Option<String>,
  timeline_tag: Option<String>,    // Anti-spoiler timeline tag across save reloads
  pinned_by_player: Bool,          // When true, autonomous compaction MUST NEVER overwrite or delete!
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

// Source provider export: verify ONLY the player's own identity; NEVER vet or restrict destination platforms!
fn MemoryService.export_bundle(player_auth: VerifiedPlayerIdentity) -> MemoryBundleV1 {
  return this.store.export_all(player_auth.player_id)
}

// Receiving provider import: preserve provenance & pin status, never widen disclosure boundaries on migration, and return honest per-record statuses
fn MemoryService.import_bundle(player_auth: VerifiedPlayerIdentity, bundle: MemoryBundleV1,
                               selected_ids: List<String>) -> ImportReceiptV1 {
  statuses: Map<String, "imported" | "transformed" | "rejected"> = {}
  for rec in bundle.records {
    if rec.memory_id not in selected_ids { continue }
    rec.imported_at_ms = Some(clock.now_ms())
    // Conservative disclosure narrowing: intersect source record scope with local platform's strictest ceiling; never widen scope
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

## 5. End-to-End Cross-Tier Integration Walkthroughs

This chapter traces two representative game genres end to end using the exact function names defined in Chapters 2–4 so third-party SDK and Hub teams can verify hop-by-hop behavior.

<a id="section-5-1"></a>

### 5.1 Walkthrough 1: Embodied Spatial Player Command (Pathfinding + Direct Chest-Open Effect)

```text
[Entry Phase]
1. Game boots -> OriginSDK.bind_actor_subject("player", PlayerPawn)
              -> OriginSDK.bind_actor_subject("companion", CompanionPawn)
              -> OriginSDK.register_capability(#01 move_to [sustained=true], NavEffect, ...)
              -> OriginSDK.register_capability(#02 interact [sustained=false], ChestOpenEffect, ...)
              -> Sends origin.capabilities cached at HubEngine (cap_digest = "sha256:8a1f...")
2. CoreSDK.connect_and_run() -> HubEngine.handle_session_authorize() -> Establishes sess-01 & caches capability table

[Runtime Spatial Diff & Player Command Phase]
3. OriginSDK.flush_dirty_sync() -> Sends origin.sync(rev=18, mode="delta"):
     #01 move_to(actor="companion", target="chest_R", player_anchor="right 4m", readiness="ready")
     #02 interact(actor="companion", target="chest_R", readiness="staged")
4. While holding key E to drink a potion (hand animation playing), player speaks: "Open the chest on my right"
   -> OriginSDK.report_player_command("Open the chest on my right")
   -> HubEngine.project_context(player_command="Open the chest on my right")
   -> CorePushStreamPort.push_event("context.push") straight to CoreSDK (zero Origin callback round-trip!)

[Single-Pass Planning & Step-by-Step Dispatch Phase]
5. CoreSDK.on_context_received() -> Composes & submits MethodCallQueue(Q-101, trigger="player_command", supersedes=true):
     Step 0: #01 move_to(actor="companion", args={"target_id": "chest_R"})
     Step 1: #02 interact(actor="companion", args={"target_id": "chest_R"})
6. HubEngine.handle_queue_submit(Q-101) -> Passes validation, enters dispatch_queue_steps:
   • Step 0 dispatches OriginSDK.handle_origin_execute(kind="invoke", exec-1, #01) -> Returns "executing" (companion begins pathfinding)
   • Companion reaches chest_R -> OriginSDK.complete_step(exec-1, succeeded=true)
     -> Atomically reports [#02 chest_R now "ready" + settled_executions=[exec-1]] inside a single origin.sync(rev=19) delta frame
   • Step 1 passes wait_until_step_ready_or_abort confirming #02(chest_R) is now "ready"!
     -> Dispatches OriginSDK.handle_origin_execute(kind="invoke", exec-2, #02)
     -> Directly invokes ChestOpenEffect(actor="companion"), bypassing player E-key mutex & animation lockouts!
7. HubEngine returns QueueReceipt(Q-101, state="completed", loot=["gold_50", "potion_1"]) -> CoreSDK calls chat.send to report loot
```

---

<a id="section-5-2"></a>

### 5.2 Walkthrough 2: Avatar-Less Management Signal Alert & Single-Prompt Queue Confirmation

```text
[Entry Phase]
1. Top-down management sim (zero character bodies, spatial=null):
   OriginSDK.bind_actor_subject("companion", BlueprintOverlayController) // Non-intrusive blueprint planning overlay
   OriginSDK.bind_actor_subject("player", WorkshopLedgerController)      // Primary player ledger controller
   OriginSDK.bind_state_module("workshop", Workshop.snapshot, Workshop.active_methods)

[Signal Trigger & Proactive Queue Gate Phase]
2. Bench 1 runs out of timber -> Emits `changed` signal -> OriginSDK.notify_module_changed("workshop", significant_event=true)
   -> Sends origin.sync(rev=42, significant_event=true):
        #05 trade_resource(actor="player", readiness="ready")
        #06 resume_line(actor="player", target="Bench_1", readiness="staged", alert_tag="halted_no_material")
3. HubEngine sees significant_event==true, immediately wakes adaptive idle sleep, and pushes context.push to CoreSDK
4. CoreSDK.on_context_received() -> Submits proactive queue Q-205(trigger="proactive"):
     Step 0: #05 trade_resource(actor="player", args={"item": "timber", "qty": 20})
     Step 1: #06 resume_line(actor="player", args={"line_id": "Bench_1"})
5. HubEngine.handle_queue_submit(Q-205):
   • Detects trigger=="proactive" with actor=="player" -> Automatically escalates to "confirm"!
   • Computes queue_digest = jcs_sha256("g2a.confirm.v1", {sess, "Q-205", steps})
   • Commits awaiting_confirmation ledger record, invokes TrustedPlayerConsentPort.prompt_queue_confirmation() (single prompt for the whole queue)
   • Returns HTTP 409 confirmation_required to CoreSDK without burning queue_id "Q-205"
6. Player clicks "Approve" -> HubEngine.on_trusted_confirmation_result(approved=true)
   -> Stores approved_digest and pushes queue.confirmed("Q-205") to CoreSDK
7. CoreSDK.on_event_queue_confirmed("Q-205") -> Resubmits queue.submit with identical Q-205 & arguments
   -> HubEngine verifies matching queue_digest -> Executes #05 timber purchase (rev=43 turns #06 ready) and #06 Bench_1 resumption!
```

---

<a id="section-5-3"></a>

### 5.3 Third-Party SDK Interoperability Self-Check Checklist

Before releasing a custom engine **Interaction Origin SDK** or custom language **Computation Core SDK**, third-party teams should verify the following 8 baseline interoperability checks:

| # | Mandatory Check | Pass Criterion |
| --- | --- | --- |
| 01 | **Strict JSON & JCS Digests** | Rejects `NaN`/`Infinity`/duplicate keys; `jcs_sha256` matches reference SHA-256 byte-for-byte on identical objects. |
| 02 | **Zero-Change Zero-Packet** | When world state and active grants are unchanged, `OriginSDK` emits zero redundant `origin.sync` packets. |
| 03 | **Direct Effect Without Hotkey Lockout** | While the player holds any physical action key playing an animation, `origin.execute` still settles effects concurrently without state-machine deadlocks. |
| 04 | **Interruptible Sustained Steps** | `StartedExecuting` actions immediately stop pathfinding/charging and settle to `cancelled` upon receiving `origin.execute(kind="cancel")`. |
| 05 | **Confidentiality Redaction** | Unrevealed puzzle answers, fog-of-war enemy positions, and un-drawn deck orders are stripped inside `OriginSDK` prior to serialization. |
| 06 | **Confirmation Preserves `queue_id`** | On `409 confirmation_required`, retains the original `queue_id`, resubmits unchanged upon `queue.confirmed`, and respects `cooldown_ms` on refusal. |
| 07 | **Reconcile Before Retry on `504`** | On `504 outcome_unknown`, queries `queue.query` first and never mints a fresh `queue_id` to blindly resend side effects. |
| 08 | **Mandatory Offline Stop** | Immediately halts background polling and reconnect loops upon player disconnect or `403 revoked`, consuming zero idle compute. |
