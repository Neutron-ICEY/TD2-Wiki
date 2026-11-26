"""Shared equipment attribute rules; legacy named presets remain authoritative."""
import json


def load(root):
    return json.loads((root / 'data/equipment/attributes.json').read_text(encoding='utf8'))


def identity(row, catalog):
    native = catalog.get('identities', {}).get(row['id'])
    if not native: return row
    return {**row, **{key:native[key] for key in ('en_name','unit_type')},
            'zh_name':native.get('display_alias') or native['zh_name']}


def ordinary_rows(minor, catalog):
    return attribute_rows(minor, catalog, 'ordinary')


def exotic_rows(minor, catalog):
    return attribute_rows(minor, catalog, 'exotic_special')


def attribute_rows(minor, catalog, kind):
    identities = {a['id']: identity(a, catalog) for a in minor['attributes']}
    rows = []
    for rule in catalog['rules']:
        if rule['kind'] != kind or rule['attribute_id'] not in identities:
            continue
        a = identities[rule['attribute_id']]
        rows.append(dict(id=rule['id'], minor_attribute_id=a['id'], value=rule['display_max'] or '',
            category=a['category'], unit=a['unit_type'], zh_name=a['zh_name'], en_name=a['en_name'],
            kind=kind, active=a.get('active', True), search_aliases=[], verification=rule['verification'], sources=[],
            keys=[], native_uid=rule['native_uid']))
    return rows
