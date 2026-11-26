"""Static readers for saved Fruit text exports and one known application dictionary."""
import json
import re

from .text_library import require, sha256


APP_DATA = 'Division2BuildTool.Model.AppData'
GUID_TAG = re.compile(rb'\bguid\s*=\s*#([0-9a-fA-F]{32})\b')
DEFINITION = re.compile(rb'^([ \t]*)([A-Za-z_]\w*)[ \t]+([^\r\n<>]+?)[ \t]+<\s*uid=([0-9a-fA-F]{32})\s*>[ \t]*(?::[^\r\n]+)?[\r]*$')
TEXT_FIELDS={'myName','myUIName','myToolTipText','myTitle','myInstructions','myHintHeader','myHintDescription',
             'myLore','myAbbreviation','myCountryOfOrigin'}
RULE_FIELDS={'myDuration','myExpirationTimer','myRequiredNumberOfItems','myValue','myModifier',
             'mySkillScriptAction','myBonusType','myUnit'}


def native_references(raw):
    """Read literal GUID fields; byte spans remain authoritative over display lines."""
    raw.decode('utf-8-sig')
    owners, references, issues = [], [], []
    offset = 0
    for line_number, line in enumerate(raw.split(b'\n'), 1):
        content = line.rstrip(b'\r')
        indent = len(content)-len(content.lstrip(b' \t'))
        if content.strip() == b'}':
            owners = [owner for owner in owners if owner['indent'] < indent]
        header = DEFINITION.fullmatch(content)
        if header:
            owners = [owner for owner in owners if owner['indent'] < len(header[1])]
            owners.append(dict(indent=len(header[1]),resource_type=header[2].decode(),
                               internal_name=header[3].decode('utf-8'),resource_uid=header[4].decode().upper()))
        tags = list(GUID_TAG.finditer(content))
        if tags:
            field = re.fullmatch(rb'[ \t]*(my\w+)[ \t]+(".*")[ \t]*',content)
            if not field or len(tags)!=1 or b'text =' not in field[2] or not owners:
                issues.append(dict(code='UNSUPPORTED_NATIVE_GUID_FIELD',line_lf=line_number,byte_start=offset))
            else:
                body = field[2].decode('utf-8')
                # Embedded metadata has its own quoting. Preserve that literal;
                # it is not a substitute for a value in a localization table.
                value = re.search(r'\btext\s*=\s*(.*?)(?:,\s*type\s*=|$)',body[1:-1])
                enabled = re.search(rb'\benabled\s*=\s*(true|false)',field[2])
                version = re.search(rb'\blineVersion\s*=\s*(-?\d+)',field[2])
                references.append(dict(guid=tags[0][1].decode().upper(),field=field[1].decode(),
                    **{k:v for k,v in owners[-1].items() if k!='indent'},
                    location=dict(line_lf=line_number,byte_start=offset,byte_end=offset+len(content),
                                  guid_byte_start=offset+tags[0].start(1),guid_byte_end=offset+tags[0].end(1)),
                    raw_field_sha256=sha256(content),embedded_text_literal=value[1] if value else None,
                    enabled=enabled[1]==b'true' if enabled else None,
                    line_version=int(version[1]) if version else None,entity_mapping_confirmed=False))
        offset += len(line)+1
    return dict(references=references,issues=issues,detected_guid_tags=len(list(GUID_TAG.finditer(raw))))


def metadata_literal_value(literal):
    """Decode the observed double-quoted or single-quoted Hunter varmap literal."""
    if isinstance(literal,str) and len(literal)>=2 and literal.startswith("'") and literal.endswith("'"):
        return json.loads('"'+literal+'"')[1:-1]
    require(isinstance(literal,str) and literal.startswith('\\"') and literal.endswith('\\"'),
            'UNSUPPORTED_METADATA_LITERAL')
    value=json.loads(json.loads('"'+literal+'"'))
    require(isinstance(value,str),'INVALID_METADATA_LITERAL')
    return value


