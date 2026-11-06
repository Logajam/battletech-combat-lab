"""
tests/test_fastcore.py - the Rust module `fastcore` must give the Python's exact answers
(2026-11-03, trial of compiled hot loops).

    python tests/test_fastcore.py

Build it first (needs Rust and maturin):
    cd fastcore && maturin build --release && pip install --force-reinstall target/wheels/*.whl
Not installed: the checks say so and pass - the simulator then runs on pure Python.
"""

import os
import random
import sys
import traceback

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

import INTEGRATION__orchestrator  # noqa: E402,F401 - puts MECHSIM / PATHFINDER on the path
import INTEGRATION__weapon_selection as ws  # noqa: E402

try:
    import fastcore  # noqa: E402
    if not hasattr(fastcore, "best_subset"):             # the fastcore/ folder as an empty package = not built
        fastcore = None
except ImportError:
    fastcore = None


def same(a, b):
    return (a[0], a[1], set(a[2])) == (b[0], b[1], set(b[2]))


CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


@check
def the_rust_knapsack_matches_the_python_on_random_weapon_sets():
    """Ties on purpose (repeated values and heats, zero heat, zero value), budgets from
    negative to plenty: value, heat AND the chosen weapons must match."""
    rng = random.Random(2026)
    for _ in range(20000):
        n = rng.randint(0, 12)
        values = [rng.choice([0.0, 0.5, 1.25, 2.5, rng.random() * 10]) for _ in range(n)]
        heats = [rng.choice([0, 1, 2, 3, 3, 4, 8, rng.randint(0, 15)]) for _ in range(n)]
        budget = rng.randint(-2, 40)
        want = ws._best_subset_python(values, heats, budget)
        got = fastcore.best_subset(values, heats, budget)
        assert same(want, got), (values, heats, budget, want, got)


@check
def the_rust_knapsack_levels_match_the_python():
    """Every level, in order: heat, value and chosen weapons (FireTable reads them all)."""
    rng = random.Random(1103)
    for _ in range(20000):
        n = rng.randint(0, 12)
        values = [rng.choice([0.0, 0.5, 1.25, 2.5, rng.random() * 10]) for _ in range(n)]
        heats = [rng.choice([0, 1, 2, 3, 3, 4, 8, rng.randint(0, 15)]) for _ in range(n)]
        budget = rng.randint(0, 40)
        want = ws._knapsack_levels_python(values, heats, budget)
        got = fastcore.knapsack_levels(values, heats, budget)
        assert [(h, v, set(i)) for h, v, i in want] == [(h, v, set(i)) for h, v, i in got], (values, heats, budget)


@check
def what_rust_does_not_take_falls_back_to_python():
    values, heats = [1.0, 2.0], [1.5, 2]                    # a non-integer heat
    assert same(ws._best_subset_rust(values, heats, 3), ws._best_subset_python(values, heats, 3))
    values, heats = [1.0] * 70, [1] * 70                   # more than 64 candidates
    assert same(ws._best_subset_rust(values, heats, 5), ws._best_subset_python(values, heats, 5))


