"""Bounded static readers; no target code, native loader or deserialization."""
import hashlib
import io
import json
from pathlib import PurePosixPath
import re
import struct
import zlib
from tools.publish.bundle import normalized_title_name

BUNDLE_MARKER = bytes.fromhex('8b1202b96a612038727b930214d7a03213f5b9e6efae3318ee3b2dce24b36aae')
SENSITIVE_NOTICE = '发现与任务无关的敏感配置，已跳过。'
IMAGE_EXTENSIONS = {'.png', '.webp', '.jpg', '.jpeg', '.svg', '.bmp', '.gif', '.ico'}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def safe_relative(name):
    if not isinstance(name, str) or not name or '\\' in name:
        raise ValueError('INVALID_PATH')
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in ('', '.', '..') for p in name.split('/')):
        raise ValueError('INVALID_PATH')
    for part in path.parts:
        if re.search(r'[\x00-\x1f<>:"|?*]', part) or part.endswith((' ', '.')):
            raise ValueError('INVALID_NAME')
        if re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?', part):
            raise ValueError('INVALID_NAME')
    return path


def write_source(base, name, data):
    path = base.joinpath(*safe_relative(name).parts)
    if base.resolve() not in path.resolve().parents:
        raise ValueError('OUTPUT_PATH_ESCAPE')
    for parent in (path,) + tuple(path.parents):
        if parent.is_symlink():
            raise ValueError('SYMLINK_OUTPUT')
        if parent == base:
            break
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError('OUTPUT_COLLISION')
    else:
        path.write_bytes(data)
    return path


def claim_filename(filename, pixel_hash, occupied):
    path = safe_relative(filename)
    if len(path.parts) != 1:
        raise ValueError('INVALID_NORMALIZED_FILENAME')
    folded = normalized_title_name(filename)
    if folded in occupied and occupied[folded] != (filename, pixel_hash):
        raise ValueError('NORMALIZED_FILENAME_COLLISION')
    occupied[folded] = (filename, pixel_hash)


def seven_bit(data, pos):
    value = 0
    for shift in range(0, 35, 7):
        byte = data[pos]; pos += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, pos
    raise ValueError('INVALID_LENGTH')


def net_string(data, pos, encoding='utf-8'):
    size, pos = seven_bit(data, pos)
    end = pos + size
    if end > len(data):
        raise ValueError('TRUNCATED_STRING')
    return data[pos:end].decode(encoding), end


def bundle_entries(data):
    marker = data.find(BUNDLE_MARKER)
    if marker < 8:
        return {'single_file': False}, []
    header = struct.unpack_from('<q', data, marker - 8)[0]
    major, minor, count = struct.unpack_from('<III', data, header)
    if major not in (1, 2, 6) or count > 100000:
        raise ValueError('UNSUPPORTED_BUNDLE')
    identifier, pos = net_string(data, header + 12)
    locations = struct.unpack_from('<qqqqQ', data, pos) if major >= 2 else None
    if locations:
        pos += 40
    entries = []; names = set()
    for _ in range(count):
        offset, size = struct.unpack_from('<qq', data, pos); pos += 16
        compressed = struct.unpack_from('<q', data, pos)[0] if major >= 6 else 0
        if major >= 6:
            pos += 8
        kind = data[pos]; pos += 1
        name, pos = net_string(data, pos)
        safe_relative(name)
        if name.casefold() in names or min(offset, size, compressed) < 0 or offset + (compressed or size) > header:
            raise ValueError('INVALID_BUNDLE_ENTRY')
        names.add(name.casefold())
        entries.append(dict(source_entry=name, offset=offset, size=size, compressed_size=compressed, bundle_type=kind))
    return dict(single_file=True, format_version=[major, minor], header_offset=header, entry_count=count,
                bundle_id=identifier, flags=locations[-1] if locations else 0), entries


