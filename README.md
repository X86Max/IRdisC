# ⇹ IRdisC

![IRdisC icon](assets/irdisc-64.png)

**IRC, discomplicated.**

**Current release: v0.1.1**

IRdisC is a lightweight IRC TUI that keeps the simplicity of a terminal and adds
conveniences usually found in graphical clients. Choose a network and nickname;
discover the rest through menus and built-in help.

![Chat, conversations and users](assets/screenshot.png)

*Current curses renderer with synthetic offline demo messages; no real private chat.*

## Features

- Multiple channels and private conversations on one active network.
- Keyboard and optional mouse; contextual menus on users and conversations.
- PMs, WHOIS and readable join/part/nick/topic/mode/kick events.
- Consistent nick colors, unread markers, mentions and new-message divider.
- Independent USERS scroll, wrapped messages/topics and resize reflow.
- Chat stays anchored when new messages arrive while reading history.
- Nick completion, input history, drafts and multiline paste review.
- Connection editor, saved profiles and controlled connect/disconnect/reconnect.
- Verified TLS and explicit SASL PLAIN or NickServ authentication, with a session-only password.
- Global grouped Commands screen, available in onboarding and chat.
- Optional bell with cooldown, local logs, three themes and confirmed URL opening.

## Installation

Requires **Python 3.11+**, standard-library `curses`, and a UTF-8 Linux terminal.
There are **no third-party runtime Python dependencies**. Minimum size is 50 × 10;
110 × 28 is comfortable. Sidebars appear at 90 columns and above.

Extract the source ZIP or tar.gz, open a terminal in its directory and run:

```bash
python3 irdisc.py
```

Keep all Python modules together. No installation is needed for this method.

To install the command in a virtual environment, from the source directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/irdisc
```

Source installation uses setuptools >=77, declared in pyproject.toml. If your
distribution packages Python venv separately, install that package first. Avoid
installing into the system Python. The release bundle also contains a built wheel:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --no-index dist/irdisc-0.1.1-py3-none-any.whl
.venv/bin/irdisc
```

The wheel commands run from the bundle directory. Check the version using
`python3 irdisc.py --version` or the installed `irdisc --version`.
`--help` works without opening the TUI.

## Quick start

1. Run IRdisC. First-use text fields are empty; placeholders are visual only.
2. Click Network or press Enter there: choose OFTC, Libera.Chat or Other / Custom.
3. Known networks fill Server, Port and TLS. Enter your own Nick.
4. Leave Channel empty or enter a channel you intend to join.
5. Select Save & Connect. Use `/join #channel` to join another channel.

Custom networks allow manual Network name, Server, Port and TLS settings.
Server takes a hostname or bare IP, not a URL or `host:port`. TLS starts enabled
as a safe default. No random nick or public channel is chosen for you.

**Save** only persists the profile. **Cancel / Esc** discards all editor edits;
on first launch it leaves the app disconnected. Nothing connects on startup
without your action, including when a saved profile exists.

The Commands label stays in the footer. IRdisC chooses **F1** if terminfo advertises
it, otherwise **Ctrl+G**. Ctrl+G always works as an alternative; the label is clickable.
A terminal/desktop may intercept F1 without notifying the app; IRdisC cannot detect
that external interception. Use Ctrl+G or click Commands in that case.

Small connected windows offer a maximize tip. Esc or resize dismisses it.
IRdisC never forces fullscreen or changes your window size.

