// Translated from INTEGRATION__legate.py, INTEGRATION__triage.py, INTEGRATION__peril.py (peak only) and INTEGRATION__vision.py:
// the battlefield-keeping layer that gives a Gladiator the whole enemy force. Switches whose research layers are not
// translated (herding, cohesion, team value, stack, peril blending, tiered move order) must be off: asking for one is a
// loud panic, never a quiet default.
use std::collections::{HashMap, HashSet};

use crate::battle::{Battle, UnitId};
use crate::hex_geometry;
use crate::los::hex_distance;
use crate::mech_state::*;
use crate::move_eval::{Candidate, MoveEvaluator};
use crate::move_options::Opt;
use crate::move_select::{self, Objective, Side};

/// (hex label, facing compass, hexes moved, mode, MP spent)
pub type State5 = (String, &'static str, i64, &'static str, i64);
type Key5 = (String, &'static str, &'static str, i64, i64);

#[derive(Default)]
pub struct LegateState {
    /// team -> {enemy unit: its estimated end state}
    plans: HashMap<String, HashMap<UnitId, State5>>,
    /// team -> {own unit: its estimated end state}
    own: HashMap<String, HashMap<UnitId, State5>>,
    rates: HashMap<(UnitId, UnitId), (f64, f64)>,
    shares: HashMap<(UnitId, UnitId), f64>,
    /// peril: (attacker, target) -> its damage profile table (one row per extra to-hit point), None = cannot fire
    profiles: HashMap<(UnitId, UnitId, bool), Option<Vec<Vec<f64>>>>,
    footprints: HashMap<UnitId, Vec<(i64, i64)>>,
    peaks: HashMap<(UnitId, UnitId, bool, (i64, i64)), f64>,
    vision: HashMap<((i64, i64), (i64, i64)), Option<(bool, i64, i64)>>,
}

fn check_switches(b: &Battle) {
    for (k, off) in [("LEGATE_HERDING", false), ("LEGATE_COHESION", false), ("STACK", false)] {
        assert!(b.cfg.b(k) == off, "{} on is not translated yet", k);
    }
    assert!(b.cfg.get("LEGATE_TEAM_VALUE").is_null(), "LEGATE_TEAM_VALUE is not translated yet");
    assert!(b.cfg.s("PERIL") == "off", "PERIL other than off is not translated yet");
    assert!(b.cfg.s("MOVE_ORDER") == "index", "MOVE_ORDER tiered is not translated yet");
}

/// A new phase: the plans are spent (the rates are valid until the next heat phase's damage, so they go too).
pub fn end_phase(b: &mut Battle) {
    b.legate.plans.clear();
    b.legate.rates.clear();
    b.legate.shares.clear();
    b.legate.profiles.clear();
    b.legate.footprints.clear();
    b.legate.peaks.clear();
}

fn xy(label: &str) -> (i64, i64) {
    hex_geometry::parse_hex_label(label).unwrap()
}

fn hold(b: &Battle, u: UnitId) -> State5 {
    let m = &b.units[u];
    (m.hex.clone().unwrap(), move_options_facing(&m.facing), 0, "Stand Still", 0)
}

fn move_options_facing(compass: &str) -> &'static str {
    hex_geometry::facing_to_compass(hex_geometry::compass_to_facing(compass).unwrap()).unwrap()
}

fn real_state(b: &Battle, u: UnitId) -> State5 {
    let m = &b.units[u];
    (m.hex.clone().unwrap(), move_options_facing(&m.facing), m.move_fc, crate::move_options::mode_str(&m.move_mode), m.mp_spent)
}

fn state_of(o: &Opt) -> State5 {
    (o.label.clone(), o.facing_compass, o.fc, o.mode, o.mp_spent)
}

fn key_of(o: &Opt) -> Key5 {
    (o.label.clone(), o.facing_compass, o.mode, o.fc, o.mp_spent)
}

/// Can this foe matter to the mover's move at all (the shortcut Princess's group code uses)?
pub fn can_matter(b: &mut Battle, mover: UnitId, foe: UnitId) -> bool {
    let reach = |b: &mut Battle, u: UnitId| -> i64 { compute_jump_mp(&b.units[u]).max((compute_walk_mp(&b.units[u]) as f64 * 1.5).ceil() as i64) + move_select::max_range(b, u) };
    let (rm, rf) = (reach(b, mover), reach(b, foe));
    let (Some(mh), Some(fh)) = (b.units[mover].hex.clone(), b.units[foe].hex.clone()) else { return true };
    hex_distance(xy(&mh), xy(&fh)) <= rm + rf + 2
}