def bundle_bytes(data, entry):
    offset = entry['offset']; size = entry['compressed_size'] or entry['size']
    value = data[offset:offset + size]
    if entry['compressed_size']:
        value = zlib.decompress(value, -15)
    if len(value) != entry['size']:
        raise ValueError('BUNDLE_SIZE_MISMATCH')
    return value


def pe_info(data):
    if data[:2] != b'MZ':
        raise ValueError('NOT_PE')
    offset = struct.unpack_from('<I', data, 0x3c)[0]
    if data[offset:offset + 4] != b'PE\0\0':
        raise ValueError('NOT_PE')
    machine, sections = struct.unpack_from('<HH', data, offset + 4)
    optional_size = struct.unpack_from('<H', data, offset + 20)[0]
    magic = struct.unpack_from('<H', data, offset + 24)[0]
    directories = offset + 24 + (112 if magic == 0x20b else 96)
    clr_rva, clr_size = struct.unpack_from('<II', data, directories + 14 * 8)
    resource_rva, resource_size = struct.unpack_from('<II', data, directories + 2 * 8)
    table = offset + 24 + optional_size
    segments = []
    for n in range(sections):
        p = table + n * 40
        virtual_size, rva, raw_size, raw_offset = struct.unpack_from('<IIII', data, p + 8)
        segments.append(dict(rva=rva, virtual_size=virtual_size, raw_size=raw_size, raw_offset=raw_offset))
    return dict(type='PE32+' if magic == 0x20b else 'PE32', architecture={0x8664: 'x64', 0x14c: 'x86', 0xaa64: 'arm64'}.get(machine, hex(machine)),
                managed=bool(clr_rva), clr_rva=clr_rva, clr_size=clr_size,
                resource_rva=resource_rva, resource_size=resource_size, sections=segments)


def rva_offset(data, rva):
    for section in pe_info(data)['sections']:
        if section['rva'] <= rva < section['rva'] + section['raw_size']:
            return section['raw_offset'] + rva - section['rva']
    raise ValueError('UNMAPPED_RVA')


def managed_resource_bytes(data, metadata, resource):
    p = rva_offset(data, metadata['resources_directory_rva']) + resource['offset']
    length = struct.unpack_from('<I', data, p)[0]
    if p + 4 + length > len(data):
        raise ValueError('TRUNCATED_MANAGED_RESOURCE')
    return data[p + 4:p + 4 + length]


def pe_image_resources(data):
    info = pe_info(data)
    if not info['resource_rva']:
        return []
    base = rva_offset(data, info['resource_rva']); result = []
    def walk(offset, parents):
        if len(parents) > 3:
            raise ValueError('INVALID_PE_RESOURCE_TREE')
        p = base + offset
        named, ids = struct.unpack_from('<HH', data, p + 12)
        for n in range(named + ids):
            name, value = struct.unpack_from('<II', data, p + 16 + n * 8)
            if name & 0x80000000:
                q = base + (name & 0x7fffffff)
                length = struct.unpack_from('<H', data, q)[0]
                name = data[q + 2:q + 2 + 2 * length].decode('utf-16le')
            path = parents + [str(name)]
            if value & 0x80000000:
                walk(value & 0x7fffffff, path)
            elif path[0] in ('2', '3'):  # RT_BITMAP / RT_ICON; no unrelated resource values
                rva, size = struct.unpack_from('<II', data, base + value)
                raw_offset = rva_offset(data, rva)
                raw = data[raw_offset:raw_offset + size]
                ext = '.png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else '.dib'
                result.append(dict(source_entry='pe-resources/' + '/'.join(path) + ext, resource_type=path[0],
                                   offset=raw_offset, size=size, data=raw))
    walk(0, [])
    return result


