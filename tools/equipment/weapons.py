"""Weapon templates/navigation; content remains owned by the equipment importer."""
import argparse,json
from .weapon_chart_study import SIGNATURE_CHART_UIDS, SIGNATURE_RECOIL_UID
from .weapons_native import ROOT,GROUPS
from tools.identity import read_json,raw_json,asset
from tools.brand_sets.navbox import markup
from tools.brand_sets.icons import weapon_talent_icons
from tools.generation import plan,apply

AMMO_ICONS={'AssaultRifle':'ammo_ar','Rifle':'ammo_rifle','SniperRifle':'ammo_marksman',
            'SubMachinegun':'ammo_smg','LightMachinegun':'ammo_lmg','Shotgun':'ammo_shotgun','Pistol':'ammo_pistol'}

PAGE_PREFIX = {'normal': '顶级武器', 'named': '具名武器', 'exotic': '奇特武器', 'signature': GROUPS['SignatureWeapon']}


def model_title(model):
    return PAGE_PREFIX[model['kind']] + '-' + model['装备名称']


def named_entry_id(model):
    return 'weapon-named-' + model['装备UID'].lower()


def check_title(title, model):
    expected = model_title(model)
    if title == expected:
        return
    if title.startswith(expected + '（') and title.endswith('）'):
        qualifier = title[len(expected) + 1:-1]
        if qualifier and qualifier == qualifier.strip() and '（' not in qualifier and '）' not in qualifier:
            return
    raise ValueError(f'Weapon page title {title!r} does not match {expected!r}')


def named_redirects(entities, registry):
    owned = {row['id']: row for row in registry['entries']
             if row['kind'] == 'redirects' and row.get('generator') == 'tools/equipment/weapons.py@v1'}
    outputs = {}
    seen = set()
    for entity_id, entity in entities.items():
        if entity['template'] != '武器信息':
            continue
        models = [record['data'] for record in entity['collections']['武器型号资料']['rows']]
        base, = (model for model in models if model['kind'] != 'named')
        parent = entity['page_title']
        check_title(parent, base)
        fragments = set()
        for model in models:
            if model['kind'] != 'named':
                continue
            key = named_entry_id(model)
            entry = owned.get(key)
            if key in seen or not entry or entry.get('related_entity') != entity_id or model['base_uid'].lower() != base['装备UID'].lower():
                raise ValueError('Named weapon does not have a unique registered parent and entrance: ' + key)
            seen.add(key)
            check_title(entry['title'], model)
            name = model['装备名称']
            fragment = '_'.join(name.replace('_', ' ').split())
            if fragment in fragments:
                raise ValueError(f'Duplicate named weapon anchor: {parent}#{name}')
            fragments.add(fragment)
            outputs[entry['source']] = '#REDIRECT [[' + parent + '#' + name + ']]\n'
    if seen != owned.keys():
        raise ValueError('Registered named weapon entrance has no model: ' + ', '.join(sorted(owned.keys() - seen)))
    return outputs

def navigation():
    sections={'normal':[],'named':[],'exotics':[],'signature':[]}
    ammo=read_json(ROOT/'data/brand-sets/equipment-ui.json')['weapon_icons']
    talents=weapon_talent_icons(ROOT)
    for entity in read_json(ROOT/'data/equipment/records.json')['entities'].values():
        if entity['template']!='武器信息':continue
        for record in entity['collections']['武器型号资料']['rows']:
            r=record['data']
            kind=r['kind']
            row={'name':r['装备名称'],'target':entity['page_title'],'slot':r['group'],'icon':''}
            if r.get('asset_ref'):
                row['icon']=asset(r['asset_ref'])['title'].split(':',1)[1]
            if kind=='named':
                row['target']+='#'+row['name']
            if kind in ('named','exotic'):
                row['slot_icon']=ammo[AMMO_ICONS[r['group']]]['wiki_file']
                for effect in entity['effects']:
                    if effect['所属装备']!=r['stable_id'] or effect['模式']!='PvE':continue
                    uid=effect['效果ID'].removeprefix(r['stable_id']+'_')
                    icon=talents.get(effect['图标'] or 'weapon_talent_'+uid)
                    if icon:
                        row.update(slot_icon=icon['wiki_file'],talent_watermark=True)
                        break
            sections['exotics' if kind=='exotic' else kind].append(row)
    labels=(('normal','{{{普通武器标题|普通武器}}}'),('named','具名武器'),('exotics','奇特武器'),('signature',PAGE_PREFIX['signature']))
    body=markup(sections,section_labels=labels,group_labels=GROUPS,group_order=list(GROUPS),label='武器导航',grouped=('normal','named','exotics'),image_size='64x32px')
    return body.replace('class="td2-navbox"','class="td2-navbox td2-weapon-navbox" data-anchor-current="true"',1)

