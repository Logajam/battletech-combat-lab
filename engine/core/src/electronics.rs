// Translated from INTEGRATION__electronics.py (session 22): Artemis IV / V, Narc pods, ECM. (pod_value, which prices
// with the Planner, and log_controls come with fire_modes.)
use crate::fasthash::HashSet;

use crate::battle::{Battle, UnitId};
use crate::equipment::{ItemId, Slot};
use crate::equipment_systems::active_stealth;
use crate::mech_state::{Mech, NarcPod};
use crate::weapon_rules::{is_ams, is_cluster, is_streak, canonical_name};

pub fn artemis_bonus(kind: i64) -> (i64, i64) {
    if kind == 5 { (-1, 3) } else { (0, 2) }
}
pub const ATM_CLUSTER: i64 = 2;
pub const NARC_TN: i64 = -1;
pub const NARC_CLUSTER: i64 = 2;
pub const SINGLE_MISSILE_KILL_CHANCE: f64 = 0.5;

/// electronics.FireControl
#[derive(Clone, Debug, PartialEq)]
pub struct FireControl {
    pub munition: String,
    pub tn: i64,
    pub cluster: i64,
    pub streak_lock: bool,
    pub note: String,
}

impl FireControl {
    pub fn plain() -> FireControl {
        FireControl { munition: "standard".into(), tn: 0, cluster: 0, streak_lock: true, note: String::new() }
    }
}

fn norm(name: &str) -> String {
    name.replace(' ', "").replace('-', "").to_uppercase()
}

pub fn dead(mech: &Mech) -> HashSet<ItemId> {
    mech.destroyed_slot_info.values().filter_map(|i| i.instance_id).collect()
}

pub fn is_narc(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    canonical_name(b, u, w).contains("NARC")
}

pub fn is_atm(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    canonical_name(b, u, w).contains("ATM")
}

fn artemis_kind_of(m: &Mech, slot: ItemId) -> Option<i64> {
    let it = &m.items[slot];
    if it.category.as_deref() == Some("ammo") {
        return None;
    }
    let n = norm(&it.name);
    if n.contains("ARTEMISV") {
        Some(5)
    } else if n.contains("ARTEMISIV") {
        Some(4)
    } else {
        None
    }
}

fn is_ecm(m: &Mech, slot: ItemId) -> bool {
    let it = &m.items[slot];
    if it.category.as_deref() == Some("ammo") {
        return false;
    }
    let n = norm(&it.name);
    n.contains("ECM") || n.contains("WATCHDOG")
}

/// Once per battle (fresh clone): link Artemis FCS to launchers, find the ECM suites, clear the pods.
pub fn attach(b: &mut Battle, u: UnitId) {
    b.units[u].narc_pods = Vec::new();
    b.units[u].ecm_suites = Vec::new();
    let mut seen: HashSet<ItemId> = HashSet::default();
    let mut fcs_by_loc: crate::fasthash::IndexMap<String, Vec<(ItemId, i64)>> = crate::fasthash::IndexMap::default();
    let mut launchers_by_loc: crate::fasthash::IndexMap<String, Vec<ItemId>> = crate::fasthash::IndexMap::default();
    let locs: Vec<String> = b.units[u].crits.keys().cloned().collect();
    for loc in &locs {
        let slots: Vec<ItemId> = b.units[u].crits[loc].iter().filter_map(|s| if let Slot::Item(i) = s { Some(*i) } else { None }).collect();
        for slot in slots {
            if !seen.insert(slot) {
                continue;
            }
            if let Some(kind) = artemis_kind_of(&b.units[u], slot) {
                fcs_by_loc.entry(loc.clone()).or_default().push((slot, kind));
            } else if is_ecm(&b.units[u], slot) {
                b.units[u].ecm_suites.push(slot);
            } else if b.units[u].items[slot].category.as_deref() == Some("weapon")
                && is_cluster(b, u, slot)
                && !is_streak(b, u, slot)
                && !is_narc(b, u, slot)
                && !is_atm(b, u, slot)
                && !is_ams(b, u, slot)
            {
                launchers_by_loc.entry(loc.clone()).or_default().push(slot);
            }
        }
    }
    let mut leftover_fcs: Vec<(ItemId, i64)> = Vec::new();
    let mut leftover_launchers: Vec<ItemId> = Vec::new();
    for loc in &locs {
        let fcs = fcs_by_loc.get(loc).cloned().unwrap_or_default();
        let launchers = launchers_by_loc.get(loc).cloned().unwrap_or_default();
        for ((slot, kind), w) in fcs.iter().zip(launchers.iter()) {
            b.units[u].items[*w].artemis = Some((*slot, *kind));
        }
        leftover_fcs.extend(fcs.iter().skip(launchers.len()).cloned());
        leftover_launchers.extend(launchers.iter().skip(fcs.len()).cloned());
    }
    for ((slot, kind), w) in leftover_fcs.iter().zip(leftover_launchers.iter()) {
        b.units[u].items[*w].artemis = Some((*slot, *kind));
    }
}

