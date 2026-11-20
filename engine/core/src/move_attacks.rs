// Translated from INTEGRATION__movement_attacks.py: the attacks a mech declares in the Movement Phase (charges, death
// from above) as movement-picker options - Pose, MoverIndex, values, scored_options, best_by_mode.
use crate::fasthash::{HashMap, HashSet};

use crate::fasthash::IndexMap;

use crate::battle::{Battle, UnitId};
use crate::hex_geometry;
use crate::los::{hex_distance, hex_line_sampled as hex_line};
use crate::mech_state::*;
use crate::move_eval::{Candidate, MoveEvaluator};
use crate::move_options::{self, PathNotes};
use crate::movement_attacks as ma;
use crate::ranged_combat::Pick;
use crate::terrain_rules;
use crate::water;

pub use ma::can_be_attacked;

const PRONE_HEIGHT: i64 = 1;
const STANDING_HEIGHT: i64 = 2;

/// Hexes other units stand in (the unit's `other_unit_hexes`, set by the turn loop; empty when not set): a charge or
/// DFA may not stop in one - "no 'Mech can deliberately violate" the stacking limit (Core p.49). Session 25: the stop
/// lists did not check, and a charge could end on a friend's hex (found by Hydra's trials). Same in the Python.
fn held_hexes(b: &Battle, mover: UnitId) -> Vec<String> {
    match &b.units[mover].other_unit_hexes {
        Some(serde_json::Value::Array(a)) => a.iter().filter_map(|v| v.as_str().map(|s| s.to_string())).filter(|s| !s.is_empty()).collect(),
        Some(serde_json::Value::String(s)) if !s.is_empty() => vec![s.clone()],
        _ => Vec::new(),
    }
}

/// Where a (possibly hypothetical) target stands for these attacks.
#[derive(Clone, Debug)]
pub struct Pose {
    pub label: String,
    pub xy: (i64, i64),
    pub facing: i64,
    pub tmm: i64,
    pub prone: bool,
    pub superheavy: bool,
}

pub fn pose_of(b: &Battle, u: UnitId) -> Pose {
    let m = &b.units[u];
    Pose {
        label: m.hex.clone().unwrap(),
        xy: hex_geometry::parse_hex_label(m.hex.as_deref().unwrap()).unwrap(),
        facing: hex_geometry::compass_to_facing(&m.facing).unwrap(),
        tmm: crate::attack_resolution::target_tmm(m),
        prone: m.prone,
        superheavy: is_superheavy(m),
    }
}

pub fn pose_at(b: &Battle, label: &str, facing_compass: &str, fc: i64, mode: &str, target: Option<UnitId>) -> Pose {
    Pose {
        label: label.to_string(),
        xy: hex_geometry::parse_hex_label(label).unwrap(),
        facing: hex_geometry::compass_to_facing(facing_compass).unwrap(),
        tmm: crate::combat::fc_to_tmm(fc, mode == "Jump").unwrap() + target.map_or(0, |t| target_size_modifier(&b.units[t])),
        prone: false,
        superheavy: target.map_or(false, |t| is_superheavy(&b.units[t])),
    }
}

/// The mover's reachable states for movement attacks, built once.
pub struct MoverIndex {
    mover: UnitId,
    standup_mp: Option<i64>,
    walk: i64,
    budget: i64,
    level_limit: terrain_rules::GroundLimit,
    ground: IndexMap<(i64, i64, i64), Vec<(i64, i64)>>,
    jump_mp: i64,
    start_label: Option<String>,
    start_xy: Option<(i64, i64)>,
    jump_hexes: HashSet<(i64, i64)>,
}