def chart_modules():
    source = raw_json(ROOT/'data/equipment/weapon-charts.json')
    image = asset(source['target']['asset_ref'])['title'].split(':', 1)[1]
    def quoted(value):
        return json.dumps(value, ensure_ascii=False)
    def payload(value):
        return quoted(json.dumps(value, separators=(',', ':'), allow_nan=False))
    outputs = {}
    for group in GROUPS:
        models = []
        traces = set()
        for uid, record in source['models'].items():
            if record['group'] != group:
                continue
            if group == 'SignatureWeapon' and uid not in SIGNATURE_CHART_UIDS:
                raise ValueError('Unsupported signature weapon in chart catalog: ' + uid)
            fields = []
            if 'angles' in record:
                fields.append('angles=' + payload(record['angles']))
            if 'trace' in record:
                if group == 'SignatureWeapon' and uid != SIGNATURE_RECOIL_UID:
                    raise ValueError('Unsupported signature recoil in chart catalog: ' + uid)
                traces.add(record['trace'])
                fields.append('trace=' + quoted(record['trace']))
            models.append('[' + quoted(uid) + ']={' + ','.join(fields) + '},')
        series = ['[' + quoted(key) + ']=' + payload(source['traces'][key]) + ',' for key in sorted(traces)]
        lines = ['return {', 'image=' + quoted(image) + ',', 'target=' + payload(source['target']) + ',']
        if group == 'SignatureWeapon':
            allowed = ','.join('[' + quoted(uid) + ']=true' for uid in sorted(SIGNATURE_CHART_UIDS))
            lines.append('signatureChartUids={' + allowed + '},')
            lines.append('signatureRecoilUid=' + quoted(SIGNATURE_RECOIL_UID) + ',')
        lines.extend(['models={', *models, '},', 'traces={', *series, '}}'])
        outputs['wiki/modules/TD2武器图表/' + group + '.lua'] = '\n'.join(lines) + '\n'
    return outputs

def generate(check=False):
    outputs={'wiki/templates/武器信息.wiki':'<noinclude>武器 Reader，使用共享装备资料与人工注释。</noinclude><includeonly>{{#invoke:TD2武器|render}}</includeonly>\n',
             'wiki/templates/TD2武器导航.wiki':'<noinclude>由装备资料与 Registry 生成。</noinclude><includeonly>'+navigation()+'</includeonly>\n'}
    outputs.update(chart_modules())
    registry=json.loads((ROOT/'publishing/registry.json').read_text('utf8'))
    entities=read_json(ROOT/'data/equipment/records.json')['entities']
    outputs.update(named_redirects(entities,registry))
    batch=plan(ROOT,outputs,registry,{key:'tools/equipment/weapons.py@v1' for key in outputs})
    if check:
        stale=[relative for relative,_,_,changed in batch if changed]
        if stale:raise ValueError('Stale generated weapon sources: '+', '.join(stale))
    else:
        apply(batch)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['generate','check']);a=p.parse_args();generate(a.command=='check')
