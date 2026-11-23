# G2A Specification

**Game-to-Agent Interaction Protocol**

An open protocol standard defining capability-table synchronization, dynamic available-method perception, and method-call queue execution between games and AI agents across a three-tier architecture: **Interaction Origin**, **Intelligent Hub**, and **Computation Core**.

Status: Working Draft for Public Review (`standard-review-2026-11-23-r81`) | Revision Date: November 23, 2026 | Language Pair: [中文协议规范](G2A_SPECIFICATION.zh-CN.md)

## Architecture Overview and Core Interaction Cases

### Three-Tier Architecture Flowchart

G2A enables any game to introduce AI roles safely with **minimal developer effort** — primarily a **Player Companion** accompanying the player, alongside optional **Independent AI NPCs**. Upon game entry, a compact table of universal character capabilities (analogous to MCP's tool list) is synced once; at runtime, the **Interaction Origin SDK** automatically pushes incremental available-method IDs and targets to the **Intelligent Hub**, enabling the **Computation Core** to compose ordered **Method Call Queues** dispatched step by step through the **Intelligent Hub**:

```text
                        [ Human Player ]
               ┌────────────────┴────────────────┐
       In-game control / commands        Consent / queue confirm / Core choice
               ▼                                 ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Tier 1: Interaction Origin (Lightweight Host SDK Bundled with Game)    │
│  • Syncs universal capability table on entry (#01 move, #02 interact)  │
│  • SDK auto-scans & pushes [state brief + ready/staged method IDs]     │
│  • Runs direct effect on actor (companion/player), bypassing key locks │
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ Southbound Interface (Loopback / Backend HTTP)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Tier 2: Intelligent Hub (Open-Source Security Shield & Queue Scheduler)│
│  • Installed once & shared per PC (single-player) or server-deployed   │
│  • Caches capability table & projects active methods to save context   │
│  • Centralizes auth, queue-level confirm, anti-replay & step abort     │
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ Northbound Interface (G2A HTTPS / Stream)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Tier 3: Computation Core (Cloud or Local Reasoning & Memory Engine)    │
│  • Checks method feasibility & composes ordered [Method Call Queues]   │
└────────────────────────────────────────────────────────────────────────┘
```

### Case 1 Flowchart: User-Initiated Command — "Open the Chest on the Right"

Triggered by **explicit player command**. Because the universal capability table (`#01 move_to`, `#02 interact`) was cached at game entry and active method IDs are kept fresh at the **Intelligent Hub**, the hub forwards **the player's command + currently active method IDs and dual-perspective targets** straight to the **Computation Core** with zero extra round-trip queries:

```text
┌────────────────────────────────────────────────────────────────────────┐
│ [Pre-State] Entry capability table cached: #01 move_to, #02 interact   │
│ Interaction Origin SDK incrementally synced active methods (rev=18):   │
│  • #01 move_to  ──▶ target: chest_R (4m right of player / 5m to comp,  │
│                                      status: ready)                    │
│  • #02 interact ──▶ target: chest_R (Wooden Chest · Open,              │
│                                      status: staged — move closer)     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 1. [Player ──▶ Interaction Origin ──▶ Intelligent Hub]                 │
│    Player speaks/types command: "Open the chest on the right"          │
│    Hub bundles [command + active method IDs #01/#02] to Core directly  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 2. [Computation Core: Feasibility Check & Queue Composition]           │
│    Resolves "right of player" to chest_R; confirms task is feasible;   │
│    Seeing #02 is staged (needs proximity), composes call queue once:   │
│    Queue Q-101 = [ Step1: #01(chest_R) ──▶ Step2: #02(chest_R) ]       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 3. [Intelligent Hub: Anti-Replay Shield & Step-by-Step Dispatch]       │
│    Verifies grant & deduplicates Q-101 (blocks duplicate retries):     │
│    • Dispatch Step1 ──▶ Origin runs #01(actor=companion, chest_R)      │
│      Companion walks to chest; Origin SDK updates #02(chest_R)=ready   │
│    • Dispatch Step2 ──▶ Origin runs #02(actor=companion, chest_R)      │
│      Runs direct chest effect (bypassing key/anim locks): [50g, Potion]│
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 4. [Intelligent Hub ──▶ Computation Core ──▶ Player]                   │
│    Hub returns committed queue outcome; companion reports loot         │
└────────────────────────────────────────────────────────────────────────┘
```

### Case 2 Flowchart: Companion Periodic Perception and Proactive Action — "Open the Chest"

Triggered **without any player command**. Here the companion character stands 1 meter in front of `chest_B` (even if the human player's character is far away). Evaluating range from the **companion actor's own origin**, the **Interaction Origin SDK** marks `#02 interact(chest_B)` as `ready`; the **Computation Core** spots it during periodic reads and proposes a proactive queue gated by the **Intelligent Hub**:

```text
┌────────────────────────────────────────────────────────────────────────┐
│ 1. [Interaction Origin SDK ──▶ Intelligent Hub] (Auto Dirty-Diff Sync) │
│    Companion stands 1m from chest_B; SDK evaluates companion origin:   │
│    Incremental sync: #02 interact adds chest_B (1m ahead, ready)       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 2. [Computation Core ◀── Intelligent Hub] (Periodic Active-Method Pull)│
│    Core verifies player is online, reads #02(chest_B, ready), and      │
│    autonomously submits proactive queue: Queue Q-205 = [#02(chest_B)]  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 3. [Intelligent Hub: Proactive Policy Gate]                            │
│    ├─ Policy = "allow" (auto-explore) ──▶ Proceed directly to Step 4   │
│    └─ Policy = "confirm" (ask before proactive interaction):           │
│         • Return confirmation_required (preserving Q-205 ID) & prompt  │
│         • Declined or timed out ──▶ Abort & mute target for cooldown   │
│         • Approved by player   ──▶ Core resubmits Q-205 -> Step 4      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 4. [Intelligent Hub ──▶ Interaction Origin (Zero Extra Game Code)]     │
│    Re-verifies chest_B is still ready & unopened, then dispatches:     │
│    Origin executes #02(actor=companion, chest_B) ──▶ Opens & reports   │
└────────────────────────────────────────────────────────────────────────┘
```

## Contents

1. [Introduction and Guiding Principles](#section-1)
2. [Three-Tier Architecture and Zero-Burden Integration](#section-2)
3. [Universal Action Primitives, Dual-Actor Model, and Interfaces](#section-3)
4. [Identity, Authorization, and Presence Lifecycle](#section-4)
5. [Capability Sync, Method Readiness, and Call Queue Execution](#section-5)
6. [Data Encoding, Transport Bindings, and Error Model](#section-6)
7. [Security Boundaries, Memory Portability, and Ecosystem Governance](#section-7)
8. [Versioning, Extensions, and References](#section-8)

<a id="section-1"></a>

## 1. Introduction and Guiding Principles

### 1.1 Goals and Scope

G2A (Game-to-Agent Interaction Protocol) is an open communication protocol that standardizes perception, authorization, and action execution between games and AI agents (Player Companions and optional Independent AI NPCs) through **entry capability registration, dynamic available-method sync, and method-call queue orchestration**.

- **In Scope:** Player Companions, Independent AI NPCs (such as Bosses, tactical teammates, or guides), game state and available-method synchronization, bounded method-queue execution, and role dialogue.
- **Out of Scope:** G2A is **not** an OS screen-scraping or raw physical keyboard/mouse simulation tool, and does not standardize arbitrary remote code execution, internal LLM weights, or private platform revenue-sharing contracts.

### 1.2 Five Guiding Principles

1. **Universal Verbs, Zero Origin Boilerplate:** Studios reuse a small set of universal character actions rather than writing hundreds of object-specific functions; spatial scanning and incremental diffing are automated by the **Interaction Origin SDK**.
2. **Method-Bounded Planning, Authoritative Game World:** The **Computation Core** composes queues strictly from currently synchronized available method IDs; physics, range, and rule outcomes are adjudicated exclusively by the **Interaction Origin**.
3. **Centralized Security and Queue Scheduling at the Hub:** Authentication, single-prompt queue confirmation, anti-replay deduplication, step-by-step dispatch, and failure circuit-breaking reside in an open-source, auditable **Intelligent Hub**.
4. **Support Is Not Authorization; Stop When Offline:** All calls obey player-approved scopes; once associated human players go offline, AI agents MUST NOT continue running in an empty game world.
5. **Open Interoperability and Memory Sovereignty:** G2A is neutral across game engines and foundation models; personal companion memories remain independent of single-run save reloads and exportable in an open standard format.

### 1.3 Normative Conventions

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**, and **MAY** follow RFC 2119 and RFC 8174 (BCP 14). Opening flowcharts illustrate logical protocol flow without mandating internal implementation languages.

<a id="section-2"></a>

## 2. Three-Tier Architecture and Zero-Burden Integration

### 2.1 Core Responsibilities of the Three Tiers

| Canonical Tier | Architectural Role | Responsibility Boundary |
| --- | --- | --- |
| **Interaction Origin** (`Origin`) | Game host & bundled lightweight SDK | Sole authoritative source of world state and action outcomes. Publishes the static capability table on entry, uses the SDK to auto-sync concise state briefs and per-actor available method IDs, and executes direct domain-effect callbacks on the specified `actor` (`companion` or authorized `player`); unrevealed game secrets **MUST** remain internal. |
| **Intelligent Hub** (`Hub`) | Open-source security shield & queue scheduler | Protocol engine bridging **Interaction Origin** and **Computation Core** (with reference source code published openly). Caches the capability table, maintains live available-method state, projects only active methods to save LLM context, and enforces auth, anti-replay, queue-level confirmation, and step-by-step dispatch/abort. |
| **Computation Core** (`Core`) | Cloud or local reasoning & memory engine | Cognitive service driving a bound role slot. Evaluates task feasibility against projected available method IDs and outputs ordered **Method Call Queues** without per-engine glue code. |

### 2.2 Developer Zero-Burden Integration and Topologies

To eliminate manual polling boilerplate and per-actor branching code, the **Interaction Origin SDK** uses **component-tag actor routing + direct effect binding + background dirty-diffing**: developers attach a lightweight `actor` tag to the player prefab and (when embodied) the companion prefab, and register existing character component methods or eligible utility-hotkey effect callbacks **once** (with zero `if (actor == player)` branches; legacy projects with player-only singletons can register `actor = player` directly without refactoring). Off the render loop, the SDK automatically inspects active `player` and `companion` instances for component readiness, relative orientation, and delta diffs (emitting zero packets when state is unchanged), and routes execution directly to the target instance's effect handler.

| Deployment Model | Tier Placement | Runtime & Distribution Characteristics |
| --- | --- | --- |
| **Single-Player / Client-Hosted Mode** | Local game **Interaction Origin** ↔ Globally shared PC **Intelligent Hub** ↔ Cloud or local **Computation Core** | Games ship **only the tiny Interaction Origin SDK**; each player PC installs **one globally shared Intelligent Hub** reused across all compatible local games (downloaded on demand on first launch). Loopback HTTP adds sub-millisecond overhead. |
| **Server-Authoritative Online Game Mode** | Game-server **Interaction Origin** ↔ Backend **Intelligent Hub** ↔ Cloud **Computation Core** | Player PCs run ordinary game clients with zero local AI components; **Interaction Origin** and **Intelligent Hub** run in the server backend, aggregating authorized views and coordinating high-concurrency queue execution so co-op raid teammates experience synchronized AI behavior while keeping personal companions and rival factions isolated. |
| **NAT-Friendly Outbound Mode** | Client **Intelligent Hub** (outbound) ↔ Cloud Relay / **Computation Core** | Client-side **Intelligent Hubs** behind home firewalls establish outbound encrypted links without opening inbound ports on the player's device. |

<a id="section-3"></a>

## 3. Universal Action Primitives, Dual-Actor Model, and Interfaces

### 3.1 Universal Verbs, Dual-Actor Routing, and Direct-Effect Execution

To prevent "method explosion hell" (writing separate functions for doors, chests, computers, and levers), cleanly distinguish *"your flashlight / chest ahead of you"* from *"my flashlight / chest on my right"*, and avoid hotkey animation lockouts, **Interaction Origins** follow three core modeling rules:

1. **Reuse Universal Character Actions Rather Than Object-Specific Functions:** The static capability table models a **small set of universal character verbs** — typically the dozen logical handlers behind the game's input-action map plus basic pathfinding `move_to(target_id)` (for example, one universal `interact(target_id)` wired to the game's existing interactable base class handles every door, chest, terminal, and switch across the entire game; one `toggle_flashlight()` controls flashlights; a card game needs only `play_card(card_id, target_id)`). Dedicated methods are added only for mechanics requiring extra structured parameters (such as entering a keypad code or crafting a specific quantity).
2. **Dual-Actor Routing (`actor = companion | player`) and Dual-Perspective Spatial Anchors:**
   - **Explicit Distinction Between Embodied Companion and Delegated Player Assist:** Available-method sync and `origin.execute` calls **MUST** explicitly specify the target `actor`:
     - `actor = companion` (Companion's Own Entity): Advertised automatically by the SDK only when the companion possesses an in-world character entity and the corresponding component/item, evaluating range and readiness from **the companion's own origin** — ensuring a chest in front of the companion succeeds even when the human player is far away, and ensuring *"turn on your flashlight"* operates the companion's own flashlight (if the companion lacks an embodied avatar or flashlight, `actor = companion` is omitted so the **Computation Core** informs the player accurately without misfiring the player's flashlight);
     - `actor = player` (Authorized Player-Assist Execution): Advertised when game rules expose an eligible player utility/hotkey capability for AI assistance (such as toggling a flashlight, pinging the map, switching items, or full co-pilot/card-game play — keeping raw movement and competitive aiming disabled by default) and the player grants consent, evaluating readiness from **the player entity's origin** so *"turn on my flashlight"* operates the player's own flashlight while the player's hands are busy;
   - **Dual-Perspective Target Labels:** Candidate `target_id` metadata carries both **readiness relative to the acting `actor`** (`ready: 1m from companion` vs. `staged: 5m from companion, move closer`) and **orientation relative to the human player** (`4m right of player` or `player's current look target`), cleanly disambiguating *"open the chest in front of you"* from *"open the chest on my right"*.
3. **Bind the Domain Effect Layer Directly, Bypassing Key-Press Mutexes and Hotkey Animations:**
   - **Strip Input Mutexes and Key-Press Windups:** Physical game hotkeys typically chain *(1) single-key input mutexes, hold-bars, and player hand-press animations → (2) gameplay rule validation and domain effect execution*. G2A `origin.execute` **MUST** bind directly to the **domain effect layer** — companions seek the post-press gameplay effect, not the hotkey animation, and **MUST NOT** route through physical input wrappers blocked by single-key mutexes or player hotkey animations;
   - **Concurrent Execution Alongside Active Player Hotkeys:** Even while the human player is actively holding `E` and playing `E`'s hotkey animation, a companion-invoked effect behind `F` (such as opening a chest or toggling a flashlight, on either `actor = companion` or authorized `actor = player`) **MUST** succeed concurrently without being blocked by or interrupting the player's `E` action — while still enforcing genuine world rules such as range, item ownership, cooldowns, and alive/stunned states.

### 3.2 Southbound Host Interface (`Interaction Origin` ↔ `Intelligent Hub`)

Operating strictly over local loopback or an isolated backend LAN, the southbound interface comprises four minimal primitives:

| Southbound Primitive | Direction | Purpose |
| --- | --- | --- |
| `origin.capabilities` | `Origin` → `Hub` | Sync the static capability table upon game entry (or chapter capability change), assigning stable method IDs (`#01..#N`), descriptions, permitted `actor` scopes (`companion` / `player`), parameter schemas, and risk flags for caching at the **Intelligent Hub** and **Computation Core**. |
| `origin.sync` | `Origin` → `Hub` | Periodically push full or incremental dual-frame updates: (1) **concise state brief** (health, phase, recent events) and (2) **available method IDs** (marking per-`actor` `ready` vs. `staged` status and dual-perspective candidate `target_id` lists) bound to monotonic revision `rev`. |
| `origin.player_event` | `Origin` → `Hub` | Report verified player-seat signals: explicit player task commands, online/offline transitions, or emergency stop signals. |
| `origin.execute` | `Hub` → `Origin` | Execute a single validated method ID and target argument directly at the domain-effect layer on the specified `actor` (`companion` or authorized `player`), bypassing hotkey/animation locks and returning authoritative status (`succeeded` / `failed` / `cancelled`) and world effects. |

### 3.3 Northbound Protocol Interface (`Intelligent Hub` ↔ `Computation Core`)

The northbound interface organizes cross-network governance around capability caching, active-method projection, and method-call queues:

| Primitive Group | Core Operations | Normative Semantics |
| --- | --- | --- |
| **Session & Capabilities** | `session.authorize` | Negotiate version and permission `Scope` (bound by an RFC 8785 digest), establish the session upon player consent, and sync the static capability table (or verify cached table digest). |
| | `session.heartbeat` / `resume` / `close` | Renew the **Computation Core** control lease (never extending absent-player presence), resume after brief blips, or idempotently close the session and fence remaining queue steps. |
| **Active Context & Methods** | `context.push` / `context.pull` | Push (bundled automatically with player commands) or allow periodic pulls of the **concise state brief + projected active available method IDs** (transmitting only currently `ready`/`staged` methods so large static tables never bloat LLM context). Visual (`visual`) and game-audio (`audio`) feeds remain optional player-toggled modules. |
| **Method Call Queues** | `queue.submit` | Submit an ordered **Method Call Queue** carrying a unique `queue_id`, referenced `based_on_rev`, and trigger source (player command vs. companion proactive), including single-step queues. |
| | `queue.confirm` | Record single-use player approval via the authenticated consent channel for an entire confirmation-gated queue. |
| | `queue.cancel` / `queue.query` | Halt remaining undispatched steps in a queue, or query authoritative per-step progress after a timeout. |
| **Dialogue** | `chat.send` | (Optional module) Send text or voice replies bounded by recipient audience and provenance tags. |

<a id="section-4"></a>

## 4. Identity, Authorization, and Presence Lifecycle

### 4.1 Authentication, Frozen Scopes, and Revocation

- **Transport-Authenticated Identity:** Caller identity **MUST** derive from transport credentials (verified local OS IPC or TLS + cryptographic tokens), never self-asserted payload fields.
- **Frozen Permission Scope (`Scope`):** Every grant binds the RFC 8785 digest of the player, **Computation Core**, game instance, bound role slot, and permitted method ID subset; broader access requires fresh player consent. Revocation at the **Intelligent Hub** immediately halts any undispatched queue steps.

### 4.2 Mandatory Offline Stop and Two-Tier Interruption Recovery

- **No Offline Background Play:** G2A **MUST NOT** permit AI agents to keep acting in an empty game world after associated human players go offline. Upon player exit or offline detection, the **Intelligent Hub** **MUST** halt method syncing and queue dispatch immediately and clear undispatched steps, while any single step already `executing` at the **Interaction Origin** finishes naturally under game rules. Upon later game re-entry, old tasks stay stopped awaiting a new player instruction.
- **Two-Tier Recovery During Active Play:** If the **Computation Core** drops while the player remains online, gameplay continues (with stationary or attributed local script fallback and zero disconnected-play backfill): brief blips within an active lease prior to script takeover may seamlessly `session.resume`; extended outages or post-fallback takeovers **MUST** keep companion actions paused until the player confirms continuation.

### 4.3 Role Slot Isolation and Configurable Cost Sponsorship

- **Declared Role Slots:** Games declare support for `companion` (default max one per player, playable when empty), `independent_npc`, or coexisting slots, strictly isolating per-role views, permissions, and billing.
- **Consumption Caps and AI NPC Billing Models:** Player-metered companions support consumption caps that pause AI inference without interrupting gameplay. Independent AI NPCs support configurable game-declared sponsorship: **defaulting to Player-Metered Mode (`player_metered`)** (bound to the authenticated owner/room host with zero silent splitting; on host disconnect, host billing terminates immediately and the encounter follows its declared stop, local script fallback, or privacy-isolated explicit teammate reassignment rule), alongside **Developer-Sponsored Mode (`developer_sponsored`)** (continuing while authorized human players remain in the encounter).

<a id="section-5"></a>

## 5. Capability Sync, Method Readiness, and Call Queue Execution

### 5.1 Two-State Method Availability (`ready` vs. `staged`) and Progressive Granularity

- **`ready` (Immediately Executable) vs. `staged` (Reachable After Prerequisite):** When an interactable target lies within perception range but requires a prerequisite step (such as standing 5m from `chest_R`, requiring `#01 move_to` first), the **Interaction Origin SDK** marks `#02 interact(chest_R)` as `staged`, allowing the **Computation Core** to compose the full `[#01 → #02]` queue in a single inference pass. Studios preferring ultra-simple integration MAY expose coarse single-step methods (such as walk-and-interact combined, always `ready`), reducing queues naturally to one step.
- **Epoch Barriers:** Save reloads, level transitions, or faction changes advance the world `epoch` and trigger a fresh baseline sync, invalidating stale deltas and obsolete queues automatically.

### 5.2 Queue Scheduling, Single-Prompt Confirmation, and Auto-Abort

The **Intelligent Hub** maintains a durable ledger per submitted `queue_id` and dispatches steps sequentially to the **Interaction Origin**:

1. **Anti-Replay Shield:** Deduplicated by `(session_id, queue_id)` at the **Intelligent Hub**; network retries return the existing queue receipt without re-executing steps at the **Interaction Origin**.
2. **Universal Policy Gate and Single-Prompt Queue Confirmation (`allow` / `confirm` / `prohibit`):**
   - Any queue containing a `prohibit` step is rejected immediately (`permission_denied`); delegated player-body actions (`actor = player`) execute directly only under **explicit player command**, whereas unprompted proactive `actor = player` attempts default to `confirm` or `prohibit` so AI never hijacks player controls;
   - Whenever a proactive companion queue, high-value transfer, irreversible trigger, or virtual-currency cap hits a `confirm` rule without prior approval, the **Intelligent Hub** consolidates the entire queue into **one player confirmation prompt**, returning `409 confirmation_required` (`outcome: not_accepted`, **preserving `queue_id` unburned**); unanswered timeouts count as refusal and mute repeat prompts on that target for `cooldown_ms`; upon approval, resubmitting `queue_id` starts execution (real-money or external-wallet transactions are never auto-approved and always require native human confirmation);
3. **Step Revalidation and Automatic Failure Circuit-Breaker (`abort`):** Before dispatching each next step, the **Intelligent Hub** verifies no stop signal occurred and the method is now `ready`. If any step fails at the **Interaction Origin**, the target disappears, or the player issues a superseding command, the **Intelligent Hub** **immediately aborts remaining queue steps** and returns partial completion status plus fresh available methods to the **Computation Core**. On a `504` / `outcome_unknown` timeout, callers **MUST** query `queue.query` first and never blindly resend.

<a id="section-6"></a>

## 6. Data Encoding, Transport Bindings, and Error Model

### 6.1 Standard JSON (RFC 8259) and RFC 8785 (JCS) Digests

- **Data Interchange:** UTF-8 **JSON (RFC 8259)** supporting integers and finite IEEE-754 floats (rejecting `NaN`, `Infinity`, and duplicate keys). Timestamps/durations SHOULD use integer milliseconds (`_ms`); currency/quota ledgers SHOULD use minor integers or decimal strings.
- **Cryptographic Canonicalization:** Scope digests, capability-table cache digests, and queue confirmation digests use **RFC 8785 (JCS)** UTF-8 bytes hashed with domain-separated SHA-256.

### 6.2 Standard Error Taxonomy and HTTP Mapping

| Standard Error Code | HTTP Status | Acceptance | Normative Caller Recovery |
| --- | --- | --- | --- |
| (Success Reply) | `200` | `accepted` | Process queue or step result (truthfully distinguishing committed vs. aborted steps). |
| `invalid_request` / `invalid_arguments` | `400` | `not_accepted` | Fix syntax, unknown method ID, or invalid target parameters; do not resend unchanged. |
| `unsupported_version` / `unsupported_capability` | `400` | `not_accepted` | Renegotiate with mutually supported version/extensions or disconnect. |
| `unauthenticated` | `401` | `not_accepted` | Obtain valid authentication credentials before retrying. |
| `permission_denied` / `revoked` | `403` | `not_accepted` | Cease unauthorized or revoked calls; never leaks hidden entity existence. |
| `not_found` | `404` | `not_accepted` | Verify target or queue ID within authorized visibility scope. |
| `stale_context` | `409` | `not_accepted` | Revision expired or target no longer available; replan using attached fresh methods. |
| `conflict` | `409` | `not_accepted` | Reconcile duplicate `queue_id` mismatch or terminal state; never invent bypass IDs. |
| `confirmation_required` | `409` | `not_accepted` | Resubmit same `queue_id` after `queue.confirm`; respect `cooldown_ms` on refusal/timeout. |
| `resource_limit` | `429` | `not_accepted` | Honor backoff (`Retry-After`) and declared queue/poll rate caps. |
| `unavailable` | `503` | `not_accepted` | Temporary outage; retry safely per idempotency rules with backoff. |
| `outcome_unknown` | `504` | `unknown` | Ambiguous commit state; **MUST** reconcile via `queue.query` first and never auto-resend. |

<a id="section-7"></a>

## 7. Security Boundaries, Memory Portability, and Ecosystem Governance

### 7.1 Core Security and Prompt-Injection Defenses

- **Separation of Data and Authority:** In-game dialogue, target labels, store copy, and recalled memories are **untrusted data** and MUST NOT invoke unadvertised methods, alter budgets, or bypass **Intelligent Hub** confirmation gates.
- **Transport Security and SSRF Prevention:** Cross-network links require authenticated TLS with zero credentials in URLs/logs and strict pre-connect scheme/host/IP/port validation against SSRF and DNS rebinding.

### 7.2 Companion Memory Ownership and Open Portability

- **Memory Ownership and Player Control:** NPC state belongs to the **Interaction Origin**, while personal companion long-term memory belongs to the player (save reloads or new playthroughs MUST NOT erase companion memories). **Computation Core** providers **MUST** support viewing, editing, pinning/locking, and deleting memories without overwriting player edits during autonomous compaction.
- **Open Standard Format Export and Import Safeguards:** Providers **MUST** let players export companion memories (with provenance/timestamps) and persona/autonomy settings in a **documented, vendor-neutral, open standard structured data format** without source-provider destination vetting; receiving importers preserve conservative disclosure bounds and return truthful local import receipts.

### 7.3 Dual-Track Hub Routing and Fair Allowlist Governance

- **Dual-Track Hub Recommendations and Custom Endpoints:** An **Intelligent Hub** **MAY** include clearly labeled recommended or sponsored **Computation Core** listings for sustainable operations, while **MUST** simultaneously provide an unrestricted **custom endpoint configuration** for any G2A-compliant cloud or local **Computation Core**.
- **Compliance Allowlists and FRAND Parity:** Developer-authored story characters belong in `independent_npc` slots; whenever an open player `companion` slot uses anti-cheat, console, or regulatory allowlists, first-party and third-party **Computation Cores** **MUST** share identical available-method feeds and cooldown bounds under published objective criteria without exclusive tying.

<a id="section-8"></a>

## 8. Versioning, Extensions, and References

### 8.1 Semantic Versioning and Modular Extensions

Breaking changes negotiate explicit semantic versions without silent downgrade. Genre-specific features (narrative branch timeline tags, structured in-game stores, or custom companion avatar manifests) load as reverse-domain namespaced **Optional Extensions**, failing safely on unsupported `required: true` extensions.

### 8.2 References and Revision Milestones

- **Normative References:** RFC 2119 & RFC 8174 (BCP 14); RFC 8259 (JSON); RFC 8785 (JSON Canonicalization Scheme, JCS).
- **Architectural References:** Model Context Protocol (MCP, https://modelcontextprotocol.io/specification/2025-11-25/); Google Agent2Agent (A2A) Protocol Specification (https://a2a-protocol.org/latest/specification/); Unity ML-Agents Action Masking; OAuth 2.0 Security BCP (RFC 9700).

| Milestone | Date | Summary of Evolution |
| --- | --- | --- |
| `r48` – `r79` | Nov 13–22, 2026 | Established the **Interaction Origin — Intelligent Hub — Computation Core** three-tier architecture, RFC 8259/8785 encoding, and 8-chapter public protocol structure. |
| `standard-review-2026-11-23-r81` | Nov 23, 2026 | Finalized pure-flowchart overview/cases, entry capability-table + runtime `ready`/`staged` method sync, and Method Call Queues; added `actor = companion \| player` component-routed dual-actor separation (*"turn on your/my flashlight"* + dual spatial anchors) and direct domain-effect execution bypassing hotkey mutexes and key-press animations. |
