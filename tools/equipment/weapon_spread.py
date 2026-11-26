"""PvE weapon launch-cone endpoints for settled pose, neutral turn and no accuracy lock."""
import math
from ctypes import c_float

MODES = {"stand": "AimSpread", "move": "AimSpread", "blind": "CoverSpread",
         "cover": "CoverAimSpread", "hip": "Spread"}
NEMESIS = "5d4179f15bd9c83400030db924aa0fb5"


def f32(x):
    return c_float(x).value


DEG = f32(math.pi / 180)
RAD = f32(180 / math.pi)


def ads_walk_speed(walk, factor):
    """Mean forward root displacement per second at full input on level ground."""
    target = f32(walk["targetMps"] * f32(factor))
    slow, fast = walk["forwardCycles"]
    if target <= 0 or target >= fast["speedMps"]:
        # Above the last key the client retimes the fast clip by last key / target.
        return max(0, target)
    weight = max(0, (target - slow["speedMps"]) / (fast["speedMps"] - slow["speedMps"]))
    if weight < f32(.0032):
        return slow["speedMps"]
    if weight > f32(.9964):
        return fast["speedMps"]
    distance = (1 - weight) * slow["strideM"] + weight * fast["strideM"]
    seconds = (1 - weight) * slow["strideM"] / slow["speedMps"] + weight * fast["strideM"] / fast["speedMps"]
    return distance / seconds


def angular_finals(raw, group, bonuses):
    """Fruit loader clamps its radian minimum before the dictionary evaluates each Final."""
    common = sum(bonuses.get(k, 0) for k in (
        "WeaponAccuracyModBonus", "WeaponSpreadSizeModBonus", "WeaponHandlingModBonus"))
    pairs = {}
    for prefix in dict.fromkeys(MODES.values()):
        low, high = (f32(f32(raw["my" + prefix + suffix]) * DEG) for suffix in ("Min", "Max"))
        finals = []
        for suffix, radians in (("Min", min(low, high)), ("Max", high)):
            specific = prefix + suffix
            if group == "Shotgun" and specific == "CoverSpreadMax":
                specific = "CoverSpreadMin"
            bonus = bonuses.get("Weapon" + specific + "ModBonus", 0)
            bonus += common if prefix != "Spread" else 0
            scale = f32(1 / max(f32(.00001), f32(1 + f32(bonus * (.5 if group == "Shotgun" else 1)))))
            finals.append(f32(f32(radians * RAD) * scale))
        pairs[prefix] = finals
    return pairs


def movement(raw, bonuses, speed):
    cap = f32(raw["myMovementModifierSpeedCap"])
    if cap <= 0:
        return 0.0
    weight = min(1, max(0, f32(f32(f32(speed) - f32(raw["myMovementSpreadThreshold"])) / cap)))
    modifier = max(0, f32(f32(f32(raw["myMovementModifier"]) * DEG)
                          * f32(1 / f32(1 + bonuses.get("WeaponSpreadMovementModBonus", 0)))))
    return f32(weight * modifier)


def cone_angles(raw, group, bonuses, modes, speed):
    pairs = angular_finals(raw, group, bonuses)
    result = {}
    for mode in modes:
        lo, hi = (f32(x * DEG) for x in pairs[MODES[mode]])
        first, last = (hi, lo) if raw["myUseReverseSpread"] else (lo, hi)
        # The client interpolates from the second endpoint even with a settled blend of one.
        first = f32(last + f32(first - last))
        extra = movement(raw, bonuses, speed) if mode == "move" else 0
        degrees = [math.degrees(f32(x + extra)) for x in (first, last)]
        if not all(0 <= x < 90 for x in degrees):
            raise ValueError(f"Unprojectable launch angle for {mode}: {degrees}")
        result[mode] = degrees
    return result

