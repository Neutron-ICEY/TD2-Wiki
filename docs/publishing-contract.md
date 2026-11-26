# 发布数据契约（v1）

所有 JSON 使用 UTF-8。Wiki 文本用 UTF-8 无 BOM、LF 换行，hash 为原始文件字节 SHA-256。`schema_version` 固定为 1。运行时校验在 `tools/publish/bundle.py`；此文档是字段说明。错误时 CLI 返回非零码，不输出 JSON 片段或凭据。

## Registry

`publishing/registry.json` 中 `target` 是稳定的部署目标标识，不是凭据。`mode` 当前只能为 `MANUAL`。`namespace_prefixes` 是本地映射配置，初始值只是常用命名空间约定，发布前必须与目标 Wiki 确认。未配置 namespace 拒绝导出；主命名空间目前保守地拒绝含冒号的标题。

一个非实际游戏数据的登记示例：

```json
{
  "id": "example-item-data",
  "kind": "pages",
  "source": "wiki/pages/example-item-data.wiki",
  "title": "示例装备/数据",
  "namespace": 0,
  "related_entity": "item:example",
  "ownership": "generated",
  "generator": "tools/generate/example.py@v1",
  "change_reason": "更新实体数值；对应源数据变更记录",
  "asset_relationships": ["example-icon"]
}
```

| 字段 | 约束 |
| --- | --- |
| id | 稳定 ASCII 字母/数字/点/横线/下划线标识，不区分大小写查重 |
| kind | pages / templates / modules / categories / redirects / assets |
| source | 仓库相对路径，使用 `/`；Wiki 源在 `wiki/<kind>/`，资产在 `assets/` |
| title / namespace | 完整 MediaWiki 标题和数字 namespace；不能跨命名空间冒用标题 |
| related_entity | 字符串或显式 null（通用模板等基础设施可为 null） |
| ownership | generated 或 manual；不支持 mixed |
| generator | generated 必填，记录当前获准执行的生成维护所有者及版本，不表示历史生成来源；manual 不声明活动 generator |
| change_reason | 必填的内部变更理由，随对应维护源更新。Wiki 编辑摘要独立填写 |
| content_sha256 | 每个资产必填，取当前确认版本原始文件字节的 64 位小写十六进制 SHA-256 |
| asset_relationships | 直接引用自动识别。此数组只补充由代码动态选择的资产 ID，通常为 `[]` |
| asset_relationship_source | 可选。动态消费者可指定提供文件名映射的模板 ID。全局资产地址模板使用 `registry-assets` 引用整个资产登记表 |

内容构建与 Reader / Editor 完整组装都从本次使用的 Wiki 源解析文件链接、`{{TD2资产|稳定ID}}` 和模板返回的已登记文件名。构建还从 `Module:TD2装备映射` 实际写出的 `image` 字段识别武器与皮肤图片，按文件名核对 Registry，未登记的引用会阻止构建。同一文件在一个消费者内只列一次。生成源更新后，新图片会自动进入发布清单，已有 baseline 不是纳入依赖的条件。注释、nowiki 等展示用文本不产生依赖。无法静态识别的动态选图由上述两个关系字段表达。

`templates`、`modules`、`categories`、`assets` 默认要求 namespace 10、828、14、6；`redirects` 可以在已配置的文本 namespace 中使用，源必须为单一 `#REDIRECT [[目标]]` 指令。Wiki 扩展名支持 `.wiki`、`.wikitext`、`.lua`、`.json`，JSON 会检查语法；不声称解析所有 wikitext 或执行 Lua。资产支持常见图片、音视频及 PDF 后缀，但具体上传许可、MIME、安全与授权需人工核验。资产 title 使用 `File:名称.扩展名` 等已配置别名。

路径不允许越界、隐藏文件、跨根符号链接；标题采用保守归一化查重，发布前核对实际规范标题。未登记文件不会导出。

## 身份和待执行地址迁移

Registry `id`、`related_entity`、`title`、`source` 分别表示登记身份、业务实体、Wiki 地址与本地文件。它们不能互相推导。资产额外记录 `content_sha256` 与 `naming` 英文语义命名及证据。消费目录以 `asset_ref` 指向资产 ID，派生模板不属于第二套维护映射。

