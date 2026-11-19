// Translated from INTEGRATION__arcs.py (session 22): firing arcs, torso twists, flipped arms, turrets.
use crate::fasthash::{HashMap, HashSet};
use std::collections::{BTreeSet};

use crate::fasthash::IndexMap;

use crate::equipment::{ItemId, Slot};
use crate::mech_state::{ArcAction, Mech, Turret};

pub const FORWARD: i64 = 0;
pub const LEFT: i64 = 1;
pub const RIGHT: i64 = 2;
pub const REAR: i64 = 3;
const EPS: f64 = 1e-6;

pub fn arc_name(a: i64) -> &'static str {
    match a {
        0 => "forward",
        1 => "left side",
        2 => "right side",
        _ => "rear",
    }
}

fn py_fmod(x: f64, y: f64) -> f64 {
    let r = x % y;
    if r != 0.0 && ((r < 0.0) != (y < 0.0)) { r + y } else { r }
}

/// The arc t_hex is in for an attacker on a_hex facing 0..5.
pub fn arcs_between(a_hex: (i64, i64), t_hex: (i64, i64)) -> [i64; 6] {
    let (dx, dy) = (t_hex.0 - a_hex.0, t_hex.1 - a_hex.1);
    if dx == 0 && dy == 0 {
        return [FORWARD; 6];
    }
    let angle = ((3f64).sqrt() / 2.0 * dy as f64).atan2(1.5 * dx as f64).to_degrees();
    let mut out = [0i64; 6];
    for facing in 0..6 {
        let off = py_fmod(angle - (90 - 60 * facing as i64) as f64 + 180.0, 360.0) - 180.0;
        let size = off.abs();
        out[facing] = if size <= 60.0 + EPS {
            FORWARD
        } else if size <= 120.0 + EPS {
            if off > 0.0 { LEFT } else { RIGHT }
        } else {
            REAR
        };
    }
    out
}

pub fn no_action() -> ArcAction {
    ArcAction { twist: 0, flip: false, turret: None }
}

pub fn tripod_leg_offset(leg: &str) -> i64 {
    match leg {
        "Left Leg" => -2,
        "Right Leg" => 2,
        _ => 0,
    }
}

fn norm(name: &str) -> String {
    name.replace(' ', "").replace('-', "").to_uppercase()
}

/// `norm(name).ends_with(suffix)` for an upper-case ASCII `suffix`, without building the string: walks the name from the
/// end, skipping spaces and hyphens, comparing letters case-blind. A non-ASCII name (whose upper case can grow, e.g.
/// "ß" -> "SS") takes the slow path, so the answer is always the same. Speed only (2026-11-19 profile: the turret
/// checks below, run inside every Hydra and Gladiator move score, were ~40% of a 12 v 12 Hydra battle).
fn norm_ends_with(name: &str, suffix: &str) -> bool {
    if !name.is_ascii() {
        return norm(name).ends_with(suffix);
    }
    let mut want = suffix.bytes().rev();
    for c in name.bytes().rev().filter(|c| *c != b' ' && *c != b'-') {
        match want.next() {
            None => return true,
            Some(w) if c.to_ascii_uppercase() == w => {}
            Some(_) => return false,
        }
    }
    want.next().is_none()
}

fn slot_name<'a>(m: &'a Mech, s: &'a Slot) -> &'a str {
    match s {
        Slot::Name(n) => n,
        Slot::Item(i) => &m.items[*i].name,
    }
}

pub fn has_quad_turret(mech: &Mech) -> bool {
    mech.crits.values().any(|slots| slots.iter().any(|s| norm_ends_with(slot_name(mech, s), "QUADTURRET")))
}

/// {location: "shoulder" / "head"}
pub fn mech_turrets(mech: &Mech) -> IndexMap<String, &'static str> {
    let mut out: IndexMap<String, &'static str> = IndexMap::default();
    for (loc, slots) in &mech.crits {
        for s in slots {
            let n = slot_name(mech, s);
            if norm_ends_with(n, "SHOULDERTURRET") {
                out.insert(loc.clone(), "shoulder");
            } else if norm_ends_with(n, "HEADTURRET") {
                out.insert(loc.clone(), "head");
            }
        }
    }
    for ((loc, _), info) in &mech.destroyed_slot_info {
        let n = &info.name;
        if norm_ends_with(n, "SHOULDERTURRET") {
            out.entry(loc.clone()).or_insert("shoulder");
        } else if norm_ends_with(n, "HEADTURRET") {
            out.entry(loc.clone()).or_insert("head");
        }
    }
    out
}

