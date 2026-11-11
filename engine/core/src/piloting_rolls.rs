// Translated from mechsim/piloting_rolls.py (session 22).
//! Piloting Skill Rolls: modifiers, falls, stand-up, Movement and Attack Phase triggers, consciousness checks.
//! Every roll reads `b.piloting` (the Python's config.PILOTING, set per mech by `Battle::with_piloting`).

use std::collections::BTreeSet;

use serde_json::{json, Value};

use crate::battle::{Battle, UnitId};
use crate::damage_resolution::{apply_damage, compute_tmm, tmm_from_mp};
use crate::hit_location::resolve_hit_location;
use crate::mech_state::*;
use crate::pyfmt::Num;

pub const DAMAGE_20_PLUS_MODIFIER: i64 = 1;
pub const LEG_ACTUATOR_DESTROYED_MODIFIER: i64 = 1;
pub const GYRO_HIT_MODIFIER: i64 = 2;
pub const PREEXISTING_ACTUATOR_MODIFIER: i64 = 1;
pub const PREEXISTING_GYRO_HIT_MODIFIER: i64 = 2;
pub const PREEXISTING_LEG_DESTROYED_MODIFIER: i64 = 4;
pub const QUAD_LEG_DESTROYED_MODIFIER: i64 = 1;
pub const STAND_UP_MODIFIER: i64 = -1;
pub const QUAD_PSR_MODIFIER: i64 = -2;
pub const TRIPOD_PSR_MODIFIER: i64 = -1;
pub const HD_GYRO_HIT_MODIFIER: i64 = 1;
pub const HD_GYRO_JUMP_MODIFIER: i64 = 2;
pub const COCKPIT_PSR_MODIFIER: i64 = 1;

fn sorted_set_json(s: impl Iterator<Item = String>) -> Value {
    let mut v: Vec<String> = s.collect();
    v.sort();
    json!(v)
}

fn destroyed_legs_set(m: &Mech) -> BTreeSet<String> {
    m.leg_locations.iter().filter(|l| m.locations[l.as_str()].destroyed).cloned().collect()
}

pub fn snapshot_preexisting_damage(m: &mut Mech) {
    let mut snap = crate::fasthash::IndexMap::default();
    snap.insert("gyro_hits".to_string(), json!(m.gyro_hits));
    snap.insert("destroyed_leg_actuators".to_string(), json!(m.destroyed_leg_actuators));
    snap.insert("destroyed_legs".to_string(), sorted_set_json(destroyed_legs_set(m).into_iter()));
    snap.insert("hip_legs".to_string(), sorted_set_json(m.destroyed_hip_locations.iter().cloned()));
    m.preexisting_damage_snapshot = snap;
}

pub fn snapshot_pre_attack_phase(m: &mut Mech) {
    let mut total = Num::I(0);
    for v in m.locations.values() {
        total = total + v.armor + v.rear_armor.unwrap_or(Num::I(0)) + v.structure;
    }
    let mut snap = crate::fasthash::IndexMap::default();
    snap.insert("total_armor_structure".to_string(), total.to_json());
    snap.insert("gyro_hits".to_string(), json!(m.gyro_hits));
    snap.insert("destroyed_leg_actuators".to_string(), json!(m.destroyed_leg_actuators));
    snap.insert("destroyed_legs".to_string(), sorted_set_json(destroyed_legs_set(m).into_iter()));
    snap.insert("hip_legs".to_string(), sorted_set_json(m.destroyed_hip_locations.iter().cloned()));
    m.pre_attack_phase_snapshot = snap;
}

fn snap_strs(v: &Value) -> BTreeSet<String> {
    v.as_array().map_or_else(BTreeSet::new, |a| a.iter().map(|x| x.as_str().unwrap().to_string()).collect())
}

fn snap_actuators(v: &Value, loc: &str) -> i64 {
    v.get(loc).and_then(|x| x.as_i64()).unwrap_or(0)
}

