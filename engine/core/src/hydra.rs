//! Hydra, the third bot (INTEGRATION__HYDRA.md is the plan: read it first). One planner for a whole team; every
//! decision is scored in one currency, the PRICE of a point of damage, and prices come from a small forecast of how the
//! battle ends. The blocks below carry the plan's names: LEDGER -> FORECAST -> PRICES, then MOVER and FIRE PLAN, which
//! ask the engine (the EXCHANGE ORACLE, `MoveEvaluator` / `dry_declare_as`) what damage flows and multiply by prices.
//!
//! Rust only: there is no Python version of this bot and no exact-match test. It is judged by results (plan, Section 4).
use crate::battle::{Battle, UnitId};
use crate::fasthash::HashMap;
use crate::hex_geometry;
use crate::los::hex_distance;
use crate::mech_state::{compute_walk_mp, is_immobile};
use crate::move_eval::MoveEvaluator;
use crate::move_options::{self, Opt};
use crate::move_select::{self, Side};
use crate::ranged_combat::Pick;

/// Hydra's memory for one battle (`Battle::hydra`).
#[derive(Default)]
pub struct HydraState {
    /// the most `guns` each unit has shown this battle (a shut-down unit keeps part of its worth)
    best_guns: HashMap<UnitId, f64>,
    /// this Weapon Attack Phase's plan, per team: attacker -> target (emptied when the phase starts)
    fire: HashMap<String, HashMap<UnitId, Option<UnitId>>>,
}

impl HydraState {
    /// The Weapon Attack Phase begins: last turn's fire plans are void.
    pub fn start_fire_phase(&mut self) {
        self.fire.clear();
    }
}

// =============================================================================================================
// LEDGER: what every unit is worth right now
// =============================================================================================================
#[derive(Clone, Copy, Debug)]
pub struct Entry {
    pub unit: UnitId,
    /// damage it can still absorb
    pub life: f64,
    /// damage a turn it puts out when it has a shot
    pub guns: f64,
}

/// A unit that cannot fire this turn (shut down, no enemy to measure against) still counts for this much of its best.
const DORMANT_GUNS: f64 = 0.5;
/// No unit is worth less than this in guns (a disarmed 'Mech still kicks).
const MIN_GUNS: f64 = 1.0;

/// (my team's entries, the enemy's entries): every unit still fighting, on or off the board.
pub fn ledger(b: &mut Battle, me: UnitId) -> (Vec<Entry>, Vec<Entry>) {
    let team = b.units[me].team.clone();
    let alive = crate::forces::standing(b);
    let per_turn = b.cfg.f("MOVEMENT_LIFETIME_INITIATIVE");
    let (mut mine, mut theirs) = (Vec::new(), Vec::new());
    for &u in &alive {
        let foe = alive.iter().copied().find(|v| b.units[*v].team != b.units[u].team);
        let mut guns = match foe {
            Some(f) => move_select::future_damage(b, u, f) / if per_turn > 0.0 { per_turn } else { 1.0 },
            None => 0.0,
        };
        let best = b.hydra.best_guns.entry(u).or_insert(0.0);
        if guns > *best {
            *best = guns;
        }
        guns = guns.max(DORMANT_GUNS * *best).max(MIN_GUNS);
        let e = Entry { unit: u, life: crate::orchestrator::effective_hp(b, u).max(1.0), guns };
        if b.units[u].team == team { mine.push(e) } else { theirs.push(e) }
    }
    (mine, theirs)
}

// =============================================================================================================
// FORECAST: how the battle ends from here, as pure attrition
// =============================================================================================================
/// The share of a side's `guns` that lands in one forecast step.
const STEP_FIRE: f64 = 0.5;
const MAX_STEPS: usize = 60;

/// One side's fire for a step, poured onto the other side's units in kill order (most guns removed per point of damage
/// first); what is left over after a kill carries on to the next.
fn pour(fire: f64, targets: &[(f64, f64)], hits: &mut [f64]) {
    let mut order: Vec<usize> = (0..targets.len()).filter(|i| targets[*i].0 > 0.0).collect();
    order.sort_by(|x, y| (targets[*y].1 / targets[*y].0).partial_cmp(&(targets[*x].1 / targets[*x].0)).unwrap().then(x.cmp(y)));
    let mut left = fire;
    for i in order {
        if left <= 0.0 {
            break;
        }
        let take = left.min(targets[i].0);
        hits[i] += take;
        left -= take;
    }
}

