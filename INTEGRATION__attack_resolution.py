"""
INTEGRATION__attack_resolution.py  (NEW 2026-10-18, Claude - Pile 2 resolution driven by Pile 3 geometry)

The Ranged Combat phase with real dice: the seam PROJECT_MAP Section 2
calls "the main seam this project exists to close" -
PATHFINDER los/combat (to-hit) -> MECHSIM hit_location/damage_resolution/
armor_rules (resolution).

Cannibalized from MECHSIM__sim_runner.py (per the 2026-08-30 Pile 1
reconciliation decision):
  - _resolve_hit()           -> _resolve_hit() here, unchanged logic, except
                                the hit-table side comes from
                                attack_side() (Core p.73 attack direction)
                                instead of config.FACING (the TAC re-roll
                                uses the same side as the original hit).
  - resolve_weapon_attack()  -> _resolve_one_attack() here. To-hit number now
                                comes from real geometry instead of
                                config.GUNNERY + to_hit_modifier + tmm; weapon
                                data comes from the parsed Equipment instance
                                instead of a hand-written ATTACK_TABLE row.
sim_runner.py itself is not imported.

=== SEQUENCE (PROJECT_MAP Section 2 step 4) ===
"Loser fires first, winner second; effects resolve simultaneously."
  1. snapshot_round_capability + snapshot_pre_attack_phase for both mechs.
  2. DECLARE both sides' attacks from the pre-damage state: LOS, rear-arc
     firing block, to-hit number, weapon selection (heat-constrained
     knapsack, INTEGRATION__weapon_selection - budget = max_heat +
     dissipation - current heat - this turn's movement heat - engine
     heat, Daniel 2026-10-18), and the to-hit roll for each
     chosen weapon. Because both declare before any damage lands, a mech
     destroyed this phase still gets its shots off (simultaneous).
  3. APPLY: loser's hits land first, then winner's (only matters for log
     order and crit-slot state, not for who gets to fire).
  4. Attack Phase PSR + consciousness checks for both (MECHSIM, real).

=== TO-HIT NUMBER ===
TN = gunnery + AMM(attacker's actual movement mode)
              + TMM(target's actual hexes moved; +1 if it jumped)
              + LOS modifier (woods/partial cover) + range bracket
              + attacker's heat modifier (2026-10-19, Heat Scale: +1 at 8,
                +2 at 13, +3 at 17, +4 at 24 - INTEGRATION__heat)
All pieces but heat are Daniel-confirmed PATHFINDER rules; heat is Core
Rulebook p.104. TMM uses ACTUAL hexes
moved (combat.fc_to_tmm), per Daniel 2026-10-18 - MECHSIM's
compute_tmm() (max available MP) is NOT used here.
Exception: an immobile target (whole crew unconscious, or shut down -
mech_state.is_immobile) uses MECHSIM's existing "TMM -4" convention
(piloting_rolls.resolve_movement_phase).
A shut-down attacker makes no attacks (Core Rulebook p.104).
The range term includes the minimum-range penalty (2026-10-19,
weapon_selection._weapon_range_mod).
Also (2026-10-19, replacing stub_to_hit_modifiers_not_applied):
  - each weapon's own modifier (INTEGRATION__weapon_rules: pulse -2, ER pulse
    -1, heavy laser +1, rocket launcher +1, ...) and a targeting computer's
    -1 for eligible weapons (p.200);
  - arm critical hits (p.97-98): shoulder +4 for that arm's weapons
    (overriding its other arm crits), upper arm actuator +1;
  - sensor hits (p.98): one +2, two = no ranged attacks (torso-mounted
    cockpit p.203: +2, +4, then none);
  - prone target (p.66): -2 from an adjacent hex, +1 otherwise;
  - firing while prone (p.67): +2, propped on the arm whose weapons matter
    least - nothing fires from that arm or the legs; no arm left = no fire.
    Tripods with no leg / hip damage +1 and only lose leg weapons; quads with
    none fire as if standing, damaged quads prop on a leg (p.231).

Stealth (2026-10-19, INTEGRATION__equipment_systems, Core pp.202, 209):
a target's active LPS / Null-Signature / stealth armor add +1 at medium and
+2 at long range to each weapon's TN; its Void-Signature System adds +3 to
+0 by how far it moved; the attacker's own Void-Signature adds +1.

AIMED SHOTS (2026-10-19, Core p.70): against an immobile target, every
eligible weapon (not Cluster / Area-Effect - so no LRM/SRM racks) aims at
config.AIMED_SHOT_LOCATION. Aiming at the head drops the -4 immobile
modifier and adds +3 instead; partial cover's modifier doesn't apply to an
aimed shot, legs can't be aimed at behind it, and a missed aim that rolls
a leg rerolls. A hit then rolls 1D6: 4+ strikes the aimed location,
otherwise the normal hit-location roll.

For weapon SELECTION the pre-range TN is clamped into
weapon_selection's table bounds (0-16); the actual to-hit ROLL uses the
real, unclamped TN.
"""

