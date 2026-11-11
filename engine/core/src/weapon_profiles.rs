// Translated from INTEGRATION__weapon_profiles.py (session 22): weapons whose damage / Cluster column / heat is not
// one fixed number in equipment.json.
use crate::battle::{Battle, UnitId};
use crate::equipment::{ItemId, Slot};
use crate::weapon_rules::canonical_name;

pub const HEAVY_GAUSS_DAMAGE: [(&str, i64); 3] = [("short", 25), ("medium", 20), ("long", 10)];
pub const HAG_GROUPING: i64 = 5;
pub const MGA_CLUSTER: i64 = 2;
pub const MGA_MAX_GUNS: usize = 4;
pub const RIFLE_VS_MECH: i64 = -3;
pub const ARROW_DAMAGE: i64 = 20;
pub const ARROW_SPLASH: i64 = 10;
pub const ARROW_TN: i64 = 4;
pub const HOMING_AE: i64 = 5;
pub const HOMING_TN: i64 = 4;
pub const HOMING_REACH: i64 = 17;
pub const ARROW_RANGE: (i64, i64) = (7, 17);
pub const AREA_GROUPING: i64 = 5;
pub const OUTSIDE_HEAT_CAP: i64 = 15;

/// {bracket: damage} for a variable-damage weapon.
pub fn variable_damage(b: &mut Battle, u: UnitId, w: ItemId) -> Option<[(&'static str, i64); 3]> {
    let n = canonical_name(b, u, w);
    if is_heavy_gauss(b, u, w) {
        return Some(HEAVY_GAUSS_DAMAGE);
    }
    for (frag, table) in [
        ("SMALLVSP", [("short", 5), ("medium", 4), ("long", 3)]),
        ("MEDIUMVSP", [("short", 9), ("medium", 7), ("long", 5)]),
        ("LARGEVSP", [("short", 11), ("medium", 9), ("long", 7)]),
        ("SNPPC", [("short", 10), ("medium", 8), ("long", 5)]),
    ] {
        if n.contains(frag) {
            return Some(table);
        }
    }
    None
}

/// Bombast laser: kind -> (damage, TN, heat).
pub fn bombast(kind: &str) -> (i64, i64, i64) {
    match kind {
        "8" => (8, 0, 6),
        "12" => (12, 1, 9),
        "16" => (16, 2, 12),
        other => panic!("KeyError: {}", other),
    }
}

pub const BOMBAST_KINDS: [&str; 3] = ["8", "12", "16"];

pub fn hag_cluster_by_bracket(bracket: &str) -> i64 {
    match bracket {
        "short" => 2,
        "medium" => 0,
        "long" => -2,
        other => panic!("KeyError: {}", other),
    }
}

pub fn mpod_column_by_bracket(bracket: &str) -> i64 {
    match bracket {
        "short" => 15,
        "medium" => 10,
        "long" => 5,
        other => panic!("KeyError: {}", other),
    }
}

pub fn is_heavy_gauss(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    let n = canonical_name(b, u, w);
    n.contains("HEAVYGAUSS") && !n.contains("IMPROVED")
}

pub fn is_hag(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    canonical_name(b, u, w).starts_with("CLHAG")
}

/// The first run of digits in the canonical name.
pub fn hag_size(b: &mut Battle, u: UnitId, w: ItemId) -> i64 {
    let n = canonical_name(b, u, w);
    let digits: String = n.chars().skip_while(|c| !c.is_ascii_digit()).take_while(|c| c.is_ascii_digit()).collect();
    digits.parse().expect("digits in a HAG name")
}

pub fn is_mpod(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    canonical_name(b, u, w).contains("MPOD")
}

pub fn is_infantry_pod(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    let n = canonical_name(b, u, w);
    n.contains("APOD") || n.contains("BPOD")
}

pub fn is_mga(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    let n = canonical_name(b, u, w);
    n.ends_with("MGA") || n.contains("MACHINEGUNARRAY")
}

pub fn is_bombast(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    canonical_name(b, u, w).contains("BOMBAST")
}

pub fn is_rifle(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    let n = canonical_name(b, u, w);
    n.ends_with("RIFLE") && !["GAUSS", "PLASMA"].iter().any(|k| n.contains(k))
}

/// "ARROWIV" / "SNIPER" / "THUMPER" for a weapon fired by the Arrow IV rules, else None.
pub fn artillery_kind(b: &mut Battle, u: UnitId, w: ItemId) -> Option<&'static str> {
    let n = canonical_name(b, u, w);
    if n.contains("ARROWIV") {
        return Some("ARROWIV");
    }
    [("SNIPER", "SNIPERARTILLERY"), ("THUMPER", "THUMPERARTILLERY")].into_iter().find(|(k, long)| n.ends_with(k) || n.ends_with(long)).map(|(k, _)| k)
}

pub fn is_arrow(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    artillery_kind(b, u, w).is_some()
}

fn artillery_profile(kind: &str) -> (i64, i64) {
    match kind {
        "ARROWIV" => (ARROW_DAMAGE, ARROW_SPLASH),
        "SNIPER" => (20, 10),
        "THUMPER" => (15, 5),
        other => panic!("KeyError: {}", other),
    }
}

