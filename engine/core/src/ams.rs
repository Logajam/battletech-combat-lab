// Translated from INTEGRATION__ams.py (session 22): Anti-Missile Systems (Core p.206).
use std::collections::HashMap;

use crate::ammo;
use crate::attack_resolution::{self as ar, DeclaredAttack, SideReport};
use crate::battle::{Battle, UnitId};
use crate::damage_resolution::get_weapons;
use crate::electronics;
use crate::equipment::ItemId;
use crate::fire_modes::{self, ShotPlan};
use crate::mech_state::{all_crew_unconscious, compute_heat_dissipation, Mech};
use crate::weapon_rules;
use crate::{arcs, hex_geometry};

pub const CLUSTER_MODIFIER: i64 = -4;
pub const STREAK_RESULT: i64 = 7;
pub const STREAK_CUT: i64 = 5;
pub const SINGLE_MISSILE_KILL: i64 = 4;
pub const ENGAGEMENTS_PER_TURN: i64 = 2;

/// A Type M weapon that does damage.
pub fn engageable(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    if weapon_rules::canonical_name(b, u, w).contains("MORTAR") {
        return false;
    }
    let it = &b.units[u].items[w];
    it.damage_type.as_deref() == Some("Missile") && it.damage_per_shot.unwrap_or(0) > 0
}

/// The mech's live AMS (destroyed ones drop out of get_weapons).
pub fn systems(b: &mut Battle, u: UnitId) -> Vec<ItemId> {
    let ws = get_weapons(&b.units[u]);
    ws.into_iter().filter(|w| weapon_rules::is_ams(b, u, *w)).collect()
}

/// p.206 (conscious crew) and p.104 (not shut down).
pub fn can_engage(m: &Mech) -> bool {
    !m.shutdown && !all_crew_unconscious(m)
}

/// The mech's live AMS whose firing arc holds `attacker_hex`, with the mech's declared twist / flip / turret (or `action`).
pub fn covering(b: &mut Battle, u: UnitId, attacker_hex: (i64, i64), action: Option<&crate::mech_state::ArcAction>) -> Vec<ItemId> {
    let found = systems(b, u);
    if found.is_empty() {
        return vec![];
    }
    let m = &b.units[u];
    let m_hex = hex_geometry::parse_hex_label(m.hex.as_deref().unwrap()).unwrap();
    let facing = hex_geometry::compass_to_facing(&m.facing).unwrap();
    let cur = arcs::current_action(m);
    let key = arcs::key_for(&arcs::arcs_between(m_hex, attacker_hex), facing, action.unwrap_or(&cur), &arcs::leg_offsets(m));
    let mut blocked = arcs::unavailable(m, &found, &ar::weapon_locations(m), &key);
    blocked.extend(ar::shielded_weapon_ids(m));
    found.into_iter().filter(|w| !blocked.contains(w)).collect()
}

/// AMS shots this AMS can still draw (inf for a laser AMS / unknown data).
pub fn shots_left(m: &Mech, w: ItemId) -> f64 {
    if !m.items[w].needs_ammo.unwrap_or(false) {
        return f64::INFINITY;
    }
    let bins = ammo::bins_for(m, w);
    if bins.iter().any(|i| m.items[*i].shots_left.is_none()) {
        return f64::INFINITY;
    }
    bins.iter().map(|i| m.items[*i].shots_left.unwrap()).sum::<i64>() as f64
}

/// How many attacks `ams_list` can engage this turn: 2 each, limited by the shots in the bins they share.
pub fn engagement_capacity(m: &Mech, ams_list: &[ItemId]) -> i64 {
    // group by ammo key (or the AMS itself), in first-seen order
    let mut groups: Vec<(Option<String>, Option<ItemId>, Vec<ItemId>)> = Vec::new();
    for &w in ams_list {
        let (k, i) = if m.items[w].needs_ammo.unwrap_or(false) { (m.items[w].ammo_key.clone(), None) } else { (None, Some(w)) };
        match groups.iter_mut().find(|(gk, gi, _)| *gk == k && *gi == i) {
            Some((_, _, v)) => v.push(w),
            None => groups.push((k, i, vec![w])),
        }
    }
    let mut total = 0.0;
    for (_, _, ws) in &groups {
        total += ((ENGAGEMENTS_PER_TURN * ws.len() as i64) as f64).min(shots_left(m, ws[0]));
    }
    total as i64
}

/// E[damage | hit] when an AMS engages the attack.
pub fn expected_damage_engaged(b: &mut Battle, u: UnitId, w: ItemId, plan: Option<&ShotPlan>) -> f64 {
    let p = plan.cloned().unwrap_or_else(ShotPlan::plain);
    fire_modes::expected_hit(b, u, w, &p, true)
}

/// Expected damage an engagement takes off one hit of `weapon`.
pub fn damage_prevented(b: &mut Battle, u: UnitId, w: ItemId, plan: Option<&ShotPlan>) -> f64 {
    let p = plan.cloned().unwrap_or_else(ShotPlan::plain);
    fire_modes::expected_hit(b, u, w, &p, false) - fire_modes::expected_hit(b, u, w, &p, true)
}

