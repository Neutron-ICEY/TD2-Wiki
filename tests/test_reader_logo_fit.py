from current_identity import entity_id, source_for, material_id, asset_file
import json
from pathlib import Path
import unittest

from PIL import Image

from wiki_subset import WikiSubset

ROOT = Path(__file__).resolve().parents[1]


class ReaderLogoFitTests(unittest.TestCase):
    def test_registered_logos_fit_the_shared_area_at_native_size(self):
        rows = json.loads((ROOT / 'publishing/registry.json').read_bytes())['entries']
        logos = [row for row in rows if row['kind'] == 'assets'
                 and row['source'].startswith(('assets/TD2-Brand-', 'assets/TD2-GearSet-'))
                 and row['source'].endswith('-Logo.png')]
        self.assertTrue(logos)
        for row in logos:
            with self.subTest(source=row['source']), Image.open(ROOT / row['source']) as image:
                self.assertLessEqual(image.width, 128)
                self.assertLessEqual(image.height, 128)

    def test_card_uses_original_image_and_old_image_uses_remain(self):
        filename = 'TD2-Brand-511Tactical-Logo.png'
        wiki = WikiSubset(ROOT, existing_files=['File:' + filename])
        for use, size in (('', 240), ('icon', 24)):
            output = wiki.template('TD2品牌图片', {'品牌': entity_id('5.11 Tactical'), '用途': use})
            self.assertIn('|%dx%dpx|' % (size, size), output)
            self.assertNotIn('td2-logo-art', output)
        card = wiki.template('品牌套装信息框', {'套装全称':'5.11 Tactical','图标品牌':entity_id('5.11 Tactical')})
        self.assertIn('td2-logo-art', card)
        self.assertIn('[[File:' + filename + '|link=|alt=5.11 Tactical]]', card)
        self.assertNotIn('240x240px', card)
        self.assertNotIn('--td2-logo-', card)

    def test_explicit_file_is_direct_and_empty_configuration_is_omitted(self):
        filename = 'NON-GAME-FACT-UNKNOWN.png'
        wiki = WikiSubset(ROOT, existing_files=['File:' + filename])
        output = wiki.template('TD2Logo显示', {'文件': filename, '名称': 'unknown'})
        self.assertIn('class="td2-logo-art"', output)
        self.assertIn('[[File:' + filename, output)
        self.assertIn('[[File:' + filename, WikiSubset(ROOT).template('TD2Logo显示', {'文件': filename}))
        self.assertEqual(WikiSubset(ROOT).template('TD2Logo显示', {'文件': ''}).strip(), '')


if __name__ == '__main__':
    unittest.main()
