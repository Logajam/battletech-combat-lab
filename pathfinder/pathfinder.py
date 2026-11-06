"""
pathfinder.py — the DP engine. Builds the full table of
(x, y, facing, mp_spent) -> max forward-move count achievable while
landing in that exact state.

Two modes:

  - terrain_map=None: original Phase 1 flat-terrain layered sweep. Every
    transition costs exactly 1 MP, unbounded plane (no board edges). Kept
    unchanged so the Phase 1 regression tests in validation.py still mean
    what they meant before.

  - terrain_map given (a board_parser.parse_board_file() result): Phase 2
    bucket-queue sweep (Dial's algorithm) per
    movement_pathfinder_handoff.md Section 4a. Forward-move cost comes
    from terrain_rules.step_cost() (backward moves too, when
    backward_mp is given - 2026-10-20), which also says which steps are
    allowed at all (level-change limit, roofs - 2026-10-21); turning always costs 1 MP
    (facing changes have no terrain dependency). Board-edge bounding is
    enforced by simply not generating a transition into a hex that isn't
    in terrain_map — not by filtering afterward (per handoff Section 4e).

Load-bearing invariant (both modes): every transition cost must be >= 1.
Bucket-queue mode relies on this to guarantee each layer is processed
exactly once (a transition from a state finalized at layer mp always
lands at a layer > mp, never <= mp). terrain_rules.step_cost()
asserts this itself.
"""

from typing import Dict, Optional, Set, Tuple

from hex_geometry import FACING_DELTAS, State, hex_label
import terrain_rules

MovementTable = Dict[State, Dict[int, int]]  # state -> {mp_spent: max forward_count}


def _record(table: MovementTable, state: State, mp: int, forward_count: int) -> None:
    col = table.setdefault(state, {})
    if mp not in col or forward_count > col[mp]:
        col[mp] = forward_count


def _build_flat(start_x: int, start_y: int, start_facing: int, mp_budget: int) -> MovementTable:
    """Phase 1: uniform 1-MP layered sweep, unbounded plane."""
    table: MovementTable = {}
    start_state: State = (start_x, start_y, start_facing)
    _record(table, start_state, 0, 0)

    layer: Dict[State, int] = {start_state: 0}

    for mp in range(mp_budget):
        next_layer: Dict[State, int] = {}

        def push(state: State, forward_count: int) -> None:
            existing = next_layer.get(state)
            if existing is None or forward_count > existing:
                next_layer[state] = forward_count

        for (x, y, facing), fc in layer.items():
            dx, dy = FACING_DELTAS[facing]
            push((x + dx, y + dy, facing), fc + 1)
            push((x, y, (facing - 1) % 6), fc)
            push((x, y, (facing + 1) % 6), fc)

        for state, fc in next_layer.items():
            _record(table, state, mp + 1, fc)

        layer = next_layer

    return table


