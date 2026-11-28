// Translated from mechsim/damage_resolution.py (session 22).
//! "What happens TO a mech": damage application, critical hit resolution and explosions. Everything takes the battle
//! and a unit (`b.units[u]`); caches (get_weapons, derived) are speed only and come back in stage 9.


use crate::armor_rules;
use crate::battle::{Battle, UnitId};
use crate::equipment::{is_crit_target, ItemId, Slot};
use crate::mech_state::*;
use crate::pyfmt::{py_max, py_min, Num};

pub const LEG_ACTUATOR_NAMES: [&str; 4] = ["Hip", "Upper Leg Actuator", "Lower Leg Actuator", "Foot Actuator"];

fn norm_name(name: &str) -> String {
    name.replace(' ', "").replace('-', "").to_uppercase()
}

/// Every live weapon Equipment on this mech right now (a multi-slot weapon once; minus any instance one of whose slots
/// was hit).
pub fn get_weapons(mech: &Mech) -> Vec<ItemId> {
    // seen / destroyed as one flag per item (the Python's two sets of ids), so nothing is hashed
    let mut skip = vec![false; mech.items.len()];
    for info in mech.destroyed_slot_info.values() {
        if let Some(id) = info.instance_id {
            skip[id] = true;
        }
    }
    let mut weapons = Vec::new();
    for slots in mech.crits.values() {
        for slot in slots {
            let id = match slot {
                Slot::Item(id) => *id,
                _ => continue,
            };
            if skip[id] || mech.items[id].category.as_deref() != Some("weapon") {
                continue;
            }
            skip[id] = true;
            weapons.push(id);
        }
    }
    weapons
}

pub fn is_jump_jet(mech: &Mech, id: ItemId) -> bool {
    norm_name(&mech.items[id].name).contains("JUMPJET")
}
pub fn is_mechanical_jump_booster(mech: &Mech, id: ItemId) -> bool {
    norm_name(&mech.items[id].name).contains("MECHANICALJUMPBOOSTER")
}
pub fn is_partial_wing(mech: &Mech, id: ItemId) -> bool {
    norm_name(&mech.items[id].name).contains("PARTIALWING")
}
pub fn is_heat_sink(mech: &Mech, id: ItemId) -> bool {
    let n = norm_name(&mech.items[id].name);
    n.contains("HEATSINK") && !n.contains("RADICAL")
}
pub fn heat_sink_units(mech: &Mech, id: ItemId) -> i64 {
    if norm_name(&mech.items[id].name).contains("2COMPACT") {
        2
    } else {
        1
    }
}

/// `_AUTOCANNON_NAME` on the name with "(...)" groups, spaces, hyphens and slashes removed, upper-cased.
pub fn is_autocannon(mech: &Mech, id: ItemId) -> bool {
    let name = &mech.items[id].name;
    let mut s = String::new();
    let chars: Vec<char> = name.chars().collect();
    let mut i = 0;
    while i < chars.len() {
        if chars[i] == '(' {
            if let Some(close) = chars[i + 1..].iter().position(|c| *c == ')') {
                i += close + 2;
                continue;
            }
        }
        if !(chars[i].is_whitespace() || chars[i] == '-' || chars[i] == '/') {
            s.push(chars[i]);
        }
        i += 1;
    }
    let s = s.to_uppercase();
    let digits_tail = |rest: &str| -> bool {
        let n = rest.chars().take_while(|c| c.is_ascii_digit()).count();
        n > 0 && matches!(&rest[n..], "" | "P")
    };
    for prefix in ["IS", "CL", "CLAN", ""] {
        if let Some(r) = s.strip_prefix(prefix) {
            for kind in ["LBX", "ULTRA", "ROTARY", "PROTOMECH", "LIGHT", "L", ""] {
                if let Some(r2) = r.strip_prefix(kind) {
                    if let Some(r3) = r2.strip_prefix("AC") {
                        if digits_tail(r3) {
                            return true;
                        }
                    }
                }
            }
            if let Some(r2) = r.strip_prefix("AUTOCANNON") {
                if digits_tail(r2) {
                    return true;
                }
            }
            if let Some(r2) = r.strip_prefix("LB") {
                let n = r2.chars().take_while(|c| c.is_ascii_digit()).count();
                if n > 0 && &r2[n..] == "XAC" {
                    return true;
                }
            }
        }
    }
    false
}

pub fn transfer_map(loc: &str) -> Option<&'static str> {
    Some(match loc {
        "Left Arm" => "Left Torso",
        "Right Arm" => "Right Torso",
        "Left Leg" => "Left Torso",
        "Right Leg" => "Right Torso",
        "Center Leg" => "Center Torso",
        "Left Torso" => "Center Torso",
        "Right Torso" => "Center Torso",
        "Front Left Leg" => "Left Torso",
        "Front Right Leg" => "Right Torso",
        "Rear Left Leg" => "Left Torso",
        "Rear Right Leg" => "Right Torso",
        _ => return None,
    })
}

pub const NON_TORSO_LOCATIONS: [&str; 10] = [
    "Head", "Left Arm", "Right Arm", "Left Leg", "Right Leg", "Center Leg", "Front Left Leg", "Front Right Leg", "Rear Left Leg", "Rear Right Leg",
];

