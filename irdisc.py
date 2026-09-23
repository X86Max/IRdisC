#!/usr/bin/env python3
"""IRdisC v0.1.1 — a deliberately small, beginner-friendly IRC terminal client."""

from __future__ import annotations

import curses
import base64
import queue
import re
import socket
import ssl
import threading
import time
from dataclasses import dataclass

DEFAULT_HOST = "irc.oftc.net"
DEFAULT_PORT = 6697
MAX_MESSAGES = 400


@dataclass
class Event:
    kind: str
    text: str


def connection_error_message(exc):
    if isinstance(exc, socket.gaierror):
        return 'DNS lookup failed. Check Server and your network/DNS connection.'
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return 'Connection timed out. Check Server, Port, TLS and network access.'
    if isinstance(exc, ConnectionRefusedError):
        return 'Connection refused. Check Server and Port; the service may be unavailable.'
    if isinstance(exc, ssl.SSLError):
        return 'TLS handshake/certificate failed. Check Server, TLS, Port and system clock. Certificate verification remains enabled.'
    return 'Connection failed or was lost. Check network access and connection settings.'


def parse_irc_line(line: str) -> tuple[str, list[str], str]:
    """Return (command, params, trailing) from one IRC protocol line."""
    if line.startswith(":"):
        _, _, line = line.partition(" ")
    head, separator, trailing = line.partition(" :")
    parts = head.split()
    return (parts[0].upper() if parts else "", parts[1:], trailing if separator else "")


class IRCClient:
    def __init__(self, host: str, port: int, nick: str, events: queue.Queue[Event],
                 *, tls: bool = True, username: str = "", sasl_account: str = "",
                 sasl_password: str = "", auth_method: str | None = None):
        self.host = host
        self.port = port
        self.nick = nick
        self.events = events
        self.tls = tls
        self.username = username or nick
        self.sasl_account = sasl_account
        self.sasl_password = sasl_password
        self.auth_method = auth_method or ('sasl' if sasl_account else 'none')
        self.cap_ended = False
        self.capabilities: set[str] = set()
        self.sasl_mechanisms: str | None = None
        self.sock: socket.socket | None = None
        self.connected = False
        self.stop_requested = threading.Event()
        self.send_lock = threading.Lock()
        self.thread: threading.Thread | None = None

    def connect(self) -> None:
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        try:
            raw = socket.create_connection((self.host, self.port), timeout=15)
            self.sock = raw
            if self.stop_requested.is_set():
                return
            if self.tls:
                context = ssl.create_default_context()
                self.sock = context.wrap_socket(raw, server_hostname=self.host)
            else:
                self.sock = raw
            if self.stop_requested.is_set():
                return
            # The connection timeout is only for establishing TLS. IRC is a
            # long-lived connection and can legitimately be quiet for hours.
            self.sock.settimeout(None)
            self.connected = True
            security = "TLS" if self.tls else "unencrypted"
            self.events.put(Event("status", f"Connected to {self.host}:{self.port} ({security})"))
            self.send("CAP LS 302")
            self.send(f"NICK {self.nick}")
            self.send(f"USER {self.username} 0 * :{self.nick}")
            buffer = b""
            while not self.stop_requested.is_set():
                data = self.sock.recv(4096)
                if not data:
                    break
                buffer += data
                if len(buffer) > 65536:
                    raise OSError("Server sent an oversized line")
                while b"\r\n" in buffer:
                    line, buffer = buffer.split(b"\r\n", 1)
                    self._handle(line.decode("utf-8", errors="replace"))
        except OSError as exc:
            if not self.stop_requested.is_set():
                self.events.put(Event("connection_error", connection_error_message(exc)))
        finally:
            self.connected = False
            if self.sock:
                try:
                    self.sock.close()
                except OSError:
                    pass
            self.sock = None
            self.events.put(Event("status", "Disconnected"))

    def _handle(self, line: str) -> None:
        self.events.put(Event("wire", line))
        parsed = line.partition(" ")[2] if line.startswith("@") else line
        command, params, trailing = parse_irc_line(parsed)
        if command == "PING":
            self.send(f"PONG :{trailing or (params[0] if params else '')}")
        elif command == "CAP" and len(params) >= 2:
            subcommand = params[1].upper()
            capabilities = trailing.split()
            if subcommand == "LS":
                self.capabilities.update(cap.split("=", 1)[0].lstrip("-~") for cap in capabilities)
                for cap in capabilities:
                    if cap.lstrip('-~').startswith('sasl='):
                        self.sasl_mechanisms = cap.split('=', 1)[1]
                if params[-1] == "*":
                    return
                if (self.auth_method == 'sasl' and self.sasl_account and self.sasl_password
                        and 'sasl' in self.capabilities
                        and (self.sasl_mechanisms is None or 'PLAIN' in self.sasl_mechanisms.upper().split(','))):
                    self.send("CAP REQ :sasl")
                else:
                    if self.auth_method == 'sasl':
                        self.events.put(Event("auth_error", "SASL is unavailable on this server."))
                    self._end_cap()
            elif subcommand == "ACK" and any(cap.split("=", 1)[0].lstrip("~") == "sasl" for cap in capabilities):
                self.send("AUTHENTICATE PLAIN")
            elif subcommand == "ACK" and any(cap.split("=", 1)[0].lstrip("~") == "-sasl" for cap in capabilities):
                self.events.put(Event("auth_error", "SASL is unavailable on this server (capability removed)."))
                self._end_cap()
            elif subcommand == "NAK":
                self.events.put(Event("auth_error", "SASL is unavailable on this server (capability rejected)."))
                self._end_cap()
        elif command == "AUTHENTICATE" and params and params[0] == "+":
            plain = f"\0{self.sasl_account}\0{self.sasl_password}".encode("utf-8")
            encoded = base64.b64encode(plain).decode("ascii")
            for start in range(0, len(encoded), 400):
                self.send("AUTHENTICATE " + encoded[start:start + 400])
            if len(encoded) % 400 == 0:
                self.send("AUTHENTICATE +")
        elif command == "903":
            self.events.put(Event("auth", "SASL authentication succeeded."))
            self._end_cap()
        elif command in {"904", "905", "906", "907"}:
            self.events.put(Event("auth_error", "SASL authentication failed. Review the account and password in /connection."))
            self._end_cap()
        # Protocol state is interpreted by the UI on its own thread.

    def _end_cap(self) -> None:
        if not self.cap_ended:
            self.cap_ended = True
            self.send("CAP END")

    def send(self, line: str) -> bool:
        if any(c in line for c in '\r\n\x00') or len(line.encode('utf-8')) > 510:
            self.events.put(Event('error', 'Message rejected: too long or contains control characters.'))
            return False
        if not self.sock or not self.connected:
            return False
        try:
            with self.send_lock:
                self.sock.sendall((line + "\r\n").encode("utf-8"))
            return True
        except OSError as exc:
            self.events.put(Event("error", f"Send error: {exc}"))
            return False

    def close(self, message: str = "Leaving") -> None:
        self.stop_requested.set()
        if self.connected:
            self.send(f"QUIT :{message}")
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


