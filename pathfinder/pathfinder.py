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
    from terrain_rules.transition_cost(); turning always costs 1 MP
    (facing changes have no terrain dependency). Board-edge bounding is
    enforced by simply not generating a transition into a hex that isn't
    in terrain_map — not by filtering afterward (per handoff Section 4e).

Load-bearing invariant (both modes): every transition cost must be >= 1.
Bucket-queue mode relies on this to guarantee each layer is processed
exactly once (a transition from a state finalized at layer mp always
lands at a layer > mp, never <= mp). terrain_rules.transition_cost()
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
) -> MovementTable:
    """Phase 2: bucket-queue (Dial's algorithm) sweep, board-edge bounded."""
    hexes = terrain_map["hexes"]

    def hex_info(x: int, y: int) -> Optional[dict]:
        try:
            label = hex_label(x, y)
        except ValueError:
            return None
        return hexes.get(label)

    table: MovementTable = {}
    start_state: State = (start_x, start_y, start_facing)
    start_info = hex_info(start_x, start_y)
    if start_info is None:
        raise ValueError(
            f"Start hex {hex_label(start_x, start_y)!r} is not on the loaded board — "
            f"can't build a movement table from an off-board start."
        )
    if start_info["impassable"]:
        raise ValueError(f"Start hex {hex_label(start_x, start_y)!r} is marked impassable.")

    _record(table, start_state, 0, 0)

    # buckets[mp] = {state: best forward_count seen so far at this mp}
    buckets: Dict[int, Dict[State, int]] = {0: {start_state: 0}}

    for mp in range(mp_budget + 1):
        bucket = buckets.get(mp)
        if not bucket:
            continue

        for (x, y, facing), fc in bucket.items():
            _record(table, (x, y, facing), mp, fc)

            current_info = hex_info(x, y)
            if current_info is None:
                continue  # shouldn't happen (we never generate off-board states), defensive only

            # 1. Forward move: cost from terrain_rules, into next hex.
            dx, dy = FACING_DELTAS[facing]
            dest_x, dest_y = x + dx, y + dy
            dest_info = hex_info(dest_x, dest_y)
            if dest_info is not None and not dest_info["impassable"]:
                cost = terrain_rules.transition_cost(
                    current_info["level"], dest_info["level"], dest_info["features"]
                )
                new_mp = mp + cost
                if new_mp <= mp_budget:
                    dest_state: State = (dest_x, dest_y, facing)
                    b = buckets.setdefault(new_mp, {})
                    if b.get(dest_state, -1) < fc + 1:
                        b[dest_state] = fc + 1

            # 2. / 3. Turning: always costs 1 MP, hex unchanged, forward_count unchanged.
            if mp + 1 <= mp_budget:
                for new_facing in ((facing - 1) % 6, (facing + 1) % 6):
                    turn_state: State = (x, y, new_facing)
                    b = buckets.setdefault(mp + 1, {})
                    if b.get(turn_state, -1) < fc:
                        b[turn_state] = fc

    return table


def build_movement_table(
    start_x: int,
    start_y: int,
    start_facing: int,
    mp_budget: int,
    terrain_map: Optional[Dict[str, object]] = None,
) -> MovementTable:
    if start_facing not in FACING_DELTAS:
        raise ValueError(f"start_facing must be 0-5, got {start_facing}")
    if mp_budget < 0:
        raise ValueError("mp_budget must be non-negative")

    if terrain_map is None:
        return _build_flat(start_x, start_y, start_facing, mp_budget)
    return _build_terrain_aware(start_x, start_y, start_facing, mp_budget, terrain_map)


def query_envelope(table: MovementTable) -> Set[State]:
    """Every (x, y, facing) reachable at all, at any mp_spent <= budget."""
    return set(table.keys())


def query_max_forward_count(table: MovementTable) -> Dict[State, int]:
    """
    For each reachable (x, y, facing), the highest forward-count achievable
    across all mp_spent values that reach it — the table that feeds TMM.
    """
    return {state: max(col.values()) for state, col in table.items()}
