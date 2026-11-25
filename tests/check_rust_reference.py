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
import gzip
import json
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(REPO_ROOT, "engine")
BTSIM = os.path.join(ENGINE, "target", "release", "btsim")
SCENARIOS_ZIP = os.path.join(ENGINE, "reference", "scenarios.zip")
LOG_DIR = os.path.join(ENGINE, "reference", "logs")
# each battle's event records (INTEGRATION__EVENTS.md), beside its log: one JSON event a line, gzipped. Played with events ON, so
# every run of this check also proves that recording events leaves the battle's log byte for byte the same.
EVENT_DIR = os.path.join(ENGINE, "reference", "events")
# the reference LIST: which battles of the zip are played (chosen by tools/choose_reference_set.py for event coverage)
LIST_FILE = os.path.join(ENGINE, "reference", "battles.txt")
# every event type must happen in at least this many of the list's battles (below it: a NOTE; at zero: the check FAILS)
EVENT_MIN_BATTLES = 3
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
    # BTTT's re-implemented bot (2026-11-25, bttt.rs): a team string "bttt:TEAMS" plays those teams as BTTT (btsim --bttt). One a duel (its
    # walk, its value, its weapon dropping), one on hills (its routes up and down levels, walked as picked), one BTTT against itself.
    "bttt_red__hy_duel_griffin": ("hy_duel_griffin", "bttt:Red"),
    "bttt_blue__hy_4v4_heavy_hills": ("hy_4v4_heavy_hills", "bttt:Blue"),
    "bttt_both__hy_2v2_grass": ("hy_2v2_grass", "bttt:Red,Blue"),
    # BTTT jumps only when its path runs past its running MP and fits its jump MP: Asymptote's jets outrun its legs (run 4, jump 5)
    "bttt_red__ref_Asymptote_vs_HeatGear_maxheat30_seed2": ("ref_Asymptote_vs_HeatGear_maxheat30_seed2", "bttt:Red"),
    # BTTT's MASC (asked for only when its path needs it, then rolled by the engine) and its own TAG phase
    "bttt_both__cov_masc_always": ("cov_masc_always", "bttt:Red,Blue"),
    "bttt_both__cov_arrow_tag": ("cov_arrow_tag", "bttt:Red,Blue"),
    # event coverage (2026-11-24, tools/make_event_scenarios.py): Hydra on both teams of two jump-'Mech scenarios, where a
    # death-from-above happens (rare: Gladiator never makes one)
    "hydra_both__ev_dfa_a": ("ev_dfa_a", "Red,Blue"),
    "hydra_both__ev_dfa_b": ("ev_dfa_b", "Red,Blue"),
}


def bot_args(teams):
    """btsim's flags for a variant's team string: "Red" / "Red,Blue" = Hydra, "caspar:Red" = CASPAR, "bttt:Red" = BTTT's bot."""
    if not teams:
        return []
    if teams.startswith("caspar:"):
        return ["--caspar", teams[len("caspar:"):]]
    if teams.startswith("bttt:"):
        return ["--bttt", teams[len("bttt:"):]]
    return ["--hydra", teams]


def bot_label(teams):
    """The saved log's header words for a variant's team string."""
    if not teams:
        return ""
    if teams.startswith("caspar:"):
        return f", CASPAR drives {teams[len('caspar:'):]}"
    if teams.startswith("bttt:"):
        return f", BTTT drives {teams[len('bttt:'):]}"
    return f", Hydra drives {teams}"


