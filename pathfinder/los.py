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

=== Rules: the Core Rulebook, pp.56-58 and 66 (since 2026-10-21) ===
Daniel, 2026-10-21: "make sure the LOS rules match those in the rules and fix
prone mechs" - this replaces his simplified 2026-07-19 ruleset (woods counted
only at exactly the higher mech's level; a 2-level hard-block test; partial
cover without the height and prone conditions; per-step border picks).

  LOS level = the hex's level + the 'Mech's height: 2 standing, 1 prone
  (p.57). A water hex's level is its floor (terrain_rules.prepare_board), a
  building hex's its roof.
  Only the hexes BETWEEN the two 'Mechs count. Terrain intervenes if its
  level is >= both LOS levels, or >= the LOS level of the 'Mech it is
  adjacent to (p.57). A hill / building level that intervenes blocks LOS;
  woods / jungle (their level + 2) that intervene add their points - light 1,
  heavy 2, also the to-hit modifier - and 3+ points block (p.58). Water never
  intervenes. 'Mechs never intervene. Adjacent 'Mechs always see each other.
  Partial cover (p.66): a standing target next to a hex one level higher
  along the LOS (hill or building; not woods, not water), unless the
  attacker's LOS level is higher than the target's; a prone target gets none
  - that hex intervenes and hides it. Standing in depth 1 water: partial
  cover even against higher attackers, not against a fully submerged one.
  Target in woods / jungle: +1 / +2 to hit (p.66), never part of LOS.
  Tactical Operations: Advanced Rules terrain (2026-10-27):
  - Ultra-heavy woods / jungle (density 3) rise 3 levels; ONE intervening
    hex blocks LOS; a target in one +3 (TO:AR pp.29, 38) - 'Mechs can't
    enter them (terrain_rules), so only the blocking matters here.
  - Planted fields rise 1 level; +1 to hit for every two full intervening
    planted-field hexes, 6 intervening block LOS (TO:AR p.36). They count
    on their own, not as woods points. With the Core test above a field
    intervenes between standing 'Mechs only at a lower level or next to a
    prone one - the book's p.37 example (a 'Mech ignores the field next to
    itself, the vehicle's neighbour counts) works the same way.
  Smoke (2026-10-27, Core p.124; INTEGRATION__smoke keeps it in a hex's
  info["smoke"]): light acts as light woods, heavy as heavy woods, 2 levels
  above the hex's ground (a water hex's surface), but never raising a hex's
  intervening points past 2 or a target hex's modifier past +2, woods
  included. Each step's smoke share is LOSStep.smoke_contrib (an active
  probe ignores it - INTEGRATION__smoke.probe_relief).
  A line exactly on a hex border (p.56): the target's controller picks the
  side for the whole line - here the side worse for the attacker (blocked,
  else the higher modifier); a side with an off-board hex can't be picked.
  The same choice gives the attack direction (p.73, attack_resolution.
  attack_side).

Not modeled: firing at a HEX (p.58: an adjacent hex intervenes only if
higher) - Arrow IV / artillery use the target 'Mech's line; levels of
multi-level buildings' insides (buildings are passive, PASSIVE_BUILDINGS).

Off-board line assumption (Daniel, 2026-07-19): has_los()/trace_los_path()
raise ValueError if any hex on the line — endpoint or intervening — is
off the loaded board. This is deliberately NOT caught/handled gracefully:
Daniel confirmed that would only matter for concave board shapes, which
this project doesn't need to support.

"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from hex_geometry import hex_label

Hex = Tuple[int, int]  # (x, y) doubled coordinates, no facing

# Target-hex woods to-hit modifier by woods density (Core p.66): light +1,
# heavy +2. Recorded on the target's LOSStep as woods_contrib.
TARGET_WOODS_MODIFIER = {"1": 1, "2": 2, "3": 3}         # ultra-heavy +3 (TO:AR p.38)


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
    smoke_contrib: int = 0              # the part of this step's points / modifier that is smoke (Core p.124)
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


