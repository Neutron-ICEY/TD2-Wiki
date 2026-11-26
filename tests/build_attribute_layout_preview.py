"""Build isolated before/after pages using maintained renderers and DOM/style assertions."""
import argparse
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.equipment.preview import build, render


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--editor-export', type=Path, required=True)
    args = parser.parse_args()
    directory = args.directory.resolve()
    build(directory, args.editor_export.resolve())
    shell = (directory/'memento.html').read_text(encoding='utf8').split('<div id="mw-content-text">')[0]
    cases = {
        'brand-multi': '<div class="td2-brand"><h2>品牌多核心结构测试（非游戏资料）</h2>{{TD2普通装备规则|backpack|主属性=red;blue;yellow|同时拥有主核心=是}}</div>',
        'corestrength': (ROOT/'wiki/pages/gear-sets/装备组-核心力量.wiki').read_text(encoding='utf8'),
    }
    for name, raw in cases.items():
        content = render(raw, directory).replace('src="/images/', 'src="images/')
        (directory/(name+'.html')).write_text(shell+'<div id="mw-content-text"><div class="mw-parser-output">'+content+'</div></div></main><script src="reader.js"></script></html>', encoding='utf8')
    shutil.copyfile(ROOT/'tests/attribute_layout.browser.js', directory/'attribute-layout.browser.js')
    for file in directory.glob('*.html'):
        file.write_text(file.read_text(encoding='utf8').replace('</html>', '<script src="attribute-layout.browser.js"></script></html>'), encoding='utf8')


if __name__ == '__main__':
    main()
