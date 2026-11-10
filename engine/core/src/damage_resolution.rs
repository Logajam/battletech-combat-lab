// Translated from mechsim/damage_resolution.py (session 22). Stage 3 needs only the weapon scan; the rest is stage 4.
use std::collections::HashSet;

use crate::equipment::{ItemId, Slot};
use crate::mech_state::Mech;

/// Every live weapon Equipment on this mech right now, deduplicated by instance (a multi-slot weapon appears once) and
/// minus any instance one of whose slots was hit (`destroyed_slot_info`). No cache (speed only, stage 9).
pub fn get_weapons(mech: &Mech) -> Vec<ItemId> {
    let destroyed_ids: HashSet<ItemId> = mech.destroyed_slot_info.values().filter_map(|i| i.instance_id).collect();
    let mut seen: HashSet<ItemId> = HashSet::new();
    let mut weapons = Vec::new();
    for slots in mech.crits.values() {
        for slot in slots {
            let id = match slot {
                Slot::Item(id) => *id,
                _ => continue,
            };
            if mech.items[id].category.as_deref() != Some("weapon") {
                continue;
            }
            if !seen.insert(id) {
                continue;
            }
            if destroyed_ids.contains(&id) {
                continue;
            }
            weapons.push(id);
        }
    }
    weapons
}

/// Is this Equipment a partial wing (normalized-name match)?
pub fn is_partial_wing(mech: &Mech, id: ItemId) -> bool {
    mech.items[id].name.replace(' ', "").replace('-', "").to_uppercase().contains("PARTIALWING")
}
