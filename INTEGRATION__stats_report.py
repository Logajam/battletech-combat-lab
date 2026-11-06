"""
INTEGRATION__stats_report.py  (NEW 2026-11-06, Claude - output only)

Battle statistics, part 2: from a batch's event logs (INTEGRATION__stats) to
the numbers and one self-contained HTML page (INTEGRATION__stats_viewer.html
with the analysis inside it, the way INTEGRATION__replay does it).

    analysis = analyze(results)          # a plain dict of numbers, JSON-ready
    path = write(analysis)               # stats/<name>.html under the repo root

run_batch calls report(results) when config.STATS is on, and the page's data is
also written next to it as JSON so any later question is a query on it.

What the page shows (Daniel's sorted list, 2026-11-06):
  - Outcome: win / draw per team with a 95% confidence interval, how draws
    ended, battle length as a distribution, the running win rate (is the batch
    big enough?), the shortest / longest battles with their seeds.
  - Per unit: survival, when and why it died (and in which phase), damage
    dealt and taken as distributions (mean, median, p10 / p90), kills per game,
    damage by weapon and by physical attack, shots by range, locations lost,
    criticals, heat, prone and shutdown time.
  - Per team (battles with several units a side): surviving units and force
    HP by turn, survivors at the end, first-kill timing, focus fire,
    each unit's share of the team's damage.
Curves read "the state at turn t": a battle that ended earlier counts at its
final state from then on, so every curve covers the same battles.
"""

import json
import math
import os
import re
from collections import Counter, defaultdict

import INTEGRATION__config as config
import hex_geometry
from los import hex_distance

VIEWER_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "INTEGRATION__stats_viewer.html")
DATA_PLACEHOLDER = "__STATS_JSON__"
HIST_BINS = 12


# =============================================================================
# ==========================  SMALL STATISTICS  ================================
# =============================================================================
def percentile(xs, q):
    """The q-th percentile (0-100) of a sorted list, interpolating between ranks."""
    if not xs:
        return 0.0
    if len(xs) == 1:
        return float(xs[0])
    pos = (len(xs) - 1) * q / 100.0
    lo = math.floor(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def describe(xs):
    """Mean, spread and percentiles of a list of numbers (all zero for none)."""
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return {"n": 0, "mean": 0, "sd": 0, "min": 0, "p10": 0, "p25": 0, "median": 0, "p75": 0, "p90": 0, "max": 0}
    mean = sum(xs) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0
    return {"n": n, "mean": mean, "sd": sd, "min": xs[0], "p10": percentile(xs, 10), "p25": percentile(xs, 25),
            "median": percentile(xs, 50), "p75": percentile(xs, 75), "p90": percentile(xs, 90), "max": xs[-1]}


def histogram(xs, bins=HIST_BINS, integer=False):
    """{"edges": [...], "counts": [...]} - whole-number values get a bar each when there are few."""
    xs = list(xs)
    if not xs:
        return {"edges": [], "counts": []}
    lo, hi = min(xs), max(xs)
    if integer and hi - lo < bins:
        edges = list(range(int(lo), int(hi) + 2))
        counts = [0] * (len(edges) - 1)
        for x in xs:
            counts[int(x) - int(lo)] += 1
        return {"edges": edges, "counts": counts}
    if hi == lo:
        return {"edges": [lo, lo + 1], "counts": [len(xs)]}
    width = (hi - lo) / bins
    counts = [0] * bins
    for x in xs:
        counts[min(bins - 1, int((x - lo) / width))] += 1
    return {"edges": [lo + i * width for i in range(bins + 1)], "counts": counts}


def wilson(k, n, z=1.96):
    """95% confidence interval for a proportion k/n (Wilson score), as (low, high)."""
    if not n:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def _prop(k, n):
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "p": k / n if n else 0.0, "lo": lo, "hi": hi}


