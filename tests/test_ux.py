import copy
import curses
import unittest
from unittest.mock import MagicMock, patch

from chat_ux import nick_color_index, mentions, copy_text, urls_in, describe_modes
from irdisc import Event, MAX_MESSAGES
from irdisc_settings import Preferences, Profile
from terminal_ui import ChatApp


class UXTests(unittest.TestCase):
    def setUp(self):
        self.screen = MagicMock()
        self.screen.getmaxyx.return_value = (25, 110)
        with patch('terminal_ui.load_preferences', return_value=Preferences(Profile(nick='Max'))):
            self.app = ChatApp(self.screen)
        self.app.client = MagicMock(nick='Max', connected=True)
        self.app.ready = True
        self.app.receive(':Max!u@h JOIN :#test')
        self.app.buffer('#test').users['lucas'] = 'Lucas'

    def ctx(self, target='#test', kind='conversation'):
        self.app.open_context(kind, target)
        return self.app.context

    def test_color_stability_case_and_mono(self):
        self.assertEqual(nick_color_index('Max', 6), nick_color_index('MAX', 6))
        self.app.nick_colors = [11, 12, 13, 14]
        self.assertEqual(self.app.nick_attr('@Lucas'), self.app.nick_attr('Lucas'))
        self.app.prefs.theme = 'mono'
        with patch('terminal_ui.curses.has_colors', return_value=True):
            self.app.configure_theme()
        self.assertFalse(self.app.nick_colors)
        self.assertEqual(self.app.nick_attr('Max'), curses.A_BOLD)

    def test_context_open_does_not_send_or_switch(self):
        self.app.buffer('#other').joined = True
        self.ctx('#other')
        self.assertEqual(self.app.active, '#test')
        self.app.client.send.assert_not_called()

    def test_leave_keeps_history_until_server_confirmation(self):
        buf = self.app.buffer('#test')
        original = list(buf.messages)
        ctx = self.ctx()
        self.assertNotIn('close', [a for _, a in ctx['items']])
        self.app.context_action('leave', ctx)
        self.app.client.send.assert_called_once_with('PART #test :Leaving')
        self.assertEqual(original, buf.messages)
        self.assertTrue(buf.joined)
        self.app.receive(':Max!u@h PART #test :bye')
        self.assertFalse(buf.joined)
        self.assertTrue(buf.messages)
        self.assertIn('rejoin', [a for _, a in self.ctx()['items']])

    def test_close_never_parts_and_preserves_other_draft(self):
        self.app.command('/close')
        self.app.client.send.assert_not_called()
        self.assertIn('#test', self.app.buffers)
        self.app.switch('Bob')
        self.app.input_text = 'unfinished'
        self.app.switch('#test')
        self.app.buffer('#old')
        self.app.close_conversation('#old')
        self.assertEqual(self.app.buffer('Bob').draft, 'unfinished')
        self.assertEqual(self.app.active, '#test')

    def test_clear_requires_confirmation_cancel_safe(self):
        original = list(self.app.buffer('#test').messages)
        self.app.command('/clear')
        self.assertEqual(original, self.app.buffer('#test').messages)
        self.app.key('\n')  # Cancel is selected by default.
        self.assertEqual(original, self.app.buffer('#test').messages)
        self.app.command('/clear')
        self.app.key(curses.KEY_DOWN)
        self.app.key('\n')
        self.assertFalse(self.app.buffer('#test').messages)

    @patch('chat_ux.copy_text', return_value=False)
    def test_copy_fallback_honest(self, copier):
        self.app.context_action('copy', self.ctx())
        copier.assert_called_once_with('#test')
        self.assertIn('Clipboard unavailable', self.app.buffer('#test').messages[-1][1])
        self.app.client.send.assert_not_called()

    @patch('chat_ux.shutil.which', return_value='/usr/bin/wl-copy')
    @patch.dict('os.environ', {'WAYLAND_DISPLAY': 'wayland-0'})
    @patch('chat_ux.subprocess.run')
    def test_clipboard_no_shell(self, run, _):
        self.assertTrue(copy_text('#test'))
        self.assertNotIn('shell', run.call_args.kwargs)
        self.assertEqual(run.call_args.kwargs['input'], b'#test')

    @patch('terminal_ui.curses.getmouse')
    def test_right_click_target_and_left_pm(self, mouse):
        self.app.draw()
        mouse.return_value = (0, 1, 3, 0, curses.BUTTON3_CLICKED)
        self.app.key(curses.KEY_MOUSE)
        self.assertEqual(self.app.context['target'], '#test')
        self.app.key('\x1b')
        mouse.return_value = (0, 100, 2, 0, curses.BUTTON1_CLICKED)
        self.app.key(curses.KEY_MOUSE)
        self.assertEqual(self.app.active, 'lucas')

    def test_menu_keyboard_resize_and_many_users(self):
        for i in range(80):
            self.app.buffer('#test').users[str(i)] = 'User'+str(i)
        self.app.key(curses.KEY_F4)
        for _ in range(60):
            self.app.key(curses.KEY_DOWN)
        for size in ((25, 110), (10, 50), (3, 8)):
            self.screen.getmaxyx.return_value = size
            self.app.draw()
        self.app.key('\n')
        self.assertEqual(self.app.context['kind'], 'user')
        self.app.key('\x1b')

    def test_mention_is_unsent_and_ignore_toggle(self):
        ctx = self.ctx('Lucas', 'user')
        self.app.context_action('mention', ctx)
        self.assertEqual(self.app.input_text, 'Lucas: ')
        self.app.client.send.assert_not_called()
        self.app.context_action('ignore', ctx)
        self.assertIn('lucas', self.app.ignored)
        self.app.context_action('ignore', ctx)
        self.assertNotIn('lucas', self.app.ignored)

    def test_unread_separator_and_no_server_activity(self):
        self.app.receive(':Bob!u@h JOIN :#other')
        self.assertEqual(self.app.buffer('#other').unread, 0)
        self.app.receive(':Bob!u@h PRIVMSG #other :hello Max')
        self.app.receive(':Bob!u@h PRIVMSG #other :again')
        buf = self.app.buffer('#other')
        self.assertEqual(buf.unread, 2)
        self.assertTrue(buf.mentioned)
        self.app.switch('#other')
        self.assertEqual(buf.unread, 0)
        self.assertFalse(buf.mentioned)
        self.app.draw()
        self.assertTrue(any('New messages' in str(c) for c in self.screen.addnstr.call_args_list))

    def test_scroll_anchor_and_counter(self):
        for i in range(40):
            self.app.add_message('message', '<Bob> line '+str(i))
        self.app.key(curses.KEY_PPAGE)
        self.app.draw()
        before = len(self.app.buffer('#test').messages)-self.app.buffer('#test').scroll
        self.app.receive(':Bob!u@h PRIVMSG #test :new')
        buf = self.app.buffer('#test')
        self.assertEqual(len(buf.messages)-buf.scroll, before)
        self.assertEqual(buf.new_while_scrolled, 1)
        self.app.key('\x0c')
        self.assertEqual(buf.new_while_scrolled, 0)

    def test_completion_and_input_history_draft(self):
        self.app.input_text, self.app.cursor = 'Luc', 3
        self.app.key('\t')
        self.assertEqual(self.app.input_text, 'Lucas: ')
        self.app.history = ['one', '/whois Bob']
        self.app.history_pos = 2
        self.app.input_text = 'draft'
        self.app.key(curses.KEY_UP)
        self.assertEqual(self.app.input_text, '/whois Bob')
        self.app.key(curses.KEY_UP)
        self.assertEqual(self.app.input_text, 'one')
        self.app.key(curses.KEY_DOWN)
        self.app.key(curses.KEY_DOWN)
        self.assertEqual(self.app.input_text, 'draft')

    def test_command_usage_even_offline(self):
        self.app.client.connected = False
        for cmd, message in [('/join', 'Usage: /join'), ('/join banana', 'Channel names'),
                             ('/msg', 'Usage: /msg'), ('/whois', 'Usage: /whois'),
                             ('/whatever', 'Unknown command')]:
            self.app.command(cmd)
            self.assertIn(message, self.app.buffer('#test').messages[-1][1])

    def test_nick_change_pm_keeps_history_draft_and_ignore(self):
        self.app.switch('Lucas')
        self.app.input_text = 'unsent'
        self.app.ignored.add('lucas')
        self.app.add_message('message', '<Lucas> old')
        self.app.receive(':Lucas!u@h NICK :Luke')
        self.assertEqual(self.app.active, 'luke')
        self.assertEqual(self.app.input_text, 'unsent')
        self.assertIn('old', str(self.app.buffer('Luke').messages))
        self.assertNotIn('lucas', self.app.buffers)
        self.assertIn('luke', self.app.ignored)
        self.assertIn('luke', self.app.buffer('#test').users)

    @patch('chat_ux.curses.beep')
    @patch('chat_ux.time.monotonic', return_value=100)
    def test_bell_rules_cooldown_and_mono(self, clock, beep):
        self.app.receive(':Bob!u@h PRIVMSG Max :hello')
        beep.assert_not_called()
        self.app.prefs.notifications = True
        self.app.prefs.theme = 'mono'
        for line in [':Bob!u@h JOIN :#test', ':srv NOTICE Max :Max',
                     ':Bob!u@h PRIVMSG #test :normal', ':Max!u@h PRIVMSG #test :Max']:
            self.app.receive(line)
        beep.assert_not_called()
        self.app.receive(':Bob!u@h PRIVMSG #test :Max: hello')
        self.app.receive(':Bob!u@h PRIVMSG Max :hello')
        self.assertEqual(beep.call_count, 1)
        clock.return_value = 106
        self.app.receive(':Bob!u@h PRIVMSG Max :hello')
        self.assertEqual(beep.call_count, 2)
        self.app.disconnect()
        clock.return_value = 112
        self.app.events.put(Event('status', 'Disconnected'))
        self.app.process_events()
        self.assertEqual(beep.call_count, 2)

    @patch('chat_ux.curses.beep')
    def test_unexpected_disconnect_bell(self, beep):
        self.app.prefs.notifications = True
        self.app.events.put(Event('status', 'Disconnected'))
        self.app.process_events()
        beep.assert_called_once()

    def test_mention_boundaries(self):
        self.assertTrue(mentions('Hello Max!', 'max'))
        self.assertFalse(mentions('Maximum or NotMax', 'Max'))

    def test_modes_topic_and_kick_legible(self):
        self.app.receive(':Op!u@h MODE #test +b *!*@bad')
        self.app.receive(':Op!u@h TOPIC #test :Welcome')
        self.app.receive(':Op!u@h KICK #test Max :reason')
        text = str(self.app.buffer('#test').messages)
        self.assertIn('changed channel modes', text)
        self.assertIn('Topic: Welcome', text)
        self.assertIn('was kicked from', text)
        self.assertEqual(describe_modes(['+b', '*!*@bad']), 'enabled ban (*!*@bad)')
        self.assertNotIn('secret', describe_modes(['+k', 'secret']))

    def test_capped_history_does_not_jump_while_scrolling(self):
        for i in range(MAX_MESSAGES+10):
            self.app.add_message('message', '<Bob> line '+str(i))
        self.app.key(curses.KEY_PPAGE)
        self.app.draw()
        buf = self.app.buffer('#test')
        visible_end = buf.messages[len(buf.messages)-buf.scroll-1]
        self.app.receive(':Bob!u@h PRIVMSG #test :next')
        self.assertEqual(buf.messages[len(buf.messages)-buf.scroll-1], visible_end)

    def test_nick_collision_preserves_both_drafts(self):
        self.app.switch('Lucas')
        self.app.input_text = 'draft one'
        self.app.switch('Luke')
        self.app.input_text = 'draft two'
        self.app.receive(':Lucas!u@h NICK :Luke')
        self.assertIn('draft one', self.app.input_text)
        self.assertIn('draft two', self.app.input_text)

    @patch('chat_ux.webbrowser.open')
    def test_links_safe_and_confirmed(self, browser):
        self.assertEqual(urls_in('file:///tmp/x javascript:alert(1) https://example.org/a.'), ['https://example.org/a'])
        self.app.buffer('#test').topic = 'https://example.org/'
        self.app.command('/links')
        self.app.key('\n')
        browser.assert_not_called()
        self.app.key('\n')  # Cancel, no browser side effects.
        browser.assert_not_called()


if __name__ == '__main__':
    unittest.main()
