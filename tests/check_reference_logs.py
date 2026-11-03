"""
tests/check_reference_logs.py - re-runs each reference battle and compares
it with its saved log in reference_logs/. Same seed + same code should give
a byte-identical log, so any difference means a change altered results.

    python tests/check_reference_logs.py            # compare
    python tests/check_reference_logs.py --update   # rewrite the saved logs
    python tests/check_reference_logs.py --round-trip   # save + reload after every turn

--round-trip (2026-11-03, INTEGRATION__saved_state): each battle is saved,
reloaded from the saved text and played on from the reloaded copy after every
turn; the log must still match the saved one byte for byte.

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
from concurrent.futures import ThreadPoolExecutor

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(REPO_ROOT, "reference_logs")

# Every reference battle stops at this many turns (Daniel, 2026-10-21: "Cap the
# test battles length to 50 ... No real fight should last that long. If it does
# it deserves to be noted as a possible flaw"). A battle that reaches it is
# flagged in the report (it still passes if its log matches).
TEST_BATTLE_MAX_TURNS = 50
CAP_MARKER = "-turn cap with both mechs standing"

# file name -> config overrides (Python statements run after
# `import INTEGRATION__config as config`, before the batch starts)
SCENARIOS = {
    # The default matchup (Kontio vs Hammerhead since 2026-10-20).
    "Kontio_vs_Hammerhead_seed12345.txt": [],
    # The old default, kept for the tripod (torso twists to any hexside,
    # tripod leg arcs) - named here since it's no longer the default.
    "Asymptote_vs_Asymptote_seed12345.txt": [
        'config.MECH_RED_MTF = "Asymptote II iJ Mpulse.mtf"',
        'config.MECH_BLUE_MTF = "Asymptote II iJ Mpulse.mtf"',
    ],
    "Asymptote_vs_Synthetic_maxheat8_seed777.txt": [
        'config.MECH_RED_MTF = "Asymptote II iJ Mpulse.mtf"',
        'config.MECH_BLUE_MTF = "TEST_Synthetic_Loadout.mtf"',
        "config.SEED = 777",
        'config.MECH_RED_CONFIG["max_heat"] = 8',
        'config.MECH_BLUE_CONFIG["max_heat"] = 8',
    ],
    # Added 2026-10-19 for the Heat Scale: max_heat 30 lets the synthetic
    # mech overheat - shutdown, a heat ammo explosion, an auto-failed PSR
    # while shut down, and an automatic restart all happen in this battle.
    "Asymptote_vs_Synthetic_maxheat30_seed2.txt": [
        'config.MECH_RED_MTF = "Asymptote II iJ Mpulse.mtf"',
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
        'config.MECH_RED_MTF = "Asymptote II iJ Mpulse.mtf"',
        'config.MECH_BLUE_MTF = "TEST_Heat_Gear.mtf"',
        "config.SEED = 5",
    ],
    # max_heat 30: coolant pods, shutdown, and an inferno ammo explosion.
    "Asymptote_vs_HeatGear_maxheat30_seed2.txt": [
        'config.MECH_RED_MTF = "Asymptote II iJ Mpulse.mtf"',
        'config.MECH_BLUE_MTF = "TEST_Heat_Gear.mtf"',
        "config.SEED = 2",
        'config.MECH_RED_CONFIG["max_heat"] = 30',
        'config.MECH_BLUE_CONFIG["max_heat"] = 30',
    ],
    # Added 2026-10-20 for Anti-Missile Systems (Core p.206): the Atlas AS7-K's
    # left-arm AMS engages the Archer ARC-2R's LRM 20 hits (and can't when the
    # Archer is outside its arc); both are real units from data/meks.zip.
    "Atlas_AS7-K_vs_Archer_ARC-2R_seed2.txt": [
        'config.MECH_RED_MTF = "Atlas AS7-K.mtf"',
        'config.MECH_BLUE_MTF = "Archer ARC-2R.mtf"',
        "config.SEED = 2",
    ],
    # Added 2026-10-20 for Narc / Artemis / ECM (Core pp.188, 193, 197, 200):
    # the Kintaro KTO-19 fires homing pods (Narc-capable SRMs and LRM) at the
    # Atlas AS7-K, whose AMS shoots some down; then the Atlas AS7-S2's Guardian
    # ECM blocks the Kintaro's pods while its own LRM 15 fires Artemis IV ammo.
    "Kintaro_KTO-19_vs_Atlas_AS7-K_seed2.txt": [
        'config.MECH_RED_MTF = "Kintaro KTO-19.mtf"',
        'config.MECH_BLUE_MTF = "Atlas AS7-K.mtf"',
        "config.SEED = 2",
    ],
    "Atlas_AS7-S2_vs_Kintaro_KTO-19_seed1.txt": [
        'config.MECH_RED_MTF = "Atlas AS7-S2.mtf"',
        'config.MECH_BLUE_MTF = "Kintaro KTO-19.mtf"',
        "config.SEED = 1",
    ],    # Added 2026-10-20 for the weapon-use choices (stubs): the Cataphract CTF-3D's
    # Ultra AC/5 rapid-fires and its LB 10-X picks slugs or cluster rounds; the
    # Emperor EMP-6D's Rotary AC/5s fire x6, jam and are unjammed. Then the
    # Akuma AKU-2XK's MML 9s pick LRM or SRM rounds and the Highlander IIC 2's
    # ATM 6 standard / ER / HE (its Artemis bonus blocked by the Akuma's ECM).
    "Cataphract_CTF-3D_vs_Emperor_EMP-6D_seed1.txt": [
        'config.MECH_RED_MTF = "Cataphract CTF-3D.mtf"',
        'config.MECH_BLUE_MTF = "Emperor EMP-6D.mtf"',
        "config.SEED = 1",
    ],
    "Akuma_AKU-2XK_vs_Highlander_IIC_2_seed1.txt": [
        'config.MECH_RED_MTF = "Akuma AKU-2XK.mtf"',
        'config.MECH_BLUE_MTF = "Highlander IIC 2.mtf"',
        "config.SEED = 1",
    ],    # Added 2026-10-20 for the weapons that couldn't fire: the Bombardier BMB-14K's
    # machine gun array against the Black Hawk F's HAG 20; the Bombardier
    # BMB-05A's Arrow IV (hex attacks, scatter) against the Cataphract CTF-3LL's
    # plasma rifle (heat on the target).
    "Bombardier_BMB-14K_vs_Black_Hawk_F_seed4.txt": [
        'config.MECH_RED_MTF = "Bombardier BMB-14K.mtf"',
        'config.MECH_BLUE_MTF = "Black Hawk (Nova) F.mtf"',
        "config.SEED = 4",
    ],
    "Bombardier_BMB-05A_vs_Cataphract_CTF-3LL_seed4.txt": [
        'config.MECH_RED_MTF = "Bombardier BMB-05A.mtf"',
        'config.MECH_BLUE_MTF = "Cataphract CTF-3LL.mtf"',
        "config.SEED = 4",
    ],
    # Added 2026-10-21 for map terrain: MegaMek's Military Base 1 (Map Set 7) -
    # hills, cliffs of 3+ levels, roads and 27 passive building hexes
    # (config.PASSIVE_BUILDINGS). Both mechs jump; the Black Hawk lands on
    # roofs three times.
    "Black_Hawk_F_vs_Cataphract_CTF-3D_MilitaryBase1_seed1.txt": [
        'config.MECH_RED_MTF = "Black Hawk (Nova) F.mtf"',
        'config.MECH_BLUE_MTF = "Cataphract CTF-3D.mtf"',
        'config.DEFAULT_BOARD_PATH = "16x17_Military_Base_1.board"',
        "config.SEED = 1",
    ],
    # Added 2026-10-21 for the water rules: MegaMek's Large Lakes 1 (Map Set 4) -
    # depth 1 and 2 lakes. Since the movement subphase (2026-10-21): runs through
    # water roll a PSR in each water hex entered, two falls on the way.
    "Black_Hawk_F_vs_Cataphract_CTF-3D_LargeLakes1_seed1.txt": [
        'config.MECH_RED_MTF = "Black Hawk (Nova) F.mtf"',
        'config.MECH_BLUE_MTF = "Cataphract CTF-3D.mtf"',
        'config.DEFAULT_BOARD_PATH = "16x17_Large_Lakes_1.board"',
        "config.SEED = 1",
    ],
}


def run_scenario(overrides, round_trip=False):
    code = "\n".join(
        ["import INTEGRATION__config as config",
         "config.TIMING = False",      # run times differ every run - not part of a saved log
         f"config.MAX_TURNS = {TEST_BATTLE_MAX_TURNS}"]
        + overrides
        + (["config.SAVE_STATE_ROUND_TRIP = True"] if round_trip else [])
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


def compare(name, actual):
    """(matched, report lines) for one scenario's fresh log vs its saved one."""
    path = os.path.join(LOG_DIR, name)
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            expected = f.read()
    except FileNotFoundError:
        return False, [f"MISSING  {name} (run with --update to create it)"]
    note = ([f"    NOTE: reached the {TEST_BATTLE_MAX_TURNS}-turn cap with both mechs standing - a possible flaw"]
            if CAP_MARKER in actual else [])
    if actual.replace("\r\n", "\n") == expected.replace("\r\n", "\n"):
        return True, [f"MATCH    {name}"] + note
    lines = [f"DIFFERS  {name} - first differences:"] + note
    diff = difflib.unified_diff(expected.splitlines(), actual.splitlines(),
                                "saved", "this run", n=1, lineterm="")
    for i, line in enumerate(diff):
        if i >= 30:
            lines.append("    ...")
            break
        lines.append("    " + line)
    return False, lines


def main():
    update = "--update" in sys.argv[1:]
    round_trip = "--round-trip" in sys.argv[1:]
    if update and round_trip:
        raise SystemExit("--round-trip only compares; it never rewrites the logs")
    # Each battle is its own child process, so they run side by side (one per
    # CPU core) without touching each other's results; reports print in
    # SCENARIOS order. Added 2026-10-20 (Claude): about 3x faster on 4 cores.
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 1) as pool:
        runs = {name: pool.submit(run_scenario, overrides, round_trip)
                for name, overrides in SCENARIOS.items()}
    failures = 0
    for name, run in runs.items():
        actual = run.result()
        if update:
            with open(os.path.join(LOG_DIR, name), "w", encoding="utf-8", newline="\n") as f:
                f.write(actual)
            print(f"UPDATED  {name}")
            if CAP_MARKER in actual:
                print(f"    NOTE: reached the {TEST_BATTLE_MAX_TURNS}-turn cap with both mechs standing - a possible flaw")
            continue
        matched, lines = compare(name, actual)
        failures += not matched
        print("\n".join(lines))
    if not update:
        print()
        print("All reference logs match." if not failures else f"{failures} reference log(s) differ.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
