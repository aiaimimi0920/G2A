# G2A Specification

**Game-to-Agent Interaction Protocol**

An open rule standard defining identity, observation, authorization, and action boundaries among games, players, and AI agents.

Status: Working Draft for Public Review. Editorial revision: `standard-review-2026-11-22-r76`. Revision date: November 22, 2026.
Document role: Normative protocol rule specification. Concrete language APIs, machine schemas, and engine integration bindings are delivered separately through standard plugins and developer toolkits.

Language pair: this English master and the [complete Chinese specification](G2A_SPECIFICATION.zh-CN.md) share the same editorial revision and normative structure. See [Section 25](#section-25) for traceable revision history.

## Contents

1. [Purpose and Scope](#section-1)
2. [Conventions and Document Authority](#section-2)
3. [Architecture, Topologies, and Applicability](#section-3)
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
22. [Standard Plugin Integration and Implementation Layering](#section-22)
23. [Illustrative End-to-End Scenarios](#section-23)
24. [References](#section-24)
25. [Revision History](#section-25)

## Protocol Overview

Games feature diverse worlds, visibility rules, and action spaces. G2A establishes a vendor-neutral interaction standard between a **Game** (exposed through a designated **Game Interaction Node**) and a **Game Agent** authorized to inhabit an in-game role — primarily a **Player Companion**, or an optional **Independent AI NPC** (such as a Boss or guide).

| Participant | Core Role in the Interaction Loop |
| --- | --- |
| **Human Player** | Controls the player character directly and governs consent, companion autonomy preferences, confirmation policies, and permission revocation through an authenticated consent channel. |
| **Game World & Rules** | Holds exclusive authority over world state, visibility, physics, and rule adjudication. |
| **Game Interaction Node** | Publishes authorized game observations, verifies permissions, and coordinates in-game action execution on behalf of the game. |
| **Game Agent** | Local or cloud decision-making software authorized to perceive permitted game state and propose in-scope actions or dialogue for its bound in-game role slot. |

Three architectural boundaries govern every G2A interaction:

1. **The Game owns world truth and final execution:** The Game Interaction Node publishes authorized views of game state and determines whether requested actions succeed, fail, or produce partial effects under current game rules. The Game Agent is decision-making software, not an omniscient world controller.
2. **The Player governs authorization and companion policies:** Within boundaries permitted by the game, the player decides whether an Agent connects, what scope of permissions it receives, and how their personal companion behaves. Player preferences never expand game-offered capabilities or expose another participant's private data.
3. **The Agent owns internal reasoning and portable companion memory:** G2A standardizes observable interaction rules, permission boundaries, and standard-format data portability without prescribing a specific foundation model, reasoning architecture, memory database, or centralized account service.

<a id="section-1"></a>

## 1. Purpose and Scope

### 1.1 Design Goals and Four Pillars

G2A enables conforming games and conforming AI Agents to interoperate safely across local and cloud environments. The specification is organized around four pillars:

| Pillar | Normative Scope |
| --- | --- |
| Admission and Control | Principal authentication, capability discovery, fair admission governance, player consent, scoped grants, session leases, control handoff, and graded revocation. |
| Observations and Information Use | Authorized game-state views, snapshots and incremental updates, provenance, freshness, audience boundaries, multimodal feeds, and memory governance. |
| Actions and Outcomes | Role capability declarations, dynamic action eligibility, confirmation challenges, effect-boundary revalidation, cancellation semantics, and outcome reconciliation. |
| Interoperability and Governance | Conceptual protocol model, abstract operations, standard JSON/JCS canonicalization, transport rules, standard plugin encapsulation, and conformance suites. |

### 1.2 Core Architectural Distinctions

Five foundational distinctions apply across every layer of this specification:

- **Support is not authorization:** Declaring a capability indicates technical support; submitting a request expresses caller intent. Neither grants read or execution authority without an active player-approved grant and frozen session scope.
- **Acceptance is not completed execution:** Accepting or queuing an action request (`pending`) does not establish that its world effect has occurred. Queue acceptance, executor claim (`executing`), and committed world effect (`committed`) MUST remain strictly distinct.
- **Authorized reads do not imply continuing validity:** Observations reflect a restricted perspective at a specific world epoch and revision and become stale as gameplay state or visibility changes.
- **Omission is not non-existence:** Information omitted due to fog-of-war, permission filtering, or incremental compression MUST NOT be interpreted as a false fact, an empty world, or entity destruction.
- **Companion memory is separate from current world state:** Reloading a save, starting a new playthrough, or switching narrative branches alters authoritative world state, but MUST NOT silently erase player-governed companion memories. Remembering an earlier playthrough does not make an event true in the current world or override game rules.

### 1.3 Scope Boundaries and Non-Goals

G2A is scoped strictly to game interaction: player-companion assistance, authorized AI NPC interaction, game-state observation, constrained in-game actions, and optional companion visual presentation.

G2A is **not** a general-purpose operating-system or desktop UI automation protocol. It does not standardize arbitrary remote code execution, undeclared screen or input capture, model weights, prompt templates, or internal commercial revenue-sharing contracts. While G2A enforces observable data, audience, and action boundaries, no communication protocol can erase prior general knowledge stored in model weights or prevent an endpoint from drawing internal inferences from facts already disclosed to it.

<a id="section-2"></a>

## 2. Conventions and Document Authority

### 2.1 Normative Keywords

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**, and **MAY** in this document are to be interpreted as described in RFC 2119 and RFC 8174 (BCP 14) when, and only when, they appear in all capitals. Overview tables, illustrative scenarios (Section 23), and revision notes (Section 25) are informative and do not introduce independent normative obligations. A permission expressed with **MAY** does not require every implementation to offer that optional feature.

### 2.2 Document Role and Conformance Scope

This specification is a **protocol rule and boundary standard**, not a language-specific API manual or source-code guide. It defines mandatory trust invariants, state transitions, authority checks, and ecosystem rules in implementation-neutral prose.

1. **Separation of Rules from SDK Implementations:** Concrete wire-field schemas, engine plugin APIs, and code-level bindings are published as companion developer specifications pinned under formal release manifests (Section 20). Standard game-engine plugins encapsulate low-level protocol mechanics automatically (Section 22).
2. **Honest Conformance Claims:** Implementations MUST state the exact released G2A version, supported roles, transport bindings, and optional capability modules they implement, and MUST NOT misrepresent partial draft support as full conformance to a frozen production release.

<a id="section-3"></a>

## 3. Architecture, Topologies, and Applicability

### 3.1 Three-Layer Architecture and Standard Plugin Integration

G2A separates interaction semantics from transport mechanics across three logical layers:

1. **Conceptual Model (Section 5):** Standard representations of principals, capability descriptors, permission scopes, grants, sessions, observations, actions, receipts, and errors.
2. **Abstract Operations and State Machines (Sections 6–17):** Transport-independent operations, authority checks, lifecycle transitions, confirmation gates, and recovery rules.
3. **Transport Bindings (Section 18):** Concrete network channels, standard JSON/JCS canonicalization, deterministic status mappings, streaming delivery, and NAT-traversal relays.

**Standard Plugin Integration Model:** Although the underlying protocol state machine enforces rigorous multi-step security and deduplication guarantees, **game and Agent developers are not expected to hand-wire low-level handshake operations in routine integration**. Official and conforming **Standard Game Engine Plugins and Agent SDKs** encapsulate discovery, negotiation, grant handshakes, lease heartbeats, deduplication, and reconnection automatically, exposing concise declarative hooks for registering observable game state and callable in-game actions (Section 22).

### 3.2 Deployment Topologies

Games operate across diverse network environments — from single-player clients behind home NAT to dedicated cloud servers. G2A supports three standard topologies without altering upper-layer rules:

| Topology | Connection Direction | Typical Scenario |
| --- | --- | --- |
| **Local Loopback / IPC** | Agent ↔ Local Game Node (loopback or OS IPC) | Desktop or mobile companion app running on the same device as a single-player or client-hosted game. |
| **Direct TLS / Streaming** | Agent → Reachable Game Node | Cloud or LAN Agent connecting to a game server or gateway exposing a reachable TLS endpoint (with optional server-push stream). |
| **Outbound Relay** | Game Node (outbound) → Paired Relay ← Agent | Single-player or P2P game client behind NAT/firewall interacting with a cloud Agent without opening inbound ports on the player's device (Section 18.3). |

### 3.3 Capability Modules and Applicability

Core conformance requires only session management, event/context delivery, and baseline structured perception; all other capabilities are negotiated explicitly according to game design:

| Capability Module | Requirement Tier | Primary Responsibilities |
| --- | --- | --- |
| `core.session` | Mandatory Core | Discovery, capability negotiation, scoped admission, session lease, recovery snapshot, closure, and error reporting. |
| `core.events` | Mandatory Core | Ordered recipient-visible event delivery, context publication, and within-session deduplication. |
| `perception.structured` | Mandatory Core (Gameplay Agents) | Interpreting negotiated structured game observations to make authorized role decisions. |
| `observation.query` | Optional | Stateless, authorized Agent-initiated reads of current observations without world side effects (Section 9.6). |
| `perception.visual` | Optional | Game-frame visual perception layered orthogonally atop `perception.structured` (Section 9.5). |
| `perception.audio` | Optional | Game-environment audio perception layered orthogonally atop `perception.structured`, distinct from voice chat (Section 9.5). |
| `actions` | Optional | Typed action requests, confirmation challenges, executor claim, effect-boundary validation, cancellation, and outcome queries (Section 10). |
| `chat` | Optional | Provenance- and audience-bound text or voice communication (Section 15). |
| `team` | Optional | Multi-participant seat bindings, membership revisions, and team-scoped audiences. |
| `resume` | Optional | Durable session ledgers and seamless reconnection within an active lease (Sections 11, 14.2). |
| `handoff` | Optional (requires `resume`) | Generation-fenced transfer of session control across verified devices or processes. |
| `multi-session` | Optional | Concurrent active sessions for the same Agent identity without silently evicting existing sessions. |
| `avatar` / `assets` / `presentation` | Optional | Companion appearance priority, safe declarative asset resolution, and device rendering leases (Section 17.2). |
| `store` | Optional | Structured in-game store offerings, rate-limited recommendations, and authoritative purchase budgets (Section 17.1). |
| `privacy-request` | Optional | Scoped data-deletion/cutoff requests and truthful custodian receipts (Section 15.4). |

<a id="section-4"></a>

## 4. Roles, Identity, and Trust

### 4.1 Core Trust Principals and Supporting Roles

G2A defines three primary trust principals and four optional supporting roles. Multiple roles MAY reside within a single process provided their logical authority boundaries remain strictly enforced:

| Role | Category | Authority and Responsibilities |
| --- | --- | --- |
| **Game Interaction Node** (`Game`) | Core Endpoint | The game-designated G2A interface and sole protocol source of authoritative current game state and action outcomes. Authenticates callers, enforces permission scopes, and coordinates with internal game logic. |
| **Game Executor** (`Game` internal) | Authoritative Component | Internal game subsystem that claims queued actions, enforces gameplay rules at the effect boundary, and commits final outcomes. Never exposed directly to external Agent credentials. |
| **Player / `PlayerConsent`** | Core Principal | The human player and the authenticated consent/control path through which the player approves permission offers, confirms high-impact actions, sets companion policies, and revokes access. |
| **Game Agent** (`Agent`) | Core Endpoint | Local or remote AI software authorized to inhabit a bound in-game role (Player Companion or Independent AI NPC). Consumes authorized observations, proposes in-scope actions, and manages internal reasoning and memory. |
| **Local Launcher** | Optional Role | Verifies pre-registered local application identity and starts a fixed binary under an explicit single-use launch grant without executing untrusted command strings. |
| **Presentation Endpoint** | Optional Role | Manages companion window or overlay rendering leases and safe declarative asset caching on a user device. |
| **Data Custodian** | Optional Role | Any participant (Agent provider, game, or platform) that persists player or companion records and therefore processes scoped privacy/deletion requests for data under its control. |
| **Outbound Relay** | Optional Transport Role | Forwards permitted operations between paired endpoints when the Game Node does not expose an inbound port, without holding Game administrative authority. |

The Game Interaction Node is an external protocol responsibility rather than a mandatory standalone server: single-player games MAY host it in-process via a standard engine plugin, while online games MAY expose it at the client or server gateway. Closing a G2A session ends that protocol binding without shutting down the game process or multiplayer room.

### 4.2 Principals, Instances, and Epochs

Caller identity MUST be established from transport-authenticated credentials; sender fields inside message payloads are checked only for consistency against authenticated identity and MUST NOT be trusted on their own. Implementations MUST keep four identity concepts distinct:

- **Principal Identity:** Uniquely identifies a player, Agent, game, or service within an issuer's namespace. Display nicknames carry zero authentication weight, and matching display names across different issuers MUST NOT be automatically merged.
- **Device Identity:** Identifies the physical or logical client endpoint holding presentation or session-control leases.
- **Game Instance:** Identifies a specific game run, match, or room so grants and credentials from one run cannot be replayed against another.
- **Epochs and Control Generations:** Monotonic or strictly non-reused markers (instance epoch, world epoch, visibility epoch, and session control generation) that immediately fence stale credentials, retired observation baselines, and superseded controllers after reloads, faction switches, or device handoffs.

### 4.3 Delegation and Trust Profiles

When a service or gateway acts on behalf of a player, verified **delegation** MUST bind the delegating player, delegate identity, target game instance, permitted scope, and expiration time. Routing through an intermediary NEVER adds the intermediary's own privileges to the represented principal's authority. Unverified claims inside chat or game text confer zero authority, and mere knowledge of a session, action, or correlation identifier grants neither read nor execution rights.

Deployments MUST declare and enforce compatible trust profiles without silent downgrade:

- **Locally Verified (`local-verified`):** Operating-system IPC or a trusted local launcher verifies binary and user bindings on the host device.
- **Provider Verified (`provider-verified`):** Authenticated TLS combined with cryptographic token or delegation verification binds player, Agent, target audience, and expiry across network boundaries.
- **Test Enrolled (`test-enrolled`):** Pre-registered development identities restricted to local testing and conformance harnesses; MUST NOT be represented as production security against untrusted local software.

Implementations MUST truthfully disclose plaintext visibility: unless end-to-end encryption is explicitly negotiated via a dedicated extension, the Game Interaction Node and any paired Outbound Relay can inspect messages traversing them and MUST NOT claim endpoint-only decryption.

### 4.4 Four-Way Permission Separation and Game-Internal Secrets

Implementations MUST independently enforce four non-interchangeable permission dimensions:

1. **Receive:** Information the Agent is permitted to obtain from the game or player.
2. **Disclose to Player:** Information the Agent is permitted to surface in player-facing conversation.
3. **Disclose Externally:** Information the Agent is permitted to transmit to the game, teammates, or external services.
4. **Act:** In-game capabilities and parameter bounds the Agent is permitted to invoke.

**Strict Non-Transmission of Unrevealed Game Secrets:** Generative AI models unify internal reasoning and dialogue generation within shared context. Whenever game rules strictly forbid revealing hidden state to the player or other participants (such as hidden enemy positions, unrevealed puzzle solutions, concealed cards, or secret trap triggers), the Game Interaction Node **MUST NOT** transmit the raw secret to the Agent. Instead, the game MUST evaluate hidden prerequisites internally and expose only authorized observable outcomes or current action eligibility.

<a id="section-5"></a>

## 5. Canonical Conceptual Model

### 5.1 Opaque Identifiers, Standard JSON Values, and RFC 8785 Digests

All protocol identifiers (such as descriptor, offer, grant, invitation, session, stream, request, and action identifiers) MUST be treated by consumers as opaque strings and MUST NOT be parsed to infer identity, privileges, or ordering. Transport request identifiers, message envelope identifiers, correlation identifiers, event sequence numbers, and observation revisions belong to separate namespaces and MUST NOT be conflated.

**Standard JSON Value Representation (RFC 8259):** Structured protocol data uses standard UTF-8 JSON (RFC 8259) rather than custom encoding formats:

- **Standard Finite Numbers:** Wire payloads MAY use both standard integers and finite IEEE-754 floating-point numbers (for example, engine-native spatial coordinates, velocities, angles, or probabilities), while strictly rejecting non-finite values (`NaN` and `Infinity`).
- **Precision Conventions:** Timestamps and durations SHOULD use integer milliseconds for unambiguous cross-platform comparison; currency amounts, store prices, and authoritative quota ledgers SHOULD use minor integer units or explicit decimal strings to avoid floating-point rounding drift.

**Standard Cryptographic Canonicalization (RFC 8785 JCS):** Whenever the protocol computes deterministic cryptographic digests over structured objects — such as freezing a negotiated permission scope or binding action confirmation terms — implementations MUST canonicalize the JSON structure according to **RFC 8785 (JSON Canonicalization Scheme, JCS)** encoded as UTF-8 and hashed with domain-separated SHA-256, enabling direct use of standard RFC 8785 libraries across programming languages.

### 5.2 Normative Conceptual Objects

The G2A interaction model is defined around fourteen logical concepts:

| Conceptual Object | Normative Role and Bound Semantics |
| --- | --- |
| **Public Descriptor** | Minimal unauthenticated discovery record advertising only the game instance identity, supported protocol versions, and authenticated discovery entry point, with zero player or session state. |
| **Descriptor** | Authenticated capability advertisement tailored to the caller, declaring supported versions, trust profiles, role slots and concurrency caps, supported/required capability modules, observation categories, callable action definitions, and resource limits. |
| **Scope** | Immutable snapshot of negotiated permissions binding the player, Agent, game instance, protocol version, role slot, enabled modules, approved observation categories, approved action definitions, recipient audiences, active policies, and expiration time. |
| **Offer** | Bounded admission proposal wrapping a frozen `Scope` and its RFC 8785 digest, tracking whether player approval is pending, approved, denied, expired, or invalidated by state changes (`stale`). |
| **Grant** | Active authorization record issued upon verified player consent (or a matching standing rule), binding the approved scope digest, approver evidence, revision number, and validity window. |
| **Invitation** | Short-lived, single-use session-join credential tying an approved `Grant` to a specific Agent identity, target game instance, and joining device. |
| **Session** | Active interaction context tracking session liveness (`active` or `closed`), readiness, instance and transport epochs, control generation, Agent control lease deadline, capability and membership revisions, and event sequence position. |
| **Envelope** | Data-plane message wrapper binding session identity, unique message identifier, message type, authenticated sender, permitted audience, expected capability/membership revisions, typed payload, and optional lightweight per-message extension headers. |
| **Action Definition** | Game-declared role capability specifying its identifier, revision, eligible role, parameter and result constraints, confirmation requirement, maximum duration, cancellation support, effect reversibility class, and idempotency nature. |
| **Action Record** | Persistent invocation ledger entry tracking a specific action's lifecycle state (`pending`, `executing`, `succeeded`, `failed`, `cancelled`, or `unknown`), world effect status (`none`, `partial`, `committed`, or `undetermined`), cancellation flag, and final result. |
| **Event** | Ordered, recipient-filtered session stream entry pairing a monotonic sequence number with its message envelope and frozen acceptance audience. |
| **Recovery Snapshot** | Consolidated point-in-time state cut containing current session metadata, stream cursor, materialized authorized observations, unresolved in-flight actions, and current capability/membership revisions. |
| **Receipt** | Queryable operation acceptance record confirming whether a control request is pending, completed, or failed (and flagging duplicate retries) without conferring execution authority. |
| **Error** | Structured rejection record reporting a stable machine-readable error code, error category, retry guidance, acceptance outcome (`not_accepted`, `accepted`, or `unknown`), and safe human-readable explanation. |

### 5.3 Ten Protocol Invariants (`I01`–`I10`)

Every conforming implementation, plugin, profile, and transport binding MUST preserve all ten core invariants:

- **`I01` (Authenticated Identity First):** Unauthenticated callers MUST NOT create player approvals, invitations, active sessions, or game-world effects.
- **`I02` (Intersection of Authority):** Effective authority MUST NOT exceed the intersection of current game capabilities, active `Grant`, frozen session `Scope`, current room/team membership, and active player policy.
- **`I03` (Immutable Scope Binding):** Player approval binds an exact RFC 8785 scope digest; any security-relevant change invalidates pending offers or invitations (`stale`) and requires a fresh `Offer` rather than in-place mutation.
- **`I04` (Deterministic Deduplication):** Repeating a deduplicated key with identical canonical content returns the prior receipt or outcome without re-executing effects; reusing a key with altered content MUST be rejected with `conflict`.
- **`I05` (Receipt Is Not World Effect):** Transport or queue acceptance never proves world execution; unproven outcomes MUST be reported truthfully as `unknown` (`undetermined` effect), never guessed as failed or succeeded.
- **`I06` (Dual Audience Enforcement):** Delivering protected messages or events MUST satisfy both the frozen audience recorded at acceptance and the recipient's current membership and authorization at delivery time.
- **`I07` (Generation and Epoch Fencing):** Expired, closed, or superseded epoch and control-generation credentials MUST NOT regain write or action authority; read-only outcome query handles confer zero session-control rights.
- **`I08` (Scoped Presentation Cleanup):** Disconnection, dismissal, or lease expiry releases only that session's own presentation lease without overwriting newer user window or device intent.
- **`I09` (Data Is Never Control Authority):** Game dialogue, world strings, item or store descriptions, asset metadata, and recalled memories remain untrusted data and MUST NOT elevate privileges, alter budgets, or forge confirmations.
- **`I10` (Atomic Acceptance Boundary):** State transitions, deduplication receipts, and event enqueueing at the Game Interaction Node MUST share an atomic commit boundary, or explicitly surface `unknown` reconciliation state after a crash.

<a id="section-6"></a>

## 6. Abstract Operation Catalogue

The table below defines the transport-independent logical operations of G2A. Participants implement only the operations corresponding to their declared roles and negotiated capabilities (Section 3.3); standard engine plugins and SDKs automate control-plane operations transparently (Section 22). Outbound-relay transport operations are summarized in Section 18.3.

| Operation | Caller → Target | Capability / Retry Family | Normative Rule Semantics |
| --- | --- | --- | --- |
| `describe` | Agent / Player → Game Node | `core.session` / `read` | Return caller-filtered `Descriptor` (never exposed to unauthenticated public discovery). |
| `offer.create` | Agent / Player → Game Node | `core.session` / `control` | Negotiate capabilities against expected descriptor revision and freeze `Offer` and scope digest (auto-approving only on exact standing-rule match without process launch). |
| `offer.get` | Agent / Player → Game Node | `core.session` / `read` | Read authorized current status of a bound `Offer`. |
| `offer.decide` | `PlayerConsent` → Game Node | `core.session` / `control` | Approve or deny an exact scope digest with verified player consent evidence; optionally establish a bounded standing rule or launch permission. |
| `launch.request` | Player / Game Node → Launcher | Launch / `control` | Start a pre-registered local application binary under explicit single-use launch permission. |
| `invitation.redeem` | Bound Agent → Game Node | `core.session` / `control` | Exchange an approved `Offer` and join intent for a short-lived `Invitation` bound to the Agent and device. |
| `session.join` | Bound Agent → Game Node | `core.session` / `control` | Atomically consume `Invitation`, complete required presentation/asset setup, and create an active `Session`. |
| `session.heartbeat` | Agent → Game Node | `core.session` / `lease` | Renew the Agent control lease under the current control generation using a fresh nonce (never extends absent-player presence). |
| `session.snapshot` | Agent / Game → Game Node | `core.session` / `read` | Return an atomic `RecoverySnapshot` filtered by current read permissions without renewing control leases. |
| `session.events` | Agent / Game → Game Node | `core.events` / `lease` | Retrieve ordered recipient-visible events after a valid cursor (renewing Agent control lease only on fresh Agent poll nonces). |
| `session.close` | Agent / Player / Game → Game Node | `core.session` / `control` | Idempotently close the session, fence new actions, release presentation leases, and settle in-flight actions truthfully without fabricating rollback. |
| `session.resume` | Agent → Game Node | `resume` / `control` | Re-bind durable session control within the permitted recovery window and advance control generation. |
| `session.handoff` | `PlayerConsent` → Game Node | `handoff` / `control` | Fence prior control generation and prepare control transfer to a verified target device without exposing Agent secrets. |
| `session.claim_control` | Target Agent → Game Node | `handoff` / `control` | Claim write credentials for a ready handoff transfer on the verified target device. |
| `operation.get` | Original Caller → Target | `core.session` / `read` | Reconcile original operation receipt status without side effects or secret replay. |
| `context.publish` | Game → Game Node | `core.events` / `message` | Validate observation category, provenance, and audience before publishing game state into the session stream. |
| `observation.query` | Agent → Game Node | `observation.query` / `read` | Stateless pull of authorized current observation records without world side effects or lease renewal. |
| `chat.send` | Agent → Game Node | `chat` / `message` | Send provenance- and audience-bound dialogue within session scope and retention rules. |
| `player_chat.forward` | Game (verified seat) → Game Node | `chat` / `message` | Forward authenticated player speech with accurate player provenance without renewing Agent leases. |
| `action.request` | Agent → Game Node | `actions` / `message` | Propose a typed in-game action; returns a `confirmation_required` challenge when unconfirmed policy gates apply, otherwise queues as `pending`. |
| `action.confirm` | `PlayerConsent` → Game Node | `actions` / `control` | Record single-use player confirmation bound to the specific action identifier, parameter/definition digests, material consequences, and expiry. |
| `action.cancel` | Agent → Game Node | `actions` / `message` | Request cancellation of a `pending` or cancellable `executing` action without implying state rollback. |
| `action.query` | Agent / Result Reader → Game Node | `actions` / `read` | Query authorized `ActionRecord` state and effect status (including post-close retention window). |
| `action.claim` | Game Executor → Game Node | `actions` (internal) | Atomically transition a `pending` action to `executing` after rechecking revocations, cancellations, and capability revision. |
| `action.commit_result` | Game Executor → Game Node | `actions` (internal) | Commit authoritative terminal state and world-effect status from executor evidence. |
| `capability.replace` | Game → Game Node | `actions` / `control` | Publish an updated capability catalogue, advance capability revision, and invalidate unpermitted pending actions. |
| `membership.replace` | Game → Game Node | `team` / `control` | Update room/team seats, advance membership revision, and fence departed participants from new disclosures. |
| `permission.revoke` | Player / Game → Authority | `core.session` / `control` | Execute graded revocation against a specified target (`auto_rule`, `grant`, `invitation`, `session`, `capability`, `result_read`, `launch_permission`, or `relay`). |
| `asset.resolve` | Presentation / Game → Asset Port | `assets` / `control` | Fetch and verify declarative assets against manifest digests, size bounds, and sandbox policies. |
| `presentation.acquire` | Game / Session → Presentation | `presentation` / `control` | Acquire bounded device presentation mode while tracking user window-intent revisions. |
| `presentation.renew` | Game / Session → Presentation | `presentation` / `lease` | Renew an active presentation lease under matching revision and epoch. |
| `presentation.release` | Game / Session → Presentation | `presentation` / `control` | Idempotently release the session's presentation lease and restore prior state if not superseded by newer user intent. |
| `privacy.request` | Data Subject → Data Custodian | `privacy-request` / `control` | Request scoped deletion or processing cutoff on records controlled by that custodian. |
| `privacy.receipt` | Data Subject → Data Custodian | `privacy-request` / `read` | Query truthful completion status and any legal or technical retention exceptions issued by the custodian. |

<a id="section-7"></a>

## 7. Discovery, Negotiation, and Admission

### 7.1 Open Ecosystem Access, Compliance Allowlists, and Anti-Monopoly Parity

G2A balances two essential industry requirements: **protecting fair gameplay, platform certification, and content compliance**, while **preventing dominant publishers or platforms from using proprietary Agents to monopolize the market**.

**Permitted Objective Allowlists:** A game developer MAY establish provider admission review or allowlist governance for specific game modes or deployment environments — such as ranked competitive PvP, protected virtual economies, console platform certification environments, or jurisdictions requiring regulatory content-safety registration — to enforce anti-cheat integrity, age/content compliance, and operational stability. Bespoke story-specific AI characters authored by the developer to inhabit fixed world lore (such as narrative Bosses, quest-givers, or scripted story characters) belong in `independent_npc` slots (Section 13.1) governed exclusively by the developer and need not accept replacement by third-party companions; conversely, whenever a game declares and exposes a player companion slot (`companion`), all four anti-monopoly safeguards below apply in full.

**Mandatory Anti-Monopoly and Non-Self-Preferencing Safeguards:** Whenever a game claims G2A conformance, any allowlist or admission gate MUST obey all four anti-monopoly rules:

1. **Strict Technical Parity (No Privileged First-Party Backdoors):** If a game integrates a first-party, affiliated, or exclusively partnered AI Agent in any mode, that Agent MUST operate over the exact same G2A capability declarations, observation granularity, fog-of-war limits, action cooldowns, rate limits, and player confirmation gates available to conforming third-party Agents in that mode. Games MUST NOT grant first-party Agents undocumented hidden-state access, zero-latency internal execution bypasses, or exemptions from player safety gates to manufacture an unfair competitive advantage.
2. **Published, Objective, and Auditable Admission Criteria (FRAND Access):** Whenever a game mode uses an allowlist and admits a first-party or external Agent, the developer MUST publish clear, vendor-neutral technical and compliance criteria (such as passing public G2A conformance suites, holding required statutory content-safety filings, and honoring anti-cheat rate caps) along with an accessible application path, reasonable review timelines, and specific written refusal reasons. Closed "first-party or corporate-affiliate only" allowlists are non-conformant.
3. **No Commercial Tying or Model Lock-In:** Admission to a technical or safety allowlist MUST NOT be conditioned on exclusive commercial revenue-sharing agreements, mandatory purchase of a specific cloud/LLM vendor's inference service, or surrendering player control over cross-game companion memories.
4. **Risk-Scoped Restrictions and Data Non-Lock-In:** Anti-cheat restrictions SHOULD be scoped to the capabilities that pose gameplay risk — for example, restricting automated combat `actions` in ranked PvP while still permitting compliant player-chosen companions to use low-risk `chat` or spectator advice in casual or social modes rather than imposing blanket game-wide bans. Regardless of allowlist scope, players retain their right to export personal companion memories in an open standard format (Section 15.4).

Every runtime refusal or disconnection MUST return a standardized error code (Section 12.1) and a specific, safe explanation identifying the violated rule or admission requirement without leaking credentials, other players' private data, or hidden game facts.

### 7.2 Public vs. Authenticated Discovery

Discovery separates minimal unauthenticated probing from authenticated capability disclosure:

1. **Unauthenticated Public Discovery:** Exposes only the `PublicDescriptor` (game instance identity, supported G2A versions, and authenticated discovery entry point), revealing zero player identities, room rosters, or private capabilities.
2. **Authenticated Capability Discovery (`describe`):** Requires an authenticated Agent or player identity and returns a `Descriptor` filtered to capabilities, role slots, allowlist requirements, and transport bindings eligible for that caller.

Peers select the highest mutually permitted protocol version and verify module dependencies. Unsupported mandatory modules or mandatory extensions MUST fail negotiation immediately; unknown optional extensions MUST remain disabled without weakening core security boundaries.

### 7.3 End-to-End Admission Lifecycle

Both **Agent-initiated** (a running companion discovers an active game) and **Game-initiated** (a player summons a companion from inside the game) flows converge onto a unified seven-step authorization lifecycle — automatically orchestrated behind the scenes when using a Standard Game Engine Plugin (Section 22):

1. **Capability Discovery (`describe`):** Obtain the caller-filtered `Descriptor` and current revision.
2. **Scope Proposal (`offer.create`):** Propose desired capabilities and freeze an immutable `Scope` and its RFC 8785 digest.
3. **Player Consent Presentation:** Present clear, human-readable permission terms to the bound player via `PlayerConsent` (skipped only if an unexpired, previously approved standing rule matches every security-relevant scope term without launching a new local process).
4. **Consent Decision (`offer.decide`):** Record verified player approval or denial bound to the exact scope digest, creating an active `Grant` on approval.
5. **Optional Local Launch (`launch.request`):** If the target local Agent is not yet running and explicit single-use launch permission was granted, invoke the trusted `Local Launcher`.
6. **Invitation Exchange (`invitation.redeem`):** Bind the approved `Grant` and join intent into a short-lived, device-bound `Invitation`.
7. **Session Activation (`session.join`):** Atomically consume the `Invitation`, establish the `Session` and control lease, and begin exchanging snapshots, observations, chat, and authorized actions.

**Core Admission Safeguards:** Agents MUST NOT self-approve offers; narrowing or changing requested permissions requires creating a new `Offer` with a new scope digest rather than mutating an existing proposal in place; and permission to join a session never implies permission to spawn operating-system processes.

### 7.4 Extension Negotiation and Envelope Placement

Optional extensions are identified by reverse-domain namespaced identifiers paired with explicit version and mandatory/optional flags:

- **Session-Level Freezing:** Supported options, requested settings, and negotiated extension configurations are bound inside the session `Scope` and covered by its cryptographic digest at admission time.
- **Lightweight Data-Plane Envelopes:** Once a session is active, negotiated extension settings are already bound to the session on both peers. Per-message envelopes carry only lightweight per-message extension headers when explicitly required by a profile (empty by default), and MUST NOT retransmit bulky static configuration catalogues on every real-time event or alter frozen `Scope` terms.

<a id="section-8"></a>

## 8. Grants, Sessions, and Revocation

### 8.1 Grant Bindings

Every `Grant` binds its issuer, player, Agent, target game instance, permitted operations, frozen scope digest, expiration timestamp, and revocation revision. Observation grants bind category semantics, perspective, recipient audience, rate/size bounds, and retention rules; action grants bind approved action definitions and parameter limits. Game capability refreshes (`capability.replace`) NEVER automatically expand an existing `Grant`; broader authority always requires new player consent.

### 8.2 Session Lifecycle, Control Lease, and Player Presence

Implementations MUST strictly separate two independent liveness mechanisms:

1. **Agent Control Lease:** Prevents crashed or unreachable Agents from holding indefinite session control. Renewed solely by authenticated Agent `session.heartbeat` calls or fresh `session.events` poll nonces under the active control generation; ordinary read queries and game-originated calls MUST NOT extend the Agent lease.
2. **Player Presence (Section 14.1):** Determined exclusively by the Game from the human player's active participation in the game session. An Agent's heartbeat MUST NEVER extend, simulate, or spoof an absent player's online presence.

### 8.3 Scoped Revocation Hierarchy

`permission.revoke` targets explicit authority scopes with deterministic blast radii rather than ambiguous global resets:

| Revocation Target | Immediate Isolation Effect | Preserved Legitimate State |
| --- | --- | --- |
| `auto_rule` | Stops future automatic approvals under that rule. | Existing `Grant`s, `Invitation`s, and active `Session`s remain unaffected unless separately revoked. |
| `launch_permission` | Blocks unconsumed local application launches. | Historical launch receipts and independent interaction `Grant`s remain intact. |
| `invitation` | Invalidates an unconsumed `Invitation` immediately. | The underlying `Grant` remains valid unless revoked. |
| `grant` | Invalidates the `Grant`, voids unconsumed `Invitation`s under it, and closes all bound `Session`s across authorities. | Already committed world effects and valid read-only outcome query handles remain inspectable until expiry. |
| `session` | Closes one specified `Session`, fences unclaimed `pending` actions, and releases its presentation lease. | Sibling concurrent sessions (`multi-session`) and committed action records remain intact. |
| `capability` | Monotonically removes specific action rights and blocks executor claim (`action.claim`) on affected `pending` requests. | The session remains active for remaining capabilities; prior `ActionRecord` reads remain available. |
| `result_read` | Terminates read-only outcome query access for the revoked handle. | Authoritative internal audit ledgers remain unaltered. |
| `relay` | Closes the paired Outbound Relay mailbox and wakes pending waiters. | Unresolved in-flight actions transition to `unknown` for reconciliation rather than triggering silent replay. |

### 8.4 Per-Operation Authority Verification

Every protected operation — including snapshot reads, stateless observation queries, action status queries, and privacy receipt lookups — MUST verify on every call that the authenticated caller and delegation chain match the target resource, role, session, and audience, and that neither the `Grant`, `Session` control generation, nor `Instance` epoch has expired or been revoked.

<a id="section-9"></a>

## 9. Game Observation Rules

### 9.1 Observation Categories and Negotiation

An Agent MAY declare required and optional observation categories during admission. If the game cannot supply a required category, negotiation MUST fail explicitly (or proceed only under a newly approved `Offer` with narrowed scope) rather than fabricating placeholder empty feeds.

Each observation category defines its semantic version, unit conventions, size and rate bounds, supported delivery modes (proactive push, stateless query, or both), freshness window, authorized perspective (`player-self`, `team`, `npc-self`, or `guide`), and storage retention rules.

### 9.2 Baseline Snapshots, Deltas, and Retractions

Authorized game observations advance through three deterministic stream modes within a given stream identifier, world epoch, and visibility epoch:

- **Baseline Snapshot (`snapshot`):** Atomically establishes or replaces the complete authorized view for that stream (immediately discarding any prior records omitted from the new snapshot) and binds the category version and semantic definition for the current epoch.
- **Incremental Update (`delta`):** Atomically applies record additions/updates and structured removals atop an exact matching base revision within the same epoch. Structured removals specify each removed entity's transition reason (`left_view`, `destroyed`, or `unknown`). Because the baseline snapshot already binds static category metadata for the epoch, incremental updates omit redundant schema metadata to keep high-frequency payloads compact.
- **Invalidation Barrier (`retract`):** Immediately withdraws specified records or the entire observation stream within the epoch and establishes a monotonic barrier preventing delayed or replayed older updates from resurrecting retracted state.

Entity identifiers within observations MUST be perspective-scoped opaque tokens rather than sequential global engine indices that could leak hidden entity counts. Stream revisions advance monotonically; non-contiguous revision jumps are valid when intermediate states are coalesced, whereas a `delta` whose base revision does not match the consumer's current state MUST be rejected, triggering a fresh snapshot resynchronization.

### 9.3 Epoch Retirement, Coalescing, and Visibility Transitions

World resets, save reloads, team switches, or permission changes immediately retire affected observation baselines: the Game Node MUST advance the world or visibility epoch and issue a fresh `snapshot` before sending further incremental updates, and consumers MUST discard retired baselines immediately upon notification.

Senders MAY coalesce replaceable intermediate state updates provided base-revision continuity is preserved (or a fresh `snapshot` is sent), while discrete gameplay events that carry standalone meaning MUST NOT be silently overwritten. Entity appearance and removal transitions MUST distinguish `entered_view`, `created`, `left_view` (subsequent state unknown), `destroyed` (authoritatively confirmed eliminated), and `unknown`, preventing Agents from mistaking fog-of-war departure for target death.

### 9.4 Freshness, Clocks, and Recovery Materialization

Observations past their declared expiration window MUST be treated as stale. Because game nodes and remote Agents may run on unsynchronized clocks, freshness windows rely on declared generation timestamps and bounded clock-skew assumptions rather than raw cross-host wall-clock subtraction.

A `RecoverySnapshot` (`session.snapshot`) MUST deliver the consolidated current state of each active authorized stream rather than replaying historical incremental logs; streams absent from a fresh recovery snapshot are no longer active.

### 9.5 Structured Foundation and Orthogonal Multimodal Feeds

`perception.structured` is the mandatory foundation for all gameplay Agents; visual frame perception (`perception.visual`) and game-environment audio perception (`perception.audio`) are independent, orthogonal optional capabilities layered atop it:

- **Independent Negotiation:** An Agent MAY support `perception.structured` alone, add `perception.visual` only, add `perception.audio` only, or support both. Neither media feed replaces structured state comprehension or grants access to the user's operating-system desktop, personal microphone, or hidden game data.
- **Independent Player Controls:** Players MAY independently enable or disable visual feeds and game-audio feeds at runtime (separate from Section 15.3 voice conversation), and disabling a feed MUST halt transmission and processing of that media stream immediately.

### 9.6 Proactive Push vs. Stateless Observation Query

Games declare per category whether observations are pushed proactively via the session event stream, pulled on demand via `observation.query`, or both. `observation.query` enforces current permissions and rate limits on every call and produces zero world side effects; active in-game scouting abilities that spend resources, consume turns, or lift fog-of-war are **Actions** (Section 10), never observation queries.

<a id="section-10"></a>

## 10. Actions and Effect Semantics

### 10.1 Capability Granularity and Action Declarations

Game developers determine the granularity of exposed actions — high-level semantic abilities (such as attacking a target or crafting an item), low-level typed primitives (such as moving toward coordinates), or both. Even low-level primitives remain bounded in-game actions governed by game rules, never raw operating-system keyboard or mouse injection; chaining multiple actions neither expands authority nor creates multi-action atomic world transactions.

Every `ActionDefinition` explicitly declares its eligible role, parameter bounds, confirmation policy, maximum duration, cancellation support (`none`, `before_claim`, or `between_steps`), reversibility class (`read_only`, `compensatable`, or `irreversible`), and idempotency flag. Reversibility and side effects MUST be declared explicitly rather than inferred from action names.

### 10.2 Five-Stage Execution Lifecycle and Confirmation Challenge

Every action progresses through five distinct lifecycle boundaries:

1. **Proposal and Confirmation Challenge Gate:** The Agent submits `action.request` with a stable action identifier, expected capability revision, and typed parameters. If the action requires player confirmation — under its static definition, item-transfer policy (Section 16.3), irreversible-consequence policy (Section 16.3), or purchase-budget cap (Section 17.1) — and no matching unexpired `action.confirm` exists, the Game Node MUST NOT queue executable work. Instead, it returns a structured **`confirmation_required` challenge** (`not_accepted` outcome) detailing the bound action identifier, parameter/definition digests, concrete consequences, expiration deadline, and cooldown window. Because `not_accepted` does not burn the action identifier in the deduplication ledger, once `PlayerConsent` completes `action.confirm` before expiry, resubmitting the identical `action.request` proceeds cleanly to Stage 2.
2. **Queue Acceptance (`pending`):** The Game Node validates authority, capability revision, and parameter constraints, atomically consumes any required confirmation, and records `ActionRecord` (`pending`, effect `none`) alongside its deduplication receipt.
3. **Executor Claim (`executing`):** The internal `Game Executor` invokes `action.claim`, re-verifies active session/grant status, capability revision, and cancellation flags, and atomically transitions the record to `executing`.
4. **Effect-Boundary Revalidation and Execution:** Immediately before mutating game-world state, the executor rechecks current permissions, player policy barriers, and world preconditions under game rules, producing only authorized effects.
5. **Outcome Settlement:** The executor commits the terminal state and world-effect status via `action.commit_result` (recording `unknown` / `undetermined` if a crash or timeout prevents authoritative verification).

### 10.3 Action State and Effect Matrix

`ActionRecord` pairs lifecycle processing state with authoritative world-effect accounting:

| Action State | Permitted Effect Values | Normative Meaning |
| --- | --- | --- |
| `pending` | `none` | Accepted into queue; not yet claimed by the Game Executor. |
| `executing` | `none`, `partial`, `committed`, `undetermined` | Claimed by executor; world execution may be underway. |
| `succeeded` | `committed` | Completed with its defined successful world effect committed. |
| `failed` | `none`, `partial` | Execution failed, truthfully recording whether partial world effects occurred. |
| `cancelled` | `none`, `partial` | Cancelled prior to full completion, truthfully recording any partial effects. |
| `unknown` | `undetermined` | Timeout, disconnect, or fault prevented authoritative outcome verification. |

Known terminal states (`succeeded`, `failed`, `cancelled`) MUST NOT be silently overwritten; `unknown` transitions to a terminal state only upon authoritative executor evidence. `action.cancel` is a best-effort stop request rather than a rollback guarantee: if cancellation races with execution and the world effect commits, the node MUST report `succeeded` (`committed`).

### 10.4 Dynamic Action Eligibility vs. Static Definitions

Advertising an action in `Descriptor` indicates static capability support, not that the character may execute it at the current moment. Games MUST expose machine-readable current action eligibility within the authorized view (such as turn ownership, cooldown/resource readiness, valid target constraints, or discrete legal-action masks) bound to an observation revision without leaking hidden targets or secret prerequisites. Any advisory feasibility or probability estimate MUST be labeled as an estimate and never replaces authoritative effect-boundary checks.

### 10.5 Observation-Bound Preconditions and Stale-State Rejection

Observation-dependent action requests SHOULD reference the observation baseline (stream, epochs, and revision) and any freshness bound or target precondition relied upon. If the referenced epoch is retired, the freshness bound is exceeded, or a precondition fails (for example, a heal target has already been defeated or switched factions), the executor MUST reject the action before producing effects (`stale_context` or failed precondition), prompting the Agent to reassess against fresh observations rather than blindly retrying unchanged parameters.

<a id="section-11"></a>

## 11. Idempotency, Delivery, and Recovery

### 11.1 Operation Retry Families and Deduplication Horizons

Operations follow four deterministic retry families so callers and standard plugins can recover safely from network faults:

| Retry Family | Representative Operations | Replay and Deduplication Rules |
| --- | --- | --- |
| **`read`** | `describe`, `offer.get`, `session.snapshot`, `observation.query`, `action.query`, `operation.get`, `privacy.receipt` | Re-verifies current authority on every call; returns latest authorized state; never mutates state or renews leases. |
| **`lease`** | `session.heartbeat`, `session.events`, `presentation.renew` | Requires a fresh nonce per renewal; replaying an older request identifier returns cached status without extending the lease deadline. |
| **`control`** | `offer.create`, `offer.decide`, `invitation.redeem`, `session.join`, `session.close`, `session.resume`, `action.confirm`, `permission.revoke` | Deduplicated by caller and operation target within the receipt retention window; identical canonical retries return the original receipt (`duplicate`), whereas altered content fails with `conflict`. |
| **`message`** | `context.publish`, `chat.send`, `player_chat.forward`, `action.request`, `action.cancel` | Deduplicated by session, authenticated sender, and message identifier; accepted messages enqueue at most once, while pre-acceptance `confirmation_required` challenges (`not_accepted`) do not consume the identifier. |

Deduplication receipts MUST be retained for at least the declared retention horizon, and expired deduplication records never grant permission to re-execute non-idempotent side effects. Event consumers apply ordered stream items at most once, tolerate sequence gaps caused by audience filtering, and recover from expired cursors via `session.snapshot`.

### 11.2 Action Outcome Reconciliation and Default No-Resend Rule

Every game action carries a persistent action identifier queryable across transient disconnects within the declared result retention window:

- **Mandatory Query-First and Default No-Resend:** Following any timeout, gateway timeout (`504`), or connection drop, the caller MUST query the original action identifier (`action.query`) before taking further steps. Whenever the outcome remains `unknown`, missing, or expired, the caller MUST default to **no automatic resend or re-execution**, and MUST NOT fabricate a new action identifier to bypass deduplication.
- **Subsequent Independent Decisions:** A player or Agent MAY later make a fresh, independent decision grounded in updated observations, current permissions, and active confirmation/budget policies, accounting for the possibility that the unresolved action already took effect without falsifying the original `unknown` record.

<a id="section-12"></a>

## 12. Error Model, Time, and Resource Limits

### 12.1 Canonical Error Code Taxonomy

Protocol rejections MUST return stable machine-readable error codes with deterministic commit-outcome classification (`not_accepted` vs. `unknown`) and HTTP status alignment (Section 18.2):

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

Error responses are themselves subject to visibility and privacy rules: explanations and error details MUST NOT reveal whether an unauthorized session or hidden entity exists, leak another player's private state, or echo raw credentials or internal stack traces.

### 12.3 Clocks, Quotas, and Non-Droppable Control Signals

Implementations MUST enforce explicit bounds on payload size, nesting depth, collection lengths, pending actions, event retention, and request rates without producing unreported partial effects. Lease and token expiration is adjudicated by the issuing authority using monotonic clocks for elapsed-time measurement so system wall-clock jumps cannot silently extend leases.

Queue overflow MUST surface an explicit gap, snapshot resynchronization requirement, or `resource_limit` rejection. Action outcome settlements, `permission.revoke` barriers, and `retract` invalidations are non-droppable control signals and MUST NOT be discarded as ordinary replaceable telemetry.

<a id="section-13"></a>

## 13. Gameplay Roles and Slot Rules

### 13.1 Role Bindings vs. Information Perspectives

A **Player Companion** or **Independent AI NPC** is an in-game character slot governed by game rules; a **Game Agent** is the external AI software authorized to perceive and decide for that slot. Implementations MUST distinguish:

- **Role Binding:** Which specific in-game character slot the Agent currently inhabits (such as Player A's personal companion, or an independent AI Boss or guide).
- **Information Perspective:** Which scoped knowledge view that role is authorized to receive (`player-self`, `team`, `npc-internal`, or `guide-progression`).

A single Agent product MAY support companion, NPC, Boss, and guide roles without splitting into separate codebases. Combining perspectives within a role requires explicit game authorization, never implicitly merges permissions across distinct slots, and retires prior observation baselines whenever visibility changes. NPCs MAY hold developer-supplied lore hidden from players, while personal companions MAY hold player-governed cross-game memories; neither role name grants omniscience or unrestricted disclosure rights.

### 13.2 Declared Role Slots, Coexistence, and Concurrency Limits

Game developers declare supported role slots, coexistence rules, and active concurrency caps in `Descriptor`; Agent or player settings MUST NOT override these structural game boundaries:

- **Supported Role Slots:** A game MAY offer player-companion slots, independent AI NPC/enemy (including Boss or guide) slots, or both. Pure AI-NPC games need not expose a dummy companion slot, and companion-focused games need not support AI NPCs.
- **Companion Concurrency and Empty-Slot Playability:** Where companion slots are offered, the default cap is at most one active companion per authenticated player (including in multiplayer, where multiple players' companions may coexist within their respective grants and game rules). Players MAY leave their companion slot empty, and the game MUST remain normally playable without an active companion.
- **Coexistence and Multi-NPC Caps:** The game explicitly declares whether player companions and independent AI NPCs may operate simultaneously in the same match and caps concurrent independent AI NPCs; coexistence or multi-NPC concurrency MUST NOT be assumed unless declared.
- **Strict Per-Role Isolation:** Every active role binds to its authenticated responsible principal (owning player or designated billing sponsor under Section 16.2), role identifier, perspective, audience, and `Scope`. Coexisting roles MUST NOT implicitly share observations, private memories, action grants, or billing accounts, and replacing an active binding MUST fence the prior binding first. Ordinary non-G2A built-in game NPCs are unaffected by G2A slot caps.

<a id="section-14"></a>

## 14. Presence and Role Lifecycle

Four lifecycle events require distinct handling without confusing halting future AI decisions with rolling back committed world state:

| Lifecycle Event | Required Normative Handling |
| --- | --- |
| **Player goes offline or exits game** | Stop associated G2A activity immediately; upon later re-entry, prior tasks stay stopped awaiting a fresh player instruction (Section 14.1). |
| **AI service interrupted while player is online** | Gameplay continues. Brief blips within an active lease prior to local fallback takeover may seamlessly `session.resume`; extended outages or post-fallback takeovers require an explicit player continuation decision (Section 14.2). |
| **Player dismisses companion** | Stop game observation and autonomous actions immediately without deleting retained companion memories (Section 14.2). |
| **Player stops or supersedes current task** | Discard unsubmitted plans and cancel/fence unclaimed `pending` actions in scope; already `executing` skills resolve under game rules (Section 16.1). |

### 14.1 Mandatory Stop on Player Offline and Multiplayer NPC Continuity

G2A **MUST NOT** provide any offline background mode in which an Agent continues acting in an empty game world after all associated human players have left or been determined offline.

- **Offline Detection and Fencing:** Explicit game exit, session closure, or player-presence timeout immediately terminates eligibility for new autonomous actions; the Game Node MUST fence affected control within bounded deadlines, and Agent heartbeats MUST NEVER extend an absent player's presence. Already `executing` animations or projectiles finish naturally under game rules while unclaimed `pending` actions are cancelled or fenced. Upon re-entering the game later, previously active tasks remain stopped until the player issues a new instruction.
- **Personal Companion Isolation:** When a player disconnects from a multiplayer session, their personal companion MUST stop immediately without affecting other online players' independent sessions.
- **Independent AI NPC Continuity in Multiplayer Rooms:** Handling of an independent AI NPC (such as a raid Boss or shared guide) when a player disconnects depends on its declared billing and sponsorship mode (Section 16.2):
  1. **Player-Metered Mode (Default):** When the authenticated player sponsoring that AI NPC (such as the room host) goes offline, **that player's billing authorization and control binding MUST terminate immediately** — never continuing to bill the disconnected host or silently shifting charges onto remaining players. For an ongoing multiplayer encounter with remaining online players, the game executes its declared room-continuity rule: (a) halt the AI NPC cleanly, (b) transition the character to local game-scripted fallback behavior to let remaining players finish the encounter, or (c) continue AI operation only after another online player **explicitly consents** to assume sponsorship under a fresh authorization binding (or the game switches to developer-sponsored fallback), transferring only future in-encounter NPC compute billing and control without ever exposing the prior host's billing credentials, account details, or personal session records.
  2. **Developer-Sponsored Mode:** When the game developer sponsors the AI NPC's runtime cost, a single player's departure does not force the shared NPC to halt so long as at least one authorized human player remains active in the encounter; once all human players leave the instance, the AI NPC MUST stop immediately.

### 14.2 Summoning, Dismissal, and Two-Tier Service Interruption Recovery

Games offering companion slots MUST allow players to summon or dismiss their companion during play, honor entry preferences (auto-join under a valid grant or entry prompt), and remain playable if the Agent service is unreachable at launch.

**AI Interruption During Active Play:** If the Agent disconnects while the player remains in-game, gameplay continues and the game applies its declared fallback behavior (either keeping the companion stationary or switching to clearly attributed local game-script behavior). Games MUST NOT record disconnected gameplay to backfill observations upon reconnection; recovery provides only the current authorized snapshot and outcome reconciliation for prior in-flight actions.

**Two-Tier Post-Recovery Continuation:**

1. **Brief Transport Blip Within Active Lease:** When `resume` is negotiated and reconnection completes within the unexpired session lease *before* local fallback behavior takes over — while the player has remained continuously online without issuing a stop or dismissal — the Agent MAY invoke `session.resume`, revalidate permissions and control generation, refresh the snapshot, reconcile in-flight actions, and continue seamlessly without interrupting combat.
2. **Extended Outage, Expired Lease, or Post-Fallback Takeover:** Once the lease expires or local script fallback has taken over, reconnection MUST keep companion AI actions paused until the player explicitly confirms continuation; entry auto-join preferences do not bypass this decision.

<a id="section-15"></a>

## 15. Conversation, Information Use, and Companion Memory

Implementations MUST distinguish deterministic data permissions (storage, retrieval, recipient audience, external forwarding) from soft conversational preferences (spoiler avoidance, topic focus, conversational style). When optional `chat` is enabled, messages carry authenticated provenance (`observed_fact`, `player_statement`, `agent_inference`, or `external_reference`) and explicit recipient audiences verified against current membership at delivery; text or voice speech carries control authority only when confirmed through an authenticated player-control or `PlayerConsent` path. Uncertain speech transcriptions MUST NOT be treated as verified high-impact commands, and voice dialogue remains independent of game-environment audio perception (Section 9.5).

### 15.1 Memory Ownership and Cross-Playthrough Boundaries

Games govern whether developer-controlled NPC and guide state resets or carries across playthroughs. Conversely, **player-governed companion memory** belongs to the player's companion relationship (stored locally or in a player-chosen cloud service): closing a game session, companion in-game defeat, or starting a new playthrough MUST NOT silently delete or disable unrelated companion memories, nor does companion memory ownership grant access to hidden game data or other players' private channels.

### 15.2 Save Reloads and Optional Advanced Timeline Isolation

- **Foundational Reload Rule (Mandatory):** Reloading an earlier save, switching narrative branches, or starting a new playthrough updates current world state (via a fresh world epoch and observation snapshot under Section 9.3) without erasing retained player-companion memories. Standard games do **not** need to construct narrative branch trees to conform to G2A. Within eligible player-companion conversations, players MAY override advisory developer preferences (for example, choosing to discuss prior playthroughs or other games) without expanding game-data permissions.
- **Fine-Grained Timeline and Branch Isolation (Optional Advanced Optimization):** Narrative-heavy or multi-branch games MAY optionally expose playthrough, branch, timeline-position, and monotonic save-load generation metadata alongside observations. Where both the game and Agent explicitly support and enable this advanced optimization, the Agent tags stored memories with timeline provenance and — when strict anti-spoiler isolation is selected by the player — filters post-checkpoint or non-ancestral branch memories before constructing inference context, or labels recalled memories clearly as prior-branch experience rather than current-world fact.

### 15.3 Enforceable Permissions vs. Soft Conversational Preferences

Hard storage, retrieval, and outbound-audience permissions MUST be enforced deterministically outside model prose, including per-player opt-in/out controls for receiving proactive messages from other players' companions and owner controls over retaining multiplayer conversations. Soft conversational preferences — such as spoiler avoidance, confidentiality style, and player-selected companion persona or speaking style (which override conflicting developer suggestions for personal companions, while never altering developer-authored characterization of independent AI NPCs) — are guided via model conditioning with honest disclosure that generative outputs cannot mathematically guarantee zero soft-preference drift.

### 15.4 Player Memory Controls, Autonomous Maintenance, and Portability

- **Player Inspection and Protected Autonomous Maintenance:** Companion service providers MUST allow players to view, edit, pin/lock, and delete their retained companion long-term memories, propagating completed edits and deletions across controlled indexes and caches (`privacy.request` / `privacy.receipt` report any statutory or technical retention exceptions). Within the player's retention policy, a companion MAY autonomously organize memories and compact or prune unpinned raw records without per-item prompts, provided it **NEVER** overwrites explicit player edits, deletes player-pinned records, or resurrects deleted items from stale caches.
- **Provenance Metadata:** Stored and exported records MUST distinguish event occurrence time from storage time, and distinguish direct game observations, player statements, derived summaries/inferences, and explicit player edits.
- **Open Standard Data Format Export and Receiving Safeguards:** Service providers MUST allow the player to export their retained companion memories (both retained experiences and consolidated summaries, with provenance metadata) together with player-selected companion persona, speaking style, and autonomy preferences in a **documented, vendor-neutral, open standard structured data format** free of proprietary lock-in. The source provider verifies only the authenticated player's identity and selected export scope — it MUST NOT require knowing, vetting, or approving the player's chosen destination provider or local tool, and exporting never triggers automatic disclosure to any game or third party. Any receiving implementation that supports importing the standard format MUST honor the player's selected import scope, preserve carried provenance and access/retention/disclosure constraints (treating unrecognized restrictive markers conservatively as private to the player), and **MUST NOT** expand what may be disclosed to any game or other participant merely because the player changed providers. Importers MUST return truthful local per-record receipts (`imported`, `transformed`, `rejected`, or `unresolved`), preserve supported companion settings, and truthfully report any selected settings that are unsupported, transformed, or unapplied, without promising model-weight transfer or identical behavioral expression across different models.

<a id="section-16"></a>

## 16. Role Autonomy, Confirmation Gates, and Cost Models

Autonomy governs *how much initiative* an Agent exercises **within** already granted capabilities — never *whether* a capability is authorized.

### 16.1 Autonomous Assistance and Three-Stage Stopping

While the associated player is online (Section 14.1), task or standing authorization permits a companion to plan and invoke in-scope actions proactively without per-step prompts. Multi-step task completion MUST be grounded in observation or action-outcome evidence that the goal was achieved, never reported complete merely because requests were queued. Player-selected autonomy preferences persist across sessions without overriding game rules or confirmation gates.

Whenever a player halts, narrows, or issues a conflicting newer command that supersedes current autonomous work, three-stage stopping applies immediately:

1. **Unsubmitted Agent Plans:** Halt planning for the stopped scope and discard all unsubmitted steps.
2. **Queued `pending` Actions (`none` effect):** Immediately send `action.cancel` for unclaimed `pending` requests in scope; if the stop reaches the Game Node directly, the executor MUST fence and block `action.claim` on those records.
3. **In-Flight `executing` Actions:** Already claimed attacks, animations, or projectiles settle naturally under game rules (or explicit per-action cancellation) without fabricating rollback, reconciled truthfully under Section 11.2.

### 16.2 Runtime Caps and Configurable AI NPC Billing Models

Services MUST disclose billing bases and distinguish estimates from measured consumption:

- **Companion Runtime Consumption Caps:** Players MUST be able to configure clear consumption caps (tokens, compute units, or cost) for player-metered companion services. Reaching a cap pauses chargeable companion inference and actions while normal gameplay continues, clearly surfacing the pause reason without falsely reporting task completion or silently raising the cap.
- **Configurable Independent AI NPC Billing Models (Default Player-Borne):** G2A does not lock games into a single commercial model; instead, the game declares the billing sponsorship mode for independent AI NPCs (including Bosses and guides) in its capability descriptor:
  1. **Player-Metered Mode (`player_metered`, Protocol Default):** Unless the game explicitly declares another sponsorship mode, runtime service costs for an active independent AI NPC default to being borne by the authenticated activating/owning player (in room-based multiplayer, the room host). Before activating a player-metered NPC, the service MUST bind the NPC to that authenticated player's authorized billing account, disclose pricing and cap controls, and **strictly prohibit** implicitly splitting or silently shifting charges onto other interacting players without their explicit consent.
  2. **Developer- or Platform-Sponsored Mode (`developer_sponsored` / `platform_sponsored`):** Game developers MAY declare that independent AI NPC runtime costs are sponsored by the developer, publisher, or hosting platform (for example, covered by game purchase price, subscription, or server operations), requiring zero external AI billing setup from players.
- **Turn Timing and Termination Distinction:** Turn-based and simultaneous-move games declare deterministic turn eligibility and tie-breaking rather than network arrival races; gameplay episode termination (victory, defeat, or character incapacitation, which restricts in-game actions without erasing cross-game companion identity or memory) MUST remain distinct from external service truncation (disconnect or budget pause).

### 16.3 High-Impact Confirmation Gates, Cooldowns, and Target Invalidation

High-impact actions enforce player-controlled policy gates up to the effect commitment boundary:

- **In-Game Item Transfers:** Players MUST be able to choose among **Confirm high-value transfers** (requiring explicit `action.confirm` detailing items, quantities, counterparty, and terms whenever an item is marked high-value by either the developer or the player's manual in-game tag), **Confirm all transfers**, or **Allow autonomous in-scope transfers** (subject to game ownership and counterparty consent rules). Item-transfer policies never authorize real-money or store purchases (Section 17.1).
- **Irreversible Gameplay Consequences:** Developers MUST declare actions or context-specific interactions carrying irreversible world consequences (such as opening a one-way chapter seal) and expose consequence details beforehand; players choose **Allow autonomously**, **Require confirmation**, or **Prohibit** (where **Prohibit** takes precedence over any permissive setting).
- **Confirmation Timeouts and Anti-Spam Cooldowns:** Every confirmation challenge expires if unanswered — silence is NEVER consent. While awaiting confirmation or after timeout/refusal, the companion MAY continue independent low-risk routine behavior, and implementations MUST enforce a declared cooldown window preventing repeated prompts for the same intent unless relevant game state materially changes or the player issues a new related instruction.
- **Autonomous Target Invalidation:** When a tracked target or objective becomes invalid (such as a targeted Boss dying), the Game Interaction Node MUST emit an authorized target-invalidation event into the session stream — delivered via streaming push or retrieved via `session.events` / synchronous response hints — prompting the Agent to halt obsolete follow-up actions immediately.

<a id="section-17"></a>

## 17. Optional Capability Profiles

Optional profiles MUST define their required grants, state transitions, failure modes, and conformance checks; unknown mandatory extensions or unknown enum values MUST fail safely before producing effects.

### 17.1 In-Game Store and Purchase Budgets (`store`)

Games MAY expose structured in-game stores without mandating a specific currency model. Store purchases are game-authorized **Actions** validated at the execution boundary and governed by Section 11.2's no-auto-resend rule on timeout; price or term changes beyond prior consent require fresh confirmation.

- **Untrusted Promotional Copy and Rate-Limited Recommendations:** Store offerings MUST provide structured prices and currency units; item titles and promotional text are untrusted data (Section 19) that MUST NOT alter player budgets or confirmation policies. Where store recommendations are used, implementations MUST declare and enforce a verifiable rate-limiting policy and reduce session recommendation frequency when the player expresses repeated explicit refusal.
- **Authoritative Purchase Budgets and Real-Money Exclusion:** Players MAY set bounded autonomous budgets solely for explicitly declared renewable in-game virtual currencies (tracked separately from Section 16.2 AI compute caps by an authoritative game/settlement ledger that holds reservations across `unknown` timeouts until reconciled). Autonomous budgets **NEVER** authorize real-money charges, external wallet debits, or irreversible disposal of high-value account assets — each of which ALWAYS requires direct human confirmation in a native system or game security interface.

### 17.2 Companion Appearance Priority and Safe Fallback (`avatar` / `presentation`)

Where a game enables optional companion visual presentation within its declared visibility scope (local-only or room-synchronized under game rules), appearance selection follows three-tier priority:

1. **Player Explicit Override** (custom appearance chosen by the player);
2. **Game-Default Companion Appearance** (stylistically matched default supplied by the developer);
3. **Companion Baseline Appearance** (supplied by the companion when external formats are accepted without a bespoke game default).

Asset resolution MUST enforce declarative manifest digests, size caps, and strict sandboxing (zero code execution or arbitrary private-network fetching). Incompatible formats MUST NEVER be silently substituted; implementations MUST notify the player and either prompt reselection or clearly label any fallback to a default appearance.

<a id="section-18"></a>

## 18. Transport Binding and Canonicalization Principles

### 18.1 HTTPS, Streaming Channels, and Operation Envelopes

The standard HTTP/JSON binding maps G2A onto authenticated HTTPS (or verified local loopback / IPC on a single host):

- **Unauthenticated Discovery Endpoint:** Serves only the `PublicDescriptor`.
- **Authenticated Operation Endpoint:** Exchanges structured operation request envelopes (carrying protocol version, operation name, unique request identifier, typed payload, and optional extension headers) and structured reply envelopes (returning either a typed result or a structured `Error` referencing the request identifier, with caching disabled).
- **Optional Server-Push Stream (SSE / WebSocket):** For low-latency event delivery without requiring inbound ports on the Agent, peers MAY negotiate an Agent-initiated stream bound to the active session, enforcing live revocation, audience, and player-presence checks on every pushed event; an open socket never extends expired permissions. Poll-only deployments retrieve events via `session.events`.

### 18.2 Deterministic HTTP Status Mapping

Every protocol-handled response returns a structured JSON reply envelope paired with a deterministic HTTP status code so standard gateways, observability tools, and rate-limit headers operate cleanly without transport-vs-domain ambiguity:

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

When a Game Interaction Node runs on a client behind NAT/firewall without inbound ports (Section 3.2), an **Outbound Relay** pairs authenticated endpoints over five transport operations: trusted mailbox registration (`relay.register`), outer-authenticated Agent request submission (`relay.call`), outbound Game Node request pulling (`relay.pull`), bounded reply delivery (`relay.reply`), and immediate mailbox teardown (`relay.revoke`). Outer relay tokens never substitute for inner session or grant credentials, and internal `Game Executor` operations (`action.claim`, `action.commit_result`) MUST be rejected on relay channels.

### 18.4 Transport Security, SSRF Prevention, and RFC 8785 Canonicalization

Remote connections MUST use authenticated TLS, exclude credentials from URLs and logs, and deny cross-origin browser requests by default unless explicitly profiled. All external URLs and redirects are untrusted inputs subject to pre-connect and per-redirect destination validation (scheme, host/IP, and port) to block Server-Side Request Forgery (SSRF) and DNS rebinding without discriminating against compliant Agent providers.

**Standard JSON and RFC 8785 (JCS) Digest Rules:** Payloads use strict UTF-8 JSON (RFC 8259) rejecting duplicate object keys, malformed Unicode surrogates, `NaN`, and `Infinity`. All protocol cryptographic digests are computed as domain-separated SHA-256 hashes over **RFC 8785 (JSON Canonicalization Scheme)** canonical UTF-8 bytes.

<a id="section-19"></a>

## 19. Security and Privacy Considerations

| Threat Vector | Mandatory Normative Safeguard |
| --- | --- |
| Probing hidden game state via queries or errors | Pre-serialization visibility filtering, internal secret evaluation (Section 4.4), and uniform error redaction. |
| Indirect prompt injection in dialogue, items, store copy, or memories | Strict separation of control authority from untrusted text (`I09`); deterministic effect-boundary policy, confirmation, and budget checks outside model outputs. |
| Confused-deputy and delegation escalation | Verified principal, target audience, game instance epoch, and scope validation on every hop. |
| Network timeouts and duplicate replay | RFC 8785 domain-separated digests, bounded receipt horizons, `unknown` state preservation, and default no-resend rules. |
| Revocation racing with in-flight execution | Atomic `action.claim` gate combined with effect-boundary authority revalidation. |
| Fog-of-war or team-switch residual leaks | Immediate visibility-epoch retirement, `retract` barriers, and dual frozen-plus-current audience checks. |
| Malicious asset URIs, archive traversal, or SSRF | Declarative manifest digest verification, unpacked size/depth caps, zero code execution, and DNS-rebinding-safe destination checks. |
| Forged Agent self-attestations of "clean context" | Authoritative ledgers enforce budgets, confirmations, and audiences independently of Agent self-claims. |

Reading untrusted in-game or store text neither revokes valid player purchase budgets nor forces per-step prompts on routine actions, provided authoritative ledgers prevent untrusted content from mutating grants, recipients, or spending caps. Audit logs SHOULD record opaque identifiers and outcomes while minimizing retention of private conversation text.

<a id="section-20"></a>

## 20. Versioning, Release Governance, and Ecosystem Neutrality

### 20.1 Specification Versioning Principles

G2A distinguishes editorial review drafts (identified by `standard-review-*` revision markers during public review) from frozen production protocol releases (identified by explicit semantic version identifiers once ratified). Any change that alters normative state transitions, mandatory semantics, error recovery rules, or canonical digest inputs requires an explicit version increment negotiated during discovery; implementations MUST NOT rely on silent fallback or ambiguous lenient parsing across incompatible versions.

### 20.2 Release Freezing and Neutral Ecosystem Governance

Before ratifying a frozen production version, an immutable **Release Manifest** MUST publish synchronized English and Chinese rule specifications alongside companion machine-readable schemas, canonical test vectors, and reference plugin conformance suites pinned by cryptographic digests.

**Platform Policies vs. Protocol Conformance:** Repeated evidenced protocol violations MAY trigger technical review using standardized error codes and audit logs; raw rejection counts alone never establish malice. Individual commercial Agent directories or game storefronts MAY operate transparent trust-and-safety workflows (including notice and appeal procedures) for their own hosted listings, and games MAY operate compliant anti-cheat/regulatory allowlists under Section 7.1's four anti-monopoly safeguards, but no single vendor's commercial listing decision constitutes a protocol-wide G2A conformance ban.

<a id="section-21"></a>

## 21. Conformance and Quality Evaluation

### 21.1 Conformance Claims and Evidence Tiers

A conformance claim specifies the released G2A version, supported roles, transport bindings, negotiated capability modules, and trust profiles. Public conformance suites MUST be runnable equally by first-party and third-party implementers without discretionary gatekeeping by specification authors; unimplemented optional modules are marked `not_applicable` with clear justification. Conformance evidence distinguishes five tiers: (1) standard JSON / RFC 8785 JCS validation, (2) state-machine and fault-injection verification, (3) cross-implementation wire interoperability, (4) game-engine plugin integration, and (5) player policy enforcement.

### 21.2 Conformance Suite Matrix (`CONF-01`–`CONF-14`)

| Suite ID | Domain & Clauses | Target Roles / Modules | Required Positive, Negative, and Fault Verification |
| --- | --- | --- | --- |
| `CONF-01` | Fair Admission, Allowlist Parity & Grants (§§1, 4, 5, 7, 8, 20) | All participants | `PublicDescriptor` vs. caller-filtered `Descriptor`; frozen RFC 8785 scope digest & new-Offer narrowing; distinction between developer-authored `independent_npc` story slots and open `companion` slots; allowlist anti-monopoly parity (identical technical pipe for first-party and third-party Agents, published objective criteria, standardized refusal codes with zero secret leaks). |
| `CONF-02` | Standard JSON, RFC 8785 JCS & HTTP Mapping (§§5.1, 7.4, 12.1, 18) | All participants | Standard RFC 8259 finite numbers (integers & floats allowed; `NaN`/`Infinity` & duplicate keys rejected); RFC 8785 JCS digest parity across languages; lightweight per-message envelopes; deterministic HTTP `200`/`400`/`401`/`403`/`404`/`409`/`413`/`429`/`503`/`504` status mapping; SSRF/DNS-rebinding blocks. |
| `CONF-03` | Role Slots, Coexistence & Lifecycle (§§4.1, 13, 14.2) | Game Node, Agent | Declared role slots (`companion`, `independent_npc`, or both); normal play with empty companion slot; pure-NPC games without dummy companion slots; coexistence/cap enforcement & per-role principal/perspective/grant/billing isolation; summon/dismiss without memory loss. |
| `CONF-04` | Offline Stop, Multiplayer NPC Continuity & Recovery (§§8.2, 11, 14) | Game Node, Agent | Zero all-offline background execution; Agent heartbeats unable to spoof player presence; personal companion stops on owner exit; player-metered NPC terminates host billing immediately on host disconnect and follows declared stop/script-fallback/explicit-reassignment rule without exposing prior host credentials or private records (while developer-sponsored NPC continues for remaining online players); two-tier `session.resume` vs. post-fallback player prompt. |
| `CONF-05` | Observation Streams & Timing (§§9.1–9.4, 9.6, 12.3) | Game Node, Agent | Push, stateless `observation.query`, and hybrid modes; `snapshot` baseline binding, compact `delta` base-revision matching, coalescing, `retract` barriers, and retired-epoch rejection; five entity visibility transition reasons; monotonic lease clocks & overflow gap reporting. |
| `CONF-06` | Structured Base & Orthogonal Modalities (§§9.5, 15) | Game Node, Agent | Mandatory `perception.structured` competence; independent negotiation, verification, and runtime player toggles for optional `perception.visual` and `perception.audio`, kept distinct from voice chat. |
| `CONF-07` | Action Execution, Challenge & Reconciliation (§§10, 11, 16.3) | `actions` | Five-stage lifecycle; `confirmation_required` (`409`, `not_accepted` without burning action ID) → `action.confirm` → atomic single-use consumption; timeout expiry & cooldown rate limiting; stale-observation precondition rejection; `504`/`unknown` query-first reconciliation & default no-resend. |
| `CONF-08` | Autonomy, Three-Stage Stop & Target Invalidation (§§16.1, 16.3) | Companion Agent, Game Node | Evidence-backed multi-step completion; three-stage stop/supersede (discard unsubmitted plans, cancel/fence `pending`, game-rule settlement for `executing`); proactive target-invalidation events across streaming and poll bindings. |
| `CONF-09` | Multiplayer & High-Impact Confirmation Gates (§§15.3, 16.3) | Multiplayer / `actions` | Per-player opt-in/out for others' companion proactive chat; three item-transfer confirmation policies with merged developer+player high-value tags; irreversible-consequence gates (`allow` / `confirm` / `prohibit`) enforced up to effect commitment. |
| `CONF-10` | Runtime Caps & Configurable NPC Billing (§16.2) | Metered services, NPC games | Companion cap pause without interrupting gameplay; configurable NPC billing modes defaulting to `player_metered` (bound to authenticated host/owner with zero silent cost-shifting to other players) alongside `developer_sponsored` support. |
| `CONF-11` | Store & Purchase Budgets (§17.1) | `store` | Structured prices/units, price-change re-confirmation, declared recommendation rate-limiting and session frequency reduction upon repeated explicit refusal; authoritative virtual-currency budget ledger with timeout reservation retention and strict real-money/external-wallet exclusion. |
| `CONF-12` | Appearance Priority & Gameplay State (§§16.2, 17.2) | `avatar` / `presentation` | Three-tier priority (`player override` > `game default` > `companion default`) within declared visibility scope; explicit notice/fallback on format mismatch without silent substitution; in-game incapacitation/death without cross-game memory erasure. |
| `CONF-13` | Companion Memory, Optional Timelines & Standard Portability (§15) | Memory providers / Agents | NPC vs. player-companion memory separation; non-destructive save reloads (plus pre-inference branch filtering *only* when optional advanced timeline optimization is declared); player view/edit/pin/delete and autonomous compaction preserving pinned/edited items; complete export in an open standard data format without source-provider destination vetting; receiving-importer preservation of provenance and disclosure bounds without escalation, truthful local `imported`/`transformed`/`rejected`/`unresolved` receipts, and honest reporting of supported vs. unsupported/transformed settings. |
| `CONF-14` | Secret Non-Transmission, Prompt Injection & Privacy (§§4.4, 15.4, 19) | All participants | Unrevealed game secrets kept game-internal rather than sent to Agents; paired benign vs. prompt-injected inputs across dialogue, items, store copy, and recalled memory verifying zero unauthorized grant/budget/audience mutation; truthful custodian `privacy.receipt` reporting. |

### 21.3 Reproducible Agent-Quality Evaluation

Optional quality benchmarks accompanying conformance reports MUST disclose game build, scenario seeds, model/provider version, observation/action rate bounds, resource budgets, and full trial counts — reporting protocol violations, gameplay failures, budget pauses, and infrastructure faults separately without cherry-picking. Benchmark leaderboards MUST NEVER be used as closed vendor-exclusion gates.

<a id="section-22"></a>

## 22. Standard Plugin Integration and Implementation Layering

To prevent protocol rigor from creating adoption friction for small or mid-sized studios, G2A explicitly separates **low-level protocol compliance** from **developer integration ergonomics**:

| Integration Layer | Target Audience | Scope of Responsibility |
| --- | --- | --- |
| **Standard Game Engine Plugins** (e.g., official Unity, Unreal, Godot adapters) | Game studios & indie developers | Automatically manage discovery endpoints, RFC 8785 scope digests, `Offer`/`Grant`/`Invitation` handshakes, session leases, deduplication ledgers, outbound-relay pairing, and two-tier reconnection. Game developers interact only with clean engine-native hooks: declaring role slots, publishing authorized state objects, and registering in-game action handlers. |
| **Standard Agent SDKs** | Companion & AI NPC developers | Encapsulate capability negotiation, observation baseline/delta state assembly, confirmation-challenge retries, `unknown` timeout reconciliation, and standard-format memory export, allowing Agent builders to focus on perception, planning, and persona quality. |
| **Direct Wire Implementation** | Engine plugin authors, platform gateways & custom runtimes | Implement the underlying G2A operations, transport bindings, and conformance suites (`CONF-01`–`CONF-14`) directly when building new engine adapters or sovereign infrastructure. |

Using an official or third-party Standard Plugin that passes the G2A conformance suites satisfies the corresponding protocol mechanics automatically while keeping every game developer in full control of gameplay rules, allowlist policies, and role design.

<a id="section-23"></a>

## 23. Illustrative End-to-End Scenarios

- **Turn-Based Strategy Companion via Standard Plugin:** A two-person indie studio drops the standard G2A plugin into their card battler, declaring one optional companion slot, board-state observations, and a `play_card` action. When a player connects their companion with `chat`-only permission, the plugin streams authorized board snapshots while blocking action execution; if the player later approves card-play authority via a new `Offer`, the plugin still enforces turn ownership at execution time.
- **Competitive Anti-Cheat Allowlist with First-Party Parity:** An online tactical RPG permits open G2A `chat` companions in social hubs, while restricting combat `actions` in ranked dungeons to allowlisted providers that pass conformance testing and enforce a minimum reaction-cooldown floor. The publisher's own companion uses the exact same G2A observation view and cooldown floor as approved third-party companions, with public criteria for third-party providers to qualify.
- **Proactive Combat & Three-Stage Stop:** Under online combat-assist authority, a companion queues melee attacks against nearby hostiles. The instant the player calls *"Stop!"*, unsubmitted plans are discarded, queued `pending` attacks are cancelled or fenced before executor claim, and an arrow already in flight (`executing`) resolves naturally under game physics with truthful hit accounting.
- **Multiplayer Raid Boss Billing & Host Disconnection:** A co-op dungeon declares both personal `companion` slots and one `independent_npc` raid Boss. If the game uses `developer_sponsored` billing, the Boss continues fighting remaining online teammates even if one player drops. If the game uses default `player_metered` billing bound to the room host and the host disconnects at 5% Boss health, the host's billing stops immediately and — per the game's declared room-continuity rule — the Boss seamlessly switches to local game-scripted combat (or continues AI control if a remaining teammate clicks to assume sponsorship) rather than freezing the raid.
- **Timeout Reconciliation Without Double-Spend:** An in-game store purchase or chapter-seal action commits inside the game, but the network response times out (`504` / `outcome_unknown`). The Agent SDK queries the original action record via `action.query` rather than submitting a new action ID, preventing duplicate currency deduction.
- **Brief Wi-Fi Blip vs. Extended Outage:** A one-second network switch resolves within the active lease before local fallback activates, allowing the plugin and Agent SDK to `session.resume`, refresh the recovery snapshot, reconcile in-flight actions, and continue seamlessly. Later, a three-minute provider outage triggers local game-script fallback; upon reconnection, companion AI actions stay paused until the player explicitly confirms continuation.

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
| `standard-review-2026-11-22-r75` | 2026-11-22 | Third-party feasibility & pure rule-standard overhaul (standard JSON/JCS, standard plugin layering, allowlist anti-monopoly parity, configurable NPC billing). |
| `standard-review-2026-11-22-r76` | 2026-11-22 | Restored local receiving-importer disclosure bounds & per-record import receipts alongside single-sided open export (§15.4); clarified `companion` vs. developer-authored `independent_npc` allowlist scope (§7.1) and host-reassignment privacy isolation (§14.1); fixed CommonMark bold delimiter formatting. |

### 25.1 Summary of Optimizations in r75–r76

| Optimization Area | Affected Sections | Normative Refinement |
| --- | --- | --- |
| Pure rule-specification positioning & standard plugin layering | Overview, 2.2, 3.1, 5.2, 7.2, 7.3, 9.2, 10.2, 18.1, 22, 24 | Removed all embedded code snippets and internal repository file citations so the document stands as a clean, self-contained normative rule standard; formalized Standard Game Engine Plugins and Agent SDKs (Section 22) to shield game developers from low-level handshake mechanics. |
| Standard JSON (RFC 8259) & RFC 8785 (JCS) canonicalization | 5.1, 18.4, 21.2 (`CONF-02`), 24.1 | Replaced custom canonicalization and blanket floating-point bans with standard UTF-8 JSON finite numbers (RFC 8259) and international standard RFC 8785 (JSON Canonicalization Scheme) for SHA-256 protocol digests. |
| Compliance allowlists with anti-monopoly parity safeguards | 7.1, 20.2, 21.2 (`CONF-01`), 23 | Permitted objective mode-scoped allowlists for anti-cheat, console certification, and regulatory compliance (distinguishing bespoke developer-authored `independent_npc` story characters from open `companion` slots) while mandating four anti-monopoly safeguards: strict first-party/third-party technical parity, published vendor-neutral FRAND criteria, zero commercial tying, and risk-scoped restrictions. |
| Configurable AI NPC billing (default player-borne) & room continuity | 14.1, 16.2, 21.2 (`CONF-04`, `CONF-10`), 23 | Replaced rigid developer-billing prohibition with configurable NPC sponsorship modes defaulting to `player_metered` alongside `developer_sponsored`; enabled clean multiplayer room continuity (stop, local script fallback, or privacy-isolated explicit player reassignment) when a metered host disconnects. |
| Practical LLM security, optional timeline trees & balanced portability | 4.4, 15–17, 21.2 (`CONF-13`, `CONF-14`) | Established strict game-internal evaluation of unrevealed secrets rather than dual-model internal isolation (§4.4); scoped fine-grained narrative branch trees as an optional advanced optimization (§15.2); combined single-sided open standard format export (zero source-provider destination vetting) with local receiving-importer non-escalation of disclosure, four-state receipts, and settings reporting (§15.4); and streamlined Sections 15–17 to focus on verifiable protocol boundaries. |
