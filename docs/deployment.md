# 本地构建与发布

Wiki 页面、模板、Lua、图片以 `publishing/registry.json` 登记；前端资源与 Gadget 登记以 `publishing/reader-editor-production.json` 为准。所有工具采用 MANUAL 模式，构建和 prepare 只生成本地审核资料。发布通过获准的浏览器操作完成。

## 内容与前端

灰机 Wiki（huijiwiki）的上传表单未开放 SVG。发布清单应排除 SVG 文件，后续发布不要尝试上传 SVG。威胁度的距离图与视野图由 Reader 在页面内绘制，静态 SVG 仅作本地研究资料保留。

先按 [装备维护](equipment-maintenance.md) 回收本批线上修改、导入并生成资料。上游完成字段、关系及代表页面验证，发布工具负责路径、目标、所有权和产物一致性。

从仓库根目录运行，`$py` 按 [README](../README.md) 或 [AGENTS](../AGENTS.md#python-与验证) 指向项目 Python 3.12+ 解释器：

```powershell
& $py -B -m tools.publish build --output dist/content-review
& $py -B -m tools.publish prepare --bundle dist/content-review

node ui/editor/production/build.cjs dist/frontend-review
& $py -B -m tools.brand_sets.production --output dist/frontend-review
```

每次使用新输出目录。Reader / Editor 组装检查当前完整输入清单、工具链及产物；该检查不重复编译。`--resources-only` 可仅组装前端资源与 Gadget 登记。

按 `publish-report.md` 的“资产依赖顺序”核对本批文件与消费者。每个消费者的完整前置资产 ID 在 `manifest.json` 的 `asset_relationships` 中。Reader / Editor 完整组装的 `resource-plan.json` 也列出对应 File 标题。

Runtime 和 Entry 分别位于 `Gadget:TD2EditorRuntime.js`、`Gadget:TD2EditorEntry.js`。Entry 初始为 UNBOUND；获得发布授权、保存并读取实际 Runtime 后，通过 `ui/editor/production/build.cjs --bind-entry <resources-directory> <runtime-receipt.json> <new-bound-directory>` 绑定真实修订。运行时只加载被绑定的版本。构建方法见 [Editor 构建](../ui/editor/production/README.md)。

## 保存与基准

发布前通过浏览器读取目标最新修订、存在性与完整内容。将线上改动与最近确认版本、本地内容比较；互不冲突的局部修改可回收，同一字段冲突先解决。即使本地显示 unchanged，也不能推断线上未变。

`publishing/baseline.json` 记录真实确认的线上文本 hash、revision，以及文件的上传版本。它用于发布比较；`data/equipment/native-baseline.json` 用于原生语义比较，两者不能互相替代。首次纳管线上对象时记录实际状态，不把本地预期内容登记成已发布。

保存成功后核对结果，只更新实际成功对象的 baseline 和回执。文件上传使用浏览器成功状态和必要轻量确认，不例行重新下载原图。Wiki Edit summary、文件简介和上传摘要默认留空；仅按用户要求、站点强制项或必要版权署名填写，不添加哈希、素材提取、测试、审核或发布过程等技术记录。文件简介清理不通过重新上传、删除文件或隐藏历史实现。

构建报告里的 create / update / unchanged 是本地意图。没有新远端观察时会报告未核实；删除仅列候选，不执行。完整字段见 [发布契约](publishing-contract.md)。

## 地址迁移

正文原生 Move 保留历史和旧标题重定向；图片原生 File MOVE 保留历史，取消“保留重定向”，原因留空。两类操作以发布包 `address_moves.move_options` 为准，不沿用表单默认值。已有图片不能通过复制上传改名，旧 File 地址不作为运行时别名或回退。图片首次上传也不填摘要、简介或额外说明，站点强制要求时停止。

先对完整内容和前端候选检查旧图片地址引用，并在移动前核对两端最新修订、权限、保护、共享文件解析、引用及移动选项，能力或状态未确认即停止。保留原始地址、文件历史、实际远端文本及逐项回执。将共享消费者关联的文件安排在同一维护窗口，移动并核实文件后立即切换相应消费者，全部图片依赖就绪后切换全局 Helper / Reader / Editor。无 File 重定向时短暂引用失效无法完全消除；版本漂移、占用、身份或历史核验失败即停止扩大批次。回退 File 时先重新核实原地址空闲（不假设旧地址仍可访问），再按成功回执逆向无重定向移动（仍 `noredirect: true`、原因留空）并恢复消费者备份；正文回退前单独核实旧标题重定向的历史与实际目标再逆向移动，不删除占用页强行回退。不能凭计划更新 baseline，不能自动删除新旧地址解决失败。

## 验证范围

复用已有结果的条件见 [AGENTS 的验证规则](../AGENTS.md#python-与验证)。按本次改动选择检查。

- 维护说明或命令帮助只改措辞时，核对涉及的链接、参数和实际入口。单页或素材改动检查对应页面与引用。共享 Reader / Editor 改动检查受影响的代表页面及交互。
- 修改发布工具或契约，涉及清单字段、包内报告的生成、资产依赖排序、地址冲突判定或回执校验时，运行对应专项测试，并用当前候选在新目录执行一次离线 `build` 和 `prepare`。
- 生成器、Reader / Editor 或发布工具共用的接口发生跨模块变化，或排查后仍难以限定受影响的离线路径时，运行完整 `tools.verify`。它已包含离线 `build` 和 `prepare`。

灰机资源缓存可能延迟约 24 小时。发布及存储内容确认后，debug 页面加载预期版本、显示与功能正常即可通过；普通入口的缓存滞后不触发额外等待、刷新或重复上传，真实解析、加载或代码错误仍须处理。
