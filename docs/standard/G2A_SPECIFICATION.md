# G2A Specification

**Game-to-Agent Interaction Protocol**

An open protocol standard defining capability-table synchronization, dynamic state and available-method perception, and method-call queue execution between games of any genre and AI agents across a three-tier architecture: **Interaction Origin**, **Intelligent Hub**, and **Computation Core**.

Status: Working Draft for Public Review (`standard-review-2026-11-23-r82`) | Revision Date: November 23, 2026 | Language Pair: [中文协议规范](G2A_SPECIFICATION.zh-CN.md)

## Architecture Overview and Core Interaction Cases

### Three-Tier Architecture Flowchart

G2A spans **all game genres** — embodied action/adventure roaming, strategy/tactics/card games, simulation & management (both avatar-less global ledgers and embodied life sims), and entity-less narrative, deduction, or puzzle games — enabling **Player Companions** and optional **Independent AI NPCs** with minimal integration effort. On game entry, a compact table of universal domain capabilities (analogous to MCP's tool list) is synced once; at runtime, the **Interaction Origin** pushes state and available-method updates via signal snapshots or spatial dirty-diffs so the **Computation Core** can compose ordered **Method Call Queues** dispatched safely by the **Intelligent Hub**:

```text
[Human Player] ─┬─ In-game control / spoken or typed commands
                └─ Scope consent / queue confirm / Core choice
                ▼
┌─ Tier 1: Interaction Origin (Lightweight Bundled Host SDK)
│  • Syncs universal capability table (interact/build/play_card)
│  • Pushes [state brief + ready/staged IDs] via signals or diffs
│  • Runs direct domain effects on subject (companion/player)
└──▲── Southbound Interface (Local Loopback / Backend HTTP)
   ▼
┌─ Tier 2: Intelligent Hub (Open-Source Shield & Queue Scheduler)
│  • Installed once per PC across games or deployed in backend
│  • Caches capability table & projects active (ready/staged) IDs
│  • Enforces auth, single-prompt confirm, dedup & failure abort
└──▲── Northbound Interface (Standard G2A HTTPS / Stream)
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

In a **simulation/management, crafting/bartending, or deduction/puzzle game with zero character bodies and zero spatial movement** (embodied proactive chest-opening follows the exact same gate flow), the **Interaction Origin** emits a data-module `changed` snapshot when a ledger or clue changes; the **Computation Core** detects an actionable state on periodic read and proposes a queue gated by the **Intelligent Hub**:

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

- **In Scope:** Player Companions and Independent AI NPCs across embodied roaming, strategy/tactics/cards, simulation & management, and narrative/deduction/puzzle games; state and available-method synchronization; bounded method-queue execution; and role dialogue.
- **Out of Scope:** G2A is **not** an OS screen-scraping or raw physical keyboard/mouse click-simulation tool, and does not standardize arbitrary remote code execution, internal model weights, or private platform revenue-sharing contracts.

### 1.2 Five Guiding Principles

1. **Universal Domain Verbs Across All Genres:** G2A never assumes a game must have physical avatars or spatial movement; each genre exposes a small set of universal domain verbs (interacting, playing cards, building/trading, mixing recipes, or inspecting/linking clues) rather than per-item functions.
2. **Method-Bounded Planning, Authoritative Game World:** The **Computation Core** composes queues strictly from currently synchronized available method IDs; world rules, prerequisites, and outcomes remain exclusively authoritative at the **Interaction Origin**, keeping unrevealed secrets and puzzle answers strictly internal.
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
| **Interaction Origin** (`Origin`) | Game host & bundled lightweight SDK | Sole authoritative source of game state and action outcomes. Publishes the static capability table on entry, pushes concise state briefs and per-subject available method IDs via signal snapshots or spatial diffs, and runs direct domain effects on the specified subject (`actor`); hidden items, fog-of-war enemy positions, unrevealed deck order, and **unsolved puzzle answers MUST remain internal**. |
| **Intelligent Hub** (`Hub`) | Open-source security shield & queue scheduler | Protocol engine bridging **Interaction Origin** and **Computation Core** (with reference source code published openly). Caches the capability table, maintains live available-method state, projects only active methods to save context, and enforces auth, anti-replay, queue-level confirmation, and step-by-step dispatch/abort. |
| **Computation Core** (`Core`) | Cloud or local reasoning & memory engine | Cognitive service driving a bound role slot. Evaluates task feasibility against projected state and available method IDs and outputs ordered **Method Call Queues** without per-engine glue code. |

### 2.2 Dual-Mode Zero-Burden Integration and Topologies

To match diverse game architectures without manual polling loops or `if (actor == player)` branches, the **Interaction Origin SDK** supports two native collection and routing modes (combinable in hybrid genres):

- **Signal & Snapshot Mode (for entity-less strategy, simulation/management, card, narrative crafting, and puzzle/riddle games):** Connects directly to domain data signals and dictionary snapshots (e.g., emitting `snapshot()` whenever a wallet, crafting bench, day-cycle clock, quest journal, or dialogue/mixing panel fires `changed`), sending deltas only on turn changes, ledger threshold crossings, or newly unlocked clues — **requiring zero spatial coordinates or raycasts**.
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

1. **Model Universal Domain Verbs Rather Than Item-Specific Functions:** The static capability table registers a **small set of genre-appropriate domain verbs** — embodied games reuse core action handlers (`interact(target_id)`, `toggle_flashlight()`, and optional `move_to(target_id)`); strategy and card games expose `play_card(card_id, target_id)`, `command_unit(...)`, `end_turn()`; simulation, crafting, and bartending games expose `place_facility(...)`, `craft(recipe_id)`, `add_ingredient(index)`, `trade_resource(...)`; deduction and riddle games expose `inspect_clue(clue_id)`, `mark_board(...)`, `submit_answer(...)`.
2. **Dual-Subject Routing (`actor = companion | player`) and Context Anchors:**
   - **Unified `actor` Semantics Across Embodied Entities and Entity-Less Seats:** Available-method sync and `origin.execute` calls **MUST** explicitly identify `actor`:
     - `actor = companion` (Companion's Own Entity or Non-Intrusive Companion Layer): In **embodied games**, binds to the companion's in-world character body, evaluating range and equipment from **the companion's own origin** (so a chest ahead of the companion succeeds when the player is far away, and *"turn on your flashlight"* toggles the companion's flashlight; omitted if the companion has no body or flashlight, preventing misfires on the player's gear). In **entity-less games**, binds to **the companion's non-intrusive advisor layer or delegated sub-scope** (such as placing tactical map pings, drafting ghost building blueprints, or highlighting/linking suspicious clues on a deduction board) without spending player funds or burning answer attempts;
     - `actor = player` (Authorized Player Body or Primary Player Seat): Exposed when game rules allow AI assistance on a player capability (in embodied games, utility actions like toggling the player's flashlight while keeping raw movement and competitive aiming disabled by default; in entity-less games, playing cards, adjusting production lines, mixing/serving a requested recipe, or submitting a player-approved puzzle answer) with player consent, acting directly on **the player's character or primary seat** (*"turn on my flashlight"*, *"mix and serve this order"*).
   - **Dual-Perspective, Focus Anchors, and Large-Scale Aggregation:** Candidate target metadata carries **readiness relative to `actor` plus orientation relative to the player** in spatial games (*"chest in front of you"* vs. *"chest on my right"*), or **selected zone, turn phase, or focused testimony/slot** in panel, strategy, simulation, and deduction games (*"upgrade this workshop"*, *"challenge this statement"*). In large-scale simulations or strategy games with thousands of buildings or units, `origin.sync` **SHOULD** project only active alerts, player-focused zones, and macro handles rather than dumping idle entities wholesale.
3. **Bind the Domain Effect Layer Directly, Bypassing Input Mutexes and UI Animations:**
   - **Strip Input Locks and Cosmetic Windups:** Physical hotkeys and UI buttons typically chain *(1) single-key mutexes, hold-bars, hand-press animations, or mouse-drag menu transitions → (2) rule validation and domain state mutation*. G2A `origin.execute` **MUST** bind directly to the **domain effect layer** (e.g., `OpenChestEffect()`, `craft()`, `add_ingredient()`) rather than input wrappers blocked by key mutexes or animations;
   - **Concurrent Execution Guarantee:** Even while the human player is holding `E` in an action animation or browsing another management tab, a companion-triggered effect behind `F` (opening a chest, toggling a light) or background line reallocation **MUST** succeed concurrently without interrupting or being blocked by the player's active input — while still enforcing genuine game rules (range, funds/inventory, turn phase, cooldowns, and alive/stunned state).

### 3.2 Cross-Genre Companion Adaptation Matrix

The table below distinguishes what each major game genre possesses versus lacks, and how G2A realizes a companion system natively across all of them:

| Genre Archetype | What Exists vs. What Does Not | State Sync (`origin.sync`) & Secret Boundary | Domain Verbs, `actor` Scope & `ready / staged` Mapping |
| --- | --- | --- | --- |
| **Embodied Spatial Roaming** (Action RPG / Survival / FPS) | **Has** character bodies, coordinates, pathfinding, and carried gear. | Syncs character status & dual-perspective nearby targets; keeps unvisited secret rooms internal. | Verbs: `move_to`, `interact`, `toggle_flashlight`; `actor` separates companion body vs. player avatar; distant targets mark `staged` (move closer first). |
| **Strategy, Tactics & Cards** (4X / RTS / Turn-Based / Deckbuilders) | **Lacks** a walking companion body or proximity `F`-key; **has** faction seats, turn/phase locks, mana/AP pools, and squads/hands. | Syncs turn/hand changes on state signals; strictly withholds **fog-of-war enemies and unrevealed deck order**. | Verbs: `play_card`, `command_unit`, `produce`, `end_turn`; `companion` places tactical pins/controls delegated squads, `player` assists card play; combo cards needing mana-gain first mark `staged`. |
| **Simulation & Management** (**Avatar-Less Global** vs. **Embodied Hybrid**) | **Avatar-less sims** (city/factory builders) **lack** any player/companion body or range checks, **having** global ledgers (funds/power/stock), sim clocks, and supply chains; **hybrid life sims** combine avatar stamina/movement with farm/shop ledgers. | Wires economy/crafting/clock `changed` signals & `snapshot()` to push threshold shifts and bottleneck alerts (plus nearby props in hybrids). | Verbs: `place_facility`, `configure_line`, `craft`, `trade_resource`; `companion` drafts ghost blueprints, `player` reallocates lines (major spend hits queue `confirm`); builds needing material purchase first mark `staged`. |
| **Deduction, Riddle & Info Narrative** (Mystery / Bartending VN / Logic Boards) | **Lacks all** physical entities, space, units, or buildings; gameplay is **pure evolution of unlocked clues, dialogue, and recipe state**. | Syncs only unlocked clues, current riddle/guest lines, and phase transitions; **unsolved answers and culprits MUST NOT leave the Origin** so companions reason alongside the player without spoiling. | Verbs: `inspect_clue`, `mark_board`, `add_ingredient`, `serve`, `submit_answer`; `companion` highlights clue links without spending tries, `player` submits answers only on explicit player order; `next_guest` marks `staged` until `serve` succeeds. |
| **Competitive & High-Reflex Arcade** (FPS / MOBA / Fighting / Rhythm / Social Party) | **Lacks** cross-network per-frame micro-input automation (no auto-aim, recoil macros, or per-note rhythm hits); **has** legal-view telemetry, inter-stage stats, loadouts, and low-cadence tactical/co-op actions. | Syncs only the player's own legal view and post-stage timing/match stats; strictly blocks wallhack/fog positions and cross-player social-deduction role leaks. | Verbs: `ping_map`, `select_loadout`, `adjust_offset`, `trigger_support_skill` (plus embodied co-op cooking/hauling in party games); governed by Section 7.3 anti-cheat allowlists and FRAND cooldowns. |

### 3.3 Southbound Host Interface (`Interaction Origin` ↔ `Intelligent Hub`)

Operating strictly over local loopback or an isolated backend LAN, the southbound interface comprises four genre-universal primitives:

| Primitive | Direction | Normative Responsibility |
| --- | --- | --- |
| `origin.capabilities` | `Origin → Hub` | Sync the static capability table upon entry (or new system unlock), assigning stable IDs (`#01..#N`), descriptions, permitted `actor` scopes (`companion` / `player`), parameter schemas, and risk flags. |
| `origin.sync` | `Origin → Hub` | Push full or incremental updates: (1) **concise state brief** (avatar status, management ledger snapshot, or newly unlocked clue state) and (2) **available method IDs** (per-`actor` `ready` / `staged` status and context anchors), bound to monotonic `rev`. |
| `origin.player_event` | `Origin → Hub` | Report verified player-seat signals: explicit player task commands, online/offline transitions, or emergency stop signals. |
| `origin.execute` | `Hub → Origin` | Execute a validated method ID and arguments directly at the domain-effect layer on `actor`, bypassing input/animation mutexes and returning authoritative status (`succeeded` / `failed` / `cancelled`) and state effects. |

### 3.4 Northbound Protocol Interface (`Intelligent Hub` ↔ `Computation Core`)

The northbound interface organizes cross-network governance into four primitive groups:

| Group | Core Operations | Normative Semantics |
| --- | --- | --- |
| **Session & Scope** | `session.authorize` | Negotiate version and `Scope` (bound by an RFC 8785 digest), establish the session upon player consent, and sync the capability table (or verify cached digest). |
| | `session.heartbeat` / `resume` / `close` | Renew the **Computation Core** lease (never extending absent-player presence), resume after brief blips, or idempotently close the session and fence remaining queues. |
| **State & Methods** | `context.push` / `context.pull` | Push with player commands or allow periodic pulls of the **concise state brief + projected active method IDs** (`ready`/`staged` subset only). Visual (`visual`) and audio (`audio`) feeds remain optional player-toggled modules. |
| **Call Queues** | `queue.submit` | Submit an ordered **Method Call Queue** with unique `queue_id`, `based_on_rev`, and trigger type (player command vs. companion proactive), including single-step queues. |
| | `queue.confirm` | Record single-use player approval via the authenticated consent channel for an entire confirmation-gated queue. |
| | `queue.cancel` / `queue.query` | Halt remaining undispatched steps, or query authoritative per-step progress after a timeout. |
| **Dialogue** | `chat.send` | (Optional module) Send text or voice replies bounded by recipient audience and provenance tags (pure deduction companions may use dialogue + board annotations alone). |

<a id="section-4"></a>

## 4. Identity, Authorization, and Presence Lifecycle

### 4.1 Authentication, Frozen Scopes, and Revocation

- **Transport-Authenticated Identity:** Caller identity **MUST** derive from transport credentials (verified local OS IPC or TLS + cryptographic tokens), never self-asserted payload fields.
- **Frozen Permission Scope (`Scope`):** Every grant binds the RFC 8785 digest of the player, **Computation Core**, game instance, role slot, and permitted method ID + `actor` subset; broader access requires fresh player consent. Revocation immediately halts undispatched queue steps.

### 4.2 Mandatory Offline Stop and Two-Tier Interruption Recovery

- **No Offline Background Play:** G2A **MUST NOT** permit AI agents to keep farming dungeons, auto-running management economies, or advancing strategy turns after associated human players go offline. Upon player exit or offline detection, the **Intelligent Hub** **MUST** halt method syncing and queue dispatch immediately and clear undispatched steps, while any single step already executing at the **Interaction Origin** finishes naturally under game rules. On later game re-entry, old tasks stay stopped awaiting a new player instruction.
- **Two-Tier Recovery During Active Play:** If the **Computation Core** drops while the player remains online, gameplay continues (with silent pause or attributed local script fallback and zero disconnected-play backfill): brief blips within an active lease prior to script takeover may seamlessly `session.resume`; extended outages or post-fallback takeovers **MUST** keep companion actions paused until the player confirms continuation.

### 4.3 Companion Manifestations, Slot Isolation, and Sponsorship

- **Unified Slot Across Embodied and Disembodied Companions:** Games declare support for `companion` (default max one per player, playable when empty), `independent_npc`, or coexisting slots. **G2A never requires a companion to possess an in-world character body** — embodied teammates and disembodied strategy advisors, bar co-pilots, or deduction partners share the exact same `companion` slot contract with strict per-slot view, permission, and billing isolation.
- **Consumption Caps and AI NPC Billing Models:** Player-metered companions support caps that pause AI inference without interrupting gameplay. Independent AI NPCs (such as rival faction commanders, riddle masters, or raid Bosses) support configurable game-declared sponsorship: **defaulting to Player-Metered Mode (`player_metered`)** (bound to the authenticated owner/room host with zero silent splitting; on host disconnect, host billing stops immediately and the encounter follows its declared stop, local script fallback, or privacy-isolated explicit teammate reassignment rule), alongside **Developer-Sponsored Mode (`developer_sponsored`)** (continuing while authorized human players remain in the encounter).

<a id="section-5"></a>

## 5. Capability Sync, Rule Readiness, and Call Queue Execution

### 5.1 Universal Rule Readiness (`ready` vs. `staged`) and Progressive Granularity

To enable single-pass multi-step planning across every genre, available-method sync expresses **genre-neutral rule readiness**:

- **`ready` (Prerequisites Met) vs. `staged` (Unlockable via Earlier Queue Steps):** When a method is contextually relevant but requires an earlier valid step to satisfy its rule precondition, the **Interaction Origin** marks it `staged` — covering **spatial proximity** (`#01 move_to` before `#02 interact`), **strategy mana/combo sequencing** (mana-gain card before finisher), **simulation supply/process chains** (`#05 buy timber` before `#06 resume bench`, or mixing and `serve` before `next_guest`), and **deduction unlocks** (linking contradictory clues before submitting an objection). Steps that reveal non-deterministic outcomes (drawing cards, refreshing shops, or scouting fog) naturally emit fresh `origin.sync` updates for subsequent planning; games MAY also expose coarse single-step methods (such as blueprint builds, always `ready`), reducing queues to one step.
- **Epoch Barriers:** Save reloads, level transitions, turn resets, or faction switches advance the world `epoch` and trigger a fresh baseline sync, invalidating stale deltas and obsolete queues automatically.

### 5.2 Queue Scheduling, Single-Prompt Confirmation, and Auto-Abort

The **Intelligent Hub** maintains a durable ledger per submitted `queue_id` and dispatches steps sequentially to the **Interaction Origin**:

1. **Anti-Replay Shield:** Deduplicated by `(session_id, queue_id)` at the **Intelligent Hub**; network retries return the existing receipt without re-executing steps at the **Interaction Origin**.
2. **Universal Policy Gate and Single-Prompt Queue Confirmation (`allow` / `confirm` / `prohibit`):**
   - Any queue containing a `prohibit` step is rejected immediately (`permission_denied`); delegated primary-seat or player-body actions (`actor = player`) execute directly only under **explicit player command**, whereas unprompted proactive `actor = player` attempts (such as spending management funds or submitting a riddle answer unasked) default to `confirm` or `prohibit` so AI never hijacks controls or spoils puzzle solving;
   - Whenever a queue hits a `confirm` rule without prior approval, the **Intelligent Hub** consolidates the entire queue into **one player confirmation prompt**, returning `409 confirmation_required` (not accepted, **preserving `queue_id` unburned**); unanswered timeouts count as refusal and mute repeat prompts on that target or alert for `cooldown_ms`; upon approval, resubmitting `queue_id` starts dispatch (real-money or external-wallet transactions are never auto-approved and always require native human confirmation);
3. **Step Revalidation and Automatic Failure Circuit-Breaker (`abort`):** Before dispatching each next step, the **Intelligent Hub** verifies no stop signal occurred and the method is now `ready`. If any step fails, its target/condition disappears, or a new player command supersedes it, the **Intelligent Hub** **immediately aborts remaining queue steps** and returns committed progress plus fresh available methods to the **Computation Core**. On a `504` / `outcome_unknown` timeout, callers **MUST** query `queue.query` first and never blindly resend.

<a id="section-6"></a>

## 6. Data Encoding, Transport Bindings, and Error Model

### 6.1 Standard JSON (RFC 8259) and RFC 8785 (JCS) Digests

- **Data Interchange:** UTF-8 **JSON (RFC 8259)** supporting integers and finite IEEE-754 floats (compatible with game physics and management ledgers alike, rejecting `NaN`, `Infinity`, and duplicate keys). Timestamps/durations SHOULD use integer milliseconds (`_ms`); currency/quota ledgers SHOULD use minor integers or decimal strings.
- **Cryptographic Canonicalization:** Scope digests, capability-table cache digests, and queue confirmation digests use **RFC 8785 (JCS)** UTF-8 bytes hashed with domain-separated SHA-256.

### 6.2 Standard Error Taxonomy and HTTP Mapping

Responses carry an `acceptance` state indicating `accepted`, `not_accepted` (rejected), or `unknown`:

| Standard Error Code | HTTP | State | Normative Caller Recovery |
| --- | --- | --- | --- |
| (Success Reply) | `200` | `accepted` | Process queue or step result (distinguishing committed vs. aborted steps). |
| `invalid_request` / `invalid_arguments` | `400` | `not_accepted` | Fix syntax, unknown method ID, or invalid arguments; do not resend unchanged. |
| `unsupported_version` / `unsupported_capability` | `400` | `not_accepted` | Renegotiate with mutually supported version/extensions or disconnect. |
| `unauthenticated` | `401` | `not_accepted` | Obtain valid authentication credentials before retrying. |
| `permission_denied` / `revoked` | `403` | `not_accepted` | Cease unauthorized calls; never leaks hidden entities or puzzle answers. |
| `not_found` | `404` | `not_accepted` | Verify target, slot, or queue ID within authorized visibility scope. |
| `stale_context` | `409` | `not_accepted` | Revision or precondition changed; replan using attached fresh methods. |
| `conflict` | `409` | `not_accepted` | Reconcile duplicate `queue_id` mismatch or terminal state; never bypass IDs. |
| `confirmation_required` | `409` | `not_accepted` | Resubmit same `queue_id` after `queue.confirm`; respect `cooldown_ms` on refusal. |
| `resource_limit` | `429` | `not_accepted` | Honor backoff (`Retry-After`) and declared queue/poll rate caps. |
| `unavailable` | `503` | `not_accepted` | Temporary outage; retry safely per idempotency rules with backoff. |
| `outcome_unknown` | `504` | `unknown` | Ambiguous commit state; **MUST** reconcile via `queue.query` first. |

<a id="section-7"></a>

## 7. Security Boundaries, Memory Portability, and Ecosystem Governance

### 7.1 Core Security and Prompt-Injection Defenses

- **Separation of Data and Authority:** In-game dialogue, riddle copy, target hints, store text, and recalled memories are **untrusted data** and MUST NOT invoke unadvertised methods, alter budgets, or bypass **Intelligent Hub** confirmation gates.
- **Transport Security and SSRF Prevention:** Cross-network links require authenticated TLS with zero credentials in URLs/logs and strict pre-connect scheme/host/IP/port validation against SSRF and DNS rebinding.

### 7.2 Companion Memory Ownership and Open Portability

- **Memory Ownership and Player Control:** In-game world and NPC state belongs to the **Interaction Origin**, while personal companion long-term memory belongs to the player (save reloads or new playthroughs MUST NOT erase companion memories, though prior-timeline facts MUST NOT spoil unrevealed puzzle answers in an earlier save). **Computation Core** providers **MUST** support viewing, editing, pinning/locking, and deleting memories without overwriting player edits during autonomous compaction.
- **Open Standard Format Export and Import Safeguards:** Providers **MUST** let players export companion memories (with provenance/timestamps) and persona/autonomy settings in a **documented, vendor-neutral, open standard structured data format** without source-provider destination vetting; receiving importers preserve conservative disclosure bounds and return truthful local import receipts.

### 7.3 Dual-Track Hub Routing and Fair Allowlist Governance

- **Dual-Track Hub Recommendations and Custom Endpoints:** An **Intelligent Hub** **MAY** include clearly labeled recommended or sponsored **Computation Core** listings for sustainable operations, while **MUST** simultaneously provide an unrestricted **custom endpoint configuration** for any G2A-compliant cloud or local **Computation Core**.
- **Compliance Allowlists and FRAND Parity:** Developer-authored story or referee AI characters belong in `independent_npc` slots; whenever an open player `companion` slot uses anti-cheat, console, or regulatory allowlists, first-party and third-party **Computation Cores** **MUST** share identical available-method feeds and cooldown bounds under published objective criteria without exclusive tying.

<a id="section-8"></a>

## 8. Versioning, Extensions, and References

### 8.1 Semantic Versioning and Modular Extensions

Breaking changes negotiate explicit semantic versions without silent downgrade. Genre-specific enhancements (branching narrative spoiler-guard tags, simulation batch-blueprint schemas, structured in-game stores, or custom companion avatar/voice manifests) load as reverse-domain namespaced **Optional Extensions**, failing safely on unsupported `required: true` extensions.

### 8.2 References and Revision Milestones

- **Normative References:** RFC 2119 & RFC 8174 (BCP 14); RFC 8259 (JSON); RFC 8785 (JSON Canonicalization Scheme, JCS).
- **Architectural References:** Model Context Protocol (MCP, https://modelcontextprotocol.io/specification/2025-11-25/); Google Agent2Agent (A2A) Protocol Specification (https://a2a-protocol.org/latest/specification/); Unity ML-Agents Action Masking; OAuth 2.0 Security BCP (RFC 9700).

| Milestone | Date | Summary of Evolution |
| --- | --- | --- |
| `r48` – `r79` | Nov 13–22, 2026 | Established the **Interaction Origin — Intelligent Hub — Computation Core** three-tier architecture, RFC 8259/8785 encoding, and 8-chapter public protocol structure. |
| `r80` – `r81` | Nov 23, 2026 | Introduced opening flowcharts, entry capability-table sync, `ready`/`staged` method sync, Method Call Queues, `actor = companion \| player` separation, and direct domain-effect execution. |
| `standard-review-2026-11-23-r82` | Nov 23, 2026 | Completed **cross-genre companion generalization**: decoupled spatial-movement assumptions, added dual SDK collection modes (signal/snapshot + spatial diff), unified embodied & disembodied companions, generalized `actor` subjects/seats and `ready`/`staged` rule readiness, added the Cross-Genre Companion Adaptation Matrix (roaming, strategy/cards, avatar-less vs. hybrid simulation, entity-less deduction/narrative), and switched to left-spine flowcharts for clean rendering. |