// =============================================================================================================
// the picker score
// =============================================================================================================
/// (a's future damage on b, b's on a) per turn, blended with the battle so far. Cached for the phase.
pub fn pair_rates(b: &mut Battle, a: UnitId, c: UnitId) -> (f64, f64) {
    if let Some(g) = b.legate.rates.get(&(a, c)) {
        return *g;
    }
    let mut mine = move_select::future_damage(b, a, c);
    let mut theirs = move_select::future_damage(b, c, a);
    if let Some(k) = b.cfg.get("MOVEMENT_LIFETIME_HISTORY_K").as_f64() {
        let (dealt, taken, fought) = move_select::battle_record(b, a, c);
        let f = fought as f64;
        mine = (k * mine + dealt) / (k + f);
        theirs = (k * theirs + taken) / (k + f);
    }
    b.legate.rates.insert((a, c), (mine, theirs));
    b.legate.rates.insert((c, a), (theirs, mine));
    (mine, theirs)
}

/// The share of `foe`'s future fire that lands on `me` (LEGATE_FIRE_SPLIT).
pub fn fire_share(b: &mut Battle, foe: UnitId, me: UnitId) -> f64 {
    match b.cfg.s("LEGATE_FIRE_SPLIT") {
        "none" => return 1.0,
        "proportional" => {}
        o => panic!("Unknown LEGATE_FIRE_SPLIT {:?}", o),
    }
    let mine = pair_rates(b, foe, me).0;
    if mine <= 0.0 {
        return 0.0;
    }
    let my_team = b.units[me].team.clone();
    let mut team: Vec<UnitId> = Vec::new();
    for u in crate::forces::standing(b) {
        if b.units[u].team == my_team && b.units[u].hex.is_some() && (u == me || can_matter(b, u, foe)) {
            team.push(u);
        }
    }
    if !team.contains(&me) {
        team.push(me);
    }
    let mut total = 0.0;
    for u in team {
        total += pair_rates(b, foe, u).0;
    }
    if total > 0.0 { mine / total } else { 1.0 }
}

/// The share of `foe`'s fire THIS turn counted on `me` in a move score. Cached for the phase.
pub fn now_share(b: &mut Battle, foe: UnitId, me: UnitId) -> f64 {
    if !b.cfg.b("LEGATE_SPLIT_THIS_TURN") {
        return 1.0;
    }
    if let Some(g) = b.legate.shares.get(&(foe, me)) {
        return *g;
    }
    let g = fire_share(b, foe, me);
    b.legate.shares.insert((foe, me), g);
    g
}

/// movement_selection._Lifetime against several foes: damage taken is the SUM over the foes, damage dealt the MAX.
pub fn multi_lifetime(b: &mut Battle, me: UnitId, foes: &[UnitId]) -> Objective {
    let floor = b.cfg.f("MOVEMENT_LIFETIME_FUTURE_FLOOR");
    let hp = move_select::effective_hp(b, me);
    let rates: Vec<(f64, f64)> = foes.iter().map(|f| pair_rates(b, me, *f)).collect();
    let mut mine = floor;
    for (m, _) in &rates {
        if *m > mine {
            mine = *m;
        }
    }
    let mut sum = 0.0;
    for ((_, t), f) in rates.iter().zip(foes) {
        sum += t * fire_share(b, *f, me);
    }
    let theirs = if sum > floor { sum } else { floor };
    Objective::Multi { hp, mine, theirs }
}

/// objective_for: the picker score for `me` against a set of foe mechs.
pub fn objective_for(b: &mut Battle, me: UnitId, foes: &[UnitId]) -> Objective {
    if b.cfg.s("MOVEMENT_OBJECTIVE") == "lifetime" && !foes.is_empty() {
        multi_lifetime(b, me, foes)
    } else {
        Objective::Ratio { eps: b.cfg.f("MOVEMENT_RATIO_EPSILON") }
    }
}

// =============================================================================================================
// one unit, modeled
// =============================================================================================================
struct Unit {
    id: UnitId,
    side: Side,
    prepared: Vec<Opt>,
    state: State5,
    locked: bool,
    tried: HashSet<String>,
    best: Option<(f64, State5)>,
    evals: HashMap<UnitId, MoveEvaluator>,
    rows: HashMap<(UnitId, State5), HashMap<Key5, Option<Candidate>>>,
}

