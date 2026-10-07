import importlib.util
from pathlib import Path
import sys
import unittest

from g2a.client import Client
from g2a.http import serve
from g2a.runtime import GameHost

# 示例通过公开接口注入客户端；协议库不依赖该存储结构。
path = Path(__file__).resolve().parents[1] / 'examples/memory_companion.py'
spec = importlib.util.spec_from_file_location('g2a_memory_example', path)
memory_example = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = memory_example
spec.loader.exec_module(memory_example)
Memory, CompanionMemory = memory_example.Memory, memory_example.CompanionMemory


def game(game_id):
    return GameHost(dict(protocol='0.1.0-dev', game_id=game_id, name=game_id, bindings=['http-poll'],
        avatar_formats=['text'], presentation='coexist', policy={'spoilers': 'avoid_unknown'}, actions=[]))


def join(host, endpoint):
    client = Client(endpoint, expected_game_id=host.descriptor['game_id'])
    client.join(host.invite('fox', 'alice', team=['bob']), dict(protocol='0.1.0-dev', agent_id='fox', player_id='alice',
        default_avatar={'id': 'fox', 'format': 'text', 'label': '狐狸'}, desktop_visible=True,
        user_policy={}, allowed_actions=[]))
    return client


class CrossGameMemoryTests(unittest.TestCase):
    def test_same_companion_recalls_first_game_inside_second_game(self):
        memory = CompanionMemory('fox')
        first = game('adventure-a')
        with serve(first) as endpoint:
            c = join(first, endpoint)
            first.send(c.session['id'], first.admin_token, dict(id='boss-defeated', type='game.context', sender='adventure-a',
                data={'summary': '我们打败了最终 Boss', 'facts': {'final_boss': '异次元魔王'},
                      'provenance': {'kind': 'shared_experience', 'source_id': 'boss-defeated', 'player_id': 'alice'}}))
            event = c.poll()['events'][0]['message']
            memory.remember(Memory('alice', 'adventure-a', 'final_boss', event['data']['facts']['final_boss'],
                event['data']['provenance']['kind'], event['data']['provenance']['source_id'], frozenset({'alice', 'bob'})))
            c.leave()
        second = game('adventure-b')
        with serve(second) as endpoint:
            c = join(second, endpoint)
            reply = memory.recall('alice', 'adventure-a', 'final_boss', recipients=['alice', 'bob'])
            c.send('chat.message', {**reply, 'channel': 'team', 'recipients': ['alice', 'bob']})
            received = second.poll(c.session['id'], second.admin_token)['events'][0]['message']['data']
            self.assertEqual(received['text'], '我们一起经历过：异次元魔王')
            self.assertEqual(received['provenance']['source_id'], 'boss-defeated')
            self.assertEqual(c.session['agent_id'], memory.agent_id)
            c.leave()

    def test_second_playthrough_does_not_erase_shared_knowledge(self):
        m = CompanionMemory('fox')
        m.remember(Memory('alice', 'game-a', 'boss', '魔王', 'shared_experience', 'first-run', frozenset({'alice'})))
        self.assertEqual(m.recall('alice', 'game-a', 'boss', recipients=['alice'])['text'], '我们一起经历过：魔王')
        self.assertIsNone(m.recall('eve', 'game-a', 'boss', recipients=['eve']))

    def test_player_told_is_known_but_not_personally_witnessed(self):
        m = CompanionMemory('fox')
        m.remember(Memory('alice', 'game-a', 'boss', '向导', 'player_report', 'chat-1', frozenset({'alice'})))
        self.assertEqual(m.recall('alice', 'game-a', 'boss', recipients=['alice'])['text'], '你之前告诉过我：向导')

    def test_external_reference_does_not_become_shared_memory(self):
        m = CompanionMemory('fox')
        m.remember(Memory('alice', 'game-a', 'boss', '攻略中的结局', 'external_reference', 'guide-1', frozenset({'alice'})))
        self.assertIsNone(m.recall('alice', 'game-a', 'boss', recipients=['alice']))
        result = m.recall('alice', 'game-a', 'boss', recipients=['alice'], allow_external=True)
        self.assertEqual(result['provenance']['kind'], 'external_reference')
        self.assertTrue(result['text'].startswith('根据外部资料'))

    def test_same_memory_store_does_not_mean_disclose_private_memory(self):
        m = CompanionMemory('fox')
        m.remember(Memory('alice', 'game-a', 'secret', '私人信息', 'player_report', 'private-chat', frozenset({'alice'})))
        self.assertIsNotNone(m.recall('alice', 'game-a', 'secret', recipients=['alice']))
        self.assertIsNone(m.recall('alice', 'game-a', 'secret', recipients=['alice', 'bob']))
