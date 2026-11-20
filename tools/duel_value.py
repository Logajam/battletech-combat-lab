"""DUEL VALUE (session 30; Daniel, 2026-11-20): a value system for 'Mechs in a 1 v 1, built from each 'Mech's own numbers,
fitted to the fair-duels battles, then tested on pairs that have never fought.

    python tools/duel_value.py fit                    weights, fit on every recorded intro battle; how well each model fits
    python tools/duel_value.py predict [--seed 7]     chooses the TEST pairs (never fought) and writes every model's prediction
                                                      to tools/duel_value_predictions.json - commit it BEFORE the battles
    python tools/duel_value.py play [--workers 4]     plays the test pairs (full sets: 10 maps x 4 bots x 4 edges, 160 each;
                                                      tools/fair_duels.py cells, label "value_test")
    python tools/duel_value.py score                  each model's predictions against what happened

Daniel: "Care to take a stab and developing a value system for mechs and then use it to make predictions about pairs of
mechs that haven't fought yet to gauge how accurate the system is?"

THE NUMBERS PER 'MECH (`profile`; the weapons from the .mtf, their damage / heat / ranges from mechsim/equipment.json, the
engine's own table):
  hp      armor + internal structure (the engine's own count: one 1-turn battle of the unit, `max_hp`)
  walk, jump   MP
  dmg(r)  expected damage a turn at range r: each forward weapon's damage x the chance a gunnery-4 pilot hits (2D6 against
          4 + the range bracket, +0 / +2 / +4, + the minimum-range penalty), a missile rack x 0.6 of its missiles (a rough
          cluster average), all of it scaled down to what the heat sinks carry (fire is cut back pro rata when the weapons'
          heat plus 2 for running exceeds the dissipation). Rear-mounted weapons do not count.
  short, medium, long   dmg averaged over ranges 1-3, 4-9 and 10-18
  ammo_turns   turns of full fire the ammo lasts (ammo weapons only; energy weapons count as unlimited, capped at 20)

THE MODELS (each gives a 'Mech a value v; P(A beats B) = 1 / (1 + exp(v_B - v_A)), a draw counted half):
  bv        v = k x ln(Battle Value)                         (the catalog's BV; k fitted)
  lanchester v = k x ln(hp x best dmg)                       (how many turns each takes to kill the other; k fitted)
  value     v = w . (ln hp, ln(1+short), ln(1+medium), ln(1+long), ln(1+best), walk, jump, ln(1+ammo_turns))
            (w fitted: the value system from the 'Mech's numbers alone)
  bv_plus   v = the same + w_bv x ln(BV)                     (Battle Value corrected by the numbers)
  ratings   the Bradley-Terry ratings from the battles themselves (only for 'Mechs that have fought; the ceiling to beat)

THE TEST (`predict`): 40 pairs of intro 'Mechs that have never met (both rated), and 40 pairs with at least one 'Mech never
seen in any battle (TR:3050 Inner Sphere 'Mechs at rules level 2, newer tech than the fit saw; BV and value can predict
these, ratings cannot). Pairs are drawn so the predicted score spreads over 15 - 85% (a test of only lopsided pairs proves
little). The predictions are written and committed before a single test battle is played.
"""
import json, math, os, random, re, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fair_duels as fd  # noqa: E402

ROOT = fd.ROOT
EQUIP = json.load(open(os.path.join(ROOT, "mechsim", "equipment.json")))
PRED = os.path.join(ROOT, "tools", "duel_value_predictions.json")
CACHE = os.path.join(ROOT, "trial_records", "progress", "duel_value_profiles.json")
GUNNERY = 4
CLUSTER = 0.6
FEATURES = ["ln_hp", "ln_short", "ln_medium", "ln_long", "ln_best", "walk", "jump", "ln_ammo"]


def hit_chance(tn):
    """P(2D6 >= tn)."""
    if tn <= 2:
        return 1.0
    if tn > 12:
        return 0.0
    return sum(1 for a in range(1, 7) for b in range(1, 7) if a + b >= tn) / 36


def lookup(name):
    key = "".join(name.strip().lower().split())
    canon = EQUIP["alias_map"].get(key)
    return EQUIP["entries"].get(canon) if canon else None


