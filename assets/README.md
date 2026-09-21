# Identity assets

`irdisc.svg` is the master: vector paths, no font dependency. The ⇹ symbol in the
application remains Unicode. PNG exports cover 16, 24, 32, 48, 64, 128, 256 and
512 pixels. A dark tile with a mint edge keeps contrast on light/dark backgrounds.

For future Linux packaging, install the SVG as
`share/icons/hicolor/scalable/apps/irdisc.svg`, PNGs under corresponding
`share/icons/hicolor/SIZExSIZE/apps/irdisc.png`, and `irdisc.desktop` under
`share/applications/`. The desktop template requires `irdisc` on PATH.
It is not automatically installed by the Python wheel.

`screenshot.png` is captured from the application's actual curses cell output
with synthetic offline demo conversations, then rendered with DejaVu Sans Mono.
It contains no real chat or personal data. See tools/render_assets.py.
