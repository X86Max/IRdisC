# Changelog

## v0.1.2 — Security, protocol correctness and stability

- Protect recognized Services credentials in prompts, paste previews, echoes,
  history, saved drafts and contextual replies, including leading whitespace,
  IRC formatting and numeric middle parameters. Reject credential-bearing actions.
- Keep fragmented, delayed and oversized bracketed pastes behind a shared input
  boundary across chat and dialogs, preventing unreviewed command execution.
- Handle SASL numeric 902 and both challenge parameter forms; prevent credential
  responses after negotiation ends and keep autojoin paused after failure.
- Synchronize socket publication and detachment, interrupt blocked I/O from
  another thread, and separate private messages to the nickname `server` from
  the reserved in-memory status buffer.
- Preserve initial preferences with empty connection fields and isolate tests
  from user configuration and logs.
- Expand deterministic coverage from 93 to 158 tests. Independent security
  review: APPROVE WITH RESERVATIONS. Maintainer-reported OFTC manual QA covered
  TLS, NickServ, contextual Services replies, masking, reconnect and messaging.
- Keep R7/R8, partial IRCv3 CAP support and unverified real-network SASL explicit
  in [RELEASE_NOTES.md](RELEASE_NOTES.md) and [QA.md](QA.md). No new runtime dependencies or feature expansion.

**Published:** [v0.1.2](https://github.com/X86Max/IRdisC/releases/tag/v0.1.2) — stable maintenance release.

## v0.1.1 — Authentication and IRC Services UX

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