def mtf_weapons(text):
    """[(entry, rear)] from the .mtf's Weapons section, and {ammo kind: tons} from its crit slots."""
    lines = text.splitlines()
    out = []
    for i, l in enumerate(lines):
        m = re.match(r"\s*Weapons:\s*(\d+)", l, re.I)
        if m:
            for w in lines[i + 1: i + 1 + int(m.group(1))]:
                name = w.split(",")[0]
                rear = "(R)" in w
                name = name.replace("(R)", "").strip()
                name = re.sub(r"^\d+\s+", "", name)  # "2 Medium Laser" style counts are not used in these files
                e = lookup(name)
                if e and e.get("category") == "weapon":
                    out.append((e, rear))
            break
    ammo = {}
    for l in lines:
        s = l.strip()
        if "ammo" in s.lower() and ":" not in s and "," not in s:
            ammo[s] = ammo.get(s, 0) + 1
    return out, ammo


def unit_hp(unit_id):
    """Armor + structure, the engine's own count (one battle of the unit against itself, 1 turn)."""
    settings = {"FORCES": [{"team": "Red", "mtf": unit_id, "count": 1, "bot": "princess"}, {"team": "Blue", "mtf": unit_id, "count": 1, "bot": "princess"}],
                "DEFAULT_BOARD_PATH": "BigBlank.board"}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(settings, f)
        p = f.name
    try:
        r = subprocess.run([fd.BTSIM, "--setup", p, "--battles", "1", "--max-turns", "1", "--threads", "1"], capture_output=True, text=True, cwd=ROOT)
    finally:
        os.unlink(p)
    return json.loads(r.stdout)["results"][0]["teams"]["Red"]["max_hp"]


def profile(u, hp):
    text = open(os.path.join(fd.DATA, u["id"]), encoding="utf-8", errors="replace").read()
    weapons, ammo = mtf_weapons(text)
    fwd = [e for e, rear in weapons if not rear]
    sinks = u.get("sinks", 10) * (2 if "double" in str(u.get("sink_kind", "")).lower() else 1)
    heat = sum(e.get("heat") or 0 for e in fwd) + 2
    scale = min(1.0, sinks / heat) if heat > 0 else 1.0

    def dmg(r):
        total = 0.0
        for e in fwd:
            rg = e.get("range") or {}
            s, m, l, mn = rg.get("short") or 0, rg.get("medium") or 0, rg.get("long") or 0, rg.get("min") or 0
            if r > l or l == 0:
                continue
            mod = 0 if r <= s else 2 if r <= m else 4
            if mn and r <= mn:
                mod += mn - r + 1
            d = (e.get("damage_per_shot") or 0) * (e.get("rack_size") or 1)
            if e.get("damage_type") == "Missile" and (e.get("rack_size") or 1) > 1:
                d *= CLUSTER
            total += d * hit_chance(GUNNERY + mod)
        return total * scale
    band = lambda a, b: sum(dmg(r) for r in range(a, b + 1)) / (b - a + 1)
    ammo_weapons = [e for e in fwd if isinstance(e.get("shots_per_ton"), (int, float)) and e["shots_per_ton"] > 0]
    if ammo_weapons:
        shots = sum(ammo.values()) * min(e["shots_per_ton"] for e in ammo_weapons)
        turns = min(20.0, shots / len(ammo_weapons))
    else:
        turns = 20.0
    p = {"hp": hp, "walk": u.get("walk", 0), "jump": u.get("jump", 0), "short": band(1, 3), "medium": band(4, 9),
         "long": band(10, 18), "best": max(dmg(r) for r in range(1, 19)), "ammo_turns": turns, "bv": u.get("bv", 0)}
    return p


def features(p):
    return {"ln_hp": math.log(p["hp"]), "ln_short": math.log1p(p["short"]), "ln_medium": math.log1p(p["medium"]),
            "ln_long": math.log1p(p["long"]), "ln_best": math.log1p(p["best"]), "walk": p["walk"], "jump": p["jump"], "ln_ammo": math.log1p(p["ammo_turns"])}


def profiles(units):
    """Every unit's numbers (hp from the engine, cached in the git-ignored progress folder)."""
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    fd.unpack(units)
    changed = False
    for u in units:
        if u["id"] not in cache:
            cache[u["id"]] = unit_hp(u["id"])
            changed = True
    if changed:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        json.dump(cache, open(CACHE, "w"))
    return {u["id"]: profile(u, cache[u["id"]]) for u in units}


