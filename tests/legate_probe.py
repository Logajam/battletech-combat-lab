"""
tests/legate_probe.py - a diagnostic battery (2026-10-30, session 15; Daniel: measure "not just how wrong
the prediction was, but to the degree it was wrong"). Princess Red v Gladiator Blue, the
baseline_battery setup, with probes that leave the battle untouched (same results as the battery).

Per turn it records:
  - Legate's estimate of each enemy's end hex vs where it really ended (and where it started);
  - each Gladiator move: its primary foe, the chosen spot, the predicted RAW damage taken from each
    enemy and dealt (no exposure weights), and the objective's parts;
  - the Ranged Attack Phase: who shot whom, the damage each unit dealt and took;
  - after movement: every unit's hex (cohesion).
  - with --calib: every attacker v every enemy at the start of the Ranged Attack Phase, everyone at
    their real spots: the movement model's expected damage (structure-weighted and raw) and the fire
    phase's own dry run - to compare with what the pairs that fired really dealt.
  - each Gladiator move is re-scored at the end of the Movement Phase with the enemies at their TRUE
    end spots (same model): the damage the estimate missed, and the regret of the choice.

    python tests/legate_probe.py OUT.json FIRST LAST [--estimate hold] [--calib] [--set=CONFIG_NAME=literal ...]
    python tests/legate_probe_report.py OUT.json [more.json ...]
Battles FIRST..LAST of the 20-battle battery (seed 12345, cap 50). --estimate hold: Legate's estimate
replaced by "every enemy stands still" (an A/B). Probes patch functions in this process only.
"""
import io, json, os, sys, time
from contextlib import redirect_stdout, redirect_stderr

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, "tests"))
os.chdir(REPO)
os.environ.setdefault("INTEGRATION_DATA_DIR", "./data")
import INTEGRATION__config as config
import INTEGRATION__orchestrator as orchestrator
import INTEGRATION__legate as legate
import INTEGRATION__movement_selection as ms
import INTEGRATION__attack_resolution as ar
import INTEGRATION__forces as forces
import baseline_battery as bb

out_path, first, last = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
flags = sys.argv[4:]
estimate_mode = "if_then"
if "--estimate" in flags:
    estimate_mode = flags[flags.index("--estimate") + 1]
config.FORCES = bb.forces("princess", None)
config.STITCH_MAPS, config.STITCH_BOARDS = True, bb.BOARDS
config.STITCH_GRID_COLS, config.STITCH_GRID_ROWS = 2, 1
config.PROMPT_FOR_MAP = False
config.DEPLOYMENT, config.DEPLOYMENT_DEPTH, config.WORKERS = "home_edge", 0, 1
config.VERBOSE = False
config.REPLAY_BATTLES = 0
for f in flags:
    if f.startswith("--set="):                       # --set=NAME=python literal
        k, v = f[6:].split("=", 1)
        setattr(config, k, eval(v))

REC = {"turns": []}
T = {}                       # current turn record


def name(m):
    return m.side_name


def new_turn():
    global T
    T = {"plans": {}, "moves": [], "fire": [], "taken": {}, "dealt": {}, "start": {}, "end": {}, "pos": {}}
    REC["cur"].append(T)


# --- Legate's estimate -------------------------------------------------------------------------
_plan_turn = legate.plan_turn
def plan_turn(units, terrain_map):
    new_turn()
    T["start"] = {name(u): u.hex for u in units if u.hex is not None and not u.destroyed}
    _plan_turn(units, terrain_map)
    for team, plan in legate._PLANS.items():
        by_id = {id(u): u for u in units}
        T["plans"][team] = {name(by_id[i]): st[0] for i, st in plan.items()}
        T["plans"][team + "_own"] = {name(by_id[i]): st[0] for i, st in legate._OWN.get(team, {}).items()}
legate.plan_turn = plan_turn

if estimate_mode == "hold":
    legate.estimate_for = lambda team, foe: None            # A/B: enemies taken to stand still

