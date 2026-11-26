"""Pure evidence checks for exact names and recorded image references."""


def unique_exact(rows, value):
    """No punctuation repair, edit distance or display-name-only entity merging."""
    if not isinstance(value, str) or not value:
        return None
    matches = [(row, evidence) for row, evidence in rows if row.get('name', '').casefold() == value.casefold()]
    return matches[0] if len(matches) == 1 else None


def image_reference_check(asset, binding, proof, original):
    """Check literal/native/byte/pixel paths; a confidence label is not evidence."""
    direct = [a for a in original if a['source_platform'] == binding['source_platform'] and
              a['source_entry'] in ('wwwroot/' + binding['source_filename'], 'assets/wwwroot/' + binding['source_filename'])]
    method = proof['evidence_type']
    if method == 'literal_filename_reference':
        valid = any(a['asset_id'] == asset['asset_id'] for a in direct) and proof['confidence'] == 'exact'
    elif method in ('exact_sha256_bridge', 'decoded_pixel_bridge'):
        sources = [a for a in direct if a['asset_id'] in proof['bridge_source_asset_ids']]
        valid = bool(sources) and proof['confidence'] == 'exact' and all(
            a['source_sha256'] == asset['source_sha256'] if method == 'exact_sha256_bridge' else
            bool(a.get('pixel_hash')) and a['pixel_hash'] == asset['pixel_hash'] for a in sources)
    elif method == 'filename_only_native_resource_candidate':
        valid = asset['source_filename'] == binding['source_filename'] and proof['confidence'] == 'medium'
    else:
        valid = False
    if not valid:
        raise ValueError('IMAGE_REFERENCE_PROOF_FAILED: ' + proof['evidence_id'])
    return dict(method=method, actual_literal_filename=binding['source_filename'], reproduced=True,
                native_runtime_consumption_proven=False if proof['confidence'] == 'medium' else None)
