// Translated from INTEGRATION__equipment_systems.py (session 22). Stage 4 part: the pieces damage resolution calls
// (HarJel, Blue Shield, name helpers, system_live). The rest (MASC, ECM, stealth, heat equipment) comes with stage 5.
use std::collections::HashSet;

use crate::battle::{Battle, UnitId};
use crate::equipment::{ItemId, Slot};
use crate::mech_state::Mech;
use crate::pyfmt::{py_max, Num};

pub const HARJEL_BREACH_BONUS: i64 = 2;
pub const PFD_EXPLOSION: i64 = 5;

pub fn norm(name: &str) -> String {
    name.replace(' ', "").replace('-', "").to_uppercase()
}

pub fn destroyed_ids(mech: &Mech) -> HashSet<ItemId> {
    mech.destroyed_slot_info.values().filter_map(|i| i.instance_id).collect()
}

pub fn has_system(mech: &Mech, kind: &str) -> bool {
    mech.equipment_systems.get(kind).map_or(false, |v| !v.is_empty())
}

/// True if the mech mounts `kind` and none of its slots is destroyed.
pub fn system_live(mech: &Mech, kind: &str) -> bool {
    match mech.equipment_systems.get(kind) {
        Some(parts) if !parts.is_empty() => {
            let dead = destroyed_ids(mech);
            !parts.iter().any(|p| dead.contains(p))
        }
        _ => false,
    }
}

/// 1, 2 or 3 for a working HarJel (I / II / III) in `location`, else 0.
pub fn harjel_kind(mech: &Mech, location: &str) -> i64 {
    let mut best = 0;
    for s in mech.crits.get(location).into_iter().flatten() {
        if let Slot::Item(id) = s {
            let n = norm(&mech.items[*id].name);
            if n.contains("HARJEL") {
                best = best.max(if n.contains("HARJELIII") { 3 } else if n.contains("HARJELII") { 2 } else { 1 });
            }
        }
    }
    best
}

fn armor_total(mech: &Mech, location: &str) -> Num {
    let v = &mech.locations[location];
    v.armor + v.rear_armor.unwrap_or(Num::I(0))
}

/// (skip the breach check?, bonus to the roll) for an underwater location that took damage.
pub fn harjel_breach_check(mech: &Mech, location: &str) -> (bool, i64) {
    let kind = harjel_kind(mech, location);
    if kind == 0 || armor_total(mech, location) <= Num::I(0) {
        return (false, 0);
    }
    if kind == 1 {
        (true, 0)
    } else {
        (false, HARJEL_BREACH_BONUS)
    }
}

/// A critical hit to a HarJel slot (p.208).
pub fn harjel_hit(b: &mut Battle, u: UnitId, location: &str, slot: ItemId) {
    let name = b.units[u].items[slot].name.clone();
    if norm(&name).contains("HARJELII") {
        b.log(format!("      {} hit: gel leak - an immediate extra critical-hit check at {} (p.208).", name, location));
        crate::damage_resolution::check_critical(b, u, location, false, 0);
    } else {
        b.log(format!("      {} hit: gel leak - {} counts as breached (p.208).", name, location));
        crate::water::breach(b, u, location);
    }
}

/// A critical hit to a Blue Shield slot (p.207): while on, a 5-point component explosion and the PFD is off for good.
pub fn blue_shield_hit(b: &mut Battle, u: UnitId, location: &str, slot: ItemId) {
    if !b.units[u].pfd_active || b.units[u].pfd_failed || b.units[u].shutdown {
        return;
    }
    b.units[u].pfd_failed = true;
    b.units[u].pfd_active = false;
    b.units[u].items[slot].explosion_damage = PFD_EXPLOSION;
    b.log(format!("      Blue Shield hit while active: a {}-point explosion (p.207).", PFD_EXPLOSION));
    crate::damage_resolution::apply_explosion(b, u, slot, location);
}

pub fn _unused(_: Num) -> Num {
    py_max(Num::I(0), Num::I(0))
}
