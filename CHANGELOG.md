# Changelog

## v0.1.1 — Authentication and IRC Services UX (release candidate)

- Select None, SASL PLAIN or NickServ in the connection editor. Passwords remain session-only.
- Distinguish unavailable SASL from rejected credentials; send NickServ identification after registration.
- Keep explicit NickServ/ChanServ interactions in their originating conversation for a bounded time.
- Hide manual service credential commands from transcripts, logs and input history.
- RC refinement: show the service destination in local command echoes and mask only
  credential arguments while typing; fresh profiles default to no authentication.

## v0.1.0 — First public release

- Terminal-first IRC client with the ⇹ identity and network selection onboarding.
- TLS, optional SASL PLAIN, editable saved profiles and connection recovery.
- Multiple conversations, PMs, WHOIS, nick colors, unread and mentions.
- Keyboard and mouse navigation, context menus, nick completion and input history.
- Independent USERS scrolling, wrapped chat/topic text and adaptive layout.
- Readable IRC events, safe URL confirmation and optional rate-limited bell.
- Global grouped Commands help, installation documentation and release assets.
- Short terminal title with active network and best-effort restoration on exit.

Prepared for publication; no publication date is asserted by this package.
