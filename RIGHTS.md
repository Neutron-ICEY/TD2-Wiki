# TD2 Wiki 授权与署名

| 作品范围 | 适用许可与再使用方式 |
| --- | --- |
| 原创软件、测试和配套软件说明 | **MIT**。包括 `tools/` 的维护程序、`ui/` 的 Reader、Editor 与 Catalog 程序、相应测试和软件使用说明。复制软件或其重要部分时附上版权声明和 MIT 全文。第三方数据、示例中引用的游戏文案及依赖按各自来源处理。[MIT 全文](LICENSES/MIT.txt) |
| Wiki 页面、模板内容及站内创作 | **CC BY-SA 3.0 Unported**。适用于 `wiki/pages/`、`wiki/templates/` 和其他文件中由 Wiki 贡献者创作的内容。再发布时注明原标题、贡献者、来源、许可及改动，发布改作时遵守相同方式共享。模板中引用的游戏原文和媒体各按其来源处理。[CC BY-SA 3.0 全文](LICENSES/CC-BY-SA-3.0.txt) |
| 已在灰机发表的 Lua、CSS、JavaScript | 对本项目拥有完整权利的原创程序逻辑，再使用者可以选择 **MIT 或 CC BY-SA 3.0**。例如原创模块、Reader 样式和 Gadget 脚本。站内前人贡献或从 Wiki 回收的外部编辑沿用原许可；只有相应权利人也授予 MIT 时，MIT 选择才覆盖这些改动。模板里的正文、生成模块内的数据与打包进 Editor 的第三方组件各自保留原条款。 |
| 独立整理的数据 | **CC BY 4.0**。适用于 `data/` 等目录中本项目有权授权的选取和编排，包括自主建立的字段结构、关联映射和原创图表数据。可署名「TD2 Wiki 贡献者」，附项目和许可链接并说明改动。单项事实、游戏文本、他人的汇编和 Wiki 改作仍按各自权利处理。生成的 Lua 数据表沿用相应数据来源。[CC BY 4.0 全文](LICENSES/CC-BY-4.0.txt) |
| 图像、字体、商标及第三方材料 | 原创图形按具体文件声明署名和使用。游戏名称、文案、美术与商标由 Ubisoft 及相应权利人管理。图片索引提供文件名、摘要和 Wiki 地址；使用图片需查看对应文件页。外部数据和软件组件的出处见[第三方署名](THIRD_PARTY.md)。 |

TD2 的 MediaWiki 站点配置声明「署名-相同方式共享」。灰机《用户编辑条款》将采用此许可的社区对应到 CC BY-SA 3.0 Unported。站内已发表版本继续适用既有许可。[TD2 站点配置](https://td2.huijiwiki.com/api.php?action=query&meta=siteinfo&siprop=rightsinfo&format=json) · [使用条款和内容声明](https://www.huijiwiki.com/wiki/Project:使用条款和内容声明) · [用户编辑条款](https://www.huijiwiki.com/wiki/Project:用户编辑条款) · [灰机 BY-SA 帮助](https://huijiwiki.com/wiki/帮助:版权信息%28CC_BY-SA%29)

## 如何署名

`publishing/registry.json` 将本地源对应到 Wiki 标题。Gadget 和 Editor 包另查前端发布映射。已核实的修订号记录在 `publishing/baseline.json`。引用单页时附原页面及贡献历史；批量复用时可随附标题与来源映射，保留原页面已有的第三方署名。[对象登记](publishing/registry.json) · [发布基准](publishing/baseline.json) · [前端发布映射](publishing/reader-editor-production.json)

例如「《Module:TD2武器》，全境封锁2国际服 Wiki 贡献者，CC BY-SA 3.0，取自修订 4203」，附上修订和历史链接。改编者另注明自己的修改。复用结构化资料时，可写「数据整理：TD2 Wiki 贡献者，CC BY 4.0」，附仓库版本，并保留相关第三方来源。[Wiki 原修订](https://td2.huijiwiki.com/wiki/Special:PermanentLink/4203) · [贡献历史](https://td2.huijiwiki.com/index.php?title=Module:TD2武器&action=history) · [协作仓库](https://github.com/Neutron-ICEY/TD2-Wiki)
