# Reader 与 Editor 组件

页面数据、共享规则和程序分开维护。字段及操作方法见 [装备维护](equipment-maintenance.md)。

| 层 | 入口 | 职责 |
| --- | --- | --- |
| 原生投影与比较 | `tools/equipment/native.py`、`merge.cjs`、`import.cjs` | 解析已登记原生关系，比较语义字段，保留未变化或不可确认的内容 |
| 固定资料 | `data/equipment/records.json`、`tools/equipment/database.cjs` | 按实体身份维护各系列固定事实、型号与属性配置，导入与生成共用 |
| 文本结构 | `ui/editor/src/parser.js`、`source-patches.js`；`tools/equipment/page.cjs` | 解析嵌套模板、定位字段和稳定记录、局部写回与重开检查 |
| 页面效果 | `page-effects.js`；`TD2资料记录.lua` | 统一效果合同、关联与 Reader 展示 |
| 装备领域 | `mapped-domain.js`、`page-fields.js`、`mapped-ui.js` | 共用身份、人工字段与表单 |
| Reader | `TD2资料映射.lua`、`TD2品牌投影.lua`、`TD2装备组投影.lua`、`TD2奇特装备.lua`、`TD2武器.lua` | 组合共享模板与各系列结构，独立于 Editor 运行 |
| 公共展示 | `TD2装备槽行`、`TD2主属性列表`、`TD2天赋资料`、`品牌图纸列表`、`TD2材料行`、`TD2图标` | 属性、天赋、图纸、材料与图标格式 |
| 站点编辑 | `site-session.js`、`mediawiki-adapter.js`、`site-entry.js` | 最新修订读取、预览、冲突保护、保存与重开 |
| 共享目录加载 | `tools/equipment/catalog.cjs`、`TD2编辑数据值.lua`、`TD2编辑数据.lua` | 独立发布共享资料，Editor 打开时加载 |
| 样式与交互 | `ui/brand-sets/`、`ui/editor/editor.css`、`wiki/pages/site/Common.css` | 正式深色显示、字体、模式切换、折叠与编辑控件 |

装备组 Reader 模块维护源为 `tools/gear_sets/reader.lua`；生成到 Wiki 的文件归属由 registry 标记。品牌和奇特的主 Reader 模块直接维护在 `wiki/modules/`。

普通与具名装备共用部位和属性模板；装备组保留件数、胸甲/背包增强、核心力量三核心；奇特保留自身属性槽、多个天赋和重新配置图纸。PvE/PvP 面板只显示该模式已有内容。

武器共用一个 Reader 骨架。原版和具名子记录位于同一实体并上下排布，奇特武器与特有武器独立成页；使用共享品质标题卡、章节折叠、天赋与图标、属性行、图纸、获取、人工脚注和页面操作。天赋紧接属性之后、位于武器控制力之前，使用共享灰底标题和天赋正文模板；随机槽以中性正文显示「随机武器天赋」。固定天赋沿用装备组的两级缩进，描述的换行与段落共用基线。具名装备的固定天赋名称可用具名金，其他名称随正文或原文色标着色。各模式保留各自的正文、图标与脚注。完整武器图按原始透明边界排版，保留全部非透明像素，原图文件不裁剪、不重绘；内联宽度受原图有效像素限制，点击使用共享图片查看器。`weapons.py` 复用装备 Navbox 的 markup；武器当前项同时比较页面与自然名称锚点。

装备导航从当前页面和固定资料数据库解析名称与关联，配置只负责排序与展开。`TD2图标` 保留冻结资源映射，图片可用性由对应场景判断。站点 Infobox 是外部基础组件，项目维护自己的参数和样式。

同一型号和模式下，相邻固定天赋共用正文细分隔线。装备组的件数奖励和部位增强沿用各自的分组标题。资料词条的导航使用 214 px 列和 60 px 卡片，容器窄于两列时使用单列。最后一个正文区块与导航标题的间距由导航上方的 2 rem 控制。

Node 使用 `equipment-inputs.cjs` 直接读取本地目录；浏览器只加载 `catalog.cjs` 生成的实体身份摘要。完整固定事实由 `projection.cjs` 生成 Reader 数据模块。Runtime 只包含程序、人工字段合同、样式与工具链，普通数据更新不改变 Runtime 版本。

## 属性机制链接

`TD2资料记录.lua` 的 `attributeLinks` 集中维护稳定属性 ID、允许的完整属性名称及经 Registry 核实的目标页面标题。`body` 渲染品牌/装备组效果，`attributeName` 供生成的 `TD2词条名称`、`TD2次属性名称` 使用；后者也覆盖具名和奇特装备的固定词条。名称模板的生成源是 `tools/brand_sets/build.py`。

