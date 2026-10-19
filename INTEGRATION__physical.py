"""
INTEGRATION__physical.py  (NEW 2026-10-19, Claude - Pile 2 rules, Pile 4 choice)

The Physical Attack Phase (Core Rulebook pp.76-83), replacing the
physical_combat stub: punches, kicks and physical weapons (claws, hatchet,
lance, mace, retractable blade, sword, vibroblades - treated as switched
off, talons on kicks). Charges, death-from-above, pushes and clubs are not
built (see results.KNOWN_MISSING_RULES).

  - Who (p.76-77): an adjacent target; a standing, powered, conscious
    attacker; one attack type per turn (both arms may punch). Prone mechs
    can't make physical attacks.
  - Arcs: for an adjacent target the arcs are the hexsides - forward = the
    front hexside and the two beside it, the rear-side hexsides are the side
    arcs, the back hexside is the rear (consistent with the rear-arc rule).
    Kicks: forward only. Punches / arm weapons: forward or that arm's side.
  - Weapons fired this turn from an arm (or the kicking leg) stop that limb
    attacking (pp.79, 81-82).
  - To-hit (p.76): Piloting + attack modifier (punch / kick -1, weapons per
    the p.81 table) + AMM + TMM + terrain + prone target / immobile; never
    heat or sensors. Actuators (pp.81-82): punch - hand +1, lower / upper
    arm +2 each and half damage, shoulder = no punch; kick - foot +1, lower /
    upper leg +2 each and half damage (any leg), a hip hit = no kicks;
    weapons - lower / upper arm +2, a destroyed hand or shoulder = no attack.
  - Damage: punch 1 per 10 tons (round up), kick 1 per 5 tons, weapons per
    the p.81 table (round up); TSM doubles (p.205); talons x1.5 on kicks.
    One grouping each. Tables: punches on the Punch table, kicks on the Kick
    table, weapons on the standard table - by attack direction (p.73).
  - Levels (p.77): within one level only. Standing target one level up:
    punch / weapon only, on the Kick table; one level down: kick / weapon on
    the Punch table. Prone target: kick / weapon (not claws) on the standard
    table at the same level, punch / weapon one level up.
  - All attacks are declared and rolled, then damage lands (p.83). A kicked
    mech, and one that missed a kick, makes a PSR (+0) at the end of the
    phase, joined to the phase's damage PSR (piloting_rolls).

Bot choice (pile 4): the attack type with the most expected damage.
"""

import math

import INTEGRATION__config as config
import INTEGRATION__attack_resolution as attack_resolution
from mech_state import DamageType, is_destroyed, is_immobile, mark_consciousness_check_pending
from equipment import Equipment
from damage_resolution import apply_damage
from hit_location import resolve_hit_location
import piloting_rolls
import hex_geometry
import combat
from los import has_los, hex_distance

ARMS = ("Left Arm", "Right Arm")
FORWARD_HEXSIDES = {5, 0, 1}
SIDE_ARC_HEXSIDE = {"Right Arm": 2, "Left Arm": 4}
PUNCH_MOD = -1
KICK_MOD = -1

KICK_TABLE = {"left": ("Left Leg", "Left Leg"), "front": ("Right Leg", "Left Leg"),
              "rear": ("Right Leg", "Left Leg"), "right": ("Right Leg", "Right Leg")}        # (1-3, 4-6), p.81
PUNCH_TABLE = {
    "left": ("Left Torso", "Left Torso", "Center Torso", "Left Arm", "Left Arm", "Head"),
    "front": ("Right Arm", "Right Torso", "Center Torso", "Left Torso", "Left Arm", "Head"),
    "rear": ("Right Arm", "Right Torso", "Center Torso", "Left Torso", "Left Arm", "Head"),
    "right": ("Right Torso", "Right Torso", "Center Torso", "Right Arm", "Right Arm", "Head"),
}

