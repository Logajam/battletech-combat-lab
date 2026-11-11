// Translated from INTEGRATION__physical.py (session 22). Part 1: the location tables; the Physical Attack Phase follows.
use crate::battle::{Battle, UnitId};
use crate::hit_location::resolve_hit_location;
use crate::mech_state::has_torso_cockpit;


/// (1-3, 4-6), p.81
pub fn kick_table(side: &str) -> (&'static str, &'static str) {
    match side {
        "left" => ("Left Leg", "Left Leg"),
        "right" => ("Right Leg", "Right Leg"),
        "front" | "rear" => ("Right Leg", "Left Leg"),
        other => panic!("KeyError: {}", other),
    }
}

pub fn punch_table(side: &str) -> [&'static str; 6] {
    match side {
        "left" => ["Left Torso", "Left Torso", "Center Torso", "Left Arm", "Left Arm", "Head"],
        "right" => ["Right Torso", "Right Torso", "Center Torso", "Right Arm", "Right Arm", "Head"],
        "front" | "rear" => ["Right Arm", "Right Torso", "Center Torso", "Left Torso", "Left Arm", "Head"],
        other => panic!("KeyError: {}", other),
    }
}

/// The location a physical attack's hit strikes: the standard table (2D6), or the kick / punch table (1D6).
pub fn location(b: &mut Battle, table: &str, side: &str, target: UnitId) -> String {
    if table == "standard" {
        let roll = b.roll_2d6();
        return resolve_hit_location(b, target, roll, side);
    }
    let die = b.pick_number(6);
    let mut loc: String;
    if table == "kick" {
        let k = kick_table(side);
        loc = (if die <= 3 { k.0 } else { k.1 }).to_string();
    } else {
        loc = punch_table(side)[(die - 1) as usize].to_string();
        while loc == "Head" && b.units[target].locations["Head"].destroyed && has_torso_cockpit(&b.units[target]) {
            let die = b.pick_number(6);
            loc = punch_table(side)[(die - 1) as usize].to_string();
        }
    }
    let t = &b.units[target];
    if t.mech_type == "quad" || t.mech_type == "quadvee" {
        loc = match loc.as_str() {
            "Left Arm" => "Front Left Leg".to_string(),
            "Right Arm" => "Front Right Leg".to_string(),
            "Left Leg" => if side == "rear" { "Rear Left Leg" } else { "Front Left Leg" }.to_string(),
            "Right Leg" => if side == "rear" { "Rear Right Leg" } else { "Front Right Leg" }.to_string(),
            _ => loc,
        };
    }
    loc
}

// =============================================================================================================
// Options (what a mech could do), Reach, base TN
// =============================================================================================================
use crate::fasthash::HashSet;

use crate::fasthash::IndexMap;

use crate::arcs;
use crate::attack_resolution::weapon_locations;
use crate::equipment::{ItemId, Slot};
use crate::mech_state::*;
use crate::physical_gear as gear;
use crate::pyfmt::Num;

pub const ARMS: [&str; 2] = ["Left Arm", "Right Arm"];
pub const PUNCH_MOD: i64 = -1;
pub const KICK_MOD: i64 = -1;
pub const AES_PHYSICAL_MOD: i64 = -1;
pub const FLAIL_FUMBLE_ROLL: i64 = 2;
pub const FLAIL_FUMBLE_DAMAGE: i64 = 5;
pub const WHIP_TRIP_PSR: i64 = 3;
pub const WHIP_TSM_BONUS: i64 = -2;
pub const PUSH_PSR_MODIFIER: i64 = 0;
pub const PUSH_MOD: i64 = -1;
pub const PUSH_SHOULDER_MOD: i64 = 2;
pub const CLUB_MOD: i64 = -1;
pub const CLUB_CLAW_MOD: i64 = 2;
pub const CLUB_ACTUATOR_MOD: i64 = 2;

/// One physical attack option (a dict in the Python).
#[derive(Clone, Debug, PartialEq)]
pub struct PhysOption {
    pub name: String,
    pub mod_: i64,
    pub damage: Num,
    pub table: String,
    pub limb: Vec<String>,
    pub kick: bool,
    pub club: bool,
    pub weapon: bool,
    pub lance: bool,
    pub heat: i64,
    pub blade: Option<String>,
    pub flail: bool,
    pub whip: bool,
    pub push: bool,
    pub fumble: bool,
    pub tn: Option<i64>,
}

impl PhysOption {
    fn new(name: String, mod_: i64, damage: i64, table: &str, limb: Vec<String>) -> PhysOption {
        PhysOption { name, mod_, damage: Num::I(damage), table: table.to_string(), limb, kick: false, club: false, weapon: false, lance: false, heat: 0, blade: None, flail: false, whip: false, push: false, fumble: false, tn: None }
    }
}

fn norm(name: &str) -> String {
    name.replace(' ', "").replace('-', "").to_uppercase()
}

/// Physical Weapon Attacks Table, p.81: (TN modifier, tons per point or None = fixed, +damage, table)
fn physical_weapon_spec(n: &str) -> Option<(i64, Option<i64>, i64, &'static str)> {
    const T: [(&str, (i64, Option<i64>, i64, &str)); 9] = [
        ("CLAW", (0, Some(7), 0, "punch")),
        ("HATCHET", (-1, Some(5), 0, "standard")),
        ("LANCE", (1, Some(5), 0, "standard")),
        ("MACE", (1, Some(4), 0, "standard")),
        ("RETRACTABLEBLADE", (-2, Some(10), 0, "standard")),
        ("SWORD", (-2, Some(10), 1, "standard")),
        ("VIBROBLADE", (-2, Some(10), 1, "standard")),
        ("FLAIL", (0, None, 9, "standard")),
        ("CHAINWHIP", (-2, None, 3, "standard")),
    ];
    T.iter().find(|(frag, _)| n.contains(frag)).map(|(_, s)| *s)
}

fn weapon_kind(m: &Mech, slot: &Slot) -> Option<(i64, Option<i64>, i64, &'static str)> {
    match slot {
        Slot::Item(i) => physical_weapon_spec(&norm(&m.items[*i].name)),
        _ => None,
    }
}

fn quad_location(loc: &str, side: &str) -> String {
    match loc {
        "Left Arm" => "Front Left Leg".into(),
        "Right Arm" => "Front Right Leg".into(),
        "Left Leg" | "Right Leg" => format!("{}{}", if side == "rear" { "Rear " } else { "Front " }, loc),
        other => other.to_string(),
    }
}

/// [(probability, location)] of the Punch (1D6) or Kick (1D6: 1-3 / 4-6) Location Table, None for the standard table.
pub fn table_rolls(table: &str, side: &str, target: &Mech) -> Option<Vec<(f64, String)>> {
    let mut rolls: Vec<(f64, String)> = match table {
        "punch" => punch_table(side).iter().map(|l| (1.0 / 6.0, l.to_string())).collect(),
        "kick" => {
            let k = kick_table(side);
            vec![(0.5, k.0.to_string()), (0.5, k.1.to_string())]
        }
        _ => return None,
    };
    if target.mech_type == "quad" || target.mech_type == "quadvee" {
        rolls = rolls.into_iter().map(|(p, l)| (p, quad_location(&l, side))).collect();
    }
    Some(rolls)
}

