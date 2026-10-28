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
    hexes = terrain_map["hexes"]
    blocked = _blocked_set(blocked)

    def hex_info(x: int, y: int) -> Optional[dict]:
        if (x, y) in blocked:
            return None
        try:
            label = hex_label(x, y)
        except ValueError:
            return None
        return hexes.get(label)

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
                cost = terrain_rules.step_cost(current_info, dest_info, level_limit)
                if cost is not None and mp + cost <= budget:
                    push(mp + cost, (x + dx, y + dy, facing, 1, used_back), fc + 1 if last >= 0 else 1)

            # 2. Backward move (walking only, same level only - see docstring;
            # level changes, with their PSR, are _build_terrain_psr's).
            if backward_mp is not None:
                dest_info = hex_info(x - dx, y - dy)
                if dest_info is not None and dest_info["level"] == current_info["level"]:
                    cost = terrain_rules.step_cost(current_info, dest_info, level_limit, backward=True)
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
    hexes = terrain_map["hexes"]
    blocked = _blocked_set(blocked)

    def hex_info(x: int, y: int) -> Optional[dict]:
        if (x, y) in blocked:
            return None
        try:
            label = hex_label(x, y)
        except ValueError:
            return None
        return hexes.get(label)

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
                cost = terrain_rules.step_cost(current_info, dest_info, level_limit)
                if cost is not None and mp + cost <= budget:
                    a, r = terrain_rules.step_psrs(current_info, dest_info)
                    push(mp + cost, (x + dx, y + dy, facing, 1, used_back),
                         (hz - terrain_rules.step_hazard(dest_info), fc + 1 if last >= 0 else 1, neg - a - r,
                          always + a, run_only + r), key, mp, "forward")

            # 2. Backward move (walking only; a level change costs a PSR).
            if backward_mp is not None:
                dest_info = hex_info(x - dx, y - dy)
                if dest_info is not None:
                    cost = terrain_rules.step_cost(current_info, dest_info, level_limit, backward=True)
                    if cost is not None and mp + cost <= backward_mp:
                        a, r = terrain_rules.step_psrs(current_info, dest_info, backward=True)
                        push(mp + cost, (x - dx, y - dy, facing, -1, True),
                             (hz - terrain_rules.step_hazard(dest_info), fc + 1 if last <= 0 else 1, neg - a - r,
                              always + a, run_only + r), key, mp, "backward")

            # 3. / 4. Turning (mud: a PSR if running, p.124).
            if mp + 1 <= budget:
                a, r = terrain_rules.turn_psrs(current_info)
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
    if terrain_rules.has_psr_terrain(terrain_map) or keep_parents:
        return _build_terrain_psr(start_x, start_y, start_facing, mp_budget, terrain_map, backward_mp, level_limit,
                                  keep_parents, blocked)
    return _build_terrain_aware(start_x, start_y, start_facing, mp_budget, terrain_map, backward_mp, level_limit,
                                blocked)


def query_envelope(table: MovementTable) -> Set[State]:
    """Every (x, y, facing) reachable at all, at any mp_spent <= budget."""
    return set(table.keys())


def query_max_forward_count(table: MovementTable) -> Dict[State, int]:
    """
    For each reachable (x, y, facing), the highest forward-count achievable
    across all mp_spent values that reach it — the table that feeds TMM.
    """
    return {state: max(col.values()) for state, col in table.items()}