class _BoardCache:
    """What a terrain search keeps asking about a board that never changes
    during a battle (2026-10-28, speed): a hex's info by (x, y), and the cost /
    terrain PSRs / hazard of stepping from one hex into a neighbour, per
    mover level limit. Filled lazily - a search only ever touches the hexes
    inside its movement footprint, so only those are computed, and a second
    search whose footprint overlaps (another unit, or the same unit next turn)
    finds them already done. Blocked hexes are NOT cached (they change turn
    to turn); the searches test them before asking."""

    __slots__ = ("hexes", "info_xy", "steps", "extras", "turns", "tables", "hazardous", "rust")

    def __init__(self, terrain_map):
        self.hexes = terrain_map["hexes"]
        # Hazards (magma crust breaking, INTEGRATION__hazards) change during a battle: such a board
        # reads them live and shares no finished tables (their PathTables carry the hazards).
        self.hazardous = any(f in info["features"] for info in self.hexes.values()
                             for f in terrain_rules.HAZARD_FEATURES)
        self.info_xy = {}
        self.steps = {}       # {limit key: {(fx, fy, tx, ty, backward): cost or None}}
        self.extras = {}      # {limit key: {(fx, fy, tx, ty, backward): (cost, always, run_only)}}
        self.tables = {}      # finished movement tables, see build_movement_table
        self.turns = {}       # {(x, y): (always, run_only)} PSRs a facing change forces there
        self.rust = {}        # {limit key: fastcore.PathBoard or False} (ranged_combat._rust_board); dies with the board cache

    def info(self, x, y):
        try:
            return self.info_xy[(x, y)]
        except KeyError:
            try:
                got = self.hexes.get(hex_label(x, y))
            except ValueError:
                got = None
            self.info_xy[(x, y)] = got
            return got

    def cost(self, level_limit, fx, fy, tx, ty, backward=False):
        """terrain_rules.step_cost for the step (fx, fy) -> (tx, ty); both hexes are on the board."""
        steps = self.steps.setdefault((int(level_limit), getattr(level_limit, "superheavy", False)), {})
        key = (fx, fy, tx, ty, backward)
        try:
            return steps[key]
        except KeyError:
            got = steps[key] = terrain_rules.step_cost(self.info(fx, fy), self.info(tx, ty), level_limit, backward)
            return got

    def extra(self, level_limit, fx, fy, tx, ty, backward=False):
        """(cost, always PSRs, run-only PSRs) of the step - cost None if it isn't allowed. The hex's hazard
        is NOT here: magma crust breaks during a battle (INTEGRATION__hazards), so hazard() reads it live."""
        extras = self.extras.setdefault((int(level_limit), getattr(level_limit, "superheavy", False)), {})
        key = (fx, fy, tx, ty, backward)
        try:
            return extras[key]
        except KeyError:
            here, there = self.info(fx, fy), self.info(tx, ty)
            cost = terrain_rules.step_cost(here, there, level_limit, backward)
            if cost is None:
                got = (None, 0, 0)
            else:
                a, r = terrain_rules.step_psrs(here, there, backward)
                got = (cost, a, r)
            extras[key] = got
            return got

    def hazard(self, x, y):
        """terrain_rules.step_hazard of the hex, read live (0 at once on a board with no hazard feature)."""
        return terrain_rules.step_hazard(self.info(x, y)) if self.hazardous else 0.0

    def turn(self, x, y):
        try:
            return self.turns[(x, y)]
        except KeyError:
            got = self.turns[(x, y)] = terrain_rules.turn_psrs(self.info(x, y))
            return got


TABLE_CACHE_SIZE = 600     # finished tables kept per board (a table is a few hundred states)
_BOARDS = {}      # {id(terrain_map): (terrain_map, _BoardCache)} - the map is held so its id stays unique


def _board(terrain_map):
    """The (shared, lazily filled) _BoardCache of a loaded board. Code that
    edits a hex during a battle (magma crust breaking) calls forget_board."""
    got = _BOARDS.get(id(terrain_map))
    if got is None or got[0] is not terrain_map:
        if len(_BOARDS) >= 8:
            _BOARDS.clear()
        got = _BOARDS[id(terrain_map)] = (terrain_map, _BoardCache(terrain_map))
    return got[1]


def forget_board(terrain_map):
    """Drop a board's _BoardCache after one of its hexes changed (2026-10-29,
    review fix: a magma crust that breaks becomes liquid magma, +1 MP and a
    different PSR, TO:AR p.30 - the cached step costs of that hex would be
    stale). Rare, so the whole board is simply refilled on the next search."""
    _BOARDS.pop(id(terrain_map), None)


