import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from tools.asset_import.pipeline import stage_images, stage_plan
from tools.asset_import.static_formats import image_metadata, sha256
from tools.brand_sets.icons import resolver_source


ROOT = Path(__file__).resolve().parents[1]


class StagingLocationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / 'dist/review'
        self.filename = 'NON-GAME-FACT-red.png'
        output = io.BytesIO()
        Image.new('RGBA', (7, 5), (12, 34, 56, 128)).save(output, format='PNG')
        self.blob = output.getvalue()
        self.raw = 'raw/fixture.png'
        self.destination = 'resources/game/current/images/hunter/fixture.png'
        self.put(self.destination, self.blob)
        self.put('dist/review/normalized/' + self.filename, self.blob)
        self.put('tests/wiki_subset.py', (ROOT / 'tests/wiki_subset.py').read_bytes())
        self.contract = dict(small_icon_entries={'state/red': dict(wiki_file=self.filename, confirmed_on_wiki=True)})
        self.put('wiki/templates/TD2图标.wiki', resolver_source(self.contract['small_icon_entries']).encode())
        self.asset = dict(asset_id='fixture', category='state', stable_id='red', icon_key='state/red',
            source_sha256=sha256(self.blob), pixel_hash=image_metadata(self.blob)['pixel_hash'], raw_path=self.raw,
            normalized_filename=self.filename, intended_wiki_filename=self.filename, normalized_sha256=sha256(self.blob),
            status='approved', confidence='exact', evidence=['proof'], game_entities=['NON-GAME-FACT'])
        self.proof()
        self.locations({'dist/review/' + self.raw: self.destination})

    def put(self, relative, blob):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)

    def locations(self, aliases):
        self.put('data/asset-import/locations.json', json.dumps(dict(schema_version=1, locations={
            old: dict(path=target, sha256=sha256(self.blob)) for old, target in aliases.items()})).encode())

    def proof(self):
        asset = self.asset
        self.put('dist/review/mapping-evidence.json', json.dumps(dict(mappings=[dict(evidence_id='proof',
            confidence='exact', source_asset_id=asset['asset_id'], source_path=asset['raw_path'],
            candidate_stable_id=asset['stable_id'], candidate_icon_key=asset['icon_key'],
            candidate_game_entity=asset['game_entities'][0])])).encode())

    def test_relocated_raw_is_staged_without_rewriting_original_provenance(self):
        before = (self.out / 'mapping-evidence.json').read_bytes()
        self.assertFalse((self.out / self.raw).exists())
        result = stage_images(self.root, self.out, self.root / 'dist/staging', [self.asset], self.contract)
        self.assertEqual(1, result['approved_image_count'])
        self.assertEqual(self.blob, (self.root / 'dist/staging/images' / self.filename).read_bytes())
        self.assertEqual(before, (self.out / 'mapping-evidence.json').read_bytes())

    def test_relocated_raw_still_requires_original_source_sha(self):
        self.put(self.destination, b'changed resource')
        with self.assertRaisesRegex(ValueError, 'RAW_SOURCE_CHANGED'):
            stage_plan(self.root, self.out, [self.asset], self.contract)

    def test_brand_selected_source_matches_exact_alias_and_rejects_other_file(self):
        selected = 'dist/old-brand/raw/fixture.png'
        self.locations({selected: self.destination})
        self.asset.update(stable_id='fixture-brand', icon_key='TD2品牌图片|品牌=fixture:stable',
            raw_path=self.destination, resolver_contract='brand_image', publication_status='READY_TO_UPLOAD')
        self.proof()
        entity = dict(publication_ready=True, publication_status='READY_TO_UPLOAD', zh_name='NON-GAME-FACT', entity_ref='fixture:stable',
            asset_mapping=dict(selected_source_sha256=sha256(self.blob), selected_asset_id=self.asset['asset_id'],
                               selected_raw_path=selected))
        with patch('tools.brand_sets.brands.load_catalog', return_value={}), \
             patch('tools.brand_sets.brands.by_key', return_value={'fixture-brand': entity}), \
             patch('tools.asset_import.pipeline.compatible_brand_filename', return_value=True):
            rows, payloads = stage_plan(self.root, self.out, [self.asset], self.contract, source_root=self.root)
            self.assertEqual(1, len(rows))
            self.assertEqual(self.blob, payloads[self.filename.casefold()][0])
            for changed in (dict(self.asset, raw_path='resources/game/current/images/hunter/other.png'),
                            dict(self.asset, publication_status='REMOTE_UNKNOWN'),
                            dict(self.asset, asset_id='another-observation')):
                with self.assertRaisesRegex(ValueError, 'BRAND_PUBLICATION_GATE_FAILED'):
                    stage_plan(self.root, self.out, [changed], self.contract, source_root=self.root)


if __name__ == '__main__':
    unittest.main()
