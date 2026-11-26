"""Weapon fields use the equipment importer and its existing ownership contract."""
import json
import re
import math
from bisect import bisect_right
from ctypes import c_float
from functools import cached_property
from decimal import Decimal
from .weapons_native import WeaponNative, GROUPS, ROOT
from .native import richtext, number, parameter
from .native_attributes import constant_value
from . import weapon_damage, weapon_range
from .rules import EquipmentRules
from tools.brand_sets.native_structure import contexts
from tools.brand_sets.icons import weapon_talent_icons

COLLECTION='武器型号资料'
STATS={'rpm':'myRPM','magazine':'myClipSize','optimal':'myRangeOptimal','long':'myRangeLong',
       'range':'myRangeMax','damage_max':'myDamageMax','damage_min':'myDamageMin',
       'accuracy':'myAccuracyUI','stability':'myStabilityUI','reload':'myReloadTimeMS',
       'reload_empty':'myEmptyClipFirstRoundReloadTimeMS'}
RECOIL={'climb':'myRecoilClimbTimeMS','reset':'myRecoilResetTimeMS','vertical_delay':'myRecoilRecoveryTimeMS',
        'vertical_return':'myPitchRecoveryPercent','horizontal_delay':'myHorizontalRecoilRecoveryTimeMS',
        'horizontal_return':'myYawRecoveryPercent','horizontal_time':'myHorizontalRecoilTimeMS',
        'vertical_min':'myRecoilMin','vertical_max':'myRecoilMax','vertical_border':'myVerticalRecoilBorder',
        'left_strength':'myHorizontalRecoilLeft','right_strength':'myHorizontalRecoilRight',
        'cover_modifier':'myRecoilCoverModifier','hip_modifier':'myHipFireModifier'}
RECOIL_DEFAULTS={'climb':100,'reset':1000,'vertical_delay':500,'vertical_return':100,
                 'horizontal_delay':100,'horizontal_return':100,'horizontal_time':100}
QUALITIES='Black Yellow Grey Green Blue Purple Orange Vanity GearSet Exotic Immersion Prototype'.split()
HANDLING='3797E3755BAE97C30002BED1E9D83E8B'
TYPE_DAMAGE={'AssaultRifle':'AssaultRifle','LightMachinegun':'LMG','SniperRifle':'MarksmanRifle',
             'SubMachinegun':'SMG','Rifle':'Rifle','Shotgun':'Shotgun','Pistol':'Pistol'}


def fixed_socket(slot, fields, excluded, quality):
    return (slot != 'WeaponSkin' and fields.get('myIsAccessBlocked') == 'TRUE'
            and quality not in excluded and QUALITIES.index(fields.get('myRequiredItemQuality','Black'))
            <= QUALITIES.index(quality) <= QUALITIES.index(fields.get('myMaxItemQuality','Prototype')))

def primary_event_parameters(fire,mode):
    owner=next((c for p in fire for c in p['context'] if c['resource_type']==mode),None)
    return {p['field']:p['raw_value'] for p in fire if p['context'] and p['context'][-1]==owner}


def rpm_roll_counts(low,high):
    """Count the client's 23-bit uniform draws per truncated integer RPM offset."""
    if low==high:return {low:1}
    if high<low:raise ValueError('Inverted RPM fluctuation bounds')
    samples=range(1<<23)
    def roll(index):
        product=c_float((high-low)*(index/len(samples))).value
        return int(c_float(low+product).value)
    counts={}
    start=0
    while start<len(samples):
        offset=roll(start)
        end=bisect_right(samples,offset,lo=start,key=roll)
        counts[offset]=end-start
        start=end
    return counts


