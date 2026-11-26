"""Recover the four known AppResources tables without executing either application."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import struct
import zipfile

from .locations import SourceLocations

from .investigate import android_app_assemblies
from .static_formats import bundle_bytes, bundle_entries, managed_resource_bytes, seven_bit
from .text_library import ROOT, RESOURCE_NAMESPACE, TextError, json_document, local_file, require, sha256


PACKAGE_METADATA = 'dist/asset-import/package-metadata.json'
PARSER_RULE = 'dotnet_resources_v2_strings@1'


def _string(data, position, end, encoding):
    length, start = seven_bit(data, position)
    require(start + length <= end, 'TRUNCATED_RESOURCE_STRING')
    return data[start:start + length].decode(encoding), start + length, start


def resource_table(data):
    """Keep every name-table slot; non-String payloads are never deserialized."""
    require(len(data) >= 12, 'TRUNCATED_RESOURCE_HEADER')
    magic, header_version, skip = struct.unpack_from('<III', data)
    require(magic == 0xbeefcace and header_version == 1, 'UNSUPPORTED_RESOURCE_HEADER')
    position = 12 + skip
    require(position + 12 <= len(data), 'TRUNCATED_RESOURCE_HEADER')
    version, count, type_count = struct.unpack_from('<III', data, position)
    require(version == 2 and count <= 100000 and type_count <= 100000, 'UNSUPPORTED_RESOURCE_VERSION')
    position += 12
    for _ in range(type_count):
        _, position, _ = _string(data, position, len(data), 'utf-8')
    position = (position + 7) & ~7
    require(position + count * 8 + 4 <= len(data), 'TRUNCATED_RESOURCE_INDEX')
    name_hashes = struct.unpack_from('<' + 'i' * count, data, position)
    position += count * 4
    offsets = struct.unpack_from('<' + 'I' * count, data, position)
    position += count * 4
    data_start = struct.unpack_from('<I', data, position)[0]
    name_start = position + 4
    require(name_start <= data_start <= len(data), 'INVALID_RESOURCE_DATA_SECTION')
    records = []
    for index, offset in enumerate(offsets):
        row = dict(entry_index=index, key=None, text=None, status='parse_error',
                   name_hash=name_hashes[index], name_offset=name_start + offset)
        try:
            require(name_start <= row['name_offset'] < data_start, 'INVALID_RESOURCE_NAME_OFFSET')
            key, end, _ = _string(data, row['name_offset'], data_start, 'utf-16le')
            row['key'] = key
            require(end + 4 <= data_start, 'TRUNCATED_RESOURCE_NAME_ENTRY')
            relative = struct.unpack_from('<I', data, end)[0]
            row['data_offset'] = data_start + relative
            require(data_start <= row['data_offset'] < len(data), 'INVALID_RESOURCE_VALUE_OFFSET')
        except (ValueError, IndexError, struct.error) as error:
            row['error'] = error.code if isinstance(error, TextError) else 'INVALID_RESOURCE_NAME'
        records.append(row)
    starts = sorted({r['data_offset'] for r in records if 'error' not in r})
    ends = dict(zip(starts, starts[1:] + [len(data)]))
    for row in records:
        if 'error' in row:
            continue
        try:
            end = ends[row['data_offset']]
            code, position = seven_bit(data, row['data_offset'])
            require(position <= end, 'TRUNCATED_RESOURCE_TYPE')
            row.update(type_code=code, payload_sha256=sha256(data[row['data_offset']:end]))
            if code == 1:
                row['text'], position, row['value_offset'] = _string(data, position, end, 'utf-8')
                row.update(status='string', value_end=position, trailing_bytes=end - position)
            else:
                row['status'] = 'null' if code == 0 else 'non_string'
        except (ValueError, IndexError, struct.error) as error:
            row['error'] = error.code if isinstance(error, TextError) else 'INVALID_RESOURCE_VALUE'
    keys = defaultdict(list)
    for row in records:
        if isinstance(row['key'], str):
            keys[row['key']].append(row['entry_index'])
    duplicate_keys = [dict(key=k, entries=v) for k,v in keys.items() if len(v) > 1]
    statuses = Counter(r['status'] for r in records)
    stats = dict(declared_entries=count, decoded_keys=sum(isinstance(r['key'], str) for r in records),
                 unique_keys=len(keys), string_values=statuses['string'], null_values=statuses['null'],
                 non_string_values=statuses['non_string'], parse_errors=statuses['parse_error'],
                 duplicate_key_groups=len(duplicate_keys), type_codes=dict(Counter(str(r['type_code']) for r in records if 'type_code' in r)),
                 empty_strings=sum(r['status'] == 'string' and r['text'] == '' for r in records),
                 trailing_bytes=sum(r.get('trailing_bytes', 0) for r in records))
    return dict(records=records, stats=stats, duplicate_keys=duplicate_keys)


def _write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def extract(root, output):
    root = Path(root).resolve()
    locations = SourceLocations(root)
    out = local_file(root, output)
    require(not out.exists() and out.parent.is_dir(), 'OUTPUT_MUST_BE_FRESH')
    out.mkdir()
    inputs = {}

    def read(name):
        data = locations.resolve(local_file(root, name)).read_bytes()
        reference = dict(file=name, sha256=sha256(data), bytes=len(data))
        if name in inputs:
            require(inputs[name] == reference, 'INPUT_CHANGED_DURING_EXTRACTION')
        inputs[name] = reference
        return data

    packages = json_document(read(PACKAGE_METADATA))
    tables, table_evidence, failures = [], [], []
    for platform in ('apk', 'windows'):
        package = packages[platform]
        try:
            binary = read(package['relative_path'])
            require(sha256(binary) == package['sha256'], 'PACKAGE_HASH_MISMATCH')
            if platform == 'apk':
                with zipfile.ZipFile(locations.resolve(local_file(root, package['relative_path']))) as archive:
                    assemblies = android_app_assemblies(archive)
            else:
                _, entries = bundle_entries(binary)
                assemblies = [(e['source_entry'], bundle_bytes(binary, e), e) for e in entries
                              if e['source_entry'] in ('Division2BuildTool.dll', 'en/Division2BuildTool.resources.dll')]
            require(len(assemblies) == 2, 'TARGET_ASSEMBLY_MISSING')
        except (OSError, ValueError, KeyError, IndexError, struct.error, zipfile.BadZipFile) as error:
            failures.append(dict(platform=platform, code=str(error) if isinstance(error, TextError) else type(error).__name__))
            continue
        for name, assembly, location in assemblies:
            culture = 'en' if name.startswith('en/') else 'neutral'
            try:
                metadata_file = 'dist/asset-import/' + platform + ('-en' if culture == 'en' else '') + '-managed-metadata.json'
                metadata = json_document(read(metadata_file))
                old = next(r for r in package['assembly_sources'] if r['source_entry'] == location['source_entry']
                           and (r.get('name') == name if platform == 'apk' else True))
                require(sha256(assembly) == (old['decoded_sha256'] if platform == 'apk' else old['sha256']),
                        'ASSEMBLY_HASH_MISMATCH')
                resource_name = RESOURCE_NAMESPACE + ('.en.resources' if culture == 'en' else '.resources')
                resource = next(r for r in metadata['resources'] if r['name'] == resource_name and r['embedded'])
                blob = managed_resource_bytes(assembly, metadata, resource)
                old_resource = next(r for r in old['resource_streams'] if r['name'] == resource_name)
                require(sha256(blob) == old_resource['sha256'] and len(blob) == old_resource['size'], 'RESOURCE_HASH_MISMATCH')
                relative = 'resources/' + platform + '/' + culture + '/' + resource_name
                _write_new(out / relative, blob)
                decoded = resource_table(blob)
                index = len(table_evidence)
                table_evidence.append(dict(platform=platform, culture=culture, resource_name=resource_name,
                    resource_sha256=sha256(blob), resource_bytes=len(blob), stats=decoded['stats'],
                    duplicate_keys=decoded['duplicate_keys'],
                    raw_resource=dict(file=(out / relative).relative_to(root).as_posix(), sha256=sha256(blob), bytes=len(blob)),
                    package=inputs[package['relative_path']], assembly=dict(location, name=name, decoded_sha256=sha256(assembly)),
                    metadata=inputs[metadata_file], resource_directory_rva=metadata['resources_directory_rva'],
                    manifest_resource=resource, package_metadata_pointer='/' + platform,
                    application_version=(package.get('metadata') or {}).get('versionName') or package.get('assembly_version'),
                    game_version=None))
                tables.append(dict(platform=platform, culture=culture, resource_name=resource_name,
                    resource_sha256=sha256(blob), evidence_pointer='/tables/' + str(index), records=decoded['records']))
            except (OSError, ValueError, KeyError, IndexError, StopIteration, struct.error) as error:
                failures.append(dict(platform=platform, culture=culture,
                    code=error.code if isinstance(error, TextError) else type(error).__name__))
        del binary
    for reference in inputs.values():
        require(sha256(locations.resolve(local_file(root, reference['file'])).read_bytes()) == reference['sha256'], 'INPUT_CHANGED_DURING_EXTRACTION')
    data = dict(schema_version=1, parser_rule=PARSER_RULE, tables=tables, failures=failures)
    _write_new(out / 'strings.json', _json_bytes(data))
    manifest = dict(schema_version=1, parser_rule=PARSER_RULE, inputs=list(inputs.values()), tables=table_evidence,
                    failures=failures, inputs_unchanged=True,
                    output=dict(file=(out / 'strings.json').relative_to(root).as_posix(),
                                sha256=sha256((out / 'strings.json').read_bytes())),
                    scope='Only the four known embedded AppResources tables; no application execution or arbitrary object deserialization.')
    _write_new(out / 'extraction.json', _json_bytes(manifest))
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', required=True, help='New repository-relative directory; parent must exist')
    args = parser.parse_args(argv)
    try:
        result = extract(args.root, args.output)
        print(json.dumps(dict(tables=[dict(platform=t['platform'], culture=t['culture'], **t['stats'])
                                           for t in result['tables']], failures=result['failures']), ensure_ascii=False, indent=2))
        return 2 if result['failures'] or any(t['stats']['parse_errors'] for t in result['tables']) else 0
    except (OSError, ValueError, KeyError, struct.error) as error:
        print(json.dumps(dict(error=error.code if isinstance(error, TextError) else type(error).__name__)))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
