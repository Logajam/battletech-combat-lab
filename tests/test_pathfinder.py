"""
tests/test_pathfinder.py - correctness suite for the movement/map modules
the battle loop uses: pathfinder/hex_geometry.py, pathfinder.py,
board_parser.py, terrain_rules.py.

Rebuilt 2026-10-19 (Claude) from PATHFINDER__validation.py for the repo
layout. Run from the repo root:

    python tests/test_pathfinder.py

Changes from the original (test logic and expected values are unchanged):
  - Imports point at pathfinder/ and the board at data/ (repo layout).
  - Old test 5 (simulate_move vs DP cross-check) REMOVED: it needed
    simulate.py, which no longer exists, and its import at the top of the
    file stopped every other test from running. Rebuilding it would mean
    writing a new move tracer, which would be new movement logic, not a test.
  - run_all() runs every test even if one fails, then reports a summary
    and exits non-zero on any failure (was: stopped at the first failure).

Covers:
  Phase 1 (flat-terrain geometry + DP):
    1. Straight-line movement
    2. 6-MP turning tax / 1:1 padding-loop conversion (emergent DP property)
    3. Facing-correction cost
    4. Hex-label round-trip
    4b. Locked-in ground-truth calibration facts (0101 NW corner, SE->0201)
  Phase 2 (board parsing + terrain-aware DP):
    6. board_parser correctness against 16x17_Grassland_1.board
    7. terrain_rules.transition_cost basic values (clear/rough/woods/water/elevation/road)
    8. Bucket-queue DP vs flat DP cross-check (interior states, all-clear map)
"""

import os
import sys
import traceback

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "pathfinder"))

from hex_geometry import FACING_DELTAS, compass_to_facing, hex_label, parse_hex_label  # noqa: E402
from pathfinder import build_movement_table, query_max_forward_count  # noqa: E402
import board_parser  # noqa: E402
import terrain_rules  # noqa: E402

BOARD_FILE = os.path.join(REPO_ROOT, "data", "16x17_Grassland_1.board")


def test_1_straight_line():
    table = build_movement_table(0, 0, 0, mp_budget=5)
    max_fc = query_max_forward_count(table)
    for n in range(6):
        state = (0, 2 * n, 0)
        assert state in max_fc, f"Test 1 FAILED: {state} not reachable"
        assert max_fc[state] == n, f"Test 1 FAILED: {state} expected forward_count {n}, got {max_fc[state]}"
    print("Test 1 (straight line, MP 5): PASS")


def test_2_turning_tax():
    table = build_movement_table(0, 0, 0, mp_budget=18)
    max_fc = query_max_forward_count(table)
    start_state = (0, 0, 0)
    assert max_fc[start_state] == 12, (
        f"Test 2 FAILED: expected forward_count 12 at start state with MP 18, got {max_fc[start_state]}"
    )
    table12 = build_movement_table(0, 0, 0, mp_budget=12)
    max_fc12 = query_max_forward_count(table12)
    assert max_fc12[start_state] == 6, (
        f"Test 2 FAILED: expected forward_count 6 at start state with MP 12, got {max_fc12[start_state]}"
    )
    print("Test 2 (6-MP turning tax, 1:1 padding conversion): PASS")


def test_3_facing_correction():
    target = (0, 6, 0)

    table_aligned = build_movement_table(0, 0, 0, mp_budget=5)
    fc_aligned = query_max_forward_count(table_aligned)
    assert fc_aligned.get(target) == 3, f"Test 3 FAILED: aligned start expected fc 3, got {fc_aligned.get(target)}"

    table_opposed_short = build_movement_table(0, 0, 3, mp_budget=5)
    fc_opposed_short = query_max_forward_count(table_opposed_short)
    assert target not in fc_opposed_short, "Test 3 FAILED: opposed start with budget 5 should NOT reach target"

    table_opposed_full = build_movement_table(0, 0, 3, mp_budget=6)
    fc_opposed_full = query_max_forward_count(table_opposed_full)
    assert fc_opposed_full.get(target) == 3, (
        f"Test 3 FAILED: opposed start with budget 6 expected fc 3, got {fc_opposed_full.get(target)}"
    )
    print("Test 3 (facing-correction cost): PASS")


