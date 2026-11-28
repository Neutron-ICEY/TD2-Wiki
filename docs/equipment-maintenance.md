# 装备资料维护

固定解包内容保存在 `data/equipment/records.json`，页面引用和人工维护内容保存在 `wiki/pages/brands/`、`gear-sets/`、`exotic-gear/` 和 `equipment/` 的结构化 WikiText。Reader 消费固定事实与页面内容，Editor 只加载页面身份和人工字段。游戏数据更新先投影和比较，再修改已登记的字段。

## 稳定身份与地址

实体 ID 和原生 UID 保持独立；显示名只来自游戏资料字段。`publishing/registry.json` 以 `related_entity` 关联实体，以 `id` 标识页面登记，以 `title` 和 `source` 分别维护线上标题和本地路径。装备目录不重复保存页面地址，`tools.identity` / `tools/identity.cjs` 提供只读解析。

装备主空间使用 `类型前缀-游戏简体中文原名`。品牌套装、装备组、奇特装备、装备规则、材料和指南沿用各自前缀。武器依据型号的 `kind` 使用 `顶级武器-`、`具名武器-`、`奇特武器-`、`特有武器-`。顶级、奇特和特有武器独立成页。具名武器按原生 UID 挂靠原版，登记的具名入口直达原版页内的游戏名称锚点，例如 `具名武器-左边` 指向 `顶级武器-ACS-12#左边`。卡片保留游戏原名。`tools.equipment.weapons generate` 从 Registry 和型号归属生成重定向及导航。同类型同名者须核实后在标题末尾用全角括号标明所属者、部位或用途。标题、源文件名或译名变化不重新生成稳定 ID。Windows 不支持的文件名使用安全显式路径，由 Registry 关联。

常规正文改名登记在 `publishing/pending-moves.json`，通过 MediaWiki 移动保留历史和旧地址重定向。短标题 `煽动者` 继续指向 `奇特装备-煽动者`，同名奇特突击步枪使用 `奇特武器-煽动者`，具名射手步枪由 `具名武器-煽动者` 进入 `顶级武器-定制 M44#煽动者`。

Navbox 的名称来自原始资料，链接从实体 ID 解析；排序配置保存实体 ID，部位与具名锚点保持原有稳定键。图片按 Asset ID 解析，规则见 [图片命名](IMAGE-NAMING-STANDARD.md)。材料显示目录以已有材料键或 `currency:<原生UID>` 为键，`name` / `aliases` 只作显示；材料行显式传 `材料ID` 或所属实体 ID。

导入审核输出用登记 ID 命名，避免不同目录同 basename 覆盖。正式导入前整批验证 Registry 身份、目标与所有权；持久化时剥离由 Registry 派生的地址。运行 `python -B -m tools.identity` 与相关生成检查。

## 数据归属

| 内容 | 维护位置 |
| --- | --- |
| 页面身份与人工内容 | 页面通过 `资料ID` 关联固定身份，WikiText 只保存其他资料、天赋脚注和补充正文 |
| 名称、原生简介 | `data/equipment/records.json` 中实体的 `fields` 与 `collections` |
| 图纸、固定目标、随机候选、材料身份 | `data/equipment/crafting.json` 按原生 UID 保存；Reader 从装备记录派生目标名称，不再逐页登记图纸名称或图纸 ID 列表。尚未闭合的旧字段保留在 `records.json` |
| 材料名称、制作与分解 | `crafting.json.currencies` 是名称维护源；公共 Catalog 的显示名称由导入器同步。制作货币及物品要求保留原生规则；分解最终产量继续使用已有公共 Catalog 与实测修订 |
| 型号与具名身份 | `collections` 中的 `装备UID` / `stable_id`；所属品牌直接由父实体派生 |
| 核心、次属性与插件槽 | 品牌、装备组、具名用 `rules`；每个部位或具名单独定位。奇特用稳定 `槽位ID` 的 `slots`，随机池及显示值复用 `attributes.json` |
| 天赋、加成及模式关系 | `effects` 按 `效果ID + 模式` 保存正文、数值、图标、件数、部位、所属装备和依赖 |
| 攻略与正文 | 页面 `其他机制`、装备组和奇特装备 `天赋脚注:<效果ID>:<模式>` 及补充正文 |
| 获取分类与依据 | `crafting.json.routes` / `sources` 保存原生关系；`acquisition-methods.json.native_route_rules` 登记公共入口、分类与短文案，`blueprint_source_rules` 对应已有证据的原生来源家族 |
| 公共属性名称和单位 | `attributes.json.identities` 是 32 项身份的唯一维护源；`display_alias` 保留中文别名。原有核心、次属性和 UI 名称是派生兼容视图，消费者直接读取统一身份 |

