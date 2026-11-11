// Translated from INTEGRATION__equipment_systems.py (session 22).
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


// ---- tables ---------------------------------------------------------------------------------------------------------
pub const ESCALATING_SYSTEMS: [&str; 3] = ["masc", "supercharger", "radical"];
pub const ESCALATING_FAILURE_AVOID_MAX: i64 = 11;
pub const TSM_ACTIVE_HEAT: i64 = 9;
pub const VOID_OWN_ATTACK_MODIFIER: i64 = 1;
pub const PFD_FAILURE_AFTER: i64 = 6;

pub fn stealth_heat_of(kind: &str) -> i64 {
    match kind {
        "chameleon" => 6,
        "null_signature" | "stealth_armor" | "void_signature" => 10,
        other => panic!("KeyError: {}", other),
    }
}

pub fn run_multiplier_by_boosters(n: usize) -> f64 {
    match n {
        0 => 1.5,
        1 => 2.0,
        2 => 2.5,
        other => panic!("KeyError: {}", other),
    }
}

/// 2D6 critical-hit check (p.90): roll -> crits.
pub fn crits_for_roll(roll: i64) -> i64 {
    if roll < 8 {
        0
    } else if roll < 10 {
        1
    } else if roll < 12 {
        2
    } else {
        3
    }
}

/// Which system an Equipment crit slot belongs to (name match), or None.
pub fn kind_of(mech: &Mech, slot: &Slot) -> Option<&'static str> {
    let id = match slot {
        Slot::Item(id) => *id,
        _ => return None,
    };
    if mech.items[id].category.as_deref() == Some("ammo") {
        return None;
    }
    let n = norm(&mech.items[id].name);
    if n.contains("MASC") {
        return Some("masc");
    }
    if n.contains("SUPERCHARGER") {
        return Some("supercharger");
    }
    if n.contains("RADICALHEATSINK") {
        return Some("radical");
    }
    if n.contains("COOLANTPOD") {
        return Some("coolant_pod");
    }
    if n.contains("BLUESHIELD") {
        return Some("blue_shield");
    }
    if n.contains("CHAMELEON") {
        return Some("chameleon");
    }
    if n.contains("NULLSIGNATURE") {
        return Some("null_signature");
    }
    if n.contains("VOIDSIGNATURE") {
        return Some("void_signature");
    }
    if n.contains("ECM") {
        return Some("ecm");
    }
    if n == "ISSTEALTH" || n == "ISSTEALTHARMOR" {
        return Some("stealth_armor");
    }
    if (n.contains("TSM") || n.contains("TRIPLESTRENGTHMYOMER")) && !n.contains("INDUSTRIAL") {
        return Some("tsm");
    }
    None
}

/// Once per battle per mech: finds every system, keyed by kind -> Equipment instances.
pub fn attach_equipment(b: &mut Battle, u: UnitId) {
    let mut found: indexmap::IndexMap<String, Vec<ItemId>> = indexmap::IndexMap::new();
    let mut seen: Vec<ItemId> = Vec::new();
    {
        let m = &b.units[u];
        for slots in m.crits.values() {
            for slot in slots {
                if let Some(kind) = kind_of(m, slot) {
                    if let Slot::Item(id) = slot {
                        if !seen.contains(id) {
                            seen.push(*id);
                            found.entry(kind.to_string()).or_default().push(*id);
                        }
                    }
                }
            }
        }
    }
    let m = &mut b.units[u];
    m.has_tsm = found.contains_key("tsm") || norm(m.myomer.as_str()).contains("TRIPLESTRENGTH");
    m.has_stealth_armor = found.contains_key("stealth_armor") || norm(m.armor_desc.as_deref().unwrap_or("")).contains("STEALTH");
    m.torso_cockpit = norm(m.cockpit_type.as_deref().unwrap_or("")).contains("TORSO");
    m.equipment_systems = found;
    m.escalating_turns = ESCALATING_SYSTEMS.iter().map(|k| (k.to_string(), 0)).collect();
    m.systems_used_this_turn = Vec::new();
    m.turn_number = 0;
    let name = m.side_name.clone().unwrap_or_default();
    let pfd = has_system(&b.units[u], "blue_shield") && crate::stubs::stub_blue_shield(b, &name, "start");
    b.units[u].pfd_active = pfd;
    b.units[u].pfd_turns_used = 0;
    b.units[u].pfd_failed = false;
}