# =============================================================================
# ==========================  THE ANALYSIS  ====================================
# =============================================================================
def analyze(results, title=""):
    """Everything the page shows, from a batch's BattleResults (those with a stats log)."""
    logs = [(r, r.stats) for r in results if getattr(r, "stats", None)]
    if not logs:
        return None
    first = logs[0][1]
    labels = list(first["units"])
    team_order = first["team_order"]
    teams = {t: [u for u in labels if first["teams"][u] == t] for t in team_order}
    n = len(logs)
    out = {"title": title, "n": n, "seed": getattr(logs[0][0], "seed", None), "labels": labels,
           "team_order": team_order, "units": first["units"], "teams_members": teams,
           "multi": any(len(m) > 1 for m in teams.values())}
    out["outcome"] = _outcome(logs, team_order)
    out["unit"] = {u: _unit(logs, u, first["units"][u]) for u in labels}
    out["curves"] = _curves(logs, labels, team_order, teams)
    if out["multi"]:
        out["team"] = {t: _team(logs, t, teams[t], teams) for t in team_order}
    return out


def _outcome(logs, team_order):
    n = len(logs)
    wins = Counter(r.winner for r, _ in logs)
    turns = [r.turns_taken for r, _ in logs]
    capped = sum(1 for r, _ in logs if r.destroyed is None and r.turn_cap and r.turns_taken >= r.turn_cap)
    draws_all_dead = sum(1 for r, _ in logs if r.winner == "Draw" and r.destroyed is not None)
    running = {t: [] for t in team_order}          # win rate after each battle: is the batch big enough?
    got = Counter()
    for i, (r, _) in enumerate(logs, start=1):
        got[r.winner] += 1
        for t in team_order:
            running[t].append(got[t] / i)
    ordered = sorted(logs, key=lambda x: x[0].turns_taken)
    def pick(entry):
        r, _ = entry
        return {"seed": None if r.seed is None else str(r.seed), "turns": r.turns_taken, "winner": r.winner}
    return {
        "wins": {t: _prop(wins.get(t, 0), n) for t in team_order},
        "draws": _prop(wins.get("Draw", 0), n),
        "draws_all_destroyed": draws_all_dead, "draws_turn_cap": capped,
        "turns": describe(turns), "turns_hist": histogram(turns, integer=True),
        "running_win_rate": running,
        "shortest": [pick(e) for e in ordered[:3]], "longest": [pick(e) for e in ordered[-3:][::-1]],
    }


