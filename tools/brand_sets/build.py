from tools.identity import read_json
"""从唯一 Catalog 生成 Wiki 适配文件；不写人工页面或冻结审核包。"""

import argparse
from pathlib import Path

from tools.publish.bundle import require, safe_path
from tools.equipment_attributes.catalog import load as load_ordinary
from .minor import load_catalog as load_minor
from .model import CATEGORIES, UNITS, SPECIAL_LABEL, display_label, load_catalog
from .knowledge import EQUIPMENT_SLOTS, load_knowledge
from .icons import weapon_talent_icons

GENERATOR = "tools/brand_sets/build.py@v1"
GENERATED = {
    "minor-attribute-name": "wiki/templates/TD2次属性名称.wiki",
    "brand-attribute-name": "wiki/templates/TD2词条名称.wiki",
    "brand-attribute-category": "wiki/templates/TD2词条分类.wiki",
    "brand-unit-name": "wiki/templates/TD2单位名称.wiki",
    "brand-category-icon": "wiki/templates/TD2分类图标.wiki",
    "brand-talent-data": "wiki/templates/TD2天赋资料.wiki",
    "brand-core-color": "wiki/templates/TD2核心颜色.wiki",
    "brand-core-icon": "wiki/templates/TD2原生核心图标.wiki",
    'equipment-base-rules': 'wiki/templates/TD2普通装备规则.wiki',
    'equipment-dismantle': 'wiki/templates/TD2分解规则.wiki',
    'equipment-major-name': 'wiki/templates/TD2主属性名称.wiki',
    'equipment-row-icon': 'wiki/templates/TD2装备行图标.wiki',
    'brand-auto-image': 'wiki/templates/TD2品牌图片.wiki',
    'equipment-visual': 'wiki/templates/TD2装备视觉.wiki',
    'equipment-major-display': 'wiki/templates/TD2主属性显示.wiki',
    'fixed-attribute-icon': 'wiki/templates/TD2固定词条图标.wiki',
    'fixed-attribute-part': 'wiki/templates/TD2固定词条片段.wiki',
    'attribute-unit': 'wiki/templates/TD2词条单位.wiki',
    'gear-slot-name': 'wiki/templates/TD2装备部位名称.wiki',
    'random-crafting-data': 'wiki/modules/TD2随机品牌制作数据.lua',
    'icon-resolver': 'wiki/templates/TD2图标.wiki',
    'brand-logo-display': 'wiki/templates/TD2Logo显示.wiki',
    'material-row': 'wiki/templates/TD2材料行.wiki',
}
HEADER = "<!-- AUTO-GENERATED — DO NOT EDIT DIRECTLY。自动生成，禁止手改。维护 data/brand-sets/ 中的配置后运行 python -m tools.brand_sets generate。 -->\n"


def switch_template(values, unknown_label):
    cases = "\n".join(f"|{key}={value}" for key, value in values.items())
    # 注释换行也放在 noinclude 内，避免名称/单位映射返回多余换行。
    return "<noinclude>" + HEADER + "这是集中配置的派生映射，不是人工维护入口；维护入口见 docs/equipment-maintenance.md。</noinclude><includeonly>{{#switch:{{{1|}}}\n" + cases + "\n|#default=" + unknown_label + "\n}}</includeonly>"


def attribute_name_template(values, unknown_label):
    source = switch_template(values, unknown_label)
    return source.replace('<includeonly>', '<includeonly>{{#invoke:TD2资料记录|attributeName|id={{{1|}}}|name=', 1).replace('</includeonly>', '}}</includeonly>')


