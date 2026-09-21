# v0.1.0 release validation

Validation distinguishes automated checks from physical terminal/network behavior.
No public IRC channel is used by this test suite. Fixtures use fictional users.

## Automated checks

Run `python3 -m unittest discover -v` from a clean source extraction.
Result in this environment: **82 tests passed**.

| Area | Evidence |
| --- | --- |
| Empty first use, presets, Custom, Save & Connect, Cancel | tests/test_release.py and test_connection.py |
| Save transaction and no partial edits/password persistence | test_connection.py and test_settings_auth.py |
| Invalid configuration → DNS failure → correction → JOIN in same app | Loopback TCP fixture in test_connection.py |
| Connect/disconnect/reconnect, TLS/SASL failures, timeout/refusal | test_connection.py, test_protocol.py, test_settings_auth.py |
| Multiple conversations, PMs, membership and command errors | test_chat.py and test_ux.py |
| 281-user list, independent scroll, mouse after scroll, join/part anchors | test_layout.py |
| Visual-line chat scroll, long URLs/topics, resize and narrow layout | test_layout.py |
| Nick colors, context menus, unread, mention and bell cooldown | test_ux.py |
| Completion, input history, nick changes, PART/close/clear, modes/topic/kick, links | test_chat.py and test_ux.py |
| Commands modal scrolling, /help, shortcut selection and Ctrl+G fallback | test_release.py |
| Maximize hint dismissal on resize | test_release.py |
| Terminal title, network changes, unsupported output, exceptions, control-character sanitization | test_terminal_title.py |

## Render and package checks

- Real Linux curses renderer exercised in an xterm-256color pseudoterminal for the
  screenshot. Data is synthetic, and there is no remote connection.
- SVG exported to PNG at 16, 24, 32, 48, 64, 128, 256 and 512 pixels; small-size
  contact sheet inspected on light/dark backgrounds (assets/icon-check.png).
- Clean source allowlist excludes configurations, logs, caches, build directories
  and credentials. Test fixtures are retained as regression tests, not user profiles.
- Release contains source ZIP/tar.gz, wheel and SHA256SUMS. Wheel installation is
  checked in a fresh virtual environment without runtime dependency downloads.
- `tools/terminal_smoke.py` passed against the installed wheel from a temporary
  working directory with empty XDG paths: startup, dropdown, editor help, chat
  help, /help, real terminal resize and clean exit.
  Title save/set/restore escape sequences were also verified in its output;
  actual title restoration depends on the emulator's support.

## Scope and remaining manual acceptance

Tests ran on Linux/Python 3.12. No claim of a macOS, Windows, WSL, Python 3.11 or
multi-terminal validation matrix. Mock input tests do not prove all mouse/keyboard
behavior in every physical terminal. Before publishing, perform one short acceptance
session in the target Linux terminal:

1. Start with a temporary empty XDG_CONFIG_HOME/XDG_STATE_HOME. Review empty fields,
   mouse/keyboard dropdown, Custom, Save, Cancel and Save & Connect.
2. Connect to a chosen real network, enter an intended channel, disconnect/reconnect.
   Check certificate/authentication behavior against that network if using SASL.
3. Try mouse/right-click/wheel, completion/history, PM/WHOIS, large channel scrolling,
   context menus and Commands. F1 interception and terminal bell are emulator settings;
   verify Ctrl+G and clickable Commands as alternatives.
4. Resize/maximize/restore; confirm wrap, independent USERS scroll and readable small
   layout. Verify the tip disappears. Check links/clipboard with installed handlers.

These physical-terminal and live-network checks are **not marked passed** merely
because the automated suite passed. No automatic publication was performed.
