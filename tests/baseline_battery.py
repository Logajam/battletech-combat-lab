"""
tests/baseline_battery.py - the baseline test battery (2026-10-28, Daniel: "Lets set up
a baseline test battery ... Mostly seeing if it works and how long it takes. Results
will be recorded as a yard stick for future tests.").

    python tests/baseline_battery.py pp 1              # Princess vs Princess, 1 battle
    python tests/baseline_battery.py pg 3 --seed 7     # Princess (Red) vs Gladiator (Blue), 3 battles
    python tests/baseline_battery.py gg 3              # Gladiator vs Gladiator

The field: TWO 16x17 boards stitched 2 x 1 (a 33 x 17 field; Daniel: "drop down to a 2x1 map size. Give the bots less room to hide in" - the first try was four boards, 2 x 2, and ran 50 turns with no result), 12 'Mechs a side, mirrored -
the same twelve on each side: 3 assault (Atlas AS7-K 100t, Emperor EMP-6D 90t, Awesome
AWS-8Q 80t), 3 heavy (Archer ARC-2R 70t, Cataphract CTF-3D 70t, Catapult CPLT-C1 65t),
3 medium (Kintaro KTO-19 55t, Griffin GRF-1N 55t, Hunchback HBK-4G 50t), 3 light (Jenner
JR7-D 35t, Commando COM-2D 25t, Locust LCT-1V 20t). Gunnery 4 / piloting 5, default
settings, home-edge deployment, a 50-turn cap (the reference battles' cap). Battles
run one after another (so the wall time is the cost of one battle); each one's seed is
battle_seed(--seed, n). Per battle: winner, turns, units left and HP left per side, wall
seconds (one core a battle: run the three setups side by side and each is still the 1-core yardstick); the time table INTEGRATION__timing prints; rows go to run_stats/baseline/ (git-ignored).
"""

import argparse
import io
import json
import os
import sys
import time
from contextlib import redirect_stdout, redirect_stderr

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)
os.environ.setdefault("INTEGRATION_DATA_DIR", "./data")

import INTEGRATION__config as config  # noqa: E402
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
import INTEGRATION__replay as replay  # noqa: E402
import INTEGRATION__timing as timing  # noqa: E402

BOARDS = ["16x17_Grassland_1.board", "16x17_Desert_Hills.board"]
FORCE = [("Atlas AS7-K", "assault"), ("Emperor EMP-6D", "assault"), ("Awesome AWS-8Q", "assault"),
         ("Archer ARC-2R", "heavy"), ("Cataphract CTF-3D", "heavy"), ("Catapult CPLT-C1", "heavy"),
         ("Kintaro KTO-19", "medium"), ("Griffin GRF-1N", "medium"), ("Hunchback HBK-4G", "medium"),
         ("Jenner JR7-D", "light"), ("Commando COM-2D", "light"), ("Locust LCT-1V", "light")]
SETUPS = {"pp": ("princess", "princess", "Princess vs Princess"),
          "pg": ("princess", None, "Princess (Red) vs Gladiator (Blue)"),
          "gg": (None, None, "Gladiator vs Gladiator")}