from dataclasses import dataclass, field
from typing import List, Optional

import INTEGRATION__config as config
import INTEGRATION__stubs as stubs
import INTEGRATION__weapon_selection as weapon_selection
import INTEGRATION__heat as heat
import INTEGRATION__equipment_systems as equip
import INTEGRATION__weapon_rules as weapon_rules
from mech_state import DamageType, ArmorType, is_immobile, snapshot_round_capability, \
    mark_consciousness_check_pending, compute_heat_dissipation
import armor_rules
from hit_location import resolve_hit_location
from damage_resolution import apply_damage, check_critical, cluster_hits_count, get_weapons
import piloting_rolls

import hex_geometry
import combat
from los import has_los, hex_distance, trace_los_path

# equipment.json damage_type strings -> MECHSIM DamageType. A name mapping,
# not a rule. Anything else (incl. null) goes through stub_unknown_damage_type.
DAMAGE_TYPE_BY_NAME = {
    "Energy": DamageType.ENERGY,
    "Ballistic": DamageType.BALLISTIC,
    "Missile": DamageType.MISSILE,
}

IMMOBILE_TMM = -4  # MECHSIM piloting_rolls.resolve_movement_phase convention (immobile target)
AIMED_HEAD_ADJUST = -IMMOBILE_TMM + 3  # p.70: head shots drop the -4 and take +3 instead
AIMED_SHOT_SUCCESS = 4                 # 1D6 4+ hits the aimed location


@dataclass
class DeclaredAttack:
    weapon: object
    tn: int
    roll: int
    hit: bool
    side: str = "front"              # hit table: attack direction (attack_side)
    aimed_at: Optional[str] = None   # aimed-shot location (immobile target)
    cover: bool = False              # target in partial cover (aimed-shot leg rerolls)


@dataclass
class SideReport:
    """What one mech did this phase - feeds BattleResult totals."""
    attacks: int = 0
    hits: int = 0
    damage_dealt: float = 0.0
    weapon_heat: int = 0
    attacks_list: List[DeclaredAttack] = field(default_factory=list)


def total_hp(mech):
    """Daniel's HP scalar (PROJECT_MAP Section 5): armor + rear armor + structure."""
    return sum(v.get("armor", 0) + v.get("rear_armor", 0) + v.get("structure", 0)
               for v in mech.locations.values())


def _with_piloting(mech, fn, *args, **kwargs):
    """piloting_rolls.py reads one global config.PILOTING; set it to this
    mech's own skill for the duration of the call (no MECHSIM edit)."""
    saved = config.PILOTING
    config.PILOTING = mech.piloting
    try:
        return fn(mech, *args, **kwargs)
    finally:
        config.PILOTING = saved


def _target_tmm(target):
    if is_immobile(target):
        return IMMOBILE_TMM
    return combat.fc_to_tmm(target.move_fc, jumped=(target.move_mode == "Jump"))


_SIDE_BY_RELATIVE_HEXSIDE = {0: "front", 1: "right", 2: "right", 3: "rear", 4: "left", 5: "left"}


