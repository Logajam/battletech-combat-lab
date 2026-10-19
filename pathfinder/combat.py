"""
combat.py — "going second" expected-damage heatmap evaluation.

Layered on top of hex_geometry -> board_parser -> pathfinder -> los. This is
the combat.py module flagged as TO DO in PROJECT_MAP_movement.md, built per
movement_pathfinder_handoff (combat.py spec) with Daniel's confirmations on
2026-07-20. Wired into config.run() as of 2026-07-20 — config.py calls
validate_profiles() then evaluate_combat_hexes() each run. Layered on top of
hex_geometry -> board_parser -> pathfinder -> los, same dependency chain as
before.

=== SCOPE ===
The defender's HEX/FACING are still fixed for the duration of one
evaluate_combat_hexes() call — this module's job is still "search one
side's full envelope against the other side's one fixed state," the
inner-loop primitive combat_turn.py's two-ply search calls repeatedly
(see PROJECT_MAP_movement.md / DESIGN_NOTES_movement.md's two-ply
section). As of 2026-07-21, the defender is no longer assumed to be
*permanently* static: it no longer carries a hardcoded `tmm` config
value. Instead, the defender's own TMM (as a target) and AMM (for its
own return fire) are computed from an explicit `defender_state` — the
(forward_count, movement_mode) it used to reach its fixed hex this call
— the same fc_to_tmm()/AMM lookup already used for the attacker. This
lets combat_turn.py pin either side at any of its own real movement
states for one call, while combat.py itself keeps searching the other
side's full envelope exactly as before. A caller that never moves the
defender (today's original single-sided usage) gets that behavior for
free via the default defender_state — see evaluate_combat_hexes()'s
docstring. For every attacker hex reachable with LOS to the defender,
this computes:
  - Expected damage dealt (attacker -> defender)
  - Expected damage received (defender -> attacker return fire)
  - The single (facing, movement mode, forward-count) combination at that
    hex that maximizes the damage-dealt/damage-received ratio.
The two-ply orchestration itself (iterating candidate states on both
sides, the in-range/closing-turn evaluator switch, caching) lives in
combat_turn.py, not here — see PROJECT_MAP_movement.md TO DO /
PROPOSAL_two_ply_combat_turn.md.

=== SCORE FORMULA + ROLLED DAMAGE (2026-07-23) ===
As of 2026-07-23, the per-hex ratio used to pick candidates/replies is no
longer a bare damage-dealt/damage-received ratio — it's compute_score(),
an HP-aware four-term formula (FinishBonus/SelfPreservation/DealtSeverity/
ReceivedSeverity — see that function's docstring and
DESIGN_NOTES_movement.md#score_formula.2026-07-23). This requires both
profiles to carry max_hp/current_hp (validate_profiles() enforces this).
Separately, resolve_combat_roll() is a new sibling to
evaluate_combat_hexes() that resolves ONE fixed pair of already-chosen
states with real dice rolls (not expected value) — this is what actually
subtracts HP after a turn's moves are committed in
combat_turn.run_multi_turn(); it plays no role in candidate search/
scoring, which stays fully deterministic/expected-value-based.

=== CONFIRMED RULES (Daniel, 2026-07-19/2026-07-20 — do not re-derive) ===

To-hit target number:
    TN = Gunnery + Attacker Movement Modifier (AMM) + Target Movement
         Modifier (TMM) + Other (LOS/terrain modifier) + Range Modifier

  - AMM: Stood still +0, Walked +1, Ran +2, Jumped +3.
  - TMM: standard BT FC-based table (TMM_TABLE below), +1 if the mover
    jumped. Applied bidirectionally: attacker's shot at the defender
    uses a TMM computed from the defender's own (fc, mode) for this
    call (defender_state — "Stood" is fc=0, not jumped, i.e. TMM 0, if
    the defender never moved); the defender's return fire uses a TMM
    computed from the attacker's own FC at the evaluated state — same
    fc_to_tmm() lookup, both directions.
  - Other: pulled directly from los.has_los()'s modifier field (woods +
    partial-cover, per los.py rules 3/5) — LOS modifiers DO feed to-hit.
  - Range Modifier: Short +0 / Medium +2 / Long +4, per weapon's own
    range brackets. Beyond a weapon's Long range, it cannot fire (0
    damage contribution, no TN calc for that weapon).

Hit probability: standard cumulative 2d6 P(sum >= TN) distribution — pure
probability math, not a BT-specific number, so this table needed no
separate confirmation from Daniel.

Expected damage per weapon: damage_i * P(hit)_i, summed independently per
weapon (each weapon checked against its own range brackets).

Rear arc (Daniel, corrected 2026-07-20 — supersedes the earlier same-day
180-degree/3-facing confirmation): only the single facing directly
opposite a mech's own facing counts as rear (60 degrees, not 180) —
own_facing + 3 (mod 6), see REAR_ARC_OFFSETS below. If the other unit's
hex falls in that one rear facing, that mech's offensive fire *from that
state* is 0 — checked independently for the attacker (its own facing at
the evaluated state) and the defender (its fixed config facing).

Jump legality (Daniel, 2026-07-19, restated/confirmed 2026-07-20):
  - Landing hex must be within Jump MP hex-distance (los.hex_distance) of
    the start hex.
  - The jump path is the same straight-line hex path los.hex_line() uses.
  - An intervening hex blocks the jump if its level >=
    start_level + jump_mp + JUMP_BLOCK_MARGIN (Daniel's worked example:
    Jump MP 3 from level 2 -> a level 6 hex blocks, a level 5 hex does not
    -> threshold = start_level + jump_mp + 1).
  - On a hex-grid-edge tie between two path candidates, the MORE
    permissible (lower-level) candidate is used for the legality check —
    the opposite of los.py's "worse for the attacker" tie-break, since
    this is a legality gate, not a to-hit modifier.
  - Per Daniel: "For every valid hex it can get to, all 6 facing states
    are included automatically" — a mech may face any direction after
    landing a jump, so build_jump_states() does not run a turn-cost DP;
    it just enumerates the 6 facings for every legal landing hex.

Movement-mode classification (per Daniel's original framing in the
handoff spec): pathfinder.build_movement_table() naturally produces Walk
states as a subset of the states reachable within the Run MP budget, so
this module builds the table ONCE at running_mp and classifies each
(state, mp_spent) entry as Walk if mp_spent <= walking_mp, else Run.
NOTE (flagged for Daniel, not yet re-confirmed): this means an mp_spent=0
entry (never actually moved, e.g. only turned) is classified as "Walked"
(AMM +1) rather than "Stood still" (AMM +0) under this rule as literally
stated. Flagging here rather than silently deviating from the spec.

=== EXPLICITLY DEFERRED (see PROJECT_MAP_movement.md TO DO) ===
  - Full two-ply lookahead (attacker's first-mover choice vs. all of the
    defender's possible responses).
  - equipment.json-sourced weapon data — weapon lists are supplied
    directly in the attacker/defender profile dicts passed into
    evaluate_combat_hexes(), not read from equipment.json this pass.
  - Any GATOR modifier beyond Gunnery/AMM/TMM/LOS-terrain/Range.
"""

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from hex_geometry import (
    FACING_DELTAS,
    State,
    compass_to_facing,
    facing_to_compass,
    hex_label,
    parse_hex_label,
    state_from_label,
)
from pathfinder import build_movement_table
from los import Hex, LOSResult, has_los, hex_distance, hex_line

