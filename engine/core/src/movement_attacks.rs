// Translated from INTEGRATION__movement_attacks.py (session 22): the displacement arithmetic charges, pushes and DFAs
// share. The mover index and the scoring of charge / DFA options belong to the bots (stages 7-8).
use crate::battle::{Battle, UnitId};
use crate::combat;
use crate::damage_resolution::apply_damage;
use crate::hex_geometry;
use crate::los::trace_los_path;
use crate::mech_state::*;
use crate::physical_gear as gear;
use crate::pyfmt::Num;
use crate::water;

pub const IMMOBILE_COMPARATIVE_PILOTING: i64 = 4;

pub fn groupings(damage: i64) -> Vec<i64> {
    let mut v = vec![5; damage.div_euclid(5) as usize];
    if damage.rem_euclid(5) != 0 {
        v.push(damage.rem_euclid(5));
    }
    v
}

pub fn comparative_modifier(attacker: &Mech, target: &Mech) -> i64 {
    attacker.piloting - if is_immobile(target) { IMMOBILE_COMPARATIVE_PILOTING } else { target.piloting }
}

/// The LOS terrain modifier without partial cover (charges ignore it, p.78).
pub fn terrain_modifier(b: &Battle, a_xy: (i64, i64), t_xy: (i64, i64)) -> i64 {
    let h = crate::attack_resolution::standing();
    let trace = trace_los_path(a_xy, t_xy, &b.board, h, h).unwrap();
    let cover = trace.steps.last().map_or(0, |s| s.partial_cover);
    trace.result.modifier - cover
}

pub fn hit_chance(tn: i64) -> f64 {
    if tn <= 12 { combat::hit_probability(tn) } else { 0.0 }
}

/// Deal `damage` to mech in 5-point groupings, each rolled on `table` against `side` (p.87). Returns
/// [(location, was it spiked)] in order.
#[allow(clippy::too_many_arguments)]
pub fn apply_groups(b: &mut Battle, u: UnitId, damage: i64, table: &str, side: &str, label: &str, spike_wear: bool, onto: Option<&str>) -> Vec<(String, bool)> {
    let mut hits = Vec::new();
    for g in groupings(damage) {
        if b.is_destroyed(u) {
            return hits;
        }
        let loc = match onto {
            Some(l) => l.to_string(),
            None => crate::physical::location(b, table, side, u),
        };
        let dmg = water::physical_damage(b, u, &loc, g);
        let name = b.units[u].side_name.clone().unwrap_or_default();
        b.log(format!("    {}: {} to {}'s {}{}.", label, dmg, name, loc, if dmg != g { " (halved: under water, p.77)" } else { "" }));
        let (dmg, spiked) = gear::spike_reduce(b, u, &loc, dmg, label);
        let dmg = gear::shield_absorb(b, u, &loc, dmg, side);
        if loc == "Head" && head_hit_hurts_pilot(&b.units[u]) {
            pilot_hit(&mut b.units[u], 1, true);
            b.pilot_hit_ev(u, "head hit");
        }
        apply_damage(b, u, &loc, Num::I(dmg), if side == "rear" { "rear_armor" } else { "armor" }, DamageType::Physical);
        if spiked && spike_wear {
            gear::spike_wear(b, u, &loc);
        }
        hits.push((loc, spiked));
    }
    hits
}

/// The label of the hex one step from `label` in facing direction 0-5, or None off the coordinate grid.
pub fn neighbour(label: &str, direction: i64) -> Option<String> {
    let (x, y) = hex_geometry::parse_hex_label(label).unwrap();
    let (dx, dy) = hex_geometry::FACING_DELTAS[direction as usize];
    hex_geometry::hex_label(x + dx, y + dy).ok()
}

/// Where a mech on from_label pushed one hex in `direction` ends up: ("off", None, 0), ("blocked", None, 0) or
/// ("moved", label, levels dropped).
pub fn displacement(b: &Battle, from_label: &str, direction: i64) -> (&'static str, Option<String>, i64) {
    let to = neighbour(from_label, direction);
    let Some(to) = to.filter(|t| b.board.hexes.contains_key(t)) else { return ("off", None, 0) };
    if b.board.hexes[&to].building && !b.board.hexes[from_label].building {
        return ("blocked", None, 0);
    }
    let drop = b.board.hexes[from_label].level - b.board.hexes[&to].level;
    if drop <= -3 {
        return ("blocked", None, 0);
    }
    ("moved", Some(to), drop)
}

