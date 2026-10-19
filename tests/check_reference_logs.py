"""
tests/check_reference_logs.py - re-runs each reference battle and compares
it with its saved log in reference_logs/. Same seed + same code should give
a byte-identical log, so any difference means a change altered results.

    python tests/check_reference_logs.py            # compare
    python tests/check_reference_logs.py --update   # rewrite the saved logs

Use --update only when a change is SUPPOSED to alter results (a new rule,
a data fix), and say so in the PROJECT_MAP change record.

Added 2026-10-19 (Claude). Each scenario is INTEGRATION__config's defaults
plus the overrides listed below. Battles run in a child process from the
repo root with INTEGRATION_DATA_DIR=./data, so the paths printed in the
log are the same on every machine.

Log format: "# stdout", the battle's stdout, a blank line,
"# stderr (stub warnings)", then its stderr.
"""

import difflib
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(REPO_ROOT, "reference_logs")

# file name -> config overrides (Python statements run after
# `import INTEGRATION__config as config`, before the batch starts)
SCENARIOS = {
    "Asymptote_vs_Asymptote_seed12345.txt": [],
    "Asymptote_vs_Synthetic_maxheat8_seed777.txt": [
        'config.MECH_BLUE_MTF = "TEST_Synthetic_Loadout.mtf"',
        "config.SEED = 777",
        'config.MECH_RED_CONFIG["max_heat"] = 8',
        'config.MECH_BLUE_CONFIG["max_heat"] = 8',
    ],
    # Added 2026-10-19 for the Heat Scale: max_heat 30 lets the synthetic
    # mech overheat - shutdown, a heat ammo explosion, an auto-failed PSR
    # while shut down, and an automatic restart all happen in this battle.
    "Asymptote_vs_Synthetic_maxheat30_seed2.txt": [
        'config.MECH_BLUE_MTF = "TEST_Synthetic_Loadout.mtf"',
        "config.SEED = 2",
        'config.MECH_RED_CONFIG["max_heat"] = 30',
        'config.MECH_BLUE_CONFIG["max_heat"] = 30',
    ],
    # Added 2026-10-19 for heat equipment: TEST_Heat_Gear carries TSM (so
    # min_heat 9), MASC, a supercharger, a radical heat sink system, coolant
    # pods, a Chameleon LPS, inferno ammo and a torso-mounted cockpit.
    # Default heat settings: TSM pins it at 9 heat, sinks switch on and off.
    "Asymptote_vs_HeatGear_seed5.txt": [
        'config.MECH_BLUE_MTF = "TEST_Heat_Gear.mtf"',
        "config.SEED = 5",
    ],
    # max_heat 30: coolant pods, shutdown, and an inferno ammo explosion.
    "Asymptote_vs_HeatGear_maxheat30_seed2.txt": [
        'config.MECH_BLUE_MTF = "TEST_Heat_Gear.mtf"',
        "config.SEED = 2",
        'config.MECH_RED_CONFIG["max_heat"] = 30',
        'config.MECH_BLUE_CONFIG["max_heat"] = 30',
    ],
}


def run_scenario(overrides):
    code = "\n".join(
        ["import INTEGRATION__config as config"]
        + overrides
        + ["import INTEGRATION__orchestrator as orchestrator", "orchestrator.run_batch()"]
    )
    env = dict(os.environ, INTEGRATION_DATA_DIR="./data", PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO_ROOT, env=env,
        capture_output=True, text=True, encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"battle crashed (exit {proc.returncode}):\n{proc.stderr[-2000:]}")
    return f"# stdout\n{proc.stdout}\n# stderr (stub warnings)\n{proc.stderr}"


def main():
    update = "--update" in sys.argv[1:]
    failures = 0
    for name, overrides in SCENARIOS.items():
        path = os.path.join(LOG_DIR, name)
        actual = run_scenario(overrides)
        if update:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(actual)
            print(f"UPDATED  {name}")
            continue
        try:
            with open(path, "r", encoding="utf-8", newline="") as f:
                expected = f.read()
        except FileNotFoundError:
            print(f"MISSING  {name} (run with --update to create it)")
            failures += 1
            continue
        if actual.replace("\r\n", "\n") == expected.replace("\r\n", "\n"):
            print(f"MATCH    {name}")
        else:
            failures += 1
            print(f"DIFFERS  {name} - first differences:")
            diff = difflib.unified_diff(expected.splitlines(), actual.splitlines(),
                                        "saved", "this run", n=1, lineterm="")
            for i, line in enumerate(diff):
                if i >= 30:
                    print("    ...")
                    break
                print("    " + line)
    if not update:
        print()
        print("All reference logs match." if not failures else f"{failures} reference log(s) differ.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
