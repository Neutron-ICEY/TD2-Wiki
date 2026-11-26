"""Local-only Lua preview; serves an isolated review directory and never writes Wiki content."""
import argparse
import base64
from functools import lru_cache
import html
from http.server import SimpleHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.equipment.wikitext import WikiSubset
from tools.identity import registry


def copy_registered_pngs(images):
    for entry in registry(ROOT):
        if entry['kind']=='assets' and entry['source'].endswith('.png'):
            shutil.copyfile(ROOT/entry['source'],images/entry['title'].split(':',1)[1])


def render_definition_lists(markup):
    def block(match):
        items=[]
        for line in match[0].splitlines():
            tag='dt' if line[0]==';' else 'dd'
            items.append('<'+tag+'>'+line[1:]+'</'+tag+'>')
        return '<dl>'+''.join(items)+'</dl>\n'
    return re.sub(r'^(?:[;:][^\n]*(?:\n|$))+',block,markup,flags=re.M)


def render(raw, directory, page_urls=None, *, today=None):
    images=directory/'images'
    names={p.name for p in images.glob('*') if p.is_file()}
    result=WikiSubset(ROOT,existing_files={'File:'+name for name in names},today=today).expand(raw,{})

    @lru_cache(maxsize=None)
    def thumbnail(name, size):
        original='/images/'+quote(name)
        if not size:
            return original, ''
        width, height = re.fullmatch(r'(\d*)(?:x(\d+))?px', size).groups()
        dimensions = ''.join(' '+key+'="'+value+'"' for key,value in (('width',width),('height',height)) if value)
        source=images/name
        if source.suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):
            return original, dimensions
        from PIL import Image
        with Image.open(source) as image:
            bounds=(int(width or image.width), int(height or image.height))
            if min(bounds)<1 or (image.width<=bounds[0] and image.height<=bounds[1]):
                return original, f' width="{image.width}" height="{image.height}"'
            target=images/'thumbs'/size/(name+'.png')
            if not target.exists() or target.stat().st_mtime_ns<source.stat().st_mtime_ns:
                target.parent.mkdir(parents=True,exist_ok=True)
                image.thumbnail(bounds, Image.Resampling.LANCZOS)
                image.save(target, 'PNG')
        with Image.open(target) as thumb:
            return '/images/'+quote(target.relative_to(images).as_posix()), f' width="{thumb.width}" height="{thumb.height}"'

    def page_href(target):
        if target.startswith('#'):return target
        if page_urls is None:return '#'
        title,separator,anchor=target.partition('#')
        return page_urls.get(title,'https://td2.huijiwiki.com/wiki/'+quote(title))+(('#'+quote(anchor)) if separator else '')

    def link(m):
        parts=m[1].split('|');target=parts[0]
        if target.startswith(('File:','文件:')):
            name=target.split(':',1)[1]
            if name not in names:return '<span class="td2-icon-placeholder"></span>'
            size=next((s for s in parts[1:] if re.fullmatch(r'(?:\d+|\d*x\d+)px',s)),None)
            src,size_attributes=thumbnail(name,size)
            picture='<img alt="'+html.escape(next((s[4:] for s in parts if s.startswith('alt=')),''),quote=True)+'" src="'+src+'"'+size_attributes+'>'
            destination=next((part[5:] for part in parts[1:] if part.startswith('link=')),None)
            if page_urls is None or destination=='':return picture
            if destination is None:return '<a class="image" href="/images/'+quote(name)+'">'+picture+'</a>'
            return '<a href="'+html.escape(page_href(destination),quote=True)+'">'+picture+'</a>'
        return '<a href="'+html.escape(page_href(target),quote=True)+'">'+(parts[-1] if len(parts)>1 else target)+'</a>'
    result=re.sub(r'\[\[([^\[\]]+)\]\]',link,result)
    def external_link(match):
        return '<a class="external text" href="' + html.escape(match[1], quote=True) + '">' + html.escape(match[2]) + '</a>'
    result=re.sub(r'\[(https?://[^\s<>\[\]"]+)\s+([^\[\]<>\n]+)\]',external_link,result)
    result=re.sub(r'^(={2,6})\s*(.*?)\s*\1\s*$',lambda m:'<h'+str(len(m[1]))+'>'+m[2]+'</h'+str(len(m[1]))+'>',result,flags=re.M)
    return render_definition_lists(result)


