"""独立手写的契约 fixture；固定主体/资源，不是发现或认证服务。

fixture-only 仅用于本地设计验证，不登记为可部署 wire 版本。
"""

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys


SPEC = importlib.util.spec_from_file_location("g2a_fixture_codec", Path(__file__).with_name("codec.py"))
codec = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = codec
SPEC.loader.exec_module(codec)


def principal(subject, kind):
    return {"issuer": "fixture-enrollment", "subject": subject, "kind": kind}


def core_fixture(features=None):
    player, agent, game = principal("alice", "player"), principal("fox", "agent"), principal("key-quest", "game")
    features = sorted(features or ["core.session", "core.events", "actions"])
    limits = {"message_bytes": 65536, "event_page_size": 64, "max_pending_actions": 32,
              "session_count": 2 if "multi-session" in features else 1, "event_retention_ms": 300000,
              "receipt_retention_ms": 900000, "result_retention_ms": 300000,
              "lease_period_ms": 120000, "resume_window_ms": 120000 if "resume" in features else 0}
    privacy = {"visible_to": [game, agent, player], "relay_plaintext": False, "retention_notice": "fixture only"}
    instance = {"game": game, "instance_id": "fixture-instance", "epoch": "epoch-1"}
    binding = {"kind": "direct-http", "endpoint": "https://fixture.invalid/g2a/operations", "peer_identity": game}
    definition = {"id": "find-key", "revision": 1, "schema_profile": "g2a-value-schema-1",
                  "parameters": {"type": "object", "properties": {"room": {"type": "string", "enum": ["hall"], "maxLength": 32}},
                                 "required": ["room"], "additionalProperties": False},
                  "result_schema": {"type": "object", "properties": {"item": {"type": "string", "maxLength": 32}},
                                    "required": ["item"], "additionalProperties": False},
                  "allowed_actors": [agent], "requires_per_action_consent": False,
                  "maximum_duration_ms": 30000, "cancellation": "between_steps", "effect_class": "irreversible"}
    actions = [definition] if "actions" in features else []
    descriptor = {"descriptor_id": "fixture-descriptor", "revision": 1, "instance": instance,
                  "supported_versions": ["fixture-only"], "bindings": [binding], "trust_profiles": ["test-enrolled"],
                  "ledger_durabilities": ["volatile", "durable"] if "resume" in features else ["volatile"],
                  "supported_features": features, "required_features": ["core.session", "core.events"],
                  "privacy_model": privacy, "policy_defaults": {"spoilers": "avoid_unknown", "proactive_chat": True, "extensions": {}},
                  "context_categories": ["room"], "actions": actions, "limits": limits, "extensions": {}}
    requested = {"player": player, "agent": agent, "supported_versions": ["fixture-only"], "bindings": [binding],
                 "trust_profiles": ["test-enrolled"], "privacy_model": privacy, "supported_features": features,
                 "required_features": [], "action_ids": [d["id"] for d in actions], "context_categories": ["room"],
                 "audiences": [player, agent], "policy": {"proactive_chat": False, "extensions": {}},
                 "companion_defaults": {"extensions": {}}, "limits": limits, "maximum_grant_duration_ms": 300000,
                 "ledger_durability": "durable" if "resume" in features else "volatile", "extensions": {}}
    scope = {"player": player, "agent": agent, "instance": instance, "version": "fixture-only", "binding": binding,
             "trust_profile": "test-enrolled", "features": features, "descriptor_revision": 1,
             "action_ids": [d["id"] for d in actions], "approved_action_digests": {d["id"]: codec.digest("action-definition", d) for d in actions},
             "context_categories": ["room"], "audiences": sorted([player, agent], key=codec.canonical),
             "effective_policy": {"spoilers": "avoid_unknown", "proactive_chat": False, "extensions": {}},
             "privacy_model": privacy, "result_retention_ms": 300000, "ledger_durability": requested["ledger_durability"],
             "limits": limits, "created_at": 0, "expires_at": 300000, "extensions": {}}
    grant = {"grant_id": "g1", "scope": scope, "scope_digest": codec.digest("scope", scope), "approver": player,
             "consent_evidence_ref": "fixture-consent-1", "revision": 1, "state": "active", "expires_at": 300000}
    session = {"session_id": "s1", "scope": scope, "grant_id": "g1", "state": "active", "instance_epoch": "epoch-1",
               "transport_epoch": "transport-1", "control_generation": 1, "lease_deadline": 120000,
               "capabilities_revision": 1, "membership_revision": 1, "sequence": 0, "ready": True}
    # 每个边界对象独立拷贝，测试修改 scope 不会同时悄悄修改 grant/request。
    return {key: deepcopy(value) for key, value in {"player": player, "agent": agent, "game": game,
            "descriptor": descriptor, "requested": requested, "scope": scope, "grant": grant,
            "session": session, "action": definition}.items()}


def wire_request(operation, payload, request_id="r1"):
    return {"version": "fixture-only", "operation": operation, "request_id": request_id,
            "payload": deepcopy(payload), "extensions": {}}


def relay_fixture(features=None):
    """固定已批准 Relay 的可信登记；不存在真实 URL 连接或身份认证。"""
    fixture = core_fixture(features)
    relay = principal("relay", "service")
    origin = "https://relay.fixture.invalid"
    binding = {"kind": "outbound-relay", "endpoint": origin + "/g2a/operations",
               "peer_identity": fixture["game"], "relay_identity": relay}
    privacy = {**fixture["scope"]["privacy_model"], "relay_plaintext": True,
               "visible_to": fixture["scope"]["privacy_model"]["visible_to"] + [relay]}
    for target in (fixture["descriptor"], fixture["requested"]):
        target.update(bindings=[deepcopy(binding)], privacy_model=deepcopy(privacy))
    for scope in (fixture["scope"], fixture["grant"]["scope"], fixture["session"]["scope"]):
        scope.update(binding=deepcopy(binding), privacy_model=deepcopy(privacy))
    fixture["grant"]["scope_digest"] = codec.digest("scope", fixture["scope"])
    fixture.update(relay_origin=origin, relay_game_audience="https://game.fixture.invalid/g2a/operations")
    common = {"instance": fixture["scope"]["instance"], "relay_identity": relay, "relay_origin": origin,
              "issued_at": 0, "expires_at": 900000, "state": "active"}
    fixture["relay_enrollments"] = {
        "relay-" + role + "-identity": {**deepcopy(common), "role": lane, "principal": deepcopy(fixture[role])}
        for role, lane in (("player", "relay_controller"), ("agent", "relay_agent"), ("game", "relay_game"))}
    fixture["relay_pairings"] = {"pairing-fixture": {**deepcopy(common), "proof_ref": "pairing-fixture",
        "controller": deepcopy(fixture["player"]), "agent_principals": [deepcopy(fixture["agent"])],
        "control_principals": [deepcopy(fixture["player"])], "limits": deepcopy(fixture["scope"]["limits"]),
        "game_authority_ref": "game-authority-fixture", "consent_evidence_ref": "relay-consent-fixture"}}
    return fixture
