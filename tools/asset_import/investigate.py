"""Phase A: inventory exact packages and inspect only selected managed types."""
import argparse
import base64
from collections import Counter
import json
from pathlib import Path, PurePosixPath
import struct
import subprocess
import zipfile

from .static_formats import (IMAGE_EXTENSIONS, android_manifest, android_resource_paths,
    bundle_entries, bundle_bytes, dib_icon_metadata, image_metadata, managed_resource_bytes, pe_info, pe_image_resources,
    resource_strings, safe_relative, sha256, write_source)

SELECTOR = (r'^Division2BuildTool\.Model\.(AppData|Attribute|NamedAttribute|Mod|Brand|HighendBrand|GearsetBrand|'
            r'Talent|GearsetTalent|NamedTalent|ExoticTalent|SpecialTalent|Gear|HighendGear|GearsetGear|Skill|Specialization)$|'
            r'^Division2BuildTool\.Blazor\.Component\.(BrandDisplay|TalentDisplay)$|'
            r'^Division2BuildTool\.Converters\.ImageSourceConverter$')


def version_tuple(value):
    parts = tuple(int(p) for p in value.split('+')[0].split('.'))
    while len(parts) > 1 and parts[-1] == 0:
        parts = parts[:-1]
    return parts


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def inspect_managed(root, out, data, label, pwsh):
    output = out / (label + '-managed-metadata.json')
    command = [str(pwsh), '-NoProfile', '-File', str(root / 'tools/asset_import/inspect-managed.ps1'),
               '-Base64Stdin', '-Selector', SELECTOR, '-OutputFile', str(output)]
    subprocess.run(command, input=base64.b64encode(data), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    metadata = json.loads(output.read_text(encoding='utf-8-sig'))
    dump(output, metadata)
    return metadata


def lz4_block(data, expected):
    """Xamarin XALZ uses a raw LZ4 block; copy only into memory."""
    out = bytearray(); pos = 0
    def extra(length):
        nonlocal pos
        if length == 15:
            while True:
                byte = data[pos]; pos += 1; length += byte
                if byte != 255:
                    break
        return length
    while pos < len(data):
        token = data[pos]; pos += 1
        count = extra(token >> 4)
        if pos + count > len(data) or len(out) + count > expected:
            raise ValueError('INVALID_LZ4')
        out.extend(data[pos:pos + count]); pos += count
        if pos == len(data):
            break
        offset = struct.unpack_from('<H', data, pos)[0]; pos += 2
        count = extra(token & 15) + 4
        if not offset or offset > len(out) or len(out) + count > expected:
            raise ValueError('INVALID_LZ4')
        for _ in range(count):
            out.append(out[-offset])
    if len(out) != expected:
        raise ValueError('LZ4_SIZE_MISMATCH')
    return bytes(out)


def android_app_assemblies(z):
    """Legacy XABA v1 descriptor offsets are proven by the exact manifest."""
    names = []
    for line in z.read('assemblies/assemblies.manifest').decode().splitlines()[1:]:
        fields = line.split()
        if len(fields) == 5 and fields[4] in ('Division2BuildTool', 'en/Division2BuildTool.resources'):
            names.append((int(fields[2]), int(fields[3]), fields[4]))
    data = z.read('assemblies/assemblies.blob')
    magic, version, count, global_count, store_id = struct.unpack_from('<IIIII', data)
    if magic != 0x41424158 or version != 1:
        raise ValueError('NEEDS_ADDITIONAL_TOOL: unsupported Android assembly store')
    result = []
    for blob, index, name in names:
        if blob != store_id or index >= count:
            raise ValueError('INVALID_ASSEMBLY_STORE_INDEX')
        offset, size = struct.unpack_from('<II', data, 20 + 24 * index)
        source = data[offset:offset + size]
        if len(source) != size:
            raise ValueError('TRUNCATED_ASSEMBLY_STORE')
        decoded = lz4_block(source[12:], struct.unpack_from('<I', source, 8)[0]) if source[:4] == b'XALZ' else source
        if decoded[:2] != b'MZ':
            raise ValueError('NOT_ASSEMBLY')
        result.append((name, decoded, dict(source_entry='assemblies/assemblies.blob', manifest_entry='assemblies/assemblies.manifest',
                       blob_index=index, offset=offset, size=size, source_sha256=sha256(source), decoded_sha256=sha256(decoded),
                       extraction_method='XABA v1 manifest index + bounded descriptor; XALZ raw LZ4 decoded in memory')))
    return result


def image_record(platform, name, data, out, source_package, android=None, container=None):
    ext = PurePosixPath(name).suffix.lower()
    record = dict(source_asset_id=platform + ':' + sha256(name.encode())[:20], source_platform=platform,
        source_package=source_package, source_entry=name, filename=PurePosixPath(name).name, extension=ext,
        size=len(data), sha256=sha256(data), resource_container_type=container or ('APK ZIP entry' if platform == 'apk' else '.NET bundle entry'),
        extraction_method='ZIP decompression, bytes unchanged' if platform == 'apk' else 'static .NET bundle offset, bytes unchanged',
        android_resources=android or [], android_resource_id=(android or [{}])[0].get('id'),
        android_resource_name=(android or [{}])[0].get('name'), embedded_resource_owner=None,
        internal_resource_key=name[7:] if name.startswith('assets/') else name)
    if ext == '.svg':
        record.update(width=None, height=None, color_mode=None, alpha=None, transparency=None, pixel_hash=None, source_format='SVG', frame_count=None)
    else:
        try:
            record.update(dib_icon_metadata(data) if ext == '.dib' else image_metadata(data))
        except Exception as exc:
            record.update(width=None, height=None, color_mode=None, alpha=None, transparency=None, pixel_hash=None,
                          source_format=ext[1:].upper(), decode_error=type(exc).__name__)
    record['raw_path'] = 'raw/' + platform + '/' + name
    write_source(out / 'raw' / platform, name, data)
    return record


def resolve_inputs(root, out, inputs):
    """Require both explicit packages and keep source files outside the extraction output."""
    if not isinstance(inputs, dict) or set(inputs) != {'apk', 'windows'}:
        raise ValueError('EXPLICIT_PACKAGE_INPUTS_REQUIRED')
    resolved = {}
    for platform, value in inputs.items():
        path = (root / value).resolve()
        if not path.is_file():
            raise ValueError('EXPECTED_INPUT_MISSING: ' + str(path))
        if path.is_relative_to(out.resolve()):
            raise ValueError('PACKAGE_INPUT_OVERLAPS_OUTPUT')
        resolved[platform] = path.relative_to(root.resolve()).as_posix() if path.is_relative_to(root.resolve()) else str(path)
    if resolved['apk'] == resolved['windows']:
        raise ValueError('PACKAGE_INPUTS_MUST_BE_DISTINCT')
    return resolved


def investigate(root, out, pwsh, inputs):
    inputs = resolve_inputs(root, out, inputs)
    out.mkdir(parents=True, exist_ok=True)
    for platform in inputs:
        (out / 'raw' / platform).mkdir(parents=True, exist_ok=True)
    before = {key: sha256((root / value).read_bytes()) for key, value in inputs.items()}
    package = {}; inventories = {}; localizations = {}; managed = {}; skipped_strings = 0
    with zipfile.ZipFile(root / inputs['apk']) as z:
        package['apk'] = dict(relative_path=inputs['apk'], absolute_path=str(root / inputs['apk']),
            filename=Path(inputs['apk']).name, size=(root / inputs['apk']).stat().st_size, sha256=before['apk'],
            file_signature='PK ZIP/APK', metadata=android_manifest(z.read('AndroidManifest.xml')),
            structure=dict(entries=len(z.infolist()), prefixes=dict(Counter(n.split('/')[0] for n in z.namelist()))))
        arsc = android_resource_paths(z.read('resources.arsc'))
        dump(out / 'android-resource-map.json', arsc)
        write_source(out / 'raw/apk', 'AndroidManifest.xml', z.read('AndroidManifest.xml'))
        # Resource table is inspected in memory: may contain unrelated configuration strings.
        package['apk']['resource_table'] = dict(source_entry='resources.arsc', sha256=sha256(z.read('resources.arsc')), image_path_mappings=len(arsc), retained=False)
        inventories['apk'] = [image_record('apk', i.filename, z.read(i), out, inputs['apk'], arsc.get(i.filename))
                              for i in sorted(z.infolist(), key=lambda i: i.filename) if PurePosixPath(i.filename).suffix.lower() in IMAGE_EXTENSIONS]
        assembly_sources = []
        for name, data, provenance in android_app_assemblies(z):
            label = 'apk' if name == 'Division2BuildTool' else 'apk-en'
            info = inspect_managed(root, out, data, label, pwsh)
            assembly_sources.append(dict(name=name, metadata=dict(assembly_version=info['assembly_version'], resources=info['resources']), **provenance))
            if label == 'apk':
                managed['apk'] = info
            for resource in info['resources']:
                stream = managed_resource_bytes(data, info, resource)
                if resource['name'].endswith('.resources'):
                    localizations[label], skipped = resource_strings(stream, with_stats=True)
                    skipped_strings += skipped
                assembly_sources[-1].setdefault('resource_streams', []).append(dict(name=resource['name'], offset=resource['offset'], size=len(stream), sha256=sha256(stream), extraction_method='PE CLI ManifestResource directory; string-only resources reader', retained=False))
        package['apk']['assembly_sources'] = assembly_sources
        package['apk']['skipped_unrelated_data'] = '内置配装样例与赞助者记录包含任务无关数据，未提取、未保存、未输出值。'
    exe = (root / inputs['windows']).read_bytes()
    bundle, entries = bundle_entries(exe)
    package['windows'] = dict(relative_path=inputs['windows'], absolute_path=str(root / inputs['windows']), filename=Path(inputs['windows']).name,
        size=len(exe), sha256=before['windows'], file_signature='MZ / PE', pe=pe_info(exe), bundle=bundle)
    inventories['windows'] = []; structure = []
    for entry in entries:
        name = entry['source_entry']; data = bundle_bytes(exe, entry)
        structure.append(dict(entry, sha256=sha256(data)))
        if PurePosixPath(name).suffix.lower() in IMAGE_EXTENSIONS:
            inventories['windows'].append(image_record('windows', name, data, out, inputs['windows']))
        elif name in ('Division2BuildTool.dll', 'en/Division2BuildTool.resources.dll'):
            label = 'windows' if name == 'Division2BuildTool.dll' else 'windows-en'
            info = inspect_managed(root, out, data, label, pwsh)
            if label == 'windows':
                managed['windows'] = info
                package['windows']['assembly_version'] = info['assembly_version']
                package['windows']['assembly_references'] = info['references']
            streams = []
            for resource in info['resources']:
                stream = managed_resource_bytes(data, info, resource)
                if resource['name'].endswith('.resources'):
                    localizations[label], skipped = resource_strings(stream, with_stats=True)
                    skipped_strings += skipped
                streams.append(dict(name=resource['name'], offset=resource['offset'], size=len(stream), sha256=sha256(stream), retained=False))
            package['windows'].setdefault('assembly_sources', []).append(dict(entry, sha256=sha256(data), resource_streams=streams))
        elif name == 'Division2BuildTool.runtimeconfig.json':
            config = json.loads(data)
            runtime = config['runtimeOptions']
            package['windows']['runtime'] = {k: runtime[k] for k in ('tfm', 'framework', 'frameworks', 'includedFrameworks') if k in runtime}
    host_images = pe_image_resources(exe)
    for entry in host_images:
        row = image_record('windows', entry['source_entry'], entry['data'], out, inputs['windows'], container='PE RT_ICON / RT_BITMAP')
        row.update(extraction_method='static PE resource directory and RVA; raw bytes unchanged',
                   source_byte_offset=entry['offset'], pe_resource_type=entry['resource_type'])
        inventories['windows'].append(row)
    package['windows']['pe_image_resource_count'] = len(host_images)
    package['windows']['maui'] = any('Microsoft.Maui' in e['source_entry'] for e in entries)
    package['windows']['self_contained'] = any(e['source_entry'] == 'System.Private.CoreLib.dll' for e in entries)
    names = {e['source_entry'] for e in entries}
    package['windows']['missing_external_dependencies'] = [ref + '.dll' for ref in package['windows']['assembly_references'] if ref + '.dll' not in names and not (root / inputs['windows']).parent.joinpath(ref + '.dll').is_file()]
    # Query only PE version data via PowerShell, without launching the application.
    ps = "(Get-Item -LiteralPath '" + str(root / inputs['windows']).replace("'", "''") + "').VersionInfo | Select-Object ProductName,ProductVersion,FileVersion | ConvertTo-Json -Compress"
    version = json.loads(subprocess.check_output([str(pwsh), '-NoProfile', '-Command', ps]).decode('utf-8-sig'))
    package['windows']['version_info'] = version
    av = package['apk']['metadata']['versionName']; wv = version['ProductVersion'].split('+')[0]
    package['version_relationship'] = 'exact' if av == wv and version_tuple(package['windows']['assembly_version']) == version_tuple(av) else 'different'
    package['skipped_unrelated_strings'] = skipped_strings
    after = {key: sha256((root / value).read_bytes()) for key, value in inputs.items()}
    if before != after:
        raise ValueError('IMMUTABLE_INPUT_CHANGED')
    package['immutable_verification'] = {key: dict(before=before[key], after=after[key], unchanged=True) for key in inputs}
    for key, values in inventories.items():
        dump(out / (key + '-inventory.json'), dict(schema_version=1, source_package=package[key], images=sorted(values, key=lambda r: r['source_entry'])))
    dump(out / 'bundle-inventory.json', dict(schema_version=1, bundle=bundle, entries=structure))
    dump(out / 'package-metadata.json', package)
    # Only game keys that will be referenced in evidence are exported in Phase B.
    return package, inventories, managed, localizations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='dist/asset-import')
    parser.add_argument('--pwsh', required=True)
    parser.add_argument('--apk', required=True)
    parser.add_argument('--windows', required=True)
    args = parser.parse_args(); root = Path.cwd(); out = root / args.output
    if (root / 'dist/asset-import').resolve() not in (out.resolve(), *out.resolve().parents):
        raise ValueError('OUTPUT_MUST_BE_UNDER_ASSET_IMPORT')
    package, inventories, _, _ = investigate(root, out, args.pwsh, {'apk': args.apk, 'windows': args.windows})
    print(json.dumps(dict(versions=package['version_relationship'], images={k: len(v) for k, v in inventories.items()})))


if __name__ == '__main__':
    main()