While running in a recognized compatible terminal, the window/tab title is
`⇹ IRdisC`, or `⇹ IRdisC — Network` after connecting. Only the chosen network
label is used, never the working directory, command, system user or server host.
On exit (including Ctrl+C), IRdisC requests restoration of the previous title.
This is best-effort: terminal settings/multiplexers can override it, and unsupported
or unknown terminals are left alone. No GNOME-specific integration is used.
Implementation follows [xterm OSC and title-stack sequences](https://invisible-island.net/xterm/ctlseqs/ctlseqs.html).

## Controls

| Context | Control | Action |
| --- | --- | --- |
| Startup/chat | F1 when available, Ctrl+G, click Commands | Grouped command help |
| Commands | Up/Down, PgUp/PgDn, wheel | Scroll |
| Commands | Esc, Enter, Q, click Close | Close help |
| Editor | Tab / Shift+Tab or Down / Up | Next / previous field or action |
| Editor | Enter on Network; click Network | Network dropdown |
| Editor | Type Network name, then Tab | Manual network configuration |
| Editor | Space on TLS; click TLS | Toggle TLS |
| Editor | Ctrl+U | Clear field |
| Editor | F4 | Load saved profile matching Network name into editor draft |
| Editor | Esc / Cancel | Discard edits |
| Chat | Click conversation | Switch conversation |
| Chat | Click user | Open PM without sending |
| Chat | Right-click conversation/user | Context menu |
| Chat | F2 | Numbered Actions menu |
| Chat | F3 / F4 | Conversation menu / user picker |
| Chat | F5 | Links list; confirmation before opening |
| Chat | F6 | Next conversation |
| Chat | F7 / click USERS heading | Focus independent user list |
| Chat | F8 / click topic | Full wrapped topic |
| Input | Tab | Nick completion; colon at start of input |
| Input | Up/Down | Input history / restore draft |
| Input | Left/Right, Home/End, Delete/Backspace | Edit draft |
| Chat | PgUp/PgDn; Ctrl+L | Scroll; return to latest |
| USERS focused | Up/Down, PgUp/PgDn; Esc | Scroll USERS; return to chat |
| Mouse wheel | Over USERS or chat | Scroll only that panel |
| Terminal | Shift + mouse drag | Select terminal text for copying (terminal-dependent) |

Right-click may be intercepted by your terminal; F3/F4 are alternatives.
Context-menu arrows/Enter select and Esc dismisses. F2 uses displayed number keys.

## Commands

`/help` opens the full grouped reference, with syntax, descriptions and related keys.

| Command | Purpose |
| --- | --- |
| `/connection` or `/settings edit` | Edit connection |
| `/settings`, `/profiles` | Show non-secret settings / saved profile names |
| `/connect` | Connect saved profile |
| `/disconnect` | Disconnect, keep app open, stop retries |
| `/reconnect` | Close session then connect saved profile |
| `/reconnect on\|off\|now\|cancel` | Control retries |
| `/join #channel` | Join channel |
| `/part [reason]` | Leave, keep local history |
| `/close` | Close PM or a channel already left |
| `/msg Nick message`, `/query Nick` | Send PM / open PM without sending |
| `/whois Nick`, `/nick Nick` | Inspect user / change nick |
| `/me action`, `/away [reason]`, `/back` | Action and away status |
| `/topic [text]` | Read/change topic |
| `/ignore Nick`, `/unignore Nick` | Session-only ignore list |
| `/users words\|clear` | Filter/reset USERS |
| `/switch name`, `/search words` | Switch chat / search in-memory history |
| `/clear` | Confirm clearing memory history, not log files |
| `/links` | List full HTTP(S) URLs |
| `/theme dark\|light\|mono` | Appearance |
| `/log on\|off` | Local logging |
| `/notify on\|off` | Terminal bell |
| `/help` | Commands screen |
| `/quit [reason]` | Disconnect and exit |

**Leave** sends PART. **Close** removes a conversation from the UI without sending
PART; joined channels must be left first. Rejoin is in the channel context menu.
Clear history asks for confirmation.

## Configuration and privacy

Preferences live in `~/.config/irdisc/config.json`, or
`$XDG_CONFIG_HOME/irdisc/config.json` when set, with private file permissions.
They include network/server/port/TLS, nick, optional channel, authentication method and SASL account,
named profiles, theme, logging, notifications and automatic reconnect preferences.

Choose **None**, **SASL PLAIN** or **NickServ** in the connection editor (Space
cycles options). SASL PLAIN needs an account and password, and works only when
the network advertises SASL PLAIN. NickServ sends `IDENTIFY` after IRC
registration using the current nickname; the client reports only that it sent
the request, since service success responses vary among networks. Both methods
require verified TLS. Passwords are masked in the editor, held in memory only
and **never saved in settings or logs**. Enter them again after restarting.
`/settings` shows the selected method without displaying a password. New profiles
default to None; older profiles with a SASL account retain SASL PLAIN.

`/msg NickServ` and `/msg ChanServ` show the service destination in the local
echo (for example, `/msg ChanServ INFO #irdisc`) and replies in
the conversation where the command was entered. A matching service reply is
routed there for up to 30 seconds; unrelated later notices return to server.
An actual service query remains a normal conversation. Manually entered service
credential arguments are masked in the local echo and while typing; complete
credential commands are omitted from input history. Prefer
the connection editor for NickServ identification.

Logs are off by default. `/log on` writes under `~/.local/state/irdisc/logs`, or
`$XDG_STATE_HOME/irdisc/logs`. Do not type secrets as ordinary messages: normal
messages can appear in input history and logs. Never commit profiles, passwords,
tokens or logs. TLS protects the client/server link; it is not end-to-end encryption.

Saving another Network name stores another profile. `/profiles` lists names;
type a saved name in the editor and press F4 to load its fields. Save & Connect
replaces the connection in order, without opening two active sessions.

## Recovering a connection

DNS, timeout, refusal, TLS and authentication errors have distinct guidance.
Use `/connection` or F2 → Connection settings, correct the fields and Save & Connect.
No restart or configuration-file deletion is needed. Validation appears beside
fields; runtime failure is labeled Connection error in the header.

SASL unavailable and SASL rejection have separate messages. Either condition
blocks automatic channel join but may leave the connection open
without authentication. Review settings before reconnecting. Automatic reconnect
is off by default; when enabled it uses increasing delays and can be cancelled.

## Notifications, links and clipboard

Notifications default off. `/notify on` enables bell for incoming mentions, PMs
and unexpected disconnects, with a global five-second cooldown. No bell for
normal channel chatter, your messages, joins/parts or intentional disconnects.
Actual sound/visual bell depends on terminal preferences; mono changes only appearance.

HTTP(S) URLs require confirmation before opening; F5 shows the full URL even when
wrapped. Copy uses an existing `wl-copy`, `xclip`, `xsel` or `pbcopy`. These helpers
are optional and never installed automatically; missing helpers fall back to
displaying the value for manual selection/copy.

When IRdisC mouse handling is active, many terminals allow text selection with
Shift + mouse drag. The terminal's normal copy shortcut can then be used.
This behavior is terminal-dependent.

## Supported platforms

| Platform | Status |
| --- | --- |
| Linux | Tested here: automated suite, loopback IRC fixtures, real curses pseudoterminal and isolated wheel install on Python 3.12. Earlier builds were used on Debian. See QA.md for terminal-specific follow-up. |
| macOS / other Unix with curses | Expected to be portable; not tested for this release. |
| Native Windows | Unsupported in this release; standard Windows Python lacks curses. |
| WSL | Not tested for this release. |

Python 3.11 is the declared minimum; execution tests here used 3.12. This is not
a claim of testing all supported Python versions or terminal emulators.

## Known limitations

- One active network; multiple saved profiles.
- History stays in memory, capped at 400 messages per conversation, and is not restored.
- Partial IRCv3, SASL PLAIN and basic NickServ identification, no DCC or server history replay.
- Local echo means socket acceptance, not confirmed remote delivery.
- Below 50 × 10, a resize prompt; below 90 columns, sidebars hide.
- Complex emoji widths, fonts, colors, bell, mouse and function keys vary by terminal.
- This first release does not implement every feature of mature IRC clients.

## Project philosophy

Terminal-first, simple and lightweight. Mouse is optional; keyboard access remains
complete. Reduce the barrier for new IRC users without a heavy GUI or hiding the
commands experienced users already know.

## Contributing and bug reports

Open an issue in the project repository for bugs or focused suggestions. Include
OS, terminal, Python and IRdisC versions, reproduction steps, expected/actual behavior,
and a redacted screenshot/log if useful. Never attach secrets or private messages.
Pull requests should explain the change and include relevant regression checks.
See [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
python3 -m unittest discover -v
```

See [QA.md](QA.md) for release validation. Asset generation uses developer-only
Pillow and Inkscape; neither is needed to run the client. Feature scope is frozen.

## License

MIT — [LICENSE](LICENSE), including documentation and icons.
See [CHANGELOG.md](CHANGELOG.md) and [release notes](RELEASE_NOTES.md).
