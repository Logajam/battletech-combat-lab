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

2026-10-21 (Claude): variant SETS and more columns, for Daniel's "guess and
follow" two-ply search ("Lets see how much the results differ from the
baseline"):

    python tests/ab_batches.py 100 "Atlas AS7-K.mtf" "Archer ARC-2R.mtf" --set search --turns 50
    python tests/ab_batches.py 60 "Black Hawk (Nova) F.mtf" "Cataphract CTF-3D.mtf" --set search \
        --board 16x17_Military_Base_1.board

--set picks a VARIANT_SETS entry (default "objective", the original two;
"baseline" runs the default settings alone - with --seed, a noise yardstick);
--seed sets the batch seed (default 12345);
--turns caps each battle (config.MAX_TURNS); --board sets the map. Extra
columns: average damage dealt and HP left per side, seconds and speed-up
against the first variant, and how many battles came out exactly the same
(winner, turns and both sides' HP).
"""

import argparse
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
VARIANT_SETS = {
    "objective": [
        ("ratio", {"MOVEMENT_OBJECTIVE": "ratio", "MOVEMENT_LIFETIME_HISTORY_K": None}),
        ("lifetime + history K=3", {"MOVEMENT_OBJECTIVE": "lifetime", "MOVEMENT_LIFETIME_HISTORY_K": 3.0}),
    ],
    # Daniel's guess-and-follow two-ply search (config.MOVEMENT_TWO_PLY_SEARCH, 2026-10-21).
    "search": [
        ("exhaustive (baseline)", {"MOVEMENT_TWO_PLY_SEARCH": "exhaustive"}),
        ("grid 1/7 + follow", {"MOVEMENT_TWO_PLY_SEARCH": "grid", "MOVEMENT_SEARCH_STARTS": 1}),
        ("grid 1/7 + follow best 3", {"MOVEMENT_TWO_PLY_SEARCH": "grid", "MOVEMENT_SEARCH_STARTS": 3}),
    ],
    # Both movers pick by guess and follow (MOVEMENT_REPLY_SEARCH, Daniel 2026-10-21).
    "search-both": [
        ("grid both movers", {"MOVEMENT_TWO_PLY_SEARCH": "grid", "MOVEMENT_REPLY_SEARCH": "grid"}),
    ],
    # With the always-checks (own hex, the 6 around the enemy - Daniel, 2026-10-21; second mover only).
    "search-always-both": [
        ("always: grid both movers", {"MOVEMENT_TWO_PLY_SEARCH": "grid", "MOVEMENT_REPLY_SEARCH": "grid"}),
    ],
    # The net's two mirror images (MOVEMENT_GRID_SPIN, Daniel 2026-10-21), both movers on the grid.
    "grid-spin": [
        ("spin clockwise", {"MOVEMENT_TWO_PLY_SEARCH": "grid", "MOVEMENT_REPLY_SEARCH": "grid",
                            "MOVEMENT_GRID_SPIN": "clockwise"}),
        ("spin counterclockwise", {"MOVEMENT_TWO_PLY_SEARCH": "grid", "MOVEMENT_REPLY_SEARCH": "grid",
                                   "MOVEMENT_GRID_SPIN": "counterclockwise"}),
    ],
    "search-always": [
        ("always: grid first mover", {"MOVEMENT_TWO_PLY_SEARCH": "grid"}),
        ("always: grid both movers", {"MOVEMENT_TWO_PLY_SEARCH": "grid", "MOVEMENT_REPLY_SEARCH": "grid"}),
    ],
    # The default settings alone: with --seed, a yardstick for how much results move with the dice alone.
    "baseline": [("default settings", {})],
}
VARIANTS = VARIANT_SETS["objective"]


def run_variant(red, blue, battles, settings, turns=None, board=None, seed=12345):
    settings = dict(settings)
    if turns is not None:
        settings["MAX_TURNS"] = turns
    if board is not None:
        settings["DEFAULT_BOARD_PATH"] = board
    saved = {name: getattr(config, name) for name in settings}
    for name, value in settings.items():
        setattr(config, name, value)
    config.MECH_RED_MTF, config.MECH_BLUE_MTF = red, blue
    config.VERBOSE, config.SEED, config.TIMING = False, seed, False
    start = time.time()
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            results = orchestrator.run_batch(num_simulations=battles)
    finally:
        for name, value in saved.items():
            setattr(config, name, value)
    return results, time.time() - start


def _outcome(r):
    """What 'the same battle' means: winner, length and both sides' HP left."""
    return r.winner, r.turns_taken, round(r.red.final_hp, 3), round(r.blue.final_hp, 3)


def main():
    parser = argparse.ArgumentParser(description="A/B batches on the same seeds.")
    parser.add_argument("battles", nargs="?", type=int, default=100)
    parser.add_argument("red", nargs="?", default=None)
    parser.add_argument("blue", nargs="?", default=None)
    parser.add_argument("--set", default="objective", choices=sorted(VARIANT_SETS))
    parser.add_argument("--turns", type=int, default=None, help="turn cap per battle (config.MAX_TURNS)")
    parser.add_argument("--board", default=None, help="board file (config.DEFAULT_BOARD_PATH)")
    parser.add_argument("--seed", type=int, default=12345, help="the batch seed (config.SEED)")
    a = parser.parse_args()
    battles = a.battles
    red, blue = (a.red, a.blue) if a.blue else (config.MECH_RED_MTF, config.MECH_BLUE_MTF)
    out_dir = os.path.join(REPO_ROOT, "run_stats", "ab")
    os.makedirs(out_dir, exist_ok=True)
    print(f"{red} vs {blue}, {battles} battles per variant, same seeds"
          f"{f', {a.turns}-turn cap' if a.turns else ''}{f', board {a.board}' if a.board else ''}"
          f"{f', seed {a.seed}' if a.seed != 12345 else ''}")
    baseline = base_outcomes = base_seconds = None
    for name, settings in VARIANT_SETS[a.set]:
        results, seconds = run_variant(red, blue, battles, settings, a.turns, a.board, a.seed)
        turns = sum(r.turns_taken for r in results)
        wins = Counter(r.winner for r in results)
        off = sum(1 for r in results for s in (r.red, r.blue)
                  if s.destroyed and "battlefield" in (s.cause_of_death or ""))
        capped = sum(1 for r in results if r.destroyed is None and r.turns_taken >= (r.turn_cap or 0))
        winners = {r.seed: r.winner for r in results}
        outcomes = {r.seed: _outcome(r) for r in results}
        same = sum(baseline.get(seed) == w for seed, w in winners.items()) if baseline else battles
        identical = sum(base_outcomes.get(seed) == o for seed, o in outcomes.items()) if base_outcomes else battles
        baseline = baseline or winners
        base_outcomes = base_outcomes or outcomes
        base_seconds = base_seconds or seconds
        n = len(results)
        print(f"  {name:28s} Red {wins['Red']:3d}  Blue {wins['Blue']:3d}  Draw {wins['Draw']:2d} | "
              f"turns {turns / battles:5.1f} | hits/turn R {sum(r.red.hits for r in results) / turns:.2f} "
              f"B {sum(r.blue.hits for r in results) / turns:.2f} | off-board deaths {off:2d} | "
              f"turn cap {capped:2d} | same winner {same}/{battles} | {seconds:.0f} s")
        print(f"  {'':28s} damage dealt R {sum(r.red.damage_dealt for r in results) / n:5.1f} "
              f"B {sum(r.blue.damage_dealt for r in results) / n:5.1f} | HP left R "
              f"{sum(r.red.final_hp for r in results) / n:5.1f} B {sum(r.blue.final_hp for r in results) / n:5.1f} | "
              f"identical battles {identical}/{battles} | {base_seconds / seconds:.1f}x the baseline's speed")
        rows = [{"seed": str(r.seed), "turns": r.turns_taken, "winner": r.winner,
                 "red_cause": r.red.cause_of_death, "blue_cause": r.blue.cause_of_death,
                 "red_hp": r.red.final_hp, "blue_hp": r.blue.final_hp,
                 "red_dealt": r.red.damage_dealt, "blue_dealt": r.blue.damage_dealt} for r in results]
        tag = f"{red}_vs_{blue}_{name}{'_' + a.board if a.board else ''}{f'_seed{a.seed}' if a.seed != 12345 else ''}"
        tag = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in tag.replace(".mtf", ""))
        with open(os.path.join(out_dir, tag + ".json"), "w") as f:
            json.dump({"settings": settings, "seconds": seconds, "rows": rows}, f)


if __name__ == "__main__":
    main()