# ------------------------------------------------------------------------------------------------------------- fitting
def battles(labels):
    rows = []
    for lb in labels:
        rows += list(fd.done_cells(lb).values())
    return rows


def pair_table(rows):
    """[(a, b, score of a, battles)] per pair."""
    t = {}
    for r in rows:
        a, b, s = r["a"], r["b"], fd.a_score(r)
        if a > b:
            a, b, s = b, a, 1 - s
        x = t.setdefault((a, b), [0.0, 0])
        x[0] += s
        x[1] += 1
    return [(a, b, s / n, n) for (a, b), (s, n) in t.items()]


def fit_logistic(pairs, xa, xb, steps=3000, lr=0.05, l2=1e-3):
    """Weights w for P = sigma(w . (x_a - x_b)), every battle a (soft) sample. Plain gradient descent on the log loss,
    features standardized first."""
    k = len(xa[0])
    diffs = [[xa[i][j] - xb[i][j] for j in range(k)] for i in range(len(pairs))]
    sd = [math.sqrt(sum(d[j] ** 2 for d in diffs) / len(diffs)) or 1.0 for j in range(k)]
    z = [[d[j] / sd[j] for j in range(k)] for d in diffs]
    w = [0.0] * k
    total = sum(n for _, _, _, n in pairs)
    for _ in range(steps):
        g = [l2 * w[j] for j in range(k)]
        for i, (_, _, s, n) in enumerate(pairs):
            p = 1 / (1 + math.exp(-sum(w[j] * z[i][j] for j in range(k))))
            for j in range(k):
                g[j] += (p - s) * n * z[i][j] / total
        w = [w[j] - lr * 10 * g[j] for j in range(k)]
    return [w[j] / sd[j] for j in range(k)]


def models(prof, train_pairs):
    """Fitted value functions {name: f(unit id) -> value}."""
    out = {}
    xa = lambda f: [[f(a)] for a, _, _, _ in train_pairs]
    xb = lambda f: [[f(b)] for _, b, _, _ in train_pairs]
    lnbv = lambda u: math.log(prof[u]["bv"])
    k = fit_logistic(train_pairs, xa(lnbv), xb(lnbv))[0]
    out["bv"] = (lambda k: lambda u: k * lnbv(u))(k)
    lan = lambda u: math.log(prof[u]["hp"] * max(prof[u]["best"], 0.1))
    k2 = fit_logistic(train_pairs, xa(lan), xb(lan))[0]
    out["lanchester"] = (lambda k: lambda u: k * lan(u))(k2)
    fv = lambda u: [features(prof[u])[f] for f in FEATURES]
    w = fit_logistic(train_pairs, [fv(a) for a, _, _, _ in train_pairs], [fv(b) for _, b, _, _ in train_pairs])
    out["value"] = (lambda w: lambda u: sum(wi * xi for wi, xi in zip(w, fv(u))))(w)
    # BV PLUS: Battle Value with the same numbers as corrections (2026-11-20: durability alone explains 83% of the duel
    # ratings, BV 87%, the numbers 89%, both together 93%)
    fb = lambda u: fv(u) + [lnbv(u)]
    w2 = fit_logistic(train_pairs, [fb(a) for a, _, _, _ in train_pairs], [fb(b) for _, b, _, _ in train_pairs])
    out["bv_plus"] = (lambda w: lambda u: sum(wi * xi for wi, xi in zip(w, fb(u))))(w2)
    out["_weights"] = {"bv_k": k, "lanchester_k": k2, "value_w": dict(zip(FEATURES, w)), "bv_plus_w": dict(zip(FEATURES + ["ln_bv"], w2))}
    return out


def logloss(pairs, f):
    tot, n = 0.0, 0
    for a, b, s, m in pairs:
        p = min(max(1 / (1 + math.exp(f(b) - f(a))), 1e-6), 1 - 1e-6)
        tot += -m * (s * math.log(p) + (1 - s) * math.log(1 - p))
        n += m
    return tot / n


def mae(pairs, f):
    return sum(abs(1 / (1 + math.exp(f(b) - f(a))) - s) for a, b, s, _ in pairs) / len(pairs)