pub fn mech_turret_locked(mech: &Mech, loc: &str) -> bool {
    mech.destroyed_slot_info.iter().any(|((l, _), info)| l == loc && {
        norm_ends_with(&info.name, "SHOULDERTURRET") || norm_ends_with(&info.name, "HEADTURRET")
    })
}

/// The location of the shoulder / head turret a "(T)" weapon in `locations` sits in, or None.
pub fn mech_turret_of(mech: &Mech, locations: &[String]) -> Option<String> {
    let turrets = mech_turrets(mech);
    for loc in locations {
        if turrets.contains_key(loc) {
            return Some(loc.clone());
        }
    }
    turrets.iter().find(|(_, k)| **k == "head").map(|(l, _)| l.clone())
}

pub fn turret_locked(mech: &Mech) -> bool {
    mech.destroyed_slot_info.values().any(|info| norm_ends_with(&info.name, "QUADTURRET"))
}

pub fn can_flip_arms(mech: &Mech) -> bool {
    if mech.mech_type == "quad" || mech.mech_type == "quadvee" || !["Left Arm", "Right Arm"].iter().all(|a| mech.crits.contains_key(*a)) {
        return false;
    }
    for arm in ["Left Arm", "Right Arm"] {
        let mut present: HashSet<String> = mech.crits[arm].iter().map(|s| slot_name(mech, s).to_string()).collect();
        for ((loc, _), info) in &mech.destroyed_slot_info {
            if loc == arm {
                present.insert(info.name.clone());
            }
        }
        if present.contains("Hand Actuator") || present.contains("Lower Arm Actuator") {
            return false;
        }
    }
    let mut seen: IndexMap<ItemId, BTreeSet<&str>> = IndexMap::default();
    for (loc, slots) in &mech.crits {
        for s in slots {
            if let Slot::Item(i) = s {
                if mech.items[*i].category.as_deref() == Some("weapon") {
                    seen.entry(*i).or_default().insert(loc.as_str());
                }
            }
        }
    }
    !seen.values().any(|locs| locs.iter().any(|l| *l == "Left Arm" || *l == "Right Arm") && locs.iter().any(|l| *l != "Left Arm" && *l != "Right Arm"))
}

pub fn twist_offsets(mech: &Mech) -> Vec<i64> {
    if mech.prone || mech.mech_type == "quad" || mech.mech_type == "quadvee" {
        return vec![0];
    }
    if mech.mech_type == "tripod" {
        return vec![0, -1, 1, -2, 2, 3];
    }
    vec![0, -1, 1]
}

pub fn current_action(mech: &Mech) -> ArcAction {
    mech.arc_action.clone().unwrap_or_else(no_action)
}

/// Every ArcAction the mech may declare now, no change first.
pub fn arc_options(mech: &Mech, phase: &str) -> Vec<ArcAction> {
    let mut turret_offsets: Vec<Option<i64>> = vec![None];
    if has_quad_turret(mech) {
        turret_offsets = if turret_locked(mech) { vec![Some(mech.turret_last_offset.unwrap_or(0))] } else { vec![Some(0), Some(-1), Some(1), Some(-2), Some(2), Some(3)] };
    }
    let base: Vec<ArcAction> = if mech.arc_action_locked.unwrap_or(false) {
        vec![current_action(mech)]
    } else {
        let mut v: Vec<ArcAction> = twist_offsets(mech).into_iter().map(|t| ArcAction { twist: t, flip: false, turret: None }).collect();
        if phase == "ranged" && !mech.prone && can_flip_arms(mech) {
            v.push(ArcAction { twist: 0, flip: true, turret: None });
        }
        v
    };
    let mut out = Vec::new();
    for a in &base {
        for t in &turret_offsets {
            out.push(ArcAction { twist: a.twist, flip: a.flip, turret: t.map(Turret::Offset) });
        }
    }
    out
}