fn has_part(m: &Mech, loc: &str, part: &str) -> bool {
    m.crits.get(loc).into_iter().flatten().any(|s| s.is_name(part)) || m.destroyed_slot_info.iter().any(|((l, _), i)| l == loc && i.name == part)
}

fn lost(m: &Mech, loc: &str, part: &str) -> bool {
    m.destroyed_slot_info.iter().any(|((l, _), i)| l == loc && i.name == part)
}

fn arm_aes(m: &Mech, arm: &str) -> i64 {
    if arm_aes_working(m, arm) { AES_PHYSICAL_MOD } else { 0 }
}
fn both_arms_aes(m: &Mech) -> i64 {
    if ARMS.iter().all(|a| arm_aes_working(m, a)) { AES_PHYSICAL_MOD } else { 0 }
}
fn leg_aes(m: &Mech) -> i64 {
    if leg_aes_working(m) { AES_PHYSICAL_MOD } else { 0 }
}

fn limb_fired(m: &Mech, loc: &str, fired: &HashSet<ItemId>) -> bool {
    let locs = weapon_locations(m);
    fired.iter().any(|w| locs.get(w).is_some_and(|l| l.iter().any(|x| x == loc)))
}

/// Where an adjacent target sits for this attacker's physical attacks.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct Reach {
    pub left_arm_ok: bool,
    pub right_arm_ok: bool,
    pub kick_ok: bool,
    pub club_ok: bool,
    pub mule_ok: bool,
}

impl Reach {
    pub fn new(mech: &Mech, facing: i64, action: &ArcAction, pair: &[i64; 6]) -> Reach {
        let torso_arc = pair[(facing + action.twist).rem_euclid(6) as usize];
        let tripod = mech.mech_type == "tripod";
        let flipped = action.flip;
        let arm_ok = |arm: &str| -> bool {
            if flipped {
                false
            } else if tripod {
                torso_arc == arcs::FORWARD
            } else {
                torso_arc == arcs::FORWARD || torso_arc == if arm == "Left Arm" { arcs::LEFT } else { arcs::RIGHT }
            }
        };
        Reach {
            left_arm_ok: arm_ok("Left Arm"),
            right_arm_ok: arm_ok("Right Arm"),
            kick_ok: (if tripod { torso_arc } else { pair[facing as usize] }) == arcs::FORWARD,
            club_ok: !flipped && torso_arc == arcs::FORWARD,
            mule_ok: (mech.mech_type == "quad" || mech.mech_type == "quadvee") && pair[facing as usize] == arcs::REAR,
        }
    }
    pub fn arm_ok(&self, arm: &str) -> bool {
        if arm == "Left Arm" { self.left_arm_ok } else { self.right_arm_ok }
    }
}

fn strength(m: &Mech, per_tons: i64, plus: i64) -> i64 {
    let dmg = -((-m.mass.unwrap_or(0)).div_euclid(per_tons)) + plus;
    dmg * if m.tsm_active { 2 } else { 1 }
}

fn punch_options(m: &Mech, rel: &Reach, fired: &HashSet<ItemId>, table: Option<&str>) -> Vec<PhysOption> {
    let mut out = Vec::new();
    for arm in ARMS {
        if !m.locations.contains_key(arm) || m.locations[arm].destroyed || !rel.arm_ok(arm) {
            continue;
        }
        if lost(m, arm, "Shoulder") || limb_fired(m, arm, fired) {
            continue;
        }
        let claw = m.crits[arm].iter().any(|s| weapon_kind(m, s).is_some_and(|k| k.3 == "punch"));
        let bash = gear::shield_bash(m, arm);
        let (mut md, dmg) = if claw { (0, strength(m, 7, bash)) } else { (PUNCH_MOD, strength(m, 10, bash)) };
        let mut halves = 0;
        if !claw && (!has_part(m, arm, "Hand Actuator") || lost(m, arm, "Hand Actuator")) {
            md += 1;
        }
        for part in ["Lower Arm Actuator", "Upper Arm Actuator"] {
            if (part == "Lower Arm Actuator" && !has_part(m, arm, part)) || lost(m, arm, part) {
                md += 2;
                halves += 1;
            }
        }
        md += arm_aes(m, arm);
        out.push(PhysOption::new(format!("{} ({})", if claw { "claw" } else { "punch" }, arm), md, dmg.div_euclid(1 << halves), table.unwrap_or("punch"), vec![arm.to_string()]));
    }
    out
}

const QUAD_FRONT_LEGS: [&str; 2] = ["Front Left Leg", "Front Right Leg"];
const QUAD_REAR_LEGS: [&str; 2] = ["Rear Left Leg", "Rear Right Leg"];

fn quad_kick_options(m: &Mech, rel: &Reach, fired: &HashSet<ItemId>, table: Option<&str>) -> Vec<PhysOption> {
    let (pair, what): ([&str; 2], &str) = if rel.kick_ok {
        (QUAD_FRONT_LEGS, "kick")
    } else if rel.mule_ok && !QUAD_FRONT_LEGS.iter().any(|l| m.locations[*l].destroyed) {
        (QUAD_REAR_LEGS, "mule kick")
    } else {
        return vec![];
    };
    if pair.iter().any(|l| m.locations[*l].destroyed || m.destroyed_hip_locations.contains(*l)) {
        return vec![];
    }
    let (mut md, mut halves) = (KICK_MOD + leg_aes(m), 0);
    for leg in pair {
        if lost(m, leg, "Foot Actuator") {
            md += 1;
        }
        for part in ["Lower Leg Actuator", "Upper Leg Actuator"] {
            if lost(m, leg, part) {
                md += 2;
                halves += 1;
            }
        }
    }
    let mut out = Vec::new();
    for leg in pair {
        if limb_fired(m, leg, fired) {
            continue;
        }
        let mut dmg = strength(m, 5, 0).div_euclid(1 << halves);
        if gear::talon_legs(m).iter().any(|l| l == leg) {
            dmg = gear::with_talons(dmg);
        }
        let mut o = PhysOption::new(format!("{} ({})", what, leg), md, dmg, table.unwrap_or("kick"), vec![leg.to_string()]);
        o.kick = true;
        out.push(o);
    }
    out
}

fn kick_options(m: &Mech, rel: &Reach, fired: &HashSet<ItemId>, table: Option<&str>) -> Vec<PhysOption> {
    if matches!(&m.stuck, Some(Some(_))) {
        return vec![];
    }
    if m.mech_type == "quad" || m.mech_type == "quadvee" {
        return quad_kick_options(m, rel, fired, table);
    }
    if !rel.kick_ok || !m.destroyed_hip_locations.is_empty() {
        return vec![];
    }
    let legs: Vec<&String> = m.leg_locations.iter().filter(|l| !m.locations[l.as_str()].destroyed).collect();
    if legs.len() < m.leg_locations.len() {
        return vec![];
    }
    let (mut md, mut halves) = (KICK_MOD + leg_aes(m), 0);
    for leg in &m.leg_locations {
        if lost(m, leg, "Foot Actuator") {
            md += 1;
        }
        for part in ["Lower Leg Actuator", "Upper Leg Actuator"] {
            if lost(m, leg, part) {
                md += 2;
                halves += 1;
            }
        }
    }
    let mut out = Vec::new();
    for leg in legs {
        if limb_fired(m, leg, fired) {
            continue;
        }
        let mut dmg = strength(m, 5, 0).div_euclid(1 << halves);
        if gear::talon_legs(m).iter().any(|l| l == leg) {
            dmg = gear::with_talons(dmg);
        }
        let mut o = PhysOption::new(format!("kick ({})", leg), md, dmg, table.unwrap_or("kick"), vec![leg.clone()]);
        o.kick = true;
        out.push(o);
    }
    out
}