def build(directory,editor_export,*,without_assets=False):
    if directory.exists():raise ValueError('Use a fresh preview directory')
    directory.mkdir(parents=True);(directory/'images').mkdir()
    for source,name in [(ROOT/'wiki/pages/site/Common.css','common.css'),(ROOT/'ui/brand-sets/brand-sets.css','reader.css'),(ROOT/'ui/brand-sets/brand-sets.js','reader.js'),(ROOT/'tools/equipment/preview.js','preview.js'),(editor_export/'modules.js','modules.js'),(editor_export/'config.json','config.json')]:shutil.copyfile(source,directory/name)
    if not without_assets:
        copy_registered_pngs(directory/'images')
    data={}
    for key,group,name in [('brand','brands','brand-511-tactical'),('hunter','brands','brand-page-4cdce5b25aabbccb00068ab8525b92b5'),('turmoil','brands','brand-page-4cdce5b25aabe95f00006a2573bf4974'),('punch','brands','brand-page-4cdce5b25aabe77600006a0d6991ecd2'),('gear','gear-sets','gear-set-ongoing-directive'),('core','gear-sets','gear-set-z'),('memento','exotic-gear','exotic-page-memento'),('investor','exotic-gear','exotic-page-investor'),('acosta','exotic-gear','exotic-page-acosta'),('sources','exotic-gear','exotic-page-b005013565e83fa600079a2bca93353e')]:
        entry=next(r for r in registry(ROOT) if r['id']==name)
        data[key]=dict(raw=(ROOT/entry['source']).read_text('utf8'),title=entry['title'])
    (directory/'samples.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf8')
    shell='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TD2 装备预览</title><link rel="stylesheet" href="/common.css"><link rel="stylesheet" href="/reader.css"><style>body{margin:0;background:#191919;color:#f5f5f5;font:16px/1.6 Arial,"Microsoft YaHei",sans-serif}a{color:rgb(254,169,0)}main{max-width:1160px;margin:0 auto;padding:24px}h2{font-size:30px;font-weight:500}nav{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}button,select{font:inherit}nav button,nav select{background:#282828;color:#fff;border:1px solid #666;border-radius:3px;padding:4px 12px}#wiki-body{background:#191919}img{object-fit:contain;vertical-align:middle;max-width:100%}@media(max-width:640px){main{padding:12px}}</style><main id="wiki-body"><nav><select id="sample" aria-label="样本"></select><button id="edit">编辑</button><button id="export">导出 WikiText</button></nav><h1 id="title"></h1><div id="mw-content-text"><div class="mw-parser-output"></div></div></main><script src="/modules.js"></script><script src="/reader.js"></script><script src="/preview.js"></script></html>'''
    shell=shell.replace('<link rel="stylesheet" href="/common.css">','<style>'+(ROOT/'wiki/pages/site/Common.css').read_text(encoding='utf8')+'</style>')
    skin=Path(__file__).with_name('preview-skin.css').read_text(encoding='utf8')
    shell=shell.replace('<style>', '<style>'+skin+'</style><style>',1)
    shell=shell.replace('color:#f5f5f5;font:16px/1.6','color:#fff;font:16px/1.42857')
    shell=shell.replace('<main id="wiki-body">','<body class="ns-subject sitedir-ltr"><main id="wiki-body"><div id="content">')
    shell=shell.replace('id="mw-content-text"','id="mw-content-text" class="mw-content-ltr"')
    shell=shell.replace('</main>','</div></main>')
    (directory/'index.html').write_text(shell.replace('href="/','href="').replace('src="/','src="'),encoding='utf8')
    for key,item in data.items():
        body=render(item['raw'],directory)
        standalone=shell.split('<nav>')[0]+('<h1>'+html.escape(item['title'])+'</h1><div id="mw-content-text" class="mw-content-ltr"><div class="mw-parser-output">'+body+'</div></div></div></main><script src="reader.js"></script></html>')
        standalone=standalone.replace('href="/reader.css"','href="reader.css"').replace('href="/common.css"','href="common.css"').replace('src="/images/','src="images/')
        (directory/(key+'.html')).write_text(standalone,encoding='utf8')
    print(directory/'index.html')


def serve(directory,port):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(directory),**kwargs)
        def do_POST(self):
            if self.path!='/parse':self.send_error(404);return
            size=int(self.headers.get('Content-Length','0'))
            if size<=0 or size>262144:self.send_error(413);return
            try:
                request=json.loads(self.rfile.read(size));raw=request['raw']
                if not isinstance(raw,str):raise ValueError('WikiText required')
                rendered=render(raw,directory)
                for image in (directory/'images').rglob('*.png'):
                    reference='/images/'+quote(image.relative_to(directory/'images').as_posix())
                    if reference in rendered:rendered=rendered.replace(reference,'data:image/png;base64,'+base64.b64encode(image.read_bytes()).decode('ascii'))
                result=dict(html=rendered,head='',modules=[],styles=[],warnings=[])
                encoded=json.dumps(result,ensure_ascii=False).encode('utf8')
                self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(encoded)));self.end_headers();self.wfile.write(encoded)
            except Exception as exc:self.send_error(400,str(exc))
    HTTPServer(('127.0.0.1',port),Handler).serve_forever()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['build','serve']);parser.add_argument('directory',type=Path);parser.add_argument('--editor-export',type=Path);parser.add_argument('--port',type=int,default=8767)
    parser.add_argument('--without-assets',action='store_true',help='Build a source preview with the existing image placeholders')
    a=parser.parse_args()
    if a.mode=='build':build(a.directory.resolve(),a.editor_export.resolve(),without_assets=a.without_assets)
    else:serve(a.directory.resolve(),a.port)