# Physical Weapon Attacks Table, p.81: name fragment -> (TN modifier, tons per point, +damage, table)
PHYSICAL_WEAPONS = (
    ("CLAW", (0, 7, 0, "punch")),
    ("HATCHET", (-1, 5, 0, "standard")),
    ("LANCE", (1, 5, 0, "standard")),
    ("MACE", (1, 4, 0, "standard")),
    ("RETRACTABLEBLADE", (-2, 10, 0, "standard")),
    ("SWORD", (-2, 10, 1, "standard")),
    ("VIBROBLADE", (-2, 10, 1, "standard")),      # switched off (activation not modeled)
)


def _norm(name):
    return (name or "").replace(" ", "").replace("-", "").upper()


def _weapon_kind(slot):
    if not isinstance(slot, Equipment):
        return None
    n = _norm(slot.name)
    return next((spec for frag, spec in PHYSICAL_WEAPONS if frag in n), None)


# =============================================================================
# ==========================  LIMB STATE  =====================================
# =============================================================================
def _has_part(mech, loc, part):
    """The design has this actuator in that location (live or destroyed)."""
    return part in mech.crits.get(loc, []) or any(
        l == loc and info["name"] == part for (l, _), info in mech.destroyed_slot_info.items())


def _lost(mech, loc, part):
    return any(l == loc and info["name"] == part for (l, _), info in mech.destroyed_slot_info.items())


def _limb_fired(mech, loc, fired_ids):
    locs = attack_resolution.weapon_locations(mech)
    return any(loc in locs.get(wid, ()) for wid in fired_ids)


def _relative_hexside(a_hex, a_facing, t_hex):
    return (combat._direction_facing(a_hex, t_hex) - hex_geometry.compass_to_facing(a_facing)) % 6


def _arm_can_reach(arm, rel):
    return rel in FORWARD_HEXSIDES or rel == SIDE_ARC_HEXSIDE[arm]


def _strength(mech, per_tons, plus=0):
    dmg = math.ceil(mech.mass / per_tons) + plus
    return dmg * (2 if getattr(mech, "tsm_active", False) else 1)


# =============================================================================
# ==========================  OPTIONS  ========================================
# =============================================================================
def _punch_options(m, rel, fired, table):
    out = []
    for arm in ARMS:
        if arm not in m.locations or m.locations[arm]["destroyed"] or not _arm_can_reach(arm, rel):
            continue
        if _lost(m, arm, "Shoulder") or _limb_fired(m, arm, fired):
            continue
        claw = next((s for s in m.crits[arm] if _weapon_kind(s) and _weapon_kind(s)[3] == "punch"), None)
        mod, dmg, halves = (0, _strength(m, 7), 0) if claw else (PUNCH_MOD, _strength(m, 10), 0)
        if not claw and (not _has_part(m, arm, "Hand Actuator") or _lost(m, arm, "Hand Actuator")):
            mod += 1
        for part in ("Lower Arm Actuator", "Upper Arm Actuator"):
            if (part == "Lower Arm Actuator" and not _has_part(m, arm, part)) or _lost(m, arm, part):
                mod += 2
                halves += 1
        out.append(dict(name=f"{'claw' if claw else 'punch'} ({arm})", mod=mod, damage=dmg // (2 ** halves),
                        table="punch" if table is None else table))
    return out


def _kick_options(m, rel, fired, table):
    if rel not in FORWARD_HEXSIDES or m.destroyed_hip_locations:
        return []
    legs = [l for l in m.leg_locations if not m.locations[l]["destroyed"]]
    if len(legs) < len(m.leg_locations):
        return []
    mod, halves = KICK_MOD, 0
    for leg in m.leg_locations:                      # actuator effects from either leg apply (p.81)
        if _lost(m, leg, "Foot Actuator"):
            mod += 1
        for part in ("Lower Leg Actuator", "Upper Leg Actuator"):
            if _lost(m, leg, part):
                mod += 2
                halves += 1
    out = []
    for leg in legs:
        if _limb_fired(m, leg, fired):
            continue
        dmg = _strength(m, 5) // (2 ** halves)
        if any(_norm(getattr(s, "name", "")) == "TALONS" for s in m.crits[leg]):
            dmg = round(dmg * 1.5)
        out.append(dict(name=f"kick ({leg})", mod=mod, damage=dmg, table="kick" if table is None else table,
                        kick=True))
    return out


