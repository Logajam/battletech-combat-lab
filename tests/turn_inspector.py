"""
tests/turn_inspector.py - pick a turn of a baseline-battery battle and read back the math of that turn
(2026-11-07, Daniel: "select a turn in a match, and get a read back of all the math going on for that turn" - a
feature and a trouble-shooting tool).

    python tests/turn_inspector.py pg 6 9                       # Princess v Gladiator, battle 6, turn 9
    python tests/turn_inspector.py pg 6 9 --unit "Blue Jenner"  # only what that unit did (and was done to)
    python tests/turn_inspector.py pg 6 9 --set=LEGATE_COHESION=True   # the same turn under another setting
    python tests/turn_inspector.py pg 6 9 --json out.json       # the raw record too

setup: pp / pg / gg as in baseline_battery.py; battle: its number in the 20-battle battery (seed 12345); turn: the
turn to read.

How it works. The first time, battle N is played to the end of turn T-1 and the saved state of that moment is
kept (run_stats/inspector/, INTEGRATION__saved_state: the units, board, dice and bot memories; about the cost of
playing T-1 turns). Every later look loads that file and plays ONLY turn T, with the same dice, so the turn
happens exactly as it did in the battle and can be read as often as needed, or replayed under a changed
setting (--set) to see what one setting does to that one turn. Turn 1 is played from deployment.

What it prints, for the turn:
  1. Legate's estimate of where each enemy would end v where it really ended.
  2. Each move, in order: from -> to, and for a Gladiator move the damage the movement model expected from
     every enemy at the chosen spot v what the same model gives with the enemies where they REALLY ended, the
     score it predicted v the score at the real spots, and the regret (best spot in hindsight).
  3. Each attacker, at the start of the Ranged Attack Phase, against the enemy it chose: distance; the movement
     model's expected damage (score points and raw); the fire phase's own dry run; what the ranged shots really
     dealt; what its physical attack really dealt; then each shot (weapon, range, to-hit number, roll, hit,
     damage) and each physical attack.
  4. Each unit's HP before and after, and what killed it.
The readings come from tests/probe_hooks.py (the same recorders as legate_probe.py) and the battle event log
(INTEGRATION__stats). Nothing is changed in the battle: with no --set the turn plays out exactly as in the batch.
"""
import argparse
import io
import json
import os
import sys
from contextlib import redirect_stdout, redirect_stderr

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("", "pathfinder", "mechsim", "tests"):
    sys.path.insert(0, os.path.join(REPO, sub))
os.chdir(REPO)
os.environ.setdefault("INTEGRATION_DATA_DIR", "./data")

import INTEGRATION__config as config  # noqa: E402
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
import INTEGRATION__saved_state as saved_state  # noqa: E402
import INTEGRATION__stats as stats  # noqa: E402
import baseline_battery as bb  # noqa: E402
import probe_hooks  # noqa: E402
import hex_geometry  # noqa: E402
from los import hex_distance  # noqa: E402

SEED = 12345
CAP = 50


def configure(setup, sets):
    """The baseline battery's field and settings (what battle N of the battery is played under)."""
    red_bot, blue_bot, _title = bb.SETUPS[setup]
    config.FORCES = bb.forces(red_bot, blue_bot)
    config.STITCH_MAPS, config.STITCH_BOARDS = True, bb.BOARDS
    config.STITCH_GRID_COLS, config.STITCH_GRID_ROWS = 2, 1
    config.PROMPT_FOR_MAP = False
    config.DEPLOYMENT, config.DEPLOYMENT_DEPTH, config.WORKERS = "home_edge", 0, 1
    config.VERBOSE = False
    config.REPLAY_BATTLES = 0
    config.STATS = False
    for item in sets:                                   # --set=NAME=python literal
        k, v = item.split("=", 1)
        setattr(config, k, eval(v))


def state_file(setup, battle, turn):
    """Where the saved state at the END of `turn` of this battle lives."""
    folder = os.path.join(REPO, "run_stats", "inspector", setup)
    return os.path.join(folder, f"battle{battle}_seed{SEED}_turn{turn:03d}.json"), folder


