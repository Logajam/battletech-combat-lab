"""
tests/check_rust_reference.py - the Rust engine's own reference battles (session 25).

    python tests/check_rust_reference.py             # build btsim, play every battle, compare with the saved logs
    python tests/check_rust_reference.py --update    # rewrite the saved logs (a change MEANT to alter results)
    python tests/check_rust_reference.py --only hy_  # just the battles whose name starts with this

Why: until now the Rust was checked only against the Python (tools/port_record.py records a battle in Python,
the Rust replays it and must match). Daniel, 2026-11-11, on the Python: "Its effectively dead code now". This
set lets the Rust check itself, the way tests/check_reference_logs.py checks the Python: same scenario + same
seed + same code = a byte-identical log, so any difference means a change altered results.

The battles. `engine/reference/scenarios.zip` holds the inputs (config.json, units.json, board.json) of the
72 scenarios the port was built on, frozen on 2026-11-11 so the Python is no longer needed to make them:
  ref_*   the 15 Python reference battles          team_*  4 v 4, 12 v 12 and a 3-way
  cov_*   short battles covering every weapon family, equipment module and hazard
  hy_*    Hydra's mirror match-ups (INTEGRATION__HYDRA.md)
Each is played once by `btsim` on its own dice (PcgDice, seed 1) with the scenario's own bots; a few are
played again with Hydra on one side (VARIANTS), since Hydra has no Python answer key at all.

Saved logs: engine/reference/logs/<name>.txt - a short result block (winner, turns, each team's armor +
structure left, units destroyed), then the battle log. A battle that reaches its turn cap prints a NOTE
(Daniel: "a possible flaw"); it still passes if its log matches.
"""

import difflib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(REPO_ROOT, "engine")
BTSIM = os.path.join(ENGINE, "target", "release", "btsim")
SCENARIOS_ZIP = os.path.join(ENGINE, "reference", "scenarios.zip")
LOG_DIR = os.path.join(ENGINE, "reference", "logs")
SEED = 1

# Extra plays of a scenario with Hydra driving some teams: saved-log name -> (scenario folder, Hydra teams).
VARIANTS = {
    "hydra_red__hy_duel_griffin": ("hy_duel_griffin", "Red"),
    "hydra_red__hy_duel_hunchback_woods": ("hy_duel_hunchback_woods", "Red"),
    "hydra_blue__hy_2v2_grass": ("hy_2v2_grass", "Blue"),
    "hydra_red__hy_4v4_lance_woods": ("hy_4v4_lance_woods", "Red"),
    "hydra_blue__hy_4v4_heavy_hills": ("hy_4v4_heavy_hills", "Blue"),
    "hydra_red__hy_12v12_valley": ("hy_12v12_valley", "Red"),
    "hydra_both__hy_4v4_lance_grass": ("hy_4v4_lance_grass", "Red,Blue"),
}


def build():
    """Builds the release btsim (quick when nothing changed)."""
    subprocess.run(["cargo", "build", "--release", "-p", "btsim"], cwd=ENGINE, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def battles(scenario_dir):
    """[(saved-log name, scenario folder, Hydra teams or None)] for every reference battle."""
    folders = sorted(d for d in os.listdir(scenario_dir) if os.path.isdir(os.path.join(scenario_dir, d)))
    out = [(f, f, None) for f in folders]
    out += [(name, folder, teams) for name, (folder, teams) in VARIANTS.items()]
    return out


def play(scenario_dir, folder, hydra):
    """One battle with btsim; returns the saved-log text."""
    cmd = [BTSIM, os.path.join(scenario_dir, folder), "--battles", "1", "--seed", str(SEED), "--log", "1", "--threads", "1"]
    if hydra:
        cmd += ["--hydra", hydra]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # a panic is a result too: save its message so a change that makes or cures one shows as a difference
        return f"# btsim failed (exit {proc.returncode})\n" + proc.stderr
    out = json.loads(proc.stdout)
    r = out["results"][0]
    lines = [f"# scenario {folder}" + (f", Hydra drives {hydra}" if hydra else ""),
             f"# seed {SEED}: winner {r['winner']}, {r['turns']} turns" + (" - NOTE: reached the turn cap" if out["hit_turn_cap"] else "")]
    for team, t in r["teams"].items():
        lines.append(f"#   {team}: {t['final_hp']} of {t['max_hp']} armor + structure left, team destroyed {t['destroyed']}, units {t['units']}, "
                     f"{t['hits']} hits of {t['attacks']} attacks, {t['damage_dealt']} damage dealt")
    lines.append("# log")
    for block in out["logs"]:
        lines.extend(block["lines"])
    return "\n".join(lines) + "\n"


def main(argv):
    update = "--update" in argv
    only = argv[argv.index("--only") + 1] if "--only" in argv else ""
    build()
    os.makedirs(LOG_DIR, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(SCENARIOS_ZIP) as z:
            z.extractall(tmp)
        todo = [b for b in battles(tmp) if b[0].startswith(only)]
        with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
            texts = list(pool.map(lambda b: play(tmp, b[1], b[2]), todo))
    failed, capped = 0, 0
    for (name, _, _), text in zip(todo, texts):
        path = os.path.join(LOG_DIR, name + ".txt")
        note = " NOTE: turn cap" if "reached the turn cap" in text.split("# log", 1)[0] else ""
        capped += bool(note)
        if text.startswith("# btsim failed"):
            note += " (btsim FAILED - see the log)"
        if update:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            print(f"SAVED  {name}{note}")
            continue
        if not os.path.exists(path):
            failed += 1
            print(f"FAIL   {name}: no saved log (run with --update)")
            continue
        old = open(path, encoding="utf-8").read()
        if old == text:
            print(f"PASS   {name}{note}")
        else:
            failed += 1
            diff = list(difflib.unified_diff(old.splitlines(), text.splitlines(), "saved", "now", n=1, lineterm=""))
            print(f"FAIL   {name}{note}: first difference")
            print("\n".join("         " + d for d in diff[2:12]))
    print(f"\n{len(todo) - failed} of {len(todo)} Rust reference battles " + ("saved." if update else "match.")
          + (f" {capped} reached the turn cap." if capped else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
