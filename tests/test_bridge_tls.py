"""现场生成一次性证书验证 TLS 信任/主机名，不提交测试私钥。"""
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import unittest
from urllib.error import URLError

from g2a.bridge import BridgeClient, BridgeMailbox, OutboundGame, serve_bridge
from g2a.client import Client
from g2a.runtime import GameHost
from test_bridge import running
from test_protocol import descriptor, join_request


class BridgeTlsTests(unittest.TestCase):
    def test_tls_trust_and_hostname_are_checked_for_both_roles(self):
        openssl = os.environ.get('G2A_OPENSSL') or shutil.which('openssl')
        if not openssl:
            candidate = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Git/usr/bin/openssl.exe'
            openssl = str(candidate) if candidate.is_file() else None
        if not openssl:
            self.skipTest('OpenSSL required to generate ephemeral TLS fixtures; TLS not verified')
        if os.environ.get('G2A_TEST_OUTPUT'):
            Path(os.environ['G2A_TEST_OUTPUT']).mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=os.environ.get('G2A_TEST_OUTPUT')) as directory:
            root = Path(directory)
            cert, key = root / 'cert.pem', root / 'key.pem'
            subprocess.run([openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                '-subj', '/CN=g2a-local-test', '-addext', 'subjectAltName=IP:127.0.0.1',
                '-keyout', str(key), '-out', str(cert)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
            server_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server_tls.load_cert_chain(cert, key)
            trust = ssl.create_default_context(cafile=str(cert))
            host, mailbox = GameHost(descriptor()), BridgeMailbox()
            with serve_bridge(mailbox, tls_context=server_tls) as endpoint:
                with self.assertRaises(URLError):
                    OutboundGame(host, endpoint, mailbox.game_token).step()
                with self.assertRaises(URLError):
                    Client(endpoint.replace('127.0.0.1', 'localhost'), expected_game_id='game-a', ssl_context=trust).call('/bridge/pull', token=mailbox.game_token)
                with running(OutboundGame(host, endpoint, mailbox.game_token, ssl_context=trust)):
                    client = BridgeClient(endpoint, mailbox.agent_token, expected_game_id='game-a', ssl_context=trust)
                    client.join(host.invite('companion-a', 'player-a', allowed_actions=['find-key']), join_request())
                    self.assertFalse(client.desktop_visible)
                    client.poll()
                    client.leave()
                    self.assertTrue(client.desktop_visible)