def make_state(setup, battle, turn_before, terrain, roster):
    """Plays battle `battle` to the end of `turn_before` (default settings of the battery) and keeps the saved state."""
    path, folder = state_file(setup, battle, turn_before)
    if os.path.exists(path):
        return path
    configure(setup, [])                                # always the battery's own settings: the state is the battle's
    config.SAVE_STATE_TURNS, config.SAVE_STATE_BATTLES = (turn_before,), battle
    config.SAVE_STATE_DIR = folder
    print(f"playing battle {battle} to the end of turn {turn_before} (once; the state is kept) ...", flush=True)
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        orchestrator._run_one_roster(battle, 20, SEED, turn_before, roster, terrain)
    config.SAVE_STATE_TURNS = ()
    produced = saved_state.file_name(battle, orchestrator.battle_seed(SEED, battle), turn_before)
    if not os.path.exists(produced):
        raise SystemExit(f"the battle ended before turn {turn_before}: no state to inspect")
    os.replace(produced, path)
    return path


def play_the_turn(setup, battle, turn, sets, terrain, roster, flags=("--calib",)):
    """Plays turn `turn` of battle `battle`; returns (turn record from probe_hooks, event log, units' HP before)."""
    path = make_state(setup, battle, turn - 1, terrain, roster) if turn > 1 else None   # BEFORE the recorders go on
    probe_hooks.install(list(flags), "if_then")
    probe_hooks.REC["cur"] = []
    hp_before = None                                    # turn 1: the log's own turn-0 snapshot has it
    if turn == 1:
        configure(setup, sets)
        config.STATS = True
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = orchestrator._run_one_roster(battle, 20, SEED, 1, roster, terrain)
        log = result.stats
    else:
        battle_obj = saved_state.load(path)             # puts the battle's saved settings back
        for item in sets:                               # then a "what if" on top, if asked
            k, v = item.split("=", 1)
            setattr(config, k, eval(v))
        config.STATS = True
        battle_obj.max_turns = turn
        hp_before = {u.side_name: round(orchestrator.attack_resolution.total_hp(u)) for u in battle_obj.units}
        stats.start(battle_obj.units, battle)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            orchestrator.play_on(battle_obj)
        log = stats.finish()
    if not probe_hooks.REC["cur"]:
        raise SystemExit("that turn was not played (the battle was over)")
    log["hp_before"] = hp_before
    return probe_hooks.REC["cur"][0], log


# =============================================================================
# ==========================  THE READ-BACK  ==================================
# =============================================================================
def dist(a, b):
    if not a or not b:
        return None
    return hex_distance(hex_geometry.parse_hex_label(a), hex_geometry.parse_hex_label(b))


