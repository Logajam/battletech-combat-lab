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
  3. Firing arcs and torso twists (INTEGRATION__arcs, Core pp.60-62, 2026-10-19):
     which weapons can bear depends on the arc the target is in (forward /
     side / rear); each side may also twist its torso (one hexside, a
     tripod any), flip its arms or turn a turret, and keeps the best -
     checked independently for the mover's own fire and the defender's
     return fire. The twist is declared at attack declaration, after
     movement (p.61), so taking the best one per spot is the real rule.
  3a. Physical attacks (2026-10-19): at range 1 each side's number is the
     best over arc actions and physical plans (INTEGRATION__physical.Planner)
     of ranged fire without the attacking limbs' weapons + the plan's
     expected damage - the twist stands for both phases, and a limb that
     punches or kicks can't have fired (pp.62, 76, 82). Physical damage is
     not structure-weighted, and kick / missed-kick PSRs are not priced
     (Daniel's rule: only Movement-phase PSRs count).
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
  that consumes this (INTEGRATION__movement_selection, 2026-10-19) does its
  own reduction.
- No scoring/ranking formula is applied - this hands back (dealt, received)
  per candidate, not a single "best" pick.

=== MoveEvaluator (2026-10-19) ===
The per-call setup (firing conditions, the four heat-limited weapon scorers
and their memo tables) is split out of the per-position work into
MoveEvaluator, so INTEGRATION__movement_selection's two-ply search can build
it ONCE per (mover, defender) pair and then score the mover's whole envelope
against a defender pinned at each of hundreds of different positions. The
scorers' memo (keyed on distance, pre_tn, movement heat) carries over between
positions - none of those inputs depend on where the defender is pinned.
evaluate_going_second() is now a thin wrapper and returns exactly what it
did before. LOS, distance, entry hexside and rear-arc answers come from
INTEGRATION__los_cache.
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
import INTEGRATION__config as config  # noqa: E402
from damage_resolution import get_weapons  # noqa: E402
from mech_state import compute_walk_mp, compute_running_mp, compute_jump_mp, compute_heat_dissipation, \
    is_immobile  # noqa: E402

if PATHFINDER_DIR not in sys.path:
    sys.path.insert(0, PATHFINDER_DIR)

import hex_geometry  # noqa: E402
from pathfinder import build_movement_table, PathTable  # noqa: E402
from mech_state import is_superheavy, ground_level_limited  # noqa: E402 - pp.90, 99, 238-239
import terrain_rules  # noqa: E402
from los import has_los, hex_distance, STANDING_HEIGHT, PRONE_HEIGHT, mech_height  # noqa: E402
from mech_state import target_size_modifier  # noqa: E402 - MECHSIM, Core p.240 (2026-10-28)
import combat  # noqa: E402

import INTEGRATION__weapon_selection as weapon_selection  # noqa: E402
import INTEGRATION__heat as heat  # noqa: E402
import INTEGRATION__equipment_systems as equip  # noqa: E402
import INTEGRATION__ammo as ammo  # noqa: E402
import INTEGRATION__structure_weight as structure_weight  # noqa: E402
import INTEGRATION__arcs as arcs  # noqa: E402
import INTEGRATION__ams as ams  # noqa: E402
import INTEGRATION__fire_modes as fire_modes  # noqa: E402
import INTEGRATION__weapon_profiles as weapon_profiles  # noqa: E402
import INTEGRATION__los_cache as geo_cache  # noqa: E402
from INTEGRATION__attack_resolution import tn_adjuster, aimed_shot_location, firing_conditions, \
    prone_target_modifier, arc_unavailable, weapon_locations, _SIDE_BY_RELATIVE_HEXSIDE  # noqa: E402
import INTEGRATION__physical as physical  # noqa: E402
import INTEGRATION__water as water  # noqa: E402
import INTEGRATION__weapon_rules as weapon_rules  # noqa: E402

IMMOBILE_TMM = -4  # same convention as INTEGRATION__attack_resolution.IMMOBILE_TMM


@dataclass(slots=True)
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
    side_on_defender: str = ""  # hit table the defender is shot on from here (Core p.73): front/left/right/rear
    side_on_mover: str = ""     # hit table the mover is shot on when the defender fires back
    attack: str = ""            # "charge" / "dfa" for an attack declared in movement (INTEGRATION__movement_attacks)


def _make_heat_limited_scorer(mech, tn_adjust, unavailable=frozenset(), scale_for_side=None, planner=None,
                              extra_dissipation=0):
    """Returns score(distance, pre_tn, move_heat) -> expected damage of the
    weapons select_weapons_to_fire() would actually fire, memoized for this
    call. Dissipation and other heat are read once (they can't change
    mid-movement); tn_adjust is the per-weapon stealth/aim change against
    this scorer's target.

    scale_for_side (2026-10-19): optional f(side) -> {id(weapon): multiplier}
    (INTEGRATION__structure_weight, built per target); when given, score() takes
    the attack side too and returns WORTH - expected damage with structure
    damage counted for more - and the memo is keyed by side as well.
    planner (2026-10-20): the fire_modes.Planner pricing this mech's special
    weapons against this target (weapon_selection.select_weapons_to_fire).
    extra_dissipation (2026-10-21): submerged heat sinks' bonus where this
    mech would stand (INTEGRATION__water, p.103)."""
    dissipation = compute_heat_dissipation(mech) + extra_dissipation
    weapons = get_weapons(mech)                                   # fixed for the scorer's life
    table = weapon_selection.build_expected_damage_table(mech)
    scales: Dict[str, dict] = {}
    other = heat.other_heat(mech)
    memo: Dict[tuple, float] = {}

    def score(distance: int, pre_tn: int, move_heat: int, side: str = "") -> float:
        key = (distance, pre_tn, move_heat, side)
        cached = memo.get(key)
        if cached is None:
            scale = None
            if scale_for_side is not None:
                scale = scales.get(side)
                if scale is None:
                    scale = scales[side] = scale_for_side(side)
            _, cached, _ = weapon_selection.select_weapons_to_fire(
                mech, distance, pre_tn, mech.min_heat, mech.max_heat,
                dissipation=dissipation, movement_heat=move_heat, other_heat=other, tn_adjust=tn_adjust,
                unavailable=unavailable, value_scale=scale, weapons=weapons, table=table, planner=planner,
                side=side or None)
            memo[key] = cached
        return cached

    return score


def movement_options(mover, terrain_map, standup_mp=None, entry_edge=None, backward=True):
    """_movement_options, except that a mech trying to unjam a Rotary AC this
    turn may only stand still or walk (Core p.183; fire_modes.declare_unjams,
    2026-10-20)."""
    states = _movement_options(mover, terrain_map, standup_mp, entry_edge, backward)
    if getattr(mover, "unjamming", None):
        return (st for st in states if st[4] in ("Stand Still", "Walk"))
    return states


def _movement_options(mover, terrain_map, standup_mp=None, entry_edge=None, backward=True):
    """Every end state the mover can reach this turn, as (x, y, facing, fc,
    mode, mp_spent), deduplicated. Normally: Walk/Run from its hex and facing
    (pathfinder.build_movement_table at Running MP) plus jumps.
    standup_mp (2026-10-19, Core p.51): the mover just stood up with that
    much running MP left - it may take any facing for free, then spend the
    rest as normal in its declared mode (Run - MECHSIM stands with running
    MP); a mech that began prone can't jump.
    entry_edge (2026-10-19, Core p.37): the mover is entering the battlefield
    - it moves into any hex of its home edge (the labels given) with any
    facing, its MP counted from that first hex (whose entry cost it pays,
    and which counts as a hex moved). Jumping onto the board isn't modeled.
    backward (2026-10-20, Core pp.45-46): a walking mech may also move
    backward (pathfinder.build_movement_table's backward_mp = Walking MP);
    those states only ever have Walk's MP. Not after standing up (MECHSIM
    stands with Running MP - a Run, which can't move backward) or when
    entering the board. backward=False gives the forward-only states
    (movement_attacks' charge index: a charge ends moving forward into the
    target's hex, and its hex count would restart after a backward step).
    Terrain PSRs (2026-10-21): on a board where steps can force one
    (pathfinder.PathTable), mover.path_psrs[state] = how many the state's
    path forces in its mode (run-only ones count for Run) - movement scoring
    prices them, the orchestrator's movement subphase rolls them.
    movement_selection.reduced_options clears it before a pick. Hazards
    (2026-10-27): mover.path_hazard[state] = the expected damage of the
    hexes its path enters (magma, hazardous liquid - terrain_rules.
    step_hazard), the least when several paths reach it.
    mover.blocked_hex (2026-10-21, p.48): the (x, y) of a mobile enemy 'Mech
    no ground step may enter (jumps pass over it) - set by the orchestrator
    for the mover's real move (blocked_by_enemy), None otherwise."""
    if not hasattr(mover, "path_psrs"):
        mover.path_psrs = {}
    if not hasattr(mover, "path_hazard"):
        mover.path_hazard = {}
    if entry_edge is not None:
        yield from _entry_options(mover, terrain_map, entry_edge)
        return
    sx, sy, start_facing = hex_geometry.state_from_label(mover.hex, mover.facing)
    if standup_mp is None:
        walk = compute_walk_mp(mover)
        starts, run_budget, jump_mp = [start_facing], compute_running_mp(mover), water.jump_mp(mover)   # water: p.50
        mode_for = lambda spent: combat.classify_movement_mode(spent, walk)  # noqa: E731
        backward_mp = walk if backward and walk > 0 else None
    else:
        starts, run_budget, jump_mp = range(6), standup_mp, 0
        mode_for = lambda spent: "Run"  # noqa: E731
        backward_mp = None
    level_limit = terrain_rules.max_level_change(ground_level_limited(mover), is_superheavy(mover))   # pp.46-47
    seen = set()
    if getattr(mover, "jump_only", False):
        # Bogged down after ground movement (TO:AR p.60): stay, or jump out.
        starts, standup_mp = [], 0
        yield (sx, sy, start_facing, 0, mode_for(0), 0)
    for f0 in starts:
        table = build_movement_table(sx, sy, f0, run_budget, terrain_map=terrain_map, backward_mp=backward_mp,
                                     level_limit=level_limit, blocked=getattr(mover, "blocked_hex", None))
        for (x, y, facing), col in table.items():
            psrs = table.psrs.get((x, y, facing)) if isinstance(table, PathTable) else None
            hazards = table.hazards.get((x, y, facing)) if isinstance(table, PathTable) else None
            for mp_spent, fc in col.items():
                key = (x, y, facing, fc, mode_for(mp_spent), mp_spent)
                if psrs is not None:
                    _note_psrs(mover, key, psrs[mp_spent], hazards[mp_spent])
                if key not in seen:
                    seen.add(key)
                    yield key
    if standup_mp is None:
        got = _minimum_move(mover, terrain_map, sx, sy, start_facing, run_budget, seen, level_limit)
        if got is not None:
            yield got
    if jump_mp > 0:
        for (x, y, facing), fc in combat.build_jump_states(sx, sy, jump_mp, terrain_map).items():
            yield (x, y, facing, fc, "Jump", jump_mp)
        # p.50: "A 'Mech can jump into the same hex it began the turn in, for 1 MP" - 0
        # hexes moved, any facing, still +1 TMM for jumping (2026-10-21, RULES_REVIEW G5).
        for facing in range(6):
            yield (sx, sy, facing, 0, "Jump", 1)


def _minimum_move(mover, terrain_map, sx, sy, facing, run_budget, seen, level_limit):
    """Minimum Movement (p.49, 2026-10-21, RULES_REVIEW G8): a 'Mech with at
    least 1 MP may run into the hex directly in front of it even without the
    MP it would normally cost - if that is all it does this turn (no facing
    change first), the hex isn't prohibited (terrain_rules.step_cost - level
    limit, roofs, impassable) or a mobile enemy's, and the move is a run
    (all its MP). Only offered when the normal search can't already reach that
    hex straight ahead. Returns the (x, y, facing, fc, mode, mp_spent) state
    or None. Its terrain PSRs (rubble...) are noted like any path's."""
    if run_budget < 1:
        return None
    dx, dy = hex_geometry.FACING_DELTAS[facing]
    fx, fy = sx + dx, sy + dy
    if (fx, fy) == getattr(mover, "blocked_hex", None):
        return None
    try:
        label = hex_geometry.hex_label(fx, fy)
    except ValueError:
        return None
    hexes = terrain_map["hexes"]
    info = hexes.get(label)
    if info is None:
        return None
    here = hexes[mover.hex]
    cost = terrain_rules.step_cost(here, info, level_limit)
    if cost is None or cost <= run_budget:
        return None                          # prohibited, or reachable the normal way
    key = (fx, fy, facing, 1, "Run", run_budget)
    if key in seen:
        return None
    if terrain_rules.has_psr_terrain(terrain_map):
        _note_psrs(mover, key, terrain_rules.step_psrs(here, info), terrain_rules.step_hazard(info))
    return key


def _note_psrs(mover, key, psrs, hazard=0.0):
    """Record the terrain PSRs (always, run_only) of the path to option `key`
    (x, y, facing, fc, mode, mp) - the fewest when several paths reach it -
    and its hazard damage (the least)."""
    n = psrs[0] + (psrs[1] if key[4] == "Run" else 0)
    old = mover.path_psrs.get(key)
    if old is None or n < old:
        mover.path_psrs[key] = n
    if hazard:
        old = mover.path_hazard.get(key)
        if old is None or hazard < old:
            mover.path_hazard[key] = hazard
    elif key in mover.path_hazard:
        mover.path_hazard[key] = 0.0


def _entry_options(mover, terrain_map, edge_labels):
    walk, run = compute_walk_mp(mover), compute_running_mp(mover)
    seen = set()
    blocked = getattr(mover, "blocked_hex", None)
    for label in edge_labels:
        info = terrain_map["hexes"].get(label)
        if info is None or hex_geometry.parse_hex_label(label) == blocked:
            continue
        cost = terrain_rules.step_cost(None, info)        # None: can't walk onto a roof from off the board
        if cost is None or cost > run:
            continue
        level_limit = terrain_rules.max_level_change(ground_level_limited(mover), is_superheavy(mover))
        ex, ey = hex_geometry.parse_hex_label(label)
        entry_psrs = terrain_rules.step_psrs(None, info)          # entering the edge hex itself
        entry_hazard = terrain_rules.step_hazard(info)
        for f0 in range(6):
            table = build_movement_table(ex, ey, f0, run - cost, terrain_map=terrain_map, level_limit=level_limit,
                                         blocked=getattr(mover, "blocked_hex", None))
            for (x, y, facing), col in table.items():
                psrs = table.psrs.get((x, y, facing)) if isinstance(table, PathTable) else None
                hazards = table.hazards.get((x, y, facing)) if isinstance(table, PathTable) else None
                for spent, fc in col.items():
                    total = spent + cost
                    key = (x, y, facing, fc + 1, combat.classify_movement_mode(total, walk), total)
                    if psrs is not None:
                        a, r = psrs[spent]
                        _note_psrs(mover, key, (a + entry_psrs[0], r + entry_psrs[1]), hazards[spent] + entry_hazard)
                    if key not in seen:
                        seen.add(key)
                        yield key


class _Option:
    """One mover end state with everything about it that doesn't depend on
    where the defender is (computed once by MoveEvaluator.prepare)."""
    __slots__ = ("x", "y", "hex_xy", "facing", "label", "facing_compass", "fc", "mode", "mp_spent",
                 "amm", "move_heat", "tmm", "void_mod")


def prepare_options(mover, options) -> List[_Option]:
    """options: (x, y, facing, fc, mode, mp_spent) tuples (movement_options
    output, or a reduction of it) -> _Option objects carrying what depends only
    on the mover's own state (label, AMM, movement heat, TMM, Void-Signature
    bonus). Drops states with no labeled hex."""
    prepared = []
    for x, y, facing, fc, mode, mp_spent in options:
        try:
            label = hex_geometry.hex_label(x, y)
        except ValueError:
            continue  # off-convention coordinate, not a real labeled hex
        o = _Option()
        o.x, o.y, o.hex_xy, o.facing, o.label = x, y, (x, y), facing, label
        o.facing_compass = hex_geometry.facing_to_compass(facing)
        o.fc, o.mode, o.mp_spent = fc, mode, mp_spent
        o.amm = combat.MODE_TO_AMM[mode]
        o.move_heat = heat.movement_heat(mover, mode, fc)
        o.tmm = combat.fc_to_tmm(fc, jumped=(mode == "Jump")) + target_size_modifier(mover)   # Core p.240
        o.void_mod = equip.void_signature_modifier(mover, fc, mp_spent)
        prepared.append(o)
    return prepared


def turned_option(o, facing) -> "_Option":
    """A copy of prepared state o facing `facing` instead (0-5). Nothing else
    on an _Option depends on the facing, so the copy keeps o's hexes moved,
    mode, TMM and heat - used by movement_selection's "short_list" reply model
    (2026-10-24), which assumes a facing it doesn't check is reachable."""
    t = _Option()
    for slot in _Option.__slots__:
        setattr(t, slot, getattr(o, slot))
    t.facing, t.facing_compass = facing, hex_geometry.facing_to_compass(facing)
    return t


def _with_physical(ranged_best, planner, actions, legs, pair_arcs, facing, diff, target_prone, base, side,
                   ranged_for, push=(), allowed=None, t_water=None):
    """Best expected damage from a spot next to the enemy counting the
    Physical phase too: for every arc action and physical plan, the ranged
    fire without the weapons in the attacking limbs (pp.76, 82) plus the
    plan's expected damage. ranged_for(key, held) gives the ranged part
    (None: no ranged fire possible); ranged_best is the no-physical value.
    allowed: the physical attack kinds water leaves (INTEGRATION__water,
    p.77), None = all; t_water: the target's water state (half damage to its
    underwater locations), None = on land."""
    best = ranged_best
    if not physical.reachable(diff, planner.target_superheavy):
        return best
    if allowed is not None and "push" not in allowed:
        push = ()
    for key, signature in planner.cases(pair_arcs, facing, actions, legs):
        for value, limbs, _ in planner.plans_in_case(signature, diff, target_prone, base, side, allowed, t_water):
            if not limbs or value <= 0:
                continue
            if value + ranged_best <= best:
                break                                    # plans are best first; ranged can't beat ranged_best
            total = value if ranged_for is None else ranged_for(key, planner.held(limbs)) + value
            if total > best:
                best = total
    for value, limbs, _ in push:                         # a push: feet facing, no twist / flip needed (p.83)
        total = value if ranged_for is None else ranged_for(
            arcs.key_for(pair_arcs, facing, actions[0], legs), planner.held(limbs)) + value
        if total > best:
            best = total
    return best


class _ArcClasses:
    """Sorts (target arcs-tuple, facing) pairs into classes: two pairs are in
    the same class when they give the same set of ArcKeys (arcs.arc_keys) -
    i.e. the same weapons can bear for every twist / flip / turret choice - so
    the best-twist damage is the same for both. of() -> (class number, the
    class's ArcKeys). Speed only (2026-10-20): MoveEvaluator's memos key on the
    class instead of the exact geometry and hit far more often."""
    __slots__ = ("actions", "legs", "_by_pair", "_by_keys")

    def __init__(self, mech_arcs):
        self.actions, self.legs = mech_arcs          # (arcs.arc_options(mech), arcs.leg_offsets(mech))
        self._by_pair: Dict[tuple, tuple] = {}
        self._by_keys: Dict[tuple, tuple] = {}

    def of(self, target_arcs, facing):
        hit = self._by_pair.get((target_arcs, facing))
        if hit is None:
            keys = tuple(key for key, _ in arcs.arc_keys(target_arcs, facing, self.actions, self.legs))
            hit = self._by_keys.get(keys)
            if hit is None:
                hit = self._by_keys[keys] = (len(self._by_keys), keys)
            self._by_pair[(target_arcs, facing)] = hit
        return hit


class MoveEvaluator:
    """Scores a mover's end states against a defender pinned at any hex.

    Build once per (mover, defender): the heat-limited scorers keep their memo
    tables for as long as the evaluator lives. Nothing about the two mechs may
    change between calls (damage, heat, ammo) - build a new one if it does.

    AMS (2026-10-20, INTEGRATION__ams): each side's missile damage is scaled
    by the engagements the other side's AMS can make from that spot (its
    arcs, untwisted); the scorers and best-twist memos are keyed by that count
    too. Mechs without AMS always see 0 - the numbers are unchanged.
    Special weapons (2026-10-20, INTEGRATION__fire_modes.Planner): missiles,
    rapid fire, LB-X, MML, ATM are priced with the ammunition / rate the stubs
    would pick, Artemis / Narc / ECM and that AMS share. A Narc beacon's pod
    value isn't counted here (the attack phase prices it).
    """

    def __init__(self, mover, defender, terrain_map: Dict[str, object]):
        self.mover, self.defender, self.terrain_map = mover, defender, terrain_map
        self.defender_immobile = is_immobile(defender)
        self.mover_cond = firing_conditions(mover)          # mover is standing here; sensors still count
        self.defender_cond = firing_conditions(defender)
        mover_blocked = (self.mover_cond[1] if self.mover_cond else frozenset()) | ammo.unavailable_weapons(mover) \
            | fire_modes.jammed_ids(mover) | weapon_profiles.array_gun_ids(mover)
        defender_blocked = (self.defender_cond[1] if self.defender_cond else frozenset()) \
            | ammo.unavailable_weapons(defender) | fire_modes.jammed_ids(defender) | weapon_profiles.array_gun_ids(defender)
        mover_adjust = tn_adjuster(mover, defender, aimed_shot_location(defender))
        defender_adjust = tn_adjuster(defender, mover)
        # Structure weighting (INTEGRATION__structure_weight): off at k = 1.0, which leaves
        # every number exactly as it was.
        weighting = config.MOVEMENT_STRUCTURE_WEIGHT != 1.0
        mover_scale = (lambda side: structure_weight.multipliers(get_weapons(mover), defender, side)) if weighting else None
        defender_scale = (lambda side: structure_weight.multipliers(get_weapons(defender), mover, side)) if weighting else None
        # One scorer per (torso arc, legs see it forward?) case - which weapons can bear differs
        # (p.60), built the first time it's needed.
        mover_scorers: Dict[tuple, object] = {}
        defender_scorers: Dict[tuple, object] = {}

        def scorer_getter(who, target, adjust, blocked, scale, cache):
            # Scorers are shared by every (key, held) that leaves the same weapons
            # unable to fire (2026-10-20, speed only): many twists / arcs block the
            # same set, and a shared scorer shares its memo.
            by_unavailable: Dict[tuple, object] = {}
            usable = [w for w in get_weapons(who) if id(w) not in blocked]
            torpedoes = frozenset(id(w) for w in usable if weapon_rules.is_torpedo(w))   # underwater only (p.187)
            planners: Dict[tuple, object] = {}     # fire_modes.Planner per (AMS count, water) (shares its memo)
            w_locs = weapon_locations(who)

            def get(key, held=frozenset(), ams_k=0, wet=None):
                # held: weapons kept back because their limb attacks in the Physical phase
                # ams_k: attacks the target's AMS can engage from here (INTEGRATION__ams, p.206)
                # wet: None on dry ground, else (firer's water state, weapons the water stops,
                #      heat sink bonus) - INTEGRATION__water (2026-10-21)
                scorer = cache.get((key, held, ams_k, wet))
                if scorer is None:
                    unavailable = blocked | arc_unavailable(who, key) | held
                    if wet is not None:
                        unavailable = unavailable | wet[1]
                    else:
                        unavailable = unavailable | torpedoes
                    w_state, bonus = (wet[0], wet[2]) if wet is not None else (water.GROUND, 0)
                    scorer = by_unavailable.get((unavailable, ams_k, w_state, bonus))
                    if scorer is None:
                        planner = planners.get((ams_k, w_state))
                        if planner is None:
                            w_adjust = water.range_adjuster(who, w_locs, w_state, adjust)
                            planner = planners[(ams_k, w_state)] = fire_modes.Planner(
                                who, target, w_adjust, fire_modes.ams_share(ams_k, usable))
                        scorer = by_unavailable[(unavailable, ams_k, w_state, bonus)] = _make_heat_limited_scorer(
                            who, planner.adjust, unavailable, scale, planner, bonus)
                    cache[(key, held, ams_k, wet)] = scorer
                return scorer
            return get
        # Water (2026-10-21, INTEGRATION__water): None on a board without depth 1+ water,
        # so dry battles take exactly the old path.
        self.water_depths = water.hexes_by_depth(terrain_map) or None
        self._wet_cases: Dict[tuple, tuple] = {}
        self.mover_scorer = scorer_getter(mover, defender, mover_adjust, mover_blocked, mover_scale, mover_scorers)
        self.defender_scorer = scorer_getter(defender, mover, defender_adjust, defender_blocked, defender_scale,
                                             defender_scorers)
        self.mover_arcs = (arcs.arc_options(mover), arcs.leg_offsets(mover))   # twists / flips / turret (pp.61-62)
        self.defender_arcs = (arcs.arc_options(defender), arcs.leg_offsets(defender))
        # Physical attacks (pp.76-83) from / against a spot next to the enemy.
        self.mover_physical = not (mover.shutdown or is_immobile(mover))
        self.defender_physical = not (defender.shutdown or defender.prone or self.defender_immobile)
        # Physical damage is weighted by its own hit table (relative: the side's
        # standard exposure factor is applied on top by movement_selection).
        self.mover_planner = physical.Planner(mover, physical.Worth(defender, relative=True))
        self.defender_planner = physical.Planner(defender, physical.Worth(mover, relative=True))
        # Best-twist memos, keyed on the arc CLASS (below) rather than the exact
        # geometry, so every spot that sees the target the same way shares one entry.
        self._best_dealt: Dict[tuple, float] = {}
        self._best_received: Dict[tuple, float] = {}
        self._mover_classes = _ArcClasses(self.mover_arcs)
        self._defender_classes = _ArcClasses(self.defender_arcs)
        self.mover_own = equip.own_attack_modifier(mover)
        self.defender_own = equip.own_attack_modifier(defender)
        # Each side's AMS (p.206): how many of the other's missile attacks it can engage, by arc.
        self.mover_ams = ams.Coverage(mover)
        self.defender_ams = ams.Coverage(defender)

    def _wet(self, firer, f_label, f_prone, target, t_label, t_prone):
        """The water case of firer at f_label shooting target at t_label
        (INTEGRATION__water): None when both are on dry ground (the old path),
        "none" when no attack can cross the water line, else the scorer's wet
        argument (firer's water state, weapons the water stops, heat sink bonus)."""
        depths = self.water_depths
        f_depth, t_depth = depths.get(f_label, 0), depths.get(t_label, 0)
        if not f_depth and not t_depth:
            return None
        # A torpedo needs an all-water line (p.187) - looked at only for a firer that carries one.
        line = (f_depth > 0 and t_depth > 0 and any(weapon_rules.is_torpedo(w) for w in get_weapons(firer))
                and water.water_line(f_label, t_label, self.terrain_map))
        key = (id(firer), id(target), f_depth, f_prone, t_depth, t_prone, line)
        case = self._wet_cases.get(key)
        if case is None:
            f_state = water.state_at(f_label, f_prone, self.terrain_map, is_superheavy(firer))   # p.240
            t_state = water.state_at(t_label, t_prone, self.terrain_map, is_superheavy(target))
            blocked = water.blocked_weapon_ids(firer, get_weapons(firer), weapon_locations(firer), f_state, t_state,
                                               torpedo_line=line)
            case = self._wet_cases[key] = "none" if blocked is None else \
                (f_state, blocked, water.dissipation_bonus(firer, f_state))
        return case

    def _physical_water(self, a_label, a_prone, t_label, t_prone, a_superheavy=False, t_superheavy=False):
        """(the physical attack kinds water allows from a_label at t_label -
        INTEGRATION__water.physical_allowed, p.77 - None = all; the target's
        water state, for its halved damage - None = on land). (None, None) on
        a board without water."""
        if self.water_depths is None:
            return None, None
        t_state = water.state_at(t_label, t_prone, self.terrain_map, t_superheavy)
        return (water.physical_allowed(water.state_at(a_label, a_prone, self.terrain_map, a_superheavy), t_state),
                None if t_state == water.GROUND else t_state)

    def _hex_row(self, o, def_hex, def_hex_label, def_facing, row_into, row_out_of, pair_info, dealt_base,
                 received_base, prone_def, defender_ams, no_return_fire):
        """evaluate's per-hex row for the mover on o's hex (speed only,
        2026-10-21): False when that hex can't be used (the defender's own hex,
        an off-board line, no LOS), else a tuple of everything about the hex
        that doesn't depend on the mover's facing or mode, then a 6-slot list
        evaluate fills per facing (side hit, arc class, AMS count) and the
        line's entry hexside at the mover."""
        atk_hex = o.hex_xy
        if atk_hex == def_hex:
            return False  # occupying the defender's hex is undefined, same as combat.py
        try:
            d_height = mech_height(prone_def, is_superheavy(self.defender))
            m_height = mech_height(False, is_superheavy(self.mover))
            atk_to_def, entry_at_def, distance, a_to_d = row_into.get(atk_hex) or pair_info(
                atk_hex, def_hex, self.terrain_map, m_height, d_height)
            def_to_atk, entry_at_atk, _, d_to_a = row_out_of.get(atk_hex) or pair_info(
                def_hex, atk_hex, self.terrain_map, d_height, m_height)
        except ValueError:
            return False  # off-board LOS line - not a usable candidate
        if not atk_to_def.los:
            return False  # no shot possible from here at all
        side_on_def = _SIDE_BY_RELATIVE_HEXSIDE[(entry_at_def - def_facing) % 6]
        # Water (2026-10-21): each side's firing case from here - None on dry ground.
        wet_dealt = wet_received = None
        if self.water_depths is not None:
            wet_dealt = self._wet(self.mover, o.label, False, self.defender, def_hex_label, prone_def)
            wet_received = self._wet(self.defender, def_hex_label, prone_def, self.mover, o.label, False)
        # The parts of each pre_tn fixed by the hex (the mover's AMM / TMM are added per state).
        dealt_hex = dealt_base + atk_to_def.modifier + (prone_target_modifier(self.defender, distance)
                                                        if prone_def else 0)
        received_hex = received_base + def_to_atk.modifier
        if no_return_fire:
            r_cls, r_keys = None, ()
        else:
            r_cls, r_keys = self._defender_classes.of(d_to_a, def_facing)
        k_def = defender_ams(d_to_a, def_facing) if defender_ams else 0
        return (atk_hex, atk_to_def, def_to_atk, distance, a_to_d, d_to_a, side_on_def, dealt_hex, received_hex,
                r_keys, r_cls, k_def, wet_dealt, wet_received, [None] * 6, entry_at_atk)

    def prepare(self, options) -> List[_Option]:
        """See prepare_options (this evaluator's mover)."""
        return prepare_options(self.mover, options)

    def evaluate(self, def_hex_label: str, def_facing_compass: str, def_fc: int, def_mode: str,
                 def_mp_spent: int, prepared: List[_Option], physical_reply: bool = True) -> List[MovementCandidate]:
        """Every prepared state with LOS to a defender standing at
        (def_hex_label, def_facing_compass) having moved def_mode / def_fc
        hexes / def_mp_spent MP. Same output the pre-2026-10-19
        evaluate_going_second produced, plus the two hit-table sides."""
        mover, defender, terrain_map = self.mover, self.defender, self.terrain_map
        def_hex = hex_geometry.parse_hex_label(def_hex_label)
        def_facing = hex_geometry.compass_to_facing(def_facing_compass)
        if self.defender_immobile:
            defender_tmm = IMMOBILE_TMM
            def_move_heat = 0
        else:
            defender_tmm = combat.fc_to_tmm(def_fc, jumped=(def_mode == "Jump"))
            def_move_heat = heat.movement_heat(defender, def_mode, def_fc)
        defender_tmm += target_size_modifier(defender)          # a superheavy is a Large target (Core p.240)
        def_amm = combat.MODE_TO_AMM[def_mode]
        dealt_stealth = equip.void_signature_modifier(defender, def_fc, def_mp_spent) + self.mover_own
        mover_cond, defender_cond = self.mover_cond, self.defender_cond
        mover_scorer, defender_scorer = self.mover_scorer, self.defender_scorer
        (mover_actions, mover_legs), (defender_actions, defender_legs) = self.mover_arcs, self.defender_arcs
        best_dealt, best_received = self._best_dealt, self._best_received   # best twist, memoized
        mover_class = self._mover_classes.of
        no_return_fire = defender.shutdown or defender_cond is None
        # The parts of each side's pre_tn that don't depend on the mover's spot (all
        # whole numbers, so adding them up front changes nothing - speed only).
        dealt_base = 0 if mover_cond is None else (mover.gunnery + defender_tmm + mover.heat_fire_modifier
                                                   + dealt_stealth + mover_cond[0])
        received_base = 0 if no_return_fire else (defender.gunnery + def_amm + defender.heat_fire_modifier
                                                  + self.defender_own + defender_cond[0])

        results: List[MovementCandidate] = []
        # Rows pinned on the defender's hex: lines INTO it (mover -> defender) and
        # OUT of it (defender -> mover), keyed by the mover's hex - plain dict gets
        # in the loop below; a miss falls back to pair_info (which fills the rows).
        # LOS heights (p.57): the mover stands at every spot; a prone defender is 1 level tall
        # (a superheavy 3 / 2 - Core p.240).
        prone_def = defender.prone
        d_height = mech_height(prone_def, is_superheavy(defender))
        m_height = mech_height(False, is_superheavy(mover))
        row_into = geo_cache.board(terrain_map, m_height, d_height).to.setdefault(def_hex, {})
        row_out_of = geo_cache.board(terrain_map, d_height, m_height).frm.setdefault(def_hex, {})
        pair_info = geo_cache.pair_info
        pre_min, pre_max = weapon_selection.PRE_TN_MIN, weapon_selection.PRE_TN_MAX
        water_depths = self.water_depths
        mover_ams = self.mover_ams.engagements if self.mover_ams.ams else None
        defender_ams = self.defender_ams.engagements if self.defender_ams.ams else None
        # Speed only (2026-10-21): what depends on the mover's HEX alone (the LOS rows,
        # the side it hits, the defender's arc class, both to-hit bases, water) is
        # worked out once per hex per call, and what depends on (hex, facing) once per
        # facing - a hex holds ~8 states (facings x modes). Same numbers, same order.
        per_hex: Dict[str, object] = {}
        for o in prepared:
            h = per_hex.get(o.label)
            if h is None:
                h = per_hex[o.label] = self._hex_row(o, def_hex, def_hex_label, def_facing, row_into, row_out_of,
                                                     pair_info, dealt_base, received_base, prone_def, defender_ams,
                                                     no_return_fire)
            if h is False:
                continue
            (atk_hex, atk_to_def, def_to_atk, distance, a_to_d, d_to_a, side_on_def, dealt_hex, received_hex,
             r_keys, r_cls, k_def, wet_dealt, wet_received, by_facing, entry_at_atk) = h
            f = by_facing[o.facing]
            if f is None:
                f = by_facing[o.facing] = (
                    _SIDE_BY_RELATIVE_HEXSIDE[(entry_at_atk - o.facing) % 6],
                    mover_class(a_to_d, o.facing),
                    mover_ams(a_to_d, o.facing) if mover_ams else 0)
            side_on_mover, (cls, keys), k_mov = f

            if mover_cond is None or wet_dealt == "none":
                dealt = 0.0
            else:
                pre_tn = dealt_hex + o.amm
                pre_tn = pre_max if pre_tn > pre_max else (pre_min if pre_tn < pre_min else pre_tn)
                memo_key = (cls, distance, pre_tn, o.move_heat, side_on_def, k_def, wet_dealt)
                dealt = best_dealt.get(memo_key)
                if dealt is None:
                    dealt = best_dealt[memo_key] = max(
                        mover_scorer(key, ams_k=k_def, wet=wet_dealt)(distance, pre_tn, o.move_heat, side_on_def)
                        for key in keys)

            if no_return_fire or wet_received == "none":
                received = 0.0
            else:
                pre_tn2 = received_hex + o.tmm + o.void_mod
                pre_tn2 = pre_max if pre_tn2 > pre_max else (pre_min if pre_tn2 < pre_min else pre_tn2)
                memo_key = (r_cls, distance, pre_tn2, def_move_heat, side_on_mover, k_mov, wet_received)
                received = best_received.get(memo_key)
                if received is None:
                    received = best_received[memo_key] = max(
                        defender_scorer(key, ams_k=k_mov, wet=wet_received)(distance, pre_tn2, def_move_heat,
                                                                           side_on_mover)
                        for key in r_keys)

            if distance == 1:
                levels = terrain_map["hexes"]
                a_level, d_level = levels[o.label]["level"], levels[def_hex_label]["level"]
                if self.mover_physical:
                    base = physical.base_tn(mover, o.amm, defender_tmm, atk_to_def.modifier,
                                            prone_target_modifier(defender, 1))
                    dealt = _with_physical(
                        dealt, self.mover_planner, mover_actions, mover_legs, a_to_d, o.facing, d_level - a_level,
                        prone_def, base, side_on_def,
                        (lambda key, held: mover_scorer(key, held, k_def, wet_dealt)(distance, pre_tn, o.move_heat,
                                                                                      side_on_def))
                        if mover_cond is not None and wet_dealt != "none" else None,
                        self.mover_planner.push_plan(atk_hex, o.facing, a_level, defender, def_hex_label, d_level,
                                                     base, side_on_def, terrain_map),
                        *self._physical_water(o.label, False, def_hex_label, prone_def,
                                              is_superheavy(mover), is_superheavy(defender)))
                if self.defender_physical and physical_reply:   # nobody punches a mech in mid-DFA
                    base = physical.base_tn(defender, def_amm, o.tmm, def_to_atk.modifier, 0)
                    received = _with_physical(
                        received, self.defender_planner, defender_actions, defender_legs, d_to_a, def_facing,
                        a_level - d_level, False, base, side_on_mover,
                        (lambda key, held: defender_scorer(key, held, k_mov, wet_received)(distance, pre_tn2,
                                                                                            def_move_heat, side_on_mover))
                        if not no_return_fire and wet_received != "none" else None,
                        self.defender_planner.push_plan(def_hex, def_facing, d_level, mover, o.label, a_level,
                                                        base, side_on_mover, terrain_map),
                        *self._physical_water(def_hex_label, prone_def, o.label, False,
                                              is_superheavy(defender), is_superheavy(mover)))

            results.append(MovementCandidate(o.label, o.facing_compass, o.mode, o.fc, o.mp_spent, distance,
                                             dealt, received, o.move_heat, side_on_def, side_on_mover))
        return results


def evaluate_going_second(
    mover, defender, terrain_map: Dict[str, object], defender_state: Optional[Dict[str, object]] = None,
    standup_mp: Optional[int] = None, entry_edge: Optional[List[str]] = None,
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

    standup_mp / entry_edge: see movement_options (after standing up /
    entering the battlefield).

    Returns every (hex, facing, mode) candidate mover can reach with LOS
    to the defender - intentionally UNREDUCED and UNRANKED. A thin wrapper
    over MoveEvaluator since 2026-10-19; the result is unchanged.
    """
    if defender_state is None:
        defender_state = {"fc": 0, "mode": "Stand Still"}
    evaluator = MoveEvaluator(mover, defender, terrain_map)
    prepared = evaluator.prepare(movement_options(mover, terrain_map, standup_mp, entry_edge))
    return evaluator.evaluate(defender.hex, defender.facing, defender_state["fc"], defender_state["mode"],
                              defender.mp_spent, prepared)


# =============================================================================
# ==========================  THE PATH TO A PICK  =============================
# =============================================================================
def path_to(mover, terrain_map, pick, standup_mp=None, entry_edge=None, tables=None):
    """The ground path to a picked end state (2026-10-21, Daniel's movement
    subphase: "There is a difference between planning where you want to go
    which the picker does. And actually getting there"): the same search
    movement_options ran (pathfinder.build_movement_table with keep_parents),
    walked back from the pick. Returns [(step, (x, y, facing), mp after)] -
    step "enter" (onto the board, first), "forward", "backward" or "turn" -
    or None when no such path is found (then the move is applied whole).
    tables: a dict to keep the searched tables in, so asking for many picks
    from one spot searches once (PathBook, 2026-10-28)."""
    def table_for(x0, y0, f0, budget, backward_mp=None):
        key = (x0, y0, f0, budget, backward_mp)
        got = tables.get(key) if tables is not None else None
        if got is None:
            got = build_movement_table(x0, y0, f0, budget, terrain_map=terrain_map, backward_mp=backward_mp,
                                       level_limit=level_limit, keep_parents=True,
                                       blocked=getattr(mover, "blocked_hex", None))
            if tables is not None:
                tables[key] = got
        return got

    x, y = hex_geometry.parse_hex_label(pick["hex"])
    state = (x, y, hex_geometry.compass_to_facing(pick["facing"]))
    fc, mp = pick["fc"], pick["mp_spent"]
    level_limit = terrain_rules.max_level_change(ground_level_limited(mover), is_superheavy(mover))
    if entry_edge is not None:
        run = compute_running_mp(mover)
        for label in entry_edge:
            info = terrain_map["hexes"].get(label)
            cost = terrain_rules.step_cost(None, info) if info is not None else None
            if cost is None or cost > mp:
                continue
            ex, ey = hex_geometry.parse_hex_label(label)
            for f0 in range(6):
                table = table_for(ex, ey, f0, run - cost)
                if table.get(state, {}).get(mp - cost) == fc - 1:
                    return [("enter", (ex, ey, f0), cost)] + [(s, st, m + cost)
                                                              for s, st, m in table.path(state, mp - cost)]
        return None
    sx, sy, start_facing = hex_geometry.state_from_label(mover.hex, mover.facing)
    if standup_mp is None:
        walk = compute_walk_mp(mover)
        starts, budget = [start_facing], compute_running_mp(mover)
        backward_mp = walk if walk > 0 else None
        dx, dy = hex_geometry.FACING_DELTAS[start_facing]
        if (fc == 1 and pick["mode"] == "Run" and state == (sx + dx, sy + dy, start_facing)
                and mp == budget and _minimum_move(mover, terrain_map, sx, sy, start_facing, budget, set(),
                                                   level_limit) is not None):
            return [("forward", state, mp)]            # Minimum Movement (p.49): the one step
    else:
        starts, budget, backward_mp = range(6), standup_mp, None
    for f0 in starts:
        table = table_for(sx, sy, f0, budget, backward_mp)
        if table.get(state, {}).get(mp) == fc:
            return table.path(state, mp)
    return None


class PathBook:
    """The ground path to each of one pick's end states (path_to), the
    searches shared - for a bot that prices every hex a path enters
    (Princess's checkPathForHazards, 2026-10-28)."""

    def __init__(self, mover, terrain_map, standup_mp=None, entry_edge=None):
        self.mover, self.terrain_map = mover, terrain_map
        self.standup_mp, self.entry_edge = standup_mp, entry_edge
        self._tables = {}

    def path(self, o):
        """[(step, (x, y, facing), mp after)] for prepared state o, None if not found."""
        pick = {"hex": o.label, "facing": o.facing_compass, "mode": o.mode, "fc": o.fc, "mp_spent": o.mp_spent}
        return path_to(self.mover, self.terrain_map, pick, self.standup_mp, self.entry_edge, self._tables)
