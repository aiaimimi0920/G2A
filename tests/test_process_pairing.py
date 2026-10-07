"""游戏、授权控制台、伙伴的独立进程端到端证明，不是 GUI 点击验收。"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

path = Path(__file__).resolve().parents[1] / 'examples/process_pairing.py'
spec = importlib.util.spec_from_file_location('g2a_process_pairing', path)
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


class ProcessPairingTests(unittest.TestCase):
    def check_flow(self, entry, allow, language='javascript'):
        if language == 'javascript' and shutil.which('node') is None:
            self.skipTest('Node.js required for independent pairing interoperability')
        result = demo.run_demo(entry=entry, decision=allow, agent_language=language)
        self.assertEqual(result['before']['sessions'], 0)
        self.assertEqual(result['before']['invitations'], 0)
        self.assertEqual(result['after']['sessions'], int(allow))
        self.assertEqual(result['after']['executions'], int(allow))
        self.assertEqual(result['after']['active_sessions'], 0)
        self.assertEqual(result['agent_running_before_decision'], entry == 'desktop')
        if allow:
            self.assertTrue(result['companion']['desktop_restored'])
            self.assertEqual(len({result['controller_pid'], result['game_pid'], result['agent_pid']}), 3)
        if entry == 'game':
            self.assertEqual(result['agent_started_after_approval'], allow)
            if not allow:
                self.assertIsNone(result['agent_pid'])

    def test_desktop_process_requests_then_user_allows(self):
        self.check_flow('desktop', True)

    def test_desktop_process_is_denied_without_joining(self):
        self.check_flow('desktop', False)

    def test_game_entry_starts_companion_only_after_approval(self):
        self.check_flow('game', True)

    def test_game_denial_never_starts_companion_process(self):
        self.check_flow('game', False)

    def test_python_companion_also_uses_the_same_pairing_binding(self):
        self.check_flow('game', True, 'python')

    def test_console_reads_explicit_chinese_approval_before_launch(self):
        env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'}
        process = subprocess.run([sys.executable, '-B', str(path), '--entry', 'game', '--agent', 'python'],
            input='允许\n'.encode('utf-8'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, env=env)
        self.assertEqual(process.returncode, 0, process.stderr.decode('utf-8', errors='replace'))
        output = process.stdout.decode('utf-8').replace('\r\n', '\n')
        result = json.loads(output[output.index('{\n  "entry"'):])
        self.assertTrue(result['approved'])
        self.assertFalse(result['agent_running_before_decision'])
        self.assertTrue(result['agent_started_after_approval'])
