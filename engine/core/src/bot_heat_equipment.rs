//! T16 step 1: Princess's and CASPAR's heat-equipment manager, a port of MegaMek's `BotHeatEquipmentManager` (the class
//! `BotClient` runs in the End Phase for every Princess-family bot, MegaMek/megamek#8802). Until now this engine treated
//! every concealment system as ON whenever it could work and ran the radical heat sink on a fixed cycle
//! (`STUB_ESCALATING_USE`); a Princess / CASPAR unit now decides as MegaMek's bot does:
//!   * stealth armor (`toggleStealthArmor` / `desiredStealthMode`): off when the unit is running hot (a random trigger of
//!     13..=19), or when most of the (visible) enemy by BV is close (average range <= 5..=9); a heat-activated TSM unit
//!     keeps it on while closing and drops it adjacent to an enemy;
//!   * Chameleon, Null and Void Signature (`toggleConcealmentSystems`, `decideHeatLoadAction`): off at 14+ heat, back on at
//!     5 or less, left alone between (so a unit near the shed point does not flap);
//!   * the radical heat sink (`manageRadicalHeatSink`): on while the unit is at 14+ heat AND the next use's failure target
//!     is 7 or lower (three uses in a row: 3+, 5+, 7+), off otherwise.
//! Not ported: Nova CEWS (no engine rule). Gladiator and Hydra keep "always on" (Daniel, 2026-11-20): their units never get
//! `heat_managed`, so nothing here touches them. Dice: the two `Compute.randomInt` draws come from the battle's dice, and
//! only for a Princess-family unit carrying stealth armor, so a battle with none draws nothing (see the Change Record).
use crate::battle::{Battle, UnitId};
use crate::equipment_systems as equip;

/// MegaMek BotHeatEquipmentManager.SHED_HEAT_THRESHOLD: shutdown rolls begin here.
pub const SHED_HEAT_THRESHOLD: i64 = 14;
/// MegaMek BotHeatEquipmentManager.RESTORE_HEAT_THRESHOLD: below the first movement penalty.
pub const RESTORE_HEAT_THRESHOLD: i64 = 5;
/// MegaMek BotHeatEquipmentManager.BEST_ODDS_TARGET_NUMBER: highest 2d6 target still better than even.
pub const BEST_ODDS_TARGET_NUMBER: i64 = 7;

/// The concealment systems `toggleConcealmentSystems` handles, in MegaMek's order.
const CONCEALMENT: [&str; 3] = ["null_signature", "void_signature", "chameleon"];

/// A Princess-family unit starts to be managed (its radical heat sink off, everything else on) at the first Movement
/// Phase, before any Heat Phase can use the old cycle.
pub fn begin_battle(b: &mut Battle) {
    for u in 0..b.units.len() {
        if b.units[u].is_princess_family() && !b.units[u].heat_managed {
            b.units[u].heat_managed = true;
            b.units[u].systems_off.clear();
            b.units[u].radical_on = false;
        }
    }
}

/// BotHeatEquipmentManager.manageOwnedUnits: the End Phase review of every Princess-family unit.
pub fn manage_owned_units(b: &mut Battle) {
    begin_battle(b);
    for u in 0..b.units.len() {
        if !b.units[u].is_princess_family() || b.units[u].destroyed {
            continue;
        }
        toggle_stealth_armor(b, u);
        toggle_concealment_systems(b, u);
        manage_radical_heat_sink(b, u);
    }
}

fn set_system(b: &mut Battle, u: UnitId, kind: &str, on: bool) {
    let off = &mut b.units[u].systems_off;
    let was_on = !off.iter().any(|k| k == kind);
    if on && !was_on {
        off.retain(|k| k != kind);
    } else if !on && was_on {
        off.push(kind.to_string());
    }
    if on != was_on {
        let (name, heat) = (b.units[u].side_name.clone().unwrap_or_default(), b.units[u].current_heat);
        b.log(format!("    {}: {} switched {} at {} heat (MegaMek BotHeatEquipmentManager).", name, kind, if on { "on" } else { "off" }, heat));
    }
}

