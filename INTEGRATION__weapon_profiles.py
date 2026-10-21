"""
INTEGRATION__weapon_profiles.py  (NEW 2026-10-20, Claude - Pile 2 rules)

Weapons whose damage, Cluster column or heat isn't one fixed number in
equipment.json - the data INTEGRATION__fire_modes reads to price and resolve
them. Before 2026-10-20 none of these could fire (null damage), or fired
without their special rule. Core Rulebook pages per entry; tables pp.248-254.

  Variable damage (V), by range bracket (pp.184-188; tables pp.248-250):
    heavy Gauss 25 / 20 / 10, Snub-Nose PPC 10 / 8 / 5, VSP lasers small 5 / 4 / 3,
    medium 9 / 7 / 5, large 11 / 9 / 7 (their -3 / -2 / -1 to-hit: weapon_rules).
  Hyper-assault Gauss (p.184): Cluster C5 on the 20 / 30 / 40 column, 1 damage
    a slug, +2 on the Cluster roll at short range, -2 at long (Daniel
    2026-10-20, as the text says). Its flak mode isn't offered (no airborne
    targets).
  M-pod (p.189): -1 to hit (weapon_rules), Cluster with 1-point (C1) hits on
    the 15 / 10 / 5 column at 0-1 / 2 / 3 hexes. A-pods and B-pods only harm
    infantry - no effect in a 'Mech duel.
  Machine gun array (p.185): fires its location's machine guns of its type
    (up to 4) as one attack - Cluster +2 on the column of the guns fired, each
    hit the guns' Damage Value, ALL hits to one hit location; its guns can't
    fire on their own while it is active (always on: Daniel's default for
    activated systems).
  Bombast laser (p.185): 8 / 12 / 16 damage at +0 / +1 / +2 to hit and 6 / 9 /
    12 heat - a choice (stubs.stub_munition_choice). Charging it instead of
    firing isn't offered.
  Rifles (cannon) (p.190): -3 damage against 'Mechs (so a light rifle does none).
  Heat-causing weapons (pp.102-104, 183-184, 189): flamers add their Damage
    Value as heat to the target (ER flamer 1), plasma rifle 1D6, plasma cannon
    2D6 (no damage) - outside heat, at most 15 a turn, in the Heat Phase
    (INTEGRATION__heat). Expected damage doesn't price the heat.
  Artillery cannons (pp.182-183): a normal ranged attack, but area-effect - no
    immobile -4, 5-point groupings; a miss scatters MOF / 2 hexes (1D6
    direction); the Long Tom also deals 10 to the hexes next to where it lands.
  Arrow IV (p.182): artillery at a hex 7-17 hexes away (a "distant" shot at 18+
    arriving next turn isn't offered); to-hit Gunnery + 4 with no range,
    target-movement or immobile modifier; 20 area-effect damage in the hex,
    10 to the hexes around it, 5-point groupings; a miss scatters 1D6
    direction, MOF / 2 (round up) hexes - so a miss by 1-2 lands next to the
    target. AMS can't touch it. Standard missiles only (homing needs TAG).
  Thumper and Sniper artillery (Tactical Operations; Daniel, 2026-10-21:
    "Thumper And Sniper Artillery use the same rules as Arrow IV. Thumper uses
    a 15/5 damage profile as a difference. Their homing ammo does 10 (Sniper)
    and 5 (Thumper) on a hit. Plus 5 AE damage to all units in the target
    hex... we'll post the full rules later"): is_arrow covers them, with
    their own damage (ARTILLERY; the Core support-strike tables p.153 agree:
    Thumper 3/1, Sniper 4/2 x 5).
  Homing artillery (p.190, 2026-10-21): only at a target designated by TAG
    this turn (INTEGRATION__tag) - in a duel, the firer's own. 2D6 4+ with no
    modifiers: HOMING_DAMAGE as one direct-fire ballistic hit on the side
    facing the firer (Arrow IV 20, Sniper 10, Thumper 5); 3 or less: the
    target's hex takes 5 area-effect damage. The chosen hex is 7-17 hexes
    away and the target within 8 of it, so any target up to 17 hexes away in
    the launcher's arc can be reached. The 5 also hits every OTHER unit in
    the hex on a hit (Daniel, 2026-10-21) - nobody else in a duel. TAG can
    designate the ground (the enemy's hex) instead of the 'Mech, an easier
    shot (INTEGRATION__tag): then either result is 5 AE on the 'Mech there.
    Not modeled: firing without LOS.
"""

