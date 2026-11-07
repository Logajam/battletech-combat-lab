"""
tests/test_stack.py - checks stacked coverage (2026-11-07, INTEGRATION__stack; Daniel: stack the damage maps on a target's
movement profile up to what kills it).

    python tests/test_stack.py
"""
import io
import os
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402
config.STATS = False
from test_multi_unit import fresh, TERRAIN, ATLAS, COMMANDO  # noqa: E402  (sets up the pathfinder path)
import INTEGRATION__peril as peril  # noqa: E402
import INTEGRATION__stack as stack  # noqa: E402
import hex_geometry  # noqa: E402
from test_heat import ScriptedDice  # noqa: E402

config.VERBOSE = False
CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


def setup():
    peril.reset()
    mover = fresh(ATLAS, "0808", "N", "A 1", "A")
    friend = fresh(ATLAS, "0608", "N", "A 2", "A")
    enemy = fresh(COMMANDO, "0812", "S", "B 1", "B")
    return mover, friend, enemy


@check
def a_spot_that_brings_guns_to_bear_adds_coverage_and_one_far_away_adds_little():
    mover, friend, enemy = setup()
    s = stack.Stack(mover, [enemy], [friend], TERRAIN)
    near = s.gain(hex_geometry.parse_hex_label("0810"))
    far = s.gain(hex_geometry.parse_hex_label("0101"))
    assert near > 0 and far < near / 5, (near, far)       # (the fast target's footprint can still reach near the far hex)


@check
def coverage_stops_growing_at_the_targets_toughness():
    mover, friend, enemy = setup()
    for loc in enemy.locations.values():                 # a target already nearly dead: tiny cap
        loc["armor"], loc["rear_armor"], loc["structure"] = 0, 0, 0
    first = next(iter(enemy.locations.values()))
    first["structure"] = 1
    s = stack.Stack(mover, [enemy], [friend], TERRAIN)
    cap = stack.movement_selection.effective_hp(enemy)
    assert s.gain(hex_geometry.parse_hex_label("0810")) <= cap + 1e-9          # no more than the whole target


@check
def the_weight_scales_the_gain():
    mover, friend, enemy = setup()
    h = hex_geometry.parse_hex_label("0810")
    g1 = stack.Stack(mover, [enemy], [friend], TERRAIN).gain(h)
    config.STACK_WEIGHT = 3.0
    try:
        g3 = stack.Stack(mover, [enemy], [friend], TERRAIN).gain(h)
    finally:
        config.STACK_WEIGHT = 1.0
    assert abs(g3 - 3 * g1) < 1e-9 and g1 > 0


def run_all():
    failed = 0
    for fn in CHECKS:
        try:
            with ScriptedDice([], default=7), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                fn()
            print(f"PASS  {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print()
    if failed:
        print(f"{failed} of {len(CHECKS)} stack checks FAILED.")
        sys.exit(1)
    print(f"All {len(CHECKS)} stack checks passed.")


if __name__ == "__main__":
    run_all()
