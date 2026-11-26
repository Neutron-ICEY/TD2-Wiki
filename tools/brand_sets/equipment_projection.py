"""普通装备规则的 Wiki 投影。业务数值来自 JSON，展示调用不保存第二份事实。"""

from html import escape

from .equipment import COUNT_FIELDS, EXCEPTION_FLAGS, dismantle_amount_text, dismantle_entries, dismantle_note, dismantle_probability_text, SLOT_VISUAL_KEYS
from .icons import call, html_icon, mappings, resolver_source, pool_wikitext, ROW_KEYS
from .slots import SLOT_LABELS


def parameter(name, default=""):
    return "{{{" + name + "|" + default + "}}}"


def _armor_display(value):
    """Reader-only K display; retain exact integers in the rule source."""
    if type(value) is not int or value < 0:
        return "待核实"
    tenths = (value + 50) // 100  # Integer half-up rounding, without float drift.
    return f"{tenths // 10}.{tenths % 10}K"


def _expertise_card(base, wiki=False):
    """Existing Wiki/HTML projections share this markup; legacy documents omit the card."""
    rule = base.get("expertise")
    if rule is None:
        return ""
    percent = str(rule["armor_bonus_per_level_percent"])
    maximum = str(rule["max_level"])
    icon = call('state', 'proficient') if wiki else html_icon('state', 'proficient')
    return ('<h2 class="td2-expertise-title">专精</h2>'
            '<div class="td2-expertise-card"><div class="td2-talent-detail"><div class="td2-talent-copy">'
            '<div class="td2-equipment-row"><span class="td2-row-label">每级加成：</span><span class="td2-row-value"><strong>+' + percent + '%</strong> 装甲</span></div>'
            '<div class="td2-equipment-row"><span class="td2-row-label">等级上限：</span><span class="td2-row-value">' + maximum + '级</span></div></div><div class="td2-talent-icon">' + icon + '</div></div></div>')


def dismantle_source(base, ui, slot):
    rows = []
    for item in dismantle_entries(base, parameter('品牌材料'), slot, ui):
        note = dismantle_note(base, item)
        probability = dismantle_probability_text(base, item)
        row = '<li' + (' title="' + escape(note, quote=True) + '"' if note else '') + '>{{TD2材料行|名称=' + item['name'] + ('|品牌=' + parameter('品牌') if item.get('brand') else '') + ('|材料ID='+item['id'] if item.get('id') else '') + '|数量=' + dismantle_amount_text(item) + ('|概率说明=' + probability if probability else '') + '}}</li>'
        rows.append('{{#if:' + parameter('品牌材料') + '|' + row + '}}' if item.get('brand') else row)
    if base['部位'][slot]['dismantle']['fixed_materials'] is None:
        rows.append('<li>' + call('material', 'unverified') + '固定分解材料：待核实</li>')
    return '<ul class="td2-materials">' + ''.join(rows) + '</ul>'


def gear_dismantle_base(item, shared):
    return {'dismantle_profile': shared['dismantle_profile'], '部位': {
        slot: {'dismantle': {**shared['common'],
            'brand_material_amount': item.get('dismantle', {}).get('brand_material_amount', {'min': None, 'max': None}),
            'fixed_materials': shared['common']['fixed_materials'] + materials}}
        for slot, materials in shared['slots'].items()}}