def attack_side(a_hex, t_hex, target_facing, terrain_map):
    """Attack direction (Core p.73): the hexside of the target's hex that
    the line of sight crosses, read against the target's facing (a prone
    mech uses the same facing). Front and rear hit zones are one hexside
    each, the sides two each (Attack Direction Diagram). A line exactly on
    a border uses the hex the LOS rules chose (los.trace_los_path)."""
    steps = trace_los_path(a_hex, t_hex, terrain_map).steps
    entry = steps[-2].hex                      # the hex the line enters the target's hex from
    relative = (combat._direction_facing(t_hex, entry) - target_facing) % 6
    return _SIDE_BY_RELATIVE_HEXSIDE[relative]


def is_cluster_weapon(weapon):
    """Rolls on the Cluster Hits Table (INTEGRATION__weapon_rules)."""
    return weapon_rules.is_cluster(weapon)


def aimed_shot_location(target, partial_cover=False):
    """Where aimed shots at `target` go this phase (p.70), or None: only at
    an immobile target, only if config.AIMED_SHOT_LOCATION names one of its
    live locations, and not at a leg behind partial cover."""
    loc = config.AIMED_SHOT_LOCATION
    if loc is None or not is_immobile(target) or loc not in target.locations:
        return None
    if target.locations[loc]["destroyed"] or (partial_cover and loc in target.leg_locations):
        return None
    return loc


def aimed_tn_adjust(aim, cover_modifier):
    """TN change for an aimed shot: no partial-cover modifier; head +7."""
    return -cover_modifier + (AIMED_HEAD_ADJUST if aim == "Head" else 0)


# --- Attacker / target conditions (2026-10-19) --------------------------------
ARM_LOCATIONS = ("Left Arm", "Right Arm")
SENSOR_MODIFIER_BY_HITS = {0: 0, 1: 2}                    # p.98; 2+ hits: no ranged attacks
TORSO_COCKPIT_SENSOR_MODIFIER_BY_HITS = {0: 0, 1: 2, 2: 4}  # p.203; 3+ hits: none
PRONE_FIRE_MODIFIER = 2                                   # p.67
TRIPOD_PRONE_FIRE_MODIFIER = 1                            # p.231
PRONE_TARGET_ADJACENT = -2                                # p.66
PRONE_TARGET_FAR = 1


def weapon_locations(mech):
    """{id(weapon): set of locations its slots sit in} - live and destroyed slots."""
    locs = {}
    for location, slots in mech.crits.items():
        for slot in slots:
            if getattr(slot, "category", None) == "weapon":
                locs.setdefault(id(slot), set()).add(location)
    for (location, _), info in mech.destroyed_slot_info.items():
        if info["instance_id"] is not None:
            locs.setdefault(info["instance_id"], set()).add(location)
    return locs


def _destroyed_names(mech, location=None):
    return [info["name"] for (loc, _), info in mech.destroyed_slot_info.items()
            if location is None or loc == location]


def sensor_modifier(mech):
    """Ranged-attack TN modifier from sensor hits, or None if they can't fire."""
    hits = _destroyed_names(mech).count("Sensors")
    table = TORSO_COCKPIT_SENSOR_MODIFIER_BY_HITS if getattr(mech, "torso_cockpit", False) \
        else SENSOR_MODIFIER_BY_HITS
    return table.get(hits)


def arm_actuator_modifier(mech, locations):
    """+4 for a weapon in an arm with a destroyed shoulder (overrides that
    arm's other crits), else +1 for a destroyed upper arm actuator."""
    worst = 0
    for arm in set(locations) & set(ARM_LOCATIONS):
        lost = _destroyed_names(mech, arm)
        worst = max(worst, 4 if "Shoulder" in lost else (1 if "Upper Arm Actuator" in lost else 0))
    return worst


def has_targeting_computer(mech):
    dead = {info["instance_id"] for info in mech.destroyed_slot_info.values()}
    return any(getattr(s, "name", "").replace(" ", "").upper().endswith("TARGETINGCOMPUTER") and id(s) not in dead
               for slots in mech.crits.values() for s in slots)


