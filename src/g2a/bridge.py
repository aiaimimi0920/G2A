"""出站轮询桥接参考：游戏端不监听端口，桥接服务不能获得游戏管理员令牌。"""
from contextlib import contextmanager
from copy import deepcopy
from http.server import ThreadingHTTPServer
import json
import re
import secrets
import threading
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

from .client import Client
from .http import handler_for
from .validation import ProtocolError, validate


class BridgeMailbox:
    """单个已配对游戏的有界邮箱；配对/同意在可信控制面完成，不提供匿名建箱接口。"""

    def __init__(self, *, timeout=2.0, capacity=32):
        if not 0 < timeout <= 3 or not 1 <= capacity <= 64:
            raise ValueError('Invalid bridge limits')
        self.timeout, self.capacity = timeout, capacity
        self.game_token = secrets.token_urlsafe(32)
        self.agent_token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.requests = {}
        self.closed = False

    def authorize(self, token, role):
        expected = self.game_token if role == 'game' else self.agent_token
        if not isinstance(token, str) or not token.isascii() or not secrets.compare_digest(token, expected):
            raise ProtocolError('unauthenticated', 'Invalid bridge credential', 401)
        if self.closed:
            raise ProtocolError('bridge_closed', 'Bridge has been revoked', 410)

    def call(self, token, command):
        validate('bridge_call', command)
        with self.lock:
            self.authorize(token, 'agent')
            if len(self.requests) >= self.capacity:
                raise ProtocolError('resource_limit', 'Bridge request capacity reached', 429)
            ident = secrets.token_hex(16)
            item = dict(id=ident, command=deepcopy(command), delivered=False,
                        ready=threading.Event(), response=None)
            self.requests[ident] = item
        try:
            if not item['ready'].wait(self.timeout):
                # 请求可能已经被领取执行；不可把传输超时解释为动作失败或自动重发。
                raise ProtocolError('bridge_timeout', 'Outcome is unknown; do not retry effects blindly', 504)
            status, result = item['response']
            if status != 200:
                error = result['error']
                raise ProtocolError(error['code'], error['message'], status)
            return deepcopy(result)
        finally:
            with self.lock:
                self.requests.pop(ident, None)

    def pull(self, token):
        with self.lock:
            self.authorize(token, 'game')
            for item in self.requests.values():
                if not item['delivered']:
                    item['delivered'] = True
                    return {'requests': [dict(id=item['id'], command=deepcopy(item['command']))]}
            return {'requests': []}

    def reply(self, token, response):
        validate('bridge_reply', response)
        with self.lock:
            self.authorize(token, 'game')
            item = self.requests.get(response['id'])
            if item is None or not item['delivered'] or item['ready'].is_set():
                raise ProtocolError('request_gone', 'Request is expired, undelivered or already answered', 409)
            item['response'] = (response['status'], deepcopy(response['result']))
            item['ready'].set()
            return {'accepted': True}

    def close(self):
        with self.lock:
            self.closed = True
            for item in self.requests.values():
                if not item['ready'].is_set():
                    item['response'] = (410, ProtocolError('bridge_closed', 'Bridge revoked').as_dict())
                    item['ready'].set()


def bridge_handler(mailbox):
    def dispatch(handler, method):
        auth = handler.headers.get_all('Authorization', [])
        if len(auth) != 1 or not auth[0].startswith('Bearer '):
            raise ProtocolError('unauthenticated', 'One bridge credential required', 401)
        token = auth[0][7:]
        route = (method, handler.path)
        if route == ('POST', '/bridge/call'):
            mailbox.authorize(token, 'agent')
            return mailbox.call(token, handler.body(max_bytes=131072))
        if route == ('GET', '/bridge/pull'):
            return mailbox.pull(token)
        if route == ('POST', '/bridge/reply'):
            mailbox.authorize(token, 'game')
            return mailbox.reply(token, handler.body(max_bytes=270336))
        raise ProtocolError('not_found', 'Unknown bridge operation', 404)
    return handler_for(None, dispatch_override=dispatch)


