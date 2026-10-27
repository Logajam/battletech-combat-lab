"""
tests/bot_agreement.py - how often the Princess clone's movement pick matches
what Gladiator would pick in the same spot (added 2026-10-27, Claude, for
Daniel: "get a sense for how often princes's top pick matches the 'Perfect
Knowledge' and the current default setting ... if it were gladiator").

    python tests/bot_agreement.py                    # 10 battles per matchup, the 8 below
    python tests/bot_agreement.py 20 --matchups 1 2  # 20 battles, the first two matchups

Every battle is Princess against Gladiator (Princess is Red in odd-numbered
battles, Blue in even ones, so both sides and both movement orders come up).
At EVERY movement decision of either 'Mech, three pickers are asked about the
same position before the move is made:
  - Princess            (INTEGRATION__princess)
  - Gladiator Short Grid - Gladiator at the current defaults: its own spot by
                         the grid search, the first mover's look-ahead by the
                         short list (MOVEMENT_SEARCH = "grid",
                         MOVEMENT_ASSUMED_ENEMY_SEARCH = "short_list").
                         "Short Grid" is a placeholder nickname - Daniel's to
                         rename.
  - Gladiator Perfect  - Gladiator with perfect knowledge: every spot, and
                         every reply spot in the look-ahead ("exhaustive").
Only the 'Mech's own bot's pick is then played, so the battle is the same
one a plain run gives (the extra pickers get a copy of the dice, never the
dice themselves). Charges / DFAs count as their own picks.

Reported per matchup and overall, for each pair (Princess vs Perfect,
Princess vs Short Grid, and Short Grid vs Perfect as the yardstick of how
much Gladiator's own fast search differs): the share of decisions where the
two picks are the same spot (hex, facing and movement mode), the same hex and
facing, the same hex, and the average hexes between the two picks. Split by
first / second mover. Raw rows go to run_stats/agreement/ as JSON.

Slow: Gladiator Perfect's look-ahead scores every spot against every reply
(~4x the default). Battles run in parallel (--workers, default all cores).
"""

import argparse
import copy
import io
import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
import multiprocessing

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402 - registers bare "config" first
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
import INTEGRATION__bots as bots  # noqa: E402
import INTEGRATION__princess as princess  # noqa: E402
import INTEGRATION__movement_selection as movement_selection  # noqa: E402
import hex_geometry  # noqa: E402 - PATHFINDER
from los import hex_distance  # noqa: E402 - PATHFINDER

# (red .mtf, blue .mtf, board or None) - the reference battles' matchups.
MATCHUPS = [
    ("Kontio.mtf", "Hammerhead.mtf", None),
    ("Atlas AS7-K.mtf", "Archer ARC-2R.mtf", None),
    ("Kintaro KTO-19.mtf", "Atlas AS7-K.mtf", None),
    ("Cataphract CTF-3D.mtf", "Emperor EMP-6D.mtf", None),
    ("Akuma AKU-2XK.mtf", "Highlander IIC 2.mtf", None),
    ("Bombardier BMB-14K.mtf", "Black Hawk (Nova) F.mtf", None),
    ("Black Hawk (Nova) F.mtf", "Cataphract CTF-3D.mtf", "16x17_Military_Base_1.board"),
    ("Black Hawk (Nova) F.mtf", "Cataphract CTF-3D.mtf", "16x17_Large_Lakes_1.board"),
]
PICKERS = ("Princess", "Short Grid", "Perfect")
PAIRS = (("Princess", "Perfect"), ("Princess", "Short Grid"), ("Short Grid", "Perfect"))
SEARCHES = {"Short Grid": ("grid", "short_list"), "Perfect": ("exhaustive", "exhaustive")}


def _spot(pick):
    """A pick as (hex, facing, mode, attack) or None."""
    if pick is None:
        return None
    attack = "charge" if pick.get("charge") else ("dfa" if pick.get("dfa") else "")
    return pick["hex"], pick["facing"], pick["mode"], attack


def _gladiator(mover, other, terrain_map, rng, moves_first, standup_mp, entry_edge, searches):
    saved = mover.move_search, mover.assumes_enemy_search
    mover.move_search, mover.assumes_enemy_search = searches
    try:
        return movement_selection.choose(mover, other, terrain_map, rng, moves_first,
                                         standup_mp=standup_mp, entry_edge=entry_edge)[0]
    finally:
        mover.move_search, mover.assumes_enemy_search = saved


_ROWS = []
_REAL_CHOOSE = bots.choose_movement


def _recording_choose(mover, other, terrain_map, battle_rng, moves_first, standup_mp=None, entry_edge=None):
    """bots.choose_movement, after asking all three pickers about the same
    position (each on a copy of the dice)."""
    if other.hex is not None and entry_edge is None:     # a real decision: both 'Mechs on the board
        picks = {"Princess": princess.choose(mover, other, terrain_map, copy.deepcopy(battle_rng), moves_first,
                                             standup_mp=standup_mp)[0]}
        for name, searches in SEARCHES.items():
            picks[name] = _gladiator(mover, other, terrain_map, copy.deepcopy(battle_rng), moves_first,
                                     standup_mp, None, searches)
        _ROWS.append({"side": mover.side_name, "driver": mover.bot, "moves_first": bool(moves_first),
                      "stood_up": standup_mp is not None, "mover_hex": mover.hex, "enemy_hex": other.hex,
                      "picks": {k: _spot(v) for k, v in picks.items()}})
    return _REAL_CHOOSE(mover, other, terrain_map, battle_rng, moves_first, standup_mp=standup_mp,
                        entry_edge=entry_edge)