pub fn ecm_live(mech: &Mech) -> bool {
    system_live(mech, "ecm")
}

/// Mark the system's upper-most live slot destroyed (radical failure, failed supercharger).
pub fn destroy_system(b: &mut Battle, u: UnitId, kind: &str, why: &str) {
    let parts: Vec<ItemId> = b.units[u].equipment_systems.get(kind).cloned().unwrap_or_default();
    let locs: Vec<String> = b.units[u].crits.keys().cloned().collect();
    for location in locs {
        let n = b.units[u].crits[&location].len();
        for i in 0..n {
            if let Slot::Item(id) = b.units[u].crits[&location][i].clone() {
                if parts.contains(&id) {
                    let name = b.units[u].items[id].name.clone();
                    b.units[u].destroyed_slot_info.insert((location.clone(), i), crate::mech_state::SlotInfo { name: name.clone(), instance_id: Some(id) });
                    b.units[u].crits.get_mut(&location).unwrap()[i] = Slot::name("DESTROYED");
                    let side = b.units[u].side_name.clone().unwrap_or_default();
                    b.log(format!("    {}: {} in {} destroyed ({}).", side, name, location, why));
                    return;
                }
            }
        }
    }
}

pub fn start_turn(b: &mut Battle, u: UnitId, turn_number: i64) {
    b.units[u].turn_number = turn_number;
    b.units[u].systems_used_this_turn = Vec::new();
    harjel_start_turn(&mut b.units[u]);
}

/// Daniel's 1-turn-on / 1-turn-off cycle.
pub fn cycle_on(b: &Battle, u: UnitId, turn_number: Option<i64>) -> bool {
    let turn = turn_number.unwrap_or(b.units[u].turn_number);
    let odd = crate::pyfmt::py_mod(turn, 2) == 1;
    if b.cfg.b("ESCALATING_CYCLE_ON_ODD_TURNS") {
        odd
    } else {
        !odd
    }
}

pub fn escalating_avoid_tn(consecutive_turns: i64) -> i64 {
    match consecutive_turns {
        1 => 3,
        2 => 5,
        3 => 7,
        4 => 10,
        _ => ESCALATING_FAILURE_AVOID_MAX,
    }
}

/// One use of an Escalating Failure system (p.180). True = it works.
pub fn escalating_roll(b: &mut Battle, u: UnitId, key: &str, label: &str) -> bool {
    *b.units[u].escalating_turns.get_mut(key).expect("escalating key") += 1;
    if !b.units[u].systems_used_this_turn.iter().any(|k| k == key) {
        b.units[u].systems_used_this_turn.push(key.to_string());
    }
    let n = b.units[u].escalating_turns[key];
    let tn = escalating_avoid_tn(n);
    let roll = b.roll_2d6();
    let ok = roll >= tn;
    let name = b.units[u].side_name.clone().unwrap_or_default();
    b.log(format!("    {}: {} (turn {} in a row) needs {}, rolled {} - {}.", name, label, n, tn, roll, if ok { "works" } else { "FAILS" }));
    ok
}

/// End Phase: every Escalating Failure system not used this turn steps its count back one.
pub fn end_turn(b: &mut Battle, u: UnitId) {
    for key in ESCALATING_SYSTEMS {
        if !b.units[u].systems_used_this_turn.iter().any(|k| k == key) {
            let v = b.units[u].escalating_turns.get_mut(key).unwrap();
            *v = 0.max(*v - 1);
        }
    }
    b.units[u].systems_used_this_turn = Vec::new();
    harjel_end_turn(b, u);
    blue_shield_end_turn(b, u);
}

/// Stealth systems switched on and working right now.
pub fn active_stealth(mech: &Mech) -> Vec<&'static str> {
    if mech.shutdown || blue_shield_on(mech) {
        return vec![];
    }
    let mut active: Vec<&'static str> = ["chameleon", "null_signature"].into_iter().filter(|k| system_live(mech, k)).collect();
    if mech.has_stealth_armor && ecm_live(mech) && !modular_active(mech) {
        active.push("stealth_armor");
    }
    if system_live(mech, "void_signature") && ecm_live(mech) {
        active.push("void_signature");
    }
    active
}