/// The margin: what side A has left minus what side B has left once one of them is gone (each unit counted as guns x
/// life), as a share of what both began with. Each entry is (life, guns).
pub fn forecast(a: &[(f64, f64)], b: &[(f64, f64)]) -> f64 {
    let (mut a, mut b) = (a.to_vec(), b.to_vec());
    let worth = |s: &[(f64, f64)]| s.iter().map(|(l, g)| l.max(0.0) * g).sum::<f64>();
    let start = worth(&a) + worth(&b);
    if start <= 0.0 {
        return 0.0;
    }
    for _ in 0..MAX_STEPS {
        let fire_a: f64 = a.iter().filter(|u| u.0 > 0.0).map(|u| u.1).sum::<f64>() * STEP_FIRE;
        let fire_b: f64 = b.iter().filter(|u| u.0 > 0.0).map(|u| u.1).sum::<f64>() * STEP_FIRE;
        if fire_a <= 0.0 || fire_b <= 0.0 {
            break;
        }
        let (mut hits_b, mut hits_a) = (vec![0.0; b.len()], vec![0.0; a.len()]);
        pour(fire_a, &b, &mut hits_b);
        pour(fire_b, &a, &mut hits_a);
        for (u, h) in b.iter_mut().zip(&hits_b) {
            u.0 -= h;
        }
        for (u, h) in a.iter_mut().zip(&hits_a) {
            u.0 -= h;
        }
    }
    (worth(&a) - worth(&b)) / start
}

// =============================================================================================================
// PRICES: what one point of damage on each unit is worth
// =============================================================================================================
/// unit -> price. For an enemy: how far a point of damage on it moves the margin my way. For a friend: how far a point
/// of damage on it moves the margin against me.
pub fn prices(mine: &[Entry], theirs: &[Entry]) -> HashMap<UnitId, f64> {
    let a: Vec<(f64, f64)> = mine.iter().map(|e| (e.life, e.guns)).collect();
    let b: Vec<(f64, f64)> = theirs.iter().map(|e| (e.life, e.guns)).collect();
    let base = forecast(&a, &b);
    let total: f64 = a.iter().chain(b.iter()).map(|(l, g)| l * g).sum();
    let mut out = HashMap::default();
    for (side, entries) in [(0, mine), (1, theirs)] {
        for (i, e) in entries.iter().enumerate() {
            let bite = e.life.min((0.15 * e.life).max(10.0));
            let (mut a2, mut b2) = (a.clone(), b.clone());
            if side == 0 { a2[i].0 -= bite } else { b2[i].0 -= bite }
            let moved = (forecast(&a2, &b2) - base).abs() / bite;
            // never free: at the least, the unit's own guns x the damage, on the margin's scale
            let floor = 0.25 * e.guns / total.max(1.0);
            out.insert(e.unit, moved.max(floor));
        }
    }
    // scaled so the mean price is 1: scores then read as points of damage
    let mean = out.values().sum::<f64>() / out.len().max(1) as f64;
    if mean > 0.0 {
        for v in out.values_mut() {
            *v /= mean;
        }
    }
    out
}

// =============================================================================================================
// MOVER: where one unit goes
// =============================================================================================================
/// How much of an enemy's attention a friend at `dist` hexes draws, next to a unit it has a clear shot at (the attention
/// share's rough alternative; replaceable by the oracle when the cost allows).
fn range_factor(dist: i64) -> f64 {
    if dist <= 9 { 1.0 } else if dist <= 15 { 0.6 } else if dist <= 21 { 0.3 } else { 0.0 }
}

/// THE REPLY's budget: about this many "what would it answer" searches per move, shared out over the enemies weighed, and
/// never more than REPLY_MAX spots re-scored. Under 2 spots the reply is skipped (a big battle: the table speaks alone).
const REPLY_BUDGET: usize = 32;
const REPLY_MAX: usize = 32;

fn xy(b: &Battle, u: UnitId) -> Option<(i64, i64)> {
    b.units[u].hex.as_deref().and_then(|h| hex_geometry::parse_hex_label(h).ok())
}