def forces(red_bot, blue_bot):
    return [{"team": team, "mtf": f"{name}.mtf", "name": f"{team} {name.split()[0]}", "bot": bot}
            for team, bot in (("Red", red_bot), ("Blue", blue_bot)) for name, _ in FORCE]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("setup", choices=sorted(SETUPS))
    ap.add_argument("battles", type=int, nargs="?", default=1)
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--turns", type=int, default=50)
    ap.add_argument("--first", type=int, default=1, help="run only battles FIRST..LAST of the BATTLES (split a battery over cores)")
    ap.add_argument("--last", type=int, default=0)
    ap.add_argument("--replay", action="store_true", help="save battle 1 as a replay page in replays/")
    ap.add_argument("--legate", action=argparse.BooleanOptionalAction, default=config.LEGATE,
                    help="config.LEGATE (default on since 2026-10-29; --no-legate for the old one-foe Gladiator)")
    ap.add_argument("--target", choices=("princess_plan", "kill_curve", "nearest"), default=config.STUB_GLADIATOR_TARGET,
                    help="config.STUB_GLADIATOR_TARGET: whom a Gladiator unit shoots (2026-10-29)")
    ap.add_argument("--fire-split", choices=("proportional", "none"), default=config.LEGATE_FIRE_SPLIT,
                    help="config.LEGATE_FIRE_SPLIT: a Gladiator's expected share of an enemy's future fire")
    ap.add_argument("--split-now", action=argparse.BooleanOptionalAction, default=config.LEGATE_SPLIT_THIS_TURN,
                    help="config.LEGATE_SPLIT_THIS_TURN: the same share for this turn's damage (2026-10-30)")
    ap.add_argument("--herding", action=argparse.BooleanOptionalAction, default=config.LEGATE_HERDING,
                    help="config.LEGATE_HERDING: the penalty for a spot beyond every friend's support")
    ap.add_argument("--fire-order", choices=("big_guns_first", "roster"), default=config.GLADIATOR_FIRE_ORDER,
                    help="config.GLADIATOR_FIRE_ORDER")
    ap.add_argument("--team-value", choices=("sum", "product"), default=config.LEGATE_TEAM_VALUE,
                    help="config.LEGATE_TEAM_VALUE: score a move by the whole team's future damage")
    args = ap.parse_args()
    red_bot, blue_bot, title = SETUPS[args.setup]
    config.FORCES = forces(red_bot, blue_bot)
    config.STITCH_MAPS, config.STITCH_BOARDS = True, BOARDS
    config.STITCH_GRID_COLS, config.STITCH_GRID_ROWS = 2, 1
    config.PROMPT_FOR_MAP = False
    config.DEPLOYMENT, config.DEPLOYMENT_DEPTH, config.WORKERS = "home_edge", 0, 1
    config.VERBOSE = False
    config.LEGATE = args.legate
    config.STUB_GLADIATOR_TARGET = args.target
    config.LEGATE_FIRE_SPLIT, config.LEGATE_HERDING = args.fire_split, args.herding
    config.LEGATE_SPLIT_THIS_TURN = args.split_now
    config.GLADIATOR_FIRE_ORDER = args.fire_order
    config.LEGATE_TEAM_VALUE = args.team_value
    tag = (f"split-{args.fire_split}{'-now' if args.split_now else ''}{'_herd' if args.herding else ''}_{args.fire_order}"
           f"{f'_team-{args.team_value}' if args.team_value else ''}")
    config.REPLAY_BATTLES = 1 if args.replay else 0
    with redirect_stdout(io.StringIO()):
        terrain = orchestrator._load_map()
        roster = config.load_roster()
    print(f"{title}{' + Legate' if args.legate else ''}, Gladiator targets: {args.target}, {tag}: 12 v 12 on a 2 x 1 stitched field, {args.battles} battle(s), cap {args.turns} turns, seed {args.seed}")
    rows = []
    for n in range(args.first, (args.last or args.battles) + 1):
        timing.reset() if hasattr(timing, "reset") else None
        t0 = time.time()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = orchestrator._run_one_roster(n, args.battles, args.seed, args.turns, roster, terrain)
        wall = time.time() - t0
        if getattr(result, "replay", None):
            print(f"  replay -> {replay.write(result.replay)}")
        teams = {name: (s.units - s.units_lost, round(s.final_hp), round(s.max_hp), round(s.damage_dealt))
                 for name, s in result.teams.items()}
        row = {"battle": n, "seed": result.seed, "winner": result.winner, "turns": result.turns_taken,
               "teams": teams, "seconds": round(wall, 1), "seconds_per_turn": round(wall / max(1, result.turns_taken), 2),
               "timing": result.timing}
        rows.append(row)
        print(f"  battle {n}: {result.winner} after {result.turns_taken} turns"
              f"{' (hit the cap)' if result.turns_taken >= args.turns else ''} | "
              + " | ".join(f"{t}: {alive}/12 left, HP {hp}/{mx}, dealt {dealt}" for t, (alive, hp, mx, dealt) in teams.items())
              + f" | {wall:.0f} s ({row['seconds_per_turn']} s a turn)")
        if result.timing:
            secs = {k: (v[0] if isinstance(v, (list, tuple)) else v) for k, v in result.timing.items()}
            print("    time: " + ", ".join(f"{k} {v:.0f}s" for k, v in sorted(secs.items(), key=lambda kv: -kv[1])[:8]))
    out_dir = os.path.join(REPO_ROOT, "run_stats", "baseline")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{args.setup}{'_legate' if args.legate else ''}_{args.target}_{tag}_seed{args.seed}_{args.first}-{args.last or args.battles}_{int(time.time())}.json")
    with open(path, "w") as f:
        json.dump({"setup": title, "legate": args.legate, "gladiator_target": args.target, "settings": tag, "seed": args.seed, "turn_cap": args.turns, "boards": BOARDS,
                   "force": [n for n, _ in FORCE], "rows": rows}, f, indent=1, default=str)
    print(f"rows -> {path}")


if __name__ == "__main__":
    main()