pub fn arrow_damage(b: &mut Battle, u: UnitId, w: ItemId) -> i64 {
    artillery_profile(artillery_kind(b, u, w).expect("an arrow weapon")).0
}

pub fn homing_damage(b: &mut Battle, u: UnitId, w: ItemId) -> i64 {
    match artillery_kind(b, u, w).expect("an arrow weapon") {
        "ARROWIV" => 20,
        "SNIPER" => 10,
        _ => 5,
    }
}

pub fn is_art_cannon(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    let n = canonical_name(b, u, w);
    n.ends_with("CANNON") && ["THUMPER", "SNIPER", "LONGTOM"].iter().any(|k| n.contains(k))
}

/// Damage to the hexes next to where an area-effect shell lands.
pub fn splash(b: &mut Battle, u: UnitId, w: ItemId) -> i64 {
    if let Some(k) = artillery_kind(b, u, w) {
        return artillery_profile(k).1;
    }
    if canonical_name(b, u, w).contains("LONGTOMCANNON") {
        10
    } else {
        0
    }
}

/// Heat a hit puts on the target (outside heat), or 0. `roll_d6(n)` rolls nD6.
pub fn target_heat(b: &mut Battle, u: UnitId, w: ItemId, roll_d6: &mut dyn FnMut(&mut Battle, i64) -> i64) -> i64 {
    let n = canonical_name(b, u, w);
    if n.contains("FLAMER") {
        return if n.contains("ERFLAMER") { 1 } else { b.units[u].items[w].damage_per_shot.unwrap_or(0) };
    }
    if n.contains("PLASMACANNON") {
        return roll_d6(b, 2);
    }
    if n.contains("PLASMARIFLE") {
        if n.contains("HEAVY") {
            return roll_d6(b, 2);
        }
        if n.contains("LIGHT") {
            return crate::pyfmt::py_floordiv(roll_d6(b, 1) + 1, 2);
        }
        return roll_d6(b, 1);
    }
    0
}

/// Average heat a hit puts on the target.
pub fn expected_target_heat(b: &mut Battle, u: UnitId, w: ItemId) -> f64 {
    let n = canonical_name(b, u, w);
    if n.contains("FLAMER") {
        return if n.contains("ERFLAMER") { 1.0 } else { b.units[u].items[w].damage_per_shot.unwrap_or(0) as f64 };
    }
    if n.contains("PLASMACANNON") || (n.contains("PLASMARIFLE") && n.contains("HEAVY")) {
        return 7.0;
    }
    if n.contains("PLASMARIFLE") {
        return if n.contains("LIGHT") { 2.0 } else { 3.5 };
    }
    0.0
}

pub fn heat_causing(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    expected_target_heat(b, u, w) > 0.0
}

/// The live machine guns `array` fires.
pub fn mga_guns(b: &Battle, u: UnitId, array: ItemId) -> Vec<ItemId> {
    let live = crate::damage_resolution::get_weapons(&b.units[u]);
    b.units[u].items[array].mga_guns.clone().unwrap_or_default().into_iter().filter(|g| live.contains(g)).collect()
}

/// Once per battle: each machine gun array takes up to 4 machine guns of its type in its own location.
pub fn link_arrays(b: &mut Battle, u: UnitId) {
    let mut seen: Vec<ItemId> = Vec::new();
    let locs: Vec<String> = b.units[u].crits.keys().cloned().collect();
    for loc in locs {
        let mut arrays: Vec<ItemId> = Vec::new();
        let mut guns: Vec<ItemId> = Vec::new();
        for s in b.units[u].crits[&loc].clone() {
            let id = match s {
                Slot::Item(id) => id,
                _ => continue,
            };
            if b.units[u].items[id].category.as_deref() != Some("weapon") || seen.contains(&id) {
                continue;
            }
            seen.push(id);
            if is_mga(b, u, id) {
                arrays.push(id);
            } else {
                let n = canonical_name(b, u, id);
                if n.contains("MACHINEGUN") || n.ends_with("MG") {
                    guns.push(id);
                }
            }
        }
        for a in arrays {
            let an = canonical_name(b, u, a);
            let kind = if an.contains("LIGHT") || an.contains("LMGA") {
                "LIGHT"
            } else if an.contains("HEAVY") || an.contains("HMGA") {
                "HEAVY"
            } else {
                ""
            };
            let mut mine: Vec<ItemId> = Vec::new();
            for g in &guns {
                let gn = canonical_name(b, u, *g);
                if gn.contains(kind) && !(kind.is_empty() && (gn.contains("LIGHT") || gn.contains("HEAVY"))) {
                    mine.push(*g);
                }
            }
            mine.truncate(MGA_MAX_GUNS);
            b.units[u].items[a].mga_guns = Some(mine.clone());
            guns.retain(|g| !mine.contains(g));
        }
    }
}

/// Machine guns fired by a live array (they can't fire on their own).
pub fn array_gun_ids(b: &mut Battle, u: UnitId) -> Vec<ItemId> {
    let mut out: Vec<ItemId> = Vec::new();
    for w in crate::damage_resolution::get_weapons(&b.units[u]) {
        if is_mga(b, u, w) {
            for g in b.units[u].items[w].mga_guns.clone().unwrap_or_default() {
                if !out.contains(&g) {
                    out.push(g);
                }
            }
        }
    }
    out
}
