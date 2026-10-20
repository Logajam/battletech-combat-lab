"""
INTEGRATION__movement_selection.py  (NEW 2026-10-19, Claude - Pile 4: the movement decision)

Where a mech chooses the spot (hex, facing, movement mode) it ends its
Movement Phase in. Replaces INTEGRATION__stubs.stub_select_movement.

=== THE OBJECTIVE (Daniel, 2026-10-19) ===
    score = dealt / (received + PSR cost + 0.001)
where, for a candidate spot,
  dealt     expected damage this mech deals from there (the same heat-, ammo-,
            arc- and to-hit-aware number Ranged Combat will actually fire -
            INTEGRATION__ranged_combat.MoveEvaluator), times the target's
            EXPOSURE FACTOR for the side the shots land on. From a spot
            next to the enemy it also counts the Physical phase (2026-10-19):
            the best twist + ranged fire + punch / kick / physical weapon,
            with the weapons in an attacking limb held back (pp.76, 82);
  received  expected damage the enemy's return fire deals (physical attacks
            included the same way), times THIS mech's exposure factor for
            the side those shots land on;
  PSR cost  expected fall damage from the Movement Phase piloting roll the
            move would force (see below), added to received;
  0.001     keeps a spot with no return fire from dividing by zero
            (PATHFINDER combat.RATIO_EPSILON's value).
Higher is better. Ties go to the spot nearest the enemy, then a seeded random
pick (the second mover only - see "two-ply").

=== EXPOSURE FACTOR (Daniel's idea, 2026-10-19; formula is Claude's) ===
Damage costs more when it lands on thin armor. Attack direction is real now
(Core p.73, INTEGRATION__attack_resolution.attack_side), so each shot has a
known side (front/left/right/rear). For one mech and one side:
    vulnerability = sum over hit-table rolls of  P(roll) / durability(location)
where durability = the armor that side actually depletes (rear armor for a
rear hit on a torso, else front armor) + structure, from the mech's CURRENT
state, following the damage-transfer map past destroyed locations.
    factor(side) = vulnerability(side) / vulnerability(front), clamped to
    [MOVEMENT_EXPOSURE_MIN, MOVEMENT_EXPOSURE_MAX]
so a shot from the front counts 1.0, and a rear shot into thin rear armor
counts more. Because it reads current armor, a mech with a stripped side
turns that side away, and shoots at the enemy's weak side. Applied both ways
(dealt uses the target's factor). MOVEMENT_EXPOSURE_WEIGHTING = False turns
it off. Partial cover is already in the to-hit (LOS modifier).

=== PSR COST (Daniel, 2026-10-19: only Movement-phase PSRs; ignore damage-
    caused PSRs) ===
Running 1+ hex or jumping forces a roll only if the mech is damaged the way
piloting_rolls.movement_psr_trigger names (gyro hit, hip/leg destroyed while
running, leg actuator/leg destroyed while jumping); walking never does
(Core p.111). cost = P(roll < target number) x fall damage, with the target
number and fall damage read from piloting_rolls (the same code the dice
use). An undamaged mech pays 0 everywhere, so this term does nothing until a
mech is hurt. NOT scored: the seatbelt pilot-hit chance and being prone
afterwards (neither is a damage number). Mines/lava: no terrain model yet.

=== TWO-PLY (Daniel, 2026-10-19: "we need the 2 ply in order for both sides
    to move intelligently") ===
  - The SECOND mover sees the enemy's final position, so its scores are real:
    one pass over its reachable spots.
  - The FIRST mover scores each reachable spot c by the reply the second mover
    would actually make from there. The reply is chosen by the same rule the
    real second mover uses (objective above, then the closing fallback), run
    with the first mover pinned at c - so the first mover plans against the
    opponent it will really face, not a hypothetical one. Independently
    greedy, not adversarial (PATHFINDER__combat_turn.py's design). The first
    mover's score for c is the objective computed from that reply's numbers
    read the other way round (what the reply receives is what the first mover
    deals).
  - Modeled reply options mirror _phase_movement: an immobile enemy stays put;
    a prone enemy stays put (declared Run if it can try to stand - whether it
    stands is a dice roll, not modeled); an enemy that hasn't entered the
    board yet is not modeled (head for its home edge instead).
  - Both mechs' spots are reduced first (below). MOVEMENT_TWO_PLY = False makes
    the first mover score against the enemy standing where it is now.

=== REDUCTION (PATHFINDER__combat_turn.py Section 5c, still valid) ===
For a given (hex, facing, mode), only the highest forward count is kept
(lowest MP on a tie): a higher forward count never hurts - accuracy depends on
mode, TMM only rises. Kept SEPARATE: forward count 0 vs 1+ (running 1+ hex is
what triggers the PSR). Jumps already carry one count per (hex, facing). The
one place this is not safe is a Void-Signature System, whose TN bonus falls as
hexes moved rise: reduced_options skips the reduction for a mech with one live
(Daniel, 2026-10-19). tests/test_movement_selection.py checks the reduction
against the full list, for a standard mech and for a Void-Signature mech.

=== CLOSING FALLBACK (ported as-is from PATHFINDER__combat_turn.py, Daniel
    2026-10-19: "Port as is. Working system first.") ===
Used only when no spot deals any damage. Brackets are measured with the mech's
single longest-range weapon: 0 Short, 1 Medium, 2 Long, 3 out of range.
  Case A  (this mech's max weapon range < the enemy's)  or
  Case B1 (>= the enemy's but currently out of range): drop spots that don't
          strictly improve the bracket; score the rest dealt / brackets
          closed; ties go to the spot closing the most (flagged in the
          original, kept).
  Case B2 (>= the enemy's and already in range - so a LOS block, not a range
          problem): the board hex nearest the mech with LOS to the enemy that
          isn't closer-in-bracket becomes a seed; take the reachable spot
          nearest the seed that isn't closer-in-bracket either.
Edge cases where it finds nothing return "no override": the mech then moves to
the reachable spot nearest the enemy. Adaptation: the old code read flat
weapon dicts; this reads the mech's live weapons (Equipment.weapon_range).
The old code's "real damage" probe is the static-enemy evaluation's dealt.

Nothing here is a BattleTech rule: it is a scoring and search policy. Its
knobs live in INTEGRATION__config.py (MOVEMENT SETTINGS).
"""

