"""DUEL VALUE (session 30; Daniel, 2026-11-20): a value system for 'Mechs in a 1 v 1, built from each 'Mech's own numbers,
fitted to the fair-duels battles, then tested on pairs that have never fought.

    python tools/duel_value.py fit                    weights, fit on every recorded intro battle; how well each model fits
    python tools/duel_value.py predict [--seed 7]     chooses the TEST pairs (never fought) and writes every model's prediction
                                                      to tools/duel_value_predictions.json - commit it BEFORE the battles
    python tools/duel_value.py play [--workers 4]     plays the test pairs (full sets: 10 maps x 4 bots x 4 edges, 160 each;
                                                      tools/fair_duels.py cells, label "value_test")
    python tools/duel_value.py challenge predict|play|score UNIT [--top 10] [--battles 100]
                                                      one 'Mech against the formula's top 10, predictions committed first
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


CACHE2 = os.path.join(ROOT, "trial_records", "progress", "duel_value_engine_profiles.json")


def engine_profiles(units, batch=40):
    """`btsim profile` for every unit (cached, git-ignored): the engine's own numbers per 'Mech."""
    cache = json.load(open(CACHE2)) if os.path.exists(CACHE2) else {}
    todo = [u["id"] for u in units if u["id"] not in cache]
    fd.unpack([u for u in units if u["id"] in set(todo)])
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        settings = {"FORCES": [{"team": f"T{j}", "mtf": uid, "count": 1, "bot": "princess"} for j, uid in enumerate(chunk)],
                    "DEFAULT_BOARD_PATH": "BigBlank.board"}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(settings, f)
            path = f.name
        try:
            r = subprocess.run([fd.BTSIM, "profile", "--setup", path], capture_output=True, text=True, cwd=ROOT)
        finally:
            os.unlink(path)
        if r.returncode != 0:  # one bad unit spoils a batch: fall back to one at a time
            if len(chunk) > 1:
                cache.update({k: v for k, v in engine_profiles([{"id": c} for c in chunk], batch=1).items()})
                continue
            cache[chunk[0]] = None
            continue
        for uid, prof in zip(chunk, json.loads(r.stdout)):
            cache[uid] = prof
        os.makedirs(os.path.dirname(CACHE2), exist_ok=True)
        json.dump(cache, open(CACHE2, "w"))
    json.dump(cache, open(CACHE2, "w"))
    return {u["id"]: cache.get(u["id"]) for u in units}


EQUIP_FLAGS = {"ams": ["antimissile", "anti-missile", " ams"], "ecm": ["ecm"], "masc": ["masc"], "tsm": ["tsm", "triple strength"],
               "case": ["case"], "tc": ["targeting computer", "targetingcomputer"], "artemis": ["artemis"]}


def features2(p):
    """The engine-based numbers of one 'Mech (`btsim profile`):
      ln_hp    ln(armor + rear armor + structure, all locations)
      ln_ct    ln(the centre torso's armor + rear + structure): the location that kills
      ln_sus_short / _medium / _long   ln(1 + SUSTAINED damage a turn, averaged over ranges 1-3 / 4-9 / 10-18): the
               forward weapons the heat sinks can carry, best damage per heat first (heat-free weapons always fire)
      ln_alpha ln(1 + the best damage a turn at any range, every forward weapon firing, heat ignored)
      ammo_short  the share of the best sustained damage that needs ammo, times how far its ammo falls short of 20 turns
      run, jump   MP;  ln_tons  (physical attacks scale with weight)
      ams, ecm, masc, tsm, case, tc, artemis   0 / 1"""
    loc = p["locations"]
    hp = sum(a + r + s for a, r, s in loc.values())
    ct = sum(loc.get("Center Torso", [0, 0, 0]))
    fwd = [w for w in p["weapons"] if not w["rear"]]
    budget = max(p["dissipation"], 0)

    def sustained(r):
        ws = sorted(fwd, key=lambda w: -(w["curve"][r - 1] / w["heat"]) if w["heat"] > 0 else -1e9)
        heat, dmg, ammo_dmg = 0, 0.0, 0.0
        for w in ws:
            d = w["curve"][r - 1]
            if d <= 0:
                continue
            if w["heat"] > 0 and heat + w["heat"] > budget:
                continue
            heat += w["heat"]
            dmg += d
            if w["shots"] is not None:
                ammo_dmg += d
        return dmg, ammo_dmg
    sus = [sustained(r) for r in range(1, 19)]
    band = lambda a, b: sum(sus[r - 1][0] for r in range(a, b + 1)) / (b - a + 1)
    best_r = max(range(1, 19), key=lambda r: sus[r - 1][0])
    best, best_ammo = sus[best_r - 1]
    ammo_ws = [w for w in fwd if w["shots"] is not None and w["curve"][best_r - 1] > 0]
    turns = min([w["shots"] for w in ammo_ws], default=20.0)
    ammo_short = (best_ammo / best if best > 0 else 0.0) * max(0.0, 1 - min(turns, 20) / 20)
    alpha = max(sum(w["curve"][r - 1] for w in fwd) for r in range(1, 19))
    names = " ".join(e.lower() for e in p["equipment"])
    f = {"ln_hp": math.log(max(hp, 1)), "ln_ct": math.log(max(ct, 1)), "ln_sus_short": math.log1p(band(1, 3)),
         "ln_sus_medium": math.log1p(band(4, 9)), "ln_sus_long": math.log1p(band(10, 18)), "ln_alpha": math.log1p(alpha),
         "ammo_short": ammo_short, "run": p["run"], "jump": p["jump"], "ln_tons": math.log(max(p["tons"] or 20, 10))}
    for k, keys in EQUIP_FLAGS.items():
        f[k] = 1.0 if any(x in " " + names for x in keys) else 0.0
    f["ln_bv"] = math.log(max(p["bv"], 1))
    return f


F2 = ["ln_hp", "ln_ct", "ln_sus_short", "ln_sus_medium", "ln_sus_long", "ln_alpha", "ammo_short", "run", "jump", "ln_tons",
      "ams", "ecm", "masc", "tsm", "case", "tc", "artemis"]
# MATCH-UP TERMS: f(A) g(B) - f(B) g(A) for these (f, g): a value of A that depends on B (long guns against a slow target,
# short guns with the speed to close against a long-range 'Mech, armor against the other's punch...). Zero for a mirror.
CROSS = [("ln_sus_long", "inv_run"), ("ln_sus_short", "run"), ("ln_sus_short", "ln_sus_long"), ("jump", "ln_sus_long"),
         ("ln_hp", "ln_alpha"), ("run", "inv_run"), ("ln_sus_medium", "run"), ("ln_ct", "ln_alpha")]


def pair_vector(fa, fb, names, cross):
    """The model's inputs for (A, B): A's features minus B's, then the match-up terms."""
    x = [fa[n] - fb[n] for n in names]
    g = lambda f, k: 1.0 / max(f["run"], 1) if k == "inv_run" else f[k]
    for f1, f2 in cross:
        x.append(g(fa, f1) * g(fb, f2) - g(fb, f1) * g(fa, f2))
    return x


def fit_np(X, s, n, l2=1e-2, iters=60):
    """Logistic regression on pair rows (inputs X, A's score s over n battles), Newton steps; standardized inputs."""
    import numpy as np
    X = np.asarray(X, float)
    s = np.asarray(s, float)
    n = np.asarray(n, float)
    sd = X.std(axis=0)
    sd[sd == 0] = 1
    Z = X / sd
    w = np.zeros(Z.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Z @ w))
        g = Z.T @ (n * (p - s)) + l2 * n.sum() * w / len(n)
        H = (Z * (n * p * (1 - p))[:, None]).T @ Z + l2 * n.sum() / len(n) * np.eye(len(w))
        w -= np.linalg.solve(H, g)
    return w / sd