固定资料的纠正入口是所属数据文件：单件资料在 `records.json`，图纸关系与材料名称在 `crafting.json`，共用属性、特殊预设和图标在原有 Catalog。材料名称修订后再执行一次原生导入以同步公共显示目录；原生未变会保留该修订。修改后运行生成命令。Editor 根据页面身份加载资料，只编辑人工内容。

Editor 按天赋脚注、其他资料、补充正文、编辑摘要的顺序提供人工编辑，并提供预览、保存等操作。天赋脚注按页面资料 ID、稳定效果 ID 和 PvE / PvP 独立关联，不改游戏描述，不跨模式回退。原生更新移除或更换效果 ID 时，旧脚注保留在页面并阻止表单保存，须人工核对身份后迁移。具名装备、图纸及获取分类由 Reader 展示；具名和图纸按自身 UID 关联，公共规则不构成品牌继承。

Reader 按实际途径逐行显示。普通、定向和开放世界活动奖励池中的常规掉落归为“战利品掉落”，暗区来源归为“暗区战利品掉落”。经核实跨活动反复发放的物品可显示“活动获取”。贮藏箱、商人、任务、行动、计划和制作分别列出。单次赛季、特定限时活动、预购窗口和入口待核实的记录保存在调查数据中。

图纸按配方 UID 分为制作、重新配置、外观转换，再关联产出 UID。已解锁配方的制作能力与图纸当前的发放入口分别核对。外观转换还须解析投入武器，重新配置用于已有物品。奇特装备与奇特武器按实际图纸用途分组，其他条目直接列来源。无获取资料时显示“暂无获取资料”，无图纸时显示“无制作图纸”。特有武器只显示对应专长的武器获取方式。已确认不存在的图纸由配方 UID、目标 UID 和证据共同排除。

既往赛季或旅程的图纸可用于核实玩家已解锁的制作能力。需同时核对发放入口、配方 UID、已开放的排程及当前制作目标。核实新的开放批次后，更新 `acquisition-methods.json` 的 `recipe_grants_verified_through` 日期；该日期只用于判断已有配方的制作能力。

`rules[].core` 分别记录 `count`、`selection`（`fixed` / `random`）、`types`。固定多核心表示同时存在；随机配置表示从候选中取得指定槽数。`minor.count` 是实际次属性槽数，`minor.fixed` 是固定预设，其余槽位使用公共随机池；奇特的逐槽规则可以引用不同候选池。`mods` 独立保存插件槽数。

基础装甲、属性显示值、图标资源、材料规则、随机品牌制作等继续直接消费现有公共配置。装备事实只维护一份，生成器为各 Reader 转换参数。显示名不承担身份职责。

## 原生更新

原始资源更新见 [game-resources.md](game-resources.md)。`tools.equipment.native` 读取当前导出的定义、本地化文本、参数和模式覆盖，按 `data/equipment/native-map.json` 的已确认映射生成投影。

