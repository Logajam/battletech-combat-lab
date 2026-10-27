"""
tests/pick_quality.py - how good is each bot's movement pick, priced on Perfect
Knowledge's scale (added 2026-10-27, Claude, for Daniel: "Does the short list's
'Rules of thumb' hold up in wider and longer tests ... For each turn's board
state take a measurement of Perfect Knowledge's pick and score, Short-Grid's
... Short-Short-Grid ... Princess Classic ... Princess Modern ... what average
percentage of score is earned compared to perfect knowledge ... And How many
hexes away on average the pick is from what perfect knowledge says is best").

    python tests/pick_quality.py                       # every scenario, 20 battles each
    python tests/pick_quality.py 8 --scenarios 1 2     # 8 battles, the two kiting scenarios

The battles are Gladiator (the default, "Short Grid") against Gladiator, so the
board states are the ones the project's own bot reaches. At EVERY movement
decision of either 'Mech, before it moves, five pickers choose from the same
position (each on a copy of the dice; only the real pick is played - the
battle is the one a plain run gives):
  Perfect        - Gladiator, every spot, every reply spot in its look-ahead
                   (MOVEMENT_SEARCH = MOVEMENT_ASSUMED_ENEMY_SEARCH = "exhaustive").
                   Its run also prices EVERY reachable spot (and every charge /
                   DFA) with the objective (movement_selection.SCORE_SINK).
  Short Grid     - the default: grid search, short-list look-ahead.
  Short-Short    - Short-Short-Grid: both movers pick from their own short list
                   (best few states a hex), pruned by the grid search
                   (MOVEMENT_SEARCH = "short_list", MOVEMENT_SHORT_LIST_GRID = True).
  Princess 0.50.07, Princess modern - the two Princess clones.
Each pick is priced at Perfect's score for that spot. Reported per scenario
and side, and overall (by mover order too):
  % of best      the pick's score / the best score any spot has (the mean; a
                 pick worth 90 where the best is worth 100 scores 90%). The
                 "lifetime" objective is mostly HP left, which hardly changes
                 between spots, so this reads high for every picker -
  % of range     where the pick sits between the worst spot (0) and the best
                 (100): (pick - worst) / (best - worst) - the sharper measure
  got best       share of decisions where the pick IS the best-scoring spot
                 (within 0.1%)
  rank pct       share of all reachable spots the pick scores at least as
                 well as (100 = best; a random pick averages ~50)
  hexes off      hexes from the pick to Perfect's own pick
  same hex       share of picks on Perfect's hex
  closer         hexes closer to the enemy than Perfect's pick (negative =
                 farther) - Daniel's "close range when I don't have to" check;
                 kiting scenarios are marked
  ms             time per decision
Decisions where the best score is 0 or less are left out of "% of best".
Scenarios run one after another, each one's battles in parallel (--workers).
Raw rows: run_stats/pick_quality/.
"""

import argparse
import copy
import io
import json
import math
import multiprocessing
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from contextlib import redirect_stderr, redirect_stdout

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402 - registers bare "config" first
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
import INTEGRATION__bots as bots  # noqa: E402
import INTEGRATION__princess as princess_classic  # noqa: E402
import INTEGRATION__princess_modern as princess_modern  # noqa: E402
import INTEGRATION__movement_selection as movement_selection  # noqa: E402
import hex_geometry  # noqa: E402 - PATHFINDER
from los import hex_distance  # noqa: E402 - PATHFINDER

# (name, red .mtf, blue .mtf, board, kiting side or None)
SCENARIOS = [
    ("Kite: Dervish vs Hunchback, Grassland", "Dervish DV-6M.mtf", "Hunchback HBK-4G.mtf",
     "16x17_Grassland_1.board", "Red"),
    ("Kite: Griffin vs Hunchback, Scattered Woods", "Griffin GRF-1N.mtf", "Hunchback HBK-4G.mtf",
     "16x17_Scattered_Woods.board", "Red"),
    ("Catapult vs Jenner, Rolling Hills", "Catapult CPLT-C1.mtf", "Jenner JR7-D.mtf",
     "16x17_Grasslands_Rolling_Hills_1.board", "Red"),
    ("Kontio vs Hammerhead, Grassland", "Kontio.mtf", "Hammerhead.mtf", "16x17_Grassland_1.board", None),
    ("Atlas vs Archer, Hilltops", "Atlas AS7-K.mtf", "Archer ARC-2R.mtf", "16x17_Hilltops_1.board", None),
    ("Awesome vs Griffin, Military Base", "Awesome AWS-8Q.mtf", "Griffin GRF-1N.mtf",
     "16x17_Military_Base_1.board", "Blue"),
    ("Locust vs Commando, Desert Hills", "Locust LCT-1V.mtf", "Commando COM-2D.mtf", "16x17_Desert_Hills.board", None),
    ("Black Hawk vs Cataphract, Large Lakes", "Black Hawk (Nova) F.mtf", "Cataphract CTF-3D.mtf",
     "16x17_Large_Lakes_1.board", None),
]
PICKERS = ("Perfect", "Short Grid", "Short-Short", "Princess 0.50.07", "Princess modern")
GLADIATOR_SETTINGS = {
    "Perfect": {"MOVEMENT_SEARCH": "exhaustive", "MOVEMENT_ASSUMED_ENEMY_SEARCH": "exhaustive"},
    "Short Grid": {"MOVEMENT_SEARCH": "grid", "MOVEMENT_ASSUMED_ENEMY_SEARCH": "short_list"},
    "Short-Short": {"MOVEMENT_SEARCH": "short_list", "MOVEMENT_ASSUMED_ENEMY_SEARCH": "short_list",
                    "MOVEMENT_SHORT_LIST_GRID": True},
}


