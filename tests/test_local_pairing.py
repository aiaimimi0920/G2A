"""本机跨进程绑定的身份、授权快照、重取和生命周期回归。"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import http.client
import json
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from g2a.client import Client
from g2a.local_pairing import LocalPairingService, serve_local_pairing
from g2a.pairing_client import PairingClient
from g2a.runtime import GameHost
from g2a.validation import ProtocolError
from test_protocol import descriptor, join_request


class LocalPairingTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.host = GameHost(descriptor(), clock=lambda: self.now)
        self.service = LocalPairingService(self.host, clock=lambda: self.now)
        self.agent_token = self.service.enroll('companion-a', 'player-a')
        self.other_token = self.service.enroll('companion-b', 'player-b')
        self.server = serve_local_pairing(self.service)
        self.endpoint = self.server.__enter__()
        self.addCleanup(self.server.__exit__, None, None, None)
        self.agent = PairingClient(self.endpoint, self.agent_token, expected_game_id='game-a')
        self.other = PairingClient(self.endpoint, self.other_token, expected_game_id='game-a')
        self.controller = PairingClient(self.endpoint, self.service.controller_token, expected_game_id='game-a')

    def error(self, code, action):
        with self.assertRaises(ProtocolError) as caught:
            action()
        self.assertEqual(caught.exception.code, code)

    def test_discovery_is_authenticated_but_never_grants_join(self):
        self.assertEqual(self.agent.discover(), [descriptor()])
        self.assertEqual(len(self.host.invitations), 0)
        bad = PairingClient(self.endpoint, 'not-enrolled', expected_game_id='game-a')
        self.error('unauthenticated', bad.discover)
        self.error('unauthenticated', lambda: Client(self.endpoint, expected_game_id='game-a').join(self.agent_token, join_request()))

    def test_enrolled_identity_cannot_be_changed_by_request(self):
        for key, value in [('agent_id', 'companion-b'), ('player_id', 'player-b')]:
            request = join_request(); request[key] = value
            self.error('permission_denied', lambda: self.agent.request(request))
        self.assertEqual(self.controller.requests(), [])

    def test_request_ownership_hides_other_agents_pending_consent(self):
        offer = self.agent.request(join_request())
        self.assertEqual(self.other.requests(), [])
        self.error('unauthenticated', lambda: self.other.offer(offer['id']))
        self.error('unauthenticated', lambda: self.other.redeem(offer['id'], desktop_visible=True))
        self.assertEqual(self.controller.requests()[0]['id'], offer['id'])

    def test_only_controller_decides_and_only_companion_redeems(self):
        offer = self.agent.request(join_request())
        self.error('permission_denied', lambda: self.agent.decide(offer, allow=True))
        self.error('permission_denied', lambda: self.agent.request(join_request(), game_initiated=True))
        self.error('consent_required', lambda: self.agent.redeem(offer['id'], desktop_visible=True))
        self.controller.decide(offer, allow=True)
        self.error('permission_denied', lambda: self.controller.redeem(offer['id'], desktop_visible=True))
        self.assertFalse(self.host.invitations)
        client = self.agent.redeem(offer['id'], desktop_visible=True)
        self.assertEqual(self.controller.offer(offer['id'])['state'], 'connected')
        client.leave()
        self.assertEqual(self.controller.offer(offer['id'])['state'], 'closed')

    def test_approval_binds_exact_snapshot_and_current_game_conditions(self):
        offer = self.agent.request(join_request())
        altered = deepcopy(offer); altered['scope'] = '0' * 64
        self.error('approval_stale', lambda: self.controller.decide(altered, allow=True))
        self.host.descriptor['name'] = 'Changed game'
        self.error('approval_stale', lambda: self.controller.decide(offer, allow=True))
        # 玩家仍可拒绝已经过时的询问，不能因过时状态卡住拒绝按钮。
        self.assertEqual(self.controller.decide(offer, allow=False)['state'], 'denied')
        self.assertFalse(self.host.invitations)

    def test_game_change_after_approval_blocks_redemption(self):
        offer = self.agent.request(join_request())
        self.controller.decide(offer, allow=True)
        self.host.revision += 1
        self.error('approval_stale', lambda: self.agent.redeem(offer['id'], desktop_visible=True))
        self.assertFalse(self.host.invitations)

    def test_game_change_after_ticket_before_join_is_also_checked(self):
        offer = self.agent.request(join_request())
        self.controller.decide(offer, allow=True)
        ticket = self.agent.call(f"requests/{offer['id']}/redeem", {'desktop_visible': True})
        self.assertEqual(self.controller.offer(offer['id'])['state'], 'connecting')
        self.host.descriptor['presentation'] = 'coexist'
        self.error('approval_stale', lambda: Client(self.endpoint, expected_game_id='game-a').join(ticket['invitation'], ticket['request']))
        self.assertFalse(self.host.sessions)

    def test_ticket_cannot_replace_user_approved_join_conditions(self):
        offer = self.agent.request(join_request())
        self.controller.decide(offer, allow=True)
        ticket = self.agent.call(f"requests/{offer['id']}/redeem", {'desktop_visible': False})
        for key, value in [
            ('user_policy', {'spoilers': 'avoid_unknown'}),
            ('default_avatar', {'id': 'other', 'format': 'text', 'label': 'Other'}),
            ('forced_avatar', {'id': 'forced', 'format': 'text', 'label': 'Forced'}),
            ('preferred_presentation', 'coexist'),
            ('allowed_actions', []),
            ('desktop_visible', True),
        ]:
            with self.subTest(field=key):
                altered = deepcopy(ticket['request']); altered[key] = value
                self.error('approval_stale', lambda: Client(self.endpoint, expected_game_id='game-a').join(
                    ticket['invitation'], altered))
                self.assertFalse(self.host.sessions)
        # 拒绝篡改不会消费邀请；领取时采样的状态及原请求重试仍有效。
        first = self.agent.redeem(offer['id'], desktop_visible=False)
        retry = self.agent.redeem(offer['id'], desktop_visible=False)
        self.assertEqual(first.session['id'], retry.session['id'])
        first.leave()
        self.assertFalse(first.desktop_visible)

    def test_concurrent_redemption_reuses_one_invitation_and_session(self):
        offer = self.agent.request(join_request())
        self.controller.decide(offer, allow=True)
        with ThreadPoolExecutor(max_workers=6) as pool:
            clients = list(pool.map(lambda _: self.agent.redeem(offer['id'], desktop_visible=False), range(6)))
        self.assertEqual(len(self.host.invitations), 1)
        self.assertEqual(len(self.host.sessions), 1)
        self.assertEqual(len({c.session['id'] for c in clients}), 1)
        self.error('redemption_conflict', lambda: self.agent.redeem(offer['id'], desktop_visible=True))
        clients[0].leave()
        self.assertFalse(clients[0].desktop_visible)

    def test_request_nonce_retry_does_not_create_another_consent(self):
        first = self.agent.request(join_request(), nonce='same')
        second = self.agent.request(join_request(), nonce='same')
        self.assertEqual(first['id'], second['id'])
        request = join_request(); request['allowed_actions'] = []
        self.error('id_conflict', lambda: self.agent.request(request, nonce='same'))
        self.assertEqual(len(self.controller.requests()), 1)

    def test_automatic_permission_does_not_authorize_launching_absent_process(self):
        offer = self.agent.request(join_request())
        self.controller.decide(offer, allow=True, remember=True)
        self.agent.redeem(offer['id'], desktop_visible=True).leave()
        automatic = self.agent.request(join_request())
        self.assertEqual(automatic['state'], 'authorized')
        self.now = 6
        game_offer = self.controller.request(join_request(), game_initiated=True)
        self.assertTrue(game_offer['launch_required'])
        self.assertEqual(game_offer['state'], 'awaiting_approval')
        self.controller.call('revoke-automatic', {})
        self.assertEqual(self.agent.offer(automatic['id'])['state'], 'awaiting_approval')
        self.error('permission_denied', lambda: self.agent.call('revoke-automatic', {}))

    def test_denied_and_expired_requests_never_issue_tickets(self):
        denied = self.agent.request(join_request())
        self.controller.decide(denied, allow=False)
        self.error('consent_required', lambda: self.agent.redeem(denied['id'], desktop_visible=True))
        expired = self.agent.request(join_request())
        self.controller.decide(expired, allow=True)
        self.now = 61
        self.error('request_expired', lambda: self.agent.redeem(expired['id'], desktop_visible=True))
        self.assertEqual(self.controller.requests(), [])
        self.assertFalse(self.host.invitations)

    def test_queue_is_bounded_and_expired_nonces_are_reclaimed(self):
        for index in range(64):
            self.agent.request(join_request(), nonce=str(index))
        self.error('resource_limit', lambda: self.agent.request(join_request(), nonce='overflow'))
        self.now = 61
        self.agent.request(join_request(), nonce='fresh')
        self.assertEqual(len(self.service.requests), 1)
        self.assertEqual(len(self.service.coordinator.pending), 1)

    def test_late_ticket_cannot_outlive_the_original_request(self):
        offer = self.agent.request(join_request())
        self.controller.decide(offer, allow=True)
        self.now = 59
        ticket = self.agent.call(f"requests/{offer['id']}/redeem", {'desktop_visible': True})
        self.now = 61
        self.error('unauthenticated', lambda: Client(self.endpoint, expected_game_id='game-a').join(ticket['invitation'], ticket['request']))
        self.assertFalse(self.host.sessions)

    def test_other_service_credentials_do_not_work_after_restart(self):
        another = LocalPairingService(GameHost(descriptor()))
        wrong = another.enroll('companion-a', 'player-a')
        self.error('unauthenticated', lambda: PairingClient(self.endpoint, wrong, expected_game_id='game-a').discover())

    def test_ticket_cannot_redirect_invitation_to_another_origin(self):
        ticket = {'endpoint': 'https://other.example', 'invitation': 'a' * 43, 'request': join_request()}
        with patch.object(self.agent, 'call', return_value=ticket):
            self.error('identity_mismatch', lambda: self.agent.redeem('request', desktop_visible=True))

    def test_browser_origin_and_duplicate_authorization_are_denied(self):
        url = urlsplit(self.endpoint)
        for headers, expected in [({'Origin': 'https://example.com'}, 403), ({}, 401)]:
            connection = http.client.HTTPConnection(url.hostname, url.port)
            self.addCleanup(connection.close)
            connection.putrequest('GET', '/pairing/requests')
            connection.putheader('Authorization', 'Bearer ' + self.agent_token)
            if not headers:
                connection.putheader('Authorization', 'Bearer ' + self.service.controller_token)
            for key, value in headers.items():
                connection.putheader(key, value)
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, expected)
            response.read()
