"""
tests/check_play.py - BATTLEROM play (INTEGRATION__PLAYER_DECISIONS.md Section 15): the Lab server's play calls, driven by a
script with no browser. A team whose bot is "human" is played by the script through play_poll / play_answer.

    python tests/check_play.py

Starts engine/target/release/combatlab on a free port, then:
  1. "human" is among the bots the Lab offers;
  2. a batch run or estimate that includes a Human team is refused in words (a person's team cannot be simulated);
  3. play_start without a Human team is refused in words;
  4. a 2 v 2 with Red human plays to its end: every kind of question (move_order, movement, target, declaration, physical)
     comes up and is answered, an illegal answer is asked again with an error, and the battle ends with a winner or a draw;
  5. the same seed with the same answers gives the same battle;
  6. a stand planned together with its move (bug A2): the moves after standing are shown before the roll, turning in place is free,
     and the stand and the move go in one answer.
Exit code 0 = every check passed.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_lab_server import ENGINE, LAB, REPO_ROOT, Lab, check, free_port  # noqa: E402

SETUP = {"teams": [
    {"name": "Red", "colour": "#4b8fd8", "bot": "human", "units": [{"unit": "Atlas AS7-K.mtf", "gunnery": 4, "piloting": 5}, {"unit": "Griffin GRF-1N.mtf", "gunnery": 4, "piloting": 5}]},
    {"name": "Blue", "colour": "#d86a4b", "bot": "gladiator", "units": [{"unit": "Awesome AWS-8Q.mtf", "gunnery": 4, "piloting": 5}, {"unit": "Hunchback HBK-4G.mtf", "gunnery": 4, "piloting": 5}]}],
    "board": "16x17_Grassland_1.board", "battles": 1, "seed": 11, "max_turns": 100}


def play(lab, seed, kinds, wrong_once):
    """One whole game with a scripted player. Returns the end record."""
    g = lab.api("play_start", {"setup": SETUP, "seed": seed})
    gid = g["game"]
    answers = []
    browse_unit = []
    for _ in range(5000):
        p = lab.api("play_poll", {"game": gid, "wait_ms": 30000})
        if p["state"] == "waiting":
            continue
        if p["state"] == "failed":
            raise SystemExit("the engine stopped: " + p["error"])
        if p["state"] == "done":
            return p["end"], answers
        r, seq = p["request"], p["seq"]
        k = r["kind"]
        kinds.add(k)
        if browse_unit and browse_unit[0] != -1:
            # the question right after a planned move is not that unit's movement question again
            assert not (k == "movement" and r["unit"] == browse_unit[0]), "a planned move is not asked again"
            browse_unit[0] = -1
        if k == "deploy":
            ans = {"hex": r["hexes"][0], "facing": "N"}
        elif k == "move_order":
            ans = {"unit": r["candidates"][0]}
            if "browse" not in kinds and len(r["candidates"]) > 1:
                # look over every unit's moves before choosing one, then commit the LAST one with its move planned: its movement
                # question must not come again, and an unknown unit is refused
                kinds.add("browse")
                views = {u: lab.api("play_query", {"game": gid, "query": {"q": "reach", "unit": u}}) for u in r["candidates"]}
                assert all(v.get("view", {}).get("options") for v in views.values()), "every candidate has a reach view: " + json.dumps(views)[:120]
                assert "error" in lab.api("play_query", {"game": gid, "query": {"q": "reach", "unit": 99}}), "an unknown unit is refused"
                last = r["candidates"][-1]
                o = max(views[last]["view"]["options"], key=lambda x: (x["mode"] == "Walk", x["mp"]))
                route = lab.api("play_query", {"game": gid, "query": {"q": "path", "unit": last, "hex": o["hex"], "facing": o["facing"], "mode": o["mode"]}})
                assert route.get("path"), "a route for a unit that is not the one asked about: " + json.dumps(route)[:100]
                # waypoints: the cost of going through a chosen hex, and what is left to reach from there
                vo = views[last]["view"]["options"]
                walks = sorted((x for x in vo if x["mode"] == "Walk"), key=lambda x: x["mp"])
                if len(walks) > 3:
                    h1 = walks[len(walks) // 2]["hex"]
                    w1 = lab.api("play_query", {"game": gid, "query": {"q": "way", "unit": last, "waypoints": [h1]}})
                    assert w1.get("reach") and w1.get("legs"), "a waypoint gives what is reachable from it: " + json.dumps(w1)[:100]
                    h2 = next((x["hex"] for x in w1["reach"] if x["hex"] != h1), None)
                    if h2:
                        w2 = lab.api("play_query", {"game": gid, "query": {"q": "way", "unit": last, "waypoints": [h1, h2]}})
                        direct = min(x["mp"] for x in vo if x["hex"] == h2) if any(x["hex"] == h2 for x in vo) else 0
                        via = min(x["mp"] for x in w2["reach"] if x["hex"] == h2)
                        assert w2["legs"][-1]["hex"] == h2 and via >= direct, f"through a waypoint costs at least the direct way ({via} v {direct})"
                    assert "error" in lab.api("play_query", {"game": gid, "query": {"q": "way", "unit": last, "waypoints": ["9999"]}}), "an impossible waypoint is refused in words"
                browse_unit[:] = [last]
                ans = {"unit": last, "plan": {"hex": o["hex"], "facing": o["facing"], "mode": o["mode"]}}
        elif k == "movement":
            if "path" not in kinds and r["options"]:
                kinds.add("path")
                o = r["options"][-1]
                q = lab.api("play_query", {"game": gid, "query": {"q": "path", "hex": o["hex"], "facing": o["facing"], "mode": o["mode"]}})
                assert q.get("path") is not None, "a path query returns the route: " + json.dumps(q)[:100]
            best = max(r["options"], key=lambda o: (o["mode"] == "Walk", o["mp"]), default=None)
            ans = {"stay": True} if best is None else {"hex": best["hex"], "facing": best["facing"], "mode": best["mode"]}
            walks = sorted((x for x in r["options"] if x["mode"] == "Walk" and x["mp"] >= 2), key=lambda x: x["mp"])
            if "drawn" not in kinds and len(walks) > 3 and not r.get("standup_mp") and not r.get("entry"):
                # a route drawn through waypoints is walked as drawn (Daniel, 2026-11-24): the way query's entries carry the numbers of the
                # route they describe, an answer that does not end at the last waypoint is refused in words, and a right one is accepted
                kinds.add("drawn")
                # a waypoint the drawn route can reach: its legs go forward and turn only (the options above also use backward steps)
                h1, w1, here = None, None, []
                for cand in walks[len(walks) // 2:] + walks[: len(walks) // 2]:
                    w = lab.api("play_query", {"game": gid, "query": {"q": "way", "unit": r["unit"], "waypoints": [cand["hex"]]}})
                    got = [x for x in w.get("reach", []) if x["hex"] == cand["hex"] and x["mode"] == "Walk"]
                    if got:
                        h1, w1, here = cand["hex"], w, got
                        break
                assert here, "some waypoint among the Walk options can be drawn to"
                assert all(k in here[0] for k in ("mp", "hexes", "tmm", "heat", "psrs", "hazard")), "a way entry carries the route's own numbers: " + json.dumps(here[0])
                e = here[0]
                other = next((x["hex"] for x in w1["reach"] if x["hex"] != h1), None)
                if other:
                    lab.api("play_answer", {"game": gid, "seq": seq, "answer": {"hex": other, "facing": e["facing"], "mode": "Walk", "waypoints": [h1]}})
                    again = lab.api("play_poll", {"game": gid, "wait_ms": 30000})
                    assert "last waypoint" in (again["request"].get("error") or ""), "a drawn move that ends elsewhere is refused in words: " + str(again["request"].get("error"))
                    seq = again["seq"]
                ans = {"hex": h1, "facing": e["facing"], "mode": "Walk", "waypoints": [h1]}
        elif k == "target":
            if not wrong_once[0]:
                wrong_once[0] = True
                lab.api("play_answer", {"game": gid, "seq": seq, "answer": {"target": 9999}})
                again = lab.api("play_poll", {"game": gid, "wait_ms": 30000})
                wrong_once.append(again["request"].get("error"))
                seq = again["seq"]
            if "preview" not in kinds:
                # the weapons first: the preview query gives the weapon rows (ranges, arcs) and every enemy's real to-hit number per weapon
                kinds.add("preview")
                pv = lab.api("play_query", {"game": gid, "query": {"q": "preview", "unit": r["unit"]}})
                assert pv.get("targets") and pv.get("arcs") is not None, "a target preview returns targets and arcs: " + json.dumps(pv)[:120]
                ready = [t for t in pv["targets"] if t.get("req")]
                assert ready, "at least one enemy can be declared at"
                q0 = ready[0]["req"]
                assert q0["weapons"] and q0["weapons"][0].get("ranges") and "tn" in q0["weapons"][0] and q0.get("breakdown") and q0["breakdown"].get("attacker_mode"), "each target carries the declaration's body with the numbers in parts"
                assert all(t["id"] in [e["id"] for e in r["enemies"]] for t in pv["targets"]), "the preview covers the enemies asked about"
                # a secondary target (p.64): with a primary named, the others are worked out as secondary (+1) or refused in words
                if len(pv["targets"]) > 1:
                    p2 = lab.api("play_query", {"game": gid, "query": {"q": "preview", "unit": r["unit"], "primary": ready[0]["id"]}})
                    other = [t for t in p2["targets"] if t["id"] != ready[0]["id"]]
                    assert all((t.get("req") and t["req"]["secondary"]) or t.get("why") or t.get("req") is None for t in other), "the others are secondary targets"
            ans = {"target": None if r.get("secondary") else r["enemies"][0]["id"]}
        elif k == "declaration":
            if "decl" not in kinds:
                # the weapon table carries the to-hit parts, and a mode change / switch query is answered while the question waits
                kinds.add("decl")
                assert r["breakdown"]["base"] == r["base_tn"], "the to-hit breakdown has a base"
                w0 = next((w for w in r["weapons"] if w["in_range"]), None)
                q = lab.api("play_query", {"game": gid, "query": {"q": "set", "unit": r["unit"], "modes": {}}})
                assert "weapons" in q and len(q["weapons"]) == len(r["weapons"]), "a 'set' query returns the weapon table"
                sw = lab.api("play_query", {"game": gid, "query": {"q": "switches", "unit": r["unit"], "switches": {"coolant": "hold", "sinks_off": None}}})
                assert sw["equipment"]["coolant"]["mode"] == "hold", "an equipment switch is applied while a question waits"
                lab.api("play_query", {"game": gid, "query": {"q": "switches", "unit": r["unit"], "switches": {"coolant": "auto"}}})
            ans = {"weapons": [w["id"] for w in r["weapons"] if w["in_range"] and not w["needs_twist"]]}
        elif k == "stand_up":
            ans = {"stand": True}
        elif k == "boost":
            ans = {"use": False}
        elif k in ("spot", "tag"):
            ans = {"target": None}
        elif k == "end_phase":
            ans = {}
        else:
            ans = {"kind": r["kinds"][0]["kind"]}
        answers.append((k, json.dumps(ans, sort_keys=True)))
        lab.api("play_answer", {"game": gid, "seq": seq, "answer": ans})
    raise SystemExit("the battle did not end")


def stand_with_plan(lab, gid, r, kinds, pending):
    """The answer to a stand_up question (bug A2): the first time, the stand is planned with its move. The moves after a first-try
    stand are shown before anything is rolled; the unit turns in place (any facing is free after standing, p.51) and the stand and
    the move go in one answer."""
    if any(x.startswith("stand_plan") for x in kinds):
        # the second time: stay prone and turn on the ground (1 MP a hexside, p.51)
        if r.get("prone_turns") and not any(x.startswith("prone_turn") for x in kinds):
            t = r["prone_turns"][0]
            pending.append((r["unit"], t["facing"], "prone"))
            kinds.add("prone_turn_sent")
            return {"stand": False, "facing": t["facing"]}
        return {"stand": True}
    v = lab.api("play_query", {"game": gid, "query": {"q": "reach", "unit": r["unit"]}})["view"]
    me = next(x for x in r["units"] if x["id"] == r["unit"])
    turn = [o for o in v["options"] if o["hex"] == me["hex"] and o["facing"] != me["facing"] and o["mp"] == 0]
    assert v["standup_mp"] == r["run"] - 2 and len(turn) == 5, "after standing every other facing is free: " + json.dumps(turn)[:200]
    o = turn[0]
    pending.append((r["unit"], o["facing"]))
    kinds.add("stand_plan_sent")
    return {"stand": True, "plan": {"hex": o["hex"], "facing": o["facing"], "mode": o["mode"]}}


def after_stand(r, k, kinds, pending):
    """The question after a planned stand: stood -> the planned facing and NO movement question for it."""
    if not pending:
        return
    u, facing, *how = pending.pop()
    me = next(x for x in r["units"] if x["id"] == u)
    if how == ["drop"]:
        kinds.add("drop_ok" if me.get("prone") and me["facing"] == facing else f"drop_bad: prone {me.get('prone')}, facing {me['facing']} (planned {facing})")
        return
    if how:
        kinds.add("prone_turn_ok" if me.get("prone") and me["facing"] == facing else f"prone_turn_bad: facing {me['facing']} (asked {facing}), prone {me.get('prone')}")
        return
    if me.get("prone"):
        kinds.add("stand_plan_roll_failed")
    elif not (k == "movement" and r["unit"] == u) and me["facing"] == facing:
        kinds.add("stand_plan_ok")
    else:
        kinds.add(f"stand_plan_bad: next {k} for {r.get('unit')}, facing {me['facing']} (planned {facing})")


KIT = {"teams": [
    {"name": "Red", "colour": "#4b8fd8", "bot": "human", "units": [{"unit": n, "gunnery": 4, "piloting": 5} for n in ("meks/3050U/Caesar CES-4R.mtf", "meks/3055U/Stealth STH-2D2.mtf", "meks/Golden Century/Minsk 2.mtf", "meks/3058Uu/Spartan SPT-N1.mtf")]},
    {"name": "Blue", "colour": "#d86a4b", "bot": "gladiator", "units": [{"unit": n, "gunnery": 4, "piloting": 5} for n in ("Atlas AS7-K.mtf", "Awesome AWS-8Q.mtf")]}],
    "board": "16x17_Grassland_1.board", "battles": 1, "seed": 7, "max_turns": 100}


def kit_game(lab, kinds):
    """A game with MASC, TAG, coolant pods and AMS on the person's side: the rarer questions, every mode and switch answered."""
    gid = lab.api("play_start", {"setup": KIT, "seed": 7})["game"]
    pending = []
    power_unit = []
    eject_unit = []
    for _ in range(20000):
        p = lab.api("play_poll", {"game": gid, "wait_ms": 30000})
        if p["state"] == "waiting":
            continue
        if p["state"] == "failed":
            raise SystemExit("the engine stopped: " + p["error"])
        if p["state"] == "done":
            return p["end"]
        r, seq = p["request"], p["seq"]
        k = r["kind"]
        kinds.add(k)
        for line in r.get("log", []):
            if "SHUT DOWN (by choice" in line: kinds.add("power_log_off")
            if "stays shut down (by choice" in line: kinds.add("power_log_held")
            if "restart chosen" in line: kinds.add("power_log_restart")
            if "EJECTS (TO:AR" in line: kinds.add("eject_log")
            if "abandoned - out of the battle" in line: kinds.add("eject_out")
        after_stand(r, k, kinds, pending)
        if k == "deploy":
            ans = {"hex": r["hexes"][0], "facing": "N"}
        elif k == "move_order":
            ans = {"unit": r["candidates"][0]}
        elif k == "stand_up":
            ans = stand_with_plan(lab, gid, r, kinds, pending)
        elif k == "boost":
            ans = {"use": True}
        elif k == "movement" and "power_held_seen" in kinds and "eject_sent" not in kinds and power_unit and r["unit"] != power_unit[0]:
            # last of the engine-pass checks: one MechWarrior ejects (TO:AR p.164) and the 'Mech leaves the battle
            ans = {"eject": True}; kinds.add("eject_sent"); eject_unit.append(r["unit"])
        elif k == "movement":
            if r["attacks"] and "attack" not in kinds:
                kinds.add("attack")
                a = r["attacks"][0]
                q = lab.api("play_query", {"game": gid, "query": {"q": "path", "attack": a}})
                assert q.get("path"), "a charge's route is returned: " + json.dumps(q)[:80]
                ans = {"attack": a}
            else:
                best = max(r["options"], key=lambda o: (o["mode"] == "Run", o["mp"]), default=None)
                ans = {"stay": True} if best is None else {"hex": best["hex"], "facing": best["facing"], "mode": best["mode"]}
                # once: a walk that leaves 1 MP drops to the ground at the end (p.51)
                walk = [o for o in r["options"] if o["mode"] == "Walk" and 0 < o["mp"] < r["run"]]
                if walk and not any(x.startswith("drop_") for x in kinds):
                    o = walk[0]
                    ans = {"hex": o["hex"], "facing": o["facing"], "mode": o["mode"], "prone": True}
                    pending.append((r["unit"], o["facing"], "drop"))
                    kinds.add("drop_sent")
        elif k == "spot":
            ans = {"target": r["candidates"][0]["id"], "fires": True}
        elif k == "tag":
            c = r["candidates"][0]
            ans = {"target": c["id"], "aim": "mech" if c["tn_mech"] is not None else "hex"}
        elif k == "target":
            ans = {"target": None if r.get("secondary") else r["enemies"][0]["id"]}
        elif k == "declaration":
            # TAG is used in its own step before the Ranged Attack Phase (Core p.200; bug B11): never a row of the weapon list
            assert not any(w["name"].endswith("TAG") for w in r["weapons"]), "TAG offered as a ranged weapon: " + str([w["name"] for w in r["weapons"]])
            modes = {str(w["id"]): w["modes"][-1]["label"] for w in r["weapons"] if w["modes"]}
            shots = {str(w["id"]): w["rates"][-1]["shots"] for w in r["weapons"] if w["rates"]}
            rows = lab.api("play_query", {"game": gid, "query": {"q": "set", "unit": r["unit"], "modes": modes, "shots": shots}})["weapons"] if (modes or shots) else r["weapons"]
            ans = {"weapons": [w["id"] for w in rows if w["in_range"] and not w["needs_twist"] and not w["jammed"]], "modes": modes, "shots": shots}
        elif k == "end_phase":
            ans = {"switches": {"coolant": "now", "radical": r["equipment"]["radical"]["live"]}}
            # voluntary shutdown (p.105): one unit shuts down by choice, stays down one End Phase, then asks for a restart
            pw = r["equipment"].get("power") or {}
            if not any(x.startswith("power_") for x in kinds) and not pw.get("shutdown"):
                ans["switches"]["power"] = "off"; kinds.add("power_off_sent"); power_unit.append(r["unit"])
            elif power_unit and r["unit"] == power_unit[0] and pw.get("by_choice"):
                kinds.add("power_held_seen")
                if "power_held_seen2" in kinds:
                    ans["switches"]["power"] = "on"; kinds.add("power_on_sent")
                kinds.add("power_held_seen2")
        elif k == "physical":
            ans = {"kind": r["kinds"][0]["kind"]}
        else:
            ans = {}
        lab.api("play_answer", {"game": gid, "seq": seq, "answer": ans})
    raise SystemExit("the kitchen game did not end")


