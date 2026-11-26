"""A missing or incomplete appearance index must stay unavailable for every model."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.equipment.weapon_projection import WeaponProjection
from tools.equipment.weapons_native import WeaponNative


class WeaponSkinCache(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for rel in ('juice/shdresearch/shdresearch.juice', 'rejuice/itemmodtaghierarchy.rejuice'):
            path = self.root/'hunter/game system data'/rel
            path.parent.mkdir(parents=True)
            path.touch()
        self.hunter = self.root/'hunter/game system data/juice/item'
        self.rogue = self.root/'rogue/game system data/juice/item'
        self.hunter.mkdir(parents=True)
        self.rogue.mkdir(parents=True)
        native = WeaponNative(self.root)
        native.texts['zh'] = {'1'*32: '第一款', '2'*32: '第二款'}
        self.projection = WeaponProjection(native)

    def write_skin(self, folder, tag, digit, kind='WeaponTransmogItem'):
        path = folder/'appearance.mitem'
        path.write_text(f'''{kind} appearance_{digit} < uid={digit*32} >
{{
    myUIName "guid = #{digit*32}, text = 'skin', type = 'MenuLine'"
    myModTags
    {{
        ItemModTag "New ItemModTag (1)" {tag}
    }}
}}
''', encoding='utf8')
        return path

    def skins(self, tag):
        return self.projection.skins([{'slot':'WeaponSkin', 'tags':[tag]}])

    def test_general_tags_require_a_preattached_uid(self):
        self.write_skin(self.hunter, 'Skin', '1', 'WeaponSkinItem')
        self.write_skin(self.rogue, 'Mod', '2', 'WeaponSkinItem')
        slot={'slot':'WeaponSkin','tags':['Skin','Mod','Specific']}
        self.assertEqual(self.projection.skins([slot]), [])
        slot['mods']=[{'uid':'1'*32}]
        skin,=self.projection.skins([slot])
        self.assertEqual((skin['uid'],skin['preattached']),('1'*32,True))

    def test_unreleased_skin_does_not_hide_another_skin_on_the_same_socket(self):
        self.write_skin(self.hunter, 'SharedSocket', '3')
        self.write_skin(self.rogue, 'SharedSocket', '1')
        with self.assertRaises(KeyError):
            self.skins('SharedSocket')
        self.projection.unreleased_skin_uids.add('3'*32)
        self.assertEqual([skin['uid'] for skin in self.skins('SharedSocket')], ['1'*32])

    def test_parse_failure_remains_unavailable_for_two_models_and_retries(self):
        self.write_skin(self.hunter, 'FirstModel', '1')
        (self.rogue/'appearance.mitem').write_bytes(b'WeaponTransmogItem \xff')
        for tag in ('FirstModel', 'SecondModel'):
            with self.subTest(tag=tag), self.assertRaises(UnicodeDecodeError):
                self.skins(tag)
        self.write_skin(self.rogue, 'SecondModel', '2')
        for tag, expected in [('FirstModel', '第一款'), ('SecondModel', '第二款')]:
            with self.subTest(recovered=tag):
                self.assertEqual([skin['name'] for skin in self.skins(tag)], [expected])

    def test_missing_namespace_retries_and_empty_readable_directories_are_known(self):
        self.rogue.rmdir()
        for tag in ('FirstModel', 'SecondModel'):
            with self.subTest(tag=tag), self.assertRaises(FileNotFoundError):
                self.skins(tag)
        self.rogue.mkdir()
        self.assertEqual(self.skins('SecondModel'), [])

    def test_each_candidate_is_checked_before_any_prefilter_read(self):
        candidate = self.rogue/'unreadable.mitem'
        candidate.touch()
        native = self.projection.n
        resolve = native.file
        read = Path.read_bytes
        attempted_reads = []

        def validate(source):
            path = resolve(source)
            if path == candidate:
                raise ValueError('Native path outside resource root')
            return path

        def read_bytes(path):
            attempted_reads.append(path)
            return read(path)

        with patch.object(native, 'file', validate), patch.object(Path, 'read_bytes', read_bytes):
            with self.assertRaisesRegex(ValueError, 'outside resource root'):
                self.skins('FirstModel')
            self.assertNotIn(candidate, attempted_reads)
        with patch.object(Path, 'read_bytes', side_effect=PermissionError('fixture read denied')):
            for tag in ('FirstModel', 'SecondModel'):
                with self.subTest(tag=tag), self.assertRaises(PermissionError):
                    self.skins(tag)
        self.assertEqual(self.skins('SecondModel'), [])