def _build_terrain_aware(
    start_x: int,
    start_y: int,
    start_facing: int,
    mp_budget: int,
    terrain_map: Dict[str, object],
    backward_mp: Optional[int] = None,
    level_limit: int = terrain_rules.MAX_LEVEL_CHANGE,
    blocked: Optional[Tuple[int, int]] = None,
) -> MovementTable:
    """Phase 2: bucket-queue (Dial's algorithm) sweep, board-edge bounded.

    backward_mp (added 2026-10-20, Claude - Core Rulebook pp.45-46): when given
    (the mech's Walking MP), backward moves are allowed too - into the hex
    directly behind, facing unchanged, same entry cost as moving forward. Only
    a walking 'Mech may move backward ("A 'Mech can only move backward if it
    uses Walking MP that turn", p.46), so a path that has moved backward never
    spends more than backward_mp. TMM counts only the hexes since the mech
    last reversed direction (p.63: "3 back then 2 forward = based on 2
    hexes"), so the forward count restarts at 1 on a reversal; turning in
    place doesn't reverse anything.
    Backward LEVEL changes (one level, each needing a PSR, p.46) are not
    offered: only a backward step into a hex of the same level
    (terrain_rules.step_cost with backward=True). The movement
    scoring has no way to price a PSR in the middle of a move yet (GAP in
    INTEGRATION__RULES_REVIEW.md).

    The search state carries two extra fields the output doesn't: the
    direction of the last hex moved (0 none yet, +1 forward, -1 backward) and
    whether the path has moved backward at all. Within one such (direction,
    used-backward) pair a higher forward count is never worse, so only the best
    is kept, as before. With backward_mp None, every path is forward-only and
    the table is exactly what it was before 2026-10-20.

    blocked (2026-10-21, p.48): a hex no step may enter - a mobile enemy
    'Mech's ("cannot enter a hex occupied by an enemy 'Mech unless that 'Mech
    is immobile"); treated like a hex off the board."""
    board = _board(terrain_map)
    blocked = _blocked_set(blocked)
    board_info, board_cost = board.info, board.cost

    def hex_info(x: int, y: int) -> Optional[dict]:
        if (x, y) in blocked:
            return None
        return board_info(x, y)

    table: MovementTable = {}
    start_info = hex_info(start_x, start_y)
    if start_info is None:
        raise ValueError(
            f"Start hex {hex_label(start_x, start_y)!r} is not on the loaded board — "
            f"can't build a movement table from an off-board start."
        )
    if start_info["impassable"]:
        raise ValueError(f"Start hex {hex_label(start_x, start_y)!r} is marked impassable.")

    # Search key: (x, y, facing, last direction, moved backward yet).
    SearchKey = Tuple[int, int, int, int, bool]
    start_key: SearchKey = (start_x, start_y, start_facing, 0, False)

    # buckets[mp] = {search key: best forward_count seen so far at this mp}
    buckets: Dict[int, Dict[SearchKey, int]] = {0: {start_key: 0}}

    def push(mp: int, key: SearchKey, fc: int) -> None:
        b = buckets.setdefault(mp, {})
        if b.get(key, -1) < fc:
            b[key] = fc

    for mp in range(mp_budget + 1):
        bucket = buckets.get(mp)
        if not bucket:
            continue

        for (x, y, facing, last, used_back), fc in bucket.items():
            _record(table, (x, y, facing), mp, fc)
            budget = backward_mp if used_back else mp_budget     # a path that moved backward is walking

            current_info = hex_info(x, y)
            if current_info is None:
                continue  # shouldn't happen (we never generate off-board states), defensive only

            dx, dy = FACING_DELTAS[facing]

            # 1. Forward move: cost from terrain_rules, into next hex.
            dest_info = hex_info(x + dx, y + dy)
            if dest_info is not None:
                cost = board_cost(level_limit, x, y, x + dx, y + dy)
                if cost is not None and mp + cost <= budget:
                    push(mp + cost, (x + dx, y + dy, facing, 1, used_back), fc + 1 if last >= 0 else 1)

            # 2. Backward move (walking only, same level only - see docstring;
            # level changes, with their PSR, are _build_terrain_psr's).
            if backward_mp is not None:
                dest_info = hex_info(x - dx, y - dy)
                if dest_info is not None and dest_info["level"] == current_info["level"]:
                    cost = board_cost(level_limit, x, y, x - dx, y - dy, True)
                    if cost is not None and mp + cost <= backward_mp:
                        push(mp + cost, (x - dx, y - dy, facing, -1, True), fc + 1 if last <= 0 else 1)

            # 3. / 4. Turning: always costs 1 MP, hex unchanged, forward_count unchanged.
            if mp + 1 <= budget:
                for new_facing in ((facing - 1) % 6, (facing + 1) % 6):
                    push(mp + 1, (x, y, new_facing, last, used_back), fc)

    return table


class PathTable(dict):
    """A MovementTable (state -> {mp_spent: forward_count}) that also knows,
    for each entry, the terrain PSRs its path forces - psrs[state][mp] =
    (always, run_only), terrain_rules.step_psrs / turn_psrs - and, when asked
    for, how to walk it (path()). Built by _build_terrain_psr (2026-10-21,
    Daniel's movement subphase)."""

    def __init__(self):
        super().__init__()
        self.psrs: Dict[State, Dict[int, Tuple[int, int]]] = {}
        self.hazards: Dict[State, Dict[int, float]] = {}   # expected damage of the hexes entered (terrain_rules.step_hazard)
        self.parents = None        # {(search key, mp): (previous key, previous mp, step)} when kept
        self.best_keys = {}        # {(state, mp): the search key that won the table entry}

    def path(self, state: State, mp: int):
        """[(step, (x, y, facing), mp after)] from the start to `state` at `mp`
        (needs keep_parents); step is "forward", "backward" or "turn"."""
        key = self.best_keys[(state, mp)]
        out = []
        while (key, mp) in self.parents:
            prev_key, prev_mp, step = self.parents[(key, mp)]
            out.append((step, key[:3], mp))
            key, mp = prev_key, prev_mp
        out.reverse()
        return out