def stage_fit2(argv):
    """Fit and test on HELD-OUT data: (1) random battery pairs held out (20%, seeded), (2) every pair with a held-out 'Mech
    (15% of the big pool, seeded; none of their battles is used to fit). Training also uses the earlier intro runs."""
    import numpy as np
    pool = big_pool()
    every = {u["id"]: u for u in fd.catalog_units()}
    rows = battles(["value_battery", "intro", "intro_confirm", "value_test"])
    ids = sorted({r["a"] for r in rows} | {r["b"] for r in rows})
    prof = engine_profiles([every[i] for i in ids if i in every])
    feats = {i: features2(p) for i, p in prof.items() if p}
    pairs = [p for p in pair_table(rows) if p[0] in feats and p[1] in feats]
    battery = set(battery_pairs())
    rng = random.Random(99)
    test_pairs = {p for p in battery if rng.random() < 0.2}
    held = {u["id"] for u in pool if random.Random(fd.cell_seed(["held", u["id"]])).random() < 0.15}
    splits = {
        "random held-out pairs": ([p for p in pairs if (p[0], p[1]) not in test_pairs], [p for p in pairs if (p[0], p[1]) in test_pairs]),
        "pairs with a never-seen 'Mech": ([p for p in pairs if p[0] not in held and p[1] not in held],
                                          [p for p in pairs if (p[0] in held or p[1] in held) and (p[0], p[1]) in battery]),
    }
    specs = {
        "bv": (["ln_bv"], []),
        "value2": (F2, []),
        "value2 + match-ups": (F2, CROSS),
        "bv_plus2": (F2 + ["ln_bv"], []),
        "bv_plus2 + match-ups": (F2 + ["ln_bv"], CROSS),
    }
    report = {}
    for split, (train, test) in splits.items():
        print(f"\n== {split}: fit on {len(train)} pairs ({sum(p[3] for p in train)} battles), test {len(test)} pairs ({sum(p[3] for p in test)} battles)")
        print(f"  {'model':22s} {'log loss':>9s} {'mean |err|':>10s} {'calib.':>7s}   (log loss: a coin 0.693; per battle)")
        s_te = np.array([p[2] for p in test])
        n_te = np.array([p[3] for p in test])
        noise = float(np.mean(np.sqrt(np.clip(s_te * (1 - s_te), 0.02, None) / n_te))) * 0.8
        for name, (names, cross) in specs.items():
            X = [pair_vector(feats[a], feats[b], names, cross) for a, b, _, _ in train]
            w = fit_np(X, [p[2] for p in train], [p[3] for p in train])
            Xt = np.array([pair_vector(feats[a], feats[b], names, cross) for a, b, _, _ in test])
            z = Xt @ w
            pr = np.clip(1 / (1 + np.exp(-z)), 1e-6, 1 - 1e-6)
            ll = float(-(n_te * (s_te * np.log(pr) + (1 - s_te) * np.log(1 - pr))).sum() / n_te.sum())
            err = float(np.mean(np.abs(pr - s_te)))
            # calibration: the slope of a refit of the outcomes on the model's own logit (1 = right, > 1 = too cautious)
            c = fit_np(z[:, None], s_te, n_te, l2=0)[0]
            print(f"  {name:22s} {ll:9.3f} {err:10.3f} {c:7.2f}")
            report.setdefault(split, {})[name] = {"log_loss": ll, "mean_err": err, "calibration": c,
                                                   "weights": dict(zip(names + [f"{f}*{g}" for f, g in cross], map(float, w)))}
        print(f"  (noise floor of mean |err| with {np.mean(n_te):.0f} battles a pair: about {noise:.3f})")
    out = os.path.join(ROOT, "tools", "duel_value_fit2.json")
    json.dump(report, open(out, "w"), indent=1)
    print("weights and scores:", out)