def _cube_round(q: float, r: float, s: float) -> Tuple[int, int, int]:
    """The hex a fractional cube coordinate is in (standard cube rounding)."""
    rq, rr, rs = round(q), round(r), round(s)
    dq, dr, ds = abs(rq - q), abs(rr - r), abs(rs - s)
    if dq > dr and dq > ds:
        return (-rr - rs, rr, rs)
    if dr > ds:
        return (rq, -rq - rs, rs)
    return (rq, rr, -rq - rr)


# A nudge off the line, far smaller than a hex and summing to 0 (cube coordinates).
_NUDGE = (1e-6, 2e-6, -3e-6)


def _cube_round_candidates(q: float, r: float, s: float) -> List[Tuple[int, int, int]]:
    """
    The hex a point on the line is in, or BOTH hexes when the point sits
    exactly on the edge between two (p.56: LOS "exactly on the line between
    two hexes"). Found by rounding the point nudged a hair to each side of the
    edge. (2026-10-20, Claude: the old tie test rounded both tied coordinates
    with Python's round-half-to-even, which often sent both to the SAME hex,
    so the second hex was missed.)
    """
    nq, nr, ns = _NUDGE
    first = _cube_round(q + nq, r + nr, s + ns)
    second = _cube_round(q - nq, r - nr, s - ns)
    return [first] if first == second else [first, second]


# (dx, dy) -> the line's steps from (0, 0) to (dx, dy) (hex_line, 2026-10-21).
_LINE_SHAPES: Dict[Tuple[int, int], List[List[Hex]]] = {}


def hex_line(a: Hex, b: Hex) -> List[List[Hex]]:
    """
    The straight-line path of hexes between two hex centers (endpoints
    included), one entry per step. Each step is normally a single hex;
    if the line runs exactly along a shared hex-grid edge at that step,
    both candidate hexes are returned (see rule 6 in the module
    docstring — has_los() picks the worse one).

    Speed only (2026-10-21, Claude): the line's shape depends only on the
    offset b - a, so it is worked out once per offset (from (0, 0)) and
    shifted onto a. tests/test_pathfinder.py checks this against
    _hex_line_direct for every pair of hexes on a board.
    """
    dx, dy = b[0] - a[0], b[1] - a[1]
    shape = _LINE_SHAPES.get((dx, dy))
    if shape is None:
        shape = _LINE_SHAPES[(dx, dy)] = _hex_line_direct((0, 0), (dx, dy))
    ax, ay = a
    return [[(ax + x, ay + y) for x, y in step] for step in shape]


def _hex_line_direct(a: Hex, b: Hex) -> List[List[Hex]]:
    """hex_line worked out from scratch for this a and b."""
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


STANDING_HEIGHT, PRONE_HEIGHT = 2, 1     # 'Mech heights in levels (p.57)
WOODS_HEIGHT = 2                          # woods / jungle rise 2 levels above their hex (p.57)
WOODS_BLOCK_POINTS = 3                    # 3+ points of intervening woods / jungle block LOS (p.58)
WOODS_POINTS = {"1": 1, "2": 2}           # light 1, heavy 2 (p.58; also their to-hit modifier, p.66)
WOODS_FEATURES = ("woods", "jungle")
ULTRA_HEAVY, ULTRA_HEAVY_HEIGHT = "3", 3   # ultra-heavy woods / jungle: 3 levels, one hex blocks (TO:AR pp.29, 38)
FIELDS_HEIGHT = 1                          # planted fields rise 1 level (TO:AR p.36)
FIELDS_PER_POINT, FIELDS_BLOCK = 2, 6      # +1 per two full intervening hexes; 6 block LOS (p.36)
SMOKE_HEIGHT = 2                           # smoke rises 2 levels above the ground (Core p.124)
SMOKE_POINTS = {"1": 1, "2": 2}            # light / heavy: as light / heavy woods (Core p.124)
SMOKE_HEX_CAP = 2                          # smoke never takes a hex past 2 points / +2 (Core p.124)


def _smoke_share(info, woods_points: int) -> int:
    """What a hex's smoke adds to `woods_points` (its woods' points or
    to-hit modifier): never past 2 (Core p.124)."""
    smoke = info.get("smoke")
    if not smoke:
        return 0
    return max(0, min(SMOKE_HEX_CAP, woods_points + SMOKE_POINTS[smoke["density"]]) - woods_points)


