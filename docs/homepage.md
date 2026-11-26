# 首页维护

「首页」维护页首、左栏的赛季、活动和站点统计，以及右栏的最近更改和最新评论。「模板:TD2首页导航」维护右栏分类。普通编辑者可以使用这两页的「编辑源码」和「显示预览」。灰机顶栏提供站内搜索和 Ctrl K 快捷键。

## 修改栏目

每个栏目在「模板:TD2首页导航」中占一行。示例见下方。

```wikitext
{{TD2首页入口|名称=装备|图标=TD2-Gear-Chest-Icon.png|目标=装备索引}}
{{TD2首页入口|名称=技能|图标=TD2-UI-ModUtility-Icon.png}}
```

移动整行即可调整顺序。新增栏目时填显示名和已登记的图标文件名；栏目有可读的总览页时再填「目标」。删除栏目时删除整行。模板末尾三个无参数调用供四列、三列、两列矩阵补齐尾行，编辑者无需计算空位。每个补位只显示细线叉号，读屏和 Tab 顺序均略过。

| 栏目 | 总入口与细分类归属 |
| --- | --- |
| 装备 | 「装备索引」调用「TD2装备导航」。品牌套装、装备组、具名装备、奇特装备由原 Navbox 维护。 |
| 武器 | 「武器索引」调用「TD2武器导航」。顶级武器、具名武器、奇特武器、特有武器沿用该索引的分组。 |
| 天赋、技能、获取与制作、专精 | 保留图标与名称。各总览页具备可读内容后，在对应行填写目标。 |
| 玩法与活动、世界资料、实用工具、感谢名单 | 同上。例如 DPS 计算器可以收录在建成的「实用工具」索引内。 |

## 赛季与当日活动

首页调用 `{{TD2首页消息栏}}`。赛季和活动跟随原生日程，缺少条目时各自保留标题和一行空状态。[消息栏模板](../wiki/templates/TD2首页消息栏.wiki)

赛季沿用游戏日程的 UTC 时间。生成器按 Registry 中的赛季 UID 找到 wrapper，从中读取赛季编号、简体中文名称，并核对宣传图和徽章。更新原生导出及对应的两张图片登记后，运行 `python -m tools.homepage_season --write` 更新日程，省略 `--write` 可检查一致性。原生日程（本地 `resources/game/current/raw_files/hunter/game system data/juice/scheduling/season_wrapper_schedule.mgameschedule`） · 当前赛季定义（本地 `resources/game/current/raw_files/hunter/game system data/juice/seasonwrapper/seasonwrapper_y8s3.mseasonwrapper`） · [生成的首页日程](../wiki/modules/TD2赛季日程.lua)

封面下方居中显示赛季编号与名称，以及周、日、时倒计时。蓝环中央使用赛季定义 `mySeasonPassIcon` 指定的徽章，环下的结束时间随读者设备时区换算，时区未知或无脚本时显示北京时间。蓝环按「已过时间 ÷ 赛季总时长」从十二点方向顺时针填充，白色方块标出弧尾。首次渲染和浏览器更新均使用同一组赛季起止时刻，结束时切入下一条已登记赛季或空状态。[赛季模块](../wiki/modules/TD2首页赛季.lua)

活动覆盖已登记赛季的赛季活动、全域事件、日历公告及启用的限时计划。中文名称按活动 UID 读取，起止时刻来自赛季内的偏移与持续天数，或计划池的绝对时间。一条限时计划链在轮播中占一张卡。更新解包与配图登记后，运行 `python -m tools.homepage_events --write` 生成活动日程，省略 `--write` 可检查一致性。[活动生成器](../tools/homepage_events.py) · [活动日程](../wiki/modules/TD2活动日程.lua)

日历使用各条目的海报或公告背景。中央公园活动的公告直接指定 `dlc3_event_timeline.dds`。限时计划优先取自身的背景覆盖，否则按活动槽查所属计划来源。“牧羊人”活动的六步计划都使用行动基地来源的 `projects_ui_nz_boo.dds`。中央公园公告（本地 `resources/game/current/raw_files/hunter/game system data/juice/seasonwrapper/seasonwrapperannouncements.juice`） · 牧羊人计划（本地 `resources/game/current/raw_files/hunter/game system data/juice/projects/projects.juice`） · 计划来源与底图（本地 `resources/game/current/raw_files/hunter/game system data/juice/projects/projectsources.juice`）

