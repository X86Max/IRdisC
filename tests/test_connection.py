import copy
import curses
import queue
import socket
import ssl
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from irdisc import Event, IRCClient, connection_error_message
from irdisc_settings import Profile, Preferences, save_preferences, load_preferences, validate_profile
from terminal_ui import ChatApp


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.screen = MagicMock()
        self.screen.getmaxyx.return_value = (25, 100)
        with patch('terminal_ui.load_preferences', return_value=Preferences(Profile(nick='Max', channel=''))):
            self.app = ChatApp(self.screen)

    def test_validation(self):
        for host in ('#ircsdstst:6697', 'irc.example:6697', 'https://irc.example', 'bad host', ''):
            self.assertIn('host', validate_profile(Profile(host=host, nick='Max')))
        for host in ('localhost', 'irc.example.org', '127.0.0.1', '::1'):
            self.assertNotIn('host', validate_profile(Profile(host=host, nick='Max')))
        self.assertFalse(validate_profile(Profile(nick='Max', channel='')))
        self.assertIn('port', validate_profile(Profile(nick='Max', port='bad')))

    @patch('terminal_ui.curses.noecho')
    @patch('terminal_ui.save_preferences')
    def test_cancel_preserves_everything(self, save, _):
        before = copy.deepcopy(self.app.prefs)
        self.screen.get_wch.side_effect = list('changed') + ['\t', '\x15'] + list('wrong') + ['\x1b']
        self.app.edit_connection()
        self.assertEqual(before, self.app.prefs)
        self.assertIs(self.app.profile, self.app.prefs.profile)
        save.assert_not_called()
        self.assertIsNone(self.app.client)

    @patch('terminal_ui.curses.noecho')
    @patch('terminal_ui.save_preferences')
    def test_inline_validation_no_connection(self, save, _):
        self.screen.get_wch.side_effect = ['\t', '\x15'] + list('#bad') + ['\t']*8 + ['\n', '\x1b']
        self.app.edit_connection()
        self.assertTrue(any('hostname or IP' in str(call) for call in self.screen.addnstr.call_args_list))
        save.assert_not_called()

    @patch('terminal_ui.save_preferences')
    def test_save_does_not_touch_active_session(self, save):
        self.app.client = MagicMock(connected=True)
        old_channel = self.app.channel
        self.app.apply_profile(Profile(nick='New', channel='#new'), '', False)
        self.app.client.close.assert_not_called()
        self.assertEqual(old_channel, self.app.channel)

    @patch('terminal_ui.save_preferences', side_effect=OSError('read only'))
    def test_save_failure_rolls_back(self, _):
        before = copy.deepcopy(self.app.prefs)
        with self.assertRaises(OSError):
            self.app.apply_profile(Profile(nick='Other'), '')
        self.assertEqual(before, self.app.prefs)

    @patch('terminal_ui.save_preferences')
    @patch.object(ChatApp, 'start_client')
    def test_replacement_waits_for_old_thread(self, start, _):
        old = MagicMock(connected=True)
        self.app.client = old
        self.app.apply_profile(Profile(nick='Max'), '', True)
        old.close.assert_called_once()
        start.assert_not_called()
        self.app.process_events()
        start.assert_not_called()
        old.thread.is_alive.return_value = False
        self.app.process_events()
        start.assert_called_once()

    def test_disconnect_stops_retry_not_app(self):
        self.app.client = MagicMock(connected=True)
        self.app.prefs.auto_reconnect = True
        self.app.command('/disconnect')
        self.app.events.put(Event('status', 'Disconnected'))
        self.app.process_events()
        self.assertEqual(self.app.status, 'Disconnected')
        self.assertFalse(self.app.reconnect_due)
        self.assertTrue(self.app.running)
        self.app.command('/quit')
        self.assertFalse(self.app.running)

    def test_errors_are_distinct(self):
        failures = [socket.gaierror(), TimeoutError(), ConnectionRefusedError(), ssl.SSLError()]
        self.assertEqual(len(set(map(connection_error_message, failures))), 4)
        self.app.events.put(Event('connection_error', connection_error_message(failures[0])))
        self.app.events.put(Event('status', 'Disconnected'))
        self.app.process_events()
        self.assertEqual(self.app.status, 'Connection error')
        self.assertIn('/connection', str(self.app.buffer('server').messages))

    def test_auth_failure_no_autojoin_or_secrets(self):
        self.app.client = MagicMock(nick='Max', connected=True, sasl_password='private-secret')
        self.app.channel = '#test'
        self.app.sasl_password = 'private-secret'
        self.app.events.put(Event('auth_error', 'private-secret'))
        self.app.events.put(Event('wire', ':server 001 Max :welcome'))
        self.app.process_events()
        self.app.command('/settings')
        self.assertEqual(self.app.status, 'Authentication error')
        self.app.client.send.assert_not_called()
        self.assertNotIn('private-secret', str(self.app.buffers))

    def test_optional_channel(self):
        self.app.client = MagicMock(nick='Max', connected=True)
        self.app.receive(':server 001 Max :Welcome')
        self.app.client.send.assert_not_called()
        self.assertTrue(self.app.ready)

    @patch.object(ChatApp, 'edit_connection')
    def test_entry_points(self, editor):
        self.app.command('/connection')
        self.app.command('/settings edit')
        self.app.key(curses.KEY_F2)
        self.app.key('7')
        self.assertEqual(editor.call_count, 3)

    @patch('terminal_ui.curses.noecho')
    def test_editor_masks_password(self, _):
        self.app.sasl_password = 'super-private'
        self.screen.get_wch.side_effect = ['\t']*8 + ['\x1b']
        self.app.edit_connection()
        drawn = str(self.screen.addnstr.call_args_list)
        self.assertNotIn('super-private', drawn)
        self.assertIn('*************', drawn)

    def test_cancel_connect_during_socket_creation(self):
        client = IRCClient('localhost', 6667, 'Max', queue.Queue(), tls=False)
        sock = MagicMock()
        def create(*args, **kwargs):
            client.close()
            return sock
        with patch('irdisc.socket.create_connection', side_effect=create):
            client._run()
        sock.sendall.assert_not_called()
        sock.close.assert_called_once()

    @patch('terminal_ui.curses.noecho')
    def test_full_recovery_one_app_real_local_server(self, _):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(3)
        port = listener.getsockname()[1]
        received = []
        errors = []
        done = threading.Event()
        def serve():
            try:
                connection, _address = listener.accept()
                with connection:
                    connection.settimeout(3)
                    reader = connection.makefile('rb')
                    while True:
                        line = reader.readline().decode().strip()
                        received.append(line)
                        if line.startswith('USER '):
                            connection.sendall(b':local 001 Max :Welcome\r\n')
                        if line == 'JOIN #recovery':
                            connection.sendall(b':Max!u@local JOIN :#recovery\r\n')
                        if not line or line.startswith('QUIT '):
                            break
                    reader.close()
            except Exception as exc:
                errors.append(exc)
            finally:
                done.set()
        server = threading.Thread(target=serve, daemon=True)
        server.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'config.json'
                self.app.profile = Profile(host='#ircsdstst:6697', nick='Max', tls=False, channel='#recovery')
                self.app.prefs.profile = self.app.profile
                save_preferences(self.app.prefs, path)
                self.app.prefs = load_preferences(path)
                self.app.profile = self.app.prefs.profile
                # Legacy malformed profile produces a recoverable error without opening a socket.
                self.app.command('/connect')
                self.assertEqual(self.app.status, 'Connection error')
                # Also exercise the asynchronous DNS-failure path.
                with patch('irdisc.socket.create_connection', side_effect=socket.gaierror(-2, 'Name or service not known')):
                    self.app.start_client()
                    self.app.client.thread.join(1)
                self.app.process_events()
                self.assertEqual(self.app.status, 'Connection error')
                self.screen.get_wch.side_effect = (['\t', '\x15'] + list('127.0.0.1') +
                    ['\t', '\x15'] + list(str(port)) + ['\t']*8 + ['\n'])
                with patch('terminal_ui.save_preferences', side_effect=lambda prefs: save_preferences(prefs, path)):
                    self.app.command('/connection')
                deadline = time.monotonic()+3
                while time.monotonic() < deadline and not self.app.buffer('#recovery').joined:
                    self.app.process_events()
                    time.sleep(.01)
                self.assertTrue(self.app.buffer('#recovery').joined)
                self.assertTrue(self.app.running)
                self.assertEqual(load_preferences(path).profile.host, '127.0.0.1')
                self.app.command('/disconnect')
                self.app.client.thread.join(1)
                done.wait(1)
                self.assertIn('JOIN #recovery', received)
                self.assertFalse(errors)
        finally:
            if self.app.client:
                self.app.client.close()
            listener.close()
