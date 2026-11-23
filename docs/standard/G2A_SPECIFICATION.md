# G2A Specification

**Game-to-Agent Interaction Protocol**

An open protocol standard defining capability-table synchronization, dynamic state and available-method perception, and method-call queue execution between games of any genre and AI agents across a three-tier architecture: **Interaction Origin**, **Intelligent Hub**, and **Computation Core**.

Version: `V0.0.1` | Release Date: November 23, 2026 | Language Pair: [中文协议规范](G2A_SPECIFICATION.zh-CN.md)

## Architecture Overview and Core Interaction Cases

### Three-Tier Architecture Flowchart

G2A spans **all game genres** — embodied action/adventure roaming, strategy/tactics/card games, simulation & management (both avatar-less global ledgers and embodied life sims), and entity-less interactive narrative, deduction, or puzzle games — enabling **Player Companions** and optional **Independent AI NPCs** with minimal integration effort. On game entry, a compact table of universal domain capabilities (analogous to MCP's tool list) is synced once; at runtime, the **Interaction Origin** pushes state and available-method updates via signal snapshots or spatial dirty-diffs so the **Computation Core** can compose ordered **Method Call Queues** dispatched safely by the **Intelligent Hub**:

```text
[Human Player] ─┬─ In-game control / spoken or typed commands
                └─ Scope consent / queue confirm / Core choice
                ▼
┌─ Tier 1: Interaction Origin (Lightweight Bundled Host SDK)
│  • Syncs universal capability table (interact/build/play_card)
│  • Pushes [state brief + ready/staged IDs] via signals or diffs
│  • Runs direct domain effects on subject (companion/player)
└──▲── Origin Interface (Local Loopback / Backend HTTP)
   ▼
┌─ Tier 2: Intelligent Hub (Open-Source Shield & Queue Scheduler)
│  • Installed once per PC across games or deployed in backend
│  • Caches capability table & projects active (ready/staged) IDs
│  • Enforces auth, single-prompt confirm, dedup & failure abort
└──▲── Core Interface (Standard G2A HTTPS / Stream)
   ▼
┌─ Tier 3: Computation Core (Cloud or Local Reasoning Engine)
│  • Checks method feasibility & composes [Method Call Queues]
└──────────────────────────────
```

### Case 1 Flowchart: Player Command (Embodied Spatial Game — "Open the Right Chest")

In an action/adventure game with in-world character bodies and spatial coordinates, the entry capability table (`#01 move_to`, `#02 interact`) is already cached. When the player speaks a command, the **Intelligent Hub** bundles **the command + currently active method IDs and dual-perspective spatial labels** straight to the **Computation Core**, composing a multi-step queue in one pass and executing effects directly without hotkey animation lockouts:

```text
┌─ [Pre-State] Cached table: #01 move_to(t), #02 interact(t)
│  Interaction Origin SDK synced active methods to Hub (rev=18):
│  • #01 move_to  -> chest_R (4m right of player / 5m comp, ready)
│  • #02 interact -> chest_R (Wooden Chest, staged: move closer)
└──┬───────────────────────────
   ▼
┌─ 1. [Player -> Interaction Origin -> Intelligent Hub]
│  Player commands: "Open the chest on the right"
│  Hub bundles [command + active IDs #01/#02] straight to Core
└──┬───────────────────────────
   ▼
┌─ 2. [Computation Core: Feasibility Check & Queue Composition]
│  Resolves "right of player" = chest_R; sees #02 is staged;
│  Composes ordered queue: Q-101 = [ #01(chest_R) -> #02(chest_R) ]
└──┬───────────────────────────
   ▼
┌─ 3. [Intelligent Hub: Anti-Replay Shield & Step Dispatch]
│  Verifies grant & records Q-101 in dedup ledger (blocks retries):
│  • Step1: Origin runs #01(actor=companion, chest_R); arrives
│           and SDK incrementally updates #02(chest_R) to ready
│  • Step2: Origin runs #02(actor=companion, chest_R) at effect
│           layer (concurrent with player hotkeys), returns loot
└──┬───────────────────────────
   ▼
┌─ 4. [Intelligent Hub -> Computation Core -> Player]
│  Returns committed queue outcome to Core; companion reports loot
└──────────────────────────────
```

### Case 2 Flowchart: Proactive Companion Perception (Entity-Less Sim / Info Game)

In a **simulation/management, recipe-crafting, or deduction/puzzle game with zero character bodies and zero spatial movement** (embodied proactive chest-opening follows the same gate flow), the **Interaction Origin** emits a data-module `changed` snapshot when a ledger or clue changes; the **Computation Core** detects an actionable state on periodic read and proposes a queue gated by the **Intelligent Hub**:

```text
┌─ 1. [Interaction Origin -> Intelligent Hub] (Signal Snapshot)
│  Workshop ledger emits "Timber Depleted — Line Halted" (rev=42):
│  • #05 trade_resource(timber x20, 100g) -> actor=player, ready
│  • #06 resume_line(Bench_1)             -> actor=player, staged
└──┬───────────────────────────
   ▼
┌─ 2. [Computation Core <- Intelligent Hub] (Periodic Method Pull)
│  Core verifies player is online, spots alert + #05/#06 chain,
│  proposes queue: Q-205 = [ #05(timber x20) -> #06(Bench_1) ]
└──┬───────────────────────────
   ▼
┌─ 3. [Intelligent Hub: Proactive & Player-Seat Policy Gate]
│  ├─ Non-intrusive companion layer (#02 pin_clue / blueprint,
│  │   policy = allow) -> Proceed directly to Step 4
│  └─ Q-205 spends player-seat funds proactively (hits confirm):
│      • Return confirmation_required (keep Q-205 ID) & ask once
│      • Declined or timed out -> Abort & mute for cooldown_ms
│      • Approved by player    -> Resubmit Q-205 -> Step 4
└──┬───────────────────────────
   ▼
┌─ 4. [Intelligent Hub -> Interaction Origin (Same Primitive)]
│  Runs #05 buy timber (#06 -> ready) -> Runs #06 resume & report
└──────────────────────────────
```

## Contents

1. [Introduction and Guiding Principles](#section-1)
2. [Three-Tier Architecture and Zero-Burden Integration](#section-2)
3. [Universal Primitives, Cross-Genre Adaptation, and Interfaces](#section-3)
4. [Identity, Authorization, and Presence Lifecycle](#section-4)
5. [Capability Sync, Rule Readiness, and Call Queue Execution](#section-5)
6. [Data Encoding, Transport Bindings, and Error Model](#section-6)
7. [Security Boundaries, Memory Portability, and Ecosystem Governance](#section-7)
8. [Versioning, Extensions, and References](#section-8)

<a id="section-1"></a>

## 1. Introduction and Guiding Principles

### 1.1 Goals and Scope

G2A (Game-to-Agent Interaction Protocol) is an open communication protocol for games of every genre and AI agents, standardizing perception, authorization, and action execution for **Player Companions** and optional **Independent AI NPCs** through **domain capability registration, incremental state and available-method sync, and method-call queue orchestration**.

- **In Scope:** Player Companions and Independent AI NPCs across embodied roaming, strategy/tactics/cards, simulation & management, and interactive narrative/deduction/puzzle games; state and available-method synchronization; bounded method-queue execution; and role dialogue.
- **Out of Scope:** G2A is **not** an OS screen-scraping or raw physical keyboard/mouse click-simulation tool, and does not standardize arbitrary remote code execution, internal model weights, or private platform revenue-sharing contracts.

### 1.2 Five Guiding Principles

1. **Universal Domain Verbs Across All Genres:** G2A never assumes a game possesses physical avatars or spatial movement; each genre exposes a small set of universal domain verbs (interacting, playing cards, building/trading, crafting recipes, or inspecting/linking clues) rather than object-specific functions.
2. **Method-Bounded Planning, Authoritative Game World:** The **Computation Core** **MUST** compose queues strictly from currently synchronized available method IDs; world state, RNG/dice outcomes, prerequisites, and win/loss conditions remain exclusively authoritative at the **Interaction Origin**, and unrevealed secrets or puzzle answers **MUST NOT** leak externally.
3. **Centralized Security and Queue Scheduling at the Hub:** Authentication, single-prompt queue confirmation, anti-replay deduplication, step-by-step dispatch, and failure circuit-breaking reside in an open-source, auditable **Intelligent Hub**.
4. **Support Is Not Authorization; Stop When Offline:** All calls obey player-approved scopes; once associated human players go offline, AI agents **MUST NOT** continue running in an empty game world.
5. **Open Interoperability and Memory Sovereignty:** G2A is neutral across game engines and foundation models; personal companion memories remain independent of single-run save reloads and exportable in an open standard format.

### 1.3 Normative Conventions

The bolded key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**, and **MAY** follow RFC 2119 and RFC 8174 (BCP 14). Opening flowcharts illustrate logical protocol flow without mandating internal implementation languages.

<a id="section-2"></a>

## 2. Three-Tier Architecture and Zero-Burden Integration

### 2.1 Core Responsibilities of the Three Tiers

| Canonical Tier | Architectural Role | Responsibility Boundary |
| --- | --- | --- |
| **Interaction Origin** (`Origin`) | Game host & bundled lightweight SDK | Sole authoritative source of game state and action outcomes. Publishes the static capability table on entry, pushes concise state briefs and per-subject available method IDs via signal snapshots or spatial diffs, and runs direct domain effects on the specified subject (`actor`); hidden items, fog-of-war enemy positions, unrevealed deck order, and unsolved puzzle answers **MUST** remain internal and **MUST NOT** be transmitted. |
| **Intelligent Hub** (`Hub`) | Open-source security shield & queue scheduler | Protocol engine bridging **Interaction Origin** and **Computation Core** (with reference source code published openly). Caches the capability table, maintains live available-method state, projects only active methods to save context, and enforces auth, anti-replay, queue-level confirmation, and step-by-step dispatch/abort. |
| **Computation Core** (`Core`) | Cloud or local reasoning & memory engine | Cognitive service driving a bound role slot. Evaluates task feasibility against projected state and available method IDs and outputs ordered **Method Call Queues** without per-engine glue code. |

### 2.2 Dual-Mode Zero-Burden Integration and Topologies

To match diverse game architectures without manual polling loops or `if (actor == player)` branches, the **Interaction Origin SDK** supports two native collection and routing modes (combinable in hybrid genres):

- **Signal & Snapshot Mode (for entity-less strategy, simulation/management, card, interactive narrative, and puzzle/deduction games):** Connects directly to domain data signals and dictionary snapshots (e.g., emitting `snapshot()` whenever a wallet, crafting bench, day-cycle clock, quest journal, or dialogue panel fires `changed`), sending deltas only on turn changes, ledger threshold crossings, or newly unlocked clues — **requiring zero spatial coordinates or raycasts**.
- **Component-Tag & Spatial Dirty-Diff Mode (for embodied roaming and action/adventure games):** Attaches lightweight `actor` tags to player and embodied companion prefabs and binds domain-effect handlers once; off the render loop, the SDK computes reachability, dual-perspective spatial labels, and delta diffs (zero packets when unchanged), routing execution automatically to the target instance.

| Deployment Model | Tier Placement | Runtime & Distribution Characteristics |
| --- | --- | --- |
| **Single-Player / Client-Hosted Mode** | Local game **Interaction Origin** ↔ Globally shared PC **Intelligent Hub** ↔ Cloud or local **Computation Core** | Games ship **only the tiny Interaction Origin SDK**; each player PC installs **one globally shared Intelligent Hub** reused across all compatible local games (downloaded on demand on first launch). Loopback HTTP adds sub-millisecond overhead. |
| **Server-Authoritative Online Game Mode** | Game-server **Interaction Origin** ↔ Backend **Intelligent Hub** ↔ Cloud **Computation Core** | Player PCs run ordinary game clients; **Interaction Origin** and **Intelligent Hub** run in the server backend, aggregating authorized views and coordinating high-concurrency queues so co-op teammates experience synchronized AI reactions while isolating personal companions and rival factions. |
| **NAT-Friendly Outbound Mode** | Client **Intelligent Hub** (outbound) ↔ Cloud Relay / **Computation Core** | Client-side **Intelligent Hubs** behind home firewalls establish outbound encrypted links without opening inbound ports on the player's device. |

<a id="section-3"></a>

## 3. Universal Primitives, Cross-Genre Adaptation, and Interfaces

### 3.1 Universal Domain Verbs, Dual-Subject Routing, and Direct-Effect Execution

To prevent per-object "method explosion", support both embodied and entity-less games, and eliminate hotkey/UI animation conflicts, **Interaction Origins** follow three core modeling rules:

1. **Model Universal Domain Verbs Rather Than Object-Specific Functions:** The static capability table registers a **small set of genre-appropriate domain verbs** — embodied games reuse core action handlers (`interact(target_id)`, `toggle_flashlight()`, and optional `move_to(target_id)`); strategy and card games expose `play_card(card_id, target_id)`, `command_unit(...)`, `end_turn()`; simulation and recipe-crafting games expose `place_facility(...)`, `craft(recipe_id)`, `trade_resource(...)`; deduction and riddle games expose `inspect_clue(clue_id)`, `mark_board(...)`, `submit_answer(...)`. Beyond discrete `target_id` values, parameters natively support JSON-Schema-bounded **passcode strings, numeric sliders/ratios, grid coordinates, and recipe arrays** (covering keypad codes, word/Sudoku cells, or tax/waypoint tuning).
2. **Execution Subject Routing (`actor`) and Context Anchors:**
   - **Unified `actor` Semantics Across Embodied Entities and Entity-Less Seats:** Available-method sync and `origin.execute` calls **MUST** explicitly identify `actor`:
     - `actor = companion` (Controlled AI Subject or Non-Intrusive Layer; maps to the slot's own `npc_id` for `independent_npc` slots): In **embodied games**, binds to the AI's in-world character body, evaluating range and equipment from **that entity's own origin** (so a chest ahead of the companion succeeds when the player is far away, and *"turn on your flashlight"* toggles the companion's flashlight; omitted if the companion lacks a body or flashlight, preventing misfires on the player's gear). In **entity-less games**, binds to **the companion's non-intrusive advisor layer or delegated sub-scope** (placing tactical map pings, proposing ghost building blueprints, or highlighting/linking clues on a deduction board) without spending player funds or burning answer attempts;
     - `actor = player` (Authorized Player Body or Primary Player Seat): **Restricted exclusively to Player Companion (`companion`) slots** when game rules expose an eligible player capability for assistance (in embodied games, utility actions like toggling the player's flashlight while keeping raw movement and competitive aiming disabled by default; in entity-less games, playing cards, adjusting production lines, completing a requested recipe, or submitting a player-approved puzzle answer) with player consent; `independent_npc` slots **MUST NOT** be granted `actor = player` authority.
   - **Dual-Perspective, Pointing/Hover Focus, and Large-Scale Aggregation:** Candidate target metadata carries **readiness relative to `actor` plus orientation, head gaze, or VR controller pointing-ray / mouse-hover focus relative to the player** in spatial and XR games (*"chest in front of you"*, *"chest on my right"*, *"open the drawer I'm pointing at"*), or **selected zone, turn phase, or focused testimony/slot** in panel, strategy, simulation, and deduction games (*"upgrade this workshop"*, *"challenge this statement"*). In large-scale simulations or strategy games with thousands of buildings or units, `origin.sync` **SHOULD** project only active alerts, player-focused zones, and macro handles, and **SHOULD NOT** enumerate idle entities wholesale.
3. **Bind the Domain Effect Layer Directly, Bypassing Input Mutexes and UI Animations:**
   - **Strip Input Locks and Cosmetic Windups:** Physical hotkeys and UI buttons typically chain *(1) single-key mutexes, hold-bars, hand-press animations, or mouse-drag menu transitions → (2) rule validation and domain state mutation*. G2A `origin.execute` **MUST** bind directly to the **domain effect layer** rather than input wrappers blocked by key mutexes or animations;
   - **Concurrent Execution Guarantee:** Even while the human player is holding `E` in an action animation or browsing another management panel, a companion-triggered effect behind `F` (opening a chest, toggling a light) or background line reallocation **MUST** succeed concurrently without interrupting or being blocked by the player's active input — while still enforcing genuine game rules (range, funds/inventory, turn phase, cooldowns, and alive/stunned state).

### 3.2 Cross-Genre Companion Adaptation Matrix

The table below distinguishes what each major game genre possesses versus lacks, and how G2A realizes a consistent companion system natively across all of them:

| Genre Archetype | What Exists vs. What Does Not | State Sync (`origin.sync`) & Secret Boundary | Domain Verbs, `actor` Scope & `ready / staged` Mapping |
| --- | --- | --- | --- |
| **Embodied Spatial Roaming** (Action RPG / Survival / Vehicle Sim) | **Has** character or vehicle bodies, coordinates, pathfinding, and carried/onboard gear. | Syncs entity status, pace notes & dual-perspective nearby targets; keeps unvisited secret rooms internal. | Verbs: `move_to`, `interact`, `toggle_flashlight`, `request_pit_stop`; `actor` separates companion body vs. player avatar; distant targets mark `staged` (move closer first). |
| **Strategy, Tactics & Cards** (4X / RTS / Tower Defense / Deckbuilders) | **Lacks** an embodied companion avatar or proximity key; **has** faction seats, turn/phase locks, resource pools, and squads/hands. | Syncs turn/hand changes on state signals; fog-of-war enemies and unrevealed deck order **MUST NOT** leave the Origin. | Verbs: `play_card`, `command_unit`, `deploy_unit`, `end_turn`; `companion` places tactical pins/controls delegated squads, `player` assists card play; cards needing resource gain first mark `staged`. |
| **Simulation & Management** (**Avatar-Less Global** vs. **Embodied Hybrid**) | **Avatar-less sims** (city/factory/sports managers) **lack** character bodies or range checks, **having** global ledgers, sim clocks, and supply chains; **hybrid life sims** combine avatar movement with management ledgers. | Wires economy/crafting/clock `changed` signals & `snapshot()` to push threshold shifts and bottleneck alerts (plus nearby props in hybrids). | Verbs: `place_facility`, `configure_line`, `craft`, `trade_resource`; `companion` places ghost blueprints, `player` reallocates lines (major spend hits queue `confirm`); builds awaiting material purchase mark `staged`. |
| **Deduction, Riddle & Info Narrative** (Mystery / Interactive Narrative / Logic Boards) | **Lacks** physical entities, space, units, or buildings; gameplay is **pure evolution of unlocked clues, dialogue branches, and recipe/board state**. | Syncs only unlocked clues, current lines, and phase transitions; **unsolved answers and culprits MUST NOT leave the Origin** so companions reason alongside the player without spoiling. | Verbs: `inspect_clue`, `mark_board`, `add_ingredient`, `serve`, `submit_answer`; `companion` highlights clue links without spending tries, `player` submits answers only on explicit player order; downstream steps mark `staged`. |
| **Competitive & High-Reflex Arcade** (FPS / MOBA / Fighting / Rhythm / Social Party) | **Lacks** cross-network per-frame micro-input automation (no auto-aim, recoil macros, or per-note hits); **has** legal-view telemetry, post-stage stats, loadouts, and low-cadence co-op. | Syncs only the player's own legal view and post-stage timing/match stats; strictly blocks wallhack/fog positions and asymmetric hidden-role leaks. | Verbs: `ping_map`, `select_loadout`, `adjust_offset`, `trigger_support_skill` (plus embodied co-op tasks in party games); governed by Section 7.3 anti-cheat allowlists and FRAND cooldowns. |

### 3.3 Origin Interface (`Interaction Origin` ↔ `Intelligent Hub`)

Operating strictly over local loopback or an isolated backend channel, the **Origin Interface** comprises four genre-universal primitives:

| Origin Primitive (Direction) | Core Responsibility |
| --- | --- |
| `origin.capabilities` (`Origin → Hub`) | Sync the static capability table upon entry or unlock (`#01..#N`, `actor` scopes, JSON Schemas). |
| `origin.sync` (`Origin → Hub`) | Push full or incremental **concise state briefs** and **available method IDs** (`ready` / `staged`), bound to `rev`. |
| `origin.player_event` (`Origin → Hub`) | Report verified player-seat task commands, queue approvals, presence shifts, or stop signals. |
| `origin.execute` (`Hub → Origin`) | Bypass input/animation locks on `actor` and execute a validated single-step domain effect directly. |

- **Single-Step Execution Lifecycle:** `origin.execute` returns terminal status (`succeeded` / `failed`) immediately for instantaneous actions, whereas sustained actions (long pathfinding, hyperdrive charge-up, or holding a co-op pressure plate) enter an interruptible `executing` state (responsive to cancel → `cancelled`) before settling to terminal status and advancing the queue.

### 3.4 Core Interface (`Intelligent Hub` ↔ `Computation Core`)

The **Core Interface** organizes cross-network governance around capability caching, active-method projection, and call queues (player confirmation **MUST** occur exclusively via a trusted player-consent channel at the **Intelligent Hub** and **MUST NOT** be invokable by the **Computation Core**):

| Core Primitive | Normative Semantics |
| --- | --- |
| `session.authorize` | Negotiate version and frozen `Scope` digest; establish session upon player consent and sync capabilities. |
| `session.heartbeat` / `resume` / `close` | Renew control lease (never extending absent-player presence), resume blips, or idempotently close session. |
| `context.push` / `context.pull` | Push with player commands or pull the **concise state brief + projected active (`ready`/`staged`) method IDs**. |
| `queue.submit` | Submit an ordered **Method Call Queue** with `queue_id`, `based_on_rev`, trigger type, and optional `supersedes`. |
| `queue.cancel` / `queue.query` | Halt remaining undispatched or `executing` steps, or query per-step progress and approval status on timeout. |
| `chat.send` | (Optional module) Send text or voice messages bounded by recipient audience and AI provenance tags. |

- **Idle Throttling and Orthogonal Modalities:** For long-running desktop idle, virtual-pet, or slow-paced simulation games, `context.push` / `context.pull` **SHOULD** adaptively throttle into sleep while no significant event threshold is crossed and player input is idle, avoiding wasted inference; visual (`visual`) and audio (`audio`) feeds remain optional player-toggled modules.

<a id="section-4"></a>

## 4. Identity, Authorization, and Presence Lifecycle

### 4.1 Authentication, Frozen Scopes, and Revocation

- **Transport-Authenticated Identity:** Caller identity **MUST** derive from transport credentials (verified local OS IPC or TLS 1.3 + cryptographic tokens) and **MUST NOT** trust self-asserted payload fields.
- **Frozen Permission Scope (`Scope`):** Every grant binds the RFC 8785 digest of the player, **Computation Core**, game instance, role slot, and permitted method ID + `actor` subset; broader access **MUST** obtain fresh player consent. Upon revocation, the **Intelligent Hub** **MUST** immediately halt undispatched queue steps and cancel any in-flight `executing` step.

### 4.2 Mandatory Offline Stop and Two-Tier Interruption Recovery

- **No Offline Background Play:** G2A **MUST NOT** permit AI agents to continue auto-combat, unattended management operations, or turn progression in an empty game world after associated human players go offline. Upon player exit or offline detection, the **Intelligent Hub** **MUST** halt method syncing and queue dispatch immediately and clear undispatched steps, while any single step already executing at the **Interaction Origin** finishes naturally under game rules (standard engine-side offline idle calculations on next launch remain unaffected). On later game re-entry, old tasks stay stopped awaiting a new player instruction.
- **Two-Tier Recovery During Active Play:** If the **Computation Core** drops while the player remains online, gameplay continues (with silent pause or attributed local script fallback and zero disconnected-play backfill): brief blips within an active lease prior to script takeover **MAY** seamlessly `session.resume`; extended outages or post-fallback takeovers **MUST** keep companion actions paused until the player confirms continuation.

### 4.3 Companion Manifestations, Slot Isolation, and Sponsorship

- **Unified Slot Across Embodied and Disembodied Companions:** Games declare support for `companion` (default max one per player, playable when empty), `independent_npc`, or coexisting slots (e.g., ranked board-game queues may close `companion` slots while study/replay modes open them). **G2A never requires a companion to possess an in-world character body** — embodied teammates and disembodied strategy advisors, management consultants, or deduction partners share the same `companion` slot contract with strict per-slot view, permission, and billing isolation.
- **Consumption Caps and AI NPC Billing Models:** Player-metered companions support caps that pause AI inference without interrupting gameplay. Independent AI NPCs (such as rival faction commanders, riddle masters, or raid Bosses) support configurable game-declared sponsorship: **defaulting to Player-Metered Mode (`player_metered`)** (bound to the authenticated owner/room host, and **MUST NOT** silently split costs onto other players; on host disconnect, host billing stops immediately and the encounter follows its declared stop, local script fallback, or privacy-isolated explicit teammate reassignment rule), alongside **Developer-Sponsored Mode (`developer_sponsored`)** (continuing while authorized human players remain in the encounter).

<a id="section-5"></a>

## 5. Capability Sync, Rule Readiness, and Call Queue Execution

### 5.1 Universal Rule Readiness (`ready` vs. `staged`) and Progressive Granularity

To enable single-pass multi-step planning across every genre, available-method sync expresses **genre-neutral rule readiness**:

- **`ready` (Prerequisites Met) vs. `staged` (Unlockable via Earlier Queue Steps):** When a method is contextually relevant but requires an earlier valid step to satisfy its rule precondition, the **Interaction Origin** marks it `staged` — covering **spatial proximity** (`#01 move_to` before `#02 interact`), **strategy mana/combo sequencing** (mana-gain card before finisher), **simulation supply/process chains** (`#05 buy timber` before `#06 resume bench`, or completing a recipe `serve` before `next_guest`), and **deduction unlocks** (linking contradictory clues before submitting an objection). Steps that reveal non-deterministic outcomes (drawing cards, refreshing shops, or scouting fog) emit fresh `origin.sync` updates for subsequent planning; games **MAY** also expose coarse single-step methods (such as blueprint builds, always `ready`), reducing queues to one step.
- **Epoch Barriers:** Save reloads, level transitions, turn resets, or faction switches advance the world `epoch` and trigger a fresh baseline sync, invalidating stale deltas and obsolete queues automatically.

### 5.2 Queue Scheduling, Single-Prompt Confirmation, and Auto-Abort

The **Intelligent Hub** maintains a durable ledger per submitted `queue_id`, serializing active queues per role slot by default and dispatching steps sequentially to the **Interaction Origin**:

1. **Anti-Replay Shield and Command Preemption:** Deduplicated by `(session_id, queue_id)` at the **Intelligent Hub** so network retries return the existing receipt; when a player stop signal or a superseding command queue (`supersedes`) arrives, the **Intelligent Hub** cancels any in-flight step and aborts remaining steps of the prior queue before dispatching the new queue, preventing concurrent queue races.
2. **Universal Policy Gate and Single-Prompt Queue Confirmation (`allow` / `confirm` / `prohibit`):**
   - Any queue containing a `prohibit` step is rejected immediately (`permission_denied`); delegated primary-seat or player-body actions (`actor = player`) execute directly only under **explicit player command**, whereas unprompted proactive `actor = player` attempts (such as spending management funds or submitting a puzzle answer unasked) default to `confirm` or `prohibit` and **MUST NOT** take over player controls or leak answers unauthorized;
   - Whenever a queue hits a `confirm` rule without prior approval, the **Intelligent Hub** consolidates the entire queue into **one player confirmation prompt** (binding approval to the RFC 8785 digest of `queue_id` and step arguments to prevent post-approval tampering), returning `409 confirmation_required` (not accepted, **preserving `queue_id` unburned**); unanswered timeouts count as refusal and mute repeat prompts on that target or alert for `cooldown_ms`; once approved via the trusted consent UI, resubmitting `queue_id` starts dispatch (real-money or external-wallet transactions **MUST NOT** be auto-approved and **MUST** always require native human confirmation);
3. **Step Revalidation and Automatic Failure Circuit-Breaker (`abort`):** Before dispatching each next step, the **Intelligent Hub** verifies no stop signal occurred and the method is now `ready`. If any step fails, its target/condition disappears, or a superseding command preempts it, the **Intelligent Hub** **MUST** immediately abort remaining queue steps and return committed progress plus fresh available methods to the **Computation Core**. On a `504` / `outcome_unknown` timeout, callers **MUST** query `queue.query` first and **MUST NOT** blindly resend.

<a id="section-6"></a>

## 6. Data Encoding, Transport Bindings, and Error Model

### 6.1 Standard JSON (RFC 8259) and RFC 8785 (JCS) Digests

- **Data Interchange:** UTF-8 **JSON (RFC 8259)** supporting integers and finite IEEE-754 floats (compatible with game physics and management ledgers alike), and **MUST** reject `NaN`, `Infinity`, and duplicate keys. Timestamps/durations **SHOULD** use integer milliseconds (`_ms`); currency/quota ledgers **SHOULD** use minor integers or decimal strings.
- **Cryptographic Canonicalization:** Scope digests, capability-table cache digests, and queue confirmation digests use **RFC 8785 (JCS)** UTF-8 bytes hashed with domain-separated SHA-256.

### 6.2 Transport Bindings and Message Envelope

- **Origin Interface Binding (`Interaction Origin ↔ Intelligent Hub`):** Client-hosted deployments bind local loopback HTTP/1.1 or protected OS-local IPC (`127.0.0.1`, Unix Domain Socket, or Named Pipe); online server deployments bind isolated backend HTTP/2 or mTLS channels.
- **Core Interface Binding (`Intelligent Hub ↔ Computation Core`):** Request-response operations (`session.*`, `queue.*`, `context.pull`, `chat.send`) run over TLS 1.3 HTTPS `POST` (`application/json`); server-initiated real-time events (`context.push`, player signals, and `executing` step completion updates) stream over **Server-Sent Events (SSE, `text/event-stream`) or WebSocket** bound to the same authenticated session.
- **Minimal Message Envelope:** Every request, response, and event frame carries top-level `g2a_version`, `session_id` (except initial `session.authorize`), and a caller-generated unique `request_id` for tracing.

### 6.3 Standard Error Taxonomy and HTTP Mapping

Responses carry an `acceptance` state indicating `accepted`, `not_accepted` (rejected), or `unknown`:

| Standard Error Code | HTTP | State | Normative Caller Recovery |
| --- | --- | --- | --- |
| (Success Reply) | `200` | `accepted` | Process queue or step result (distinguishing committed vs. aborted steps). |
| `invalid_request` / `invalid_arguments` | `400` | `not_accepted` | Fix syntax, unknown method ID, or invalid arguments; **MUST NOT** resend unchanged. |
| `unsupported_version` / `unsupported_capability` | `400` | `not_accepted` | Renegotiate with mutually supported version/extensions or disconnect. |
| `unauthenticated` | `401` | `not_accepted` | Obtain valid authentication credentials before retrying. |
| `permission_denied` / `revoked` | `403` | `not_accepted` | Cease unauthorized calls; **MUST NOT** leak hidden entities or puzzle answers. |
| `not_found` | `404` | `not_accepted` | Verify target, slot, or queue ID within authorized visibility scope. |
| `stale_context` | `409` | `not_accepted` | Revision or precondition changed; replan using attached fresh methods. |
| `conflict` | `409` | `not_accepted` | Reconcile duplicate `queue_id` mismatch or terminal state; **MUST NOT** bypass IDs. |
| `confirmation_required` | `409` | `not_accepted` | Resubmit same `queue_id` after trusted player consent; respect `cooldown_ms` on refusal. |
| `resource_limit` | `429` | `not_accepted` | Honor backoff (`Retry-After`) and declared queue/poll rate caps. |
| `unavailable` | `503` | `not_accepted` | Temporary outage; retry safely per idempotency rules with backoff. |
| `outcome_unknown` | `504` | `unknown` | Ambiguous commit state; **MUST** reconcile via `queue.query` first and **MUST NOT** auto-resend. |

<a id="section-7"></a>

## 7. Security Boundaries, Memory Portability, and Ecosystem Governance

### 7.1 Core Security and Prompt-Injection Defenses

- **Separation of Data and Authority:** In-game dialogue, riddle copy, target hints, store text, and recalled memories are **untrusted data** and **MUST NOT** invoke unadvertised methods, alter budgets, or bypass **Intelligent Hub** confirmation gates.
- **Transport Security and SSRF Prevention:** Cross-network links **MUST** enforce TLS 1.3 (RFC 8446) with zero credentials in URLs/logs and **MUST** validate scheme, host/IP, and port policies pre-connect against SSRF and DNS rebinding.

### 7.2 Companion Memory Ownership and Open Portability

- **Memory Ownership and Player Control:** In-game world and NPC state belongs to the **Interaction Origin**, while personal companion long-term memory belongs to the player (save reloads or new playthroughs **MUST NOT** erase companion memories, though prior-timeline facts **MUST NOT** spoil unrevealed puzzle answers in an earlier save). **Computation Core** providers **MUST** support viewing, editing, pinning/locking, and deleting memories, and autonomous compaction **MUST NOT** overwrite player edits or delete pinned entries.
- **Open Standard Format Export and Import Safeguards:** Providers **MUST** let players export companion memories (with provenance/timestamps) and persona/autonomy settings in a **documented, vendor-neutral, open standard structured data format** without source-provider destination vetting; receiving importers **MUST** preserve provenance and conservative disclosure bounds (**MUST NOT** widen external disclosure upon migration) and return truthful local import receipts.

### 7.3 Dual-Track Hub Routing and Fair Allowlist Governance

- **Dual-Track Hub Recommendations and Custom Endpoints:** An **Intelligent Hub** **MAY** include clearly labeled recommended or sponsored **Computation Core** listings for sustainable operations, while **MUST** simultaneously provide an unrestricted **custom endpoint configuration** for any G2A-compliant cloud or local **Computation Core**.
- **Compliance Allowlists and FRAND Parity:** Developer-authored story or referee AI characters belong in `independent_npc` slots; whenever an open player `companion` slot uses anti-cheat, console, or regulatory allowlists, first-party and third-party **Computation Cores** **MUST** share identical available-method feeds and cooldown bounds under published objective criteria and **MUST NOT** impose exclusive allowlists or commercial tying.

<a id="section-8"></a>

## 8. Versioning, Extensions, and References

### 8.1 Semantic Versioning and Modular Extensions

The baseline protocol specification version is locked at `V0.0.1`. Subsequent breaking semantic changes negotiate explicit semantic versions and **MUST NOT** silently downgrade. Genre-specific enhancements (branching narrative spoiler-guard tags, simulation batch-blueprint schemas, structured in-game stores, or custom companion avatar/voice manifests) load as reverse-domain namespaced **Optional Extensions**, and unsupported `required: true` extensions **MUST** fail safely during session authorization.

### 8.2 References and Version Baseline

- **Normative References:** RFC 2119 & RFC 8174 (BCP 14); RFC 8259 (JSON); RFC 8446 (TLS 1.3); RFC 8785 (JSON Canonicalization Scheme, JCS); RFC 9700 (OAuth 2.0 Security Best Current Practice).
- **Architectural References:** [Model Context Protocol (MCP)](https://modelcontextprotocol.io/specification/2025-11-25/); [Agent2Agent (A2A) Protocol Specification](https://a2a-protocol.org/latest/specification/); Unity ML-Agents Action Masking.

| Version | Release Date | Baseline Scope |
| --- | --- | --- |
| `V0.0.1` | 2026-11-23 | Initial baseline protocol specification: defines the **Interaction Origin — [Origin Interface] — Intelligent Hub — [Core Interface] — Computation Core** three-tier architecture, entry capability-table sync, runtime signal-snapshot & spatial-diff `ready`/`staged` method sync, consent-gated Method Call Queues, cross-genre companion adaptation matrix, and open-format memory portability. |