def build():
    """Builds the release btsim (quick when nothing changed)."""
    subprocess.run(["cargo", "build", "--release", "-p", "btsim"], cwd=ENGINE, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def listed_names():
    """The reference list, engine/reference/battles.txt: one battle name a line, text after # is the reason it is there."""
    names = []
    for line in open(LIST_FILE, encoding="utf-8"):
        line = line.split("#", 1)[0].strip()
        if line:
            names.append(line)
    return names


def battles(scenario_dir, everything=False):
    """[(saved-log name, scenario folder, (Hydra teams or None, settings))] for the battles of the reference LIST
    (engine/reference/battles.txt). `everything` = every scenario folder in the zip and every variant, listed or not (the pool
    tools/choose_reference_set.py chooses from)."""
    folders = sorted(d for d in os.listdir(scenario_dir) if os.path.isdir(os.path.join(scenario_dir, d)))
    out = [(f, f, (None, [])) for f in folders]
    out += [(name, v[0], (v[1], v[2] if len(v) > 2 else [])) for name, v in VARIANTS.items()]
    if everything:
        return out
    by_name = {o[0]: o for o in out}
    missing = [n for n in listed_names() if n not in by_name]
    if missing:
        raise SystemExit(f"battles.txt names battles that do not exist: {', '.join(missing)}")
    return [by_name[n] for n in listed_names()]


def play(scenario_dir, folder, variant, parity=False, history_dir=None):
    """One battle with btsim; returns the saved-log text. With `parity` (2026-11-17) the battle is played once under the
    MegaMek bridge's parity check (btsim --bridge-parity --bridge-compact, tests/check_bridge_parity.py) and returns
    (text, parity problem or None): the same battle serves both checks, so run_checks.py no longer plays them twice."""
    hydra, settings = variant
    cmd = [BTSIM, os.path.join(scenario_dir, folder), "--battles", "1", "--seed", str(SEED), "--log", "1", "--threads", "1"]
    ev_file = os.path.join(scenario_dir, f"{folder}.{abs(hash(str(variant)))}.events.jsonl")
    if parity:
        cmd += ["--bridge-parity", "--bridge-compact"]
    else:
        cmd += ["--events", "--events-out", ev_file]
    if history_dir:   # --history DIR: also write the battle's replay page there (a search result's replay command)
        cmd += ["--history", "1", "--history-dir", history_dir]
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
        return f"# btsim failed (exit {proc.returncode})\n" + proc.stderr, None
    text = saved_text(folder, hydra, settings, json.loads(proc.stdout))
    return text, events_text(ev_file)


def events_text(path):
    """The battle's events as saved: a header line {events_version, teams}, then one JSON event a line (btsim --events-out), or None."""
    if not os.path.exists(path):
        return None
    row = json.loads(open(path).readline())
    os.remove(path)
    head = json.dumps({"events_version": row["events_version"], "teams": row["teams"]}, separators=(",", ":")) + "\n"
    return head + "".join(json.dumps(e, separators=(",", ":")) + "\n" for e in row["events"])


def write_events(name, text, folder=None):
    folder = folder or EVENT_DIR
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name + ".events.jsonl.gz"), "wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9, mtime=0) as z:
            z.write(text.encode())


