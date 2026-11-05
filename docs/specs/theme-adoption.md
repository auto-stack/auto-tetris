# 主题接入（theme-adoption）— 036-tetris / auto-tetris

> 来源：auto-os/PLAN-060（桌面游戏三产品正式主题接入，主合同）。
> 消费形态与宿主策略定义见 OS `docs/specs/shell/host-theme-policy-and-delivery.md`；
> 批次登记见 OS `docs/specs/apps/product-theme-batch-060.md`。本页只记本产品
> 的实际表面与合法固定值，不重复宿主机制。

## 接入形态（2026-11-05，PLAN-060 T-02）

- `vendor/themes`：UI 管理渠道固定版本快照（themes 0.2.0，内容 digest
  `9fa07742dc68aa5377ae06cb2d966386002063f184c515b6c5dddf8a6bef838e`，per-file
  sha256 与源包逐文件校验同律；不可二次编辑、非第二权威源）。
- pac.at：原显式 `theme: "dark"` 键退役 = **follow 宿主**；`accent: "indigo"`
  保留（品牌豁免）；`dep themes { path: "vendor/themes" }`。
- app.at：`use themes.themes: Auto` + `design { theme: "Auto",
  mode: if .dark_mode … }`；App 级 `dark_mode` 位（Plan 458 契约变量名），
  种子链 AUTO_UI_THEME > os-config > 系统主题。
- 本产品壳原已用语义 token（bg-background/bg-card/bg-secondary/…）——映射
  面即 `border-slate-700`（棋盘框边）→ `border-border` 一处。

## 合法固定值（内容身份豁免，不随主题）

- **七种方块分类色**（`tetris_store.at` `colors`，I=cyan/O=yellow/T=violet/
  S=emerald/Z=rose/J=blue/L=orange 系）：规则/分类身份，
  docs/source-README.md 色彩契约原样（accent 只影响品牌控件）。
- **方块渲染域（井+预览）暗底** `bg-slate-950`/`border-slate-800`：亮色方块
  可见性身份（对比域），类比 calc 运算符色豁免。

## 已知非本批红（具名，owner=auto-lang）

- a2r rust 后端 codegen：`src/back/db.at` 的 `raw[i].to_int() ?? 0` 生成
  `.parse::<i64>().unwrap_or(0).unwrap_or(0)` 链（E0599 ×3）——在冻结工具链
  （auto-man 0.1.0+plan-890 r7 t19-18 g03bb65e）与**基线提交 06b2e67f 同败**
  （probe/tetris-base 复测），非主题接入引入。本批主题门走
  `auto run -r vm --server vm` 纯 VM 分体轨（source-README 既有支持模式）；
  rust 轨原门（tracked rules_golden fixture 的 `cargo test -p tetris
  --test rules_golden --no-default-features --features ui-iced`）另行执行。
  owner=auto-lang 后端生成；关闭条件=该 `??` 模式 a2r 修复。

## 验证入口

- 本批定向反控：`tests/test_060_theme.py`（leg A 显式暗 / leg B 显式亮 /
  leg C Solarized-dark 跟随 / leg D 开始→暂停后活跃局中换肤业务守恒+活体
  翻转实测生效 / leg E 重开追最新；oracle=官方 token 像素占比 ≥5%，fit 窗
  运行态边条不做单点采样；`AUTO_BIN=<auto>` python tests/test_060_theme.py，
  证据在 `D:/autostack/plan-artifacts/plan-060/auto-os/tetris`）。
- 分体模式 MCP action 元素地址格式：`vnode_<id>`（字符串）——数字裸 id 在
  split 轨不投递（merged 轨两者皆可）。
- 原门分母（不动）：`pnpm --dir tests test`（smoke.spec.ts）、
  `python tests/desktop_mcp.py`（需外部 `auto run -r vm --server vm` MCP 端点）、
  `python tests/run_matrix.py --suite …`、`python tests/vm_rules_golden.py`、
  `python tests/native_physical.py`、`python tests/gallery_contract.py`、
  tracked fixture `cargo test -p tetris --test rules_golden --no-default-features
  --features ui-iced`。
