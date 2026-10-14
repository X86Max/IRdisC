"""Round-two review regressions: synthetic input, credentials and local logs."""
import base64
import curses
import queue
import tempfile
import unittest
from collections import deque
from pathlib import Path
from unittest.mock import MagicMock, patch

from irdisc import Event, IRCClient
from irdisc_settings import append_log, default_preferences
from terminal_ui import ChatApp, masked_service_input


PAUSE = object()
START, END = '\x1b[200~', '\x1b[201~'
DANGEROUS = 'hello\r/quit\r/msg Peer injected\r'


class ReviewUITests(unittest.TestCase):
    def setUp(self):
        self.screen = MagicMock()
        self.screen.getmaxyx.return_value = (25, 110)
        with patch('terminal_ui.load_preferences', side_effect=default_preferences):
            self.app = ChatApp(self.screen)
        self.app.client = MagicMock(nick='Tester', connected=True, sasl_password='')
        self.app.ready = True
        self.app.last_send = -1000
        self.app.receive(':Tester!u@h JOIN :#test')
        self.app.client.send.reset_mock()
        self.stream = deque()
        self.screen.get_wch.side_effect = self.read

    def read(self):
        item = self.stream.popleft() if self.stream else PAUSE
        if item is PAUSE:
            raise curses.error()
        return item

    def feed(self):
        while self.stream:
            try:
                self.app.key(self.read())
            except curses.error:
                pass

    def assert_no_execution(self):
        self.assertTrue(self.app.running)
        self.app.client.send.assert_not_called()
        self.assertEqual(self.app.history, [])

    def outputs(self, root=None):
        fields = [self.app.status, self.app.input_text, self.app.history_draft,
                  str(self.app.history), str(self.screen.addnstr.call_args_list)]
        for buf in self.app.buffers.values():
            fields.extend((str(buf.messages), buf.topic, buf.draft))
        if root is not None:
            fields.extend(p.read_text() for p in Path(root).glob('*.log'))
        return '\n'.join(fields)

    def test_start_marker_interrupted_at_every_byte_boundary(self):
        for boundary in range(1, len(START) + 1):
            with self.subTest(boundary=boundary):
                self.setUp()
                self.stream.extend([*START[:boundary], PAUSE,
                                    *START[boundary:], *DANGEROUS, *END, 'n'])
                self.feed()
                self.assert_no_execution()
                self.assertEqual(self.app.input_text, '')

    def test_start_marker_can_pause_after_every_byte(self):
        for char in START:
            self.stream.extend((char, PAUSE))
        self.stream.extend([*DANGEROUS, *END, 'n'])
        self.feed()
        self.assert_no_execution()
        self.assertEqual(self.app.input_text, '')

    def test_resize_does_not_forget_a_fragmented_start(self):
        for event in (curses.KEY_RESIZE, curses.KEY_MOUSE):
            with self.subTest(event=event):
                self.setUp()
                self.stream.extend([*START[:3], event, *START[3:], *DANGEROUS, *END, 'n'])
                with patch('terminal_ui.curses.getmouse', side_effect=curses.error()):
                    self.feed()
                self.assert_no_execution()
                self.assertEqual(self.app.input_text, '')

    def test_help_cancellation_keeps_pending_paste_framing(self):
        self.stream.extend([*START, *DANGEROUS, *END])
        self.app.show_commands()
        self.feed()
        self.assert_no_execution()
        self.assertEqual(self.app.input_text, '')

    @patch('terminal_ui.curses.noecho')
    def test_editor_cancellation_keeps_pending_paste_framing(self, _):
        self.stream.extend([*START, *DANGEROUS, *END])
        with patch.object(self.app, 'apply_profile') as apply:
            self.app.edit_connection()
        self.feed()
        self.assert_no_execution()
        apply.assert_not_called()
        self.assertEqual(self.app.input_text, '')

    @patch('terminal_ui.curses.noecho')
    def test_small_editor_cancellation_keeps_pending_paste_framing(self, _):
        self.screen.getmaxyx.return_value = (8, 40)
        self.stream.extend([*START, *DANGEROUS, *END])
        self.app.edit_connection()
        self.screen.getmaxyx.return_value = (25, 110)
        self.feed()
        self.assert_no_execution()

    def test_selector_cancellation_keeps_pending_paste_framing(self):
        values = {'name': 'unchanged'}
        self.stream.extend([*START, *DANGEROUS, *END])
        self.app.choose_network(values)
        self.feed()
        self.assert_no_execution()
        self.assertEqual(values, {'name': 'unchanged'})
        self.assertEqual(self.app.input_text, '')

    def test_confirmation_cancellation_keeps_pending_paste_framing(self):
        self.stream.extend([*START, *DANGEROUS, *END])
        self.app.review_paste('unsent\npreview')
        self.feed()
        self.assert_no_execution()
        self.assertEqual(self.app.input_text, '')

    def test_inline_dialogs_keep_pending_paste_framing(self):
        for modal in ('context', 'topic', 'menu'):
            with self.subTest(modal=modal):
                self.setUp()
                if modal == 'context':
                    self.app.command('/clear')
                elif modal == 'topic':
                    self.app.open_topic()
                else:
                    self.app.menu = True
                self.stream.extend([*START, *DANGEROUS, *END])
                self.feed()
                self.assert_no_execution()
                self.assertEqual(self.app.input_text, '')

    def test_fragmented_start_survives_a_change_of_dialog(self):
        self.stream.extend([START[0], PAUSE])
        self.app.show_commands()
        self.feed()
        self.stream.extend([START[1], PAUSE, *START[2:], *DANGEROUS, *END])
        self.feed()
        self.assert_no_execution()
        self.assertEqual(self.app.input_text, '')

    def test_ordinary_escape_arrows_shortcuts_and_typed_text(self):
        self.stream.extend(['\x1b'])
        self.app.show_commands()
        self.stream.extend('hello [typed]')
        self.feed()
        self.assertEqual(self.app.input_text, 'hello [typed]')
        self.stream.extend('\x1b[D')
        self.stream.append('X')
        self.feed()
        self.assertEqual(self.app.input_text, 'hello [typedX]')
        self.stream.extend('\x1bOCZ')
        self.feed()
        self.assertEqual(self.app.input_text, 'hello [typedX]Z')
        self.app.key(curses.KEY_HOME)
        self.app.key('Y')
        self.assertEqual(self.app.input_text, 'Yhello [typedX]Z')
        self.app.key(curses.KEY_F2)
        self.assertTrue(self.app.menu)
        self.assert_no_execution()

    def test_legitimate_bracket_text_after_escape_is_preserved(self):
        self.stream.extend(['\x1b', *'[brackets]'])
        self.feed()
        self.assertEqual(self.app.input_text, '[brackets]')
        self.assert_no_execution()

    def test_multiline_review_still_inserts_only_an_unsent_draft(self):
        self.stream.extend([*START, *'one\r/quit\r', *END, 'y'])
        self.feed()
        self.assert_no_execution()
        self.assertEqual(self.app.input_text, 'one | /quit')

    def test_formatted_service_echo_is_normalized_before_redaction(self):
        secret = 'demo-secret'
        for origin in ('server', '#test', 'NickServ'):
            for control in ('\x02', '\x03' + '04', '\x1d', '\x1f', '\u200b'):
                with self.subTest(origin=origin, control=repr(control)):
                    self.setUp()
                    with tempfile.TemporaryDirectory() as root:
                        self.app.switch(origin)
                        with patch('terminal_ui.append_log', side_effect=lambda target, line: append_log(target, line, Path(root))):
                            self.app.prefs.logging = True
                            self.app.command('/msg NickServ IDENTIFY ' + secret)
                            self.app.receive(':NickServ!s@h NOTICE Tester :Your password: demo-' + control + 'secret')
                            self.app.draw()
                        self.assertNotIn(secret, self.outputs(root))
                        self.assertIn('[redacted]', self.outputs(root))

    def test_numeric_middle_parameters_and_trailing_are_protected(self):
        with tempfile.TemporaryDirectory() as root:
            with patch('terminal_ui.append_log', side_effect=lambda target, line: append_log(target, line, Path(root))):
                self.app.prefs.logging = True
                self.app.command('/msg NickServ IDENTIFY demo-secret')
                self.app.receive(':srv 400 Tester demo-secret :Invalid demo-\x02secret parameter')
                self.app.draw()
            self.assertNotIn('demo-secret', self.outputs(root))
            for name in ('server.log', 'test.log'):
                self.assertIn('400 [redacted]', (Path(root) / name).read_text())

    def test_service_action_and_server_error_echoes_are_protected(self):
        with tempfile.TemporaryDirectory() as root:
            with patch('terminal_ui.append_log', side_effect=lambda target, line: append_log(target, line, Path(root))):
                self.app.prefs.logging = True
                self.app.command('/msg NickServ IDENTIFY demo-secret')
                self.app.receive(':NickServ!s@h PRIVMSG Tester :\x01ACTION IDENTIFY demo-\x02secret\x01')
                self.app.receive(':srv ERROR :Bad demo-\x02secret')
                self.app.receive(':srv NOTICE Tester :Rejected demo-\x02secret')
                self.app.draw()
            self.assertNotIn('demo-secret', self.outputs(root))

    def test_ordinary_peer_text_is_not_censored_by_short_passwords(self):
        self.app.command('/msg NickServ IDENTIFY a')
        self.app.receive(':Peer!u@h PRIVMSG #test :a banana in a normal message')
        self.assertTrue(self.app.buffer('#test').messages[-1][1].endswith('a banana in a normal message'))

    def test_server_topic_and_auth_events_use_the_normalized_representation(self):
        self.app.sasl_password = 'demo-secret'
        with tempfile.TemporaryDirectory() as root:
            with patch('terminal_ui.append_log', side_effect=lambda target, line: append_log(target, line, Path(root))):
                self.app.prefs.logging = True
                self.app.receive(':srv 332 Tester #test :demo-\x02secret topic')
                self.app.events.put(Event('auth_error', 'Rejected demo-\x02secret'))
                self.app.process_events()
                self.app.draw()
            self.assertNotIn('demo-secret', self.outputs(root))
            self.assertIn('[redacted]', self.app.buffer('#test').topic)

    def test_sensitive_service_actions_are_masked_and_rejected(self):
        for command in ('/me IDENTIFY demo-secret', '/me\tIDENTIFY\tdemo-secret',
                        '/msg NickServ \x01ACTION IDENTIFY demo-secret\x01'):
            with self.subTest(command=repr(command)):
                self.setUp()
                self.app.switch('NickServ')
                self.app.input_text = command
                self.app.cursor = len(command)
                self.app.history_draft = command
                self.app.buffer('NickServ').draft = command
                self.app.draw()
                self.assertNotIn('demo-secret', str(self.screen.addnstr.call_args_list))
                with tempfile.TemporaryDirectory() as root:
                    with patch('terminal_ui.append_log', side_effect=lambda target, line: append_log(target, line, Path(root))):
                        self.app.prefs.logging = True
                        self.app.submit()
                        self.app.draw()
                    self.assertNotIn('demo-secret', self.outputs(root))
                self.assert_no_execution()

    def test_direct_sensitive_action_send_is_rejected_without_echo(self):
        self.assertFalse(self.app.send_message('NickServ', 'IDENTIFY demo-secret', action=True))
        self.assertNotIn('demo-secret', self.outputs())
        self.assert_no_execution()

    def test_normal_actions_in_channels_and_private_messages_are_preserved(self):
        for target in ('#test', 'Peer'):
            with self.subTest(target=target):
                self.setUp()
                self.app.switch(target)
                self.app.input_text = '/me waves'
                self.app.submit()
                self.app.client.send.assert_called_once_with(f'PRIVMSG {target} :\x01ACTION waves\x01')
                self.assertIn('/me waves', self.app.history)
                self.assertIn('* Tester waves', str(self.app.buffer(target).messages))

    def test_tab_separated_service_command_has_one_masked_execution(self):
        command = '/msg\tNickServ\tIDENTIFY\tdemo-secret'
        self.app.input_text = command
        self.app.cursor = len(command)
        self.app.draw()
        with tempfile.TemporaryDirectory() as root:
            with patch('terminal_ui.append_log', side_effect=lambda target, line: append_log(target, line, Path(root))):
                self.app.prefs.logging = True
                self.app.submit()
                self.app.draw()
            self.assertNotIn('demo-secret', self.outputs(root))
        self.app.client.send.assert_called_once_with('PRIVMSG NickServ :IDENTIFY\tdemo-secret')
        self.assertEqual(self.app.history, [])

    def test_masking_and_execution_agree_on_command_whitespace(self):
        for separator in (' ', '\t', ' \t ', '\u00a0'):
            with self.subTest(separator=repr(separator)):
                self.setUp()
                command = separator.join(('/msg', 'NickServ', 'IDENTIFY', 'demo-secret'))
                self.assertNotIn('demo-secret', masked_service_input(command, '#test'))
                self.app.input_text = command
                self.app.submit()
                self.app.client.send.assert_called_once_with('PRIVMSG NickServ :IDENTIFY' + separator + 'demo-secret')
                self.assertNotIn('demo-secret', self.outputs())

    def test_failed_service_actions_do_not_restore_sensitive_drafts(self):
        for connected in (True, False):
            with self.subTest(connected=connected):
                self.setUp()
                self.app.switch('NickServ')
                self.app.client.connected = connected
                self.app.client.send.return_value = False
                self.app.input_text = '/me IDENTIFY demo-secret'
                self.app.buffer('NickServ').draft = self.app.input_text
                self.app.history_draft = self.app.input_text
                self.app.submit()
                self.assertNotIn('demo-secret', self.outputs())
                self.assert_no_execution()

    def test_command_errors_do_not_reflect_untrusted_command_names(self):
        with tempfile.TemporaryDirectory() as root:
            with patch('terminal_ui.append_log', side_effect=lambda target, line: append_log(target, line, Path(root))):
                self.app.prefs.logging = True
                self.app.command('/unknown-demo-secret argument')
            self.assertNotIn('demo-secret', self.outputs(root))
        self.app.client.send.assert_not_called()

    def test_service_action_partial_mask_preserves_command_structure(self):
        self.assertEqual(masked_service_input('/me IDENTIFY demo-secret', 'nickserv'),
                         '/me IDENTIFY ***********')


