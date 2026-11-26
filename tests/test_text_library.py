"""Isolated failure fixtures plus read-only acceptance of the pinned local corpus."""
from contextlib import redirect_stdout
import csv
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.asset_import.text_library import (
    DEFAULT_INDEX, RESOURCE_NAMESPACE, ROOT, TextError, TextLibrary, main, sha256,
)
from text_snapshot import ARCHIVED_INPUTS, HistoricalTextLibrary
from fixture_corpus import corpus_root


GUID = 'A' * 32


def menu_bytes(rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\r\n')
    writer.writerows([['2', '', '', ''], [str(len(rows)), '', '', '']] + rows)
    return stream.getvalue().encode('utf-8')


def package_metadata():
    result = {}
    for platform in ('apk', 'windows'):
        result[platform] = dict(relative_path='original/' + platform, sha256='f' * 64,
            assembly_version='29.0.0.0', assembly_sources=[dict(source_entry='assembly-' + culture,
                offset=10, resource_streams=[dict(name=RESOURCE_NAMESPACE + ('.en.resources' if culture == 'en' else '.resources'),
                sha256=('e' if culture == 'en' else 'c') * 64, offset=0)]) for culture in ('neutral', 'en')])
    return result


def attribute(key='K', zh='中文', en='English'):
    return dict(localization_key=key, source_platforms=['apk', 'windows'], display_name_zh=zh,
        display_name_en=en, chinese_name=zh, chinese_name_source='default_resource',
        localization_key_status='shared_resource_key', internal_keys=['AppData::' + key],
        status='bilingual', variants=[dict(raw_value=0, unit='')], source_locations=[],
        english_aliases_from_app_dictionary=[], evidence=[dict(kind='resource_key_value', key=key,
            culture=culture, value=value, source_location=dict(platform=platform))
            for platform in ('apk', 'windows') for culture, value in [('neutral', zh), ('en', en)]])


class TextLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TD2_TEXT_LIBRARY_TEST_TMP'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        self.index = dict(schema_version=1, sources=[])
        self.save_index()

    def put(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def write(self, name, data):
        return self.put(name, (json.dumps(data, ensure_ascii=False) + '\n').encode('utf-8'))

    def ref(self, name):
        return dict(file=name, sha256=sha256((self.root / name).read_bytes()))

    def save_index(self):
        self.write('index.json', self.index)

    def wire(self, fmt, data, name='one', evidence=None):
        filename = name + ('.locpack' if fmt == 'menus_csv' else '.json')
        self.put(filename, data) if isinstance(data, bytes) else self.write(filename, data)
        source = dict(id=name, format=fmt, **self.ref(filename), batch_ref='existing-review', evidence={})
        if fmt == 'menus_csv':
            evidence = evidence or dict(
                provenance=dict(immutable_input_copies=[dict(original_path='old/english/menus.locpack',
                    snapshot=filename, sha256=source['sha256'])]),
                guid_references=dict(game_brands=[], target_name_associations=[]))
        for role, doc in (evidence or {}).items():
            p = name + '-' + role + '.json'
            self.write(p, doc)
            source['evidence'][role] = self.ref(p)
        self.index['sources'].append(source)
        self.save_index()
        return source

    def wire_attributes(self, rows, name='attributes'):
        localization = {p:dict(tables=[dict(culture=c, resource_sha256=('e' if c=='en' else 'c')*64,
            candidate_strings={r['localization_key']:r.get(f)
            for r in rows}) for c,f in [('neutral','display_name_zh'),('en','display_name_en')]])
            for p in ('apk', 'windows')}
        return self.wire('attributes_json', rows, name,
                         dict(packages=package_metadata(), localization=localization))

    def wire_resources(self, overrides=None, missing=()):
        packages = package_metadata()
        data = dict(schema_version=1, parser_rule='dotnet_resources_v2_strings@1', tables=[])
        evidence = dict(parser_rule=data['parser_rule'], tables=[])
        for platform in ('apk','windows'):
            for culture in ('neutral','en'):
                if (platform,culture) in missing:
                    continue
                rows = (overrides or {}).get((platform,culture), [dict(key='K',text='Value',status='string')])
                records = [dict(row, entry_index=j, name_offset=100+j, data_offset=200+j) for j,row in enumerate(rows)]
                resource = packages[platform]['assembly_sources'][culture=='en']['resource_streams'][0]
                table = dict(platform=platform, culture=culture, resource_name=resource['name'],
                             resource_sha256=resource['sha256'])
                stats = dict(declared_entries=len(rows), **{name:sum(r['status']==status for r in rows)
                    for name,status in [('string_values','string'),('null_values','null'),
                                        ('non_string_values','non_string'),('parse_errors','parse_error')]})
                data['tables'].append(dict(table, evidence_pointer='/tables/'+str(len(evidence['tables'])), records=records))
                evidence['tables'].append(dict(table, stats=stats, raw_resource=dict(file='raw/'+platform+'/'+culture,
                                                                                    sha256=resource['sha256'])))
        source = self.wire('app_resources', data, evidence=dict(packages=packages, bindings=dict(bindings=[]), extraction=evidence))
        evidence['output'] = dict(file=source['file'], sha256=source['sha256'])
        self.write(source['evidence']['extraction']['file'], evidence)
        source['evidence']['extraction'].update(self.ref(source['evidence']['extraction']['file']))
        self.save_index()
        return source

    def load(self):
        return TextLibrary(self.root, 'index.json')

    def query(self, **kwargs):
        return self.load().query(**kwargs)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix():(sha256(p.read_bytes()), p.stat().st_mtime_ns)
                for p in self.root.rglob('*') if p.is_file()}

    def test_csv_quotes_commas_multiline_placeholders_controls_and_columns(self):
        value = 'Hello, "agent"\n{0}\r\n<color name="orange">\\n\t\x01'
        self.wire('menus_csv', menu_bytes([[GUID, '19', value, 'uninterpreted']]))
        result = self.query(key=GUID)
        self.assertEqual([], result['issues'])
        record = result['results'][0]
        self.assertEqual(value, record['text'])
        self.assertEqual([GUID, '19', value, 'uninterpreted'], record['raw_columns'])
        self.assertEqual(3, record['location']['line_start'])
        self.assertEqual(5, record['location']['line_end'])
        self.assertEqual(sha256(value.encode('utf-8')), record['text_sha256'])

    def test_empty_csv_text_is_a_value(self):
        self.wire('menus_csv', menu_bytes([[GUID, '0', '', '']]))
        record = self.query()['results'][0]
        self.assertEqual(('', 'text'), (record['text'], record['value_state']))

    def test_bom_newlines_and_json_escapes_change_observations_not_logical_identity(self):
        data = b'{"attributes":[{"id":"bonus_k","zh_name":"\\u4e2d","en_name":"E"}]}'
        source = self.wire('business_bonuses', data)
        before = self.query(language='zh')['results'][0]
        alternate = b'\xef\xbb\xbf' + data.replace(b'\\u4e2d', '中'.encode('utf-8')) + b'\r\n'
        self.put(source['file'], alternate)
        source.update(self.ref(source['file']))
        self.save_index()
        after = self.query(language='zh')['results'][0]
        self.assertEqual(before['logical_id'], after['logical_id'])
        self.assertEqual(before['text_sha256'], after['text_sha256'])
        self.assertNotEqual(before['observation_id'], after['observation_id'])
        self.assertTrue(self.query()['sources'][0]['inputs'][0]['bom'])

    def test_array_reordering_does_not_change_logical_identity(self):
        rows = [dict(id='bonus_a', zh_name='A', en_name='A'), dict(id='bonus_b', zh_name='B', en_name='B')]
        source = self.wire('business_bonuses', dict(attributes=rows))
        before = self.query(key='bonus_a', language='zh')['results'][0]
        self.write(source['file'], dict(attributes=list(reversed(rows))))
        source.update(self.ref(source['file'])); self.save_index()
        after = self.query(key='bonus_a', language='zh')['results'][0]
        self.assertEqual(before['logical_id'], after['logical_id'])
        self.assertNotEqual(before['observation_id'], after['observation_id'])
        self.assertNotEqual(before['location'], after['location'])

    def test_identical_bytes_and_text_in_different_sources_are_retained(self):
        data = dict(attributes=[dict(id='bonus_a', zh_name='Same', en_name='Same')])
        self.wire('business_bonuses', data, 'a'); self.wire('business_bonuses', data, 'b')
        rows = self.query(text='Same', language='en')['results']
        self.assertEqual(2, len(rows))
        self.assertEqual(1, len({r['input_sha256'] for r in rows}))
        self.assertEqual(1, len({r['text_sha256'] for r in rows}))
        self.assertEqual(2, len({r['observation_id'] for r in rows}))

    def test_same_text_different_keys_is_not_merged(self):
        self.wire('menus_csv', menu_bytes([[GUID, '0', 'Same', ''], ['B'*32, '0', 'Same', '']]))
        rows = self.query(text='Same')['results']
        self.assertEqual(2, len({r['logical_id'] for r in rows}))

    def test_different_snapshot_values_share_logical_identity_without_overwrite(self):
        for name,value in [('old','Old name'),('new','New name')]:
            self.wire('business_bonuses',dict(attributes=[dict(id='bonus_a',zh_name=value,en_name=value)]),name)
        out=self.query(key='bonus_a',language='en')
        self.assertEqual({'Old name','New name'},{r['text'] for r in out['results']})
        self.assertEqual(1,len({r['logical_id'] for r in out['results']}))
        self.assertEqual(2,len({r['context']['revision'] for r in out['results']}))
        self.assertEqual([],out['issues'])

    def test_unapproved_brand_name_is_not_exposed(self):
        self.wire('business_brands',dict(brands=[dict(entity_key='brand_a',zh_name='候选',en_name='Candidate',
            name_policy=dict(business_name_approved=False))]))
        out=self.query()
        self.assertEqual(0,out['total'])
        self.assertEqual('BUSINESS_NAME_NOT_APPROVED',out['issues'][0]['code'])

    def test_same_key_different_cultures_and_platforms_is_retained(self):
        tables = {'apk':{'K':'中'},'apk-en':{'K':'E'},'windows':{'K':'中'},'windows-en':{'K':'E'}}
        self.wire('app_names', tables, evidence=dict(packages=package_metadata(), bindings=dict(bindings=[])))
        result = self.query(key='K')
        self.assertEqual(4, result['total'])
        self.assertEqual(4, len({r['logical_id'] for r in result['results']}))
        self.assertEqual(2, self.query(culture='neutral')['total'])
        self.assertTrue(all(r['context']['language'] is None for r in self.query(culture='neutral')['results']))
        self.assertEqual(0, self.query(language='zh-CN')['total'])
        self.assertTrue(all(r['context']['game_version'] is None for r in result['results']))

    def test_full_resources_preserve_binary_locations_and_independent_pairs(self):
        value = '\ufeff中, "quote"\r\n{0}<tag>\\r\\n\x01'
        self.wire_resources({('apk','neutral'):[dict(key='K',text=value,status='string')]})
        out = self.query(key='K')
        self.assertEqual([], out['issues'])
        self.assertEqual(4, len({r['logical_id'] for r in out['results']}))
        row = self.query(culture='neutral')['results'][0]
        self.assertEqual(value, row['text'])
        self.assertEqual(0, row['resource_location']['entry_index'])
        self.assertEqual('raw/apk/neutral', row['resource_location']['file'])
        self.assertEqual('evidenced_same_resource_key', row['relations'][0]['status'])
        self.assertIsNone(row['context']['language'])
        self.assertEqual(1, self.query(platform='windows',culture='en')['total'])
        self.assertEqual(0, self.query(platform='unknown')['total'])

    def test_full_resources_empty_null_non_string_and_failed_values_stay_distinct(self):
        self.wire_resources({('apk','neutral'):[
            dict(key='Empty',text='',status='string'), dict(key='Null',text=None,status='null'),
            dict(key='Object',text=None,status='non_string',type_code=64),
            dict(key='Bad',text=None,status='parse_error',error='INVALID_RESOURCE_VALUE'),
            dict(key=None,text=None,status='parse_error',error='INVALID_RESOURCE_NAME')]})
        out = self.query(culture='neutral')
        states = {r['key']:r['value_state'] for r in out['results']}
        self.assertEqual(('text','null','missing','missing'), tuple(states[k] for k in ('Empty','Null','Object','Bad')))
        self.assertEqual(2, len(out['issues']))
        self.assertEqual('partial', out['coverage'])
        self.assertEqual(8, out['sources'][0]['stats']['input_records'])

    def test_full_resources_duplicate_keys_report_ambiguity_and_conflicts(self):
        self.wire_resources({('apk','neutral'):[dict(key='K',text=v,status='string') for v in ['A','B','A']]})
        out = self.query(key='K')
        self.assertEqual(6, out['total'])
        self.assertEqual({'DUPLICATE_RESOURCE_KEY','LOGICAL_CONTEXT_CONFLICT'}, {r['code'] for r in out['issues']})
        self.assertEqual('ambiguous_or_unrecoverable_peer', out['results'][0]['relations'][0]['status'])

    def test_full_resources_missing_table_is_explicit_with_other_tables_available(self):
        self.wire_resources(missing=[('windows','en')])
        out = self.query()
        self.assertEqual(3, out['total'])
        self.assertEqual('TARGET_TABLE_MISSING', out['issues'][0]['code'])

    def test_full_resources_manifest_count_and_output_must_match(self):
        source = self.wire_resources()
        spec = source['evidence']['extraction']
        evidence = json.loads((self.root/spec['file']).read_bytes())
        evidence['tables'][0]['stats']['string_values'] = 0
        self.write(spec['file'], evidence); spec.update(self.ref(spec['file'])); self.save_index()
        self.assertEqual('APP_RESOURCE_COUNT_CONFLICT', self.query()['issues'][0]['code'])
        evidence['output']['sha256'] = '0'*64
        self.write(spec['file'], evidence); spec.update(self.ref(spec['file'])); self.save_index()
        self.assertEqual('APP_RESOURCE_OUTPUT_CONFLICT', self.query()['issues'][0]['code'])

    def test_null_missing_and_empty_business_fields_are_distinct(self):
        self.wire('business_bonuses', dict(attributes=[dict(id='a',zh_name=''),dict(id='b',zh_name=None),dict(id='c')]))
        rows = self.query(language='zh')['results']
        self.assertEqual(['text','null','missing'], [r['value_state'] for r in rows])
        self.assertEqual(['',None,None], [r['text'] for r in rows])

    def test_attributes_preserve_pairs_internal_keys_and_variant_locations(self):
        self.wire_attributes([attribute()])
        result = self.query(key='AppData::K')
        self.assertEqual(4, result['total'])
        self.assertTrue(all(r['relations'][0]['status']=='evidenced_constructor_resource_key' for r in result['results']))
        self.assertTrue(all(r['variant_count']==1 and r['variants_pointer']=='/0/variants' for r in result['results']))

    def test_constructor_literal_does_not_become_neutral_resource_value(self):
        row = attribute(zh=None,en=None)
        row.update(status='missing_english',chinese_name='构造字面值',chinese_name_source='constructor_literal', evidence=[],
                   source_locations=[dict(platform=p,il_offset=1) for p in ('apk','windows')])
        self.wire_attributes([row])
        rows = self.query(text='构造字面值')['results']
        self.assertEqual(2, len(rows))
        self.assertTrue(all(r['value_kind']=='constructor_literal' and r['context']['culture'] is None for r in rows))
        self.assertTrue(all('resource' not in r['context']['provenance'] for r in rows))
        self.assertEqual(0, self.query(culture='neutral', text='构造字面值')['total'])

    def test_dictionary_aliases_have_own_keys_and_no_official_translation_claim(self):
        row=attribute()
        row['english_aliases_from_app_dictionary']=[dict(input_name=x,output_internal_name='K',
            source_locations=[dict(platform=p,field='TranslateDictionary') for p in ('apk','windows')]) for x in ['Full name','Other name']]
        self.wire_attributes([row])
        result=self.query(key='Full name')
        self.assertEqual(2,result['total'])
        self.assertEqual([],result['issues'])
        self.assertTrue(all(r['value_kind']=='dictionary_alias' and r['context']['culture'] is None for r in result['results']))
        self.assertTrue(all('resource' not in r['context']['provenance'] for r in result['results']))
        self.assertEqual(8,self.query(key='K')['total'])

    def test_attribute_missing_field_is_reported_as_missing(self):
        row=attribute();del row['display_name_en'];row['status']='partial'
        self.wire_attributes([row])
        self.assertEqual({'missing'},{r['value_state'] for r in self.query(culture='en')['results']})

    def test_attribute_language_evidence_mismatch_fails_source_atomically(self):
        row=attribute();row['evidence'][0]['value']='changed'
        self.wire_attributes([row])
        out=self.query()
        self.assertEqual(0,out['total'])
        self.assertEqual('ATTRIBUTE_LANGUAGE_EVIDENCE_CONFLICT',out['issues'][0]['code'])

    def test_attribute_resource_revision_must_match_recorded_package(self):
        source=self.wire_attributes([attribute()])
        spec=source['evidence']['localization'];doc=json.loads((self.root/spec['file']).read_bytes())
        doc['apk']['tables'][0]['resource_sha256']='0'*64
        self.write(spec['file'],doc);spec.update(self.ref(spec['file']));self.save_index()
        self.assertEqual('ATTRIBUTE_RESOURCE_REVISION_CONFLICT',self.query()['issues'][0]['code'])

    def test_evidence_version_change_changes_observation_but_not_logical_identity(self):
        source=self.wire_attributes([attribute()])
        before=self.query(key='K',culture='en')['results'][0]
        spec=source['evidence']['packages'];doc=json.loads((self.root/spec['file']).read_bytes())
        doc['apk']['assembly_version']='30.0.0.0'
        self.write(spec['file'],doc);spec.update(self.ref(spec['file']));self.save_index()
        after=self.query(key='K',culture='en')['results'][0]
        self.assertEqual(before['logical_id'],after['logical_id'])
        self.assertNotEqual(before['observation_id'],after['observation_id'])
        self.assertNotEqual(before['source_snapshot_id'],after['source_snapshot_id'])
        self.assertIsNone(after['context']['game_version'])

    def test_dictionary_same_input_with_different_outputs_reports_conflict(self):
        rows=[attribute('A'),attribute('B')]
        for row in rows:
            row['english_aliases_from_app_dictionary']=[dict(input_name='Same input',output_internal_name=row['localization_key'],
                source_locations=[dict(platform=p,field='TranslateDictionary') for p in ('apk','windows')])]
        self.wire_attributes(rows)
        out=self.query(key='Same input')
        self.assertEqual(4,out['total'])
        self.assertEqual(2,len(out['issues']))
        self.assertEqual({'A','B'},{r['dictionary_output_key'] for r in out['results']})

    def test_duplicate_json_key_is_not_silently_overwritten(self):
        self.wire('business_bonuses',b'{"attributes":[],"attributes":[]}')
        self.assertEqual('DUPLICATE_JSON_KEY',self.query()['issues'][0]['code'])

    def test_duplicate_index_json_key_is_rejected(self):
        self.put('index.json',b'{"schema_version":1,"sources":[],"sources":[]}')
        with self.assertRaisesRegex(TextError,'DUPLICATE_JSON_KEY'):self.load()

    def test_conflicting_guid_values_keep_both_and_report_conflict(self):
        self.wire('menus_csv',menu_bytes([[GUID,'0','First',''],[GUID,'0','Second','']]))
        out=self.query(key=GUID)
        self.assertEqual(2,out['total'])
        self.assertEqual('partial',out['coverage'])
        self.assertEqual('LOGICAL_CONTEXT_CONFLICT',out['issues'][0]['code'])

    def test_conflict_report_retains_all_duplicate_observation_locations(self):
        self.wire('menus_csv',menu_bytes([[GUID,'0',x,''] for x in ['A','B','A']]))
        out=self.query()
        self.assertEqual(3,len(out['issues'][0]['observations']))

    def test_identical_duplicate_guid_rows_remain_separate_observations(self):
        self.wire('menus_csv',menu_bytes([[GUID,'0','Same',''],[GUID,'0','Same','']]))
        out=self.query()
        self.assertEqual([],out['issues'])
        self.assertEqual(2,len({r['observation_id'] for r in out['results']}))

    def test_unknown_menu_metadata_difference_is_not_discarded(self):
        self.wire('menus_csv',menu_bytes([[GUID,'0','Same',''],[GUID,'1','Same','']]))
        self.assertEqual('LOGICAL_CONTEXT_CONFLICT',self.query()['issues'][0]['code'])

    def test_identical_source_registration_is_idempotent(self):
        source=self.wire('business_bonuses',dict(attributes=[]))
        self.index['sources'].append(dict(source));self.save_index()
        out=self.query()
        self.assertEqual(1,len(out['sources']))
        self.assertEqual(1,out['duplicate_source_references'])

    def test_changed_duplicate_source_id_is_an_error(self):
        source=self.wire('business_bonuses',dict(attributes=[]))
        self.index['sources'].append(dict(source,sha256='0'*64));self.save_index()
        with self.assertRaisesRegex(TextError,'SOURCE_ID_CONFLICT'):self.load()

    def test_loading_is_demand_driven_and_missing_source_makes_coverage_partial(self):
        self.wire('business_bonuses',dict(attributes=[]),'good')
        bad=self.wire('business_bonuses',dict(attributes=[]),'bad')
        (self.root/bad['file']).unlink()
        self.assertEqual([],self.query(sources=['good'])['issues'])
        out=self.query()
        self.assertEqual('partial',out['coverage'])
        self.assertEqual('INPUT_MISSING',out['issues'][0]['code'])

    def test_hash_change_is_rejected_before_parsing(self):
        source=self.wire('business_bonuses',dict(attributes=[]))
        self.put(source['file'],b'not JSON')
        self.assertEqual('INPUT_HASH_MISMATCH',self.query()['issues'][0]['code'])

    def test_evidence_hash_change_also_fails_with_its_file(self):
        source=self.wire('menus_csv',menu_bytes([[GUID,'0','x','']]))
        name=source['evidence']['provenance']['file'];self.put(name,b'{}')
        issue=self.query()['issues'][0]
        self.assertEqual(('INPUT_HASH_MISMATCH',name),(issue['code'],issue['file']))

    def test_unsafe_relative_absolute_and_hidden_paths_are_rejected(self):
        source=self.wire('business_bonuses',dict(attributes=[]))
        for path in ['../outside.json',str(self.root/'one.json'),'.env.json','sub/../one.json','sub\\one.json']:
            with self.subTest(path=path):
                source['file']=path;self.save_index()
                self.assertEqual('UNSAFE_PATH',self.query()['issues'][0]['code'])

    def test_resolved_path_outside_root_is_rejected(self):
        self.wire('business_bonuses',dict(attributes=[]))
        library=self.load()
        with patch.object(Path,'resolve',return_value=Path(self.temp.name)):
            self.assertEqual('PATH_OUTSIDE_ROOT',library.query()['issues'][0]['code'])

    def test_invalid_utf8_and_utf16_are_explicit_failures(self):
        for i,raw in enumerate([b'\xff', '{"attributes":[]}'.encode('utf-16')]):
            self.index['sources']=[]
            self.wire('business_bonuses',raw,str(i))
            self.assertEqual('INVALID_UTF8',self.query()['issues'][0]['code'])

    def test_invalid_json_and_unsupported_format_fail_explicitly(self):
        source=self.wire('business_bonuses',b'{')
        self.assertEqual('INVALID_JSON',self.query()['issues'][0]['code'])
        source['format']='native_binary';self.save_index()
        self.assertEqual('UNSUPPORTED_TEXT_FORMAT',self.query()['issues'][0]['code'])

    def test_csv_bad_count_shape_and_quotation_fail_atomically(self):
        for raw,code in [(b'2,,,\r\n2,,,\r\n'+(GUID+',0,x,\r\n').encode(),'MENU_COUNT_MISMATCH'),
                         (b'2,,,\r\n1,,,\r\n'+(GUID+',0,x\r\n').encode(),'INVALID_MENU_RECORD'),
                         (b'2,,,\r\n1,,,\r\n'+(GUID+',0,"unterminated,\r\n').encode(),'INVALID_SOURCE_DATA')]:
            self.index['sources']=[];self.wire('menus_csv',raw)
            out=self.query();self.assertEqual(0,out['total']);self.assertEqual(code,out['issues'][0]['code'])

    def test_normalization_only_changes_search_matching(self):
        self.wire('business_bonuses',dict(attributes=[dict(id='k',zh_name='ＡBc',en_name='ＡBc')]))
        self.assertEqual(0,self.query(text='abc')['total'])
        record=self.query(text='abc',normalized=True,language='en')['results'][0]
        raw=self.query(language='en')['results'][0]
        self.assertEqual(('ＡBc',raw['observation_id']),(record['text'],record['observation_id']))
        self.assertEqual(0,self.query(key='K',normalized=True)['total'])

    def test_source_batch_pagination_and_unknown_filters(self):
        self.wire('business_bonuses',dict(attributes=[dict(id='x',zh_name='中',en_name='E')]))
        self.assertEqual(2,self.query(batch='existing-review',limit=1,offset=1)['total'])
        self.assertEqual(1,len(self.query(limit=1,offset=1)['results']))
        for kwargs,code in [(dict(sources=['no']),'UNKNOWN_TEXT_SOURCE'),(dict(batch='no'),'UNKNOWN_BATCH_REFERENCE'),
                            (dict(limit=0),'INVALID_PAGINATION')]:
            with self.assertRaisesRegex(TextError,code):self.query(**kwargs)

    def test_query_and_cli_have_no_writes_or_new_files(self):
        self.wire('menus_csv',menu_bytes([[GUID,'0','{0} <tag>','']]))
        before=self.snapshot()
        with patch.object(Path,'write_bytes',side_effect=AssertionError('write')), \
             patch.object(Path,'write_text',side_effect=AssertionError('write')), \
             patch.object(Path,'mkdir',side_effect=AssertionError('mkdir')), \
             patch.object(Path,'unlink',side_effect=AssertionError('unlink')):
            self.assertEqual(1,self.query(key=GUID)['total'])
            stream=io.StringIO()
            with redirect_stdout(stream):code=main(['--root',str(self.root),'--index','index.json','--key',GUID])
            self.assertEqual(0,code);self.assertFalse(json.loads(stream.getvalue())['writes_performed'])
        self.assertEqual(before,self.snapshot())

    def test_cli_returns_json_and_nonzero_for_incomplete_inputs(self):
        source=self.wire('business_bonuses',dict(attributes=[]));self.put(source['file'],b'changed')
        stream=io.StringIO()
        with redirect_stdout(stream):code=main(['--root',str(self.root),'--index','index.json'])
        self.assertEqual(2,code);self.assertEqual('partial',json.loads(stream.getvalue())['coverage'])


class ExistingTextCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=corpus_root()
        cls.library=TextLibrary(root=cls.root)
        cls.result=cls.library.query(limit=1)
        cls.historical=HistoricalTextLibrary()
        cls.historical_result=cls.historical.query(limit=1)

    def test_all_registered_real_sources_load_without_issues(self):
        self.assertEqual([], self.result['issues'])
        self.assertTrue(all(not s['issues'] for s in self.result['sources']))
        self.assertEqual(set(self.library.sources), {s['source_id'] for s in self.result['sources']})
        self.assertTrue(all(s['stats']['input_records'] > 0 for s in self.result['sources']))
        self.assertEqual('selected_registered_sources_only', self.result['coverage'])
        self.assertFalse(self.result['writes_performed'])
        self.assertEqual(['NATIVE_UID_DEFINITION_CONFLICT']*2,[r['code'] for r in self.historical_result['issues']])
        self.assertTrue(all(not s['issues'] for s in self.historical_result['sources']))
        counts={s['source_id']:s['stats']['input_records'] for s in self.historical_result['sources']}
        self.assertEqual({'game-english-menus':71206,'app-localization':8620,'app-attributes':72,
                          'business-brands':26,'business-bonuses':5,'game-chinesegav-menus':65029,
                          'app-dictionary':864,'native-literals':3,'game-simplifiedchinese-menus':70148},counts)

    def assert_current_native_registration(self, index):
        targets={'game-english-menus','game-simplifiedchinese-menus'}
        sources={s['id']:s for s in index['sources']}
        provenance=[sources[key]['manual_provenance'] for key in sorted(targets)]
        self.assertTrue(all(p['origin']=='USER_SUPPLIED_MANUAL_EXPORT' for p in provenance))
        identity={(p['current_manual_dataset_id'],p['source_container_sha256']) for p in provenance}
        self.assertEqual(1,len(identity))
        dataset,container=next(iter(identity))
        self.assertTrue(dataset and container)
        documents={}
        for key in ('native_definitions','native_references'):
            self.assertIn(key,index)
            _,text,_=self.library._read(index[key])
            documents[key]=json.loads(text)
            self.assertTrue(documents[key]['files'])
            for row in documents[key]['files']:
                self.assertEqual(dataset,row.get('manual_provenance',{}).get('current_manual_dataset_id'),row['file'])
                self.assertEqual(container,row.get('source_container_sha256'),row['file'])
        self.assertEqual(dataset,documents['native_definitions']['current_manual_dataset_id'])
        self.assertEqual(targets,set(index['native_references']['target_sources']))
        definitions={(r['file'],r['sha256']) for r in documents['native_definitions']['files']}
        references={(r['file'],r['sha256']) for r in documents['native_references']['files']}
        self.assertLessEqual(references,definitions)

    def test_current_native_graph_is_required_and_bound_to_current_manual_input(self):
        self.assert_current_native_registration(json.loads((self.root/DEFAULT_INDEX).read_bytes()))
        for key in ('native_resource_total','native_reference_total','native_uid_link_total','native_relation_total'):
            self.assertGreater(self.result[key],0,key)

    def test_current_native_guard_rejects_missing_historical_and_hash_mismatched_graphs(self):
        current=json.loads((self.root/DEFAULT_INDEX).read_bytes())
        historical={'native_definitions':self.historical.definition_spec,'native_references':self.historical.native_spec}
        for key in historical:
            with self.subTest(key=key,mutation='missing'):
                mutant=dict(current);del mutant[key]
                with self.assertRaises(AssertionError):self.assert_current_native_registration(mutant)
            with self.subTest(key=key,mutation='historical'):
                with self.assertRaises(AssertionError):self.assert_current_native_registration({**current,key:historical[key]})
            with self.subTest(key=key,mutation='hash'):
                with self.assertRaisesRegex(TextError,'INPUT_HASH_MISMATCH'):
                    self.assert_current_native_registration({**current,key:{**current[key],'sha256':'0'*64}})

    def test_current_named_item_brand_preset_and_blueprint_uid_chain(self):
        item='5D4179F15D7789A50003580F023071EC'
        out=self.library.query(resource=item,related_depth=1,limit=100)
        row=next(r for r in out['native_resources'] if r['resource_uid']==item)
        self.assertEqual('ArmorItem',row['resource_type'])
        self.assertEqual('player_gear_gloves_511_named_01',row['internal_name'])
        blob=(self.root/row['resource_file']).read_bytes();location=row['location']
        self.assertEqual(row['resource_sha256'],sha256(blob))
        self.assertEqual(row['definition_sha256'],sha256(blob[location['byte_start']:location['byte_end']]))
        links=out['native_uid_links']
        for field,source,target,status in [
            ('myGearBrand',item,'4CDCE5B25C4057F200032204474DAA22','saved_definition'),
            ('myItemGenerationConfig',item,'5D4179F15D7904EA000344862B57279F','definition_not_saved'),
            ('myCraftedItem','B1A7497A655C9F9A000536C1BF617A4C',item,'saved_definition'),
            ('myPresetAttribute',None,'5D4179F15BF55A5200032C69B6DF1572','saved_definition'),
        ]:
            with self.subTest(field=field):
                edges=[e for e in links if (e['field'],e.get('source_uid'),e['target_uid'])==(field,source,target)]
                self.assertTrue(edges)
                self.assertTrue(all(e['target_status']==status for e in edges))
                self.assertTrue(all(not e['entity_mapping_confirmed'] for e in edges))
        self.assertFalse(row['entity_mapping_confirmed'])
        self.assertEqual([],out['issues'])

    def test_current_localization_guid_links_real_observations_without_becoming_resource_uid(self):
        uid='4CDCE5B25C4057F200032204474DAA22';guid='4CDCE5B25C4057F2000322017B35A809'
        out=self.library.query(resource=uid,limit=100)
        ref=next(r for r in out['native_references'] if r['guid']==guid and r['field']=='myName')
        self.assertEqual(uid,ref['resource_uid'])
        self.assertNotEqual(uid,guid)
        self.assertEqual('matched_saved_string',ref['match_status'])
        observations={r['observation_id']:r for r in out['results']}
        self.assertEqual({'game-english-menus','game-simplifiedchinese-menus'},{r['source_id'] for r in ref['string_observations']})
        for link in ref['string_observations']:
            row=observations[link['observation_id']];source=self.library.sources[link['source_id']]
            self.assertEqual((guid,'5.11 Tactical'),(row['key'],row['text']))
            self.assertEqual(source['sha256'],row['input_sha256'])
            self.assertEqual(source['file'],row['location']['file'])
            self.assertEqual(row['location'],link['location'])
        blob=(self.root/ref['resource_file']).read_bytes();location=ref['location']
        self.assertEqual(ref['raw_field_sha256'],sha256(blob[location['byte_start']:location['byte_end']]))
        self.assertEqual(guid,blob[location['guid_byte_start']:location['guid_byte_end']].decode('ascii'))
        self.assertFalse(ref['entity_mapping_confirmed'])

    def test_current_talent_retains_distinct_default_pvp_and_dungeon_parameters(self):
        out=self.library.query(resource='B005013569A58E9700158B612CC26177',limit=100)
        row=next(r for r in out['native_resources'] if r['resource_uid']=='B005013569A58E9700158B612CC26177')
        values=[p for p in row['properties'] if p['field']=='myValue']
        self.assertEqual(['0.22'],[p['raw_value'] for p in values if any(c['internal_name']=='PVP' for c in p['context'])])
        self.assertEqual(['0.2'],[p['raw_value'] for p in values if not any(c['internal_name']=='PVP' for c in p['context'])])
        curve=[p for p in row['properties'] if p['field'] in ('myB','myC')]
        self.assertEqual({'myB':'0.1','myC':'0.0'},{p['field']:p['raw_value'] for p in curve})
        self.assertTrue(all(any(c['resource_type']=='mySurvivalDungeonTalentOverrides' for c in p['context']) for p in curve))
        blob=(self.root/row['resource_file']).read_bytes();location=row['location']
        self.assertEqual(row['definition_sha256'],sha256(blob[location['byte_start']:location['byte_end']]))
        self.assertFalse(row['entity_mapping_confirmed'])
        self.assertEqual([],out['issues'])

    def test_real_simplified_5_11_names_keep_audited_text_and_identity(self):
        audit=json.loads((self.root/'dist/text-locale-audit-20261018-001/comparison.json').read_bytes())
        actual={r['key']:r for r in self.historical.loaded['game-simplifiedchinese-menus']['records']}
        count=0
        for entity in audit['rows']:
            for field in entity['name_fields']:
                expected=field['values']['simplifiedchinese'];row=actual[field['guid']]
                self.assertEqual(expected['text'],row['text'])
                self.assertEqual(expected['observation_id'],row['observation_id'])
                self.assertEqual(expected['location'],row['location'])
                self.assertEqual(('simplifiedchinese','zh-CN'),(row['context']['culture'],row['context']['language']))
                count+=1
        self.assertEqual(19,count)

    def test_real_defaults_prefer_simplified_without_relabeling_gav(self):
        guid='5D4179F15D7789A40003580E6E77EBA0'
        row=self.library.query(key=guid,limit=1)['results'][0]
        self.assertEqual(('game-simplifiedchinese-menus','<color name="legendary_orange">死亡之握</color>'),
                         (row['source_id'],row['text']))
        gav=self.library.query(key=guid,culture='chinesegav')['results'][0]
        self.assertEqual(('<color name="legendary_orange">暗影之握</color>',None),
                         (gav['text'],gav['context']['language']))
        self.assertNotEqual(row['observation_id'],gav['observation_id'])
        keeper=self.library.query(key='B00501356A6B4D4E001AF7AD34C41527',language='zh-CN')
        self.assertEqual(1,keeper['total'])
        self.assertIn('看守人',keeper['results'][0]['text'])
        self.assertEqual(0,self.library.query(key=guid,language='zh')['total'])
        self.assertNotIn('game-traditionalchinese-menus',self.library.sources)

    def test_real_menu_guid_content_and_physical_line(self):
        out=self.historical.query(sources=['game-english-menus'],key='4CDCE5B25C4057F2000322017B35A809')
        row=out['results'][0]
        self.assertEqual((1,'5.11 Tactical',24468),(out['total'],row['text'],row['location']['line_start']))
        self.assertEqual('4CDCE5B25C4057F2000322017B35A809',row['raw_columns'][0])
        self.assertTrue(any(r['kind']=='native_guid_reference' for r in row['relations']))
        self.assertTrue(all(r.get('entity_mapping_confirmed') is False for r in row['relations']))

    def test_real_menu_multiline_and_format_markers_survive(self):
        row=self.library.query(key='5D3469FD5A8AACB100012C23A6BADC05',sources=['game-english-menus'])['results'][0]
        self.assertIn('\n',row['text']);self.assertEqual((1193,1194),(row['location']['line_start'],row['location']['line_end']))
        row=self.library.query(key='C3512A2C594917B80004BA11E4F7A9C1',sources=['game-english-menus'])['results'][0]
        self.assertIn('{0}',row['text'])

    def test_real_attributes_all_keys_pairs_and_unknowns_survive(self):
        out=self.library.query(sources=['app-attributes'],limit=1000)
        resource=[r for r in out['results'] if r['value_kind']=='resource_value']
        self.assertEqual(72,len({r['key'] for r in resource}))
        self.assertEqual(276,sum(bool(r['relations']) for r in resource))
        self.assertEqual(12,sum(r['value_state']=='null' for r in resource))
        self.assertEqual(4,len([r for r in out['results'] if r['value_kind']=='constructor_literal']))
        self.assertTrue(all(r['context']['language'] is None for r in resource if r['context']['culture']=='neutral'))

    def test_real_full_localization_includes_every_old_value(self):
        data = json.loads((self.root/'dist/asset-import/game-localization-evidence.json').read_bytes())
        self.library.query(sources=['app-localization'])
        actual = {(r['context']['platform'],r['context']['culture'],r['key']):r['text']
                  for r in self.library.loaded['app-localization']['records']}
        self.assertEqual(8620, len(actual))
        for label, values in data.items():
            platform = 'apk' if label.startswith('apk') else 'windows'
            culture = 'en' if label.endswith('-en') else 'neutral'
            for key, value in values.items():
                self.assertEqual(value, actual[platform,culture,key])

    def test_real_full_localization_descriptions_escapes_empty_values_and_pairs(self):
        out = self.library.query(sources=['app-localization'], key='电击器A', culture='en')
        self.assertEqual(2, out['total'])
        self.assertTrue(all('Shocker Punch' in r['text'] and r['text'].count('\r\n')==4 for r in out['results']))
        self.assertTrue(all(r['relations'][0]['status']=='evidenced_same_resource_key' for r in out['results']))
        empty = self.library.query(sources=['app-localization'], key='无A', culture='neutral')
        self.assertEqual(2, empty['total'])
        self.assertTrue(all((r['text'],r['value_state'])==('','text') for r in empty['results']))
        self.assertEqual(4, self.library.query(sources=['app-localization'],key='下载方式')['total'])

    def test_real_alias_resource_name_and_business_name_are_distinct(self):
        out=self.library.query(key='暴击伤害',sources=['app-attributes'],limit=1000)
        self.assertEqual({'CH DMG'},{r['text'] for r in out['results'] if r['context']['culture']=='en'})
        self.assertIn('Critical Hit Damage',{r['text'] for r in out['results'] if r['value_kind']=='dictionary_alias'})
        row=self.library.query(key='bonus_weapon_damage',sources=['business-bonuses'],language='en')['results'][0]
        self.assertEqual(('Weapon Damage','business_name'),(row['text'],row['value_kind']))

    def test_real_inputs_and_image_queries_stay_unchanged(self):
        from tools.asset_import.library import Library
        paths=[self.root/s['file'] for s in self.library.sources.values()]
        before={str(p):sha256(p.read_bytes()) for p in paths}
        image_before=Library(root=self.root).search('gear2.png','path')
        self.library.query(text='Damage',limit=3)
        self.assertEqual(before,{str(p):sha256(p.read_bytes()) for p in paths})
        self.assertEqual(image_before,Library(root=self.root).search('gear2.png','path'))


class HistoricalTextInputTests(unittest.TestCase):
    def test_changed_snapshot_registry_is_rejected(self):
        with patch.object(Path, 'read_bytes', return_value=b'changed snapshot registry'):
            with self.assertRaisesRegex(TextError, 'INPUT_HASH_MISMATCH'):
                HistoricalTextLibrary()

    def test_archived_inputs_fail_closed_without_current_data_fallback(self):
        library = HistoricalTextLibrary()
        for spec in library.sources.values():
            if spec['file'] not in ARCHIVED_INPUTS:
                continue
            with self.subTest(file=spec['file'], case='changed'):
                with patch.object(Path, 'read_bytes', return_value=b'changed historical input'):
                    with self.assertRaisesRegex(TextError, 'INPUT_HASH_MISMATCH'):
                        library._read(spec)
            with self.subTest(file=spec['file'], case='missing'):
                with patch.object(Path, 'read_bytes', side_effect=FileNotFoundError):
                    with self.assertRaisesRegex(TextError, 'INPUT_MISSING'):
                        library._read(spec)


if __name__ == '__main__':
    unittest.main()
