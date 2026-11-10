// Translated from INTEGRATION__physical_gear.py (session 22): talons, spikes, lances, vibroblades, shields.
use std::collections::BTreeSet;

use serde_json::Value;

use crate::battle::{Battle, UnitId};
use crate::damage_resolution::{apply_damage, explosion_structure, resolve_slot_hit};
use crate::equipment::{ItemId, Slot};
use crate::mech_state::{is_destroyed, mech_shields, shield_row, DamageType, Mech, SlotInfo};
use crate::pyfmt::Num;

pub const SPIKE_REDUCTION: i64 = 4;
pub const SPIKE_RETALIATION: i64 = 2;
pub const SPIKE_CHARGE_BONUS: i64 = 2;
pub const TALON_MULTIPLIER: f64 = 1.5;
pub const LANCE_AP_TN: i64 = 9;
pub const LANCE_CHARGE_AP_TN: i64 = 5;
pub const TORSOS: [&str; 3] = ["Left Torso", "Right Torso", "Center Torso"];

fn norm(name: &str) -> String {
    name.replace(' ', "").replace('-', "").to_uppercase()
}

/// Live Equipment in `loc` whose name holds `fragment`, one per instance (first-slot order).
fn live(mech: &Mech, loc: &str, fragment: &str) -> Vec<ItemId> {
    let mut seen: Vec<ItemId> = Vec::new();
    for s in mech.crits.get(loc).into_iter().flatten() {
        if let Slot::Item(i) = s {
            if norm(&mech.items[*i].name).contains(fragment) && !seen.contains(i) {
                seen.push(*i);
            }
        }
    }
    seen
}

fn foot_lost(mech: &Mech, leg: &str) -> bool {
    mech.destroyed_slot_info.iter().any(|((l, _), info)| l == leg && info.name == "Foot Actuator")
}

// ---- talons ---------------------------------------------------------------------------------------------------------
pub fn talon_legs(mech: &Mech) -> Vec<String> {
    mech.leg_locations.iter().filter(|leg| !mech.locations[leg.as_str()].destroyed && !live(mech, leg, "TALONS").is_empty() && !foot_lost(mech, leg)).cloned().collect()
}

pub fn dfa_talons(mech: &Mech) -> bool {
    let need = if mech.leg_locations.len() > 2 { 2 } else { mech.leg_locations.len() };
    talon_legs(mech).len() >= need
}

pub fn with_talons(damage: i64) -> i64 {
    (damage as f64 * TALON_MULTIPLIER + 0.5) as i64
}

// ---- spikes -----------------------------------------------------------------------------------------------------------
pub fn spike_clusters(mech: &Mech, loc: &str) -> usize {
    live(mech, loc, "SPIKES").len()
}

pub fn torso_spike_clusters(mech: &Mech) -> usize {
    TORSOS.iter().filter(|t| mech.locations.contains_key(**t)).map(|t| spike_clusters(mech, t)).sum()
}

/// p.196: a physical attack's damage to a spiked location -4, minimum 1. Returns (damage, spiked?).
pub fn spike_reduce(b: &mut Battle, target: UnitId, loc: &str, damage: i64, label: &str) -> (i64, bool) {
    if damage <= 0 || spike_clusters(&b.units[target], loc) == 0 {
        return (damage, false);
    }
    let cut = 1.max(damage - SPIKE_REDUCTION);
    let line = format!(
        "      Spikes at {}'s {}: {} -> {}{} (p.196).",
        b.units[target].side_name.clone().unwrap_or_default(),
        loc,
        damage,
        cut,
        if label.is_empty() { String::new() } else { format!(" ({})", label) }
    );
    b.log(line);
    (cut, true)
}

/// p.196: the attacker takes 2 damage split evenly over the location(s) that delivered the attack.
pub fn spike_retaliation(b: &mut Battle, attacker: UnitId, delivered_by: &[&str]) {
    let locs: Vec<&str> = delivered_by.iter().copied().filter(|l| b.units[attacker].locations.contains_key(*l)).collect();
    if locs.is_empty() {
        return;
    }
    let share = SPIKE_RETALIATION / locs.len() as i64;
    for loc in locs {
        if b.is_destroyed(attacker) {
            return;
        }
        let line = format!("      Spikes: {} takes {} to its {} (p.196).", b.units[attacker].side_name.clone().unwrap_or_default(), share, loc);
        b.log(line);
        apply_damage(b, attacker, loc, Num::I(share), "armor", DamageType::Physical);
    }
}

/// The declared choice (p.196) - only a 'Mech with torso spikes has it.
pub fn use_spikes_in_charge(b: &mut Battle, attacker: UnitId) -> bool {
    let clusters = torso_spike_clusters(&b.units[attacker]);
    if clusters == 0 {
        return false;
    }
    let name = b.units[attacker].side_name.clone().unwrap_or_default();
    crate::stubs::stub_charge_spikes(b, &name, clusters as i64)
}

