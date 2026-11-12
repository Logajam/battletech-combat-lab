"""
tools/megamek_bridge_games.py - play games in MegaMek with our engine driving some players (the MegaMek bridge,
INTEGRATION__MEGAMEK_BRIDGE.md) and summarize them.

    python tools/megamek_bridge_games.py SCENARIO.mms --megamek DIR --bridge Red [--games 3] [--rounds 100]
        [--timeout 8] [--records FILE] [--label TEXT] [--seed 1]

--megamek: the unpacked MegaMek release folder (megamek_bridge/README.md says how to get it). The bridge jar is built
first if it is missing (megamek_bridge/build.sh). Each game is ONE run of btbridge.BridgeLauncher (MegaMek sometimes
stalls at a game's start; a game that ends before round 2 without a result is played again, at most twice). Every
game's record is appended to --records (default trial_records/megamek_bridge.jsonl) as it ends; the decision
transcripts go to the MegaMek folder's logs/ (bridge_<label>_<player>.jsonl).

Prints one line per game and a summary: wins per team, draws, unfinished, our engine's decisions and Princess's
fallbacks by reason.
"""
import argparse
import collections
import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JAR = os.path.join(REPO_ROOT, "megamek_bridge", "build", "megamek_bridge.jar")
BTSIM = os.path.join(REPO_ROOT, "engine", "target", "release", "btsim")


def play(a, n, records):
    """One game; returns its record (dict), or None if the launcher wrote none."""
    label = f"{a.label} {n}"
    cmd = ["java", "-Djava.awt.headless=true", "-cp", f"{JAR}:MegaMek.jar:lib/*", "btbridge.BridgeLauncher",
           os.path.abspath(a.scenario), "--btsim", BTSIM, "--bridge", a.bridge, "--rounds", str(a.rounds),
           "--timeout", str(a.timeout), "--records", records, "--label", label, "--seed", str(a.seed + n - 1)]
    try:
        subprocess.run(cmd, cwd=a.megamek, capture_output=True, text=True, timeout=a.timeout * 60 + 120)
    except subprocess.TimeoutExpired:
        return {"label": label, "error": "the launcher itself did not stop"}
    with open(records, encoding="utf-8") as f:
        lines = [json.loads(l) for l in f if l.strip()]
    mine = [r for r in lines if r.get("label") == label]
    return mine[-1] if mine else None


def describe(r):
    if r is None:
        return "no record"
    if "error" in r:
        return "ERROR " + r["error"][:200]
    teams = ", ".join(f"team {t}: {v['survivors']} left, BV {v['bv_left']}/{v['bv_start']}" for t, v in r["teams"].items())
    ours = r["bridge"][0] if r.get("bridge") else {}
    return (f"{'finished' if r['finished'] else 'UNFINISHED'}, {r['rounds']} rounds, winner {r['winning_team']}; {teams}; "
            f"ours {ours.get('ours')}, fallbacks {ours.get('fallbacks')}")


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("scenario")
    p.add_argument("--megamek", required=True)
    p.add_argument("--bridge", required=True)
    p.add_argument("--games", type=int, default=3)
    p.add_argument("--rounds", type=int, default=100)
    p.add_argument("--timeout", type=int, default=8)
    p.add_argument("--records", default=os.path.join(REPO_ROOT, "trial_records", "megamek_bridge.jsonl"))
    p.add_argument("--label", default="")
    p.add_argument("--seed", type=int, default=1)
    a = p.parse_args(argv)
    a.label = a.label or os.path.splitext(os.path.basename(a.scenario))[0]
    if not os.path.exists(JAR):
        subprocess.run([os.path.join(REPO_ROOT, "megamek_bridge", "build.sh")], check=True,
                       env=dict(os.environ, MEGAMEK=os.path.abspath(a.megamek)))
    os.makedirs(os.path.dirname(os.path.abspath(a.records)), exist_ok=True)
    os.makedirs(os.path.join(a.megamek, "savegames"), exist_ok=True)
    results = []
    for n in range(1, a.games + 1):
        r = None
        for attempt in range(3):
            r = play(a, n, os.path.abspath(a.records))
            stalled_at_start = r is None or "error" in r or (not r.get("finished") and r.get("rounds", 0) < 2)
            if not stalled_at_start:
                break
            print(f"  game {n}: stalled at the start ({describe(r)}), playing it again", flush=True)
        results.append(r)
        print(f"game {n}: {describe(r)}", flush=True)
    wins, fallbacks, ours = collections.Counter(), collections.Counter(), collections.Counter()
    for r in results:
        if not r or "error" in r:
            wins["no result"] += 1
            continue
        wins[f"team {r['winning_team']}" if r["finished"] and r["winning_team"] is not None
             else ("draw" if r["finished"] else "unfinished")] += 1
        for b in r.get("bridge", []):
            ours.update(b.get("ours", {}))
            fallbacks.update(b.get("fallbacks", {}))
    print(f"\n{len(results)} games: {dict(wins)}")
    print(f"our engine decided: {dict(ours)}")
    print(f"Princess decided instead: {dict(fallbacks)}")


if __name__ == "__main__":
    main(sys.argv[1:])
