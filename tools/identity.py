"""Registry-owned addresses; catalogs retain stable entity and asset references."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def raw_json(path):
    from tools.publish.bundle import read_json as strict_read
    return strict_read(path)


def registry(root=ROOT):
    return raw_json(Path(root)/'publishing/registry.json')['entries']

def page(entity_id, root=ROOT):
    rows=[r for r in registry(root) if r['kind']=='pages' and r.get('related_entity')==entity_id]
    if len(rows)!=1:raise ValueError('PAGE_IDENTITY_NOT_UNIQUE: '+entity_id)
    return rows[0]

def asset(asset_id, root=ROOT):
    rows=[r for r in registry(root) if r['kind']=='assets' and r['id']==asset_id]
    if len(rows)!=1:raise ValueError('ASSET_IDENTITY_NOT_UNIQUE: '+asset_id)
    return rows[0]

def display_name(entity):
    f=entity['fields']
    return f.get('套装全称') or f.get('装备组名称') or f.get('装备名称') or ''

def read_json(path):
    # Only business catalogs are projected. Publication evidence is never rewritten.
    path=Path(path);data=raw_json(path)
    roots=[p for p in path.resolve().parents if (p/'publishing/registry.json').is_file()]
    if not roots:return data
    root=roots[0]
    if 'data' not in path.relative_to(root).parts:return data
    entries=registry(root);by_id={r['id']:r for r in entries};by_entity={r.get('related_entity'):r for r in entries if r['kind']=='pages' and r.get('related_entity')}
    baseline=raw_json(root/'publishing/baseline.json')['entries'] if (root/'publishing/baseline.json').is_file() else []
    published={(r['namespace'],r['title'].split(':',1)[-1]) for r in baseline}
    def hydrate(v):
        if isinstance(v,list):return [hydrate(x) for x in v]
        if not isinstance(v,dict):return v
        out={k:hydrate(w) for k,w in v.items() if k!='asset_ref'}
        if v.get('asset_ref'):
            a=by_id[v['asset_ref']]
            if a['kind']!='assets':raise ValueError('NOT_AN_ASSET: '+a['id'])
            out.update(wiki_file=a['title'].split(':',1)[-1],confirmed_on_wiki=(6,a['title'].split(':',1)[-1]) in published,local_available=(root/a['source']).is_file())
            # Local content readiness is separate from publication.
        return out
    if path.name in ('brands.json','sets.json','records.json','native-map.json'):pass
    else:return hydrate(data)
    if path.name in ('records.json','native-map.json'):
        entities=data['entities']
        for id,e in (entities.items() if isinstance(entities,dict) else ((e['id'],e) for e in entities)):
            p=by_entity[id];e['source']=p['source'];e['page_title']=p['title'];e['page_id']=p['id']
        return data
    records=raw_json(root/'data/equipment/records.json')['entities'] if (root/'data/equipment/records.json').is_file() else {}
    if path.name=='sets.json':
        data=hydrate(data)
        for g in data['sets']:
            p=by_entity[g['id']];g.update(source=p['source'],title=display_name(records[g['id']]),page_title=p['title'])
            material=(g.get('material') or {}).get('display',{})
            material['brand_ref']=g['id']
        return data
    # Application source identity/evidence remains intact; current addresses are derived.
    for b in data['brands']:
        a=by_id[b['asset_ref']];b['wiki_filename']=a['title'].split(':',1)[-1]
        b['published_icon']={'wiki_file':b['wiki_filename'],'confirmed_on_wiki':(6,b['wiki_filename']) in published,'local_available':(root/a['source']).is_file()}
    data['entity_names']={id:display_name(e) for id,e in records.items()}
    data['entity_images']={id:by_id[e['visuals']['logo']]['title'].split(':',1)[-1] for id,e in records.items() if e.get('visuals',{}).get('logo')}
    return data


def validate(root=ROOT, check_bytes=True):
    """Validate registered identities and addresses; hashes cover Wiki assets only."""
    from tools.publish.bundle import digest, title_key, validate_asset_digest
    from tools.publish.asset_dependencies import AssetDependencies, publication_order
    from tools.asset_import.static_formats import safe_relative
    root=Path(root);entries=registry(root);ids={};titles={};paths={};entities={}
    for row in entries:
        if row['id'].casefold() in {id.casefold() for id in ids}:raise ValueError('DUPLICATE_REGISTRATION_ID: '+row['id'])
        ids[row['id']]=row
        key=title_key(row['title'],row['namespace'])
        if key in titles:raise ValueError('DUPLICATE_TITLE: '+row['title'])
        titles[key]=row['id']
        safe_relative(row['source']);key=row['source'].casefold()
        if key in paths:raise ValueError('DUPLICATE_SOURCE: '+row['source'])
        paths[key]=row['id']
        path=root/row['source']
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):raise ValueError('MISSING_OR_UNSAFE_SOURCE: '+row['id'])
        if row['kind']=='pages' and row.get('related_entity'):
            if row['related_entity'] in entities:raise ValueError('DUPLICATE_PAGE_ENTITY: '+row['related_entity'])
            entities[row['related_entity']]=row
        if row['kind']=='assets':
            if path.name!=row['title'].split(':',1)[-1]:raise ValueError('ASSET_SOURCE_TITLE_MISMATCH: '+row['id'])
            naming=row.get('naming',{})
            if naming.get('status')=='ready':
                if not naming.get('evidence') or not naming.get('english_label'):raise ValueError('ASSET_NAME_EVIDENCE_REQUIRED: '+row['id'])
                if not path.name.isascii():raise ValueError('ASSET_ENGLISH_NAME_REQUIRED: '+row['id'])
            validate_asset_digest(row, digest(path.read_bytes()) if check_bytes else None)
    resolver = AssetDependencies(entries, lambda row: (root / row['source']).read_text('utf8'))
    resolved = publication_order([{**row, 'asset_relationships': resolver.resolve(row)} for row in entries])
    records=raw_json(root/'data/equipment/records.json')['entities']
    mapping=raw_json(root/'data/equipment/native-map.json')
    native=mapping['entities']+mapping.get('weapons',[])
    for id,e in records.items():
        if id not in entities:raise ValueError('MISSING_PAGE_IDENTITY: '+id)
        if any(k in e for k in ('source','page_title','page_id')):raise ValueError('DUPLICATED_PAGE_ADDRESS: '+id)
        if '|资料ID='+id+'\n' not in (root/entities[id]['source']).read_text('utf8'):raise ValueError('PAGE_CONTENT_IDENTITY_MISMATCH: '+id)
        if e.get('visuals',{}).get('logo') and e['visuals']['logo'] not in ids:raise ValueError('MISSING_LOGO_ASSET: '+id)
    if len({e['id'] for e in native})!=len(native) or {e['id'] for e in native}!=set(records):raise ValueError('NATIVE_RECORD_IDENTITY_MISMATCH')
    def refs(v):
        if isinstance(v,list):
            for w in v:refs(w)
        elif isinstance(v,dict):
            if v.get('asset_ref') and (v['asset_ref'] not in ids or ids[v['asset_ref']]['kind']!='assets'):raise ValueError('MISSING_ASSET_REFERENCE: '+v['asset_ref'])
            for w in v.values():refs(w)
    for folder in ('brand-sets','gear-sets','exotic-gear'):
        for file in (root/'data'/folder).glob('*.json'):refs(raw_json(file))
    refs(records)
    # A normalized same title is never enough to identify a source file or asset.
    return {'registrations':len(entries),'entities':len(records),'assets':sum(r['kind']=='assets' for r in entries),
            'asset_relationships':sum(len(row['asset_relationships']) for row in resolved)}


if __name__=='__main__':
    print(json.dumps(validate(),ensure_ascii=False))
