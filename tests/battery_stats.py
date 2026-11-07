"""
tests/battery_stats.py - the full statistics page for a battery that was run with
`tests/baseline_battery.py ... --stats` (2026-11-07, Daniel: "don't we have the option to record everything and
generate end of game stats for every unit?" - yes: INTEGRATION__stats records every battle, and this builds the same
page a normal batch makes, from the battles the battery saved).

    python tests/battery_stats.py                 # list the saved sets that have event logs
    python tests/battery_stats.py <name part>     # write stats/<...>.html for the first matching set

Per unit: survival, when and why it died, damage dealt and taken, kills, damage by weapon, shots by range, heat,
criticals; per team: force HP by turn, first kill, focus fire. See INTEGRATION__stats_report for the full list.
"""
import glob
import json
import os
import sys
from types import SimpleNamespace

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("", "pathfinder", "mechsim"):
    sys.path.insert(0, os.path.join(REPO_ROOT, sub))
os.environ.setdefault("INTEGRATION_DATA_DIR", os.path.join(REPO_ROOT, "data"))
SAVED = os.path.join(REPO_ROOT, "run_stats", "baseline", "saved")


def load(set_dir):
    results = []
    for f in sorted(glob.glob(os.path.join(set_dir, "battle_*.json"))):
        try:
            with open(f) as fh:
                row = json.load(fh)
        except (OSError, ValueError):
            continue
        if row.get("stats"):
            results.append(SimpleNamespace(stats=row["stats"], seed=row.get("seed"), winner=row["winner"],
                                           turns_taken=row["turns"], destroyed=row.get("destroyed"),
                                           turn_cap=row.get("turn_cap")))
    return results


def main():
    names = sorted(os.listdir(SAVED)) if os.path.isdir(SAVED) else []
    with_logs = [(n, len(load(os.path.join(SAVED, n)))) for n in names]
    with_logs = [(n, k) for n, k in with_logs if k]
    pattern = sys.argv[1] if len(sys.argv) > 1 else None
    if pattern is None:
        for n, k in with_logs:
            print(f"{k:3d} battles with event logs: {n}")
        if not with_logs:
            print("no saved set has event logs - run baseline_battery.py with --stats")
        return
    match = [(n, k) for n, k in with_logs if pattern in n]
    if not match:
        print(f"no saved set with event logs matches {pattern!r}")
        return
    import INTEGRATION__stats_report as stats_report
    name = match[0][0]
    analysis = stats_report.analyze(load(os.path.join(SAVED, name)), title=name)
    print("Stats page:", stats_report.write(analysis))


if __name__ == "__main__":
    main()