class App:
    def __init__(self, screen: curses.window):
        self.screen = screen
        self.events: queue.Queue[Event] = queue.Queue()
        self.client: IRCClient | None = None
        self.channel = ""
        self.nick = ""
        self.messages: list[tuple[str, str]] = []
        self.input_text = ""
        self.status = "Not connected"
        self.running = True

    def add_message(self, kind: str, text: str) -> None:
        stamp = time.strftime("%H:%M")
        self.messages.append((kind, f"{stamp}  {text}"))
        self.messages = self.messages[-MAX_MESSAGES:]

    def setup(self) -> None:
        self.screen.timeout(-1)
        curses.echo()
        self.screen.clear()
        self.screen.addstr(1, 2, "IRdisC", curses.A_BOLD)
        self.screen.addstr(2, 2, "IRC, discomplicated.")
        self.screen.addstr(4, 2, f"Network: OFTC ({DEFAULT_HOST}:{DEFAULT_PORT}, TLS)")
        self.screen.addstr(6, 2, "Nickname: ")
        while True:
            self.screen.move(6, 12)
            self.screen.clrtoeol()
            self.nick = self.screen.getstr(6, 12, 30).decode("utf-8", "replace").strip()
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,29}", self.nick):
                break
            self.screen.addstr(9, 2, "Enter a nick: start with a letter; no spaces.")
        self.screen.move(9, 0)
        self.screen.clrtoeol()
        self.screen.addstr(7, 2, f"Channel [{self.channel}]: ")
        while True:
            column = 2 + len(f"Channel [{self.channel}]: ")
            self.screen.move(7, column)
            self.screen.clrtoeol()
            chosen = self.screen.getstr(7, column, 30).decode("utf-8", "replace").strip()
            candidate = chosen if chosen.startswith("#") else f"#{chosen}"
            if not chosen or (len(candidate) > 1 and not any(c.isspace() or c in ',:\x00\x07' for c in candidate)):
                break
            self.screen.addstr(9, 2, "Enter one channel, without spaces or commas.")
        if chosen:
            self.channel = chosen if chosen.startswith("#") else f"#{chosen}"
        curses.noecho()
        self.screen.move(9, 0)
        self.screen.clrtoeol()
        self.screen.addstr(9, 2, f"Nick: {self.nick}")
        self.screen.addstr(10, 2, f"Channel: {self.channel}")
        self.screen.addstr(12, 2, "Connect? Press Y to connect, any other key to cancel.")
        self.screen.refresh()
        if self.screen.get_wch() not in ("y", "Y"):
            self.running = False
            return
        self.client = IRCClient(DEFAULT_HOST, DEFAULT_PORT, self.nick, self.events)
        self.client.connect()
        self.add_message("server", "Connecting… join will happen after the welcome message.")

    def process_events(self) -> None:
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                return
            if event.kind == "status":
                self.status = event.text
                self.add_message("server", event.text)
            elif event.kind == "welcome":
                self.add_message("server", event.text)
                if self.client and self.channel:
                    self.client.send(f"JOIN {self.channel}")
                    self.status = f"Connected as {self.client.nick} · joining {self.channel}…"
            else:
                self.add_message(event.kind, event.text)

    def draw(self) -> None:
        height, width = self.screen.getmaxyx()
        self.screen.erase()
        if height < 8 or width < 60:
            self.screen.addstr(0, 0, "Please resize terminal to at least 60×8.")
            self.screen.refresh()
            return
        title = f" IRdisC  |  {self.channel} "
        self.screen.addnstr(0, 0, title.ljust(width - 1), width - 1, curses.A_REVERSE)
        self.screen.addnstr(1, 1, self.status, width - 2, curses.A_DIM)
        message_height = height - 4
        visible = self.messages[-message_height:]
        for row, (kind, text) in enumerate(visible, start=2):
            color = curses.A_NORMAL
            if kind == "error":
                color = curses.A_BOLD
            elif kind in {"server", "status"}:
                color = curses.A_DIM
            self.screen.addnstr(row, 1, text, width - 2, color)
        self.screen.hline(height - 2, 0, curses.ACS_HLINE, width)
        self.screen.addnstr(height - 1, 1, "> " + self.input_text, width - 3)
        self.screen.move(height - 1, min(width - 2, 3 + len(self.input_text)))
        self.screen.refresh()

    def submit(self) -> None:
        text = self.input_text.strip()
        self.input_text = ""
        if not text:
            return
        if text.startswith("/"):
            self.command(text)
            return
        if not self.client or not self.client.connected:
            self.add_message("error", "Not connected yet.")
            return
        self.client.send(f"PRIVMSG {self.channel} :{text}")
        self.add_message("message", f"<{self.client.nick}> {text}")

    def command(self, text: str) -> None:
        name, _, arg = text[1:].partition(" ")
        name = name.lower()
        arg = arg.strip()
        if name == "help":
            self.add_message("server", "Commands: /join #channel, /part [message], /nick name, /quit [message], /help")
        elif name == "join" and arg and self.client:
            channel = arg if arg.startswith("#") else f"#{arg}"
            self.client.send(f"JOIN {channel}")
            self.channel = channel
            self.add_message("server", f"Joining {channel}…")
        elif name == "part" and self.client:
            self.client.send(f"PART {self.channel} :{arg or 'Leaving'}")
            self.add_message("server", f"Left {self.channel}")
        elif name == "nick" and arg and self.client:
            self.client.send(f"NICK {arg}")
        elif name == "quit":
            if self.client:
                self.client.close(arg or "Leaving")
            self.running = False
        else:
            self.add_message("error", "Unknown or incomplete command. Try /help.")

    def run(self) -> None:
        curses.curs_set(1)
        self.setup()
        self.screen.timeout(100)
        while self.running:
            self.process_events()
            self.draw()
            try:
                key = self.screen.get_wch()
            except curses.error:
                continue
            if key == curses.KEY_RESIZE:
                continue
            if key in ("\n", "\r"):
                self.submit()
            elif key in ("\x7f", "\b") or key == curses.KEY_BACKSPACE:
                self.input_text = self.input_text[:-1]
            elif key == "\x03":
                self.command("/quit")
            elif isinstance(key, str) and key.isprintable():
                self.input_text += key
        if self.client:
            self.client.close()


def main() -> None:
    import argparse
    import sys
    parser = argparse.ArgumentParser(description='⇹ IRdisC — IRC, discomplicated.')
    parser.add_argument('--version', action='version', version='IRdisC 0.1.1')
    parser.parse_args()
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.exit(2, 'IRdisC needs an interactive terminal. Use --help for usage.\n')
    from terminal_ui import ChatApp
    from release_ui import TerminalTitle
    try:
        with TerminalTitle() as title:
            curses.wrapper(lambda screen: ChatApp(screen, title=title).run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