/// 4 / 5 for a live linked FCS, else None.
pub fn artemis_kind(mech: &Mech, weapon: ItemId) -> Option<i64> {
    let (slot, kind) = mech.items[weapon].artemis?;
    if dead(mech).contains(&slot) { None } else { Some(kind) }
}

pub fn live_ecm(mech: &Mech) -> Vec<ItemId> {
    let d = dead(mech);
    mech.ecm_suites.iter().copied().filter(|s| !d.contains(s)).collect()
}

/// Does this mech's ECM jam its enemies right now?
pub fn hostile_field(mech: &Mech) -> bool {
    if mech.shutdown || live_ecm(mech).is_empty() {
        return false;
    }
    !active_stealth(mech).iter().any(|k| *k != "chameleon")
}

pub fn angel_field(mech: &Mech) -> bool {
    hostile_field(mech) && live_ecm(mech).iter().any(|s| norm(&mech.items[*s].name).contains("ANGEL"))
}

pub fn as_if_jammed(mech: &Mech) -> bool {
    active_stealth(mech).iter().any(|k| *k == "stealth_armor" || *k == "void_signature") || crate::advanced_weapons::as_if_jammed(mech)
}

pub fn artemis_blocked(attacker: &Mech, target: &Mech) -> bool {
    hostile_field(target) || as_if_jammed(attacker)
}

pub fn narc_blocked(target: &Mech) -> bool {
    hostile_field(target)
}

fn live_pods<'a>(target: &'a Mech, owner_side: &str, effective_only: bool) -> Vec<&'a NarcPod> {
    target.narc_pods.iter().filter(|p| p.owner == owner_side && !target.locations[p.location.as_str()].destroyed && (p.effective || !effective_only)).collect()
}

pub fn live_pod_exists(target: &Mech, owner_side: &str, effective_only: bool) -> bool {
    !live_pods(target, owner_side, effective_only).is_empty()
}

/// A working homing pod from `attacker` on `target` (p.193).
pub fn homing_working(attacker: &Mech, target: &Mech) -> bool {
    live_pod_exists(target, attacker.side_name.as_deref().unwrap_or(""), true) && !narc_blocked(target)
}

pub fn attach_pod(target: &mut Mech, location: &str, owner_side: &str) {
    target.narc_pods.push(NarcPod { effective: false, location: location.to_string(), owner: owner_side.to_string() });
}

/// End of the Ranged phase: pods that hit take effect from the next phase (p.193).
pub fn activate_pods(mech: &mut Mech) {
    for p in mech.narc_pods.iter_mut() {
        p.effective = true;
    }
}

