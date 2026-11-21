// Translated from INTEGRATION__fire_modes.py (session 22). First part: the ammunition-kind tables and the weapon
// predicates ammo needs; the shot plan / planner follow with electronics.
use crate::battle::{Battle, UnitId};
use crate::equipment::ItemId;
use crate::weapon_rules::canonical_name;

/// (damage per missile, grouping, range {min, short, medium, long})
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct KindRange {
    pub min: i64,
    pub short: i64,
    pub medium: i64,
    pub long: i64,
}

/// MML_KINDS: kind -> (damage per missile, grouping, range)
pub fn mml_kind(kind: &str) -> Option<(i64, i64, KindRange)> {
    match kind {
        "lrm" => Some((1, 5, KindRange { min: 6, short: 7, medium: 14, long: 21 })),
        "srm" => Some((2, 2, KindRange { min: 0, short: 3, medium: 6, long: 9 })),
        _ => None,
    }
}

/// MML_SHOTS[rack][kind]
pub fn mml_shots(rack: Option<i64>, kind: &str) -> Option<i64> {
    let (l, s) = match rack? {
        3 => (40, 33),
        5 => (24, 20),
        7 => (17, 14),
        9 => (13, 11),
        _ => return None,
    };
    match kind {
        "lrm" => Some(l),
        "srm" => Some(s),
        _ => None,
    }
}

/// ATM_KINDS: kind -> (damage per missile, range)
pub fn atm_kind(kind: &str) -> Option<(i64, KindRange)> {
    match kind {
        "standard" => Some((2, KindRange { min: 4, short: 5, medium: 10, long: 15 })),
        "er" => Some((1, KindRange { min: 4, short: 9, medium: 18, long: 27 })),
        "he" => Some((3, KindRange { min: 0, short: 3, medium: 6, long: 9 })),
        "imp" => Some((1, KindRange { min: 0, short: 3, medium: 6, long: 9 })),
        "iiw" => Some((0, KindRange { min: 4, short: 5, medium: 10, long: 15 })),
        _ => None,
    }
}

pub const LBX_CLUSTER_TN: i64 = -1;
pub const RAC_JAM_AT: [(i64, i64); 3] = [(6, 4), (4, 3), (2, 2)];
pub const UNJAM_TN_MODIFIER: i64 = 3;
pub const APOLLO_CLUSTER: i64 = 1;

pub fn is_ultra(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    canonical_name(b, u, w).contains("ULTRAAC")
}
pub fn is_rotary(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    canonical_name(b, u, w).contains("ROTARYAC")
}
pub fn is_lbx(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    canonical_name(b, u, w).contains("LBXAC")
}
pub fn is_mml(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    canonical_name(b, u, w).contains("MML")
}
pub fn is_mrm(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    canonical_name(b, u, w).starts_with("MRM")
}
pub fn max_shots(b: &mut Battle, u: UnitId, w: ItemId) -> i64 {
    if is_ultra(b, u, w) {
        2
    } else if is_rotary(b, u, w) {
        6
    } else {
        1
    }
}

// =============================================================================================================
// The shot plan, damage / range / column / grouping per plan, options and the Planner.
// =============================================================================================================
use crate::fasthash::{HashMap, HashSet};

use crate::ammo;
use crate::damage_resolution::{cluster_hits_count, get_weapons};
use crate::electronics::{self, FireControl};
use crate::equipment::{Slot, WeaponRange};
use crate::weapon_profiles as wp;
use crate::weapon_rules;

/// How one weapon fires this turn.
#[derive(Clone, Debug, PartialEq)]
pub struct ShotPlan {
    pub guidance: FireControl,
    pub kind: String,
    pub shots: i64,
    pub apollo: bool,
    pub bracket: String,
}

impl ShotPlan {
    pub fn plain() -> ShotPlan {
        ShotPlan { guidance: FireControl::plain(), kind: String::new(), shots: 1, apollo: false, bracket: String::new() }
    }
    pub fn with_kind(kind: &str) -> ShotPlan {
        ShotPlan { kind: kind.to_string(), ..ShotPlan::plain() }
    }
    pub fn munition(&self) -> &str {
        &self.guidance.munition
    }
    pub fn hex_attack(&self) -> bool {
        self.kind == "saturation" || self.kind == "artillery" || self.kind == "distant"
    }
    pub fn tn(&self) -> i64 {
        let mut tn = self.guidance.tn + if self.kind == "cluster" { LBX_CLUSTER_TN } else { 0 };
        if BOMBAST_KINDS_LIST.contains(&self.kind.as_str()) {
            tn += wp::bombast(&self.kind).1;
        }
        if self.kind == "artillery" || self.kind == "distant" {
            tn += wp::ARROW_TN;
        }
        tn
    }
    pub fn note(&self) -> String {
        let mut parts: Vec<String> = Vec::new();
        if !self.guidance.note.is_empty() {
            parts.push(self.guidance.note.clone());
        }
        if !self.kind.is_empty() {
            parts.push(match self.kind.as_str() {
                "cluster" => "LB-X cluster rounds".to_string(),
                "er" => "ATM ER".to_string(),
                "he" => "ATM HE".to_string(),
                "imp" => "iATM IMP".to_string(),
                "iiw" => "iATM IIW (inferno)".to_string(),
                "lrm" => "MML LRM rounds".to_string(),
                "srm" => "MML SRM rounds".to_string(),
                "saturation" => "Apollo saturation".to_string(),
                "artillery" => "artillery at the hex".to_string(),
                "distant" => "distant artillery at the hex, lands next turn".to_string(),
                "array" => format!("array of {}", self.shots),
                "homing" => "homing at the TAG-designated target".to_string(),
                other => format!("{} damage", other),
            });
        }
        if self.shots > 1 && self.kind != "array" {
            parts.push(format!("rapid fire x{}", self.shots));
        }
        if self.apollo && self.kind != "saturation" {
            parts.push("Apollo".to_string());
        }
        parts.join(", ")
    }
}

