"""资源字节、可信传输见证、声明式 parser 和原子缓存的协议反例；无真实下载。"""

from copy import deepcopy
from hashlib import sha256
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1] / "docs/protocol"


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = load("test_asset_harness", "asset_harness.py")
F = load("test_asset_fixture", "fixtures.py")
C = A.C
ORIGIN = "https://assets.fixture.invalid"
COMPAT = {"profile": "fixture-avatar", "revision": "1", "properties": {}}


def asset(name, issuer, dependencies=(), mutate=None):
    value = {"fixture_format": "fixture-1", "compatibility": deepcopy(COMPAT),
             "dependencies": sorted(child["content_digest"] for child in dependencies),
             "entries": [{"path": name + ".txt", "kind": "file", "content": "fixture data"}], "model": {"label": name}}
    if mutate:
        mutate(value)
    raw = C.codec.canonical(value)
    manifest = {"asset_id": name, "content_digest": sha256(raw).hexdigest(), "byte_size": len(raw),
                "media_type": A.PORTS.MEDIA, "format_version": "fixture-1", "compatibility": deepcopy(COMPAT),
                "dependency_manifests": deepcopy(list(dependencies)), "approved_origins": [ORIGIN],
                "license_claim": "fixture-only", "issuer": issuer, "sandbox_requirements": ["declarative-only"], "locator": ORIGIN + "/" + name}
    response = {"hops": [{"url": manifest["locator"], "tls_verified": True, "resolved": ["1.1.1.1"], "connected_ip": "1.1.1.1"}],
                "chunks": [raw[:10], raw[10:]]}
    return manifest, response


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.start()

    def start(self, *, mutate=None, presentation=True, policy=None):
        features = ["core.session", "core.events", "actions", "resume", "handoff", "avatar", "assets"]
        if presentation:
            features.append("presentation")
        self.f = F.core_fixture(features)
        leaf, leaf_response = asset("leaf", self.f["game"])
        self.manifest, root_response = asset("root", self.f["game"], [leaf], mutate)
        self.f["descriptor"]["avatar_requirements"] = {"accepted_formats": [A.PORTS.MEDIA]}
        self.f["requested"]["forced_avatar"] = {"kind": "manifest", "manifest": deepcopy(self.manifest)}
        if presentation:
            self.f["requested"]["presentation_terms"] = {"mode": "hide_desktop", "device_id": "device-a"}
        self.h = A.AssetHarness(self.f)
        if policy:
            self.h.resource_policy.update(policy)
        self.h.resources.responses = {leaf["locator"]: leaf_response, self.manifest["locator"]: root_response}
        self.h.resources.renderer_profiles = {key: {A.PORTS.PROFILE} for key in ("device-a", "device-b", "fixture-headless")}
        observation = self.h.enroll_device("device-a") if presentation else None
        self.h.enroll_device("device-b")
        self.h.identities["agent-identity"]["device_id"] = "device-a" if presentation else None
        offer = self.send("offer.create", {"entry": "companion", "descriptor_id": "fixture-descriptor", "expected_descriptor_revision": 1,
                                          "requested": self.f["requested"]})
        decision = {"offer_id": offer["offer_id"], "scope_digest": offer["scope_digest"], "allow": True, "remember": False,
                    "launch_permission": False, "decision_ref": "asset-approve"}
        self.h.decisions["asset-approve"] = {"player": self.f["player"], "payload": decision}
        self.send("offer.decide", decision, "player-fixture")
        intent = {"scope_digest": offer["scope_digest"]}
        if presentation:
            intent.update(selected_device="device-a", presentation_observation=observation)
        self.invitation = self.send("invitation.redeem", {"offer_id": offer["offer_id"], "join_intent": intent})
        self.join_payload = {key: self.invitation[key] for key in ("invitation_id", "join_intent")}
        self.send("session.join", self.join_payload, self.invitation["invitation_credential"])
        self.payload = {"session_id": "s1", "manifest": deepcopy(self.manifest), "scope_digest": offer["scope_digest"]}

    def wire(self, op, payload, credential="agent-identity", rid="r1", **kwargs):
        return C.codec.decode(self.h.submit(C.codec.canonical(F.wire_request(op, payload, rid)), credential, now=1000, **kwargs))

    def send(self, *args, **kwargs):
        reply = self.wire(*args, **kwargs)
        self.assertNotIn("error", reply)
        return reply["result"]

    def resolve(self, **kwargs):
        return self.wire("asset.resolve", self.payload, "resource-fixture", **kwargs)

    def acquire(self, jid="admission-s1"):
        return self.send("presentation.acquire", self.h.state["presentation_jobs"][jid]["acquire"], "presentation-fixture", rid=jid)

    def error(self, code, fn):
        with self.assertRaises(C.ContractError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def failed(self, cause):
        reply = self.resolve()
        self.assertIn("error", reply)
        self.assertEqual(reply["error"]["code"], "operation_failed")
        self.assertEqual(reply["error"]["outcome"], "accepted")
        self.assertEqual(self.h.state["asset_receipts"]["r1"]["failure_reason"], cause)
        self.assertEqual(self.h.session.state["session"]["state"], "closed")
        self.assertEqual(self.h.state["asset_cache"], {})
        self.assertIsNone(self.h.state["asset_binding"])
        return reply

    def ready(self):
        self.assertIn("result", self.resolve())
        if "presentation" in self.f["descriptor"]["supported_features"]:
            self.acquire()
        self.h.finish_admission(now=1000)
        return self.send("session.join", self.join_payload, self.invitation["invitation_credential"])

    def handoff(self):
        payload = {"session_id": "s1", "expected_generation": 1, "target_device": "device-b", "decision_ref": "move", "target_proof_ref": "target"}
        self.h.decisions["move"] = {"player": self.f["player"], "payload": payload, "scope_digest": self.payload["scope_digest"]}
        self.h.target_proofs["target"] = {"agent": self.f["agent"], "device_id": "device-b", "session_id": "s1", "expires_at": 100000,
                                        "scope_digest": self.payload["scope_digest"]}
        return self.send("session.handoff", payload, "player-fixture")

    def test_resource_closure_must_be_ready_before_device_or_session(self):
        self.assertFalse(self.h.finish_admission(now=1000)["ready"])
        self.error("temporarily_unavailable", self.acquire)
        receipt = self.resolve()["result"]
        C.validate_type("AssetReceipt", receipt)
        self.assertEqual(receipt["content_digest"], self.manifest["content_digest"])
        self.assertEqual(len(self.h.state["asset_cache"]), 2)
        self.assertFalse(self.h.finish_admission(now=1000)["ready"])
        self.acquire()
        self.assertTrue(self.h.finish_admission(now=1000)["ready"])

    def test_precommit_failure_does_not_publish_any_dependency_or_binding(self):
        with self.assertRaises(A.U.S.H.InjectedFailure):
            self.resolve(fault="before_commit")
        self.assertEqual(self.h.state["asset_cache"], {})
        self.assertEqual(self.h.state["asset_receipts"], {})
        self.assertEqual(len(self.h.resources.trace), 2)
        self.assertIn("result", self.resolve())
        self.assertEqual(len(self.h.resources.trace), 4)

    def test_postcommit_retry_and_new_request_reuse_exact_verified_closure(self):
        with self.assertRaises(A.U.S.H.InjectedFailure):
            self.resolve(fault="after_commit")
        first = self.resolve()["result"]
        self.assertEqual(self.resolve(rid="new-read")["result"], first)
        self.assertEqual(len(self.h.resources.trace), 2)
        self.assertEqual(self.h.resources.parse_calls, 2)

    def test_wrong_role_scope_or_unapproved_manifest_has_no_download(self):
        for credential in ("agent-identity", "player-fixture", "game-fixture", "presentation-fixture"):
            self.error("permission_denied", lambda: self.wire("asset.resolve", self.payload, credential))
        for field, value in (("scope_digest", "0" * 64), ("session_id", "other"),
                             ("manifest", {**self.manifest, "license_claim": "different"})):
            self.error("permission_denied", lambda: self.wire("asset.resolve", {**self.payload, field: value}, "resource-fixture"))
        self.assertEqual(self.h.resources.trace, [])

    def test_manifest_binding_does_not_coerce_boolean_and_integer_properties(self):
        for approved, changed in ((1, True), (0, False), (True, 1), (False, 0)):
            with self.subTest(approved=approved, changed=changed):
                with patch.dict(COMPAT["properties"], {"variant": approved}):
                    self.start()
                self.payload["manifest"]["compatibility"]["properties"]["variant"] = changed
                self.error("permission_denied", self.resolve)
                self.assertEqual(self.h.resources.trace, [])
                self.assertEqual(self.h.state["asset_cache"], {})
                self.assertEqual(self.h.state["asset_receipts"], {})

    def test_same_request_changed_extensions_conflicts_without_new_effects(self):
        self.resolve()
        req = F.wire_request("asset.resolve", self.payload)
        req["extensions"] = {"fixture.note": {"version": "1", "required": False, "value": 1}}
        self.error("id_conflict", lambda: self.h.submit(C.codec.canonical(req), "resource-fixture", now=1000))
        self.assertEqual(self.h.resources.parse_calls, 2)

    def test_digest_mismatch_after_dependency_parse_leaves_no_visible_partial_cache(self):
        response = self.h.resources.responses[self.manifest["locator"]]
        response["chunks"][-1] = response["chunks"][-1][:-1] + b"x"
        self.failed("resource_integrity_error")
        self.assertEqual(self.h.resources.parse_calls, 1)

    def test_stream_too_long_or_truncated_is_not_accepted_as_manifest(self):
        for suffix, cause in ((b"excess", "resource_limit"), (None, "resource_integrity_error")):
            self.start()
            response = self.h.resources.responses[self.manifest["locator"]]
            if suffix is None:
                response["chunks"].pop()
            else:
                response["chunks"].append(suffix)
            self.failed(cause)

    def test_private_mixed_dns_and_unpinned_connection_are_denied(self):
        for change in ({"resolved": ["127.0.0.1"], "connected_ip": "127.0.0.1"},
                       {"resolved": ["1.1.1.1", "169.254.169.254"]}, {"connected_ip": "8.8.8.8"},
                       {"resolved": ["::ffff:127.0.0.1"], "connected_ip": "::ffff:127.0.0.1"}, {"tls_verified": False}):
            self.start()
            self.h.resources.responses[self.manifest["locator"]]["hops"][0].update(change)
            self.failed("resource_policy_denied")

    def test_explicit_private_network_policy_is_still_origin_bound(self):
        self.start(policy={"allow_private_network": True})
        hop = self.h.resources.responses[self.manifest["locator"]]["hops"][0]
        hop.update(resolved=["192.168.1.2"], connected_ip="192.168.1.2")
        self.assertIn("result", self.resolve())

    def test_every_redirect_is_checked_against_manifest_and_scope(self):
        for url in ("https://unapproved.invalid/file", "http://assets.fixture.invalid/file", "https://user:pass@assets.fixture.invalid/file"):
            self.start()
            response = self.h.resources.responses[self.manifest["locator"]]
            response["hops"][0]["redirect_to"] = url
            response["hops"].append({"url": url, "tls_verified": True, "resolved": ["1.1.1.1"], "connected_ip": "1.1.1.1"})
            self.failed("resource_policy_denied")

    def test_safe_redirect_succeeds_without_forwarding_control_credentials(self):
        response = self.h.resources.responses[self.manifest["locator"]]
        url = ORIGIN + "/cdn/root"
        response["hops"][0]["redirect_to"] = url
        response["hops"].append({"url": url, "tls_verified": True, "resolved": ["1.1.1.1"], "connected_ip": "1.1.1.1"})
        result = self.ready()
        trace = C.codec.canonical(self.h.resources.trace)
        self.assertNotIn(result["control_credential"].encode(), trace)
        self.assertNotIn(self.invitation["invitation_credential"].encode(), trace)
        self.assertTrue(all(set(item["headers"]) == {"Accept"} for item in self.h.resources.trace))

    def test_archive_paths_links_and_executable_entries_are_rejected(self):
        for change in ({"path": "../escape.txt"}, {"path": "/abs.txt"}, {"path": "C:/escape.txt"},
                       {"path": "folder\\escape.txt"}, {"kind": "symlink"}, {"path": "run.js"}):
            self.start(mutate=lambda value: value["entries"][0].update(change))
            self.failed("resource_policy_denied")

    def test_unpacked_limit_applies_to_full_closure_not_each_file_separately(self):
        self.start(policy={"max_unpacked_bytes": 15})
        self.failed("resource_limit")
        self.assertEqual(self.h.resources.parse_calls, 2)

    def test_parsed_compatibility_dependencies_and_active_fields_are_checked(self):
        cases = [(lambda v: v["compatibility"].update(revision="2"), "avatar_incompatible"),
                 (lambda v: v.update(dependencies=[]), "resource_integrity_error"),
                 (lambda v: v.update(script="execute()"), "resource_integrity_error")]
        for mutation, cause in cases:
            self.start(mutate=mutation)
            self.failed(cause)

    def test_parsed_compatibility_does_not_coerce_boolean_and_integer_properties(self):
        for declared, actual in ((1, True), (0, False), (True, 1), (False, 0)):
            with self.subTest(declared=declared, actual=actual):
                with patch.dict(COMPAT["properties"], {"variant": declared}):
                    self.start(mutate=lambda value: value["compatibility"]["properties"].update(variant=actual))
                self.failed("avatar_incompatible")
                self.assertEqual(self.h.resources.parse_calls, 2)

    def test_shared_manifest_identity_requires_exact_canonical_properties(self):
        with patch.dict(COMPAT["properties"], {"variant": 1}):
            leaf, _ = asset("shared", self.f["game"])
        identical = deepcopy(leaf)
        identical["compatibility"] = dict(reversed(list(identical["compatibility"].items())))
        root, _ = asset("parent", self.f["game"], [leaf, identical])
        validate = lambda: A.R.validate_manifest_closure(root, self.h.resource_policy, supported_profiles={A.PORTS.PROFILE})
        self.assertEqual(validate()["manifest_count"], 2)
        root["dependency_manifests"][1]["compatibility"]["properties"]["variant"] = True
        self.error("resource_integrity_error", validate)

    def test_license_policy_is_checked_before_download_and_on_cache_reuse(self):
        self.h.resources.allowed_claims.clear()
        self.failed("resource_policy_denied")
        self.assertEqual(self.h.resources.trace, [])
        self.start()
        self.resolve()
        self.h.resources.allowed_claims.clear()
        self.error("approval_stale", self.resolve)
        reply = self.resolve(rid="new-rule")
        self.assertEqual(reply["error"]["code"], "operation_failed")
        self.assertEqual(self.h.state["asset_receipts"]["new-rule"]["failure_reason"], "resource_policy_denied")
        self.assertEqual(len(self.h.resources.trace), 2)

    def test_parser_revision_invalidates_old_receipt_and_requires_new_verification(self):
        self.resolve()
        self.h.resources.parser_revision = "fixture-parser-2"
        self.error("approval_stale", self.resolve)
        self.assertFalse(self.h.finish_admission(now=1000)["ready"])
        self.resolve(rid="parser-2")
        self.assertEqual(self.h.resources.parse_calls, 4)
        self.acquire()
        self.assertTrue(self.h.finish_admission(now=1000)["ready"])

    def test_policy_changes_do_not_expand_frozen_scope_or_publish_old_preparation(self):
        original = deepcopy(self.h.session.state["session"]["scope"])
        self.h.resources.after_prepare = lambda: self.h.resource_policy.update(allow_private_network=True)
        self.error("approval_stale", self.resolve)
        self.assertEqual(self.h.state["asset_cache"], {})
        self.assertEqual(self.h.session.state["session"]["scope"], original)
        self.start()
        self.resolve()
        self.h.resource_policy["allow_private_network"] = 0
        self.error("approval_stale", self.resolve)

    def test_revocation_between_prepare_and_publish_survives_failed_resource_commit(self):
        self.h.resources.after_prepare = lambda: self.send("permission.revoke", {"object_type": "grant", "object_id": "grant-1", "expected_revision": 1}, "player-fixture")
        self.error("grant_revoked", self.resolve)
        self.assertEqual(self.h.state["asset_cache"], {})
        self.assertEqual(self.h.session.state["session"]["state"], "closed")
        self.assertTrue(self.h.state["presentation_jobs"]["admission-s1"]["release_pending"])

    def test_failed_receipt_is_replayable_and_player_status_does_not_claim_success(self):
        self.h.resources.responses[self.manifest["locator"]]["status"] = "timeout"
        original = self.failed("temporarily_unavailable")
        count = len(self.h.resources.trace)
        self.assertEqual(self.resolve(), original)
        self.assertEqual(len(self.h.resources.trace), count)
        payload = {"operation": "asset.resolve", "original_request_id": "r1"}
        status = self.send("operation.get", payload, "player-fixture")
        self.assertEqual(status["state"], "failed")
        self.error("permission_denied", lambda: self.send("operation.get", payload))
        self.h = self.h.restart_from_mock_ledger(now=1000, intact=False)
        self.error("temporarily_unavailable", self.resolve)

    def test_renderer_capability_is_separate_from_successful_parser(self):
        self.resolve()
        self.h.resources.renderer_profiles["device-a"].clear()
        self.error("avatar_incompatible", self.acquire)
        self.assertEqual(self.h.devices["device-a"].render_calls, 0)
        self.assertEqual(self.h.finish_admission(now=1000)["state"], "closed")

    def test_target_renderer_failure_closes_transfer_without_restoring_old_writer(self):
        self.ready()
        transfer = self.handoff()
        self.h.resources.renderer_profiles["device-b"].clear()
        result = self.h.advance_transfer(transfer["transfer_id"], now=1000)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.h.session.state["session"]["control_generation"], 2)
        self.assertEqual(self.h.devices["device-b"].render_calls, 0)

    def test_assets_without_presentation_still_require_resource_and_renderer_proofs(self):
        self.start(presentation=False)
        self.assertFalse(self.h.finish_admission(now=1000)["ready"])
        self.resolve()
        self.assertTrue(self.h.finish_admission(now=1000)["ready"])

    def test_mock_restart_preserves_verified_cache_but_not_old_write_authority(self):
        self.ready()
        self.h = self.h.restart_from_mock_ledger(now=1000)
        self.assertEqual(len(self.h.state["asset_cache"]), 2)
        self.assertIn("result", self.resolve())
        self.assertEqual(self.h.resources.parse_calls, 2)
        result = self.send("session.resume", {"session_id": "s1", "expected_generation": 1, "device_id": "device-a"})
        self.assertEqual(result["status"], "pending")

    def test_malformed_transport_witness_is_a_bounded_resource_failure(self):
        self.h.resources.responses[self.manifest["locator"]]["hops"] = [{}]
        self.failed("resource_policy_denied")

    def test_resource_failure_commit_boundaries_preserve_exact_failed_receipt(self):
        self.h.resources.responses[self.manifest["locator"]]["status"] = "timeout"
        with self.assertRaises(A.U.S.H.InjectedFailure):
            self.resolve(fault="before_commit")
        self.assertEqual(self.h.session.state["session"]["state"], "active")
        self.assertEqual(self.h.state["asset_receipts"], {})
        with self.assertRaises(A.U.S.H.InjectedFailure):
            self.resolve(fault="after_commit")
        sequence = self.h.session.state["session"]["sequence"]
        self.assertEqual(self.resolve()["error"]["outcome"], "accepted")
        self.assertEqual(self.h.session.state["session"]["sequence"], sequence)

    def test_no_presentation_resume_cannot_bypass_changed_resource_parser(self):
        self.start(presentation=False)
        self.ready()
        self.h.resources.parser_revision = "fixture-parser-2"
        self.error("temporarily_unavailable", lambda: self.send("session.resume", {"session_id": "s1", "expected_generation": 1}))
        self.assertEqual(self.h.session.state["session"]["control_generation"], 1)

    def test_handoff_uses_verified_cache_and_independent_target_renderer(self):
        self.ready()
        transfer = self.handoff()
        self.send("presentation.release", {"session_id": "s1", "generation": 1, "device_id": "device-a"}, "presentation-fixture")
        self.h.advance_transfer(transfer["transfer_id"], now=1000)
        self.acquire("presentation-" + transfer["transfer_id"])
        self.assertEqual(self.h.advance_transfer(transfer["transfer_id"], now=1000)["status"], "ready")
        self.assertEqual(len(self.h.resources.trace), 2)
        self.assertEqual(self.h.resources.parse_calls, 2)


if __name__ == "__main__":
    unittest.main()