/// Number of shots that connect, from config.CLUSTER_HITS_TABLE (roll row, shots column).
pub fn cluster_hits_count(b: &Battle, shots: i64, roll: i64) -> Result<i64, String> {
    if let Some(hits) = b.cfg.cluster_hits(roll, shots) {
        return Ok(hits);
    }
    // not in the table (or not a number): the text lookup below words the error
    let table = b.cfg.get("CLUSTER_HITS_TABLE").as_object().unwrap();
    let row = match table.get(&roll.to_string()) {
        Some(r) => r.as_object().unwrap(),
        None => {
            let mut keys: Vec<i64> = table.keys().map(|k| k.parse().unwrap()).collect();
            keys.sort();
            return Err(format!("No Cluster Hits Table row for a roll of {} - table only covers rolls {}.", roll, int_list(&keys)));
        }
    };
    match row.get(&shots.to_string()) {
        Some(v) => Ok(v.as_i64().unwrap()),
        None => {
            let mut keys: Vec<i64> = row.keys().map(|k| k.parse().unwrap()).collect();
            keys.sort();
            Err(format!("No Cluster Hits Table column for {} shots - table only covers {} shot-columns. Extend config.CLUSTER_HITS_TABLE rather than guessing.", shots, int_list(&keys)))
        }
    }
}

fn int_list(v: &[i64]) -> String {
    format!("[{}]", v.iter().map(|n| n.to_string()).collect::<Vec<_>>().join(", "))
}

/// `(loc, i) in breached_slots(mech)`: the Python's accessor creates the (empty) set on first use, so does this.
fn breached_slots_contains(m: &mut Mech, loc: &str, i: usize) -> bool {
    m.breached_slot_set.get_or_insert_with(Default::default).contains(&(loc.to_string(), i))
}

/// What a slot was, for destroyed_slot_info: (name, instance id).
fn slot_identity(m: &Mech, slot: &Slot) -> SlotInfo {
    match slot {
        Slot::Item(id) => SlotInfo { name: m.items[*id].name.clone(), instance_id: Some(*id) },
        Slot::Name(n) => SlotInfo { name: n.clone(), instance_id: None },
    }
}

/// Mark slots destroyed and count special components (a bulk "location destroyed" pass).
pub fn mark_all_crits_destroyed(b: &mut Battle, u: UnitId, location: &str) {
    if !b.units[u].crits.contains_key(location) {
        return;
    }
    let n = b.units[u].crits[location].len();
    for i in 0..n {
        let slot = b.units[u].crits[location][i].clone();
        if slot.is_name("DESTROYED") || slot.is_name("-Empty-") {
            continue;
        }
        let already_lost = breached_slots_contains(&mut b.units[u], location, i);
        let info = slot_identity(&b.units[u], &slot);
        b.units[u].destroyed_slot_info.insert((location.to_string(), i), info);
        b.units[u].crits.get_mut(location).unwrap()[i] = Slot::name("DESTROYED");
        if !already_lost {
            slot_loss_effects(b, u, location, &slot, "destruction", false);
        }
    }
    b.log(format!("  All critical slots in {} marked DESTROYED.", location));
    b.ev("LOCATION_DESTROYED").unit(u).loc(location).emit(b);
}

/// A slot destroyed by a hit resolved elsewhere (the MegaMek bridge: MegaMek rolled the critical hit and applied its
/// damage): marked DESTROYED with its loss effects (engine, gyro, cockpit, hip, jump jet, heat sink...), but no ammo
/// explosion and no dice - that already happened in the other engine. A slot already destroyed is left alone.
pub fn destroy_slot_quietly(b: &mut Battle, u: UnitId, location: &str, i: usize) {
    let Some(slot) = b.units[u].crits.get(location).and_then(|l| l.get(i)).cloned() else { return };
    if slot.is_name("DESTROYED") || slot.is_name("-Empty-") {
        return;
    }
    let info = slot_identity(&b.units[u], &slot);
    b.units[u].destroyed_slot_info.insert((location.to_string(), i), info);
    b.units[u].crits.get_mut(location).unwrap()[i] = Slot::name("DESTROYED");
    slot_loss_effects(b, u, location, &slot, "a critical hit (MegaMek)", true);
}

/// Hull breach (Core p.127): every slot's effects applied once, the slots stay in the crit table.
pub fn mark_location_nonfunctional(b: &mut Battle, u: UnitId, location: &str, why: &str) {
    if !b.units[u].crits.contains_key(location) {
        return;
    }
    let n = b.units[u].crits[location].len();
    for i in 0..n {
        let slot = b.units[u].crits[location][i].clone();
        if slot.is_name("DESTROYED") || slot.is_name("-Empty-") || breached_slots_contains(&mut b.units[u], location, i) {
            continue;
        }
        let info = slot_identity(&b.units[u], &slot);
        b.units[u].destroyed_slot_info.insert((location.to_string(), i), info);
        b.units[u].breached_slot_set.get_or_insert_with(Default::default).insert((location.to_string(), i));
        slot_loss_effects(b, u, location, &slot, why, false);
    }
}