可选 `publishing/pending-moves.json` 使用 `status: LOCAL_ONLY_NOT_PUBLISHED` 和 `entries`，每项包含 `id`、`namespace`、`from_title`、`from_source`。目标来自相同 ID 的 Registry 项。build 生成 `address_moves`，每项状态为 `NOT_EXECUTED`，包含已有 baseline 和本次快照中实际存在的源/目标观察。条目带 `ADDRESS_MIGRATION_REQUIRES_REVIEW`，旧标题从删除候选中排除。地址迁移不是新建/上传授权。

迁移项只接受上述四个输入字段，不允许覆盖移动策略。发布包每项 `move_options` 明确记录 `method: native_move`、`preserve_history: true`、`reason: ""`：正文 `noredirect: false`，保留旧标题重定向；File `noredirect: true`，不创建旧文件名重定向。源存在、已知源基准相符且目标不存在时，`execution_action` 分别为 `MOVE_PAGE_KEEP_REDIRECT` / `MOVE_FILE_NO_REDIRECT_KEEP_HISTORY`。源没有历史基准时仍须观察两端。未知观察为 `HOLD_ADDRESS_PREFLIGHT`，目标占用为 `HOLD_TARGET_OCCUPIED`。两端均确认不存在且源无历史基准时，才列首次创建或上传待批。

迁移项的 `source_baseline` 保存原地址的最近确认修订、内容摘要及适用的文件版本。目标为空时，源观察与已知基准相异或原地址已消失，行动为 `HOLD_SOURCE_DRIFT`，冲突为 `MOVE_SOURCE_DRIFT`。prepare 用同一规则复核。

顶层 `file_write_policy` 固定摘要和新文件简介为空，原有文件简介保留，已有文件改名只能原生移动，运行时地址只从 Registry 解析。图片不额外填写原因、说明或摘要；站点若强制要求则停止。禁止复制上传替代移动、旧文件别名、重定向或旧地址回退。迁移项只列在地址迁移清单和冲突清单，不进入普通 CREATE/UPDATE/UPLOAD/UNCHANGED 指令列表。

无 File 重定向的切换不是原子操作。执行前冻结完整消费者候选、备份远端内容和文件历史，按共享消费者形成的依赖组安排短维护窗口。每组文件移动并核实后立即切换该组消费者，所有依赖就绪后才切换全局地址 Helper 与 Reader/Editor。任一占用、版本漂移、身份/历史不匹配或选项不可用即停止扩大范围；按实际成功回执恢复该组。File 回退先核实原地址空闲，再原生逆向 MOVE（仍 `noredirect: true`、原因留空），随后恢复对应消费者备份；不得假设旧地址存在。正文反向移动需单独核实旧标题重定向的历史和目标，不删除占用页来强行回退。

baseline 和图片回执继续保存最后确认的线上旧地址，不能用本地新名替换。只有另行授权、成功移动并核实后才按成功项更新 baseline、回执和临时迁移事务。旧名称仅存在于历史证据或未完成事务中，不作为第二套当前地址。

## Reader / Editor

正式源、资源名和 Gadget 定义由 `reader-editor-production.json` 登记。站点深色公共样式为 `MediaWiki:Common.css`，namespace 8、content_model 为 css。

Editor 新候选按当前源码核对输入集合、工具链、版本与产物；Entry 根据实际 Runtime 回读绑定。操作命令见 [部署](deployment.md)。

## Baseline 与远端快照

`publishing/baseline.json` 的条目示例（hash 必须替换为真实 64 位十六进制摘要）：

```json
{
  "schema_version": 1,
  "target": "huijiwiki-td2",
  "entries": [{
    "title": "示例装备/数据",
    "namespace": 0,
    "content_hash": "<真实线上文本的 SHA-256>",
    "revision_id": 123,
    "reviewed_by": "编辑者标识",
    "published_at": "2026-10-03T12:00:00Z"
  }]
}
```

只有已验证发布回执而缺少确切发布时间时，允许显式 `published_at: null`，并必须增加：

```json
"confirmation": {
  "observed_at": "<原始回执中的回读时间>",
  "receipt": "publishing/history/<真实回执>.json",
  "receipt_sha256": "<回执原始字节的 SHA-256>"
}
```

