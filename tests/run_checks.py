"""
tests/run_checks.py - the project's checks in one command, chosen by WHAT CHANGED, one line each, then a one-line verdict.

    python tests/run_checks.py            # the checks this change needs (from the files changed since origin/main)
    python tests/run_checks.py --full     # every Rust and website check: ALWAYS before a merge (CLAUDE.md)
    python tests/run_checks.py --python   # ... plus the retired Python's tests and reference battles (once a week)
    python tests/run_checks.py --list     # print what would run and why, run nothing
    python tests/run_checks.py --bench    # ... then the 10-turn benchmark (Python), alone at the end

Added 2026-10-20 (Claude) after Daniel: "probably need to establish a briefer way to get a clean baseline." Pruned
2026-11-17 (Daniel: "probably time to prune down the suite of tests we use"):

  LEVELS. The files changed since origin/main (committed, staged, unstaged or new) pick the checks:
    docs only (*.md, trial records, licences)             -> nothing to run (says so)
    Combat Lab art (token / shell / reference art files)  -> the three token tests (Daniel, 2026-11-04)
    Lab pages only (engine/lab/web, engine/wasm/web, ...)  -> the website checks + the Lab server check
    the Python (INTEGRATION__*.py, mechsim/, ...)        -> the Python tests and Python reference battles
    anything else (the engine, tools, checks...)          -> the Rust checks + the website + the Lab server
  --full runs every Rust and website check whatever changed; it is the one to run before a merge.
  THE PYTHON is retired (Daniel, 2026-11-11) and frozen: its test files and 15 reference battles guard code nobody changes
  now, so they run only when a Python file changed, or with --python (weekly: the first session of the week).
  ONE RUN, TWO CHECKS - TRIED, NOT KEPT: playing the Rust reference battles under the bridge's parity check
  (check_rust_reference.py --parity) took 434 s, against 71 s for the plain reference run plus 108 s for
  check_bridge_parity.py --quick (which skips the 8 v 8 / 12 v 12 battles and stops at turn 15). The parity check is the
  costly half, so the two stay separate; --parity remains for a thorough run (every battle in full under parity).
  SMALLER COUNTS: the Lab server compares 4 battles a setup (was 8); the website parity check 4.
  FEWER AT ONCE: the heavy checks (each of which already uses every core) run one after another; only the light Python
  checks run side by side. Before, they all ran together and fought over the cores.

Every check runs in its own process, so how they are scheduled changes no result. A failing check's output is printed
under its line. The benchmark runs last and alone, because its time only means something on a quiet machine.
"""

import glob
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))

ART_TESTS = ["test_token_shell.py", "test_token_joined.py", "test_token_volume.py"]


