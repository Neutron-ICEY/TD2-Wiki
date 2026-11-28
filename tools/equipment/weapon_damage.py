"""Native item generation and near-range weapon damage for the PvE inventory."""
import math
import re
from ctypes import c_float

from . import native_tree as tree

SETTINGS = 'hunter/game system data/rejuice/itemgenerationsettings.rejuice'
CURVES = 'hunter/game system data/juice/itemgeneration/attributecurves/attributecurves_{}.mitemgenerationattributecurves'
PRIMARY = '4F5DDEA253F6F6E700000DE8E92DD09D'
GRENADE_EXPLOSION = '5D4179F15A030C4A00022C5D8ED16481'
BLAST_SCRIPTS = {GRENADE_EXPLOSION, '544DB9085D4D33410013BC7057F8BCFB', 'F34855CA58D8C97000009BC57FD0D39F'}


def f32(value):
    return c_float(float(value)).value


def required(node, name):
    child = tree.child(node, name)
    if child is None:
        raise ValueError('Missing native damage input: '+name)
    return child


def level_power(definitions, level):
    previous_level = 1
    power = int(tree.prop(definitions, 'myPowerBaseValue', '1'))
    ranges = required(definitions, 'myLevelModifiers')['children']
    for row in sorted(ranges, key=lambda r: int(tree.prop(r, 'myMaxLevel', '30'))):
        end = int(tree.prop(row, 'myMaxLevel', '30'))
        if end <= previous_level or level < previous_level:
            raise ValueError('Invalid native level-power interval')
        rate = f32(tree.prop(row, 'myModifier', '1'))
        factor = f32(rate ** (min(end, level) - previous_level))
        # The client caches the ceiling at each segment boundary, then uses it as the next base.
        power = math.ceil(max(0, f32(f32(power) * factor)))
        if level <= end:
            return power
        previous_level = end
    raise ValueError('Level exceeds native power definitions')


def damage_scales(native, level=40):
    def read(path):
        return tree.parse(native.file(path).read_text('utf-8-sig'))
    version = tree.item_generation_version(native)
    defs, = [v for v in tree.walk(read(SETTINGS)) if v['header'] == 'myPowerDefinitions']
    power = level_power(defs, level)
    curve = required(read(CURVES.format(version)), 'AttributeCurve WeaponDamage')
    if tree.prop(curve, 'myAttribute') != PRIMARY or required(curve, 'myGenTypeModifiers')['children']:
        raise ValueError('Unreviewed WeaponDamage attribute or generation-type modifier')
    brackets = required(curve, 'myBracketedCurve')['children']
    eligible = [(int(tree.prop(row, 'myMaxPower', '-1')), row) for row in brackets]
    selected = [row for end, row in sorted(eligible, key=lambda v: math.inf if v[0] == -1 else v[0])
                if end == -1 or end >= power]
    if not selected:
        raise ValueError('Missing WeaponDamage power interval')
    a, b, c = [f32(tree.prop(selected[0], field, 0)) for field in ('myA', 'myB', 'myC')]
    # Native 0x11ec4f7 uses Power*A*A + Power*B + C.
    base = f32(f32(f32(f32(power*a)*a) + f32(power*b)) + c)
    return {tree.prop(row, 'myQuality', 'Grey'): f32(base*f32(tree.prop(row, 'myModifier', 1)))
            for row in required(curve, 'myQualityModifiers')['children']}


def primary_range(record, links):
    fields = {p['field']: p['raw_value'] for p in record['properties']
              if p['context'][-1]['resource_type'] == 'myPrimaryAttributeRange'}
    if fields:
        return fields
    if any(e['field'] == 'myPrimaryAttributeRange' for e in record.get('empty_blocks', [])):
        return {}


def signature_primary_range(record, links):
    fields = primary_range(record, links)
    if fields is None and not record.get('inheritance_name') and not any(link['field'] == ':alias' for link in links):
        # A terminal config without a primary range grants no WeaponDamageBaseModBonus.
        return {}
    return fields


