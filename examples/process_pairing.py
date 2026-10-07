"""可信本地启动器示例：审批控制台、游戏、伙伴是独立进程。"""
import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time

from g2a.pairing_client import PairingClient


def read_line(process):
    result = queue.Queue()
    reader = threading.Thread(target=lambda: result.put(process.stdout.readline()), daemon=True)
    reader.start()
    value = result.get(timeout=5)
    reader.join(timeout=1)
    if not value:
        raise RuntimeError('Child process exited before its response')
    return json.loads(value)


def join_request():
    return dict(protocol='0.1.0-dev', agent_id='fox', player_id='alice',
        default_avatar={'id': 'fox', 'format': 'text', 'label': '狐狸'}, desktop_visible=True,
        user_policy={'spoilers': 'avoid_unknown'}, allowed_actions=['find-key'])


def run_demo(*, entry='game', decision=None, agent_language='javascript'):
    source = Path(__file__).resolve().parent
    # 具体程序由可信启动器固定；网络请求不能提供命令行、路径或 URI handler。
    env = {k: v for k, v in os.environ.items() if not k.startswith('G2A_') or k == 'G2A_JS_MODULE'}
    game = subprocess.Popen([sys.executable, '-B', str(source / 'pairing_game.py')], env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    agent = None
    try:
        startup = read_line(game)
        controller = PairingClient(startup['endpoint'], startup['controller_token'], expected_game_id='key-quest')

        def launch(request_id=None):
            if agent_language == 'javascript':
                node = shutil.which('node')
                if node is None:
                    raise RuntimeError('Node.js 20+ is required for the JavaScript companion')
                command = [node, str(source / 'pairing_agent.mjs')]
            elif agent_language == 'python':
                command = [sys.executable, '-B', str(source / 'pairing_agent.py')]
            else:
                raise ValueError('Unknown companion implementation')
            peer = subprocess.Popen(command, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            config = {'endpoint': startup['endpoint'], 'agent_token': startup['agent_token'],
                      'entry': entry, 'request': join_request(), 'request_id': request_id}
            peer.stdin.write(json.dumps(config).encode('utf-8'))
            peer.stdin.close(); peer.stdin = None
            return peer

        if entry == 'desktop':
            agent = launch()
            deadline = time.monotonic() + 5
            offers = []
            while time.monotonic() < deadline and not offers:
                offers = controller.requests()
                time.sleep(0.02)
            if not offers:
                raise RuntimeError('Desktop companion did not request pairing')
            offer = controller.offer(offers[0]['id'])
        elif entry == 'game':
            offer = controller.request(join_request(), game_initiated=True)
        else:
            raise ValueError('Unknown entry')
        game.stdin.write(b'"stats"\n'); game.stdin.flush()
        before = read_line(game)
        assert before['invitations'] == 0 and before['sessions'] == 0
        assert offer['state'] == 'awaiting_approval'
        agent_running_before_decision = agent is not None and agent.poll() is None
        if decision is None:
            print(f"游戏：{offer['game_name']}；伙伴：{offer['agent_id']}；玩家：{offer['player_id']}")
            print('申请内容：' + json.dumps(offer['request'], ensure_ascii=False, indent=2))
            print('游戏条件：' + json.dumps(offer['descriptor'], ensure_ascii=False, indent=2))
            print('批准后启动伙伴进程。' if offer['launch_required'] else '伙伴进程已运行，正在等待批准。')
            decision = input('输入“允许”加入，其余输入均拒绝：').strip() == '允许'
        controller.decide(offer, allow=decision)
        if entry == 'game' and decision:
            agent = launch(offer['id'])
        result = {'joined': False, 'denied': True}
        if agent:
            stdout, stderr = agent.communicate(timeout=15)
            if agent.returncode:
                raise RuntimeError('Companion failed: ' + stderr.decode('utf-8', errors='replace'))
            result = json.loads(stdout)
        game.stdin.write(b'"stats"\n'); game.stdin.flush()
        after = read_line(game)
        assert not after['failures']
        assert after['sessions'] == (1 if decision else 0)
        assert after['invitations'] == (1 if decision else 0)
        return {'entry': entry, 'approved': decision, 'before': before, 'after': after, 'companion': result,
                'agent_language': agent_language, 'agent_running_before_decision': agent_running_before_decision,
                'game_pid': game.pid, 'agent_pid': agent.pid if agent else None, 'controller_pid': os.getpid(),
                'agent_started_after_approval': entry == 'game' and agent is not None}
    finally:
        if agent:
            if agent.poll() is None:
                agent.kill()
            agent.wait(timeout=5)
        if game.poll() is None:
            try:
                game.stdin.write(b'"stop"\n'); game.stdin.flush()
                game.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                game.kill(); game.wait(timeout=5)
        for process in (agent, game):
            if process:
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream and not stream.closed:
                        stream.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--entry', choices=['desktop', 'game'], default='game')
    parser.add_argument('--agent', choices=['python', 'javascript'], default='javascript')
    args = parser.parse_args()
    print(json.dumps(run_demo(entry=args.entry, agent_language=args.agent), ensure_ascii=False, indent=2))
