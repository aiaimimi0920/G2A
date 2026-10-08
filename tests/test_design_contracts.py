"""草案结构、角色与能力契约；不是实际身份/网络/数据库验收。"""

from copy import deepcopy
import importlib.util
import itertools
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1] / "docs" / "protocol"
SPEC = importlib.util.spec_from_file_location("design_contract_checks", ROOT / "contract_checks.py")
checks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checks)
C = checks.catalog
SCHEMA = checks.SCHEMA
CORE = ["core.session", "core.events"]
ALL = list(C.FEATURE_DEPENDENCIES)


def sample(spec):
    """仅生成结构见证；不能将该生成器当作独立业务场景。"""
    if "$ref" in spec:
        name = spec["$ref"].rsplit("/", 1)[1]
        special = {"Features": CORE, "Digest": "0" * 64, "Version": "fixture-only",
                   "Error": {"code": "unauthenticated", "category": "authentication",
                             "retry": "after_reauth", "outcome": "not_accepted", "details": {}}}
        return deepcopy(special[name]) if name in special else sample(SCHEMA["$defs"][name])
    if "const" in spec:
        return spec["const"]
    if "enum" in spec:
        return spec["enum"][0]
    for alternative in ("oneOf", "anyOf"):
        if alternative in spec:
            return sample(spec[alternative][0])
    if "allOf" in spec and "type" not in spec:
        value = sample(spec["allOf"][0])
        for part in spec["allOf"][1:]:
            for key, field in part.get("properties", {}).items():
                if "const" in field:
                    value[key] = field["const"]
        return value
    kind = spec["type"]
    if kind == "object":
        return {key: sample(spec["properties"][key]) for key in spec.get("required", [])}
    if kind == "array":
        item = spec["items"]
        if "$ref" in item:
            item = SCHEMA["$defs"][item["$ref"].rsplit("/", 1)[1]]
        if spec.get("uniqueItems") and "enum" in item:
            return item["enum"][:spec.get("minItems", 0)]
        return [sample(spec["items"]) for _ in range(spec.get("minItems", 0))]
    return {"string": "fixture", "integer": spec.get("minimum", 0), "boolean": False, "null": None}[kind]


def request(name):
    return {"version": "fixture-only", "operation": name, "request_id": "r1", "extensions": {},
            "payload": sample(C.ref(C.OPERATIONS[name]["input"]))}


