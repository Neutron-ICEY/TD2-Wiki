"""English naming, registry addresses and unchanged asset identity; offline only."""
import copy, json, subprocess, unittest
from pathlib import Path
from tools import identity as identity_catalog
from tools.brand_sets.equipment import asset_image_name, validate_image_filename, load_equipment
from tools.brand_sets.brands import load_catalog
from tools.brand_sets.equipment_projection import equipment_sources
from tools.publish.bundle import title_key
from tools.asset_import.static_formats import claim_filename
from wiki_subset import WikiSubset
ROOT=Path(__file__).resolve().parents[1]
class ImageNamingTests(unittest.TestCase):
    def test_english_candidates_and_controlled_fields(self):
        self.assertEqual(asset_image_name('Brand','5.11 Tactical','Logo'),'TD2-Brand-511Tactical-Logo.png')
        self.assertEqual(asset_image_name('Talent','Charged','Icon',subtype='GearSet',owner='Cavalier'),'TD2-Talent-GearSet-Cavalier-Charged-Icon.png')
        self.assertEqual(asset_image_name('Brand','Golan Gear Ltd.','Logo'),'TD2-Brand-GolanGearLtd-Logo.png')
        self.assertEqual(asset_image_name('Weapon','Solid – Admiral for Invisible Hand','Icon',subtype='Skin'),
                         'TD2-Weapon-Skin-SolidAdmiralForInvisibleHand-Icon.png')
        for label in ['电力','name.png','a/b','a#b','a%b','a?b','a\nb','a\u202eb','']:
            with self.subTest(label=label),self.assertRaises(ValueError):asset_image_name('Brand',label,'Logo')
        with self.assertRaises(ValueError):asset_image_name('品牌','Electric','Logo')
    def test_native_color_markup_uses_visible_name(self):
        for label in ['<color name="legendary_orange">Perfect Jazz Hands</color>',
                      '<color name="legendary orange">Perfect Jazz Hands</color>',
                      '<color name=“orange”><color name="blue">Perfect Jazz</color> Hands </color>']:
            with self.subTest(label=label):
                self.assertEqual(asset_image_name('Talent',label,'Icon',subtype='Weapon'),
                                 'TD2-Talent-Weapon-PerfectJazzHands-Icon.png')
        for label in ['<img src="icon.dds">Jazz Hands','<b>Jazz Hands</b>',
                      '<color name="orange" broken>Jazz Hands</color>',
                      '<color name=" ">Jazz Hands</color>',
                      '<color name="legendary\norange">Jazz Hands</color>']:
            with self.subTest(label=label),self.assertRaises(ValueError):
                asset_image_name('Talent',label,'Icon')
        self.assertEqual(asset_image_name('Talent','<color name="legendary orange">Shared Effects</color>',
                         'Icon',subtype='GearSet',owner='<color name="legendary orange">Ortiz: Reficere</color>'),
                         'TD2-Talent-GearSet-OrtizReficere-SharedEffects-Icon.png')

    def test_semantic_colon_in_name_and_owner_keeps_filename_safety(self):
        for name in ['Exuro','Reficere']:
            with self.subTest(name=name):
                self.assertEqual(asset_image_name('GearSet','Ortiz: '+name,'Logo'),
                                 'TD2-GearSet-Ortiz'+name+'-Logo.png')
        for owner,label,expected in [('Ortiz: Reficere','SharedEffects','SharedEffects'),
                                     ('Ortiz: Exuro','Ortiz Incinerator Turret Prototype','OrtizIncineratorTurretPrototype')]:
            with self.subTest(owner=owner):
                self.assertEqual(asset_image_name('Talent',label,'Icon',subtype='GearSet',owner=owner),
                                 'TD2-Talent-GearSet-'+owner.replace(': ','')+'-'+expected+'-Icon.png')
        with self.assertRaises(ValueError):validate_image_filename('TD2-GearSet-Ortiz:Exuro-Logo.png')

    def test_apostrophes_join_possessives_and_contractions(self):
        for apostrophe in ["'",'’','‘','ʼ']:
            for label, expected in [("Striker's Battlegear",'StrikersBattlegear'),
                                    ("Hunter's Fury",'HuntersFury'),
                                    ("You Can Look But You Can't Touch",'YouCanLookButYouCantTouch')]:
                with self.subTest(apostrophe=apostrophe,label=label):
                    self.assertEqual(asset_image_name('GearSet',label.replace("'",apostrophe),'Logo'),
                                     'TD2-GearSet-'+expected+'-Logo.png')
        self.assertEqual(asset_image_name('Talent',"Dead Man's Hand",'Icon',subtype='GearSet',owner="Striker’s Battlegear"),
                         'TD2-Talent-GearSet-StrikersBattlegear-DeadMansHand-Icon.png')
        self.assertEqual(asset_image_name('Brand','WyvernWear & 5.11','Logo'),'TD2-Brand-WyvernWearAnd511-Logo.png')

    def test_global_file_collision_and_windows_safety(self):
        self.assertEqual(title_key('File:Cafe\u0301__Logo.png',6),title_key('文件:CAFÉ Logo.png',6))
        self.assertEqual(title_key('File:Straße.png',6),title_key('文件:STRASSE.png',6))
        used={};claim_filename('A B.png','same',used)
        with self.assertRaisesRegex(ValueError,'COLLISION'):claim_filename('a_b.png','same',used)
        for name in ['CON.png','COM¹.png','foo.png.png','../foo.png','foo.PNG','foo_.png']:
            with self.subTest(name=name),self.assertRaises(ValueError):validate_image_filename(name)
    def test_js_python_collision_keys_match(self):
        values=['Straße','Σςσ','Cafe\u0301__LOGO','ＡＢＣ','İ','A B']
        script="console.log(JSON.stringify("+json.dumps(values)+".map(require('./tools/naming.cjs').normalized)))"
        actual=json.loads(subprocess.check_output(['node','-e',script],cwd=ROOT,text=True,encoding='utf8'))
        from tools.publish.bundle import normalized_title_name
        self.assertEqual(actual,[normalized_title_name(x) for x in values])
    def test_registered_assets_have_unique_current_addresses(self):
        report=identity_catalog.validate(ROOT)
        self.assertEqual(report['assets'],sum(r['kind']=='assets' for r in identity_catalog.registry(ROOT)))
        self.assertGreater(report['assets'],0)
        rows=identity_catalog.registry(ROOT)
        self.assertEqual(len({title_key(r['title'],r['namespace']) for r in rows}),len(rows))
    def test_display_rename_cannot_change_asset_resolution(self):
        base,ui=load_equipment(ROOT);catalog=copy.deepcopy(load_catalog(ROOT));row=catalog['brands'][0]
        filename=row['wiki_filename'];row['zh_name']='NON-GAME-FACT renamed';row['source_names']['source_full_chinese_name']=row['zh_name']
        wiki=WikiSubset(ROOT,existing_files=['File:'+filename],sources=equipment_sources(base,ui,brand_catalog=catalog))
        self.assertIn('File:'+filename+'|',wiki.template('TD2品牌图片',{'品牌':row['entity_ref']}))
        self.assertNotIn('File:',wiki.template('TD2品牌图片',{'品牌':row['zh_name']}))
    def test_missing_asset_never_falls_back_to_a_similar_name(self):
        row=load_catalog(ROOT)['brands'][0]
        wiki=WikiSubset(ROOT,existing_files=['File:'+row['zh_name']+'.png'])
        rendered = wiki.template('TD2品牌图片', {'品牌':row['entity_ref']})
        self.assertIn('[[File:'+row['wiki_filename']+'|', rendered)
        self.assertNotIn('[[File:'+row['zh_name']+'.png|', rendered)
    def test_public_notice_keeps_copyright_and_semantic_example(self):
        entry=next(r for r in identity_catalog.registry(ROOT) if r['title']=='MediaWiki:Uploadfiles-info')
        s=(ROOT/entry['source']).read_text('utf8')
        self.assertIn('TD2-Brand-GolanGearLtd-Logo.png',s)
        self.assertIn('请不要上传他人创作的、著作权未知的图像。',s)
        self.assertIn('不代表取得著作权或上传许可',s)
