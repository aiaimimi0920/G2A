"""配置 GODOT_EXECUTABLE 和 G2A_TEST_OUTPUT 时运行真实引擎；不伪装缺依赖为通过。"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import unittest
import uuid

from g2a.client import Client
from g2a.http import serve

path = Path(__file__).resolve().parents[1] / 'examples/godot_demo.py'
spec = importlib.util.spec_from_file_location('g2a_godot_demo', path)
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


@unittest.skipUnless(os.environ.get('GODOT_EXECUTABLE') and os.environ.get('G2A_TEST_OUTPUT'),
                     'Real Godot requires GODOT_EXECUTABLE and G2A_TEST_OUTPUT; engine not verified')
class GodotInteropTests(unittest.TestCase):
    def run_game(self, blocked):
        output = Path(os.environ['G2A_TEST_OUTPUT']) / ('godot-' + uuid.uuid4().hex)
        return demo.run_demo(os.environ['GODOT_EXECUTABLE'], output, blocked=blocked)

    def test_engine_moves_companion_and_picks_key_once(self):
        result = self.run_game(False)
        self.assertTrue(result['key_taken'])
        self.assertEqual(result['executions'], 1)
        self.assertTrue(result['companion']['unauthorized_action_rejected'])

    def test_game_world_can_refuse_authorized_action(self):
        result = self.run_game(True)
        self.assertFalse(result['key_taken'])
        self.assertEqual(result['executions'], 0)
        self.assertEqual(result['companion']['action_result']['status'], 'failed')

    def run_interruption(self, before_claim):
        output = Path(os.environ['G2A_TEST_OUTPUT']) / ('interruption-' + uuid.uuid4().hex)
        project = output / 'game'
        shutil.copytree(path.parent / 'godot_key_quest', project,
                        ignore=shutil.ignore_patterns('.godot', '*.uid'))
        host = demo.make_host()
        with serve(host) as endpoint, (output / 'godot.log').open('wb') as log:
            client = Client(endpoint, expected_game_id='key-quest')
            client.join(host.invite('fox', 'alice', allowed_actions=['find-key']),
                dict(protocol='0.1.0-dev', agent_id='fox', player_id='alice',
                     default_avatar={'id': 'fox', 'format': 'text', 'label': 'Fox'},
                     desktop_visible=True, user_policy={}, allowed_actions=['find-key']))
            client.send('action.request', dict(action='find-key', arguments={'room': 'hall'},
                capability_revision=1), message_id='edge-action')
            if before_claim:
                client.send('action.cancel', {'request_id': 'edge-action'})
            env = {k: v for k, v in os.environ.items() if not k.startswith('G2A_')}
            env.update(G2A_ENDPOINT=endpoint, G2A_SESSION=client.session['id'],
                       G2A_GAME_TOKEN=host.admin_token, G2A_EVIDENCE=str(output / 'game.json'))
            game = subprocess.Popen([os.environ['GODOT_EXECUTABLE'], '--headless', '--path', str(project)],
                                    env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 10
                wanted = 'cancelled' if before_claim else 'executing'
                while time.monotonic() < deadline:
                    action = host.get_action(client.session['id'], host.admin_token, 'edge-action')
                    if action['state'] == wanted:
                        break
                    self.assertIsNone(game.poll(), 'Game exited before interruption point')
                    time.sleep(0.005)
                self.assertEqual(action['state'], wanted)
                client.leave()
                self.assertEqual(game.wait(timeout=10), 0)
                log.flush()
                engine_log = (output / 'godot.log').read_text(encoding='utf-8', errors='replace')
                for marker in ('SCRIPT ERROR:', 'ERROR:', 'ObjectDB instances leaked'):
                    self.assertNotIn(marker, engine_log)
                evidence = json.loads((output / 'game.json').read_text(encoding='utf-8'))
                self.assertFalse(evidence['key_taken'])
                self.assertTrue(evidence['session_closed'])
                self.assertEqual(evidence['executions'], 0 if before_claim else 1)
                terminal = host.get_action(client.session['id'], host.admin_token, 'edge-action')
                self.assertEqual(terminal['state'], 'cancelled' if before_claim else 'unknown')
            finally:
                if game.poll() is None:
                    game.kill()
                game.wait(timeout=5)

    def test_cancel_before_claim_does_not_crash_game(self):
        self.run_interruption(True)

    def test_leave_during_movement_preserves_unknown_without_pickup(self):
        self.run_interruption(False)