# =============================================================================
# ============================  CONFIG  ======================================
# =============================================================================

# --- Attacker Movement Modifier (AMM): TN penalty for how the shooter itself
# moved to reach the firing hex. Daniel-confirmed 2026-07-20.
AMM_STILL = 0
AMM_WALK = 1
AMM_RUN = 2
AMM_JUMP = 3

# --- Movement-mode -> AMM lookup. "Stood" is not a real pathfinder/jump
# mode (nothing in pathfinder.py or build_jump_states() produces it) — it
# exists only as evaluate_combat_hexes()'s default defender_state mode,
# for a caller that wants the original "defender never moved" behavior
# (fc=0, AMM_STILL, TMM 0). Added 2026-07-21 alongside the defender_state
# change (see module docstring SCOPE) so that default path and the
# Walk/Run/Jump paths share one lookup instead of a separate hardcoded
# AMM_STILL branch.
MODE_TO_AMM: Dict[str, int] = {
    "Stand Still": AMM_STILL,
    "Walk": AMM_WALK,
    "Run": AMM_RUN,
    "Jump": AMM_JUMP,
}

# --- Target Movement Modifier (TMM) table: (max_fc_inclusive, tmm), standard
# BT table. Daniel-confirmed 2026-07-20. The table's top bracket (18-24) is
# applied as an open-ended floor above 17 rather than re-deriving a higher
# bracket for FC > 24 — this project's MP budgets can exceed 24, and the
# standard table doesn't define anything past this bracket.
TMM_TABLE = [
    (2, 0),
    (4, 1),
    (6, 2),
    (9, 3),
    (17, 4),
]
TMM_TOP_BRACKET_VALUE = 5  # FC >= 18
TMM_JUMP_BONUS = 1

