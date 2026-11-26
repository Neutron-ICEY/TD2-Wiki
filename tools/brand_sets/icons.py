"""统一小图标合同：类别/稳定键 → raster → 等尺寸占位。

实体仍拥有各自配置（天赋、核心、分类），模板不再自行拼图片或猜中文文件名。
装备行/状态/材料的新映射集中于 equipment-ui.json。组合装备大图不属于小图标。
"""
from html import escape

ROW_KEYS = ('major_attribute', 'minor_attribute', 'talent_slot', 'mod_slot')
STATE_KEYS = ('red', 'blue', 'yellow', 'random', 'none')
OPTIONAL_STATE_KEYS = ('gear_mod_slot', 'proficient', 'drop', 'craft', 'named')
STATUS_LABELS = {'state/drop': '可掉落', 'state/named': '具名装备'}
CATEGORY_STATES = {'offense': 'red', 'defense': 'blue', 'utility': 'yellow'}
EMPTY_ICON = {'wiki_file': '', 'confirmed_on_wiki': False}
PLACEHOLDER = '<span class="td2-icon-placeholder" aria-hidden="true"></span>'


# Wiki UI notation, not game assets or Catalog identities.
UI_SYMBOLS = {
    'state/none': '⊘', 'state/unknown': '?',
    'state/drop': '落', 'state/craft': '制', 'state/named': '名',
    'material/brand_material': '?', 'material/unverified': '?',
}


def ui_fallback(key):
    symbol = UI_SYMBOLS.get(key)
    return ('<span class="td2-icon-symbol" aria-hidden="true">' + symbol + '</span>') if symbol else PLACEHOLDER


def annotate_status(key, rendered):
    """Keep each approved status name available to pointer, keyboard and screen readers."""
    label = STATUS_LABELS.get(key)
    return ('<span class="td2-status-icon" tabindex="0" role="img" aria-label="' + label + '" data-tooltip="' + label + '">' + rendered + '</span>') if label else rendered


def weapon_talent_icons(root):
    from tools.identity import read_json
    talents = read_json(root / 'data/brand-sets/talents.json')['talents']
    icons = {row['id']: row['icon'] for row in talents
             if row['id'].startswith('weapon_talent_') and row.get('icon', {}).get('wiki_file')}
    for uid, icon in read_json(root / 'data/equipment/weapon-navbox-talents.json').items():
        key = 'weapon_talent_' + uid
        if key in icons and icons[key]['wiki_file'] != icon['wiki_file']:
            raise ValueError('Conflicting weapon talent icon: ' + uid)
        icons[key] = icon
    return icons


def mappings(ui=None, categories=None, core=None, talents=None, gear_sets=()):
    """将既有集中入口投影成一张只读映射，不产生第二份人工数据库。"""
    ui = ui or {}
    result = {'state/unknown': EMPTY_ICON}
    rows = ui.get('icons', {})
    for key in ROW_KEYS:
        result['equipment_row/' + key] = rows.get(key, EMPTY_ICON)
    for key in STATE_KEYS + tuple(k for k in OPTIONAL_STATE_KEYS if k in ui.get('state_icons', {})):
        result['state/' + key] = ui.get('state_icons', {}).get(key, EMPTY_ICON)
    for key, icon in (categories or {}).get('icons', {}).items():
        result['attribute_category/' + key] = icon
    for kind, entries in (core or {}).get('icons', {}).items():
        for key, icon in entries.items():
            result['core_' + kind + '/' + key] = icon
    for item in (talents or {}).get('talents', []):
        result['talent/' + item['id']] = item['icon']
    for key, icon in ui.get('material_icons', {}).items():
        result['material/' + key] = icon
    for key, icon in ui.get('weapon_icons', {}).items():
        result['weapon/' + key] = icon
    # 标题卡的小图标直接复用已有六张通用部位图，不新增人工图片目录。
    for key, icon in ui.get('slot_visuals', {}).items():
        result['equipment_slot/' + key] = icon
    for item in gear_sets:
        for key, icon in item.get('talent_icons', {}).items():
            if 'talent/' + key in result:
                raise ValueError('GEAR_SET_ICON_COLLISION')
            result['talent/' + key] = icon
    return result


def call(category, key):
    return '{{TD2图标|类别=' + category + '|键=' + key + '}}'