/// live_hip_legs for a snapshot's sets.
fn live_hip_legs_snap(destroyed: &BTreeSet<String>, hips: &BTreeSet<String>) -> usize {
    hips.iter().filter(|l| !destroyed.contains(*l)).count()
}

pub fn preexisting_modifier(m: &Mech) -> i64 {
    let snap = &m.preexisting_damage_snapshot;
    if snap.is_empty() {
        return 0;
    }
    let mut total = snap["gyro_hits"].as_i64().unwrap() * if has_hd_gyro(m) { HD_GYRO_HIT_MODIFIER } else { PREEXISTING_GYRO_HIT_MODIFIER };
    let destroyed = snap_strs(&snap["destroyed_legs"]);
    for loc in &m.leg_locations {
        if !destroyed.contains(loc) {
            total += snap_actuators(&snap["destroyed_leg_actuators"], loc) * PREEXISTING_ACTUATOR_MODIFIER;
        }
    }
    let lost = destroyed.len() as i64;
    if is_quad(m) {
        total += if lost <= 2 { lost * QUAD_LEG_DESTROYED_MODIFIER } else { PREEXISTING_LEG_DESTROYED_MODIFIER };
        let hips = snap.get("hip_legs").map_or_else(BTreeSet::new, snap_strs);
        if live_hip_legs_snap(&destroyed, &hips) > 0 {
            total -= PREEXISTING_ACTUATOR_MODIFIER;
        }
    } else {
        total += lost * PREEXISTING_LEG_DESTROYED_MODIFIER;
    }
    total
}

pub fn special_case_modifier(m: &Mech) -> i64 {
    let mut total = 0;
    if m.leg_locations.iter().any(|l| m.armor_type.get(l) == Some(&ArmorType::Hardened)) {
        total += 1;
    }
    if (m.mech_type == "quad" || m.mech_type == "quadvee") && destroyed_leg_count(m) == 0 {
        total += QUAD_PSR_MODIFIER;
    }
    if m.mech_type == "tripod" && destroyed_leg_count(m) == 0 {
        total += TRIPOD_PSR_MODIFIER;
    }
    total += tripod_pilot_modifier(m);
    if leg_aes_working(m) {
        total -= 2;
    }
    if has_small_cockpit(m) || has_torso_cockpit(m) {
        total += COCKPIT_PSR_MODIFIER;
    }
    total += torso_cockpit_sensor_penalty(m);
    if matches!(m.taser_interference_until, Some(Some(_))) {
        total += 2;
    }
    if m.modular_armor.iter().any(|id| m.items[*id].modular_points.unwrap_or(0) > 0) {
        total += 1;
    }
    if pilot_unconscious(m) && m.mech_type != "tripod" {
        total += 3;
    }
    total
}

pub fn fall_damage(m: &Mech) -> i64 {
    (m.mass.unwrap() as f64 / 10.0).ceil() as i64
}

