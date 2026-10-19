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
                                stubs.stub_attack_direction() instead of
                                config.FACING (the TAC re-roll uses the same
                                side as the original hit - sim_runner's own
                                non-"random" branch).
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
Anything else (prone, sensor hits, arm actuators...) is not applied
- stubs.stub_to_hit_modifiers_not_applied() says so out loud.

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
from mech_state import DamageType, ArmorType, is_immobile, snapshot_round_capability, \
    mark_consciousness_check_pending, compute_heat_dissipation
import armor_rules
from hit_location import resolve_hit_location
from damage_resolution import apply_damage, check_critical, cluster_hits_count, get_weapons
import piloting_rolls

import hex_geometry
import combat
from los import has_los, hex_distance

# equipment.json damage_type strings -> MECHSIM DamageType. A name mapping,
# not a rule. Anything else (incl. null) goes through stub_unknown_damage_type.
DAMAGE_TYPE_BY_NAME = {
    "Energy": DamageType.ENERGY,
    "Ballistic": DamageType.BALLISTIC,
    "Missile": DamageType.MISSILE,
}

IMMOBILE_TMM = -4  # MECHSIM piloting_rolls.resolve_movement_phase convention (immobile target)


@dataclass
class DeclaredAttack:
    weapon: object
    tn: int
    roll: int
    hit: bool


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
    pre_tn = attacker.gunnery + amm + tmm + los.modifier + heat_mod
    stubs.stub_to_hit_modifiers_not_applied(attacker, target, a_name, t_name)

    sel_pre_tn = max(weapon_selection.PRE_TN_MIN, min(weapon_selection.PRE_TN_MAX, pre_tn))
    dissipation = compute_heat_dissipation(attacker)
    eng_heat = heat.engine_heat(attacker)
    weapons, exp_dmg, weapon_heat = weapon_selection.select_weapons_to_fire(
        attacker, distance, sel_pre_tn, attacker.min_heat, attacker.max_heat,
        dissipation=dissipation, movement_heat=attacker.movement_heat, engine_heat=eng_heat)
    budget = heat.weapon_heat_budget(attacker, attacker.movement_heat)

    config.log(f"  [Ranged] {a_name} -> {t_name}: range {distance}, base TN {pre_tn} "
               f"(gunnery {attacker.gunnery} + AMM {amm} [{attacker.move_mode}] + TMM {tmm} "
               f"+ LOS {los.modifier} + heat {heat_mod}); firing {[w.name for w in weapons] or 'nothing'} "
               f"(weapon heat {weapon_heat} of budget {budget} = max {attacker.max_heat} + sink {dissipation} "
               f"- current {attacker.current_heat} - movement {attacker.movement_heat} - engine {eng_heat}; "
               f"expected dmg {exp_dmg:.2f})")

    report.weapon_heat += weapon_heat
    for w in weapons:
        if stubs.is_one_shot(w):
            stubs.stub_one_shot(a_name, w)  # no ammo bin - its own limit instead
        elif w.damage_type != "Energy" and (w.damage_per_shot or 0) > 0:
            stubs.stub_ammo(a_name, w)
        range_mod = weapon_selection._weapon_range_mod(w, distance)
        tn = pre_tn + range_mod
        roll = config.roll_2d6(prompt=f"To-hit roll ({w.name})")
        hit = roll >= tn
        config.log(f"    {w.name}: needs {tn} (range mod +{range_mod}), rolled {roll} -> "
                   f"{'HIT' if hit else 'miss'}")
        report.attacks += 1
        report.attacks_list.append(DeclaredAttack(weapon=w, tn=tn, roll=roll, hit=hit))


def _damage_type_for(weapon):
    dt = DAMAGE_TYPE_BY_NAME.get(weapon.damage_type)
    return dt if dt is not None else stubs.stub_unknown_damage_type(weapon)


def _resolve_hit(target, damage, damage_type, side, tag=""):
    """Cannibalized from MECHSIM__sim_runner._resolve_hit() - same logic:
    hit-location roll, head-hit pilot damage, floating TAC on a 2, then
    apply_damage(). Only change: `side` is passed in (stub_attack_direction)
    rather than read from config.FACING."""
    armor_field = "rear_armor" if side == "rear" else "armor"
    loc_roll = config.roll_2d6(prompt=f"{tag}Hit location roll")
    loc = resolve_hit_location(loc_roll, target, side)
    config.log(f"      {tag}Hit location roll {loc_roll} ({side} table): {loc}.")

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
    side = stubs.stub_attack_direction(attacker.side_name, target.side_name, battle_rng)
    dtype = _damage_type_for(w)
    is_cluster = w.damage_type == "Missile" and w.rack_size is not None
    if not is_cluster:
        config.log(f"    {w.name} hit for {w.damage_per_shot}:")
        _resolve_hit(target, w.damage_per_shot, dtype, side)
        return
    cluster_roll = config.roll_2d6(prompt=f"Cluster hits roll ({w.name})")
    hits = cluster_hits_count(w.rack_size, cluster_roll)
    total = hits * w.damage_per_shot
    config.log(f"    {w.name} hit: cluster roll {cluster_roll} on the {w.rack_size}-column table -> "
               f"{hits} connect ({total} dmg).")
    groups = stubs.stub_cluster_grouping(w, total)
    for i, dmg in enumerate(groups, start=1):
        _resolve_hit(target, dmg, dtype, side, tag=f"Group {i}/{len(groups)}: ")


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
