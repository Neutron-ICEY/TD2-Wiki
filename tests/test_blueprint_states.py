from current_identity import source_for
from tools import identity as identity_catalog
import json
import unittest
from pathlib import Path
from wiki_subset import WikiSubset
from reader_test_html import nodes

ROOT=Path(__file__).resolve().parents[1]

class BlueprintStatesTests(unittest.TestCase):
    def setUp(self):
        self.wiki=WikiSubset(ROOT)

    def test_confirmed_named_relation_and_unknown_identity_are_distinct(self):
        known=self.wiki.expand('{{#invoke:TD2品牌投影|blueprintSource|source_subject=gear_511_keeper}}',{})
        self.assertIn('重建贮藏箱',known)
        unknown=self.wiki.expand('{{#invoke:TD2品牌投影|blueprintSource|source_subject=unknown}}',{})
        self.assertEqual(unknown,'<p>暂无获取资料</p>')

    def test_shared_list_preserves_order_and_empty_defaults(self):
        for value in ('','无制作图纸'):
            rendered=self.wiki.template('品牌图纸列表',{'列表':value})
            self.assertEqual([n.text for n in nodes(rendered,'td2-blueprint-none')],['无制作图纸'])
            self.assertNotIn('state/craft',rendered)
        for value in ('NON-GAME-FACT 甲','NON-GAME-FACT 乙;NON-GAME-FACT 甲'):
            rendered=self.wiki.template('品牌图纸列表',{'列表':value})
            items=[n for n in nodes(rendered,'td2-blueprints')[0].children if getattr(n,'tag','')=='li']
            self.assertEqual([n.text for n in items],value.split(';'))
            self.assertEqual(rendered.count('data-icon-key="state/craft"'),len(items))

    def test_holiday_records_render_without_blueprints_or_unconfirmed_sources(self):
        records=identity_catalog.read_json(ROOT/'data/equipment/records.json')['entities']
        for title,name in [('影子军团股份有限公司','节日快递'),('毒蜥守卫队','放轻松'),('电力','雪花机'),('捷克出产自律组织','动荡')]:
            source=source_for(title).read_text('utf8')
            entity=next(e for e in records.values() if e['page_title']=='品牌套装-'+title)
            record=next(r for r in entity['collections']['具名装备资料']['rows'] if r['装备名称']==name)
            rendered=self.wiki.expand(source,{})
            card=next(n for n in nodes(rendered,'td2-equipment') if n.attrs.get('id')=='named-'+record['stable_id'])
            self.assertTrue(card.find_all('td2-blueprint-none'))
            self.assertNotIn('重建贮藏箱',card.text)
            self.assertNotIn('td2-model-craftable',card.text)
            self.assertNotIn('备注',card.text)
            sources = [n.text for n in card.find_all('td2-acquisition-result')]
            self.assertEqual(sources, ['无制作图纸', '活动获取' if name=='动荡' else '暂无获取资料'])
