"""Literal native references, bounded IL aliases and real corpus compatibility."""
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.asset_import.text_evidence import (APP_DATA, metadata_literal_value, native_definitions,
                                            native_references, translation_dictionary)
from tools.asset_import.text_library import DEFAULT_INDEX, ROOT, TextError, TextLibrary, identity, main, sha256
from text_snapshot import HistoricalTextLibrary
import test_text_library as fixtures


GUID='A'*32
UID='B'*32


def native_bytes(guid=GUID,uid=UID):
    return ('AttributeDictionary D\r\r\n{\r\r\n\tAttributeDefinition Name < uid='+uid+' >\r\r\n\t{\r\r\n'
        '\t\tmyUIName "enabled = false, guid = #'+guid+', lineVersion = 3, text = \\"Name {0}\\""\r\r\n\t}\r\r\n}\r\r\n').encode()


def dictionary_metadata(pairs):
    il=[dict(opcode='newobj',operand=dict(name='TypeSpecification::.ctor'))]
    for key,value in pairs:
        il += [dict(opcode='dup',operand=None),dict(opcode='ldstr',operand=key),dict(opcode='ldstr',operand=value),
               dict(opcode='callvirt',operand=dict(name='TypeSpecification::Add',signature='20020113001301'))]
    il.append(dict(opcode='stsfld',operand=dict(name=APP_DATA+'::TranslateDictionary')))
    for i,row in enumerate(il): row['offset']=i*5
    return dict(types=[dict(name=APP_DATA,methods=[dict(name='.cctor',token='0x06000001',rva=100,il=il)])])