fn modular_active(mech: &Mech) -> bool {
    mech.modular_armor.iter().any(|id| mech.items[*id].modular_points.unwrap_or(0) > 0)
}

pub fn stealth_heat(mech: &Mech) -> i64 {
    active_stealth(mech).iter().map(|k| stealth_heat_of(k)).sum()
}

/// {bracket: TN bonus} for attacks against `target`.
pub fn range_stealth_bonus(target: &Mech) -> [(&'static str, i64); 3] {
    let count = active_stealth(target).iter().filter(|k| matches!(**k, "chameleon" | "null_signature" | "stealth_armor")).count() as i64;
    [("short", count * 0), ("medium", count * 1), ("long", count * 2)]
}

/// TN bonus for every attack against a target with an active Void-Signature System.
pub fn void_signature_modifier(target: &Mech, hexes_moved: Option<i64>, mp_spent: Option<i64>) -> i64 {
    if !active_stealth(target).contains(&"void_signature") {
        return 0;
    }
    let mut hexes = hexes_moved.unwrap_or(target.move_fc);
    let spent = mp_spent.unwrap_or(target.mp_spent);
    if hexes == 0 && spent > 0 {
        hexes = 1;
    }
    for (threshold, bonus) in [(6, 0), (3, 1), (1, 2), (0, 3)] {
        if hexes >= threshold {
            return bonus;
        }
    }
    0
}

pub fn unused_coolant_pods(mech: &Mech) -> Vec<ItemId> {
    let dead = destroyed_ids(mech);
    mech.equipment_systems.get("coolant_pod").map_or_else(Vec::new, |v| v.iter().copied().filter(|p| !dead.contains(p) && !mech.items[*p].pod_used.unwrap_or(false)).collect())
}

pub fn use_coolant_pod(b: &mut Battle, u: UnitId) -> ItemId {
    let pod = unused_coolant_pods(&b.units[u])[0];
    let it = &mut b.units[u].items[pod];
    it.pod_used = Some(true);
    it.is_explosive = false;
    it.explosion_damage = 0;
    pod
}

pub fn use_escalating(b: &mut Battle, u: UnitId, label: &str, turn_number: Option<i64>, warn: bool) -> bool {
    let cycle = cycle_on(b, u, turn_number);
    let name = b.units[u].side_name.clone().unwrap_or_default();
    crate::stubs::stub_escalating_use(b, &name, label, cycle, warn)
}

pub fn radical_planned(b: &mut Battle, u: UnitId, turn_number: Option<i64>, warn: bool) -> bool {
    system_live(&b.units[u], "radical") && !b.units[u].shutdown && use_escalating(b, u, "radical heat sink system", turn_number, warn)
}

pub fn radical_destroyed(mech: &Mech) -> bool {
    has_system(mech, "radical") && !system_live(mech, "radical")
}

pub fn reset_movement_boost(mech: &mut Mech) {
    mech.run_mp_multiplier = run_multiplier_by_boosters(0);
}

/// The Running MP multiplier the working MASC / supercharger give.
pub fn boost_multiplier(b: &mut Battle, u: UnitId, planned: bool) -> f64 {
    let live = ["masc", "supercharger"].iter().filter(|k| system_live(&b.units[u], k)).count();
    if live == 0 || (planned && !use_escalating(b, u, "MASC / supercharger", None, false)) {
        return run_multiplier_by_boosters(0);
    }
    run_multiplier_by_boosters(live)
}

/// Called when the mech declares its movement: rolls each working MASC / supercharger; returns the systems that failed.
pub fn resolve_movement_boosters(b: &mut Battle, u: UnitId) -> Vec<&'static str> {
    reset_movement_boost(&mut b.units[u]);
    if !(system_live(&b.units[u], "masc") || system_live(&b.units[u], "supercharger")) {
        return vec![];
    }
    if !use_escalating(b, u, "MASC / supercharger", None, true) {
        return vec![];
    }
    let mut worked = 0;
    let mut failed = Vec::new();
    for (kind, label) in [("masc", "MASC"), ("supercharger", "Supercharger")] {
        if system_live(&b.units[u], kind) {
            if escalating_roll(b, u, kind, label) {
                worked += 1;
            } else {
                failed.push(kind);
            }
        }
    }
    b.units[u].run_mp_multiplier = run_multiplier_by_boosters(worked);
    failed
}

