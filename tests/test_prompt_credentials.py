"""B1: prompt/preview classification must agree with submission's whitespace handling."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from irdisc_settings import append_log, default_preferences
from terminal_ui import ChatApp, clean, masked_service_input


SECRET = 'b1-synthetic-secret'
LEADING = (' ', '\t', '\u00a0', ' \t\u00a0 ', '\v\f ')
SEPARATORS = (' ', '\t', '\u00a0', ' \t ', '\f')


class PromptCredentialTests(unittest.TestCase):
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

    def prepare(self, text, active='#test'):
        self.app.switch(active)
        self.app.input_text = text
        self.app.cursor = len(text)
        self.app.history_draft = text
        self.app.buffer(active).draft = text

    def assert_draw_masked(self):
        self.screen.addnstr.reset_mock()
        self.app.draw()
        shown = str(self.screen.addnstr.call_args_list)
        self.assertNotIn(SECRET, shown)
        prompt = next(c.args[2] for c in self.screen.addnstr.call_args_list if c.args[0] == 24)
        self.assertIn('IDENTIFY', prompt)
        self.assertIn('*' * len(SECRET), prompt)

    def assert_protected_after_submit(self, root):
        fields = [self.app.status, self.app.input_text, self.app.history_draft,
                  str(self.app.history), str(self.screen.addnstr.call_args_list)]
        for buf in self.app.buffers.values():
            fields.extend((buf.draft, buf.topic, str(buf.messages)))
        fields.extend(p.read_text() for p in Path(root).glob('*.log'))
        self.assertNotIn(SECRET, '\n'.join(fields))
        self.assertEqual(self.app.history, [])
        self.assertTrue(self.app.running)

    def submit_with_logs(self, *, expected=None):
        with tempfile.TemporaryDirectory() as root:
            with patch('terminal_ui.append_log', side_effect=lambda target, line: append_log(target, line, Path(root))):
                self.app.prefs.logging = True
                self.app.submit()
                self.app.draw()
            self.assert_protected_after_submit(root)
        if expected is None:
            self.app.client.send.assert_not_called()
        else:
            self.app.client.send.assert_called_once_with(expected)

    def test_indented_msg_is_masked_before_its_exact_single_send(self):
        for leading in LEADING:
            for separator in SEPARATORS:
                for target in ('NickServ', 'ChanServ'):
                    with self.subTest(leading=repr(leading), separator=repr(separator), target=target):
                        self.setUp()
                        command = separator.join(('/msg', target, 'IDENTIFY', SECRET))
                        self.prepare(leading + command)
                        self.assert_draw_masked()
                        self.submit_with_logs(expected=f'PRIVMSG {target} :IDENTIFY{separator}{SECRET}')

    def test_indented_me_is_masked_before_safe_action_rejection(self):
        for leading in LEADING:
            for separator in SEPARATORS:
                with self.subTest(leading=repr(leading), separator=repr(separator)):
                    self.setUp()
                    command = separator.join(('/me', 'IDENTIFY', SECRET))
                    self.prepare(leading + command, 'NickServ')
                    self.assert_draw_masked()
                    self.submit_with_logs()
                    self.assertIn('cannot be sent as actions', str(self.app.buffer('NickServ').messages))

    def test_indented_explicit_ctcp_actions_are_masked_and_rejected(self):
        for leading in LEADING:
            for separator in SEPARATORS:
                for explicit_msg in (False, True):
                    with self.subTest(leading=repr(leading), separator=repr(separator), explicit_msg=explicit_msg):
                        self.setUp()
                        body = '\x01ACTION IDENTIFY' + separator + SECRET + '\x01'
                        command = separator.join(('/msg', 'NickServ', body)) if explicit_msg else body
                        self.prepare(leading + command, 'NickServ')
                        self.assert_draw_masked()
                        self.submit_with_logs()

    def test_indented_multiline_preview_is_masked_without_execution(self):
        for leading in LEADING:
            for separator in SEPARATORS:
                with self.subTest(leading=repr(leading), separator=repr(separator)):
                    self.setUp()
                    self.app.switch('NickServ')
                    lines = [leading + separator.join(('/msg', 'NickServ', 'IDENTIFY', SECRET)),
                             leading + separator.join(('/me', 'IDENTIFY', SECRET)),
                             leading + '\x01ACTION IDENTIFY' + separator + SECRET + '\x01']
                    self.screen.get_wch.return_value = 'n'
                    self.app.review_paste('\n'.join(lines))
                    self.assertNotIn(SECRET, str(self.screen.addnstr.call_args_list))
                    self.assertIn('IDENTIFY', str(self.screen.addnstr.call_args_list))
                    self.app.client.send.assert_not_called()
                    self.assertEqual(self.app.input_text, '')
                    self.assertEqual(self.app.history, [])

    def test_indented_single_line_paste_draw_is_masked(self):
        for leading in LEADING:
            with self.subTest(leading=repr(leading)):
                self.setUp()
                command = leading + '/msg NickServ IDENTIFY ' + SECRET
                self.app.review_paste(command)
                self.assertEqual(self.app.input_text, command)
                self.assert_draw_masked()
                self.app.client.send.assert_not_called()
                self.submit_with_logs(expected='PRIVMSG NickServ :IDENTIFY ' + SECRET)

    def test_leading_whitespace_length_and_cursor_are_preserved(self):
        for leading in LEADING:
            with self.subTest(leading=repr(leading)):
                self.setUp()
                raw = leading + '/msg NickServ IDENTIFY ' + SECRET
                self.prepare(raw)
                masked = masked_service_input(raw, '#test')
                self.assertEqual(masked, leading + '/msg NickServ IDENTIFY ' + '*' * len(SECRET))
                self.assertEqual(len(masked), len(raw))
                self.assert_draw_masked()
                self.assertEqual(self.app.input_text, raw)
                self.assertEqual(self.app.cursor, len(raw))
                self.screen.move.assert_called_with(24, 2 + len(raw))
                prompt = next(c.args[2] for c in self.screen.addnstr.call_args_list if c.args[0] == 24)
                self.assertTrue(prompt.startswith('> ' + clean(leading)))

    def test_indented_ordinary_messages_and_actions_are_unchanged(self):
        for leading in LEADING:
            for raw, active, wire in (
                    ('a banana in a normal message', '#test', 'PRIVMSG #test :a banana in a normal message'),
                    ('/msg Peer IDENTIFY a', '#test', 'PRIVMSG Peer :IDENTIFY a'),
                    ('/me waves', '#test', 'PRIVMSG #test :\x01ACTION waves\x01'),
                    ('/me waves', 'Peer', 'PRIVMSG Peer :\x01ACTION waves\x01')):
                with self.subTest(leading=repr(leading), raw=raw, active=active):
                    self.setUp()
                    self.prepare(leading + raw, active)
                    self.assertEqual(masked_service_input(self.app.input_text, self.app.active), self.app.input_text)
                    self.app.draw()
                    self.assertIn(clean(raw), str(self.screen.addnstr.call_args_list))
                    self.app.submit()
                    self.app.client.send.assert_called_once_with(wire)
                    self.assertEqual(self.app.history, [raw])
