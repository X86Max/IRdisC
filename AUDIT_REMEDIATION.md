# IRdisC v0.1.1 — independent verification and security remediation

Round 2 addresses the mandatory findings from the independent review of snapshot `7a3595c1d7c7d6382965cc55c0c025bda6a87de5` against local baseline `74d1eb7f9b40b1f4cdadbd03f3093b0cea637209`. The new suite contains **151 tests: the previous 121 + 30 new; all passed**. Review findings R1–R6, SASL 902 and `AUTHENTICATE :+` were reproduced before remediation. Current implementation, evidence, limitations and Git state are in sections F–K.

Sections A–E preserve the first-pass record, including its original line references and test history. The independent review rejected that snapshot despite the 121 passing tests: paste handling and credential protection were incomplete. The first-pass “Fixed” labels below describe the original reproductions, not complete subsystem guarantees; sections F–K supersede their broader interpretation. The original socket-reference race, empty-profile persistence, reserved in-memory buffer protection and test-isolation fixes remain in place.

## First-pass record (historical)

Date: 14/10/2026. Execution environment: Linux, Python 3.13.5.

The first-pass changes addressed BUG-01, BUG-02, BUG-03, BUG-04, BUG-07 and BUG-12.
The first-pass final suite ran **121 tests: 93 existing + 28 new; all passed**.
The remaining findings were assessed and stayed outside that pass, as specified by its scope.

## A. Verification matrix

Severity classifications describe the observed impact, without assigning a CVSS score.
Reproductions used mocks, fictitious credentials, temporary files and local sockets.

| Finding | Verification and actual severity | Evidence and caveats | Disposition |
| --- | --- | --- | --- |
| BUG-01 | Confirmed; high | In an active channel, a paste of 10,005 characters followed by `\r/quit\r` allowed the suffix to become keystrokes: the original code sent `PRIVMSG #test :draftaaaaa` and ended with `running=False`, without review. This demonstrated execution, beyond merely leaving characters unread. A timeout also allowed delayed content to become keystrokes. | Fixed. |
| BUG-02 | Partially confirmed; high for `server` | `NICK :server` replaced the connection buffer object. `server` is a legitimate nickname. However, `#test` fails the project's own nickname validation: channel destruction is reproducible through a direct call, but depends on protocol-invalid input. | Fixed the legitimate case and added protection against collisions with channels/local views. |
| BUG-03 | Confirmed; high | `_run` modified and closed `self.sock` without the lock used by the writer; `send` and `close` reread the attribute between checking and using it. In addition to the artificial `__bool__` mock, a test with two threads and barriers reproduced `AttributeError` after finalization occurred while the writer was waiting for the lock. `close` could also wait indefinitely for a blocked writer. | Fixed the lifecycle and I/O unblocking. |
| BUG-04 | Confirmed; medium | Saving initial preferences with `theme='mono'` and reloading them returned `dark`. There are two causes: `int('')` and rejection of an empty host. Fixing only the port would not resolve persistence on first use. | Fixed while retaining empty initial fields. |
| BUG-05 | Confirmed; medium | `NOTICE #test :maintenance` appeared only in `server`; the calculated destination is overwritten unconditionally. | Deferred: outside the six priority fixes. |
| BUG-06 | Confirmed in the client's state; medium/high | After CAP LS/ACK with SASL and numeric 902, `cap_ended=False`. The set of handled failures omits 902. Stalling against a real server was not tested. | Deferred: protocol handling outside the authorized first pass. |
| BUG-07 | Confirmed; medium | `IDENTIFY a` changed `Hello world and banana` into `Hello world [redacted]nd b[redacted]n[redacted]n[redacted]`. The same substring list interfered with history and the prompt; it included public names and was not cleared per session. | Fixed through contextual credential identification. |
| BUG-08 | Confirmed; low/medium | Pressing Enter in `*search*` called `send('PRIVMSG *search* :hello')`. This proves transmission to the socket, not actual delivery to another user or the numeric response a particular network will return. | Deferred: protection against sending from local views remains pending. |
| BUG-09 | Confirmed; low | `Max\|afk` was accepted in the profile and rejected by `/nick`; the command uses a different regex. | Deferred: consistent validation. |
| BUG-10 | Functional limitation confirmed; low | `/join #secret key` was rejected by the single-target validator. The documentation advertises `/join #channel`; no evidence of previous key support was found. This is missing functionality, with no demonstrated regression. | Deferred: adding support would expand functionality. |
| BUG-11 | Confirmed; low | `/quit custom reason` only changes flags; the `finally` block in `ChatApp.run` calls `client.close()` without the argument, although help advertises an optional reason. | Deferred: behavior correction outside the first pass. |
| BUG-12 | Confirmed; medium | The 93 original tests passed with temporary XDG directories, but created `state/irdisc/logs/Alice.log`. The mock expired while `logging=True`. `ChatTests.setUp` also read real preferences. No real user directory was used in the reproduction. | Fixed and protected by a regression test that blocks access to the default log directory. |
| BUG-13 | Partially confirmed; low/medium | `pending_names` persists after disconnect. After reinserting a fictitious user following disconnection, the first 353 does not clear it. However, `disconnect` and the `Disconnected` event already clear `users`: the audit's reproduction injects the ghost user manually and does not, by itself, demonstrate that it would survive a normal reconnection. | Deferred: residual state confirmed; the practical extent of the effect requires further validation. |