def _unit(logs, u, info):
    n = len(logs)
    team = info["team"]
    deaths, causes, phases, killers = [], Counter(), Counter(), Counter()
    dealt, taken, kills, lifespan = [], [], [], []
    by_weapon = defaultdict(lambda: {"shots": 0, "hits": 0, "damage": 0.0, "dmg_per_battle": [], "max_hit": 0.0})
    by_phys = defaultdict(lambda: {"tries": 0, "hits": 0, "damage": 0.0})
    range_shots, range_hits, range_dmg = Counter(), Counter(), Counter()
    ranges_all = []
    lost_loc = defaultdict(lambda: {"battles": 0, "turns": []})
    crit = Counter()
    heat_means, heat_max, prone_turns, shut_turns, turns_alive = [], [], [], [], []
    first_hit_turn = []
    for r, log in logs:
        d = log["deaths"].get(u)
        if d:
            deaths.append(d[0]); lifespan.append(d[0]); causes[d[2] or "Unknown"] += 1; phases[d[1]] += 1
            killer = log["killed_by"].get(u)
            if killer:
                killers[f"{killer[0]}: {killer[1]}"] += 1
        else:
            lifespan.append(r.turns_taken)
        # damage dealt: shots and physical attacks by this unit; taken: HP the unit lost (every source)
        per_w = defaultdict(float)
        dealt_b = 0.0
        for turn, att, tgt, w, rng, tn, roll, hit, dmg in log["shots"]:
            if att != u:
                continue
            row = by_weapon[w]
            row["shots"] += 1 if rng is not None else 0     # a pooled-cluster lump is damage, not a shot
            row["hits"] += 1 if (hit and rng is not None) else 0
            row["damage"] += dmg
            row["max_hit"] = max(row["max_hit"], dmg)
            per_w[w] += dmg
            dealt_b += dmg
            if rng is not None:
                range_shots[rng] += 1
                range_hits[rng] += 1 if hit else 0
                range_dmg[rng] += dmg
                ranges_all.append(rng)
        for w, v in per_w.items():
            by_weapon[w]["dmg_per_battle"].append(v)
        for turn, att, tgt, name, hit, dmg in log["phys"]:
            if att != u:
                continue
            row = by_phys[name]
            row["tries"] += 1
            row["hits"] += 1 if hit else 0
            row["damage"] += dmg
            dealt_b += dmg
        dealt.append(dealt_b)
        kills.append(sum(1 for v, k in log["killed_by"].items() if k[0] == u))
        # state per turn
        snaps = [t["units"][u] for t in log["turns"] if u in t["units"]]
        final = snaps[-1] if snaps else None
        max_hp = info["max_hp"] or 1
        taken.append(max_hp - final["hp"] if final else 0)
        if final:
            for loc in final["lost"]:
                lost_loc[loc]["battles"] += 1
            for key, label in (("engine", "Engine hit"), ("gyro", "Gyro hit")):
                if final[key]:
                    crit[label] += 1
            if final["cockpit"]:
                crit["Cockpit hit"] += 1
            if final["explosions"]:
                crit["Ammo / other explosion"] += 1
            if final["pilot_hits"]:
                crit["Pilot wounded"] += 1
            if final["crippled"]:
                crit["Crippled"] += 1
        # turn each location was first lost
        seen = {}
        for t in log["turns"]:
            s = t["units"].get(u)
            if s:
                for loc in s["lost"]:
                    seen.setdefault(loc, t["turn"])
        for loc, tt in seen.items():
            lost_loc[loc]["turns"].append(tt)
        live = [t["units"][u] for t in log["turns"] if u in t["units"] and t["turn"] >= 1]
        if live:
            heat_means.append(sum(s["heat"] for s in live) / len(live))
            heat_max.append(max(s["heat"] for s in live))
            prone_turns.append(sum(1 for s in live if s["prone"]))
            shut_turns.append(sum(1 for s in live if s["shutdown"]))
            turns_alive.append(len(live))
    died = len(deaths)
    max_range = max(ranges_all) if ranges_all else 0
    rng_rows = [{"range": k, "shots": range_shots[k], "hit_pct": 100 * range_hits[k] / range_shots[k],
                 "damage": range_dmg[k]} for k in sorted(range_shots)]
    weapons = []
    for w, row in by_weapon.items():
        per_battle = row["dmg_per_battle"] + [0.0] * (n - len(row["dmg_per_battle"]))
        weapons.append({"name": w, "shots": row["shots"], "hits": row["hits"],
                        "hit_pct": 100 * row["hits"] / row["shots"] if row["shots"] else 0.0,
                        "damage": row["damage"], "per_battle": describe(per_battle),
                        "dmg_per_hit": row["damage"] / row["hits"] if row["hits"] else 0.0,
                        "max_hit": row["max_hit"]})
    weapons.sort(key=lambda x: -x["damage"])
    phys = sorted(({"name": k, "tries": v["tries"], "hits": v["hits"],
                    "hit_pct": 100 * v["hits"] / v["tries"] if v["tries"] else 0.0, "damage": v["damage"]}
                   for k, v in by_phys.items()), key=lambda x: -x["damage"])
    return {
        "team": team,
        "died": _prop(died, n),
        "death_turn": describe(deaths), "death_turn_hist": histogram(deaths, integer=True),
        "lifespan": describe(lifespan),
        "causes": dict(causes.most_common()), "death_phase": dict(phases.most_common()),
        "killed_by": dict(killers.most_common(8)),
        "damage_dealt": describe(dealt), "damage_dealt_hist": histogram(dealt),
        "damage_taken": describe(taken), "damage_taken_hist": histogram(taken),
        "kills": describe(kills), "kills_total": sum(kills), "kills_per_game": sum(kills) / n,
        "weapons": weapons, "physical": phys, "ranges": rng_rows,
        "range_mean": sum(ranges_all) / len(ranges_all) if ranges_all else 0.0, "range_max": max_range,
        "locations_lost": {loc: {"pct": 100 * v["battles"] / n, "mean_turn": sum(v["turns"]) / len(v["turns"])}
                           for loc, v in sorted(lost_loc.items(), key=lambda kv: -kv[1]["battles"])},
        "criticals": {k: 100 * c / n for k, c in crit.items()},
        "heat_mean": describe(heat_means), "heat_peak": describe(heat_max),
        "prone_turns": describe(prone_turns), "shutdown_turns": describe(shut_turns),
        "turns_alive": describe(turns_alive),
    }