@check
def the_rust_movement_search_matches_the_python_on_real_boards():
    """fastcore.PathBoard (the movement table and the walking states) against the Python search: the
    same states in the same order and the same terrain PSR counts, on boards with PSR terrain and on
    a flat one, for several 'Mechs, start hexes, facings, blocked hexes and level limits (a destroyed hip).
    One quirk this random check did NOT find on its own: while a mech enters the board, _note_psrs runs as each
    state is yielded and the picker's reduction reads the count then, so a state reached again by a way with
    fewer PSRs is read with the FIRST count (the Rust returns both). The Large Lakes reference battle
    (tests/check_reference_logs.py) catches that one."""
    import io
    from contextlib import redirect_stdout
    import INTEGRATION__config as config
    import INTEGRATION__ranged_combat as rc
    import INTEGRATION__orchestrator as orchestrator
    import INTEGRATION__movement_selection as ms
    import hex_geometry
    import los
    from board_parser import parse_board_file
    from mech_state import clone_mech, ground_level_limited, is_superheavy
    from mtf_parser import parse_mtf
    import terrain_rules
    if not hasattr(rc, "_rust_board") or rc._fastcore is None:
        print("      (PathBoard not built: skipped)")
        return
    config.VERBOSE = False
    rng = random.Random(4242)
    templates = [parse_mtf(config.data_path(n)) for n in
                 ("Asymptote II iJ Mpulse.mtf", "Kontio.mtf", "Hammerhead.mtf", "Atlas AS7-K.mtf", "Locust LCT-1V.mtf")]
    compared = psr_boards = rust_used = 0
    for board_name in ("16x17_Desert_Hills.board", "16x17_Hilltops_1.board", "16x17_Large_Lakes_1.board",
                       "16x17_Scattered_Woods.board", "16x17_Military_Base_1.board", "16x17_Grassland_1.board"):
        terrain = parse_board_file(config.data_path(board_name))
        labels = sorted(terrain["hexes"])
        for _ in range(24):
            template = rng.choice(templates)
            start = rng.choice(labels)
            mover = clone_mech(template)
            with redirect_stdout(io.StringIO()):
                orchestrator._attach_mech_config(mover, {"hex": start, "facing": rng.choice("N NE SE S SW NW".split()),
                                                         "gunnery": 4, "piloting": 5, "min_heat": 0, "max_heat": 4}, "T")
            blocked = {hex_geometry.parse_hex_label(rng.choice(labels)) for _ in range(rng.randint(0, 6))}
            blocked.discard(hex_geometry.parse_hex_label(start))
            mover.blocked_hex = blocked or None
            if rng.random() < 0.3:
                mover.destroyed_hip_locations = ["Left Leg"]        # a destroyed hip: one level at a time (pp.46-47)
            backward = rng.random() < 0.8
            runs = {}
            for fast in (False, True):
                config.FASTCORE_MOVEMENT = fast
                mover.path_psrs, mover.path_hazard = {}, {}
                runs[fast] = (list(rc.movement_options(mover, terrain, backward=backward)), dict(mover.path_psrs),
                              dict(mover.path_hazard))
            # an edge: a column of hexes, or a cluster of neighbours (their searches overlap, so a state is reached
            # by several ways with different PSR counts - the case the first-count order matters in)
            near = rng.choice(labels)
            cluster = [lb for lb in labels if los.hex_distance(hex_geometry.parse_hex_label(lb),
                                                               hex_geometry.parse_hex_label(near)) <= 3]
            side = rng.random()
            edge = cluster if side < 0.4 else [lb for lb in labels if lb.startswith("01")] if side < 0.7 else \
                [lb for lb in labels if lb.startswith("16")]
            for fast in (False, True):                      # entering the board from an edge (turn 1)
                config.FASTCORE_MOVEMENT = fast
                mover.path_psrs, mover.path_hazard = {}, {}
                runs[("entry", fast)] = (list(rc.movement_options(mover, terrain, entry_edge=edge)),
                                         dict(mover.path_psrs))
            config.FASTCORE_MOVEMENT = True
            assert runs[("entry", False)] == runs[("entry", True)], (board_name, start, "entry states differ")
            # what the picker really reads: the reduced states. (_note_psrs runs as each state is yielded and the
            # reduction reads the count then - a state reached again with fewer PSRs reads the first count.)
            for entry in (None, edge):
                for fast in (False, True):
                    config.FASTCORE_MOVEMENT = fast
                    runs[("reduced", entry is None, fast)] = ms.reduced_options(mover, terrain, entry_edge=entry)
                assert runs[("reduced", entry is None, False)] == runs[("reduced", entry is None, True)], \
                    (board_name, start, entry, "reduced states differ")
            config.FASTCORE_MOVEMENT = True
            assert runs[False][0] == runs[True][0], (board_name, start, "states differ")
            # the Rust fills a count for every state (as _note_psrs); a board with no PSR terrain has none
            assert runs[False][1] == runs[True][1], (board_name, start, "terrain PSR counts differ")
            assert runs[False][2] == runs[True][2], (board_name, start, "hazards differ")
            compared += 1
            psr_boards += bool(runs[True][1])
            limit = terrain_rules.max_level_change(ground_level_limited(mover), is_superheavy(mover))
            rust_used += rc._rust_board(terrain, limit) is not None     # (a silent fall back would pass the rest)
    assert compared >= 120 and psr_boards >= 60 and rust_used == compared, (compared, psr_boards, rust_used)


