// Translated from INTEGRATION__forces.py (session 22). Part 1: the roster lookups the engine rules need; the turn-order
// and target-choice parts follow with the orchestrator.
use crate::battle::{Battle, UnitId};

/// The standing unit in hex `label`, other than those in `exclude`.
pub fn unit_in_hex(b: &mut Battle, label: &str, exclude: &[UnitId]) -> Option<UnitId> {
    for u in 0..b.units.len() {
        if b.units[u].hex.as_deref() == Some(label) && !b.is_destroyed(u) && !exclude.contains(&u) {
            return Some(u);
        }
    }
    None
}

use crate::hex_geometry;
use crate::los::hex_distance;
use crate::mech_state::*;

pub fn standing(b: &mut Battle) -> Vec<UnitId> {
    (0..b.units.len()).filter(|u| !b.is_destroyed(*u)).collect()
}

/// Teams in order of first appearance.
pub fn team_names(b: &Battle, units: &[UnitId]) -> Vec<String> {
    let mut seen: Vec<String> = Vec::new();
    for u in units {
        let t = b.units[*u].team.clone().unwrap_or_default();
        if !seen.contains(&t) {
            seen.push(t);
        }
    }
    seen
}

/// Teams with at least one unit left.
pub fn teams_standing(b: &mut Battle) -> Vec<String> {
    let s = standing(b);
    team_names(b, &s)
}

/// Standing units on other teams.
pub fn enemies_of(b: &mut Battle, unit: UnitId) -> Vec<UnitId> {
    let team = b.units[unit].team.clone();
    standing(b).into_iter().filter(|u| b.units[*u].team != team && *u != unit).collect()
}

pub fn hex_xy(b: &Battle, u: UnitId) -> Option<(i64, i64)> {
    b.units[u].hex.as_deref().map(|h| hex_geometry::parse_hex_label(h).unwrap())
}

/// Hexes between two units on the board, None if either is still off it.
pub fn distance(b: &Battle, a: UnitId, c: UnitId) -> Option<i64> {
    Some(hex_distance(hex_xy(b, a)?, hex_xy(b, c)?))
}

/// Hex labels of every OTHER standing unit on the board (a set).
pub fn occupied_labels(b: &mut Battle, unit: UnitId) -> Vec<String> {
    let mut v: Vec<String> = standing(b).into_iter().filter(|u| *u != unit).filter_map(|u| b.units[u].hex.clone()).collect();
    v.sort();
    v.dedup();
    v
}

/// (x, y) of every mobile enemy on the board: no ground step may enter them (a set, sorted).
pub fn blocked_xy(b: &mut Battle, unit: UnitId) -> Vec<(i64, i64)> {
    let mut v: Vec<(i64, i64)> = enemies_of(b, unit).into_iter().filter(|u| b.units[*u].hex.is_some() && !is_immobile(&b.units[*u])).filter_map(|u| hex_xy(b, u)).collect();
    v.sort();
    v.dedup();
    v
}

/// Every team rolls 2D6 for Initiative (p.39); returns the teams LOWEST roll first. Tied teams re-roll among themselves.
/// `rolls`, if given, is filled with each team's last (deciding) roll.
pub fn initiative_order(b: &mut Battle, teams: &[String], mut rolls: Option<&mut crate::fasthash::IndexMap<String, i64>>) -> Vec<String> {
    fn settle(b: &mut Battle, group: &[String], rolls: &mut Option<&mut crate::fasthash::IndexMap<String, i64>>) -> Vec<String> {
        if group.len() == 1 {
            return group.to_vec();
        }
        let mut thrown: Vec<(String, i64)> = Vec::new();
        for t in group {
            let r = b.roll_2d6();
            thrown.push((t.clone(), r));
        }
        if let Some(r) = rolls.as_deref_mut() {
            for (t, v) in &thrown {
                r.insert(t.clone(), *v);
            }
        }
        let mut values: Vec<i64> = thrown.iter().map(|(_, v)| *v).collect();
        values.sort();
        values.dedup();
        let mut ordered: Vec<String> = Vec::new();
        for value in values {
            let tied: Vec<String> = group.iter().filter(|t| thrown.iter().find(|(x, _)| x == *t).unwrap().1 == value).cloned().collect();
            if tied.len() > 1 {
                ordered.extend(settle(b, &tied, rolls));
            } else {
                ordered.extend(tied);
            }
        }
        ordered
    }
    settle(b, teams, &mut rolls)
}