fn weapon_options(b: &mut Battle, u: UnitId, rel: &Reach, fired: &HashSet<ItemId>, table: Option<&str>) -> Vec<PhysOption> {
    let mut out = Vec::new();
    for arm in ARMS {
        let m = &b.units[u];
        if !m.locations.contains_key(arm) || m.locations[arm].destroyed || !rel.arm_ok(arm) {
            continue;
        }
        if lost(m, arm, "Shoulder") || limb_fired(m, arm, fired) {
            continue;
        }
        let mut seen: Vec<ItemId> = Vec::new();
        for s in &m.crits[arm] {
            if let Slot::Item(i) = s {
                if weapon_kind(m, s).is_some() && !seen.contains(i) {
                    seen.push(*i);
                }
            }
        }
        for slot in seen {
            let (tn_mod, per, plus, wtable) = physical_weapon_spec(&norm(&b.units[u].items[slot].name)).unwrap();
            let m = &b.units[u];
            let sname = m.items[slot].name.clone();
            let n = norm(&sname);
            if wtable == "punch" {
                continue;
            }
            if lost(m, arm, "Hand Actuator") && !n.contains("RETRACTABLEBLADE") {
                continue;
            }
            let mut md = tn_mod;
            for part in ["Lower Arm Actuator", "Upper Arm Actuator"] {
                if (part == "Lower Arm Actuator" && !has_part(m, arm, part)) || lost(m, arm, part) {
                    md += 2;
                }
            }
            md += arm_aes(m, arm);
            let (mut damage, mut heat, mut active) = (match per { None => plus, Some(p) => strength(m, p, plus) }, 0, false);
            if n.contains("VIBROBLADE") {
                let ded = -((-m.mass.unwrap_or(0)).div_euclid(per.unwrap())) + plus;
                let tsm = m.tsm_active;
                let r = gear::vibro_attack(b, u, slot, ded, tsm);
                damage = r.0;
                heat = r.1;
                active = r.2;
            }
            let mut o = PhysOption::new(format!("{} ({}){}", sname, arm, if active { " activated" } else { "" }), md, damage, table.unwrap_or("standard"), vec![arm.to_string()]);
            o.weapon = true;
            o.lance = n.contains("LANCE");
            o.heat = heat;
            o.blade = if active { Some(sname.clone()) } else { None };
            o.flail = n.contains("FLAIL");
            o.whip = n.contains("CHAINWHIP");
            out.push(o);
        }
    }
    out
}

fn club_options(m: &Mech, rel: &Reach, fired: &HashSet<ItemId>, table: &str) -> Vec<PhysOption> {
    if !matches!(&m.club, Some(Some(_))) || !rel.club_ok || !crate::clubs::can_wield(m) {
        return vec![];
    }
    if ARMS.iter().any(|a| limb_fired(m, a, fired)) {
        return vec![];
    }
    let mut md = CLUB_MOD + CLUB_ACTUATOR_MOD * ARMS.iter().flat_map(|a| ["Upper Arm Actuator", "Lower Arm Actuator"].into_iter().map(move |p| (*a, p))).filter(|(a, p)| lost(m, a, p)).count() as i64;
    if ARMS.iter().any(|a| m.crits.get(*a).into_iter().flatten().any(|s| matches!(s, Slot::Item(i) if norm(&m.items[*i].name).contains("CLAW")))) {
        md += CLUB_CLAW_MOD;
    }
    md += both_arms_aes(m);
    let club = if let Some(Some(c)) = &m.club { c.clone() } else { unreachable!() };
    let mut o = PhysOption::new(format!("{} club", club), md, strength(m, 5, 0), table, ARMS.iter().map(|s| s.to_string()).collect());
    o.club = true;
    vec![o]
}

/// Can a physical attack span this level difference (target minus attacker)?
pub fn reachable(diff: i64, target_superheavy: bool) -> bool {
    if target_superheavy { (-2..=1).contains(&diff) } else { diff.abs() <= 1 }
}

type Opts = IndexMap<&'static str, Vec<PhysOption>>;

fn keep(opts: Opts) -> Opts {
    opts.into_iter().filter(|(_, v)| !v.is_empty()).collect()
}

fn superheavy_options(b: &mut Battle, u: UnitId, rel: &Reach, diff: i64, target_prone: bool, fired: &HashSet<ItemId>) -> Opts {
    let mut opts: Opts = IndexMap::default();
    let m = b.units[u].clone();
    if !target_prone {
        if diff == 1 {
            opts.insert("punch", punch_options(&m, rel, fired, Some("kick")));
            opts.insert("weapon", weapon_options(b, u, rel, fired, Some("kick")));
            opts.insert("club", club_options(&m, rel, fired, "kick"));
        } else if diff == -1 {
            opts.insert("punch", punch_options(&m, rel, fired, None));
            opts.insert("kick", kick_options(&m, rel, fired, None));
            opts.insert("weapon", weapon_options(b, u, rel, fired, None));
            opts.insert("club", club_options(&m, rel, fired, "standard"));
        } else if diff == -2 {
            opts.insert("kick", kick_options(&m, rel, fired, Some("punch")));
            opts.insert("weapon", weapon_options(b, u, rel, fired, Some("punch")));
            opts.insert("club", club_options(&m, rel, fired, "punch"));
        }
    } else if diff == 1 {
        opts.insert("punch", punch_options(&m, rel, fired, None));
        opts.insert("weapon", weapon_options(b, u, rel, fired, None));
        opts.insert("club", club_options(&m, rel, fired, "standard"));
    } else if diff == -1 {
        opts.insert("punch", punch_options(&m, rel, fired, None));
        opts.insert("kick", kick_options(&m, rel, fired, Some("standard")));
        opts.insert("weapon", weapon_options(b, u, rel, fired, None));
        opts.insert("club", club_options(&m, rel, fired, "standard"));
    }
    keep(opts)
}

