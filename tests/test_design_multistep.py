"""接受/撤权竞争、多执行器、多步及三个崩溃位置的有限验证。"""

from concurrent.futures import ThreadPoolExecutor
import importlib.util
from itertools import permutations
from pathlib import Path
from threading import Barrier
import unittest


SPEC = importlib.util.spec_from_file_location("multistep_test", Path(__file__).resolve().parents[1] / "docs/protocol/multistep_model.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class MultiStepTests(unittest.TestCase):
    def opened(self):
        m = M.MultiStepModel()
        m.accept()
        return m, m.claim("worker-1")

    def test_accept_revoke_both_orders(self):
        for order in permutations(("accept", "revoke")):
            m = M.MultiStepModel()
            for op in order:
                if op == "revoke":
                    m.stop(revoke=True)
                elif m.authorized:
                    m.accept()
                else:
                    with self.assertRaises(M.Rejected):
                        m.accept()
            self.assertFalse(m.authorized)
            self.assertEqual(m.world, {})
            self.assertTrue(m.action is None or m.action["state"] == "cancelled")

    def test_two_actual_threads_claim_only_one_ticket(self):
        m = M.MultiStepModel()
        m.accept()
        barrier = Barrier(2)
        def claim(worker):
            barrier.wait(timeout=5)
            try:
                return m.claim(worker)
            except M.Rejected as error:
                self.assertEqual(error.code, "not_executable")
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, ("worker-1", "worker-2")))
        winners = [r for r in results if r is not None]
        self.assertEqual(len(winners), 1)
        winner = winners[0]
        loser = "worker-2" if winner[1] == "worker-1" else "worker-1"
        with self.assertRaises(M.Rejected):
            m.step(loser, winner, 1)
        m.step(winner[1], winner, 1)
        self.assertEqual(len(m.world), 1)

    def test_actual_accept_revoke_race_never_leaves_writable_action(self):
        m = M.MultiStepModel()
        barrier = Barrier(2)
        def accept():
            barrier.wait(timeout=5)
            try:
                return m.accept()
            except M.Rejected as error:
                self.assertEqual(error.code, "grant_revoked")
                return "denied"
        def revoke():
            barrier.wait(timeout=5)
            m.stop(revoke=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            accepted, revoked = pool.submit(accept), pool.submit(revoke)
            self.assertIn(accepted.result(timeout=5), {"accepted", "denied"})
            revoked.result(timeout=5)
        self.assertFalse(m.authorized)
        self.assertTrue(m.action is None or m.action["state"] == "cancelled")
        self.assertEqual(m.world, {})

    def test_partial_effect_is_not_erased_by_cancel(self):
        m, ticket = self.opened()
        fact = m.step("worker-1", ticket, 1)
        m.stop(revoke=True)
        self.assertEqual(m.step("worker-1", ticket, 1), fact)
        with self.assertRaises(M.Rejected):
            m.step("worker-1", ticket, 2)
        self.assertEqual(m.finish("worker-1", ticket), ("cancelled", "partial"))
        self.assertEqual(len(m.world), 1)

    def test_complete_then_revoke_reports_success_without_reexecuting(self):
        m, ticket = self.opened()
        m.step("worker-1", ticket, 1)
        m.step("worker-1", ticket, 2)
        m.stop(revoke=True)
        for _ in range(2):
            self.assertEqual(m.finish("worker-1", ticket), ("succeeded", "committed"))
        self.assertEqual(len(m.world), 2)

    def test_claim_without_fact_remains_unknown_after_restart(self):
        m, ticket = self.opened()
        with self.assertRaises(M.SimulatedCrash):
            m.step("worker-1", ticket, 1, crash="after_claim")
        m = m.recover_copy()
        m.stop(revoke=True)
        self.assertEqual(m.reconcile("worker-1", ticket), "unknown")
        self.assertEqual(m.finish("worker-1", ticket), ("unknown", "undetermined"))
        with self.assertRaises(M.Rejected) as caught:
            m.step("worker-1", ticket, 1)
        self.assertEqual(caught.exception.code, "outcome_unknown")
        self.assertEqual(m.world, {})

    def test_effect_without_action_journal_reconciles_not_replays(self):
        m, ticket = self.opened()
        with self.assertRaises(M.SimulatedCrash):
            m.step("worker-1", ticket, 1, crash="after_effect")
        m = m.recover_copy()
        m.stop(revoke=True)
        self.assertEqual(m.finish("worker-1", ticket), ("unknown", "undetermined"))
        self.assertEqual(m.reconcile("worker-1", ticket), "reconciled")
        self.assertEqual(m.finish("worker-1", ticket), ("cancelled", "partial"))
        self.assertEqual(len(m.world), 1)

    def test_lost_step_reply_and_sequence_guards(self):
        m, ticket = self.opened()
        with self.assertRaises(M.Rejected):
            m.step("worker-1", ticket, 2)
        with self.assertRaises(M.SimulatedCrash):
            m.step("worker-1", ticket, 1, crash="after_journal")
        m = m.recover_copy()
        m.step("worker-1", ticket, 1)
        m.step("worker-1", ticket, 2)
        self.assertEqual(m.finish("worker-1", ticket), ("succeeded", "committed"))
        self.assertEqual(len(m.world), 2)

    def test_all_120_two_step_stop_orders(self):
        for order in permutations(("step1", "step2", "stop", "finish", "reconcile")):
            with self.subTest(order=order):
                m, ticket = self.opened()
                stopped = False
                for op in order:
                    before = len(m.world)
                    try:
                        if op == "stop":
                            m.stop(revoke=True)
                            stopped = True
                        elif op == "finish":
                            m.finish("worker-1", ticket)
                        elif op == "reconcile":
                            m.reconcile("worker-1", ticket)
                        else:
                            m.step("worker-1", ticket, int(op[-1]))
                    except M.Rejected as error:
                        self.assertIn(error.code, {"not_executable", "execution_conflict"})
                    if stopped:
                        self.assertEqual(len(m.world), before)
                    if m.action["effect"] == "none":
                        self.assertEqual(len(m.world), 0)
                    self.assertLessEqual(len(m.world), 2)
