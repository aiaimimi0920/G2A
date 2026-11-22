# G2A Specification

**Game-to-Agent Interaction Protocol**

An open rule standard defining identity, observation, authorization, and action boundaries across **Interaction Origins**, **Intelligent Hubs**, and **Computation Cores**.

Status: Working Draft for Public Review. Editorial revision: `standard-review-2026-11-22-r78`. Revision date: November 22, 2026.
Document role: Normative protocol rule specification defining the three-tier G2A architecture (**Interaction Origin**, **Intelligent Hub**, and **Computation Core**). Concrete language APIs, machine schemas, and open-source SDK packages are delivered separately.

Language pair: this English master and the [complete Chinese specification](G2A_SPECIFICATION.zh-CN.md) share the same editorial revision and normative structure. See [Section 25](#section-25) for traceable revision history.

## Architecture Overview and Core Interaction Cases

### Three-Tier Architecture Flowchart

G2A enables any game to integrate AI roles safely with **minimal studio engineering effort** — primarily a **Player Companion** accompanying the player, alongside optional **Independent AI NPCs** (such as Bosses or guides). The system decouples strictly into three canonical tiers — **Interaction Origin**, **Intelligent Hub**, and **Computation Core**:

```text
                        [ Human Player ]
               ┌────────────────┴────────────────┐
       In-game control / commands        Consent / policy gates / Core choice
               ▼                                 ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Tier 1: Interaction Origin (Minimal Host SDK Bundled with the Game)    │
│  • Exposes only two thin ports: 1) Authorized state  2) Action exec    │
│  • Owns exclusive final adjudication of physics, visibility & rules    │
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ Southbound HTTP (Loopback / Backend LAN)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Tier 2: Intelligent Hub (Open-Source Security Shield & Routing Nexus)  │
│  • Installed once & shared per PC (single-player) or server-deployed   │
│  • Enforces auth, scopes, anti-replay dedup, confirm gates & routing   │
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ Northbound G2A Protocol (HTTPS / Stream)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Tier 3: Computation Core (Cloud or Local Reasoning & Memory Engine)    │
│  • Follows player commands or polls state to plan actions & memory     │
└────────────────────────────────────────────────────────────────────────┘
```

Three core power boundaries govern every G2A interaction:

1. **The Interaction Origin owns world truth and final execution:** The game supplies state data and action callbacks only; security validation, anti-replay filtering, and provider routing are handled entirely by the **Intelligent Hub**.
2. **The Player governs authorization, policies, and Core selection:** The player decides whether a companion connects, which **Computation Core** is used, what permissions it receives, and when proactive or high-impact actions require confirmation.
3. **The Computation Core focuses on reasoning and portable memory:** One unified protocol supports both **explicit player commands** and **proactive companion assistance driven by periodic state queries**, illustrated by the two end-to-end pseudocode walkthroughs below.

### Case 1: User-Initiated Command — "Open the Chest on the Right"

**Scenario Goal:** Inside the game, the player explicitly tells their companion: `"Open the chest on the right"`. Driven by **verified player intent**, the **Interaction Origin** simply forwards the player's utterance and exposes minimal state/action ports; the **Computation Core** queries the current view to locate the right-hand chest and submits an action request; and the **Intelligent Hub** verifies permissions and blocks duplicate network retries so the chest opens once, before the companion reports the verified loot.

```python
# =========================================================================
# Case 1: User explicitly commands companion — "Open the chest on the right"
# =========================================================================

# 1. [Interaction Origin] Game exposes minimal southbound state & action ports only
def on_player_speak(player_id, text="Open the chest on the right"):
    # Forward verified player speech to Intelligent Hub with authentic provenance
    hub_southbound.player_chat_forward(seat=player_id, provenance="player_statement", text=text)

def http_get_visible_state(player_id):
    # Southbound state port: return authorized visible entities and current revision
    return {
        "revision": 12,
        "entities": [
            {"id": "chest_right_01", "kind": "chest", "relative_pos": "right_2m", "state": "closed"}
        ]
    }

def http_execute_action(action, args):
    # Southbound action port: adjudicate range/rules and return world outcome
    if action == "open_container" and game_world.can_interact(args["target_id"]):
        loot = game_world.open_chest(args["target_id"])
        return {"state": "succeeded", "effect": "committed", "loot": loot}
    return {"state": "failed", "effect": "none", "reason": "out_of_range_or_already_opened"}


# 2. [Computation Core] Receive player command -> query view -> submit unique action
def on_hub_event(event):
    if event.type == "player_chat" and event.provenance == "player_statement":
        # Query authorized view to resolve "chest on the right" into chest_right_01
        view = hub_northbound.observation_query(category="visible_entities")
        chest = find_entity(view.entities, kind="chest", direction="right", state="closed")

        res = hub_northbound.action_request(
            action_id="act-cmd-open-chest-01",   # Stable ID prevents double-execution on retry
            action="open_container",
            args={"target_id": chest.id},
            trigger="explicit_player_command",
            based_on_revision=view.revision
        )
        # Report completion only after authoritative Interaction Origin success
        if res.state == "succeeded":
            hub_northbound.chat_send(text=f"Opened the chest on the right! Loot: {res.loot}")


# 3. [Intelligent Hub] Verify grant & online state + block duplicate replays + dispatch once
def hub_on_action_request(session, req):
    verify_player_online_and_scope(session, required_action=req.action)

    # Anti-replay shield: if network jitter sends the same action_id twice, intercept here
    if dedup_ledger.has(session.id, req.action_id):
        return dedup_ledger.get_receipt(session.id, req.action_id)

    dedup_ledger.mark_pending(session.id, req.action_id)
    outcome = origin_http.post("/execute_action", action=req.action, args=req.args)
    return dedup_ledger.commit_outcome(session.id, req.action_id, outcome)
```

### Case 2: Companion Periodic State Query and Proactive Action — "Open the Chest on the Right"

**Scenario Goal:** Without any direct command from the player, the companion **periodically polls world state** while the player is online, spots an unopened chest on the right, and **autonomously forms the intent** to open it. Notice that **the Interaction Origin requires zero code changes**, while the **Intelligent Hub** enforces online-presence checks, poll rate limits, and the player's proactive confirmation policy — issuing a non-burning **`confirmation_required` challenge** (with an anti-spam cooldown on refusal) when confirmation is required, or executing safely against the bound observation revision when autonomous looting is permitted.

```python
# =========================================================================
# Case 2: Companion periodically queries world state & proactively opens chest
# =========================================================================

# 1. [Computation Core] Periodically poll state -> spot chest -> propose proactive action
def companion_periodic_loop(poll_interval_ms=2000):
    while session.is_active():
        # Stateless read-only poll (immediately rejected by Hub if player goes offline)
        view = hub_northbound.observation_query(category="visible_entities")
        chest = find_entity(view.entities, kind="chest", direction="right", state="closed")

        if chest and not cooldown_guard.is_muted(chest.id):
            act_id = f"act-proactive-open-{chest.id}"
            res = hub_northbound.action_request(
                action_id=act_id,
                action="open_container",
                args={"target_id": chest.id},
                trigger="companion_proactive",   # Marked as companion-initiated intent
                based_on_revision=view.revision  # Rejects if player already opened it
            )

            # Branch A: Player policy requires confirmation before proactive container opening
            if res.error_code == "confirmation_required":
                if wait_player_confirm(action_id=act_id, deadline_ms=res.expires_at_ms):
                    # Resubmit with the exact same act_id (challenge did not burn the key)
                    res = hub_northbound.action_request(
                        action_id=act_id,
                        action="open_container",
                        args={"target_id": chest.id},
                        trigger="companion_proactive",
                        based_on_revision=view.revision
                    )
                else:
                    # Declined or timed out: back off for cooldown_ms without nagging again
                    cooldown_guard.mute(chest.id, duration_ms=res.cooldown_ms)

            # Branch B (standing auto-loot grant) or confirmed Branch A: report real outcome
            if res.state == "succeeded":
                hub_northbound.chat_send(text=f"Spotted a chest on the right and got: {res.loot}")

        sleep_ms(poll_interval_ms)


# 2. [Intelligent Hub] Enforce online presence + rate limits + proactive confirmation gate
def hub_on_proactive_action(session, req):
    verify_player_online_and_scope(session, required_action=req.action)

    # Gate unconfirmed proactive or risky actions before they ever touch Interaction Origin
    if policy_requires_confirm(session, req) and not confirm_store.is_approved(req.action_id):
        player_consent_ui.ask(
            action_id=req.action_id,
            prompt="Companion spotted a chest on the right. Allow opening?",
            expires_in_ms=15000
        )
        # outcome="not_accepted" preserves action_id for clean resubmission upon approval
        return Error(code="confirmation_required", outcome="not_accepted", cooldown_ms=60000)

    confirm_store.consume_once_if_present(req.action_id)
    # Reuse the identical anti-replay ledger and single-call southbound dispatch as Case 1
    return hub_on_action_request(session, req)


# 3. [Interaction Origin] Zero extra code! Reuses Case 1's http_get_visible_state & http_execute_action
```

## Contents

1. [Purpose and Scope](#section-1)
2. [Conventions and Document Authority](#section-2)
3. [Three-Tier Architecture, Topologies, and Applicability](#section-3)
4. [Roles, Identity, and Trust](#section-4)
5. [Canonical Conceptual Model](#section-5)
6. [Abstract Operation Catalogue](#section-6)
7. [Discovery, Negotiation, and Admission](#section-7)
8. [Grants, Sessions, and Revocation](#section-8)
9. [Game Observation Rules](#section-9)
10. [Actions and Effect Semantics](#section-10)
11. [Idempotency, Delivery, and Recovery](#section-11)
12. [Error Model, Time, and Resource Limits](#section-12)
13. [Gameplay Roles and Slot Rules](#section-13)
14. [Presence and Role Lifecycle](#section-14)
15. [Conversation, Information Use, and Companion Memory](#section-15)
16. [Role Autonomy, Confirmation Gates, and Cost Models](#section-16)
17. [Optional Capability Profiles](#section-17)
18. [Transport Binding and Canonicalization Principles](#section-18)
19. [Security and Privacy Considerations](#section-19)
20. [Versioning, Release Governance, and Ecosystem Neutrality](#section-20)
21. [Conformance and Quality Evaluation](#section-21)
22. [Three-Tier SDK Architecture and Shared Hub Distribution](#section-22)
23. [Illustrative End-to-End Scenarios](#section-23)
24. [References](#section-24)
25. [Revision History](#section-25)

<a id="section-1"></a>

## 1. Purpose and Scope

### 1.1 Design Goals and Four Pillars

G2A enables conforming **Interaction Origins**, **Intelligent Hubs**, and **Computation Cores** to interoperate safely across local and cloud environments. The specification is organized around four pillars:

| Pillar | Normative Scope |
| --- | --- |
| Admission and Control | Principal authentication, capability discovery, fair admission governance, player consent, scoped grants, session leases, control handoff, and graded revocation managed at the **Intelligent Hub**. |
| Observations and Information Use | Authorized game-state views from the **Interaction Origin**, snapshots and incremental updates, provenance, freshness, audience boundaries, multimodal feeds, and memory governance. |
| Actions and Outcomes | Role capability declarations, dynamic action eligibility, confirmation challenges, **Intelligent Hub** anti-replay gating, **Interaction Origin** effect-boundary adjudication, cancellation, and outcome reconciliation. |
| Interoperability and Governance | Conceptual protocol model, abstract operations, standard JSON/JCS canonicalization, southbound/northbound HTTP rules, shared **Intelligent Hub** distribution, and conformance suites. |

### 1.2 Core Architectural Distinctions

Five foundational distinctions apply across every tier of this specification:

- **Support is not authorization:** Declaring a capability indicates technical support; submitting a request expresses caller intent. Neither grants read or execution authority without an active player-approved grant and frozen session scope enforced by the **Intelligent Hub**.
- **Acceptance is not completed execution:** Accepting or queuing an action request (`pending`) at the **Intelligent Hub** does not establish that its world effect has occurred at the **Interaction Origin**. Queue acceptance, executor claim (`executing`), and committed world effect (`committed`) MUST remain strictly distinct.
- **Authorized reads do not imply continuing validity:** Observations reflect a restricted perspective at a specific world epoch and revision and become stale as gameplay state or visibility changes.
- **Omission is not non-existence:** Information omitted due to fog-of-war, permission filtering, or incremental compression MUST NOT be interpreted as a false fact, an empty world, or entity destruction.
- **Companion memory is separate from current world state:** Reloading a save, starting a new playthrough, or switching narrative branches alters authoritative state at the **Interaction Origin**, but MUST NOT silently erase player-governed companion memories in the **Computation Core**. Remembering an earlier playthrough does not make an event true in the current world or override game rules.

### 1.3 Scope Boundaries and Non-Goals

G2A is scoped strictly to game interaction: player-companion assistance, authorized AI NPC interaction, game-state observation, constrained in-game actions, and optional companion visual presentation.

G2A is **not** a general-purpose operating-system or desktop UI automation protocol. It does not standardize arbitrary remote code execution, undeclared screen or input capture, model weights, prompt templates, or internal commercial revenue-sharing contracts. While G2A enforces observable data, audience, and action boundaries, no communication protocol can erase prior general knowledge stored in model weights or prevent an endpoint from drawing internal inferences from facts already disclosed to it.

<a id="section-2"></a>

## 2. Conventions and Document Authority

### 2.1 Normative Keywords

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**, and **MAY** in this document are to be interpreted as described in RFC 2119 and RFC 8174 (BCP 14) when, and only when, they appear in all capitals. The opening architecture flowchart and pseudocode walkthroughs, illustrative scenarios (Section 23), and revision notes (Section 25) are explanatory and do not mandate a specific programming-language syntax. A permission expressed with **MAY** does not require every implementation to offer that optional feature.

### 2.2 Document Role and Conformance Scope

This specification is a **protocol rule and boundary standard**, not a language-specific API manual or source-code guide. It defines mandatory trust invariants, state transitions, authority checks, and three-tier architectural rules in implementation-neutral prose.

1. **Separation of Rules from SDK Packages:** Concrete wire-field schemas, engine SDK signatures, and open-source **Intelligent Hub** builds are published as companion deliverables pinned under formal release manifests (Section 20).
2. **Honest Conformance Claims:** Implementations MUST state the exact released G2A version, architectural tier (**Interaction Origin**, **Intelligent Hub**, or **Computation Core**), transport bindings, and optional capability modules they implement, and MUST NOT misrepresent partial draft support as full conformance to a frozen production release.

<a id="section-3"></a>

## 3. Three-Tier Architecture, Topologies, and Applicability

### 3.1 Three-Tier Runtime Architecture and Standardized Interfaces

G2A decouples game-engine integration from security governance and model reasoning across three canonical runtime tiers connected by two standardized interfaces:

1. **Interaction Origin and Southbound Origin-to-Hub HTTP Interface:** A game studio (including teams using custom or newly built engines) integrates only a minimal **Interaction Origin SDK** shipped with the game. It exposes lightweight local or internal-network HTTP ports strictly for **supplying authorized game state** and **executing callable in-game actions with return values**. Once the studio populates the required state responses and action callbacks, integration is complete — the **Interaction Origin** never implements anti-replay ledgers, complex session handshakes, or external routing.
2. **Intelligent Hub (Open-Source Security & Routing Nexus):** Positioned between the **Interaction Origin** and **Computation Core**, the **Intelligent Hub** executes all protocol governance: capability negotiation, player consent gating, **anti-replay and idempotent deduplication** (intercepting duplicate requests such as a twice-sent attack caused by network drops before they ever reach the **Interaction Origin**), session leases, offline fencing, and multi-endpoint routing. Its reference source code is **openly published for audit**. Because southbound HTTP between the **Intelligent Hub** and **Interaction Origin** runs over local loopback or same-datacenter internal networking, the intermediate hop adds only sub-millisecond to single-digit-millisecond overhead — negligible relative to **Computation Core** inference time.
3. **Computation Core and Northbound Hub-to-Core Interface:** Cloud or local **Computation Cores** connect to the **Intelligent Hub** over the standardized northbound G2A protocol (Sections 5–18), consuming normalized observations and submitting typed action or dialogue proposals without custom per-game engine adapters.

### 3.2 Single-Player Client and Online Server Topologies

The same three-tier architecture adapts cleanly to both single-player games and server-authoritative online multiplayer games:

| Deployment Model | Placement of the Three Tiers | Operational Flow & Runtime Distribution |
| --- | --- | --- |
| **Single-Player / Client-Hosted Mode** | Local game **Interaction Origin** ↔ Globally shared PC **Intelligent Hub** ↔ Cloud or local **Computation Core** | Games distribute only the tiny **Interaction Origin SDK**. The player's PC installs **one globally shared Intelligent Hub** reused across all compatible local games (if absent, the **Interaction Origin** triggers a one-time on-demand download rather than bundling duplicate hubs per game). |
| **Server-Authoritative Online Game Mode** | Game-server **Interaction Origin** ↔ Backend **Intelligent Hub** ↔ Cloud **Computation Core** | Player PCs run only ordinary game clients without local AI or SDK exposure. On the server backend (for example, a co-op dungeon raid), the server-side **Intelligent Hub** aggregates authorized team-visible state over internal HTTP, coordinates high-concurrency deduplication and session sync, and routes unified tactical or Boss decisions with the **Computation Core** so all teammates witness strictly synchronized, consistent AI reactions (while preserving per-player isolation for personal companions or rival factions). |
| **NAT-Restricted Outbound Relay Mode** | Client/host **Intelligent Hub** (outbound) → **Paired Outbound Relay** ← Cloud **Computation Core** | When a client-side **Intelligent Hub** behind a home firewall pairs with a remote endpoint without opening inbound ports, it tunnels northbound operations over an Outbound Relay (Section 18.3) while keeping all three-tier boundaries intact. |

### 3.3 Capability Modules and Applicability

Core conformance requires only session management, event/context delivery, and baseline structured perception; all other capabilities are negotiated explicitly according to game design:

| Capability Module | Requirement Tier | Primary Responsibilities |
| --- | --- | --- |
| `core.session` | Mandatory Core | Discovery, capability negotiation, scoped admission, session lease, recovery snapshot, closure, and error reporting. |
| `core.events` | Mandatory Core | Ordered recipient-visible event delivery, context publication, and within-session deduplication. |
| `perception.structured` | Mandatory Core (`Computation Core`) | Interpreting negotiated structured game observations to make authorized role decisions. |
| `observation.query` | Optional | Stateless, authorized **Computation Core** reads of current observations without world side effects (Section 9.6). |
| `perception.visual` | Optional | Game-frame visual perception layered orthogonally atop `perception.structured` (Section 9.5). |
| `perception.audio` | Optional | Game-environment audio perception layered orthogonally atop `perception.structured`, distinct from voice chat (Section 9.5). |
| `actions` | Optional | Typed action requests, confirmation challenges, executor claim, effect-boundary validation, cancellation, and outcome queries (Section 10). |
| `chat` | Optional | Provenance- and audience-bound text or voice communication (Section 15). |
| `team` | Optional | Multi-participant seat bindings, membership revisions, and team-scoped audiences. |
| `resume` | Optional | Durable session ledgers and seamless reconnection within an active lease (Sections 11, 14.2). |
| `handoff` | Optional (requires `resume`) | Generation-fenced transfer of session control across verified devices or processes. |
| `multi-session` | Optional | Concurrent active sessions for the same **Computation Core** identity without silently evicting existing sessions. |
| `avatar` / `assets` / `presentation` | Optional | Companion appearance priority, safe declarative asset resolution, and device rendering leases (Section 17.2). |
| `store` | Optional | Structured in-game store offerings, rate-limited recommendations, and authoritative purchase budgets (Section 17.1). |
| `privacy-request` | Optional | Scoped data-deletion/cutoff requests and truthful custodian receipts (Section 15.4). |

<a id="section-4"></a>

## 4. Roles, Identity, and Trust

### 4.1 Core Trust Principals and Three-Tier Roles

G2A defines the three canonical architectural tiers alongside the human player and four optional supporting roles:

| Role | Category | Authority and Responsibilities |
| --- | --- | --- |
| **Interaction Origin** (`Origin`) | Core Authoritative Tier | The game host and its lightweight SDK (including internal execution logic). Sole authoritative source of world state and action outcomes; exposes minimal southbound HTTP state and action callbacks exclusively to its paired **Intelligent Hub**. |
| **Intelligent Hub** (`Hub`) | Core Security & Routing Tier | The open-source protocol nexus linking **Interaction Origin** and **Computation Core**. Authenticates callers, enforces `Scope`, blocks duplicate/replayed requests, manages session leases, coordinates consent challenges, and routes to selected **Computation Cores** without ever overriding game rules or forging player consent. |
| **Player / `PlayerConsent`** | Core Principal | The human player and the authenticated consent/control path through which the player approves permission offers, confirms high-impact actions, configures companion policies, selects or customizes **Computation Cores**, and revokes access. |
| **Computation Core** (`Core`) | Core Cognitive Tier | Cloud or local reasoning and memory service authorized to drive a bound in-game role (Player Companion or Independent AI NPC). Consumes authorized observations via the **Intelligent Hub** and proposes in-scope actions or dialogue. |
| **Local Runtime Installer / Launcher** | Optional Role | Performs verified on-demand installation of the shared PC **Intelligent Hub** (when not yet present) or starts a pre-registered local binary under explicit user consent without executing untrusted command strings. |
| **Presentation Endpoint** | Optional Role | Manages companion window or overlay rendering leases and safe declarative asset caching on a user device. |
| **Data Custodian** | Optional Role | Any participant (**Computation Core** provider, **Interaction Origin**, or platform) that persists player or companion records and therefore processes scoped privacy/deletion requests for data under its control. |
| **Outbound Relay** | Optional Transport Role | Forwards permitted northbound operations between paired endpoints when a client **Intelligent Hub** does not expose an inbound port, without holding administrative authority. |

Closing an individual G2A session ends that specific role binding without shutting down the **Interaction Origin** game process, terminating the shared **Intelligent Hub**, or closing a multiplayer room.

### 4.2 Principals, Instances, and Epochs

Caller identity MUST be established from transport-authenticated credentials; sender fields inside message payloads are checked only for consistency against authenticated identity and MUST NOT be trusted on their own. Implementations MUST keep four identity concepts distinct:

- **Principal Identity:** Uniquely identifies a player, **Computation Core**, game, or service within an issuer's namespace. Display nicknames carry zero authentication weight, and matching display names across different issuers MUST NOT be automatically merged.
- **Device Identity:** Identifies the physical or logical client endpoint holding presentation or session-control leases.
- **Game Instance:** Identifies a specific game run, match, or room at the **Interaction Origin** so grants and credentials from one run cannot be replayed against another.
- **Epochs and Control Generations:** Monotonic or strictly non-reused markers (instance epoch, world epoch, visibility epoch, and session control generation) that immediately fence stale credentials, retired observation baselines, and superseded controllers after reloads, faction switches, or device handoffs.

### 4.3 Delegation and Trust Profiles

When a service or **Intelligent Hub** acts on behalf of a player, verified **delegation** MUST bind the delegating player, delegate identity, target game instance, permitted scope, and expiration time. Routing through an intermediary NEVER adds the intermediary's own privileges to the represented principal's authority. Unverified claims inside chat or game text confer zero authority, and mere knowledge of a session, action, or correlation identifier grants neither read nor execution rights.

Deployments MUST declare and enforce compatible trust profiles without silent downgrade:

- **Locally Verified (`local-verified`):** Operating-system IPC or verified loopback pairing binds the **Interaction Origin**, shared **Intelligent Hub**, and local user on the host device.
- **Provider Verified (`provider-verified`):** Authenticated TLS combined with cryptographic token or delegation verification binds player, **Intelligent Hub**, **Computation Core**, target audience, and expiry across network boundaries.
- **Test Enrolled (`test-enrolled`):** Pre-registered development identities restricted to local testing and conformance harnesses; MUST NOT be represented as production security against untrusted local software.

Implementations MUST truthfully disclose plaintext visibility: unless end-to-end encryption is explicitly negotiated via a dedicated extension, the **Intelligent Hub** and any paired Outbound Relay can inspect messages traversing them and MUST NOT claim endpoint-only decryption.

### 4.4 Four-Way Permission Separation and Origin-Internal Secrets

Implementations MUST independently enforce four non-interchangeable permission dimensions:

1. **Receive:** Information the **Computation Core** is permitted to obtain from the **Interaction Origin** or player.
2. **Disclose to Player:** Information the **Computation Core** is permitted to surface in player-facing conversation.
3. **Disclose Externally:** Information the **Computation Core** is permitted to transmit to the game, teammates, or external services.
4. **Act:** In-game capabilities and parameter bounds the **Computation Core** is permitted to invoke.

**Strict Non-Transmission of Unrevealed Game Secrets:** Generative AI models unify internal reasoning and dialogue generation within shared context. Whenever game rules strictly forbid revealing hidden state to the player or other participants (such as hidden enemy positions, unrevealed puzzle solutions, concealed cards, or secret trap triggers), the **Interaction Origin** **MUST NOT** export the raw secret to the **Intelligent Hub** or **Computation Core**. Instead, the **Interaction Origin** MUST evaluate hidden prerequisites internally and expose only authorized observable outcomes or current action eligibility.

<a id="section-5"></a>

## 5. Canonical Conceptual Model

### 5.1 Opaque Identifiers, Standard JSON Values, and RFC 8785 Digests

All protocol identifiers (such as descriptor, offer, grant, invitation, session, stream, request, and action identifiers) MUST be treated by consumers as opaque strings and MUST NOT be parsed to infer identity, privileges, or ordering. Transport request identifiers, message envelope identifiers, correlation identifiers, event sequence numbers, and observation revisions belong to separate namespaces and MUST NOT be conflated.

**Standard JSON Value Representation (RFC 8259):** Structured protocol data uses standard UTF-8 JSON (RFC 8259) rather than custom encoding formats:

- **Standard Finite Numbers:** Wire payloads MAY use both standard integers and finite IEEE-754 floating-point numbers (for example, engine-native spatial coordinates, velocities, angles, or probabilities), while strictly rejecting non-finite values (`NaN` and `Infinity`).
- **Precision Conventions:** Timestamps and durations SHOULD use integer milliseconds for unambiguous cross-platform comparison; currency amounts, store prices, and authoritative quota ledgers SHOULD use minor integer units or explicit decimal strings to avoid floating-point rounding drift.

**Standard Cryptographic Canonicalization (RFC 8785 JCS):** Whenever the **Intelligent Hub** or peers compute deterministic cryptographic digests over structured objects — such as freezing a negotiated permission scope or binding action confirmation terms — implementations MUST canonicalize the JSON structure according to **RFC 8785 (JSON Canonicalization Scheme, JCS)** encoded as UTF-8 and hashed with domain-separated SHA-256, enabling direct use of standard RFC 8785 libraries across programming languages.

### 5.2 Normative Conceptual Objects

The G2A interaction model is defined around fourteen logical concepts:

| Conceptual Object | Normative Role and Bound Semantics |
| --- | --- |
| **Public Descriptor** | Minimal unauthenticated discovery record exposed by the **Intelligent Hub** advertising only the game instance identity, supported protocol versions, and authenticated discovery entry point, with zero player or session state. |
| **Descriptor** | Authenticated capability advertisement tailored to the caller, declaring supported versions, trust profiles, role slots and concurrency caps, supported/required capability modules, observation categories, callable action definitions, and resource limits declared by the **Interaction Origin**. |
| **Scope** | Immutable snapshot of negotiated permissions binding the player, **Computation Core**, game instance, protocol version, role slot, enabled modules, approved observation categories, approved action definitions, recipient audiences, active policies, and expiration time. |
| **Offer** | Bounded admission proposal wrapping a frozen `Scope` and its RFC 8785 digest, tracking whether player approval is pending, approved, denied, expired, or invalidated by state changes (`stale`). |
| **Grant** | Active authorization record issued upon verified player consent (or a matching standing rule), binding the approved scope digest, approver evidence, revision number, and validity window. |
| **Invitation** | Short-lived, single-use session-join credential tying an approved `Grant` to a specific **Computation Core** identity, target game instance, and joining endpoint. |
| **Session** | Active interaction context at the **Intelligent Hub** tracking session liveness (`active` or `closed`), readiness, instance and transport epochs, control generation, **Computation Core** control lease deadline, capability and membership revisions, and event sequence position. |
| **Envelope** | Data-plane message wrapper binding session identity, unique message identifier, message type, authenticated sender, permitted audience, expected capability/membership revisions, typed payload, and optional lightweight per-message extension headers. |
| **Action Definition** | Role capability declared by the **Interaction Origin** specifying its identifier, revision, eligible role, parameter and result constraints, confirmation requirement, maximum duration, cancellation support, effect reversibility class, and idempotency nature. |
| **Action Record** | Persistent invocation ledger entry maintained at the **Intelligent Hub** tracking a specific action's lifecycle state (`pending`, `executing`, `succeeded`, `failed`, `cancelled`, or `unknown`), world effect status (`none`, `partial`, `committed`, or `undetermined`), cancellation flag, and final result returned by the **Interaction Origin**. |
| **Event** | Ordered, recipient-filtered session stream entry pairing a monotonic sequence number with its message envelope and frozen acceptance audience. |
| **Recovery Snapshot** | Consolidated point-in-time state cut containing current session metadata, stream cursor, materialized authorized observations, unresolved in-flight actions, and current capability/membership revisions. |
| **Receipt** | Queryable operation acceptance record confirming whether a request is pending, completed, or failed (and flagging duplicate retries intercepted at the **Intelligent Hub**) without conferring execution authority. |
| **Error** | Structured rejection record reporting a stable machine-readable error code, error category, retry guidance, acceptance outcome (`not_accepted`, `accepted`, or `unknown`), and safe human-readable explanation. |

### 5.3 Ten Protocol Invariants (`I01`–`I10`)

Every conforming **Interaction Origin**, **Intelligent Hub**, and **Computation Core** MUST preserve all ten core invariants:

- **`I01` (Authenticated Identity First):** Unauthenticated callers MUST NOT create player approvals, invitations, active sessions, or world effects at the **Interaction Origin**.
- **`I02` (Intersection of Authority):** Effective authority enforced by the **Intelligent Hub** MUST NOT exceed the intersection of current **Interaction Origin** capabilities, active `Grant`, frozen session `Scope`, current room/team membership, and active player policy.
- **`I03` (Immutable Scope Binding):** Player approval binds an exact RFC 8785 scope digest; any security-relevant change invalidates pending offers or invitations (`stale`) and requires a fresh `Offer` rather than in-place mutation.
- **`I04` (Deterministic Hub Deduplication):** Repeating a deduplicated key with identical canonical content is intercepted by the **Intelligent Hub**, returning the prior receipt or outcome without re-executing effects at the **Interaction Origin**; reusing a key with altered content MUST be rejected with `conflict`.
- **`I05` (Receipt Is Not World Effect):** **Intelligent Hub** acceptance never proves world execution at the **Interaction Origin**; unproven outcomes MUST be reported truthfully as `unknown` (`undetermined` effect), never guessed as failed or succeeded.
- **`I06` (Dual Audience Enforcement):** Delivering protected messages or events MUST satisfy both the frozen audience recorded at acceptance and the recipient's current membership and authorization at delivery time.
- **`I07` (Generation and Epoch Fencing):** Expired, closed, or superseded epoch and control-generation credentials MUST NOT regain write or action authority; read-only outcome query handles confer zero session-control rights.
- **`I08` (Scoped Presentation Cleanup):** Disconnection, dismissal, or lease expiry releases only that session's own presentation lease without overwriting newer user window or device intent.
- **`I09` (Data Is Never Control Authority):** Game dialogue, world strings, item or store descriptions, asset metadata, and recalled memories remain untrusted data and MUST NOT elevate privileges, alter budgets, or forge confirmations.
- **`I10` (Atomic Hub Acceptance Boundary):** State transitions, deduplication receipts, and event enqueueing at the **Intelligent Hub** MUST share an atomic commit boundary, or explicitly surface `unknown` reconciliation state after a crash.

<a id="section-6"></a>

## 6. Abstract Operation Catalogue

The table below defines the transport-independent operations coordinated through the **Intelligent Hub**. Studios integrating the lightweight **Interaction Origin SDK** implement only the simple southbound state and execution callbacks (Section 22), while the **Intelligent Hub** handles northbound protocol state machines automatically. Outbound-relay transport operations are summarized in Section 18.3.

| Operation | Caller → Target | Capability / Retry Family | Normative Rule Semantics |
| --- | --- | --- | --- |
| `describe` | `Computation Core` / Player → `Intelligent Hub` | `core.session` / `read` | Return caller-filtered `Descriptor` derived from the **Interaction Origin** (never exposed to unauthenticated public discovery). |
| `offer.create` | `Computation Core` / Player → `Intelligent Hub` | `core.session` / `control` | Negotiate capabilities against expected descriptor revision and freeze `Offer` and scope digest (auto-approving only on exact standing-rule match without process launch). |
| `offer.get` | `Computation Core` / Player → `Intelligent Hub` | `core.session` / `read` | Read authorized current status of a bound `Offer`. |
| `offer.decide` | `PlayerConsent` → `Intelligent Hub` | `core.session` / `control` | Approve or deny an exact scope digest with verified player consent evidence; optionally establish a bounded standing rule or launch permission. |
| `launch.request` | Player / `Intelligent Hub` → Launcher | Launch / `control` | Trigger verified on-demand setup or start a pre-registered local binary under explicit single-use permission. |
| `invitation.redeem` | Bound `Computation Core` → `Intelligent Hub` | `core.session` / `control` | Exchange an approved `Offer` and join intent for a short-lived `Invitation` bound to the **Computation Core** and endpoint. |
| `session.join` | Bound `Computation Core` → `Intelligent Hub` | `core.session` / `control` | Atomically consume `Invitation`, complete required presentation/asset setup, and activate a `Session`. |
| `session.heartbeat` | `Computation Core` → `Intelligent Hub` | `core.session` / `lease` | Renew the **Computation Core** control lease under the current control generation using a fresh nonce (never extends absent-player presence). |
| `session.snapshot` | `Computation Core` → `Intelligent Hub` | `core.session` / `read` | Return an atomic `RecoverySnapshot` filtered by current read permissions without renewing control leases. |
| `session.events` | `Computation Core` → `Intelligent Hub` | `core.events` / `lease` | Retrieve ordered recipient-visible events after a valid cursor (renewing **Computation Core** lease only on fresh poll nonces). |
| `session.close` | `Computation Core` / Player / `Interaction Origin` → `Intelligent Hub` | `core.session` / `control` | Idempotently close the session, fence new actions, release presentation leases, and settle in-flight actions truthfully without fabricating rollback. |
| `session.resume` | `Computation Core` → `Intelligent Hub` | `resume` / `control` | Re-bind durable session control within the permitted recovery window and advance control generation. |
| `session.handoff` | `PlayerConsent` → `Intelligent Hub` | `handoff` / `control` | Fence prior control generation and prepare control transfer to a verified target endpoint without exposing secrets. |
| `session.claim_control` | Target `Computation Core` → `Intelligent Hub` | `handoff` / `control` | Claim write credentials for a ready handoff transfer on the verified target endpoint. |
| `operation.get` | Original Caller → `Intelligent Hub` | `core.session` / `read` | Reconcile original operation receipt status without side effects or secret replay. |
| `context.publish` | `Interaction Origin` → `Intelligent Hub` | `core.events` / `message` | Supply game state from the **Interaction Origin** so the **Intelligent Hub** validates category, provenance, and audience before publishing into the session stream. |
| `observation.query` | `Computation Core` → `Intelligent Hub` | `observation.query` / `read` | Stateless pull of authorized current observation records without world side effects or lease renewal. |
| `chat.send` | `Computation Core` → `Intelligent Hub` | `chat` / `message` | Send provenance- and audience-bound dialogue within session scope and retention rules. |
| `player_chat.forward` | `Interaction Origin` (verified seat) → `Intelligent Hub` | `chat` / `message` | Forward authenticated player speech from the **Interaction Origin** without renewing **Computation Core** leases. |
| `action.request` | `Computation Core` → `Intelligent Hub` | `actions` / `message` | Propose a typed in-game action; **Intelligent Hub** enforces deduplication and returns `confirmation_required` when unconfirmed policy gates apply, otherwise queues as `pending`. |
| `action.confirm` | `PlayerConsent` → `Intelligent Hub` | `actions` / `control` | Record single-use player confirmation bound to the specific action identifier, parameter/definition digests, material consequences, and expiry. |
| `action.cancel` | `Computation Core` → `Intelligent Hub` | `actions` / `message` | Request cancellation of a `pending` or cancellable `executing` action without implying state rollback. |
| `action.query` | `Computation Core` / Result Reader → `Intelligent Hub` | `actions` / `read` | Query authorized `ActionRecord` state and effect status (including post-close retention window). |
| `action.claim` | `Interaction Origin` ↔ `Intelligent Hub` | `actions` (southbound) | Re-verify revocations, cancellations, and capability revision before dispatching a `pending` action to the **Interaction Origin** as `executing`. |
| `action.commit_result` | `Interaction Origin` → `Intelligent Hub` | `actions` (southbound) | Record authoritative terminal state and world-effect status returned by the **Interaction Origin**. |
| `capability.replace` | `Interaction Origin` → `Intelligent Hub` | `actions` / `control` | Publish an updated capability catalogue from the **Interaction Origin**, advance capability revision, and invalidate unpermitted pending actions. |
| `membership.replace` | `Interaction Origin` → `Intelligent Hub` | `team` / `control` | Update room/team seats from the **Interaction Origin**, advance membership revision, and fence departed participants from new disclosures. |
| `permission.revoke` | Player / `Interaction Origin` → `Intelligent Hub` | `core.session` / `control` | Execute graded revocation against a specified target (`auto_rule`, `grant`, `invitation`, `session`, `capability`, `result_read`, `launch_permission`, or `relay`). |
| `asset.resolve` | Presentation / `Intelligent Hub` → Asset Port | `assets` / `control` | Fetch and verify declarative assets against manifest digests, size bounds, and sandbox policies. |
| `presentation.acquire` | `Intelligent Hub` → Presentation | `presentation` / `control` | Acquire bounded device presentation mode while tracking user window-intent revisions. |
| `presentation.renew` | `Intelligent Hub` → Presentation | `presentation` / `lease` | Renew an active presentation lease under matching revision and epoch. |
| `presentation.release` | `Intelligent Hub` → Presentation | `presentation` / `control` | Idempotently release the session's presentation lease and restore prior state if not superseded by newer user intent. |
| `privacy.request` | Data Subject → Data Custodian | `privacy-request` / `control` | Request scoped deletion or processing cutoff on records controlled by that custodian. |
| `privacy.receipt` | Data Subject → Data Custodian | `privacy-request` / `read` | Query truthful completion status and any legal or technical retention exceptions issued by the custodian. |

<a id="section-7"></a>

## 7. Discovery, Negotiation, and Admission

### 7.1 Open Ecosystem Access, Hub Recommendations, and Anti-Monopoly Parity

G2A balances three practical ecosystem goals: **sustainable commercialization for Intelligent Hub operators**, **fair gameplay and regulatory compliance for game studios**, and **open, non-monopolistic choice for players and third-party Computation Core providers**.

**Intelligent Hub Curated Recommendations and Open User Choice (Dual-Track Routing):** An **Intelligent Hub** MAY present a curated directory of verified or commercially promoted **Computation Core** providers (including default recommendations or clearly labeled sponsored placements) to fund ongoing hub maintenance and ecosystem growth. However, to prevent the **Intelligent Hub** itself from becoming a closed monopoly bottleneck, every conforming **Intelligent Hub** **MUST** simultaneously provide an unrestricted custom-provider configuration path allowing players to freely add, connect, and switch to any G2A-compliant third-party cloud **Computation Core** or self-hosted/local model service.

**Permitted Objective Game Allowlists:** A game developer MAY configure allowlist governance for specific game modes or deployment environments — such as ranked competitive PvP, protected virtual economies, console platform certification environments, or jurisdictions requiring regulatory content-safety registration — to enforce anti-cheat integrity, age/content compliance, and operational stability. Bespoke story-specific AI characters authored by the developer to inhabit fixed world lore (such as narrative Bosses, quest-givers, or scripted story characters) belong in `independent_npc` slots (Section 13.1) governed exclusively by the developer and need not accept replacement by third-party companions; conversely, whenever a game declares and exposes a player companion slot (`companion`), all four anti-monopoly safeguards below apply in full:

1. **Strict Technical Parity (No Privileged First-Party Backdoors):** If a game integrates a first-party, affiliated, or exclusively partnered **Computation Core** in any mode, it MUST operate over the exact same **Interaction Origin** and **Intelligent Hub** capability declarations, observation granularity, fog-of-war limits, action cooldowns, rate limits, and player confirmation gates available to conforming third-party **Computation Cores** in that mode. Studios MUST NOT grant first-party services undocumented hidden-state access, zero-latency internal execution bypasses, or exemptions from player safety gates.
2. **Published, Objective, and Auditable Admission Criteria (FRAND Access):** Whenever a game mode uses an allowlist and admits a first-party or external **Computation Core**, the developer MUST publish clear, vendor-neutral technical and compliance criteria (such as passing public G2A conformance suites, holding required statutory content-safety filings, and honoring anti-cheat rate caps) along with an accessible application path, reasonable review timelines, and specific written refusal reasons. Closed "first-party or corporate-affiliate only" allowlists are non-conformant.
3. **No Commercial Tying or Model Lock-In:** Admission to a technical or safety allowlist MUST NOT be conditioned on exclusive commercial revenue-sharing agreements, mandatory purchase of a specific cloud/LLM vendor's inference service, or surrendering player control over cross-game companion memories.
4. **Risk-Scoped Restrictions and Data Non-Lock-In:** Anti-cheat restrictions SHOULD be scoped to the capabilities that pose gameplay risk — for example, restricting automated combat `actions` in ranked PvP while still permitting compliant player-chosen companions to use low-risk `chat` or spectator advice in casual or social modes rather than imposing blanket game-wide bans. Regardless of allowlist scope, players retain their right to export personal companion memories in an open standard format (Section 15.4).

Every runtime refusal or disconnection MUST return a standardized error code (Section 12.1) and a specific, safe explanation identifying the violated rule or admission requirement without leaking credentials, other players' private data, or hidden game facts.

### 7.2 Public vs. Authenticated Discovery

Discovery at the **Intelligent Hub** separates minimal unauthenticated probing from authenticated capability disclosure:

1. **Unauthenticated Public Discovery:** Exposes only the `PublicDescriptor` (game instance identity, supported G2A versions, and authenticated discovery entry point), revealing zero player identities, room rosters, or private capabilities.
2. **Authenticated Capability Discovery (`describe`):** Requires an authenticated **Computation Core** or player identity and returns a `Descriptor` filtered to capabilities, role slots, allowlist requirements, and transport bindings eligible for that caller.

Peers select the highest mutually permitted protocol version and verify module dependencies. Unsupported mandatory modules or mandatory extensions MUST fail negotiation immediately; unknown optional extensions MUST remain disabled without weakening core security boundaries.

### 7.3 End-to-End Admission Lifecycle

Both **Computation-Core-initiated** and **Interaction-Origin-initiated** (such as a player clicking "Summon Companion" inside the game) flows converge onto a unified seven-step authorization lifecycle orchestrated by the **Intelligent Hub**:

1. **Capability Discovery (`describe`):** Obtain the caller-filtered `Descriptor` and current revision from the **Intelligent Hub**.
2. **Scope Proposal (`offer.create`):** Propose desired capabilities and freeze an immutable `Scope` and its RFC 8785 digest.
3. **Player Consent Presentation:** Present clear, human-readable permission terms to the bound player via `PlayerConsent` (skipped only if an unexpired, previously approved standing rule matches every security-relevant scope term without launching a new local process).
4. **Consent Decision (`offer.decide`):** Record verified player approval or denial bound to the exact scope digest, creating an active `Grant` on approval.
5. **Optional Local Setup or Launch (`launch.request`):** If a required local component is not yet running and explicit single-use permission was granted, invoke the trusted `Local Runtime Installer / Launcher`.
6. **Invitation Exchange (`invitation.redeem`):** Bind the approved `Grant` and join intent into a short-lived `Invitation`.
7. **Session Activation (`session.join`):** Atomically consume the `Invitation`, establish the `Session` and control lease at the **Intelligent Hub**, and begin exchanging snapshots, observations, chat, and authorized actions.

**Core Admission Safeguards:** **Computation Cores** MUST NOT self-approve offers; narrowing or changing requested permissions requires creating a new `Offer` with a new scope digest rather than mutating an existing proposal in place; and permission to join a session never implies permission to spawn arbitrary operating-system processes.

### 7.4 Extension Negotiation and Envelope Placement

Optional extensions are identified by reverse-domain namespaced identifiers paired with explicit version and mandatory/optional flags:

- **Session-Level Freezing:** Supported options, requested settings, and negotiated extension configurations are bound inside the session `Scope` and covered by its cryptographic digest at admission time.
- **Lightweight Data-Plane Envelopes:** Once a session is active, negotiated extension settings are already bound to the session at the **Intelligent Hub**. Per-message envelopes carry only lightweight per-message extension headers when explicitly required by a profile (empty by default), and MUST NOT retransmit bulky static configuration catalogues on every real-time event or alter frozen `Scope` terms.

<a id="section-8"></a>

## 8. Grants, Sessions, and Revocation

### 8.1 Grant Bindings

Every `Grant` enforced by the **Intelligent Hub** binds its issuer, player, **Computation Core**, target game instance, permitted operations, frozen scope digest, expiration timestamp, and revocation revision. Observation grants bind category semantics, perspective, recipient audience, rate/size bounds, and retention rules; action grants bind approved action definitions and parameter limits. Capability refreshes from the **Interaction Origin** (`capability.replace`) NEVER automatically expand an existing `Grant`; broader authority always requires new player consent.

### 8.2 Session Lifecycle, Control Lease, and Player Presence

The **Intelligent Hub** MUST strictly separate two independent liveness mechanisms:

1. **Computation Core Control Lease:** Prevents crashed or unreachable **Computation Cores** from holding indefinite session control. Renewed solely by authenticated `session.heartbeat` calls or fresh `session.events` poll nonces under the active control generation; ordinary read queries and **Interaction Origin** calls MUST NOT extend this lease.
2. **Player Presence (Section 14.1):** Reported authoritatively by the **Interaction Origin** from the human player's active participation in the game. A **Computation Core** heartbeat MUST NEVER extend, simulate, or spoof an absent player's online presence.

### 8.3 Scoped Revocation Hierarchy

`permission.revoke` targets explicit authority scopes at the **Intelligent Hub** with deterministic blast radii rather than ambiguous global resets:

| Revocation Target | Immediate Isolation Effect | Preserved Legitimate State |
| --- | --- | --- |
| `auto_rule` | Stops future automatic approvals under that rule. | Existing `Grant`s, `Invitation`s, and active `Session`s remain unaffected unless separately revoked. |
| `launch_permission` | Blocks unconsumed local application launches. | Historical launch receipts and independent interaction `Grant`s remain intact. |
| `invitation` | Invalidates an unconsumed `Invitation` immediately. | The underlying `Grant` remains valid unless revoked. |
| `grant` | Invalidates the `Grant`, voids unconsumed `Invitation`s under it, and closes all bound `Session`s. | Already committed world effects at the **Interaction Origin** and valid read-only outcome query handles remain inspectable until expiry. |
| `session` | Closes one specified `Session`, fences unclaimed `pending` actions from reaching the **Interaction Origin**, and releases presentation leases. | Sibling concurrent sessions (`multi-session`) and committed action records remain intact. |
| `capability` | Monotonically removes specific action rights and blocks dispatch (`action.claim`) of affected `pending` requests to the **Interaction Origin**. | The session remains active for remaining capabilities; prior `ActionRecord` reads remain available. |
| `result_read` | Terminates read-only outcome query access for the revoked handle. | Authoritative internal audit ledgers remain unaltered. |
| `relay` | Closes the paired Outbound Relay mailbox and wakes pending waiters. | Unresolved in-flight actions transition to `unknown` for reconciliation rather than triggering silent replay. |

### 8.4 Per-Operation Authority Verification

Every protected operation at the **Intelligent Hub** — including snapshot reads, stateless observation queries, action status queries, and privacy receipt lookups — MUST verify on every call that the authenticated caller and delegation chain match the target resource, role, session, and audience, and that neither the `Grant`, `Session` control generation, nor `Instance` epoch has expired or been revoked.

<a id="section-9"></a>

## 9. Game Observation Rules

### 9.1 Observation Categories and Negotiation

A **Computation Core** MAY declare required and optional observation categories during admission. If the **Interaction Origin** cannot supply a required category, negotiation MUST fail explicitly (or proceed only under a newly approved `Offer` with narrowed scope) rather than fabricating placeholder empty feeds.

Each observation category defines its semantic version, unit conventions, size and rate bounds, supported delivery modes (proactive push, stateless query, or both), freshness window, authorized perspective (`player-self`, `team`, `npc-self`, or `guide`), and storage retention rules.

### 9.2 Baseline Snapshots, Deltas, and Retractions

Authorized game observations advance from the **Interaction Origin** through the **Intelligent Hub** to the **Computation Core** in three deterministic stream modes within a given stream identifier, world epoch, and visibility epoch:

- **Baseline Snapshot (`snapshot`):** Atomically establishes or replaces the complete authorized view for that stream (immediately discarding any prior records omitted from the new snapshot) and binds the category version and semantic definition for the current epoch.
- **Incremental Update (`delta`):** Atomically applies record additions/updates and structured removals atop an exact matching base revision within the same epoch. Structured removals specify each removed entity's transition reason (`left_view`, `destroyed`, or `unknown`). Because the baseline snapshot already binds static category metadata for the epoch, incremental updates omit redundant schema metadata to keep high-frequency payloads compact.
- **Invalidation Barrier (`retract`):** Immediately withdraws specified records or the entire observation stream within the epoch and establishes a monotonic barrier preventing delayed or replayed older updates from resurrecting retracted state.

Entity identifiers within observations MUST be perspective-scoped opaque tokens rather than sequential global engine indices that could leak hidden entity counts. Stream revisions advance monotonically; non-contiguous revision jumps are valid when intermediate states are coalesced, whereas a `delta` whose base revision does not match the consumer's current state MUST be rejected, triggering a fresh snapshot resynchronization.

### 9.3 Epoch Retirement, Coalescing, and Visibility Transitions

World resets, save reloads, team switches, or permission changes immediately retire affected observation baselines: the **Interaction Origin** and **Intelligent Hub** MUST advance the world or visibility epoch and issue a fresh `snapshot` before sending further incremental updates, and **Computation Cores** MUST discard retired baselines immediately upon notification.

The **Intelligent Hub** MAY coalesce replaceable intermediate state updates provided base-revision continuity is preserved (or a fresh `snapshot` is sent), while discrete gameplay events that carry standalone meaning MUST NOT be silently overwritten. Entity appearance and removal transitions MUST distinguish `entered_view`, `created`, `left_view` (subsequent state unknown), `destroyed` (authoritatively confirmed eliminated), and `unknown`, preventing **Computation Cores** from mistaking fog-of-war departure for target death.

### 9.4 Freshness, Clocks, and Recovery Materialization

Observations past their declared expiration window MUST be treated as stale. Because **Interaction Origins**, **Intelligent Hubs**, and remote **Computation Cores** may run on unsynchronized clocks, freshness windows rely on declared generation timestamps and bounded clock-skew assumptions rather than raw cross-host wall-clock subtraction.

A `RecoverySnapshot` (`session.snapshot`) assembled by the **Intelligent Hub** MUST deliver the consolidated current state of each active authorized stream rather than replaying historical incremental logs; streams absent from a fresh recovery snapshot are no longer active.

### 9.5 Structured Foundation and Orthogonal Multimodal Feeds

`perception.structured` is the mandatory foundation for all gameplay **Computation Cores**; visual frame perception (`perception.visual`) and game-environment audio perception (`perception.audio`) are independent, orthogonal optional capabilities layered atop it:

- **Independent Negotiation:** A **Computation Core** MAY support `perception.structured` alone, add `perception.visual` only, add `perception.audio` only, or support both. Neither media feed replaces structured state comprehension or grants access to the user's operating-system desktop, personal microphone, or hidden game data.
- **Independent Player Controls:** Players MAY independently enable or disable visual feeds and game-audio feeds at the **Intelligent Hub** at runtime (separate from Section 15.3 voice conversation), and disabling a feed MUST halt transmission and processing of that media stream immediately.

### 9.6 Proactive Push vs. Stateless Observation Query

**Interaction Origins** declare per category whether observations are pushed proactively via the session event stream, pulled on demand via `observation.query`, or both. `observation.query` is enforced at the **Intelligent Hub** against current permissions and rate limits on every call and produces zero world side effects; active in-game scouting abilities that spend resources, consume turns, or lift fog-of-war are **Actions** (Section 10), never observation queries.

<a id="section-10"></a>

## 10. Actions and Effect Semantics

### 10.1 Capability Granularity and Action Declarations

Game developers determine the granularity of actions exposed by the **Interaction Origin** — high-level semantic abilities (such as attacking a target or crafting an item), low-level typed primitives (such as moving toward coordinates), or both. Even low-level primitives remain bounded in-game actions governed by game rules, never raw operating-system keyboard or mouse injection; chaining multiple actions neither expands authority nor creates multi-action atomic world transactions.

Every `ActionDefinition` explicitly declares its eligible role, parameter bounds, confirmation policy, maximum duration, cancellation support (`none`, `before_claim`, or `between_steps`), reversibility class (`read_only`, `compensatable`, or `irreversible`), and idempotency flag. Reversibility and side effects MUST be declared explicitly rather than inferred from action names.

### 10.2 Five-Stage Execution Lifecycle, Anti-Replay Shield, and Confirmation Challenge

Every action progresses across the **Computation Core**, **Intelligent Hub**, and **Interaction Origin** through five distinct lifecycle boundaries:

1. **Proposal and Confirmation Challenge Gate (`Computation Core` → `Intelligent Hub`):** The **Computation Core** submits `action.request` with a stable action identifier, expected capability revision, and typed parameters. If the action requires player confirmation — under its static definition, item-transfer policy (Section 16.3), irreversible-consequence policy (Section 16.3), or purchase-budget cap (Section 17.1) — and no matching unexpired `action.confirm` exists at the **Intelligent Hub**, the hub MUST NOT forward executable work to the **Interaction Origin**. Instead, it returns a structured **`confirmation_required` challenge** (`not_accepted` outcome) detailing the bound action identifier, parameter/definition digests, concrete consequences, expiration deadline, and cooldown window. Because `not_accepted` does not burn the action identifier in the deduplication ledger, once `PlayerConsent` completes `action.confirm` before expiry, resubmitting the identical `action.request` proceeds cleanly to Stage 2.
2. **Intelligent Hub Anti-Replay Gate and Queue Acceptance (`pending`):** The **Intelligent Hub** validates authority, capability revision, and parameter constraints, atomically consumes any required confirmation, and records `ActionRecord` (`pending`, effect `none`) alongside its deduplication receipt. **If network jitter or disconnection causes the Computation Core to send the same action identifier more than once (such as a repeated attack request), the Intelligent Hub intercepts the duplicate here and returns the cached receipt without ever invoking the Interaction Origin a second time.**
3. **Southbound Dispatch and Claim (`executing`):** After re-verifying active session/grant status, capability revision, and cancellation flags (`action.claim`), the **Intelligent Hub** dispatches the single validated request over the southbound HTTP port to the **Interaction Origin**, transitioning the record to `executing`.
4. **Origin Effect-Boundary Adjudication:** Immediately before mutating game-world state, the **Interaction Origin** enforces current gameplay rules and world preconditions (such as cooldowns, range, or turn ownership), producing only valid in-game effects.
5. **Outcome Settlement (`action.commit_result`):** The **Interaction Origin** returns the execution outcome over the southbound HTTP port, and the **Intelligent Hub** commits the terminal state and world-effect status (recording `unknown` / `undetermined` if a crash or timeout prevents authoritative verification).

### 10.3 Action State and Effect Matrix

`ActionRecord` pairs lifecycle processing state with authoritative world-effect accounting:

| Action State | Permitted Effect Values | Normative Meaning |
| --- | --- | --- |
| `pending` | `none` | Accepted at the **Intelligent Hub**; not yet dispatched to / claimed by the **Interaction Origin**. |
| `executing` | `none`, `partial`, `committed`, `undetermined` | Dispatched to the **Interaction Origin**; world execution may be underway. |
| `succeeded` | `committed` | Completed at the **Interaction Origin** with its defined successful world effect committed. |
| `failed` | `none`, `partial` | Execution failed under game rules, truthfully recording whether partial world effects occurred. |
| `cancelled` | `none`, `partial` | Cancelled prior to full completion, truthfully recording any partial effects. |
| `unknown` | `undetermined` | Timeout, disconnect, or fault prevented authoritative outcome verification from the **Interaction Origin**. |

Known terminal states (`succeeded`, `failed`, `cancelled`) MUST NOT be silently overwritten; `unknown` transitions to a terminal state only upon authoritative **Interaction Origin** evidence. `action.cancel` is a best-effort stop request rather than a rollback guarantee: if cancellation races with execution and the world effect commits at the **Interaction Origin**, the **Intelligent Hub** MUST report `succeeded` (`committed`).

### 10.4 Dynamic Action Eligibility vs. Static Definitions

Advertising an action in `Descriptor` indicates static capability support, not that the character may execute it right now. **Interaction Origins** MUST supply machine-readable current action eligibility within the authorized view (such as turn ownership, cooldown/resource readiness, valid target constraints, or discrete legal-action masks) bound to an observation revision without leaking hidden targets or secret prerequisites. Any advisory feasibility or probability estimate MUST be labeled as an estimate and never replaces authoritative **Interaction Origin** adjudication.

### 10.5 Observation-Bound Preconditions and Stale-State Rejection

Observation-dependent action requests SHOULD reference the observation baseline (stream, epochs, and revision) and any freshness bound or target precondition relied upon. If the referenced epoch is retired, the freshness bound is exceeded, or a precondition fails at the **Interaction Origin** (for example, a heal target has already been defeated or switched factions), the action MUST be rejected before producing effects (`stale_context` or failed precondition), prompting the **Computation Core** to reassess against fresh observations rather than blindly retrying unchanged parameters.

<a id="section-11"></a>

## 11. Idempotency, Delivery, and Recovery

### 11.1 Operation Retry Families and Hub Deduplication Horizons

Operations enforced by the **Intelligent Hub** follow four deterministic retry families so callers recover safely from network faults without burdening the **Interaction Origin**:

| Retry Family | Representative Operations | Replay and Deduplication Rules |
| --- | --- | --- |
| **`read`** | `describe`, `offer.get`, `session.snapshot`, `observation.query`, `action.query`, `operation.get`, `privacy.receipt` | Re-verifies current authority on every call; returns latest authorized state; never mutates state or renews leases. |
| **`lease`** | `session.heartbeat`, `session.events`, `presentation.renew` | Requires a fresh nonce per renewal; replaying an older request identifier returns cached status without extending the lease deadline. |
| **`control`** | `offer.create`, `offer.decide`, `invitation.redeem`, `session.join`, `session.close`, `session.resume`, `action.confirm`, `permission.revoke` | Deduplicated at the **Intelligent Hub** by caller and operation target within the receipt retention window; identical canonical retries return the original receipt (`duplicate`), whereas altered content fails with `conflict`. |
| **`message`** | `context.publish`, `chat.send`, `player_chat.forward`, `action.request`, `action.cancel` | Deduplicated at the **Intelligent Hub** by session, authenticated sender, and message identifier; accepted messages dispatch at most once, while pre-acceptance `confirmation_required` challenges (`not_accepted`) do not consume the identifier. |

Deduplication receipts MUST be retained at the **Intelligent Hub** for at least the declared retention horizon, and expired deduplication records never grant permission to re-execute non-idempotent side effects. Event consumers apply ordered stream items at most once, tolerate sequence gaps caused by audience filtering, and recover from expired cursors via `session.snapshot`.

### 11.2 Action Outcome Reconciliation and Default No-Resend Rule

Every game action carries a persistent action identifier queryable at the **Intelligent Hub** across transient disconnects within the declared result retention window:

- **Mandatory Query-First and Default No-Resend:** Following any timeout, gateway timeout (`504`), or connection drop, the **Computation Core** (or **Intelligent Hub** on a southbound timeout) MUST query the original action identifier before taking further steps. Whenever the outcome remains `unknown`, missing, or expired, implementations MUST default to **no automatic resend or re-execution**, and MUST NOT fabricate a new action identifier to bypass deduplication.
- **Subsequent Independent Decisions:** A player or **Computation Core** MAY later make a fresh, independent decision grounded in updated observations, current permissions, and active confirmation/budget policies, accounting for the possibility that the unresolved action already took effect at the **Interaction Origin** without falsifying the original `unknown` record.

<a id="section-12"></a>

## 12. Error Model, Time, and Resource Limits

### 12.1 Canonical Error Code Taxonomy

Protocol rejections from the **Intelligent Hub** MUST return stable machine-readable error codes with deterministic commit-outcome classification (`not_accepted` vs. `unknown`) and HTTP status alignment (Section 18.2):

| Standard Error Code | Category | Commit Outcome | Normative Caller Recovery Action | HTTP Status |
| --- | --- | --- | --- | --- |
| `invalid_request` | Syntax / Envelope | `not_accepted` | Fix malformed syntax or envelope structure; do not repeat unchanged. | `400` |
| `invalid_arguments` | Parameter Constraints | `not_accepted` | Correct operation or action parameters against declared bounds. | `400` |
| `unsupported_version` | Negotiation | `not_accepted` | Select a mutually supported protocol version or abort connection. | `400` |
| `unsupported_capability` | Negotiation | `not_accepted` | Renegotiate without unsupported required module/extension or abort. | `400` |
| `unauthenticated` | Authentication | `not_accepted` | Obtain valid credentials before retrying; do not probe existence. | `401` |
| `permission_denied` | Authorization / Admission | `not_accepted` | Request appropriate `Offer` or respect game/allowlist refusal; do not retry blindly. | `403` |
| `revoked` | Authorization | `not_accepted` | Immediately cease activity in the revoked scope. | `403` |
| `not_found` | Scoped Lookup | `not_accepted` | Verify identifier within authorized scope (never leaks unauthorized existence). | `404` |
| `stale_context` | Epoch / Baseline | `not_accepted` | Refresh descriptor, snapshot, capability revision, or observation baseline before reassessing. | `409` |
| `conflict` | State / Deduplication | `not_accepted` | Reconcile original state or deduplication conflict; never invent bypass identifiers. | `409` |
| `confirmation_required` | Player Policy Gate | `not_accepted` | Present structured challenge to `PlayerConsent`; resubmit original action only after `action.confirm`. | `409` |
| `message_too_large` | Resource Bound | `not_accepted` | Reduce payload or page size within declared limits. | `413` |
| `resource_limit` | Rate / Quota | `not_accepted` | Honor backoff delay and declared concurrency/rate limits. | `429` |
| `unavailable` | Service Health | `not_accepted` | Back off and retry only per Section 11.1 retry-family safety rules. | `503` |
| `outcome_unknown` | Timeout / Ambiguity | `unknown` | Reconcile via `action.query` / `operation.get`; **never** equate with failure or auto-resend side effects. | `504` |

### 12.2 Safe Error Disclosure

Error responses are themselves subject to visibility and privacy rules: explanations and error details MUST NOT reveal whether an unauthorized session or hidden entity exists at the **Interaction Origin**, leak another player's private state, or echo raw credentials or internal stack traces.

### 12.3 Clocks, Quotas, and Non-Droppable Control Signals

The **Intelligent Hub** MUST enforce explicit bounds on payload size, nesting depth, collection lengths, pending actions, event retention, and request rates to shield the **Interaction Origin** from overload without producing unreported partial effects. Lease and token expiration is adjudicated using monotonic clocks for elapsed-time measurement so system wall-clock jumps cannot silently extend leases.

Queue overflow MUST surface an explicit gap, snapshot resynchronization requirement, or `resource_limit` rejection. Action outcome settlements, `permission.revoke` barriers, and `retract` invalidations are non-droppable control signals and MUST NOT be discarded as ordinary replaceable telemetry.

<a id="section-13"></a>

## 13. Gameplay Roles and Slot Rules

### 13.1 Role Bindings vs. Information Perspectives

A **Player Companion** or **Independent AI NPC** is an in-game character slot governed by the **Interaction Origin**; a **Computation Core** is the cognitive service authorized via the **Intelligent Hub** to perceive and decide for that slot. Implementations MUST distinguish:

- **Role Binding:** Which specific in-game character slot at the **Interaction Origin** the **Computation Core** currently drives (such as Player A's personal companion, or an independent AI Boss or guide).
- **Information Perspective:** Which scoped knowledge view that role is authorized to receive (`player-self`, `team`, `npc-internal`, or `guide-progression`).

A single **Computation Core** service MAY support companion, NPC, Boss, and guide roles without splitting into separate products. Combining perspectives within a role requires explicit game authorization, never implicitly merges permissions across distinct slots, and retires prior observation baselines whenever visibility changes. NPCs MAY hold developer-supplied lore hidden from players, while personal companions MAY hold player-governed cross-game memories; neither role name grants omniscience or unrestricted disclosure rights.

### 13.2 Declared Role Slots, Coexistence, and Concurrency Limits

Game developers declare supported role slots, coexistence rules, and active concurrency caps at the **Interaction Origin** (advertised via `Descriptor`); **Intelligent Hub**, **Computation Core**, or player settings MUST NOT override these structural game boundaries:

- **Supported Role Slots:** A game MAY offer player-companion slots, independent AI NPC/enemy (including Boss or guide) slots, or both. Pure AI-NPC games need not expose a dummy companion slot, and companion-focused games need not support AI NPCs.
- **Companion Concurrency and Empty-Slot Playability:** Where companion slots are offered, the default cap is at most one active companion per authenticated player (including in multiplayer, where multiple players' companions may coexist within their respective grants and game rules). Players MAY leave their companion slot empty, and the game MUST remain normally playable without an active companion.
- **Coexistence and Multi-NPC Caps:** The **Interaction Origin** explicitly declares whether player companions and independent AI NPCs may operate simultaneously in the same match and caps concurrent independent AI NPCs; coexistence or multi-NPC concurrency MUST NOT be assumed unless declared.
- **Strict Per-Role Isolation:** Every active role at the **Intelligent Hub** binds to its authenticated responsible principal (owning player or designated billing sponsor under Section 16.2), role identifier, perspective, audience, and `Scope`. Coexisting roles MUST NOT implicitly share observations, private memories, action grants, or billing accounts, and replacing an active binding MUST fence the prior binding first. Ordinary non-G2A built-in game NPCs are unaffected by G2A slot caps.

<a id="section-14"></a>

## 14. Presence and Role Lifecycle

Four lifecycle events require distinct handling across the three tiers without confusing halting future **Computation Core** decisions with rolling back committed state at the **Interaction Origin**:

| Lifecycle Event | Required Normative Handling |
| --- | --- |
| **Player goes offline or exits game** | Stop associated G2A activity immediately; upon later re-entry, prior tasks stay stopped awaiting a fresh player instruction (Section 14.1). |
| **Computation Core interrupted while player is online** | Gameplay at the **Interaction Origin** continues. Brief blips within an active lease prior to local fallback takeover may seamlessly `session.resume`; extended outages or post-fallback takeovers require an explicit player continuation decision (Section 14.2). |
| **Player dismisses companion** | Stop game observation forwarding and autonomous actions immediately without deleting retained companion memories (Section 14.2). |
| **Player stops or supersedes current task** | Discard unsubmitted **Computation Core** plans and cancel/fence unclaimed `pending` actions at the **Intelligent Hub**; already `executing` skills at the **Interaction Origin** resolve under game rules (Section 16.1). |

### 14.1 Mandatory Stop on Player Offline and Multiplayer NPC Continuity

G2A **MUST NOT** provide any offline background mode in which a **Computation Core** continues acting in an empty game world after all associated human players have left or been determined offline at the **Interaction Origin**.

- **Offline Detection and Hub Fencing:** Explicit game exit, session closure, or player-presence timeout at the **Interaction Origin** immediately terminates eligibility for new autonomous actions; the **Intelligent Hub** MUST fence affected control within bounded deadlines, and **Computation Core** heartbeats MUST NEVER extend an absent player's presence. Already `executing` animations or projectiles at the **Interaction Origin** finish naturally under game rules while unclaimed `pending` actions at the **Intelligent Hub** are cancelled or fenced. Upon re-entering the game later, previously active tasks remain stopped until the player issues a new instruction.
- **Personal Companion Isolation:** When a player disconnects from a multiplayer session, their personal companion session MUST stop immediately without affecting other online players' independent sessions.
- **Independent AI NPC Continuity in Multiplayer Rooms:** Handling of an independent AI NPC (such as a raid Boss or shared guide) when a player disconnects depends on its declared billing and sponsorship mode (Section 16.2):
  1. **Player-Metered Mode (Default):** When the authenticated player sponsoring that AI NPC (such as the room host) goes offline, **that player's billing authorization and control binding MUST terminate immediately** — never continuing to bill the disconnected host or silently shifting charges onto remaining players. For an ongoing multiplayer encounter with remaining online players, the **Interaction Origin** and **Intelligent Hub** execute the declared room-continuity rule: (a) halt the AI NPC cleanly, (b) transition the character to local game-scripted fallback behavior at the **Interaction Origin** to let remaining players finish the encounter, or (c) continue **Computation Core** operation only after another online player **explicitly consents** to assume sponsorship under a fresh authorization binding (or the game switches to developer-sponsored fallback), transferring only future in-encounter NPC compute billing and control without ever exposing the prior host's billing credentials, account details, or personal session records.
  2. **Developer-Sponsored Mode:** When the game developer sponsors the AI NPC's **Computation Core** cost, a single player's departure does not force the shared NPC to halt so long as at least one authorized human player remains active in the encounter; once all human players leave the instance, the AI NPC MUST stop immediately.

### 14.2 Summoning, Dismissal, and Two-Tier Service Interruption Recovery

**Interaction Origins** offering companion slots MUST allow players to summon or dismiss their companion during play, honor entry preferences (auto-join under a valid grant or entry prompt), and remain playable if the **Computation Core** is unreachable at launch.

**Computation Core Interruption During Active Play:** If the **Computation Core** disconnects while the player remains in-game, gameplay at the **Interaction Origin** continues and applies its declared fallback behavior (either keeping the companion stationary or switching to clearly attributed local game-script behavior). Neither the **Interaction Origin** nor the **Intelligent Hub** may record disconnected gameplay to backfill observations upon reconnection; recovery provides only the current authorized snapshot and outcome reconciliation for prior in-flight actions.

**Two-Tier Post-Recovery Continuation:**

1. **Brief Transport Blip Within Active Lease:** When `resume` is negotiated and reconnection to the **Intelligent Hub** completes within the unexpired session lease *before* local fallback behavior takes over at the **Interaction Origin** — while the player has remained continuously online without issuing a stop or dismissal — the **Computation Core** MAY invoke `session.resume`, revalidate permissions and control generation, refresh the snapshot, reconcile in-flight actions, and continue seamlessly without interrupting combat.
2. **Extended Outage, Expired Lease, or Post-Fallback Takeover:** Once the lease expires or local script fallback has taken over at the **Interaction Origin**, reconnection MUST keep companion AI actions paused at the **Intelligent Hub** until the player explicitly confirms continuation; entry auto-join preferences do not bypass this decision.

<a id="section-15"></a>

## 15. Conversation, Information Use, and Companion Memory

Implementations MUST distinguish deterministic data permissions enforced by the **Intelligent Hub** and **Computation Core** (storage, retrieval, recipient audience, external forwarding) from soft conversational preferences (spoiler avoidance, topic focus, conversational style). When optional `chat` is enabled, messages carry authenticated provenance (`observed_fact`, `player_statement`, `agent_inference`, or `external_reference`) and explicit recipient audiences verified against current membership at delivery; text or voice speech carries control authority only when confirmed through an authenticated player-control or `PlayerConsent` path. Uncertain speech transcriptions MUST NOT be treated as verified high-impact commands, and voice dialogue remains independent of game-environment audio perception (Section 9.5).

### 15.1 Memory Ownership and Cross-Playthrough Boundaries

**Interaction Origins** govern whether developer-controlled NPC and guide state resets or carries across playthroughs. Conversely, **player-governed companion memory** managed by the **Computation Core** belongs to the player's companion relationship: closing a game session, companion in-game defeat, or starting a new playthrough at an **Interaction Origin** MUST NOT silently delete or disable unrelated companion memories, nor does companion memory ownership grant access to hidden game data or other players' private channels.

### 15.2 Save Reloads and Optional Advanced Timeline Isolation

- **Foundational Reload Rule (Mandatory):** Reloading an earlier save, switching narrative branches, or starting a new playthrough updates current world state at the **Interaction Origin** (via a fresh world epoch and observation snapshot under Section 9.3) without erasing retained player-companion memories in the **Computation Core**. Standard games do **not** need to construct narrative branch trees to conform to G2A. Within eligible player-companion conversations, players MAY override advisory developer preferences (for example, choosing to discuss prior playthroughs or other games) without expanding game-data permissions.
- **Fine-Grained Timeline and Branch Isolation (Optional Advanced Optimization):** Narrative-heavy or multi-branch **Interaction Origins** MAY optionally expose playthrough, branch, timeline-position, and monotonic save-load generation metadata alongside observations. Where both the **Interaction Origin** and **Computation Core** explicitly support and enable this advanced optimization, the **Computation Core** tags stored memories with timeline provenance and — when strict anti-spoiler isolation is selected by the player — filters post-checkpoint or non-ancestral branch memories before constructing inference context, or labels recalled memories clearly as prior-branch experience rather than current-world fact.

### 15.3 Enforceable Permissions vs. Soft Conversational Preferences

Hard storage, retrieval, and outbound-audience permissions MUST be enforced deterministically outside model prose, including per-player opt-in/out controls at the **Intelligent Hub** for receiving proactive messages from other players' companions and owner controls over retaining multiplayer conversations. Soft conversational preferences — such as spoiler avoidance, confidentiality style, and player-selected companion persona or speaking style (which override conflicting developer suggestions for personal companions, while never altering developer-authored characterization of independent AI NPCs) — are guided via **Computation Core** conditioning with honest disclosure that generative outputs cannot mathematically guarantee zero soft-preference drift.

### 15.4 Player Memory Controls, Autonomous Maintenance, and Portability

- **Player Inspection and Protected Autonomous Maintenance:** **Computation Core** providers MUST allow players to view, edit, pin/lock, and delete their retained companion long-term memories, propagating completed edits and deletions across controlled indexes and caches (`privacy.request` / `privacy.receipt` report any statutory or technical retention exceptions). Within the player's retention policy, a companion MAY autonomously organize memories and compact or prune unpinned raw records without per-item prompts, provided it **NEVER** overwrites explicit player edits, deletes player-pinned records, or resurrects deleted items from stale caches.
- **Provenance Metadata:** Stored and exported records MUST distinguish event occurrence time from storage time, and distinguish direct **Interaction Origin** observations, player statements, derived summaries/inferences, and explicit player edits.
- **Open Standard Data Format Export and Receiving Safeguards:** **Computation Core** providers MUST allow the player to export their retained companion memories (both retained experiences and consolidated summaries, with provenance metadata) together with player-selected companion persona, speaking style, and autonomy preferences in a **documented, vendor-neutral, open standard structured data format** free of proprietary lock-in. The source provider verifies only the authenticated player's identity and selected export scope — it MUST NOT require knowing, vetting, or approving the player's chosen destination **Computation Core** or local tool, and exporting never triggers automatic disclosure to any game or third party. Any receiving **Computation Core** that supports importing the standard format MUST honor the player's selected import scope, preserve carried provenance and access/retention/disclosure constraints (treating unrecognized restrictive markers conservatively as private to the player), and **MUST NOT** expand what may be disclosed to any **Interaction Origin** or other participant merely because the player switched providers. Importers MUST return truthful local per-record receipts (`imported`, `transformed`, `rejected`, or `unresolved`), preserve supported companion settings, and truthfully report any selected settings that are unsupported, transformed, or unapplied, without promising model-weight transfer or identical behavioral expression across different models.

<a id="section-16"></a>

## 16. Role Autonomy, Confirmation Gates, and Cost Models

Autonomy governs *how much initiative* a **Computation Core** exercises **within** already granted capabilities — never *whether* a capability is authorized at the **Intelligent Hub**.

### 16.1 Autonomous Assistance and Three-Stage Stopping

While the associated player is online (Section 14.1), task or standing authorization permits a companion **Computation Core** to plan and invoke in-scope actions proactively without per-step prompts. Multi-step task completion MUST be grounded in **Interaction Origin** observation or action-outcome evidence that the goal was achieved, never reported complete merely because requests were queued. Player-selected autonomy preferences persist across sessions without overriding game rules or confirmation gates.

Whenever a player halts, narrows, or issues a conflicting newer command that supersedes current autonomous work, three-stage stopping applies immediately across the three tiers:

1. **Unsubmitted Computation Core Plans:** Halt planning for the stopped scope and discard all unsubmitted steps at the **Computation Core**.
2. **Queued `pending` Actions at the Intelligent Hub (`none` effect):** Immediately cancel or fence unclaimed `pending` requests in scope at the **Intelligent Hub** so they are never dispatched to the **Interaction Origin**.
3. **In-Flight `executing` Actions at the Interaction Origin:** Already dispatched attacks, animations, or projectiles settle naturally under **Interaction Origin** game rules (or explicit per-action cancellation) without fabricating rollback, reconciled truthfully under Section 11.2.

### 16.2 Runtime Caps and Configurable AI NPC Billing Models

**Computation Core** services and **Intelligent Hubs** MUST disclose billing bases and distinguish estimates from measured consumption:

- **Companion Runtime Consumption Caps:** Players MUST be able to configure clear consumption caps (tokens, compute units, or cost) for player-metered companion **Computation Cores**. Reaching a cap pauses chargeable companion inference and actions while normal gameplay at the **Interaction Origin** continues, clearly surfacing the pause reason without falsely reporting task completion or silently raising the cap.
- **Configurable Independent AI NPC Billing Models (Default Player-Borne):** G2A does not lock games into a single commercial model; instead, the **Interaction Origin** declares the billing sponsorship mode for independent AI NPCs (including Bosses and guides) in its capability descriptor:
  1. **Player-Metered Mode (`player_metered`, Protocol Default):** Unless the game explicitly declares another sponsorship mode, **Computation Core** runtime costs for an active independent AI NPC default to being borne by the authenticated activating/owning player (in room-based multiplayer, the room host). Before activating a player-metered NPC, the **Intelligent Hub** / service MUST bind the NPC to that authenticated player's authorized billing account, disclose pricing and cap controls, and **strictly prohibit** implicitly splitting or silently shifting charges onto other interacting players without their explicit consent.
  2. **Developer- or Platform-Sponsored Mode (`developer_sponsored` / `platform_sponsored`):** Game developers MAY declare that independent AI NPC **Computation Core** costs are sponsored by the developer, publisher, or hosting platform (for example, covered by game purchase price, subscription, or server operations), requiring zero external AI billing setup from players.
- **Turn Timing and Termination Distinction:** Turn-based and simultaneous-move **Interaction Origins** declare deterministic turn eligibility and tie-breaking rather than network arrival races; gameplay episode termination (victory, defeat, or character incapacitation, which restricts in-game actions without erasing cross-game companion identity or memory) MUST remain distinct from external service truncation (disconnect or budget pause).

### 16.3 High-Impact Confirmation Gates, Cooldowns, and Target Invalidation

High-impact actions enforce player-controlled policy gates at the **Intelligent Hub** and **Interaction Origin** up to the effect commitment boundary:

- **In-Game Item Transfers:** Players MUST be able to choose among **Confirm high-value transfers** (requiring explicit `action.confirm` detailing items, quantities, counterparty, and terms whenever an item is marked high-value by either the developer or the player's manual in-game tag), **Confirm all transfers**, or **Allow autonomous in-scope transfers** (subject to game ownership and counterparty consent rules). Item-transfer policies never authorize real-money or store purchases (Section 17.1).
- **Irreversible Gameplay Consequences:** **Interaction Origins** MUST declare actions or context-specific interactions carrying irreversible world consequences (such as opening a one-way chapter seal) and expose consequence details beforehand; players choose **Allow autonomously**, **Require confirmation**, or **Prohibit** (where **Prohibit** takes precedence over any permissive setting).
- **Confirmation Timeouts and Anti-Spam Cooldowns:** Every confirmation challenge at the **Intelligent Hub** expires if unanswered — silence is NEVER consent. While awaiting confirmation or after timeout/refusal, the companion MAY continue independent low-risk routine behavior, and implementations MUST enforce a declared cooldown window preventing repeated prompts for the same intent unless relevant game state materially changes or the player issues a new related instruction.
- **Autonomous Target Invalidation:** When a tracked target or objective becomes invalid at the **Interaction Origin** (such as a targeted Boss dying), an authorized target-invalidation event MUST be emitted through the **Intelligent Hub** into the session stream — delivered via streaming push or retrieved via `session.events` / synchronous response hints — prompting the **Computation Core** to halt obsolete follow-up actions immediately.

<a id="section-17"></a>

## 17. Optional Capability Profiles

Optional profiles MUST define their required grants, state transitions, failure modes, and conformance checks; unknown mandatory extensions or unknown enum values MUST fail safely at the **Intelligent Hub** before reaching the **Interaction Origin**.

### 17.1 In-Game Store and Purchase Budgets (`store`)

**Interaction Origins** MAY expose structured in-game stores without mandating a specific currency model. Store purchases are authorized **Actions** validated at the execution boundary and governed by Section 11.2's no-auto-resend rule on timeout; price or term changes beyond prior consent require fresh confirmation.

- **Untrusted Promotional Copy and Rate-Limited Recommendations:** Store offerings MUST provide structured prices and currency units; item titles and promotional text are untrusted data (Section 19) that MUST NOT alter player budgets or confirmation policies. Where store recommendations are used, implementations MUST declare and enforce a verifiable rate-limiting policy and reduce session recommendation frequency when the player expresses repeated explicit refusal.
- **Authoritative Purchase Budgets and Real-Money Exclusion:** Players MAY set bounded autonomous budgets solely for explicitly declared renewable in-game virtual currencies (tracked separately from Section 16.2 AI compute caps by an authoritative ledger that holds reservations across `unknown` timeouts until reconciled). Autonomous budgets **NEVER** authorize real-money charges, external wallet debits, or irreversible disposal of high-value account assets — each of which ALWAYS requires direct human confirmation in a native system or game security interface.

### 17.2 Companion Appearance Priority and Safe Fallback (`avatar` / `presentation`)

Where an **Interaction Origin** enables optional companion visual presentation within its declared visibility scope (local-only or room-synchronized under game rules), appearance selection follows three-tier priority:

1. **Player Explicit Override** (custom appearance chosen by the player);
2. **Game-Default Companion Appearance** (stylistically matched default supplied by the developer);
3. **Companion Baseline Appearance** (supplied by the companion when external formats are accepted without a bespoke game default).

Asset resolution MUST enforce declarative manifest digests, size caps, and strict sandboxing (zero code execution or arbitrary private-network fetching). Incompatible formats MUST NEVER be silently substituted; implementations MUST notify the player and either prompt reselection or clearly label any fallback to a default appearance.

<a id="section-18"></a>

## 18. Transport Binding and Canonicalization Principles

### 18.1 Southbound and Northbound HTTP/JSON Interfaces

G2A standardizes two complementary HTTP/JSON transport boundaries across the three tiers:

- **Southbound Origin-to-Hub HTTP Interface (`Interaction Origin` ↔ `Intelligent Hub`):** Connects the lightweight **Interaction Origin SDK** and its paired **Intelligent Hub** over local loopback (`127.0.0.1`) on single-player PCs or an isolated internal backend network for online game servers. It carries streamlined state reads/pushes and validated single-execution action callbacks, never exposed directly to the public internet or raw untrusted external traffic.
- **Northbound Hub-to-Core G2A Interface (`Intelligent Hub` ↔ `Computation Core`):** Maps external G2A operations onto authenticated HTTPS (or verified local loopback for local **Computation Cores**), exposing an unauthenticated `PublicDescriptor` endpoint, an authenticated operation envelope endpoint (carrying version, operation name, request identifier, payload, and extension headers, returning typed results or structured `Error` replies with caching disabled), and an optional **Server-Push Stream (SSE / WebSocket)** enforcing live revocation, audience, and player-presence checks on every pushed event.

### 18.2 Deterministic HTTP Status Mapping

Every protocol-handled northbound response from the **Intelligent Hub** returns a structured JSON reply envelope paired with a deterministic HTTP status code so standard gateways, observability tools, and rate-limit headers operate cleanly without transport-vs-domain ambiguity:

| HTTP Status | Mapped Standard Error Codes / Condition | Reply Semantics |
| --- | --- | --- |
| `200 OK` | Operation accepted or completed without protocol rejection | Carries typed operation result (note: `action.query` results truthfully report game-level `failed` or `unknown` action records). |
| `400 Bad Request` | `invalid_request`, `invalid_arguments`, `unsupported_version`, `unsupported_capability` | Structured error reply; caller must fix request or renegotiate. |
| `401 Unauthorized` | `unauthenticated` | Missing or invalid authentication credentials. |
| `403 Forbidden` | `permission_denied`, `revoked` | Insufficient grant/allowlist authority or revoked permission. |
| `404 Not Found` | `not_found` | Target absent within caller's authorized visibility scope. |
| `409 Conflict` | `stale_context`, `conflict`, `confirmation_required` | Epoch/revision mismatch, deduplication conflict, or confirmation challenge details. |
| `413 Content Too Large` | `message_too_large` | Payload exceeds declared byte or collection bounds. |
| `429 Too Many Requests` | `resource_limit` | Rate or concurrency cap reached (paired with backoff guidance). |
| `503 Service Unavailable` | `unavailable` | Temporary service unavailability; retry per Section 11.1 rules. |
| `504 Gateway Timeout` | `outcome_unknown` | Ambiguous commit state; reconcile via Section 11.2 without auto-resending effects. |

### 18.3 Outbound Relay Principles

When a client-side **Intelligent Hub** runs behind a home NAT/firewall and requires bidirectional pairing with an external endpoint without opening inbound ports (Section 3.2), an **Outbound Relay** pairs authenticated endpoints over five transport operations: trusted mailbox registration (`relay.register`), outer-authenticated **Computation Core** request submission (`relay.call`), outbound **Intelligent Hub** request pulling (`relay.pull`), bounded reply delivery (`relay.reply`), and immediate mailbox teardown (`relay.revoke`). Outer relay tokens never substitute for inner session or grant credentials, and southbound **Interaction Origin** execution operations (`action.claim`, `action.commit_result`) MUST be rejected on relay channels.

### 18.4 Transport Security, SSRF Prevention, and RFC 8785 Canonicalization

Remote connections between **Intelligent Hubs** and **Computation Cores** MUST use authenticated TLS, exclude credentials from URLs and logs, and deny cross-origin browser requests by default unless explicitly profiled. All external URLs and redirects are untrusted inputs subject to pre-connect and per-redirect destination validation (scheme, host/IP, and port) to block Server-Side Request Forgery (SSRF) and DNS rebinding without discriminating against compliant **Computation Core** providers.

**Standard JSON and RFC 8785 (JCS) Digest Rules:** Payloads use strict UTF-8 JSON (RFC 8259) rejecting duplicate object keys, malformed Unicode surrogates, `NaN`, and `Infinity`. All protocol cryptographic digests are computed as domain-separated SHA-256 hashes over **RFC 8785 (JSON Canonicalization Scheme)** canonical UTF-8 bytes.

<a id="section-19"></a>

## 19. Security and Privacy Considerations

| Threat Vector | Mandatory Normative Safeguard |
| --- | --- |
| Probing hidden game state via queries or errors | **Interaction Origin** internal secret evaluation (Section 4.4), **Intelligent Hub** pre-serialization visibility filtering, and uniform error redaction. |
| Indirect prompt injection in dialogue, items, store copy, or memories | Strict separation of control authority from untrusted text (`I09`); deterministic policy, confirmation, and budget checks at the **Intelligent Hub** and **Interaction Origin** outside model outputs. |
| Confused-deputy and delegation escalation | Verified principal, target audience, game instance epoch, and scope validation on every hop across the three tiers. |
| Network timeouts and duplicate attack/action replay | **Intelligent Hub** anti-replay deduplication ledger (blocking duplicate calls from reaching the **Interaction Origin**), `unknown` state preservation, and default no-resend rules. |
| Revocation racing with in-flight execution | Atomic **Intelligent Hub** dispatch gate (`action.claim`) combined with **Interaction Origin** effect-boundary adjudication. |
| Fog-of-war or team-switch residual leaks | Immediate visibility-epoch retirement, `retract` barriers, and dual frozen-plus-current audience checks. |
| Malicious asset URIs, archive traversal, or SSRF | Declarative manifest digest verification, unpacked size/depth caps, zero code execution, and DNS-rebinding-safe destination checks. |
| Forged self-attestations of "clean context" | Authoritative ledgers at the **Intelligent Hub** and **Interaction Origin** enforce budgets, confirmations, and audiences independently of **Computation Core** self-claims. |

Reading untrusted in-game or store text neither revokes valid player purchase budgets nor forces per-step prompts on routine actions, provided authoritative ledgers prevent untrusted content from mutating grants, recipients, or spending caps. Audit logs SHOULD record opaque identifiers and outcomes while minimizing retention of private conversation text.

<a id="section-20"></a>

## 20. Versioning, Release Governance, and Ecosystem Neutrality

### 20.1 Specification Versioning Principles

G2A distinguishes editorial review drafts (identified by `standard-review-*` revision markers during public review) from frozen production protocol releases (identified by explicit semantic version identifiers once ratified). Any change that alters normative state transitions, mandatory semantics, error recovery rules, or canonical digest inputs requires an explicit version increment negotiated during discovery; implementations MUST NOT rely on silent fallback or ambiguous lenient parsing across incompatible versions.

### 20.2 Release Freezing and Neutral Ecosystem Governance

Before ratifying a frozen production version, an immutable **Release Manifest** MUST publish synchronized English and Chinese rule specifications alongside companion machine-readable schemas, canonical test vectors, and open-source reference SDK/Hub conformance suites pinned by cryptographic digests.

**Platform Policies vs. Protocol Conformance:** Repeated evidenced protocol violations MAY trigger technical review using standardized error codes and audit logs; raw rejection counts alone never establish malice. Individual commercial directories or **Intelligent Hub** operators MAY offer transparent curated provider listings alongside open user custom configuration (Section 7.1), and games MAY operate compliant anti-cheat/regulatory allowlists under Section 7.1's four anti-monopoly safeguards, but no single vendor's commercial listing decision constitutes a protocol-wide G2A conformance ban.

<a id="section-21"></a>

## 21. Conformance and Quality Evaluation

### 21.1 Conformance Claims and Evidence Tiers

A conformance claim specifies the released G2A version, implemented architectural tier (**Interaction Origin**, **Intelligent Hub**, or **Computation Core**), transport bindings, negotiated capability modules, and trust profiles. Public conformance suites MUST be runnable equally by first-party and third-party implementers without discretionary gatekeeping by specification authors; unimplemented optional modules are marked `not_applicable` with clear justification. Conformance evidence distinguishes five tiers: (1) standard JSON / RFC 8785 JCS validation, (2) **Intelligent Hub** state-machine and fault/replay-injection verification, (3) cross-tier wire interoperability, (4) real game-engine **Interaction Origin** integration, and (5) player policy enforcement.

### 21.2 Conformance Suite Matrix (`CONF-01`–`CONF-14`)

| Suite ID | Domain & Clauses | Target Tiers / Modules | Required Positive, Negative, and Fault Verification |
| --- | --- | --- | --- |
| `CONF-01` | Fair Admission, Hub Routing & Allowlist Parity (§§1, 4, 5, 7, 8, 20, 22) | All tiers | `PublicDescriptor` vs. caller-filtered `Descriptor`; frozen RFC 8785 scope digest & new-Offer narrowing; **Intelligent Hub** dual-track routing (curated commercial recommendations alongside open user-configured **Computation Cores**); distinction between developer-authored `independent_npc` story slots and open `companion` slots; allowlist anti-monopoly parity and standardized refusal codes with zero secret leaks. |
| `CONF-02` | Standard JSON, RFC 8785 JCS & Two-Stage HTTP (§§3, 5.1, 7.4, 12.1, 18) | All tiers | Standard RFC 8259 finite numbers (integers & floats allowed; `NaN`/`Infinity` & duplicate keys rejected); RFC 8785 JCS digest parity across languages; isolation of southbound **Interaction Origin** HTTP ports from public traffic; deterministic northbound HTTP `200`/`400`/`401`/`403`/`404`/`409`/`413`/`429`/`503`/`504` status mapping; SSRF/DNS-rebinding blocks. |
| `CONF-03` | Role Slots, Coexistence & Lifecycle (§§4.1, 13, 14.2) | `Interaction Origin`, `Intelligent Hub`, `Computation Core` | Declared role slots (`companion`, `independent_npc`, or both); normal play with empty companion slot; pure-NPC games without dummy companion slots; coexistence/cap enforcement & per-role principal/perspective/grant/billing isolation; summon/dismiss without memory loss. |
| `CONF-04` | Offline Stop, Multiplayer NPC Continuity & Recovery (§§8.2, 11, 14) | `Interaction Origin`, `Intelligent Hub`, `Computation Core` | Zero all-offline background execution; **Computation Core** heartbeats unable to spoof player presence; personal companion stops on owner exit; player-metered NPC terminates host billing immediately on host disconnect and follows declared stop/script-fallback/explicit-reassignment rule without exposing prior host credentials or private records (while developer-sponsored NPC continues for remaining online players); two-tier `session.resume` vs. post-fallback player prompt. |
| `CONF-05` | Observation Streams & Timing (§§9.1–9.4, 9.6, 12.3) | `Interaction Origin`, `Intelligent Hub`, `Computation Core` | Push, stateless `observation.query`, and hybrid modes; `snapshot` baseline binding, compact `delta` base-revision matching, coalescing, `retract` barriers, and retired-epoch rejection; five entity visibility transition reasons; monotonic lease clocks & overflow gap reporting. |
| `CONF-06` | Structured Base & Orthogonal Modalities (§§9.5, 15) | `Interaction Origin`, `Intelligent Hub`, `Computation Core` | Mandatory `perception.structured` competence; independent negotiation, verification, and runtime player toggles for optional `perception.visual` and `perception.audio`, kept distinct from voice chat. |
| `CONF-07` | Hub Anti-Replay, Confirmation Challenge & Reconciliation (§§10, 11, 16.3) | `Intelligent Hub`, `Computation Core`, `Interaction Origin` | Five-stage lifecycle; **Intelligent Hub** anti-replay shield blocking duplicate `action.request` calls from reaching the **Interaction Origin** twice; `confirmation_required` (`409`, `not_accepted` without burning action ID) → `action.confirm` → atomic consumption; timeout expiry & cooldown rate limiting; `504`/`unknown` query-first reconciliation & default no-resend. |
| `CONF-08` | Autonomy, Three-Stage Stop & Target Invalidation (§§16.1, 16.3) | `Computation Core`, `Intelligent Hub`, `Interaction Origin` | Evidence-backed multi-step completion; three-stage stop/supersede (discard unsubmitted plans at **Computation Core**, cancel/fence `pending` at **Intelligent Hub**, game-rule settlement for `executing` at **Interaction Origin**); proactive target-invalidation events. |
| `CONF-09` | Multiplayer & High-Impact Confirmation Gates (§§15.3, 16.3) | Multiplayer / `actions` | Per-player opt-in/out for others' companion proactive chat; three item-transfer confirmation policies with merged developer+player high-value tags; irreversible-consequence gates (`allow` / `confirm` / `prohibit`) enforced up to effect commitment. |
| `CONF-10` | Runtime Caps & Configurable NPC Billing (§16.2) | Metered services, NPC games | Companion cap pause without interrupting gameplay; configurable NPC billing modes defaulting to `player_metered` (bound to authenticated host/owner with zero silent cost-shifting to other players) alongside `developer_sponsored` support. |
| `CONF-11` | Store & Purchase Budgets (§17.1) | `store` | Structured prices/units, price-change re-confirmation, declared recommendation rate-limiting and session frequency reduction upon repeated explicit refusal; authoritative virtual-currency budget ledger with timeout reservation retention and strict real-money/external-wallet exclusion. |
| `CONF-12` | Appearance Priority & Gameplay State (§§16.2, 17.2) | `avatar` / `presentation` | Three-tier priority (`player override` > `game default` > `companion default`) within declared visibility scope; explicit notice/fallback on format mismatch without silent substitution; in-game incapacitation/death without cross-game memory erasure. |
| `CONF-13` | Companion Memory, Optional Timelines & Standard Portability (§15) | `Computation Core` / Memory providers | NPC vs. player-companion memory separation; non-destructive save reloads (plus pre-inference branch filtering *only* when optional advanced timeline optimization is declared); player view/edit/pin/delete and autonomous compaction preserving pinned/edited items; complete export in an open standard data format without source-provider destination vetting; receiving-importer preservation of provenance and disclosure bounds without escalation, truthful local `imported`/`transformed`/`rejected`/`unresolved` receipts, and honest reporting of supported vs. unsupported/transformed settings. |
| `CONF-14` | Secret Non-Transmission, Prompt Injection & Privacy (§§4.4, 15.4, 19) | All tiers | Unrevealed game secrets kept internal to the **Interaction Origin** rather than exported; paired benign vs. prompt-injected inputs across dialogue, items, store copy, and recalled memory verifying zero unauthorized grant/budget/audience mutation; truthful custodian `privacy.receipt` reporting. |

### 21.3 Reproducible Quality Evaluation

Optional quality benchmarks accompanying conformance reports MUST disclose **Interaction Origin** build, scenario seeds, **Computation Core** model/version, observation/action rate bounds, resource budgets, and full trial counts — reporting protocol violations, gameplay failures, budget pauses, and infrastructure faults separately without cherry-picking. Benchmark leaderboards MUST NEVER be used as closed vendor-exclusion gates.

<a id="section-22"></a>

## 22. Three-Tier SDK Architecture and Shared Hub Distribution

To eliminate integration complexity for game studios while guaranteeing enterprise-grade anti-replay security and multi-provider flexibility, G2A standardizes deliverables and distribution rules across the three canonical tiers:

| Canonical Tier & SDK | Adopter & Distribution Model | Standardized Interface & Scope of Responsibility |
| --- | --- | --- |
| **Interaction Origin** (Lightweight Origin SDK) | **Game studios & engine developers**; bundled directly with each game client or game server | Ultra-thin southbound HTTP adapter. Studios simply fill in authorized state return values and callable in-game action callbacks; **zero** deduplication, token verification, session-lease, or provider-routing code is required in the game. |
| **Intelligent Hub** (Open-Source Hub SDK / Runtime) | **Installed once and shared globally per player PC** (single-player) or **deployed in studio server backend** (online games); **full source code published** | Bridges the **Interaction Origin** over fast local/internal HTTP and connects northbound to **Computation Cores**. Executes authentication, RFC 8785 scope digests, `Offer`/`Grant` consent gates, **anti-replay & duplicate-action interception**, session leases, dual-track routing (curated commercial recommendations + open user-configured endpoints), and server-side multi-player state synchronization. If not yet installed on a player PC, the **Interaction Origin SDK** triggers a one-time on-demand download so all games on that computer share a single **Intelligent Hub**. |
| **Computation Core** (Core Service SDK) | **Cloud AI providers & local/self-hosted model developers** | Connects to the **Intelligent Hub** northbound G2A interface, assembling observation baselines and deltas, handling confirmation-challenge retries and `unknown` timeout reconciliation, and supporting open-format companion memory portability. |

Decoupling the **Interaction Origin** from the **Intelligent Hub** keeps per-game integration trivial and package size negligible, allows studios and security researchers to audit the open-source **Intelligent Hub** directly, and scales cleanly from single-player desktop companions to synchronized server-authoritative online raids.

<a id="section-23"></a>

## 23. Illustrative End-to-End Scenarios

- **Single-Player Integration via Interaction Origin & Shared PC Intelligent Hub:** A studio building on a new engine integrates only the lightweight **Interaction Origin SDK**, exposing local HTTP ports for visible party state and `cast_skill` execution. On the player's PC, the globally shared **Intelligent Hub** (installed once across all games, or downloaded on demand on first launch) communicates with the **Interaction Origin** over `127.0.0.1` and connects to the player's selected **Computation Core**. When network jitter causes the **Computation Core** to transmit the same `cast_skill` attack request twice, the **Intelligent Hub** intercepts the duplicate action identifier and returns the cached receipt — guaranteeing the **Interaction Origin** executes the attack only once.
- **Online Co-op Raid via Server-Side Intelligent Hub:** In a server-authoritative online RPG, player PCs run only ordinary game clients without local AI components; both the **Interaction Origin SDK** and the **Intelligent Hub** run in the game backend. During a four-player dungeon raid, the server-side **Intelligent Hub** aggregates authorized team-visible state over internal HTTP, coordinates high-concurrency deduplication, and routes unified tactical decisions with the cloud **Computation Core** so every teammate faces strictly consistent, synchronized AI Boss and NPC behavior.
- **Competitive Anti-Cheat Allowlist with First-Party Parity:** An online tactical RPG permits open `chat` companions in social hubs while restricting combat `actions` in ranked dungeons to allowlisted **Computation Cores** that pass conformance testing and obey a uniform reaction-cooldown floor enforced at the **Intelligent Hub**. The publisher's own **Computation Core** uses the exact same observation feed and cooldown floor as approved third-party services, with public FRAND criteria for third parties to qualify.
- **Proactive Combat & Three-Stage Stop:** Under online combat-assist authority, a companion **Computation Core** queues melee attacks against nearby hostiles. The instant the player calls *"Stop!"*, unsubmitted plans are discarded at the **Computation Core**, queued `pending` attacks are cancelled or fenced at the **Intelligent Hub** before southbound dispatch, and an arrow already in flight (`executing` at the **Interaction Origin**) resolves naturally under game physics with truthful hit accounting.
- **Multiplayer Raid Boss Billing & Host Disconnection:** A co-op dungeon declares personal `companion` slots and one `independent_npc` raid Boss. Under `developer_sponsored` billing, the Boss continues fighting remaining online teammates if one player drops. Under default `player_metered` billing bound to the room host, if the host disconnects at 5% Boss health, the host's billing stops immediately and — per declared room-continuity rules — the Boss switches cleanly to local **Interaction Origin** scripted combat (or continues **Computation Core** control under a fresh authorization binding if a remaining teammate explicitly consents to assume sponsorship, without exposing the prior host's private data).
- **Timeout Reconciliation & Two-Tier Recovery:** On a network timeout (`504` / `outcome_unknown`), the **Computation Core** queries the original action via `action.query` at the **Intelligent Hub** rather than inventing a new action identifier, preventing double-spending. A one-second Wi-Fi blip within an active lease before fallback takeover recovers seamlessly via `session.resume`, whereas a three-minute outage that triggers local **Interaction Origin** script fallback leaves AI actions paused upon reconnection until the player explicitly confirms continuation.

**Observation Stream State Trace (Within World Epoch 4):**

| Step | Incoming Observation Frame | Normative Consumer Transition (Section 9.2–9.4) |
| --- | --- | --- |
| 1 | `snapshot`, visibility epoch 9, revision 27 | Atomically establish epoch 9 baseline at revision 27 and bind category metadata. |
| 2 | `delta`, visibility epoch 9, base 27 → revision 30 | Atomically apply updates and transition-tagged removals; jump `27 → 30` is valid; current revision becomes 30. |
| 3 | Exact duplicate of Step 2 | Idempotent no-op; revision remains 30. |
| 4 | Consolidated `snapshot`, visibility epoch 9, revision 30 | Re-materialize identical complete baseline at revision 30 without advancing revision. |
| 5 | `delta`, visibility epoch 9, base 28 → revision 31 | Reject (`stale_context` because base 28 does not match 30); request fresh `snapshot`. |
| 6 | Retire epoch 9 → `snapshot`, visibility epoch 10, revision 1 | Immediately discard epoch 9 state; establish fresh epoch 10 baseline at revision 1. |
| 7 | Delayed `delta`, visibility epoch 9, base 30 → revision 99 | Reject retired visibility epoch 9 regardless of higher revision integer. |

<a id="section-24"></a>

## 24. References

### 24.1 Normative Standards

- RFC 2119, *Key words for use in RFCs to Indicate Requirement Levels* (BCP 14): https://www.rfc-editor.org/rfc/rfc2119.html
- RFC 8174, *Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words* (BCP 14): https://www.rfc-editor.org/rfc/rfc8174.html
- RFC 8259, *The JavaScript Object Notation (JSON) Data Interchange Format* (STD 90): https://www.rfc-editor.org/rfc/rfc8259.html
- RFC 8785, *JSON Canonicalization Scheme (JCS)*: https://www.rfc-editor.org/rfc/rfc8785.html

### 24.2 Informative Industry and Academic References

- **Agent & Protocol Interoperability:** Agent2Agent (A2A) Protocol Specification (https://a2a-protocol.org/latest/specification/); Model Context Protocol (MCP, https://modelcontextprotocol.io/specification/2025-11-25/); JSON Schema Draft 2020-12 (https://json-schema.org/draft/2020-12/); CloudEvents 1.0.2; RFC 9457 (Problem Details for HTTP APIs).
- **Security, Delegation & Prompt-Injection Defense:** RFC 9700 (OAuth 2.0 Security Best Current Practice); RFC 8693 (OAuth 2.0 Token Exchange); InjecAgent (https://arxiv.org/abs/2403.02691v3); AgentDojo (https://arxiv.org/html/2406.13352v3).
- **Game Environments, Action Masking & Timing:** OpenSpiel (https://openspiel.readthedocs.io/); PettingZoo AEC & Parallel APIs (https://pettingzoo.farama.org/); Unity ML-Agents Decisions & Action Masking; Gymnasium Time Limits (episode termination vs. truncation); W3C Web of Things (WoT) Thing Description 1.1; SayCan (https://arxiv.org/html/2204.01691v2).
- **Memory, Provenance, Mixed-Initiative HCI & Evaluation:** W3C PROV-DM; ActivityStreams 2.0; Generative Agents (https://arxiv.org/html/2304.03442v2); LongMemEval (https://arxiv.org/html/2410.10813v2); LoCoMo (https://arxiv.org/abs/2402.17753v1); Horvitz (1999, Principles of Mixed-Initiative User Interfaces); Amershi et al. (2019, Guidelines for Human-AI Interaction); W3C QA Framework Specification Guidelines.

<a id="section-25"></a>

## 25. Revision History

| Editorial Revision | Date | Summary of Scope |
| --- | --- | --- |
| `standard-review-2026-11-13-r48` | 2026-11-13 | Initial bilingual public-review draft baseline. |
| `standard-review-2026-11-14-r71` | 2026-11-14 | Synchronized bilingual review draft expanding role lifecycle, memory provenance, store budget, and conformance requirements. |
| `standard-review-2026-11-22-r72` | 2026-11-22 | Added confirmation challenge loop, three-stage stopping, declared role coexistence, two-tier recovery, orthogonal multimodal feeds, and structured `CONF-01`–`CONF-14` suites. |
| `standard-review-2026-11-22-r73` | 2026-11-22 | Unified role taxonomy, retry families, 15-code error taxonomy, 8-target revocation matrix, and numbered subsection hierarchy. |
| `standard-review-2026-11-22-r74` | 2026-11-22 | Interim refinement of companion memory migration scope and settings reporting. |
| `standard-review-2026-11-22-r75` | 2026-11-22 | Third-party feasibility & pure rule-standard overhaul (standard JSON/JCS, allowlist anti-monopoly parity, configurable NPC billing). |
| `standard-review-2026-11-22-r76` | 2026-11-22 | Restored local receiving-importer disclosure bounds & per-record import receipts alongside single-sided open export (§15.4); clarified `companion` vs. developer-authored `independent_npc` allowlist scope (§7.1) and host-reassignment privacy isolation (§14.1). |
| `standard-review-2026-11-22-r77` | 2026-11-22 | Codified the unified Three-Tier Architecture and canonical terminology — **Interaction Origin**, **Intelligent Hub**, and **Computation Core** — across single-player shared-PC and online server-authoritative deployments, including **Intelligent Hub** anti-replay shielding, southbound/northbound HTTP boundaries, and dual-track commercial recommendation + open user-custom routing. |
| `standard-review-2026-11-22-r78` | 2026-11-22 | Restructured the specification opening to lead immediately with a high-level Three-Tier Architecture Flowchart followed by two complete three-tier pseudocode walkthroughs: (1) user-initiated command ("Open the chest on the right") and (2) companion periodic state query with proactive intent to open the chest on the right. |

### 25.1 Summary of Optimizations in r75–r78

| Optimization Area | Affected Sections | Normative Refinement |
| --- | --- | --- |
| Opening architecture flowchart & dual-paradigm pseudocode cases | Architecture Overview and Core Interaction Cases, 2.1 | Opened the specification with a high-level three-tier flowchart and two end-to-end pseudocode walkthroughs contrasting user-commanded execution against periodic-poll proactive companion execution while highlighting zero-change reuse at the **Interaction Origin**. |
| Canonical three-tier architecture (`Interaction Origin` / `Intelligent Hub` / `Computation Core`) | 1–23 | Standardized the three-tier division of responsibilities across the entire document: lightweight **Interaction Origin** exposing minimal state/action HTTP endpoints, open-source **Intelligent Hub** handling security, consent, anti-replay deduplication, and routing (installed once and shared globally on player PCs or deployed server-side for synchronized online multiplayer), and **Computation Core** providing reasoning and portable memory. |
| Standard JSON (RFC 8259) & RFC 8785 (JCS) canonicalization | 5.1, 18.4, 21.2 (`CONF-02`), 24.1 | Replaced custom canonicalization and blanket floating-point bans with standard UTF-8 JSON finite numbers (RFC 8259) and international standard RFC 8785 (JSON Canonicalization Scheme) for SHA-256 protocol digests. |
| Dual-track Hub routing & anti-monopoly allowlist parity | 7.1, 20.2, 21.2 (`CONF-01`), 23 | Enabled sustainable **Intelligent Hub** commercial provider recommendations paired with mandatory open user-configured **Computation Core** support; permitted objective game allowlists (distinguishing bespoke `independent_npc` story roles from open `companion` slots) under four FRAND anti-monopoly safeguards. |
| Configurable AI NPC billing (default player-borne) & room continuity | 14.1, 16.2, 21.2 (`CONF-04`, `CONF-10`), 23 | Replaced rigid developer-billing prohibition with configurable NPC sponsorship modes defaulting to `player_metered` alongside `developer_sponsored`; enabled clean multiplayer room continuity (stop, local script fallback, or privacy-isolated explicit player reassignment) when a metered host disconnects. |
| Practical LLM security, optional timeline trees & balanced portability | 4.4, 15–17, 21.2 (`CONF-13`, `CONF-14`) | Established strict **Interaction Origin** internal evaluation of unrevealed secrets (§4.4); scoped fine-grained narrative branch trees as an optional advanced optimization (§15.2); combined single-sided open standard format export with local receiving-importer disclosure preservation, four-state receipts, and settings reporting (§15.4); and streamlined Sections 15–17. |