## B. Implemented changes

| File and reference | Root cause addressed and implementation | Regression coverage |
| --- | --- | --- |
| `terminal_ui.py:1205`, `:1240`, `:1257`, `:1275` | The read limit released the rest of the paste as input. An explicit paste state now intercepts keystrokes before commands, retains up to 10,000 characters plus the marker and discards excess input until the end marker. The initial read is limited to a batch of 1,024 input items. A timeout or a recognizably truncated/malformed start sequence triggers discard mode. Paste review also masks Services commands. | Actual `/quit` execution in the original code; boundaries; 100,000 characters; timeout and delayed suffix; truncated/malformed start; normal confirmation; single line; Esc; masking in the preview. |
| `chat_ux.py:30`, `:35`, `:254`; routing in `terminal_ui.py` | The PM key could collide with `server`. The nickname `server` has the local representation `@server`, translated to `server` only for actions targeting the nickname and when sending. History, drafts, navigation and menus remain separate from the connection buffer. Renames to channels/local views are ignored. | Legitimate nickname `server`, incoming message, reply, subsequent rename, `/query`, `/msg`, closing the conversation and channel preservation. Existing tests retain coverage of collisions between two PMs and their drafts. |
| `irdisc.py:71`, `:78`, `:191`, `:209` | The shared attribute was reread without protection. A briefly held lock protects publication/detachment, and the writer captures a local reference under that lock. The network thread owns the socket and uses its local reference in `recv`; on finalization, it performs shutdown and close. `close` detaches the socket, prevents new sends and interrupts I/O without waiting for the write lock. QUIT is attempted with a one-second limit when no writer is active. | Barriers between send/finalization; blocked send versus close and versus finalization; close during TLS; cancellation during creation already covered by the existing suite; repeated close; QUIT validation; real socketpair across two fresh sessions. |
| `irdisc_settings.py:16`, `:91` | The empty editor's saved format was rejected by the loader itself. Empty port and host fields are recognized as a profile that is not yet configured; the port annotation reflects this state. Connection validation remains mandatory, invalid ports are still rejected, and SASL migration/the field allowlist remain in place. | Round-trip of theme, flags and saved profiles; legacy file with empty host/port; SASL migration; no persisted password. |
| `terminal_ui.py:63`, `:356`, `:374`, `:678`, `:689`, `:728` | Removed global substring replacement in messages, history and the prompt. Recognized command arguments remain masked; credentials are extracted by position and used to filter Services replies, server text and authentication events, using word boundaries. The set is separated by service and cleared per session. Disconnect detaches the old queue before forgetting credentials, preventing exposure of queued or late echoes. Credentials from partially failed writes remain protected. | Passwords `a`, `me`, `do`, `in`; ordinary messages, rendering and history intact; public account preserved; REGISTER in both services; retention of earlier credentials within the session; clearing/reconnect; delayed echoes; existing authentication and partial masking suite. |
| `tests/test_services_auth.py:104`; `tests/test_chat.py:10` | The logging mock now covers the entire test that enables logging. `ChatTests` receives mocked initial preferences without reading the developer's configuration. | `test_service_test_never_reaches_default_log_directory` fails if the test resumes looking up the default directory. |
| `tests/test_audit_regressions.py:17`, `:249`, `:287` | 28 new test methods with fictitious data, mocks, temporary directories and exclusively local sockets. | Cover the six fixes and relevant boundaries. |