/// Shared fall handler: prone, falling damage in 5-point clusters, the seatbelt check.
pub fn resolve_fall(b: &mut Battle, u: UnitId, cause: &str, levels: i64, side: Option<&str>) {
    b.units[u].prone = true;
    let (side, side_note): (String, String) = match side {
        None => {
            let die = b.pick_number(6);
            let s = if die == 1 { "rear" } else { "front" };
            (s.to_string(), format!("1D6 {}: {}", die, s))
        }
        Some(s) => (s.to_string(), s.to_string()),
    };
    let mut total_damage = fall_damage(&b.units[u]) * (levels + 1);
    let divisor = crate::water::fall_damage_divisor(b, u);
    total_damage = crate::pyfmt::py_floordiv(total_damage, divisor);
    let cause_note = if cause.is_empty() { String::new() } else { format!(" ({})", cause) };
    let (chassis, model) = (b.units[u].chassis.clone(), b.units[u].model.clone());
    b.log(format!(
        "FALL{}: {} {} takes {} falling damage{} ({} table, 5-pt clusters).",
        cause_note, chassis, model, total_damage, if divisor > 1 { " (halved: water, p.115)" } else { "" }, side_note
    ));
    let mut remaining = total_damage;
    while remaining > 0 {
        let cluster = remaining.min(5);
        let loc_roll = b.roll_2d6();
        let loc = resolve_hit_location(b, u, loc_roll, &side);
        b.log(format!("  Fall cluster ({} dmg): rolled {} -> {}", cluster, loc_roll, loc));
        apply_damage(b, u, &loc, Num::I(cluster), if side == "rear" { "rear_armor" } else { "armor" }, DamageType::Physical);
        remaining -= cluster;
        if b.is_destroyed(u) {
            return;
        }
    }
    let needed = b.piloting + levels;
    let level_note = if levels != 0 { format!(" (Piloting {} + {} levels)", b.piloting, levels) } else { String::new() };
    if is_immobile(&b.units[u]) || needed > 12 {
        b.units[u].pilot_hits += 1;
        mark_consciousness_check_pending(&mut b.units[u]);
        let why = if is_immobile(&b.units[u]) { "immobile".to_string() } else { format!("needs {}", needed) };
        let ph = b.units[u].pilot_hits;
        b.log(format!("  Seatbelt check: {} - pilot takes 1 hit automatically ({}/6).", why, ph));
    } else {
        let roll = b.roll_2d6();
        if roll < needed {
            b.units[u].pilot_hits += 1;
            mark_consciousness_check_pending(&mut b.units[u]);
            let ph = b.units[u].pilot_hits;
            b.log(format!("  Seatbelt check: needs {}{}. Rolled {}. FAILED - pilot takes 1 hit ({}/6).", needed, level_note, roll, ph));
        } else {
            b.log(format!("  Seatbelt check: needs {}{}. Rolled {}. Pilot unharmed.", needed, level_note, roll));
        }
    }
    if console_active(&b.units[u]) {
        let roll = if is_immobile(&b.units[u]) || needed > 12 { None } else { Some(b.roll_2d6()) };
        if roll.map_or(true, |r| r < needed) {
            let sh = b.units[u].secondary_hits.unwrap_or(0) + 1;
            b.units[u].secondary_hits = Some(sh);
            let how = match roll {
                None => "automatic".to_string(),
                Some(r) => format!("rolled {}", r),
            };
            b.log(format!("  Seatbelt check (command console warrior): {} - takes 1 hit ({}/6).", how, sh));
        }
    }
    crate::hazards::after_fall(b, u);
    b.is_destroyed(u);
}

/// p.110 Multiple Rolls: `count` PSRs one at a time at Piloting + modifier; the first failure is a fall.
pub fn roll_psrs(b: &mut Battle, count: i64, modifier: i64, what: &str) -> bool {
    let needed = b.piloting + modifier;
    for i in 1..=count {
        let roll = b.roll_2d6();
        let idx = if count > 1 { format!(" {}/{}", i, count) } else { String::new() };
        b.log(format!("{}{}: needs {} (Piloting {} + {:+}). Rolled {}.", what, idx, needed, b.piloting, modifier, roll));
        if roll < needed {
            let more = if i < count { format!(" ({} more not rolled.)", count - i) } else { String::new() };
            b.log(format!("  Failed - falls.{}", more));
            return false;
        }
    }
    b.log("  Succeeded - remains standing.");
    true
}

pub fn can_stand(m: &Mech) -> bool {
    if gyro_destroyed(m) {
        return false;
    }
    let legs_lost = destroyed_leg_count(m);
    let arms_lost = ["Left Arm", "Right Arm"].iter().filter(|l| m.locations.get(**l).map_or(false, |x| x.destroyed)).count() as i64;
    if is_quad(m) {
        return legs_lost < 4;
    }
    legs_lost < 2 && !(legs_lost == 1 && arms_lost == 2)
}

