// Translated from INTEGRATION__structure_weight.py (session 22): damage that reaches internal structure counts for more.
use crate::battle::{Battle, UnitId};
use crate::damage_resolution::transfer_map;
use crate::equipment::ItemId;
use crate::hit_location::table_for;
use crate::mech_state::Mech;
use crate::pyfmt::Num;
use crate::weapon_rules::{damage_groupings, is_cluster};

/// One row of a hit spread: (probability, location, armor key "armor" / "rear_armor").
pub type Spread = Vec<(f64, String, &'static str)>;

fn p_2d6(roll: i64) -> f64 {
    (6 - (roll - 7).abs()) as f64 / 36.0
}

/// The location a 2D6 roll strikes as a LOOKAHEAD sees it (a tripod's leg sub-roll reads the raw table; a destroyed
/// torso-cockpit head draws dice, a Python quirk kept).
fn lookahead_location(b: &Battle, u: UnitId, roll: i64, side: &str) -> String {
    if b.units[u].mech_type == "tripod" {
        let table = table_for(side);
        return table.iter().find(|(r, _)| *r == roll).map_or("Center Torso", |(_, l)| l).to_string();
    }
    crate::hit_location::resolve_hit_location_shared(b, u, roll, side)
}

/// [(probability, location, armor key)] for a shot on `side` of `mech` from its CURRENT state; `rolls` = another table.
pub fn hit_spread(b: &Battle, u: UnitId, side: &str, rolls: Option<&[(f64, String)]>) -> Spread {
    let mech = &b.units[u];
    let mut base: Vec<(f64, String)> = Vec::new();
    match rolls {
        Some(r) => base.extend(r.iter().cloned()),
        None => {
            for roll in 2..=12 {
                base.push((p_2d6(roll), lookahead_location(b, u, roll, side)));
            }
        }
    }
    let mut spread = Vec::new();
    for (p, loc0) in base {
        let mut loc: Option<String> = Some(loc0);
        while let Some(l) = &loc {
            if mech.locations.get(l.as_str()).map_or(false, |s| s.destroyed) {
                loc = transfer_map(l).map(|s| s.to_string());
            } else {
                break;
            }
        }
        let Some(l) = loc else { continue };
        let Some(state) = mech.locations.get(l.as_str()) else { continue };
        let key = if side == "rear" && state.rear_armor.is_some() { "rear_armor" } else { "armor" };
        spread.push((p, l, key));
    }
    spread
}

fn armor_of(m: &Mech, loc: &str, key: &str) -> Num {
    let s = &m.locations[loc];
    if key == "rear_armor" { s.rear_armor.unwrap_or(s.armor) } else { s.armor }
}

/// sum of P(roll) / durability(location) over a hit_spread.
pub fn vulnerability(m: &Mech, spread: &Spread) -> f64 {
    // Python: sum(...) of floats
    crate::pyfmt::py_sum(spread.iter().map(|(p, loc, key)| p / (armor_of(m, loc, key) + m.locations[loc.as_str()].structure).f().max(1.0)))
}

/// Worth of `damage` landing on a location with this armor / structure.
pub fn worth(damage: f64, armor: f64, structure: f64, k: f64) -> f64 {
    let armor_part = damage.min(armor);
    let structure_part = (damage - armor_part).min(structure);
    let rest = damage - armor_part - structure_part;
    armor_part + k * structure_part + rest
}

/// Expected worth of one hit of `damage` rolled on `spread` (a roll that leaves the mech counts flat).
pub fn spread_worth(m: &Mech, spread: &Spread, damage: f64, k: f64) -> f64 {
    // Python: two sum(...) calls of floats
    let covered: f64 = crate::pyfmt::py_sum(spread.iter().map(|(p, _, _)| *p));
    let sum = crate::pyfmt::py_sum(spread.iter().map(|(p, loc, key)| p * worth(damage, armor_of(m, loc, key).f(), m.locations[loc.as_str()].structure.f(), k)));
    damage * (1.0 - covered) + sum
}

/// Damage amounts of the separate location rolls one hit of `weapon` makes.
pub fn weapon_groups(b: &Battle, u: UnitId, w: ItemId) -> Result<Vec<Num>, String> {
    let total = crate::expected_damage::expected_damage_per_hit(b, u, w, 0)?;
    if !is_cluster(b, u, w) {
        return Ok(vec![total]);
    }
    Ok(damage_groupings(b, u, w, total))
}

/// {weapon: multiplier} of `attacker_weapons` fired at `target`'s `side` (no cache: speed only, stage 9).
pub fn multipliers(b: &Battle, attacker: UnitId, attacker_weapons: &[ItemId], target: UnitId, side: &str) -> Vec<(ItemId, f64)> {
    let k = b.cfg.f("MOVEMENT_STRUCTURE_WEIGHT");
    let t = &b.units[target];
    let spread = hit_spread(b, target, side, None);
    let mut result = Vec::new();
    for &w in attacker_weapons {
        if b.units[attacker].items[w].damage_per_shot.is_none() {
            continue;
        }
        let groups = weapon_groups(b, attacker, w).unwrap();
        let raw = crate::pyfmt::py_sum_num(groups.iter().copied()).f();
        if raw <= 0.0 {
            result.push((w, 1.0));
            continue;
        }
        let sum = crate::pyfmt::py_sum(groups.iter().map(|d| spread_worth(t, &spread, d.f(), k)));
        result.push((w, sum / raw));
    }
    result
}
