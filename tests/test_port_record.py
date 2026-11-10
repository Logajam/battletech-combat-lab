"""
tests/test_port_record.py - RUST PORT, STAGE 0 (INTEGRATION__RUST_PORT.md): checks on tools/port_record.py.

1. Recording changes nothing: the same battle played with and without the recorder prints the same log.
2. Recording is repeatable: two recordings of one battle give byte-identical trace, dice tape and units.
3. The trace has no raw memory addresses, and one line per phase, and the tape length matches the last line.
4. port_diff finds a planted difference and names it.

NOT YET (stage 0b, in INTEGRATION__RUST_PORT.md's stage log): the decisions list and its Python self-replay.
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
    env = dict(os.environ, INTEGRATION_DATA_DIR="./data", PYTHONIOENCODING="utf-8")
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
    print()
    print("All port_record checks passed." if not failed else f"{failed} port_record check(s) FAILED.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