pub fn options(b: &mut Battle, u: UnitId, rel: &Reach, diff: i64, target_prone: bool, fired: &HashSet<ItemId>, target_superheavy: bool) -> Opts {
    if target_superheavy && diff != 0 {
        return superheavy_options(b, u, rel, diff, target_prone, fired);
    }
    let mut opts: Opts = IndexMap::default();
    let m = b.units[u].clone();
    if target_prone {
        if diff == 0 {
            opts.insert("kick", kick_options(&m, rel, fired, Some("standard")));
            opts.insert("weapon", weapon_options(b, u, rel, fired, None));
            opts.insert("club", club_options(&m, rel, fired, "standard"));
        } else if diff == 1 {
            opts.insert("punch", punch_options(&m, rel, fired, None));
            opts.insert("weapon", weapon_options(b, u, rel, fired, None));
            opts.insert("club", club_options(&m, rel, fired, "standard"));
        }
    } else if diff == 0 {
        opts.insert("punch", punch_options(&m, rel, fired, None));
        opts.insert("kick", kick_options(&m, rel, fired, None));
        opts.insert("weapon", weapon_options(b, u, rel, fired, None));
        opts.insert("club", club_options(&m, rel, fired, "standard"));
    } else if diff == 1 {
        opts.insert("punch", punch_options(&m, rel, fired, Some("kick")));
        opts.insert("weapon", weapon_options(b, u, rel, fired, Some("kick")));
        opts.insert("club", club_options(&m, rel, fired, "kick"));
    } else {
        opts.insert("kick", kick_options(&m, rel, fired, Some("punch")));
        opts.insert("weapon", weapon_options(b, u, rel, fired, Some("punch")));
        opts.insert("club", club_options(&m, rel, fired, "punch"));
    }
    keep(opts)
}

/// opts without the attack kinds the water rules out; allowed None = no restriction.
pub fn water_filter(opts: Opts, allowed: Option<&[&str]>) -> Opts {
    match allowed {
        None => opts,
        Some(a) => opts.into_iter().filter(|(k, _)| a.contains(k)).collect(),
    }
}

/// attack_options for an attacker standing on a_hex facing a_facing against a target on t_hex.
#[allow(clippy::too_many_arguments)]
pub fn options_at(b: &mut Battle, u: UnitId, a_hex: (i64, i64), a_facing: i64, a_level: i64, t_hex: (i64, i64), t_level: i64, target_prone: bool, fired: &HashSet<ItemId>, action: &ArcAction, target_superheavy: bool) -> Opts {
    if crate::los::hex_distance(a_hex, t_hex) != 1 {
        return IndexMap::default();
    }
    let diff = t_level - a_level;
    if !reachable(diff, target_superheavy) {
        return IndexMap::default();
    }
    let pair = arcs::arcs_between(a_hex, t_hex);
    let rel = Reach::new(&b.units[u], a_facing, action, &pair);
    options(b, u, &rel, diff, target_prone, fired, target_superheavy)
}

/// p.76: Piloting + AMM + TMM + terrain + prone / immobile target; torso-cockpit sensor hits, a tripod's pilot.
pub fn base_tn(attacker: &Mech, amm: i64, target_tmm: i64, los_modifier: i64, target_prone_modifier: i64) -> i64 {
    attacker.piloting + amm + target_tmm + los_modifier + target_prone_modifier + crate::advanced_weapons::own_attack_modifier(attacker, true) + torso_cockpit_sensor_penalty(attacker) + physical_attacker_modifier(attacker)
}

/// Weapons that may not fire if `limbs` make physical attacks this turn.
pub fn limb_weapon_ids(mech: &Mech, limbs: &[String]) -> HashSet<ItemId> {
    weapon_locations(mech).into_iter().filter(|(_, where_)| where_.iter().any(|l| limbs.contains(l))).map(|(w, _)| w).collect()
}

/// The push the attacker could make (p.83), as an option, or None. `value` is what the displacement does.
#[allow(clippy::too_many_arguments)]
pub fn push_option(b: &mut Battle, attacker: UnitId, a_xy: (i64, i64), a_facing: i64, a_level: i64, target: UnitId, t_label: &str, t_level: i64, fired: &HashSet<ItemId>, value: &mut dyn FnMut(&mut Battle, &str, i64) -> f64) -> Option<PhysOption> {
    let t = &b.units[target];
    if t.prone || t_level != a_level || t.charging.is_some() || t.dfa.is_some() {
        return None;
    }
    let t_xy = crate::hex_geometry::parse_hex_label(t_label).unwrap();
    if crate::los::hex_distance(a_xy, t_xy) != 1 || crate::combat::direction_facing(a_xy, t_xy).unwrap() != a_facing {
        return None;
    }
    let a = &b.units[attacker];
    if ARMS.iter().any(|arm| !a.locations.contains_key(*arm) || a.locations[*arm].destroyed) {
        return None;
    }
    if !fired.is_empty() && ARMS.iter().any(|arm| limb_fired(a, arm, fired)) {
        return None;
    }
    let v = value(b, t_label, a_facing);
    if v <= 0.0 {
        return None;
    }
    let a = &b.units[attacker];
    let md = PUSH_MOD + PUSH_SHOULDER_MOD * ARMS.iter().filter(|arm| lost(a, arm, "Shoulder")).count() as i64 + both_arms_aes(a);
    let mut o = PhysOption::new("push".into(), md, 0, "displacement", ARMS.iter().map(|s| s.to_string()).collect());
    o.damage = Num::F(v);
    o.push = true;
    Some(o)
}

// =============================================================================================================
// The Physical Attack Phase
// =============================================================================================================
use crate::attack_resolution::SideReport;
use crate::charge::{self, Triggers};
use crate::damage_resolution::apply_damage;
use crate::hex_geometry;
use crate::movement_attacks as ma;

/// What the Physical Attack Phase asks of a bot (stages 7-8; Stage 6 reads decisions.json).
pub trait PhysicalBot {
    /// The one enemy a unit attacks (None: nobody to hit).
    fn target_of(&mut self, b: &mut Battle, attacker: UnitId) -> Option<UnitId>;
    /// bots.choose_physical: (base TN, picked options, arc action) or None.
    fn choose_physical(&mut self, b: &mut Battle, attacker: UnitId, target: UnitId) -> Option<(i64, Vec<PhysOption>, crate::mech_state::ArcAction)>;
}

fn name_of(b: &Battle, u: UnitId) -> String {
    b.units[u].side_name.clone().unwrap_or_default()
}

fn add_trigger(t: &mut Triggers, who: &str, why: &str, m: i64) {
    t.entry(who.to_string()).or_default().push((why.to_string(), m));
}

