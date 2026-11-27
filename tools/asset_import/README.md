# 资源查询与证据

原始游戏资源的唯一维护入口是 `resources/game/current/`，导入、差异、完整性和恢复见 [资源更新流程](../../docs/game-resources.md)。本目录查询已有证据、解析原生定义并生成审核候选；不会自动修改人工资料、上传图片或发布 Wiki。

`data/asset-import/batches.json` 和 `text-sources.json` 登记查询来源。活跃图片观察只引用当前原始库或正式 `assets/`；历史批次的 `observations` 白名单保留原数组指针与观察身份，未列入的旧导出不参与查询。`locations.json` 精确重定位来源路径，SHA 不变；项目资产目标用 asset_ref 解析 Registry 当前路径，原生库目标仍用 path。两者只能选一，不按同名或前缀替代。项目派生记录保留历史 derived_file 与独立 asset_ref；发布观察保留原 wiki_filename，通过 registry_id 读取当前文件，并分别输出原资源 asset_id 与 wiki_asset_id。GAV 旧文本及 42 个必要解析片段在 `evidence/asset-import/inputs/`，保持原来源身份；当前原生索引、来源账本及必要人工证据在 `records/`。查询不读取备份目录或旧 Lab。

## 跨批次只读资源检索

在项目根目录执行，解释器按 [AGENTS](../../AGENTS.md) 选择：

```powershell
$py = '.\.venv\Scripts\python.exe'
& $py -B -m tools.asset_import.library batches
& $py -B -m tools.asset_import.library search ui_inventory_spritesheet --field path --verify
& $py -B -m tools.asset_import.library duplicates --kind bytes --limit 20
& $py -B -m tools.asset_import.library targets backpack-gear
```

检索默认只读元数据，文件完整性为 `not_checked`；`--verify` 才核对命中文件。支持路径、SHA、资源 ID、名称、类别、批次和 Sprite 检索；`duplicates` 可按 bytes、pixels、source、shared 查看已有证据分组。同图标不证明同装备，资源身份不等于 Wiki 实体映射。`ui-targets.json` 的可用性与来源状态按记录查询。

## 既有文本资源查询

```powershell
& $py -B -m tools.asset_import.text_library --resource talent_gear_brand_g_01
& $py -B -m tools.asset_import.text_library --key 4CDCE5B25C4057F2000322017B35A809
& $py -B -m tools.asset_import.text_library --source game-simplifiedchinese-menus --text '暴击' --limit 20
& $py -B -m tools.asset_import.text_library --resource B00501356A6B4D4E001AF7AFF1F451F3 --related-depth 2 --limit 60
```

简体原生来源为 `game-simplifiedchinese-menus`，英文为 `game-english-menus`。业务 Catalog 与原生本地化保持来源和语言区分。查询结果保留未知和冲突，不自行推断获取方式、公式或最终游戏效果。

## 原生定义与更新候选

`text_evidence.py` 解析已登记定义，`native_index.py` 在原始库更新后重建显式审核候选。它需要现有 `text-sources.json` 登记索引及已初始化的资源 `manifest.jsonl` / `source.json`，按现有登记范围重建，不自动发现或映射新增定义。候选保留来源 SHA、覆盖范围、引用关系和未纳入资源统计，不自动替换 `data/asset-import/text-sources.json`。完整命令和接入方法见 [资源更新流程](../../docs/game-resources.md#更新后审查-wiki-输入)。父文件变化时，旧派生片段返回 `DERIVED_INPUT_REQUIRES_REVIEW`，不能沿用旧偏移去解释新字节。

Hunter 定向导出使用 [现有 GUI 桥接](../../docs/hunter-cli.md)；本目录 `hunter.py` 只处理离线来源和映射门禁，不启动 Hunter。图片冻结名称及正式素材维护按 [图片命名规范](../../docs/IMAGE-NAMING-STANDARD.md)。

`investigate` / `pipeline` 保留应用包静态提取能力，必须显式传入 `--apk <新包路径>`、`--windows <新包路径>` 和 `--pwsh <PowerShell路径>`，输出使用全新目录；没有旧包默认路径，不运行安装包。所有输入先验证存在且位于输出目录之外，再生成产物；前后 SHA 检查保持不变。`pipeline.stage_plan` / `stage_images` 通过稳定实体 ID 与 asset_ref 解析 Registry 当前地址，分别检查本地解析兼容性、来源和发布状态。应用包中文或英文名称只产生审核候选，不能自动批准实体关联；品牌来源键通过 entity_ref 连接游戏实体，历史来源记录不承担当前地址。

`continuation`、`reconciliation` 和 `brand_publication` 对传入的角色、名称、图片引用及文件观察做判定。

当前回归位于 `tests/test_asset_*.py`、`test_text_*.py`、`test_native_index.py`；固定样本及摘要在 `tests/fixtures/`。完整离线检查用 `tools.verify`，正式本地资源库接入检查加 `--resources`。
