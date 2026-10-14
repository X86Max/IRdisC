# v0.1.2 release validation and publication record

Preparation validation date: 2026-10-14. Environment: Linux, Python 3.13.5.

**Publication status:** [v0.1.2](https://github.com/X86Max/IRdisC/releases/tag/v0.1.2)
was published as a stable GitHub release. The release commit and annotated tag
refer to `2e6dd3f41dd0f090b76eff1860709c579a8b59ea`.
Five published assets were downloaded and verified against SHA-256 checksums.
The previously published v0.1.1 tag and artifacts were preserved.

The original pre-publication validation evidence below is retained as a dated
historical record, not a description of the current Git working tree. The
complete v0.1.1 validation record below the separator is also preserved.

## Post-publication verification

The following checks were reported as completed during the packaging and
publication workflow, after the preparation-only validation recorded below:

| Check | Result |
| --- | --- |
| Published release | Stable GitHub release `v0.1.2` |
| Release commit | `2e6dd3f41dd0f090b76eff1860709c579a8b59ea` |
| Distribution files | Release ZIP, source ZIP, source tar.gz, wheel, `SHA256SUMS` |
| Source archive installation | Passed in an isolated virtual environment |
| Wheel installation | Passed in a separate isolated virtual environment |
| Package/archive integrity | Validated during staging and after upload |
| Published assets | Five assets downloaded and SHA-256 verified |
| Previous v0.1.1 release | Tag, notes and artifacts preserved |

These results supplement the **158/158 automated tests**, local TLS checks,
terminal smoke and credential-prompt checks described below. They do not imply
that Python 3.11 runtime, other operating systems, all terminal emulators or
real-network SASL authentication were tested.

## Historical preparation record (before publication)

The sections until the next horizontal rule describe the **pre-publication
snapshot** on 2026-10-14. Statements about uncommitted changes, absent packages,
blocked publication and Git status are preserved as historical observations;
they are **not the current release status**.

### Scope and version-reference inventory

Preparation changes only version strings and current release documentation.
No new features, authentication changes, tests, dependencies or UI redesign were
introduced. The classic identity, assets and version-free help/title text remain.

| File/reference | Version role and disposition |
| --- | --- |
| `pyproject.toml:7` | Authoritative package metadata: `0.1.2`. |
| `irdisc.py:2`, `irdisc.py:401` | Application module description and CLI `--version`: `0.1.2`. |
| `terminal_ui.py:219` | Connection-editor version banner: `v0.1.2`. |
| `tools/build_release.py:16` | Archive/wheel naming constant: `0.1.2`; builder not executed. |
| `README.md` | Candidate label and planned wheel installation filename: `v0.1.2` / `irdisc-0.1.2-py3-none-any.whl`; v0.1.1 remains explicitly published. |
| `CHANGELOG.md`, `RELEASE_NOTES.md`, `QA.md` | New v0.1.2 sections precede preserved historical release/validation records. |
| `AUDIT_REMEDIATION.md`, `tests/test_services_auth.py` | v0.1.1 audit evidence and historical regression description retained unchanged. |
| `CONTRIBUTING.md` | The v0.1.0 feature-freeze reference is historical and retained. |
| Existing tags and branch names | Historical Git identifiers, not application metadata; unchanged. |

Version inventory used `git grep` over tracked files. Package metadata, CLI,
connection-editor rendering and build constant were checked for agreement.
`--help` works without opening the TUI. Version-free chat/help/terminal-title
branding requires no release-number change.

### Exact changed files

- `CHANGELOG.md`: add the maintenance-release summary; retain older entries.
- `README.md`: candidate/version/install references, current platform evidence,
  contextual privacy guarantees and known limitations.
- `RELEASE_NOTES.md`: proposed English v0.1.2 notes, review/manual QA and limitations;
  retain the complete v0.1.1 notes.
- `QA.md`: this preparation, validation and readiness record; retain v0.1.1 evidence.
- `irdisc.py`: module description and CLI version only.
- `pyproject.toml`: package version only.
- `terminal_ui.py`: connection-editor version banner only.
- `tools/build_release.py`: version constant only; no packaging run.

### Executed validation

| Check | Outcome and limits |
| --- | --- |
| Complete isolated unittest suite | **158/158 passed**, zero failures/errors, in **0.776 s**. Includes the existing security, SASL and seven B1 methods; no new tests were added for this metadata/documentation pass. |
| Syntax/compile | **25 Python files passed** in-memory compilation and Python 3.11 grammar parsing. Runtime is 3.13.5; no Python 3.11 runtime execution was performed. |
| Terminal smoke | **PASS**: startup, picker, help, fragmented/modal/confirmation paste, subsequent commands, resize, clean quit and title save/set/restore sequences. Real curses PTY, no IRC connection. |
| Local verified TLS smoke | **PASS: 2 scenarios**. Blocked-reader close: **0.000090 s**; blocked-writer close: **0.000020 s**, after seven successful sends. Reader/writer exited. Existing OpenSSL generated a temporary synthetic localhost certificate/key; no dependencies installed. External-thread shutdown is not proof of UI responsiveness during a blocked send. |
| Credential prompt smoke | **PASS: 8 real PTY pre-submission prompts**. Synthetic plaintext absent, command structure and mask present, zero sends. Uses a mocked client and isolated HOME/XDG. |
| Metadata and history checks | **PASS**: package, CLI, editor banner and build versions agree; CLI help works. Prior changelog/release-note sections and complete audit are unchanged. |
| Secret and personal-path review | **PASS within the stated scope**: 38 tracked UTF-8 text files scanned for private-key headers, AWS/GitHub/OpenAI/Slack token signatures, credential URLs and personal home paths; no matches. Six nonempty credential-like keyword/simple-assignment literal locations were confined to synthetic test/prompt fixtures. No tracked key, PEM, P12, log, `.env` or `config.json` files. Existing binary assets are unchanged. Heuristic scanning is not proof that every possible secret format is detectable. |
| Git whitespace | `git diff --check`: **PASS**. |
| Isolation and preservation | **PASS**: validation HOME/XDG directories remained empty; persistence/logging fixtures use their own temporary directories or mocks. All branch/tag refs match the initial snapshot; unchanged tracked files, including tests, assets and the audit, were verified by hashes. |

The initial sandbox suite ran 158 methods in 4.788 s and ended with **three error
entries**: two socketpair subtest timeouts and one loopback-socket permission error.
The sandbox TLS attempt failed at `SO_SNDBUF` with a permission error. Neither
attempt is counted as a pass. The successful suite and local TLS runs above used
authorized execution outside the sandbox and only local sockets.

An additional metadata probe initially checked the version-free chat screen for
a version banner and failed that assertion. The corrected probe exercised the
connection editor, where the version banner is displayed, and passed; no application
behavior was changed in response.

#### Commands and isolation

`$QA_TMP` denotes the temporary validation directory; `$SOURCE_ROOT` denotes this
checkout. These publication-safe placeholders replace local filesystem paths.
The commands ran with HOME, XDG_CONFIG_HOME and XDG_STATE_HOME set to
`$QA_TMP/home`, `$QA_TMP/config` and `$QA_TMP/state`, and
`PYTHONDONTWRITEBYTECODE=1`:

```sh
python3 -m unittest discover -s tests
python3 tools/terminal_smoke.py "$QA_TMP/irdisc-source"
PYTHONPATH=. python3 tools/local_tls_smoke.py
python3 tools/credential_prompt_smoke.py
python3 irdisc.py --version
python3 irdisc.py --help
git diff --check
```

For the preparation checks, the executable PTY launcher was outside the checkout and invokes the existing
Python interpreter on `$SOURCE_ROOT/irdisc.py`; no package was built or installed.
Syntax validation used `ast.parse(..., feature_version=(3, 11))` and
`compile(source, filename, 'exec')` on all tracked Python files, without bytecode
writes. Secret/path checks scanned tracked text only; no user preferences/logs,
real credentials, SASL payloads or untracked `release/` contents were inspected.

### Independent review and OFTC manual QA

The maintainer reports **APPROVE WITH RESERVATIONS** from the independent security
review and successful real-network OFTC checks of TLS, NickServ IDENTIFY/STATUS,
contextual ChanServ replies, credential masking, reconnection, channel messages
and PMs. These are supplied manual results, not public-network tests run during
release preparation. No new public IRC connection was made.

OFTC's published [Services FAQ](https://www.oftc.net/FAQ/Services/#do-you-provide-sasl)
states that SASL is not currently provided. Deterministic SASL negotiation/failure
tests passed; real SASL authentication was not validated on OFTC or another network.

### Known limitations and publication boundary (historical)

R7 (status/`@server` log collision) and R8 (synchronous sends can block the UI)
remain open. CAP support is partial: colonless capability lists are ignored and
CAP NEW/DEL are unhandled. Privacy is contextual, missing paste end markers can
require restart, NickServ autojoin does not await service confirmation, and the
other deferred findings remain documented in RELEASE_NOTES.md and the unchanged
audit. No vulnerability-free or complete IRCv3-compliance claim is made.

At this preparation checkpoint, no remaining preparation-check failure was
identified. This was not publication approval. At that time, packaging and publication remained blocked on explicit authorization.
The existing builder writes into `release/`, including `dist/SHA256SUMS`; it must
be run only from a fresh approved staging tree/output location so that immutable
v0.1.1 artifacts are preserved. No release packages were created in this preparation step. At that time, future
v0.1.2 archive/checksum inspection and isolated wheel installation/smoke validation
were still required after packaging authorization; historical v0.1.1 package results
are not evidence for a v0.1.2 wheel.

Python 3.11 runtime, other operating systems, a terminal/emulator matrix, real SASL,
NAT/Wi-Fi transport-loss emulation and additional physical mouse/keyboard/CJK
acceptance remain unverified. R7/R8 and other reservations require release-owner
acceptance; this preparation does not resolve or silently waive them.

### Git state (historical snapshot)

At the preparation snapshot, working branch: `main`; HEAD was `43207badb689f2335018f698174b485acc8a3344`.
The `backup/pre-v0.1.2-merge` and `fix/audit-v0.1.1` branches remain at the same
commit. The annotated v0.1.1 tag object remains
`a15c72bb9e01456c8dcc43f2e42d3c3d3854f7bd`; its published commit remains
`f33692e9e5db60021913c75ef731f3e57542da44`. No staging, commit, push, tag, merge,
package creation or publication was performed **during that preparation step**. The untracked `release/` directory
was not opened, modified, staged or traversed.

Historical `git status --short` at the end of the eight-file preparation:

```text
 M CHANGELOG.md
 M QA.md
 M README.md
 M RELEASE_NOTES.md
 M irdisc.py
 M pyproject.toml
 M terminal_ui.py
 M tools/build_release.py
?? release/
```

---

# v0.1.1 release validation

Validation distinguishes automated checks from physical terminal/network behavior.
No public IRC channel is used by this test suite. Fixtures use fictional users.
The maintainer reported successful OFTC checks for NickServ identification and
contextual ChanServ/NickServ replies before this RC refinement; the revised
input masking and local echo still need a quick on-network visual check.

## Automated checks

Run `python3 -m unittest discover -v` from a clean source extraction.
Run the complete suite after changes; the v0.1.1 service/authentication regressions
are in `tests/test_services_auth.py`.
Result in this environment: **93 tests passed** (Linux/Python 3.12).

| Area | Evidence |
| --- | --- |
| Empty first use, presets, Custom, Save & Connect, Cancel | tests/test_release.py and test_connection.py |
| Save transaction and no partial edits/password persistence | test_connection.py and test_settings_auth.py |
| Invalid configuration → DNS failure → correction → JOIN in same app | Loopback TCP fixture in test_connection.py |
| Connect/disconnect/reconnect, TLS/SASL failures, timeout/refusal | test_connection.py, test_protocol.py, test_settings_auth.py |
| SASL unavailable vs rejected, NickServ after welcome, service context and secret handling | test_services_auth.py |
| Multiple conversations, PMs, membership and command errors | test_chat.py and test_ux.py |
| 281-user list, independent scroll, mouse after scroll, join/part anchors | test_layout.py |
| Visual-line chat scroll, long URLs/topics, resize and narrow layout | test_layout.py |
| Nick colors, context menus, unread, mention and bell cooldown | test_ux.py |
| Completion, input history, nick changes, PART/close/clear, modes/topic/kick, links | test_chat.py and test_ux.py |
| Commands modal scrolling, /help, shortcut selection and Ctrl+G fallback | test_release.py |
| Maximize hint dismissal on resize | test_release.py |
| Terminal title, network changes, unsupported output, exceptions, control-character sanitization | test_terminal_title.py |

## Render and package checks

The screenshot and icon inspection below are inherited from v0.1.0; these
unchanged visual assets were not regenerated for v0.1.1. The v0.1.1 wheel was
installed in an isolated virtual environment and passed `terminal_smoke.py`.

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
   Check certificate behavior, SASL PLAIN support/rejection or NickServ identification
   with a test account. Some networks require a manual join after NickServ replies;
   IRdisC sends the identification before the configured autojoin but cannot infer
   service success from generic IRC replies.
3. From a channel, run harmless `/msg ChanServ INFO #channel` and
   `/msg NickServ STATUS YourNick`; check replies and unsolicited notices.
4. Try mouse/right-click/wheel, completion/history, PM/WHOIS, large channel scrolling,
   context menus and Commands. F1 interception and terminal bell are emulator settings;
   verify Ctrl+G and clickable Commands as alternatives.
5. Resize/maximize/restore; confirm wrap, independent USERS scroll and readable small
   layout. Verify the tip disappears. Check links/clipboard with installed handlers.

These physical-terminal and live-network checks are **not marked passed** merely
because the automated suite passed. No automatic publication was performed.