def _weapon_options(m, rel, fired, table, target_prone):
    out = []
    for arm in ARMS:
        if arm not in m.locations or m.locations[arm]["destroyed"] or not _arm_can_reach(arm, rel):
            continue
        if _lost(m, arm, "Shoulder") or _limb_fired(m, arm, fired):
            continue
        for slot in {id(s): s for s in m.crits[arm] if _weapon_kind(s)}.values():
            tn_mod, per, plus, wtable = _weapon_kind(slot)
            if wtable == "punch":
                continue                                # claws are punches
            if _lost(m, arm, "Hand Actuator") and "RETRACTABLEBLADE" not in _norm(slot.name):
                continue
            mod = tn_mod + sum(2 for part in ("Lower Arm Actuator", "Upper Arm Actuator")
                               if (part == "Lower Arm Actuator" and not _has_part(m, arm, part)) or _lost(m, arm, part))
            out.append(dict(name=f"{slot.name} ({arm})", mod=mod, damage=_strength(m, per, plus),
                            table="standard" if table is None else table))
    return out


def attack_options(attacker, target, terrain_map):
    """{"type": [option, ...]} the attacker could make this phase (one type
    is then chosen). Empty when no physical attack is possible."""
    if attacker.prone or is_immobile(attacker) or is_destroyed(attacker) or is_destroyed(target):
        return {}
    a_hex, t_hex = hex_geometry.parse_hex_label(attacker.hex), hex_geometry.parse_hex_label(target.hex)
    if hex_distance(a_hex, t_hex) != 1:
        return {}
    a_level = terrain_map["hexes"][attacker.hex]["level"]
    t_level = terrain_map["hexes"][target.hex]["level"]
    diff = t_level - a_level
    if abs(diff) > 1:
        return {}
    rel = _relative_hexside(a_hex, attacker.facing, t_hex)
    fired = getattr(attacker, "weapons_fired_this_turn", frozenset())
    opts = {}
    if target.prone:
        if diff == 0:
            opts["kick"] = _kick_options(attacker, rel, fired, "standard")
            opts["weapon"] = _weapon_options(attacker, rel, fired, None, True)
        elif diff == 1:
            opts["punch"] = _punch_options(attacker, rel, fired, None)
            opts["weapon"] = _weapon_options(attacker, rel, fired, None, True)
    elif diff == 0:
        opts["punch"] = _punch_options(attacker, rel, fired, None)
        opts["kick"] = _kick_options(attacker, rel, fired, None)
        opts["weapon"] = _weapon_options(attacker, rel, fired, None, False)
    elif diff == 1:
        opts["punch"] = _punch_options(attacker, rel, fired, "kick")
        opts["weapon"] = _weapon_options(attacker, rel, fired, "kick", False)
    else:
        opts["kick"] = _kick_options(attacker, rel, fired, "punch")
        opts["weapon"] = _weapon_options(attacker, rel, fired, "punch", False)
    return {k: v for k, v in opts.items() if v}


def _base_tn(attacker, target, terrain_map):
    a_hex, t_hex = hex_geometry.parse_hex_label(attacker.hex), hex_geometry.parse_hex_label(target.hex)
    return (attacker.piloting + combat.MODE_TO_AMM[attacker.move_mode] + attack_resolution._target_tmm(target)
            + has_los(a_hex, t_hex, terrain_map).modifier + attack_resolution.prone_target_modifier(target, 1))