impl MoverIndex {
    pub fn new(b: &Battle, mover: UnitId, standup_mp: Option<i64>, notes: &mut PathNotes) -> MoverIndex {
        let m = &b.units[mover];
        let walk = compute_walk_mp(m);
        let budget = if standup_mp.is_none() { compute_running_mp(m) } else { standup_mp.unwrap() };
        let level_limit = terrain_rules::max_level_change(ground_level_limited(m), is_superheavy(m));
        let mut ground: IndexMap<(i64, i64, i64), Vec<(i64, i64)>> = IndexMap::default();
        for (x, y, facing, fc, mode, mp) in move_options::movement_options(b, mover, standup_mp, None, false, notes) {
            if mode != "Jump" {
                ground.entry((x, y, facing)).or_default().push((fc, mp));
            }
        }
        // CHARGING AFTER A BACKWARD STEP (Core p.78: a charge needs no straight line and no run - only the MP to enter the
        // target's hex, facing it; walking may go backward, p.46; backlog N9, rules review G12): the stops only a walk with
        // backward steps reaches are added. The table does not say which way such a path last moved, and the movement
        // modifier counts only the hexes since the last reversal (p.65), so the planner counts their charge as one hex (fc 0,
        // + 1 for the target's hex): never more damage than the rules give. The engine's resolution counts the real path.
        if standup_mp.is_none() {
            for (x, y, facing, _fc, mode, mp) in move_options::movement_options(b, mover, standup_mp, None, true, notes) {
                if mode == "Jump" || mode == "Run" {
                    continue;
                }
                let e = ground.entry((x, y, facing)).or_default();
                if !e.iter().any(|(_, m)| *m <= mp) {
                    e.push((0, mp));
                }
            }
        }
        let jump_mp = if standup_mp.is_none() && !m.prone { water::jump_mp(b, mover) } else { 0 };
        let start_label = m.hex.clone();
        let start_xy = start_label.as_deref().map(|h| hex_geometry::parse_hex_label(h).unwrap());
        let mut jump_hexes = HashSet::default();
        if jump_mp > 0 && start_label.is_some() {
            let (sx, sy) = start_xy.unwrap();
            jump_hexes = crate::combat::build_jump_states(&b.board, sx, sy, jump_mp).unwrap().keys().map(|(x, y, _)| (*x, *y)).collect();
        }
        MoverIndex { mover, standup_mp, walk, budget, level_limit, ground, jump_mp, start_label, start_xy, jump_hexes }
    }

    pub fn release(&mut self) {}

