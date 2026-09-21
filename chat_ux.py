"""Small TUI interactions. No network or clipboard action occurs on import."""
import curses
import hashlib
import os
import re
import shutil
import subprocess
import time
import threading
import webbrowser
from urllib.parse import urlsplit


def urls_in(text):
    result = []
    for match in re.finditer(r'https?://[^\s<>"\x00-\x1f]+', text):
        value = match.group().rstrip('.,;!?)')
        try:
            if urlsplit(value).hostname and value not in result:
                result.append(value)
        except ValueError:
            pass
    return result


def fold(value):
    return value.lower().translate(str.maketrans('[]\\^', '{}|~'))


def nick_color_index(nick, count):
    return int.from_bytes(hashlib.sha256(fold(nick).encode()).digest()[:4], 'big') % max(1, count)


def mentions(text, nick):
    return bool(nick) and bool(re.search(r'(?<![\w{}|^~-])' + re.escape(fold(nick)) +
                                        r'(?![\w{}|^~-])', fold(text)))


def describe_modes(parts):
    if not parts:
        return 'channel settings'
    names = {'b': 'ban', 'o': 'operator', 'v': 'voice', 'i': 'invite-only',
             'm': 'moderated', 'n': 'members-only messages', 't': 'protected topic',
             'k': 'channel password', 'l': 'user limit'}
    args = iter(parts[1:])
    adding = True
    changes = []
    for mode in parts[0]:
        if mode in '+-':
            adding = mode == '+'
            continue
        target = next(args, '') if mode in 'bovk' or (mode == 'l' and adding) else ''
        if mode == 'k' and target:
            target = '[hidden]'
        changes.append(('enabled ' if adding else 'removed ') + names.get(mode, 'mode '+mode) +
                       (' ('+target+')' if target else ''))
    return '; '.join(changes)


def copy_text(text):
    """Use optional desktop helpers; never use a shell or read the clipboard."""
    choices = []
    if os.environ.get('WAYLAND_DISPLAY'):
        choices.append(['wl-copy'])
    if os.environ.get('DISPLAY'):
        choices.extend([['xclip', '-selection', 'clipboard'], ['xsel', '--clipboard', '--input']])
    if os.sys.platform == 'darwin':
        choices.append(['pbcopy'])
    for command in choices:
        executable = shutil.which(command[0])
        if executable:
            try:
                subprocess.run([executable, *command[1:]], input=text.encode(),
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=2, check=True)
                return True
            except (OSError, subprocess.SubprocessError):
                continue
    return False