/// The EXCHANGE ORACLE for one enemy: per prepared option, (damage I deal it, damage it deals me). An enemy that has
/// moved is taken where it stands (fixed pose); one that has not is a ghost: in its hex, having walked, turned to face
/// each option.
fn exchange(b: &mut Battle, mover: UnitId, enemy: UnitId, prepared: &[Opt], index: &HashMap<(String, &'static str, &'static str, i64), usize>) -> Vec<(f64, f64)> {
    let mut out = vec![(0.0, 0.0); prepared.len()];
    let label = b.units[enemy].hex.clone().unwrap();
    let e_xy = hex_geometry::parse_hex_label(&label).unwrap();
    let mut ev = MoveEvaluator::new(b, mover, enemy);
    let fixed = b.units[enemy].moved_this_turn || is_immobile(&b.units[enemy]);
    let mut put = |cands: Vec<crate::move_eval::Candidate>| {
        for c in cands {
            if let Some(&i) = index.get(&c.key4()) {
                out[i] = (c.dealt, c.received);
            }
        }
    };
    if fixed {
        let (facing, fc, mode, mp) = (b.units[enemy].facing.clone(), b.units[enemy].move_fc, b.units[enemy].move_mode.clone(), b.units[enemy].mp_spent);
        put(ev.evaluate(b, &label, &facing, fc, &mode, mp, prepared, true));
    } else {
        let walked = compute_walk_mp(&b.units[enemy]).max(0);
        let mode = if walked > 0 { "Walk" } else { "Stand Still" };
        let mut groups: Vec<Vec<Opt>> = vec![Vec::new(); 6];
        for o in prepared {
            let f = if o.hex_xy() == e_xy { 0 } else { crate::combat::direction_facing(e_xy, o.hex_xy()).unwrap_or(0) };
            groups[(f.rem_euclid(6)) as usize].push(o.clone());
        }
        for (f, group) in groups.iter().enumerate() {
            if group.is_empty() {
                continue;
            }
            let compass = hex_geometry::facing_to_compass(f as i64).unwrap();
            put(ev.evaluate(b, &label, compass, walked, mode, walked, group, true));
        }
    }
    out
}

