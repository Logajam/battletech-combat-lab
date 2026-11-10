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