# ------------------------------------------------------------------------------------------------------------- stages
def intro_units():
    return fd.intro_pool()


def new_units():
    """Never-seen 'Mechs for the test: Technical Readout 3050 Inner Sphere bipeds at Standard rules (rules level 2: XL
    engines, double heat sinks, ER and pulse lasers, Gauss, Artemis...), all in the website's catalog, which keeps only
    units whose equipment the engine models. A harder test than the intro pool: tech the fit never saw."""
    seen = {u["id"] for u in fd.intro_pool()}
    out = []
    for u in fd.catalog_units():
        if u["id"] in seen or u.get("rules") != 2 or u.get("tech") != "Inner Sphere" or u.get("book") != "TR:3050":
            continue
        if not str(u.get("config", "")).startswith("Biped") or "Omni" in str(u.get("config")):
            continue
        out.append(u)
    return out


def stage_fit(argv):
    units = intro_units()
    prof = profiles(units)
    pairs = pair_table(battles(["intro", "intro_confirm"]))
    pairs = [p for p in pairs if p[0] in prof and p[1] in prof]
    m = models(prof, pairs)
    print(f"fit on {len(pairs)} pairs, {sum(p[3] for p in pairs)} battles")
    print("weights:", json.dumps(m["_weights"], indent=1))
    rows = battles(["intro", "intro_confirm"])
    ids = [u["id"] for u in units]
    rt = fd.bradley_terry(rows, ids)
    m["ratings"] = lambda u: rt[u]
    print(f"{'model':12s} {'log loss':>9s} {'mean |error|':>13s}   (in-sample; a coin is 0.693 log loss)")
    for name in ("bv", "lanchester", "value", "bv_plus", "ratings"):
        print(f"{name:12s} {logloss(pairs, m[name]):9.3f} {mae(pairs, m[name]):13.3f}")


def stage_predict(argv):
    if os.path.exists(PRED) and "--force" not in argv:
        sys.exit(f"{PRED} exists: predictions are made once, before the battles (--force to redo, and say so)")
    rng = random.Random(int(fd.option(argv, "--seed", "7")))
    intro = intro_units()
    fresh = new_units()
    prof = profiles(intro + fresh)
    rows = battles(["intro", "intro_confirm"])
    pairs = [p for p in pair_table(rows) if p[0] in prof and p[1] in prof]
    m = models(prof, pairs)
    ids = [u["id"] for u in intro]
    rt = fd.bradley_terry(rows, ids)
    met = {(a, b) for a, b, _, _ in pair_table(rows)}
    P = lambda f, a, b: 1 / (1 + math.exp(f(b) - f(a)))

    def draw(pool_a, pool_b, n, need_unmet):
        chosen, tries = [], 0
        while len(chosen) < n and tries < 200000:
            tries += 1
            a, b = rng.choice(pool_a), rng.choice(pool_b)
            if a == b:
                continue
            a, b = sorted((a, b))
            if (a, b) in met or (a, b) in [(c[0], c[1]) for c in chosen]:
                continue
            p = P(m["value"], a, b)
            # spread: a target score drawn evenly over 15 - 85%, the pair kept if the value model's guess is near it
            if abs(p - (0.15 + 0.7 * (len(chosen) + 0.5) / n)) > 0.04:
                continue
            chosen.append((a, b))
        return chosen
    intro_ids = [u["id"] for u in intro]
    fresh_ids = [u["id"] for u in fresh]
    test = [(a, b, "both rated") for a, b in draw(intro_ids, intro_ids, 40, True)]
    test += [(a, b, "new 'Mech") for a, b in draw(fresh_ids, intro_ids + fresh_ids, 40, True)]
    out = {"made": fd.subprocess.run(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], capture_output=True, text=True).stdout.strip(),
           "commit": fd.subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
           "weights": m["_weights"], "trained_on_battles": sum(p[3] for p in pairs), "pairs": []}
    for a, b, kind in test:
        e = {"a": a, "b": b, "kind": kind, "profile_a": prof[a], "profile_b": prof[b]}
        for name in ("bv", "lanchester", "value", "bv_plus"):
            e[name] = round(P(m[name], a, b), 4)
        if a in rt and b in rt:
            e["ratings"] = round(1 / (1 + math.exp(rt[b] - rt[a])), 4)
        out["pairs"].append(e)
    json.dump(out, open(PRED, "w"), indent=1)
    print(f"{len(out['pairs'])} test pairs written to {PRED}; commit it before `play`")


