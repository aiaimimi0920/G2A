import unittest

from g2a.http import serve
from g2a.pairing import PairingCoordinator
from g2a.runtime import GameHost
from g2a.validation import ProtocolError
from test_protocol import descriptor, join_request


class PairingTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.coordinator = PairingCoordinator(clock=lambda: self.now)
        self.host = GameHost(descriptor())
        self.server = serve(self.host)
        self.endpoint = self.server.__enter__()
        self.addCleanup(self.server.__exit__, None, None, None)
        self.coordinator.register_game(self.host, self.endpoint)

    def offer(self, request=None, **kwargs):
        return self.coordinator.request('game-a', request or join_request(),
            initiated_by=kwargs.get('entry', 'desktop'), companion_running=kwargs.get('running', True))

    def error(self, code, operation):
        with self.assertRaises(ProtocolError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)

    def test_discovery_and_request_never_issue_invitation(self):
        self.assertEqual(self.coordinator.discover(), [descriptor()])
        offer = self.offer()
        self.assertEqual(offer['state'], 'awaiting_approval')
        self.assertFalse(self.host.invitations)
        self.error('consent_required', lambda: self.coordinator.connect(offer['id']))
        self.coordinator.deny(offer['id'])
        self.error('consent_required', lambda: self.coordinator.connect(offer['id']))
        self.assertFalse(self.host.sessions)

    def test_explicit_desktop_join_over_http_and_restore(self):
        offer = self.offer()
        self.coordinator.approve(offer['id'])
        client = self.coordinator.connect(offer['id'])
        self.assertFalse(client.desktop_visible)
        client.leave()
        self.assertTrue(client.desktop_visible)
        self.error('consent_required', lambda: self.coordinator.connect(offer['id']))

    def test_automatic_join_is_scoped_and_revocable(self):
        offer = self.offer()
        self.coordinator.approve(offer['id'], remember=True)
        self.coordinator.connect(offer['id']).leave()
        automatic = self.offer()
        self.assertEqual(automatic['state'], 'authorized')
        other_player = join_request(); other_player['player_id'] = 'another-player'
        self.assertEqual(self.offer(other_player)['state'], 'awaiting_approval')
        other_agent = join_request(); other_agent['agent_id'] = 'another-agent'
        self.assertEqual(self.offer(other_agent)['state'], 'awaiting_approval')
        self.coordinator.revoke_automatic_join()
        self.error('consent_required', lambda: self.coordinator.connect(automatic['id']))

    def test_game_initiated_launch_requires_approval_even_with_auto_grant(self):
        offer = self.offer()
        self.coordinator.approve(offer['id'], remember=True)
        game_offer = self.offer(entry='game', running=False)
        self.assertTrue(game_offer['launch_required'])
        self.assertEqual(game_offer['state'], 'awaiting_approval')
        self.coordinator.approve(game_offer['id'])
        self.coordinator.connect(game_offer['id']).leave()
        self.error('companion_not_running', lambda: self.offer(running=False))

    def test_stale_approval_and_expiration_do_not_create_invitation(self):
        offer = self.offer()
        self.coordinator.approve(offer['id'])
        self.host.revision += 1
        self.error('approval_stale', lambda: self.coordinator.connect(offer['id']))
        fresh = self.offer()
        self.now = 61
        self.error('request_expired', lambda: self.coordinator.approve(fresh['id']))
        self.assertFalse(self.host.invitations)

    def test_permissions_cannot_be_expanded_by_user(self):
        request = join_request(); request['allowed_actions'] = ['reveal-boss']
        self.error('permission_denied', lambda: self.offer(request))

    def test_offer_is_copy_not_mutable_approval(self):
        offer = self.offer()
        offer['state'] = 'authorized'
        self.error('consent_required', lambda: self.coordinator.connect(offer['id']))

    def test_visibility_is_captured_at_connection_not_at_prompt(self):
        offer = self.offer()
        self.coordinator.approve(offer['id'])
        client = self.coordinator.connect(offer['id'], desktop_visible=False)
        client.leave()
        self.assertFalse(client.desktop_visible)

    def test_invitation_rejects_changed_conditions_before_http_join(self):
        state = self.host.authorization_state()
        invitation = self.host.invite('companion-a', 'player-a',
            allowed_actions=['find-key'], expected_state=state)
        self.host.descriptor['presentation'] = 'coexist'
        self.error('approval_stale', lambda: self.host.join(invitation, join_request()))
        self.assertFalse(self.host.sessions)

    def test_bound_invitation_retry_returns_existing_session_after_game_update(self):
        invitation = self.host.invite('companion-a', 'player-a',
            allowed_actions=['find-key'], expected_state=self.host.authorization_state())
        first = self.host.join(invitation, join_request())
        self.host.revision += 1
        second = self.host.join(invitation, join_request())
        self.assertEqual(first['session']['id'], second['session']['id'])