/// Which Movement Phase PSR trigger applies moving in `mode` ("running" / "jump"), or None.
pub fn movement_psr_trigger(m: &Mech, mode: &str) -> Option<&'static str> {
    if m.gyro_hits > 0 && (mode == "jump" || !has_hd_gyro(m)) {
        return Some("gyro hit");
    }
    if is_quad(m) {
        return quad_trigger(m, mode);
    }
    if mode == "jump" && m.leg_locations.iter().any(|l| m.destroyed_leg_actuators.get(l).copied().unwrap_or(0) > 0 || m.locations[l.as_str()].destroyed) {
        return Some("leg actuator/leg destroyed while jumping");
    }
    if mode == "running" && m.leg_locations.iter().any(|l| m.destroyed_hip_locations.contains(l) || m.locations[l.as_str()].destroyed) {
        return Some("Hip/leg destroyed while running");
    }
    None
}

fn quad_counts(m: &Mech, mode: &str) -> i64 {
    let lost = destroyed_leg_count(m);
    if mode == "running" {
        return hip_effects(m) + if lost >= 3 { 1 } else { 0 };
    }
    let live: Vec<&String> = m.leg_locations.iter().filter(|l| !m.locations[l.as_str()].destroyed).collect();
    let hips = live_hip_legs(m);
    let damaged: Vec<&&String> = live.iter().filter(|l| m.destroyed_leg_actuators.get(l.as_str()).copied().unwrap_or(0) > if hips.contains(l) { 1 } else { 0 }).collect();
    let hip_only = hips.iter().filter(|l| !damaged.iter().any(|d| ***d == **l)).count() as i64;
    damaged.len() as i64 + 0.max(hip_only - 1) + if lost >= 2 { 1 } else { 0 }
}

fn quad_trigger(m: &Mech, mode: &str) -> Option<&'static str> {
    if (mode == "running" || mode == "jump") && quad_counts(m, mode) != 0 {
        Some("a quad's leg damage")
    } else {
        None
    }
}

/// How many Movement Phase PSRs moving in `mode` forces.
pub fn movement_psr_count(m: &Mech, mode: &str) -> i64 {
    if movement_psr_trigger(m, mode).is_none() {
        return 0;
    }
    let mut count = if m.gyro_hits > 0 && (mode == "jump" || !has_hd_gyro(m)) { 1 } else { 0 };
    if is_quad(m) {
        return count + quad_counts(m, mode);
    }
    for loc in &m.leg_locations {
        if m.locations[loc.as_str()].destroyed {
            count += 1;
        } else if mode == "jump" && m.destroyed_leg_actuators.get(loc).copied().unwrap_or(0) > 0 {
            count += 1;
        } else if mode == "running" && m.destroyed_hip_locations.contains(loc) {
            count += 1;
        }
    }
    count
}

pub fn hd_gyro_jump_adjust(m: &Mech, mode: &str) -> i64 {
    if mode == "jump" && has_hd_gyro(m) && m.gyro_hits > 0 {
        HD_GYRO_JUMP_MODIFIER - m.gyro_hits * HD_GYRO_HIT_MODIFIER
    } else {
        0
    }
}

/// Target number of the Movement Phase PSR this mech would make moving in `mode`, or None.
pub fn movement_psr_target_number(m: &Mech, mode: &str) -> Option<i64> {
    movement_psr_trigger(m, mode)?;
    Some(m.piloting + preexisting_modifier(m) + special_case_modifier(m) + hd_gyro_jump_adjust(m, mode))
}

/// Movement Phase PSR trigger: true if the mech remains standing.
pub fn check_movement_psr(b: &mut Battle, u: UnitId, mode: &str, cause: Option<&str>) -> bool {
    let trigger = match movement_psr_trigger(&b.units[u], mode) {
        None => return true,
        Some(t) => t,
    };
    let m = &b.units[u];
    let modifier = preexisting_modifier(m) + special_case_modifier(m) + hd_gyro_jump_adjust(m, mode);
    let count = movement_psr_count(m, mode);
    if !roll_psrs(b, count, modifier, &format!("Movement Phase PSR ({} mode, {})", mode, trigger)) {
        let c = cause.map(|s| s.to_string()).unwrap_or_else(|| format!("failed Movement Phase PSR ({})", mode));
        resolve_fall(b, u, &c, 0, None);
        return false;
    }
    true
}

