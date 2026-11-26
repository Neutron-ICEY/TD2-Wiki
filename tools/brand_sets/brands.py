from tools.identity import read_json
"""Approved local brand identities. Wiki page identity and publication stay separate."""
import re

from tools.publish.bundle import require, normalized_title_name
from .equipment import validate_image_filename
from .knowledge import raster
from .model import plain

EMPTY = {"schema_version": 1, "brands": []}


def validate_catalog(data, ui):
    require(data.get('schema_version') == 1 and isinstance(data.get('brands'), list), 'BRAND_CATALOG_SCHEMA')
    keys = set(); filenames = {}
    for item in data['brands']:
        key = item.get('entity_key')
        require(isinstance(key, str) and re.fullmatch(r'brand_source:[0-9a-f]{20}', key) and key not in keys, 'BRAND_ENTITY_KEY')
        keys.add(key)
        require(item.get('entity_type') == 'brand_set' and item.get('entity_verified') is True, 'BRAND_IDENTITY_NOT_VERIFIED')
        require(item.get('game_internal_id') is None, 'APPLICATION_KEY_IS_NOT_GAME_INTERNAL_ID')
        for field in ('zh_name', 'en_name'):
            require(plain(item.get(field), field).strip() == item[field] and item[field], 'BRAND_CANONICAL_NAME')
        require(item.get('name_policy', {}).get('business_name_approved') is True, 'BRAND_BUSINESS_NAME_NOT_APPROVED')
        require(item['name_policy'].get('official_game_zh_verified') is False, 'BRAND_OFFICIAL_ZH_EVIDENCE_MISSING')
        require(item.get('source_names', {}).get('source_full_chinese_name') == item['zh_name']
                and item['source_names'].get('source_full_english_name') == item['en_name'], 'BRAND_SOURCE_NAME_CONFLICT')
        require(isinstance(item.get('search_aliases'), list), 'BRAND_ALIASES')
        for alias in item['search_aliases']:
            require(plain(alias, '品牌别名').strip(), 'BRAND_ALIAS_EMPTY')
        filename = item.get('wiki_filename')
        validate_image_filename(filename)
        require(item.get('entity_ref') and item.get('asset_ref'), 'BRAND_STABLE_REFERENCES')
        mapping = item.get('asset_mapping', {})
        require(mapping.get('mapping_verified') is True and mapping.get('asset_role') == 'brand_logo', 'BRAND_ASSET_MAPPING')
        require(mapping.get('source_asset_ids') and mapping.get('relation_ids') and item.get('source_evidence'), 'BRAND_EVIDENCE_MISSING')
        hashes = mapping.get('source_sha256', [])
        require(hashes and all(isinstance(h, str) and re.fullmatch('[0-9a-f]{64}', h) for h in hashes), 'BRAND_SOURCE_HASH')
        require(mapping.get('selected_asset_id') in mapping['source_asset_ids']
                and mapping.get('selected_source_sha256') in hashes, 'BRAND_SELECTED_PAYLOAD')
        prior = filenames.get(normalized_title_name(filename))
        require(prior is None or prior == (filename, mapping['selected_source_sha256']), 'BRAND_FILENAME_COLLISION')
        filenames[normalized_title_name(filename)] = (filename, mapping['selected_source_sha256'])
        raster(item['published_icon'])
        require(item.get('catalog_ready') is True, 'BRAND_CATALOG_NOT_READY')
    return data


def load_catalog(root):
    path = root / 'data/brand-sets/brands.json'
    data = read_json(path) if path.is_file() else EMPTY
    return validate_catalog(data, read_json(root / 'data/brand-sets/equipment-ui.json'))


def by_key(catalog):
    return {item['entity_key']: item for item in catalog['brands']}


def image_reference(root, entity_key):
    item = by_key(load_catalog(root))[entity_key]
    return dict(entity_key=entity_key, filename=item['wiki_filename'], template='TD2品牌图片',
                parameters={'品牌': item['entity_ref']}, confirmed_on_wiki=item['published_icon']['confirmed_on_wiki'])