def read_events(name):
    path = os.path.join(EVENT_DIR, name + ".events.jsonl.gz")
    return gzip.open(path, "rt").read() if os.path.exists(path) else None


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
    exact = "--exact" in argv   # --only NAME is the whole name, not a prefix
    history_dir = argv[argv.index("--history") + 1] if "--history" in argv else None
    # --all --out DIR: play EVERY scenario and variant in the zip, listed or not, and write their logs and events into DIR (nothing
    # in engine/reference is touched): the pool tools/event_coverage.py and tools/choose_reference_set.py choose the list from
    everything = "--all" in argv
    out_dir = argv[argv.index("--out") + 1] if "--out" in argv else None
    if everything and not out_dir:
        raise SystemExit("--all needs --out DIR (it never rewrites the reference list's saved logs)")
    # --parity: each battle is played once under the bridge's parity check as well (and the wire test is run), standing in
    # for tests/check_bridge_parity.py in run_checks.py (2026-11-17, Daniel: prune the checks)
    with_parity = "--parity" in argv
    build()
    seconds = {}
    os.makedirs(LOG_DIR, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(SCENARIOS_ZIP) as z:
            z.extractall(tmp)
        todo = [b for b in battles(tmp, everything) if (b[0] == only if exact else b[0].startswith(only))]
        with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
            def timed(b):
                t0 = time.perf_counter()
                r = play(tmp, b[1], b[2], with_parity, history_dir)
                seconds[b[0]] = time.perf_counter() - t0
                return r
            played = list(pool.map(timed, todo))
        if "--times" in argv:   # --times FILE: how long each battle took (seconds, with every core busy), for choosing a lean set
            with open(argv[argv.index("--times") + 1], "w") as f:
                f.writelines(f"{n}\t{s:.2f}\n" for n, s in sorted(seconds.items()))
        if history_dir:   # a replay only: the page's log leaves out the engine's bare prints, so it is not compared with the saved one
            print(f"replay page(s) written to {history_dir} (no comparison made)")
            return 0
        texts = [p[0] for p in played]
        problems = [p[1] for p in played] if with_parity else [None] * len(played)
        events = [None if with_parity else p[1] for p in played]
        if everything:
            os.makedirs(out_dir, exist_ok=True)
            for (name, _, _), text, ev in zip(todo, texts, events):
                with open(os.path.join(out_dir, name + ".txt"), "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
                if ev is not None:
                    write_events(name, ev, out_dir)
            print(f"{len(todo)} battles played; logs and events written to {out_dir}")
            return 0
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
    for (name, _, _), text, ev in zip(todo, texts, events):
        path = os.path.join(LOG_DIR, name + ".txt")
        note = " NOTE: turn cap" if "reached the turn cap" in text.split("# log", 1)[0] else ""
        capped += bool(note)
        if text.startswith("# btsim failed"):
            note += " (btsim FAILED - see the log)"
        if update:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            if ev is not None:
                write_events(name, ev)
            print(f"SAVED  {name}{note}")
            continue
        if not os.path.exists(path):
            failed += 1
            print(f"FAIL   {name}: no saved log (run with --update)")
            continue
        old = open(path, encoding="utf-8").read()
        ev_note = ""
        if old == text and ev is not None:
            saved_ev = read_events(name)
            if saved_ev is None:
                ev_note = " (no saved events: run with --update)"
            elif saved_ev != ev:
                failed += 1
                print(f"FAIL   {name}{note}: the log matches but the EVENTS differ ({len(saved_ev.splitlines()) - 1} saved, {len(ev.splitlines()) - 1} now)")
                continue
        if old == text:
            print(f"PASS   {name}{note}{ev_note}")
        else:
            failed += 1
            diff = list(difflib.unified_diff(old.splitlines(), text.splitlines(), "saved", "now", n=1, lineterm=""))
            print(f"FAIL   {name}{note}: first difference")
            print("\n".join("         " + d for d in diff[2:12]))
    print(f"\n{len(todo) - failed} of {len(todo)} Rust reference battles " + ("saved." if update else "match.")
          + (f" {capped} reached the turn cap." if capped else ""))
    if not only and not with_parity and all(e is not None for e in events):
        failed += coverage_report(events)
        stale = sorted(f[:-4] for f in os.listdir(LOG_DIR) if f.endswith(".txt") and f[:-4] not in {n for n, _, _ in todo})
        if stale:
            print(f"NOTE: saved logs of battles no longer on the list (delete them): {', '.join(stale[:6])}" + (" ..." if len(stale) > 6 else ""))
    return 1 if failed else 0


def coverage_report(events):
    """EVENT COVERAGE of the list (Daniel, 2026-11-24): how many of the battles, and how many events, each event type has. A type
    with no event at all FAILS the check (a rule or a scenario stopped reaching it); fewer than EVENT_MIN_BATTLES is a NOTE.
    Returns the number of failures (0 or 1)."""
    texts = [t for t in events]
    kinds = [k["kind"] for k in json.loads(subprocess.run([BTSIM, "--events-list"], capture_output=True, text=True, check=True).stdout)["kinds"]]
    battles_with, total = {k: 0 for k in kinds}, {k: 0 for k in kinds}
    for text in texts:
        seen = set()
        for line in text.splitlines()[1:]:
            k = json.loads(line)["k"]
            total[k] = total.get(k, 0) + 1
            seen.add(k)
        for k in seen:
            battles_with[k] = battles_with.get(k, 0) + 1
    thin = [k for k in kinds if 0 < battles_with[k] < EVENT_MIN_BATTLES]
    zero = [k for k in kinds if battles_with[k] == 0]
    print(f"\nEVENT COVERAGE ({len(texts)} battles; every type needs {EVENT_MIN_BATTLES}):")
    width = max(len(k) for k in kinds)
    for k in kinds:
        flag = "   <-- NO EVENT: FAIL" if k in zero else ("   <-- fewer than %d battles" % EVENT_MIN_BATTLES if k in thin else "")
        print(f"  {k:{width}s} {battles_with[k]:4d} battles {total[k]:7d} events{flag}")
    if zero:
        print(f"FAIL   event types with no event in any listed battle: {', '.join(zero)}")
        return 1
    if thin:
        print(f"NOTE: event types in fewer than {EVENT_MIN_BATTLES} battles: {', '.join(thin)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
