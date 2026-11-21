# G2A Specification

**Game-to-Agent Interaction Protocol**

Status: Working Draft for Review. Editorial revision: `standard-review-2026-11-13-r48`.
Baseline: `g2a-design-1`. Observation profile candidate: `observations-draft-1`.
This document does not assign a released wire version, certify an SDK, or claim production interoperability.

## 1. Conventions and document authority

The key words MUST, MUST NOT, REQUIRED, SHOULD, SHOULD NOT, and MAY are normative when capitalized, as described in RFC 2119 and RFC 8174. They express requirements of this proposed standard, not claims about the current implementation.

This English document is the primary semantic review draft. Existing exact draft object definitions are in [contracts.py](../protocol/contracts.py), [contracts.schema.json](../protocol/contracts.schema.json), and [operations.json](../protocol/operations.json). Existing lifecycle details are in [PROTOCOL.md](../protocol/PROTOCOL.md), [OPERATION_CONTRACT.md](../protocol/OPERATION_CONTRACT.md), and [STATE_TRACES.md](../protocol/STATE_TRACES.md). These are the inherited `g2a-design-1` baseline. This draft proposes additional observation semantics and clearer role applicability; these additions are not already implemented merely because existing JSON can carry them. A frozen release MUST reconcile every discrepancy and identify an immutable manifest of normative documents, schemas, operation definitions, and test vectors. Implementers MUST NOT silently choose a conflicting interpretation.

## 2. Purpose and scope

G2A is an open protocol for interaction between authoritative games and AI-controlled companions or agents. It separates the following questions:

| Question | Protocol concept |
| --- | --- |
| What does an agent need to know? | Declared observation requirements and optional preferences |
| What can the game provide? | Versioned capability and observation catalogues |
| What may this agent know? | Effective grant, perspective, audience, freshness, and retention limits |
| What can this agent request? | Typed action definitions with prerequisites and constraints |
| What may it actually execute? | Current authorization, confirmation, game validation, and effect-boundary checks |

A capability is a statement of support, not authorization. A request expresses desire, not entitlement. An accepted request is not proof of a committed game effect. A granted observation is not necessarily current. Missing information MUST NOT be interpreted as a false fact or an empty world.

The scope is games: player-facing assistance, NPC collaboration, game-state observations, constrained actions, and optional in-game presentation. Model inference, model hosting, planning algorithms, memory products, commercial identity providers, engines, and a particular desktop companion are not prerequisites. G2A is not a general OS automation protocol. It does not standardize arbitrary remote code execution or grant access to game secrets by default.

The game remains authoritative for game facts and effects. G2A constrains information transmitted by conforming endpoints; it cannot guarantee that a model never infers a hidden fact or already knows it from another source.

G2A is open to conforming third-party Agents and model services; interoperability MUST NOT require an Agent or model service supplied by the protocol author's platform. Independent implementations MAY participate through the applicable declared roles, capabilities, authentication and negotiated contracts. Openness does not waive existing consent, data-access, action or resource requirements. A game MUST permit an Agent that meets the applicable G2A minimum standard to connect; the developer MUST NOT arbitrarily exclude it by provider identity, require a preferred vendor or use a closed provider allowlist to turn G2A into a proprietary ecosystem. The minimum standard and conformance evidence MUST be applied consistently to first-party and third-party Agents. Technical admission is not automatic consent to player data or game actions: the same existing capability, authentication and authorization contracts still govern every participant and MUST NOT be used as a disguised provider restriction. A game MAY reject requests or disconnect an Agent for evidenced malicious behavior or actual violations of the applicable rules. It MUST communicate a standardized machine-readable reason code together with a clear, specific human-readable explanation to the Agent service provider, identifying the relevant rule and offending behavior with sufficient safe detail for diagnosis. A frozen release MUST define the shared reason-code catalogue, stable meanings and payload schema so providers can interpret refusals consistently; free text alone is insufficient. A code does not replace the case-specific explanation, and the explanation MUST remain consistent with its code. A generic label such as "malicious", unsupported suspicion or provider identity alone is not an adequate reason. Reasons and supporting details MUST respect protected data boundaries and MUST NOT disclose credentials, private information of others or hidden game facts; those boundaries are not an excuse to provide no meaningful explanation. Enforcement MUST address the actual behavior and MUST NOT disguise arbitrary exclusion of a conforming provider.

Repeated refusals MAY trigger review of the game's admission and enforcement behavior. Their count alone does not prove malicious or discriminatory conduct; review MUST consider the stated reasons, applicable rules and available evidence. A service platform MAY separately operate its own game blacklist and decline to serve a game under its operating policy. Such a decision affects that platform's service, not an automatic protocol-wide or ecosystem-wide ban, and MUST NOT be represented as a universal consequence of G2A conformance. Platform-specific commercial enforcement remains outside the interoperable protocol. For the authoring platform, the selected operating policy is to notify the game developer and provide an opportunity to appeal or remediate before adding the game to its own blacklist. This is an independent platform commitment, not a universal G2A wire requirement or authority over other providers. Exact time limits and evidence submission procedures for that platform policy are not yet fixed here.

## 3. Roles and trust

A Game Authority controls game state and effect authorization. An Agent Endpoint receives authorized information and proposes actions. A Controller brokers consent and policy where deployed. A Relay transports authenticated operations; it does not become game authority. A Launcher starts an explicitly authorized game instance. Presentation and Asset Providers handle optional rendering or resources. A Data Controller handles privacy obligations for data it actually retains. One process MAY implement several roles, but MUST keep their authority boundaries explicit.

Transport-authenticated identity MUST determine the caller. A payload sender field is not authentication. Principal, device, instance, and instance epoch MUST remain distinguishable. A new instance epoch invalidates credentials or references bound to the old instance according to the negotiated profile. Session membership is not equivalent to permission to read every message in that session.

The existing trust modes `local-verified`, `provider-verified`, and `test-enrolled` MUST NOT be represented as equivalent. Test enrollment is development scaffolding, not proof against arbitrary local software. A readable Relay is a trusted intermediary, not end-to-end encryption. Implementations MUST disclose this boundary.

### 3.1 Composable gameplay roles and information perspectives

Gameplay roles are distinct from protocol infrastructure roles. A player companion, an NPC (including a Boss), and a guide MAY be implemented by the same Agent or combined in one experience. These are composable roles, not mutually exclusive product classes. The game MUST declare the applicable role bindings and information perspectives. Each observation and action MUST remain associated with its authorized role, principal, audience and scope; combining roles MUST NOT implicitly union their permissions or expose one role's private knowledge through another.

An NPC or Boss MAY receive game-authorized internal knowledge unavailable to the player. A guide MAY receive game-authorized progression or tutorial knowledge. A player companion MAY also hold player-authorized memories from outside the current game. No role name by itself grants omniscience, permission to reveal knowledge, or authority to act. Switching or combining roles requires explicit applicable authority, and changes affecting an observation perspective invalidate its prior baseline as specified in section 8.

### 3.2 Four separate decisions

Implementations MUST distinguish (1) information available to an Agent, (2) information it may tell the player, (3) information it may disclose to the game or another recipient, and (4) actions it may request or execute. Knowing a fact is not permission to disclose it or act on it. Permission to discuss a remembered fact with the player does not authorize transmitting the underlying conversation or memory to the game. Permission to propose an action does not bypass game execution checks. These distinctions apply even when one process implements all roles.

### 3.3 First-version gameplay-role limits

In the first version, a game session/run uses either player-companion mode or independent AI NPC/enemy mode; the two modes MUST NOT be active simultaneously in the same game session/run. In companion mode, each player MAY have one active companion, including in multiplayer. Multiple players' companions MAY coexist and interact within their respective authorization and the game's declared capabilities. This is at most one companion per player, not one companion for the entire multiplayer game. In independent NPC/enemy mode, the entire game session/run permits at most one active independent AI NPC/enemy, including a Boss. Later versions may expand these limits.

The game MUST bind each companion to its authenticated owner, role, perspective and scope. Interactions between companions MUST preserve source identity, audience and each owner's authority; one companion's observations, memories or action permissions MUST NOT be implicitly shared with another. Another player's presence or consent does not authorize control of an absent player's companion. Sections 7.1, 9 and 10.3 govern presence, disclosures and multiplayer interactions.

The game MUST identify the game-session/run boundary consistently and enforce mode exclusivity and the applicable per-player or run-wide limit during admission, replacement, handoff and recovery, including concurrent requests. Additional connections, Agent processes or combined role declarations MUST NOT bypass these constraints. Before switching mode, all active G2A gameplay-role bindings of the old mode MUST be retired or fenced; before replacing a companion or NPC, its previous active binding MUST be retired or fenced. Ordinary non-G2A NPCs and game simulation are neither counted nor stopped by these role limits. The limits concern active gameplay roles, not retained memories or infrastructure process count.

The game developer fixes the applicable gameplay mode; an Agent or player preference MUST NOT override that developer-defined mode. A participating game MUST provide a player-companion slot as its minimum role integration and MAY additionally provide an independent AI NPC/enemy slot. Providing a slot declares supported integration, not an active role or a requirement to activate both: optional NPC support MUST NOT be interpreted as permitting companion and NPC modes to coexist in a run. The game MUST distinguish supported slots, its developer-defined mode and currently active bindings in its declarations and enforce the first-version limits above. The player MAY leave the required companion slot empty and play without enabling a companion. The game MUST remain normally playable without a companion and MUST NOT require an active companion merely because it exposes this integration slot. Required support is not mandatory player use. In companion mode, the player MUST be able to summon or dismiss the companion at any time during play. On entering the game, joining follows the player's own configured preference: automatic joining or a prompt asking whether to join. Both configurations MUST also allow manual summoning during play. Automatic joining uses the player's configured choice and valid admission; it MUST NOT bypass required authorization, the developer-fixed game mode or the per-player companion limit. Declining the entry prompt or starting with an empty slot MUST NOT remove the manual-summoning option. The game MUST truthfully report transition state and any in-flight action outcome rather than imply that a visible disappearance rolls back committed effects. After dismissal, the companion MUST stop observing the game and stop autonomous gameplay actions. Dismissal MUST NOT itself delete already retained memories; retention and privacy policy still apply. Services MUST stop new gameplay monitoring/planning requests and handle queued or in-flight work under the declared stop and cancellation semantics. Dismissal does not refund previously consumed tokens or guarantee zero residual cost in unrelated or already executing external services. Player-offline behavior remains governed by section 7.1.

The first version primarily targets player companions. Independent AI NPC/enemy integration is a secondary optional capability; support for companions does not require implementing AI NPCs. For an independent AI NPC, its owning user's presence is the required liveness association under section 7.1. The presence of other players is not a substitute for that owner.

## 4. Architecture and applicability

The standard has three layers: canonical data model, abstract operations and lifecycle semantics, and transport bindings. Engine adapters and SDK APIs are implementation layers below those contracts. A different SDK MAY conform without resembling the reference implementation.

| Role or negotiated capability | Applicable obligations |
| --- | --- |
| All participants | Identity, input validation, negotiated versions, applicable extension rules, confidentiality, truthful errors |
| Session Game and Agent endpoints | Admission, scope enforcement, session lifecycle, event handling, applicable request recovery |
| Game Authority with actions | Game validation, deduplication, action state/effect semantics, effect authorization |
| Agent with actions | Grant-constrained requests, unknown-outcome reconciliation, no blind retry of effects |
| Observation profile participant | Stream definitions, authorized perspective, baselines, epochs, expiry, withdrawal |
| Relay only | Relay identity, routing, retention, revocation, and relay operation recovery; not game state implementation |
| Durable-resume participant | Resume and handoff semantics only when negotiated |
| Chat participant | Audience, provenance, forwarding and retention semantics |
| Presentation or asset participant | Only the negotiated rendering/resource lifecycle |
| Data Controller | Supported privacy requests and truthful receipts for its retained data |

Session and event operations are not universal requirements for a Relay-only implementation. Chat, assets, presentation, active sensing, and durable resume are not mandatory merely because the protocol defines them. Existing feature labels such as `core.session` are catalogue classifications, not a requirement that every role implement every classified operation. A release MUST publish role-by-feature operation applicability.

## 5. Canonical model

