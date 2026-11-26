"""Read and exercise the current Wiki contract without changing its configuration."""
import importlib.util
import json

from tools.brand_sets.icons import mappings
from .static_formats import safe_relative, sha256


def read(root, path):
    return __import__('tools.identity',fromlist=['read_json']).read_json(root/path)


def subset(root):
    spec = importlib.util.spec_from_file_location('asset_import_wiki_subset', root / 'tests/wiki_subset.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.WikiSubset


def detect_contract(root):
    from tools.brand_sets.brands import load_catalog as load_brands
    brands = load_brands(root)
    ui = read(root, 'data/brand-sets/equipment-ui.json')
    core = read(root, 'data/brand-sets/core-icons.json')
    categories = read(root, 'data/brand-sets/category-icons.json')
    talents = read(root, 'data/brand-sets/talents.json')
    entries = mappings(ui, categories, core, talents)
    wiki = subset(root)(root)
    examples = []
    for category, key, lookup_category in (('material', 'brand_material', 'material'), ('attribute/state', 'red', 'state'),
            ('attribute/state', 'offense', 'attribute_category'), ('equipment row type', 'major_attribute', 'equipment_row'),
            ('mod', 'mod_slot', 'equipment_row'), ('attribute/state', 'red', 'core_major')):
        icon_key = lookup_category + '/' + key
        filename = entries[icon_key]['wiki_file']
        examples.append(dict(category=category, stable_id=key, icon_key=icon_key, normalized_filename=filename or None,
            intended_wiki_filename=filename or None, lookup='{{TD2图标|类别=' + lookup_category + '|键=' + key + '}}',
            lookup_result=wiki.template('TD2图标', {'类别': lookup_category, '键': key}),
            gate='PASS' if filename else 'MISSING_MAPPING_ENTRY',
            source='tools/brand_sets/icons.py::mappings + data/brand-sets/*-icons.json / equipment-ui.json'))
    slot = 'mask'; filename = ui['slot_visuals'][slot]['wiki_file']
    examples.append(dict(category='gear_slot', stable_id=slot, icon_key='slot_visuals/' + slot,
        normalized_filename=filename or None, intended_wiki_filename=filename or None,
        lookup='{{TD2装备视觉|部位=mask}}', lookup_result=wiki.template('TD2装备视觉', {'部位': slot}),
        gate='PASS' if filename else 'MISSING_MAPPING_ENTRY', source='tools/brand_sets/equipment_projection.py::equipment_sources'))
    for category in ('talent', 'gear_set'):
        examples.append(dict(category=category, stable_id=None, icon_key=None, normalized_filename=None,
            intended_wiki_filename=None, lookup='{{TD2图标|类别=' + category + '|键=}}',
            lookup_result=wiki.template('TD2图标', {'类别': category, '键': ''}),
            gate='EMPTY_CATALOG' if category == 'talent' else 'UNSUPPORTED_CATEGORY',
            source='data/brand-sets/talents.json' if category == 'talent' else 'tools/brand_sets/icons.py::mappings'))
    fixture = read(root, 'tests/fixtures/phase16-pf55-final.json')
    name = brands['brands'][0]['zh_name'] if brands['brands'] else fixture['brand']['套装全称']
    filename = brands['brands'][0]['wiki_filename'] if brands['brands'] else ''
    present = subset(root)(root, existing_files=('File:' + filename,))
    result = present.template('TD2品牌图片', {'品牌': brands['brands'][0]['entity_ref'] if brands['brands'] else name})
    examples.append(dict(category='brand', stable_id=brands['brands'][0]['entity_key'] if brands['brands'] else None,
        icon_key='TD2品牌图片|品牌=' + brands['brands'][0]['entity_ref'] if brands['brands'] else None, normalized_filename=filename,
        intended_wiki_filename=filename, lookup='{{TD2品牌图片|品牌=' + (brands['brands'][0]['entity_ref'] if brands['brands'] else '') + '}}', lookup_result=result,
        gate='PASS_REGISTERED_BRAND_MAPPING' if brands['brands'] else 'CLOSED_NO_REAL_BRAND_CATALOG_FOR_FIXTURE',
        source='data/brand-sets/brands.json::entity_ref + asset_ref → publishing/registry.json',
        notes='Registry address resolved by stable entity and Asset IDs. Publication remains independently verified.'))
    sources = ['tools/brand_sets/icons.py', 'tools/brand_sets/equipment.py', 'tools/brand_sets/equipment_projection.py',
               'wiki/templates/TD2图标.wiki', 'wiki/templates/TD2品牌图片.wiki', 'wiki/templates/TD2装备视觉.wiki',
               'data/brand-sets/equipment-ui.json', 'data/brand-sets/core-icons.json', 'data/brand-sets/category-icons.json',
               'data/brand-sets/talents.json', 'data/brand-sets/bonuses.json', 'tools/brand_sets/slots.py', 'publishing/registry.json']
    if (root / 'data/brand-sets/brands.json').is_file():
        sources.append('data/brand-sets/brands.json')
    conflicts = []
    for icon_key, entry in entries.items():
        filename = entry['wiki_file']
        if filename:
            category, key = icon_key.split('/', 1)
            actual = subset(root)(root, existing_files=('File:' + filename,)).template('TD2图标', {'类别': category, '键': key})
            if '[[File:' + filename + '|' not in actual:
                conflicts.append(dict(code='NAMING_CONTRACT_CONFLICT', icon_key=icon_key, filename=filename,
                                      reason='Current configuration and current resolver disagree.'))
    confirmed = [k for k, e in entries.items() if e['wiki_file'] and e.get('confirmed_on_wiki')]
    return dict(schema_version=1, examples=examples, small_icon_entries=entries,
        brand_catalog_count=len(brands['brands']),
        brand_contract='TD2品牌图片|品牌=<stable entity ID>',
        naming_contract_conflicts=conflicts, automatic_normalization_gate=('PARTIAL_EXPLICIT_RESOLVER_MAPPINGS'
            if entries and not conflicts else 'CLOSED_NO_RESOLVABLE_REAL_ENTITY_FILENAME'),
        confirmed_icon_keys=confirmed,
        sources={p: sha256((root / p).read_bytes()) for p in sources},
        explanation='Catalog 保存稳定实体和 asset_ref；Registry 唯一维护当前地址。解析器兼容性与远端发布状态分开。名称仅产生审核候选，不能批准身份关联。')


def compatible_filename(root, category, stable_id, filename, contract, resolver_sources=None):
    path = safe_relative(filename)
    if len(path.parts) != 1:
        return False
    entry = contract['small_icon_entries'].get(category + '/' + stable_id)
    if not entry or entry['wiki_file'] != filename or not (entry.get('local_available') or entry.get('confirmed_on_wiki')):
        return False
    rendered = subset(root)(root, existing_files=('File:' + filename,), sources=resolver_sources).template('TD2图标', {'类别': category, '键': stable_id})
    return '[[File:' + filename + '|' in rendered and 'td2-icon-placeholder' not in rendered


def compatible_brand_filename(root, entity_key, filename, resolver_sources=None):
    from tools.brand_sets.brands import by_key, load_catalog
    item = by_key(load_catalog(root)).get(entity_key)
    if not item or filename != item['wiki_filename']:
        return False
    rendered = subset(root)(root, existing_files=('File:' + filename,), sources=resolver_sources).template(
        'TD2品牌图片', {'品牌': item['entity_ref']})
    return '[[File:' + filename + '|' in rendered


def match_wiki(root, binding):
    category = binding['category']
    # Application Attribute is shared by Main/Minor/Mod/Bonus. A localized name
    # alone cannot establish its Wiki domain; Main uses explicit reconciliation.
    if category == 'attribute':
        return dict(stable_id=None, icon_key=None, unique=False,
                    method='unscoped_attribute_requires_domain_reconciliation',
                    notes='应用 Attribute 必须先核实 Main/Minor/Mod/Bonus 领域，不能只按名称加入 Bonus Catalog。')
    catalog = read(root, 'data/brand-sets/talents.json')['talents'] if category == 'talent' else []
    matches = []
    for row in catalog:
        zh = binding['chinese_name']; en = binding.get('english_name')
        if (zh and row.get('zh_name') == zh) or (en and row.get('en_name', '').casefold() == en.casefold()):
            matches.append(row)
    # Application-local keys and game-native UIDs are different identities. A
    # unique localized name is useful evidence for review, never a binding.
    return dict(stable_id=None, icon_key=None, unique=False,
                method='localized_name_candidates_require_identity_evidence' if matches else 'no_catalog_entry',
                candidate_ids=[row['id'] for row in matches],
                notes='名称仅用于审核候选；须核实原生/应用来源身份后登记关联。' if matches else '当前 Wiki 无该实体条目；不创建 stable ID。')
