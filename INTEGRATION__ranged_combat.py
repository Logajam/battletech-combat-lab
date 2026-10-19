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
  3. Rear arc (PATHFINDER__combat.in_rear_arc, the confirmed 60-degree rule)
     zeroes that direction's damage entirely, checked independently for
     mover's own fire and defender's return fire - matches
     PATHFINDER__combat.py's _evaluate_state() exactly.
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


def _make_heat_limited_scorer(mech):
    """Returns score(distance, pre_tn, move_heat) -> expected damage of the
    weapons select_weapons_to_fire() would actually fire, memoized for this
    call. Dissipation and engine heat are read once (they can't change
    mid-movement)."""
    dissipation = compute_heat_dissipation(mech)
    eng_heat = heat.engine_heat(mech)
    memo: Dict[tuple, float] = {}

    def score(distance: int, pre_tn: int, move_heat: int) -> float:
        key = (distance, pre_tn, move_heat)
        cached = memo.get(key)
        if cached is None:
            _, cached, _ = weapon_selection.select_weapons_to_fire(
                mech, distance, pre_tn, mech.min_heat, mech.max_heat,
                dissipation=dissipation, movement_heat=move_heat, engine_heat=eng_heat)
            memo[key] = cached
        return cached

    return score


def evaluate_going_second(
    mover, defender, terrain_map: Dict[str, object], defender_state: Optional[Dict[str, object]] = None,
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

    Returns every (hex, facing, mode) candidate mover can reach with LOS
    to the defender - intentionally UNREDUCED and UNRANKED.
    """
    if defender_state is None:
        defender_state = {"fc": 0, "mode": "Stand Still"}
    def_fc = defender_state["fc"]
    def_mode = defender_state["mode"]

    mp = {
        "walk": compute_walk_mp(mover),
        "run": compute_running_mp(mover),
        "jump": compute_jump_mp(mover),
    }

    start_x, start_y, start_facing = hex_geometry.state_from_label(mover.hex, mover.facing)
    wr_table = build_movement_table(start_x, start_y, start_facing, mp["run"], terrain_map=terrain_map)
    jump_states = combat.build_jump_states(start_x, start_y, mp["jump"], terrain_map)

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

    mover_score = _make_heat_limited_scorer(mover)
    defender_score = _make_heat_limited_scorer(defender)

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

        if combat.in_rear_arc(atk_hex, facing, def_hex):
            dealt = 0.0
        else:
            pre_tn = _clamp_pre_tn(mover.gunnery + amm + defender_tmm + atk_to_def.modifier
                                   + mover.heat_fire_modifier)
            dealt = mover_score(distance, pre_tn, move_heat)

        if defender.shutdown or combat.in_rear_arc(def_hex, def_facing, atk_hex):
            received = 0.0
        else:
            attacker_tmm = combat.fc_to_tmm(fc, jumped=(mode == "Jump"))
            pre_tn2 = _clamp_pre_tn(defender.gunnery + def_amm + attacker_tmm + def_to_atk.modifier
                                    + defender.heat_fire_modifier)
            received = defender_score(distance, pre_tn2, def_move_heat)

        results.append(MovementCandidate(
            hex=label, facing=hex_geometry.facing_to_compass(facing), mode=mode,
            fc=fc, mp_spent=mp_spent, distance=distance, dealt=dealt, received=received,
            movement_heat=move_heat,
        ))

    for (x, y, facing), col in wr_table.items():
        for mp_spent, fc in col.items():
            mode = combat.classify_movement_mode(mp_spent, mp["walk"])
            _evaluate_one(x, y, facing, fc, mode, mp_spent)

    for (x, y, facing), fc in jump_states.items():
        _evaluate_one(x, y, facing, fc, "Jump", mp["jump"])

    return results