def prone_target_modifier(target, distance):
    if not target.prone:
        return 0
    return PRONE_TARGET_ADJACENT if distance <= 1 else PRONE_TARGET_FAR


def _weapon_value(weapon):
    return (weapon.damage_per_shot or 0) * (weapon.rack_size or 1)


def prone_fire(mech):
    """(TN modifier, ids of weapons that can't fire), or None if a prone mech
    can't fire at all (p.67, p.231). (0, empty) when standing."""
    if not mech.prone:
        return 0, frozenset()
    locs = weapon_locations(mech)
    weapons = get_weapons(mech)
    in_loc = lambda place: {id(w) for w in weapons if place & locs.get(id(w), set())}   # noqa: E731
    legs = set(mech.leg_locations)
    legs_ok = not mech.destroyed_hip_locations and not any(mech.locations[l]["destroyed"] for l in legs)
    if mech.mech_type in ("quad", "quadvee"):
        if legs_ok:
            return 0, frozenset()
        usable = [l for l in legs if not mech.locations[l]["destroyed"]]
        prop = min(usable, key=lambda l: sum(_weapon_value(w) for w in weapons if id(w) in in_loc({l})))
        return PRONE_FIRE_MODIFIER, frozenset(in_loc({prop}))
    if mech.mech_type == "tripod" and legs_ok:
        return TRIPOD_PRONE_FIRE_MODIFIER, frozenset(in_loc(legs))
    arms = [a for a in ARM_LOCATIONS if a in mech.locations and not mech.locations[a]["destroyed"]]
    if not arms:
        return None
    prop = min(arms, key=lambda a: sum(_weapon_value(w) for w in weapons if id(w) in in_loc({a})))
    return PRONE_FIRE_MODIFIER, frozenset(in_loc(legs | {prop}))


def firing_conditions(attacker):
    """Attacker-side ranged conditions: (TN modifier, unavailable weapon ids,
    note), or None if it can't make ranged attacks this turn."""
    sensors = sensor_modifier(attacker)
    prone = prone_fire(attacker)
    if sensors is None or prone is None:
        return None
    note = []
    if sensors:
        note.append(f"sensors +{sensors}")
    if prone[0] or prone[1]:
        note.append(f"prone +{prone[0]}")
    return sensors + prone[0], prone[1], ", ".join(note)


def tn_adjuster(attacker, target, aim=None, cover_modifier=0):
    """f(weapon, bracket) -> per-weapon TN change for select_weapons_to_fire:
    the weapon's own modifier, targeting computer, arm crits, the target's
    range-stealth bonus, and the aimed-shot change for weapons that can aim."""
    stealth = equip.range_stealth_bonus(target)
    aim_adjust = aimed_tn_adjust(aim, cover_modifier) if aim else 0
    tc = has_targeting_computer(attacker)
    locs = weapon_locations(attacker)

    def adjust(weapon, bracket):
        tn = stealth.get(bracket, 0) if bracket else 0
        tn += weapon_rules.weapon_tn_modifier(weapon, bracket)
        tn += arm_actuator_modifier(attacker, locs.get(id(weapon), ()))
        aiming = aim and not is_cluster_weapon(weapon)
        if aiming:
            tn += aim_adjust
        # TC -1 (p.200): not on head shots, nor on a pulse weapon's aimed shot.
        if tc and weapon_rules.targeting_computer_eligible(weapon) and not (
                aiming and (aim == "Head" or weapon_rules.is_pulse(weapon))):
            tn -= 1
        return tn
    return adjust