def _battle(job):
    """One battle in a worker: (matchup index, battle number, seed, turn cap) -> rows."""
    index, sim, seed, max_turns = job
    red, blue, board = MATCHUPS[index]
    config.MECH_RED_MTF, config.MECH_BLUE_MTF = red, blue
    if board:
        config.DEFAULT_BOARD_PATH = board
    princess_side = "MECH_RED_CONFIG" if sim % 2 else "MECH_BLUE_CONFIG"
    other_side = "MECH_BLUE_CONFIG" if sim % 2 else "MECH_RED_CONFIG"
    getattr(config, princess_side)["bot"] = "princess"
    getattr(config, other_side)["bot"] = "gladiator"
    config.WORKERS, config.TIMING, config.REPLAY_BATTLES = 1, False, 0
    bots.choose_movement = _recording_choose
    _ROWS.clear()
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        terrain_map = orchestrator._load_map()
        template_red, template_blue, _, _ = config.load_two_mechs()
        result = orchestrator._run_one_battle(sim, sim, seed, max_turns, template_red, template_blue, terrain_map)
    for row in _ROWS:
        row.update(matchup=index, battle=sim)
    winner = "Draw"
    if result.red.destroyed != result.blue.destroyed:
        winner = "Blue" if result.red.destroyed else "Red"
    return list(_ROWS), {"matchup": index, "battle": sim, "turns": result.turns_taken, "winner": winner,
                         "princess": "Red" if sim % 2 else "Blue"}


def _compare(a, b):
    """(same spot, same hex + facing, same hex, hexes apart) for two picks."""
    if a is None or b is None:
        return None
    return (a == b, a[:2] == b[:2], a[0] == b[0],
            hex_distance(hex_geometry.parse_hex_label(a[0]), hex_geometry.parse_hex_label(b[0])))


def _table(rows, title):
    lines = [title, f"  {'pair':<26} {'decisions':>9} {'same spot':>10} {'hex+facing':>11} {'same hex':>9} "
                    f"{'avg hexes apart':>16}"]
    for x, y in PAIRS:
        got = [c for c in (_compare(r["picks"][x], r["picks"][y]) for r in rows) if c is not None]
        if not got:
            continue
        n = len(got)
        share = lambda i: 100.0 * sum(1 for c in got if c[i]) / n            # noqa: E731
        lines.append(f"  {x + ' vs ' + y:<26} {n:>9} {share(0):>9.0f}% {share(1):>10.0f}% {share(2):>8.0f}% "
                     f"{sum(c[3] for c in got) / n:>16.2f}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("battles", nargs="?", type=int, default=10, help="battles per matchup")
    parser.add_argument("--matchups", nargs="*", type=int, default=None, help="1-based matchup numbers")
    parser.add_argument("--turns", type=int, default=30, help="turn cap per battle")
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--workers", type=int, default=0, help="0 = one per CPU core")
    args = parser.parse_args()
    chosen = [m - 1 for m in args.matchups] if args.matchups else list(range(len(MATCHUPS)))
    jobs = [(i, sim, args.seed, args.turns)
            for i in chosen for sim in range(1, args.battles + 1)]
    workers = args.workers or os.cpu_count() or 1
    started = time.perf_counter()
    rows, battles = [], []
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as pool:
        for got_rows, battle in pool.map(_battle, jobs):
            rows += got_rows
            battles.append(battle)
    elapsed = time.perf_counter() - started

    out = [f"Princess's movement pick against Gladiator's, {args.battles} battles per matchup, seed {args.seed}, "
           f"{args.turns}-turn cap, {len(rows)} decisions, {elapsed / 60:.1f} min"]
    for i in chosen:
        red, blue, board = MATCHUPS[i]
        mine = [r for r in rows if r["matchup"] == i]
        wins = sum(1 for b in battles if b["matchup"] == i and b["winner"] == b["princess"])
        losses = sum(1 for b in battles if b["matchup"] == i and b["winner"] not in ("Draw", b["princess"]))
        out.append("")
        out.append(_table(mine, f"{i + 1}. {red} vs {blue}{f' ({board})' if board else ''} - "
                                f"Princess won {wins}, lost {losses} of {args.battles}"))
    out.append("")
    out.append(_table(rows, "ALL MATCHUPS"))
    for first, label in ((True, "first mover (enemy still to move)"), (False, "second mover (enemy has moved)")):
        out.append("")
        out.append(_table([r for r in rows if r["moves_first"] == first], f"ALL MATCHUPS - {label}"))
    report = "\n".join(out)
    print(report)
    folder = os.path.join(REPO_ROOT, "run_stats", "agreement")
    os.makedirs(folder, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    with open(os.path.join(folder, f"agreement_{stamp}.json"), "w") as f:
        json.dump({"args": vars(args), "battles": battles, "rows": rows}, f)
    with open(os.path.join(folder, f"agreement_{stamp}.txt"), "w") as f:
        f.write(report + "\n")


if __name__ == "__main__":
    main()
