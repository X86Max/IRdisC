import copy
import curses
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from irdisc_settings import default_preferences, load_preferences
from release_ui import help_shortcut, COMMANDS
from terminal_ui import ChatApp


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.screen = MagicMock()
        self.screen.getmaxyx.return_value = (25, 110)
        with patch('terminal_ui.load_preferences', side_effect=default_preferences):
            self.app = ChatApp(self.screen)

    def test_clean_first_use(self):
        with tempfile.TemporaryDirectory() as directory:
            p = load_preferences(Path(directory)/'missing').profile
        for key in ('name', 'host', 'port', 'nick', 'channel', 'sasl_account'):
            self.assertEqual(getattr(p, key), '')
        self.assertIsNone(self.app.client)

    def test_presets_preserve_nick_channel_and_custom_clears_server(self):
        values = dict(nick='Alice', channel='#example')
        self.screen.get_wch.side_effect = [curses.KEY_DOWN, '\n']
        self.app.choose_network(values)
        self.assertEqual(values['host'], 'irc.libera.chat')
        self.assertEqual(values['nick'], 'Alice')
        self.assertEqual(values['channel'], '#example')
        self.screen.get_wch.side_effect = [curses.KEY_DOWN, curses.KEY_DOWN, '\n']
        self.app.choose_network(values)
        self.assertEqual(values['host'], '')
        self.assertEqual(values['port'], '')

    @patch('terminal_ui.curses.noecho')
    @patch('terminal_ui.save_preferences')
    def test_onboarding_save_and_connect(self, save, _):
        # Network dropdown -> OFTC -> nick; leave optional channel blank.
        self.screen.get_wch.side_effect = ['\n', '\n'] + ['\t']*4 + list('Alice') + ['\t']*6 + ['\n']
        with patch.object(self.app, 'request_connect') as connect:
            self.app.edit_connection()
        self.assertEqual(self.app.profile.nick, 'Alice')
        self.assertEqual(self.app.profile.channel, '')
        self.assertEqual(self.app.profile.host, 'irc.oftc.net')
        save.assert_called_once()
        connect.assert_called_once_with(replace=True)

    @patch('terminal_ui.curses.noecho')
    @patch('terminal_ui.save_preferences')
    def test_dropdown_then_escape_does_not_save(self, save, _):
        before = copy.deepcopy(self.app.prefs)
        self.screen.get_wch.side_effect = ['\n', '\n', '\x1b']
        self.app.edit_connection()
        self.assertEqual(before, self.app.prefs)
        save.assert_not_called()

    def test_help_shortcut_detection_and_fallback(self):
        with patch('release_ui.curses.tigetstr', return_value=b'\x1bOP'):
            self.assertEqual(help_shortcut(), (curses.KEY_F1, 'F1'))
        with patch('release_ui.curses.tigetstr', return_value=None):
            self.assertEqual(help_shortcut(), ('\x07', 'Ctrl+G'))
        with patch.object(self.app, 'show_commands') as show:
            self.app.key('\x07')
            self.app.command('/help')
            self.assertEqual(show.call_count, 2)

    def test_help_scroll_resize_and_close(self):
        self.screen.get_wch.side_effect = [curses.KEY_NPAGE, curses.KEY_DOWN, curses.KEY_RESIZE, '\x1b']
        self.app.show_commands()
        self.assertGreater(self.screen.refresh.call_count, 3)
        self.assertEqual(set(COMMANDS), {'Connection', 'Channels', 'Messaging', 'Users', 'Interface', 'Notifications'})

    def test_mouse_network(self):
        self.screen.get_wch.side_effect = [curses.KEY_MOUSE]
        values = {}
        with patch('release_ui.curses.getmouse', return_value=(0, 3, 3, 0, curses.BUTTON1_CLICKED)):
            self.app.choose_network(values)
        self.assertEqual(values['name'], 'Libera.Chat')

    def test_maximize_tip_dismissal(self):
        self.app.ready = True
        self.app.key(curses.KEY_RESIZE)
        self.assertTrue(self.app.size_tip_dismissed)