    /// Stop next to the target facing it with the MP to enter its hex (p.78); best (most hexes, least MP) per (hex, mode).
    pub fn charge_states(&self, b: &Battle, pose: &Pose) -> Vec<Pick> {
        let hexes = &b.board.hexes;
        let t_info = &hexes[&pose.label];
        let mut best: IndexMap<(String, i64, &'static str), (i64, i64)> = IndexMap::default();
        let held = held_hexes(b, self.mover);
        for d in 0..6 {
            let Some(n) = ma::neighbour(&pose.label, d) else { continue };
            if !hexes.contains_key(&n) {
                continue;
            }
            if held.contains(&n) {
                continue; // another unit stands there: no 'Mech may end its move in it (stacking, p.49)
            }
            let (nx, ny) = hex_geometry::parse_hex_label(&n).unwrap();
            let facing = (d + 3) % 6;
            let Some(states) = self.ground.get(&(nx, ny, facing)) else { continue };
            if states.is_empty() {
                continue;
            }
            let Some(cost) = terrain_rules::step_cost(Some(&hexes[&n]), t_info, self.level_limit, false) else { continue };
            let allowed = water::physical_allowed(water::state_at(&b.board, Some(&n), false, is_superheavy(&b.units[self.mover])), water::state_at(&b.board, Some(&pose.label), pose.prone, pose.superheavy));
            if allowed.as_ref().is_some_and(|a| !a.contains(&"charge")) {
                continue;
            }
            for (fc, mp) in states {
                let total = mp + cost;
                if total > self.budget {
                    continue;
                }
                let mode = if self.standup_mp.is_some() { "Run" } else { crate::combat::classify_movement_mode(total, self.walk) };
                let key = (n.clone(), facing, mode);
                let cand = (fc + 1, -total);
                if !best.contains_key(&key) || cand > best[&key] {
                    best.insert(key, cand);
                }
            }
        }
        best.into_iter().map(|((n, f, m), (fc, neg))| Pick { hex: n, facing: hex_geometry::facing_to_compass(f).unwrap().to_string(), mode: m.to_string(), fc, mp_spent: -neg, charge: true, dfa: false }).collect()
    }

    /// A jump that can land on the target's hex, stopping in the hex next to it along the path.
    pub fn dfa_states(&self, b: &Battle, pose: &Pose) -> Vec<Pick> {
        if self.jump_hexes.is_empty() || !self.jump_hexes.contains(&pose.xy) {
            return vec![];
        }
        if water::state_at(&b.board, Some(&pose.label), pose.prone, pose.superheavy) == water::SUBMERGED {
            return vec![];
        }
        let start_xy = self.start_xy.unwrap();
        let dist = hex_distance(start_xy, pose.xy);
        let hexes = &b.board.hexes;
        let height = if pose.superheavy { if pose.prone { 2 } else { 3 } } else if pose.prone { PRONE_HEIGHT } else { STANDING_HEIGHT };
        let need = hexes[&pose.label].level + height - hexes[self.start_label.as_ref().unwrap()].level;
        if dist > self.jump_mp || need > self.jump_mp {
            return vec![];
        }
        let stop = if dist == 1 {
            start_xy
        } else {
            let line = hex_line(start_xy, pose.xy);
            line[line.len() - 2][0]
        };
        let label = hex_geometry::hex_label(stop.0, stop.1).unwrap();
        if held_hexes(b, self.mover).contains(&label) {
            return vec![]; // the jump would end on another unit's hex (stacking, p.49)
        }
        let facing = crate::combat::direction_facing(stop, pose.xy).unwrap();
        vec![Pick { hex: label, facing: hex_geometry::facing_to_compass(facing).unwrap().to_string(), mode: "Jump".to_string(), fc: dist, mp_spent: dist, charge: false, dfa: true }]
    }
}

/// (dealt worth, attacker self-damage worth, P(hit), TN, raw damage, side on target, may the target attack it physically?).
pub fn values(b: &Battle, mover: UnitId, target: UnitId, pose: &Pose, state: &Pick) -> (f64, f64, f64, i64, i64, &'static str, bool) {
    let a_xy = hex_geometry::parse_hex_label(&state.hex).unwrap();
    let h = crate::attack_resolution::standing();
    let side = crate::attack_resolution::attack_side(b, a_xy, pose.xy, pose.facing, h, h);
    let direction = crate::combat::direction_facing(a_xy, pose.xy).unwrap();
    let t_water = water::state_at(&b.board, Some(&pose.label), pose.prone, pose.superheavy);
    let wet = |table: &str, s: &str| water::physical_value_factor(&b.units[target], t_water, table, s);
    let (m, t) = (&b.units[mover], &b.units[target]);
    if state.charge {
        let tn = crate::charge::to_hit(b, mover, &state.mode, target, a_xy, pose.xy, pose.tmm);
        let p = ma::hit_chance(tn);
        let dmg = crate::charge::target_damage(m, crate::combat::fc_to_tmm(state.fc, false).unwrap());
        let dealt = p * (ma::table_worth(b, dmg, target, "standard", side) * wet("standard", side) + ma::displacement_worth(b, target, &pose.label, direction).f());
        let self_cost = p * ma::table_worth(b, crate::charge::attacker_damage(t), mover, "standard", "front");
        return (dealt, self_cost, p, tn, dmg, side, true);
    }
    let tn = crate::dfa::to_hit(b, mover, target, pose.tmm);
    let p = ma::hit_chance(tn);
    let dmg = crate::dfa::target_damage(m);
    let (table, t_side) = if pose.prone { ("standard", "rear") } else { ("punch", side) };
    let dealt = p * (ma::table_worth(b, dmg, target, table, t_side) * wet(table, t_side) + ma::displacement_worth(b, target, &pose.label, direction).f());
    let self_cost = p * ma::table_worth(b, crate::dfa::attacker_damage(m), mover, "kick", "front") + (1.0 - p) * ma::table_worth(b, crate::dfa::miss_fall_damage(m), mover, "standard", "rear");
    (dealt, self_cost, p, tn, dmg, side, false)
}

/// Best ordinary dealt (x the target's exposure for that side) per mode - the gate; computed only if a state needs it.
pub enum BestMode<'a> {
    Lazy(&'a [Candidate], [f64; 4]),
}

fn side_ix(s: &str) -> usize {
    match s {
        "front" => 0,
        "left" => 1,
        "right" => 2,
        _ => 3,
    }
}

pub fn best_by_mode(cands: &[Candidate], target_exposure: &[f64; 4]) -> HashMap<&'static str, f64> {
    let mut best: HashMap<&'static str, f64> = HashMap::default();
    for c in cands {
        let v = c.dealt * target_exposure[side_ix(c.side_on_defender)];
        if v > best.get(c.mode).copied().unwrap_or(0.0) {
            best.insert(c.mode, v);
        }
    }
    best
}