def native_definitions(raw, include_formulas=False, include_data=False, include_objects=False):
    """Retain scopes and explicit references without evaluating game formulas.

    include_objects enables the observed inline Weapon and UID-less generation
    records. Earlier parsing rules keep their original ownership and output.
    """
    raw.decode('utf-8-sig')
    property_fields=RULE_FIELDS | {'myOriginalFormula','myFormula','myCondition'} if include_formulas else RULE_FIELDS
    old=native_references(raw)
    guid_fields={r['location']['byte_start']:r for r in old['references']}
    lines=[];offset=0
    for number,line in enumerate(raw.split(b'\n'),1):
        lines.append((number,offset,line.rstrip(b'\r')))
        offset+=len(line)+1
    following_lines=[None]*len(lines);following=None
    for i in range(len(lines)-1,-1,-1):
        following_lines[i]=following
        if lines[i][2].strip(): following=lines[i][2].strip()
    resources=[];links=[];includes=[];issues=list(old['issues']);stack=[];pending=None
    for index,(number,start,line) in enumerate(lines):
        stripped=line.strip()
        if not stripped: continue
        location=dict(line_lf=number,byte_start=start,byte_end=start+len(line))
        if stripped==b'{':
            require(pending is not None,'UNSUPPORTED_NATIVE_BLOCK')
            context,header_location=pending;pending=None
            if context['resource_uid'] is not None or context.get('uidless_definition'):
                parent=next((c['definition_index'] for c,_ in reversed(stack) if 'definition_index' in c),None)
                row=dict(context,parents=[dict(c) for c,_ in stack],location=dict(header_location),fields=[],properties=[])
                if 'inheritance_name' in context:
                    row.update(inheritance_location=dict(header_location),
                        inheritance_field_sha256=sha256(raw[header_location['byte_start']:header_location['byte_end']]))
                resources.append(row);context=dict(context,definition_index=len(resources)-1)
                if include_objects and parent is not None and 'inline_field' in context:
                    links.append(dict(source_index=parent,field=context['inline_field'],reference_uid=None,
                        target_name=None,target_uid=context['resource_uid'],kind='native_inline_definition',
                        context=[{k:v for k,v in c.items() if k!='definition_index'} for c,_ in stack],
                        location=dict(header_location),
                        raw_field_sha256=sha256(raw[header_location['byte_start']:header_location['byte_end']]),
                        entity_mapping_confirmed=False))
            stack.append((context,dict(location,header_location=header_location)))
            continue
        if stripped==b'}':
            require(bool(stack),'UNBALANCED_NATIVE_BLOCK')
            context,opened=stack.pop()
            if 'definition_index' in context:
                row=resources[context['definition_index']];row['location']['byte_end']=start+len(line)
                row['definition_sha256']=sha256(raw[row['location']['byte_start']:row['location']['byte_end']])
            elif include_objects and not raw[opened['byte_end']:start].strip():
                owner=next((c['definition_index'] for c,_ in reversed(stack) if 'definition_index' in c),None)
                if owner is not None:
                    resources[owner].setdefault('empty_blocks',[]).append(dict(field=context['resource_type'],
                        context=[{k:v for k,v in c.items() if k!='definition_index'} for c,_ in stack]+[context],
                        location=dict(opened['header_location'],byte_end=start+len(line))))
            continue
        following=following_lines[index]
        if following==b'{':
            header=DEFINITION.fullmatch(line)
            if header:
                context=dict(resource_type=header[2].decode(),internal_name=header[3].decode('utf-8'),resource_uid=header[4].decode().upper())
                inheritance=re.search(rb'>[ \t]*:[ \t]*(.+)',line) if include_data else None
                if inheritance:
                    context['inheritance_name']=inheritance[1].decode('utf-8')
            else:
                inline=re.fullmatch(rb'myWeapon[ \t]+<[ \t]*uid=([0-9a-fA-F]{32})[ \t]*>[ \t]*(?::[ \t]*(.+))?',stripped) if include_objects else None
                if inline:
                    context=dict(resource_type='Weapon',internal_name=None,resource_uid=inline[1].decode().upper(),inline_field='myWeapon')
                    if inline[2] is not None:context['inheritance_name']=inline[2].decode('utf-8')
                else:
                    parts=stripped.decode('utf-8').split(None,1)
                    context=dict(resource_type=parts[0],internal_name=parts[1] if len(parts)>1 else None,resource_uid=None)
                    if include_objects and not stack and parts[0] in ('ItemGenerationConfig','QualityTalentSlots',
                            'AttributeCurve','ItemGenerationBracketedCurve','ItemGenerationVersions','ItemGenerationVersionedSettings'):
                        context['uidless_definition']=True
                        if context['internal_name'] and ' : ' in context['internal_name']:
                            context['internal_name'],context['inheritance_name']=context['internal_name'].split(' : ',1)
            pending=(context,location)
            continue
        include=re.fullmatch(rb'include[ \t]+"([^"]+)"',stripped)
        if include is None and include_data:
            include=re.fullmatch(rb'include[ \t]+([^"\r\n]+)',stripped)
        if include:
            includes.append(dict(path=include[1].decode('utf-8'),location=location))
            continue
        owner=next((c['definition_index'] for c,_ in reversed(stack) if 'definition_index' in c),None)
        if owner is None and include_objects and not stack:
            alias=re.fullmatch(rb'([A-Za-z_]\w*)[ \t]+([^<>]+?)[ \t]+<[ \t]*uid=([0-9a-fA-F]{32})[ \t]*>[ \t]*=[ \t]*(.+?)[ \t]+([0-9a-fA-F]{32})',stripped)
            if alias:
                resources.append(dict(resource_type=alias[1].decode(),internal_name=alias[2].decode('utf-8'),
                    resource_uid=alias[3].decode().upper(),definition_form='native_alias',parents=[],location=location,
                    definition_sha256=sha256(raw[start:start+len(line)]),fields=[],properties=[]))
                links.append(dict(source_index=len(resources)-1,field=':alias',reference_uid=None,
                    target_type=alias[1].decode(),target_name=alias[4].decode('utf-8'),target_uid=alias[5].decode().upper(),
                    kind='native_alias_reference',context=[],location=location,raw_field_sha256=sha256(line),entity_mapping_confirmed=False))
        if owner is None: continue
        path=[{k:v for k,v in c.items() if k!='definition_index'} for c,_ in stack]
        edge=re.fullmatch(rb'([A-Za-z_]\w*)(?:[ \t]+([^<]*?))?[ \t]*<\s*uid=([0-9a-fA-F]{32})\s*>[ \t]*=[ \t]*(.+?)[ \t]+([0-9a-fA-F]{32})',stripped)
        field=re.fullmatch(rb'(my\w+)[ \t]+(.+)',stripped)
        if edge:
            links.append(dict(source_index=owner,field=edge[1].decode(),reference_uid=edge[3].decode().upper(),
                target_name=edge[4].decode('utf-8'),target_uid=edge[5].decode().upper(),kind='native_uid_reference',
                context=path,location=location,raw_field_sha256=sha256(line),entity_mapping_confirmed=False))
            if include_objects and edge[1]==b'myPresetTalent':links[-1]['target_type']='Talent'
        elif field and (field[1]==b'myAttributeUID' or (include_objects
                and ((resources[owner]['resource_type']=='WeaponItem' and field[1]==b'myBaseWeapon')
                    or (field[1]==b'myPresetAttribute' and path[-1]['resource_type']=='ItemAttributeSlot')
                    or (field[1]==b'myAttribute' and path[-1]['resource_type'] in ('myPrimaryAttributeRange','AttributeData','AttributeCurve')))) or (include_data
                and resources[owner]['resource_type']=='StatusEffect'
                and field[1] in (b'myResistanceAttributeUID',b'myActionBlocksImmunityAttributeUID'))
                ) and re.fullmatch(rb'[0-9a-fA-F]{32}',field[2]):
            links.append(dict(source_index=owner,field=field[1].decode(),reference_uid=None,target_name=None,
                target_uid=field[2].decode().upper(),kind='attribute_uid_reference',context=path,location=location,
                raw_field_sha256=sha256(line),entity_mapping_confirmed=False))
            if field[1]==b'myBaseWeapon':links[-1]['kind']='native_base_weapon_reference'
            elif field[1] in (b'myPresetAttribute',b'myAttribute'):links[-1]['kind']='native_generation_attribute_reference'
        elif include_data:
            assignment=re.fullmatch(rb'([A-Za-z_]\w*)[ \t]+=[ \t]*(.+?)[ \t]+([0-9a-fA-F]{32})',stripped)
            zero_curve=include_objects and field is not None and field[1] in (b'myRangeMin',b'myRangeMax') and re.search(rb'[ \t]+0{32}$',field[2])
            if assignment and not zero_curve:
                links.append(dict(source_index=owner,field=assignment[1].decode(),reference_uid=None,
                    target_name=assignment[2].decode('utf-8'),target_uid=assignment[3].decode().upper(),
                    kind='native_uid_assignment_reference',context=path,location=location,
                    raw_field_sha256=sha256(line),entity_mapping_confirmed=False))
            elif include_objects:
                symbol=re.fullmatch(rb'QualityTalentSlots[ \t]+(.+?)[ \t]+=[ \t]+(.+)',stripped)
                if symbol:
                    links.append(dict(source_index=owner,field=symbol[1].decode('utf-8'),reference_uid=None,
                        target_type='QualityTalentSlots',target_name=re.sub(rb'[ \t]+0{32}$',b'',symbol[2]).decode('utf-8'),target_uid=None,
                        kind='native_symbol_reference',context=path,location=location,
                        raw_field_sha256=sha256(line),entity_mapping_confirmed=False))
        if field:
            name=field[1].decode();row=resources[owner]
            curve=re.fullmatch(rb'=[ \t]*(.+)',field[2]) if include_objects and name in ('myRangeMin','myRangeMax') else None
            if curve:
                links.append(dict(source_index=owner,field=name,reference_uid=None,
                    target_type='ItemGenerationBracketedCurve',target_name=re.sub(rb'[ \t]+0{32}$',b'',curve[1]).decode('utf-8'),target_uid=None,
                    kind='native_symbol_reference',context=path,location=location,
                    raw_field_sha256=sha256(line),entity_mapping_confirmed=False))
            if start in guid_fields:
                row['fields'].append(dict(field=name,kind='localization_reference',guid=guid_fields[start]['guid'],location=location,context=path))
            elif name in TEXT_FIELDS and field[2].startswith(b'"'):
                try:
                    value=json.loads(field[2].decode('utf-8'))
                    require(isinstance(value,str),'INVALID_NATIVE_LITERAL')
                    row['fields'].append(dict(field=name,kind='native_literal',guid=None,text=value,location=location,context=path))
                except (ValueError,UnicodeError):
                    issues.append(dict(code='UNSUPPORTED_NATIVE_LITERAL',**location))
            elif name in property_fields or (include_data and not edge):
                row['properties'].append(dict(field=name,raw_value=field[2].decode('utf-8'),location=location,context=path))
        elif include_data and not edge:
            scalar=re.fullmatch(rb'(string|float|int|bool|file|ItemTag|ItemModTag|ItemQuality'+(rb'|uid' if include_objects else b'')+rb')[ \t]+("(?:\\.|[^"\\])*"|[A-Za-z_]\w*)[ \t]+(.+)',stripped)
            if scalar:
                resources[owner]['properties'].append(dict(field=scalar[2].decode(),value_type=scalar[1].decode(),
                    raw_value=scalar[3].decode('utf-8'),location=location,context=path))
                if scalar[1]==b'uid' and re.fullmatch(rb'[0-9a-fA-F]{32}',scalar[3]):
                    links.append(dict(source_index=owner,field=scalar[2].decode(),reference_uid=None,target_name=None,
                        target_uid=scalar[3].decode().upper(),kind='native_uid_list_reference',context=path,location=location,
                        raw_field_sha256=sha256(line),entity_mapping_confirmed=False))
    require(not stack and pending is None,'UNBALANCED_NATIVE_BLOCK')
    # Parser bookkeeping must not enter recorded parent context.
    for row in resources:
        row['parents']=[{k:v for k,v in c.items() if k!='definition_index'} for c in row['parents']]
    return dict(resources=resources,links=links,includes=includes,issues=issues)


