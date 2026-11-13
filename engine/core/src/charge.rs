// Translated from INTEGRATION__charge.py (session 22): charges (Core p.78), resolved in the Physical phase.
use crate::fasthash::IndexMap;

use crate::attack_resolution::target_tmm;
use crate::battle::{Battle, UnitId};
use crate::combat;
use crate::domino;
use crate::hazards;
use crate::hex_geometry;
use crate::mech_state::*;
use crate::movement_attacks as ma;
use crate::physical_gear as gear;
use crate::piloting_rolls as pr;

pub const CHARGE_PSR_MODIFIER: i64 = 2;

/// Triggers by unit side name: [(reason, modifier)].
pub type Triggers = IndexMap<String, Vec<(String, i64)>>;

fn ceil_div(a: i64, b: i64) -> i64 {
    -((-a).div_euclid(b))
}

pub fn target_damage(attacker: &Mech, attacker_tmm: i64) -> i64 {
    // math.ceil(mass / 5 * (tmm + 1)): float product, then ceil
    ((attacker.mass.unwrap_or(0) as f64 / 5.0) * (attacker_tmm + 1) as f64).ceil() as i64
}

pub fn attacker_damage(target: &Mech) -> i64 {
    ceil_div(target.mass.unwrap_or(0), 10)
}

/// -1 with AES in all legs (Core p.206).
pub fn aes_modifier(attacker: &Mech) -> i64 {
    if leg_aes_working(attacker) { -1 } else { 0 }
}

#[allow(clippy::too_many_arguments)]
pub fn to_hit(b: &Battle, attacker: UnitId, mode: &str, target: UnitId, a_xy: (i64, i64), t_xy: (i64, i64), target_tmm: i64) -> i64 {
    let a = &b.units[attacker];
    a.piloting
        + combat::mode_to_amm(mode)
        + target_tmm
        + ma::terrain_modifier(b, a_xy, t_xy)
        + ma::comparative_modifier(a, &b.units[target])
        + aes_modifier(a)
        + torso_cockpit_sensor_penalty(a)
        + physical_attacker_modifier(a)
        + crate::advanced_weapons::own_attack_modifier(a, true)
}

pub fn can_charge(b: &mut Battle, mover: UnitId, target: UnitId, target_has_moved: bool) -> bool {
    ma::can_be_attacked(b, target, target_has_moved) && !b.units[target].prone && b.units[mover].hex.is_some()
}

/// The result of `declare`: Some(None) = cancelled (returns None in Python), "miss", or (tn, hit).
#[derive(Clone, Debug, PartialEq)]
pub enum Declared {
    Cancelled,
    Miss,
    Going(i64, bool),
}

/// Physical phase: the charge's (TN, hit) if it goes ahead, cancelled (attacker.charging cleared), or a miss outright.
pub fn declare(b: &mut Battle, attacker: UnitId, target: UnitId) -> Declared {
    let a_name = b.units[attacker].side_name.clone().unwrap_or_default();
    let t_name = b.units[target].side_name.clone().unwrap_or_default();
    if b.is_destroyed(target) || b.units[target].prone {
        let why = if b.is_destroyed(target) { "is destroyed" } else { "fell" };
        b.log(format!("  [Physical] {}'s charge is cancelled: {} {} (p.78).", a_name, t_name, why));
        b.units[attacker].charging = None;
        return Declared::Cancelled;
    }
    if b.units[attacker].prone || b.is_destroyed(attacker) || all_crew_unconscious(&b.units[attacker]) {
        let why = if b.units[attacker].prone { "down" } else if !b.is_destroyed(attacker) { "unconscious" } else { "destroyed" };
        b.log(format!("  [Physical] {}'s charge misses: it is {} (p.78).", a_name, why));
        return Declared::Miss;
    }
    let a_hex = hex_geometry::parse_hex_label(b.units[attacker].hex.as_deref().unwrap()).unwrap();
    let t_hex = hex_geometry::parse_hex_label(b.units[target].hex.as_deref().unwrap()).unwrap();
    let ttmm = target_tmm(&b.units[target]);
    let mode = b.units[attacker].move_mode.clone();
    let tn = to_hit(b, attacker, &mode, target, a_hex, t_hex, ttmm);
    if tn > 12 {
        b.log(format!("  [Physical] {} aborts its charge (needs {}) (p.78).", a_name, tn));
        b.units[attacker].charging = None;
        return Declared::Cancelled;
    }
    let roll = b.roll_2d6();
    let hit = roll >= tn;
    let aes = aes_modifier(&b.units[attacker]);
    let line = format!(
        "  [Physical] {} -> {}: CHARGE needs {} (piloting {} + AMM {} + TMM {} + terrain {} + comparative {:+}{}), rolled {} -> {}",
        a_name,
        t_name,
        tn,
        b.units[attacker].piloting,
        combat::mode_to_amm(&mode),
        ttmm,
        ma::terrain_modifier(b, a_hex, t_hex),
        ma::comparative_modifier(&b.units[attacker], &b.units[target]),
        if aes != 0 { format!(" + AES {}", aes) } else { String::new() },
        roll,
        if hit { "HIT" } else { "miss" }
    );
    b.log(line);
    Declared::Going(tn, hit)
}

