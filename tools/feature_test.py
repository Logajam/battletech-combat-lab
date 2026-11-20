"""CONTROLLED FEATURE TESTS (session 30; Daniel, 2026-11-20): what one feature is worth in a 1 v 1, measured by editing it
onto known 'Mechs with everything else unchanged, the way the Combat Lab's unit editor does (it writes a changed .mtf).

    python tools/feature_test.py FEATURE play [--workers 4]     plays the set (restart-safe: re-run the SAME command)
    python tools/feature_test.py FEATURE report                 each 'Mech's score, original v the edited version(s)
    FEATURE: hardened (versions hardened, doubled) | ferrolam (version ferrolam; Daniel: "Ferro-lam is the fairest to
    test. Reactive and reflective are dependant on what their opponents are using")
The originals are played once, under the hardened set (label feature_hardened); every later feature plays only its edited
versions and reads the originals from there (same base 'Mechs, opponents, cells and seeds: replaying them would repeat
the same battles).

Daniel's calls (2026-11-20): FREE UPGRADES ("I build the designer that way on purpose to allow illegal designs for such
testing"); hardened armor first; "May as well go with rules as written" (hardened armor exactly as the rules have it: Core
p.202, a pip destroyed only by two points of damage, -2 on through-armor critical checks, -1 Running MP, +1 to Piloting
Skill Rolls); FULLY CHAOTIC DICE, not paired seeds ("the bots make decisions based on how heavy their armor is. Once one
moves to a different spot the seed no longer matters"): every battle's seed comes from its own cell, file name included.

THE SET: 20 base 'Mechs (5 a weight class, standard armor, Inner Sphere biped, rules levels 1-2, drawn with a fixed seed from
`duel_value.big_pool`) in three versions, each against the same 10 opponents (also standard armor, drawn the same way,
none of them a base 'Mech), 16 battles a pair (`fair_duels.cells_rate`: 4 edges x 4 bots, maps rotated; the same maps for
the three versions of a pair):
  orig      the 'Mech as published
  hardened  the armor type line switched to Hardened(Inner Sphere), the same points (the rules-as-written package)
  doubled   standard armor, every location's points doubled (Daniel: "also not quite the same": no critical-check modifier,
            no run / Piloting penalty, and a single point of damage is not carried over): hardened - doubled = the rule's
            other parts
The edited files go to data/_modified/feature_test/<version>/ (git-ignored; rebuilt from the published file by this tool).
3 x 20 x 10 x 16 = 9,600 battles; records `trial_records/<date>_fair_duels_feature_hardened.jsonl`."""
import json, math, os, random, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fair_duels as fd  # noqa: E402
import duel_value as dv  # noqa: E402

ROOT = os.path.dirname(HERE)
CLASSES = [(20, 35), (40, 55), (60, 75), (80, 100)]
VERSIONS = ["orig", "hardened", "doubled"]
# feature -> the versions it plays (the originals belong to the hardened set) and the armor-type line of each
FEATURES = {"hardened": ["orig", "hardened", "doubled"], "ferrolam": ["ferrolam"]}
ARMOR_LINE = {"hardened": "Hardened(Inner Sphere)", "ferrolam": "Ferro-Lamellor(Clan)"}


def standard_armor(u):
    t = (u.get("armor_type") or "").lower()
    return t.startswith("standard") and "unknown" not in t


def draw_units():
    """(base 'Mechs, opponents): a fixed draw from the big pool, 5 base + 2-3 opponents a weight class."""
    pool = [u for u in dv.big_pool() if standard_armor(u) and u.get("config") == "Biped"]
    rng = random.Random(20261120)
    base, opp = [], []
    for k, (lo, hi) in enumerate(CLASSES):
        cls = sorted((u for u in pool if lo <= u["tons"] <= hi), key=lambda u: u["id"])
        pick = rng.sample(cls, 5 + (3 if k in (1, 2) else 2))
        base += pick[:5]
        opp += pick[5:]
    return base, opp


