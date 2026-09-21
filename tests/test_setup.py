import unittest
from unittest.mock import MagicMock, patch

from irdisc import App, Event


class SetupTests(unittest.TestCase):
    def setup_app(self, answers, confirmation):
        screen = MagicMock()
        screen.getstr.side_effect = answers
        screen.get_wch.return_value = confirmation
        return App(screen)

    @patch('irdisc.curses.noecho')
    @patch('irdisc.curses.echo')
    @patch('irdisc.IRCClient')
    def test_waits_and_connects_only_after_confirmation(self, client, *_):
        app = self.setup_app([b'Alice', b'#example'], 'y')
        def confirm():
            client.assert_not_called()
            return 'y'
        app.screen.get_wch.side_effect = confirm
        app.setup()
        app.screen.timeout.assert_called_once_with(-1)
        self.assertEqual(app.channel, '#example')
        self.assertEqual(app.nick, 'Alice')
        client.return_value.connect.assert_called_once()
        app.events.put(Event('welcome', 'Welcome'))
        app.process_events()
        client.return_value.send.assert_called_once_with('JOIN #example')

    @patch('irdisc.curses.noecho')
    @patch('irdisc.curses.echo')
    @patch('irdisc.IRCClient')
    def test_blank_nick_retries_and_cancel_never_connects(self, client, *_):
        app = self.setup_app([b'', b'bad nick', b'MaxTest', b'custom-test'], 'n')
        app.setup()
        self.assertEqual(app.nick, 'MaxTest')
        self.assertEqual(app.channel, '#custom-test')
        self.assertFalse(app.running)
        client.assert_not_called()
