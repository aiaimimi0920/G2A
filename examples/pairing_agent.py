"""只获得已登记伙伴凭据的独立客户端；不能批准自己的申请。"""
import json
import sys
import time

from g2a.pairing_client import PairingClient


def main():
    config = json.loads(sys.stdin.read(65537))
    pairing = PairingClient(config['endpoint'], config['agent_token'], expected_game_id='key-quest')
    games = pairing.discover()
    assert games[0]['game_id'] == 'key-quest'
    if config['entry'] == 'desktop':
        offer = pairing.request(config['request'])
        request_id = offer['id']
    else:
        request_id = config['request_id']
    deadline = time.monotonic() + 55
    while time.monotonic() < deadline:
        offer = pairing.offer(request_id)
        if offer['state'] == 'denied':
            print(json.dumps({'denied': True, 'joined': False}), flush=True)
            return
        if offer['state'] == 'authorized':
            break
        time.sleep(0.03)
    else:
        raise TimeoutError('No user decision within request lifetime')
    client = pairing.redeem(request_id, desktop_visible=config['request']['desktop_visible'])
    try:
        sent, result = False, None
        while time.monotonic() < deadline and result is None:
            page = client.poll()
            if not sent and any(e['message']['type'] == 'game.context' for e in page['events']):
                client.send('chat.message', {'text': '我去拿钥匙。', 'channel': 'private', 'recipients': ['alice']})
                client.send('action.request', {'action': 'find-key', 'arguments': {'room': 'hall'},
                                              'capability_revision': client.session['capability_revision']})
                sent = True
            result = next((e['message']['data'] for e in page['events'] if e['message']['type'] == 'action.result'), None)
            time.sleep(0.01)
        assert result and result['status'] == 'succeeded'
    finally:
        client.leave()
    print(json.dumps({'joined': True, 'result': result, 'desktop_restored': client.desktop_visible,
                      'consent_required': True}), flush=True)


if __name__ == '__main__':
    main()