def main():
    subprocess.run(["cargo", "build", "--release", "-q", "-p", "combatlab"], cwd=ENGINE, check=True, capture_output=True)
    port = free_port()
    proc = subprocess.Popen([LAB, "--no-browser", "--port", str(port)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=dict(os.environ, BTSIM_ROOT=REPO_ROOT))
    failures = []
    try:
        line = proc.stdout.readline()
        if "running" not in line:
            raise SystemExit("combatlab did not start: " + line + proc.stderr.read())
        lab = Lab(port)
        check("human" in lab.api("info")["bots"], "the Lab offers a Human bot", failures)
        e = lab.api("run", {"setup": SETUP}).get("error", "")
        check("Human" in e and "Play" in e, f"a batch with a Human team is refused in words ({e[:60]}...)", failures)
        e = lab.api("estimate", {"setup": SETUP}).get("error", "")
        check("Human" in e, "an estimate with a Human team is refused", failures)
        no_human = json.loads(json.dumps(SETUP)); no_human["teams"][0]["bot"] = "gladiator"
        e = lab.api("play_start", {"setup": no_human}).get("error", "")
        check("Human" in e, f"play_start with no Human team is refused ({e[:50]}...)", failures)
        kinds, wrong = set(), [False]
        end, ans1 = play(lab, 11, kinds, wrong)
        check({"move_order", "movement", "target", "declaration"} <= kinds, f"the questions that came up: {sorted(kinds)}", failures)
        check(len(wrong) == 2 and bool(wrong[1]), "an illegal answer is asked again with an error", failures)
        check("drawn" in kinds, "a route drawn through a waypoint is accepted when it ends at the waypoint, refused in words when it does not, and its way entries carry the route's numbers (2026-11-24)", failures)
        check(end["winner"] in ("Red", "Blue", "Draw") and end["turns"] > 0, f"the battle ends: {end['winner']} after {end['turns']} turns, {end['decisions']} decisions", failures)
        end2, ans2 = play(lab, 11, set(), [True, None])
        check(ans1 == ans2 and end["winner"] == end2["winner"] and end["turns"] == end2["turns"], "the same seed and answers give the same battle", failures)
        kk = set()
        end3 = kit_game(lab, kk)
        check({"boost", "declaration", "end_phase", "spot"} <= kk, f"a game with MASC, TAG, coolant pods and AMS on the person's side: questions {sorted(kk)}", failures)
        check(end3["winner"] in ("Red", "Blue", "Draw"), f"... and it ends: {end3['winner']} after {end3['turns']} turns", failures)
        sp = sorted(x for x in kk if x.startswith("stand_plan"))
        ej = sorted(x for x in kk if x.startswith("eject"))
        check({"eject_sent", "eject_log", "eject_out"} <= kk, f"a MechWarrior ejects instead of moving; the 'Mech leaves the battle (TO:AR p.164; {ej})", failures)
        pw = sorted(x for x in kk if x.startswith("power_"))
        check({"power_log_off", "power_log_held", "power_log_restart"} <= kk, f"a voluntary shutdown stays down until the person asks for a restart (p.105; {pw})", failures)
        dr = sorted(x for x in kk if x.startswith("drop_"))
        check("drop_ok" in kk, f"a move answered with prone: true ends with the unit dropped to the ground, same facing (p.51; {dr})", failures)
        pt = sorted(x for x in kk if x.startswith("prone_turn"))
        check("prone_turn_ok" in kk or not pt, f"a unit that stays prone turns on the ground when asked (p.51; {pt or 'no second stand question in this game'})", failures)
        check("stand_plan_ok" in kk or "stand_plan_roll_failed" in kk, f"a stand planned together with its move (turning in place) stands and moves with no second question (A2; {sp})", failures)
    finally:
        proc.kill()
    if failures:
        print(f"\n{len(failures)} check(s) FAILED")
        return 1
    print("\nall play checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
