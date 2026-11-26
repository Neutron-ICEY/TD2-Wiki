"""Bounded .resources fixtures and acceptance of the four recovered app tables."""
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from fixture_corpus import corpus_root

from tools.asset_import.text_extract import PACKAGE_METADATA, extract, resource_table
from tools.asset_import.text_library import ROOT, RESOURCE_NAMESPACE, TextError, sha256


def varint(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    return bytes(result) + bytes([value])


def string_bytes(value, encoding='utf-8'):
    raw = value.encode(encoding)
    return varint(len(raw)) + raw


def resource_bytes(rows):
    names, values, offsets = bytearray(), bytearray(), []
    for key, code, value in rows:
        offsets.append(len(names))
        names.extend(string_bytes(key, 'utf-16le') + struct.pack('<I', len(values)))
        values.extend(varint(code))
        values.extend(string_bytes(value) if code == 1 and isinstance(value, str) else value)
    header = struct.pack('<IIIIII', 0xbeefcace, 1, 0, 2, len(rows), 0)
    header += struct.pack('<'+'i'*len(rows), *([0]*len(rows)))
    header += struct.pack('<'+'I'*len(rows), *offsets)
    return header + struct.pack('<I', len(header)+4+len(names)) + names + values


class ResourceTableTests(unittest.TestCase):
    def test_all_string_characters_and_empty_values_survive_exactly(self):
        value = '\ufeff中, "quoted"\r\n{0}<color>\\r\\n\t\x01'
        raw = resource_bytes([('键/名',1,value), ('Empty',1,'')])
        result = resource_table(raw)
        self.assertEqual([value,''], [r['text'] for r in result['records']])
        self.assertEqual(1, result['stats']['empty_strings'])
        self.assertEqual(0, result['stats']['parse_errors'])
        for row in result['records']:
            self.assertEqual(row['text'], raw[row['value_offset']:row['value_end']].decode('utf-8'))

    def test_duplicate_keys_keep_all_slots_and_report_them(self):
        result = resource_table(resource_bytes([('K',1,'A'),('K',1,'B'),('K',1,'A')]))
        self.assertEqual(['A','B','A'], [r['text'] for r in result['records']])
        self.assertEqual([dict(key='K',entries=[0,1,2])], result['duplicate_keys'])
        self.assertEqual((3,1,1), tuple(result['stats'][k] for k in ('declared_entries','unique_keys','duplicate_key_groups')))

    def test_null_and_non_string_are_counted_without_deserializing_objects(self):
        result = resource_table(resource_bytes([('Null',0,b''),('Object',64,b'arbitrary object bytes'),('String',1,'')]))
        self.assertEqual(['null','non_string','string'], [r['status'] for r in result['records']])
        self.assertEqual((1,1,1), tuple(result['stats'][k] for k in ('null_values','non_string_values','string_values')))
        self.assertIsNone(result['records'][1]['text'])

    def test_bad_utf8_value_does_not_discard_other_entries(self):
        result = resource_table(resource_bytes([('Bad',1,b'\x01\xff'),('Good',1,'Preserved')]))
        self.assertEqual('parse_error', result['records'][0]['status'])
        self.assertEqual('INVALID_RESOURCE_VALUE', result['records'][0]['error'])
        self.assertEqual('Preserved', result['records'][1]['text'])

    def test_invalid_name_and_value_offsets_are_explicit_per_entry(self):
        for position in ('name','value'):
            raw = bytearray(resource_bytes([('K',1,'Text')]))
            if position == 'name':
                struct.pack_into('<I', raw, 28, 0xffffffff)
            else:
                # Header/index end at 36; one-byte length and two-byte UTF-16 key follow.
                struct.pack_into('<I', raw, 39, 0xffffffff)
            result = resource_table(raw)
            self.assertEqual(1, result['stats']['parse_errors'])
            self.assertIn('error', result['records'][0])

    def test_truncated_value_and_unsupported_headers_are_explicit(self):
        result = resource_table(resource_bytes([('K',1,b'\x09abc')]))
        self.assertEqual('TRUNCATED_RESOURCE_STRING', result['records'][0]['error'])
        for raw in (b'', b'\x00'*40, struct.pack('<IIIIII',0xbeefcace,1,0,1,0,0)):
            with self.subTest(raw=raw), self.assertRaises((TextError,struct.error)):
                resource_table(raw)


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TD2_TEXT_LIBRARY_TEST_TMP'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = resource_bytes([('K',1,'Value {0}'),('Empty',1,'')])
        self.assemblies = {'Division2BuildTool':b'neutral assembly', 'en/Division2BuildTool.resources':b'en assembly'}
        packages = {}
        for platform in ('apk','windows'):
            filename = 'inputs/' + platform
            path = self.root/filename
            path.parent.mkdir(parents=True, exist_ok=True)
            if platform == 'apk':
                with zipfile.ZipFile(path,'w'):
                    pass
            else:
                path.write_bytes(b'fake single-file bundle')
            sources = []
            for culture, name in zip(('neutral','en'),self.assemblies):
                resource_name = RESOURCE_NAMESPACE + ('.en.resources' if culture=='en' else '.resources')
                source_entry = 'assemblies.blob' if platform=='apk' else name+'.dll'
                sources.append(dict(name=name,source_entry=source_entry,sha256=sha256(self.assemblies[name]),
                    decoded_sha256=sha256(self.assemblies[name]),resource_streams=[
                        dict(name=resource_name,sha256=sha256(self.raw),size=len(self.raw))]))
                self.write('dist/asset-import/'+platform+('-en' if culture=='en' else '')+'-managed-metadata.json',
                    dict(resources_directory_rva=0,resources=[dict(name=resource_name,embedded=True,offset=0)]))
            packages[platform] = dict(relative_path=filename,sha256=sha256(path.read_bytes()),assembly_version='29.0',
                                      assembly_sources=sources)
        self.write(PACKAGE_METADATA,packages)
        self.patches = [
            patch('tools.asset_import.text_extract.android_app_assemblies',return_value=[
                (name,raw,dict(source_entry='assemblies.blob',decoded_sha256=sha256(raw)))
                for name,raw in self.assemblies.items()]),
            patch('tools.asset_import.text_extract.bundle_entries',return_value=(None,[
                dict(source_entry=name+'.dll') for name in self.assemblies])),
            patch('tools.asset_import.text_extract.bundle_bytes',side_effect=lambda raw,entry:self.assemblies[entry['source_entry'][:-4]]),
            patch('tools.asset_import.text_extract.managed_resource_bytes',return_value=self.raw)]
        for active in self.patches:
            active.start()
            self.addCleanup(active.stop)

    def write(self,name,value):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value),encoding='utf-8')

    def snapshot(self):
        return {p.relative_to(self.root).as_posix():sha256(p.read_bytes()) for p in self.root.rglob('*') if p.is_file()}

    def test_four_tables_are_extracted_to_new_files_with_pinned_inputs(self):
        before = self.snapshot()
        result = extract(self.root,'output')
        self.assertEqual([],result['failures'])
        self.assertEqual(4,len(result['tables']))
        self.assertTrue(result['inputs_unchanged'])
        self.assertEqual(before,{p:sha256((self.root/p).read_bytes()) for p in before})
        for table in result['tables']:
            raw = (self.root/table['raw_resource']['file']).read_bytes()
            self.assertEqual(self.raw,raw)
            self.assertEqual(sha256(raw),table['raw_resource']['sha256'])
        self.assertEqual(sha256((self.root/'output/strings.json').read_bytes()),result['output']['sha256'])

    def test_existing_output_is_refused_without_changes(self):
        extract(self.root,'output')
        before = self.snapshot()
        with self.assertRaisesRegex(TextError,'OUTPUT_MUST_BE_FRESH'):
            extract(self.root,'output')
        self.assertEqual(before,self.snapshot())

    def test_package_hash_failure_is_reported_while_other_platform_survives(self):
        (self.root/'inputs/windows').write_bytes(b'changed')
        result = extract(self.root,'output')
        self.assertEqual(2,len(result['tables']))
        self.assertEqual('windows',result['failures'][0]['platform'])
        self.assertEqual('PACKAGE_HASH_MISMATCH',result['failures'][0]['code'])

    def test_one_bad_assembly_does_not_discard_other_tables(self):
        bad = self.patches[-1]
        bad.stop()
        with patch('tools.asset_import.text_extract.managed_resource_bytes',side_effect=[self.raw,b'bad',self.raw,self.raw]):
            result = extract(self.root,'output')
        self.assertEqual(3,len(result['tables']))
        self.assertEqual('RESOURCE_HASH_MISMATCH',result['failures'][0]['code'])

    def test_unsafe_output_paths_do_not_create_files(self):
        before = self.snapshot()
        for path in ('../outside','/absolute','sub/../output','sub\\output'):
            with self.subTest(path=path),self.assertRaises(TextError):
                extract(self.root,path)
        self.assertEqual(before,self.snapshot())