const BOMBAST_KINDS_LIST: [&str; 3] = ["8", "12", "16"];

pub fn is_inferno(plan: &ShotPlan) -> bool {
    plan.munition() == "inferno" || plan.kind == "iiw"
}

/// A weapon's range for a plan: {min, short, medium, long} and an optional "floor" (Arrow IV / homing).
#[derive(Clone, Debug, PartialEq)]
pub struct RangeSpec {
    pub min: Option<i64>,
    pub short: i64,
    pub medium: i64,
    pub long: i64,
    pub floor: Option<i64>,
}

impl From<KindRange> for RangeSpec {
    fn from(k: KindRange) -> RangeSpec {
        RangeSpec { min: Some(k.min), short: k.short, medium: k.medium, long: k.long, floor: None }
    }
}
impl From<&WeaponRange> for RangeSpec {
    fn from(w: &WeaponRange) -> RangeSpec {
        RangeSpec { min: w.min, short: w.short, medium: w.medium, long: w.long, floor: None }
    }
}

/// Damage of one missile / shot / pellet / slug.
pub fn damage_per(b: &mut Battle, u: UnitId, w: ItemId, plan: &ShotPlan) -> Option<i64> {
    if is_inferno(plan) {
        return Some(0);
    }
    if plan.kind == "cluster" || wp::is_hag(b, u, w) || wp::is_mpod(b, u, w) {
        return Some(1);
    }
    if is_mml(b, u, w) {
        if let Some((d, ..)) = mml_kind(&plan.kind) {
            return Some(d);
        }
    }
    if canonical_name(b, u, w).contains("ATM") {
        let k = if plan.kind.is_empty() { "standard" } else { plan.kind.as_str() };
        return Some(atm_kind(k).unwrap_or_else(|| atm_kind("standard").unwrap()).0);
    }
    if BOMBAST_KINDS_LIST.contains(&plan.kind.as_str()) {
        return Some(wp::bombast(&plan.kind).0);
    }
    if plan.kind == "homing" {
        return Some(wp::homing_damage(b, u, w));
    }
    if wp::is_arrow(b, u, w) {
        return Some(wp::arrow_damage(b, u, w));
    }
    if wp::is_infantry_pod(b, u, w) {
        return Some(0);
    }
    if let Some(table) = wp::variable_damage(b, u, w) {
        let key = if plan.bracket.is_empty() { "short" } else { plan.bracket.as_str() };
        return Some(table.iter().find(|(k, _)| *k == key).map_or(0, |(_, v)| *v) + crate::capacitor::charge_bonus(b, u, w));
    }
    if wp::is_rifle(b, u, w) {
        return Some(0.max(b.units[u].items[w].damage_per_shot.unwrap_or(0) + wp::RIFLE_VS_MECH));
    }
    b.units[u].items[w].damage_per_shot
}

pub fn weapon_range(b: &mut Battle, u: UnitId, w: ItemId, plan: &ShotPlan) -> Option<RangeSpec> {
    if is_mml(b, u, w) {
        if let Some((_, _, r)) = mml_kind(&plan.kind) {
            return Some(r.into());
        }
    }
    if canonical_name(b, u, w).contains("ATM") {
        if let Some((_, r)) = atm_kind(&plan.kind) {
            return Some(r.into());
        }
    }
    if plan.kind == "homing" {
        return Some(RangeSpec { min: Some(0), short: wp::HOMING_REACH, medium: wp::HOMING_REACH, long: wp::HOMING_REACH, floor: Some(1) });
    }
    if plan.kind == "distant" {
        // p.182: 18 hexes or more, no upper limit on the board (artillery.rs)
        let reach = crate::artillery::DISTANT_REACH;
        return Some(RangeSpec { min: Some(0), short: reach, medium: reach, long: reach, floor: Some(crate::artillery::DISTANT_MIN) });
    }
    if wp::is_arrow(b, u, w) {
        let (lo, hi) = wp::ARROW_RANGE;
        return Some(RangeSpec { min: Some(0), short: hi, medium: hi, long: hi, floor: Some(lo) });
    }
    if wp::is_mga(b, u, w) {
        let guns = b.units[u].items[w].mga_guns.clone().unwrap_or_default();
        return match guns.first() {
            Some(g) => b.units[u].items[*g].weapon_range.as_ref().map(|r| r.into()),
            None => b.units[u].items[w].weapon_range.as_ref().map(|r| r.into()),
        };
    }
    b.units[u].items[w].weapon_range.as_ref().map(|r| r.into())
}

/// Cluster Hits Table column, or None for a single hit.
pub fn column(b: &mut Battle, u: UnitId, w: ItemId, plan: &ShotPlan) -> Option<i64> {
    if wp::is_mga(b, u, w) {
        return Some(plan.shots);
    }
    if plan.shots > 1 {
        return Some(plan.shots);
    }
    if plan.kind == "cluster" {
        return b.units[u].items[w].damage_per_shot;
    }
    if wp::is_hag(b, u, w) {
        return Some(wp::hag_size(b, u, w));
    }
    if wp::is_mpod(b, u, w) {
        let key = if plan.bracket.is_empty() { "short" } else { plan.bracket.as_str() };
        return Some(wp::mpod_column_by_bracket(key));
    }
    if wp::is_arrow(b, u, w) {
        return None;
    }
    if weapon_rules::is_cluster(b, u, w) {
        return b.units[u].items[w].rack_size;
    }
    None
}

