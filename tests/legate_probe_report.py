"""
tests/legate_probe_report.py - reads tests/legate_probe.py output(s) and prints Daniel's five suspects
(2026-10-30): A the enemy position estimate, B damage taken (predicted / at the true spots / actual),
C the regret of the choice, D the primary foe v who fired, E cohesion, F calibration (with --calib).
    python tests/legate_probe_report.py OUT.json [more.json ...]
"""
import json, os, sys, statistics as st
from collections import defaultdict
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("", "pathfinder", "mechsim"):
    sys.path.insert(0, os.path.join(REPO, sub))
import hex_geometry
from los import hex_distance

xy = hex_geometry.parse_hex_label
dist = lambda a, b: hex_distance(xy(a), xy(b))
CLASS = {"Atlas": "assault", "Emperor": "assault", "Awesome": "assault", "Archer": "heavy", "Cataphract": "heavy",
         "Catapult": "heavy", "Kintaro": "medium", "Griffin": "medium", "Hunchback": "medium", "Jenner": "light",
         "Commando": "light", "Locust": "light"}
cls = lambda n: CLASS[n.split()[1]]
team = lambda n: n.split()[0]
bucket = lambda t: "t1-3" if t <= 3 else "t4-10" if t <= 10 else "t11+"
mean = lambda v: sum(v) / len(v) if v else float("nan")

battles = []
for p in sys.argv[1:]:
    battles += json.load(open(p))["battles"]
print(f"{len(battles)} battles")

# A. Where the enemy goes: Legate's estimate vs hold vs truth ------------------------------------
err_est, err_hold, moved, adv_bias = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
dmg_err = defaultdict(list)
for b in battles:
    for t, T in enumerate(b["turn_log"], 1):
        plan = T["plans"].get("Blue", {})
        blue_end = [h for n, h in T["end"].items() if team(n) == "Blue"]
        for n, est in plan.items():
            real, start = T["end"].get(n), T["start"].get(n)
            if real is None or start is None or not blue_end:
                continue
            k = bucket(t)
            err_est[k].append(dist(est, real)); err_hold[k].append(dist(start, real)); moved[k].append(dist(start, real))
            # signed: how much closer to Gladiator's force the estimate put it than it really went
            near = lambda h: min(dist(h, g) for g in blue_end)
            adv_bias[k].append(near(real) - near(est))      # + = estimate too close (enemy held back more)
print("\nA. ENEMY POSITION ESTIMATE (hexes; Princess units, Gladiator's Legate plan)")
for k in ("t1-3", "t4-10", "t11+"):
    e = err_est[k]
    print(f"  {k:6s} n={len(e):4d}  estimate off by {mean(e):4.2f} (median {st.median(e) if e else 0})"
          f" | 'stands still' off by {mean(err_hold[k]):4.2f} | estimate exact {mean([x == 0 for x in e]):.0%}, "
          f"within 2: {mean([x <= 2 for x in e]):.0%} | estimate closer to us than truth by {mean(adv_bias[k]):+.2f}")

# B. Damage: predicted at estimated spots, same model at true spots, actually taken ----------------
rows = []
for b in battles:
    for t, T in enumerate(b["turn_log"], 1):
        for m in T["moves"]:
            if m["team"] != "Blue" or "on_me" not in m or "true_on_me" not in m:
                continue
            m = dict(m, turn=t, taken=T["taken"].get(m["mover"], 0.0), dealt_real=T["dealt"].get(m["mover"], 0.0),
                     shooters=[a for a, tg in T["fire"].items() if tg == m["mover"]], target=T["fire"].get(m["mover"]),
                     obj=T.get("obj", {}).get(m["mover"]))
            rows.append(m)
print(f"\nB. DAMAGE TAKEN THIS TURN, Gladiator movers ({len(rows)} moves with a Legate score)")
print("   predicted = the model at Legate's estimated spots (what it decided on); true-spot = the same model with"
      "\n   each enemy where it really ended; actual = the Ranged Attack Phase")
for k in ("t1-3", "t4-10", "t11+", "all"):
    R = [r for r in rows if k == "all" or bucket(r["turn"]) == k]
    if not R:
        continue
    pred = mean([sum(r["on_me"].values()) for r in R]); true = mean([sum(r["true_on_me"].values()) for r in R])
    act = mean([r["taken"] for r in R])
    pd = mean([max(r["on_them"].values() or [0]) for r in R]); ad = mean([r["dealt_real"] for r in R])
    print(f"  {k:6s} n={len(R):4d}  taken: predicted {pred:5.1f} | true-spot {true:5.1f} | actual {act:5.1f}"
          f"   ratio pred/actual {pred / act if act else float('nan'):4.1f}x | dealt: predicted {pd:4.1f} actual {ad:4.1f}")
by_cls = defaultdict(list)
for r in rows:
    by_cls[cls(r["mover"])].append(r)
for c, R in by_cls.items():
    pred = mean([sum(r["on_me"].values()) for r in R]); act = mean([r["taken"] for r in R])
    true = mean([sum(r["true_on_me"].values()) for r in R])
    print(f"   {c:8s} n={len(R):4d} predicted {pred:5.1f} true-spot {true:5.1f} actual {act:5.1f}")
# per-move error degree: absolute, and how often the estimate UNDER-stated what the true spots give
under = [sum(r["true_on_me"].values()) - sum(r["on_me"].values()) for r in rows]
print(f"   position error per move (true-spot - predicted): mean {mean(under):+.1f}, mean |x| {mean([abs(x) for x in under]):.1f},"
      f" under-predicted by >10: {mean([x > 10 for x in under]):.0%}, over by >10: {mean([x < -10 for x in under]):.0%}")
