"""
tests/test_port_record.py - RUST PORT, STAGE 0 (INTEGRATION__RUST_PORT.md): checks on tools/port_record.py.

1. Recording changes nothing: the same battle played with and without the recorder prints the same log.
2. Recording is repeatable: two recordings of one battle give byte-identical trace, dice tape and units.
3. The trace has no raw memory addresses, and one line per phase, and the tape length matches the last line.
4. port_diff finds a planted difference and names it.

5. The Python self-replay (stage 0b): a recorded battle played again from dice.json + decisions.json alone, no bot
   thinking, gives the same trace, dice position, log and stub warnings - so the decision list is complete. A few
   quick fixtures here (a duel, a missile duel, a 4 v 4 of Princess, a melee); `python tools/port_fixtures.py`
   does all 48.
"""
import json
import os
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))
import check_reference_logs  # noqa: E402

NAME = "Kontio_vs_Hammerhead_seed12345.txt"


def record(out_dir):
    env = dict(os.environ, INTEGRATION_DATA_DIR="./data", PYTHONIOENCODING="utf-8", PYTHONHASHSEED="0")
    subprocess.run([sys.executable, "tools/port_record.py", "--reference", NAME, out_dir],
                   cwd=REPO_ROOT, env=env, check=True, capture_output=True)


def read(d, name):
    with open(os.path.join(d, name), encoding="utf-8") as f:
        return f.read()


def main():
    failed = 0
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        record(a)
        record(b)
        plain = check_reference_logs.run_scenario(check_reference_logs.SCENARIOS[NAME])

        def check(label, ok):
            nonlocal failed
            print(("PASS  " if ok else "FAIL  ") + label)
            failed += not ok
        check("recorded log == unrecorded log", read(a, "log.txt") == plain)
        for f in ("trace.jsonl", "dice.json", "units.json", "board.json", "log.txt"):
            check(f"two recordings give the same {f}", read(a, f) == read(b, f))
        trace = [json.loads(line) for line in read(a, "trace.jsonl").splitlines()]
        check("no raw addresses in the trace", "ADDRESS?" not in read(a, "trace.jsonl"))
        check("trace starts at Deployment", trace[0]["phase"] == "Deployment")
        check("dice used is non-decreasing and ends at the tape length",
              all(x["dice_used"] <= y["dice_used"] for x, y in zip(trace, trace[1:]))
              and trace[-1]["dice_used"] == len(json.loads(read(a, "dice.json"))))
        bad = read(a, "trace.jsonl").replace('"facing": "', '"facing": "X', 1)
        with open(os.path.join(b, "bad.jsonl"), "w", encoding="utf-8") as f:
            f.write(bad)
        proc = subprocess.run([sys.executable, "tools/port_diff.py", os.path.join(a, "trace.jsonl"),
                               os.path.join(b, "bad.jsonl")], cwd=REPO_ROOT, capture_output=True, text=True)
        check("port_diff names a planted difference", proc.returncode == 1 and "FIRST DIFFERENCE" in proc.stdout)
    sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
    import port_fixtures
    with tempfile.TemporaryDirectory() as out:
        for name in ("ref_Atlas_AS7-K_vs_Archer_ARC-2R_seed2", "ref_Kintaro_KTO-19_vs_Atlas_AS7-K_seed2",
                     "team_4v4_princess_v_princess", "cov_melee_mace_sword"):
            _, ok, _, note = port_fixtures.one(name, out)
            print(("PASS  " if ok else "FAIL  ") + f"self-replay of {name}: {note.splitlines()[0]}")
            failed += not ok
    print()
    print("All port_record checks passed." if not failed else f"{failed} port_record check(s) FAILED.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
