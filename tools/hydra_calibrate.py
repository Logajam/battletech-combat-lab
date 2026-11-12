"""S6: calibrate Hydra's Forecast on finished battles (INTEGRATION__HYDRA.md Section 7; session 25).

    python tools/hydra_calibrate.py collect OUT.jsonl [--battles 20] [--big-battles 8] [--seed 11] [--threads N] [--btsim PATH]
    python tools/hydra_calibrate.py fit OUT.jsonl [--every 2]

COLLECT plays the nine mirror match-ups (engine/fixtures/hy_*, from tools/hydra_scenarios.py) with these pairings, each
seat both ways where the bots differ: Hydra v Gladiator, Hydra v Princess, Hydra v Hydra, Gladiator v Gladiator,
Princess v Princess. `btsim --ledger` records every unit's raw ledger figures (life, guns) at the end of every turn and
when the battle ends (scenario::run_recorded). One JSON line per battle, tagged with scenario and bots.

FIT asks: from a snapshot at the end of turn t, how well does the Forecast predict how the battle really ended?
- The OUTCOME is measured in the Forecast's own terms but with the snapshot's guns held fixed, so it does not depend on
  the settings being fitted: M = (sum over Red of life_end x guns_t - the same for Blue) / (the same sums with life_t).
  life_end is 0 for a unit destroyed by the end (a battle that hit the turn cap counts as it stands).
- The ledger rules Hydra applies are applied here too: guns = max(raw, DORMANT 0.5 x the unit's best so far, MIN 1).
- The Forecast is the Rust's (hydra::forecast: half a turn's fire a step, each side pours its fire on the enemy in
  kill order, 60 steps), with two settings it never had:
    FOCUS  share of a side's fire poured in kill order; the rest is spread over the enemy in proportion to life left
           (1 = today's perfect focus, 0 = fire spread evenly by size);
    FADE   a unit's guns shrink with its life: guns x (life / life_t) ^ FADE (0 = today: full guns until destroyed).
  and the step size STEP (today 0.5).
- Scored per setting: the mean squared error between predicted and real margin (the fit), the correlation, and how often
  the sign is right among battles that ended with a clear winner. Today's setting is printed first.
"""
import itertools, json, math, os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import round_robin  # noqa: E402

BTSIM = os.path.join(ROOT, "engine", "target", "release", "btsim")
SMALL = ["hy_duel_griffin", "hy_duel_hunchback_woods", "hy_duel_awesome_hills", "hy_2v2_grass", "hy_4v4_lance_grass",
         "hy_4v4_lance_woods", "hy_4v4_heavy_hills"]
BIG = ["hy_8v8_valley", "hy_12v12_valley"]
PAIRINGS = [("hydra", "gladiator"), ("gladiator", "hydra"), ("hydra", "princess"), ("princess", "hydra"),
            ("hydra", "hydra"), ("gladiator", "gladiator"), ("princess", "princess")]
DORMANT_GUNS, MIN_GUNS, MAX_STEPS = 0.5, 1.0, 60


def option(argv, name, default):
    return argv[argv.index(name) + 1] if name in argv else default


def collect(argv):
    out_path = argv[0]
    battles, big = int(option(argv, "--battles", "20")), int(option(argv, "--big-battles", "8"))
    seed, threads, btsim = option(argv, "--seed", "11"), option(argv, "--threads", None), option(argv, "--btsim", BTSIM)
    with open(out_path, "w") as out, tempfile.TemporaryDirectory() as tmp:
        for scen in SMALL + BIG:
            n = big if scen in BIG else battles
            for red, blue in PAIRINGS:
                folder = round_robin.seat(os.path.join(ROOT, "engine", "fixtures", scen), os.path.join(tmp, f"{scen}_{red}_{blue}"), red, blue)
                ledger = os.path.join(tmp, "ledger.jsonl")
                cmd = [btsim, folder, "--battles", str(n), "--seed", seed, "--ledger", ledger] + (["--threads", threads] if threads else [])
                subprocess.run(cmd, capture_output=True, text=True, check=True)
                for line in open(ledger):
                    rec = json.loads(line)
                    rec.update({"scenario": scen, "red": red, "blue": blue})
                    out.write(json.dumps(rec) + "\n")
                print(f"{scen:24s} {red:9s} v {blue:9s} {n} battles", flush=True)


# ---------------------------------------------------------------------------------------------------------------------
# the Forecast, as in engine/core/src/hydra.rs, with FOCUS / FADE / STEP
# ---------------------------------------------------------------------------------------------------------------------
def pour(fire, life, guns, hits):
    order = sorted((i for i in range(len(life)) if life[i] > 0), key=lambda i: (-(guns[i] / life[i]), i))
    left = fire
    for i in order:
        if left <= 0:
            break
        take = min(left, life[i])
        hits[i] += take
        left -= take


def spread(fire, life, hits):
    total = sum(l for l in life if l > 0)
    if total <= 0:
        return
    for i, l in enumerate(life):
        if l > 0:
            hits[i] += fire * l / total


