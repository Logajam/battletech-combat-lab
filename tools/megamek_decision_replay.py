"""
tools/megamek_decision_replay.py - does our clone of a MegaMek bot move as the real one did? (session 30)

    python tools/megamek_decision_replay.py TRANSCRIPT.jsonl [...] --unit U2 --team T3 --bot caspar --start 0915 [--start-facing 0]

Reads MegaMek bridge transcripts (MegaMek's logs/bridge_<label>_<player>.jsonl, written by tools/megamek_bridge_games.py):
the state of the whole game at each of OUR engine's decisions. For every round it rebuilds the state the OTHER side's
MegaMek bot (--unit, a 'Mech of team --team, driven in MegaMek by MegaMek's own Princess or CASPAR) saw just before it
moved - the round's start if it moved first, the state after our unit's move if it moved second - asks our engine's
clone (--bot caspar or princess, through `btsim decide`, the bridge's decision process) where it would move, and
compares with where MegaMek's bot really went. Duels only (one unit a side: our unit is the other one). --start: the
unit's hex at the scenario's start (the transcript begins at our engine's first question, after any round-1 move).
Prints one line per decision and the totals (same hex / same hex and facing).
"""
import argparse, copy, json, os, subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BTSIM = os.path.join(REPO_ROOT, "engine", "target", "release", "btsim")
COMPASS = ["N", "NE", "SE", "S", "SW", "NW"]


def distance(a, b):
    def cube(h):
        q, r = int(h[:2]) - 1, int(h[2:]) - 1
        r -= (q - (q & 1)) // 2
        return q, r, -q - r
    x, y = cube(a), cube(b)
    return max(abs(x[i] - y[i]) for i in range(3))


def unit(state, name):
    return next(u for u in state["megamek_units"] if u["name"] == name)


def fresh_round(state, turn):
    """A state at a round's start: nobody has moved or fired yet."""
    s = copy.deepcopy(state)
    s["turn"], s["move_queue"] = turn, []
    for u in s["megamek_units"]:
        u.update({"moved": "Stand Still", "done": False, "mp_spent": 0, "hexes_moved": 0, "fired": []})
    return s


def questions(path, a):
    """(round, state before the bot's move, moves first?, hex before, the bot's unit after its move, our unit's hex)."""
    lines = [json.loads(l) for l in open(path) if l.strip()]
    start = next(l for l in lines if "settings" in l)
    last, ours_asked, end_move = {}, {}, {}
    for l in lines:
        st = l.get("state")
        if not st:
            continue
        t = st["turn"]
        last[t] = st
        if l.get("method") == "choose_movement" and t not in ours_asked:
            ours_asked[t] = st
        if l.get("method") == "end_movement":
            end_move[t] = st
    other = next(f["name"] for f in start["settings"]["FORCES"] if f["name"] != a.unit)   # our unit (a duel)
    out = []
    for t in sorted(end_move):
        if t not in ours_asked:
            continue
        after = unit(end_move[t], a.unit)
        if after.get("destroyed") or after.get("prone") or unit(end_move[t], other).get("destroyed"):
            continue
        if unit(ours_asked[t], a.unit).get("done"):          # it moved first: the round's start
            if (t - 1) not in last:
                if t != 1:
                    continue
                base = copy.deepcopy(ours_asked[1])
                u = unit(base, a.unit)
                u["hex"], u["facing"] = a.start, a.start_facing
                last[0] = base
            pre, first = fresh_round(last[t - 1], t), True
        else:                                                # it moved second: our unit's move done
            pre = copy.deepcopy(end_move[t])
            pre["move_queue"] = []
            before = copy.deepcopy(unit(ours_asked[t], a.unit))
            pre["megamek_units"] = [before if u["name"] == a.unit else u for u in pre["megamek_units"]]
            first = False
        if unit(pre, a.unit).get("prone"):
            continue
        out.append((t, pre, first, unit(pre, a.unit)["hex"], after, unit(pre, other)["hex"]))
    return start, out, other


def main():
    p = argparse.ArgumentParser()
    p.add_argument("transcripts", nargs="+")
    p.add_argument("--unit", required=True)
    p.add_argument("--team", required=True)
    p.add_argument("--bot", choices=["caspar", "princess"], required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--start-facing", type=int, default=0)
    a = p.parse_args()
    total = {"decisions": 0, "same hex": 0, "same hex and facing": 0}
    for path in a.transcripts:
        start, qs, other = questions(path, a)
        names = [f["name"] for f in start["settings"]["FORCES"]]
        mover, foe = names.index(a.unit), names.index(other)
        s = dict(start)
        s["hydra_teams"] = [t for t in s.get("hydra_teams", []) if t != a.team]
        if a.bot == "caspar":
            s["caspar_teams"] = [a.team]
        else:
            for f in s["settings"]["FORCES"]:
                if f["team"] == a.team:
                    f["bot"] = "princess"
        proc = subprocess.Popen([BTSIM, "decide"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, cwd=REPO_ROOT)
        proc.stdin.write(json.dumps(s) + "\n")
        proc.stdin.flush()
        proc.stdout.readline()                               # {"started": true}
        print(f"== {os.path.basename(path)}")
        for t, pre, first, before, after, enemy in qs:
            line = {"method": "choose_movement", "args": {"mover": mover, "other": foe, "moves_first": first, "standup_mp": None,
                                                          "entry_edge": None}, "state": pre}
            proc.stdin.write(json.dumps(line) + "\n")
            proc.stdin.flush()
            ans = json.loads(proc.stdout.readline()).get("answer", {})
            pick = ans.get("pick") or {}
            ours = (pick.get("hex"), str(pick.get("facing")), str(pick.get("mode")))
            real = (after["hex"], COMPASS[after["facing"] % 6], str(after.get("moved")))
            total["decisions"] += 1
            total["same hex"] += ours[0] == real[0]
            total["same hex and facing"] += ours[:2] == real[:2]
            print(f"  t{t:<3} {'first ' if first else 'second'} from {before} (foe at {enemy}, {distance(before, enemy)} away): "
                  f"MegaMek {real[0]} {real[1]:2} {real[2]:11} ours {ours[0]} {ours[1]:2} {ours[2]:11} "
                  f"{'SAME' if ours[0] == real[0] else '    '}  [{ans.get('note') or ''}]")
        proc.stdin.close()
        proc.wait()
    print(total)


if __name__ == "__main__":
    main()