活动日程的海报按游戏的 450 × 600 画框显示。顶部黑条持续显示「进行中」与剩余时间。深色底栏显示类型、名称和图标，鼠标悬停时变为橙色并沿海报向上展开，停在中心徽记外圈下方。鼠标移开即收起。活动类型取原生中文本地化，图标按定义中的图集与 Sprite ID 关联已登记的图片。游戏用完整纹理坐标填充图片区，因此解包中以方形保存的日历图在网页上也按 3∶4 显示。手动填写的普通图片保持自身比例并裁入同一画框。游戏日历面板绘制（本地 `resources/game/current/raw_files/hunter/nodes/compounds/seasons_event_panel.mcompoundnode.decompiled`） · 游戏网格单位（本地 `resources/game/current/raw_files/hunter/global variables/aa40fd0e595106850000420b4c230577.mvar`）

到开始时刻显示，到结束时刻撤下。剩余时间在首次渲染和浏览期间都按结束时刻计算。悬停剩余时间可查看完整起止时间，浏览器按读者时区显示，无法识别时区及无脚本时使用北京时间。打开的页面会在活动边界更新。多项每 12 秒轮换，鼠标悬停或键盘焦点在轮播内时暂停，Q/E 和方点可手动翻页。减少动态效果时手动翻页，无脚本时顺序显示渲染时正在进行的活动。编辑者仍可用消息栏的「活动」参数覆盖默认日程。[活动模块](../wiki/modules/TD2首页活动.lua) · [消息卡](../wiki/templates/TD2首页消息卡.wiki)

翻页时海报直接切换，底栏的活动类型、名称和右侧图标在 0.2 秒内从离散色块恢复。溶解时长取自游戏「最新消息」组件。启用减少动态效果时，翻页与底栏展开均即时完成。原生消息组件（本地 `resources/game/current/raw_files/hunter/ui/retained graphs/mainmenu_widgetinfonews.mretuigraph.decompiled`） · 原生溶解动画（本地 `resources/game/current/raw_files/hunter/ui/compounds/anim_triggereddissolve.mcompoundnode.decompiled`）

Steam 公告的接口、截图中的两条记录和灰机自动读取实测独立保存。Steam 公告接口验证（完整维护环境的查询记录）

## 页首、框体和布局

页首使用通栏华盛顿全景，官方英文 Logo 置于左下方，读屏名称为「全境封锁2」。正文宽度不超过 38rem 时调整取景，将纪念碑留在字标右侧。[官方 Logo](https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/2221490/logo.png) · [全景原图](https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/2221490/library_hero.jpg)

装备用胸甲图标，武器用制作台的 `main_weapon`。实用工具借用笔记本剪影，感谢名单借用三人盾徽。

「世界资料」使用匹配界面「开放世界探索」的经纬网地球 `world_bracket`。「玩法与活动」使用主线任务的双六边形 `mission_main`。两者均从地图图集的红色通道提取透明剪影。对应图块在 1024 × 1024 图集中的左上角分别为 (64, 256) 和 (192, 64)，大小均为 64 × 64。原生匹配菜单（本地 `resources/game/current/raw_files/hunter/ui/graphs/megamap_automatchmakemenu.muigraph.decompiled`） · 图块定义（本地 `resources/game/current/raw_files/hunter/ui/spritesheets/ui_map_spritesheet.spritesheet.decompiled`） · 地图图集（本地 `resources/game/current/images/hunter/baked/ui/spritesheets/ui_map_spritesheet.png`）

「专精」使用维修站的折线放大镜 `Research_icon`。统计区关注数使用配装图标选择器中的凤凰 `loadout_11`。制作台图集（本地 `resources/game/current/raw_files/hunter/ui/spritesheets/ui_crafting_spritesheet3.spritesheet.decompiled`） · 配装图集（本地 `resources/game/current/raw_files/hunter/ui/spritesheets/ui_loadout_icons_spritesheet.spritesheet.decompiled`）

首页按需调用「Html:TD2首页样式」。单元使用 Reader 的 `td2-frame` 和「TD2边框角节点」。赛季栏、资料矩阵、「最近更改」和「最新评论」各自在顶部调用「TD2分割线」，两个方形端点与各自栏边对齐。单列时分割线随栏目排列。[分割线模板](../wiki/templates/TD2分割线.wiki) · [角点模板](../wiki/templates/TD2边框角节点.wiki)

有目标的单元复用 `td2-navbox-card` 和 `td2-navbox-name` 的整块链接与焦点框，悬停或聚焦即时切为橙底深色。矩阵通过 `td2-control-palette` 共享 Navbox 的控制颜色。`td2-navbox` 根类用于需要 Reader 移至词条页尾的导航箱。[Reader 样式](../ui/brand-sets/brand-sets.css)

