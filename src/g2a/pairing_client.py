"""跨进程本机配对客户端；发现信息不能作为授权凭据。"""
import uuid

from .client import Client
from .validation import ProtocolError, validate


class PairingClient:
    def __init__(self, endpoint, token, *, expected_game_id):
        self.transport = Client(endpoint, expected_game_id=expected_game_id)
        self.token = token

    def call(self, path, body=None):
        return self.transport.call('/pairing/' + path, body, self.token)

    def discover(self):
        return validate('pairing_discovery', self.call('discovery'))['games']

    def request(self, request, *, nonce=None, game_initiated=False):
        body = validate('pairing_request', {'nonce': nonce or uuid.uuid4().hex, 'request': request})
        return validate('pairing_offer', self.call('game-request' if game_initiated else 'requests', body))

    def requests(self):
        return validate('pairing_page', self.call('requests'))['requests']

    def offer(self, request_id):
        return validate('pairing_offer', self.call('requests/' + request_id))

    def decide(self, offer, *, allow, remember=False):
        body = validate('pairing_decision', {'scope': offer['scope'], 'allow': allow, 'remember': remember})
        return validate('pairing_offer', self.call(f"requests/{offer['id']}/decision", body))

    def redeem(self, request_id, *, desktop_visible):
        body = validate('pairing_redemption', {'desktop_visible': desktop_visible})
        ticket = validate('pairing_ticket', self.call(f'requests/{request_id}/redeem', body))
        # 本机绑定不允许配对响应把邀请转送到另一个 origin。
        if ticket['endpoint'] != self.transport.endpoint:
            raise ProtocolError('identity_mismatch', 'Pairing ticket changed the selected endpoint', 409)
        client = Client(ticket['endpoint'], expected_game_id=self.transport.expected_game_id)
        client.join(ticket['invitation'], ticket['request'])
        return client