class _Settings:
    """config settings changed for a block (and the mech's own per-side ones cleared)."""

    def __init__(self, mover, settings):
        self.mover, self.settings = mover, settings

    def __enter__(self):
        self.saved = {k: getattr(config, k) for k in self.settings}
        self.saved_mech = (self.mover.move_search, self.mover.assumes_enemy_search)
        self.mover.move_search = self.mover.assumes_enemy_search = None
        for k, v in self.settings.items():
            setattr(config, k, v)

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            setattr(config, k, v)
        self.mover.move_search, self.mover.assumes_enemy_search = self.saved_mech


def _key(pick):
    if pick is None:
        return None
    attack = "charge" if pick.get("charge") else ("dfa" if pick.get("dfa") else "")
    return pick["hex"], pick["facing"], pick["mode"], pick["fc"], attack


_ROWS = []
_REAL_CHOOSE = bots.choose_movement


def _recording_choose(mover, other, terrain_map, battle_rng, moves_first, standup_mp=None, entry_edge=None):
    if other.hex is not None and entry_edge is None:
        picks, seconds = {}, {}
        sink = {}
        for name in PICKERS:
            rng = copy.deepcopy(battle_rng)
            started = time.perf_counter()
            if name in GLADIATOR_SETTINGS:
                with _Settings(mover, GLADIATOR_SETTINGS[name]):
                    if name == "Perfect":
                        movement_selection.SCORE_SINK = sink
                    try:
                        pick = movement_selection.choose(mover, other, terrain_map, rng, moves_first,
                                                         standup_mp=standup_mp)[0]
                    finally:
                        movement_selection.SCORE_SINK = None
            else:
                version = "modern" if name.endswith("modern") else "0.50.07"
                saved, config.PRINCESS_VERSION = config.PRINCESS_VERSION, version
                try:
                    module = princess_modern if version == "modern" else princess_classic
                    pick = module.choose(mover, other, terrain_map, rng, moves_first, standup_mp=standup_mp)[0]
                finally:
                    config.PRINCESS_VERSION = saved
            seconds[name] = time.perf_counter() - started
            picks[name] = _key(pick)
        spots = sink.get("spots", {})
        attacks = sink.get("attacks", {})

        def price(k):
            if k is None:
                return None
            return attacks.get(k) if k[4] else spots.get(k[:4])
        all_scores = sorted(list(spots.values()) + list(attacks.values()))
        best = all_scores[-1] if all_scores else None
        worst = all_scores[0] if all_scores else None
        enemy_xy = hex_geometry.parse_hex_label(other.hex)
        _ROWS.append({
            "side": mover.side_name, "moves_first": bool(moves_first), "turn": getattr(mover, "turn_number", 0),
            "stood_up": standup_mp is not None, "picks": picks, "seconds": seconds, "best": best, "worst": worst,
            "scores": {n: price(k) for n, k in picks.items()},
            "rank": {n: (None if price(k) is None or not all_scores else
                         sum(1 for v in all_scores if v <= price(k) + 1e-9) / len(all_scores))
                     for n, k in picks.items()},
            "enemy_distance": {n: (None if k is None else
                                   hex_distance(hex_geometry.parse_hex_label(k[0]), enemy_xy))
                               for n, k in picks.items()},
        })
    return _REAL_CHOOSE(mover, other, terrain_map, battle_rng, moves_first, standup_mp=standup_mp,
                        entry_edge=entry_edge)


def _battle(job):
    index, sim, seed, max_turns = job
    _, red, blue, board, _ = SCENARIOS[index]
    config.MECH_RED_MTF, config.MECH_BLUE_MTF, config.DEFAULT_BOARD_PATH = red, blue, board
    config.MECH_RED_CONFIG["bot"] = config.MECH_BLUE_CONFIG["bot"] = "gladiator"
    config.WORKERS, config.TIMING, config.REPLAY_BATTLES = 1, False, 0
    bots.choose_movement = _recording_choose
    _ROWS.clear()
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        terrain_map = orchestrator._load_map()
        template_red, template_blue, _, _ = config.load_two_mechs()
        result = orchestrator._run_one_battle(sim, sim, seed, max_turns, template_red, template_blue, terrain_map)
    for row in _ROWS:
        row.update(scenario=index, battle=sim)
    return list(_ROWS), {"scenario": index, "battle": sim, "turns": result.turns_taken}