pub fn grouping(b: &mut Battle, u: UnitId, w: ItemId, plan: &ShotPlan) -> i64 {
    if plan.kind == "saturation" {
        return wp::AREA_GROUPING;
    }
    if wp::is_hag(b, u, w) {
        return wp::HAG_GROUPING;
    }
    if plan.shots > 1 || plan.kind == "cluster" || wp::is_mpod(b, u, w) {
        return damage_per(b, u, w, plan).unwrap_or(0);
    }
    if is_mml(b, u, w) {
        if let Some((_, g, _)) = mml_kind(&plan.kind) {
            return g;
        }
    }
    weapon_rules::grouping_size(b, u, w)
}

pub fn cluster_modifier(b: &mut Battle, u: UnitId, w: ItemId, plan: &ShotPlan) -> i64 {
    if wp::is_mga(b, u, w) {
        return wp::MGA_CLUSTER;
    }
    let mut m = plan.guidance.cluster + if plan.shots == 1 { weapon_rules::cluster_roll_modifier(b, u, w) } else { 0 };
    if wp::is_hag(b, u, w) {
        let key = if plan.bracket.is_empty() { "medium" } else { plan.bracket.as_str() };
        m += wp::hag_cluster_by_bracket(key);
    }
    m + if plan.apollo { APOLLO_CLUSTER } else { 0 }
}

pub fn heat(b: &mut Battle, u: UnitId, w: ItemId, plan: &ShotPlan) -> i64 {
    if BOMBAST_KINDS_LIST.contains(&plan.kind.as_str()) {
        return wp::bombast(&plan.kind).2;
    }
    b.units[u].items[w].heat.unwrap_or(0) * if wp::is_mga(b, u, w) { 1 } else { plan.shots }
}

/// p.70: no rapid fire, Cluster, area-effect or Flak aimed shots.
pub fn aimable(b: &mut Battle, u: UnitId, w: ItemId, plan: &ShotPlan) -> bool {
    plan.shots == 1
        && plan.kind != "cluster"
        && !plan.hex_attack()
        && !weapon_rules::is_cluster(b, u, w)
        && !(wp::is_hag(b, u, w) || wp::is_mpod(b, u, w) || wp::is_mga(b, u, w) || wp::is_arrow(b, u, w) || wp::is_art_cannon(b, u, w))
}

pub fn tc_eligible(b: &mut Battle, u: UnitId, w: ItemId, plan: &ShotPlan) -> bool {
    if plan.hex_attack() || plan.kind == "cluster" || wp::is_mpod(b, u, w) || wp::is_arrow(b, u, w) || wp::is_mga(b, u, w) || wp::is_art_cannon(b, u, w) {
        return false;
    }
    wp::is_hag(b, u, w) || weapon_rules::targeting_computer_eligible(b, u, w)
}

pub fn range_mod(b: &mut Battle, u: UnitId, w: ItemId, plan: &ShotPlan, distance: i64) -> Option<i64> {
    let wr = weapon_range(b, u, w, plan)?;
    if let Some(floor) = wr.floor {
        return if floor <= distance && distance <= wr.long { Some(0) } else { None };
    }
    let bracket = if distance <= wr.short {
        crate::combat::RANGE_MOD_SHORT
    } else if distance <= wr.medium {
        crate::combat::RANGE_MOD_MEDIUM
    } else if distance <= wr.long {
        crate::combat::RANGE_MOD_LONG
    } else {
        return None;
    };
    Some(bracket + crate::weapon_selection::min_range_penalty(wr.min.unwrap_or(0), distance))
}

pub fn bracket(b: &mut Battle, u: UnitId, w: ItemId, plan: &ShotPlan, distance: i64) -> Option<&'static str> {
    let wr = weapon_range(b, u, w, plan)?;
    if distance <= wr.short {
        Some("short")
    } else if distance <= wr.medium {
        Some("medium")
    } else if distance <= wr.long {
        Some("long")
    } else {
        None
    }
}

/// E[hits] on `col` with `modifier`; engaged = an AMS took it (below 2 = none, p.206), else the roll clamps to 2-12.
/// thirds: E[round(hits / 3)] (Apollo saturation, p.197).
pub fn expected_hits(b: &Battle, col: i64, modifier: i64, engaged: bool, thirds: bool) -> f64 {
    let mut total = 0.0;
    for (roll, p) in crate::expected_damage::p_2d6_exact() {
        let r = roll + modifier;
        if engaged && r < 2 {
            continue;
        }
        let hits = cluster_hits_count(b, col, 2.max(12.min(r))).unwrap();
        total += p * if thirds { third(hits) as f64 } else { hits as f64 };
    }
    total
}

/// hits / 3, rounding normally (.5 up).
pub fn third(hits: i64) -> i64 {
    (hits as f64 / 3.0 + 0.5) as i64
}