def _state_at(log, turn, u):
    """A unit's snapshot at the end of `turn`, or its last one when the battle ended before it."""
    last = None
    for t in log["turns"]:
        if t["turn"] > turn:
            break
        last = t["units"].get(u, last)
    return last


def _curves(logs, labels, team_order, teams):
    """Mean HP %, probability of still standing and mean heat for every unit, by turn - to the turn
    90% of the battles had ended by (a longer tail is a handful of battles)."""
    horizon = max(1, int(math.ceil(percentile(sorted(r.turns_taken for r, _ in logs), 90))))
    out = {"horizon": horizon, "unit": {}}
    for u in labels:
        max_hp = logs[0][1]["units"][u]["max_hp"] or 1
        hp = [[] for _ in range(horizon + 1)]
        alive = [0] * (horizon + 1)
        heat = [[] for _ in range(horizon + 1)]
        for r, log in logs:
            for t in range(horizon + 1):
                s = _state_at(log, t, u)
                if s is None:
                    continue
                hp[t].append(100 * s["hp"] / max_hp)
                heat[t].append(s["heat"])
                alive[t] += 0 if s["destroyed"] else 1
        n = len(logs)
        out["unit"][u] = {
            "hp_mean": [sum(x) / len(x) if x else None for x in hp],
            "hp_p10": [percentile(sorted(x), 10) if x else None for x in hp],
            "hp_p90": [percentile(sorted(x), 90) if x else None for x in hp],
            "alive": [a / n for a in alive],
            "heat_mean": [sum(x) / len(x) if x else None for x in heat],
        }
    out["team"] = {}
    for t, members in teams.items():
        tot_hp = sum(logs[0][1]["units"][u]["max_hp"] for u in members) or 1
        standing = [[] for _ in range(horizon + 1)]
        force = [[] for _ in range(horizon + 1)]
        for r, log in logs:
            for k in range(horizon + 1):
                snaps = [_state_at(log, k, u) for u in members]
                snaps = [s for s in snaps if s]
                standing[k].append(sum(0 if s["destroyed"] else 1 for s in snaps))
                force[k].append(100 * sum(s["hp"] for s in snaps) / tot_hp)
        out["team"][t] = {
            "units": len(members),
            "standing_mean": [sum(x) / len(x) for x in standing],
            "standing_p10": [percentile(sorted(x), 10) for x in standing],
            "standing_p90": [percentile(sorted(x), 90) for x in standing],
            "force_mean": [sum(x) / len(x) for x in force],
            "force_p10": [percentile(sorted(x), 10) for x in force],
            "force_p90": [percentile(sorted(x), 90) for x in force],
        }
    return out