impl Unit {
    fn new(b: &mut Battle, id: UnitId, lite: bool, side: Option<Side>) -> Unit {
        let mut side = side.unwrap_or_else(|| Side::new(b, id, true));
        let mut prepared = vec![];
        if !lite {
            // _blocking: ground steps cannot enter a mobile enemy's hex while its options are built
            let blocked: Vec<serde_json::Value> = crate::forces::blocked_xy(b, id).into_iter().map(|(x, y)| serde_json::json!([x, y])).collect();
            b.units[id].blocked_hex = Some(serde_json::Value::Array(blocked));
            let options = move_select::opponent_options(b, id, &mut side);
            b.units[id].blocked_hex = Some(serde_json::Value::Null);
            prepared = crate::move_options::prepare_options(b, id, &options);
        }
        let state = hold(b, id);
        Unit { id, side, prepared, state, locked: false, tried: HashSet::new(), best: None, evals: HashMap::new(), rows: HashMap::new() }
    }

    /// {state key: candidate} for each of `states` against `foe` standing at foe_state - None without line of sight.
    fn rows(&mut self, b: &mut Battle, foe: UnitId, foe_state: &State5, states: &[Opt]) -> &HashMap<Key5, Option<Candidate>> {
        let memo_key = (foe, foe_state.clone());
        let missing: Vec<Opt> = states.iter().filter(|o| !self.rows.get(&memo_key).map_or(false, |m| m.contains_key(&key_of(o)))).cloned().collect();
        if !missing.is_empty() {
            let id = self.id;
            let ev = self.evals.entry(foe).or_insert_with(|| MoveEvaluator::new(b, id, foe));
            let got = ev.evaluate(b, &foe_state.0, foe_state.1, foe_state.2, foe_state.3, foe_state.4, &missing, true);
            let got: HashMap<Key5, Candidate> = got.into_iter().map(|c| ((c.hex.clone(), c.facing, c.mode, c.fc, c.mp_spent), c)).collect();
            let memo = self.rows.entry(memo_key.clone()).or_default();
            for o in &missing {
                memo.insert(key_of(o), got.get(&key_of(o)).cloned());
            }
        }
        &self.rows[&memo_key]
    }
}

type Row = (f64, Opt, (f64, f64));

/// combine: score each of `states` for `me` against several foes: damage taken adds up over the foes, damage dealt is
/// the best (both with the exposure factors); a state with no line of sight to any foe is left out.
fn combine(b: &mut Battle, units: &mut [Unit], me: usize, entries: &[(usize, State5)], states: &[Opt], objective: &Objective) -> Vec<Row> {
    let mut per_foe: Vec<(usize, HashMap<Key5, Option<Candidate>>)> = Vec::new();
    for (f, st) in entries {
        let fid = units[*f].id;
        let rows = units[me].rows(b, fid, st, states).clone();
        per_foe.push((*f, rows));
    }
    let mut out = Vec::new();
    for o in states {
        let (mut dealt, mut received) = (0.0f64, 0.0f64);
        let mut seen = false;
        for (f, rows) in &per_foe {
            let Some(Some(cand)) = rows.get(&key_of(o)) else { continue };
            seen = true;
            let v = cand.dealt * units[*f].side.exp(cand.side_on_defender);
            if v > dealt {
                dealt = v;
            }
            let share = now_share(b, units[*f].id, units[me].id);
            received += cand.received * units[me].side.exp(cand.side_on_mover) * share;
        }
        if seen {
            let psr = units[me].side.psr_for_opt(b, o);
            out.push((objective.score(dealt, received, 1.0, 1.0, psr), o.clone(), (dealt, received)));
        }
    }
    out
}

// =============================================================================================================
// the estimate
// =============================================================================================================
/// Give every unit a spot: proposals = [(unit, [(score, state), ...best first, one per hex])]; locked = {unit: hex}.
fn resolve(proposals: &[(usize, Vec<(f64, Opt)>)], locked: &HashMap<usize, String>) -> HashMap<usize, (f64, Opt)> {
    let reserved: HashSet<&String> = locked.values().collect();
    let mut pointer: HashMap<usize, usize> = proposals.iter().map(|(u, _)| (*u, 0)).collect();
    let lists: HashMap<usize, &Vec<(f64, Opt)>> = proposals.iter().map(|(u, r)| (*u, r)).collect();
    let mut holder: HashMap<String, usize> = HashMap::new();
    let mut placed: HashMap<usize, (f64, Opt)> = HashMap::new();
    let mut pending: std::collections::VecDeque<usize> = proposals.iter().map(|(u, _)| *u).collect();
    while let Some(unit) = pending.pop_front() {
        let rows = lists[&unit];
        while pointer[&unit] < rows.len() {
            let (score, state) = &rows[pointer[&unit]];
            let label = &state.label;
            if reserved.contains(label) {
                *pointer.get_mut(&unit).unwrap() += 1;
                continue;
            }
            match holder.get(label).copied() {
                None => {
                    holder.insert(label.clone(), unit);
                    placed.insert(unit, (*score, state.clone()));
                    break;
                }
                Some(current) => {
                    if *score > placed[&current].0 {
                        holder.insert(label.clone(), unit);
                        placed.insert(unit, (*score, state.clone()));
                        placed.remove(&current);
                        *pointer.get_mut(&current).unwrap() += 1;
                        pending.push_back(current);
                        break;
                    }
                    *pointer.get_mut(&unit).unwrap() += 1;
                }
            }
        }
    }
    placed
}