/// The movement pick for a Hydra unit and the note the log prints. `other` is the foe the engine named (used only where
/// the engine's own helpers want one).
pub fn choose_movement(b: &mut Battle, mover: UnitId, other: UnitId, moves_first: bool, standup_mp: Option<i64>, entry_edge: Option<&[String]>) -> (Option<Pick>, String) {
    let enemies: Vec<UnitId> = crate::forces::enemies_of(b, mover).into_iter().filter(|e| b.units[*e].hex.is_some()).collect();
    if enemies.is_empty() {
        // nobody to weigh yet (the enemy has not entered): the engine's march toward its edge
        let mut ties = move_select::Ties { recorded: None, missed: false };
        return move_select::choose(b, mover, other, moves_first, standup_mp, entry_edge, &mut ties);
    }
    let mut me = Side::new(b, mover, standup_mp.is_none());
    let exclude = move_options::occupied_hexes(b, mover, other);
    let (options, notes) = move_options::reduced_options(b, mover, &exclude, standup_mp, entry_edge);
    me.notes = notes;
    let prepared = move_options::prepare_options(b, mover, &options);
    if prepared.is_empty() {
        return (None, "no reachable spot".into());
    }
    let mut index: HashMap<(String, &'static str, &'static str, i64), usize> = HashMap::default();
    for (i, o) in prepared.iter().enumerate() {
        index.insert((o.label.clone(), o.facing_compass, o.mode, o.fc), i);
    }

    let (mine, theirs) = ledger(b, mover);
    let price = prices(&mine, &theirs);
    let my_price = price.get(&mover).copied().unwrap_or(1.0);
    let guns: HashMap<UnitId, f64> = theirs.iter().map(|e| (e.unit, e.guns)).collect();

    // only the enemies that can matter this turn are asked about; never none
    let mut relevant: Vec<UnitId> = enemies.iter().copied().filter(|e| b.units[mover].hex.is_none() || crate::legate::can_matter(b, mover, *e)).collect();
    if relevant.is_empty() {
        let near = enemies.iter().copied().min_by_key(|e| match (xy(b, mover), xy(b, *e)) {
            (Some(m), Some(t)) => hex_distance(m, t),
            _ => 0,
        });
        relevant.extend(near);
    }

    let n = prepared.len();
    let friends: Vec<UnitId> = mine.iter().map(|e| e.unit).filter(|u| *u != mover && b.units[*u].hex.is_some()).collect();
    // one exchange table per enemy weighed: (enemy, its price, what else it could shoot at, per option (dealt, received))
    let mut tables: Vec<(UnitId, f64, f64, Vec<(f64, f64)>)> = Vec::new();
    for &e in &relevant {
        let table = exchange(b, mover, e, &prepared, &index);
        let p_e = price.get(&e).copied().unwrap_or(1.0);
        // what else this enemy could be shooting at: its best friend-target, roughly
        let e_xy = xy(b, e).unwrap();
        let mut elsewhere = 0.0f64;
        for &f in &friends {
            let v = price.get(&f).copied().unwrap_or(1.0) * guns.get(&e).copied().unwrap_or(0.0) * range_factor(hex_distance(e_xy, xy(b, f).unwrap()));
            elsewhere = elsewhere.max(v);
        }
        tables.push((e, p_e, elsewhere, table));
    }
    // (gain, the enemy it is on, cost) of option i; `instead` swaps one enemy's line of the table for a modeled reply
    let weigh = |i: usize, instead: Option<(UnitId, (f64, f64))>| -> (f64, Option<UnitId>, f64) {
        let (mut gain, mut on, mut cost) = (0.0f64, None, 0.0f64);
        for (e, p_e, elsewhere, table) in &tables {
            let (dealt, received) = match instead {
                Some((r, x)) if r == *e => x,
                _ => table[i],
            };
            let g = p_e * dealt;
            if g > gain {
                gain = g;
                on = Some(*e);
            }
            let hurt = my_price * received;
            if hurt > 0.0 {
                cost += hurt * hurt / (hurt + elsewhere);
            }
        }
        (gain, on, cost)
    };
    let risks: Vec<f64> = prepared.iter().map(|o| my_price * me.psr_for_opt(b, o)).collect();
    // THE SCORE of a spot: what it does to my team's rate of exchange over a typical turn,
    //     (d0 + gain) / (r0 + cost + risk)
    // d0 / r0 = what my whole team (this unit included) deals / takes in a typical turn, priced. In a big force one
    // unit's trade is small next to d0 and r0, and the score asks "is this trade better than the team's average?". In a
    // duel d0 and r0 are this unit's own typical turn, which keeps the score from chasing a tiny free shot over a solid
    // trade. A side that waits scores d0 / r0, so stalling never beats a fair trade.
    let mean = |side: &[Entry]| side.iter().map(|e| price.get(&e.unit).copied().unwrap_or(1.0)).sum::<f64>() / side.len().max(1) as f64;
    let d0 = STEP_FIRE * mean(&theirs) * mine.iter().map(|e| e.guns).sum::<f64>();
    let r0 = STEP_FIRE * mean(&mine) * theirs.iter().map(|e| e.guns).sum::<f64>();
    let rate = |g: f64, c: f64, risk: f64| (d0 + g) / (r0 + c + risk).max(1e-9);
    let mut scored: Vec<(f64, usize)> = Vec::new();
    let mut cost = vec![0.0f64; n];
    for i in 0..n {
        let (g, _, c) = weigh(i, None);
        cost[i] = c;
        if g > 0.0 {
            scored.push((rate(g, c, risks[i]), i));
        }
    }
    scored.sort_by(|x, y| y.0.partial_cmp(&x.0).unwrap().then(x.1.cmp(&y.1)));

    // THE REPLY: an enemy that has not moved will answer this move. For the best few spots (one per hex), the unmoved
    // enemy that weighs most on them (the rival) is given its best answer, and the spots are scored again against it.
    let mut reply_note = String::new();
    let mut best: Option<(f64, usize, Option<(UnitId, (f64, f64))>)> = scored.first().map(|(s, i)| (*s, *i, None));
    let unmoved: Vec<UnitId> = relevant.iter().copied().filter(|e| !(b.units[*e].moved_this_turn || is_immobile(&b.units[*e]))).collect();
    let depth = (REPLY_BUDGET / relevant.len().max(1)).min(REPLY_MAX);
    if !unmoved.is_empty() && depth >= 2 && !scored.is_empty() {
        let mut short: Vec<usize> = Vec::new();
        for (_, i) in &scored {
            if !short.iter().any(|j| prepared[*j].hex_xy() == prepared[*i].hex_xy()) {
                short.push(*i);
                if short.len() == depth {
                    break;
                }
            }
        }
        let weight_of = |e: UnitId| -> f64 {
            let (_, p_e, _, table) = tables.iter().find(|t| t.0 == e).unwrap();
            short.iter().map(|i| p_e * table[*i].0 + my_price * table[*i].1).sum()
        };
        let rival = unmoved.iter().copied().max_by(|x, y| weight_of(*x).partial_cmp(&weight_of(*y)).unwrap().then(y.cmp(x))).unwrap();
        let p_r = price.get(&rival).copied().unwrap_or(1.0);
        let mut them = Side::new(b, rival, true);
        let replies = move_select::opponent_options(b, rival, &mut them);
        let mut ev2 = MoveEvaluator::new(b, rival, mover);
        let prepared2 = ev2.prepare(b, &replies);
        best = None;
        for &i in &short {
            let o = &prepared[i];
            // the rival's answer: the most (damage on me at my price - damage on it at its price), seen from its seat
            let mut answer: Option<(f64, (f64, f64))> = None;
            for c in ev2.evaluate(b, &o.label, o.facing_compass, o.fc, o.mode, o.mp_spent, &prepared2, true) {
                let v = my_price * c.dealt - p_r * c.received;
                if answer.map_or(true, |(a, _)| v > a) {
                    answer = Some((v, (c.received, c.dealt)));
                }
            }
            let instead = Some((rival, answer.map_or((0.0, 0.0), |(_, x)| x)));
            let (g, _, c) = weigh(i, instead);
            let s = rate(g, c, risks[i]);
            if best.map_or(true, |(bs, _, _)| s > bs) {
                best = Some((s, i, instead));
            }
        }
        reply_note = format!("; {} spots re-scored against {}'s best answer", short.len(), b.units[rival].side_name.clone().unwrap_or_default());
    }
    if let Some((score, i, instead)) = best {
        let o = &prepared[i];
        let (g, on, c) = weigh(i, instead);
        let on = on.map_or("nobody".to_string(), |e| b.units[e].side_name.clone().unwrap_or_default());
        let note = format!("Hydra: rate {:.3} = (team {:.1} + gain {:.2} on {}) / (team {:.1} + cost {:.2} + risk {:.2}) ({} of {} enemies weighed, {} spots{})", score, d0, g, on, r0, c, risks[i], relevant.len(), enemies.len(), n, reply_note);
        return (Some(o.pick()), note);
    }

    // no spot deals damage: close on the highest-priced enemy among the nearest, by the least costly route
    let m_xy = xy(b, mover);
    let goal = enemies
        .iter()
        .copied()
        .max_by(|x, y| {
            let key = |e: UnitId| price.get(&e).copied().unwrap_or(1.0) / (1.0 + m_xy.map_or(0, |m| hex_distance(m, xy(b, e).unwrap())) as f64);
            key(*x).partial_cmp(&key(*y)).unwrap().then(y.cmp(x))
        })
        .unwrap();
    let goal_xy = xy(b, goal).unwrap();
    let goal_name = b.units[goal].side_name.clone().unwrap_or_default();
    if let Some(o) = move_select::closing_fallback(b, mover, goal, &me, &prepared, goal_xy, &|_| 0.0, None) {
        return (Some(o.pick()), format!("Hydra: no spot deals damage - closes on {}", goal_name));
    }
    let mut pick: Option<(f64, usize)> = None;
    for i in 0..n {
        let o = &prepared[i];
        let v = -(hex_distance(o.hex_xy(), goal_xy) as f64) - cost[i] - my_price * me.psr_for_opt(b, o) + 0.01 * o.tmm as f64;
        if pick.map_or(true, |(s, _)| v > s) {
            pick = Some((v, i));
        }
    }
    let o = &prepared[pick.unwrap().1];
    (Some(o.pick()), format!("Hydra: no spot deals damage - nearest safe spot to {}", goal_name))
}

