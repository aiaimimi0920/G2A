"""独立 fixture 的跨对象反例，及真实 FlowModel 状态到结果契约的接缝。"""

from copy import deepcopy
from hashlib import sha256
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / "docs" / "protocol"


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = load("relations_under_test", "relations.py")
F = load("fixtures_under_test", "fixtures.py")
M = load("model_under_test", "flow_model.py")


class RelationTests(unittest.TestCase):
    def setUp(self):
        self.f = F.core_fixture()

    def scope(self):
        R.validate_scope(self.f["scope"], self.f["descriptor"], self.f["requested"], now=1000,
                         verified_audiences=[self.f["player"], self.f["agent"]])

    def reject(self, fn, code=None):
        with self.assertRaises(R.ContractError) as caught:
            fn()
        if code:
            self.assertEqual(caught.exception.code, code)

    def write(self, **overrides):
        args = dict(now=1000, principal=self.f["agent"], generation=1, transport_epoch="transport-1")
        args.update(overrides)
        R.validate_session_write(self.f["session"], self.f["grant"], **args)

    def test_independent_valid_scope_grant_and_write(self):
        self.scope()
        R.validate_grant(self.f["grant"], self.f["scope"], now=1000)
        self.write()
        self.assertFalse(self.f["scope"]["effective_policy"]["proactive_chat"])

    def test_same_display_subject_different_issuer_is_not_same_principal(self):
        alien = deepcopy(self.f["agent"])
        alien["issuer"] = "other-provider"
        self.reject(lambda: self.write(principal=alien), "permission_denied")

    def test_scope_cannot_expand_authority(self):
        mutations = [lambda s: s["action_ids"].append("admin-reset"),
                     lambda s: s["audiences"].append(F.principal("bob", "player")),
                     lambda s: s["context_categories"].append("private-inventory"),
                     lambda s: s["effective_policy"].update(proactive_chat=True),
                     lambda s: s.update(trust_profile="local-verified"),
                     lambda s: s.update(version="0.1.0-dev"),
                     lambda s: s["instance"].update(epoch="different"),
                     lambda s: s.update(descriptor_revision=2)]
        for mutation in mutations:
            self.f = F.core_fixture()
            mutation(self.f["scope"])
            self.reject(self.scope)

    def test_approval_binds_action_definition_not_just_id(self):
        self.f["descriptor"]["actions"][0]["effect_class"] = "read_only"
        self.reject(self.scope, "approval_stale")
        self.f = F.core_fixture()
        self.f["scope"]["approved_action_digests"] = {}
        self.reject(self.scope, "approval_stale")

    def test_initial_time_is_not_moved_by_rechecking(self):
        self.f["scope"]["expires_at"] = 300500
        self.reject(self.scope, "invitation_expired")
        self.f = F.core_fixture()
        self.f["scope"]["limits"]["receipt_retention_ms"] = 299000
        self.reject(self.scope, "negotiation_failed")

    def test_current_grant_and_write_fences(self):
        for overrides, code in (({"now": 120000}, "session_closed"), ({"generation": 2}, "stale_controller"),
                                ({"transport_epoch": "transport-2"}, "stale_transport"),
                                ({"device_id": "unapproved"}, "permission_denied")):
            self.reject(lambda: self.write(**overrides), code)
        self.f["grant"]["state"] = "revoked"
        self.reject(self.write, "grant_revoked")

    def test_grant_cannot_be_used_before_frozen_start(self):
        self.f["session"]["scope"]["created_at"] = 2000
        self.f["grant"]["scope"] = deepcopy(self.f["session"]["scope"])
        self.f["grant"]["scope_digest"] = R.codec.digest("scope", self.f["grant"]["scope"])
        self.reject(self.write, "grant_revoked")
        self.write(now=2000)

    def test_closed_or_pending_session_does_not_write(self):
        self.f["session"]["ready"] = False
        self.reject(self.write, "session_not_writable")
        self.f["session"].update(state="closed", close_reason="left")
        self.reject(self.write, "session_closed")

    def test_result_read_is_independent_but_cannot_expand(self):
        read = {"session_id": "s1", "action_ids": ["a1"], "access_revision": 1, "read_until": 300000}
        self.f["session"].update(state="closed", ready=False, close_reason="left")
        R.validate_result_read(read, "s1", "a1", now=300000, access_revision=1)
        self.reject(lambda: R.validate_result_read(read, "s1", "a2", now=1, access_revision=1), "permission_denied")
        self.reject(lambda: R.validate_result_read(read, "s1", "a1", now=300001, access_revision=1), "result_expired")
        self.reject(lambda: R.validate_result_read(read, "s1", "a1", now=1, access_revision=2), "permission_denied")
        self.reject(lambda: R.validate_result_read(read, "s1", "a1", now=1, access_revision=1, revoked=True), "permission_denied")

    def test_audience_uses_membership_incarnation(self):
        agent, player = self.f["agent"], self.f["player"]
        members = {R.principal_key(agent): 1, R.principal_key(player): 1}
        envelope = {"version": "fixture-only", "session_id": "s1", "id": "m1", "type": "chat.message",
                    "sender": agent, "audience": [player], "payload": {"channel": "private", "text": "hello",
                    "provenance": [], "source_refs": []}, "extensions": {}}
        frozen = R.validate_envelope_audience(envelope, self.f["session"], authenticated_sender=agent, current_members=members)
        self.assertTrue(R.can_deliver(player, frozen, members, [agent, player]))
        del members[R.principal_key(player)]
        self.assertFalse(R.can_deliver(player, frozen, members, [agent, player]))
        members[R.principal_key(player)] = 2
        self.assertFalse(R.can_deliver(player, frozen, members, [agent, player]))

    def test_minimal_core_and_resume_dependencies(self):
        self.f = F.core_fixture(["core.session", "core.events"])
        self.scope()
        self.assertEqual(self.f["scope"]["action_ids"], [])
        self.f = F.core_fixture(["core.session", "core.events", "resume"])
        self.scope()
        self.f["scope"]["ledger_durability"] = self.f["requested"]["ledger_durability"] = "volatile"
        self.reject(self.scope, "resume_denied")

    def test_chat_sender_must_be_current_and_allowed_for_channel(self):
        player, agent = self.f["player"], self.f["agent"]
        outsider = F.principal("bob", "player")
        members = {R.principal_key(p): 1 for p in (player, agent, outsider)}
        envelope = {"version": "fixture-only", "session_id": "s1", "id": "m1", "type": "chat.message",
                    "sender": outsider, "audience": [player], "payload": {"channel": "private", "text": "hello",
                    "provenance": [], "source_refs": []}, "extensions": {}}
        def validate():
            return R.validate_envelope_audience(envelope, self.f["session"],
                                               authenticated_sender=envelope["sender"], current_members=members)
        self.reject(validate, "permission_denied")
        self.f["session"]["scope"]["audiences"].append(outsider)
        self.reject(validate, "permission_denied")
        envelope["sender"] = agent
        validate()
        del members[R.principal_key(agent)]
        self.reject(validate, "permission_denied")
        self.f["session"]["scope"]["features"].append("team")
        envelope["sender"] = outsider
        envelope["payload"]["channel"] = "team"
        envelope["expected_membership_revision"] = 1
        validate()
        envelope["expected_membership_revision"] = 2
        self.reject(validate, "membership_conflict")

    def test_game_context_authority_is_not_required_to_be_chat_member(self):
        game, player = self.f["game"], self.f["player"]
        envelope = {"version": "fixture-only", "session_id": "s1", "id": "c1", "type": "game.context",
                    "sender": game, "audience": [player], "payload": {"category": "room", "content": {},
                    "provenance": []}, "extensions": {}}
        frozen = R.validate_envelope_audience(envelope, self.f["session"], authenticated_sender=game,
                                              current_members={R.principal_key(player): 1})
        self.assertEqual(frozen, {R.principal_key(player): 1})

    def test_chat_cannot_bypass_channel_checks_with_generic_envelope(self):
        agent, player = self.f["agent"], self.f["player"]
        envelope = {"version": "fixture-only", "session_id": "s1", "id": "m1", "type": "chat.message",
                    "sender": agent, "audience": [player], "payload": {}, "extensions": {}}
        self.reject(lambda: R.validate_envelope_audience(envelope, self.f["session"], authenticated_sender=agent,
                    current_members={R.principal_key(p): 1 for p in (agent, player)}), "invalid_message")

    def test_required_extension_and_immutable_selection(self):
        ext = {"version": "1", "required": True, "value": {"mode": "fixture"}}
        self.f["descriptor"]["extensions"]["example.fixture"] = ext
        self.reject(self.scope, "feature_unsupported")
        self.f["requested"]["extensions"]["example.fixture"] = deepcopy(ext)
        self.f["scope"]["extensions"]["example.fixture"] = deepcopy(ext)
        self.scope()
        self.f["scope"]["extensions"]["example.fixture"]["value"]["mode"] = "changed"
        self.reject(self.scope, "approval_stale")

    def test_required_companion_policy_extension_is_not_silently_dropped(self):
        self.f["requested"]["companion_defaults"]["extensions"]["example.required"] = {
            "version": "1", "required": True, "value": {"mode": "must-keep"}}
        self.reject(self.scope, "negotiation_failed")

    def test_relay_privacy_is_explicit(self):
        relay = F.principal("relay", "service")
        for binding in (self.f["scope"]["binding"], self.f["descriptor"]["bindings"][0], self.f["requested"]["bindings"][0]):
            binding.update(kind="outbound-relay", relay_identity=relay)
        self.reject(self.scope, "negotiation_failed")
        for obj in (self.f["scope"], self.f["descriptor"], self.f["requested"]):
            obj["privacy_model"]["relay_plaintext"] = True
            obj["privacy_model"]["visible_to"].append(relay)
        self.scope()

    def test_resource_closure_checks_every_dependency_before_download(self):
        manifest = {"asset_id": "fox", "content_digest": "0" * 64, "byte_size": 10,
                    "media_type": "application/fixture", "format_version": "1",
                    "compatibility": {"profile": "fixture", "revision": "1", "properties": {}},
                    "dependency_manifests": [], "approved_origins": ["https://assets.invalid"],
                    "locator": "https://assets.invalid/fox", "license_claim": "fixture-only",
                    "issuer": self.f["game"], "sandbox_requirements": ["no-script"]}
        policy = {"approved_origins": ["https://assets.invalid"], "max_total_bytes": 20,
                  "max_unpacked_bytes": 20, "max_dependencies": 1, "max_depth": 2,
                  "accepted_media_types": ["application/fixture"], "allow_private_network": False}
        def validate():
            return R.validate_manifest_closure(manifest, policy, supported_profiles={("fixture", "1")})
        self.assertEqual(validate(), {"manifest_count": 1, "declared_bytes": 10})
        child = deepcopy(manifest)
        child.update(asset_id="texture", content_digest="1" * 64, locator="https://evil.invalid/texture")
        manifest["dependency_manifests"] = [child]
        self.reject(validate, "resource_policy_denied")
        child["locator"] = "https://assets.invalid/texture"
        self.assertEqual(validate()["declared_bytes"], 20)
        child["byte_size"] = 11
        self.reject(validate, "resource_policy_denied")
        child["byte_size"] = 10
        child["asset_id"] = "fox"
        self.reject(validate, "resource_policy_denied")


    def test_shared_resource_subtree_depth_is_checked_on_every_path(self):
        def node(name, children=()):
            return {"asset_id": name, "content_digest": sha256(name.encode("utf-8")).hexdigest(), "byte_size": 1,
                    "media_type": "application/fixture", "format_version": "1",
                    "compatibility": {"profile": "fixture", "revision": "1", "properties": {}},
                    "dependency_manifests": list(children), "approved_origins": ["https://assets.invalid"],
                    "locator": "https://assets.invalid/" + name, "license_claim": "fixture-only",
                    "issuer": self.f["game"], "sandbox_requirements": []}
        shared = node("shared", [node("leaf")])
        branch = node("branch", [deepcopy(shared)])
        root = node("root", [shared, branch])
        policy = {"approved_origins": ["https://assets.invalid"], "max_total_bytes": 5,
                  "max_unpacked_bytes": 5, "max_dependencies": 4, "max_depth": 3,
                  "accepted_media_types": ["application/fixture"], "allow_private_network": False}
        def validate():
            return R.validate_manifest_closure(root, policy, supported_profiles={("fixture", "1")})
        # 浅路径先缓存 shared；深路径不能因此漏掉位于第 4 层的 leaf。
        self.reject(validate, "resource_policy_denied")
        root["dependency_manifests"].reverse()
        self.reject(validate, "resource_policy_denied")
        policy["max_depth"] = 4
        self.assertEqual(validate(), {"manifest_count": 4, "declared_bytes": 4})