/// `leg_actuators`: also count a lost leg actuator against walking MP, as a critical hit does - for a single slot lost by a
/// critical hit elsewhere (the MegaMek bridge's mirror); a destroyed or breached location keeps its old effects only.
fn slot_loss_effects(b: &mut Battle, u: UnitId, location: &str, slot: &Slot, why: &str, leg_actuators: bool) {
    match slot {
        Slot::Item(id) => {
            let id = *id;
            let name = b.units[u].items[id].name.clone();
            if is_jump_jet(&b.units[u], id) && !b.units[u].destroyed_jump_jet_ids.contains(&id) {
                b.units[u].destroyed_jump_jet_ids.insert(id);
                let now = compute_jump_mp(&b.units[u]);
                b.log(format!("    Jump jet destroyed ({}) from {} {} - jump MP reduced (now {}).", name, location, why, now));
            }
            if is_heat_sink(&b.units[u], id) && !b.units[u].destroyed_heat_sinks.contains_key(&id) {
                let units = heat_sink_units(&b.units[u], id);
                b.units[u].destroyed_heat_sinks.insert(id, units);
                let now = compute_heat_dissipation(&b.units[u]);
                b.log(format!("    Heat sink destroyed ({}) from {} {} - heat dissipation reduced (now {}).", name, location, why, now));
            }
            if is_mechanical_jump_booster(&b.units[u], id) && !b.units[u].mechanical_jump_booster_disabled {
                b.units[u].mechanical_jump_booster_disabled = true;
                let now = compute_mechanical_jump_booster_mp(&b.units[u]);
                b.log(format!("    Mechanical Jump Booster disabled (system-wide) from {} {} - jump booster MP now {}.", location, why, now));
            }
            if is_partial_wing(&b.units[u], id) && b.units[u].partial_wing_active {
                b.units[u].partial_wing_active = false;
                let now = compute_jump_mp(&b.units[u]);
                b.log(format!("    Partial Wing disabled (system-wide) from {} {} - jump MP now {}.", location, why, now));
            }
        }
        Slot::Name(n) => {
            if n == "Engine" {
                b.units[u].engine_hits += 1;
                let (h, t) = (b.units[u].engine_hits, engine_hits_to_destroy(&b.units[u]));
                b.log(format!("    Engine hit ({}/{}) from {} {}.", h, t, location, why));
            } else if n == "Gyro" {
                b.units[u].gyro_hits += 1;
                let (h, t) = (b.units[u].gyro_hits, if has_hd_gyro(&b.units[u]) { 4 } else { 2 });
                b.log(format!("    Gyro hit ({}/{}) from {} {}.", h, t, location, why));
            } else if n == "Cockpit" {
                b.units[u].cockpit_hit = true;
                b.log(format!("    Cockpit destroyed from {} {}.", location, why));
            } else if leg_actuators && LEG_ACTUATOR_NAMES.contains(&n.as_str()) && b.units[u].leg_locations.iter().any(|l| l == location) {
                // a leg actuator lost costs walking MP, as in a battle of our own (the critical-hit path above);
                // session 30: the copy kept only the hip's piloting-roll effect, so in MegaMek games our bots planned
                // at full MP with a hip or leg actuator gone, and MegaMek refused the run ("would not take the route")
                let c = b.units[u].destroyed_leg_actuators.get(location).copied().unwrap_or(0) + 1;
                b.units[u].destroyed_leg_actuators.insert(location.to_string(), c);
                let wmp = compute_walk_mp(&b.units[u]);
                b.log(format!("    Leg actuator lost at {} ({} there) from {} - walk MP now {}.", location, c, why, wmp));
                if n == "Hip" {
                    b.units[u].destroyed_hip_locations.insert(location.to_string());
                    b.log(format!("    Hip specifically destroyed at {} from {} {}.", location, location, why));
                }
            } else if n == "Hip" && b.units[u].leg_locations.iter().any(|l| l == location) {
                b.units[u].destroyed_hip_locations.insert(location.to_string());
                b.log(format!("    Hip specifically destroyed at {} from {} {}.", location, location, why));
            }
        }
    }
}

