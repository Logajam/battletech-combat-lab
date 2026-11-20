// Translated from INTEGRATION__attack_resolution.py (session 22): the Ranged Attack Phase. The weapon choice itself is
// the bot's (a `DeclChoice` handed in; Stage 7-8 computes it, Stage 6 reads it from decisions.json); everything else is
// here: the to-hit numbers, the rolls, the hits and damage, AMS, ammo, heat. (`stats.*` and `timing.*` only log: skipped.)
use crate::fasthash::{HashMap, HashSet};

use crate::advanced_weapons as adv;
use crate::ammo;
use crate::arcs::{self, ArcKey};
use crate::battle::{Battle, UnitId};
use crate::combat;
use crate::damage_resolution::{apply_damage, check_critical, cluster_hits_count, get_weapons, transfer_map};
use crate::electronics;
use crate::equipment::{ItemId, Slot};
use crate::equipment_systems as equip;
use crate::fire_modes::{self, Planner, ShotPlan, TnAdjust};
use crate::hazards;
use crate::hex_geometry;
use crate::hit_location::resolve_hit_location;
use crate::los::{hex_distance, mech_height, trace_los_path, Height, LOSResult, LOSTrace};
use crate::mech_state::*;
use crate::physical_gear as gear;
use crate::pyfmt::Num;
use crate::smoke;
use crate::water::{self, WeaponLocs};
use crate::weapon_profiles as wp;
use crate::weapon_rules;
use crate::weapon_selection;

pub const IMMOBILE_TMM: i64 = -4;
pub const AIMED_HEAD_ADJUST: i64 = -IMMOBILE_TMM + 3;
pub const AIMED_SHOT_SUCCESS: i64 = 4;
pub const ARM_LOCATIONS: [&str; 2] = ["Left Arm", "Right Arm"];
pub const PRONE_FIRE_MODIFIER: i64 = 2;
pub const TRIPOD_PRONE_FIRE_MODIFIER: i64 = 1;
pub const PRONE_TARGET_ADJACENT: i64 = -2;
pub const PRONE_TARGET_FAR: i64 = 1;

/// DeclaredAttack.cover: False / True (partial cover) / KICK (Kick Location Table, legs only).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Cover {
    No,
    Partial,
    Kick,
}

impl Cover {
    pub fn truthy(&self) -> bool {
        *self != Cover::No
    }
}

#[derive(Clone, Debug)]
pub struct DeclaredAttack {
    pub weapon: ItemId,
    pub tn: i64,
    pub roll: i64,
    pub hit: bool,
    pub side: String,
    pub aimed_at: Option<String>,
    pub cover: Cover,
    /// the target's AMS / APDS engaging this hit: items of the TARGET's arena
    pub ams: Option<ItemId>,
    pub apds: Option<ItemId>,
    pub fire: Option<ShotPlan>,
    pub pod_value: f64,
}

#[derive(Clone, Debug, Default)]
pub struct SideReport {
    pub attacks: i64,
    pub hits: i64,
    pub damage_dealt: f64,
    pub weapon_heat: i64,
    pub attacks_list: Vec<DeclaredAttack>,
}

/// Daniel's HP scalar: armor + rear armor + structure.
pub fn total_hp(mech: &Mech) -> Num {
    let mut sum = Num::I(0);
    for v in mech.locations.values() {
        sum = sum + (v.armor + v.rear_armor.unwrap_or(Num::I(0)) + v.structure);
    }
    sum
}

/// The target's movement modifier - immobile -4, else its TMM; stuck / size modifiers.
pub fn target_tmm(m: &Mech) -> i64 {
    let stuck = (if hazards::is_stuck(m) { hazards::STUCK_TO_HIT } else { 0 }) + target_size_modifier(m);
    if is_immobile(m) {
        return IMMOBILE_TMM + stuck;
    }
    combat::fc_to_tmm(m.move_fc, m.move_mode == "Jump").unwrap() + stuck
}

pub fn side_by_relative_hexside(r: i64) -> &'static str {
    match r {
        0 => "front",
        1 | 2 => "right",
        3 => "rear",
        _ => "left",
    }
}

/// A 'Mech's height for line of sight (p.57).
pub fn los_height(m: &Mech) -> Height {
    mech_height(m.prone, is_superheavy(m))
}

/// Attack direction (Core p.73): the hexside of the target's hex that the line of sight crosses, read against the
/// target's facing.
pub fn attack_side(b: &Battle, a_hex: (i64, i64), t_hex: (i64, i64), target_facing: i64, a_height: Height, t_height: Height) -> &'static str {
    let trace = trace_los_path(a_hex, t_hex, &b.board, a_height, t_height).unwrap();
    let entry = trace.steps[trace.steps.len() - 2].hex;
    let relative = (combat::direction_facing(t_hex, entry).unwrap() - target_facing).rem_euclid(6);
    side_by_relative_hexside(relative)
}

pub fn standing() -> Height {
    mech_height(false, false)
}

/// Where aimed shots at `target` go this phase (p.70), or None.
pub fn aimed_shot_location(b: &Battle, target: UnitId, partial_cover: bool) -> Option<String> {
    let loc = b.cfg.get("AIMED_SHOT_LOCATION").as_str()?.to_string();
    let t = &b.units[target];
    if !is_immobile(t) || !t.locations.contains_key(&loc) {
        return None;
    }
    if t.locations[&loc].destroyed || (partial_cover && t.leg_locations.contains(&loc)) {
        return None;
    }
    Some(loc)
}

pub fn aimed_tn_adjust(aim: &str, cover_modifier: i64) -> i64 {
    -cover_modifier + if aim == "Head" { AIMED_HEAD_ADJUST } else { 0 }
}

/// {weapon: locations its slots sit in} - live and destroyed slots; locations sorted.
pub fn weapon_locations(mech: &Mech) -> WeaponLocs {
    let mut locs: HashMap<ItemId, std::collections::BTreeSet<String>> = HashMap::default();
    for (location, slots) in &mech.crits {
        for slot in slots {
            if let Slot::Item(i) = slot {
                if mech.items[*i].category.as_deref() == Some("weapon") {
                    locs.entry(*i).or_default().insert(location.clone());
                }
            }
        }
    }
    for ((location, _), info) in &mech.destroyed_slot_info {
        if let Some(id) = info.instance_id {
            locs.entry(id).or_default().insert(location.clone());
        }
    }
    locs.into_iter().map(|(k, v)| (k, v.into_iter().collect())).collect()
}

fn destroyed_names<'a>(mech: &'a Mech, location: Option<&str>) -> Vec<&'a str> {
    mech.destroyed_slot_info.iter().filter(|((l, _), _)| location.map_or(true, |x| l == x)).map(|(_, i)| i.name.as_str()).collect()
}

/// Ranged-attack TN modifier from sensor hits, or None if they can't fire.
pub fn sensor_modifier(mech: &Mech) -> Option<i64> {
    let hits = destroyed_names(mech, None).iter().filter(|n| **n == "Sensors").count();
    if mech.torso_cockpit {
        match hits {
            0 => Some(0),
            1 => Some(2),
            2 => Some(4),
            _ => None,
        }
    } else {
        match hits {
            0 => Some(0),
            1 => Some(2),
            _ => None,
        }
    }
}

pub fn arm_actuator_modifier(mech: &Mech, locations: &[String]) -> i64 {
    let mut worst = 0;
    for arm in ARM_LOCATIONS {
        if !locations.iter().any(|l| l == arm) {
            continue;
        }
        let lost = destroyed_names(mech, Some(arm));
        worst = worst.max(if lost.contains(&"Shoulder") { 4 } else if lost.contains(&"Upper Arm Actuator") { 1 } else { 0 });
    }
    worst
}

pub fn arm_aes_modifier(mech: &Mech, locations: &[String]) -> i64 {
    // one location (however many slots), and it is an arm with working AES
    let Some(first) = locations.first() else { return 0 };
    if locations.iter().all(|l| l == first) && ARM_LOCATIONS.contains(&first.as_str()) && arm_aes_working(mech, first) {
        -1
    } else {
        0
    }
}

pub fn has_targeting_computer(mech: &Mech) -> bool {
    let dead: HashSet<ItemId> = mech.destroyed_slot_info.values().filter_map(|i| i.instance_id).collect();
    mech.crits.values().any(|slots| {
        slots.iter().any(|s| match s {
            Slot::Item(i) => mech.items[*i].name.replace(' ', "").to_uppercase().ends_with("TARGETINGCOMPUTER") && !dead.contains(i),
            _ => false,
        })
    })
}

pub fn prone_target_modifier(target: &Mech, distance: i64) -> i64 {
    if !target.prone {
        return 0;
    }
    if distance <= 1 { PRONE_TARGET_ADJACENT } else { PRONE_TARGET_FAR }
}

fn weapon_value(b: &mut Battle, u: UnitId, w: ItemId) -> i64 {
    if weapon_rules::is_ams(b, u, w) {
        return 0;
    }
    let it = &b.units[u].items[w];
    it.damage_per_shot.unwrap_or(0) * it.rack_size.filter(|r| *r != 0).unwrap_or(1)
}