def _build_terrain_psr(
    start_x: int,
    start_y: int,
    start_facing: int,
    mp_budget: int,
    terrain_map: Dict[str, object],
    backward_mp: Optional[int],
    level_limit: int,
    keep_parents: bool,
    blocked: Optional[Tuple[int, int]] = None,
) -> PathTable:
    """_build_terrain_aware on a board where steps can force terrain PSRs
    (terrain_rules.has_psr_terrain; 2026-10-21, Daniel: "There is a
    difference between planning where you want to go which the picker does.
    And actually getting there"). The same search, but each entry also counts
    its path's terrain PSRs (always, run-only); between two paths to the same
    state and MP, the one with more hexes moved wins as before, then the one
    with fewer PSRs. Hazards (2026-10-27): each entry also adds up the
    expected damage of the hexes its path enters (terrain_rules.step_hazard -
    magma, hazardous liquid), and between two paths to the same state and MP
    the less damaging wins FIRST - before hexes moved; with no hazard on the
    board every path scores 0 and nothing changes. Backward level changes
    (one level, a PSR each, p.46) are allowed here. keep_parents: remember
    each entry's path (PathTable.path), for the movement subphase that walks
    it. blocked: as _build_terrain_aware."""
    board = _board(terrain_map)
    blocked = _blocked_set(blocked)
    board_info, board_extra, board_hazard = board.info, board.extra, board.hazard

    def hex_info(x: int, y: int) -> Optional[dict]:
        if (x, y) in blocked:
            return None
        return board_info(x, y)

    table = PathTable()
    if keep_parents:
        table.parents = {}
    if hex_info(start_x, start_y) is None:
        raise ValueError(f"Start hex {hex_label(start_x, start_y)!r} is not on the loaded board.")

    start_key = (start_x, start_y, start_facing, 0, False)
    # buckets[mp] = {search key: (-hazard, forward_count, -total PSRs, always, run_only)}
    buckets: Dict[int, Dict[tuple, tuple]] = {0: {start_key: (0.0, 0, 0, 0, 0)}}
    parents = table.parents

    def push(mp, key, value, prev_key, prev_mp, step):
        b = buckets.setdefault(mp, {})
        old = b.get(key)
        if old is None or value[:3] > old[:3]:
            b[key] = value
            if parents is not None:
                parents[(key, mp)] = (prev_key, prev_mp, step)

    for mp in range(mp_budget + 1):
        bucket = buckets.get(mp)
        if not bucket:
            continue
        for key, value in bucket.items():
            x, y, facing, last, used_back = key
            hz, fc, neg, always, run_only = value
            state = (x, y, facing)
            col = table.setdefault(state, {})
            if mp not in col or (hz, fc, neg) > (-table.hazards[state][mp], col[mp], -sum(table.psrs[state][mp])):
                col[mp] = fc
                table.psrs.setdefault(state, {})[mp] = (always, run_only)
                table.hazards.setdefault(state, {})[mp] = -hz if hz else 0.0
                table.best_keys[(state, mp)] = key
            budget = backward_mp if used_back else mp_budget
            current_info = hex_info(x, y)
            dx, dy = FACING_DELTAS[facing]

            # 1. Forward move.
            dest_info = hex_info(x + dx, y + dy)
            if dest_info is not None:
                cost, a, r = board_extra(level_limit, x, y, x + dx, y + dy)
                if cost is not None and mp + cost <= budget:
                    push(mp + cost, (x + dx, y + dy, facing, 1, used_back),
                         (hz - board_hazard(x + dx, y + dy), fc + 1 if last >= 0 else 1, neg - a - r,
                          always + a, run_only + r), key, mp, "forward")

            # 2. Backward move (walking only; a level change costs a PSR).
            if backward_mp is not None:
                dest_info = hex_info(x - dx, y - dy)
                if dest_info is not None:
                    cost, a, r = board_extra(level_limit, x, y, x - dx, y - dy, True)
                    if cost is not None and mp + cost <= backward_mp:
                        push(mp + cost, (x - dx, y - dy, facing, -1, True),
                             (hz - board_hazard(x - dx, y - dy), fc + 1 if last <= 0 else 1, neg - a - r,
                              always + a, run_only + r), key, mp, "backward")

            # 3. / 4. Turning (mud: a PSR if running, p.124).
            if mp + 1 <= budget:
                a, r = board.turn(x, y)
                for new_facing in ((facing - 1) % 6, (facing + 1) % 6):
                    push(mp + 1, (x, y, new_facing, last, used_back), (hz, fc, neg - a - r, always + a, run_only + r),
                         key, mp, "turn")
    return table


