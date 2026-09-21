import io
import unittest
from unittest.mock import MagicMock, patch

from release_ui import TerminalTitle
from terminal_ui import ChatApp
from irdisc_settings import default_preferences


class TTY(io.StringIO):
    def isatty(self):
        return True


class TerminalTitleTests(unittest.TestCase):
    def test_titles_deduplicate_and_restore(self):
        stream = TTY()
        with TerminalTitle(stream, 'xterm-256color') as title:
            title.update('OFTC')
            title.update('OFTC')
            title.update()
        self.assertEqual(stream.getvalue(), '\x1b[22;2t\x1b]2;⇹ IRdisC\x1b\\'
                         '\x1b]2;⇹ IRdisC — OFTC\x1b\\'
                         '\x1b]2;⇹ IRdisC\x1b\\\x1b[23;2t')

    def test_unknown_console_and_redirected_output_untouched(self):
        for stream, term in [(TTY(), 'linux'), (TTY(), 'dumb'), (TTY(), ''),
                             (TTY(), 'unknown'), (io.StringIO(), 'xterm')]:
            with TerminalTitle(stream, term) as title:
                title.update('OFTC')
            self.assertEqual(stream.getvalue(), '')

    def test_write_failure_nonfatal(self):
        for error in (OSError('closed'), ValueError('closed'), UnicodeError('encoding')):
            stream = MagicMock()
            stream.write.side_effect = error
            with TerminalTitle(stream, 'xterm') as title:
                title.update('OFTC')
            self.assertFalse(title.enabled)

    def test_restores_after_exception(self):
        stream = TTY()
        with self.assertRaises(KeyboardInterrupt):
            with TerminalTitle(stream, 'xterm'):
                raise KeyboardInterrupt
        self.assertTrue(stream.getvalue().endswith('\x1b[23;2t'))

    def test_untrusted_network_label(self):
        stream = TTY()
        with TerminalTitle(stream, 'xterm') as title:
            title.update('OFTC\x1b]2;evil\x07\n\x9c\u202e'+'a'*100)
        data = stream.getvalue()
        self.assertNotIn('\x07', data)
        self.assertNotIn('\x9c', data)
        self.assertNotIn('\u202e', data)
        self.assertEqual(data.count('\x1b]2;'), 2)

    def test_active_profile_not_unsaved_or_future_profile(self):
        title = MagicMock()
        with patch('terminal_ui.load_preferences', side_effect=default_preferences):
            app = ChatApp(MagicMock(), title=title)
        app.profile.name = 'Next network'
        app.session_profile.name = 'OFTC'
        app.ready = True
        app.process_events()
        title.update.assert_called_with('OFTC')
        app.ready = False
        app.process_events()
        title.update.assert_called_with('')
