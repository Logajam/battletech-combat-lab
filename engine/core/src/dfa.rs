// Translated from INTEGRATION__dfa.py (session 22): Death From Above (Core pp.79-81).
use crate::attack_resolution::target_tmm;
use crate::battle::{Battle, UnitId};
use crate::charge::Triggers;
use crate::combat;
use crate::domino;
use crate::hazards;
use crate::hex_geometry;
use crate::mech_state::*;
use crate::movement_attacks as ma;
use crate::physical_gear as gear;
use crate::piloting_rolls as pr;
use indexmap::IndexMap;

pub const DFA_PSR_MODIFIER: i64 = 2;
pub const JUMP_MODIFIER: i64 = 3;
pub const MISS_FALL_LEVELS: i64 = 2;

fn ceil_div(a: i64, b: i64) -> i64 {
    -((-a).div_euclid(b))
}

/// ceil(tons / 10 x 3); x1.5 with talons on both legs.
pub fn target_damage(a: &Mech) -> i64 {
    let damage = (a.mass.unwrap_or(0) as f64 / 10.0 * 3.0).ceil() as i64;
    if gear::dfa_talons(a) { gear::with_talons(damage) } else { damage }
}

pub fn attacker_damage(a: &Mech) -> i64 {
    ceil_div(a.mass.unwrap_or(0), 5)
}

pub fn miss_fall_damage(a: &Mech) -> i64 {
    ceil_div(a.mass.unwrap_or(0), 10) * (MISS_FALL_LEVELS + 1)
}

pub fn to_hit(b: &Battle, attacker: UnitId, target: UnitId, ttmm: i64) -> i64 {
    let a = &b.units[attacker];
    a.piloting + JUMP_MODIFIER + ttmm + ma::comparative_modifier(a, &b.units[target]) + crate::advanced_weapons::own_attack_modifier(a, true) + torso_cockpit_sensor_penalty(a) + physical_attacker_modifier(a)
}

/// The attacker lands in the target's hex, facing as it was (p.80). Returns True if the attacker fell.
fn land(b: &mut Battle, attacker: UnitId, label: &str, direction: Option<i64>, with_domino: bool) -> bool {
    if b.is_destroyed(attacker) {
        return false;
    }
    if with_domino && domino::advance_into(b, attacker, label, direction.unwrap(), "landing its DFA") {
        return true;
    }
    b.units[attacker].hex = Some(label.to_string());
    hazards::enter_hex(b, attacker, label, true, None, true);
    false
}

#[derive(Clone, Debug, PartialEq)]
pub enum Declared {
    Cancelled,
    Going(i64, bool),
}

/// Physical phase: (TN, hit) for a DFA that goes ahead, None if cancelled.
pub fn declare(b: &mut Battle, attacker: UnitId, target: UnitId) -> Declared {
    let a_name = b.units[attacker].side_name.clone().unwrap_or_default();
    let t_name = b.units[target].side_name.clone().unwrap_or_default();
    if b.is_destroyed(attacker) {
        b.units[attacker].dfa = None;
        return Declared::Cancelled;
    }
    if b.is_destroyed(target) {
        let th = b.units[target].hex.clone().unwrap();
        b.log(format!("  [Physical] {}'s DFA is cancelled: {} is destroyed - it lands in {} (p.80).", a_name, t_name, th));
        land(b, attacker, &th, None, false);
        b.units[attacker].dfa = None;
        return Declared::Cancelled;
    }
    let ttmm = target_tmm(&b.units[target]);
    let tn = to_hit(b, attacker, target, ttmm);
    if b.units[attacker].prone || all_crew_unconscious(&b.units[attacker]) {
        b.log(format!("  [Physical] {}'s DFA misses: it is {} (p.79).", a_name, if b.units[attacker].prone { "down" } else { "unconscious" }));
        return Declared::Going(tn, false);
    }
    let roll = b.roll_2d6();
    let hit = tn <= 12 && roll >= tn;
    let line = format!(
        "  [Physical] {} -> {}: DEATH FROM ABOVE needs {} (piloting {} + jump {} + TMM {} + comparative {:+}), rolled {} -> {}",
        a_name,
        t_name,
        tn,
        b.units[attacker].piloting,
        JUMP_MODIFIER,
        ttmm,
        ma::comparative_modifier(&b.units[attacker], &b.units[target]),
        roll,
        if hit { "HIT" } else { "miss" }
    );
    b.log(line);
    Declared::Going(tn, hit)
}

/// Displacement candidates nearest `direction` first (p.80).
fn open_hexes(b: &Battle, target: UnitId, direction: i64) -> Vec<(i64, &'static str, Option<String>, i64)> {
    let order = [direction, (direction - 1).rem_euclid(6), (direction + 1).rem_euclid(6), (direction - 2).rem_euclid(6), (direction + 2).rem_euclid(6), (direction + 3).rem_euclid(6)];
    let here = b.units[target].hex.clone().unwrap();
    let mut out = Vec::new();
    for d in order {
        let (kind, label, drop) = ma::displacement(b, &here, d);
        if kind != "blocked" {
            out.push((d, kind, label, drop));
        }
    }
    out
}