Compatibility: no new dependencies, version change or format change requiring destructive migration.
First use still starts with empty fields; default authentication `none`, SASL migration, NickServ,
contextual Services routing and partial masking retain coverage through the existing tests.
The `@server` alias distinguishes a PM from the reserved buffer in the interface without changing the IRC recipient.

## C. Validation performed

### Results

- Original baseline: 93 tests, all passed with temporary HOME/XDG directories and local sockets permitted.
- First attempt in the sandbox: 92 passed, and a permission error occurred when creating the loopback test's socket. That attempt was not treated as a successful suite run.
- Original isolation: `Alice.log` was created only in the temporary XDG directory, confirming BUG-12.
- Comparison against a `git archive HEAD` extraction in `/tmp`: running 27 of the new cases against the original code produced `FAILED (failures=26, errors=2)`; the counters include subtests. The two errors are the old reader exhausting the simulated input and the new cache not yet existing; the behavioral failures demonstrate the six fixes. The 28th test provides additional protection against late echoes when clearing credentials.
- Final suite: **121 run, 121 passed, zero failures/errors**, in 0.332 s.
- Syntax: in-memory compilation and parsing with the Python 3.11 grammar for all 21 Python source/test/tool files. `compileall` was not used, avoiding bytecode writes in the project.
- Real terminal smoke test: PASS for startup, picker, help, resize, exit and title save/restore sequences, without an IRC connection.
- `git diff --check`: no errors.
- HOME/XDG for final validation: no files created in these three directories. Persistence/logging tests use their own temporary directories or mocks.

### Main commands, exactly as executed

At the repository root, baseline:

```sh
HOME=/tmp/irdisc-audit-wsap2r42/home XDG_CONFIG_HOME=/tmp/irdisc-audit-wsap2r42/config XDG_STATE_HOME=/tmp/irdisc-audit-wsap2r42/state PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
```

In the original copy at `/tmp/irdisc-audit-wsap2r42/original-source`, with the new regression file copied into it:

```sh
HOME=/tmp/irdisc-audit-wsap2r42/original-home XDG_CONFIG_HOME=/tmp/irdisc-audit-wsap2r42/original-config XDG_STATE_HOME=/tmp/irdisc-audit-wsap2r42/original-state PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_audit_regressions.py
```

At the repository root, final validation:

```sh
HOME=/tmp/irdisc-audit-wsap2r42/validation-home XDG_CONFIG_HOME=/tmp/irdisc-audit-wsap2r42/validation-config XDG_STATE_HOME=/tmp/irdisc-audit-wsap2r42/validation-state PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
HOME=/tmp/irdisc-audit-wsap2r42/validation-home XDG_CONFIG_HOME=/tmp/irdisc-audit-wsap2r42/validation-config XDG_STATE_HOME=/tmp/irdisc-audit-wsap2r42/validation-state PYTHONDONTWRITEBYTECODE=1 python3 tools/terminal_smoke.py /tmp/irdisc-audit-wsap2r42/irdisc-source
git diff --check
```

