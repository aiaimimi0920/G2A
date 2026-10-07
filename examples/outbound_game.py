"""桥接演示的独立游戏进程：只出站连接，管理员令牌不离开进程。"""
import json
import sys
import time

from g2a.bridge import OutboundGame
from g2a.runtime import GameHost


def main():
    config = json.loads(sys.stdin.read(65537))
    bind_attempts = 0

    def forbid_listeners(event, _):
        nonlocal bind_attempts
        if event == 'socket.bind':
            bind_attempts += 1
            raise RuntimeError('The outbound game must not bind a listening socket')

    sys.addaudithook(forbid_listeners)
    host = GameHost(dict(protocol='0.1.0-dev', game_id='key-quest', name='Outbound Key Quest',
        bindings=['outbound-poll'], avatar_formats=['text'], presentation='hide_desktop',
        policy={'spoilers': 'avoid_unknown'}, actions=[dict(name='find-key', description='寻找大厅钥匙',
            timeout_ms=5000, parameters={'type': 'object', 'properties': {'room': {'enum': ['hall']}},
                                       'required': ['room'], 'additionalProperties': False})]))
    invitation = host.invite('fox', 'alice', team=['bob'], allowed_actions=['find-key'])
    # 可信启动器已明确选择该示例；邀请只通过匿名管道交给它，不写日志/磁盘/argv。
    print(json.dumps({'invitation': invitation}), flush=True)
    game = OutboundGame(host, config['endpoint'], config['game_token'])
    seen, cursor, executions, chat = False, 0, 0, False
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        game.step()
        session = next(iter(host.sessions.values()), None)
        if session is None:
            time.sleep(0.01)
            continue
        if not seen:
            host.send(session.id, host.admin_token, dict(id='hall-1', type='game.context', sender='key-quest',
                data={'summary': '大厅中有一把钥匙', 'facts': {'room': 'hall'},
                      'provenance': {'kind': 'shared_experience', 'source_id': 'hall-1', 'player_id': 'alice'}}))
            seen = True
        page = host.poll(session.id, host.admin_token, cursor)
        cursor = page['cursor']
        for event in page['events']:
            msg = event['message']
            if msg['type'] == 'chat.message' and msg['sender'] == 'fox':
                chat = msg['data']['recipients'] == ['alice', 'bob']
            if msg['type'] == 'action.request':
                claim = host.claim_action(session.id, host.admin_token, msg['id'])
                assert claim['arguments'] == {'room': 'hall'}
                executions += 1
                host.send(session.id, host.admin_token, dict(id='found-1', type='action.result', sender='key-quest',
                    data={'request_id': msg['id'], 'status': 'succeeded', 'details': {'item': 'gold-key'}}))
        if session.state == 'closed':
            print(json.dumps({'executions': executions, 'proactive_chat': chat, 'session_closed': True,
                              'listener_guard': True, 'bind_attempts': bind_attempts}), flush=True)
            return
        time.sleep(0.01)
    raise RuntimeError('Outbound demo did not finish in time')


if __name__ == '__main__':
    main()
