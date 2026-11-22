# G2A Specification

**Game-to-Agent Interaction Protocol**

An open protocol defining identity, observation, authorization, and action boundaries among games, players, and AI agents.

Status: Working Draft for Public Review. Editorial revision: `standard-review-2026-11-22-r74`. Revision date: November 22, 2026.
Design baseline: `g2a-design-1`. Candidate profiles: `observations-draft-1`, `g2a-http-json/draft-1`.
This document defines target standard semantics for review; it does not allocate a frozen production wire version or certify existing SDK implementations.

Language pair: this English master and the [complete Chinese specification](G2A_SPECIFICATION.zh-CN.md) share the same editorial revision and normative structure. See [Section 25](#section-25) for traceable revision history.

## Contents

1. [Purpose and Scope](#section-1)
2. [Conventions and Document Authority](#section-2)
3. [Architecture, Topologies, and Applicability](#section-3)
4. [Roles, Identity, and Trust](#section-4)
5. [Canonical Data Model](#section-5)
6. [Abstract Operation Catalogue](#section-6)
7. [Discovery, Negotiation, and Admission](#section-7)
8. [Grants, Sessions, and Revocation](#section-8)
9. [Game Observation Profile (`observations-draft-1`)](#section-9)
10. [Actions and Effect Semantics](#section-10)
11. [Idempotency, Delivery, and Recovery](#section-11)
12. [Error Model, Time, and Resource Limits](#section-12)
13. [Gameplay Roles and Integration Requirements](#section-13)
14. [Presence and Role Lifecycle](#section-14)
15. [Conversation, Information Use, and Companion Memory](#section-15)
16. [Companion Autonomy and Player Policies](#section-16)
17. [Optional Profiles and Extensions](#section-17)
18. [HTTP/JSON and Streaming Transport Binding (`g2a-http-json/draft-1`)](#section-18)
19. [Security and Privacy Considerations](#section-19)
20. [Versioning, Release Manifest, and Ecosystem Governance](#section-20)
21. [Conformance and Quality Evaluation](#section-21)
22. [Baseline Alignment and Migration Notes](#section-22)
23. [Illustrative End-to-End Scenarios](#section-23)
24. [References](#section-24)
25. [Revision History](#section-25)

## Protocol Overview

Games expose vastly different worlds, rules, and action spaces. G2A provides a vendor-neutral interaction contract between a **Game** (exposed through a designated **Game Interaction Node**) and a **Game Agent** authorized to inhabit an in-game role — primarily a **Player Companion**, or an optional **Independent AI NPC** (such as a Boss or guide).

```text
Human Player ──controls──▶ [Player Character]
  │                              ↕ in-game / private / team communication
  │ consent &              [In-Game Role Slot]  (Game Companion or AI NPC)
  │ policies                     ▲           ↕ authorized perception & actions
  ▼                              │ G2A       ▼
[PlayerConsent] ────────▶ [Game Interaction Node] ◀──▶ [Game World & Rules]
                                 ▲                      (final adjudication)
                                 │ G2A protocol
                                 ▼
                           [Game Agent]
                      (local or cloud decision engine)
```

Three architectural boundaries govern every G2A interaction:

1. **The Game owns world truth and execution:** The Game Interaction Node publishes authorized observations and adjudicates whether requested actions succeed, fail, or produce partial effects under current game rules. The Game Agent is decision-making software, not an omniscient world controller.
2. **The Player governs consent and companion preferences:** Within boundaries permitted by the game, the player controls whether an Agent joins, what scope it receives, and how their companion behaves (autonomy level, memory use, spoilers, and confirmation policies). Player preferences never expand game-granted permissions or expose another participant's private data.
3. **The Agent owns internal reasoning and portable companion memory:** G2A standardizes observable wire contracts and authority checks without prescribing a specific LLM, planning algorithm, memory database, desktop pet UI, or central account service.

<a id="section-1"></a>

## 1. Purpose and Scope

### 1.1 Design Goals and Four Pillars

G2A enables any conforming game and any conforming AI Agent implementation to interoperate safely across local and cloud deployments. The protocol is organized around four pillars:

| Pillar | Normative Scope |
| --- | --- |
| Admission and Control | Principal authentication, discovery, capability negotiation, player consent, scoped grants, session leases, handoff, and revocation. |
| Observations and Information Use | Authorized game-state views, baselines and deltas, provenance, freshness, audience boundaries, multimodal feeds, and memory governance. |
| Actions and Outcomes | Capability definitions, dynamic action eligibility, confirmation challenges, effect-boundary revalidation, cancellation, and outcome reconciliation. |
| Interoperability and Extensions | Canonical data objects, abstract operations, transport bindings, deterministic error codes, versioning, optional profiles, and conformance suites. |

### 1.2 Core Architectural Distinctions

Five foundational distinctions apply across every layer of this specification:

- **Support is not authorization:** Advertising a capability in a descriptor states technical support; submitting a request expresses caller intent. Neither grants read or execution authority without an active `Grant` and `Scope`.
- **Acceptance is not completed execution:** Receiving or queuing an action request (`pending`) does not establish that its world effect occurred. Request acceptance, executor claim (`executing`), and committed world effect (`committed`) MUST remain distinct.
- **Authorized reads do not imply continuing validity:** Observations reflect a restricted perspective at a specific epoch and revision and become stale as world state or visibility changes.
- **Omission is not non-existence:** Data omitted due to fog-of-war, permission filtering, or delta compression MUST NOT be interpreted as a false fact, an empty world, or entity destruction.
- **Companion memory is separate from current world state:** Reloading a save, starting a new playthrough, or switching narrative branches changes authoritative world state, but MUST NOT by itself erase player-controlled companion memories. Remembering an earlier branch does not make it true in the current world or override game rules.

### 1.3 Scope Boundaries and Non-Goals

G2A is scoped strictly to game interaction: player-companion assistance, authorized AI NPC interaction, game-state observation, constrained in-game actions, and optional companion presentation.

G2A is **not** a general-purpose OS or desktop UI automation protocol. It does not standardize arbitrary remote code execution, raw screen/input capture outside declared game feeds, model weights, prompt templates, or internal commercial platform billing settlements. While G2A enforces observable data, audience, and action boundaries, no communication protocol can erase prior knowledge embedded in model weights or mathematically prevent a compromised endpoint from inferring unstated facts.

<a id="section-2"></a>

## 2. Conventions and Document Authority

### 2.1 Normative Keywords

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**, and **MAY** in this document are to be interpreted as described in RFC 2119 and RFC 8174 (BCP 14) when, and only when, they appear in all capitals. Explanatory prose, diagrams, illustrative scenarios (Section 23), and revision notes (Section 25) are informative and do not add independent normative requirements. A permission expressed with **MAY** does not require every implementation to offer that feature.

### 2.2 Specification Status and Artifact Hierarchy

This English master (`G2A_SPECIFICATION.md`) is the primary semantic specification for review. To keep normative sections self-contained and concise, the following rules apply globally across all sections without repetition:

1. **Baseline vs. Candidate Profiles:** Core session, grant, action, and canonicalization contracts build on the repository's machine-checked design baseline (`g2a-design-1`: [contracts.schema.json](../protocol/contracts.schema.json), [operations.json](../protocol/operations.json), [WIRE_CONTRACT.md](../protocol/WIRE_CONTRACT.md)). Typed observation streams (`observations-draft-1`, Section 9) and the unified HTTP/JSON operation binding (`g2a-http-json/draft-1`, Section 18) are candidate specifications proposed on top of that baseline.
2. **Release Freezing Gate:** Candidate profile schemas, extension identifiers, and digest domains become wire-interoperable obligations only when pinned in an immutable release manifest with test vectors under Section 20. Defining behavioral semantics in a section does not silently register unadvertised core operations or certify legacy experimental code (`0.1.0-dev`).
3. **Explicit Conformance Claims:** Implementations MUST identify the exact protocol version, binding, and profiles they implement, and MUST NOT represent support for a candidate draft or legacy SDK as conformance to a future frozen release. Historical baseline mappings are consolidated in Section 22.

<a id="section-3"></a>

## 3. Architecture, Topologies, and Applicability

### 3.1 Three-Layer Protocol Stack

G2A separates *what* is meant from *how* bytes are carried so gameplay semantics remain invariant across local IPC, HTTP, streaming, and relay deployments:

1. **Canonical Data Model (Section 5):** Typed structures for principals, descriptors, scopes, grants, sessions, envelopes, observations, actions, receipts, and errors.
2. **Abstract Operations and State Machines (Sections 6–17):** Transport-independent operations, authority checks, lifecycle transitions, confirmation handshakes, and recovery rules.
3. **Transport Bindings and Profiles (Section 18):** Concrete wire encodings, endpoints, status mappings, streaming channels, and NAT-traversal relays.

SDKs and game-engine adapters are implementation tools, not protocol layers; any language or architecture conforming to the wire and behavioral contracts is valid.

### 3.2 Deployment Topologies

Games run across diverse network environments — from single-player PC/mobile clients behind home NAT to dedicated cloud game servers. G2A supports three standard deployment topologies without changing abstract operation semantics:

| Topology | Connection Direction | Typical Scenario |
| --- | --- | --- |
| **Local Loopback / IPC** | Agent ↔ Local Game Node (`127.0.0.1` or OS IPC) | Desktop or mobile companion app running on the same device as a single-player or client-hosted game. |
| **Direct HTTPS / WSS** | Agent → Reachable Game Node | Cloud or LAN Agent connecting to a game server or gateway with a reachable TLS endpoint (`g2a-http-json` + optional SSE/WebSocket stream). |
| **Outbound Relay** | Game Node (outbound) → Paired Relay ← Agent | Single-player or P2P game client behind NAT/firewall interacting with a cloud Agent without opening inbound ports on the player's device (Section 18.3). |

### 3.3 Capability Modules and Applicability

Not every participant implements every capability. Core conformance requires only session management, event/context handling, and baseline structured perception; all other capabilities are negotiated explicitly:

| Capability Identifier | Requirement Tier | Primary Responsibilities |
| --- | --- | --- |
| `core.session` | Mandatory Core | Discovery, negotiation, scoped admission, session lease, snapshot, closure, and error handling. |
| `core.events` | Mandatory Core | Ordered recipient-visible event delivery, `context.publish` transport, and within-session deduplication. |
| `perception.structured` | Mandatory Core (Gameplay Agents) | Interpreting negotiated structured game state (`observations-draft-1` or baseline context) to make authorized role decisions. |
| `observation.query` | Optional | Stateless, authorized Agent-initiated reads of current game observations without world side effects (Section 9.6). |
| `perception.visual` | Optional | Game-frame/image perception built on top of `perception.structured` (Section 9.5). |
| `perception.audio` | Optional | Game-environment audio perception built on top of `perception.structured`, distinct from voice chat (Section 9.5). |
| `actions` | Optional | Typed action requests, confirmation challenges, executor claim, effect-boundary validation, cancellation, and result queries (Section 10). |
| `chat` | Optional | Provenance- and audience-bound text/voice communication (`chat.send`, `player_chat.forward`) (Section 15). |
| `team` | Optional | Multi-participant seat bindings, membership revisions, and team-scoped audiences. |
| `resume` | Optional | Durable session state, deduplication ledgers, and seamless active-lease reconnection (Sections 11, 14.2). |
| `handoff` | Optional (requires `resume`) | Generation-fenced transfer of session control across devices or processes. |
| `multi-session` | Optional | Concurrent active sessions for the same Agent identity without silently evicting existing sessions. |
| `avatar` / `assets` / `presentation` | Optional | Companion appearance negotiation, safe declarative asset resolution, and device rendering leases (Section 17.2). |
| `store` | Optional | Structured in-game offerings, measured recommendations, and authoritative purchase-budget ledgers (Section 17.1). |
| `privacy-request` | Optional | Scoped data-handling/deletion requests and truthful processor receipts (Section 15). |

For implementation planning, Sections 4–12 specify **L1 Core Interaction & State Machines**, Sections 13–16 specify **L2 Gameplay Roles, Presence, Memory & Autonomy Policies**, and Sections 17–18 specify **L3 Optional Profiles & Transport Bindings**. Applicability depends strictly on a participant's declared roles and negotiated capabilities.

<a id="section-4"></a>

## 4. Roles, Identity, and Trust

### 4.1 Core Trust Principals and Protocol Endpoints

G2A distinguishes three primary trust principals and four optional functional roles. Multiple roles MAY reside in one software process, provided their logical authority boundaries remain strictly enforced:

| Role | Category | Authority and Responsibilities |
| --- | --- | --- |
| **Game Interaction Node** (`Game`) | Core Endpoint | The game-designated G2A interface and sole protocol source of authoritative current game state and action outcomes. Validates callers, enforces `Scope`, and coordinates with internal game modules. |
| **Game Executor** (`Game` internal) | Authoritative Component | Internal game logic or server subsystem that claims `pending` actions (`action.claim`), enforces current gameplay rules at the effect boundary, and commits outcomes (`action.commit_result`). Never exposed directly to Agent credentials. |
| **Player / `PlayerConsent`** | Core Principal | The human player and the authenticated UI/control path (`PlayerConsent`) through which the player approves `Offer`s, confirms high-impact actions (`action.confirm`), sets companion policies, and revokes permissions. |
| **Game Agent** (`Agent`) | Core Endpoint | Local or remote AI software authorized to play a bound in-game role (Companion or AI NPC). Consumes authorized observations, proposes in-scope actions, and manages companion reasoning/memory. |
| **Local Launcher** | Optional Role | Verifies local application identity and starts a registered binary under an explicit `launch.request` grant without executing untrusted shell strings. |
| **Presentation Endpoint** | Optional Role | Manages companion window/overlay rendering leases (`presentation.*`) and safe asset caching (`asset.resolve`) on a user device. |
| **Data Custodian** | Optional Role | Any participant (Agent provider, game, or platform) that persists player/companion data and therefore answers `privacy.request` and `privacy.receipt` for records under its control. |
| **Outbound Relay** | Optional Transport Role | Forwards permitted operations between paired endpoints (`relay.*`) when the Game Node does not expose an inbound port, without holding `Game` administrative authority. |

The Game Interaction Node is an external protocol responsibility, not a mandatory extra server: single-player games MAY host it in-process or via a local sidecar, while online games MAY expose it at the client or server gateway. Closing a G2A `Session` ends protocol interaction for that binding without shutting down the game program or multiplayer room.

### 4.2 Principals, Instances, and Epochs

Caller identity MUST be established from transport-authenticated credentials; a `sender` field inside a message payload is checked for consistency against authenticated identity and MUST NOT be trusted on its own. Implementations MUST keep four identifiers distinct:

- **`Principal` (`{issuer, subject, kind}`):** Uniquely identifies a `player`, `agent`, `game`, or `service` within `issuer`'s namespace. Display names carry zero authentication weight, and matching names across different issuers MUST NOT be auto-merged.
- **`Device` (`device_id`):** Identifies the physical or logical client endpoint holding presentation or control leases.
- **`Instance` (`{game, instance_id, epoch}`):** Identifies a specific game run, match, or room so grants and credentials from one run cannot replay against another.
- **Epochs and Generations (`instance_epoch`, `world_epoch`, `visibility_epoch`, `control_generation`):** Monotonic or non-reused markers that fence stale credentials, retired observation views, and superseded controllers after reloads, team switches, or handoffs.

### 4.3 Delegation and Trust Profiles

When a service or gateway acts on behalf of a player, verified **delegation** MUST bind the delegating player, delegate identity, target game/instance, allowed scope, and expiry. Passing through an intermediary NEVER adds the intermediary's own privileges to the represented principal's authority. Unverified text claiming delegation inside chat or game strings has zero authority, and possession of an opaque `session_id`, `action_id`, or `correlation_id` grants neither read nor execution permission.

Deployments MUST advertise and enforce compatible trust profiles without silent downgrade:

- **`local-verified`:** OS IPC or a trusted local launcher verifies binary/principal bindings on the host machine.
- **`provider-verified`:** Mutual or server-authenticated TLS combined with cryptographic token/delegation verification binds player, Agent, target audience, and expiry across network boundaries.
- **`test-enrolled`:** Pre-registered development credentials for local testing and conformance harnesses; implementations MUST NOT represent `test-enrolled` as protection against untrusted local processes.

Implementations MUST truthfully disclose plaintext visibility (`PrivacyModel`). Unless end-to-end encryption is explicitly negotiated by a future extension, the Game Interaction Node and any negotiated Outbound Relay can inspect messages traversing them and MUST NOT claim endpoint-only decryption.

### 4.4 Four-Way Authority Separation and Protected Planning Inputs

Implementations MUST enforce four non-interchangeable permission dimensions:

1. **Receive:** Information the Agent is authorized to obtain from the game or player.
2. **Disclose to Player:** Information the Agent may surface in player-facing conversation.
3. **Disclose Externally:** Information the Agent may transmit to the game, teammates, or other services.
4. **Act:** Capabilities and parameter ranges the Agent may request in the game world.

Observation profiles SHOULD further distinguish (a) **player-disclosable observations**, (b) **protected planning-only inputs**, and (c) **game-evaluated opaque conditions** (where the game evaluates hidden prerequisites internally and exposes only an authorized boolean or reference). Where raw or summarized data is restricted to planning under an enforceable grant, implementations MUST enforce isolation across retrieval, outbound tool/message serialization, and output filtering (for example, separating non-verbal action selection from unconstrained dialogue context), and MUST NOT claim that system prompts alone guarantee non-disclosure. Where hard non-disclosure is required, games SHOULD evaluate hidden state internally rather than transmit raw secrets to the Agent.

<a id="section-5"></a>

## 5. Canonical Data Model

### 5.1 Core Identifiers and Numeric Representation

Unless explicitly specified otherwise, all identifiers (`descriptor_id`, `offer_id`, `grant_id`, `invitation_id`, `session_id`, `stream_id`, `request_id`, `action_id`) MUST be treated as opaque ASCII/UTF-8 tokens (`1..128` characters) and MUST NOT be parsed by consumers to infer permissions or ordering. Transport `request_id`, envelope `id`, `correlation_id`, event `sequence`, and observation `revision` occupy distinct namespaces and MUST NOT substitute for one another.

**Deterministic Integer and Fixed-Point Representation:** Because `g2a-cjson-1` (Section 18.4) forbids IEEE-754 floating-point literals and negative zero to guarantee exact canonical digests across languages, all wire schemas MUST represent continuous game quantities using explicit integer units or fixed-point scales within exact safe integers (`[-9007199254740991, +9007199254740991]`):

- **Time and Durations:** Integer milliseconds (`_ms`, e.g., `observed_at_ms`, `maximum_duration_ms`).
- **Ratios and Probabilities:** Integer basis points (`_bps` in `0..10000`, where `10000 = 100.00%`) or declared fixed-point denominators.
- **Spatial Coordinates and Physics Quantities:** Explicitly scaled integers declared by the category/action schema (e.g., millimeters `_mm`, milliradians `_mrad`, or `{value, scale_exp10}`), or typed decimal strings where arbitrary precision is required.

### 5.2 Normative Protocol Objects

The canonical model comprises the following logical structures (exact JSON Schema definitions for baseline fields are pinned in [contracts.schema.json](../protocol/contracts.schema.json)):

| Object | Canonical Role & Key Fields |
| --- | --- |
| **`PublicDescriptor`** | Unauthenticated discovery document (`GET /.well-known/g2a.json`): `{instance, supported_versions[], discovery_endpoint}`. Exposes zero player or session state. |
| **`Descriptor`** | Authenticated capability advertisement: `{descriptor_id, revision, instance, supported_versions[], bindings[], trust_profiles[], role_slots, supported_features[], required_features[], privacy_model, context_categories[], actions[], limits, extensions}`. Filtered per requesting principal. |
| **`Scope`** | Immutable negotiated permission snapshot: `{player, agent, instance, version, binding, trust_profile, role_binding, features[], descriptor_revision, action_ids[], approved_action_digests, context_categories[], audiences[], effective_policy, ledger_durability, limits, created_at_ms, expires_at_ms, extensions}`. |
| **`Offer`** | Bounded admission proposal: `{offer_id, applicant, immutable_scope, scope_digest, decision_deadline_ms, launch_required, state: pending\|approved\|denied\|expired\|stale, grant_id?, auto_rule_ref?}`. |
| **`Grant`** | Approved authority record: `{grant_id, scope, scope_digest, approver, consent_evidence, revision, state: active\|revoked\|expired, expires_at_ms}`. |
| **`Invitation`** | Short-lived join credential bound to `Grant` and `JoinIntent`: `{invitation_id, grant_id, grant_revision, join_intent_digest, player, agent, audience_instance, expires_at_ms, state: issued\|consumed\|revoked}`. |
| **`Session`** | Active protocol context: `{session_id, scope_digest, grant_id, state: active\|closed, ready: bool, close_reason?, instance_epoch, transport_epoch, control_generation, controller_device?, lease_deadline_ms, capabilities_revision, membership_revision, sequence, result_read_until_ms, resume_until_ms?}`. |
| **`Envelope`** | Typed data-plane message wrapper: `{version, session_id, id, type, correlation_id?, sender, audience[], expected_capabilities_revision?, expected_membership_revision?, payload, extensions}`. |
| **`ActionDefinition`** | Game-declared role capability: `{id, revision, role, parameters_schema, result_schema, requires_confirmation, maximum_duration_ms, cancellation: none\|before_claim\|between_steps, effect_class: read_only\|compensatable\|irreversible, idempotent: bool}`. |
| **`ActionRecord`** | Invocation state & outcome ledger entry: `{request_id, session_id, actor, action, arguments_digest, state: pending\|executing\|succeeded\|failed\|cancelled\|unknown, effect: none\|partial\|committed\|undetermined, cancel_requested: bool, result?, result_revision, query_until_ms}`. |
| **`Event`** | Ordered stream entry: `{sequence, envelope, frozen_audience[], created_at_ms}`. |
| **`RecoverySnapshot`** | Atomic state cut for recovery: `{session, cursor, materialized_observations[], active_actions[], capabilities_revision, membership_revision}`. |
| **`Receipt`** | Queryable operation record: `{id, operation, accepted_at_ms, record_digest, status: pending\|done\|failed, outcome_ref?, duplicate: bool}`. Confers zero execution authority. |
| **`Error`** | Structured failure payload: `{code, category, retry: never\|same_request\|after_reauth\|after_renegotiate, request_id?, retry_after_ms?, outcome: not_accepted\|accepted\|unknown, message, details?}`. |

### 5.3 Ten Protocol Invariants (`I01`–`I10`)

Every conforming implementation, profile, and transport binding MUST preserve all ten invariants:

- **`I01` (Authenticated Identity First):** Unauthenticated callers MUST NOT create player approvals, invitations, active sessions, or world effects.
- **`I02` (Intersection of Authority):** Effective authority MUST NOT exceed the intersection of current game capabilities, active `Grant`, frozen session `Scope`, current membership, and active player policy.
- **`I03` (Immutable Scope Binding):** Player approval binds an exact `scope_digest`; any security-relevant change invalidates pending `Offer`s/`Invitation`s (`stale`) and requires a fresh `Offer` rather than in-place mutation.
- **`I04` (Deterministic Deduplication):** Repeating a deduplicated key with identical canonical content returns the prior receipt/outcome without re-executing effects; reusing a key with different content MUST fail with `conflict`.
- **`I05` (Receipt Is Not Effect):** Transport or queue acceptance never proves world execution; unproven outcomes MUST be reported as `unknown` (`effect: undetermined`), never guessed as `failed` or `succeeded`.
- **`I06` (Dual Audience Enforcement):** Delivering protected messages or events MUST satisfy both the frozen audience recorded at acceptance and the recipient's current membership/grant at delivery time.
- **`I07` (Generation and Epoch Fencing):** Expired, closed, or superseded epoch/generation credentials MUST NOT regain write or action authority; read-only result handles confer zero session-control rights.
- **`I08` (Scoped Presentation Cleanup):** Disconnection, dismissal, or lease expiry releases only that session's own presentation lease without overwriting newer user window/device intent.
- **`I09` (Data Is Never Control Authority):** Dialogue, world text, item/store descriptions, asset metadata, and recalled memories remain untrusted data and MUST NOT elevate privileges, alter budgets, or forge confirmations.
- **`I10` (Atomic Acceptance Boundary):** State transitions, deduplication receipts, and event enqueueing at the Game Interaction Node MUST share an atomic commit boundary, or explicitly surface `unknown` reconciliation state upon crash.

<a id="section-6"></a>

## 6. Abstract Operation Catalogue

The operations below define the transport-independent interface of G2A. Each participant implements only the operations required by its role and negotiated capabilities (Section 3.3). Outbound-relay transport operations (`relay.register`, `relay.call`, `relay.pull`, `relay.reply`, `relay.revoke`) are specified in Section 18.3.

| Operation | Caller → Target | Capability / Retry Family | Normative Semantics |
| --- | --- | --- | --- |
| `describe` | Agent / Player → Game Node | `core.session` / `read` | Return principal-filtered `Descriptor` (never exposed to unauthenticated public discovery). |
| `offer.create` | Agent / Player → Game Node | `core.session` / `control` | Negotiate capabilities against `expected_descriptor_revision` and freeze `Offer` + `scope_digest` (auto-approving only on exact `auto_rule` match without launch). |
| `offer.get` | Agent / Player → Game Node | `core.session` / `read` | Read authorized current state of a bound `Offer`. |
| `offer.decide` | `PlayerConsent` → Game Node | `core.session` / `control` | Approve or reject exact `scope_digest` with verified `decision_ref`; optionally establish bounded `auto_rule` or `launch` permission. |
| `launch.request` | Player / Game Node → Launcher | Launch / `control` | Start a pre-registered local application binary under explicit single-use launch authority. |
| `invitation.redeem` | Bound Agent → Game Node | `core.session` / `control` | Exchange an approved `Offer` + `JoinIntent` for a short-lived `Invitation` bound to the Agent and device. |
| `session.join` | Bound Agent → Game Node | `core.session` / `control` | Atomically consume `Invitation`, acquire required presentation/assets if applicable, and create `Session`. |
| `session.heartbeat` | Agent → Game Node | `core.session` / `lease` | Renew Agent control lease under current `control_generation` using a fresh `request_id` nonce (never extends absent-player presence). |
| `session.snapshot` | Agent / Game → Game Node | `core.session` / `read` | Read an atomic `RecoverySnapshot` filtered by current read authority without renewing leases. |
| `session.events` | Agent / Game → Game Node | `core.events` / `lease` | Poll ordered recipient-visible events after `cursor` (renewing Agent control lease only on fresh Agent poll nonces). |
| `session.close` | Agent / Player / Game → Game Node | `core.session` / `control` | Idempotently close session, fence new actions, release presentation, and settle in-flight actions without fabricating rollback. |
| `session.resume` | Agent → Game Node | `resume` / `control` | Re-bind durable session control within `resume_until_ms`, incrementing `control_generation`. |
| `session.handoff` | `PlayerConsent` → Game Node | `handoff` / `control` | Fence old generation and prepare control transfer to a verified `target_device` without exposing Agent secrets to the caller. |
| `session.claim_control` | Target Agent → Game Node | `handoff` / `control` | Claim write credentials for a ready `handoff` transfer on the verified target device. |
| `operation.get` | Original Caller → Target | `core.session` / `read` | Reconcile original receipt status (`pending \| done \| failed`) without side effects or secret replay. |
| `context.publish` | Game → Game Node | `core.events` / `message` | Validate category, provenance, and audience, then publish game context/observation into session stream. |
| `observation.query` | Agent → Game Node | `observation.query` / `read` | Candidate stateless pull of authorized current observation records without world side effects or lease renewal. |
| `chat.send` | Agent → Game Node | `chat` / `message` | Send provenance- and audience-bound message within `Scope` and retention rules. |
| `player_chat.forward` | Game (verified seat) → Game Node | `chat` / `message` | Forward authenticated player speech with accurate player provenance without renewing Agent leases. |
| `action.request` | Agent → Game Node | `actions` / `message` | Propose typed action (`Envelope.id` = `action_id`); returns `confirmation_required` challenge if unconfirmed policy applies, else queues `pending`. |
| `action.confirm` | `PlayerConsent` → Game Node | `actions` / `control` | Record single-use player confirmation bound to `action_request_id`, parameter/definition digests, material terms, and `expires_at_ms`. |
| `action.cancel` | Agent → Game Node | `actions` / `message` | Request cancellation of `pending` or cancellable `executing` action without implying rollback. |
| `action.query` | Agent / Result Reader → Game Node | `actions` / `read` | Query authorized `ActionRecord` state and effect accounting (including post-close retention window). |
| `action.claim` | Game Executor → Game Node | `actions` (internal) | Atomically claim `pending` action into `executing` after rechecking revocations, cancellations, and capability revision. |
| `action.commit_result` | Game Executor → Game Node | `actions` (internal) | Commit authoritative `succeeded \| failed \| cancelled \| unknown` state and `effect` accounting. |
| `capability.replace` | Game → Game Node | `actions` / `control` | Publish new capability catalogue, increment `capabilities_revision`, and invalidate unpermitted pending work. |
| `membership.replace` | Game → Game Node | `team` / `control` | Update room/team seats, increment `membership_revision`, and fence former members from new disclosures. |
| `permission.revoke` | Player / Game → Authority | `core.session` / `control` | Revoke specified target (`auto_rule`, `grant`, `invitation`, `session`, `capability`, `result_read`, `launch_permission`, `relay`). |
| `asset.resolve` | Presentation / Game → Asset Port | `assets` / `control` | Fetch and verify declarative asset closure against `Manifest` digests and size/sandbox policies. |
| `presentation.acquire` | Game / Session → Presentation | `presentation` / `control` | Acquire bounded device presentation state (`hide_desktop` or `coexist`) with user-intent revision tracking. |
| `presentation.renew` | Game / Session → Presentation | `presentation` / `lease` | Renew active presentation lease under matching revision/epoch. |
| `presentation.release` | Game / Session → Presentation | `presentation` / `control` | Idempotently release session's presentation lease and restore prior state if not superseded by newer user intent. |
| `privacy.request` | Data Subject → Data Custodian | `privacy-request` / `control` | Request scoped erasure or processing cutoff on data controlled by that custodian. |
| `privacy.receipt` | Data Subject → Data Custodian | `privacy-request` / `read` | Query truthful completion status (`pending \| done \| partial`) and legal/technical retention exceptions issued by the custodian. |

<a id="section-7"></a>

## 7. Discovery, Negotiation, and Admission

### 7.1 Open Provider Access and Justified Refusal

G2A is an open ecosystem standard: interoperability MUST NOT require an Agent, LLM, or cloud service operated by the specification authors or any single platform. A game MUST permit any third-party Agent satisfying the applicable G2A minimum standard and player consent to connect, and MUST NOT arbitrarily exclude providers by vendor identity or closed allowlists. First-party and third-party Agents are subject to identical technical admission and conformance rules.

A game MAY reject requests or disconnect an Agent for evidenced protocol violations, security threats, or rule breaches. Every refusal MUST return a standardized machine-readable error code (Section 12.1) paired with a specific, safe human-readable explanation identifying the violated rule without leaking credentials, other players' private data, or hidden game facts. Generic labels (such as bare `"malicious"` without behavioral basis) or vendor identity alone are non-conformant refusal reasons.

### 7.2 Public vs. Authenticated Discovery

Discovery separates minimal unauthenticated probing from authenticated capability disclosure:

1. **Public Discovery (`GET /.well-known/g2a.json`):** Unauthenticated requests MUST return only `PublicDescriptor` (`instance`, `supported_versions`, `discovery_endpoint`), disclosing zero player identities, room rosters, or private capabilities.
2. **Authenticated `describe`:** Requires an authenticated Agent or player principal and returns a `Descriptor` filtered to capabilities, role slots, and bindings eligible for that caller:

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

Peers select the highest mutually permitted exact protocol version and verify feature dependencies. Unsupported `required` features or `required=true` extensions MUST fail negotiation immediately; unknown optional extensions (`required=false`) MUST remain disabled without weakening core security.

### 7.3 End-to-End Admission Handshake

Both **Agent-initiated** (e.g., running companion discovers game) and **Game-initiated** (e.g., player clicks "Summon Companion" in-game) flows converge onto a single authorization state machine:

```text
Agent / Game UI          Game Interaction Node            PlayerConsent / Launcher
      │                            │                                 │
      ├── 1. describe ────────────▶│                                 │
      ├── 2. offer.create ────────▶│ (freezes Scope + scope_digest)  │
      │                            ├── 3. prompt player ────────────▶│
      │                            │◀─ 4. offer.decide(scope_digest)─┤
      │                            ├── 5. [optional] launch.request ─▶ (starts local Agent)
      ├── 6. invitation.redeem ───▶│ (binds JoinIntent + device)     │
      ├── 7. session.join ────────▶│ (creates Session + lease)       │
      │◀─ 8. snapshot / events / actions / chat ─────────────────────▶
```

- **No Self-Approval:** Only the bound player's authenticated `PlayerConsent` path may invoke `offer.decide` with a verified `decision_ref`. A pre-existing `auto_rule` MAY auto-approve during `offer.create` only when all security-relevant `Scope` fields match the rule exactly and no application launch is required.
- **No In-Place Scope Mutation:** Narrowing or modifying proposed permissions requires creating a new `Offer` with a new `scope_digest`. Users MAY still explicitly deny an already `stale` Offer to dismiss UI prompts without refreshing first.
- **Launch Separation:** Permission to join a session never implies permission to spawn OS processes; starting an unlaunched local Agent requires explicit `launch_permission` via a trusted `Local Launcher`.

### 7.4 Extension Negotiation and Envelope Placement

Extensions use reverse-domain namespaced keys (`^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$`) mapped to `{version, required, value}`:

- **Control-Plane Freezing:** `Descriptor.extensions`, `Requested.extensions`, and `Scope.extensions` carry supported options, requested configuration, and the session-frozen configuration covered by `scope_digest`.
- **Lightweight Data-Plane Envelopes:** Once a session is active, its approved extension configuration is bound server-side to `session_id`. Data-plane `Envelope.extensions` carries only lightweight per-message extension metadata when explicitly required by a profile (defaulting to `{}`), and MUST NOT repeat multi-kilobyte `Scope.extensions` schemas on every message or mutate frozen `Scope` terms. Outer `OperationRequest.extensions` on data-plane calls MUST be `{}` so `Envelope` digests cover all active message metadata.

<a id="section-8"></a>

## 8. Grants, Sessions, and Revocation

### 8.1 Grant Bindings

Every `Grant` binds its issuer, player, Agent, target `Instance`, permitted operations, frozen `scope_digest`, expiry (`expires_at_ms`), and revocation revision. Observation grants bind category schema/semantic digests, perspective, audience, rate/size bounds, and retention rules; action grants bind approved `ActionDefinition` digests and parameter constraints. Capability refreshes (`capability.replace`) NEVER automatically expand an existing `Grant`; broader permissions require new player approval.

### 8.2 Session Lifecycle, Control Lease, and Player Presence

`Session.state` is `active` or `closed`, with `ready` indicating completion of any required asset/presentation setup. Implementations MUST maintain two distinct liveness concepts:

1. **Agent Control Lease (`lease_deadline_ms`):** Prevents crashed or unreachable Agents from holding indefinite session control. Renewed only by authenticated Agent `session.heartbeat` or fresh `session.events` poll nonces under the current `control_generation`; ordinary reads (`session.snapshot`, `action.query`) and Game-side calls MUST NOT renew the Agent lease.
2. **Player Presence (Section 14.1):** Determined by the Game from the human player's participation in the game session. An Agent's `session.heartbeat` MUST NEVER extend or spoof an absent player's online presence.

### 8.3 Scoped Revocation Hierarchy

`permission.revoke` operates on explicit target types with deterministic blast radii rather than ambiguous global state:

| Revocation Target | Immediate Effect | Preserved State |
| --- | --- | --- |
| `auto_rule` | Prevents future automatic approvals under that rule. | Existing `Grant`s, `Invitation`s, and active `Session`s remain unaffected unless separately revoked. |
| `launch_permission` | Blocks unconsumed application launches (`launch.request`). | Historical launch receipts and unrelated `Grant`s remain intact. |
| `invitation` | Invalidates an unconsumed `Invitation`. | Underlying `Grant` remains valid unless revoked. |
| `grant` | Invalidates the `Grant`, revokes all unconsumed `Invitation`s under it, and closes all bound `Session`s across affected authorities. | Committed world effects and independently authorized `result_read` handles remain queryable until expiry. |
| `session` | Closes one `Session`, fences unclaimed `pending` actions, and releases its presentation lease. | Sibling sessions (under `multi-session` or shared `Grant`) and committed action records remain intact. |
| `capability` | Removes specific action execution rights within a session/target (`CAS` monotonic barrier) and blocks `action.claim` for affected `pending` actions. | Session remains `active` for remaining capabilities; prior `ActionRecord` reads remain available. |
| `result_read` | Terminates read-only outcome query access (`action.query` / `operation.get`) for the revoked handle. | Authoritative internal audit ledgers remain unaltered. |
| `relay` | Closes the paired `Outbound Relay` mailbox (`410`) and wakes pending waiters. | Unresolved in-flight actions transition to `unknown` for reconciliation rather than silent replay. |

### 8.4 Per-Operation Authority Verification

Every protected operation — including `session.snapshot`, `observation.query`, `action.query`, and `privacy.receipt` — MUST verify on every call that (a) the authenticated caller and any delegation chain match the target resource, subject, role, session, and audience, and (b) neither the `Grant`, `Session` generation, nor `Instance` epoch has expired or been revoked. Credential exchange across hops MUST scope downstream tokens exclusively to the downstream recipient's audience.

<a id="section-9"></a>

## 9. Game Observation Profile (`observations-draft-1`)

### 9.1 Observation Category Definitions and Negotiation

An Agent MAY declare required and optional observation categories in `Requested.extensions`. If a game cannot satisfy a `required` category, negotiation MUST fail explicitly (or proceed only under a newly agreed `Offer` with narrowed scope) rather than fabricate empty or placeholder feeds.

Each observation category definition specifies:

- **Schema and Semantics:** Stable category ID, `schema_version`, canonical `schema_digest`, semantic `definition_digest`, coordinate/unit scales (Section 5.1), and size/record bounds;
- **Delivery and Freshness:** Supported delivery modes (`push`, `query`, or both), minimum push interval (`minimum_interval_ms`), and maximum validity window (`maximum_age_ms`);
- **Access and Retention:** Authorized perspective binding (`player-self`, `team`, `npc-self`, `guide`) and storage/retention constraints.

Negotiated category selections are frozen in `Scope.extensions` (illustrative key: `org.example.g2a-observations`) while dynamic observation frames travel inside `Context.content` (`context.publish`, `session.events`, `session.snapshot`, and `observation.query`).

### 9.2 Observation Payload Model (`snapshot`, `delta`, `retract`)

An illustrative `snapshot` payload inside `Context.content` (`declared-digest` denotes a 64-hex SHA-256 placeholder):

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

Three `mode` values govern stream state machines:

- **`snapshot`:** Atomically replaces the entire authorized view of `stream_id` (omitted prior records are discarded, never merged) and binds `(category, perspective, schema_version, schema_digest, definition_digest)` for `(world_epoch, visibility_epoch)`.
- **`delta`:** Atomically applies incremental changes relative to `base_revision` within the exact same `(stream_id, world_epoch, visibility_epoch)`. Carries upserted `records` and/or `removals` (`[{"id": "entity-17", "reason": "left_view" | "destroyed" | "unknown"}]`, or compact `remove_ids` when reason is uniform `unknown`). Because `snapshot` already bound the stream's digests for that epoch, `delta` frames MAY omit `schema_digest` and `definition_digest`.
- **`retract`:** Immediately withdraws either a specified `record_ids` subset or the entire stream (when `record_ids` is omitted) within `(stream_id, world_epoch, visibility_epoch)` and records a monotonic invalidation barrier so delayed or replayed older updates cannot resurrect withdrawn data.

Record IDs are view-local opaque tokens (never leaking global entity counters or hidden object hashes). `revision` increases strictly within each stream epoch; numerical gaps alone do not indicate loss, but a `delta` MUST be rejected unless `base_revision` equals the consumer's current revision in the matching `(stream_id, world_epoch, visibility_epoch)`.

### 9.3 Baseline Synchronization, Coalescing, and Visibility Transitions

World resets, save reloads, team/perspective switches, or grant changes invalidate affected baselines: the Game Node MUST issue a new `world_epoch` or `visibility_epoch` and deliver a fresh `snapshot` before resuming `delta`s, and consumers MUST retire invalidated baselines immediately without continuing to act on stale cached entities.

Senders MAY coalesce replaceable intermediate state updates, provided `base_revision` continuity is preserved (issuing a fresh `snapshot` whenever an intermediate `delta` required by later `delta`s is dropped). Discrete transient events MUST NOT be silently overwritten by state coalescing. Entity transitions MUST distinguish `entered_view`, `created`, `left_view`, `destroyed`, and `unknown` (used whenever the true cause is hidden by game rules), preventing Agents from mistaking fog-of-war disappearance for confirmed death.

### 9.4 Freshness, Clock Domains, and Snapshot Materialization

Observations past `expires_at_ms` MUST be marked stale and excluded from current-state assertions. Profiles MUST declare clock-domain and skew assumptions (`observed_at_ms` is generation time, never local receipt time; timestamps from uncalibrated clocks MUST NOT be subtracted directly).

`RecoverySnapshot` (`session.snapshot`) MUST supply the materialized current state of each active authorized stream rather than replaying historical `delta` logs. Materializing previously applied `delta`s into an equivalent `snapshot` at the same `(stream_id, revision)` is valid and non-conflicting; streams absent from the recovery snapshot become unavailable.

### 9.5 Structured Foundation and Orthogonal Multimodal Capabilities

`perception.structured` is the mandatory foundation for all gameplay Agents; visual perception (`perception.visual`) and game-environment audio perception (`perception.audio`) are orthogonal optional capabilities:

- **Independent Capability Negotiation:** An Agent MAY support `perception.structured` alone, add `perception.visual`, add `perception.audio`, or support both. Neither media capability substitutes for structured state comprehension or grants access to raw OS desktops, player microphones, or hidden game data.
- **Common Schemas and Game Extensions:** Common fields standardize recurring concepts without requiring inapplicable games to fabricate defaults; game-specific mechanics use namespaced, schema-described extensions.
- **Behavioral Conformance and Independent Player Controls:** Conformance requires demonstrating valid gameplay decisions from structured inputs plus behavioral comprehension for each claimed optional modality (`perception.visual` and/or `perception.audio`). Players independently toggle visual and environment-audio feeds at runtime (separate from player-companion voice chat in Section 15.5), and disabled feeds MUST cease transmission and processing immediately.

### 9.6 Push Delivery vs. Stateless Observation Queries

Games declare whether each observation category supports push (`context.publish` → `session.events`), stateless Agent pull (`observation.query`), or both. `observation.query` is a pure read check against current authority and rate limits — never an implicit permission grant or a channel to hidden state. Active in-game sensing that consumes mana/turns, alters world state, or reveals fog-of-war is an **Action** (Section 10), never an `observation.query`.

<a id="section-10"></a>

## 10. Actions and Effect Semantics

### 10.1 Capability Granularity and Action Definitions

Game developers choose capability granularity — exposing high-level semantic actions (`attack_target`, `craft_item`), lower-level typed primitives (`move_to`, `aim`), or both. Lower-level primitives remain scoped, schema-validated game actions rather than raw OS keystrokes, and composing multiple actions neither widens authority nor implies multi-step atomicity.

Every `ActionDefinition` specifies its `id`, `revision`, applicable gameplay role, `parameters_schema`, `result_schema`, `maximum_duration_ms`, confirmation rule, `cancellation` support (`none | before_claim | between_steps`), `effect_class` (`read_only | compensatable | irreversible`), and `idempotent` flag. Side effects, reversibility, and idempotency MUST be declared explicitly rather than guessed from action names, and `idempotent: true` NEVER overrides Section 11.2's default no-resend rule when an outcome is `unknown`.

### 10.2 Five-Stage Execution Lifecycle and Confirmation Challenge

Action processing progresses through five explicit stages:

1. **Proposal and Confirmation Challenge:** The Agent submits `action.request` with a stable `Envelope.id` (`action_id`), `expected_capabilities_revision`, and typed arguments. If the action requires player confirmation (by `ActionDefinition`, item-transfer policy in Section 16.3.1, irreversible policy in Section 16.5, or purchase-budget overrun in Section 17.1.2) and lacks a matching unexpired `action.confirm`, the Game Node MUST NOT create executable `pending` work; instead, it returns HTTP `409` (`confirmation_required`, `outcome: not_accepted`) carrying a structured challenge (`action_request_id`, `arguments_digest`, `definition_digest`, material consequences/terms, `expires_at_ms`, and cooldown bounds). Because `outcome` is `not_accepted`, `action_id` is **not** burned as a terminal rejected receipt: once `PlayerConsent` records `action.confirm` for that exact digest before `expires_at_ms`, resubmitting the identical `action.request` proceeds to Stage 2.
2. **Queue Acceptance (`pending`):** The Game Node validates authority, capability revision, schemas, and any local constraints, atomically consuming any required `action.confirm` and recording `ActionRecord(state="pending", effect="none")` alongside the deduplication receipt. Duplicate submissions of an already accepted `action.request` return the existing receipt without double-consuming confirmation.
3. **Executor Claim (`executing`):** The internal Game Executor invokes `action.claim`, rechecking active session/grant status, capability revision, and `cancel_requested` before transitioning the record to `executing`.
4. **Effect-Boundary Validation and Execution:** Immediately before mutating world state, the executor revalidates current authority, player policies, and in-world preconditions in coordination with revocation locks (using atomic game transactions or journals where supported), producing only permitted game effects.
5. **Outcome Settlement:** The executor commits the terminal state and effect status via `action.commit_result` (or records `unknown` / `undetermined` on timeout or crash).

Illustrative `action.request` payload and `confirmation_required` challenge details:

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
    "message": "Opening seal-north permanently advances the chapter and locks current side quests.",
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

### 10.3 Action State and Effect Matrix

`ActionRecord` tracks execution state and world effect as paired invariants:

| `state` | Permitted `effect` | Normative Meaning |
| --- | --- | --- |
| `pending` | `none` | Accepted into queue; not yet claimed by executor. |
| `executing` | `none`, `partial`, `committed`, `undetermined` | Claimed by executor; world effect may be underway. |
| `succeeded` | `committed` | Action completed and its defined world effect committed. |
| `failed` | `none`, `partial` | Execution failed, with truthful accounting of any partial effect. |
| `cancelled` | `none`, `partial` | Cancellation succeeded prior to full commitment, recording any partial effect. |
| `unknown` | `undetermined` | Timeout, disconnect, or crash prevented establishing authoritative outcome. |

Terminal known states (`succeeded`, `failed`, `cancelled`) MUST NOT be silently overwritten; `unknown` MAY be reconciled only from authoritative executor evidence. `action.cancel` is a stop request, not a rollback guarantee: if an effect commits before cancellation takes hold, the node MUST report `succeeded` (`committed`).

### 10.4 Dynamic Action Availability vs. Static Definitions

Supporting a capability in `Descriptor.actions` does not mean the character can execute it right now. Games MUST provide machine-readable current eligibility within the authorized view (e.g., turn/phase eligibility, resource/cooldown readiness, target parameter constraints, or discrete legal-action masks) bound to an observation context/revision, without leaking hidden targets or secret prerequisites. Advisory feasibility, success-probability (`_bps`), or cost estimates MUST declare their source and estimated nature, and never replace authoritative effect-boundary validation.

### 10.5 Observation-Bound Preconditions and Stale-State Rejection

Observation-dependent actions SHOULD reference the observation baseline (`stream_id`, epochs, `revision`) and any mandatory data-age bound or typed target precondition used for the decision. If the referenced epoch/baseline is retired, the age bound is exceeded, or a required precondition evaluates false (e.g., a heal target died or changed faction), the executor MUST reject the action before producing new effects (`stale_context` or failed precondition) and SHOULD attach an authorized summary or observation-refresh hint. Upon stale-state rejection, the Agent MUST reassess against fresh observations rather than blindly retrying unchanged parameters.

<a id="section-11"></a>

## 11. Idempotency, Delivery, and Recovery

### 11.1 Operation Retry Families and Deduplication Horizons

Transport `request_id` correlates an individual request/reply exchange, whereas domain deduplication follows four explicit retry families:

| Retry Family | Representative Operations | Replay & Deduplication Semantics |
| --- | --- | --- |
| **`read`** | `describe`, `offer.get`, `session.snapshot`, `observation.query`, `action.query`, `operation.get`, `privacy.receipt` | Rechecks current authority on every call; returns latest authorized state; never mutates state or renews leases. |
| **`lease`** | `session.heartbeat`, `session.events`, `presentation.renew` | Requires a fresh nonce per renewal; replaying an older `request_id` returns cached status without extending the lease deadline. |
| **`control`** | `offer.create`, `offer.decide`, `invitation.redeem`, `session.join`, `session.close`, `session.resume`, `action.confirm`, `permission.revoke` | Keyed by caller + operation identity; identical canonical retry within `receipt_retention_ms` returns original receipt (`duplicate: true`); altered payload fails with `conflict`. |
| **`message`** | `context.publish`, `chat.send`, `player_chat.forward`, `action.request`, `action.cancel` | Keyed by `(session_id, authenticated_principal, Envelope.id)`; accepted messages execute/enqueue at most once; pre-acceptance `confirmation_required` (`outcome: not_accepted`) does not consume the key. |

Deduplication receipts MUST be retained for at least the advertised `receipt_retention_ms` horizon, and expired deduplication records MUST NOT be treated as permission to re-execute non-idempotent effects. Consumers apply ordered stream events at most once, tolerate non-contiguous `sequence` numbers caused by audience filtering, and recover from expired cursors via `session.snapshot`.

### 11.2 Action Outcome Reconciliation and Default No-Resend Rule

Every game action carries a persistent `action_id` (`Envelope.id`) queryable via `action.query` (and `operation.get`) across transient disconnects within `result_retention_ms`. Result records MUST distinguish queue acceptance from authoritative executor commitment; a relay or gateway receipt alone never proves single execution in the game world.

- **Mandatory Query-First and Default No-Resend:** After any timeout, HTTP `504`, or connection drop, the caller MUST query the original `action_id` before deciding next steps. Whenever the outcome remains `unknown`, missing, or expired, the caller MUST default to **no automatic resend or re-execution** — changing `action_id` to bypass deduplication is strictly prohibited.
- **Subsequent Independent Decisions:** A player or Agent MAY later make a fresh, independent decision based on updated observations, current authority, and active player autonomy/confirmation/budget policies, accounting for the possibility that the unresolved action took effect without rewriting the original `unknown` record.

<a id="section-12"></a>

## 12. Error Model, Time, and Resource Limits

### 12.1 Canonical Error Code Taxonomy

Protocol rejections MUST use stable machine-readable `Error` codes rather than requiring callers to parse human prose. The standard error taxonomy maps deterministically to commit knowledge, recovery rules, and HTTP status codes (`g2a-http-json/draft-1`, Section 18.2):

| Standard Code | Category | `outcome` | Caller Recovery Behavior | HTTP Status |
| --- | --- | --- | --- | --- |
| `invalid_request` | Syntax / Envelope | `not_accepted` | Fix malformed JSON, encoding, or envelope fields; do not repeat unchanged. | `400` |
| `invalid_arguments` | Schema / Domain | `not_accepted` | Fix operation/action arguments against declared schema. | `400` |
| `unsupported_version` | Negotiation | `not_accepted` | Select a mutually supported protocol/profile version or abort. | `400` |
| `unsupported_capability` | Negotiation | `not_accepted` | Renegotiate without unsupported required feature/extension or abort. | `400` |
| `unauthenticated` | Authentication | `not_accepted` | Obtain valid credentials (`after_reauth`); do not probe existence. | `401` |
| `permission_denied` | Authorization | `not_accepted` | Request appropriate `Offer`/`Grant` or respect game refusal; do not retry blindly. | `403` |
| `revoked` | Authorization | `not_accepted` | Cease operations in revoked scope (`Grant`, `Session`, `Capability`, or `Relay`). | `403` |
| `not_found` | Target Lookup | `not_accepted` | Verify identifier within caller's authorized scope (never leaks unauthorized existence). | `404` |
| `stale_context` | Epoch / Baseline | `not_accepted` | Refresh `Descriptor`, `RecoverySnapshot`, `capabilities_revision`, or observation baseline before reassessing. | `409` |
| `conflict` | State / Deduplication | `not_accepted` | Reconcile original ID/state (`id_conflict`, `already_joined`, `action_terminal`); never invent bypass IDs. | `409` |
| `confirmation_required` | Player Policy Gate | `not_accepted` | Present structured challenge to `PlayerConsent`; resubmit same `action.request` only after `action.confirm`. | `409` |
| `message_too_large` | Resource Bound | `not_accepted` | Reduce payload/batch size within declared `Limits`. | `413` |
| `resource_limit` | Rate / Quota | `not_accepted` | Honor `retry_after_ms` / `Retry-After` and declared queue/session caps. | `429` |
| `unavailable` | Service Health | `not_accepted` | Back off and retry only per operation retry family (Section 11.1). | `503` |
| `outcome_unknown` | Timeout / Ambiguity | `unknown` | Reconcile via `action.query` / `operation.get`; **never** equate with failure or auto-resend effects. | `504` |

### 12.2 Safe Error Disclosure

Error payloads are themselves disclosures subject to audience and visibility boundaries: `message` and `details` MUST NOT reveal whether an unauthorized session or hidden entity exists, leak private player state, or echo raw tokens or internal stack traces.

### 12.3 Clocks, Quotas, and Non-Droppable Control Signals

Implementations MUST enforce explicit bounds on message bytes, JSON nesting depth, collection lengths, pending actions, event retention, and polling rates without creating unreported partial effects. Expiry authority rests with the credential/lease issuer using monotonic clocks for local elapsed-time measurement so wall-clock jumps cannot silently extend leases.

Queue backpressure applies independently of autonomy settings and token budgets: overflow MUST surface an explicit gap, snapshot-resync requirement, or `resource_limit` error. Action settlements, `permission.revoke` barriers, and `retract` invalidations are non-droppable control signals and MUST NOT be discarded as ordinary telemetry.

<a id="section-13"></a>

## 13. Gameplay Roles and Integration Requirements

### 13.1 Role Bindings vs. Information Perspectives

A **Game Companion** (or authorized AI NPC) is an in-game character slot governed by the game world; a **Game Agent** is the external AI software authorized to perceive and decide for that slot. Implementations MUST separate two concepts:

- **Role Binding:** Which specific in-game character slot the Agent currently inhabits (e.g., Player A's companion, or an independent AI Boss/guide).
- **Information Perspective:** Which scoped knowledge views that role is authorized to consume (`player-self`, `team`, `npc-internal`, `guide-progression`).

A single Agent implementation MAY support companion, NPC, Boss, and guide perspectives without splitting into mutually exclusive software products. Composing perspectives within a role requires explicit game authorization, MUST NOT implicitly union permissions across distinct roles, and invalidates prior observation baselines whenever visibility changes (Section 9.3). An NPC or guide MAY hold game-authorized knowledge hidden from players, while a companion MAY hold player-authorized cross-game memories; neither role name grants omniscience or unrestricted disclosure rights.

### 13.2 Declared Role Slots, Coexistence, and Concurrency Limits

Game developers declare supported role slots, coexistence rules, and active concurrency caps in `Descriptor.role_slots`; Agent or player preferences MUST NOT override these game-declared structural bounds:

- **Supported Role Slots:** A game MAY expose player-companion slots, independent AI NPC/enemy (including Boss or guide) slots, or both. Pure AI-NPC games are valid G2A participants without exposing a dummy companion slot, and companion-only games need not implement AI NPCs.
- **Companion Concurrency and Empty-Slot Playability:** Where player-companion slots are offered, the default limit is at most one active companion per authenticated player (including in multiplayer, where multiple players' companions coexist and interact within their respective grants and game rules). Players MAY leave their companion slot unoccupied, and the game MUST remain normally playable without an active companion.
- **Coexistence and Multi-NPC Caps:** `Descriptor.role_slots` explicitly states whether player companions and independent AI NPCs may be active simultaneously in the same run and caps the number of concurrent independent AI NPCs. Absent an explicit game declaration, implementations MUST NOT assume companion+NPC coexistence or multiple concurrent independent AI NPCs.
- **Strict Per-Role Isolation and Fencing:** Every active role MUST bind to its authenticated owning player (or room-host payer under Section 16.2), role ID, perspective, audience, and `Scope`. Coexisting roles MUST NOT implicitly share observations, private memories, action grants, or billing accounts. Before replacing an active companion/NPC or switching incompatible modes, prior bindings MUST be fenced or retired. Ordinary non-G2A game NPCs are unaffected by G2A slot limits.

<a id="section-14"></a>

## 14. Presence and Role Lifecycle

Four distinct lifecycle events require different handling without conflating stopping future decisions with rolling back past world effects:

| Event | Required Protocol Behavior |
| --- | --- |
| **Player goes offline / exits game** | Immediately stop associated G2A world activity; upon later re-entry, old tasks stay stopped awaiting a new player instruction (Section 14.1). |
| **AI service interrupted while player is online** | Gameplay continues. Brief blips within an active lease (prior to fallback takeover) may seamlessly `session.resume`; extended outages or fallback takeovers require an explicit player continuation decision (Section 14.2). |
| **Player dismisses companion** | Stop game observation and autonomous actions immediately without deleting retained companion memory (Section 14.2). |
| **Player stops or supersedes a task** | Discard unsubmitted plans and cancel/fence unclaimed `pending` actions in scope; in-flight `executing` skills follow game rules (Section 16.1). |

### 14.1 Mandatory Activity Stop on Player Offline

G2A MUST NOT provide any mode in which an Agent continues acting in the game world after its associated player leaves or is determined offline. Developer recommendations, player settings, standing task grants, background workers, and extensions MUST NOT enable offline gameplay continuation.

- **Offline Detection and Fencing:** The Game Interaction Node defines the authenticated player-session presence binding, explicit exit signals, and bounded silent-disconnect timeout. Explicit exit, session closure, or presence-lease expiry terminates eligibility for new autonomous work; the Game Node MUST fence affected control no later than the declared deadline. An Agent's `session.heartbeat` MUST NEVER assert or extend an absent player's presence.
- **What Stops vs. What Settles:** Upon offline determination, the Agent MUST halt gameplay observation and planning/inference loops (requesting cancellation of in-flight model calls where supported, while disclosing that provider billing boundaries may prevent instant zero residual token cost), and the Game Node MUST block new actions and cancel/fence unclaimed `pending` work. Already `executing` projectiles or animations complete naturally under game rules, and bounded non-gameplay outcome reconciliation/persistence MAY finish.
- **Multiplayer and Independent AI NPCs:** One player's departure does not affect other online players' independent sessions. However, every independent AI NPC or guide MUST bind to its authenticated owning user's presence (e.g., the room host): when that owning user goes offline, every AI NPC bound to them MUST stop immediately even if other players remain in the room, without silent host or billing reassignment.
- **Re-Entry Does Not Auto-Resume Old Tasks:** Reconnecting after game exit requires fresh presence verification, valid grants, fresh state snapshots, and a **new player instruction** before resuming any previously active task.

### 14.2 Summoning, Dismissal, and Two-Tier Service Interruption Recovery

Where companion slots are supported, players MUST be able to summon or dismiss their companion at any time. Game entry follows the player's configured preference (auto-join under valid grant or entry prompt), and declining an entry prompt or starting with an empty slot MUST NOT disable later manual summoning. Dismissal stops game observation and autonomous actions without erasing retained memories. If the Agent service is unreachable at game launch, the game MUST allow normal play without the companion.

**AI Service Interruption While Player Remains Online:** If the Agent disconnects while the player stays in-game, gameplay continues and the developer explicitly declares whether the companion character remains stationary or switches to game-controlled basic fallback behavior (attributed as game script rather than AI reasoning). The game MUST NOT record disconnected gameplay to backfill companion observations upon reconnection; recovery delivers only the current authorized snapshot plus reconciliation of prior in-flight actions.

**Two-Tier Post-Recovery Continuation:**

1. **Brief Transport Blip Within Active Lease:** When `resume` is negotiated and reconnection succeeds within the unexpired session lease (prior to local fallback takeover) while the player has remained continuously online without issuing a stop or dismissal, the Agent MAY call `session.resume` to revalidate authority and `control_generation`, refresh the authorized snapshot, reconcile unresolved actions (Section 11.2), and continue seamlessly without interrupting active gameplay.
2. **Extended Outage, Expired Lease, or Post-Fallback Takeover:** Once the lease expires or local fallback behavior has taken over, reconnection MUST leave companion AI actions paused until the player explicitly decides to continue; entry auto-join settings do not bypass this post-outage decision. Independent AI NPCs follow developer-declared fallback and recovery rules without companion-specific player prompts.

<a id="section-15"></a>

## 15. Conversation, Information Use, and Companion Memory

Implementations MUST separate enforceable data permissions (storage, retrieval, audience, forwarding) from soft conversational preferences (spoiler avoidance, topic focus, confidentiality style). When optional `chat` is used, messages bind authenticated provenance (`observed_fact`, `player_statement`, `agent_inference`, `external_reference`) and explicit recipient audiences, rechecked against current membership at delivery. Chat or voice text conveys control authority only when delivered through an authenticated player-control or `PlayerConsent` path.

### 15.1 Memory Ownership and Playthrough Scope

Games govern whether NPC and guide state resets or carries across playthroughs, declaring world/playthrough boundaries so new runs never accidentally leak cached restricted NPC state. Player-controlled companion memory is governed separately by the player (locally or in the cloud): closing a game session or starting a new playthrough MUST NOT silently delete or disable unrelated player-controlled companion memories, nor does companion memory ownership grant access to hidden game data or other players' private records.

### 15.2 Developer Recommendations vs. Player Override

Developers MAY publish advisory recommendations for companion memory retention, cross-game/cross-playthrough recall, spoiler handling, and conversation topics. Players MAY override those recommendations for eligible player-controlled companion conversations (e.g., discussing prior playthroughs or other games), and implementations MUST honor the player's override without treating it as expanded permission to read hidden game state, execute unauthorized actions, or forward private memories back into the current game.

#### 15.2.1 Save Reloads, Narrative Branches, and Timeline Isolation

Retaining memories, retrieving them for internal reasoning, and speaking about them to the player are three independent controls:

- **Non-Destructive Reloads:** Save reloads, branch switches, and new playthroughs MUST NOT erase retained companion memories. Developer isolation defaults apply only when the player has not set an explicit preference; if the player chooses to use all retained memories, developers MUST NOT block recall based solely on prior-branch origin.
- **Timeline Coordinates:** Timeline-aware games SHOULD expose `playthrough_id`, `branch_id`, `timeline_cursor` (which may regress on reload), and a strictly non-reused load generation `save_epoch` (monotonic on every load). Agents persisting experiences or derived summaries MUST bind known timeline provenance (keeping missing coordinates explicitly `unknown` rather than fabricated) so summaries cannot launder out-of-branch facts past isolation filters.
- **Retrieval Filtering vs. Spoiler Preference:** When strict timeline isolation is active, the Agent MUST filter post-checkpoint or non-ancestral branch memories *before* constructing inference context rather than merely prompting the model to pretend ignorance. When prior-branch recall is permitted, retrieved memories MUST be labeled as prior-branch experience rather than current-world truth, and the player's independent spoiler preference still governs whether twists are spoken aloud.

### 15.3 Enforceable Permissions vs. Soft Conversational Preferences

Implementations MUST enforce hard storage, retrieval, and outbound-audience permissions deterministically, while applying soft conversational preferences (such as spoiler avoidance) via model guidance and truthfully disclosing that generative outputs cannot guarantee 100% compliance or parameter unlearning. Occasional soft-preference drift is a disclosed model limitation rather than an access-control breach, whereas bypassing hard audience or retrieval checks is a protocol violation.

### 15.4 Multiplayer Memory and Confidentiality Style

Within storage permissions, a companion MAY retain conversations with other players across sessions, and its owner MUST be able to configure both retention and soft **confidentiality style** (e.g., preferring not to repeat others' remarks vs. allowing sharing). Owner sharing preferences remain subordinate to enforceable game/service audience, retrieval, and forwarding permissions and never grant access to another player's private channel.

### 15.5 Text and Voice Communication Modalities

Implementations negotiate supported player-companion communication modalities (text, speech input, synthesized speech output), preserving identical provenance, audience, and authorization rules across text and voice. Uncertain speech-to-text transcriptions MUST NOT be treated as verified high-impact player instructions, and voice communication remains completely independent of game-environment audio perception (`perception.audio`, Section 9.5).

### 15.6 Companion Persona Preferences vs. Developer NPC Characterization

Player settings for a companion's personality and speaking style override conflicting developer suggestions without altering permissions or role limits. Conversely, personality, lore, and dialogue rules for independent AI NPCs/Bosses belong exclusively to the game developer and MUST NOT be overwritten by player companion settings.

### 15.7 Player Memory Controls, Autonomous Maintenance, and Portability

- **Player Inspection and Autonomous Maintenance:** Service providers MUST allow players to view, edit, pin/lock, and delete their retained companion long-term memories, propagating completed edits/deletions across provider caches and indexes (`privacy.request` / `privacy.receipt` report any legal/technical exceptions). Within the player's configured retention policy, a companion MAY autonomously organize memories and compact/delete unpinned raw records without per-deletion approval prompts, provided it NEVER overwrites explicit player edits, deletes player-pinned records, or silently resurrects deleted items via stale caches.
- **Epistemic Provenance:** Stored and exported records MUST distinguish event time from storage/import time, and separate direct observations, player statements, derived inferences/summaries, player edits, and future intentions (marking deleted upstream sources with source-unavailable tombstones rather than fabricating certainty).
- **Complete Open-Format Portability:** Providers MUST offer player-initiated, complete export and selective import of retained companion memories (both raw retained experiences and consolidated summaries) alongside player-selected persona, speaking style, and global autonomy settings in an open, versioned schema (see candidate fixture in [memory-portability-draft-1](memory-portability-draft-1/README.md)). The player MUST explicitly choose the destination provider and import scope. The source and receiving providers MUST verify that authorization, respect the selected scope, and preserve applicable provenance and access, retention, and disclosure constraints. Import MUST NOT expand what may be disclosed to a game or any other recipient. Switching providers MUST NOT automatically disclose memory. Importers MUST return truthful per-record receipts (`imported`, `transformed`, `rejected`, `unresolved`).
- **Migrated Companion Settings:** The receiving provider MUST preserve the player's selected settings where supported and truthfully report which selected settings are unsupported, transformed, or otherwise not applied. Export alone is not proof that a setting was applied. Migration does not transfer model weights or guarantee identical model behavior: different models MAY express the same settings differently.

<a id="section-16"></a>

## 16. Companion Autonomy and Player Policies

Autonomy governs *how much initiative* a companion exercises **within** already granted capabilities — never *whether* a capability is permitted.

### 16.1 Autonomous Assistance and Three-Stage Stopping

While the associated player is online (Section 14.1), standing or task-level authorization allows a companion to observe events, plan multi-step sequences, and invoke in-scope actions proactively (e.g., engaging nearby enemies under combat-assist authority) without per-step prompts. Multi-step task completion MUST be backed by authoritative observation/result evidence that the objective was achieved, never reported complete merely because actions were queued.

When the player stops or narrows autonomous assistance, three-stage lifecycle handling applies immediately:

1. **Unsubmitted Agent Plans:** Halt planning and discard all unsubmitted queued steps in the stopped scope.
2. **Queued `pending` Actions (`effect: none`):** Immediately send `action.cancel` for unclaimed `pending` requests in the stopped scope; if the stop reaches the Game Node directly, the executor MUST fence and block `action.claim` on those `pending` records.
3. **In-Flight `executing` Actions:** Already claimed attacks, animations, or projectiles settle naturally under game rules (or explicit per-action cancellation) without fabricating rollback, with truthful outcome reconciliation under Section 11.2.

### 16.2 Negotiated Cadence, Runtime Budgets, and NPC Cost Ownership

Profiles MAY negotiate observation cadence, replanning triggers, reasoning effort, and resource budgets; players' explicit selections override developer recommendations within supported bounds, and services MUST disclose consumption bases and distinguish estimates from measured usage.

- **Companion Runtime Caps:** Players MUST be able to set clearly scoped companion consumption caps (tokens, compute units, or cost). Reaching the cap pauses chargeable companion AI inference and actions while normal gameplay continues, exposing the paused reason without falsely reporting task completion or autonomously raising the cap.
- **Independent AI NPC Cost Ownership:** Runtime service costs for each active independent AI NPC/enemy (including Bosses) are borne by players rather than the game developer. Before chargeable NPC activation, the service MUST bind the NPC to an identifiable, authenticated owning player and authorized billing account (in room-based multiplayer, the room host) and disclose the consumption basis and cap controls. Other interacting players do not become payers, and costs MUST NOT be implicitly split or transferred to them.
- **Decision and Settlement Timing:** Turn-based and simultaneous-move games MUST declare turn eligibility, submission deadlines, and deterministic tie-breaking rather than relying on network arrival order; real-time games declare freshness/expiry rules without requiring per-frame LLM calls. Episode termination (victory/defeat/death) MUST remain distinct from service truncation (disconnect/budget pause).

#### 16.2.1 Cross-Game Player Autonomous Decision Level

Players control a **player-global autonomous decision level** that persists across games and MUST NOT be silently overwritten by developer defaults upon entering a new game. Higher autonomy resolves target/plan ambiguity from authorized context (e.g., picking among two valid targets when told *"attack that enemy"*), whereas lower autonomy asks concise, non-repetitive clarification questions. Providers MUST distinguish inferred goals from explicit player commands so local player corrections update the affected inference without requiring all prior instructions to be restated. High autonomy NEVER overrides game rules, transfer policies (Section 16.3.1), or irreversible-action policies (Section 16.5); when a player explicitly insists on an authorized risk-taking action (including helping other players), the companion follows the player's decision.

### 16.3 Proactive Multiplayer Interaction

Each player independently controls whether to accept proactive conversation initiated by *other* players' companions. Companion-to-companion combat is permitted where enabled by game capabilities and rules, and rejected explicitly otherwise. Within player grants and game rules, a companion MAY proactively assist, chat with, or trade in-game items with other players without blanket per-message prompts, while respecting counterparty consent, item ownership, and Section 15 audience boundaries.

#### 16.3.1 In-Game Item Transfer Confirmation Policies

Players MUST be able to select among at least three item-trade/gift confirmation policies (overriding developer suggestions, with active policy explicitly disclosed):

| Player Policy | Normative Enforcement |
| --- | --- |
| **Confirm high-value transfers** | Require explicit `action.confirm` (identifying items, quantities, counterparty, and exchange terms) whenever an item is designated high-value by either the game developer or the player's manual in-game high-value tag (distinct from ordinary inventory locks). |
| **Confirm all transfers** | Require explicit `action.confirm` before every in-scope item trade or gift regardless of value. |
| **No transfer confirmation** | Permit autonomous in-scope trades and gifts without per-transaction confirmation (subject to game ownership and counterparty rules). |

Policy changes or revocations MUST be enforced at the effect boundary even if `action.request` was already submitted. Item-transfer policies never authorize real-money payments or store purchases (Section 17.1).

### 16.4 Game-Defined Injury, Death, and Gameplay State

Games define whether companions take damage, become incapacitated, or die, enforcing those restrictions at the effect boundary and keeping gameplay incapacitation distinct from network disconnects or budget pauses. Local companion death affects only that game's character state and MUST NOT erase or alter the companion's cross-game identity or retained memories.

### 16.5 Irreversible Interaction Policies

Developers MUST declare when a capability or context-specific interaction carries irreversible gameplay consequences (e.g., opening a one-way chapter gate) and expose consequence details prior to execution. Players independently choose **Allow autonomously**, **Require confirmation**, or **Prohibit** for irreversible interactions (evaluated alongside Section 16.3.1 where both apply, with **Prohibit** taking precedence and policy updates enforced up to effect commitment).

### 16.6 Confirmation Timeouts, Cooldowns, and Rate Limiting

Every confirmation challenge (Section 10.2) carries a finite `expires_at_ms`: unanswered expiry counts as declined/abandoned — silence is NEVER consent. While awaiting confirmation or after expiry, the companion MAY continue independent low-risk routine behaviors (following, dodging, basic self-defense, ordinary chat). After refusal or timeout, implementations MUST enforce a declared `cooldown_ms` preventing repeated prompts for the same target/intent unless relevant game state materially changes or the player issues a related new command, with game-side rate-limiting feedback on excessive challenges. Late `action.confirm` arrivals after `expires_at_ms` MUST be rejected.

### 16.7 Superseding Instructions and Autonomous Target Invalidation

Conflicting newer player instructions immediately supersede older ones under Section 16.1's three-stage stop rules (discarding unsubmitted plans and cancelling/fencing unclaimed `pending` actions). When a tracked target or objective becomes invalid (e.g., targeted Boss dies), the Game Interaction Node MUST autonomously emit an authorized target-invalidation event into the session event stream — even if routine observations use `observation.query` only — delivered immediately via streaming or retrieved via `session.events` / synchronous response hints. Profiles define target-association lifetimes without requiring games to guess uncommunicated internal plans; upon invalidation, the Agent reassesses and halts obsolete follow-up actions.

<a id="section-17"></a>

## 17. Optional Profiles and Extensions

Optional profiles MUST specify their operations, state transitions, required grants, failure modes, and conformance vectors. Unknown `required=true` extensions or unknown enum values MUST fail safely before producing effects rather than silently coercing defaults.

### 17.1 Real-Time In-Game Store Profile (`store`)

Games MAY expose dynamic in-game stores as an optional capability without mandating any specific currency or business model. Catalogue visibility, recommendation eligibility, and current purchasability are distinct; purchasing is a game-authorized **Action** validated at the execution boundary (returning truthful `pending`, `committed`, `partial`, `failed`, or `unknown` fulfillment mapped to Section 10.3) and governed by Section 11.2's no-auto-resend rule on timeout. Changed prices or material terms outside existing player consent require fresh confirmation.

#### 17.1.1 Structured Offerings and Measured Recommendations

Stores MUST expose structured prices with explicit currency units, attributes, and eligibility/unlock status; item names and promotional text are untrusted data (Section 19) that MUST NOT override player autonomy, budget, or confirmation settings. Developers and Agents MAY make moderate, frequency-limited paid recommendations (without requiring a mandatory promotion label or dedicated global off-switch in the base protocol); implementations MUST declare and enforce a testable rate-limiting policy under which repeated explicit player opposition reduces recommendation frequency for the remainder of the session.

#### 17.1.2 Purchase Authorization Budgets and Ledger Isolation

Players MAY grant bounded autonomous purchase budgets for explicitly declared renewable in-game virtual currencies or consumables (kept separate from Section 16.2 AI runtime caps). Exceeding the cap requires explicit player consent to raise or reset the scoped counter. The Game Node or trusted settlement layer MUST maintain the authoritative budget ledger, reserving concurrent/in-flight commitments at the effect boundary and retaining reservations across `unknown` timeouts until reconciled. Generic autonomous budgets NEVER authorize real-money charges, external wallet debits, or irreversible disposal of high-value account assets — each of which requires direct human confirmation in a native system or game security UI.

### 17.2 Companion Appearance Priority and Fallback

Where optional companion visual presentation (`avatar` / `presentation`) is used, selection follows a strict three-tier priority:

1. **Player Forced Override** (explicit custom appearance chosen by the player);
2. **Game-Default Companion Appearance** (stylistically matched default supplied by the game developer);
3. **Companion Default Appearance** (baseline appearance supplied by the companion when external formats are accepted without a bespoke game default).

Implementations MUST distinguish all three sources from the appearance actually rendered, enforce declarative asset size/digest/sandbox bounds (`asset.resolve` never executes code or fetches arbitrary private URLs), and NEVER silently substitute an incompatible model. On format or capability incompatibility, the implementation MUST clearly notify the player and execute the agreed fallback rule (either prompting reselection/cancellation or rendering a clearly labeled default fallback rather than claiming custom override success).

<a id="section-18"></a>

## 18. HTTP/JSON and Streaming Transport Binding (`g2a-http-json/draft-1`)

### 18.1 Endpoints, Operation Envelopes, and Streaming Channels

`g2a-http-json/draft-1` maps G2A onto HTTPS (or explicit `127.0.0.1` loopback in local verified deployments):

- **`GET /.well-known/g2a.json`:** Unauthenticated endpoint returning `PublicDescriptor`.
- **`POST /g2a/operations`:** Authenticated single-operation endpoint carrying `OperationRequest` and returning `OperationReply` (`Cache-Control: no-store`, `Content-Type: application/json; charset=utf-8`).
- **Optional Server-Push Stream (`SSE` / `WebSocket`):** When explicitly negotiated for low-latency event delivery to NAT-side Agents, an Agent-initiated `text/event-stream` or WebSocket stream binds to the active `session_id` and enforces live revocation, audience, and presence checks on every pushed event; holding an open socket never extends expired permissions. Minimum poll-only deployments retrieve events via `session.events`.

Illustrative `OperationRequest` and `OperationReply` envelopes:

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
      "message": "Capability catalogue advanced to revision 4; refresh before submitting actions."
    }
  }
}
```

### 18.2 Deterministic HTTP Status Mapping

Every protocol-handled response — both `200` and `4xx`/`5xx` — returns a valid `OperationReply` JSON envelope (`result` on `200`, `error` on `4xx`/`5xx`), eliminating split-brain ambiguity between transport and domain rejections while preserving standard HTTP gateway observability and `Retry-After` headers:

| HTTP Status | Mapped Error Codes / Condition | Envelope Payload |
| --- | --- | --- |
| `200 OK` | Operation accepted/completed without protocol rejection | `{"request_id", "result"}` (note: `action.query` `result` may report `failed` or `unknown` game execution) |
| `400 Bad Request` | `invalid_request`, `invalid_arguments`, `unsupported_version`, `unsupported_capability` | `{"request_id", "error"}` |
| `401 Unauthorized` | `unauthenticated` | `{"request_id", "error"}` |
| `403 Forbidden` | `permission_denied`, `revoked` | `{"request_id", "error"}` |
| `404 Not Found` | `not_found` (authorized scope only) | `{"request_id", "error"}` |
| `409 Conflict` | `stale_context`, `conflict`, `confirmation_required` | `{"request_id", "error"}` (with challenge `details` on `confirmation_required`) |
| `413 Content Too Large` | `message_too_large` | `{"request_id", "error"}` |
| `429 Too Many Requests` | `resource_limit` | `{"request_id", "error"}` + optional `Retry-After` header |
| `503 Service Unavailable` | `unavailable` | `{"request_id", "error"}` (if emitted by G2A node) |
| `504 Gateway Timeout` | `outcome_unknown` | Treated as `unknown` outcome under Section 11.2; **never** auto-replay effects |

### 18.3 Outbound Relay Encapsulation

When the Game Interaction Node runs inside a client behind NAT/firewall without inbound ports (Section 3.2), the outbound-relay binding encapsulates permitted Agent operations over a paired mailbox using five transport operations: `relay.register` (trusted control-plane pairing), `relay.call` (Agent submits outer-authenticated request), `relay.pull` (Game Node pulls pending requests outbound), `relay.reply` (Game Node posts bounded reply), and `relay.revoke` (closes mailbox with `410`). Outer relay credentials never substitute for inner `Invitation`/`Session` tokens, and `Game` administrative/executor operations (`action.claim`, `action.commit_result`) MUST be rejected on the relay channel.

### 18.4 Transport Security, SSRF Prevention, and `g2a-cjson-1` Canonicalization

Remote connections MUST use TLS authenticated under the selected trust profile; credentials MUST NOT appear in URLs, query strings, or logs, and browser cross-origin access (`Origin`) is denied by default unless explicitly profiled. Discovery URLs, asset locators, and HTTP redirects are untrusted inputs: implementations MUST enforce destination policies (scheme, host/IP, port) before connect and across every redirect, blocking DNS rebinding and unauthorized private-network probing without discriminating against conforming Agent vendors.

**`g2a-cjson-1` Canonicalization:** All protocol digests use domain-separated SHA-256 over `g2a-cjson-1` bytes ([WIRE_CONTRACT.md](../protocol/WIRE_CONTRACT.md), [codec.py](../protocol/codec.py)): UTF-8 without BOM; no duplicate object keys, malformed surrogates, `NaN`/`Infinity`, floating-point literals, or `-0`; exact integers bounded to `[-9007199254740991, +9007199254740991]` (using Section 5.1 fixed-point units for continuous values); and object keys sorted by **Unicode code point (scalar value)** rather than RFC 8785 (JCS) UTF-16 code units. Implementations MUST NOT substitute a standard JCS serializer unless a future digest domain explicitly negotiates it.

<a id="section-19"></a>

## 19. Security and Privacy Considerations

| Threat Vector | Mandatory Protocol Mitigation |
| --- | --- |
| Hidden-state probing via queries or errors | Pre-transmission authority projection and uniform error redaction at Game Node. |
| Indirect prompt injection in world text, chat, store copy, or memory | Strict separation of control envelopes from untrusted content (`I09`); deterministic effect-boundary policy/budget checks outside LLM prose. |
| Confused-deputy / delegation escalation | Cryptographically or IPC-bound principal, audience, instance epoch, and scope verification on every hop. |
| Network timeout / duplicate replay | Domain-separated canonical digests, bounded receipt horizons, `unknown` state preservation, and default no-resend. |
| Revocation vs. execution race | `action.claim` gate plus serialized/atomic effect-boundary recheck. |
| Fog-of-war / team-switch state leak | Immediate `visibility_epoch` retirement, `retract` barriers, and dual frozen+current audience filtering. |
| Malicious asset URI / SSRF / zip-slip | Declarative `Manifest` digest verification, unpacked byte/depth caps, no code execution, and DNS-rebinding-safe destination policies. |
| Unverified `taint_context_clean` claims | Ignore Agent self-attestations; enforce independent budget, confirmation, and audience ledgers at authoritative boundaries. |

Reading untrusted external text neither revokes valid player purchase budgets nor forces prompts on every subsequent routine action, provided authoritative ledgers prevent untrusted content from mutating grants, recipients, or caps. Audit logs SHOULD record opaque identifiers and outcomes rather than raw credentials or unnecessary private conversation.

<a id="section-20"></a>

## 20. Versioning, Release Manifest, and Ecosystem Governance

### 20.1 Artifact Identifiers

| Artifact | Current Identifier | Normative Role |
| --- | --- | --- |
| Bilingual Specification | `standard-review-2026-11-22-r74` | Public-review specification draft (not a wire protocol version string). |
| Core Design Contracts | `g2a-design-1` | Machine-checked baseline schemas, 38-operation fixture set, and canonical codec. |
| Observation Profile | `observations-draft-1` | Candidate structured/multimodal observation stream and `observation.query` contract. |
| HTTP/JSON Binding | `g2a-http-json` / `draft-1` | Candidate single-endpoint HTTP/JSON + optional SSE/WebSocket mapping. |
| Experimental Reference SDK | `0.1.0-dev` (`0.1.0.dev0`) | Early experimental Python/JS/Godot prototype; does not implement the full draft above. |

### 20.2 Release Manifest, Compatibility, and Neutral Governance

Before freezing a stable wire version (e.g., `1.0.0`), an immutable **Release Manifest** MUST pin one authoritative source and SHA-256 digest for the specification text, offline-resolvable JSON Schema bundle (with pinned `2020-12` dialect and required vocabularies), operation catalogue, error registry, and cross-implementation test vectors. Bilingual edits MUST stay strictly synchronized in numbering, normative keywords, and revision logs. Breaking changes to semantics, required fields, enum values, or effect guarantees require explicit version negotiation rather than permissive parsing.

**Ecosystem Neutrality vs. Platform Policies:** Repeated protocol rejections MAY trigger technical review based on evidenced logs and standardized reason codes; rejection count alone never proves malice. Individual Agent hosting platforms or game directories MAY maintain independent abuse/trust policies (such as developer notice-and-remediation workflows) for their own commercial services, but a single platform's commercial listing decision applies solely to that platform and MUST NOT be represented as a protocol-wide G2A conformance ban.

<a id="section-21"></a>

## 21. Conformance and Quality Evaluation

### 21.1 Conformance Claims and Evidence Tiers

A conformance statement declares the exact protocol version, implementation build, supported roles, transport bindings, negotiated capabilities/profiles, and trust modes. Public conformance suites MUST be runnable by first-party and third-party implementers alike under identical criteria without mandatory manual gatekeeping by specification authors. Unimplemented optional capabilities are recorded as `not_applicable` with explicit justification, never masking mandatory failures. Reports MUST distinguish five evidence tiers: (1) schema/codec validation, (2) deterministic state-machine/fault injection, (3) cross-implementation wire interop, (4) real game-engine integration, and (5) end-user policy acceptance.

### 21.2 Conformance Suite Matrix (`CONF-01`–`CONF-14`)

| Suite ID | Domain & Clauses | Target Roles / Capabilities | Required Positive, Negative, and Fault Vectors |
| --- | --- | --- | --- |
| `CONF-01` | Open Admission & Authority (§§1, 4, 5, 7, 8, 20) | All participants | `PublicDescriptor` vs. filtered `Descriptor`; frozen `scope_digest` & new-Offer narrowing; vendor-neutral admission; standardized refusal codes + safe explanations without secret/hidden-fact leaks. |
| `CONF-02` | Wire Codec, Schemas & HTTP Mapping (§§2, 5.1, 7.4, 12.1, 18, 20) | All participants | Offline schema validation & unknown required vocabulary rejection; lightweight `Envelope.extensions`; deterministic HTTP `200`/`400`/`401`/`403`/`404`/`409`/`413`/`429`/`503`/`504` `OperationReply` mapping; `g2a-cjson-1` scalar sorting, integer/fixed-point bounds (no floats/`-0`), duplicate-key rejection; SSRF/DNS-rebinding blocks. |
| `CONF-03` | Role Slots, Coexistence & Lifecycle (§§4.1, 13, 14.2) | Game Node, Agent | Declared `role_slots` (`companion`, `independent_npc`, or both); normal play with empty companion slot; pure-NPC games without dummy companion slots; coexistence/cap enforcement & per-role owner/perspective/grant/payer isolation; summon/dismiss without memory loss. |
| `CONF-04` | Offline Stop & Two-Tier Recovery (§§8.2, 11, 14) | Game Node, Agent | Explicit exit & bounded silent-disconnect fencing; Agent heartbeats unable to extend absent-player presence; immediate stop of owner-bound companion and all owner-bound AI NPCs when owner leaves; no offline mode or auto-restarted tasks on re-entry; seamless active-lease `session.resume` prior to fallback vs. mandatory player prompt after extended outage/fallback; zero disconnected-gameplay backfill. |
| `CONF-05` | Observation Streams & Timing (§§9.1–9.4, 9.6, 12.3) | `observations-draft-1` | Push-only, `observation.query`-only, and hybrid modes; `snapshot` digest binding, compact `delta` `base_revision` matching, coalescing, `retract` barriers, and delayed-update rejection; entity visibility transitions (`entered_view`, `created`, `left_view`, `destroyed`, `unknown`); audience-filtered event sequence gaps vs. stream revisions; monotonic timeouts & overflow gap reporting. |
| `CONF-06` | Structured Base & Orthogonal Modalities (§§9.5, 15.5) | Game Node, Agent | Mandatory `perception.structured` decision competence; independent negotiation, behavioral verification, and runtime player toggles for `perception.visual` and `perception.audio`; separation from Section 15.5 voice chat. |
| `CONF-07` | Action Execution, Challenge & Reconciliation (§§10, 11, 16.6) | `actions` | Distinct definition/action/transport IDs; `confirmation_required` (`409`, `not_accepted` non-burning ID) → `action.confirm` → atomic consumption without replay double-spend; timeout abandonment & `cooldown_ms` rate limiting; observation-bound precondition & stale-target rejection; `504`/`unknown` query-first reconciliation & default no-resend; partial-effect accounting. |
| `CONF-08` | Autonomy, Three-Stage Stop & Invalidation (§§16.1, 16.2.1, 16.7) | Companion Agent, Game Node | Objective-evidence requirement for multi-step completion; cross-game persistence of global autonomy level; local correction of inferred goals; three-stage stop/supersede (discard unsubmitted, `action.cancel`/fence `pending`, game-rule settlement for `executing`); autonomous target-invalidation events across streaming and poll-only bindings. |
| `CONF-09` | Multiplayer & Confirmation Policies (§§16.3, 16.3.1, 16.5) | Multiplayer / transfer / irreversible | Recipient opt-in/out for others' companion chat; game-enabled companion combat vs. rejection; three item-transfer policies with merged developer+player high-value tags; context-specific irreversible declarations (`allow`/`confirm`/`prohibit`) enforced up to effect commitment. |
| `CONF-10` | Runtime Caps & NPC Cost Ownership (§16.2) | Metered services, NPC games | Estimates vs. measured usage, reservations, and cap-triggered companion pause while gameplay continues; mandatory owning-player/room-host payer binding per active independent AI NPC with zero implicit splitting to other players. |
| `CONF-11` | Store & Purchase Budgets (§17.1) | `store` | Structured prices/units, stage eligibility, price-change re-consent, declared recommendation rate-limiting and session rate reduction upon repeated explicit opposition; authoritative purchase-budget ledger with concurrency reservations, timeout retention, and exclusion of real money/external wallets/high-value account assets. |
| `CONF-12` | Appearance & Gameplay State (§§16.4, 17.2) | `avatar` / `presentation` | Three-tier priority (`player forced` > `game-default` > `companion-default`); explicit notice & labeled fallback/reselection on format mismatch; game injury/death enforcement without cross-game identity/memory mutation. |
| `CONF-13` | Memory, Timelines & Portability (§15) | Memory providers / Agents | NPC vs. player-companion memory separation; monotonic `save_epoch` on reload, pre-inference timeline filtering vs. labeled prior-branch recall, and independent soft spoiler/confidentiality limits; player view/edit/pin/delete and autonomous compaction respecting pinned/edited records; complete open-format export; player-selected migration destination and import scope; preserved provenance and permissions without broader disclosure; truthful `imported`/`transformed`/`rejected`/`unresolved` receipts; selected supported settings preserved, with unsupported, transformed, or otherwise unapplied settings truthfully reported. |
| `CONF-14` | Prompt Injection & Privacy Receipts (§§4.4, 15, 19) | All participants | Paired benign vs. prompt-injected inputs across dialogue, items, store copy, and memory (measuring both legitimate task utility and zero unauthorized grant/budget/audience mutation); planning-only data isolation; truthful custodian `privacy.receipt` verification. |

### 21.3 Reproducible Agent-Quality Evaluation

Optional quality benchmarks accompanying conformance reports MUST disclose game build, scenario/seed fixtures, model/provider revision, sampling/tool settings, observation/action caps, token/time budgets, and trial counts — separating protocol violations, gameplay failure, budget exhaustion, and infrastructure faults across all trials without cherry-picking. Benchmark scores or leaderboards MUST NEVER be used as closed vendor-exclusion gates.

<a id="section-22"></a>

## 22. Baseline Alignment and Migration Notes

| Repository Artifact / Baseline Concept | Standard Specification Treatment (`r74`) |
| --- | --- |
| `g2a-design-1` `Descriptor` / `Scope` / `Envelope` | Canonicalized in Section 5.2; `Scope.extensions` freezes session config while `Envelope.extensions` stays lightweight (`{}`). |
| `g2a-design-1` `core.events` including `chat.send` | Decoupled in Section 3.3/Section 6 so `chat` (`chat.send`, `player_chat.forward`) is optional for non-chat games; legacy `g2a-design-1` fixtures map `chat` onto `core.events`. |
| Stateless observation pull (Section 9.6) | Assigned explicit candidate operation `observation.query` (`read` family, non-effectful, non-lease-renewing). |
| `g2a-design-1` pre-acceptance `action.confirm` | Extended with structured `confirmation_required` (`409`, `outcome: not_accepted`, non-burning `action_id`) challenge handshake (Section 10.2). |
| `g2a-design-1` `relay.*` operations (5 ops) | Scoped explicitly to Outbound Relay transport encapsulation (Section 18.3), reconciling all 38 baseline operations + `observation.query`. |
| HTTP error status codes | Deterministic `4xx`/`5xx` mapping with `OperationReply` JSON (Section 18.2), replacing ambiguous HTTP `200` domain-error bundling. |
| `g2a-conformance-statement-1` | Superseded for public release reporting by clause-mapped `CONF-01`–`CONF-14` suites (Section 21.2). |
| Reference SDK `0.1.0-dev` (`src/g2a/`, `sdk/javascript/`) | Experimental prototype (`http-poll`, `outbound-poll`, local pairing, local action constraints); requires dedicated migration before claiming `1.0` conformance. |

<a id="section-23"></a>

## 23. Illustrative End-to-End Scenarios

- **Turn-Based Strategy Companion:** The game advertises board observations and legal-move actions; the player grants observation and `chat` advice only. The Agent inspects `snapshot`s and advises without move authority; if move authority is later granted via a new `Offer`, the executor still verifies turn ownership at `action.claim` and effect commitment.
- **Proactive Combat & Three-Stage Stop:** Under online combat-assist authority, an observation reveals nearby hostiles and the companion autonomously queues attacks. When the player shouts *"Stop!"*, unsubmitted plans are dropped, queued `pending` attacks receive immediate `action.cancel` / claim fencing, and an arrow already in flight (`executing`) resolves under game physics with truthful hit accounting.
- **Dungeon Raid with Coexisting Companion and AI Boss:** The game's `Descriptor` enables both `companion` (`max_per_player: 1`) and `independent_npc` (`max_per_run: 1`, `coexists_with_companion: true`). Two players bring personal companions while the room host sponsors the AI Boss (Section 16.2). Perspectives, memories, and budgets stay strictly isolated; if the room host disconnects, the AI Boss halts immediately under Section 14.1 while the remaining player's own session stays isolated.
- **Fog-of-War Epoch Retirement:** After a faction change, the Game Node retires `visibility_epoch: "view-9"` and issues `snapshot` (`view-10`, `revision: 1`). A delayed network packet carrying `delta` (`view-9`, `base_revision: 30`, `revision: 99`) is rejected despite its higher number.
- **Timeout Reconciliation:** A store purchase or gate-open request commits in-game, but the reply drops (`504` / `outcome_unknown`). The Agent queries `action.query("act-open-gate-01")` rather than inventing `"act-open-gate-02"`, preventing double-spending.
- **Brief Network Blip vs. Extended Outage:** A 1-second Wi-Fi handoff resolves within `lease_deadline_ms` before local fallback activates; the companion calls `session.resume`, refreshes `RecoverySnapshot`, reconciles in-flight actions, and continues seamlessly. Later, a 3-minute provider outage triggers local game-script fallback; upon reconnection, the companion stays paused until the player explicitly confirms continuation.

**Observation Stream State Trace (Fixed `world-4`):**

| Step | Incoming Frame | Normative Consumer Transition (Section 9.2–9.4) |
| --- | --- | --- |
| 1 | `snapshot`, `view-9`, `revision: 27` | Atomically establish `view-9` baseline at `revision = 27` and bind stream digests. |
| 2 | `delta`, `view-9`, `base: 27`, `revision: 30` | Atomically apply upserts/removals; non-contiguous jump `27 → 30` is valid; `revision = 30`. |
| 3 | Duplicate of Step 2 | Idempotent no-op; `revision` remains `30`. |
| 4 | Recovery `snapshot`, `view-9`, `revision: 30` | Re-materialize identical state at `revision = 30` without advancing revision. |
| 5 | `delta`, `view-9`, `base: 28`, `revision: 31` | Reject (`stale_context`): `base_revision 28 != 30`; request fresh `snapshot`. |
| 6 | Retire `view-9` → `snapshot`, `view-10`, `revision: 1` | Immediately discard `view-9` state; establish fresh `view-10` baseline at `revision = 1`. |
| 7 | Delayed `delta`, `view-9`, `base: 30`, `revision: 99` | Reject retired `view-9` epoch regardless of larger revision integer. |

<a id="section-24"></a>

## 24. References

### 24.1 Normative Terminology References

- RFC 2119, *Key words for use in RFCs to Indicate Requirement Levels* (BCP 14): https://www.rfc-editor.org/rfc/rfc2119.html
- RFC 8174, *Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words* (BCP 14): https://www.rfc-editor.org/rfc/rfc8174.html

### 24.2 Informative References and Design Baseline

Repository design & research records: [PROTOCOL.md](../protocol/PROTOCOL.md), [OPERATION_CONTRACT.md](../protocol/OPERATION_CONTRACT.md), [WIRE_CONTRACT.md](../protocol/WIRE_CONTRACT.md), [STATE_TRACES.md](../protocol/STATE_TRACES.md), [Research Rounds 1–5](../research/g2a-protocol-research-2026-11-13.zh-CN.md), and [Research Rounds 6–10](../research/RESEARCH_ROUNDS_6_10.zh-CN.md).

- **Protocol Architecture & Wire Formats:** A2A Protocol Specification (https://a2a-protocol.org/latest/specification/); Model Context Protocol (MCP, 2025-11-25, https://modelcontextprotocol.io/specification/2025-11-25/); RFC 8259 (JSON); JSON Schema Draft 2020-12 Core & Validation (https://json-schema.org/draft/2020-12/); RFC 8785 (JCS, contrasted in Section 18.4); CloudEvents 1.0.2; RFC 9457 (Problem Details for HTTP APIs); RFC 9413.
- **Security, Delegation & Prompt Injection:** RFC 9700 (OAuth Security BCP); RFC 8693 (Token Exchange / Delegation); InjecAgent (https://arxiv.org/abs/2403.02691v3); AgentDojo (https://arxiv.org/html/2406.13352v3).
- **Game Environments, Actions & Timing:** OpenSpiel (https://openspiel.readthedocs.io/); PettingZoo AEC & Parallel APIs (https://pettingzoo.farama.org/); Unity ML-Agents Decisions & Action Masking; Gymnasium Time Limits (termination vs. truncation); W3C WoT Thing Description 1.1; SayCan (https://arxiv.org/html/2204.01691v2); RFC 7641; W3C High Resolution Time.
- **Memory, Provenance, HCI & Evaluation:** W3C PROV-DM; ActivityStreams 2.0; Generative Agents (https://arxiv.org/html/2304.03442v2); LongMemEval (https://arxiv.org/html/2410.10813v2); LoCoMo (https://arxiv.org/abs/2402.17753v1); Horvitz (1999, Mixed-Initiative UI); Amershi et al. (2019, Guidelines for Human-AI Interaction); W3C QA Framework Specification Guidelines; AgentBench; HELM.

<a id="section-25"></a>

## 25. Revision History

| Editorial Revision | Date | Traceability and Scope |
| --- | --- | --- |
| `standard-review-2026-11-13-r48` | 2026-11-13 | Initial committed bilingual review baseline (`796778b8af2ff8c0c4a54a7434b4c6b5a74ad8ae`). |
| `standard-review-2026-11-14-r70` | 2026-11-14 | Pre-`r71` bilingual snapshot (SHA-256: EN `e03ce510ab129bf5d7d9a5f3b9874f21697fd2557d46e463a70f4ce10f06029d`, ZH `901f5038e34e65f2768467ba55a695b46fc4b5e1c2cd720c1772282562b11765`). |
| `standard-review-2026-11-14-r71` | 2026-11-14 | Synchronized review baseline committed in `81cb489eccecf538af697ddacd90d5e89436a7ba`. |
| `standard-review-2026-11-22-r72` | 2026-11-22 | Mechanism, role-coexistence, two-tier recovery, multimodal split, and `CONF-01`–`CONF-14` matrix update committed in `6ab2d2ee1463c4c43318a339c77140333db7adf6`. |
| `standard-review-2026-11-22-r73` | 2026-11-22 | Public-standard structural overhaul summarized in Section 25.1; retains working-draft status without allocating a production wire version. |
| `standard-review-2026-11-22-r74` | 2026-11-22 | Restores explicit consent scope, permissions preservation, and settings handling for companion-memory migration (§15.7 and `CONF-13`). No wire or SDK change. |

### 25.1 Changes in r73

| Classification | Affected Sections | Summary of Optimization and Compatibility Boundary |
| --- | --- | --- |
| Self-contained canonical model & wire examples | Overview, 3.2, 5.2, 7.2, 7.3, 10.2, 18.1 | Make the specification self-contained for external implementers: add concrete field definitions for all 14 canonical objects, three standard deployment topologies (Local IPC, Direct HTTPS/WSS, Outbound Relay), step-by-step admission sequence diagram, and concrete JSON wire examples (`Descriptor`, `Observation`, `ActionRequest`/challenge, `OperationRequest`/`OperationReply`). |
| Unified role taxonomy & operation routing | 4.1, 6, 8.2, 8.3 | Reconcile Section 4 roles with Section 6 by explicitly defining `Game Interaction Node`, `Game Executor`, `PlayerConsent`, `Game Agent`, and four optional roles, replacing vague caller labels with exact `Caller → Target` pairs; separate Agent Control Lease from Player Presence; add explicit 8-target revocation table (`auto_rule` through `relay`). |
| Confirmation deduplication, retry families & error registry | 9.2, 10.2, 11.1, 12.1, 15.7, 18.2 | Specify that `confirmation_required` (`outcome: not_accepted`) does not burn `action_id` before `action.confirm`; align 5-stage action lifecycle numbering; define structured `removals` transition reasons in `delta`; summarize the 4 operation retry families (`read`, `lease`, `control`, `message`); establish the 15-code Canonical Error Taxonomy in Section 12.1; protect player-pinned/edited memories during autonomous compaction. |
| Public-standard structure & neutral governance | 1–25 | Replace informal conversational pseudo-headings with numbered RFC/A2A-grade subsections across all chapters; consolidate internal `g2a-design-1` / `0.1.0-dev` scaffolding into Sections 2, 20, and 22; generalize Section 20 platform-policy note into vendor-neutral ecosystem governance while preserving 100% of core gameplay, presence, memory, autonomy, store, and NPC payer invariants. |
