# Rules golden evidence

`cargo test -p tetris --test rules_golden --no-default-features --features ui-iced`

Rust result on 2026-09-14: **3 passed**.  The generated workspace was run with
`CARGO_TARGET_DIR=D:/autostack/auto-os/.target-tetris-rules --offline` so Cargo
uses a writable target directory outside the plan worktree.

- `opening_and_lock_golden`: deterministic spawn, move, rotate, soft drop,
  hard drop, lock and next-piece transition.
- `line_clear_score_and_compaction_golden`: one through four line clears,
  score tiers (100/300/500/800), feedback, fixed board length and top-row
  compaction.
- `all_piece_rotations_golden`: all seven pieces and four rotation states,
  including the exact eight coordinate values for every state.

The fixture includes the generated Rust component, so it exercises the same
`TetrisStore::on` implementation used by the Rust renderer.  The VM side now
uses the opt-in AutoUI MCP `autoui_fixture` channel.  Its runner seeds the same
opening, all 7×4 shape rotations through collision behavior, and 1/2/3/4-line
clear cases; on the live merged VM MCP endpoint it passed:

`VM rules golden passed: opening/lock + 7x4 rotations + 1..4 line clears`.

The VM result is a rules/state golden, not a replacement for native physical
input, focus/blur, visual pixel, or desktop/gallery acceptance.