# who shoots: does the expected-fire share match reality?
share_pred = [len(r["on_me"]) for r in rows]
print(f"   enemies counted as shooting me (predicted): {mean(share_pred):.1f}; actually shot at me: {mean([len(r['shooters']) for r in rows]):.2f}")

# C. Regret: how much the wrong prediction cost the choice ---------------------------------------
print("\nC. REGRET (score points; the spots the mover looked at, re-scored with the enemy's true end spots)")
for k in ("t1-3", "t4-10", "t11+", "all"):
    R = [r for r in rows if (k == "all" or bucket(r["turn"]) == k) and "true_score_best" in r]
    if not R:
        continue
    reg = [r["true_score_best"] - r["true_score_chosen"] for r in R]
    rel = [g / abs(r["true_score_best"]) for g, r in zip(reg, R) if abs(r["true_score_best"]) > 1e-9]
    over = [r["pred_score_chosen"] - r["true_score_chosen"] for r in R]
    far = [dist(r["to"], r["true_best_hex"]) for r in R]
    print(f"  {k:6s} n={len(R):4d} regret mean {mean(reg):6.1f} (median {st.median(reg):5.1f}), {mean(rel):5.1%} of the best; "
          f"zero-regret {mean([g < 1e-6 for g in reg]):.0%} | chosen spot's score over-rated by {mean(over):+6.1f} | best spot {mean(far):.1f} hexes away")

# D. The wrong unit: primary foe vs who actually shot ---------------------------------------------
print("\nD. PRIMARY FOE (the one it plans the two-ply against) vs who actually fired at it")
fired = [r for r in rows if r["shooters"]]
print(f"  moves where someone shot it: {len(fired)}/{len(rows)}; primary among the shooters: "
      f"{mean([r['primary'] in r['shooters'] for r in fired]):.0%}; primary was the biggest predicted source: "
      f"{mean([max(r['on_me'], key=r['on_me'].get) == r['primary'] for r in rows if r['on_me']]):.0%}")
print(f"  primary's predicted share of damage on me: {mean([r['on_me'].get(r['primary'], 0) / max(sum(r['on_me'].values()), 1e-9) for r in rows]):.0%}"
      f"; shooters per hit unit: {mean([len(r['shooters']) for r in fired]):.2f}")
print(f"  mover shot its own primary: {mean([r['target'] == r['primary'] for r in rows if r['target']]):.0%}")
lifes = [r["obj"] for r in rows if r["obj"]]
if lifes:
    print(f"  objective: HP {mean([o['hp'] for o in lifes]):.0f}, enemies' future on me {mean([o['theirs'] for o in lifes]):.1f}/turn, "
          f"my future {mean([o['mine'] for o in lifes]):.1f}/turn -> life {mean([o['hp'] / o['theirs'] for o in lifes]):.1f} turns, "
          f"over {mean([o['foes'] for o in lifes]):.1f} foes")

# E. Cohesion ---------------------------------------------------------------------------------------
print("\nE. COHESION after movement (hexes): nearest friend / units with no friend within 4 / ahead of the team and alone")
for k in ("t1-3", "t4-10", "t11+"):
    out = {}
    for side in ("Red", "Blue"):
        nf, alone, exposed = [], [], []
        for b in battles:
            for t, T in enumerate(b["turn_log"], 1):
                if bucket(t) != k:
                    continue
                pos = T["pos"]
                mine = {n: h for n, h in pos.items() if team(n) == side}
                foes = [h for n, h in pos.items() if team(n) != side]
                if len(mine) < 2 or not foes:
                    continue
                front = {n: min(dist(h, f) for f in foes) for n, h in mine.items()}
                med = st.median(front.values())
                for n, h in mine.items():
                    d = min(dist(h, g) for m2, g in mine.items() if m2 != n)
                    nf.append(d); alone.append(d > 4); exposed.append(d > 4 and front[n] < med)
        out[side] = f"{mean(nf):4.1f} / {mean(alone):4.0%} / {mean(exposed):4.0%}"
    print(f"  {k:6s} Princess {out['Red']}   Gladiator {out['Blue']}")

# F. Calibration: the model's expected damage for the pairs that really fired, everyone at their real spots
pairs = []
for b in battles:
    for t, T in enumerate(b["turn_log"], 1):
        model = T.get("model")
        if not model:
            continue
        for a, tg in T["fire"].items():
            if tg is None:
                continue
            got = model.get(a + "|" + tg, (None, None, None))
            m, d, raw = (list(got) + [None])[:3]
            if isinstance(m, str) or isinstance(raw, str):
                continue
            pairs.append((team(a), t, m or 0.0, d or 0.0, T["dealt"].get(a, 0.0), raw or 0.0))
if pairs:
    print("\nF. CALIBRATION, pairs that fired, everyone at their real spots (expected damage per attack)")
    for side, who in (("Red", "Princess firing"), ("Blue", "Gladiator firing")):
        P = [p for p in pairs if p[0] == side]
        if not P:
            continue
        print(f"  {who:17s} n={len(P):4d}  movement model {mean([p[2] for p in P]):5.2f} (raw points {mean([p[5] for p in P]):5.2f}) | fire phase's dry run "
              f"{mean([p[3] for p in P]):5.2f} | actual {mean([p[4] for p in P]):5.2f}")
        for k in ("t1-3", "t4-10", "t11+"):
            Q = [p for p in P if bucket(p[1]) == k]
            if Q:
                print(f"     {k:6s} n={len(Q):4d}  model {mean([p[2] for p in Q]):5.2f} (raw {mean([p[5] for p in Q]):5.2f}) | dry run {mean([p[3] for p in Q]):5.2f} | actual {mean([p[4] for p in Q]):5.2f}")