/// Successful pushes (p.83): the target moves one hex straight on, the pusher into its hex, then the target makes a PSR.
fn resolve_pushes(b: &mut Battle, pushes: &[(UnitId, UnitId)], triggers: &mut Triggers) {
    if pushes.len() == 2 {
        b.log("    Both pushes succeed - neither mech moves; both must make a PSR (p.83).");
        for (_, target) in pushes {
            let n = name_of(b, *target);
            add_trigger(triggers, &n, "pushed", PUSH_PSR_MODIFIER);
        }
        return;
    }
    for &(attacker, target) in pushes {
        let (an, tn) = (name_of(b, attacker), name_of(b, target));
        let direction = hex_geometry::compass_to_facing(&b.units[attacker].facing).unwrap();
        let here = b.units[target].hex.clone().unwrap();
        let (kind, label, drop) = ma::displacement(b, &here, direction);
        if kind == "off" {
            b.units[target].destroyed = true;
            b.units[target].cause_of_death = Some("Pushed off the battlefield".into());
            b.log(format!("    {} is pushed off the battlefield - destroyed (p.83).", tn));
            b.units[attacker].hex = b.units[target].hex.clone();
            continue;
        }
        if kind == "blocked" {
            b.log("    The push into a hex 3+ levels up is prohibited - nobody moves (p.83).");
            add_trigger(triggers, &tn, "pushed", PUSH_PSR_MODIFIER);
            continue;
        }
        let mut label = label.unwrap();
        let old = here;
        let mut fell_here = false;
        if crate::domino::occupant(b, &label, &[attacker, target]).is_some() {
            fell_here = crate::domino::displace_into_occupied(b, target, &label, direction, drop, "pushed");
            label = b.units[target].hex.clone().unwrap();
        } else {
            b.units[target].hex = Some(label.clone());
        }
        b.log(format!("    {} is pushed {} -> {}; {} follows into {}.", tn, old, label, an, old));
        let attacker_fell = crate::domino::advance_into(b, attacker, &old, direction, "following its push");
        if !fell_here {
            crate::hazards::enter_hex(b, target, &label, false, Some(&format!("pushed into {}", label)), true);
        }
        if !attacker_fell {
            let ah = b.units[attacker].hex.clone().unwrap();
            crate::hazards::enter_hex(b, attacker, &ah, false, Some(&format!("followed into {}", ah)), true);
        }
        if fell_here {
        } else if drop >= 2 {
            b.log(format!("    {} is pushed {} levels down - automatic fall (p.83).", tn, drop));
            crate::piloting_rolls::resolve_fall(b, target, "pushed down", drop, None);
        } else {
            add_trigger(triggers, &tn, "pushed", PUSH_PSR_MODIFIER);
        }
    }
}

/// A chain whip's bonus trip attack after a leg hit (TO:AUE p.101).
fn whip_trip(b: &mut Battle, attacker: UnitId, target: UnitId, o: &PhysOption, triggers: &mut Triggers) {
    let tn = o.tn.unwrap() + if b.units[attacker].tsm_active && !b.units[target].tsm_active { WHIP_TSM_BONUS } else { 0 };
    let roll = b.roll_2d6();
    let tname = name_of(b, target);
    let text = if roll >= tn { format!("the leg is caught: {} makes a PSR at +3", tname) } else { "miss".to_string() };
    b.log(format!("    Chain whip bonus trip attack: needs {}, rolled {} -> {} (TO:AUE p.101).", tn, roll, text));
    if roll >= tn {
        add_trigger(triggers, &tname, "tripped by a chain whip", WHIP_TRIP_PSR);
    }
}

/// Every unit declares and rolls, then the damage lands, then charges' and DFAs' damage and displacement, then PSRs and
/// consciousness checks (p.83). `reports` parallel to `order`.
pub fn run_physical_units(b: &mut Battle, order: &[UnitId], reports: &mut [SideReport], bot: &mut dyn PhysicalBot) {
    let idx = |u: UnitId| order.iter().position(|x| *x == u);
    for &m in order {
        let fired: crate::fasthash::IndexSet<ItemId> = match idx(m) {
            Some(i) => reports[i].attacks_list.iter().map(|a| a.weapon).collect(),
            None => Default::default(),
        };
        b.units[m].weapons_fired_this_turn = Some(fired);
        crate::piloting_rolls::snapshot_pre_attack_phase(&mut b.units[m]);
        if !b.is_destroyed(m) {
            gear::declare_raise(b, m, "Physical");
        }
    }
    let mut declared: Vec<(UnitId, UnitId, PhysOption, bool, String)> = Vec::new();
    let mut charges: Vec<(UnitId, UnitId)> = Vec::new();
    let mut dfas: Vec<(UnitId, UnitId, bool)> = Vec::new();
    for &attacker in order {
        let Some(target) = bot.target_of(b, attacker) else { continue };
        if b.units[attacker].charging.is_some() {
            match charge::declare(b, attacker, target) {
                charge::Declared::Cancelled => {}
                charge::Declared::Miss => continue,
                charge::Declared::Going(_, hit) => {
                    if hit {
                        charges.push((attacker, target));
                    }
                    continue;
                }
            }
        }
        if b.units[attacker].dfa.is_some() {
            match crate::dfa::declare(b, attacker, target) {
                crate::dfa::Declared::Cancelled => {}
                crate::dfa::Declared::Going(_, hit) => {
                    dfas.push((attacker, target, hit));
                    continue;
                }
            }
        }
        if b.units[target].dfa.is_some() && !b.is_destroyed(target) {
            continue;
        }
        let Some((base, picks, action)) = bot.choose_physical(b, attacker, target) else { continue };
        if Some(&action) != Some(&arcs::current_action(&b.units[attacker])) {
            arcs::declare(&mut b.units[attacker], action.clone());
            let line = format!("  [Physical] {} {} to reach {}.", name_of(b, attacker), arcs::describe(&action), name_of(b, target));
            b.log(line);
        }
        let a_hex = hex_geometry::parse_hex_label(b.units[attacker].hex.as_deref().unwrap()).unwrap();
        let t_hex = hex_geometry::parse_hex_label(b.units[target].hex.as_deref().unwrap()).unwrap();
        let tf = hex_geometry::compass_to_facing(&b.units[target].facing).unwrap();
        let side = crate::attack_resolution::attack_side(b, a_hex, t_hex, tf, crate::attack_resolution::standing(), crate::attack_resolution::standing()).to_string();
        for mut o in picks {
            let (an, tname) = (name_of(b, attacker), name_of(b, target));
            if o.heat != 0 {
                let blade = o.blade.clone().unwrap();
                crate::stubs::stub_vibroblade(b, &an, &blade, true);
                if let Some(i) = idx(attacker) {
                    reports[i].weapon_heat += o.heat;
                }
                b.log(format!("  [Physical] {} activates its {}: +{} heat (p.196).", an, blade, o.heat));
            }
            let tn = base + o.mod_;
            let roll = b.roll_2d6();
            let mut hit = roll >= tn;
            if o.flail && roll == FLAIL_FUMBLE_ROLL {
                hit = false;
                o.fumble = true;
            }
            let piloting = b.units[attacker].piloting;
            b.log(format!(
                "  [Physical] {} -> {}: {} needs {} (piloting {} + base {} + attack {:+}), rolled {} -> {} ({} dmg, {} side){}",
                an,
                tname,
                o.name,
                tn,
                piloting,
                base - piloting,
                o.mod_,
                roll,
                if hit { "HIT" } else { "miss" },
                o.damage.py_str(),
                side,
                if o.fumble { " - the flail swings back into its wielder (TO:AUE p.101)" } else { "" }
            ));
            o.tn = Some(tn);
            declared.push((attacker, target, o, hit, side.clone()));
        }
    }
    let mut triggers: Triggers = crate::fasthash::IndexMap::default();
    let mut pushes: Vec<(UnitId, UnitId)> = Vec::new();
    for (attacker, target, o, hit, side) in declared {
        if o.push {
            if hit {
                pushes.push((attacker, target));
            }
            continue;
        }
        let (an, tname) = (name_of(b, attacker), name_of(b, target));
        if hit {
            let loc = location(b, &o.table, &side, target);
            let dmg0 = match o.damage {
                Num::I(i) => i,
                Num::F(f) => f as i64,
            };
            let dmg = crate::water::physical_damage(b, target, &loc, dmg0);
            b.log(format!("    {} hits {}'s {} for {}{}.", o.name, tname, loc, dmg, if dmg != dmg0 { " (halved: under water, p.77)" } else { "" }));
            let (dmg, spiked) = gear::spike_reduce(b, target, &loc, dmg, &o.name);
            let dmg = gear::shield_absorb(b, target, &loc, dmg, &side);
            if loc == "Head" && head_hit_hurts_pilot(&b.units[target]) {
                pilot_hit(&mut b.units[target], 1, true);
            }
            let before = gear::snapshot(&b.units[target], &loc);
            apply_damage(b, target, &loc, Num::I(dmg), if side == "rear" { "rear_armor" } else { "armor" }, DamageType::Physical);
            if o.lance && gear::armor_only(&b.units[target], &loc, before) {
                gear::lance_ap_check(b, target, &loc, gear::LANCE_AP_TN, &o.name);
            }
            if spiked && !(o.club || o.weapon) {
                let l: Vec<&str> = o.limb.iter().map(|s| s.as_str()).collect();
                gear::spike_retaliation(b, attacker, &l);
            }
            if o.kick {
                add_trigger(&mut triggers, &tname, "kicked", 0);
            }
            if o.club {
                add_trigger(&mut triggers, &tname, "hit by a club", 0);
                crate::clubs::used(b, attacker);
            }
            if o.whip && b.units[target].leg_locations.contains(&loc) && !b.units[target].locations[&loc].destroyed {
                whip_trip(b, attacker, target, &o, &mut triggers);
            }
        } else if o.kick {
            add_trigger(&mut triggers, &an, "missed a kick", 0);
        } else if o.fumble {
            let roll = b.roll_2d6();
            let loc = resolve_hit_location(b, attacker, roll, "front");
            b.log(format!("    The flail hits {}'s own {} for {} (TO:AUE p.101).", an, loc, FLAIL_FUMBLE_DAMAGE));
            apply_damage(b, attacker, &loc, Num::I(FLAIL_FUMBLE_DAMAGE), "armor", DamageType::Physical);
            add_trigger(&mut triggers, &an, "hit itself with a flail", 0);
        }
    }
    resolve_pushes(b, &pushes, &mut triggers);
    for (attacker, target) in charges {
        for (name, extra) in charge::resolve_hit(b, attacker, target) {
            triggers.entry(name).or_default().extend(extra);
        }
    }
    for (attacker, target, hit) in dfas {
        for (name, extra) in crate::dfa::resolve(b, attacker, target, hit) {
            triggers.entry(name).or_default().extend(extra);
        }
    }
    for &m in order {
        gear::lower(&mut b.units[m]);
    }
    for &m in order {
        let n = name_of(b, m);
        let extra = ma::end_of_movement_triggers(b, m);
        triggers.entry(n).or_default().extend(extra);
    }
    for &m in order {
        let n = name_of(b, m);
        let forced: Vec<(String, i64)> = triggers.get(&n).cloned().unwrap_or_default();
        b.with_piloting(m, |b| crate::piloting_rolls::resolve_attack_phase_psr(b, m, &forced));
        crate::piloting_rolls::resolve_consciousness_checks(b, m, "Physical Attack Phase");
    }
}

