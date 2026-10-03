# 036-tetris — AutoUI 俄罗斯方块

这是一个由 AutoLang 驱动的单人俄罗斯方块 app。界面和状态机只写一份
`.at` 源码，同时提供 Vue Web 轨、VM 原生轨，以及 Rust UI 产物。

## 运行

```powershell
cd apps/036-tetris
$env:AUTO_LANG_ROOT = "D:/autostack/auto-lang"

# Vue 前端通过 HTTP 调用后端（17500 / 17501）
auto run --render vue --server rust --no-merge

# VM/Rust 原生轨：可选 HTTP 后端或进程内 merged
# VM no-merge 的后端实现默认是 VM；不要传 --server vm（该参数会只启动后端服务）
auto run -r vm --no-merge
auto run -r vm --merged
auto run -r rust --server rust --no-merge
auto run -r rust --merged
```

`am.at` 为本地 app 的最小配置。生成产物放在 `gen/`、`dist/` 和
`rust-workspace/`，由 `.gitignore` 排除。

## 操作和设计

- `← →` 移动，`↑` 旋转，`↓` 软降，`Space` 硬降，`P` 暂停。
- 棋盘是 10×20，显示活动块、锁定块和硬降幽灵轮廓；右侧显示下一个方块、
  得分、最高纪录、等级、消行和升级进度。
- 开始、暂停、重新开始确认、玩法说明和游戏结束均是状态机 overlay，
  触屏按钮与键盘事件复用同一组 Store 消息。
- `src/front/tetris_store.at` 将形状和颜色表、碰撞、消行、计分、重力和
  render cell 字段集中管理。棋子颜色固定，`pac.at` 的 `accent: "indigo"`
  只影响标题/主按钮等品牌控件，不改变棋盘的色彩语义。
- `src/back/db.at` / `src/back/api.at` 定义最高分读写接口。HTTP 后端以带
  `schema_version`/`best` 的版本化 JSON 写入 `records.json`，同时兼容早期裸整数；
  merged Rust 仍使用生成器的进程内 API shim，需待框架能力补齐后再验证真实落盘。

## 测试

```powershell
cd apps/036-tetris
pnpm --dir tests install
pnpm --dir tests test
python tests/desktop_mcp.py
# capability probe and evidence (native legs stay blocked without a driver)
python tests/run_matrix.py --probe
# persistence leg after building the backend
python tests/run_matrix.py --suite persistence
# generated Rust rules golden (opening/lock + 1..4 line clears)
cargo test -p tetris --test rules_golden --no-default-features --features ui-iced
# real Windows key-down/key-up, long-press and blur acceptance (needs a visible window)
python tests/native_physical.py --mcp-url http://127.0.0.1:9247/mcp --blur
# desktop manifest and 05-games gallery contract audit
python tests/gallery_contract.py
```

Playwright 测试会 mock 纪录 API，覆盖首屏、开始/暂停、键盘硬降和说明
overlay；`desktop_mcp.py` 在设置 `AUTOUI_MCP_URL` 时可对 VM MCP 快照做同样
的结构冒烟。

相关实现计划：[auto-os Plan 005](../../docs/plans/005-tetris.md)。