/// (TN modifier, weapons that can't fire), or None if a prone mech can't fire at all (p.67, p.231).
pub fn prone_fire(b: &mut Battle, u: UnitId) -> Option<(i64, HashSet<ItemId>)> {
    if !b.units[u].prone {
        return Some((0, HashSet::default()));
    }
    let locs = weapon_locations(&b.units[u]);
    let weapons = get_weapons(&b.units[u]);
    let in_loc = |place: &[&str]| -> HashSet<ItemId> {
        weapons.iter().copied().filter(|w| locs.get(w).map_or(false, |l| l.iter().any(|x| place.contains(&x.as_str())))).collect()
    };
    let legs: Vec<String> = b.units[u].leg_locations.clone();
    let m = &b.units[u];
    let legs_ok = m.destroyed_hip_locations.is_empty() && !legs.iter().any(|l| m.locations[l.as_str()].destroyed);
    let mech_type = m.mech_type.clone();
    if mech_type == "quad" || mech_type == "quadvee" {
        if legs_ok {
            return Some((0, HashSet::default()));
        }
        let usable: Vec<&String> = legs.iter().filter(|l| !b.units[u].locations[l.as_str()].destroyed).collect();
        // Core p.238 (quad 'Mechs, Firing While Prone): props on one leg only with no more than two legs destroyed;
        // with three or four gone it cannot prop, so it cannot fire while prone. (2026-11-20, found by tools/fair_duels.py:
        // a Scorpion with all four legs gone indexed an empty list and crashed; with three gone it propped against the rule.
        // The frozen Python answer key keeps the old behaviour.)
        if legs.len() - usable.len() > 2 {
            return None;
        }
        // min(): the first of equals, in the legs' set order (hash order in Python: the legs are listed in leg order)
        let mut prop = usable[0];
        let mut best = i64::MAX;
        for l in &usable {
            let v: i64 = weapons.iter().filter(|w| in_loc(&[l.as_str()]).contains(w)).map(|w| weapon_value(b, u, *w)).sum();
            if v < best {
                best = v;
                prop = l;
            }
        }
        return Some((PRONE_FIRE_MODIFIER, in_loc(&[prop.as_str()])));
    }
    if mech_type == "tripod" && legs_ok {
        let legs_s: Vec<&str> = legs.iter().map(|s| s.as_str()).collect();
        return Some((TRIPOD_PRONE_FIRE_MODIFIER, in_loc(&legs_s)));
    }
    let arms: Vec<&str> = ARM_LOCATIONS.iter().copied().filter(|a| b.units[u].locations.contains_key(*a) && !b.units[u].locations[*a].destroyed).collect();
    if arms.is_empty() {
        return None;
    }
    let mut prop = arms[0];
    let mut best = i64::MAX;
    for a in &arms {
        let v: i64 = weapons.iter().filter(|w| in_loc(&[a]).contains(w)).map(|w| weapon_value(b, u, *w)).sum();
        if v < best {
            best = v;
            prop = a;
        }
    }
    let mut place: Vec<&str> = legs.iter().map(|s| s.as_str()).collect();
    place.push(prop);
    Some((PRONE_FIRE_MODIFIER, in_loc(&place)))
}

/// Weapons that can't bear on a target seen as `key`.
pub fn arc_unavailable(m: &Mech, key: &ArcKey) -> HashSet<ItemId> {
    arcs::unavailable(m, &get_weapons(m), &weapon_locations(m), key)
}

/// Attacker-side ranged conditions: (TN modifier, unavailable weapons, note), or None if it can't make ranged attacks.
pub fn firing_conditions(b: &mut Battle, attacker: UnitId) -> Option<(i64, HashSet<ItemId>, String)> {
    let sensors = sensor_modifier(&b.units[attacker]);
    let prone = prone_fire(b, attacker);
    let (sensors, prone) = match (sensors, prone) {
        (Some(s), Some(p)) => (s, p),
        _ => return None,
    };
    let mut note: Vec<String> = Vec::new();
    if sensors != 0 {
        note.push(format!("sensors +{}", sensors));
    }
    if prone.0 != 0 || !prone.1.is_empty() {
        note.push(format!("prone +{}", prone.0));
    }
    let gunner = tripod_gunner_modifier(&b.units[attacker]);
    if gunner != 0 {
        note.push(format!("tripod gunner out +{}", gunner));
    }
    Some((sensors + prone.0 + gunner, prone.1, note.join(", ")))
}