# --- Range modifiers: Short/Medium/Long TN penalty, per weapon's own range
# brackets. Beyond Long, the weapon cannot fire. Daniel-confirmed 2026-07-20.
RANGE_MOD_SHORT = 0
RANGE_MOD_MEDIUM = 2
RANGE_MOD_LONG = 4

# --- Rear arc: 60 degrees directly opposite the mech's facing (Daniel,
# corrected 2026-07-20 — supersedes the earlier same-day 180-degree/
# 3-facing confirmation). Only the single facing directly opposite one's
# own counts as rear: own_facing + 3 (mod 6).
REAR_ARC_OFFSETS = (3,)

# --- Jump elevation-blocking margin (Daniel, 2026-07-19/2026-07-20): an
# intervening hex on the jump path blocks the jump if its level >=
# start_level + jump_mp + JUMP_BLOCK_MARGIN.
JUMP_BLOCK_MARGIN = 1

# --- Standard 2d6 cumulative hit-probability table: P(2d6 sum >= TN). Pure
# probability math (not a BT-specific number) — no Daniel confirmation needed.
_2D6_AT_LEAST: Dict[int, float] = {
    2: 36 / 36, 3: 35 / 36, 4: 33 / 36, 5: 30 / 36, 6: 26 / 36,
    7: 21 / 36, 8: 15 / 36, 9: 10 / 36, 10: 6 / 36, 11: 3 / 36, 12: 1 / 36,
}

# --- Ratio tie-break epsilon: avoids a division-by-zero degenerate case when
# comparing damage-dealt/damage-received across candidate states at a hex.
RATIO_EPSILON = 0.001

# --- Score formula severity cap (Daniel-confirmed 2026-07-23): caps how much
# DealtSeverity/ReceivedSeverity (fraction of current HP one hit represents)
# can contribute -- not a BT rule, a tunable design knob. See compute_score()
# and DESIGN_NOTES_movement.md#score_formula.2026-07-23 for the derivation.
SEVERITY_CAP = 2.0

# =============================================================================
# ========================  END CONFIG  ======================================
# =============================================================================


@dataclass
class HexResult:
    """The best-ratio (dealt/received) state found at one attacker hex,
    across every (facing, movement mode, forward-count) combination that
    reaches that hex with LOS to the defender."""
    hex: str
    facing: str
    mode: str  # "Walk" / "Run" / "Jump"
    fc: int
    mp_spent: int
    damage_dealt: float
    damage_received: float
    ratio: float


def hit_probability(tn: int) -> float:
    """P(2d6 roll >= tn). tn<=2 always hits; tn>12 is an automatic miss."""
    if tn <= 2:
        return 1.0
    if tn > 12:
        return 0.0
    return _2D6_AT_LEAST[tn]


def fc_to_tmm(fc: int, jumped: bool) -> int:
    """Forward-count -> Target Movement Modifier, per TMM_TABLE, +1 if jumped."""
    if fc < 0:
        raise ValueError(f"forward_count must be >= 0, got {fc}")
    tmm = TMM_TOP_BRACKET_VALUE
    for max_fc, value in TMM_TABLE:
        if fc <= max_fc:
            tmm = value
            break
    if jumped:
        tmm += TMM_JUMP_BONUS
    return tmm


def range_bracket_modifier(distance: int, weapon: Dict[str, object]) -> Optional[int]:
    """Short/Medium/Long TN modifier for firing this weapon at this distance,
    or None if the distance is beyond the weapon's Long range (can't fire)."""
    if distance <= weapon["short"]:
        return RANGE_MOD_SHORT
    if distance <= weapon["medium"]:
        return RANGE_MOD_MEDIUM
    if distance <= weapon["long"]:
        return RANGE_MOD_LONG
    return None


def classify_movement_mode(mp_spent: int, walking_mp: int) -> str:
    """'Walk' if mp_spent fits within the Walking MP budget, else 'Run' — see
    module docstring's "Movement-mode classification" note (including the
    flagged mp_spent=0 edge case)."""
    if mp_spent == 0:
        return "Stand Still"
    return "Walk" if mp_spent <= walking_mp else "Run"


# =============================================================================
# Rear-arc geometry
# =============================================================================

def _facing_unit_cube_vectors() -> Dict[int, Tuple[float, float, float]]:
    """Cube-coordinate unit direction vector for each of the 6 facings,
    derived from hex_geometry.FACING_DELTAS via the same doubled->cube
    conversion los.py uses. Pure geometry, not a BT rule — stays in sync
    with FACING_DELTAS automatically if that compass calibration ever
    changes."""
    vectors = {}
    for facing, (dx, dy) in FACING_DELTAS.items():
        q = float(dx)
        r = (dy - dx) / 2.0
        s = -q - r
        vectors[facing] = (q, r, s)
    return vectors


