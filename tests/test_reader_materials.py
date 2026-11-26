"""Focused material presentation tests; synthetic quantities are not game facts."""
import copy
import re
import unittest
from pathlib import Path
from tools import identity as identity_catalog
from tools.brand_sets.equipment import load_equipment, validate_ui
from tools.brand_sets.icons import mappings, material_row_source, material_row_html
from tools.brand_sets.equipment_projection import equipment_sources
from tools.brand_sets.build import GENERATED

ROOT=Path(__file__).resolve().parents[1]

class ReaderMaterialTests(unittest.TestCase):
    def setUp(self): self.base,self.ui=load_equipment(ROOT)
    def test_registered_material_pages_render_by_stable_identity(self):
        from wiki_subset import WikiSubset
        registry={r['id']:r for r in identity_catalog.registry(ROOT)}
        pages=[r for r in registry.values() if r['source'].startswith('wiki/pages/materials/')]
        materials={v['page_ref']:(key,v) for key,v in self.ui['material_display'].items() if v.get('page_ref')}
        records=identity_catalog.read_json(ROOT/'data/equipment/records.json')['entities']
        self.assertEqual(len(pages),12)
        for page in pages:
            with self.subTest(page=page['id']):
                key,info=materials[page['id']]
                filename=(registry[records[info['brand_ref']]['visuals']['logo']]['title'].split(':',1)[1]
                          if info.get('brand_ref') else self.ui['material_icons'][info['icon_key']]['wiki_file'])
                raw=(ROOT/page['source']).read_text('utf8')
                rendered=WikiSubset(ROOT,existing_files=['File:'+filename]).expand(raw,{})
                self.assertIn('|材料ID='+key+'|',raw)
                self.assertIn('td2-material-row td2-material-'+info['quality']+'"',rendered)
                self.assertNotIn('td2-material-unknown',rendered)
                self.assertIn('[[File:'+filename+'|24x24px|link='+page['title']+'|alt=]]',rendered)
                label=re.search(r'\{\{TD2材料行\|[^\n]*?\|名称=([^|}]+)',raw)[1]
                self.assertIn('[['+page['title']+'|'+label+']]',rendered)
    def view(self, ui=None, present=True):
        from wiki_subset import WikiSubset
        ui=ui or self.ui
        files={'File:'+v['wiki_file'] for v in mappings(ui).values() if v['wiki_file']} if present else set()
        from tools.brand_sets.icons import resolver_source
        return WikiSubset(ROOT,files,sources={'wiki/templates/TD2材料行.wiki':material_row_source(ui),'wiki/templates/TD2图标.wiki':resolver_source(mappings(ui))})
    def test_five_explicit_names_and_quality(self):
        published = {r['title'].split(':', 1)[-1] for r in identity_catalog.raw_json(ROOT/'publishing/baseline.json')['entries'] if r['namespace'] == 6}
        for key,quality in [('protective_fabric','gray'),('polycarbonate','green'),('electronics','blue'),('carbon_fiber','blue'),('ceramics','green')]:
            info=self.ui['material_display'][key]
            self.assertEqual(info['quality'],quality)
            self.assertTrue(self.ui['material_icons'][key]['local_available'])
            icon = self.ui['material_icons'][key]
            self.assertEqual(icon['confirmed_on_wiki'], icon['wiki_file'] in published)
        validate_ui(self.ui)
    def test_unknown_quantity_and_no_fake_identity(self):
        row=self.view().template('TD2材料行',{'名称':'未知材料'})
        self.assertIn('td2-material-unknown',row);self.assertIn('数量待核实',row)
        self.assertNotIn('File:',row)
        # A familiar name without stable identity cannot select an image.
        self.assertNotIn('File:',self.view().template('TD2材料行',{'名称':'防具布料'}))
        zero=self.view().template('TD2材料行',{'名称':'防具布料','材料ID':'protective_fabric','数量':'0'})
        self.assertIn('td2-material-quantity">0',zero)
    def test_local_files_and_publication_are_separate(self):
        args={'名称':'防御性布料','材料ID':'protective_fabric','数量':'23 / 46'}
        present=self.view().template('TD2材料行',args);missing=self.view(present=False).template('TD2材料行',args)
        self.assertIn('[[材料-防具布料|防御性布料]]',present)
        self.assertIn('|link=材料-防具布料|',present)
        self.assertIn('[[File:'+self.ui['material_icons']['protective_fabric']['wiki_file']+'|',missing)
        self.assertNotIn('td2-icon-placeholder',missing)
        self.assertIn('[[材料-防具布料|防御性布料]]',missing)
    def test_probability_is_optional_and_follows_quantity(self):
        args={'名称':'陶瓷碎片','材料ID':'ceramics','数量':'0 / 8','概率说明':'20%'}
        expected='<span class="td2-material-quantity">0 / 8</span><span class="td2-material-probability">[20%]</span>'
        self.assertIn(expected,self.view().template('TD2材料行',args))
        self.assertIn(expected,material_row_html(self.ui,'陶瓷碎片','0 / 8',probability='20%',material_id='ceramics'))
        hidden=self.view().template('TD2材料行',dict(args,显示数量='否'))
        self.assertNotIn('td2-material-probability',hidden);self.assertNotIn('td2-material-quantity',hidden)
    def test_six_weaves_resolve_to_matching_files_and_links(self):
        for slot in ['mask','chest','holster','backpack','gloves','kneepads']:
            key='weave_'+slot;info=self.ui['material_display'][key];name=info['name'];file=self.ui['material_icons'][key]['wiki_file']
            row=self.view().template('TD2材料行',{'名称':name,'材料ID':key,'数量':'0–1'})
            self.assertIn('[[File:'+file+'|24x24px|link=材料-'+name+'|alt=]]',row)
            self.assertIn('[[材料-'+name+'|'+name+']]',row)
            self.assertIn('0–1',row);self.assertNotIn('td2-icon-placeholder',row)
    def test_material_gradient_keeps_original_accent(self):
        css=(ROOT/'ui/brand-sets/brand-sets.css').read_text(encoding='utf-8')
        self.assertIn('--td2-heading-start: color-mix(in srgb, color-mix(in srgb, var(--td2-heading-accent) 55%, #000) 50%, transparent)',css)
        self.assertIn('--td2-heading-accent: var(--td2-material-accent, var(--td2-quality-neutral-accent))',css)
        for quality,color in [('gray','#a6a6a6'),('green','#78c832'),('blue','#5080ff'),('high_end','#ffaf10')]:
            self.assertIn('.td2-material-'+quality+' { --td2-material-accent: '+color+'; }',css)

    def test_local_css_scope(self):
        css=(ROOT/'ui/brand-sets/brand-sets.css').read_text(encoding='utf-8').split('/* Approved material presentation only;')[1]
        self.assertIn('filter: none; box-shadow: none; text-shadow: none;',css)
        self.assertNotIn('drop-shadow(',css)
        self.assertNotIn('#30343a',css)
        self.assertIn('.td2-brand .td2-material-row',css)
        full=(ROOT/'ui/brand-sets/brand-sets.css').read_text(encoding='utf-8')
        self.assertIn('.td2-equipment-heading-card, .td2-brand .td2-material-row, .td2-brand .td2-brand-infobox-frame { background: linear-gradient',full)
        self.assertIn('.td2-quality-high_end { --td2-heading-accent: var(--td2-quality-high-end-accent);',full)


if __name__=='__main__':unittest.main()
