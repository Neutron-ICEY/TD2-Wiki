"""Non-game fixtures exercise evidence boundaries, not game facts."""
import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from tools.asset_import.hunter import asset_manifest_entry, extraction_gate, exported_record, export_duplicate_links
from tools.asset_import.reconciliation import image_reference_check, unique_exact
from tools.asset_import.static_formats import image_metadata, sha256


class ImageProofTests(unittest.TestCase):
    def setUp(self):
        self.source = dict(asset_id='fixture:direct', source_platform='apk', source_entry='assets/wwwroot/fixture.png',
                           source_filename='fixture.png', source_sha256='a' * 64, pixel_hash='b' * 64)
        self.binding = dict(source_platform='apk', source_filename='fixture.png')

    def proof(self, method, confidence='exact'):
        return dict(evidence_id='NON-GAME-FACT', evidence_type=method, confidence=confidence,
                    bridge_source_asset_ids=['fixture:direct'])

    def test_same_name_different_native_bytes_cannot_become_exact(self):
        native = dict(self.source, asset_id='fixture:native', source_entry='res/drawable/fixture.png',
                      source_sha256='c' * 64, pixel_hash='d' * 64)
        self.assertFalse(image_reference_check(native, self.binding,
            self.proof('filename_only_native_resource_candidate', 'medium'), [self.source])['native_runtime_consumption_proven'])
        for method in ('literal_filename_reference', 'exact_sha256_bridge', 'decoded_pixel_bridge'):
            with self.subTest(method=method), self.assertRaises(ValueError):
                image_reference_check(native, self.binding, self.proof(method), [self.source])

    def test_pixel_bridge_keeps_distinct_original_byte_identity(self):
        native = dict(self.source, asset_id='fixture:density', source_entry='res/drawable/fixture.png', source_sha256='c' * 64)
        self.assertTrue(image_reference_check(native, self.binding, self.proof('decoded_pixel_bridge'), [self.source])['reproduced'])
        with self.assertRaises(ValueError):
            image_reference_check(native, self.binding, self.proof('exact_sha256_bridge'), [self.source])
        self.assertNotEqual(native['source_sha256'], self.source['source_sha256'])

    def test_bridge_requires_a_real_literal_source_path(self):
        fake = dict(self.source, source_entry='res/drawable/fixture.png')
        with self.assertRaises(ValueError):
            image_reference_check(fake, self.binding, self.proof('exact_sha256_bridge'), [fake])

    def test_scoped_exact_name_rejects_ambiguity_and_punctuation_repair(self):
        rows = [({'name': 'NON-GAME-FACT Talent'}, {'scope': 'gear'})]
        self.assertIsNotNone(unique_exact(rows, 'non-game-fact talent'))
        self.assertIsNone(unique_exact(rows + rows, 'NON-GAME-FACT Talent'))
        self.assertIsNone(unique_exact([({'name': "Fixture's"}, {})], 'Fixture’s'))


class HunterBoundaryTests(unittest.TestCase):
    def test_existing_image_gaps_never_authorize_extraction(self):
        for gap in ('IMAGE_EXISTS_MAPPING_MISSING', 'IMAGE_EXISTS_ENTITY_MISSING'):
            self.assertFalse(extraction_gate(gap, ['NON-GAME-FACT'], True, True, True)[0])

    def test_missing_requires_completed_source_search_and_confirmed_role(self):
        self.assertFalse(extraction_gate('IMAGE_MISSING', [], False, True, True)[0])
        self.assertFalse(extraction_gate('IMAGE_MISSING', [], True, False, True)[0])
        self.assertFalse(extraction_gate('IMAGE_MISSING', [], True, True, False)[0])
        self.assertFalse(extraction_gate('IMAGE_MISSING', ['still-candidate'], True, True, True)[0])
        self.assertTrue(extraction_gate('IMAGE_MISSING', [], True, True, True)[0])

    def test_variant_requires_independent_confirmed_gap(self):
        self.assertFalse(extraction_gate('IMAGE_VARIANT_MISSING', ['existing-image'], False, True, True)[0])
        self.assertTrue(extraction_gate('IMAGE_VARIANT_MISSING', ['existing-other-variant'], True, True, True)[0])

    def test_only_isolated_copies_are_read_and_unknown_provenance_stays_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); out = root / 'review'; raw = out / 'hunter/raw'; raw.mkdir(parents=True)
            buffer = io.BytesIO(); Image.new('RGBA', (7, 5), (5, 8, 13, 0)).save(buffer, format='PNG')
            data = buffer.getvalue(); game_file = root / 'game-original.png'; game_file.write_bytes(data)
            with self.assertRaises(ValueError):
                exported_record(out, game_file, {})
            copy = raw / 'NON-GAME-FACT.png'; copy.write_bytes(data)
            record = exported_record(out, copy, {})
            self.assertEqual(record['mapping_status'], 'EXTRACTED_UNMAPPED')
            self.assertIsNone(record['entity_key'])
            self.assertEqual(record['source_container_sha256'], 'UNKNOWN')
            self.assertEqual(record['original_resource_sha256'], 'UNKNOWN')
            self.assertEqual(record['normalized_file_sha256'], 'UNKNOWN')
            self.assertEqual(game_file.read_bytes(), data)
            self.assertEqual(record['exported_file_sha256'], sha256(data))
            entry = asset_manifest_entry(out, record)
            self.assertEqual(entry['source_sha256'], record['exported_file_sha256'])
            self.assertEqual(entry['mapping_status'], 'unresolved')
            self.assertEqual(entry['hunter_result'], 'EXTRACTED_UNMAPPED')
            self.assertIsNone(entry['stable_id'])
            self.assertEqual(entry['game_entities'], [])
            self.assertEqual(entry['provenance']['original_resource_sha256'], 'UNKNOWN')
            copy.write_bytes(b'changed-copy')
            with self.assertRaises(ValueError):
                asset_manifest_entry(out, record)

    def test_corrupt_manual_copy_is_export_failed_not_unknown_entity(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder); raw = out / 'hunter/raw'; raw.mkdir(parents=True)
            path = raw / 'NON-GAME-FACT.png'; path.write_bytes(b'corrupt exported bytes')
            with self.assertRaisesRegex(ValueError, 'EXPORT_FAILED'):
                exported_record(out, path, {})

    def test_duplicate_bytes_and_pixels_do_not_transfer_entity_identity(self):
        image = Image.new('RGBA', (7, 5), (5, 8, 13, 255))
        first = io.BytesIO(); second = io.BytesIO()
        image.save(first, format='PNG', compress_level=0)
        image.save(second, format='PNG', compress_level=9)
        self.assertNotEqual(sha256(first.getvalue()), sha256(second.getvalue()))
        pixels = image_metadata(first.getvalue())['pixel_hash']
        self.assertEqual(pixels, image_metadata(second.getvalue())['pixel_hash'])
        links = export_duplicate_links(dict(exported_file_sha256=sha256(first.getvalue()), decoded_image_sha256=pixels),
            [dict(asset_id='fixture:one', source_sha256=sha256(first.getvalue()), pixel_hash=pixels),
             dict(asset_id='fixture:two', source_sha256=sha256(second.getvalue()), pixel_hash=pixels)])
        self.assertEqual(links['exact_export_byte_sources'], ['fixture:one'])
        self.assertEqual(links['decoded_pixel_sources'], ['fixture:one', 'fixture:two'])
        self.assertFalse(links['entity_promotion'])


if __name__ == '__main__':
    unittest.main()