_FACING_CUBE_VECTORS = _facing_unit_cube_vectors()


def _direction_facing(from_hex: Hex, to_hex: Hex) -> int:
    """Nearest of the 6 facings pointing from from_hex toward to_hex (by cube
    dot-product against each facing's unit direction vector — standard
    technique for "which of 6 hex directions is B relative to A", works for
    any distance/off-axis position). Raises ValueError if the hexes are
    identical (direction undefined)."""
    if from_hex == to_hex:
        raise ValueError(f"Cannot determine a direction from hex {from_hex} to itself.")
    fx, fy = from_hex
    tx, ty = to_hex
    dx, dy = tx - fx, ty - fy
    q = float(dx)
    r = (dy - dx) / 2.0
    s = -q - r

    best_facing, best_dot = None, float("-inf")
    for facing, (vq, vr, vs) in _FACING_CUBE_VECTORS.items():
        dot = q * vq + r * vr + s * vs
        if dot > best_dot:
            best_dot, best_facing = dot, facing
    return best_facing


def in_rear_arc(mech_hex: Hex, mech_facing: int, target_hex: Hex) -> bool:
    """True if target_hex falls within mech_hex's rear arc (the single
    facing directly opposite mech_facing), per Daniel's confirmed rule
    (module docstring)."""
    direction = _direction_facing(mech_hex, target_hex)
    rear_facings = {(mech_facing + offset) % 6 for offset in REAR_ARC_OFFSETS}
    return direction in rear_facings


# =============================================================================
# Jump-state enumeration
# =============================================================================

def build_jump_states(start_x: int, start_y: int, jump_mp: int, terrain_map: Dict[str, object]) -> Dict[State, int]:
    """
    Every (x, y, facing) state reachable by jumping, given jump_mp. Per
    Daniel: every legal landing hex automatically gets all 6 facing states
    (no turn-cost DP — a mech can face any direction after landing a jump).

    Returns {state: forward_count}, forward_count being the straight-line
    hex distance jumped (used for the TMM lookup on defender return fire).

    Legality (see module docstring): on-board, not impassable, within
    jump_mp hex-distance, and the straight-line path isn't blocked by an
    intervening hex at/above start_level + jump_mp + JUMP_BLOCK_MARGIN. An
    intervening step that runs off-board (can happen only on a concave/edge
    path) is treated as blocking that candidate, matching this project's
    existing stance (los.py) of not supporting off-board line segments.
    """
    hexes = terrain_map["hexes"]

    def hex_info(h: Hex):
        try:
            label = hex_label(*h)
        except ValueError:
            return None
        return hexes.get(label)

    start_hex: Hex = (start_x, start_y)
    start_info = hex_info(start_hex)
    if start_info is None:
        raise ValueError(f"Jump start hex {hex_label(start_x, start_y)!r} is not on the loaded board.")
    if start_info["impassable"]:
        raise ValueError(f"Jump start hex {hex_label(start_x, start_y)!r} is marked impassable.")

    block_threshold = start_info["level"] + jump_mp + JUMP_BLOCK_MARGIN

    states: Dict[State, int] = {}

    for label, info in hexes.items():
        if info["impassable"]:
            continue
        x, y = parse_hex_label(label)
        candidate_hex: Hex = (x, y)
        if candidate_hex == start_hex:
            continue

        dist = hex_distance(start_hex, candidate_hex)
        if dist > jump_mp:
            continue

        path = hex_line(start_hex, candidate_hex)
        blocked = False
        for step in path[1:-1]:  # intervening hexes only, endpoints excluded
            step_infos = [hex_info(h) for h in step]
            if any(si is None for si in step_infos):
                blocked = True  # path runs off-board — not a legal jump here
                break
            # More-permissible (lower-level) candidate wins the tie —
            # opposite of los.py's "worse for the attacker" convention,
            # since this is a legality gate, not a to-hit modifier.
            chosen_level = min(si["level"] for si in step_infos)
            if chosen_level >= block_threshold:
                blocked = True
                break
        if blocked:
            continue

        for facing in range(6):
            states[(x, y, facing)] = dist

    return states


# =============================================================================
# Expected-damage evaluation
# =============================================================================

def _weapon_expected_damage(
    gunnery: int, amm: int, target_tmm: int, los_modifier: int, distance: int, weapons: List[Dict[str, object]]
) -> float:
    total = 0.0
    for w in weapons:
        range_mod = range_bracket_modifier(distance, w)
        if range_mod is None:
            continue  # beyond this weapon's Long range
        tn = gunnery + amm + target_tmm + los_modifier + range_mod
        total += w["damage"] * hit_probability(tn)
    return total


