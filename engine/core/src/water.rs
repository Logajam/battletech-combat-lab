// Translated from INTEGRATION__water.py (session 22). Stage 4 part: states, breaches, drowning, heat sinks, jump jets,
// falls. The ranged-attack parts (blocked_weapon_ids, range_adjuster...) come with attack resolution (stage 5).
use std::collections::BTreeSet;

use crate::battle::{Battle, UnitId};
use crate::board_parser::Board;
use crate::damage_resolution::{heat_sink_units, is_heat_sink, is_jump_jet, mark_location_nonfunctional};
use crate::equipment::Slot;
use crate::mech_state::*;

pub const GROUND: &str = "ground";
pub const PARTIAL: &str = "partial";
pub const SUBMERGED: &str = "submerged";
pub const WADING: &str = "wading";
pub const BREACH_MAX_ROLL: i64 = 4;
pub const MAX_WATER_DISSIPATION: i64 = 6;

/// Water depth of a hex (0 = dry or depth 0).
pub fn depth_at(board: &Board, label: Option<&str>) -> i64 {
    match label {
        None => 0,
        Some(l) => board.hexes.get(l).and_then(|h| h.depth).unwrap_or(0),
    }
}

pub fn state_at(board: &Board, label: Option<&str>, prone: bool, superheavy: bool) -> &'static str {
    let mut d = depth_at(board, label);
    if d <= 0 {
        return GROUND;
    }
    if superheavy {
        if d == 1 {
            return WADING;
        }
        d -= 1;
    }
    if prone || d >= 2 {
        return SUBMERGED;
    }
    PARTIAL
}

pub fn state(b: &Battle, u: UnitId) -> &'static str {
    let m = &b.units[u];
    state_at(&b.board, m.hex.as_deref(), m.prone, is_superheavy(m))
}

/// Locations under water: the legs in depth 1, everything when submerged.
pub fn submerged_locations(mech: &Mech, water_state: &str) -> BTreeSet<String> {
    if water_state == SUBMERGED {
        mech.locations.keys().cloned().collect()
    } else if water_state == PARTIAL || water_state == WADING {
        mech.leg_locations.iter().cloned().collect()
    } else {
        BTreeSet::new()
    }
}

fn breached(m: &mut Mech) -> &mut crate::fasthash::IndexSet<String> {
    m.breached_locations.get_or_insert_with(Default::default)
}

/// p.127: an underwater location that takes damage rolls 2D6 - a breach on 2-4.
pub fn check_breach(b: &mut Battle, u: UnitId, location: &str) {
    if breached(&mut b.units[u]).contains(location) || b.units[u].locations[location].destroyed {
        return;
    }
    let st = state(b, u);
    if !submerged_locations(&b.units[u], st).contains(location) {
        return;
    }
    let (skip, bonus) = crate::equipment_systems::harjel_breach_check(&b.units[u], location);
    if skip {
        b.log(format!("    Hull breach check, {}: none - HarJel with armor left (p.208).", location));
        return;
    }
    let roll = b.roll_2d6() + bonus;
    if roll <= BREACH_MAX_ROLL {
        b.log(format!("    Hull breach check, {} under water: rolled {} - BREACHED (2-4, p.127).", location, roll));
        breach(b, u, location);
    } else {
        b.log(format!("    Hull breach check, {} under water: rolled {} - holds.", location, roll));
    }
}

/// p.127: a location with all its armor gone is breached as soon as it is under water. Checked after every phase.
pub fn auto_breaches(b: &mut Battle, u: UnitId) {
    if b.units[u].hex.is_none() {
        return;
    }
    let st = state(b, u);
    let locs = submerged_locations(&b.units[u], st); // BTreeSet = sorted(...)
    for location in locs {
        let _loc = &b.units[u].locations[location.as_str()];
        if breached(&mut b.units[u]).contains(&location) || b.units[u].locations[location.as_str()].destroyed {
            continue;
        }
        let loc = &b.units[u].locations[location.as_str()];
        let _ = loc;
        let l = &b.units[u].locations[location.as_str()];
        if l.armor <= crate::pyfmt::Num::I(0) || l.rear_armor.map_or(false, |r| r <= crate::pyfmt::Num::I(0)) {
            let name = b.units[u].side_name.clone().unwrap_or_default();
            b.log(format!("    {}'s {} has no armor left and is under water - BREACHED (p.127).", name, location));
            breach(b, u, &location);
        }
    }
}