def edited_id(uid, version):
    return uid if version == "orig" else os.path.join("_modified", "feature_test", version, uid)


def write_version(uid, version):
    """The edited .mtf, made from the published one (the Lab editor's way: a changed copy of the file)."""
    if version == "orig":
        return
    text = open(os.path.join(fd.DATA, uid), encoding="utf-8", errors="replace").read()
    out = []
    for line in text.splitlines():
        key, sep, val = line.partition(":")
        k = key.strip().lower()
        if sep and k == "armor" and version in ARMOR_LINE:
            line = f"{key}:{ARMOR_LINE[version]}"
        elif sep and k.endswith(" armor") and version == "doubled" and val.strip().isdigit():
            line = f"{key}:{2 * int(val.strip())}"
        out.append(line)
    path = os.path.join(fd.DATA, edited_id(uid, version))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


def cells(base, opp, versions=VERSIONS):
    out = []
    for a in base:
        for b in opp:
            pair = fd.cells_rate(a["id"], b["id"], random.Random(fd.cell_seed(["feature", a["id"], b["id"]])), fd.BOTS)
            for v in versions:
                out += [(edited_id(a["id"], v),) + c[1:] for c in pair]
    return out


def play(feature, argv):
    base, opp = draw_units()
    fd.unpack(base + opp)
    for u in base:
        for v in FEATURES[feature]:
            write_version(u["id"], v)
    fd.COMMIT = fd.subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    fd.run_cells(cells(base, opp, FEATURES[feature]), f"feature_{feature}", int(fd.option(argv, "--workers", "4")))


def report(feature, argv):
    base, opp = draw_units()
    rows = list(fd.done_cells("feature_hardened").values())
    if feature != "hardened":
        rows = [r for r in rows if not r["a"].startswith("_modified/")] + list(fd.done_cells(f"feature_{feature}").values())
    shown = ["orig"] + [v for v in FEATURES[feature] if v != "orig"]
    score = {}
    for r in rows:
        score.setdefault(r["a"], []).append(fd.a_score(r))
    logit = lambda p: math.log(min(max(p, 0.01), 0.99) / (1 - min(max(p, 0.01), 0.99)))
    print(f"{len(rows)} battles. Each base 'Mech's score (win 1, draw 1/2) against the 10 opponents, 160 battles a version")
    print(f"  {'Mech':34s} {'tons':>4s} " + " ".join(f"{v[:8]:>8s}" for v in shown) + " " + " ".join(f"{(v[:6] + '-orig'):>11s}" for v in shown[1:]))
    deltas = {v: [] for v in shown[1:]}
    for u in base:
        s = {v: score.get(edited_id(u["id"], v), []) for v in shown}
        if not all(s.values()):
            continue
        m = {v: sum(x) / len(x) for v, x in s.items()}
        for v in shown[1:]:
            deltas[v].append(logit(m[v]) - logit(m["orig"]))
        print(f"  {u['name'][:34]:34s} {u['tons']:4d} " + " ".join(f"{m[v]:8.2f}" for v in shown) + " "
              + " ".join(f"{m[v] - m['orig']:+11.2f}" for v in shown[1:]))
    print("  mean change in log-odds: " + ", ".join(f"{v} {sum(d) / max(len(d), 1):+.2f}" for v, d in deltas.items()))
    by = {}
    for r in rows:
        v = r["a"].split("/")[2] if r["a"].startswith("_modified/feature_test/") else "orig"
        by.setdefault((r["bot"], v), []).append(fd.a_score(r))
    for bot in fd.BOTS:
        print(f"  {bot:10s} " + "  ".join(f"{v} {sum(by.get((bot, v), [0])) / max(len(by.get((bot, v), [])), 1):.2f}" for v in shown))


def main(argv):
    if len(argv) < 2 or argv[0] not in FEATURES:
        sys.exit(__doc__)
    {"play": play, "report": report}[argv[1]](argv[0], argv[2:])


if __name__ == "__main__":
    main(sys.argv[1:])