# ------------------------------------------------------------------------------------------------------------- challenge
# Daniel, 2026-11-20: "I personally expect the asymptote to break your model. Go ahead and fire up a batch of asymptote vs
# the top 10. 100 battles each." One 'Mech against the formula's top 10 (engine-numbers ranking of the big pool), every
# model's prediction written BEFORE the battles (committed), then played and scored.
CHALLENGE = os.path.join(ROOT, "tools", "duel_value_challenge_{}.json")


def fit_all():
    """Every fit2 model refit on ALL recorded battles: (feats, prof, {model: (names, cross, weights)}, pool ids)."""
    pool = big_pool()
    every = {u["id"]: u for u in fd.catalog_units()}
    rows = battles(["value_battery", "intro", "intro_confirm", "value_test"])
    ids = sorted({r["a"] for r in rows} | {r["b"] for r in rows} | {u["id"] for u in pool})
    prof = engine_profiles([every[i] for i in ids if i in every])
    feats = {i: features2(p) for i, p in prof.items() if p}
    pairs = [p for p in pair_table(rows) if p[0] in feats and p[1] in feats]
    specs = {"bv": (["ln_bv"], []), "value2": (F2, []), "value2 + match-ups": (F2, CROSS),
             "bv_plus2": (F2 + ["ln_bv"], []), "bv_plus2 + match-ups": (F2 + ["ln_bv"], CROSS)}
    models = {}
    for name, (names, cross) in specs.items():
        X = [pair_vector(feats[a], feats[b], names, cross) for a, b, _, _ in pairs]
        models[name] = (names, cross, [float(x) for x in fit_np(X, [p[2] for p in pairs], [p[3] for p in pairs])])
    return feats, prof, models, [u["id"] for u in pool if u["id"] in feats], sum(p[3] for p in pairs)


