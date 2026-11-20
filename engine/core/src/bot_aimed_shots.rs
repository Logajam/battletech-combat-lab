//! T16 step 3: Princess's and CASPAR's aimed-shot choice, a port of MegaMek `Princess.calculateAimedShotLocation` and
//! `setAttackAsAimedOrCalled` (enhanced targeting is ON by default: `Princess.resetEnhancedTargeting(true)`).
//!
//! What the engine allows is narrower than MegaMek: aimed shots only at an IMMOBILE target (shut down, crew out, legs gone;
//! p.70) - the engine has no targeting-computer aim at a mobile target, and no called shots (listed for Daniel in the T16
//! audit table). Against an immobile 'Mech the choice does not depend on the firing plan, only on the target:
//!   * the head only for an infantry shooter (never here: every shooter is a 'Mech);
//!   * candidates in order: an arm that carries a "big gun" (a non-missile weapon doing 10+ damage at range 5, standing in
//!     for `WeaponType.getDamage(5) >= 10`), right arm first; the right torso (else the left); the left torso; the center
//!     torso; the right leg (else the left); the left leg;
//!   * the winner is the candidate with the least armor (the rear armor against a rear shot), a later one replacing an
//!     earlier one only if it has strictly less armor, or its armor plus internal structure is below the current one's;
//!     a torso with no armor ends the search;
//!   * the "will the weapons be effective" test applies to mobile targets and the head only, so it does not run here.
//! A target with partial cover gets no aimed shot (`allowCoverEnhancedTargeting` is false by default).
//! Then each weapon is aimed only if its to-hit number is 12 or less (SHUTDOWN_MAX_TARGET_NUMBER), 13 if its damage could
//! destroy the location (`gate`); otherwise it fires unaimed.
use crate::battle::{Battle, UnitId};
use crate::equipment::ItemId;

/// MegaMek Princess.BIG_GUN_MIN_DAMAGE
const BIG_GUN_MIN_DAMAGE: i64 = 10;
/// MegaMek Princess.SHUTDOWN_MAX_TARGET_NUMBER
const SHUTDOWN_MAX_TARGET_NUMBER: i64 = 12;

/// `isBigGun`: damage at the typical range (5) of 10 or more. A missile weapon's damage is by cluster table in MegaMek, so
/// it never counts.
fn is_big_gun(b: &Battle, target: UnitId, w: ItemId) -> bool {
    let it = &b.units[target].items[w];
    it.damage_type.as_deref() != Some("Missile") && it.damage_per_shot.unwrap_or(0) >= BIG_GUN_MIN_DAMAGE
}

fn internal(b: &Battle, target: UnitId, loc: &str) -> i64 {
    b.units[target].locations.get(loc).map_or(0, |l| if l.destroyed { 0 } else { l.structure.as_int_or_trunc() })
}

fn armor(b: &Battle, target: UnitId, loc: &str, rear: bool) -> i64 {
    let l = &b.units[target].locations[loc];
    let a = match (rear, l.rear_armor) {
        (true, Some(r)) => r.as_int_or_trunc(),
        _ => l.armor.as_int_or_trunc(),
    };
    a.max(0)
}

/// Where a Princess-family shooter aims at an immobile 'Mech, with the location's destruction threshold (armor + internal
/// structure; `locationDestruction`), or None. `rear_shot` is a shot into the rear arc, `partial_cover` the target's cover.
pub fn aimed_location(b: &mut Battle, target: UnitId, rear_shot: bool, partial_cover: bool) -> Option<(String, i64)> {
    if partial_cover || !crate::mech_state::is_immobile(&b.units[target]) {
        return None;
    }
    let locs = crate::attack_resolution::weapon_locations(&b.units[target]);
    let mut ranked: Vec<&str> = Vec::new();
    for w in crate::damage_resolution::get_weapons(&b.units[target]) {
        if !is_big_gun(b, target, w) {
            continue;
        }
        let at = locs.get(&w).cloned().unwrap_or_default();
        for arm in ["Right Arm", "Left Arm"] {
            if at.first().map(|s| s.as_str()) == Some(arm) && !ranked.contains(&arm) && internal(b, target, arm) > 0 {
                ranked.push(arm);
            }
        }
    }
    // "Prefers right to left": a stable order whatever order the weapons are listed in
    ranked.sort_by_key(|l| if *l == "Right Arm" { 0 } else { 1 });
    if internal(b, target, "Right Torso") > 0 {
        ranked.push("Right Torso");
    } else if internal(b, target, "Left Torso") > 0 {
        ranked.push("Left Torso");
    }
    if !ranked.contains(&"Left Torso") && internal(b, target, "Left Torso") > 0 {
        ranked.push("Left Torso");
    }
    ranked.push("Center Torso");
    if internal(b, target, "Right Leg") > 0 {
        ranked.push("Right Leg");
    } else if internal(b, target, "Left Leg") > 0 {
        ranked.push("Left Leg");
    }
    if !ranked.contains(&"Left Leg") && internal(b, target, "Left Leg") > 0 {
        ranked.push("Left Leg");
    }
    let (mut aim, mut lowest, mut destruction): (Option<&str>, i64, i64) = (None, i64::MAX, 0);
    for loc in ranked {
        if !b.units[target].locations.contains_key(loc) {
            continue;
        }
        let a = armor(b, target, loc, rear_shot && b.units[target].locations[loc].rear_armor.is_some());
        let int = internal(b, target, loc);
        if int > 0 && (lowest > a || destruction > a + int) {
            aim = Some(loc);
            lowest = a;
            destruction = lowest + int;
        }
        if lowest == 0 && matches!(aim, Some("Right Torso" | "Left Torso" | "Center Torso")) {
            break;
        }
    }
    aim.map(|l| (l.to_string(), destruction))
}

/// `setAttackAsAimedOrCalled` for an immobile target: is this weapon's shot aimed? `tn` is its to-hit number, `max_damage`
/// its damage; the number may be one higher if the shot could destroy the location outright.
pub fn gate(tn: i64, max_damage: i64, destruction: i64) -> bool {
    tn <= SHUTDOWN_MAX_TARGET_NUMBER + if max_damage >= destruction { 1 } else { 0 }
}
