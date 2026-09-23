"""Authentication and services regressions for v0.1.1."""
import json
import queue
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from irdisc import IRCClient
from irdisc_settings import Profile, Preferences, load_preferences, save_preferences, validate_profile
from terminal_ui import ChatApp, masked_service_input


class ServicesAuthTests(unittest.TestCase):
    def setUp(self):
        screen = MagicMock()
        screen.getmaxyx.return_value = (25, 110)
        with patch('terminal_ui.load_preferences', return_value=Preferences(Profile(nick='Max'))):
            self.app = ChatApp(screen)
        self.app.client = MagicMock(nick='Max', connected=True, sasl_password='')
        self.app.ready = True
        self.app.last_send = -1000

    def test_contextual_services_and_unsolicited_notices(self):
        app = self.app
        app.receive(':NickServ!s@h NOTICE Max :This nickname is registered and protected')
        self.assertIn('registered', str(app.buffer('server').messages))
        app.receive(':Max!u@h JOIN :#irdisc')
        for service, command in [('ChanServ', 'INFO #irdisc'), ('NickServ', 'STATUS Max')]:
            app.last_send = -1000
            app.command(f'/msg {service} {command}')
            self.assertNotIn(service.lower(), app.buffers)
            self.assertIn(command, str(app.buffer('#irdisc').messages))
            app.receive(f':{service}!s@h NOTICE Max :reply from {service}')
            self.assertIn(f'reply from {service}', str(app.buffer('#irdisc').messages))
        app.service_context['nickserv'] = ('#irdisc', -1)
        app.receive(':NickServ!s@h NOTICE Max :later unsolicited')
        self.assertIn('later unsolicited', str(app.buffer('server').messages))
        self.assertNotIn('later unsolicited', str(app.buffer('#irdisc').messages))

    def test_closed_origin_falls_back_and_query_is_explicit(self):
        app = self.app
        app.receive(':Max!u@h JOIN :#irdisc')
        app.command('/msg ChanServ INFO #irdisc')
        app.switch('server')
        del app.buffers['#irdisc']
        app.receive(':ChanServ!s@h NOTICE Max :still visible')
        self.assertIn('still visible', str(app.buffer('server').messages))
        app.command('/query ChanServ')
        app.last_send = -1000
        app.command('/msg ChanServ HELP')
        app.receive(':ChanServ!s@h PRIVMSG Max :private reply')
        app.receive(':ChanServ!s@h NOTICE Max :private notice')
        self.assertIn('private reply', str(app.buffer('ChanServ').messages))
        self.assertIn('private notice', str(app.buffer('ChanServ').messages))

    def test_regular_message_and_notice_routing(self):
        app = self.app
        app.command('/msg Alice hi')
        self.assertIn('hi', str(app.buffer('Alice').messages))
        app.receive(':Alice!u@h PRIVMSG Max :hello')
        app.receive(':Alice!u@h NOTICE Max :notice')
        self.assertIn('hello', str(app.buffer('Alice').messages))
        self.assertIn('notice', str(app.buffer('server').messages))

    def test_fresh_profile_none_and_legacy_sasl_migration(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'config.json'
            self.assertEqual(load_preferences(path).profile.auth_method, 'none')
            fresh = Preferences(Profile(nick='Max'))
            save_preferences(fresh, path)
            self.assertEqual(load_preferences(path).profile.auth_method, 'none')
            path.write_text(json.dumps({'profile': {'nick': 'Max', 'sasl_account': 'Old'},
                                        'profiles': {'OFTC': {'nick': 'Max', 'sasl_account': 'Old'}}}))
            loaded = load_preferences(path)
            self.assertEqual(loaded.profile.auth_method, 'sasl')
            self.assertEqual(loaded.profiles['OFTC']['auth_method'], 'sasl')
        values = {'name': '', 'host': '', 'port': '', 'nick': 'Max', 'channel': '', 'auth_method': 'none'}
        self.app.screen.get_wch.side_effect = ['\n']
        self.app.choose_network(values)
        self.assertEqual(values['auth_method'], 'none')

    def test_partial_service_masking(self):
        samples = [
            ('/msg NickServ IDENTIFY my-password', '/msg NickServ IDENTIFY ***********'),
            ('/msg ChanServ SET PASSWORD old new', '/msg ChanServ SET PASSWORD *** ***'),
            ('/msg NickServ GHOST Max private', '/msg NickServ GHOST *** *******'),
            ('/msg NickServ LOGIN Max private', '/msg NickServ LOGIN *** *******'),
            ('/msg  NickServ IDENTIFY my-password', '/msg  NickServ IDENTIFY ***********'),
        ]
        for raw, visible in samples:
            self.assertEqual(masked_service_input(raw, '#irdisc'), visible)
            self.assertNotIn('private', visible)
        self.assertEqual(masked_service_input('IDENTIFY my-password', 'nickserv'), 'IDENTIFY ***********')
        self.assertEqual(masked_service_input('/msg ChanServ INFO #irdisc', '#irdisc'),
                         '/msg ChanServ INFO #irdisc')
        self.app.input_text = '/msg NickServ IDENTIFY my-password'
        self.app.cursor = len(self.app.input_text)
        self.app.draw()
        drawn = str(self.app.screen.addnstr.call_args_list)
        self.assertIn('/msg NickServ IDENTIFY ***********', drawn)
        self.assertNotIn('my-password', drawn)

    def test_service_echo_names_actual_destination_without_extra_send(self):
        app = self.app
        app.receive(':Max!u@h JOIN :#irdisc')
        app.client.send.reset_mock()
        for service, command in [('ChanServ', 'INFO #irdisc'), ('NickServ', 'STATUS X86Max')]:
            app.last_send = -1000
            app.command(f'/msg {service} {command}')
            app.client.send.assert_called_once_with(f'PRIVMSG {service} :{command}')
            app.client.send.reset_mock()
            self.assertIn(f'/msg {service} {command}', app.buffer('#irdisc').messages[-1][1])
            self.assertNotIn(f'<Max> {command}', str(app.buffer('#irdisc').messages))
            self.assertNotIn(service.lower(), app.buffers)
        app.last_send = -1000
        app.input_text = '/msg NickServ IDENTIFY hidden-password'
        with patch('terminal_ui.append_log') as log:
            app.prefs.logging = True
            app.submit()
        app.client.send.assert_called_once_with('PRIVMSG NickServ :IDENTIFY hidden-password')
        self.assertIn('/msg NickServ IDENTIFY ***************', app.buffer('#irdisc').messages[-1][1])
        self.assertNotIn('hidden-password', str(app.buffers))
        self.assertNotIn('hidden-password', str(app.history))
        self.assertNotIn('hidden-password', str(log.call_args_list))
        app.last_send = -1000
        app.input_text = '/msg ChanServ SET PASSWORD old-secret new-secret'
        with patch('terminal_ui.append_log') as log:
            app.submit()
            app.receive(':ChanServ!s@h NOTICE Max :old-secret and new-secret')
        self.assertNotIn('old-secret', str(app.buffers) + str(app.history) + str(log.call_args_list))
        self.assertNotIn('new-secret', str(app.buffers) + str(app.history) + str(log.call_args_list))
        app.last_send = -1000
        app.client.send.reset_mock()
        app.command('/msg Alice hello')
        app.client.send.assert_called_once_with('PRIVMSG Alice :hello')
        self.assertIn('<Max> hello', app.buffer('Alice').messages[-1][1])

    def test_secrets_omitted_from_history_buffers_and_logs(self):
        app = self.app
        app.receive(':Max!u@h JOIN :#irdisc')
        app.prefs.logging = True
        with tempfile.TemporaryDirectory() as root, patch('terminal_ui.append_log') as log:
            app.input_text = '/msg NickServ IDENTIFY very-private'
            app.submit()
            app.receive(':NickServ!s@h NOTICE Max :very-private accepted')
            app.command('/settings')
            self.assertNotIn('very-private', str(app.buffers))
            self.assertNotIn('very-private', str(app.history))
            self.assertNotIn('very-private', str(log.call_args_list))
            self.assertIn('IDENTIFY very-private', str(app.client.send.call_args_list))
            app.switch('NickServ')
            app.last_send = -1000
            app.input_text = 'IDENTIFY another-secret'
            app.submit()
            self.assertNotIn('another-secret', str(app.buffers))
            self.assertNotIn('another-secret', str(app.history))
            self.assertNotIn('another-secret', str(log.call_args_list))

    def test_auth_validation_and_legacy_profile(self):
        sasl = Profile(nick='Max', auth_method='sasl')
        self.assertIn('sasl_account', validate_profile(sasl, 'secret', connecting=True))
        sasl.sasl_account = 'Max'
        self.assertIn('password', validate_profile(sasl, connecting=True))
        sasl.tls = False
        self.assertIn('tls', validate_profile(sasl, 'secret', connecting=True))
        nickserv = Profile(nick='Max', auth_method='nickserv')
        self.assertIn('password', validate_profile(nickserv, connecting=True))
        self.assertFalse(validate_profile(nickserv, 'secret', connecting=True))
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'config.json'
            path.write_text(json.dumps({'profile': {'nick': 'Max', 'sasl_account': 'Old'},
                                        'profiles': {'OFTC': {'nick': 'Max', 'sasl_account': 'Old', 'password': 'obsolete'}}}))
            prefs = load_preferences(path)
            self.assertEqual(prefs.profile.auth_method, 'sasl')
            self.assertEqual(prefs.profiles['OFTC']['auth_method'], 'sasl')
            save_preferences(prefs, path)
            self.assertNotIn('obsolete', path.read_text())
            self.assertNotIn('password', path.read_text())

    @patch('terminal_ui.curses.noecho')
    def test_connection_editor_cycles_methods_and_masks_secret(self, _):
        self.app.sasl_password = 'editor-private'
        self.app.screen.get_wch.side_effect = ['\t'] * 6 + [' ', ' ', '\x1b']
        self.app.edit_connection()
        drawn = str(self.app.screen.addnstr.call_args_list)
        self.assertIn('SASL PLAIN', drawn)
        self.assertIn('NickServ (after connecting)', drawn)
        self.assertNotIn('editor-private', drawn)

    def test_sasl_available_unavailable_rejected(self):
        for advert, numeric, expected in [(':multi-prefix', None, 'unavailable'),
                                           (':sasl=EXTERNAL', None, 'unavailable'),
                                           (':sasl=PLAIN', '904', 'failed')]:
            events = queue.Queue()
            client = IRCClient('example.org', 6697, 'Max', events, sasl_account='Max', sasl_password='secret')
            client.sock = MagicMock()
            client.connected = True
            client._handle(':srv CAP Max LS ' + advert)
            if numeric:
                client._handle(':srv CAP Max ACK :sasl')
                client._handle(f':srv {numeric} Max :secret should not be echoed')
            errors = []
            while not events.empty():
                event = events.get_nowait()
                if event.kind == 'auth_error':
                    errors.append(event.text)
            self.assertEqual(len(errors), 1)
            self.assertIn(expected, errors[0])
            self.assertNotIn('secret', errors[0])
            self.assertTrue(client.cap_ended)

    def test_nickserv_sends_after_welcome_before_autojoin(self):
        app = self.app
        app.ready = False
        app.channel = '#test'
        app.session_profile = Profile(nick='Max', channel='#test', auth_method='nickserv')
        app.client.sasl_password = 'private-password'
        app.receive(':srv NOTICE Max :before welcome')
        app.client.send.assert_not_called()
        app.receive(':srv 001 Max :welcome')
        self.assertEqual([call.args[0] for call in app.client.send.call_args_list],
                         ['PRIVMSG NickServ :IDENTIFY private-password', 'JOIN #test'])
        self.assertIn('identification sent', str(app.buffer('server').messages))
        self.assertNotIn('private-password', str(app.buffers))
        app.client.send.reset_mock()
        app.disconnect()
        self.assertFalse(app.service_context)


if __name__ == '__main__':
    unittest.main()