/// p.127 Breach Effects: every component in the location stops working; a breached leg counts as destroyed; a
/// breached side torso breaches its arm.
pub fn breach(b: &mut Battle, u: UnitId, location: &str) {
    breached(&mut b.units[u]).insert(location.to_string());
    let name = b.units[u].side_name.clone().unwrap_or_default();
    b.log(format!("    {}'s {} floods - its components stop working (p.127).", name, location));
    mark_location_nonfunctional(b, u, location, "breach");
    if b.units[u].leg_locations.iter().any(|l| l == location) {
        b.units[u].locations.get_mut(location).unwrap().destroyed = true;
        b.log("    A breached leg counts as destroyed (p.127).");
    }
    if let Some(child) = b.units[u].side_torso_child.get(location).cloned() {
        if !breached(&mut b.units[u]).contains(&child) && !b.units[u].locations[child.as_str()].destroyed {
            b.log(format!("    The {} on that side is breached with it (p.127).", child));
            breach(b, u, &child);
        }
    }
}

/// p.117: with a life support critical hit, a 'Mech fully submerged in the End Phase costs its MechWarrior 1 hit.
pub fn drowning(b: &mut Battle, u: UnitId, has_life_support_hit: bool) {
    if b.units[u].hex.is_none() || !has_life_support_hit || state(b, u) != SUBMERGED {
        return;
    }
    b.units[u].pilot_hits += 1;
    b.pilot_hit_ev(u, "life support");
    mark_consciousness_check_pending(&mut b.units[u]);
    let (n, h) = (b.units[u].side_name.clone().unwrap_or_default(), b.units[u].pilot_hits);
    b.log(format!("  [End] {}: life support destroyed and fully submerged - MechWarrior takes 1 hit ({}/6, p.117).", n, h));
}

/// Equipment items in `location` passing `test`, once each, in slot order.
fn working<F: Fn(&Mech, usize) -> bool>(mech: &Mech, location: &str, test: F) -> Vec<usize> {
    let mut seen: Vec<usize> = Vec::new();
    for s in mech.crits.get(location).into_iter().flatten() {
        if let Slot::Item(id) = s {
            if test(mech, *id) && !seen.contains(id) {
                seen.push(*id);
            }
        }
    }
    seen
}

/// Extra heat dissipated by submerged heat sinks (p.103), at most 6.
pub fn dissipation_bonus(b: &Battle, u: UnitId, water_state: Option<&str>) -> i64 {
    let m = &b.units[u];
    let st = water_state.unwrap_or_else(|| state(b, u));
    if st == GROUND {
        return 0;
    }
    let submerged = if st == SUBMERGED {
        active_heat_sinks(m)
    } else {
        let mut s = 0;
        for loc in &m.leg_locations {
            for sink in working(m, loc, is_heat_sink) {
                if !m.destroyed_heat_sinks.contains_key(&sink) {
                    s += heat_sink_units(m, sink);
                }
            }
        }
        s.min(active_heat_sinks(m))
    };
    MAX_WATER_DISSIPATION.min(submerged * heat_sink_rate(m))
}

/// Jumping MP the water takes away (p.50); None = can't jump at all.
pub fn jump_mp_lost(b: &Battle, u: UnitId, water_state: Option<&str>) -> Option<i64> {
    let m = &b.units[u];
    let st = water_state.unwrap_or_else(|| state(b, u));
    if st == SUBMERGED {
        return None;
    }
    if st == PARTIAL || st == WADING {
        let mut n = 0;
        for loc in &m.leg_locations {
            for jet in working(m, loc, is_jump_jet) {
                if !m.destroyed_jump_jet_ids.contains(&jet) {
                    n += 1;
                }
            }
        }
        return Some(n);
    }
    Some(0)
}

pub fn jump_mp(b: &Battle, u: UnitId) -> i64 {
    match jump_mp_lost(b, u, None) {
        None => 0,
        Some(lost) => 0.max(compute_jump_mp(&b.units[u]) - lost),
    }
}

/// p.115: a 'Mech that falls in depth 1+ water takes half damage.
pub fn fall_damage_divisor(b: &Battle, u: UnitId) -> i64 {
    if depth_at(&b.board, b.units[u].hex.as_deref()) >= 1 {
        2
    } else {
        1
    }
}

