# G2A Specification

**Game-to-Agent Interaction Protocol**

An open protocol standard defining state perception, authorization control, and action execution between games and AI agents across a three-tier architecture: **Interaction Origin**, **Intelligent Hub**, and **Computation Core**.

Status: Working Draft for Public Review (`standard-review-2026-11-22-r79`) | Revision Date: November 22, 2026 | Language Pair: [中文协议规范](G2A_SPECIFICATION.zh-CN.md)

## Architecture Overview and Core Interaction Cases

### Three-Tier Architecture Flowchart

G2A enables any game to introduce AI roles safely with **minimal engineering effort** — primarily a **Player Companion** accompanying the player, alongside optional **Independent AI NPCs** (such as Bosses or guides). Following the clean layered philosophy of open protocols like MCP and A2A, G2A decouples the system into **Interaction Origin**, **Intelligent Hub**, and **Computation Core**:

```text
                        [ Human Player ]
               ┌────────────────┴────────────────┐
       In-game control / commands        Consent / policy gates / Core choice
               ▼                                 ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Tier 1: Interaction Origin (Minimal Host SDK Bundled with the Game)    │
│  • Exposes thin southbound ports: 1) Authorized state  2) Action exec  │
│  • Owns exclusive final adjudication of physics, visibility & rules    │
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ Southbound Interface (Loopback / Backend HTTP)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Tier 2: Intelligent Hub (Open-Source Security Shield & Routing Nexus)  │
│  • Installed once & shared per PC (single-player) or server-deployed   │
│  • Centralizes auth, scopes, anti-replay dedup, confirm gates & routes │
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ Northbound Interface (G2A HTTPS / Stream)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Tier 3: Computation Core (Cloud or Local Reasoning & Memory Engine)    │
│  • Follows player commands or polls state to plan actions & memory     │
└────────────────────────────────────────────────────────────────────────┘
```

### Case 1: User-Initiated Command — "Open the Chest on the Right"

Inside the game, the player explicitly instructs their companion: `"Open the chest on the right"`. The **Interaction Origin** simply reports the player's command and exposes thin state and execution callbacks; the **Computation Core** queries the current view to locate the chest and submits an action request; and the **Intelligent Hub** enforces permissions and anti-replay deduplication so the game executes the action at most once:

```python
# =========================================================================
# Case 1: User explicitly commands companion — "Open the chest on the right"
# =========================================================================

# 1. [Interaction Origin] Game exposes minimal southbound state, event & execution hooks
def on_player_speak(player_id, text="Open the chest on the right"):
    hub.origin_player_event(seat=player_id, kind="player_command", text=text)

def origin_state(player_id):                    # Southbound state port: visible entities
    return {"revision": 12, "entities": [
        {"id": "chest_right_01", "kind": "chest", "pos": "right_2m", "state": "closed"}
    ]}

def origin_execute(action, args):               # Southbound exec port: game physics/range
    if action == "open_container" and world.can_interact(args["target_id"]):
        loot = world.open_chest(args["target_id"])
        return {"state": "succeeded", "effect": "committed", "loot": loot}
    return {"state": "failed", "effect": "none", "reason": "out_of_range_or_opened"}


# 2. [Computation Core] Receive player command -> query view -> submit unique action ID
def on_hub_event(event):
    if event.kind == "player_command":
        view = hub.observation_query(category="visible_entities")
        chest = find_entity(view.entities, kind="chest", pos="right", state="closed")

        res = hub.action_request(
            action_id="act-cmd-open-chest-01",  # Fixed ID prevents double-execution on retry
            action="open_container",
            args={"target_id": chest.id},
            trigger="player_command",
            based_on_revision=view.revision
        )
        if res.state == "succeeded":            # Report only after authoritative commit
            hub.chat_send(text=f"Opened the chest on the right! Loot: {res.loot}")


# 3. [Intelligent Hub] Verify online & scope + block network replays + call Origin once
def hub_handle_action(session, req):
    verify_online_and_scope(session, action=req.action)
    if dedup_ledger.has(session.id, req.action_id):
        return dedup_ledger.get_receipt(session.id, req.action_id)  # Intercept replay

    dedup_ledger.mark_pending(session.id, req.action_id)
    outcome = origin_http.post("/origin.execute", action=req.action, args=req.args)
    return dedup_ledger.commit(session.id, req.action_id, outcome)
```