def challenge_cells(a, b, n):
    """n battles of a balanced set: the 16 bot x edge cells in turn, each with a different map each time round (n <= 160)."""
    out = []
    for k in range(len(fd.MAPS)):
        for i, bot in enumerate(fd.BOTS):
            for j, edge in enumerate(fd.EDGES):
                out.append((a, b, fd.MAPS[(k + 4 * i + j) % len(fd.MAPS)], bot, edge))
    return out[:n]


def stage_challenge(argv):
    """challenge predict UNIT [--top 10] [--battles 100] | challenge addendum UNIT | challenge play UNIT [--workers 4] | challenge score UNIT"""
    what, unit = argv[0], argv[1]
    tag = re.sub(r"[^A-Za-z0-9]+", "_", os.path.splitext(os.path.basename(unit))[0]).strip("_").lower()
    path, label = CHALLENGE.format(tag), f"challenge_{tag}"
    if what == "predict":
        if os.path.exists(path) and "--force" not in argv:
            sys.exit(f"{path} exists: predictions are made once, before the battles")
        feats, prof, models, poolids, n_fit = fit_all()
        every = {u["id"]: u for u in fd.catalog_units()}
        prof.update(engine_profiles([every[unit]]))
        feats[unit] = features2(prof[unit])
        fv = lambda i: sum(w * feats[i][k] for k, w in zip(models["value2"][0], models["value2"][2]))
        top, seen = [], set()
        for i in sorted(poolids, key=lambda i: -fv(i)):
            name = os.path.basename(i)
            if i != unit and name not in seen:  # one copy of a 'Mech the library holds twice
                seen.add(name)
                top.append(i)
            if len(top) == int(fd.option(argv, "--top", "10")):
                break
        out = {"made": fd.subprocess.run(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], capture_output=True, text=True).stdout.strip(),
               "commit": fd.subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
               "unit": unit, "battles": int(fd.option(argv, "--battles", "100")), "trained_on_battles": n_fit,
               "fv": {i: round(fv(i), 4) for i in [unit] + top}, "pairs": []}
        for b in top:
            e = {"a": unit, "b": b}
            for name, (names, cross, w) in models.items():
                z = sum(x * y for x, y in zip(pair_vector(feats[unit], feats[b], names, cross), w))
                e[name] = round(1 / (1 + math.exp(-z)), 4)
            out["pairs"].append(e)
        json.dump(out, open(path, "w"), indent=1)
        print(f"{len(top)} pairs written to {path}; commit it before `challenge play`")
        for e in out["pairs"]:
            print(f"  {os.path.basename(e['b'])[:-4]:32s} " + "  ".join(f"{k} {e[k]:.2f}" for k in models))
    elif what == "addendum":
        # Daniel, 2026-11-20, while the battles were starting: "hardened armor definitly counts for at least 2 per point of
        # armor" (Core p.202: a hardened pip is destroyed only by two points of damage). The same fitted models, with the
        # challenger's armor counted twice in its hit points (ln_hp, ln_ct); written beside the first predictions, dated,
        # before any result was read.
        pred = json.load(open(path))
        feats, prof, models, _, _ = fit_all()
        every = {u["id"]: u for u in fd.catalog_units()}
        u = pred["unit"]
        p = (engine_profiles([every[u]]))[u]
        if "hardened" not in (every[u].get("armor_type") or "").lower():
            sys.exit(f"{u} has no hardened armor")
        p2 = dict(p, locations={k: [2 * a, 2 * r, st] for k, (a, r, st) in p["locations"].items()})
        fa = features2(p2)
        for e in pred["pairs"]:
            b = e["b"]
            for name, (names, cross, w) in models.items():
                z = sum(x * y for x, y in zip(pair_vector(fa, feats[b], names, cross), w))
                e["hardened x2: " + name] = round(1 / (1 + math.exp(-z)), 4)
        pred["addendum"] = {"made": fd.subprocess.run(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], capture_output=True, text=True).stdout.strip(),
                            "why": "Daniel: hardened armor counts at least 2 per point (Core p.202); challenger's armor doubled",
                            "fv": round(sum(w * fa[k] for k, w in zip(models["value2"][0], models["value2"][2])), 4)}
        json.dump(pred, open(path, "w"), indent=1)
        for e in pred["pairs"]:
            print(f"  {os.path.basename(e['b'])[:-4]:32s} " + "  ".join(f"{k[13:]} {e[k]:.2f}" for k in e if k.startswith("hardened")))
        print("challenger's FV with armor x2:", pred["addendum"]["fv"], " (was", pred["fv"][u], ")")
    elif what == "play":
        pred = json.load(open(path))
        every = {u["id"]: u for u in fd.catalog_units()}
        fd.unpack([every[x] for e in pred["pairs"] for x in (e["a"], e["b"])])
        fd.COMMIT = fd.subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        cells = [c for e in pred["pairs"] for c in challenge_cells(e["a"], e["b"], pred["battles"])]
        fd.run_cells(cells, label, int(fd.option(argv, "--workers", "4")))
    elif what == "score":
        pred = json.load(open(path))
        rows = battles([label])
        names = ["bv", "value2", "value2 + match-ups", "bv_plus2", "bv_plus2 + match-ups"]
        names += ["hardened x2: " + n for n in names[1:] if "hardened x2: " + n in pred["pairs"][0]]
        print(f"{os.path.basename(pred['unit'])[:-4]}'s score (win 1, draw 1/2) against each, and each model's prediction")
        print(f"  {'opponent':32s} {'played':>6s} {'actual':>6s} {'draws':>5s} " + " ".join(f"{n.replace('hardened x2: ', 'hx2 ').replace(' + match-ups', '+mu')[:12]:>12s}" for n in names))
        err = {n: [] for n in names}
        for e in pred["pairs"]:
            rs = [r for r in rows if r["a"] == e["a"] and r["b"] == e["b"]]
            if not rs:
                continue
            act = sum(fd.a_score(r) for r in rs) / len(rs)
            draws = sum(r["winner"] == "Draw" for r in rs)
            for n in names:
                err[n].append(abs(e[n] - act))
            print(f"  {os.path.basename(e['b'])[:-4]:32s} {len(rs):6d} {act:6.2f} {draws:5d} " + " ".join(f"{e[n]:12.2f}" for n in names))
        print(f"  {'mean |error|':54s} " + " ".join(f"{sum(v) / max(len(v), 1):12.3f}" for v in err.values()))
        by_bot = {}
        for r in rows:
            by_bot.setdefault(r["bot"], []).append(fd.a_score(r))
        print("  by bot (all opponents): " + ", ".join(f"{k} {sum(v) / len(v):.2f} ({len(v)})" for k, v in sorted(by_bot.items())))


def main(argv):
    if not argv:
        sys.exit(__doc__)
    {"fit": stage_fit, "predict": stage_predict, "play": stage_play, "score": stage_score, "battery": stage_battery, "fit2": stage_fit2, "challenge": stage_challenge}[argv[0]](argv[1:])


if __name__ == "__main__":
    main(sys.argv[1:])