Socket tests were run outside the sandbox after authorization, exclusively over loopback/socketpair.
The smoke test initially attempted to execute `irdisc.py` directly, but that file lacks execute permission and the PTY child exited. It also failed outside the sandbox. The approved run used this temporary launcher, with mode 0700, without installing the project:

```sh
#!/bin/sh
exec /usr/bin/python3 /path/to/IRdisC/irdisc.py
```
The original local filesystem path has been anonymized for publication. The launcher shown here is illustrative; the actual validation used a temporary launcher pointing to the local checkout.

The syntax validation performed in Python uses:

```python
import ast, pathlib
paths = [pathlib.Path(f) for f in (
    'irdisc.py', 'terminal_ui.py', 'chat_ux.py', 'irdisc_settings.py',
    'release_ui.py', 'text_layout.py'
)] + list(pathlib.Path('tests').glob('*.py')) + list(pathlib.Path('tools').glob('*.py'))
for p in paths:
    source = p.read_text()
    ast.parse(source, filename=str(p), feature_version=(3, 11))
    compile(source, str(p), 'exec')
```

Not run: the Python 3.11 runtime (unavailable in the environment), an emulator/OS matrix, physical mouse/keyboard use and authentication on a real network. Parsing with the 3.11 grammar does not replace execution on that version.

## D. Outstanding issues and risks

**Defects/limitations outside this pass:** BUG-05, BUG-06, BUG-08, BUG-09 and BUG-11 remain confirmed and unfixed; BUG-10 remains missing functionality. BUG-13 has confirmed residual state, with the extent of its consequences still only partially demonstrated.

**Suspicions raised by the audit:**

1. NickServ/autojoin: confirmed that IDENTIFY and JOIN are sent in sequence after 001, without waiting for service confirmation. An actual rejection by a channel requiring authentication depends on the network. The limitation is already documented in QA.md; it was not changed.
2. Silently lost connection: `settimeout(None)` and the absence of a heartbeat remain. Loss of NAT or Wi-Fi state without FIN/RST was not simulated; the risk of a zombie connection remains an operational hypothesis.
3. `AUTHENTICATE :+`: the parser places `+` in the trailing parameter, and the condition requires `params[0]`. Local reproduction confirmed zero response sends. Compatibility with a server/bouncer using this format was not tested; fix deferred.
4. CJK cursor: with input `界`, logical cursor position 1 and a 110-column terminal, rendering placed the cursor at column 3, while the visual width requires column 4. The misalignment was demonstrated locally; physical testing with emojis/emulators remains pending.

**Optional improvements, not implemented:** rejoining all channels; Tab cycling; operator commands; reducing NAMES after MODE; creating the temporary settings file with mode 0600 from the outset; replacing the dynamic import. The `.tmp` permission window remains possible with a permissive umask; the current test checks final permissions without eliminating that window. These are separate work items.

**Limitations of the fixes:** a paste without an end marker keeps input in discard mode until `ESC[201~` is received; this prevents a delayed suffix from becoming commands, but may require restarting the application if the terminal never sends the marker. Cancellation during creation/TLS is observed when the operation finishes, bounded by the 15-second connection timeout. Services credentials remain only in memory until the end of the session and are not evicted based on count, preventing exposure of echoes of earlier passwords. Protection is contextual: proprietary authentication formats and transformed echoes must be assessed during network QA; ordinary messages are not censored for containing words that match short passwords.

**Network QA still required:** real SASL/NickServ, REGISTER/IDENTIFY variants, numeric 902, TLS errors and recovery, channels requiring authentication, Services messages and reconnection after transport loss. No production IRC network was accessed.

## E. Git review and preservation

Branch: `fix/audit-v0.1.1`.

