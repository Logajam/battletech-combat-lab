"""
INTEGRATION__ranged_combat.py

"Going second"'s core primitive: given a mover (with a real weapon list via
MECHSIM__equipment.json/mtf_parser) and a defender fixed at some hex/facing,
compute expected damage DEALT and RECEIVED for every (hex, facing, mode)
candidate the mover could reach this turn.

This is NOT an edit to PATHFINDER__combat.py (that source project stays
reference-only, per INTEGRATION__PROJECT_MAP.md Section 5's "new
orchestrator files, not either existing driver" decision). It's a new
INTEGRATION file that reuses combat.py's movement/LOS/TMM/rear-arc
machinery (all confirmed BT rules, untouched) but replaces the ONE seam
that was still a placeholder: PATHFINDER__combat.py's _weapon_expected_damage()
scores against a flat attacker["weapons"] = [{"damage","short","medium","long"}]
list with no cluster-weapon math and no connection to a real mech's
Equipment instances. That placeholder is swapped out here for
INTEGRATION__weapon_selection's real, already-validated per-weapon
expected-damage table keyed on (distance, pre_tn), built once per mech.

=== WHAT THIS DOES ===
For every (hex, facing, mode, fc, mp_spent) mover could reach (Walk/Run via
pathfinder.build_movement_table, Jump via combat.build_jump_states - same
envelope PATHFINDER__combat.py's own evaluate_combat_hexes() builds):
  1. LOS check both directions (mover->defender, defender->mover) via
     PATHFINDER__los.has_los(). Candidates with no LOS to the defender are
     dropped (a shot that can't be taken isn't a real option).
  2. pre_tn = gunnery + AMM(own mode) + TMM(target's fc/mode) + LOS modifier
     - the SAME "GATOR minus this weapon's own Range term" pre_tn
     INTEGRATION__weapon_selection.py's table is keyed on (see that module's
     docstring) - computed here once per candidate, not per weapon, since
     it's weapon-independent (range is the one GATOR term that varies by
     weapon and that's already baked into the table's own distance axis).
  3. Rear arc (PATHFINDER__combat.in_rear_arc, the confirmed 60-degree rule):
     only rear-mounted weapons fire into it, and they fire nowhere else
     (Core p.60, 2026-10-19) - checked independently for mover's own fire
     and defender's return fire. (Was: rear arc = no fire at all.)
  4. Expected damage in each direction - HEAT-AWARE as of 2026-10-18 (see
     below).

=== HEAT-AWARE SCORING (2026-10-18, Daniel: "switch movement scoring to be
    heat aware") ===
Was: the sum of expected damage over EVERY live in-range weapon - i.e. it
scored every spot as if the mech would alpha strike, even when the heat
budget would only let it fire one weapon.
Now: each direction's expected damage is exactly what
weapon_selection.select_weapons_to_fire() - the same selector the Ranged
Combat phase uses - would actually fire from there:
  - dealt: mover's own budget for THIS candidate = max_heat + dissipation
    - current heat - this candidate's own movement heat - engine heat
    (INTEGRATION__heat.movement_heat: Walk 1 / Run 2 / Jump max(3, hexes)
    or max(3, ceil(hexes/2)) with Improved JJ). So a 3-heat jump that would
    cost the mech a laser is scored with that laser missing.
  - received: defender's return fire under ITS budget, using the movement
    heat implied by defender_state (Stand Still / 0 for a defender that
    hasn't moved yet this turn).
Heat Scale effects (2026-10-19, INTEGRATION__heat): each side's own heat
to-hit modifier is in its pre_tn; Walking/Running MP already carry the
heat penalty (mech_state.compute_walk_mp). An immobile defender (shut down
or crew unconscious) is scored at the -4 immobile TMM the combat phase
uses, and a shut-down defender returns no fire.
Equipment (2026-10-19): stealth TN bonuses (range bracket, Void-Signature
by hexes moved - the candidate's own fc for the mover), aimed shots at an
immobile defender, and other heat (engine, stealth, planned radical
cooling) all go in exactly as attack_resolution applies them, except that
partial cover is not taken off aimed shots here. To-hit conditions
(weapon / targeting computer / arm crits / sensors / prone attacker and
target) come from attack_resolution too.
Results are memoized within one call on (distance, pre_tn, movement heat)
- the knapsack inputs - so thousands of candidates cost a few hundred
selector calls, not thousands.

=== WHAT THIS DELIBERATELY DOES NOT DO ===
- No candidate reduction (PATHFINDER__combat_turn.py's Section 5c dominance
  argument). Returns the FULL raw candidate list, unreduced - the picker
  that consumes this (INTEGRATION__stubs.stub_select_movement) is still a
  stub.
- No scoring/ranking formula is applied - this hands back (dealt, received)
  per candidate, not a single "best" pick.
- LB-X / Ultra AC / HAG / Artemis gaps are unchanged from
  INTEGRATION__expected_damage.py's own documented scope - a weapon with
  unconfirmed damage_per_shot/heat/range is never selectable, so it adds
  nothing here either.
"""

