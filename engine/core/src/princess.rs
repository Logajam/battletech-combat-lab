// Translated from INTEGRATION__princess.py (the v0.50.07 clone's shared pieces the modern ranker reuses): the chance a move's
// piloting rolls all succeed, the hazard prices of the hexes a path enters, the armor bias, MegaMek's direction, and the
// estimate of an enemy that has not moved yet.
use std::collections::HashMap;

use crate::battle::{Battle, UnitId};
use crate::combat::hit_probability;
use crate::hex_geometry;
use crate::mech_state::*;
use crate::move_options::{Opt, PathNotes};
use crate::princess_geometry::{mm, mm_distance, neighbor, ConvexBoardArea, HexLine};
use crate::pyfmt::py_round;
use crate::terrain_rules;

pub const FACING_MOD_MULTIPLIER: f64 = 50.0;
pub const UNIT_DESTRUCTION_FACTOR: f64 = 1000.0;
pub const ALLOW_FACING_TOLERANCE: i64 = 1;
pub const UNMOVED_DAMAGE_DISCOUNT: f64 = 0.25;

/// getMovePathSuccessProbability: the chance every piloting roll this move forces succeeds.
pub fn success_probability(b: &Battle, mover: UnitId, o: &Opt, psr_applies: bool, notes: &PathNotes) -> f64 {
    if !psr_applies {
        return 1.0;
    }
    let m = &b.units[mover];
    let mut p = 1.0;
    let psr_mode = if o.mode == "Run" && o.fc >= 1 { Some("running") } else if o.mode == "Jump" { Some("jump") } else { None };
    if let Some(pm) = psr_mode {
        if let Some(tn) = crate::piloting_rolls::movement_psr_target_number(m, pm) {
            p *= hit_probability(tn).powf(crate::piloting_rolls::movement_psr_count(m, pm) as f64);
        }
    }
    let target = m.piloting + crate::piloting_rolls::preexisting_modifier(m) + crate::piloting_rolls::special_case_modifier(m);
    let ok = hit_probability(target);
    if o.mode == "Jump" {
        if crate::water::depth_at(&b.board, Some(&o.label)) >= 1 || b.board.hexes[&o.label].features.has("rubble") {
            p *= ok;
        }
    } else if o.mode == "Walk" || o.mode == "Run" {
        let n = notes.psrs.get(&(o.x, o.y, o.facing, o.fc, o.mode, o.mp_spent)).copied().unwrap_or(0);
        p *= ok.powf(n as f64);
    }
    p
}

fn bog_down_factor(pilot: i64, modifier: i64, end_hex: bool, jump_landing: bool) -> f64 {
    let odds = hit_probability(pilot + modifier).max(0.0);
    let bogged = if end_hex && jump_landing { 1.0 } else if !jump_landing { 1.0 - odds } else { 0.0 };
    let turns = if (1.0 - odds) < 1.0 && odds < 1.0 { 0.10f64.log10() / (1.0 - odds).log10() } else { UNIT_DESTRUCTION_FACTOR };
    1.0 + bogged + turns
}

fn submerged_breaches(m: &Mech, depth: i64, prone: bool) -> f64 {
    let mut total = 0.0;
    for (loc, entry) in &m.locations {
        if entry.destroyed {
            continue;
        }
        let legs = m.leg_locations.contains(loc) || loc == "Front Left Leg" || loc == "Front Right Leg";
        if !(depth >= 2 || prone || legs) || entry.armor.f() > 0.0 {
            continue;
        }
        if loc == "Head" || loc == "Center Torso" {
            return UNIT_DESTRUCTION_FACTOR;
        }
        total += 50.0;
    }
    total
}

fn swamp_hazard(m: &Mech, swamp: &[String], end_hex: bool, jump_landing: bool) -> f64 {
    let first = swamp.first().map(|s| s.as_str()).unwrap_or("1");
    let level: i64 = if first.is_empty() { 1 } else { first.parse().unwrap_or(1) };
    let quicksand = level > 1;
    let chance = if quicksand { 1.0 } else { 1.0 / 36.0 };
    let hazard = chance * UNIT_DESTRUCTION_FACTOR / (1.0 + 1.0);
    py_round(hazard * bog_down_factor(m.piloting, if quicksand { 3 } else { 1 }, end_hex, jump_landing)) as f64
}

fn leg_armor(m: &Mech) -> f64 {
    m.leg_locations.iter().map(|l| m.locations[l].armor.f().max(0.0)).sum()
}

fn total_armor(m: &Mech) -> f64 {
    m.locations.values().map(|e| e.armor.f().max(0.0) + e.rear_armor.map_or(0.0, |r| r.f()).max(0.0)).sum()
}