Before editing, the branch, `main` and the commit referenced by `v0.1.1` were `f33692e9e5db60021913c75ef731f3e57542da44`. The annotated `v0.1.1` tag object was `a15c72bb9e01456c8dcc43f2e42d3c3d3854f7bd`.
All branch/tag refs were compared with the initial snapshot and remained unchanged.
The file set in `release/` and the SHA-256 hashes of its five files also remained unchanged.
No commit, staging, merge, push, tagging or publication was performed. The version and website were not changed.

`git status --short` at completion:

```text
 M chat_ux.py
 M irdisc.py
 M irdisc_settings.py
 M terminal_ui.py
 M tests/test_chat.py
 M tests/test_services_auth.py
?? AUDIT_REMEDIATION.md
?? release/
?? tests/test_audit_regressions.py
```

`git diff --stat` (Git omits untracked files):

```text
 chat_ux.py                  |  30 ++++++---
 irdisc.py                   |  83 ++++++++++++++++++-------
 irdisc_settings.py          |  11 ++--
 terminal_ui.py              | 145 +++++++++++++++++++++++++++++++++-----------
 tests/test_chat.py          |   4 +-
 tests/test_services_auth.py |   3 +-
 6 files changed, 204 insertions(+), 72 deletions(-)
```

In addition to this diff, the new files for review are this report and `tests/test_audit_regressions.py`.
`release/` is the pre-existing artifacts directory, preserved in full.

## F. Round 2 — independent reproduction and resolution matrix

Date: 14/10/2026. Runtime: Linux, Python 3.13.5. The source findings were reproduced on local commit `74d1eb7`, rather than assuming that a passing suite or the review's earlier archive established their correctness. All credentials and identities introduced by this round are synthetic. Logs were written only to temporary directories; no production IRC network was contacted.

| Review finding | Verification, severity and observed baseline effect | Resolution and evidence |
| --- | --- | --- |
| R1 — fragmented paste start | Confirmed; high. Interrupting after `[`, `[2` or `[20` allowed `200~hello`, `00~hello` or `0~hello` to be sent to `#test`, followed by `/quit` setting `running=False`. | A persistent escape-prefix state survives read timeouts, mouse/resize notifications and changes of dialog. All six boundaries in the six-byte start marker and a pause after every byte have deterministic coverage. Dangerous suffixes produce no unreviewed sends, history entries or quit. Normal Esc, decoded keys, raw CSI/SS3 arrows, shortcuts and ordinary typed text have positive coverage. |
| R2 — modal readers | Confirmed; high. Both help and the connection editor consumed the opening ESC, then released `[200~hello` as a channel message and executed `/quit`. | Chat, help, editor (including its small-terminal branch), selector, paste confirmation and startup use the same framing boundary. Inline context menus, topic view and action menu also pass through it. A paste that starts in a dialog is discarded through its end marker even if Esc dismisses that dialog. Help/editor/selector/confirmation and inline dialogs have no-send/no-quit regressions; real PTY probes cover help, editor and nested paste confirmation. |
| R3 — normalization order | Confirmed; high. A Services reply containing `demo-\x02secret` became the unredacted `demo-secret` after display cleanup and was written to a real temporary log. | Formatting/control cleanup precedes contextual credential matching. The protected assembled representation is used for message storage, drawing and logging; stored topic text and authentication events use the same normalization. Tests include bold, color, italic, underline and a nonprinting Unicode character, across status/channel/Services origins. |
| R4 — numeric middle parameters | Confirmed; high. `:srv 400 Tester demo-secret :Invalid parameter` wrote the synthetic credential to both status and channel logs. | The complete rendered numeric message, including its middle parameters, is normalized and redacted before buffering/logging. Raw protocol parameters remain available for protocol state. Regression checks both log files, visible buffers, rendering and a formatted trailing parameter. |
| R5 — service actions | Confirmed; medium. `/me IDENTIFY demo-secret` in a NickServ PM entered history, produced an unmasked action log and sent a CTCP ACTION containing the credential. | `/me` and explicit CTCP ACTION bodies share sensitive-input recognition and masking. Recognized credential-bearing service actions are rejected before transmission with a constant message. Submission clears sensitive history drafts and the active saved draft, including failed/offline cases. Ordinary channel/peer actions still send their normal CTCP ACTION and retain their usual history/echo. |
| R6 — whitespace/parser mismatch | Confirmed; medium. A tab-separated `/msg` was masked by the classifier but treated as an unknown command; its error logged `msgnickservidentifydemo-secret`. | Command and `/msg` argument parsing now accept the same whitespace as the classifier. Unknown-command errors do not interpolate an untrusted command name. Tests cover tabs, spaces, mixed whitespace and a nonbreaking space; the recognized command sends once, stays out of history and never exposes the credential through errors or logs. |

