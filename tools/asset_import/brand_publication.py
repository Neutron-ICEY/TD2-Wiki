"""Classify an observed publication candidate without writing or authorizing uploads."""
from .continuation import file_decision


def publication_status(entity, page, rights, resolver_compatible):
    if not entity.get('entity_verified') or not entity.get('catalog_ready'):
        return 'ENTITY_NOT_READY'
    if not entity.get('asset_mapping', {}).get('mapping_verified'):
        return 'MAPPING_NOT_VERIFIED'
    if (not resolver_compatible or not {'read', 'edit', 'createpage', 'upload'}.issubset(rights)
            or page is None or page.get('protection') != []):
        return 'REMOTE_UNKNOWN'
    if page.get('missing') is True and page.get('imagerepository', '') != '':
        return 'REMOTE_UNKNOWN'
    decision = file_decision(page, entity['asset_mapping']['selected_source_sha1'])
    return {'upload': 'READY_TO_UPLOAD', 'already_present': 'ALREADY_PRESENT',
            'FILE_CONFLICT': 'FILE_CONFLICT'}.get(decision, 'REMOTE_UNKNOWN')
