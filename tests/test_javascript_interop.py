"""独立 Node 进程只持有 Agent 邀请；游戏管理员令牌不交给它。"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import unittest

from g2a.http import serve
from g2a.runtime import GameHost


class JavaScriptInteropTests(unittest.TestCase):
    def test_independent_node_agent_against_python_game(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node.js 20+ required; cross-language conformance has not run')
        host = GameHost(dict(protocol='0.1.0-dev', game_id='key-quest', name='钥匙探险',
            bindings=['http-poll'], avatar_formats=['text'], presentation='hide_desktop', policy={'spoilers': 'avoid_unknown'},
            actions=[dict(name='find-key', description='寻找钥匙', timeout_ms=5000,
                parameters={'type': 'object', 'properties': {'room': {'enum': ['hall']}}, 'required': ['room'], 'additionalProperties': False})]))
        invitation = host.invite('fox', 'alice', team=['bob'], allowed_actions=['find-key'])
        stop = threading.Event()
        failures, evidence = [], {'executions': 0, 'proactive_chat': False}

        def game_loop():
            try:
                observed, cursors = set(), {}
                while not stop.wait(0.01):
                    with host.lock:
                        sessions = list(host.sessions.values())
                    for session in sessions:
                        if session.id not in observed:
                            host.send(session.id, host.admin_token, dict(id='hall-1', type='game.context', sender='key-quest',
                                data={'summary': '大厅中有一把钥匙', 'facts': {'room': 'hall'},
                                      'provenance': {'kind': 'shared_experience', 'source_id': 'hall-1', 'player_id': 'alice'}}))
                            observed.add(session.id)
                        page = host.poll(session.id, host.admin_token, cursors.get(session.id, 0))
                        cursors[session.id] = page['cursor']
                        for entry in page['events']:
                            message = entry['message']
                            if message['type'] == 'chat.message' and message['sender'] == 'fox':
                                evidence['proactive_chat'] = message['data']['channel'] == 'team' and message['data']['recipients'] == ['alice', 'bob']
                            if message['type'] == 'action.request':
                                action = host.claim_action(session.id, host.admin_token, message['id'])
                                assert action['arguments'] == {'room': 'hall'}
                                evidence['executions'] += 1
                                host.send(session.id, host.admin_token, dict(id='game-result', type='action.result', sender='key-quest',
                                    data={'request_id': message['id'], 'status': 'succeeded', 'details': {'item': 'gold-key'}}))
            except BaseException as error:
                failures.append(error)

        thread = threading.Thread(target=game_loop, daemon=True)
        with serve(host) as endpoint:
            thread.start()
            try:
                config = {'endpoint': endpoint, 'game_id': 'key-quest', 'invitation': invitation,
                    'request': dict(protocol='0.1.0-dev', agent_id='fox', player_id='alice',
                        default_avatar={'id': 'fox', 'format': 'text', 'label': '小狐狸'}, desktop_visible=True,
                        user_policy={'spoilers': 'allow'}, allowed_actions=['find-key'])}
                peer = Path(__file__).resolve().parents[1] / 'examples/javascript_companion.mjs'
                process = subprocess.run([node, str(peer)], input=json.dumps(config).encode(),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, env=os.environ.copy())
                self.assertEqual(process.returncode, 0, process.stderr.decode('utf-8', errors='replace'))
                result = json.loads(process.stdout)
                self.assertTrue(result['desktop_restored'])
                self.assertTrue(result['unauthorized_action_rejected'])
                self.assertTrue(result['duplicate_receipt'])
                self.assertEqual(evidence, {'executions': 1, 'proactive_chat': True})
                self.assertEqual(next(iter(host.sessions.values())).state, 'closed')
            finally:
                stop.set(); thread.join(timeout=3)
            self.assertEqual(failures, [])