/// The damage grouping: armor, structure, criticals, destruction and transfer. `armor_field` "armor" / "rear_armor".
pub fn apply_damage(b: &mut Battle, u: UnitId, location: &str, damage: Num, armor_field: &str, damage_type: DamageType) {
    let mut remaining = damage;
    let mut current: Option<String> = Some(location.to_string());
    let mut current_armor_field = armor_field.to_string();
    b.log(format!("{} damage ({}) incoming to {} ({}).", damage.py_str(), damage_type.name(), location, armor_field));
    if b.log.ev.on && damage > Num::I(0) {
        let d = match damage { Num::I(i) => i as f64, Num::F(f) => f };
        let mut e = b.ev("HIT").unit(u).loc(location).sub(&damage_type.name().to_lowercase()).dmg(d);
        if let Some((a, w)) = b.log.ev.actor.clone() {
            e = e.other(a).what(&w);
        }
        e.emit(b);
    }
    while remaining > Num::I(0) && current.is_some() {
        let cur = current.clone().unwrap();
        if b.units[u].locations[cur.as_str()].destroyed {
            let nxt = transfer_map(&cur);
            b.log(format!("  {} already destroyed - damage transfers to {}.", cur, nxt.unwrap_or("nowhere (attack finished)")));
            current = nxt.map(|s| s.to_string());
            current_armor_field = "armor".to_string();
            continue;
        }
        let armor_key: String = if current_armor_field == "rear_armor" && b.units[u].locations[cur.as_str()].rear_armor.is_some() {
            current_armor_field.clone()
        } else if current_armor_field == "armor" || current_armor_field == "structure" {
            current_armor_field.clone()
        } else {
            "armor".to_string()
        };
        if !b.units[u].modular_armor.is_empty() {
            remaining = crate::advanced_equipment::absorb(b, u, &cur, &armor_key, remaining);
            if remaining <= Num::I(0) {
                return;
            }
        }
        let armor_type = if damage_type == DamageType::Reengineered { ArmorType::Standard } else { b.units[u].armor_type.get(&cur).copied().unwrap_or(ArmorType::Standard) };
        let incoming_dmg = remaining;
        let armor_pool_before = b.units[u].locations[cur.as_str()].field(&armor_key);
        let effective_dmg = armor_rules::effective_damage(armor_type, damage_type, incoming_dmg, armor_pool_before);
        let (armor_destroyed, struct_incoming) = armor_rules::consume_armor(armor_type, damage_type, effective_dmg, armor_pool_before);
        let new_armor = py_max(Num::I(0), armor_pool_before - armor_destroyed);
        b.units[u].locations.get_mut(cur.as_str()).unwrap().set_field(&armor_key, new_armor);

        let struct_before = b.units[u].locations[cur.as_str()].structure;
        let mut struct_dmg = Num::I(0);
        let mut struct_overflow = Num::I(0);
        if struct_incoming > Num::I(0) {
            let (sd, so) = armor_rules::consume_structure(b.units[u].structure_type, struct_incoming, struct_before);
            struct_dmg = sd;
            struct_overflow = so;
            b.units[u].locations.get_mut(cur.as_str()).unwrap().structure = py_max(Num::I(0), struct_before - struct_dmg);
        }
        remaining = struct_overflow;

        let reduced_note = if effective_dmg != incoming_dmg {
            format!(" (pre-armor damage reduced {} -> {})", incoming_dmg.py_str(), effective_dmg.fmt_g())
        } else {
            String::new()
        };
        let armor_after = b.units[u].locations[cur.as_str()].field(&armor_key);
        let mut msg = format!(
            "  [{}/{}]{} {} armor pts destroyed at {} ({} -> {} remaining).",
            armor_type.name(), damage_type.name(), reduced_note, armor_destroyed.fmt_g(), armor_key, armor_pool_before.fmt_g(), armor_after.fmt_g()
        );
        if struct_dmg > Num::I(0) {
            msg += &format!(
                " {} damage applied to structure [{}] ({} -> {}/{} remaining).",
                struct_dmg.fmt_g(), b.units[u].structure_type.name(), struct_before.fmt_g(), b.units[u].locations[cur.as_str()].structure.fmt_g(), b.units[u].max_structure[cur.as_str()]
            );
        }
        b.log(msg);

        let mut destroyed_this_hit = false;
        if struct_dmg > Num::I(0) {
            destroyed_this_hit = b.units[u].locations[cur.as_str()].structure <= Num::I(0);
            let present = b.units[u].locations[cur.as_str()].field(&armor_key) > Num::I(0);
            let modifier = armor_rules::crit_roll_modifier(b.units[u].structure_type, Some(armor_type), present);
            check_critical(b, u, &cur, destroyed_this_hit, modifier);
        }
        if !destroyed_this_hit && (armor_destroyed > Num::I(0) || struct_dmg > Num::I(0)) && !b.is_destroyed(u) {
            crate::water::check_breach(b, u, &cur);
        }
        if destroyed_this_hit {
            {
                let l = b.units[u].locations.get_mut(cur.as_str()).unwrap();
                l.structure = Num::I(0);
                l.destroyed = true;
            }
            b.log(format!("  {} DESTROYED!", cur));
            mark_all_crits_destroyed(b, u, &cur);
            if let Some(child) = b.units[u].side_torso_child.get(&cur).cloned() {
                {
                    let l = b.units[u].locations.get_mut(child.as_str()).unwrap();
                    l.destroyed = true;
                    l.structure = Num::I(0);
                }
                b.log(format!("  {} also destroyed (side torso rule).", child));
                b.units[u].severed_limbs.get_or_insert_with(Vec::new).push(child.clone());
                mark_all_crits_destroyed(b, u, &child);
            }
            let nxt = transfer_map(&cur);
            b.log(format!("  {} damage remains, transfers to {}.", remaining.py_str(), nxt.unwrap_or("nowhere (attack finished)")));
            current = nxt.map(|s| s.to_string());
            current_armor_field = "armor".to_string();
        }
        if b.is_destroyed(u) {
            return;
        }
    }
}

/// Check for a possible critical hit after structure damage. `modifier`: Hardened / Ablation / Reinforced.
pub fn check_critical(b: &mut Battle, u: UnitId, location: &str, location_destroyed: bool, modifier: i64) {
    if location_destroyed {
        let any = b.units[u].crits[location].iter().any(|s| matches!(s, Slot::Item(id) if b.units[u].items[*id].is_explosive && !b.units[u].items[*id].exploded));
        if !any {
            b.log(format!("  {} destroyed with no live explosive components - no critical roll.", location));
            return;
        }
    }
    let raw_roll = b.roll_2d6();
    let roll = 2.max(raw_roll + modifier);
    let mod_note = if modifier != 0 { format!(" ({} {:+})", raw_roll, modifier) } else { String::new() };
    b.log(format!("  Check for possible critical. Roll a {}{}.", roll, mod_note));
    if roll < 8 {
        b.log("    No critical hit.");
        return;
    }
    let count;
    if roll == 12 && !location_destroyed {
        if NON_TORSO_LOCATIONS.contains(&location) && armored_joint_absorbs(b, u, location) {
            return;
        }
        if NON_TORSO_LOCATIONS.contains(&location) {
            b.log(format!("    Roll of 12: {} blown off / destroyed!", location));
            b.units[u].severed_limbs.get_or_insert_with(Vec::new).push(location.to_string());
            {
                let l = b.units[u].locations.get_mut(location).unwrap();
                l.destroyed = true;
                l.structure = Num::I(0);
            }
            mark_all_crits_destroyed(b, u, location);
            return;
        } else {
            b.log("    Roll of 12 on torso: rolling 3 critical hits instead of destruction.");
            count = 3;
        }
    } else {
        count = if roll < 10 { 1 } else if roll < 12 { 2 } else { 3 };
    }
    b.log(format!("    {} critical hit(s).", count));
    for i in 1..=count {
        resolve_critical(b, u, location, location_destroyed, i, count);
    }
}