fn proposals_for(b: &mut Battle, units: &mut [Unit], unit: usize, opposing: &[usize], taken: &HashSet<String>, objectives: &mut HashMap<usize, Objective>, asking: &[usize]) -> Vec<(f64, Opt)> {
    let prepared: Vec<Opt> = units[unit].prepared.iter().filter(|o| !taken.contains(&o.label)).cloned().collect();
    if prepared.is_empty() {
        return vec![];
    }
    let mut entries: Vec<(usize, State5)> = Vec::new();
    for f in opposing {
        if can_matter(b, units[unit].id, units[*f].id) {
            entries.push((*f, units[*f].state.clone()));
        }
    }
    let mut rows: Vec<Row> = vec![];
    if !entries.is_empty() && prepared.len() > 1 {
        if !objectives.contains_key(&unit) {
            let others: &[usize] = if asking.contains(&unit) { opposing } else { asking };
            let mut foes = Vec::new();
            for f in others {
                if can_matter(b, units[unit].id, units[*f].id) {
                    foes.push(units[*f].id);
                }
            }
            let o = objective_for(b, units[unit].id, &foes);
            objectives.insert(unit, o);
        }
        let objective = objectives[&unit].clone();
        let start = move_select::search_start(b, units[unit].id, &prepared);
        let starts = b.cfg.i("MOVEMENT_SEARCH_STARTS") as usize;
        // grid_search hands the closure a batch of states of one hex; the units live outside the closure's borrow of b
        let units_ptr: *mut [Unit] = units;
        let mut f = |bb: &mut Battle, states: &[Opt]| -> Vec<(f64, (Opt, (f64, f64)))> {
            // SAFETY: `units` is not otherwise touched while the search runs
            let us: &mut [Unit] = unsafe { &mut *units_ptr };
            combine(bb, us, unit, &entries, states, &objective).into_iter().map(|(s, o, p)| (s, (o, p))).collect()
        };
        rows = move_select::grid_search(b, &prepared, &mut f, start, starts, None).into_iter().map(|(s, (o, p))| (s, o, p)).collect();
    }
    if !rows.iter().any(|r| r.2 .0 > 0.0) {
        // Nothing it can hit from any spot it looked at: it closes on the nearest opposing unit.
        if !opposing.is_empty() {
            let here = xy(b.units[units[unit].id].hex.as_deref().unwrap());
            let mut target: Option<((i64, i64), i64)> = None;
            for f in opposing {
                let p = xy(&units[*f].state.0);
                let d = hex_distance(here, p);
                if target.map_or(true, |(_, bd)| d < bd) {
                    target = Some((p, d));
                }
            }
            let target_xy = target.unwrap().0;
            let mut ranked = prepared.clone();
            ranked.sort_by_key(|o| hex_distance(o.hex_xy(), target_xy));
            rows = ranked.into_iter().take(8).map(|o| (-1.0e6 - hex_distance(o.hex_xy(), target_xy) as f64, o, (0.0, 0.0))).collect();
        }
    }
    let mut best_by_hex: indexmap::IndexMap<String, (f64, Opt)> = indexmap::IndexMap::new();
    for (score, o, _) in rows {
        let better = best_by_hex.get(&o.label).map_or(true, |(s, _)| score > *s);
        if better {
            best_by_hex.insert(o.label.clone(), (score, o));
        }
    }
    let mut v: Vec<(f64, Opt)> = best_by_hex.into_values().collect();
    v.sort_by(|a, c| (-a.0).partial_cmp(&(-c.0)).unwrap());
    v
}