def forecast(a, b, focus=1.0, fade=0.0, step=0.5):
    """(life, guns) lists of both sides -> margin, as hydra::forecast (focus 1, fade 0, step 0.5 is the Rust's)."""
    la, ga = [x[0] for x in a], [x[1] for x in a]
    lb, gb = [x[0] for x in b], [x[1] for x in b]
    la0, lb0 = la[:], lb[:]
    worth = lambda l, g: sum(max(x, 0.0) * y for x, y in zip(l, g))
    start = worth(la, ga) + worth(lb, gb)
    if start <= 0:
        return 0.0
    eff = lambda l, l0, g: [gi * ((li / l0i) ** fade if fade and l0i > 0 else 1.0) if li > 0 else 0.0 for li, l0i, gi in zip(l, l0, g)]
    for _ in range(MAX_STEPS):
        fa, fb = sum(eff(la, la0, ga)) * step, sum(eff(lb, lb0, gb)) * step
        if fa <= 0 or fb <= 0:
            break
        hb, ha = [0.0] * len(lb), [0.0] * len(la)
        pour(fa * focus, lb, gb, hb)
        spread(fa * (1 - focus), lb, hb)
        pour(fb * focus, la, ga, ha)
        spread(fb * (1 - focus), la, ha)
        lb = [l - h for l, h in zip(lb, hb)]
        la = [l - h for l, h in zip(la, ha)]
    return (worth(la, ga) - worth(lb, gb)) / start


def samples(path, every):
    """(red entries, blue entries, real margin, clear winner sign or 0, tag) per usable snapshot."""
    out = []
    for line in open(path):
        rec = json.loads(line)
        snaps = rec["snapshots"]
        final = {u: life for u, _, life, _ in snaps[-1]["units"]}
        best = {}
        for k, snap in enumerate(snaps[:-1]):
            red, blue = [], []
            for u, team, life, guns in snap["units"]:
                best[u] = max(best.get(u, 0.0), guns)
                if life <= 0:
                    continue
                g = max(guns, DORMANT_GUNS * best[u], MIN_GUNS)
                (red if team == "Red" else blue).append((u, life, g))
            if k % every or not red or not blue:
                continue
            start = sum(l * g for _, l, g in red + blue)
            real = (sum(final[u] * g for u, _, g in red) - sum(final[u] * g for u, _, g in blue)) / start
            sign = {"Red": 1, "Blue": -1}.get(rec["winner"], 0)
            out.append(([(l, g) for _, l, g in red], [(l, g) for _, l, g in blue], real, sign, f"{rec['scenario']}:{rec['red']}-{rec['blue']}"))
    return out


def score(data, **kw):
    pred = [forecast(a, b, **kw) for a, b, _, _, _ in data]
    real = [r for _, _, r, _, _ in data]
    n = len(data)
    mse = sum((p - r) ** 2 for p, r in zip(pred, real)) / n
    mp, mr = sum(pred) / n, sum(real) / n
    cov = sum((p - mp) * (r - mr) for p, r in zip(pred, real))
    sd = math.sqrt(sum((p - mp) ** 2 for p in pred) * sum((r - mr) ** 2 for r in real)) or 1.0
    decided = [(p, s) for p, (_, _, _, s, _) in zip(pred, data) if s != 0]
    sign_ok = sum(1 for p, s in decided if p * s > 0) / max(len(decided), 1)
    return mse, cov / sd, sign_ok, sum(abs(p) for p in pred) / n, sum(abs(r) for r in real) / n


def fit(argv):
    data = samples(argv[0], int(option(argv, "--every", "2")))
    print(f"{len(data)} snapshots")
    print(f"{'focus':>6} {'fade':>5} {'step':>5} | {'MSE':>7} {'corr':>6} {'sign ok':>8} | mean |pred| v |real|")
    grid = list(itertools.product([1.0, 0.75, 0.5, 0.25, 0.0], [0.0, 0.5, 1.0, 2.0], [0.5, 0.25, 1.0]))
    rows = []
    for focus, fade, step in grid:
        mse, corr, sign, ap, ar = score(data, focus=focus, fade=fade, step=step)
        rows.append((mse, focus, fade, step, corr, sign, ap, ar))
        mark = "  <- today" if (focus, fade, step) == (1.0, 0.0, 0.5) else ""
        print(f"{focus:6.2f} {fade:5.1f} {step:5.2f} | {mse:7.4f} {corr:6.3f} {sign:8.1%} | {ap:.3f} v {ar:.3f}{mark}", flush=True)
    rows.sort()
    print("\nBEST by MSE:")
    for mse, focus, fade, step, corr, sign, ap, ar in rows[:5]:
        print(f"  focus {focus:.2f} fade {fade:.1f} step {step:.2f}: MSE {mse:.4f} corr {corr:.3f} sign {sign:.1%}")


if __name__ == "__main__":
    {"collect": collect, "fit": fit}[sys.argv[1]](sys.argv[2:])
