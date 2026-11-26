from tools.identity import read_json
"""Equipment navigation derived from maintained Reader records; no site writes."""
import argparse
import json
import shutil
import subprocess
from html import escape
from pathlib import Path
from urllib.parse import quote

from tools.publish.bundle import require
import re
ID = re.compile(r"(?:[a-z][a-z0-9_-]{2,79}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})$")

def navigation(record, anchor_available=True):
    return record['parent_page'] + ('#' + record['anchor'] if anchor_available and record.get('anchor') else '')
from .slots import SLOTS, SLOT_LABELS, CARD_ORDER

SOURCE = 'wiki/templates/TD2装备导航.wiki'
GENERATOR = 'tools/brand_sets/navbox.py@v1'
SECTIONS = (('brands', '品牌套装'), ('gear_sets', '装备组'), ('named', '具名装备'), ('exotics', '奇特装备'))
CONFIG = 'ui/brand-sets/equipment-navbox.json'


def exotic_rows(records, talents, icons):
    """Project canonical armor identity and the first talent without guessing missing art."""
    result, seen = [], set()
    by_id = {t['id']: t for t in talents}
    for row in records:
        fields = row['params']
        slot, identity = fields['装备部位'], fields['装备ID']
        require(slot in SLOTS and identity not in seen, 'Invalid or duplicate exotic armor')
        seen.add(identity)
        refs = list(dict.fromkeys(r['图标'] for r in row.get('effects', []) if r.get('图标')))
        require(all(ref in by_id for ref in refs), 'Unknown exotic talent reference')
        icon = by_id[refs[0]].get('icon') or {} if refs else {}
        visual = icons['slot_visuals'][slot]
        result.append(dict(name=fields['装备名称'], target=row['title'], slot=slot,
                           icon=icon.get('wiki_file', ''), slot_icon=visual.get('wiki_file', '')))
    return sorted(result, key=lambda row: CARD_ORDER.index(row['slot']))


def project(root):
    """Reuse the formal Editor parser and Reader anchor contract without editing either."""
    records = json.loads(subprocess.check_output(['node', str(Path(__file__).with_name('navbox-records.cjs')), str(root.resolve())], encoding='utf8'))
    pages = records['pages']
    name_rank = {key: index for index, key in enumerate(records['named_order'])}
    catalog = read_json(root / 'data/brand-sets/brands.json')
    icons = read_json(root / 'data/brand-sets/equipment-ui.json')
    images = catalog['entity_images']
    talents = {row['id']: row for row in read_json(root / 'data/brand-sets/talents.json')['talents']}
    result = {key: [] for key, _ in SECTIONS}
    seen = set()
    for page in pages:
        name = page['params']['套装全称']
        image = images.get(page['id'], '')
        result['brands'].append(dict(entity_id=page['id'], name=name, target=page['title'], icon=image))
        for item in page['named']:
            require(item.get('装备部位') in SLOTS, 'Navbox only accepts armor slots')
            key = item.get('stable_id', '')
            require(ID.fullmatch(key) and key not in seen, 'Invalid or duplicate named anchor')
            seen.add(key)
            talent = talents.get(item.get('talent_icon'))
            require(item.get('talent_mode') != 'fixed' or talent is not None, 'Missing named talent icon reference: ' + key)
            named_icon = image
            if talent and talent['en_name'].startswith(('Perfect ', 'Perfectly ')):
                named_icon = talent.get('icon', {}).get('wiki_file', '')
                require(bool(named_icon), 'Missing perfect talent icon: ' + key)
            result['named'].append(dict(name=item['装备名称'], slot=item['装备部位'], target=navigation(dict(parent_page=page['title'], anchor='named-' + key)),
                                        brand=name, icon=named_icon,
                                        slot_icon=icons['slot_visuals'][item['装备部位']].get('wiki_file', '')))
    gear_sets = read_json(root / 'data/gear-sets/sets.json')['sets']
    registry = read_json(root / 'publishing/registry.json')['entries']
    for gear_set in gear_sets:
        require(any(row.get('related_entity') == gear_set['id'] and row['source'] == gear_set['source'] and row['title'] == gear_set['page_title'] for row in registry), 'Gear set navigation requires registered identity')
        logo = gear_set.get('logo', {})
        result['gear_sets'].append(dict(name=gear_set['title'], target=gear_set['page_title'], icon=logo.get('wiki_file', '')))
    order = read_json(root / CONFIG)['brand_order']
    rank = {title: index for index, title in enumerate(order)}
    result['brands'].sort(key=lambda row: rank.get(row['entity_id'], len(rank)))
    from tools.identity import page as page_address, asset as asset_address
    entities = read_json(root / 'data/equipment/records.json')['entities']
    for extra in read_json(root / CONFIG).get('brand_supplements', []):
        entity_id = extra['entity_id']
        target = page_address(entity_id, root)
        entity = entities[entity_id]
        require(entity['source'] == target['source'] and (root / target['source']).is_file(), 'Navigation supplement requires registered source')
        require(not any(row['entity_id'] == entity_id for row in result['brands']), 'Duplicate navigation supplement')
        result['brands'].append(dict(entity_id=entity_id, name=entity['fields']['套装全称'], target=target['title'], icon=asset_address(extra['asset_ref'], root)['title'].split(':', 1)[1]))
    result['named'].sort(key=lambda row: (CARD_ORDER.index(row['slot']), name_rank[row['target'].split('#named-')[1]]))
    result['exotics'] = exotic_rows(records['exotics'], read_json(root / 'data/exotic-gear/talents.json')['talents'], icons)
    return result


