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
        // each unit with its team's settings (team_settings.rs)
        crate::team_settings::with_unit(b, u, |b| {
            toggle_stealth_armor(b, u);
            toggle_concealment_systems(b, u);
            manage_radical_heat_sink(b, u);
            set_ams_modes(b, u);
        });
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

// ---------------------------------------------------------------------------------------------------- AMS on / off
// Backlog N3 (Daniel, 2026-11-20: "Need AMS on/off and ammo conservation for princess"). MegaMek `Princess.setAMSModes`
// (MegaMek main 3f9f2fd), run in `endOfTurnProcessing` as this manager is. The Core Rulebook lets the defender choose to
// engage each attack (p.206); MegaMek, and this, settle it as an on / off state per AMS for the next turn. An AMS that is
// off is listed in `systems_off` as "ams:<item>" and `ams::systems` leaves it out. What MegaMek does, in its order (one
// mode carried from AMS to AMS, as MegaMek's loop does):
//   * a laser AMS is switched off while the 'Mech is at MAX_OVERHEAT_AMS (14) heat or more, else on;
//   * an AMS with ammunition, when its loaded bin is down to the self-preservation share of the AMS's "original shots"
//     (MegaMek reads them from the weapon, where they are 0: in effect, when it has no ammunition left), may go off: TN = 12 - bravery index, -4 undamaged / -2 light / +1 moderate / +4 +8 heavy
//     (MegaMek's switch falls through) / +8 crippled; when the TN is under 10, 2d6 >= TN switches it off (the battle's
//     dice, as T16's other MegaMek draws). NOT PORTED: the +4 against a missile-boat last target (the engine has no unit
//     roles) and manual AMS against infantry (no infantry).

/// MegaMek Princess.MAX_OVERHEAT_AMS
pub const MAX_OVERHEAT_AMS: i64 = 14;

/// MegaMek Entity.getDamageLevel for a 'Mech (Mek.isDmgHeavy / isDmgModerate / isDmgLight): 0 none, 1 light,
/// 2 moderate, 3 heavy, 4 crippled.
pub fn damage_level(m: &crate::mech_state::Mech) -> i64 {
    if crate::mech_state::is_crippled(m) {
        return 4;
    }
    let armor_of = |l: &str| m.locations.get(l).map_or(0, |v| v.armor.as_int().max(0));
    let head_ratio = {
        let o = *m.max_armor.get("Head").unwrap_or(&0);
        if o > 0 { armor_of("Head") as f64 / o as f64 } else { 1.0 }
    };
    let total: i64 = m.locations.values().map(|v| v.armor.as_int().max(0) + v.rear_armor.map_or(0, |r| r.as_int().max(0))).sum();
    let o_total: i64 = m.max_armor.values().sum::<i64>() + m.max_rear_armor.values().sum::<i64>();
    let armor_pct = if o_total > 0 { total as f64 / o_total as f64 } else { 1.0 };
    let structure_hit = |l: &str| m.locations.get(l).is_some_and(|v| v.structure.as_int() < *m.max_structure.get(l).unwrap_or(&0));
    let limbs = ["Right Leg", "Left Leg", "Left Arm", "Right Arm"].iter().filter(|l| structure_hit(l)).count();
    let torsos = ["Center Torso", "Left Torso", "Right Torso"].iter().filter(|l| structure_hit(l) && armor_of(l) < 1).count();
    let total_weapons = m.items.iter().filter(|e| e.category.as_deref() == Some("weapon")).count();
    let live = crate::damage_resolution::get_weapons(m);
    let jammed = live.iter().filter(|w| m.items[**w].jammed.unwrap_or(false)).count();
    let inoperable = total_weapons.saturating_sub(live.len()) + jammed;
    let share = if total_weapons > 0 { inoperable as f64 / total_weapons as f64 } else { 0.0 };
    if head_ratio <= 0.33 || armor_pct <= 0.25 || limbs == 2 || torsos == 1 || m.engine_hits == 1 || m.gyro_hits == 1 || m.pilot_hits == 3 || share >= 0.75 {
        return 3;
    }
    if head_ratio <= 0.67 || armor_pct <= 0.5 || limbs == 1 || m.pilot_hits == 2 || share >= 0.5 {
        return 2;
    }
    if head_ratio < 1.0 || armor_pct <= 0.75 || m.pilot_hits == 1 || share >= 0.5 {
        return 1;
    }
    0
}

