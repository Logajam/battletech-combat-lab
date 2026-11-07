"""
tests/baseline_battery.py - the baseline test battery (2026-10-28, Daniel: "Lets set up
a baseline test battery ... Mostly seeing if it works and how long it takes. Results
will be recorded as a yard stick for future tests.").

    python tests/baseline_battery.py pp 1              # Princess vs Princess, 1 battle
    python tests/baseline_battery.py pg 3 --seed 7     # Princess (Red) vs Gladiator (Blue), 3 battles
    python tests/baseline_battery.py gg 3              # Gladiator vs Gladiator

The field: TWO 16x17 boards stitched 2 x 1 (a 32 x 17 field - 33 x 17 before the MegaMek seams of 2026-11-06; Daniel: "drop down to a 2x1 map size. Give the bots less room to hide in" - the first try was four boards, 2 x 2, and ran 50 turns with no result), 12 'Mechs a side, mirrored -
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
config.STATS = False  # event log + report off: not part of a test or battery (2026-11-06)
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
    ap.add_argument("--cohesion", type=float, default=None,
                    help="config.LEGATE_COHESION on, at this LEGATE_COHESION_SCALE (2026-10-30)")
    ap.add_argument("--herding", action=argparse.BooleanOptionalAction, default=config.LEGATE_HERDING,
                    help="config.LEGATE_HERDING: the penalty for a spot beyond every friend's support")
    ap.add_argument("--fire-order", choices=("big_guns_first", "roster"), default=config.GLADIATOR_FIRE_ORDER,
                    help="config.GLADIATOR_FIRE_ORDER")
    ap.add_argument("--team-value", choices=("sum", "product"), default=config.LEGATE_TEAM_VALUE,
                    help="config.LEGATE_TEAM_VALUE: score a move by the whole team's future damage")
    ap.add_argument("--move-order", choices=("index", "tiered", "random", "reverse"), default=config.MOVE_ORDER,
                    help="config.MOVE_ORDER: which unit of a side moves next (2026-11-07)")
    ap.add_argument("--peril", choices=("off", "peak", "mean"), default=config.PERIL,
                    help="how Legate prices the other enemies' fire: from the one estimated spot (off) or the whole field (INTEGRATION__peril)")
    ap.add_argument("--peril-blend", type=float, default=config.PERIL_BLEND, help="the share the peril field takes (1.0 = only it)")
    ap.add_argument("--stack", type=float, default=None, help="stacked coverage weight (INTEGRATION__stack); off when absent")
    ap.add_argument("--stack-quantile", type=float, default=None, help="read coverage at this quantile of the enemy footprint (default: the mean)")
    ap.add_argument("--triage", type=float, default=None, help="peril / toughness tiers: the fraction of the team in each of the hot and cool tiers (INTEGRATION__triage)")
    ap.add_argument("--triage-hot", type=float, default=config.TRIAGE_HOT_RECEIVED, help="hot tier: damage taken counts this many times")
    ap.add_argument("--triage-cool", type=float, default=config.TRIAGE_COOL_DEALT, help="cool tier: damage dealt counts this many times")
    ap.add_argument("--exchange", action=argparse.BooleanOptionalAction, default=config.LEGATE_TEAM_EXCHANGE,
                    help="config.LEGATE_TEAM_EXCHANGE: with a team value, also count the enemy damage our fire removes")
    ap.add_argument("--stats", action="store_true",
                    help="also record every battle's event log (INTEGRATION__stats: each shot, physical attack, unit snapshot "
                         "and death) in its saved file; then `python tests/battery_stats.py <name>` makes the statistics page")
    ap.add_argument("--fresh", action="store_true",
                    help="ignore the saved battles and run every one again (default: a battle already saved for these settings is skipped)")
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
    if args.cohesion is not None:
        config.LEGATE_COHESION, config.LEGATE_COHESION_SCALE = True, args.cohesion
    config.GLADIATOR_FIRE_ORDER = args.fire_order
    config.LEGATE_TEAM_VALUE = args.team_value
    config.MOVE_ORDER = args.move_order
    config.PERIL, config.PERIL_BLEND = args.peril, args.peril_blend
    if args.triage is not None:
        config.TRIAGE, config.TRIAGE_FRACTION = True, args.triage
        config.TRIAGE_HOT_RECEIVED, config.TRIAGE_COOL_DEALT = args.triage_hot, args.triage_cool
    if args.stack is not None:
        config.STACK, config.STACK_WEIGHT, config.STACK_QUANTILE = True, args.stack, args.stack_quantile
    config.STATS = args.stats        # off by default: a little time a shot (the reference checks switch it off too)
    config.LEGATE_TEAM_EXCHANGE = args.exchange
    tag = (f"split-{args.fire_split}{'-now' if args.split_now else ''}{'_herd' if args.herding else ''}{f'_coh{args.cohesion}' if args.cohesion is not None else ''}_{args.fire_order}"
           f"{f'_team-{args.team_value}{"" if args.exchange else "-noexch"}' if args.team_value else ''}{f'_order-{args.move_order}' if args.move_order != 'index' else ''}{f'_peril-{args.peril}-{args.peril_blend:g}' if args.peril != 'off' else ''}{f'_triage-{args.triage:g}-h{args.triage_hot:g}-c{args.triage_cool:g}' if args.triage is not None else ''}{f'_stack-{args.stack:g}{"" if args.stack_quantile is None else f"q{args.stack_quantile:g}"}' if args.stack is not None else ''}")
    config.REPLAY_BATTLES = 1 if args.replay else 0
    with redirect_stdout(io.StringIO()):
        terrain = orchestrator._load_map()
        roster = config.load_roster()
    print(f"{title}{' + Legate' if args.legate else ''}, Gladiator targets: {args.target}, {tag}: 12 v 12 on a 2 x 1 stitched field, {args.battles} battle(s), cap {args.turns} turns, seed {args.seed}")
    rows = []
    # RESUMABLE (2026-11-07, Daniel: "write the driver and make it standard equipment"): every finished battle is
    # saved at once under run_stats/baseline/saved/<these settings>/, so a restart of the machine costs only the
    # battle in progress - run the same command again and the saved battles are skipped. A battle's seed depends
    # only on its number, so saved and fresh battles are interchangeable. --fresh ignores the saved ones.
    run_key = f"{args.setup}{'_legate' if args.legate else ''}_{args.target}_{tag}_seed{args.seed}_turns{args.turns}{'_stats' if args.stats else ''}"
    save_dir = os.path.join(REPO_ROOT, "run_stats", "baseline", "saved", run_key)
    os.makedirs(save_dir, exist_ok=True)
    for n in range(args.first, (args.last or args.battles) + 1):
        saved_path = os.path.join(save_dir, f"battle_{n:03d}.json")
        row = None
        if not args.fresh and os.path.exists(saved_path):
            try:
                with open(saved_path) as f:
                    row = json.load(f)
                row["teams"] = {k: tuple(v) for k, v in row["teams"].items()}
                row["from_saved"] = True
            except (OSError, ValueError, KeyError):
                row = None            # a half-written file from a crash: run the battle again
        if row is None:
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
            if args.stats and getattr(result, "stats", None):
                row["stats"] = result.stats
                row["destroyed"], row["turn_cap"] = getattr(result, "destroyed", None), getattr(result, "turn_cap", None)
            tmp = saved_path + ".tmp"
            with open(tmp, "w") as f:                     # write whole, then rename: never a half file
                json.dump(row, f, default=str)
            os.replace(tmp, saved_path)
        rows.append(row)
        teams, wall = row["teams"], row["seconds"]
        print(f"  battle {n}: {row['winner']} after {row['turns']} turns"
              f"{' (hit the cap)' if row['turns'] >= args.turns else ''} | "
              + " | ".join(f"{t}: {alive}/12 left, HP {hp}/{mx}, dealt {dealt}" for t, (alive, hp, mx, dealt) in teams.items())
              + f" | {wall:.0f} s ({row['seconds_per_turn']} s a turn){' [saved]' if row.get('from_saved') else ''}")
        if row.get("timing") and not row.get("from_saved"):
            secs = {k: (v[0] if isinstance(v, (list, tuple)) else v) for k, v in row["timing"].items()}
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
