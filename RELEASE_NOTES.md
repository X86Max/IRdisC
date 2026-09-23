# ⇹ IRdisC v0.1.1 — release candidate

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