These are scoped resolutions of the mandatory reproductions and their tested variants. They are not a claim that arbitrary text or all proprietary authentication formats can be recognized as passwords.

## G. SASL protocol corrections

- **902:** reproduced before the fix with `cap_ended=False`, no authentication-error event and no `CAP END`. It now follows the existing controlled authentication-failure path alongside 904–907. Dedicated credential-free output replaces the raw numeric in the UI. Tests feed each failure followed by 001: negotiation ends with exactly one `CAP END`, the UI retains `Authentication error`, and no configured-channel JOIN is sent.
- **Challenge equivalence:** before the fix, `AUTHENTICATE +` sent a PLAIN response while `AUTHENTICATE :+` sent none. Both now produce the same expected base64 payload. A following 903 completes negotiation with exactly one `CAP END`.
- **Late challenges:** once CAP has ended, neither challenge form sends credentials again.
- **Unavailable versus failed:** absent SASL capability and CAP NAK retain their unavailable-capability messages; 902 produces an authentication-failure message. Existing success, unavailable/rejected SASL, NickServ, default `none` and legacy migration tests remain in the full suite.

These tests use local protocol fixtures. They do not assert that OFTC naturally emits 902 or the trailing-parameter challenge form, or claim a real-network authentication result.

## H. Files changed in Round 2

| File | Reason and relevant implementation |
| --- | --- |
| `terminal_ui.py` | Persistent escape framing and shared modal reads (`read_key`, `filter_input`, `key`, paste review); normalized contextual display protection (`add_message`, `receive`, `redact_auth_text`); service action classification/masking/rejection and sensitive draft cleanup; whitespace-consistent command execution and constant unknown-command errors. The logging notice now accurately refers to recognized service credentials instead of promising that all passwords are never logged. |
| `release_ui.py` | Help and network selection use the shared input boundary. Their layout and normal controls remain unchanged. |
| `irdisc.py` | Add SASL 902 to the existing failure set, accept both challenge parameter forms, and ignore credential challenges after CAP ends. The socket ownership and lifecycle implementation is retained. |
| `tests/test_review_security.py` | 30 new regression methods, with multiple boundary/control/origin/failure subcases. They check actual no-send/no-quit behavior, real temporary log contents, buffers, prompt rendering, history/draft history, normal actions and SASL wire/event/UI outcomes. |
| `tools/terminal_smoke.py` | Extend the existing real PTY smoke with delayed marker splits, help/editor pastes and a paste arriving at multiline confirmation. Offline `/quit` probes must not exit the client; subsequent `/settings` confirms it still accepts commands. |
| `tools/local_tls_smoke.py` | Reproducible optional transport check using verified localhost TLS over socketpairs. An existing OpenSSL executable generates an ephemeral synthetic certificate/key outside the checkout. No new package or runtime dependency is installed. Exit 77 explicitly means the fixture generator is unavailable; that outcome is not a pass. |
| `AUDIT_REMEDIATION.md` | Preserve first-pass evidence, identify its incomplete scope, and document Round 2 verification, changes, executed checks and remaining risks. Retain the publication-safe launcher clarification in the historical record. |

