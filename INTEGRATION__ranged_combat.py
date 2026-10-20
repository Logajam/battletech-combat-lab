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
from pathfinder import build_movement_table  # noqa: E402
import terrain_rules  # noqa: E402
from los import has_los, hex_distance  # noqa: E402
import combat  # noqa: E402

import INTEGRATION__weapon_selection as weapon_selection  # noqa: E402
import INTEGRATION__heat as heat  # noqa: E402
import INTEGRATION__equipment_systems as equip  # noqa: E402
import INTEGRATION__ammo as ammo  # noqa: E402
import INTEGRATION__structure_weight as structure_weight  # noqa: E402
import INTEGRATION__arcs as arcs  # noqa: E402
import INTEGRATION__ams as ams  # noqa: E402
import INTEGRATION__los_cache as geo_cache  # noqa: E402
from INTEGRATION__attack_resolution import tn_adjuster, aimed_shot_location, firing_conditions, \
    prone_target_modifier, arc_unavailable, _SIDE_BY_RELATIVE_HEXSIDE  # noqa: E402
import INTEGRATION__physical as physical  # noqa: E402

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


def _make_heat_limited_scorer(mech, tn_adjust, unavailable=frozenset(), scale_for_side=None):
    """Returns score(distance, pre_tn, move_heat) -> expected damage of the
    weapons select_weapons_to_fire() would actually fire, memoized for this
    call. Dissipation and other heat are read once (they can't change
    mid-movement); tn_adjust is the per-weapon stealth/aim change against
    this scorer's target.

    scale_for_side (2026-10-19): optional f(side) -> {id(weapon): multiplier}
    (INTEGRATION__structure_weight, built per target); when given, score() takes
    the attack side too and returns WORTH - expected damage with structure
    damage counted for more - and the memo is keyed by side as well."""
    dissipation = compute_heat_dissipation(mech)
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
                unavailable=unavailable, value_scale=scale, weapons=weapons, table=table)
            memo[key] = cached
        return cached

    return score


def movement_options(mover, terrain_map, standup_mp=None, entry_edge=None, backward=True):
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
    target's hex, and its hex count would restart after a backward step)."""
    if entry_edge is not None:
        yield from _entry_options(mover, terrain_map, entry_edge)
        return
    sx, sy, start_facing = hex_geometry.state_from_label(mover.hex, mover.facing)
    if standup_mp is None:
        walk = compute_walk_mp(mover)
        starts, run_budget, jump_mp = [start_facing], compute_running_mp(mover), compute_jump_mp(mover)
        mode_for = lambda spent: combat.classify_movement_mode(spent, walk)  # noqa: E731
        backward_mp = walk if backward and walk > 0 else None
    else:
        starts, run_budget, jump_mp = range(6), standup_mp, 0
        mode_for = lambda spent: "Run"  # noqa: E731
        backward_mp = None
    seen = set()
    for f0 in starts:
        for (x, y, facing), col in build_movement_table(sx, sy, f0, run_budget, terrain_map=terrain_map,
                                                        backward_mp=backward_mp).items():
            for mp_spent, fc in col.items():
                key = (x, y, facing, fc, mode_for(mp_spent), mp_spent)
                if key not in seen:
                    seen.add(key)
                    yield key
    if jump_mp > 0:
        for (x, y, facing), fc in combat.build_jump_states(sx, sy, jump_mp, terrain_map).items():
            yield (x, y, facing, fc, "Jump", jump_mp)


def _entry_options(mover, terrain_map, edge_labels):
    walk, run = compute_walk_mp(mover), compute_running_mp(mover)
    seen = set()
    for label in edge_labels:
        info = terrain_map["hexes"].get(label)
        if info is None or info["impassable"]:
            continue
        cost = terrain_rules.transition_cost(info["level"], info["level"], info["features"])
        if cost > run:
            continue
        ex, ey = hex_geometry.parse_hex_label(label)
        for f0 in range(6):
            for (x, y, facing), col in build_movement_table(ex, ey, f0, run - cost, terrain_map=terrain_map).items():
                for spent, fc in col.items():
                    total = spent + cost
                    key = (x, y, facing, fc + 1, combat.classify_movement_mode(total, walk), total)
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
        o.tmm = combat.fc_to_tmm(fc, jumped=(mode == "Jump"))
        o.void_mod = equip.void_signature_modifier(mover, fc, mp_spent)
        prepared.append(o)
    return prepared


