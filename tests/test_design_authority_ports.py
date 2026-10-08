"""固定权威端口的来源导入与收紧型扩展执行。"""

from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest
import test_design_chat_harness as chat_tests
import test_design_pipeline as pipeline_tests


ROOT = Path(__file__).resolve().parents[1] / "docs/protocol"
SPEC = importlib.util.spec_from_file_location("source_import_test", ROOT / "source_import.py")
I = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(I)


class AuthorityPortTests(unittest.TestCase):
    def source_fixture(self):
        t = chat_tests.ChatHarnessTests()
        t.setUp()
        proof = {**deepcopy(t.record), "revoked": False}
        return t, I.SourceImporter({"consent-fixture-1": proof})

    def test_import_then_real_chat_pipeline(self):
        t, importer = self.source_fixture()
        imported = importer.import_record(t.record, verified_controller=t.f["player"], session=t.f["session"], now=1000)
        t.h.state["records"] = {imported["source"]["source_id"]: imported}
        t.submit()
        self.assertEqual(len(t.h.delivery(t.f["player"], now=1001)), 1)
        importer.evidence["consent-fixture-1"]["revoked"] = True
        t.h.state["records"] = importer.snapshot(t.f["session"], now=1002)
        self.assertEqual(t.h.delivery(t.f["player"], now=1002), [])

    def test_forged_controller_evidence_or_target_rejected(self):
        for field, value in (("controller", "agent"), ("evidence_ref", "missing"), ("session_id", "another")):
            t, importer = self.source_fixture()
            record = deepcopy(t.record)
            record[field] = t.f[value] if field == "controller" else value
            with self.assertRaises(I.C.ContractError):
                importer.import_record(record, verified_controller=t.f["player"], session=t.f["session"], now=1000)
            self.assertEqual(importer.records, {})

    def test_revision_replay_and_no_reexpansion(self):
        t, importer = self.source_fixture()
        def put(record):
            return importer.import_record(record, verified_controller=t.f["player"], session=t.f["session"], now=1000)
        put(t.record)
        self.assertEqual(put(t.record), t.record)
        narrowed = deepcopy(t.record)
        narrowed.update(revision=2, allowed_readers=[t.f["agent"]])
        put(narrowed)
        expanded = deepcopy(t.record)
        expanded["revision"] = 3
        with self.assertRaises(I.C.ContractError):
            put(expanded)
        with self.assertRaises(I.C.ContractError):
            put(t.record)

    def test_revoked_evidence_cannot_be_reimported(self):
        t, importer = self.source_fixture()
        importer.evidence["consent-fixture-1"]["revoked"] = True
        with self.assertRaises(I.C.ContractError):
            importer.import_record(t.record, verified_controller=t.f["player"], session=t.f["session"], now=1000)

    def test_chat_extension_is_executed_and_input_not_mutated(self):
        t = chat_tests.ChatHarnessTests()
        t.setUp()
        ext = {"example.max-chat-bytes": {"version": "1", "required": True, "value": {"maximum": 2}}}
        for scope in (t.h.state["session"]["scope"], t.h.state["grant"]["scope"]):
            scope["extensions"] = deepcopy(ext)
        t.h.state["grant"]["scope_digest"] = chat_tests.C.codec.digest("scope", t.h.state["grant"]["scope"])
        t.request["payload"]["extensions"] = deepcopy(ext)
        original = deepcopy(t.request)
        t.reject_without_mutation("resource_limit")
        self.assertEqual(t.request, original)
        t.request["payload"]["payload"]["text"] = "ok"
        t.submit()
        self.assertEqual(len(t.h.state["events"]), 1)

    def test_action_policy_executes_and_core_cancel_bypasses_failed_policy(self):
        t = pipeline_tests.ActionPipelineTests()
        t.setUp()
        ext = {"example.deny-action": {"version": "1", "required": True, "value": {"action": "find-key"}}}
        for scope in (t.h.authority.state["session"]["scope"], t.h.authority.state["grant"]["scope"]):
            scope["effective_policy"]["extensions"] = deepcopy(ext)
        t.h.authority.state["grant"]["scope_digest"] = pipeline_tests.A.C.codec.digest("scope", t.h.authority.state["grant"]["scope"])
        with self.assertRaises(pipeline_tests.A.C.ContractError) as caught:
            t.send()
        self.assertEqual(caught.exception.code, "permission_denied")
        self.assertIsNone(t.h.model.action)
        # 单独的已接受 fixture：之后扩展服务不可用，核心取消仍可受理。
        t.setUp()
        t.send()
        for scope in (t.h.authority.state["session"]["scope"], t.h.authority.state["grant"]["scope"]):
            scope["effective_policy"]["extensions"] = {"example.unavailable": deepcopy(ext["example.deny-action"])}
        t.h.authority.state["grant"]["scope_digest"] = pipeline_tests.A.C.codec.digest("scope", t.h.authority.state["grant"]["scope"])
        cancel = deepcopy(t.request)
        cancel.update(operation="action.cancel")
        cancel["payload"].update(id="cancel", type="action.cancel", payload={"request_id": "a1"})
        t.send(cancel)
        self.assertEqual(t.query()["state"], "cancelled")