def declare_attacks(attacker, target, terrain_map, report: SideReport):
    """Step 2 above for one attacker. Rolls to-hit for every selected
    weapon; returns nothing (fills report)."""
    a_name, t_name = attacker.side_name, target.side_name
    if attacker.shutdown:
        config.log(f"  [Ranged] {a_name}: shut down - no attacks.")
        return
    a_hex = hex_geometry.parse_hex_label(attacker.hex)
    t_hex = hex_geometry.parse_hex_label(target.hex)
    if a_hex == t_hex:
        config.log(f"  [Ranged] {a_name}: same hex as target - no attack (undefined).")
        return

    stubs.stub_unconfirmed_weapon_data(a_name, get_weapons(attacker))

    los = has_los(a_hex, t_hex, terrain_map)
    if not los.los:
        config.log(f"  [Ranged] {a_name}: no LOS to {t_name} - holds fire.")
        return
    if combat.in_rear_arc(a_hex, hex_geometry.compass_to_facing(attacker.facing), t_hex):
        config.log(f"  [Ranged] {a_name}: {t_name} is in its rear arc - can't fire (PATHFINDER rule).")
        return

    distance = hex_distance(a_hex, t_hex)
    amm = combat.MODE_TO_AMM[attacker.move_mode]
    tmm = _target_tmm(target)
    heat_mod = attacker.heat_fire_modifier
    stealth_mod = equip.void_signature_modifier(target) + equip.own_attack_modifier(attacker)
    conditions = firing_conditions(attacker)
    if conditions is None:
        config.log(f"  [Ranged] {a_name}: can't make ranged attacks (sensors destroyed, or prone with no arm to prop on).")
        return
    cond_mod, unavailable, cond_note = conditions
    prone_mod = prone_target_modifier(target, distance)
    other_mod = cond_mod + prone_mod
    pre_tn = attacker.gunnery + amm + tmm + los.modifier + heat_mod + stealth_mod + other_mod

    cover = 0
    aim = None
    if is_immobile(target) and config.AIMED_SHOT_LOCATION:
        cover = trace_los_path(a_hex, t_hex, terrain_map).steps[-1].partial_cover
        aim = aimed_shot_location(target, partial_cover=cover > 0)
    adjust = tn_adjuster(attacker, target, aim, cover)
    side = attack_side(a_hex, t_hex, hex_geometry.compass_to_facing(target.facing), terrain_map)

    sel_pre_tn = max(weapon_selection.PRE_TN_MIN, min(weapon_selection.PRE_TN_MAX, pre_tn))
    dissipation = compute_heat_dissipation(attacker)
    other = heat.other_heat(attacker)
    weapons, exp_dmg, weapon_heat = weapon_selection.select_weapons_to_fire(
        attacker, distance, sel_pre_tn, attacker.min_heat, attacker.max_heat,
        dissipation=dissipation, movement_heat=attacker.movement_heat, other_heat=other, tn_adjust=adjust,
        unavailable=unavailable)
    budget = heat.weapon_heat_budget(attacker, attacker.movement_heat)
    surcharge = heat.weapon_fire_surcharge(attacker) if weapons else 0

    config.log(f"  [Ranged] {a_name} -> {t_name}: range {distance}, base TN {pre_tn} "
               f"(gunnery {attacker.gunnery} + AMM {amm} [{attacker.move_mode}] + TMM {tmm} "
               f"+ LOS {los.modifier} + heat {heat_mod}{f' + stealth {stealth_mod}' if stealth_mod else ''}"
               f"{f' + {cond_note}' if cond_note else ''}{f' + prone target {prone_mod}' if prone_mod else ''}); "
               f"firing {[w.name for w in weapons] or 'nothing'}{f' (aimed at {aim})' if aim else ''} "
               f"(weapon heat {weapon_heat}{f' +{surcharge} damaged radical' if surcharge else ''} of budget "
               f"{budget} = max {attacker.max_heat} + sink {dissipation} - current {attacker.current_heat} "
               f"- movement {attacker.movement_heat} - other {other}; expected dmg {exp_dmg:.2f})")

    report.weapon_heat += weapon_heat + surcharge
    for w in weapons:
        if stubs.is_one_shot(w):
            stubs.stub_one_shot(a_name, w)  # no ammo bin - its own limit instead
        elif w.damage_type != "Energy" and (w.damage_per_shot or 0) > 0:
            stubs.stub_ammo(a_name, w)
        range_mod = weapon_selection._weapon_range_mod(w, distance)
        extra = adjust(w, weapon_selection.range_bracket(w, distance))
        w_aim = aim if aim and not is_cluster_weapon(w) else None
        tn = pre_tn + range_mod + extra
        roll = config.roll_2d6(prompt=f"To-hit roll ({w.name})")
        hit = roll >= tn
        config.log(f"    {w.name}: needs {tn} (range mod +{range_mod}"
                   f"{f', modifiers {extra:+d}' if extra else ''}){f' aimed at {w_aim}' if w_aim else ''}, "
                   f"rolled {roll} -> {'HIT' if hit else 'miss'}")
        if not hit and weapon_rules.is_streak(w):
            report.weapon_heat -= w.heat or 0        # a Streak that misses doesn't fire (p.187)
            config.log(f"      Streak missed - launcher doesn't fire: no heat.")
        report.attacks += 1
        report.attacks_list.append(DeclaredAttack(weapon=w, tn=tn, roll=roll, hit=hit, side=side,
                                                  aimed_at=w_aim, cover=cover > 0))