class EvidenceReaderTests(unittest.TestCase):
    def test_inline_weapon_uid_and_parameters_are_separate_from_item(self):
        raw=('WeaponItem Item < uid='+UID+' >\r\n{\r\n'
             ' myWeapon < uid='+'C'*32+' > : WeaponBase\r\n {\r\n'
             '  myDamageMax 122.559998\r\n  myReloadTimeMS 1740\r\n }\r\n}\r\n').encode()
        old=native_definitions(raw,include_data=True)
        self.assertEqual(1,len(old['resources']))
        new=native_definitions(raw,include_data=True,include_objects=True)
        item,weapon=new['resources']
        self.assertEqual(('Weapon',None,'C'*32,'WeaponBase'),
            tuple(weapon[k] for k in ('resource_type','internal_name','resource_uid','inheritance_name')))
        self.assertEqual([],item['properties'])
        self.assertEqual(['122.559998','1740'],[p['raw_value'] for p in weapon['properties']])
        self.assertEqual('native_inline_definition',new['links'][0]['kind'])
        self.assertEqual((0,'myWeapon','C'*32),tuple(new['links'][0][k] for k in ('source_index','field','target_uid')))
        loc=weapon['location']
        self.assertEqual(weapon['definition_sha256'],sha256(raw[loc['byte_start']:loc['byte_end']]))
        self.assertEqual(UID,weapon['parents'][0]['resource_uid'])

    def test_base_weapon_uid_requires_weapon_item_schema_context(self):
        raw=('WeaponItem Item < uid='+UID+' >\n{\n myBaseWeapon '+'C'*32+'\n myUnknownUID '+'D'*32+'\n}\n').encode()
        self.assertEqual([],native_definitions(raw,include_data=True)['links'])
        data=native_definitions(raw,include_data=True,include_objects=True)
        self.assertEqual([('myBaseWeapon','C'*32,'native_base_weapon_reference')],
            [(r['field'],r['target_uid'],r['kind']) for r in data['links']])
        self.assertEqual([],native_definitions(raw.replace(b'WeaponItem',b'Talent'),include_data=True,include_objects=True)['links'])

    def test_generation_attributes_empty_lists_and_curve_symbols_keep_raw_context(self):
        raw=('ItemGenerationConfig C\n{\n myTalentSlots\n {\n }\n myAttributeSlots\n {\n'
             '  ItemAttributeSlot Core\n  {\n   myPresetAttribute '+'C'*32+'\n   myPresetPercentage -1.0\n'
             '   myRangeMin = Curve\n  }\n }\n myLabel ""\n}\n').encode()
        out=native_definitions(raw,include_data=True,include_objects=True)
        self.assertEqual(['native_generation_attribute_reference','native_symbol_reference'],[e['kind'] for e in out['links']])
        row=out['resources'][0]
        self.assertIsNone(row['resource_uid'])
        self.assertEqual(['myTalentSlots'],[r['field'] for r in row['empty_blocks']])
        self.assertIn(('myLabel','""'),{(p['field'],p['raw_value']) for p in row['properties']})
        self.assertEqual('-1.0',next(p['raw_value'] for p in row['properties'] if p['field']=='myPresetPercentage'))
        self.assertNotIn('empty_blocks',native_definitions(raw,include_data=True)['resources'][0] if native_definitions(raw,include_data=True)['resources'] else {})

    def test_top_level_uid_alias_is_not_a_reference_slot_or_copied_definition(self):
        raw=('AttributeListContainer Core < uid='+UID+' > = Base '+'C'*32+'\n'
             'ItemGenerationConfig Config\n{\n AttributeListContainer Slot < uid='+'D'*32+' > = Core '+UID+'\n}\n').encode()
        data=native_definitions(raw,include_data=True,include_objects=True)
        self.assertEqual(2,len(data['resources']))
        alias=data['resources'][0]
        self.assertEqual(('native_alias',UID),tuple(alias[k] for k in ('definition_form','resource_uid')))
        self.assertEqual(['native_alias_reference','native_uid_reference'],[e['kind'] for e in data['links']])
        self.assertIsNone(data['links'][0]['reference_uid'])
        self.assertEqual('D'*32,data['links'][1]['reference_uid'])
        self.assertNotIn('D'*32,{r['resource_uid'] for r in data['resources']})

    def test_zero_uid_curve_is_a_symbol_reference_with_original_literal(self):
        raw=('AttributeListContainer Core < uid='+UID+' >\n{\n myRangeMax = Curve '+'0'*32+'\n}\n').encode()
        new=native_definitions(raw,include_data=True,include_objects=True)
        self.assertEqual(1,len(new['links']))
        self.assertEqual(('native_symbol_reference','Curve',None),tuple(new['links'][0][k] for k in ('kind','target_name','target_uid')))
        self.assertEqual('= Curve '+'0'*32,new['resources'][0]['properties'][0]['raw_value'])
        old=native_definitions(raw,include_data=True)
        self.assertEqual('0'*32,old['links'][0]['target_uid'])

    def test_definition_data_keeps_scalar_parameters_and_unquoted_includes_opt_in(self):
        raw=('include rogue/skillscript/example.mskillscriptjuice\r\r\n'
             'Talent Name < uid='+UID+' >\r\r\n{\r\r\n myIsTalentPerk TRUE\r\r\n'
             ' mySkillScript < uid='+'C'*32+' > = Script '+'D'*32+'\r\r\n'
             ' myVariables\r\r\n {\r\r\n  string damageBuff 11\r\r\n  string empty ""\r\r\n }\r\r\n'
             ' TalentOverride PvP\r\r\n {\r\r\n  myOverrideType PvP\r\r\n'
             '  myDuration 1.50\r\r\n }\r\r\n}\r\r\n').encode()
        old=native_definitions(raw,include_formulas=True)
        self.assertEqual([],old['includes'])
        self.assertEqual(['1.50'],[p['raw_value'] for p in old['resources'][0]['properties']])
        new=native_definitions(raw,include_formulas=True,include_data=True)
        self.assertEqual('rogue/skillscript/example.mskillscriptjuice',new['includes'][0]['path'])
        props=new['resources'][0]['properties']
        self.assertEqual(['TRUE','11','""','PvP','1.50'],[p['raw_value'] for p in props])
        self.assertEqual('string',props[1]['value_type'])
        self.assertEqual('myVariables',props[1]['context'][-1]['resource_type'])
        self.assertEqual('PvP',props[-1]['context'][-1]['internal_name'])
        self.assertEqual(new['links'],old['links'])
        for prop in props:
            loc=prop['location'];literal=raw[loc['byte_start']:loc['byte_end']].decode().strip()
            self.assertEqual((prop.get('value_type','')+' '+prop['field']+' '+prop['raw_value']).strip(),literal)

    def test_declared_inheritance_is_preserved_without_inventing_uid_edge(self):
        raw=('include ./confuse.mstatuseffect\nStatusEffect Confuse_ShieldBreak < uid='+UID+' > : Confuse\n'
             '{\n myIgnoresDiminishingReturns TRUE\n}\n').encode()
        data=native_definitions(raw,include_data=True)
        self.assertEqual('Confuse',data['resources'][0]['inheritance_name'])
        self.assertEqual('./confuse.mstatuseffect',data['includes'][0]['path'])
        self.assertEqual([],data['links'])
        self.assertNotIn('inheritance_name',native_definitions(raw)['resources'][0])

    def test_explicit_uid_assignment_is_distinct_from_reference_slot_uid(self):
        raw=('Talent Name < uid='+UID+' >\n{\n myLinkedAction = "Increase Handling" '+'C'*32+'\n}\n').encode()
        self.assertEqual([],native_definitions(raw)['links'])
        edge=native_definitions(raw,include_data=True)['links'][0]
        self.assertEqual(('C'*32,None,'"Increase Handling"','native_uid_assignment_reference'),
            tuple(edge[k] for k in ('target_uid','reference_uid','target_name','kind')))
        self.assertFalse(edge['entity_mapping_confirmed'])

    def test_status_attribute_edges_require_known_schema_field_and_owner_type(self):
        body='\n{\n myResistanceAttributeUID '+'C'*32+'\n myActionBlocksImmunityAttributeUID '+'D'*32+'\n myUnknownUID '+'E'*32+'\n}\n'
        raw=('StatusEffect Burn < uid='+UID+' >'+body).encode()
        self.assertEqual([],native_definitions(raw)['links'])
        self.assertEqual({'C'*32,'D'*32},{r['target_uid'] for r in native_definitions(raw,include_data=True)['links']})
        self.assertEqual([],native_definitions(raw.replace(b'StatusEffect',b'Talent'),include_data=True)['links'])

    def test_skill_tags_keep_quoted_list_labels_without_becoming_uid_links(self):
        raw=('WeaponModifierItem Mod < uid='+UID+' >\n{\n myTags\n {\n'
             '  ItemTag "New ItemTag (0)" Live_SkillVariant\n  ItemModTag SkillModTag AssaultDrone\n }\n}\n').encode()
        data=native_definitions(raw,include_data=True)
        self.assertEqual([],data['links'])
        tags=data['resources'][0]['properties']
        self.assertEqual(['ItemTag','ItemModTag'],[p['value_type'] for p in tags])
        self.assertEqual('"New ItemTag (0)"',tags[0]['field'])
        self.assertEqual(['Live_SkillVariant','AssaultDrone'],[p['raw_value'] for p in tags])

    def test_formulas_are_opt_in_and_keep_raw_quotes_conditions_and_scope(self):
        raw=('AttributeDefinition Formula < uid='+UID+' >\n{\n myOriginalFormula "Max(0, Bonus + 1)"\n'
             ' mySpecializations\n {\n  Specialization PvP\n  {\n   myCondition Game.IsPvPOverrideActive\n'
             '   myFormula 5.75\n  }\n }\n}\n').encode()
        self.assertEqual([],native_definitions(raw)['resources'][0]['properties'])
        row=native_definitions(raw,include_formulas=True)['resources'][0]
        self.assertEqual(['"Max(0, Bonus + 1)"','Game.IsPvPOverrideActive','5.75'],
                         [p['raw_value'] for p in row['properties']])
        self.assertEqual('PvP',row['properties'][2]['context'][-1]['internal_name'])
        for p in row['properties']:
            span=raw[p['location']['byte_start']:p['location']['byte_end']].decode().strip()
            self.assertEqual(p['field']+' '+p['raw_value'],span)

    def test_definition_scopes_keep_named_groups_and_exact_block_bytes(self):
        raw=native_bytes()
        row=native_definitions(raw)['resources'][0]
        self.assertEqual('D',row['parents'][0]['internal_name'])
        self.assertEqual(UID,row['resource_uid'])
        self.assertEqual(GUID,row['fields'][0]['guid'])
        self.assertEqual(row['definition_sha256'],sha256(raw[row['location']['byte_start']:row['location']['byte_end']]))

    def test_nested_uid_links_and_pvp_values_keep_separate_contexts(self):
        raw=('GearSet Test < uid='+UID+' >\n{\n myValue 0.15\n GearSetEffectOverride PvPOverride\n {\n'
             '  myValue 0.05\n }\n ApplyAttributeBonus Action < uid='+'C'*32+' >\n {\n'
             '  myAttributeUID '+'D'*32+'\n  myHash '+'E'*32+'\n  myDuration 6.0\n }\n'
             ' myTalent < uid='+'F'*32+' > = TalentName '+'1'*32+'\n}\n').encode()
        result=native_definitions(raw)
        self.assertEqual(2,len(result['resources']))
        root,child=result['resources']
        self.assertEqual(['0.15','0.05'],[p['raw_value'] for p in root['properties']])
        self.assertEqual('PvPOverride',root['properties'][1]['context'][-1]['internal_name'])
        self.assertEqual(UID,child['parents'][0]['resource_uid'])
        self.assertEqual({'D'*32,'1'*32},{r['target_uid'] for r in result['links']})
        self.assertTrue(all(r['entity_mapping_confirmed'] is False for r in result['links']))

    def test_literal_empty_controls_and_escaped_quotes_are_preserved(self):
        value='Line\r\n{0}, "quoted"\t\x01\\end'
        raw=('Talent Name < uid='+UID+' >\n{\n myUIName '+json.dumps(value)+'\n myLore ""\n}\n').encode()
        fields=native_definitions(raw)['resources'][0]['fields']
        self.assertEqual([value,''],[r['text'] for r in fields])
        encoded=json.dumps(json.dumps(value))[1:-1]
        self.assertEqual(value,metadata_literal_value(encoded))
        self.assertEqual(value,metadata_literal_value(json.dumps("'"+value+"'")[1:-1]))
        self.assertEqual('',metadata_literal_value("''"))
        self.assertEqual('',metadata_literal_value(r'\"\"'))
        for unsupported in ('unquoted',"'"):
            with self.assertRaisesRegex(TextError,'UNSUPPORTED_METADATA_LITERAL'): metadata_literal_value(unsupported)

    def test_unbalanced_or_unsupported_definition_blocks_fail_explicitly(self):
        for raw in (b'{\n}',b'}',b'Name\n{'):
            with self.assertRaises(TextError): native_definitions(raw)
        raw=('Talent Name < uid='+UID+' >\n{\n myUIName "bad\\escape"\n}\n').encode()
        self.assertEqual('UNSUPPORTED_NATIVE_LITERAL',native_definitions(raw)['issues'][0]['code'])

    def test_nested_owner_guid_field_and_exact_byte_spans(self):
        raw=native_bytes()
        data=native_references(raw)
        self.assertEqual([],data['issues'])
        row=data['references'][0];loc=row['location']
        self.assertEqual((GUID,UID,'AttributeDefinition','Name','myUIName'),
                         tuple(row[k] for k in ('guid','resource_uid','resource_type','internal_name','field')))
        self.assertEqual(GUID.encode(),raw[loc['guid_byte_start']:loc['guid_byte_end']])
        self.assertEqual(row['raw_field_sha256'],sha256(raw[loc['byte_start']:loc['byte_end']]))
        self.assertFalse(row['enabled']);self.assertFalse(row['entity_mapping_confirmed'])
        self.assertIn('{0}',row['embedded_text_literal'])

    def test_repeated_guid_under_different_uid_keeps_both(self):
        result=native_references(native_bytes()+native_bytes(uid='C'*32))
        self.assertEqual(2,len(result['references']))
        self.assertEqual({UID,'C'*32},{r['resource_uid'] for r in result['references']})

    def test_unsupported_guid_location_and_invalid_encoding_are_explicit(self):
        result=native_references(b'guid = #'+GUID.encode())
        self.assertEqual('UNSUPPORTED_NATIVE_GUID_FIELD',result['issues'][0]['code'])
        with self.assertRaises(UnicodeError): native_references(b'\xff')

    def test_closing_block_does_not_reuse_a_stale_owner(self):
        result=native_references(native_bytes()+b'myUIName "guid = #'+GUID.encode()+b', text = \\"wrong\\""')
        self.assertEqual(1,len(result['references']))
        self.assertEqual(1,len(result['issues']))

    def test_dictionary_preserves_original_alias_output_and_il_pointer(self):
        rows=translation_dictionary(dictionary_metadata([('Alias, "quoted"\r\n{0}','App Key'),('','')]))
        self.assertEqual(['Alias, "quoted"\r\n{0}',''],[r['input_name'] for r in rows])
        self.assertEqual('/types/0/methods/0/il/1',rows[0]['evidence_pointer'])
        self.assertEqual('App Key',rows[0]['output_internal_name'])

    def test_dictionary_rejects_unproved_instruction_shape_and_duplicate_inputs(self):
        bad=dictionary_metadata([('A','Key')]);bad['types'][0]['methods'][0]['il'][2]['opcode']='call'
        with self.assertRaisesRegex(TextError,'UNSUPPORTED_TRANSLATION_ENTRY'): translation_dictionary(bad)
        with self.assertRaisesRegex(TextError,'DUPLICATE_TRANSLATION_INPUT'):
            translation_dictionary(dictionary_metadata([('A','Key'),('A','Different')]))


class EvidenceQueryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=os.environ.get('TD2_TEXT_LIBRARY_TEST_TMP'))
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.index=dict(schema_version=1,sources=[])
        self.save()

    def write(self,name,value):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode('utf-8'))
        return dict(file=name,sha256=sha256(path.read_bytes()))

    def save(self): self.write('index.json',self.index)
    def query(self,**kwargs): return TextLibrary(self.root,'index.json').query(**kwargs)

    def menu(self,name='english',value='Name {0}',locale=None,language=None,key=GUID):
        ref=self.write(name+'.locpack',fixtures.menu_bytes([[key,'0',value,'']]))
        provenance=self.write(name+'-provenance.json',dict(immutable_input_copies=[dict(original_path='cache/'+name,sha256=ref['sha256'])]))
        source=dict(id=name,format='menus_csv',**ref,evidence=dict(provenance=provenance))
        if locale: source['locale']=dict(namespace='hunter/localization/packages/'+locale+'/menus.locpack',
                                        culture=locale,language=language,language_evidence='recorded package identifier')
        self.index['sources'].append(source);self.save()

    def native(self,files=None):
        records=[];specs=[];issues=[]
        for i,(name,raw) in enumerate(files or [('native.txt',native_bytes())]):
            spec=self.write(name,raw);specs.append(spec)
            parsed=native_references(raw)
            issues.extend(dict(r,file=name) for r in parsed['issues'])
            for row in parsed['references']:
                records.append(dict(row,file_index=i,reference_id=identity([name,spec['sha256'],row['location']['byte_start'],row['field'],row['guid']])))
        ref=self.write('native.json',dict(schema_version=1,parser_rule='fruit_localization_guid_fields@1',
                                         files=specs,references=records,issues=issues))
        self.index['native_references']=dict(ref,target_sources=[s['id'] for s in self.index['sources'] if s['format']=='menus_csv'])
        self.save()
        return records

    def definitions(self,files=None,include_formulas=False,include_data=False,include_objects=False):
        documents=[]
        for name,raw in files or [('native.txt',native_bytes())]:
            documents.append(dict(self.write(name,raw),parsed=native_definitions(raw,include_formulas=include_formulas,
                include_data=include_data,include_objects=include_objects)))
        self.index['native_definitions']=self.write('definitions.json',dict(schema_version=1,
            parser_rule='fruit_definition_scopes@4' if include_objects else 'fruit_definition_scopes@3' if include_data else 'fruit_definition_scopes@2' if include_formulas else 'fruit_definition_scopes@1',schema_evidence=[],files=documents))
        self.save()

    def test_uidless_config_does_not_match_unrelated_strings_or_gain_native_uid(self):
        self.menu()
        raw=b'ItemGenerationConfig Base\n{\n myMin 0.0\n}\nItemGenerationConfig Child : Base\n{\n myMax 1.0\n}\n'
        self.definitions([('config.txt',raw)],include_data=True,include_objects=True)
        out=self.query(resource='Child')
        self.assertEqual((0,1,0,1),(out['total'],out['native_resource_total'],out['native_uid_link_total'],out['native_relation_total']))
        row=out['native_resources'][0]
        self.assertIsNone(row['resource_uid']);self.assertEqual('no_native_uid',row['uid_status'])
        self.assertEqual('saved_definition',row['inheritance_status'])
        edge=out['native_relations'][0]
        self.assertIsNone(edge['target_uid']);self.assertEqual(1,len(edge['target_resource_ids']))
        self.assertEqual('declared_symbol_in_same_file',edge['resolution'])
        self.assertEqual(2,self.query(resource='Child',related_depth=1)['native_resource_total'])

    def test_generation_binding_requires_shared_config_uid_and_source_index(self):
        self.menu()
        item=('WeaponItem Item < uid='+UID+' >\n{\n myItemGenerationConfig < uid='+'C'*32+' > = Link '+'D'*32+'\n}\n').encode()
        config=('ItemGenerationConfig Config\n{\n myItemGenerationConfigLink < uid='+'E'*32+' > = Link '+'D'*32+'\n'
                ' myTalentSlots\n {\n  QualityTalentSlots Orange\n  {\n   ItemTalentSlot Preset\n   {\n'
                '    myPresetTalent < uid='+'1'*32+' > = Talent '+'F'*32+'\n   }\n  }\n'
                '  QualityTalentSlots Prototype\n  {\n   ItemTalentSlot Preset\n   {\n'
                '    myPresetTalent < uid='+'2'*32+' > = Talent '+'F'*32+'\n   }\n  }\n }\n}\n').encode()
        talent=('Talent Talent < uid='+'F'*32+' >\n{\n myValue 0.125\n}\n').encode()
        self.definitions([('item.txt',item),('config.txt',config),('foreign.txt',config),('talent.txt',talent)],
                         include_data=True,include_objects=True)
        data=json.loads((self.root/'definitions.json').read_bytes())
        for spec in data['files']:
            spec.update(resource_name='hunter/'+spec['file'],export_role='raw',source_container_sha256='a'*64)
        data['files'][2]['source_container_sha256']='b'*64
        self.index['native_definitions']=self.write('definitions.json',data);self.save()
        out=self.query(resource=UID)
        self.assertEqual([],out['issues'])
        presets=[e for e in out['native_uid_links'] if e['kind']=='native_equipment_preset_talent']
        self.assertEqual(2,len(presets))
        self.assertEqual(2,len({e['link_id'] for e in presets}))
        self.assertTrue(all(e['binding_evidence']['resource_file']=='config.txt' for e in presets))
        self.assertEqual({'Orange','Prototype'},{c['internal_name'] for e in presets for c in e['configuration_context']
            if c['resource_type']=='QualityTalentSlots'})
        self.assertTrue(all(e['field']=='myItemGenerationConfig' and e['target_field']=='myPresetTalent' for e in presets))
        self.assertTrue(all(e['shared_config_link_uid']=='D'*32 for e in presets))
        related=self.query(resource=UID,related_depth=1)
        self.assertEqual({'WeaponItem','ItemGenerationConfig','Talent'},
                         {r['resource_type'] for r in related['native_resources']})
        reverse=self.query(resource='F'*32)
        self.assertEqual({UID},{e['source_uid'] for e in reverse['native_uid_links'] if e['kind']=='native_equipment_preset_talent'})
        self.assertTrue(all(not e['entity_mapping_confirmed'] for e in presets))

    def test_uidless_duplicate_symbols_are_reported_without_overwriting(self):
        raw=b'ItemGenerationConfig C\n{\n myMin 0\n}\nItemGenerationConfig C\n{\n myMin 1\n}\n'
        self.definitions([('config.txt',raw)],include_data=True,include_objects=True)
        out=self.query(resource='C')
        self.assertEqual(2,out['native_resource_total'])
        self.assertEqual(['NATIVE_SYMBOL_DEFINITION_CONFLICT'],[i['code'] for i in out['issues']])

    def test_generation_conflicts_are_distinct_from_separate_data_versions(self):
        item=('WeaponItem Item < uid='+UID+' >\n{\n myItemGenerationConfig < uid='+'C'*32+' > = Link '+'D'*32+'\n}\n').encode()
        config=('ItemGenerationConfig C\n{\n myItemGenerationConfigLink < uid='+'E'*32+' > = Link '+'D'*32+'\n myMin 1.0\n}\n').encode()
        for other_version in (23,22):
            self.definitions([('item.txt',item),('c1.txt',config),('c2.txt',config.replace(b'1.0',b'2.0'))],include_data=True,include_objects=True)
            data=json.loads((self.root/'definitions.json').read_bytes())
            for spec in data['files']:spec.update(resource_name='hunter/'+spec['file'],export_role='raw',source_container_sha256='a'*64)
            for spec,version in zip(data['files'][1:],(23,other_version)):spec['generation_context']=dict(code_version=1,data_version=version)
            self.index['native_definitions']=self.write('definitions.json',data);self.save()
            out=self.query(resource=UID)
            bindings=[e for e in out['native_relations'] if e['kind']=='native_generation_binding']
            self.assertEqual(2,len(bindings))
            self.assertEqual(['NATIVE_GENERATION_CONFIG_CONFLICT'] if other_version==23 else [],[i['code'] for i in out['issues']])
            self.assertEqual({'conflicting_saved_generation_context'} if other_version==23 else {'shared_native_config_link_uid'},
                             {e['binding_status'] for e in bindings})

    def test_preset_talent_does_not_resolve_to_same_uid_of_another_native_type(self):
        raw=('ItemGenerationConfig C\n{\n myPresetTalent < uid='+'C'*32+' > = Named '+'D'*32+'\n}\n'
             'WeaponItem Named < uid='+'D'*32+' >\n{\n}\n').encode()
        self.definitions([('config.txt',raw)],include_data=True,include_objects=True)
        out=self.query(resource='C',related_depth=1)
        self.assertEqual(1,out['native_resource_total'])
        edge=out['native_uid_links'][0]
        self.assertEqual(('Talent','saved_uid_has_different_type',[]),
                         tuple(edge[k] for k in ('target_type','target_status','target_resource_ids')))

    def test_related_queries_require_resource_and_bounded_depth(self):
        for kwargs in (dict(related_depth=1),dict(resource=UID,related_depth=-1),dict(resource=UID,related_depth=6)):
            with self.subTest(kwargs=kwargs),self.assertRaisesRegex(TextError,'INVALID_RELATED_DEPTH'):
                self.query(**kwargs)

    def test_mixed_definition_rules_keep_old_ids_and_validate_new_parameters(self):
        self.menu();self.definitions(include_formulas=True)
        old=self.query(resource=UID)
        data=json.loads((self.root/'definitions.json').read_bytes())
        data['files'][0]['parser_rule']=data['parser_rule']
        data['parser_rule']='fruit_definition_scopes@3'
        raw=('StatusEffect Burn < uid='+'C'*32+' >\n{\n myDuration Burn_Duration_Final\n'
             ' myMinimumDuration 0.5\n myDurationForNPCs NPC_Burn_Duration_Base\n}\n').encode()
        data['files'].append(dict(self.write('burn.mstatuseffect',raw),parser_rule='fruit_definition_scopes@3',
                                 resource_name='rogue/game system data/juice/statuseffects/burn.mstatuseffect',export_role='raw',
                                 parsed=native_definitions(raw,include_formulas=True,include_data=True)))
        self.index['native_definitions']=self.write('definitions.json',data);self.save()
        current=self.query(resource=UID)
        self.assertEqual(old['results'],current['results'])
        self.assertEqual(old['native_resources'][0]['resource_id'],current['native_resources'][0]['resource_id'])
        self.assertEqual('fruit_definition_scopes@2',current['native_resources'][0]['parser_rule'])
        new=self.query(resource='C'*32)
        self.assertEqual([],new['issues'])
        self.assertEqual(['Burn_Duration_Final','0.5','NPC_Burn_Duration_Base'],
                         [p['raw_value'] for p in new['native_resources'][0]['properties']])
        self.assertFalse(new['native_resources'][0]['entity_mapping_confirmed'])
        self.assertEqual(new['native_resources'],self.query(resource=data['files'][1]['resource_name'])['native_resources'])
        data['files'][1]['parsed']['resources'][0]['properties'][1]['raw_value']='5'
        self.index['native_definitions']=self.write('definitions.json',data);self.save()
        self.assertEqual('NATIVE_DEFINITION_EVIDENCE_CONFLICT',self.query()['issues'][0]['code'])

    def test_pinned_export_receipt_change_is_reported_by_both_native_components(self):
        self.menu();self.native();self.definitions(include_data=True)
        ledger=self.write('export-receipt.json',dict(status='SUCCEEDED'))
        for component in ('native_references','native_definitions'):
            spec=self.index[component];data=json.loads((self.root/spec['file']).read_bytes())
            data['files'][0]['ledger']=dict(ledger,pointer='/exports/0')
            spec.update(self.write(spec['file'],data))
        self.save();self.assertEqual([],self.query()['issues'])
        self.write(ledger['file'],dict(status='changed'))
        out=self.query()
        self.assertEqual(1,out['total'])
        self.assertEqual({'native_references','native_definitions'},{i['component'] for i in out['issues']})
        self.assertTrue(all(i['code']=='INPUT_HASH_MISMATCH' for i in out['issues']))

    def test_inheritance_resolves_only_declared_include_in_same_source_index(self):
        child=('include "rogue/base.mtalent"\nTalent Perfect < uid='+UID+' > : Base\n\n{\n myValue 0.8\n}\n').encode()
        base=('Talent Base < uid='+'C'*32+' >\n{\n myValue 0.5\n}\n').encode()
        other=base.replace(('C'*32).encode(),('D'*32).encode())
        for include,index_hash,expected in [(True,'1'*64,1),(False,'1'*64,0),(True,'2'*64,0)]:
            with self.subTest(include=include,index=index_hash):
                self.definitions([('child.txt',child if include else child.split(b'\n',1)[1]),('base.txt',base),('other.txt',other)],
                                 include_formulas=True,include_data=True)
                data=json.loads((self.root/'definitions.json').read_bytes())
                for spec,name in zip(data['files'],['child','base','other']):
                    spec.update(resource_name='rogue/'+name+'.mtalent',export_role='raw',source_container_sha256='1'*64)
                data['files'][1]['source_container_sha256']=index_hash
                self.index['native_definitions']=self.write('definitions.json',data);self.save()
                out=self.query(resource=UID)
                self.assertEqual([],out['issues'])
                self.assertEqual(expected,out['native_uid_link_total'])
                if expected:
                    edge=out['native_uid_links'][0]
                    self.assertEqual(('C'*32,'declared_native_inheritance'),(edge['target_uid'],edge['kind']))
                    loc=edge['location'];self.assertEqual(edge['raw_field_sha256'],sha256(child[loc['byte_start']:loc['byte_end']]))
                    self.assertFalse(edge['entity_mapping_confirmed'])
                else:self.assertEqual('definition_not_saved',out['native_resources'][0]['inheritance_status'])

    def test_formula_adapter_preserves_resource_and_string_identity(self):
        self.menu()
        raw=native_bytes().replace(b'\t\tmyUIName',b'\t\tmyOriginalFormula 25\r\r\n\t\tmyUIName')
        self.definitions([('native.txt',raw)])
        old=self.query(resource=UID)
        self.definitions([('native.txt',raw)],include_formulas=True)
        new=self.query(resource=UID)
        self.assertEqual(old['results'],new['results'])
        self.assertEqual(old['native_resources'][0]['resource_id'],new['native_resources'][0]['resource_id'])
        self.assertEqual('25',new['native_resources'][0]['properties'][0]['raw_value'])
        self.assertEqual('fruit_definition_scopes@2',new['native_resources'][0]['parser_rule'])
        data=json.loads((self.root/'definitions.json').read_bytes())
        data['files'][0]['parsed']['resources'][0]['properties'][0]['raw_value']='999'
        self.index['native_definitions']=self.write('definitions.json',data);self.save()
        self.assertEqual('NATIVE_DEFINITION_EVIDENCE_CONFLICT',self.query()['issues'][0]['code'])

    def literals(self):
        spec=self.write('native.txt',native_bytes())
        rows=native_references((self.root/'native.txt').read_bytes())['references']
        self.index['sources'].append(dict(id='literals',format='native_literals',**self.write('literals.json',
            dict(schema_version=1,parser_rule='fruit_metadata_literals@1',files=[dict(spec,records=rows)]))))
        self.save()

    def test_resource_query_resolves_fields_without_changing_menu_identity(self):
        self.menu();before=self.query()['results'][0]
        self.native();self.definitions()
        out=self.query(resource=UID)
        self.assertEqual((1,1,1),(out['total'],out['native_reference_total'],out['native_resource_total']))
        self.assertEqual(before['observation_id'],out['results'][0]['observation_id'])
        row=out['native_resources'][0]
        self.assertEqual('Name {0}',row['fields'][0]['string_observations'][0]['text'])
        self.assertFalse(row['entity_mapping_confirmed'])
        self.assertEqual(1,self.query(resource='D')['native_resource_total'])
        self.assertEqual((0,0),(self.query(resource='unknown')['total'],self.query(resource='unknown')['native_resource_total']))

    def test_guid_without_saved_menu_value_still_returns_its_definition(self):
        self.menu();self.native([('native.txt',native_bytes(guid='C'*32))])
        self.definitions([('native.txt',native_bytes(guid='C'*32))])
        out=self.query(key='C'*32)
        self.assertEqual((0,1,1),(out['total'],out['native_reference_total'],out['native_resource_total']))

    def test_same_uid_different_definitions_are_retained_and_reported(self):
        self.menu()
        self.definitions([('one.txt',native_bytes()),('two.txt',native_bytes().replace(b' Name ',b' Other '))])
        out=self.query(resource=UID)
        self.assertEqual(2,out['native_resource_total'])
        self.assertEqual('NATIVE_UID_DEFINITION_CONFLICT',out['issues'][0]['code'])
        self.assertEqual({'Name','Other'},{r['internal_name'] for r in out['native_resources']})

    def test_uid_link_target_resolution_is_exact_and_does_not_bind_text_entities(self):
        self.menu()
        link=('Talent TalentName < uid='+'C'*32+' >\n{\n myRule < uid='+'D'*32+' > = Name '+UID+'\n}\n').encode()
        self.definitions([('one.txt',native_bytes()),('two.txt',link)])
        out=self.query(resource='C'*32)
        self.assertEqual((0,1),(out['total'],out['native_uid_link_total']))
        edge=out['native_uid_links'][0]
        self.assertEqual('saved_definition',edge['target_status'])
        self.assertEqual(1,len(edge['target_resource_ids']))
        self.assertFalse(edge['entity_mapping_confirmed'])
        self.assertEqual(1,self.query(resource=UID)['native_uid_link_total'])

    def test_literals_remain_distinct_from_menu_values_with_same_guid(self):
        self.menu(value='Menu value');self.literals();self.definitions()
        out=self.query(key=GUID)
        self.assertEqual({'Menu value','Name {0}'},{r['text'] for r in out['results']})
        row=next(r for r in out['results'] if r['value_kind']=='native_metadata_literal')
        self.assertIsNone(row['context']['culture']);self.assertIsNone(row['context']['language'])
        self.assertFalse(row['relations'][0]['menu_value_recovered'])
        self.assertEqual('native.txt',row['source_location']['file'])

    def test_forged_or_duplicate_literal_evidence_fails_atomically(self):
        self.literals()
        source=self.index['sources'][0];original=json.loads((self.root/'literals.json').read_bytes())
        for kind,code in [('changed','NATIVE_LITERAL_EVIDENCE_CONFLICT'),('duplicate','DUPLICATE_NATIVE_LITERAL')]:
            data=json.loads(json.dumps(original))
            if kind=='changed': data['files'][0]['records'][0]['field']='myLore'
            else: data['files'][0]['records'].append(data['files'][0]['records'][0])
            source.update(self.write('literals.json',data));self.save()
            out=self.query();self.assertEqual(0,out['total']);self.assertEqual(code,out['issues'][0]['code'])

    def test_definition_missing_hash_forgery_unsafe_and_duplicate_fail_without_losing_strings(self):
        self.menu();self.definitions()
        original=json.loads((self.root/'definitions.json').read_bytes())
        for kind,code in [('missing','INPUT_MISSING'),('hash','INPUT_HASH_MISMATCH'),
                          ('unsafe','UNSAFE_PATH'),('forged','NATIVE_DEFINITION_EVIDENCE_CONFLICT'),
                          ('duplicate','DUPLICATE_NATIVE_DEFINITION_FILE')]:
            data=json.loads(json.dumps(original))
            if kind=='missing': data['files'][0]['file']='absent.txt'
            if kind=='hash': data['files'][0]['sha256']='0'*64
            if kind=='unsafe': data['files'][0]['file']='../outside'
            if kind=='forged': data['files'][0]['parsed']['resources'][0]['internal_name']='Fake'
            if kind=='duplicate': data['files'].append(data['files'][0])
            self.index['native_definitions']=self.write('definitions.json',data);self.save()
            out=self.query();self.assertEqual(1,out['total']);self.assertEqual(code,out['issues'][0]['code'])

    def dictionary(self):
        evidence=dict(packages=self.write('packages.json',fixtures.package_metadata()))
        attributes=[dict(english_aliases_from_app_dictionary=[dict(input_name='Old',output_internal_name='K',
            source_locations=[dict(platform=p) for p in ('apk','windows')])])]
        evidence['attributes']=self.write('attributes.json',attributes)
        records=[]
        for platform in ('apk','windows'):
            md=dictionary_metadata([('Old','K'),('New','K2')]);evidence[platform]=self.write(platform+'.json',md)
            records.append(dict(platform=platform,**translation_dictionary(md)[1]))
        source=dict(id='dictionary',format='app_dictionary',**self.write('dictionary.json',
            dict(schema_version=1,parser_rule='app_translate_dictionary_il@1',records=records)),evidence=evidence)
        self.index['sources'].append(source);self.save();return source

    def test_relation_addition_keeps_original_menu_identity(self):
        self.menu();before=self.query()['results'][0]
        self.native();after=self.query()['results'][0]
        for key in ('observation_id','logical_id','source_snapshot_id','text','location'): self.assertEqual(before[key],after[key])
        relation=after['relations'][0]
        self.assertEqual(('myUIName',UID,'native.txt'),tuple(relation[k] for k in ('field','resource_uid','resource_file')))
        self.assertFalse(relation['entity_mapping_confirmed'])

    def test_multiple_sources_for_same_guid_are_not_merged(self):
        self.menu();self.native([('one.txt',native_bytes()),('two.txt',native_bytes(uid='C'*32))])
        out=self.query(key=GUID)
        self.assertEqual(2,out['native_reference_total'])
        self.assertEqual(2,len(out['results'][0]['relations']))
        self.assertEqual(2,len({r['reference_id'] for r in out['native_references']}))

    def test_missing_guid_returns_references_without_inventing_a_string(self):
        self.menu();self.native([('native.txt',native_bytes(guid='C'*32))])
        out=self.query(key='C'*32)
        self.assertEqual(0,out['total']);self.assertEqual(1,out['native_reference_total'])
        self.assertEqual('guid_absent_from_selected_tables',out['native_references'][0]['match_status'])

    def test_same_file_different_uid_references_are_not_merged_in_string_results(self):
        self.menu();self.native([('native.txt',native_bytes()+native_bytes(uid='C'*32))])
        out=self.query(key=GUID)
        self.assertEqual(2,len(out['results'][0]['relations']))
        self.assertEqual({UID,'C'*32},{r['resource_uid'] for r in out['results'][0]['relations']})

    def test_native_source_hash_change_is_partial_and_does_not_remove_menu(self):
        self.menu();self.native();self.write('native.txt',b'changed')
        out=self.query(key=GUID)
        self.assertEqual(1,out['total']);self.assertEqual('partial',out['coverage'])
        self.assertEqual('INPUT_HASH_MISMATCH',out['issues'][0]['code'])

    def test_native_unsafe_path_duplicate_registration_and_forged_field_fail(self):
        self.menu();self.native()
        data=json.loads((self.root/'native.json').read_bytes())
        original=json.loads(json.dumps(data))
        for kind,code in [('unsafe','UNSAFE_PATH'),('duplicate','DUPLICATE_NATIVE_REFERENCE'),('field','NATIVE_FIELD_EVIDENCE_CONFLICT')]:
            doc=json.loads(json.dumps(original))
            if kind=='unsafe':
                doc['files'][0]['file']='../outside'
                r=doc['references'][0];r['reference_id']=identity(['../outside',doc['files'][0]['sha256'],r['location']['byte_start'],r['field'],r['guid']])
            elif kind=='duplicate': doc['references'].append(doc['references'][0])
            else:
                r=doc['references'][0];r['enabled']=True
            self.index['native_references'].update(self.write('native.json',doc));self.save()
            self.assertEqual(code,self.query()['issues'][0]['code'])

    def test_language_pairs_use_exact_guid_without_changing_culture_or_identity(self):
        self.menu();old=self.query()['results'][0]['observation_id']
        self.menu('other','原文',locale='chinesegav');self.native()
        out=self.query(key=GUID)
        self.assertEqual((2,1,1),(out['total'],out['native_reference_total'],out['native_localization_pair_keys']))
        self.assertEqual(old,out['results'][0]['observation_id'])
        self.assertEqual('chinesegav',out['results'][1]['context']['culture'])
        self.assertIsNone(out['results'][1]['context']['language'])
        self.assertEqual('evidenced_same_guid_in_saved_tables',out['results'][0]['relations'][-1]['status'])

    def test_verified_simplified_priority_retains_other_chinese_sources(self):
        self.menu('simplified','简体原文',locale='simplifiedchinese',language='zh-CN')
        self.menu('english','English')
        self.menu('gav','另一原文',locale='chinesegav')
        self.menu('traditional','繁體原文',locale='traditionalchinese',language='zh-TW')
        self.native()
        out=self.query(key=GUID)
        self.assertEqual(['simplified','english','gav','traditional'],[r['source_id'] for r in out['results']])
        self.assertEqual(4,len({r['observation_id'] for r in out['results']}))
        self.assertEqual('simplified',self.query(key=GUID,limit=1)['results'][0]['source_id'])
        self.assertEqual({'simplified'},{r['source_id'] for r in self.query(key=GUID,language='zh-CN')['results']})
        self.assertEqual({'traditional'},{r['source_id'] for r in self.query(key=GUID,language='zh-TW')['results']})
        gav=self.query(key=GUID,culture='chinesegav')['results'][0]
        self.assertEqual(('另一原文',None),(gav['text'],gav['context']['language']))
        only=self.query(key=GUID,sources=['simplified'])
        self.assertEqual(['simplified'],[r['source_id'] for r in only['native_references'][0]['string_observations']])

    def test_missing_simplified_guid_never_uses_gav_or_traditional(self):
        self.menu('simplified','其他记录',locale='simplifiedchinese',language='zh-CN',key='B'*32)
        self.menu('gav','GAV 原文',locale='chinesegav')
        self.menu('traditional','繁體原文',locale='traditionalchinese',language='zh-TW')
        self.native()
        self.assertEqual(0,self.query(key=GUID,language='zh-CN')['total'])
        self.assertEqual(0,self.query(key=GUID,culture='simplifiedchinese')['total'])
        only=self.query(key=GUID,sources=['simplified'])
        self.assertEqual(0,only['total'])
        self.assertEqual('guid_absent_from_selected_tables',only['native_references'][0]['match_status'])
        self.assertEqual([],only['native_references'][0]['string_observations'])

    def test_failed_simplified_input_is_reported_without_fallback(self):
        self.menu('simplified','简体原文',locale='simplifiedchinese',language='zh-CN')
        self.menu('gav','GAV 原文',locale='chinesegav')
        (self.root/'simplified.locpack').write_bytes(b'changed')
        out=self.query(key=GUID,language='zh-CN')
        self.assertEqual(0,out['total'])
        self.assertEqual('partial',out['coverage'])
        self.assertEqual('INPUT_HASH_MISMATCH',out['issues'][0]['code'])

    def test_preferred_source_registration_keeps_old_observation_ids(self):
        self.menu('english','English');self.menu('gav','原文',locale='chinesegav')
        before={r['source_id']:r for r in self.query(key=GUID)['results']}
        self.menu('simplified','简体原文',locale='simplifiedchinese',language='zh-CN')
        self.index['sources'].insert(0,self.index['sources'].pop());self.save()
        after={r['source_id']:r for r in self.query(key=GUID)['results']}
        for source in before:
            self.assertEqual({k:v for k,v in before[source].items() if k!='relations'},
                             {k:v for k,v in after[source].items() if k!='relations'})
        self.assertEqual(['english'],[r['source_id'] for r in self.query(key=GUID,language='en')['results']])
        self.assertEqual(0,self.query(key=GUID,language='zh')['total'])

    def test_simplified_substring_miss_does_not_use_another_culture(self):
        self.menu('simplified','标准原文',locale='simplifiedchinese',language='zh-CN')
        self.menu('gav','另一名称',locale='chinesegav')
        self.assertEqual(0,self.query(text='另一名称',language='zh-CN')['total'])
        self.assertEqual('gav',self.query(text='另一名称')['results'][0]['source_id'])

    def test_empty_simplified_value_remains_empty_without_fallback(self):
        self.menu('simplified','',locale='simplifiedchinese',language='zh-CN')
        self.menu('gav','非空名称',locale='chinesegav')
        row=self.query(key=GUID,language='zh-CN')['results'][0]
        self.assertEqual(('simplified','','text'),(row['source_id'],row['text'],row['value_state']))

    def test_dictionary_aliases_keep_platforms_and_skip_existing_attribute_aliases(self):
        self.dictionary();out=self.query(key='K2')
        self.assertEqual(2,out['total']);self.assertEqual(0,self.query(key='Old')['total'])
        self.assertEqual({'apk','windows'},{r['context']['platform'] for r in out['results']})
        self.assertTrue(all(r['value_kind']=='dictionary_alias' and r['dictionary_output_key']=='K2' for r in out['results']))
        self.assertTrue(all(r['relations'][0]['official_translation'] is False for r in out['results']))

    def test_dictionary_evidence_change_does_not_silently_rebind_alias(self):
        source=self.dictionary();md=json.loads((self.root/'apk.json').read_bytes())
        md['types'][0]['methods'][0]['il'][7]['operand']='Changed'
        source['evidence']['apk'].update(self.write('apk.json',md));self.save()
        out=self.query()
        self.assertEqual(0,out['total']);self.assertEqual('DICTIONARY_INSTRUCTION_EVIDENCE_CONFLICT',out['issues'][0]['code'])

    def test_query_and_cli_are_read_only_and_repeatable(self):
        self.menu();self.native();self.dictionary();self.definitions();self.literals()
        before={p:sha256(p.read_bytes()) for p in self.root.rglob('*') if p.is_file()}
        library=TextLibrary(self.root,'index.json')
        with patch.object(Path,'write_bytes',side_effect=AssertionError('write')),patch.object(Path,'write_text',side_effect=AssertionError('write')),patch.object(Path,'mkdir',side_effect=AssertionError('mkdir')):
            first=library.query(key=GUID);self.assertEqual(first,library.query(key=GUID))
            stream=io.StringIO()
            with redirect_stdout(stream): code=main(['--root',str(self.root),'--index','index.json','--key',GUID])
            self.assertEqual(0,code);self.assertEqual(1,json.loads(stream.getvalue())['native_reference_total'])
            stream=io.StringIO()
            with redirect_stdout(stream): code=main(['--root',str(self.root),'--index','index.json','--resource',UID])
            self.assertEqual(0,code);self.assertEqual(1,json.loads(stream.getvalue())['native_resource_total'])
            stream=io.StringIO()
            with redirect_stdout(stream):code=main(['--root',str(self.root),'--index','index.json','--resource',UID,'--related-depth','2'])
            self.assertEqual(0,code);self.assertFalse(json.loads(stream.getvalue())['writes_performed'])
        self.assertEqual(before,{p:sha256(p.read_bytes()) for p in self.root.rglob('*') if p.is_file()})


class RealEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library=HistoricalTextLibrary();cls.result=cls.library.query(limit=1)

    def assert_business_bonus_catalog(self):
        names = {'bonus_weapon_damage': ('武器伤害', 'Weapon Damage'),
                 'bonus_protection_from_elites': ('对精英的防御', 'Protection from Elites'),
                 'bonus_skill_efficiency': ('技能效率', 'Skill Efficiency'),
                 'bonus_increased_threat': ('提升威胁度', 'Increased Threat'),
                 'bonus_hazard_protection': ('危害防护', 'Hazard Protection')}
        expected = {(key, lang, value) for key, pair in names.items() for lang, value in zip(('zh', 'en'), pair)}
        actual = {(row['key'], row['context']['language'], row['text']) for row in self.library.loaded['business-bonuses']['records']}
        self.assertEqual(actual, expected)

    def test_all_216320_baseline_observations_and_native_ids_are_preserved(self):
        before=json.loads((self.library.root/'dist/text-library-20261018-002/before.json').read_bytes())
        for source,expected in before['sources'].items():
            rows=[{k:v for k,v in r.items() if k!='relations'} for r in self.library.loaded[source]['records']]
            self.assertEqual(expected,dict(count=len(rows),core_sha256=identity(rows),
                ids_sha256=identity(sorted(r['observation_id'] for r in rows))))
        self.assertTrue(set(before['resource_ids']).issubset({r['resource_id'] for r in self.library.definitions_loaded['resources']}))
        self.assertTrue(set(before['link_ids']).issubset({r['link_id'] for r in self.library.definitions_loaded['links']}))

    def test_real_keeper_preset_uses_native_config_uid_and_keeps_quality_contexts(self):
        uid='B00501356A6B4D4E001AF7AFF1F451F3'
        out=self.library.query(resource=uid,related_depth=1,limit=100)
        presets=[e for e in out['native_relations'] if e['kind']=='native_equipment_preset_talent' and e['source_uid']==uid]
        self.assertEqual(2,len(presets))
        self.assertEqual({'B00501356A6B4F9A001F0F6940DD0643'},{e['target_uid'] for e in presets})
        self.assertEqual({'B00501356A6B4D2E001AC14C5F6AB8D7'},{e['shared_config_link_uid'] for e in presets})
        self.assertEqual({'Orange','Prototype'},{c['internal_name'] for e in presets for c in e['configuration_context']
            if c['resource_type']=='QualityTalentSlots'})
        self.assertTrue(all(e['target_status']=='saved_definition' and not e['entity_mapping_confirmed'] for e in presets))
        self.assertTrue(any(r['resource_type']=='ItemGenerationConfig' and r['resource_uid'] is None for r in out['native_resources']))

    def test_real_ordinary_and_perfect_protector_keep_distinct_uids_values_and_shared_rule(self):
        cases=[('3797E3755DB30A180009C8646400F59A',['0.05','0.15','3.0'],['0.1','0.2','3.0']),
               ('B00501356A6B4F9A001F0F6940DD0643',['0.25','0.35','3.0'],['0.15','0.3','3.0'])]
        identities=[]
        for uid,default,pvp in cases:
            out=self.library.query(resource=uid)
            row=next(r for r in out['native_resources'] if r['resource_uid']==uid)
            identities.append(row['resource_id'])
            values=[p for p in row['properties'] if p['field']=='myValue']
            self.assertEqual(pvp,[p['raw_value'] for p in values if any(c['internal_name']=='PVP' for c in p['context'])])
            self.assertEqual(default,[p['raw_value'] for p in values if not any(c['internal_name']=='PVP' for c in p['context'])])
            self.assertTrue(any(e['field']=='myTalentRules' and e['target_uid']=='3797E3755DB3078500083FDDB87CB036' for e in out['native_uid_links']))
        self.assertEqual(2,len(set(identities)))

    def test_real_deathgrips_named_attribute_keeps_percentile_and_curve_separate(self):
        out=self.library.query(resource='player_gear_gloves_511_named_01_config',limit=100)
        row=out['native_resources'][0]
        self.assertIsNone(row['resource_uid']);self.assertEqual(0,out['total'])
        presets=[e for e in out['native_uid_links'] if e['field']=='myPresetAttribute' and e['target_uid']=='5D4179F15BF55A5200032C69B6DF1572']
        self.assertEqual(2,len(presets))
        for edge in presets:
            props={p['field']:p['raw_value'] for p in row['properties'] if p['context']==edge['context']}
            self.assertEqual(('100.0','TRUE'),(props['myPresetPercentage'],props['myIsNamedAttribute']))
        curve=self.library.query(resource='Percent_1_to_10',limit=100)
        self.assertEqual(1,curve['native_resource_total'])
        self.assertIsNone(curve['native_resources'][0]['resource_uid'])
        self.assertTrue(any(p['field']=='myC' and p['raw_value']=='0.09' for p in curve['native_resources'][0]['properties']))

    def test_real_native_attribute_alias_and_inline_weapon_are_independent_definitions(self):
        alias=self.library.query(resource='BackpackCore',limit=100)
        row=alias['native_resources'][0]
        self.assertEqual('native_alias',row['definition_form'])
        edge=next(e for e in alias['native_uid_links'] if e['kind']=='native_alias_reference')
        self.assertNotEqual(row['resource_uid'],edge['target_uid'])
        weapon=self.library.query(resource='346395BC5F44C8090003A975ADB87A3F',limit=100)
        body=next(r for r in weapon['native_resources'] if r['resource_uid']=='346395BC5F45193100055E45A5632A32')
        self.assertEqual('Weapon',body['resource_type'])
        properties={p['field']:p['raw_value'] for p in body['properties']}
        self.assertEqual(('122.559998','1740'),(properties['myDamageMax'],properties['myReloadTimeMS']))

    def test_new_counts_and_exact_guid_link_coverage(self):
        self.assertEqual(['NATIVE_UID_DEFINITION_CONFLICT']*2,[r['code'] for r in self.result['issues']])
        self.assertEqual(216320,self.result['total'])
        self.assertEqual(2897,self.result['native_reference_total']);self.assertEqual(69872,self.result['native_localization_pair_keys'])
        refs=self.library.native_loaded['references'];en={r['key'] for r in self.library.loaded['game-english-menus']['records']}
        self.assertEqual(2320,sum(r['guid'] in en for r in refs))

    def test_all_146165_original_observations_keep_core_identity_and_values(self):
        before=json.loads((self.library.root/'dist/text-library-20261017-003/before.json').read_bytes())['observations']
        for source,expected in before.items():
            if source == 'business-bonuses':
                self.assert_business_bonus_catalog()
                continue
            rows=self.library.loaded[source]['records']
            raw=json.dumps([{k:v for k,v in r.items() if k!='relations'} for r in rows],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
            self.assertEqual(expected,dict(count=len(rows),core_sha256=sha256(raw)))

    def test_real_definition_counts_uid_collision_and_existing_reference_ids(self):
        self.assertEqual((9121,14973),(self.result['native_resource_total'],self.result['native_uid_link_total']))
        before=json.loads((self.library.root/'dist/text-library-20261017-003/before.json').read_bytes())
        self.assertTrue(set(before['old_reference_ids']).issubset({r['reference_id'] for r in self.library.native_loaded['references']}))
        out=self.library.query(resource='3797E3755CF83F0B001FD22CAF3088AA')
        self.assertEqual(2,out['native_resource_total'])
        self.assertEqual('NATIVE_UID_DEFINITION_CONFLICT',out['issues'][0]['code'])

    def test_real_burn_effect_retains_typed_rule_and_distinct_npc_duration(self):
        out=self.library.query(resource='777869BC5457C15400001FD0C4A3DAB3')
        self.assertEqual({'Burn','燃烧'},{r['text'] for r in out['results']})
        row=out['native_resources'][0]
        self.assertEqual('StatusEffect',row['resource_type'])
        props={p['field']:p['raw_value'] for p in row['properties']}
        self.assertEqual(('Burn_Duration_Final','NPC_Burn_Duration_Base','0.5'),
                         tuple(props[k] for k in ('myDuration','myDurationForNPCs','myMinimumDuration')))
        edge=next(e for e in out['native_uid_links'] if e['field']=='myTalentRules')
        self.assertEqual(('886631C55A27C7F400001D4520259802','saved_definition'),(edge['target_uid'],edge['target_status']))
        self.assertFalse(row['entity_mapping_confirmed'])

    def test_real_perfect_talent_keeps_pvp_values_and_explicit_base_relation(self):
        out=self.library.query(resource='BFAAA1FC5D8A0E2A00034519C4D63A41')
        row=out['native_resources'][0]
        values=[p for p in row['properties'] if p['field']=='myValue']
        self.assertEqual(['0.64','8.0'],[p['raw_value'] for p in values if any(c['internal_name']=='PVP' for c in p['context'])])
        self.assertEqual(['0.8','10.0'],[p['raw_value'] for p in values if not any(c['internal_name']=='PVP' for c in p['context'])])
        base=next(e for e in out['native_uid_links'] if e['kind']=='declared_native_inheritance')
        self.assertEqual('3797E3755BB3F1E70004C9D68098822C',base['target_uid'])
        self.assertEqual('saved_definition',base['target_status'])
        self.assertTrue(any('Perfectly On Empty' in r['text'] for r in out['results']))

    def test_real_boo_skill_branch_and_item_have_separate_uids_and_evidence(self):
        branch=self.library.query(resource='boo_skillmod_drone_assault')
        row=branch['native_resources'][0]
        self.assertEqual(('BOOSkillMod','D165BD135B755E560001CEF70982CAC4'),(row['resource_type'],row['resource_uid']))
        item_type=next(p['raw_value'] for p in row['properties'] if p['field']=='myItemType')
        item=self.library.query(resource=json.loads(item_type))['native_resources'][0]
        self.assertEqual(('WeaponModifierItem','F34855CA59C3821F0003441ED59D83CF'),(item['resource_type'],item['resource_uid']))
        self.assertNotEqual(row['resource_id'],item['resource_id'])
        self.assertEqual({'Striker','突袭者','前锋'},{p['text'] for p in branch['results'] if p['key']=='D165BD135B755E560001CEF5393AEFCD'})
        self.assertTrue(any(p.get('value_type')=='ItemModTag' and p['raw_value']=='AssaultDrone' for p in item['properties']))
        self.assertFalse(item['entity_mapping_confirmed'])

    def test_real_spawn_uid_collision_keeps_all_three_definitions(self):
        out=self.library.query(resource='B0EA4E535A8EF5BB0001184E6E93D2B0')
        self.assertEqual(3,out['native_resource_total'])
        self.assertEqual(3,len({r['resource_id'] for r in out['native_resources']}))
        self.assertEqual({'"NPC Tesla Trap"','"Trap (Skill - Parent)"','"Trap (Skill - Child)"'},
                         {r['internal_name'] for r in out['native_resources']})
        self.assertEqual(1,len(out['native_definition_conflicts']))
        self.assertTrue(all(not r['entity_mapping_confirmed'] for r in out['native_resources']))

    def test_real_named_gloves_uid_now_resolves_existing_gear_set_reference(self):
        uid='5D4179F15D7789A50003580F023071EC'
        out=self.library.query(resource=uid)
        self.assertEqual('ArmorItem',out['native_resources'][0]['resource_type'])
        self.assertTrue(any('Deathgrips' in r['text'] for r in out['results']))
        self.assertTrue(any(e['target_uid']==uid and e['target_status']=='saved_definition' for e in out['native_uid_links']))
        self.assertFalse(out['native_resources'][0]['entity_mapping_confirmed'])

    def test_real_skill_group_and_shock_parameter_do_not_become_skill_entities(self):
        out=self.library.query(resource='Drone_Base')
        self.assertEqual((78,26,27),(out['total'],out['native_reference_total'],out['native_resource_total']))
        self.assertEqual('AttributeDefinition',out['native_resources'][0]['resource_type'])
        shock=self.library.query(resource='Trap_Shock_Effect_Duration_Base')
        self.assertEqual({'Base Shock Duration','电击效果持续时间','基础电击效果持续时间'},{r['text'] for r in shock['results']})
        self.assertEqual('1C021E955DF11BF6000643C95C9D80F5',shock['native_resources'][0]['resource_uid'])
        self.assertTrue(all(r['entity_mapping_confirmed'] is False for r in shock['native_resources']))

    def test_real_talent_description_rules_and_attribute_target(self):
        out=self.library.query(resource='talent_gear_brand_g_01')
        self.assertEqual((6,2,1),(out['total'],out['native_reference_total'],out['native_uid_link_total']))
        self.assertIn('Critical Hit Chance bonus for 6 seconds when completing a Cover-to-Cover move.',{r['text'] for r in out['results']})
        self.assertEqual('4CDCE5B25AAA46F50004B8F0C3C1A251',out['native_uid_links'][0]['target_uid'])
        rules=self.library.query(resource='talentrule_gear_brand_g_01')
        values={(p['field'],p['raw_value']) for r in rules['native_resources'] for p in r['properties']}
        self.assertTrue({('myDuration','6.0'),('myValue','0.15'),('mySkillScriptAction','CompletedCoverToCover')} <= values)
        self.assertEqual(('myAttributeUID','saved_definition'),tuple(rules['native_uid_links'][0][k] for k in ('field','target_status')))

    def test_real_drone_formula_keeps_default_and_pvp_values_independent(self):
        row=self.library.query(resource='drone_assault_damage_Base')['native_resources'][0]
        properties={p['field']:p for p in row['properties']}
        self.assertEqual(('25','5.75','Game.IsPvPOverrideActive'),
            tuple(properties[k]['raw_value'] for k in ('myOriginalFormula','myFormula','myCondition')))
        self.assertFalse(any(c['internal_name']=='PvP' for c in properties['myOriginalFormula']['context']))
        self.assertEqual('PvP',properties['myFormula']['context'][-1]['internal_name'])
        raw=(self.library.root/row['resource_file']).read_bytes()
        for field in ('myOriginalFormula','myFormula','myCondition'):
            p=properties[field];loc=p['location']
            self.assertEqual(field+' '+p['raw_value'],raw[loc['byte_start']:loc['byte_end']].decode().strip())

    def test_real_talent_symbolic_formula_is_returned_without_evaluation(self):
        row=self.library.query(resource='TalentDownedAssistSpeedModFinal')['native_resources'][0]
        self.assertEqual('"Max(0, (1 + TalentDownedAsssistSpeedModBonus))"',row['properties'][0]['raw_value'])
        self.assertEqual('AttributeDefinition',row['resource_type'])
        self.assertFalse(row['entity_mapping_confirmed'])

    def test_real_enabled_missing_guids_only_gain_metadata_literals(self):
        expected={'4F5DDEA25409B75700001B3DB98592B0':'Primary Defensive',
                  '4F5DDEA25409B75700001B3E930CAD8A':'Primary Offensive',
                  '5D4179F1574D53DB0000628A8D5260F9':'Cold Protection'}
        for guid,value in expected.items():
            out=self.library.query(key=guid)
            self.assertEqual((1,1),(out['total'],out['native_reference_total']))
            self.assertEqual(('native_metadata_literal',value),tuple(out['results'][0][k] for k in ('value_kind','text')))
            self.assertEqual('guid_absent_from_selected_tables',out['native_references'][0]['match_status'])

    def test_original_80272_observations_have_identical_core_identity_and_values(self):
        before=json.loads((self.library.root/'dist/text-library-20261017-002/before.json').read_bytes())['observations']
        for source,expected in before.items():
            if source == 'business-bonuses':
                self.assert_business_bonus_catalog()
                continue
            rows=self.library.loaded[source]['records']
            raw=json.dumps([{k:v for k,v in r.items() if k!='relations'} for r in rows],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
            self.assertEqual(expected,dict(count=len(rows),core_sha256=hashlib.sha256(raw).hexdigest()))

    def test_real_chinesegav_value_and_original_brand_evidence_survive(self):
        out=self.library.query(key='4CDCE5B25C4057F2000322017B35A809')
        self.assertEqual({'5.11 Tactical','5.11战术'},{r['text'] for r in out['results']})
        row=next(r for r in out['results'] if r['source_id']=='game-english-menus')
        ref=next(r for r in row['relations'] if r['kind']=='native_guid_reference')
        self.assertEqual('myName',ref['field']);self.assertIn('game-brand-references.json',ref['evidence_file'])
        self.assertFalse(ref['entity_mapping_confirmed'])

    def test_real_multi_source_guid_and_unresolved_guid_are_explicit(self):
        out=self.library.query(key='5B17B22F5C41FD6C0004FFD990AD330A')
        self.assertEqual(3,out['native_reference_total'])
        self.assertEqual(3,len({r['resource_uid'] for r in out['native_references']}))
        self.assertTrue(all(sum(r['kind']=='native_guid_reference' for r in row['relations'])==3 for row in out['results']))
        out=self.library.query(key='4CDCE5B25B3626EC0000B880BC68E51E')
        self.assertEqual((0,1),(out['total'],out['native_reference_total']))

    def test_real_new_aliases_and_existing_attribute_pairs_are_not_replaced(self):
        out=self.library.query(key='Police M4',sources=['app-dictionary'])
        self.assertEqual(2,out['total'])
        self.assertEqual({'警用 M4'},{r['dictionary_output_key'] for r in out['results']})
        self.assertTrue(all(r['source_locations'][0]['il_offset']==72733 for r in out['results']))
        aliases=self.library.query(sources=['app-dictionary'],key='Critical Hit Damage')
        self.assertEqual(0,aliases['total'])
        self.assertEqual(2,self.library.query(sources=['app-attributes'],key='Critical Hit Damage')['total'])


if __name__=='__main__': unittest.main()
