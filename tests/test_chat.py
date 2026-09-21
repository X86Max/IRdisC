import curses
import queue
import unittest
from unittest.mock import MagicMock, patch
from irdisc import IRCClient, Event
from terminal_ui import ChatApp, clean

class ChatTests(unittest.TestCase):
    def setUp(self):
        self.screen = MagicMock()
        self.screen.getmaxyx.return_value = (25, 110)
        self.app = ChatApp(self.screen)
        self.app.client = MagicMock(nick='Max', connected=True)
        self.app.ready = True

    def join(self):
        self.app.receive(':Max!u@h JOIN :#test')

    def test_join_confirmation(self):
        self.app.command('/join #test')
        self.assertEqual(self.app.active, 'server')
        self.join()
        self.assertTrue(self.app.buffer('#test').joined)

    def test_routing(self):
        self.join()
        self.app.receive(':Alice!u@h PRIVMSG #elsewhere :hello Max')
        self.app.receive(':Bob!u@h PRIVMSG Max :private')
        self.assertEqual(self.app.buffer('#test').unread, 0)
        self.assertEqual(self.app.buffer('#elsewhere').unread, 1)
        self.assertTrue(self.app.buffer('#elsewhere').mentioned)
        self.assertIn('private', self.app.buffer('Bob').messages[-1][1])

    def test_membership(self):
        self.join()
        self.app.receive(':srv 353 Max = #test :@Max +Alice Bob')
        self.app.receive(':srv 366 Max #test :end')
        self.assertEqual(len(self.app.buffer('#test').users), 3)
        self.app.receive(':Alice!u@h NICK :Alice2')
        self.assertEqual(self.app.buffer('#test').users['alice2'], '+Alice2')
        self.app.receive(':Bob!u@h PART #test :bye')
        self.assertNotIn('bob', self.app.buffer('#test').users)
        self.app.receive(':Op!u@h KICK #test Max :bye')
        self.assertFalse(self.app.buffer('#test').joined)

    def test_drafts_editing_completion(self):
        self.join()
        self.app.input_text = 'draft'
        self.app.switch('Bob')
        self.app.switch('#test')
        self.assertEqual(self.app.input_text, 'draft')
        self.app.key(curses.KEY_HOME)
        self.app.key('a')
        self.assertEqual(self.app.input_text, 'adraft')
        self.app.input_text, self.app.cursor = '/qu', 3
        self.app.key('\t')
        self.assertEqual(self.app.input_text, '/query ')

    def test_failed_send(self):
        self.join()
        self.app.client.send.return_value = False
        self.app.input_text = 'keep me'
        self.app.submit()
        self.assertEqual(self.app.input_text, 'keep me')
        self.assertEqual(self.app.buffer('#test').messages[-1][0], 'error')

    def test_disconnect(self):
        self.join()
        self.app.events.put(Event('status', 'Disconnected'))
        self.app.process_events()
        self.assertFalse(self.app.ready)
        self.assertFalse(self.app.buffer('#test').joined)

    @patch.object(ChatApp, 'start_client')
    @patch('terminal_ui.time.monotonic')
    def test_optional_reconnect_countdown(self, monotonic, start_client):
        self.app.prefs.auto_reconnect = True
        monotonic.side_effect = [100, 100]
        self.app.events.put(Event('status', 'Disconnected'))
        self.app.process_events()
        self.assertEqual(self.app.reconnect_due, 105)
        start_client.assert_not_called()
        monotonic.side_effect = None
        monotonic.return_value = 106
        self.app.process_events()
        start_client.assert_called_once()

    def test_topic_ctcp(self):
        self.join()
        self.app.receive(':srv 332 Max #test :a topic')
        self.assertEqual(self.app.buffer('#test').topic, 'a topic')
        before = len(self.app.buffer('#test').messages)
        self.app.receive(':Bob!u@h PRIVMSG #test :\x01VERSION\x01')
        self.assertEqual(len(self.app.buffer('#test').messages), before)
        self.app.receive(':Bob!u@h PRIVMSG #test :\x01ACTION waves\x01')
        self.assertIn('* Bob waves', self.app.buffer('#test').messages[-1][1])
        self.assertNotIn('\x1b', clean('\x1b[31mred'))

    def test_drawing(self):
        self.join()
        for i in range(50):
            self.app.add_message('message', str(i) + ' long message ' * 20)
        self.app.key(curses.KEY_PPAGE)
        for dimensions in ((25, 110), (15, 60), (3, 10)):
            self.screen.getmaxyx.return_value = dimensions
            self.app.draw()

    def test_transport(self):
        client = IRCClient('localhost', 6697, 'Max', queue.Queue())
        client.sock = MagicMock()
        client.connected = True
        self.assertFalse(client.send('PRIVMSG #a :hello\r\nQUIT'))
        self.assertFalse(client.send('x'*511))
        client.sock.sendall.assert_not_called()
        client._handle('PING :token')
        client.sock.sendall.assert_called_once_with(b'PONG :token\r\n')

    @patch('irdisc.curses.noecho')
    @patch('irdisc.curses.echo')
    @patch('irdisc.IRCClient')
    def test_confirmation(self, client, *_):
        self.screen.get_wch.side_effect = ['\x1b']
        self.app.setup()
        client.assert_not_called()
        self.assertTrue(self.app.running)

    def test_ignore_search_close_and_settings(self):
        self.join()
        self.app.command('/ignore Alice')
        before = len(self.app.buffer('#test').messages)
        self.app.receive(':Alice!u@h PRIVMSG #test :hidden')
        self.assertEqual(len(self.app.buffer('#test').messages), before)
        self.app.command('/unignore Alice')
        self.app.receive(':Alice!u@h PRIVMSG #test :find-me')
        self.app.command('/search find-me')
        self.assertEqual(self.app.active, '*search*')
        self.assertIn('find-me', self.app.buffer('*search*').messages[-1][1])
        self.app.command('/close')
        self.assertEqual(self.app.active, 'server')

    @patch('terminal_ui.save_preferences')
    @patch('terminal_ui.curses.beep')
    def test_user_filter_and_optional_mention_bell(self, beep, _save):
        self.join()
        self.app.receive(':srv 353 Max = #test :Max Alice Bob')
        self.app.command('/users Ali')
        self.assertEqual(self.app.user_filter, 'Ali')
        self.app.command('/notify on')
        self.app.switch('server')
        self.app.receive(':Alice!u@h PRIVMSG #test :hello Max')
        beep.assert_called_once()

    def test_multiline_paste_requires_confirmation_and_never_sends(self):
        self.join()
        self.app.client.send.reset_mock()
        self.screen.get_wch.return_value = 'y'
        self.app.review_paste('one\ntwo')
        self.assertEqual(self.app.input_text, 'one | two')
        self.app.client.send.assert_not_called()
        self.app.input_text = ''
        self.app.cursor = 0
        self.screen.get_wch.return_value = 'n'
        self.app.review_paste('three\nfour')
        self.assertEqual(self.app.input_text, '')
        self.app.client.send.assert_not_called()