No source/version changes were made in `chat_ux.py`, `irdisc_settings.py`, `pyproject.toml` or the earlier regression files during this round. Existing PM/status separation, settings persistence and lifecycle tests remain part of validation.

## I. Round 2 test results and commands

| Executed validation | Result and limits |
| --- | --- |
| Unmodified local baseline | **121/121 passed**, in 0.310 s, with isolated HOME/XDG and local sockets permitted. This corroborates the original test count, not the absence of security flaws. |
| Original R1–R6/SASL probes | All six review findings confirmed through actual application methods; R3–R6 wrote synthetic credentials to real temporary logs. Both SASL defects were reproduced. The probe script and output were kept outside the project tree. |
| New regressions against a temporary extraction of `74d1eb7` | **30 methods run; `FAILED (failures=54)`**, zero errors, in 0.090 s. Failure counters include subtests and are not a count of 54 test methods. The old implementation fails the security/protocol assertions; positive compatibility cases also run. |
| New regressions after correction | **30/30 passed**. |
| Full isolated suite | **151/151 passed**, zero failures/errors, in 0.433 s: the original 121 plus 30 Round 2 methods. |
| Full suite with default configuration/state lookups forbidden | **151/151 passed**, zero failures/errors, in 0.430 s. Explicit temporary file paths and mocked preferences remain allowed. |
| Local verified TLS | **2 scenarios passed**: blocked reader and blocked writer. Close took 0.000122 s and 0.000061 s respectively; the non-reading peer stalled the writer after seven successful sends. Reader and writer exited without captured exceptions. This is an external-thread shutdown check, not proof of UI responsiveness during a stalled write. |
| Real PTY | **PASS**: startup, picker, help, five delayed start-marker splits in help, editor paste, nested paste confirmation, subsequent commands, resize, clean exit and title save/restore sequences. No IRC connection. |
| Syntax | **23 Python files passed** in-memory compilation and Python 3.11 grammar parsing. Execution runtime is 3.13.5; no Python 3.11 runtime claim. |
| Whitespace review | `git diff --check` passed. |

The first sandbox baseline attempt had three error entries: two socketpair timeouts and a loopback-socket permission error. The TLS tool's sandbox attempt was also blocked at `SO_SNDBUF`. The successful socket validations above ran outside the sandbox after authorization; those environmental failures were not counted as passes. HOME/XDG are isolated throughout, and no dependencies were installed.

For publication, `$AUDIT_TMP` below denotes the temporary audit directory, and `$SOURCE_ROOT` the checkout. These are placeholders for local paths, not committed personal paths. With HOME/XDG set to `$AUDIT_TMP/home`, `$AUDIT_TMP/config`, `$AUDIT_TMP/state` and `PYTHONDONTWRITEBYTECODE=1`, the executed checks were:

```sh
python3 -m unittest tests.test_review_security
python3 -m unittest discover -s tests
PYTHONPATH=. python3 tools/local_tls_smoke.py
python3 tools/terminal_smoke.py "$AUDIT_TMP/irdisc-source"
git diff --check
```

The temporary PTY launcher invokes the existing interpreter on `$SOURCE_ROOT/irdisc.py`. It is outside the checkout and no package was installed. The full-suite guard was executed with:

```python
import unittest
from unittest.mock import patch
with patch('irdisc_settings.config_dir', side_effect=AssertionError('Default configuration directory access forbidden')), patch('irdisc_settings.state_dir', side_effect=AssertionError('Default state directory access forbidden')):
    suite = unittest.defaultTestLoader.discover('tests')
    result = unittest.TextTestRunner(verbosity=1).run(suite)
raise SystemExit(not result.wasSuccessful())
```

The syntax check follows the in-memory AST/compile procedure recorded in section C, now including the new test and TLS tool. Baseline extraction used tracked `git archive HEAD` content in a temporary directory and copied only the new test module into that copy. Untracked `release/` was excluded and was not opened, modified or packaged in this round.

## J. Remaining limitations and merge status

