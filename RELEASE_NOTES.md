# ⇹ IRdisC v0.1.0

**IRC, discomplicated.**

The first public release of a lightweight terminal IRC client with conveniences
usually found in graphical clients. Choose a network and nickname, connect,
and discover commands from the persistent help shortcut.

Highlights: editable connections, TLS and optional SASL, multiple channels and
PMs, mouse menus, nick colors, unread/mentions, independent USERS scrolling,
word wrap, completion, input history and an optional terminal bell.

Requires Python 3.11+ and a curses-capable terminal. Linux is the tested platform.
Extract the source archive and run `python3 irdisc.py`; no runtime packages needed.
See README.md for virtual-environment installation, controls and limitations.

This is an early client: one active network, 400 messages per conversation in
memory, partial IRCv3 support. See QA.md for the exact scope of release checks.
Please include OS, terminal, Python/client version and reproduction steps in bugs.

## Maintainer publication steps

1. Review LICENSE (MIT), README and QA.md; complete terminal-specific manual checks.
2. Commit the clean source tree to the actual project repository.
3. Tag that reviewed commit `v0.1.0` and create a GitHub Release from the tag.
4. Use the text above as its description; attach source ZIP/tar.gz, wheel and
   SHA256SUMS from the release bundle. Do not upload config files or logs.

No repository URL or published package is assumed. Publication is a separate action.
