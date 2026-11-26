"""Local-ready assets retain separate identity and unconfirmed publication state."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.brand_sets.equipment import load_equipment, validate_ui
from tools.brand_sets.knowledge import raster
from tools.brand_sets.icons import mappings
from tools.publish.publisher import ManualPublisher
from wiki_subset import WikiSubset
from tools.brand_sets.icons import resolver_source

ROOT = Path(__file__).resolve().parents[1]
A = 'TD2-UI-MajorAttribute-Icon.png'
B = 'TD2-UI-ModSlot-Icon.png'
SLOTS = ('mask', 'chest', 'backpack', 'holster', 'gloves', 'kneepads')


class LocalEquipmentIconsTests(unittest.TestCase):
    def setUp(self):
        self.base, self.ui = load_equipment(ROOT)
        self.files = {'File:' + x['wiki_file'] for x in mappings(self.ui).values() if x['wiki_file']}
        self.wiki = WikiSubset(ROOT, self.files)

    def test_contract_is_scoped_and_not_publication(self):
        for group, key in (('icons', 'major_attribute'),):
            icon = self.ui[group][key]
            self.assertIsInstance(icon['confirmed_on_wiki'], bool)
            raster(icon)
            self.assertTrue(icon['local_available'])
            bad = copy.deepcopy(self.ui)
            bad[group][key]['confirmed_on_wiki'] = True
            validate_ui(bad)
            bad[group][key]['confirmed_on_wiki'] = 'true'
            with self.assertRaises(ValueError): validate_ui(bad)
        for badkey in ('typo', 'gear_mod_slots'):
            bad = copy.deepcopy(self.ui)
            bad['state_icons'][badkey] = bad['state_icons']['gear_mod_slot']
            with self.assertRaises(ValueError): validate_ui(bad)
        bad = copy.deepcopy(self.ui)
        bad['icons']['minor_attribute'] = bad['icons']['major_attribute']
        validate_ui(bad)  # Sharing a registered image is allowed.
        with self.assertRaises(RuntimeError): ManualPublisher().publish(ROOT, ROOT)

    def test_local_source_integrity_is_required(self):
        from tools import identity
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'publishing').mkdir();(root/'data/equipment').mkdir(parents=True)
            row=copy.deepcopy(next(r for r in identity.registry(ROOT) if r['source']=='assets/'+A))
            (root/'publishing/registry.json').write_text(json.dumps({'entries':[row]}),'utf8')
            (root/'data/equipment/records.json').write_text('{"entities":{}}','utf8')
            (root/'data/equipment/native-map.json').write_text('{"entities":[]}','utf8')
            with self.assertRaisesRegex(ValueError,'MISSING_OR_UNSAFE_SOURCE'):identity.validate(root)
            (root/'assets').mkdir();(root/row['source']).write_bytes(b'wrong bytes')
            with self.assertRaisesRegex(ValueError,'ASSET_BYTES_CHANGED'):identity.validate(root)
            del row['content_sha256']
            (root/'publishing/registry.json').write_text(json.dumps({'entries':[row]}),'utf8')
            for check_bytes in (False,True):
                with self.assertRaisesRegex(ValueError,'ASSET_SHA256_REQUIRED'):
                    identity.validate(root,check_bytes=check_bytes)

    def test_ordinary_all_slots_and_major_values(self):
        for slot in SLOTS:
            for values in ('red', 'blue', 'yellow', 'red;blue;yellow'):
                for mode in ('PvE', 'PvP'):
                    params = {'1': slot, '主属性': values, '模式': mode}
                    output = self.wiki.template('TD2普通装备规则', params)
                    self.assertIn('[[File:' + A + '|24x24px', output)
                    self.assertIn('[[File:' + B, output)
                    self.assertEqual('[[File:TD2-UI-GearModSlot-Icon.png' in output, slot in ('mask','chest','backpack'))
                    if 'blue' in values: self.assertIn('TD2-UI-Blue-Icon.png', output)
                    self.assertIn('TD2-UI-Random-Icon.png', output)

    def test_count_branches_and_named_override(self):
        for count in ('', '0', '1', '3', '251'):
            output = self.wiki.template('TD2普通装备规则', {'1':'mask', '主属性':'blue', '插件槽例外':'是', '插件槽数':count})
            self.assertEqual(output.count('[[File:' + B), int(count) if count in ('1','3') else 1)
            self.assertEqual(output.count('[[File:TD2-UI-GearModSlot-Icon.png'), int(count) if count in ('1','3') else 0)
            if count == '0': self.assertIn('无插件槽位', output)
            if count in ('','251'): self.assertIn('data-icon-key="state/unknown"', output)
            self.assertIn('TD2-UI-ModSlot-Icon.png', output)
        named = self.wiki.template('品牌装备摘要内容', {'stable_id':'override', '装备名称':'NON-GAME-FACT', '装备部位':'gloves', '插件槽例外':'是','插件槽数':'2'})
        self.assertEqual(named.count('[[File:' + B), 2)
        self.assertEqual(named.count('[[File:TD2-UI-GearModSlot-Icon.png'), 2)

    def test_fallback_and_distinct_files(self):
        self.assertNotEqual(A, B)
        for category, key in (('equipment_row','major_attribute'),('state','gear_mod_slot')):
            identity = category + '/' + key
            confirmed = WikiSubset(ROOT).template('TD2图标', {'类别':category,'键':key})
            self.assertIn('[[File:'+mappings(self.ui)[identity]['wiki_file']+'|', confirmed)
            self.assertNotIn('td2-icon-placeholder', confirmed)
            present=self.wiki.template('TD2图标', {'类别':category,'键':key})
            self.assertIn('[[File:'+mappings(self.ui)[identity]['wiki_file']+'|', present)
            source = resolver_source({identity:{'wiki_file':'','confirmed_on_wiki':False}})
            missing = WikiSubset(ROOT, sources={'wiki/templates/TD2图标.wiki':source}).template('TD2图标', {'类别':category,'键':key})
            self.assertIn('data-icon-key="'+identity+'"', missing)
            self.assertIn('td2-icon-placeholder', missing)
            self.assertNotIn('[[File:', missing)
        self.assertIn('TD2-UI-Random-Icon.png', self.wiki.template('TD2图标', {'类别':'state','键':'random'}))
        unknown = WikiSubset(ROOT).template('TD2图标', {'类别':'state','键':'unknown'})
        none = WikiSubset(ROOT).template('TD2图标', {'类别':'state','键':'none'})
        self.assertIn('>?</span>', unknown)
        self.assertIn('data-icon-key="state/none"', none)
        self.assertIn('[[File:'+self.ui['state_icons']['none']['wiki_file']+'|', none)
        self.assertNotIn('➖', none)
        self.assertNotEqual(none, unknown)


if __name__ == '__main__': unittest.main()
