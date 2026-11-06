"""
INTEGRATION__future_damage.py  (NEW 2026-10-20, Claude - Pile 4 scoring input)

"Future damage per turn": how much one mech can expect to deal another on a
typical later turn, for the "lifetime" movement objective
(INTEGRATION__movement_selection, config.MOVEMENT_OBJECTIVE). Daniel
(2026-10-20): ".5 (Odds of winning initiative)*perfect expected damage.
Gunnery+Best enemy TMM as the target number vs the optimum damage potential
of the attacking mech. This weights in an evasive enemy taking less damage
per turn."

    future = MOVEMENT_LIFETIME_INITIATIVE x the best expected damage over every
             range, the target dead ahead,
             TN = gunnery + AMM of MOVEMENT_LIFETIME_ATTACKER_MODE (Walk: +1)
                  + the TARGET's best TMM (its Running or Jumping MP, p.57)
                  + the attacker's heat / sensor / prone / own-equipment
                    modifiers + each weapon's own and range modifiers

Claude's readings (2026-10-20, agreed with Daniel before building):
  - Heat-limited: the weapons select_weapons_to_fire would really fire at the
    attacker's present heat, not an alpha strike it can't repeat.
  - The attacker is assumed to walk (its own +1, and walking heat), since the
    target is assumed to run for its best TMM - config knob.
  - Kicks / punches count at range 1 (on piloting, with the target's TMM and
    the attacker's AMM), with the weapons in the attacking limbs held back -
    the same combination movement scoring uses (ranged_combat._with_physical).
  - Same units as the movement score's "dealt": structure damage counts
    MOVEMENT_STRUCTURE_WEIGHT times, on the front table (exposure 1.0).
  - Not counted: the target's AMS, terrain and partial cover, aimed shots -
    this is a baseline rate, not a position.
Recomputed every pick, so it follows damage: lose leg actuators and your TMM
drops (the enemy's future damage on you rises); lose weapons and your own
future damage drops.
"""

import INTEGRATION__config as config
import INTEGRATION__arcs as arcs
import INTEGRATION__ammo as ammo
import INTEGRATION__fire_modes as fire_modes
import INTEGRATION__heat as heat
import INTEGRATION__physical as physical
import INTEGRATION__structure_weight as structure_weight
import INTEGRATION__weapon_profiles as weapon_profiles
import INTEGRATION__weapon_selection as weapon_selection
from INTEGRATION__attack_resolution import arc_unavailable, firing_conditions, tn_adjuster
from INTEGRATION__ranged_combat import _make_heat_limited_scorer, _with_physical
import INTEGRATION__equipment_systems as equip
from damage_resolution import get_weapons, tmm_from_mp
from mech_state import compute_running_mp, compute_jump_mp, is_immobile
import combat

# A sample geometry for "target dead ahead": attacker at the origin facing N
# (0), target straight north. Coordinates are hex_geometry's (column, doubled row).
_ORIGIN = (0, 0)
_FACING = 0


def best_tmm(mech):
    """The highest TMM the mech can earn (p.57): from its Running MP with any
    working MASC / supercharger (equipment_systems.boost_multiplier), or its
    Jumping MP + 1. Doesn't change the mech (compute_tmm records the movement
    mode for the PSR code, so it isn't used here)."""
    with equip.modeled_boost(mech, equip.boost_multiplier(mech, planned=False)):
        run = compute_running_mp(mech)
    tmm = tmm_from_mp(run)
    jump = compute_jump_mp(mech)
    if jump > 0:
        tmm = max(tmm, tmm_from_mp(jump) + 1)
    return tmm


def _max_distance(weapons):
    longest = 1
    for w in weapons:
        r = getattr(w, "weapon_range", None) or {}
        longest = max(longest, r.get("long") or 0)
    return min(longest, 30)


def future_damage(attacker, target):
    """attacker's future damage per turn against target (see the module
    docstring), in movement-score units."""
    if attacker.shutdown or is_immobile(attacker):
        return 0.0
    mode = config.MOVEMENT_LIFETIME_ATTACKER_MODE
    amm = combat.MODE_TO_AMM[mode]
    move_heat = heat.movement_heat(attacker, mode, 1)
    tmm = best_tmm(target)
    weapons = get_weapons(attacker)
    legs = arcs.leg_offsets(attacker)

    cond = firing_conditions(attacker)
    scorers = {}
    # What does not change from one distance to the next (2026-11-06, speed: this ran for each of ~30 distances):
    # the target is straight north at every distance, so its arc key is the same, and so are the weapons that
    # can't fire, the to-hit base and the sets of weapons held back.
    fixed = {}

    def ranged(distance, held=frozenset()):
        """Best heat-limited expected damage at this distance (0 if it can't fire)."""
        if cond is None:
            return 0.0
        if not fixed:
            target_xy = (_ORIGIN[0], _ORIGIN[1] + 2 * distance)          # straight north
            key = arcs.key_for(arcs.arcs_between(_ORIGIN, target_xy), _FACING, arcs.NO_ACTION, legs)
            fixed["blocked"] = (cond[1] | ammo.unavailable_weapons(attacker) | fire_modes.jammed_ids(attacker)
                                | weapon_profiles.array_gun_ids(attacker) | arc_unavailable(attacker, key))
            fixed["by_held"] = {}
            pre = (attacker.gunnery + amm + tmm + attacker.heat_fire_modifier + cond[0]
                   + equip.own_attack_modifier(attacker))
            fixed["pre_tn"] = max(weapon_selection.PRE_TN_MIN, min(weapon_selection.PRE_TN_MAX, pre))
        unavailable = fixed["by_held"].get(held)
        if unavailable is None:
            unavailable = fixed["by_held"][held] = fixed["blocked"] | held
        scorer = scorers.get(unavailable)
        if scorer is None:
            adjust = tn_adjuster(attacker, target)
            usable = [w for w in weapons if id(w) not in unavailable]
            scale = ((lambda side: structure_weight.multipliers(weapons, target, side))
                     if config.MOVEMENT_STRUCTURE_WEIGHT != 1.0 else None)
            planner = fire_modes.Planner(attacker, target, adjust, fire_modes.ams_share(0, usable))
            scorer = scorers[unavailable] = _make_heat_limited_scorer(attacker, adjust, unavailable, scale, planner,
                                                                      share=("future damage",))
        return scorer(distance, fixed["pre_tn"], move_heat, "front")

    best = max(ranged(d) for d in range(1, _max_distance(weapons) + 1))

    # Range 1 with a kick / punch / physical weapon on top (pp.76-83).
    if not attacker.prone:
        pair = arcs.arcs_between(_ORIGIN, (_ORIGIN[0], _ORIGIN[1] + 2))
        planner = physical.Planner(attacker, physical.Worth(target, relative=True))
        base = physical.base_tn(attacker, amm, tmm, 0, 0)
        best = _with_physical(max(best, ranged(1)), planner, (arcs.NO_ACTION,), legs, pair, _FACING, 0, False,
                              base, "front", lambda key, held: ranged(1, held))
    return config.MOVEMENT_LIFETIME_INITIATIVE * best