def _blocked_set(blocked):
    """`blocked` as a frozenset of (x, y) hexes: None (nothing blocked), one
    (x, y) pair, or a collection of pairs (several mobile enemy 'Mechs on the
    board, 2026-10-28 - the multi-unit battle)."""
    if blocked is None:
        return frozenset()
    if len(blocked) == 2 and all(isinstance(v, int) for v in blocked):
        return frozenset((tuple(blocked),))
    return frozenset(blocked)


def build_movement_table(
    start_x: int,
    start_y: int,
    start_facing: int,
    mp_budget: int,
    terrain_map: Optional[Dict[str, object]] = None,
    backward_mp: Optional[int] = None,
    level_limit: int = terrain_rules.MAX_LEVEL_CHANGE,
    keep_parents: bool = False,
    blocked: Optional[Tuple[int, int]] = None,
) -> MovementTable:
    """backward_mp: the mech's Walking MP to allow backward moves (terrain
    mode only - see _build_terrain_aware); None = forward moves only.
    level_limit (2026-10-21, pp.46-47): most levels one ground step may climb
    or drop - terrain_rules.max_level_change() (2, or 1 with a destroyed hip).
    On a board where a step can force a terrain PSR (terrain_rules.
    has_psr_terrain) the table is a PathTable (PSR counts per entry, paths
    with keep_parents) - 2026-10-21, Daniel's movement subphase.
    blocked (2026-10-21, p.48): an (x, y) hex no ground step may enter - a
    mobile enemy 'Mech's (terrain mode only)."""
    if start_facing not in FACING_DELTAS:
        raise ValueError(f"start_facing must be 0-5, got {start_facing}")
    if mp_budget < 0:
        raise ValueError("mp_budget must be non-negative")

    if terrain_map is None:
        return _build_flat(start_x, start_y, start_facing, mp_budget)
    if keep_parents:                          # the movement subphase walks its own copy of the path
        return _build_terrain_psr(start_x, start_y, start_facing, mp_budget, terrain_map, backward_mp, level_limit,
                                  keep_parents, blocked)
    # A table is a pure function of its arguments on a board that never
    # changes, and nobody moves while the units plan - so identical requests
    # (the same unit next to the same enemies, a second unit looking at the
    # same enemy, the six facings of a stand-up) share one table. 2026-10-28:
    # callers must treat it as read-only. A blocked hex farther than the MP
    # budget can't be entered, so it doesn't make a different table.
    board = _board(terrain_map)
    near = frozenset(b for b in _blocked_set(blocked)
                     if abs(b[0] - start_x) <= mp_budget and abs(b[1] - start_y) <= 2 * mp_budget)   # y counts half-hexes
    key = (start_x, start_y, start_facing, mp_budget, backward_mp,
           int(level_limit), getattr(level_limit, "superheavy", False), near)
    got = None if board.hazardous else board.tables.get(key)
    if got is not None:
        return got
    if terrain_rules.has_psr_terrain(terrain_map):
        got = _build_terrain_psr(start_x, start_y, start_facing, mp_budget, terrain_map, backward_mp, level_limit,
                                 False, near)
    else:
        got = _build_terrain_aware(start_x, start_y, start_facing, mp_budget, terrain_map, backward_mp, level_limit,
                                   near)
    if board.hazardous:
        return got
    if len(board.tables) >= TABLE_CACHE_SIZE:
        board.tables.clear()                  # simple and bounded; a battle refills what it uses
    board.tables[key] = got
    return got


def query_envelope(table: MovementTable) -> Set[State]:
    """Every (x, y, facing) reachable at all, at any mp_spent <= budget."""
    return set(table.keys())


def query_max_forward_count(table: MovementTable) -> Dict[State, int]:
    """
    For each reachable (x, y, facing), the highest forward-count achievable
    across all mp_spent values that reach it — the table that feeds TMM.
    """
    return {state: max(col.values()) for state, col in table.items()}
