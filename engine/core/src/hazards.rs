// Translated from INTEGRATION__hazards.py (session 22): TO:AR magma, hazardous liquid, bogging down.
use crate::battle::{Battle, UnitId};
use crate::damage_resolution::apply_damage;
use crate::hit_location::resolve_hit_location;
use crate::mech_state::*;
use crate::terrain_rules::{magma_state, MAGMA_CRUST, MAGMA_LIQUID};

pub const CRUST_BREAKS_GROUND: i64 = 6;
pub const CRUST_BREAKS_JUMP: i64 = 4;
pub const POOL_GROUPING: i64 = 5;
pub const STUCK_TO_HIT: i64 = -2;

pub fn magma_at(b: &Battle, label: Option<&str>) -> Option<String> {
    let info = b.board.hexes.get(label?)?;
    magma_state(&info.features).map(|s| s.to_string())
}

pub fn pool_at(b: &Battle, label: Option<&str>) -> bool {
    label.and_then(|l| b.board.hexes.get(l)).map_or(false, |i| i.features.has("hazardous_liquid"))
}

/// The hex's Piloting modifier (p.30): magma crust +1, liquid +4.
pub fn psr_modifier(b: &Battle, label: Option<&str>) -> i64 {
    match magma_at(b, label).as_deref() {
        Some(MAGMA_CRUST) => 1,
        Some(MAGMA_LIQUID) => 4,
        _ => 0,
    }
}

pub fn is_stuck(m: &Mech) -> bool {
    matches!(m.stuck, Some(Some(_)))
}

pub fn bogs_down(b: &Battle, label: Option<&str>) -> bool {
    magma_at(b, label).as_deref() == Some(MAGMA_LIQUID)
}

fn d6(b: &mut Battle) -> i64 {
    b.pick_number(6)
}

/// Locations liquid magma reaches (p.35): (location, armor field) pairs.
fn exposed(m: &Mech, prone: bool) -> Vec<(String, &'static str)> {
    let mut out = Vec::new();
    for (loc, entry) in &m.locations {
        if entry.destroyed {
            continue;
        }
        if !prone && !m.leg_locations.contains(loc) {
            continue;
        }
        out.push((loc.clone(), "armor"));
        if prone && entry.rear_armor.is_some() {
            out.push((loc.clone(), "rear_armor"));
        }
    }
    out
}

/// Damage outside the attack phases counts toward the damage-triggered Piloting rolls, resolved straight after.
fn with_damage_psr(b: &mut Battle, u: UnitId, apply: &mut dyn FnMut(&mut Battle)) {
    if b.units[u].prone || b.hazards_in_phase {
        apply(b);
        return;
    }
    crate::piloting_rolls::snapshot_pre_attack_phase(&mut b.units[u]);
    apply(b);
    if !b.is_destroyed(u) {
        b.with_piloting(u, |b| crate::piloting_rolls::resolve_attack_phase_psr(b, u, &[]));
    }
}

/// 2D6 to each exposed location, one attack (p.35).
pub fn magma_burn(b: &mut Battle, u: UnitId, why: &str) {
    let spots = exposed(&b.units[u], b.units[u].prone);
    if spots.is_empty() || b.is_destroyed(u) {
        return;
    }
    let why = why.to_string();
    with_damage_psr(b, u, &mut |b: &mut Battle| {
        let mut rolls: Vec<String> = Vec::new();
        for (loc, field) in &spots {
            if b.is_destroyed(u) || b.units[u].locations[loc.as_str()].destroyed {
                continue;
            }
            let dmg = b.roll_2d6();
            rolls.push(format!("{}{} {}", loc, if *field == "rear_armor" { " (rear)" } else { "" }, dmg));
            apply_damage(b, u, loc, crate::pyfmt::Num::I(dmg), field, DamageType::Ballistic);
        }
        let name = b.units[u].side_name.clone().unwrap_or_default();
        b.log(format!("    {}: {} - liquid magma burns {} (2D6 each, TO:AR p.35).", name, why, rolls.join(", ")));
    });
}

/// One roll on the Hazardous Liquid Pools Table (p.47).
pub fn pool_damage(b: &mut Battle, u: UnitId, why: &str) {
    if b.is_destroyed(u) {
        return;
    }
    let roll = d6(b);
    let (dmg, what): (i64, &str) = if roll <= 2 {
        (0, "Class 0: normal")
    } else if roll == 3 {
        (d6(b) / 2, "Class 1: slightly hazardous")
    } else if roll == 4 {
        (d6(b), "Class 2: hazardous")
    } else if roll == 5 {
        (d6(b) + 2, "Class 3: extreme danger")
    } else {
        (b.roll_2d6(), "deadly")
    };
    let name = b.units[u].side_name.clone().unwrap_or_default();
    b.log(format!("    {}: {} - hazardous liquid roll {} ({}): {} damage (TO:AR p.47).", name, why, roll, what, dmg));
    if dmg <= 0 {
        return;
    }
    let st = crate::water::state(b, u);
    let legs_only = st == crate::water::PARTIAL || st == crate::water::WADING;
    with_damage_psr(b, u, &mut |b: &mut Battle| {
        let mut left = dmg;
        while left > 0 && !b.is_destroyed(u) {
            let group = left.min(POOL_GROUPING);
            left -= group;
            let loc: String;
            if legs_only {
                let legs: Vec<String> = b.units[u].leg_locations.iter().filter(|l| !b.units[u].locations[l.as_str()].destroyed).cloned().collect();
                if legs.is_empty() {
                    return;
                }
                let pick = b.pick_number(legs.len() as i64);
                loc = legs[(pick - 1) as usize].clone();
            } else {
                let r = b.roll_2d6();
                loc = resolve_hit_location(b, u, r, "front");
            }
            apply_damage(b, u, &loc, crate::pyfmt::Num::I(group), "armor", DamageType::Ballistic);
        }
    });
}

