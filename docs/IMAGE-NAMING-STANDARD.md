# Wiki 图片身份与命名

图片文件名是可变地址，`publishing/registry.json` 的资产 `id` 是稳定 Wiki 资产身份。消费目录只保存 `asset_ref`，装备 Logo 使用 `records.json.entities[id].visuals.logo`。原生资源 UID、来源路径、游戏英文原名及实际内容摘要分别保存，不能互相替代。

## 英文地址

灰机 Wiki 未开放 SVG 文件上传。本地 SVG 原图保留在对应维护或研究目录，不登记为待上传的 File 目标。见[部署说明](deployment.md)。

`TD2-Category[-Subtype][-Owner]-Name-Usage.ext`

类别受控为 Brand、GearSet、Talent、Attribute、Weapon、Gear、Skill、Material、UI、Status。当前已使用 Brand、GearSet、Talent、Gear、Material、UI；Talent 细分 Gear、GearSet、ExoticGear、Weapon、ExoticWeapon、Prototype。Prototype 仅表示已有来源明确为原型的资源，不表示玩家可获取。用途为 Logo、Icon、Background、Pattern；扩展名小写，与实际格式一致。

| 资源 | 示例 |
| --- | --- |
| 品牌 | `TD2-Brand-GolanGearLtd-Logo.png` |
| 装备组 | `TD2-GearSet-OngoingDirective-Logo.png` |
| 装备天赋 | `TD2-Talent-Gear-PerfectEnergize-Icon.png` |
| 装备组天赋 | `TD2-Talent-GearSet-Cavalier-Charging-Icon.png` |

Name 优先采用已核实游戏英文名。来源为当前原生本地化 GUID、原生内部资源名或已核实 Name/Image 绑定。UI 技术用途和 `SharedEffects` 是 Wiki 资源角色词，不冒充游戏名称。无法核实英文或所属身份时保留待审，不自动翻译或覆盖。

候选由 `tools.brand_sets.equipment.asset_image_name` 生成：先提取原生 `<color name="…">…</color>` 文本的可见名称，颜色名支持 `legendary_orange` 和 `legendary orange`，未知标签拒绝；不改写原始本地化文本。Name 与 Owner 中的冒号作为词块分隔（`Ortiz: Exuro` → `OrtizExuro`），最终文件名仍禁止冒号。外层 ASCII 连字符；英文直撇号、弯撇号和修饰字母撇号移除后仍为同一词，不将所有格或缩写后半段另起大写（`Striker’s` → `Strikers`、`Can’t` → `Cant`）；其余词块去空格和标点、首字母大写拼接，保留已有词内大小写；`&` 转 `And`，数字保留；重音经 NFKD 去组合符后必须为 ASCII。类别和用途大小写固定，禁止路径、控制、隐藏方向字符及重复扩展名。不按结果反推名称或实体。

新文件先核实语义再生成候选。完整 File 名全局查重，不能按逻辑分类分开检查。少量确有冲突者添加经核实的所属者、部位或用途；仍不能区分时才申请短稳定标识。不能使用随机数字掩盖身份疑问。Windows 设备名、尾随点/空格和危险路径拒绝；标题保守碰撞键使用 NFC、下划线/空白归一及 Unicode casefold，Python/Node 规则一致。线上仍需核对站点实际规范标题和目标占用。

## 关联和更新

同名不同天赋保持各自稳定身份与资产引用；不同天赋可以引用同一 `asset_ref`。相同摘要只证明字节相同，不自动合并业务资产。图片普通内容更新保持 Asset ID；改名同样不重新编号。Registry 的 `source` basename 与 File 名相同，文件夹不承担身份职责。

`tools.identity` 和 `tools/identity.cjs` 按稳定 ID 生成消费者所需地址。派生 `wiki_file`、`source`、`page_title` 不写回 Catalog。`TD2资产`、`TD2页面地址`、Reader Helper 与 Lua 数据都由 Registry 生成，不手工维护第二份地址。历史来源记录、回执中的旧名称保留为证据，不作为当前地址。

登记资产必须同时填写 `naming`（scheme、category、subtype、english_label、evidence、status）、正确来源关系与 `content_sha256`。对文件内容的更新须核对来源后同步摘要。`python -B -m tools.identity` 检查全局地址、文件与稳定关联，并仅校验 Wiki 资产字节；不扫描原始游戏库。完整离线入口 `tools.verify` 包含此检查。

本地图片可用不等于线上已发布。`confirmed_on_wiki` 仅从相同当前地址的真实 baseline 派生，`local_available` 单独表示本地存在。缺失图片保留已有占位行为。

## 线上地址变更

Registry 是计划当前地址；`publishing/pending-moves.json` 是临时迁移事务，记录稳定登记 ID 和旧地址，目标从 Registry 派生。发布包显式报告地址迁移，旧对象不进入自动删除候选。该文件不是长期别名数据库，真实移动并回读成功、更新准确回执及 baseline 后才移除成功项。

已有图片改名使用原生 File MOVE，保留图片字节、描述页和文件历史，显式不创建旧文件名重定向（`noredirect: true`）。所有正式消费者直接使用 Registry 的新英文 File 地址，不保留旧文件别名或自动回退；不复制上传已有图片代替移动。正文页面 Move 仍保留重定向，两者不能共用默认选项。

图片原生移动与首次上传均保持原因、摘要和新文件简介为空，移动保留原有简介；仅确认源和目标均不存在的资产才进入单独批准的首次上传清单。本地重命名或构建不授权任何线上操作。执行前的远端检查、按依赖组短维护窗口切换以及失败逆向回退流程，统一按 [部署说明的地址迁移](deployment.md#地址迁移) 与 [发布契约](publishing-contract.md#身份和待执行地址迁移) 执行。