/// (leg location, offset of its forward arc from the facing) - plus ("turret:<loc>", offset) for each locked turret.
pub fn leg_offsets(mech: &Mech) -> Vec<(String, i64)> {
    let mut out: Vec<(String, i64)> = if mech.mech_type == "tripod" {
        mech.leg_locations.iter().map(|l| (l.clone(), tripod_leg_offset(l))).collect()
    } else {
        mech.leg_locations.iter().map(|l| (l.clone(), 0)).collect()
    };
    let turrets = mech_turrets(mech);
    if mech.mech_turret_dir.is_some() || !turrets.is_empty() {
        let dirs = mech.mech_turret_dir.clone().unwrap_or_default();
        for loc in turrets.keys() {
            if mech_turret_locked(mech, loc) {
                out.push((format!("turret:{}", loc), dirs.get(loc).copied().unwrap_or(0)));
            }
        }
    }
    out
}

/// What decides which weapons bear on one target (scorer cache key).
#[derive(Clone, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct ArcKey {
    pub torso_arc: i64,
    pub legs_forward: BTreeSet<String>,
    pub flip: bool,
    pub turret_forward: Option<bool>,
}

pub fn simple_key(mech: &Mech, torso_arc: i64, legs_forward: bool) -> ArcKey {
    ArcKey { torso_arc, legs_forward: if legs_forward { mech.leg_locations.iter().cloned().collect() } else { BTreeSet::new() }, flip: false, turret_forward: None }
}

fn at(arcs: &[i64; 6], facing: i64, off: i64) -> i64 {
    arcs[(facing + off).rem_euclid(6) as usize]
}

pub fn key_for(arcs: &[i64; 6], facing: i64, action: &ArcAction, legs: &[(String, i64)]) -> ArcKey {
    ArcKey {
        torso_arc: at(arcs, facing, action.twist),
        legs_forward: legs.iter().filter(|(_, off)| at(arcs, facing, *off) == FORWARD).map(|(l, _)| l.clone()).collect(),
        flip: action.flip,
        turret_forward: action.turret.as_ref().map(|t| match t {
            Turret::Offset(o) => at(arcs, facing, *o) == FORWARD,
            Turret::Name(n) => panic!("key_for: turret {:?}", n),
        }),
    }
}

/// ((ArcKey, first ArcAction giving it), ...), one per distinct key among `actions`.
pub fn arc_keys(arcs: &[i64; 6], facing: i64, actions: &[ArcAction], legs: &[(String, i64)]) -> Vec<(ArcKey, ArcAction)> {
    let mut out: Vec<(ArcKey, ArcAction)> = Vec::new();
    for a in actions {
        let k = key_for(arcs, facing, a, legs);
        if !out.iter().any(|(x, _)| *x == k) {
            out.push((k, a.clone()));
        }
    }
    out
}

/// 'turret', 'turret:<loc>', 'rear', 'leg', 'left_arm', 'right_arm' or 'torso'.
pub fn weapon_class(mech: &Mech, weapon: ItemId, locations: &[String]) -> String {
    let w = &mech.items[weapon];
    if w.turret_mounted && has_quad_turret(mech) && mech_turret_of(mech, locations).is_none() {
        return "turret".into();
    }
    if w.turret_mounted {
        if let Some(loc) = mech_turret_of(mech, locations) {
            return format!("turret:{}", loc);
        }
    }
    if w.rear_mounted {
        return "rear".into();
    }
    let locs: HashSet<&str> = locations.iter().map(|s| s.as_str()).collect();
    if !locs.is_empty() && locs.iter().all(|l| mech.leg_locations.iter().any(|x| x == l)) {
        return "leg".into();
    }
    if locs.len() == 1 && locs.contains("Left Arm") {
        return "left_arm".into();
    }
    if locs.len() == 1 && locs.contains("Right Arm") {
        return "right_arm".into();
    }
    "torso".into()
}