def choose_attack(attacker, target, terrain_map):
    """Pile 4: the attack type (all of its options - e.g. both punches) with
    the most expected damage. Returns (base TN, [options]) or None."""
    options = attack_options(attacker, target, terrain_map)
    if not options:
        return None
    base = _base_tn(attacker, target, terrain_map)
    value = lambda opts: sum(combat.hit_probability(base + o["mod"]) * o["damage"] for o in opts)  # noqa: E731
    kind = max(options, key=lambda k: value(options[k] if k == "punch" else [max(options[k], key=lambda o: value([o]))]))
    picks = options[kind] if kind == "punch" else [max(options[kind], key=lambda o: value([o]))]
    return (base, picks) if value(picks) > 0 else None


# =============================================================================
# ==========================  PHASE  ==========================================
# =============================================================================
def _location(table, side, target):
    if table == "standard":
        return resolve_hit_location(config.roll_2d6(prompt="Physical hit location"), target, side)
    die = config.pick_number(6, prompt=f"{table} location (1D6)")
    if table == "kick":
        loc = KICK_TABLE[side][0 if die <= 3 else 1]
    else:
        loc = PUNCH_TABLE[side][die - 1]
    if target.mech_type in ("quad", "quadvee"):
        quad = {"Left Arm": "Front Left Leg", "Right Arm": "Front Right Leg",
                "Left Leg": "Rear Left Leg" if side == "rear" else "Front Left Leg",
                "Right Leg": "Rear Right Leg" if side == "rear" else "Front Right Leg"}
        loc = quad.get(loc, loc)
    return loc


def run_physical_phase(mech_a, mech_b, terrain_map, reports):
    """Both mechs declare and roll, then the damage lands, then PSRs and
    consciousness checks (p.83)."""
    for m in (mech_a, mech_b):
        rep = reports.get(m.side_name)
        m.weapons_fired_this_turn = frozenset(id(x.weapon) for x in rep.attacks_list) if rep else frozenset()
        piloting_rolls.snapshot_pre_attack_phase(m)
    declared = []
    for attacker, target in ((mech_a, mech_b), (mech_b, mech_a)):
        choice = choose_attack(attacker, target, terrain_map)
        if choice is None:
            continue
        base, picks = choice
        side = attack_resolution.attack_side(hex_geometry.parse_hex_label(attacker.hex),
                                             hex_geometry.parse_hex_label(target.hex),
                                             hex_geometry.compass_to_facing(target.facing), terrain_map)
        for o in picks:
            tn = base + o["mod"]
            roll = config.roll_2d6(prompt=f"Physical attack roll ({o['name']})")
            hit = roll >= tn
            config.log(f"  [Physical] {attacker.side_name} -> {target.side_name}: {o['name']} needs {tn} "
                       f"(piloting {attacker.piloting} + base {base - attacker.piloting} + attack {o['mod']:+d}), "
                       f"rolled {roll} -> {'HIT' if hit else 'miss'} ({o['damage']} dmg, {side} side)")
            declared.append((attacker, target, o, hit, side))
    triggers = {mech_a.side_name: [], mech_b.side_name: []}
    for attacker, target, o, hit, side in declared:
        if hit:
            loc = _location(o["table"], side, target)
            config.log(f"    {o['name']} hits {target.side_name}'s {loc} for {o['damage']}.")
            if loc == "Head":
                target.pilot_hits += 1
                mark_consciousness_check_pending(target)
            apply_damage(target, loc, o["damage"], armor_field="rear_armor" if side == "rear" else "armor",
                         damage_type=DamageType.PHYSICAL)
            if o.get("kick"):
                triggers[target.side_name].append(("kicked", 0))
        elif o.get("kick"):
            triggers[attacker.side_name].append(("missed a kick", 0))
    for m in (mech_a, mech_b):
        attack_resolution._with_piloting(m, piloting_rolls.resolve_attack_phase_psr,
                                         forced_triggers=tuple(triggers[m.side_name]))
        piloting_rolls.resolve_consciousness_checks(m, "Physical Attack Phase")