def test_4_hex_label_roundtrip():
    from hex_geometry import _row_parity_offset
    for x in range(0, 10):
        offset = _row_parity_offset(x)
        for row_idx in range(0, 8):
            y = offset - row_idx * 2
            label = hex_label(x, y)
            assert parse_hex_label(label) == (x, y), f"Test 4 FAILED: round trip mismatch for ({x},{y})"
    print("Test 4 (hex-label round trip): PASS")


def test_4b_ground_truth():
    x0, y0 = parse_hex_label("0101")
    dx, dy = FACING_DELTAS[compass_to_facing("SE")]
    se_x, se_y = x0 + dx, y0 + dy
    assert hex_label(se_x, se_y) == "0201", f"Test 4b FAILED: SE from 0101 gave {hex_label(se_x, se_y)}, expected 0201"
    print("Test 4b (0101 -> SE -> 0201 ground truth): PASS")


def test_6_board_parser():
    board = board_parser.parse_board_file(BOARD_FILE)
    assert board["width"] == 16 and board["height"] == 17, (
        f"Test 6 FAILED: expected 16x17, got {board['width']}x{board['height']}"
    )
    assert len(board["hexes"]) == 16 * 17, f"Test 6 FAILED: expected {16*17} hexes, got {len(board['hexes'])}"

    # Spot-check a light-woods hex and a heavy-woods hex from the sample file.
    assert board["hexes"]["0303"]["features"].get("woods") == ["1"], "Test 6 FAILED: 0303 expected woods:1"
    assert board["hexes"]["0503"]["features"].get("woods") == ["2"], "Test 6 FAILED: 0503 expected woods:2"
    # Spot-check a plain grass hex.
    assert board["hexes"]["0101"]["features"] == {}, "Test 6 FAILED: 0101 expected no features"
    assert board["hexes"]["0101"]["level"] == 0
    print("Test 6 (board_parser against 16x17_Grassland_1.board): PASS")


def test_7_transition_cost():
    # Clear, no elevation change: base 1, +0 terrain, +0 elevation = 1
    assert terrain_rules.transition_cost(0, 0, {}) == 1
    # Rough: 1 + 1 = 2
    assert terrain_rules.transition_cost(0, 0, {"rough": []}) == 2
    # Light woods: 1 + 1 = 2
    assert terrain_rules.transition_cost(0, 0, {"woods": ["1"]}) == 2
    # Heavy woods: 1 + 2 = 3
    assert terrain_rules.transition_cost(0, 0, {"woods": ["2"]}) == 3
    # Water depth 1: 1 + 1 = 2
    assert terrain_rules.transition_cost(0, 0, {"water": ["1"]}) == 2
    # Water depth 3: 1 + 2 = 3
    assert terrain_rules.transition_cost(0, 0, {"water": ["3"]}) == 3
    # Elevation change of 2, otherwise clear: 1 + 0 + 2 = 3
    assert terrain_rules.transition_cost(0, 2, {}) == 3
    # A road hex entered from off the road costs its underlying terrain (p.53,
    # 2026-10-21 - was: the road always cancelled it): 1 + 2 + 1 = 4. Road
    # travel (road to road) is terrain_rules.step_cost's - tests/test_terrain.py.
    assert terrain_rules.transition_cost(0, 1, {"woods": ["2"], "road": []}) == 4
    # Unresolved bridge feature -> ValueError, not a guessed number.
    try:
        terrain_rules.transition_cost(0, 0, {"bridge": ["0"]})
        raise AssertionError("Test 7 FAILED: bridge feature should have raised ValueError")
    except ValueError:
        pass
    print("Test 7 (transition_cost basic values): PASS")