class ModelContractSeamTests(unittest.TestCase):
    def opened(self):
        m = M.FlowModel(["actions", "resume", "handoff"], durable=True)
        oid = m.create_offer("player-proof", "game")
        m.decide("player-proof", oid)
        iid = m.redeem("agent-proof", oid, device=None)
        sid, _ = m.join("agent-proof", iid)
        m.request(sid)
        return m, sid

    def projected_result(self, m, sid):
        raw = m.query("agent-proof", sid)
        # 仅投影状态/效果及 fixture ID；时间是逻辑时钟换算，不是实际服务器时间证明。
        result = {"request_id": "a1", "session_id": sid, "state": raw["state"], "effect": raw["effect"],
                  "result_revision": 0, "query_until": (m.sessions[sid]["read_until"] or 600) * 1000}
        R.checks.validate_type("ActionResult", result)
        return result

    def test_executing_close_resume_handoff_are_unknown_not_none(self):
        for transition in ("close", "resume", "handoff"):
            m, sid = self.opened()
            m.claim("game-proof", sid)
            if transition == "close":
                m.close(sid)
            elif transition == "resume":
                m.resume("agent-proof", sid, 1, "r1")
            else:
                m.handoff("player-proof", sid, "target")
            result = self.projected_result(m, sid)
            self.assertEqual((result["state"], result["effect"]), ("unknown", "undetermined"))

    def test_pending_close_is_cancelled_without_effect(self):
        m, sid = self.opened()
        m.close(sid)
        result = self.projected_result(m, sid)
        self.assertEqual((result["state"], result["effect"]), ("cancelled", "none"))