- **R7 remains open:** status and `@server` PM logs can share `server.log`; the repaired in-memory buffer namespace does not fix the persistence namespace.
- **R8 remains open:** synchronous unbounded `sendall` can block the UI. Another thread can interrupt it, as demonstrated by the TLS test; an operator's disconnect on that blocked UI thread is not a verified escape. No broad write-queue redesign was attempted.
- **BUG-05, 08, 09, 10, 11 and 13 remain outside this round:** channel NOTICE routing; unwanted sends from local search; nickname-validation inconsistency; keyed JOIN support; quit reason; residual pending NAMES state and its incompletely demonstrated practical consequence.
- **NickServ/autojoin sequencing remains:** IDENTIFY is sent before JOIN without waiting for service confirmation. The new no-autojoin assertions cover SASL failure, not successful NickServ account confirmation or entry into authentication-restricted channels.
- **Input recovery and scope:** a possible paste-start prefix is retained across arbitrary input delays. Esc can dismiss a dialog immediately while retaining that framing role; an ambiguous literal escape-prefix sequence may wait for more input. Paste beginning in a dialog is discarded, not inserted into editor fields. Missing end markers still quarantine subsequent input until the closing marker or application restart. Oversize/malformed recognized pastes retain bounded storage and do not become executable suffixes. Tests do not certify every emulator's key encoding or arbitrary malformed terminal traffic.
- **Credentials:** recognized Services commands retain partial masking; ordinary peer messages deliberately remain outside contextual redaction. Proprietary/unrecognized authentication syntax, transformed echoes beyond the tested normalization and passwords deliberately posted as ordinary chat are not universally detectable. Manual service credential messages are still not separately TLS-gated when an unencrypted `none` session is in use; configured SASL/NickServ profile validation continues to require TLS.
- **Other prior risks remain:** silent transport loss without a heartbeat, CJK/emoji prompt cursor width, all-channel rejoin, Tab cycling, operator commands, unnecessary NAMES after MODE, the settings temporary-file permission window and the dynamic import. Cancellation during connection creation/handshake still relies on those operations completing or timing out; this round does not establish an end-to-end 15-second cancellation bound.
- **Not executed:** production IRC/OFTC authentication, NAT/Wi-Fi failure emulation, a physical keyboard/mouse/CJK session, an emulator/OS matrix or Python 3.11 runtime execution. These remain real-network/manual QA tasks.

**Mandatory blocker status:** none of R1–R6, SASL 902 or the trailing-parameter challenge remains unresolved in the executed reproductions and regressions. This is a locally tested candidate for the next independent review, not an assertion of merge approval. R7/R8 and the listed nonblocking findings remain explicitly open.

## K. Round 2 Git review

Working branch: `fix/audit-v0.1.1`. HEAD remains `74d1eb7f9b40b1f4cdadbd03f3093b0cea637209`; `main` remains `f33692e9e5db60021913c75ef731f3e57542da44`. Branch/tag refs are compared against the start of this round. Existing tags, the published version, website and untracked `release/` are outside the edits. No staging, commit, amendment, merge, push, tag or publication is performed.

`git status --short` for this round:

```text
 M AUDIT_REMEDIATION.md
 M irdisc.py
 M release_ui.py
 M terminal_ui.py
 M tools/terminal_smoke.py
?? release/
?? tests/test_review_security.py
?? tools/local_tls_smoke.py
```

`git diff --stat` (tracked files only; new test/TLS files are untracked):

```text
 AUDIT_REMEDIATION.md    | 136 ++++++++++++++++++++++++++-
 irdisc.py               |   4 +-
 release_ui.py           |   4 +-
 terminal_ui.py          | 239 ++++++++++++++++++++++++++++++++----------------
 tools/terminal_smoke.py |  28 +++++-
 5 files changed, 323 insertions(+), 88 deletions(-)
```

The seven intended changed/new files are listed in section H. The pre-existing `release/` status entry is not a change made by this round.