fn armored_joint_absorbs(b: &mut Battle, u: UnitId, location: &str) -> bool {
    let n = b.units[u].crits[location].len();
    for slot_idx in 0..n {
        let name = match &b.units[u].crits[location][slot_idx] {
            Slot::Name(n) => n.clone(),
            _ => continue,
        };
        if (name == "Shoulder" || name == "Hip") && b.units[u].armored_slots.contains(&(location.to_string(), slot_idx)) {
            b.units[u].armored_slots.shift_remove(&(location.to_string(), slot_idx));
            b.log(format!("    Roll of 12: {} would be blown off - its armored {} stops it and loses its component armor (p.207).", location, name));
            return true;
        }
    }
    false
}

pub fn resolve_critical(b: &mut Battle, u: UnitId, location: &str, explosive_only: bool, idx: i64, total: i64) {
    let slots = b.units[u].crits[location].clone();
    let pool: Vec<usize> = if explosive_only {
        slots.iter().enumerate().filter(|(_, s)| matches!(s, Slot::Item(id) if { let e = &b.units[u].items[*id]; e.is_explosive && !e.exploded && e.partner_of_slot.is_none() })).map(|(i, _)| i).collect()
    } else {
        slots.iter().enumerate().filter(|(_, s)| is_crit_target(s, &b.units[u].items)).map(|(i, _)| i).collect()
    };
    if !pool.is_empty() {
        let slot_idx = if pool.len() == 1 {
            pool[0]
        } else {
            if b.cfg.b("VERBOSE") {
                b.print(format!("  Critical hit pool at {}:", location));
                for (pick_num, &ci) in pool.iter().enumerate() {
                    let display = match &slots[ci] {
                        Slot::Item(id) => b.units[u].items[*id].name.clone(),
                        Slot::Name(n) => n.clone(),
                    };
                    b.print(format!("    {}: {} (slot {})", pick_num + 1, display, ci + 1));
                }
            }
            let choice = b.pick_number(pool.len() as i64);
            // the slot roll, shown in the report (Daniel, 2026-11-24: critical hit dice; whether to show the slot roll is an option on
            // the page). One die over the slots that can take the hit is the book's own shortcut (p.94: rolling both dice again on an
            // inapplicable slot makes every applicable slot equally likely). A known change from the answer key (stage6 known_changes).
            if b.cfg.b("VERBOSE") {
                b.print(format!("    Slot roll: {} on 1D{} (one die over the {} slots that can take the hit; p.94).", choice, pool.len(), pool.len()));
            }
            pool[(choice - 1) as usize]
        };
        let slot = slots[slot_idx].clone();
        if b.units[u].armored_slots.contains(&(location.to_string(), slot_idx)) {
            b.units[u].armored_slots.shift_remove(&(location.to_string(), slot_idx));
            let nm = match &slot {
                Slot::Item(id) => b.units[u].items[*id].name.clone(),
                Slot::Name(n) => n.clone(),
            };
            b.log(format!("    {}/{} Criticals: {} slot hit - its component armor absorbs it, no effect (p.207).", idx, total, nm));
            return;
        }
        resolve_slot_hit(b, u, location, slot_idx, &slot, idx, total);
        return;
    }
    if explosive_only {
        b.log(format!("    {}/{} Criticals: no live explosive component available - discarded.", idx, total));
        return;
    }
    if b.units[u].round_capable.get(location).copied().unwrap_or(true) {
        b.log(format!("    {}/{} Criticals: {} critical slots exhausted during this round - discarded (no transfer).", idx, total, location));
        return;
    }
    let nxt = transfer_map(location);
    b.log(format!("    {}/{} Criticals: {} was already fully cratered at the start of this round - transfers to {}.", idx, total, location, nxt.unwrap_or("nowhere")));
    if let Some(n) = nxt {
        resolve_critical(b, u, n, false, idx, total);
    }
}