pub fn charge_spike_bonus(attacker: &Mech, used: bool) -> i64 {
    if used { SPIKE_CHARGE_BONUS * torso_spike_clusters(attacker) as i64 } else { 0 }
}

/// p.196: offensive spikes - each time a spiked location takes damage from the charge, 1D6: on a 1 one cluster there
/// is destroyed.
pub fn spike_wear(b: &mut Battle, attacker: UnitId, loc: &str) {
    let clusters = live(&b.units[attacker], loc, "SPIKES");
    if clusters.is_empty() {
        return;
    }
    let die = b.pick_number(6);
    if die == 1 {
        let spike = clusters[0];
        let idx = b.units[attacker].crits[loc].iter().position(|s| *s == Slot::Item(spike)).unwrap();
        let line = format!("      Spikes at {}'s {}: 1D6 1 - the cluster is destroyed (p.196).", b.units[attacker].side_name.clone().unwrap_or_default(), loc);
        b.log(line);
        resolve_slot_hit(b, attacker, loc, idx, &Slot::Item(spike), 1, 1);
    }
}

// ---- lance --------------------------------------------------------------------------------------------------------------
pub fn lances(mech: &Mech) -> Vec<ItemId> {
    ["Left Arm", "Right Arm"].iter().flat_map(|arm| live(mech, arm, "LANCE")).collect()
}

/// p.194: 2D6 >= tn deals 1 point of internal structure damage to `loc` (no TSM) and so a critical-hit check.
pub fn lance_ap_check(b: &mut Battle, target: UnitId, loc: &str, tn: i64, why: &str) {
    if b.is_destroyed(target) || b.units[target].locations[loc].destroyed {
        return;
    }
    let roll = b.roll_2d6();
    let name = b.units[target].side_name.clone().unwrap_or_default();
    if roll < tn {
        b.log(format!("      Lance armor-piercing check ({}): needs {}, rolled {} - no effect (p.194).", why, tn, roll));
        return;
    }
    b.log(format!("      Lance armor-piercing check ({}): needs {}, rolled {} - 1 point to {}'s {} internal structure (p.194).", why, tn, roll, name, loc));
    explosion_structure(b, target, loc, Num::I(1), 0);
}

/// True if a hit on `loc` took armor but no internal structure: `before` = (armor + rear armor, structure).
pub fn armor_only(target: &Mech, loc: &str, before: (Num, Num)) -> bool {
    let v = &target.locations[loc];
    let armor_now = v.armor + v.rear_armor.unwrap_or(Num::I(0));
    armor_now < before.0 && v.structure == before.1
}

pub fn snapshot(target: &Mech, loc: &str) -> (Num, Num) {
    let v = &target.locations[loc];
    (v.armor + v.rear_armor.unwrap_or(Num::I(0)), v.structure)
}

// ---- vibroblades --------------------------------------------------------------------------------------------------------
pub fn vibro_row(size: &str) -> (i64, i64) {
    match size {
        "SMALL" => (7, 3),
        "MEDIUM" => (10, 5),
        "LARGE" => (14, 7),
        other => panic!("KeyError: {}", other),
    }
}

pub fn vibro_size(mech: &Mech, slot: ItemId) -> &'static str {
    let n = norm(&mech.items[slot].name);
    ["SMALL", "MEDIUM", "LARGE"].into_iter().find(|s| n.contains(s)).unwrap_or("MEDIUM")
}

/// (damage, heat, activated?) for a vibroblade attack.
pub fn vibro_attack(b: &mut Battle, u: UnitId, slot: ItemId, deactivated_damage: i64, tsm: bool) -> (i64, i64, bool) {
    let (damage, heat) = vibro_row(vibro_size(&b.units[u], slot));
    let name = b.units[u].side_name.clone().unwrap_or_default();
    let blade = b.units[u].items[slot].name.clone();
    if crate::stubs::stub_vibroblade(b, &name, &blade, false) {
        return (damage, heat, true);
    }
    (deactivated_damage.min(damage) * if tsm { 2 } else { 1 }, 0, false)
}

// ---- shields -------------------------------------------------------------------------------------------------------------
pub fn shield_bash_for(size: &str) -> i64 {
    match size {
        "SMALL" => 1,
        "MEDIUM" => 2,
        "LARGE" => 3,
        other => panic!("KeyError: {}", other),
    }
}

fn side_of(arm: &str) -> (&'static str, &'static str) {
    if arm == "Left Arm" { ("Left Torso", "Left Leg") } else { ("Right Torso", "Right Leg") }
}