### Case 2: Companion Periodic State Query and Proactive Action — "Open the Chest on the Right"

Without any direct command from the player, the companion **periodically polls world state**, spots an unopened chest on the right, and **proactively forms the intent** to open it. Notice that **the Interaction Origin requires zero code changes**, while the **Intelligent Hub** enforces online-presence checks, rate limits, and confirmation policy gates — issuing a non-burning confirmation challenge (with an anti-spam cooldown on refusal) when required, or executing directly when standing auto-explore authority is active:

```python
# =========================================================================
# Case 2: Companion periodically queries world state & proactively opens chest
# =========================================================================

# 1. [Computation Core] Periodically poll state -> spot chest -> propose proactive action
def companion_periodic_loop(interval_ms=2000):
    while session.is_active():
        view = hub.observation_query(category="visible_entities")   # Stateless read-only poll
        chest = find_entity(view.entities, kind="chest", pos="right", state="closed")

        if chest and not cooldown_guard.is_muted(chest.id):
            act_id = f"act-auto-open-{chest.id}"
            res = hub.action_request(
                action_id=act_id,
                action="open_container",
                args={"target_id": chest.id},
                trigger="companion_proactive",  # Marked as companion-initiated intent
                based_on_revision=view.revision
            )
            # If policy gate requires player confirmation: resubmit same act_id on approval
            if res.error_code == "confirmation_required":
                if wait_player_confirm(act_id, deadline_ms=res.expires_at_ms):
                    res = hub.action_request(
                        action_id=act_id,
                        action="open_container",
                        args={"target_id": chest.id},
                        trigger="companion_proactive",
                        based_on_revision=view.revision
                    )
                else:
                    cooldown_guard.mute(chest.id, duration_ms=res.cooldown_ms)

            if res.state == "succeeded":
                hub.chat_send(text=f"Spotted a chest on the right and picked up: {res.loot}")

        sleep_ms(interval_ms)


# 2. [Intelligent Hub] Enforce online presence, rate limits & non-burning confirm gate
def hub_handle_proactive_action(session, req):
    verify_online_and_scope(session, action=req.action)
    if policy_gate(session, req) == "confirm" and not confirm_store.approved(req.action_id):
        consent_ui.ask(req.action_id, text="Companion found a chest on the right. Open?", ttl_ms=15000)
        return Error(code="confirmation_required", outcome="not_accepted", cooldown_ms=60000)

    confirm_store.consume_once_if_present(req.action_id)
    return hub_handle_action(session, req)      # Reuse Case 1 anti-replay & single dispatch

# 3. [Interaction Origin] Zero code changes! Reuses Case 1's origin_state & origin_execute
```

## Contents

