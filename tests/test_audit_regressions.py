"""Deterministic first-pass regressions; synthetic credentials, no remote IRC."""
import curses
import json
import queue
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from irdisc import Event, IRCClient
from irdisc_settings import default_preferences, load_preferences, save_preferences, validate_profile
from terminal_ui import ChatApp


class AuditUITests(unittest.TestCase):
    def setUp(self):
        self.screen = MagicMock()
        self.screen.getmaxyx.return_value = (25, 110)
        with patch('terminal_ui.load_preferences', side_effect=default_preferences):
            self.app = ChatApp(self.screen)
        self.app.client = MagicMock(nick='Max', connected=True, sasl_password='')
        self.app.ready = True
        self.app.last_send = -1000
        self.app.receive(':Max!u@h JOIN :#test')
        self.app.client.send.reset_mock()

    def paste(self, content, suffix='\x1b[201~', confirm=None):
        keys = iter('[200~' + content + suffix)
        self.screen.get_wch.side_effect = lambda: next(keys)
        self.app.read_escape_sequence()
        for key in keys:
            self.app.key(key)
        if confirm is not None:
            self.app.key(confirm)

    def test_oversized_paste_cannot_send_or_execute_quit(self):
        self.paste('x' * 10005 + '\r/quit\r')
        self.assertTrue(self.app.running)
        self.app.client.send.assert_not_called()
        self.assertEqual(self.app.input_text, '')
        self.assertIn('cancelled', str(self.app.buffer('#test').messages))
        self.app.key('z')
        self.assertEqual(self.app.input_text, 'z')

    def test_paste_limit_excludes_closing_marker(self):
        with patch.object(self.app, 'review_paste') as review:
            self.paste('x' * 10000)
        review.assert_called_once_with('x' * 10000)
        self.app.client.send.assert_not_called()

    def test_multiline_paste_still_requires_confirmation(self):
        keys = iter('[200~first\r/quit\r\x1b[201~y')
        self.screen.get_wch.side_effect = lambda: next(keys)
        self.app.read_escape_sequence()
        self.assertEqual(self.app.input_text, 'first | /quit')
        self.assertTrue(self.app.running)
        self.app.client.send.assert_not_called()

    def test_paste_timeout_quarantines_delayed_commands(self):
        keys = iter('[200~partial')
        def read():
            part = next(keys, None)
            if part is None:
                raise curses.error()
            return part
        self.screen.get_wch.side_effect = read
        self.app.read_escape_sequence()
        for key in '\r/quit\r\x1b[201~':
            self.app.key(key)
        self.assertTrue(self.app.running)
        self.app.client.send.assert_not_called()
        self.assertEqual(self.app.input_text, '')
        self.app.key('z')
        self.assertEqual(self.app.input_text, 'z')

    def test_oversized_paste_keeps_bounded_storage(self):
        self.screen.get_wch.side_effect = iter('[200~' + 'x' * 1024)
        self.app.read_escape_sequence()
        for _ in range(100000):
            self.app.key('x')
        self.assertLessEqual(len(self.app.paste_buffer), 10006)
        for key in '\r/quit\r\x1b[201~':
            self.app.key(key)
        self.assertTrue(self.app.running)
        self.app.client.send.assert_not_called()

    def test_partial_or_malformed_start_marker_quarantines_input(self):
        for start in ('[200', '[200X'):
            with self.subTest(start=start):
                keys = iter(start)
                def read():
                    part = next(keys, None)
                    if part is None:
                        raise curses.error()
                    return part
                self.screen.get_wch.side_effect = read
                self.app.read_escape_sequence()
                for key in '\r/quit\r\x1b[201~':
                    self.app.key(key)
                self.assertTrue(self.app.running)
                self.app.client.send.assert_not_called()
                self.assertEqual(self.app.input_text, '')

    def test_single_line_and_escape_preserve_keyboard_behavior(self):
        self.paste('hello')
        self.assertEqual(self.app.input_text, 'hello')
        self.screen.get_wch.side_effect = curses.error()
        self.app.key('\x1b')
        self.app.key('!')
        self.assertEqual(self.app.input_text, 'hello!')
        self.app.client.send.assert_not_called()

    def test_legal_server_nick_uses_distinct_private_buffer(self):
        server = self.app.buffer('server')
        original = list(server.messages)
        self.app.switch('Mallory')
        self.app.add_message('message', '<Mallory> old conversation')
        self.app.input_text = 'unsent'
        self.app.receive(':Mallory!u@h NICK :server')
        self.assertIs(self.app.buffer('server'), server)
        self.assertEqual(server.messages, original)
        self.assertNotEqual(self.app.active, 'server')
        self.assertIn('old conversation', str(self.app.buffers[self.app.active].messages))
        self.assertEqual(self.app.input_text, 'unsent')
        self.app.receive(':server!u@h PRIVMSG Max :new private message')
        self.assertIn('new private message', str(self.app.buffers[self.app.active].messages))
        self.app.submit()
        self.app.client.send.assert_called_once_with('PRIVMSG server :unsent')
        self.app.receive(':server!u@h NICK :Renamed')
        self.assertEqual(self.app.active, 'renamed')
        self.assertIn('old conversation', str(self.app.buffer('Renamed').messages))

    def test_query_and_msg_to_server_nick_do_not_use_status_buffer(self):
        server = self.app.buffer('server')
        original = list(server.messages)
        self.app.command('/query server')
        self.assertNotEqual(self.app.active, 'server')
        self.app.command('/msg server hello')
        self.app.client.send.assert_called_once_with('PRIVMSG server :hello')
        self.assertEqual(server.messages, original)
        self.app.command('/close')
        self.assertEqual(self.app.active, 'server')
        self.assertIs(self.app.buffer('server'), server)

    def test_invalid_channel_or_internal_renames_preserve_state(self):
        channel = self.app.buffer('#test')
        channel.topic = 'topic'
        channel.users['alice'] = 'Alice'
        self.app.buffer('Mallory').messages.append(('message', 'history'))
        for destination in ('#test', '*search*'):
            self.app.rename_pm('Mallory', destination)
        self.app.rename_pm('#test', 'Someone')
        self.assertIs(self.app.buffer('#test'), channel)
        self.assertTrue(channel.joined)
        self.assertEqual(channel.topic, 'topic')
        self.assertIn('alice', channel.users)
        self.assertEqual(self.app.buffer('Mallory').messages, [('message', 'history')])

    def test_short_secrets_do_not_corrupt_chat_history_or_input(self):
        for secret in ('a', 'me', 'do', 'in'):
            with self.subTest(secret=secret):
                self.app.last_send = -1000
                self.app.input_text = '/msg NickServ IDENTIFY account ' + secret
                with patch('terminal_ui.append_log') as log:
                    self.app.prefs.logging = True
                    self.app.submit()
                    self.assertIn('/msg NickServ IDENTIFY ******* ' + '*' * len(secret),
                                  self.app.buffer('#test').messages[-1][1])
                    self.app.add_message('message', 'Hello world and banana; remind me to do it in chat')
                    self.assertTrue(self.app.buffer('#test').messages[-1][1].endswith(
                        'Hello world and banana; remind me to do it in chat'))
                    self.app.last_send = -1000
                    self.app.input_text = 'Hello world and banana; remind me to do it in chat'
                    self.app.cursor = len(self.app.input_text)
                    self.app.screen.addnstr.reset_mock()
                    self.app.draw()
                    self.assertIn(self.app.input_text, str(self.screen.addnstr.call_args_list))
                    self.app.submit()
                    self.assertIn('Hello world and banana; remind me to do it in chat', self.app.history)
                    self.assertNotIn('IDENTIFY account ' + secret, str(log.call_args_list))
                self.app.prefs.logging = False

    def test_service_echo_redacts_short_secret_without_masking_account(self):
        self.app.input_text = '/msg NickServ IDENTIFY account a'
        self.app.submit()
        self.app.receive(':NickServ!s@h NOTICE Max :account: a accepted; banana remains')
        shown = self.app.buffer('#test').messages[-1][1]
        self.assertIn('account: [redacted] accepted; banana remains', shown)

    def test_credentials_are_cleared_on_session_boundaries(self):
        self.app.send_message('NickServ', 'IDENTIFY old-secret')
        self.app.disconnect()
        self.app.receive(':NickServ!s@h NOTICE Max :old-secret is ordinary text now')
        self.assertIn('old-secret is ordinary text now', self.app.buffer('server').messages[-1][1])

    def test_service_cache_retains_old_credentials_until_reconnect(self):
        for number in range(40):
            self.app.last_send = -1000
            self.app.send_message('NickServ', f'IDENTIFY secret-{number}')
        self.app.receive(':NickServ!s@h NOTICE Max :secret-0 is still private')
        self.assertTrue(self.app.buffer('server').messages[-1][1].endswith('[redacted] is still private'))
        with patch('irdisc.IRCClient'):
            self.app.start_client()
        self.assertFalse(self.app.service_secrets)

    def test_disconnect_discards_queued_and_late_credential_echoes(self):
        self.app.send_message('NickServ', 'IDENTIFY private-secret')
        old_events = self.app.events
        old_events.put(Event('wire', ':NickServ!s@h NOTICE Max :private-secret accepted'))
        self.app.disconnect()
        old_events.put(Event('wire', ':NickServ!s@h NOTICE Max :late private-secret echo'))
        with patch('terminal_ui.append_log') as log:
            self.app.prefs.logging = True
            self.app.process_events()
        self.app.prefs.logging = False
        self.assertNotIn('private-secret', str(self.app.buffers) + str(log.call_args_list))

    def test_register_keeps_public_parameters_and_redacts_password(self):
        for target, body, reply in (
                ('NickServ', 'REGISTER private-secret user@example.org', 'user@example.org: private-secret'),
                ('ChanServ', 'REGISTER #test private-secret description', '#test: private-secret')):
            with self.subTest(target=target):
                self.app.last_send = -1000
                self.app.command(f'/msg {target} {body}')
                with patch('terminal_ui.append_log') as log:
                    self.app.prefs.logging = True
                    self.app.receive(f':{target}!s@h NOTICE Max :{reply}')
                self.app.prefs.logging = False
                self.assertNotIn('private-secret', str(log.call_args_list))
                public = reply.split(':')[0]
                self.assertIn(public + ': [redacted]', self.app.buffer('#test').messages[-1][1])

    def test_paste_review_masks_service_credentials(self):
        self.screen.get_wch.return_value = 'n'
        self.app.review_paste('/msg NickServ IDENTIFY private-secret\n/quit')
        self.assertNotIn('private-secret', str(self.screen.addnstr.call_args_list))
        self.assertIn('IDENTIFY **************', str(self.screen.addnstr.call_args_list))
        self.app.client.send.assert_not_called()

    def test_auth_password_common_word_leaves_ordinary_text_intact(self):
        self.app.sasl_password = 'in'
        self.app.client.sasl_password = 'in'
        self.app.receive(':Alice!u@h PRIVMSG #test :in banana in chat')
        self.assertTrue(self.app.buffer('#test').messages[-1][1].endswith('in banana in chat'))