从仓库根目录运行，`$py` 按 [README](../README.md) 或 [AGENTS](../AGENTS.md#python-与验证) 指向项目 Python 3.12+ 解释器（单独执行 `import.cjs --write` 且未激活 `.venv` 时，先设置 `$env:TD2_PYTHON = $py`）：

```powershell
& $py -B -X utf8 -m tools.equipment.native --output dist/update-input.json
node tools/equipment/import.cjs dist/update-input.json dist/update-review
```

查看 `result.json` 的具体字段变化、`catalogs` 和 `unavailable`，核对输出的 `records.json`、`data/` 下的公共目录及变化页面。确认投影范围后，用一个新目录执行同一命令并加 `--write`，同时更新数据库、公共目录、页面和原生基准。写入前检查整批路径、身份、结构和输入是否发生变化。导入前先完成下一节的线上修改回收。

本地写入用 Python 标准库加进程锁。导入器先固化审核产物和各目标的前后哈希，逐文件原子替换页面、实体和公共目录，核对整批落盘后最后更新原生基准。若写入中断，保留原投影、审核目录及 `.cache/equipment-import/pending.json`，用相同投影和参数重跑 `--write` 即可续写原批次。若尚未形成待续批次，使用全新的审核目录重跑。并行编辑导致目标与两个已审核版本均不符时，命令会指出文件并停止；保留人工版本，先与该批审核产物核对再续写。

`native-baseline.json` 保存每个语义字段或关联组的指纹。比较规则为：

- 首次建立基准（包括新接入的字段）时保留已有内容；`--initialize` 用于明确重建基准，不能当作普通更新选项。
- 原生语义未变，保留当前值；变化时只替换对应字段。映射字段更新数据库，其他字段更新所属页面。
- 当前没有内容的新增字段、稳定记录正常插入；新实体先登记页面、映射及必要身份，再导入。
- 缺文件、缺文本、关系冲突、未知格式等产生 `unavailable`，保留已有字段及旧指纹。导出缺失不会删除实体、字段或记录。

数值只比较描述实际引用的参数。PvP 覆盖单独解析。型号按 UID、属性槽按原生槽名映射后的稳定 ID、效果按页面稳定 ID 定位；数组顺序、其他记录或人工说明不会扩大覆盖范围。原生天赋引用变化时沿已登记的引用查找新目标，无法确认的目标保留旧内容。

天赋通过声明的父定义解析继承，子级显式字段或集合优先；基础参数、PvP 参数覆盖和说明覆盖分别选择。覆盖类型使用原生枚举及其默认值，说明只引用该模式实际使用的参数。解析器修正时，先对同一份原生输入比较修正前后投影，确认旧指纹与修正前一致，再只校正受影响字段的基准并保留当前资料；不能把解析差异当成游戏更新。新恢复解析的字段按首次基准处理。

核心配置作为关联组比较，次属性槽数和插件槽数独立比较。`rules.py` 沿 ArmorItem 的配置 UID、当前 code1/data23 定义及继承读取规则；型号之间不一致的字段保留原值并报告。已有属性槽与随机池关系继续独立更新。PvP 明确没有覆盖时复用基础定义；覆盖存在但无法解析时保留现有 PvP 内容。

新映射必须以原生身份和引用核对，不仅靠同名。品牌型号排除原生内部名含 `milestone` 和 `level数字boost` 的奖励或直升预设；制作变体保留真实制作目标和图纸关联，不能仅按显示名合并。完整工程用 `evidence/equipment/excluded-salvaged-models.json` 保存已确认的 29 个回收型号 UID。

`crafting.py` 扫描当前 Hunter / Rogue 的装备和图纸定义，沿继承、`myCraftedItem`、`myPossibleCraftedItems`、`myGearBrand` 与 `GearSet.myItems` 解析已登记装备的关系。制作变体可以通过唯一品牌 UID 归属补齐；新页面和归属冲突仍需登记或核对。模板、空标签图纸不会被当成有效制作记录；`myIsObtainable`、制作条件、品质覆盖和等级上限独立保留。图纸定义存在不等于现在可以获得。

`crafting.json.sources` 保存 SourceInfo 标签条件、引入等级、本地化和人工核实记录。`routes` 保存入口、实际发放对象、表、目标 UID 和已核对的条件。每次导入按来源组重算，原始文件缺失或无法解析时保留旧组并报告。物品定义、标签或单独出现的奖励对象均不足以证明可获取。

`source-relations.cjs` 按入口与目标 UID 核对装备／图纸身份，逐条验证资格、正权重及条件。奇特箱、重建箱与图纸商人在原生投影时还检查实际父组的掉落概率：省略时使用原生默认值 100，零概率候选标为入口禁用，不选中获取分类，也不能由通用来源提示恢复；概率无效或存在未解析的动态修正时报告未闭合，保留旧关系组。商人条件仍属于各张图纸，不能互相替代。等级、持有物品、世界进度、暗区、AND／OR 和否定使用公共解析；`native_drop_sources.py` 沿普通 NPC 的难度表和主装备池、定向轮换的部位表及公共父条件验证可满足的运行场景。正权重、实际列表引用、原生可掉落资格和排除标签均须满足；未知条件、缺失父级及奖励触发链仍留在后台。

`acquisition.cjs` 的 `resolve` 先按成品和配方 UID 判定，返回可展示的入口和被排除的原因，再按页面汇总。`availability` 用于原生入口和按 UID 保存的确认记录。SourceInfo 按图纸 UID 与实际奖励或库存交叉核对。`permanent`、`recurring` 和持续生效的组合包权益可展示，`limited` 和未核实来源保留在后台。混合首领须有各自的常设入口，贮藏箱须有独立供应证明。新入口未登记有效性时保持待核实。

`native_special_sources.py` 核对商人配置、实景位置、轮换和库存，并按箱子 UID 保存供应关系。`native_blueprint_rewards.py` 保留有日期的赛季奖励和扩展轨道。`native_cache_rewards.py` 从常规经验奖励与商人货位追到箱子 UID，核对箱内的具体掉落表、品质及物品资格。当前赛季货位由当季奖励表与纺织品轮换库存交叉识别。开放世界活动从解锁标志、活动结算、奖励组逐层跟到物品列表，保留适用范围和原始奖励池。

`acquisition-methods.json.confirmed_equipment_sources` 保存按装备 UID 核实的成品来源，必须有 `current_confirmed` 和具体依据。原生链未闭合时须有明确实测，不能用同名文件或候选标签填入。尚未接入自动解析、但已定向核对完整原生奖励链的来源可标记 `evidence_type: "native_chain_review"`；依据须包含任务/活动与奖励引用、实际发放项、目标 UID、条件和 schema 默认值，不能记为用户实测。这些记录只补充对应装备的显示，不改变原生路线校验、其他装备或图纸来源；自动解析缺口及原生冲突仍记录在证据中，更新相关原生资源时需重新核对。

确认说明已涵盖同一原生入口时，可填写该入口的 `entry_uid`，用完整确认句替代同一装备、同一入口的原生显示摘要；两份证据和原生规则分别保留。未关联入口的确认记录不合并，其他装备、入口和图纸结果不受影响。

获取规则可用 `preset: "manhunt"` 组合游戏内完整简体任务名 `mission` 和已核实的 `condition`，显示 `任务名 - 条件`。`preset: "retaliation"` 使用原生简体势力名 `faction` 及 `action: "kill_squad"` 或 `"defend_territory"`，分别显示 `击杀杀戮小队有几率获得 [报复行动：势力]`、`成功保卫领土有几率获得 [报复行动：势力]`。使用预设时不另存 `text`。

已确认首次通关大师难度保证奖励的猎捕任务使用 `游戏内完整任务名 - 首次通关大师难度必定获得`。副本首领和最终奖励箱使用 `副本名 - 行为`，已核实的概率以 ` [10%]` 等形式置后。

预设只整理显示，不自动识别猎捕任务或推断难度、概率。大师难度仅用于已明确确认的任务，首次通关保证不代表重复通关必得，结算奖励不能泛化为普通首领“必定掉落”，也不建立 `Legendary` 的通用中文映射。未确认首次通关保证的来源保留自身已核实条件，不套用该句式。任务名不使用内部赛季编号。猎捕任务以 40 级进度奖励的永久解锁清单核对高潮任务 UID。报复行动从势力、地区与防守／击杀奖励追到图纸 UID，同名掉落表的 UID 冲突保留在 source_contexts。

Reader 按 `{category, text}` 展示成品及普通图纸来源，奇特图纸按 `blueprintGroups` 的标题与来源列表排版。同一条目的不同常规来源各占一行。持有前置、特定难度及首次奖励随对应来源显示。部位适用范围保留在成品和配方 UID 关系中，各部位的图纸列在图纸清单。

`native_attributes.py` 按 `identities` 的原生 UID 更新本地化、单位及格式信息。`native_profile` 明确选择 code1/data23 和十条已闭合规则：普通武器控制、暴击几率、技能分阶及七条具名常量预设。常量规则核对品质、池、预设百分位和相关等级段；不推测 Power 端点或取整，不使用百分位简单相乘。其余 25 条继续使用确认值。别名、独立说明和原生未变时的修订保留，原有显示视图在导入时同步。

幽灵与承包商手套的固定对装甲伤害使用相同属性 UID、池和品质百分位；这可以核实共享预设的映射，但不能单独推出最终 UI 数值。普通 Orange 的 8.0% 保留确认值及来源，不把 Prototype 百分位或未闭合的取整推算作为数值导入。

制作货币需求按匹配标签累加。`crafting.requirements()` 必须使用明确的制作台品质、物品等级；涉及 Power 的公式还需实际 Power，不能用等级替代。图纸品质覆盖优先；物品要求不累加，多条候选无法唯一判断最具体标签时保持未确认。公式、物品质量映射和条件保留原义，不把不完整合计输出成最终制作成本。现有 Reader 不新增未经确认的制作成本展示。

公共分解目录自动更新可闭合的基础量、概率和专用材料数量。额外数量奖励的运行时规则仍不完整，Orange / GearSet 已有实测最终产量分别保留；`精密组件材料` 的特殊文本字段仍使用已确认名称。原生基础量与最终产量不能互换。随机品牌制作目录直接从统一图纸关系生成。

映射的每个 `bindings` 条目集中保存一个原生对象的 `source`、`uid`、可选 `follow` 引用和页面 `records` 定位，`fields` 按页面字段名列出文本、天赋或数值的读取方式。同一对象的中英文名与描述共用来源和定位；字段仍分别比较，不因放在同组而一起覆盖。

武器获取沿枪种定向表、专长树节点、首领和贮藏箱匹配型号 UID。特有武器的获取方式按各专长中实际授予该型号的节点登记。聚落计划、专长实地研究和失乐园首领可向实际命中的配方 UID 发放图纸。高峰大厦同档奖励的成品与重新配置图纸分别处理。组合包内的低等级成品与外观转换图纸分别核对。

## 回收线上修改

少量管理员维护时，在生成前通过浏览器读取本批页面最新修订和源文本。以最近确认发布的原文为 base、本地原文为 local、最新线上原文为 remote：

```powershell
node tools/equipment/sync.cjs base.wiki local.wiki remote.wiki dist/merged.wiki
```

工具按稳定记录和字段合并互不冲突的修改，保留页面外正文；同一字段双方改成不同内容或线上移除字段会报告冲突，不产生合并文件。核对输出后替换对应本地源，再进行原生更新。原文、修订号与这次回收结果即可满足日常维护，不需要字段锁或人工修改标签。

缺少可信 base 时，先比较实际线上与本地内容，不能把本地候选当成已发布状态。`publishing/baseline.json` 记录真实发布状态，与原生字段基准分别维护。

## Reader、Editor 与生成

`wiki/modules/TD2资料记录.lua` 统一效果传输和展示；品牌、装备组、奇特 Reader 保留各自的布局和机制。属性、图标、制作、获取与材料使用共用模板及规则。正式样式在 `ui/brand-sets/`，站点深色样式与字体在 `wiki/pages/site/Common.css`。

奇特护具通过 `visuals.inventory.asset_ref` 把库存图传给共用身份卡。优先取物品的 `myIcon`。没有该字段时，用物品文件名、`myMaleVisualGearName` 和部位共同核对生成的库存图。登记 Wiki 图片前按非零 alpha 的外接框裁切，四边各保留至多 2 像素原透明边距，保持原比例与所有可见像素。注册项记录物品 UID 和原图路径。

Editor 的 `mapped-domain.js`、`mapped-ui.js` 和 `page-fields.js` 共用三类页面的人工字段合同。`source-patches.js` 保留未修改字段与记录的原文。`site-session.js` 保留最新修订、冲突保护、预览、保存和重新打开校验。

未修改的既有正文原样保留；正文输入合同仅校验实际修改的正文。

`projection.cjs` 将固定事实转换为 Reader 参数。品牌和装备组通过 `TD2资料映射` 读取 `TD2装备映射`，具名按稳定身份补全，奇特通过 `TD2装备属性数据` 读取逐槽配置。`TD2效果映射` 提供模式独立的效果内容。Reader 映射由本地完整数据生成；浏览器打开 Editor 时只加载实体身份摘要，固定游戏内容不嵌入 Runtime。

普通资料更新只需更新相应数据模块与页面；程序、人工字段合同或样式变化才重建 Runtime。

```powershell
& $py -B -m tools.brand_sets generate
node tools/gear_sets/generate.cjs templates
node tools/exotic_gear/generate.cjs generate
node tools/equipment/catalog.cjs
```

各生成器先计算并校验整批目标，只写 registry 指定归属的源。模板和目录生成不会重写装备页面。

## 武器资料

武器沿用 `records.json`、`native-map.json`、`native-baseline.json` 与 `import.cjs`。`武器型号资料` 集合保存原版及其具名子记录；固定数值、原生描述、属性 ID、后坐力配置和配件引用由 `weapon_projection.py` 投影。天赋仍使用共享 `效果资料`，人工天赋脚注、其他资料和正文仍保留在页面。武器页面只调用 `武器信息`；`TD2武器.lua` 共享天赋、获取、图纸、脚注和导航能力。

正文和导航共用型号的 `asset_ref`。核对游戏精通列表中带型号名的整枪缩略图与原生物品、库存、模型图片，再登记与卡片外观一致的资产。多个型号在列表中同图时复用同一资产。模型上的涂装及其预览图由皮肤槽独立提供。游戏卡图对照（完整维护环境的 `../evidence/equipment/weapon-appearance/expertise.webp`）

导入按型号稳定 ID 合并。每个普通字段、每项 `stats` 数值和每个有序集合独立比较。明确的空集合或投影中 `clear` 指定的字段可清空。读取失败会保留对应集合、依赖其输入的计算值和旧指纹。旧整行指纹按型号在下次导入时迁移；无法核对旧指纹的型号会在 `result.json` 记为 `model_baseline`，待用原投影或旧资料复核。

固定天赋槽完整解析 PvE 和 PvP 后，才按所属型号替换原生效果。确认转为随机槽时移除旧固定效果。缺少模式或原效果归属未登记时保留整组。退役天赋的人工脚注原样留在页面，审核结果的 `orphanNotes` 列出待处理的参数名。Editor 会阻止保存带有失效脚注的页面；维护者核实具体脚注后再处理。

`weapons_native.py` 按 include 图、实际类型、UID 和字段覆盖解析武器继承。具名优先采用 `myBaseWeapon` 的物品 UID；旧具名沿实际 Weapon UID 链关联原版。制作变体保存自己的 UID 和实际图纸关联。`milestone`、`level数字boost`、原生假道具、内部测试武器（`*_testing_asset.mitem`）和已确认未实装的型号排除在玩家目录外。未实装物品按 UID 和确认依据登记在 `native-map.json.unreleased_items`；发现、导入和图表重建沿用同一名单。

「冷酷无情」的 40 级型号取自「外观转换」图纸的成品 `player_weapon_rifle_akm_exotic_t1_v2`。豪华组合包发放 1 级 v1 和这张图纸，转换消耗一把「无情」。按原生标签 `Y6S3_AprilFools_FakeItem` 排除愚人节假道具。

六把特有武器由 `PlayerSpecialization.myElementGridByLevels → PlayerSpecializationElementItem.myItemType` 的实际 UID 引用和 `Weapon_LiveSignature` 标签确定，不能仅凭枪种纳入实验预设。专精加成投影 `shdresearch.juice` 的武器伤害、特有武器伤害两组定义及排除表；不把其他技能定义遗留的宽泛标签当成武器加成。

40 级 PvE 单次基础伤害由 `tools/equipment/weapon_damage.py` 从本体计算。沿物品 UID 读取生成配置、主属性、品质、武器定义和默认 FireEvent。等级 Power 在每个分段末尾向上取整，再查该数据版本的 WeaponDamage 曲线。按原生单精度将生成属性与物理伤害参数、同发弹丸数相乘。缺少曲线、主属性或遇到新实例区间时，导入报告具体缺项并保留已审核伤害。复核入口见原生计算与逐型号证据（完整维护环境的 `audit/2026-11-20/weapon-native-damage.md`）。

特有武器的「面板基础伤害」按实际发放物品的指定等级读取同一 UI 公式。三种爆炸事件按 40 级角色的技能曲线另存 `base_explosion_damage`。六把特有武器中，只有迷你炮按普通全自动射击计算基础 DPS。P-017 的导弹发射由专属事件控制，词条保留标称射速和单枚爆炸伤害。参见六把特有武器的原件与算式（完整维护环境的 `audit/2026-11-25/signature-weapon-damage.md`）。

武器导入优先采用原生词条上限。原生数据未闭合时，仅对同一物品 UID、品质类别和同一词条槽的 ID、核心／具名标志、百分位、固定授予值，沿用正式 `records.json` 已采纳且带 `reference_field` 来源的上限。新型号和变化的词条缺乏依据时留空。固定百分位词条按实例授予值登记，原生常量区间可用 `native_attributes.constant_value` 复核。

配装工具 29.2.0 的 `data/equipment/weapon-reference.json` 和 `evidence/equipment/weapon-reference-29.2.0-bindings.json` 留在本地，与截图一样供人工核对。常规导入、页面生成和预览均不读取这两份文件。

40 级固定授予值按物品 UID 登记在 `level40_preset`。导入核对橙色配置的原生属性 ID、属性池、具名标志和预设百分位，将实物值写入 `granted`。共享上限仍用 `maximum`。专长奖励的固定伤害核心全额计入，普通核心沿用同类比较基线；具名强化核心只计超出同类普通核心的百分点。截图中的可变词条只作样本。目标限定的生命值、装甲与离开掩体增伤各自保留在词条里。

DPS 由 `weapon_projection.py` 计算。普通模式使用默认单次伤害 × 默认射速 / 60。按原生槽锁、品质和排除表纳入固定配件，以及固定天赋的无条件效果。`damage_max` 记录裸枪参数，`base_damage` 记录 40 级一次齐射值，`damage_with_mods` 记录适用固定修正后的值。`rpm`、`pellets` 和原生距离独立保留。霰弹和双枪管每次齐射只合计一次。Reader 的 `damage_ui` 用最近整数，DPS 使用显示取整前的默认伤害，最后按既有规则向下取整。暴击、爆头、换弹、命中或叠层效果均在基础 DPS 口径之外。

详情栏的每分钟射速沿用 `WeaponRPMCompareUI → RPMFinal`。连发分别核对连内间隔、事件结束和末发后的重触发门槛。存在原生射速浮动时记录周期边界，并在决定周期的抽样分布已知时用每轮伤害除以平均周期。双向扳机按下、松开各一发，分别计入到下一发的间隔。蓄力按满蓄力单次伤害和完整蓄力／恢复周期计算。大角、小角的开镜替代模式另有独立事件。连发与蓄力（完整维护环境的 `audit/2026-11-20/weapon-default-dps.md`） · 固定授予值、可变连发与双向扳机（完整维护环境的 `audit/2026-11-20/weapon-remaining-dps.md`）

爆头伤害按 `DamageMultiplierHeadFinal` 与 `WeaponHeadShotDamageUI` 合并原生倍率、本武器爆头词条和固定配件。弹匣按 `ClipSizeFinal` 合并固定容量与 PvE 常量天赋，保留单发、双发及向下取整规则。装弹时间按 `WeaponReloadTimeUI` 的逐发、空仓和常规分支选择，速度合并固定装弹速度与武器控制力。

控制力条使用 `itemdetail_stats` 实际调用的 `WeaponAccuracyCompareUI` 和 `WeaponStabilityCompareUI`，包括射手步枪的收束时间分支及固定配件加成；`myAccuracyUI` 是改装屏幕字段，不能直接当作物品面板准确度。上述公式位于当前原生 `rogue/game system data/juice/attribute/dictionary/`，图形节点位于 `hunter/ui/compounds/`。

武器控制力图按原生型号 UID 读取 `data/equipment/weapon-charts.json`，由 `tools.equipment.weapons generate` 按枪种生成 Lua 模块。精准度显示默认配置、选定姿态的发射散布半角。「移动瞄准」对所有型号使用 1.9 m/s 的稳定比较速度，忽略一切角色移速加成，按各自的原生阈值和散布修正计算。普通角色平地前进的原生步态均速为 1.89126 m/s。参见移动瞄准调查（完整维护环境的 `audit/2026-11-21/weapon-ads-movement.md`）。镜头后坐采用站立瞄准、八个固定种子及 60 Hz 回放，图中显示各次回放的散布点及代表轨迹。两图的坐标都是距起点 10 米平面上的厘米值。两图每格 25 厘米，方形视口边长从 200 厘米起每档增加 50 厘米。精准度按当前姿态的最外圈选档，原点居中。后坐力按显示的散布点及轨迹选档，原点在底边中央。任一外缘与可扩展的边界相距 12.5 厘米时升档。选定档位后，视口与图形在 240 毫秒内同步过渡，启用减少动态效果时直接显示目标状态。模型可以只提供其中一张图；复仇女神保留控制属性、排除两张模拟图。用 `tools.equipment.weapon_chart_study` 从随库提供的模型和轨迹重建图表目录，再用 `tools.equipment.weapons check` 检查模板、具名入口与八份图表模块。

特有武器中，迷你炮机枪展示精准度与后坐力图，TAC-50 C 步枪仅展示精准度图。`weapon_chart_study.py` 按型号 UID 限定两种图表的适用范围，Reader 使用特有武器图表模块中的同一规则。游戏面板的准确度、稳定度和装弹时间独立展示。

「左边」按自身 UID 登记双图。它和 ACS-12 共用武器控制参数，默认配件没有控制力加成。固定天赋 `talent_weapon_sledgehammer_perfect` 的手榴弹标记影响目标移速和受到的装甲伤害，因此两者的默认散布与后坐力轨迹相同。

「武器皮肤」按 `WeaponSkin` 槽的预装物品 UID 及限定适配标签关联 `WeaponSkinItem`、`WeaponTransmogItem`。只有通用 `Skin` 或 `Mod` 标签的皮肤只在真正预装该物品的型号展示。型号专用皮肤和预装涂装进入对应型号的图库，预装项排在前面。普通型号与具名型号都适配的同款皮肤在普通型号下展示一次。具名专用预装涂装按实际所属型号展示。

优先采用原生 `myCustomPreviewTexture`，其次采用 `myIcon`。仅有纹理的涂装按 `ItemSkin` 着色器将 `mySkinTexture` 与三组原生颜色合成，再居中等比裁切，铺满图库的 2∶1 展示区。运行 `python -m tools.equipment.weapon_skin_swatches dist/<新目录>` 可重建这些图片。UID、图片来源与 Registry 绑定保存在 `weapon-skins.json`。截图用于核对外观。缺少原生图源的条目保留游戏原名。已确认未实装的皮肤按 UID 登记在 `unreleased`。

奇特武器通过型号已有的 `base_uid` 关联顶级原版，原生依据记在 `native-map.json` 的 `base_evidence`。优先核对实际 WeaponItem 或具体 Weapon 型号 UID；仅有枪族、相似名称或外观时不登记。Reader 在皮肤后复用同一卡片，读取原版型号的名称、图片和 Registry 页面地址。没有皮肤时原版卡仍可独立显示。属性与配件图标复用 TD2图标，配置在 equipment-ui.json 的 weapon_icons。

Reader 复用 `品牌套装信息框`，品质栏通过 `TD2图标` 显示枪种或特有武器的弹药图标。图标关联在 `evidence/equipment/weapon-ui-icons.json`，消费入口为 `equipment-ui.json.weapon_icons`。天赋与属性分组复用 `td2-talent-section-title`，具名武器在原版页内排列。

射程图沿用原生库存 HUD 的 `Get Range Points`。最优距离 O 和递减终点 L 决定折点，高低两档固定在图高的 80% 与 10%。横轴固定 0–100 米，越界的斜段沿原方向截断，O=L 时保留竖线。具有原生面板距离的实体弹丸和脚本武器也可显示这张图。

`tools/equipment/weapon_range.py` 按默认 PvE 的 FireEvent 读取普通物理通道。`stats.distance_damage` 保存模式、修正后的 O/L、RangeMaxFinal（R）、分别取整的近远伤害端点和 `retention`。保留率取零变动下的 D(R) / 近档，超过 R 才归零。射程面板与该比值独立展示。具备两组覆写的大角分全自动和开镜单发，缺少适用物理通道的型号保留空列表。

武器定向更新及预览（`--name` 可重复，只投影对应原版页及其具名）：

```powershell
& $py -B -m tools.equipment.weapon_projection --output dist/weapon-native/projection.json --name "ACS-12" --name "圣艾尔莫引擎"
node tools/equipment/import.cjs dist/weapon-native/projection.json dist/weapon-import --write
node tools/equipment/catalog.cjs
& $py -B -m tools.equipment.weapons generate
& $py -B -m tools.equipment.weapons_preview dist/weapon-preview
```

每次使用全新 dist 目录；先审核投影和 importer 的差异，再使用 `--write`。完整 `tools.equipment.native` 更新也包含已登记武器。Navbox 使用装备导航的 markup、样式和交互，包含普通、具名、奇特和特有武器；具名卡片链接到原版页内的型号锚点，左侧显示已登记的武器外观，右侧优先显示该型号的固定天赋图标，随机天赋使用半透明枪种图标。奇特武器沿用同一布局，左侧显示枪图，右侧显示天赋图标。武器天赋正文、图标模板与导航按效果 UID 共享已登记图片。补充的稳定资产引用维护在 `data/equipment/weapon-navbox-talents.json`。核实新图时按原生天赋的实际继承关系读取 `myIconSprite`，在指定图集中按 `mySpriteId` 匹配唯一图块；登记前核对图块边界、透明通道和现有图片。无法核实者保留空图标字段。词条导航的桌面卡为 214 × 60 px，单列窄容器按可用宽度排版。当前项同时比较页面和锚点。规划与样式迭代只抽查各类别的代表页，不生成或检查全体页面。静态预览运行实际 Lua，默认生成 ACS-12（含具名）、ACR、圣诞颂歌的原版页、三把奇特及其已关联原版、两把特有武器，以及奇特装备对照；保留完整导航与窄屏入口。未生成的导航目标保留 Wiki 地址。页面操作按匿名读者呈现。运行产物内 `start-preview.ps1` 后打开其打印的本地地址，审核后关闭该服务。编辑表单的往返仍使用下述装备预览及共享 Editor。

## 验证与预览

普通资料修改只检查受影响页面的读取、修改、写回与生成结果。共享代码调整运行对应测试；完整检查使用 `tools.verify`，发布准备见 [deployment.md](deployment.md)。

```powershell
node --test tests/test_equipment_import.cjs
& $py -B -m unittest discover -s tests -p 'test_equipment_native.py' -v
node ui/editor/production/build.cjs dist/editor-review --local-preview
& $py -B -m tools.equipment.preview build dist/equipment-preview --editor-export dist/editor-review/local-preview
& $py -B -m tools.equipment.preview serve dist/equipment-preview --port 8767
```

浏览器打开 `http://127.0.0.1:8767/index.html`，选择样本后点击“编辑”。本地预览运行实际模板和 Lua，Editor 修改与保存使用内存中的样本，不写源文件或 Wiki；返回阅读页或切换样本会保留本次保存，刷新浏览器恢复原始样本，可用“导出 WikiText”下载当前内容。Lua 依赖使用已有 `.cache/python/` 时，启动前设置 `$env:TD2_LUA_TEST_PATH="$PWD\.cache\python"`。服务只绑定本机；审核后 Ctrl+C 结束。页面独立 HTML 也在同一目录。站点基础 Infobox、资源加载与最终 MediaWiki 行为在获准发布时核对。
