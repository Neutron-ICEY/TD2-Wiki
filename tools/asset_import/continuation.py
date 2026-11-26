"""Pure checks over recorded source roles and file observations; no I/O."""
import re


TECHNICAL_TYPES = {'talent': 'talent_icon', 'attribute': 'attribute_icon',
    'brand': 'brand_icon', 'gear_set': 'gearset_icon', 'mod': 'mod_icon'}


def require(value, code):
    if not value:
        raise ValueError(code)


def classify(asset, evidence):
    rows = [evidence[k] for k in asset['evidence']]
    categories = {r['candidate_category'] for r in rows if r['confidence'] == 'exact'}
    technical = TECHNICAL_TYPES.get(next(iter(categories)), 'unknown') if len(categories) == 1 else 'unknown'
    status = 'source_only' if categories else 'candidate' if rows else 'unresolved'
    return technical, status


def verified_core_bindings(key, canonical, bindings, ui):
    require(canonical['scope'] == 'gear_main' and canonical['status'] == 'exact_existing'
            and canonical['confidence'] == 'exact' and canonical['source_scope_membership'] == 'GearAttribute1List', 'CORE_IDENTITY_NOT_EXACT')
    require(canonical['wiki_stable_id'] == key and canonical['wiki_chinese_name'] == ui['major_names'][key]
            and canonical['source_chinese_name'] == ui['major_names'][key], 'CORE_CATALOG_CHANGED')
    expected_fields = set(canonical['source_internal_keys'])
    results = {}
    for platform in ('apk', 'windows'):
        found = [b for b in bindings if b['source_platform'] == platform and b['category'] == 'attribute'
                 and b['internal_key'] == canonical['source_internal_name']
                 and any(e.get('source_field') in expected_fields for e in b['evidence'])]
        require(len(found) == 1 and found[0]['confidence'] == 'exact', 'CORE_IMAGE_BINDING_AMBIGUOUS')
        results[platform] = found[0]
    require(results['apk']['source_filename'] == results['windows']['source_filename'], 'CORE_PLATFORM_BINDING_CONFLICT')
    return results


def file_decision(page, expected_sha1):
    """Decide from an observed file version; never authorize an overwrite."""
    if page.get('missing') is True and not page.get('imageinfo'):
        return 'upload' if page.get('protection') == [] else 'REMOTE_UNVERIFIED'
    versions = page.get('imageinfo', [])
    if not page.get('pageid') or not versions or not isinstance(expected_sha1, str):
        return 'REMOTE_UNVERIFIED'
    observed = versions[0].get('sha1')
    if not isinstance(observed, str) or not re.fullmatch('[0-9a-f]{40}', observed):
        return 'REMOTE_UNVERIFIED'
    return 'already_present' if observed == expected_sha1 else 'FILE_CONFLICT'


def preflight_entry(remote, filename, expected_sha1=None):
    require(set(('read', 'edit', 'createpage', 'upload')).issubset(remote['file_preflight']['rights']), 'WIKI_RIGHTS_MISSING')
    pages = [p for p in remote['file_preflight']['pages'] if p['title'].split(':', 1)[-1] == filename]
    require(len(pages) == 1, 'FILE_CONFLICT_OR_UNKNOWN_REMOTE_STATE')
    require(file_decision(pages[0], expected_sha1) in ('upload', 'already_present'), 'FILE_CONFLICT_OR_UNKNOWN_REMOTE_STATE')
    return pages[0]


def verified_uploads(plan, observed, downloaded):
    """Check public readback, independently downloaded bytes and upload history."""
    result = []
    for entry in plan['entries']:
        filename = entry['wiki_filename']
        pages = [p for p in observed['query']['pages'] if p['title'].split(':', 1)[-1] == filename]
        require(len(pages) == 1 and file_decision(pages[0], entry['source_sha1']) == 'already_present', 'UPLOAD_READBACK_HASH_MISMATCH')
        page = pages[0]; info = page['imageinfo'][0]; blob = downloaded[filename]
        require(info['mime'] == 'image/png' and info['size'] == entry['byte_size']
            and (info['width'], info['height']) == (entry['width'], entry['height']), 'UPLOAD_READBACK_METADATA_MISMATCH')
        require(blob['sha256'] == entry['normalized_sha256'] and blob['sha1'] == info['sha1']
            and blob['size'] == info['size'], 'REMOTE_BYTES_MISMATCH')
        require(page['lastrevid'] > 0 and info['timestamp'] and len(page['imageinfo']) == 1, 'UNEXPECTED_FILE_REVISION_HISTORY')
        result.append(dict(entry, upload_status='uploaded_verified', wiki_pageid=page['pageid'],
            wiki_revision=page['lastrevid'], wiki_timestamp=info['timestamp'], wiki_url=info['descriptionurl'],
            remote_sha1=info['sha1'], remote_sha256=blob['sha256'], remote_mime=info['mime'],
            file_revision=info['timestamp'] + '/' + info['sha1'], history_count=len(page['imageinfo'])))
    return result
