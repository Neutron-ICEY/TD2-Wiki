"""Passive Hunter preflight/target planning and isolated export provenance.

No executable launch, game write, CLI invention, export-all, or image identity
inference. A manual export can be registered later, without promoting it.
"""
from collections import defaultdict
import json
from pathlib import Path

from .investigate import dump
from .static_formats import image_metadata, sha256

GAP_TYPES = ('IMAGE_EXISTS_MAPPING_MISSING', 'IMAGE_MISSING', 'IMAGE_EXISTS_ENTITY_MISSING', 'IMAGE_VARIANT_MISSING')
FAILURE_STATUSES = ('TARGET_NOT_FOUND', 'TOOL_UNAVAILABLE', 'GAME_FILES_UNAVAILABLE', 'EXPORT_UNSUPPORTED',
                    'EXPORT_FAILED', 'EXTRACTED_UNMAPPED', 'EXTRACTED_VERIFIED')


def extraction_gate(gap_type, candidate_ids, confirmed_missing, role_verified, p0_p2_complete):
    if gap_type not in GAP_TYPES:
        raise ValueError('UNKNOWN_IMAGE_GAP_TYPE')
    if gap_type in ('IMAGE_EXISTS_MAPPING_MISSING', 'IMAGE_EXISTS_ENTITY_MISSING'):
        return False, 'Existing image/mapping or Catalog gap must be handled at P0-P2.'
    if not (confirmed_missing and role_verified and p0_p2_complete):
        return False, 'Missing image/independent variant and current consumer demand are not confirmed after P0-P2.'
    if gap_type == 'IMAGE_MISSING' and candidate_ids:
        return False, 'Existing candidate images must be excluded by evidence before claiming missing.'
    return True, 'Confirmed image gap only; individual target review still required before manual export.'


def target_plan(out):
    mappings = json.loads((out / 'entity-mappings.json').read_text(encoding='utf-8'))['mappings']
    assets = json.loads((out / 'asset-manifest.json').read_text(encoding='utf-8'))['assets']
    by_entity = defaultdict(list)
    for row in mappings:
        by_entity[row['entity_key']].append(row)
    targets = []
    for key, rows in sorted(by_entity.items()):
        first = rows[0]
        verified = any(r['mapping_status'] == 'verified_mapping_proposal' for r in rows)
        gap = 'IMAGE_EXISTS_ENTITY_MISSING' if verified else 'IMAGE_EXISTS_MAPPING_MISSING'
        candidate_ids = sorted({s for row in rows for s in row['source_asset_ids']})
        allowed, reason = extraction_gate(gap, candidate_ids, False, verified, True)
        targets.append(dict(entity_key=key, entity_type=first['entity_type'], chinese_name=first['source_chinese_name'],
            english_name=first.get('matched_entity_name') or first.get('source_english_name'), internal_name=first['internal_name'],
            source_references=sorted({s for row in rows for s in row['source_evidence_ids']}),
            target_image_role=first.get('asset_role', 'UNKNOWN'), existing_candidate_assets=candidate_ids,
            reason=reason, gap_type=gap, confirmed_missing=False, p0_p2_complete_for_existing_pool=True,
            extraction_eligible=allowed, search_keywords=sorted({v for v in
                (first.get('source_english_name'), first.get('matched_entity_name'), first['internal_name']) if v}),
            evidence=[e for row in rows for e in row['source_evidence']],
            hunter_search_executed=False, result='NOT_REQUESTED_EXISTING_IMAGE_GAP'))
    # Unresolved inventory is not a list of missing textures. Six current slot
    # consumers have no approved symbol mapping; filename hints do not prove an
    # absent image or authorize a search/export of every model in the client.
    slots = []
    ui = json.loads((out / 'inputs/catalog/primary/equipment-ui.json').read_text(encoding='utf-8'))
    possible_slots = [a['asset_id'] for a in assets if a['source_filename'].startswith('gear')
                      and not a['source_filename'].startswith('gearset')]
    for slot, config in sorted(ui['slot_visuals'].items()):
        if not config.get('wiki_file'):
            slots.append(dict(entity_key='equipment_slot/' + slot, entity_type='equipment_slot', chinese_name='UNKNOWN',
                english_name=slot, internal_name='UNKNOWN', source_references=['data/brand-sets/equipment-ui.json#/slot_visuals/' + slot],
                target_image_role='current generic slot visual', existing_candidate_assets=possible_slots,
                reason='P1 slot-role identification incomplete; an empty Wiki mapping does not prove the client image is absent.',
                gap_type='IMAGE_EXISTS_MAPPING_MISSING', confirmed_missing=False, extraction_eligible=False,
                search_keywords=[slot], evidence=[], hunter_search_executed=False, result='DEFERRED_P1_ROLE_VERIFICATION'))
    targets.extend(slots)
    result = dict(schema_version=1, targets=targets, executable_targets=[t for t in targets if t['extraction_eligible']],
                  source_record_inventory_not_a_missing_asset_list=True, loose_image_semantics='UNVERIFIED_HINT',
                  example_resource_hint='player_gear_mask_exotic_01_ps_gm_ex1_a1', example_is_verified_target=False,
                  gm_nm_cm_semantics='UNKNOWN', failure_status_vocabulary=FAILURE_STATUSES,
                  counts_by_gap={gap: sum(t['gap_type'] == gap for t in targets) for gap in GAP_TYPES})
    dump(out / 'hunter-targets.json', result)
    raw = out / 'hunter/raw'
    raw.mkdir(parents=True, exist_ok=True)
    manifest = out / 'hunter/export-manifest.json'
    if manifest.exists() and json.loads(manifest.read_text(encoding='utf-8')).get('exports'):
        raise ValueError('EXISTING_HUNTER_EXPORT_MANIFEST_MUST_NOT_BE_REPLACED')
    dump(manifest, dict(schema_version=1, exports=[], exported_file_count=0,
         executable_launched=False, source_container_written=False, normalized=False, status='NOT_RUN_NO_CONFIRMED_IMAGE_MISSING_TARGET'))
    return result