def equipment_sources(base, ui, core_icons=None, include_resolver=True, brand_catalog=None, gear_sets=()):
    """从显式实体映射生成图片；无映射时不根据名称猜文件。"""
    from .build import GENERATED, HEADER, switch_template
    cards, dismantle = {}, {}
    for slot, rule in base["部位"].items():
        talent_text = pool_wikitext(ui, rule['talent_pool']) if rule.get('talent_pool') else rule['talent_description'] or '天赋槽位'
        args = {"部位": slot, "简介": parameter("简介"), "天赋状态": parameter("talent_mode"), "固定次属性": parameter("固定次属性"), "固定天赋引用": parameter("固定天赋引用"), "所属品牌": parameter("所属品牌"), "主属性": parameter("主属性"), "主属性内容": parameter("主属性内容"), "主属性引用": parameter("主属性引用"), "同时拥有主核心": parameter("同时拥有主核心", "否"), "基础装甲": _armor_display(rule["base_armor"]), "天赋说明": talent_text, "专精说明": rule["specialization_note"] or ""}
        for key, label in COUNT_FIELDS.items():
            if key == "major_core_slots": continue
            default = "" if rule[key] is None else str(rule[key])
            args[label] = "{{#switch:" + parameter(EXCEPTION_FLAGS[key]) + "|是=" + parameter(label) + "|#default=" + default + "}}"
        if rule.get("talent_pool") in ("backpack", "chest"):
            args["天赋状态"] = "{{#if:" + parameter("talent_mode") + "|{{{talent_mode}}}|random_" + rule["talent_pool"] + "}}"
        args["天赋位数"] = "{{#switch:" + parameter("talent_mode") + "|none=0|random_chest|random_backpack|fixed=1|#default=" + args["天赋位数"] + "}}"
        args["天赋说明"] = "{{#switch:" + parameter("talent_mode") + "|random_chest=随机胸甲天赋槽位|random_backpack=随机背包天赋槽位|fixed=固定天赋待选择|none=无天赋槽位|#default=" + talent_text + "}}"
        blocked_modes = '|'.join('random_' + pool for pool in ('chest', 'backpack') if pool != slot)
        cards[slot] = ("{{#switch:" + parameter('talent_mode') + '|' + blocked_modes
                       + '=<strong class="td2-data-error">随机天赋类型与装备部位不符。</strong>|#default='
                       + "{{品牌装备属性" + "".join("|" + k + "=" + v for k, v in args.items()) + "}}}}")
        dismantle[slot] = dismantle_source(base, ui, slot)
    dismantle['scope'] = base.get('dismantle_profile', {}).get('display', '')
    cards["expertise"] = _expertise_card(base, wiki=True)
    cards["armor"] = "{{#switch:" + parameter("部位") + "|" + "|".join(slot + "=" + _armor_display(rule["base_armor"]) for slot, rule in base["部位"].items()) + "|#default=待核实}}"
    names = dict((brand_catalog or {}).get('entity_images', {}))
    convention = '{{#switch:' + parameter('品牌') + ''.join('|'+k+'='+v for k,v in sorted(names.items())) + '|#default=}}'
    label = '{{#switch:' + parameter('品牌') + ''.join('|'+k+'='+v for k,v in sorted((brand_catalog or {}).get('entity_names', {}).items())) + '|#default=}}'
    guard = convention
    brand_image = "{{#if:" + guard + "|[[File:" + convention + "|240x240px|alt=" + label + "]]}}"
    # Optional icon use reuses the existing frozen brand resolver; standalone logo remains 240px.
    icon_image = "{{#if:" + guard + "|[[File:" + convention + "|24x24px|link=" + parameter("链接") + "|alt=]]}}"
    card_image = '{{TD2Logo显示|文件=' + convention + '|名称=' + parameter('名称') + '}}'
    brand_image = "{{#switch:" + parameter("用途") + "|icon=" + icon_image + "|card=" + card_image + "|#default=" + brand_image + "}}"
    guard = convention
    slot_images = {}
    for slot, key in SLOT_VISUAL_KEYS.items():
        filename = ui.get("slot_visuals", {}).get(key, {}).get("wiki_file", "")
        slot_images[slot] = '<span class="td2-slot-image">[[File:' + filename + '|128x128px|link=|alt=' + SLOT_LABELS[slot] + ']]</span>' if filename else ""
    logo = "{{#if:" + guard + '|<span class="td2-logo-image">[[File:' + convention + '|80x80px|link=|alt=' + label + ']]</span>}}'
    slot_switch = "{{#switch:" + parameter("部位") + "".join("|" + k + "=" + v for k,v in slot_images.items()) + "|#default=}}"
    composed = '<span class="td2-equipment-visual">' + slot_switch + logo + '</span>'
    major = {c: '<span class="td2-major-option">' + call('state', c) + ('<span class="td2-text-orange">' + base['major_display_values'][c] + '</span> ' if base.get('major_display_values') else '') + name + '</span>' for c,name in ui["major_names"].items()}
    visual_note = '组合视觉通过实体 ID 和 Registry 解析；部位图来自 equipment-ui.json。'
    brand_note = '品牌参数是稳定实体 ID，Registry 是唯一地址源。未知身份不显示图片。'
    sources = {
        GENERATED["equipment-visual"]: HEADER + "<noinclude>" + visual_note + "</noinclude><includeonly>" + composed + "</includeonly>",
        GENERATED["equipment-major-display"]: switch_template(major, "待核实"),
        GENERATED["equipment-base-rules"]: switch_template(cards, "部位未填写／待核实"),
        GENERATED["equipment-dismantle"]: switch_template(dismantle, "分解规则待核实"),
        GENERATED["equipment-major-name"]: switch_template(ui["major_names"], "待核实"),
        GENERATED["equipment-row-icon"]: switch_template({k: call('equipment_row', k) for k in ROW_KEYS}, call('equipment_row', 'unknown')),
        GENERATED["brand-auto-image"]: "<noinclude>" + HEADER + brand_note + "</noinclude><includeonly>" + brand_image + "</includeonly>",
    }
    if gear_sets:
        from pathlib import Path
        from tools.publish.bundle import read_json
        shared = read_json(Path(__file__).resolve().parents[2] / 'data/gear-sets/dismantle-rules.json')
        gear_rules = {}
        for item in gear_sets:
            gear_base = gear_dismantle_base(item, shared)
            values = {slot: dismantle_source(gear_base, ui, slot) for slot in gear_base['部位']}
            values.update(scope=shared['dismantle_profile']['display'], known='1')
            gear_rules[item['id']] = '{{#switch:' + parameter('1') + ''.join('|'+key+'='+value for key, value in values.items()) + '|#default=分解规则待核实}}'
        selector = '{{#switch:' + parameter('装备组') + ''.join('|'+key+'='+value for key, value in gear_rules.items()) + '|#default=}}'
        source = sources[GENERATED['equipment-dismantle']]
        start = source.index('<includeonly>') + len('<includeonly>')
        sources[GENERATED['equipment-dismantle']] = source[:start] + '{{#if:' + parameter('装备组') + '|' + selector + '|' + source[start:].replace('</includeonly>', '}}</includeonly>')
    if include_resolver:
        sources[GENERATED['icon-resolver']] = resolver_source(mappings(ui, core=core_icons, gear_sets=gear_sets))
    return sources
