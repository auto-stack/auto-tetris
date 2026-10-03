# Native input evidence

Driver: `python tests/native_focus_probe.py --mcp-url http://127.0.0.1:9273/mcp`

The driver is ready to send real Windows key-down/key-up events, hold the first
key for a configurable interval, move focus to a second window for blur, then
capture AutoUI snapshots before and after the sequence.  The 2026-09-14 run
returned:

`BLOCKED: no visible native window matching '俄罗斯方块'; matches: none`

The lower-level driver was then run against an independently started visible
VM window on 2026-09-14 with `--long-press-ms 600 --blur`; it completed with
key-down/key-up events for `ArrowLeft, ArrowRight, ArrowDown, Space, P`,
recorded a focus switch to a second visible window, and completed the sequence
with the final `P` toggling the auto-paused game back to playing. The full
before/after snapshot and event record is in
`tests/evidence/native-input-live.json`.

The same live VM run produced `tests/evidence/vm-ready-modal-live.png`; the
ready dialog is centered in the window with a dimmed game surface behind it.

The follow-up probe `tests/native_focus_probe.py` also sends repeated physical
key-down packets during a 750 ms hold and a distinct key-up. Six packets moved
the active piece from `px=3` to `px=0`, so the repeat and release path is
observable. Moving focus to a second visible window now dispatches the opt-in
`Blur` lifecycle message and leaves the game in `phase="paused"`; focus
restoration does not resume play. A later physical/MCP `P` control pause is
idempotent while paused. The exact state record is in
`tests/evidence/native-focus-repeat-live.json`.
