# Hunter CLI 实验原型

本工具复用项目内 Hunter 2.2.9 的资源加载、PNG 和原生文件导出。它是 **需要交互式 Windows 桌面的 GUI 桥接原型**，不是 Hunter 原生 CLI，也不是无界面解包器。解析和转换仍全部由原版 Hunter 完成。

代码在 `tools/hunter_cli/`；不修改 `tools/hunter.exe`、依赖或游戏文件。不用于 Wiki 上传，不会按图片外观建立游戏实体对应关系。

## 运行条件

- Windows 11、可用的 Python 3.11+ 与 Pillow；复用现有 `tools.asset_import.hunter.exported_record` 登记文件和像素哈希。
- 固定 Hunter 2.2.9 二进制 SHA-256：`7f7279795df8573ef8211f03ed39b373bdb9c88339df5158291b067d8eccc014`。其它版本直接拒绝。
- 使用普通交互式桌面运行。受限沙箱环境可能导致剪贴板粘贴失效；自动化需要在可访问桌面与剪贴板的环境中运行，不要求管理员权限。
- 原配置 `%APPDATA%/DTZxPorter/GameTools/config/hunter.dat` 必须存在。会话持有独占只读句柄，使 Hunter 使用内存默认配置，也阻止改写原配置。期间不要打开另一个 Hunter。
- CLI 会占用前台、鼠标和剪贴板；执行期间不要同时操作桌面。它不会保留原剪贴板内容。锁屏、焦点争夺、窗口尺寸变化会导致失败。

## 最短使用流程

从项目根目录运行，`$py` 指向已配置的项目解释器，`$index` 指向自己的游戏安装目录。

```powershell
$py = '.\.venv\Scripts\python.exe'
$session = 'dist/hunter-session-001' # 必须是尚不存在的新目录；也可指定绝对路径
$index = Read-Host '当前游戏安装目录中 sdf.sdftoc 的完整路径'

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

每批明确指定 1–20 个完整资源名；不提供全量导出。每项默认等待输出最多 30 秒，可用 `--timeout` 设置为不超过 300 秒。不存在的目标记为失败并继续；焦点/选择/输出状态不确定时停止后续项，保留已成功文件。

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

`end_observed` 仅表示按 Down 后复制值不再变化；重复名称可能提前终止枚举。因此始终标记 `complete_catalog: false`，不能把 `list` 当作完整索引转储。同名资源无法区分原生身份；完整名称查询过宽或最终回读不一致时拒绝导出。

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

## 已知限制与维护边界

标准文件对话框使用窗口消息；查询、选择和导出主要使用键盘及剪贴板。但 Hunter 主界面没有可用的标准控件树，目前仍有少量**固定布局点击**：设置入口、目录浏览、加载入口、首行选择。窗口逻辑客户区必须为 980×625，按实际 DPI 换算；布局或版本不符即拒绝。不同 DPI、显示器布局和锁屏/远程桌面变化未获得广泛验证。

因此这是能实际处理明确图片和原生文件清单的原型，不能称为稳定的长期资源 API。运行会主动取得前台，适合专用桌面或一段无人操作的时间；后台无人值守、并行会话、所有格式、所有资源类型、原生 ID 和全量资源目录均未实现。

批量流程减少了人工查找、截图识别、逐个点击和重复加载索引的步骤，但内部仍逐项查询并选择。没有声称比熟练用户的 GUI 多选更快；实际效率优势是脚本一次提交清单、自动登记输出、复用加载结果。

离线测试：

```powershell
& $py -B -m unittest discover -s tests -p test_hunter_cli.py -v
```

该测试使用人工合成 PNG，覆盖精确选择、防路径歧义、取消、部分成功和错误停止；真实游戏验收记录另存于 `dist/`，不进入测试夹具。