pub fn resolve_slot_hit(b: &mut Battle, u: UnitId, location: &str, slot_idx: usize, slot: &Slot, idx: i64, total: i64) {
    if breached_slots_contains(&mut b.units[u], location, slot_idx) {
        b.units[u].crits.get_mut(location).unwrap()[slot_idx] = Slot::name("DESTROYED");
        let nm = match slot {
            Slot::Item(id) => b.units[u].items[*id].name.clone(),
            Slot::Name(n) => n.clone(),
        };
        b.log(format!("    {}/{} Criticals: {} slot hit (already breached).", idx, total, nm));
        if let Slot::Item(id) = slot {
            let e = &b.units[u].items[*id];
            if e.category.as_deref() == Some("ammo") && e.is_explosive && !e.exploded {
                b.units[u].items[*id].exploded = true;
                apply_explosion(b, u, *id, location);
            }
        }
        return;
    }
    match slot {
        Slot::Item(id) => {
            let id = *id;
            if autocannon_shrugs_off(b, u, location, slot_idx, id, idx, total) {
                return;
            }
            let name = b.units[u].items[id].name.clone();
            b.units[u].destroyed_slot_info.insert((location.to_string(), slot_idx), SlotInfo { name: name.clone(), instance_id: Some(id) });
            b.units[u].crits.get_mut(location).unwrap()[slot_idx] = Slot::name("DESTROYED");
            b.log(format!("    {}/{} Criticals: {} slot hit.", idx, total, name));
            if b.ev("CRIT").live() {
                let kind = {
                    let m = &b.units[u];
                    if m.items[id].category.as_deref() == Some("ammo") { "Ammo" } else if is_heat_sink(m, id) { "Heat Sink" } else if m.items[id].category.as_deref() == Some("weapon") { "Weapon" } else { "Other" }
                };
                b.ev("CRIT").unit(u).loc(location).sub(kind).what(&name).emit(b);
            }
            let crits_now = display_crits(&b.units[u], location);
            b.log(format!("      Current crit slots in {}: {}", location, py_str_list(&crits_now)));
            if is_jump_jet(&b.units[u], id) && !b.units[u].destroyed_jump_jet_ids.contains(&id) {
                b.units[u].destroyed_jump_jet_ids.insert(id);
                let now = compute_jump_mp(&b.units[u]);
                b.log(format!("      Jump jet destroyed ({}) - jump MP reduced (now {}).", name, now));
            }
            if is_heat_sink(&b.units[u], id) && !b.units[u].destroyed_heat_sinks.contains_key(&id) {
                let units = heat_sink_units(&b.units[u], id);
                b.units[u].destroyed_heat_sinks.insert(id, units);
                let now = compute_heat_dissipation(&b.units[u]);
                b.log(format!("      Heat sink destroyed ({}) - heat dissipation reduced (now {}).", name, now));
            }
            if is_mechanical_jump_booster(&b.units[u], id) && !b.units[u].mechanical_jump_booster_disabled {
                b.units[u].mechanical_jump_booster_disabled = true;
                let now = compute_mechanical_jump_booster_mp(&b.units[u]);
                b.log(format!("      Mechanical Jump Booster disabled (system-wide, all-or-nothing) - jump booster MP now {}.", now));
            }
            if is_partial_wing(&b.units[u], id) && b.units[u].partial_wing_active {
                b.units[u].partial_wing_active = false;
                let now = compute_jump_mp(&b.units[u]);
                b.log(format!("      Partial Wing disabled (system-wide, all-or-nothing) - jump MP now {}.", now));
            }
            if b.units[u].items[id].linked_ppc.is_some() || b.units[u].items[id].capacitor.is_some() {
                crate::capacitor::crit_hit(b, u, location, id);
            }
            if norm_name(&b.units[u].items[id].name).contains("BLUESHIELD") {
                crate::equipment_systems::blue_shield_hit(b, u, location, id);
            }
            if b.units[u].items[id].modular_points.unwrap_or(0) != 0 {
                crate::advanced_equipment::slot_hit(b, u, id);
            }
            if norm_name(&b.units[u].items[id].name).contains("HARJEL") {
                crate::equipment_systems::harjel_hit(b, u, location, id);
            }
            let (explosive, exploded) = (b.units[u].items[id].is_explosive, b.units[u].items[id].exploded);
            if explosive && !exploded {
                b.units[u].items[id].exploded = true;
                apply_explosion(b, u, id, location);
            } else if explosive && exploded {
                b.log(format!("      {} already exploded - this slot destroyed, no further effect.", name));
            }
        }
        Slot::Name(n) => {
            b.units[u].destroyed_slot_info.insert((location.to_string(), slot_idx), SlotInfo { name: n.clone(), instance_id: None });
            b.units[u].crits.get_mut(location).unwrap()[slot_idx] = Slot::name("DESTROYED");
            b.log(format!("    {}/{} Criticals: {} hit.", idx, total, n));
            if b.ev("CRIT").live() {
                let kind = if LEG_ACTUATOR_NAMES.contains(&n.as_str()) || n.contains("Actuator") || n.as_str() == "Shoulder" || n.as_str() == "Hip" { "Actuator" } else if ["Engine", "Gyro", "Cockpit", "Sensors", "Life Support"].contains(&n.as_str()) { n.as_str() } else { "Other" };
                // engine / gyro hits so far (this critical not yet counted by the effects below)
                let hits = match n.as_str() { "Engine" => b.units[u].engine_hits + 1, "Gyro" => b.units[u].gyro_hits + 1, _ => 0 };
                let e = b.ev("CRIT").unit(u).loc(location).sub(kind).what(n);
                (if hits > 0 { e.n(hits) } else { e }).emit(b);
            }
            let crits_now = display_crits(&b.units[u], location);
            b.log(format!("      Current crit slots in {}: {}", location, py_str_list(&crits_now)));
            let n = n.as_str();
            if n == "Engine" {
                b.units[u].engine_hits += 1;
                let (h, t) = (b.units[u].engine_hits, engine_hits_to_destroy(&b.units[u]));
                b.log(format!("      Engine hit ({}/{}).", h, t));
                if h >= t {
                    b.ev("COMPONENT_DESTROYED").unit(u).sub("Engine").emit(b);
                }
            } else if n == "Gyro" {
                b.units[u].gyro_hits += 1;
                let (h, t) = (b.units[u].gyro_hits, if has_hd_gyro(&b.units[u]) { 4 } else { 2 });
                b.log(format!("      Gyro hit ({}/{}).", h, t));
                if h >= t {
                    b.ev("COMPONENT_DESTROYED").unit(u).sub("Gyro").emit(b);
                }
            } else if n == "Cockpit" && has_command_console(&b.units[u]) && b.units[u].crits[location].iter().any(|s| s.is_name("Cockpit")) {
                let last = b.units[u].crits[location].iter().enumerate().filter(|(_, s)| s.is_name("Cockpit")).map(|(i, _)| i).max().unwrap();
                let first = slot_idx < last;
                if first && console_active(&b.units[u]) {
                    b.log("      Pilot's cockpit destroyed - the command console takes over (p.203).");
                    let line = console_takes_over(&mut b.units[u], "pilot's cockpit destroyed");
                    b.log(line);
                } else {
                    b.units[u].console_lost = Some(true);
                    b.log("      Command console destroyed - no second warrior any more (p.203).");
                }
            } else if n == "Cockpit" {
                b.units[u].cockpit_hit = true;
                b.log("      Cockpit hit - instant kill condition set.");
                b.ev("COMPONENT_DESTROYED").unit(u).sub("Cockpit").emit(b);
            } else if LEG_ACTUATOR_NAMES.contains(&n) && b.units[u].leg_locations.iter().any(|l| l == location) {
                let c = b.units[u].destroyed_leg_actuators.get(location).copied().unwrap_or(0) + 1;
                b.units[u].destroyed_leg_actuators.insert(location.to_string(), c);
                let wmp = compute_walk_mp(&b.units[u]);
                b.log(format!("      Leg actuator hit at {} ({} destroyed there) - walk MP now {}.", location, c, wmp));
                if n == "Hip" {
                    b.units[u].destroyed_hip_locations.insert(location.to_string());
                    b.log(format!("      Hip specifically destroyed at {} - running-mode Movement Phase PSR trigger now active.", location));
                }
            }
        }
    }
}