class ContractTests(unittest.TestCase):
    def assert_rejected(self, fn, code=None):
        with self.assertRaises(checks.ContractError) as caught:
            fn()
        if code:
            self.assertEqual(caught.exception.code, code)

    def test_meta_schema_and_local_references(self):
        Draft202012Validator.check_schema(SCHEMA)
        def walk(value):
            if isinstance(value, dict):
                if "$ref" in value:
                    self.assertTrue(value["$ref"].startswith("#/$defs/"))
                    self.assertIn(value["$ref"].split("/")[-1], SCHEMA["$defs"])
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(SCHEMA)

    def test_generated_files_match_source(self):
        self.assertEqual(json.loads((ROOT / "contracts.schema.json").read_text(encoding="utf-8")), SCHEMA)
        disk = json.loads((ROOT / "operations.json").read_text(encoding="utf-8"))
        self.assertEqual(disk["operations"], C.OPERATIONS)
        self.assertEqual(disk["features"], C.FEATURE_DEPENDENCIES)
        self.assertEqual(disk["errors"], C.ERRORS)

    def test_all_operation_input_and_output_shapes(self):
        for name, metadata in C.OPERATIONS.items():
            with self.subTest(operation=name):
                value = request(name)
                checks.validate_request(checks.codec.canonical(value))
                response = {"request_id": "r1", "result": sample(C.ref(metadata["output"]))}
                checks.validate_reply(name, "r1", response)
                value["payload"]["unexpected_standard_field"] = True
                self.assert_rejected(lambda: checks.validate_request(checks.codec.canonical(value)))

    def test_each_required_input_field_is_required(self):
        for name, metadata in C.OPERATIONS.items():
            spec = C.TYPES[metadata["input"]]
            while "$ref" in spec:
                spec = C.TYPES[spec["$ref"].rsplit("/", 1)[1]]
            for key in spec["required"]:
                with self.subTest(operation=name, missing=key):
                    value = request(name)
                    del value["payload"][key]
                    self.assert_rejected(lambda: checks.validate_request(checks.codec.canonical(value)))

    def test_all_feature_combinations(self):
        # 全枚举 2^11 个能力集合；这是依赖图检查，不是所有业务交错。
        for bits in itertools.product((False, True), repeat=len(ALL)):
            selected = [name for name, enabled in zip(ALL, bits) if enabled]
            valid = set(CORE) <= set(selected)
            valid &= all(set(C.FEATURE_DEPENDENCIES[name]) <= set(selected) for name in selected)
            with self.subTest(features=selected):
                if valid:
                    checks.validate_features(selected, durable=True)
                else:
                    self.assert_rejected(lambda: checks.validate_features(selected, durable=True))
        self.assert_rejected(lambda: checks.validate_features(CORE + ["resume"]), "resume_denied")
        self.assert_rejected(lambda: checks.validate_features(CORE + ["actions", "actions"], durable=True))

    def test_route_role_matrix(self):
        roles = set(role for op in C.OPERATIONS.values() for role in op["roles"]) | {"visitor"}
        for name, metadata in C.OPERATIONS.items():
            self.assertIn(metadata["feature"], ALL)
            self.assertTrue(metadata["semantic_guard"])
            for role in roles:
                lane = "management" if role == "game" else metadata["lane"]
                with self.subTest(operation=name, role=role):
                    if role in metadata["roles"]:
                        checks.authorize_route(name, role, lane, ALL)
                        self.assert_rejected(lambda: checks.authorize_route(name, role, "unregistered", ALL))
                        self.assert_rejected(lambda: checks.authorize_route(name, role, lane, []), "feature_unsupported")
                    else:
                        self.assert_rejected(lambda: checks.authorize_route(name, role, lane, ALL), "permission_denied")

    def test_relay_cannot_cross_control_or_management_lanes(self):
        checks.authorize_relay_inner("relay_agent", "agent", "offer.create", ALL)
        checks.authorize_relay_inner("relay_controller", "player", "offer.decide", ALL)
        for outer, inner, name in (("relay_agent", "player", "offer.decide"),
                                   ("relay_agent", "executor", "action.claim"),
                                   ("relay_controller", "game", "permission.revoke"),
                                   ("relay_controller", "player", "launch.request"),
                                   ("relay_game", "agent", "session.join")):
            self.assert_rejected(lambda: checks.authorize_relay_inner(outer, inner, name, ALL), "permission_denied")
        call = request("relay.call")
        call["payload"]["call"]["operation_request"] = request("action.claim")
        self.assert_rejected(lambda: checks.validate_request(checks.codec.canonical(call)))

    def test_explicit_approval_conditions(self):
        value = request("offer.decide")
        value["payload"]["remember"] = True
        self.assert_rejected(lambda: checks.validate_request(checks.codec.canonical(value)))
        value["payload"].update(allow=True, rule_expires_at=100, maximum_grant_duration_ms=50)
        checks.validate_request(checks.codec.canonical(value))
        value["payload"]["allow"] = False
        self.assert_rejected(lambda: checks.validate_request(checks.codec.canonical(value)))

    def test_team_revision_and_envelope_version(self):
        value = request("chat.send")
        value["payload"]["payload"]["channel"] = "team"
        self.assert_rejected(lambda: checks.validate_request(checks.codec.canonical(value)))
        value["payload"]["expected_membership_revision"] = 1
        value["payload"]["version"] = value["version"]
        checks.validate_request(checks.codec.canonical(value))
        value["payload"]["version"] = "other-version"
        self.assert_rejected(lambda: checks.validate_request(checks.codec.canonical(value)), "unsupported_version")

    def test_cursor_is_not_cross_session(self):
        value = request("session.events")
        value["payload"]["cursor"]["session_id"] = "other-session"
        self.assert_rejected(lambda: checks.validate_request(checks.codec.canonical(value)), "invalid_cursor")

    def test_reply_correlation_and_exclusive_result(self):
        name = "session.handoff"
        response = {"request_id": "r1", "result": sample(C.ref(C.OPERATIONS[name]["output"]))}
        checks.validate_reply(name, "r1", response)
        self.assert_rejected(lambda: checks.validate_reply(name, "other", response))
        response["error"] = sample(C.ref("Error"))
        self.assert_rejected(lambda: checks.validate_reply(name, "r1", response))

    def test_error_directory_semantics(self):
        for code, rule in C.ERRORS.items():
            error = {key: value for key, value in rule.items() if key != "http_status"}
            error.update(code=code, details={})
            if code == "history_gap":
                error["details"] = {"snapshot": sample(C.ref("RecoverySnapshot")),
                                    "next_cursor": sample(C.ref("Cursor")), "unresolved_actions": []}
            with self.subTest(code=code):
                self.assertEqual(checks.validate_error(error), rule["http_status"])
                error["outcome"] = "accepted" if error["outcome"] != "accepted" else "not_accepted"
                self.assert_rejected(lambda: checks.validate_error(error), "invalid_error_contract")

    def test_public_views_do_not_contain_credentials(self):
        for typename in ("PublicDescriptor", "OfferView", "SessionView", "TransferView", "OperationView"):
            value = sample(C.ref(typename))
            value["control_credential"] = "should-not-be-here"
            self.assert_rejected(lambda: checks.validate_type(typename, value))
        output = C.OPERATIONS["session.handoff"]["output"]
        view = sample(C.ref(output))
        view["result_read_handle"] = "not-for-player"
        self.assert_rejected(lambda: checks.validate_type(output, view))

    def test_result_effect_and_control_delivery_invariants(self):
        value = sample(C.ref("ActionResult"))
        for state, effect in (("unknown", "none"), ("succeeded", "undetermined"),
                              ("cancelled", "committed"), ("pending", "partial")):
            value.update(state=state, effect=effect)
            self.assert_rejected(lambda: checks.validate_type("ActionResult", value))
        value.update(state="failed", effect="partial")
        checks.validate_type("ActionResult", value)
        delivery = sample(C.ref("ControlDelivery"))
        delivery["session"]["ready"] = False
        self.assert_rejected(lambda: checks.validate_type("ControlDelivery", delivery))
        delivery["session"].update(state="closed", close_reason="revoked", ready=False)
        self.assert_rejected(lambda: checks.validate_type("ControlDelivery", delivery))

    def test_independent_wire_fixture(self):
        raw = b'{"version":"fixture-only","operation":"session.events","request_id":"poll-1","payload":{"session_id":"s1","cursor":{"session_id":"s1","instance_epoch":"epoch-1","sequence":0},"page_size":10},"extensions":{}}'
        parsed = checks.validate_request(raw)
        self.assertEqual(parsed["payload"]["page_size"], 10)
        for bad in (raw.replace(b'"page_size":10', b'"page_size":true'),
                    raw.replace(b'"sequence":0', b'"sequence":-1'),
                    raw.replace(b'"sequence":0', b'"sequence":0.0'),
                    raw.replace(b'"extensions":{}', b'"extensions":{},"extensions":{}')):
            with self.assertRaises((checks.ContractError, checks.codec.CodecError)):
                checks.validate_request(bad)

    def test_action_schema_profile_is_bounded_and_has_no_remote_resolution(self):
        parameters = {"type": "object", "properties": {"room": {"type": "string", "maxLength": 32}},
                      "required": ["room"], "additionalProperties": False}
        checks.validate_value_schema(parameters, require_object=True)
        checks.validate_action_value(parameters, {"room": "hall"})
        self.assert_rejected(lambda: checks.validate_action_value(parameters, {"room": 12}), "invalid_arguments")
        self.assert_rejected(lambda: checks.validate_action_value(parameters, {"room": "hall", "admin": True}), "invalid_arguments")
        bad_schemas = [{"type": "string"}, {"type": "array", "items": {"type": "null"}},
                       {"type": "integer", "minimum": 9, "maximum": 1},
                       {"type": "integer", "enum": [True]},
                       {"type": "boolean", "$ref": "https://not-contacted.invalid/schema"},
                       {"type": "string", "maxLength": 20, "pattern": "(a+)+$"},
                       {"type": "object", "properties": {}, "required": ["missing"], "additionalProperties": False}]
        for value in bad_schemas:
            self.assert_rejected(lambda: checks.validate_value_schema(value))

    def test_declared_actions_and_device_binding(self):
        value = request("capability.replace")
        definition = sample(C.ref("ActionDefinition"))
        definition["parameters"] = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
        value["payload"]["definitions"] = [definition]
        checks.validate_request(checks.codec.canonical(value))
        value["payload"]["definitions"].append(deepcopy(definition))
        self.assert_rejected(lambda: checks.validate_request(checks.codec.canonical(value)))
        value = request("presentation.acquire")
        value["payload"]["terms"]["device_id"] = "another-device"
        self.assert_rejected(lambda: checks.validate_request(checks.codec.canonical(value)))

    def test_control_receipt_pending_and_stale_secret_are_serializable(self):
        for operation in ("session.join", "session.resume", "session.claim_control", "invitation.redeem"):
            for status in ("pending", "completed_without_secret"):
                result = {"status": status, "outcome_ref": "original-operation", "reauth_required": status != "pending"}
                reply = {"request_id": "r1", "result": result}
                checks.validate_reply(operation, "r1", reply)
                result["control_credential"] = "must-not-leak"
                self.assert_rejected(lambda: checks.validate_reply(operation, "r1", reply))

    def test_privacy_pending_is_not_a_completed_deletion_receipt(self):
        pending = {"privacy_request_id": "p1", "status": "pending", "controlled_scope": ["source-1"], "poll_after_ms": 1000}
        for name in ("privacy.request", "privacy.receipt"):
            checks.validate_reply(name, "r1", {"request_id": "r1", "result": pending})
        bad = {**pending, "status": "done"}
        self.assert_rejected(lambda: checks.validate_type("PrivacyReceipt", bad))
        pending["exceptions"] = []
        self.assert_rejected(lambda: checks.validate_type("PrivacyReceipt", pending))


if __name__ == "__main__":
    unittest.main()
