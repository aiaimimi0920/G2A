"""启动桥接、独立游戏与 Node 伙伴三个进程，不调用 Mot 或公网业务服务。"""
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading

from g2a.bridge import BridgeMailbox, serve_bridge


def run_demo():
    node = shutil.which('node')
    if node is None:
        raise RuntimeError('Node.js 20+ is required')
    source = Path(__file__).resolve().parent
    env = {k: v for k, v in os.environ.items() if not k.startswith('G2A_') or k == 'G2A_JS_MODULE'}
    processes = []
    mailbox = BridgeMailbox()
    with serve_bridge(mailbox) as endpoint:
        try:
            game = subprocess.Popen([sys.executable, '-B', str(source / 'outbound_game.py')],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            processes.append(game)
            game.stdin.write(json.dumps({'endpoint': endpoint, 'game_token': mailbox.game_token}).encode())
            game.stdin.close(); game.stdin = None
            startup = queue.Queue()
            reader = threading.Thread(target=lambda: startup.put(game.stdout.readline()), daemon=True)
            reader.start()
            invitation = json.loads(startup.get(timeout=5))['invitation']
            reader.join(timeout=1)
            agent = subprocess.Popen([node, str(source / 'javascript_companion.mjs')],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            processes.append(agent)
            config = {'endpoint': endpoint, 'bridge_token': mailbox.agent_token, 'game_id': 'key-quest',
                'invitation': invitation, 'request': dict(protocol='0.1.0-dev', agent_id='fox', player_id='alice',
                    default_avatar={'id': 'fox', 'format': 'text', 'label': 'Fox'}, desktop_visible=True,
                    user_policy={}, allowed_actions=['find-key'])}
            stdout, stderr = agent.communicate(json.dumps(config).encode(), timeout=20)
            if agent.returncode != 0:
                raise RuntimeError('Node companion failed: ' + stderr.decode('utf-8', errors='replace'))
            game_out, game_err = game.communicate(timeout=5)
            if game.returncode != 0:
                raise RuntimeError('Outbound game failed: ' + game_err.decode('utf-8', errors='replace'))
            result = {'game': json.loads(game_out), 'companion': json.loads(stdout), 'mot_services_used': False,
                      'transport': 'outbound-poll', 'process_ids': [os.getpid(), game.pid, agent.pid]}
            assert len(set(result['process_ids'])) == 3
            assert result['game']['executions'] == 1 and result['game']['bind_attempts'] == 0
            return result
        finally:
            # 只清理本次 Popen 创建且尚未退出的两个子进程，不按名称杀进程。
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream and not stream.closed:
                        stream.close()


if __name__ == '__main__':
    print(json.dumps(run_demo(), ensure_ascii=False, indent=2))
