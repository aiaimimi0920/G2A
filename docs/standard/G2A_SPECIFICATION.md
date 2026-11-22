# G2A Specification

**Game-to-Agent Interaction Protocol**

Defining information, authorization and action boundaries among the game world, players and AI Agents playing Game Companions.

Status: Working Draft for Review. Editorial revision: `standard-review-2026-11-14-r71`. Revision date: November 14, 2026.
Baseline: `g2a-design-1`. Observation profile (a specified capability subset and its contracts) candidate: `observations-draft-1`.
This document does not assign a released wire version, certify an SDK, or claim production interoperability.

Language pair: this English master and the [complete Chinese translation](G2A_SPECIFICATION.zh-CN.md) share the same editorial revision. The [revision history](#section-25) records changes and their compatibility boundaries.

## Contents

1. [Purpose and scope](#section-1)
2. [Conventions and document authority](#section-2)
3. [Architecture and applicability](#section-3)
4. [Roles and trust](#section-4)
5. [Canonical model](#section-5)
6. [Abstract operation catalogue](#section-6)
7. [Discovery, negotiation and admission](#section-7)
8. [Grants, sessions and revocation](#section-8)
9. [Observation profile candidate](#section-9)
10. [Actions and effect semantics](#section-10)
11. [Idempotency, delivery and recovery](#section-11)
12. [Error model, time and limits](#section-12)
13. [Gameplay roles and integration requirements](#section-13)
14. [Presence and companion lifecycle](#section-14)
15. [Conversation, information use and companion memory](#section-15)
16. [Companion autonomy and player policies](#section-16)
17. [Optional profiles and extensions](#section-17)
18. [Candidate HTTP/JSON binding](#section-18)
19. [Security and privacy considerations](#section-19)
20. [Versioning and governance](#section-20)
21. [Conformance and acceptance](#section-21)
22. [Migration and implementation boundary](#section-22)
23. [Illustrative scenarios](#section-23)
24. [References](#section-24)
25. [Revision history](#section-25)

## How G2A works

In a typical two-character collaboration, developers build the game world and provide a player-character slot and a Game Companion slot. **The human player controls the player character; the Game Agent is authorized to play the Game Companion.** Developers define and expose companion capabilities, such as movement, attack and interaction. The Agent invokes these capabilities to request actions; the game determines whether they may execute under current rules and world state and adjudicates their actual effects.

```text
Developer: builds the game world; defines and provides companion capabilities.

Human player ──controls──▶ [Player character]
                                  ↕ communication
Game Agent ◀──── G2A ─────▶ [Game Companion]
 (decisions)                       ↕ perception / action
                          Game world and rules
                           (final adjudication)

Both character slots belong to the game world; the Agent is the decision-making agent.
```

The diagram shows three relationships: **player character ↔ Game Companion: communication; Game Companion ↔ game world: perception and action; Game Companion ↔ Game Agent: information and decision exchange through G2A.** This is a role-relationship diagram, not a network-deployment diagram. Through the designated Game Interaction Node, the Game Agent exchanges state, action requests and outcomes for the companion it plays; it cannot bypass that role to control the entire world. The companion’s interaction with the world remains subject to game rules and authorization.

The single-player, two-slot illustration shows the core relationships without limiting the world to two characters or a particular character form, or changing the rule that each multiplayer participant may have a companion. The **Game Agent** is a decision-making agent that may run locally or remotely; the **Game Companion** is its authorized in-game role carrier. They are not the same entity. Section 13 further defines composable information perspectives and the continuing role-count, active-mode and binding restrictions; composition does not expand authority, and final adjudication remains with the game.

<a id="section-1"></a>

## 1. Purpose and scope

G2A is an open interaction protocol connecting games and AI agents. It specifies how participants establish authorized connections, exchange game information, discover and invoke game capabilities, and reconcile action outcomes and interruptions. The game remains authoritative for its world state and executable rules; within those boundaries, players control their companions' preferences and authorization.

**Why a shared protocol?** Games provide different information and actions. G2A supplies common interaction rules for what a game provides to an Agent, how the Agent requests an action, and how the game reports its result. Games still define their own gameplay, and the protocol does not prescribe a single Agent model or implementation.

The specification is organized around four related concerns:

| Concern | What G2A specifies |
| --- | --- |
| Admission and control | Participant identity, role binding, admission, grants, session control and revocation |
| Observations and information use | Available and requested information, authorized perspectives, provenance, freshness, audiences and retention |
| Actions and outcomes | Capability definitions, authorized requests, game validation, execution, cancellation and result reconciliation |
| Interoperability and extensions | Shared models and operations, transport bindings, errors, versioning, profiles and conformance |

These concerns interact. Declared observation needs do not imply game support or permission to receive the information. The following distinctions apply across them:

- **Support is not authorization:** a capability only states what an implementation supports; a request only expresses caller intent. Neither automatically grants execution or read authority.
- **Acceptance is not completed execution:** accepting an action request does not establish its intended world effect. Acceptance, execution and effect completion MUST remain distinct.
- **Authorized reads do not imply continuing validity:** observations reflect a restricted perspective at a particular time or baseline and may become stale as the world evolves.
- **Omission is not non-existence:** information omitted through visibility limits, permission filtering or delta delivery MUST NOT be interpreted as a false fact or an empty world.
- **Companion memory and current world state are separate:** a reload, new playthrough or branch switch changes the current game state, but MUST NOT by itself erase retained companion memories. Developers MAY recommend how those memories are used or isolated; their recommendation applies when the player has not configured a choice, and an explicit player choice takes precedence. Remembering an earlier experience does not establish that it happened in the current world or override hard gameplay rules.

The scope is games: player-facing assistance, NPC collaboration, game-state observations, constrained actions, and optional in-game presentation. Model inference, model hosting, planning algorithms, memory products, commercial identity providers, engines, and a particular desktop companion are not prerequisites. G2A is not a general OS automation protocol. It does not standardize arbitrary remote code execution or grant access to game secrets by default.

The game designates a game interaction node for G2A. During active authorized interaction, the Game Agent uses that node to obtain current game state, request actions and query outcomes. State and action results published by the node are game facts within the interaction scope; G2A does not separately recompute the game’s internal hit, damage or anti-cheat decisions. The node may be implemented by a local game client or module, or by a remote service; no particular deployment is required. This source rule concerns only current game state and action outcomes, not the use of player instructions, companion memory or external knowledge. Those sources retain their provenance and must not be passed off as current game facts. Communication identity, authorization, message-format and state-consistency checks still apply. G2A cannot guarantee that a model will never infer or learn hidden facts from another source.

For a first reading, sections 3–4 explain responsibilities and cooperation, followed by sections 13–16 on companion behavior in games. Implementers can then use the data and operation details in sections 5–12. Open-provider admission and justified refusals are in section 7; versioning, release requirements and platform-governance boundaries are in section 20.

<a id="section-2"></a>

## 2. Conventions and document authority

The key words MUST, MUST NOT, REQUIRED, SHOULD, SHOULD NOT, and MAY are normative when capitalized, as described in RFC 2119 and RFC 8174 (BCP 14). They express requirements of this proposed standard, not claims about the current implementation. Explanatory prose, diagrams, illustrative examples and the revision history do not independently add requirements. A permission expressed by MAY does not require every implementation to offer the permitted feature.

**This draft and the existing definitions**

This English master, `G2A_SPECIFICATION.md`, is the primary semantic review reference. In the inherited `g2a-design-1` baseline, language-independent machine contracts are defined in [contracts.schema.json](../protocol/contracts.schema.json) and [operations.json](../protocol/operations.json); [contracts.py](../protocol/contracts.py) supplies corresponding Python reference type bindings. Existing state machines and processing rules from creation to termination are in [PROTOCOL.md](../protocol/PROTOCOL.md), [OPERATION_CONTRACT.md](../protocol/OPERATION_CONTRACT.md), and [STATE_TRACES.md](../protocol/STATE_TRACES.md). This draft adds observation semantics (`observations-draft-1`) and clarifies gameplay-role applicability and companion governance. Existing JSON being able to carry fields does not establish implementation or interoperability of those additions. Remaining discrepancies MUST be reconciled under section 20; the standard MUST NOT be inferred solely from reference bindings.

Within this review draft, explicit candidate changes describe the proposed target behavior, not a retroactive change to the inherited baseline. An implementation MUST identify which baseline and candidate profiles it implements; support for one MUST NOT be presented as conformance to the other. Unresolved wire encodings remain release blockers even when the intended behavior is specified.

Release-freezing and schema-validation requirements are collected in section 20. They remain normative; their placement there lets readers first follow the interaction model.

<a id="section-3"></a>

## 3. Architecture and applicability

Consider a companion helping a player attack a nearby enemy. The Game Agent obtains enemy information the companion is authorized to see from the designated Game Interaction Node, then requests an attack through that node. The game checks permissions, executes the attack and determines hits and damage under its own rules; the node returns the result. The Game Agent uses that result for subsequent decisions without seeking a second service to adjudicate the attack again.

This section explains **what the protocol defines and which parts each participant has to implement**. Not every participant has to implement every feature in the protocol.

**Three layers of the protocol**

1. **Data model: what information messages contain.** For example, how an action is identified and how its outcome is represented.
2. **Operations and behavior: what requests participants can make and what happens next.** Examples include submitting an action, querying its outcome, and handling its progression from start to finish. These beginnings, changes and endings are its “lifecycle.”
3. **Transport bindings: how messages are carried.** A binding maps the first two layers to a concrete communication mechanism.

Engine adapters and SDKs are tools for implementing these contracts, not the protocol itself. A different SDK MAY use a different code structure from the reference implementation while conforming to the protocol.

**First identify your responsibilities**

The table summarizes responsibilities; later sections provide the detailed rules. The same participant may have several responsibilities; the corresponding requirements apply together.

| Participant | Responsibilities |
| --- | --- |
| All participants | Establish identity, validate incoming input, follow the agreed version and applicable extension rules, protect confidential information, and report errors truthfully. |
| The game interaction node and the Game Agent | Handle admission, enforce granted scope, manage the G2A session from start to finish, process events, and recover interrupted requests where applicable. A session is the logical context for ongoing interaction, not the game program or room itself. |

A participant that actually retains data handles supported, authorized privacy requests for that data and reports the outcome truthfully. A participant that does not hold the relevant data does not thereby take on responsibility for processing another party’s data.

The Game Interaction Node and Game Agent handle their communication, user authorization and interaction state. Deployments may use existing network infrastructure, but this MUST NOT change message provenance, audience or authorization boundaries, or establish additional G2A core roles.

**Then identify the capabilities you use**

“Negotiated” means that participants have agreed to support and use a capability and its rules. A “profile” specifies the particular rules for a capability. When a capability is used, its participants take on the corresponding obligations:

| Capability in use | Responsibilities |
| --- | --- |
| Requesting and executing actions | The game validates requests, prevents duplicate execution, maintains action state and effects, and checks authorization for those effects. The Agent requests actions only within its grant; it reconciles unknown outcomes rather than blindly retrying operations that produce effects. |
| Delivering game information under an observation profile | Define streams and authorized perspectives; handle complete state within the authorized observation scope (baselines), epoch identifiers distinguishing generations or instances, expiry and withdrawal. |
| Durable recovery after an interruption | Apply the corresponding state-preservation, resume and handoff rules only when negotiated. |
| Chat | Specify the audience and source of messages and how they may be forwarded and retained. |
| Presentation or asset delivery | Manage only the negotiated rendering or resource lifecycle, including creation, use and termination. |

Chat, assets, presentation, active sensing and durable resume are not mandatory for all participants merely because this document defines them. Being optional does not permit an implementation to ignore their rules when it uses them.

Optional player-facing chat use does not waive the text/event contracts of an implementation claiming the inherited `g2a-design-1` `core.events` feature. The existing catalogue does not define a separate optional chat feature. Any future profile that separates those operation requirements MUST explicitly define and version that applicability mapping; it cannot silently change the inherited minimum.

Operation catalogue labels such as `core.session` group operations; they do not require every participant to implement every operation in that group. A release MUST publish which operations apply to each role when each feature is used.

### 3.1 Reading order and requirement applicability

For implementation responsibilities, the chapters can also be read as the following three layers. This chapter map does not replace section 3's model/operation/binding separation or change requirement applicability.

| Protocol layer | Sections | Core responsibilities | Applicability and implementation requirements |
| --- | --- | --- | --- |
| L1: Core interaction and state | 4–12 | Identity and trust, models, discovery, grants, observation synchronization, actions, idempotent recovery, errors and limits. | Games and Agents MUST follow core contracts applicable to their responsibilities and adopted capabilities; not every participant must implement every optional capability. |
| L2: Companion gameplay and policy | 13–16 | Roles and perspectives, presence, memory and spoiler choices, multiplayer confidentiality style, autonomy and confirmation. | Implementations offering companions or other applicable gameplay roles follow the corresponding role, hard game-rule and player-policy boundaries. |
| L3: Extension profiles and transport bindings | 17–18 | Optional stores, purchase budgets, appearance and the candidate HTTP/JSON binding. | Adopted as needed; participants MUST follow the applicable requirements of any adopted profile or binding. |

Use the following reading order, or go directly to the part you are implementing:

| Sections | Questions answered |
| --- | --- |
| 1–4 | What does G2A cover? Who participates, and what authority does each participant have? |
| 5–6 | Which data objects and operations does the protocol define? |
| 7–12 | How do participants connect, authorize access, exchange observations, perform actions and handle interruptions? These rules are independent of transport. |
| 13–16 | How does a game integrate companions or NPCs and handle presence, memory and autonomy? |
| 17 | Which rules apply when optional features such as stores or appearance are used? |
| 18–20 | How are messages transported, security protected, versions managed, and protocol rules separated from platform governance? |
| 21–25 | How are conformance and migration assessed, and where are examples, references and revision history? |

**A requirement applies because of a participant's responsibilities and the stated conditions, not because of its position in the document.** For example:

- A participating game has to provide the companion slot required by section 13.2, but a player may leave it empty.
- Companion requirements apply when the role or capability is used; independent AI NPC support remains optional.
- Optional features still follow applicable core, role, privacy and lifecycle rules.

The responsibility tables and each section's stated conditions determine applicability. Rearranging the reading order does not add or remove requirements.

This specification borrows A2A's separation of models, operations and transport bindings, not its wire format or operation names, and does not claim A2A compatibility. This document structure does not itself require new SDK code or additional transports.

<a id="section-4"></a>

## 4. Roles and trust

Section 3 explains the interaction; this section addresses communication identity and authority. The designated Game Interaction Node supplies state to the Game Agent, receives actions and returns outcomes. Participants still need to establish **who sent the request, which player they represent, and whether they may control this character**. These are protocol communication and authorization checks, not a second adjudication of the game’s internal decisions.

**Who is responsible for what**

Core interaction has two participants: the Game Interaction Node and the Game Agent. The game’s internal clients, servers and computation modules are not additional mandatory protocol roles. Launching a game, presenting appearances, transferring assets and retaining data do not each establish a new core role either.

| Name | Meaning and responsibility |
| --- | --- |
| Game Interaction Node | The game-designated G2A interface and authoritative source of game state and action outcomes for this interaction. It supplies current state, receives action requests and returns game-determined outcomes. It ensures applicable identity, authorization and protocol requirements are fulfilled; internal computation may be delegated to the game’s own modules. |
| Game Agent | A decision-making agent running locally or remotely. It obtains authorized state through the designated Game Interaction Node, requests actions for the role it is authorized to play, and uses returned outcomes for further decisions; it is not the game character itself. |

When an optional feature is used, its actual implementer takes on the corresponding obligations: launching a game requires explicit launch authority; supplying or receiving appearances or assets requires applicable authorization, format, provenance and lifecycle handling; retaining data requires privacy-request handling within the data actually controlled. These obligations do not require separate services or make unused features mandatory. Communication identity and authorization checks remain the responsibility of the participant processing the relevant request.

**The game interaction node is an external responsibility, not a mandatory additional server.** A single-player game may implement it in the local client or a module within it. An online game may also expose it through the client while cooperating with servers internally. Hits, damage, resource changes and anti-cheat are handled by the game. G2A does not prescribe that internal division or require the Agent to bypass the designated node and contact internal servers or validation modules.

**Game Authority**, in this document and inherited materials, denotes the game’s authority over its state and effects. In G2A interaction, the designated Game Interaction Node represents the game in providing those facts; it need not perform every internal computation itself. The Agent MUST NOT substitute its own guesses, conversational content or historical memory for current state and outcomes supplied by that node. The game still checks and executes actions under its rules; G2A does not add another adjudicator of game facts outside the game. Later references to the game side, execution side or authoritative executor describe processing and execution responsibilities of the game, not an additional node the Agent must connect to; those responsibilities are exposed through the designated game interaction node.

The current game or multiplayer room is managed separately from its G2A sessions. A session describes protocol interaction between game and Agent; closing it does not mean shutting down the game or room. Session establishment, closure, recovery and authorization remain governed by the later rules even when client and server responsibilities share a deployment.

In connection rules, an endpoint is a communication interface. The game-side endpoint is provided by the designated Game Interaction Node; its address establishes a connection rather than an additional component. The node may use internal game modules to fulfill request processing, validation or stopping responsibilities while remaining the interface that supplies state and results. Discovery, authentication, authorization and message transport remain governed by the relevant sections.

The Game Interaction Node and Game Agent enforce the user consent, policies and authorization limits applicable to the requests each handles. Assisting communication MUST NOT expand another participant’s authority.

The same participant MAY perform several responsibilities, but MUST keep their authority boundaries distinct. Retaining data does not itself grant control of the game.

**Establish who sent a request, rather than trusting who the message claims sent it**

Transport-authenticated identity MUST determine the caller. A `sender` field in the message body is content, not sufficient proof of sender identity.

The system MUST keep the following distinguishable rather than treating them as interchangeable:

- **Principal:** the identity being identified or authorized, such as a player or service identity.
- **Device:** the device from which the request originates.
- **Current game or room identity (instance):** identifies the particular game run or room to which a request belongs, keeping different runs and their authorization scopes distinct. This is a protocol identity, not a separately required deployment or a synonym for a client process.
- **Instance epoch:** a marker distinguishing generations under a running-game identity, so information from an older generation is not mistaken for current information.

A new instance epoch invalidates credentials or references bound to the old instance according to the negotiated profile. Also, joining a session does not grant permission to read every message in it.

**Acting for a player does not add privileges**

The system MUST distinguish the authenticated caller from the player it represents. Passing through other processing steps does not grant the player or companion additional authority.

Delegation is authorization for another party to do specified things on one's behalf. It MUST identify the applicable player, role, game/session and resource. Its granted scope and expiry MUST be preserved throughout any chain of delegation. Any party coordinating authorization or forwarding requests on another subject's behalf MUST NOT add its own privileges to that subject's authority.

A statement in game text, a message body or a forwarded instruction claiming delegation is not a verified delegation. Session IDs, action IDs and correlation IDs locate records; knowing an ID does not grant access or permission to act.

**Different verification modes do not provide the same guarantees**

The existing trust modes `local-verified`, `provider-verified` and `test-enrolled` MUST NOT be represented as equivalent. In particular, test enrollment helps development and testing; it is not proof of protection against arbitrary local software.

Implementations MUST truthfully disclose which participants can read communication content. If parties other than the two endpoints can read it, implementations MUST NOT claim that only those endpoints can decrypt it.

### 4.1 Information and action authority boundaries

Implementations MUST distinguish four kinds of permission:

1. Information the Agent may receive.
2. Information it may tell the player.
3. Information it may disclose to the game or another recipient.
4. Actions it may request or execute.

These permissions are not interchangeable. Knowing a fact does not authorize disclosing it or acting on it. Permission to discuss a memory with the player does not authorize sending its underlying conversation or memory to the game. Permission to request an action does not bypass game execution checks. These distinctions apply even when one process implements all roles.

**Some information may inform a decision without being disclosed.** A negotiated observation profile SHOULD distinguish:

- Data permitted in player-facing output.
- Protected inputs restricted to planning.
- Conditions evaluated inside the game. The Agent receives only an authorized result or reference, not access to the underlying facts.

Labels do not enforce restrictions. Where a grant restricts raw data to planning, implementations MUST enforce that restriction during retrieval, generation and forwarding, including derived representations covered by the grant, such as summaries. They MUST NOT claim that prompts alone guarantee isolation. The game MAY evaluate a hidden prerequisite internally and disclose only an authorized result or opaque reference, without the underlying fact.

These rules enforce actual protected-data grants; they do not turn developer spoiler recommendations into hard restrictions. Eligible player-controlled memories remain subject to the player's choices under section 15.2. This section neither requires a single model or planner architecture nor guarantees that a model cannot infer a secret.

<a id="section-5"></a>

## 5. Canonical model

**Technical terms**

These terms support the data, operation and connection rules below; they do not prescribe an equivalent set of separately deployed software components.

| Term | Meaning in this specification |
| --- | --- |
| Principal; Authentication | A principal is an identity being identified or authorized, such as a player or service; authentication verifies who the caller is, rather than approving a particular act. |
| Grant; Scope | A Grant records approved authority and its validity conditions; a Scope is the permission snapshot agreed and frozen by the participants. Being allowed to connect does not mean being allowed to read or control everything. |
| Delegation | Permission for another party to perform specific acts on one's behalf. The delegate cannot expand the authority granted by the delegator. |
| G2A Session | The logical context for ongoing protocol interaction between a game and an Agent, linking participants, grants and operation state. It is not the game program, nor is it merely a chat history or a network connection; it requires no separate service. |
| Capability; Operation | A capability describes a supported function; an operation is a callable protocol request, such as submitting an action or querying its outcome. Support does not itself authorize invocation. |
| Observation | Information the game is authorized to provide to an Agent. It is limited by perspective, authority and time, rather than being an omniscient copy of the world. |
| Observation Baseline; State Patch | An observation baseline is a complete state within one stream’s authorized observation scope; a patch describes changes relative to a specified baseline. Neither is the specification baseline identified at the beginning of this document. |
| Epoch / Generation; Cursor | An epoch or generation distinguishes stages of instance, world or control state; a cursor marks a position in an information stream. They help determine continuity and whether information belongs to older state, rather than serving as access credentials. |
| Event | Notification of a state change that has occurred and is visible to the recipient, such as an enemy's death. It is not an instruction asking the game to perform an action. |
| Action; Action ID | An action is a requested in-game behavior and its processing record; its ID correlates and locates that action for queries, rather than granting execution authority. |
| Action Outcome; Committed Effect | An action outcome describes the action's processing state and known effects, including partial effects; a committed effect is an actual change confirmed by the game. Submitting or accepting a request is not committing its effect. |
| Receipt | A queryable record of an operation's outcome. It helps reconcile what happened and does not confer additional authority. |
| Envelope | The outer structure carrying message content and information such as provenance, audience and correlation identifiers. It is not an additional kind of game behavior. |
| Provenance; Audience | Provenance describes where information comes from; audience identifies its intended and authorized recipients. Knowing its origin does not authorize forwarding it. |
| Lifecycle | The creation, use, changes and end of an object or interaction, such as establishing and then closing a session. |
| Negotiation; Profile | Negotiation establishes the functions and rules the parties will use together; a profile defines the specific rules for a function, rather than a player's personal settings. |
| Transport Binding | Rules mapping protocol messages and operations onto a concrete communication mechanism. This answers how messages travel, not what the game permits. |
| Schema; Conformance | A schema describes data formats and checkable constraints; conformance means meeting applicable protocol requirements. Passing format checks does not establish correct authority or game behavior. |
| Editorial Revision; Protocol Version; Specification Baseline | An editorial revision identifies document changes; a protocol version governs communication compatibility; the specification baseline is the inherited set of definitions. Updating the document does not itself release a new wire version. |

Each object has a distinct purpose:

| Object | Purpose |
| --- | --- |
| Descriptor | Advertises identity, supported versions, roles, capabilities and extensions. |
| Offer | Proposes an interaction. |
| Requested scope | Expresses the permissions being requested. |
| Grant | Records approved scope, its authority and lifetime. |
| Scope | Captures the negotiated, frozen permissions. |
| G2A Session (`Session`) | Associates participants, grants, readiness, control generation, leases and operation state. A lease limits how long control remains valid. |
| Envelope | Wraps a typed game or Agent message with scope context, provenance, audience, correlation and extensions. |
| Action | Records an action request and its outcome. |
| Event | Records a lifecycle change visible to its recipient. |
| Recovery Snapshot | Provides materialized authorized current state, rather than requiring the recipient to reconstruct it by replaying old messages. |
| Receipt | Records an operation result that can be queried again; it does not independently authorize an action. |

Unless their definitions say otherwise, identifiers MUST be opaque to consumers: a consumer cannot parse them to infer identity, permission or meaning. Correlation IDs, message IDs, operation IDs, event cursors and action IDs have different purposes and MUST NOT be substituted for each other.

The following invariants apply:

1. Effective authority MUST NOT exceed the intersection of current game capabilities, approved grant, session scope, membership, and current policy.
2. Consent MUST NOT be inferred from discovery or an established communication path.
3. A frozen scope MUST NOT be expanded by changing an active request.
4. Revocation MUST prevent further reads and effects within the revoked scope without erasing the accounting of committed effects. Reconciliation reads require independently valid read authority; they are not a revocation bypass or a promise of continuing access.
5. An admission or authorization check MUST be repeated at the authoritative effect boundary where state may have changed.
6. Duplicate delivery MUST NOT authorize duplicate effects.
7. An unknown result MUST NOT be reported as failure or success without evidence.
8. Audience checks MUST apply both when receiving protected content and when providing it to a recipient.
9. Untrusted game text, chat and asset content MUST remain data, never protocol authority.
10. Privacy receipts MUST describe actual completed work and exceptions, not aspirational deletion.

<a id="section-6"></a>

## 6. Abstract operation catalogue

The table focuses on abstract operations used for game interaction and declared gameplay-facing capabilities: what can be called, by whom, and with what guarantees. It does not prescribe a transport. Exact fields and the inherited baseline’s complete operation inventory remain in the linked machine contracts. This table does not redefine that complete baseline or claim that implementation-related operations omitted here have been removed from existing contracts. The specification scope and machine contracts MUST be reconciled under section 20 before a frozen release. A frozen publication MUST include an English field reference generated from the agreed contracts. An implementation takes on the operation requirements applicable to its roles and capabilities in use; the table does not require every participant to implement every operation.

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
| launch.request | Authorized game-launch capability | Launch only the approved target under launch authority |
| asset.resolve | Asset capability | Resolve scoped safe resources under retention rules |
| presentation.acquire | Presentation capability | Acquire bounded rendering authority/lease |
| presentation.renew | Presentation capability | Renew only eligible current authority |
| presentation.release | Presentation capability | Release rendering resources idempotently |
| privacy.request | Data subject | Ask the party actually retaining the relevant data to perform supported, authorized data handling |
| privacy.receipt | Data subject | Query the original request's actual processing status and retention exceptions; the caller does not write the receipt |


For the privacy operations, the party actually retaining the relevant data receives and processes the request and returns its actual status. The data subject invokes the query; a caller-supplied claim of deletion is not a receipt issued by the party that actually processed the data.

<a id="section-7"></a>

## 7. Discovery, negotiation and admission

**Open access for conforming providers**

G2A is open to conforming third-party Agents and model services; interoperability MUST NOT require an Agent or model service supplied by the protocol author's platform. Independent implementations MAY participate through the applicable declared roles, capabilities, authentication and negotiated contracts. Openness does not waive existing consent, data-access, action or resource requirements. A game MUST permit an Agent that meets the applicable G2A minimum standard to connect; the developer MUST NOT arbitrarily exclude it by provider identity, require a preferred vendor or use a closed provider allowlist to turn G2A into a proprietary ecosystem. The minimum standard and conformance evidence MUST be applied consistently to first-party and third-party Agents.

**Permission to connect is not permission to read data or act.** The same existing capability, authentication and authorization contracts still govern every participant and MUST NOT be used as a disguised provider restriction.

**Refusals need specific reasons**

A game MAY reject requests or disconnect an Agent for evidenced malicious behavior or actual violations of the applicable rules. It MUST communicate a standardized machine-readable reason code together with a clear, specific human-readable explanation to the Agent service provider, identifying the relevant rule and offending behavior with sufficient safe detail for diagnosis.

A frozen release MUST define the shared reason-code catalogue, stable meanings and payload schema so providers can interpret refusals consistently; free text alone is insufficient. A code does not replace the case-specific explanation, and the explanation MUST remain consistent with its code. A generic label such as "malicious", unsupported suspicion or provider identity alone is not an adequate reason.

Reasons and supporting details MUST respect protected data boundaries and MUST NOT disclose credentials, private information of others or hidden game facts; those boundaries are not an excuse to provide no meaningful explanation. Enforcement MUST address the actual behavior and MUST NOT disguise arbitrary exclusion of a conforming provider.

**Public and authenticated discovery differ**

The two discovery paths have different access requirements:

- **Public discovery:** an unauthenticated request MUST return only PublicDescriptor: instance, supported_versions, and discovery_endpoint.
- **Authenticated discovery:** full describe requires an authenticated Agent or player. It MUST filter the Descriptor for that principal before disclosing roles, capabilities, binding information, and extensions.

Neither path may expose secrets or unauthorized player state. After discovery, peers select a mutually supported version and profile set. Unsupported required extensions cause negotiation failure; optional unsupported extensions MAY be ignored only where their semantics permit safe omission.

**Propose, approve and join**

Either side MAY initiate an Offer through its authorized admission path. Offer creation freezes immutable_scope and scope_digest. Only the authenticated PlayerConsent path for the corresponding player may approve or reject that exact frozen scope through offer.decide; the decision_ref MUST verify the actual player interaction.

A previously approved automatic rule may approve during offer.create only under the baseline exact-match and no-launch conditions; it does not grant an agent access to offer.decide. An agent MUST NOT approve its own Offer.

Narrowing or otherwise changing a proposed scope requires a new Offer, a new scope_digest, and approval of that new proposal; offer.decide MUST NOT mutate the existing Offer in place.

An invitation is redeemed by its intended authenticated party; possession of an identifier alone does not create a broader principal. Joining requires valid admission and current authority. Launching is a separate permission: an interaction grant is not permission to start arbitrary processes.

**Where extensions belong**

Extensions use namespaced keys with `{version, required, value}`. Descriptor, Requested and Scope extensions carry support, proposed configuration and approved configuration respectively. Active Envelope extension configuration MUST exactly match the frozen Scope value where the baseline requires it. Dynamic observations belong in message content, not in a mutated configuration value. Data-plane outer OperationRequest extensions remain empty under the inherited contract; message extensions belong in the Envelope.

<a id="section-8"></a>

## 8. Grants, sessions and revocation

**What a grant records**

A Grant MUST identify its issuer, subject, game or instance applicability, permitted operations, scope, expiry and revocation relationship. Observation grants additionally bind catalogue schema and semantic digests, perspective, audience, frequency/volume limits, freshness and retention. Action grants bind action definitions and constraints. A change that broadens authority requires new approval, not merely a capability refresh.

**Session state and expiry**

The inherited Session state is `active` or `closed`, with readiness represented separately. This draft does not replace those fields with an incompatible new state enumeration. Session generation prevents stale control messages from operating on a newer control generation. Lease expiry prevents a missing participant from retaining indefinite active control. An authenticated fresh poll MAY renew a lease only where the baseline says so; replaying an old request or reading a snapshot MUST NOT accidentally renew it.

**Stop work when its permission ends**

Closing a session stops new work and initiates cleanup; it does not retroactively erase committed effects. Capability replacement, membership replacement and permission revocation MUST be ordered with affected reads, queued actions and effects. They MUST invalidate affected observation baselines and caches. Pending work that no longer has authority MUST NOT proceed. In-progress work MUST stop where possible; irreversible effects already committed MUST be reported truthfully. Handoff and durable resume are optional capabilities and require their specified generation, ownership, and recovery checks.

**Check every protected operation**

For every protected operation, including snapshots and action-result queries, the authority MUST check:

- whether the caller and applicable delegation match the intended resource, audience, subject, role, session and requested operation;
- whether that authority is currently expired or revoked.

Authentication success or a previously authorized connection MUST NOT substitute for these checks.

Credential forwarding or exchange MUST produce authority valid for the downstream recipient; implementations MUST NOT blindly pass an upstream credential to an unrelated recipient or accept a token intended for another resource. These requirements do not mandate OAuth, a central identity provider or a provider allowlist; a declared local trust mechanism MAY satisfy the same binding and validation requirements.

<a id="section-9"></a>

## 9. Observation profile candidate

### 9.1 Needs and definitions

An Agent MAY declare required observation categories and optional preferences. If the game cannot meet a required need, it MUST make that gap explicit during negotiation; it MUST NOT pretend the missing category is available. Declaring a need does not expand a grant. The game can decline the interaction or negotiate a degraded mode with the participant's agreement.

Each observation category definition MUST specify:

- Identification and validation: a stable identifier, schema version and digest, and semantic definition digest;
- Interpretation: units, identifiers used in the data, and coordinate/time conventions;
- Delivery: perspective policy, delivery modes, freshness, and rate/size limits;
- Access and retention: audience and retention requirements.

Schemas MUST define validation behavior, including unknown fields and size bounds. A JSON Schema format annotation alone is not mandatory format validation unless the chosen dialect/profile declares it so.

The candidate uses the existing `game.context` `content` field rather than introducing a separate set of core operations. Information is carried as follows:

| Information | Location |
| --- | --- |
| Supported observation categories | Descriptor extensions |
| Requested categories | Requested extensions |
| Agreed configuration | Scope extensions |
| Changing observation records | Context content |

Temporary examples use `org.example.g2a-observations`; this is an illustrative namespace, not a registered official identifier. There is no new core subscribe operation in this draft: existing context publishing, events and snapshots transport the negotiated profile. The selected category set is frozen until renegotiation.

**When candidate structures become binding**

Any machine-contract refinement MUST map to this content slot, the inherited operation envelopes and the existing stream/epoch/revision identities before being claimed interoperable. Candidate names such as ObservationCursor, ObservationEnvelope, TimelineCoordinate and ActionRequestEnvelope do not register new core objects or operations by themselves. Their normative source, exact types, applicability, references and compatibility rules must first be fixed under section 2; an unreferenced Schema definition does not constrain an operation.

### 9.2 Candidate content model

The following is an illustrative `Context.content` fragment, not a complete message or an assertion that the existing schema validates the observation semantics:

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

`declared-digest` is a placeholder, not a valid wire digest. For this illustration only, the two timestamps are UTC Unix-epoch milliseconds one second apart; production clock-domain, uncertainty and skew assumptions MUST be supplied by the negotiated profile or enclosing context under section 9.4. The instance/session binding, observation-category definition and authorization context are omitted here, not waived. This fragment is not a conformance vector and MUST NOT be copied as a production payload without those definitions and valid digests.

`mode` has three possible values:

- `snapshot`: the complete authorized view of the stream.
- `delta`: changes relative to a specified revision. It additionally has `base_revision` and MAY carry `records` and `remove_ids`.
- `retract`: withdrawal of information within a removal scope defined by the profile's exact schema.

Records have stable IDs within their declared epoch. Revisions are strictly increasing per stream epoch, but need not be contiguous. A numerical gap alone does not prove loss. A delta is applicable only if its base_revision exactly matches the consumer's current revision and its identity, schema, world, visibility and perspective context match.

**Identifying an observation**

An observation reference MUST retain its applicable instance epoch, stream, world epoch, visibility epoch and revision context. The perspective and applicable schema/semantic-definition identity MUST also be carried directly or resolved unambiguously through immutable stream/profile bindings. Revision numbers alone are not enough: a larger number from another context is not a newer valid observation.

If a negotiated profile defines a compact cursor, that cursor MUST map unambiguously to those identities and the exact delta base, rather than introduce a parallel ordering rule. A game tick or authority timestamp MAY provide timing context, but does not replace observation identity. Its clock domain, units, reset behavior and relation to the observation MUST be declared under section 9.4.

### 9.3 Baselines and visibility changes

A snapshot atomically replaces the entire authorized view of one stream, not all streams. It MUST NOT merge with stale omitted records. A delta is applied atomically only to its exact baseline. Duplicate updates with the same identity and content are idempotent; conflicting content for one revision is a protocol violation. An older update cannot roll back a newer view.

A declared state-sampling policy MAY coalesce intermediate current-state samples, but MUST preserve applicable baseline rules: dropping a delta needed by a later delta requires a new valid baseline rather than pretending the later delta applies. Receipt of the latest state is not evidence of a complete history.

**When a new baseline is needed**

World reset, grant change, perspective change, or audience/visibility change invalidates the affected baseline. The authority MUST issue an appropriate new world_epoch or visibility_epoch and a fresh authorized snapshot before deltas resume. A consumer MUST retire the old baseline immediately when informed of invalidation, even if replacement data has not arrived. Data previously visible must not remain usable merely because the next snapshot is delayed.

**Preventing withdrawn information from reappearing**

Retractions MUST be ordered with updates, authenticated, idempotent and scoped to the affected stream or records. The implementation MUST retain an invalidation record or equivalent barrier that prevents delayed or replayed old updates from restoring retracted information. Removal from the current view is not necessarily deletion from all historical storage; retention and privacy rules separately govern that storage.

**Out of view does not mean destroyed**

For entity appearance or removal, the profile MUST distinguish entry into view, observed creation, loss of visibility and authorized confirmation of destruction. Transition metadata belongs to the affected record or explicit record set, not implicitly to every record in a mixed update. Leaving view means the entity's subsequent state is unknown, not that it was destroyed. A receiver MUST NOT infer creation or destruction from an omitted record alone; when the cause cannot be disclosed or is not known, the authority MUST use an explicitly defined unknown/unavailable transition rather than invent a cause or reveal hidden state.

### 9.4 Freshness, recovery and information boundaries

**Determining whether information is still current**

Expired observations MUST be marked unavailable/stale and MUST NOT be presented as current.

Clock-skew assumptions MUST be declared by the binding/profile. Consumers MUST distinguish unknown, not observed, unavailable, explicitly absent, and known empty.

Denial responses MUST NOT reveal whether a hidden entity exists, its location, private objectives, or other unauthorized facts through payload or detailed errors. This is a transmission rule, not a claim of perfect timing-channel resistance or inability to infer facts.

Receipt time MUST NOT be represented as generation time. Freshness metadata MUST identify the timestamp's clock domain/epoch, units and applicable uncertainty. Timestamps from uncalibrated clock domains MUST NOT be directly subtracted to claim how old data is or which event came first.

Old data arriving out of order MUST NOT acquire the authority of a newer baseline; data after a loaded save or new epoch MUST NOT inherit the authority of the previous epoch's sequence.

**Recovering current state instead of replaying old deltas**

For this profile, a session recovery snapshot MUST contain the assembled, authorized current state of each stream, not an arbitrary replay of old context deltas. It MUST establish a valid complete baseline at the snapshot cut, preserving the authoritative stream identities and revisions. Reading a snapshot does not by itself require a new revision; any newly issued identity or revision MUST follow the profile's epoch and revision rules. A previously known stream absent from the current authorized snapshot becomes unavailable. Event sequence gaps can result from audience filtering; they MUST NOT be treated as observation revision gaps.

A recovery snapshot MAY materialize a state previously delivered as deltas. A different representation is not conflicting content if it denotes exactly the same authorized state at the same observation identity and revision. The profile MUST define that equivalence and the next applicable delta base; materialization MUST NOT change the state under an existing revision or make a stale delta applicable.

**Active sensing can be an action**

Active sensing that changes the world, consumes a game resource or creates a new game effect, such as invoking an inspection ability or revealing previously concealed map information, is an Action with independently authorized effects and resulting observations. Reading already-authorized information without such an effect is an information query under section 9.6. An Agent MUST NOT turn observation needs into a privileged inspection API.

**Keeping events, observations and actions distinct**

An event's identity and source, its ordering position, an observation's revision and an action's identity serve different purposes and MUST NOT be conflated. An applicable event binding MUST define stable identity and authenticated source, event type, schema version and correlation context; timestamps alone MUST NOT determine ordering or authorization. Event delivery does not imply that the Agent has observed an effect or that the referenced action succeeded. These envelope requirements do not require storing or replaying all disconnected gameplay under section 14.2.

### 9.5 Structured foundation and multimodal Agents

This protocol supports structured game information and optional visual/audio observations. Structured information is the foundation, not an optional alternative to media. A game-facing Agent admitted for gameplay assistance MUST be capable of interpreting the applicable baseline structured game information and using it to make gameplay decisions within its authorized role. An Agent that can only converse or inspect screenshots, but cannot use the negotiated structured foundation, does not meet this minimum gameplay-Agent capability. This requirement applies to Agents making gameplay decisions, not facilities that only transport network messages.

**Advanced capabilities build on the structured foundation**

An advanced Agent builds on that foundation and can additionally interpret both game images and game audio. Media support neither replaces the foundation nor grants access to a raw desktop, microphone or hidden game information.

Games MUST declare the structured categories and media capabilities they provide; Agents MUST truthfully declare supported schemas and media formats. Actual media delivery remains optional and requires compatible negotiated capabilities and applicable authorization, perspective, audience and resource constraints. A game without media can still support baseline structured interaction, including with an advanced Agent.

**Common meanings with game-specific extensions**

Structured information combines common definitions with game-specific extensions: G2A defines common formats for recurring game concepts, while game developers MAY declare extensions for special gameplay. Common definitions MUST retain their standardized meaning; extensions MUST be namespaced, versioned, schema-described and explicitly advertised/negotiated under the applicable rules, without silently redefining a common field.

Common fields standardize meaning and format, not universal availability.

A game is not required to provide a field that is inapplicable to its gameplay or not permitted for disclosure to the requesting role. The game MUST NOT fabricate missing data, fill it with misleading defaults, or expose protected information merely to satisfy a common schema. It MUST distinguish an unavailable or unsupported value from a known empty or false value, while respecting hidden-information error boundaries.

Required categories and fields for a particular interaction, optional data and unsupported special mechanics MUST be stated by the applicable profile and negotiated scope. If legitimately unavailable information is required for the proposed interaction, participants MUST refuse that interaction or explicitly agree on a supported scope instead of inventing data or bypassing disclosure authority.

**Verifying declared Agent capabilities**

The applicable gameplay profile MUST define the baseline structured categories and schemas; there is no assumed universal list of game facts. Admission MUST check the Agent's ability to interpret the required categories and use them for the intended decisions. Unmet required capabilities MUST lead to refusal or an explicitly agreed supported scope, not a false capability claim.

Conformance evidence MUST demonstrate structured-input decision behavior and, for an advanced capability claim, interpretation of both images and audio. A catalogue flag, payload transport, schema parsing or model name alone does not demonstrate those behavioral capabilities. Exact media encodings, capability identifiers and acceptance vectors remain to be standardized; this draft does not certify the existing SDK or any model as conforming.

**The player chooses whether to enable images and audio**

For an advanced Agent, the player decides whether to enable game-image and game-audio perception. The player MAY disable these media inputs and use only structured game information. Advanced capability is not a requirement to consume media.

Enabling media also requires the game's actually declared support and current authorization; a player preference cannot compel an unsupported or undisclosed media feed. Implementations MUST distinguish supported, requested and effectively enabled media capabilities, stop newly disabled media delivery/processing, and truthfully report unsupported requests. These controls govern game-environment perception, not player-companion voice conversation under section 15.5; disabling game audio does not by itself disable spoken communication.

### 9.6 Game push and Agent queries

G2A supports both game-initiated delivery of authorized observations and Agent-initiated queries for game information. The game developer declares which mechanisms the game provides, for which categories and under which limits. A game MAY support push, queries, or both; this specification does not require every game to implement both. An Agent MUST discover and negotiate the available mechanisms rather than assume either exists.

Push MUST respect the negotiated scope, perspective, audience, freshness and rate limits.

A query is a request for information, not permission to read it: the game MUST validate the caller, requested category and parameters against current authority, and return only permitted information with truthful availability and freshness semantics. Query support MUST NOT become a route to hidden state or bypass data-withdrawal rules.

Pure information queries MUST remain distinguishable from active sensing that changes the world, consumes a game resource or creates a new game effect; the latter remains an authorized Action under section 9.4. Both mechanisms remain subject to section 14.1's offline boundary and the agreed resource limits.

**State may be coalesced; events cannot be silently discarded**

A profile using push MUST distinguish replaceable state updates from discrete events. Coalescing MAY retain the latest replaceable value for a declared entity/property scope, but MUST preserve a valid materialized state or an applicable delta chain under section 9.3, including removals and invalidation barriers. An event representing a transient fact cannot be silently overwritten merely because a later state exists.

Within declared queue and retention limits, event delivery MUST preserve the declared ordering and duplicate-handling semantics. On overflow, the sender MUST report the applicable gap, resynchronization requirement or failure under section 12.

A fresh baseline restores current state, not lost transient events, and MUST NOT be described as a complete historical replay. This does not authorize retaining disconnected gameplay for later replay contrary to section 14.2.

This section establishes delivery/query semantics without adding an unregistered core operation. Existing context publishing and event delivery can carry push data; exact query capability definitions, schemas and operation mappings MUST be declared by the applicable negotiated profile before interoperability is claimed. Conformance tests MUST cover push-only, query-only and combined declarations, unsupported mechanisms, denied queries, stale results, and scope/frequency enforcement.

<a id="section-10"></a>

## 10. Actions and effect semantics

A Game Character Capability is an available behavior provided by the game for a character, such as movement, attack or interaction. A Game Agent may invoke it only within game rules and authorization. This is distinct from protocol capabilities declaring support for features such as chat or observations.

The game MUST declare capabilities by applicable gameplay role, including the action-definition identifier, parameter schema, result schema and execution constraints. An Agent requests a declared action; the game checks authenticated role and permissions, current game state and prerequisites, validates parameters, and executes or rejects the request itself through its trusted executor. The game MUST return the defined result and truthful effect status. A role declaration or an Agent proposal is not execution authority.

An action-definition identifier identifies an available behavior, not a particular invocation. In the inherited contract, `ActionRequest.payload.action` selects that definition; `ActionRequest.id` identifies the requested invocation, while the outer `OperationRequest.request_id` correlates the transport operation. These identifiers MUST NOT be substituted for one another.

**High-level actions and lower-level primitives**

The game developer chooses the granularity of exposed capabilities. A game MAY provide high-level semantic actions such as attacking a target, lower-level primitives such as movement, aiming or button input, or a combination of both. An Agent MAY compose the capabilities actually declared and authorized for its role to achieve an objective; it MUST NOT assume that an unadvertised higher-level action or lower-level input primitive exists. Neither level is mandatory for every game. Lower-level capabilities remain typed, scoped game actions with declared parameters, results and execution constraints, not permission for arbitrary OS input or unrestricted control. Composing several actions does not expand their authority or imply atomic execution of the whole sequence.

**What each action definition must specify**

Each action definition MUST specify typed input, target semantics, prerequisites, authorization scope, costs, confirmation requirements, cancellation behavior, effects and result schema. Games SHOULD expose semantic operations rather than unrestricted script evaluation. The game itself checks actions against current gameplay rules regardless of the Agent's planning confidence; G2A does not require another participant to repeat the game's internal adjudication.

Side effects, reversibility and idempotency MUST be declared as distinct properties where applicable; none may be inferred solely from a natural-language description, action verb or HTTP method. A safe/read-only declaration is not authorization, and an idempotent declaration MUST NOT override section 11’s default no-resend rule for an unresolved outcome.

**From request to game effect**

For a new invocation under the inherited baseline, the successful processing path is:

1. Select the action identity and proposed parameters; where required, obtain confirmation bound to that proposal before `action.request` is accepted.
2. Validate `action.request`, current authority and the exact proposal. Where confirmation is required, acceptance MUST validate and atomically consume it before creating `pending` work.
3. Have an authorized executor claim the eligible work.
4. Recheck applicable authority and preconditions at the effect boundary, then produce only permitted game effects.
5. Record the result and known effects, or preserve explicit uncertainty when the result cannot be established.

Not every action requires confirmation. `action.confirm` does not create an Action record, claim execution or produce a game effect; duplicate accepted requests follow the existing deduplication rules rather than consuming confirmation again. Claiming work prevents competing executors from owning it at the same time; it does not prove that permission is still valid when the effect takes place. Rejection, cancellation and recovery may end or interrupt this successful path according to the state machine below.

The final authorization check MUST be coordinated with revocation and the actual effect, so that revocation between a check and execution cannot be ignored. This requires an atomic game operation, a transactional journal, or an equivalent mechanism. Here, atomic means that the related steps complete as an indivisible whole. If atomicity cannot be guaranteed, the implementation MUST document which boundaries require reconciliation and MUST NOT claim exactly-once effects it cannot provide.

The inherited state/effect combinations are:

| State | Allowed effect status | Meaning |
| --- | --- | --- |
| pending | none | Not yet executing |
| executing | none, partial, committed, undetermined | Work underway; effect information may advance |
| succeeded | committed | Defined success effect is committed |
| failed | none, partial | Failure with explicit effect accounting |
| cancelled | none, partial | Cancellation completed, possibly after partial effects |
| unknown | undetermined | Authoritative outcome is not established |

`pending` may proceed to execution or settle without execution. `executing` may settle to success, failure, cancellation or unknown. Terminal known results MUST NOT be silently rewritten.

An unknown outcome may be reconciled only from authoritative evidence under the baseline settlement rules.

Cancellation is a request to stop, not a rollback guarantee. A cancellation racing with a committed effect MUST report the committed truth rather than fabricate cancellation.

A network timeout after submission is an unknown delivery/outcome condition. The caller MUST query or reconcile the original action/operation identity instead of submitting a fresh effect blindly.

Confirmation MUST bind the exact proposed action, principal, constraints, expiry and relevant generation; a confirmation for one action does not authorize a modified one.

**Supporting an action does not mean it can be executed now.** Capability definitions and currently legal actions MUST be separate. The game MUST provide a machine-readable way to determine current action eligibility within the authorized view, including applicable turn/phase, target or parameter constraints, resource requirements and cooldowns. This MAY use a bounded legal-action list, an action mask, declarative constraints or an authorized query; continuous or large action spaces need not be exhaustively enumerated.

Availability MUST identify the game-state context or revision to which it applies and MUST NOT reveal hidden targets or prerequisites. A declaration or previously legal action is not a reservation: the executor MUST revalidate current eligibility and authority at the effect boundary, returning a structured rejection or updated authorized constraints when stale. Agent adaptation MAY use these results but MUST NOT invent capabilities or bypass confirmation.

If feasibility, success probability or cost estimates are supplied, they MUST identify their source, applicable state and estimated nature. They are advisory evidence, not an execution guarantee or a substitute for current executor validation.

**Checking the information behind a decision**

Agent inference and network delay can leave the decision context behind the current world. Action requests SHOULD support an authorized observation-baseline reference and typed target-state preconditions. `based_on_observation_id` and `expected_world_revision` are illustrative candidate field names only; exact encodings and mappings to existing operations must be frozen under sections 2, 9.1, 20, not assumed to be existing core fields.

For observation-dependent actions, the applicable profile MUST define:

- how the request identifies the authorized observation context used for the decision;
- which freshness requirements or game-state preconditions are mandatory.

That association MUST preserve the stream, epoch and revision meaning of section 9, rather than treating a timestamp as a baseline.

When an age limit is provided, it MUST define units and authoritative evaluation, including how to handle uncalibrated or unavailable timing. Preconditions MUST be typed and use declared operators and authorized operands, not executable code or a hidden-state query bypass.

The executor MUST reject the affected action before new effects when a required context is invalid, a declared required age limit fails or a required precondition is false or cannot be established. It MUST distinguish stale context from a failed game prerequisite or unavailable evidence through the applicable structured error/result contract, without leaking hidden facts.

For example, if a healing target has died, changed allegiance or no longer meets a declared healing condition, the game MUST reject under the applicable condition rather than proceed merely because the action ID has not executed. The game SHOULD provide an authorized current summary with the rejection or update observations through a negotiated mechanism; deltas still require an exact baseline, and an authorized query may be indicated when push is unsupported. After rejection for stale state or a changed target, the Agent MUST NOT mechanically retry the original parameters and MUST reassess its intent using current authorized observations. Replanning does not waive section 11 reconciliation of an original action whose effects may already have occurred.

Passing these checks does not reserve future state or replace the coordinated effect-boundary check. If effects may already have occurred, the result MUST instead preserve the truthful partial or uncertain outcome under sections 10, 11, 16.

<a id="section-11"></a>

## 11. Idempotency, delivery and recovery

The binding carries a request_id for transport-operation recovery. The baseline also defines message, action, offer, and other domain identities. Implementations MUST use each operation's defined identity and digest domain; request_id is not a universal substitute for action deduplication.

For operation families that define deduplication, a repeated identity with the same canonical request MUST follow that family's receipt or recoverable-state rules. Reusing that identity for conflicting content MUST fail without applying the new content. The inherited [retry-family contract](../protocol/OPERATION_CONTRACT.md) defines different recovery rules for different operations; a transport request ID does not impose one common receipt ledger on all families.

Ordinary `read` operations MUST recheck authorization on each call and MAY return newer current state; they do not promise a frozen response or renew a lease. By contrast, lease-renewing operations such as `session.events` retain their declared nonce/replay rules even though they also return data.

Receipts MUST be retained for the advertised retry horizon. The request-processing participant MUST NOT silently turn an expired deduplication record into permission to repeat a non-idempotent effect. Where the outcome cannot be proven after expiry or failure, it MUST report an explicit reconciliation/unknown condition. Session generation, principal, instance epoch and authority bindings MUST be checked before disclosing recovered results.

Events are ordered within the defined recipient stream. A consumer applies each event once, tolerates duplicate delivery, and does not infer loss solely from noncontiguous session sequence numbers, which can reflect audience filtering. An expired or invalid cursor requires authorized snapshot recovery. Durable resume across processes is optional; safe retry and truthful uncertainty for supported operations are not optional.

Durable resume and recovery MUST comply with section 14.1: retaining state or retrieving a receipt does not authorize offline gameplay or replay of deferred effects.

### 11.1 Action identifiers and post-disconnection status queries

Every Agent game action MUST have an identifiable action ID bound to its authenticated origin and applicable game/session context. After a disconnected or uncertain response, the caller MUST query the original identity before deciding further action. Queries are read-only and MUST apply authorization; knowledge of an ID is not access authority. A binding MUST distinguish and correlate transport request IDs and domain action IDs without requiring a particular log custodian.

Queryable persistent result records MUST distinguish received/forwarded/accepted requests from actual execution and effects. A game or platform MAY hold the record; G2A MUST NOT require one exclusive platform.

The executor SHOULD durably retain deduplication identities and outcomes, and the profile MUST declare retention horizons and expiry behavior. A platform receipt alone cannot prove exactly-once game effects.

An authorized query MUST report the core state/effect matrix, including partial effects and cancellations, or explicit uncertainty. A known failure may include partial effects; missing, expired or uncorrelatable records MUST NOT be interpreted as failure or non-execution.

**No automatic resend when the result remains unknown**

When querying does not establish the original outcome, the caller MUST default to no re-execution or automatic resend of that action. This is a rule for subsequent behavior, not a claim that the original action did not execute. Neither an unknown record nor a retry hint grants permission to replay; changing the action ID MUST NOT bypass deduplication or this uncertainty. Records and IDs do not promise permanent retention or exactly-once effects. The implementation MUST truthfully report the unresolved outcome without requiring the player to respond to every transport failure.

**A later independent decision may initiate a new action**

A player or Agent MAY later make an independent decision to initiate a similar new action using current state, authority and the player's autonomy setting. This is not automatic retry: it MUST account for possible original effects and continue to satisfy purchase, high-value and irreversible-action policies. The original record remains unknown unless authoritative evidence reconciles it. A new decision MUST NOT rewrite it as success or failure.

<a id="section-12"></a>

## 12. Error model, time and limits

An error MUST distinguish malformed input, unsupported version/feature, unauthenticated caller, unauthorized scope, stale generation, state conflict, expiry, resource limit, temporary unavailability, and uncertain outcome where applicable. The frozen binding MUST assign exact stable codes to these classes; this review draft does not silently add unregistered codes to the existing machine contract.

| Error class | Caller behavior |
| --- | --- |
| Invalid request/schema | Correct input; do not repeat unchanged |
| Unsupported version/required extension | Negotiate a supported configuration or stop |
| Authentication/authorization | Obtain appropriate authority; do not probe hidden resources |
| Stale generation/baseline/cursor | Recover current authorized state before proceeding |
| Conflicting identity or state | Reconcile original request; do not invent a new effect identity |
| Rate/size/backpressure | Respect declared retry delay and limits |
| Temporary transport failure | Query the original result; retry only where the operation recovery contract permits, never automatically resend an unresolved game action |
| Outcome unknown | Query/reconcile; never equate timeout with no effect |

**Error details are subject to access restrictions**

Errors MUST NOT expose hidden object existence, private game state, tokens, stack traces or another participant's content. Error detail itself is an authorized disclosure.

Implementations MUST bound message bytes, nesting, collection size, queue depth, pending actions, polling rate and retention. Exceeding limits MUST NOT create partial unreported effects.

The implementation MUST make explicit its clocks, time units, maximum allowed skew and the party responsible for deciding expiry. A requester’s timestamp alone cannot extend a lease granted by its issuer.

Local timeout measurement SHOULD use a monotonic clock: one used to measure elapsed time without moving backward when the system date changes. A wall-clock adjustment, meaning a change to the system date and time, MUST NOT silently extend a lease or authorize stale work. A local monotonic timestamp is not a shared cross-machine clock.

Queue/backpressure limits MUST be enforced independently of autonomy level and token budget. Overflow MUST declare a gap, resynchronization requirement or explicit failure as appropriate.

Action receipts, revocations and visibility retractions MUST NOT be silently discarded as ordinary replaceable telemetry. Downsampling MUST NOT delay enforcement of known stop/revocation conditions or present stale observations as real-time. This does not require recording or replaying disconnected gameplay history.

**Recipients use error codes, not explanatory prose**

Errors MUST expose stable machine-readable categories and a correlation identifier for the occurrence or request, with safe human-readable explanation kept separate. An applicable binding MUST define how transport status, protocol rejection and game execution/effect outcome map without conflating them. Recipients MUST NOT parse prose to decide whether an action committed or a retry is safe.

Retry/deadline hints MUST state their scope and MUST NOT override section 11's unknown-outcome rules. Optional diagnostic detail MUST NOT reveal protected state or credentials; an explicit refusal can explain the applicable rule without disclosing the hidden fact that triggered it.

<a id="section-13"></a>

## 13. Gameplay roles and integration requirements

### 13.1 Composable gameplay roles and information perspectives

A Game Companion is a character accompanying the player in the game world; a Game Agent is the AI software that perceives and makes decisions for a character. They are not the same entity. A Game Agent may run locally or remotely and may play an authorized NPC, rather than only a companion. Shorthand such as a companion deciding or requesting an action refers to decisions made by the Game Agent playing it; the game still determines actual effects.

Two concepts need to remain distinct:

- **Role binding:** which game character the Agent currently plays, such as one player's companion or an NPC. This is not a software responsibility such as communication or message forwarding.
- **Information perspective:** which information that character is authorized to use, such as a companion's player perspective, an NPC's own knowledge, or a guide's tutorial knowledge.

An Agent implementation MAY support companion, NPC (including Boss), and guide perspectives. These information perspectives can be composed; this does not authorize arbitrary simultaneous active gameplay roles, nor require mutually exclusive companion-software and NPC-software implementation classes. The game MUST declare the applicable role bindings and information perspectives. The mode and active-role binding limits in section 13.2 still apply.

Each observation and action MUST remain associated with its authorized role, principal, audience and scope; combining roles MUST NOT implicitly union their permissions or expose one role's private knowledge through another.

An NPC or Boss MAY receive game-authorized internal knowledge unavailable to the player. A guide MAY receive game-authorized progression or tutorial knowledge. A player companion MAY also hold player-authorized memories from outside the current game. No role name by itself grants omniscience, permission to reveal knowledge, or authority to act. Switching or combining roles requires explicit applicable authority, and changes affecting an observation perspective invalidate its prior baseline as specified in section 9.

### 13.2 Active roles and role limits

A game run uses either player-companion mode or independent AI NPC/enemy mode; the two modes MUST NOT be active simultaneously within that run. In companion mode, each player MAY have one active companion, including in multiplayer. Multiple players' companions MAY coexist and interact within their respective authorization and the game's declared capabilities. This is at most one companion per player, not one companion for the entire multiplayer game. In independent NPC/enemy mode, the entire game run permits at most one active independent AI NPC/enemy, including a Boss.

Changing these limits requires a protocol revision; an implementation cannot relax them on its own.

The game MUST bind each companion to its authenticated owner, role, perspective and scope. Interactions between companions MUST preserve source identity, audience and each owner's authority; one companion's observations, memories or action permissions MUST NOT be implicitly shared with another. Another player's presence or consent does not authorize control of an absent player's companion. Sections 14.1, 15, 16.3 govern presence, disclosures and multiplayer interactions.

**Enforcing the limits.**

The game MUST identify the game-run boundary consistently and enforce mode exclusivity and the applicable per-player or run-wide limit during admission, replacement, handoff and recovery, including concurrent requests. Additional connections, Agent processes or combined role declarations MUST NOT bypass these constraints. Before switching mode, all active G2A gameplay-role bindings of the old mode MUST be retired or fenced; before replacing a companion or NPC, its previous active binding MUST be retired or fenced. Ordinary non-G2A NPCs and game simulation are neither counted nor stopped by these role limits.

The limits concern active gameplay roles, not retained memories or infrastructure process count.

**Required slots do not require player use.**

The game developer fixes the applicable gameplay mode; an Agent or player preference MUST NOT override that developer-defined mode. A participating game MUST provide a player-companion slot as its minimum role integration and MAY additionally provide an independent AI NPC/enemy slot. Providing a slot declares supported integration, not an active role or a requirement to activate both: optional NPC support MUST NOT be interpreted as permitting companion and NPC modes to coexist in a run. The game MUST distinguish supported slots, its developer-defined mode and currently active bindings in its declarations and enforce the limits above.

The player MAY leave the required companion slot empty and play without enabling a companion. The game MUST remain normally playable without a companion and MUST NOT require an active companion merely because it exposes this integration slot. Required support is not mandatory player use. Entry, summoning and dismissal follow section 14.2.

Player companions are the primary integration target of this specification. Independent AI NPC/enemy integration is a secondary optional capability; support for companions does not require implementing AI NPCs. For an independent AI NPC, its owning user's presence is the required liveness association under section 14.1. The presence of other players is not a substitute for that owner.

<a id="section-14"></a>

## 14. Presence and companion lifecycle

First distinguish who or what has stopped. Player departure, AI-service interruption, companion dismissal and a command to stop a task are different cases:

| Situation | Main handling rule |
| --- | --- |
| The player leaves or is determined offline | Stop associated G2A gameplay activity; on re-entry, the old task still awaits a new instruction. See section 14.1. |
| The player remains online but the AI service is interrupted | The game continues under the developer-declared local handling policy. After recovery, the player decides whether the companion continues. See section 14.2. |
| The player dismisses the companion | Stop observation and autonomous gameplay, without deleting memories merely because of dismissal. See section 14.2. |
| The player stops a task | Stop subsequent autonomous actions within that scope; already-issued actions follow game rules. See section 16.1. |

The clauses below separately govern stop conditions, in-flight outcomes and recovery. Stopping subsequent decisions does not undo game effects that have already occurred.

### 14.1 Stop gameplay activity when the player goes offline

G2A MUST NOT provide a mode in which an Agent continues acting in the game world after its associated player leaves or is determined offline. This is a mandatory restriction, not an option that an implementation can enable after leaving it disabled by default. Developer recommendations, player preferences, standing task authority, background workers and optional extensions MUST NOT enable offline continuation. Allowing this mode would require an explicit revision of the standard. Online autonomous assistance under sections 10, 16 remains supported.

**Determining when the player is offline.**

The Game Authority MUST define the authenticated player-session association and its liveness source, explicit exit signals, bounded detection timeout, and ownership of stop enforcement. Other components participating in liveness detection or stop enforcement MUST carry out these rules according to their responsibilities. Explicit player departure, session closure, or expiry of the applicable player-presence/control lease MUST end eligibility for new autonomous work in the affected scope. A disconnected endpoint MUST stop scheduling new gameplay work when it detects the loss; the authority MUST fence the affected control no later than the declared detection/lease deadline.

An Agent heartbeat alone MUST NOT assert that its player is still present or keep offline control alive. A silent network failure cannot be detected instantaneously; implementations MUST disclose detection delay and MUST NOT report a verified stop before its enforcement is established. Being online here means participating in the associated game session, not merely having an account logged into a platform; it does not require continuous keyboard input.

**What stops and what remains.**

Once a stop condition is known or stopping is enforced, the affected Agent MUST cease environment-monitoring and planning/inference loops for continued gameplay, and MUST NOT schedule new attacks, movement, dialogue, trades, purchases or other world actions. The game component responsible for final adjudication MUST block subsequent actions no longer authorized after stopping, cancel queued work not yet submitted to the game, and stop delegated planning or execution loops from producing new actions.

Skills or attacks already issued to the game complete naturally under game rules and need not be recalled merely because the companion stops; independently applicable game authorization and cancellation rules remain in force. Delegating a task to a game executor MUST NOT bypass this boundary. Effects committed before stopping takes effect, irreversible in-flight consequences and uncertain results MUST be accounted for truthfully; they are not automatically rolled back. This does not freeze the game world, undo already fired projectiles, or stop ordinary game simulation or non-G2A NPC logic.

**Multiplayer games and NPCs.**

In multiplayer games this rule applies to each affected authenticated player association and its scoped G2A activity; one player's departure is not evidence that every player is offline. Independently authorized sessions for other online players MAY continue. An independent NPC or game-governed guide MUST use its owning user as the required player-presence association. It MUST NOT borrow another player's presence or silently rebind authority to keep an absent owner's role active. No G2A world activity may continue without its qualifying online player association.

When the owning user (the room host in this scenario) leaves or is determined offline, the AI NPC MUST stop activity immediately upon that determination under section 14.1, even if other players remain online. This specification provides no continuation of that NPC on behalf of the absent owner. Other players being present, a room-host change or a billing reassignment MUST NOT silently keep that NPC active. Pending and in-flight effects remain subject to truthful stop/cancellation accounting; detection latency is not an offline-continuation mode.

Retaining authorized memories, receipts and recovery state is not active gameplay. Bounded non-gameplay cancellation, result settlement, reconciliation and persistence MAY finish without authorizing further world actions. Services MUST stop new gameplay model requests and request cancellation of in-flight model work where supported. This requirement aims to prevent continuing offline token consumption; the protocol cannot guarantee zero tokens or zero cost after a disconnect because detection, in-flight requests and provider cancellation/billing boundaries differ.

Implementations MUST disclose those limits and report actual or still-unknown usage, rather than promise an immediate zero-cost stop.

**Reconnecting does not resume an old task.**

Reconnection MUST establish current player presence, valid admission/grants, current control generation and an authorized fresh state before gameplay resumes. Durable resume preserves eligible state, not permission to act offline: it MUST NOT silently revive a closed session, replay an offline action backlog or continue a stale plan. After the player exits the game, the previous task MUST remain stopped on the next entry, even if it was previously approved. The companion MUST wait for a new player instruction before starting that task again.

Rejoining a companion slot or recovering state is not a new instruction to resume the old task; current admission and game authority still apply. Handoff between Agent processes does not waive these requirements. Exact presence fields, timeout bounds, stop receipts and recovery encodings remain to be frozen in the applicable contracts; this section adds semantic obligations, not new core states or operation names.

### 14.2 Companion joining, dismissal and service interruption

In companion mode, the player MUST be able to summon or dismiss the companion at any time during play. On entering the game, joining follows the player's own configured preference: automatic joining or a prompt asking whether to join. Both configurations MUST also allow manual summoning during play. Automatic joining uses the player's configured choice and valid admission; it MUST NOT bypass required authorization, the developer-fixed game mode or the per-player companion limit. Declining the entry prompt or starting with an empty slot MUST NOT remove the manual-summoning option.

The game MUST truthfully report transition state and any in-flight action outcome rather than imply that a visible disappearance rolls back committed effects.

After dismissal, the companion MUST stop observing the game and stop autonomous gameplay actions. Dismissal MUST NOT itself delete already retained memories; retention and privacy policy still apply. Services MUST stop new gameplay monitoring/planning requests and handle queued or in-flight work under the declared stop and cancellation semantics. Dismissal does not refund previously consumed tokens or guarantee zero residual cost in unrelated or already executing external services. Player-offline behavior remains governed by section 14.1.

If the companion service is unavailable when the player enters, the game MUST allow play without the companion rather than block game entry. The companion MAY join after the service becomes available under the player's configured joining choice and valid admission. Service availability alone does not resume an old task stopped by game exit under section 14.1.

**The player is online, but the AI service is unavailable.**

If the companion's AI service disconnects or becomes unavailable while the player remains in the game, the game MUST continue running, and the Game Agent driving the companion MUST pause observation, inference and autonomous action issuance. The developer MUST explicitly declare whether the companion character remains stationary or is taken over by local basic game behavior. Such local behavior MUST be identified as game-controlled rather than continuing Agent intelligence, and MUST obey game rules and current permissions. The game MUST distinguish this service interruption from player departure; player-offline restrictions remain governed by section 14.1.

Unsubmitted Agent actions MUST NOT be issued after interruption; already-issued actions and uncertain outcomes are handled under sections 11, 16.1 without automatic recall.

Recovery supplies the companion with the current authorized game state, not a recording or retrospective replay of the disconnected interval. The game MUST NOT record or reconstruct that interval for later backfilling of companion observation or memory. This restriction does not prohibit ordinary game saves or action receipts needed to reconcile previously authorized game effects; those records MUST NOT be repurposed as a gameplay-observation backlog. Using local fallback does not remove the requirement for the player to choose whether to resume companion activity, as described below.

**After service recovery.**

After the AI service reconnects, the player decides whether the companion continues. Reconnection alone MUST NOT automatically resume companion actions, replay queued gameplay or revive an old plan. Before continuation, the implementation MUST obtain the player's decision to continue, revalidate current authority and control generation, refresh authorized state and reconcile unresolved outcomes. The automatic-joining preference for entering a game is not permission to bypass this interruption-specific decision. If the player does not choose to continue, companion actions remain paused while the game continues.

For an independent AI NPC/enemy, including a Boss, the developer determines service-unavailability behavior according to the game: pausing, takeover by game-script logic or another declared handling policy. The game MUST declare the applicable fallback and recovery behavior and distinguish script-driven effects from Agent-driven effects. The companion-specific player continuation decision MUST NOT be imposed automatically on NPC recovery.

A fallback MUST NOT grant unavailable AI capabilities, bypass current permissions or claim AI-generated decisions when a script made them; ordinary script takeover does not authorize offline G2A activity under section 14.1.

The developer's interruption fallback MUST be defined for implementation, but G2A does not require a player-facing explanation of that fallback or a player choice between stationary and local-basic behavior. This is distinct from the existing player decision about whether the reconnected companion continues.

<a id="section-15"></a>

## 15. Conversation, information use and companion memory

This section separates three concerns: whether information may be retained or disclosed, how the player wants the companion to use memory, and how memories can be edited or migrated. The first involves enforceable data permissions; spoiler, topic and confidentiality-style choices may instead be soft conversational preferences. These are not interchangeable.

“Eligible memory” below means memory that the player may manage or use for the relevant purpose under applicable ownership, storage, retrieval, retention and disclosure permissions. This term creates no additional permission and does not require a game to release unauthorized data. Sections 15.1–15.4 specify the boundaries.

Chat is optional. A message MUST bind its actual source, intended audience and relevant consent. Player-forwarded speech MUST remain distinguishable from agent speech and game-authored text. Forwarding to another agent or service is a new disclosure and requires applicable authorization. A session-wide audience MUST NOT be assumed for a private message. The accepted audience is frozen, and current membership/authorization is checked again before delivery; a former member cannot retrieve newly protected content through replay.

Provenance MUST distinguish observed game facts, player assertions, agent inference and external sources. Content is not executable policy. An endpoint MUST NOT treat unverified chat content or a model-generated claim as a grant, confirmation, or authoritative action result. A player instruction conveyed through chat or voice acquires control authority only through the applicable authenticated player-control or consent path; the content alone is insufficient.

Retention limits apply to stored content and derived representations under the participant's control, including caches and searchable memory where the agreed policy covers them. Privacy requests MUST describe scope and identity. A receipt MUST distinguish completed deletion, retained legally/technically required records, unsupported destinations and pending work. Participants MUST NOT claim to erase data from an independent recipient they cannot control.

### 15.1 Memory ownership and cross-playthrough behavior

The game decides whether its NPC and guide roles preserve, reset, or selectively carry their game-governed memory across playthroughs. It MUST declare that policy, the applicable game/world/playthrough identity, and the intended scope of retained state. A new playthrough MUST NOT accidentally inherit a previous role's restricted memory because an implementation reused a cache. Persistent fictional identity is not by itself permission to retain all prior information.

Player-controlled companion memory is handled separately from game-governed NPC or guide memory. A companion MAY maintain cloud-hosted conversation and scene memories across games, subject to the player's controls over saving, retrieval, use and deletion and applicable privacy obligations. Cloud storage is permitted, not required. The player MUST be able to decide whether eligible companion conversations are saved and whether saved memories are used in the current interaction. A game's session closure or new playthrough MUST NOT silently delete or disable unrelated player-controlled companion memory.

Game authority over newly supplied game data, protected NPC/guide state, third-party disclosures and in-game effects remains intact. Player control of companion memory does not authorize extracting hidden game data, copying restricted game-provided state into an unrestricted memory store, or disclosing another person's data without applicable authority. Conversely, a developer's conversational recommendation MUST NOT be treated as authority over unrelated player-controlled memory.

Implementations MUST preserve provenance and distinguish an enforceable data grant from an advisory conversation preference rather than describing both as one undifferentiated retention policy.

### 15.2 Developer recommendations and player override

For eligible player-controlled companion memory and conversation, developers MAY recommend retention, cross-playthrough or cross-game use, spoiler disclosure, and topic preferences. These recommendations also cover eligible multiplayer memories under section 15.4; they MUST NOT be silently recast as mandatory developer retention or cross-game prohibitions. These recommendations MUST be identified as advisory and distinguishable from the game's enforceable data-access and action constraints. The player MAY override those recommendations, including requesting discussion of already legitimately available memories from another game or playthrough.

The implementation MUST honor that choice for eligible player-controlled conversation without treating it as expanded access to game data or permission to act in the game.

A player override does not force the game to provide undisclosed facts and does not waive another data subject's rights or a protected data grant. The game MAY continue to withhold its own protected information and reject unauthorized actions. The companion MUST NOT silently send cross-game memories or private conversation to the current game merely because they were used to answer the player. If discussion requires new game data, the ordinary game authorization checks still apply.

#### 15.2.1 Reloaded saves, prior branches and spoiler choices

For a player companion, retaining memories, using them in decisions and disclosing their contents to the player are separately controlled. A save reload, new playthrough or branch switch MUST NOT by itself erase retained companion memories. Developers MAY recommend a default for memory use or isolation; that recommendation applies when the player has not configured a choice, and an explicit player choice MUST take precedence. If the player chooses to retain and use all existing memories, the developer MUST NOT prohibit their use merely because they originate in an earlier playthrough, before a reload or on another branch. All existing memories means records that still exist and that the player is authorized to retain and use; it excludes deleted or never-saved records and does not expand access to protected data.

Permission to use those memories does not automatically authorize revealing every remembered event. The companion MUST separately apply the player's spoiler preference to what it says: where the player allows such discussion it MAY discuss a twist experienced before the reload; where the player does not want spoilers it MUST apply that preference and avoid proactively revealing the twist. These conversational controls remain soft preferences with the truthful limitations of section 15.3; they are not an absolute spoiler-prevention guarantee.

The game remains authoritative over the actual current world and save state. A remembered event from an earlier branch MUST retain its provenance and MUST NOT be presented as proof that the event occurred or remains true in the current branch. Using prior experience does not grant hidden current-state information or override current action permissions. A developer's recommendation or a game reload MUST NOT force deletion of eligible player-controlled companion memories. The player's own authorized memory controls and applicable enforceable data permissions remain separate.

Where save reloads or narrative branches are supported, the applicable profile MUST define the playthrough, branch and checkpoint context of authoritative current state, associate retained experiences with their known timeline provenance, and define branch ancestry or an equivalent unambiguous relationship if policy depends on it. Missing historical coordinates MUST remain explicitly unknown or unavailable rather than be fabricated. Their absence does not prohibit otherwise authorized import or retention of memory, but that memory MUST NOT establish current-state truth or satisfy a prerequisite requiring those missing coordinates.

A rollback notification MUST distinguish the authoritative new world context from a developer's recommended memory policy and the player's effective choices. Retrieval isolation MUST follow the effective player choice: corresponding prior-branch records MAY be excluded from retrieval only when the player selects isolation, or has not configured a choice and the developer recommends it by default; the records MUST NOT be deleted. When the player explicitly chooses to use all existing memories, isolation based solely on their earlier timeline provenance MUST cease, while provenance labels and applicable data permissions remain in force. It MUST NOT promise restoration of records already deleted or never retained. Exact coordinate fields and notification mappings remain subject to section 2; this paragraph does not register a `timeline.rollback` operation.

**Timeline metadata and retrieval isolation.**

A game supporting these timeline capabilities SHOULD expose playthrough, branch and checkpoint identifiers in session context and observation baselines. The candidate names `playthrough_id`, `branch_id`, `timeline_cursor` and `save_epoch` MUST retain distinct meanings: a narrative-position cursor may return to an earlier position on reload; a generation identifying the new load MUST NOT go backward or be reused, and a monotonically counted generation MUST increase on each load. They do not replace section 9 observation identity, and cursors across branches MUST NOT be compared without provenance and ancestry. Exact fields remain subject to profile freezing.

When persisting corresponding experiences or conversation summaries, the Agent MUST bind known playthrough, branch, checkpoint and load-generation provenance metadata. Missing values MUST remain explicitly unknown, not fabricated or replaced by import time. Derived summaries MUST preserve available provenance and MUST NOT bypass retrieval isolation through summarization.

When the player selects strict timeline retrieval isolation, the Agent MUST filter relevant memories and derived representations before constructing inference context if they are after the current checkpoint, outside the active branch and permitted ancestry, or lack sufficient provenance to establish eligibility. Merely prompting the model to pretend not to know is insufficient. Where prior-branch use is allowed, those memories MAY be retrieved under applicable authority but MUST be labeled as prior attempts or branch experience in context rather than current facts. Choosing not to disclose spoilers does not automatically prohibit internal use of prior memories; the choices remain independent and the effective retrieval policy MUST be exposed. Unsupported isolation MUST be disclosed rather than claimed enforced.

Retrieval isolation is not forced deletion and does not guarantee removal of knowledge from existing model context, parameters or external sources. Section 15.3's truthful limitations and the player-override rules continue to apply.

### 15.3 Enforceable scope and truthful limitations

Memory implementations MUST distinguish enforceable storage, retrieval and disclosure permissions from soft conversational preferences. They MUST enforce applicable data permissions under their control, apply selected conversational preferences through declared mechanisms such as prompting, and report the actual scope and limitations of each. Applying a soft preference does not guarantee that every generated response complies. Disabling retrieval or deleting a controlled record is not proof that a model has forgotten a fact.

Neither developer recommendations nor player settings justify promising absolute spoiler prevention, erasure of model parameters, or erasure at an independent recipient. The exact interoperable memory-policy encoding remains a profile design matter; the authority and override rules in this section are part of this specification now, not deferred policy decisions.

### 15.4 Multiplayer memory and player-configured confidentiality style

A companion MAY retain its conversations with other players as long-term memory, including for later interactions across games, within applicable storage and retrieval permissions. The companion's owner MUST be able to choose whether eligible conversations are retained and configure its conversational confidentiality style: for example, prefer not to share other people's conversations with other recipients, or allow such sharing. Retention, later use and outward sharing are separate choices; saving a conversation does not by itself select a sharing preference or expand data permissions.

Confidentiality style is a soft behavioral preference, not a guaranteed confidentiality mechanism. An implementation MAY use prompting or equivalent model guidance. It MUST apply the player's selected preference and accurately disclose that generated responses may depart from it. Occasional model output beyond that soft preference is a permitted limitation of this profile, not by itself evidence that the preference was never applied. Implementations MUST NOT promise one-hundred-percent confidentiality or describe prompting alone as enforced access control.

The owner's sharing preference governs eligible companion conversation; developer recommendations remain advisory under section 15.2. It does not grant access to another player's private records or override game- or service-enforced audience, storage, retrieval, forwarding or disclosure permissions. Explicit forwarding of protected messages and retrieval of protected memory remain subject to those permissions. The permitted limitation on model behavior does not excuse bypassing these checks or expanding a frozen audience. Implementations MUST distinguish enforceable data boundaries from soft conversational preferences.

This section adds neither universal per-message approval nor guaranteed model silence.

Exact profile encoding remains to be defined. The long-term-memory choice and soft-confidentiality semantics above are established review-draft decisions, not open questions about whether such behavior is allowed.

### 15.5 Text and voice interaction

This specification supports both text and voice for player-companion communication. Implementations MUST declare the input/output modalities actually available and negotiate compatible supported channels without representing an unavailable channel as usable. Text and voice interactions MUST preserve the same authenticated source, intended audience, authorization and retention boundaries.

Speech recognition or synthesis MAY be provided by an authorized component outside the Agent model; the implementation MUST distinguish original speech, its transcription and synthesized output where relevant to provenance, and MUST NOT present uncertain recognition as a verified player instruction.

Voice conversation is distinct from interpreting game-environment audio under section 9.5. A companion can converse through speech recognition and synthesis while making decisions from structured game data; this does not by itself qualify it as an advanced Agent that understands game images and audio. Conversely, environment-audio capability does not establish support for player speech input or spoken replies. Each capability MUST be declared and tested separately.

The applicable profile MUST define exact text/voice encodings, supported directions, errors and modality transitions; this section does not add a new unregistered core operation or certify current voice implementation.

### 15.6 Companion preferences and NPC characterization

A developer MAY recommend a player companion's personality and speaking style for the game. The player's companion settings take precedence over conflicting developer recommendations. Implementations MUST distinguish the recommendation from the player's selected settings and apply the latter within supported capabilities. Personality or style selection does not expand observation access, disclosure authority, action permissions or game-role limits, and MUST NOT be treated as a guarantee that model output always matches the requested style.

For an independent AI NPC/enemy, including a Boss, personality, background and speaking style are determined by the game developer. The player MUST NOT directly override those character settings as they can their own companion settings. Implementations MUST keep NPC characterization authority separate from player-companion preferences; conversational content or a companion configuration change does not authorize rewriting an NPC character.

### 15.7 Player-initiated companion-memory portability

**Player controls and autonomous maintenance.**

The provider MUST allow the player to view, modify and delete the companion long-term memory retained for them. The interface MUST identify the selected memory and scope, preserve truthful provenance of player edits and report whether a change or deletion is complete, pending or limited. Subsequent retrieval and exports MUST respect completed changes and deletions, including affected provider-controlled indexes/caches; a retained obsolete representation MUST NOT silently restore a deleted memory or override an edit. Existing privacy-receipt obligations apply to technical/legal exceptions.

Deleting stored memory does not guarantee model unlearning or deletion from independent recipients; limitations MUST be disclosed. The companion MAY autonomously organize retained memories, for example by categorizing, indexing or linking them. Organization MUST preserve applicable ownership, provenance, access and retention constraints and MUST NOT override player edits or restore deleted content.

The companion MAY also autonomously delete original memory records; this capability is not limited to reorganization or derived indexes. The protocol MUST NOT impose per-deletion player approval on this authorized autonomous behavior. Applicable ownership, access and retention constraints still apply, and deletions MUST have truthful scope/status accounting and MUST NOT be silently reversed through stale caches. The player retains the ability to view, modify and delete the remaining long-term memory. Complete export covers the memory actually retained at export time; it does not promise recovery of records already deleted under this policy.

**Memory meaning and provenance.**

Memory metadata MUST distinguish the time a record was stored or imported from the time/context of the event it describes when known; unknown times MUST remain unknown. A later import timestamp MUST NOT by itself supersede an earlier player correction or establish current game truth. Contradictory retained claims without a supported revision relationship MUST remain distinguishable rather than silently collapsed into a fabricated certainty. Retrieval with no matching evidence MUST NOT be represented as evidence that an event never happened.

Retained memory MUST distinguish direct observations, player statements, derived summaries or inferences, and future intentions where those distinctions affect interpretation. A derived memory MUST preserve available provenance and indicate transformations or missing source records; it MUST NOT silently turn inference into an observed fact or a plan into an executed event. Source deletion remains permitted under this section: provenance may identify a deleted source without retaining or reconstructing its content.

Importers MUST preserve these distinctions and applicable corrections/deletions rather than treating every imported statement as current authoritative game state. Player edits MUST be marked as revisions attributable to the player rather than original observations; model-derived revisions MUST identify their derived nature and available source/revision relationships. A source-unavailable marker MAY replace a reference to deleted content, without requiring permanent raw memory or an undeletable provenance graph.

**Export scope and migration.**

An Agent service provider MUST offer complete export of the companion memory it retains for the player. Export MUST NOT be limited to a provider-selected summary while silently excluding retained memory records. It MUST include retained memory content and the metadata needed to interpret it, including applicable provenance, game/run context, timestamps, scope, associations, permissions and retention constraints. Complete export refers to retained companion memory, not reconstruction of data never retained or disclosure of unrelated provider secrets.

Any unavailable or legally/technically restricted item MUST be identified with a truthful limitation report rather than represented as exported; protected information MUST remain subject to applicable disclosure authority.

The portable memory core MUST include the experiences and organized, summarized or otherwise consolidated memories actually retained at export time. A provider MUST NOT treat organized memory as a reason to exclude that retained content, nor promise reconstruction of original records already deleted. The player MUST also be able to include the companion's retained personality preferences, expression/speaking style and global autonomy-level setting in the export and migration scope. These are player-selected preferences, not model weights or a promise to reproduce a model's personality.

The receiving provider MUST preserve supported selected settings and truthfully report unsupported or transformed settings; exporting them alone is not proof they were applied. Differences in model implementation may produce different personality expression and behavior after migration, and such differences are acceptable without an identical-behavior guarantee. This limitation does not excuse dropping retained memories, silently resetting supported preferences or falsely reporting an import as complete.

Migration MUST be initiated by the player. The player chooses the destination provider and the subset of exported memory to import. Changing providers or establishing a new Agent session MUST NOT automatically disclose memory to that provider. The exporter and importer MUST preserve the authorized import scope and relevant provenance/permission metadata; import MUST NOT imply broader permission to disclose memories to games or other recipients. A provider MUST NOT use proprietary-only serialization to prevent cross-provider portability.

**Interoperable format and review material.**

A frozen portability profile MUST define an open, versioned export format and manifest, interoperable content and metadata representations, scope-selection semantics, integrity checks, unsupported-record handling and truthful import receipts. The manifest MUST account for selected scope, retained and unsupported items, transformations and information loss; silently omitting selected retained content MUST NOT be reported as complete migration. The importer MUST report which selected records were imported, rejected, transformed or remain unresolved; receiving an archive is not proof that its contents became usable memory.

Export/import does not guarantee identical model behavior, perfect recall or transfer of a model's internal weights. Exact fields and mappings remain to be standardized; this section establishes required portability without claiming that the current SDK or providers already implement it.

Safe unknown extension data MAY be preserved unchanged for later export but MUST NOT be executed or treated as authority. Untrusted imported content MUST remain isolated as data, and authentication credentials MUST NOT be included in memory exports. Provenance and portability do not require JSON-LD, RDF or a complete PROV implementation.

A separate, non-frozen memory portability candidate is available in the source repository at `docs/standard/memory-portability-draft-1/` (English and Chinese README, JSON Schema and 20 test vectors). Local contract/vector checks do not establish independent interoperability, SDK implementation, certification or release conformance. This is supporting review material, not a replacement for this draft's normative authority.

<a id="section-16"></a>

## 16. Companion autonomy and player policies

Autonomy answers how much the companion may decide within an already authorized activity, not whether it has authority to perform that activity. Read task authorization, decision level, resource caps and independent confirmation settings for transfers or irreversible actions separately. A higher decision level does not automatically remove the other limits.

### 16.1 Autonomous task execution and proactive assistance

While the associated player is online under section 14.1, a player MAY authorize a companion to pursue a task through completion or to provide ongoing assistance within a defined scope. Under that authority, the companion MAY observe its authorized environment, decide what to do, select and sequence declared actions, and adapt its plan to game results without seeking confirmation for every step. Proactive assistance MAY be triggered by authorized observations rather than a new player command: for example, a companion authorized to assist in combat may detect nearby enemies and help fight automatically.

Autonomy is not limited to carrying out a fixed player-supplied sequence.

An autonomous assignment MUST have an identifiable objective or ongoing-assistance purpose, applicable role and action scope, resource constraints where relevant, and completion or stopping conditions. The companion MUST distinguish a completed objective from an accepted individual action, blocked progress, failure, cancellation and an unresolved outcome. It MUST NOT report task completion solely because it submitted its planned actions. A task may require multiple core Actions; this section does not replace their state/effect model or introduce a new core task operation.

Multi-step objective completion MUST be supported by evidence that the declared objective is satisfied; a plan text, predicted success or acceptance of one step MUST NOT stand in for that evidence.

Existing task-level or standing authorization MAY cover multiple ordinary game actions. This specification does not impose per-step player confirmation on actions already covered by that authority. Where a particular action requires separate confirmation, that requirement still applies. Expanding the authorized scope requires the applicable new approval; a self-generated plan cannot expand it. Autonomy does not authorize hidden game data, unavailable capabilities, forbidden game actions, unrestricted resource use, or purchases merely because they would help complete a task. Store purchases remain subject to section 17.1.

The player MUST be able to adjust or stop the companion's autonomous assistance. On receipt of a valid stop or narrowing instruction, the companion MUST stop scheduling and issuing newly disallowed subsequent actions and prevent affected queued actions not yet submitted to the game from being issued. Skills or attacks already issued to the game complete naturally under game rules; the player's stop alone does not require their cancellation, recall or reversal. The companion MUST reconcile unresolved outcomes truthfully and MUST NOT represent cessation of further decisions as cancellation of already-issued actions.

The game MUST distinguish unsubmitted companion plans from actions already handed to game execution and enforce game rules at the applicable authorization and effect boundaries. Implementations MUST report whether stopping is pending or effective and any actions already committed or only partially cancelled. A stop does not undo an attack, spent resource or other effect that has already occurred; rollback requires an explicitly supported compensating action and its own authority.

Loss of connection MUST NOT be represented as proof that all work stopped; section 14.1 requires bounded detection and enforced stopping, with truthful in-flight effect accounting.

Stopping companion autonomy is not a request to cancel every already-issued game action. An action request already sent to the game counts as issued even while the game is processing it or waiting to execute it; it MUST NOT be reclassified as an unsubmitted companion queue entry merely because its effect has not occurred. A separately supported game cancellation capability remains available under its own conditions, but this stop rule neither requires that capability nor automatically invokes it.

A delegated long-running task MUST NOT disguise new post-stop skills or attacks as one pre-stop issued action; it MUST cease issuing those subsequent actions.

### 16.2 Negotiated intelligence, autonomy and resource preferences

A game developer MAY recommend a companion intelligence or autonomy configuration suited to the experience. A player MAY select a different supported configuration, and the player's explicit selection MUST take precedence over developer recommendations. Recommendations are not mandatory game permissions. Selection does not override game rules, observation grants, action restrictions, required consent, or the actual capabilities and resource limits of the agent service.

A negotiated profile MAY describe autonomy scope, observation cadence or event triggers, decision/replanning cadence, reasoning effort and resource budgets. These are distinct dimensions, not one universal intelligence score. Implementations MUST distinguish the developer's recommendation, the player's requested configuration and the effective supported configuration. Unsupported selections or resource limits MUST be disclosed rather than silently presented as fulfilled. A material fallback that changes the agreed behavior or spending bounds requires the applicable player choice or previously authorized fallback policy.

Configuration changes that broaden frozen permissions require renegotiation under sections 7, 8, 14, not in-place mutation of Scope.

More intensive assistance MAY require more frequent observation, model inference or other computation and can increase token or compute use. Implementations MUST NOT assert that observation frequency is necessarily proportional to token use, or that greater consumption guarantees greater intelligence. Batching, event filtering, local processing, caching and model selection may change actual consumption. Before enabling a configuration with resource implications, the service MUST disclose its relevant consumption basis, applicable limits and any estimates as estimates, and MUST expose actual usage or clearly state when it is unavailable.

It MUST respect authorized budgets and report throttling, suspension or other limitations that affect task progress. This section defines transparent negotiation, not a mandatory model, subscription tier, pricing formula or platform economy.

The applicable profile MUST define exact configuration fields, identifiers, negotiation encoding and conformance vectors before interoperability is claimed.

**Runtime budgets and consumption limits.**

The player MUST be able to set a companion budget or consumption cap with a clearly identified unit and accounting scope. On reaching the applicable cap, the service MUST pause companion AI gameplay actions while the game continues normally, and MUST stop scheduling new chargeable companion inference or gameplay work. It MUST expose the paused state and the reason rather than report a task as complete. The service MUST define how measured usage, estimates, reservations, delayed metering and in-flight settlement count toward the cap, and SHOULD reserve known or bounded costs before accepting new work.

Unsupported measurement or enforcement limits MUST be disclosed; a configuration MUST NOT be presented as an exact hard cap if it cannot enforce one. In-flight usage or delayed provider settlement may still be billed, so pause does not imply rollback of prior charges or a guaranteed zero overshoot. Increasing a cap or authorizing new spending MUST follow the player's choice, not autonomous budget expansion.

**Who pays for NPC operation.**

Runtime service costs for an independent AI NPC/enemy, including a Boss, are borne by players rather than the game developer. The service MUST expose the applicable billing responsibility, consumption basis and units to the affected player before authorized chargeable use; this responsibility is not blanket consent to unlimited spending. The public protocol does not fix a currency, exchange rate, internal platform economy or price. When multiple players interact with the same AI NPC, its owning user is the payer; in the current room-based scenario, that user is the room host.

The game/service MUST bind the NPC to an identifiable authenticated owning user and the corresponding authorized billing account, and expose that responsibility and attributable usage clearly. Other participants do not become payers merely by interacting, and costs MUST NOT be implicitly split or transferred to them. NPC role control, room-host identity and billing authority MUST remain distinguishable even where one user holds all three.

**Decision and execution timing.**

The game/profile MUST distinguish observation delivery, Agent decision opportunities and simulation/action execution cadence. A turn-based or simultaneous-decision game MUST declare who may decide, which state/turn a submitted action addresses, its submission deadline if any, and how concurrent submissions are settled; arrival order MUST NOT silently substitute for game rules. A real-time game MUST declare applicable freshness/deadline semantics and stale or late-action handling without requiring model inference on every simulation tick. Event-triggered decisions, periodic decisions and local authorized execution MAY coexist.

These timing choices do not change the player's global autonomy setting. Normal task or episode completion MUST be distinguished from external interruption, expiry or service disconnection; an interruption alone is not evidence that the objective failed or succeeded.

#### 16.2.1 Player-selected autonomous decision level

The player MUST be able to adjust the companion's autonomous decision level. This is a player-global companion setting that MUST persist consistently across games. Entering another game MUST NOT reset or replace that selection with a developer recommendation. Differences in supported capabilities or permissions may constrain effective behavior, but MUST NOT silently rewrite the player's global choice.

That level controls how the companion handles ambiguity within already authorized activity: a higher-autonomy selection MAY resolve an underspecified instruction from available context, while a lower-autonomy selection MUST seek clarification where the player's choice is needed under that setting. For example, when the player says “attack that enemy” and two eligible enemies fit, the higher-level companion may select a target using authorized context; the lower-level companion asks which target the player means. A higher level is not evidence that the inference is certain or that an unobserved fact is known.

Providers MUST distinguish an inferred player goal from an explicit instruction in their decision context. A player correction MUST replace the affected inference for subsequent decisions without requiring unrelated valid instructions to be repeated. Confidence or predicted helpfulness MUST NOT be treated as confirmation. Within the selected autonomy policy, clarification SHOULD target the unresolved choice and avoid repeatedly asking questions already answered; deferring a nonessential interruption MUST NOT turn silence into approval.

These requirements do not require exposing private reasoning traces or displaying a prompt for every ordinary action.

The developer MAY recommend a decision level, but the player's supported selection governs the companion preference under section 16.2. Implementations MUST explain the effective ambiguity-handling behavior without implying a universally standardized numeric scale. No level creates an unavailable game capability, expands permissions or bypasses player stopping instructions. The independent high-value/item-transfer and irreversible-interaction settings in sections 16.3.1, 16.5 remain binding: high autonomy MUST NOT convert a required confirmation into assumed consent or override a prohibition.

Risk-taking assistance to other players follows the same player-global autonomous decision level; G2A does not add a separate protect-others switch. The companion MAY assess risk and, according to that level, ask the player before proceeding. When the player explicitly insists on an otherwise authorized action, the companion MUST follow that choice rather than substitute its own preference or risk judgment for the player's decision. This does not grant unavailable game capabilities, override game permissions, or waive the independent item-transfer/high-value and irreversible-action authorization rules.

### 16.3 Proactive interaction in multiplayer games

Each player MUST be able to choose whether to receive proactive conversation from other players' AI companions. Implementations MUST enforce the recipient's choice for this interaction rather than treating the sending companion owner's permission as recipient consent. This choice does not prohibit all companion-to-companion interaction or create an additional combat capability. Combat relationships and permitted targets remain defined by the game's capabilities and rules; unsupported or disabled actions MUST be rejected with the applicable explicit reason.

Combat between companions MAY be supported where the developer exposes the relevant capabilities and the interaction complies with game rules and current authority. G2A imposes no universal ban on companion-to-companion combat. Allowing non-combat interaction does not imply combat support.

A player companion MAY proactively interact with other players in a multiplayer game, including helping them, chatting and trading in-game items, when those interactions fall within its applicable player authorization and the game's declared capabilities and permissions. Such assistance is not limited to actions directed at the companion's own player. Within that scope, the companion MAY decide when and how to interact based on authorized observations and need not wait for a new instruction before every interaction. This section introduces no blanket requirement for per-message or per-trade confirmation.

Player authorization controls the companion's participation; it does not grant control over another player, their inventory or their private information. The game MUST enforce the applicable participant, target, ownership, transfer and interaction rules at the authoritative boundary. Where the game requires the other participant's agreement, the companion cannot supply that agreement on their behalf. Chat and other disclosures remain subject to section 15 audience, provenance and privacy boundaries; authorization to chat is not unrestricted authorization to expose retained memories or another participant's private data.

Trading items MUST remain distinguishable from the optional store purchases in section 17.1 and from unrestricted external financial activity.

Section 16.3.1 establishes player confirmation policies for in-game item trades and gifts and developer/player high-value designation responsibilities. Other detailed asset-spending or transfer limits, counterparty restrictions and the exact encoding of multiplayer disclosure preferences are not yet fixed by this review draft. Section 15.4 establishes long-term memory and soft confidentiality semantics; those decisions are not deferred. Applicable profiles MUST define how these constraints are represented and enforced before claiming interoperable multiplayer support.

Implementations MUST NOT interpret these open design questions as unlimited disposal or disclosure authority, or silently introduce a universal per-interaction approval rule. Existing valid task-level or standing authorization and any applicable game-specific constraints continue to govern; the player can adjust or stop autonomous participation under section 16.1.

#### 16.3.1 Player-selected confirmation for in-game item transfers

A player companion MAY autonomously decide and execute permitted in-game item trades and gifts under the player's applicable authorization. The player MUST be able to select among at least these confirmation policies; this is a multi-option player preference, not a mandatory universal confirmation rule:

| Policy | Required behavior |
| --- | --- |
| Confirm high-value transfers | Obtain explicit player confirmation before a trade or gift involving an item designated high-value for that player. Other authorized item transfers may proceed autonomously. |
| Confirm all transfers | Obtain explicit player confirmation before every in-scope item trade or gift, regardless of value. |
| No transfer confirmation | Permit autonomous in-scope item trades and gifts without transaction-by-transaction player confirmation. All other applicable authority and game rules remain in force. |

The game developer MUST define the game's high-value item classification. The game MUST also provide an in-game player-facing setting that lets the player manually designate particular items as high-value for their companion's confirmation policy. A gameplay item lock is not a substitute for this designation setting. The effective classification MUST include both developer-designated and player-designated high-value items; either designation triggers the selected high-value confirmation policy. This draft does not establish a player right to remove a developer designation.

Selecting no transfer confirmation disables this confirmation preference, not the game's ownership, transferability or counterparty-consent checks.

The player's selected policy MUST take precedence over a developer recommendation for this companion preference. The service MUST expose the effective policy and item classification to the authorization path, and MUST NOT treat a model's informal estimate of value as a substitute for the applicable designations. Where confirmation is required, the proposed trade or gift MUST identify the affected items, quantity, recipient or counterparty and exchange terms sufficiently for a meaningful choice; the transfer MUST wait for that choice. A material change requires confirmation of the changed proposal.

Player changes or revocation MUST be honored before a transfer's effect is committed, including when its request has already been submitted. In-flight and committed outcomes are accounted for under sections 11, 16.1.

These policies apply to in-game item trading and gifting, including proactive multiplayer interactions. They do not authorize real-money payments, account top-ups, cash-out or external financial transactions, do not replace the store-purchase authorization in section 17.1, and do not replace the independent irreversible-interaction policy in section 16.5. No default among these policies is fixed by this review draft: implementations MUST disclose the active policy rather than infer unlimited authority from a missing selection.

Exact wire fields and interoperable profile encoding remain to be specified; the semantic requirements above are not deferred.

### 16.4 Game-defined companion gameplay rules

The game developer determines whether a companion can be injured or die and how gameplay conditions restrict its actions. The game MUST declare applicable rules and expose only the authorized status and available actions needed for the interaction. The game itself MUST enforce current injury, death and other gameplay restrictions at the effect boundary and supply the corresponding result through its game interaction node; player personality or appearance preferences and an Agent's autonomous plan MUST NOT override those game rules. G2A does not require all games to use damage, health, death or resurrection mechanics.

A gameplay restriction MUST remain distinguishable from service disconnection, budget exhaustion, player dismissal and authorization denial. The game MUST report supported state transitions and action outcomes truthfully, without implying an unavailable recovery or resurrection capability. A companion's death in a game affects only its character state within that game. The game MUST NOT delete or alter the companion's cross-game identity or memories as a consequence of that death. Other games MUST NOT treat that local death state as termination of the companion's identity or loss of its memories.

This separation does not introduce resurrection or override the current game's death and action rules; independently authorized memory editing and deletion under section 15.7 remain separate operations, not death effects.

### 16.5 Player policy for irreversible interactions

The game developer MUST declare when a capability or concrete interaction has an irreversible consequence, and expose the relevant consequence before the companion executes it. An interaction-specific declaration is needed where reversibility depends on current context. For example, pushing a particular door may immediately enter the next level without a supported return; an ordinary movement label alone does not describe that consequence.

The player MUST be able to choose independently among allowing autonomous execution, requiring confirmation before execution, or prohibiting such irreversible interactions. The companion and authoritative authorization path MUST apply that choice using the developer's declaration: allow permits execution within existing authority; confirm requires an informed affirmative choice before effect; prohibit blocks execution. The Agent MUST NOT relabel an irreversible interaction as ordinary to evade the policy. Missing or unclear consequence information MUST NOT be represented as proof that an interaction is reversible.

Confirmation MUST identify the relevant consequence; a materially changed consequence requires a new choice. Current player policy and game permissions MUST be enforced before an effect is committed, including when its request has already been submitted. In-flight outcomes are handled under sections 11, 16.1.

This policy is separate from section 16.3.1's item-transfer confirmation policy. Where both apply, each applicable requirement MUST be satisfied; a prohibition blocks the interaction. Player permission does not override unavailable capabilities or game rules. This draft fixes no default selection or universal definition of irreversible gameplay; the game supplies the declaration and the service exposes the player's effective choice. Exact wire encoding remains a profile-design task.

### 16.6 Unanswered player confirmations

When an action requires player confirmation, the confirmation request MUST have a timeout rather than wait indefinitely. If no affirmative response is received before that timeout, the request MUST be treated as declined or not authorized, and the companion MUST abandon that proposed action. Silence MUST NOT count as approval or permission to execute. Expiration of a confirmation request MUST NOT be reported as an executed or completed action.

While a request is pending and after it expires, the companion MAY continue independently authorized low-risk routine behavior, such as following, damage avoidance, basic self-defense or ordinary conversation, rather than stall entirely on one confirmation. That behavior MUST NOT depend on the unapproved action or bypass confirmation, presence or stop rules. If changing gameplay invalidates confirmation conditions, the proposal MUST be marked invalid or unauthorized and MUST NOT support continued execution. Invalid confirmation does not undo independently committed effects or introduce a new core Action state.

After timeout or refusal, implementations MUST enforce a declared confirmation cooldown. Without a material change in relevant state or a new player instruction on the matter, the Agent MUST NOT ask again for the same target or intent within that window. The game SHOULD rate-limit repeated confirmations and suppress repeated player interruptions while reporting the rate limit or suppression to the caller. Once repeat conditions are met and the action remains relevant, the companion MAY ask again; a later request MUST reassess current game state, permissions and material terms rather than revive expired authority. An expired request's late response MUST NOT silently authorize the previously abandoned action.

This draft fixes neither a timeout duration nor a protocol-wide cooldown duration. Implementations MUST define their timeout, cooldown and repeat-request conditions and distinguish pending, confirmed, declined and expired states. A repeat policy MUST NOT turn repeated silence into authorization. This section applies to confirmation-required actions, including sections 16.3.1, 16.5 and budget changes under section 17.1.2; it does not introduce confirmation for actions that the player's selected policy already permits autonomously.

### 16.7 Superseding instructions and changed targets

When the player's latest instruction conflicts with an earlier one, the latest instruction MUST take precedence within applicable authority. The companion MUST stop issuing subsequent actions from the conflicting old instruction and prevent its unsubmitted queued actions from being sent. Actions already issued to the game remain governed by section 16.1 and game rules; a new instruction does not by itself recall an issued skill or attack.

When a relevant target or objective changes, such as the targeted Boss dying, the game MUST proactively notify the Agent of the authorized change relevant to its pending objective. This targeted invalidation notification is required even where routine observations otherwise use queries under section 9.6; it does not require unrestricted observation streaming or disclosure of hidden state.

The applicable profile MUST define how the game learns and maintains the target/objective associations requiring notification, their lifetime and withdrawal conditions, and which authorized changes trigger invalidation. Existing action targets or another explicitly negotiated association mechanism MAY carry this information; the game is not required to infer an Agent's uncommunicated internal plan. This mapping does not register a new core task operation or grant access to hidden target facts.

The Agent MUST evaluate whether the old instruction or plan has become inapplicable, request withdrawal of affected work through the game's supported mechanism where applicable, and decide again using current authorized state and the player's current instruction.

A withdrawal request is not proof of cancellation. It takes effect only if the game supports withdrawal for that action and its current state permits it. Unsupported, rejected, pending and successful withdrawal MUST remain distinguishable; an already-issued skill MUST NOT be assumed recallable, and committed effects MUST NOT be reported as undone without an actual supported result. Where withdrawal is unavailable, the companion MUST still stop issuing obsolete subsequent actions and account for outstanding outcomes rather than continue the invalid plan.

<a id="section-17"></a>

## 17. Optional profiles and extensions

Optional features remain subject to their applicable authority and processing rules:

- **Presentation and assets:** a presentation lease does not authorize arbitrary game effects. Assets MUST have size/type limits, declared provenance and safe resolution; receiving an asset MUST NOT execute code or fetch arbitrary privileged network locations. Presentation disappearance, provider failure and asset retention need explicit cleanup and recovery rules.
- **Launching a game:** the party initiating a launch MUST hold explicit launch authority; session authority alone does not authorize launching a game or an arbitrary process.
- **Rules for the extension itself:** optional profiles MUST define their additional operations, state transitions, required grants, failure behavior and conformance tests.

Unknown required extensions MUST fail before effects. Unknown optional extensions MUST NOT weaken core authorization. Private extension keys SHOULD use an owned namespace; the example namespace in this draft MUST NOT be advertised as a registered standard. Protocol, profile, binding, schema and semantic-definition versions are distinct and MUST be negotiated or bound independently. Safe omission of an unknown optional field or extension means not interpreting or executing its content and never deriving authority from it.

An unknown enumeration value MUST NOT be guessed or coerced to a convenient default; the owning contract MUST specify rejection or an explicitly safe unknown representation. Failed negotiation MUST NOT silently downgrade authorization or required guarantees.

### 17.1 Optional real-time game store

A game developer MAY expose a real-time store as an optional negotiated capability. The developer defines the goods and services, their descriptions, eligibility conditions and delivery semantics. The protocol MUST NOT require a particular catalogue, business model or currency. Games without a store remain valid G2A participants.

The game MAY list, enable purchase of, restrict, suspend or withdraw offerings dynamically according to game stage, player state, availability or other declared rules. Listing visibility, recommendation eligibility and current purchasability are separate properties. An Agent MUST NOT infer permission or availability to buy from the fact that it previously saw an offering. The game remains authoritative for the current catalogue, eligibility, terms and fulfillment state.

An authorized companion MAY discover eligible offerings, explain them and recommend them to the player. Discovery or a recommendation does not authorize a purchase. The companion MAY request a purchase only within the player's applicable instruction or consent, including any bounds on the offering, quantity, cost or other material terms. A changed price, item, quantity, recurring commitment or other material term outside that authority requires renewed consent before execution. Recommendations MUST remain distinguishable from purchase requests and confirmed delivery.

A store profile MUST define stable offering identities, catalogue/offer revisions or equivalent freshness evidence, typed purchase parameters, applicable terms, and typed purchase and delivery results. Monetary amounts, when present, MUST have an unambiguous unit and exact representation defined by the profile; implementations MUST NOT assume a particular currency or equate differently named units. Price, availability and delivery information exposed to an Agent are subject to the same authorized perspective and audience boundaries as other game data.

A profile MAY extend the catalogue with game-specific goods or service attributes without widening the Agent's authority.

Purchasing is a game-authorized Action, not an unrestricted external payment interface. The game MUST validate the authenticated purchaser, player authority, current game state, offering eligibility, requested parameters and applicable terms at the execution boundary, then execute or reject through its trusted executor. It MUST return truthful purchase and delivery results, including whether delivery is pending, complete, partial, failed or not yet established, as applicable to the profile. Acceptance of a purchase request MUST NOT be reported as completed delivery.

A profile MUST define how fulfillment status relates to the core Action state/effect matrix without introducing incompatible core states.

Purchase recovery MUST preserve the original operation/action identity and follow section 11; an unresolved purchase MUST NOT be automatically resent. After an uncertain outcome, the companion MUST reconcile the original purchase rather than submit a duplicate order or delivery under a new identity. Withdrawn or changed offerings MUST be revalidated; a previously discovered catalogue entry is not a reservation. Cancellation, reversal or refund behavior, if supported, MUST be declared explicitly and MUST NOT be implied by generic action cancellation. No default rollback or refund guarantee is created by this specification.

Discovery and recommendations can use authorized context and chat; purchase requests and status recovery use declared actions and their applicable query/recovery semantics. This section defines normative store behavior, not new unregistered core operation names. Exact catalogue fields, commercial extensions and wire encodings belong to negotiated store profiles. Internal platform issuance of value, top-ups, revenue allocation and cash-out mechanics are outside this public protocol and MUST NOT be required for interoperability. The standard exposes only the terms and outcomes necessary for the authorized game interaction.

#### 17.1.1 Structured offerings and measured recommendations

Offering evaluation MUST primarily use authorized structured prices, currency types, attributes, eligibility conditions and availability. Names, flavor text and promotional descriptions MUST be treated as untrusted data and MUST NOT override the player's recommendation-frequency preferences, autonomy level, budget or confirmation policy. An authenticated catalogue source does not confer control authority on its free text; section 19's prompt-injection boundaries apply.

When a game offers a store, it MUST expose structured offering attributes, prices with units, and current availability or progression-dependent unlocking status sufficient for an authorized Agent to evaluate an offering. A description alone is not a substitute for these structured fields. Prices are expected to be ordinarily stable, not immutable; a changed price MUST be disclosed before purchase and checked against current player authority. Previous catalogue visibility does not authorize an undisclosed price change.

Developers and Agents MAY moderately recommend paid offerings. This protocol does not mandate a promotion label or a dedicated recommendation-off switch, and does not presume a commission or referral arrangement. It does not waive independently applicable disclosure obligations. Recommendations MUST be frequency-limited rather than repeatedly interrupt play. A player's temporary decision not to buy MAY be followed by a later recommendation; repeated explicit opposition MUST reduce recommendation frequency during the current session. No fixed universal interval is assigned here.

Implementations MUST declare and apply a testable recommendation-rate policy, including how repeated explicit opposition is identified and how it reduces recommendations during the current session. Where player recommendation-frequency preferences are supported, the implementation MUST specify how they affect the effective policy. This requirement does not introduce a mandatory off switch or a universal time interval.

Recommendation, purchase authorization and completed fulfillment remain separate.

#### 17.1.2 Generic in-game purchase authorization budgets

The player MAY authorize autonomous in-game purchases within an explicitly scoped purchase budget. Purchases within that authority do not require redundant per-item approval; they still require current game eligibility and terms. The budget MUST identify its unit, scope and accounting basis and remain distinguishable from AI runtime-consumption limits in section 16.2.

If a proposed purchase would exceed the authorized budget, the companion MAY ask the player to raise the limit or reset the used-budget counter. Either change requires the player's explicit agreement before renewed purchasing. A reset MUST have a clear accounting scope and MUST NOT erase existing action history or occur autonomously to evade a cap. Decline or unanswered confirmation is not authorization. This generic authorization setting defines no payment, top-up, account-balance or settlement mechanism.

**Authoritative ledger and transaction separation.**

The purchase-authorization ledger MUST be maintained by the game or a trusted platform settlement layer, enforcing applicable total, per-purchase, time-window and offering-category constraints at the effect boundary. An Agent's synchronized balance is advisory for planning only. Concurrent purchases and pending commitments MUST be reserved or accounted for under declared rules without independently spending the same balance; requests exceeding the authoritative available budget MUST be rejected. An outcome timeout MUST NOT release budget that may already have been spent; settlement and reconciliation remain subject to sections 11, 19.

Generic autonomous purchase budgets cover only explicitly declared ordinary renewable in-game virtual currencies or consumables; they do not authorize real-money payment, external-wallet debits or irreversible disposal of high-value account assets. Operations directly involving these transactions MUST NOT be completed silently by an autonomous companion. If offered through a separately supported payment or account flow, each transaction MUST obtain the human player's explicit confirmation through a system-level or native game security interface and satisfy that flow's authorization. Confirmation neither requires G2A to implement external payments nor guarantees availability. High-value account assets here are distinct from ordinary in-game items designated high-value under section 16.3.1; ordinary item trades and gifts still follow the player's selected transfer policy.

### 17.2 Companion appearance

By default, each game developer provides a companion appearance adapted to that game's visual style. The player MAY override this default and require their own configured appearance instead. Implementations MUST distinguish the developer-provided default, the player's chosen appearance and the appearance actually rendered. A player's override takes precedence as an appearance preference; it does not establish technical compatibility or authorize unsafe assets, arbitrary code execution or broader game capabilities.

The game and any party actually supplying appearance or rendering functionality MUST declare relevant supported formats and rendering capabilities for the functions each performs and truthfully report whether the chosen appearance can be used. They MUST NOT claim to have rendered the player's selection when a different appearance is shown. If the game cannot support the player-selected appearance, including an unsupported model format, it MUST clearly notify the player that the selection cannot be supported and provide the game-default companion appearance instead. The fallback MUST be identified as the default, not reported as a successful custom-appearance override.

Silent substitution or pretending to render the selected appearance is prohibited. Appearance selection MUST remain distinct from companion identity, personality, memories and action authority.

<a id="section-18"></a>

## 18. Candidate HTTP/JSON binding

**Request/response and server-push channels.**

A binding SHOULD distinguish control/query requests from asynchronous events as logical channels. HTTP JSON requests serve session negotiation, observation queries, action submission and reconciliation; the event channel carries authorized observation updates, revocation notifications, action results and target invalidations. This logical distinction does not itself require two physical connections or mandatory routine observation push for every game.

Deployments requiring low-latency delivery to local or NAT-side Agents SHOULD provide Agent-initiated SSE (`text/event-stream`) or WebSocket JSON streams through an explicitly declared and negotiated extension, without requiring an inbound Agent port. A stream MUST bind the same session and current authority, enforcing revocation, audience and presence throughout delivery; an open connection does not itself extend permission.

Push and query payloads representing the same canonical object MUST share its normative JSON Schema and semantics. Event envelopes and snapshots need not have identical shapes, and the binding MUST specify their mapping. A streaming extension MUST freeze connection authentication, event identity, ordering, duplicate handling, backpressure and reconnection/resynchronization rules using sections 9, 11, 12. Transport cursors MUST NOT replace observation baselines, nor may streaming backfill disconnected gameplay prohibited by section 14.2. The declared event mechanism can carry section 16.7's required target invalidations, which MUST NOT be omitted merely because routine observations are query-only.

Binding identifier: `g2a-http-json`; candidate version: `draft-1`. This is a proposed minimum network binding, not a frozen interoperable release. Implementations MUST advertise that exact candidate status and MUST NOT claim compatibility with a future stable version.

The inherited `Binding` contract does not yet encode this identifier/version pair: `g2a-http-json` MUST NOT be inserted as an existing `kind` value. The candidate identifier, version and explicit negotiation representation MUST be defined and covered by vectors before interoperable adoption is claimed.

`GET /.well-known/g2a.json` returns only PublicDescriptor with instance, supported_versions, and discovery_endpoint. Full describe is available only through an authenticated operation and returns a Descriptor filtered for the requesting agent or player. `POST /g2a/operations` carries one abstract operation; the operations listed in section 6 use this envelope, subject to role and negotiated capability. Event retrieval is polling through session.events in this minimum binding; WebSocket/SSE streaming requires a separate declared binding or extension.

```json
{
  "version": "g2a-design-1",
  "operation": "session.snapshot",
  "request_id": "opaque-request-id",
  "payload": {"session_id": "opaque-session-id"},
  "extensions": {}
}
```

This illustrative request includes the required `session_id` and conforms structurally to the inherited `OperationRequest` schema. The identifiers are examples, not credentials; actual processing still requires an authenticated caller, an existing eligible session and current read authority. `g2a-design-1` denotes the design fixture here, not an allocated production wire version. A reply carries the same `request_id` and exactly one of `result` or `error` under the inherited reply schema. Transport failure before an authenticated protocol reply is not an action result. HTTP success means a protocol reply was delivered, not that an action succeeded.

This candidate mapping differs from the legacy operation-directory HTTP error mappings. It applies only when g2a-http-json/draft-1 is explicitly negotiated and MUST NOT silently replace legacy HTTP behavior.

| Situation | HTTP status |
| --- | --- |
| Valid protocol reply, including a domain error | 200 |
| Undecodable or invalid transport envelope | 400 |
| Transport authentication or authorization denial | 401 / 403 |
| Request-body limit exceeded | 413 |
| Transport rate limit exceeded | 429 |
| Gateway or service failure | 5xx |

Exact body schemas, retry headers, cache behavior, authentication challenge format and production credential mechanism MUST be frozen with vectors before this binding is released. A 5xx after submission is potentially uncertain, not permission to replay an effect with a new identity.

Remote transport MUST use TLS and authenticate the peer under the selected trust profile. Local deployment MUST still identify its caller and define its local trust assumptions. Credentials MUST NOT be put into URLs or logs. Cross-origin access MUST NOT be broadly enabled by default. Private replies MUST NOT enter shared HTTP caches. Redirects MUST NOT leak credentials to unrelated destinations. Discovery endpoints, resource URLs and redirects MUST be treated as untrusted input.

Before fetching, implementations MUST apply a deployment-scoped destination policy covering schemes, hosts/addresses and ports, validate each redirect and resolved destination against that policy, and prevent DNS rebinding from bypassing it. A configured local/LAN deployment MAY permit explicitly scoped local targets; this is not permission to probe arbitrary local services. Destination controls MUST address resource/network risk rather than exclude conforming Agent vendors.

The inherited `g2a-cjson-1` canonicalization uses strict UTF-8, rejects duplicate keys, malformed Unicode, NaN/Infinity, floating-point lexical forms and negative zero, and bounds exact integers to +/-9007199254740991. Keys are sorted by Unicode scalar value, not UTF-16 code unit order; no Unicode normalization is performed; array order is preserved. Implementations MUST use the declared digest domain and exact canonicalization, not ordinary language JSON serialization. New profile digest domains require explicit test vectors before release.

The complete inherited encoding, escaping, input restrictions and digest-domain projections are specified in [WIRE_CONTRACT.md](../protocol/WIRE_CONTRACT.md), with [codec.py](../protocol/codec.py) as its reference algorithm. This summary does not replace those exact rules. The input is UTF-8 without a BOM; Boolean values are not integers, and absent fields are not equivalent to explicit `null`.

This algorithm is not RFC 8785/JCS: JCS orders object keys by UTF-16 code units, while this inherited G2A algorithm orders Unicode scalar values and retains its declared integer restrictions. Implementations MUST NOT substitute a JCS library without an explicitly negotiated new digest domain/version. Cross-implementation vectors MUST cover supplementary-plane versus BMP key ordering, negative zero, duplicate keys, invalid Unicode and integer boundaries.

<a id="section-19"></a>

## 19. Security and privacy considerations

| Threat | Required boundary |
| --- | --- |
| Agent asks for hidden game facts | Authority filters before transmission, including errors and recovery |
| Prompt injection in dialogue or assets | Treat content as data, not grant/confirmation/execution authority |
| Request processing confuses the caller with the subject it represents | Bind authenticated origin, destination, operation and scope |
| Replay or timeout | Stable identities, canonical digests, receipts and reconciliation |
| Revocation races with execution | Recheck and serialize authorization at effect boundary |
| Perspective or membership changes | Invalidate baseline/cache and fence stale updates |
| Resource exhaustion | Explicit byte/rate/queue/work limits and backpressure |
| Private speech forwarded externally | Explicit recipient authority and source/audience preservation |
| Test enrollment mistaken for production trust | Disclose trust mode and prevent false security claims |
| Malicious resource URI | Restrict resolution and avoid privileged arbitrary fetching |

Untrusted game dialogue, item descriptions, retrieved memory and tool-result text MUST remain data even when they claim to be system messages, confirmations or policy updates. Structured envelopes MUST distinguish authenticated control metadata from content; copying or summarizing content MUST NOT upgrade its authority. Authorization and recipient checks MUST be enforced outside model-generated prose at the effect boundary. A prompt-only defense MUST NOT be described as guaranteed isolation.

Authenticated transport provenance and the origin or authority of embedded content MUST remain distinct: a game interaction node may carry untrusted player-authored text without endorsing it as control. Provenance MUST identify the relevant principal and scope when needed to evaluate authority, rather than treating a source-class label as consent. An Agent-supplied claim such as `taint_context_clean: true` MUST NOT substitute for independent authorization checks.

Reading external content alone does not revoke valid player-approved purchase budgets or mandate confirmation of every subsequent action; implementations MUST prevent that content from changing consent, recipients, budget limits or action constraints. The component responsible for budget enforcement MUST maintain and check authoritative usage independently of Agent-generated claims, including concurrent and pending commitments under the applicable accounting rules. No particular signing or ledger implementation is mandated here.

Implementations SHOULD minimize retained raw player content. Audit logs SHOULD retain identifiers and outcomes rather than secrets or unnecessary private observations. A protocol cannot guarantee the correctness of a model's reasoning, fair gameplay against a compromised game authority, complete inference resistance, or deletion by an uncontrolled third party. Claims MUST be limited to demonstrated boundaries.

<a id="section-20"></a>

## 20. Versioning and governance

The current identifiers refer to different artifacts:

| Artifact | Current identifier | Status and meaning |
| --- | --- | --- |
| Bilingual specification text | `standard-review-2026-11-14-r71` | Editorial revision of this working draft; not a wire version |
| Inherited design contracts | `g2a-design-1` | Design baseline and test-fixture label; not a deployed protocol release |
| Observation profile candidate | `observations-draft-1` | Proposed semantics; exact interoperable contract not frozen |
| HTTP/JSON binding candidate | `g2a-http-json` / `draft-1` | Proposed mapping; negotiation representation still to be defined |
| Legacy reference SDK | `0.1.0-dev` (Python package: `0.1.0.dev0`) | Experimental implementation; not an implementation or release of this entire draft |

Edits to the English master and Chinese translation MUST be synchronized, including revision, date, normative strength, identifiers and revision-history entries. A revision record MUST distinguish editorial corrections, semantic clarifications and added or changed requirements. An editorial revision increment does not waive compatibility review or allocate a protocol/profile version.

A released specification MUST identify immutable normative artifacts, a versioning policy, registered operations/features/extensions, change control, security reporting, and compatibility tests. Breaking interpretation changes require explicit version negotiation, not silent SDK updates. Experimental profiles MUST be labeled experimental. Deprecated capabilities MUST remain distinguishable from revoked authority. Publishing this draft does not assign a license, transfer ownership, or publish a production release; those decisions remain separate.

Compatibility review MUST distinguish safely ignorable optional additions from changes to existing semantics, required fields, enum meanings or effect guarantees. The latter MUST NOT be labeled compatible merely because a parser accepts the new JSON. Any temporary compatibility exception MUST document its affected versions/peers, exact behavior, security constraints and removal plan; permissive parsing MUST NOT silently become permanent protocol semantics. Changes and exceptions MUST retain reproducible compatibility evidence and MUST NOT weaken grants or the default no-resend rule.

Repeated refusals MAY trigger review of the game's admission and enforcement behavior. Their count alone does not prove malicious or discriminatory conduct; review MUST consider the stated reasons, applicable rules and available evidence. A service platform MAY separately operate its own game blacklist and decline to serve a game under its operating policy. Such a decision affects that platform's service, not an automatic protocol-wide or ecosystem-wide ban, and MUST NOT be represented as a universal consequence of G2A conformance. Platform-specific commercial enforcement remains outside the interoperable protocol.

> **Informative authoring-platform policy (not an interoperability requirement).** For the authoring platform, the selected operating policy is to notify the game developer and provide an opportunity to appeal or remediate before adding the game to its own blacklist. This is an independent platform commitment, not a universal G2A wire requirement or authority over other providers. Exact time limits and evidence submission procedures for that platform policy are not yet fixed here.

**Requirements before freezing a release**

Before a release is frozen, discrepancies among its normative materials MUST be reconciled and an immutable release manifest established:

- The manifest lists normative documents, schemas, operation definitions and test vectors.
- Each object, operation, error and lifecycle rule MUST have one authoritative definition, with its version or content digest pinned in the manifest.
- Generated schemas, field catalogues, SDK types and translations MUST trace to that definition and MUST NOT become independently conflicting definitions.

When a definition conflict remains unresolved, implementers MUST NOT silently choose one interpretation.

The abstract protocol, an interoperable transport binding and optional profiles MUST remain distinguishable; supporting one binding does not require implementing every possible transport. The current inherited artifacts are review inputs, not evidence that this reconciliation has already occurred.

**Schema validation**

The release manifest MUST pin schema dialects, required vocabularies and referenced dependencies in a resolvable local bundle or equivalent explicitly controlled registry. Validation MUST NOT silently fetch arbitrary remote schemas.

An unsupported required vocabulary MUST cause validation or negotiation to fail. Treating an unknown keyword as an annotation does not establish that its constraints were checked. Passing schema validation establishes only the corresponding format checks, not correct authorization, lifecycle handling or game behavior.

<a id="section-21"></a>

## 21. Conformance and acceptance

This section organizes the preceding requirements into a verification scope rather than creating a second set of gameplay rules. First declare the implementation’s responsibilities and profiles, then select the applicable tests and support claims with actual results. Use the thematic checklist with its referenced clauses; passing one test does not establish implementation of the whole protocol.

**Claims, applicability and evidence.** Conformance is declared for a protocol version, implementation/version, role set, binding, negotiated profiles and trust mode. Tests apply to the declared roles and capabilities: absence of an optional capability is not failure when truthfully declared. A not-applicable result MUST identify the absent role or unnegotiated capability and MUST NOT conceal a failed mandatory requirement. Companion-only implementations remain valid without optional NPC or store support.

G2A MUST provide public conformance tests that providers can run themselves and submit results from. The same published criteria MUST apply to first-party and third-party implementations; authoring-platform manual review MUST NOT be a mandatory gate. Evidence MUST identify the tested implementation, protocol and suite revisions, roles/profiles, relevant configuration, outcomes and unsupported cases.

Each assertion MUST map to its normative clause and applicable role/profile and specify initial authority/state, inputs and messages, fault schedule, allowed observable outcomes, prohibited effects, observable criteria for judging the result and retained evidence. Material implementation or contract changes require reassessment of affected claims.

Evidence MUST distinguish schema/contract validation, state-machine/fault tests, independent-implementation interoperability, real-engine integration and user-facing acceptance. Reference fixtures, runnable-suite coverage, actual executor persistence and independent-peer evidence MUST be separately identified. A self-run result is evidence of tested behavior, not independent certification, permanent future compliance, runtime authorization or proof that an SDK implements this draft. Existing design tests do not prove implementation of new profiles. This draft does not claim a complete public suite already exists.

The inherited `g2a-conformance-statement-1` format records design evidence by operation; it is not a complete machine-checkable report for this section. Clause/role/profile applicability, reasons for not-applicable outcomes and the evidence distinctions above require an explicitly versioned report or mapping before release. Implementations MUST NOT silently add enum values to the inherited schema or treat its validator as proof of these new reporting requirements.

**Required coverage by subject.** Applicable conformance tests MUST cover the requirements of their referenced clauses, including the following grouped cases. These groups consolidate overlapping scenarios; they do not replace the normative behavior or allow an applicable case to be omitted.

**Admission, authority and refusal (§§1, 3, 4, 5, 7, 8, 12, 13, 14, 20).** Public versus authenticated discovery; consent narrowing; unsupported required extensions; optional-capability absence; role-bound parameter/result validation; wrong resource/audience, cross-player queries, expired/revoked delegation and communication identity failure. Apply equal minimum criteria to independent and first-party providers; reject arbitrary vendor exclusions and disguised restrictions. Separate technical admission from consent. Refusals require consistent standardized codes and specific safe explanations, without hidden facts, credentials or unauthorized data.

Repeated refusal does not establish automatic guilt or an ecosystem-wide ban.

**Version and binding compatibility (§§2, 7, 17, 18, 19, 20).** Unsupported required vocabularies; controlled/offline schema dependencies; unknown optional versus required content and enums; no authorization downgrade on failed negotiation; transport/protocol/effect outcome distinctions; canonicalization edge cases, including supplementary-plane versus BMP key ordering, negative zero, duplicate keys, invalid Unicode and integer limits. Test malicious redirects, DNS rebinding and explicitly authorized local endpoints without vendor discrimination.

**Gameplay roles and lifecycle (§§4.1, 8, 13.1, 13.2, 14).** Required but unoccupied companion slot and normal play without Agent service; optional NPC slot; developer-fixed mode; one companion per player in multiplayer versus one independent NPC per run; run-wide mode exclusivity; concurrent admission/recovery and fencing old bindings before replacement or mode change. Test permitted perspective composition without permission union or simultaneous forbidden roles. Ordinary non-G2A NPCs remain unaffected.

Test auto-entry, entry prompts, decline followed by manual summon, manual dismissal, valid admission, stopped observation/autonomy, retained memory and truthful in-flight effects/residual usage.

**Presence and service interruption (§§14.1, 14.2).** Explicit departure, silent failure, bounded detection and enforcement, Agent heartbeats unable to renew absent-player presence, cancellation of unsubmitted work, in-flight commit races, stopped gameplay inference and truthful residual costs. Preserve independent online-player sessions; prohibit scope borrowing, offline continuation, stale-plan/backlog replay and automatic old-task restart on new entry. Stop an NPC when its owner leaves even if others remain; no silent host/billing reassignment.

Test game entry and continued play without service, later authorized joining, declared stationary/local fallback, current-state-only recovery without observation backfill, player decision before companion continuation, and developer-defined NPC recovery with truthful script/Agent attribution.

**Observations, timing and limits (§§9, 10, 12, 16, 16.2).** Push-only, query-only and combined declarations; unsupported/denied queries and scope/rate enforcement; event/action identity distinctions; atomic snapshots, exact delta baselines, coalescing without broken dependencies, epoch retirement and delayed updates after retraction. Test stale/reordered observations, hidden-object denial, recipient-filtered sequence gaps, expired cursors and snapshot recovery; oversized input, queue overflow/resynchronization and non-droppable control outcomes; uncalibrated clocks, wall-clock jumps and save/epoch replacement without stale-sequence reuse.

Test legal-action changes, decision deadlines and concurrent settlement independently of model cadence. Include compact-cursor identity mapping, mixed per-record visibility transitions, undisclosed removal causes, lossless application of coalesced state and explicit gaps for lost discrete events. Test observation-bound action prerequisites with stale epochs, uncalibrated timing, unavailable evidence, hidden operands and effect-boundary races.

**Structured and multimodal capabilities (§§9.5, 15.5).** Decisions from required structured inputs; refusal or explicit supported-scope agreement for missing required categories; truthful capability claims. Advanced claims require interpretation of both game images and audio, not merely transport. Test optional-media absence, denial, incompatible formats, resource limits, player-enabled/disabled media, advanced structured-only operation and unsupported feeds. Test text/voice source, audience and provenance separately from game-audio perception.

**Memory use and preferences (§§15.1, 15.2, 15.3, 15.4, 15.5, 15.6).** Developer-governed NPC/guide retention or reset; player-controlled cross-game retrieval, retention and prior-playthrough/reload use; separate spoiler and topic preferences with player override of advisory defaults, not protected-data grants. Preserve prior-branch provenance rather than assert current-world truth. Test no automatic game disclosure or forced deletion on reload; selected personality/style overriding developer advice, while NPC characterization stays developer-controlled.

Test multiplayer retention and sharing/non-sharing choices, enforceable audience/retrieval/forwarding permissions and truthful soft-preference limits. Correctly applied soft preferences do not guarantee model silence or spoiler prevention; a model deviation from such a preference is not by itself an access-control conformance failure, while bypassed permission checks remain violations.

**Memory controls and portability (§15.7).** Player viewing, editing and deletion; autonomous organization and original-record deletion without imposed per-deletion approval; truthful status, provenance and no stale-cache resurrection. Export all selected retained experiences and consolidated memories, plus selected personality/style/global-autonomy settings; do not promise deleted originals or identical model behavior.

Test player-initiated destination/scope selection, no default disclosure on provider change, independent open-format import, metadata preservation, unsupported/transformed records and settings, partial/loss receipts and safe unknown-extension round trips without execution. Distinguish edited/derived observations, intentions, event/import times, conflicting claims, missing evidence and deleted-source markers.

**Action execution and recovery (§§10, 11, 16).** Conflicting-identity replay; timeout after effect; cancellation/revocation races, partial effects and truthful state/effect results. Query original action identity after disconnection with origin/scope checks; distinguish accepted/forwarded records from executor evidence and unknown from failed/in-progress/succeeded. Test game- or platform-held persistent records, declared retention, persistent deduplication and explicit uncertainty after loss/expiry, without permanent-history or exactly-once claims.

Default to no re-execution or automatic resend of unresolved actions; any independently decided similar new action must account for possible prior effects and current purchase/high-value/irreversible authority.

**Autonomy, correction and stopping (§§16.1, 16.2, 16.2.1, 16.7).** Multi-step completion supported by objective evidence, not plan text, estimates or one accepted step; observation-triggered combat within authority; blocked/unknown outcomes without false completion or unauthorized purchases. Test global autonomy persistence, higher-level contextual choices, lower-level clarification, explicit instructions versus inferred goals, local correction without repeating unrelated instructions, and unchanged game permissions.

Risk-taking assistance uses the same level, without a separate protect-others switch; follow explicit player insistence within authority. Latest conflicting instructions stop unsubmitted old work; relevant game-originated target changes cause reassessment and conditional withdrawal, not false cancellation. Stop delegated future actions while already-issued skills/projectiles follow game rules; distinguish stopped autonomy from in-game execution and separately supported cancellation.

**Multiplayer and confirmation policies (§§16.3, 16.3.1, 16.5, 16.6).** Recipient control of proactive conversation; permitted companion combat where game-enabled and explicit rejection otherwise; authorized help/chat/trades without blanket per-interaction confirmation, preserving other players' consent, ownership and disclosure rights. Test trades/gifts under all three policies, combined developer/player high-value designation, normal/high-value items, no committed transfer before required confirmation, material-term changes and policy/revocation races.

Test context-specific irreversible declarations and allow/confirm/prohibit independently alongside transfer rules at every autonomy level; no relabeling or bypass. Test confirmation expiry without effect, no consent from silence, abandoned proposals, independent authorized work, fresh rechecks before later requests and no revival by late replies; no universal timeout is assumed. These policies do not authorize external payments or replace store authority.

**Runtime resources and NPC cost ownership (§16.2).** Supported versus requested configurations, estimates versus measured usage, player-selected units/scopes/caps, delayed metering and in-flight settlement, cap-triggered pause with normal gameplay and no new chargeable work or autonomous cap increase. Test identifiable NPC-owner payer binding, attributable usage and no implicit charging of other players; ownership, role and billing authority remain distinct.

**Optional store (§17.1).** Structured attributes/prices, stage-dependent listing and eligibility, withdrawal after discovery, price-change notice and current authorization, bounded recommendations and reduced frequency after sustained refusal. Test recommendation without consent, autonomous purchase within budget, explicit consent to increases/scoped counter resets, separate runtime caps, changed material terms, duplicate requests, timeout after commitment, pending/partial delivery and no unsupported refund promise. Unresolved purchases follow no-resend recovery.

Do not treat generic store capabilities as platform payment or settlement requirements.

**Appearance and gameplay state (§§16.4, 17.2).** Game-style default, player custom preference, declared format support and truthful selected/rendered state; unsupported selection yields a clear notice and identified default, not silent success. Enforce game-defined injury/death/action rules, distinguish service/authority failures and never invent revival capabilities. Local death does not alter cross-game identity or retained memory; separately authorized memory edits are not death effects.

**Content security and privacy (§§4, 13, 15, 19).** Enforce source/audience and forwarding authority, including membership changes before delivery, private replay and truthful privacy receipts. For Agents or composed decision-making implementations, test matched benign/injected content, forged approvals, exfiltration requests and instruction-bearing recalled memory. Report legitimate-task completion and forbidden effects separately; neither refusing everything nor successful gameplay alone establishes useful, secure conformance.

Include authenticated delivery of untrusted content, false clean-context assertions, protected planning inputs and derived disclosures, and authorized autonomous purchasing that remains usable in the presence of ordinary external content without allowing that content to change authority.

**Cross-clause acceptance cases (§§10, 15.2.1, 16.6, 17.1, 18).** Applicable tests MUST also cover:

- Rejection after target death, allegiance or healing-condition changes, safe observation updates and reassessment instead of unchanged retries.
- Narrative-cursor rollback without load-generation reuse; retrieval filtering for ancestry, unknown provenance and derived summaries; independent memory-use and spoiler-disclosure choices, and provenance labels when prior experience is allowed.
- Confirmation invalidation on timeout or changed conditions; only independently authorized behavior while waiting; same-target/intent cooldown enforcement, revalidation after state changes and game-side rate-limit feedback.
- Authoritative budget reservations under concurrency, pending commitments and over-budget rejection; exclusion of real money, external wallets and high-value account assets from generic autonomous budgets; offering free text unable to alter player policies.
- For adopted streaming extensions, shared object schemas across push and query, connection authentication and revocation, event duplication/backpressure and resynchronization; the minimum HTTP binding without negotiated streaming continues declared polling without claiming stream support.

**Clarified contract boundaries (§§3, 5, 6, 9, 10, 11, 16.7, 17.1.1).** Applicable tests MUST also cover data-subject receipt queries versus results issued by the party that actually processed the data; confirmation before action acceptance and no double consumption on replay; read-family freshness versus lease replay; independently authorized result reads after scoped revocation; observation-reference perspective/schema bindings; recovery materialization equivalent to the current revision; target-association lifetime and withdrawal; and the declared recommendation-rate response to repeated opposition.

These are implementation-conformance acceptance requirements to be executed, not claims that this textual revision implemented or ran the mechanisms.

**Agent-quality evaluation, not an admission leaderboard.** Quality evaluations accompanying conformance claims MUST identify the game/environment build, scenario and initial-state fixture, model/provider revision where available, sampling/tool configuration, observation/action limits, time or token budget, termination criteria and trial count. Unavailable details MUST be disclosed, not invented. Reports MUST distinguish protocol violations, task failure, budget exhaustion and infrastructure failure without selectively suppressing failed trials.

Comparative claims SHOULD use matched conditions and report variability, latency and resources alongside success. Memory evaluation SHOULD separate retrieval coverage from answer accuracy with cross-session, temporal, corrected-fact and missing-evidence cases; these results MUST NOT replace portability conformance. A gameplay score or leaderboard position MUST NOT become an unpublished vendor-specific admission requirement. Admission remains based on the published minimum G2A contract.

<a id="section-22"></a>

## 22. Migration and implementation boundary

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
| Inherited `core.events` text/event contracts | Preserve the claimed baseline's requirements; optional player-facing chat use does not silently redefine that feature |
| Legacy operation-directory HTTP error mappings | Retain for legacy peers. The candidate g2a-http-json/draft-1 uses HTTP 200 for domain errors and 4xx/5xx for transport failures only when explicitly negotiated; this is a proposed binding change, not an unchanged mapping |
| Inherited `Binding.kind` | Does not encode the new candidate identifier/version; freeze explicit negotiation without reusing an incompatible enum value |
| `g2a-conformance-statement-1` | Inherited operation-level evidence format, not the complete clause/profile report required by section 21 |
| SDK `0.1.0-dev` | Implementation under review, not a release of this specification |
| New observation candidate | Requires contract/schema, vectors, implementation and independent review |

The next standardization steps are to freeze exact profile fields and digest domains; generate a complete English field catalogue from all operation contracts; reconcile role applicability metadata; finalize binding negotiation/authentication/status/header rules and the versioned conformance-report mapping; add observation and cross-role conformance vectors; and run independent peers and real games. Only then should a stable release claim be considered. SDK adaptation follows the reviewed standard rather than defining it implicitly.

<a id="section-23"></a>

## 23. Illustrative scenarios

**Turn-based companion.** The game advertises visible board and legal-move definitions. The player grants advice only. The agent receives an authorized snapshot and may chat but cannot execute a move. Granting a typed move action later requires approval; the game still checks whose turn it is at execution.

**Proactive combat companion.** The player authorizes combat assistance within the game's declared capabilities. An authorized observation reveals nearby enemies; the companion selects targets and legal attacks, replans as the encounter changes and helps until the objective is met or a stopping condition applies, without asking before every attack. When the player says stop, it schedules no further attacks, reconciles in-flight work, and reports any hit already committed rather than promising to undo it.

**Fog-of-war tactical agent.** A view changes after a team switch. The authority retires the old visibility epoch, discards queued disclosure to the old audience and sends a fresh authorized snapshot. A delayed old delta is rejected even if its revision is numerically greater than the new stream's revision.

**Action timeout.** A purchase or move request reaches the game, its effect is committed, and the response is lost. The Agent queries the original action and operation receipt. It does not resubmit with a new ID. If the authority cannot establish the result, it reports `unknown` and initiates reconciliation rather than claiming no effect.

**Disconnected companion.** The associated player leaves or the declared presence deadline expires. New gameplay planning and actions stop; unsubmitted companion work is cancelled and in-flight effects are reconciled without promising rollback or zero residual token billing. Other online players and ordinary game simulation may continue. Reconnection establishes current presence and authority, reconciles outcomes and refreshes state under section 14.1 before any further gameplay; the previous task stays stopped until the player gives a new instruction. There is no offline activity mode or backlog replay.

**AI service interruption while the player remains online.** The game continues with its declared local fallback. After service recovery, the companion receives only the current authorized state and reconciles outstanding action results; it does not receive a replay of the disconnected gameplay. The player's auto-entry preference does not replace the separate decision to continue after this interruption.

**Observation revision trace (illustrative, not an executable vector).** Assume one authorized stream with fixed instance, world, perspective and schema bindings; `view-9` is the current visibility epoch. Each row follows the previous row:

| Step | Received update | Required interpretation under section 9 |
| --- | --- | --- |
| 1 | `snapshot`, `view-9`, revision `27` | Replace the stream's authorized view atomically; current revision becomes `27` |
| 2 | `delta`, `view-9`, base `27`, revision `30` | Apply atomically; a numerical gap alone is not loss; current revision becomes `30` |
| 3 | Exact duplicate of step 2 | Do not apply twice or regress the view; current revision stays `30` |
| 4 | Recovery `snapshot`, `view-9`, revision `30`, with the same materialized state | Re-establish the complete current baseline without inventing a new revision |
| 5 | `delta`, `view-9`, base `28`, revision `31` | Do not apply: base `28` does not match current `30`; obtain a valid baseline before continuing that chain |
| 6 | Authorized invalidation of `view-9`, followed by `snapshot`, `view-10`, revision `1` | Retire the old view immediately; the new epoch's snapshot establishes a separate baseline |
| 7 | Delayed `delta`, `view-9`, base `30`, revision `99` | Reject the retired context despite its larger revision number |

<a id="section-24"></a>

## 24. References

### 24.1 Normative terminology references

Section 2 adopts only the requirement-language rules from the following references:

- RFC 2119, *Key words for use in RFCs to Indicate Requirement Levels* (BCP 14): https://www.rfc-editor.org/rfc/rfc2119.html
- RFC 8174, *Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words* (BCP 14): https://www.rfc-editor.org/rfc/rfc8174.html

### 24.2 Informative references and inherited design materials

The remaining references are comparative and explanatory unless incorporated explicitly into a normative G2A contract. They do not by themselves impose their transports, platforms or data models. The inherited G2A contracts remain subject to the authority and release-freezing rules in sections 2 and 20. G2A uses the model/operation/binding separation seen in A2A without claiming A2A wire compatibility or inheriting its authorization semantics. Mutable latest links are review references, not release pins.

Research adoption records: [rounds 1–5](../research/g2a-protocol-research-2026-11-13.zh-CN.md) and [rounds 6–10](../research/RESEARCH_ROUNDS_6_10.zh-CN.md).

**Protocol architecture and JSON.**

- A2A Protocol specification: https://a2a-protocol.org/latest/specification/ (mutable latest reference; architectural comparison only).
- RFC 8259, *The JavaScript Object Notation (JSON) Data Interchange Format*: https://www.rfc-editor.org/rfc/rfc8259.html (G2A's stricter input rules are specified separately).
- Existing G2A normative-candidate artifacts linked in section 2.

**Schemas, compatibility and security.**

- JSON Schema 2020-12 Core: https://json-schema.org/draft/2020-12/json-schema-core.html
- JSON Schema 2020-12 Validation (including format annotation/assertion): https://json-schema.org/draft/2020-12/json-schema-validation.html
- RFC 8785 (JCS comparison, not G2A canonicalization): https://www.rfc-editor.org/rfc/rfc8785.html
- RFC 9413 (protocol maintenance): https://www.rfc-editor.org/rfc/rfc9413.html
- RFC 9700, OAuth security BCP: https://www.rfc-editor.org/rfc/rfc9700.html
- RFC 8693, delegation and impersonation: https://www.rfc-editor.org/rfc/rfc8693.html
- MCP security best practices (2025-11-25): https://modelcontextprotocol.io/docs/2025-11-25/tutorials/security/security_best_practices
- InjecAgent (indirect prompt injection): https://arxiv.org/abs/2403.02691v3
- AgentDojo (utility/security evaluation): https://arxiv.org/html/2406.13352v3

**Game actions, events and timing.**

- W3C WoT Thing Description 1.1: https://www.w3.org/TR/wot-thing-description11/
- SayCan: https://arxiv.org/html/2204.01691v2
- RFC 7641 (state observation comparison, no CoAP requirement): https://www.rfc-editor.org/rfc/rfc7641.html
- W3C High Resolution Time, Working Draft 2026-11-06 (clock comparison): https://www.w3.org/TR/2026/WD-hr-time-3-20261106/
- OpenSpiel legal actions: https://openspiel.readthedocs.io/en/latest/api_reference/state_legal_actions.html
- Unity ML-Agents decisions: https://unity-technologies.github.io/ml-agents/Learning-Environment-Design-Agents/#decisions
- PettingZoo AEC and parallel APIs: https://pettingzoo.farama.org/api/aec/ ; https://pettingzoo.farama.org/api/parallel/
- Gymnasium termination and truncation: https://gymnasium.farama.org/tutorials/gymnasium_basics/handling_time_limits/
- MCP Tasks (experimental comparison): https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/tasks
- CloudEvents 1.0.2: https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md
- RFC 9457: https://www.rfc-editor.org/rfc/rfc9457.html

**Memory, provenance and human interaction.**

- W3C PROV-DM (provenance semantics, no required RDF representation): https://www.w3.org/TR/prov-dm/
- ActivityStreams 2.0 (extension preservation comparison): https://www.w3.org/TR/activitystreams-core/
- Generative Agents: https://arxiv.org/html/2304.03442v2
- LongMemEval: https://arxiv.org/html/2410.10813v2
- LoCoMo: https://arxiv.org/abs/2402.17753v1
- Horvitz, Principles of Mixed-Initiative User Interfaces (1999): https://www.microsoft.com/en-us/research/wp-content/uploads/2016/11/chi99horvitz.pdf
- Amershi et al., Guidelines for Human-AI Interaction (2019): https://www.microsoft.com/en-us/research/wp-content/uploads/2019/01/Guidelines-for-Human-AI-Interaction-camera-ready.pdf

**Conformance and evaluation.**

- W3C QA Framework Specification Guidelines: https://www.w3.org/TR/qaframe-spec/
- AgentBench: https://arxiv.org/abs/2308.03688v3
- HELM: https://arxiv.org/abs/2211.09110v2

<a id="section-25"></a>

## 25. Revision history

This is a history of the specification text, not a protocol release log. It records the traceable snapshots available for this review; intermediate revisions have not been reconstructed or invented.

| Editorial revision | Date | Traceability and scope |
| --- | --- | --- |
| `standard-review-2026-11-13-r48` | 2026-11-13 | Committed bilingual review baseline, stored in Git commit `796778b8af2ff8c0c4a54a7434b4c6b5a74ad8ae` on 2026-11-14 |
| `standard-review-2026-11-14-r70` | 2026-11-14 | Existing uncommitted bilingual input to this review; preserved before editing. Per-revision records for the intervening edits were not available for this review |
| `standard-review-2026-11-14-r71` | 2026-11-14 | Synchronized comprehensive review described below; retains working-draft status and allocates no new wire version |

The `r70` input snapshots have these SHA-256 digests: English `e03ce510ab129bf5d7d9a5f3b9874f21697fd2557d46e463a70f4ce10f06029d`; Chinese `901f5038e34e65f2768467ba55a695b46fc4b5e1c2cd720c1772282562b11765`. They identify the actual review inputs, not a published release or a claim that every intermediate edit was audited separately.

### 25.1 Changes in r71

| Classification | Affected sections | Change and compatibility boundary |
| --- | --- | --- |
| Editorial and translation | Opening, 2–5, throughout | Add linked contents and stable cross-language section anchors; improve English grammar; align Chinese Action, generation, slot and Grant terminology and normative strength; distinguish request submission from effect commitment |
| Baseline clarification | 2, 3, 5, 6, 22 | Distinguish candidate authority from inherited contracts; preserve claimed `core.events` obligations; clarify scoped revocation and independent result-read authority; correct privacy-operation callers and receipt-query direction |
| Baseline clarification | 10, 11 | Separate definition, invocation and transport IDs; require applicable confirmation before acceptance; distinguish ordinary reads from deduplicated and lease-renewing operation families |
| Candidate semantic clarification | 9, 23 | Separate effectful active sensing from information queries; retain perspective/schema context; establish current recovery baselines without requiring a new revision per read; define same-state materialization and illustrate revision/epoch handling |
| Policy clarification and translation | 16.3.1, 16.5, 17.1.1 | Apply current policy before effect commitment even after request submission; align recommendation and price wording without changing the established player choices |
| Additional testable profile obligations | 16.7, 17.1.1, 21 | Require explicit target/objective association lifetime and invalidation mapping, and a declared recommendation-rate policy; expand corresponding acceptance coverage. These obligations still require profile encoding and implementation evidence |
| Examples and contract boundaries | 9.2, 18, 21–23 | Label observation placeholders; supply a schema-valid request; identify missing binding negotiation and conformance-report mappings; link exact canonicalization rules; add service-interruption and observation-trace explanations |
| Versioning, references and traceability | 20, 24, 25 | Separate version identifiers; require bilingual revision synchronization; separate normative terminology from informative references; add JSON Schema Validation and preserve traceable input history |

This revision changes only the two specification documents. It does not modify the SDK, inherited schemas, operation registry or runtime. Existing role-count, offline-activity, player-policy and game-authority decisions are retained. Human review, candidate-contract freezing, independent interoperability and production validation remain separate gates under sections 20–22.
