"""
tests/test_stats.py - checks the battle statistics (INTEGRATION__stats and
INTEGRATION__stats_report, added 2026-11-06): logging a battle changes nothing
about it, the event log agrees with the battle's own result, a team battle
analyzes cleanly, and the written page carries the analysis intact.

    python tests/test_stats.py
"""

import io
import json
import os
import re
import sys
import tempfile
import traceback
from contextlib import redirect_stderr, redirect_stdout

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402 - registers bare "config" first
config.STATS = False                   # each check turns it on where it needs it
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
import INTEGRATION__stats_report as stats_report  # noqa: E402

TERRAIN = orchestrator._load_map()
OUT_DIR = tempfile.mkdtemp()


def one_battle(stats_on, seed=11, max_turns=12):
    saved = config.STATS, config.DEPLOYMENT_DEPTH
    config.STATS, config.DEPLOYMENT_DEPTH = stats_on, 0
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            red, blue, _, _ = config.load_two_mechs()
            return orchestrator._run_one_battle(1, 1, seed, max_turns, red, blue, TERRAIN)
    finally:
        config.STATS, config.DEPLOYMENT_DEPTH = saved


def team_batch(n=3, max_turns=5):
    saved = (config.FORCES, config.DEPLOYMENT_DEPTH, config.STATS)
    config.FORCES = [{"team": "Red", "mtf": "Kontio.mtf", "count": 2},
                     {"team": "Blue", "mtf": "Hammerhead.mtf", "count": 2}]
    config.DEPLOYMENT_DEPTH, config.STATS = 0, True
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            roster = config.load_roster()
            return [orchestrator._run_one_roster(i, n, 100 + i, max_turns, roster, TERRAIN) for i in range(1, n + 1)]
    finally:
        config.FORCES, config.DEPLOYMENT_DEPTH, config.STATS = saved


PLAIN = one_battle(False)
LOGGED = one_battle(True)


def logging_changes_nothing():
    assert PLAIN.stats is None and LOGGED.stats is not None
    key = lambda r: (r.turns_taken, r.winner, r.red.final_hp, r.blue.final_hp, r.red.damage_dealt, r.blue.damage_dealt,
                     r.red.cause_of_death, r.blue.cause_of_death)
    assert key(PLAIN) == key(LOGGED), (key(PLAIN), key(LOGGED))


def log_agrees_with_the_result():
    log = LOGGED.stats
    assert len(log["turns"]) == LOGGED.turns_taken + 1, (len(log["turns"]), LOGGED.turns_taken)
    assert [t["turn"] for t in log["turns"]] == list(range(LOGGED.turns_taken + 1))
    for label, unit in LOGGED.units.items():
        assert log["turns"][-1]["units"][label]["hp"] == unit.final_hp, label
        assert (label in log["deaths"]) == bool(unit.destroyed), label
        if unit.destroyed:
            assert log["deaths"][label][2] == unit.cause_of_death, label
    for victim, (killer, how) in log["killed_by"].items():
        assert victim in log["deaths"] and log["teams"][killer] != log["teams"][victim], (victim, killer)
    # the damage the shots and physical attacks did to a unit never exceeds what it lost
    for label, unit in LOGGED.units.items():
        done = sum(r[8] for r in log["shots"] if r[2] == label) + sum(r[5] for r in log["phys"] if r[2] == label)
        lost = log["units"][label]["max_hp"] - unit.final_hp
        assert done <= lost + 1e-9, (label, done, lost)
    # a ranged attacker's own damage total matches the engine's own count
    for label, unit in LOGGED.units.items():
        shots = sum(r[8] for r in log["shots"] if r[1] == label)
        assert abs(shots - unit.damage_dealt) < 1e-6, (label, shots, unit.damage_dealt)
    assert all(r[4] is None or r[4] >= 1 for r in log["shots"])      # a range is at least one hex


def small_statistics():
    assert stats_report.percentile([1, 2, 3, 4], 50) == 2.5
    assert stats_report.percentile([5], 90) == 5.0 and stats_report.percentile([], 50) == 0.0
    lo, hi = stats_report.wilson(5, 10)
    assert abs(lo - 0.2366) < 1e-3 and abs(hi - 0.7634) < 1e-3, (lo, hi)
    assert stats_report.wilson(0, 0) == (0.0, 0.0)
    d = stats_report.describe([1, 2, 3, 4, 5])
    assert d["mean"] == 3 and d["median"] == 3 and d["min"] == 1 and d["max"] == 5
    assert stats_report.histogram([1, 1, 2, 4], integer=True) == {"edges": [1, 2, 3, 4, 5], "counts": [2, 1, 0, 1]}


def a_team_battle_analyzes():
    results = team_batch()
    assert all(r.stats for r in results)
    a = stats_report.analyze(results, "check")
    assert a["multi"] and a["n"] == 3 and set(a["team_order"]) == {"Red", "Blue"}
    assert len(a["labels"]) == 4 and set(a["unit"]) == set(a["labels"])
    for t in ("Red", "Blue"):
        x = a["team"][t]
        assert 0 <= x["survivors"]["min"] <= x["survivors"]["max"] <= 2
        c = a["curves"]["team"][t]
        assert len(c["standing_mean"]) == a["curves"]["horizon"] + 1
        assert abs(c["standing_mean"][0] - 2) < 1e-9 and abs(c["force_mean"][0] - 100) < 1e-9     # all standing at the start
    wins = sum(a["outcome"]["wins"][t]["k"] for t in a["team_order"]) + a["outcome"]["draws"]["k"]
    assert wins == 3
    json.dumps(a)                                    # plain data throughout


def the_page_carries_the_analysis():
    a = stats_report.analyze([LOGGED], "check")
    saved = config.STATS_DIR
    path = stats_report.write(a, OUT_DIR)
    config.STATS_DIR = saved
    with open(path, encoding="utf-8") as f:
        page = f.read()
    assert stats_report.DATA_PLACEHOLDER not in page
    blob = re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1)
    assert json.loads(blob.replace("<\\/", "</")) == json.loads(json.dumps(a, default=str))
    assert os.path.exists(path[:-5] + ".json")


CHECKS = [logging_changes_nothing, log_agrees_with_the_result, small_statistics, a_team_battle_analyzes,
          the_page_carries_the_analysis]


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
    print(f"All {len(CHECKS)} statistics checks passed." if not failed
          else f"{failed} of {len(CHECKS)} statistics checks FAILED.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_all())
