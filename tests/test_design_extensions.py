"""活动扩展与摘要边界；固定声明不是插件执行或真实认证。"""

from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / "docs" / "protocol"
SPEC = importlib.util.spec_from_file_location("extension_checks", ROOT / "contract_checks.py")
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)


class ExtensionTests(unittest.TestCase):
    def setUp(self):
        self.ext = {"version": "1", "required": True, "value": {"enabled": True}}
        principal = {"issuer": "fixture", "subject": "fox", "kind": "agent"}
        self.request = {"version": "fixture-only", "operation": "chat.send", "request_id": "r1",
                        "extensions": {}, "payload": {"version": "fixture-only", "session_id": "s1",
                        "id": "m1", "type": "chat.message", "sender": principal, "audience": [principal],
                        "payload": {"channel": "private", "text": "hello", "provenance": [], "source_refs": []},
                        "extensions": {}}}

    def active(self, selected=None, supported=()):
        return C.validate_active_request(C.codec.canonical(self.request),
                    selected_extensions=selected or {}, supported_extensions=supported)

    def reject(self, fn, code):
        with self.assertRaises(C.ContractError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def test_outer_message_extensions_cannot_escape_message_digest(self):
        before = C.codec.digest("message", self.request["payload"])
        self.request["extensions"]["example.guard"] = self.ext
        self.assertEqual(before, C.codec.digest("message", self.request["payload"]))
        self.reject(lambda: C.validate_request(C.codec.canonical(self.request)), "invalid_message")

    def test_unknown_required_rejected_optional_preserved_but_inactive(self):
        self.request["payload"]["extensions"]["example.guard"] = self.ext
        self.reject(self.active, "feature_unsupported")
        self.ext["required"] = False
        parsed, activated = self.active()
        self.assertEqual(activated, {})
        self.assertEqual(parsed, self.request)
        before = C.codec.digest("message", parsed["payload"])
        self.ext["value"]["enabled"] = False
        self.assertNotEqual(before, C.codec.digest("message", self.request["payload"]))

    def test_required_selection_cannot_be_omitted_or_lose_handler(self):
        selected = {"example.guard": deepcopy(self.ext)}
        self.reject(lambda: self.active(selected, [("example.guard", "1")]), "feature_unsupported")
        self.request["payload"]["extensions"] = deepcopy(selected)
        self.reject(lambda: self.active(selected), "feature_unsupported")
        parsed, active = self.active(selected, [("example.guard", "1")])
        self.assertEqual(active, selected)
        active["example.guard"]["value"]["enabled"] = False
        self.assertEqual(parsed, self.request)
        self.assertTrue(selected["example.guard"]["value"]["enabled"])

    def test_no_version_fallback_or_configuration_drift(self):
        selected = {"example.guard": deepcopy(self.ext)}
        for field, value in (("version", "2"), ("required", False), ("value", {"enabled": 1})):
            with self.subTest(field=field):
                self.request["payload"]["extensions"] = deepcopy(selected)
                self.request["payload"]["extensions"]["example.guard"][field] = value
                self.reject(lambda: self.active(selected, [("example.guard", "1")]), "approval_stale")

    def test_known_but_unapproved_optional_extension_is_not_activated(self):
        self.ext["required"] = False
        self.request["payload"]["extensions"]["example.guard"] = self.ext
        self.assertEqual(self.active(supported=[("example.guard", "1")])[1], {})

    def test_control_extensions_are_in_control_digest(self):
        self.request.update(operation="session.close", payload={"session_id": "s1", "reason": "left"})
        self.request["extensions"] = {"example.guard": deepcopy(self.ext)}
        selected = deepcopy(self.request["extensions"])
        self.assertEqual(self.active(selected, [("example.guard", "1")])[1], selected)
        before = C.codec.digest("control", {k: v for k, v in self.request.items() if k != "request_id"})
        self.request["extensions"]["example.guard"]["value"]["enabled"] = False
        self.assertNotEqual(before, C.codec.digest("control", {k: v for k, v in self.request.items() if k != "request_id"}))

    def test_core_close_does_not_depend_on_failed_required_handler(self):
        self.request.update(operation="session.close", payload={"session_id": "s1", "reason": "left"})
        self.assertEqual(self.active({"example.guard": self.ext})[1], {})
        self.request["extensions"] = {"example.guard": self.ext}
        self.reject(lambda: self.active({"example.guard": self.ext}), "feature_unsupported")


if __name__ == "__main__":
    unittest.main()