import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

MECHSIM_DIR = os.environ.get("MECHSIM_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "mechsim"))
PATHFINDER_DIR = os.environ.get("PATHFINDER_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "pathfinder"))

if MECHSIM_DIR not in sys.path:
    sys.path.insert(0, MECHSIM_DIR)

import INTEGRATION__config  # noqa: E402,F401 - registers bare "config" before any MECHSIM import
from mech_state import compute_walk_mp, compute_running_mp, compute_jump_mp, compute_heat_dissipation, \
    is_immobile  # noqa: E402

if PATHFINDER_DIR not in sys.path:
    sys.path.insert(0, PATHFINDER_DIR)

import hex_geometry  # noqa: E402
from pathfinder import build_movement_table  # noqa: E402
from los import has_los, hex_distance  # noqa: E402
import combat  # noqa: E402

import INTEGRATION__weapon_selection as weapon_selection  # noqa: E402
import INTEGRATION__heat as heat  # noqa: E402
import INTEGRATION__equipment_systems as equip  # noqa: E402
from INTEGRATION__attack_resolution import tn_adjuster, aimed_shot_location, firing_conditions, \
    prone_target_modifier, arc_unavailable  # noqa: E402

IMMOBILE_TMM = -4  # same convention as INTEGRATION__attack_resolution.IMMOBILE_TMM


@dataclass
class MovementCandidate:
    """One (hex, facing, mode) state mover could reach this turn, with
    expected damage in both directions against the fixed defender."""
    hex: str
    facing: str
    mode: str
    fc: int
    mp_spent: int
    distance: int
    dealt: float       # expected damage mover deals to defender from here (heat-limited)
    received: float     # expected damage defender deals back to mover from here (heat-limited)
    movement_heat: int = 0  # heat this candidate's own movement generates


def _clamp_pre_tn(pre_tn: int) -> int:
    """weapon_selection's table only populates pre_tn in [PRE_TN_MIN,
    PRE_TN_MAX] (0-16). Clamped rather than KeyError'ing on a pathological
    (very high AMM+TMM+LOS) case; clamping to the ceiling can only make an
    extreme candidate look slightly better than it truly is (it UNDERSTATES
    how hard the shot is), never inflate an ordinary one."""
    return max(weapon_selection.PRE_TN_MIN, min(weapon_selection.PRE_TN_MAX, pre_tn))


def _make_heat_limited_scorer(mech, tn_adjust, unavailable=frozenset()):
    """Returns score(distance, pre_tn, move_heat) -> expected damage of the
    weapons select_weapons_to_fire() would actually fire, memoized for this
    call. Dissipation and other heat are read once (they can't change
    mid-movement); tn_adjust is the per-weapon stealth/aim change against
    this scorer's target."""
    dissipation = compute_heat_dissipation(mech)
    other = heat.other_heat(mech)
    memo: Dict[tuple, float] = {}

    def score(distance: int, pre_tn: int, move_heat: int) -> float:
        key = (distance, pre_tn, move_heat)
        cached = memo.get(key)
        if cached is None:
            _, cached, _ = weapon_selection.select_weapons_to_fire(
                mech, distance, pre_tn, mech.min_heat, mech.max_heat,
                dissipation=dissipation, movement_heat=move_heat, other_heat=other, tn_adjust=tn_adjust,
                unavailable=unavailable)
            memo[key] = cached
        return cached

    return score


def movement_options(mover, terrain_map, standup_mp=None):
    """Every end state the mover can reach this turn, as (x, y, facing, fc,
    mode, mp_spent), deduplicated. Normally: Walk/Run from its hex and facing
    (pathfinder.build_movement_table at Running MP) plus jumps.
    standup_mp (2026-10-19, Core p.51): the mover just stood up with that
    much running MP left - it may take any facing for free, then spend the
    rest as normal in its declared mode (Run - MECHSIM stands with running
    MP); a mech that began prone can't jump."""
    sx, sy, start_facing = hex_geometry.state_from_label(mover.hex, mover.facing)
    if standup_mp is None:
        walk = compute_walk_mp(mover)
        starts, run_budget, jump_mp = [start_facing], compute_running_mp(mover), compute_jump_mp(mover)
        mode_for = lambda spent: combat.classify_movement_mode(spent, walk)  # noqa: E731
    else:
        starts, run_budget, jump_mp = range(6), standup_mp, 0
        mode_for = lambda spent: "Run"  # noqa: E731
    seen = set()
    for f0 in starts:
        for (x, y, facing), col in build_movement_table(sx, sy, f0, run_budget, terrain_map=terrain_map).items():
            for mp_spent, fc in col.items():
                key = (x, y, facing, fc, mode_for(mp_spent), mp_spent)
                if key not in seen:
                    seen.add(key)
                    yield key
    if jump_mp > 0:
        for (x, y, facing), fc in combat.build_jump_states(sx, sy, jump_mp, terrain_map).items():
            yield (x, y, facing, fc, "Jump", jump_mp)


def evaluate_going_second(
    mover, defender, terrain_map: Dict[str, object], defender_state: Optional[Dict[str, object]] = None,
    standup_mp: Optional[int] = None,
) -> List[MovementCandidate]:
    """
    mover/defender: BattleMech instances with .hex (CCRR str), .facing
    (compass str), .gunnery (int), .min_heat/.max_heat, .current_heat
    already attached (orchestrator._attach_mech_config()).

    defender_state: optional {"fc": int, "mode": str} describing how the
    DEFENDER reached its own fixed hex this turn - feeds the defender's
    own TMM (as mover's target), AMM (for its return fire) and movement
    heat (for its return-fire heat budget). Default (None) is
    fc=0/"Stand Still".

    standup_mp: see movement_options (movement after standing up).

    Returns every (hex, facing, mode) candidate mover can reach with LOS
    to the defender - intentionally UNREDUCED and UNRANKED.
    """
    if defender_state is None:
        defender_state = {"fc": 0, "mode": "Stand Still"}
    def_fc = defender_state["fc"]
    def_mode = defender_state["mode"]

    def_x, def_y = hex_geometry.parse_hex_label(defender.hex)
    def_hex = (def_x, def_y)
    def_facing = hex_geometry.compass_to_facing(defender.facing)
    if is_immobile(defender):
        defender_tmm = IMMOBILE_TMM
        def_move_heat = 0
    else:
        defender_tmm = combat.fc_to_tmm(def_fc, jumped=(def_mode == "Jump"))
        def_move_heat = heat.movement_heat(defender, def_mode, def_fc)
    def_amm = combat.MODE_TO_AMM[def_mode]

    mover_cond = firing_conditions(mover)          # mover is standing here; sensors still count
    defender_cond = firing_conditions(defender)
    mover_blocked = mover_cond[1] if mover_cond else frozenset()
    defender_blocked = defender_cond[1] if defender_cond else frozenset()
    mover_adjust = tn_adjuster(mover, defender, aimed_shot_location(defender))
    defender_adjust = tn_adjuster(defender, mover)
    # One scorer per (rear arc?) case - which weapons can bear differs (p.60).
    mover_score = {rear: _make_heat_limited_scorer(mover, mover_adjust, mover_blocked | arc_unavailable(mover, rear))
                   for rear in (False, True)}
    defender_score = {rear: _make_heat_limited_scorer(defender, defender_adjust,
                                                      defender_blocked | arc_unavailable(defender, rear))
                      for rear in (False, True)}
    dealt_stealth = equip.void_signature_modifier(defender, def_fc, defender.mp_spent) \
        + equip.own_attack_modifier(mover)
    defender_own = equip.own_attack_modifier(defender)

    results: List[MovementCandidate] = []

    def _evaluate_one(x, y, facing, fc, mode, mp_spent):
        atk_hex = (x, y)
        if atk_hex == def_hex:
            return  # occupying the defender's hex is undefined, same as combat.py

        try:
            label = hex_geometry.hex_label(x, y)
        except ValueError:
            return  # off-convention coordinate, not a real labeled hex

        try:
            atk_to_def = has_los(atk_hex, def_hex, terrain_map)
            def_to_atk = has_los(def_hex, atk_hex, terrain_map)
        except ValueError:
            return  # off-board LOS line - not a usable candidate
        if not atk_to_def.los:
            return  # no shot possible from here at all

        distance = hex_distance(atk_hex, def_hex)
        amm = combat.MODE_TO_AMM[mode]
        move_heat = heat.movement_heat(mover, mode, fc)

        if mover_cond is None:
            dealt = 0.0
        else:
            pre_tn = _clamp_pre_tn(mover.gunnery + amm + defender_tmm + atk_to_def.modifier
                                   + mover.heat_fire_modifier + dealt_stealth + mover_cond[0]
                                   + prone_target_modifier(defender, distance))
            dealt = mover_score[combat.in_rear_arc(atk_hex, facing, def_hex)](distance, pre_tn, move_heat)

        if defender.shutdown or defender_cond is None:
            received = 0.0
        else:
            attacker_tmm = combat.fc_to_tmm(fc, jumped=(mode == "Jump"))
            pre_tn2 = _clamp_pre_tn(defender.gunnery + def_amm + attacker_tmm + def_to_atk.modifier
                                    + defender.heat_fire_modifier + defender_own + defender_cond[0]
                                    + equip.void_signature_modifier(mover, fc, mp_spent))
            received = defender_score[combat.in_rear_arc(def_hex, def_facing, atk_hex)](distance, pre_tn2, def_move_heat)

        results.append(MovementCandidate(
            hex=label, facing=hex_geometry.facing_to_compass(facing), mode=mode,
            fc=fc, mp_spent=mp_spent, distance=distance, dealt=dealt, received=received,
            movement_heat=move_heat,
        ))

    for x, y, facing, fc, mode, mp_spent in movement_options(mover, terrain_map, standup_mp):
        _evaluate_one(x, y, facing, fc, mode, mp_spent)

    return results
