"""
tools/port_fixtures.py - record (and self-replay) every fixture battle of the Rust port.

    python tools/port_fixtures.py                    # all scenarios of tools/port_scenarios.py -> engine/fixtures/
    python tools/port_fixtures.py NAME [NAME ...]    # only these
    python tools/port_fixtures.py --out DIR          # another folder
    python tools/port_fixtures.py --no-replay        # skip the Python self-replay check

Each scenario is recorded by tools/port_record.py in its own process (side by side, one per core), then replayed
from its dice tape and decisions with the bots off, and the two traces and stdout logs are compared: a fixture
that does not replay is a decision missing from the list, and is reported as FAIL. A fixture that replays also
gets the Python's replay record (replay.json, Combat Lab CL2's answer key). engine/fixtures is git-ignored
(the 12 v 12 traces are 80 MB): recording is byte-for-byte repeatable, so any session can rebuild it in a few
minutes. The comparison tools and the Rust tests read these folders.
"""
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
import port_diff  # noqa: E402
import port_scenarios  # noqa: E402


def one(name, out, replay=True):
    env = dict(os.environ, INTEGRATION_DATA_DIR="./data", PYTHONIOENCODING="utf-8", PYTHONHASHSEED="0")
    start = time.time()
    folder = os.path.join(out, name)
    proc = subprocess.run([sys.executable, "tools/port_record.py", "--scenario", name, folder],
                          cwd=REPO_ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode:
        return name, False, time.time() - start, "RECORD FAILED\n" + proc.stderr[-1500:]
    if not replay:
        return name, True, time.time() - start, "recorded"
    again = folder + ".replay"
    proc = subprocess.run([sys.executable, "tools/port_record.py", "--replay", folder, again],
                          cwd=REPO_ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode:
        return name, False, time.time() - start, "REPLAY FAILED\n" + proc.stderr[-1500:]
    diff = subprocess.run([sys.executable, "tools/port_diff.py", os.path.join(folder, "trace.jsonl"),
                           os.path.join(again, "trace.jsonl")], cwd=REPO_ROOT, capture_output=True, text=True)
    same_log = _stdout(os.path.join(folder, "log.txt")) == _stdout(os.path.join(again, "log.txt"))
    for f in os.listdir(again):
        os.remove(os.path.join(again, f))
    os.rmdir(again)
    if diff.returncode or not same_log:
        return name, False, time.time() - start, "replay differs:\n" + diff.stdout + ("" if same_log else "log differs")
    # Combat Lab CL2's answer key: the Python's replay record of the battle (replay.json; engine/core/tests/cl2_history.rs)
    proc = subprocess.run([sys.executable, "tools/port_record.py", "--replay-data", folder],
                          cwd=REPO_ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode:
        return name, False, time.time() - start, "REPLAY DATA FAILED\n" + proc.stderr[-1500:]
    return name, True, time.time() - start, diff.stdout.strip()


def _stdout(path):
    """The whole log (stdout, then the stub warnings of stderr): a replay must reproduce both."""
    with open(path, encoding="utf-8") as f:
        return port_diff.normalize_log(f.read())


def main(argv):
    out = os.path.join(REPO_ROOT, "engine", "fixtures")
    replay = "--no-replay" not in argv
    if "--out" in argv:
        out = os.path.abspath(argv[argv.index("--out") + 1])
    names = [a for a in argv if a in port_scenarios.SCENARIOS] or list(port_scenarios.SCENARIOS)
    os.makedirs(out, exist_ok=True)
    failed = 0
    # the long ones first, so every core stays busy to the end
    names.sort(key=lambda n: -port_scenarios.SCENARIOS[n][1] * (3 if n.startswith("team_12") else 1))
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 1) as pool:
        jobs = [pool.submit(one, n, out, replay) for n in names]
        for job in jobs:
            name, ok, secs, note = job.result()
            failed += not ok
            print(f"{'PASS' if ok else 'FAIL'} {secs:6.1f}s  {name}: {note}", flush=True)
    print(f"\n{len(names) - failed} of {len(names)} fixtures recorded" + (" and replayed." if replay else "."))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
