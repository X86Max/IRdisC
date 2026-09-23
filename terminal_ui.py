"""Multi-buffer interface for IRdisC. No connections are made during import."""
import curses
import copy
import queue
import re
import sys
import textwrap
import time
from dataclasses import dataclass, field
from chat_ux import ChatUX, mentions, urls_in, describe_modes
from text_layout import cells, clip, wrap_cells, message_rows
from release_ui import ReleaseUI

from irdisc import App, MAX_MESSAGES, parse_irc_line
from irdisc_settings import Profile, append_log, load_preferences, save_preferences, validate_profile


def fold(value):
    return value.lower().translate(str.maketrans('[]\\^', '{}|~'))


def clean(value):
    value = re.sub(r'\x03(?:\d{1,2}(?:,\d{1,2})?)?', '', value)
    return ''.join(c for c in value if c.isprintable())


def valid_target(value):
    return bool(value) and not any(c.isspace() or c in ',:\x00\x07' for c in value)


def service_secret(target, message):
    """Manual service credentials must never enter history or visible buffers."""
    if fold(target) not in ('nickserv', 'chanserv'):
        return False
    return bool(service_credential_parts(message))


def service_credential_parts(message):
    """Keep only the recognized command verb; all arguments may be secrets."""
    return re.match(r'^(\s*(?:IDENTIFY|IDENT|LOGIN|AUTH|REGISTER|SET\s+PASSWORD|SET\s+PASS|RECOVER|GHOST|RELEASE)\b)(.*)$', message, re.I | re.S)


def redact_service_command(target, message):
    parts = service_credential_parts(message) if fold(target) in ('nickserv', 'chanserv') else None
    if not parts:
        return message
    return parts[1] + ''.join('*' if not c.isspace() else c for c in parts[2])


def service_input_parts(text, active):
    match = re.match(r'^(/msg\s+)(\S+)(\s+)(.*)$', text, re.I | re.S)
    if match:
        return match[1] + match[2] + match[3], match[2], match[4]
    return '', active, text


def masked_service_input(text, active):
    prefix, target, message = service_input_parts(text, active)
    # Preserve spacing and cursor position while concealing every argument.
    return prefix + redact_service_command(target, message)


@dataclass
class Buffer:
    name: str
    messages: list = field(default_factory=list)
    users: dict = field(default_factory=dict)
    joined: bool = False
    topic: str = ''
    draft: str = ''
    unread: int = 0
    mentioned: bool = False
    scroll: int = 0
    first_unread: int | None = None
    new_while_scrolled: int = 0
    users_scroll: int = 0
    users_anchor: str = ''
    wrap_width: int = 0
    view_anchor: tuple | None = None


