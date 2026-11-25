"""
tests/run_checks.py - the project's checks in one command, chosen by WHAT CHANGED, one line each, then a one-line verdict.

    python tests/run_checks.py            # the checks this change needs (from the files changed since origin/main)
    python tests/run_checks.py --full     # every Rust and website check: ALWAYS before a merge (CLAUDE.md)
    python tests/run_checks.py --list     # print what would run and why, run nothing

Added 2026-10-20 (Claude) after Daniel: "probably need to establish a briefer way to get a clean baseline." Pruned
2026-11-17 (Daniel: "probably time to prune down the suite of tests we use"):

  LEVELS. The files changed since origin/main (committed, staged, unstaged or new) pick the checks:
    docs only (*.md, trial records, licences)             -> nothing to run (says so)
    Combat Lab art (token / shell / reference art files)  -> the three token tests (Daniel, 2026-11-04) + the low-poly
                                                            reference models and block library (test_lowpoly_ref.py)
    Lab pages only (engine/lab/web, engine/wasm/web, ...)  -> the website checks + the Lab server check
    anything else (the engine, tools, checks...)          -> the Rust checks + the website + the Lab server
  --full runs every Rust and website check whatever changed; it is the one to run before a merge.
  THE PYTHON ENGINE was retired (Daniel, 2026-11-11) and removed (2026-11-20, "dead code the python"): its tests, its 15
  reference battles, --python and --bench (its benchmark) went with it. Its answers live on as the frozen answer key
  (engine/answer_key.tar.xz), unpacked into engine/fixtures/ by tools/unpack_answer_key.py before the Rust checks run.
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

ART_TESTS = ["test_token_shell.py", "test_token_joined.py", "test_token_volume.py", "test_lowpoly_ref.py"]


def run_test_file(path, args=()):
    """(passed, seconds, output) for one tests/test_*.py file (or a check script, with its arguments)."""
    start = time.time()
    proc = subprocess.run([sys.executable, path, *args], cwd=REPO_ROOT,
                          capture_output=True, text=True, encoding="utf-8",
                          env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    return proc.returncode == 0, time.time() - start, proc.stdout + proc.stderr


def run_web_checks():
    """The browser build's three checks, one after the other (they share the web_lab/ build): check_web_ui.py (the page as a
    person uses it; it rebuilds web_lab/ when its sources are newer), check_web_lab.py (browser = desktop, battle for
    battle) then check_web_play.py (a person's game in the browser = the desktop's). Exit code 77 = skipped (no node / Playwright / wasm32 target here): reported as a NOTE, not a failure."""
    start, out, ok = time.time(), [], True
    for script, args in (("check_web_ui.py", []), ("check_web_lab.py", ["--battles", "4"]), ("check_web_play.py", []), ("check_web_tabletop.py", [])):
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
    """docs / art / pages / engine for one changed path."""
    name = os.path.basename(path)
    if path.startswith(("trial_records/", "licenses/")) or path.endswith(".md") or name in ("LICENSE", "THIRD_PARTY_LICENSES.txt"):
        return "docs"
    if path.startswith(("reference_art/", "tools/token_", "tools/lowpoly_")) or name in ART_TESTS \
            or name.startswith(("INTEGRATION__token", "INTEGRATION__shell", "INTEGRATION__structure_table")) or name == "test_lowpoly_ref.py":
        return "art"
    if path.startswith(("engine/lab/web/", "engine/wasm/web/")) or path in (
            "tools/build_web_lab.py", "tools/make_lab_demo.py", "tools/publish_web_lab.py", "tests/check_web_ui.py", "tests/check_web_lab.py", "tests/check_web_play.py", "tests/check_web_tabletop.py"):
        return "pages"
    return "engine"


def plan(argv):
    """(what to run: a set of 'art' / 'pages' / 'engine', the reasons in words)."""
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
    if "engine" in want:
        want.add("pages")          # an engine change reaches the Lab and the website too
    return want, why


def main(argv):
    start = time.time()
    want, why = plan(argv)
    print("Checks chosen by what changed:\n  " + "\n  ".join(why))
    light, heavy = [], []      # (label, function, args)
    if "art" in want:
        light += [(f"test       {t}", run_test_file, (os.path.join(REPO_ROOT, "tests", t),)) for t in ART_TESTS if os.path.exists(os.path.join(REPO_ROOT, "tests", t))]
    has_cargo = shutil.which("cargo") is not None
    if want & {"engine", "pages"} and not has_cargo:
        print("NOTE: no cargo on this machine - the Rust and website checks were not run")
    if "engine" in want and has_cargo:
        # the Rust engine's own reference battles, then the MegaMek bridge's quick parity check (B1)
        heavy.append(("rust       check_rust_reference.py (the reference list, 68 battles)",
                      run_test_file, (os.path.join(REPO_ROOT, "tests", "check_rust_reference.py"),)))
        heavy.append(("rust       check_bridge_parity.py --quick",
                      run_test_file, (os.path.join(REPO_ROOT, "tests", "check_bridge_parity.py"), ["--quick"])))
        # the event records and their search (INTEGRATION__EVENTS.md): events change nothing, known events appear, the search works
        heavy.append(("rust       check_events.py",
                      run_test_file, (os.path.join(REPO_ROOT, "tests", "check_events.py"),)))
        # CL1 settings, stage-6 attach, CL2 histories, BV skills, charge targets, walk-on zones
        heavy.append(("rust       cargo test cl1_setup + stage6_attach + cl2_history + bv_skills + charge_targets + zone_entry + human_bots + play_session + step_walk + drawn_route + core unit tests",
                      run_command, (["cargo", "test", "--release", "-q", "-p", "btsim_core", "--lib", "--test", "cl1_setup", "--test", "stage6_attach", "--test", "cl2_history",
                                     "--test", "bv_skills", "--test", "charge_targets", "--test", "zone_entry", "--test", "human_bots", "--test", "play_session", "--test", "step_walk", "--test", "drawn_route"], os.path.join(REPO_ROOT, "engine"))))
    if want & {"engine", "pages"} and has_cargo:
        # Combat Lab CL3: the Lab server, driven by a script, gives btsim's battles for the same setup and seed
        heavy.append(("rust       check_bv_megamek.py",
                      run_test_file, (os.path.join(REPO_ROOT, "tests", "check_bv_megamek.py"), [])))
        heavy.append(("rust       check_lab_server.py --battles 4",
                      run_test_file, (os.path.join(REPO_ROOT, "tests", "check_lab_server.py"), ["--battles", "4"])))
        # BattleROM play: the Lab's play calls, a script playing one team (INTEGRATION__PLAYER_DECISIONS.md Section 15)
        heavy.append(("rust       check_play.py",
                      run_test_file, (os.path.join(REPO_ROOT, "tests", "check_play.py"), [])))
        # Combat Lab in the browser: the website clicked through, and the browser v the desktop
        heavy.append(("web        check_web_ui.py + check_web_lab.py --battles 4 + check_web_play.py + check_web_tabletop.py", run_web_checks, ()))
    if not light and not heavy:
        print("\nNothing to run for this change.")
        return 0
    if "--list" in argv:
        print("\nWould run:\n  " + "\n  ".join(label for label, _, _ in heavy + light))
        return 0
    if want & {"engine", "pages"} and has_cargo:
        # the frozen answer key (the retired Python's recordings) must be unpacked before any Rust check reads it
        subprocess.run([sys.executable, os.path.join(REPO_ROOT, "tools", "unpack_answer_key.py")], cwd=REPO_ROOT, check=True)
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
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