/// A charge that hit, between its damage and its displacement: who, and where both stood when it was made.
pub struct ChargeHit {
    pub attacker: UnitId,
    pub target: UnitId,
    pub a_label: String,
    pub t_label: String,
    /// the direction of the charge (attacker's hex -> target's hex)
    pub dir: i64,
}

/// A charge's damage, both ways (p.78). Displacement waits until every physical attack of the phase has been made (Core
/// p.76): `resolve_displacement` does it, from the ChargeHit returned here.
pub fn resolve_damage(b: &mut Battle, attacker: UnitId, target: UnitId) -> ChargeHit {
    let a_label = b.units[attacker].hex.clone().unwrap();
    let t_label = b.units[target].hex.clone().unwrap();
    let a_hex = hex_geometry::parse_hex_label(&a_label).unwrap();
    let t_hex = hex_geometry::parse_hex_label(&t_label).unwrap();
    let tf = hex_geometry::compass_to_facing(&b.units[target].facing).unwrap();
    let side = crate::attack_resolution::attack_side(b, a_hex, t_hex, tf, crate::attack_resolution::standing(), crate::attack_resolution::standing()).to_string();
    let dealt = target_damage(&b.units[attacker], combat::fc_to_tmm(b.units[attacker].move_fc, false).unwrap());
    let taken = attacker_damage(&b.units[target]);
    let spikes = gear::use_spikes_in_charge(b, attacker);
    let bonus = gear::charge_spike_bonus(&b.units[attacker], spikes);
    let (a_name, t_name) = (b.units[attacker].side_name.clone().unwrap_or_default(), b.units[target].side_name.clone().unwrap_or_default());
    b.log(format!("    Charge: {} takes {}{} ({}), {} takes {}.", t_name, dealt, if bonus != 0 { format!(" + {} (spikes, p.196)", bonus) } else { String::new() }, side, a_name, taken));
    let first = ma::apply_groups(b, target, dealt + bonus, "standard", &side, "Charge", false, None);
    if !first.is_empty() && first.iter().any(|(_, s)| *s) {
        gear::spike_retaliation(b, attacker, &["Center Torso"]);
    }
    if !first.is_empty() && !b.is_destroyed(target) {
        let loc = first[0].0.clone();
        let v = &b.units[target].locations[&loc];
        let armor_sum = v.armor + v.rear_armor.unwrap_or(crate::pyfmt::Num::I(0));
        if !v.destroyed && armor_sum > crate::pyfmt::Num::I(0) {
            for _ in gear::lances(&b.units[attacker]) {
                gear::lance_ap_check(b, target, &loc, gear::LANCE_CHARGE_AP_TN, "lance in a charge");
            }
        }
    }
    let onto = gear::raised_arm(&b.units[attacker]);
    ma::apply_groups(b, attacker, taken, "standard", "front", "Charge (attacker)", spikes, onto.as_deref());
    ChargeHit { attacker, target, a_label, t_label, dir: combat::direction_facing(a_hex, t_hex).unwrap() }
}

