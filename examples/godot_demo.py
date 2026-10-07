"""Godot 游戏 + Python 协议 sidecar + 独立 Node 伙伴，不调用 Mot。"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from g2a.http import serve
from g2a.runtime import GameHost


def make_host():
    return GameHost(dict(protocol='0.1.0-dev', game_id='key-quest', name='Godot Key Quest',
        bindings=['http-poll'], avatar_formats=['text'], presentation='hide_desktop',
        policy={'spoilers': 'avoid_unknown'}, actions=[dict(name='find-key', description='Find the hall key',
            timeout_ms=5000, parameters={'type': 'object', 'properties': {'room': {'enum': ['hall']}},
                                       'required': ['room'], 'additionalProperties': False})]))


def run_demo(godot, output, *, headless=True, blocked=False):
    output = Path(output).resolve()
    # 每次运行保留独立证据，不覆盖前次结果；Godot 导入缓存也留在输出目录。
    output.mkdir(parents=True, exist_ok=False)
    project = output / 'game'
    source = Path(__file__).resolve().parent
    shutil.copytree(source / 'godot_key_quest', project,
                    ignore=shutil.ignore_patterns('.godot', '*.uid'))
    host = make_host()
    invitation = host.invite('fox', 'alice', team=['bob'], allowed_actions=['find-key'])
    node = shutil.which('node')
    if node is None:
        raise RuntimeError('Node.js 20+ is required')
    processes = []
    # 不从环境意外向伙伴转发游戏管理员凭据。
    env = {k: v for k, v in os.environ.items() if not k.startswith('G2A_') or k == 'G2A_JS_MODULE'}
    with serve(host) as endpoint, (output / 'agent.stdout').open('wb') as agent_out, \
            (output / 'agent.stderr').open('wb') as agent_err, \
            (output / 'godot.log').open('wb') as game_log:
        try:
            agent = subprocess.Popen([node, str(source / 'javascript_companion.mjs')],
                stdin=subprocess.PIPE, stdout=agent_out, stderr=agent_err, env=env)
            processes.append(agent)
            config = {'endpoint': endpoint, 'game_id': 'key-quest', 'invitation': invitation,
                'companion_text': "I'll go get the key. Hold the monsters back!",
                'expected_action_status': 'failed' if blocked else 'succeeded',
                'request': dict(protocol='0.1.0-dev', agent_id='fox', player_id='alice',
                    default_avatar={'id': 'fox', 'format': 'text', 'label': 'Fox'}, desktop_visible=True,
                    user_policy={}, allowed_actions=['find-key'])}
            agent.stdin.write(json.dumps(config).encode('utf-8'))
            agent.stdin.close()
            deadline = time.monotonic() + 5
            sid = None
            while time.monotonic() < deadline and agent.poll() is None:
                with host.lock:
                    sid = next(iter(host.sessions), None)
                if sid:
                    break
                time.sleep(0.02)
            if sid is None:
                raise RuntimeError('Companion did not join; see agent.stderr')
            game_env = {**env, 'G2A_ENDPOINT': endpoint, 'G2A_SESSION': sid,
                'G2A_GAME_TOKEN': host.admin_token, 'G2A_EVIDENCE': str(output / 'game.json'),
                'G2A_BLOCKED_KEY': '1' if blocked else '0',
                'G2A_SCREENSHOT': '' if headless else str(output / 'game.png')}
            command = [str(godot), '--path', str(project)]
            if headless:
                command.append('--headless')
            game = subprocess.Popen(command, stdout=game_log, stderr=subprocess.STDOUT, env=game_env)
            processes.append(game)
            if game.wait(timeout=25) != 0:
                raise RuntimeError('Godot game failed; see godot.log')
            game_log.flush()
            engine_log = (output / 'godot.log').read_text(encoding='utf-8', errors='replace')
            if any(marker in engine_log for marker in ('SCRIPT ERROR:', 'ERROR:', 'ObjectDB instances leaked')):
                raise RuntimeError('Godot logged a script error or object leak; see godot.log')
            if agent.wait(timeout=5) != 0:
                raise RuntimeError('Companion failed; see agent.stderr')
            evidence = json.loads((output / 'game.json').read_text(encoding='utf-8'))
            agent_out.flush()
            companion = json.loads((output / 'agent.stdout').read_text(encoding='utf-8'))
            expected_x = 230 if blocked else 690
            if (evidence['key_taken'] != (not blocked)
                    or evidence['executions'] != (0 if blocked else 1)
                    or abs(evidence['fox_x'] - expected_x) > 0.1
                    or not evidence['chat_received'] or not evidence['session_closed']
                    or not companion['desktop_restored']):
                raise RuntimeError('Game world or companion postconditions failed')
            if host.sessions[sid].state != 'closed':
                raise RuntimeError('Protocol session did not close')
            evidence['companion'] = companion
            evidence['headless'] = headless
            (output / 'result.json').write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
            return evidence
        finally:
            # 只清理本启动器持有的子进程句柄，不按进程名清理其他 Godot 会话。
            for process in reversed(processes):
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot', required=True)
    parser.add_argument('--output', required=True, help='New output directory; must not already exist')
    parser.add_argument('--window', action='store_true', help='Render and capture a visible Godot window')
    parser.add_argument('--blocked', action='store_true', help='World rejects an otherwise authorized action')
    args = parser.parse_args()
    print(json.dumps(run_demo(args.godot, args.output, headless=not args.window,
                              blocked=args.blocked), ensure_ascii=False, indent=2))
