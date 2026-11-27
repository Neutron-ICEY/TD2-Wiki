# 原始游戏资源与版本更新

正式原始资源只有 `resources/game/current/`，保留 Hunter 导出的原目录和文件名，包括 `raw_files/`、`images/`、`materials/` 及其他实际导出类型。`assets/` 是正式 Wiki 图片，`data/` 是人工维护或已审核资料；资源更新命令不会写入这两个目录，也不会生成或发布 Wiki 页面。

当前原件只放在 `resources/game/current/`。更新前核对 Git 工作区及人工资料，独有输入进入正式证据目录或外部备份。工具只写资源库和本次审核产物。

查询使用的正式图片直接绑定 `assets/`；`evidence/asset-import/records/` 保存必要索引和来源回执，`inputs/` 保存查询所需的派生片段。固定输入不代表当前库版本。

`resources/game/manifest.jsonl` 逐文件记录相对路径、字节数、SHA-256 和 `source_id`，按路径 `casefold()` 严格递增；`source.json` 保存各来源的游戏 build、容器摘要、来源证据和文件数量。未知 build 必须写 `null`。一次部分导入可能保留多个来源，不能把全库误标成同一新版本。完整性校验只证明已提供文件集的内容，不证明 Hunter 已导出整个游戏。

## 更新原始库

1. 将新导出放入独立临时目录，例如 `incoming/game-update/update-001/`，其中保留 `raw_files/hunter/...`、`images/hunter/...` 等结构。Hunter 操作按 [Hunter CLI](hunter-cli.md) 的能力与权限执行；不需要可靠的增量解包能力，也不直接导出覆盖 `current/`。
2. 在导出目录之外创建 `incoming/game-update/update-001.source.json`。`source_id` 必须唯一；已经登记的 ID 不允许重写来源。

Hunter CLI 定向 Raw 导出的成功任务可将 `jobs/<uuid>/hunter/raw/` 作为 `--source`，显式使用 `--unfiltered`，并在来源记录中引用相邻的导出回执。这属于部分导入，不能据此声明整个 `raw_files` 已完整导出；更新全量范围时仍保留人工导出环节。

```json
{
  "source_id": "填写本次唯一来源ID",
  "origin": "USER_SUPPLIED_MANUAL_EXPORT",
  "game_build": null,
  "source_container_sha256": null,
  "coverage": "填写实际导出范围及完整性依据"
}
```

已知 build 以字符串填写，容器 SHA-256 填实测值；`exporter`、`exported_at`、`evidence`、`recorded_export_root`、`observed_installation` 等附加来源字段会原样保留。来源声明不会被工具自动认证。安装目录当前版本与已有导出的版本分开记录，不能仅凭目录时间或同一个索引摘要建立版本关系。

```powershell
$py = '.\.venv\Scripts\python.exe'
& $py -B -m tools.game_resources plan `
  --profile wiki `
  --source incoming/game-update/update-001 `
  --metadata incoming/game-update/update-001.source.json `
  --output dist/game-update-001
```

这是日常 Wiki 游戏资源更新的标准命令。命令行 `plan` 默认启用 `wiki`，示例仍显式标明，避免复制命令时遗漏用途。标准更新采用部分导入：新增和修改进入计划，未出现的旧文件保留。特殊调查、定向补导等未筛选操作见下文。

### Wiki 标准范围

Hunter Export All 仍保留完整原始导出。Wiki 标准配置适用于具有 `raw_files/`、`images/`、`materials/` 根目录的导出；规则集中在 `data/asset-import/resource-scope.json`，仅跳过：

- `raw_files/hunter/shadercache/`
- `raw_files/hunter/shaderbytecode/`
- `materials/`：Hunter 的 Materials 纹理输出，**不包括** `raw_files/` 中的制作材料、图纸或分解定义。
- `raw_files/hunter/baked/art/`：动画、物理、骨架、几何及视频等原始烘焙美术数据。
- `images/hunter/maps/`、`images/hunter/baked_maps/`：地图地形与场景贴图。
- 配置中明确列出的 16 个 `raw_files/hunter/maps/<地图UID>/settings/<层UID>/`：8 个 `globalillumination` 光照层、8 个 `navmesh` 导航层。`layer_types` 为每个路径绑定已核实的类型，不使用通配符。

