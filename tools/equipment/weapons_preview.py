"""Static local weapon review using the maintained Lua Reader and Navbox."""
import argparse
import html
import json
from pathlib import Path
import re
import shutil
import sys
from .preview import ROOT,copy_registered_pngs,render
from tools.identity import read_json


def build(directory,*,without_assets=False):
    if directory.exists():raise ValueError('Use a fresh preview directory')
    db=read_json(ROOT/'data/equipment/records.json')
    # Design iterations render representatives only. The full Navbox still uses
    # its maintained source; unsampled links retain their ordinary Wiki URL.
    sample_names={'ACS-12','ACR','圣艾尔莫引擎','圣诞颂歌','头牌明星','饥饿之人','K8 急流火焰喷射器','TAC-50 C 步枪'}
    entities=[r for r in db['entities'].values() if r['template']=='武器信息' and any(item['data']['装备名称'] in sample_names for item in r['collections']['武器型号资料']['rows'])]
    originals={row['data']['base_uid'] for e in entities for row in e['collections']['武器型号资料']['rows']
               if row['data']['kind']=='exotic' and row['data'].get('base_uid')}
    titles={e['page_title'] for e in entities}
    for uid in sorted(originals):
        base=db['entities']['weapon:'+uid.lower()]
        if base['page_title'] not in titles:entities.append(base)
    reference=next(r for r in db['entities'].values() if r['fields'].get('装备名称')=='道奇城枪手枪套')
    urls={r['page_title']:Path(r['source']).stem+'.html' for r in entities}
    urls[reference['page_title']]='equipment-reference.html'
    directory.mkdir(parents=True);(directory/'images').mkdir()
    for source,name in [('wiki/pages/site/Common.css','common.css'),('ui/brand-sets/brand-sets.css','reader.css'),('ui/brand-sets/brand-sets.js','reader.js'),('tools/equipment/preview-skin.css','skin.css')]:
        shutil.copyfile(ROOT/source,directory/name)
    if not without_assets:
        copy_registered_pngs(directory/'images')
    css='''body{margin:0;background:#191919;color:#fff;font:16px/1.42857 Arial,"Microsoft YaHei",sans-serif}main{max-width:1160px;margin:auto;padding:24px}a{color:#ffa900}img{object-fit:contain;max-width:100%}#content h1{display:block;font-size:2.4em}.preview-nav{display:flex;gap:18px;flex-wrap:wrap;margin-bottom:24px}.preview-index{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px}.preview-index a{display:block;border:1px solid #444;background:#222;padding:20px}.preview-index strong{display:block;font-size:1.2em}.preview-index small{color:#bbb}iframe{border:1px solid #555;height:85vh;background:#191919;max-width:100%}@media(max-width:640px){main{padding:12px}#content h1{font-size:2em}}'''
    def shell(title,body,config_title=None):
        config={'wgNamespaceNumber':0,'wgAction':'view','wgIsArticle':True,'wgArticleId':0,'wgUserId':0,'wgUserGroups':[],'wgPageName':config_title or title}
        stub='window.mw={config:{get:function(k){return '+json.dumps(config,ensure_ascii=False)+'[k];}},util:{getUrl:function(){return location.href.split("#")[0];}}};'
        return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+' · TD2 Wiki</title><link rel="stylesheet" href="skin.css"><link rel="stylesheet" href="common.css"><link rel="stylesheet" href="reader.css"><style>'+css+'</style><body class="ns-subject sitedir-ltr"><main id="wiki-body"><div id="content"><nav class="preview-nav"><a href="index.html">武器预览</a><a href="navigation.html">完整导航</a><a href="narrow.html">窄屏预览</a></nav><header id="firstHeading" class="page-header"><h1>'+html.escape(title)+'</h1></header><div id="mw-content-text" class="mw-content-ltr"><div class="mw-parser-output">'+body+'</div></div></div></main><script>'+stub+'</script><script src="reader.js"></script></body></html>'
    for entity in entities+[reference]:
        body=render((ROOT/entity['source']).read_text('utf8'),directory,urls).replace('src="/images/','src="images/').replace('href="/images/','href="images/')
        (directory/urls[entity['page_title']]).write_text(shell(entity['page_title'],body,entity['page_title']),encoding='utf8')
    navigation=render('{{TD2武器导航}}',directory,urls).replace('src="/images/','src="images/')
    (directory/'navigation.html').write_text(shell('武器导航',navigation),encoding='utf8')
    hosts={r['data']['装备名称']:e['page_title'] for e in entities for r in e['collections']['武器型号资料']['rows']}
    samples=[(hosts['ACS-12'],'普通武器与具名武器',''),(hosts['左边'],'左边 · 独立外观','#左边'),(hosts['印花代理人'],'印花代理人','#印花代理人'),(hosts['ACR'],'ACR',''),(hosts['圣艾尔莫引擎'],'圣艾尔莫引擎',''),(hosts['圣诞颂歌'],'圣诞颂歌','#圣诞颂歌'),(hosts['头牌明星'],'头牌明星',''),(hosts['饥饿之人'],'饥饿之人','')]
    samples += [(e['page_title'],e['page_title'],'') for e in entities if e['collections']['武器型号资料']['rows'][0]['data']['kind']=='signature']
    samples.append((reference['page_title'],'装备页对照',''))
    cards=''.join('<a href="'+urls[title]+anchor+'"><strong>'+label+'</strong><small>'+title+'</small></a>' for title,label,anchor in samples)
    (directory/'index.html').write_text(shell('武器页面预览','<div class="preview-index">'+cards+'<a href="navigation.html"><strong>武器导航</strong><small>普通 · 具名 · 奇特 · 特有</small></a></div>'),encoding='utf8')
    narrow='<label>宽度 <select id="width"><option value="390">390 px</option><option value="320">320 px</option><option value="768">768 px</option></select></label> <label>页面 <select id="sample">'+''.join('<option value="'+urls[title]+anchor+'">'+label+'</option>' for title,label,anchor in samples)+'</select></label><p></p><iframe title="窄屏武器页面" id="viewport" width="390" src="'+urls[hosts['ACS-12']]+'"></iframe><script>document.getElementById("width").onchange=function(){document.getElementById("viewport").width=this.value;};document.getElementById("sample").onchange=function(){document.getElementById("viewport").src=this.value;};</script>'
    (directory/'narrow.html').write_text(shell('窄屏预览',narrow),encoding='utf8')
    starter='''param([int]$Port = 8778)
$ErrorActionPreference = 'Stop'
$py = '__PREVIEW_PYTHON__'
if (-not (Test-Path -LiteralPath $py)) { throw 'Python interpreter unavailable' }
Write-Host "http://127.0.0.1:$Port/index.html"
& $py -B -m http.server $Port --bind 127.0.0.1 --directory $PSScriptRoot
'''
    (directory/'start-preview.ps1').write_text(starter.replace('__PREVIEW_PYTHON__',sys.executable.replace("'","''")),encoding='utf8')
    (directory/'pages.json').write_text(json.dumps(urls,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(str(directory/'index.html'),len(entities),'pages')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path)
    parser.add_argument('--without-assets',action='store_true',help='Render the Reader without local image files')
    args=parser.parse_args();build(args.directory.resolve(),without_assets=args.without_assets)
