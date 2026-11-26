"""Build review-only native text indexes from the registered scope and current resources."""
import argparse
from copy import deepcopy
import csv
import io
import hashlib
import json
from pathlib import Path
import re

from tools.game_resources import ResourceError, locked, store_at

from .locations import SourceLocations, _relative
from .text_evidence import native_definitions, native_references
from .text_library import DEFAULT_INDEX, ROOT, TextError, identity, json_document, local_file, require, sha256


RULES = ('fruit_definition_scopes@1', 'fruit_definition_scopes@2',
         'fruit_definition_scopes@3', 'fruit_definition_scopes@4')


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def validate_menu(blob):
    rows = csv.reader(io.StringIO(blob.decode('utf-8-sig'), newline=''), strict=True)
    require(next(rows, None) == ['2', '', '', ''], 'UNSUPPORTED_MENU_HEADER')
    header = next(rows, None)
    require(header is not None and len(header) == 4 and header[0].isdigit()
            and header[1:] == ['', '', ''], 'INVALID_MENU_COUNT')
    count = 0
    for row in rows:
        require(len(row) == 4 and re.fullmatch('[0-9A-F]{32}', row[0]), 'INVALID_MENU_RECORD')
        count += 1
    require(count == int(header[0]), 'MENU_COUNT_MISMATCH')


def source_name(spec):
    return spec.get('derived_source', {}).get('original_resource_name', spec['resource_name'])


def build(root, output, index=DEFAULT_INDEX):
    """Write a fresh candidate only; a blocked run writes its issue report alone."""
    root = Path(root).resolve()
    store = store_at(root)
    with locked(store):
        require(not (store / '.transaction').exists(), 'PENDING_TRANSACTION_USE_RECOVER')
        require(not (store / '.initializing.json').exists(), 'PENDING_INITIALIZATION_USE_RECOVER')
        return _build(root, output, index)