fn half_round(b: &mut Battle, units: &mut [Unit], movers: &[usize], opposing: &[usize], objectives: &mut HashMap<usize, Objective>, asking: &[usize]) {
    let taken: HashSet<String> = opposing.iter().map(|f| units[*f].state.0.clone()).collect();
    let free: Vec<usize> = movers.iter().copied().filter(|u| !units[*u].locked).collect();
    let mut proposals: Vec<(usize, Vec<(f64, Opt)>)> = Vec::new();
    for u in free {
        let rows = proposals_for(b, units, u, opposing, &taken, objectives, asking);
        proposals.push((u, rows));
    }
    let mut placed;
    loop {
        let locked: HashMap<usize, String> = movers.iter().filter(|u| units[**u].locked).map(|u| (*u, units[*u].state.0.clone())).collect();
        placed = resolve(&proposals, &locked);
        let mut newly = Vec::new();
        for (u, (_, o)) in &placed {
            if units[*u].tried.contains(&o.label) {
                newly.push(*u);
            }
        }
        newly.sort();
        if newly.is_empty() {
            break;
        }
        for u in newly {
            units[u].locked = true;
            if let Some((_, s)) = &units[u].best {
                units[u].state = s.clone();
            }
        }
        proposals.retain(|(u, _)| !units[*u].locked);
    }
    // (placed is walked in the order of the proposals, as the Python's dict)
    for (u, _) in &proposals {
        if let Some((score, o)) = placed.get(u) {
            units[*u].tried.insert(o.label.clone());
            units[*u].state = state_of(o);
            if units[*u].best.as_ref().map_or(true, |(s, _)| *score > *s) {
                units[*u].best = Some((*score, units[*u].state.clone()));
            }
        }
    }
}

/// The start of the Movement Phase: estimate where each side's enemies will end, for every team with a Gladiator
/// unit that faces two or more enemies on the board.
pub fn plan_turn(b: &mut Battle) {
    b.legate.plans.clear();
    b.legate.own.clear();
    b.legate.vision.clear();
    if !b.cfg.b("LEGATE") {
        return;
    }
    check_switches(b);
    let alive = crate::forces::standing(b);
    let on_board: Vec<UnitId> = alive.iter().copied().filter(|u| b.units[*u].hex.is_some()).collect();
    if on_board.len() != alive.len() {
        return;
    }
    for team in crate::forces::team_names(b, &alive) {
        let mine: Vec<UnitId> = on_board.iter().copied().filter(|u| b.units[*u].team.as_deref() == Some(team.as_str())).collect();
        let theirs: Vec<UnitId> = on_board.iter().copied().filter(|u| b.units[*u].team.as_deref() != Some(team.as_str())).collect();
        if theirs.len() < 2 || !mine.iter().any(|u| b.units[*u].bot == "gladiator") {
            continue;
        }
        let (plan, own) = estimate(b, &mine, &theirs);
        b.legate.plans.insert(team.clone(), plan);
        b.legate.own.insert(team, own);
    }
}

#[allow(clippy::type_complexity)]
fn estimate(b: &mut Battle, mine: &[UnitId], theirs: &[UnitId]) -> (HashMap<UnitId, State5>, HashMap<UnitId, State5>) {
    let mut units: Vec<Unit> = Vec::new();
    for m in mine {
        units.push(Unit::new(b, *m, false, None));
    }
    for m in theirs {
        units.push(Unit::new(b, *m, false, None));
    }
    let asking: Vec<usize> = (0..mine.len()).collect();
    let enemy: Vec<usize> = (mine.len()..mine.len() + theirs.len()).collect();
    let mut objectives: HashMap<usize, Objective> = HashMap::new();
    for _ in 0..b.cfg.i("LEGATE_ITERATIONS").max(0) {
        half_round(b, &mut units, &enemy, &asking, &mut objectives, &asking);
        if enemy.iter().all(|u| units[*u].locked) {
            break;
        }
        half_round(b, &mut units, &asking, &enemy, &mut objectives, &asking);
    }
    let ends = |side: &[usize], units: &[Unit]| -> HashMap<UnitId, State5> { side.iter().map(|u| (units[*u].id, units[*u].best.as_ref().map(|x| x.1.clone()).unwrap_or_else(|| units[*u].state.clone()))).collect() };
    (ends(&enemy, &units), ends(&asking, &units))
}

// =============================================================================================================
// using it
// =============================================================================================================
fn estimate_for(b: &Battle, team: &str, foe: UnitId) -> Option<State5> {
    b.legate.plans.get(team).and_then(|p| p.get(&foe)).cloned()
}

/// Where the mover should take this foe to be: its real spot if it has moved, else Legate's estimate, else where it stands.
pub fn foe_state(b: &Battle, team: &str, foe: UnitId) -> State5 {
    if b.units[foe].moved_this_turn {
        return real_state(b, foe);
    }
    estimate_for(b, team, foe).unwrap_or_else(|| hold(b, foe))
}

