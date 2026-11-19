"""Reads the benchmark records (tools/benchmark_bots.py, trial_records/benchmark_1v1_*.jsonl) and prints what they say.

    python tools/benchmark_report.py [--records DIR] [--bv-file LISTS.json]

1. BV AS A PREDICTOR (Daniel, 2026-11-19): for every same-bot pairing (the pilot is identical on both sides, so only the 'Mechs
   differ) the share of decided battles the 'Mech with the higher Battle Value won, against its BV share. Read: if BV were
   a fair measure the high-BV 'Mech would win in proportion; "rank" is how often it won more than half of its battles.
2. EDGE BIAS (preliminary; the 1 v 1 'Mechs differ, so this is a hint, the 4 v 4 mirrors are the test): wins by the edge a
   team started on, per map and axis, with a two-sided binomial p-value against 50/50.
Battle Value per 'Mech comes from the Lab's unit list (a JSON file with {"units": [{"id", "bv"}]}, `--bv-file`).
"""
import collections, glob, json, math, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def binom_p(k, n):
    """Two-sided p of k or a more extreme split out of n fair coin flips."""
    if n == 0:
        return 1.0
    lo = min(k, n - k)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(lo + 1)) / 2 ** n)


def main(argv):
    opt = lambda n, d: argv[argv.index(n) + 1] if n in argv else d
    records = opt("--records", os.path.join(ROOT, "trial_records"))
    bv = {u["id"]: u["bv"] for u in json.load(open(opt("--bv-file", "")))["units"] if "bv" in u}
    same = collections.defaultdict(lambda: [0, 0, 0])      # (matchup, bot) -> ['Mech 1 wins, 'Mech 2 wins, none] for same-bot pairings
    mechs_of = {}
    edge = collections.defaultdict(lambda: [0, 0])          # (map, axis) -> [wins by the N / W edge, wins by the S / E edge]
    for path in sorted(glob.glob(os.path.join(records, "benchmark_1v1_*.jsonl"))):
        for line in open(path):
            r = json.loads(line)
            a, b = r["cell"].split("|")[1:3]
            mechs_of[r["matchup"]] = r["mechs"]
            for x in r["results"]:
                if x["winner"] in ("Red", "Blue"):
                    e = x["edges"].get(x["winner"])
                    edge[(r["map"], r["axis"])][0 if e in ("N", "W") else 1] += 1
                if a == b:
                    same[(r["matchup"], a)][{"Red": 0, "Blue": 1}.get(x["winner"], 2)] += 1
    print("1. BATTLE VALUE v WIN RATE, same bot on both sides (decided battles only)")
    print(f"   {'matchup':9s} {'bot':9s} {'BV hi v lo':>12s} {'BV share':>9s} {'hi-BV won':>10s}")
    pts, kept = [], 0
    for (m, bot), (w1, w2, _) in sorted(same.items()):
        b1, b2 = (bv[x] for x in mechs_of[m])
        hi_won, lo_won = (w1, w2) if b1 >= b2 else (w2, w1)
        share, rate = max(b1, b2) / (b1 + b2), hi_won / max(w1 + w2, 1)
        pts.append((math.log(max(b1, b2) / min(b1, b2)), rate, share, bot, hi_won, lo_won))
        kept += rate > 0.5
        print(f"   {m:9s} {bot:9s} {max(b1, b2):5d} v {min(b1, b2):<5d} {share:9.0%} {rate:10.0%}")
    n = len(pts)
    print(f"   the higher-BV 'Mech won more than half in {kept} of {n} sets")
    # how much of the win rate does BV explain: correlation, and the error of "win rate = BV share"
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    mx, my = sum(xs) / n, sum(ys) / n
    r = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    mae = sum(abs(p[1] - p[2]) for p in pts) / n
    print(f"   correlation of ln(BV ratio) with the high-BV win rate: r = {r:.2f}; mean gap between win rate and BV share: {mae:.0%}")
    for bot in sorted({p[3] for p in pts}):
        q = [p for p in pts if p[3] == bot]
        print(f"   {bot:9s} high-BV 'Mech won {sum(p[4] for p in q)} of {sum(p[4] + p[5] for p in q)} decided ({sum(p[4] for p in q) / max(sum(p[4] + p[5] for p in q), 1):.0%}); BV share averaged {sum(p[2] for p in q) / len(q):.0%}")
    print("\n2. EDGE BIAS (preliminary: the 1 v 1 'Mechs differ). Wins by the team that started on the N (or W) edge v the S (or E) edge")
    for (m, ax), (lo, hi) in sorted(edge.items()):
        side = "N v S" if ax == "NS" else "W v E"
        print(f"   {m[:-6]:38s} {side}  {lo:3d} - {hi:3d}   p = {binom_p(lo, lo + hi):.2f}")
    for ax, side in (("NS", "N v S"), ("EW", "W v E")):
        lo = sum(v[0] for (m, a), v in edge.items() if a == ax)
        hi = sum(v[1] for (m, a), v in edge.items() if a == ax)
        print(f"   ALL MAPS {side}: {lo} - {hi}   p = {binom_p(lo, lo + hi):.3f}")


if __name__ == "__main__":
    main(sys.argv[1:])