def exported_record(out, exported_path, provenance):
    """Record an existing manually exported copy, never an original game file.

    Container bytes, original encoded resource bytes, decoded RGBA pixels and
    future normalized bytes have distinct fields. Unknown hashes stay UNKNOWN.
    """
    out = out.resolve()
    raw = (out / 'hunter/raw').resolve()
    if out not in raw.parents:
        raise ValueError('HUNTER_RAW_DIRECTORY_ESCAPES_REVIEW')
    path = Path(exported_path).resolve()
    if raw not in path.parents or not path.is_file():
        raise ValueError('EXPORT_MUST_BE_ISOLATED_MANUAL_COPY')
    data = path.read_bytes()
    try:
        metadata = image_metadata(data)
    except (NotImplementedError, ImportError) as error:
        raise ValueError('EXPORT_UNSUPPORTED: decoder unavailable') from error
    except (OSError, ValueError) as error:
        raise ValueError('EXPORT_FAILED: exported copy cannot be decoded') from error
    if metadata['source_format'] not in ('DDS', 'PNG', 'TIFF', 'TGA'):
        raise ValueError('EXPORT_UNSUPPORTED')
    required = ('source_container', 'source_container_sha256', 'hunter_version', 'game_build',
                'resource_name', 'resource_id', 'exported_at', 'export_settings', 'original_image_sha256')
    fields = {name: provenance.get(name) or 'UNKNOWN' for name in required}
    original_hash = fields.pop('original_image_sha256')
    return dict(fields, exported_path=str(path), exported_file_sha256=sha256(data),
                original_resource_sha256=original_hash,
                decoded_image_sha256=metadata.get('pixel_hash') or 'UNKNOWN',
                decoded_hash_contract='tools.asset_import.static_formats.image_metadata dimension+RGBA8 digest',
                normalized_file_sha256='UNKNOWN', source_format=metadata['source_format'], width=metadata['width'],
                height=metadata['height'], alpha=metadata['alpha'], transparency=metadata['transparency'],
                mapping_status='EXTRACTED_UNMAPPED', entity_key=None, technical_category='UNKNOWN',
                identity_from_filename_or_visual=False, human_approved=False)


def export_duplicate_links(record, existing_assets):
    """Do not equate byte/pixel duplication with an entity or purpose identity."""
    return dict(exact_export_byte_sources=sorted(a['asset_id'] for a in existing_assets
                    if a['source_sha256'] == record['exported_file_sha256']),
                decoded_pixel_sources=sorted(a['asset_id'] for a in existing_assets
                    if a.get('pixel_hash') and a['pixel_hash'] == record['decoded_image_sha256']),
                visual_similarity='NOT_COMPUTED_NOT_IDENTITY_EVIDENCE', entity_promotion=False)


def asset_manifest_entry(out, record):
    """Adapt an isolated copy to the existing manifest, with no semantic approval."""
    path = Path(record['exported_path']).resolve()
    out = Path(out).resolve()
    raw = (out / 'hunter/raw').resolve()
    if out not in raw.parents or raw not in path.parents:
        raise ValueError('EXPORT_MUST_BE_ISOLATED_MANUAL_COPY')
    if sha256(path.read_bytes()) != record['exported_file_sha256']:
        raise ValueError('EXPORTED_COPY_CHANGED')
    source_identity = json.dumps([record['source_container'], record['source_container_sha256'],
        record['resource_name'], record['resource_id'], record['exported_file_sha256']], ensure_ascii=False)
    asset_id = 'hunter:' + sha256(source_identity.encode())[:20]
    return dict(asset_id=asset_id, source_platform='game-hunter', source_package=record['source_container'],
        source_entry=record['resource_name'], source_filename=path.name,
        source_sha256=record['exported_file_sha256'], source_format=record['source_format'],
        raw_path=path.relative_to(out).as_posix(), source_review=str(out),
        width=record['width'], height=record['height'], alpha=record['alpha'], transparency=record['transparency'],
        pixel_hash=record['decoded_image_sha256'] if record['decoded_image_sha256'] != 'UNKNOWN' else None,
        category='unknown', technical_category='unknown', confidence='unknown', status='unmatched',
        mapping_status='unresolved', upload_status='not_eligible', hunter_result='EXTRACTED_UNMAPPED',
        entity_key=None, stable_id=None, icon_key=None, wiki_filename=None, wiki_revision=None,
        normalized_filename=None, normalized_sha256=None, intended_wiki_filename=None, conversion=None,
        game_entities=[], chinese_names=[], english_names=[], proposed_game_entities=[],
        proposed_chinese_names=[], proposed_english_names=[], evidence=[], match_method=[], duplicate_group=[],
        semantic_mappings=[], naming_gate='CLOSED', provenance=record,
        notes=['Manual Hunter copy; container/original/exported/decoded hashes are distinct; no entity inferred.'])