def translation_dictionary(metadata):
    """Require the observed newobj / (dup, ldstr, ldstr, Add)* / stsfld shape."""
    type_index, app = next((i,t) for i,t in enumerate(metadata['types']) if t['name']==APP_DATA)
    method_index, method = next((i,m) for i,m in enumerate(app['methods']) if m['name']=='.cctor')
    il = method['il']
    start = 0
    matches = []
    for index,row in enumerate(il):
        if row['opcode'] != 'stsfld':
            continue
        if row['operand']['name'] == APP_DATA+'::TranslateDictionary':
            matches.append((start,index))
        start = index+1
    require(len(matches)==1,'TRANSLATION_DICTIONARY_NOT_UNIQUE')
    start,end = matches[0]
    require(il[start]['opcode']=='newobj' and il[start]['operand']['name']=='TypeSpecification::.ctor'
            and (end-start-1)%4==0,'UNSUPPORTED_TRANSLATION_INITIALIZER')
    rows=[]
    for index in range(start+1,end,4):
        snippet=il[index:index+4]
        require([r['opcode'] for r in snippet]==['dup','ldstr','ldstr','callvirt']
                and snippet[3]['operand']['name']=='TypeSpecification::Add'
                and snippet[3]['operand']['signature']=='20020113001301'
                and all(isinstance(r['operand'],str) for r in snippet[1:3]),'UNSUPPORTED_TRANSLATION_ENTRY')
        rows.append(dict(input_name=snippet[1]['operand'],output_internal_name=snippet[2]['operand'],
            il_offset=snippet[3]['offset'],method_token=method['token'],method_rva=method['rva'],
            evidence_pointer='/types/'+str(type_index)+'/methods/'+str(method_index)+'/il/'+str(index),
            instructions=snippet))
    require(len({r['input_name'] for r in rows})==len(rows),'DUPLICATE_TRANSLATION_INPUT')
    return rows