import re

VARIABLE_DAMAGE = {          # canonical-name fragment -> {bracket: damage}
    "SMALLVSP": {"short": 5, "medium": 4, "long": 3},
    "MEDIUMVSP": {"short": 9, "medium": 7, "long": 5},
    "LARGEVSP": {"short": 11, "medium": 9, "long": 7},
    "SNPPC": {"short": 10, "medium": 8, "long": 5},
}
HEAVY_GAUSS_DAMAGE = {"short": 25, "medium": 20, "long": 10}
HAG_CLUSTER_BY_BRACKET = {"short": 2, "medium": 0, "long": -2}
HAG_GROUPING = 5
MPOD_COLUMN_BY_BRACKET = {"short": 15, "medium": 10, "long": 5}
MGA_CLUSTER = 2
MGA_MAX_GUNS = 4
BOMBAST = {"8": (8, 0, 6), "12": (12, 1, 9), "16": (16, 2, 12)}     # kind -> (damage, TN, heat)
RIFLE_VS_MECH = -3
ARROW_DAMAGE, ARROW_SPLASH, ARROW_TN = 20, 10, 4
ARTILLERY = {"ARROWIV": (ARROW_DAMAGE, ARROW_SPLASH),    # (in the hex, the hexes around it)
             "SNIPER": (20, 10),                         # Daniel 2026-10-21: "the same rules as Arrow IV"
             "THUMPER": (15, 5)}                         # "Thumper uses a 15/5 damage profile"
HOMING_DAMAGE = {"ARROWIV": 20, "SNIPER": 10, "THUMPER": 5}   # p.190; Daniel 2026-10-21 - needs TAG (not built)
HOMING_AE = 5                                      # p.190: to anything else in the target hex
HOMING_TN = 4                                      # p.190: 2D6, no modifiers
HOMING_REACH = 17                                  # a "close" attack: a chosen hex 7-17 away within 8 of the target
CANNON_SPLASH = {"LONGTOMCANNON": 10}               # adjacent-hex damage (p.183)
ARROW_RANGE = (7, 17)
AREA_GROUPING = 5                                  # artillery / AE: 5-point groupings (pp.87, 182)
OUTSIDE_HEAT_CAP = 15                              # p.102


def cn(weapon):
    import INTEGRATION__weapon_rules as weapon_rules
    return weapon_rules.canonical_name(weapon)


def is_heavy_gauss(weapon):
    n = cn(weapon)
    return "HEAVYGAUSS" in n and "IMPROVED" not in n


def variable_damage(weapon):
    n = cn(weapon)
    if is_heavy_gauss(weapon):
        return HEAVY_GAUSS_DAMAGE
    return next((table for frag, table in VARIABLE_DAMAGE.items() if frag in n), None)


def is_hag(weapon):
    return cn(weapon).startswith("CLHAG")


def hag_size(weapon):
    return int(re.search(r"(\d+)", cn(weapon)).group(1))


def is_mpod(weapon):
    return "MPOD" in cn(weapon)


def is_infantry_pod(weapon):
    n = cn(weapon)
    return "APOD" in n or "BPOD" in n


def is_mga(weapon):
    n = cn(weapon)
    return n.endswith("MGA") or "MACHINEGUNARRAY" in n


def is_bombast(weapon):
    return "BOMBAST" in cn(weapon)


def is_rifle(weapon):
    n = cn(weapon)
    return n.endswith("RIFLE") and not any(k in n for k in ("GAUSS", "PLASMA"))