/// p.77: physical damage to an underwater location is halved, rounded down.
pub fn physical_damage(b: &Battle, u: UnitId, location: &str, damage: i64) -> i64 {
    let st = state(b, u);
    if submerged_locations(&b.units[u], st).contains(location) {
        crate::pyfmt::py_floordiv(damage, 2)
    } else {
        damage
    }
}

// ---- ranged attacks (stage 5) --------------------------------------------------------------------------------------
use crate::fasthash::{HashMap, HashSet};

use crate::equipment::ItemId;

/// {weapon: locations its slots sit in} (attack_resolution.weapon_locations), locations sorted.
pub type WeaponLocs = HashMap<ItemId, Vec<String>>;

pub const CANT_FIRE_TN: i64 = 99;

pub fn underwater_bracket_tn(bracket: &str) -> i64 {
    match bracket {
        "short" | "medium" => 2,
        _ => CANT_FIRE_TN,
    }
}

/// p.127: one bracket longer ("" = none).
pub fn shifted_bracket(bracket: &str) -> &'static str {
    match bracket {
        "short" => "medium",
        "medium" => "long",
        "long" => "",
        other => panic!("KeyError: {}", other),
    }
}

fn combat_state(s: &str) -> &str {
    if s == WADING { GROUND } else { s }
}

fn locs_of<'a>(w: &'a WeaponLocs, id: ItemId) -> &'a [String] {
    w.get(&id).map(|v| v.as_slice()).unwrap_or(&[])
}

/// True when the line from a_label to t_label runs entirely through water of depth 1 or deeper, both ends included.
pub fn water_line(board: &Board, a_label: &str, t_label: &str) -> bool {
    let a = crate::hex_geometry::parse_hex_label(a_label).unwrap();
    let t = crate::hex_geometry::parse_hex_label(t_label).unwrap();
    crate::los::hex_line(a, t).iter().all(|step| step.iter().all(|h| depth_at(board, Some(&crate::hex_geometry::hex_label(h.0, h.1).unwrap())) >= 1))
}

/// ids of the attacker's weapons that can't fire at a target in t_state from a_state, or None when no attack can be made.
pub fn blocked_weapon_ids(attacker: &Mech, weapons: &[ItemId], weapon_locs: &WeaponLocs, a_state: &str, t_state: &str, torpedo_line: bool) -> Option<HashSet<ItemId>> {
    let torpedoes: HashSet<ItemId> = weapons.iter().copied().filter(|w| crate::weapon_rules::is_torpedo(attacker, *w)).collect();
    if a_state == WADING && (t_state == PARTIAL || t_state == SUBMERGED) {
        return None;
    }
    if t_state == WADING && (a_state == PARTIAL || a_state == SUBMERGED) {
        let under = submerged_locations(attacker, a_state);
        return Some(
            weapons
                .iter()
                .copied()
                .filter(|w| torpedoes.contains(w) || (locs_of(weapon_locs, *w).iter().any(|l| under.contains(l)) && attacker.items[*w].damage_type.as_deref() != Some("Energy")))
                .collect(),
        );
    }
    let (a_state, t_state) = (combat_state(a_state), combat_state(t_state));
    if a_state == GROUND && t_state == GROUND {
        return Some(torpedoes);
    }
    if (a_state == GROUND && t_state == SUBMERGED) || (a_state == SUBMERGED && t_state == GROUND) {
        return None;
    }
    let legs: HashSet<&String> = attacker.leg_locations.iter().collect();
    let under = submerged_locations(attacker, a_state);
    let mut blocked = HashSet::default();
    for &w in weapons {
        let locs = locs_of(weapon_locs, w);
        let in_leg = locs.iter().any(|l| legs.contains(l));
        let energy = attacker.items[w].damage_type.as_deref() == Some("Energy");
        if torpedoes.contains(&w) {
            if !(!locs.is_empty() && locs.iter().all(|l| under.contains(l)) && t_state != GROUND && torpedo_line) {
                blocked.insert(w);
            }
        } else if a_state == PARTIAL && t_state == GROUND && in_leg {
            blocked.insert(w);
        } else if a_state == PARTIAL && t_state == SUBMERGED && !in_leg {
            blocked.insert(w);
        } else if locs.iter().any(|l| under.contains(l)) && !energy {
            blocked.insert(w);
        }
    }
    Some(blocked)
}