class AuditSettingsTests(unittest.TestCase):
    def test_empty_profile_round_trip_keeps_all_preferences(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'config.json'
            prefs = default_preferences()
            prefs.theme, prefs.logging, prefs.notifications, prefs.auto_reconnect = 'mono', True, True, True
            prefs.profiles['saved'] = {'host': 'irc.example.org', 'port': 6697,
                                       'sasl_account': 'Account', 'password': 'obsolete'}
            save_preferences(prefs, path)
            loaded = load_preferences(path)
            self.assertEqual(loaded.theme, 'mono')
            self.assertTrue(loaded.logging and loaded.notifications and loaded.auto_reconnect)
            self.assertEqual(loaded.profile, prefs.profile)
            self.assertIn('saved', loaded.profiles)
            self.assertNotIn('obsolete', path.read_text())
            self.assertEqual(validate_profile(loaded.profile).keys(), validate_profile(prefs.profile).keys())

    def test_legacy_empty_port_and_host_preserve_settings_and_sasl_migration(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'config.json'
            path.write_text(json.dumps({'profile': {'host': '', 'port': ''}, 'theme': 'light',
                                        'profiles': {'old': {'sasl_account': 'Account'}}}))
            prefs = load_preferences(path)
            self.assertEqual(prefs.theme, 'light')
            self.assertEqual(prefs.profile.host, '')
            self.assertEqual(prefs.profile.port, '')
            self.assertEqual(prefs.profiles['old']['auth_method'], 'sasl')

    def test_service_test_never_reaches_default_log_directory(self):
        from tests.test_services_auth import ServicesAuthTests
        case = ServicesAuthTests('test_service_echo_names_actual_destination_without_extra_send')
        result = unittest.TestResult()
        with patch('irdisc_settings.state_dir', side_effect=AssertionError('Unisolated log access')):
            case.run(result)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.failures, [])


class AuditSocketTests(unittest.TestCase):
    def client(self):
        return IRCClient('localhost', 6667, 'Max', queue.Queue(), tls=False)

    def run_thread(self, function):
        errors = []
        def run():
            try:
                function()
            except BaseException as exc:
                errors.append(exc)
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread, errors

    def test_finalization_between_send_validation_and_write(self):
        client = self.client()
        paused, resume = threading.Event(), threading.Event()
        sock = MagicMock()
        sock.recv.return_value = b''
        class Gate:
            def __enter__(self):
                paused.set()
                if not resume.wait(2):
                    raise AssertionError('send gate timed out')
            def __exit__(self, *args):
                pass
        client.send_lock = Gate()
        client.sock, client.connected = sock, True
        sender, errors = self.run_thread(lambda: client.send('PING :test'))
        try:
            self.assertTrue(paused.wait(2))
            with patch('irdisc.socket.create_connection', return_value=sock), patch.object(client, 'send'):
                client._run()
        finally:
            resume.set()
            sender.join(2)
        self.assertFalse(sender.is_alive())
        self.assertEqual(errors, [])
        sock.sendall.assert_not_called()

    def test_close_interrupts_blocked_send_without_waiting_for_send_lock(self):
        client = self.client()
        entered, released = threading.Event(), threading.Event()
        sock = MagicMock()
        def blocked_send(data):
            entered.set()
            if not released.wait(2):
                raise AssertionError('close did not interrupt send')
            raise OSError('closed')
        sock.sendall.side_effect = blocked_send
        sock.shutdown.side_effect = lambda *args: released.set()
        client.sock, client.connected = sock, True
        sender, errors = self.run_thread(lambda: client.send('PING :test'))
        try:
            self.assertTrue(entered.wait(2))
            client.close()
        finally:
            released.set()
            sender.join(2)
        self.assertFalse(sender.is_alive())
        self.assertEqual(errors, [])
        self.assertFalse(client.connected)
        self.assertFalse(client.send('PING :late'))
        sock.shutdown.assert_called_once()

    def test_network_finalization_interrupts_an_inflight_send(self):
        client = self.client()
        entered, released = threading.Event(), threading.Event()
        sock = MagicMock()
        sock.recv.return_value = b''
        sock.shutdown.side_effect = lambda *args: released.set()
        def blocked_send(data):
            entered.set()
            if not released.wait(2):
                raise AssertionError('finalization did not interrupt send')
            raise OSError('closed')
        sock.sendall.side_effect = blocked_send
        client.sock, client.connected = sock, True
        sender, errors = self.run_thread(lambda: client.send('PING :test'))
        try:
            self.assertTrue(entered.wait(2))
            with patch('irdisc.socket.create_connection', return_value=sock), patch.object(client, 'send'):
                client._run()
            sender.join(2)
            self.assertFalse(sender.is_alive())
            self.assertEqual(errors, [])
        finally:
            released.set()
            sender.join(2)

    def test_close_during_tls_handshake_does_not_publish_socket(self):
        client = self.client()
        client.tls = True
        raw, tls = MagicMock(), MagicMock()
        context = MagicMock()
        def wrap(*args, **kwargs):
            client.close()
            return tls
        context.wrap_socket.side_effect = wrap
        with patch('irdisc.socket.create_connection', return_value=raw), patch('irdisc.ssl.create_default_context', return_value=context):
            client._run()
        self.assertIsNone(client.sock)
        self.assertFalse(client.connected)
        tls.close.assert_called_once()
        tls.sendall.assert_not_called()

    def test_close_validates_quit_and_is_idempotent(self):
        for message in ('bye', 'bad\r\nPRIVMSG #test :injected'):
            with self.subTest(message=message):
                client = self.client()
                sock = MagicMock()
                client.sock, client.connected = sock, True
                client.close(message)
                client.close(message)
                self.assertFalse(client.connected)
                self.assertIsNone(client.sock)
                sock.shutdown.assert_called_once()
                if '\r' in message:
                    sock.sendall.assert_not_called()
                else:
                    sock.sendall.assert_called_once_with(b'QUIT :bye\r\n')

    def test_reader_uses_owned_socket_when_close_detaches_shared_socket(self):
        client = self.client()
        sock = MagicMock()
        def read(size):
            client.close()
            return b''
        sock.recv.side_effect = read
        with patch('irdisc.socket.create_connection', return_value=sock):
            client._run()
        sock.close.assert_called_once()
        self.assertIsNone(client.sock)
        self.assertFalse(client.connected)

    def test_real_socket_close_wakes_reader_and_allows_fresh_session(self):
        for _ in range(2):
            with self.subTest(session=_):
                client = self.client()
                owned, peer = socket.socketpair()
                peer.settimeout(2)
                try:
                    with patch('irdisc.socket.create_connection', return_value=owned):
                        client.connect()
                        received = b''
                        while b'USER Max 0 * :Max\r\n' not in received:
                            received += peer.recv(4096)
                        client.close('local test')
                        client.thread.join(2)
                    self.assertFalse(client.thread.is_alive())
                    self.assertFalse(client.connected)
                    self.assertIsNone(client.sock)
                    self.assertEqual(owned.fileno(), -1)
                finally:
                    client.close()
                    peer.close()
                    owned.close()
