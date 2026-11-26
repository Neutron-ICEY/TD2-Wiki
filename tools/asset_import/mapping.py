"""Recover literal constructor bindings with verified Name/Image argument flow.

This is a bounded backwards IL expression reader, not a CLR or an application
interpreter. Unsupported expressions stay unresolved rather than being guessed.
"""
from collections import defaultdict
from pathlib import PurePosixPath
import re

from .static_formats import seven_bit, sha256

MODEL = 'Division2BuildTool.Model.'
ROLES = {
    'Attribute': ('attribute', 1, 0), 'NamedAttribute': ('attribute', 1, 0),
    'Mod': ('mod', 1, 0), 'HighendBrand': ('brand', 0, 1), 'GearsetBrand': ('gear_set', 0, 1),
    'Talent': ('talent', 1, 2), 'GearsetTalent': ('talent', 0, 1),
    'NamedTalent': ('talent', 0, 1), 'ExoticTalent': ('talent', 0, 1), 'SpecialTalent': ('talent', 1, 2),
}


def signature_shape(signature):
    data = bytes.fromhex(signature)
    if not data:
        raise ValueError('MISSING_SIGNATURE')
    pos = 1
    if data[0] & 0x10:
        _, pos = seven_bit(data, pos)
    count, pos = seven_bit(data, pos)
    return count, bool(data[0] & 0x20), data[pos] == 1


def expression(il, end, depth=0):
    if end < 0 or depth > 32:
        raise ValueError('UNRESOLVED_EXPRESSION')
    item = il[end]; op = item['opcode']; value = item['operand']
    if op == 'ldstr':
        return dict(kind='literal', value=value, offsets=[item['offset']]), end - 1
    if op.startswith('ldc.i4.'):
        val = value if op == 'ldc.i4.s' else -1 if op == 'ldc.i4.m1' else int(op.rsplit('.', 1)[-1])
        return dict(kind='literal', value=val, offsets=[item['offset']]), end - 1
    if op in ('ldc.i4', 'ldc.i8', 'ldc.r4', 'ldc.r8', 'ldnull'):
        return dict(kind='literal', value=value, offsets=[item['offset']]), end - 1
    if op.startswith(('ldloc', 'ldarg')) or op in ('ldsfld', 'ldtoken'):
        return dict(kind='reference', value=value, offsets=[item['offset']]), end - 1
    if op in ('newobj', 'call', 'callvirt'):
        count, instance, void = signature_shape(value['signature'])
        if void and op != 'newobj':
            raise ValueError('VOID_NOT_EXPRESSION')
        if op != 'newobj' and instance:
            count += 1
        args = []; cursor = end - 1
        for _ in range(count):
            arg, cursor = expression(il, cursor, depth + 1); args.append(arg)
        args.reverse()
        return dict(kind='constructor' if op == 'newobj' else 'call', name=value['name'], args=args,
                    offsets=sorted([item['offset']] + [n for arg in args for n in arg['offsets']])), cursor
    raise ValueError('UNRESOLVED_EXPRESSION: ' + op)


def arg_index(item):
    op = item['opcode']
    if op.startswith('ldarg.') and op != 'ldarg.s':
        return int(op.rsplit('.', 1)[-1])
    return item['operand'] if op in ('ldarg.s', 'ldarg') else None


def constructor_contracts(metadata):
    types = {t['name']: t for t in metadata['types']}
    contracts = {}
    for name, (category, name_pos, image_pos) in ROLES.items():
        t = types.get(MODEL + name)
        if not t:
            continue
        ctor = next((m for m in t['methods'] if m['name'] == '.ctor' and m['il']), None)
        if not ctor:
            continue
        il = ctor['il']; name_arg = name_pos + 1; image_arg = image_pos + 1
        if name in ('Talent', 'Attribute'):
            name_ok = any(i['opcode'] == 'stfld' and i['operand']['name'].endswith('::Name') and j > 0 and arg_index(il[j - 1]) == name_arg for j, i in enumerate(il))
            image_ok = any(i['opcode'] == 'call' and i['operand']['name'].endswith('::set_Image') and j > 0 and arg_index(il[j - 1]) == image_arg for j, i in enumerate(il))
            verified = name_ok and image_ok
        else:
            parent = 'Brand' if category in ('brand', 'gear_set') else 'Attribute' if category in ('attribute', 'mod') else 'Talent'
            call = next((j for j, i in enumerate(il) if i['opcode'] == 'call' and i['operand']['name'] == MODEL + parent + '::.ctor'), None)
            verified = call is not None
            if verified:
                # Verify the actual forwarding sequence, including Talent Save=0.
                count, _, _ = signature_shape(il[call]['operand']['signature'])
                args = il[call - count:call]
                if parent == 'Brand':
                    verified = [arg_index(i) for i in args[:2]] == [1, 2]
                    parent_ctor = next(m for m in types[MODEL + 'Brand']['methods'] if m['name'] == '.ctor')
                    parent_il = parent_ctor['il']
                    verified &= any(i['opcode'] == 'stfld' and i['operand']['name'].endswith('::Name') and arg_index(parent_il[j - 1]) == 1 for j, i in enumerate(parent_il))
                    verified &= any(i['opcode'] == 'call' and i['operand']['name'].endswith('::set_Image') and arg_index(parent_il[j - 1]) == 2 for j, i in enumerate(parent_il))
                elif parent == 'Talent':
                    verified = ([arg_index(i) for i in args[:3]] == [1, 2, 3] if name == 'SpecialTalent'
                                else args[0]['opcode'] == 'ldc.i4.0' and [arg_index(i) for i in args[1:3]] == [1, 2])
                else:
                    verified = [arg_index(i) for i in args[:2]] == [1, 2]
                verified &= parent == 'Brand' or contracts.get(parent, {}).get('verified', False)
        contracts[name] = dict(category=category, name_argument=name_arg, image_argument=image_arg,
                               verified=bool(verified), constructor_token=ctor['token'], constructor_type=MODEL + name)
    # Parents must be proven first (ROLES has Attribute and Talent in that order).
    return contracts


