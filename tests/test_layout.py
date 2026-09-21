import curses
import unittest
from unittest.mock import MagicMock, patch

from irdisc_settings import Preferences, Profile
from terminal_ui import ChatApp
from text_layout import cells, clip, wrap_cells, message_rows


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.screen = MagicMock()
        self.screen.getmaxyx.return_value = (25, 110)
        with patch('terminal_ui.load_preferences', return_value=Preferences(Profile(nick='Max'))):
            self.app = ChatApp(self.screen)
        self.app.client = MagicMock(nick='Max', connected=True)
        self.app.ready = True
        self.app.receive(':Max!u@h JOIN :#test')
        self.buf = self.app.buffer('#test')
        self.buf.users = {f'user{i:03}': f'User{i:03}' for i in range(281)}

    def mouse(self, x, y, state):
        with patch('terminal_ui.curses.getmouse', return_value=(0, x, y, 0, state)):
            self.app.key(curses.KEY_MOUSE)

    def test_users_wheel_does_not_move_chat_and_clicks_after_scroll(self):
        self.app.draw()
        self.mouse(100, 4, curses.BUTTON5_PRESSED)
        self.app.draw()
        self.assertEqual(self.buf.scroll, 0)
        self.assertEqual(self.app.click_users[2], 'User003')
        self.mouse(100, 2, curses.BUTTON3_CLICKED)
        self.assertEqual(self.app.context['target'], 'User003')
        self.app.key('\x1b')
        self.mouse(100, 2, curses.BUTTON1_CLICKED)
        self.assertEqual(self.app.active, 'user003')

    def test_focus_keyboard_pages_and_last_user(self):
        self.app.key(curses.KEY_F7)
        for _ in range(30):
            self.app.key(curses.KEY_NPAGE)
        self.app.draw()
        self.assertIn('User280', self.app.click_users.values())
        self.assertEqual(self.buf.scroll, 0)
        bottom = self.buf.users_scroll
        self.app.key(curses.KEY_UP)
        self.assertEqual(self.buf.users_scroll, bottom-1)
        self.app.key('\x1b')
        self.assertEqual(self.app.focus, 'chat')

    def test_join_part_anchor_and_channel_switch(self):
        self.app.scroll_users(60)
        self.app.draw()
        before = self.app.click_users[2]
        self.app.receive(':AAAA!u@h JOIN :#test')
        self.app.draw()
        self.assertEqual(self.app.click_users[2], before)
        self.app.receive(':User001!u@h PART #test :bye')
        self.app.draw()
        self.assertEqual(self.app.click_users[2], before)
        self.app.switch('#other')
        self.app.switch('#test')
        self.app.draw()
        self.assertEqual(self.app.click_users[2], before)

    def test_users_header_focus_and_filter_reset(self):
        self.app.draw()
        self.mouse(100, 1, curses.BUTTON1_CLICKED)
        self.assertEqual(self.app.focus, 'users')
        self.app.key(curses.KEY_NPAGE)
        self.app.command('/users User28')
        self.app.draw()
        self.assertEqual(self.app.click_users[2], 'User280')
        self.assertEqual(self.buf.users_scroll, 0)

    def test_wrap_cells_unicode_and_long_url_no_loss(self):
        url = 'https://example.org/' + 'z'*300
        rows = wrap_cells(url, 31)
        self.assertEqual(''.join(line for line, _ in rows), url)
        for line, _ in wrap_cells('界🙂 e\u0301 '*70, 19):
            self.assertLessEqual(cells(line), 19)
        self.assertEqual(clip('界界', 3), '界')

    def test_continuation_aligns_with_body(self):
        prefix = '12:34  <Bob> '
        rows = message_rows(prefix + 'a message with words '*20, 70)
        self.assertTrue(all(line.startswith(' '*len(prefix)) for line, _ in rows[1:]))
        self.assertEqual(sum('12:34' in line for line, _ in rows), 1)
        self.assertTrue(all(cells(line) <= 70 for line, _ in rows))

    def test_chat_drawing_stays_inside_sidebar(self):
        self.app.receive(':Bob!u@h PRIVMSG #test :' + '界🙂 word '*60)
        for width in (90, 110, 140, 65):
            self.screen.getmaxyx.return_value = (25, width)
            self.screen.addnstr.reset_mock()
            self.app.draw()
            left = 20 if width >= 90 else 0
            edge = width-20 if width >= 90 else width-2
            for call in self.screen.addnstr.call_args_list:
                y, x, text = call.args[:3]
                if 2 <= y < 22 and left <= x < edge:
                    self.assertLessEqual(x+cells(text), edge)

    def test_visual_scroll_counts_hanging_wrap_and_arrival(self):
        for i in range(35):
            self.app.add_message('message', '<Bob> '+str(i)+' text '*30)
        self.app.key(curses.KEY_PPAGE)
        self.app.draw()
        anchor = self.buf.view_anchor
        self.app.receive(':Bob!u@h PRIVMSG #test :'+'new content '*100)
        self.app.draw()
        self.assertIs(self.buf.view_anchor[0], anchor[0])
        self.assertEqual(self.buf.view_anchor[1], anchor[1])
        self.assertEqual(self.buf.new_while_scrolled, 1)
        self.screen.getmaxyx.return_value = (25, 95)
        self.app.draw()
        self.assertIs(self.buf.view_anchor[0], anchor[0])
        self.assertLessEqual(self.buf.view_anchor[1], anchor[1])

    def test_topic_full_view_scroll_resize_close(self):
        self.buf.topic = 'Long topic '*300 + 'FINAL-TOPIC-TEXT'
        self.app.draw()
        self.mouse(25, 1, curses.BUTTON1_CLICKED)
        self.assertIsNotNone(self.app.topic_view)
        for _ in range(60):
            self.app.key(curses.KEY_NPAGE)
        self.screen.addnstr.reset_mock()
        self.app.draw()
        self.assertIn('FINAL-TOPIC-TEXT', str(self.screen.addnstr.call_args_list))
        self.assertEqual(self.buf.scroll, 0)
        self.screen.getmaxyx.return_value = (12, 55)
        self.app.draw()
        self.app.key('\x1b')
        self.assertIsNone(self.app.topic_view)
        self.app.key(curses.KEY_F8)
        self.assertIsNotNone(self.app.topic_view)


if __name__ == '__main__':
    unittest.main()
