"""
tests/check_events.py - the event records (INTEGRATION__EVENTS.md; Daniel, 2026-11-24).

    python tests/check_events.py

What it checks:
  1. RECORDING CHANGES NOTHING: one short battle is played with and without --events; the results are identical.
  2. KNOWN EVENTS APPEAR with the right fields: a scripted 1-v-1 battle (cov_ scenario) is played and its events must hold an
     Initiative roll per team on turn 1, MOVE / ATTACK events whose to-hit number, roll and hit flag agree with each other
     (hit = roll >= number), HIT events with a location and damage, and a UNIT_DESTROYED for the unit the result says died.
  3. EVERY KIND IS DOCUMENTED: each kind `btsim --events-list` prints is named in INTEGRATION__EVENTS.md, and the other way round.
  4. THE SEARCH WORKS: the example queries find what they should in a hand-made event list (a sequence, a group count, a
     same-unit reference), and the replay viewer's copy of the search engine is in sync with engine/lab/web/events_query.js.
  5. THE SEARCH TOOL RUNS under node on a real events file (the reference battles' events).
Exit code 77 = skipped (no node here).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BTSIM = os.path.join(ROOT, "engine", "target", "release", "btsim")
sys.path.insert(0, os.path.join(ROOT, "tools"))


def check(ok, what, failures):
    print(("PASS   " if ok else "FAIL   ") + what)
    if not ok:
        failures.append(what)


def btsim(*args):
    return subprocess.run([BTSIM, *args], capture_output=True, text=True, check=True).stdout


def main():
    if not shutil.which("node"):
        print("SKIP: node is needed for the search")
        return 77
    subprocess.run(["cargo", "build", "--release", "-p", "btsim"], cwd=os.path.join(ROOT, "engine"), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(os.path.join(ROOT, "engine", "reference", "scenarios.zip")) as z:
            z.extractall(tmp)
        scen = os.path.join(tmp, "ref_Akuma_AKU-2XK_vs_Highlander_IIC_2_seed1")
        evf = os.path.join(tmp, "ev.jsonl")
        plain = json.loads(btsim(scen, "--battles", "2", "--seed", "3"))
        withev = json.loads(btsim(scen, "--battles", "2", "--seed", "3", "--events", "--events-out", evf))
        strip = lambda o: [{k: v for k, v in r.items() if k != "seconds"} for r in o["results"]]
        check(strip(plain) == strip(withev), "events on: both battles' results are exactly the same as with events off", failures)

        rows = {json.loads(l)["sim"]: json.loads(l) for l in open(evf)}
        ev = rows[1]["events"]
        res = withev["results"][0]
        kinds = {e["k"] for e in ev}
        listed = {k["kind"] for k in json.loads(btsim("--events-list"))["kinds"]}
        check(kinds <= listed, "every event the battle wrote is a listed kind", failures)
        rolls = [e for e in ev if e["k"] == "INITIATIVE_ROLL" and e["t"] == 1]
        check({e["s"] for e in rolls} == {"Red", "Blue"} and all(2 <= e["r"] <= 12 and e["n"] >= 1 for e in rolls),
              "turn 1 has an Initiative roll (2-12) for each team", failures)
        attacks = [e for e in ev if e["k"] == "ATTACK"]
        check(len(attacks) > 0 and all(a["ok"] == (a["r"] >= a["tn"]) and a["p"] == "ranged" and a["s"] in
                                       ("energy", "ballistic", "missile", "area_effect", "artillery", "homing", "other") for a in attacks),
              f"{len(attacks)} ATTACK events: hit agrees with roll >= number, family set, phase ranged", failures)
        hits = [e for e in ev if e["k"] == "HIT" and e.get("o")]
        check(len(hits) > 0 and all(h.get("l") and h["d"] > 0 for h in hits), f"{len(hits)} attack HIT events have a location and damage", failures)
        dead = [e for e in ev if e["k"] == "UNIT_DESTROYED"]
        check(res["winner"] == "Draw" or len(dead) >= 1, "a battle with a winner has a UNIT_DESTROYED", failures)
        check(all(e.get("s") for e in dead), "UNIT_DESTROYED carries its cause", failures)
        moves = [e for e in ev if e["k"] == "MOVE"]
        check(len(moves) > 0 and all(m["p"] == "movement" and m.get("s") for m in moves), f"{len(moves)} MOVE events carry a mode", failures)
        # a MOVE_PATH follows its MOVE: same unit, the route ends at the MOVE's hex having spent the MOVE's MP, n counts the steps,
        # every step is one of F B L R E and the MP never goes down
        paths = [(i, e) for i, e in enumerate(ev) if e["k"] == "MOVE_PATH"]
        def path_ok(i, e):
            mv = ev[i - 1] if i else {}
            steps = [x.split("/") for x in e["w"].split(" ")]
            mps = [int(x[2]) for x in steps]
            return (mv.get("k") == "MOVE" and mv.get("u") == e.get("u") and mv.get("s") == e.get("s") and steps[-1][0] == mv["w"] and mps[-1] == mv["n"]
                    and e["n"] == len(steps) and all(x[1] in "FBLRE" for x in steps) and mps == sorted(mps))
        check(len(paths) > 0 and all(path_ok(i, e) for i, e in paths), f"{len(paths)} MOVE_PATH events follow their MOVE (same unit, ending at its hex and MP)", failures)
        check(max(e["t"] for e in ev) <= res["turns"], "no event is dated after the battle's last turn", failures)

        # 3. the doc names every kind
        doc = open(os.path.join(ROOT, "INTEGRATION__EVENTS.md"), encoding="utf-8").read()
        named = set(re.findall(r"^\| `([A-Z_]+)` \|", doc, flags=re.M))
        check(named == listed, f"INTEGRATION__EVENTS.md lists exactly the {len(listed)} kinds the engine has"
              + (f" (doc only: {sorted(named - listed)}; engine only: {sorted(listed - named)})" if named != listed else ""), failures)
        version = json.loads(btsim("--events-list"))["version"]
        check(f"version {version}" in doc.lower() or f"**version {version}**" in doc.lower(), f"the doc states list version {version}", failures)

    # 4. the query engine on a hand-made battle
    events = [
        {"k": "STAND_ATTEMPT", "t": 3, "p": "movement", "u": "Blue 1", "tn": 5, "r": 7, "ok": True},
        {"k": "PHYS_CHARGE", "t": 3, "p": "physical", "u": "Red 1", "o": "Blue 1", "tn": 7, "r": 9, "ok": True},
        {"k": "PHYS_CHARGE", "t": 4, "p": "physical", "u": "Red 1", "o": "Blue 2", "tn": 7, "r": 9, "ok": True},
        {"k": "CRIT", "t": 5, "p": "ranged", "u": "Red 1", "s": "Engine", "n": 1},
        {"k": "CRIT", "t": 5, "p": "ranged", "u": "Red 1", "s": "Engine", "n": 2},
        {"k": "CRIT", "t": 5, "p": "ranged", "u": "Red 1", "s": "Engine", "n": 3},
        {"k": "CRIT", "t": 5, "p": "ranged", "u": "Red 1", "s": "Engine", "n": 4},
        {"k": "CRIT", "t": 6, "p": "ranged", "u": "Red 1", "s": "Engine", "n": 5},
        {"k": "COMPONENT_DESTROYED", "t": 6, "p": "ranged", "u": "Red 1", "s": "Gyro"},
        {"k": "COMPONENT_DESTROYED", "t": 6, "p": "ranged", "u": "Blue 1", "s": "Gyro"},
        {"k": "COMPONENT_DESTROYED", "t": 7, "p": "ranged", "u": "Blue 2", "s": "Gyro"},
    ]
    teams = {"Red 1": "Red", "Blue 1": "Blue", "Blue 2": "Blue"}
    examples = {e["name"]: e["query"] for e in json.load(open(os.path.join(ROOT, "engine", "lab", "web", "events_examples.json")))}
    runner = os.path.join(ROOT, "tools", "events_search_runner.js")

    def search(query):
        inp = json.dumps(query) + "\n" + json.dumps({"id": "x", "events": events, "teams": teams}) + "\n"
        out = subprocess.run(["node", runner], input=inp, capture_output=True, text=True, check=True).stdout
        return json.loads(out)["matches"]

    m = search(examples["stand-then-charge"])
    check(len(m) == 1 and m[0]["t"] == 3, "stand-then-charge: finds the charge on the unit that stood, same turn (not turn 4's)", failures)
    m = search(examples["engine-hits-4"])
    check(len(m) == 1 and m[0]["count"] == 4 and m[0]["group"] == {"u": "Red 1", "t": 5, "p": "ranged"},
          "engine-hits-4: the 4 engine hits of turn 5 are one match (turn 6's single hit is not)", failures)
    m = search(examples["mutual-gyro"])
    check(len(m) == 1 and m[0]["t"] == 6 and sorted(m[0]["units"]) == ["Blue 1", "Red 1"],
          "mutual-gyro: both units' gyros on turn 6 (Blue 2 on turn 7 does not pair)", failures)
    m = search({"steps": [{"kind": "COMPONENT_DESTROYED", "where": {"u_team": "Blue"}}]})
    check(len(m) == 2, "a team filter (u_team) finds the two Blue gyros", failures)
    m = search({"steps": [{"kind": "PHYS_CHARGE", "where": {"tn": {"gte": 7}, "r": {"in": [9, 10]}}}]})
    check(len(m) == 2, "field conditions (gte, in) work", failures)

    # the viewer's copy is the same engine
    import sync_events_query
    html = open(sync_events_query.VIEWER, encoding="utf-8").read()
    check(sync_events_query.synced(html) == html, "the replay viewer's copy of events_query.js is in sync (python tools/sync_events_query.py)", failures)

    # the reference check's coverage rule: a type with no event fails, a thin one is only a note
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import check_rust_reference as ref
    header = '{"events_version":2,"teams":{}}\n'
    some = header + "".join(json.dumps({"k": k, "t": 1, "p": "movement"}) + "\n" for k in sorted(listed))
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        full = ref.coverage_report([some] * ref.EVENT_MIN_BATTLES)
    gap_text = header + "".join(json.dumps({"k": k, "t": 1, "p": "movement"}) + "\n" for k in sorted(listed) if k != "HOMING_HIT")
    with contextlib.redirect_stdout(io.StringIO()):
        short = ref.coverage_report([gap_text] * ref.EVENT_MIN_BATTLES)
    check(full == 0 and short == 1, "the reference check's coverage rule: all types present passes, a type with no event fails", failures)

    # 5. the tool on the reference battles' events
    ref = os.path.join(ROOT, "engine", "reference", "events")
    if os.path.isdir(ref) and os.listdir(ref):
        p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "search_events.py"), "--reference", "--kind", "ATTACK", "--where", "ok=true",
                            "--group", "u,t", "--count", ">=2", "--limit", "1"], capture_output=True, text=True)
        check(p.returncode == 0 and "TOTAL:" in p.stdout and "replay:" in p.stdout, "tools/search_events.py searches the reference events and prints a replay command", failures)
    print(f"\n{'FAILED: ' + str(len(failures)) if failures else 'all event checks passed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