// =============================================================================================================
// Planning (the bot's side of physical attacks): Worth, plans, the Planner, choose_attack
// =============================================================================================================
use crate::fasthash::HashMap;

use crate::structure_weight as sw;

/// How much a point of physical damage on each hit table counts against `target` (the table's own armor exposure times
/// the structure bonus). relative=True divides out the standard-table exposure for that side.
pub struct Worth {
    pub target: UnitId,
    pub relative: bool,
    front: f64,
    memo: HashMap<(String, String, u64), f64>,
}

impl Worth {
    pub fn new(b: &Battle, target: UnitId, relative: bool) -> Worth {
        let t = &b.units[target];
        let front = sw::vulnerability(t, &sw::hit_spread(b, target, "front", None));
        Worth { target, relative, front, memo: HashMap::default() }
    }

    fn exposure(&self, b: &Battle, spread: &sw::Spread) -> f64 {
        if !b.cfg.b("MOVEMENT_EXPOSURE_WEIGHTING") || self.front <= 0.0 {
            return 1.0;
        }
        let v = sw::vulnerability(&b.units[self.target], spread) / self.front;
        b.cfg.f("MOVEMENT_EXPOSURE_MIN").max(b.cfg.f("MOVEMENT_EXPOSURE_MAX").min(v))
    }

    pub fn factor(&mut self, b: &Battle, table: &str, side: &str, damage: f64) -> f64 {
        let t = &b.units[self.target];
        if table == "displacement" {
            if !self.relative || side == "front" {
                return 1.0;
            }
            return 1.0 / self.exposure(b, &sw::hit_spread(b, self.target, side, None));
        }
        let key = (table.to_string(), side.to_string(), damage.to_bits());
        if let Some(g) = self.memo.get(&key) {
            return *g;
        }
        let rolls = table_rolls(table, side, t);
        let spread = sw::hit_spread(b, self.target, side, rolls.as_deref());
        let mut got = self.exposure(b, &spread);
        if self.relative {
            let standard = if side == "front" { 1.0 } else { self.exposure(b, &sw::hit_spread(b, self.target, side, None)) };
            got /= standard;
        }
        if damage > 0.0 {
            got *= sw::spread_worth(t, &spread, damage, b.cfg.f("MOVEMENT_STRUCTURE_WEIGHT")) / damage;
        }
        self.memo.insert(key, got);
        got
    }
}

/// Expected damage of the picks; with a Worth, their worth on `side`.
pub fn expected_damage_of(b: &Battle, base: i64, picks: &[PhysOption], worth: Option<&mut Worth>, side: &str) -> f64 {
    match worth {
        None => {
            // Python: sum(...) of floats (here and below)
            crate::pyfmt::py_sum(picks.iter().map(|o| crate::combat::hit_probability(base + o.mod_) * o.damage.f()))
        }
        Some(w) => {
            let mut terms = Vec::new();
            for o in picks {
                terms.push(crate::combat::hit_probability(base + o.mod_) * o.damage.f() * w.factor(b, &o.table, side, o.damage.f()));
            }
            crate::pyfmt::py_sum(terms)
        }
    }
}

/// One planned physical attack: (expected damage, the limbs it uses, the options).
#[derive(Clone, Debug)]
pub struct Plan {
    pub value: f64,
    pub limbs: Vec<String>,
    pub picks: Vec<PhysOption>,
}