@contextmanager
def serve_bridge(mailbox, *, tls_context=None):
    # 测试参考服务器只回环监听；生产部署需要合适的 TLS/资源隔离和身份控制面。
    server = ThreadingHTTPServer(('127.0.0.1', 0), bridge_handler(mailbox))
    if tls_context is not None:
        server.socket = tls_context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"{'https' if tls_context else 'http'}://127.0.0.1:{server.server_port}"
    finally:
        mailbox.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def execute(host, command):
    """固定操作分派，不接收 URL、命令行、模块名或游戏管理员调用。"""
    validate('bridge_call', command)
    operation, args, token = command['operation'], command['arguments'], command['credential']
    # 即使桥接服务伪造请求，管理员令牌也不得用于该 Agent 通道。
    if secrets.compare_digest(token, host.admin_token):
        raise ProtocolError('permission_denied', 'Administrative calls are not bridge operations', 403)
    if operation == 'describe':
        with host.lock:
            return deepcopy(host.descriptor)
    if operation == 'join':
        return host.join(token, args['request'])
    sid = args['session_id']
    if operation == 'poll':
        return host.poll(sid, token, args['cursor'])
    if operation == 'send':
        return host.send(sid, token, args['message'])
    if operation == 'leave':
        return host.leave(sid, token, args['reason'])
    if operation == 'action':
        return host.get_action(sid, token, args['request_id'])
    raise ProtocolError('invalid_operation', 'Unknown bridge operation')


class OutboundGame:
    def __init__(self, host, endpoint, token, *, ssl_context=None):
        self.host, self.token = host, token
        self.transport = Client(endpoint, expected_game_id=host.descriptor['game_id'], ssl_context=ssl_context)

    def step(self):
        page = self.transport.call('/bridge/pull', token=self.token)
        validate('bridge_batch', page)
        for item in page['requests']:
            try:
                result = execute(self.host, item['command'])
                if len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8')) > 262144:
                    raise ProtocolError('response_too_large', 'Response exceeds client limit', 413)
                status = 200
            except ProtocolError as error:
                result, status = error.as_dict(), error.status
            try:
                self.transport.call('/bridge/reply', dict(id=item['id'], result=result, status=status), self.token)
            except ProtocolError as error:
                if error.code != 'request_gone':
                    raise
                # 迟到回包被拒绝，绝不再次执行动作。

    def run(self, stop):
        while not stop.is_set():
            try:
                self.step()
            except (URLError, TimeoutError, ConnectionError):
                # 只重新领取后续请求；丢失的领取/回包不自动重放执行。
                stop.wait(0.2)
            except ProtocolError as error:
                if error.status < 500:
                    raise
                stop.wait(0.2)
            stop.wait(0.02)


class BridgeClient(Client):
    def __init__(self, endpoint, bridge_token, *, expected_game_id, ssl_context=None, **kwargs):
        super().__init__(endpoint, expected_game_id=expected_game_id, ssl_context=ssl_context, **kwargs)
        self.bridge_token = bridge_token

    def call(self, path, body=None, token=None):
        url = urlsplit(path)
        if url.scheme or url.netloc or url.fragment:
            raise ProtocolError('invalid_route', 'Only known protocol operations can be bridged')
        args = {}
        if path == '/.well-known/g2a.json' and body is None:
            operation = 'describe'
        elif path == '/sessions' and body is not None:
            operation, args = 'join', {'request': body}
        else:
            match = re.fullmatch(r'/sessions/([A-Za-z0-9._:-]+)/(?:(events|leave)|actions/([A-Za-z0-9._:-]+))', url.path)
            if not match:
                raise ProtocolError('invalid_route', 'Unsupported bridge route')
            sid, route, action = match.groups()
            args = {'session_id': sid}
            if route == 'events' and body is None:
                query = parse_qs(url.query, keep_blank_values=True)
                if set(query) - {'cursor'} or len(query.get('cursor', ['0'])) != 1:
                    raise ProtocolError('invalid_cursor', 'One cursor required')
                cursor = query.get('cursor', ['0'])[0]
                if not cursor.isascii() or not cursor.isdecimal() or len(cursor) > 10:
                    raise ProtocolError('invalid_cursor', 'Invalid cursor')
                operation = 'poll'; args['cursor'] = int(cursor)
            elif not url.query and route == 'events' and body is not None:
                operation = 'send'; args['message'] = body
            elif not url.query and route == 'leave' and body is not None:
                validate('leave', body)
                operation = 'leave'; args['reason'] = body['reason']
            elif not url.query and action and body is None:
                operation = 'action'; args['request_id'] = action
            else:
                raise ProtocolError('invalid_route', 'Unsupported bridge operation')
        command = validate('bridge_call', dict(operation=operation, arguments=args, credential=token or ''))
        return super().call('/bridge/call', command, self.bridge_token)
