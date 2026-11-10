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

fn breached(m: &mut Mech) -> &mut indexmap::IndexSet<String> {
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
        let loc = &b.units[u].locations[location.as_str()];
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