/// Princess's move index: higher goes first; a unit not on the board goes first.
pub fn move_index(b: &mut Battle, unit: UnitId) -> f64 {
    let near: Vec<i64> = enemies_of(b, unit).into_iter().filter_map(|e| distance(b, unit, e)).collect();
    if b.units[unit].hex.is_none() || near.is_empty() {
        return f64::INFINITY;
    }
    let fastest = compute_running_mp(&b.units[unit]).max(compute_jump_mp(&b.units[unit]));
    let m = *near.iter().min().unwrap();
    let total = if fastest == 0 { (m * 2) as f64 } else { m as f64 / fastest as f64 };
    let mut total = total * if b.units[unit].prone { 1.1 } else { 1.0 };
    // T16 step 4 (MegaMek Princess.calculateMoveIndex, PRIORITY_STEALTH): "move stealthy units later" - stealth armor or a Void
    // Signature System switched on cuts the index to a third. Princess / CASPAR only (Gladiator and Hydra keep their order).
    if b.units[unit].is_princess_family() && crate::equipment_systems::active_stealth(&b.units[unit]).iter().any(|k| matches!(*k, "stealth_armor" | "void_signature")) {
        total /= 3.0;
    }
    total
}

pub fn can_select_move(m: &Mech) -> bool {
    !(m.shutdown || all_crew_unconscious(m) || is_immobile(m))
}

pub fn can_select_fire(m: &Mech) -> bool {
    !(m.shutdown || all_crew_unconscious(m))
}

/// Which of a unit list goes next, as `pick(candidates)` returns an index into it.
pub type Pick<'a> = &'a mut dyn FnMut(&mut Battle, &[UnitId]) -> UnitId;

/// The activation sequence (sides alternate, the side that lost Initiative first; unequal numbers p.41), computed one
/// unit at a time from the live units: call `next` repeatedly until it returns None.
#[derive(Clone)]
pub struct Activation {
    teams: Vec<String>,
    eligible: crate::fasthash::IndexMap<String, Vec<UnitId>>,
    idle: crate::fasthash::IndexMap<String, Vec<UnitId>>,
    queue: std::collections::VecDeque<UnitId>,
    round_open: bool,
    can_select: fn(&Mech) -> bool,
    started: bool,
    round_tally: crate::fasthash::IndexMap<String, i64>,
    team_cursor: usize,
    pending_takes: i64,
    pending_team: Option<String>,
}

impl Activation {
    pub fn new(b: &mut Battle, teams_in_order: &[String], can_select: fn(&Mech) -> bool) -> Activation {
        let live = standing(b);
        let mut eligible = crate::fasthash::IndexMap::default();
        let mut idle = crate::fasthash::IndexMap::default();
        for t in teams_in_order {
            eligible.insert(t.clone(), live.iter().copied().filter(|u| b.units[*u].team.as_deref() == Some(t) && can_select(&b.units[*u])).collect::<Vec<_>>());
            idle.insert(t.clone(), live.iter().copied().filter(|u| b.units[*u].team.as_deref() == Some(t) && !can_select(&b.units[*u])).collect::<Vec<_>>());
        }
        Activation { teams: teams_in_order.to_vec(), eligible, idle, queue: Default::default(), round_open: false, can_select, started: false, round_tally: Default::default(), team_cursor: 0, pending_takes: 0, pending_team: None }
    }