def test_8_bucket_queue_vs_flat():
    # Build a synthetic all-clear terrain_map covering the interior of the
    # 16x17 board, then confirm the bucket-queue DP matches the flat DP's
    # forward-counts for states well away from the board edge (where
    # bounding wouldn't kick in either way).
    board = board_parser.parse_board_file(BOARD_FILE)
    all_clear_hexes = {label: {"level": 0, "features": {}, "impassable": False} for label in board["hexes"]}
    all_clear_map = {"width": board["width"], "height": board["height"], "hexes": all_clear_hexes}

    start_label, start_compass = "0808", "N"
    x0, y0 = parse_hex_label(start_label)
    facing0 = compass_to_facing(start_compass)
    mp_budget = 6  # small enough to stay well inside the board from hex 0808

    flat_table = build_movement_table(x0, y0, facing0, mp_budget)
    terrain_table = build_movement_table(x0, y0, facing0, mp_budget, terrain_map=all_clear_map)

    flat_fc = query_max_forward_count(flat_table)
    terrain_fc = query_max_forward_count(terrain_table)

    mismatches = []
    for state, fc in flat_fc.items():
        if state in terrain_fc and terrain_fc[state] != fc:
            mismatches.append((state, fc, terrain_fc[state]))
    assert not mismatches, f"Test 8 FAILED: bucket-queue/flat DP mismatches: {mismatches[:5]}"
    print("Test 8 (bucket-queue DP matches flat DP on all-clear terrain): PASS")


def test_9_backward_movement():
    # 2026-10-20, Core Rulebook pp.45-46, 63: walking mechs may move backward
    # (hex directly behind, facing kept); never past Walking MP once they have;
    # the hex count restarts when the mech reverses; same-level hexes only
    # (backward level changes need a PSR - not offered yet).
    board = board_parser.parse_board_file(BOARD_FILE)
    hexes = {label: {"level": 0, "features": {}, "impassable": False} for label in board["hexes"]}
    clear = {"width": board["width"], "height": board["height"], "hexes": hexes}
    x0, y0 = parse_hex_label("0808")
    north = compass_to_facing("N")
    behind = lambda n: (x0, y0 - 2 * n, north)          # noqa: E731 - n hexes straight back, still facing N

    forward_only = build_movement_table(x0, y0, north, 3, terrain_map=clear)
    assert behind(1) not in forward_only, "Test 9 FAILED: backward move offered without backward_mp"

    table = build_movement_table(x0, y0, north, 3, terrain_map=clear, backward_mp=2)
    assert table[behind(1)] == {1: 1} and table[behind(2)] == {2: 2}, table.get(behind(2))
    # Walking MP 2, Running MP 3: three hexes back would be a backward run - not allowed.
    assert behind(3) not in table, "Test 9 FAILED: moved backward past Walking MP"
    assert behind(3) in build_movement_table(x0, y0, north, 3, terrain_map=clear, backward_mp=3)
    # One hex forward, then back again (2 MP, facing N, back in the start hex): the
    # reversal restarts the count, so 1 hex - not 2.
    assert table[(x0, y0, north)][2] == 1, table[(x0, y0, north)]

    # A level-1 hex behind: no backward step into it.
    hexes[hex_label(*behind(1)[:2])] = {"level": 1, "features": {}, "impassable": False}
    table = build_movement_table(x0, y0, north, 3, terrain_map=clear, backward_mp=3)
    assert behind(1) not in table or 1 not in table[behind(1)], "Test 9 FAILED: backward level change offered"
    print("Test 9 (backward movement): PASS")


def test_10_line_shapes():
    """los.hex_line shifts a line shape worked out once per offset (2026-10-21,
    speed only): it must equal the line worked out from scratch for every
    ordered pair of hexes on a 16x17 board."""
    import los
    hexes = [parse_hex_label(f"{c:02d}{r:02d}") for c in range(1, 17) for r in range(1, 18)]
    bad = [(a, b) for a in hexes for b in hexes if los.hex_line(a, b) != los._hex_line_direct(a, b)]
    assert not bad, f"{len(bad)} lines differ, e.g. {bad[0]}"
    print(f"test_10_line_shapes: {len(hexes) ** 2} hex pairs, shifted shape = direct line - PASS")


TESTS = [
    test_1_straight_line,
    test_2_turning_tax,
    test_3_facing_correction,
    test_4_hex_label_roundtrip,
    test_4b_ground_truth,
    test_6_board_parser,
    test_7_transition_cost,
    test_8_bucket_queue_vs_flat,
    test_9_backward_movement,
    test_10_line_shapes,
]


def run_all():
    failed = []
    for test in TESTS:
        try:
            test()
        except Exception:
            failed.append(test.__name__)
            print(f"{test.__name__}: FAILED")
            traceback.print_exc()
    print()
    if failed:
        print(f"{len(failed)} of {len(TESTS)} checks FAILED: {', '.join(failed)}")
        return 1
    print(f"All {len(TESTS)} validation checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
