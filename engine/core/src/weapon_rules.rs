// Translated from INTEGRATION__weapon_rules.py (session 22): per-weapon special rules keyed off the weapon's name.
use crate::battle::{Battle, UnitId};
use crate::equipment::{is_torpedo_name, ItemId};
use crate::pyfmt::Num;

pub const DEFAULT_GROUPING: i64 = 5;
const GROUPING_BY_FAMILY: [(&str, i64); 7] = [("ATM", 6), ("SRM", 2), ("LRM", 5), ("SRT", 2), ("LRT", 5), ("MRM", 5), ("MORTAR", 2)];

fn norm(name: &str) -> String {
    name.replace(' ', "").replace('-', "").to_uppercase()
}

fn wnorm(b: &Battle, u: UnitId, w: ItemId) -> String {
    norm(&b.units[u].items[w].name)
}

/// Rolls on the Cluster Hits Table: a missile weapon with a rack size.
pub fn is_cluster(b: &Battle, u: UnitId, w: ItemId) -> bool {
    let e = &b.units[u].items[w];
    e.damage_type.as_deref() == Some("Missile") && e.rack_size.is_some()
}

/// Streak launchers - and the iATM.
pub fn is_streak(b: &Battle, u: UnitId, w: ItemId) -> bool {
    let n = wnorm(b, u, w);
    n.contains("STREAK") || n.contains("IATM")
}

pub fn grouping_size(b: &Battle, u: UnitId, w: ItemId) -> i64 {
    let n = wnorm(b, u, w);
    GROUPING_BY_FAMILY.iter().find(|(f, _)| n.contains(f)).map_or(DEFAULT_GROUPING, |(_, s)| *s)
}

pub fn cluster_roll_modifier(b: &Battle, u: UnitId, w: ItemId) -> i64 {
    let n = wnorm(b, u, w);
    if n.contains("MRM") { -1 } else { 0 }
}

/// Split a cluster hit's damage into groupings (p.87): full groups, leftover last.
pub fn damage_groupings(b: &Battle, u: UnitId, w: ItemId, total_damage: Num) -> Vec<Num> {
    let size = grouping_size(b, u, w);
    let full = total_damage.floordiv(Num::I(size));
    let n_groups = match full {
        Num::I(i) => i,
        Num::F(f) => f as i64,
    };
    let mut groups: Vec<Num> = (0..n_groups).map(|_| Num::I(size)).collect();
    let leftover = total_damage - Num::I(size * n_groups);
    if leftover > Num::I(0) {
        groups.push(leftover);
    }
    groups
}

/// equipment.json canonical name for a weapon instance (cached on it, as the Python caches `_canonical`).
pub fn canonical_name(b: &mut Battle, u: UnitId, w: ItemId) -> String {
    if let Some(c) = &b.units[u].items[w].canonical {
        return c.clone();
    }
    let name = b.units[u].items[w].name.clone();
    let c = match b.db.lookup_equipment(&name) {
        Some(entry) => entry.canonical_name().to_string(),
        None => name,
    };
    let cached = norm(&c);
    b.units[u].items[w].canonical = Some(cached.clone());
    cached
}

pub fn vsp_modifier(bracket: Option<&str>) -> i64 {
    match bracket {
        Some("short") => -3,
        Some("medium") => -2,
        Some("long") => -1,
        _ => 0,
    }
}

/// The weapon's own to-hit modifier (p.185 lasers, p.184 silver bullet, p.187 rockets, p.189 M-pods).
pub fn weapon_tn_modifier(b: &mut Battle, u: UnitId, w: ItemId, bracket: Option<&str>) -> i64 {
    let n = canonical_name(b, u, w);
    if n.contains("VSP") {
        return vsp_modifier(bracket);
    }
    if n.contains("XPULSE") {
        return -2;
    }
    if n.contains("PULSE") {
        return if n.starts_with("CLER") || n.starts_with("ISER") || n.starts_with("ER") { -1 } else { -2 };
    }
    if n.contains("HEAVY") && n.contains("LASER") {
        return if n.contains("IMPROVED") { 0 } else { 1 };
    }
    if n.contains("REENGINEERED") || n.contains("RELASER") {
        return -1;
    }
    if n.contains("SBGR") || n.contains("SILVERBULLET") {
        return -1;
    }
    if n.starts_with("RL") || n.contains("ROCKETLAUNCHER") {
        return 1;
    }
    if n.contains("MPOD") {
        return -1;
    }
    if n.contains("MORTAR") {
        return 3;
    }
    if n.contains("TASER") {
        return 1;
    }
    0
}

/// p.200: direct-fire ballistic/energy and pulse weapons, but not cluster weapons, flamers or machine guns.
pub fn targeting_computer_eligible(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    let dt = b.units[u].items[w].damage_type.clone();
    if is_cluster(b, u, w) || !matches!(dt.as_deref(), Some("Energy") | Some("Ballistic")) {
        return false;
    }
    let n = canonical_name(b, u, w);
    if n.contains("TASER") {
        return false;
    }
    !["FLAMER", "MACHINEGUN", "MGA", "LIGHTMG", "HEAVYMG"].iter().any(|k| n.contains(k)) && !n.ends_with("MG")
}

pub fn is_pulse(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    canonical_name(b, u, w).contains("PULSE")
}

pub fn is_ams(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    let n = canonical_name(b, u, w);
    n.contains("ANTIMISSILESYSTEM") || n.contains("APDS")
}

pub fn is_apds(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    canonical_name(b, u, w).contains("APDS")
}

/// A torpedo launcher (p.187); cached by ammo.attach_ammo as `.torpedo`.
pub fn is_torpedo(m: &crate::mech_state::Mech, w: ItemId) -> bool {
    match m.items[w].torpedo {
        Some(t) => t,
        None => is_torpedo_name(&m.items[w].name),
    }
}