增加关联时先核实目标身份，再添加映射；映射直接使用已核实的页面标题。当前 `bonus_increased_threat` 的“威胁度／提升威胁度”和 `minor_attribute_reduced_threat` 的“降低威胁度”将完整属性名称链接到“威胁度”（Registry ID `mechanic-threat`）。新增关联也统一链接完整属性名称；数值、单位和描述不变。未知 ID、未登记名称、天赋名称、人工正文均不做替换。链接继承所在属性的颜色，并提供下划线和键盘焦点。

## 公共页面操作

默认加载的 `Gadget:TD2Reader.js` / `TD2Reader.css` 在主命名空间阅读页面的 `#firstHeading` 挂载唯一 `#td2-page-actions`，包括无装备容器的人工词条。特殊页面、讨论、模板、编辑操作不挂载；历史/差异视图只提供当前词条的复制链接。

背景由 `ui/brand-sets/brand-sets.css` 统一管理，以灰机页面的 `body.ns-0.action-view` 覆盖所有主命名空间阅读页，沿用装备页的背景图、灰度处理和渐隐效果；`body`、`#wiki-outer-body`、`#wiki-body` 设为透明，避免皮肤的灰色正文底板遮住背景。装备 Reader 与表单编辑器仍匹配同一组规则，本地 Reader 预览也可复用，无需修改各词条。

游客和普通用户只有“复制链接”。管理员入口要求当前有效组包含 `sysop`，并通过 `action=query&meta=userinfo&uiprop=groups|rights&prop=info&intestactions=edit` 核实账号、页面 ID、完整标题、`edit` 权限和该页 `actions.edit`。权限未知或请求失败时不展示编辑操作。复用皮肤的源码编辑链接，无此链接的皮肤由同一框架生成。

“编辑表单”仅接纳现有 `site-entry.js` 核实顶层模板、页面合同和权限后生成的入口，不按名称、装备容器或单纯模板转入推断。`mediawiki-adapter.js` 仍在保存前重新核实管理员身份、实际编辑权、账号及最新修订；公共按钮不改变保存合同。

“复制链接”优先复制灰机分享菜单所称的“pid 链接”，格式为 `/p/页面ID`。通过官方 `mw.huijiApi` / `$cockpitUtil.getPageUrlById(pageId, 'td2')` 生成；工具未加载时使用已核实的官方路由，同站 `index.php?curid=ID` 也可归一到该路由。仅接受正安全整数 ID、同源且同 ID 的结果，异常时使用 canonical 完整页面链接并移除锚点。`/p/ID` 打开同一页面身份，不要求地址栏跳回 `/wiki/标题`。复制在点击事件内启动，保留移动端用户激活；使用 HTTPS 页面提供的 Clipboard API，按钮反馈“成功复制／复制失败”；权限拒绝或接口不可用时不会误报成功。

### 服务端编辑限制

按钮和 JS 保存检查不能阻止用户直接访问 `action=edit` 或调用编辑 API。灰机普通注册组没有 `edit`，但 `verified` 认证用户有；页面未保护时，仅发布 Reader 不能实现“只有管理员能写”。上线此策略前必须同步配置服务端限制，且保留灰机平台管理人员的既有管理权限。

主命名空间整体限制应由机长联系灰机平台管理员，为 TD2 站点合并以下 MediaWiki 配置（保留已有命名空间限制）：

```php
$wgNamespaceProtection[NS_MAIN] = array_values(array_unique(array_merge(
    $wgNamespaceProtection[NS_MAIN] ?? [], ['editprotected']
)));
```

`editprotected` 在 TD2 由管理员、机长及相应平台管理组持有，认证用户和高级用户不持有；不要仅移除 `user` 的 `edit`，权限组会叠加。该配置由灰机托管服务端维护，不能写进 Common.js、模板或零件；官方机长室功能文档未提供可自行修改这项设置的开关。平台尚未配置时，可通过页面左栏“保护”，将编辑等级设为“管理员”、期限设为永久；页面保护只覆盖已处理的页面，后续新页面仍需保护，故不是全站长期策略。

配置后以管理员、非管理员认证用户、游客分别检查正文、源码编辑入口、表单入口和 `intestactions=edit`；在获准的测试页确认直接编辑 API 也拒绝非管理员写入。仅前端模拟测试或按钮隐藏不能作为服务端验收。本地改动不自动应用上述线上配置。

官方依据：[编辑页面](https://www.huijiwiki.com/wiki/帮助:编辑页面)、[用户权限](https://www.huijiwiki.com/wiki/帮助:用户权限)、[cockpit 组件](https://www.huijiwiki.com/wiki/帮助:使用cockpit组件)、[保护页面](https://www.huijiwiki.com/wiki/帮助:保护页面)、[可配置的站点功能](https://www.huijiwiki.com/wiki/帮助:可配置的站点功能)、[MediaWiki 命名空间保护](https://www.mediawiki.org/wiki/Manual:$wgNamespaceProtection)。
