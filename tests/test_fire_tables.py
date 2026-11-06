"""
tests/test_fire_tables.py - the weapon choice's lookup tables (2026-11-03, Daniel: "For that
target, what is the base TN, and what is the range. After that it should just be a look up
table ... only refreshed if the mech takes battle damage that changes its options").

    python tests/test_fire_tables.py

weapon_selection.FireTable answers every movement heat from one knapsack, and scorers that
ask the same question about the same units share one table (weapon_selection.fire_state is
the key). Here real team battles run with config.FIRE_TABLE_VERIFY: every answer a table
gives is recomputed from scratch and must match, and the tables are kept from turn to turn
(normally emptied each turn), so damage, heat and ammo use between turns test the key - a
key that misses something fails here (tried: leaving out the target's state does).
Plus the rule the tables rest on: a knapsack solved at a large budget, filtered to a smaller
one, is the knapsack solved at the smaller one (same value, heat, weapons, tie-break).
"""

import io
import os
import random
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402
config.STATS = False  # event log + report off: not part of a test or battery (2026-11-06)
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
import INTEGRATION__weapon_selection as ws  # noqa: E402

config.VERBOSE = False
config.TIMING = False
with redirect_stdout(io.StringIO()):
    TERRAIN = orchestrator._load_map()

CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


@check
def one_large_knapsack_filtered_is_the_small_knapsack():
    rng = random.Random(7)
    for _ in range(20000):
        n = rng.randint(0, 10)
        values = [rng.choice([0.0, 1.0, 1.0, 2.5, rng.random() * 10]) for _ in range(n)]
        heats = [rng.choice([0, 1, 3, 3, 4, rng.randint(0, 12)]) for _ in range(n)]
        small = rng.randint(0, 25)
        levels = ws._knapsack_levels_python(values, heats, small + rng.randint(0, 20))
        v, h, ids = ws.best_within(levels, small)
        want = ws._best_subset_python(values, heats, small)
        assert (v, h, set(ids)) == (want[0], want[1], set(want[2])), (values, heats, small)


def battle(entries, seed, turns, **settings):
    names = ["FORCES", "DEPLOYMENT_DEPTH", "WORKERS", "REPLAY_BATTLES", "FIRE_TABLE_VERIFY"] + list(settings)
    saved = {n: getattr(config, n) for n in names}
    config.FORCES, config.DEPLOYMENT_DEPTH, config.WORKERS, config.REPLAY_BATTLES = entries, 0, 1, 0
    config.FIRE_TABLE_VERIFY = True
    for n, v in settings.items():
        setattr(config, n, v)
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            roster = config.load_roster()
            return orchestrator._run_one_roster(1, 1, seed, turns, roster, TERRAIN)
    finally:
        for n, v in saved.items():
            setattr(config, n, v)
        config.set_active_rng(None)


@check
def gladiator_teams_with_narc_ams_and_ecm_get_the_fresh_answer_every_time():
    """Kintaro KTO-19 (Narc, Artemis), Atlas AS7-K (AMS), Atlas AS7-S2 (Guardian ECM), Archer."""
    result = battle([{"team": "Red", "mtf": "Kintaro KTO-19.mtf", "count": 1},
                     {"team": "Red", "mtf": "Archer ARC-2R.mtf", "count": 1},
                     {"team": "Blue", "mtf": "Atlas AS7-K.mtf", "count": 1},
                     {"team": "Blue", "mtf": "Atlas AS7-S2.mtf", "count": 1}], seed=4, turns=6)
    assert result.turns_taken >= 3


@check
def heat_gear_and_structure_weighting_get_the_fresh_answer_too():
    """Rapid-fire / LB-X / Rotary (Cataphract, Emperor), MML / ATM (Akuma, Highlander), and the
    structure weighting on (its value scale is part of a table's key)."""
    result = battle([{"team": "Red", "mtf": "Cataphract CTF-3D.mtf", "count": 1},
                     {"team": "Red", "mtf": "Akuma AKU-2XK.mtf", "count": 1},
                     {"team": "Blue", "mtf": "Emperor EMP-6D.mtf", "count": 1},
                     {"team": "Blue", "mtf": "Highlander IIC 2.mtf", "count": 1}], seed=1, turns=5,
                    MOVEMENT_STRUCTURE_WEIGHT=1.5)
    assert result.turns_taken >= 2


def run_all():
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
        print(f"{failed} of {len(CHECKS)} fire table checks FAILED.")
        sys.exit(1)
    print(f"All {len(CHECKS)} fire table checks passed.")


if __name__ == "__main__":
    run_all()