pub fn active_for(b: &mut Battle, mover: UnitId) -> bool {
    let team = b.units[mover].team.clone().unwrap_or_default();
    b.cfg.b("LEGATE") && b.units[mover].bot == "gladiator" && b.legate.plans.contains_key(&team) && crate::forces::enemies_of(b, mover).len() >= 2
}

/// The enemy this Gladiator plans against: the one expected to score highest against it, among the enemies yet to move.
pub fn foe_for(b: &mut Battle, mover: UnitId) -> Option<UnitId> {
    if !active_for(b, mover) || b.units[mover].hex.is_none() {
        return None;
    }
    check_switches(b);
    let foes: Vec<UnitId> = crate::forces::enemies_of(b, mover).into_iter().filter(|f| b.units[*f].hex.is_some()).collect();
    let waiting: Vec<UnitId> = foes.iter().copied().filter(|f| !b.units[*f].moved_this_turn).collect();
    let pool = if waiting.is_empty() { foes } else { waiting };
    if pool.is_empty() {
        return None;
    }
    let team = b.units[mover].team.clone().unwrap_or_default();
    let (hx, hy, hf) = hex_geometry::state_from_label(b.units[mover].hex.as_deref().unwrap(), &b.units[mover].facing).unwrap();
    let hold_opt = crate::move_options::prepare_options(b, mover, &[(hx, hy, hf, 0, "Stand Still", 0)]);
    let side = Side::new(b, mover, true);
    let mut best: Option<((f64, i64, usize), UnitId)> = None;
    for (index, f) in pool.iter().enumerate() {
        let st = foe_state(b, &team, *f);
        let threat = threat_of(b, mover, *f, &st, &hold_opt, &side);
        let dist = crate::forces::distance(b, mover, *f).unwrap_or(0);
        let rank = (-threat, dist, index);
        if best.as_ref().map_or(true, |(r, _)| rank.partial_cmp(r) == Some(std::cmp::Ordering::Less)) {
            best = Some((rank, *f));
        }
    }
    best.map(|(_, f)| f)
}

/// The foe's picker score against the mover standing still.
fn threat_of(b: &mut Battle, mover: UnitId, foe: UnitId, state: &State5, hold: &[Opt], side: &Side) -> f64 {
    let mut ev = MoveEvaluator::new(b, mover, foe);
    let got = ev.evaluate(b, &state.0, state.1, state.2, state.3, state.4, hold, true);
    let Some(cand) = got.first() else { return 0.0 };
    let foe_side = Side::new(b, foe, true);
    let dealt = cand.received * side.exp(cand.side_on_mover);
    let taken = cand.dealt * foe_side.exp(cand.side_on_defender);
    let (mine, theirs) = pair_rates(b, foe, mover);
    let floor = b.cfg.f("MOVEMENT_LIFETIME_FUTURE_FLOOR");
    if b.cfg.s("MOVEMENT_OBJECTIVE") == "lifetime" {
        let left = move_select::effective_hp(b, foe) - taken;
        return dealt + if left > 0.0 { left / theirs.max(floor) * mine.max(floor) } else { 0.0 };
    }
    dealt / (taken + b.cfg.f("MOVEMENT_RATIO_EPSILON"))
}

// =============================================================================================================
// Extras: what a Gladiator's move scoring adds for the enemies other than its foe
// =============================================================================================================
pub struct Extras {
    mover: UnitId,
    primary: UnitId,
    others: Vec<UnitId>,
    entries: Vec<(UnitId, State5, Side)>,
    unit: Unit,
    pub count: usize,
    tier: Tier,
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Tier {
    Hot,
    Mid,
    Cool,
}

impl Extras {
    /// Legate's view for this mover's pick, or None - a duel, a Princess unit, Legate off, or no plan this turn.
    pub fn for_pick(b: &mut Battle, mover: UnitId, other: UnitId, me: &Side) -> Option<Extras> {
        if !b.cfg.b("LEGATE") || b.units[mover].bot != "gladiator" || b.units[other].hex.is_none() {
            return None;
        }
        if !active_for(b, mover) {
            return None;
        }
        check_switches(b);
        let team = b.units[mover].team.clone().unwrap_or_default();
        let mut others = Vec::new();
        for f in crate::forces::enemies_of(b, mover) {
            if f != other && b.units[f].hex.is_some() && can_matter(b, mover, f) {
                others.push(f);
            }
        }
        let mut entries = Vec::new();
        for f in &others {
            let st = foe_state(b, &team, *f);
            let side = Side::new(b, *f, true);
            entries.push((*f, st, side));
        }
        let unit = Unit::new(b, mover, true, Some(me.clone()));
        let count = entries.len();
        if count == 0 {
            return None;
        }
        let tier = if b.cfg.b("TRIAGE") { tier_of(b, mover) } else { Tier::Mid };
        Some(Extras { mover, primary: other, others, entries, unit, count, tier })
    }

