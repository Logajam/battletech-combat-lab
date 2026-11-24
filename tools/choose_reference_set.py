"""
tools/choose_reference_set.py - the smallest set of battles that covers every EVENT TYPE at least N times
(INTEGRATION__EVENTS.md; Daniel, 2026-11-24: "a shorter reference list that tracks events more densely").

    python tools/choose_reference_set.py COVERAGE.tsv [--n 3] [--times a.tsv --times b.tsv] [--keep NAME,NAME] [--keep-file FILE]

COVERAGE.tsv is `tools/event_coverage.py --tsv` (rows: source, battle, turns, events, then a count per event kind / sub-kind key).
--times FILE (any number) = `name<TAB>seconds` lines, the cost of a battle (default: its event count / 20000 seconds).
--penalty PREFIX=FACTOR: a battle whose name starts with PREFIX costs FACTOR times as much (--penalty key:=3).
--keep: battles that stay whatever they cover (the long full-length ones, the Hydra / CASPAR variants).

Greedy multi-cover: the kept battles count first; then, until every event kind has N battles, the battle that adds the most
still-needed kind-coverage per second of run time is taken. A battle counts toward a kind once (a kind needs N BATTLES, so one
battle with 5000 events of a kind is one battle). Sub-kind keys (CRIT:Gyro ...) are wanted once each, at a lower weight. Prints
the chosen battles, what each added, and every kind still short (a purpose-built scenario is needed for those).
"""
import sys


def read_tsv(path):
    with open(path) as f:
        head = f.readline().rstrip("\n").split("\t")
        rows = []
        for line in f:
            p = line.rstrip("\n").split("\t")
            rows.append({"source": p[0], "name": p[1], "turns": int(p[2]), "events": int(p[3]), "counts": dict(zip(head[4:], map(int, p[4:])))})
    return head[4:], rows


def read_times(paths):
    t = {}
    for p in paths:
        for line in open(p):
            n, s = line.rstrip("\n").split("\t")
            t[n] = float(s)
    return t


def choose(cols, rows, n, times, keep, sub_weight=0.25, want_sub=True, penalties=None):
    penalties = penalties or {}
    kinds = [c for c in cols if ":" not in c]
    subs = [c for c in cols if ":" in c]
    need = {k: n for k in kinds}
    need.update({s: 1 for s in subs} if want_sub else {})
    weight = {k: 1.0 for k in kinds}
    weight.update({s: sub_weight for s in subs})
    chosen, log = [], []
    by_name = {r["name"]: r for r in rows}

    def cost(r):
        c = max(times.get(r["name"], r["events"] / 20000.0), 0.3)
        for prefix, factor in penalties.items():   # e.g. "key:" = 3: an answer-key scenario is chosen only when it earns it
            if r["name"].startswith(prefix):
                c *= factor
        return c

    def take(r, why):
        gained = {k: min(r["counts"].get(k, 0) > 0 and 1 or 0, need[k]) for k in need if need[k] > 0 and r["counts"].get(k, 0) > 0}
        for k in gained:
            need[k] -= 1
        chosen.append(r)
        log.append((r["name"], why, sorted(gained)))

    for name in keep:
        if name not in by_name:
            raise SystemExit(f"--keep {name}: no such battle in the table")
        take(by_name[name], "kept")
    pool = [r for r in rows if r not in chosen]
    while any(v > 0 for v in need.values()):
        best, best_score = None, 0.0
        for r in pool:
            gain = sum(weight[k] for k in need if need[k] > 0 and r["counts"].get(k, 0) > 0)
            score = gain / cost(r)
            if score > best_score:
                best, best_score = r, score
        if best is None:
            break
        pool.remove(best)
        take(best, "covers")
    short = [k for k, v in need.items() if v > 0]
    return chosen, log, short


def main(argv):
    if not argv or argv[0].startswith("--"):
        raise SystemExit(__doc__)
    cols, rows = read_tsv(argv[0])
    n = int(argv[argv.index("--n") + 1]) if "--n" in argv else 3
    times = read_times([argv[i + 1] for i, a in enumerate(argv) if a == "--times"])
    keep, why_kept = [], {}
    if "--keep" in argv:
        keep += argv[argv.index("--keep") + 1].split(",")
    if "--keep-file" in argv:
        label = "kept"
        for l in open(argv[argv.index("--keep-file") + 1]):
            l = l.strip()
            if l.startswith("#"):
                label = l.lstrip("# ").strip()   # a comment line names the group of names below it
            elif l:
                keep.append(l)
                why_kept[l] = label
    penalties = {a.split("=")[0]: float(a.split("=")[1]) for i, a in enumerate(argv) if i and argv[i - 1] == "--penalty"}
    chosen, log, short = choose(cols, rows, n, times, keep, want_sub="--no-subkinds" not in argv, penalties=penalties)
    total = sum(max(times.get(r["name"], r["events"] / 20000.0), 0.3) for r in chosen)
    print(f"{len(chosen)} battles, about {total:.0f} s of battle time (the cost column)")
    for name, why, gained in log:
        print(f"  {name:55s} {why:7s} {len(gained):3d} keys  {', '.join(g for g in gained if ':' not in g)[:110]}")
    if "--write-list" in argv:
        # engine/reference/battles.txt: one battle a line, the reason after a #; the kept groups first, then what was added for coverage
        with open(argv[argv.index("--write-list") + 1], "w") as f:
            f.write("# THE REFERENCE LIST (tools/choose_reference_set.py, 2026-11-24): the battles tests/check_rust_reference.py plays.\n"
                    "# One name a line (a scenario folder, or a variant of check_rust_reference.py's VARIANTS); text after # is why it is here.\n"
                    "# Rule: every event type happens in at least %d of these battles (the check fails if one drops to zero).\n" % n)
            for name, why, gained in log:
                kinds_gained = [g for g in gained if ":" not in g]
                cases_gained = [g for g in gained if ":" in g]
                reason = why_kept.get(name) or ("covers " + ", ".join(kinds_gained[:6] or cases_gained[:3]))
                f.write(f"{name}  # {reason}\n")
    kinds = [c for c in cols if ":" not in c]
    print("\nNOT YET COVERED (need a purpose-built scenario):", ", ".join(k for k in short if k in kinds) or "no event kind")
    print("sub-kind cases no battle has:", ", ".join(k for k in short if k not in kinds) or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