def _with_physical(ranged_best, planner, actions, legs, pair_arcs, facing, diff, target_prone, base, side,
                   ranged_for, push=()):
    """Best expected damage from a spot next to the enemy counting the
    Physical phase too: for every arc action and physical plan, the ranged
    fire without the weapons in the attacking limbs (pp.76, 82) plus the
    plan's expected damage. ranged_for(key, held) gives the ranged part
    (None: no ranged fire possible); ranged_best is the no-physical value."""
    best = ranged_best
    if abs(diff) > 1:
        return best
    for key, signature in planner.cases(pair_arcs, facing, actions, legs):
        for value, limbs, _ in planner.plans_in_case(signature, diff, target_prone, base, side):
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
    """

    def __init__(self, mover, defender, terrain_map: Dict[str, object]):
        self.mover, self.defender, self.terrain_map = mover, defender, terrain_map
        self.defender_immobile = is_immobile(defender)
        self.mover_cond = firing_conditions(mover)          # mover is standing here; sensors still count
        self.defender_cond = firing_conditions(defender)
        mover_blocked = (self.mover_cond[1] if self.mover_cond else frozenset()) | ammo.unavailable_weapons(mover)
        defender_blocked = (self.defender_cond[1] if self.defender_cond else frozenset()) \
            | ammo.unavailable_weapons(defender)
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

        def scorer_getter(who, adjust, blocked, scale, cache):
            # Scorers are shared by every (key, held) that leaves the same weapons
            # unable to fire (2026-10-20, speed only): many twists / arcs block the
            # same set, and a shared scorer shares its memo.
            by_unavailable: Dict[tuple, object] = {}
            usable = [w for w in get_weapons(who) if id(w) not in blocked]

            def get(key, held=frozenset(), ams_k=0):
                # held: weapons kept back because their limb attacks in the Physical phase
                # ams_k: attacks the target's AMS can engage from here (INTEGRATION__ams, p.206)
                scorer = cache.get((key, held, ams_k))
                if scorer is None:
                    unavailable = blocked | arc_unavailable(who, key) | held
                    scorer = by_unavailable.get((unavailable, ams_k))
                    if scorer is None:
                        side_scale = scale
                        factors = ams.damage_factors(usable, ams_k) if ams_k else None
                        if factors:
                            side_scale = lambda side: ams.combine(scale(side) if scale else None, factors)  # noqa: E731
                        scorer = by_unavailable[(unavailable, ams_k)] = _make_heat_limited_scorer(
                            who, adjust, unavailable, side_scale)
                    cache[(key, held, ams_k)] = scorer
                return scorer
            return get
        self.mover_scorer = scorer_getter(mover, mover_adjust, mover_blocked, mover_scale, mover_scorers)
        self.defender_scorer = scorer_getter(defender, defender_adjust, defender_blocked, defender_scale, defender_scorers)
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
        def_amm = combat.MODE_TO_AMM[def_mode]
        dealt_stealth = equip.void_signature_modifier(defender, def_fc, def_mp_spent) + self.mover_own
        mover_cond, defender_cond = self.mover_cond, self.defender_cond
        mover_scorer, defender_scorer = self.mover_scorer, self.defender_scorer
        (mover_actions, mover_legs), (defender_actions, defender_legs) = self.mover_arcs, self.defender_arcs
        best_dealt, best_received = self._best_dealt, self._best_received   # best twist, memoized
        mover_class, defender_class = self._mover_classes.of, self._defender_classes.of
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
        board = geo_cache.board(terrain_map)
        row_into = board.to.setdefault(def_hex, {})
        row_out_of = board.frm.setdefault(def_hex, {})
        pair_info = geo_cache.pair_info
        pre_min, pre_max = weapon_selection.PRE_TN_MIN, weapon_selection.PRE_TN_MAX
        prone_def = defender.prone
        mover_ams = self.mover_ams.engagements if self.mover_ams.ams else None
        defender_ams = self.defender_ams.engagements if self.defender_ams.ams else None
        for o in prepared:
            atk_hex = o.hex_xy
            if atk_hex == def_hex:
                continue  # occupying the defender's hex is undefined, same as combat.py
            try:
                atk_to_def, entry_at_def, distance, a_to_d = row_into.get(atk_hex) or pair_info(atk_hex, def_hex, terrain_map)
                def_to_atk, entry_at_atk, _, d_to_a = row_out_of.get(atk_hex) or pair_info(def_hex, atk_hex, terrain_map)
            except ValueError:
                continue  # off-board LOS line - not a usable candidate
            if not atk_to_def.los:
                continue  # no shot possible from here at all
            side_on_def = _SIDE_BY_RELATIVE_HEXSIDE[(entry_at_def - def_facing) % 6]
            side_on_mover = _SIDE_BY_RELATIVE_HEXSIDE[(entry_at_atk - o.facing) % 6]

            if mover_cond is None:
                dealt = 0.0
            else:
                pre_tn = (dealt_base + o.amm + atk_to_def.modifier
                          + (prone_target_modifier(defender, distance) if prone_def else 0))
                pre_tn = pre_max if pre_tn > pre_max else (pre_min if pre_tn < pre_min else pre_tn)
                cls, keys = mover_class(a_to_d, o.facing)
                k_def = defender_ams(d_to_a, def_facing) if defender_ams else 0
                memo_key = (cls, distance, pre_tn, o.move_heat, side_on_def, k_def)
                dealt = best_dealt.get(memo_key)
                if dealt is None:
                    dealt = best_dealt[memo_key] = max(
                        mover_scorer(key, ams_k=k_def)(distance, pre_tn, o.move_heat, side_on_def) for key in keys)

            if no_return_fire:
                received = 0.0
            else:
                pre_tn2 = received_base + o.tmm + def_to_atk.modifier + o.void_mod
                pre_tn2 = pre_max if pre_tn2 > pre_max else (pre_min if pre_tn2 < pre_min else pre_tn2)
                cls, keys = defender_class(d_to_a, def_facing)
                k_mov = mover_ams(a_to_d, o.facing) if mover_ams else 0
                memo_key = (cls, distance, pre_tn2, def_move_heat, side_on_mover, k_mov)
                received = best_received.get(memo_key)
                if received is None:
                    received = best_received[memo_key] = max(
                        defender_scorer(key, ams_k=k_mov)(distance, pre_tn2, def_move_heat, side_on_mover)
                        for key in keys)

            if distance == 1:
                levels = terrain_map["hexes"]
                a_level, d_level = levels[o.label]["level"], levels[def_hex_label]["level"]
                if self.mover_physical:
                    base = physical.base_tn(mover, o.amm, defender_tmm, atk_to_def.modifier,
                                            prone_target_modifier(defender, 1))
                    dealt = _with_physical(
                        dealt, self.mover_planner, mover_actions, mover_legs, a_to_d, o.facing, d_level - a_level,
                        prone_def, base, side_on_def,
                        (lambda key, held: mover_scorer(key, held, k_def)(distance, pre_tn, o.move_heat, side_on_def))
                        if mover_cond is not None else None,
                        self.mover_planner.push_plan(atk_hex, o.facing, a_level, defender, def_hex_label, d_level,
                                                     base, side_on_def, terrain_map))
                if self.defender_physical and physical_reply:   # nobody punches a mech in mid-DFA
                    base = physical.base_tn(defender, def_amm, o.tmm, def_to_atk.modifier, 0)
                    received = _with_physical(
                        received, self.defender_planner, defender_actions, defender_legs, d_to_a, def_facing,
                        a_level - d_level, False, base, side_on_mover,
                        (lambda key, held: defender_scorer(key, held, k_mov)(distance, pre_tn2, def_move_heat, side_on_mover))
                        if not no_return_fire else None,
                        self.defender_planner.push_plan(def_hex, def_facing, d_level, mover, o.label, a_level,
                                                        base, side_on_mover, terrain_map))

            results.append(MovementCandidate(
                hex=o.label, facing=o.facing_compass, mode=o.mode,
                fc=o.fc, mp_spent=o.mp_spent, distance=distance, dealt=dealt, received=received,
                movement_heat=o.move_heat,
                side_on_defender=side_on_def, side_on_mover=side_on_mover,
            ))
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