/// Move the target; returns True if it fell automatically.
fn displace(b: &mut Battle, target: UnitId, kind: &str, label: Option<String>, drop: i64, cause: &str) -> bool {
    let t_name = b.units[target].side_name.clone().unwrap_or_default();
    if kind == "off" {
        b.units[target].destroyed = true;
        b.units[target].cause_of_death = Some("Displaced off the battlefield".into());
        b.log(format!("    {} is pushed off the battlefield - destroyed (p.113).", t_name));
        return true;
    }
    let mut label = label.unwrap();
    let old = b.units[target].hex.clone().unwrap();
    let mut fell_here = false;
    if domino::occupant(b, &label, &[target]).is_some() {
        let dir = domino::combat_dir(&old, &label);
        fell_here = domino::displace_into_occupied(b, target, &label, dir, drop, cause);
        label = b.units[target].hex.clone().unwrap();
    } else {
        b.units[target].hex = Some(label.clone());
    }
    b.log(format!("    {} is displaced {} -> {}.", t_name, old, label));
    if fell_here {
        return true;
    }
    hazards::enter_hex(b, target, &label, false, Some(&format!("displaced into {}", label)), true);
    if drop >= 2 {
        b.log(format!("    {} is displaced {} levels down - automatic fall (p.114).", t_name, drop));
        pr::resolve_fall(b, target, cause, drop, None);
        return true;
    }
    false
}

/// Damage, landing and displacement (p.80). Returns PSR triggers.
pub fn resolve(b: &mut Battle, attacker: UnitId, target: UnitId, hit: bool) -> Triggers {
    let a_name = b.units[attacker].side_name.clone().unwrap_or_default();
    let t_name = b.units[target].side_name.clone().unwrap_or_default();
    let mut triggers: Triggers = IndexMap::new();
    triggers.insert(a_name.clone(), vec![]);
    triggers.insert(t_name.clone(), vec![]);
    let a_xy = hex_geometry::parse_hex_label(b.units[attacker].hex.as_deref().unwrap()).unwrap();
    let t_xy = hex_geometry::parse_hex_label(b.units[target].hex.as_deref().unwrap()).unwrap();
    let direction = combat::direction_facing(a_xy, t_xy).unwrap();
    let target_hex = b.units[target].hex.clone().unwrap();
    if hit {
        let tf = hex_geometry::compass_to_facing(&b.units[target].facing).unwrap();
        let side = crate::attack_resolution::attack_side(b, a_xy, t_xy, tf, crate::attack_resolution::standing(), crate::attack_resolution::standing());
        let (table, t_side) = if b.units[target].prone { ("standard", "rear") } else { ("punch", side) };
        let td = target_damage(&b.units[attacker]);
        let ad = attacker_damage(&b.units[attacker]);
        b.log(format!("    DFA: {} takes {} ({} table, {}), {} takes {} (kick table).", t_name, td, table, t_side, a_name, ad));
        let talons = gear::dfa_talons(&b.units[attacker]);
        let hits = ma::apply_groups(b, target, td, table, t_side, &format!("DFA{}", if talons { " (talons x1.5, p.196)" } else { "" }), false, None);
        if hits.iter().any(|(_, s)| *s) {
            let m = &b.units[attacker];
            let legs: Vec<String> = m.leg_locations.iter().filter(|l| !m.locations[l.as_str()].destroyed).take(2).cloned().collect();
            let l: Vec<&str> = legs.iter().map(|s| s.as_str()).collect();
            gear::spike_retaliation(b, attacker, &l);
        }
        ma::apply_groups(b, attacker, ad, "kick", "front", "DFA (attacker)", false, None);
        let mut fell = false;
        if !b.is_destroyed(target) {
            let options = open_hexes(b, target, direction);
            if options.is_empty() {
                b.units[target].destroyed = true;
                b.units[target].cause_of_death = Some("Nowhere to be displaced (DFA)".into());
                b.log(format!("    {} can't be displaced anywhere - destroyed (p.81).", t_name));
            } else {
                let (_, kind, label, drop) = options[0].clone();
                fell = displace(b, target, kind, label, drop, "displaced by a DFA");
            }
        }
        let attacker_fell = land(b, attacker, &target_hex, Some(direction), true);
        if !fell {
            for (m, why) in [(target, "hit by a DFA"), (attacker, "DFA (attacker)")] {
                if !b.is_destroyed(m) && !(m == attacker && attacker_fell) {
                    let n = b.units[m].side_name.clone().unwrap_or_default();
                    triggers.get_mut(&n).unwrap().push((why.into(), DFA_PSR_MODIFIER));
                }
            }
        }
        return triggers;
    }
    // Miss: the target steps aside (its choice - the safest open hex), the attacker falls 2 levels.
    let options: Vec<(i64, &'static str, Option<String>, i64)> = open_hexes(b, target, direction).into_iter().filter(|o| o.1 == "moved").collect();
    if options.is_empty() {
        b.units[attacker].destroyed = true;
        b.units[attacker].cause_of_death = Some("Failed DFA with nowhere to land".into());
        b.log(format!("    {} has nowhere to step aside - {} is destroyed (p.81).", t_name, a_name));
        return triggers;
    }
    let mut best: Option<((bool, i64, bool), usize)> = None;
    for (i, o) in options.iter().enumerate() {
        let occ = domino::occupant(b, o.2.as_deref().unwrap(), &[target, attacker]).is_some();
        let key = (occ, 0.max(o.3), o.0 != direction);
        if best.as_ref().map_or(true, |(k, _)| key < *k) {
            best = Some((key, i));
        }
    }
    let (_, _, label, drop) = options[best.unwrap().1].clone();
    displace(b, target, "moved", label, drop, "stepping aside from a DFA");
    land(b, attacker, &target_hex, Some(direction), true);
    if !b.units[attacker].prone && !b.is_destroyed(attacker) {
        b.log(format!("    {} misses and falls {} levels in {} (rear, p.80).", a_name, MISS_FALL_LEVELS, target_hex));
        pr::resolve_fall(b, attacker, "failed DFA", MISS_FALL_LEVELS, Some("rear"));
    }
    triggers
}
