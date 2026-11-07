"""
tests/legate_probe.py - a diagnostic battery (2026-10-30, session 15; Daniel: measure "not just how wrong
the prediction was, but to the degree it was wrong"). Princess Red v Gladiator Blue, the
baseline_battery setup, with probes that leave the battle untouched (same results as the battery).

Per turn it records:
  - Legate's estimate of each enemy's end hex vs where it really ended (and where it started);
  - each Gladiator move: its primary foe, the chosen spot, the predicted RAW damage taken from each
    enemy and dealt (no exposure weights), and the objective's parts;
  - the Ranged Attack Phase: who shot whom, the damage each unit dealt and took;
  - after movement: every unit's hex (cohesion).
  - with --calib: every attacker v every enemy at the start of the Ranged Attack Phase, everyone at
    their real spots: the movement model's expected damage (structure-weighted and raw) and the fire
    phase's own dry run - to compare with what the pairs that fired really dealt.
  - each Gladiator move is re-scored at the end of the Movement Phase with the enemies at their TRUE
    end spots (same model): the damage the estimate missed, and the regret of the choice.

    python tests/legate_probe.py OUT.json FIRST LAST [--estimate hold] [--calib] [--set=CONFIG_NAME=literal ...]
    python tests/legate_probe_report.py OUT.json [more.json ...]
Battles FIRST..LAST of the 20-battle battery (seed 12345, cap 50). --estimate hold: Legate's estimate
replaced by "every enemy stands still" (an A/B). Probes patch functions in this process only.
"""
import io, json, os, sys, time
from contextlib import redirect_stdout, redirect_stderr

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, "tests"))
os.chdir(REPO)
os.environ.setdefault("INTEGRATION_DATA_DIR", "./data")
import INTEGRATION__config as config
config.STATS = False  # event log + report off: not part of a test or battery (2026-11-06)
import INTEGRATION__orchestrator as orchestrator
import INTEGRATION__legate as legate
import INTEGRATION__movement_selection as ms
import INTEGRATION__attack_resolution as ar
import INTEGRATION__forces as forces
import baseline_battery as bb

out_path, first, last = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
flags = sys.argv[4:]
estimate_mode = "if_then"
if "--estimate" in flags:
    estimate_mode = flags[flags.index("--estimate") + 1]
config.FORCES = bb.forces("princess", None)
config.STITCH_MAPS, config.STITCH_BOARDS = True, bb.BOARDS
config.STITCH_GRID_COLS, config.STITCH_GRID_ROWS = 2, 1
config.PROMPT_FOR_MAP = False
config.DEPLOYMENT, config.DEPLOYMENT_DEPTH, config.WORKERS = "home_edge", 0, 1
config.VERBOSE = False
config.REPLAY_BATTLES = 0
for f in flags:
    if f.startswith("--set="):                       # --set=NAME=python literal
        k, v = f[6:].split("=", 1)
        setattr(config, k, eval(v))

import probe_hooks                      # the recorders (2026-11-07: moved out so tests/turn_inspector.py can use them)
probe_hooks.install(flags, estimate_mode)
REC = probe_hooks.REC

with redirect_stdout(io.StringIO()):
    terrain = orchestrator._load_map()
    roster = config.load_roster()
battles = []
for n in range(first, last + 1):
    REC["cur"] = []
    t0 = time.time()
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        result = orchestrator._run_one_roster(n, 20, 12345, 50, roster, terrain)
    teams = {k: (s.units - s.units_lost, round(s.damage_dealt)) for k, s in result.teams.items()}
    battles.append({"battle": n, "winner": result.winner, "turns": result.turns_taken, "teams": teams,
                    "turn_log": REC["cur"]})
    print(n, result.winner, result.turns_taken, teams, round(time.time() - t0), flush=True)
    with open(out_path, "w") as f:
        json.dump({"flags": flags, "battles": battles}, f, default=str)
