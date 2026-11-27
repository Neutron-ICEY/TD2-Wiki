# TD2 Wiki

《全境封锁2》中文社区 Wiki 的开发工程。这里维护读者看到的装备、武器与机制页面，也维护管理员使用的编辑器、资料目录和发布工具。[灰机 Wiki](https://td2.huijiwiki.com/)

## 工程结构

| 目录 | 维护内容 |
| --- | --- |
| `wiki/` | 当前 WikiText 页面、重定向、模板、Scribunto Lua 模块及站点 CSS。登记为生成目标的源文件随仓库保存，更新时使用对应生成器。 |
| `ui/` | Reader 样式和交互，Editor 源码、构建配方及 Node 锁文件。 |
| `data/` | 装备和武器记录、制作关系、原生字段投影基准、图表、语言和图片索引。 |
| `publishing/` | 对象的稳定 ID、Wiki 标题、本地路径、依赖，以及最后确认的站点基准和前端发布配置。 |
| `tools/` | 原生导入、资源查询、Catalog 和页面生成、本地 Lua 预览、人工发布包准备。 |
| `tests/`、`evidence/` | 正式测试、可共享的夹具、已采用的数据依据和武器图表计算输入。 |
| `assets/` | 完整维护环境中登记图片的放置位置。Git 跟踪资源地址，图片由灰机文件系统及本地资源库管理。 |
| `docs/`、`.agents/skills/` | 维护说明与项目操作入口。[工程约定](AGENTS.md) · [项目 Skill](.agents/skills/td2-wiki/SKILL.md) |

## 从源码开始

使用 Python 3.12 或更高版本，以及 Node.js 和 npm。在仓库根目录执行以下命令。示例为 PowerShell，`$py` 指向本项目独立环境中的 Python。已有兼容环境也可直接使用。

```powershell
py -3.12 -m venv .venv
$py = '.\.venv\Scripts\python.exe'
& $py -m pip install -r tests/requirements.txt
npm ci --prefix ui/editor/tooling --ignore-scripts
```

检查 Catalog、武器页面及图表生成结果，并构建 Editor 与一个可打开的静态预览。每次预览使用新的输出目录。

```powershell
node tools/equipment/catalog.cjs check
& $py -B -m tools.equipment.weapons check
node ui/editor/production/build.cjs dist/editor-review --local-preview
& $py -B -m tools.equipment.preview build dist/equipment-review --editor-export dist/editor-review/local-preview --without-assets
& $py -B -m tools.homepage_preview dist/home-review --without-assets
& $py -B -m tools.equipment.weapons_preview dist/weapon-review --without-assets
```

首页、装备和武器预览均以对应目录的 `index.html` 为入口。源码预览使用 Reader 现有的缺图占位，首页的实时统计和活动记录留空或显示破折号。查看武器图表和资料文字无需解包游戏。验证装备编辑往返时，运行 `& $py -B -m tools.equipment.preview serve dist/equipment-review --port 8767`，打开本机 `127.0.0.1:8767/index.html`，完成后按 Ctrl+C。独立的普通测试示例为 `node --test tests/test_acquisition_mechanisms.cjs`。[装备维护](docs/equipment-maintenance.md) · [首页维护](docs/homepage.md) · [组件关系](docs/td2-reader-component-architecture.md)

## 图片与本地依赖

按业务记录的 `asset_ref` 在 `publishing/registry.json` 查 `id`，即可得到 `title`、`source` 和 `content_sha256`。例如登记标题 `File:TD2-UI-TheDivision2-Logo.png` 对应灰机文件页。Python 和 Node 均有现成的 `tools/identity` 查询入口，Wiki 模板从相同登记生成。发布状态另查 `publishing/baseline.json`。[示例文件页](https://td2.huijiwiki.com/wiki/File:TD2-UI-TheDivision2-Logo.png) · [命名和映射规则](docs/IMAGE-NAMING-STANDARD.md)

| 任务 | 额外输入 |
| --- | --- |
| 维护当前页面、Catalog、图表和前端 | Git 源码和上述软件依赖。图表重建命令 `& $py -B -m tools.equipment.weapon_chart_study` 读取已整理的模型和轨迹。 |
| 完整配图预览 | 由维护者在本机按 Registry 的 `source` 放置已核准的图片，使用预览命令时省去 `--without-assets`。首页还使用本地 `tools/homepage-preview-snapshot.json` 和 `tools/homepage-preview-avatar.png`。 |
| 原生更新、历史来源查询、完整回归 | 完整维护环境提供 `resources/game/current/`、相应 manifest、Hunter，以及所用索引指定的本地片段、来源账本和私人回归夹具。测试所需文件见夹具说明。 |
| 完整发布包和回退 | 使用完整维护环境中的登记图片、发布回执、实际远端修订与回退备份。构建会校验所需文件及哈希，线上写入另行授权。 |

[资源更新](docs/game-resources.md) · [资源查询](tools/asset_import/README.md) · [测试夹具](tests/fixtures/README.md) · [部署](docs/deployment.md) · [发布契约](docs/publishing-contract.md)

## 协作与同步

日常在本仓库从最新 `main` 新建分支。修改归属源，运行受影响的生成器和专项检查，审阅 `git diff --cached` 后推送工作分支并提交 Pull Request。生成的 Wiki 模块或模板与对应的输入一起提交。

同时使用完整维护工程时，在本仓库一次性配置 `git config --local td2sync.full ../WEB-TD2-Wiki`，按同步说明建立共同检查点。日常用 `& $py -B -m tools.github_sync status` 查看变更，`export` 带入完整工程的修改，`import` 回收协作分支的修改。新增文件按相对路径显式选取，两边都改过的文件逐段合并。[命令和文件范围](docs/github-sync.md)

`.gitignore` 列出可提交的源码范围。新增原创图片时先确认素材来源，再放行具体文件。原生图像、裁切图、游戏导出、抓取快照、凭据和构建目录保留在本机。维护源优先用 Git 保存。导出和发布包在验收后清理，实际回执、固定样本及难以重取的人工资料按[工程约定](AGENTS.md)保留。Git 合并和推送均不会触发灰机 Wiki 发布。

## 权利与署名

项目原创软件采用 **MIT**，Wiki 原创页面及模板内容采用 **CC BY-SA 3.0**，本项目独立完成的数据选取与编排采用 **CC BY 4.0**。已上线的原创程序可选择的许可、游戏内容的权利归属和外部来源见 [LICENSE](LICENSE)、[授权范围](RIGHTS.md) 和[第三方署名](THIRD_PARTY.md)。第三方配装工具的武器对照表留在维护者本地，页面生成、预览和常规武器导入读取正式资料。
