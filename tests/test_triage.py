"""
tests/test_triage.py - checks the peril / toughness tiers (2026-11-07, INTEGRATION__triage; Daniel's top-10% idea).

    python tests/test_triage.py
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

from test_multi_unit import fresh, TERRAIN, ATLAS, COMMANDO  # noqa: E402  (sets up the pathfinder path)
import INTEGRATION__config as config  # noqa: E402
config.STATS = False
import INTEGRATION__peril as peril  # noqa: E402
import INTEGRATION__triage as triage  # noqa: E402
from test_heat import ScriptedDice  # noqa: E402

config.VERBOSE = False
CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


def team_and_enemy():
    peril.reset()
    near = fresh(COMMANDO, "0809", "N", "A 1", "A")        # right beside the enemy: the most peril, the least armor
    mid = fresh(ATLAS, "0806", "N", "A 2", "A")
    far = fresh(ATLAS, "0201", "N", "A 3", "A")             # far corner
    enemy = fresh(ATLAS, "0811", "S", "B 1", "B")
    return near, mid, far, enemy, [near, mid, far, enemy]


@check
def the_unit_in_most_peril_for_its_toughness_is_hot_and_the_safest_is_cool():
    near, mid, far, enemy, units = team_and_enemy()
    assert triage.tier_of(near, units, TERRAIN) == triage.HOT
    assert triage.tier_of(far, units, TERRAIN) == triage.COOL
    assert triage.tier_of(mid, units, TERRAIN) == triage.MID


@check
def fewer_than_three_units_or_off_the_board_is_mid():
    near, mid, far, enemy, units = team_and_enemy()
    assert triage.tier_of(near, [near, mid, enemy], TERRAIN) == triage.MID
    near.hex = None
    assert triage.tier_of(near, units, TERRAIN) == triage.MID


@check
def the_mirror_map_is_the_team_field_turned_round():
    near, mid, far, enemy, units = team_and_enemy()
    f = triage.reach_on([near, mid], enemy, TERRAIN)
    assert f.peak.max() > 0 and (f.peak >= peril.unit_field(near, enemy, TERRAIN).peak - 1e-9).all()


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
        print(f"{failed} of {len(CHECKS)} triage checks FAILED.")
        sys.exit(1)
    print(f"All {len(CHECKS)} triage checks passed.")


if __name__ == "__main__":
    run_all()