class ChatUX:
    def bell(self):
        if not self.prefs.notifications:
            return
        now = time.monotonic()
        if now - self.last_bell < 5:
            return
        self.last_bell = now
        try:
            curses.beep()
        except curses.error:
            pass

    def nick_attr(self, nick):
        bare = nick.lstrip('~&@%+')
        own = self.client.nick if self.client else self.nick
        attr = curses.A_BOLD if fold(bare) == fold(own) else 0
        if self.nick_colors:
            attr |= self.nick_colors[nick_color_index(bare, len(self.nick_colors))]
        return attr

    def context_options(self, kind, target):
        if kind == 'user':
            return [('Private message', 'pm'), ('WHOIS', 'whois'), ('Mention', 'mention'),
                    ('Unignore' if fold(target) in self.ignored else 'Ignore', 'ignore'),
                    ('Copy nickname', 'copy')]
        buf = self.buffers[fold(target)]
        if target == 'server':
            return [('Connection settings', 'settings'), ('Connect / Reconnect', 'reconnect'),
                    ('Disconnect', 'disconnect'), ('Clear local history', 'clear')]
        if target.startswith(('#', '&')):
            items = [('Leave channel' if buf.joined else 'Rejoin channel', 'leave' if buf.joined else 'rejoin'),
                     ('Channel info', 'info'), ('Copy channel name', 'copy'),
                     ('Clear local history', 'clear')]
            if not buf.joined:
                items.append(('Close conversation', 'close'))
            return items
        if target.startswith('*'):
            return [('Close conversation', 'close'), ('Clear local history', 'clear')]
        return [('Close conversation', 'close'), ('WHOIS user', 'whois'),
                ('Unignore user' if fold(target) in self.ignored else 'Ignore user', 'ignore'),
                ('Copy nickname', 'copy')]

    def open_context(self, kind, target, x=2, y=2):
        self.menu = False
        self.context = {'kind': kind, 'target': target, 'origin': self.active,
                        'items': self.context_options(kind, target), 'selected': 0,
                        'x': x, 'y': y}

    def draw_context(self):
        ctx = self.context
        if not ctx:
            return
        h, w = self.screen.getmaxyx()
        width = min(w-1, max(30, *(len(label)+4 for label, _ in ctx['items'])))
        visible = max(1, h-2)
        start = max(0, ctx['selected']-visible+1)
        shown = ctx['items'][start:start+visible]
        ctx['start'] = start
        height = len(shown)+2
        x = max(0, min(ctx['x'], w-width-1))
        y = max(0, min(ctx['y'], h-height))
        ctx['bounds'] = (x, y, width, height)
        self.put(y, x, (' '+ctx['target']).ljust(width), width, curses.A_REVERSE)
        for i, (label, _) in enumerate(shown):
            self.put(y+i+1, x, (' '+label).ljust(width), width,
                     curses.A_REVERSE | (curses.A_BOLD if i+start == ctx['selected'] else curses.A_DIM))
        self.put(y+height-1, x, ' ↑↓ Enter | Esc closes'.ljust(width), width, curses.A_REVERSE)

    def context_key(self, key):
        ctx = self.context
        if key == '\x1b':
            self.context = None
        elif key in (curses.KEY_UP, curses.KEY_DOWN, '\t'):
            ctx['selected'] = (ctx['selected'] + (-1 if key == curses.KEY_UP else 1)) % len(ctx['items'])
        elif key in ('\n', '\r', curses.KEY_ENTER):
            self.context_action(ctx['items'][ctx['selected']][1], ctx)
        elif key == curses.KEY_MOUSE:
            try:
                _, x, y, _, state = curses.getmouse()
                if state & curses.BUTTON1_CLICKED:
                    bx, by, bw, bh = ctx.get('bounds', (0, 0, 0, 0))
                    if bx <= x < bx+bw and by < y < by+bh-1:
                        self.context_action(ctx['items'][ctx.get('start', 0)+y-by-1][1], ctx)
                    else:
                        self.context = None
            except curses.error:
                pass

    def close_conversation(self, target):
        key = fold(target)
        buf = self.buffers.get(key)
        if not buf:
            return
        if key == 'server' or buf.joined:
            self.add_message('error', 'Leave channel first; closing a conversation never sends PART.')
            return
        if key == self.active:
            self.switch('server')
        del self.buffers[key]

    def context_action(self, action, ctx):
        self.context = None
        target = ctx['target']
        buf = self.buffers.get(fold(target))
        if action.startswith('select_user:'):
            self.open_context('user', action.partition(':')[2])
        elif action.startswith('select_url:'):
            url = action.partition(':')[2]
            self.context = dict(ctx, target=url, items=[('Cancel', 'cancel'), ('Open HTTP(S) URL in browser', 'open_url')],
                                selected=0, url=url)
        elif action == 'open_url':
            url = ctx.get('url', '')
            if urls_in(url) == [url]:
                threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
        elif action == 'clear':
            self.context = dict(ctx, items=[('Cancel', 'cancel'), ('Clear local history (memory only)', 'clear_confirm')],
                                selected=0)
        elif action == 'clear_confirm' and buf:
            buf.messages.clear()
            buf.scroll = buf.unread = buf.new_while_scrolled = 0
            buf.first_unread = None
            buf.mentioned = False
        elif action == 'close':
            self.close_conversation(target)
        elif action in ('settings', 'reconnect', 'disconnect'):
            self.command({'settings': '/connection', 'reconnect': '/reconnect', 'disconnect': '/disconnect'}[action])
        elif action == 'pm':
            self.switch(target)
        elif action == 'mention':
            if ctx['origin'] in self.buffers:
                self.switch(ctx['origin'])
            self.insert_text(target + (': ' if self.cursor == 0 else ' '))
        elif action == 'ignore':
            self.command(('/unignore ' if fold(target) in self.ignored else '/ignore ') + target)
        elif action == 'whois':
            self.command('/whois '+target)
        elif action == 'copy':
            success = copy_text(target)
            self.add_message('server' if success else 'error',
                             'Copied: '+target if success else 'Clipboard unavailable. Select/copy this name using your terminal: '+target)
        elif action == 'info' and buf:
            self.add_message('server', f'{buf.name}: {"joined" if buf.joined else "not joined"}; {len(buf.users)} users. Topic: {buf.topic or "(none)"}')
        elif action in ('leave', 'rejoin'):
            if not self.ready or not self.client or not self.client.connected:
                self.add_message('error', 'Not connected. Use /connect.')
            elif buf and action == 'leave' and buf.joined:
                self.client.send('PART '+target+' :Leaving')
            elif buf and action == 'rejoin' and not buf.joined:
                self.client.send('JOIN '+target)

    def open_links(self):
        buf = self.buffers[self.active]
        urls = urls_in(buf.topic + ' ' + ' '.join(text for _, text in buf.messages))
        if not urls:
            self.add_message('server', 'No HTTP(S) links in this conversation.')
            return
        self.context = {'kind': 'links', 'target': 'Links (confirm before opening)',
                        'origin': self.active, 'items': [(url, 'select_url:'+url) for url in urls],
                        'selected': 0, 'x': 2, 'y': 2}

    def rename_pm(self, old, new):
        oldkey, newkey = fold(old), fold(new)
        if oldkey not in self.buffers or oldkey == 'server':
            return
        buf = self.buffers[oldkey]
        if self.active == oldkey:
            buf.draft = self.input_text
        if oldkey != newkey and newkey in self.buffers:
            other = self.buffers[newkey]
            if self.active == newkey:
                other.draft = self.input_text
            # Preserve both histories and any unsent text on collision.
            buf.messages.extend(other.messages)
            buf.messages = buf.messages[-400:]
            buf.unread += other.unread
            buf.mentioned |= other.mentioned
            if other.draft:
                buf.draft = (buf.draft+' '+other.draft).strip()
        if self.active in (oldkey, newkey):
            self.active = newkey
            self.input_text = buf.draft
            self.cursor = len(self.input_text)
        del self.buffers[oldkey]
        buf.name = new
        self.buffers[newkey] = buf
        self.add_message('server', old+' is now '+new, new)