/// Python's `str(list_of_str)`.
pub fn py_str_list(v: &[String]) -> String {
    format!("[{}]", v.iter().map(|s| crate::pyfmt::py_repr_str(s)).collect::<Vec<_>>().join(", "))
}

/// Core p.183: the first critical hit to an autocannon doesn't destroy it.
fn autocannon_shrugs_off(b: &mut Battle, u: UnitId, location: &str, slot_idx: usize, id: ItemId, idx: i64, total: i64) -> bool {
    if b.units[u].items[id].category.as_deref() != Some("weapon") || !is_autocannon(&b.units[u], id) {
        return false;
    }
    if b.units[u].autocannon_crits.get_or_insert_with(Default::default).contains(&id) {
        return false;
    }
    b.units[u].autocannon_crits.as_mut().unwrap().insert(id);
    let name = b.units[u].items[id].name.clone();
    if b.units[u].items[id].slots_occupied > 1 {
        b.units[u].destroyed_slot_info.insert((location.to_string(), slot_idx), SlotInfo { name: name.clone(), instance_id: None });
        b.units[u].crits.get_mut(location).unwrap()[slot_idx] = Slot::name("DESTROYED");
    }
    b.log(format!("    {}/{} Criticals: {} slot hit - an autocannon's first critical hit doesn't destroy it (p.183); it still fires.", idx, total, name));
    true
}

/// CASE / CASE II in a location: "CASE II", "CASE", or none.
pub fn get_case_tier(mech: &Mech, location: &str) -> Option<&'static str> {
    const CASE_II: [&str; 4] = ["ISCASEII", "CLCASEII", "IS CASE II", "CLAN CASE II"];
    const CASE: [&str; 6] = ["ISCASE", "CLCASE", "IS CASE", "CLAN CASE", "ISCASEPROTOTYPE", "PROTOTYPE CASE"];
    let mut found = false;
    for slot in &mech.crits[location] {
        if let Slot::Item(id) = slot {
            let name = mech.items[*id].name.trim().to_uppercase();
            if CASE_II.contains(&name.as_str()) {
                return Some("CASE II");
            }
            if CASE.contains(&name.as_str()) {
                found = true;
            }
        }
    }
    if found {
        return Some("CASE");
    }
    // A Clan-tech 'Mech has CASE in every location with no slot needed (Daniel, 2026-11-28; MegaMek Mek.addClanCase; the
    // same rule `battle_value.rs` `location_case` already used). The head and legs are not places an explosion crosses anyway.
    let tb = mech.tech_base.as_deref().unwrap_or("").to_uppercase();
    if tb.starts_with("CLAN") || tb.contains("MIXED (CLAN") {
        return Some("CASE");
    }
    None
}

pub const EXPLOSION_IS_CAP: i64 = 20;
pub const CASE_ARMOR_CAP: i64 = 10;
pub const CASE_II_CRIT_MODIFIER: i64 = -1;

fn case_is_cap(tier: &str) -> i64 {
    if tier == "CASE" { 10 } else { 1 }
}

