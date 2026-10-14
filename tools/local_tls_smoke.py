"""Verify local TLS ownership/shutdown with a verified synthetic certificate.

Uses the existing openssl executable to create an ephemeral localhost fixture.
No IRC network, user configuration, package installation or release is involved.
Exit 77 means the optional openssl fixture generator is unavailable.
"""
import json
import queue
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

from irdisc import IRCClient


def scenario(server_context, client_context, *, blocked_writer):
    raw_client, raw_peer = socket.socketpair()
    raw_client.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
    registered, finish = threading.Event(), threading.Event()
    errors = []
    progress = [0]
    client = IRCClient('localhost', 6697, 'Tester', queue.Queue())
    writer = None

    def peer():
        try:
            with server_context.wrap_socket(raw_peer, server_side=True) as connection:
                connection.settimeout(3)
                data = b''
                while b'USER Tester 0 * :Tester\r\n' not in data:
                    chunk = connection.recv(4096)
                    if not chunk:
                        raise AssertionError('Client closed before registration')
                    data += chunk
                registered.set()
                # Deliberately stop reading, for both the quiet-reader case
                # and the case where the client's write buffer is filled.
                if not finish.wait(5):
                    raise AssertionError('TLS fixture was not released')
        except BaseException as exc:
            errors.append(repr(exc))
            registered.set()

    def send_until_blocked():
        try:
            while not client.stop_requested.is_set():
                if not client.send('PRIVMSG #test :' + 'x' * 450):
                    break
                progress[0] += 1
        except BaseException as exc:
            errors.append(repr(exc))

    server = threading.Thread(target=peer, daemon=True)
    server.start()
    try:
        with patch('irdisc.socket.create_connection', return_value=raw_client), patch('irdisc.ssl.create_default_context', return_value=client_context):
            client.connect()
            assert registered.wait(3), 'TLS registration timed out'
            assert not errors, errors
            assert client.connected, 'Verified TLS socket was not published'
            if blocked_writer:
                writer = threading.Thread(target=send_until_blocked, daemon=True)
                writer.start()
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    previous = progress[0]
                    time.sleep(.2)
                    if previous > 0 and previous == progress[0] and writer.is_alive():
                        break
                else:
                    raise AssertionError('No blocked TLS writer was observed')
            started = time.monotonic()
            client.close('local TLS test')
            elapsed = time.monotonic() - started
            client.thread.join(2)
            if writer:
                writer.join(2)
            assert elapsed < 1.5, 'Close exceeded its bounded graceful-write allowance'
            assert not client.thread.is_alive(), 'TLS reader did not exit'
            assert not writer or not writer.is_alive(), 'TLS writer did not exit'
            assert client.sock is None and not client.connected
            assert not errors, errors
            assert not any(e.kind == 'connection_error' for e in client.events.queue)
            return {'scenario': 'blocked writer' if blocked_writer else 'blocked reader',
                    'successful_sends': progress[0], 'close_seconds': round(elapsed, 6),
                    'reader_exited': True, 'writer_exited': writer is None or not writer.is_alive()}
    finally:
        client.close()
        finish.set()
        server.join(2)
        if client.thread:
            client.thread.join(2)
        if writer:
            writer.join(2)
        raw_client.close()
        raw_peer.close()
        assert not server.is_alive(), 'TLS peer did not exit'
        assert not errors, errors


def main():
    openssl = shutil.which('openssl')
    if not openssl:
        print('SKIP: openssl is unavailable; no dependencies were installed')
        return 77
    with tempfile.TemporaryDirectory(prefix='irdisc-tls-') as directory:
        cert, key = Path(directory) / 'localhost.crt', Path(directory) / 'localhost.key'
        subprocess.run([openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(key), '-out', str(cert), '-days', '1',
                        '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost'],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server.load_cert_chain(cert, key)
        client = ssl.create_default_context(cafile=str(cert))
        results = [scenario(server, client, blocked_writer=False),
                   scenario(server, client, blocked_writer=True)]
        print('PASS: 2 verified local TLS shutdown scenarios')
        print(json.dumps(results, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