def markup(sections, wiki=True, config=None, *, section_labels=SECTIONS, group_labels=SLOT_LABELS, group_order=CARD_ORDER, label='装备导航', grouped=('named','exotics'), image_size='40x40px'):
    """Render identical structure for the Wiki template and local HTML review."""
    def card(row):
        name, target, icon = (escape(row[k], quote=True) for k in ('name', 'target', 'icon'))
        if wiki:
            label = '[[' + target + '|' + name + ']]'
            art = '[[File:' + icon + '|' + image_size + '|link=|alt=]]' if icon else ''
        else:
            label = '<a href="https://td2.huijiwiki.com/wiki/' + quote(row['target'].split('#')[0].replace(' ', '_')) + ('#' + quote(row['target'].split('#')[1]) if '#' in row['target'] else '') + '">' + name + '</a>'
            art = '<img src="images/' + quote(row['icon']) + '" alt="">' if icon else ''
        tooltip = ' title="' + escape(row['name'] + ' · ' + row['brand'], quote=True) + '"' if row.get('brand') else ''
        slot = row.get('slot_icon', '')
        watermark = ''
        if slot:
            slot_art = '[[File:' + escape(slot, quote=True) + '|40x40px|link=|alt=]]' if wiki else '<img src="images/' + quote(slot) + '" alt="">'
            watermark_class = 'td2-navbox-slot-watermark' + (' td2-navbox-talent' if row.get('talent_watermark') else '')
            watermark = '<span class="' + watermark_class + '" aria-hidden="true">' + slot_art + '</span>'
        return '<div class="td2-navbox-card" data-target="' + target + '"' + tooltip + '><span class="td2-navbox-icon">' + art + '</span><span class="td2-navbox-name">' + label + '</span>' + watermark + '</div>'

    config = config or {'default_open': True, 'section_open': {}}

    def panel(label, body, key):
        override = config['section_open'].get(key)
        state = '' if override is None else ' data-default-open="' + str(override).lower() + '"'
        # Index pages need fragment targets in the server HTML, before Reader runs.
        anchor = ''
        if wiki and key != 'all':
            anchor = '{{#if:{{{索引|}}}|id="td2-index-' + key + '" style="scroll-margin-top:4rem"}} '
        tag = 'h2' if key == 'all' else 'div'
        heading = f'<{tag} class="td2-navbox-heading">{label}</{tag}>'
        return '<div ' + anchor + 'class="td2-navbox-panel" data-section="' + key + '"' + state + '>' + heading + '<div class="td2-navbox-body">' + body + '</div></div>'

    def grid(rows):
        return '<div class="td2-navbox-grid">' + '\n'.join(card(row) for row in rows) + '</div>'

    def groups(rows):
        return '\n'.join('<div class="td2-navbox-slot-group" data-slot="' + slot + '"><div class="td2-navbox-slot-label">' + group_labels[slot] + '</div>' + grid([row for row in rows if row['slot'] == slot]) + '</div>' for slot in group_order if any(row['slot'] == slot for row in rows)) if rows else grid([])
    sections_html = ''.join(panel(title, groups(sections[key]) if key in grouped else grid(sections[key]), key) for key, title in section_labels)
    return '<div class="td2-navbox" role="navigation" aria-label="'+escape(label)+'" data-default-open="' + str(config['default_open']).lower() + '">' + panel(label, sections_html, 'all') + '</div>'