按相对目录精确匹配，大小写不敏感；在进入目录前剪枝，不枚举子文件。地图设置层仅定向读取 `layerdata.mlayer`，核对根 header 的 type、uid 并计算描述文件摘要；不读取层内其余资源。层目录存在但描述文件缺失、格式不明、类型或 UID 不符时拒绝筛选，目录自身缺席则记录为缺席。同名普通文件通常保留；地图层路径变成普通文件时拒绝。遇到的链接与路径冲突仍拒绝。

未知目录、新地图 UID、新设置层默认保留。`raw_files/{hunter,rogue}/game system data/` 保留完整发现范围，规则不能排除该范围及其子目录。其余 maps、全部 raw_files/baked_maps（包括 layers）、`images/hunter/baked/art/` 和其它未确认范围仍纳入。工具只记录实际遇到的 `skipped_directories`，不为了统计被跳过文件数而遍历子树。

筛选模式只能部分导入，**不能与任何 `--complete-scope` 混用**，apply 也会复核这一限制。旧库中未纳入的文件及其 `source_id` 保留，不生成删除操作、不自动退出纳管。只有显式 `--unfiltered` 才关闭命令行 plan 的筛选；它与 `--profile wiki` 互斥。规则或依赖校验失败时不会自动退回未筛选模式。旧的未筛选计划仍兼容，apply 始终沿用计划的范围。

直接调用 Python `make_plan()` 的 Wiki 维护脚本须显式传入 `profile='wiki'`；该函数的通用未筛选默认保持兼容。Hunter CLI 定向导出的根结构不同，使用下文的未筛选入口。

plan 冻结规则版本、规则文件 SHA-256、展开后的排除目录、依赖登记快照及地图层描述证据。依赖检查复用 `native-map.json`、`text-sources.json` 及其原生定义/引用索引、图片 Library 的活跃观察与父图证据，并使用现有 SourceLocations 路径映射；不读取原始资源来建立另一套索引。图片容器的 entry/resource_name 等来源标识不推导为 raw_files 路径，实际图片路径、父图、sprite 定义及原生 include/schema 仍受保护。必要输入落入排除目录时拒绝计划；登记缺失、索引摘要不符也会阻止筛选。检查覆盖现有登记与已解析证据，不声称发现尚未登记的新版本全部游戏引擎依赖。

原生索引的 `parsed.includes` 使用所属文件的 `resource_name` 解析相对路径；缺少该字段时，仅使用能通过 SourceLocations 确认的原始文件路径。`./`、`../` 和同目录文件名以原生文件所在目录为基准，不以索引或派生片段的存放目录为基准。缺少可确认的相对路径基准、主机绝对路径或越出 raw_files 根目录的引用会阻止筛选。

apply 从计划取得相同规则，安装前重新检查规则、依赖与地图层描述，文件安装后、清单提交前再检查登记快照和描述证据。规则文件、登记内容或描述文件发生变化（包括层目录出现或消失）时拒绝提交；依赖解析得到的范围与计划不一致也会阻止更新。尚未开始安装时可以重新 plan；已经安装部分文件时保留未完成状态，先恢复对应输入，再按下文重试。筛选标记保存在新来源的 `import_scope` 和成功回执中，地图层证据保存在计划及回执的 `layer_evidence`，原始导出范围与实际导入范围分开追踪。`import_scope` 由工具填写，不能提供与本次筛选矛盾的值；同一来源 ID 的筛选规则也不能重写。

审核 `dist/game-update-001/plan.json` 的新增、修改、删除、保留、复制字节统计，以及 `wiki_review` 的影响范围。需要重复内容报告时，plan 加 `--report-duplicates`；默认 `duplicates: null` 表示未统计。重复内容只报告，不合并不同原生路径。这个影响报告用于定位需复查的装备、属性、天赋、技能、获取规则、文本或图片；它不裁决游戏事实，也不自动更新业务资料。

```powershell
& $py -B -m tools.game_resources apply --plan dist/game-update-001
```

有删除候选时默认拒绝；确认该计划的完整覆盖与删除清单后，使用同一命令加 `--allow-deletions`。未变化文件不会重新复制，原文件和修改时间保留。相同来源 ID 的描述变化、计划产物被改、复制内容与计划不符、清单或来源元数据漂移、路径越界、链接、并行工具写入都会阻止更新。文件与目录互换的路径变更需要单独处理，不能靠覆盖已有目录解决。