def compute_score(
    dealt: float, received: float,
    target_max_hp: int, target_cur_hp: int,
    self_max_hp: int, self_cur_hp: int,
    cap: float = SEVERITY_CAP,
) -> float:
    """
    Daniel's 2026-07-23 four-term score formula, replacing the old bare
    damage-dealt/damage-received ratio. See DESIGN_NOTES_movement.md
    #score_formula.2026-07-23 for the derivation history and rejected
    intermediate drafts.

        Score = DamageDealt * FinishBonus(target) * DealtSeverity
                --------------------------------------------------
                DamageReceived * SelfPreservation(self) * ReceivedSeverity

    FinishBonus(target)    = target_max_hp / target_cur_hp   -- reward finishing a wounded target
    SelfPreservation(self) = self_max_hp / self_cur_hp       -- caution when self is wounded
    DealtSeverity           = min(dealt / target_cur_hp, cap) -- how big a bite this hit takes, capped
    ReceivedSeverity        = min(received / self_cur_hp, cap)-- mirror, for damage taken

    Epsilon placement matches the old ratio's convention exactly (only the
    received side gets a small additive floor, plus one more on the whole
    denominator) -- validated against /home/claude/score_test.py's 8
    scenarios before this was wired in; don't rebalance without re-running
    those.

    target_cur_hp/self_cur_hp must both be > 0 -- a destroyed mech should
    never reach this function. combat_turn.run_multi_turn() stops the
    entire run the turn either side hits 0 HP (see its docstring), so this
    raises loudly rather than silently dividing by zero if that invariant
    is ever violated by a future caller.
    """
    if target_cur_hp <= 0:
        raise ValueError(f"compute_score got target_cur_hp={target_cur_hp} -- a destroyed target should never reach scoring.")
    if self_cur_hp <= 0:
        raise ValueError(f"compute_score got self_cur_hp={self_cur_hp} -- a destroyed self should never reach scoring.")

    finish_bonus = target_max_hp / target_cur_hp
    self_preservation = self_max_hp / self_cur_hp
    dealt_severity = min(dealt / target_cur_hp, cap)
    received_severity = min(received / self_cur_hp, cap)

    numerator = dealt * finish_bonus * dealt_severity
    denominator = (received + .01) * self_preservation * received_severity + .0001
    return numerator / denominator


def _evaluate_state(
    x: int, y: int, facing: int, fc: int, mode: str, mp_spent: int,
    attacker: Dict[str, object], defender: Dict[str, object],
    def_hex: Hex, def_facing: int, def_fc: int, def_mode: str,
    los_cache: Dict[Hex, Optional[Tuple[LOSResult, LOSResult]]],
    terrain_map: Dict[str, object],
) -> Optional[HexResult]:
    atk_hex: Hex = (x, y)
    if atk_hex == def_hex:
        return None  # occupying the defender's hex is undefined here

    if atk_hex not in los_cache:
        hexes = terrain_map["hexes"]
        try:
            atk_label = hex_label(*atk_hex)
        except ValueError:
            los_cache[atk_hex] = None
            return None
        info = hexes.get(atk_label)
        if info is None or info["impassable"]:
            los_cache[atk_hex] = None
        else:
            try:
                atk_to_def = has_los(atk_hex, def_hex, terrain_map)
                def_to_atk = has_los(def_hex, atk_hex, terrain_map)
            except ValueError:
                los_cache[atk_hex] = None
            else:
                los_cache[atk_hex] = (atk_to_def, def_to_atk) if atk_to_def.los else None

    cached = los_cache[atk_hex]
    if cached is None:
        return None
    atk_to_def, def_to_atk = cached

    distance = hex_distance(atk_hex, def_hex)
    amm = MODE_TO_AMM[mode]

    # Defender's TMM as a target for the attacker's shot: computed from
    # def_fc/def_mode (this call's fixed defender state) via the same
    # fc_to_tmm() lookup used for the attacker's own return-fire TMM
    # below — no more static config["tmm"]. def_mode="Stood" (the
    # evaluate_combat_hexes() default) gives fc_to_tmm(0, jumped=False)
    # == TMM 0, matching the old "static defender" behavior exactly.
    # See module docstring SCOPE (2026-07-21 change) and
    # PROPOSAL_two_ply_combat_turn.md Section 6.
    defender_tmm = fc_to_tmm(def_fc, jumped=(def_mode == "Jump"))

    if in_rear_arc(atk_hex, facing, def_hex):
        dealt = 0.0
    else:
        dealt = _weapon_expected_damage(
            attacker["gunnery"], amm, defender_tmm, atk_to_def.modifier, distance, attacker["weapons"]
        )

    if in_rear_arc(def_hex, def_facing, atk_hex):
        received = 0.0
    else:
        # Attacker's TMM as a target for the defender's return fire —
        # unchanged from before this pass.
        attacker_tmm = fc_to_tmm(fc, jumped=(mode == "Jump"))
        # Defender's own AMM for its return fire: was hardcoded
        # AMM_STILL (defender never moved). Now computed from def_mode
        # the same way the attacker's amm is above — AMM_STILL falls
        # out automatically when def_mode="Stood".
        def_amm = MODE_TO_AMM[def_mode]
        received = _weapon_expected_damage(
            defender["gunnery"], def_amm, attacker_tmm, def_to_atk.modifier, distance, defender["weapons"]
        )

    # 2026-07-23: HP-based four-term score, replaces the old bare ratio.
    # attacker/defender dicts already carry max_hp/current_hp -- required
    # by validate_profiles() as of this change.
    ratio = compute_score(
        dealt, received,
        target_max_hp=defender["max_hp"], target_cur_hp=defender["current_hp"],
        self_max_hp=attacker["max_hp"], self_cur_hp=attacker["current_hp"],
    )

    return HexResult(
        hex=hex_label(x, y),
        facing=facing_to_compass(facing),
        mode=mode,
        fc=fc,
        mp_spent=mp_spent,
        damage_dealt=dealt,
        damage_received=received,
        ratio=ratio,
    )