/// E[damage | hit] for this plan; with ams_engaged, as if the target's AMS took it.
pub fn expected_hit(b: &mut Battle, u: UnitId, w: ItemId, plan: &ShotPlan, ams_engaged: bool) -> f64 {
    let dmg: f64 = if is_inferno(plan) {
        crate::advanced_weapons::INFERNO_HEAT_PER_MISSILE as f64 * b.cfg.f("TARGET_HEAT_WORTH")
    } else {
        damage_per(b, u, w, plan).unwrap_or(0) as f64
    };
    if dmg == 0.0 {
        return 0.0;
    }
    let Some(col) = column(b, u, w, plan) else {
        if ams_engaged {
            return dmg * (crate::ams::SINGLE_MISSILE_KILL - 1) as f64 / 6.0;
        }
        return dmg;
    };
    if weapon_rules::is_streak(b, u, w) && plan.guidance.streak_lock {
        if ams_engaged {
            return dmg * cluster_hits_count(b, col, crate::ams::STREAK_RESULT).unwrap() as f64;
        }
        return dmg * col as f64;
    }
    let mod_ = cluster_modifier(b, u, w, plan) + if ams_engaged { crate::ams::CLUSTER_MODIFIER } else { 0 };
    dmg * expected_hits(b, col, mod_, ams_engaged, plan.kind == "saturation")
}

// ---- options ---------------------------------------------------------------------------------------------------
pub fn apollo_live(mech: &crate::mech_state::Mech, weapon: ItemId) -> bool {
    match mech.items[weapon].apollo {
        Some(link) => !electronics::dead(mech).contains(&link),
        None => false,
    }
}

/// Once per battle: link Apollo FCS to MRMs, clear jams and unjam declarations.
pub fn attach(b: &mut Battle, u: UnitId) {
    b.units[u].unjamming = Vec::new();
    wp::link_arrays(b, u);
    let mut seen: HashSet<ItemId> = HashSet::default();
    let mut fcs_by_loc: crate::fasthash::IndexMap<String, Vec<ItemId>> = crate::fasthash::IndexMap::default();
    let mut mrm_by_loc: crate::fasthash::IndexMap<String, Vec<ItemId>> = crate::fasthash::IndexMap::default();
    let locs: Vec<String> = b.units[u].crits.keys().cloned().collect();
    for loc in &locs {
        let slots: Vec<ItemId> = b.units[u].crits[loc].iter().filter_map(|s| if let Slot::Item(i) = s { Some(*i) } else { None }).collect();
        for s in slots {
            if !seen.insert(s) {
                continue;
            }
            let cat = b.units[u].items[s].category.clone();
            if cat.as_deref() != Some("ammo") && b.units[u].items[s].name.to_uppercase().contains("APOLLO") {
                fcs_by_loc.entry(loc.clone()).or_default().push(s);
            } else if cat.as_deref() == Some("weapon") && is_mrm(b, u, s) {
                mrm_by_loc.entry(loc.clone()).or_default().push(s);
            }
            if cat.as_deref() == Some("weapon") {
                b.units[u].items[s].jammed = Some(false);
            }
        }
    }
    let (mut left_f, mut left_w): (Vec<ItemId>, Vec<ItemId>) = (vec![], vec![]);
    for loc in &locs {
        let f = fcs_by_loc.get(loc).cloned().unwrap_or_default();
        let w = mrm_by_loc.get(loc).cloned().unwrap_or_default();
        for (a, m) in f.iter().zip(w.iter()) {
            b.units[u].items[*m].apollo = Some(*a);
        }
        left_f.extend(f.iter().skip(w.len()));
        left_w.extend(w.iter().skip(f.len()));
    }
    for (a, m) in left_f.iter().zip(left_w.iter()) {
        b.units[u].items[*m].apollo = Some(*a);
    }
}

/// {(munition, kind)} of the live bins that feed `weapon` ({("standard", "")} for a weapon without ammo), sorted.
pub fn bin_kinds(mech: &crate::mech_state::Mech, weapon: ItemId) -> Vec<(String, String)> {
    if !mech.items[weapon].needs_ammo.unwrap_or(false) {
        return vec![("standard".into(), String::new())];
    }
    let mut out: Vec<(String, String)> = ammo::bins_for(mech, weapon)
        .into_iter()
        .map(|i| (mech.items[i].munition.clone().unwrap_or_else(|| "standard".into()), mech.items[i].kind.clone().unwrap_or_default()))
        .collect();
    out.sort();
    out.dedup();
    // Core p.192: a weapon using caseless ammunition cannot use any other
    if out.iter().any(|(m, _)| m == "caseless") {
        out.retain(|(m, _)| m == "caseless");
    }
    out
}

/// Does this autocannon carry a special round (armor-piercing, precision, caseless; N10)? Then its shot is planned.
pub fn has_special_ac_round(mech: &crate::mech_state::Mech, weapon: ItemId) -> bool {
    mech.items[weapon].needs_ammo.unwrap_or(false) && bin_kinds(mech, weapon).iter().any(|(m, _)| matches!(m.as_str(), "ap" | "precision" | "caseless"))
}

pub fn rounds_left(mech: &crate::mech_state::Mech, weapon: ItemId, munition: &str, kind: &str) -> f64 {
    if !mech.items[weapon].needs_ammo.unwrap_or(false) {
        return f64::INFINITY;
    }
    let bins: Vec<ItemId> = ammo::bins_for(mech, weapon)
        .into_iter()
        .filter(|i| mech.items[*i].munition.as_deref().unwrap_or("standard") == munition && mech.items[*i].kind.as_deref().unwrap_or("") == kind)
        .collect();
    if bins.iter().any(|i| mech.items[*i].shots_left.is_none()) {
        return f64::INFINITY;
    }
    bins.iter().map(|i| mech.items[*i].shots_left.unwrap()).sum::<i64>() as f64
}