@check
def the_rust_line_of_sight_matches_the_python_on_real_boards():
    """fastcore.LosBoard against the Python trace (los_cache.pair_info): the same LOSResult, entry direction,
    distance and arcs for random pairs on boards with woods, hills, water, buildings and fields, standing, prone
    and superheavy heights, with and without smoke - and the same ValueError for a line off the board."""
    import INTEGRATION__config as config
    import INTEGRATION__los_cache as geo_cache
    import hex_geometry
    import los
    from board_parser import parse_board_file
    if geo_cache._fastcore is None:
        print("      (LosBoard not built: skipped)")
        return
    rng = random.Random(77)
    heights = [2, 1, los.SUPERHEAVY_STANDING, los.SUPERHEAVY_PRONE]
    pairs = errors = blocked = modified = 0
    for board_name in ("16x17_Desert_Hills.board", "16x17_Hilltops_1.board", "16x17_Large_Lakes_1.board",
                       "16x17_Scattered_Woods.board", "16x17_Military_Base_1.board", "16x17_Grassland_1.board",
                       "16x17_Badlands_2_Hazardous_Liquid.board"):
        for smoky in (False, True):
            terrain = parse_board_file(config.data_path(board_name))
            labels = sorted(terrain["hexes"])
            if smoky:
                for label in rng.sample(labels, 25):
                    terrain["hexes"][label]["smoke"] = {"density": rng.choice("12"), "until": 9}
            coords = [hex_geometry.parse_hex_label(lb) for lb in labels]
            asked = []
            for _ in range(500):
                a, t = rng.choice(coords), rng.choice(coords)
                if rng.random() < 0.02:
                    t = (t[0] + 40, t[1])                              # off the board
                asked.append((a, t, rng.choice(heights), rng.choice(heights)))

            def answers(fast):
                config.FASTCORE_LOS = fast
                geo_cache.reset()
                geo_cache.invalidate_rust()
                out = []
                for a, t, ah, th in asked:
                    try:
                        out.append(geo_cache.pair_info(a, t, terrain, ah, th))
                    except ValueError:
                        out.append("off the board")
                return out
            python, rust = answers(False), answers(True)
            config.FASTCORE_LOS = True
            assert geo_cache._rust_los(terrain) is not None      # (a silent fall back would pass the rest)
            assert python == rust, [(q, p, r) for q, p, r in zip(asked, python, rust) if p != r][:3]
            pairs += len(asked)
            errors += python.count("off the board")
            blocked += sum(1 for r in python if r != "off the board" and not r[0].los)
            modified += sum(1 for r in python if r != "off the board" and r[0].modifier)
    assert pairs >= 6000 and errors >= 20 and blocked >= 300 and modified >= 300, (pairs, errors, blocked, modified)


def run_all():
    if fastcore is None:
        print("SKIP  fastcore is not built here (pure Python is used) - see this file's docstring")
        print("\nAll fastcore checks skipped.")
        return
    failed = 0
    for fn in CHECKS:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print()
    if failed:
        print(f"{failed} of {len(CHECKS)} fastcore checks FAILED.")
        sys.exit(1)
    print(f"All {len(CHECKS)} fastcore checks passed.")


if __name__ == "__main__":
    run_all()