def app_bindings(platform, metadata, localization):
    contracts = constructor_contracts(metadata); result = {}; unresolved = []
    t = next(t for t in metadata['types'] if t['name'] == MODEL + 'AppData')
    m = next(m for m in t['methods'] if m['name'] == '.cctor'); il = m['il']
    zh = localization.get(platform, {}); en = localization.get(platform + '-en', {})
    for j, i in enumerate(il):
        if i['opcode'] != 'newobj' or not i['operand']['name'].startswith(MODEL):
            continue
        typename = i['operand']['name'][len(MODEL):].split('::')[0]
        if typename not in contracts or not contracts[typename]['verified']:
            continue
        category, name_pos, image_pos = ROLES[typename]
        try:
            expr, _ = expression(il, j)
            name = expr['args'][name_pos]; image = expr['args'][image_pos]
            if name['kind'] != 'literal' or image['kind'] != 'literal' or not isinstance(name['value'], str) or not isinstance(image['value'], str):
                raise ValueError('NON_LITERAL_NAME_OR_IMAGE')
            name = name['value']; image = image['value']
            if not re.fullmatch(r'[^/\\:]+\.(png|webp|jpe?g|gif|bmp)', image, re.I):
                raise ValueError('NON_IMAGE_RESOURCE')
            internal_id = expr['args'][0]['value'] if typename in ('Talent', 'SpecialTalent') and expr['args'][0]['kind'] == 'literal' else None
            key = (category, name, image, internal_id)
            source_field = il[j + 1]['operand']['name'] if j + 1 < len(il) and il[j + 1]['opcode'] == 'stsfld' else None
            record = result.setdefault(key, dict(category=category, application_type=typename, internal_id=internal_id,
                internal_key=name, source_filename=image, chinese_name=zh.get(name, name), english_name=en.get(name),
                full_chinese_name=zh.get(name + 'FN'), full_english_name=en.get(name + 'FN'), localization_key=name,
                confidence='exact', source_platform=platform, evidence=[]))
            record['evidence'].append(dict(type='literal_constructor_binding', method=MODEL + 'AppData::.cctor', method_token=m['token'],
                constructor_token=i['operand']['token'], il_offset=i['offset'], argument_offsets=expr['offsets'],
                source_field=source_field, constructor_contract=contracts[typename], localization_key=name))
        except (ValueError, IndexError, KeyError) as exc:
            unresolved.append(dict(method_token=m['token'], il_offset=i['offset'], constructor=typename, reason=str(exc).split(':')[0]))
    return sorted(result.values(), key=lambda r: (r['category'], r['internal_key'], r['source_filename'], str(r['internal_id']))), contracts, unresolved


def duplicate_groups(images, bindings):
    exact = defaultdict(list); pixels = defaultdict(list); filenames = defaultdict(list)
    for image in images:
        exact[image['sha256']].append(image)
        if image['pixel_hash']:
            pixels[image['pixel_hash']].append(image)
        filenames[PurePosixPath(image['source_entry']).name.casefold()].append(image)
    direct = defaultdict(list)
    for image in images:
        if image['source_entry'] in ('wwwroot/' + image['filename'], 'assets/wwwroot/' + image['filename']):
            direct[(image['source_platform'], image['filename'])].append(image)
    bound_files = defaultdict(set); bound_pixels = defaultdict(set)
    for binding in bindings:
        entity = (binding['category'], binding['internal_key'])
        for image in direct[(binding['source_platform'], binding['source_filename'])]:
            bound_files[(image['source_platform'], image['sha256'])].add(entity)
            if image['pixel_hash']:
                bound_pixels[(image['source_platform'], image['pixel_hash'])].add(entity)
    groups = []
    for kind, buckets in (('exact_file_duplicate', exact), ('pixel_duplicate', pixels)):
        for digest, members in sorted(buckets.items()):
            if len(members) < 2:
                continue
            entities = sorted({entity for member in members
                for entity in bound_files[(member['source_platform'], member['sha256'])]
                    | bound_pixels[(member['source_platform'], member['pixel_hash'])]})
            groups.append(dict(duplicate_group=kind + ':' + digest[:20], type=kind, digest=digest,
                members=sorted(m['source_asset_id'] for m in members), source_sha256s=sorted({m['sha256'] for m in members}),
                cross_platform=len({m['source_platform'] for m in members}) > 1,
                legitimate_shared_icon=len(entities) > 1, confirmed_application_entities=entities))
    correlations = []
    for apk in sorted((m for m in images if m['source_platform'] == 'apk'), key=lambda r: r['source_asset_id']):
        candidates = {m['source_asset_id']: m for m in exact[apk['sha256']] + pixels.get(apk['pixel_hash'], []) + filenames[apk['filename'].casefold()] if m['source_platform'] == 'windows'}
        for wid, win in sorted(candidates.items()):
            same_file = apk['sha256'] == win['sha256']
            same_pixel = bool(apk['pixel_hash']) and apk['pixel_hash'] == win['pixel_hash']
            correlations.append(dict(apk_asset_id=apk['source_asset_id'], windows_asset_id=wid,
                confidence='exact' if same_file or same_pixel else 'medium',
                evidence_types=(["exact_sha256"] if same_file else []) + (["decoded_pixel_hash"] if same_pixel else []) + (["filename"] if apk['filename'] == win['filename'] else []),
                filename_only_not_entity_proof=not (same_file or same_pixel)))
    return groups, correlations