def default_fire_stats(stats, fire, bonuses, rate_bounds=(0, 0)):
    """PvE default event only. Simultaneous projectiles are included in base_damage."""
    modes=stats['fire_events']
    if not modes:return
    mode=modes[0]
    params=primary_event_parameters(fire,mode)
    rate=stats.get('rpm_with_mods',stats.get('rpm'))
    damage = None
    if not stats.get('default_damage_pending'):
        damage = stats.get('damage_with_mods', stats.get('base_damage'))
    if mode in ('FullAutoFireEvent','SemiAutoFireEvent'):
        override=float(params.get('myRPMOverride',0))
        if override>0 and stats.get('rpm'):
            rate=override*rate/stats['rpm']
        if rate and damage is not None:stats['dps']=float(Decimal(str(damage))*Decimal(str(rate))/60)
    elif mode=='BurstFireEvent':
        inner=int(params.get('myBurstRPMOverride',0))
        rounds=int(params.get('myRoundsPerBurst',3))+round(bonuses.get('48B41A535BADE3510002D433FCEAFF75',0))
        cycle=stats['fire_cycle']={'mode':'burst','rounds':rounds,'internal_rpm':inner}
        if not inner or rounds<1 or not rate:return
        inside=60000//inner
        # The non-sequence event timer starts at the first round. A separate
        # gate tests integer elapsed time since the last shot strictly > the
        # weapon interval. Both gates must permit a new trigger.
        def event_end(offset):
            return rounds*(60000//max(1,inner+offset))
        def next_trigger(offset):
            return (rounds-1)*inside+60000//max(1,round(rate)+offset)+1
        def burst_period(offset):
            return max(event_end(offset),next_trigger(offset))
        weights=rpm_roll_counts(*rate_bounds)
        lo,hi=min(weights),max(weights)
        short,long=burst_period(hi),burst_period(lo)
        if short!=long:
            cycle.update(inside_ms=inside,between_range_ms=[v-(rounds-1)*inside for v in (short,long)],
                         period_range_ms=[short,long])
            if damage is not None:stats['dps_range']=[damage*rounds*1000/p for p in (long,short)]
            if event_end(lo)<=next_trigger(hi):
                # The last-shot gate decides every cycle, regardless of earlier
                # rolls. Sustained DPS divides total damage by total elapsed time.
                mean=sum(next_trigger(offset)*count for offset,count in weights.items())/sum(weights.values())
                cycle['mean_period_ms']=mean
                if damage is not None:stats['dps']=damage*rounds*1000/mean
            return
        period=short
        cycle.update(inside_ms=inside,between_ms=period-(rounds-1)*inside,period_ms=period)
        if damage is not None:stats['dps']=damage*rounds*1000/period
    elif mode=='ChargedFireEvent':
        cycle={'mode':'charged','auto_release_s':float(params.get('myMaxDuration',5))}
        for key,uid in [('charge_s','3797E3755C4F3BF40023A5B9678B3D0E'),('minimum_s','30EB6A0F5C76A0E70003647C6A1260D2'),
                        ('full_charge_factor','3797E3755C4F3BF40023A5B8F34E8F7C')]:
            if uid in bonuses:cycle[key]=bonuses[uid]
        stats['fire_cycle']=cycle
        if (not rate or any(rate_bounds) or bonuses.get('3797E3755C4F3BF40023A5B78F6F953E')!=1
            or any(k not in cycle for k in ('charge_s','minimum_s','full_charge_factor'))):return
        charge_ms=int(1000*max(cycle['minimum_s'],cycle['charge_s']))
        if not 0<charge_ms<=1000*cycle['auto_release_s']:return
        recovery_ms=60000//max(1,round(rate))+1
        cycle.update(recovery_ms=recovery_ms,period_ms=charge_ms+recovery_ms)
        if damage is not None:
            cycle['full_charge_damage']=damage*cycle['full_charge_factor']
            stats['dps']=cycle['full_charge_damage']*1000/cycle['period_ms']
    elif mode=='BinaryFireEvent':
        cycle=stats['fire_cycle']={'mode':'binary','rounds':2}
        if not rate or any(rate_bounds):return
        # Release accepts timer equality. A new press requires strictly more
        # elapsed milliseconds after the release shot.
        interval=60000//max(1,round(rate))
        period=2*interval+1
        cycle.update(inside_ms=interval,between_ms=interval+1,period_ms=period)
        if damage is not None:stats['dps']=damage*2000/period


def fixed_secondary_stats(native, weapon, bonuses):
    """Weapon-only PvE values. Each pair retains a zero-loadout comparison."""
    effects={}
    chance=sum(bonuses.get(k,0) for k in ('4F5DDEA253EB6DD100001F28FCDEFA52','10E5BD55552D1AA200004882E759F8E6'))
    crit=sum(bonuses.get(k,0) for k in ('4F5DDEA253EB6DD100001F292673DC62','5D31260057343B77000096E0363DA2FF'))
    if chance:
        raw=float(native.scalar(weapon,'myCriticalHitChance',0))
        cap=.6+bonuses.get('5D3126005745CD2D0000902FB82A90AF',0)
        effects['crit_chance']=[100*max(0,min(.6,raw)),100*max(0,min(cap,raw+chance))]
    if crit:
        raw=.25+float(native.scalar(weapon,'myCriticalHitDamageModifier',1))-1
        effects['crit_damage']=[100*max(0,raw),100*max(0,raw+crit)]
    switch=bonuses.get('4F5DDEA25410024900001B190DD20269',0)+bonuses.get(HANDLING,0)
    if switch:effects['switch_factor']=[1,max(.00001,1+switch)]
    melee=bonuses.get('5D4179F15C13BC9000033F9CC5D321EC',0)
    if melee:effects['melee_factor']=[1,1+melee]
    movement=bonuses.get('4F5DDEA252D943B90000077FA24C5A93',0)
    if movement:effects['movement_factor']=[1,min(1.2,max(0,1+movement))]
    penetration=bonuses.get('30EB6A0F5A6F3C0200005F511F99B614',0)
    if penetration:effects['penetration']=[0,penetration]
    return effects


class WeaponProjection:
    def __init__(self,native):
        self.n=native;self.rules=EquipmentRules(native);self.rules.index();self.missing=[]
        skin_catalog=json.loads((ROOT/'data/equipment/weapon-skins.json').read_text('utf8'))
        self.skin_assets={r['uid']:r['asset_ref'] for r in skin_catalog['skins']}
        self.unreleased_skin_uids=set(skin_catalog.get('unreleased',{}))
        self.slot_names={}
        self.pool_documents={};self.art_bounds={}
        self.signatures=native.signature_weapons()
        self.talent_icons=weapon_talent_icons(ROOT)
        from . import native_tree as tree
        self.expertise_source='hunter/game system data/juice/shdresearch/shdresearch.juice'
        self.expertise_definitions=[r for r in tree.walk(tree.parse(native.file(self.expertise_source).read_text('utf-8-sig'))) if r['header'].startswith('SHDUpgradeBonusDefinition ')]
        document=tree.parse(native.file('hunter/game system data/rejuice/itemmodtaghierarchy.rejuice').read_text('utf-8-sig'))
        for row in tree.walk(document):
            tag=tree.prop(row,'myTag');guid=re.search(r'guid = #([A-F0-9]{32})',tree.prop(row,'myUIName',''))
            if tag and guid:
                label=native.localization('zh').get(guid[1],'')
                if label:self.slot_names[tag]=label

    @cached_property
    def reviewed_attributes(self):
        entities = json.loads((ROOT / 'data/equipment/records.json').read_text('utf8'))['entities']
        reviewed = {}
        for entity in entities.values():
            if entity['template'] == '武器信息':
                for row in entity['collections']['武器型号资料']['rows']:
                    model = row['data']
                    reviewed[model['装备UID'], model['kind']] = model['attributes']
        return reviewed

    def retain_reviewed_maxima(self, uid, kind, attributes):
        previous = self.reviewed_attributes.get((uid, kind), [])
        slot = ('id', 'core', 'named', 'percentile', 'granted')
        for attr in attributes:
            if not attr.get('id') or 'maximum' in attr:
                continue
            # Keep an adopted ceiling only for the same model and native slot.
            matches = [a for a in previous if a.get('reference_field') and 'maximum' in a and 'unit' in a
                       and all(a.get(k) == attr.get(k) for k in slot)]
            if len(matches) == 1:
                attr.update({k: matches[0][k] for k in ('maximum', 'unit', 'reference_field')})

    @cached_property
    def attribute_rows(self):
        rows={}
        for ns in ('hunter','rogue'):
            for path in self.n.file(ns+'/game system data/juice/attribute/dictionary').glob('*.mdict'):
                for row in self.n.document(path.relative_to(self.n.root).as_posix())['resources']:
                    rows[row['resource_uid']]=row
        return rows

    def expertise(self,item):
        from . import native_tree as tree
        uid=item['resource_uid'];tags={p['raw_value'] for p in self.n.collection(item,'myTags')[1]};out=[]
        def values(node,field):return [p[0] for p in (tree.child(node,field) or {'properties':[]})['properties']]
        def uids(nodes):return {m[1] for r in nodes if (m:=re.search(r' ([A-F0-9]{32})$',r))}
        for definition in self.expertise_definitions:
            scope=tree.child(definition,'myItemsDefine')
            if scope is None:continue
            excluded=uids(values(scope,'myExcludeItems'))
            allowed=uids(values(scope,'myItems'))
            tag_values={r.rsplit(' ',1)[-1] for r in values(scope,'myItemTags')}
            excluded_tags={r.rsplit(' ',1)[-1] for r in values(scope,'myExcludeItemTags')}
            if uid in excluded or tags & excluded_tags or not (uid in allowed or tags & tag_values):continue
            for bonus in tree.walk(definition):
                if not bonus['header'].startswith('SHDUpgradeBonusAttribute '):continue
                formula=tree.child(bonus,'myValueFormula')
                if formula is None:continue
                attribute=tree.prop(bonus,'myAttributeUID')
                # Project the two weapon upgrade definitions only. Skill
                # definitions can retain broad editor tags (e.g. Exotic) and
                # are not evidence of an additional weapon upgrade.
                if attribute not in ('43A2C97052209A23000004CDD0FB54EC','5D4179F15BC1F72C0002FCD003F26495'):continue
                native=self.attribute_rows.get(attribute)
                fields=[f for f in native['fields'] if f['field']=='myUIName'] if native else []
                name=self.n.localization().get(fields[0]['guid'],'') if fields else ''
                out.append({'attribute':attribute,'name':richtext(name),'type':tree.prop(bonus,'myType'),
                            'formula':{key:float(tree.prop(formula,'my'+key,'0')) for key in ('A','B','C')},'source':self.expertise_source})
        return out

    def unavailable(self,uid,field,error):
        self.missing.append({'uid':uid,'field':field,'reason':str(error)})

    @cached_property
    def damage_scales(self):
        return weapon_damage.damage_scales(self.n)

    @cached_property
    def signature_skill_scale(self):
        return weapon_damage.signature_skill_scale(self.n)

    def generation_config(self, item):
        links = self.n.references(item, 'myItemGenerationConfig')[1]
        choices = self.rules.configs.get(links[0]['target_uid'], []) if len(links) == 1 else []
        if len(choices) != 1:
            raise ValueError('Weapon generation config is missing or ambiguous')
        return choices[0]

    def base_volley(self, item, weapon, fire, stats, quality, signature):
        reader = weapon_damage.signature_primary_range if signature else weapon_damage.primary_range
        fields, _ = self.rules.reader.resolve(*self.generation_config(item), reader)
        if not fields and signature:
            scale = 0  # WeaponBaseDamageUI applies its 0.5 minimum in base_volley.
        elif (fields.get('myAttribute') != weapon_damage.PRIMARY
              or any(float(fields.get(key, 0)) != 0 for key in ('myMin', 'myMax'))):
            raise ValueError('Unreviewed weapon primary attribute or instance roll')
        elif signature:
            level = float(self.n.scalar(item, 'myPrescriptedLevel', -1))
            if not level.is_integer() or not 1 <= level <= 40:
                raise ValueError('Unresolved signature item generation level')
            item_quality = self.n.scalar(item, 'myQuality')
            scale = weapon_damage.damage_scales(self.n, int(level))[item_quality]
        else:
            scale = self.damage_scales[quality]
        return weapon_damage.base_volley(self.n, weapon, fire, stats['damage_max'], stats['pellets'], scale)

    def art_fit(self,asset_ref):
        if asset_ref not in self.art_bounds:
            from PIL import Image
            from tools.identity import asset
            with Image.open(ROOT/asset(asset_ref)['source']) as image:
                bounds=image.getchannel('A').getbbox() if image.mode=='RGBA' else (0,0,*image.size)
                if bounds is None:raise ValueError('Empty weapon artwork: '+asset_ref)
                x,y,right,bottom=bounds
                x=max(0,x-2);y=max(0,y-2);right=min(image.width,right+2);bottom=min(image.height,bottom+2)
                self.art_bounds[asset_ref]={'width':image.width,'height':image.height,'x':x,'y':y,'w':right-x,'h':bottom-y}
        return self.art_bounds[asset_ref]

    def optional_text(self,row,field,language='zh'):
        try:return self.n.text(row,field,language)
        except (ValueError,KeyError):return ''

    def config(self,item,quality,field,kind):
        def extract(row,refs):
            if any(e['field']==field and len(e['context'])==1 for e in row.get('empty_blocks',[])):return ([],[])
            groups=[c for c in contexts(row,refs,kind) if any(p['field']=='myQuality' and p['raw_value']==quality and p['context']==c for p in row['properties'])]
            if not groups:
                # The root ItemGenerationConfig lists have no implicit slots.
                # Signature configs intentionally omit the attribute list.
                present=any(any(c['resource_type']==field for c in p['context']) for p in row['properties']+refs)
                if not row.get('inheritance_name') and not present:return ([],[])
                return None
            if len(groups)!=1:raise ValueError('Weapon quality group is ambiguous')
            scope=groups[0]
            return ([p for p in row['properties'] if p['context'][:len(scope)]==scope],
                    [r for r in refs if r['context'][:len(scope)]==scope])
        return self.rules.reader.resolve(*self.generation_config(item),extract)[0]

    def external(self,name,uid,folder,suffix):
        for ns in ('hunter','rogue'):
            path=ns+'/game system data/juice/'+folder+'/'+name.strip('"')+suffix
            if self.n.file(path).is_file():
                found=self.n.definition(path,uid=uid)
                if found:return found
        raise ValueError('Native UID target not found: '+str(uid))

    def attributes(self,item,quality,preset=None):
        self.optional_text(item,'myUIName')
        props,refs=self.config(item,quality,'myAttributeSlots','QualityAttributeSlots')
        slots=[]
        for ctx in dict_contexts(props,refs,'ItemAttributeSlot'):
            values={p['field']:p['raw_value'] for p in props if p['context']==ctx}
            uid=values.get('myPresetAttribute','0'*32)
            if uid!='0'*32:
                row=self.attribute_rows[uid]
                text_fields=[p for p in row['fields'] if p['field']=='myUIName']
                name=self.n.texts.get('zh',{}).get(text_fields[0]['guid'],'') if text_fields else ''
                if not name:raise ValueError('Attribute localization unavailable: '+uid)
                pools=sorted({r['target_uid'] for r in refs if r['field']=='AttributeListContainer' and r['context'][:len(ctx)]==ctx})
                entry={'id':uid,'name':richtext(name),'core':values.get('myIsCoreAttribute')=='TRUE',
                       'named':values.get('myIsNamedAttribute')=='TRUE','percentile':values.get('myPresetPercentage','-1')}
                if preset and uid in preset['attributes']:
                    grant=preset['attributes'][uid]
                    if (quality!='Orange' or not entry['named'] or float(entry['percentile'])!=preset['percentile']
                            or pools!=[grant['pool']]):
                        raise ValueError('Level-40 grant no longer matches its native slot: '+uid)
                    entry.update(granted=grant['value'],unit='%')
                if entry['percentile'] in ('-1','-1.0','100','100.0'):
                    bound=self.attribute_maximum(uid,pools,quality)
                    if bound is not None:entry['maximum']=bound;entry['unit']='%'
                slots.append(entry)
            else:
                pools=sorted({r['target_uid'] for r in refs if r['field']=='AttributeListContainer' and r['context'][:len(ctx)]==ctx})
                slots.append({'name':'随机属性','core':values.get('myIsCoreAttribute')=='TRUE','pools':pools})
        if preset and set(preset['attributes'])!={a['id'] for a in slots if 'granted' in a}:
            raise ValueError('Level-40 grant missing its native attribute')
        return slots

    def attribute_maximum(self,uid,pools,quality):
        # Reuse the closed, constant high-level interval contract. Never choose
        # a Power endpoint for a sloped curve; apply the attribute's UI rounding.
        from . import native_tree as tree
        if self.n.attribute(uid).get('myBonusType')!='Percentage':return None
        results=[]
        for pool in pools:
            if pool not in self.rules.pools:continue
            path,_=self.rules.pools[pool]
            if path not in self.pool_documents:self.pool_documents[path]=tree.parse(path.read_text('utf-8-sig'))
            doc=self.pool_documents[path]
            containers=[r for r in tree.walk(doc) if ('uid='+pool) in r['header']]
            if len(containers)!=1:continue
            defs=[r for r in tree.walk(containers[0]) if r['header'].startswith('AttributeData ') and tree.prop(r,'myAttribute')==uid]
            for definition in defs:
                curve=tree.child(definition,'myRangeMax')
                if curve is None:
                    ref=tree.prop(definition,'myRangeMax','')
                    name=ref[2:].rsplit(' ',1)[0] if ref.startswith('= ') else ''
                    curve=next((r for r in doc['children'] if r['header'].split(' ',1)[-1].split(' <')[0].strip('"')==name),None)
                if curve is None:continue
                data={'brackets':[{'max_power':int(tree.prop(r,'myMaxPower','-1')),**{k.lower():tree.prop(r,'my'+k,'0') for k in ('A','B','C')}} for r in curve['children']],
                      'qualities':{tree.prop(r,'myQuality','Grey'):tree.prop(r,'myModifier','1') for r in (tree.child(definition,'myQualityModifiers') or {'children':[]})['children']}}
                try:value=constant_value(data,quality,'Percentage',930 if any(r['max_power']==930 for r in data['brackets']) else None)
                except ValueError:continue
                results.append(float(parameter({'raw':value,'type':'FlatValue','round':self.n.attribute(uid).get('myRoundMode','None')})))
        return results[0] if results and len(set(results))==1 else None

    def talents(self,item,quality,owner):
        props,refs=self.config(item,quality,'myTalentSlots','QualityTalentSlots')
        if any(r['field']=='myPresetTalent' and not r['target_uid'] for r in refs):
            raise ValueError('Fixed talent reference unavailable')
        preset={r['target_uid']:r for r in refs if r['field']=='myPresetTalent' and r['target_uid']}
        effects=[];fixed={}
        for uid,ref in preset.items():
            row=self.external(ref['target_name'],uid,'talent','.mtalent')
            for attribute,value in self.fixed_talent_bonuses(row).items():
                fixed[attribute]=fixed.get(attribute,0)+value
            name=richtext(self.n.text(row,'myUIName'))
            for mode in ('PvE','PvP'):
                try:
                    _,description=self.n.talent(row,mode)
                    if not name or not description:raise ValueError('Fixed talent text unavailable')
                except (ValueError,KeyError,IndexError) as error:
                    self.unavailable(item['resource_uid'],'talent:'+uid+':'+mode,error);continue
                effects.append({'效果ID':owner+'_'+uid.lower(),'模式':mode,'所属装备':owner,'名称':name,
                                '描述':description,'图标':('weapon_talent_'+uid.lower()) if ('weapon_talent_'+uid.lower()) in self.talent_icons else '',
                                '属性ID':'','属性':'','数值':'','单位':''})
        return effects,not bool(preset),fixed

    def fixed_talent_bonuses(self,talent):
        """The normal (PvE) list. Skill-script tuning IDs remain separate from actual stat IDs."""
        _,props,_=self.n.collection(talent,'myBonusList')
        out={}
        for prop in props:
            ctx=prop['context']
            if prop['field']!='myAttributeUID' or ctx[-1]['resource_type'] not in ('BonusAttributeRef','BonusValue'):continue
            raw=next((p['raw_value'] for p in props if p['field']=='myValue' and p['context']==ctx),'0')
            out[prop['raw_value']]=out.get(prop['raw_value'],0)+float(raw)
        return out

    def sockets(self,item,quality):
        owner,props,refs=self.n.collection(item,'myItemSockets')
        rows=[]
        for ctx in dict_contexts(props,refs,'ItemSocket'):
            values={p['field']:p['raw_value'] for p in props if p['context']==ctx}
            tags=[p['raw_value'] for p in props if p['context'][:len(ctx)]==ctx and p.get('value_type')=='ItemModTag']
            mods=[r for r in refs if r['field']=='myPreattachedMods' and r['target_uid'] and r['context'][:len(ctx)]==ctx]
            resolved=[]
            for ref in mods:
                try:
                    definition=self.n.record('rogue/game system data/juice/preattachedmods/player_weapon_preattached_mods.mpreattachedmoddefinition',ref['target_uid'])
                    for prop in self.n.collection(definition,'myMods')[1]:
                        if prop.get('value_type')!='string':continue
                        name=prop['raw_value'].strip('"');mod=None
                        for ns in ('hunter','rogue'):
                            source=ns+'/game system data/juice/item/'+name.lower()+'.mitem'
                            if self.n.file(source).is_file():
                                mod=self.n.definition(source,name=name)
                                if mod:break
                        if mod is None:raise ValueError('Preattached item asset not found: '+name)
                        bonuses=[]
                        for value in self.n.collection(mod,'myAttributeBonuses')[1]:
                            if value['field']!='myValue':continue
                            props2=self.n.collection(mod,'myAttributeBonuses')[1]
                            attr=next(p['raw_value'] for p in props2 if p['field']=='myAttributeUID' and p['context']==value['context'])
                            native=self.attribute_rows.get(attr)
                            fields=[f for f in native['fields'] if f['field']=='myUIName'] if native else []
                            label=self.n.texts['zh'].get(fields[0]['guid'],'') if fields else ''
                            kind=self.n.attribute(attr).get('myBonusType','FlatValue')
                            bonuses.append({'uid':attr,'name':richtext(label),'value':float(value['raw_value'])*(100 if kind=='Percentage' else 1),'unit':'%' if kind=='Percentage' else ''})
                        resolved.append({'uid':mod['resource_uid'],'definition_uid':ref['target_uid'],'name':richtext(self.optional_text(mod,'myUIName')),'bonuses':bonuses,
                                         'source':mod['_source'],'graph':self.n.scalar(mod,'myGraphObject'),'skin':self.n.scalar(mod,'mySkinBaseTexture') or self.n.scalar(mod,'mySkinTexture')})
                except (ValueError,KeyError,OSError,StopIteration) as error:self.unavailable(item['resource_uid'],'mod:'+ref['target_uid'],error)
            names=list(dict.fromkeys(self.slot_names[tag] for tag in tags if tag in self.slot_names))
            slot=values.get('mySocketIO',ctx[-1]['internal_name'])
            socket={'slot':slot,'name':' / '.join(names) or None,'tags':tags,'mods':resolved,
                    'preattached':[r['target_uid'] for r in mods]}
            if mods:
                excluded={p['raw_value'] for p in props if p['context'][:len(ctx)]==ctx and p['context'][-1]['resource_type']=='myExcludedQualities'}
                socket['fixed']=fixed_socket(slot,values,excluded,quality)
            rows.append(socket)
        return rows

    @cached_property
    def skin_items(self):
        items = []
        for ns in ('hunter', 'rogue'):
            directory = self.n.file(ns + '/game system data/juice/item')
            for path in sorted(directory.iterdir()):
                if path.suffix.lower() != '.mitem':
                    continue
                source = path.relative_to(self.n.root).as_posix()
                raw = self.n.file(source).read_bytes()
                if b'WeaponTransmogItem' not in raw and b'WeaponSkinItem' not in raw:
                    continue
                for mod in self.n.document(source)['resources']:
                    if mod['parents'] or mod['resource_type'] not in ('WeaponTransmogItem', 'WeaponSkinItem'):
                        continue
                    tags = {p['raw_value'] for p in self.n.collection(mod, 'myModTags')[1]
                            if p.get('value_type') == 'ItemModTag'}
                    items.append((mod, tags))
        return items

    def skins(self,sockets):
        slots = [s for s in sockets if s['slot'] == 'WeaponSkin']
        if not slots:
            return []
        tags = {tag for s in slots for tag in s['tags']}
        attached = {m['uid'] for s in slots for m in s.get('mods', [])}
        dedicated = tags - {'Skin', 'Mod'}
        if not dedicated and not attached:
            return []
        skins=[]
        for mod,allowed in self.skin_items:
            uid = mod['resource_uid']
            if uid in self.unreleased_skin_uids or (uid not in attached and not dedicated.intersection(allowed)):
                continue
            name=richtext(self.n.text(mod,'myUIName'))
            if not name:raise ValueError('Weapon skin name unavailable: '+uid)
            skin={'uid':uid,'name':name,'tags':sorted(allowed & tags),'source':mod['_source'],'icon':self.n.scalar(mod,'myIcon'),'graph':self.n.scalar(mod,'myGraphObject')}
            if uid in attached:
                skin['preattached'] = True
            if uid in self.skin_assets:skin['asset_ref']=self.skin_assets[uid]
            skins.append(skin)
        return sorted(skins, key=lambda skin: not skin.get('preattached'))

    def row(self,binding):
        n=self.n;uid=binding['uid'];item=n.record(binding['source'],uid);weapon=n.linked(item,'myWeapon')
        row={'stable_id':'weapon_'+uid.lower(),'装备UID':uid,
             'kind':binding['kind'],'group':binding['group'],'base_uid':binding.get('base_uid'),
             'description':'','asset_ref':binding.get('asset_ref'),
             'variants':binding.get('variants',[])}
        for field,language in (('装备名称','zh'),('英文原名','en')):
            try:row[field]=n.item_name(item,language)
            except (OSError,ValueError,KeyError) as error:self.unavailable(uid,field,error)
        try:row['description']=n.item_description(item)
        except (OSError,ValueError,KeyError) as error:self.unavailable(uid,'description',error)
        if binding.get('asset_ref'):row['art_fit']=self.art_fit(binding['asset_ref'])
        if uid in self.signatures:row['specialization']=self.signatures[uid]
        stats={key:float(value) for key,field in STATS.items() if (value:=n.scalar(weapon,field)) is not None}
        # weapon.fruit supplies 0.0 when no ancestor overrides myStabilityUI.
        stats.setdefault('stability', 0.0)
        _,fire,fire_links=n.collection(weapon,'myFireEvents')
        firetypes=list(dict.fromkeys(c['resource_type'] for p in fire for c in p['context'] if c['resource_type'].endswith('FireEvent')))
        stats['fire_events']=firetypes
        if firetypes:
            stats['pellets']=int(primary_event_parameters(fire,firetypes[0]).get('myBulletsPerRound',1))
        quality='Exotic' if row['kind'] in ('exotic','signature') else 'Orange'
        signature = row['group'] == 'SignatureWeapon'
        project_fire_stats = not signature
        if not binding.get('damage_excluded'):
            try:
                stats['base_damage'] = self.base_volley(item, weapon, fire, stats, quality, signature)
            except (ValueError, KeyError, OSError, StopIteration) as error:
                self.unavailable(uid, 'base_damage', error)
            if signature:
                try:
                    projectile, impact = weapon_damage.signature_event(fire, fire_links)
                    script_damage = weapon_damage.f32(n.scalar(weapon, 'mySkillScriptDamage', 0))
                    # Only sustained automatic bullet fire uses the standard DPS model for signature weapons.
                    project_fire_stats = (firetypes[:1] == ['FullAutoFireEvent'] and projectile == 'BulletHitScan'
                                          and impact is None and script_damage == 0)
                    if impact in weapon_damage.BLAST_SCRIPTS and script_damage > 0:
                        stats['base_explosion_damage'] = weapon_damage.f32(script_damage * self.signature_skill_scale)
                except (ValueError, KeyError, OSError) as error:
                    self.unavailable(uid, 'signature_discharge', error)
        row['stats']=stats;row['recoil']=[]
        for field,label in [('myCameraRecoil','镜头后坐力'),('myAimDirectionRecoil','瞄准方向后坐力')]:
            if not n.references(weapon,field)[1]:continue
            try:
                config=n.linked(weapon,field)
                values={k:float(value) for k,prop in RECOIL.items() if (value:=n.scalar(config,prop,RECOIL_DEFAULTS.get(k))) is not None}
                row['recoil'].append({'name':label,'uid':config['resource_uid'],'values':values})
            except (ValueError,KeyError,OSError) as error:self.unavailable(uid,field,error)
        preset=binding.get('level40_preset')
        try:row['attributes']=self.attributes(item,quality,preset)
        except (ValueError,KeyError,OSError) as error:row['attributes']=[];self.unavailable(uid,'attributes',error)
        self.retain_reviewed_maxima(uid, row['kind'], row['attributes'])
        try:effects,row['random_talent'],fixed=self.talents(item,quality,row['stable_id'])
        except (ValueError,KeyError,OSError,IndexError) as error:effects=[];fixed={};self.unavailable(uid,'talents',error)
        try:row['sockets']=self.sockets(item,quality)
        except (ValueError,KeyError,OSError) as error:row['sockets']=[];self.unavailable(uid,'sockets',error)
        try:row['skins']=self.skins(row['sockets'])
        except (ValueError,KeyError,OSError) as error:row['skins']=[];self.unavailable(uid,'skins',error)
        row['fixed_talent_bonuses']=fixed
        try:row['expertise']=self.expertise(item)
        except (ValueError,KeyError,OSError) as error:row['expertise']=[];self.unavailable(uid,'expertise',error)
        bonuses=dict(fixed)
        control_presets = {
            '43A2C97052209A23000004D8D5EC4528': 'stability_compare',
            '43A2C97052209A23000004DB8AF701B4': 'reload_ui',
        }
        unresolved_controls = set()
        for attr in row['attributes']:
            attribute = attr.get('id')
            if attribute not in control_presets:
                continue
            # A fixed roll modifies the same attribute as an installed attachment.
            value=attr.get('granted',attr.get('maximum'))
            if attr.get('named') and attr.get('unit') == '%' and value is not None:
                bonuses[attribute] = bonuses.get(attribute, 0) + value / 100
            else:
                unresolved_controls.add(control_presets[attribute])
        for socket in row['sockets']:
            if not socket.get('fixed'):continue
            for mod in socket['mods']:
                for bonus in mod['bonuses']:
                    bonuses[bonus['uid']]=bonuses.get(bonus['uid'],0)+bonus['value']/(100 if bonus['unit']=='%' else 1)
        # WeaponRPMCompareUI reads RPMFinal.
        rpm_bonus = sum(Decimal(str(bonuses.get(uid, 0))) for uid in (
            '43A2C97052209A23000004DC3D85D0C7', '5D4179F155FFC2E80000C82FEE8A95C3',
            '3797E3755BA13CC20015BD9A6CE93B46'))
        if rpm_bonus and 'rpm' in stats:
            stats['rpm_with_mods'] = float(Decimal(str(stats['rpm'])) * max(0, 1 + rpm_bonus))
        damage_bonus=Decimal(str(bonuses.get('43A2C97052209A23000004CDD0FB54EC',0)))
        # A named damage roll can be preset at e.g. 50, 75 or 115 percent
        # of its generation interval. The simulator's shared maximum does
        # not establish the actual granted value of that item.
        type_stat=TYPE_DAMAGE.get(row['group'],'')+'DamageModBonus'
        prescribed=[a for a in row['attributes'] if a.get('named') and float(a['percentile'])>=0
                    and self.attribute_rows.get(a.get('id'),{}).get('internal_name')==type_stat]
        extra_pellets=round(bonuses.get('48B41A535BADE33A0002D1CD82DAA88B',0))
        if extra_pellets and stats.get('pellets'):
            stats['pellets_with_mods']=max(1,stats['pellets']+extra_pellets)
        core=prescribed[0] if len(prescribed)==1 else {}
        basis=(preset or {}).get('basis')
        reviewed=bool(core) and preset and float(core['percentile'])==preset['percentile']
        if reviewed and basis=='grant' and 'granted' in core:
            damage_bonus+=Decimal(str(core['granted']))/100
        elif reviewed and basis=='excess' and 'granted' in core and 'maximum' in core:
            damage_bonus+=(Decimal(str(core['granted']))-Decimal(str(core['maximum'])))/100
        elif (prescribed or preset) and not (reviewed and basis=='ordinary'):
            stats['default_damage_pending']=True
            for attr in prescribed:attr['instance_value_pending']=True
            self.unavailable(uid,'default_damage','Named damage roll: level-40 granted value at its native preset percentile is unresolved')
        if not stats.get('default_damage_pending') and (damage_bonus or extra_pellets) and 'base_damage' in stats:
            volley=Decimal(str(stats['base_damage']))*max(0,1+damage_bonus)
            if extra_pellets and stats.get('pellets'):
                volley=volley*stats['pellets_with_mods']/stats['pellets']
            stats['damage_with_mods']=float(volley)
        if 'base_damage' in stats and not stats.get('default_damage_pending'):
            stats['damage_ui'] = round(weapon_damage.f32(stats.get('damage_with_mods', stats['base_damage'])))
        range_flat=bonuses.get(weapon_range.FLAT,0)
        range_mod=sum(bonuses.get(uid,0) for uid in weapon_range.PERCENT)
        if range_flat or range_mod:
            for field in ('optimal','long'):
                if field in stats:stats[field+'_with_mods']=(stats[field]+range_flat)*max(0,1+range_mod)
        try:
            scale = 1.0 if row['group'] == 'SignatureWeapon' else self.damage_scales[quality]
            stats['distance_damage'] = weapon_range.profiles(n, weapon, stats, fire, range_flat, range_mod, scale)
        except (KeyError, ValueError, OSError) as error:
            self.unavailable(uid, 'distance_damage', error)
        secondary=fixed_secondary_stats(n,weapon,bonuses)
        if secondary:stats['fixed_secondary']=secondary
        if project_fire_stats:
            bounds=tuple(int(float(n.scalar(weapon,key,0))) for key in ('myRPMFluctuationMin','myRPMFluctuationMax'))
            default_fire_stats(stats,fire,bonuses,bounds)
        head=n.scalar(weapon,'myDamageMultiplierHead')
        head_uids={'5D31260055A5251C00000585050F2BC4','10E5BD55558185C100000891ED2BA4F1'}
        head_attributes=[a for a in row['attributes'] if a.get('id') in head_uids]
        # Weapon.DamageMultiplierHead is a multiplier. Add only this item's
        # fixed headshot attribute/mods; character watch/gear bonuses stay out.
        head_values=[a.get('granted',a.get('maximum')) for a in head_attributes]
        if head is not None and all(v is not None for v in head_values):
            multiplier=float(head)+sum(head_values)/100+sum(bonuses.get(uid,0) for uid in head_uids)
            stats['headshot']=(multiplier*max(0,1+bonuses.get('4F5DDEA253EB764D0000204A2E0F1BEE',0))-1)*100
        if 'magazine' in stats:
            # ClipSizeFinal: flat additions precede a positive modifier; the
            # negative branch applies to the native clip. One/two-round clips
            # have explicit overrides. The native result rounds down.
            base=stats['magazine'];flat=bonuses.get('43A2C97052209A23000004DD71A770C1',0)
            modifier=bonuses.get('43A2C97052209A23000004DA32591EE2',0)
            clip=base+flat
            if base in (1,2):clip=base
            elif modifier>0:clip+=max(1,clip*modifier)
            elif modifier<0:clip+=min(-1,base*modifier)
            stats['magazine_with_mods']=math.floor(max(0,clip))
        # ReloadTimeMSCalc inherits WeaponHandlingModBonus. Keep raw native
        # milliseconds alongside the derived fixed-item value.
        reload_bonus=bonuses.get('43A2C97052209A23000004DB8AF701B4',0)+bonuses.get('3797E3755BAE97C30002BED1E9D83E8B',0)
        reload_flat=bonuses.get('4F5DDEA253F6053A00000DD487DFA83B',0)
        for key in ('reload','reload_empty'):
            if stats.get(key,-1)>=0:stats[key+'_with_mods']=max(0,stats[key]-reload_flat)/max(.00001,1+reload_bonus)
        # WeaponReloadTimeCompareUI -> WeaponReloadTimeUI selects cycling or
        # empty-clip timing; a per-round reload must not be shown as a full clip.
        rounds=int(n.scalar(weapon,'myRoundsAddedPerReload','-1'))
        initial=float(n.scalar(weapon,'myInitialShellReloadTimeMS','-1'))
        if rounds==1:
            stats['reload_per_round']=True
            if initial>=0 and 'reload_with_mods' in stats:
                stats['reload_ui']=stats['reload_with_mods']*(stats['magazine_with_mods']-1)+max(0,initial-reload_flat)/max(.00001,1+reload_bonus)
        else:stats['reload_ui']=stats.get('reload_empty_with_mods',stats.get('reload_with_mods'))
        if bonuses.get('544DB9085DF111890003721C5E047536',0)>0:
            stats['reload_unnecessary']=True
        # itemdetail_stats consumes CompareUI, not Weapon.AccuracyUI (which
        # belongs to the modding screen). Apply only fixed item bonuses.
        handling=bonuses.get(HANDLING,0)
        spread=bonuses.get('43A2C97052209A23000004D5B1403F3D',0)+bonuses.get('5D4179F15BF557AA00032C570AF8C977',0)+handling
        if row['group']=='SniperRifle':
            speed=bonuses.get('43A2C97052209A23000004D633EC80E9',0)
            grow=float(n.scalar(weapon,'myTimeToMinAccuracyMS','500'))*max(0,1+speed)
            shrink=float(n.scalar(weapon,'myTimeToMaxAccuracyMS','1000'))/max(.00001,1+speed+spread*.3)
            stats['accuracy_compare']=min(100,(200/(1+grow+shrink)+.6)*60+spread*40+20)
        else:
            low=float(n.scalar(weapon,'myAimSpreadMin','0'));high=float(n.scalar(weapon,'myAimSpreadMax','0'))
            stats['accuracy_compare']=max(10,min(100,80/(1+min(low,high))+40/(1+high)+spread*40-40))
        stats['stability_compare']=stats['stability']*(1+bonuses.get('43A2C97052209A23000004D8D5EC4528',0)+bonuses.get('5D4179F15BF5593200032C60DD35B0C6',0)+handling)
        for field in sorted(unresolved_controls):
            stats.pop(field, None)
            self.unavailable(uid, field, 'Fixed control attribute value unavailable')
        return row,effects

    def project(self,bindings):
        result=[]
        batch_start=len(self.missing)
        for entity in bindings:
            units=[]
            names=None
            for b in entity['items']:
                start=len(self.missing)
                row,effects=self.row(b)
                if b['kind']!='named':
                    if names is not None:raise ValueError('Ambiguous primary weapon: '+entity['id'])
                    names={field:row[field] for field in ('装备名称','英文原名') if field in row}
                target={'field':'data','records':[{'field':COLLECTION,'template':'武器型号','id':{'stable_id':row['stable_id']}}]}
                unit={'target':target,'value':json.dumps(row,ensure_ascii=False,separators=(',',':')),'semantic':row}
                # Omission alone is inconclusive. These optional inputs have known absence rules.
                unit['clear']=[field for field in ('specialization','art_fit') if field not in row]
                unit['clear'] += ['stats.'+key for key in STATS if key not in row['stats']]
                unit['clear'] += ['stats.'+key for key in ('base_damage','damage_ui','base_rpm','rpm_with_mods','damage_with_mods',
                                  'optimal_with_mods','long_with_mods','pellets_with_mods','reload_per_round','reload_unnecessary',
                                  'default_damage_pending','fixed_secondary','dps','dps_range','damage_precision','fire_cycle') if key not in row['stats']]
                if b['kind'] == 'signature' and 'base_explosion_damage' not in row['stats']:
                    unit['clear'].append('stats.base_explosion_damage')
                missing={issue['field'] for issue in self.missing[start:]}
                if not any(field=='talents' or field.startswith('talent:') for field in missing):
                    unit['fixed_effect_ids']=sorted({effect['效果ID'] for effect in effects})
                units.append(unit)
                for effect in effects:
                    target={'records':[{'field':'效果资料','template':'装备效果','id':{'效果ID':effect['效果ID'],'模式':effect['模式']}}]}
                    for field,value in effect.items():units.append({'target':{**target,'field':field},'value':value,'semantic':value})
            for field,value in (names or {}).items():
                units.append({'target':{'field':field,'records':[]},'value':value,'semantic':value})
            from tools.identity import page
            result.append({'id':entity['id'],'source':page(entity['id'])['source'],'template':'武器信息','units':units})
        return {'schema_version':1,'entities':result,'unavailable':self.missing[batch_start:]}


def dict_contexts(props,refs,kind):
    result=[]
    for p in props+refs:
        for i,c in enumerate(p['context']):
            if c['resource_type']==kind and p['context'][:i+1] not in result:result.append(p['context'][:i+1])
    return result


def crafting_projection(native,projection):
    """Extend the shared crafting/source catalog, preserving unrelated subjects."""
    from .crafting import Crafting,CATALOG
    from .native_sources import project as sources
    from .native_source_rules import project as rules
    c=Crafting(native,ROOT)
    db=json.loads((ROOT/'data/equipment/records.json').read_text('utf8'))
    db['entities']={k:v for k,v in db['entities'].items() if v['template']=='武器信息'}
    records,blueprint_records,owners=c.scan();infos=c.source_infos()
    known=c.identities(db,records,owners,projection)
    blueprints=c.blueprints(blueprint_records,known,infos)
    sources(c,known,blueprints,blueprint_records);rules(c,known,blueprints,records)
    saved=json.loads((ROOT/CATALOG).read_text('utf8'));subjects=set(known)|set(blueprints)
    units=[]
    for unit in c.units:
        path=unit['path'];key=path[0]
        if key=='routes':
            old=saved.get('routes',{}).get(path[1],{});merged={}
            for identity,row in old.items():
                remaining=[uid for uid in row['targets'] if uid not in subjects]
                if remaining:merged[identity]={**row,'targets':remaining}
            for identity,row in unit['value'].items():
                prior=merged.get(identity)
                merged[identity]={**row,'targets':sorted(set(row['targets'])|set(prior['targets'] if prior else []))}
            units.append({**unit,'value':merged,'semantic':merged})
        elif key in ('items','blueprints') or key in ('sources','source_contexts','condition_items'):
            units.append(unit)
    projection['catalogs']=units;projection['unavailable'].extend(c.unavailable)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=__import__('pathlib').Path);p.add_argument('--crafting',action='store_true');p.add_argument('--name',action='append',help='Project only the entity containing this exact weapon name; repeatable');a=p.parse_args()
    mapping=json.loads((ROOT/'data/equipment/native-map.json').read_text('utf8'))
    bindings=mapping['weapons']
    if a.name:
        missing=set(a.name)-{b['name'] for e in bindings for b in e['items']}
        if missing:raise ValueError('Unknown weapon names: '+', '.join(sorted(missing)))
        bindings=[e for e in bindings if any(b['name'] in a.name for b in e['items'])]
    native=WeaponNative(ROOT/'resources/game/current/raw_files');result=WeaponProjection(native).project(bindings)
    if a.crafting:crafting_projection(native,result)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(len(result['entities']),'pages;',len(result['unavailable']),'unavailable fields')