// =============================================================================================================
// FIRE PLAN: who shoots whom, for the whole team at once
// =============================================================================================================
/// Damage past this multiple of a target's remaining life counts for nothing (dice are dice: aim a little over).
const OVERKILL: f64 = 1.5;

fn plan_fire(b: &mut Battle, team: &str) -> HashMap<UnitId, Option<UnitId>> {
    let shooters: Vec<UnitId> = crate::forces::standing(b).into_iter().filter(|u| b.units[*u].team.as_deref() == Some(team) && b.units[*u].bot == "hydra" && b.units[*u].hex.is_some()).collect();
    let mut plan: HashMap<UnitId, Option<UnitId>> = HashMap::default();
    let Some(&first) = shooters.first() else { return plan };
    let (mine, theirs) = ledger(b, first);
    let price = prices(&mine, &theirs);
    let mut room: HashMap<UnitId, f64> = theirs.iter().map(|e| (e.unit, OVERKILL * e.life)).collect();
    // the oracle: each shooter's expected damage on each enemy it can hit
    let mut shots: Vec<(UnitId, Vec<(UnitId, f64)>)> = Vec::new();
    for &u in &shooters {
        let mut row = Vec::new();
        for e in crate::bot_targets::candidates(b, u) {
            if let Some((_, dmg, _)) = crate::bot_targets::dry_declare_as(b, u, e, false) {
                if dmg > 0.0 {
                    row.push((e, dmg));
                }
            }
        }
        shots.push((u, row));
    }
    // the biggest priced bite first; each takes room off its target, so spare guns move on
    let mut open: Vec<usize> = (0..shots.len()).collect();
    while !open.is_empty() {
        let mut best: Option<(f64, usize, UnitId, f64)> = None;
        for &s in &open {
            for &(e, dmg) in &shots[s].1 {
                let counted = dmg.min(room.get(&e).copied().unwrap_or(0.0).max(0.0));
                let v = price.get(&e).copied().unwrap_or(1.0) * (counted + 0.01 * dmg);
                if best.map_or(true, |(bv, _, _, _)| v > bv) {
                    best = Some((v, s, e, dmg));
                }
            }
        }
        match best {
            Some((_, s, e, dmg)) => {
                plan.insert(shots[s].0, Some(e));
                *room.entry(e).or_insert(0.0) -= dmg;
                open.retain(|x| *x != s);
            }
            None => {
                // nothing to hit: the engine's default (the nearest enemy), so the phase's bookkeeping still runs
                for &s in &open {
                    let u = shots[s].0;
                    let t = crate::forces::choose_target(b, u, true, false);
                    plan.insert(u, t);
                }
                open.clear();
            }
        }
    }
    plan
}