/// Munition kinds the weapon can fire right now (live bins with shots), in set order of first appearance.
pub fn munitions(mech: &Mech, weapon: ItemId) -> Vec<String> {
    if !mech.items[weapon].needs_ammo.unwrap_or(false) {
        return vec!["standard".into()];
    }
    let mut out: Vec<String> = Vec::new();
    for bin in crate::ammo::bins_for(mech, weapon) {
        let m = mech.items[bin].munition.clone().unwrap_or_else(|| "standard".into());
        if !out.contains(&m) {
            out.push(m);
        }
    }
    out
}

/// FireControl of `weapon` firing `munition` at `target` now.
pub fn control_for(b: &mut Battle, attacker: UnitId, weapon: ItemId, target: UnitId, munition: &str) -> FireControl {
    if b.units[attacker].items[weapon].damage_type.as_deref() != Some("Missile") {
        // AUTOCANNON MUNITIONS (Core pp.191-192; N10): precision rounds take up to 2 off the target's movement modifier
        return match munition {
            "precision" => {
                let relief = crate::attack_resolution::target_tmm(&b.units[target]).clamp(0, 2);
                FireControl { munition: munition.into(), tn: -relief, note: format!("precision rounds -{}", relief), ..FireControl::plain() }
            }
            "ap" => FireControl { munition: munition.into(), note: "armor-piercing rounds".into(), ..FireControl::plain() },
            "caseless" => FireControl { munition: munition.into(), note: "caseless rounds".into(), ..FireControl::plain() },
            _ => FireControl::plain(),
        };
    }
    let lock = !(is_streak(b, attacker, weapon) && angel_field(&b.units[target]));
    let cluster_weapon = is_cluster(b, attacker, weapon);
    let (mut tn, mut cluster, mut note) = (0, 0, String::new());
    // Core p.70: no Artemis FCS bonus of any kind applies to an indirect fire attack
    let indirect = b.indirect_pairs.contains(&(attacker, target));
    if is_atm(b, attacker, weapon) {
        if !indirect && !artemis_blocked(&b.units[attacker], &b.units[target]) {
            cluster = ATM_CLUSTER;
            note = "ATM Artemis".into();
        }
    } else if munition == "narc" && homing_working(&b.units[attacker], &b.units[target]) {
        tn = NARC_TN;
        cluster = if cluster_weapon { NARC_CLUSTER } else { 0 };
        note = "Narc homing".into();
    } else if munition == "semiguided" {
        // SEMI-GUIDED LRMs (Core p.193; N10): -1 on the Cluster Hits Table, unless the target is designated by TAG; then, fired
        // directly, they ignore partial cover, take 2 off the target hex's terrain modifier and +2 on the Cluster Hits Table.
        // (Indirect: the target hex's terrain and the spotter's modifiers would go - NOT BUILT: indirect SG fires as plain.)
        if b.units[target].tag_designated.is_some() && !indirect {
            let (cover, hex_mod) = semi_guided_relief(b, attacker, target);
            tn = -(cover + hex_mod);
            cluster = if cluster_weapon { 2 } else { 0 };
            note = format!("semi-guided on TAG: -{} to hit, +2 cluster", cover + hex_mod);
        } else {
            cluster = if cluster_weapon { -1 } else { 0 };
            note = "semi-guided, no TAG: -1 cluster".into();
        }
    } else if munition == "artemis4" || munition == "artemis5" {
        let kind: i64 = munition[munition.len() - 1..].parse().unwrap();
        if !indirect && artemis_kind(&b.units[attacker], weapon) == Some(kind) && !artemis_blocked(&b.units[attacker], &b.units[target]) {
            let (t, c) = artemis_bonus(kind);
            tn = t;
            cluster = c;
            note = format!("Artemis {}", if kind == 4 { "IV" } else { "V" });
        }
    }
    if !lock {
        note = format!("{}{}", if note.is_empty() { String::new() } else { format!("{}, ", note) }, "Angel ECM: no Streak lock");
    }
    FireControl { munition: munition.to_string(), tn, cluster, streak_lock: lock, note }
}

