"""真实桥接传输与失败边界；不把回环部署称为公网云端验收。"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import shutil
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import URLError

from g2a.bridge import BridgeClient, BridgeMailbox, OutboundGame, execute, serve_bridge
from g2a.client import Client
from g2a.runtime import GameHost
from g2a.validation import ProtocolError, validate
from test_protocol import descriptor, join_request, message


@contextmanager
def running(game):
    stop, failures = threading.Event(), []

    def run():
        try:
            game.run(stop)
        except BaseException as error:
            failures.append(error)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    try:
        yield stop
    finally:
        stop.set(); worker.join(timeout=6)
        assert not worker.is_alive(), 'Outbound worker did not stop'
        assert not failures, failures


class BridgeTests(unittest.TestCase):
    def error(self, code, action):
        with self.assertRaises(ProtocolError) as error:
            action()
        self.assertEqual(error.exception.code, code)

    def join(self, host, endpoint, mailbox, **kwargs):
        client = BridgeClient(endpoint, mailbox.agent_token, expected_game_id='game-a', **kwargs)
        invitation = host.invite('companion-a', 'player-a', allowed_actions=['find-key'])
        client.join(invitation, join_request())
        return client

    def test_real_bridge_preserves_actions_permissions_and_receipts(self):
        host, mailbox = GameHost(descriptor()), BridgeMailbox()
        with serve_bridge(mailbox) as endpoint, running(OutboundGame(host, endpoint, mailbox.game_token)):
            client = self.join(host, endpoint, mailbox)
            data = dict(action='find-key', arguments={'room': 'hall'}, capability_revision=1)
            receipt = client.send('action.request', data, message_id='same')
            self.assertEqual(client.send('action.request', data, message_id='same'), receipt)
            self.error('id_conflict', lambda: client.send('action.request', {**data, 'arguments': {'room': 'other'}}, message_id='same'))
            self.error('permission_denied', lambda: client.send('action.request', {**data, 'action': 'admin'}))
            sid = client.session['id']
            host.claim_action(sid, host.admin_token, 'same')
            host.send(sid, host.admin_token, message('done', 'action.result',
                {'request_id': 'same', 'status': 'succeeded', 'details': {'item': 'key'}}, sender='game-a'))
            self.assertEqual(client.call(f'/sessions/{sid}/actions/same', token=client.token)['state'], 'succeeded')
            client.leave('x' * 300)
            self.assertTrue(client.desktop_visible)
            self.assertEqual(len(host.sessions[sid].actions), 1)

    def test_bridge_role_credentials_and_mailboxes_are_isolated(self):
        first, second = BridgeMailbox(), BridgeMailbox()
        with serve_bridge(first) as endpoint:
            transport = Client(endpoint, expected_game_id='game-a')
            for token in (first.agent_token, second.game_token, 'wrong'):
                self.error('unauthenticated', lambda: transport.call('/bridge/pull', token=token))
            self.error('unauthenticated', lambda: transport.call('/bridge/call', {}, first.game_token))
            self.error('unauthenticated', lambda: transport.call('/bridge/reply', {}, first.agent_token))
            self.error('unauthenticated', lambda: first.pull('令牌'))
            self.assertEqual(first.requests, {})

    def test_game_rejects_admin_credentials_and_privileged_operations(self):
        host = GameHost(descriptor())
        self.error('permission_denied', lambda: execute(host, dict(operation='describe', arguments={}, credential=host.admin_token)))
        self.error('invalid_message', lambda: execute(host, dict(operation='claim', arguments={}, credential='')))
        self.error('invalid_message', lambda: execute(host, dict(operation='describe', arguments={}, credential='令牌')))
        mailbox = BridgeMailbox()
        with serve_bridge(mailbox) as endpoint, running(OutboundGame(host, endpoint, mailbox.game_token)):
            client = self.join(host, endpoint, mailbox)
            sid = client.session['id']
            self.error('invalid_route', lambda: client.call(f'/sessions/{sid}/actions/x/claim', {}, host.admin_token))
            self.error('permission_denied', lambda: client.send('game.context', {
                'summary': 'fake', 'facts': {}, 'provenance': {'kind': 'shared_experience', 'source_id': 'x', 'player_id': 'player-a'}}))

    def test_large_unicode_event_page_crosses_reply_envelope(self):
        host, mailbox = GameHost(descriptor()), BridgeMailbox()
        with serve_bridge(mailbox) as endpoint, running(OutboundGame(host, endpoint, mailbox.game_token)):
            client = self.join(host, endpoint, mailbox)
            for index in range(4):
                host.send(client.session['id'], host.admin_token, message(str(index), 'game.context', {
                    'summary': '中文' * 4000, 'facts': {},
                    'provenance': {'kind': 'shared_experience', 'source_id': str(index), 'player_id': 'player-a'}}, sender='game-a'))
            page = client.poll()
            self.assertGreater(len(json.dumps(page, ensure_ascii=False).encode()), 65536)
            self.assertEqual(len(page['events']), 4)

    def test_timeout_removes_unclaimed_request_and_bounds_capacity(self):
        mailbox = BridgeMailbox(timeout=0.15, capacity=1)
        command = dict(operation='describe', arguments={}, credential='')
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(mailbox.call, mailbox.agent_token, command)
            deadline = time.monotonic() + 1
            while not mailbox.requests and time.monotonic() < deadline:
                time.sleep(0.001)
            self.error('resource_limit', lambda: mailbox.call(mailbox.agent_token, command))
            self.error('bridge_timeout', future.result)
        self.assertEqual(mailbox.pull(mailbox.game_token), {'requests': []})
        self.assertEqual(mailbox.requests, {})

    def test_lost_reply_is_unknown_and_original_message_id_can_be_queried(self):
        host, mailbox = GameHost(descriptor()), BridgeMailbox(timeout=0.15)
        with serve_bridge(mailbox) as endpoint:
            game = OutboundGame(host, endpoint, mailbox.game_token)
            with running(game):
                client = self.join(host, endpoint, mailbox)
            command = dict(operation='send', credential=client.token, arguments={'session_id': client.session['id'],
                'message': message('lost', 'action.request', {'action': 'find-key', 'arguments': {'room': 'hall'}, 'capability_revision': 1})})
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(mailbox.call, mailbox.agent_token, command)
                batch = {'requests': []}
                deadline = time.monotonic() + 1
                while not batch['requests'] and time.monotonic() < deadline:
                    batch = mailbox.pull(mailbox.game_token)
                item = batch['requests'][0]
                receipt = execute(host, item['command'])
                self.error('bridge_timeout', future.result)
            self.error('request_gone', lambda: mailbox.reply(mailbox.game_token, {'id': item['id'], 'status': 200, 'result': receipt}))
            with running(game):
                status = client.call(f"/sessions/{client.session['id']}/actions/lost", token=client.token)
                self.assertEqual(status['state'], 'pending')
                self.assertEqual(client.call(f"/sessions/{client.session['id']}/events", command['arguments']['message'], client.token), receipt)
            self.assertEqual(len(host.sessions[client.session['id']].actions), 1)

    def test_missing_game_expires_client_lease_and_revocation_wakes_waiter(self):
        now = [0]
        host, mailbox = GameHost(descriptor()), BridgeMailbox(timeout=0.1)
        with serve_bridge(mailbox) as endpoint:
            with running(OutboundGame(host, endpoint, mailbox.game_token)):
                client = self.join(host, endpoint, mailbox, clock=lambda: now[0])
            now[0] = 31
            self.error('bridge_timeout', client.poll)
            self.assertTrue(client.desktop_visible)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(client.call, '/.well-known/g2a.json')
                deadline = time.monotonic() + 1
                while not mailbox.requests and time.monotonic() < deadline:
                    time.sleep(0.001)
                mailbox.close()
                self.error('bridge_closed', future.result)
            self.error('bridge_closed', lambda: mailbox.pull(mailbox.game_token))

    def test_outbound_loop_recovers_transient_pull_without_replaying_effects(self):
        host, mailbox = GameHost(descriptor()), BridgeMailbox()
        with serve_bridge(mailbox) as endpoint:
            game = OutboundGame(host, endpoint, mailbox.game_token)
            call = game.transport.call
            failed = [False]

            def intermittent(path, *args, **kwargs):
                if path == '/bridge/pull' and not failed[0]:
                    failed[0] = True
                    raise URLError('injected offline')
                return call(path, *args, **kwargs)

            with patch.object(game.transport, 'call', side_effect=intermittent), running(game):
                client = self.join(host, endpoint, mailbox)
                self.assertIsNotNone(client.session)
            self.assertTrue(failed[0])

    def test_schema_forbids_redirect_and_non_error_failure_responses(self):
        for status in (201, 302, 399, 600):
            self.error('invalid_message', lambda: validate('bridge_reply', dict(id='r', status=status, result={})))
        self.error('invalid_message', lambda: validate('bridge_reply', dict(id='r', status=500, result={})))

    def test_three_process_outbound_game_and_independent_node_companion(self):
        if shutil.which('node') is None:
            self.skipTest('Node.js required; bridge cross-language path not verified')
        path = Path(__file__).resolve().parents[1] / 'examples/outbound_demo.py'
        spec = importlib.util.spec_from_file_location('g2a_outbound_demo', path)
        demo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(demo)
        result = demo.run_demo()
        self.assertEqual(len(set(result['process_ids'])), 3)
        self.assertEqual(result['game']['bind_attempts'], 0)
        self.assertTrue(result['game']['listener_guard'])
        self.assertTrue(result['game']['proactive_chat'])
        self.assertTrue(result['companion']['desktop_restored'])