/// The machine guns `array` can fire now: each needs a round of its own.
pub fn mga_firing_guns(b: &mut Battle, attacker: UnitId, array: ItemId) -> Vec<ItemId> {
    let mut left: Vec<(Option<String>, Option<ItemId>, f64)> = Vec::new();
    let mut out = Vec::new();
    for g in wp::mga_guns(b, attacker, array) {
        let m = &b.units[attacker];
        let (key_s, key_i) = if m.items[g].needs_ammo.unwrap_or(false) { (m.items[g].ammo_key.clone(), None) } else { (None, Some(g)) };
        let idx = match left.iter().position(|(s, i, _)| *s == key_s && *i == key_i) {
            Some(i) => i,
            None => {
                left.push((key_s.clone(), key_i, rounds_left(m, g, "standard", "")));
                left.len() - 1
            }
        };
        if left[idx].2 >= 1.0 {
            left[idx].2 -= 1.0;
            out.push(g);
        }
    }
    out
}

/// Mark off one round for each of the first `shots` guns that can fire; returns the last bin's log note.
pub fn take_array_rounds(b: &mut Battle, attacker: UnitId, array: ItemId, shots: i64) -> String {
    let guns = mga_firing_guns(b, attacker, array);
    let mut last = String::new();
    for g in guns.into_iter().take(shots.max(0) as usize) {
        last = ammo::take(b, attacker, g, Some("standard"), Some("")).0;
    }
    last
}

/// Every ammunition kind / guidance / Apollo mode `weapon` could fire now, as ShotPlans with 1 shot.
pub fn kind_options(b: &mut Battle, attacker: UnitId, w: ItemId, target: UnitId) -> Vec<ShotPlan> {
    if electronics::is_narc(b, attacker, w) {
        let mut kinds: Vec<String> = bin_kinds(&b.units[attacker], w).into_iter().map(|(m, _)| m).collect();
        kinds.sort();
        kinds.dedup();
        if kinds.is_empty() {
            kinds = vec!["homing".into()];
        }
        return kinds.into_iter().map(|m| ShotPlan { guidance: FireControl { munition: m, ..FireControl::plain() }, ..ShotPlan::plain() }).collect();
    }
    if wp::is_bombast(b, attacker, w) {
        return BOMBAST_KINDS_LIST.iter().map(|k| ShotPlan::with_kind(k)).collect();
    }
    if wp::is_arrow(b, attacker, w) {
        let have = bin_kinds(&b.units[attacker], w);
        let mut plans = Vec::new();
        if have.contains(&("standard".to_string(), String::new())) {
            plans.push(ShotPlan::with_kind("artillery"));
            // distant fire (18+ hexes, lands next turn; p.182): whether to use it is a bot decision (a stub for now)
            let far = crate::forces::distance(b, attacker, target).is_some_and(|d| d >= crate::artillery::DISTANT_MIN);
            // Princess / CASPAR aim by MegaMek's ArtilleryTargetingControl (princess_artillery.rs); Hydra borrows that aim
            // (2026-11-21: it reads no Princess setting, and Hydra borrows its tools as it borrows Gladiator's); Gladiator: the stub
            let offer = if b.units[attacker].is_princess_family() || b.units[attacker].bot == "hydra" {
                let dmg = damage_per(b, attacker, w, &ShotPlan::with_kind("distant")).unwrap_or(0);
                far && crate::princess_artillery::distant_aim(b, attacker, w, target, dmg).is_some()
            } else {
                far && crate::stubs::stub_distant_artillery(b, attacker, target)
            };
            if offer {
                plans.push(ShotPlan::with_kind("distant"));
            }
        }
        if have.contains(&("homing".to_string(), String::new())) && b.units[target].tag_designated.is_some() {
            plans.push(ShotPlan { guidance: FireControl { munition: "homing".into(), note: "homing".into(), ..FireControl::plain() }, ..ShotPlan::with_kind("homing") });
        }
        return plans;
    }
    if wp::is_mga(b, attacker, w) {
        let guns = mga_firing_guns(b, attacker, w);
        return if guns.is_empty() { vec![] } else { vec![ShotPlan { shots: guns.len() as i64, ..ShotPlan::with_kind("array") }] };
    }
    let mut kinds = bin_kinds(&b.units[attacker], w);
    if kinds.is_empty() {
        kinds = vec![("standard".into(), String::new())];
    }
    let mut out = Vec::new();
    for (munition, kind) in kinds {
        if is_mml(b, attacker, w) && mml_kind(&kind).is_none() {
            continue;
        }
        let guidance = electronics::control_for(b, attacker, w, target, &munition);
        let apollo = is_mrm(b, attacker, w) && apollo_live(&b.units[attacker], w);
        out.push(ShotPlan { guidance: guidance.clone(), kind: kind.clone(), shots: 1, apollo, bracket: String::new() });
        if apollo {
            out.push(ShotPlan { guidance, kind: "saturation".into(), shots: 1, apollo: true, bracket: String::new() });
        }
    }
    out
}

/// Shot counts the weapon can fire with this plan's ammunition.
pub fn rate_options(b: &mut Battle, attacker: UnitId, w: ItemId, plan: &ShotPlan) -> Vec<i64> {
    if wp::is_mga(b, attacker, w) {
        return vec![plan.shots];
    }
    let ms = max_shots(b, attacker, w);
    let left = rounds_left(&b.units[attacker], w, plan.munition(), &plan.kind);
    let top = ms.min(left.min(ms as f64) as i64);
    (1..=top.max(1)).collect()
}

/// Attack roll at or below which a Rotary AC jams (0 = can't jam).
pub fn jam_threshold(plan: &ShotPlan) -> i64 {
    for (at_least, roll) in RAC_JAM_AT {
        if plan.shots >= at_least {
            return roll;
        }
    }
    0
}

