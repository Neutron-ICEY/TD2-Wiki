import json
import re
import unittest
import html
from pathlib import Path
from tools.equipment.wikitext import WikiSubset

ROOT=Path(__file__).resolve().parents[1]
class TalentNotesTests(unittest.TestCase):
    def render(self,raw):
        return WikiSubset(ROOT).expand(raw,{})
    def test_editor_export_preserves_json_without_executable_wiki_markup(self):
        result=self.render('{{#invoke:TD2编辑数据|export}}')
        encoded=re.search(r'data-td2-editor-catalog="([^"]+)"',result)[1]
        self.assertNotIn('{{',encoded)
        self.assertNotIn('[[',encoded)
        catalog=json.loads(html.unescape(encoded))['options']['equipmentCatalog']
        names=[t['name'] for e in catalog.values() for t in e.get('talents',[])]
        entities=json.loads((ROOT/'data/equipment/records.json').read_text('utf8'))['entities']
        expected=[(uid,row['效果ID'],row['模式'],row['名称']) for uid,e in entities.items()
                  if e['template'] in ('装备组信息','奇特装备信息','武器信息') for row in e['effects'] if row.get('名称')]
        exported=[(uid,t['id'],t['mode'],t['name']) for uid,e in catalog.items() for t in e.get('talents',[])]
        self.assertCountEqual(exported,expected)
        self.assertTrue(any('{{TD2文字' in name for name in names))
    def test_existing_pve_note_is_on_name_and_absent_from_pvp(self):
        raw=(ROOT/'wiki/pages/gear-sets/装备组-烈焰大炮.wiki').read_text('utf8')
        result=self.render(raw)
        note='从第4次连续爆头开始，只有该次爆头击杀目标，才会同时获得三项奖励。'
        self.assertEqual(result.count(note),1)
        self.assertRegex(result,r'头痛欲裂<ref name="td2-note-[^"]+-PvE" group="PvE">'+note)
        self.assertNotRegex(result,r'<ref\s[^>]+group="PvP"')
        self.assertIn('class="td2-brand-panel td2-brand-pve"><references group="PvE">',result)
        self.assertNotIn('<references group="PvP">',result)
    def test_exotic_multi_talent_note_modes_and_original_descriptions(self):
        data=json.loads((ROOT/'data/equipment/records.json').read_text('utf8'))
        identity='exotic:4cdce5b25be1b0b000032b512386d5e7'
        rows=data['entities'][identity]['effects']
        raw='{{奇特装备信息\n|资料ID='+identity+'\n'
        for index,row in enumerate(rows):
            if row.get('名称'):raw+='|天赋脚注:'+row['效果ID']+':'+row['模式']+'=TEST NOTE '+str(index)+'\n'
        result=self.render(raw+'}}')
        for index,row in enumerate(rows):
            if not row.get('名称'):continue
            self.assertRegex(result,re.escape(row['名称'])+r'<ref name="td2-note-'+re.escape(row['效果ID'])+'-'+row['模式']+'" group="'+row['模式']+'">TEST NOTE '+str(index)+'</ref>')
        self.assertEqual(result.count('TEST NOTE '),4)
        self.assertNotIn('四件套脚注',result)
if __name__=='__main__':unittest.main()
