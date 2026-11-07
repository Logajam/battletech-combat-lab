"""
tests/battery_summary.py - the table for batteries run with tests/baseline_battery.py (2026-11-07).

    python tests/battery_summary.py                      # every saved set under run_stats/baseline/saved/
    python tests/battery_summary.py order                # only sets whose name contains "order"
    python tests/battery_summary.py --log a.txt b.txt    # battle lines of old console logs (before saving existed); the files are one set

One line a set of battles: how many, wins for each side, draws, the average 'Mechs left and damage dealt per
side, and turns. Battles are the ones baseline_battery.py saved as it ran (`run_stats/baseline/saved/<settings>/
battle_NNN.json`), so a set that was cut off by a restart still shows what finished.
"""

import glob
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVED = os.path.join(REPO_ROOT, "run_stats", "baseline", "saved")

LOG_LINE = re.compile(r"^\s+battle (\d+): (\w+) after (\d+) turns.*?\| (.*) \| (\d+) s")
TEAM = re.compile(r"(\w+): (\d+)/12 left, HP (\d+)/(\d+), dealt (\d+)")


def rows_from_dir(path):
    rows = []
    for f in sorted(glob.glob(os.path.join(path, "battle_*.json"))):
        try:
            with open(f) as fh:
                rows.append(json.load(fh))
        except (OSError, ValueError):
            pass                                  # half-written: ignore
    return rows


def rows_from_logs(paths):
    rows = {}
    for path in paths:
        with open(path) as fh:
            for line in fh:
                m = LOG_LINE.match(line)
                if not m:
                    continue
                teams = {t: (int(a), int(hp), int(mx), int(d)) for t, a, hp, mx, d in TEAM.findall(m.group(4))}
                rows[int(m.group(1))] = {"battle": int(m.group(1)), "winner": m.group(2), "turns": int(m.group(3)),
                                         "teams": teams}
    return [rows[k] for k in sorted(rows)]


def summarize(name, rows):
    if not rows:
        return None
    sides = sorted({t for r in rows for t in r["teams"]})
    wins = {t: sum(1 for r in rows if r["winner"] == t) for t in sides}
    draws = sum(1 for r in rows if r["winner"] not in sides)
    n = len(rows)
    left = {t: sum(r["teams"][t][0] for r in rows) / n for t in sides}
    dealt = {t: sum(r["teams"][t][3] for r in rows) / n for t in sides}
    turns = sum(r["turns"] for r in rows) / n
    return (f"{name}\n    {n} battles | " + " / ".join(f"{t} {wins[t]}" for t in sides) + f" / draws {draws}"
            + " | left " + " / ".join(f"{left[t]:.2f}" for t in sides)
            + " | dealt " + " / ".join(f"{dealt[t]:.0f}" for t in sides) + f" | {turns:.1f} turns")


def main():
    args = sys.argv[1:]
    if args and args[0] == "--log":
        # all the files given are ONE set (a battery cut off by a restart and run again leaves several logs)
        print(summarize(os.path.basename(args[1]), rows_from_logs(args[1:])) or "no battle lines")
        return
    pattern = args[0] if args else ""
    names = sorted(d for d in os.listdir(SAVED) if pattern in d) if os.path.isdir(SAVED) else []
    if not names:
        print("no saved batteries" + (f" matching {pattern!r}" if pattern else ""))
        return
    for name in names:
        print(summarize(name, rows_from_dir(os.path.join(SAVED, name))))


if __name__ == "__main__":
    main()
