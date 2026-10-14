# IRdisC v0.1.1 — independent verification and first remediation pass

Date: 14/10/2026. Execution environment: Linux, Python 3.13.5.

The local changes fix BUG-01, BUG-02, BUG-03, BUG-04, BUG-07 and BUG-12.
The final suite ran **121 tests: 93 existing + 28 new; all passed**.
The remaining findings were assessed and remain outside this pass, as specified by the scope.

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