缺少 `published_at`、空字符串或不合法时间仍拒绝。回执必须为本 Root 内无链接跳转的受控 JSON、schema 1、相同 target、顶层 `PUBLISHED_VERIFIED`，并且在 `entries` / `completed` 中对该规范目标仅有一个严格匹配的成功记录；标题、namespace、revision、content_hash、observed_at 及资产 file_revision 必须对应。重复 JSON 键、修改的回执和旧字段与 confirmation 冲突均拒绝。现有 `reviewed_by` 要求不变。`observed_at` 只表示回读证据时间，不替代发布时间或新的实时远端观察。

`reviewed_by` 必须是非空文本。历史回执欠缺审核人时，核对成功回执、留存正文或文件版本后，可署本次复核人的标识，并明确复核日期和依据。原修订、摘要、发布时刻及回执保留原值。

保留而退役的历史资源可在真实baseline记录上增加`retired: true`；revision和content_hash保持原值，该标记仅排除自动删除候选，不表示线上已删除。

`retired` 也不表示禁用线上资源，不能阻止仍在 registry 中的对象被导出；应用前须核对精确标题/namespace及正式资源集合。只对已批准保留的历史对象补状态，保留原revision、hash、发布时间及回执，不按Sandbox等名称前缀批量处理。

资产 namespace=6 另需 `file_revision`，记录可识别实际上传版本的标识，例如站点提供的文件时间戳/版本键。`revision_id` 同时保留文件描述页 revision。

可选快照放入忽略的 `.publish-local/remote-snapshot.json`，顶层结构也是 schema_version、target、entries。存在的条目包含 title、namespace、`exists: true`、content_hash、revision_id、observed_at，资产另需 file_revision；不存在的条目只需 title、namespace、`exists: false`、observed_at。未列出的对象视为未核实，绝不推断不存在。

```powershell
& '.\.venv\Scripts\python.exe' -B -m tools.publish build --snapshot .publish-local/remote-snapshot.json --output dist/<new-review>
```

快照只包含公开内容状态，不包含账户会话。采集时用准确页面源文本或原始资产字节计算 hash，不能对浏览器渲染后的 HTML 或复制后被改换行的文本计算。baseline 只能记录审核者实际验证的线上状态，不可把整个 manifest 直接改名充当 baseline。

## 输出契约

`manifest.json` 顶层包含版本、模式、目标、UTC 构建时间、hash_algorithm、comparison、entries、address_moves、file_write_policy、delete_candidates。每个 entry 保留 registry 映射，并增加：

- `file`：包内相对路径，按 kind 分目录，以稳定 id 命名。
- `operation`：create / update / unchanged，表示相对 baseline 的内容差异；只有不在地址迁移中的 assets create/update 对应报告 UPLOAD。
- `content_hash`：产物原始字节 SHA-256。
- `asset_relationships`：本次源文件、地址提供模板和显式补充共同得到的资产 ID。每项前置文件在 `entries` 中排在消费者之前。
- `declared_asset_relationships`：仅在 Registry 有显式补充时保留，用于离线复算完整关系，并发现漏项或多项。
- `baseline_revision`：上次确认 revision，无记录时为 null。
- `remote_observation`：可选的人工观察记录，无则 null。
- `conflicts`：REMOTE_UNVERIFIED / REMOTE_EXISTS_WITHOUT_BASELINE / REMOTE_DELETED / REMOTE_DRIFT。

删除仅在独立 `delete_candidates` 数组中报告，没有 delete operation。候选是 baseline 中不属于 registry 或现有 reader-editor-production.json 正式资源集合、且未标记 retired=true 的对象；正式资源配置不扩展通用包的 entries。报告的 CREATE/UPDATE/UPLOAD 表示本地意图，CONFLICT 可同时列出同一对象，冲突不是授权写入。UNCHANGED 也必须检查 drift。

`validation.json` 记录离线 validation 结果、manifest/report hash、条目数，`production_approved` 永远为 false。`prepare` 从包内原文重新核对可解析的资产依赖及顺序，并验证所有产物 hash、地址迁移与登记项的对应、两类重定向选项、空图片说明策略、未执行状态及报告一致性。报告的“资产依赖顺序”列出本批待创建、更新或移动的前置文件及受影响的消费者。旧合同的历史包只作证据，需要重新 build 才能 prepare。

每个审核包有生成时间，因此包元数据不保证逐字节重现；源内容不变时条目 hash、映射和操作保持一致。构建不改 baseline、不改源、不写线上。失败输出不能作为可发布包使用；换一个新目录重新构建，不手工修补 validation。