def _mean(values):
    values = [v for v in values if v is not None]
    return (sum(values) / len(values)) if values else float("nan")


def _table(rows, title):
    lines = [title, f"  {'picker':<17} {'n':>4} {'% of best':>9} {'% of range':>10} {'got best':>9} {'rank pct':>9} {'hexes off':>10} "
                    f"{'same hex':>9} {'closer':>7} {'ms':>7}"]
    for name in PICKERS:
        mine = [r for r in rows if r["scores"].get(name) is not None]
        if not mine:
            continue
        pct = [100.0 * r["scores"][name] / r["best"] for r in mine if r["best"] and r["best"] > 0]
        spread = [100.0 * (r["scores"][name] - r["worst"]) / (r["best"] - r["worst"]) for r in mine
                  if r["best"] is not None and r["best"] - r["worst"] > 1e-9]
        got = [r["scores"][name] >= r["best"] - abs(r["best"]) * 1e-3 for r in mine if r["best"] is not None]
        perfect_hex = lambda r: r["picks"]["Perfect"][0] if r["picks"].get("Perfect") else None   # noqa: E731
        off = [hex_distance(hex_geometry.parse_hex_label(r["picks"][name][0]),
                            hex_geometry.parse_hex_label(perfect_hex(r)))
               for r in mine if perfect_hex(r)]
        same = [r["picks"][name][0] == perfect_hex(r) for r in mine if perfect_hex(r)]
        closer = [r["enemy_distance"]["Perfect"] - r["enemy_distance"][name] for r in mine
                  if r["enemy_distance"].get("Perfect") is not None]
        lines.append(f"  {name:<17} {len(mine):>4} {_mean(pct):>8.1f}% {_mean(spread):>9.1f}% {100 * _mean(got):>8.0f}% "
                     f"{100 * _mean([r['rank'][name] for r in mine]):>8.0f}% {_mean(off):>10.2f} "
                     f"{100 * _mean(same):>8.0f}% {_mean(closer):>+7.2f} "
                     f"{1000 * _mean([r['seconds'][name] for r in mine]):>7.0f}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("battles", nargs="?", type=int, default=20, help="battles per scenario")
    parser.add_argument("--scenarios", nargs="*", type=int, default=None, help="1-based scenario numbers")
    parser.add_argument("--turns", type=int, default=30, help="turn cap per battle")
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--workers", type=int, default=0, help="battles at once within a scenario (0 = all cores)")
    args = parser.parse_args()
    chosen = [s - 1 for s in args.scenarios] if args.scenarios else list(range(len(SCENARIOS)))
    workers = args.workers or os.cpu_count() or 1
    folder = os.path.join(REPO_ROOT, "run_stats", "pick_quality")
    os.makedirs(folder, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    all_rows, report = [], [f"Movement picks priced on Perfect Knowledge's scale - {args.battles} battles per "
                            f"scenario, Gladiator (Short Grid) driving both sides, seed {args.seed}, "
                            f"{args.turns}-turn cap"]
    for i in chosen:
        name, red, blue, board, kiter = SCENARIOS[i]
        started = time.perf_counter()
        jobs = [(i, sim, args.seed, args.turns) for sim in range(1, args.battles + 1)]
        rows, battles = [], []
        with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as pool:
            for got_rows, battle in pool.map(_battle, jobs):
                rows += got_rows
                battles.append(battle)
        all_rows += rows
        part = [f"\n{i + 1}. {name} ({red} Red vs {blue} Blue) - {len(rows)} decisions, "
                f"{_mean([b['turns'] for b in battles]):.1f} turns a battle, {(time.perf_counter() - started) / 60:.1f} min"]
        part.append(_table(rows, "  both sides"))
        for side in ("Red", "Blue"):
            label = f"  {side}{' (the kiter)' if side == kiter else ''}"
            part.append(_table([r for r in rows if r["side"] == side], label))
        text = "\n".join(part)
        print(text, flush=True)
        report.append(text)
        with open(os.path.join(folder, f"pick_quality_{stamp}.json"), "w") as f:
            json.dump({"args": vars(args), "rows": all_rows}, f)
    summary = ["", _table(all_rows, "ALL SCENARIOS")]
    for first, label in ((True, "first mover"), (False, "second mover")):
        summary.append(_table([r for r in all_rows if r["moves_first"] == first], f"ALL SCENARIOS - {label}"))
    kite_rows = [r for r in all_rows if SCENARIOS[r["scenario"]][4] == r["side"]]
    if kite_rows:
        summary.append(_table(kite_rows, "THE KITERS ONLY (Dervish, Griffin x2, Catapult)"))
    text = "\n".join(summary)
    print(text)
    report.append(text)
    with open(os.path.join(folder, f"pick_quality_{stamp}.txt"), "w") as f:
        f.write("\n".join(report) + "\n")


if __name__ == "__main__":
    main()