def _roll_weapon_damage(
    gunnery: int, amm: int, target_tmm: int, los_modifier: int, distance: int,
    weapons: List[Dict[str, object]], rng: random.Random,
) -> float:
    """Same TN math as _weapon_expected_damage(), but resolves each weapon
    with one actual RNG roll instead of summing probability*damage. Used
    only for the real HP-subtracting shot at the end of a committed turn
    (combat_turn.run_multi_turn()) -- NOT for candidate search/scoring,
    which stays on the deterministic expected-value path above."""
    total = 0.0
    for w in weapons:
        range_mod = range_bracket_modifier(distance, w)
        if range_mod is None:
            continue
        tn = gunnery + amm + target_tmm + los_modifier + range_mod
        if rng.random() < hit_probability(tn):
            total += w["damage"]
    return total


def resolve_combat_roll(
    attacker: Dict[str, object], attacker_hex_label: str, attacker_facing_compass: str,
    attacker_mode: str, attacker_fc: int,
    defender: Dict[str, object], defender_hex_label: str, defender_facing_compass: str,
    defender_mode: str, defender_fc: int,
    terrain_map: Dict[str, object],
    rng: Optional[random.Random] = None,
) -> Tuple[float, float]:
    """
    2026-07-23: the actual-damage counterpart to evaluate_combat_hexes().
    Resolves ONE FIXED PAIR of already-chosen final states (no envelope
    search) with real dice rolls in both directions -- this is what
    combat_turn.run_multi_turn() calls once per turn, after both sides'
    moves are committed, to determine HP loss. Mirrors _evaluate_state()'s
    geometry/to-hit math (LOS both ways, rear arc, fc_to_tmm/MODE_TO_AMM
    for both sides) exactly, so a rolled result and an expected-value
    result for the same two states are computed from identical TN inputs
    -- only hit resolution differs (roll vs. probability-weighted sum).

    Returns (attacker_deals, defender_deals) -- actual damage each side
    inflicts on the other this shot, 0.0 if no LOS / rear-arc-blocked /
    same hex. rng defaults to the global `random` module if not given.
    SEEDING (2026-08-04, Claude - INTEGRATION project, Section 5 RNG
    decision): pass an INTEGRATION__rng.BattleRNG instance here for
    reproducible batches -- it exposes .random(), satisfying this
    function's rng.random() call with no changes needed in this file.
    """
    if rng is None:
        rng = random

    a_hex = parse_hex_label(attacker_hex_label)
    d_hex = parse_hex_label(defender_hex_label)
    if a_hex == d_hex:
        return 0.0, 0.0

    try:
        atk_to_def = has_los(a_hex, d_hex, terrain_map)
        def_to_atk = has_los(d_hex, a_hex, terrain_map)
    except ValueError:
        return 0.0, 0.0
    if not atk_to_def.los:
        return 0.0, 0.0

    distance = hex_distance(a_hex, d_hex)
    a_facing = compass_to_facing(attacker_facing_compass)
    d_facing = compass_to_facing(defender_facing_compass)
    a_amm = MODE_TO_AMM[attacker_mode]
    d_amm = MODE_TO_AMM[defender_mode]
    d_tmm = fc_to_tmm(defender_fc, jumped=(defender_mode == "Jump"))
    a_tmm = fc_to_tmm(attacker_fc, jumped=(attacker_mode == "Jump"))

    if in_rear_arc(a_hex, a_facing, d_hex):
        attacker_deals = 0.0
    else:
        attacker_deals = _roll_weapon_damage(
            attacker["gunnery"], a_amm, d_tmm, atk_to_def.modifier, distance, attacker["weapons"], rng
        )

    if in_rear_arc(d_hex, d_facing, a_hex):
        defender_deals = 0.0
    else:
        defender_deals = _roll_weapon_damage(
            defender["gunnery"], d_amm, a_tmm, def_to_atk.modifier, distance, defender["weapons"], rng
        )

    return attacker_deals, defender_deals