/// Movement Phase stand-up retry loop; returns the running MP left (0 if still prone).
pub fn resolve_stand_up(b: &mut Battle, u: UnitId, mp_available: Option<i64>) -> i64 {
    if !can_stand(&b.units[u]) {
        b.log("Cannot stand (destroyed gyro, or too many legs / arms lost - pp.51, 98). Remains prone.");
        return 0;
    }
    if b.units[u].pilot_hits >= 5 {
        b.log("Pilot has 5+ hits - remaining prone rather than risk a stand attempt.");
        return 0;
    }
    let mut running_mp = match mp_available {
        None => compute_running_mp(&b.units[u]),
        Some(m) => m,
    };
    if running_mp <= 0 {
        b.log("No running MP available - cannot attempt to stand (minimum movement rule). Remains prone.");
        return 0;
    }
    let mut attempt = 0;
    loop {
        attempt += 1;
        if attempt > 1 {
            if running_mp < 2 {
                b.log("Insufficient MP (<2) remaining for another stand attempt. Remains prone.");
                return 0;
            }
            if b.units[u].pilot_hits >= 5 {
                b.log("Pilot reached 5 hits from a failed stand attempt - stopping, remains prone.");
                return 0;
            }
        }
        running_mp = 0.max(running_mp - 2);
        let (roll, needed): (Option<i64>, i64);
        if is_quad(&b.units[u]) && destroyed_leg_count(&b.units[u]) == 0 {
            b.log(format!("Stand attempt {}: a quad with no leg destroyed stands without a PSR (p.238).", attempt));
            roll = None;
            needed = 0;
        } else {
            let m = &b.units[u];
            let modifier = preexisting_modifier(m) + special_case_modifier(m) + STAND_UP_MODIFIER;
            needed = b.piloting + modifier;
            let r = b.roll_2d6();
            roll = Some(r);
            b.log(format!("Stand attempt {}: needs {} (Piloting {} + {:+}, incl. -1 for standing). Rolled {}.", attempt, needed, b.piloting, modifier, r));
        }
        if let Some(r) = roll {
            if r < needed {
                b.log("  Failed to stand.");
                resolve_fall(b, u, "failed to stand", 0, None);
                if b.is_destroyed(u) {
                    return 0;
                }
                continue;
            }
        }
        b.units[u].prone = false;
        let (chassis, model) = (b.units[u].chassis.clone(), b.units[u].model.clone());
        b.log(format!("  Success - {} {} is standing (remaining running MP {}).", chassis, model, running_mp));
        if running_mp > 0 {
            b.units[u].movement_mode_this_turn = "running".to_string();
            if !check_movement_psr(b, u, "running", Some("fell again after standing")) {
                b.log("  Will not attempt to stand again this round.");
                return 0;
            }
        }
        return running_mp;
    }
}

/// Called once per turn before the attack loop; returns this turn's TMM.
pub fn resolve_movement_phase(b: &mut Battle, u: UnitId) -> i64 {
    if all_crew_unconscious(&b.units[u]) {
        b.log("All crew unconscious - Movement Phase skipped, TMM -4.");
        return -4;
    }
    if b.units[u].prone {
        let remaining_mp = resolve_stand_up(b, u, None);
        return tmm_from_mp(remaining_mp);
    }
    let tmm = compute_tmm(&mut b.units[u]);
    let mode = b.units[u].movement_mode_this_turn.clone();
    if !check_movement_psr(b, u, &mode, None) {
        return tmm_from_mp(0);
    }
    tmm
}