/// The enemy a Hydra unit fires at this phase: its line of the team's plan (made at the first ask of the phase).
pub fn choose_target(b: &mut Battle, attacker: UnitId) -> Option<UnitId> {
    let team = b.units[attacker].team.clone().unwrap_or_default();
    if !b.hydra.fire.contains_key(&team) {
        let plan = plan_fire(b, &team);
        b.hydra.fire.insert(team.clone(), plan);
    }
    match b.hydra.fire[&team].get(&attacker) {
        Some(t) => *t,
        None => crate::forces::choose_target(b, attacker, true, false),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn forecast_is_even_for_equal_sides_and_favors_the_stronger() {
        let a = [(100.0, 20.0), (100.0, 20.0)];
        assert!(forecast(&a, &a).abs() < 1e-9);
        let weak = [(100.0, 20.0)];
        assert!(forecast(&a, &weak) > 0.0);
        assert!(forecast(&weak, &a) < 0.0);
    }

    #[test]
    fn the_nearly_dead_big_gun_is_priced_highest() {
        let e = |unit, life, guns| Entry { unit, life, guns };
        let mine = [e(0, 100.0, 20.0), e(1, 100.0, 20.0)];
        let theirs = [e(2, 100.0, 20.0), e(3, 20.0, 30.0)];
        let p = prices(&mine, &theirs);
        assert!(p[&3] > p[&2], "{:?}", p);
    }
}