/// A 'Mech has just entered `label`. Returns "stuck" when it bogs down.
pub fn enter_hex(b: &mut Battle, u: UnitId, label: &str, jumped: bool, why: Option<&str>, in_phase: bool) -> Option<&'static str> {
    b.hazards_in_phase = in_phase;
    let r = enter_hex_inner(b, u, label, jumped, why);
    b.hazards_in_phase = false;
    r
}

fn enter_hex_inner(b: &mut Battle, u: UnitId, label: &str, jumped: bool, why: Option<&str>) -> Option<&'static str> {
    if b.is_destroyed(u) {
        return None;
    }
    if !b.board.hexes.contains_key(label) {
        return None;
    }
    let why = why.map(|s| s.to_string()).unwrap_or_else(|| if jumped { format!("landed in {}", label) } else { format!("entered {}", label) });
    let mut state: Option<String> = magma_state(&b.board.hexes[label].features).map(|s| s.to_string());
    if state.as_deref() == Some(MAGMA_CRUST) {
        let roll = d6(b);
        if roll >= if jumped { CRUST_BREAKS_JUMP } else { CRUST_BREAKS_GROUND } {
            b.board.hexes.get_mut(label).unwrap().features.0.insert("magma".to_string(), vec![MAGMA_LIQUID.to_string()]);
            b.broken_crust.push(label.to_string());
            state = Some(MAGMA_LIQUID.to_string());
            let name = b.units[u].side_name.clone().unwrap_or_default();
            b.log(format!("    {}: the magma crust at {} breaks (1D6 {}) - liquid magma for the rest of the battle (TO:AR p.34).", name, label, roll));
        }
    }
    if let Some(s) = &state {
        b.units[u].magma_entered.get_or_insert_with(Vec::new).push((label.to_string(), s.clone()));
    }
    if state.as_deref() == Some(MAGMA_LIQUID) {
        magma_burn(b, u, &why);
        if !b.is_destroyed(u) && !b.units[u].prone && !is_stuck(&b.units[u]) && bog_down_roll(b, u, label, "entering liquid magma") {
            return Some("stuck");
        }
    }
    if b.board.hexes[label].features.has("hazardous_liquid") {
        pool_damage(b, u, &why);
    }
    None
}

/// The Piloting roll on entering a bog hex (p.60). True = stuck (it doesn't fall).
pub fn bog_down_roll(b: &mut Battle, u: UnitId, label: &str, what: &str) -> bool {
    let modifier = crate::piloting_rolls::preexisting_modifier(&b.units[u]) + crate::piloting_rolls::special_case_modifier(&b.units[u]) + psr_modifier(b, Some(label));
    let name = b.units[u].side_name.clone().unwrap_or_default();
    let ok = b.with_piloting(u, |b| crate::piloting_rolls::roll_psrs(b, 1, modifier, &format!("[Movement] {}: bog-down roll, {} at {}", name, what, label)));
    if ok {
        return false;
    }
    let by_jump = b.units[u].move_mode == "Jump";
    b.units[u].stuck = Some(Some(Stuck { rolls: 1, prone_stage: false, by_jump, stand_only: None }));
    b.log(format!("    {} is STUCK in {} (bogged down, TO:AR p.60): no more movement this turn.", name, label));
    true
}

/// Start of the 'Mech's Movement Phase: liquid magma and pools hurt; a stuck 'Mech tries to get free.
pub fn start_of_movement(b: &mut Battle, u: UnitId) {
    b.units[u].magma_entered = Some(Vec::new());
    let hex = b.units[u].hex.clone();
    b.units[u].started_in_liquid = Some(magma_at(b, hex.as_deref()).as_deref() == Some(MAGMA_LIQUID));
    if hex.is_none() || b.is_destroyed(u) {
        return;
    }
    let h = hex.clone().unwrap();
    if b.units[u].started_in_liquid == Some(true) {
        magma_burn(b, u, &format!("starts its Movement Phase in liquid magma at {}", h));
    }
    if pool_at(b, hex.as_deref()) && !b.is_destroyed(u) {
        pool_damage(b, u, &format!("starts its Movement Phase in a hazardous liquid pool at {}", h));
    }
    if is_stuck(&b.units[u]) && !b.is_destroyed(u) {
        free_roll(b, u);
    }
}