def signature_event(fire, links):
    first = next((p['context'][:i+1] for p in fire for i, c in enumerate(p['context'])
                  if c['resource_type'].endswith('FireEvent')), None)
    if first is None:
        return None, None
    projectiles = [p['raw_value'] for p in fire if p['field'] == 'myProjectileType'
                   and p['context'][:-1] == first and p['context'][-1]['resource_type'] == 'myProjectileData']
    impacts = [link['target_uid'] for link in links if link['field'] == 'myImpactSkillScript' and link['context'] == first]
    if len(projectiles) > 1 or len(impacts) > 1:
        raise ValueError('Ambiguous signature weapon discharge')
    return next(iter(projectiles), 'BulletHitScan'), next(iter(impacts), None)


def signature_skill_scale(native, level=40):
    """Neutral PvE SkillCurveFinal, without group scaling or a game-mode modifier."""
    if level <= 30:
        raise ValueError('Expected the level 31+ skill curve')
    folder = 'rogue/game system data/juice/attribute/dictionary/'
    scaling = folder + 'scaling_dictionary.mdict'
    gear = native.record(scaling, '5D31260056814D04000088E43BB795C6')
    player_gear = native.record(scaling, '5D31260056814C2A000088D6C44754FC')
    skill = native.record(folder + 'player_skill_dictionary.mdict', 'F34855CA5BAA38300002AE63A137A52D')
    if (native.direct(player_gear)['myOriginalFormula'] != 'BaseGearScalingCurve'
            or native.direct(skill)['myOriginalFormula'].strip('"').replace(' ', '') != 'LevelAndTierCurve*PlayerExclusiveBaseGearScalingCurve'):
        raise ValueError('Unreviewed signature skill scaling inputs')
    neutral_gear = f32(native.direct(gear)['myOriginalFormula'])
    curve = native.record(scaling, '1C021E955DE63E2B0015885E862867EC')
    branch = {p['field']: p['raw_value'].strip('"') for p in curve['properties']
              if p['context'][-1]['internal_name'] == '31+'}
    formula = branch.get('myFormula', '').replace(' ', '')
    power = r'\(([\d.]+)\^(\d+)\)'
    above = r'\(([\d.]+)\^MAX\(0,\(Agent.level\+Agent.CoopBuff-(\d+)\)\)\)'
    match = re.fullmatch(power + r'\*' + power + r'\*' + above, formula)
    if not match or branch.get('myCondition', '').replace(' ', '') != '(Agent.level+Agent.CoopBuff)>30':
        raise ValueError('Unreviewed signature skill level curve')
    base, levels, tier, tiers, growth, start = map(float, match.groups())
    at_30 = f32(f32(base ** levels) * f32(tier ** tiers))
    return f32(f32(at_30 * f32(growth ** max(0, level - start))) * neutral_gear)


def physical_entry(properties, field='myDamageMax'):
    entries = {}
    for p in properties:
        ctx = p['context'][-1]
        if ctx['resource_type'] == 'DamageInfo':
            entries.setdefault(ctx['internal_name'], {})[p['field']] = p['raw_value']
    result = None
    for entry in entries.values():
        if entry.get('myDamageType', 'PHYSICAL') == 'PHYSICAL':
            result = f32(entry.get(field, 0))
    return result


def base_volley(native, weapon, fire, physical_max, pellets, scale):
    if not pellets or pellets < 1 or not fire:
        raise ValueError('Incomplete native weapon discharge')
    first = next(c for p in fire for c in p['context'] if c['resource_type'].endswith('FireEvent'))
    override = physical_entry([p for p in fire if first in p['context']
                               and any(c['resource_type'] == 'myWeaponOverride' for c in p['context'])])
    if override is None:
        override = physical_entry(native.collection(weapon, 'myDamages')[1])
    damage = f32(physical_max) if override is None else override
    return f32(f32(damage * max(.5, scale)) * pellets)
