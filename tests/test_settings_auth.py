import base64
import json
import os
import queue
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from irdisc import IRCClient
from irdisc_settings import Profile, Preferences, append_log, load_preferences, save_preferences


class SettingsTests(unittest.TestCase):
    def test_round_trip_permissions_and_no_password_field(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            prefs = Preferences(Profile(nick='Max', sasl_account='Max'), theme='mono', logging=True)
            save_preferences(prefs, path)
            loaded = load_preferences(path)
            self.assertEqual(loaded.profile.nick, 'Max')
            self.assertEqual(loaded.profile.sasl_account, 'Max')
            self.assertIn('OFTC', loaded.profiles)
            self.assertNotIn('password', path.read_text())
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_invalid_file_returns_safe_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text('{"profile":{"port":99999}}')
            self.assertEqual(load_preferences(path).profile.host, '')

    def test_log_filename_and_line_safety(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            append_log('../bad/channel', 'one\ntwo', root)
            files = list(root.iterdir())
            self.assertEqual(len(files), 1)
            self.assertNotIn('..', files[0].name)
            self.assertEqual(files[0].read_text().count('\n'), 1)


class SaslTests(unittest.TestCase):
    def client(self, account='Max', password='secret'):
        client = IRCClient('irc.example', 6697, 'Max', queue.Queue(),
                           sasl_account=account, sasl_password=password)
        client.sock = MagicMock()
        client.connected = True
        return client

    def sent(self, client):
        return [call.args[0].decode().strip() for call in client.sock.sendall.call_args_list]

    def test_plain_sasl_negotiation(self):
        client = self.client()
        client._handle(':srv CAP Max LS * :multi-prefix')
        self.assertEqual(self.sent(client), [])
        client._handle(':srv CAP Max LS :sasl=PLAIN,EXTERNAL')
        client._handle(':srv CAP Max ACK :sasl')
        client._handle('AUTHENTICATE +')
        lines = self.sent(client)
        self.assertEqual(lines[0], 'CAP REQ :sasl')
        self.assertEqual(lines[1], 'AUTHENTICATE PLAIN')
        encoded = lines[2].split(' ', 1)[1]
        self.assertEqual(base64.b64decode(encoded), b'\0Max\0secret')
        self.assertNotIn('secret', '\n'.join(lines))
        client._handle(':srv 903 Max :SASL success')
        self.assertEqual(self.sent(client)[-1], 'CAP END')

    def test_cap_ends_without_credentials(self):
        client = self.client('', '')
        client._handle(':srv CAP Max LS :multi-prefix sasl')
        self.assertEqual(self.sent(client), ['CAP END'])