REVIEW = corpus_root()/'dist/text-library-20261017-001/localization-full'


class ExistingResourceTablesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((REVIEW/'extraction.json').read_bytes())
        cls.data = json.loads((REVIEW/'strings.json').read_bytes())

    def test_all_real_slots_match_the_raw_binary_and_declared_counts(self):
        counts = {}
        for table in self.manifest['tables']:
            raw = (corpus_root()/table['raw_resource']['file']).read_bytes()
            self.assertEqual(table['raw_resource']['sha256'],sha256(raw))
            decoded = resource_table(raw)
            evidence_index = self.manifest['tables'].index(table)
            stored = next(t for t in self.data['tables'] if t['evidence_pointer']=='/tables/'+str(evidence_index))
            self.assertEqual(decoded['records'],stored['records'])
            self.assertEqual(decoded['stats'],table['stats'])
            self.assertEqual(0,sum(decoded['stats'][k] for k in ('null_values','non_string_values','parse_errors','duplicate_key_groups')))
            counts[table['platform'],table['culture']] = decoded['stats']['string_values']
        self.assertEqual({('apk','neutral'):2313,('apk','en'):1997,('windows','neutral'):2313,('windows','en'):1997},counts)

    def test_matching_platform_tables_remain_independent_and_exact(self):
        tables = {(t['platform'],t['culture']):t for t in self.data['tables']}
        for culture in ('neutral','en'):
            self.assertEqual(tables['apk',culture]['records'],tables['windows',culture]['records'])
        rows = [r for t in tables.values() for r in t['records']]
        self.assertEqual(8620,len(rows))
        self.assertEqual(2313,len({r['key'] for r in rows}))
        self.assertEqual(4132,len({r['text'] for r in rows}))


if __name__ == '__main__':
    unittest.main()
