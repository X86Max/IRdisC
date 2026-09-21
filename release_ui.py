"""Shared, offline help and network selection for startup and chat."""
import curses
import os
import sys
from text_layout import wrap_cells


class TerminalTitle:
    """Best-effort xterm-style OSC title; never query the terminal for data.

    OSC 2 changes the window title. CSI 22/23 ; 2 t push/pop only that title.
    Unknown terminals are left alone. Unsupported operations are ignored by
    compatible emulators; restoration also depends on their title-stack support.
    """
    def __init__(self, stream=None, term=None):
        self.stream = sys.stdout if stream is None else stream
        term = os.environ.get('TERM', '') if term is None else term
        families = ('xterm', 'rxvt', 'screen', 'tmux', 'alacritty', 'foot',
                    'kitty', 'wezterm', 'st')
        try:
            self.enabled = self.stream.isatty() and any(term == name or term.startswith(name+'-') for name in families)
        except (OSError, ValueError, AttributeError):
            self.enabled = False
        self.saved = False
        self.last = None

    def write(self, sequence):
        try:
            self.stream.write(sequence)
            self.stream.flush()
            return True
        except (OSError, ValueError, UnicodeError):
            self.enabled = False
            return False

    def __enter__(self):
        if self.enabled:
            self.saved = self.write('\x1b[22;2t')
            self.update()
        return self

    def update(self, network=''):
        if not self.enabled:
            return
        # Profile labels are user-editable: strip controls, bidi formatting,
        # ESC/BEL/ST and cap length before interpolating into an OSC sequence.
        label = ' '.join(''.join(c for c in network if c.isprintable()).split())[:40]
        title = '⇹ IRdisC' + (' — '+label if label else '')
        if title != self.last and self.write('\x1b]2;'+title+'\x1b\\'):
            self.last = title

    def __exit__(self, *_):
        if self.saved:
            self.write('\x1b[23;2t')
            self.saved = False


COMMANDS = {
    'Connection': [('/connection', 'Edit connection; /settings edit also works'),
                   ('/settings', 'Show non-secret settings'), ('/profiles', 'List saved profiles; F4 loads by name in editor'),
                   ('/connect', 'Connect saved profile'), ('/disconnect', 'Disconnect and stay in app'),
                   ('/reconnect [on|off|now|cancel]', 'Replace session or control automatic retries'),
                   ('/quit [reason]', 'Disconnect and exit')],
    'Channels': [('/join #channel', 'Join a channel'), ('/part [reason]', 'Leave; keep local history'),
                 ('/topic [text]', 'Read or set topic; F8 opens full topic'),
                 ('/close', 'Close PM or a channel already left')],
    'Messaging': [('/query Nick', 'Open PM'), ('/msg Nick text', 'Send PM'), ('/me action', 'Send action'),
                  ('/away [reason]', 'Set away'), ('/back', 'Clear away'),
                  ('/links', 'List links; F5; confirm before opening')],
    'Users': [('/whois Nick', 'Show user details in server chat'), ('/nick Nick', 'Change your nickname'),
              ('/ignore Nick', 'Ignore for this session'), ('/unignore Nick', 'Stop ignoring'),
              ('/users words|clear', 'Filter USERS; F7 focuses list')],
	'Interface': [('/help', 'Open Commands; Esc closes'), ('/switch name', 'Switch conversation; F6 next'),
              ('/clear', 'Clear local history after confirmation'), ('/search words', 'Search memory history'),
              ('/theme dark|light|mono', 'Change theme'), ('/log on|off', 'Toggle local logging'),
              ('Tab / Up / Down', 'Nick completion / input history'),
              ('PgUp / PgDn / Ctrl+L', 'Scroll chat / return to latest'),
              ('F2 / F3 / F4', 'Actions / conversation menu / user picker'),
              ('Mouse', 'Left: select or PM; right: context; wheel: panel scroll'),
              ('Shift + mouse drag', 'Select terminal text for copying (terminal-dependent)')],
    'Notifications': [('/notify on|off', 'Bell for mentions, PMs, unexpected drops; 5s cooldown')],
}

