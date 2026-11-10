// Translated from INTEGRATION__advanced_equipment.py (session 22): TO:AUE modular armor.
use crate::battle::{Battle, UnitId};
use crate::equipment::{ItemId, Slot};
use crate::pyfmt::{py_min, Num};

pub const MODULAR_POINTS: i64 = 10;

pub fn is_modular_armor(b: &Battle, u: UnitId, id: ItemId) -> bool {
    b.units[u].items[id].name.replace(' ', "").to_uppercase().contains("MODULARARMOR")
}

/// Once per battle (fresh clone): fill each Modular Armor slot.
pub fn attach(b: &mut Battle, u: UnitId) {
    b.units[u].modular_armor = Vec::new();
    let mut seen: Vec<ItemId> = Vec::new();
    let locs: Vec<String> = b.units[u].crits.keys().cloned().collect();
    for loc in locs {
        for s in b.units[u].crits[&loc].clone() {
            if let Slot::Item(id) = s {
                if is_modular_armor(b, u, id) && !seen.contains(&id) {
                    seen.push(id);
                    let rear = b.units[u].items[id].rear_mounted;
                    let it = &mut b.units[u].items[id];
                    it.modular_points = Some(MODULAR_POINTS);
                    it.modular_location = Some(loc.clone());
                    it.modular_field = Some(if rear { "rear_armor" } else { "armor" }.to_string());
                    b.units[u].modular_armor.push(id);
                }
            }
        }
    }
}

/// Any modular armor point left.
pub fn active(b: &Battle, u: UnitId) -> bool {
    b.units[u].modular_armor.iter().any(|id| b.units[u].items[*id].modular_points.unwrap_or(0) > 0)
}

/// Modular armor on `location`'s `armor_field` takes `damage` first; returns what is left.
pub fn absorb(b: &mut Battle, u: UnitId, location: &str, armor_field: &str, damage: Num) -> Num {
    let list = b.units[u].modular_armor.clone();
    for id in list {
        let it = &b.units[u].items[id];
        if it.modular_location.as_deref() == Some(location) && it.modular_field.as_deref() == Some(armor_field) && it.modular_points.unwrap_or(0) > 0 {
            let points = it.modular_points.unwrap();
            let taken = py_min(damage, Num::I(points));
            let left = Num::I(points) - taken;
            // modular_points stays an int in the Python only while `taken` is: min(damage, points) of a float damage is a float
            b.units[u].items[id].modular_points = Some(left.as_int_or_trunc());
            let side = if armor_field == "rear_armor" { " (rear)" } else { "" };
            b.log(format!("  Modular armor on {}{} takes {} ({} left; TO:AUE p.93).", location, side, taken.py_str(), left.py_str()));
            if left == Num::I(0) && !active(b, u) {
                let name = b.units[u].side_name.clone().unwrap_or_default();
                b.log(format!("  {}'s last modular armor is gone - its penalties end (TO:AUE p.93).", name));
            }
            return damage - taken;
        }
    }
    damage
}

/// A critical hit on a Modular Armor slot destroys all its points (p.93).
pub fn slot_hit(b: &mut Battle, u: UnitId, id: ItemId) {
    let pts = b.units[u].items[id].modular_points.unwrap_or(0);
    if pts > 0 {
        b.log(format!("      Modular armor slot hit - its {} points are destroyed (TO:AUE p.93).", pts));
        b.units[u].items[id].modular_points = Some(0);
    }
}
