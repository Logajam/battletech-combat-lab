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
structure left, units destroyed), then the battle log. The turn cap is the engine's standard, 100 (2026-11-12; it was 50). A battle that reaches it prints a NOTE
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

# Extra plays of a scenario with Hydra driving some teams: saved-log name -> (scenario folder, Hydra teams[, settings]).
# Settings are btsim --set KEY=VALUE pairs (engine/core/src/hydra.rs lists Hydra's switches and their OFF values).
# Hydra as first built (session 24-25): every later switch off. (The map-edge risk, 2026-11-17, has no switch: Daniel
# made it mandatory, so these play the first version WITH the edge risk.)
FIRST_VERSION = ["HYDRA_PLAYOUT=reply", "HYDRA_MOVEMENT_ATTACKS=false", "HYDRA_MOVE_ORDER=index", "HYDRA_WAITING=false", "HYDRA_ATTENTION=range"]

VARIANTS = {
    "hydra_red__hy_duel_griffin": ("hy_duel_griffin", "Red"),
    "hydra_red__hy_duel_hunchback_woods": ("hy_duel_hunchback_woods", "Red"),
    "hydra_blue__hy_2v2_grass": ("hy_2v2_grass", "Blue"),
    "hydra_red__hy_4v4_lance_woods": ("hy_4v4_lance_woods", "Red"),
    "hydra_blue__hy_4v4_heavy_hills": ("hy_4v4_heavy_hills", "Blue"),
    "hydra_red__hy_12v12_valley": ("hy_12v12_valley", "Red"),
    "hydra_both__hy_4v4_lance_grass": ("hy_4v4_lance_grass", "Red,Blue"),
    # session 25, 2026-11-12: Hydra's five switches are ON by default ("Leave them all on"); these keep each OFF path played
    "hydra_noplayout_red__hy_4v4_lance_woods": ("hy_4v4_lance_woods", "Red", ["HYDRA_PLAYOUT=reply"]),
    "hydra_nocharge_red__hy_duel_griffin": ("hy_duel_griffin", "Red", ["HYDRA_MOVEMENT_ATTACKS=false"]),
    "hydra_nomoveorder_blue__hy_8v8_valley": ("hy_8v8_valley", "Blue", ["HYDRA_MOVE_ORDER=index"]),
    "hydra_nowait_red__hy_8v8_valley": ("hy_8v8_valley", "Red", ["HYDRA_WAITING=false"]),
    "hydra_noattention_blue__hy_4v4_heavy_hills": ("hy_4v4_heavy_hills", "Blue", ["HYDRA_ATTENTION=range"]),
    "hydra_first_red__hy_4v4_lance_woods": ("hy_4v4_lance_woods", "Red", FIRST_VERSION),
    "hydra_first_blue__hy_8v8_valley": ("hy_8v8_valley", "Blue", FIRST_VERSION),
    # CASPAR, the fourth bot (session 29; added in its review, 2026-11-19): a team string "caspar:TEAMS" plays those teams as
    # CASPAR (btsim --caspar) instead of Hydra. Without these no reference battle ran CASPAR's code at all.
    "caspar_red__hy_duel_griffin": ("hy_duel_griffin", "caspar:Red"),
    "caspar_blue__hy_4v4_heavy_hills": ("hy_4v4_heavy_hills", "caspar:Blue"),
    "caspar_red__hy_8v8_valley": ("hy_8v8_valley", "caspar:Red"),
    "caspar_red__team_4v4_princess_v_gladiator": ("team_4v4_princess_v_gladiator", "caspar:Red"),
}


def bot_args(teams):
    """btsim's flags for a variant's team string: "Red" / "Red,Blue" = Hydra, "caspar:Red" = CASPAR."""
    if not teams:
        return []
    if teams.startswith("caspar:"):
        return ["--caspar", teams[len("caspar:"):]]
    return ["--hydra", teams]


def bot_label(teams):
    """The saved log's header words for a variant's team string."""
    if not teams:
        return ""
    if teams.startswith("caspar:"):
        return f", CASPAR drives {teams[len('caspar:'):]}"
    return f", Hydra drives {teams}"