def derived_sources(catalog, icons, knowledge=None, equipment=None, minor_catalog=None, presets=None, brand_catalog=None, random_crafting=None, gear_sets=(), exotic_talents=(), ordinary=None, weapon_icons=None):
    from .minor import EMPTY, by_id
    minor_catalog = minor_catalog if minor_catalog is not None else EMPTY
    by_id(minor_catalog)
    from .fixed_minor import search_records, display_value, EMPTY as PRESETS_EMPTY
    preset_rows = search_records(presets if presets is not None else PRESETS_EMPTY, minor_catalog, ordinary)
    from tools.equipment_attributes.catalog import exotic_rows
    preset_rows += exotic_rows(minor_catalog, ordinary or {'rules': []})
    fixed_parts = {}
    for row in preset_rows:
        name = '{{TD2次属性名称|' + row['minor_attribute_id'] + '}}'
        if row['id'].startswith('fixed_minor_'):
            name = '<span class="td2-text-gold">' + name + '</span>'
        fixed_parts[row['id']] = ('<span class="td2-text-orange">' + display_value(row['value'], row['unit']) + UNITS[row['unit']] + '</span> ' if row['value'] else '') + name
    from .slots import SLOT_LABELS
    import json
    names = {a["id"]: display_label(a) for a in catalog["attributes"]}
    names["special"] = SPECIAL_LABEL
    categories = {a["id"]: a["category"] for a in catalog["attributes"]}
    from .icons import call, mappings, resolver_source, material_row_source
    if equipment and gear_sets:
        base, ui = equipment
        material_display = dict(ui.get('material_display', {}))
        for item in gear_sets:
            if item.get('material'):
                material = item['material']
                key='currency:'+material['currency_uid'].lower()
                require(key not in material_display, 'GEAR_SET_MATERIAL_COLLISION')
                material_display[key] = {**material['display'], 'name': material['name']}
        equipment = (base, {**ui, 'material_display': material_display})
    icon_entries = mappings(equipment[1] if equipment else None, icons, knowledge[2] if knowledge else None, knowledge[1] if knowledge else None, gear_sets=gear_sets)
    icon_entries.update({'talent/' + key: icon for key, icon in (weapon_icons or {}).items()})
    for talent in exotic_talents:
        if talent.get('icon'):
            key = 'talent/' + talent['id']
            require(key not in icon_entries, 'EXOTIC_TALENT_ICON_COLLISION')
            icon_entries[key] = talent['icon']
    icon_values = {key: call('attribute_category', key) for key in CATEGORIES}
    sources = {
        GENERATED['material-row']: material_row_source(equipment[1] if equipment else {}),
        GENERATED["minor-attribute-name"]: attribute_name_template({a["id"]: display_label(a) for a in minor_catalog["attributes"]}, "未收录次属性"),
        GENERATED["brand-attribute-name"]: attribute_name_template(names, "未收录词条（请维护 Catalog）"),
        GENERATED["brand-attribute-category"]: switch_template(categories, ""),
        GENERATED["brand-unit-name"]: switch_template(UNITS, "单位未填写"),
        GENERATED["brand-category-icon"]: switch_template(icon_values, ""),
        GENERATED["fixed-attribute-icon"]: switch_template({a["id"]: call('attribute_category', a["category"]) for a in preset_rows}, ""),
        GENERATED["fixed-attribute-part"]: switch_template(fixed_parts, '<strong class="td2-data-error">未知固定词条预设</strong>'),
        GENERATED["attribute-unit"]: switch_template({a["id"]: UNITS[a["unit_type"]] for a in catalog["attributes"]}, ""),
        GENERATED["gear-slot-name"]: switch_template(SLOT_LABELS, "部位未填写"),
        GENERATED['icon-resolver']: resolver_source(icon_entries),
    }
    from .logos import source as logo_source
    from .random_crafting import lua_source
    sources[GENERATED['random-crafting-data']] = lua_source(random_crafting or {'schema_version': 1, 'brands': {}, 'recipes': []})
    sources[GENERATED['brand-logo-display']] = logo_source()
    from .projection import knowledge_sources
    sources.update(knowledge_sources())
    if equipment is not None:
        from .equipment_projection import equipment_sources
        sources.update(equipment_sources(*equipment, core_icons=knowledge[2] if knowledge else None, include_resolver=False, brand_catalog=brand_catalog, gear_sets=gear_sets))
    return sources


def generate(root, check=False):
    from .brands import load_catalog as load_brands
    brands = load_brands(root)
    catalog, icons = load_catalog(root)
    from .minor import load_catalog as load_minor
    from .equipment import load_equipment
    from .fixed_minor import load_catalog as load_presets
    from .random_crafting import load as load_random_crafting
    sources = derived_sources(catalog, icons, load_knowledge(root, catalog), load_equipment(root), load_minor(root), load_presets(root, load_minor(root)), brand_catalog=brands, random_crafting=load_random_crafting(root), gear_sets=read_json(root / 'data/gear-sets/sets.json')['sets'], exotic_talents=read_json(root / 'data/exotic-gear/talents.json')['talents'], ordinary=load_ordinary(root), weapon_icons=weapon_talent_icons(root))
    registry = read_json(root / "publishing/registry.json")
    owned = {r["source"]: r for r in registry["entries"] if r["ownership"] == "generated" and r.get("generator") == GENERATOR}
    # 先检查全部所有权再写任何文件；不靠目录范围猜测所有权。
    require(set(sources) == set(owned), "生成文件与 registry 所有权不一致")
    for entry_id, relative in GENERATED.items():
        matches = [r for r in registry["entries"] if r["source"] == relative]
        require(len(matches) == 1 and matches[0]["id"] == entry_id, "生成文件存在重复来源映射或 id 不一致")
    from .navbox import SOURCE as NAVBOX_SOURCE, GENERATOR as NAVBOX_GENERATOR, source as navbox_source
    from tools.generation import plan, apply
    sources[NAVBOX_SOURCE] = navbox_source(root)
    owners = {relative: GENERATOR for relative in sources}
    owners[NAVBOX_SOURCE] = NAVBOX_GENERATOR
    return apply(plan(root, sources, registry, owners), check)


def main():
    parser=argparse.ArgumentParser(description="Generate shared equipment catalogs")
    parser.add_argument('command',choices=['generate','check'])
    parser.add_argument('--root',type=Path,default=Path.cwd())
    args=parser.parse_args()
    changed=generate(args.root.resolve(),check=args.command=='check')
    print(f'Shared catalogs checked; {len(changed)} generated files changed')