/// toggleStealthArmor: the armor's mode is set every turn, from `desiredStealthMode`.
fn toggle_stealth_armor(b: &mut Battle, u: UnitId) {
    if !b.units[u].has_stealth_armor {
        return;
    }
    let on = desired_stealth_mode(b, u);
    set_system(b, u, "stealth_armor", on);
}

/// desiredStealthMode: true = armor on.
fn desired_stealth_mode(b: &mut Battle, u: UnitId) -> bool {
    // every 'Mech tracks heat, so the "heat does not matter" branch (always on) never applies here
    let trigger_heat = 13 + (b.pick_number(7) - 1);
    if b.units[u].current_heat > trigger_heat {
        return false;
    }
    let Some(here) = crate::forces::hex_xy(b, u) else {
        // off-board: stealth up before coming back
        return true;
    };
    if b.units[u].has_tsm {
        // heat-activated TSM keeps the armor's heat while closing, drops it adjacent to an enemy
        let enemies = crate::forces::enemies_of(b, u);
        let adjacent = enemies.iter().any(|e| crate::forces::hex_xy(b, *e).is_some_and(|h| crate::princess_geometry::mm_distance(here, h) <= 1));
        return !adjacent;
    }
    let (mut total_bv, mut known_bv, mut known_range, mut known_count) = (0i64, 0i64, 0i64, 0i64);
    for e in crate::forces::enemies_of(b, u) {
        let bv = crate::battle_value::battle_value(b, e);
        total_bv += bv;
        // every positioned enemy counts as visible: the engine has no line-of-sight hiding for this test
        if let Some(h) = crate::forces::hex_xy(b, e) {
            known_count += 1;
            known_bv += bv;
            known_range += crate::princess_geometry::mm_distance(here, h);
        }
    }
    // few or no enemies seen: they are hiding, so stealth stays on
    if known_count == 0 || known_bv < total_bv / 2 {
        return true;
    }
    // close enemy force: armor off to free heat sinks for weapons (average range, integer division as in Java)
    let limit = 5 + (b.pick_number(5) - 1);
    (known_range / known_count) > limit
}

/// decideHeatLoadAction: Some(true) = switch on, Some(false) = switch off, None = leave alone.
fn decide_heat_load_action(heat: i64, currently_on: bool) -> Option<bool> {
    if heat >= SHED_HEAT_THRESHOLD {
        return if currently_on { Some(false) } else { None };
    }
    if heat <= RESTORE_HEAT_THRESHOLD {
        return if currently_on { None } else { Some(true) };
    }
    None
}

/// toggleConcealmentSystems: Null, Void and Chameleon, each by heat alone.
fn toggle_concealment_systems(b: &mut Battle, u: UnitId) {
    for kind in CONCEALMENT {
        if !equip::system_live(&b.units[u], kind) {
            continue;
        }
        let on_now = !b.units[u].systems_off.iter().any(|k| k == kind);
        if let Some(on) = decide_heat_load_action(b.units[u].current_heat, on_now) {
            set_system(b, u, kind, on);
        }
    }
}

/// manageRadicalHeatSink: on while the unit needs the cooling and the gamble is still better than even.
fn manage_radical_heat_sink(b: &mut Battle, u: UnitId) {
    if !equip::system_live(&b.units[u], "radical") {
        return;
    }
    let needs_cooling = b.units[u].current_heat >= SHED_HEAT_THRESHOLD;
    let next_tn = equip::escalating_avoid_tn(b.units[u].escalating_turns["radical"] + 1);
    let should_be_active = needs_cooling && next_tn <= BEST_ODDS_TARGET_NUMBER;
    if should_be_active == b.units[u].radical_on {
        return;
    }
    b.units[u].radical_on = should_be_active;
    let (name, heat) = (b.units[u].side_name.clone().unwrap_or_default(), b.units[u].current_heat);
    b.log(format!("    {}: radical heat sink {} at {} heat, next failure roll needs {} (MegaMek BotHeatEquipmentManager).", name, if should_be_active { "on" } else { "off" }, heat, next_tn));
}