def validate_profiles(
    attacker: Dict[str, object], defender: Dict[str, object], terrain_map: Dict[str, object]
) -> None:
    """
    Validates ATTACKER/DEFENDER profile dicts against the loaded board
    before evaluate_combat_hexes() runs, so a bad CONFIG value fails
    loudly with a clear message pointing at the exact field, instead of
    a raw KeyError/ValueError surfacing deep inside _evaluate_state().

    Checks: both hexes are on-board and not impassable; attacker and
    defender aren't on the same hex (an occupied hex can't be entered by
    another mech); facings are valid compass strings; gunnery/walking_mp/
    running_mp/jumping_mp are non-negative ints on BOTH profiles; every
    weapon dict has damage/short/medium/long, each a non-negative number.

    2026-07-21 change (see module docstring SCOPE /
    PROPOSAL_two_ply_combat_turn.md Section 6): `tmm` is no longer a
    valid/checked field on either profile -- the defender's TMM is now
    computed per-call from a defender_state passed into
    evaluate_combat_hexes(), not read from a static config value. Both
    profiles now require the same MP fields, since either side may be
    the one whose full envelope gets searched, and either side may be
    the one pinned fixed for a given call.

    Raises ValueError naming the exact missing/bad field. Returns
    nothing on success.
    """
    hexes = terrain_map["hexes"]

    def _check_hex(label, who):
        if not isinstance(label, str):
            raise ValueError(f"{who} hex must be a string CCRR label, got {label!r}")
        info = hexes.get(label)
        if info is None:
            raise ValueError(f"{who} hex {label!r} is not on the loaded board.")
        if info["impassable"]:
            raise ValueError(f"{who} hex {label!r} is marked impassable.")

    _check_hex(attacker.get("hex"), "Attacker")
    _check_hex(defender.get("hex"), "Defender")

    if attacker["hex"] == defender["hex"]:
        raise ValueError(
            f"Attacker and defender can't both start on hex {attacker['hex']!r} — "
            f"a hex occupied by one mech can't be entered by another."
        )

    for who, profile in (("Attacker", attacker), ("Defender", defender)):
        try:
            compass_to_facing(profile.get("facing"))
        except ValueError as e:
            raise ValueError(f"{who} facing invalid: {e}")

    def _check_nonneg_int(value, field, who):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{who} {field!r} must be a non-negative int, got {value!r}")

    # Symmetric as of 2026-07-21: both profiles need the same MP fields,
    # since either side can be the one searched or the one pinned fixed
    # for a given evaluate_combat_hexes() call. 'tmm' is no longer
    # checked on either profile -- see docstring above.
    for who, profile in (("Attacker", attacker), ("Defender", defender)):
        _check_nonneg_int(profile.get("gunnery"), "gunnery", who)
        _check_nonneg_int(profile.get("walking_mp"), "walking_mp", who)
        _check_nonneg_int(profile.get("running_mp"), "running_mp", who)
        _check_nonneg_int(profile.get("jumping_mp"), "jumping_mp", who)
        # --- 2026-07-23: HP fields, required for compute_score() ---
        _check_nonneg_int(profile.get("max_hp"), "max_hp", who)
        _check_nonneg_int(profile.get("current_hp"), "current_hp", who)
        max_hp, cur_hp = profile.get("max_hp"), profile.get("current_hp")
        if max_hp < 1:
            raise ValueError(f"{who} 'max_hp' must be >= 1, got {max_hp!r}")
        if not (1 <= cur_hp <= max_hp):
            raise ValueError(f"{who} 'current_hp' must be between 1 and max_hp ({max_hp}), got {cur_hp!r}")

    for who, profile in (("Attacker", attacker), ("Defender", defender)):
        weapons = profile.get("weapons")
        if not isinstance(weapons, list) or not weapons:
            raise ValueError(f"{who} 'weapons' must be a non-empty list, got {weapons!r}")
        for i, w in enumerate(weapons):
            for field in ("name", "damage", "short", "medium", "long"):
                if field not in w:
                    raise ValueError(f"{who} weapons[{i}] missing required field {field!r}: {w!r}")
            for field in ("damage", "short", "medium", "long"):
                val = w[field]
                if not isinstance(val, (int, float)) or isinstance(val, bool) or val < 0:
                    raise ValueError(
                        f"{who} weapons[{i}][{field!r}] must be a non-negative number, got {val!r}"
                    )


