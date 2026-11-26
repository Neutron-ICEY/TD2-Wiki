"""Synthetic NON-GAME-FACT fixtures test the private importer and approval gates."""
import io
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import unittest

from tools.asset_import.contract import compatible_filename, detect_contract, match_wiki
from tools.asset_import.investigate import lz4_block, version_tuple
from tools.asset_import.mapping import duplicate_groups, expression, signature_shape
from tools.asset_import.pipeline import normalize_bytes, stage_images, stage_plan
from tools.asset_import.static_formats import claim_filename, image_metadata, safe_relative, sha256, write_source
from tools.brand_sets.icons import resolver_source

try:
    from PIL import Image, features
except ImportError:
    Image = None

ROOT = Path(__file__).resolve().parents[1]


class StaticReaderTests(unittest.TestCase):
    def test_reject_invalid_paths_and_windows_names(self):
        for path in ('../x.png', '/x.png', 'a/../x.png', 'C:/x.png', 'a\\x.png', 'a//x.png',
                     'a/./x.png', 'CON.png', 'a/aux.jpg', 'a/x*.png', 'a/x?.png', 'a/x.png ', 'x\x00.png'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                safe_relative(path)
        self.assertEqual(str(safe_relative('assets/wwwroot/brand0.png')), 'assets/wwwroot/brand0.png')

    def test_raw_write_does_not_rename_or_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); original = b'NON-GAME-FACT raw resource'
            path = write_source(root, 'res/a.png', original)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(write_source(root, 'res/a.png', original), path)
            with self.assertRaisesRegex(ValueError, 'COLLISION'):
                write_source(root, 'res/a.png', b'different')

    def test_output_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); base = root / 'base'; base.mkdir(); other = root / 'other'; other.mkdir()
            try:
                (base / 'escape').symlink_to(other, target_is_directory=True)
            except OSError:
                if os.name != 'nt':
                    raise
                import _winapi
                _winapi.CreateJunction(str(other), str(base / 'escape'))
                self.assertTrue((base / 'escape').is_junction())
            with self.assertRaises(ValueError):
                write_source(base, 'escape/image.png', b'fixture')
            self.assertFalse((other / 'image.png').exists())

    def test_lz4_literal_and_overlap_copy(self):
        self.assertEqual(lz4_block(b'\x30abc', 3), b'abc')
        self.assertEqual(lz4_block(b'\x10a\x01\x00', 5), b'aaaaa')
        with self.assertRaises(ValueError):
            lz4_block(b'\x10a\x00\x00', 5)

    def test_metadata_signature_not_application_execution(self):
        self.assertEqual(signature_shape('200401080E0E12852C'), (4, True, True))
        self.assertEqual(signature_shape('00010E0E'), (1, False, False))

    def test_version_comparison_does_not_strip_nonzero_components(self):
        self.assertEqual(version_tuple('29.0.0.0'), version_tuple('29.0.0+metadata'))
        self.assertNotEqual(version_tuple('29.0.10'), version_tuple('29.0.1'))

    def test_backwards_reader_rejects_unsupported_expression(self):
        with self.assertRaisesRegex(ValueError, 'UNRESOLVED'):
            expression([dict(opcode='br.s', operand=0, offset=0)], 0)

    def test_missing_mapping_does_not_invent_filenames(self):
        contract = detect_contract(ROOT)
        self.assertFalse(contract['naming_contract_conflicts'])
        self.assertFalse(contract['small_icon_entries']['material/brand_material']['wiki_file'])
        self.assertEqual(contract['small_icon_entries']['equipment_row/talent_slot']['wiki_file'], 'TD2-UI-TalentSlot-Icon.png')
        self.assertFalse(compatible_filename(ROOT, 'state', 'random', 'invented-random.png', contract))
        self.assertFalse(compatible_filename(ROOT, 'state', 'red', 'invented-red.png', contract))
        brand = next(r for r in contract['examples'] if r['category'] == 'brand')
        self.assertIn('[[File:' + brand['normalized_filename'], brand['lookup_result'])
        self.assertEqual(brand['gate'], 'PASS_REGISTERED_BRAND_MAPPING')

    def test_application_attribute_name_cannot_select_bonus_domain(self):
        result = match_wiki(ROOT, {'category': 'attribute', 'chinese_name': '武器伤害', 'english_name': 'Weapon Damage'})
        self.assertIsNone(result['stable_id'])
        self.assertEqual(result['method'], 'unscoped_attribute_requires_domain_reconciliation')

    def test_unique_talent_name_cannot_authorize_identity(self):
        result = match_wiki(ROOT, {'category':'talent','chinese_name':'完美守护者','english_name':'Perfect Protector'})
        self.assertIsNone(result['stable_id'])
        self.assertIn('perfect_protector', result['candidate_ids'])
        self.assertFalse(result['unique'])