import os
import sys
from typing import Dict, List, Optional, Tuple

MECHSIM_DIR = os.environ.get("MECHSIM_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "mechsim"))
PATHFINDER_DIR = os.environ.get("PATHFINDER_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "pathfinder"))
if MECHSIM_DIR not in sys.path:
    sys.path.insert(0, MECHSIM_DIR)

import INTEGRATION__config as config  # noqa: E402 - registers bare "config" before any MECHSIM import
from mech_state import is_immobile, compute_running_mp  # noqa: E402
from damage_resolution import get_weapons, TRANSFER_MAP  # noqa: E402
import hit_location  # noqa: E402
import piloting_rolls  # noqa: E402

if PATHFINDER_DIR not in sys.path:
    sys.path.insert(0, PATHFINDER_DIR)

import hex_geometry  # noqa: E402
import combat  # noqa: E402
from los import hex_distance  # noqa: E402

import INTEGRATION__ranged_combat as ranged_combat  # noqa: E402
import INTEGRATION__structure_weight as structure_weight  # noqa: E402
import INTEGRATION__los_cache as geo_cache  # noqa: E402
import INTEGRATION__equipment_systems as equipment_systems  # noqa: E402
import INTEGRATION__charge as charge  # noqa: E402

SIDES = ("front", "left", "right", "rear")
_P_2D6 = {roll: (6 - abs(roll - 7)) / 36 for roll in range(2, 13)}


# =============================================================================
# ===========================  EXPOSURE  ======================================
# =============================================================================
def _vulnerability(mech, side):
    """sum over hit-table rolls of P(roll) / durability(location) for shots
    landing on `side` of `mech`, from its current armor and structure
    (structure_weight.hit_spread does the table walk)."""
    return structure_weight.vulnerability(structure_weight.hit_spread(mech, side))


def exposure_factors(mech) -> Dict[str, float]:
    """{side: factor}: how much a point of damage landing on that side matters
    compared with the front, from current armor. See the module docstring."""
    if not config.MOVEMENT_EXPOSURE_WEIGHTING:
        return dict.fromkeys(SIDES, 1.0)
    vuln = {side: _vulnerability(mech, side) for side in SIDES}
    reference = vuln["front"]
    if reference <= 0:
        return dict.fromkeys(SIDES, 1.0)
    lo, hi = config.MOVEMENT_EXPOSURE_MIN, config.MOVEMENT_EXPOSURE_MAX
    factors = {side: max(lo, min(hi, vuln[side] / reference)) for side in SIDES}
    factors["front"] = 1.0
    return factors


# =============================================================================
# ===========================  PSR COST  ======================================
# =============================================================================
def psr_costs(mech) -> Dict[str, float]:
    """{"Run": expected fall damage, "Jump": expected fall damage} for this
    mech's CURRENT damage; 0 where no roll is forced. Run's cost only applies
    when the mech moves 1+ hex (a caller checks that)."""
    costs = {"Run": 0.0, "Jump": 0.0}
    if not config.MOVEMENT_PSR_COST:
        return costs
    for mode, psr_mode in (("Run", "running"), ("Jump", "jump")):
        target = piloting_rolls.movement_psr_target_number(mech, psr_mode)
        if target is None:
            continue
        p_fail = 1.0 - combat.hit_probability(target)     # the roll fails when it is under the target
        costs[mode] = p_fail * piloting_rolls.fall_damage(mech)
    return costs


class _Side:
    """One mech's per-pick scoring inputs: exposure table and PSR prices."""

    def __init__(self, mech, psr_applies=True):
        self.mech = mech
        self.exposure = exposure_factors(mech)
        self._psr = psr_costs(mech) if psr_applies else {"Run": 0.0, "Jump": 0.0}

    def psr_cost(self, mode, fc):
        if mode == "Run":
            return self._psr["Run"] if fc >= 1 else 0.0   # check_movement_psr's gate: Run 1+ hex
        if mode == "Jump":
            return self._psr["Jump"]
        return 0.0


# =============================================================================
# ===========================  CANDIDATE SETS  ================================
# =============================================================================
def reduced_options(mover, terrain_map, exclude_hex=None, standup_mp=None, entry_edge=None):
    """The mover's reachable end states after the Section 5c reduction, as
    (x, y, facing, fc, mode, mp_spent) tuples in a stable order. exclude_hex
    (a label or None) is a hex that is occupied and can't be ended in."""
    exclude_xy = hex_geometry.parse_hex_label(exclude_hex) if exclude_hex else None
    void = "void_signature" in equipment_systems.active_stealth(mover)
    best: Dict[tuple, tuple] = {}
    for x, y, facing, fc, mode, mp_spent in ranged_combat.movement_options(mover, terrain_map, standup_mp, entry_edge):
        if (x, y) == exclude_xy:
            continue
        # A live Void-Signature System's TN bonus FALLS as hexes moved rise
        # (0 hexes +3 ... 6+ hexes 0), so for it more movement is not
        # "never worse" (Daniel, 2026-10-19): keep every (fc, MP) variant.
        key = (x, y, facing, mode, fc, mp_spent) if void else (x, y, facing, mode, fc > 0)
        cur = best.get(key)
        if cur is None or fc > cur[3] or (fc == cur[3] and mp_spent < cur[5]):
            best[key] = (x, y, facing, fc, mode, mp_spent)
    return list(best.values())


def _opponent_options(other, terrain_map):
    """The reachable states a modeled second mover could end in, mirroring
    orchestrator._phase_movement: immobile and prone mechs stay put."""
    x, y, facing = hex_geometry.state_from_label(other.hex, other.facing)
    if is_immobile(other):
        return [(x, y, facing, 0, "Stand Still", 0)]
    if other.prone:
        tries = other.pilot_hits < 5 and compute_running_mp(other) > 0   # resolve_stand_up's own gates
        return [(x, y, facing, 0, "Run" if tries else "Stand Still", 0)]
    return reduced_options(other, terrain_map)


def _pick_dict(o) -> Dict[str, object]:
    return {"hex": o.label, "facing": o.facing_compass, "mode": o.mode, "fc": o.fc, "mp_spent": o.mp_spent}


# =============================================================================
# ===========================  SCORING  =======================================
# =============================================================================
def _objective(dealt, received, dealt_mult, received_mult, extras):
    return (dealt * dealt_mult) / (received * received_mult + extras + config.MOVEMENT_RATIO_EPSILON)


def _nearest_to(options, target_xy, rng=None):
    """Of `options` (prepared states), those nearest target_xy; one is chosen
    with the seeded rng, or the first when rng is None (a modeled reply must
    not consume the battle's random stream)."""
    nearest = min(hex_distance(o.hex_xy, target_xy) for o in options)
    pool = [o for o in options if hex_distance(o.hex_xy, target_xy) == nearest]
    return pool[rng.pick_number(len(pool)) - 1] if rng is not None and len(pool) > 1 else pool[0]


def _best_by_score(scored, enemy_xy, rng=None):
    """scored: [(score, prepared_state, payload)]. Highest score; ties (to 9
    places) go to the state nearest the enemy, then rng / first."""
    top = max(round(s, 9) for s, _, _ in scored)
    tied = [(o, payload) for s, o, payload in scored if round(s, 9) == top]
    nearest = min(hex_distance(o.hex_xy, enemy_xy) for o, _ in tied)
    tied = [(o, payload) for o, payload in tied if hex_distance(o.hex_xy, enemy_xy) == nearest]
    return tied[rng.pick_number(len(tied)) - 1] if rng is not None and len(tied) > 1 else tied[0]


# =============================================================================
# ===========================  CLOSING FALLBACK  ==============================
# =============================================================================
def _weapon_ranges(mech):
    """Live weapons with confirmed range data."""
    return [w for w in get_weapons(mech) if w.weapon_range and w.weapon_range.get("long") is not None]


def _max_range(mech) -> int:
    return max((w.weapon_range["long"] for w in _weapon_ranges(mech)), default=0)


def _longest_range_weapon(mech):
    weapons = _weapon_ranges(mech)
    return max(weapons, key=lambda w: w.weapon_range["long"]) if weapons else None


def _bracket(distance, weapon) -> int:
    """0 Short, 1 Medium, 2 Long, 3 out of range, for one weapon (Daniel
    2026-07-21: the fallback compares brackets, not raw distance)."""
    wr = weapon.weapon_range
    if distance <= wr["short"]:
        return 0
    if distance <= wr["medium"]:
        return 1
    if distance <= wr["long"]:
        return 2
    return 3


def closing_fallback(mover, other, options, enemy_xy, dealt_for, terrain_map, exclude_xy=None):
    """Ported from PATHFINDER__combat_turn._closing_fallback (module
    docstring). options: prepared states; dealt_for(option) -> expected damage
    dealt from there against the enemy as it stands (0 with no LOS). Returns
    the chosen option, or None when an edge case leaves nothing to override."""
    weapon = _longest_range_weapon(mover)
    if weapon is None:
        return None                      # nothing that can shoot: no bracket to close
    mover_xy = hex_geometry.parse_hex_label(mover.hex) if mover.hex is not None else None
    # A mech still off the board counts as out of range (bracket 3).
    initial_bracket = _bracket(hex_distance(mover_xy, enemy_xy), weapon) if mover_xy is not None else 3
    pool = [o for o in options if o.hex_xy != exclude_xy]

    if _max_range(mover) < _max_range(other) or initial_bracket == 3:
        # Case A / B1: close the range, scored by damage per bracket closed.
        best, best_score, best_denom = None, None, None
        for o in pool:
            bracket = _bracket(hex_distance(o.hex_xy, enemy_xy), weapon)
            if bracket >= initial_bracket:
                continue                 # doesn't strictly close the range
            denom = initial_bracket - bracket
            score = dealt_for(o) / denom
            # Tie-break flagged in the original (not specified by Daniel): on an
            # equal score, whichever closes the range the most.
            if best is None or score > best_score or (score == best_score and denom > best_denom):
                best, best_score, best_denom = o, score, denom
        return best

    # Case B2: already in range, so LOS is the problem. Find the nearest board
    # hex with LOS to the enemy that isn't closer-in-bracket, then head for it.
    seed_xy, seed_dist = None, None
    for label, info in terrain_map["hexes"].items():
        if info["impassable"]:
            continue
        cell = hex_geometry.parse_hex_label(label)
        if cell == mover_xy:
            continue
        if _bracket(hex_distance(cell, enemy_xy), weapon) < initial_bracket:
            continue
        try:
            los = geo_cache.los(cell, enemy_xy, terrain_map)
        except ValueError:
            continue
        if not los.los:
            continue
        dist = hex_distance(cell, mover_xy)
        if seed_dist is None or dist < seed_dist:
            seed_xy, seed_dist = cell, dist
    if seed_xy is None:
        return None
    best, best_dist = None, None
    for o in pool:
        if _bracket(hex_distance(o.hex_xy, enemy_xy), weapon) < initial_bracket:
            continue
        dist = hex_distance(o.hex_xy, seed_xy)
        if best is None or dist < best_dist:
            best, best_dist = o, dist
    return best


# =============================================================================
# ===========================  THE CHOICE  ====================================
# =============================================================================
def _static_scores(cands, prepared_by_key, me, them):
    """Objective for the mover's states against the enemy where it stands.
    Returns [(score, prepared_state, MovementCandidate)]."""
    out = []
    for cand in cands:
        o = prepared_by_key[(cand.hex, cand.facing, cand.mode, cand.fc)]
        score = _objective(cand.dealt, cand.received, them.exposure[cand.side_on_defender],
                           me.exposure[cand.side_on_mover], me.psr_cost(cand.mode, cand.fc))
        out.append((score, o, cand))
    return out


def _modeled_reply(c, ev2, prepared2, them, me, other, mover_xy_of_c, terrain_map):
    """The second mover's reply if the first mover ends at prepared state c:
    (MovementCandidate or None, reply's prepared state or None). The reply is
    picked by the same rule the real second mover uses - the objective, then
    the closing fallback when nothing deals damage - with no randomness."""
    cands = ev2.evaluate(c.label, c.facing_compass, c.fc, c.mode, c.mp_spent, prepared2)
    best_score, best = None, None
    any_damage = False
    # `me` is the first mover, `them` the second: here the second mover is the one choosing.
    for cand in cands:
        if cand.dealt > 0:
            any_damage = True
        score = _objective(cand.dealt, cand.received, me.exposure[cand.side_on_defender],
                           them.exposure[cand.side_on_mover], them.psr_cost(cand.mode, cand.fc))
        key = round(score, 9)
        if best is None or key > best_score:
            best_score, best = key, cand
        elif key == best_score:
            # tie: nearer the first mover's pinned hex wins (first seen otherwise)
            if cand.distance < best.distance:
                best = cand
    if any_damage:
        return best
    # Nothing deals damage from here: the second mover would fall back to closing.
    by_key = {(cand.hex, cand.facing, cand.mode, cand.fc): cand for cand in cands}
    fb = closing_fallback(other, ev2.defender, prepared2, mover_xy_of_c, lambda o: 0.0, terrain_map,
                          exclude_xy=mover_xy_of_c)
    if fb is None:
        pool = [o for o in prepared2 if o.hex_xy != mover_xy_of_c]
        if not pool:
            return None
        fb = _nearest_to(pool, mover_xy_of_c)
    return by_key.get((fb.label, fb.facing_compass, fb.mode, fb.fc))


def choose(mover, other, terrain_map, battle_rng, moves_first, standup_mp=None, entry_edge=None):
    """Pick the mover's end-of-movement state.

    mover / other: BattleMech instances (see orchestrator._attach_mech_config).
    `other` hasn't moved yet this turn if `moves_first`, else it has (its real
    position). Returns (pick, note): pick is {hex, facing, mode, fc, mp_spent}
    (plus "charge": True for a charge, INTEGRATION__charge) or None (nothing
    reachable); note is a one-line log string."""
    pick, note, score, ctx = _choose_normal(mover, other, terrain_map, battle_rng, moves_first,
                                            standup_mp=standup_mp, entry_edge=entry_edge)
    if ctx is not None and config.CHARGES and entry_edge is None \
            and charge.can_charge(mover, other, target_has_moved=not moves_first):
        charged = _charge_pick(mover, other, terrain_map, standup_mp, score, *ctx)
        if charged is not None:
            return charged
    return pick, note


def _charge_pick(mover, other, terrain_map, standup_mp, normal_score, ev1, me, them, static):
    """INTEGRATION__charge's decision: gate each charge on beating the best
    ordinary attack (ranged + physical) in the same movement mode, then score
    the survivors like any spot and keep the best if it beats the normal pick."""
    best_by_mode: Dict[str, float] = {}
    for c in static:
        value = c.dealt * them.exposure[c.side_on_defender]
        best_by_mode[c.mode] = max(best_by_mode.get(c.mode, 0.0), value)
    best = None
    for state in charge.charge_states(mover, other, terrain_map, standup_mp=standup_mp):
        dealt, p_hit, dmg, tn = charge.expected_dealt(mover, other, state, terrain_map)
        if dealt <= best_by_mode.get(state["mode"], 0.0):
            continue                      # the gate: no better than an ordinary attack in this mode
        x, y = hex_geometry.parse_hex_label(state["hex"])
        prepared = ev1.prepare([(x, y, hex_geometry.compass_to_facing(state["facing"]), state["fc"],
                                 state["mode"], state["mp_spent"])])
        cands = ev1.evaluate(other.hex, other.facing, other.move_fc, other.move_mode, other.mp_spent, prepared)
        received = (cands[0].received * me.exposure[cands[0].side_on_mover]) if cands else 0.0
        received += charge.self_damage_worth(mover, other, p_hit)
        extras = me.psr_cost(state["mode"], state["fc"])
        score = _objective(dealt, received, 1.0, 1.0, extras)
        if best is None or score > best[0]:
            best = (score, state, dealt, received, extras, p_hit, dmg, tn)
    if best is None or (normal_score is not None and best[0] <= normal_score):
        return None
    score, state, dealt, received, extras, p_hit, dmg, tn = best
    return state, (f"CHARGE {other.side_name}: score {score:.3f} = dealt {dealt:.2f} (TN {tn}, P {p_hit:.2f}, "
                   f"{dmg} dmg) / (received {received:.2f} incl. self-damage + PSR {extras:.2f}) beats "
                   f"{'nothing' if normal_score is None else f'{normal_score:.3f}'}")


def _choose_normal(mover, other, terrain_map, battle_rng, moves_first, standup_mp=None, entry_edge=None):
    """Pick the mover's end-of-movement state (no charges).

    mover / other: BattleMech instances (see orchestrator._attach_mech_config).
    `other` hasn't moved yet this turn if `moves_first`, else it has (its real
    position). Returns (pick, note, score, ctx): score is the pick's objective
    (None for a fallback pick), ctx = (ev1, me, them, static) for the charge
    decision (None when there is no enemy on the board)."""
    me = _Side(mover, psr_applies=standup_mp is None)   # a stand-up already rolled its PSR (orchestrator)
    options = reduced_options(mover, terrain_map, exclude_hex=other.hex, standup_mp=standup_mp,
                              entry_edge=entry_edge)

    if other.hex is None:
        # The enemy hasn't entered the board: nothing to shoot or to model. Head for its home edge.
        enemy_label = other.home_edge[len(other.home_edge) // 2]
        enemy_xy = hex_geometry.parse_hex_label(enemy_label)
        prepared = ranged_combat.prepare_options(mover, options)
        if not prepared:
            return None, "no reachable spot", None, None
        fb = closing_fallback(mover, other, prepared, enemy_xy, lambda o: 0.0, terrain_map)
        pick = fb if fb is not None else _nearest_to(prepared, enemy_xy, battle_rng)
        return _pick_dict(pick), (f"no enemy on the board yet - heads for its home edge near {enemy_label}"
                                  f"{' (closing fallback)' if fb is not None else ''}"), None, None

    them = _Side(other, psr_applies=True)
    enemy_xy = hex_geometry.parse_hex_label(other.hex)

    # Static evaluation: the enemy standing where it is now. Real for the second
    # mover; the "projection" the first mover scores against with two-ply off,
    # and the damage probe for the closing fallback either way.
    ev1 = ranged_combat.MoveEvaluator(mover, other, terrain_map)
    prepared1 = ev1.prepare(options)
    if not prepared1:
        return None, "no reachable spot", None, None
    prepared_by_key = {(o.label, o.facing_compass, o.mode, o.fc): o for o in prepared1}
    static = ev1.evaluate(other.hex, other.facing, other.move_fc, other.move_mode, other.mp_spent, prepared1)
    static_dealt = {(c.hex, c.facing, c.mode, c.fc): c.dealt for c in static}
    dealt_for = lambda o: static_dealt.get((o.label, o.facing_compass, o.mode, o.fc), 0.0)  # noqa: E731

    two_ply = moves_first and config.MOVEMENT_TWO_PLY
    ctx = (ev1, me, them, static)

    if not two_ply:
        scored = _static_scores(static, prepared_by_key, me, them)
        if scored and any(c.dealt > 0 for _, _, c in scored):
            o, cand = _best_by_score(scored, enemy_xy, battle_rng)
            score = _objective(cand.dealt, cand.received, them.exposure[cand.side_on_defender],
                               me.exposure[cand.side_on_mover], me.psr_cost(cand.mode, cand.fc))
            return _pick_dict(o), _note(cand.dealt, cand.received, them.exposure[cand.side_on_defender],
                                        me.exposure[cand.side_on_mover], me.psr_cost(cand.mode, cand.fc),
                                        f"enemy held at {other.hex}; {len(scored)} spots with LOS"), score, ctx
        return (*_fallback_pick(mover, other, prepared1, enemy_xy, dealt_for, terrain_map, battle_rng,
                                "no spot deals damage"), None, ctx)

    # --- two-ply: score every spot by the second mover's modeled reply ---
    ev2 = ranged_combat.MoveEvaluator(other, mover, terrain_map)
    prepared2 = ev2.prepare(_opponent_options(other, terrain_map))
    scored, any_dealt = [], False
    for c in prepared1:
        reply = _modeled_reply(c, ev2, prepared2, them, me, other, c.hex_xy, terrain_map)
        if reply is None:
            dealt = received = 0.0
            dealt_mult = received_mult = 1.0
        else:
            # What the reply receives is what the first mover deals, and back.
            dealt, received = reply.received, reply.dealt
            dealt_mult = them.exposure[reply.side_on_mover]
            received_mult = me.exposure[reply.side_on_defender]
        if dealt > 0:
            any_dealt = True
        extras = me.psr_cost(c.mode, c.fc)
        scored.append((_objective(dealt, received, dealt_mult, received_mult, extras), c,
                       (dealt, received, dealt_mult, received_mult, extras, reply)))
    if any_dealt:
        o, (dealt, received, dm, rm, extras, reply) = _best_by_score(scored, enemy_xy, battle_rng)
        reply_txt = (f"; modeled reply {other.side_name} -> {reply.hex} {reply.facing} {reply.mode}"
                     if reply is not None else "; modeled reply: none with LOS")
        return (_pick_dict(o), _note(dealt, received, dm, rm, extras,
                                     f"two-ply, {len(prepared1)} spots x {len(prepared2)} replies{reply_txt}"),
                _objective(dealt, received, dm, rm, extras), ctx)
    return (*_fallback_pick(mover, other, prepared1, enemy_xy, dealt_for, terrain_map, battle_rng,
                            f"no spot deals damage even before the reply (two-ply, {len(prepared1)} spots)"), None, ctx)


def _fallback_pick(mover, other, prepared, enemy_xy, dealt_for, terrain_map, battle_rng, why):
    fb = closing_fallback(mover, other, prepared, enemy_xy, dealt_for, terrain_map)
    if fb is not None:
        return _pick_dict(fb), f"{why} - closing fallback"
    return _pick_dict(_nearest_to(prepared, enemy_xy, battle_rng)), \
        f"{why} - closing fallback found nothing; nearest reachable spot to the enemy"


def _note(dealt, received, dealt_mult, received_mult, extras, how):
    score = _objective(dealt, received, dealt_mult, received_mult, extras)
    return (f"score {score:.3f} = dealt {dealt:.2f} x{dealt_mult:.2f} / (received {received:.2f} x{received_mult:.2f}"
            f" + PSR {extras:.2f} + {config.MOVEMENT_RATIO_EPSILON}) [{how}]")
