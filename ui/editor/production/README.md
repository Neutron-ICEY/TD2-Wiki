# Editor 构建

从 Root 执行：

```powershell
node ui/editor/production/build.cjs dist/editor-review
node ui/editor/production/build.cjs --verify-inputs dist/editor-review/editor --root .
```

构建读取 `ui/editor/src/`、`editor.css`、人工字段合同、工具链锁与构建配方，生成 Runtime、UNBOUND Entry 和 manifest。共享 Catalog 由 `tools/equipment/catalog.cjs` 独立生成。Runtime 载入或重读表单时读取 Wiki 目录，提交修改前再核对当前实体的模板和可编辑字段。字段发生变化时保留手稿，提示重读。修改名称、效果和数值更新所属固定数据及派生模块，不重建 Runtime。

`--verify-inputs` 检查当前输入集合、版本和产物，不重复编译。依赖在 `ui/editor/tooling/` 按锁文件恢复；具体输入以 `build.cjs` 为准。

加 `--local-preview` 会生成 `local-preview/modules.js` 和 `config.json`，供 `tools.equipment.preview build --editor-export <build-directory>/local-preview` 使用。该预览不写 Wiki。

Reader / Editor 资源统一由 `tools.brand_sets.production --output <build-directory>` 组装。Runtime 获准发布并取得实际回读后，使用 `--bind-entry <resources-directory> <runtime-receipt.json> <new-bound-directory>` 绑定 Entry。此操作检查实际正文、标题和修订，不能用本地候选代替远端回读。

相关 Editor 回归入口为 `node --test ui/editor/production/formal.test.cjs`。发布操作与真实状态分别以当前任务授权、Root baseline / 回执为准。