/// After each attack phase. forced_triggers: extra (reason, modifier) PSR triggers that aren't damage.
pub fn resolve_attack_phase_psr(b: &mut Battle, u: UnitId, forced_triggers: &[(String, i64)]) {
    if b.is_destroyed(u) || b.units[u].prone {
        return;
    }
    let snap = b.units[u].pre_attack_phase_snapshot.clone();
    if snap.is_empty() {
        return;
    }
    let mut modifier = 0;
    let mut rolls = 0;
    let mut automatic_fall = false;

    let mut current_total = Num::I(0);
    for v in b.units[u].locations.values() {
        current_total = current_total + v.armor + v.rear_armor.unwrap_or(Num::I(0)) + v.structure;
    }
    let damage_this_phase = Num::from_json(&snap["total_armor_structure"]) - current_total;
    if damage_this_phase >= Num::I(20) {
        modifier += DAMAGE_20_PLUS_MODIFIER;
        rolls += 1;
        b.log(format!("PSR trigger: {} armor+structure lost this phase (>=20) -> {:+}.", damage_this_phase.py_str(), DAMAGE_20_PLUS_MODIFIER));
    }
    let snap_destroyed = snap_strs(&snap["destroyed_legs"]);
    let legs = b.units[u].leg_locations.clone();
    let mut newly_destroyed: Vec<String> = Vec::new();
    for loc in &legs {
        if snap_destroyed.contains(loc) {
            continue;
        }
        if b.units[u].locations[loc.as_str()].destroyed {
            newly_destroyed.push(loc.clone());
            automatic_fall = true;
            b.log(format!("PSR trigger: {} destroyed this phase -> automatic fall.", loc));
        }
    }
    for loc in &legs {
        if snap_destroyed.contains(loc) || newly_destroyed.contains(loc) {
            continue;
        }
        let mut new_actuators = b.units[u].destroyed_leg_actuators.get(loc).copied().unwrap_or(0) - snap_actuators(&snap["destroyed_leg_actuators"], loc);
        let snap_hips = snap.get("hip_legs").map_or_else(BTreeSet::new, snap_strs);
        if is_quad(&b.units[u]) && new_actuators > 0 && b.units[u].destroyed_hip_locations.contains(loc) && !snap_hips.contains(loc) && live_hip_legs(&b.units[u]).len() == 1 {
            new_actuators -= 1;
        }
        if new_actuators > 0 {
            modifier += new_actuators * LEG_ACTUATOR_DESTROYED_MODIFIER;
            rolls += 1;
            b.log(format!("PSR trigger: {} leg actuator(s) destroyed at {} this phase -> {:+}, one roll.", new_actuators, loc, new_actuators * LEG_ACTUATOR_DESTROYED_MODIFIER));
        }
    }
    let new_gyro_hits = b.units[u].gyro_hits - snap["gyro_hits"].as_i64().unwrap();
    if new_gyro_hits > 0 {
        if gyro_destroyed(&b.units[u]) {
            automatic_fall = true;
            b.log("PSR trigger: Gyro destroyed this phase -> automatic fall.");
        } else if has_hd_gyro(&b.units[u]) {
            modifier += new_gyro_hits * HD_GYRO_HIT_MODIFIER;
            b.log(format!("Heavy-duty gyro hit this phase: no PSR forced, {:+} to any PSR (p.204).", new_gyro_hits * HD_GYRO_HIT_MODIFIER));
        } else {
            modifier += GYRO_HIT_MODIFIER;
            rolls += 1;
            b.log(format!("PSR trigger: Gyro hit this phase -> {:+}.", GYRO_HIT_MODIFIER));
        }
    }
    for (reason, m) in forced_triggers {
        modifier += m;
        rolls += 1;
        b.log(format!("PSR trigger: {} -> {:+}.", reason, m));
    }
    if rolls == 0 && !automatic_fall {
        return;
    }
    modifier += preexisting_modifier(&b.units[u]) + special_case_modifier(&b.units[u]);
    if automatic_fall {
        b.log("Automatic fall this phase.");
        resolve_fall(b, u, "automatic fall", 0, None);
        return;
    }
    if all_crew_unconscious(&b.units[u]) || b.units[u].shutdown {
        let why = if b.units[u].shutdown { "shut down" } else { "all crew unconscious" };
        let mut cap = why.to_string();
        cap = cap[..1].to_uppercase() + &cap[1..].to_lowercase();
        b.log(format!("{} - Attack Phase PSR auto-fails.", cap));
        resolve_fall(b, u, &format!("auto-fail ({})", why), 0, None);
        return;
    }
    if !roll_psrs(b, rolls, modifier, "Attack Phase PSR") {
        resolve_fall(b, u, "failed Attack Phase PSR", 0, None);
    }
}

