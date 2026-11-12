"""
tests/check_bridge_parity.py - the MegaMek bridge's decision process gives the battle's own answers (stage B1).

    python tests/check_bridge_parity.py              # every reference scenario + the Hydra variants, then the wire test
    python tests/check_bridge_parity.py --only hy_   # just the scenarios whose name starts with this
    python tests/check_bridge_parity.py --quick      # run_checks.py's run: no 8 v 8 / 12 v 12 battles, and every battle
                                                     # stops at turn 15 (the full set takes about 6 minutes on 4 cores)

Why (INTEGRATION__MEGAMEK_BRIDGE.md, Section 8, B1): in a MegaMek game our bots decide from SNAPSHOTS of the game, sent
line by line to `btsim decide`, which keeps its own copy of the battle and the bots' memories. This check proves that
deciding that way is the same as deciding inside one of our own battles:

1. PARITY. Each reference battle (engine/reference/scenarios.zip, the same 72 scenarios and Hydra variants as
   tests/check_rust_reference.py, seed 1) is played with `btsim --bridge-parity`: its bots' every call is recorded with
   the battle's state, then a fresh decision process is fed the recording and must give the same answer to every
   decision (engine/core/src/bridge.rs). One difference fails the check and names the call.
   Units go to the process as COMPACT states (stage B3: only what a battle changes, bridge.rs UNIT_FIELDS /
   ITEM_FIELDS, the rest from each unit at the start), so the check also proves those lists are complete: every unit
   rebuilt from its compact state must equal its real dump at every call, field for field, and a field that does not
   ("rebuild gaps") fails the check even if no decision happened to depend on it.
2. THE WIRE. One recording is piped through a real `btsim decide` process, one JSON line at a time, the way the Java
   side of the bridge will talk to it; every answer must equal the recorded one.

Every bot call is covered: the signals, move order, movement, targets, firing order, the weapon declaration and the
physical attack.
"""

import json
import os
import subprocess
import sys
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_rust_reference as ref  # noqa: E402  (the scenarios zip, the Hydra variants, the build)


def parity(scenario_dir, name, folder, variant, max_turns=None):
    """One battle under --bridge-parity: (name, ok, summary text)."""
    hydra, settings = variant
    cmd = [ref.BTSIM, os.path.join(scenario_dir, folder), "--battles", "1", "--seed", str(ref.SEED), "--threads", "1", "--bridge-parity", "--bridge-compact"]
    if max_turns:
        cmd += ["--max-turns", str(max_turns)]
    if hydra:
        cmd += ["--hydra", hydra]
    for kv in settings:
        cmd += ["--set", kv]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    lines = [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]
    if not lines:
        return name, False, f"btsim failed (exit {proc.returncode}): {proc.stderr.strip()[-400:]}"
    r = lines[0]
    text = f"{r['decisions']} decisions, {r['calls']} calls"
    if r.get("rebuild_gaps"):
        # a field the compact state does not carry: add it to bridge.rs UNIT_FIELDS / ITEM_FIELDS
        return name, False, f"{text}; COMPACT STATE MISSES {r['rebuild_gaps']}"
    if not r["same"]:
        d = r["first_difference"]
        return name, False, f"{text}; FIRST DIFFERENCE at line {d['line']} ({d['method']}): battle {json.dumps(d['battle'])[:200]} / session {json.dumps(d['session'])[:200]}"
    return name, True, text


def wire(scenario_dir, folder, max_turns=None):
    """Records one battle, pipes it through `btsim decide`, compares every answer. Returns (ok, text)."""
    with tempfile.TemporaryDirectory() as tmp:
        dump = os.path.join(tmp, "recording.jsonl")
        cmd = [ref.BTSIM, os.path.join(scenario_dir, folder), "--battles", "1", "--seed", str(ref.SEED), "--threads", "1",
               "--bridge-parity", "--bridge-compact", "--bridge-dump", dump]
        if max_turns:
            cmd += ["--max-turns", str(max_turns)]
        subprocess.run(cmd, capture_output=True, check=True)
        rows = [json.loads(l) for l in open(dump, encoding="utf-8") if l.strip()]
    start, calls = rows[0], rows[1:]
    feed = "".join(json.dumps(x) + "\n" for x in [start] + [{"method": c["method"], "args": c["args"], "state": c["state"]} for c in calls])
    proc = subprocess.run([ref.BTSIM, "decide"], input=feed, capture_output=True, text=True)
    replies = [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]
    if len(replies) != len(calls) + 1 or not replies[0].get("started"):
        return False, f"btsim decide gave {len(replies)} replies for {len(calls) + 1} lines: {proc.stderr.strip()[-300:]}"
    for i, (c, rep) in enumerate(zip(calls, replies[1:]), start=1):
        if "error" in rep:
            return False, f"call {i} ({c['method']}): error {rep['error'][:300]}"
        if rep["answer"] != c["answer"]:
            return False, f"call {i} ({c['method']}): battle {json.dumps(c['answer'])[:200]} / decide {json.dumps(rep['answer'])[:200]}"
    return True, f"{len(calls)} calls through `btsim decide`, every answer the same"


def main(argv):
    only = argv[argv.index("--only") + 1] if "--only" in argv else ""
    ref.build()
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(ref.SCENARIOS_ZIP) as z:
            z.extractall(tmp)
        todo = [b for b in ref.battles(tmp) if b[0].startswith(only)]
        quick = "--quick" in argv
        if quick:
            todo = [b for b in todo if not any(big in b[1] for big in ("8v8", "12v12"))]
        # one core spare: the 4 v 4 and larger battles hold several hundred MB each while checked
        with ThreadPoolExecutor(max_workers=max(1, (os.cpu_count() or 4) - 1)) as pool:
            results = list(pool.map(lambda b: parity(tmp, b[0], b[1], b[2], 15 if quick else None), todo))
        wire_folder = "hy_2v2_grass" if quick else "hy_4v4_lance_woods"
        wire_ok, wire_text = wire(tmp, wire_folder, 15 if quick else None)
    failed = 0
    for name, ok, text in results:
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}   {name}: {text}")
    failed += not wire_ok
    print(f"{'PASS' if wire_ok else 'FAIL'}   wire ({wire_folder}): {wire_text}")
    print(f"\n{len(results) + 1 - failed} of {len(results) + 1} bridge checks passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