def run_test_file(path, args=()):
    """(passed, seconds, output) for one tests/test_*.py file (or a check script, with its arguments)."""
    start = time.time()
    proc = subprocess.run([sys.executable, path, *args], cwd=REPO_ROOT,
                          capture_output=True, text=True, encoding="utf-8",
                          env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    return proc.returncode == 0, time.time() - start, proc.stdout + proc.stderr


def run_web_checks():
    """The browser build's two checks, one after the other (they share the web_lab/ build): check_web_ui.py (the page as a
    person uses it; it rebuilds web_lab/ when its sources are newer) then check_web_lab.py (browser = desktop, battle for
    battle). Exit code 77 = skipped (no node / Playwright / wasm32 target here): reported as a NOTE, not a failure."""
    start, out, ok = time.time(), [], True
    for script, args in (("check_web_ui.py", []), ("check_web_lab.py", ["--battles", "4"])):
        proc = subprocess.run([sys.executable, os.path.join(REPO_ROOT, "tests", script), *args], cwd=REPO_ROOT,
                              capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        if proc.returncode == 77:
            out.append(f"NOTE: {script} skipped - " + (proc.stdout.strip().splitlines() or ["?"])[-1])
            break
        ok = ok and proc.returncode == 0
        out.append(proc.stdout + proc.stderr)
    return ok, time.time() - start, "\n".join(out)


def run_command(cmd, cwd):
    """(passed, seconds, output) for any command."""
    start = time.time()
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    return proc.returncode == 0, time.time() - start, proc.stdout + proc.stderr


def run_reference(name, overrides):
    """(matched, seconds, report) for one Python reference battle."""
    import check_reference_logs
    start = time.time()
    try:
        matched, lines = check_reference_logs.compare(name, check_reference_logs.run_scenario(overrides))
    except RuntimeError as crash:
        matched, lines = False, [str(crash)]
    return matched, time.time() - start, "\n".join(lines)


# ---------------------------------------------------------------- what changed
def changed_files():
    """Paths changed since origin/main: committed on this branch, staged, unstaged, or new. None when git can't say."""
    def git(*a):
        p = subprocess.run(["git", *a], cwd=REPO_ROOT, capture_output=True, text=True)
        return p.stdout.splitlines() if p.returncode == 0 else None
    base = git("merge-base", "HEAD", "origin/main")
    if not base:
        return None
    files = set()
    for args in (("diff", "--name-only", base[0], "HEAD"), ("diff", "--name-only", "HEAD"), ("ls-files", "--others", "--exclude-standard")):
        got = git(*args)
        if got is None:
            return None
        files.update(f for f in got if f)
    return sorted(files)


def kind_of(path):
    """docs / art / pages / python / engine for one changed path."""
    name = os.path.basename(path)
    if path.startswith(("trial_records/", "licenses/")) or path.endswith(".md") or name in ("LICENSE", "THIRD_PARTY_LICENSES.txt"):
        return "docs"
    if path.startswith(("reference_art/", "tools/token_", "tools/lowpoly_")) or name in ART_TESTS \
            or name.startswith(("INTEGRATION__token", "INTEGRATION__shell")) or name == "test_lowpoly_ref.py":
        return "art"
    if path.startswith(("engine/lab/web/", "engine/wasm/web/")) or path in (
            "tools/build_web_lab.py", "tools/make_lab_demo.py", "tests/check_web_ui.py", "tests/check_web_lab.py"):
        return "pages"
    if (name.startswith("INTEGRATION__") and name.endswith((".py", ".html"))) \
            or path.startswith(("mechsim/", "pathfinder/", "fastcore/", "reference_logs/")) \
            or (path.startswith("tests/") and name.startswith("test_")) \
            or path in ("tests/check_reference_logs.py", "tests/benchmark_turns.py"):
        return "python"
    return "engine"


def plan(argv):
    """(what to run: a set of 'art' / 'pages' / 'python' / 'engine', the reasons in words)."""
    want, why = set(), []
    if "--full" in argv:
        want |= {"engine", "pages"}
        why.append("--full: every Rust and website check")
    else:
        files = changed_files()
        if files is None:
            want |= {"engine", "pages"}
            why.append("git could not compare with origin/main: every Rust and website check")
        elif not files:
            why.append("nothing changed since origin/main")
        else:
            kinds = {}
            for f in files:
                kinds.setdefault(kind_of(f), []).append(f)
            for k, fs in sorted(kinds.items()):
                why.append(f"{k}: {len(fs)} file(s), e.g. {', '.join(fs[:3])}")
            want |= set(kinds) - {"docs"}
    if "--python" in argv:
        want.add("python")
        why.append("--python: the retired Python's tests and reference battles")
    if "engine" in want:
        want.add("pages")          # an engine change reaches the Lab and the website too
    return want, why


def main(argv):
    start = time.time()
    want, why = plan(argv)
    print("Checks chosen by what changed:\n  " + "\n  ".join(why))
    light, heavy = [], []      # (label, function, args)
    if "python" in want:
        import check_reference_logs
        light += [(f"reference  {name}", run_reference, (name, overrides)) for name, overrides in check_reference_logs.SCENARIOS.items()]
        light += [(f"test       {os.path.basename(p)}", run_test_file, (p,)) for p in sorted(glob.glob(os.path.join(REPO_ROOT, "tests", "test_*.py")))]
    elif "art" in want:
        light += [(f"test       {t}", run_test_file, (os.path.join(REPO_ROOT, "tests", t),)) for t in ART_TESTS if os.path.exists(os.path.join(REPO_ROOT, "tests", t))]
    has_cargo = shutil.which("cargo") is not None
    if want & {"engine", "pages"} and not has_cargo:
        print("NOTE: no cargo on this machine - the Rust and website checks were not run")
    if "engine" in want and has_cargo:
        # the Rust engine's own reference battles, then the MegaMek bridge's quick parity check (B1)
        heavy.append(("rust       check_rust_reference.py (86 battles)",
                      run_test_file, (os.path.join(REPO_ROOT, "tests", "check_rust_reference.py"),)))
        heavy.append(("rust       check_bridge_parity.py --quick",
                      run_test_file, (os.path.join(REPO_ROOT, "tests", "check_bridge_parity.py"), ["--quick"])))
        # CL1 settings, stage-6 attach, CL2 histories, BV skills, charge targets, walk-on zones
        heavy.append(("rust       cargo test cl1_setup + stage6_attach + cl2_history + bv_skills + charge_targets + zone_entry",
                      run_command, (["cargo", "test", "--release", "-q", "--test", "cl1_setup", "--test", "stage6_attach", "--test", "cl2_history",
                                     "--test", "bv_skills", "--test", "charge_targets", "--test", "zone_entry"], os.path.join(REPO_ROOT, "engine"))))
    if want & {"engine", "pages"} and has_cargo:
        # Combat Lab CL3: the Lab server, driven by a script, gives btsim's battles for the same setup and seed
        heavy.append(("rust       check_lab_server.py --battles 4",
                      run_test_file, (os.path.join(REPO_ROOT, "tests", "check_lab_server.py"), ["--battles", "4"])))
        # Combat Lab in the browser: the website clicked through, and the browser v the desktop
        heavy.append(("web        check_web_ui.py + check_web_lab.py --battles 4", run_web_checks, ()))
    if not light and not heavy:
        print("\nNothing to run for this change.")
        return 0
    if "--list" in argv:
        print("\nWould run:\n  " + "\n  ".join(label for label, _, _ in heavy + light))
        return 0
    # the heavy checks (each already using every core) one at a time; the light ones side by side alongside them
    failed = 0
    with ThreadPoolExecutor(max_workers=1) as one, ThreadPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1)) as pool:
        jobs = [(label, one.submit(fn, *args)) for label, fn, args in heavy]
        jobs += [(label, pool.submit(fn, *args)) for label, fn, args in light]
        print()
        for label, job in jobs:
            ok, seconds, output = job.result()
            print(f"{'PASS' if ok else 'FAIL'}  {seconds:5.1f}s  {label}", flush=True)
            if not ok:
                failed += 1
                print("    " + output.strip().replace("\n", "\n    "))
            elif "NOTE:" in output:                # a reference battle that hit its turn cap, a skipped web check...
                print("\n".join(l for l in output.splitlines() if "NOTE:" in l))
    print()
    print(f"{len(jobs) - failed} of {len(jobs)} checks passed in {time.time() - start:.0f} s."
          + ("" if not failed else f"  {failed} FAILED."))
    if "--bench" in argv:
        print()
        subprocess.run([sys.executable, os.path.join(REPO_ROOT, "tests", "benchmark_turns.py")], cwd=REPO_ROOT)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