def truth(row, lx, key, mover):
    """Re-score every spot the mover probed with each enemy where it REALLY ended (same model):
    the chosen spot's raw damage from each enemy, and the regret of the choice in score points."""
    me_side = lx.unit.side
    foes = [f for f in [lx.primary] + lx.others if f.hex is not None and not f.destroyed]
    obj = legate.objective_for(me_side, foes) if foes else None
    real = []
    for f in foes:
        unit = next((u for u, _ in lx.entries if u.mech is f), None) or legate._Unit(f, forces.battle(), lx.terrain_map, lite=True)
        real.append((unit, legate._real_state(f)))
    states = [p[2] for p in lx._probe.values()]
    best = None
    for k, (on_me, on_them, o, got) in lx._probe.items():
        d = r = 0.0
        raw_me = {}
        for unit, st in real:
            if st[0] == o.label:
                continue
            c = lx.unit.rows(unit.mech, st, [o]).get(legate._key(o))
            if c is None:
                continue
            d = max(d, c.dealt * unit.side.exposure[c.side_on_defender])
            r += c.received * me_side.exposure[c.side_on_mover]
            raw_me[name(unit.mech)] = c.received
        score = obj(d, r, 1.0, 1.0, me_side.psr_for(o)) if obj else 0.0
        pred = obj(got[0], got[1], 1.0, 1.0, me_side.psr_for(o)) if obj else 0.0
        if k == key:
            row["true_on_me"] = raw_me
            row["true_score_chosen"], row["pred_score_chosen"] = score, pred
        if best is None or score > best[0]:
            best = (score, o.label, pred)
    row["true_score_best"], row["true_best_hex"], row["pred_score_of_true_best"] = best
    row["spots"] = len(lx._probe)


_end_phase = legate.end_phase
def end_phase():
    units = forces.battle()
    T["end"] = {name(u): u.hex for u in units if u.hex is not None and not u.destroyed}
    import INTEGRATION__timing as timing
    with config.quiet():
        for item in PENDING:
            try:
                truth(*item)
            except Exception as e:
                item[0]["truth_error"] = repr(e)
    PENDING.clear()
    _end_phase()
legate.end_phase = end_phase

# --- each Gladiator move: the predicted raw figures at every scored spot ---------------------------
LAST = {}
PENDING = []        # (move row, its Extras, chosen key, mover) to re-score at the true positions
_le = ms._legate_extras
def legate_extras(mover, other, terrain_map, me):
    lx = _le(mover, other, terrain_map, me)
    if lx is not None:
        lx._probe = {}
        LAST["lx"] = lx
    return lx
ms._legate_extras = legate_extras

_adjust = legate.Extras.adjust
def adjust(self, o, dealt, received, dealt_mult, received_mult):
    on_me = {name(self.primary): received}
    on_them = {name(self.primary): dealt}
    for foe, st in self.entries:
        if st[0] == o.label:
            st = legate._hold(foe.mech)                  # as Extras.adjust (2026-11-06)
        cand = self.unit.rows(foe.mech, st, [o]).get(legate._key(o))
        if cand is None:
            continue
        on_me[name(foe.mech)] = cand.received
        on_them[name(foe.mech)] = cand.dealt
    got = _adjust(self, o, dealt, received, dealt_mult, received_mult)
    self._probe[legate._key(o)] = (on_me, on_them, o, got)
    return got
legate.Extras.adjust = adjust

_cn = ms._choose_normal
def choose_normal(mover, other, terrain_map, battle_rng, moves_first, standup_mp=None, entry_edge=None):
    LAST.pop("lx", None)
    got = _cn(mover, other, terrain_map, battle_rng, moves_first, standup_mp, entry_edge)
    pick, note = got[0], got[1]
    lx = LAST.get("lx")
    row = {"mover": name(mover), "team": mover.team, "bot": mover.bot, "primary": name(other),
           "moves_first": moves_first, "from": mover.hex, "note": note}
    if pick is not None:
        row["to"] = pick["hex"]
        if lx is not None:
            key = (pick["hex"], pick["facing"], pick["mode"], pick["fc"], pick["mp_spent"])
            probe = lx._probe.get(key)
            if probe is not None:
                row["on_me"], row["on_them"] = probe[0], probe[1]
                PENDING.append((row, lx, key, mover))
    if lx is not None and T is not None:
        o = ms.effective_hp(mover)
        row["hp_eff"] = o
    T["moves"].append(row)
    return got