pub fn jammed_ids(mech: &crate::mech_state::Mech) -> HashSet<ItemId> {
    get_weapons(mech).into_iter().filter(|w| mech.items[*w].jammed.unwrap_or(false)).collect()
}

// ---- pricing / planner -------------------------------------------------------------------------------------------
/// What attack_resolution's `tn_adjuster` (and water.range_adjuster around it) offers the Planner.
pub trait TnAdjust {
    fn adjust(&self, b: &mut Battle, w: ItemId, bracket: Option<&str>, plan: Option<&ShotPlan>) -> i64;
    fn underwater_ids(&self) -> Option<&HashSet<ItemId>>;
}

/// Weapons the Planner prices (anything that isn't a plain single shot).
pub fn special(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    // the name and damage type decide it: kept on the item after the first asking
    if let Some(s) = b.units[u].items[w].memo.special {
        return s;
    }
    let s = special_by_name(b, u, w);
    b.units[u].items[w].memo.special = Some(s);
    s
}

fn special_by_name(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    let dt_missile = b.units[u].items[w].damage_type.as_deref() == Some("Missile");
    let cn = canonical_name(b, u, w);
    dt_missile
        || max_shots(b, u, w) > 1
        || is_lbx(b, u, w)
        || is_mml(b, u, w)
        || cn.contains("ATM")
        || has_profile(b, u, w)
        || wp::is_rifle(b, u, w)
        || wp::heat_causing(b, u, w)
        || wp::is_art_cannon(b, u, w)
        || cn.contains("TASER")
        || cn.contains("TSEMP")
        || cn.contains("NAIL")
        || cn.contains("RIVET")
        || has_special_ac_round(&b.units[u], w)
}

pub fn has_profile(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    if let Some(p) = b.units[u].items[w].memo.has_profile {
        return p;
    }
    let p = has_profile_by_name(b, u, w);
    b.units[u].items[w].memo.has_profile = Some(p);
    p
}

fn has_profile_by_name(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    is_mml(b, u, w)
        || wp::variable_damage(b, u, w).is_some()
        || wp::is_hag(b, u, w)
        || wp::is_mpod(b, u, w)
        || wp::is_bombast(b, u, w)
        || wp::is_arrow(b, u, w)
        || wp::is_mga(b, u, w)
        || wp::is_infantry_pod(b, u, w)
}

/// The adjuster a Planner reads: borrowed (a one-off planner) or shared (a long-lived one).
pub enum AdjustRef<'a> {
    Borrowed(&'a dyn TnAdjust),
    Shared(std::rc::Rc<dyn TnAdjust>),
}

impl<'a> std::ops::Deref for AdjustRef<'a> {
    type Target = dyn TnAdjust + 'a;
    fn deref(&self) -> &(dyn TnAdjust + 'a) {
        match self {
            AdjustRef::Borrowed(r) => *r,
            AdjustRef::Shared(r) => &**r,
        }
    }
}

/// Prices one attacker's special weapons against one target.
pub struct Planner<'a> {
    pub attacker: UnitId,
    pub target: UnitId,
    pub adjust: AdjustRef<'a>,
    pub ams_share: f64,
    pub pod_values: HashMap<ItemId, f64>,
    pub hex_offset: Option<i64>,
    kinds_cache: HashMap<ItemId, Vec<ShotPlan>>,
    memo: HashMap<(ItemId, i64, i64), Option<(f64, i64, ShotPlan)>>,
}

impl<'a> Planner<'a> {
    pub fn new(attacker: UnitId, target: UnitId, adjust: &'a dyn TnAdjust, ams_share: f64, pod_values: HashMap<ItemId, f64>, hex_offset: Option<i64>) -> Planner<'a> {
        Planner { attacker, target, adjust: AdjustRef::Borrowed(adjust), ams_share, pod_values, hex_offset, kinds_cache: HashMap::default(), memo: HashMap::default() }
    }

    /// A planner that shares its adjuster (movement scoring keeps one adjuster for many planners).
    pub fn new_shared(attacker: UnitId, target: UnitId, adjust: std::rc::Rc<dyn TnAdjust>, ams_share: f64) -> Planner<'static> {
        Planner { attacker, target, adjust: AdjustRef::Shared(adjust), ams_share, pod_values: HashMap::default(), hex_offset: None, kinds_cache: HashMap::default(), memo: HashMap::default() }
    }

    /// The bracket the shot's damage uses: an energy weapon firing from under water fires one bracket longer.
    pub fn damage_bracket(&self, w: ItemId, b: Option<&str>) -> String {
        match b {
            Some(br) if !br.is_empty() && self.adjust.underwater_ids().is_some_and(|ids| ids.contains(&w)) => crate::water::shifted_bracket(br).to_string(),
            Some(br) => br.to_string(),
            None => String::new(),
        }
    }

    pub fn kinds(&mut self, b: &mut Battle, w: ItemId) -> Vec<ShotPlan> {
        if let Some(k) = self.kinds_cache.get(&w) {
            return k.clone();
        }
        let k = kind_options(b, self.attacker, w, self.target);
        self.kinds_cache.insert(w, k.clone());
        k
    }

