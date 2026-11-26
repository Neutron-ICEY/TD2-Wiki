"""Default PvE physical damage at distance, expressed relative to point-blank damage."""

import math

from .weapon_damage import f32, physical_entry

FLAT = '43A2C97052209FAE000004FB3EE13CB6'
PERCENT = ('43A2C97052209FAE000004F9BA3A9FAA', '3797E3755BFC69E90004160B332AA289',
           '3797E3755BAD1DE2000431963B2D8E9D')
DISTANCES = {'optimal': 'myRangeOptimal', 'long': 'myRangeLong', 'limit': 'myRangeMax'}
OVERRIDE_DEFAULTS = {'optimal': 50, 'long': 75, 'limit': 100}


def adjusted_distance(raw, flat, modifier):
    return f32(f32(f32(raw) + f32(flat)) * max(0, f32(1 + f32(modifier))))


def physical_damage_at(distance, optimal, long, limit, near, far):
    """Client RVA 0x12CC631, default PvE physical channel with zero damage variation."""
    distance, optimal, long, limit, near, far = map(f32, (distance, optimal, long, limit, near, far))
    if distance > limit:
        return 0.0
    if distance > long:
        return far
    width = f32(long - optimal)
    if distance < optimal or abs(width) < f32(1e-5):
        return near
    t = f32(f32(distance - optimal) / width)
    return f32(far + f32(f32(1 - t) * f32(near - far)))


def profiles(native, weapon, stats, fire, flat, modifier, scale):
    """Read each hitscan FireEvent, using its WeaponDamage override as a separate record."""
    events = {}
    for prop in fire:
        context = prop['context']
        event = next((i for i, c in enumerate(context) if c['resource_type'].endswith('FireEvent')), None)
        if event is not None:
            key = (context[event]['resource_type'], context[event]['internal_name'])
            events.setdefault(key, []).append((prop, tuple(c['resource_type'] for c in context[event+1:])))

    weapon_damage = native.collection(weapon, 'myDamages')[1]
    ordinary = {'optimal': stats['optimal'], 'long': stats['long'], 'limit': stats['range']}
    result = []
    for (mode, _), properties in events.items():
        projectile = next((p['raw_value'] for p, ctx in properties
                           if ctx == ('myProjectileData',) and p['field'] == 'myProjectileType'), 'BulletHitScan')
        if projectile != 'BulletHitScan':
            continue
        override = [p for p, ctx in properties if ctx[:1] == ('myWeaponOverride',)]
        values = {p['field']: p['raw_value'] for p, ctx in properties if ctx == (
            'myWeaponOverride', 'FireEventWeaponOverride', 'myDamage')}
        ranges = {k: float(values.get(field, OVERRIDE_DEFAULTS[k])) for k, field in DISTANCES.items()} if override else ordinary
        endpoints = []
        for key in ('max', 'min'):
            field = 'myDamage' + key.title()
            damage = physical_entry(override, field)
            if damage is None:
                damage = physical_entry(weapon_damage, field)
            if damage is None:
                damage = stats['damage_' + key]
            # Same generated weapon scale for both physical endpoints. The Final
            # attributes floor each endpoint before interpolation, per pellet.
            endpoints.append(math.floor(f32(f32(damage) * max(.5, scale))))
        near, far = endpoints
        if near <= 0:
            continue
        profile = {'optimal': adjusted_distance(ranges['optimal'], flat, modifier),
                   'long': adjusted_distance(ranges['long'], flat, modifier),
                   'limit': f32(ranges['limit']), 'near': near, 'far': far}
        if any(all(p[k] == v for k, v in profile.items()) for p in result):
            continue
        at_limit = physical_damage_at(profile['limit'], **profile)
        result.append({'mode': mode, **profile, 'retention': at_limit / near})
    return result
