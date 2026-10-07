"""可信本地连接协调器；不是公开注册服务或跨供应商身份提供者。"""
from copy import deepcopy
import secrets
import time

from .client import Client
from .runtime import fingerprint
from .validation import ProtocolError, validate


class PairingCoordinator:
    """供可信宿主 UI 调用。Agent 不得获得本对象、approve 或注册接口。"""

    def __init__(self, *, clock=time.monotonic):
        self.clock = clock
        self.games = {}
        self.pending = {}
        self.grants = set()

    def register_game(self, host, endpoint):
        # 复用客户端的 URL 安全检查。只注册调用方实际拥有的宿主，不扫描端口。
        game_id = host.descriptor['game_id']
        Client(endpoint, expected_game_id=game_id)
        if game_id in self.games:
            raise ProtocolError('already_registered', 'Game instance already registered', 409)
        if len(self.games) >= 32:
            raise ProtocolError('resource_limit', 'Local game capacity reached', 429)
        self.games[game_id] = (host, endpoint, secrets.token_hex(16))

    def discover(self):
        return [deepcopy(host.descriptor) for host, _, _ in self.games.values()]

    def _scope(self, game_id, request):
        host, endpoint, instance = self.games[game_id]
        with host.lock:
            return fingerprint(dict(instance=instance, endpoint=endpoint,
                descriptor=host.descriptor, revision=host.revision,
                # 桌面当前是否显示不改变永久授权范围；每次连接仍保存实际状态。
                request={k: v for k, v in request.items() if k != 'desktop_visible'}))

    def request(self, game_id, request, *, initiated_by, companion_running):
        validate('join', request)
        if game_id not in self.games:
            raise ProtocolError('game_not_found', 'Game is not registered', 404)
        if initiated_by not in {'desktop', 'game'}:
            raise ProtocolError('invalid_entry', 'Unknown connection entry')
        if initiated_by == 'desktop' and not companion_running:
            raise ProtocolError('companion_not_running', 'Desktop discovery requires a running companion', 409)
        # 有界过期回收，不淘汰尚有效的用户决定。
        self.pending = {k: v for k, v in self.pending.items() if self.clock() < v['expires']}
        if len(self.pending) >= 64:
            raise ProtocolError('resource_limit', 'Connection request capacity reached', 429)
        host, endpoint, _ = self.games[game_id]
        with host.lock:
            if not set(request['allowed_actions']) <= host.capabilities.keys():
                raise ProtocolError('permission_denied', 'Requested actions exceed game capabilities', 403)
            scope = self._scope(game_id, request)
            offer = dict(id=secrets.token_hex(16), game_id=game_id, endpoint=endpoint,
                game_name=host.descriptor['name'], agent_id=request['agent_id'], player_id=request['player_id'],
                actions=list(request['allowed_actions']), presentation=host.descriptor['presentation'],
                initiated_by=initiated_by, launch_required=not companion_running,
                state='authorized' if companion_running and scope in self.grants else 'awaiting_approval')
        self.pending[offer['id']] = dict(offer=offer, request=deepcopy(request), scope=scope,
                                          expires=self.clock() + 60)
        return deepcopy(offer)

    def _get(self, request_id):
        pending = self.pending.get(request_id)
        if pending is None or self.clock() >= pending['expires']:
            raise ProtocolError('request_expired', 'Connection request expired', 409)
        if pending['scope'] != self._scope(pending['offer']['game_id'], pending['request']):
            raise ProtocolError('approval_stale', 'Game or requested capabilities changed; ask again', 409)
        return pending

    def approve(self, request_id, *, remember=False):
        pending = self._get(request_id)
        if pending['offer']['state'] != 'awaiting_approval':
            raise ProtocolError('invalid_decision', 'Request is not awaiting a user decision', 409)
        pending['offer']['state'] = 'authorized'
        if remember:
            self.grants.add(pending['scope'])

    def deny(self, request_id):
        pending = self._get(request_id)
        if pending['offer']['state'] not in {'awaiting_approval', 'authorized'}:
            raise ProtocolError('invalid_decision', 'Request is no longer pending', 409)
        pending['offer']['state'] = 'denied'

    def revoke_automatic_join(self):
        self.grants.clear()
        # 撤销还未连接的自动授权；已经连接的会话由明确退出操作结束。
        for pending in self.pending.values():
            if pending['offer']['state'] == 'authorized':
                pending['offer']['state'] = 'awaiting_approval'

    def connect(self, request_id, *, desktop_visible=None):
        pending = self._get(request_id)
        if pending['offer']['state'] != 'authorized':
            raise ProtocolError('consent_required', 'User approval is required before joining', 403)
        game_id = pending['offer']['game_id']
        host, endpoint, _ = self.games[game_id]
        request = deepcopy(pending['request'])
        if desktop_visible is not None:
            if not isinstance(desktop_visible, bool):
                raise ProtocolError('invalid_message', 'Desktop visibility must be a boolean')
            request['desktop_visible'] = desktop_visible
        # 将授权范围复核与邀请创建置于同一个宿主锁内。
        with host.lock:
            self._get(request_id)
            invitation = host.invite(request['agent_id'], request['player_id'],
                                     allowed_actions=request['allowed_actions'], ttl=30,
                                     expected_state=host.authorization_state())
        client = Client(endpoint, expected_game_id=game_id)
        pending['offer']['state'] = 'connecting'
        try:
            client.join(invitation, request)
        except Exception:
            pending['offer']['state'] = 'failed'
            raise
        pending['offer']['state'] = 'connected'
        return client
