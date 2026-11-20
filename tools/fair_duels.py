"""FAIR DUELS (session 30; Daniel, 2026-11-19): find very different 'Mechs that are equal in a 1 v 1.

    python tools/fair_duels.py pilot      [--workers 4] [--label NAME]
    python tools/fair_duels.py rate       [--round 1|2] [--opponents 10] [--bots hydra] [--workers 4] [--label NAME]
    python tools/fair_duels.py confirm    [--pairs FILE] [--top 60] [--reps 3] [--workers 4] [--label NAME]
    python tools/fair_duels.py report     [--label NAME]

Daniel: "1 on 1 matches of 2 different units. Using the same bot for both sides. Sweep through maps, bots. Balance starting
positions so that they get equal time from all starting edges. The goal is to find very different units that are somehow
equivalent ... the results could be used to make an improved battle value system." Pool (his pick): the Introductory-rules
'Mechs of the Combat Lab catalog (`web_lab/catalog.json`, rules level 1: 314 'Mechs, 20 - 100 tons, all Inner Sphere).

ONE CELL = one pair (A, B), one map, one bot (both sides), one edge: A starts on the edge, B on the opposite one (zone
deployment, placed: `DEPLOY_ZONES` with that edge's three boxes, `walk_on` false). A FULL SET for a pair = every map x every
bot x the four edges, so each 'Mech starts on every edge equally often on every map with every bot. A is Red on the N and E
cells and Blue on the S and W ones, so neither the seat nor the edge leans one way. Every battle of a cell has its own dice
(seed from the cell), 100-turn cap (the standard game).

Stages (314 'Mechs make 49,000 pairs; a full set is 144 battles, so not every pair can be played in full):
  pilot    the project's own 23 'Mechs (data/*.mtf), every pair, full sets: proves the method on a small pool.
  rate     a sparse schedule over the 314: round 1, each 'Mech against `--opponents` random others; round 2, against the
           ones nearest it in rating. Per pair: the 4 edges x the 4 bots, maps rotated (16 battles). Ratings: Bradley-Terry
           (a draw is half a win), so every 'Mech gets one strength number on one scale.
  confirm  pairs of near-equal rating that differ most (tonnage, speed, armor): full sets head to head, three times over
           with fresh dice (Daniel: the pilot and rating are for pruning; a finalist needs 480 battles, 120 a bot, about
           +- 4.5% per bot instead of +- 8%). `--pairs FILE` (tab-separated ids) confirms a given list, e.g. the pilot's best.
  report   per pair: A's score (win = 1, draw = 1/2) with its margin of error, per bot and per map; the ratings beside BV.

Bots: all four in every stage (Daniel, 2026-11-19, reversing a Hydra-only idea the same hour: "Forgot that we were
looking for fairness across bots too. I expect this will give absolutely dirty data that doesn't agree with itself.").
A FAIR pair is even under each bot, not only on the total; `report` gives each bot's own ratings and how far the bots
agree. `--bots a,b` remains for a side study.

Records: every battle, as each cell ends, in trial_records/<date>_fair_duels_<label>.jsonl (one line a cell); a re-run plays
only the missing cells. Units are unpacked from data/meks.zip into data/meks/ (git-ignored), as the Combat Lab does.
"""
import concurrent.futures, datetime, hashlib, itertools, json, math, os, random, subprocess, sys, tempfile, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BTSIM = os.path.join(ROOT, "engine", "target", "release", "btsim")
RECORDS = os.path.join(ROOT, "trial_records")
CATALOG = os.path.join(ROOT, "web_lab", "catalog.json")
DATA = os.path.join(ROOT, "data")

# the project's own boards (data/*.board): eight standard 16 x 17 sheets and one double-width 32 x 17
MAPS = sorted(f for f in os.listdir(DATA) if f.endswith(".board"))
BOTS = ["gladiator", "princess", "caspar", "hydra"]
EDGES = ["N", "E", "S", "W"]
OPPOSITE = {"N": "S", "S": "N", "E": "W", "W": "E"}
BOXES = {"N": [0, 1, 2], "S": [6, 7, 8], "W": [0, 3, 6], "E": [2, 5, 8]}  # NW N NE / W Centre E / SW S SE
MAX_TURNS = 100


def option(argv, name, default):
    return argv[argv.index(name) + 1] if name in argv else default


def zone(edge):
    return {"boxes": [i in BOXES[edge] for i in range(9)], "walk_on": False}


def cell_seed(key):
    return int(hashlib.sha1(json.dumps(key).encode()).hexdigest()[:8], 16)