def show(rec, log, turn, only):
    def wanted(*names):
        return only is None or any(only in n for n in names if n)

    out = []
    p = out.append
    p(f"TURN {turn}")
    snaps = {s["turn"]: s["units"] for s in log["turns"]}
    after = snaps.get(turn, {})
    hp_before = log.get("hp_before") or {k: v.get("hp", 0) for k, v in snaps.get(0, {}).items()}

    # 1. Legate's estimate -------------------------------------------------------------------------------
    p("\n1. LEGATE: where it expected each unit to end v where it ended")
    real = rec.get("end", {})
    for team, plan in rec.get("plans", {}).items():
        if team.endswith("_own") or not plan:
            continue
        for unit, est in sorted(plan.items()):
            if not wanted(unit):
                continue
            err = dist(est, real.get(unit))
            p(f"   {unit:22s} expected {est}  ended {real.get(unit)}"
              f"{'' if err is None else f'  (off by {err} hexes)'}")

    # 2. Movement ----------------------------------------------------------------------------------------
    p("\n2. MOVEMENT, in the order it happened")
    for mv in rec.get("moves", []):
        if not wanted(mv["mover"]):
            continue
        p(f"   {mv['mover']:22s} [{mv['bot']}] foe {mv['primary']}: {mv['from']} -> {mv.get('to')}"
          f"   {mv.get('note') or ''}")
        if "on_me" in mv:
            top = sorted(mv["on_me"].items(), key=lambda kv: -kv[1])[:3]
            p("        predicted damage TAKEN at the chosen spot (raw): "
              + ", ".join(f"{k} {v:.1f}" for k, v in top) + f"   total {sum(mv['on_me'].values()):.1f}")
            if "true_on_me" in mv:
                p("        same model, enemies where they really ended:   "
                  + ", ".join(f"{k} {v:.1f}" for k, v in sorted(mv["true_on_me"].items(), key=lambda kv: -kv[1])[:3])
                  + f"   total {sum(mv['true_on_me'].values()):.1f}")
            p(f"        predicted damage DEALT (best single target): {max(mv['on_them'].values(), default=0):.1f}")
        if "true_score_chosen" in mv:
            regret = mv["true_score_best"] - mv["true_score_chosen"]
            p(f"        score: predicted {mv['pred_score_chosen']:.1f}, at the real spots {mv['true_score_chosen']:.1f}; "
              f"best in hindsight {mv['true_score_best']:.1f} at {mv['true_best_hex']} (regret {regret:.1f}, "
              f"{mv.get('spots', '?')} spots scored)")

    # 3. Attacks -----------------------------------------------------------------------------------------
    p("\n3. ATTACKS: the movement model v the fire phase v what happened")
    p("   (model = what the move picker believed, score points / raw points; dry = the fire phase's own estimate;"
      " ranged and physical = what really landed)")
    shots = [s for s in log["shots"] if s[0] == turn]
    phys = [s for s in log["phys"] if s[0] == turn]
    for attacker, target in sorted(rec.get("fire", {}).items()):
        if target is None or not wanted(attacker, target):
            continue
        key = f"{attacker}|{target}"
        model = rec.get("model", {}).get(key) or (None, None, None)
        d = dist(rec["pos"].get(attacker), rec["pos"].get(target))
        mine = [s for s in shots if s[1] == attacker]
        my_phys = [s for s in phys if s[1] == attacker]
        ranged = sum((s[8] or 0) for s in mine)
        physical = sum((s[5] or 0) for s in my_phys)

        def f(x):
            return "  - " if x is None or isinstance(x, str) else f"{x:5.1f}"
        p(f"   {attacker:22s} -> {target:22s} range {d}:  model {f(model[0])} / raw {f(model[2])}  |  dry {f(model[1])}"
          f"  |  ranged dealt {ranged:5.1f}  physical dealt {physical:5.1f}")
        for s in mine:
            _, _, tg, weapon, rng, tn, roll, hit, dmg = s[:9]
            p(f"        {weapon:22s} at {tg}: range {rng}, needs {tn}, rolled {roll}, {'HIT ' if hit else 'miss'} {dmg or 0:.0f}")
        for s in my_phys:
            _, _, tg, atk, hit, dmg = s[:6]
            p(f"        {atk:22s} at {tg}: {'HIT ' if hit else 'miss'} {dmg or 0:.0f}")

    # 4. Units -------------------------------------------------------------------------------------------
    p("\n4. UNITS: HP before -> after")
    for label in sorted(after):
        if not wanted(label):
            continue
        a = after[label]
        killer = (log.get("killed_by") or {}).get(label)
        death = (log.get("deaths") or {}).get(label)
        p(f"   {label:22s} {hp_before.get(label, 0):6.0f} -> {a.get('hp', 0):6.0f}   heat {a.get('heat', 0)}"
          f"{'  DESTROYED' if a.get('destroyed') else ''}{f' by {killer[0]} ({killer[1]})' if killer else ''}"
          f"{f' - {death[2]}' if death and not killer else ''}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("setup", choices=sorted(bb.SETUPS))
    ap.add_argument("battle", type=int)
    ap.add_argument("turn", type=int)
    ap.add_argument("--unit", help="only this unit (a part of its name is enough, e.g. 'Blue Jenner')")
    ap.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                    help="play the turn under another setting (a 'what if'): --set=LEGATE_COHESION=True")
    ap.add_argument("--json", help="also write the raw record here")
    a = ap.parse_args()
    sets = [s[4:] if s.startswith("set=") else s for s in a.set]
    configure(a.setup, [])
    with redirect_stdout(io.StringIO()):
        terrain = orchestrator._load_map()
        roster = config.load_roster()
    rec, log = play_the_turn(a.setup, a.battle, a.turn, sets, terrain, roster)
    print(f"{bb.SETUPS[a.setup][2]}, battle {a.battle} (seed {orchestrator.battle_seed(SEED, a.battle)})"
          f"{', under ' + ', '.join(sets) if sets else ''}")
    print(show(rec, log, a.turn, a.unit))
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"turn": rec, "log": log}, f, default=str)


if __name__ == "__main__":
    main()