def _woods_density(features) -> Optional[str]:
    for name in WOODS_FEATURES:
        if name in features:
            return features[name][0] if features[name] else None
    return None


def _evaluate(attacker_hex: Hex, target_hex: Hex, terrain_map: Dict[str, object],
              attacker_height: int = STANDING_HEIGHT, target_height: int = STANDING_HEIGHT) -> LOSTrace:
    """The Core Rulebook's line of sight (pp.56-58, 66; rebuilt 2026-10-21 -
    Daniel: "make sure the LOS rules match those in the rules and fix prone
    mechs"). Heights: 2 for a standing 'Mech, 1 for a prone one (p.57)."""
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

    a_level, b_level = a_info["level"], b_info["level"]
    a_los, b_los = a_level + attacker_height, b_level + target_height      # LOS levels (p.57)

    path = hex_line(attacker_hex, target_hex)
    n = len(path) - 1
    if n == 0:
        steps = [LOSStep(index=0, hex=attacker_hex, level=a_level, is_endpoint=True)]
        return LOSTrace(steps=steps, result=LOSResult(los=True, modifier=0, distance=0))

    def intervenes(top: int, i: int) -> bool:
        """p.57: terrain intervenes if its level is >= both LOS levels, or >= the
        LOS level of the 'Mech it is adjacent to."""
        return ((top >= a_los and top >= b_los) or (i == 1 and top >= a_los)
                or (i == n - 1 and top >= b_los))

    # A line exactly on the border between two hexes: the target's controller
    # picks which side it runs along, for the whole line (p.56) - so each side is
    # one candidate path. A side through a hex off the board isn't there to pick.
    sides = []
    for pick in (0, -1):
        hexes_on = [path[i][pick] for i in range(1, n)]
        if all(hex_info(h) is not None for h in hexes_on):
            sides.append(hexes_on)
        if all(len(path[i]) == 1 for i in range(1, n)):
            break                                    # no border steps: one path
    if not sides:
        raise ValueError(f"LOS line {attacker_hex} -> {target_hex} runs off the loaded board.")

    def walk(hexes_on):
        """(steps, blocked_at, modifier) along one path - modifier is the
        intervening woods (each hex its points) plus partial cover; the
        target's own woods are added after the choice."""
        steps: List[LOSStep] = [LOSStep(index=0, hex=attacker_hex, level=a_level, is_endpoint=True)]
        woods, fields, blocked_at = 0, 0, None
        for i, h in enumerate(hexes_on, start=1):
            info = hex_info(h)
            level = info["level"]
            after = blocked_at is not None
            contrib, blocks, smoke = 0, False, 0
            if not after:
                # Hills and buildings (a roof's level is the hex's level): one
                # intervening hex blocks (p.58). Water never intervenes - a water
                # hex's level is its floor (terrain_rules.prepare_board).
                blocks = intervenes(level, i)
                density = _woods_density(info["features"])
                if not blocks and density == ULTRA_HEAVY:
                    blocks = intervenes(level + ULTRA_HEAVY_HEIGHT, i)       # TO:AR p.38
                elif not blocks and density is not None and intervenes(level + WOODS_HEIGHT, i):
                    contrib = WOODS_POINTS.get(density, 0)
                    woods += contrib
                    blocks = woods >= WOODS_BLOCK_POINTS
                if (not blocks and "smoke" in info
                        and intervenes(info.get("surface_level", level) + SMOKE_HEIGHT, i)):
                    smoke = _smoke_share(info, contrib)                      # Core p.124
                    contrib += smoke
                    woods += smoke
                    blocks = woods >= WOODS_BLOCK_POINTS
                if not blocks and "planted_fields" in info["features"] and intervenes(level + FIELDS_HEIGHT, i):
                    fields += 1                                              # TO:AR p.36
                    contrib += 1 if fields % FIELDS_PER_POINT == 0 else 0  # this hex completes a pair: +1
                    blocks = fields >= FIELDS_BLOCK
                if blocks:
                    blocked_at = i
            steps.append(LOSStep(index=i, hex=h, level=level, blocked=blocks, woods_contrib=contrib,
                                 cumulative_modifier=woods + fields // FIELDS_PER_POINT, after_block=after,
                                 smoke_contrib=smoke))
        cover = 0
        if blocked_at is None:
            # Partial cover (p.66): a STANDING target next to a hex one level higher
            # along the LOS (a hill or a building - not water, not woods), unless
            # the attacker's LOS level is higher. A prone target gets none: that hex
            # hides it instead (it intervenes above). Water: standing in depth 1 is
            # partial cover even against higher attackers, but not against a fully
            # submerged attacker (p.67) - standing in depth 2+, or prone in water.
            if target_height == STANDING_HEIGHT:
                if n >= 2:
                    info = hex_info(hexes_on[-1])
                    if info["level"] == b_level + 1 and not info.get("depth") and a_los <= b_los:
                        cover = 1
                a_depth = a_info.get("depth", 0)
                a_submerged = a_depth >= 2 or (a_depth >= 1 and attacker_height == PRONE_HEIGHT)
                if b_info.get("depth") == 1 and not a_submerged:
                    cover = 1
            if n >= 2:
                steps[-1].partial_cover = cover
                steps[-1].cumulative_modifier = woods + fields // FIELDS_PER_POINT + cover
        return steps, blocked_at, woods + fields // FIELDS_PER_POINT + cover, cover

    walked = [walk(h) for h in sides]
    # The target's choice: a blocked line if it can, else the higher modifier.
    best = max(range(len(walked)), key=lambda k: (walked[k][1] is not None, walked[k][2]))
    steps, blocked_at, modifier, cover = walked[best]
    if len(walked) > 1:
        for step, other in zip(steps[1:], sides[1 - best]):
            if other != step.hex:
                step.other_candidate = other

    # Target in woods / jungle (p.66): +1 light, +2 heavy - a to-hit modifier only;
    # the target's own hex never affects LOS (pp.57-58).
    target_woods = target_smoke = 0
    if blocked_at is None:
        target_woods = TARGET_WOODS_MODIFIER.get(_woods_density(b_info["features"]), 0)
        target_smoke = _smoke_share(b_info, target_woods)                       # Core p.124
        modifier += target_woods + target_smoke
    steps.append(LOSStep(
        index=n,
        hex=target_hex,
        level=b_level,
        is_endpoint=True,
        woods_contrib=target_woods + target_smoke,
        smoke_contrib=target_smoke,
        partial_cover=cover,   # also here: callers read steps[-1]
        cumulative_modifier=modifier,
        after_block=blocked_at is not None,
    ))
    los = blocked_at is None
    return LOSTrace(steps=steps, result=LOSResult(los=los, modifier=modifier,
                                                  distance=n if los else blocked_at))