def material_row_source(ui):
    """Reuse the icon resolver; the material page owns prose, never the row."""
    from .build import HEADER
    rows = {}
    quantity = '{{#switch:{{{显示数量|是}}}|否=|#default=<span class="td2-material-value"><span class="td2-material-quantity">{{#if:{{{数量|}}}|{{{数量}}}|数量待核实}}</span>{{#if:{{{概率说明|}}}|<span class="td2-material-probability">[{{{概率说明}}}]</span>}}</span>}}'
    for material_id, info in ui.get('material_display', {}).items():
        name = '{{{名称|' + info['name'] + '}}}'
        target = next((r['title'] for r in __import__('tools.identity',fromlist=['registry']).registry() if r['id']==info.get('page_ref')), name) if info else name
        if info.get('brand_ref'):
            icon = '<span class="td2-icon">{{TD2品牌图片|品牌=' + info['brand_ref'] + '|用途=icon|链接=' + target + '}}</span>'
        elif ui['material_icons'][info['icon_key']]['confirmed_on_wiki']:
            icon = wikitext_icon('material/' + info['icon_key'], ui['material_icons'][info['icon_key']]).replace('{{{链接|}}}', target)
        else:
            icon = '{{TD2图标|类别=material|键=' + info['icon_key'] + '|链接=' + target + '}}'
        rows[material_id] = ('<span class="td2-material-row td2-material-' + info['quality'] + '">'
                      '<span class="td2-material-quality" aria-hidden="true"></span>'
                      + icon + '<span class="td2-material-name">[[' + target + '|' + name + ']]</span>' + quantity + '</span>')
    fallback = ('<span class="td2-material-row td2-material-unknown"><span class="td2-material-quality" aria-hidden="true"></span>'
                '<span class="td2-icon">{{#if:{{{品牌|}}}|{{TD2品牌图片|品牌={{{品牌}}}|用途=icon|链接={{{名称|}}}}}}}</span>'
                '<span class="td2-material-name">[[{{{名称|材料待核实}}}]]</span>' + quantity + '</span>')
    owners='{{#switch:{{{品牌|}}}'+''.join('|'+v['brand_ref']+'='+k for k,v in ui.get('material_display',{}).items() if v.get('brand_ref'))+'|#default=}}'
    selector='{{{材料ID|'+owners+'}}}'
    return '<noinclude>' + HEADER + '材料ID或所属实体ID解析资源；名称仅作显示。品质色为Wiki视觉设计。</noinclude><includeonly>{{#if:{{{名称|}}}|{{#switch:'+selector+'\n' + '\n'.join('|' + name + '=' + row for name, row in rows.items()) + '\n|#default=' + fallback + '\n}}}}</includeonly>'


def material_row_html(ui, name, quantity, brand_catalog=None, probability='', material_id=None):
    if not name.strip():
        return ''
    info = ui.get('material_display', {}).get(material_id)
    target = next((r['title'] for r in __import__('tools.identity',fromlist=['registry']).registry() if r['id']==info.get('page_ref')), name) if info else name
    icon = html_icon('material', info['icon_key']) if info else '<span class="td2-icon"></span>'
    if info and info.get('brand_ref') and brand_catalog is not None:
        from urllib.parse import quote
        names = brand_catalog['entity_images']
        filename = names.get(info['brand_ref'], '')
        if filename:
            icon = '<span class="td2-icon"><img data-brand-file="' + escape(filename, quote=True) + '" src="images/' + quote(filename) + '" alt=""></span>'
    value = '<span class="td2-material-value"><span class="td2-material-quantity">' + escape(quantity or '数量待核实') + '</span>' + ('<span class="td2-material-probability">[' + escape(probability) + ']</span>' if probability else '') + '</span>'
    content = icon + '<a class="td2-material-name" href="/wiki/' + escape(target, quote=True) + '">' + escape(name) + '</a>' + value
    return '<span class="td2-material-row td2-material-' + (info['quality'] if info else 'unknown') + '"><span class="td2-material-quality" aria-hidden="true"></span>' + content + '</span>'


def wikitext_icon(key, icon):
    filename = icon['wiki_file']
    # Only explicit heading use gets 64px raster output; ordinary icons stay 24px.
    size = '80x80px' if key.startswith('talent/') or key == 'state/proficient' else '24x24px'
    fallback = ui_fallback(key)
    file = '[[File:' + filename + '|' + size + '|link={{{链接|}}}|alt=]]' if filename else ''
    image = file if filename else fallback
    rendered = '<span class="td2-icon" data-icon-key="' + escape(key, quote=True) + '">' + image + '</span>'
    if key == 'state/proficient':
        # No configured chapter mark leaves no empty icon box.
        optional = '<span class="td2-icon" data-icon-key="state/proficient">[[File:' + filename + '|80x80px|link=|alt=]]</span>' if filename else ''
        return optional
    if key.startswith('equipment_slot/'):
        return '{{#switch:{{{用途|}}}|heading=' + rendered.replace('|24x24px|', '|64x64px|') + '|#default=' + rendered + '}}'
    return annotate_status(key, rendered)


def resolver_source(entries):
    from .build import switch_template
    fallback = '<span class="td2-icon" data-icon-key="{{{类别|}}}/{{{键|}}}">' + PLACEHOLDER + '</span>'
    def optional(key, icon):
        rendered = wikitext_icon(key, icon)
        if icon.get('wiki_file'):
            return rendered
        return '{{#switch:{{{用途|}}}|optional=|#default=' + rendered + '}}'
    fallback = '{{#switch:{{{用途|}}}|optional=|#default=' + fallback + '}}'
    return switch_template({key: optional(key, icon) for key, icon in entries.items()}, fallback).replace('{{{1|}}}', '{{{类别|}}}/{{{键|}}}')


def html_icon(category, key):
    """离线预览没有真实 Wiki 图片 URL，只证明统一尺寸与稳定 key，绝不假造素材。"""
    key = category + '/' + key
    return annotate_status(key, '<span class="td2-icon" data-icon-key="' + escape(key, quote=True) + '">' + ui_fallback(key) + '</span>')


def pool_wikitext(ui, pool):
    info = ui.get('talent_pools', {}).get(pool)
    if not info:
        return '天赋规则待核实'
    label, target = info['label'], info['target']
    return '[[' + target + '|' + label + ']]' if target else label


def pool_label(ui, pool):
    return ui.get('talent_pools', {}).get(pool, {}).get('label', '天赋规则待核实')
