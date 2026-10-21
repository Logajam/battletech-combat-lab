"""
tests/ab_batches.py - A/B batches: the same matchup and the same seeds under
several bot settings, side by side (added 2026-10-21, Claude; used to compare
the "ratio" and "lifetime" movement objectives and the history blend).

    python tests/ab_batches.py                          # the VARIANTS below, 100 battles
    python tests/ab_batches.py 40 "Atlas AS7-K.mtf" "Archer ARC-2R.mtf"

Each variant is a name and the config settings it changes. Every variant runs
the same battle seeds (config.SEED = 12345, battle n gets its own seed), so a
difference comes from the settings, not the dice. Prints, per variant: wins,
average turns, hits per turn, off-board deaths, battles that hit the turn cap,
and how many seeds kept the first variant's winner. Raw rows go to
run_stats/ab/ (git-ignored) as JSON. Battles run in parallel (config.WORKERS).
"""

import io
import json
import os
import sys
import time
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)
os.environ.setdefault("INTEGRATION_DATA_DIR", "./data")

import INTEGRATION__config as config  # noqa: E402
import INTEGRATION__orchestrator as orchestrator  # noqa: E402

# (name, {config setting: value}) - the first is the baseline the others are compared with.
VARIANTS = [
    ("ratio", {"MOVEMENT_OBJECTIVE": "ratio", "MOVEMENT_LIFETIME_HISTORY_K": None}),
    ("lifetime + history K=3", {"MOVEMENT_OBJECTIVE": "lifetime", "MOVEMENT_LIFETIME_HISTORY_K": 3.0}),
]


def run_variant(red, blue, battles, settings):
    saved = {name: getattr(config, name) for name in settings}
    for name, value in settings.items():
        setattr(config, name, value)
    config.MECH_RED_MTF, config.MECH_BLUE_MTF = red, blue
    config.VERBOSE, config.SEED, config.TIMING = False, 12345, False
    start = time.time()
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            results = orchestrator.run_batch(num_simulations=battles)
    finally:
        for name, value in saved.items():
            setattr(config, name, value)
    return results, time.time() - start


def main():
    args = sys.argv[1:]
    battles = int(args[0]) if args else 100
    red, blue = (args[1], args[2]) if len(args) >= 3 else (config.MECH_RED_MTF, config.MECH_BLUE_MTF)
    out_dir = os.path.join(REPO_ROOT, "run_stats", "ab")
    os.makedirs(out_dir, exist_ok=True)
    print(f"{red} vs {blue}, {battles} battles per variant, same seeds")
    baseline = None
    for name, settings in VARIANTS:
        results, seconds = run_variant(red, blue, battles, settings)
        turns = sum(r.turns_taken for r in results)
        wins = Counter(r.winner for r in results)
        off = sum(1 for r in results for s in (r.red, r.blue)
                  if s.destroyed and "battlefield" in (s.cause_of_death or ""))
        capped = sum(1 for r in results if r.destroyed is None and r.turns_taken >= (r.turn_cap or 0))
        winners = {r.seed: r.winner for r in results}
        same = sum(baseline.get(seed) == w for seed, w in winners.items()) if baseline else battles
        baseline = baseline or winners
        print(f"  {name:28s} Red {wins['Red']:3d}  Blue {wins['Blue']:3d}  Draw {wins['Draw']:2d} | "
              f"turns {turns / battles:5.1f} | hits/turn R {sum(r.red.hits for r in results) / turns:.2f} "
              f"B {sum(r.blue.hits for r in results) / turns:.2f} | off-board deaths {off:2d} | "
              f"turn cap {capped:2d} | same winner {same}/{battles} | {seconds:.0f} s")
        rows = [{"seed": str(r.seed), "turns": r.turns_taken, "winner": r.winner,
                 "red_cause": r.red.cause_of_death, "blue_cause": r.blue.cause_of_death} for r in results]
        tag = f"{red}_vs_{blue}_{name}".replace(" ", "_").replace(".mtf", "")
        with open(os.path.join(out_dir, tag + ".json"), "w") as f:
            json.dump({"settings": settings, "seconds": seconds, "rows": rows}, f)


if __name__ == "__main__":
    main()
