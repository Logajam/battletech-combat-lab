// Translated from pathfinder/combat.py (session 22). Part 1: the to-hit table and constants the rules code reads; the
// movement scoring (build_jump_states, evaluate_combat_hexes, compute_score) follows with the bots.

pub const AMM_STILL: i64 = 0;
pub const AMM_WALK: i64 = 1;
pub const AMM_RUN: i64 = 2;
pub const AMM_JUMP: i64 = 3;
pub const RANGE_MOD_SHORT: i64 = 0;
pub const RANGE_MOD_MEDIUM: i64 = 2;
pub const RANGE_MOD_LONG: i64 = 4;
pub const RATIO_EPSILON: f64 = 0.001;
pub const SEVERITY_CAP: f64 = 2.0;

pub fn mode_to_amm(mode: &str) -> i64 {
    match mode {
        "Stand Still" => AMM_STILL,
        "Walk" => AMM_WALK,
        "Run" => AMM_RUN,
        "Jump" => AMM_JUMP,
        other => panic!("KeyError: {}", other),
    }
}

/// P(2d6 roll >= tn). tn<=2 always hits; tn>12 is an automatic miss.
pub fn hit_probability(tn: i64) -> f64 {
    if tn <= 2 {
        return 1.0;
    }
    if tn > 12 {
        return 0.0;
    }
    let n = [36.0, 35.0, 33.0, 30.0, 26.0, 21.0, 15.0, 10.0, 6.0, 3.0, 1.0][(tn - 2) as usize];
    n / 36.0
}

/// Forward-count -> Target Movement Modifier, +1 if jumped.
pub fn fc_to_tmm(fc: i64, jumped: bool) -> Result<i64, String> {
    if fc < 0 {
        return Err(format!("forward_count must be >= 0, got {}", fc));
    }
    let mut tmm = 5;
    for (max_fc, t) in [(2, 0), (4, 1), (6, 2), (9, 3), (17, 4)] {
        if fc <= max_fc {
            tmm = t;
            break;
        }
    }
    Ok(tmm + if jumped { 1 } else { 0 })
}

/// Nearest of the 6 facings pointing from from_hex toward to_hex (cube dot-product against each facing's unit vector).
pub fn direction_facing(from_hex: (i64, i64), to_hex: (i64, i64)) -> Result<i64, String> {
    if from_hex == to_hex {
        return Err(format!("Cannot determine a direction from hex ({}, {}) to itself.", from_hex.0, from_hex.1));
    }
    let (dx, dy) = (to_hex.0 - from_hex.0, to_hex.1 - from_hex.1);
    let q = dx as f64;
    let r = (dy - dx) as f64 / 2.0;
    let s = -q - r;
    let mut best_facing = 0;
    let mut best_dot = f64::NEG_INFINITY;
    for (facing, (fx, fy)) in crate::hex_geometry::FACING_DELTAS.iter().enumerate() {
        let (vq, vr) = (*fx as f64, (*fy - *fx) as f64 / 2.0);
        let vs = -vq - vr;
        let dot = q * vq + r * vr + s * vs;
        if dot > best_dot {
            best_dot = dot;
            best_facing = facing as i64;
        }
    }
    Ok(best_facing)
}

/// 'Walk' if mp_spent fits within the Walking MP budget, else 'Run'.
pub fn classify_movement_mode(mp_spent: i64, walking_mp: i64) -> &'static str {
    if mp_spent == 0 {
        return "Stand Still";
    }
    if mp_spent <= walking_mp { "Walk" } else { "Run" }
}

pub const JUMP_BLOCK_MARGIN: i64 = 1;

/// Every (x, y, facing) state reachable by jumping, given jump_mp: {state: forward_count} in board-hex order.
pub fn build_jump_states(board: &crate::board_parser::Board, start_x: i64, start_y: i64, jump_mp: i64) -> Result<crate::fasthash::IndexMap<(i64, i64, i64), i64>, String> {
    use crate::hex_geometry::{hex_label, parse_hex_label};
    use crate::los::{hex_distance, hex_line_sampled as hex_line};
    let hex_info = |h: (i64, i64)| -> Option<&crate::board_parser::Hex> { hex_label(h.0, h.1).ok().and_then(|l| board.hexes.get(&l)) };
    let start_hex = (start_x, start_y);
    let start_info = hex_info(start_hex).ok_or_else(|| format!("Jump start hex {} is not on the loaded board.", crate::pyfmt::py_repr_str(&hex_label(start_x, start_y).unwrap_or_default())))?;
    if start_info.impassable {
        return Err(format!("Jump start hex {} is marked impassable.", crate::pyfmt::py_repr_str(&hex_label(start_x, start_y).unwrap())));
    }
    let block_threshold = start_info.level + jump_mp + JUMP_BLOCK_MARGIN;
    let mut states = crate::fasthash::IndexMap::default();
    for (label, info) in &board.hexes {
        if info.impassable {
            continue;
        }
        let cand = parse_hex_label(label).unwrap();
        if cand == start_hex {
            continue;
        }
        let dist = hex_distance(start_hex, cand);
        if dist > jump_mp {
            continue;
        }
        if info.level >= block_threshold {
            continue;
        }
        let path = hex_line(start_hex, cand);
        let mut blocked = false;
        if path.len() > 2 {
            for step in &path[1..path.len() - 1] {
                let infos: Vec<Option<&crate::board_parser::Hex>> = step.iter().map(|h| hex_info(*h)).collect();
                if infos.iter().any(|i| i.is_none()) {
                    blocked = true;
                    break;
                }
                let chosen = infos.iter().map(|i| i.unwrap().level).min().unwrap();
                if chosen >= block_threshold {
                    blocked = true;
                    break;
                }
            }
        }
        if blocked {
            continue;
        }
        for facing in 0..6 {
            states.insert((cand.0, cand.1, facing), dist);
        }
    }
    Ok(states)
}
