"""预登记身份的本机配对绑定；不是匿名发现或跨供应商身份认证服务。"""
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
import re
import secrets
import threading
import time
from urllib.parse import urlsplit

from .http import handler_for
from .pairing import PairingCoordinator, REQUEST_TTL
from .runtime import fingerprint
from .validation import ProtocolError, validate


class LocalPairingService:
    def __init__(self, host, *, clock=time.monotonic):
        self.host, self.clock, self.lock = host, clock, host.lock
        self.coordinator = PairingCoordinator(clock=clock)
        self.controller_token = secrets.token_urlsafe(32)
        self.agents, self.requests = {}, {}
        self.endpoint = None

    def enroll(self, agent_id, player_id):
        """只由可信安装器/启动器调用，不能通过网络自注册。"""
        with self.lock:
            if len(self.agents) >= 32:
                raise ProtocolError('resource_limit', 'Enrolled companion limit reached', 429)
            if any(not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', value)
                   for value in (agent_id, player_id)):
                raise ProtocolError('invalid_identity', 'Invalid enrolled identity')
            if agent_id in self.agents or len({agent_id, player_id, self.host.descriptor['game_id']}) != 3:
                raise ProtocolError('invalid_identity', 'Distinct registered identities required')
            token = secrets.token_urlsafe(32)
            self.agents[agent_id] = dict(player_id=player_id, token=token, seen=None)
            return token

    def _authenticate(self, token):
        if isinstance(token, str) and token.isascii():
            if secrets.compare_digest(token, self.controller_token):
                return None
            for ident, agent in self.agents.items():
                if secrets.compare_digest(token, agent['token']):
                    return ident
        raise ProtocolError('unauthenticated', 'Invalid local pairing credential', 401)

    def _owned(self, ident, request_id):
        record = self.requests.get(request_id)
        if record is None or ident is not None and record['agent_id'] != ident:
            raise ProtocolError('unauthenticated', 'Request not accessible to this principal', 401)
        self.coordinator.offer(request_id)
        return record

    def _request(self, ident, body, entry):
        validate('pairing_request', body)
        request = body['request']
        agent_id = request['agent_id']
        agent = self.agents.get(agent_id)
        if agent is None or request['player_id'] != agent['player_id'] or ident is not None and ident != agent_id:
            raise ProtocolError('permission_denied', 'Request differs from enrolled identity', 403)
        self.requests = {key: value for key, value in self.requests.items() if self.clock() < value['expires']}
        for request_id, record in self.requests.items():
            if (record['agent_id'], record['entry'], record['nonce']) == (agent_id, entry, body['nonce']):
                if record['fingerprint'] != fingerprint(body):
                    raise ProtocolError('id_conflict', 'Request nonce was already used with different content', 409)
                return self.coordinator.offer(request_id)
        running = agent['seen'] is not None and self.clock() - agent['seen'] < 5
        offer = self.coordinator.request(self.host.descriptor['game_id'], request,
            initiated_by=entry, companion_running=running)
        self.requests[offer['id']] = dict(agent_id=agent_id, entry=entry, nonce=body['nonce'],
            fingerprint=fingerprint(body), expires=self.clock() + REQUEST_TTL)
        return offer

    def _list(self, ident):
        offers = []
        for request_id, record in self.requests.items():
            if self.clock() >= record['expires'] or ident is not None and record['agent_id'] != ident:
                continue
            offer = self.coordinator.offer(request_id)
            offers.append({key: offer[key] for key in ('id', 'game_id', 'agent_id', 'player_id', 'state',
                                                       'initiated_by', 'launch_required')})
        return {'requests': offers}

    def dispatch(self, handler, method):
        url = urlsplit(handler.path)
        if not url.path.startswith('/pairing/'):
            return NotImplemented
        auth = handler.headers.get_all('Authorization', [])
        token = auth[0][7:] if len(auth) == 1 and auth[0].startswith('Bearer ') else ''
        with self.lock:
            ident = self._authenticate(token)
            if url.query:
                raise ProtocolError('invalid_route', 'Pairing routes do not accept query parameters')
            if ident is not None:
                self.agents[ident]['seen'] = self.clock()
            route = (method, url.path)
            if route == ('GET', '/pairing/discovery'):
                return {'games': self.coordinator.discover()}
            if route == ('GET', '/pairing/requests'):
                return self._list(ident)
            if route == ('POST', '/pairing/requests') and ident is not None:
                return self._request(ident, handler.body(), 'desktop')
            if route == ('POST', '/pairing/game-request'):
                if ident is not None:
                    raise ProtocolError('permission_denied', 'Trusted controller required', 403)
                return self._request(None, handler.body(), 'game')
            if route == ('POST', '/pairing/revoke-automatic'):
                if ident is not None:
                    raise ProtocolError('permission_denied', 'Trusted controller required', 403)
                if handler.body() != {}:
                    raise ProtocolError('invalid_message', 'Empty body required')
                self.coordinator.revoke_automatic_join()
                return {'revoked': True}
            match = re.fullmatch(r'/pairing/requests/([a-f0-9]{32})(?:/(decision|redeem))?', url.path)
            if match:
                request_id, operation = match.groups()
                self._owned(ident, request_id)
                if method == 'GET' and operation is None:
                    return self.coordinator.offer(request_id)
                if method == 'POST' and operation == 'decision':
                    if ident is not None:
                        raise ProtocolError('permission_denied', 'Only the trusted user interface can decide', 403)
                    body = validate('pairing_decision', handler.body())
                    offer = self.coordinator.offer(request_id)
                    if body['scope'] != offer['scope']:
                        raise ProtocolError('approval_stale', 'Consent snapshot does not match', 409)
                    if body['allow']:
                        self.coordinator.approve(request_id, remember=body['remember'])
                    else:
                        self.coordinator.deny(request_id)
                    return self.coordinator.offer(request_id)
                if method == 'POST' and operation == 'redeem':
                    if ident is None:
                        raise ProtocolError('permission_denied', 'Only the selected companion can redeem', 403)
                    body = validate('pairing_redemption', handler.body())
                    return self.coordinator.prepare(request_id, desktop_visible=body['desktop_visible'])
            raise ProtocolError('not_found', 'Unknown pairing operation', 404)


@contextmanager
def serve_local_pairing(service):
    if service.endpoint is not None:
        raise ValueError('Create a new service for each listener lifecycle')
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(service.host, dispatch_override=service.dispatch))
    service.endpoint = f'http://127.0.0.1:{server.server_port}'
    service.coordinator.register_game(service.host, service.endpoint)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield service.endpoint
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