plan 读取选中输入的完整内容，冻结本次文件集和摘要；apply 只读取新增、修改文件，边复制边核对计划中的大小及 SHA-256。plan 后出现的新文件、以及未变化输入的后续改动留到下次 plan 处理。准备 apply 时不要继续导出或改动该目录；若尚未开始安装而需要纳入新变化，重新生成计划。不以大小或修改时间替代 plan 的内容哈希。

资源安装成功、已登记输入检查通过且没有待恢复事务后，清理本次导出、计划和验证输出。保留 `resources/game/source.json`、`resources/game/updates/` 及其直接引用的来源回执。历史研究仍需某个已变化的原件时，按原路径和摘要单独保存。完整工程的 `evidence/research/<专题>/historical-inputs.zip` 按原始相对路径存放已变化的研究输入。同一原件由多个专题引用时，以研究清单里的 SHA-256 查找留存的那一份。

### 明确需要未筛选导入时

特殊调查或非标准目录的定向导出使用同一工具的 `--unfiltered`，不应用上述 22 项排除规则：

```powershell
& $py -B -m tools.game_resources plan `
  --unfiltered `
  --source incoming/game-update/targeted-001 `
  --metadata incoming/game-update/targeted-001.source.json `
  --output dist/game-targeted-001
```

未筛选指读取所给 source 的全部文件，不证明导出覆盖整个游戏。默认仍是部分导入；只有确认完整导出了某个目录时，才同时增加 `--complete-scope raw_files` 等参数，可重复指定。删除候选只来自这些目录，apply 仍要求 `--allow-deletions`。空目录也必须真实存在，缺目录不会被解释为“全部删除”。

## 更新后审查 Wiki 输入

原始库更新后，已有资料仍保持原样。

旧查询记录固定了来源 SHA；对应原件改变后可能明确报告不匹配。这表示该输入需要审查，不要直接改旧 SHA 消除提示。确需长期引用的少量片段作为必要证据另存；不因此备份整批旧原始资源。正式 Wiki 图片和人工资料不会随原始库替换。

按已登记的原生范围重建候选：

```powershell
& $py -B -m tools.asset_import.native_index --output evidence/asset-import/native/update-001
& $py -B -m tools.asset_import.text_library `
  --index evidence/asset-import/native/update-001/text-sources-candidate.json --resource <原生UID>