/// The shield's Damage Capacity left (kept on the Equipment instance).
fn capacity(b: &mut Battle, u: UnitId, shield: ItemId, size: &str) -> i64 {
    if b.units[u].items[shield].shield_dc.is_none() {
        b.units[u].items[shield].shield_dc = Some(shield_row(size).2);
    }
    b.units[u].items[shield].shield_dc.unwrap()
}

/// The arm whose shield is raised this phase, or None.
pub fn raised_arm(mech: &Mech) -> Option<String> {
    mech.shield_raised.as_ref().and_then(|v| v.as_str()).map(|s| s.to_string())
}

/// Locations a RAISED shield on `arm` protects (p.195).
pub fn covered(mech: &Mech, arm: &str) -> BTreeSet<String> {
    let (torso, leg) = side_of(arm);
    let mut locs: Vec<&str> = vec![arm, "Center Torso", torso];
    if mech.mech_type != "tripod" || leg != "Center Leg" {
        locs.push(leg);
    }
    locs.into_iter().filter(|l| mech.locations.contains_key(*l)).map(|s| s.to_string()).collect()
}

/// Start of an attack phase: raise a shield? Sets mech.shield_raised for this phase and returns it.
pub fn declare_raise(b: &mut Battle, u: UnitId, phase: &str) -> Option<String> {
    b.units[u].shield_raised = Some(Value::Null);
    let mut shields: Vec<String> = Vec::new();
    for (arm, s, size) in mech_shields(&b.units[u]) {
        if capacity(b, u, s, size) > 0 {
            shields.push(arm);
        }
    }
    if !shields.is_empty() && !b.units[u].prone {
        let name = b.units[u].side_name.clone().unwrap_or_default();
        if let Some(arm) = crate::stubs::stub_raise_shield(b, &name, phase, &shields) {
            b.units[u].shield_raised = Some(Value::String(arm.clone()));
            b.log(format!("  [{}] {} raises its {} shield (p.195).", phase, name, arm));
        }
    }
    raised_arm(&b.units[u])
}

pub fn lower(mech: &mut Mech) {
    mech.shield_raised = Some(Value::Null);
}

/// Locations that can't attack this phase behind a raised shield (p.195).
pub fn raised_blocks(mech: &Mech) -> BTreeSet<String> {
    match raised_arm(mech) {
        Some(arm) => covered(mech, &arm),
        None => BTreeSet::new(),
    }
}

/// Damage from outside to `loc` after the target's shields (p.195). Rear-hit-zone attacks bypass them.
pub fn shield_absorb(b: &mut Battle, target: UnitId, loc: &str, damage: i64, side: &str) -> i64 {
    if damage <= 0 || side == "rear" {
        return damage;
    }
    let raised = raised_arm(&b.units[target]);
    for (arm, shield, size) in mech_shields(&b.units[target]) {
        if loc != arm && !(raised.as_deref() == Some(arm.as_str()) && covered(&b.units[target], &arm).contains(loc)) {
            continue;
        }
        let dc = capacity(b, target, shield, size);
        if dc <= 0 {
            continue;
        }
        let took = damage.min(shield_row(size).1).min(dc);
        b.units[target].items[shield].shield_dc = Some(dc - took);
        let line = format!(
            "      {}'s {} shield ({}) absorbs {} of {} at {} (capacity left {}, p.195).",
            b.units[target].side_name.clone().unwrap_or_default(),
            size.to_lowercase(),
            arm,
            took,
            damage,
            loc,
            dc - took
        );
        b.log(line);
        if dc - took <= 0 {
            wreck(b, target, &arm, shield);
        }
        return damage - took;
    }
    damage
}

/// A shield whose Damage Capacity is used up is gone (its slots destroyed).
fn wreck(b: &mut Battle, u: UnitId, arm: &str, shield: ItemId) {
    let line = format!("      {}'s {} shield is destroyed (capacity used up).", b.units[u].side_name.clone().unwrap_or_default(), arm);
    b.log(line);
    let name = b.units[u].items[shield].name.clone();
    let m = &mut b.units[u];
    let n = m.crits[arm].len();
    for idx in 0..n {
        if m.crits[arm][idx] == Slot::Item(shield) {
            m.destroyed_slot_info.insert((arm.to_string(), idx), SlotInfo { name: name.clone(), instance_id: Some(shield) });
            m.crits.get_mut(arm).unwrap()[idx] = Slot::name("DESTROYED");
        }
    }
    if raised_arm(m).as_deref() == Some(arm) {
        m.shield_raised = Some(Value::Null);
    }
}

/// +damage to a punch with `arm` from its shield (p.195).
pub fn shield_bash(mech: &Mech, arm: &str) -> i64 {
    mech_shields(mech).iter().filter(|(a, _, _)| a == arm).map(|(_, _, size)| shield_bash_for(size)).sum()
}

#[allow(dead_code)]
fn _unused(_: &Mech) {
    let _ = is_destroyed;
}