fn random_leg(b: &mut Battle, u: UnitId) -> String {
    let legs = b.units[u].leg_locations.clone();
    if legs.iter().any(|l| l == "Right Leg") && legs.iter().any(|l| l == "Left Leg") && legs.len() == 2 {
        return if b.pick_number(6) <= 3 { "Right Leg" } else { "Left Leg" }.to_string();
    }
    let pick = b.pick_number(legs.len() as i64);
    legs[(pick - 1) as usize].clone()
}

/// End of movement: damage from a failed MASC / supercharger roll.
pub fn apply_booster_failures(b: &mut Battle, u: UnitId, failed: &[&str]) {
    for kind in failed {
        let roll = b.roll_2d6();
        let count = crits_for_roll(roll);
        let name = b.units[u].side_name.clone().unwrap_or_default();
        b.log(format!("    {}: {} failure - critical check {}: {} critical hit(s).", name, kind, roll, count));
        if *kind == "masc" {
            masc_crits(b, u, count);
        } else {
            supercharger_crits(b, u, count);
            destroy_system(b, u, "supercharger", "failed activation");
        }
    }
}

fn masc_crits(b: &mut Battle, u: UnitId, count: i64) {
    if count == 0 {
        return;
    }
    let leg = random_leg(b, u);
    for i in 1..=count {
        if b.units[u].locations[leg.as_str()].destroyed {
            b.log(format!("      {} already destroyed - MASC critical {}/{} lost (never transfers).", leg, i, count));
            continue;
        }
        let pool: Vec<usize> = b.units[u].crits[&leg].iter().enumerate().filter(|(_, s)| crate::equipment::is_crit_target(s, &b.units[u].items)).map(|(j, _)| j).collect();
        if pool.is_empty() {
            b.log(format!("      No critical slots left in {} - MASC critical {}/{} lost (never transfers).", leg, i, count));
            continue;
        }
        let pick = b.pick_number(pool.len() as i64);
        let idx = pool[(pick - 1) as usize];
        let slot = b.units[u].crits[&leg][idx].clone();
        crate::damage_resolution::resolve_slot_hit(b, u, &leg, idx, &slot, i, count);
    }
}

fn supercharger_crits(b: &mut Battle, u: UnitId, count: i64) {
    for i in 1..=count {
        let engines: Vec<usize> = b.units[u].crits["Center Torso"].iter().enumerate().filter(|(_, s)| s.is_name("Engine")).map(|(j, _)| j).collect();
        if engines.is_empty() {
            b.log(format!("      No undamaged centre-torso Engine slot - supercharger critical {}/{} lost.", i, count));
            continue;
        }
        crate::damage_resolution::resolve_slot_hit(b, u, "Center Torso", engines[0], &Slot::name("Engine"), i, count);
    }
}

pub fn tsm_active_for(mech: &Mech, heat_level: i64) -> bool {
    mech.has_tsm && heat_level >= TSM_ACTIVE_HEAT
}

pub fn harjel_repair(kind: i64) -> i64 {
    match kind {
        2 => 2,
        3 => 4,
        other => panic!("KeyError: {}", other),
    }
}

pub fn harjel_start_turn(m: &mut Mech) {
    m.armor_at_turn_start = Some(m.locations.iter().map(|(loc, v)| (loc.clone(), vec![v.armor, v.rear_armor.unwrap_or(Num::I(0))])).collect());
}