def source(root):
    return '<noinclude>自动生成，禁止手改；运行 python -m tools.brand_sets generate。名称、链接及图标来自既有品牌源与 Catalog；默认展开与排序由 ui/brand-sets/equipment-navbox.json 维护。</noinclude><includeonly>' + markup(project(root), config=read_json(root / CONFIG)) + '</includeonly>\n'


def generate(root, check=False):
    from tools.generation import plan, apply
    registry = read_json(root / 'publishing/registry.json')
    return bool(apply(plan(root, {SOURCE: source(root)}, registry, {SOURCE: GENERATOR}), check))


def preview(root, output):
    """Create a fresh static review using production markup, CSS, JS and existing images."""
    require(not output.exists(), 'Use a fresh preview directory')
    sections = project(root)
    output.mkdir(parents=True)
    (output / 'images').mkdir()
    for filename in {r.get(key) for rows in sections.values() for r in rows for key in ('icon', 'slot_icon') if r.get(key)}:
        matches = list((root / 'assets').rglob(filename))
        require(bool(matches), 'Missing local preview image: ' + filename)
        shutil.copyfile(matches[0], output / 'images' / filename)
    for ext in ('css', 'js'):
        shutil.copyfile(root / ('ui/brand-sets/brand-sets.' + ext), output / ('reader.' + ext))
    body = markup(sections, wiki=False, config=read_json(root / CONFIG))
    html = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>装备导航本地预览</title><link rel="stylesheet" href="reader.css"><style>body{margin:0;padding:24px;background:#151515;color:#eee;font:16px/1.5 sans-serif}main{max-width:1160px;margin:auto}body.narrow main{width:342px;max-width:100%}</style><main id="mw-content-text"><div class="mw-parser-output"><div class="td2-brand" data-brand="5.11 Tactical"><h1>5.11 Tactical</h1>' + body + '</div><p id="after-reader">正文末尾</p></div></main><script src="reader.js"></script></html>'
    (output / 'index.html').write_text(html, encoding='utf8')
    (output / 'narrow.html').write_text(html.replace('<main id=', '<body class="narrow"><main id='), encoding='utf8')
    (output / 'responsive.html').write_text('<!doctype html><meta charset="utf-8"><title>390 / 320px</title><style>body{background:#111;color:white;display:flex;gap:20px}iframe{height:800px;border:0}</style><iframe title="390px" width="390" src="index.html"></iframe><iframe title="320px" width="320" src="index.html"></iframe>', encoding='utf8')
    (output / 'lifecycle.html').write_text(html.replace(body, body + body).replace('<script src="reader.js"></script>', '<script src="reader.js"></script><script src="reader.js"></script>'), encoding='utf8')
    (output / 'data.json').write_text(json.dumps(sections, ensure_ascii=False, indent=2), encoding='utf8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('generate', 'check', 'preview'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.command == 'preview':
        require(args.output is not None, 'Preview output required')
        preview(Path.cwd(), args.output)
    else:
        generate(Path.cwd(), args.command == 'check')
