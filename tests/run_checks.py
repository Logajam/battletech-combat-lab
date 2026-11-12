"""
tests/run_checks.py - the whole clean-baseline check in one command: every
tests/test_*.py file and every reference battle, run side by side (one per
CPU core), one line each, then a one-line verdict.

    python tests/run_checks.py          # all tests + reference logs
    python tests/run_checks.py --bench  # ... then the 10-turn benchmark

Added 2026-10-20 (Claude) after Daniel: "probably need to establish a briefer
way to get a clean baseline." Run one at a time, the checks took about 5
minutes in the cloud container; side by side, about 1.5. Every check runs in its
own process, so running them together changes no result. A failing check's
own output is printed under its line. The benchmark runs last and alone,
because its time only means something on a quiet machine.
"""

import glob
import shutil
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))

import check_reference_logs  # noqa: E402


def run_test_file(path, args=()):
    """(passed, seconds, output) for one tests/test_*.py file (or a check script, with its arguments)."""
    start = time.time()
    proc = subprocess.run([sys.executable, path, *args], cwd=REPO_ROOT,
                          capture_output=True, text=True, encoding="utf-8",
                          env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    return proc.returncode == 0, time.time() - start, proc.stdout + proc.stderr


def run_command(cmd, cwd):
    """(passed, seconds, output) for any command."""
    start = time.time()
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    return proc.returncode == 0, time.time() - start, proc.stdout + proc.stderr


def run_reference(name, overrides):
    """(matched, seconds, report) for one reference battle."""
    start = time.time()
    try:
        matched, lines = check_reference_logs.compare(
            name, check_reference_logs.run_scenario(overrides))
    except RuntimeError as crash:
        matched, lines = False, [str(crash)]
    return matched, time.time() - start, "\n".join(lines)


def main():
    start = time.time()
    tests = sorted(glob.glob(os.path.join(REPO_ROOT, "tests", "test_*.py")))
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 1) as pool:
        # Reference battles first: they're the slow ones, so starting them
        # early keeps every core busy to the end.
        jobs = [(f"reference  {name}", pool.submit(run_reference, name, overrides))
                for name, overrides in check_reference_logs.SCENARIOS.items()]
        jobs += [(f"test       {os.path.basename(path)}", pool.submit(run_test_file, path))
                 for path in tests]
        # The Rust engine's own reference battles (session 25; tests/check_rust_reference.py), when cargo is here.
        if shutil.which("cargo"):
            jobs.append(("rust       check_rust_reference.py (86 battles)",
                         pool.submit(run_test_file, os.path.join(REPO_ROOT, "tests", "check_rust_reference.py"))))
            # the MegaMek bridge's decision process gives the battles' own answers (B1; INTEGRATION__MEGAMEK_BRIDGE.md)
            jobs.append(("rust       check_bridge_parity.py --quick",
                         pool.submit(run_test_file, os.path.join(REPO_ROOT, "tests", "check_bridge_parity.py"), ["--quick"])))
            # Combat Lab CL1: every fixture's scenario built by Rust from its settings equals the Python-built one;
            # CL2: every fixture's Rust battle history equals the Python's replay record of it
            jobs.append(("rust       cargo test cl1_setup + stage6_attach + cl2_history",
                         pool.submit(run_command, ["cargo", "test", "--release", "-q", "--test", "cl1_setup", "--test", "stage6_attach", "--test", "cl2_history"],
                                     os.path.join(REPO_ROOT, "engine"))))
            # Combat Lab CL3: the Lab server, driven by a script, gives btsim's battles for the same setup and seed
            jobs.append(("rust       check_lab_server.py --battles 8",
                         pool.submit(run_test_file, os.path.join(REPO_ROOT, "tests", "check_lab_server.py"), ["--battles", "8"])))
        else:
            print("NOTE: no cargo on this machine - the Rust reference battles were not run")
        failed = 0
        for label, job in jobs:
            ok, seconds, output = job.result()
            print(f"{'PASS' if ok else 'FAIL'}  {seconds:5.1f}s  {label}")
            if not ok:
                failed += 1
                print("    " + output.strip().replace("\n", "\n    "))
            elif "NOTE:" in output:                # e.g. a reference battle that hit its turn cap
                print("\n".join(l for l in output.splitlines() if "NOTE:" in l))
    print()
    print(f"{len(jobs) - failed} of {len(jobs)} checks passed in {time.time() - start:.0f} s."
          + ("" if not failed else f"  {failed} FAILED."))
    if "--bench" in sys.argv[1:]:
        print()
        subprocess.run([sys.executable, os.path.join(REPO_ROOT, "tests", "benchmark_turns.py")],
                       cwd=REPO_ROOT)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
