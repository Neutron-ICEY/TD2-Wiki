# 完整工程与 GitHub 的同步

完整维护工程用于游戏原件、完整预览、原生导入和发布。协作仓库维护可共享的源文件，GitHub 上的分支和 Pull Request 只包含协作仓库自身的历史。两边都能修改共享源。一般在最适合该任务的一边编辑一次，再同步改动。

## 关联与查看

以下命令在协作仓库根目录运行，`$py` 指向 Python 3.12+。首次关联一对已经核对过的副本时执行以下命令。路径存于本机 Git 配置。检查点指向双方共享文件一致时的协作仓库提交，保存在本地 `refs/td2-sync/base`。

```powershell
git config --local td2sync.full ../WEB-TD2-Wiki
& $py -B -m tools.github_sync status
& $py -B -m tools.github_sync checkpoint
```

在新机器上若两个副本已分叉，应先找到已知同步的协作提交，将协作副本切到该版并核对完整工程，再设立检查点。若找不到共同版本，先人工合并差异。只有共享文件一致且协作仓库干净时才能建立或推进检查点。

## 日常操作

1. 在协作分支拉取协作者的提交（例如主分支使用 `git pull --ff-only`），运行 `status`。工具用同一个 Git 基准比较两个工作区，按 Git 属性处理文本换行和二进制文件。两边独立改动同一文件时列为 `conflict`，由维护者逐段合并。
2. 运行 `import` 把只在协作仓库变化的文件带回完整工程，运行 `export` 把只在完整工程变化的文件带入协作工作区。命令后可以给出一个或多个精确相对路径。默认检查协作仓库已跟踪或检查点已有的文件。**新增文件须显式给出路径并审查实际内容**，例如 `& $py -B -m tools.github_sync export tools/example.py`。
3. 遇到 `review-deletion`，核实是否退役，再分别处理两个工作区中的文件。重命名同样核实旧路径与新路径。工具逐文件替换，若中断可以重新运行 `status`，已一致的文件会跳过。
4. 在协作仓库审阅 `git diff`，明确暂存本次文件，再审阅 `git diff --cached`。运行受影响的生成器和测试，连同应更新的生成源一起提交。两边再次一致后执行 `checkpoint`，正常推送协作分支并提交 Pull Request。检查点应位于当前分支历史上，切换到无关分支时使用独立协作副本。

```powershell
& $py -B -m tools.github_sync status
& $py -B -m tools.github_sync import
& $py -B -m tools.github_sync export
# 审阅、测试并提交本次共享文件后
& $py -B -m tools.github_sync checkpoint
```

## 文件范围

协作仓库的 `.gitignore` 决定可纳入范围。`.gitattributes` 标为 `td2-manual` 的文件在两个环境承担不同职责，包括 Git 策略、环境入口、含本机说明的文档和有私人来源字段的图片映射。改到这类文件时按段吸收共享变更；可用 `git check-attr td2-manual -- <路径>` 确认。完整工程保留原件、证据、凭据、回执和备份。文件筛选之外，提交者仍需核对新代码、数据和图片的实际来源。

资源批次的历史根目录只在完整工程配置。共享来源字段使用仓库相对路径或固定版本的上游链接；本机解包路径、Steam 安装路径和剪贴板路径留在完整工程。

Wiki 页面和前端资源的生成、登记、灰机发布及回退仍由原工具负责。[装备维护](equipment-maintenance.md) · [部署](deployment.md)