    /// (expected worth, TN) of firing `plan`, or None if out of range.
    pub fn value(&mut self, b: &mut Battle, w: ItemId, plan: &ShotPlan, distance: i64, pre_tn: i64) -> Option<(f64, i64)> {
        let (a, t) = (self.attacker, self.target);
        let rm = range_mod(b, a, w, plan, distance)?;
        let br = bracket(b, a, w, plan, distance);
        let mut plan = plan.clone();
        plan.bracket = self.damage_bracket(w, br);
        let tn;
        if plan.hex_attack() {
            let off = self.hex_offset?;
            tn = pre_tn + off + rm + self.adjust.adjust(b, w, None, Some(&plan)) + plan.tn();
        } else {
            tn = pre_tn + rm + self.adjust.adjust(b, w, br, Some(&plan)) + plan.tn() + area_immobile_fix(b, a, w, t);
        }
        if plan.kind == "homing" {
            if b.units[t].tag_designated.as_deref() == Some("hex") {
                return Some((wp::HOMING_AE as f64, wp::HOMING_TN));
            }
            let p = crate::combat::hit_probability(wp::HOMING_TN);
            return Some((p * wp::homing_damage(b, a, w) as f64 + (1.0 - p) * wp::HOMING_AE as f64, wp::HOMING_TN));
        }
        let p = crate::combat::hit_probability(tn);
        if plan.kind == "artillery" || plan.kind == "distant" || wp::is_art_cannon(b, a, w) {
            let near = crate::combat::hit_probability(tn - 2) - p;
            return Some((p * damage_per(b, a, w, &plan).unwrap_or(0) as f64 + near * wp::splash(b, a, w) as f64, tn));
        }
        if electronics::is_narc(b, a, w) {
            let worth = if plan.munition() == "explosive" {
                let key = b.units[a].items[w].ammo_key.clone().unwrap_or_default();
                ammo::explosive_pod_damage(&key).unwrap_or(0) as f64
            } else {
                self.pod_values.get(&w).copied().unwrap_or(0.0)
            };
            return Some((p * worth, tn));
        }
        Some((p * self.hit_worth(b, w, &plan), tn))
    }

    /// What one hit of an ordinary attack is worth: expected damage after the target's AMS, plus effects.
    fn hit_worth(&mut self, b: &mut Battle, w: ItemId, plan: &ShotPlan) -> f64 {
        let (a, t) = (self.attacker, self.target);
        let mut hit = expected_hit(b, a, w, plan, false);
        let cn = canonical_name(b, a, w);
        if self.ams_share != 0.0 && b.units[a].items[w].damage_type.as_deref() == Some("Missile") && !cn.contains("MORTAR") && hit > 0.0 {
            hit -= self.ams_share * (hit - expected_hit(b, a, w, plan, true));
        }
        hit += b.cfg.f("TARGET_HEAT_WORTH") * wp::expected_target_heat(b, a, w);
        if cn.contains("TASER") && b.units[t].mass.unwrap_or(0) <= 100 {
            hit += b.cfg.f("TASER_EFFECT_WORTH");
        }
        hit += self.advanced_worth(b, w, plan);
        hit
    }

    fn advanced_worth(&mut self, b: &mut Battle, w: ItemId, plan: &ShotPlan) -> f64 {
        use crate::advanced_weapons as adv;
        let (a, t) = (self.attacker, self.target);
        if adv::is_tsemp(b, a, w) {
            return if b.units[t].mass.unwrap_or(0) < adv::TSEMP_NO_EFFECT_TONS { b.cfg.f("TSEMP_EFFECT_WORTH") } else { 0.0 };
        }
        if adv::is_nail_gun(b, a, w) {
            return adv::nail_worth(&b.units[t], "front");
        }
        if plan.kind == "imp" && adv::imp_level(&b.units[t]) == 0 {
            let col = column(b, a, w, plan).unwrap_or(0);
            return b.cfg.f("IMP_EFFECT_WORTH") * adv::IMP_MAX.min(col.div_euclid(adv::IMP_PER_STEP)) as f64;
        }
        0.0
    }

    fn decide(&mut self, b: &mut Battle, w: ItemId, distance: i64, pre_tn: i64, warn: bool) -> Option<ShotPlan> {
        let a = self.attacker;
        let name = b.units[a].side_name.clone().unwrap_or_default();
        let mut options: Vec<(ShotPlan, f64)> = Vec::new();
        for plan in self.kinds(b, w) {
            if let Some(got) = self.value(b, w, &plan, distance, pre_tn) {
                let br = bracket(b, a, w, &plan, distance);
                let mut p = plan.clone();
                p.bracket = self.damage_bracket(w, br);
                options.push((p, got.0));
            }
        }
        if options.is_empty() {
            return None;
        }
        let mut plan = if options.len() > 1 { crate::stubs::stub_munition_choice(b, &name, w, a, &options, warn) } else { options[0].0.clone() };
        let rates = rate_options(b, a, w, &plan);
        if rates.len() > 1 {
            let mut priced: Vec<(i64, f64)> = Vec::new();
            for n in &rates {
                let mut p = plan.clone();
                p.shots = *n;
                priced.push((*n, self.value(b, w, &p, distance, pre_tn).unwrap().0));
            }
            plan.shots = crate::stubs::stub_rate_of_fire(b, &name, a, w, &priced, warn);
        }
        Some(plan)
    }

    /// (value, heat, plan) for weapon_selection, or None (can't fire here).
    pub fn plan_for(&mut self, b: &mut Battle, w: ItemId, distance: i64, pre_tn: i64) -> Option<(f64, i64, ShotPlan)> {
        let key = (w, distance, pre_tn);
        if let Some(got) = self.memo.get(&key) {
            return got.clone();
        }
        let got = match self.decide(b, w, distance, pre_tn, false) {
            None => None,
            Some(plan) => {
                let v = self.value(b, w, &plan, distance, pre_tn).unwrap().0;
                let h = heat(b, self.attacker, w, &plan);
                Some((v, h, plan))
            }
        };
        self.memo.insert(key, got.clone());
        got
    }