/// A charge's displacement (pp.78, 113-115), once every physical attack of the phase has been made (p.76). Returns the
/// PSR triggers. If an earlier displacement this phase already moved the attacker or the target out of the hex it
/// stood in for the charge, this one moves nobody else: the target is not displaced again, and the attacker (if it was
/// not moved itself) advances into the hex it charged, as MegaMek does for a target that is no longer there (the
/// rulebook does not say; TWGameManager.resolveChargeAttack).
pub fn resolve_displacement(b: &mut Battle, h: &ChargeHit) -> Triggers {
    let (attacker, target) = (h.attacker, h.target);
    let (a_name, t_name) = (b.units[attacker].side_name.clone().unwrap_or_default(), b.units[target].side_name.clone().unwrap_or_default());
    let mut triggers: Triggers = IndexMap::default();
    triggers.insert(a_name.clone(), vec![]);
    triggers.insert(t_name.clone(), vec![]);
    if !b.is_destroyed(attacker) {
        triggers.get_mut(&a_name).unwrap().push(("charged (attacker)".into(), CHARGE_PSR_MODIFIER));
    }
    let attacker_moved = b.units[attacker].hex.as_deref() != Some(h.a_label.as_str());
    let target_moved = b.units[target].hex.as_deref() != Some(h.t_label.as_str());
    if attacker_moved || target_moved {
        let who = if attacker_moved { &a_name } else { &t_name };
        b.log(format!("    {}'s charge on {}: {} was already displaced this phase - no displacement from this charge (p.76).", a_name, t_name, who));
        if !b.is_destroyed(target) {
            triggers.get_mut(&t_name).unwrap().push(("charged".into(), CHARGE_PSR_MODIFIER));
        }
        if !attacker_moved && !b.is_destroyed(attacker) {
            if domino::advance_into(b, attacker, &h.t_label, h.dir, "advancing after its charge") {
                triggers.insert(a_name.clone(), vec![]);
            } else {
                let ah = b.units[attacker].hex.clone().unwrap();
                hazards::enter_hex(b, attacker, &ah, false, Some(&format!("advanced into {}", ah)), true);
            }
        }
        return triggers;
    }
    if b.is_destroyed(target) {
        if !b.is_destroyed(attacker) {
            b.units[attacker].hex = b.units[target].hex.clone();
        }
        return triggers;
    }
    let dir = h.dir;
    let here = b.units[target].hex.clone().unwrap();
    let (kind, new_label, drop) = ma::displacement(b, &here, dir);
    if kind == "off" {
        b.units[target].destroyed = true;
        b.units[target].cause_of_death = Some("Displaced off the battlefield".into());
        b.log(format!("    {} is pushed off the battlefield - destroyed (p.113).", t_name));
        if !b.is_destroyed(attacker) {
            b.units[attacker].hex = b.units[target].hex.clone();
        }
        return triggers;
    }
    if kind == "blocked" {
        b.log("    Displacement is prohibited (3+ levels up) - neither mech moves (p.113).");
        triggers.get_mut(&t_name).unwrap().push(("charged".into(), CHARGE_PSR_MODIFIER));
        return triggers;
    }
    let mut new_label = new_label.unwrap();
    let old = here;
    let mut fell_here = false;
    if domino::occupant(b, &new_label, &[attacker, target]).is_some() {
        fell_here = domino::displace_into_occupied(b, target, &new_label, dir, drop, "displaced by a charge");
        new_label = b.units[target].hex.clone().unwrap();
    } else {
        b.units[target].hex = Some(new_label.clone());
    }
    b.log(format!("    {} is displaced {} -> {}; {} advances into {}.", t_name, old, new_label, a_name, old));
    let mut attacker_fell = false;
    if !b.is_destroyed(attacker) {
        attacker_fell = domino::advance_into(b, attacker, &old, dir, "advancing after its charge");
        if attacker_fell {
            triggers.insert(a_name.clone(), vec![]);
        }
    }
    if !fell_here {
        hazards::enter_hex(b, target, &new_label, false, Some(&format!("displaced into {}", new_label)), true);
    }
    if !b.is_destroyed(attacker) && !attacker_fell {
        let ah = b.units[attacker].hex.clone().unwrap();
        hazards::enter_hex(b, attacker, &ah, false, Some(&format!("advanced into {}", ah)), true);
    }
    if fell_here {
    } else if drop >= 2 {
        b.log(format!("    {} is displaced {} levels down - automatic fall (p.114).", t_name, drop));
        pr::resolve_fall(b, target, "displaced down", drop, None);
    } else {
        triggers.get_mut(&t_name).unwrap().push(("charged".into(), CHARGE_PSR_MODIFIER));
    }
    triggers
}