class ChatApp(ReleaseUI, ChatUX, App):
    def __init__(self, screen, title=None):
        super().__init__(screen)
        self.terminal_title = title
        self.buffers = {'server': Buffer('server')}
        self.active = 'server'
        self.ready = False
        self.cursor = 0
        self.history = []
        self.history_pos = 0
        self.last_send = 0.0
        self.pending_names = set()
        self.menu = False
        self.click_buffers = {}
        self.click_users = {}
        self.prefs = load_preferences()
        self.profile = self.prefs.profile
        self.nick = self.profile.nick
        self.channel = self.profile.channel
        self.sasl_password = ''
        self.service_context = {}
        self.service_queries = set()
        self.session_secrets = []
        self.ignored = set()
        self.reconnect_due = 0.0
        self.reconnect_attempts = 0
        self.reconnect_cancelled = False
        self.colors = {'title': curses.A_REVERSE, 'error': curses.A_BOLD,
                       'server': curses.A_DIM, 'mention': curses.A_BOLD}
        self.user_filter = ''
        self.pending_connect = False
        self.auth_failed = False
        self.session_profile = copy.deepcopy(self.profile)
        self.context = None
        self.nick_colors = []
        self.last_bell = float('-inf')
        self.history_draft = ''
        self.click_links = []
        self.focus = 'chat'
        self.topic_view = None
        self.size_tip_dismissed = False

    def setup(self):
        self.status = 'Disconnected'
        self.edit_connection()

    def edit_connection(self):
        """One transactional editor, also usable while a connection is active."""
        p = self.profile
        fields = [('name', 'Network [Enter: select]'), ('host', 'Server'), ('port', 'Port'),
                  ('tls', 'TLS (Space toggles)'), ('nick', 'Nick'),
                  ('channel', 'Channel (optional)'), ('auth_method', 'Auth (Space: None / SASL PLAIN / NickServ)'),
                  ('sasl_account', 'SASL account'), ('password', 'Auth password (memory only)')]
        values = {key: str(getattr(p, key)) for key, _ in fields if key != 'password'}
        values['tls'] = 'yes' if p.tls else 'no'
        values['auth_method'] = p.auth_method
        values['password'] = self.sasl_password
        selected, cursor, errors = 0, len(values['name']), {}
        note = ''
        self.screen.timeout(100)
        curses.noecho()
        try:
            while self.running:
                self.process_events()
                h, w = self.screen.getmaxyx()
                self.screen.erase()
                if h < 10 or w < 50:
                    self.put(0, 0, 'Resize to 50 x 10 or press Esc to cancel.', w-1)
                    self.screen.refresh()
                    try:
                        if self.screen.get_wch() == '\x1b':
                            return
                    except curses.error:
                        pass
                    continue
                self.put(0, 1, '⇹ IRdisC v0.1.1 | ' + self.status, w-2, curses.A_BOLD)
                self.put(1, 1, 'IRC, discomplicated. | Tab: next | Esc: Cancel | F4: load saved', w-2)
                rows = max(1, (h-6)//2)
                start = max(0, min(selected, len(fields)-1)-rows+1)
                for index in range(start, min(len(fields), start+rows)):
                    key, label = fields[index]
                    row = 2 + (index-start)*2
                    value = ('*' * len(values[key]) if key == 'password' else
                             {'none': 'None', 'sasl': 'SASL PLAIN', 'nickserv': 'NickServ (after connecting)'}.get(values[key], values[key])
                             if key == 'auth_method' else values[key])
                    # Keep the end of long values visible on narrow terminals.
                    placeholders = {'name': 'Choose network or type a name', 'host': 'irc.example.org', 'port': '6697', 'nick': 'Your nickname', 'channel': 'Optional: #channel', 'sasl_account': 'Required for SASL PLAIN', 'password': 'Required for selected auth'}
                    text = label + ': ' + (value or '<'+placeholders.get(key, '')+'>')
                    caret = len(label)+2+cursor
                    offset = max(0, (caret if selected == index else len(text))-max(1,w-4))
                    self.put(row, 1, text[offset:], w-2,
                             curses.A_REVERSE if selected == index else 0)
                    self.put(row+1, 1, errors.get(key, ''), w-2, curses.A_BOLD)
                actions = ['Save', 'Save & Connect', 'Cancel']
                for index, label in enumerate(actions, len(fields)):
                    self.put(h-3, 1+(index-len(fields))*19, '['+label+']', 18,
                             curses.A_REVERSE if selected == index else 0)
                self.put(h-2, 1, note or 'Save does not change the active connection. Passwords are never saved.', w-2)
                self.put(h-1, 0, self.commands_label()+' | Ctrl+G: help | Ctrl+U: clear field', w-1)
                if selected < len(fields):
                    caret = len(fields[selected][1])+2+cursor
                    offset = max(0, caret-max(1,w-4))
                    try:
                        self.screen.move(2+(selected-start)*2, min(w-2, 1+caret-offset))
                    except curses.error:
                        pass
                self.screen.refresh()
                try:
                    key = self.screen.get_wch()
                except curses.error:
                    continue
                if key == '\x1b':
                    return
                if self.commands_key(key):
                    self.show_commands()
                    continue
                if key == curses.KEY_MOUSE:
                    try:
                        _, x, y, _, state = curses.getmouse()
                    except curses.error:
                        continue
                    if not state & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED):
                        continue
                    if y == h-1:
                        self.show_commands()
                        continue
                    if y == h-3:
                        selected = len(fields)+min(2, max(0, (x-1)//19))
                        key = '\n'
                    elif 2 <= y < 2+rows*2 and start+(y-2)//2 < len(fields):
                        selected = start+(y-2)//2
                        cursor = len(values[fields[selected][0]])
                        if selected == 0:
                            key = '\n'
                        elif fields[selected][0] in ('tls', 'auth_method'):
                            key = ' '
                        else:
                            continue
                    else:
                        continue
                if key == curses.KEY_F4:
                    saved = self.prefs.profiles.get(values['name'])
                    if saved:
                        try:
                            loaded = Profile(**saved)
                            values.update({field: str(getattr(loaded, field)) for field, _ in fields if field != 'password'})
                            values['tls'] = 'yes' if loaded.tls else 'no'
                            values['auth_method'] = loaded.auth_method
                            values['password'] = ''
                            selected, cursor, errors = 1, len(values['host']), {}
                            note = 'Loaded into editor only. Save or Cancel.'
                        except TypeError:
                            note = 'Could not load this profile. You can edit its fields manually.'
                    else:
                        note = 'No saved profile with this Network name.'
                    continue
                if key in ('\t', curses.KEY_DOWN, curses.KEY_BTAB, curses.KEY_UP):
                    step = -1 if key in (curses.KEY_BTAB, curses.KEY_UP) else 1
                    selected = (selected+step) % (len(fields)+3)
                    if selected < len(fields):
                        cursor = len(values[fields[selected][0]])
                    continue
                if key in ('\n', '\r', curses.KEY_ENTER):
                    if selected == 0:
                        self.choose_network(values)
                        cursor = len(values['name'])
                        continue
                    if selected < len(fields):
                        selected += 1
                        if selected < len(fields):
                            cursor = len(values[fields[selected][0]])
                        continue
                    if selected == len(fields)+2:
                        return
                    candidate = Profile(values['name'].strip(), values['host'].strip(),
                                        values['port'], values['tls'] == 'yes',
                                        values['nick'].strip(), values['channel'].strip(),
                                        values['sasl_account'].strip(), values['auth_method'])
                    connect = selected == len(fields)+1
                    errors = validate_profile(candidate, values['password'], connecting=connect)
                    if errors:
                        selected = next(i for i, (key, _) in enumerate(fields) if key in errors)
                        cursor = len(values[fields[selected][0]])
                        continue
                    candidate.port = int(candidate.port)
                    try:
                        self.apply_profile(candidate, values['password'], connect)
                    except OSError:
                        note = 'Could not save settings. Check config directory permissions; nothing changed.'
                        continue
                    return
                if selected >= len(fields):
                    continue
                field_name = fields[selected][0]
                value = values[field_name]
                if field_name == 'tls':
                    if key in (' ', 'y', 'Y', 'n', 'N'):
                        values[field_name] = ('no' if value == 'yes' else 'yes') if key == ' ' else ('yes' if key.lower() == 'y' else 'no')
                elif field_name == 'auth_method':
                    if key == ' ':
                        choices = ('none', 'sasl', 'nickserv')
                        values[field_name] = choices[(choices.index(value)+1) % len(choices)]
                elif key == '\x15':
                    values[field_name], cursor = '', 0
                elif key in ('\x7f', '\b', curses.KEY_BACKSPACE) and cursor:
                    values[field_name] = value[:cursor-1] + value[cursor:]
                    cursor -= 1
                elif key == curses.KEY_DC:
                    values[field_name] = value[:cursor] + value[cursor+1:]
                elif key == curses.KEY_LEFT:
                    cursor = max(0, cursor-1)
                elif key == curses.KEY_RIGHT:
                    cursor = min(len(value), cursor+1)
                elif key == curses.KEY_HOME:
                    cursor = 0
                elif key == curses.KEY_END:
                    cursor = len(value)
                elif isinstance(key, str) and key.isprintable() and len(value) < 253:
                    values[field_name] = value[:cursor]+key+value[cursor:]
                    cursor += 1
        finally:
            self.screen.timeout(100)

    def apply_profile(self, profile, password, connect=False):
        errors = validate_profile(profile, password, connecting=connect)
        if errors:
            raise ValueError('; '.join(errors.values()))
        prefs = copy.deepcopy(self.prefs)
        prefs.profile = profile
        save_preferences(prefs)  # Commit only after persistence succeeds.
        self.prefs, self.profile = prefs, profile
        self.sasl_password = password if profile.auth_method != 'none' else ''
        self.add_message('server', 'Connection settings saved. Use /connect or /reconnect.', 'server')
        if connect:
            self.request_connect(replace=True)

    def request_connect(self, replace=False):
        errors = validate_profile(self.profile, self.sasl_password, connecting=True)
        if errors:
            self.status = 'Connection error'
            self.add_message('error', '; '.join(errors.values()) + ' Use /connection or F2 → Connection settings.', 'server')
            self.switch('server')
            return
        if self.client and (self.client.connected or (self.client.thread and self.client.thread.is_alive())):
            if not replace:
                self.add_message('server', 'Already connected or connecting. Use /reconnect to replace this session.', 'server')
                return
            self.disconnect()
            self.pending_connect = True
            self.status = 'Disconnecting before reconnect'
            return
        self.start_client()

    def disconnect(self):
        self.pending_connect = False
        self.reconnect_cancelled = True
        self.reconnect_due = 0
        self.ready = False
        self.service_context.clear()
        self.service_queries.clear()
        self.status = 'Disconnected'
        for buf in self.buffers.values():
            buf.joined = False
            buf.users.clear()
        if self.client:
            self.client.close('Disconnect requested')

    def start_client(self):
        self.reconnect_due = 0
        self.reconnect_cancelled = False
        self.auth_failed = False
        self.service_context.clear()
        self.service_queries.clear()
        self.ready = False
        self.pending_connect = False
        # Each session gets its own queue: late events cannot alter its replacement.
        self.events = queue.Queue()
        self.session_profile = copy.deepcopy(self.profile)
        self.nick, self.channel = self.profile.nick, self.profile.channel
        self.client = __import__('irdisc').IRCClient(
            self.profile.host, self.profile.port, self.profile.nick, self.events,
            tls=self.profile.tls, username=self.profile.nick,
            sasl_account=self.profile.sasl_account, sasl_password=self.sasl_password,
            auth_method=self.profile.auth_method)
        self.status = 'Connecting'
        self.client.connect()
        self.add_message('server', f'Connecting to {self.profile.host}:{self.profile.port}…', 'server')

    def buffer(self, name):
        key = fold(name)
        if key not in self.buffers:
            self.buffers[key] = Buffer(name)
        return self.buffers[key]

    def switch(self, name):
        self.focus = 'chat'
        self.history_pos = len(self.history)
        self.buffers[self.active].draft = self.input_text
        buf = self.buffer(name)
        self.active = fold(name)
        self.input_text = buf.draft
        self.cursor = len(self.input_text)
        buf.unread = 0
        buf.mentioned = False

    def add_message(self, kind, text, target=None):
        if not hasattr(self, 'buffers'):
            return super().add_message(kind, text)
        secrets = [self.sasl_password, getattr(self.client, 'sasl_password', '')] + self.session_secrets
        for secret in secrets:
            if isinstance(secret, str) and secret:
                text = text.replace(secret, '[redacted]')
        buf = self.buffer(target or self.active)
        if kind == 'message' and fold(buf.name) != self.active and not buf.unread:
            buf.first_unread = len(buf.messages)
        buf.messages.append((kind, time.strftime('%H:%M') + '  ' + clean(text)))
        if len(buf.messages) > MAX_MESSAGES:
            del buf.messages[:-MAX_MESSAGES]
            if buf.first_unread is not None:
                buf.first_unread = max(0, buf.first_unread-1)
        if kind == 'message' and fold(buf.name) != self.active:
            buf.unread += 1
            if self.client and mentions(text, self.client.nick):
                buf.mentioned = True
        if buf.scroll:
            buf.scroll += len(message_rows(buf.messages[-1][1], self.chat_width()))
            if kind == 'message':
                buf.new_while_scrolled += 1
        if self.prefs.logging:
            try:
                append_log(buf.name, buf.messages[-1][1])
            except OSError:
                self.prefs.logging = False
                buf.messages.append(('error', time.strftime('%H:%M') + '  Logging disabled after a write error.'))

    def chat_width(self):
        _, width = self.screen.getmaxyx()
        return max(10, width - (40 if width >= 90 else 2))

    def user_rows(self):
        buf = self.buffers[self.active]
        users = [n for n in sorted(buf.users.values(), key=fold)
                 if not self.user_filter or fold(self.user_filter) in fold(n)]
        names = [fold(n.lstrip('~&@%+')) for n in users]
        if buf.users_anchor in names:
            buf.users_scroll = names.index(buf.users_anchor)
        count = max(1, self.screen.getmaxyx()[0]-6)
        buf.users_scroll = max(0, min(buf.users_scroll, max(0, len(users)-count)))
        buf.users_anchor = names[buf.users_scroll] if names else ''
        return users, count

    def scroll_users(self, amount):
        users, count = self.user_rows()
        buf = self.buffers[self.active]
        buf.users_scroll = max(0, min(buf.users_scroll+amount, max(0, len(users)-count)))
        buf.users_anchor = fold(users[buf.users_scroll].lstrip('~&@%+')) if users else ''

    def open_topic(self):
        buf = self.buffers[self.active]
        self.topic_view = {'name': buf.name, 'text': buf.topic or '(No topic)', 'scroll': 0}

    def topic_key(self, key):
        view = self.topic_view
        if key in ('\x1b', '\n', '\r', curses.KEY_F8):
            self.topic_view = None
            return
        h, w = self.screen.getmaxyx()
        page = max(1, h-4)
        amount = {curses.KEY_UP: -1, curses.KEY_DOWN: 1,
                  curses.KEY_PPAGE: -page, curses.KEY_NPAGE: page}.get(key, 0)
        if key == curses.KEY_MOUSE:
            try:
                _, _, _, _, state = curses.getmouse()
                amount = -3 if state & curses.BUTTON4_PRESSED else 3 if state & getattr(curses, 'BUTTON5_PRESSED', 0) else 0
            except curses.error:
                pass
        rows = wrap_cells(view['text'], max(1, w-4))
        view['scroll'] = max(0, min(view['scroll']+amount, max(0, len(rows)-page)))

    def draw_topic(self):
        view = self.topic_view
        h, w = self.screen.getmaxyx()
        self.screen.erase()
        self.put(0, 1, 'Topic — '+view['name'], w-2, curses.A_BOLD)
        rows = wrap_cells(view['text'], max(1, w-4))
        page = max(1, h-4)
        view['scroll'] = min(view['scroll'], max(0, len(rows)-page))
        for row, (line, _) in enumerate(rows[view['scroll']:view['scroll']+page], 2):
            self.put(row, 2, line, w-4)
        self.put(h-1, 0, f'Topic {view["scroll"]+1}/{len(rows)} | ↑↓ PgUp/PgDn Wheel | Esc closes', w-1, curses.A_REVERSE)

    def process_events(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if event.kind == 'wire':
                self.receive(event.text)
            elif event.kind == 'status':
                if self.status not in ('Connection error', 'Authentication error'):
                    self.status = event.text
                if event.text == 'Disconnected':
                    if self.ready and not self.reconnect_cancelled:
                        self.bell()
                    self.ready = False
                    for buf in self.buffers.values():
                        buf.joined = False
                        buf.users.clear()
                    if self.prefs.auto_reconnect and self.running and not self.reconnect_cancelled and self.status not in ('Connection error', 'Authentication error'):
                        delay = min(60, 5 * (2 ** self.reconnect_attempts))
                        self.reconnect_attempts += 1
                        self.reconnect_due = time.monotonic() + delay
                        self.status = f'Disconnected | reconnect in {delay}s (/reconnect cancel)'
                self.add_message('server', event.text, 'server')
            elif event.kind == 'auth':
                self.add_message('server', event.text, 'server')
            elif event.kind == 'auth_error':
                self.auth_failed = True
                self.status = 'Authentication error'
                self.reconnect_cancelled = True
                self.add_message('error', event.text + ' Connected without authentication; autojoin paused.', 'server')
            elif event.kind == 'connection_error':
                if self.ready and not self.reconnect_cancelled:
                    self.bell()
                self.status = 'Connection error'
                self.reconnect_cancelled = True
                self.add_message('error', event.text + ' Open /connection or F2 → Connection settings, then Save & Connect.', 'server')
                self.switch('server')
            else:
                self.add_message(event.kind, event.text)
        if self.pending_connect and (not self.client.thread or not self.client.thread.is_alive()):
            self.start_client()
        if self.reconnect_due and time.monotonic() >= self.reconnect_due:
            self.start_client()
        if self.terminal_title:
            self.terminal_title.update(self.session_profile.name if self.ready else '')

    def receive(self, line):
        # Ignore IRCv3 tags when present; no capabilities are requested yet.
        if line.startswith('@'):
            line = line.partition(' ')[2]
        command, params, trailing = parse_irc_line(line)
        nick = line[1:].split(' ', 1)[0].split('!', 1)[0] if line.startswith(':') else ''
        own = self.client.nick if self.client else self.nick
        if command == '001':
            self.ready = True
            self.reconnect_attempts = 0
            self.reconnect_due = 0
            if params:
                self.client.nick = params[0]
            self.status = 'Authentication error' if self.auth_failed else f'Connected as {self.client.nick} | {"TLS" if self.session_profile.tls else "NO TLS"}'
            self.add_message('server', trailing, 'server')
            if self.session_profile.auth_method == 'nickserv':
                # Registration is complete. Send before autojoin; no success is inferred.
                if self.client.send(f'PRIVMSG NickServ :IDENTIFY {self.client.sasl_password}'):
                    self.add_message('server', 'NickServ identification sent.', 'server')
                else:
                    self.auth_failed = True
                    self.status = 'Authentication error'
                    self.add_message('error', 'NickServ identification could not be sent; autojoin paused.', 'server')
            if self.channel and not self.auth_failed:
                self.client.send(f'JOIN {self.channel}')
        elif command in ('PRIVMSG', 'NOTICE') and params:
            target = params[0] if params[0].startswith(('#', '&')) else nick
            if command == 'NOTICE':
                target = 'server'
            service = fold(nick)
            if service in ('nickserv', 'chanserv') and command in ('NOTICE', 'PRIVMSG'):
                context = self.service_context.get(service)
                if context:
                    origin, expires = context
                    if time.monotonic() <= expires and origin in self.buffers:
                        target = origin
                    else:
                        self.service_context.pop(service, None)
                elif service in self.service_queries and service in self.buffers:
                    target = service
            if fold(nick) in self.ignored:
                return
            if trailing.startswith('\x01'):
                if trailing.startswith('\x01ACTION ') and trailing.endswith('\x01'):
                    text = f'* {nick} {trailing[8:-1]}'
                else:
                    return  # Do not render or execute CTCP control requests.
            else:
                text = f'<{nick}> {trailing}'
            incoming = command == 'PRIVMSG' and fold(nick) != fold(own)
            self.add_message('message' if incoming else 'server', text, target)
            if incoming and (not params[0].startswith(('#', '&')) or mentions(trailing, own)):
                self.bell()
        elif command == 'JOIN':
            channel = trailing or (params[0] if params else '')
            if not channel:
                return
            buf = self.buffer(channel)
            buf.users[fold(nick)] = nick
            if fold(nick) == fold(own):
                buf.joined = True
                self.switch(channel)
            self.add_message('server', f'{nick} joined {channel}', channel)
        elif command in ('PART', 'KICK') and params:
            buf = self.buffer(params[0])
            leaving = params[1] if command == 'KICK' and len(params) > 1 else nick
            buf.users.pop(fold(leaving), None)
            if fold(leaving) == fold(own):
                buf.joined = False
                buf.users.clear()
            self.add_message('error' if command == 'KICK' else 'server',
                             f'{leaving} {"was kicked from" if command == "KICK" else "left"} {buf.name}: {trailing}', buf.name)
        elif command == 'QUIT':
            for buf in self.buffers.values():
                if buf.users.pop(fold(nick), None):
                    self.add_message('server', f'{nick} quit: {trailing}', buf.name)
        elif command == 'NICK':
            new = trailing or (params[0] if params else '')
            if not new:
                return
            if fold(nick) == fold(own):
                self.client.nick = new
                self.status = f'Connected as {new} | {"TLS" if self.session_profile.tls else "NO TLS"}'
            for buf in list(self.buffers.values()):
                old = buf.users.pop(fold(nick), None)
                if old:
                    prefix = old[:len(old) - len(old.lstrip('~&@%+'))]
                    buf.users[fold(new)] = prefix + new
                    self.add_message('server', f'{nick} is now {new}', buf.name)
            self.rename_pm(nick, new)
            if fold(nick) in self.ignored:
                self.ignored.discard(fold(nick))
                self.ignored.add(fold(new))
        elif command == '353' and len(params) >= 3:
            buf = self.buffer(params[-1])
            if fold(buf.name) not in self.pending_names:
                buf.users.clear()
                self.pending_names.add(fold(buf.name))
            for name in trailing.split():
                buf.users[fold(name.lstrip('~&@%+'))] = name
        elif command == '366' and len(params) >= 2:
            self.pending_names.discard(fold(params[1]))
        elif command in ('332', 'TOPIC') and params:
            channel = params[1] if command == '332' and len(params) > 1 else params[0]
            self.buffer(channel).topic = clean(trailing)
            self.add_message('server', 'Topic: ' + trailing, channel)
        elif command == 'MODE' and params and params[0].startswith(('#', '&')):
            self.add_message('server', f'{nick} changed channel modes: ' +
                             describe_modes(params[1:] + ([trailing] if trailing else [])), params[0])
            if self.client:
                self.client.send('NAMES ' + params[0])
        elif command == 'ERROR':
            self.add_message('error', trailing, 'server')
        elif command.isdigit():
            if command in ('900', '903', '904', '905', '906', '907', '908'):
                return  # Authentication has dedicated, credential-free events.
            if command in ('353', '366'):
                return
            errors = {'433': 'Nickname in use. Try /nick AnotherNick.',
                      '474': 'Banned from this channel; the server may not provide a reason or expiry.',
                      '473': 'Invite-only channel.', '475': 'Channel requires a password.',
                      '471': 'Channel is full.', '404': 'Cannot send to this channel.'}
            kind = 'error' if 400 <= int(command) <= 599 else 'server'
            detail = ' '.join(params[1:])
            self.add_message(kind, f'{errors.get(command, command)} {detail} {trailing}', 'server')
            if kind == 'error' and self.active != 'server':
                self.add_message(kind, f'{errors.get(command, command)} {detail} {trailing}')

    def send_message(self, target, text, action=False, *, service_origin=None):
        if not self.ready or not self.client or not self.client.connected:
            self.add_message('error', 'Not registered with the server yet.')
            return False
        if target == 'server' or not valid_target(target):
            self.add_message('error', 'Choose a channel or use /query Nick first.')
            return False
        if target.startswith(('#', '&')) and not self.buffer(target).joined:
            self.add_message('error', 'You have not joined this channel. Use /join ' + target)
            return False
        if time.monotonic() - self.last_send < 1:
            self.add_message('error', 'Please wait a second before sending again. Your draft was kept.')
            return False
        payload = '\x01ACTION ' + text + '\x01' if action else text
        sensitive = service_secret(target, text)
        if sensitive:
            # Retain the command body only in memory for redacting server echoes.
            self.session_secrets.append(text)
            parts = service_credential_parts(text)
            if parts:
                self.session_secrets.extend(parts[2].split())
        if self.client.send(f'PRIVMSG {target} :{payload}'):
            self.last_send = time.monotonic()
            origin = service_origin if service_origin is not None else target
            if fold(target) in ('nickserv', 'chanserv') and service_origin is None:
                self.service_context.pop(fold(target), None)
            if fold(target) in ('nickserv', 'chanserv') and service_origin is not None:
                if fold(origin) != fold(target):
                    self.service_context[fold(target)] = (fold(origin), time.monotonic() + 30)
                else:
                    self.service_context.pop(fold(target), None)
            if fold(target) in ('nickserv', 'chanserv') and not action:
                shown = f'/msg {target} {redact_service_command(target, text)}'
            else:
                shown = f'* {self.client.nick} {text}' if action else f'<{self.client.nick}> {text}'
            self.add_message('outgoing', shown, origin)
            return True
        self.add_message('error', 'Send failed. Re-enter the credential in /connection.' if sensitive else 'Send failed. Your draft was kept.')
        return False

    def submit(self):
        text = self.input_text.strip()
        if not text:
            return
        _, target, message = service_input_parts(text, self.active)
        sensitive = service_secret(target, message)
        if not sensitive:
            sensitive = any(isinstance(secret, str) and secret and secret in text for secret in
                            [self.sasl_password, getattr(self.client, 'sasl_password', '')] + self.session_secrets)
        if not sensitive:
            self.history.append(text)
            self.history = self.history[-100:]
        else:
            self.history_draft = ''
        self.history_pos = len(self.history)
        if text.startswith('/'):
            self.input_text = ''
            self.cursor = 0
            self.command(text)
        else:
            delivered = self.send_message(self.buffers[self.active].name, text)
            if delivered or sensitive:
                self.input_text = ''
                self.cursor = 0

    def command(self, text):
        name, _, arg = text[1:].partition(' ')
        name, arg = name.lower(), arg.strip()
        buf = self.buffers[self.active]
        known = set('help clear switch query ignore unignore search users profiles close log theme notify connection connect disconnect settings reconnect quit nick join part msg me whois topic away back links'.split())
        if name not in known:
            self.add_message('error', f'Unknown command: /{name}. Use /help.')
            return
        error = None
        if name == 'join':
            if not arg:
                error = 'Usage: /join #channel'
            elif not arg.startswith(('#', '&')):
                error = 'Channel names must start with # (or &). Example: /join #debian'
            elif not valid_target(arg) or len(arg) < 2:
                error = 'Use one channel without spaces or commas. Usage: /join #channel'
        elif name in ('whois', 'query', 'ignore', 'unignore') and (not valid_target(arg) or arg.startswith(('#', '&'))):
            error = f'Usage: /{name} Nick'
        elif name == 'msg' and (not valid_target(arg.partition(' ')[0]) or not arg.partition(' ')[2].strip()):
            error = 'Usage: /msg Nick message'
        elif name in ('log', 'notify') and arg not in ('on', 'off'):
            error = f'Usage: /{name} on|off'
        elif name == 'theme' and arg not in ('dark', 'light', 'mono'):
            error = 'Usage: /theme dark|light|mono'
        elif name in ('me', 'search') and not arg:
            error = f'Usage: /{name} text'
        elif name == 'nick' and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,29}', arg):
            error = 'Usage: /nick Nick (start with a letter; no spaces)'
        elif name == 'switch' and fold(arg) not in self.buffers:
            error = 'Usage: /switch name (choose an open conversation)'
        elif name in ('part', 'topic') and not buf.joined:
            error = 'You have not joined this channel. Use /join #channel'
        if error:
            self.add_message('error', error)
            return
        if name == 'help':
            self.show_commands()
            return
        elif name == 'links':
            self.open_links()
        elif name == 'clear':
            self.open_context('conversation', buf.name)
            self.context_action('clear', self.context)
        elif name == 'switch' and fold(arg) in self.buffers:
            self.switch(arg)
        elif name == 'query' and valid_target(arg) and not arg.startswith(('#', '&')):
            self.service_context.pop(fold(arg), None)
            if fold(arg) in ('nickserv', 'chanserv'):
                self.service_queries.add(fold(arg))
            self.switch(arg)
        elif name == 'ignore' and valid_target(arg):
            self.ignored.add(fold(arg))
            self.add_message('server', f'Ignoring {arg} for this session.')
        elif name == 'unignore' and valid_target(arg):
            self.ignored.discard(fold(arg))
            self.add_message('server', f'No longer ignoring {arg}.')
        elif name == 'search' and arg:
            results = []
            needle = fold(arg)
            for source in self.buffers.values():
                if fold(source.name) == '*search*':
                    continue
                for kind, line in source.messages:
                    if needle in fold(line):
                        results.append((kind, f'[{source.name}] {line}'))
            search = self.buffer('*search*')
            search.messages = results[-MAX_MESSAGES:] or [('server', time.strftime('%H:%M') + '  No matches.')]
            self.switch('*search*')
        elif name == 'users':
            self.user_filter = '' if arg == 'clear' else arg
            self.buffers[self.active].users_anchor = ''
            self.buffers[self.active].users_scroll = 0
            self.add_message('server', f'User filter: {self.user_filter or "none"}.')
        elif name == 'profiles':
            names = sorted(set(self.prefs.profiles) | {self.profile.name})
            self.add_message('server', 'Saved profiles: ' + ', '.join(names), 'server')
            self.add_message('server', '/connection edits settings. Enter a saved Network name and press F4 to load it.', 'server')
            self.switch('server')
        elif name == 'close':
            self.close_conversation(buf.name)
        elif name == 'log' and arg in ('on', 'off'):
            self.prefs.logging = arg == 'on'
            save_preferences(self.prefs)
            self.add_message('server', f'Local logging is {arg}. Passwords are never logged.')
        elif name == 'theme' and arg in ('dark', 'light', 'mono'):
            self.prefs.theme = arg
            save_preferences(self.prefs)
            self.configure_theme()
            self.add_message('server', f'Theme changed to {arg}.')
        elif name == 'notify' and arg in ('on', 'off'):
            self.prefs.notifications = arg == 'on'
            save_preferences(self.prefs)
            self.add_message('server', f'Terminal bell is {arg} (mentions, PMs, unexpected disconnects; 5s cooldown).')
        elif name == 'connection' or (name == 'settings' and arg == 'edit'):
            self.edit_connection()
        elif name == 'connect':
            self.request_connect()
        elif name == 'disconnect':
            self.disconnect()
        elif name == 'settings':
            p = self.profile
            self.add_message('server', f'Network={p.name} server={p.host}:{p.port} TLS={p.tls} nick={p.nick} channel={p.channel or "(none)"} auth={p.auth_method}', 'server')
            self.add_message('server', f'logging={self.prefs.logging} auto-reconnect={self.prefs.auto_reconnect} notifications={self.prefs.notifications} theme={self.prefs.theme}', 'server')
            self.switch('server')
        elif name == 'reconnect':
            if arg in ('on', 'off'):
                self.prefs.auto_reconnect = arg == 'on'
                save_preferences(self.prefs)
                self.add_message('server', f'Automatic reconnect is {arg}.')
            elif arg == 'cancel':
                self.pending_connect = False
                self.reconnect_cancelled = True
                self.reconnect_due = 0
                self.status = 'Reconnect cancelled'
            elif arg in ('', 'now'):
                self.request_connect(replace=True)
            else:
                self.add_message('error', 'Use /reconnect on, off, now, or cancel.')
        elif name == 'quit':
            self.reconnect_cancelled = True
            self.running = False
        elif not self.client or not self.client.connected:
            self.add_message('error', 'Not connected.')
        elif name == 'nick' and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,29}', arg):
            self.client.send('NICK ' + arg)
        elif not self.ready:
            self.add_message('error', 'Wait for registration. /nick is available if the name is taken.')
        elif name == 'join' and valid_target(arg) and arg.startswith(('#', '&')) and len(arg) > 1:
            self.client.send('JOIN ' + arg)
            self.add_message('server', 'Requested join: ' + arg)
        elif name == 'part' and buf.joined:
            self.client.send(f'PART {buf.name} :{arg or "Leaving"}')
        elif name == 'msg':
            target, _, message = arg.partition(' ')
            if valid_target(target) and message:
                service = fold(target) in ('nickserv', 'chanserv')
                origin = buf.name if service else None
                if not self.send_message(target, message, service_origin=origin) and not service_secret(target, message):
                    self.input_text = text
                    self.cursor = len(text)
            else:
                self.add_message('error', 'Usage: /msg Nick message')
        elif name == 'me' and arg:
            if not self.send_message(buf.name, arg, True):
                self.input_text = text
                self.cursor = len(text)
        elif name == 'whois' and valid_target(arg):
            self.client.send('WHOIS ' + arg)
            self.switch('server')
        elif name == 'topic' and buf.joined:
            self.client.send('TOPIC ' + buf.name + (' :' + arg if arg else ''))
        elif name == 'away':
            self.client.send('AWAY :' + (arg or 'Away'))
        elif name == 'back':
            self.client.send('AWAY')
        else:
            self.add_message('error', f'Usage or context for /{name} is invalid. Use /help.')

    def put(self, y, x, text, width, attr=0):
        try:
            clipped = clip(clean(text), max(0, width))
            self.screen.addnstr(y, x, clipped, len(clipped), attr)
        except curses.error:
            pass

    def configure_theme(self):
        self.nick_colors = []
        self.colors = {'title': curses.A_REVERSE, 'error': curses.A_BOLD,
                       'server': curses.A_DIM, 'mention': curses.A_BOLD}
        if not curses.has_colors() or self.prefs.theme == 'mono':
            return
        try:
            curses.start_color()
            curses.use_default_colors()
            palette = {'dark': (curses.COLOR_CYAN, curses.COLOR_RED),
                       'light': (curses.COLOR_BLUE, curses.COLOR_RED)}[self.prefs.theme]
            curses.init_pair(1, palette[0], -1)
            curses.init_pair(2, palette[1], -1)
            self.colors['title'] = curses.color_pair(1) | curses.A_BOLD
            self.colors['error'] = curses.color_pair(2) | curses.A_BOLD
            self.colors['mention'] = curses.color_pair(1) | curses.A_BOLD
            palette = ([81, 114, 180, 213, 141, 117] if self.prefs.theme == 'dark'
                       else [25, 28, 88, 90, 94, 30]) if curses.COLORS >= 256 else [2, 3, 4, 5, 6]
            for pair, color in enumerate(palette, 3):
                if pair >= curses.COLOR_PAIRS:
                    break
                curses.init_pair(pair, color, -1)
                self.nick_colors.append(curses.color_pair(pair))
        except curses.error:
            pass

    def draw(self):
        h, w = self.screen.getmaxyx()
        self.screen.erase()
        self.click_buffers.clear()
        self.click_users.clear()
        self.click_links.clear()
        if h < 10 or w < 50:
            self.put(0, 0, 'Resize terminal to at least 50 x 10.', w - 1)
            self.screen.refresh()
            return
        buf = self.buffers[self.active]
        self.put(0, 0, (' ⇹ IRdisC | ' + self.status).ljust(w-1), w-1, self.colors['title'])
        left, right = (20, 18) if w >= 90 else (0, 0)
        if not right and self.focus == 'users':
            self.focus = 'chat'
        if left:
            self.put(1, 0, ' CONVERSATIONS', left-1, curses.A_BOLD)
            names = list(self.buffers)
            start = max(0, names.index(self.active) - (h - 7))
            for row, key in enumerate(names[start:start+h-5], 2):
                item = self.buffers[key]
                prefix = '>' if key == self.active else ('!' if item.mentioned else '•' if item.unread else ' ')
                self.put(row, 0, prefix + ' ' + item.name, left-1, self.colors['mention'] if item.mentioned else curses.A_BOLD if key == self.active else 0)
                self.click_buffers[row] = key
            visible_users, user_page = self.user_rows()
            user_title = f'USERS ({len(visible_users)}/{len(buf.users)})' if self.user_filter else f'USERS ({len(buf.users)})'
            self.put(1, w-right, user_title, right-1, curses.A_REVERSE if self.focus == 'users' else curses.A_BOLD)
            for row, nick in enumerate(visible_users[buf.users_scroll:buf.users_scroll+user_page], 2):
                self.put(row, w-right, nick, right-1, self.nick_attr(nick))
                self.click_users[row] = nick.lstrip('~&@%+')
            last = min(len(visible_users), buf.users_scroll+user_page)
            self.put(h-4, w-right, f'{buf.users_scroll+1 if last else 0}-{last}/{len(visible_users)}', right-1, curses.A_DIM)
        chat_w = max(10, w-left-right-2)
        header = buf.name + (' [joined]' if buf.joined else '') + ' | ' + buf.topic
        shown_header = clip(header, max(1, chat_w-12)) + ' … [F8 topic]' if cells(header) > chat_w else header
        self.put(1, left, shown_header, chat_w, curses.A_BOLD)
        for url in urls_in(buf.topic):
            pos = shown_header.find(url)
            if pos >= 0:
                begin = cells(shown_header[:pos])
                self.click_links.append((1, left+begin, left+begin+cells(url), url))
        lines = []
        complete_urls = set(urls_in(buf.topic + ' ' + ' '.join(message for _, message in buf.messages)))
        for index, (kind, message) in enumerate(buf.messages):
            if index == buf.first_unread:
                lines.append(('server', '── New messages ──', None, 0))
            lines.extend((kind, part, buf.messages[index], offset) for part, offset in message_rows(message, chat_w))
        area = h - 5
        if buf.scroll and buf.wrap_width != chat_w and buf.view_anchor:
            source, offset = buf.view_anchor
            candidates = [i for i, (_, _, item, start) in enumerate(lines)
                          if item is source and start <= offset]
            if candidates:
                buf.scroll = max(0, len(lines)-candidates[-1]-1)
        buf.wrap_width = chat_w
        buf.scroll = min(buf.scroll, max(0, len(lines)-area))
        end = len(lines)-buf.scroll
        buf.view_anchor = (lines[end-1][2], lines[end-1][3]) if end and lines[end-1][2] else None
        for row, (kind, line, _, _) in enumerate(lines[max(0, end-area):end], 2):
            attr = self.colors['error'] if kind == 'error' else self.colors['server'] if kind == 'server' else 0
            self.put(row, left, line, chat_w, attr)
            for url in urls_in(line):
                # Only link complete URLs, never a truncated/wrapped fragment.
                if url in complete_urls:
                    pos = cells(line[:line.find(url)])
                    self.put(row, left+pos, url, min(cells(url), chat_w-pos), curses.A_UNDERLINE)
                    self.click_links.append((row, left+pos, left+pos+cells(url), url))
            if kind in ('message', 'outgoing'):
                match = re.match(r'^\d\d:\d\d  (?:<([^>]+)>|\* (\S+))', line)
                if match:
                    group = 1 if match.group(1) else 2
                    pos = cells(line[:match.start(group)])
                    self.put(row, left+pos, match.group(group), max(0, chat_w-pos), self.nick_attr(match.group(group)))
        hint = self.commands_label()+' | F2 Actions | F6 Chat | PgUp/Dn Scroll'
        if self.focus == 'users':
            hint = self.commands_label()+' | USERS: ↑↓ PgUp/PgDn | Esc: chat'
        if buf.scroll:
            hint += f' | ↓ {buf.new_while_scrolled} new | Ctrl+L: latest'
        else:
            buf.new_while_scrolled = 0
        self.put(h-3, 0, hint, w-1, curses.A_REVERSE)
        self.put(h-2, 0, 'Tip: maximize terminal for more messages/users. Esc: dismiss' if self.ready and w < 90 and not self.size_tip_dismissed else 'F7: focus USERS | F8: full topic | Click user: PM', w-1, curses.A_DIM)
        offset = max(0, self.cursor - (w-5))
        display = masked_service_input(self.input_text, self.active)
        for secret in [self.sasl_password, getattr(self.client, 'sasl_password', '')] + self.session_secrets:
            if isinstance(secret, str) and secret:
                display = display.replace(secret, '*' * len(secret))
        self.put(h-1, 0, '> ' + display[offset:], w-1)
        if self.menu:
            for row, line in enumerate([' ACTIONS (press number; Esc closes)', ' 1 Join channel', ' 2 Private message', ' 3 WHOIS user', ' 4 Leave channel', ' 5 Help', ' 6 Quit', ' 7 Connection settings', ' 8 Connect / Reconnect', ' 9 Disconnect'], 0):
                self.put(row, max(0, (w-40)//2), line.ljust(39), min(39, w-1), curses.A_REVERSE)
        self.draw_context()
        if self.topic_view:
            self.draw_topic()
        try:
            self.screen.move(h-1, min(w-2, 2+self.cursor-offset))
        except curses.error:
            pass
        self.screen.refresh()

    def key(self, key):
        if self.commands_key(key):
            self.show_commands()
            return
        if key == curses.KEY_RESIZE:
            self.size_tip_dismissed = True
        if key == '\x1b':
            self.size_tip_dismissed = True
        if key == curses.KEY_MOUSE:
            try:
                event = curses.getmouse()
                _, x, y, _, state = event
                if y == self.screen.getmaxyx()[0]-3 and x < len(self.commands_label()) and state & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED):
                    self.show_commands()
                    return
                curses.ungetmouse(*event)
            except curses.error:
                pass
        buf = self.buffers[self.active]
        if self.topic_view:
            self.topic_key(key)
            return
        if self.context:
            self.context_key(key)
            return
        if self.menu:
            self.menu = False
            templates = {'1': '/join #', '2': '/query ', '3': '/whois '}
            if key in templates:
                self.input_text = templates[key]
                self.cursor = len(self.input_text)
            elif key in ('4', '5', '6', '7', '8', '9'):
                self.command({'4': '/part', '5': '/help', '6': '/quit', '7': '/connection', '8': '/reconnect', '9': '/disconnect'}[key])
            return
        if key == curses.KEY_F7:
            if self.screen.getmaxyx()[1] >= 90:
                self.focus = 'chat' if self.focus == 'users' else 'users'
            else:
                self.add_message('server', 'Widen the terminal to 90 columns for USERS, or press F4 for the user list.')
            return
        if key == curses.KEY_F8:
            self.open_topic()
            return
        if self.focus == 'users':
            if key == '\x1b':
                self.focus = 'chat'
                return
            page = max(1, self.screen.getmaxyx()[0]-6)
            amounts = {curses.KEY_UP: -1, curses.KEY_DOWN: 1,
                       curses.KEY_PPAGE: -page, curses.KEY_NPAGE: page}
            if key in amounts:
                self.scroll_users(amounts[key])
                return
        if key == '\x1b':
            self.read_escape_sequence()
        elif key == curses.KEY_F2:
            self.menu = True
        elif key == curses.KEY_F3:
            self.open_context('conversation', buf.name)
        elif key == curses.KEY_F4:
            users = sorted((n.lstrip('~&@%+') for n in buf.users.values()), key=fold)
            if users:
                self.open_context('user', users[0])
                self.context['items'] = [(n, 'select_user:'+n) for n in users]
        elif key == curses.KEY_F5:
            self.open_links()
        elif key == curses.KEY_F6:
            names = list(self.buffers)
            self.switch(names[(names.index(self.active)+1) % len(names)])
        elif key == curses.KEY_PPAGE:
            buf.scroll += 10
        elif key == curses.KEY_NPAGE:
            buf.scroll = max(0, buf.scroll-10)
        elif key == '\x0c':
            buf.scroll = 0
            buf.new_while_scrolled = 0
        elif key == curses.KEY_MOUSE:
            try:
                _, x, y, _, state = curses.getmouse()
                height, width = self.screen.getmaxyx()
                in_users = width >= 90 and x >= width-18 and 1 <= y < height-3
                wheel = -3 if state & curses.BUTTON4_PRESSED else 3 if state & getattr(curses, 'BUTTON5_PRESSED', 0) else 0
                if wheel:
                    if in_users:
                        self.scroll_users(wheel)
                    elif 2 <= y < height-3:
                        buf.scroll = max(0, buf.scroll-wheel)
                    return
                if state & curses.BUTTON1_CLICKED and y == 1:
                    if in_users:
                        self.focus = 'users'
                    elif (20 if width >= 90 else 0) <= x < width-(18 if width >= 90 else 0):
                        self.open_topic()
                    return
                if state & curses.BUTTON1_CLICKED and not in_users:
                    self.focus = 'chat'
                hit = next((url for row, begin, end, url in self.click_links if y == row and begin <= x < end), None)
                if state & curses.BUTTON1_CLICKED and hit:
                    ctx = {'target': hit, 'origin': self.active, 'items': [], 'x': x, 'y': y}
                    self.context_action('select_url:'+hit, ctx)
                elif state & (curses.BUTTON3_CLICKED | curses.BUTTON3_PRESSED) and self.screen.getmaxyx()[1] >= 90:
                    if x < 20 and y in self.click_buffers:
                        self.open_context('conversation', self.buffers[self.click_buffers[y]].name, x, y)
                    elif x >= self.screen.getmaxyx()[1]-18 and y in self.click_users:
                        self.open_context('user', self.click_users[y], x, y)
                elif state & curses.BUTTON1_CLICKED and self.screen.getmaxyx()[1] >= 90:
                    if x < 20 and y in self.click_buffers:
                        self.switch(self.click_buffers[y])
                    elif x >= self.screen.getmaxyx()[1]-18 and y in self.click_users:
                        self.switch(self.click_users[y])
                elif state & getattr(curses, 'BUTTON4_PRESSED', 0):
                    buf.scroll += 3
                elif state & getattr(curses, 'BUTTON5_PRESSED', 0):
                    buf.scroll = max(0, buf.scroll-3)
            except curses.error:
                pass
        elif key in ('\n', '\r'):
            self.submit()
        elif key in ('\x7f', '\b', curses.KEY_BACKSPACE):
            if self.cursor:
                self.input_text = self.input_text[:self.cursor-1]+self.input_text[self.cursor:]
                self.cursor -= 1
        elif key == curses.KEY_DC:
            self.input_text = self.input_text[:self.cursor]+self.input_text[self.cursor+1:]
        elif key == curses.KEY_LEFT:
            self.cursor = max(0, self.cursor-1)
        elif key == curses.KEY_RIGHT:
            self.cursor = min(len(self.input_text), self.cursor+1)
        elif key == curses.KEY_HOME:
            self.cursor = 0
        elif key == curses.KEY_END:
            self.cursor = len(self.input_text)
        elif key in (curses.KEY_UP, curses.KEY_DOWN):
            if self.history_pos == len(self.history):
                self.history_draft = self.input_text
            self.history_pos = max(0, min(len(self.history), self.history_pos + (-1 if key == curses.KEY_UP else 1)))
            self.input_text = self.history[self.history_pos] if self.history_pos < len(self.history) else self.history_draft
            self.cursor = len(self.input_text)
        elif key == '\t':
            before = self.input_text[:self.cursor]
            token = before.split(' ')[-1]
            options = [n.lstrip('~&@%+') for n in buf.users.values()] + [b.name for b in self.buffers.values()]
            options += ['/join', '/part', '/query', '/msg', '/whois', '/help', '/quit', '/nick', '/me', '/topic', '/away', '/back', '/clear', '/switch', '/ignore', '/unignore', '/search', '/users', '/profiles', '/close', '/log', '/notify', '/theme', '/reconnect', '/settings']
            options += ['/connection', '/connect', '/disconnect']
            match = next((o for o in options if token and fold(o).startswith(fold(token))), None)
            if match:
                is_nick = any(fold(match) == fold(n.lstrip('~&@%+')) for n in buf.users.values())
                prefix = before[:-len(token)] + match + (': ' if before == token and is_nick else ' ')
                self.input_text = prefix + self.input_text[self.cursor:]
                self.cursor = len(prefix)
        elif key == '\x03':
            self.running = False
        elif isinstance(key, str) and key.isprintable() and len(self.input_text) < 1000:
            self.input_text = self.input_text[:self.cursor]+key+self.input_text[self.cursor:]
            self.cursor += len(key)

    def insert_text(self, text):
        room = 1000 - len(self.input_text)
        text = text[:max(0, room)]
        self.input_text = self.input_text[:self.cursor] + text + self.input_text[self.cursor:]
        self.cursor += len(text)

    def read_escape_sequence(self):
        """Recognize terminal bracketed-paste without treating it as keystrokes."""
        sequence = ''
        self.screen.timeout(30)
        try:
            for _ in range(5):
                part = self.screen.get_wch()
                if not isinstance(part, str):
                    return
                sequence += part
                if sequence.endswith('~'):
                    break
        except curses.error:
            return
        finally:
            self.screen.timeout(100)
        if sequence != '[200~':
            return
        pasted = ''
        marker = '\x1b[201~'
        self.screen.timeout(2000)
        try:
            while len(pasted) < 10000 and not pasted.endswith(marker):
                part = self.screen.get_wch()
                if isinstance(part, str):
                    pasted += part
        except curses.error:
            self.add_message('error', 'Paste timed out and was cancelled.')
            return
        finally:
            self.screen.timeout(100)
        if pasted.endswith(marker):
            self.review_paste(pasted[:-len(marker)])

    def review_paste(self, pasted):
        pasted = pasted.replace('\r\n', '\n').replace('\r', '\n')
        lines = pasted.split('\n')
        if len(lines) <= 1:
            self.insert_text(pasted)
            return
        h, w = self.screen.getmaxyx()
        self.screen.erase()
        self.put(1, 2, f'MULTILINE PASTE: {len(lines)} lines', w-4, curses.A_BOLD)
        self.put(2, 2, 'Nothing has been sent. Y inserts it as one draft; any other key cancels.', w-4)
        preview = [clean(line) for line in lines[:max(1, h-6)]]
        for row, line in enumerate(preview, 4):
            self.put(row, 4, line, w-8)
        self.screen.refresh()
        self.screen.timeout(-1)
        confirm = self.screen.get_wch()
        self.screen.timeout(100)
        if confirm in ('y', 'Y'):
            combined = ' | '.join(line.strip() for line in lines if line.strip())
            self.insert_text(combined)
            self.add_message('server', f'Inserted {len(lines)} pasted lines as one unsent draft.')
        else:
            self.add_message('server', 'Multiline paste cancelled; nothing was sent.')

    def run(self):
        curses.curs_set(1)
        self.configure_theme()
        sys.stdout.write('\x1b[?2004h')
        sys.stdout.flush()
        try:
            while True:
                h, w = self.screen.getmaxyx()
                if h >= 10 and w >= 50:
                    break
                self.screen.erase()
                self.put(0, 0, 'Resize to 50 x 10 for setup. Q cancels.', w-1)
                self.screen.refresh()
                self.screen.timeout(-1)
                if self.screen.get_wch() in ('q', 'Q'):
                    return
            curses.mousemask(curses.ALL_MOUSE_EVENTS)
            self.setup()
            self.screen.timeout(100)
            self.add_message('server', 'Welcome! Use /join #channel to join a conversation. '+self.commands_label()+' lists commands.')
            while self.running:
                self.process_events()
                self.draw()
                try:
                    self.key(self.screen.get_wch())
                except curses.error:
                    continue
        finally:
            sys.stdout.write('\x1b[?2004l')
            sys.stdout.flush()
            if self.client:
                self.client.close()
