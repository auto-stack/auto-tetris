# auto-tetris

俄罗斯方块，使用 AutoLang / AutoUI 开发的独立应用。

本仓是首批产品源码基线；当前能力以导入版本为准，仓库描述中的产品方向不表示全部已实现。

## 运行

安装对应版本的 `auto` CLI 后，从本仓根执行：

```sh
auto run
auto run -r vm
```

前端端口：`17844`。后端端口：`17845`。

源码包含原生桌面制品声明；clone 后不附带 exe，使用 `auto build -r rust` 生成后再使用原生制品路径。

## 来源与组合

来源提交、路径与文件 hash 见 `SOURCE-IMPORT.json`。首次导入提交保留在 `source-sync` 分支；完整 v0.5 恢复后从该基线导入差异，再与产品开发线合并。

AutoOS 通过 [`apps/036-tetris`](https://github.com/auto-stack/auto-os/tree/v0.6-dev/apps/036-tetris) submodule 固定本仓版本；教学 Demo 保留在来源仓。


## 主题

官方主题包正式接入（auto-os/PLAN-060，主合同与宿主策略见 auto-os 仓
`docs/specs/shell/host-theme-policy-and-delivery.md`；本产品表面、合法固定值与
已知 a2r 后端生成红见 [`docs/specs/theme-adoption.md`](docs/specs/theme-adoption.md)）。
pac `theme` 键缺省 = follow 宿主；`vendor/themes` 为 UI 管理渠道固定快照，不可二次编辑。

已有测试随源导入；端口与平台相关测试需要按本仓配置准备运行环境。安装/启动与双端完整功能验收是不同检查项。
