"""错误映射与提交知识测试；AST 覆盖只证明代码登记，不代替分支执行。"""

import ast
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / "docs" / "protocol"
SPEC = importlib.util.spec_from_file_location("boundary_errors_under_test", ROOT / "error_mapping.py")
E = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(E)


class ErrorMappingTests(unittest.TestCase):
    def test_all_literal_flow_model_errors_are_registered(self):
        tree = ast.parse((ROOT / "flow_model.py").read_text(encoding="utf-8"))
        codes = set()
        nodes = (node for top in tree.body
                 if not (isinstance(top, ast.FunctionDef) and top.name == "require")
                 for node in ast.walk(top))
        for node in nodes:
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"require", "Rejected"}:
                index = 1 if node.func.id == "require" else 0
                self.assertIsInstance(node.args[index], ast.Constant, "新增动态错误需显式登记和测试")
                codes.add(node.args[index].value)
        self.assertTrue(codes)
        for code in codes:
            with self.subTest(code=code):
                self.assertIn(E.ALIASES.get(code, code), E.checks.catalog.ERRORS)

    def test_all_alias_targets_are_valid(self):
        for source, target in E.ALIASES.items():
            self.assertIn(target, E.checks.catalog.ERRORS)
            # history_gap 不是 alias，不会在这里凭空创建敏感快照。
            for knowledge in ("not_accepted", "accepted", "unknown"):
                error = E.boundary_error(source, knowledge=knowledge, request_id="r1")
                E.checks.validate_error(error)

    def test_same_error_has_different_commit_knowledge(self):
        before = E.boundary_error("resource_limit", knowledge="not_accepted")
        after = E.boundary_error("resource_limit", knowledge="accepted")
        uncertain = E.boundary_error("resource_limit", knowledge="unknown")
        self.assertEqual((before["code"], before["outcome"]), ("resource_limit", "not_accepted"))
        self.assertEqual((after["code"], after["outcome"]), ("operation_failed", "accepted"))
        self.assertEqual(uncertain["outcome"], "unknown")

    def test_unregistered_errors_do_not_leak_or_claim_rollback(self):
        secret = "oops Authorization=secret-memory-trace"
        error = E.boundary_error(secret, knowledge="not_accepted", request_id="r1")
        self.assertEqual(error["code"], "internal_failure")
        self.assertEqual(error["outcome"], "unknown")
        self.assertNotIn(secret, str(error))

    def test_closed_bridge_and_unknown_effect_never_mean_not_sent(self):
        for code in ("bridge_closed", "outcome_unknown", "transport_timeout"):
            self.assertEqual(E.boundary_error(code, knowledge="not_accepted")["outcome"], "unknown")
        self.assertEqual(E.boundary_error("relay_not_dispatched", knowledge="not_accepted")["outcome"], "not_accepted")

    def test_details_are_whitelisted_and_cannot_inject_secrets(self):
        with self.assertRaises(E.checks.ContractError):
            E.boundary_error("permission_denied", knowledge="not_accepted", safe_details={"Authorization": "secret"})
        with self.assertRaises(ValueError):
            E.boundary_error("resource_limit", knowledge="probably_not_committed")


if __name__ == "__main__":
    unittest.main()
