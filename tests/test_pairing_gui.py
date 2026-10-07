import importlib.util
import gc
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from g2a.http import serve
from g2a.pairing import PairingCoordinator


@unittest.skipUnless(os.environ.get('G2A_GUI_TEST') == '1', 'Set G2A_GUI_TEST=1 on a Tk display to verify windows')
class PairingWindowTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / 'examples/local_pairing.py'
        spec = importlib.util.spec_from_file_location('local_pairing_example', path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.host = self.module.demo_host()
        self.server = serve(self.host)
        endpoint = self.server.__enter__()
        self.addCleanup(self.server.__exit__, None, None, None)
        self.coordinator = PairingCoordinator()
        self.coordinator.register_game(self.host, endpoint)
        self.root = self.module.tk.Tk()
        self.app = self.module.PairingDemo(self.root, self.coordinator)
        self.addCleanup(self.close_windows)
        self.root.update()

    def close_windows(self):
        self.app.close()
        self.app = None
        self.root = None
        gc.collect()

    def test_desktop_question_denial_and_real_window_restore(self):
        self.app.start_button.invoke()
        self.root.update()
        self.app.discover_button.invoke()
        self.assertIsNone(self.app.client)
        self.assertFalse(self.host.invitations)
        self.app.deny_button.invoke()
        self.assertEqual(self.app.desktop.state(), 'normal')
        self.app.discover_button.invoke()
        self.app.approve_button.invoke()
        self.root.update()
        self.assertIsNotNone(self.app.client)
        self.assertEqual(self.app.desktop.state(), 'withdrawn')
        self.app.leave_button.invoke()
        self.root.update()
        self.assertEqual(self.app.desktop.state(), 'normal')

    def test_game_link_launches_only_after_approval(self):
        self.app.link_button.invoke()
        self.assertIsNone(self.app.desktop)
        self.assertFalse(self.host.invitations)
        self.app.approve_button.invoke()
        self.assertIsNotNone(self.app.desktop)
        self.assertIsNotNone(self.app.client)
        self.app.leave_button.invoke()
        self.assertEqual(self.app.desktop.state(), 'normal')

    def test_configured_auto_join_and_revocation(self):
        self.app.start_button.invoke()
        self.app.remember.set(True)
        self.app.discover_button.invoke()
        self.app.approve_button.invoke()
        self.app.leave_button.invoke()
        self.app.discover_button.invoke()
        self.assertIsNotNone(self.app.client)
        self.app.leave_button.invoke()
        self.app.revoke()
        self.app.discover_button.invoke()
        self.assertIsNone(self.app.client)

    def test_originally_hidden_window_stays_hidden_after_leave(self):
        self.app.start_button.invoke()
        self.app.desktop.withdraw()
        self.app.discover_button.invoke()
        self.app.approve_button.invoke()
        self.app.leave_button.invoke()
        self.assertEqual(self.app.desktop.state(), 'withdrawn')

    def test_window_changed_during_question_restores_latest_state(self):
        self.app.start_button.invoke()
        self.app.discover_button.invoke()
        self.app.desktop.withdraw()
        self.app.approve_button.invoke()
        self.app.leave_button.invoke()
        self.assertEqual(self.app.desktop.state(), 'withdrawn')

    def test_game_prompt_does_not_reshow_window_started_while_waiting(self):
        self.app.link_button.invoke()
        self.app.start_button.invoke()
        self.app.desktop.withdraw()
        self.app.approve_button.invoke()
        self.assertIsNotNone(self.app.client)
        self.app.leave_button.invoke()
        self.assertEqual(self.app.desktop.state(), 'withdrawn')

    def test_closed_companion_needs_new_launch_approval(self):
        self.app.start_button.invoke()
        self.app.discover_button.invoke()
        self.app.stop_desktop()
        self.app.approve_button.invoke()
        self.assertIsNone(self.app.desktop)
        self.assertIsNone(self.app.client)
        self.assertFalse(self.host.invitations)

    def test_prompt_shows_current_approved_game_name(self):
        self.host.descriptor['name'] = '重新命名的游戏'
        self.app.link_button.invoke()
        self.assertIn('重新命名的游戏', self.app.status.get())

    def test_game_closed_session_restores_real_window(self):
        self.app.start_button.invoke()
        self.app.discover_button.invoke()
        self.app.approve_button.invoke()
        self.host.leave(self.app.client.session['id'], self.host.admin_token, 'game_exit')
        self.app._poll()
        self.assertEqual(self.app.desktop.state(), 'normal')
        self.assertIsNone(self.app.client)

    def test_transport_failure_and_expired_lease_restore_real_window(self):
        self.app.start_button.invoke()
        self.app.discover_button.invoke()
        self.app.approve_button.invoke()
        client = self.app.client
        client.deadline = client.clock() - 1
        # 故障注入；不是实际断网或杀进程的证明。
        with patch.object(client, 'call', side_effect=ConnectionError('simulated disconnect')):
            self.app._poll()
        self.assertEqual(self.app.desktop.state(), 'normal')
        self.assertIsNone(self.app.client)
