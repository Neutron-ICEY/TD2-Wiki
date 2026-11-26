"""Select named fixtures explicitly; production consumers use stable identities."""
from tools import identity
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def entity_id(name):
    data=identity.raw_json(ROOT/'data/equipment/records.json')['entities']
    rows=[id for id,e in data.items() if identity.display_name(e)==name]
    assert len(rows)==1,(name,rows)
    return rows[0]
def source_for(name):
    return ROOT/identity.page(entity_id(name))['source']
def asset_file(id):
    return identity.asset(id)['title'].split(':',1)[-1]
def material_id(name):
    rows=identity.raw_json(ROOT/'data/brand-sets/equipment-ui.json')['material_display']
    matches=[k for k,v in rows.items() if name==v['name'] or name in v.get('aliases',[])]
    assert len(matches)==1,(name,matches)
    return matches[0]