/// The roll to break free (p.60), at the hex's modifier.
pub fn free_roll(b: &mut Battle, u: UnitId) {
    {
        let prone = b.units[u].prone;
        let st = b.units[u].stuck.as_mut().unwrap().as_mut().unwrap();
        if st.prone_stage && !prone {
            st.prone_stage = false;
        }
    }
    let hex = b.units[u].hex.clone();
    let modifier = crate::piloting_rolls::preexisting_modifier(&b.units[u]) + crate::piloting_rolls::special_case_modifier(&b.units[u]) + psr_modifier(b, hex.as_deref());
    let prone_stage = b.units[u].stuck.as_ref().unwrap().as_ref().unwrap().prone_stage;
    let what = if prone_stage { "free itself from the stuck prone position" } else { "break free" };
    let name = b.units[u].side_name.clone().unwrap_or_default();
    let hx = hex.clone().unwrap_or_default();
    let ok = b.with_piloting(u, |b| crate::piloting_rolls::roll_psrs(b, 1, modifier, &format!("[Movement] {}: roll to {} at {}", name, what, hx)));
    if !ok {
        b.log(format!("    {} stays stuck at {} (TO:AR p.60; no fall).", name, hx));
        return;
    }
    if prone_stage {
        let st = b.units[u].stuck.as_mut().unwrap().as_mut().unwrap();
        st.prone_stage = false;
        st.stand_only = Some(true);
        b.log(format!("    {} frees itself from the stuck prone position - it may stand, then must still break free next turn.", name));
        return;
    }
    b.units[u].stuck = Some(None);
    b.log(format!("    {} breaks free at {}.", name, hx));
}

pub fn can_ground_move(m: &Mech) -> bool {
    !is_stuck(m)
}

/// p.60: stuck after non-jumping movement - it may jump out instead.
pub fn can_jump_out(m: &Mech) -> bool {
    match &m.stuck {
        Some(Some(s)) => !s.by_jump && !s.prone_stage && !m.prone,
        _ => false,
    }
}

pub fn end_of_movement(b: &mut Battle, u: UnitId) {
    if b.units[u].hex.is_none() || b.is_destroyed(u) {
        return;
    }
    let prone = b.units[u].prone;
    if let Some(Some(st)) = b.units[u].stuck.as_mut() {
        if st.stand_only.is_some() && !prone {
            st.stand_only = None;
        }
    }
    let hex = b.units[u].hex.clone();
    if b.units[u].started_in_liquid == Some(true) && magma_at(b, hex.as_deref()).as_deref() == Some(MAGMA_LIQUID) {
        magma_burn(b, u, &format!("starts and ends its Movement Phase in liquid magma ({})", hex.unwrap()));
    }
}

/// A stuck 'Mech jumped: it is free (p.60).
pub fn jumped_out(b: &mut Battle, u: UnitId) {
    if is_stuck(&b.units[u]) && b.units[u].move_mode == "Jump" {
        b.units[u].stuck = Some(None);
        let name = b.units[u].side_name.clone().unwrap_or_default();
        b.log(format!("    {} jumps clear of the bog.", name));
    }
}

/// This turn's magma heat (p.35).
pub fn magma_heat(b: &mut Battle, u: UnitId) -> i64 {
    if b.is_destroyed(u) || b.units[u].hex.is_none() {
        return 0;
    }
    let hex = b.units[u].hex.clone();
    let here = magma_at(b, hex.as_deref());
    let mut total = 0;
    for (label, state) in b.units[u].magma_entered.clone().unwrap_or_default() {
        if Some(&label) != hex.as_ref() {
            total += if state == MAGMA_CRUST { 2 } else { 5 };
        }
    }
    if let Some(h) = here {
        total += if h == MAGMA_CRUST { 5 } else { 10 };
    }
    b.units[u].magma_entered = Some(Vec::new());
    total
}

/// A 'Mech fell (piloting_rolls.resolve_fall): in liquid magma every location is exposed, and it is stuck.
pub fn after_fall(b: &mut Battle, u: UnitId) {
    let hex = b.units[u].hex.clone();
    if b.is_destroyed(u) || magma_at(b, hex.as_deref()).as_deref() != Some(MAGMA_LIQUID) {
        return;
    }
    let h = hex.unwrap();
    magma_burn(b, u, &format!("fell in liquid magma at {}", h));
    if !b.is_destroyed(u) {
        b.units[u].stuck = Some(Some(Stuck { rolls: 1, prone_stage: true, by_jump: false, stand_only: None }));
        let name = b.units[u].side_name.clone().unwrap_or_default();
        b.log(format!("    {} fell in liquid magma - STUCK (TO:AR p.61: free the prone 'Mech, stand, then free it from the hex).", name));
    }
}

/// Expected damage of STARTING next turn's Movement Phase in `label` (movement scoring).
pub fn stay_damage(b: &Battle, u: UnitId, label: &str) -> f64 {
    match b.board.hexes.get(label) {
        None => 0.0,
        Some(info) => crate::terrain_rules::step_hazard(info, b.units[u].leg_locations.len() as i64),
    }
}
