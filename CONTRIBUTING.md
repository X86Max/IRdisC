# Contributing

Open an issue in the project's GitHub repository for bugs or focused improvement
ideas. Search existing issues first. There is no telemetry or automatic report upload.

For bugs include OS/version, terminal/version, Python version (`python3 --version`),
IRdisC version (`irdisc --version` or `python3 irdisc.py --version`), reproduction
steps, expected/actual behavior and an optional redacted screenshot or log.
Remove nick/account identifiers when appropriate and never include passwords,
tokens, private messages, full profiles or unredacted logs.

For a pull request: explain the problem and resulting behavior, keep changes
focused, add regression tests for behavioral changes and run
`python3 -m unittest discover -v`. Runtime dependencies remain empty.
Discuss large changes in an issue first; v0.1.0 is feature-frozen.
