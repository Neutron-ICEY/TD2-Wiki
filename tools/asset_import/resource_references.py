"""Exact, version-bound corrections of source references; no identity promotion."""
from .static_formats import sha256


def effective_image_reference(binding, overrides):
    fingerprint = sha256(__import__('json').dumps(binding, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8'))
    matches = [row for row in overrides.get('overrides', []) if row['binding_sha256'] == fingerprint]
    if len(matches) > 1:
        raise ValueError('SOURCE_REFERENCE_OVERRIDE_CONFLICT')
    if not matches:
        return dict(source_filename=binding['source_filename'], corrected=False, mapping_verified=False)
    row = matches[0]
    if row['original_filename'] != binding['source_filename'] or row['source_platform'] != binding['source_platform']:
        raise ValueError('SOURCE_REFERENCE_OVERRIDE_MISMATCH')
    return dict(source_filename=row['corrected_logical_filename'], original_filename=binding['source_filename'],
                corrected=True, mapping_verified=False, override_id=row['override_id'],
                target_asset_ids=row['target_asset_ids'], native_runtime_consumption_proven=False)
