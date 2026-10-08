"""下一版草案编码层测试；不导入旧 SDK，不访问网络。"""

import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest


PATH = Path(__file__).resolve().parents[1] / "docs" / "protocol" / "codec.py"
SPEC = importlib.util.spec_from_file_location("g2a_design_codec", PATH)
codec = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = codec
SPEC.loader.exec_module(codec)


class CodecTests(unittest.TestCase):
    def reject(self, code, raw, limits=codec.DEFAULT_LIMITS):
        with self.assertRaises(codec.CodecError) as caught:
            codec.decode(raw, limits)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)

    def test_literal_golden_encoding(self):
        value = {"z": [None, True, False, 0, -1], "a": "中文/\n\t\b\f\r\0\x1f\"\\"}
        expected = b'{"a":"\xe4\xb8\xad\xe6\x96\x87/\\n\\t\\b\\f\\r\\u0000\\u001f\\\"\\\\","z":[null,true,false,0,-1]}'
        self.assertEqual(codec.canonical(value), expected)
        self.assertEqual(codec.decode(expected), value)

    def test_unicode_scalar_sort_not_utf16(self):
        self.assertEqual(codec.canonical({"\U00010000": 1, "\ue000": 2}),
                         '{"\ue000":2,"\U00010000":1}'.encode("utf-8"))

    def test_no_unicode_normalization(self):
        self.assertNotEqual(codec.canonical("é"), codec.canonical("e\u0301"))

    def test_escaped_and_literal_equivalence(self):
        self.assertEqual(codec.decode(b'"\\ud83e\\udd8a"'), "🦊")
        self.assertEqual(codec.canonical(codec.decode(b'{"\\u0061":1}')), b'{"a":1}')

    def test_duplicate_decoded_keys(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":1,"\\u0061":2}', b'{"x":{"a":0,"a":1}}'):
            with self.subTest(raw=raw):
                self.reject("duplicate_key", raw)

    def test_numbers(self):
        for raw in (b'1.0', b'1e0', b'-0', b'NaN', b'Infinity', b'-Infinity'):
            with self.subTest(raw=raw):
                self.reject("invalid_number", raw)
        for raw in (b'9007199254740992', b'-9007199254740992', b'9' * 1000):
            self.reject("integer_out_of_range", raw)
        for number in (-codec.MAX_INTEGER, 0, codec.MAX_INTEGER):
            self.assertEqual(codec.decode(str(number).encode()), number)

    def test_invalid_json(self):
        for raw in (b'', b'01', b'{', b'{}{}', b'[1,]', b'{"a":}', b'"\x00"', b'+1'):
            with self.subTest(raw=raw):
                self.reject("invalid_json", raw)

    def test_encoding_rejections(self):
        self.reject("bom_forbidden", b'\xef\xbb\xbf{}')
        self.reject("invalid_utf8", b'"\xff"')
        self.reject("invalid_unicode", b'"\\ud800"')
        self.reject("invalid_unicode", b'{"\\udfff":1}')
        self.reject("bytes_required", "{}")

    def test_limits_at_boundaries(self):
        self.assertEqual(codec.decode(b'[]', codec.Limits(max_bytes=2)), [])
        self.reject("byte_limit", b'[0]', codec.Limits(max_bytes=2))
        self.assertEqual(codec.decode(b'[[]]', codec.Limits(max_depth=2)), [[]])
        self.reject("depth_limit", b'[[[]]]', codec.Limits(max_depth=2))
        self.assertEqual(codec.decode(b'{"a":0}', codec.Limits(max_nodes=3)), {"a": 0})
        self.reject("node_limit", b'{"a":0}', codec.Limits(max_nodes=2))
        self.reject("container_limit", b'[0,1]', codec.Limits(max_container_items=1))
        self.reject("container_limit", b'{"a":0,"b":0}', codec.Limits(max_container_items=1))
        self.assertEqual(codec.decode('"中"'.encode(), codec.Limits(max_string_bytes=3)), "中")
        self.reject("string_limit", '"中"'.encode(), codec.Limits(max_string_bytes=2))

    def test_depth_scan_ignores_strings_and_escapes(self):
        value = {"x": '[{\\"}]'}
        encoded = codec.canonical(value, codec.Limits(max_depth=1))
        self.assertEqual(codec.decode(encoded, codec.Limits(max_depth=1)), value)
        self.reject("depth_limit", b'[' * 1000 + b']' * 1000)

    def test_encoder_rejects_non_json_python_values(self):
        for value, code in ((1.0, "invalid_type"), (float('nan'), "invalid_type"),
                            ((1, 2), "invalid_type"), ({1: "x"}, "invalid_key"),
                            ("\ud800", "invalid_unicode"),
                            (codec.MAX_INTEGER + 1, "integer_out_of_range")):
            with self.subTest(code=code):
                with self.assertRaises(codec.CodecError) as caught:
                    codec.canonical(value)
                self.assertEqual(caught.exception.code, code)

    def test_encoder_limits_and_cycle(self):
        cycle = []
        cycle.append(cycle)
        with self.assertRaises(codec.CodecError) as caught:
            codec.canonical(cycle)
        self.assertEqual(caught.exception.code, "depth_limit")
        with self.assertRaises(codec.CodecError) as caught:
            codec.canonical("\0", codec.Limits(max_bytes=7))
        self.assertEqual(caught.exception.code, "byte_limit")

    def test_digest_domain_separation(self):
        expected = hashlib.sha256(b'g2a-cjson-1\x00scope\x00{"a":1}').hexdigest()
        self.assertEqual(codec.digest("scope", {"a": 1}), expected)
        self.assertEqual(len({codec.digest(domain, {"a": 1}) for domain in codec.DOMAINS}), len(codec.DOMAINS))
        with self.assertRaises(codec.CodecError):
            codec.digest("authentication", {})

    def test_semantic_distinctions(self):
        self.assertNotEqual(codec.digest("message", {}), codec.digest("message", {"x": None}))
        self.assertNotEqual(codec.digest("message", [1, 2]), codec.digest("message", [2, 1]))
        self.assertNotEqual(codec.canonical(True), codec.canonical(1))
        self.assertEqual(codec.canonical({"b": 2, "a": 1}), codec.canonical({"a": 1, "b": 2}))

    def test_limits_are_not_request_controlled(self):
        for options in ({"max_bytes": True}, {"max_depth": 65}, {"max_nodes": 0}):
            with self.assertRaises(ValueError):
                codec.Limits(**options)


if __name__ == "__main__":
    unittest.main()