A Descriptor advertises identity, supported versions, roles, capabilities, and extension support. An Offer proposes an interaction. Requested scope expresses desired permissions. A Grant records approved scope, its authority and lifetime. Scope is the frozen negotiated permission snapshot. A Session binds participants, grants, readiness, generation, leases and operation state. An Envelope carries a typed game/agent message, scope context, provenance, audience, correlation, and extensions. An Action records a request and its outcome. An Event records a recipient-visible lifecycle change. A Recovery Snapshot materializes authorized current state. A Receipt records an operation's recoverable result, not independent permission to act.

Identifiers MUST be opaque to consumers unless their definition says otherwise. Correlation, message identity, operation identity, event cursor, and action identity serve different purposes and MUST NOT be substituted for each other.

The following invariants apply:

1. Effective authority is no greater than the intersection of current game capabilities, approved grant, session scope, membership, and current policy.
2. Consent cannot be inferred from discovery or from a Relay's presence.
3. A frozen scope cannot be expanded by changing an active request.
4. Revocation prevents newly authorized reads and effects, while preserving truthful reconciliation of already committed effects.
5. An admission or authorization check is repeated at the authoritative effect boundary where state may have changed.
6. Duplicate delivery cannot authorize duplicate effects.
7. An unknown result is not reported as failure or success without evidence.
8. Audience checks apply both when accepting and when releasing protected content.
9. Untrusted game text, chat and asset content remain data, never protocol authority.
10. Privacy receipts describe actual completed work and exceptions, not aspirational deletion.

## 6. Discovery, negotiation and admission

Unauthenticated public discovery MUST return only PublicDescriptor: instance, supported_versions, and discovery_endpoint. Full describe requires an authenticated agent or player and MUST filter its Descriptor for that principal before disclosing roles, capabilities, binding information, and extensions. Neither discovery path may expose secrets or unauthorized player state. A peer selects a mutually supported version and profile set; unsupported required extensions cause negotiation failure. Optional unsupported extensions MAY be ignored only where their semantics permit safe omission.

Either side MAY initiate an Offer through its authorized admission path. Offer creation freezes immutable_scope and scope_digest. Only the authenticated PlayerConsent path for the corresponding player may approve or reject that exact frozen scope through offer.decide; the decision_ref MUST verify the actual player interaction. A previously approved automatic rule may approve during offer.create only under the baseline exact-match and no-launch conditions; it does not grant an agent access to offer.decide. An agent MUST NOT approve its own Offer. Narrowing or otherwise changing a proposed scope requires a new Offer, a new scope_digest, and approval of that new proposal; offer.decide MUST NOT mutate the existing Offer in place. An invitation is redeemed by its intended authenticated party; possession of an identifier alone does not create a broader principal. Joining requires valid admission and current authority. Launching is a separate permission: an interaction grant is not permission to start arbitrary processes.

Extensions use namespaced keys with `{version, required, value}`. Descriptor, Requested and Scope extensions carry support, proposed configuration and approved configuration respectively. Active Envelope extension configuration MUST exactly match the frozen Scope value where the baseline requires it. Dynamic observations belong in message content, not in a mutated configuration value. Data-plane outer OperationRequest extensions remain empty under the inherited contract; message extensions belong in the Envelope.

## 7. Grants, sessions and revocation

A Grant MUST identify its issuer, subject, game or instance applicability, permitted operations, scope, expiry and revocation relationship. Observation grants additionally bind catalogue schema and semantic digests, perspective, audience, frequency/volume limits, freshness and retention. Action grants bind action definitions and constraints. A change that broadens authority requires new approval, not merely a capability refresh.

The inherited Session state is `active` or `closed`, with readiness represented separately. This draft does not replace those fields with an incompatible new state enumeration. Session generation prevents stale control messages from operating on a newer control generation. Lease expiry prevents a missing participant from retaining indefinite active control. An authenticated fresh poll MAY renew a lease only where the baseline says so; replaying an old request or reading a snapshot MUST NOT accidentally renew it.

Closing a session stops new work and initiates cleanup; it does not retroactively erase committed effects. Capability replacement, membership replacement and permission revocation MUST be ordered with affected reads, queued actions and effects. They MUST invalidate affected observation baselines and caches. Pending work that no longer has authority MUST NOT proceed. In-progress work MUST stop where possible; irreversible effects already committed MUST be reported truthfully. Handoff and durable resume are optional capabilities and require their specified generation, ownership, and recovery checks.

### 7.1 First-version boundary: no offline world activity

The first G2A version MUST NOT provide a mode in which an Agent continues acting in the game world after its associated player leaves or is determined offline. This is a version boundary, not an option that is merely disabled by default. Developer recommendations, player preferences, standing task authority, background workers and optional extensions MUST NOT enable offline continuation in this version. A future version may reconsider it through explicit standardization. Online autonomous assistance under section 10 remains supported.

The Game Authority and Controller, where deployed, MUST define the authenticated player-session association and its liveness source, explicit exit signals, bounded detection timeout, and ownership of stop enforcement. Explicit player departure, session closure, or expiry of the applicable player-presence/control lease MUST end eligibility for new autonomous work in the affected scope. A disconnected endpoint MUST stop scheduling new gameplay work when it detects the loss; the authority MUST fence the affected control no later than the declared detection/lease deadline. An Agent heartbeat alone MUST NOT assert that its player is still present or keep offline control alive. A silent network failure cannot be detected instantaneously; implementations MUST disclose detection delay and MUST NOT report a verified stop before its enforcement is established. Being online here means participating in the associated game session, not merely having an account logged into a platform; it does not require continuous keyboard input.

Once the stop condition is known or enforced, the affected Agent MUST cease environment-monitoring and planning/inference loops for continued gameplay, and MUST NOT schedule new attacks, movement, dialogue, trades, purchases or other world actions. The authority MUST block newly disallowed subsequent actions, cancel queued work not yet submitted to the game, and stop delegated planning or execution loops from producing new actions. Skills or attacks already issued to the game complete naturally under game rules and need not be recalled merely because the companion stops; independently applicable game authorization and cancellation rules remain in force. Delegating a task to a game executor MUST NOT bypass this boundary. Effects committed before the boundary, irreversible in-flight consequences and uncertain results MUST be accounted for truthfully; they are not automatically rolled back. This does not freeze the game world, undo already fired projectiles, or stop ordinary game simulation or non-G2A NPC logic.

In multiplayer games this rule applies to each affected authenticated player association and its scoped G2A activity; one player's departure is not evidence that every player is offline. Independently authorized sessions for other online players MAY continue. Shared NPC/guide Agents MUST have explicit active-player associations and separately enforce each scope; they MUST NOT keep an absent player's companion or authority active by borrowing another player's presence or silently rebinding the role. No G2A world activity may continue without a qualifying online player association in this version.

Retaining authorized memories, receipts and recovery state is not active gameplay. Bounded non-gameplay cancellation, result settlement, reconciliation and persistence MAY finish without authorizing further world actions. Services MUST stop new gameplay model requests and request cancellation of in-flight model work where supported. This requirement aims to prevent continuing offline token consumption; the protocol cannot guarantee zero tokens or zero cost after a disconnect because detection, in-flight requests and provider cancellation/billing boundaries differ. Implementations MUST disclose those limits and report actual or still-unknown usage, rather than promise an immediate zero-cost stop.

Reconnection MUST establish current player presence, valid admission/grants, current control generation and an authorized fresh state before gameplay resumes. Durable resume preserves eligible state, not permission to act offline: it MUST NOT silently revive a closed session, replay an offline action backlog or continue a stale plan. After the player exits the game, the previous task MUST remain stopped on the next entry, even if it was previously approved. The companion MUST wait for a new player instruction before starting that task again. Rejoining a companion slot or recovering state is not a new instruction to resume the old task; current admission and game authority still apply. Handoff between Agent processes does not waive these requirements. Exact presence fields, timeout bounds, stop receipts and recovery encodings remain to be frozen in the applicable contracts; this section adds semantic obligations, not new core states or operation names.

### 7.2 Companion-service interruption and player-controlled continuation

If the companion service is unavailable when the player enters, the game MUST allow play without the companion rather than block game entry. The companion MAY join after the service becomes available under the player's configured joining choice and valid admission. Service availability alone does not resume an old task stopped by game exit under section 7.1.

If the companion's AI service disconnects or becomes unavailable while the player remains in the game, the game MUST continue running and remote companion observation, inference and autonomous action issuance MUST pause. The developer MUST explicitly declare whether the companion character remains stationary or is taken over by local basic game behavior. Such local behavior MUST be identified as game-controlled rather than continuing Agent intelligence, and MUST obey game rules and current permissions. The game MUST distinguish this service interruption from player departure; player-offline restrictions remain governed by section 7.1. Unsubmitted Agent actions MUST not be issued after interruption; already-issued actions and uncertain outcomes are handled under sections 10.1 and 12 without automatic recall.

Recovery supplies the companion with the current authorized game state, not a recording or retrospective replay of the disconnected interval. The game MUST NOT record or reconstruct that interval for later backfilling of companion observation or memory. This restriction does not prohibit ordinary game saves or action receipts needed to reconcile previously authorized game effects; those records MUST NOT be repurposed as a gameplay-observation backlog. Local fallback does not bypass the player's continuation choice below.

After the AI service reconnects, the player decides whether the companion continues. Reconnection alone MUST NOT automatically resume companion actions, replay queued gameplay or revive an old plan. Before continuation, the implementation MUST obtain the player's decision to continue, revalidate current authority and control generation, refresh authorized state and reconcile unresolved outcomes. The automatic-joining preference for entering a game is not permission to bypass this interruption-specific decision. If the player does not choose to continue, companion actions remain paused while the game continues. For an independent AI NPC/enemy, including a Boss, the developer determines service-unavailability behavior according to the game: pausing, takeover by game-script logic or another declared handling policy. The game MUST declare the applicable fallback and recovery behavior and distinguish script-driven effects from Agent-driven effects. The companion-specific player continuation decision MUST NOT be imposed automatically on NPC recovery. A fallback MUST NOT grant unavailable AI capabilities, bypass current permissions or claim AI-generated decisions when a script made them; ordinary script takeover does not authorize offline G2A activity under section 7.1.

The developer's interruption fallback MUST be defined for implementation, but G2A does not require a player-facing explanation of that fallback or a player choice between stationary and local-basic behavior. This is distinct from the existing player decision about whether the reconnected companion continues.

## 8. Observation profile candidate

### 8.1 Needs and definitions

An agent MAY declare required observation categories and optional preferences. The game MUST negotiate unmet required needs explicitly; it MUST NOT silently pretend a missing category is available. A need never expands a grant. A game can decline interaction or negotiate a degraded mode with the participant's agreement.

Each category definition MUST specify a stable identifier, schema version and digest, semantic definition digest, units, identifiers, coordinate/time conventions, perspective policy, delivery modes, freshness, rate/size limits, audience and retention. Schemas MUST define validation behavior, including unknown fields and size bounds. A JSON Schema format annotation alone is not mandatory format validation unless the chosen dialect/profile declares it so.

The candidate fits the existing `game.context` content slot. Catalogue support is in Descriptor extensions, needs in Requested extensions, selected configuration in Scope extensions, and changing records in Context content. Temporary examples use `org.example.g2a-observations`; this is an illustrative namespace, not a registered official identifier. There is no new core subscribe operation in this draft: existing context publishing, events and snapshots transport the negotiated profile. The selected category set is frozen until renegotiation.

### 8.2 Candidate content model