ms._choose_normal = choose_normal

_obj_for = legate.objective_for
def objective_for(me, foes):
    o = _obj_for(me, foes)
    if isinstance(o, legate.MultiLifetime) and T is not None:
        T.setdefault("obj", {})[name(me.mech)] = {"hp": o.hp, "mine": o.mine, "theirs": o.theirs,
                                                  "foes": len(foes)}
    return o
legate.objective_for = objective_for

def calib(units, terrain_map):
    """Every attacker v every enemy, everyone where they really are: the movement model's expected damage
    (MoveEvaluator, what the picker scores with) and the fire phase's own dry run (its weapon choice)."""
    import INTEGRATION__ranged_combat as rc
    import hex_geometry as hg
    out = {}
    live = [u for u in units if u.hex is not None and not u.destroyed]
    with config.quiet():
        for a in live:
            st = (*hg.parse_hex_label(a.hex), hg.compass_to_facing(a.facing), a.move_fc, a.move_mode, a.mp_spent)
            for b in live:
                if b.team == a.team:
                    continue
                vals = []
                saved = config.MOVEMENT_STRUCTURE_WEIGHT
                for w in (saved, 1.0):                     # as the picker sees it, and raw points
                    config.MOVEMENT_STRUCTURE_WEIGHT = w
                    try:
                        ev = rc.MoveEvaluator(a, b, terrain_map)
                        prep = ev.prepare([st])
                        got = ev.evaluate(b.hex, b.facing, b.move_fc, b.move_mode, b.mp_spent, prep)
                        vals.append(got[0].dealt if got else None)
                    except Exception as e:
                        vals.append("err " + repr(e)[:80])
                    finally:
                        config.MOVEMENT_STRUCTURE_WEIGHT = saved
                dry = ar.declare_attacks(a, b, terrain_map, ar.SideReport(), dry=True)
                out[name(a) + "|" + name(b)] = (vals[0], None if dry is None else dry[1], vals[1])
    return out


# --- the Ranged Attack Phase -------------------------------------------------------------------------
_rrp = ar.run_ranged_phase
def run_ranged_phase(order, target_of, terrain_map, battle_rng):
    units = forces.battle()
    T["pos"] = {name(u): u.hex for u in units if u.hex is not None and not u.destroyed}
    hp0 = {name(u): ar.total_hp(u) for u in units}
    if "--calib" in flags:
        T["model"] = calib(units, terrain_map)
    picks = {}
    def tgt(u):
        t = target_of(u)
        picks[name(u)] = name(t) if t is not None else None
        return t
    reports = _rrp(order, tgt, terrain_map, battle_rng)
    T["fire"] = picks
    T["taken"] = {name(u): hp0[name(u)] - ar.total_hp(u) for u in units if name(u) in hp0}
    T["dealt"] = {k: r.damage_dealt for k, r in reports.items()}
    return reports
ar.run_ranged_phase = run_ranged_phase
orchestrator.attack_resolution.run_ranged_phase = run_ranged_phase

with redirect_stdout(io.StringIO()):
    terrain = orchestrator._load_map()
    roster = config.load_roster()
battles = []
for n in range(first, last + 1):
    REC["cur"] = []
    t0 = time.time()
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        result = orchestrator._run_one_roster(n, 20, 12345, 50, roster, terrain)
    teams = {k: (s.units - s.units_lost, round(s.damage_dealt)) for k, s in result.teams.items()}
    battles.append({"battle": n, "winner": result.winner, "turns": result.turns_taken, "teams": teams,
                    "turn_log": REC["cur"]})
    print(n, result.winner, result.turns_taken, teams, round(time.time() - t0), flush=True)
    with open(out_path, "w") as f:
        json.dump({"flags": flags, "battles": battles}, f, default=str)
