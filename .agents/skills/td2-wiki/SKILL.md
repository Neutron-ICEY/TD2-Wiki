---
name: td2-wiki
description: 为 TD2 Wiki 工程任务定位维护源、发现已有工具、梳理跨模块关系并复用现有能力。适用于 Reader、数据 Catalog、JS Editor、资源查询及发布准备的入口定位；简单文案修改无需完整项目调查。
---

# TD2 Wiki 工程导航

按任务选取相关维护源与工具入口；权限及操作规则见 [AGENTS](../../../AGENTS.md)，工程总览见 [README](../../../README.md)。本 Skill 仅提供导航，普通小修改不因此增加全量调查或验证。

| 任务 | 入口 |
| --- | --- |
| 装备资料、导入、线上改动回收 | [装备维护](../../../docs/equipment-maintenance.md)；`tools/equipment/native.py`、`import.cjs`、`sync.cjs`；`data/equipment/records.json`、`native-map.json`、`native-baseline.json` |
| Reader、模板与 Lua | [组件关系](../../../docs/td2-reader-component-architecture.md)；`wiki/templates/`、`wiki/modules/`；装备组 Reader 源为 `tools/gear_sets/reader.lua` |
| Reader 样式与交互 | `ui/brand-sets/brand-sets.css`、`brand-sets.js`；主命名空间阅读页的深色背景由 Reader CSS 维护，站点公共字体为 `wiki/pages/site/Common.css`；桌面端设计基线见 [组件关系](../../../docs/td2-reader-component-architecture.md) |
| JS Editor、共享数据与构建 | [组件关系](../../../docs/td2-reader-component-architecture.md)、[Editor 构建](../../../ui/editor/production/README.md)；`ui/editor/src/`、`ui/editor/production/build.cjs`；`tools/equipment/catalog.cjs` |
| 稳定身份、页面与图片地址 | `publishing/registry.json`；`tools.identity` / `tools/identity.cjs`；[装备维护](../../../docs/equipment-maintenance.md)、[图片命名](../../../docs/IMAGE-NAMING-STANDARD.md)；当前地址从稳定 ID 解析 |
| Wiki 首页与资料索引 | [首页维护](../../../docs/homepage.md)；`wiki/pages/site/首页.wiki`、`wiki/templates/TD2首页导航.wiki`；本地预览 `tools.homepage_preview` |
| 装备导航 | `tools/brand_sets/navbox.py`、`navbox-records.cjs`；`ui/brand-sets/equipment-navbox.json` 负责排序和展开 |
| 武器页面与导航 | [装备维护的武器资料](../../../docs/equipment-maintenance.md#武器资料)；`tools/equipment/weapon_projection.py`、`weapons.py`、`weapons_preview.py`；`TD2武器.lua` 消费共享装备记录。武器地址按顶级、具名、奇特、特有加前缀，具名入口重定向至原版页锚点，详见装备维护的「稳定身份与地址」 |
| 图片、Sprite 和图集查询 | [资源工具](../../../tools/asset_import/README.md)；`tools.asset_import.library` 及 `data/asset-import/batches.json` |
| 文本、UID/GUID、原生定义 | 同一资源工具文档；`tools.asset_import.text_library`、`text_evidence.py`、`data/asset-import/text-sources.json`。简体来源为 `game-simplifiedchinese-menus`，英文为 `game-english-menus` |
| 原始资源更新 | [资源更新](../../../docs/game-resources.md)；日常 `tools.hunter_cli bulk --profile daily` → `tools.version_update run`，持久原生索引 `tools.version_update activate-index`，底层事务入口 `tools.game_resources`；失败按原计划重试或 `recover`。可选 `--report-duplicates`；定向未筛选导入用 `--unfiltered`。成功前保留计划与导出；当前库 `resources/game/current/` |
| Hunter 全量和定向导出 | [Hunter](../../../docs/hunter-cli.md)；`tools/hunter_cli/`。先核对运行条件、明确范围和 GUI 操作权限 |
| 本地预览与验证 | 装备维护文档的预览命令，源码副本可用 `--without-assets`。公开验证 `tools.verify --public`，完整维护工程的离线构建预检 `tools.verify --preflight`，全量回归 `tools.verify` |
| 离线发布准备 | [部署](../../../docs/deployment.md)、[发布契约](../../../docs/publishing-contract.md)；`tools.publish`、`tools.brand_sets.production` |
| GitHub 协作 | [双向同步](../../../docs/github-sync.md)；从协作仓库运行 `tools.github_sync`。外部材料的来源和许可见 [RIGHTS.md](../../../RIGHTS.md) |
| 图片命名与上传 | [图片命名](../../../docs/IMAGE-NAMING-STANDARD.md)；精确目标按 registry 和冻结资产目录核对 |

以当前源码确定功能，以 registry / production 配置确定维护对象，以 baseline / 回执确定最后确认发布状态。本地候选与历史记录不能替代新一次线上观察。
