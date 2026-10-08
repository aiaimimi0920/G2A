"""统一交付的声明与追溯完整性，不把目录完整性当作语义证明。"""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1] / "docs" / "protocol"
SPEC = importlib.util.spec_from_file_location("statement_checks", ROOT / "contract_checks.py")
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)


class ConformanceTests(unittest.TestCase):
    def test_unreviewed_template_makes_no_pass_claim(self):
        template = json.loads((ROOT / "conformance.template.json").read_text(encoding="utf-8"))
        self.assertEqual(template, C.catalog.statement_template())
        C.validate_statement(template)
        self.assertEqual(template["status"], "not_evaluated")
        self.assertTrue(all(item["verdict"] == "not_evaluated" for item in template["coverage"]))

    def test_operation_traces_cover_exact_catalog_once(self):
        text = (ROOT / "STATE_TRACES.md").read_text(encoding="utf-8")
        operations = re.findall(r"^\| ([a-z_]+(?:\.[a-z_]+)*) \|", text, re.MULTILINE)
        self.assertEqual(len(operations), len(set(operations)))
        self.assertEqual(set(operations), set(C.catalog.OPERATIONS))
        coverage = (ROOT / "SESSION_OPERATION_COVERAGE.md").read_text(encoding="utf-8")
        rows = re.findall(r"^\| ([a-z_]+(?:\.[a-z_]+)*) \| (unified|not_assembled) \|", coverage, re.MULTILINE)
        self.assertEqual(len(rows), len(C.catalog.OPERATIONS))
        self.assertEqual({op for op, _ in rows}, set(C.catalog.OPERATIONS))
        spec = importlib.util.spec_from_file_location("coverage_session", ROOT / "relay_harness.py")
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)
        self.assertEqual({op for op, status in rows if status == "unified"}, harness.RelayHarness.WIRE_OPERATIONS)

    def test_pass_cannot_have_missing_or_unlinked_evidence(self):
        statement = C.catalog.statement_template()
        statement["status"] = "passed"
        with self.assertRaises(C.ContractError):
            C.validate_statement(statement)
        for record in statement["coverage"]:
            record.update(verdict="passed", evidence_ids=["missing"])
        with self.assertRaises(C.ContractError):
            C.validate_statement(statement)
        statement["evidence"] = [{"id": "missing", "kind": "symbolic", "artifact": "STATE_TRACES.md", "case_refs": ["reviewed-example"]}]
        statement["reviewed_by"] = "fixture-reviewer"
        C.validate_statement(statement)
        statement["coverage"].pop()
        with self.assertRaises(C.ContractError):
            C.validate_statement(statement)

    def test_symbolic_proof_cannot_be_promoted_to_deployment(self):
        statement = C.catalog.statement_template()
        statement.update(status="passed", assurance="deployment", wire_versions=["fixture-only"], trust_profiles=["test-enrolled"], roles=["agent"])
        statement["subject"]["artifact_kind"] = "implementation"
        statement["evidence"] = [{"id": "e1", "kind": "symbolic", "artifact": "STATE_TRACES.md", "case_refs": ["manual"]}]
        for record in statement["coverage"]:
            record.update(verdict="passed", evidence_ids=["e1"])
        with self.assertRaises(C.ContractError):
            C.validate_statement(statement)

    def test_duplicate_operation_or_evidence_is_rejected(self):
        statement = C.catalog.statement_template()
        statement["coverage"].append(deepcopy(statement["coverage"][0]))
        with self.assertRaises(C.ContractError):
            C.validate_statement(statement)

    def test_schema_only_is_not_design_semantic_evidence(self):
        statement = C.catalog.statement_template()
        statement.update(status="passed", reviewed_by="fixture-reviewer")
        statement["evidence"] = [{"id": "e1", "kind": "schema", "artifact": "contracts.schema.json", "case_refs": ["all-fields"]}]
        for record in statement["coverage"]:
            record.update(verdict="passed", evidence_ids=["e1"])
        with self.assertRaises(C.ContractError):
            C.validate_statement(statement)


if __name__ == "__main__":
    unittest.main()