# ---------------------------------------------------------------------------------------------------------------- units
def catalog_units():
    return [u for u in json.load(open(CATALOG))["units"] if u.get("ok")]


def intro_pool():
    """Daniel's pool: the Introductory-rules 'Mechs (catalog rules level 1)."""
    return sorted((u for u in catalog_units() if u.get("rules") == 1), key=lambda u: u["id"])


def pilot_pool():
    """The project's own 'Mechs (data/*.mtf, the test files left out)."""
    by_id = {u["id"]: u for u in catalog_units()}
    ids = sorted(f for f in os.listdir(DATA) if f.endswith(".mtf") and not f.startswith("TEST_"))
    return [by_id.get(i, {"id": i, "name": i[:-4]}) for i in ids]


def unpack(units):
    """Each unit's .mtf where the engine reads it (DATA_DIR/<id>): catalog ids under meks/ come from data/meks.zip."""
    z = None
    for u in units:
        p = os.path.join(DATA, u["id"])
        if not os.path.exists(p):
            z = z or zipfile.ZipFile(os.path.join(DATA, "meks.zip"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(z.read(u["id"]))


# ---------------------------------------------------------------------------------------------------------------- cells
def cells_full(a, b, reps=1):
    """A full set for the pair (a, b): every map x bot x edge, `reps` times with fresh dice. The first time is the plain
    5-part cell (so the pilot's and the rating's records count toward it); a repeat carries its number as a 6th part."""
    return [(a, b, m, bot, e) + ((r,) if r else ()) for r in range(reps) for m in MAPS for bot in BOTS for e in EDGES]


def cells_rate(a, b, rng, bots):
    """The rating sample for a pair: 16 battles, the 4 edges x 4 rounds of the bots given (each bot equally often), each
    with a map (the maps rotated from a random start)."""
    start = rng.randrange(len(MAPS))
    out = []
    for i in range(16):
        out.append((a, b, MAPS[(start + i) % len(MAPS)], bots[(i // 4) % len(bots)], EDGES[i % 4]))
    return out


def play_cell(cell):
    """Plays one cell (one battle). Returns the record line (a dict)."""
    a, b, board, bot, edge = cell[:5]
    rep = cell[5] if len(cell) > 5 else 0
    # A is Red on the N and E cells, Blue on the S and W ones (seat and edge both balanced over a full set)
    a_red = edge in ("N", "E")
    red, blue = (a, b) if a_red else (b, a)
    red_edge, blue_edge = (edge, OPPOSITE[edge]) if a_red else (OPPOSITE[edge], edge)
    base_bot = "princess" if bot in ("princess", "caspar") else "gladiator"
    settings = {
        "FORCES": [{"team": "Red", "mtf": red, "count": 1, "bot": base_bot}, {"team": "Blue", "mtf": blue, "count": 1, "bot": base_bot}],
        "DEFAULT_BOARD_PATH": board,
        "DEPLOY_ZONES": {"Red": zone(red_edge), "Blue": zone(blue_edge)},
    }
    seed = cell_seed([a, b, board, bot, edge] + ([rep] if rep else []))
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(settings, f)
        path = f.name
    cmd = [BTSIM, "--setup", path, "--battles", "1", "--seed", str(seed), "--threads", "1", "--max-turns", str(MAX_TURNS)]
    if bot == "hydra":
        cmd += ["--hydra", "Red,Blue"]
    if bot == "caspar":
        cmd += ["--caspar", "Red,Blue"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    finally:
        os.unlink(path)
    line = {"a": a, "b": b, "map": board, "bot": bot, "edge": edge, "a_team": "Red" if a_red else "Blue", "seed": seed}
    if rep:
        line["rep"] = rep
    if p.returncode != 0:
        line["error"] = (p.stderr or p.stdout)[-400:]
        return line
    out = json.loads(p.stdout)
    if out.get("crashed"):
        line["error"] = str(out["crashed"])[:400]
        return line
    r = out["results"][0]
    line.update({"winner": r["winner"], "turns": r["turns"], "capped": r["winner"] == "Draw" and r["turns"] >= MAX_TURNS,
                 "left": {t: [v["final_hp"], v["max_hp"]] for t, v in r["teams"].items()}})
    return line


def records_file(label):
    return os.path.join(RECORDS, f"{datetime.date.today().isoformat()}_fair_duels_{label}.jsonl")


def progress_file(label):
    """Where a run writes as it goes (git-ignored, like trial_records/progress/ for the other tools); moved into the records
    file when the run ends, so the records in git change once a run, not every second."""
    return os.path.join(RECORDS, "progress", f"fair_duels_{label}.jsonl")


def done_cells(label, finished_only=False):
    """Cells already recorded under this label (any date, or still in progress), so a re-run plays only the missing ones."""
    done = {}
    files = [os.path.join(RECORDS, f) for f in os.listdir(RECORDS) if f.endswith(f"_fair_duels_{label}.jsonl")]
    if not finished_only and os.path.exists(progress_file(label)):
        files.append(progress_file(label))
    for path in files:
        if True:
            for row in open(path):
                try:
                    r = json.loads(row)
                except ValueError:
                    continue
                if "error" not in r:
                    done[(r["a"], r["b"], r["map"], r["bot"], r["edge"]) + ((r["rep"],) if r.get("rep") else ())] = r
    return done


def run_cells(cells, label, workers):
    done = done_cells(label)
    todo = [c for c in cells if c not in done]
    print(f"{len(cells)} cells, {len(cells) - len(todo)} already recorded, {len(todo)} to play ({workers} at a time)", flush=True)
    path = progress_file(label)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    errors = 0
    with concurrent.futures.ThreadPoolExecutor(workers) as pool, open(path, "a") as f:
        for i, line in enumerate(pool.map(play_cell, todo), 1):
            line["commit"] = COMMIT
            f.write(json.dumps(line) + "\n")
            f.flush()
            if "error" in line:
                errors += 1
                print(f"  ERROR {line['a']} v {line['b']} {line['map']} {line['bot']} {line['edge']}: {line['error'][:200]}", flush=True)
            if i % 500 == 0:
                print(f"  {i} / {len(todo)}", flush=True)
    print(f"done; {errors} errors", flush=True)
    # the run is over: its battles go into the records file (kept in git), the progress file is emptied
    with open(path) as src, open(records_file(label), "a") as dst:
        dst.write(src.read())
    os.unlink(path)
    return done_cells(label)


# ---------------------------------------------------------------------------------------------------------------- scoring
def a_score(r):
    """A's score in one battle: win 1, draw 1/2, loss 0."""
    if r["winner"] == "Draw":
        return 0.5
    return 1.0 if r["winner"] == r["a_team"] else 0.0


def pair_results(rows):
    """{(x, y): [score of x, ...]} with x < y, from rows (A and B in either order)."""
    out = {}
    for r in rows:
        s = a_score(r)
        x, y = r["a"], r["b"]
        if x > y:
            x, y, s = y, x, 1 - s
        out.setdefault((x, y), []).append((s, r))
    return out


def bradley_terry(rows, units, iters=400):
    """Strength per unit (log scale, mean 0) from every battle; a draw counts half a win each way. A weak prior (one draw
    against an average unit) keeps a unit that never won or never lost finite."""
    wins = {u: 0.5 for u in units}
    games = {}
    for r in rows:
        s = a_score(r)
        wins[r["a"]] += s
        wins[r["b"]] += 1 - s
        k = tuple(sorted((r["a"], r["b"])))
        games[k] = games.get(k, 0) + 1
    p = {u: 1.0 for u in units}
    for _ in range(iters):
        denom = {u: 1.0 / (p[u] + 1.0) for u in units}  # the prior's game against strength 1
        for (x, y), n in games.items():
            d = n / (p[x] + p[y])
            denom[x] += d
            denom[y] += d
        new = {u: wins[u] / denom[u] for u in units}
        g = math.exp(sum(math.log(v) for v in new.values()) / len(new))
        p = {u: v / g for u, v in new.items()}
    return {u: math.log(v) for u, v in p.items()}


def expected(rx, ry):
    return 1.0 / (1.0 + math.exp(ry - rx))


# ---------------------------------------------------------------------------------------------------------------- stages
def stage_pilot(argv):
    units = pilot_pool()
    unpack(units)
    ids = [u["id"] for u in units]
    cells = [c for a, b in itertools.combinations(ids, 2) for c in cells_full(a, b)]
    run_cells(cells, option(argv, "--label", "pilot"), int(option(argv, "--workers", "4")))


def stage_rate(argv):
    label = option(argv, "--label", "intro")
    units = intro_pool()
    unpack(units)
    ids = [u["id"] for u in units]
    k = int(option(argv, "--opponents", "10"))
    rnd = int(option(argv, "--round", "1"))
    rng = random.Random(1000 + rnd)
    pairs = set()
    if rnd == 1:
        # each unit against k random others (a random regular-ish schedule)
        for _ in range(k // 2 + (k % 2)):
            order = ids[:]
            rng.shuffle(order)
            for i in range(len(order)):
                pairs.add(tuple(sorted((order[i], order[(i + 1) % len(order)]))))
    else:
        # each unit against the k nearest it in rating, not met before
        # from FINISHED rounds only (the records file, not a round still in progress), so a stopped round 2 picks the
        # same pairs when run again (found 2026-11-20: a container restart stopped round 2 a quarter of the way)
        done = done_cells(label, finished_only=True)
        met = {tuple(sorted((c[0], c[1]))) for c in done}
        rating = bradley_terry(list(done.values()), ids)
        by = sorted(ids, key=lambda u: rating[u])
        pos = {u: i for i, u in enumerate(by)}
        for u in ids:
            near = sorted((v for v in by[max(0, pos[u] - 3 * k): pos[u] + 3 * k + 1] if v != u), key=lambda v: abs(rating[v] - rating[u]))
            n = 0
            for v in near:
                pr = tuple(sorted((u, v)))
                if pr not in met and pr not in pairs:
                    pairs.add(pr)
                    n += 1
                    if n >= k // 2:
                        break
    bots = option(argv, "--bots", ",".join(BOTS)).split(",")
    cells = [c for a, b in sorted(pairs) for c in cells_rate(a, b, random.Random(cell_seed([a, b])), bots)]
    print(f"round {rnd}: {len(pairs)} pairs")
    run_cells(cells, label, int(option(argv, "--workers", "4")))


def traits(u):
    w = [n for n, c in u.get("weapons", []) for _ in range(c)]
    return {"tons": u.get("tons", 0), "walk": u.get("walk", 0), "jump": u.get("jump", 0), "bv": u.get("bv", 0), "armor": u.get("armor", 0)}


def difference(a, b):
    """How different two 'Mechs are, 0 = alike: tonnage, speed (walk + jump), armor, each as a share of the larger."""
    ta, tb = traits(a), traits(b)
    rel = lambda x, y: abs(x - y) / max(x, y, 1)
    return rel(ta["tons"], tb["tons"]) + rel(ta["walk"] + ta["jump"] / 2, tb["walk"] + tb["jump"] / 2) + rel(ta["armor"], tb["armor"])


def stage_confirm(argv):
    label = option(argv, "--label", "intro")
    units = {u["id"]: u for u in intro_pool()}
    done = done_cells(label)
    rows = list(done.values())
    rating = bradley_terry(rows, list(units))
    per_bot = {bot: bradley_terry([r for r in rows if r["bot"] == bot], list(units)) for bot in BOTS}
    if "--pairs" in argv:
        pairs = [tuple(l.split("\t")[:2]) for l in open(option(argv, "--pairs", "")) if l.strip()]
    else:
        top = int(option(argv, "--top", "60"))
        cands = []
        ids = sorted(units, key=lambda u: rating[u])
        for i, x in enumerate(ids):
            for y in ids[i + 1:]:
                if rating[y] - rating[x] > 0.15:  # predicted score within about 46 - 54%
                    break
                # fair across bots too: no single bot rates them more than 0.4 apart (about 40 - 60%); the per-bot ratings
                # rest on a quarter of the battles, so this is a loose screen and the full set decides
                if any(abs(per_bot[bot][x] - per_bot[bot][y]) > 0.4 for bot in BOTS):
                    continue
                cands.append((difference(units[x], units[y]), x, y))
        cands.sort(reverse=True)
        pairs, used = [], {}
        for d, x, y in cands:  # the most different first; at most 3 pairs per unit, for variety
            if used.get(x, 0) < 3 and used.get(y, 0) < 3:
                pairs.append((x, y))
                used[x] = used.get(x, 0) + 1
                used[y] = used.get(y, 0) + 1
            if len(pairs) >= top:
                break
    every = {u["id"]: u for u in catalog_units()}  # a --pairs list may name 'Mechs outside the pool (the pilot's)
    unpack([every.get(p, {"id": p}) for pr in pairs for p in pr])
    reps = int(option(argv, "--reps", "3"))
    cells = [c for a, b in pairs for c in cells_full(a, b, reps)]
    print(f"confirm: {len(pairs)} pairs, full sets x {reps} (fresh dice each time)")
    run_cells(cells, label + "_confirm", int(option(argv, "--workers", "4")))


def summarize(rows, units, title, full_only=False):
    pr = pair_results(rows)
    lines = []
    for (x, y), ss in pr.items():
        n = len(ss)
        if full_only and n < len(MAPS) * len(BOTS) * len(EDGES):
            continue
        s = sum(v for v, _ in ss) / n
        se = math.sqrt(max(s * (1 - s), 0.05) / n)
        per_bot = {bot: sum(v for v, r in ss if r["bot"] == bot) / max(1, sum(1 for _, r in ss if r["bot"] == bot)) for bot in BOTS}
        draws = sum(1 for _, r in ss if r["winner"] == "Draw") / n
        worst = max(abs(v - 0.5) for v in per_bot.values())
        lines.append((max(abs(s - 0.5), worst) if full_only else abs(s - 0.5), x, y, s, se, n, per_bot, draws))
    lines.sort()
    order = "the bot furthest from even" if full_only else "the total"
    print(f"\n{title}: {len(lines)} pairs, nearest even first by {order} (score = the first 'Mech's, win 1 / draw 1/2; +- one standard error)")
    for _, x, y, s, se, n, pb, dr in lines:
        ux, uy = units.get(x, {}), units.get(y, {})
        nm = lambda u, i: f"{(u.get('name') or i)} ({u.get('tons', '?')}t, BV {u.get('bv', '?')})"
        bots = " ".join(f"{b[:3]} {v:.2f}" for b, v in pb.items())
        print(f"  {s:.3f} +- {se:.3f}  n={n:3d}  draws {dr:.0%}  [{bots}]  {nm(ux, x)}  v  {nm(uy, y)}")


def stage_report(argv):
    label = option(argv, "--label", "intro")
    units = {u["id"]: u for u in catalog_units()}
    for u in pilot_pool():
        units.setdefault(u["id"], u)
    rows = list(done_cells(label).values())
    if not rows:
        print("no records for", label)
        return
    ids = sorted({r["a"] for r in rows} | {r["b"] for r in rows})
    rating = bradley_terry(rows, ids)
    print(f"{label}: {len(rows)} battles, {len(ids)} 'Mechs, draws {sum(1 for r in rows if r['winner'] == 'Draw') / len(rows):.0%}")
    # the ratings beside Battle Value: how well BV orders them, and the biggest disagreements
    bv = [(rating[i], math.log(units[i]["bv"])) for i in ids if units.get(i, {}).get("bv")]
    if len(bv) > 2:
        mx = sum(a for a, _ in bv) / len(bv)
        my = sum(b for _, b in bv) / len(bv)
        cov = sum((a - mx) * (b - my) for a, b in bv)
        corr = cov / math.sqrt(sum((a - mx) ** 2 for a, _ in bv) * sum((b - my) ** 2 for _, b in bv))
        slope = cov / sum((b - my) ** 2 for _, b in bv)
        print(f"rating v log(BV): correlation {corr:.2f}; slope {slope:.2f} (rating per log-BV)")
    per_bot = {bot: bradley_terry([r for r in rows if r["bot"] == bot], ids) for bot in BOTS}

    def corr(xs, ys):
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        c = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
        return c / math.sqrt(sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys) or 1)
    print("\nhow far the bots agree (correlation of their ratings; 1 = the same order):")
    for i, x in enumerate(BOTS):
        print("  " + f"{x:10s}" + " ".join(f"{corr([per_bot[x][u] for u in ids], [per_bot[y][u] for u in ids]):6.2f}" for y in BOTS))
    print("\nratings (Bradley-Terry, log scale; +0.69 = twice as likely to win against the same opponent); then each bot's own:")
    print("  " + " " * 7 + f"{'':32s} {'':>4}  {'':>8}  " + " ".join(f"{b[:5]:>6}" for b in BOTS))
    for i in sorted(ids, key=lambda i: -rating[i]):
        u = units.get(i, {})
        pb = " ".join(f"{per_bot[b][i]:+6.2f}" for b in BOTS)
        print(f"  {rating[i]:+.2f}  {(u.get('name') or i):32s} {u.get('tons', '?'):>3}t  BV {u.get('bv', '?'):>5}  {pb}")
    summarize(rows, units, "pairs closest to even" + (" (full sets only)" if "--full" in argv else ""), "--full" in argv)


COMMIT = ""


def main(argv):
    global COMMIT
    COMMIT = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if not argv:
        sys.exit(__doc__)
    {"pilot": stage_pilot, "rate": stage_rate, "confirm": stage_confirm, "report": stage_report}[argv[0]](argv[1:])


if __name__ == "__main__":
    main(sys.argv[1:])