/// A homing pod's worth to `owner` (one-turn gain of its Narc-capable launchers).
pub fn pod_value(b: &mut Battle, owner: UnitId, target: UnitId, distance: i64, pre_tn: i64, adjust: &dyn crate::fire_modes::TnAdjust) -> f64 {
    use crate::fire_modes::{Planner, ShotPlan};
    let owner_side = b.units[owner].side_name.clone().unwrap_or_default();
    if narc_blocked(&b.units[target]) || live_pod_exists(&b.units[target], &owner_side, false) {
        return 0.0;
    }
    let mut planner = Planner::new(owner, target, adjust, 0.0, Default::default(), None);
    let mut blocked = crate::ammo::unavailable_weapons(&b.units[owner]);
    blocked.extend(crate::fire_modes::jammed_ids(&b.units[owner]));
    let mut total = 0.0;
    for w in crate::damage_resolution::get_weapons(&b.units[owner]) {
        if blocked.contains(&w) || b.units[owner].items[w].damage_type.as_deref() != Some("Missile") || is_narc(b, owner, w) {
            continue;
        }
        let plans = planner.kinds(b, w);
        let narc: Vec<&ShotPlan> = plans.iter().filter(|p| p.munition() == "narc").collect();
        if narc.is_empty() {
            continue;
        }
        let mut now = 0.0f64;
        let mut first = true;
        for p in &plans {
            if let Some(v) = planner.value(b, w, p, distance, pre_tn) {
                if first || v.0 > now {
                    now = v.0;
                    first = false;
                }
            }
        }
        if first {
            now = 0.0;
        }
        let mut homing = narc[0].clone();
        homing.guidance = FireControl { munition: "narc".into(), tn: NARC_TN, cluster: if is_cluster(b, owner, w) { NARC_CLUSTER } else { 0 }, streak_lock: narc[0].guidance.streak_lock, note: "Narc homing".into() };
        if let Some(got) = planner.value(b, w, &homing, distance, pre_tn) {
            total += 0.0f64.max(got.0 - now);
        }
    }
    total
}

/// One log line naming each fired weapon's shot plan, when it isn't plain.
pub fn log_controls(b: &mut Battle, name: &str, plans: &[(ItemId, crate::fire_modes::ShotPlan)], weapons: &[ItemId], u: UnitId) {
    let mut notes: Vec<String> = Vec::new();
    for w in weapons {
        if let Some((_, p)) = plans.iter().find(|(x, _)| x == w) {
            let n = p.note();
            if !n.is_empty() {
                notes.push(format!("{}: {}", b.units[u].items[*w].name, n));
            }
        }
    }
    notes.sort();
    notes.dedup();
    if !notes.is_empty() {
        b.log(format!("    [{} fire control] {}", name, notes.join("; ")));
    }
}

/// What semi-guided missiles on a TAG-designated target take off (Core p.193): the partial cover modifier of the line, and up
/// to 2 of the target hex's own terrain modifier (N10).
fn semi_guided_relief(b: &Battle, attacker: UnitId, target: UnitId) -> (i64, i64) {
    let xy = |u: UnitId| b.units[u].hex.as_deref().and_then(|h| crate::hex_geometry::parse_hex_label(h).ok());
    let (Some(a), Some(t)) = (xy(attacker), xy(target)) else { return (0, 0) };
    let h = (crate::attack_resolution::los_height(&b.units[attacker]), crate::attack_resolution::los_height(&b.units[target]));
    let cover = crate::los::trace_los_path(a, t, &b.board, h.0, h.1).ok().and_then(|tr| tr.steps.last().map(|s| s.partial_cover)).unwrap_or(0);
    let hex_mod = crate::los::target_hex_modifier(t, &b.board).unwrap_or(0).clamp(0, 2);
    (cover, hex_mod)
}