/// Internal explosion (Core pp.95-96).
pub fn apply_explosion(b: &mut Battle, u: UnitId, component: ItemId, location: &str) {
    b.units[u].explosions += 1;
    b.units[u].pilot_hits += 1;
    b.pilot_hit_ev(u, "explosion");
    mark_consciousness_check_pending(&mut b.units[u]);
    let mut base = b.units[u].items[component].explosion_damage;
    if let Some(partner) = b.units[u].items[component].partner {
        let (c_ammo, p) = (b.units[u].items[component].category.as_deref() == Some("ammo"), &b.units[u].items[partner]);
        if c_ammo && p.category.as_deref() == Some("ammo") && p.is_explosive && !p.exploded {
            b.units[u].items[partner].exploded = true;
            base += b.units[u].items[partner].explosion_damage;
            let locs: Vec<String> = b.units[u].crits.keys().cloned().collect();
            for loc in locs {
                let n = b.units[u].crits[&loc].len();
                for i in 0..n {
                    if b.units[u].crits[&loc][i] == Slot::Item(partner) {
                        let nm = b.units[u].items[partner].name.clone();
                        b.units[u].destroyed_slot_info.insert((loc.clone(), i), SlotInfo { name: nm, instance_id: Some(partner) });
                        b.units[u].crits.get_mut(&loc).unwrap()[i] = Slot::name("DESTROYED");
                    }
                }
            }
            let (pn, pd) = (b.units[u].items[partner].name.clone(), b.units[u].items[partner].explosion_damage);
            b.log(format!("    {} shares the superheavy slot - it explodes too (+{}; one MechWarrior hit, Core p.240).", pn, pd));
        }
    }
    let cname = b.units[u].items[component].name.clone();
    let ph = b.units[u].pilot_hits;
    b.log(format!("    {} destroyed at {} - EXPLOSION ({} dmg)! Pilot takes 1 hit ({}/6).", cname, location, base, ph));
    if b.ev("AMMO_EXPLOSION").live() {
        let case = match get_case_tier(&b.units[u], location) {
            None => "no_case",
            Some("CASE") => "case",
            Some(_) => "case_ii",
        };
        b.ev("AMMO_EXPLOSION").unit(u).loc(location).sub(case).what(&cname).dmg(base as f64).emit(b);
    }

    let mut remaining = Num::I(base.min(EXPLOSION_IS_CAP));
    let mut incoming = Num::I(base);
    let mut current: Option<String> = Some(location.to_string());
    let mut last_hit: Option<String> = None;
    while remaining > Num::I(0) && current.is_some() {
        let cur = current.clone().unwrap();
        if b.units[u].locations[cur.as_str()].destroyed {
            let nxt = transfer_map(&cur);
            b.log(format!("    {} already destroyed - explosion transfers to {}.", cur, nxt.unwrap_or("nowhere")));
            current = nxt.map(|s| s.to_string());
            continue;
        }
        if let Some(tier) = get_case_tier(&b.units[u], &cur) {
            case_contains(b, u, &cur, tier, incoming);
            return;
        }
        b.log(format!("    Explosion reaches {}. No CASE present - {} damage to structure.", cur, remaining.py_str()));
        let struct_dmg = py_min(remaining, b.units[u].locations[cur.as_str()].structure);
        let destroyed_this_hit = explosion_structure(b, u, &cur, struct_dmg, 0);
        if struct_dmg > Num::I(0) {
            last_hit = Some(cur.clone());
        }
        remaining = remaining - struct_dmg;
        incoming = remaining;
        if b.is_destroyed(u) {
            return;
        }
        if remaining > Num::I(0) && destroyed_this_hit {
            let nxt = transfer_map(&cur);
            b.log(format!("    {} explosion damage remains, transfers to {}.", remaining.py_str(), nxt.unwrap_or("nowhere")));
            current = nxt.map(|s| s.to_string());
        }
    }
    if base > EXPLOSION_IS_CAP && remaining == Num::I(0) {
        if let Some(lh) = last_hit {
            if !b.units[u].locations[lh.as_str()].destroyed {
                strip_armor(b, u, &lh, None, "base damage over 20 (p.96)");
            }
        }
    }
}

fn case_contains(b: &mut Battle, u: UnitId, location: &str, tier: &str, incoming: Num) {
    let is_cap = case_is_cap(tier);
    let struct_dmg = py_min(py_min(incoming, Num::I(is_cap)), b.units[u].locations[location].structure);
    b.log(format!("    Explosion reaches {}. {} present - at most {} structure damage.", location, tier, is_cap));
    let destroyed = explosion_structure(b, u, location, struct_dmg, if tier == "CASE II" { CASE_II_CRIT_MODIFIER } else { 0 });
    let excess = incoming - Num::I(is_cap);
    if excess > Num::I(0) && !destroyed && !b.is_destroyed(u) {
        strip_armor(b, u, location, Some(py_min(excess, Num::I(CASE_ARMOR_CAP))), &format!("{} vents the excess", tier));
    }
    b.log(format!("    {} contains the explosion. No further transfer.", tier));
}

pub fn explosion_structure(b: &mut Battle, u: UnitId, location: &str, struct_dmg: Num, crit_modifier: i64) -> bool {
    let new_struct = b.units[u].locations[location].structure - struct_dmg;
    b.units[u].locations.get_mut(location).unwrap().structure = new_struct;
    let destroyed_this_hit = new_struct <= Num::I(0);
    b.log(format!("    {} structure damage taken ({}/{} remaining).", struct_dmg.py_str(), new_struct.py_str(), b.units[u].max_structure[location]));
    if struct_dmg > Num::I(0) {
        let modifier = armor_rules::crit_roll_modifier(b.units[u].structure_type, None, false) + crit_modifier;
        check_critical(b, u, location, destroyed_this_hit, modifier);
    }
    if destroyed_this_hit {
        {
            let l = b.units[u].locations.get_mut(location).unwrap();
            l.structure = Num::I(0);
            l.destroyed = true;
        }
        b.log(format!("    {} DESTROYED! (explosion)", location));
        mark_all_crits_destroyed(b, u, location);
        if let Some(child) = b.units[u].side_torso_child.get(location).cloned() {
            {
                let l = b.units[u].locations.get_mut(child.as_str()).unwrap();
                l.destroyed = true;
                l.structure = Num::I(0);
            }
            b.log(format!("  {} also destroyed (side torso rule).", child));
            b.units[u].severed_limbs.get_or_insert_with(Vec::new).push(child.clone());
            mark_all_crits_destroyed(b, u, &child);
        }
    }
    destroyed_this_hit
}

fn strip_armor(b: &mut Battle, u: UnitId, location: &str, amount: Option<Num>, why: &str) {
    let field = if b.units[u].locations[location].rear_armor.is_some() { "rear_armor" } else { "armor" };
    let cur = b.units[u].locations[location].field(field);
    let lost = match amount {
        None => cur,
        Some(a) => py_min(a, cur),
    };
    let left = cur - lost;
    b.units[u].locations.get_mut(location).unwrap().set_field(field, left);
    b.log(format!("    {}: {} loses {} {} ({} left).", why, location, lost.py_str(), field.replace('_', " "), left.py_str()));
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