fn lava_hazard(m: &Mech, jump_landing: bool, end_hex: bool, prone: Option<bool>) -> f64 {
    let prone = prone.unwrap_or(m.prone);
    let mut psr_factor = 1.0;
    if jump_landing && end_hex {
        let odds = hit_probability(m.piloting + 4);
        let bogged = 1.0 - odds;
        let turns = if 0.0 < bogged && bogged < 1.0 { 0.10f64.log10() / bogged.log10() } else { 0.0 };
        psr_factor = 1.0 + bogged + turns;
    }
    let mut value = if end_hex { 10.0 } else { 5.0 };
    let (dmg, exposed) = if prone { (7.0 * m.locations.len() as f64, total_armor(m)) } else { (7.0 * m.leg_locations.len() as f64, leg_armor(m)) };
    value += UNIT_DESTRUCTION_FACTOR * (dmg / exposed.max(1.0));
    py_round(value * psr_factor) as f64
}

fn magma_hazard(m: &Mech, features: &crate::board_parser::Features, jump_landing: bool, end_hex: bool, prone: Option<bool>) -> f64 {
    match terrain_rules::magma_state(features) {
        Some(s) if s == terrain_rules::MAGMA_LIQUID => lava_hazard(m, jump_landing, end_hex, prone),
        Some(s) if s == terrain_rules::MAGMA_CRUST => {
            let breaks = if jump_landing { 0.5 } else { 0.1667 };
            py_round(lava_hazard(m, jump_landing, end_hex, prone) * breaks) as f64 + (if end_hex { 5.0 } else { 2.0 }) * (1.0 - breaks)
        }
        _ => 0.0,
    }
}

fn hazardous_liquid_hazard(b: &Battle, m: &Mech, label: &str, prone: Option<bool>) -> f64 {
    let dmg = 3.0f64.max(2.0 / 3.0);
    let exposed = if prone.unwrap_or(m.prone) || crate::water::depth_at(&b.board, Some(label)) > 1 { total_armor(m) } else { leg_armor(m) };
    py_round(UNIT_DESTRUCTION_FACTOR * (dmg / exposed.max(1.0))) as f64
}

pub type WaterFn<'a> = &'a dyn Fn(&Battle, &str, i64, bool, bool) -> f64;

/// checkHexForHazards for one hex.
pub fn hex_hazard(b: &Battle, mover: UnitId, label: &str, end_hex: bool, jump_landing: bool, prone: bool, water_fn: Option<WaterFn>) -> f64 {
    let m = &b.units[mover];
    let features = &b.board.hexes[label].features;
    let mut total = 0.0;
    let depth = crate::water::depth_at(&b.board, Some(label));
    if depth >= 1 {
        total += match water_fn {
            Some(f) => f(b, label, depth, end_hex, prone),
            None => submerged_breaches(m, depth, prone),
        };
    }
    if let Some(sw) = features.get("swamp") {
        total += swamp_hazard(m, sw, end_hex, jump_landing);
    }
    if features.has("mud") {
        total += py_round(bog_down_factor(m.piloting, 0, end_hex, false)) as f64;
    }
    total += magma_hazard(m, features, jump_landing, end_hex, Some(prone));
    if features.has("hazardous_liquid") {
        total += hazardous_liquid_hazard(b, m, label, Some(prone));
    }
    total
}

/// Has the board any hex hex_hazard could price (depth 1+ water, swamp, mud, magma, hazardous liquid)?
pub fn hazard_board(b: &Battle) -> bool {
    b.board.hexes.values().any(|i| i.depth.unwrap_or(0) >= 1 || ["swamp", "mud", "magma", "hazardous_liquid"].iter().any(|f| i.features.has(f)))
}

/// checkPathForHazards: a jump - its landing hex only; otherwise every hex its steps stand in, a hex once, the last step's
/// hex as the end hex. `steps`: the ground path to the state (None = none found). standup: the get-up step's hex.
#[allow(clippy::too_many_arguments)]
pub fn path_hazards(b: &Battle, mover: UnitId, o: &Opt, steps: Option<Vec<(i64, i64)>>, standup_hex: Option<(i64, i64)>, water_fn: Option<WaterFn>, stay: Option<&dyn Fn(&Battle) -> f64>) -> f64 {
    if o.mode == "Jump" {
        return hex_hazard(b, mover, &o.label, true, true, b.units[mover].prone, water_fn);
    }
    let moves = o.fc != 0 || o.mp_spent != 0;
    let mut steps: Option<Vec<(i64, i64)>> = if moves { steps.or_else(|| Some(vec![(o.x, o.y)])) } else { None };
    if let Some(h) = standup_hex {
        let mut v = vec![h];
        v.extend(steps.unwrap_or_default());
        steps = Some(v);
    }
    let steps = steps.unwrap_or_default();
    if steps.is_empty() {
        return stay.map_or(0.0, |f| f(b));
    }
    let mut total = 0.0;
    let mut previous: Option<(i64, i64)> = None;
    for (n, (x, y)) in steps.iter().enumerate() {
        if Some((*x, *y)) == previous {
            continue;
        }
        total += hex_hazard(b, mover, &hex_geometry::hex_label(*x, *y).unwrap(), n == steps.len() - 1, false, false, water_fn);
        previous = Some((*x, *y));
    }
    total
}

