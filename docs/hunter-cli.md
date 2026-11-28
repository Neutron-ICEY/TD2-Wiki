# Hunter 导出

从工程根目录运行。批量入口驱动项目固定的 Hunter 2.2.9，复用原程序选择类型、加载索引、筛选和 Export All。三类输出为 PNG 图片、Materials 和 Raw Files（含 Hunter 产生的伴随文件）。需要可绘制窗口的 Windows 桌面、Pillow（支持按 HWND 抓取）、Windows OCR 和系统 .NET Framework 编译器。无需手动操作窗口。每次只运行一个 Hunter。

从仓库根目录运行，`$py` 按 [README](../README.md) 或 [AGENTS](../AGENTS.md#python-与验证) 指向项目 Python 3.12+ 解释器，`$index` 指向本机游戏安装目录中的 `sdf.sdftoc`：

```powershell
$index = Read-Host '当前游戏安装目录中 sdf.sdftoc 的完整路径'
# 全量，三个类型共享一次加载
& $py -B -m tools.hunter_cli bulk --index $index --session incoming/game-update/full-001
# 日常版本发现与登记输入
& $py -B -m tools.hunter_cli bulk --index $index --session incoming/game-update/wiki-001 --profile daily
# 专项范围、逻辑处理器上限、每种资源的完成检查点
& $py -B -m tools.hunter_cli bulk --index $index --session incoming/game-update/art-001 --types images materials --query faceman --separate-types --cpu-limit 4
```

`--profile daily` 默认给 Hunter 分配最多 8 个逻辑处理器，运行中每秒采样。全量模式默认使用进程可用的处理器，每 3 秒采样。可用 `--cpu-limit` 和 `--poll` 覆盖。检测到输出、匹配数与导出按钮恢复后，CLI 以短间隔确认状态稳定。stderr 和各尝试的 `progress.jsonl` 报告索引条数、可读的百分比和进程 I/O。`export.json` 记录实际筛选、加载、回读、导出、完成确认和合并统计，`invocations.jsonl` 记录整次命令墙钟。`source.json` 和 `export/` 可直接交给[版本更新入口](game-resources.md)。Hunter 没有逐资源错误清单，输出文件数量包括伴随文件。

Ctrl+C 或在会话目录创建空文件 `cancel` 可中断，再用原命令加 `--resume`。已完成的范围保留，未完成的范围从其起点重试。`--retries` 控制每次运行中可恢复错误的额外尝试数。`--separate-types` 为长批次提供更多恢复点，默认将三类一起导出。恢复时复核索引 SHA-256、Hunter SHA-256、容器目录元数据、已知 Steam build/depot 和选项。旧 daily 会话按冻结的类型和筛选范围复核，能够覆盖当前发现目录和登记项就可继续使用。已结束会话另核对输出目录身份，内容完整性由资源计划验证。

bulk 锁住用户 Hunter 配置，在独立会话副本运行程序。首次使用时以独占临时句柄保护缺省配置位置。窗口消息发往本次进程，设置、筛选结果和按钮状态由窗口回读。点击时鼠标会短暂移动，请在窗口保持正常可绘制时执行。成功后 CLI 请求关闭本次 Hunter 主窗口并等待退出。各 host 的 `child-process.json` 记录关闭方式和退出码。关闭超时会终止专用进程并报告失败。

Hunter 的 Export All 会把多个原生条目写入同一个 PNG。文件可以正常解码，也可能含有来自多个条目的字节。对已按行核实的冲突，CLI 按索引 SHA 查询 `data/asset-import/hunter-image-collisions.json`。实际导出的冲突路径和对应行数写入命令结果、`export.json` 与 `source.json` 的 `known_image_collisions`。需要辨认来源时，在同版 Hunter 中把候选行分别导出到独立空目录，核对解码像素和引用。

daily 在同一份已加载的索引上处理发现目录、已登记图片和其他原生输入。地图分块共用 `mbucket`，图片按登记名称选范围。多条筛选已覆盖相同输入时省去多余的一条。新增登记超出窄词时可重新启用配置中的宽词，再超出配置则导出所选类型的全部资源。实际生效的筛选在每次成功尝试的 `applied_query`，同路径重复输出仍核对大小和内容摘要。后续资源计划只取发现目录和登记输入。专项 `--query` 只代表实际匹配到的范围。

以下 `start/search/batch-export` 使用前台与剪贴板，要求已有 hunter.dat。它们的会话和 bulk 会话分别管理。

## 按完整资源名补导

从项目根目录运行，复用上文 `$py`（需安装 Pillow）与 `$index`：

```powershell
$session = 'dist/hunter-session-001' # 必须是尚不存在的新目录；也可指定绝对路径

& $py -B tools/hunter_cli doctor
& $py -B tools/hunter_cli start --session $session --index $index --experimental-gui
& $py -B tools/hunter_cli search --session $session --query 'uni_logo' --limit 10
& $py -B tools/hunter_cli export --session $session --name 'hunter/baked/art/characters/npc/civilians/unique/shared/textures/uni_logo_01_d'
& $py -B tools/hunter_cli status --session $session
& $py -B tools/hunter_cli stop --session $session
```

`start` 只加载一次索引，后续命令复用同一进程。`--experimental-gui` 明确表示接受下述 GUI 限制。`--startup-timeout` 默认 240 秒。会话空闲 30 分钟自动关闭。

批量导出使用 UTF-8 JSON 字符串数组，例如 `targets.json`：

```json
[
  "hunter/baked/art/characters/npc/civilians/unique/shared/textures/uni_logo_01_d",
  "hunter/baked/art/characters/npc/civilians/unique/shared/textures/uni_logo_02_c",
  "hunter/baked/art/characters/npc/civilians/unique/shared/textures/uni_logo_03_c"
]
```

```powershell
& $py -B tools/hunter_cli batch-export --session $session --manifest targets.json
# 取消当前会话（不会删除已导出的文件）；之后用 status 查看最终状态。
& $py -B tools/hunter_cli cancel --session $session
```

定向 batch-export 每批接受 1–20 个完整资源名。每项默认等待输出最多 30 秒，可用 `--timeout` 设置为不超过 300 秒。不存在的目标记为失败并继续；焦点/选择/输出状态不确定时停止后续项，保留已成功文件。

## 命令和结果

| 命令 | 实际能力 |
| --- | --- |
| `doctor` | 检查 Windows、Python、Pillow、固定 EXE 哈希和配置存在性；不保证 GUI 当前可操作 |
| `start` | 配置保护、原样复制 EXE、新输出路径设置及回读、加载一个 `.sdftoc` |
| `list` / `search` | 用 Hunter 搜索框过滤，通过选择项的 Ctrl+C 获取完整资源名；每次最多 100 项 |
| `export` | 查询完整名称并逐字回读确认后，触发 Hunter 的 E 导出快捷键 |
| `batch-export` | 同一索引、同一批输出目录内依次处理明确目标；不是原子任务 |
| `status` | 读取会话和各任务的持久化结果，不是 Hunter 内部进度 API |
| `stop` / `cancel` | 正常关闭 / 请求取消，终止专用 Hunter，释放配置锁，记录完整性校验 |

默认 `--kind image` 的 `search` 和 `list` 均限于 `hunter/` 命名空间的图片，内部添加 `width:>0,hunter/`。用户查询最多三项，用逗号分隔，传给 Hunter；名称片段和 `width:2048` 可组合使用。**属性匹配由 Hunter 决定，本工具没有重新解释查询语言，也不声称支持任意属性。**

返回 `native_id: null`，不能取得的原生 ID、游戏版本和原始编码资源哈希保持未知。`filtered_as: image` 的依据是 Hunter 宽度过滤条件，不是从扩展名或图像外观推断。查询没有读取 GUI 表格的其它元数据，宽高、透明度等在成功导出后由实际文件解码取得。

`list` 的 `end_observed` 表示按 Down 后复制值重复，重复名称可提前结束浏览。按名称执行 `export` 和 `batch-export` 时，CLI 额外用 Windows OCR 回读匹配行数，在 20 行以内逐行复制并核对名称。同一完整名称出现多次时，该项返回 `AMBIGUOUS_RESOURCE_NAME`，其余明确目标可继续处理。行数回读失败或最终选中行不符会停止该批。

标准输出为 JSON，启动阶段状态提示在标准错误；命令帮助使用 argparse 文本。退出码：

| 码 | 含义 |
| --- | --- |
| 0 | 命令成功；`status` 表示成功读取状态，`cancel` 表示请求已提交 |
| 2 | 参数、目标清单或前置状态不合法 |
| 3 | 启动、文件访问、超时等运行失败 |
| 4 | 请求执行失败或部分失败，检查 JSON 和任务收据 |
| 130 | 客户端被 Ctrl+C 中断，已请求取消会话 |

## 输出与追溯

### 原生文件模式

新会话使用 `start --load-raw`：在配置锁保护的固定版本默认设置上，首次加载前启用 General > Load Raw Files，仍保留图片加载。不能对已运行的旧会话补传此参数；旧会话先正常停止，再创建新目录。缺少此启动参数的原生请求返回 `RAW_LOADING_NOT_ENABLED_START_WITH_LOAD_RAW`。

```powershell
$session = 'dist/hunter-raw-session-001' # 必须是新目录
& $py -B tools/hunter_cli start --session $session --index $index --experimental-gui --load-raw
& $py -B tools/hunter_cli search --session $session --kind raw --namespace hunter --query 'ri_crafting_material_t2_ceramics_small' --limit 3
& $py -B tools/hunter_cli search --session $session --kind raw --namespace rogue --query 'talent_gear_brand_g_01' --limit 3
& $py -B tools/hunter_cli export --session $session --kind raw --name 'rogue/game system data/juice/talent/talent_gear_brand_g_01.mtalent'
& $py -B tools/hunter_cli stop --session $session
```

原生模式的 `list/search` 必须提供非空查询，使用 `--namespace hunter|rogue`，不加宽度条件。结果仅代表名称过滤，标记 `any_loaded_type`，不伪造 GUI 类型或原生 UID；搜索为空不证明资源不存在。先用已知原生资源确认加载有效，再调查缺失定义。

`export` 与 `batch-export --manifest <明确清单.json>` 均支持 `--kind raw`，由完整目标路径决定命名空间。每批仍为 1–20 项，允许混合 hunter/ 与 rogue/；同名、大小写冲突和原文件与 `.decompiled` 附属文件的目标冲突均拒绝。默认图片命令不变。

原生输出为 `jobs/<uuid>/hunter/raw/raw_files/<完整资源路径>`，保留扩展名，同时登记实际出现的同名 `.decompiled`。收据写入 `result.json` 和独立的 `hunter/raw-export-manifest.json`，不混入图片 manifest。每项等待原文件及附属文件大小、修改时间连续稳定至少 3 秒后记录哈希；这是 `RAW_FILE_STABLE` / `FILE_STABLE_ONLY`，不是 Hunter 内部任务完成通知、二进制完整性或定义语义证明。附属文件未出现时不假定它必然存在；超时或取消留下的文件不算成功。

保留索引来源、资源完整路径、输出文件及角色，`resource_id` 保持 UNKNOWN。原生文本 UID 应由后续定义解析取得，不能把路径或显示名当作 UID。已有 `tools.asset_import.text_evidence` 可读取支持的定义文本；导出本身不会自动接入文本库或确认 Wiki 实体映射。

CLI 不自动置顶目标窗口，若目标窗口被其他窗口遮挡将直接拒绝操作。

输出根目录由 `--session` 指定。每次导出创建新 UUID 子目录，不接受已有目录作为一次新会话，不清理或复用旧成果：

```text
<session>/
  session.json, state.json, worker.log
  input-metadata-before.json
  app/hunter.exe                 # 原样副本
  requests/, responses/          # 可复现的命令和响应
  jobs/<uuid>/result.json        # 逐项结果、错误、成功/失败/未尝试数量
  jobs/<uuid>/hunter/export-manifest.json
  jobs/<uuid>/hunter/raw/images/hunter/.../<原名称>.png
```

每次任务设置新空目录，并从文件夹地址栏和 Hunter 设置框两次读回路径后才允许导出。成功要求预期路径出现、文件可完整解码且哈希稳定；它表示 `EXPORTED_FILE_VALIDATED`，不伪造 Hunter 内部成功/失败计数。清单兼容项目既有 provenance 字段，保留完整资源路径、索引路径/哈希、导出文件哈希和 RGBA 像素哈希；实体映射仍为 `EXTRACTED_UNMAPPED`。

关闭后记录原 EXE、配置、索引 SHA-256 是否一致，以及索引同目录文件大小/修改时间是否一致。后者不是所有大型游戏资源的逐字节校验。崩溃可能留下 `RUNNING` 收据；不要把它当成功。Windows Job Object 用于守护进程退出时关闭其专用 Hunter，正常 `stop` 的最终校验仍是首选。

## 定向接口的边界

按名称补导要求 Win32 前台与剪贴板可用，并回读所选资源名。批次数量、支持类型和回执结构见上表。批量版本更新使用本页开头的 bulk 入口。Hunter 二进制或窗口布局升级后，先在独立会话重新核对类型选择、名称过滤、导出按钮以及恢复，再更新固定版本。