    /// The picker score against the primary foe and the others together.
    pub fn objective(&self, b: &mut Battle, primary: UnitId) -> Objective {
        let mut foes = vec![primary];
        foes.extend(self.others.iter().copied());
        objective_for(b, self.mover, &foes)
    }

    /// The mover's dealt / received at state o against its foe, with the other enemies added; returned already multiplied
    /// by the exposure factors (multipliers 1.0).
    pub fn adjust(&mut self, b: &mut Battle, o: &Opt, dealt: f64, received: f64, dealt_mult: f64, received_mult: f64) -> (f64, f64, f64, f64) {
        let mut d = dealt * dealt_mult;
        let mut r = received * received_mult;
        r *= now_share(b, self.primary, self.mover);
        for i in 0..self.entries.len() {
            let (foe, st) = (self.entries[i].0, self.entries[i].1.clone());
            // the mover would take the hex this enemy is estimated to end in: the enemy then ends somewhere else and
            // still shoots - taken from where it stands now
            let st = if st.0 == o.label { hold(b, foe) } else { st };
            let cand = self.unit.rows(b, foe, &st, std::slice::from_ref(o)).get(&key_of(o)).cloned().flatten();
            let Some(cand) = cand else { continue };
            let v = cand.dealt * self.entries[i].2.exp(cand.side_on_defender);
            if v > d {
                d = v;
            }
            let taken = cand.received * self.unit.side.exp(cand.side_on_mover);
            r += taken * now_share(b, foe, self.mover);
        }
        match self.tier {
            Tier::Hot => r *= b.cfg.f("TRIAGE_HOT_RECEIVED"),
            Tier::Cool => d *= b.cfg.f("TRIAGE_COOL_DEALT"),
            Tier::Mid => {}
        }
        (d, r, 1.0, 1.0)
    }
}

// =============================================================================================================
// triage tiers (peril / toughness)
// =============================================================================================================
/// range_profile with its four to-hit classes: T[c][d].
fn profile_table(b: &mut Battle, attacker: UnitId, target: UnitId) -> Option<Vec<Vec<f64>>> {
    // keyed by whether the attacker has moved: the Python's field cache is, and a unit that stood up in its move has a
    // different profile afterwards
    let moved = b.units[attacker].moved_this_turn;
    if let Some(t) = b.legate.profiles.get(&(attacker, target, moved)) {
        return t.clone();
    }
    let base = move_select::range_profile(b, attacker, target, 0);
    let table = if base.is_empty() {
        None
    } else {
        let reach = base.len();
        let mut t = vec![vec![0.0; reach + 1]; 4];
        t[0][..reach].copy_from_slice(&base);
        for c in 1..4 {
            let prof = move_select::range_profile(b, attacker, target, c as i64);
            t[c][..prof.len()].copy_from_slice(&prof);
        }
        Some(t)
    };
    b.legate.profiles.insert((attacker, target, moved), table.clone());
    table
}

fn footprint(b: &mut Battle, attacker: UnitId) -> Vec<(i64, i64)> {
    if b.units[attacker].hex.is_some() && (b.units[attacker].shutdown || is_immobile(&b.units[attacker])) {
        return vec![xy(b.units[attacker].hex.as_deref().unwrap())];
    }
    let edge = if b.units[attacker].hex.is_none() { b.units[attacker].home_edge.clone() } else { None };
    let mut notes = crate::move_options::PathNotes::default();
    let blocked = b.units[attacker].blocked_hex.clone();
    let states = crate::move_options::movement_options(b, attacker, None, edge.as_deref(), true, &mut notes);
    b.units[attacker].blocked_hex = blocked;
    let mut seen = HashSet::new();
    states.into_iter().map(|s| (s.0, s.1)).filter(|p| seen.insert(*p)).collect()
}

fn vision_at(b: &mut Battle, a: (i64, i64), t: (i64, i64)) -> Option<(bool, i64, i64)> {
    if let Some(v) = b.legate.vision.get(&(a, t)) {
        return *v;
    }
    let h = crate::attack_resolution::standing();
    let v = match crate::move_eval::pair_info(b, a, t, h, h) {
        Some(p) => Some((p.los.los, if p.los.los { p.los.modifier.clamp(0, 3) } else { 0 }, p.distance)),
        None => Some((false, 0, hex_distance(a, t))),
    };
    b.legate.vision.insert((a, t), v);
    v
}

/// field_for(attacker, target).at(hex, "peak"): the most damage the attacker could bring to `hex` from any spot it can reach.
fn peak_at(b: &mut Battle, attacker: UnitId, target: UnitId, hex: (i64, i64)) -> f64 {
    let moved = b.units[attacker].moved_this_turn;
    let key = (attacker, target, moved, hex);
    if let Some(v) = b.legate.peaks.get(&key) {
        return *v;
    }
    let value = (|| {
        let table = profile_table(b, attacker, target)?;
        if std::env::var("BT_DUMP_TIER").is_ok() && b.units[attacker].side_name.as_deref() == Some("Blue 4") && b.units[target].side_name.as_deref() == Some("Red 3") {
            eprintln!("PROF {:?} {:?} {:?}", b.units[attacker].hex, table[0].iter().map(|x| (x * 1000.0).round() / 1000.0).collect::<Vec<_>>(), table[1].iter().map(|x| (x * 1000.0).round() / 1000.0).collect::<Vec<_>>());
        }
        let spots: Vec<(i64, i64)> = if moved && b.units[attacker].hex.is_some() {
            vec![xy(b.units[attacker].hex.as_deref().unwrap())]
        } else {
            if !b.legate.footprints.contains_key(&attacker) {
                let f = footprint(b, attacker);
                b.legate.footprints.insert(attacker, f);
            }
            b.legate.footprints[&attacker].clone()
        };
        // spots off the board are skipped; a hex that is not on the board has no field
        let on_board = |bb: &Battle, p: &(i64, i64)| hex_geometry::hex_label(p.0, p.1).ok().is_some_and(|l| bb.board.hexes.contains_key(&l));
        if !on_board(b, &hex) {
            return Some(0.0);
        }
        let last = table[0].len() - 1;
        let mut best: Option<f64> = None;
        for s in spots {
            if !on_board(b, &s) {
                continue;
            }
            let (seen, m, d) = vision_at(b, s, hex)?;
            let dmg = if seen { table[m as usize][(d as usize).min(last)] } else { 0.0 };
            if best.map_or(true, |x| dmg > x) {
                best = Some(dmg);
            }
        }
        best
    })()
    .unwrap_or(0.0);
    if std::env::var("BT_DUMP_TIER").is_ok() {
        eprintln!("PEAK {} {} {} {:?} {} {}", b.units[attacker].side_name.clone().unwrap_or_default(), b.units[target].side_name.clone().unwrap_or_default(), moved, hex, value, b.legate.footprints.get(&attacker).map_or(0, |f| f.len()));
    }
    b.legate.peaks.insert(key, value);
    value
}

/// HOT, MID or COOL for the mover among its team.
pub fn tier_of(b: &mut Battle, mover: UnitId) -> Tier {
    if std::env::var("BT_DUMP_TIER").is_ok() {
        eprintln!("TIER_FOR {} {}", b.units[mover].side_name.clone().unwrap_or_default(), b.units[mover].turn_number);
    }
    let team_name = b.units[mover].team.clone();
    let standing = crate::forces::standing(b);
    let team: Vec<UnitId> = standing.iter().copied().filter(|u| b.units[*u].team == team_name).collect();
    if team.len() < 3 || b.units[mover].hex.is_none() {
        return Tier::Mid;
    }
    let enemies = crate::forces::enemies_of(b, mover);
    if enemies.is_empty() {
        return Tier::Mid;
    }
    let on_board: Vec<UnitId> = team.iter().copied().filter(|u| b.units[*u].hex.is_some()).collect();
    if on_board.len() < 3 {
        return Tier::Mid;
    }
    let mut ratios: HashMap<UnitId, f64> = HashMap::new();
    for u in &on_board {
        let hxy = xy(b.units[*u].hex.as_deref().unwrap());
        let mut peril_here = 0.0;
        for e in &enemies {
            peril_here += peak_at(b, *e, *u, hxy);
        }
        ratios.insert(*u, peril_here / move_select::effective_hp(b, *u).max(1.0));
        if std::env::var("BT_DUMP_TIER").is_ok() {
            eprintln!("RATIO {} {:?}", b.units[*u].side_name.clone().unwrap_or_default(), ratios[u]);
        }
    }
    let mut order = on_board.clone();
    order.sort_by(|a, c| (-ratios[a]).partial_cmp(&(-ratios[c])).unwrap());
    let k = ((b.cfg.f("TRIAGE_FRACTION") * order.len() as f64).ceil() as usize).max(1);
    let rank = order.iter().position(|u| *u == mover).unwrap();
    if rank < k {
        Tier::Hot
    } else if rank >= order.len() - k {
        Tier::Cool
    } else {
        Tier::Mid
    }
}