def _team(logs, t, members, teams):
    n = len(logs)
    survivors, first_kill, second_kill = [], [], []
    focus_turns, shooting_turns = 0, 0
    share = {u: [] for u in members}
    top_target_share = []
    for r, log in logs:
        survivors.append(sum(1 for u in members if u not in log["deaths"]))
        foe_deaths = sorted(d[0] for v, d in log["deaths"].items() if log["teams"][v] != t)
        if foe_deaths:
            first_kill.append(foe_deaths[0])
        if len(foe_deaths) > 1:
            second_kill.append(foe_deaths[1])
        # focus fire: per turn, how many of this team's shooters fired at the same target
        per_turn = defaultdict(lambda: defaultdict(set))
        dmg_by_target = Counter()
        dmg_by_unit = Counter()
        for turn, att, tgt, w, rng, tn, roll, hit, dmg in log["shots"]:
            if att in members:
                per_turn[turn][tgt].add(att)
                dmg_by_target[tgt] += dmg
                dmg_by_unit[att] += dmg
        for turn, targets in per_turn.items():
            shooters = set().union(*targets.values())
            if len(shooters) > 1:
                shooting_turns += 1
                if any(len(a) > 1 for a in targets.values()):
                    focus_turns += 1
        for _, att, tgt, name, hit, dmg in log["phys"]:
            if att in members:
                dmg_by_unit[att] += dmg
                dmg_by_target[tgt] += dmg
        total = sum(dmg_by_unit.values())
        for u in members:
            share[u].append(100 * dmg_by_unit[u] / total if total else 0.0)
        if dmg_by_target:
            top_target_share.append(100 * max(dmg_by_target.values()) / sum(dmg_by_target.values()))
    # order enemies die in (their most-damaged first?) is left to the per-unit death-turn tables
    cohesion = []
    for r, log in logs:
        for snap in log["turns"]:
            hexes = [snap["units"][u]["hex"] for u in members if u in snap["units"] and not snap["units"][u]["destroyed"]
                     and snap["units"][u]["hex"]]
            if len(hexes) > 1:
                pts = [_hex_xy(h) for h in hexes]
                d = [_hex_dist(pts[i], pts[j]) for i in range(len(pts)) for j in range(i + 1, len(pts))]
                cohesion.append(sum(d) / len(d))
    return {
        "units": len(members),
        "survivors": describe(survivors), "survivors_hist": histogram(survivors, integer=True),
        "survivors_counts": dict(sorted(Counter(survivors).items())),
        "first_kill_turn": describe(first_kill), "second_kill_turn": describe(second_kill),
        "focus_fire_pct": 100 * focus_turns / shooting_turns if shooting_turns else None,
        "top_target_damage_share": describe(top_target_share),
        "damage_share": {u: describe(v) for u, v in share.items()},
        "cohesion": describe(cohesion),
    }


def _hex_xy(label):
    return hex_geometry.parse_hex_label(label)


def _hex_dist(a, b):
    return hex_distance(a, b)


# =============================================================================
# ==========================  WRITING THE PAGE  ================================
# =============================================================================
def render(analysis):
    """The viewer page with this analysis inside it."""
    with open(VIEWER_TEMPLATE, encoding="utf-8") as f:
        page = f.read()
    payload = json.dumps(analysis, separators=(",", ":"), default=str).replace("</", "<\\/")
    return page.replace(DATA_PLACEHOLDER, payload, 1)


def file_stem(analysis):
    names = [analysis["units"][members[0]]["name"] if len(members) == 1 else f"{t}{len(members)}"
             for t, members in analysis["teams_members"].items()]
    stem = f"{'_vs_'.join(names)}_n{analysis['n']}_seed{analysis['seed']}"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", stem)


def write(analysis, directory=None):
    """Write the page and its JSON; returns the page's path."""
    directory = directory or config.STATS_DIR
    if not os.path.isabs(directory):            # relative = under the repo root
        directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), directory)
    os.makedirs(directory, exist_ok=True)
    stem = os.path.join(directory, file_stem(analysis))
    with open(stem + ".json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(analysis, f, separators=(",", ":"), default=str)
    with open(stem + ".html", "w", encoding="utf-8", newline="\n") as f:
        f.write(render(analysis))
    return stem + ".html"


def report(results, title=""):
    """run_batch's hook: analyze the batch, write the page, print where it went."""
    analysis = analyze(results, title)
    if analysis is None:
        return None
    path = write(analysis)
    print(f"Stats report saved: {path}")
    return path