def dib_icon_metadata(data):
    # A wrapped ICO is used only in memory for decoding; raw DIB bytes stay unchanged.
    header, width, doubled_height, planes, bits = struct.unpack_from('<IiiHH', data)
    width = abs(width); height = abs(doubled_height) // 2
    if not (0 < width <= 256 and 0 < height <= 256) or header < 40:
        raise ValueError('UNSUPPORTED_DIB')
    ico = struct.pack('<HHHBBBBHHII', 0, 1, 1, width % 256, height % 256, 0, 0, planes, bits, len(data), 22) + data
    metadata = image_metadata(ico); metadata['source_format'] = 'DIB'
    return metadata


def resource_strings(data, with_stats=False):
    """Read only ResourceTypeCode.String; never instantiate serialized objects."""
    magic, header_version, skip = struct.unpack_from('<III', data)
    if magic != 0xbeefcace or header_version != 1:
        raise ValueError('UNSUPPORTED_RESOURCES')
    p = 12 + skip
    version, count, types = struct.unpack_from('<III', data, p); p += 12
    if version != 2 or count > 100000:
        raise ValueError('UNSUPPORTED_RESOURCES')
    for _ in range(types):
        _, p = net_string(data, p)
    p = (p + 7) & ~7
    p += count * 4  # name hashes
    offsets = struct.unpack_from('<' + 'I' * count, data, p); p += count * 4
    data_start = struct.unpack_from('<I', data, p)[0]; p += 4
    name_start = p; result = {}; skipped = 0
    for offset in offsets:
        name, q = net_string(data, name_start + offset, 'utf-16le')
        value_offset = struct.unpack_from('<I', data, q)[0]
        code, q = seven_bit(data, data_start + value_offset)
        if code == 1:
            value, _ = net_string(data, q)
            if re.search(r'https?://|password|secret|token|api.?key|private.?key|credential|BEGIN .*KEY', name + ' ' + value, re.I):
                skipped += 1
                continue
            result[name] = value
    return (result, skipped) if with_stats else result


def string_pool(data, start):
    _, header, _ = struct.unpack_from('<HHI', data, start)
    count, _, flags, strings_start, _ = struct.unpack_from('<IIIII', data, start + 8)
    offsets = struct.unpack_from('<' + 'I' * count, data, start + header)
    def length(p, utf8):
        if utf8:
            n = data[p]; p += 1
            if n & 128:
                n = ((n & 127) << 8) | data[p]; p += 1
        else:
            n = struct.unpack_from('<H', data, p)[0]; p += 2
            if n & 0x8000:
                n = ((n & 0x7fff) << 16) | struct.unpack_from('<H', data, p)[0]; p += 2
        return n, p
    result = []
    for offset in offsets:
        p = start + strings_start + offset
        if flags & 0x100:
            _, p = length(p, True); n, p = length(p, True)
            result.append(data[p:p + n].decode('utf-8'))
        else:
            n, p = length(p, False)
            result.append(data[p:p + n * 2].decode('utf-16le'))
    return result


def chunks(data, start, end):
    while start < end:
        kind, header, size = struct.unpack_from('<HHI', data, start)
        if header < 8 or size < header or start + size > end:
            raise ValueError('INVALID_ANDROID_CHUNK')
        yield start, kind, header, size
        start += size


def android_manifest(data):
    result = {}; pool = []
    for p, kind, header, size in chunks(data, 8, len(data)):
        if kind == 1:
            pool = string_pool(data, p)
        elif kind == 0x102:
            tag = pool[struct.unpack_from('<I', data, p + 20)[0]]
            attr_start, attr_size, attr_count = struct.unpack_from('<HHH', data, p + 24)
            attrs = {}
            for n in range(attr_count):
                q = p + 16 + attr_start + attr_size * n
                _, name, raw = struct.unpack_from('<III', data, q)
                value_type = data[q + 15]; value = struct.unpack_from('<I', data, q + 16)[0]
                attrs[pool[name]] = pool[raw] if raw != 0xffffffff else pool[value] if value_type == 3 else value
            if tag == 'manifest':
                result.update({k: attrs.get(k) for k in ('package', 'versionName', 'versionCode')})
            elif tag == 'uses-sdk':
                result.update({k: attrs.get(k) for k in ('minSdkVersion', 'targetSdkVersion')})
    return result


