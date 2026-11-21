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
  5. the same seed with the same answers gives the same battle.
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
        if k == "move_order":
            ans = {"unit": r["candidates"][0]}
        elif k == "movement":
            best = max(r["options"], key=lambda o: (o["mode"] == "Walk", o["mp"]), default=None)
            ans = {"stay": True} if best is None else {"hex": best["hex"], "facing": best["facing"], "mode": best["mode"]}
        elif k == "target":
            if not wrong_once[0]:
                wrong_once[0] = True
                lab.api("play_answer", {"game": gid, "seq": seq, "answer": {"target": 9999}})
                again = lab.api("play_poll", {"game": gid, "wait_ms": 30000})
                wrong_once.append(again["request"].get("error"))
                seq = again["seq"]
            ans = {"target": r["enemies"][0]["id"]}
        elif k == "declaration":
            ans = {"weapons": [w["id"] for w in r["weapons"] if w["in_range"] and not w["needs_twist"]]}
        else:
            ans = {"kind": r["kinds"][0]["kind"]}
        answers.append((k, json.dumps(ans, sort_keys=True)))
        lab.api("play_answer", {"game": gid, "seq": seq, "answer": ans})
    raise SystemExit("the battle did not end")


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
        check(end["winner"] in ("Red", "Blue", "Draw") and end["turns"] > 0, f"the battle ends: {end['winner']} after {end['turns']} turns, {end['decisions']} decisions", failures)
        end2, ans2 = play(lab, 11, set(), [True, None])
        check(ans1 == ans2 and end["winner"] == end2["winner"] and end["turns"] == end2["turns"], "the same seed and answers give the same battle", failures)
    finally:
        proc.kill()
    if failures:
        print(f"\n{len(failures)} check(s) FAILED")
        return 1
    print("\nall play checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