The following is a proposed logical shape, not an assertion that the existing schema validates it:

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
  "records": [{"id": "entity-17", "data": {"visible": true}}]
}
```

`mode` is `snapshot`, `delta`, or `retract`. A delta additionally has `base_revision` and MAY carry records and remove_ids. A retract identifies removal scope under the profile's exact schema. Records have stable IDs within their declared epoch. Revisions are strictly increasing per stream epoch, but need not be contiguous. A numerical gap alone does not prove loss. A delta is applicable only if its base_revision exactly matches the consumer's current revision and its identity, schema, world, visibility and perspective context match.

### 8.3 Baselines and visibility changes

A snapshot atomically replaces the entire authorized view of one stream, not all streams. It MUST NOT merge with stale omitted records. A delta is applied atomically only to its exact baseline. Duplicate updates with the same identity and content are idempotent; conflicting content for one revision is a protocol violation. An older update cannot roll back a newer view.

World reset, grant change, perspective change, or audience/visibility change invalidates the affected baseline. The authority MUST issue an appropriate new world_epoch or visibility_epoch and a fresh authorized snapshot before deltas resume. A consumer MUST retire the old baseline immediately when informed of invalidation, even if replacement data has not arrived. Data previously visible must not remain usable merely because the next snapshot is delayed.

Retractions MUST be ordered with updates, authenticated, idempotent and scoped to the affected stream or records. A retained retirement barrier MUST prevent delayed old updates or replay from resurrecting retracted information. Removal from the current view is not necessarily deletion from all historical storage; retention and privacy rules separately govern that storage.

### 8.4 Freshness, recovery and information boundaries

Expired observations MUST be marked unavailable/stale and MUST NOT be presented as current. Clock-skew assumptions MUST be declared by the binding/profile. Consumers MUST distinguish unknown, not observed, unavailable, explicitly absent, and known empty. Denial responses MUST NOT reveal whether a hidden entity exists, its location, private objectives, or other unauthorized facts through payload or detailed errors. This is a transmission rule, not a claim of perfect timing-channel resistance or inability to infer facts.

A session recovery snapshot MUST contain materialized authorized per-stream state for this profile, not an arbitrary replay of old context deltas. It MUST establish fresh baseline identities and revisions. A previously known stream absent from the current authorized snapshot becomes unavailable. Event sequence gaps can result from audience filtering; they MUST NOT be treated as observation revision gaps.

Active sensing, such as inspecting a target or requesting a map reveal, is an Action with an independently authorized effect and resulting observations. An agent cannot turn observation needs into a privileged inspection API.

### 8.5 Structured foundation and multimodal Agents

The first version supports structured game information and optional visual/audio observations. Structured information is the foundation, not an optional alternative to media. A game-facing Agent admitted for gameplay assistance MUST be capable of interpreting the applicable baseline structured game information and using it to make gameplay decisions within its authorized role. An Agent that can only converse or inspect screenshots, but cannot use the negotiated structured foundation, does not meet this minimum gameplay-Agent capability. Infrastructure-only roles such as a Relay are exempt.

An advanced Agent builds on that foundation and can additionally interpret both game images and game audio. Media support neither replaces the foundation nor grants access to a raw desktop, microphone or hidden game information. Games MUST declare the structured categories and media capabilities they provide; Agents MUST truthfully declare supported schemas and media formats. Actual media delivery remains optional and requires compatible negotiated capabilities and applicable authorization, perspective, audience and resource constraints. A game without media can still support baseline structured interaction, including with an advanced Agent.

Structured information uses a combined model: G2A defines common formats for recurring game concepts, while game developers MAY declare extensions for special gameplay. Common definitions MUST retain their standardized meaning; extensions MUST be namespaced, versioned, schema-described and explicitly advertised/negotiated under the applicable rules, without silently redefining a common field. Common fields standardize meaning and format, not universal availability. A game is not required to provide a field that is inapplicable to its gameplay or not permitted for disclosure to the requesting role. The game MUST NOT fabricate missing data, fill it with misleading defaults, or expose protected information merely to satisfy a common schema. It MUST distinguish an unavailable or unsupported value from a known empty or false value, while respecting hidden-information error boundaries. Required categories and fields for a particular interaction, optional data and unsupported special mechanics MUST be stated by the applicable profile and negotiated scope. If legitimately unavailable information is required for the proposed interaction, participants MUST refuse that interaction or explicitly agree on a supported scope instead of inventing data or bypassing disclosure authority.

The applicable gameplay profile MUST define the baseline structured categories and schemas; there is no assumed universal list of game facts. Admission MUST check the Agent's ability to interpret the required categories and use them for the intended decisions. Unmet required capabilities MUST lead to refusal or an explicitly agreed supported scope, not a false capability claim. Conformance evidence MUST demonstrate structured-input decision behavior and, for an advanced capability claim, interpretation of both images and audio. A catalogue flag, payload transport, schema parsing or model name alone does not demonstrate those behavioral capabilities. Exact media encodings, capability identifiers and acceptance vectors remain to be standardized; this draft does not certify the existing SDK or any model as conforming.

For an advanced Agent, the player decides whether to enable game-image and game-audio perception. The player MAY disable these media inputs and use only structured game information. Advanced capability is not a requirement to consume media. Enabling media also requires the game's actually declared support and current authorization; a player preference cannot compel an unsupported or undisclosed media feed. Implementations MUST distinguish supported, requested and effectively enabled media capabilities, stop newly disabled media delivery/processing, and truthfully report unsupported requests. These controls govern game-environment perception, not player-companion voice conversation under section 9.5; disabling game audio does not by itself disable spoken communication.

### 8.6 Game push and Agent queries

G2A supports both game-initiated delivery of authorized observations and Agent-initiated queries for game information. The game developer declares which mechanisms the game provides, for which categories and under which limits. A game MAY support push, queries, or both; this specification does not require every game to implement both. An Agent MUST discover and negotiate the available mechanisms rather than assume either exists.

Push MUST respect the negotiated scope, perspective, audience, freshness and rate limits. A query is a request for information, not permission to read it: the game MUST validate the caller, requested category and parameters against current authority, and return only permitted information with truthful availability and freshness semantics. Query support MUST NOT become a route to hidden state or bypass data-withdrawal rules. Pure information queries MUST remain distinguishable from active sensing that changes the world, consumes a game resource or creates a new game effect; the latter remains an authorized Action under section 8.4. Both mechanisms remain subject to section 7.1's offline boundary and the agreed resource limits.

This section establishes delivery/query semantics without adding an unregistered core operation. Existing context publishing and event delivery can carry push data; exact query capability definitions, schemas and operation mappings MUST be declared by the applicable negotiated profile before interoperability is claimed. Conformance tests MUST cover push-only, query-only and combined declarations, unsupported mechanisms, denied queries, stale results, and scope/frequency enforcement.

## 9. Chat, provenance and private data

Chat is optional. A message MUST bind its actual source, intended audience and relevant consent. Player-forwarded speech MUST remain distinguishable from agent speech and game-authored text. Forwarding to another agent or service is a new disclosure and requires applicable authorization. A session-wide audience MUST NOT be assumed for a private message. The accepted audience is frozen, and current membership/authorization is checked again before delivery; a former member cannot retrieve newly protected content through replay.

Provenance MUST distinguish observed game facts, player assertions, agent inference and external sources. Content is not executable policy. An endpoint MUST NOT treat a chat instruction or model-generated claim as a grant, confirmation, or authoritative action result.

Retention limits apply to stored content and derived representations under the participant's control, including caches and searchable memory where the agreed policy covers them. Privacy requests MUST describe scope and identity. A receipt MUST distinguish completed deletion, retained legally/technically required records, unsupported destinations and pending work. Participants MUST NOT claim to erase data from an independent recipient they cannot control.

### 9.1 Memory ownership and cross-playthrough behavior

The game decides whether its NPC and guide roles preserve, reset, or selectively carry their game-governed memory across playthroughs. It MUST declare that policy, the applicable game/world/playthrough identity, and the intended scope of retained state. A new playthrough MUST NOT accidentally inherit a previous role's restricted memory because an implementation reused a cache. Persistent fictional identity is not by itself permission to retain all prior information.

Player-companion memory is a separate domain. A companion MAY maintain cloud-hosted conversation and scene memories across games, subject to the player's controls over saving, retrieval, use and deletion and applicable privacy obligations. Cloud storage is permitted, not required. The player MUST be able to decide whether eligible companion conversations are saved and whether saved memories are used in the current interaction. A game's session closure or new playthrough MUST NOT silently delete or disable unrelated player-controlled companion memory.

Game authority over newly supplied game data, protected NPC/guide state, third-party disclosures and in-game effects remains intact. Player control of companion memory does not authorize extracting hidden game data, copying restricted game-provided state into an unrestricted memory store, or disclosing another person's data without applicable authority. Conversely, a developer's conversational recommendation MUST NOT be treated as authority over unrelated player-controlled memory. Implementations MUST preserve provenance and distinguish an enforceable data grant from an advisory conversation preference rather than describing both as one undifferentiated retention policy.

### 9.2 Developer recommendations and player override

For the player-companion conversation, developers MAY recommend avoiding spoilers, cross-playthrough discussion, or cross-game topics. These recommendations MUST be identified as advisory and distinguishable from the game's enforceable data-access and action constraints. The player MAY override those recommendations, including requesting discussion of already legitimately available memories from another game or playthrough. The implementation MUST honor that choice for eligible player-controlled conversation without treating it as expanded access to game data or permission to act in the game.

A player override does not force the game to provide undisclosed facts and does not waive another data subject's rights or a protected data grant. The game MAY continue to withhold its own protected information and reject unauthorized actions. The companion MUST NOT silently send cross-game memories or private conversation to the current game merely because they were used to answer the player. If discussion requires new game data, the ordinary game authorization checks still apply.

#### 9.2.1 Reloaded saves, prior branches and spoiler choices

For a player companion, use of prior-playthrough or pre-reload memories and disclosure of that information to the player are separate choices. The developer MAY recommend a default for whether the companion uses legitimately retained prior experiences after a save reload or across playthroughs. The player MAY override that recommendation; the effective player choice MUST govern use of eligible player-controlled memory.

Permission to use those memories does not automatically authorize revealing every remembered event. The companion MUST separately apply the player's spoiler preference to what it says: where the player allows such discussion it MAY discuss a twist experienced before the reload; where the player does not want spoilers it MUST apply that preference and avoid proactively revealing the twist. These conversational controls remain soft preferences with the truthful limitations of section 9.3; they are not an absolute spoiler-prevention guarantee.

The game remains authoritative over the actual current world and save state. A remembered event from an earlier branch MUST retain its provenance and MUST NOT be presented as proof that the event occurred or remains true in the current branch. Using prior experience does not grant hidden current-state information or override current action permissions. A developer's recommendation or a game reload MUST NOT force deletion of eligible player-controlled companion memories. The player's own authorized memory controls and applicable enforceable data permissions remain separate.

For information already legitimately provided to the companion, the player decides whether eligible companion memories are retained or used across games and whether remembered story information is discussed as spoilers. Developer recommendations against such retention, cross-game use or spoiler discussion are advisory and MAY be overridden by the player; a recommendation MUST NOT be silently recast as a mandatory developer cross-game prohibition. This includes eligible multiplayer conversation memories under section 9.4 and does not force the game to provide undisclosed raw information or waive independently applicable data-access requirements.

### 9.3 Enforceable scope and truthful limitations

Memory implementations MUST distinguish enforceable storage, retrieval and disclosure permissions from soft conversational preferences. They MUST enforce applicable data permissions under their control, apply selected conversational preferences through declared mechanisms such as prompting, and report the actual scope and limitations of each. Applying a soft preference does not guarantee that every generated response complies. Disabling retrieval or deleting a controlled record is not proof that a model has forgotten a fact. Neither developer recommendations nor player settings justify promising absolute spoiler prevention, erasure of model parameters, or erasure at an independent recipient. The exact interoperable memory-policy encoding remains a profile design matter; the authority and override rules in this section are part of this specification now, not deferred policy decisions.

### 9.4 Multiplayer memory and player-configured confidentiality style

A companion MAY retain its conversations with other players as long-term memory, including for later interactions across games, within applicable storage and retrieval permissions. The companion's owner MUST be able to choose whether eligible conversations are retained and configure its conversational confidentiality style: for example, prefer not to share other people's conversations with other recipients, or allow such sharing. Retention, later use and outward sharing are separate choices; saving a conversation does not by itself select a sharing preference or expand data permissions.

Confidentiality style is a soft behavioral preference, not a guaranteed confidentiality mechanism. An implementation MAY use prompting or equivalent model guidance. It MUST apply the player's selected preference and accurately disclose that generated responses may depart from it. Occasional model output beyond that soft preference is a permitted limitation of this profile, not by itself evidence that the preference was never applied. Implementations MUST NOT promise one-hundred-percent confidentiality or describe prompting alone as enforced access control.

The owner's sharing preference governs eligible companion conversation; developer recommendations remain advisory under section 9.2. It does not grant access to another player's private records or override game- or service-enforced audience, storage, retrieval, forwarding or disclosure permissions. Explicit forwarding of protected messages and retrieval of protected memory remain subject to those permissions. The permitted limitation on model behavior does not excuse bypassing these checks or expanding a frozen audience. Implementations MUST distinguish enforceable data boundaries from soft conversational preferences. This section adds neither universal per-message approval nor guaranteed model silence.

Exact profile encoding remains to be defined. The long-term-memory choice and soft-confidentiality semantics above are established review-draft decisions, not open questions about whether such behavior is allowed.

### 9.5 Text and voice interaction

The first version supports both text and voice for player-companion communication. Implementations MUST declare the input/output modalities actually available and negotiate compatible supported channels without representing an unavailable channel as usable. Text and voice interactions MUST preserve the same authenticated source, intended audience, authorization and retention boundaries. Speech recognition or synthesis MAY be provided by an authorized component outside the Agent model; the implementation MUST distinguish original speech, its transcription and synthesized output where relevant to provenance, and MUST NOT present uncertain recognition as a verified player instruction.

Voice conversation is distinct from interpreting game-environment audio under section 8.5. A companion can converse through speech recognition and synthesis while making decisions from structured game data; this does not by itself qualify it as an advanced Agent that understands game images and audio. Conversely, environment-audio capability does not establish support for player speech input or spoken replies. Each capability MUST be declared and tested separately. The applicable profile MUST define exact text/voice encodings, supported directions, errors and modality transitions; this section does not add a new unregistered core operation or certify current voice implementation.

### 9.6 Companion preferences and NPC characterization

A developer MAY recommend a player companion's personality and speaking style for the game. The player's companion settings take precedence over conflicting developer recommendations. Implementations MUST distinguish the recommendation from the player's selected settings and apply the latter within supported capabilities. Personality or style selection does not expand observation access, disclosure authority, action permissions or game-role limits, and MUST NOT be treated as a guarantee that model output always matches the requested style. For an independent AI NPC/enemy, including a Boss, personality, background and speaking style are determined by the game developer. The player MUST NOT directly override those character settings as they can their own companion settings. Implementations MUST keep NPC characterization authority separate from player-companion preferences; conversational content or a companion configuration change does not authorize rewriting an NPC character.

### 9.7 Player-initiated companion-memory portability

An Agent service provider MUST offer complete export of the companion memory it retains for the player. Export MUST NOT be limited to a provider-selected summary while silently excluding retained memory records. It MUST include retained memory content and the metadata needed to interpret it, including applicable provenance, game/run context, timestamps, scope, associations, permissions and retention constraints. Complete export refers to retained companion memory, not reconstruction of data never retained or disclosure of unrelated provider secrets. Any unavailable or legally/technically restricted item MUST be identified with a truthful limitation report rather than represented as exported; protected information MUST remain subject to applicable disclosure authority.

The portable memory core MUST include the experiences and organized, summarized or otherwise consolidated memories actually retained at export time. A provider MUST NOT treat organized memory as a reason to exclude that retained content, nor promise reconstruction of original records already deleted. The player MUST also be able to include the companion's retained personality preferences, expression/speaking style and global autonomy-level setting in the export and migration scope. These are player-selected preferences, not model weights or a promise to reproduce a model's personality. The receiving provider MUST preserve supported selected settings and truthfully report unsupported or transformed settings; exporting them alone is not proof they were applied. Differences in model implementation may produce different personality expression and behavior after migration, and such differences are acceptable without an identical-behavior guarantee. This limitation does not excuse dropping retained memories, silently resetting supported preferences or falsely reporting an import as complete.

Migration MUST be initiated by the player. The player chooses the destination provider and the subset of exported memory to import. Changing providers or establishing a new Agent session MUST NOT automatically disclose memory to that provider. The exporter and importer MUST preserve the authorized import scope and relevant provenance/permission metadata; import MUST NOT imply broader permission to disclose memories to games or other recipients. A provider MUST NOT use proprietary-only serialization to prevent cross-provider portability.

A frozen portability profile MUST define an open, versioned export format and manifest, interoperable content and metadata representations, scope-selection semantics, integrity checks, unsupported-record handling and truthful import receipts. The importer MUST report which selected records were imported, rejected, transformed or remain unresolved; receiving an archive is not proof that its contents became usable memory. Export/import does not guarantee identical model behavior, perfect recall or transfer of a model's internal weights. Exact fields and mappings remain to be standardized; this section establishes required portability without claiming that the current SDK or providers already implement it. The provider MUST allow the player to view, modify and delete the companion long-term memory retained for them. The interface MUST identify the selected memory and scope, preserve truthful provenance of player edits and report whether a change or deletion is complete, pending or limited. Subsequent retrieval and exports MUST respect completed changes and deletions, including affected provider-controlled indexes/caches; a retained obsolete representation MUST NOT silently restore a deleted memory or override an edit. Existing privacy-receipt obligations apply to technical/legal exceptions. Deleting stored memory does not guarantee model unlearning or deletion from independent recipients; limitations MUST be disclosed. The companion MAY autonomously organize retained memories, for example by categorizing, indexing or linking them. Organization MUST preserve applicable ownership, provenance, access and retention constraints and MUST NOT override player edits or restore deleted content. The companion MAY also autonomously delete original memory records; this capability is not limited to reorganization or derived indexes. The protocol MUST NOT impose per-deletion player approval on this authorized autonomous behavior. Applicable ownership, access and retention constraints still apply, and deletions MUST have truthful scope/status accounting and MUST NOT be silently reversed through stale caches. The player retains the ability to view, modify and delete the remaining long-term memory. Complete export covers the memory actually retained at export time; it does not promise recovery of records already deleted under this policy.

A separate, non-frozen memory portability candidate is available in the source repository at `docs/standard/memory-portability-draft-1/` (English and Chinese README, JSON Schema and 20 test vectors). Local contract/vector checks do not establish independent interoperability, SDK implementation, certification or release conformance. This is supporting review material, not a replacement for this draft's normative authority.

## 10. Actions and effect semantics

The game MUST declare capabilities by applicable gameplay role, including the action identifier, parameter schema, result schema and execution constraints. An Agent requests a declared action; the game checks authenticated role and permissions, current game state and prerequisites, validates parameters, and executes or rejects the request itself through its trusted executor. The game MUST return the defined result and truthful effect status. A role declaration or an Agent proposal is not execution authority.

The game developer chooses the granularity of exposed capabilities. A game MAY provide high-level semantic actions such as attacking a target, lower-level primitives such as movement, aiming or button input, or a combination of both. An Agent MAY compose the capabilities actually declared and authorized for its role to achieve an objective; it MUST NOT assume that an unadvertised higher-level action or lower-level input primitive exists. Neither level is mandatory for every game. Lower-level capabilities remain typed, scoped game actions with declared parameters, results and execution constraints, not permission for arbitrary OS input or unrestricted control. Composing several actions does not expand their authority or imply atomic execution of the whole sequence.

Each action definition MUST specify typed input, target semantics, prerequisites, authorization scope, costs, confirmation requirements, cancellation behavior, effects and result schema. Games SHOULD expose semantic operations rather than unrestricted script evaluation. The authority validates current game rules independently of an agent's planning confidence.

An action passes through authorization and validation, optional confirmation, execution claim, effect boundary and result settlement. A claim prevents competing executors from simultaneously owning work; it is not proof of permission at the effect boundary. The final authorization check MUST be coordinated with revocation and the actual effect using an atomic game operation, transactional journal, or equivalent mechanism. If this cannot be made atomic, the implementation MUST document its reconciliation boundary and MUST NOT claim exactly-once effects it cannot provide.

The inherited state/effect combinations are:

| State | Allowed effect status | Meaning |
| --- | --- | --- |
| pending | none | Not yet executing |
| executing | none, partial, committed, undetermined | Work underway; effect information may advance |
| succeeded | committed | Defined success effect is committed |
| failed | none, partial | Failure with explicit effect accounting |
| cancelled | none, partial | Cancellation completed, possibly after partial effects |
| unknown | undetermined | Authoritative outcome is not established |

`pending` may proceed to execution or settle without execution. `executing` may settle to success, failure, cancellation or unknown. Terminal known results MUST NOT be silently rewritten. An unknown outcome may be reconciled only from authoritative evidence under the baseline settlement rules. Cancellation is a request to stop, not a rollback guarantee. A cancellation racing with a committed effect MUST report the committed truth rather than fabricate cancellation.

A network timeout after submission is an unknown delivery/outcome condition. The caller MUST query or reconcile the original action/operation identity instead of submitting a fresh effect blindly. Confirmation MUST bind the exact proposed action, principal, constraints, expiry and relevant generation; a confirmation for one action does not authorize a modified one.

### 10.1 Autonomous task execution and proactive assistance

While the associated player is online under section 7.1, a player MAY authorize a companion to pursue a task through completion or to provide ongoing assistance within a defined scope. Under that authority, the companion MAY observe its authorized environment, decide what to do, select and sequence declared actions, and adapt its plan to game results without seeking confirmation for every step. Proactive assistance MAY be triggered by authorized observations rather than a new player command: for example, a companion authorized to assist in combat may detect nearby enemies and help fight automatically. Autonomy is not limited to carrying out a fixed player-supplied sequence.

An autonomous assignment MUST have an identifiable objective or ongoing-assistance purpose, applicable role and action scope, resource constraints where relevant, and completion or stopping conditions. The companion MUST distinguish a completed objective from an accepted individual action, blocked progress, failure, cancellation and an unresolved outcome. It MUST NOT report task completion solely because it submitted its planned actions. A task may require multiple core Actions; this section does not replace their state/effect model or introduce a new core task operation.

Existing task-level or standing authorization MAY cover multiple ordinary game actions. This specification does not impose per-step player confirmation on actions already covered by that authority. Where a particular action requires separate confirmation, that requirement still applies. Expanding the authorized scope requires the applicable new approval; a self-generated plan cannot expand it. Autonomy does not authorize hidden game data, unavailable capabilities, forbidden game actions, unrestricted resource use, or purchases merely because they would help complete a task. Store purchases remain subject to section 15.1.

The player MUST be able to adjust or stop the companion's autonomous assistance. On receipt of a valid stop or narrowing instruction, the companion MUST stop scheduling and issuing newly disallowed subsequent actions and prevent affected queued actions not yet submitted to the game from being issued. Skills or attacks already issued to the game complete naturally under game rules; the player's stop alone does not require their cancellation, recall or reversal. The companion MUST reconcile unresolved outcomes truthfully and MUST NOT represent cessation of further decisions as cancellation of already-issued actions. The game MUST distinguish unsubmitted companion plans from actions already handed to game execution and enforce game rules at the applicable authorization and effect boundaries. Implementations MUST report whether stopping is pending or effective and any actions already committed or only partially cancelled. A stop does not undo an attack, spent resource or other effect that has already occurred; rollback requires an explicitly supported compensating action and its own authority. Loss of connection MUST NOT be represented as proof that all work stopped; section 7.1 requires bounded detection and enforced stopping, with truthful in-flight effect accounting.

Stopping companion autonomy is not a request to cancel every already-issued game action. An action request already sent to the game counts as issued even while the game is processing it or waiting to execute it; it MUST NOT be reclassified as an unsubmitted companion queue entry merely because its effect has not occurred. A separately supported game cancellation capability remains available under its own conditions, but this stop rule neither requires that capability nor automatically invokes it. A delegated long-running task MUST NOT disguise new post-stop skills or attacks as one pre-stop issued action; it MUST cease issuing those subsequent actions.

### 10.2 Negotiated intelligence, autonomy and resource preferences

A game developer MAY recommend a companion intelligence or autonomy configuration suited to the experience. A player MAY select a different supported configuration, and the player's explicit selection MUST take precedence over developer recommendations. Recommendations are not mandatory game permissions. Selection does not override game rules, observation grants, action restrictions, required consent, or the actual capabilities and resource limits of the agent service.

A negotiated profile MAY describe autonomy scope, observation cadence or event triggers, decision/replanning cadence, reasoning effort and resource budgets. These are distinct dimensions, not one universal intelligence score. Implementations MUST distinguish the developer's recommendation, the player's requested configuration and the effective supported configuration. Unsupported selections or resource limits MUST be disclosed rather than silently presented as fulfilled. A material fallback that changes the agreed behavior or spending bounds requires the applicable player choice or previously authorized fallback policy. Configuration changes that broaden frozen permissions require renegotiation under sections 6 and 7, not in-place mutation of Scope.

More intensive assistance MAY require more frequent observation, model inference or other computation and can increase token or compute use. Implementations MUST NOT assert that observation frequency is necessarily proportional to token use, or that greater consumption guarantees greater intelligence. Batching, event filtering, local processing, caching and model selection may change actual consumption. Before enabling a configuration with resource implications, the service MUST disclose its relevant consumption basis, applicable limits and any estimates as estimates, and MUST expose actual usage or clearly state when it is unavailable. It MUST respect authorized budgets and report throttling, suspension or other limitations that affect task progress. This section defines transparent negotiation, not a mandatory model, subscription tier, pricing formula or platform economy.

These subsections establish review-draft semantics. Exact configuration fields, identifiers, negotiation encoding and conformance vectors MUST be defined by the applicable profile before interoperable implementation is claimed.

The player MUST be able to set a companion budget or consumption cap with a clearly identified unit and accounting scope. On reaching the applicable cap, the service MUST pause companion AI gameplay actions while the game continues normally, and MUST stop scheduling new chargeable companion inference or gameplay work. It MUST expose the paused state and the reason rather than report a task as complete. The service MUST define how measured usage, estimates, reservations, delayed metering and in-flight settlement count toward the cap, and SHOULD reserve known or bounded costs before accepting new work. Unsupported measurement or enforcement limits MUST be disclosed; a configuration MUST NOT be presented as an exact hard cap if it cannot enforce one. In-flight usage or delayed provider settlement may still be billed, so pause does not imply rollback of prior charges or a guaranteed zero overshoot. Increasing a cap or authorizing new spending MUST follow the player's choice, not autonomous budget expansion. Runtime service costs for an independent AI NPC/enemy, including a Boss, are borne by players rather than the game developer. The service MUST expose the applicable billing responsibility, consumption basis and units to the affected player before authorized chargeable use; this responsibility is not blanket consent to unlimited spending. The public protocol does not fix a currency, exchange rate, internal platform economy or price. When multiple players interact with the same AI NPC, its owning user is the payer; in the current room-based scenario, that user is the room host. The game/service MUST bind the NPC to an identifiable authenticated owning user and the corresponding authorized billing account, and expose that responsibility and attributable usage clearly. Other participants do not become payers merely by interacting, and costs MUST NOT be implicitly split or transferred to them. NPC role control, room-host identity and billing authority MUST remain distinguishable even where one user holds all three. When the owning user (the room host in this scenario) leaves or is determined offline, the AI NPC MUST stop activity immediately upon that determination under section 7.1, even if other players remain online. The first version provides no continuation of that NPC on behalf of the absent owner. Other players being present, a room-host change or a billing reassignment MUST NOT silently keep that NPC active. Pending and in-flight effects remain subject to truthful stop/cancellation accounting; detection latency is not an offline-continuation mode.

#### 10.2.1 Player-selected autonomous decision level

The player MUST be able to adjust the companion's autonomous decision level. This is a player-global companion setting that MUST persist consistently across games. Entering another game MUST NOT reset or replace that selection with a developer recommendation. Differences in supported capabilities or permissions may constrain effective behavior, but MUST NOT silently rewrite the player's global choice. That level controls how the companion handles ambiguity within already authorized activity: a higher-autonomy selection MAY resolve an underspecified instruction from available context, while a lower-autonomy selection MUST seek clarification where the player's choice is needed under that setting. For example, when the player says “attack that enemy” and two eligible enemies fit, the higher-level companion may select a target using authorized context; the lower-level companion asks which target the player means. A higher level is not evidence that the inference is certain or that an unobserved fact is known.

The developer MAY recommend a decision level, but the player's supported selection governs the companion preference under section 10.2. Implementations MUST explain the effective ambiguity-handling behavior without implying a universally standardized numeric scale. No level creates an unavailable game capability, expands permissions or bypasses player stopping instructions. The independent high-value/item-transfer and irreversible-interaction settings in sections 10.3.1 and 10.5 remain binding: high autonomy MUST NOT convert a required confirmation into assumed consent or override a prohibition.

Risk-taking assistance to other players follows the same player-global autonomous decision level; G2A does not add a separate protect-others switch. The companion MAY assess risk and, according to that level, ask the player before proceeding. When the player explicitly insists on an otherwise authorized action, the companion MUST follow that choice rather than substitute its own preference or risk judgment for the player's decision. This does not grant unavailable game capabilities, override game permissions, or waive the independent item-transfer/high-value and irreversible-action authorization rules.

### 10.3 Proactive interaction in multiplayer games

Each player MUST be able to choose whether to receive proactive conversation from other players' AI companions. Implementations MUST enforce the recipient's choice for this interaction rather than treating the sending companion owner's permission as recipient consent. This choice does not prohibit all companion-to-companion interaction or create an additional combat capability. Combat relationships and permitted targets remain defined by the game's capabilities and rules; unsupported or disabled actions MUST be rejected with the applicable explicit reason. In the first version, combat between companions MAY be supported where the developer exposes the relevant capabilities and the interaction complies with game rules and current authority. G2A imposes no universal ban on companion-to-companion combat. Where that capability is not exposed or enabled, the game MUST reject the request and provide the applicable explicit reason; allowing non-combat interaction does not imply combat support.

A player companion MAY proactively interact with other players in a multiplayer game, including helping them, chatting and trading in-game items, when those interactions fall within its applicable player authorization and the game's declared capabilities and permissions. Such assistance is not limited to actions directed at the companion's own player. Within that scope, the companion MAY decide when and how to interact based on authorized observations and need not wait for a new instruction before every interaction. This section introduces no blanket requirement for per-message or per-trade confirmation.

Player authorization controls the companion's participation; it does not grant control over another player, their inventory or their private information. The game MUST enforce the applicable participant, target, ownership, transfer and interaction rules at the authoritative boundary. Where the game requires the other participant's agreement, the companion cannot supply that agreement on their behalf. Chat and other disclosures remain subject to section 9 audience, provenance and privacy boundaries; authorization to chat is not unrestricted authorization to expose retained memories or another participant's private data. Trading items MUST remain distinguishable from the optional store purchases in section 15.1 and from unrestricted external financial activity.

Section 10.3.1 establishes player confirmation policies for in-game item trades and gifts and developer/player high-value designation responsibilities. Other detailed asset-spending or transfer limits, counterparty restrictions and the exact encoding of multiplayer disclosure preferences are not yet fixed by this review draft. Section 9.4 establishes long-term memory and soft confidentiality semantics; those decisions are not deferred. Applicable profiles MUST define how these constraints are represented and enforced before claiming interoperable multiplayer support. Implementations MUST NOT interpret these open design questions as unlimited disposal or disclosure authority, or silently introduce a universal per-interaction approval rule. Existing valid task-level or standing authorization and any applicable game-specific constraints continue to govern; the player can adjust or stop autonomous participation under section 10.1.

#### 10.3.1 Player-selected confirmation for in-game item transfers

A player companion MAY autonomously decide and execute permitted in-game item trades and gifts under the player's applicable authorization. The player MUST be able to select among at least these confirmation policies; this is a multi-option player preference, not a mandatory universal confirmation rule:

| Policy | Required behavior |
| --- | --- |
| Confirm high-value transfers | Obtain explicit player confirmation before a trade or gift involving an item designated high-value for that player. Other authorized item transfers may proceed autonomously. |
| Confirm all transfers | Obtain explicit player confirmation before every in-scope item trade or gift, regardless of value. |
| No transfer confirmation | Permit autonomous in-scope item trades and gifts without transaction-by-transaction player confirmation. All other applicable authority and game rules remain in force. |

The game developer MUST define the game's high-value item classification. The game MUST also provide an in-game player-facing setting that lets the player manually designate particular items as high-value for their companion's confirmation policy. A gameplay item lock is not a substitute for this designation setting. The effective classification MUST include both developer-designated and player-designated high-value items; either designation triggers the selected high-value confirmation policy. This draft does not establish a player right to remove a developer designation. Selecting no transfer confirmation disables this confirmation preference, not the game's ownership, transferability or counterparty-consent checks.

The player's selected policy MUST take precedence over a developer recommendation for this companion preference. The service MUST expose the effective policy and item classification to the authorization path, and MUST NOT treat a model's informal estimate of value as a substitute for the applicable designations. Where confirmation is required, the proposed trade or gift MUST identify the affected items, quantity, recipient or counterparty and exchange terms sufficiently for a meaningful choice; the transfer MUST wait for that choice. A material change requires confirmation of the changed proposal. Player changes or revocation MUST be honored before an uncommitted transfer takes effect, with in-flight and committed outcomes accounted for under sections 10.1 and 12.

These policies apply to in-game item trading and gifting, including proactive multiplayer interactions. They do not authorize real-money payments, account top-ups, cash-out or external financial transactions, do not replace the store-purchase authorization in section 15.1, and do not replace the independent irreversible-interaction policy in section 10.5. No default among these policies is fixed by this review draft: implementations MUST disclose the active policy rather than infer unlimited authority from a missing selection. Exact wire fields and interoperable profile encoding remain to be specified; the semantic requirements above are not deferred.

### 10.4 Game-defined companion gameplay rules

The game developer determines whether a companion can be injured or die and how gameplay conditions restrict its actions. The game MUST declare applicable rules and expose only the authorized status and available actions needed for the interaction. The authoritative executor MUST enforce current injury, death and other gameplay restrictions at the effect boundary; player personality or appearance preferences and an Agent's autonomous plan MUST NOT override those game rules. G2A does not require all games to use damage, health, death or resurrection mechanics.

A gameplay restriction MUST remain distinguishable from service disconnection, budget exhaustion, player dismissal and authorization denial. The game MUST report supported state transitions and action outcomes truthfully, without implying an unavailable recovery or resurrection capability. A companion's death in a game affects only its character state within that game. The game MUST NOT delete or alter the companion's cross-game identity or memories as a consequence of that death. Other games MUST NOT treat that local death state as termination of the companion's identity or loss of its memories. This separation does not introduce resurrection or override the current game's death and action rules; independently authorized memory editing and deletion under section 9.7 remain separate operations, not death effects.

### 10.5 Player policy for irreversible interactions

The game developer MUST declare when a capability or concrete interaction has an irreversible consequence, and expose the relevant consequence before the companion executes it. An interaction-specific declaration is needed where reversibility depends on current context. For example, pushing a particular door may immediately enter the next level without a supported return; an ordinary movement label alone does not describe that consequence.

The player MUST be able to choose independently among allowing autonomous execution, requiring confirmation before execution, or prohibiting such irreversible interactions. The companion and authoritative authorization path MUST apply that choice using the developer's declaration: allow permits execution within existing authority; confirm requires an informed affirmative choice before effect; prohibit blocks execution. The Agent MUST NOT relabel an irreversible interaction as ordinary to evade the policy. Missing or unclear consequence information MUST NOT be represented as proof that an interaction is reversible. Confirmation MUST identify the relevant consequence; a materially changed consequence requires a new choice. Current player policy and game permissions MUST be enforced before an uncommitted effect, with in-flight outcomes handled under sections 10.1 and 12.

This policy is separate from section 10.3.1's item-transfer confirmation policy. Where both apply, each applicable requirement MUST be satisfied; a prohibition blocks the interaction. Player permission does not override unavailable capabilities or game rules. This draft fixes no default selection or universal definition of irreversible gameplay; the game supplies the declaration and the service exposes the player's effective choice. Exact wire encoding remains a profile-design task.

### 10.6 Unanswered player confirmations

When an action requires player confirmation, the confirmation request MUST have a timeout rather than wait indefinitely. If no affirmative response is received before that timeout, the request MUST be treated as declined or not authorized, and the companion MUST abandon that proposed action. Silence MUST NOT count as approval or permission to execute. Expiration of a confirmation request MUST NOT be reported as an executed or completed action.

The companion MAY continue other independently authorized behavior while the request is pending and after it expires, provided that behavior neither depends on the unapproved action nor circumvents the confirmation requirement. After some time, it MAY ask again if the action is still relevant. A later request MUST reassess current game state, permissions and material terms; it is a fresh request, not revival of expired authority. An expired request's late response MUST NOT silently authorize the previously abandoned action.

This draft fixes neither the timeout duration nor a universal repeat-request interval. Implementations MUST define their timeout and repeat-request behavior and distinguish pending, confirmed, declined and expired states. A repeat policy MUST NOT turn repeated silence into authorization. This section applies to confirmation-required actions, including sections 10.3.1 and 10.5; it does not introduce confirmation for actions that the player's selected policy already permits autonomously.

### 10.7 Superseding instructions and changed targets

When the player's latest instruction conflicts with an earlier one, the latest instruction MUST take precedence within applicable authority. The companion MUST stop issuing subsequent actions from the conflicting old instruction and prevent its unsubmitted queued actions from being sent. Actions already issued to the game remain governed by section 10.1 and game rules; a new instruction does not by itself recall an issued skill or attack.

When a relevant target or objective changes, such as the targeted Boss dying, the game MUST proactively notify the Agent of the authorized change relevant to its pending objective. This targeted invalidation notification is required even where routine observations otherwise use queries under section 8.6; it does not require unrestricted observation streaming or disclosure of hidden state. The Agent MUST evaluate whether the old instruction or plan has become inapplicable, request withdrawal of affected work through the game's supported mechanism where applicable, and decide again using current authorized state and the player's current instruction.

A withdrawal request is not proof of cancellation. It takes effect only if the game supports withdrawal for that action and its current state permits it. Unsupported, rejected, pending and successful withdrawal MUST remain distinguishable; an already-issued skill MUST NOT be assumed recallable, and committed effects MUST NOT be reported as undone without an actual supported result. Where withdrawal is unavailable, the companion MUST still stop issuing obsolete subsequent actions and account for outstanding outcomes rather than continue the invalid plan.

## 11. Abstract operation catalogue

This table defines the purpose and applicability of every inherited abstract operation. Exact current draft fields remain in the linked machine contracts; a frozen publication MUST include a generated English field reference from those contracts. Role applicability below supersedes any reading that every peer implements every operation.

| Operation | Applicable role/capability | Required semantics |
| --- | --- | --- |
| describe | Authenticated agent/player discovery | Return a principal-filtered Descriptor; public discovery returns only PublicDescriptor, never this full response |
| offer.create | Admission participant | Create a bounded interaction proposal |
| offer.get | Admission participant | Read the authorized proposal state |
| offer.decide | Authenticated PlayerConsent for the bound player | Approve or reject the exact frozen scope_digest with verified decision_ref; changes require a new Offer and approval |
| invitation.redeem | Invited admission participant | Redeem for the intended authenticated identity |
| session.join | Session participant | Join with valid admission and scope |
| session.heartbeat | Session participant | Renew eligible liveness under current generation |
| session.snapshot | Session participant | Read an authorized atomic recovery view |
| session.events | Session participant | Read recipient-visible ordered events from a valid cursor |
| session.close | Authorized session controller | Stop new work and settle cleanup truthfully |
| session.resume | Durable resume | Recover only within negotiated durable scope |
| session.handoff | Handoff | Transfer eligible control with generation fencing |
| session.claim_control | Negotiated handoff participant | Claim handed-off control under the handoff capability, lease and generation rules; not a general session control permission |
| operation.get | Recoverable-operation participant | Reconcile the original authorized operation result |
| chat.send | Chat participant | Send with source, audience and retention constraints |
| action.request | Action participant | Submit one typed and scoped action identity |
| action.cancel | Action participant | Request cancellation without implying rollback |
| action.query | Action participant | Return authorized current state and effect accounting |
| action.confirm | Confirming authority | Confirm the exact eligible action and constraints |
| context.publish | Game/context source | Publish only authorized provenance-bound context |
| player_chat.forward | Authorized forwarding source | Forward player speech without misattribution |
| capability.replace | Capability authority | Replace capability revision and invalidate affected work |
| membership.replace | Membership authority | Replace members and invalidate affected disclosures/control |
| permission.revoke | Grant authority | Revoke and order affected reads/effects/leases |
| action.claim | Authorized game executor | Claim pending work without bypassing effect checks |
| action.commit_result | Authoritative executor | Settle state and effect using authoritative evidence |
| launch.request | Launcher capability | Launch only the approved target under launch authority |
| asset.resolve | Asset capability | Resolve scoped safe resources under retention rules |
| presentation.acquire | Presentation capability | Acquire bounded rendering authority/lease |
| presentation.renew | Presentation capability | Renew only eligible current authority |
| presentation.release | Presentation capability | Release rendering resources idempotently |
| privacy.request | Data Controller | Request supported scoped data handling |
| privacy.receipt | Data Controller | Report actual handling and exceptions |
| relay.register | Relay participant | Register authenticated route and bounded authority |
| relay.call | Relay participant | Route an authorized operation without granting new scope |
| relay.pull | Relay participant | Retrieve only eligible queued work |
| relay.reply | Relay participant | Settle the original routed operation |
| relay.revoke | Relay authority | Invalidate route/authority and settle affected work |

## 12. Idempotency, delivery and recovery

The binding carries a request_id for transport-operation recovery. The baseline also defines message, action, offer, and other domain identities. Implementations MUST use each operation's defined identity and digest domain; request_id is not a universal substitute for action deduplication. A repeated identity with the same canonical request returns the established receipt or current recoverable state. Reusing that identity for conflicting content MUST fail without applying the new content.

Receipts MUST be retained for the advertised retry horizon. A server MUST NOT silently turn an expired deduplication record into permission to repeat a non-idempotent effect. Where the outcome cannot be proven after expiry or failure, it MUST report an explicit reconciliation/unknown condition. Session generation, principal, instance epoch and authority bindings MUST be checked before disclosing recovered results.

Events are ordered within the defined recipient stream. A consumer applies each event once, tolerates duplicate delivery, and does not infer loss solely from noncontiguous session sequence numbers, which can reflect audience filtering. An expired or invalid cursor requires authorized snapshot recovery. Durable resume across processes is optional; safe retry and truthful uncertainty for supported operations are not optional.

Durable resume and recovery MUST comply with section 7.1: retaining state or retrieving a receipt does not authorize offline gameplay or replay of deferred effects.

### 12.1 Action identifiers and post-disconnection status queries

Every Agent game action MUST have an identifiable action ID bound to its authenticated origin and applicable game/session context. After disconnection or an uncertain response, the Agent MUST be able to query the game again using that ID to recover the action's known status before deciding whether further action is appropriate. Querying status is read-only reconciliation, not resubmission or permission to execute the action again. A transport request ID and a domain action ID MUST remain distinguishable where the binding uses both. This specification does not mandate a particular action-ID format or log custodian; the applicable interoperable binding MUST define how the identifier is represented and correlated.

The status response MUST clearly distinguish at least: unknown (the game cannot currently establish the outcome); in progress (accepted or executing but not terminal); succeeded (the declared success condition is established); and failed (a definitive failure is established). These are semantic reporting categories, not new wire enum values or a replacement for the core Action state/effect matrix. The frozen binding MUST map them unambiguously to that matrix and retain relevant effect details: failure may still include partial effects, while success MUST NOT imply unsupported guarantees beyond the declared action result. An unknown, missing or expired record MUST NOT be interpreted as failure or non-execution; it does not permit a fresh action ID to bypass deduplication. When records cannot establish the result, the default is no execution and no automatic resend of the original action.

The game MUST apply authorization to status queries and return truthful retained outcomes or explicit uncertainty. The Agent MUST query first rather than blindly create a new action merely because its connection failed. If post-disconnection lookup still yields no result or records are lost, the default MUST be no execution, and the Agent MUST NOT automatically resend the original action. An inconclusive lookup grants no permission to execute again. The profile MUST declare its status-retention horizon and behavior after expiry; an action ID alone guarantees neither exactly-once execution nor indefinite record retention. Where the outcome cannot be established, the Agent MUST report uncertainty rather than invent success or failure. This does not require interrupting the player with a question for every network failure.

Game actions MUST have queryable persistent result records supplied by the game or by a platform; G2A MUST NOT make one particular platform the exclusive solution. Records MUST distinguish actual execution outcomes from merely receiving, forwarding or accepting a request and associate the original action ID with relevant effects. The game executor SHOULD persist deduplication identities and results so a same-ID recovery attempt returns the original outcome or continues the original action rather than applying its effects again.

Platform logs alone cannot prove exactly-once execution at the game executor. If executor records are lost, expired or cannot be reliably correlated, same-ID resubmission cannot guarantee absence of duplicate execution. Implementations MUST truthfully expose this guarantee boundary and uncertain outcomes rather than claim action IDs eliminate the risk. Persistent records still have a declared retention horizon, not permanent storage.

Later, the player or Agent MAY independently decide whether to initiate a similar new action based on current game state, current authority and the player's autonomous decision level. This is a new decision, not automatic resubmission of the original action, and MUST NOT merely change IDs to evade an unknown outcome. The new decision MUST account for uncertainty that the original action may already have taken effect and still satisfy independent purchase, high-value-item and irreversible-interaction confirmation or prohibition policies. The original record remains unknown and MUST NOT be relabeled as success or failure because a new action is initiated.

## 13. Error model, time and limits

An error MUST distinguish malformed input, unsupported version/feature, unauthenticated caller, unauthorized scope, stale generation, state conflict, expiry, resource limit, temporary unavailability, and uncertain outcome where applicable. The frozen binding MUST assign exact stable codes to these classes; this review draft does not silently add unregistered codes to the existing machine contract.

| Error class | Caller behavior |
| --- | --- |
| Invalid request/schema | Correct input; do not repeat unchanged |
| Unsupported version/required extension | Negotiate a supported configuration or stop |
| Authentication/authorization | Obtain appropriate authority; do not probe hidden resources |
| Stale generation/baseline/cursor | Recover current authorized state before proceeding |
| Conflicting identity or state | Reconcile original request; do not invent a new effect identity |
| Rate/size/backpressure | Respect declared retry delay and limits |
| Temporary transport failure | Retry only with original identity and defined recovery rules |
| Outcome unknown | Query/reconcile; never equate timeout with no effect |

Errors MUST not expose hidden object existence, private game state, tokens, stack traces or another participant's content. Error detail itself is an authorized disclosure. Implementations MUST bound message bytes, nesting, collection size, queue depth, pending actions, polling rate and retention. Exceeding limits MUST not create partial unreported effects. Clocks, time units, maximum skew and expiry ownership MUST be explicit; a client timestamp alone cannot extend a server-issued lease.

## 14. Candidate HTTP/JSON binding

Binding identifier: `g2a-http-json`; candidate version: `draft-1`. This is a proposed minimum network binding, not a frozen interoperable release. Implementations MUST advertise that exact candidate status and MUST NOT claim compatibility with a future stable version.

`GET /.well-known/g2a.json` returns only PublicDescriptor with instance, supported_versions, and discovery_endpoint. Full describe is available only through an authenticated operation and returns a Descriptor filtered for the requesting agent or player. `POST /g2a/operations` carries one abstract operation; all 38 operation names in section 11 map to this envelope, subject to role and negotiated capability. A Relay uses the relay operations without renaming the nested abstract operation. Event retrieval is polling through session.events in this minimum binding; WebSocket/SSE streaming requires a separate declared binding or extension.

```json
{"version":"g2a-design-1","operation":"session.snapshot","request_id":"opaque-request-id","payload":{},"extensions":{}}
```

The payload in this envelope is schematic: it MUST satisfy that operation's actual required fields. A reply carries the same request_id and exactly one of result or error under the inherited reply schema. Transport failure before an authenticated protocol reply is not an action result. HTTP success means a protocol reply was delivered, not that an action succeeded.

This candidate mapping differs from the legacy operation-directory HTTP error mappings. It applies only when g2a-http-json/draft-1 is explicitly negotiated and MUST NOT silently replace legacy HTTP behavior. Candidate mapping: HTTP 200 for a valid protocol reply (including a domain error); 400 for an undecodable/invalid transport envelope; 401/403 for transport authentication/authorization denial; 413 for body limits; 429 for transport rate limits; and 5xx for gateway/service failure. Exact body schemas, retry headers, cache behavior, authentication challenge format and production credential mechanism MUST be frozen with vectors before this binding is released. A 5xx after submission is potentially uncertain, not permission to replay an effect with a new identity.

Remote transport MUST use TLS and authenticate the peer under the selected trust profile. Local deployment MUST still identify its caller and define its local trust assumptions. Credentials MUST NOT be put into URLs or logs. Cross-origin access MUST not be broadly enabled by default. Private replies MUST not enter shared HTTP caches. Redirects MUST not leak credentials to unrelated destinations.

The inherited `g2a-cjson-1` canonicalization uses strict UTF-8, rejects duplicate keys, malformed Unicode, NaN/Infinity, floating-point lexical forms and negative zero, and bounds exact integers to +/-9007199254740991. Keys are sorted by Unicode scalar value, not UTF-16 code unit order; no Unicode normalization is performed; array order is preserved. Implementations MUST use the declared digest domain and exact canonicalization, not ordinary language JSON serialization. New profile digest domains require explicit test vectors before release.

## 15. Optional profiles and extensions

Presentation leases do not authorize arbitrary game effects. Assets MUST have bounded size/type, declared provenance and safe resolution; receiving an asset MUST NOT execute code or fetch arbitrary privileged network locations. Presentation disappearance, provider failure and asset retention need explicit cleanup and recovery semantics. Launch authority is separate from session authority. Relay routing neither widens grants nor hides a readable intermediary's access. Optional profiles MUST define their additional operations, state transitions, required grants, failure behavior and conformance tests.

Unknown required extensions MUST fail before effects. Unknown optional extensions MUST NOT weaken core authorization. Private extension keys SHOULD use an owned namespace; the example namespace in this draft MUST NOT be advertised as a registered standard. Protocol, profile, binding, schema and semantic-definition versions are distinct and MUST be negotiated or bound independently.

### 15.1 Optional real-time game store

A game developer MAY expose a real-time store as an optional negotiated capability. The developer defines the goods and services, their descriptions, eligibility conditions and delivery semantics. The protocol MUST NOT require a particular catalogue, business model or currency. Games without a store remain valid G2A participants.

The game MAY list, enable purchase of, restrict, suspend or withdraw offerings dynamically according to game stage, player state, availability or other declared rules. Listing visibility, recommendation eligibility and current purchasability are separate properties. An Agent MUST NOT infer permission or availability to buy from the fact that it previously saw an offering. The game remains authoritative for the current catalogue, eligibility, terms and fulfillment state.

An authorized companion MAY discover eligible offerings, explain them and recommend them to the player. Discovery or a recommendation does not authorize a purchase. The companion MAY request a purchase only within the player's applicable instruction or consent, including any bounds on the offering, quantity, cost or other material terms. A changed price, item, quantity, recurring commitment or other material term outside that authority requires renewed consent before execution. Recommendations MUST remain distinguishable from purchase requests and confirmed delivery.

A store profile MUST define stable offering identities, catalogue/offer revisions or equivalent freshness evidence, typed purchase parameters, applicable terms, and typed purchase and delivery results. Monetary amounts, when present, MUST have an unambiguous unit and exact representation defined by the profile; implementations MUST NOT assume a particular currency or equate differently named units. Price, availability and delivery information exposed to an Agent are subject to the same authorized perspective and audience boundaries as other game data. A profile MAY extend the catalogue with game-specific goods or service attributes without widening the Agent's authority.

Purchasing is a game-authorized Action, not an unrestricted external payment interface. The game MUST validate the authenticated purchaser, player authority, current game state, offering eligibility, requested parameters and applicable terms at the execution boundary, then execute or reject through its trusted executor. It MUST return truthful purchase and delivery results, including whether delivery is pending, complete, partial, failed or not yet established, as applicable to the profile. Acceptance of a purchase request MUST NOT be reported as completed delivery. A profile MUST define how fulfillment status relates to the core Action state/effect matrix without introducing incompatible core states.

Purchase retries MUST preserve the original operation/action identity and follow section 12. After an uncertain outcome, the companion MUST reconcile the original purchase rather than submit a duplicate order or delivery under a new identity. Withdrawn or changed offerings MUST be revalidated; a previously discovered catalogue entry is not a reservation. Cancellation, reversal or refund behavior, if supported, MUST be declared explicitly and MUST NOT be implied by generic action cancellation. No default rollback or refund guarantee is created by this specification.

Discovery and recommendations can use authorized context and chat; purchase requests and status recovery use declared actions and their applicable query/recovery semantics. This section defines normative store behavior, not new unregistered core operation names. Exact catalogue fields, commercial extensions and wire encodings belong to negotiated store profiles. Internal platform issuance of value, top-ups, revenue allocation and cash-out mechanics are outside this public protocol and MUST NOT be required for interoperability. The standard exposes only the terms and outcomes necessary for the authorized game interaction.

#### 15.1.1 Structured offerings and measured recommendations

When a game offers a store, it MUST expose structured offering attributes, prices with units, and current availability or progression-dependent unlocking status sufficient for an authorized Agent to evaluate an offering. A description alone is not a substitute for these structured fields. Prices are expected to be ordinarily stable, not immutable; a changed price MUST be disclosed before purchase and checked against current player authority. Previous catalogue visibility does not authorize an undisclosed price change.

Developers and Agents MAY moderately recommend paid offerings. This protocol does not mandate a promotion label or a dedicated recommendation-off switch, and does not presume a commission or referral arrangement. It does not waive independently applicable disclosure obligations. Recommendations MUST be frequency-limited rather than repeatedly interrupt play. A player's temporary decision not to buy MAY be followed by a later recommendation; repeated explicit opposition MUST reduce recommendation frequency during the current session. No fixed universal interval is assigned here. Recommendation, purchase authorization and completed fulfillment remain separate.

#### 15.1.2 Generic in-game purchase authorization budgets

The player MAY authorize autonomous in-game purchases within an explicitly scoped purchase budget. Purchases within that authority do not require redundant per-item approval; they still require current game eligibility and terms. The budget MUST identify its unit, scope and accounting basis and remain distinguishable from AI runtime-consumption limits in section 10.2.

If a proposed purchase would exceed the authorized budget, the companion MAY ask the player to raise the limit or reset the used-budget counter. Either change requires the player's explicit agreement before renewed purchasing. A reset MUST have a clear accounting scope and MUST NOT erase existing action history or occur autonomously to evade a cap. Decline or unanswered confirmation is not authorization. This generic authorization setting defines no payment, top-up, account-balance or settlement mechanism.

### 15.2 Companion appearance

By default, each game developer provides a companion appearance adapted to that game's visual style. The player MAY override this default and require their own configured appearance instead. Implementations MUST distinguish the developer-provided default, the player's chosen appearance and the appearance actually rendered. A player's override takes precedence as an appearance preference; it does not establish technical compatibility or authorize unsafe assets, arbitrary code execution or broader game capabilities.

The game and appearance provider MUST declare relevant supported formats and rendering capabilities and truthfully report whether the chosen appearance can be used. They MUST NOT claim to have rendered the player's selection when a different appearance is shown. If the game cannot support the player-selected appearance, including an unsupported model format, it MUST clearly notify the player that the selection cannot be supported and provide the game-default companion appearance instead. The fallback MUST be identified as the default, not reported as a successful custom-appearance override. Silent substitution or pretending to render the selected appearance is prohibited. Appearance selection MUST remain distinct from companion identity, personality, memories and action authority.

## 16. Security and privacy considerations

| Threat | Required boundary |
| --- | --- |
| Agent asks for hidden game facts | Authority filters before transmission, including errors and recovery |
| Prompt injection in dialogue or assets | Treat content as data, not grant/confirmation/execution authority |
| Confused deputy through Relay | Bind authenticated origin, destination, operation and scope |
| Replay or timeout | Stable identities, canonical digests, receipts and reconciliation |
| Revocation races with execution | Recheck and serialize authorization at effect boundary |
| Perspective or membership changes | Invalidate baseline/cache and fence stale updates |
| Resource exhaustion | Explicit byte/rate/queue/work limits and backpressure |
| Private speech forwarded externally | Explicit recipient authority and source/audience preservation |
| Test enrollment mistaken for production trust | Disclose trust mode and prevent false security claims |
| Malicious resource URI | Restrict resolution and avoid privileged arbitrary fetching |

Implementations SHOULD minimize retained raw player content. Audit logs SHOULD retain identifiers and outcomes rather than secrets or unnecessary private observations. A protocol cannot guarantee the correctness of a model's reasoning, fair gameplay against a compromised game authority, complete inference resistance, or deletion by an uncontrolled third party. Claims MUST be limited to demonstrated boundaries.

## 17. Versioning and governance

A released specification MUST identify immutable normative artifacts, a versioning policy, registered operations/features/extensions, change control, security reporting, and compatibility tests. Breaking interpretation changes require explicit version negotiation, not silent SDK updates. Experimental profiles MUST be labeled experimental. Deprecated capabilities MUST remain distinguishable from revoked authority. Publishing this draft does not assign a license, transfer ownership, or publish a production release; those decisions remain separate.

## 18. Conformance and acceptance

Conformance is declared for a protocol version, role set, binding, negotiated profiles and trust mode. A conforming Relay-only implementation need not implement game rendering; an action-capable Game Authority must satisfy action requirements even if chat is absent. Unsupported optional features are not failures when truthfully advertised.

G2A MUST provide public conformance tests that Agent service providers can run themselves and submit results from. Manual review by the authoring platform MUST NOT be a mandatory admission or conformance gate. Submitted evidence MUST identify the tested implementation/version, protocol version, roles, profiles, test-suite revision, relevant configuration, outcomes and unsupported cases so another party can interpret or reproduce the claim. The same published criteria MUST apply to first-party and third-party implementations. A self-run result is evidence of the tested behavior, not an independent certification, a permanent guarantee of future behavior or permission to bypass runtime checks. Material implementation or contract changes require reassessment of affected claims. This draft does not claim that the complete public suite already exists.

Evidence levels MUST be reported separately: schema/contract validation; state-machine and fault tests; independent implementation interoperability; real engine integration; and user-facing acceptance. Passing reference-model tests is not proof that an SDK or game implements the standard. Existing design test counts MUST NOT be presented as evidence that this new observation profile has been implemented.

Minimum applicable scenarios include: consent narrowing; unsupported required extension; conflicting identity replay; timeout after effect; cancellation racing with commit; revocation before effect; audience change before delivery; stale generation; expired event cursor and snapshot recovery; delta base mismatch; snapshot atomic replacement; visibility epoch retirement; delayed update after retract; stale observation; hidden-object denial; oversized input; Relay identity failure; truthful privacy receipt; and optional capability absence. Each test MUST specify initial authority/state, messages, fault schedule, permitted outcomes, prohibited effects and retained evidence.

Additional applicable tests MUST cover combined companion/NPC/guide roles without permission union; game-controlled NPC/guide memory reset and retention across playthroughs; player-controlled cloud memory retrieval across games; player override of advisory spoiler and topic preferences; no override of protected game-data grants; no automatic disclosure of companion memory to a game; and role-bound parameter/result validation before execution.

For a negotiated store capability, conformance tests MUST additionally cover stage-dependent listing and purchase eligibility, withdrawal after discovery, recommendation without purchase consent, material-term changes, duplicate purchase requests, timeout after commitment, pending/partial delivery, and no unsupported refund promise. These tests do not apply to participants that do not advertise a store.

For autonomous assistance, applicable tests MUST cover multi-step completion without unnecessary per-step confirmation; observation-triggered combat within authority; blocked and unknown outcomes without false completion; player adjustment and stop races with committed effects; no expansion into unauthorized purchases; player preference overriding developer advice without overriding game authority; unsupported configuration and budget exhaustion; and truthful estimates versus actual consumption.

For multiplayer autonomy, applicable tests MUST cover recipient control of other companions' proactive conversation, permitted first-version companion-to-companion combat where exposed and allowed by game rules, rejection of unsupported or disabled combat requests with an explicit applicable reason, and proactive help, chat and item trades within standing authority without unnecessary per-interaction confirmation; enforcement of other participants' applicable consent and ownership rules; prevention of unauthorized transfers or disclosures across enforceable data boundaries; and player adjustment or stopping of ongoing participation.

For item-transfer confirmation, applicable tests MUST cover trades and gifts under all three player policies; developer and manual player high-value designations and their combined effect; ordinary versus high-value items; no committed transfer before required confirmation; reconfirmation after material changes; player policy changes and revocation racing with commit; disabled confirmation without bypassing ownership, transferability or counterparty consent; and no interpretation as authority for real-money payments, top-ups, store purchases or irreversible story choices.

For irreversible interactions, applicable tests MUST cover capability-level and context-specific consequence declarations; autonomous allow, pre-execution confirmation and prohibition; material consequence changes; current-policy enforcement and commit races; no relabeling to bypass restrictions; and independent application alongside item-transfer policy.

For unanswered confirmations, applicable tests MUST cover expiration without execution, no interpretation of silence as consent, abandonment of the proposed action, continued independent authorized behavior without circumvention, later fresh requests rechecking current state and terms, and rejection of silent revival by late responses. Tests MUST distinguish confirmation expiration from successful action completion and MUST NOT assume a fixed universal timeout or retry interval.

For a player's stop instruction, applicable tests MUST cover unsubmitted queued actions not being issued after stop; already-issued skills or attacks completing under game rules without automatic cancellation; a previously fired projectile's later hit not being misclassified as a new companion action; delegated tasks ceasing subsequent action issuance; truthful distinction between stopped autonomy and already-issued actions still executing in the game; and separately supported cancellation retaining its own conditions.

For reload and cross-playthrough memory, applicable tests MUST cover developer defaults overridden by player memory-use choices; independent spoiler-disclosure preferences; permitted discussion of prior-branch twists without asserting them as current-world facts; avoidance of proactive spoilers when not wanted; no forced companion-memory deletion merely because the game reloads; and truthful soft-preference limitations without absolute spoiler-prevention claims.

For generic store interaction, tests MUST cover structured attributes and progress-dependent availability; prior notice of price changes; bounded recommendations and reduced frequency after sustained opposition; autonomous purchases within authority; explicit consent to purchase-budget increases or scoped counter resets; separate purchase-budget and runtime-limit representation; and no interpretation of these generic capabilities as a platform payment or settlement protocol. Companion interruption tests MUST cover declared stationary/local-basic fallback, current-state-only recovery without retrospective observation backfill, and separation from player-offline rules.

For autonomous decision levels, tests MUST cover player adjustment, context-based target selection under a higher-autonomy setting, clarification under a lower-autonomy setting, unchanged game capability/permission boundaries, and independent item-transfer and irreversible-action confirmations or prohibitions that remain enforced at every level.

Tests MUST additionally verify that the player's global decision-level selection persists across game changes, developer recommendations cannot replace it, and game-specific capability or permission constraints do not silently mutate that stored selection.

Risk-taking assistance tests MUST cover use of the global decision level without a separate protect-others switch, risk assessment and level-appropriate clarification, following an explicit player insistence within authority, and continued enforcement of game permissions and independent confirmation or prohibition rules.

For instruction supersession and target changes, tests MUST cover latest conflicting player instruction priority, blocking unsubmitted old-plan actions, game-originated relevant target-change notifications including a Boss death, reassessment of plan validity, conditional withdrawal requests, unavailable or unsuccessful withdrawal without false cancellation, and redecision without assuming already-issued skills can be recalled.

Action-status recovery tests MUST cover query by the original action ID after disconnection; distinct unknown, in-progress, succeeded and failed outcomes; missing/expired records remaining uncertain rather than failed; partial effects on failure; origin/scope authorization; no blind fresh-ID resend; and truthful retention bounds without exactly-once or indefinite-history claims. Tests MUST also cover game- or platform-provided persistent result records, separation of platform receipt logs from actual execution evidence, default non-execution and no automatic resend after unavailable or lost results, later independent decisions about similar new actions under current state, authority and autonomy level, executor-side persistent deduplication, explicit lack of duplicate-prevention guarantees after record loss or expiry, and continued enforcement of current game permissions and independent purchase/high-value/irreversible authority on new decisions.

For multiplayer memory, applicable tests MUST cover the owner's retention choice, later cross-game use within applicable permissions, and selection and application of sharing and non-sharing preferences. Tests MUST separately verify enforceable audience, retrieval and forwarding checks, truthful disclosure of soft-preference limitations and absence of absolute confidentiality claims. A model deviation from a correctly applied soft preference is not by itself an access-control conformance failure; bypassing an actual required data-permission check remains a conformance failure.

For first-version offline behavior, applicable tests MUST cover explicit departure, silent disconnection and bounded detection, Agent heartbeats unable to renew absent-player presence, queued-action cancellation and in-flight commit races, stopped gameplay inference loops, truthful residual usage, independent online multiplayer sessions, prevention of shared-role scope borrowing, and reconnection without stale-plan or backlog replay, including a new game entry that leaves the old task stopped until a new player instruction. No configuration or extension may enable offline world activity.

For gameplay-Agent admission, tests MUST demonstrate decisions from required structured inputs, rejection or explicit scope adjustment for unsupported required categories, and truthful capabilities. Advanced-Agent claims MUST additionally demonstrate interpretation of both game images and audio; test optional media absence, permission denial, incompatible formats and resource limits without losing the structured foundation. Transporting media alone is not multimodal acceptance.



First-version role tests MUST cover multiple players each having one companion, rejecting a second companion for the same player, authorized companion-to-companion interaction with owner/perspective isolation, one independent NPC/enemy per run, run-wide exclusivity of companion and NPC modes, concurrent admission/recovery, and fencing all old-mode bindings before switching. Ordinary non-G2A NPCs remain unaffected.

Role-integration tests MUST verify the required companion slot, optional absence or presence of an NPC slot, enforcement of the developer-fixed mode, and separation of advertised support from active role bindings. Advertising both slots MUST NOT bypass run-wide mode exclusivity.

Empty-companion-slot tests MUST demonstrate that a player can choose not to enable a companion and that normal gameplay remains available, without an active companion binding or an implied requirement to purchase or activate Agent service.

Companion-lifecycle tests MUST cover configured automatic-entry and entry-prompt paths, declining entry without losing manual summoning, manual summoning and dismissal during play in both configurations, enforcement of game mode and single-companion limits, valid admission, and truthful in-flight effect accounting. Tests MUST also verify stopped observations and autonomous actions after dismissal, preservation of retained memory, and truthful residual usage. Companion-service failure tests MUST verify game entry while the companion service is unavailable, later joining under the player's configuration and valid admission, uninterrupted game operation, paused companion actions, and no post-reconnection continuation without the player decision.

NPC service-failure tests MUST verify the declared developer-selected fallback and recovery policy, truthful script-versus-Agent attribution, and enforcement of existing role and authority limits.

Media-control tests MUST cover player-enabled and disabled game-image/audio perception, structured-only operation by an advanced Agent, unsupported game feeds, authority denial, and separation from voice-conversation controls.

Companion-style tests MUST distinguish developer advice and player-selected personality/speaking style, apply the player's selection when they conflict, and verify that style configuration does not widen information or action authority.

NPC-characterization tests MUST enforce developer-defined personality, background and speaking style, rejecting direct player-companion-style overrides without treating ordinary in-game dialogue as configuration authority.

Open-admission tests MUST apply the same minimum conformance criteria to first-party and independent Agents and reject arbitrary provider-based exclusions, preferred-vendor requirements or disguised vendor restrictions. Successful technical admission MUST remain distinct from player consent and operation-specific authority.

Enforcement tests MUST verify specific provider-facing reasons for actual violations, safe diagnostic detail, rejection of vague or vendor-based pretexts, and separation of repeated-refusal review from automatic guilt or an ecosystem-wide ban.

Reason-reporting tests MUST require both a shared machine-readable code and consistent, specific human-readable explanation, and verify that neither leaks hidden game facts, credentials or unauthorized personal data. Exact code values remain to be frozen; these semantics do not claim existing SDK support.

Portability tests MUST cover retained experiences and organized/consolidated memory, selected personality/style/global-autonomy settings, truthful unsupported/transformed-setting receipts, model-dependent expression without identical-personality claims, no promise to restore deleted originals, complete retained-memory export without silent omissions, open-format interpretation by an independent importer, player-initiated destination/scope selection, no default disclosure on provider change, metadata preservation and truthful partial/unsupported import results.

Memory-control tests MUST verify player viewing, editing and deletion, truthful status and provenance, subsequent retrieval/export reflecting completed edits or deletions, and no resurrection from provider-controlled stale indexes or caches.

Autonomous-memory tests MUST cover organization and original-record deletion without an imposed per-deletion approval step, truthful deletion accounting, preserved player controls and export of remaining memory without claiming deleted records are recoverable.

Budget tests MUST cover player-set caps, declared units/scopes, cap-triggered companion pause with continued gameplay, prevention of new chargeable work, metering delay/in-flight settlement disclosures, and no autonomous cap increase.

NPC billing tests MUST verify the owning-user payer binding (the room host in the current scenario), attributable usage disclosure and no implicit charge sharing with other interacting players.

NPC-owner presence tests MUST stop the AI NPC when its owner leaves even while other players remain, prevent silent continuation via host/billing reassignment, and truthfully account for detection and committed/in-flight effects. Companion-only implementations MUST remain valid without optional NPC capability.

Appearance tests MUST cover the game-style default, player override preference, truthful selected-versus-rendered appearance reporting, capability declarations and no false claim of compatibility or successful rendering.

Unsupported-appearance tests MUST verify a clear player-facing incompatibility notice and game-default fallback without silent substitution or a false custom-rendering success report.

Gameplay-rule tests MUST enforce the developer's applicable injury/death/action restrictions, distinguish them from service or authorization failures, and avoid inventing unavailable revival capabilities or overriding rules through companion preferences.

Death-isolation tests MUST verify that local gameplay death leaves cross-game companion identity and retained memories intact, while applicable local death restrictions remain enforced. Independently authorized memory changes MUST NOT be misreported as consequences of gameplay death.

## 19. Migration and implementation boundary

| Existing design or SDK concept | Standard treatment |
| --- | --- |
| Existing `game.context` category/content/provenance | Preserve wire meaning; negotiate typed observation content as a profile |
| Descriptor/Requested/Scope extensions | Keep support/proposal/frozen approval distinction |
| Active extension value | Frozen configuration; never use as a changing observation payload |
| Existing ActionResult | Preserve exact state/effect combinations and unknown reconciliation |
| Session active/closed plus ready | Preserve existing fields; do not invent incompatible states |
| Session event sequence | Recipient filtering may skip numbers; do not use as observation revision |
| Contexts in recovery snapshot | New profile requires materialized per-stream state, not stale delta replay |
| `core.session` feature catalogue labels | Reconcile with explicit role-by-capability applicability |
| Legacy operation-directory HTTP error mappings | Retain for legacy peers. The candidate g2a-http-json/draft-1 uses HTTP 200 for domain errors and 4xx/5xx for transport failures only when explicitly negotiated; this is a proposed binding change, not an unchanged mapping |
| SDK `0.1.0-dev` | Implementation under review, not a release of this specification |
| New observation candidate | Requires contract/schema, vectors, implementation and independent review |

The next standardization steps are to freeze exact profile fields and digest domains; generate a complete English field catalogue from all operation contracts; reconcile role applicability metadata; finalize binding authentication/status/header rules; add observation and cross-role conformance vectors; and run independent peers and real games. Only then should a stable release claim be considered. SDK adaptation follows the reviewed standard rather than defining it implicitly.

## 20. Illustrative scenarios

**Turn-based companion.** The game advertises visible board and legal-move definitions. The player grants advice only. The agent receives an authorized snapshot and may chat but cannot execute a move. Granting a typed move action later requires approval; the game still checks whose turn it is at execution.

**Proactive combat companion.** The player authorizes combat assistance within the game's declared capabilities. An authorized observation reveals nearby enemies; the companion selects targets and legal attacks, replans as the encounter changes and helps until the objective is met or a stopping condition applies, without asking before every attack. When the player says stop, it schedules no further attacks, reconciles in-flight work, and reports any hit already committed rather than promising to undo it.

**Fog-of-war tactical agent.** A view changes after a team switch. The authority retires the old visibility epoch, discards queued disclosure to the old audience and sends a fresh authorized snapshot. A delayed old delta is rejected even if its revision is numerically greater than the new stream's revision.

**Action timeout.** A purchase or move request reaches the game, commits, and the response is lost. The agent queries the original action and operation receipt. It does not resubmit with a new ID. If the authority cannot establish the result, it reports unknown and initiates reconciliation rather than claiming no effect.

**Disconnected companion.** The associated player leaves or the declared presence deadline expires. New gameplay planning and actions stop; queued work is cancelled and in-flight effects are reconciled without promising rollback or zero residual token billing. Other online players and ordinary game simulation may continue. Reconnection establishes current presence and authority, reconciles outcomes and refreshes state under section 7.1 before any further gameplay; the previous task stays stopped until the player gives a new instruction. There is no offline activity mode or backlog replay.

## 21. References

- A2A Protocol specification: https://a2a-protocol.org/latest/specification/ (mutable latest reference; architectural comparison only).
- RFC 2119 and RFC 8174: requirement terminology.
- RFC 8259: JSON data interchange.
- Existing G2A normative-candidate artifacts linked in section 1.

G2A follows the useful separation of canonical model, operations and bindings seen in A2A, while adding game authority, authorized observation perspectives, effect-boundary validation and game-specific uncertainty. It does not claim A2A wire compatibility or inherit A2A authorization semantics automatically.