/// End Phase repair for HarJel II / III locations that took armor damage.
pub fn harjel_end_turn(b: &mut Battle, u: UnitId) {
    let start = match b.units[u].armor_at_turn_start.clone() {
        Some(s) if !s.is_empty() => s,
        _ => return,
    };
    for (loc, pair) in start {
        let (front0, rear0) = (pair[0], pair[1]);
        let kind = harjel_kind(&b.units[u], &loc);
        let v = b.units[u].locations[loc.as_str()].clone();
        if kind < 2 || v.destroyed {
            continue;
        }
        let (front, rear) = (v.armor, v.rear_armor.unwrap_or(Num::I(0)));
        if front >= front0 && rear >= rear0 {
            continue;
        }
        let mut budget = harjel_repair(kind);
        let room_f = py_max(Num::I(0), Num::I(b.units[u].max_armor.get(&loc).copied().unwrap_or(0)) - front).as_int_or_trunc();
        let room_r = if v.rear_armor.is_some() { py_max(Num::I(0), Num::I(b.units[u].max_rear_armor.get(&loc).copied().unwrap_or(0)) - rear).as_int_or_trunc() } else { 0 };
        let (mut got_f, mut got_r) = (0, 0);
        while budget != 0 && (room_f > got_f || room_r > got_r) {
            if room_f > got_f && (got_f <= got_r || room_r <= got_r) {
                got_f += 1;
            } else if room_r > got_r {
                got_r += 1;
            }
            budget -= 1;
        }
        if got_f != 0 || got_r != 0 {
            let l = b.units[u].locations.get_mut(loc.as_str()).unwrap();
            l.armor = front + Num::I(got_f);
            if got_r != 0 {
                l.rear_armor = Some(rear + Num::I(got_r));
            }
            let side = b.units[u].side_name.clone().unwrap_or_default();
            let split = if got_r != 0 { format!(" ({} front, {} rear)", got_f, got_r) } else { String::new() };
            b.log(format!("  [End] {}'s HarJel {} restores {} armor at {}{} (p.208).", side, if kind == 2 { "II" } else { "III" }, got_f + got_r, loc, split));
        }
    }
}

pub fn blue_shield_on(m: &Mech) -> bool {
    m.pfd_active && !m.pfd_failed && !m.shutdown && system_live(m, "blue_shield")
}

pub fn is_ppc(m: &Mech, weapon: ItemId) -> bool {
    let n = norm(&m.items[weapon].name);
    n.contains("PPC") && !n.contains("CAPACITOR")
}

/// A PPC hit's damage after the target's Blue Shield (p.207).
pub fn blue_shield_damage(b: &mut Battle, target: UnitId, weapon_owner: UnitId, weapon: ItemId, damage: i64) -> i64 {
    if damage != 0 && is_ppc(&b.units[weapon_owner], weapon) && blue_shield_on(&b.units[target]) {
        let cut = 1.max(crate::pyfmt::py_floordiv(damage, 2));
        let (tn, wn) = (b.units[target].side_name.clone().unwrap_or_default(), b.units[weapon_owner].items[weapon].name.clone());
        b.log(format!("      {}'s Blue Shield halves the {}: {} -> {} (p.207).", tn, wn, damage, cut));
        return cut;
    }
    damage
}

pub fn blue_shield_end_turn(b: &mut Battle, u: UnitId) {
    if !has_system(&b.units[u], "blue_shield") || b.units[u].pfd_failed {
        return;
    }
    if blue_shield_on(&b.units[u]) {
        b.units[u].pfd_turns_used += 1;
        if b.units[u].pfd_turns_used >= PFD_FAILURE_AFTER {
            let used = b.units[u].pfd_turns_used;
            let interval = used - PFD_FAILURE_AFTER + 1;
            let tn = escalating_avoid_tn(interval);
            let roll = b.roll_2d6();
            let name = b.units[u].side_name.clone().unwrap_or_default();
            b.log(format!("  [End] {}'s Blue Shield ({} turns on) needs {}, rolled {} - {} (p.207).", name, used, tn, roll, if roll >= tn { "holds" } else { "FAILS: off for the rest of the battle" }));
            if roll < tn {
                b.units[u].pfd_failed = true;
                b.units[u].pfd_active = false;
                return;
            }
        }
    }
    if system_live(&b.units[u], "blue_shield") && !b.units[u].pfd_failed {
        let name = b.units[u].side_name.clone().unwrap_or_default();
        let on = crate::stubs::stub_blue_shield(b, &name, "end phase");
        b.units[u].pfd_active = on;
    }
}

/// own_attack_modifier: an active Void-Signature System adds +1 to its own mech's ranged attacks; plus Taser / TSEMP / IMP.
pub fn own_attack_modifier(mech: &Mech) -> i64 {
    (if active_stealth(mech).contains(&"void_signature") { VOID_OWN_ATTACK_MODIFIER } else { 0 }) + crate::advanced_weapons::own_attack_modifier(mech, false)
}
