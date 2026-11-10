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

pub fn tmm_from_mp(mp: i64) -> i64 {
    if mp <= 2 {
        0
    } else if mp <= 4 {
        1
    } else if mp <= 6 {
        2
    } else if mp <= 9 {
        3
    } else if mp <= 17 {
        4
    } else {
        5
    }
}

/// TMM: the higher of the Running-MP value or the Jump-MP value (+1) this turn (also jump booster); records the
/// winning movement mode on the mech.
pub fn compute_tmm(mech: &mut Mech) -> i64 {
    use crate::mech_state::*;
    let running_mp = compute_running_mp(mech);
    let mut tmm = tmm_from_mp(running_mp);
    mech.movement_mode_this_turn = "running".to_string();
    let jump_mp = compute_jump_mp(mech);
    if jump_mp > 0 {
        let jump_tmm = tmm_from_mp(jump_mp) + 1;
        if jump_tmm > tmm {
            tmm = jump_tmm;
            mech.movement_mode_this_turn = "jump".to_string();
        }
    }
    if mech.base_mechanical_jump_booster_mp > 0 {
        let booster_mp = compute_mechanical_jump_booster_mp(mech);
        if booster_mp > 0 {
            let booster_tmm = tmm_from_mp(booster_mp) + 1;
            if booster_tmm > tmm {
                tmm = booster_tmm;
                mech.movement_mode_this_turn = "jump".to_string();
            }
        }
    }
    tmm
}