```

成功结果是 `REVIEW_CANDIDATE`，包括 `report.json`、`native-definitions.json`、`native-references.json`、`provenance.json` 和 `text-sources-candidate.json`。核对范围变化、未选资源、来源、解析问题及查询结果后，才显式将该目录的 `text-sources-candidate.json` 复制到 `data/asset-import/text-sources.json` 接入，不必改写候选中的路径和身份。临时试验也可输出到全新 `dist/` 子目录；长期使用的索引不能依赖可清理的临时产物。新资源不会因本次导入自动纳入实体映射。

已有派生片段只在父文件 SHA-256 未变化时沿用原切片；父文件变化会返回 `DERIVED_INPUT_REQUIRES_REVIEW`，保留报告而不猜新偏移。Wiki 数据生成、图片命名、离线构建及线上发布继续使用各自入口和授权。

## 验证与恢复

首次纳管既有导出时，将导出置于不存在的 `resources/game/current/`，无需额外备份可重新导出的原件。同卷目录移动只改变位置，不筛选子目录或改写文件；移动前核对源、目标的绝对路径和链接状态，避免目标已存在时发生额外嵌套。初始化失败时保留 `current/` 原件，先恢复未完成元数据并解决原因，不据此删除原始文件。

```powershell
& $py -B -X utf8 -m tools.game_resources init --metadata <本次来源JSON的绝对路径>
& $py -B -m tools.game_resources status
```

初始化读取实际文件建立清单；同一输入无需紧接着再做一次完整哈希验证。

```powershell
& $py -B -m tools.game_resources status
& $py -B -m tools.game_resources verify
& $py -B -m tools.game_resources recover
```

`status` 只校验清单摘要、结构、来源和是否有未完成更新，明确返回 `content_checked: false`；未完成时返回错误及状态、计划路径，不把旧清单当作当前库已完成更新。`verify` 才重新读取全部原始文件并核对 SHA-256、增删和链接。首次 `init --metadata <来源文件>` 已经读取全部文件建立基线，同一未变化版本无需立即再做一次全量校验。

apply 核对清单、计划产物摘要及来源身份后，只执行冻结的差异清单。每个文件先复制到一个可复用的临时文件，流式校验成功后以 `os.replace` 替换目标；不保留旧原件，不重复读取复制后的内容，不对可重新导出的旧目标做内容校验。全部文件成功后才安装新 manifest/source 并保存成功回执。返回的 `content_scope: changed_files` 明确表示本次只校验复制内容。

普通错误和进程中断均保留 `.transaction/state.json`，不自动回滚：`applying` 表示库可能混合新旧原件；`committing` 表示原件已全部安装、元数据待完成；`committed` 表示只剩回执或临时文件清理。修复磁盘、权限等原因后执行 `recover`，或重新执行同一 `apply --plan ...`。`applying` 从头重做本批差异，无需逐文件进度数据库；删除也可重复执行。复制源缺失或变化时，恢复原导出目录中符合该计划的文件（必要时重新导出同版本）再重试。进入 `committing` 后恢复不再需要原导出。

未完成期间不使用 `current/` 生成 Wiki 候选，不开始另一计划，不删除状态或重写审核包。原计划与对应导出是完成这次更新的依据；工具不会把未知混合状态自动改标为成功。初始化中断仍由 `recover` 修复元数据，原始文件不删除。

路径检查按一次操作过程复用已检查的目录，每个文件仍检查类型和链接；避免逐文件反复解析驱动器到根目录的整条路径。更新期间不要用其他程序移动、改写或替换这些目录。工具独占锁阻止另一个维护命令并行写入，不承担对抗外部程序实时替换目录的职责。

`status` 和 `verify` 不接受 profile；`verify` 仍覆盖全部已纳管文件，包括旧库中保留的被排除目录。常规更新后使用 status 和已登记输入检查；重复 plan、全库 verify 仅用于确有需要的验证，不作为每次更新的固定步骤。

### 阶段计时

`init`、`plan`、`apply`、`status`、`verify` 和更新重试返回附加 `timings`，并在退出计时范围时向 stderr 输出一条 `event: resource_timing` JSON，含命令、成功状态、总秒数和各阶段秒数/调用次数。失败或中断时也会输出已执行阶段；参数校验尚未进入计时范围时只输出错误。stdout 保留命令结果 JSON，可用 PowerShell `2> <日志路径>` 单独保存计时和扫描进度。

扫描的 `scan` 只计迭代器推进（目录枚举及 stat），`resource_hash` 单列资源内容检查及其尝试文件数/逻辑字节数；按需启用的 `duplicate_index`、`manifest_write`、`manifest_flush` 区分重复统计、清单序列化与落盘。`inventory` / 全库 verify 的 `source_verify` 是包含这些子阶段的总耗时。

清单校验/合并分别为 `manifest_current`、`manifest_next`、plan 的 `manifest_merge`；计划完整性为 `plan_artifact_hash` / `plan_validation`。`layer_validation` 记录首次地图层描述检查，后续复核计入 `dependency_recheck`。apply 的 `prepare_update` 包含计划与元数据准备；`apply_files` 包含整个操作循环，包括操作清单解析、`path_check` 的路径检查及建目录、`copy_hash` 的复制与摘要、`install_files` 的替换/删除；其后另计 `metadata_check`、`install_metadata`、`finish_update`、回执和清理。

每个阶段的 `seconds` 包含其子阶段，不能直接相加；`exclusive_seconds` 扣除子阶段后可相加，`unattributed_seconds` 显示尚未覆盖的命令开销。计时不参与清单身份、差异比较、来源 ID 或计划摘要，不会使重复导入产生内容变化。它是本机墙钟计时，包含等待和系统缓存影响，不代表物理磁盘读量，也不能据文件/字节减少比例直接推算加速比例。

命令仅使用 Python 标准库，清单结构检查、统计及摘要同流完成，比较按行处理。仅在请求重复报告时使用临时 SQLite 索引，扫描后删除。更新临时空间通常只需最大单个差异文件和一份待安装清单；源码及人工资料的备份按项目规则维护。