/// Every physical attack the mech could plan with these options, best first; the empty plan is always included.
pub fn plans(b: &Battle, options: &Opts, base: i64, mut worth: Option<&mut Worth>, side: &str) -> Vec<Plan> {
    let mut out = vec![Plan { value: 0.0, limbs: vec![], picks: vec![] }];
    for (kind, opts) in options {
        let groups: Vec<Vec<PhysOption>> = if *kind == "punch" {
            let mut g: Vec<Vec<PhysOption>> = opts.iter().map(|o| vec![o.clone()]).collect();
            if opts.len() > 1 {
                g.push(opts.clone());
            }
            g
        } else {
            opts.iter().map(|o| vec![o.clone()]).collect()
        };
        for g in groups {
            let v = expected_damage_of(b, base, &g, worth.as_deref_mut(), side);
            if v > 0.0 {
                let limbs: Vec<String> = g.iter().flat_map(|o| o.limb.clone()).collect();
                out.push(Plan { value: v, limbs, picks: g });
            }
        }
    }
    out.sort_by(|x, y| (-x.value).partial_cmp(&(-y.value)).unwrap());
    out
}

fn push_value(b: &Battle, target: UnitId, label: &str, direction: i64) -> Num {
    crate::movement_attacks::displacement_worth(b, target, label, direction)
}

/// attack_options: {"type": [option, ...]} the attacker could make this phase with arc action `action`.
pub fn attack_options(b: &mut Battle, attacker: UnitId, target: UnitId, action: Option<&crate::mech_state::ArcAction>) -> Opts {
    if b.units[attacker].prone || is_immobile(&b.units[attacker]) || b.is_destroyed(attacker) || b.is_destroyed(target) {
        return IndexMap::default();
    }
    let a_xy = crate::hex_geometry::parse_hex_label(b.units[attacker].hex.as_deref().unwrap()).unwrap();
    let a_facing = crate::hex_geometry::compass_to_facing(&b.units[attacker].facing).unwrap();
    let (ah, th) = (b.units[attacker].hex.clone().unwrap(), b.units[target].hex.clone().unwrap());
    let (a_level, t_level) = (b.board.hexes[&ah].level, b.board.hexes[&th].level);
    let fired: HashSet<ItemId> = b.units[attacker].weapons_fired_this_turn.clone().map(|s| s.into_iter().collect()).unwrap_or_default();
    let cur = arcs::current_action(&b.units[attacker]);
    let act = action.cloned().unwrap_or_else(|| cur.clone());
    let t_xy = crate::hex_geometry::parse_hex_label(&th).unwrap();
    let prone = b.units[target].prone;
    let sup = is_superheavy(&b.units[target]);
    let mut opts = options_at(b, attacker, a_xy, a_facing, a_level, t_xy, t_level, prone, &fired, &act, sup);
    if !act.flip {
        let mut value = |b: &mut Battle, label: &str, direction: i64| push_value(b, target, label, direction).f();
        if let Some(push) = push_option_valued(b, attacker, a_xy, a_facing, a_level, target, &th, t_level, &fired, &mut value) {
            opts.insert("push", vec![push]);
        }
    }
    let allowed = crate::water::physical_allowed(crate::water::state(b, attacker), crate::water::state(b, target));
    opts = water_filter(opts, allowed.as_deref());
    let blocked = gear::raised_blocks(&b.units[attacker]);
    if !blocked.is_empty() {
        let free = |o: &PhysOption| !o.limb.iter().any(|l| blocked.contains(l));
        opts = opts.into_iter().map(|(k, v)| (k, v.into_iter().filter(|o| free(o)).collect::<Vec<_>>())).filter(|(_, v)| !v.is_empty()).collect();
    }
    opts
}

/// push_option with the displacement value coming from a closure that also reports the exact Num (so an int HP value
/// keeps printing as an int).
#[allow(clippy::too_many_arguments)]
fn push_option_valued(b: &mut Battle, attacker: UnitId, a_xy: (i64, i64), a_facing: i64, a_level: i64, target: UnitId, t_label: &str, t_level: i64, fired: &HashSet<ItemId>, value: &mut dyn FnMut(&mut Battle, &str, i64) -> f64) -> Option<PhysOption> {
    let mut o = push_option(b, attacker, a_xy, a_facing, a_level, target, t_label, t_level, fired, value)?;
    // the option's damage is the displacement worth as the Python computed it (an int total HP stays an int)
    o.damage = push_value(b, target, t_label, a_facing);
    Some(o)
}

/// base TN of an attack on the adjacent target (p.76), from where the attacker stands.
pub fn base_tn_for(b: &Battle, attacker: UnitId, target: UnitId) -> i64 {
    let a_hex = crate::hex_geometry::parse_hex_label(b.units[attacker].hex.as_deref().unwrap()).unwrap();
    let t_hex = crate::hex_geometry::parse_hex_label(b.units[target].hex.as_deref().unwrap()).unwrap();
    let h = crate::attack_resolution::standing();
    let modifier = crate::los::has_los(a_hex, t_hex, &b.board, h, h).unwrap().modifier;
    base_tn(
        &b.units[attacker],
        crate::combat::mode_to_amm(&b.units[attacker].move_mode),
        crate::attack_resolution::target_tmm(&b.units[target]),
        modifier,
        crate::attack_resolution::prone_target_modifier(&b.units[target], 1),
    )
}