class ReviewSaslTests(unittest.TestCase):
    def client(self):
        client = IRCClient('localhost', 6697, 'Tester', queue.Queue(),
                           sasl_account='Account', sasl_password='synthetic-secret')
        client.sock = MagicMock()
        client.connected = True
        return client

    def sent(self, client):
        return [call.args[0].decode().strip() for call in client.sock.sendall.call_args_list]

    def negotiate(self, client):
        client._handle(':srv CAP Tester LS :sasl=PLAIN')
        client._handle(':srv CAP Tester ACK :sasl')

    def test_both_challenge_forms_produce_the_same_plain_response(self):
        for challenge in ('AUTHENTICATE +', 'AUTHENTICATE :+'):
            with self.subTest(challenge=challenge):
                client = self.client()
                self.negotiate(client)
                client._handle(challenge)
                encoded = base64.b64encode(b'\0Account\0synthetic-secret').decode()
                self.assertIn('AUTHENTICATE ' + encoded, self.sent(client))
                client._handle(':srv 903 Tester :success')
                self.assertTrue(client.cap_ended)
                self.assertEqual(self.sent(client).count('CAP END'), 1)

    def test_authentication_failures_end_cap_once_and_never_autojoin(self):
        for numeric in ('902', '904', '905', '906', '907'):
            with self.subTest(numeric=numeric):
                client = self.client()
                self.negotiate(client)
                client._handle(f':srv {numeric} Tester synthetic-secret :failed')
                client._handle(':srv 001 Tester :welcome')
                with patch('terminal_ui.load_preferences', side_effect=default_preferences):
                    app = ChatApp(MagicMock())
                app.client, app.events = client, client.events
                app.channel = '#authenticated'
                app.process_events()
                self.assertTrue(client.cap_ended)
                self.assertTrue(app.auth_failed)
                self.assertEqual(app.status, 'Authentication error')
                self.assertEqual(self.sent(client).count('CAP END'), 1)
                self.assertFalse(any(line.startswith('JOIN ') for line in self.sent(client)))
                self.assertNotIn('synthetic-secret', str(app.buffers))

    def test_missing_or_rejected_capability_is_distinct_from_auth_failure(self):
        for response in (':srv CAP Tester LS :multi-prefix', ':srv CAP Tester NAK :sasl'):
            with self.subTest(response=response):
                client = self.client()
                client._handle(response)
                errors = [e.text for e in client.events.queue if e.kind == 'auth_error']
                self.assertEqual(len(errors), 1)
                self.assertIn('unavailable', errors[0])
                self.assertNotIn('failed.', errors[0])
                self.assertEqual(self.sent(client).count('CAP END'), 1)
        client = self.client()
        self.negotiate(client)
        client._handle(':srv 902 Tester :locked')
        self.assertIn('failed', ' '.join(e.text for e in client.events.queue if e.kind == 'auth_error'))

    def test_late_challenges_after_failure_do_not_send_credentials(self):
        client = self.client()
        self.negotiate(client)
        client._handle(':srv 902 Tester :locked')
        count = len(self.sent(client))
        client._handle('AUTHENTICATE +')
        client._handle('AUTHENTICATE :+')
        self.assertEqual(len(self.sent(client)), count)