type PsrFn<'a> = &'a dyn Fn(&Battle, &str, i64, &str, &str, i64) -> f64;

/// [(score, candidate, state, note)] for the movement attacks that pass the gate, best first.
#[allow(clippy::too_many_arguments)]
pub fn scored_options(b: &mut Battle, mover: UnitId, target: UnitId, pose: &Pose, index: &MoverIndex, ev: &mut MoveEvaluator, mover_exposure: &[f64; 4], target_exposure: &[f64; 4], psr_cost: PsrFn, best_mode: BestMode, target_args: &(String, String, i64, String, i64), objective: &dyn Fn(f64, f64, f64, f64, f64) -> f64, allowed: &[&str]) -> Vec<(f64, Candidate, Pick, String)> {
    let mut out: Vec<(f64, Candidate, Pick, String)> = Vec::new();
    let mut states: Vec<Pick> = Vec::new();
    if allowed.contains(&"charge") && b.cfg.b("CHARGES") && !pose.prone {
        states.extend(index.charge_states(b, pose));
    }
    if allowed.contains(&"dfa") && b.cfg.b("DFA") {
        states.extend(index.dfa_states(b, pose));
    }
    let mut best_map: Option<HashMap<&'static str, f64>> = None;
    for state in states {
        if best_map.is_none() {
            let BestMode::Lazy(cands, exp) = &best_mode;
            best_map = Some(best_by_mode(cands, exp));
        }
        let (dealt_abs, self_cost, p, tn, dmg, side, physical_reply) = values(b, mover, target, pose, &state);
        if dealt_abs <= best_map.as_ref().unwrap().get(state.mode.as_str()).copied().unwrap_or(0.0) + 1e-12 {
            continue; // the gate
        }
        let (x, y) = hex_geometry::parse_hex_label(&state.hex).unwrap();
        let prepared = ev.prepare(b, &[(x, y, hex_geometry::compass_to_facing(&state.facing).unwrap(), state.fc, move_options::mode_str(&state.mode), state.mp_spent)]);
        let cands = ev.evaluate(b, &target_args.0, &target_args.1, target_args.2, &target_args.3, target_args.4, &prepared, physical_reply);
        let base = match cands.into_iter().next() {
            Some(c) => c,
            None => Candidate { hex: state.hex.clone(), facing: hex_geometry::facing_to_compass(hex_geometry::compass_to_facing(&state.facing).unwrap()).unwrap(), mode: move_options::mode_str(&state.mode), fc: state.fc, mp_spent: state.mp_spent, distance: 1, dealt: 0.0, received: 0.0, movement_heat: 0, side_on_defender: side, side_on_mover: "front", attack: "" },
        };
        let t_mult = { let v = target_exposure[side_ix(side)]; if v != 0.0 { v } else { 1.0 } };
        let m_mult = { let v = mover_exposure[side_ix(base.side_on_mover)]; if v != 0.0 { v } else { 1.0 } };
        let mut cand = base.clone();
        cand.dealt = dealt_abs / t_mult;
        cand.received = base.received + self_cost / m_mult;
        cand.side_on_defender = side;
        cand.attack = if state.charge { "charge" } else { "dfa" };
        let score = objective(cand.dealt, cand.received, t_mult, m_mult, psr_cost(b, &state.mode, state.fc, &state.hex, &state.facing, state.mp_spent));
        let kind = if state.charge { "CHARGE" } else { "DFA" };
        out.push((score, cand, state, format!("{} (TN {}, P {}, {} dmg)", kind, tn, crate::pyfmt::Fx(p, 2), dmg)));
    }
    out.sort_by(|a, c| (-a.0).partial_cmp(&(-c.0)).unwrap());
    out
}
