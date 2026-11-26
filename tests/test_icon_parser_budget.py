from tools import identity as identity_catalog
import unittest
import json
from pathlib import Path
from tools.brand_sets.icons import wikitext_icon, mappings, resolver_source, weapon_talent_icons
from tools.brand_sets.model import load_catalog
from tools.brand_sets.equipment import load_equipment
from tools.brand_sets.knowledge import load_knowledge

ROOT = Path(__file__).resolve().parents[1]


class IconParserBudgetTests(unittest.TestCase):
    def test_confirmed_icons_do_not_spend_existence_checks(self):
        for key in ('equipment_slot/mask', 'state/proficient', 'talent/test'):
            rendered = wikitext_icon(key, {'wiki_file': 'Test.png', 'confirmed_on_wiki': True})
            self.assertNotIn('#ifexist', rendered)
            self.assertIn('[[File:Test.png|', rendered)
        self.assertIn('64x64px', wikitext_icon('equipment_slot/mask', {'wiki_file': 'Test.png', 'confirmed_on_wiki': True}))

    def test_known_unpublished_icons_are_direct_and_empty_icons_keep_fallback(self):
        for key in ('equipment_slot/mask', 'state/proficient', 'talent/test'):
            unpublished = wikitext_icon(key, {'wiki_file': 'Test.png', 'confirmed_on_wiki': False})
            self.assertEqual(unpublished, wikitext_icon(key, {'wiki_file': 'Test.png', 'confirmed_on_wiki': True}))
            self.assertIn('[[File:Test.png|', unpublished)
            self.assertNotIn('#ifexist', unpublished)
        self.assertIn('td2-icon-placeholder', wikitext_icon('equipment_slot/mask', {'wiki_file': '', 'confirmed_on_wiki': False}))
        self.assertEqual(wikitext_icon('state/proficient', {'wiki_file': '', 'confirmed_on_wiki': False}), '')

    def test_registered_projection_matches_current_catalog(self):
        catalog, categories = load_catalog(ROOT)
        knowledge = load_knowledge(ROOT, catalog)
        entries = mappings(load_equipment(ROOT)[1], categories, knowledge[2], knowledge[1], gear_sets=identity_catalog.read_json(ROOT / 'data/gear-sets/sets.json')['sets'])
        for key, icon in weapon_talent_icons(ROOT).items():
            entries['talent/' + key] = icon
        for talent in identity_catalog.read_json(ROOT / 'data/exotic-gear/talents.json')['talents']:
            if talent.get('icon'):
                key = 'talent/' + talent['id']
                self.assertNotIn(key, entries)
                entries[key] = talent['icon']
        rendered = resolver_source(entries)
        assets = {row['title'].split(':', 1)[-1]: row for row in identity_catalog.registry(ROOT) if row['kind'] == 'assets'}
        for key, icon in entries.items():
            if icon['wiki_file']:
                self.assertIn(icon['wiki_file'], assets, key)
                self.assertTrue((ROOT / assets[icon['wiki_file']]['source']).is_file(), key)
        self.assertEqual(rendered, (ROOT / 'wiki/templates/TD2图标.wiki').read_text(encoding='utf-8'))
        for key, icon in entries.items():
            self.assertNotIn('#ifexist', wikitext_icon(key, dict(icon, confirmed_on_wiki=False)), key)
        self.assertNotIn('#ifexist', rendered)

    def test_maintained_page_target_does_not_depend_on_remote_existence(self):
        from tools.brand_sets.icons import pool_wikitext
        ui = {'talent_pools': {'chest': {'label': '胸甲天赋', 'target': '测试资料#稳定锚点'}}}
        self.assertEqual(pool_wikitext(ui, 'chest'), '[[测试资料#稳定锚点|胸甲天赋]]')
        ui['talent_pools']['chest']['target'] = ''
        self.assertEqual(pool_wikitext(ui, 'chest'), '胸甲天赋')

    def test_random_state_uses_its_own_mapping_and_rejects_old_row_key(self):
        import copy
        from tools.brand_sets.equipment import validate_ui
        _, ui = load_equipment(ROOT)
        self.assertEqual(mappings(ui)['state/random'], ui['state_icons']['random'])
        old = copy.deepcopy(ui)
        old['icons']['random_attribute'] = old['icons'].pop('minor_attribute')
        with self.assertRaises(ValueError):
            validate_ui(old)
        del old['state_icons']['random']
        self.assertEqual(mappings(old)['state/random']['wiki_file'], '')

    def test_heading_uses_explicit_icon_or_default_slot(self):
        from wiki_subset import WikiSubset
        source = (ROOT / 'wiki/templates/装备标题卡.wiki').read_text(encoding='utf8')
        self.assertNotIn('#ifexist', source)
        reader = WikiSubset(ROOT, existing_files=[])
        for explicit_icon in ['', '<span>ICON</span>']:
            with self.subTest(explicit_icon=explicit_icon):
                result = reader.template('装备标题卡', {'中文名称': '测试', '图标键': 'mask', '图标': explicit_icon})
                if explicit_icon:
                    self.assertIn(explicit_icon, result)
                    self.assertNotIn('data-icon-key="equipment_slot/mask"', result)
                else:
                    self.assertIn('data-icon-key="equipment_slot/mask"', result)
                    self.assertIn('|64x64px|', result)

    def test_registered_composed_visual_is_independent_of_publication(self):
        from wiki_subset import WikiSubset
        from tools.brand_sets.equipment_projection import equipment_sources
        from tools.brand_sets.logos import source as logo_source
        from tools.brand_sets.build import GENERATED
        base, ui = load_equipment(ROOT)
        brands = identity_catalog.read_json(ROOT / 'data/brand-sets/brands.json')
        sources = equipment_sources(base, ui, brand_catalog=brands)
        visual = sources[GENERATED['equipment-visual']]
        self.assertNotIn('#ifexist', visual)
        self.assertNotIn('#ifexist', sources[GENERATED['brand-auto-image']])
        self.assertNotIn('#ifexist', logo_source())
        brand, logo = next(iter(brands['entity_images'].items()))
        for slot, item in ui['slot_visuals'].items():
            with self.subTest(slot=slot):
                params = {'部位': slot, '品牌': brand}
                unpublished = WikiSubset(ROOT, existing_files=[], sources=sources).template('TD2装备视觉', params)
                published = WikiSubset(ROOT, existing_files=['File:' + item['wiki_file'], 'File:' + logo], sources=sources).template('TD2装备视觉', params)
                self.assertEqual(unpublished, published)
                self.assertIn('[[File:' + item['wiki_file'] + '|128x128px|', unpublished)
                self.assertIn('[[File:' + logo + '|80x80px|', unpublished)
                for missing_brand in ['', 'missing-entity']:
                    default = WikiSubset(ROOT, sources=sources).template('TD2装备视觉', {'部位': slot, '品牌': missing_brand})
                    self.assertIn('[[File:' + item['wiki_file'] + '|128x128px|', default)
                    self.assertNotIn('td2-logo-image', default)


if __name__ == '__main__':
    unittest.main()
