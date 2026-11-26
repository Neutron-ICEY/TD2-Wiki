import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.asset_import.locations import SourceLocations


class SourceLocationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TD2_ASSET_LIBRARY_TEST_TMP'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'data/asset-import').mkdir(parents=True)

    def index(self, locations):
        (self.root / 'data/asset-import/locations.json').write_text(
            json.dumps(dict(schema_version=1, locations=locations)), encoding='utf-8')

    def test_registered_asset_relocation_follows_id_without_changing_evidence(self):
        publishing=self.root/'publishing';publishing.mkdir()
        registry=publishing/'registry.json'
        registry.write_text(json.dumps({'entries':[{'id':'stable','kind':'assets','source':'assets/New.png'}]}),'utf8')
        record={'asset_ref':'stable','sha256':'a'*64};self.index({'dist/old/image.png':record})
        locations=SourceLocations(self.root)
        self.assertEqual(self.root/'assets/New.png',locations.resolve('dist/old/image.png',resolve=False))
        self.assertEqual(record,locations.locations['dist/old/image.png'])
        registry.write_text(json.dumps({'entries':[{'id':'stable','kind':'assets','source':'assets/Renamed.png'}]}),'utf8')
        self.assertEqual(self.root/'assets/Renamed.png',SourceLocations(self.root).resolve('dist/old/image.png',resolve=False))

    def test_absent_map_keeps_isolated_fixture_paths(self):
        self.assertEqual(self.root / 'dist/input.txt', SourceLocations(self.root).resolve('dist/input.txt'))

    def test_exact_relocation_preserves_unlisted_neighbor_and_recorded_root(self):
        self.index({'dist/old/input.txt': dict(path='resources/game/current/raw_files/input.txt', sha256='a' * 64)})
        locations = SourceLocations(self.root)
        expected = self.root / 'resources/game/current/raw_files/input.txt'
        self.assertEqual(expected, locations.resolve('input.txt', base='dist/old'))
        self.assertEqual(expected, locations.resolve('D:/old-project/dist/old/input.txt', historical_roots=['D:/old-project']))
        self.assertEqual(self.root / 'dist/old/other.txt', locations.resolve('dist/old/other.txt'))

    def test_search_resolution_does_not_open_or_stat_resource(self):
        self.index({'dist/old.txt': dict(path='evidence/old.txt', sha256='a' * 64)})
        locations = SourceLocations(self.root)
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('resource read forbidden')), \
                patch.object(Path, 'is_file', side_effect=AssertionError('resource stat forbidden')):
            self.assertEqual(self.root / 'evidence/old.txt', locations.resolve('dist/old.txt', resolve=False))

    def test_mapping_cannot_escape_or_chain(self):
        for target in ('../outside.txt', '/outside.txt', 'D:/outside.txt', 'a/../../outside.txt'):
            self.index({'dist/old.txt': dict(path=target, sha256='a' * 64)})
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, 'UNSAFE_LOCATION_PATH'):
                SourceLocations(self.root)
        self.index({'dist/a': dict(path='dist/b', sha256='a' * 64),
                    'dist/b': dict(path='evidence/b', sha256='a' * 64)})
        with self.assertRaisesRegex(ValueError, 'CHAINED_SOURCE_LOCATION'):
            SourceLocations(self.root)

    def test_foreign_absolute_path_and_traversal_fail(self):
        locations = SourceLocations(self.root)
        for value in ('../outside.txt', 'D:/unregistered/source.txt', 'D:/old/../escape.txt'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'PATH_OUTSIDE_ROOT'):
                locations.resolve(value, historical_roots=['D:/old'])

    def test_duplicate_json_paths_are_rejected(self):
        (self.root / 'data/asset-import/locations.json').write_text(
            '{"schema_version":1,"locations":{"a":{},"a":{}}}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_LOCATION_KEY'):
            SourceLocations(self.root)

    def test_windows_sprite_path_casing_keeps_recorded_identity(self):
        recorded = 'dist/old/hunter/baked/ui/spritesheets/fixture.png'
        destination = 'resources/game/current/images/hunter/baked/ui/spritesheets/fixture.png'
        row = dict(path=destination, sha256='a' * 64)
        self.index({recorded: row})
        locations = SourceLocations(self.root)
        self.assertEqual(self.root / destination, locations.resolve(
            'dist/old/hunter/baked/UI/SPRITESHEETS/fixture.png', resolve=False))
        self.assertEqual({recorded: row}, locations.locations)
        self.assertEqual(self.root / 'dist/old/hunter/baked/UI/SPRITESHEETS/other.png', locations.resolve(
            'dist/old/hunter/baked/UI/SPRITESHEETS/other.png', resolve=False))

    def test_windows_case_conflicts_and_case_variant_chains_are_rejected(self):
        self.index({'dist/Input.txt': dict(path='evidence/first.txt', sha256='a' * 64),
                    'dist/input.txt': dict(path='evidence/second.txt', sha256='b' * 64)})
        with self.assertRaisesRegex(ValueError, 'CASE_CONFLICTING_SOURCE_LOCATION'):
            SourceLocations(self.root)
        self.index({'dist/a': dict(path='DIST/B', sha256='a' * 64),
                    'dist/b': dict(path='evidence/b', sha256='a' * 64)})
        with self.assertRaisesRegex(ValueError, 'CHAINED_SOURCE_LOCATION'):
            SourceLocations(self.root)


if __name__ == '__main__':
    unittest.main()