def _build(root, output, index):
    out = Path(output)
    out = (out if out.is_absolute() else root / out).resolve()
    review_roots = (root / 'dist', root / 'evidence/asset-import/native')
    require(any(out.is_relative_to(base) and out != base for base in review_roots), 'OUTPUT_OUTSIDE_REVIEW_ROOT')
    require(not out.exists(), 'OUTPUT_MUST_BE_FRESH')
    locations = SourceLocations(root)
    inputs = {}

    def read(path, expected=None):
        p = locations.resolve(local_file(root, path))
        blob = p.read_bytes()
        digest = sha256(blob)
        require(expected is None or digest == expected, 'INPUT_HASH_MISMATCH')
        key = p.relative_to(root).as_posix()
        require(key not in inputs or inputs[key] == digest, 'INPUT_CHANGED_DURING_INDEXING')
        inputs[key] = digest
        return blob

    source_blob = read('resources/game/source.json')
    source = json_document(source_blob)
    require(source.get('schema_version') == 1 and isinstance(source.get('sources'), dict)
            and isinstance(source.get('manifest_sha256'), str)
            and re.fullmatch('[0-9a-f]{64}', source['manifest_sha256']), 'INVALID_GAME_SOURCE')
    registered = json_document(read(index))
    require(registered.get('schema_version') == 1, 'UNSUPPORTED_TEXT_INDEX')
    old_defs_spec, old_refs_spec = registered['native_definitions'], registered['native_references']
    old_defs = json_document(read(old_defs_spec['file'], old_defs_spec['sha256']))
    old_refs = json_document(read(old_refs_spec['file'], old_refs_spec['sha256']))
    require(old_defs.get('parser_rule') in RULES
            and old_refs.get('parser_rule') == 'fruit_localization_guid_fields@1', 'UNSUPPORTED_NATIVE_INDEX_RULE')
    require([{k: v for k, v in s.items() if k not in ('parsed', 'parser_rule')} for s in old_defs['files']] == old_refs['files'],
            'NATIVE_INDEX_SCOPE_CONFLICT')
    require(len({s['file'] for s in old_defs['files']}) == len(old_defs['files']), 'DUPLICATE_NATIVE_DEFINITION_FILE')
    requested = {'raw_files/' + source_name(s) for s in old_defs['files'] + old_defs.get('schema_evidence', [])}
    requested.update('raw_files/' + s['locale']['namespace'] for s in registered['sources'] if s.get('format') == 'menus_csv')
    manifest, unselected_examples = {}, []
    manifest_count = manifest_bytes = unselected_count = 0
    previous_path = None
    digest = hashlib.sha256()
    manifest_path = local_file(root, 'resources/game/manifest.jsonl')
    with manifest_path.open('rb') as stream:
        for line in stream:
            digest.update(line)
            row = json_document(line)
            path = _relative(row.get('path'))
            folded = path.casefold()
            require(previous_path is None or previous_path < folded, 'UNSORTED_OR_DUPLICATE_RESOURCE_PATH')
            previous_path = folded
            require(isinstance(row.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', row['sha256'])
                    and type(row.get('bytes')) is int and row['bytes'] >= 0
                    and row.get('source_id') in source['sources'], 'INVALID_RESOURCE_RECORD')
            manifest_count += 1
            manifest_bytes += row['bytes']
            if path in requested:
                manifest[path] = row
            elif path.startswith('raw_files/'):
                unselected_count += 1
                if len(unselected_examples) < 50:
                    unselected_examples.append(path)
    manifest_sha = digest.hexdigest()
    require(manifest_sha == source['manifest_sha256'], 'INPUT_HASH_MISMATCH')
    inputs['resources/game/manifest.jsonl'] = manifest_sha
    require(manifest_count == source.get('files') and manifest_bytes == source.get('bytes'), 'RESOURCE_MANIFEST_TOTAL_MISMATCH')
    output_prefix = out.relative_to(root).as_posix()
    changed, issues, staged, ledger_rows = [], [], {}, []

    def current(resource_name):
        local_file(root, resource_name)
        require(resource_name.startswith(('hunter/', 'rogue/', 'snowdrop/')), 'INVALID_NATIVE_RESOURCE_NAME')
        relative = 'raw_files/' + resource_name
        require(relative in manifest, 'SELECTED_RESOURCE_MISSING')
        m = manifest[relative]
        file = 'resources/game/current/' + relative
        blob = read(file, m['sha256'])
        require(len(blob) == m['bytes'], 'RESOURCE_SIZE_MISMATCH')
        origin = source['sources'][m['source_id']]
        spec = dict(file=file, sha256=m['sha256'], bytes=m['bytes'], resource_name=resource_name,
                    export_role='current_raw_text', source_id=m['source_id'],
                    source_container_sha256=origin.get('source_container_sha256'),
                    manual_provenance=dict(origin=origin.get('origin'), current_manual_dataset_id=m['source_id'],
                                           game_build=origin.get('game_build')))
        return spec, blob

    def issue(error, file):
        issues.append(dict(file=file, code=error.code if isinstance(error, TextError)
                           else 'INPUT_MISSING' if isinstance(error, FileNotFoundError)
                           else 'INPUT_UNREADABLE' if isinstance(error, OSError) else 'INVALID_NATIVE_INPUT'))

    definitions, references = [], []
    for i, previous in enumerate(old_defs['files']):
        try:
            rule = previous.get('parser_rule', old_defs['parser_rule'])
            require(rule in RULES, 'UNSUPPORTED_NATIVE_DEFINITION_RULE')
            spec, blob = current(source_name(previous))
            if previous.get('derived_source'):
                parent = previous['derived_source']
                require(spec['sha256'] == parent['sha256'], 'DERIVED_INPUT_REQUIRES_REVIEW')
                slices = parent.get('slices')
                require(isinstance(slices, list) and bool(slices), 'UNSUPPORTED_DERIVATION')
                require(all(type(s.get('byte_start')) is int and type(s.get('byte_end')) is int
                            and 0 <= s['byte_start'] < s['byte_end'] <= len(blob) for s in slices), 'INVALID_DERIVED_RANGE')
                fragment = b''.join(blob[s['byte_start']:s['byte_end']] for s in slices)
                require(sha256(fragment) == previous['sha256'], 'DERIVED_INPUT_HASH_MISMATCH')
                file = 'fragments/' + str(i) + '-' + Path(previous['file']).name
                staged[file] = fragment
                derived = dict(deepcopy(parent), file=spec['file'], sha256=spec['sha256'],
                               bytes=spec['bytes'], source_id=spec['source_id'])
                spec.update(file=output_prefix + '/' + file, sha256=sha256(fragment), bytes=len(fragment),
                            export_role='verbatim_source_excerpt', derived_source=derived,
                            resource_name=previous['resource_name'])
                blob = fragment
            if spec['sha256'] != previous['sha256']:
                changed.append(dict(resource_name=previous['resource_name'], previous_sha256=previous['sha256'],
                                    sha256=spec['sha256'], role='definition'))
            if 'generation_context' in previous:
                spec['generation_context'] = deepcopy(previous['generation_context'])
            parsed = native_definitions(blob, include_formulas=rule != RULES[0],
                                        include_data=rule in RULES[2:], include_objects=rule == RULES[3])
            refs = native_references(blob)
            for problem in parsed['issues'] + refs['issues']:
                issues.append(dict(problem, file=spec['file']))
            ledger_rows.append({k: v for k, v in spec.items() if k not in ('parsed', 'ledger')})
            definitions.append(dict(spec, parser_rule=rule, parsed=parsed))
            for row in refs['references']:
                references.append(dict(row, file_index=len(definitions) - 1,
                    reference_id=identity([spec['file'], spec['sha256'], row['location']['byte_start'], row['field'], row['guid']])))
        except (OSError, ValueError, KeyError, TypeError) as error:
            issue(error, previous.get('file'))

    schemas = []
    for previous in old_defs.get('schema_evidence', []):
        try:
            spec, _ = current(previous['resource_name'])
            spec['export_role'] = 'current_raw_schema'
            schemas.append(spec)
            if spec['sha256'] != previous['sha256']:
                changed.append(dict(resource_name=previous['resource_name'], previous_sha256=previous['sha256'],
                                    sha256=spec['sha256'], role='schema'))
        except (OSError, ValueError, KeyError, TypeError) as error:
            issue(error, previous.get('file'))

    candidate = deepcopy(registered)
    menus = []
    for text_source in candidate['sources']:
        if text_source.get('format') != 'menus_csv':
            continue
        try:
            spec, blob = current(text_source['locale']['namespace'])
            if spec['sha256'] != text_source['sha256']:
                changed.append(dict(resource_name=spec['resource_name'], previous_sha256=text_source['sha256'],
                                    sha256=spec['sha256'], role='localization'))
            text_source.update(file=spec['file'], sha256=spec['sha256'], manual_provenance=spec['manual_provenance'],
                               batch_ref=output_prefix + '/provenance.json')
            menus.append(dict(spec))
            validate_menu(blob)
        except (OSError, ValueError, KeyError, TypeError, csv.Error) as error:
            issue(error, text_source.get('file'))

    ledger = dict(schema_version=1, source=dict(file='resources/game/source.json', sha256=sha256(source_blob)),
                  resource_manifest=dict(file='resources/game/manifest.jsonl', sha256=manifest_sha),
                  previous_indexes=dict(definitions=old_defs_spec, references=old_refs_spec),
                  files=ledger_rows, immutable_input_copies=menus)
    ledger_blob = json_bytes(ledger)
    ledger_ref = dict(file=output_prefix + '/provenance.json', sha256=sha256(ledger_blob))
    for i, spec in enumerate(definitions):
        spec['ledger'] = dict(ledger_ref, pointer='/files/' + str(i))
    for text_source in candidate['sources']:
        if text_source.get('format') == 'menus_csv':
            text_source['evidence'] = dict(provenance=ledger_ref)
    defs = dict(schema_version=1, parser_rule=old_defs['parser_rule'], schema_evidence=schemas, files=definitions)
    refs = dict(schema_version=1, parser_rule=old_refs['parser_rule'],
                files=[{k: v for k, v in s.items() if k not in ('parsed', 'parser_rule')} for s in definitions],
                references=references, issues=[])
    defs_blob, refs_blob = json_bytes(defs), json_bytes(refs)
    candidate['native_definitions'] = dict(file=output_prefix + '/native-definitions.json', sha256=sha256(defs_blob))
    candidate['native_references'] = dict(file=output_prefix + '/native-references.json', sha256=sha256(refs_blob),
                                          target_sources=old_refs_spec['target_sources'])
    for file, digest in inputs.items():
        try:
            with local_file(root, file).open('rb') as stream:
                require(hashlib.file_digest(stream, 'sha256').hexdigest() == digest, 'INPUT_CHANGED_DURING_INDEXING')
        except (OSError, ValueError) as error:
            issue(error, file)
    report = dict(schema_version=1, status='BLOCKED' if issues else 'REVIEW_CANDIDATE',
                  source_manifest_sha256=manifest_sha, selected_definition_files=len(old_defs['files']),
                  parsed_definition_files=len(definitions), changes=changed, issues=issues,
                  unselected_current_raw_file_count=unselected_count, unselected_current_raw_files=unselected_examples,
                  unselected_examples_truncated=unselected_count > len(unselected_examples),
                  retained_registered_source_ids=[s['id'] for s in registered['sources'] if s.get('format') != 'menus_csv'],
                  registration_updated=False, wiki_data_updated=False, publishing_performed=False)
    out.mkdir(parents=True)
    if issues:
        (out / 'report.json').write_bytes(json_bytes(report))
        return report
    staged.update({'provenance.json': ledger_blob, 'native-definitions.json': defs_blob,
                   'native-references.json': refs_blob, 'text-sources-candidate.json': json_bytes(candidate)})
    for file, blob in staged.items():
        path = out / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    (out / 'report.json').write_bytes(json_bytes(report))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', required=True, help='Fresh directory inside evidence/asset-import/native/ or dist/')
    parser.add_argument('--index', default=DEFAULT_INDEX)
    args = parser.parse_args(argv)
    try:
        report = build(args.root, args.output, args.index)
        print(json.dumps({k: report[k] for k in ('status', 'selected_definition_files', 'parsed_definition_files', 'issues')},
                         ensure_ascii=False))
        return 2 if report['issues'] else 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        code = error.code if isinstance(error, TextError) else str(error) if isinstance(error, ResourceError) else type(error).__name__
        print(json.dumps(dict(status='BLOCKED', code=code)))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
