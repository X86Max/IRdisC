# ⇹ IRdisC v0.1.2

IRdisC v0.1.2 is a maintenance release focused on security, protocol correctness
and stability. It keeps the classic ⇹ identity, terminal interface and existing
feature scope. Requires Python 3.11+ and a curses-capable Linux terminal; no new
runtime dependencies or destructive configuration migration are introduced.

## Changes

- **Credential masking and Services privacy:** recognized NickServ/ChanServ
  credential arguments are masked before submission, including commands with
  leading spaces, tabs or nonbreaking spaces. Command structure remains visible.
  Paste previews and contextual replies use the same protection, with display
  cleanup before redaction and coverage of numeric middle parameters. Sensitive
  submissions clear history/draft remnants; credential-bearing `/me` and explicit
  CTCP ACTION requests are rejected before sending. Ordinary chat remains intact.
- **Bracketed paste and modal input:** shared framing protects chat and dialogs
  against fragmented start markers, delayed content and oversized pastes. A paste
  beginning in a dialog is discarded through its end marker; multiline chat paste
  still requires review. Unreviewed suffixes cannot become executable commands
  in the covered regressions.
- **SASL correctness:** numeric 902 follows the controlled authentication-failure
  path; both `AUTHENTICATE +` and `AUTHENTICATE :+` are accepted. Negotiation ends
  once, late challenges do not resend credentials, and failed authentication
  pauses autojoin. Unavailable capability and authentication failure remain
  distinct outcomes.
- **Connection lifecycle and state:** socket publication/detachment is synchronized
  and another thread can interrupt blocked I/O. Private messages to the legitimate
  nickname `server` use a separate in-memory conversation. Reconnect replaces the
  event queue so late events cannot enter the new session.
- **Configuration and regression coverage:** initial preferences round-trip with
  empty connection fields, without persisting passwords. Tests are isolated from
  default configuration/log directories. The suite now contains **158 tests**,
  up from the original 93, including security, protocol and credential-prompt
  regressions. Current validation results are recorded in [QA.md](QA.md).

## Review and manual QA

The maintainer reports an independent security verdict of **APPROVE WITH
RESERVATIONS**, followed by real-network OFTC checks of verified TLS, NickServ
IDENTIFY/STATUS, contextual ChanServ replies, credential masking, reconnection,
channel messages and private messages. These manual results are supplied by the
maintainer; release preparation does not repeat public-network connections.

OFTC's published [Services FAQ](https://www.oftc.net/FAQ/Services/#do-you-provide-sasl)
states that SASL is not currently provided. Real SASL authentication was therefore
not validated on OFTC; deterministic SASL tests passed. Neither the review nor
the tests establish that the application is vulnerability-free or fully
IRCv3-compliant. Historical audit evidence remains in AUDIT_REMEDIATION.md.

## Remaining limitations

- **R7 — log namespace:** status and the `@server` private conversation can share
  `server.log`, despite their separate in-memory buffers.
- **R8 — UI blocking:** synchronous, unbounded `sendall` can stall the UI. Local
  TLS checks demonstrate shutdown from another thread, not that a disconnect
  command on a blocked UI remains usable.
- **Partial IRCv3 CAP support:** colonless capability lists are not recognized;
  CAP NEW/DEL are ignored even though CAP 302 implies capability notifications.
  Tested multiline LS and SASL mechanism values do not establish complete CAP
  support. Real-network SASL remains unverified.
- **Contextual privacy:** proprietary authentication syntax, transformed echoes
  beyond tested normalization and credentials posted as ordinary chat are not
  universally detectable. Manual Services commands in an unencrypted `None`
  session are not separately TLS-gated; configured SASL/NickServ require TLS.
- **Paste recovery:** a missing end marker quarantines subsequent input until
  the marker arrives or the application restarts. Ambiguous escape prefixes can
  wait for more input; emulator coverage is limited.
- NickServ identification precedes autojoin without waiting for confirmation.
  Silent transport loss has no heartbeat detection; connection/handshake
  cancellation waits for the underlying operation to finish or time out.
- Deferred NOTICE routing, local-search sends, nickname validation, keyed JOIN,
  quit-reason handling and pending NAMES state remain outside this release's fixes.
  CJK/emoji cursor width, the settings temporary-file permission window and the
  other deferred items in AUDIT_REMEDIATION.md also remain open.

## Preparation status

This candidate is prepared locally and is **not published**. The published
v0.1.1 tag and artifacts remain immutable. Packaging and publication require
explicit approval and a fresh output location that preserves existing artifacts.
See [QA.md](QA.md) for executed checks, platform limits and remaining acceptance.

# ⇹ IRdisC v0.1.1

This focused update makes authentication explicit in the connection editor:
None, SASL PLAIN or NickServ. SASL requires an account and password over
verified TLS; NickServ sends identification after server registration, with a
session-only password. The client distinguishes missing SASL support from
rejected authentication.

Explicit `/msg NickServ` and `/msg ChanServ` commands remain in the current
conversation with replies received in a short bounded window. Unsolicited
service notices remain in server status. Local echoes identify the service
destination; credential arguments are masked in the input and local echo and
excluded from logs and input history.

Requires Python 3.11+ and a curses-capable terminal. See README.md and QA.md
for installation, behavior, test coverage and live-network acceptance steps.

This is a local candidate. Publication, tags and releases are separate actions.