/// FacingDiffCalculator.getBiasTowardsFacing: +1 if the left side has more armor left, -1 if the right does.
pub fn armor_bias(m: &Mech) -> i64 {
    let side = |names: [&str; 3]| -> f64 {
        let mut total = 0.0;
        for n in names {
            let loc = location_name(m, n);
            if let Some(e) = m.locations.get(&loc) {
                if !e.destroyed {
                    total += e.armor.f().max(0.0);
                }
            }
        }
        total
    };
    let left = side(["Left Arm", "Left Leg", "Left Torso"]);
    let right = side(["Right Arm", "Right Leg", "Right Torso"]);
    if left > right { 1 } else if right > left { -1 } else { 0 }
}

fn location_name(m: &Mech, loc: &str) -> String {
    if m.mech_type == "quad" || m.mech_type == "quadvee" {
        match loc {
            "Right Arm" => return "Front Right Leg".into(),
            "Left Arm" => return "Front Left Leg".into(),
            "Right Leg" => return "Rear Right Leg".into(),
            "Left Leg" => return "Rear Left Leg".into(),
            _ => {}
        }
    }
    loc.to_string()
}

pub const SAME_HEX_DIRECTION: i64 = 5;

/// MegaMek Coords.direction: the facing from one hex toward another.
pub fn direction(from: (i64, i64), to: (i64, i64)) -> i64 {
    if from == to { SAME_HEX_DIRECTION } else { crate::combat::direction_facing(from, to).unwrap() }
}

/// {option key: (my damage, its weapon damage, its flank kick)} - the parts of evaluateUnmovedEnemy.
pub fn unmoved_parts(b: &mut Battle, mover: UnitId, other: UnitId, prepared: &[Opt]) -> HashMap<(String, i64, &'static str, i64, i64), (f64, f64, f64)> {
    let mut them = crate::move_select::Side::new(b, other, true);
    let reach = crate::move_select::opponent_options(b, other, &mut them);
    let area = ConvexBoardArea::new(&reach.iter().map(|s| mm((s.0, s.1))).collect::<Vec<_>>());
    let potential: std::collections::HashSet<((i64, i64), i64)> = reach.iter().map(|s| (mm((s.0, s.1)), s.2)).collect();
    let can_twist = crate::arcs::twist_offsets(&b.units[mover]).len() > 1;
    let kick = (b.units[other].mass.unwrap_or(0) as f64 / 5.0).ceil() * UNMOVED_DAMAGE_DISCOUNT;
    let mut mine_at: HashMap<i64, f64> = HashMap::new();
    let mut theirs_at: HashMap<i64, f64> = HashMap::new();
    let mut out = HashMap::new();
    for o in prepared {
        let here = mm(o.hex_xy());
        let f = o.facing;
        let rng = mm_distance(area.closest_to(here), here);
        if !mine_at.contains_key(&rng) {
            mine_at.insert(rng, crate::princess_fire::max_damage_at_range(b, mover, rng) as f64 * UNMOVED_DAMAGE_DISCOUNT);
            theirs_at.insert(rng, crate::princess_fire::max_damage_at_range(b, other, rng) as f64 * UNMOVED_DAMAGE_DISCOUNT);
        }
        let behind = mm(neighbor(o.hex_xy(), f + 3));
        let left_flank = mm(neighbor(o.hex_xy(), f + 2));
        let right_flank = mm(neighbor(o.hex_xy(), f + 4));
        let spread = if can_twist { (2, 4) } else { (1, 5) };
        let left = HexLine::new(behind, (f + spread.0).rem_euclid(6));
        let right = HexLine::new(behind, (f + spread.1).rem_euclid(6));
        let mine = if left.judge_area(&area) > 0 && right.judge_area(&area) < 0 { mine_at[&rng] } else { 0.0 };
        let theirs = theirs_at[&rng];
        let flank = [(behind, f), (behind, (f + 1) % 6), (behind, (f + 5) % 6), (left_flank, f), (left_flank, (f + 4) % 6), (left_flank, (f + 5) % 6), (right_flank, f), (right_flank, (f + 1) % 6), (right_flank, (f + 2) % 6)];
        let flank_kick = if flank.iter().any(|c| potential.contains(c)) { kick } else { 0.0 };
        out.insert((o.label.clone(), o.facing, o.mode, o.fc, o.mp_spent), (mine, theirs, flank_kick));
    }
    out
}
