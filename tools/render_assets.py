"""Developer-only asset generation: Inkscape + Pillow; no network access.

The screenshot uses the real curses renderer in a pseudoterminal with demo data.
"""
import curses
import fcntl
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import termios

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def capture(screen, destination):
    from unittest.mock import patch
    from irdisc_settings import default_preferences
    from terminal_ui import ChatApp
    with patch('terminal_ui.load_preferences', side_effect=default_preferences):
        app = ChatApp(screen)
    app.configure_theme()
    app.nick = 'Alex'
    app.status = 'Connected as Alex | TLS'
    app.ready = True
    app.switch('#welcome')
    buf = app.buffers[app.active]
    buf.joined = True
    buf.topic = 'Welcome to IRdisC — IRC, discomplicated.'
    buf.users = {name.lower(): name for name in ['@Morgan', 'Alex', 'Casey', 'Jordan', 'Robin', 'Sam', 'Taylor']}
    buf.messages = [
        ('server', '16:19  Topic: Welcome! This is an offline demo conversation.'),
        ('message', '16:19  <Morgan> Hi Alex! Welcome to IRC.'),
        ('outgoing', '16:20  <Alex> Hello! Where can I find the commands?'),
        ('message', '16:20  <Casey> Press F1 or click Commands below. Ctrl+G also works.'),
        ('message', '16:21  <Robin> You can use the keyboard or the mouse. Right-click a conversation or a user to discover more actions.'),
        ('outgoing', '16:21  <Alex> Nice. IRC, discomplicated.'),
        ('server', '16:22  Sam joined #welcome'),
        ('message', '16:22  <Sam> Good evening, everyone!'),
    ]
    app.buffer('#development').unread = 3
    app.buffer('Morgan').mentioned = True
    app.draw()
    # Capture actual cells, not a separately composed screenshot layout.
    rows = []
    for y in range(28):
        text = screen.instr(y, 0).decode('utf-8')
        attrs = [screen.inch(y, x) & curses.A_ATTRIBUTES for x in range(116)]
        rows.append((text, attrs))
    Path(destination).write_text(json.dumps(rows))


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--capture':
        curses.wrapper(lambda screen: capture(screen, sys.argv[2]))
        return
    from PIL import Image, ImageDraw, ImageFont
    assets = ROOT/'assets'
    for size in (16, 24, 32, 48, 64, 128, 256, 512):
        subprocess.run(['inkscape', str(assets/'irdisc.svg'), f'--export-width={size}', f'--export-height={size}', '--export-filename='+str(assets/f'irdisc-{size}.png')], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    with tempfile.TemporaryDirectory() as directory:
        dest = str(Path(directory)/'cells.json')
        pid, fd = os.forkpty()
        if pid == 0:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack('HHHH', 28, 116, 0, 0))
            os.environ['TERM'] = 'xterm-256color'
            os.execv(sys.executable, [sys.executable, __file__, '--capture', dest])
        try:
            while os.read(fd, 65536):
                pass
        except OSError:
            pass
        _, status = os.waitpid(pid, 0)
        if status:
            raise RuntimeError('Curses screenshot capture failed')
        rows = json.loads(Path(dest).read_text())
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', 16)
    image = Image.new('RGB', (1180, 588), '#141b24')
    draw = ImageDraw.Draw(image)
    colors = {3:'#5fd7ff', 4:'#87d787', 5:'#d7af87', 6:'#ff87ff', 7:'#af87ff', 8:'#87d7ff'}
    for y, (text, attrs) in enumerate(rows):
        for x, char in enumerate(text):
            if x >= 116:
                break
            attr = attrs[x]
            fg = colors.get((attr & curses.A_COLOR) >> 8, '#d2dbe5')
            if attr & curses.A_DIM:
                fg = '#8293a7'
            if attr & curses.A_REVERSE:
                draw.rectangle((10+x*10, 10+y*20, 20+x*10, 30+y*20), fill='#a9dcd3')
                fg = '#142329'
            draw.text((10+x*10, 10+y*20), char, font=font, fill=fg)
    image.save(assets/'screenshot.png')
    sheet = Image.new('RGB', (480, 180), 'white')
    draw = ImageDraw.Draw(sheet)
    draw.rectangle((240, 0, 480, 180), fill='#141b24')
    for base in (0, 240):
        for i, size in enumerate((16, 24, 32, 48)):
            icon = Image.open(assets/f'irdisc-{size}.png').convert('RGBA')
            sheet.paste(icon, (base+10+i*55, 30), icon)
        draw.text((base+10, 110), '16 / 24 / 32 / 48 px', fill='#808080')
    sheet.save(assets/'icon-check.png')


if __name__ == '__main__':
    main()
