// Translated from INTEGRATION__expected_damage.py (session 22): E[damage | hit] of one weapon.
use crate::battle::{Battle, UnitId};
use crate::damage_resolution::cluster_hits_count;
use crate::equipment::ItemId;
use crate::weapon_rules::{cluster_roll_modifier, is_cluster, is_streak};

/// P(2d6 == n) for n in 2..=12 as the Python's literals (`k / 36`).
pub fn p_2d6_exact() -> [(i64, f64); 11] {
    [(2, 1.0 / 36.0), (3, 2.0 / 36.0), (4, 3.0 / 36.0), (5, 4.0 / 36.0), (6, 5.0 / 36.0), (7, 6.0 / 36.0), (8, 5.0 / 36.0), (9, 4.0 / 36.0), (10, 3.0 / 36.0), (11, 2.0 / 36.0), (12, 1.0 / 36.0)]
}

/// Expected number of submunitions / shots that connect for a Cluster Hits Table column `shots` with a modifier.
pub fn expected_cluster_hits(b: &Battle, shots: i64, modifier: i64) -> Result<f64, String> {
    let mut total = 0.0;
    for (roll, p) in p_2d6_exact() {
        let modified = 2.max(12.min(roll + modifier));
        total += p * cluster_hits_count(b, shots, modified)? as f64;
    }
    Ok(total)
}

/// E[damage | hit] for one weapon instance (a Number: int for a flat hit, float for a cluster).
pub fn expected_damage_per_hit(b: &Battle, u: UnitId, w: ItemId, cluster_hit_modifier: i64) -> Result<crate::pyfmt::Num, String> {
    use crate::pyfmt::Num;
    let it = &b.units[u].items[w];
    if it.category.as_deref() != Some("weapon") {
        return Err(format!("expected_damage_per_hit() called on a non-weapon: {}", crate::pyfmt::py_repr_str(&it.name)));
    }
    let Some(dps) = it.damage_per_shot else {
        return Err(format!("{} has no confirmed damage_per_shot in equipment.json - can't compute expected damage. Fix the data rather than guessing here.", crate::pyfmt::py_repr_str(&it.name)));
    };
    if !is_cluster(b, u, w) {
        return Ok(Num::I(dps));
    }
    let rack = it.rack_size.unwrap();
    if is_streak(b, u, w) {
        return Ok(Num::I(dps * rack));
    }
    let modifier = cluster_hit_modifier + cluster_roll_modifier(b, u, w);
    Ok(Num::F(dps as f64 * expected_cluster_hits(b, rack, modifier)?))
}