def stage_play(argv):
    pred = json.load(open(PRED))
    every = {u["id"]: u for u in fd.catalog_units()}
    fd.unpack([every[x] for e in pred["pairs"] for x in (e["a"], e["b"])])
    fd.COMMIT = fd.subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    cells = [c for e in pred["pairs"] for c in fd.cells_full(e["a"], e["b"])]
    fd.run_cells(cells, "value_test", int(fd.option(argv, "--workers", "4")))


def stage_score(argv):
    pred = json.load(open(PRED))
    got = {(a, b): (s, n) for a, b, s, n in pair_table(battles(["value_test"]))}
    names = ["bv", "lanchester", "value", "bv_plus", "ratings"]
    for kind in ("both rated", "new 'Mech", None):
        rows = [e for e in pred["pairs"] if (kind is None or e["kind"] == kind) and (e["a"], e["b"]) in got]
        if not rows:
            continue
        print(f"\n{kind or 'all'}: {len(rows)} pairs, {sum(got[(e['a'], e['b'])][1] for e in rows)} battles")
        print(f"  {'model':11s} {'log loss':>9s} {'mean |error|':>13s} {'favourite right':>16s}   (a coin: 0.693; always 50%: mean error of the scores)")
        for nm in names:
            r = [e for e in rows if nm in e]
            if not r:
                continue
            ll = mae_ = right = 0.0
            nb = 0
            for e in r:
                s, n = got[(e["a"], e["b"])]
                p = min(max(e[nm], 1e-6), 1 - 1e-6)
                ll += -n * (s * math.log(p) + (1 - s) * math.log(1 - p))
                nb += n
                mae_ += abs(p - s)
                right += 1 if (p - 0.5) * (s - 0.5) > 0 or s == 0.5 else 0
            print(f"  {nm:11s} {ll / nb:9.3f} {mae_ / len(r):13.3f} {right / len(r):15.0%}   ({len(r)} pairs)")
        base = sum(abs(got[(e['a'], e['b'])][0] - 0.5) for e in rows) / len(rows)
        print(f"  {'coin':11s} {0.693:9.3f} {base:13.3f}")


# ------------------------------------------------------------------------------------------------------------- round 2
# Daniel, 2026-11-20 ("Lets go with your suggestion"): better ingredients from the engine itself (`btsim profile`), a random
# battery over a bigger pool, match-up terms, and a test on random held-out pairs.
BATTERY_PAIRS = 3000


def big_pool():
    """Every Inner Sphere biped or quad 'Mech at Introductory or Standard rules in the website's catalog (which keeps only
    units whose equipment the engine models): 1,754 'Mechs."""
    return sorted((u for u in fd.catalog_units() if u.get("rules") in (1, 2) and u.get("tech") == "Inner Sphere"
                   and u.get("config") in ("Biped", "Quad")), key=lambda u: u["id"])


def battery_pairs():
    """BATTERY_PAIRS random pairs from the big pool (seed 2026; the same list every run, so a stopped battery resumes)."""
    ids = [u["id"] for u in big_pool()]
    rng = random.Random(2026)
    pairs = set()
    while len(pairs) < BATTERY_PAIRS:
        a, b = rng.sample(ids, 2)
        pairs.add(tuple(sorted((a, b))))
    return sorted(pairs)


def stage_battery(argv):
    pool = big_pool()
    fd.unpack(pool)
    fd.COMMIT = fd.subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    cells = [c for a, b in battery_pairs() for c in fd.cells_rate(a, b, random.Random(fd.cell_seed([a, b])), fd.BOTS)]
    fd.run_cells(cells, "value_battery", int(fd.option(argv, "--workers", "4")))


def main(argv):
    if not argv:
        sys.exit(__doc__)
    {"fit": stage_fit, "predict": stage_predict, "play": stage_play, "score": stage_score, "battery": stage_battery}[argv[0]](argv[1:])


if __name__ == "__main__":
    main(sys.argv[1:])
