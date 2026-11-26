from current_identity import entity_id, source_for, material_id, asset_file
import unittest
import re
from pathlib import Path
from tools import identity as identity_catalog
from wiki_subset import WikiSubset
from reader_test_html import nodes

ROOT=Path(__file__).resolve().parents[1]

class AcquisitionReaderTests(unittest.TestCase):
    def test_actual_page_families_and_named_cards_resolve_guide_ids(self):
        registry={r['id']:r for r in identity_catalog.registry(ROOT)}
        current={id:registry[id]['title'] for id in ('crafting-guide','loot-guide')}
        variants=[(current,{}),({'crafting-guide':'REVIEW-Crafting','loot-guide':'REVIEW-Loot'},
            {'wiki/templates/TD2页面地址.wiki':'{{#switch:{{{1|}}}|crafting-guide=REVIEW-Crafting|loot-guide=REVIEW-Loot|#default=}}'})]
        for targets,sources in variants:
            for id,labels in [('brand-511-tactical',{'装备图纸','图纸获取','装备获取'}),
                              ('gear-set-ongoing-directive',{'装备图纸','图纸获取','装备获取'}),
                              ('exotic-page-memento',{'装备获取'})]:
                with self.subTest(page=id,targets=targets):
                    raw=(ROOT/registry[id]['source']).read_text('utf8')
                    rendered=WikiSubset(ROOT,sources=sources).expand(raw,{})
                    sections=[('page',rendered,labels)]
                    if id=='brand-511-tactical':
                        cards=nodes(rendered,'td2-equipment')
                        self.assertEqual(len(cards),2)
                        sections.extend(('named',card.text,{'图纸获取','装备获取'}) for card in cards)
                    for kind,content,expected in sections:
                        links=re.findall(r'\[\[([^\[\]|]+)\|(装备图纸|图纸获取|装备获取)\]\]',content)
                        self.assertTrue(expected <= {label for _,label in links},kind)
                        for target,label in links:
                            self.assertEqual(target,targets['loot-guide' if label=='装备获取' else 'crafting-guide'])

    def test_unknown_equipment_and_blueprint_sources_keep_their_fallback(self):
        reader=WikiSubset(ROOT)
        for method in ['acquisition','blueprintSource']:
            result=reader.expand('{{#invoke:TD2品牌投影|'+method+'|source_subject=unknown-review-subject}}',{})
            self.assertIn('<p>暂无获取资料</p>',result)
            self.assertNotIn('特殊途径：',result)

    def test_absent_blueprint_source_has_a_paragraph_in_every_page_family(self):
        # MediaWiki inserts this paragraph online; the local subset renderer
        # does not. The shared source must give both environments the same box.
        for group,title in [('brands','沃克与哈里斯企业'),('gear-sets','巅峰协议'),('brands','捷克出产自律组织')]:
            result=WikiSubset(ROOT).expand(source_for(title).read_text('utf8'),{})
            blocks=[n for n in nodes(result,'td2-acquisition-result') if n.text=='无制作图纸']
            self.assertTrue(blocks,title)
            for block in blocks:
                elements=[n for n in block.children if hasattr(n,'tag')]
                self.assertEqual([n.tag for n in elements],['p'])
                self.assertEqual(elements[0].text,'无制作图纸')

    def test_hunter_routes_survive_without_manual_source_records(self):
        reader=WikiSubset(ROOT)
        raw=(ROOT/'wiki/pages/brands/品牌套装-戈兰装备有限公司.wiki').read_text('utf8')
        result=reader.expand(raw,{})
        hunter=next(n for n in nodes(result,'td2-equipment') if '猎人杀手' in n.text)
        self.assertEqual([n.text for n in hunter.find_all('td2-acquisition-result')],
                         ['猎人箱解锁后依娜亚出售','避风港猎人箱猎人箱解锁后可在卡西购买制作台制作'])
        self.assertFalse(reader.ref_calls)
        self.assertNotIn('备注',hunter.text)
        self.assertNotIn('钥匙',hunter.text)
        self.assertNotIn('具名装备资料',raw)

    def test_other_information_remains_separate_from_automatic_results(self):
        for group,title in [('brands','戈兰装备有限公司'),('gear-sets','核心力量'),('exotic-gear','追悼')]:
            reader=WikiSubset(ROOT)
            raw=source_for(title).read_text('utf8')
            before=reader.expand(raw,{})
            after=reader.expand(raw.replace('|资料ID=','|其他机制=NON-GAME-FACT 独立正文\n|资料ID=',1),{})
            self.assertIn('NON-GAME-FACT 独立正文',after)
            self.assertEqual([n.text for n in nodes(before,'td2-acquisition-result')],
                             [n.text for n in nodes(after,'td2-acquisition-result')])
            self.assertNotIn('td2-acquisition-notes',after)
