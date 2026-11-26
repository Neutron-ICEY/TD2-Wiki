"""Localized names use the registered item UID, inherited fields and each language independently."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.equipment.weapon_projection import WeaponProjection
from tools.equipment.weapons_native import DISABLED_DESCRIPTION, WeaponNative


class WeaponNames(unittest.TestCase):
    base_uid = '5D4179F1569771580000DB08F5A8CF47'
    named_uid = 'F58BDD5662DE9D6C0008594BC73A8023'
    base_text = '11111111111111111111111111111111'
    named_text = '22222222222222222222222222222222'

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for rel in ('juice/shdresearch/shdresearch.juice','rejuice/itemmodtaghierarchy.rejuice'):
            path = self.root/'hunter/game system data'/rel
            path.parent.mkdir(parents=True)
            path.touch()
        source = self.root/'family.mitem'
        sections = []
        for name, uid, text in [('base', self.base_uid, self.base_text), ('named', self.named_uid, self.named_text)]:
            parent = ' : base' if name == 'named' else ''
            sections.append(f'''WeaponItem {name} < uid={uid} >{parent}
{{
    myUIName "guid = #{text}, text = 'embedded', type = 'MenuLine'"
''')
            if name == 'base':
                sections.append('    myWeapon = fixture_weapon ' + '3'*32 + '\n')
            sections.append('}\n')
        sections.append('Weapon fixture_weapon < uid=' + '3'*32 + ' >\n{\n    myRPM 120\n}\n')
        source.write_text(''.join(sections),encoding='utf8')
        self.bindings = [dict(uid=uid,source=source.name,kind=kind,group='Shotgun',name='旧名称',en='Old name')
                         for uid,kind in [(self.base_uid,'normal'),(self.named_uid,'named')]]

    def language(self, language, rows):
        path = self.root/'hunter/localization/packages'/language/'menus.locpack'
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('w',encoding='utf8',newline='') as out:
            csv.writer(out).writerows((guid,'',value) for guid,value in rows)

    def project(self, bindings=None):
        projector = WeaponProjection(WeaponNative(self.root))
        return projector.project([{'id':'weapon:'+self.base_uid.lower(),'items':bindings or self.bindings}])

    def test_root_and_named_renames_use_separate_fields(self):
        self.language('simplifiedchinese',[(self.base_text,'底型新名'),(self.named_text,'具名新名')])
        self.language('english',[(self.base_text,'New base')])
        result = self.project()
        page = result['entities'][0]
        self.assertEqual(page['source'],'wiki/pages/weapons/'+self.base_uid.lower()+'.wiki')
        units = page['units']
        rows = [u['semantic'] for u in units if u['target']['field']=='data']
        self.assertEqual([(r['装备UID'],r['装备名称']) for r in rows],
                         [(self.base_uid,'底型新名'),(self.named_uid,'具名新名')])
        self.assertNotIn('英文原名',rows[1])
        self.assertIn((self.named_uid,'英文原名'),[(i['uid'],i['field']) for i in result['unavailable']])
        self.assertEqual({u['target']['field']:u['value'] for u in units if not u['target']['records']},
                         {'装备名称':'底型新名','英文原名':'New base'})
        reordered = self.project(self.bindings[::-1])['entities'][0]['units']
        self.assertEqual({u['target']['field']:u['value'] for u in reordered if not u['target']['records']},
                         {'装备名称':'底型新名','英文原名':'New base'})
        self.assertFalse(any(not u['target']['records'] for u in self.project(self.bindings[1:])['entities'][0]['units']))

    def test_description_placeholder_and_unavailable_translation_are_distinct(self):
        guid = '3A' * 16
        path = self.root/'family.mitem'
        original = path.read_text('utf8')
        self.language('simplifiedchinese', [])
        self.language('english', [])

        def read_description(enabled, text):
            source = f'''    myDescription "enabled = {enabled}, guid = #{guid}, lineVersion = 0, text = '{text}'"'''
            path.write_text(original.replace('    myWeapon =', source + '\n    myWeapon ='), encoding='utf8')
            native = WeaponNative(self.root)
            return native.item_description(native.record('family.mitem', self.named_uid))

        self.assertEqual(read_description('false', DISABLED_DESCRIPTION), '')
        with self.assertRaises(KeyError):
            read_description('true', DISABLED_DESCRIPTION)
        with self.assertRaises(KeyError):
            read_description('false', 'An actual description')
        self.language('english', [(guid, 'English description')])
        with self.assertRaises(KeyError):
            read_description('false', DISABLED_DESCRIPTION)
        self.language('simplifiedchinese', [(guid, '本地化说明')])
        self.assertEqual(read_description('true', 'An actual description'), '本地化说明')

    def test_missing_pack_and_blank_string_leave_the_other_language_available(self):
        self.language('english',[(self.base_text,'New base'),(self.named_text,'   ')])
        result = self.project()
        units = result['entities'][0]['units']
        self.assertEqual({u['target']['field']:u['value'] for u in units if not u['target']['records']},
                         {'英文原名':'New base'})
        self.assertNotIn('装备名称',units[0]['semantic'])
        self.assertNotIn('英文原名',units[1]['semantic'])
        self.assertEqual({(i['uid'],i['field']) for i in result['unavailable'] if i['field'] in ('装备名称','英文原名')},
                         {(self.base_uid,'装备名称'),(self.named_uid,'装备名称'),(self.named_uid,'英文原名')})

    def test_only_the_reviewed_inherited_literal_can_fill_a_missing_entry(self):
        self.language('english',[])
        source = self.root/'family.mitem'
        fixture = source.read_text('utf8')
        fixture = fixture.replace(self.base_text,'346395BC5D5BAB8400037EECCE058F36')
        fixture = fixture.replace("'embedded'","'KSG Shotgun'",1)
        named_line = next(line for line in fixture.splitlines() if self.named_text in line)
        fixture = fixture.replace(named_line,'')
        source.write_text(fixture,encoding='utf8')
        row = self.project()['entities'][0]['units'][1]['semantic']
        self.assertEqual(row['英文原名'],'KSG Shotgun')
        source.write_text(fixture.replace("'KSG Shotgun'","'Changed'"),encoding='utf8')
        row = self.project()['entities'][0]['units'][1]['semantic']
        self.assertNotIn('英文原名',row)