PRESETS = [('OFTC', 'irc.oftc.net'), ('Libera.Chat', 'irc.libera.chat'), ('Other / Custom', '')]


def help_shortcut():
    # No F1 binding exists in IRdisC/curses. terminfo tells us whether F1
    # can be decoded, not whether the terminal/desktop intercepts it.
    try:
        supported = bool(curses.tigetstr('kf1'))
    except curses.error:
        supported = False
    return (curses.KEY_F1, 'F1') if supported else ('\x07', 'Ctrl+G')


class ReleaseUI:
    def commands_key(self, key):
        shortcut, _ = help_shortcut()
        return key in (shortcut, '\x07')

    def commands_label(self):
        return help_shortcut()[1] + ' Commands'

    def show_commands(self):
        offset = 0
        while self.running:
            self.process_events()
            h, w = self.screen.getmaxyx()
            lines = []
            for group, entries in COMMANDS.items():
                lines.append(group)
                for syntax, description in entries:
                    lines.extend(line for line, _ in wrap_cells('  '+syntax+' — '+description, max(1, w-3)))
                lines.append('')
            page = max(1, h-3)
            offset = max(0, min(offset, max(0, len(lines)-page)))
            self.screen.erase()
            self.put(0, 0, '⇹ IRdisC | Commands', w-1, curses.A_REVERSE)
            for row, line in enumerate(lines[offset:offset+page], 1):
                self.put(row, 0, line, w-1)
            self.put(h-1, 0, '[Close] Esc | ↑↓ PgUp/PgDn wheel | Ctrl+G: help fallback', w-1)
            self.screen.refresh()
            try:
                key = self.screen.get_wch()
            except curses.error:
                continue
            if key in ('\x1b', 'q', '\n', '\r') or self.commands_key(key):
                return
            if key == curses.KEY_MOUSE:
                try:
                    _, x, y, _, state = curses.getmouse()
                except curses.error:
                    continue
                if state & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED) and y == h-1 and x < 8:
                    return
                key = curses.KEY_UP if state & curses.BUTTON4_PRESSED else (curses.KEY_DOWN if state & getattr(curses, 'BUTTON5_PRESSED', 0) else None)
            if key in (curses.KEY_DOWN, curses.KEY_NPAGE):
                offset += page if key == curses.KEY_NPAGE else 1
            elif key in (curses.KEY_UP, curses.KEY_PPAGE):
                offset -= page if key == curses.KEY_PPAGE else 1

    def choose_network(self, values):
        index = 0
        while self.running:
            self.process_events()
            h, w = self.screen.getmaxyx()
            self.screen.erase()
            self.put(0, 1, '⇹ IRdisC | Choose network', w-2, curses.A_BOLD)
            for i, (name, _) in enumerate(PRESETS):
                self.put(i+2, 2, name, w-4, curses.A_REVERSE if i == index else 0)
            self.put(h-1, 0, '[Cancel] Esc | Enter: select | '+self.commands_label(), w-1)
            self.screen.refresh()
            try:
                key = self.screen.get_wch()
            except curses.error:
                continue
            if self.commands_key(key):
                self.show_commands()
            elif key == '\x1b':
                return
            elif key in (curses.KEY_UP, curses.KEY_BTAB):
                index = (index-1) % len(PRESETS)
            elif key in (curses.KEY_DOWN, '\t'):
                index = (index+1) % len(PRESETS)
            elif key == curses.KEY_MOUSE:
                try:
                    _, x, y, _, state = curses.getmouse()
                except curses.error:
                    continue
                if state & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED):
                    if y == h-1:
                        if x < 8:
                            return
                        self.show_commands()
                    elif 2 <= y < 2+len(PRESETS):
                        index, key = y-2, '\n'
            if key in ('\n', '\r', curses.KEY_ENTER):
                name, host = PRESETS[index]
                values.update(name=name if host else '', host=host, port='6697' if host else '', tls='yes')
                return
