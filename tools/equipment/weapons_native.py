"""Weapon projection into the shared equipment database, using native identities."""
import argparse
import json
import re
from pathlib import Path

from .native import Native, richtext
from tools.asset_import.text_evidence import native_references, metadata_literal_value

GROUPS = {'AssaultRifle':'突击步枪','Rifle':'步枪','SniperRifle':'射手步枪',
          'SubMachinegun':'冲锋枪','LightMachinegun':'轻机枪','Shotgun':'霰弹枪','Pistol':'手枪',
          'SignatureWeapon':'特有武器'}
ROOT = Path(__file__).resolve().parents[2]
# These reviewed menu references have a usable embedded name when a locale is missing.
EMBEDDED_NAMES = {
    '346395BC5D5BAB8400037EECCE058F36': 'KSG Shotgun',
    '46B416455594E7630003DF9618542A5F': '586 Magnum',
    '843210E16AFEC3D9001980D9B64FA9FA': 'Blizzard',
}

DISABLED_DESCRIPTION = '- THIS STRING IS NOT LOCALIZED YET, PLEASE EDIT AND SAVE THIS FILE!'


class WeaponNative(Native):
    def item_description(self, item):
        owner = self.member(item, 'myDescription')
        if owner is None or self.direct(owner).get('myDescription') == '""':
            return ''
        try:
            return richtext(self.text(item, 'myDescription'))
        except KeyError as error:
            # A missing translation usually protects the existing field on import.
            # The game's explicitly disabled editor placeholder denotes an empty field.
            guid = error.args[0]
            field, = (f for f in owner['fields'] if f['field'] == 'myDescription'
                      and len(f['context']) == 1 and f['guid'] == guid)
            refs = native_references(self.file(owner['_source']).read_bytes())['references']
            ref, = (r for r in refs if r['location']['byte_start'] == field['location']['byte_start'])
            if guid == '843210E16AFEC428001AD4EE75C33024' and ref['enabled'] and ref['embedded_text_literal']:
                return richtext(self.localization('en').get(guid) or metadata_literal_value(ref['embedded_text_literal']))
            if (ref['enabled'] is False and ref['line_version'] == 0 and ref['embedded_text_literal']
                    and metadata_literal_value(ref['embedded_text_literal']).strip() == DISABLED_DESCRIPTION
                    and guid not in self.localization('en')):
                return ''
            raise

    def item_name(self, item, language):
        try:
            name = self.text(item, 'myUIName', language)
        except KeyError as error:
            owner = self.member(item, 'myUIName')
            fields = [f for f in owner['fields'] if f['field']=='myUIName' and len(f['context'])==1] if owner else []
            if len(fields) != 1 or fields[0]['guid'] not in EMBEDDED_NAMES:
                raise ValueError('Weapon name translation unavailable: '+language) from error
            field = fields[0]
            raw = self.file(owner['_source']).read_bytes()
            matches = [ref for ref in native_references(raw)['references']
                       if ref['location']['byte_start']==field['location']['byte_start'] and ref['guid']==field['guid']]
            if len(matches) != 1:
                raise ValueError('Weapon embedded name unavailable') from error
            name = metadata_literal_value(matches[0]['embedded_text_literal'])
            if name != EMBEDDED_NAMES[field['guid']]:
                raise ValueError('Embedded weapon name changed; translation requires review') from error
        label = re.sub(r'</?color\b[^>]*>', '', name).strip()
        if not label:
            raise ValueError('Empty weapon name: '+language)
        return label

    def signature_weapons(self):
        """Only the item granted by each live specialization's signature slot."""
        result={}
        folder='hunter/game system data/juice/playerspecializations'
        for file in sorted(self.file(folder).glob('playerspecialization_*.mplayerspecialization')):
            source=file.relative_to(self.root).as_posix()
            spec=next(r for r in self.document(source)['resources'] if r['resource_type']=='PlayerSpecialization' and not r['parents'])
            elements={r['resource_uid']:r for path in self.includes(source) if path.endswith('.mplayerspecializationelement') for r in self.document(path)['resources'] if not r['parents']}
            for ref in self.collection(spec,'myElementGridByLevels')[2]:
                if ref['field']!='myElement':continue
                element=elements.get(ref['target_uid'])
                if element is None or element['resource_type']!='PlayerSpecializationElementItem':continue
                item=self.linked(element,'myItemType')
                tags={p['raw_value'] for p in self.collection(item,'myTags')[1]}
                if 'Weapon_LiveSignature' not in tags:continue
                uid=item['resource_uid']
                result[uid]={'name':self.text(spec,'myName'),'uid':spec['resource_uid'],'source':source,
                             'element_uid':element['resource_uid'],'element_source':element['_source'],
                             'item_source':item['_source']}
        return result

    def lineage(self, record):
        seen=set()
        while record:
            key=(record['_source'],record['resource_uid'],record['internal_name'])
            if key in seen:raise ValueError('Native inheritance cycle')
            seen.add(key);yield record
            parent=record.get('inheritance_name')
            if not parent:return
            types={'Weapon','myWeapon'} if record['resource_type'] in ('Weapon','myWeapon') else None
            row=self.definition(record['_source'],name=parent,types=types)
            if row is None:raise ValueError('Native parent unavailable: '+parent)
            record=row

    @staticmethod
    def direct(row):
        return {p['field']:p['raw_value'] for p in row['properties'] if len(p['context'])==len(row['parents'])+1}

    def scalar(self, row, field, default=None):
        for r in self.lineage(row):
            props=self.direct(r)
            if field in props:return props[field]
        return default

    def references(self, row, field):
        for r in self.lineage(row):
            doc=self.document(r['_source']);index=doc['resources'].index(r)
            found=[l for l in doc['links'] if l['source_index']==index and l['field']==field
                   and len(l['context'])==len(r['parents'])+1]
            if found:return r,found
            if any(e['field']==field and len(e['context'])==len(r['parents'])+1 for e in r.get('empty_blocks',[])):return r,[]
        return None,[]

    def linked(self, row, field):
        owner,refs=self.references(row,field)
        if len(refs)!=1:raise ValueError('Native reference unavailable: '+field)
        ref=refs[0]
        found=self.definition(owner['_source'],name=ref['target_name'],uid=ref['target_uid'])
        if found is None:raise ValueError('Native reference target unavailable: '+field)
        return found

    def collection(self, row, field):
        for r in self.lineage(row):
            depth=len(r['parents'])+1
            props=[p for p in r['properties'] if len(p['context'])>depth and p['context'][depth]['resource_type']==field]
            doc=self.document(r['_source']);index=doc['resources'].index(r)
            refs=[l for l in doc['links'] if l['source_index']==index and len(l['context'])>depth and l['context'][depth]['resource_type']==field]
            if props or refs or any(e['field']==field and len(e['context'])==depth for e in r.get('empty_blocks',[])):
                return r,props,refs
        return None,[],[]

    def discover(self):
        rows=[];errors=[];excluded=[];signatures=self.signature_weapons()
        unreleased=json.loads((ROOT/'data/equipment/native-map.json').read_text('utf8')).get('unreleased_items',{})
        for ns in ('hunter','rogue'):
            for file in sorted(self.file(ns+'/game system data/juice/item').glob('player_weapon*.mitem')):
                source=file.relative_to(self.root).as_posix()
                if re.search(r'milestone|level\d+boost|_template|_immersion|_testing_asset\.mitem$',file.name,re.I):
                    excluded.append(source);continue
                try:
                    for item in self.document(source)['resources']:
                        if item['resource_type']!='WeaponItem' or item['parents']:continue
                        if item['resource_uid'] in unreleased:
                            excluded.append(source);continue
                        tags=[p['raw_value'] for p in self.collection(item,'myTags')[1]]
                        if 'Y6S3_AprilFools_FakeItem' in tags:
                            excluded.append(source);continue
                        weapon=self.linked(item,'myWeapon')
                        group=self.scalar(weapon,'myWeaponGroup','AssaultRifle')
                        if group not in GROUPS:continue
                        if group=='SignatureWeapon' and item['resource_uid'] not in signatures:continue
                        line=list(self.lineage(weapon))
                        quality=self.scalar(item,'myQuality','Grey')
                        row={'uid':item['resource_uid'],'source':source,'name':self.item_name(item,'zh'),
                             'en':self.item_name(item,'en'),
                             'kind':'signature' if item['resource_uid'] in signatures else 'exotic' if quality=='Exotic' or self.scalar(item,'myIsExotic','FALSE')=='TRUE' else 'named' if self.scalar(item,'myIsNamed','FALSE')=='TRUE' else 'normal',
                             'quality':quality,'tags':tags,
                             'group':group,'weapon':[{'uid':r['resource_uid'],'name':r['internal_name'],'source':r['_source']} for r in line],
                             'damage':self.scalar(weapon,'myDamageMax'), 'rpm':self.scalar(weapon,'myRPM'),
                             'base_item_uid':next((x['target_uid'] for x in self.references(item,'myBaseWeapon')[1]),None),
                             'icon':self.scalar(item,'myIcon') or self.scalar(weapon,'myInventoryIcon')}
                        rows.append(row)
                except (OSError,ValueError,KeyError) as error:errors.append({'source':source,'reason':str(error)})
        return {'rows':rows,'unavailable':errors,'excluded':excluded}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['discover'])
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Use a fresh output')
    result=WeaponNative(ROOT/'resources/game/current/raw_files').discover()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    from collections import Counter
    print(json.dumps({'items':len(result['rows']),'kinds':dict(Counter(r['kind'] for r in result['rows'])),
                      'unavailable':len(result['unavailable'])},ensure_ascii=False))


if __name__=='__main__':main()
