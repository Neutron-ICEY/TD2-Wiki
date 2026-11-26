"""Public identities and the explicitly closed constant attribute rules."""
import json
import re
from decimal import Decimal
from . import native_tree as tree
from .rules import EquipmentRules
from .crafting import links, scalar
from tools.brand_sets.native_structure import contexts

CATALOG = 'data/equipment/attributes.json'


def constant_value(curve, quality, bonus_type, after_power=None):
    rows = curve['brackets']
    if after_power is not None:
        # The verified level 31+ interval starts after this native boundary. No
        # endpoint Power is assumed: every subsequent bracket must be identical.
        positions = [i for i, r in enumerate(rows) if r['max_power'] == after_power]
        if len(positions) != 1: raise ValueError('Attribute bracket boundary changed')
        rows = rows[positions[0]+1:]
    if not rows or rows[-1]['max_power'] != -1: raise ValueError('Incomplete constant curve')
    if any(Decimal(r['a']) or Decimal(r['b']) for r in rows): raise ValueError('Attribute depends on unresolved Power')
    values = {Decimal(r['c']) for r in rows}
    if len(values) != 1: raise ValueError('Attribute bracket values differ')
    value = values.pop() * Decimal(curve['qualities'].get(quality, '1'))
    if bonus_type == 'Percentage': value *= 100
    elif bonus_type != 'FlatValue': raise ValueError('Unknown attribute unit')
    return format(value, 'f').rstrip('0').rstrip('.') if '.' in format(value, 'f') else str(value)


def project(crafting):
    catalog = json.loads((crafting.root / CATALOG).read_text('utf8'))
    native = crafting.native
    for identity, row in catalog.get('identities', {}).items():
        try:
            nodes = [n for n in tree.walk(crafting.document(row['native_source'])) if re.search(r'uid='+row['native_uid']+r'\s*>', n['header'])]
            if len(nodes)!=1: raise ValueError('Attribute identity missing or ambiguous')
            name = tree.prop(nodes[0], 'myUIName')
            definition = native.attribute(row['native_uid'])
            kind = definition.get('myBonusType', 'FlatValue')
            if kind not in ('Percentage', 'FlatValue'): raise ValueError('Unknown attribute bonus type')
            values = {'zh_name':crafting.text(name), 'en_name':crafting.text(name, 'en'),
                      'unit_type':'percent' if kind == 'Percentage' else 'number',
                      'native_format':{k:definition.get(k, default) for k,default in
                          [('myBonusType','FlatValue'),('myUnit','Value'),('myUINumDecimals','0'),('myRoundMode','None')]}}
            for key, value in values.items(): crafting.unit(['identities', identity, key], value, file=CATALOG)
        except (OSError, ValueError, KeyError) as error: crafting.missing('attribute:'+identity, error)
    profile = catalog.get('native_profile')
    if not profile: return
    rules = EquipmentRules(native)
    for binding in profile['constant_rules']:
        try:
            identity = catalog['identities'][binding['attribute_id']]
            doc = crafting.document(profile['attribute_list'])
            containers = [n for n in tree.walk(doc) if re.search(r'uid='+binding['pool_uid']+r'\s*>', n['header'])]
            if len(containers) != 1: raise ValueError('Attribute pool missing or ambiguous')
            matches = [n for n in tree.walk(containers[0]) if n['header'].startswith('AttributeData ') and tree.prop(n,'myAttribute')==identity['native_uid']]
            if len(matches) != 1: raise ValueError('Attribute definition missing or ambiguous')
            definition = matches[0]
            curve = tree.child(definition, 'myRangeMax')
            if curve is None:
                ref = tree.prop(definition, 'myRangeMax', '')
                name = ref[2:].rsplit(' ',1)[0] if ref.startswith('= ') else ''
                candidates = [n for n in doc['children'] if n['header'].split(' ',1)[-1].split(' <')[0].split(' : ')[0].strip('"')==name]
                if len(candidates) != 1: raise ValueError('Attribute curve unavailable')
                curve = candidates[0]
            data = {'brackets':[{'max_power':int(tree.prop(n,'myMaxPower','-1')),
                    **{k.lower():tree.prop(n,'my'+k,'0') for k in ('A','B','C')}} for n in curve['children']],
                    'qualities':{tree.prop(n,'myQuality','Grey'):tree.prop(n,'myModifier','1') for n in (tree.child(definition,'myQualityModifiers') or {'children':[]})['children']}}
            presets = []
            for item in binding.get('items', []):
                rules.index()
                record = native.record(item['source'], item['uid'])
                if scalar(native,record,'myQuality')!=binding['quality']:raise ValueError('Fixed item quality changed')
                references = links(native, record, 'myItemGenerationConfig')
                configs = rules.configs.get(references[0]['target_uid'], []) if len(references)==1 else []
                if len(configs)!=1: raise ValueError('Fixed attribute config unavailable')
                def extract(row, refs):
                    groups = [c for c in contexts(row, refs, 'QualityAttributeSlots') if any(p['field']=='myQuality' and p['raw_value']==binding['quality'] and p['context']==c for p in row['properties'])]
                    if not groups: return None
                    if len(groups)!=1: raise ValueError('Ambiguous fixed attribute quality')
                    found=[]
                    for context in contexts(row,refs,'ItemAttributeSlot'):
                        if context[:len(groups[0])]!=groups[0]: continue
                        props={p['field']:p['raw_value'] for p in row['properties'] if p['context']==context}
                        if props.get('myPresetAttribute')!=identity['native_uid']: continue
                        pools=sorted({l['target_uid'] for l in refs if l['field']=='AttributeListContainer' and l['context'][:len(context)]==context})
                        found.append({'percentile':props.get('myPresetPercentage','-1'),'pools':pools})
                    return found
                found,_ = rules.reader.resolve(*configs[0], extract)
                if len(found)!=1 or Decimal(found[0]['percentile'])!=100 or found[0]['pools']!=[binding['pool_uid']]:
                    raise ValueError('Fixed percentile or pool changed; calculation requires review')
                presets.append(found[0])
            kind=native.attribute(identity['native_uid']).get('myBonusType','FlatValue')
            qualities=[binding['quality']] if binding.get('items') else ['Orange','Exotic','GearSet']
            values={constant_value(data, quality, kind, binding.get('after_power')) for quality in qualities}
            if len(values)!=1:raise ValueError('Shared attribute qualities disagree')
            brackets=data['brackets']
            if 'after_power' in binding:brackets=brackets[next(i for i,r in enumerate(brackets) if r['max_power']==binding['after_power'])+1:]
            effective={'brackets':brackets,'qualities':{q:data['qualities'].get(q,'1') for q in qualities}}
            crafting.unit(binding['path'], values.pop(), {'uid':identity['native_uid'],'curve':effective,'unit':kind,'presets':presets}, file=binding['file'])
        except (OSError, ValueError, KeyError, IndexError) as error: crafting.missing('attribute-rule:'+binding['id'], error)
