"""B1 regression: capture real curses prompts before submitting synthetic credentials.

From the checkout: python3 tools/credential_prompt_smoke.py
The child has isolated HOME/XDG and a mocked client; it never opens a network socket.
"""
import curses
import fcntl
import os
import select
import signal
import struct
import sys
import tempfile
import termios
import time
from pathlib import Path


SECRET = 'b1-pty-synthetic-secret'
CASES = (
    ('#test', ' /msg NickServ IDENTIFY ' + SECRET),
    ('#test', '\t/msg\tNickServ\tIDENTIFY\t' + SECRET),
    ('#test', '\u00a0/msg\u00a0NickServ\u00a0IDENTIFY\u00a0' + SECRET),
    ('#test', ' \t\u00a0 /msg \tNickServ\t IDENTIFY \t' + SECRET),
    ('NickServ', ' /me IDENTIFY ' + SECRET),
    ('NickServ', '\t/me\tIDENTIFY\t' + SECRET),
    ('#test', ' /msg NickServ \x01ACTION IDENTIFY ' + SECRET + '\x01'),
    ('NickServ', '\u00a0\x01ACTION IDENTIFY ' + SECRET + '\x01'),
)


def child(ack_fd):
    from unittest.mock import MagicMock, patch
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from irdisc_settings import default_preferences
    from terminal_ui import ChatApp

    def render(screen):
        with patch('terminal_ui.load_preferences', side_effect=default_preferences):
            app = ChatApp(screen)
        app.client = MagicMock(nick='Tester', connected=True, sasl_password='')
        app.ready = True
        app.last_send = -1000
        app.receive(':Tester!u@h JOIN :#test')
        app.configure_theme()
        screen.timeout(100)
        for index, (active, text) in enumerate(CASES):
            app.input_text = ''
            app.switch(active)
            screen.clear()
            app.draw()
            os.write(ack_fd, f'READY {index}\n'.encode())
            deadline = time.monotonic() + 5
            while app.input_text != text:
                if time.monotonic() >= deadline:
                    raise AssertionError('Paste input did not arrive')
                try:
                    app.key(app.read_key(paste_to_chat=True), framed=True)
                except curses.error:
                    continue
                app.draw()
            assert app.cursor == len(text)
            app.client.send.assert_not_called()
            os.write(ack_fd, f'DRAWN {index}\n'.encode())
        assert not app.history
    curses.wrapper(render)
    os.close(ack_fd)


def main():
    with tempfile.TemporaryDirectory(prefix='irdisc-b1-pty-') as directory:
        ack_read, ack_write = os.pipe()
        os.set_inheritable(ack_write, True)
        pid, terminal = os.forkpty()
        if pid == 0:
            os.close(ack_read)
            os.environ.update(TERM='xterm-256color', HOME=directory + '/home',
                              XDG_CONFIG_HOME=directory + '/config', XDG_STATE_HOME=directory + '/state',
                              PYTHONDONTWRITEBYTECODE='1')
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack('HHHH', 25, 110, 0, 0))
            os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve()), '--child', str(ack_write)])
        os.close(ack_write)
        transcript, acknowledgements = bytearray(), bytearray()
        waited = False

        def capture():
            try:
                chunk = os.read(terminal, 65536)
            except OSError:
                return
            transcript.extend(chunk)
            assert len(transcript) < 1048576, 'Unexpected terminal output volume'

        def expect(marker):
            deadline = time.monotonic() + 5
            while marker.encode() not in acknowledgements:
                assert time.monotonic() < deadline, 'PTY checkpoint timed out'
                ready, _, _ = select.select([terminal, ack_read], [], [], .1)
                if terminal in ready:
                    capture()
                if ack_read in ready:
                    data = os.read(ack_read, 4096)
                    assert data, 'PTY child exited before its checkpoint'
                    acknowledgements.extend(data)
            while select.select([terminal], [], [], 0)[0]:
                # End-of-stream is also readable; only drain live output here.
                try:
                    data = os.read(terminal, 65536)
                except OSError:
                    break
                if not data:
                    break
                transcript.extend(data)

        try:
            for index, (_, text) in enumerate(CASES):
                expect(f'READY {index}\n')
                os.write(terminal, ('\x1b[200~' + text + '\x1b[201~').encode())
                expect(f'DRAWN {index}\n')
            _, status = os.waitpid(pid, 0)
            waited = True
            assert status == 0, 'PTY child failed'
            assert SECRET.encode() not in transcript, 'B1: synthetic credential appeared in pre-submission terminal output'
            assert b'IDENTIFY' in transcript, 'Credential command structure was not rendered'
            assert ('*' * len(SECRET)).encode() in transcript, 'Credential mask was not rendered'
            print(f'PASS: {len(CASES)} real PTY pre-submission prompts; synthetic plaintext absent; no sends')
            return 0
        finally:
            if not waited:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                os.waitpid(pid, 0)
            os.close(terminal)
            os.close(ack_read)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--child':
        child(int(sys.argv[2]))
    else:
        raise SystemExit(main())