def _damage_type_for(weapon):
    dt = DAMAGE_TYPE_BY_NAME.get(weapon.damage_type)
    return dt if dt is not None else stubs.stub_unknown_damage_type(weapon)


def _resolve_hit(target, damage, damage_type, side, tag="", reroll_legs=False):
    """Cannibalized from MECHSIM__sim_runner._resolve_hit() - same logic:
    hit-location roll, head-hit pilot damage, floating TAC on a 2, then
    apply_damage(). Only change: `side` is passed in (attack_side) rather
    than read from config.FACING."""
    armor_field = "rear_armor" if side == "rear" else "armor"
    loc_roll = config.roll_2d6(prompt=f"{tag}Hit location roll")
    loc = resolve_hit_location(loc_roll, target, side)
    config.log(f"      {tag}Hit location roll {loc_roll} ({side} table): {loc}.")
    while reroll_legs and loc in target.leg_locations:   # aimed shot behind partial cover (p.70)
        loc_roll = config.roll_2d6(prompt=f"{tag}Hit location re-roll (legs in cover)")
        loc = resolve_hit_location(loc_roll, target, side)
        config.log(f"      {tag}Legs behind partial cover - re-rolled {loc_roll}: {loc}.")

    if loc == "Head":
        target.pilot_hits += 1
        mark_consciousness_check_pending(target)
        config.log(f"      Head hit - pilot takes 1 hit ({target.pilot_hits}/6), regardless of armor.")

    if loc_roll == 2 and not target.locations[loc]["destroyed"]:
        config.log("      Roll of 2 - Through-Armor Critical (floating) triggered.")
        tac_side = side
        tac_loc_roll = config.roll_2d6(prompt="  TAC (Through-Armor Critical) location roll")
        tac_loc = resolve_hit_location(tac_loc_roll, target, tac_side)
        tac_armor_field = "rear_armor" if tac_side == "rear" else "armor"
        config.log(f"      Floating TAC re-roll: {tac_loc_roll} -> {tac_loc}")
        apply_damage(target, tac_loc, damage, armor_field=tac_armor_field, damage_type=damage_type)
        config.log("      Additional critical hit due to TAC.")
        tac_loc_state = target.locations[tac_loc]
        tac_armor_key = tac_armor_field if tac_armor_field in tac_loc_state else "armor"
        tac_armor_type = ArmorType.STANDARD if damage_type == DamageType.REENGINEERED \
            else target.armor_type.get(tac_loc, ArmorType.STANDARD)
        modifier = armor_rules.crit_roll_modifier(
            target.structure_type, tac_armor_type, armor_present=tac_loc_state[tac_armor_key] > 0)
        check_critical(target, tac_loc, location_destroyed=False, modifier=modifier)
        return

    apply_damage(target, loc, damage, armor_field=armor_field, damage_type=damage_type)