def android_resource_paths(data):
    global_pool = []; result = {}
    for p, kind, header, size in chunks(data, 12, len(data)):
        if kind == 1:
            global_pool = string_pool(data, p)
        elif kind == 0x200:
            package_id = struct.unpack_from('<I', data, p + 8)[0]
            type_pool = string_pool(data, p + struct.unpack_from('<I', data, p + 268)[0])
            key_pool = string_pool(data, p + struct.unpack_from('<I', data, p + 276)[0])
            type_offset = struct.unpack_from('<I', data, p + 284)[0] if header >= 288 else 0
            for q, subkind, subheader, subsize in chunks(data, p + header, p + size):
                if subkind != 0x201:
                    continue
                type_id, flags = struct.unpack_from('<BB', data, q + 8)
                count, entries_start = struct.unpack_from('<II', data, q + 12)
                if flags & 1:
                    offsets = [(struct.unpack_from('<H', data, q + subheader + i * 4)[0], struct.unpack_from('<H', data, q + subheader + i * 4 + 2)[0] * 4) for i in range(count)]
                elif flags & 2:
                    offsets = [(i, o * 4) for i, o in enumerate(struct.unpack_from('<' + 'H' * count, data, q + subheader)) if o != 0xffff]
                else:
                    offsets = [(i, o) for i, o in enumerate(struct.unpack_from('<' + 'I' * count, data, q + subheader)) if o != 0xffffffff]
                for index, offset in offsets:
                    r = q + entries_start + offset
                    entry_size, entry_flags, key = struct.unpack_from('<HHI', data, r)
                    if entry_flags & 1:
                        continue  # bags do not directly map image paths
                    value_type = data[r + entry_size + 3]
                    value = struct.unpack_from('<I', data, r + entry_size + 4)[0]
                    if value_type == 3 and value < len(global_pool):
                        path = global_pool[value]
                        if path.startswith(('res/', 'assets/')):
                            row = dict(id='0x%08x' % ((package_id << 24) | ((type_id + type_offset) << 16) | index), name=type_pool[type_id - 1] + '/' + key_pool[key])
                            if row not in result.setdefault(path, []):
                                result[path].append(row)
    return {k: sorted(v, key=lambda r: (r['id'], r['name'])) for k, v in result.items()}


def image_metadata(data):
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        width, height = image.size; mode = image.mode
        icon_sizes = sorted(image.ico.sizes()) if image.format == 'ICO' else None
        frames = len(icon_sizes) if icon_sizes else getattr(image, 'n_frames', 1)
        digest = hashlib.sha256(b'TD2-RGBA8-v1\0' + struct.pack('<III', width, height, frames))
        alpha_channel = 'A' in image.getbands() or 'transparency' in image.info
        transparency = False
        for n in range(frames):
            if icon_sizes:
                frame = image.ico.getimage(icon_sizes[n])
            else:
                image.seek(n); frame = image
            rgba = frame.convert('RGBA')
            alpha_channel |= 'A' in frame.getbands() or 'transparency' in frame.info
            transparency |= rgba.getchannel('A').getextrema()[0] < 255
            digest.update(struct.pack('<III', *rgba.size, int(image.info.get('duration', 0)) if frames > 1 else 0))
            digest.update(rgba.tobytes())
        return dict(width=width, height=height, color_mode=mode, alpha=alpha_channel,
                    transparency=transparency, frame_count=frames, source_format=image.format,
                    pixel_hash=digest.hexdigest(), pixel_hash_representation='TD2-RGBA8-v1; little-endian dimensions/frame count; each full RGBA8 frame + duration; no EXIF transform')
