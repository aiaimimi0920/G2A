"""实际 Tk 窗口示例：可信本地注册、用户授权、自动加入和呈现恢复。"""
import tkinter as tk
from tkinter import ttk

from g2a.http import serve
from g2a.pairing import PairingCoordinator
from g2a.runtime import GameHost
from g2a.validation import ProtocolError


class PairingDemo:
    def __init__(self, root, coordinator):
        self.root = root
        self.coordinator = coordinator
        self.desktop = None
        self.client = None
        self.pending = None
        self.timer = None
        self.closed = False
        root.title('G2A · 本地连接示例')
        root.geometry('680x460')
        self.game_id = tk.StringVar(root)
        self.agent_id = tk.StringVar(root, 'fox')
        self.remember = tk.BooleanVar(root, False)
        self.status = tk.StringVar(root, '未连接。可以先启动桌面伙伴，或从游戏内发起连接。')
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='游戏与伙伴', font=('', 16)).pack(anchor='w')
        self.games = {item['game_id']: item for item in coordinator.discover()}
        ttk.Label(frame, text='已由可信本地启动器注册的游戏').pack(anchor='w', pady=(12, 2))
        ttk.Combobox(frame, textvariable=self.game_id, values=list(self.games), state='readonly').pack(fill='x')
        if self.games:
            self.game_id.set(next(iter(self.games)))
        ttk.Label(frame, text='选择本地伙伴').pack(anchor='w', pady=(10, 2))
        ttk.Combobox(frame, textvariable=self.agent_id, values=['fox', 'owl'], state='readonly').pack(fill='x')
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x', pady=12)
        self.start_button = ttk.Button(buttons, text='启动桌面伙伴', command=self.start_desktop)
        self.start_button.pack(side='left')
        self.discover_button = ttk.Button(buttons, text='桌面发现并加入', command=lambda: self.request('desktop'))
        self.discover_button.pack(side='left', padx=6)
        self.link_button = ttk.Button(buttons, text='链接我的伙伴', command=lambda: self.request('game'))
        self.link_button.pack(side='left')
        ttk.Label(frame, textvariable=self.status, wraplength=620).pack(anchor='w', pady=8)
        self.approval = ttk.Frame(frame)
        ttk.Checkbutton(self.approval, text='同一游戏、伙伴、玩家和权限不变时，不询问自动加入（本次运行有效）',
                        variable=self.remember).pack(anchor='w')
        decisions = ttk.Frame(self.approval)
        decisions.pack(anchor='w', pady=6)
        self.approve_button = ttk.Button(decisions, text='允许加入', command=self.approve)
        self.approve_button.pack(side='left')
        self.deny_button = ttk.Button(decisions, text='拒绝', command=self.deny)
        self.deny_button.pack(side='left', padx=8)
        footer = ttk.Frame(frame)
        footer.pack(side='bottom', fill='x')
        self.leave_button = ttk.Button(footer, text='退出游戏连接', command=self.leave)
        self.leave_button.pack(side='left')
        ttk.Button(footer, text='撤销自动加入', command=self.revoke).pack(side='left', padx=8)
        ttk.Label(footer, text='本地示例 · 不连接 Mot 服务').pack(side='right')
        root.protocol('WM_DELETE_WINDOW', self.close)

    def start_desktop(self):
        if self.desktop is None:
            self.desktop = tk.Toplevel(self.root)
            self.desktop.title('G2A · 桌面伙伴')
            self.desktop.geometry('260x160')
            ttk.Label(self.desktop, text='你的伙伴', font=('', 20)).pack(pady=25)
            ttk.Label(self.desktop, text='加入游戏时按协议隐藏或共存').pack()
            self.desktop.protocol('WM_DELETE_WINDOW', self.stop_desktop)
        if self.client is None:
            self.desktop.deiconify()

    def stop_desktop(self):
        if self.client:
            self.leave()
        if self.desktop:
            self.desktop.destroy()
            self.desktop = None

    def request(self, entry):
        if self.client:
            self.status.set('请先退出当前游戏连接。')
            return
        if self.pending:
            self.deny()
        try:
            game_id = self.game_id.get()
            self.games = {item['game_id']: item for item in self.coordinator.discover()}
            descriptor = self.games[game_id]
            request = dict(protocol='0.1.0-dev', agent_id=self.agent_id.get(), player_id='alice',
                default_avatar={'id': self.agent_id.get(), 'format': 'text', 'label': self.agent_id.get()},
                desktop_visible=self.desktop.state() != 'withdrawn' if self.desktop else True,
                user_policy={}, allowed_actions=[a['name'] for a in descriptor['actions']])
            self.pending = self.coordinator.request(game_id, request,
                initiated_by=entry, companion_running=self.desktop is not None)
            if self.pending['state'] == 'authorized':
                self._connect()
                return
            actions = '、'.join(self.pending['actions']) or '无行动权限'
            self.status.set(f"允许 {self.pending['agent_id']} 以玩家 alice 的伙伴身份加入“{self.pending['game_name']}”？\n"
                            f"行动权限：{actions}；呈现：{self.pending['presentation']}。"
                            + ('\n批准后启动本地伙伴窗口。' if self.pending['launch_required'] else ''))
            self.approval.pack(fill='x', pady=8)
        except (ProtocolError, KeyError) as error:
            self.status.set('无法请求连接：' + getattr(error, 'code', 'game_not_found'))

    def approve(self):
        if not self.pending:
            return
        try:
            self.coordinator.approve(self.pending['id'], remember=self.remember.get())
            self._connect()
        except ProtocolError as error:
            self.status.set('未连接：' + error.code)

    def _connect(self):
        try:
            if self.desktop is None:
                if not self.pending['launch_required']:
                    raise ProtocolError('companion_not_running', 'Request permission to launch the companion again', 409)
                self.start_desktop()
            self.client = self.coordinator.connect(self.pending['id'],
                desktop_visible=self.desktop.state() != 'withdrawn')
            self._apply_presentation()
            self.status.set(f"已连接：{self.client.session['game_id']} / {self.client.session['agent_id']}。")
            self.pending = None
            self.approval.pack_forget()
            self.timer = self.root.after(250, self._poll)
        except Exception as error:
            self.status.set('连接未完成：' + getattr(error, 'code', type(error).__name__))

    def _apply_presentation(self):
        if self.desktop and self.client:
            if self.client.desktop_visible:
                self.desktop.deiconify()
            else:
                self.desktop.withdraw()

    def _poll(self):
        if self.timer:
            self.root.after_cancel(self.timer)
        self.timer = None
        if self.closed or not self.client:
            return
        try:
            self.client.poll()
        except Exception:
            self.client.check_lease()
            self.status.set('连接中断；租约到期后恢复加入前窗口状态。')
        self._apply_presentation()
        if self.client.session['state'] == 'closed' or self.client.check_lease():
            self._apply_presentation()
            self.client = None
        else:
            self.timer = self.root.after(250, self._poll)

    def deny(self):
        if self.pending:
            try:
                self.coordinator.deny(self.pending['id'])
            except ProtocolError:
                pass
        self.pending = None
        self.approval.pack_forget()
        self.status.set('未加入游戏。')

    def revoke(self):
        self.coordinator.revoke_automatic_join()
        self.remember.set(False)
        self.status.set('自动加入授权已撤销；当前会话不会因此强制退出。')

    def leave(self):
        if self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None
        if self.client:
            try:
                self.client.leave()
            except Exception:
                self.status.set('远端退出未确认，已恢复本地窗口。')
            else:
                self.status.set('已退出，恢复加入前窗口状态。')
            finally:
                self._apply_presentation()
                self.client = None

    def close(self):
        self.closed = True
        self.leave()
        self.root.destroy()
        # Tk 变量必须在 UI 线程释放，不能留给后续 HTTP 工作线程触发的 GC。
        self.game_id = None
        self.agent_id = None
        self.remember = None
        self.status = None


def demo_host():
    return GameHost(dict(protocol='0.1.0-dev', game_id='local-adventure', name='本地冒险示例',
        bindings=['http-poll'], avatar_formats=['text'], presentation='hide_desktop', policy={},
        actions=[dict(name='find-key', description='寻找钥匙', timeout_ms=5000,
                      parameters={'type': 'object'})]))


if __name__ == '__main__':
    host = demo_host()
    with serve(host) as endpoint:
        coordinator = PairingCoordinator()
        coordinator.register_game(host, endpoint)
        root = tk.Tk()
        PairingDemo(root, coordinator)
        root.mainloop()