/// Ids of `weapons` that cannot fire at a target seen as `key`.
pub fn unavailable(mech: &Mech, weapons: &[ItemId], locations_by_weapon: &HashMap<ItemId, Vec<String>>, key: &ArcKey) -> HashSet<ItemId> {
    let mut blocked = HashSet::default();
    let torso_arc = key.torso_arc;
    let empty: Vec<String> = Vec::new();
    for &w in weapons {
        let locs = locations_by_weapon.get(&w).unwrap_or(&empty);
        let kind = weapon_class(mech, w, locs);
        let ok = if kind == "turret" {
            key.turret_forward == Some(true)
        } else if let Some(loc) = kind.strip_prefix("turret:") {
            mech_turret_bears(mech, loc, torso_arc, key)
        } else if kind == "rear" {
            torso_arc == REAR
        } else if kind == "leg" {
            locs.iter().all(|l| key.legs_forward.contains(l))
        } else if (kind == "left_arm" || kind == "right_arm") && key.flip {
            torso_arc == REAR
        } else if kind == "left_arm" {
            torso_arc == FORWARD || torso_arc == LEFT
        } else if kind == "right_arm" {
            torso_arc == FORWARD || torso_arc == RIGHT
        } else {
            torso_arc == FORWARD
        };
        if !ok {
            blocked.insert(w);
        }
    }
    blocked
}

fn mech_turret_bears(mech: &Mech, loc: &str, torso_arc: i64, key: &ArcKey) -> bool {
    if mech_turret_locked(mech, loc) {
        return key.legs_forward.contains(&format!("turret:{}", loc));
    }
    if mech_turrets(mech).get(loc) == Some(&"head") {
        return !(has_quad_turret(mech) && torso_arc == REAR);
    }
    let side = if loc.starts_with("Left") { Some("Left") } else if loc.starts_with("Right") { Some("Right") } else { None };
    !((side == Some("Left") && torso_arc == RIGHT) || (side == Some("Right") && torso_arc == LEFT))
}

/// Remember where a working shoulder / head turret last pointed, for a later lock.
pub fn note_mech_turret_fire(mech: &mut Mech, weapon: ItemId, locations: &[String], target_offset: i64) {
    let kind = weapon_class(mech, weapon, locations);
    if let Some(loc) = kind.strip_prefix("turret:") {
        if !mech_turret_locked(mech, loc) {
            mech.mech_turret_dir.get_or_insert_with(IndexMap::default).insert(loc.to_string(), target_offset.rem_euclid(6));
        }
    }
}

/// Record the ArcAction declared this phase.
pub fn declare(mech: &mut Mech, action: ArcAction) {
    mech.torso_twist = Some(action.twist);
    mech.arms_flipped = Some(action.flip);
    if action.twist != 0 || action.flip {
        mech.arc_action_locked = Some(true);
    }
    if let Some(Turret::Offset(t)) = &action.turret {
        mech.turret_last_offset = Some(*t);
    }
    mech.arc_action = Some(action);
}

/// End Phase: the torso turns forward and reversed arms return.
pub fn end_turn(mech: &mut Mech) {
    let turret = current_action(mech).turret;
    mech.arc_action = Some(ArcAction { twist: 0, flip: false, turret });
    mech.torso_twist = Some(0);
    mech.arms_flipped = Some(false);
    mech.arc_action_locked = Some(false);
}

pub fn describe(action: &ArcAction) -> String {
    let mut parts: Vec<String> = Vec::new();
    if action.twist != 0 {
        parts.push(format!("twists its torso {} hexside{} {}", action.twist.abs(), if action.twist.abs() > 1 { "s" } else { "" }, if action.twist > 0 { "right" } else { "left" }));
    }
    if action.flip {
        parts.push("reverses its arms".into());
    }
    if let Some(Turret::Offset(t)) = &action.turret {
        if *t != 0 {
            parts.push(format!("turns its turret {} {}", t.abs(), if *t > 0 { "right" } else { "left" }));
        }
    }
    parts.join(" and ")
}

#[cfg(test)]
mod norm_tests {
    use super::{norm, norm_ends_with};

    /// The fast check must agree with the slow one on every name, including spacing, hyphens, case and non-ASCII.
    #[test]
    fn norm_ends_with_matches_norm() {
        let names = ["Shoulder Turret", "shoulder-turret", "Head Turret", "Quad Turret", "QUADTURRET", "Medium Laser", "", " ", "-",
            "Turret", "ISQuadTurret", "Clan Head-Turret ", "ßHOULDERTURRET", "Ärm Quad Turret", "urret", "HEADTURRET x"];
        for n in names {
            for suf in ["QUADTURRET", "SHOULDERTURRET", "HEADTURRET", "TURRET"] {
                assert_eq!(norm_ends_with(n, suf), norm(n).ends_with(suf), "{n:?} / {suf}");
            }
        }
    }
}
