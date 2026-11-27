# 完整工程与 GitHub 的同步

完整维护工程用于游戏原件、完整预览、原生导入和发布。协作仓库维护可共享的源文件，GitHub 上的分支和 Pull Request 只包含协作仓库自身的历史。两边都能修改共享源。一般在最适合该任务的一边编辑一次，再同步改动。

## 关联与查看

在协作仓库根目录运行以下命令，`$py` 指向 Python 3.12+。示例中，`GitHub/TD2-Wiki` 与 `Workspace/WEB-TD2-Wiki` 位于同一基目录下。`td2sync.full` 写入协作仓库的本地 Git 配置，相对路径从协作仓库根目录解析。

```powershell
git config --local td2sync.full ../../Workspace/WEB-TD2-Wiki
& $py -B -m tools.github_sync status
& $py -B -m tools.github_sync checkpoint
```

首次运行 `status` 时，如果还没有检查点，工具会以协作仓库的 `HEAD` 为基准。只有共享文件一致且协作仓库干净时，`checkpoint` 才会把当前提交记入本地 `refs/td2-sync/base`。在新机器上若两个副本已分叉，应先切到已知同步的协作提交并核对完整工程。若找不到共同版本，先人工合并差异。

## 日常操作

1. 在协作分支拉取协作者的提交（例如主分支使用 `git pull --ff-only`），运行 `status`。工具用同一个 Git 基准比较两个工作区，按 Git 属性处理文本换行和二进制文件。两边都改过且结果不同的文件列为 `conflict`，由维护者逐段合并。
2. 建立检查点后，运行 `& $py -B -m tools.github_sync import` 把只在协作仓库变化的文件带回完整工程，或运行 `& $py -B -m tools.github_sync export` 把只在完整工程变化的文件带入协作仓库。默认检查协作仓库已跟踪或检查点已有的共享文件。对这个范围之外的新增文件，先审查实际内容，再显式指定路径，例如 `& $py -B -m tools.github_sync export tools/example.py`。
3. 遇到 `review-deletion`，核实是否退役，再分别处理两个工作区中的文件。重命名同样核实旧路径与新路径。工具逐文件替换，若中断可以重新运行 `status`，已一致的文件会跳过。
4. 在协作仓库审阅 `git diff`，明确暂存本次文件，再审阅 `git diff --cached`。运行受影响的生成器和测试，连同应更新的生成源一起提交。两边再次一致后执行 `checkpoint`，正常推送协作分支并提交 Pull Request。检查点应位于当前分支历史上，切换到无关分支时使用独立协作副本。

## 文件范围

同步工具跳过协作仓库忽略的文件，以及 `.gitattributes` 标为 `td2-manual` 的文件。显式指定这些路径时，命令会报错。`README.md`、`docs/readme-assets/` 下的配图、Git 策略和含私人来源字段的图片映射均由两个环境分别维护。可用 `git check-attr td2-manual -- <路径>` 查询标记。完整工程保留原件、证据、凭据、回执和备份。提交者仍需核对新代码、数据和图片的实际来源。

资源批次的历史根目录只在完整工程配置。共享来源字段使用仓库相对路径或固定版本的上游链接；本机解包路径、Steam 安装路径和剪贴板路径留在完整工程。

Wiki 页面和前端资源的生成、登记、灰机发布及回退仍由原工具负责。[装备维护](equipment-maintenance.md) · [部署](deployment.md)