fn capitalize(s: &str) -> String {
    let mut c = s.chars();
    match c.next() {
        None => String::new(),
        Some(f) => f.to_uppercase().collect::<String>() + &c.as_str().to_lowercase(),
    }
}

/// Consciousness checks after the Movement / Attack Phase PSR step.
pub fn resolve_consciousness_checks(b: &mut Battle, u: UnitId, phase_label: &str) {
    if b.is_destroyed(u) {
        return;
    }
    let roles: Vec<String> = b.units[u].crew.keys().cloned().collect();
    for role in roles {
        if !b.units[u].crew[&role].check_pending {
            continue;
        }
        b.units[u].crew.get_mut(&role).unwrap().check_pending = false;
        let hits = b.units[u].pilot_hits;
        if hits >= 6 {
            // Found by Hydra's first trials (2026-11-11): a unit with several crew can reach 6 hits and still be standing
            // (is_destroyed did not end it); the Python raised here. Loud placeholder until Daniel rules: that crew
            // member is out for good, no roll.
            let nm = b.units[u].side_name.clone().unwrap_or_default();
            b.warn_stub("crew_six_hits", &format!("{}: {} has {} hits and the unit still stands - counted as out, no consciousness roll", nm, role, hits));
            b.units[u].crew.get_mut(&role).unwrap().unconscious = true;
            b.log(format!("{} consciousness check ({}, {} pilot hits): no roll, out for the battle.", phase_label, role, hits));
            continue;
        }
        let needed = consciousness_target_number(hits).unwrap_or_else(|e| panic!("{}", e));
        let roll = b.roll_2d6();
        b.log(format!("{} consciousness check ({}, {} pilot hits): needs {}. Rolled {}.", phase_label, role, hits, needed, roll));
        if roll < needed {
            let st = b.units[u].crew.get_mut(&role).unwrap();
            st.unconscious = true;
            st.went_out_this_turn = true;
            b.log(format!("  {} knocked unconscious.", capitalize(&role)));
        } else {
            b.log(format!("  {} stays conscious.", capitalize(&role)));
        }
    }
}

/// End Phase wake-up rolls (1-turn decay).
pub fn resolve_end_phase_wakeup(b: &mut Battle, u: UnitId) {
    if b.is_destroyed(u) {
        return;
    }
    let roles: Vec<String> = b.units[u].crew.keys().cloned().collect();
    for role in &roles {
        let st = b.units[u].crew[role].clone();
        if st.unconscious && !st.went_out_this_turn {
            let hits = b.units[u].pilot_hits;
            let needed = consciousness_target_number(hits).unwrap_or_else(|e| panic!("{}", e));
            let roll = b.roll_2d6();
            b.log(format!("End Phase wake-up check ({}, {} pilot hits): needs {}. Rolled {}.", role, hits, needed, roll));
            if roll >= needed {
                b.units[u].crew.get_mut(role).unwrap().unconscious = false;
                b.log(format!("  {} wakes up.", capitalize(role)));
            } else {
                b.log(format!("  {} remains unconscious.", capitalize(role)));
            }
        }
    }
    for st in b.units[u].crew.values_mut() {
        st.went_out_this_turn = false;
    }
}
