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

2026-10-24 (Claude): sets "short-list" (grid vs short-list look-ahead, for the
time a turn) and "short-vs-perfect" (Daniel's "Simple Short Grid" against
perfect knowledge, one per side), and a "ms a turn" column.

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

def _side(side, own, assumes):
    """Settings giving one side its own movement search and its assumption about
    the enemy's ("MECH_RED_CONFIG.search" sets that dict's key)."""
    cfg = f"MECH_{side.upper()}_CONFIG"
    return {f"{cfg}.search": own, f"{cfg}.assumes_enemy_search": assumes}


# (name, {config setting: value}) - the first is the baseline the others are compared with.
# A setting "DICT.key" sets one key of a config dict (per-side mech settings).
VARIANT_SETS = {
    "objective": [
        ("ratio", {"MOVEMENT_OBJECTIVE": "ratio", "MOVEMENT_LIFETIME_HISTORY_K": None}),
        ("lifetime + history K=3", {"MOVEMENT_OBJECTIVE": "lifetime", "MOVEMENT_LIFETIME_HISTORY_K": 3.0}),
    ],
    # Daniel's guess-and-follow search (2026-10-21): everyone "perfect" vs everyone "fast".
    "search": [
        ("all fast (default)", {}),
        ("all perfect", {"MOVEMENT_SEARCH": "exhaustive", "MOVEMENT_ASSUMED_ENEMY_SEARCH": "exhaustive"}),
    ],
    # "See how much of an advantage perfect knowledge is vs close enough" (Daniel, 2026-10-21).
    # Per side: how it picks its own spot / how it assumes the enemy picks (perfect = every
    # spot, fast = the grid search).
    "knowledge": [
        ("all fast (default)", {}),
        ("Red perfect, expects perfect", _side("Red", "exhaustive", "exhaustive")),
        ("Red perfect, expects fast", _side("Red", "exhaustive", "grid")),
        ("Blue perfect, expects perfect", _side("Blue", "exhaustive", "exhaustive")),
        ("Blue perfect, expects fast", _side("Blue", "exhaustive", "grid")),
        ("Red fast, expects perfect", _side("Red", "grid", "exhaustive")),
        ("Blue fast, expects perfect", _side("Blue", "grid", "exhaustive")),
    ],
    # The net's two mirror images (MOVEMENT_GRID_SPIN, Daniel 2026-10-21).
    "grid-spin": [
        ("spin clockwise", {"MOVEMENT_GRID_SPIN": "clockwise"}),
        ("spin counterclockwise", {"MOVEMENT_GRID_SPIN": "counterclockwise"}),
    ],
    # Daniel's "simple short list" reply model (2026-10-24): what it costs per turn against
    # the grid reply, both movers searching their own spots by grid.
    "short-list": [
        ("grid reply", {"MOVEMENT_SEARCH": "grid", "MOVEMENT_ASSUMED_ENEMY_SEARCH": "grid"}),
        ("short-list reply", {"MOVEMENT_SEARCH": "grid", "MOVEMENT_ASSUMED_ENEMY_SEARCH": "short_list"}),
    ],
    # "Simple Short Grid" (grid for its own spots, short-list look-ahead) against perfect
    # knowledge (every spot, every reply), one per side (Daniel, 2026-10-24: "make sure
    # win rates don't deviate too badly").
    "short-vs-perfect": [
        ("both perfect", {"MOVEMENT_SEARCH": "exhaustive", "MOVEMENT_ASSUMED_ENEMY_SEARCH": "exhaustive"}),
        ("Red short-grid, Blue perfect", {**_side("Red", "grid", "short_list"),
                                          **_side("Blue", "exhaustive", "exhaustive")}),
        ("Red perfect, Blue short-grid", {**_side("Red", "exhaustive", "exhaustive"),
                                          **_side("Blue", "grid", "short_list")}),
        ("both short-grid", {"MOVEMENT_SEARCH": "grid", "MOVEMENT_ASSUMED_ENEMY_SEARCH": "short_list"}),
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
    saved = {}
    for name in settings:
        top = name.split(".")[0]
        if top not in saved:
            value = getattr(config, top)
            saved[top] = dict(value) if isinstance(value, dict) else value
    for name, value in settings.items():
        if "." in name:
            top, key = name.split(".", 1)
            getattr(config, top)[key] = value
        else:
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
              f"identical battles {identical}/{battles} | {base_seconds / seconds:.1f}x the baseline's speed | "
              f"{1000 * seconds / max(1, turns):.0f} ms a turn (batch clock)")
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