    /// The next unit, or None when the phase is over. `pick` chooses among a side's eligible units (default: first).
    pub fn next(&mut self, b: &mut Battle, pick: &mut dyn FnMut(&mut Battle, &[UnitId]) -> UnitId) -> Option<UnitId> {
        let _ = (self.can_select, self.started);
        loop {
            if let Some(u) = self.queue.pop_front() {
                return Some(u);
            }
            if !self.round_open {
                if !self.teams.iter().any(|t| !self.eligible[t].is_empty() || !self.idle[t].is_empty()) {
                    return None;
                }
                self.round_open = true;
                self.started = true;
                // the round's tallies as the round begins
                self.round_tally = self.teams.iter().map(|t| (t.clone(), self.eligible[t].len() as i64)).collect();
                self.team_cursor = 0;
                self.pending_takes = 0;
                self.pending_team = None;
            }
            // within the round: for each team in order: idle first, then `take` selections
            if self.pending_takes > 0 {
                let t = self.pending_team.clone().unwrap();
                let cands = self.eligible[&t].clone();
                let unit = pick(b, &cands);
                self.eligible.get_mut(&t).unwrap().retain(|x| *x != unit);
                self.pending_takes -= 1;
                return Some(unit);
            }
            if self.team_cursor >= self.teams.len() {
                self.round_open = false;
                continue;
            }
            let t = self.teams[self.team_cursor].clone();
            self.team_cursor += 1;
            while !self.idle[&t].is_empty() {
                let u = self.idle.get_mut(&t).unwrap().remove(0);
                self.queue.push_back(u);
            }
            let n = self.eligible[&t].len() as i64;
            if n == 0 {
                continue;
            }
            let others: Vec<i64> = self.teams.iter().filter(|o| **o != t).map(|o| self.round_tally[o]).filter(|x| *x != 0).collect();
            let tally_t = self.round_tally[&t];
            let take = if others.is_empty() { n } else { 1.max(-((-tally_t).div_euclid(*others.iter().min().unwrap()))) };
            self.pending_takes = take.min(n);
            self.pending_team = Some(t);
            // idle units of this team were queued first; they are yielded before its selections
            if !self.queue.is_empty() {
                continue;
            }
        }
    }
}

/// The enemy this unit's bot plans its movement against: the nearest standing enemy on the board (ties by roster
/// order), else the first standing enemy still off it. None when no enemy is left.
pub fn choose_foe(b: &mut Battle, mover: UnitId) -> Option<UnitId> {
    let foes = enemies_of(b, mover);
    if foes.is_empty() {
        return None;
    }
    if foes.len() == 1 {
        return Some(foes[0]);
    }
    assert!(b.cfg.s("FOE_CHOICE") == "nearest", "Unknown FOE_CHOICE");
    let mut best: Option<(i64, usize, UnitId)> = None;
    for (i, f) in foes.iter().enumerate() {
        if let Some(d) = distance(b, mover, *f) {
            if best.map_or(true, |x| (d, i) < (x.0, x.1)) {
                best = Some((d, i, *f));
            }
        }
    }
    match best {
        Some(x) => Some(x.2),
        None => Some(foes[0]),
    }
}

/// The one enemy this unit attacks in an attack phase (bot choice, PROJECT_MAP Section 6 'Target choice').
pub fn choose_target(b: &mut Battle, attacker: UnitId, with_map: bool, adjacent_only: bool) -> Option<UnitId> {
    let mut candidates: Vec<(i64, usize, UnitId)> = Vec::new();
    for (i, e) in enemies_of(b, attacker).into_iter().enumerate() {
        let Some(d) = distance(b, attacker, e) else { continue };
        if adjacent_only && d != 1 {
            continue;
        }
        candidates.push((d, i, e));
    }
    if candidates.is_empty() {
        return None;
    }
    if candidates.len() == 1 || !with_map {
        return Some(candidates.iter().min_by_key(|r| (r.0, r.1)).unwrap().2);
    }
    let mut best: Option<((i64, i64, i64, usize), UnitId)> = None;
    for (d, i, e) in candidates {
        let a_xy = hex_xy(b, attacker).unwrap();
        let e_xy = hex_xy(b, e).unwrap();
        let trace = crate::los::trace_los_path(a_xy, e_xy, &b.board, crate::attack_resolution::los_height(&b.units[attacker]), crate::attack_resolution::los_height(&b.units[e])).unwrap();
        let no_los = if trace.result.los { 0 } else { 1 };
        let cannot_bear = if adjacent_only || crate::attack_resolution::weapons_can_bear(b, attacker, e) { 0 } else { 1 };
        let rank = (no_los, cannot_bear, d, i);
        if best.map_or(true, |x| rank < x.0) {
            best = Some((rank, e));
        }
    }
    best.map(|x| x.1)
}

/// The attack phases' declaration / resolution order (p.39): fixed at the start of the phase. `pick`: which of a
/// side's units declares next (default roster order).
pub fn fire_order(b: &mut Battle, teams_in_order: &[String], pick: &mut dyn FnMut(&mut Battle, &[UnitId]) -> UnitId) -> Vec<UnitId> {
    let mut act = Activation::new(b, teams_in_order, can_select_fire);
    let mut out = Vec::new();
    while let Some(u) = act.next(b, pick) {
        out.push(u);
    }
    out
}