/// What engaging this declared hit is worth.
pub fn attack_prevented(b: &mut Battle, attacker: UnitId, attack: &DeclaredAttack) -> f64 {
    let w = attack.weapon;
    if electronics::is_narc(b, attacker, w) {
        if attack.fire.as_ref().is_some_and(|f| f.munition() == "explosive") {
            let key = b.units[attacker].items[w].ammo_key.clone().unwrap_or_default();
            return electronics::SINGLE_MISSILE_KILL_CHANCE * ammo::explosive_pod_damage(&key).unwrap_or(0) as f64;
        }
        return electronics::SINGLE_MISSILE_KILL_CHANCE * attack.pod_value;
    }
    if !engageable(b, attacker, w) {
        return 0.0;
    }
    damage_prevented(b, attacker, w, attack.fire.as_ref())
}

/// The mech's heat level at the end of this turn if nothing else changes.
pub fn projected_heat(b: &mut Battle, u: UnitId, weapon_heat: i64) -> i64 {
    let m = &b.units[u];
    let base = m.current_heat + m.movement_heat;
    base + crate::heat::other_heat(b, u) + weapon_heat - compute_heat_dissipation(&b.units[u]) - crate::water::dissipation_bonus(b, u, None)
}

/// Assign the defender's AMS to the attacker's declared hits.
pub fn engage(b: &mut Battle, defender: UnitId, attacker: UnitId, attacks: &mut [DeclaredAttack], defender_report: &mut SideReport) {
    let mut hits: Vec<usize> = Vec::new();
    for (i, a) in attacks.iter().enumerate() {
        if a.hit && attack_prevented(b, attacker, a) > 0.0 {
            hits.push(i);
        }
    }
    if hits.is_empty() || systems(b, defender).is_empty() {
        return;
    }
    do_engage(b, defender, attacker, attacks, &hits, defender_report, false);
    do_engage(b, defender, attacker, attacks, &hits, defender_report, true);
}

fn do_engage(b: &mut Battle, defender: UnitId, attacker: UnitId, attacks: &mut [DeclaredAttack], hits: &[usize], rep: &mut SideReport, apds: bool) {
    let name = b.units[defender].side_name.clone().unwrap_or_default();
    if !can_engage(&b.units[defender]) {
        b.log(format!("  [AMS] {}: can't engage ({}).", name, if b.units[defender].shutdown { "shut down" } else { "crew unconscious" }));
        return;
    }
    let a_hex = hex_geometry::parse_hex_label(b.units[attacker].hex.as_deref().unwrap()).unwrap();
    let cov = covering(b, defender, a_hex, None);
    let mut ams_list: Vec<ItemId> = cov.into_iter().filter(|w| weapon_rules::is_apds(b, defender, *w) == apds).collect();
    ams_list.sort_by_key(|w| b.units[defender].items[*w].heat.unwrap_or(0)); // sorted(): stable
    if ams_list.is_empty() {
        if !apds {
            b.log(format!("  [AMS] {}: no AMS covers the attack from {}'s hex.", name, b.units[attacker].side_name.clone().unwrap_or_default()));
        }
        return;
    }
    let limit = b.units[defender].max_heat.max(b.cfg.i("AMS_HEAT_LIMIT"));
    // engagements spent so far this phase, shared by every attacker on this defender (the phase sets ams_used)
    let mut used: HashMap<ItemId, i64> = match &b.units[defender].ams_used {
        Some(serde_json::Value::Object(o)) => o.iter().map(|(k, v)| (k.parse().unwrap(), v.as_i64().unwrap())).collect(),
        _ => HashMap::new(),
    };
    let shared = matches!(b.units[defender].ams_used, Some(serde_json::Value::Object(_)));
    let mut order: Vec<(usize, f64)> = hits.iter().map(|i| (*i, attack_prevented(b, attacker, &attacks[*i]))).collect();
    order.sort_by(|x, y| y.1.partial_cmp(&x.1).unwrap());
    for (ai, _) in order {
        for &w in &ams_list {
            if used.get(&w).copied().unwrap_or(0) >= ENGAGEMENTS_PER_TURN || shots_left(&b.units[defender], w) < 1.0 {
                continue;
            }
            let wheat = b.units[defender].items[w].heat.unwrap_or(0);
            let projected = projected_heat(b, defender, rep.weapon_heat + wheat);
            let wname = b.units[defender].items[w].name.clone();
            let aw_name = b.units[attacker].items[attacks[ai].weapon].name.clone();
            if projected > limit {
                b.log(format!("  [AMS] {}: {} holds - engaging {} would end the turn at {} heat (limit {}).", name, wname, aw_name, projected, limit));
                continue;
            }
            if apds && attacks[ai].apds.is_some() {
                break;
            }
            *used.entry(w).or_insert(0) += 1;
            let note = ammo::spend(b, defender, w, None, None);
            rep.weapon_heat += wheat;
            if apds {
                attacks[ai].apds = Some(w);
            } else {
                attacks[ai].ams = Some(w);
            }
            let cut = attack_prevented(b, attacker, &attacks[ai]);
            let att_name = b.units[attacker].side_name.clone().unwrap_or_default();
            b.log(format!("  [AMS] {}'s {} engages {}'s {} (cuts {} expected; +{} heat{}).", name, wname, att_name, aw_name, crate::pyfmt::Fx(cut, 2), wheat, if note.is_empty() { String::new() } else { format!("; {}", note) }));
            break;
        }
    }
    if shared {
        let mut o = serde_json::Map::new();
        for (k, v) in &used {
            o.insert(k.to_string(), serde_json::json!(v));
        }
        b.units[defender].ams_used = Some(serde_json::Value::Object(o));
    }
}
