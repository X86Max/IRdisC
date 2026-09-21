"""Exercise clean startup and global help in a real Linux pseudoterminal.

Usage: python3 tools/terminal_smoke.py /absolute/path/to/installed/irdisc
Never connects to a network or uses the operator's configuration.
"""
import fcntl
import os
import select
import signal
import struct
import sys
import tempfile
import termios
import time


def main():
    executable = os.path.abspath(sys.argv[1])
    with tempfile.TemporaryDirectory() as directory:
        pid, fd = os.forkpty()
        if pid == 0:
            os.chdir(directory)
            os.environ.update(TERM='xterm-256color', XDG_CONFIG_HOME=directory+'/config',
                              XDG_STATE_HOME=directory+'/state')
            os.environ.pop('PYTHONPATH', None)
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack('HHHH', 28, 116, 0, 0))
            os.execv(executable, [executable])
        output = bytearray()
        transcript = bytearray()

        def expect(text):
            end = time.monotonic()+5
            while text.encode() not in output:
                if time.monotonic() >= end:
                    raise AssertionError('Terminal did not show '+repr(text))
                if select.select([fd], [], [], .2)[0]:
                    chunk = os.read(fd, 65536)
                    output.extend(chunk)
                    transcript.extend(chunk)
            output.clear()

        def send(text):
            os.write(fd, text.encode())

        try:
            expect('Choose network or type a name')
            send('\r')
            expect('Libera.Chat')
            send('\x1b')
            expect('Optional: #channel')
            send('\x07')
            expect('/connect')
            send('\x1b')
            expect('Optional: #channel')
            send('\x1b')
            expect('Welcome!')
            send('/help\r')
            expect('/connect')
            fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', 12, 60, 0, 0))
            os.kill(pid, signal.SIGWINCH)
            send('\x1b')
            expect('F1 Commands')
            send('/quit\r')
            end = time.monotonic()+5
            while time.monotonic() < end:
                child, status = os.waitpid(pid, os.WNOHANG)
                if child:
                    assert status == 0, status
                    try:
                        while select.select([fd], [], [], 0)[0]:
                            chunk = os.read(fd, 65536)
                            if not chunk:
                                break
                            transcript.extend(chunk)
                    except OSError:
                        pass
                    assert '\x1b]2;⇹ IRdisC\x1b\\'.encode() in transcript
                    assert b'\x1b[22;2t' in transcript and b'\x1b[23;2t' in transcript
                    print('PASS: isolated TUI, startup, picker, help, resize, quit, title set/restore sequences')
                    return
                if select.select([fd], [], [], .1)[0]:
                    try:
                        transcript.extend(os.read(fd, 65536))
                    except OSError:
                        pass
            raise AssertionError('Client did not exit')
        finally:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            os.close(fd)


if __name__ == '__main__':
    main()
