import html
import json
import re
from pathlib import Path
from .slots import SLOT_LABELS
from tools import identity


def load(root=None):
    root = root or Path(__file__).resolve().parents[2]
    native = json.loads((root / 'data/equipment/crafting.json').read_text('utf-8'))
    records = json.loads((root / 'data/equipment/records.json').read_text('utf-8'))['entities']
    data = {'schema_version':1,'brands':{},'recipes':[]}
    pages = {}
    for row in identity.registry(root):
        if row['kind'] == 'pages' and row.get('related_entity'):
            pages.setdefault(row['related_entity'], []).append(row['title'])
    for uid,blueprint in native['blueprints'].items():
        if not blueprint['random']:continue
        targets=[];slots=set()
        for target in blueprint['targets']:
            item=native['items'][target];entity=records[item['entity_id']];brand=item['brand_uid'];slots.add(item['slot'])
            titles = pages.get(item['entity_id'], [])
            if len(titles) != 1:
                raise ValueError('PAGE_IDENTITY_NOT_UNIQUE: ' + item['entity_id'])
            data['brands'][brand]={'entity_id':item['entity_id'],'name':entity['fields']['套装全称'],'page':titles[0]}
            targets.append({'item_uid':target,'brand_uid':brand})
        if len(slots)!=1:raise ValueError('Random recipe crosses equipment slots')
        data['recipes'].append({'uid':uid,'slot':next(iter(slots)),'name':blueprint['name'],'targets':targets})
    validate(data)
    return data


def validate(data):
    assert data['schema_version'] == 1
    uid = re.compile(r'^[A-F0-9]{32}$')
    brands = data['brands']
    assert len({b['entity_id'] for b in brands.values()}) == len(brands)
    for key, brand in brands.items():
        assert uid.fullmatch(key) and brand['name'] and brand['page']
    seen = set()
    for recipe in data['recipes']:
        assert uid.fullmatch(recipe['uid']) and recipe['uid'] not in seen
        seen.add(recipe['uid'])
        assert recipe['slot'] in SLOT_LABELS and recipe['name'] and recipe['targets']
        targets = set()
        for target in recipe['targets']:
            assert uid.fullmatch(target['item_uid']) and target['item_uid'] not in targets
            targets.add(target['item_uid'])
            assert target['brand_uid'] in brands
    return data


def for_brand(name, kind='', data=None):
    data = data if data is not None else load()
    if kind == 'unbranded':
        return []
    brand_uid = next((uid for uid, b in data['brands'].items() if b.get('entity_id') == name), None)
    return [r for r in data['recipes'] if any(t['brand_uid'] == brand_uid for t in r['targets'])]


def render(name, kind='', slot='', data=None, icon=None):
    if not any(r['slot'] == slot for r in for_brand(name, kind, data)):
        return ''
    filename = html.escape(identity.asset('ui-loadout-circle-icon')['title'].split(':',1)[-1], quote=True)
    return '<ul class="td2-blueprints td2-random-brand-crafting"><li>' + (icon if icon is not None else '<span class="td2-icon"><img data-brand-file="' + filename + '" src="images/' + filename + '" alt=""></span>') + '随机品牌制作</li></ul>'


def lua_source(data):
    validate(data)
    q = lambda s: json.dumps(s, ensure_ascii=False)
    brands = ',\n'.join('[' + q(b['entity_id']) + ']=' + q(uid) for uid, b in data['brands'].items())
    recipes = ',\n'.join('{uid=' + q(r['uid']) + ',slot=' + q(r['slot']) + ',label=' + q(SLOT_LABELS[r['slot']]) + ',name=' + q(r['name']) + ',brands={' + ','.join(q(uid) for uid in dict.fromkeys(t['brand_uid'] for t in r['targets'])) + '}}' for r in data['recipes'])
    return '-- AUTO-GENERATED — DO NOT EDIT DIRECTLY。由 data/equipment/crafting.json 的 UID 图纸关系生成。\nreturn {brands={\n' + brands + '\n},recipes={\n' + recipes + '\n}}\n'