def _resolve_one_attack(attacker, target, attack: DeclaredAttack, battle_rng):
    """Cannibalized from MECHSIM__sim_runner.resolve_weapon_attack() (the
    post-to-hit half): one hit for a flat weapon, or a cluster roll and one
    _resolve_hit per damage group for a cluster weapon. Cluster detection
    matches INTEGRATION__expected_damage: damage_type == "Missile" with a
    rack_size (LB-X/Ultra/Rotary are flat single hits for now - documented
    gap there)."""
    w = attack.weapon
    if not w.damage_per_shot:
        config.log(f"    {w.name} hit - zero damage weapon, no damage resolution.")
        return
    side = attack.side
    dtype = _damage_type_for(w)
    if attack.aimed_at:
        _resolve_aimed_hit(target, w, dtype, side, attack)
        return
    if not is_cluster_weapon(w):
        config.log(f"    {w.name} hit for {w.damage_per_shot}:")
        _resolve_hit(target, w.damage_per_shot, dtype, side)
        return
    if weapon_rules.is_streak(w):
        hits = w.rack_size                    # Streak: Cluster result is automatically 12 (p.187)
        config.log(f"    {w.name} hit: Streak - all {hits} missiles hit ({hits * w.damage_per_shot} dmg).")
    else:
        raw = config.roll_2d6(prompt=f"Cluster hits roll ({w.name})")
        mod = weapon_rules.cluster_roll_modifier(w)
        cluster_roll = max(2, min(12, raw + mod))     # p.74: results clamp to 2-12
        hits = cluster_hits_count(w.rack_size, cluster_roll)
        config.log(f"    {w.name} hit: cluster roll {raw}{f' {mod:+d}' if mod else ''} on the "
                   f"{w.rack_size}-column table -> {hits} connect ({hits * w.damage_per_shot} dmg).")
    total = hits * w.damage_per_shot
    groups = weapon_rules.damage_groupings(w, total)
    for i, dmg in enumerate(groups, start=1):
        _resolve_hit(target, dmg, dtype, side, tag=f"Group {i}/{len(groups)}: ")


def _resolve_aimed_hit(target, weapon, dtype, side, attack):
    """p.70: 1D6 4+ puts the hit on the aimed location; otherwise roll
    normally (re-rolling legs behind partial cover)."""
    die = config.pick_number(6, prompt="Aimed shot 1D6")
    if die < AIMED_SHOT_SUCCESS:
        config.log(f"    {weapon.name} hit for {weapon.damage_per_shot}: aimed at {attack.aimed_at}, "
                   f"1D6 {die} - rolls for location.")
        _resolve_hit(target, weapon.damage_per_shot, dtype, side, reroll_legs=attack.cover)
        return
    config.log(f"    {weapon.name} hit for {weapon.damage_per_shot}: aimed at {attack.aimed_at}, 1D6 {die} - on target.")
    loc = attack.aimed_at
    if loc == "Head":
        target.pilot_hits += 1
        mark_consciousness_check_pending(target)
        config.log(f"      Head hit - pilot takes 1 hit ({target.pilot_hits}/6), regardless of armor.")
    apply_damage(target, loc, weapon.damage_per_shot,
                 armor_field="rear_armor" if side == "rear" else "armor", damage_type=dtype)


def run_ranged_combat_phase(mover_first, mover_second, terrain_map, battle_rng):
    """Whole phase, per the SEQUENCE in the module docstring. Returns
    {side_name: SideReport}."""
    reports = {mover_first.side_name: SideReport(), mover_second.side_name: SideReport()}
    pairs = ((mover_first, mover_second), (mover_second, mover_first))

    for m in (mover_first, mover_second):
        snapshot_round_capability(m)
        piloting_rolls.snapshot_pre_attack_phase(m)

    for attacker, target in pairs:
        declare_attacks(attacker, target, terrain_map, reports[attacker.side_name])

    for attacker, target in pairs:
        rep = reports[attacker.side_name]
        hp_before = total_hp(target)
        for attack in rep.attacks_list:
            if attack.hit:
                rep.hits += 1
                _resolve_one_attack(attacker, target, attack, battle_rng)
        rep.damage_dealt += hp_before - total_hp(target)

    for m in (mover_first, mover_second):
        _with_piloting(m, piloting_rolls.resolve_attack_phase_psr)
        piloting_rolls.resolve_consciousness_checks(m, "Attack Phase")

    return reports
