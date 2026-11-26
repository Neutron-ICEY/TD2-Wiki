import copy
from pathlib import Path
import unittest

from tools.brand_sets.equipment import load_equipment, validate_ui
from tools.brand_sets.icons import html_icon, mappings, resolver_source
from reader_test_html import nodes
import json
from wiki_subset import WikiSubset

ROOT = Path(__file__).resolve().parents[1]


class ReaderStatusIconsTests(unittest.TestCase):
    def test_approved_icons_remain_local_ready(self):
        _, ui = load_equipment(ROOT)
        for key in ['state/drop','state/craft','state/named']:
            icon=mappings(ui)[key]
            self.assertTrue(icon['local_available'])
            self.assertTrue((ROOT/'assets'/icon['wiki_file']).is_file())
        invalid = copy.deepcopy(ui)
        invalid['state_icons']['unapproved_status'] = ui['state_icons']['drop']
        with self.assertRaises(ValueError):
            validate_ui(invalid)

    def test_known_files_and_keyboard_targets_do_not_depend_on_publication(self):
        _, ui = load_equipment(ROOT)
        for key, label in {'state/drop':'可掉落','state/named':'具名装备'}.items():
            category,name=key.split('/')
            filename=mappings(ui)[key]['wiki_file']
            confirmed=WikiSubset(ROOT,existing_files=['File:'+filename]).template('TD2图标',{'类别':category,'键':name})
            self.assertIn('[[File:'+filename+'|24x24px',confirmed)
            entries={key:{'wiki_file':'NON-GAME-FACT.png','confirmed_on_wiki':False}}
            sources={'wiki/templates/TD2图标.wiki':resolver_source(entries)}
            for files in ([],['File:NON-GAME-FACT.png']):
                output=WikiSubset(ROOT,existing_files=files,sources=sources).template('TD2图标',{'类别':category,'键':name})
                self.assertIn('tabindex="0" role="img" aria-label="'+label+'"',output)
                self.assertIn('data-tooltip="'+label+'"',output)
                self.assertIn('[[File:NON-GAME-FACT.png|24x24px', output)
            self.assertIn('data-tooltip="'+label+'"',html_icon(category,name))
        source=resolver_source({'state/craft':{'wiki_file':'','confirmed_on_wiki':False}})
        for wiki in (WikiSubset(ROOT),WikiSubset(ROOT,sources={'wiki/templates/TD2图标.wiki':source})):
            blueprints=wiki.template('品牌图纸列表',{'列表':'TEST BP A;TEST BP B'})
            self.assertEqual([n.text for n in nodes(blueprints,'td2-blueprints')],['TEST BP ATEST BP B'])
            self.assertNotIn('td2-status-icon',blueprints)
            self.assertNotIn('tabindex=',blueprints)
            self.assertNotIn('data-tooltip=',blueprints)
            self.assertEqual(blueprints.count('data-icon-key="state/craft"'),2)

    def test_unrelated_icon_roles_keep_their_contract(self):
        self.assertNotIn('td2-status-icon', html_icon('state', 'blue'))
        self.assertNotIn('tabindex=', html_icon('equipment_slot', 'backpack'))
        wiki = WikiSubset(ROOT, existing_files=['File:TD2-Gear-Backpack-Icon.png'])
        self.assertIn('|64x64px|', wiki.template('TD2图标', {'类别': 'equipment_slot', '键': 'backpack', '用途': 'heading'}))
        self.assertIn('|24x24px|', wiki.template('TD2图标', {'类别': 'equipment_slot', '键': 'backpack'}))


if __name__ == '__main__':
    unittest.main()