def evaluate_combat_hexes(
    attacker: Dict[str, object], defender: Dict[str, object], terrain_map: Dict[str, object],
    defender_state: Optional[Dict[str, object]] = None,
) -> Dict[str, HexResult]:
    """
    Expected-damage evaluation: searches attacker's full envelope
    (Walk/Run/Jump) against defender's one fixed hex/facing for this
    call. Returns {hex_label: HexResult} — one entry per attacker hex
    that is reachable AND has LOS to the defender, each holding the
    single (facing, mode, fc) combination at that hex with the best
    damage-dealt/damage-received ratio.

    attacker: {"hex": "CCRR", "facing": compass str, "gunnery": int,
               "walking_mp": int, "running_mp": int, "jumping_mp": int,
               "weapons": [{"name", "damage", "short", "medium", "long"}, ...]}
    defender: {"hex": "CCRR", "facing": compass str, "gunnery": int,
               "walking_mp": int, "running_mp": int, "jumping_mp": int,
               "weapons": [...]}  (MP fields required by validate_profiles()
               for contract symmetry even though this call doesn't search
               the defender's envelope -- see module docstring SCOPE)
    terrain_map: a board_parser.parse_board_file() result.
    defender_state: optional {"fc": int, "mode": str} describing how the
        defender reached its fixed hex THIS CALL -- feeds the defender's
        own TMM (as attacker's target) and AMM (for its own return fire)
        via the same fc_to_tmm()/MODE_TO_AMM lookups used for the
        attacker. mode must be one of "Stood"/"Walk"/"Run"/"Jump".
        Default (None) is {"fc": 0, "mode": "Stood"} -- TMM 0, AMM_STILL
        -- reproducing this function's original "defender never moves"
        behavior exactly. combat_turn.py's two-ply search is expected to
        pass the defender's actual (fc, mode) for whichever of its own
        movement-table/jump-state entries landed it at that fixed hex.
    """
    if defender_state is None:
        defender_state = {"fc": 0, "mode": "Stand Still"}
    def_fc = defender_state["fc"]
    def_mode = defender_state["mode"]
    if def_mode not in MODE_TO_AMM:
        raise ValueError(
            f"defender_state['mode'] must be one of {sorted(MODE_TO_AMM)}, got {def_mode!r}"
        )

    def_x, def_y = parse_hex_label(defender["hex"])
    def_hex: Hex = (def_x, def_y)
    def_facing = compass_to_facing(defender["facing"])

    start_x, start_y, start_facing = state_from_label(attacker["hex"], attacker["facing"])
    walking_mp = attacker["walking_mp"]
    running_mp = attacker["running_mp"]
    jumping_mp = attacker["jumping_mp"]

    # Walk/Run: one DP build at the Run MP budget — Walk states fall out as
    # the mp_spent<=walking_mp subset (Daniel-confirmed, see module docstring).
    wr_table = build_movement_table(start_x, start_y, start_facing, running_mp, terrain_map=terrain_map)
    jump_states = build_jump_states(start_x, start_y, jumping_mp, terrain_map)

    los_cache: Dict[Hex, Optional[Tuple[LOSResult, LOSResult]]] = {}
    best_by_hex: Dict[str, HexResult] = {}

    def consider(result: Optional[HexResult]) -> None:
        if result is None:
            return
        current = best_by_hex.get(result.hex)
        if current is None or result.ratio > current.ratio:
            best_by_hex[result.hex] = result

    for (x, y, facing), col in wr_table.items():
        for mp_spent, fc in col.items():
            mode = classify_movement_mode(mp_spent, walking_mp)
            consider(_evaluate_state(
                x, y, facing, fc, mode, mp_spent, attacker, defender,
                def_hex, def_facing, def_fc, def_mode, los_cache, terrain_map
            ))

    for (x, y, facing), fc in jump_states.items():
        consider(_evaluate_state(
            x, y, facing, fc, "Jump", jumping_mp, attacker, defender,
            def_hex, def_facing, def_fc, def_mode, los_cache, terrain_map
        ))

    return best_by_hex
