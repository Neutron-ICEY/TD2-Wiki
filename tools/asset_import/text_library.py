"""Read-only queries over explicitly wired, already exported text sources."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
import unicodedata

from .locations import SourceLocations


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INDEX = 'data/asset-import/text-sources.json'
RULE_VERSION = 1
MISSING = object()
RESOURCE_NAMESPACE = 'Division2BuildTool.Resources.Resx.AppResources'


class TextError(ValueError):
    def __init__(self, code, file=None):
        super().__init__(code)
        self.code, self.file = code, file


def require(condition, code):
    if not condition:
        raise TextError(code)


def local_file(root, value):
    # Evidence may mention external containers; only explicit local inputs open.
    require(isinstance(value, str) and bool(value), 'INVALID_PATH')
    parts = PurePosixPath(value).parts
    require(not PurePosixPath(value).is_absolute() and ':' not in value and '\\' not in value
            and not any(p.startswith('.') for p in parts), 'UNSAFE_PATH')
    path = (root / value).resolve()
    require(path.is_relative_to(root), 'PATH_OUTSIDE_ROOT')
    return path


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def identity(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8'))


def json_document(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result

    def invalid_constant(value):
        raise TextError('NONFINITE_JSON_NUMBER')

    return json.loads(data.decode('utf-8-sig'), object_pairs_hook=unique, parse_constant=invalid_constant)


def pointer(value):
    return str(value).replace('~', '~0').replace('/', '~1')


def search_text(value):
    return unicodedata.normalize('NFKC', value).casefold()


class TextLibrary:
    def __init__(self, root=ROOT, index=DEFAULT_INDEX):
        self.root = Path(root).resolve()
        self.locations = SourceLocations(self.root)
        data = json_document(local_file(self.root, index).read_bytes())
        require(isinstance(data, dict) and data.get('schema_version') == 1
                and isinstance(data.get('sources'), list), 'UNSUPPORTED_TEXT_INDEX')
        self.sources = {}
        self.duplicate_source_references = 0
        for source in data['sources']:
            require(isinstance(source, dict) and isinstance(source.get('id'), str)
                    and bool(source['id']), 'INVALID_SOURCE')
            old = self.sources.get(source['id'])
            if old is not None:
                require(old == source, 'SOURCE_ID_CONFLICT')
                self.duplicate_source_references += 1
            self.sources[source['id']] = source
        self.loaded = {}
        self.native_spec = data.get('native_references')
        self.native_loaded = None
        self.definition_spec = data.get('native_definitions')
        self.definitions_loaded = None

    def _read(self, spec):
        require(isinstance(spec, dict) and isinstance(spec.get('sha256'), str)
                and re.fullmatch('[0-9a-f]{64}', spec['sha256']), 'INVALID_INPUT_REFERENCE')
        name = spec.get('file')
        try:
            data = self.locations.resolve(local_file(self.root, name)).read_bytes()
        except FileNotFoundError:
            raise TextError('INPUT_MISSING', name) from None
        except OSError:
            raise TextError('INPUT_UNREADABLE', name) from None
        if sha256(data) != spec['sha256']:
            raise TextError('INPUT_HASH_MISMATCH', name)
        try:
            text = data.decode('utf-8-sig')
        except UnicodeError:
            raise TextError('INVALID_UTF8', name) from None
        info = dict(file=name, sha256=spec['sha256'], bytes=len(data), encoding='utf-8',
                    bom=data.startswith(b'\xef\xbb\xbf'), crlf=data.count(b'\r\n'),
                    lf_without_cr=data.count(b'\n') - data.count(b'\r\n'),
                    cr_without_lf=data.count(b'\r') - data.count(b'\r\n'))
        return data, text, info

    def _record(self, source, context, key, value, location, value_kind, **extra):
        require(isinstance(key, str), 'INVALID_STRING_KEY')
        require(value is MISSING or value is None or isinstance(value, str), 'INVALID_TEXT_VALUE')
        state = 'missing' if value is MISSING else 'null' if value is None else 'text'
        # Positions describe observations. Logical matching deliberately excludes
        # array order, file digest and application/game version.
        logical = dict(namespace=context['namespace'], key=key, platform=context.get('platform'),
                       culture=context.get('culture'), language=context.get('language'),
                       value_kind=value_kind)
        observation = [source['snapshot_id'], location, logical, RULE_VERSION]
        return dict(observation_id=identity(observation), logical_id=identity(logical),
                    source_id=source['id'], source_snapshot_id=source['snapshot_id'],
                    batch_ref=source.get('batch_ref'), key=key,
                    value_kind=value_kind, text=None if value is MISSING else value,
                    value_state=state, text_sha256=sha256(value.encode('utf-8')) if state == 'text' else None,
                    context=context, location=dict(file=source['file'], **location),
                    input_sha256=source['sha256'], parser_rule=source['format'] + '@1',
                    relations=[], **extra)

    @staticmethod
    def _app_context(packages, platform, culture, metadata_file):
        package = packages[platform]
        resource = RESOURCE_NAMESPACE + ('.en.resources' if culture == 'en' else '.resources')
        matches = [(assembly, stream, i, j) for i, assembly in enumerate(package['assembly_sources'])
                   for j, stream in enumerate(assembly['resource_streams']) if stream['name'] == resource]
        require(len(matches) == 1, 'RESOURCE_TABLE_NOT_UNIQUE')
        assembly, stream, assembly_index, resource_index = matches[0]
        return dict(namespace=RESOURCE_NAMESPACE, source_kind='companion_application', platform=platform,
                    culture=culture, language='en' if culture == 'en' else None,
                    application_version=(package.get('metadata') or {}).get('versionName') or package.get('assembly_version'),
                    game_version=None, revision=stream['sha256'],
                    provenance=dict(container=package['relative_path'], container_sha256=package['sha256'],
                                    source_entry=assembly['source_entry'], resource=resource,
                                    assembly_offset=assembly.get('offset'), resource_offset=stream['offset'],
                                    metadata_file=metadata_file,
                                    metadata_pointer='/' + platform + '/assembly_sources/' + str(assembly_index)
                                                     + '/resource_streams/' + str(resource_index),
                                    verification='recorded_package_metadata; original_package_not_opened'))

    def _menus(self, source, text, docs):
        reader = csv.reader(io.StringIO(text, newline=''), strict=True)
        require(next(reader, None) == ['2', '', '', ''], 'UNSUPPORTED_MENU_HEADER')
        header = next(reader, None)
        require(header is not None and len(header) == 4 and header[0].isdigit()
                and header[1:] == ['', '', ''], 'INVALID_MENU_COUNT')
        context = dict(namespace='hunter/localization/packages/english/menus.locpack',
                       source_kind='native_game_export', culture=None, language='en',
                       language_evidence='recorded english package path', application_version=None,
                       game_version=None, revision=source['sha256'])
        if 'locale' in source:
            locale = source['locale']
            require(set(locale)=={'namespace','culture','language','language_evidence'}
                    and all(isinstance(locale[k],str) for k in ('namespace','culture','language_evidence'))
                    and (locale['language'] is None or isinstance(locale['language'],str)), 'INVALID_MENU_LOCALE')
            context.update(locale)
        records = []
        for ordinal, row in enumerate(reader):
            start = 3 if ordinal == 0 else end + 1
            end = reader.line_num
            require(len(row) == 4 and re.fullmatch('[0-9A-F]{32}', row[0]), 'INVALID_MENU_RECORD')
            records.append(self._record(source, context, row[0], row[2],
                           dict(record=ordinal, line_start=start, line_end=end, column=2),
                           'exported_game_string', raw_columns=row))
        require(len(records) == int(header[0]), 'MENU_COUNT_MISMATCH')
        ledger = docs['provenance']['immutable_input_copies']
        copies = [r for r in ledger if r.get('sha256') == source['sha256']]
        require(len(copies) == 1, 'MENU_PROVENANCE_UNRESOLVED')
        context['provenance'] = dict(copies[0], verification='snapshot_hash_checked; original_cache_not_opened')
        if 'guid_references' not in docs:
            return records, dict(input_records=len(records),guid_references=0,unresolved_guid_references=0)
        refs = docs['guid_references']
        by_key = defaultdict(list)
        for record in records:
            by_key[record['key']].append(record)
        resolved = 0
        unresolved = []
        for i, ref in enumerate(refs['game_brands']):
            evidence = ref.get('localization_evidence')
            if evidence is None:
                unresolved.append(dict(key=ref['localization_guid'], resource_file=ref['path'],
                                       evidence_pointer='/game_brands/' + str(i), reason='no_recorded_localization_evidence'))
                continue
            matches = by_key.get(ref['localization_guid'], [])
            require(len(matches) == 1, 'GUID_REFERENCE_NOT_UNIQUE')
            record = matches[0]
            require(evidence['sha256'] == source['sha256'] and evidence['columns'] == record['raw_columns']
                    and evidence['text'] == record['text'] and evidence['line'] == record['location']['line_start'],
                    'GUID_REFERENCE_CONFLICT')
            record['relations'].append(dict(kind='native_guid_reference', status='evidenced_guid_lookup',
                evidence_file=source['evidence']['guid_references']['file'],
                evidence_pointer='/game_brands/' + str(i),
                resource_file=(PurePosixPath(source['evidence']['guid_references']['file']).parent / ref['path']).as_posix(),
                resource_sha256=ref['source_sha256'], resource_uid=ref['game_uid'],
                internal_name=ref['internal_name'], entity_mapping_confirmed=False))
            resolved += 1
        for i, association in enumerate(refs['target_name_associations']):
            for candidate in association['game_candidates']:
                for record in by_key.get(candidate['localization_guid'], []):
                    record['relations'].append(dict(kind='name_association', status='candidate',
                        evidence_file=source['evidence']['guid_references']['file'],
                        recorded_status=association['status'], entity_key=association['entity_key'],
                        evidence_pointer='/target_name_associations/' + str(i),
                        basis='historical normalized English name comparison', entity_mapping_confirmed=False))
        return records, dict(input_records=len(records), guid_references=resolved,
                             unresolved_guid_references=len(unresolved), unresolved_references=unresolved)

    def _app_names(self, source, data, docs):
        require(set(data) == {'apk', 'apk-en', 'windows', 'windows-en'}, 'INVALID_APP_TABLES')
        records = []
        bindings = defaultdict(list)
        for i, row in enumerate(docs['bindings']['bindings']):
            bindings[(row['source_platform'], row['localization_key'])].append(dict(
                evidence_file=source['evidence']['bindings']['file'],
                evidence_pointer='/bindings/' + str(i), application_type=row['application_type'],
                application_id=row['internal_id'], id_scope='application_only', internal_key=row['internal_key']))
        for label, table in data.items():
            require(isinstance(table, dict), 'INVALID_APP_TABLE')
            platform = 'apk' if label.startswith('apk') else 'windows'
            culture = 'en' if label.endswith('-en') else 'neutral'
            context = self._app_context(docs['packages'], platform, culture, source['evidence']['packages']['file'])
            peer_label = platform if culture == 'en' else platform + '-en'
            for key, value in table.items():
                location = dict(pointer='/' + pointer(label) + '/' + pointer(key))
                record = self._record(source, context, key, value, location, 'resource_value',
                                      application_bindings=bindings.get((platform, key), []))
                if key in data[peer_label] and isinstance(value, str) and isinstance(data[peer_label][key], str):
                    record['relations'].append(dict(kind='localization_pair', status='evidenced_same_resource_key',
                        peer_pointer='/' + pointer(peer_label) + '/' + pointer(key),
                        peer_culture='neutral' if culture == 'en' else 'en', official_translation=False))
                records.append(record)
        return records, dict(input_records=sum(map(len, data.values())), table_counts={k:len(v) for k,v in data.items()})

    def _app_resources(self, source, data, docs):
        require(data.get('schema_version') == 1 and data.get('parser_rule') == 'dotnet_resources_v2_strings@1',
                'UNSUPPORTED_APP_RESOURCE_DATA')
        require(docs['extraction']['parser_rule'] == data['parser_rule']
                and docs['extraction']['output'] == dict(file=source['file'], sha256=source['sha256']),
                'APP_RESOURCE_OUTPUT_CONFLICT')
        records, issues, table_counts = [], [], {}
        tables = {}
        for index, table in enumerate(data['tables']):
            identity_key = (table['platform'], table['culture'])
            require(identity_key in {(p,c) for p in ('apk','windows') for c in ('neutral','en')}
                    and identity_key not in tables, 'INVALID_APP_RESOURCE_TABLE')
            tables[identity_key] = (index, table)
        bindings = defaultdict(list)
        for i, binding in enumerate(docs['bindings']['bindings']):
            bindings[(binding['source_platform'], binding['localization_key'])].append(dict(
                evidence_file=source['evidence']['bindings']['file'], evidence_pointer='/bindings/' + str(i),
                application_type=binding['application_type'], application_id=binding['internal_id'],
                id_scope='application_only', internal_key=binding['internal_key']))
        for platform in ('apk','windows'):
            for culture in ('neutral','en'):
                if (platform,culture) not in tables:
                    issues.append(dict(source_id=source['id'], platform=platform, culture=culture, code='TARGET_TABLE_MISSING'))
                    continue
                index, table = tables[(platform,culture)]
                require(re.fullmatch(r'/tables/\d+', table['evidence_pointer']), 'INVALID_TABLE_EVIDENCE_POINTER')
                evidence = docs['extraction']['tables'][int(table['evidence_pointer'].rsplit('/',1)[1])]
                context = self._app_context(docs['packages'], platform, culture, source['evidence']['packages']['file'])
                require(evidence['platform'] == platform and evidence['culture'] == culture
                        and evidence['resource_name'] == table['resource_name'] == context['provenance']['resource']
                        and evidence['resource_sha256'] == table['resource_sha256'] == context['revision']
                        and evidence['stats']['declared_entries'] == len(table['records']), 'APP_RESOURCE_EVIDENCE_CONFLICT')
                statuses = [row['status'] for row in table['records']]
                require(all(row['entry_index'] == j for j,row in enumerate(table['records']))
                        and all(evidence['stats'][name] == statuses.count(status) for name,status in
                            [('string_values','string'),('null_values','null'),
                             ('non_string_values','non_string'),('parse_errors','parse_error')]),
                        'APP_RESOURCE_COUNT_CONFLICT')
                context['provenance'] = dict(context['provenance'],
                    extraction_file=source['evidence']['extraction']['file'], extraction_pointer=table['evidence_pointer'],
                    raw_resource=evidence['raw_resource'],
                    verification='package/resource hashes checked during extraction; query reads pinned derivative')
                label = platform + ('-en' if culture == 'en' else '')
                table_counts[label] = len(table['records'])
                peer = tables.get((platform, 'neutral' if culture == 'en' else 'en'))
                own_keys, peer_keys = defaultdict(list), defaultdict(list)
                for j, row in enumerate(table['records']):
                    own_keys[row['key']].append(j)
                for key, positions in own_keys.items():
                    if isinstance(key, str) and len(positions) > 1:
                        issues.append(dict(source_id=source['id'], platform=platform, culture=culture,
                            code='DUPLICATE_RESOURCE_KEY', key=key, entries=positions))
                if peer:
                    for j, row in enumerate(peer[1]['records']):
                        peer_keys[row['key']].append(j)
                for j, row in enumerate(table['records']):
                    location = '/tables/' + str(index) + '/records/' + str(j)
                    require(row['status'] in ('string','null','non_string','parse_error'), 'INVALID_RESOURCE_STATUS')
                    if row['status'] == 'parse_error':
                        issues.append(dict(source_id=source['id'], file=source['file'], pointer=location,
                                           code=row.get('error', 'RESOURCE_ENTRY_PARSE_ERROR')))
                    if not isinstance(row['key'], str):
                        continue
                    value = row['text'] if row['status'] in ('string','null') else MISSING
                    require((row['status'] != 'string' or isinstance(value, str))
                            and (row['status'] != 'null' or value is None), 'INVALID_STRING_RESOURCE_VALUE')
                    record = self._record(source, context, row['key'], value, dict(pointer=location + '/text'),
                        'resource_value', resource_status=row['status'], type_code=row.get('type_code'),
                        resource_location=dict(file=evidence['raw_resource']['file'],
                            **{k:row[k] for k in ('entry_index','name_offset','data_offset','value_offset','value_end') if k in row}),
                        application_bindings=bindings.get((platform,row['key']), []))
                    matches = peer_keys.get(row['key'], [])
                    relation = dict(kind='localization_pair', peer_culture='neutral' if culture == 'en' else 'en',
                                    official_translation=False, status='peer_key_absent')
                    if matches:
                        relation['peer_pointers'] = ['/tables/' + str(peer[0]) + '/records/' + str(k) + '/text' for k in matches]
                        relation['status'] = ('evidenced_same_resource_key' if len(own_keys[row['key']]) == len(matches) == 1
                            and row['status'] == peer[1]['records'][matches[0]]['status'] == 'string'
                            else 'ambiguous_or_unrecoverable_peer')
                    record['relations'].append(relation)
                    records.append(record)
        for failure in data.get('failures', []):
            issues.append(dict(failure, source_id=source['id']))
        return records, dict(input_records=sum(table_counts.values()), table_counts=table_counts,
            string_values=sum(r['resource_status'] == 'string' for r in records),
            unique_keys=len({r['key'] for r in records}),
            unique_text_values=len({r['text'] for r in records if r['value_state'] == 'text'}), recovery_issues=issues)

    def _attributes(self, source, data, docs):
        require(isinstance(data, list), 'INVALID_ATTRIBUTE_DATA')
        records = []
        contexts = {(p,c): self._app_context(docs['packages'], p, c, source['evidence']['packages']['file'])
                    for p in ('apk', 'windows') for c in ('neutral', 'en')}
        for i, row in enumerate(data):
            key = row['localization_key']
            prefix = '/' + str(i)
            require(isinstance(row['source_platforms'], list) and bool(row['source_platforms'])
                    and len(set(row['source_platforms'])) == len(row['source_platforms'])
                    and set(row['source_platforms']) <= {'apk', 'windows'}, 'INVALID_ATTRIBUTE_PLATFORMS')
            for platform in row['source_platforms']:
                for culture, field in (('neutral', 'display_name_zh'), ('en', 'display_name_en')):
                    value = row.get(field, MISSING)
                    context = contexts[(platform, culture)]
                    evidence = [e for e in row['evidence'] if e['kind'] == 'resource_key_value'
                                and e['culture'] == culture and e['source_location']['platform'] == platform]
                    if isinstance(value, str):
                        require(len(evidence) == 1 and evidence[0]['key'] == key and evidence[0]['value'] == value,
                                'ATTRIBUTE_LANGUAGE_EVIDENCE_CONFLICT')
                        table = next(t for t in docs['localization'][platform]['tables'] if t['culture'] == culture)
                        require(table['candidate_strings'].get(key, MISSING) == value,
                                'ATTRIBUTE_LOCALIZATION_CONFLICT')
                        require(table['resource_sha256'] == context['revision'], 'ATTRIBUTE_RESOURCE_REVISION_CONFLICT')
                    record = self._record(source, context, key, value, dict(pointer=prefix + '/' + field),
                        'resource_value', internal_keys=row.get('internal_keys', []),
                        lookup_status=row.get('localization_key_status'), resource_evidence=evidence,
                        variants_pointer=prefix + '/variants', variant_count=len(row.get('variants', [])))
                    if row.get('status') == 'bilingual':
                        require(isinstance(value, str), 'BILINGUAL_VALUE_MISSING')
                        record['relations'].append(dict(kind='localization_pair', status='evidenced_constructor_resource_key',
                            peer_pointer=prefix + ('/display_name_zh' if culture == 'en' else '/display_name_en'),
                            peer_culture='neutral' if culture == 'en' else 'en', official_translation=False))
                    records.append(record)
                if row.get('chinese_name_source') == 'constructor_literal':
                    locations = [s for s in row['source_locations'] if s['platform'] == platform]
                    require(bool(locations), 'INVALID_CONSTRUCTOR_EVIDENCE')
                    package = contexts[(platform, 'neutral')]['provenance']
                    context = dict(contexts[(platform, 'neutral')], namespace='Division2BuildTool.Model.AppData',
                                   culture=None, language=None, revision=source['sha256'],
                                   provenance=dict(container=package['container'], container_sha256=package['container_sha256'],
                                       source_locations=locations, verification='recorded_static_il; original_package_not_opened'))
                    records.append(self._record(source, context, key, row.get('chinese_name', MISSING),
                        dict(pointer=prefix + '/chinese_name'), 'constructor_literal',
                        source_locations=locations))
                for j, alias in enumerate(row['english_aliases_from_app_dictionary']):
                    locations = [s for s in alias['source_locations'] if s['platform'] == platform]
                    require(bool(locations) and alias['output_internal_name'] == key, 'INVALID_DICTIONARY_EVIDENCE')
                    package = contexts[(platform, 'en')]['provenance']
                    context = dict(contexts[(platform, 'en')], namespace='Division2BuildTool.Model.AppData::TranslateDictionary',
                                   culture=None, revision=source['sha256'], language_evidence='explicit English alias field',
                                   provenance=dict(container=package['container'], container_sha256=package['container_sha256'],
                                       source_locations=locations, verification='recorded_static_il; original_package_not_opened'))
                    record = self._record(source, context, alias['input_name'], alias['input_name'],
                        dict(pointer=prefix + '/english_aliases_from_app_dictionary/' + str(j) + '/input_name'),
                        'dictionary_alias', internal_keys=[key],
                        dictionary_output_key=alias['output_internal_name'],
                        source_locations=locations)
                    record['relations'].append(dict(kind='application_dictionary', status='explicit_dictionary_entry',
                        output_internal_key=alias['output_internal_name'], official_translation=False))
                    records.append(record)
        return records, dict(input_records=len(data), attribute_status_counts=dict(Counter(r['status'] for r in data)))

    def _app_dictionary(self, source, data, docs):
        from .text_evidence import APP_DATA, translation_dictionary
        require(data.get('schema_version')==1 and data.get('parser_rule')=='app_translate_dictionary_il@1',
                'UNSUPPORTED_DICTIONARY_DATA')
        records=[]
        recovered=0
        excluded=0
        require(all(r['platform'] in ('apk','windows') for r in data['records']),'INVALID_DICTIONARY_PLATFORM')
        for platform in ('apk','windows'):
            entries=translation_dictionary(docs[platform])
            existing={(a['input_name'],a['output_internal_name']) for row in docs['attributes']
                      for a in row['english_aliases_from_app_dictionary']
                      if any(s['platform']==platform for s in a['source_locations'])}
            require(existing <= {(r['input_name'],r['output_internal_name']) for r in entries},'EXISTING_ALIAS_EVIDENCE_CONFLICT')
            expected=[r for r in entries if (r['input_name'],r['output_internal_name']) not in existing]
            actual=[{k:v for k,v in r.items() if k!='platform'} for r in data['records'] if r['platform']==platform]
            require(actual==expected,'DICTIONARY_INSTRUCTION_EVIDENCE_CONFLICT')
            recovered+=len(entries)
            excluded+=len(existing)
            package=docs['packages'][platform]
            metadata_spec=source['evidence'][platform]
            context=dict(namespace=APP_DATA+'::TranslateDictionary',source_kind='companion_application',
                platform=platform,culture=None,language=None,game_version=None,
                application_version=(package.get('metadata') or {}).get('versionName') or package.get('assembly_version'),
                revision=metadata_spec['sha256'],provenance=dict(container=package['relative_path'],
                    container_sha256=package['sha256'],metadata_file=metadata_spec['file'],
                    verification='exact cached static initializer instructions; original package not opened'))
            for i,row in enumerate(data['records']):
                if row['platform']!=platform: continue
                location=dict(file=metadata_spec['file'],pointer=row['evidence_pointer'],
                    il_offset=row['il_offset'],method_token=row['method_token'],method_rva=row['method_rva'],
                    type=APP_DATA,method='.cctor',field='TranslateDictionary')
                record=self._record(source,context,row['input_name'],row['input_name'],
                    dict(pointer='/records/'+str(i)+'/input_name'),'dictionary_alias',
                    internal_keys=[row['output_internal_name']],dictionary_output_key=row['output_internal_name'],
                    source_locations=[location])
                record['relations'].append(dict(kind='application_dictionary',status='explicit_dictionary_entry',
                    output_internal_key=row['output_internal_name'],official_translation=False,id_scope='application_only'))
                records.append(record)
        return records,dict(input_records=len(data['records']),dictionary_entries_recovered=recovered,
                            already_registered=excluded,unique_alias_pairs=len({(r['key'],r['dictionary_output_key']) for r in records}))

    def _business(self, source, data):
        brands = source['format'] == 'business_brands'
        collection = 'brands' if brands else 'attributes'
        require(isinstance(data, dict) and isinstance(data.get(collection), list), 'INVALID_BUSINESS_CATALOG')
        records = []
        for i, row in enumerate(data[collection]):
            if brands:
                require((row.get('name_policy') or {}).get('business_name_approved') is True, 'BUSINESS_NAME_NOT_APPROVED')
            key = row['entity_key' if brands else 'id']
            for field, language in (('zh_name', 'zh'), ('en_name', 'en')):
                context = dict(namespace='wiki_business/' + ('brands' if brands else 'bonuses'), source_kind='reviewed_business_name',
                               language=language, culture=None, application_version=None, game_version=None,
                               revision=source['sha256'])
                record = self._record(source, context, key, row.get(field, MISSING),
                    dict(pointer='/' + collection + '/' + str(i) + '/' + field), 'business_name',
                    verification=row.get('name_policy') if brands else row.get('verification'),
                    official_game_zh_verified=(row.get('name_policy') or {}).get('official_game_zh_verified'))
                record['relations'].append(dict(kind='curated_name_fields', status='business_record_only',
                                                official_translation=False))
                records.append(record)
        return records, dict(input_records=len(data[collection]))

    def _native_literals(self, source, data):
        from .text_evidence import metadata_literal_value, native_references
        require(data.get('schema_version') == 1 and data.get('parser_rule') == 'fruit_metadata_literals@1',
                'UNSUPPORTED_NATIVE_LITERALS')
        records = []
        seen = set()
        for index, document in enumerate(data['files']):
            if 'sha256' in document.get('ledger',{}):
                self._read(document['ledger'])
            raw, _, _ = self._read(document)
            refs = native_references(raw)['references']
            for j, row in enumerate(document['records']):
                require(row in refs, 'NATIVE_LITERAL_EVIDENCE_CONFLICT')
                token = (document['file'], row['location']['byte_start'])
                require(token not in seen, 'DUPLICATE_NATIVE_LITERAL')
                seen.add(token)
                context = dict(namespace=document['file'], source_kind='native_game_export',
                    culture=None, language=None, application_version=None, game_version=None,
                    revision=document['sha256'], provenance=dict(file=document['file'],
                        sha256=document['sha256'], ledger=document.get('ledger')))
                record = self._record(source, context, row['resource_uid'] + '::' + row['field'],
                    metadata_literal_value(row['embedded_text_literal']),
                    dict(pointer='/files/' + str(index) + '/records/' + str(j)), 'native_metadata_literal',
                    internal_keys=[row['guid']], resource_uid=row['resource_uid'],
                    source_location=dict(file=document['file'], **row['location']),
                    embedded_text_literal=row['embedded_text_literal'])
                record['relations'].append(dict(kind='native_metadata_literal', status='saved_field_literal',
                    localization_guid=row['guid'], resource_uid=row['resource_uid'], field=row['field'],
                    enabled=row['enabled'], entity_mapping_confirmed=False,
                    menu_value_recovered=False))
                records.append(record)
        return records, dict(input_records=len(records))

    def _load(self, source):
        inputs = []
        current_file = source.get('file')
        try:
            snapshot={k:source.get(k) for k in ('id','file','sha256','format','batch_ref','evidence')}
            if 'locale' in source: snapshot['locale']=source['locale']
            source = dict(source, snapshot_id=identity(snapshot))
            fmt = source.get('format')
            require(fmt in ('menus_csv', 'app_names', 'app_resources', 'app_dictionary', 'attributes_json', 'business_brands', 'business_bonuses', 'native_literals'),
                    'UNSUPPORTED_TEXT_FORMAT')
            raw, text, info = self._read(source)
            inputs.append(dict(info, role='text_input'))
            docs = {}
            for role, spec in source.get('evidence', {}).items():
                current_file = spec.get('file')
                data, _, metadata = self._read(spec)
                docs[role] = json_document(data)
                inputs.append(dict(metadata, role=role))
            current_file = source['file']
            if fmt == 'menus_csv':
                records, stats = self._menus(source, text, docs)
            else:
                data = json_document(raw)
                if fmt == 'app_names':
                    records, stats = self._app_names(source, data, docs)
                elif fmt == 'app_resources':
                    records, stats = self._app_resources(source, data, docs)
                elif fmt == 'attributes_json':
                    records, stats = self._attributes(source, data, docs)
                elif fmt == 'app_dictionary':
                    records, stats = self._app_dictionary(source, data, docs)
                elif fmt == 'native_literals':
                    records, stats = self._native_literals(source, data)
                else:
                    records, stats = self._business(source, data)
            recovery_issues = stats.pop('recovery_issues', [])
            return dict(source_id=source['id'], records=records, stats=dict(stats, observations=len(records)),
                        inputs=inputs, issues=recovery_issues)
        except (OSError, ValueError, KeyError, TypeError, IndexError, StopIteration, AttributeError, csv.Error) as error:
            code = error.code if isinstance(error, TextError) else ('INVALID_UTF8' if isinstance(error, UnicodeError)
                    else 'INVALID_JSON' if isinstance(error, json.JSONDecodeError) else 'INVALID_SOURCE_DATA')
            return dict(source_id=source['id'], records=[], stats=dict(observations=0), inputs=inputs,
                        issues=[dict(source_id=source['id'], file=getattr(error, 'file', None) or current_file, code=code)])

    def _load_native(self):
        from .text_evidence import native_references
        current_file=self.native_spec.get('file') if isinstance(self.native_spec,dict) else None
        try:
            raw,_,info=self._read(self.native_spec)
            data=json_document(raw)
            require(data.get('schema_version')==1 and data.get('parser_rule')=='fruit_localization_guid_fields@1',
                    'UNSUPPORTED_NATIVE_REFERENCES')
            recovery_issues=list(data.get('issues',[]))
            require(isinstance(self.native_spec.get('target_sources'),list)
                    and all(s in self.sources and self.sources[s]['format']=='menus_csv' for s in self.native_spec['target_sources']),
                    'INVALID_NATIVE_REFERENCE_TARGETS')
            by_file=defaultdict(list)
            ids=set()
            for i,row in enumerate(data['references']):
                require(isinstance(row['file_index'],int) and 0<=row['file_index']<len(data['files']), 'INVALID_NATIVE_FILE_INDEX')
                spec=data['files'][row['file_index']]
                require(row['reference_id']==identity([spec['file'],spec['sha256'],row['location']['byte_start'],row['field'],row['guid']]),
                        'NATIVE_REFERENCE_ID_CONFLICT')
                require(row['reference_id'] not in ids,'DUPLICATE_NATIVE_REFERENCE')
                ids.add(row['reference_id'])
                by_file[row['file_index']].append((i,row))
            references=[]
            for file_index,spec in enumerate(data['files']):
                current_file=spec['file']
                if 'sha256' in spec.get('ledger',{}):
                    self._read(spec['ledger'])
                blob,_,_=self._read(spec)
                parsed=native_references(blob)
                for issue in parsed['issues']:
                    issue=dict(issue,file=spec['file'])
                    if issue not in recovery_issues: recovery_issues.append(issue)
                expected=[{k:v for k,v in row.items() if k not in ('file_index','reference_id')} for _,row in by_file[file_index]]
                require(parsed['references']==expected,'NATIVE_FIELD_EVIDENCE_CONFLICT')
                for i,row in by_file[file_index]:
                    references.append(dict(row,resource_file=spec['file'],resource_sha256=spec['sha256'],
                        evidence_file=self.native_spec['file'],evidence_pointer='/references/'+str(i)))
            return dict(references=references,issues=recovery_issues,input=info)
        except (OSError,ValueError,KeyError,TypeError,IndexError,StopIteration,AttributeError) as error:
            return dict(references=[],issues=[dict(component='native_references',file=getattr(error,'file',None) or current_file,
                code=error.code if isinstance(error,TextError) else 'INVALID_NATIVE_REFERENCES')])

    def _load_definitions(self):
        from .text_evidence import native_definitions
        current_file = self.definition_spec.get('file') if isinstance(self.definition_spec, dict) else None
        try:
            raw, _, info = self._read(self.definition_spec)
            data = json_document(raw)
            rules=('fruit_definition_scopes@1','fruit_definition_scopes@2','fruit_definition_scopes@3','fruit_definition_scopes@4')
            require(data.get('schema_version') == 1 and data.get('parser_rule') in rules,
                    'UNSUPPORTED_NATIVE_DEFINITIONS')
            for schema in data.get('schema_evidence', []):
                self._read(schema)
            resources, links, issues = [], [], []
            includes_by_file={}
            files = set()
            for i, spec in enumerate(data['files']):
                current_file = spec['file']
                require(current_file not in files, 'DUPLICATE_NATIVE_DEFINITION_FILE')
                files.add(current_file)
                if 'sha256' in spec.get('ledger',{}):
                    self._read(spec['ledger'])
                blob, _, _ = self._read(spec)
                rule=spec.get('parser_rule',data['parser_rule']) if data['parser_rule'] in rules[2:] else data['parser_rule']
                require(rule in rules,'UNSUPPORTED_NATIVE_DEFINITIONS')
                parsed = native_definitions(blob, include_formulas=rule!='fruit_definition_scopes@1',
                                            include_data=rule in rules[2:],include_objects=rule=='fruit_definition_scopes@4')
                require(parsed == spec['parsed'], 'NATIVE_DEFINITION_EVIDENCE_CONFLICT')
                includes_by_file[current_file]=parsed['includes']
                issues.extend(dict(issue, file=current_file) for issue in parsed['issues'])
                own = []
                for j, row in enumerate(parsed['resources']):
                    resource = dict(row, resource_id=identity([current_file, spec['sha256'], row['location'], row['resource_uid']]),
                        resource_file=current_file, resource_sha256=spec['sha256'], ledger=spec.get('ledger'),
                        evidence_file=self.definition_spec['file'], evidence_pointer='/files/' + str(i) + '/parsed/resources/' + str(j),
                        entity_mapping_confirmed=False, parser_rule=rule)
                    if 'resource_name' in spec:
                        resource.update(resource_name=spec['resource_name'],export_role=spec['export_role'],
                                        source_container_sha256=spec.get('source_container_sha256'))
                    if 'generation_context' in spec:resource['generation_context']=spec['generation_context']
                    own.append(resource)
                    resources.append(resource)
                for j, row in enumerate(parsed['links']):
                    owner = own[row['source_index']]
                    links.append(dict(row, link_id=identity([current_file, spec['sha256'], row['location'], row['target_uid']]),
                        source_resource_id=owner['resource_id'], source_uid=owner['resource_uid'],
                        resource_file=current_file, resource_sha256=spec['sha256'], ledger=spec.get('ledger'),
                        evidence_file=self.definition_spec['file'], evidence_pointer='/files/' + str(i) + '/parsed/links/' + str(j)))
            symbols=defaultdict(list)
            for row in resources:
                if row.get('source_container_sha256'):
                    symbols[row['source_container_sha256'],row['resource_name']].append(row)
            for row in resources:
                if 'inheritance_name' not in row:continue
                candidates=[]
                if row['parser_rule']=='fruit_definition_scopes@4':
                    candidates.extend((target,None) for target in resources if target['resource_file']==row['resource_file']
                        and (target['resource_type'],target['internal_name'])==(row['resource_type'],row['inheritance_name']))
                for include in includes_by_file[row['resource_file']]:
                    path=include['path']
                    if path.startswith('./') and row.get('resource_name'):
                        path=str(PurePosixPath(row['resource_name']).parent/path[2:])
                    for target in symbols.get((row.get('source_container_sha256'),path),[]):
                        if (target['resource_type'],target['internal_name'])==(row['resource_type'],row['inheritance_name']):
                            candidates.append((target,include))
                row['inheritance_status']='definition_not_saved' if not candidates else 'ambiguous_saved_symbol'
                if len({c['resource_uid'] or c['resource_id'] for c,_ in candidates})!=1:continue
                target,include=candidates[0];row['inheritance_status']='saved_definition'
                loc=row['inheritance_location']
                links.append(dict(source_index=None,field=':base',reference_uid=None,target_name=row['inheritance_name'],
                    target_uid=target['resource_uid'],kind='declared_native_inheritance',context=[],location=loc,
                    target_resource_ids=[target['resource_id']],
                    raw_field_sha256=row['inheritance_field_sha256'],entity_mapping_confirmed=False,
                    link_id=identity([row['resource_file'],row['resource_sha256'],loc,target['resource_uid']]),
                    source_resource_id=row['resource_id'],source_uid=row['resource_uid'],
                    resource_file=row['resource_file'],resource_sha256=row['resource_sha256'],ledger=row['ledger'],
                    evidence_file=row['evidence_file'],evidence_pointer=row['evidence_pointer']+'/inheritance_name',
                    include_evidence=include,resolution='declared_symbol_in_same_file' if include is None
                        else 'explicit_include_and_declared_symbol_in_same_source_index'))
            by_uid = defaultdict(list)
            local_symbols=defaultdict(list)
            for row in resources:
                if row['resource_uid'] is None:
                    row['uid_status']='no_native_uid'
                    local_symbols[row['resource_file'],row['resource_type'],row['internal_name']].append(row)
                else:by_uid[row['resource_uid']].append(row)
            for (file,kind,name),rows in local_symbols.items():
                if len(rows)>1:
                    issues.append(dict(code='NATIVE_SYMBOL_DEFINITION_CONFLICT',file=file,resource_type=kind,
                        internal_name=name,resource_ids=[r['resource_id'] for r in rows]))
            conflicts = []
            for uid, rows in by_uid.items():
                different = len({(r['resource_type'],r['internal_name'],r['definition_sha256']) for r in rows}) > 1
                for row in rows:
                    row['uid_status'] = 'conflicting_saved_definitions' if different else 'saved_definition'
                if different:
                    conflicts.append(dict(code='NATIVE_UID_DEFINITION_CONFLICT',resource_uid=uid,
                        definitions=[dict(resource_id=r['resource_id'],file=r['resource_file'],
                            internal_name=r['internal_name'],location=r['location']) for r in rows]))
            by_resource_id={r['resource_id']:r for r in resources}
            config_bindings=defaultdict(list)
            preset_talents=defaultdict(list)
            for edge in links:
                owner=by_resource_id[edge['source_resource_id']]
                if owner['resource_type']!='ItemGenerationConfig':continue
                if edge['field']=='myItemGenerationConfigLink':config_bindings[edge['target_uid']].append(edge)
                elif edge['field']=='myPresetTalent':preset_talents[edge['source_resource_id']].append(edge)
            for edge in list(links):
                item=by_resource_id[edge['source_resource_id']]
                if item['resource_type'] not in ('ArmorItem','WeaponItem') or edge['field']!='myItemGenerationConfig':continue
                for binding in config_bindings.get(edge['target_uid'],[]):
                    config=by_resource_id[binding['source_resource_id']]
                    if not item.get('source_container_sha256') or item['source_container_sha256']!=config.get('source_container_sha256'):continue
                    generation=config.get('generation_context')
                    peers=[b for b in config_bindings[edge['target_uid']] if
                        by_resource_id[b['source_resource_id']].get('source_container_sha256')==item['source_container_sha256']
                        and by_resource_id[b['source_resource_id']].get('generation_context')==generation]
                    conflict=bool(generation) and len({b['source_resource_id'] for b in peers})>1
                    binding_status='conflicting_saved_generation_context' if conflict else 'shared_native_config_link_uid'
                    if conflict:
                        issue=dict(code='NATIVE_GENERATION_CONFIG_CONFLICT',resource_uid=item['resource_uid'],
                            generation_context=generation,configuration_resource_ids=sorted({b['source_resource_id'] for b in peers}))
                        if issue not in conflicts:conflicts.append(issue)
                    relation=dict(edge,kind='native_generation_binding',target_uid=None,target_name=config['internal_name'],
                        target_resource_ids=[config['resource_id']],configuration_resource_id=config['resource_id'],
                        shared_config_link_uid=edge['target_uid'],
                        generation_context=generation,binding_status=binding_status,binding_evidence=dict(binding),
                        link_id=identity(['native_generation_binding',item['resource_id'],config['resource_id'],edge['location']]))
                    links.append(relation)
                    for preset in preset_talents[config['resource_id']]:
                        links.append(dict(edge,kind='native_equipment_preset_talent',target_field='myPresetTalent',target_type='Talent',
                            target_uid=preset['target_uid'],target_name=preset['target_name'],configuration_context=preset['context'],
                            configuration_resource_id=config['resource_id'],generation_context=config.get('generation_context'),
                            binding_status=binding_status,
                            shared_config_link_uid=edge['target_uid'],
                            binding_evidence=dict(binding),preset_evidence=dict(preset),
                            link_id=identity(['native_equipment_preset_talent',item['resource_id'],config['resource_id'],preset['location'],preset['target_uid']])))
            for row in links:
                targets=by_uid.get(row['target_uid'],[]) if row['target_uid'] is not None else [by_resource_id[k] for k in row.get('target_resource_ids',[])]
                wrong_type=bool(targets) and row['target_uid'] is not None and row.get('target_type') is not None and not any(t['resource_type']==row['target_type'] for t in targets)
                if row['target_uid'] is not None and row.get('target_type') is not None:
                    targets=[t for t in targets if t['resource_type']==row['target_type']]
                if row['kind']=='native_symbol_reference':
                    source=by_resource_id[row['source_resource_id']]
                    allowed={source['resource_name']} if source.get('resource_name') else set()
                    for include in includes_by_file[source['resource_file']]:
                        path=include['path']
                        if path.startswith('./') and source.get('resource_name'):
                            path=str(PurePosixPath(source['resource_name']).parent/path[2:])
                        allowed.add(path)
                    targets=[target for target in resources if target['resource_file']==source['resource_file']
                        and (target['resource_type'],target['internal_name'])==(row['target_type'],row['target_name'])]
                    targets.extend(target for path in allowed for target in symbols.get((source.get('source_container_sha256'),path),[])
                        if target['resource_file']!=source['resource_file']
                        and (target['resource_type'],target['internal_name'])==(row['target_type'],row['target_name']))
                row['target_resource_ids'] = [t['resource_id'] for t in targets]
                row['target_status'] = ('saved_uid_has_different_type' if wrong_type else 'ambiguous_saved_uid' if any(t['uid_status']=='conflicting_saved_definitions' for t in targets)
                    else 'ambiguous_saved_symbol' if row['target_uid'] is None and len(targets)>1
                    else 'saved_definition' if targets else 'definition_not_saved')
                if row['kind']=='declared_native_inheritance':
                    by_resource_id[row['source_resource_id']]['inheritance_status']=row['target_status']
            return dict(resources=resources, links=links, issues=issues, conflicts=conflicts, input=info)
        except (OSError, ValueError, KeyError, TypeError, IndexError, StopIteration, AttributeError) as error:
            return dict(resources=[], links=[], issues=[dict(component='native_definitions',
                file=getattr(error, 'file', None) or current_file,
                code=error.code if isinstance(error, TextError) else 'INVALID_NATIVE_DEFINITIONS')])

    @staticmethod
    def _conflicts(records):
        seen = {}
        conflicts = {}
        for record in records:
            context = (record['logical_id'], record['context']['revision'])
            signature = (record['value_state'], record['text'], tuple(record.get('raw_columns', [])),
                         record.get('dictionary_output_key'))
            old = seen.get(context)
            if old is None:
                seen[context] = signature, [record['observation_id']]
            else:
                old[1].append(record['observation_id'])
                if old[0] != signature and context not in conflicts:
                    conflicts[context] = dict(code='LOGICAL_CONTEXT_CONFLICT', key=record['key'],
                        logical_id=record['logical_id'], revision=record['context']['revision'], observations=old[1])
        return list(conflicts.values())

    def query(self, key=None, text=None, sources=(), culture=None, language=None,
              batch=None, limit=20, offset=0, normalized=False, platform=None, resource=None, related_depth=0):
        require(1 <= limit <= 1000 and offset >= 0, 'INVALID_PAGINATION')
        require(isinstance(related_depth,int) and 0<=related_depth<=5 and (not related_depth or resource is not None),
                'INVALID_RELATED_DEPTH')
        require(not (set(sources) - self.sources.keys()), 'UNKNOWN_TEXT_SOURCE')
        selected = [s for s in self.sources.values() if (not sources or s['id'] in sources)
                    and (batch is None or s.get('batch_ref') == batch or s.get('related_asset_batch') == batch)]
        if batch is not None:
            require(any(s.get('batch_ref') == batch or s.get('related_asset_batch') == batch
                        for s in self.sources.values()), 'UNKNOWN_BATCH_REFERENCE')
        for source in selected:
            if source['id'] not in self.loaded:
                self.loaded[source['id']] = self._load(source)
        loaded = [self.loaded[s['id']] for s in selected]
        records = [r for item in loaded for r in item['records']]
        conflicts = self._conflicts(records)
        issues = [i for item in loaded for i in item['issues']] + conflicts
        menu_ids={s['id'] for s in selected if s['format']=='menus_csv'}
        definitions, uid_links, resource_guids, selected_resource_ids = [], [], set(), set()
        resource_uids = set()
        resource_owners = set()
        if self.definition_spec is not None and (menu_ids or resource is not None):
            if self.definitions_loaded is None:
                self.definitions_loaded = self._load_definitions()
            issues.extend(self.definitions_loaded['issues'])
            definitions = self.definitions_loaded['resources']
            if resource is not None:
                definitions = [r for r in definitions if resource in (r['resource_uid'], r['internal_name'],r.get('resource_name'))
                    or any(resource in (p['resource_uid'], p['internal_name']) for p in r['parents'])]
                if related_depth:
                    selected_ids={r['resource_id'] for r in definitions}
                    for _ in range(related_depth):
                        targets={target for edge in self.definitions_loaded['links']
                            if edge['source_resource_id'] in selected_ids and edge['target_status']=='saved_definition'
                            for target in edge['target_resource_ids']}
                        selected_ids.update(targets)
                        owners={(r['resource_file'],r['resource_uid']) for r in self.definitions_loaded['resources']
                            if r['resource_id'] in selected_ids and r['resource_uid'] is not None}
                        selected_ids.update(r['resource_id'] for r in self.definitions_loaded['resources']
                            if any((r['resource_file'],p['resource_uid']) in owners for p in r['parents'] if p['resource_uid'] is not None))
                        require(len(selected_ids)<=1000,'RELATED_RESOURCE_LIMIT_EXCEEDED')
                    definitions=[r for r in self.definitions_loaded['resources'] if r['resource_id'] in selected_ids]
            selected_resource_ids = {r['resource_id'] for r in definitions}
            resource_uids = {r['resource_uid'] for r in definitions if r['resource_uid'] is not None}
            resource_owners = {(r['resource_file'], r['resource_uid']) for r in definitions}
            resource_guids = {f['guid'] for r in definitions for f in r['fields'] if f['guid'] is not None}
            uid_links = [r for r in self.definitions_loaded['links'] if r['source_resource_id'] in selected_resource_ids
                         or (resource is not None and r['target_uid'] == resource)]
        matches = []
        needle = search_text(text) if normalized and text is not None else text
        for record in records:
            if resource is not None and not (
                    (record['source_id'] in menu_ids and record['key'] in resource_guids)
                    or record.get('resource_uid') in resource_uids):
                continue
            if key is not None and key != record['key'] and key not in record.get('internal_keys', []):
                continue
            if culture is not None and record['context'].get('culture') != culture:
                continue
            if language is not None and record['context'].get('language') != language:
                continue
            if platform is not None and record['context'].get('platform') != platform:
                continue
            if needle is not None:
                value = record['text']
                if value is None or needle not in (search_text(value) if normalized else value):
                    continue
            matches.append(record)
        menu_by_key=defaultdict(list)
        for record in records:
            if record['source_id'] in menu_ids:
                menu_by_key[record['key']].append(record)
        pair_keys=sum(len({(r['context']['culture'],r['context']['language']) for r in rows})>1
                      for rows in menu_by_key.values())
        native_rows=[]
        native_by_key=defaultdict(list)
        reference_info=None
        if self.native_spec is not None and menu_ids:
            if self.native_loaded is None:
                self.native_loaded=self._load_native()
            issues.extend(self.native_loaded['issues'])
            target_ids=menu_ids & set(self.native_spec.get('target_sources',[])) if isinstance(self.native_spec,dict) else set()
            if target_ids:
                matching_keys={r['key'] for r in matches if r['source_id'] in target_ids}
                for ref in self.native_loaded['references']:
                    native_by_key[ref['guid']].append(ref)
                    if resource is not None and (ref['resource_file'],ref['resource_uid']) not in resource_owners: continue
                    if key is not None and key!=ref['guid']: continue
                    if any(v is not None for v in (text,culture,language,platform)) and ref['guid'] not in matching_keys: continue
                    linked=[r for r in menu_by_key.get(ref['guid'],[]) if r['source_id'] in target_ids]
                    native_rows.append(dict(ref,match_status='matched_saved_string' if linked else 'guid_absent_from_selected_tables',
                        string_observations=[dict(source_id=r['source_id'],observation_id=r['observation_id'],location=r['location']) for r in linked]))
                reference_info=dict(reference_count=len(self.native_loaded['references']),
                    unique_guids=len({r['guid'] for r in self.native_loaded['references']}),
                    input=self.native_loaded.get('input'),target_sources=sorted(target_ids))
        output=[]
        for original in matches[offset:offset+limit]:
            record=dict(original,relations=[dict(r) for r in original['relations']])
            if record['source_id'] in menu_ids:
                for ref in native_by_key.get(record['key'],[]):
                    details=dict(reference_id=ref['reference_id'],field=ref['field'],resource_uid=ref['resource_uid'],
                        resource_file=ref['resource_file'],resource_sha256=ref['resource_sha256'],
                        source_location=ref['location'],resource_type=ref['resource_type'],internal_name=ref['internal_name'],
                        embedded_text_literal=ref['embedded_text_literal'],enabled=ref['enabled'],entity_mapping_confirmed=False)
                    old=next((r for r in record['relations'] if r.get('kind')=='native_guid_reference'
                              and (r.get('reference_id')==ref['reference_id'] or
                                   (r.get('reference_id') is None and r.get('resource_file')==ref['resource_file']
                                    and r.get('resource_uid')==ref['resource_uid']
                                    and r.get('field',ref['field'])==ref['field']))),None)
                    if old is not None:
                        old.update(details)
                        old['expanded_evidence']=dict(file=ref['evidence_file'],pointer=ref['evidence_pointer'])
                    else:
                        record['relations'].append(dict(kind='native_guid_reference',status='evidenced_guid_lookup',
                            evidence_file=ref['evidence_file'],evidence_pointer=ref['evidence_pointer'],**details))
                peers=menu_by_key.get(record['key'],[])
                for peer in peers:
                    if (peer['context']['culture'],peer['context']['language'])==(record['context']['culture'],record['context']['language']): continue
                    unique=sum(r['source_id']==peer['source_id'] for r in peers)==sum(r['source_id']==record['source_id'] for r in peers)==1
                    record['relations'].append(dict(kind='native_localization_pair',
                        status='evidenced_same_guid_in_saved_tables' if unique else 'ambiguous_guid_records',
                        peer_source=peer['source_id'],peer_culture=peer['context']['culture'],
                        peer_observation_id=peer['observation_id'],peer_location=peer['location'],entity_mapping_confirmed=False))
            output.append(record)
        matched_keys = {r['key'] for r in matches if r['source_id'] in menu_ids}
        if resource is None and any(v is not None for v in (key, text, culture, language, platform)):
            definitions = [r for r in definitions if any(
                (key is None or f['guid']==key) and (f['guid'] in matched_keys
                    or (key is not None and text is None and culture is None and language is None and platform is None))
                for f in r['fields'])]
            selected_resource_ids = {r['resource_id'] for r in definitions}
            uid_links = [r for r in uid_links if r['source_resource_id'] in selected_resource_ids]
        resource_output = []
        selected_uids = {r['resource_uid'] for r in definitions}
        definition_conflicts = [c for c in (self.definitions_loaded or {}).get('conflicts', [])
                               if c['resource_uid'] in selected_uids]
        issues.extend(definition_conflicts)
        for row in definitions[offset:offset+limit]:
            fields = []
            for field in row['fields']:
                peers = menu_by_key.get(field['guid'], [])
                fields.append(dict(field, string_observations=[dict(source_id=p['source_id'],
                    observation_id=p['observation_id'], text=p['text'], culture=p['context']['culture'],
                    language=p['context']['language'], location=p['location']) for p in peers]))
            resource_output.append(dict(row, fields=fields))
        uid_only=[edge for edge in uid_links if edge['target_uid'] is not None]
        return dict(coverage='partial' if issues else 'selected_registered_sources_only',
                    total=len(matches), limit=limit, offset=offset, results=output,
                    native_reference_total=len(native_rows),native_references=native_rows[offset:offset+limit],
                    native_reference_source=reference_info,native_localization_pair_keys=pair_keys,
                    native_resource_total=len(definitions), native_resources=resource_output,
                    native_uid_resource_total=sum(r['resource_uid'] is not None for r in definitions),
                    native_uidless_resource_total=sum(r['resource_uid'] is None for r in definitions),
                    native_uid_link_total=len(uid_only), native_uid_links=uid_only[offset:offset+limit],
                    native_relation_total=len(uid_links),native_relations=uid_links[offset:offset+limit],
                    native_relation_kind_counts=dict(Counter(edge['kind'] for edge in uid_links)),
                    native_definition_conflicts=definition_conflicts,
                    sources=[{k:v for k,v in item.items() if k != 'records'} for item in loaded],
                    issues=issues, duplicate_source_references=self.duplicate_source_references,
                    writes_performed=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--index', default=DEFAULT_INDEX)
    parser.add_argument('--key', help='Exact string key, GUID or recorded attribute internal field key')
    parser.add_argument('--resource', help='Exact saved native UID, internal name, parent group or recorded export resource path; not a business entity ID')
    parser.add_argument('--related-depth',type=int,default=0,help='Follow saved native references 0-5 levels from --resource; default keeps direct query behavior')
    parser.add_argument('--text', help='Literal, case-sensitive substring of the original parsed value')
    parser.add_argument('--source', action='append', default=[])
    parser.add_argument('--culture', help='Exact recorded culture, e.g. neutral or en')
    parser.add_argument('--platform', help='Exact recorded platform, e.g. apk or windows')
    parser.add_argument('--language', help='Explicit language, e.g. en or zh; neutral is not zh-CN')
    parser.add_argument('--batch', help='Exact existing receipt reference or related image batch ID')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--normalized', action='store_true', help='NFKC/casefold substring search only')
    args = parser.parse_args(argv)
    try:
        result = TextLibrary(args.root, args.index).query(key=args.key, text=args.text, sources=args.source,
            culture=args.culture, language=args.language, batch=args.batch,
            limit=args.limit, offset=args.offset, normalized=args.normalized, platform=args.platform, resource=args.resource,
            related_depth=args.related_depth)
        code = 2 if result['issues'] else 0
    except (OSError, ValueError, TypeError) as error:
        result = dict(coverage='partial', results=[], writes_performed=False,
                      issues=[dict(code=error.code if isinstance(error, TextError) else 'INVALID_TEXT_INDEX')])
        code = 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