/// ids of the attacker's weapons whose hits on a target standing in depth 1 use the Kick Location Table.
pub fn kick_table_weapon_ids(attacker: &Mech, weapons: &[ItemId], weapon_locs: &WeaponLocs, a_state: &str, t_state: &str) -> HashSet<ItemId> {
    if t_state == WADING {
        let under = if a_state == PARTIAL || a_state == SUBMERGED { submerged_locations(attacker, a_state) } else { BTreeSet::new() };
        return weapons.iter().copied().filter(|w| locs_of(weapon_locs, *w).iter().any(|l| under.contains(l)) || a_state == SUBMERGED).collect();
    }
    if t_state != PARTIAL {
        return HashSet::default();
    }
    if a_state == SUBMERGED {
        return weapons.iter().copied().collect();
    }
    if a_state == PARTIAL {
        let legs: HashSet<&String> = attacker.leg_locations.iter().collect();
        return weapons.iter().copied().filter(|w| locs_of(weapon_locs, *w).iter().any(|l| legs.contains(l))).collect();
    }
    HashSet::default()
}

/// The ids of the weapons the underwater range shift touches (None: nothing is submerged, no wrapper).
pub fn submerged_weapon_ids(attacker: &Mech, weapon_locs: &WeaponLocs, a_state: &str) -> Option<HashSet<ItemId>> {
    let under = submerged_locations(attacker, a_state);
    if under.is_empty() {
        return None;
    }
    Some(weapon_locs.iter().filter(|(_, locs)| locs.iter().any(|l| under.contains(l))).map(|(w, _)| *w).collect())
}

/// {label: depth} of the board's water hexes of depth 1+.
pub fn hexes_by_depth(board: &Board) -> crate::fasthash::IndexMap<String, i64> {
    board.hexes.iter().filter_map(|(l, h)| match h.depth { Some(d) if d >= 1 => Some((l.clone(), d)), _ => None }).collect()
}

/// Physical attacks an attacker in a_state may make on a target in t_state (p.77): None = any; else the kinds allowed.
pub fn physical_allowed(a_state: &str, t_state: &str) -> Option<Vec<&'static str>> {
    if a_state == WADING && (t_state == PARTIAL || t_state == SUBMERGED) {
        return Some(vec![]);
    }
    let (a_state, t_state) = (combat_state(a_state), combat_state(t_state));
    if t_state == SUBMERGED {
        if a_state == SUBMERGED {
            return None;
        }
        return Some(if a_state == PARTIAL { vec!["kick"] } else { vec![] });
    }
    if a_state == SUBMERGED && t_state == GROUND {
        return Some(vec![]);
    }
    None
}

/// P(a standard-table hit lands on a leg), p.74 - a quad's arm results are its front legs.
fn leg_share_q(quad: bool, side: &str) -> f64 {
    let table: &[(i64, &str)] = match side {
        "left" => &crate::hit_location::HIT_TABLE_LEFT_SIDE,
        "right" => &crate::hit_location::HIT_TABLE_RIGHT_SIDE,
        _ => &crate::hit_location::HIT_TABLE_FRONT_REAR,
    };
    // Python: sum(...) of floats
    let mut terms = Vec::new();
    for r in 2..=12i64 {
        let p = (6 - (7 - r).abs()) as f64 / 36.0;
        let name = table.iter().find(|(k, _)| *k == r).unwrap().1;
        if name.contains("Leg") || (quad && name.contains("Arm")) {
            terms.push(p);
        }
    }
    crate::pyfmt::py_sum(terms)
}

/// How much of a physical attack's damage lands at full strength, for movement scoring.
pub fn physical_value_factor(target: &Mech, t_state: &str, table: &str, side: &str) -> f64 {
    physical_value_factor_q(target.mech_type == "quad" || target.mech_type == "quadvee", t_state, table, side)
}

pub fn physical_value_factor_q(quad: bool, t_state: &str, table: &str, side: &str) -> f64 {
    if t_state == GROUND || table == "displacement" {
        return 1.0;
    }
    if t_state == SUBMERGED || table == "kick" {
        return 0.5;
    }
    if table == "punch" {
        return 1.0;
    }
    1.0 - 0.5 * leg_share_q(quad, side)
}