功能方块的宽高比为 15∶16。图标框占单格内宽的 30%，图标和补位 X 的中心都位于格高的 53% 处。列数按首页正文可用宽度切换，在根字号 16px 时取下表数值。

| 正文宽度 | 外层信息 / 资料 | 资料矩阵 |
| --- | --- | --- |
| 大于 832px | 三等分，左占一份、右占两份 | 四列三行，末行补两个空位。 |
| 大于 608px，至 832px | 同上 | 三列四行，末行补两个空位。 |
| 大于 416px，至 608px | 左右两列等宽 | 两列五行。 |
| 至 416px | 单列，先完整信息栏、再显示资料区 | 两列五行。双环和两项读数居中。 |

## 真实数据与快照

「模块:TD2首页统计」把编辑数 `NUMBEROFEDITS:R` 放在圆心，对应内侧橙环。下方的页面数使用 `NUMBEROFARTICLES:R`，与「特殊:统计」的内容页面数一致，对应外侧紫环。读数及悬停时的目标均直接显示整数。每圈从十二点顺时针绘制，白色方块跟随弧末端。下一里程碑取严格大于当前计数的最小 2 的幂，弧长占比为「计数 ÷ 下一里程碑」。零和未知都显示空轨道，读数分别显示 0 和破折号。[灰机魔术字](https://www.huijiwiki.com/wiki/帮助:魔术字)

游戏道具栏引用 `styleguide_progressrings`。网页复用其轨道、弧宽、间距和等宽白色端点的关系。中心大数字参照启用等宽数字的 `Number 04`，按圆径缩放，长数字自动缩小。站点优先使用已安装的 Borda Medium，其次使用现有的 Sansation。本地预览从原生导出加载 Borda 数字。统计标题字号为「活动日程」的 1.6 倍，编辑数标签、页面数标签和页面读数均与「活动日程」同字号。环下方用「关注数:」和凤凰图标引出灰机 `NUMBEROFFOLLOWERS` 的实际读数。原生圆心文字（本地 `resources/game/current/raw_files/hunter/ui/compounds/styleguide_circlecentertext_new.mcompoundnode.decompiled`） · 字号预设（本地 `resources/game/current/raw_files/hunter/game system data/juice/ui/presetfonts.juice`） · 原生进度环（本地 `resources/game/current/raw_files/hunter/ui/compounds/styleguide_progressrings.mcompoundnode.decompiled`） · [首页统计模块](../wiki/modules/TD2首页统计.lua)

「最近更改」使用灰机原生 `<siteactivity style="log" limit="6" />` 显示最近 6 条动态。头像、包含作者和页面链接的动作描述，以及右侧的相对时间均由灰机组件排版。[灰机 Siteactivity](https://www.huijiwiki.com/wiki/帮助:解析器扩展标签#Siteactivity)

「最新评论」紧接「最近更改」，使用灰机原生 `<commentsoftheday />`。评论、回复及空状态均由灰机显示。[灰机 CommentsOfTheDay](https://www.huijiwiki.com/wiki/帮助:解析器扩展标签#CommentsOfTheDay)

本地生成器使用相同的页面、模板、Lua、Reader 样式和脚本。线上服务独有的计数与动态取自注明时间的公开站点快照（本地 `tools/homepage-preview-snapshot.json`），相对时间以采集时刻为准。目录中同时生成可点击的装备和武器索引。

```powershell
$env:TD2_LUA_TEST_PATH = (Resolve-Path '.cache/python').Path
& '.\.venv\Scripts\python.exe' -B -m tools.homepage_preview dist/home-review
```

`index.html` 可加载本地游戏数字字体，`release.html` 使用站点的字体设置，两者均渲染登记的首页原文。`empty.html` 展示赛季与活动的空状态。站点计数、最近更改和最新评论使用快照，赛季和活动默认跟随实际时钟。传入 `--as-of 2026-11-24T07:59:59Z` 可从指定时刻回放，省略时区时按北京时间解释。附加 `--skin-snapshot` 并指定保存有 `manifest.json` 和 `media/` 的站点备份目录可复现皮肤底图和字体。

源码副本使用 `--without-assets` 预览，省略本地图片和活动快照。

## 部署与回退

先按部署流程核对远端修订并备份。Registry 登记页首与导航素材、赛季和活动的配图及日程、Reader 资源、首页样式、统计模块与首页模板。回退时先还原首页及专用模板和样式。共享 Reader 文件按差异撤回首页调用并保留其他词条的修改。[部署流程](deployment.md)
