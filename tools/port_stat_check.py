"""
tools/port_stat_check.py - RUST PORT stage 9: are the two engines the same game on their own dice?

    python tools/port_stat_check.py FIXTURE_OR_OVERRIDES N [--seed S] [--rust-only | --python-only]

Plays N battles of the scenario on the Python engine (its own NumPy dice, all CPU cores) and N on the Rust engine
(`btsim`, its own PCG dice), then compares wins per team, turns, and each team's damage dealt and final HP: a two-sample
z-test (for the win rates, a two-proportion one); any |z| > 3 is reported as a difference. Writes nothing in the repo.
"""
import json
import math
import os
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))
os.chdir(REPO_ROOT)
os.environ.setdefault("INTEGRATION_DATA_DIR", "./data")


def python_batch(statements, max_turns, n, seed):
    import port_record as pr
    import INTEGRATION__config as config
    import INTEGRATION__orchestrator as orchestrator
    import io
    from contextlib import redirect_stdout, redirect_stderr
    config.TIMING = False
    config.STATS = False
    config.MAX_TURNS = max_turns
    pr.apply_overrides(statements)
    config.NUM_SIMULATIONS = n
    config.SEED = seed
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        results = orchestrator.run_batch()
    rows = []
    for r in results:
        rows.append({"turns": r.turns_taken, "winner": r.winner,
                     "teams": {k: {"damage_dealt": s.damage_dealt, "final_hp": s.final_hp} for k, s in r.teams.items()}})
    return rows


def rust_batch(statements, max_turns, n, seed):
    scen = tempfile.mkdtemp(prefix="port_stat_")
    ov = os.path.join(scen, "overrides.json")
    with open(ov, "w", encoding="utf-8") as f:
        json.dump(statements, f)
    subprocess.run([sys.executable, "tools/port_scenario.py", os.path.join(scen, "s"), "--overrides", ov,
                    "--max-turns", str(max_turns)], check=True, env=dict(os.environ, PYTHONHASHSEED="0"),
                   stdout=subprocess.DEVNULL)
    out = os.path.join(scen, "res.json")
    subprocess.run([os.path.join(REPO_ROOT, "engine", "target", "release", "btsim"), os.path.join(scen, "s"),
                    "--battles", str(n), "--seed", str(seed), "--out", out], check=True)
    with open(out, encoding="utf-8") as f:
        data = json.load(f)
    rows = [{"turns": r["turns"], "winner": r["winner"],
             "teams": {k: {"damage_dealt": t["damage_dealt"], "final_hp": t["final_hp"]} for k, t in r["teams"].items()}}
            for r in data["results"]]
    return rows, data["seconds"]


def mean_sd(xs):
    m = sum(xs) / len(xs)
    v = sum((x - m) ** 2 for x in xs) / max(1, len(xs) - 1)
    return m, math.sqrt(v)


def compare(a, b):
    lines, bad = [], 0
    teams = sorted({t for r in a + b for t in r["teams"]})
    winners = sorted({r["winner"] for r in a + b})
    for w in winners:
        pa, pb = sum(r["winner"] == w for r in a) / len(a), sum(r["winner"] == w for r in b) / len(b)
        p = (pa * len(a) + pb * len(b)) / (len(a) + len(b))
        se = math.sqrt(max(p * (1 - p), 1e-12) * (1 / len(a) + 1 / len(b)))
        z = (pa - pb) / se
        lines.append(("wins " + w, pa, pb, z))
    metrics = [("turns", lambda r: r["turns"])]
    for t in teams:
        metrics.append((f"{t} damage dealt", lambda r, t=t: r["teams"][t]["damage_dealt"]))
        metrics.append((f"{t} final HP", lambda r, t=t: r["teams"][t]["final_hp"]))
    for name, f in metrics:
        xa, xb = [f(r) for r in a], [f(r) for r in b]
        (ma, sa), (mb, sb) = mean_sd(xa), mean_sd(xb)
        se = math.sqrt(sa ** 2 / len(xa) + sb ** 2 / len(xb)) or 1e-12
        lines.append((name, ma, mb, (ma - mb) / se))
    for name, x, y, z in lines:
        flag = "  <-- DIFFERENT" if abs(z) > 3 else ""
        bad += abs(z) > 3
        print(f"  {name:<28} python {x:>10.3f}  rust {y:>10.3f}  z {z:>6.2f}{flag}")
    return bad


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    src, n = argv[0], int(argv[1])
    seed = int(argv[argv.index("--seed") + 1]) if "--seed" in argv else 1
    path = os.path.join(REPO_ROOT, "engine", "fixtures", src, "overrides.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            meta = json.load(f)
        statements, max_turns = meta["overrides"], meta["max_turns"]
    else:
        with open(src, encoding="utf-8") as f:
            statements = json.load(f)
        max_turns = 50
    print(f"{src}: {n} battles each, seed {seed}")
    statements = [s for s in statements if "config.SEED" not in s]
    rust, secs = rust_batch(statements, max_turns, n, seed)
    print(f"  Rust: {secs:.1f} s")
    if "--rust-only" in argv:
        return
    import time
    t0 = time.perf_counter()
    py = python_batch(statements, max_turns, n, seed)
    print(f"  Python: {time.perf_counter() - t0:.1f} s")
    bad = compare(py, rust)
    print("  SAME GAME" if bad == 0 else f"  {bad} measure(s) differ")


if __name__ == "__main__":
    main(sys.argv[1:])