/// The key of an AMS in `systems_off`.
pub fn ams_key(w: crate::equipment::ItemId) -> String {
    format!("ams:{}", w)
}

/// Is this AMS switched off (by a MegaMek bot's End Phase choice)?
pub fn ams_off(m: &crate::mech_state::Mech, w: crate::equipment::ItemId) -> bool {
    m.heat_managed && m.systems_off.iter().any(|k| *k == ams_key(w))
}

fn set_ams_modes(b: &mut Battle, u: UnitId) {
    if b.units[u].hex.is_none() {
        return;
    }
    let all: Vec<crate::equipment::ItemId> = crate::damage_resolution::get_weapons(&b.units[u]).into_iter().filter(|w| crate::weapon_rules::is_ams(b, u, *w)).collect();
    if all.is_empty() {
        return;
    }
    let overheating = b.units[u].current_heat >= MAX_OVERHEAT_AMS;
    let self_preservation = crate::princess_fire::setting(b, "self_preservation");
    let bravery = b.cfg.get("PRINCESS_BEHAVIOR")["bravery"].as_i64().unwrap_or(5).clamp(0, 10);
    let mut on = true; // MegaMek: one mode, set to "on" before the loop and carried through it
    for w in all {
        let laser = !b.units[u].items[w].needs_ammo.unwrap_or(false);
        if laser {
            if overheating {
                on = false;
            }
        } else {
            // MegaMek: linked ammo's usable shots <= floor(curAMS.getOriginalShots() x self preservation / 100). The
            // ORIGINAL SHOTS ARE READ FROM THE AMS WEAPON, and MegaMek sets them only on ammunition, so they are 0 and
            // the test is "the loaded bin is empty" (ported as MegaMek plays it; with no usable bin left it is true)
            let left = crate::ammo::bins_for(&b.units[u], w).first().map_or(0, |i| b.units[u].items[*i].shots_left.unwrap_or(0));
            let weapon_original_shots = 0;
            let conserve = left <= (weapon_original_shots as f64 * self_preservation / 100.0).floor() as i64;
            if conserve {
                let mut tn = 12 - bravery;
                tn += match damage_level(&b.units[u]) {
                    0 => -4,
                    1 => -2,
                    2 => 1,
                    3 => 4 + 8,
                    _ => 8,
                };
                if tn < 10 {
                    let roll = b.roll_2d6();
                    if roll >= tn {
                        on = false;
                    }
                    let name = b.units[u].side_name.clone().unwrap_or_default();
                    b.log(format!("    {}: {} down to {} shot(s) - conserve ammo? needs {}, rolled {} (MegaMek Princess.setAMSModes).", name, b.units[u].items[w].name, left, tn, roll));
                }
            }
        }
        let was_on = !b.units[u].systems_off.iter().any(|k| *k == ams_key(w));
        if on != was_on {
            let key = ams_key(w);
            if on {
                b.units[u].systems_off.retain(|k| *k != key);
            } else {
                b.units[u].systems_off.push(key);
            }
            let (name, wname, heat) = (b.units[u].side_name.clone().unwrap_or_default(), b.units[u].items[w].name.clone(), b.units[u].current_heat);
            b.log(format!("    {}: {} switched {} at {} heat (MegaMek Princess.setAMSModes).", name, wname, if on { "on" } else { "off" }, heat));
        }
    }
}