def build():
    """Builds the release btsim (quick when nothing changed)."""
    subprocess.run(["cargo", "build", "--release", "-p", "btsim"], cwd=ENGINE, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def battles(scenario_dir):
    """[(saved-log name, scenario folder, (Hydra teams or None, settings))] for every reference battle."""
    folders = sorted(d for d in os.listdir(scenario_dir) if os.path.isdir(os.path.join(scenario_dir, d)))
    out = [(f, f, (None, [])) for f in folders]
    out += [(name, v[0], (v[1], v[2] if len(v) > 2 else [])) for name, v in VARIANTS.items()]
    return out


def play(scenario_dir, folder, variant, parity=False):
    """One battle with btsim; returns the saved-log text. With `parity` (2026-11-17) the battle is played once under the
    MegaMek bridge's parity check (btsim --bridge-parity --bridge-compact, tests/check_bridge_parity.py) and returns
    (text, parity problem or None): the same battle serves both checks, so run_checks.py no longer plays them twice."""
    hydra, settings = variant
    cmd = [BTSIM, os.path.join(scenario_dir, folder), "--battles", "1", "--seed", str(SEED), "--log", "1", "--threads", "1"]
    if parity:
        cmd += ["--bridge-parity", "--bridge-compact"]
    cmd += bot_args(hydra)
    for kv in settings:
        cmd += ["--set", kv]
    # HYDRA_CHECK (session 25, engine/core/src/playout.rs): every Hydra decision is also checked to leave the battle as it
    # found it (no dice, no log, no state); a breach panics, and the saved log then shows the difference.
    proc = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, HYDRA_CHECK="1"))
    if parity:
        rows = [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]
        if not rows or "result" not in rows[0]:
            return f"# btsim failed (exit {proc.returncode})\n" + proc.stderr, f"btsim failed: {proc.stderr.strip()[-300:]}"
        row = rows[0]
        problem = None
        if row.get("rebuild_gaps"):
            problem = f"COMPACT STATE MISSES {row['rebuild_gaps']}"
        elif not row["same"]:
            d = row["first_difference"]
            problem = f"bridge parity: FIRST DIFFERENCE at line {d['line']} ({d['method']})"
        out = {"results": [row["result"]], "hit_turn_cap": row["capped"], "logs": [{"lines": row["log"]}]}
        return saved_text(folder, hydra, settings, out), problem
    if proc.returncode != 0:
        # a panic is a result too: save its message so a change that makes or cures one shows as a difference
        return f"# btsim failed (exit {proc.returncode})\n" + proc.stderr
    return saved_text(folder, hydra, settings, json.loads(proc.stdout))


def saved_text(folder, hydra, settings, out):
    """The saved-log text of one battle from btsim's JSON (results, hit_turn_cap, logs)."""
    r = out["results"][0]
    lines = [f"# scenario {folder}" + bot_label(hydra) + "".join(f", {kv}" for kv in settings),
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
    # --parity: each battle is played once under the bridge's parity check as well (and the wire test is run), standing in
    # for tests/check_bridge_parity.py in run_checks.py (2026-11-17, Daniel: prune the checks)
    with_parity = "--parity" in argv
    build()
    os.makedirs(LOG_DIR, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(SCENARIOS_ZIP) as z:
            z.extractall(tmp)
        todo = [b for b in battles(tmp) if b[0].startswith(only)]
        with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
            played = list(pool.map(lambda b: play(tmp, b[1], b[2], with_parity), todo))
        texts = [p[0] for p in played] if with_parity else played
        problems = [p[1] for p in played] if with_parity else [None] * len(played)
        wire_result = None
        if with_parity:
            import check_bridge_parity   # noqa: E402 (its wire test: one recording through a real `btsim decide`)
            wire_result = check_bridge_parity.wire(tmp, "hy_2v2_grass")
    failed, capped = 0, 0
    for (name, _, _), problem in zip(todo, problems):
        if problem:
            failed += 1
            print(f"FAIL   {name}: {problem}")
    if wire_result is not None:
        failed += not wire_result[0]
        print(f"{'PASS' if wire_result[0] else 'FAIL'}   bridge wire (hy_2v2_grass): {wire_result[1]}")
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