def target_hex_modifier(target_hex: Hex, terrain_map: Dict[str, object]) -> int:
    """The to-hit modifier of the target's own hex alone - woods / jungle
    (p.66) - for an attack that takes no LOS modifiers: indirect fire with
    no spotter (2026-10-27, TO:AUE p.136 'Mech mortars; Core p.70: "Attacks
    ignoring Spotter LOS modifiers still apply effects of the target's hex")."""
    info = terrain_map["hexes"][hex_label(*target_hex)]
    woods = TARGET_WOODS_MODIFIER.get(_woods_density(info["features"]), 0)
    return woods + _smoke_share(info, woods)


def has_los(attacker_hex: Hex, target_hex: Hex, terrain_map: Dict[str, object],
            attacker_height: int = STANDING_HEIGHT, target_height: int = STANDING_HEIGHT) -> LOSResult:
    return _evaluate(attacker_hex, target_hex, terrain_map, attacker_height, target_height).result


def trace_los_path(attacker_hex: Hex, target_hex: Hex, terrain_map: Dict[str, object],
                   attacker_height: int = STANDING_HEIGHT, target_height: int = STANDING_HEIGHT) -> LOSTrace:
    """Same evaluation as has_los(), but returns the full per-step trace
    (chosen hex, discarded tie-break candidate, per-step contribution,
    and exactly which step blocked) for callers that need to render or
    debug the line rather than just get the final result. los_viz.py is
    the current consumer."""
    return _evaluate(attacker_hex, target_hex, terrain_map, attacker_height, target_height)
