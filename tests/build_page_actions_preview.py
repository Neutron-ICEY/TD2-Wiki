"""Isolated static preview of the actual Lua output, Reader JS and CSS."""
import argparse
import html
import json
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import identity
from tools.equipment.preview import render
from tools.equipment.wikitext import WikiSubset


def build(directory):
    directory.mkdir(parents=True, exist_ok=False)
    (directory / 'images').mkdir()
    registry = identity.registry(ROOT)
    pages = {r['id']: r for r in registry}
    assets = {r['title'].split(':', 1)[-1]: r for r in registry if r['kind'] == 'assets'}
    cases = [('threat', 'mechanic-threat', 903, False), ('511', 'brand-511-tactical', 617, True),
             ('belstone', 'brand-page-346395bc5f16893600033057664d551b', 664, True),
             ('golan', 'brand-page-4cdce5b25aabbccb00068ab8525b92b5', 641, True),
             ('hotshot', 'gear-set-p', 700, True)]
    for source, target in [('ui/brand-sets/brand-sets.js', 'reader.js'), ('ui/brand-sets/brand-sets.css', 'reader.css'),
                           ('wiki/pages/site/Common.css', 'common.css'), ('tools/equipment/preview-skin.css', 'skin.css'),
                           ('tests/page_actions_preview.js', 'context.js')]:
        shutil.copyfile(ROOT / source, directory / target)
    reader = WikiSubset(ROOT)
    nav = ' '.join('<a data-preview-page href="' + key + '.html">' + html.escape(pages[pid]['title']) + '</a>' for key, pid, _, _ in cases)
    for key, pid, pageid, form in cases:
        page = pages[pid]
        raw = (ROOT / page['source']).read_text('utf8')
        expanded = reader.expand(raw, {})
        for filename in set(re.findall(r'\[\[(?:File|文件):([^|\]]+)', expanded)):
            if filename in assets and not (directory / 'images' / filename).exists():
                shutil.copyfile(ROOT / assets[filename]['source'], directory / 'images' / filename)
        body = render(raw, directory).replace('src="/images/', 'src="images/')
        body = body.replace('<span class="td2-attribute-link"><a href="#">',
                            '<span class="td2-attribute-link"><a href="https://td2.huijiwiki.com/wiki/' + quote(pages['mechanic-threat']['title']) + '">')
        title = html.escape(page['title'])
        metadata = json.dumps(dict(title=page['title'], pageid=pageid, form=form), ensure_ascii=False)
        source = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>本地页面操作验证</title><link rel="canonical" href="https://td2.huijiwiki.com/wiki/''' + quote(page['title']) + '''">
<link rel="stylesheet" href="skin.css"><link rel="stylesheet" href="common.css"><link rel="stylesheet" href="reader.css">
<style>body{margin:0;background:#fff;color:#fff;font:16px/1.42857 Arial,sans-serif}#wiki-outer-body{background:#111}#wiki-body{background:#222}main{max-width:1160px;margin:auto;padding:24px}.preview-controls{background:#242424;padding:12px;font-size:14px}.preview-controls nav{display:flex;gap:16px;flex-wrap:wrap;margin-top:8px}.page-header{border-bottom:1px solid #404040;padding-bottom:12px}h1{font-size:36px;line-height:1.1;font-weight:500}img{max-width:100%;object-fit:contain}textarea{display:block;width:100%;font:16px sans-serif;color:#111}@media(max-width:640px){main{padding:12px}h1{font-size:28px}}</style>
<body class="ns-0 ns-subject action-view sitedir-ltr"><aside class="preview-controls">本地验证 · 身份和服务端响应为模拟，无线上保存。
<label>身份 <select id="preview-role"><option value="admin">管理员</option><option value="user">普通认证用户</option><option value="guest">游客</option><option value="blocked">管理员无编辑权</option></select></label><nav>''' + nav + '''</nav></aside>
<div id="wiki-outer-body" class="huiji-css-hook"><main id="wiki-body"><div id="content"><header id="firstHeading" class="page-header"><h1>''' + title + '''</h1><div id="huiji-h1-edit-button"><a id="ca-edit" class="icon-edit-code" href="#">源码</a></div><div id="contentSub"></div></header>
<div id="bodyContent"><div id="mw-content-text"><div class="mw-parser-output">''' + body + '''</div></div></div></div></main></div>
<aside class="preview-controls"><p id="preview-form" hidden>表单按钮可用；真实 Editor 合同与保存权限由专项测试验证。</p><label>复制结果核验<textarea id="clipboard-proof" aria-label="复制结果核验"></textarea></label></aside>
<script id="preview-page" type="application/json">''' + metadata + '''</script><script src="context.js"></script><script src="reader.js"></script></html>'''
        (directory / (key + '.html')).write_text(source, encoding='utf8')
    (directory / 'index.html').write_text('<!doctype html><meta charset="utf-8"><title>页面操作预览</title>' + nav, encoding='utf8')
    print(directory)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    build(parser.parse_args().directory.resolve())