1. [Introduction and Guiding Principles](#section-1)
2. [Three-Tier Architecture and Deployment Topologies](#section-2)
3. [Standardized Interfaces and Protocol Primitives](#section-3)
4. [Identity, Authorization, and Presence Lifecycle](#section-4)
5. [Observations, Action State Machine, and Anti-Replay](#section-5)
6. [Data Encoding, Transport Bindings, and Error Model](#section-6)
7. [Security Boundaries, Memory Portability, and Ecosystem Governance](#section-7)
8. [Versioning, Extensions, and References](#section-8)

<a id="section-1"></a>

## 1. Introduction and Guiding Principles

### 1.1 Goals and Scope

G2A (Game-to-Agent Interaction Protocol) is an open communication protocol standardizing game-state perception, player-governed authorization, bounded in-game actions, and role dialogue between games and AI agents.

- **In Scope:** Cross-game Player Companions, game-defined Independent AI NPCs (such as Bosses, tactical teammates, or guides), authorized game-state observations, and rule-bounded in-game actions.
- **Out of Scope:** G2A is **not** an operating-system screen-scraping or raw keyboard/mouse injection tool, and does not standardize arbitrary remote code execution, internal LLM weights/prompts, or private commercial revenue-sharing contracts.

### 1.2 Five Guiding Principles

1. **Minimal Origin, Authoritative Game World:** The game host supplies authorized state and adjudicates action outcomes under game physics and rules without implementing complex auth or deduplication state machines.
2. **Centralized Security and Anti-Replay at the Hub:** Authentication, scope enforcement, confirmation gates, rate limits, and duplicate-request interception are consolidated inside an open-source, auditable **Intelligent Hub**.
3. **Support Is Not Authorization; Stop When Offline:** Advertising a capability confers zero access without an active player-approved grant; once associated human players go offline, AI agents MUST NOT continue running in an empty game world.
4. **Acceptance Is Not World Execution:** Queuing a request at the **Intelligent Hub** (`pending`) never proves world execution at the **Interaction Origin** (`committed`); ambiguous timeouts (`unknown`) require status query first and default to no blind resend.
5. **Open Interoperability and Player Data Sovereignty:** G2A remains neutral across game engines and foundation models; personal companion memories remain separate from single-run save reloads and exportable in an open standard format.

### 1.3 Normative Conventions

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**, and **MAY** are interpreted per RFC 2119 and RFC 8174 (BCP 14). The opening flowchart and pseudocode cases are explanatory illustrations and do not mandate a specific programming-language syntax.

<a id="section-2"></a>

## 2. Three-Tier Architecture and Deployment Topologies

### 2.1 Core Responsibilities of the Three Tiers

G2A separates game-engine hooks, security/routing governance, and cognitive reasoning into three clean tiers:

| Canonical Tier | Architectural Role | Responsibility Boundary |
| --- | --- | --- |
| **Interaction Origin** (`Origin`) | Game host & bundled lightweight SDK | Sole authoritative source of world state and action outcomes. Exposes thin southbound HTTP state and execution callbacks exclusively to its paired **Intelligent Hub**; unrevealed game secrets (hidden cards, fog-of-war ambushes, puzzle solutions) **MUST** remain internal and never be exported. |
| **Intelligent Hub** (`Hub`) | Open-source security shield & routing nexus | Protocol engine bridging **Interaction Origin** and **Computation Core** (with reference source code published openly). Enforces discovery, player consent gates, session leases, anti-replay deduplication, dual-track provider routing, and multi-client sync without overriding game rules or forging consent. |
| **Computation Core** (`Core`) | Cloud or local reasoning & memory engine | Cognitive service authorized to drive a bound in-game role slot. Consumes normalized observations and proposes actions or dialogue through the **Intelligent Hub** without custom per-engine glue code. |

### 2.2 Single-Player and Online Game Topologies

The identical three-tier model adapts across single-player desktop/mobile games and server-authoritative online games without changing protocol semantics:

| Deployment Model | Tier Placement | Runtime & Distribution Characteristics |
| --- | --- | --- |
| **Single-Player / Client-Hosted Mode** | Local game **Interaction Origin** ↔ Globally shared PC **Intelligent Hub** ↔ Cloud or local **Computation Core** | Games ship **only the tiny Interaction Origin SDK**. Each player PC installs **one globally shared Intelligent Hub** reused across all compatible local games (downloaded on demand on first launch rather than duplicated per game). Loopback HTTP adds sub-millisecond overhead. |
| **Server-Authoritative Online Game Mode** | Game-server **Interaction Origin** ↔ Backend **Intelligent Hub** ↔ Cloud **Computation Core** | Player PCs run ordinary game clients with zero local AI components; **Interaction Origin** and **Intelligent Hub** run in the server backend. In a co-op dungeon raid, the backend **Intelligent Hub** aggregates authorized team views, manages high-concurrency deduplication, and coordinates unified **Computation Core** decisions so all teammates experience synchronized AI reactions while keeping personal companions and rival factions isolated. |
| **NAT-Friendly Outbound Mode** | Client **Intelligent Hub** (outbound) ↔ Cloud Relay / **Computation Core** | Client-side **Intelligent Hubs** behind home firewalls initiate outbound encrypted connections or pair via an outbound relay without opening inbound ports on the player's device. |

<a id="section-3"></a>

## 3. Standardized Interfaces and Protocol Primitives

G2A divides its wire surface into an ultra-thin **Southbound Host Interface** for game developers and a clean **Northbound Protocol Interface** for cognitive services.

### 3.1 Southbound Interface (`Interaction Origin` ↔ `Intelligent Hub`)

The southbound interface operates strictly over local loopback (`127.0.0.1`) or an isolated backend network, never exposed directly to the public internet. Game studios implement just four minimal primitives:

| Southbound Primitive | Direction | Purpose |
| --- | --- | --- |
| `origin.manifest` | `Hub` → `Origin` | Read static game declarations: supported role slots (`companion` / `independent_npc` and concurrency caps), observable state categories, and callable action definitions (parameter bounds and risk flags). |
| `origin.state` | Bidirectional (pull or push) | Output authorized game-state snapshots (`snapshot`), incremental updates (`delta`), or invalidations (`retract`) for a bound role perspective. |
| `origin.player_event` | `Origin` → `Hub` | Report verified player-seat signals: player online/offline transitions, explicit chat commands, emergency stop signals, or tracked-target invalidations. |
| `origin.execute` | `Hub` → `Origin` | Execute a single validated action that has already passed **Intelligent Hub** auth, confirmation gates, and anti-replay checks, returning authoritative state (`succeeded` / `failed` / `cancelled`) and world effects. |

### 3.2 Northbound Interface (`Intelligent Hub` ↔ `Computation Core`)

The northbound interface carries cross-network authentication and session governance through four orthogonal primitive groups:

| Primitive Group | Core Operations | Normative Semantics |
| --- | --- | --- |
| **Discovery & Session** | `hub.describe` | Unauthenticated discovery returns minimal instance identity only; authenticated calls return a caller-filtered capability `Descriptor`. |
| | `session.authorize` | Negotiate capability modules and freeze permission `Scope` (bound by an RFC 8785 digest); issue an active `Grant` and `Session` upon verified player consent. |
| | `session.heartbeat` | Renew the **Computation Core** control lease with a fresh nonce (never extends or spoofs an absent player's online presence). |
| | `session.resume` | Rebind session control generation within the permitted recovery window, returning a consolidated snapshot and unresolved action records. |
| | `session.close` | Idempotently close a session or apply permission revocation, fencing new actions and settling in-flight actions truthfully without fabricating rollback. |
| **Observations** | `observation.stream` | Receive ordered authorized state snapshots, deltas, and retractions (via polling or SSE/WebSocket push). |
| | `observation.query` | Stateless read-only pull of current authorized observations (such as Case 2's periodic polling), subject to online presence and rate caps with zero world side effects. Structured state is mandatory; visual (`visual`) and game-audio (`audio`) feeds are orthogonal optional modules with independent runtime player toggles. |
| **Actions** | `action.request` | Propose an action carrying a unique `action_id`, typed arguments, and referenced observation revision; returns `confirmation_required` when unconfirmed policy gates apply, otherwise queues for execution. |
| | `action.confirm` | Record single-use player approval via the authenticated consent channel bound to exact action digest, consequences, and expiry. |
| | `action.cancel` | Request cancellation of an undispatched `pending` action or a game-cancellable `executing` action. |
| | `action.query` | Query persistent `ActionRecord` status for post-timeout or post-disconnect reconciliation. |
| **Dialogue** | `chat.send` | (Optional module) Send text or voice dialogue bounded by recipient audience and provenance tags (observed fact, player statement, or model inference). |

<a id="section-4"></a>

## 4. Identity, Authorization, and Presence Lifecycle

### 4.1 Authentication, Frozen Scopes, and Revocation

- **Transport-Authenticated Identity:** Caller identity **MUST** be established from transport credentials (verified local OS IPC or TLS + cryptographic tokens/delegations), never from self-asserted payload fields alone.
- **Frozen Permission Scope (`Scope`):** Every session grant binds the RFC 8785 digest of the player, **Computation Core**, game instance, role slot, and permitted observation/action sets. Capability updates at the **Interaction Origin** never automatically expand existing grants; broader access always requires fresh player approval.
- **Immediate Revocation Fencing:** Players or games may revoke a session or specific capability at any time; revocation takes effect immediately at the **Intelligent Hub**, blocking undispatched `pending` actions from reaching the **Interaction Origin**.

### 4.2 Mandatory Offline Stop and Two-Tier Interruption Recovery

- **No Offline Background Play:** G2A **MUST NOT** provide any mode where AI agents continue acting in an empty game world after associated human players disconnect. Upon player exit or offline detection at the **Interaction Origin**, the **Intelligent Hub** **MUST** halt observation polling and new actions immediately and cancel undispatched `pending` requests, while already `executing` in-world actions finish naturally under game rules. Upon later game re-entry, prior tasks stay stopped awaiting a fresh player command.
- **Two-Tier Recovery During Active Play:** If the **Computation Core** disconnects while the player stays online, gameplay continues (with stationary or clearly attributed local game-script fallback, and zero backfill recording of disconnected play):
  1. **Brief Blip Within Active Lease (Before Fallback Takeover):** May seamlessly resume via `session.resume`, refreshing the snapshot and reconciling in-flight actions without interrupting combat;
  2. **Extended Outage or Post-Fallback Takeover:** Reconnection **MUST** keep companion actions paused at the **Intelligent Hub** until the player explicitly confirms continuation.

### 4.3 Role Slot Isolation and Configurable Cost Sponsorship

- **Declared Role Slots:** Games declare support for `companion` (default max one per authenticated player, with normal play when left empty), `independent_npc`, or coexisting slots in `origin.manifest`, enforcing strict per-role isolation of views, memories, permissions, and billing.
- **Consumption Caps and AI NPC Billing Models:**
  - Player-metered companion services **MUST** support explicit consumption caps that pause AI inference upon exhaustion without interrupting gameplay.
  - Independent AI NPCs (such as Bosses or guides) support configurable sponsorship modes declared by the game: **defaulting to Player-Metered Mode (`player_metered`)** (bound to the authenticated owning player or room host with zero silent cost-splitting to other players; if the host disconnects, host billing stops immediately and the encounter follows its declared rule: clean stop, local **Interaction Origin** script fallback, or privacy-isolated explicit reassignment to another consenting teammate), alongside **Developer-Sponsored Mode (`developer_sponsored`)** (continuing for remaining online players until all human players leave).

<a id="section-5"></a>

## 5. Observations, Action State Machine, and Anti-Replay

### 5.1 Observation Baselines, Deltas, and Epoch Barriers

Authorized observation streams progress within monotonic world epochs (`world_epoch`), visibility epochs (`visibility_epoch`), and revisions (`revision`):

- **`snapshot` (Baseline):** Atomically replaces the authorized view for the current epoch; save reloads, world resets, or faction switches **MUST** advance the epoch and emit a fresh `snapshot`, automatically invalidating delayed older packets.
- **`delta` (Incremental Update):** Applies additions/updates and reason-tagged removals (`left_view` vs. `destroyed`, preventing fog-of-war exit from being misread as death) against an exact base revision, triggering snapshot resync on mismatch.
- **`retract` (Invalidation Barrier):** Immediately withdraws specified records or an entire stream so delayed packets cannot resurrect revoked state.

### 5.2 Action State Machine, Universal Policy Gates, and Anti-Replay

Each action maintains a persistent `ActionRecord` at the **Intelligent Hub** pairing lifecycle state (`pending`, `executing`, `succeeded`, `failed`, `cancelled`, `unknown`) with world effect (`none`, `partial`, `committed`, `undetermined`):

1. **Intelligent Hub Anti-Replay Shield:** The **Intelligent Hub** deduplicates action requests deterministically by `(session_id, action_id)`. Network retries carrying identical parameters return the cached receipt without ever invoking `origin.execute` a second time at the **Interaction Origin**; altered parameters under the same `action_id` fail with `conflict`.
2. **Universal Three-State Action Policy Gate (`allow` / `confirm` / `prohibit`):** Proactive companion initiatives (such as Case 2's chest opening), high-value item transfers, irreversible story triggers, and virtual-currency budget thresholds all resolve through one uniform policy gate at the **Intelligent Hub**:
   - **`prohibit`:** Rejected immediately with `permission_denied`;
   - **`confirm`:** Without a matching unexpired `action.confirm`, the **Intelligent Hub** returns `409 confirmation_required` (`outcome: not_accepted`, **preserving `action_id` unburned**) and prompts the player; unanswered timeouts count as refusal and enforce a declared `cooldown_ms` anti-spam window; upon player approval, resubmitting the original `action_id` atomically consumes the confirmation and dispatches execution (note: real-money or external-wallet transactions are **never** eligible for autonomous budgets and always require native human confirmation);
   - **`allow`:** Validates that the referenced observation revision is still fresh (returning `stale_context` otherwise) and dispatches once to the **Interaction Origin**.
3. **Three-Stage Emergency Stop and Timeout Reconciliation:** On a player stop or superseding command, unsubmitted **Computation Core** plans are discarded, undispatched `pending` requests are cancelled at the **Intelligent Hub**, and already `executing` actions settle under game physics. On a `504` / `outcome_unknown` timeout, callers **MUST** query `action.query` for the original `action_id` first and default to no automatic resend or ID substitution.

<a id="section-6"></a>

## 6. Data Encoding, Transport Bindings, and Error Model

### 6.1 Standard JSON (RFC 8259) and RFC 8785 (JCS) Digests

- **Data Interchange:** Payloads use standard UTF-8 **JSON (RFC 8259)** supporting integers and finite IEEE-754 floating-point numbers (natively compatible with game-engine coordinates and physics), strictly rejecting `NaN`, `Infinity`, and duplicate keys. Timestamps and durations SHOULD use integer milliseconds (`_ms`); currency and quota ledgers SHOULD use minor integer units or decimal strings.
- **Cryptographic Canonicalization:** Scope and confirmation digests use **RFC 8785 (JSON Canonicalization Scheme, JCS)** UTF-8 bytes hashed with domain-separated SHA-256, compatible with off-the-shelf JCS libraries in every major language.

### 6.2 Standard Error Taxonomy and HTTP Mapping

Northbound responses return structured JSON envelopes correlated by `request_id` and mapped deterministically onto standard HTTP status codes:

| Standard Error Code | HTTP Status | Acceptance | Normative Caller Recovery |
| --- | --- | --- | --- |
| (Success Reply) | `200` | `accepted` | Process result (`action.query` results truthfully report `succeeded` / `failed` / `unknown` execution). |
| `invalid_request` / `invalid_arguments` | `400` | `not_accepted` | Fix malformed syntax or out-of-bounds parameters; do not resend unchanged. |
| `unsupported_version` / `unsupported_capability` | `400` | `not_accepted` | Renegotiate with mutually supported version/modules or disconnect. |
| `unauthenticated` | `401` | `not_accepted` | Obtain valid authentication credentials before retrying. |
| `permission_denied` / `revoked` | `403` | `not_accepted` | Cease unauthorized or revoked calls; never leaks existence of hidden entities. |
| `not_found` | `404` | `not_accepted` | Verify target identifier within authorized visibility scope. |
| `stale_context` | `409` | `not_accepted` | Observation epoch or baseline expired; refresh state and reassess rather than retrying blindly. |
| `conflict` | `409` | `not_accepted` | Reconcile duplicate-ID payload mismatch or terminal state; never invent bypass IDs. |
| `confirmation_required` | `409` | `not_accepted` | Resubmit same `action_id` after `action.confirm`; respect `cooldown_ms` on refusal/timeout. |
| `resource_limit` | `429` | `not_accepted` | Honor backoff (`Retry-After`) and declared rate/concurrency quotas. |
| `unavailable` | `503` | `not_accepted` | Temporary service outage; retry safely per idempotency rules with backoff. |
| `outcome_unknown` | `504` | `unknown` | Ambiguous commit state; **MUST** reconcile via `action.query` first and never auto-resend effects. |

<a id="section-7"></a>

## 7. Security Boundaries, Memory Portability, and Ecosystem Governance

### 7.1 Core Security and Prompt-Injection Defenses

- **Strict Separation of Data and Authority:** In-game dialogue, item descriptions, store copy, and recalled memories are **untrusted data** and MUST NOT elevate session permissions, alter spending caps, or bypass **Intelligent Hub** confirmation gates.
- **Transport Security and SSRF Prevention:** Cross-network links require authenticated TLS with zero credentials in URLs or logs; all external URLs and redirects enforce pre-connect scheme, host/IP, and port validation to block private-network probing and DNS rebinding.

### 7.2 Companion Memory Ownership and Open Portability

- **Memory Ownership and Player Control:** In-game NPC state belongs to the **Interaction Origin**, whereas personal companion long-term memory belongs to the player (save reloads or new playthroughs MUST NOT silently erase companion memories). **Computation Core** providers **MUST** let players view, edit, pin/lock, and delete retained memories; autonomous memory compaction MUST never overwrite player edits or delete pinned records.
- **Open Standard Format Export and Import Safeguards:** Providers **MUST** let players export retained companion memories (with provenance and timestamps) and persona/autonomy settings in a **documented, vendor-neutral, open standard structured data format**. Source providers verify only player identity and **MUST NOT** vet or restrict the destination; receiving **Computation Cores** that support import preserve provenance and conservative disclosure bounds (never expanding disclosure to games or third parties upon switching) and return truthful local import receipts (`imported`, `transformed`, `rejected`, or `unresolved`).

### 7.3 Dual-Track Hub Routing and Fair Allowlist Governance

- **Dual-Track Hub Recommendations and Custom Endpoints:** An **Intelligent Hub** **MAY** feature a curated or commercially sponsored **Computation Core** directory (transparently labeled) for sustainable commercialization, while **MUST** simultaneously provide an unrestricted **custom endpoint configuration** so players can connect any G2A-compliant third-party cloud or local **Computation Core** without hub lock-in.
- **Compliance Allowlists and FRAND Parity:** Bespoke story-specific AI characters authored by a game developer belong in `independent_npc` slots and need not accept third-party replacement. Conversely, whenever a game exposes an open player `companion` slot and applies anti-cheat, console-certification, or regulatory allowlists, first-party and third-party **Computation Cores** **MUST** share identical capability, visibility, and cooldown bounds under published objective criteria without exclusive tying or cloud/revenue lock-in.

<a id="section-8"></a>

## 8. Versioning, Extensions, and References

### 8.1 Semantic Versioning and Modular Extensions

Breaking semantic changes require explicit protocol version negotiation during session establishment without silent downgrade. Genre-specific capabilities (such as narrative branch timeline tags, structured in-game store catalogues, or custom companion avatar asset manifests) are negotiated as reverse-domain namespaced **Optional Extensions**; unsupported `required: true` extensions fail cleanly during authorization so the core protocol stays lean and durable.

### 8.2 References and Revision Milestones

- **Normative References:** RFC 2119 & RFC 8174 (BCP 14 Requirement Keywords); RFC 8259 (JSON Data Interchange Format); RFC 8785 (JSON Canonicalization Scheme, JCS).
- **Architectural References:** Google Agent2Agent (A2A) Protocol Specification (https://a2a-protocol.org/latest/specification/); Model Context Protocol (MCP, https://modelcontextprotocol.io/specification/2025-11-25/); OAuth 2.0 Security Best Current Practice (RFC 9700).

| Milestone | Date | Summary of Evolution |
| --- | --- | --- |
| `r48` – `r74` | Nov 13–22, 2026 | Initial bilingual draft baselines exploring permissions, observation streams, action state machines, and memory portability. |
| `r75` – `r78` | Nov 22, 2026 | Established the **Interaction Origin — Intelligent Hub — Computation Core** three-tier architecture, RFC 8259/8785 encoding, dual-track Hub routing, FRAND allowlist parity, and opening flowchart + dual pseudocode walkthroughs. |
| `standard-review-2026-11-22-r79` | Nov 22, 2026 | Benchmarked against A2A and MCP public specifications to consolidate 25 fragmented chapters into a cohesive 8-chapter open protocol standard centered on the three-tier architecture and clean southbound/northbound primitives. |
