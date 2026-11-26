# Reader / Editor 数据与构建关系

Root 为 `WEB-TD2-Wiki`，所有维护源共用 Root Git。操作方法见 [装备维护](../../../../docs/equipment-maintenance.md)，构建命令见 [Editor 构建](../../../../ui/editor/production/README.md)。

| 内容 | 维护源与消费方 |
| --- | --- |
| 当前装备资料 | `wiki/pages/brands/`、`gear-sets/`、`exotic-gear/`、`equipment/`、`weapons/` 用 `资料ID` 关联固定事实，保存其他资料、天赋脚注与补充正文 |
| 固定资料 | `data/equipment/records.json` 保存各系列固定字段、型号、效果、关系与属性配置；`database.cjs` 定位，`projection.cjs` 生成 Reader 参数 |
| 效果 | 数据库按效果和模式维护，JS `page-effects.js` 与 Lua `TD2资料记录` 共享传输合同 |
| 公共规则和目录 | `data/brand-sets/`、`data/equipment/`、`data/gear-sets/`、`data/exotic-gear/` |
| 原生比较 | `tools/equipment/native.py` 投影已确认映射；`merge.cjs` 比较字段指纹，`import.cjs` 校验整批并写入 |
| 文本处理 | `parser.js`、`source-patches.js`；导入的 `page.cjs` 复用同一解析与补丁能力 |
| Editor 领域 | `local-session.js`、`mapped-domain.js`、`page-fields.js`、`mapped-ui.js` 共用人工字段、引用校验和表单 |
| 保存与预览 | `site-session.js`、`mediawiki-adapter.js`、`site-entry.js`、`reader-preview.js` |

Node 通过 `equipment-inputs.cjs` 直接读取 Root 数据。浏览器 Runtime 包含程序、人工字段合同和样式，打开 Editor 时只读取 `TD2编辑数据` 提供的实体身份摘要。`catalog.cjs` 同时生成 Reader 的 `TD2装备映射`、`TD2效果映射`；奇特逐槽资料由 `tools/exotic_gear/generate.cjs` 生成到 `TD2装备属性数据`。普通数据更新不要求发布 Runtime。

Reader 独立运行。品牌与奇特主模块在 `wiki/modules/`，装备组源在 `tools/gear_sets/reader.lua`；共享模板由各自 registry 所属生成器维护。导航生成使用 `navbox-records.cjs` 只读解析当前页面与数据库，不依赖 Editor Runtime。

武器由 `TD2武器.lua` 读取共享 `武器型号资料` 集合，具名是原版实体内的子记录；`weapons.py` 使用同一个装备 Navbox markup。固定参数和图片布局信息由 `weapon_projection.py` 经现有 importer 更新，Editor 仍只编辑人工字段。

正式构建为 `ui/editor/production/build.cjs`；`--verify-inputs` 检查完整输入集合与产物，不重新编译。`tools.brand_sets.production` 按 `publishing/reader-editor-production.json` 组装资源；Entry 根据实际 Runtime 回读绑定。当前发布状态只查 Root baseline 和回执。

测试从相关 `tests/test_*.cjs` / `test_*.py` 选择；Editor 集中入口为 `ui/editor/production/formal.test.cjs`。完整验证由 `tools.verify` 运行，固定样本不依赖完整游戏库或旧构建目录。
