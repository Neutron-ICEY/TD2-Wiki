# 回归输入

协作仓库附带正式测试源码、人工构造的样本、整理后的期望值和输入清单。下列输入在完整维护环境中按相同路径提供，适用于需要比对原件或历史兼容性的测试。

`test_weapons.py` 中校验导航配图与全库源文件存在性的两个用例需要完整维护环境中的登记图片。只有源码时可运行 `tools.equipment.weapons check`、`node --test tests/test_weapon_import.cjs` 和无图预览。

- `resource-corpus.zip`、`equipment-native/hunter/`、`equipment-native/rogue/`、`core-configs.json`、`named-structures.json` 含有实际原生内容。
- `regression-inputs.json` 登记的 gzip 输入包含固定的历史对照和原生样本。排序、解析、Catalog 生成等普通专项可按实际依赖独立运行。[源码检查示例](../../README.md)

`resource-corpus.zip` 保存文本、原生解析、资源查询和旧回执回归实际读取的固定输入。`resource-corpus.json` 登记原路径、字节数和 SHA-256；测试验证压缩包及每份内容后解到自己的临时目录，结束时清理。历史观察 ID、原始偏移、计数及哈希断言保留，包内 `dist/` 是原记录路径，不读取工作区的历史构建目录。

`regression-inputs.json` 登记几个 Node 回归的 gzip 输入，`fixture-data.cjs` 校验解压字节。`salvaged-native` 只包含既有型号筛选断言需要的 58 份原生定义。

这些固定样本不随游戏更新自动覆盖，也不是当前游戏资料源。默认 `tools.verify` 无需完整私人解包库；已安装当前资源库时，再用 `tools.verify --resources` 检查真实注册输入与资源 manifest。完整原始文件哈希复核使用 `tools.game_resources verify`。

`equipment-native/` 保存代表装备的真实原生定义、所需属性字典与本地化片段，用于模式、数值、身份及缺失输入验证。`sources.json` 记录来源路径，不能据此推断游戏 build。

武器 Reader、导航、生成物与导入失败情形在默认回归中使用正式源、固定记录或小型测试夹具。安装私人游戏导出后，可单独执行 `python -B -m unittest discover -s tests -p "resource_*.py" -v` 交叉核对原生型号、投影、贴图与天赋切换；`tools.verify --resources` 也会运行这组测试。