@unittest.skipUnless(Image is not None, 'Use the existing Pillow-enabled Python for image verification')
class ImageAndApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.out = self.root / 'dist/asset-import'; self.out.mkdir(parents=True)
        (self.root / 'wiki/templates').mkdir(parents=True); (self.root / 'tests').mkdir()
        shutil.copyfile(ROOT / 'tests/wiki_subset.py', self.root / 'tests/wiki_subset.py')
        self.filename = 'NON-GAME-FACT-red.png'
        entries = {'state/red': {'wiki_file': self.filename, 'confirmed_on_wiki': True}}
        (self.root / 'wiki/templates/TD2图标.wiki').write_text(resolver_source(entries), encoding='utf-8')
        self.contract = dict(small_icon_entries=entries)
        self.data = self.png()
        self.metadata = image_metadata(self.data)
        self.raw = 'raw/apk/assets/wwwroot/fixture.png'
        write_source(self.out, self.raw, self.data); write_source(self.out / 'normalized', self.filename, self.data)
        self.asset = dict(asset_id='NON-GAME-FACT-asset', category='state', stable_id='red', icon_key='state/red',
            source_sha256=sha256(self.data), pixel_hash=self.metadata['pixel_hash'], raw_path=self.raw,
            normalized_filename=self.filename, intended_wiki_filename=self.filename, normalized_sha256=sha256(self.data),
            status='approved', confidence='exact', evidence=['fixture-proof'], game_entities=['NON-GAME-FACT state red'])
        self.proof = dict(evidence_id='fixture-proof', source_asset_id=self.asset['asset_id'], source_path=self.raw,
            candidate_stable_id='red', candidate_icon_key='state/red', candidate_game_entity='NON-GAME-FACT state red', confidence='exact')
        self.write_proof()

    def png(self, mode='RGBA', compress=6):
        image = Image.new(mode, (7, 5), (120, 40, 10, 128) if mode == 'RGBA' else (120, 40, 10))
        output = io.BytesIO(); image.save(output, format='PNG', compress_level=compress); return output.getvalue()

    def write_proof(self):
        (self.out / 'mapping-evidence.json').write_text(json.dumps(dict(mappings=[self.proof])), encoding='utf-8')

    def test_dimensions_and_alpha_are_read_from_pixels(self):
        self.assertEqual((self.metadata['width'], self.metadata['height']), (7, 5))
        self.assertTrue(self.metadata['alpha']); self.assertTrue(self.metadata['transparency'])
        opaque = image_metadata(self.png(mode='RGB'))
        self.assertFalse(opaque['alpha']); self.assertFalse(opaque['transparency'])

    def test_rgba_channel_is_distinct_from_actual_transparency(self):
        image = Image.new('RGBA', (2, 3), (1, 2, 3, 255)); out = io.BytesIO(); image.save(out, format='PNG')
        meta = image_metadata(out.getvalue()); self.assertTrue(meta['alpha']); self.assertFalse(meta['transparency'])

    def test_decoded_pixel_hash_is_deterministic_across_compression(self):
        a = self.png(compress=0); b = self.png(compress=9)
        self.assertNotEqual(sha256(a), sha256(b))
        self.assertEqual(image_metadata(a)['pixel_hash'], image_metadata(b)['pixel_hash'])
        self.assertEqual(image_metadata(a), image_metadata(a))

    def test_animated_frame_and_duration_affect_pixel_hash(self):
        a = Image.new('RGB', (3, 3), (255, 0, 0)); b = Image.new('RGB', (3, 3), (0, 255, 0))
        outputs = []
        for duration in (100, 200):
            out = io.BytesIO(); a.save(out, format='GIF', save_all=True, append_images=[b], duration=duration); outputs.append(out.getvalue())
        self.assertEqual(image_metadata(outputs[0])['frame_count'], 2)
        self.assertNotEqual(image_metadata(outputs[0])['pixel_hash'], image_metadata(outputs[1])['pixel_hash'])

    def test_webp_to_png_preserves_dimensions_pixels_and_alpha(self):
        if not features.check('webp'):
            self.skipTest('Existing Pillow has no WebP codec')
        image = Image.open(io.BytesIO(self.data)); out = io.BytesIO(); image.save(out, format='WEBP', lossless=True)
        source = out.getvalue(); converted, operation = normalize_bytes(source, 'fixture.png')
        for key in ('width', 'height', 'alpha', 'transparency', 'pixel_hash'):
            self.assertEqual(image_metadata(source)[key], image_metadata(converted)[key])
        self.assertIn('lossless', operation)
        self.assertEqual(normalize_bytes(converted, 'fixture.png')[0], converted)

    def test_lossy_or_animated_conversion_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'UNSUPPORTED'):
            normalize_bytes(self.data, 'fixture.jpg')

    def test_duplicates_and_cross_platform_correlation_are_deterministic(self):
        def row(platform, source_id, data):
            return dict(source_platform=platform, source_asset_id=source_id, source_entry='wwwroot/test.png',
                        filename='test.png', sha256=sha256(data), pixel_hash=image_metadata(data)['pixel_hash'])
        images = [row('apk', 'apk-1', self.data), row('windows', 'windows-1', self.png(compress=0)), row('windows', 'windows-2', self.data)]
        groups, correlations = duplicate_groups(images, [])
        again = duplicate_groups(list(reversed(images)), [])
        self.assertEqual(groups, again[0]); self.assertEqual(correlations, again[1])
        self.assertEqual({g['type'] for g in groups}, {'exact_file_duplicate', 'pixel_duplicate'})
        self.assertTrue(all(c['confidence'] == 'exact' for c in correlations))

    def test_filename_match_does_not_prove_entity(self):
        changed = Image.new('RGBA', (7, 5), (9, 8, 7, 6)); out = io.BytesIO(); changed.save(out, format='PNG')
        images = [dict(source_platform=platform, source_asset_id=platform, source_entry='wwwroot/test.png', filename='test.png',
                       sha256=sha256(data), pixel_hash=image_metadata(data)['pixel_hash']) for platform, data in [('apk', self.data), ('windows', out.getvalue())]]
        _, rows = duplicate_groups(images, [])
        self.assertEqual(rows[0]['confidence'], 'medium'); self.assertTrue(rows[0]['filename_only_not_entity_proof'])

    def test_native_filename_hint_does_not_confirm_shared_entities(self):
        images = [dict(source_platform='apk', source_asset_id=str(n), source_entry='res/' + str(n) + '/test.png',
                       filename='test.png', sha256=sha256(self.data), pixel_hash=self.metadata['pixel_hash']) for n in range(2)]
        bindings = [dict(source_platform='apk', source_filename='test.png', category='fixture', internal_key=key) for key in ('a', 'b')]
        groups, _ = duplicate_groups(images, bindings)
        self.assertTrue(all(not g['legitimate_shared_icon'] and not g['confirmed_application_entities'] for g in groups))
        images.append(dict(images[0], source_asset_id='direct', source_entry='assets/wwwroot/test.png'))
        groups, _ = duplicate_groups(images, bindings)
        self.assertTrue(all(g['legitimate_shared_icon'] and len(g['confirmed_application_entities']) == 2 for g in groups))

    def test_existing_resolver_resolves_approved_filename(self):
        self.assertTrue(compatible_filename(self.root, 'state', 'red', self.filename, self.contract))
        rows, payloads = stage_plan(self.root, self.out, [self.asset], self.contract)
        self.assertEqual(rows[0]['sha256'], sha256(self.data)); self.assertEqual(len(payloads), 1)

    def test_approved_only_staging_preserves_existing_sandbox(self):
        staging = self.root / 'dist/huiji-updater'; (staging / 'sandbox').mkdir(parents=True)
        sentinel = staging / 'sandbox/manual.wiki'; sentinel.write_bytes(b'preserve')
        result = stage_images(self.root, self.out, staging, [self.asset], self.contract)
        self.assertEqual(result['approved_image_count'], 1)
        self.assertEqual((staging / 'images' / self.filename).read_bytes(), self.data)
        self.assertEqual(sentinel.read_bytes(), b'preserve')

    def test_all_review_statuses_are_excluded_from_staging(self):
        for status in ('high_confidence', 'needs_review', 'unmatched', 'needs_catalog_entry'):
            with self.subTest(status=status):
                asset = dict(self.asset, status=status)
                self.assertEqual(stage_plan(self.root, self.out, [asset], self.contract), ([], {}))

    def test_approved_without_exact_confidence_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'APPROVAL'):
            stage_plan(self.root, self.out, [dict(self.asset, confidence='high')], self.contract)

    def test_incompatible_filename_and_missing_mapping_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'NAMING_CONTRACT'):
            stage_plan(self.root, self.out, [self.asset], dict(small_icon_entries={}))
        with self.assertRaisesRegex(ValueError, 'INVALID_PATH'):
            stage_plan(self.root, self.out, [dict(self.asset, normalized_filename='../x.png')], self.contract)

    def test_incomplete_or_ambiguous_provenance_is_rejected(self):
        for asset in (dict(self.asset, evidence=[]), dict(self.asset, evidence=['unknown']),
                      dict(self.asset, game_entities=['entity-1', 'entity-2'])):
            with self.subTest(asset=asset), self.assertRaises(ValueError):
                stage_plan(self.root, self.out, [asset], self.contract)

    def test_forged_review_evidence_cannot_be_upgraded(self):
        self.proof['confidence'] = 'high'; self.write_proof()
        with self.assertRaisesRegex(ValueError, 'ENTITY_OR_PROVENANCE'):
            stage_plan(self.root, self.out, [self.asset], self.contract)

    def test_modified_raw_or_normalized_bytes_are_rejected(self):
        (self.out / self.raw).write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'RAW_SOURCE_CHANGED'):
            stage_plan(self.root, self.out, [self.asset], self.contract)
        (self.out / self.raw).write_bytes(self.data)
        (self.out / 'normalized' / self.filename).write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'NORMALIZED_CHANGED'):
            stage_plan(self.root, self.out, [self.asset], self.contract)

    def test_filename_collision_is_rejected(self):
        occupied = {}
        claim_filename(self.filename, self.metadata['pixel_hash'], occupied)
        claim_filename(self.filename, self.metadata['pixel_hash'], occupied)
        with self.assertRaisesRegex(ValueError, 'COLLISION'):
            claim_filename(self.filename, 'different-pixels', occupied)
        with self.assertRaisesRegex(ValueError, 'COLLISION'):
            claim_filename(self.filename.upper(), self.metadata['pixel_hash'], occupied)

    def test_staging_requires_fresh_directory(self):
        staging = self.root / 'dist/huiji-updater'; (staging / 'images').mkdir(parents=True)
        (staging / 'images/unknown.png').write_bytes(b'preserve')
        with self.assertRaisesRegex(ValueError, 'STAGING_NOT_FRESH'):
            stage_images(self.root, self.out, staging, [self.asset], self.contract)


if __name__ == '__main__':
    unittest.main()
