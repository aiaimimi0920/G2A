"""独立游戏进程；仅向可信父进程的匿名管道交付配对启动凭据。"""
import json
import sys
import threading

from g2a.local_pairing import LocalPairingService, serve_local_pairing
from godot_demo import make_host


def main():
    host = make_host()
    host.descriptor['name'] = '跨进程钥匙探险'
    service = LocalPairingService(host)
    agent_token = service.enroll('fox', 'alice')
    stop = threading.Event()
    failures = []
    evidence = {'executions': 0, 'proactive_chat': False}

    def game_loop():
        seen, cursors = set(), {}
        try:
            while not stop.wait(0.01):
                with host.lock:
                    for session in list(host.sessions.values()):
                        if session.id not in seen:
                            host.send(session.id, host.admin_token, dict(id='hall', type='game.context', sender='key-quest',
                                data={'summary': '大厅有钥匙', 'facts': {'room': 'hall'},
                                      'provenance': {'kind': 'shared_experience', 'source_id': 'hall', 'player_id': 'alice'}}))
                            seen.add(session.id)
                        page = host.poll(session.id, host.admin_token, cursors.get(session.id, 0))
                        cursors[session.id] = page['cursor']
                        for event in page['events']:
                            message = event['message']
                            if message['type'] == 'chat.message' and message['sender'] == 'fox':
                                evidence['proactive_chat'] = True
                            if message['type'] == 'action.request':
                                host.claim_action(session.id, host.admin_token, message['id'])
                                evidence['executions'] += 1
                                host.send(session.id, host.admin_token, dict(id='found', type='action.result', sender='key-quest',
                                    data={'request_id': message['id'], 'status': 'succeeded', 'details': {'item': 'gold-key'}}))
        except BaseException as error:
            failures.append(type(error).__name__)

    with serve_local_pairing(service) as endpoint:
        print(json.dumps({'endpoint': endpoint, 'agent_token': agent_token,
                          'controller_token': service.controller_token}), flush=True)
        thread = threading.Thread(target=game_loop, daemon=True)
        thread.start()
        try:
            for line in sys.stdin:
                command = json.loads(line)
                if command == 'stop':
                    break
                if command != 'stats':
                    raise ValueError('Unknown trusted launcher command')
                with host.lock:
                    print(json.dumps({**evidence, 'invitations': len(host.invitations), 'sessions': len(host.sessions),
                        'active_sessions': sum(s.state == 'active' for s in host.sessions.values()), 'failures': failures}), flush=True)
        finally:
            stop.set(); thread.join(timeout=3)


if __name__ == '__main__':
    main()
