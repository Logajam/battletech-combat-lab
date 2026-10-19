"""
los.py — line-of-sight between two hexes: the straight-line hex path
between their centers, and whether/how that path blocks or degrades LOS.

Standalone geometry+rules module, not wired into config.run() (see
CALL_GRAPH_movement.md). Two consumers so far:
  - combat.py (planned): has_los() feeds the GATOR to-hit calc (modifier,
    distance) and filters out zero-damage hexes (los=False).
  - los_viz.py: trace_los_path() exposes the full per-step evaluation
    (not just the final result) so the firing line can be drawn hex by
    hex, including which tie-break candidate was chosen/discarded and
    exactly which hex caused a block.

Convention: all functions here take plain (x, y) doubled-coordinate hex
positions (see hex_geometry.py), NOT full (x, y, facing) States — LOS has
no facing dependency. Argument order is always (attacker_hex, target_hex);
this matters because Rule 5 (partial cover) is defined relative to "the
unit being attacked," i.e. the second argument.

=== Rules, confirmed by Daniel (2026-07-19), KISS-mode, static target ===

Applied to every intervening hex on the LOS path (endpoints excluded):

  1. Hard block: an intervening hex's level >= (higher endpoint's level + 2).
  2. Hard block: the hex adjacent-on-path to whichever endpoint is LOWER
     has level >= (lower endpoint's level + 2). (If both endpoints are
     the same level, both sides' adjacent hexes are checked, since
     neither is uniquely "the lower" one.)
  3. Soft block: sum the to-hit modifier of every intervening woods hex
     (light=+1, heavy=+2). If the running sum exceeds 2 at any point,
     LOS is blocked from that hex onward (evaluation stops immediately —
     this is a hard stop once the threshold is crossed, not a retroactive
     block of the whole path).
  4. A woods hex counts as "intervening" (i.e. contributes to rule 3) if
     its level == the higher endpoint's level, OR its level >= the lower
     endpoint's level AND it is the hex adjacent-on-path to the lower
     endpoint (same "adjacent" hex identified in rule 2).
  5. Partial cover (does not block, adds modifier only): the hex
     adjacent-on-path to the target (second argument) with
     level == target's level + 1 adds +1.
  6. Tie-break when the line runs exactly along a hex-grid edge (two
     candidate hexes for one step of the path): evaluate both
     candidates against rules 1-5 and keep whichever is worse for the
     attacker — a block wins over no block; failing that, the higher
     woods contribution wins. (Per Daniel: this stands in for "defender
     picks whichever option most favors them" until a proper evaluation
     function exists to drive that choice for real.)

KISS-mode note (Daniel, 2026-07-19): woods canopy height and mech height
are both treated as 2 levels and cancel out, so rules 1/2/4 use the
hex's raw `level` field as-is — `foliage_elev` is NOT factored in here,
matching board_parser.py's existing "cosmetic, no rules weight" framing
for that feature. This is a deliberate simplification versus MegaMek's
full multi-height LOS model, not an oversight.

Off-board line assumption (Daniel, 2026-07-19): has_los()/trace_los_path()
raise ValueError if any hex on the line — endpoint or intervening — is
off the loaded board. This is deliberately NOT caught/handled gracefully:
Daniel confirmed that would only matter for concave board shapes, which
this project doesn't need to support.

NOT implemented (out of scope this pass, per Daniel): minimum range,
heat, non-static-target TMM-on-defender interactions, any GATOR modifier
other than the woods/partial-cover terrain modifiers above. Elevation/
woods LOS rules above are Daniel's own simplified ruleset for this
project, not researched from a rulebook — do not "correct" them against
MegaMek/official BT LOS rules without asking first.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from hex_geometry import hex_label

Hex = Tuple[int, int]  # (x, y) doubled coordinates, no facing

_EPS = 1e-6


@dataclass
class LOSResult:
    los: bool       # True if LOS exists, False if blocked
    modifier: int   # cumulative to-hit modifier accumulated up to the
                     # point of evaluation (still populated even when
                     # los=False — left as-is per Daniel's instruction,
                     # not zeroed out on block)
    distance: int    # hex count from attacker_hex (0) to the point of
                     # evaluation (the full a->b distance if los=True,
                     # or the step index that blocked if los=False)


@dataclass
class LOSStep:
    """One step of the evaluated firing line — the hex used at this
    step, plus enough detail to render or debug it. Built by
    trace_los_path(); has_los() only needs the final LOSResult, but
    los_viz.py needs this full per-hex trace."""
    index: int                          # 0 = attacker hex, N = target hex
    hex: Hex                            # the hex used at this step (chosen candidate on a tie)
    other_candidate: Optional[Hex] = None  # the discarded tie-break candidate, if any (rule 6)
    level: int = 0
    is_endpoint: bool = False
    blocked: bool = False               # True only on the exact step that blocked LOS
    woods_contrib: int = 0              # this step's own woods modifier contribution
    partial_cover: int = 0              # rule 5, only possibly nonzero on the step adjacent to target
    cumulative_modifier: int = 0        # running modifier total through this step
    after_block: bool = False           # True for steps beyond the blocking step (not evaluated)


@dataclass
class LOSTrace:
    steps: List[LOSStep]
    result: LOSResult


# =============================================================================
# Cube-coordinate line geometry
# =============================================================================
# This project's doubled (x, y) coordinates convert to cube coordinates via
# q = x, r = (y - x) / 2, s = -q - r. Verified against every entry in
# hex_geometry.FACING_DELTAS: all 6 map to valid unit cube-neighbor vectors
# (permutations of (+1,-1,0)), so this conversion is correct for this
# project's grid — pure geometry, not a BT rule, no confirmation needed.


def _to_cube(h: Hex) -> Tuple[float, float, float]:
    x, y = h
    q = float(x)
    r = (y - x) / 2.0
    s = -q - r
    return q, r, s


def _from_cube(q: float, r: float, s: float) -> Hex:
    x = round(q)
    y = round(2 * r + x)
    return (x, y)


def hex_distance(a: Hex, b: Hex) -> int:
    """Straight-line hex distance between two doubled-coordinate hexes."""
    aq, ar, as_ = _to_cube(a)
    bq, br, bs = _to_cube(b)
    return round(max(abs(aq - bq), abs(ar - br), abs(as_ - bs)))


def _cube_round_candidates(q: float, r: float, s: float) -> List[Tuple[int, int, int]]:
    """
    Round a fractional cube coordinate to its nearest hex, returning a
    second candidate if the point sits exactly on a hex-grid edge (i.e.
    two of the three axis roundings are tied for "most in need of
    correction" to restore q+r+s=0). Ordinary (non-tied) points return a
    single candidate.
    """
    rq, rr, rs = round(q), round(r), round(s)
    dq, dr, ds = abs(rq - q), abs(rr - r), abs(rs - s)

    def fix(which: str) -> Tuple[int, int, int]:
        if which == "q":
            return (-rr - rs, rr, rs)
        if which == "r":
            return (rq, -rq - rs, rs)
        return (rq, rr, -rq - rr)

    diffs = {"q": dq, "r": dr, "s": ds}
    max_diff = max(diffs.values())
    tied = [k for k, v in diffs.items() if abs(v - max_diff) < _EPS]

    candidates = [fix(tied[0])]
    if len(tied) > 1:
        second = fix(tied[1])
        if second != candidates[0]:
            candidates.append(second)
    return candidates


def hex_line(a: Hex, b: Hex) -> List[List[Hex]]:
    """
    The straight-line path of hexes between two hex centers (endpoints
    included), one entry per step. Each step is normally a single hex;
    if the line runs exactly along a shared hex-grid edge at that step,
    both candidate hexes are returned (see rule 6 in the module
    docstring — has_los() picks the worse one).
    """
    n = hex_distance(a, b)
    aq, ar, as_ = _to_cube(a)
    bq, br, bs = _to_cube(b)

    if n == 0:
        return [[a]]

    path: List[List[Hex]] = []
    for i in range(n + 1):
        t = i / n
        q = aq + (bq - aq) * t
        r = ar + (br - ar) * t
        s = as_ + (bs - as_) * t
        candidates = [_from_cube(cq, cr, cs) for cq, cr, cs in _cube_round_candidates(q, r, s)]
        path.append(candidates)

    return path


# =============================================================================
# LOS rules
# =============================================================================


def _evaluate(attacker_hex: Hex, target_hex: Hex, terrain_map: Dict[str, object]) -> LOSTrace:
    hexes = terrain_map["hexes"]

    def hex_info(h: Hex):
        try:
            label = hex_label(*h)
        except ValueError:
            return None
        return hexes.get(label)

    a_info = hex_info(attacker_hex)
    b_info = hex_info(target_hex)
    if a_info is None:
        raise ValueError(f"LOS attacker hex {attacker_hex} is not on the loaded board.")
    if b_info is None:
        raise ValueError(f"LOS target hex {target_hex} is not on the loaded board.")

    a_level = a_info["level"]
    b_level = b_info["level"]
    highest_level = max(a_level, b_level)
    lowest_level = min(a_level, b_level)

    path = hex_line(attacker_hex, target_hex)
    total_distance = len(path) - 1

    steps: List[LOSStep] = [
        LOSStep(index=0, hex=attacker_hex, level=a_level, is_endpoint=True)
    ]

    if total_distance == 0:
        return LOSTrace(steps=steps, result=LOSResult(los=True, modifier=0, distance=0))

    modifier = 0
    blocked_at: Optional[int] = None

    def worse_key(item):
        _, _, blocked_here, contrib = item
        return (1 if blocked_here else 0, contrib)

    for step_index in range(1, total_distance):
        candidates = path[step_index]
        adjacent_to_low_a = step_index == 1 and a_level == lowest_level
        adjacent_to_low_b = step_index == total_distance - 1 and b_level == lowest_level
        adjacent_to_low_endpoint = adjacent_to_low_a or adjacent_to_low_b

        evaluated = []
        for c in candidates:
            info = hex_info(c)
            if info is None:
                raise ValueError(
                    f"Intervening LOS hex {c} is not on the loaded board — "
                    f"LOS calc requires the full line to be on-board."
                )
            level = info["level"]
            blocked_here = level >= highest_level + 2
            if adjacent_to_low_endpoint and level >= lowest_level + 2:
                blocked_here = True

            contrib = 0
            if not blocked_here:
                features = info["features"]
                if "woods" in features:
                    density = features["woods"][0] if features["woods"] else None
                    is_intervening = level == highest_level or (
                        level >= lowest_level and adjacent_to_low_endpoint
                    )
                    if is_intervening:
                        if density == "1":
                            contrib = 1
                        elif density == "2":
                            contrib = 2

            evaluated.append((c, level, blocked_here, contrib))

        chosen = max(evaluated, key=worse_key)
        chosen_hex, chosen_level, chosen_blocked, chosen_contrib = chosen
        other = next((e[0] for e in evaluated if e[0] != chosen_hex), None)

        after_block = blocked_at is not None
        this_step_blocks = False

        if not after_block:
            if chosen_blocked:
                blocked_at = step_index
                this_step_blocks = True
            else:
                modifier += chosen_contrib
                if modifier > 2:
                    blocked_at = step_index
                    this_step_blocks = True

        steps.append(LOSStep(
            index=step_index,
            hex=chosen_hex,
            other_candidate=other,
            level=chosen_level,
            is_endpoint=False,
            blocked=this_step_blocks,
            woods_contrib=(0 if after_block else chosen_contrib),
            cumulative_modifier=modifier,
            after_block=after_block,
        ))

    # Rule 5: partial cover, hex adjacent-on-path to the target only —
    # only applies if LOS survived the whole intervening path.
    if blocked_at is None:
        cover = 0
        for c in path[total_distance - 1]:
            info = hex_info(c)
            if info is not None and info["level"] == b_level + 1:
                cover = max(cover, 1)
        modifier += cover
        if steps and steps[-1].index == total_distance - 1:
            steps[-1].partial_cover = cover
            steps[-1].cumulative_modifier = modifier

    steps.append(LOSStep(
        index=total_distance,
        hex=target_hex,
        level=b_level,
        is_endpoint=True,
        cumulative_modifier=modifier,
        after_block=blocked_at is not None,
    ))

    los = blocked_at is None
    distance = blocked_at if blocked_at is not None else total_distance
    return LOSTrace(steps=steps, result=LOSResult(los=los, modifier=modifier, distance=distance))


def has_los(attacker_hex: Hex, target_hex: Hex, terrain_map: Dict[str, object]) -> LOSResult:
    return _evaluate(attacker_hex, target_hex, terrain_map).result


def trace_los_path(attacker_hex: Hex, target_hex: Hex, terrain_map: Dict[str, object]) -> LOSTrace:
    """Same evaluation as has_los(), but returns the full per-step trace
    (chosen hex, discarded tie-break candidate, per-step contribution,
    and exactly which step blocked) for callers that need to render or
    debug the line rather than just get the final result. los_viz.py is
    the current consumer."""
    return _evaluate(attacker_hex, target_hex, terrain_map)