def artillery_kind(weapon):
    """"ARROWIV" / "SNIPER" / "THUMPER" for a weapon fired by the Arrow IV
    rules (a key of ARTILLERY), else None. Not the artillery cannons."""
    n = cn(weapon)
    if "ARROWIV" in n:
        return "ARROWIV"
    return next((k for k in ("SNIPER", "THUMPER") if n.endswith(k) or n.endswith(k + "ARTILLERY")), None)


def is_arrow(weapon):
    """Fired by the Arrow IV rules (p.182): Arrow IV, Thumper and Sniper."""
    return artillery_kind(weapon) is not None


def arrow_damage(weapon):
    return ARTILLERY[artillery_kind(weapon)][0]


def homing_damage(weapon):
    return HOMING_DAMAGE[artillery_kind(weapon)]


def is_art_cannon(weapon):
    n = cn(weapon)
    return n.endswith("CANNON") and any(k in n for k in ("THUMPER", "SNIPER", "LONGTOM"))


def splash(weapon):
    """Damage to the hexes next to where an area-effect shell lands."""
    if is_arrow(weapon):
        return ARTILLERY[artillery_kind(weapon)][1]
    return next((v for k, v in CANNON_SPLASH.items() if k in cn(weapon)), 0)


def target_heat(weapon, roll_d6):
    """Heat a hit puts on the target (outside heat), or 0. roll_d6(n) rolls nD6."""
    n = cn(weapon)
    if "FLAMER" in n:
        return 1 if "ERFLAMER" in n else (weapon.damage_per_shot or 0)
    if "PLASMACANNON" in n:
        return roll_d6(2)
    if "PLASMARIFLE" in n:
        if "HEAVY" in n:
            return roll_d6(2)
        if "LIGHT" in n:
            return (roll_d6(1) + 1) // 2           # 1D3
        return roll_d6(1)
    return 0


def expected_target_heat(weapon):
    """Average heat a hit puts on the target (target_heat's expectation)."""
    n = cn(weapon)
    if "FLAMER" in n:
        return 1 if "ERFLAMER" in n else (weapon.damage_per_shot or 0)
    if "PLASMACANNON" in n or ("PLASMARIFLE" in n and "HEAVY" in n):
        return 7.0
    if "PLASMARIFLE" in n:
        return 2.0 if "LIGHT" in n else 3.5
    return 0.0


def heat_causing(weapon):
    return expected_target_heat(weapon) > 0


def mga_guns(mech, array):
    """The live machine guns `array` fires (attached by INTEGRATION__fire_modes)."""
    from damage_resolution import get_weapons
    live = {id(w) for w in get_weapons(mech)}
    return [g for g in getattr(array, "mga_guns", []) if id(g) in live]


def link_arrays(mech):
    """Once per battle: each machine gun array takes up to 4 machine guns of
    its type (light / standard / heavy) in its own location."""
    from equipment import Equipment
    seen = set()
    for loc, slots in mech.crits.items():
        arrays, guns = [], []
        for s in slots:
            if not isinstance(s, Equipment) or s.category != "weapon" or id(s) in seen:
                continue
            seen.add(id(s))
            if is_mga(s):
                arrays.append(s)
            elif "MACHINEGUN" in cn(s) or cn(s).endswith("MG"):
                guns.append(s)
        for a in arrays:
            kind = "LIGHT" if "LIGHT" in cn(a) or "LMGA" in cn(a) else ("HEAVY" if "HEAVY" in cn(a) or "HMGA" in cn(a) else "")
            mine = [g for g in guns if (kind in cn(g)) and not (kind == "" and ("LIGHT" in cn(g) or "HEAVY" in cn(g)))]
            a.mga_guns = mine[:MGA_MAX_GUNS]
            guns = [g for g in guns if g not in a.mga_guns]


def array_gun_ids(mech):
    """Machine guns fired by a live array (they can't fire on their own)."""
    from damage_resolution import get_weapons
    out = set()
    for w in get_weapons(mech):
        if is_mga(w):
            out |= {id(g) for g in getattr(w, "mga_guns", [])}
    return frozenset(out)