/// attack_resolution.tn_adjuster (and water.range_adjuster around it): the per-weapon TN change.
#[derive(Clone)]
pub struct Adjuster {
    pub attacker: UnitId,
    pub stealth: [(&'static str, i64); 3],
    pub aim: Option<String>,
    pub aim_adjust: i64,
    pub tc: bool,
    pub locs: WeaponLocs,
    pub underwater: Option<HashSet<ItemId>>,
}

pub fn tn_adjuster(b: &Battle, attacker: UnitId, target: UnitId, aim: Option<&str>, cover_modifier: i64) -> Adjuster {
    Adjuster {
        attacker,
        stealth: equip::range_stealth_bonus(&b.units[target]),
        aim: aim.map(|s| s.to_string()),
        aim_adjust: aim.map_or(0, |a| aimed_tn_adjust(a, cover_modifier)),
        tc: has_targeting_computer(&b.units[attacker]),
        locs: weapon_locations(&b.units[attacker]),
        underwater: None,
    }
}

impl TnAdjust for Adjuster {
    fn adjust(&self, b: &mut Battle, w: ItemId, bracket: Option<&str>, plan: Option<&ShotPlan>) -> i64 {
        let a = self.attacker;
        let empty: Vec<String> = Vec::new();
        let locs = self.locs.get(&w).unwrap_or(&empty);
        let mut tn = match bracket {
            Some(br) if !br.is_empty() => self.stealth.iter().find(|(k, _)| *k == br).map_or(0, |(_, v)| *v),
            _ => 0,
        };
        tn += weapon_rules::weapon_tn_modifier(b, a, w, bracket);
        tn += arm_actuator_modifier(&b.units[a], locs);
        tn += arm_aes_modifier(&b.units[a], locs);
        let aiming = self.aim.is_some() && match plan {
            Some(p) => fire_modes::aimable(b, a, w, p),
            None => !weapon_rules::is_cluster(b, a, w),
        };
        if aiming {
            tn += self.aim_adjust;
        }
        let eligible = match plan {
            Some(p) => fire_modes::tc_eligible(b, a, w, p),
            None => weapon_rules::targeting_computer_eligible(b, a, w),
        };
        if self.tc && eligible && !(aiming && (self.aim.as_deref() == Some("Head") || weapon_rules::is_pulse(b, a, w))) {
            tn -= 1;
        }
        if let Some(under) = &self.underwater {
            if under.contains(&w) {
                if let Some(br) = bracket {
                    tn += water::underwater_bracket_tn(br);
                }
            }
        }
        tn
    }
    fn underwater_ids(&self) -> Option<&HashSet<ItemId>> {
        self.underwater.as_ref()
    }
}

/// water.range_adjuster: marks the weapons in submerged locations on the adjuster.
pub fn with_range_adjuster(mut adj: Adjuster, attacker: &Mech, a_state: &str) -> Adjuster {
    adj.underwater = water::submerged_weapon_ids(attacker, &adj.locs, a_state);
    adj
}

/// (TN, weapon, note) of the easiest standard ranged attack with one of `weapons` from where the attacker stands, or
/// None when none can be made (TAG's use).
pub fn single_attack_tn(b: &mut Battle, attacker: UnitId, target: UnitId, weapons: &[ItemId], at_hex: bool) -> Option<(i64, ItemId, String)> {
    let (tns, distance, cond_note) = weapon_attack_tns(b, attacker, target, weapons, at_hex)?;
    let mut best: Option<(i64, ItemId, String)> = None;
    for (w, tn) in tns {
        if best.as_ref().map_or(true, |x| tn < x.0) {
            best = Some((tn, w, format!("range {}{}", distance, if cond_note.is_empty() { String::new() } else { format!(", {}", cond_note) })));
        }
    }
    best
}

/// The standard ranged attack TN of each of `weapons` that could fire at the target from where the attacker stands, in
/// the given order (a weapon out of range, out of arc or otherwise unable is left out), with the range and the firing
/// conditions' note; None when no attack can be made at all (no line of sight, or the attacker cannot fire). `at_hex`:
/// aimed at the hex (no target movement, prone or partial cover modifier). Shared by `single_attack_tn` (TAG) and the
/// Princess / CASPAR deployment's damage estimate (`princess_deploy`, MegaMek's getDeployDamage).
pub fn weapon_attack_tns(b: &mut Battle, attacker: UnitId, target: UnitId, weapons: &[ItemId], at_hex: bool) -> Option<(Vec<(ItemId, i64)>, i64, String)> {
    let a_hex = hex_geometry::parse_hex_label(b.units[attacker].hex.as_deref().unwrap()).unwrap();
    let t_hex = hex_geometry::parse_hex_label(b.units[target].hex.as_deref().unwrap()).unwrap();
    if a_hex == t_hex {
        return None;
    }
    let heights = (los_height(&b.units[attacker]), los_height(&b.units[target]));
    let trace = trace_los_path(a_hex, t_hex, &b.board, heights.0, heights.1).unwrap();
    let cover = if at_hex { 0 } else { trace.steps.last().unwrap().partial_cover };
    let conditions = firing_conditions(b, attacker);
    if !trace.result.los || conditions.is_none() {
        return None;
    }
    let (cond_mod, unavailable, cond_note) = conditions.unwrap();
    let a_water = water::state(b, attacker);
    let t_water = water::state(b, target);
    let w_locs = weapon_locations(&b.units[attacker]);
    let all = get_weapons(&b.units[attacker]);
    let blocked = water::blocked_weapon_ids(&b.units[attacker], &all, &w_locs, a_water, t_water, false)?;
    let a_facing = hex_geometry::compass_to_facing(&b.units[attacker].facing).unwrap();
    let key = arcs::key_for(&arcs::arcs_between(a_hex, t_hex), a_facing, &arcs::current_action(&b.units[attacker]), &arcs::leg_offsets(&b.units[attacker]));
    let mut unavailable = unavailable;
    unavailable.extend(blocked);
    unavailable.extend(arc_unavailable(&b.units[attacker], &key));
    unavailable.extend(shielded_weapon_ids(&b.units[attacker]));
    let distance = hex_distance(a_hex, t_hex);
    let own = if at_hex {
        0
    } else {
        target_tmm(&b.units[target]) + equip::void_signature_modifier(&b.units[target], None, None) + prone_target_modifier(&b.units[target], distance)
    };
    let a = &b.units[attacker];
    let pre_tn = a.gunnery + combat::mode_to_amm(&a.move_mode) + trace.result.modifier + a.heat_fire_modifier + equip::own_attack_modifier(a) + cond_mod + own;
    let adjust = with_range_adjuster(tn_adjuster(b, attacker, target, None, cover), &b.units[attacker], a_water);
    let mut tns = Vec::new();
    for &w in weapons {
        let rm = weapon_selection::weapon_range_mod(b, attacker, w, distance);
        if unavailable.contains(&w) || rm.is_none() {
            continue;
        }
        let br = weapon_selection::range_bracket(b, attacker, w, distance);
        tns.push((w, pre_tn + rm.unwrap() + adjust.adjust(b, w, br, None)));
    }
    Some((tns, distance, cond_note))
}

/// True when some weapon of the attacker could fire at the target, with any torso twist / arm flip it may declare.
pub fn weapons_can_bear(b: &Battle, attacker: UnitId, target: UnitId) -> bool {
    let a_hex = hex_geometry::parse_hex_label(b.units[attacker].hex.as_deref().unwrap()).unwrap();
    let t_hex = hex_geometry::parse_hex_label(b.units[target].hex.as_deref().unwrap()).unwrap();
    if a_hex == t_hex {
        return false;
    }
    let a = &b.units[attacker];
    let pair = arcs::arcs_between(a_hex, t_hex);
    let choices = arcs::arc_keys(&pair, hex_geometry::compass_to_facing(&a.facing).unwrap(), &arcs::arc_options(a, "ranged"), &arcs::leg_offsets(a));
    let total = get_weapons(a).len();
    choices.iter().any(|(key, _)| arc_unavailable(a, key).len() < total)
}

// =============================================================================================================
// Resolution
// =============================================================================================================
pub fn damage_type_for(b: &mut Battle, u: UnitId, w: ItemId) -> DamageType {
    match b.units[u].items[w].damage_type.as_deref() {
        Some("Energy") => DamageType::Energy,
        Some("Ballistic") => DamageType::Ballistic,
        Some("Missile") => DamageType::Missile,
        _ => stub_unknown_damage_type(b, u, w),
    }
}

fn stub_unknown_damage_type(b: &mut Battle, u: UnitId, w: ItemId) -> DamageType {
    let name = b.cfg.s("STUB_UNKNOWN_DAMAGE_TYPE").to_string();
    let dt = DamageType::from_name(&name);
    let wn = b.units[u].items[w].name.clone();
    b.warn_stub("unknown_damage_type", &format!("{} has damage_type null - treated as {}", wn, dt.name()));
    dt
}

pub fn has_heat_dissipating_armor(m: &Mech) -> bool {
    m.armor_type.values().any(|t| *t == ArmorType::HeatDissipating)
}

/// Heat-dissipating armor (p.202): damage from a heat-causing weapon to a location armored with it is halved, rounding up.
fn heat_armor_damage(b: &mut Battle, target: UnitId, loc: &str, damage: i64, heat_weapon: bool) -> i64 {
    if heat_weapon && b.units[target].armor_type.get(loc) == Some(&ArmorType::HeatDissipating) && damage != 0 {
        let halved = -((-damage).div_euclid(2));
        b.log(format!("      Heat-dissipating armor at {}: {} -> {} (p.202).", loc, damage, halved));
        return halved;
    }
    damage
}

/// Weapons behind a raised shield this phase (p.195): none of them fires, rear-mounted ones aside.
pub fn shielded_weapon_ids(mech: &Mech) -> HashSet<ItemId> {
    let blocked = gear::raised_blocks(mech);
    if blocked.is_empty() {
        return HashSet::default();
    }
    let locs = weapon_locations(mech);
    get_weapons(mech).into_iter().filter(|w| locs.get(w).map_or(false, |l| l.iter().any(|x| blocked.contains(x))) && !mech.items[*w].rear_mounted).collect()
}

/// Damage that reaches `loc` after the target's shield (p.195) and then its heat-dissipating armor (p.202).
fn protected(b: &mut Battle, target: UnitId, loc: &str, damage: i64, side: &str, heat_weapon: bool) -> i64 {
    let d = gear::shield_absorb(b, target, loc, damage, side);
    heat_armor_damage(b, target, loc, d, heat_weapon)
}

fn d6(b: &mut Battle, n: i64) -> i64 {
    (0..n).map(|_| b.pick_number(6)).sum()
}

/// A heat-causing weapon's hit (flamers, plasma): outside heat on the target (at most 15 a turn) in its Heat Phase.
pub fn target_heat(b: &mut Battle, target: UnitId, attacker: UnitId, weapon: ItemId) {
    let mut roll = |b: &mut Battle, n: i64| d6(b, n);
    let got = wp::target_heat(b, attacker, weapon, &mut roll);
    let wn = b.units[attacker].items[weapon].name.clone();
    let tn = b.units[target].side_name.clone().unwrap_or_default();
    if got != 0 && has_heat_dissipating_armor(&b.units[target]) {
        b.log(format!("      {}: heat-dissipating armor - no heat to {} (p.202).", wn, tn));
        return;
    }
    if got != 0 {
        let t = &mut b.units[target];
        t.outside_heat = Some(t.outside_heat.unwrap_or(0) + got);
        b.log(format!("      {}: +{} heat to {} (outside heat, p.102).", wn, got, tn));
    }
}

/// hit-location roll, head-hit pilot damage, floating TAC on a 2, then apply_damage(). Returns the location struck.
#[allow(clippy::too_many_arguments)]
pub fn resolve_hit(b: &mut Battle, target: UnitId, damage: i64, damage_type: DamageType, side: &str, tag: &str, reroll_legs: bool, cover: Cover, heat_weapon: bool) -> Option<String> {
    let armor_field = if side == "rear" { "rear_armor" } else { "armor" };
    if cover == Cover::Kick {
        let loc = crate::physical::location(b, "kick", side, target);
        b.log(format!("      {}Kick Location Table ({}; legs only under water, p.67): {}.", tag, side, loc));
        let d = protected(b, target, &loc, damage, side, heat_weapon);
        apply_damage(b, target, &loc, Num::I(d), armor_field, damage_type);
        return Some(loc);
    }
    let mut loc_roll = b.roll_2d6();
    let mut loc = resolve_hit_location(b, target, loc_roll, side);
    b.log(format!("      {}Hit location roll {} ({} table): {}.", tag, loc_roll, side, loc));
    while reroll_legs && b.units[target].leg_locations.contains(&loc) {
        loc_roll = b.roll_2d6();
        loc = resolve_hit_location(b, target, loc_roll, side);
        b.log(format!("      {}Legs behind partial cover - re-rolled {}: {}.", tag, loc_roll, loc));
    }
    if cover.truthy() && b.units[target].leg_locations.contains(&loc) {
        b.log(format!("      {}Leg hit strikes the partial cover - no damage (p.66).", tag));
        return None;
    }
    if loc == "Head" && head_hit_hurts_pilot(&b.units[target]) {
        pilot_hit(&mut b.units[target], 1, true);
        let ph = b.units[target].pilot_hits;
        b.log(format!("      Head hit - pilot takes 1 hit ({}/6), regardless of armor.", ph));
    }
    let floating = b.cfg.b("FLOATING_CRITICALS");
    if loc_roll == 2 && floating && !b.units[target].locations[&loc].destroyed {
        b.log("      Roll of 2 - Through-Armor Critical (floating) triggered.");
        let tac_side = side;
        let mut tac_roll = b.roll_2d6();
        let mut tac_loc = resolve_hit_location(b, target, tac_roll, tac_side);
        let tac_armor_field = if tac_side == "rear" { "rear_armor" } else { "armor" };
        b.log(format!("      Floating TAC re-roll: {} -> {}", tac_roll, tac_loc));
        while cover.truthy() && b.units[target].leg_locations.contains(&tac_loc) {
            tac_roll = b.roll_2d6();
            tac_loc = resolve_hit_location(b, target, tac_roll, tac_side);
            b.log(format!("      Legs behind partial cover - re-rolled {}: {}.", tac_roll, tac_loc));
        }
        if tac_loc == "Head" && head_hit_hurts_pilot(&b.units[target]) {
            pilot_hit(&mut b.units[target], 1, true);
            let ph = b.units[target].pilot_hits;
            b.log(format!("      Head hit - pilot takes 1 hit ({}/6), regardless of armor.", ph));
        }
        let d = protected(b, target, &tac_loc, damage, tac_side, heat_weapon);
        apply_damage(b, target, &tac_loc, Num::I(d), tac_armor_field, damage_type);
        b.log("      Additional critical hit due to TAC.");
        tac_check(b, target, &tac_loc, tac_armor_field, damage_type, false);
        return Some(tac_loc);
    }
    let mut tac_loc: Option<String> = None;
    if loc_roll == 2 && !floating && damage >= 1 {
        let mut t = Some(loc.clone());
        while let Some(l) = &t {
            if b.units[target].locations[l.as_str()].destroyed {
                t = transfer_map(l).map(|s| s.to_string());
            } else {
                break;
            }
        }
        tac_loc = t;
    }
    let d = protected(b, target, &loc, damage, side, heat_weapon);
    apply_damage(b, target, &loc, Num::I(d), armor_field, damage_type);
    if let Some(tl) = tac_loc {
        b.log(format!("      Roll of 2 - Through-Armor Critical: extra critical-hit check at {}.", tl));
        let destroyed = b.units[target].locations[tl.as_str()].destroyed;
        tac_check(b, target, &tl, armor_field, damage_type, destroyed);
    }
    Some(loc)
}

/// The Through-Armor Critical's own critical-hit check at `loc` (p.91).
pub fn tac_check(b: &mut Battle, target: UnitId, loc: &str, armor_field: &str, damage_type: DamageType, location_destroyed: bool) {
    let st = &b.units[target].locations[loc];
    let armor_val = if armor_field == "rear_armor" && st.rear_armor.is_some() { st.rear_armor.unwrap() } else { st.armor };
    let armor_type = if damage_type == DamageType::Reengineered { ArmorType::Standard } else { *b.units[target].armor_type.get(loc).unwrap_or(&ArmorType::Standard) };
    let modifier = crate::armor_rules::crit_roll_modifier(b.units[target].structure_type, Some(armor_type), armor_val > Num::I(0));
    check_critical(b, target, loc, location_destroyed, modifier);
}

/// One hit of an ordinary attack: a flat hit, or a Cluster Hits Table roll and one hit per damage group.
fn resolve_one_attack(b: &mut Battle, attacker: UnitId, target: UnitId, attack: &DeclaredAttack, pool: &mut Option<Pool>) {
    let w = attack.weapon;
    let wname = b.units[attacker].items[w].name.clone();
    let tname = b.units[target].side_name.clone().unwrap_or_default();
    if electronics::is_narc(b, attacker, w) {
        resolve_pod(b, attacker, target, attack);
        return;
    }
    let plan = attack.fire.clone().unwrap_or_else(ShotPlan::plain);
    target_heat(b, target, attacker, w);
    let tag_hex = b.units[target].tag_designated.as_deref() == Some("hex");
    if plan.kind == "homing" && tag_hex {
        b.log(format!("    {} homing missile hits the TAG-designated hex: {} area-effect damage to {} in it (p.190; Daniel 2026-10-21).", wname, wp::HOMING_AE, tname));
        resolve_area(b, target, wp::HOMING_AE, &attack.side, attack.cover);
        return;
    }
    if plan.kind == "homing" {
        let dmg = wp::homing_damage(b, attacker, w);
        b.log(format!("    {} homing missile hits the TAG-designated {}: {} direct-fire ballistic damage (p.190):", wname, tname, dmg));
        resolve_hit(b, target, dmg, DamageType::Ballistic, &attack.side, "", false, attack.cover, false);
        return;
    }
    if plan.kind == "artillery" || wp::is_art_cannon(b, attacker, w) {
        let dmg = fire_modes::damage_per(b, attacker, w, &plan).unwrap_or(0);
        b.log(format!("    {} hits {}'s hex: {} area-effect damage (pp.182-183).", wname, tname, dmg));
        resolve_area(b, target, dmg, &attack.side, attack.cover);
        return;
    }
    if adv::is_nail_gun(b, attacker, w) {
        resolve_nail(b, target, attack, &wname);
        return;
    }
    let mut per = fire_modes::damage_per(b, attacker, w, &plan).unwrap_or(0);
    let inferno = fire_modes::is_inferno(&plan);
    if per == 0 && !inferno {
        b.log(format!("    {} hit - zero damage weapon, no damage resolution.", wname));
        return;
    }
    let side = attack.side.clone();
    let col = fire_modes::column(b, attacker, w, &plan);
    let streak = weapon_rules::is_streak(b, attacker, w) && plan.guidance.streak_lock;
    let mut modi = fire_modes::cluster_modifier(b, attacker, w, &plan);
    let pn = plan.note();
    let note = if pn.is_empty() { String::new() } else { format!(" ({})", pn) };
    let dtype = damage_type_for(b, attacker, w);
    let engaged: Vec<ItemId> = [attack.ams, attack.apds].into_iter().flatten().collect();
    let tgt_name = |b: &Battle, i: ItemId| b.units[target].items[i].name.clone();
    if !engaged.is_empty() && col.is_none() {
        for system in &engaged {
            let die = b.pick_number(6);
            let sn = tgt_name(b, *system);
            if die >= crate::ams::SINGLE_MISSILE_KILL {
                b.log(format!("    {} hit - {} rolls 1D6 {}: missile destroyed, no damage (p.206).", wname, sn, die));
                return;
            }
            b.log(format!("    {} hit - {} rolls 1D6 {}: the missile gets through.", wname, sn, die));
        }
    }
    if attack.aimed_at.is_some() {
        resolve_aimed_hit(b, attacker, target, w, per, dtype, &side, attack);
        return;
    }
    let Some(col) = col else {
        per = equip::blue_shield_damage(b, target, attacker, w, per);
        b.log(format!("    {} hit for {}{}:", wname, per, note));
        let hc = wp::heat_causing(b, attacker, w);
        resolve_hit(b, target, per, dtype, &side, "", false, attack.cover, hc);
        return;
    };
    if col == 0 {
        b.log(format!("    {} hit - no guns left to fire.", wname));
        return;
    }
    let names: Vec<String> = engaged.iter().map(|i| tgt_name(b, *i)).collect();
    let names = names.join(" + ");
    let hits: i64;
    if streak && !engaged.is_empty() {
        let result = 2.max(12 - crate::ams::STREAK_CUT * engaged.len() as i64);
        hits = cluster_hits_count(b, col, result).unwrap();
        b.log(format!("    {} hit: Streak engaged by {} - result {} on the {}-column table -> {} connect ({} dmg).", wname, names, result, col, hits, hits * per));
    } else if streak {
        hits = col;
        b.log(format!("    {} hit: Streak - all {} missiles hit ({} dmg).", wname, hits, hits * per));
    } else if !engaged.is_empty() {
        let raw = b.roll_2d6();
        modi += crate::ams::CLUSTER_MODIFIER * engaged.len() as i64;
        if raw + modi < 2 {
            b.log(format!("    {} hit: cluster roll {} {:+} (AMS {}){} = {} - below 2, every missile destroyed, no damage.", wname, raw, modi, names, note, raw + modi));
            return;
        }
        hits = cluster_hits_count(b, col, 12.min(raw + modi)).unwrap();
        b.log(format!("    {} hit: cluster roll {} {:+} (AMS {}){} on the {}-column table -> {} connect ({} dmg).", wname, raw, modi, names, note, col, hits, hits * per));
    } else {
        let raw = b.roll_2d6();
        let cluster_roll = 2.max(12.min(raw + modi));
        hits = cluster_hits_count(b, col, cluster_roll).unwrap();
        b.log(format!(
            "    {} hit: cluster roll {}{}{} on the {}-column table -> {} connect ({} dmg).",
            wname,
            raw,
            if modi != 0 { format!(" {:+}", modi) } else { String::new() },
            note,
            col,
            hits,
            hits * per
        ));
    }
    if inferno {
        adv::inferno_hit(b, target, hits, &format!("{} infernos", wname), has_heat_dissipating_armor(&b.units[target]));
        return;
    }
    if plan.kind == "imp" {
        let turn = b.units[attacker].turn_number;
        adv::imp_hit(b, target, hits, turn, has_heat_dissipating_armor(&b.units[target]));
    }
    let mut total = hits * per;
    if wp::is_mga(b, attacker, w) {
        let loc = resolve_hit(b, target, per, dtype, &side, "Array: ", false, attack.cover, false);
        for _ in 0..(hits - 1) {
            if loc.is_none() || b.units[target].destroyed {
                break;
            }
            let l = loc.as_ref().unwrap().clone();
            if l == "Head" && head_hit_hurts_pilot(&b.units[target]) {
                pilot_hit(&mut b.units[target], 1, true);
            }
            let d = protected(b, target, &l, per, &side, false);
            apply_damage(b, target, &l, Num::I(d), if side == "rear" { "rear_armor" } else { "armor" }, dtype);
        }
        return;
    }
    if plan.kind == "saturation" {
        total = fire_modes::third(hits);
        b.log(format!("      Apollo saturation: {} missiles / 3 = {} area-effect damage (p.197).", hits, total));
        resolve_area(b, target, total, &side, attack.cover);
        return;
    }
    let size = fire_modes::grouping(b, attacker, w, &plan);
    if let Some(p) = pool {
        p.add((size, dtype, side.clone(), attack.cover), wname.clone(), total);
        return;
    }
    apply_groups(b, target, total, size, dtype, &side, attack.cover, "");
}

/// The optional pooled-cluster-damage rule: (size, damage type, side, cover) -> [(weapon name, damage)], insertion order.
#[derive(Default)]
pub struct Pool {
    pub entries: Vec<((i64, DamageType, String, Cover), Vec<(String, i64)>)>,
}

impl Pool {
    fn add(&mut self, key: (i64, DamageType, String, Cover), name: String, total: i64) {
        match self.entries.iter_mut().find(|(k, _)| *k == key) {
            Some((_, v)) => v.push((name, total)),
            None => self.entries.push((key, vec![(name, total)])),
        }
    }
}

/// A nail / rivet gun hit (MegaMek's rule): 1D6 to a location with no armor left.
fn resolve_nail(b: &mut Battle, target: UnitId, attack: &DeclaredAttack, wname: &str) {
    let side = attack.side.as_str();
    let mut field = if side == "rear" { "rear_armor" } else { "armor" };
    let loc_roll = b.roll_2d6();
    let mut loc: Option<String> = Some(resolve_hit_location(b, target, loc_roll, side));
    b.log(format!("    {} hit - hit location roll {} ({} table): {}.", wname, loc_roll, side, loc.as_ref().unwrap()));
    if attack.cover.truthy() && b.units[target].leg_locations.contains(loc.as_ref().unwrap()) {
        b.log("      Leg hit strikes the partial cover - no damage (p.66).");
        return;
    }
    while let Some(l) = &loc {
        if b.units[target].locations[l.as_str()].destroyed {
            loc = transfer_map(l).map(|s| s.to_string());
            field = "armor";
        } else {
            break;
        }
    }
    let Some(loc) = loc else { return };
    let armored = |b: &Battle, name: &str, key: &str| -> bool {
        let here = &b.units[target].locations[name];
        let modular = b.units[target].modular_armor.iter().any(|s| {
            let it = &b.units[target].items[*s];
            it.modular_points.unwrap_or(0) > 0 && it.modular_location.as_deref().unwrap_or(name) == name
        });
        let a = if key == "rear_armor" { here.rear_armor.unwrap_or(here.armor) } else { here.armor };
        a > Num::I(0) || modular
    };
    if armored(b, &loc, field) {
        b.log(format!("      {} still has armor - the nails do nothing (MegaMek: armor BAR 5+).", loc));
        return;
    }
    let mut dmg = b.pick_number(adv::NAIL_DIE);
    let structure = b.units[target].locations[loc.as_str()].structure;
    let nxt = transfer_map(&loc);
    let nxt_ok = nxt.is_some_and(|n| !b.units[target].locations[n].destroyed && armored(b, n, "armor"));
    if Num::I(dmg) > structure && nxt_ok {
        b.log(format!("      1D6 = {}; only {} can land - the rest would transfer into armor.", dmg, structure.py_str()));
        dmg = match structure {
            Num::I(i) => i,
            Num::F(f) => f as i64,
        };
    } else {
        b.log(format!("      1D6 = {} damage to the bare {}.", dmg, loc));
    }
    if loc == "Head" && dmg > 0 && head_hit_hurts_pilot(&b.units[target]) {
        pilot_hit(&mut b.units[target], 1, true);
        let ph = b.units[target].pilot_hits;
        b.log(format!("      Head hit - pilot takes 1 hit ({}/6).", ph));
    }
    apply_damage(b, target, &loc, Num::I(dmg), field, DamageType::Ballistic);
}

/// `total` damage in `size`-point groupings, the remainder last (p.87).
pub fn apply_groups(b: &mut Battle, target: UnitId, total: i64, size: i64, dtype: DamageType, side: &str, cover: Cover, label: &str) {
    let full = total.div_euclid(size);
    let mut groups: Vec<i64> = vec![size; full as usize];
    if total.rem_euclid(size) != 0 {
        groups.push(total - size * full);
    }
    let n = groups.len();
    for (i, dmg) in groups.into_iter().enumerate() {
        resolve_hit(b, target, dmg, dtype, side, &format!("{}Group {}/{}: ", label, i + 1, n), false, cover, false);
    }
}

/// Area-effect damage on a 'Mech in the hex: 5-point groupings, standard hit location table.
pub fn resolve_area(b: &mut Battle, target: UnitId, damage: i64, side: &str, cover: Cover) {
    apply_groups(b, target, damage, wp::AREA_GROUPING, DamageType::Missile, side, cover, "AE ");
}

fn in_firing_arc(b: &Battle, attacker: UnitId, weapon: ItemId, xy: (i64, i64)) -> bool {
    let a = &b.units[attacker];
    let key = arcs::key_for(
        &arcs::arcs_between(hex_geometry::parse_hex_label(a.hex.as_deref().unwrap()).unwrap(), xy),
        hex_geometry::compass_to_facing(&a.facing).unwrap(),
        &arcs::current_action(a),
        &arcs::leg_offsets(a),
    );
    !arc_unavailable(a, &key).contains(&weapon)
}

/// A missed Arrow IV / artillery cannon scatters (pp.182-183).
fn resolve_area_miss(b: &mut Battle, attacker: UnitId, target: UnitId, attack: &DeclaredAttack) {
    let w = attack.weapon;
    let wname = b.units[attacker].items[w].name.clone();
    let tname = b.units[target].side_name.clone().unwrap_or_default();
    let mof = attack.tn - attack.roll;
    let dist = -((-mof).div_euclid(2));
    let direction = b.pick_number(6) - 1;
    let (tx, ty) = hex_geometry::parse_hex_label(b.units[target].hex.as_deref().unwrap()).unwrap();
    let (dx, dy) = hex_geometry::FACING_DELTAS[direction as usize];
    let mut steps = 0;
    while steps < dist && in_firing_arc(b, attacker, w, (tx + dx * (steps + 1), ty + dy * (steps + 1))) {
        steps += 1;
    }
    let impact = (tx + dx * steps, ty + dy * steps);
    let held = if steps < dist { format!(" (held to {} by the firing arc, pp.182-183)", steps) } else { String::new() };
    if steps == 0 {
        let plan = attack.fire.clone().unwrap_or_else(ShotPlan::plain);
        let dmg = fire_modes::damage_per(b, attacker, w, &plan).unwrap_or(0);
        b.log(format!(
            "    {} missed by {}: scatters {} hex{} (direction {}), but the firing arc holds it in {}'s hex: {} area-effect damage (pp.182-183).",
            wname,
            mof,
            dist,
            if dist > 1 { "es" } else { "" },
            direction + 1,
            tname,
            dmg
        ));
        resolve_area(b, target, dmg, &attack.side, attack.cover);
        return;
    }
    if wp::splash(b, attacker, w) == 0 {
        b.log(format!("    {} missed - the shell lands {} hex{} away from {}{} (no splash).", wname, steps, if steps > 1 { "es" } else { "" }, tname, held));
        return;
    }
    let label = hex_geometry::hex_label(impact.0, impact.1).ok();
    let on_board = label.as_ref().is_some_and(|l| b.board.hexes.contains_key(l));
    b.log(format!(
        "    {} missed by {}: scatters {} hex{} (direction {}){} to {}{}.",
        wname,
        mof,
        dist,
        if dist > 1 { "es" } else { "" },
        direction + 1,
        held,
        label.clone().unwrap_or_else(|| "off the board".to_string()),
        if on_board { "" } else { " - off the board, no effect" }
    ));
    if on_board && steps == 1 {
        let tf = hex_geometry::compass_to_facing(&b.units[target].facing).unwrap();
        let side = attack_side(b, impact, (tx, ty), tf, standing(), standing());
        let dmg = wp::splash(b, attacker, w);
        b.log(format!("      {} is next to the impact: {} area-effect damage.", tname, dmg));
        resolve_area(b, target, dmg, side, Cover::No);
    }
}

/// A Narc / iNarc beacon hit (pp.188, 193).
fn resolve_pod(b: &mut Battle, attacker: UnitId, target: UnitId, attack: &DeclaredAttack) {
    let w = attack.weapon;
    let wname = b.units[attacker].items[w].name.clone();
    let tname = b.units[target].side_name.clone().unwrap_or_default();
    let munition = attack.fire.clone().unwrap_or_else(ShotPlan::plain).guidance.munition;
    for system in [attack.ams, attack.apds].into_iter().flatten() {
        let die = b.pick_number(6);
        let sn = b.units[target].items[system].name.clone();
        if die >= crate::ams::SINGLE_MISSILE_KILL {
            b.log(format!("    {} hit - {} rolls 1D6 {}: pod destroyed (p.206).", wname, sn, die));
            return;
        }
        b.log(format!("    {} hit - {} rolls 1D6 {}: the pod gets through.", wname, sn, die));
    }
    if munition == "explosive" {
        let key = b.units[attacker].items[w].ammo_key.clone().unwrap_or_default();
        let dmg = ammo::explosive_pod_damage(&key).unwrap_or(0);
        b.log(format!("    {} hit: explosive pod for {}:", wname, dmg));
        resolve_hit(b, target, dmg, DamageType::Missile, &attack.side, "", false, attack.cover, false);
        return;
    }
    let roll = b.roll_2d6();
    let mut loc = resolve_hit_location(b, target, roll, &attack.side);
    if attack.cover == Cover::Kick {
        loc = crate::physical::location(b, "kick", &attack.side, target);
    } else if attack.cover.truthy() && b.units[target].leg_locations.contains(&loc) {
        b.log(format!("    {} hit: location roll {} -> {}, behind partial cover - the pod strikes the cover.", wname, roll, loc));
        return;
    }
    let owner = b.units[attacker].side_name.clone().unwrap_or_default();
    electronics::attach_pod(&mut b.units[target], &loc, &owner);
    let blocked = electronics::narc_blocked(&b.units[target]);
    b.log(format!(
        "    {} hit: homing pod attached to {}'s {} (location roll {}); works from the next phase{}.",
        wname,
        tname,
        loc,
        roll,
        if blocked { " - but its ECM blocks it" } else { "" }
    ));
}

/// p.70: 1D6 4+ puts the hit on the aimed location; otherwise roll normally.
#[allow(clippy::too_many_arguments)]
fn resolve_aimed_hit(b: &mut Battle, attacker: UnitId, target: UnitId, weapon: ItemId, damage: i64, dtype: DamageType, side: &str, attack: &DeclaredAttack) {
    let wname = b.units[attacker].items[weapon].name.clone();
    let aimed = attack.aimed_at.clone().unwrap();
    let die = b.pick_number(6);
    let hc = wp::heat_causing(b, attacker, weapon);
    if die < AIMED_SHOT_SUCCESS {
        b.log(format!("    {} hit for {}: aimed at {}, 1D6 {} - rolls for location.", wname, damage, aimed, die));
        resolve_hit(b, target, damage, dtype, side, "", attack.cover.truthy(), Cover::No, hc);
        return;
    }
    b.log(format!("    {} hit for {}: aimed at {}, 1D6 {} - on target.", wname, damage, aimed, die));
    if aimed == "Head" && head_hit_hurts_pilot(&b.units[target]) {
        pilot_hit(&mut b.units[target], 1, true);
        let ph = b.units[target].pilot_hits;
        b.log(format!("      Head hit - pilot takes 1 hit ({}/6), regardless of armor.", ph));
    }
    let d = protected(b, target, &aimed, damage, side, hc);
    apply_damage(b, target, &aimed, Num::I(d), if side == "rear" { "rear_armor" } else { "armor" }, dtype);
}

#[allow(dead_code)]
fn _unused(_: &LOSTrace, _: &LOSResult) {}

// =============================================================================================================
// Declaration
// =============================================================================================================
/// Everything `_declare` works out before the weapon choice - and the choice needs, and the log line after it prints.
pub struct DeclCtx {
    pub attacker: UnitId,
    pub target: UnitId,
    pub a_hex: (i64, i64),
    pub t_hex: (i64, i64),
    pub indirect: bool,
    pub los_modifier: i64,
    pub cover: i64,
    pub a_facing: i64,
    pub pair_arcs: [i64; 6],
    pub arc_choices: Vec<(ArcKey, crate::mech_state::ArcAction)>,
    pub distance: i64,
    pub amm: i64,
    pub tmm: i64,
    pub heat_mod: i64,
    pub stealth_mod: i64,
    pub cond_note: String,
    pub unavailable: HashSet<ItemId>,
    pub w_locs: WeaponLocs,
    pub kick_ids: HashSet<ItemId>,
    pub prone_mod: i64,
    pub pre_tn: i64,
    pub aim: Option<String>,
    pub adjust: Adjuster,
    pub side: String,
    pub sel_pre_tn: i64,
    pub pod_values: HashMap<ItemId, f64>,
    pub hex_offset: i64,
    pub ams_share: f64,
    pub dissipation: i64,
    pub other: i64,
}

pub use crate::mech_state::ArcAction;

/// The bot's choice: (value, (weapons, expected damage, weapon heat), arc key, arc action, the physical attack planned
/// alongside, its value, the limbs' weapons held back). THE decision of a declaration (RUST PORT stage 0b).
#[derive(Clone, Debug)]
pub struct DeclChoice {
    pub weapons: Vec<ItemId>,
    pub exp_dmg: f64,
    pub weapon_heat: i64,
    pub key_torso_arc: i64,
    pub action: ArcAction,
    pub phys_names: Vec<String>,
    pub phys_value: f64,
    pub held: HashSet<ItemId>,
}

pub enum Prep {
    /// returned early (the reason is in the log)
    Done,
    Ready(Box<DeclCtx>),
}

/// `_declare` up to the weapon choice. dry: nothing is changed or logged (the caller wraps it in a quiet block).
pub fn prepare_declaration(b: &mut Battle, attacker: UnitId, target: UnitId, dry: bool) -> Prep {
    let a_name = b.units[attacker].side_name.clone().unwrap_or_default();
    let t_name = b.units[target].side_name.clone().unwrap_or_default();
    if b.units[attacker].shutdown {
        b.log(format!("  [Ranged] {}: shut down - no attacks.", a_name));
        return Prep::Done;
    }
    if b.units[attacker].charging.is_some() || b.units[attacker].dfa.is_some() {
        let what = if b.units[attacker].charging.is_some() { "charging" } else { "in a death from above on" };
        b.log(format!("  [Ranged] {}: {} {} - no ranged attacks this turn (pp.78-79).", a_name, what, t_name));
        return Prep::Done;
    }
    let a_hex = hex_geometry::parse_hex_label(b.units[attacker].hex.as_deref().unwrap()).unwrap();
    let t_hex = hex_geometry::parse_hex_label(b.units[target].hex.as_deref().unwrap()).unwrap();
    if a_hex == t_hex {
        b.log(format!("  [Ranged] {}: same hex as target - no attack (undefined).", a_name));
        return Prep::Done;
    }
    if !dry {
        crate::stubs::stub_unconfirmed_weapon_data(b, attacker);
    }
    let heights = (los_height(&b.units[attacker]), los_height(&b.units[target]));
    let trace = trace_los_path(a_hex, t_hex, &b.board, heights.0, heights.1).unwrap();
    let mut los = trace.result.clone();
    let mut cover = trace.steps.last().unwrap().partial_cover;
    let mut indirect = false;
    if !los.los {
        if adv::indirect_weapons(b, attacker).is_empty() {
            b.log(format!("  [Ranged] {}: no LOS to {} - holds fire.", a_name, t_name));
            return Prep::Done;
        }
        indirect = true;
        los = LOSResult { los: true, modifier: crate::los::target_hex_modifier(t_hex, &b.board).unwrap(), distance: hex_distance(a_hex, t_hex) };
        cover = 0;
        b.log(format!(
            "  [Ranged] {}: no LOS to {} - only its mortars may fire, indirectly (+{}: indirect +1, no spotter +2; target hex terrain only).",
            a_name,
            t_name,
            adv::MORTAR_INDIRECT_MODIFIER
        ));
    }
    let a_facing = hex_geometry::compass_to_facing(&b.units[attacker].facing).unwrap();
    let pair_arcs = arcs::arcs_between(a_hex, t_hex);
    let arc_choices = arcs::arc_keys(&pair_arcs, a_facing, &arcs::arc_options(&b.units[attacker], "ranged"), &arcs::leg_offsets(&b.units[attacker]));
    let total_weapons = get_weapons(&b.units[attacker]).len();
    if arc_choices.iter().all(|(key, _)| arc_unavailable(&b.units[attacker], key).len() == total_weapons) {
        b.log(format!("  [Ranged] {}: no weapon can bear on {} ({} arc) - can't fire.", a_name, t_name, arcs::arc_name(pair_arcs[a_facing as usize])));
        return Prep::Done;
    }

    let distance = hex_distance(a_hex, t_hex);
    let amm = combat::mode_to_amm(&b.units[attacker].move_mode);
    let tmm = target_tmm(&b.units[target]);
    let heat_mod = b.units[attacker].heat_fire_modifier;
    let stealth_mod = equip::void_signature_modifier(&b.units[target], None, None) + equip::own_attack_modifier(&b.units[attacker]);
    let Some((cond_mod, mut unavailable, cond_note)) = firing_conditions(b, attacker) else {
        b.log(format!("  [Ranged] {}: can't make ranged attacks (sensors destroyed, or prone with no arm to prop on).", a_name));
        return Prep::Done;
    };
    unavailable.extend(ammo::unavailable_weapons(&b.units[attacker]));
    unavailable.extend(fire_modes::jammed_ids(&b.units[attacker]));
    unavailable.extend(wp::array_gun_ids(b, attacker));
    unavailable.extend(shielded_weapon_ids(&b.units[attacker]));
    unavailable.extend(adv::no_effect_ids(b, attacker));
    if indirect {
        let ind: HashSet<ItemId> = adv::indirect_weapons(b, attacker).into_iter().collect();
        for w in get_weapons(&b.units[attacker]) {
            if !ind.contains(&w) {
                unavailable.insert(w);
            }
        }
    }
    let a_water = water::state(b, attacker);
    let t_water = water::state(b, target);
    let w_locs = weapon_locations(&b.units[attacker]);
    let all_w = get_weapons(&b.units[attacker]);
    let torpedo_line = a_water != water::GROUND && t_water != water::GROUND && {
        let (al, tl) = (b.units[attacker].hex.clone().unwrap(), b.units[target].hex.clone().unwrap());
        water::water_line(&b.board, &al, &tl)
    };
    let Some(water_blocked) = water::blocked_weapon_ids(&b.units[attacker], &all_w, &w_locs, a_water, t_water, torpedo_line) else {
        b.log(format!("  [Ranged] {} ({}) can't attack {} ({}) across the water line (p.62) - holds fire.", a_name, a_water, t_name, t_water));
        return Prep::Done;
    };
    unavailable.extend(water_blocked);
    let kick_ids = water::kick_table_weapon_ids(&b.units[attacker], &all_w, &w_locs, a_water, t_water);
    let prone_mod = prone_target_modifier(&b.units[target], distance);
    let other_mod = cond_mod + prone_mod;
    let probe_mod = if indirect { 0 } else { -smoke::probe_relief(b, attacker, target, &trace, distance) };
    if probe_mod != 0 {
        b.log(format!("  [Ranged] {}'s active probe sees through the smoke on the line ({}).", a_name, probe_mod));
    }
    let pre_tn = b.units[attacker].gunnery + amm + tmm + los.modifier + heat_mod + stealth_mod + other_mod + probe_mod;

    let mut aim: Option<String> = None;
    if is_immobile(&b.units[target]) && b.cfg.get("AIMED_SHOT_LOCATION").as_str().is_some() {
        aim = aimed_shot_location(b, target, cover > 0);
    }
    let adjust = with_range_adjuster(tn_adjuster(b, attacker, target, aim.as_deref(), cover), &b.units[attacker], a_water);
    let side = attack_side(b, a_hex, t_hex, hex_geometry::compass_to_facing(&b.units[target].facing).unwrap(), heights.0, heights.1).to_string();
    let sel_pre_tn = weapon_selection::PRE_TN_MIN.max(weapon_selection::PRE_TN_MAX.min(pre_tn));
    let usable: Vec<ItemId> = get_weapons(&b.units[attacker]).into_iter().filter(|w| !unavailable.contains(w)).collect();
    let k = if crate::ams::can_engage(&b.units[target]) {
        let cov = crate::ams::covering(b, target, a_hex, None);
        crate::ams::engagement_capacity(&b.units[target], &cov)
    } else {
        0
    };
    let mut pod_values: HashMap<ItemId, f64> = HashMap::default();
    let narcs: Vec<ItemId> = usable.iter().copied().filter(|w| electronics::is_narc(b, attacker, *w)).collect();
    if !narcs.is_empty() {
        let worth = electronics::pod_value(b, attacker, target, distance, sel_pre_tn, &adjust);
        for w in narcs {
            pod_values.insert(w, worth);
        }
    }
    let hex_offset = -(tmm + prone_mod + equip::void_signature_modifier(&b.units[target], None, None));
    let share = fire_modes::ams_share(b, attacker, k, &usable);
    let dissipation = compute_heat_dissipation(&b.units[attacker]) + water::dissipation_bonus(b, attacker, None);
    let other = crate::heat::other_heat(b, attacker);
    Prep::Ready(Box::new(DeclCtx {
        attacker,
        target,
        a_hex,
        t_hex,
        indirect,
        los_modifier: los.modifier,
        cover,
        a_facing,
        pair_arcs,
        arc_choices,
        distance,
        amm,
        tmm,
        heat_mod,
        stealth_mod,
        cond_note,
        unavailable,
        w_locs,
        kick_ids,
        prone_mod,
        pre_tn,
        aim,
        adjust,
        side,
        sel_pre_tn,
        pod_values,
        hex_offset,
        ams_share: share,
        dissipation,
        other,
    }))
}

/// About how much damage the chosen weapons deal (expected, no heat or utility terms) - a special weapon by its
/// planner, the rest by the table.
pub fn plan_damage(b: &mut Battle, attacker: UnitId, weapons: &[ItemId], planner: &mut Planner, distance: i64, pre_tn: i64) -> f64 {
    let mut damage = 0.0;
    for &w in weapons {
        if fire_modes::special(b, attacker, w) {
            damage += planner.plan_for(b, w, distance, pre_tn).map_or(0.0, |g| g.0);
        } else {
            damage += table_value(b, attacker, w, distance, pre_tn).unwrap_or(0.0);
        }
    }
    damage
}

/// weapon_selection.build_expected_damage_table(attacker)[weapon][distance][pre_tn], or None when the table has no row.
pub fn table_value(b: &mut Battle, attacker: UnitId, w: ItemId, distance: i64, pre_tn: i64) -> Option<f64> {
    if b.units[attacker].items[w].damage_per_shot.is_none() || weapon_rules::is_ams(b, attacker, w) {
        return None;
    }
    let rm = weapon_selection::weapon_range_mod(b, attacker, w, distance)?;
    let ed = crate::expected_damage::expected_damage_per_hit(b, attacker, w, 0).ok()?;
    let ed = match ed {
        Num::I(i) => i as f64,
        Num::F(f) => f,
    };
    Some(ed * combat::hit_probability(pre_tn + rm))
}

fn choice_note(b: &mut Battle, attacker: UnitId, weapons: &[ItemId], value: f64, planner: &mut Planner, distance: i64, pre_tn: i64) -> String {
    if !b.units[attacker].is_princess_family() {
        return format!("expected dmg {}", crate::pyfmt::Fx(value, 2));
    }
    let damage = plan_damage(b, attacker, weapons, planner, distance, pre_tn);
    format!("Princess plan utility {}, about {} expected dmg", crate::pyfmt::Fx(value, 2), crate::pyfmt::Fx(damage, 2))
}

/// `_declare` after the choice: declares the arc action, logs the attack line, rolls to hit for each selected weapon
/// and fills `report`. `record_damage`: Princess's damage map (called with the plan's expected damage) or None.
/// A weapon's place in the firing order: (the most damage one hit puts into one location, the size of its cluster). A missile
/// rack puts its grouping (SRM 2, LRM 5...) into a location at a time, any other weapon its whole damage; the cluster size is
/// the rack (0 for a weapon that is not a cluster). Larger first on both counts.
pub fn salvo_key(b: &mut Battle, attacker: UnitId, w: ItemId, plan: &ShotPlan) -> (i64, i64) {
    if weapon_rules::is_cluster(b, attacker, w) {
        (fire_modes::grouping(b, attacker, w, plan), b.units[attacker].items[w].rack_size.unwrap_or(0))
    } else {
        (fire_modes::damage_per(b, attacker, w, plan).unwrap_or(0), 0)
    }
}

pub fn finish_declaration(
    b: &mut Battle,
    ctx: &DeclCtx,
    planner: &mut Planner,
    choice: &DeclChoice,
    report: &mut SideReport,
    record_damage: Option<&mut dyn FnMut(&mut Battle, f64)>,
) {
    let (attacker, target) = (ctx.attacker, ctx.target);
    let a_name = b.units[attacker].side_name.clone().unwrap_or_default();
    let t_name = b.units[target].side_name.clone().unwrap_or_default();
    let weapons = &choice.weapons;
    let mut chosen = choice.action.clone();
    if weapons.is_empty() {
        let cur = arcs::current_action(&b.units[attacker]);
        chosen = ArcAction { twist: cur.twist, flip: cur.flip, turret: chosen.turret.clone() };
    }
    arcs::declare(&mut b.units[attacker], chosen.clone());
    let desc = arcs::describe(&chosen);
    if !desc.is_empty() && !weapons.is_empty() {
        b.log(format!("  [Ranged] {} {} ({} is in its torso's {} arc after that).", a_name, desc, t_name, arcs::arc_name(choice.key_torso_arc)));
    }
    let mut held_names: Vec<String> = Vec::new();
    for w in get_weapons(&b.units[attacker]) {
        if choice.held.contains(&w) && !ctx.unavailable.contains(&w) && !weapon_rules::is_ams(b, attacker, w) {
            held_names.push(b.units[attacker].items[w].name.clone());
        }
    }
    held_names.sort();
    held_names.dedup();
    if !choice.phys_names.is_empty() && !held_names.is_empty() {
        b.log(format!(
            "  [Ranged] {} holds {} back for the Physical phase (plans {}, expected {}).",
            a_name,
            crate::damage_resolution::py_str_list(&held_names),
            choice.phys_names.join(", "),
            crate::pyfmt::Fx(choice.phys_value, 2)
        ));
    }
    if let Some(rec) = record_damage {
        if !weapons.is_empty() {
            let d = plan_damage(b, attacker, weapons, planner, ctx.distance, ctx.sel_pre_tn);
            rec(b, d);
        }
    }
    let movement_heat = b.units[attacker].movement_heat;
    let budget = crate::heat::weapon_heat_budget(b, attacker, movement_heat);
    let surcharge = if weapons.is_empty() { 0 } else { crate::heat::weapon_fire_surcharge(&b.units[attacker]) };
    let note_c = choice_note(b, attacker, weapons, choice.exp_dmg, planner, ctx.distance, ctx.sel_pre_tn);
    {
        let a = &b.units[attacker];
        let names: Vec<String> = weapons.iter().map(|w| a.items[*w].name.clone()).collect();
        let firing = if names.is_empty() { "nothing".to_string() } else { crate::damage_resolution::py_str_list(&names) };
        let mut line = format!(
            "  [Ranged] {} -> {}: range {}, base TN {} (gunnery {} + AMM {} [{}] + TMM {} + LOS {} + heat {}",
            a_name, t_name, ctx.distance, ctx.pre_tn, a.gunnery, ctx.amm, a.move_mode, ctx.tmm, ctx.los_modifier, ctx.heat_mod
        );
        if ctx.stealth_mod != 0 {
            line += &format!(" + stealth {}", ctx.stealth_mod);
        }
        if !ctx.cond_note.is_empty() {
            line += &format!(" + {}", ctx.cond_note);
        }
        if ctx.prone_mod != 0 {
            line += &format!(" + prone target {}", ctx.prone_mod);
        }
        line += &format!("); firing {}", firing);
        if let Some(aim) = &ctx.aim {
            line += &format!(" (aimed at {})", aim);
        }
        line += &format!(" (weapon heat {}", choice.weapon_heat);
        if surcharge != 0 {
            line += &format!(" +{} damaged radical", surcharge);
        }
        line += &format!(
            " of budget {} = max {} + sink {} - current {} - movement {} - other {}; {})",
            budget, a.max_heat, ctx.dissipation, a.current_heat, a.movement_heat, ctx.other, note_c
        );
        b.log(line);
    }
    // The decisions themselves (stubs warn here): each special weapon's ammunition / rate.
    let mut plans: Vec<(ItemId, ShotPlan)> = Vec::new();
    for &w in weapons {
        if fire_modes::special(b, attacker, w) {
            let p = planner.declare(b, w, ctx.distance, ctx.sel_pre_tn);
            plans.push((w, p));
        }
    }
    electronics::log_controls(b, &a_name, &plans, weapons, attacker);

    report.weapon_heat += choice.weapon_heat + surcharge;
    let t_dir = combat::direction_facing(ctx.a_hex, ctx.t_hex).unwrap();
    // FIRING ORDER (Daniel, 2026-11-14: "fire the weapons that deal the most damage to one location first, then in descending
    // order of cluster size - the AC/20 before the SRM-6 even if the unit lists the SRM-6 first"). The salvo is one
    // simultaneous attack; this is the order its to-hit rolls are made and its hits applied, so a big hit that opens a
    // location comes before the small ones that follow it. It is simply the rule, not a setting. Only the frozen Python's saved
    // fixtures (`Scenario::load`, which marks them _FIRE_ORDER_LISTED) keep the unit's own order, so the answer-key comparisons
    // still mean something.
    let sorted: Vec<ItemId>;
    let weapons: &Vec<ItemId> = if !b.cfg.has("_FIRE_ORDER_LISTED") && weapons.len() > 1 {
        let mut keyed: Vec<(ItemId, i64, i64)> = Vec::with_capacity(weapons.len());
        for &w in weapons {
            let plan = plans.iter().find(|(x, _)| *x == w).map(|(_, p)| p.clone()).unwrap_or_else(ShotPlan::plain);
            let (per_location, cluster) = salvo_key(b, attacker, w, &plan);
            keyed.push((w, per_location, cluster));
        }
        keyed.sort_by(|x, y| y.1.cmp(&x.1).then(y.2.cmp(&x.2))); // stable: equal keys keep the listed order
        sorted = keyed.into_iter().map(|k| k.0).collect();
        if sorted != *weapons {
            let names: Vec<String> = sorted.iter().map(|w| b.units[attacker].items[*w].name.clone()).collect();
            b.log(format!("  [Ranged] {} fires in order: {}.", a_name, crate::damage_resolution::py_str_list(&names)));
        }
        &sorted
    } else {
        weapons
    };
    for &w in weapons {
        let plan = plans.iter().find(|(x, _)| *x == w).map(|(_, p)| p.clone()).unwrap_or_else(ShotPlan::plain);
        let special = fire_modes::special(b, attacker, w);
        let mut ammo_note = String::new();
        if wp::is_mga(b, attacker, w) {
            ammo_note = fire_modes::take_array_rounds(b, attacker, w, plan.shots);
        } else if !weapon_rules::is_streak(b, attacker, w) {
            let kind: Option<String> = if !special || ["8", "12", "16"].contains(&plan.kind.as_str()) || ["saturation", "artillery", "homing"].contains(&plan.kind.as_str()) { None } else { Some(plan.kind.clone()) };
            let mut last = String::new();
            for _ in 0..plan.shots {
                last = ammo::take(b, attacker, w, Some(plan.munition()), kind.as_deref()).0;
            }
            ammo_note = last;
        }
        let range_mod;
        let mut extra;
        if special && plan.hex_attack() {
            range_mod = fire_modes::range_mod(b, attacker, w, &plan, ctx.distance);
            extra = ctx.hex_offset + ctx.adjust.adjust(b, w, None, Some(&plan)) + plan.tn();
        } else if special {
            range_mod = fire_modes::range_mod(b, attacker, w, &plan, ctx.distance);
            let br = fire_modes::bracket(b, attacker, w, &plan, ctx.distance);
            extra = ctx.adjust.adjust(b, w, br, Some(&plan)) + plan.tn() + fire_modes::area_immobile_fix(b, attacker, w, target);
        } else {
            range_mod = weapon_selection::weapon_range_mod(b, attacker, w, ctx.distance);
            let br = weapon_selection::range_bracket(b, attacker, w, ctx.distance);
            extra = ctx.adjust.adjust(b, w, br, None);
        }
        let mut range_mod = range_mod.expect("a selected weapon is in range");
        let mut w_aim = if ctx.aim.is_some() && fire_modes::aimable(b, attacker, w, &plan) { ctx.aim.clone() } else { None };
        if ctx.kick_ids.contains(&w) {
            extra -= ctx.cover;
            w_aim = None;
        }
        let mut tn = ctx.pre_tn + range_mod + extra;
        if plan.kind == "homing" {
            range_mod = 0;
            extra = 0;
            tn = wp::HOMING_TN;
        }
        if ctx.indirect {
            tn += adv::MORTAR_INDIRECT_MODIFIER - adv::MORTAR_DIRECT_MODIFIER;
        }
        let roll = b.roll_2d6();
        let mut hit = roll >= tn;
        let wname = b.units[attacker].items[w].name.clone();
        b.log(format!(
            "    {}{}: needs {} (range mod +{}{}){}, rolled {} -> {}{}",
            wname,
            if plan.shots > 1 { format!(" x{}", plan.shots) } else { String::new() },
            tn,
            range_mod,
            if extra != 0 { format!(", modifiers {:+}", extra) } else { String::new() },
            w_aim.as_ref().map_or(String::new(), |a| format!(" aimed at {}", a)),
            roll,
            if hit { "HIT" } else { "miss" },
            if ammo_note.is_empty() { String::new() } else { format!(" [{}]", ammo_note) }
        ));
        let empty: Vec<String> = Vec::new();
        let wl = ctx.w_locs.get(&w).unwrap_or(&empty).clone();
        arcs::note_mech_turret_fire(&mut b.units[attacker], w, &wl, t_dir - ctx.a_facing);
        let first_loc = if wl.is_empty() { "Center Torso".to_string() } else { wl[0].clone() };
        let turn = b.units[attacker].turn_number;
        if adv::is_hvac(b, attacker, w) {
            adv::hvac_smoke(b, attacker, target, turn);
            if roll == adv::HVAC_MISFEED_ROLL {
                adv::hvac_misfeed(b, attacker, w, &first_loc);
            }
        }
        if adv::is_tsemp(b, attacker, w) && !adv::tsemp_fired(b, attacker, w, roll, turn, &first_loc) {
            hit = false;
        }
        let jam_at = if fire_modes::is_rotary(b, attacker, w) { fire_modes::jam_threshold(&plan) } else { 0 };
        if roll <= jam_at {
            b.units[attacker].items[w].jammed = Some(true);
            b.log(format!("      {} JAMS (roll {} with {} shots, p.183) - the shots still fire.", wname, roll, plan.shots));
        }
        if weapon_rules::is_streak(b, attacker, w) {
            if hit {
                let note = ammo::spend(b, attacker, w, Some(plan.munition()), Some(plan.kind.as_str()));
                if !note.is_empty() {
                    b.log(format!("      [{}]", note));
                }
            } else {
                report.weapon_heat -= b.units[attacker].items[w].heat.unwrap_or(0);
                b.log("      Streak missed - launcher doesn't fire: no heat, no ammo.");
            }
        }
        report.attacks += 1;
        report.attacks_list.push(DeclaredAttack {
            weapon: w,
            tn,
            roll,
            hit,
            side: ctx.side.clone(),
            aimed_at: w_aim,
            cover: if ctx.kick_ids.contains(&w) { Cover::Kick } else if ctx.cover > 0 { Cover::Partial } else { Cover::No },
            ams: None,
            apds: None,
            fire: Some(plan),
            pod_value: ctx.pod_values.get(&w).copied().unwrap_or(0.0),
        });
    }
}

// =============================================================================================================
// The phase
// =============================================================================================================
/// What the Ranged Attack Phase asks of a bot: whom each unit fires at, and the weapon / twist choice itself
/// (`choose` is THE decision of a declaration; Stage 6 reads it from decisions.json, Stages 7-8 compute it).
pub trait RangedBot {
    /// Princess's damage map starts the phase empty.
    fn reset_assigned(&mut self, _b: &mut Battle) {}
    /// The one enemy a unit fires at (None: nothing to shoot), picked as each unit's turn comes.
    fn target_of(&mut self, b: &mut Battle, attacker: UnitId) -> Option<UnitId>;
    fn choose(&mut self, b: &mut Battle, ctx: &DeclCtx, planner: &mut Planner, attacker: UnitId, target: UnitId) -> DeclChoice;
    fn records_declared_damage(&self, _b: &Battle, _attacker: UnitId) -> bool {
        false
    }
    fn assign_damage(&mut self, _b: &mut Battle, _attacker: UnitId, _target: UnitId, _dmg: f64) {}
}

/// Step 2 for one attacker. Rolls to-hit for every selected weapon and fills `report`.
pub fn declare_attacks(b: &mut Battle, attacker: UnitId, target: UnitId, report: &mut SideReport, bot: &mut dyn RangedBot) {
    let Prep::Ready(ctx) = prepare_declaration(b, attacker, target, false) else { return };
    let mut planner = Planner::new(attacker, target, &ctx.adjust, ctx.ams_share, ctx.pod_values.clone(), Some(ctx.hex_offset));
    let choice = bot.choose(b, &ctx, &mut planner, attacker, target);
    let records = bot.records_declared_damage(b, attacker) && !choice.weapons.is_empty();
    if records {
        let mut rec = |b: &mut Battle, d: f64| bot.assign_damage(b, attacker, target, d);
        finish_declaration(b, &ctx, &mut planner, &choice, report, Some(&mut rec));
    } else {
        finish_declaration(b, &ctx, &mut planner, &choice, report, None);
    }
}

/// Whole phase for any number of units: `order` is the units in declaration / resolution order. Returns the reports,
/// parallel to `order`.
pub fn run_ranged_phase(b: &mut Battle, order: &[UnitId], bot: &mut dyn RangedBot) -> Vec<SideReport> {
    let mut reports: Vec<SideReport> = order.iter().map(|_| SideReport::default()).collect();
    let idx = |u: UnitId| order.iter().position(|x| *x == u).unwrap();
    bot.reset_assigned(b);
    for &m in order {
        b.units[m].ams_used = Some(serde_json::json!({}));
    }
    for &m in order {
        snapshot_round_capability(&mut b.units[m]);
        crate::piloting_rolls::snapshot_pre_attack_phase(&mut b.units[m]);
        if !b.is_destroyed(m) {
            gear::declare_raise(b, m, "Ranged");
        }
    }
    let mut pairs: Vec<(UnitId, UnitId)> = Vec::new();
    for &attacker in order {
        let Some(target) = bot.target_of(b, attacker) else { continue };
        pairs.push((attacker, target));
        let mut rep = std::mem::take(&mut reports[idx(attacker)]);
        declare_attacks(b, attacker, target, &mut rep, bot);
        let fired = !rep.attacks_list.is_empty();
        let firing: Vec<ItemId> = rep.attacks_list.iter().map(|a| a.weapon).collect();
        reports[idx(attacker)] = rep;
        crate::clubs::maybe_pick_up(b, attacker, fired);
        let can_act = !(b.is_destroyed(attacker) || b.units[attacker].shutdown || all_crew_unconscious(&b.units[attacker]));
        crate::capacitor::declare(b, attacker, &firing, can_act);
    }
    // AMS (p.206): engaged right after the attack rolls, before any damage lands.
    for &(attacker, target) in &pairs {
        let mut attacks = std::mem::take(&mut reports[idx(attacker)].attacks_list);
        let mut trep = std::mem::take(&mut reports[idx(target)]);
        crate::ams::engage(b, target, attacker, &mut attacks, &mut trep);
        reports[idx(target)] = trep;
        reports[idx(attacker)].attacks_list = attacks;
    }
    for &(attacker, target) in &pairs {
        let hp_before = total_hp(&b.units[target]);
        let mut pool: Option<Pool> = if b.cfg.b("POOL_CLUSTER_DAMAGE") { Some(Pool::default()) } else { None };
        let attacks = reports[idx(attacker)].attacks_list.clone();
        for attack in &attacks {
            let w = attack.weapon;
            let wname = b.units[attacker].items[w].name.clone();
            let tname = b.units[target].side_name.clone().unwrap_or_default();
            // the Lab's tallies: what this shot did to the target (read-only: nothing here touches the dice or the rules)
            let hp_num = |n: Num| match n { Num::I(i) => i as f64, Num::F(f) => f };
            let (hp0, dead0) = (hp_num(total_hp(&b.units[target])), b.is_destroyed(target));
            if attack.hit {
                reports[idx(attacker)].hits += 1;
                if adv::is_tsemp(b, attacker, w) {
                    b.log(format!("    {} hit:", wname));
                    let turn = b.units[attacker].turn_number;
                    adv::tsemp_hit(b, attacker, target, turn);
                    continue;
                }
                resolve_one_attack(b, attacker, target, attack, &mut pool);
                if adv::is_taser(b, attacker, w) {
                    let turn = b.units[attacker].turn_number;
                    adv::taser_hit(b, attacker, target, turn);
                }
            } else if attack.fire.as_ref().is_some_and(|f| f.kind == "homing") {
                b.log(format!("    {} homing missile misses (rolled {}): it strikes {}'s hex for {} area-effect damage (p.190).", wname, attack.roll, tname, wp::HOMING_AE));
                resolve_area(b, target, wp::HOMING_AE, &attack.side, attack.cover);
            } else if attack.fire.as_ref().is_some_and(|f| f.kind == "artillery") || wp::is_art_cannon(b, attacker, w) {
                resolve_area_miss(b, attacker, target, attack);
            }
            b.tally.fit(b.units.len());
            let turn_now = b.units[attacker].turn_number;
            let ws = b.tally.weapons[attacker].entry(wname.clone()).or_insert([0.0; 5]);
            ws[0] += 1.0;
            if attack.hit { ws[1] += 1.0; }
            ws[2] += (hp0 - hp_num(total_hp(&b.units[target]))).max(0.0);
            if ws[4] != turn_now as f64 { ws[3] += 1.0; ws[4] = turn_now as f64; }
            if !dead0 && b.is_destroyed(target) { b.tally.kills[attacker] += 1; }
        }
        if let Some(p) = pool {
            for ((size, dtype, side, cover), parts) in p.entries {
                let total: i64 = parts.iter().map(|(_, d)| *d).sum();
                if parts.len() > 1 {
                    let list: Vec<String> = parts.iter().map(|(n, d)| format!("{} {}", n, d)).collect();
                    b.log(format!("    Cluster damage pooled ({}-point groupings): {} = {}.", size, list.join(" + "), total));
                } else {
                    b.log(format!("    {}: {} damage in {}-point groupings.", parts[0].0, total, size));
                }
                apply_groups(b, target, total, size, dtype, &side, cover, "");
            }
        }
        let dealt = hp_before - total_hp(&b.units[target]);
        reports[idx(attacker)].damage_dealt += match dealt {
            Num::I(i) => i as f64,
            Num::F(f) => f,
        };
    }
    for &m in order {
        b.units[m].ams_used = Some(serde_json::Value::Null);
        gear::lower(&mut b.units[m]);
        electronics::activate_pods(&mut b.units[m]);
        fire_modes::resolve_unjams(b, m);
        crate::capacitor::end_phase(b, m);
    }
    for &m in order {
        b.with_piloting(m, |b| crate::piloting_rolls::resolve_attack_phase_psr(b, m, &[]));
        crate::piloting_rolls::resolve_consciousness_checks(b, m, "Attack Phase");
    }
    reports
}