/// Charge / DFA targets: on the board, not destroyed, finished moving or immobile (pp.78-79). A 'Mech that has
/// declared its own charge or DFA has not finished moving (its movement ends in the Physical Attack Phase), so it can't
/// be charged or DFA'd (Core p.78) - two 'Mechs never charge each other. And a 'Mech is the target of only one charge,
/// DFA or push a turn (p.83): not one another 'Mech has already declared a charge or DFA on.
pub fn can_be_attacked(b: &mut Battle, target: UnitId, target_has_moved: bool) -> bool {
    let t = &b.units[target];
    let mid_attack = t.charging.is_some() || t.dfa.is_some() || already_charged_or_dfad(b, target);
    t.hex.is_some() && !b.is_destroyed(target) && !mid_attack && (target_has_moved || is_immobile(&b.units[target]))
}

/// Some 'Mech has declared a charge or DFA on `target` this turn (p.83: one charge, DFA or push per target).
pub fn already_charged_or_dfad(b: &Battle, target: UnitId) -> bool {
    b.units.iter().any(|m| m.charging == Some(target) || m.dfa == Some(target))
}

/// The PSRs a charging / DFA mech owes when its movement finally ends in the Physical Attack Phase.
pub fn end_of_movement_triggers(b: &mut Battle, u: UnitId) -> Vec<(String, i64)> {
    let pending = b.units[u].deferred_end_of_move.take();
    b.units[u].deferred_end_of_move = Some(serde_json::Value::Null);
    let pending = match pending {
        Some(serde_json::Value::Object(o)) => o,
        _ => return vec![],
    };
    if b.is_destroyed(u) || b.units[u].prone || b.units[u].hex.is_none() {
        return vec![];
    }
    let hex = b.units[u].hex.clone().unwrap();
    let from_hex = pending["from_hex"].as_str().unwrap().to_string();
    let mut out: Vec<(String, i64)> = Vec::new();
    if hex != from_hex {
        let info = &b.board.hexes[&hex];
        if b.units[u].move_mode == "Jump" {
            let depth = water::depth_at(&b.board, Some(&hex));
            if depth >= 1 {
                out.push((format!("landed in water at {} (depth {})", hex, depth), 0));
            }
            if info.features.0.contains_key("rubble") {
                out.push((format!("landed in rubble at {}", hex), 0));
            }
        } else {
            let running = b.units[u].move_mode == "Run";
            for cause in crate::terrain_rules::step_psr_causes(Some(&b.board.hexes[&from_hex]), info, false, running) {
                out.push((format!("entered {} at {}", cause, hex), crate::terrain_rules::psr_modifier(cause)));
            }
        }
    }
    let mode = pending.get("mode").and_then(|m| m.as_str());
    if let Some(mode) = mode {
        if let Some(trigger) = crate::piloting_rolls::movement_psr_trigger(&b.units[u], mode) {
            let n = crate::piloting_rolls::movement_psr_count(&b.units[u], mode);
            for _ in 0..n {
                out.push((format!("end of movement ({}, {})", mode, trigger), 0));
            }
        }
    }
    out
}

/// Worth of `damage` in 5-point groups rolled on `table` against `side`.
pub fn table_worth(b: &Battle, damage: i64, mech: UnitId, table: &str, side: &str) -> f64 {
    let mut w = crate::physical::Worth::new(b, mech, false);
    // Python: sum(...) of floats
    let mut terms = Vec::new();
    for g in groupings(damage) {
        terms.push(g as f64 * w.factor(b, table, side, g as f64));
    }
    crate::pyfmt::py_sum(terms)
}

/// What being pushed this way costs the target: its whole remaining armor + structure off the board, the fall's worth
/// 2+ levels down (p.115), else 0.
pub fn displacement_worth(b: &Battle, target: UnitId, from_label: &str, direction: i64) -> Num {
    let (kind, _, drop) = displacement(b, from_label, direction);
    if kind == "off" {
        return crate::attack_resolution::total_hp(&b.units[target]);
    }
    if kind == "moved" && drop >= 2 {
        let mass = b.units[target].mass.unwrap_or(0);
        let dmg = -((-mass).div_euclid(10)) * (drop + 1);
        return Num::F(table_worth(b, dmg, target, "standard", "front"));
    }
    Num::F(0.0)
}