/// Pile 4: the arc action (a twist, if it may still declare one) and attack type with the most expected damage,
/// weighted by where each table lands. Returns (base TN, [options], ArcAction) or None.
pub fn choose_attack(b: &mut Battle, attacker: UnitId, target: UnitId) -> Option<(i64, Vec<PhysOption>, crate::mech_state::ArcAction)> {
    if b.is_destroyed(attacker) || b.is_destroyed(target) || b.units[attacker].hex == b.units[target].hex {
        return None;
    }
    let turret = arcs::current_action(&b.units[attacker]).turret;
    let mut actions: Vec<crate::mech_state::ArcAction> = Vec::new();
    for a in arcs::arc_options(&b.units[attacker], "physical") {
        let a = crate::mech_state::ArcAction { twist: a.twist, flip: a.flip, turret: turret.clone() };
        if !actions.contains(&a) {
            actions.push(a);
        }
    }
    let a_xy = crate::hex_geometry::parse_hex_label(b.units[attacker].hex.as_deref().unwrap()).unwrap();
    let t_xy = crate::hex_geometry::parse_hex_label(b.units[target].hex.as_deref().unwrap()).unwrap();
    let tf = crate::hex_geometry::compass_to_facing(&b.units[target].facing).unwrap();
    let side = crate::attack_resolution::attack_side(b, a_xy, t_xy, tf, crate::attack_resolution::standing(), crate::attack_resolution::standing()).to_string();
    let mut worth = Worth::new(b, target, false);
    let mut base: Option<i64> = None;
    let t_water = crate::water::state(b, target);
    let quad = b.units[target].mech_type == "quad" || b.units[target].mech_type == "quadvee";
    let mut best: Option<(i64, Vec<PhysOption>, crate::mech_state::ArcAction)> = None;
    let value = |b: &Battle, worth: &mut Worth, base: i64, opts: &[PhysOption]| -> f64 {
        if t_water != crate::water::GROUND {
            let scaled: Vec<PhysOption> = opts
                .iter()
                .map(|o| {
                    let mut o = o.clone();
                    o.damage = Num::F(o.damage.f() * crate::water::physical_value_factor_q(quad, t_water, &o.table, &side));
                    o
                })
                .collect();
            return expected_damage_of(b, base, &scaled, Some(worth), &side);
        }
        expected_damage_of(b, base, opts, Some(worth), &side)
    };
    for action in actions {
        let options = attack_options(b, attacker, target, Some(&action));
        if options.is_empty() {
            continue;
        }
        if base.is_none() {
            base = Some(base_tn_for(b, attacker, target));
        }
        let base = base.unwrap();
        let mut picks_by_kind: Vec<(&'static str, Vec<PhysOption>)> = Vec::new();
        for (k, opts) in &options {
            let pick = if *k == "punch" {
                opts.clone()
            } else {
                let mut best_o = &opts[0];
                let mut best_v = value(b, &mut worth, base, std::slice::from_ref(&opts[0]));
                for o in &opts[1..] {
                    let v = value(b, &mut worth, base, std::slice::from_ref(o));
                    if v > best_v {
                        best_v = v;
                        best_o = o;
                    }
                }
                vec![best_o.clone()]
            };
            picks_by_kind.push((k, pick));
        }
        let mut kind_i = 0;
        let mut kind_v = value(b, &mut worth, base, &picks_by_kind[0].1);
        for (i, (_, p)) in picks_by_kind.iter().enumerate().skip(1) {
            let v = value(b, &mut worth, base, p);
            if v > kind_v {
                kind_v = v;
                kind_i = i;
            }
        }
        let picks = picks_by_kind[kind_i].1.clone();
        let pv = value(b, &mut worth, base, &picks);
        let better = match &best {
            None => true,
            Some((_, bp, _)) => pv > value(b, &mut worth, base, bp) + 1e-12,
        };
        if pv > 0.0 && better {
            best = Some((base, picks, action));
        }
    }
    best
}

// =============================================================================================================
// physical.Planner: physical plans for positions that do not exist yet (movement scoring, the ranged phase's look-ahead)
// =============================================================================================================
pub type PlanCase = (Reach, i64, bool);

/// Physical plans for one mech before anything has fired this turn. The options only depend on the Reach signature,
/// the level difference and whether the target is prone, so they are built once per case.
pub struct PhysPlanner {
    pub mech: UnitId,
    pub worth: Option<Worth>,
    pub target_superheavy: bool,
    options: HashMap<PlanCase, Opts>,
    plans: HashMap<(PlanCase, i64, String, Option<Vec<&'static str>>, Option<&'static str>), Vec<Plan>>,
    held: HashMap<Vec<String>, HashSet<ItemId>>,
    push_target: Option<UnitId>,
    push_values: HashMap<(String, i64), Num>,
}

impl PhysPlanner {
    pub fn new(b: &Battle, mech: UnitId, worth: Option<Worth>) -> PhysPlanner {
        let target_superheavy = worth.as_ref().map_or(false, |w| is_superheavy(&b.units[w.target]));
        PhysPlanner { mech, worth, target_superheavy, options: HashMap::default(), plans: HashMap::default(), held: HashMap::default(), push_target: None, push_values: HashMap::default() }
    }

    fn plans_for(&mut self, b: &mut Battle, reach: Reach, diff: i64, target_prone: bool, base: i64, side: &str, allowed: &Option<Vec<&'static str>>, t_water: Option<&'static str>) -> Vec<Plan> {
        let case = (reach, diff, target_prone);
        let side = if self.worth.is_some() { side } else { "front" };
        let key = (case, base, side.to_string(), allowed.clone(), t_water);
        if let Some(got) = self.plans.get(&key) {
            return got.clone();
        }
        if !self.options.contains_key(&case) {
            let o = options(b, self.mech, &reach, diff, target_prone, &HashSet::default(), self.target_superheavy);
            self.options.insert(case, o);
        }
        let mut opts = water_filter(self.options[&case].clone(), allowed.as_deref());
        if let Some(tw) = t_water {
            if tw != crate::water::GROUND {
                let quad = self.worth.as_ref().map_or(false, |w| {
                    let t = &b.units[w.target];
                    t.mech_type == "quad" || t.mech_type == "quadvee"
                });
                opts = opts
                    .into_iter()
                    .map(|(k, v)| {
                        (
                            k,
                            v.into_iter()
                                .map(|mut o| {
                                    let f = crate::water::physical_value_factor_q(quad, tw, &o.table, side);
                                    o.damage = Num::F(o.damage.f() * f);
                                    o
                                })
                                .collect(),
                        )
                    })
                    .collect();
            }
        }
        let got = plans(b, &opts, base, self.worth.as_mut(), side);
        self.plans.insert(key, got.clone());
        got
    }

    /// The distinct (ArcKey, reach signature) pairs `actions` give against an adjacent target.
    pub fn cases(&self, b: &Battle, pair_arcs: &[i64; 6], facing: i64, actions: &[ArcAction], legs: &[(String, i64)]) -> Vec<(arcs::ArcKey, Reach)> {
        let mut out: Vec<(arcs::ArcKey, Reach)> = Vec::new();
        for a in actions {
            let c = (arcs::key_for(pair_arcs, facing, a, legs), Reach::new(&b.units[self.mech], facing, a, pair_arcs));
            if !out.contains(&c) {
                out.push(c);
            }
        }
        out
    }

    pub fn plans_in_case(&mut self, b: &mut Battle, reach: Reach, diff: i64, target_prone: bool, base: i64, side: &str, allowed: &Option<Vec<&'static str>>, t_water: Option<&'static str>) -> Vec<Plan> {
        if reachable(diff, self.target_superheavy) { self.plans_for(b, reach, diff, target_prone, base, side, allowed, t_water) } else { vec![] }
    }

    /// [(value, limbs, option)] for the push from this spot, or None.
    #[allow(clippy::too_many_arguments)]
    pub fn push_plan(&mut self, b: &mut Battle, a_xy: (i64, i64), a_facing: i64, a_level: i64, target: UnitId, t_label: &str, t_level: i64, base: i64, side: &str) -> Option<(f64, PhysOption)> {
        if self.push_target != Some(target) {
            self.push_target = Some(target);
            self.push_values.clear();
        }
        let values = &mut self.push_values;
        let mut value_for = |b: &mut Battle, label: &str, direction: i64| -> f64 {
            let key = (label.to_string(), direction);
            if let Some(v) = values.get(&key) {
                return v.f();
            }
            let v = push_value(b, target, label, direction);
            values.insert(key, v);
            v.f()
        };
        let o = push_option_valued(b, self.mech, a_xy, a_facing, a_level, target, t_label, t_level, &HashSet::default(), &mut value_for)?;
        let v = expected_damage_of(b, base, std::slice::from_ref(&o), self.worth.as_mut(), side);
        if v > 0.0 { Some((v, o)) } else { None }
    }

    pub fn held(&mut self, b: &Battle, limbs: &[String]) -> HashSet<ItemId> {
        if let Some(g) = self.held.get(limbs) {
            return g.clone();
        }
        let g = limb_weapon_ids(&b.units[self.mech], limbs);
        self.held.insert(limbs.to_vec(), g.clone());
        g
    }
}