    /// The decision itself, at attack declaration: the stubs warn here.
    pub fn declare(&mut self, b: &mut Battle, w: ItemId, distance: i64, pre_tn: i64) -> ShotPlan {
        self.decide(b, w, distance, pre_tn, true).unwrap_or_else(ShotPlan::plain)
    }
}

/// Area-effect weapons never take the immobile -4 (p.181): undo it for an artillery cannon's normal attack on an
/// immobile target.
pub fn area_immobile_fix(b: &mut Battle, attacker: UnitId, w: ItemId, target: UnitId) -> i64 {
    if wp::is_art_cannon(b, attacker, w) && crate::mech_state::is_immobile(&b.units[target]) { 4 } else { 0 }
}

/// Fraction of missile hits a target AMS able to engage `target_capacity` attacks would take.
pub fn ams_share(b: &mut Battle, u: UnitId, target_capacity: i64, weapons: &[ItemId]) -> f64 {
    let mut n = 0;
    for &w in weapons {
        if b.units[u].items[w].damage_type.as_deref() == Some("Missile") && b.units[u].items[w].damage_per_shot.unwrap_or(0) > 0 && !canonical_name(b, u, w).contains("MORTAR") {
            n += 1;
        }
    }
    if target_capacity > 0 && n != 0 { 1.0f64.min(target_capacity as f64 / n as f64) } else { 0.0 }
}

// ---- RAC jams ------------------------------------------------------------------------------------------------------
/// Movement Phase start: which jammed RACs the mech tries to clear (stub_unjam).
pub fn declare_unjams(b: &mut Battle, u: UnitId) {
    b.units[u].unjamming = Vec::new();
    if b.units[u].shutdown {
        return;
    }
    // T16 step 2: Princess / CASPAR decide after the move is chosen (`princess_modern::rank` -> `princess_declare_unjam`)
    if b.units[u].is_princess_family() {
        return;
    }
    let mut picked = Vec::new();
    let name = b.units[u].side_name.clone().unwrap_or_default();
    for w in get_weapons(&b.units[u]) {
        if b.units[u].items[w].jammed.unwrap_or(false) {
            let prone = b.units[u].prone;
            let wname = b.units[u].items[w].name.clone();
            if crate::stubs::stub_unjam(b, &name, &wname, prone) {
                picked.push(w);
            }
        }
    }
    b.units[u].unjamming = picked.clone();
    if !picked.is_empty() {
        let names: Vec<String> = picked.iter().map(|w| b.units[u].items[*w].name.clone()).collect();
        b.log(format!("  [Movement] {} tries to unjam {} (stand still or walk only, p.183).", name, crate::damage_resolution::py_str_list(&names)));
    }
}

/// T16 step 2: movement is limited to Stand Still / Walk while the unit has declared an unjam, and, for a Princess-family
/// unit, whenever it has a jammed weapon it could try to clear (MegaMek PathRanker: with `canUnjamRAC` every path that
/// runs or jumps is INADVISABLE, whether or not the unjam is then attempted). Never while prone (as `stub_unjam`).
pub fn walk_only_for_unjam(m: &crate::mech_state::Mech) -> bool {
    !m.unjamming.is_empty() || (m.is_princess_family() && !m.shutdown && !m.prone && !jammed_ids(m).is_empty())
}

/// MegaMek Princess.unjamRAC (embellishPath): a chosen path that stays within walking MP gets an unjam step appended when
/// the path's expected damage is under 5 (`expectedDamage >= 5` means fire instead). `path_mode` is the chosen move's mode;
/// the unjam is then tried at the end of the Ranged Attack Phase like any other (`resolve_unjams`).
pub fn princess_declare_unjam(b: &mut Battle, u: UnitId, path_mode: &str, expected_damage: f64) {
    if !b.units[u].is_princess_family() || b.units[u].shutdown || b.units[u].prone {
        return;
    }
    let jammed: Vec<ItemId> = get_weapons(&b.units[u]).into_iter().filter(|w| jammed_ids(&b.units[u]).contains(w)).collect();
    if jammed.is_empty() || !matches!(path_mode, "Stand Still" | "Walk") || expected_damage >= 5.0 {
        return;
    }
    b.units[u].unjamming = jammed.clone();
    let name = b.units[u].side_name.clone().unwrap_or_default();
    let names: Vec<String> = jammed.iter().map(|w| b.units[u].items[*w].name.clone()).collect();
    b.log(format!("  [Movement] {} tries to unjam {} (MegaMek Princess.unjamRAC: expected damage {:.1} < 5; stand still or walk only, p.183).", name, crate::damage_resolution::py_str_list(&names), expected_damage));
}

/// End of the Ranged Attack Phase: Gunnery + 3 for each attempt (p.183).
pub fn resolve_unjams(b: &mut Battle, u: UnitId) {
    let attempts = b.units[u].unjamming.clone();
    for w in attempts {
        if !get_weapons(&b.units[u]).contains(&w) {
            continue;
        }
        let tn = b.units[u].gunnery + UNJAM_TN_MODIFIER;
        let roll = b.roll_2d6();
        if roll >= tn {
            b.units[u].items[w].jammed = Some(false);
        }
        let line = format!(
            "  [Ranged] {} unjam {}: needs {}, rolled {} -> {}.",
            b.units[u].side_name.clone().unwrap_or_default(),
            b.units[u].items[w].name,
            tn,
            roll,
            if roll >= tn { "cleared" } else { "still jammed" }
        );
        b.log(line);
    }
    b.units[u].unjamming = Vec::new();
}
