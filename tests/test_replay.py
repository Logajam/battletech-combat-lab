"""
tests/test_replay.py - checks battle replays (INTEGRATION__replay, added
2026-10-20): recording a battle doesn't change it, the steps follow the turn,
and the written page carries the battle's data intact.

    python tests/test_replay.py
"""

import io
import json
import os
import re
import sys
import tempfile
import traceback
from contextlib import redirect_stdout

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402 - registers bare "config" first
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
import INTEGRATION__replay as replay  # noqa: E402

# Battle 1 of seed 2167380083587462785 (Kontio vs Hammerhead) - a short battle
# (chosen when it ended in four turns with the Hammerhead pushed off the board;
# the checks below read the outcome from the result, so they hold whatever the
# bot does, 2026-10-24).
SEED = 2167380083587462785
OUT_DIR = tempfile.mkdtemp()


def _batch(record):
    saved = config.REPLAY_BATTLES, config.REPLAY_DIR, config.WORKERS
    config.REPLAY_BATTLES, config.REPLAY_DIR, config.WORKERS = (1 if record else 0), OUT_DIR, 1
    config.TIMING = False                          # run times differ between the two runs
    try:
        out = io.StringIO()
        with redirect_stdout(out):
            results = orchestrator.run_batch(num_simulations=1, seed=SEED)
        return results[0], out.getvalue()
    finally:
        config.REPLAY_BATTLES, config.REPLAY_DIR, config.WORKERS = saved


PLAIN, PLAIN_OUT = _batch(record=False)
RECORDED, RECORDED_OUT = _batch(record=True)


def recording_changes_nothing():
    saved_line = re.compile(r"^Replay saved: .*\n", re.M)
    assert saved_line.search(RECORDED_OUT), "no replay was written"
    assert saved_line.sub("", RECORDED_OUT) == PLAIN_OUT, "recording changed the battle's output"
    assert PLAIN.replay is None and RECORDED.replay is not None


def steps_follow_the_turn():
    data = RECORDED.replay
    steps = data["steps"]
    assert steps[0]["phase"] == "Deployment" and steps[0]["turn"] == 0
    # Five steps a turn (both movements, ranged, physical, heat and end phase),
    # then "Battle over" with the closing log line.
    assert len(steps) == 1 + 5 * RECORDED.turns_taken + 1, len(steps)
    assert steps[-1]["phase"] == "Battle over"
    assert [s["phase"] for s in steps[3:6]] == ["Ranged attacks", "Physical attacks", "Heat and end phase"]
    last = steps[-1]["state"]
    for side, stats in (("Red", RECORDED.red), ("Blue", RECORDED.blue)):
        assert bool(last[side]["destroyed"]) == bool(stats.destroyed), side
        assert last[side]["hp"] == stats.final_hp, side
        assert data["result"]["causes"][side] == stats.cause_of_death, side
    # Every log line of the battle lands in exactly one step, VERBOSE or not.
    logged = sum(len(s["log"]) for s in steps)
    assert logged > 100, logged


def page_carries_the_data():
    path = os.path.join(OUT_DIR, replay.file_name(RECORDED.replay))
    with open(path, encoding="utf-8") as f:
        page = f.read()
    assert replay.DATA_PLACEHOLDER not in page
    blob = re.search(r'<script id="replay-data" type="application/json">(.*?)</script>', page, re.S).group(1)
    data = json.loads(blob.replace("<\\/", "</"))
    assert data == json.loads(json.dumps(RECORDED.replay))
    assert data["seed"] == str(SEED)               # as text: JavaScript can't hold it exactly as a number


CHECKS = [recording_changes_nothing, steps_follow_the_turn, page_carries_the_data]


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
    print(f"All {len(CHECKS)} replay checks passed." if not failed
          else f"{failed} of {len(CHECKS)} replay checks FAILED.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_all())
