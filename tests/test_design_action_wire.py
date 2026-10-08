"""动作控制入口的字节级闭环；可信决定、执行与故障均为本地夹具。"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import importlib.util
from pathlib import Path
from threading import Barrier
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1] / "docs/protocol"


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = load("action_wire_harness", "action_harness.py")
F = load("action_wire_fixture", "fixtures.py")
E = load("action_wire_consumer", "event_consumer.py")


class ActionWireTests(unittest.TestCase):
    def setUp(self):
        self.f = F.core_fixture()
        self.h = A.ActionHarness(self.f)
        self.request = F.wire_request("action.request", {
            "version": "fixture-only", "session_id": "s1", "id": "a1", "type": "action.request",
            "sender": self.f["agent"], "audience": [self.f["player"]],
            "expected_capabilities_revision": 1, "extensions": {},
            "payload": {"action": "find-key", "arguments": {"room": "hall"}, "deadline": 30000}})

    def send(self, request, credential="agent-fixture", now=1000, fault=None):
        return A.C.codec.decode(self.h.submit(A.C.codec.canonical(request), credential, now=now, fault=fault))["result"]

    def claim_request(self, worker="worker-1", request_id="claim-1"):
        return F.wire_request("action.claim", {"session_id": "s1", "action_id": "a1",
                              "worker": F.principal(worker, "service")}, request_id)

    def claim(self, worker="worker-1", request_id="claim-1"):
        return self.send(self.claim_request(worker, request_id), worker + "-fixture")

    def report(self, ticket, state="succeeded", effect="committed", steps=(1, 2), result=True):
        fact = {"state": state, "effect": effect, "steps": [
            {"step": n, "effect": "committed", "evidence_ref": ticket["proof_ref"] + "-step-" + str(n)}
            for n in steps]}
        if result:
            fact["result"] = {"item": "gold-key"}
        return F.wire_request("action.commit_result", {"ticket": ticket, "fact": fact}, "commit-1")

    def complete_steps(self, ticket, count=2):
        for step in range(1, count + 1):
            self.h.execute("step", "worker-1", ticket=ticket, step=step, now=1001)

    def high_risk(self):
        self.f["action"]["requires_per_action_consent"] = True
        digest = A.C.codec.digest("action-definition", self.f["action"])
        for scope in (self.f["scope"], self.f["grant"]["scope"], self.f["session"]["scope"]):
            scope["approved_action_digests"]["find-key"] = digest
        self.f["grant"]["scope_digest"] = A.C.codec.digest("scope", self.f["scope"])
        payload = {"session_id": "s1", "action_request_id": "a1", "action": "find-key",
                   "arguments_digest": A.C.codec.digest("action-arguments", {"room": "hall"}),
                   "definition_digest": digest, "expires_at": 5000, "decision_ref": "decision-1"}
        evidence = {"player": self.f["player"], "allow": True, "payload": deepcopy(payload)}
        self.h = A.ActionHarness(self.f, decisions={"decision-1": evidence})
        return F.wire_request("action.confirm", payload, "confirm-1")

    def test_full_high_risk_action_wire_chain_and_business_result(self):
        confirm = self.high_risk()
        lease = self.h.authority.state["session"]["lease_deadline"]
        approval = self.send(confirm, "player-fixture")
        self.assertEqual(self.h.authority.state["session"]["lease_deadline"], lease)
        self.assertIsNone(self.h.model.action)
        self.request["payload"]["payload"]["confirmation"] = approval["confirmation_id"]
        self.send(self.request)
        ticket = self.claim()["ticket"]
        self.complete_steps(ticket)
        result = self.send(self.report(ticket), "worker-1-fixture")
        self.assertEqual((result["state"], result["effect"], result["known_result"]),
                         ("succeeded", "committed", {"item": "gold-key"}))
        reducer = E.ResultReducer("s1")
        reducer.apply(result)
        query = F.wire_request("action.query", {"session_id": "s1", "action_id": "a1"})
        self.assertEqual(self.send(query), result)
        self.assertEqual(len(self.h.model.world), 2)

    def test_unconfirmed_high_risk_request_never_creates_action(self):
        self.high_risk()
        with self.assertRaises(A.C.ContractError) as caught:
            self.send(self.request)
        self.assertEqual(caught.exception.code, "action_consent_required")
        self.assertIsNone(self.h.model.action)

    def test_claim_wire_competition_and_original_request_retry(self):
        self.send(self.request)
        barrier = Barrier(2)
        def claim(worker):
            barrier.wait(timeout=5)
            return worker, self.claim(worker)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, ("worker-1", "worker-2")))
        winners = [(worker, result) for worker, result in results if result["status"] == "claimed"]
        self.assertEqual(len(winners), 1)
        worker, original = winners[0]
        self.assertEqual(self.claim(worker), original)
        self.assertEqual(self.claim(worker, "claim-new")["status"], "not_executable")
        self.assertEqual(self.h.model.world, {})

    def test_fabricated_result_does_not_create_effect_or_terminal(self):
        self.send(self.request)
        ticket = self.claim()["ticket"]
        with self.assertRaises(A.C.ContractError) as caught:
            self.send(self.report(ticket), "worker-1-fixture")
        self.assertEqual(caught.exception.code, "execution_conflict")
        self.assertEqual(self.h.model.action["state"], "executing")
        self.assertEqual(self.h.model.world, {})

    def assert_denied(self, request, credential, code, *, now=1000):
        with self.assertRaises(A.C.ContractError) as caught:
            self.send(request, credential, now=now)
        self.assertEqual(caught.exception.code, code)

    def test_confirmation_requires_exact_trusted_player_decision(self):
        original = self.high_risk()
        self.assert_denied(original, "agent-fixture", "permission_denied")
        for field, value in (("decision_ref", "forged"), ("arguments_digest", "0" * 64),
                             ("action_request_id", "a2"), ("expires_at", 4000)):
            request = deepcopy(original)
            request["payload"][field] = value
            self.assert_denied(request, "player-fixture", "action_consent_required")
        self.h.decisions["decision-1"]["allow"] = False
        self.assert_denied(original, "player-fixture", "action_consent_required")
        self.assertEqual(self.h.confirmations, {})
        self.assertEqual(self.h.control_receipts, {})

    def test_confirmation_is_once_bound_and_expires_without_consumption(self):
        request = self.high_risk()
        result = self.send(request, "player-fixture")
        other = deepcopy(request)
        other["request_id"] = "confirm-other"
        self.assertEqual(self.send(other, "player-fixture"), result)
        self.assertEqual(len(self.h.confirmations), 1)
        self.request["payload"]["payload"]["confirmation"] = result["confirmation_id"]
        wrong = deepcopy(self.request)
        wrong["payload"]["id"] = "a2"
        self.assert_denied(wrong, "agent-fixture", "action_consent_required")
        self.assert_denied(self.request, "agent-fixture", "action_consent_required", now=5000)
        self.assertFalse(self.h.confirmations[result["confirmation_id"]]["consumed"])
        self.send(self.request)
        self.assertTrue(self.send(self.request)["duplicate"])
        self.assertTrue(self.h.confirmations[result["confirmation_id"]]["consumed"])

    def test_confirm_and_accept_failures_are_atomic_and_lost_reply_is_idempotent(self):
        request = self.high_risk()
        with self.assertRaises(A.H.InjectedFailure):
            self.send(request, "player-fixture", fault="before_commit")
        self.assertEqual(self.h.confirmations, {})
        with self.assertRaises(A.H.InjectedFailure):
            self.send(request, "player-fixture", fault="after_commit")
        result = self.send(request, "player-fixture")
        self.assertEqual(len(self.h.confirmations), 1)
        self.request["payload"]["payload"]["confirmation"] = result["confirmation_id"]
        with self.assertRaises(A.H.InjectedFailure):
            self.send(self.request, fault="before_commit")
        self.assertIsNone(self.h.model.action)
        self.assertFalse(self.h.confirmations[result["confirmation_id"]]["consumed"])
        with self.assertRaises(A.H.InjectedFailure):
            self.send(self.request, fault="after_commit")
        revision = self.h.revision
        self.assertTrue(self.send(self.request)["duplicate"])
        self.assertEqual(self.h.revision, revision)

    def test_claim_lost_reply_and_encoding_failure_do_not_reclaim(self):
        self.send(self.request)
        request = self.claim_request()
        with patch.object(A.C, "validate_reply", side_effect=A.C.ContractError("invalid_message")):
            self.assert_denied(request, "worker-1-fixture", "invalid_message")
        self.assertEqual(self.h.model.action["state"], "pending")
        self.assertIsNone(self.h.wire_ticket)
        self.assertEqual(self.h.control_receipts, {})
        with self.assertRaises(A.H.InjectedFailure):
            self.send(request, "worker-1-fixture", fault="after_commit")
        revision = self.h.revision
        ticket = self.claim()["ticket"]
        self.assertEqual(ticket, self.h.wire_ticket)
        self.assertEqual(self.h.revision, revision)
        changed = deepcopy(request)
        changed["extensions"] = {"unknown.optional": {"version": "1", "required": False, "value": 1}}
        self.assert_denied(changed, "worker-1-fixture", "id_conflict")

    def test_claim_authorization_and_ticket_exact_binding(self):
        self.send(self.request)
        request = self.claim_request()
        self.assert_denied(request, "agent-fixture", "permission_denied")
        self.assert_denied(request, "worker-2-fixture", "permission_denied")
        self.assert_denied(request, "unregistered-fixture", "unauthenticated")
        ticket = self.claim()["ticket"]
        report = self.report(ticket)
        self.assert_denied(report, "worker-2-fixture", "permission_denied")
        for field, value in (("generation", 2), ("fence", 2), ("deadline", 30001),
                             ("request_id", "a2"), ("proof_ref", "forged"), ("session_id", "s2")):
            bad = deepcopy(report)
            bad["payload"]["ticket"][field] = value
            self.assert_denied(bad, "worker-1-fixture", "permission_denied")
        self.assertEqual(self.h.model.world, {})

    def test_pending_claim_after_revoke_or_deadline_has_no_ticket(self):
        for barrier in ("revoke", "deadline", "definition", "generation"):
            self.setUp()
            self.send(self.request)
            now = 1000
            if barrier == "revoke":
                self.h.revoke(now=1000)
            elif barrier == "deadline":
                now = 30000
            elif barrier == "definition":
                self.h.definition["maximum_duration_ms"] = 10000
            else:
                self.h.authority.state["session"]["control_generation"] = 2
            result = self.send(self.claim_request(), "worker-1-fixture", now=now)
            self.assertEqual(result["status"], "not_executable")
            self.assertEqual((result["action"]["state"], result["action"]["effect"]), ("cancelled", "none"))
            self.assertIsNone(self.h.wire_ticket)

    def test_refreshed_controller_cannot_execute_old_action(self):
        self.send(self.request)
        ticket = self.claim()["ticket"]
        self.complete_steps(ticket, count=1)
        self.h.authority.state["session"]["control_generation"] = 2
        self.h.authority.credentials["agent-fixture"]["generation"] = 2
        with self.assertRaises(A.C.ContractError) as caught:
            self.h.execute("step", "worker-1", ticket=ticket, step=2, now=1002)
        self.assertEqual(caught.exception.code, "stale_controller")
        self.assertEqual(len(self.h.model.world), 1)
        self.assertEqual(self.h.execute("step", "worker-1", ticket=ticket, step=1, now=1002)["effect"], "committed")

    def test_commit_loss_conflict_and_frozen_business_result_schema(self):
        self.send(self.request)
        ticket = self.claim()["ticket"]
        self.complete_steps(ticket)
        report = self.report(ticket)
        for mutate in (lambda fact: fact.update(effect="partial"),
                       lambda fact: fact["steps"][0].update(evidence_ref="forged"),
                       lambda fact: fact["steps"].reverse(),
                       lambda fact: fact.update(result={"item": "invented-key"})):
            bad = deepcopy(report)
            mutate(bad["payload"]["fact"])
            self.assert_denied(bad, "worker-1-fixture", "execution_conflict")
        self.h.definition["result_schema"]["properties"]["item"]["maxLength"] = 2
        with self.assertRaises(A.H.InjectedFailure):
            self.send(report, "worker-1-fixture", fault="before_commit")
        self.assertEqual(self.h.model.action["state"], "executing")
        with self.assertRaises(A.H.InjectedFailure):
            self.send(report, "worker-1-fixture", fault="after_commit")
        result = self.send(report, "worker-1-fixture")
        revision = self.h.revision
        other = deepcopy(report)
        other["request_id"] = "commit-new"
        self.assertEqual(self.send(other, "worker-1-fixture"), result)
        self.assertEqual(self.h.revision, revision)
        other["payload"]["fact"]["result"]["item"] = "silver-key"
        other["request_id"] = "commit-conflict"
        self.assert_denied(other, "worker-1-fixture", "execution_conflict")

    def test_trusted_world_result_must_still_match_accepted_business_schema(self):
        self.f["action"]["result_schema"]["properties"]["item"]["maxLength"] = 2
        digest = A.C.codec.digest("action-definition", self.f["action"])
        for scope in (self.f["scope"], self.f["grant"]["scope"], self.f["session"]["scope"]):
            scope["approved_action_digests"]["find-key"] = digest
        self.f["grant"]["scope_digest"] = A.C.codec.digest("scope", self.f["scope"])
        self.h = A.ActionHarness(self.f)
        self.send(self.request)
        ticket = self.claim()["ticket"]
        self.complete_steps(ticket)
        self.assert_denied(self.report(ticket), "worker-1-fixture", "invalid_arguments")
        self.assertIsNone(self.h.committed_fact)
        self.assertEqual((self.h.model.action["state"], self.h.model.action["effect"]), ("executing", "committed"))
        self.assertEqual(len(self.h.model.world), 2)

    def test_old_ticket_reports_after_revoke_without_renewing_lease(self):
        self.send(self.request)
        ticket = self.claim()["ticket"]
        self.complete_steps(ticket)
        self.h.revoke(now=1002)
        self.h.authority.credentials.pop("agent-fixture")
        lease = self.h.authority.state["session"]["lease_deadline"]
        result = self.send(self.report(ticket), "worker-1-fixture", now=1003)
        self.assertEqual(result["state"], "succeeded")
        self.assertEqual(self.h.authority.state["session"]["lease_deadline"], lease)
        self.assert_denied(self.report(ticket), "worker-1-fixture", "result_expired", now=self.h.read_until + 1)
        self.assertEqual(len(self.h.model.world), 2)

    def test_cancelled_and_failed_reports_keep_partial_effects(self):
        for kind in ("cancelled", "failed"):
            for count in (0, 1):
                self.setUp()
                self.send(self.request)
                ticket = self.claim()["ticket"]
                self.complete_steps(ticket, count=count)
                if kind == "cancelled":
                    cancel = deepcopy(self.request)
                    cancel.update(operation="action.cancel", request_id="cancel")
                    cancel["payload"].update(id="cancel-1", type="action.cancel", payload={"request_id": "a1"})
                    self.send(cancel)
                else:
                    self.h.execute("deny", "worker-1", ticket=ticket, step=count + 1, now=1002)
                report = self.report(ticket, kind, "partial" if count else "none", steps=range(1, count + 1), result=False)
                if kind == "failed":
                    report["payload"]["fact"]["steps"].append({"step": count + 1, "effect": "none",
                        "evidence_ref": ticket["proof_ref"] + "-denied-" + str(count + 1)})
                result = self.send(report, "worker-1-fixture")
                self.assertEqual(result["state"], kind)
                self.assertEqual(result["effect"], "partial" if count else "none")
                self.assertNotIn("known_result", result)
                self.assertEqual(len(self.h.model.world), count)

    def test_unknown_report_reconciles_original_facts_without_new_effect(self):
        for crash in ("after_claim", "after_effect", "after_journal"):
            self.setUp()
            self.send(self.request)
            ticket = self.claim()["ticket"]
            with self.assertRaises(A.M.SimulatedCrash):
                self.h.execute("step", "worker-1", ticket=ticket, step=1, crash=crash, now=1001)
            self.h.revoke(now=1002)
            report = self.report(ticket, "cancelled" if crash == "after_journal" else "unknown",
                                 "partial" if crash == "after_journal" else "undetermined",
                                 steps=(1,) if crash == "after_journal" else (), result=False)
            previous = self.send(report, "worker-1-fixture")
            before = len(self.h.model.world)
            self.h.execute("reconcile", "worker-1", ticket=ticket, now=1003)
            if crash == "after_effect":
                stale = deepcopy(report)
                stale["request_id"] = "commit-stale-new"
                self.assert_denied(stale, "worker-1-fixture", "execution_conflict")
                final = self.report(ticket, "cancelled", "partial", steps=(1,), result=False)
                final["request_id"] = "commit-recovered"
                result = self.send(final, "worker-1-fixture")
                self.assertGreater(result["result_revision"], previous["result_revision"])
                reducer = E.ResultReducer("s1")
                reducer.apply(result)
                self.assertEqual(reducer.apply(self.send(report, "worker-1-fixture")), "stale")
                self.assertEqual(result["state"], "cancelled")
            elif crash == "after_claim":
                self.assertEqual(previous["state"], "unknown")
            self.assertEqual(len(self.h.model.world), before)


if __name__ == "__main__":
    unittest.main()
