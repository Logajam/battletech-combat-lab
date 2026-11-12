// Translated from INTEGRATION__domino.py (session 22): displacement into an occupied hex (Core pp.113-116).
use crate::battle::{Battle, UnitId};
use crate::forces::unit_in_hex;
use crate::hazards;
use crate::hex_geometry;
use crate::los::hex_distance;
use crate::mech_state::*;
use crate::movement_attacks as ma;
use crate::piloting_rolls as pr;
use crate::terrain_rules;

pub const ACCIDENTAL_FALL_TN: i64 = 7;
pub const ACCIDENTAL_TARGET_PSR: i64 = 2;
pub const DOMINO_PSR: i64 = 0;

pub fn occupant(b: &mut Battle, label: &str, exclude: &[UnitId]) -> Option<UnitId> {
    unit_in_hex(b, label, exclude)
}

/// One PSR for `u` (its own piloting skill); True if it passes.
fn psr(b: &mut Battle, u: UnitId, modifier: i64, what: &str) -> bool {
    let base = pr::preexisting_modifier(&b.units[u]) + pr::special_case_modifier(&b.units[u]);
    b.with_piloting(u, |b| pr::roll_psrs(b, 1, base + modifier, what))
}

fn name(b: &Battle, u: UnitId) -> String {
    b.units[u].side_name.clone().unwrap_or_default()
}

/// `mover` is being displaced from its hex into `label` (heading `direction`), `drop` levels down, and another 'Mech
/// stands there. Returns True when `mover` fell here.
pub fn displace_into_occupied(b: &mut Battle, mover: UnitId, label: &str, direction: i64, drop: i64, _cause: &str) -> bool {
    let origin = b.units[mover].hex.clone().unwrap();
    let Some(other) = occupant(b, label, &[mover]) else {
        b.units[mover].hex = Some(label.to_string());
        return false;
    };
    if drop >= 2 {
        return fall_from_above(b, mover, other, &origin, label, drop);
    }
    let line = format!("    {} is displaced into {}, where {} stands: DOMINO EFFECT (p.114).", name(b, mover), label, name(b, other));
    b.log(line);
    b.units[mover].hex = Some(label.to_string());
    push_out(b, other, direction, &origin);
    false
}

/// `mover` has just fallen while walking, in a hex another 'Mech also stands in: a hex it was allowed to pass through
/// (an immobile enemy, Core p.48) and either entered as it fell or was leaving on a failed backward level change (p.115:
/// it falls in the hex it was moving out of). The book does not cover this; MegaMek does
/// (TWGameManager.doEntityFallsInto): the faller takes its normal fall (already resolved by the caller), then the 'Mech
/// already there suffers a domino effect (p.114) - pushed out heading the way the faller was going (`direction`), or,
/// when the faller fell in the hex it was already in (None), in a 1D6 direction. Found 2026-11-12 by a Hydra trial: the
/// two 'Mechs were left stacked and the next movement table crashed. Nothing happens when no other 'Mech is there.
pub fn fell_into_occupied(b: &mut Battle, mover: UnitId, direction: Option<i64>) {
    let here = b.units[mover].hex.clone().unwrap();
    let Some(other) = occupant(b, &here, &[mover]) else { return };
    let direction = match direction {
        Some(d) => d,
        None => b.pick_number(6) - 1,
    };
    let line = format!("    {} fell in {}, where {} stands: DOMINO EFFECT (p.114).", name(b, mover), here, name(b, other));
    b.log(line);
    push_out(b, other, direction, &here);
}

/// An attacker follows into the hex its target just left. Returns True when `mover` fell here.
pub fn advance_into(b: &mut Battle, mover: UnitId, label: &str, direction: i64, cause: &str) -> bool {
    if occupant(b, label, &[mover]).is_none() {
        b.units[mover].hex = Some(label.to_string());
        return false;
    }
    let mh = b.units[mover].hex.clone();
    let drop = match mh.as_deref().and_then(|h| b.board.hexes.get(h)) {
        Some(h) => h.level - b.board.hexes[label].level,
        None => 0,
    };
    displace_into_occupied(b, mover, label, direction, drop, cause)
}

/// Hexes `mech` may step into to dodge a domino: directly forward or back, free, legal ground moves.
fn legal_dodges(b: &mut Battle, mech: UnitId, origin: &str) -> Vec<String> {
    let facing = hex_geometry::compass_to_facing(&b.units[mech].facing).unwrap();
    let mut options = Vec::new();
    for (step, backward) in [(facing, false), ((facing + 3) % 6, true)] {
        let here = b.units[mech].hex.clone().unwrap();
        let Some(label) = ma::neighbour(&here, step) else { continue };
        if !b.board.hexes.contains_key(&label) || label == origin || occupant(b, &label, &[mech]).is_some() {
            continue;
        }
        if backward && b.units[mech].move_mode == "Run" {
            continue;
        }
        let lim = terrain_rules::max_level_change(false, false);
        if terrain_rules::step_cost(Some(&b.board.hexes[&here]), &b.board.hexes[&label], lim, backward).is_none() {
            continue;
        }
        options.push(label);
    }
    options
}

/// The domino effect on `other`: an intruder just entered its hex heading `direction` from `origin`.
fn push_out(b: &mut Battle, other: UnitId, direction: i64, origin: &str) {
    let n = name(b, other);
    let passed = psr(b, other, DOMINO_PSR, &format!("[Domino] {} PSR", n));
    if passed && b.cfg.b("DOMINO_DODGE") && !b.units[other].prone && !is_immobile(&b.units[other]) {
        let dodges = legal_dodges(b, other, origin);
        if !dodges.is_empty() {
            b.log(format!("    {} steps out of the way to {} (p.114).", n, dodges[0]));
            b.units[other].hex = Some(dodges[0].clone());
            hazards::enter_hex(b, other, &dodges[0], false, Some("stepped out of a domino effect"), true);
            return;
        }
    }
    let here = b.units[other].hex.clone().unwrap();
    let (kind, label, drop) = ma::displacement(b, &here, direction);
    if kind == "off" {
        b.units[other].destroyed = true;
        b.units[other].cause_of_death = Some("Displaced off the battlefield".into());
        b.log(format!("    {} is forced off the battlefield - destroyed (p.113).", n));
        return;
    }
    if kind == "blocked" {
        b.units[other].destroyed = true;
        b.units[other].cause_of_death = Some("No room to be displaced (domino)".into());
        b.log(format!("    {} has no legal hex to be displaced into - destroyed (p.114).", n));
        return;
    }
    let label = label.unwrap();
    let mut fell = false;
    if occupant(b, &label, &[other]).is_some() {
        fell = displace_into_occupied(b, other, &label, direction, drop, "a domino effect");
    } else {
        let old = std::mem::replace(&mut b.units[other].hex, Some(label.clone())).unwrap();
        b.log(format!("    {} is forced {} -> {}{} (p.114).", n, old, label, if passed { "" } else { " and falls" }));
        hazards::enter_hex(b, other, &label, false, Some(&format!("forced into {}", label)), true);
    }
    if b.is_destroyed(other) || fell {
        return;
    }
    if drop >= 2 {
        b.log(format!("    {} is displaced {} levels down - automatic fall (p.114).", n, drop));
        pr::resolve_fall(b, other, "domino effect, displaced down", drop, None);
    } else if !passed {
        pr::resolve_fall(b, other, "failed the domino effect PSR", 0, None);
    }
}

fn neighbours(b: &Battle, label: &str) -> Vec<(i64, String)> {
    (0..6).filter_map(|d| ma::neighbour(label, d).filter(|n| b.board.hexes.contains_key(n)).map(|n| (d, n))).collect()
}

fn dist_labels(a: &str, b: &str) -> i64 {
    hex_distance(hex_geometry::parse_hex_label(a).unwrap(), hex_geometry::parse_hex_label(b).unwrap())
}

/// p.116: `falling` is displaced `levels` down into `label`, where `target` stands. Returns True.
fn fall_from_above(b: &mut Battle, falling: UnitId, target: UnitId, origin: &str, label: &str, levels: i64) -> bool {
    let (fname, tname) = (name(b, falling), name(b, target));
    b.log(format!("    {} is displaced {} levels down into {}, where {} stands: ACCIDENTAL FALL FROM ABOVE (p.116).", fname, levels, label, tname));
    let a_xy = hex_geometry::parse_hex_label(origin).unwrap();
    let t_xy = hex_geometry::parse_hex_label(label).unwrap();
    let tmm = crate::attack_resolution::target_tmm(&b.units[target]);
    let terrain = ma::terrain_modifier(b, a_xy, t_xy);
    let tn = ACCIDENTAL_FALL_TN + tmm + terrain;
    let roll = b.roll_2d6();
    let hit = tn <= 12 && roll >= tn;
    b.log(format!("    Attack roll: needs {} (7 + TMM {} + terrain {}), rolled {} -> {}", tn, tmm, terrain, roll, if hit { "HIT" } else { "miss" }));
    if !hit {
        let ring = neighbours(b, label);
        if ring.is_empty() {
            b.units[falling].destroyed = true;
            b.units[falling].cause_of_death = Some("Nowhere to land (fall from above)".into());
            return true;
        }
        let dist: Vec<(String, i64)> = ring.iter().map(|(_, n)| (n.clone(), dist_labels(origin, n))).collect();
        let closest = dist.iter().map(|(_, d)| *d).min().unwrap();
        let near: Vec<String> = ring.iter().map(|(_, n)| n.clone()).filter(|n| dist.iter().find(|(x, _)| x == n).unwrap().1 == closest).collect();
        let mut free: Vec<String> = Vec::new();
        for n in &near {
            if occupant(b, n, &[falling]).is_none() {
                free.push(n.clone());
            }
        }
        if free.is_empty() {
            free = near;
        }
        let k = b.pick_number(free.len() as i64) as usize;
        let landing = free[k - 1].clone();
        b.units[falling].hex = Some(landing.clone());
        b.log(format!("    {} misses and lands in {} (p.116).", fname, landing));
        hazards::enter_hex(b, falling, &landing, false, Some(&format!("landed in {}", landing)), true);
        let lands_levels = 0.max(b.board.hexes[origin].level - b.board.hexes[&landing].level);
        pr::resolve_fall(b, falling, "accidental fall from above, missed", lands_levels, None);
        if let Some(occ) = occupant(b, &landing, &[falling]) {
            let dir = combat_dir(label, &landing);
            push_out(b, occ, dir, label);
        }
        return true;
    }
    let height = crate::attack_resolution::los_height(&b.units[target]).levels - 1;
    let mass = b.units[falling].mass.unwrap_or(0);
    let damage = -((-mass).div_euclid(10)) * 1.max(levels - height);
    let tf = hex_geometry::compass_to_facing(&b.units[target].facing).unwrap();
    let side = crate::attack_resolution::attack_side(b, a_xy, t_xy, tf, crate::attack_resolution::standing(), crate::attack_resolution::standing());
    let table = if b.units[target].prone { "standard" } else { "punch" };
    b.log(format!("    {} lands on {}: {} damage ({} table, {}).", fname, tname, damage, table, side));
    ma::apply_groups(b, target, damage, table, side, "Fall from above", false, None);
    b.units[falling].hex = Some(label.to_string());
    pr::resolve_fall(b, falling, "accidental fall from above", levels, Some("rear"));
    if b.is_destroyed(target) {
        return true;
    }
    let lim = terrain_rules::max_level_change(false, false);
    let _ = lim;
    let options: Vec<String> = neighbours(b, label)
        .into_iter()
        .map(|(_, n)| n)
        .filter(|n| terrain_rules::step_cost(None, &b.board.hexes[n], terrain_rules::max_level_change(false, false), false).is_some() && b.board.hexes[n].level - b.board.hexes[label].level < 3)
        .collect();
    if options.is_empty() {
        b.units[target].destroyed = true;
        b.units[target].cause_of_death = Some("No legal hex to be displaced into (fall from above)".into());
        b.log(format!("    {} has no legal hex to be displaced into - destroyed (p.116).", tname));
        return true;
    }
    let k = b.pick_number(options.len() as i64) as usize;
    let new = options[k - 1].clone();
    let d = combat_dir(label, &new);
    b.units[target].hex = Some(new.clone());
    b.log(format!("    {} is displaced to {}.", tname, new));
    hazards::enter_hex(b, target, &new, false, Some(&format!("displaced into {}", new)), true);
    if let Some(nxt) = occupant(b, &new, &[target]) {
        push_out(b, nxt, d, label);
    }
    if !psr(b, target, ACCIDENTAL_TARGET_PSR, &format!("[Fall from above] {} PSR", tname)) {
        pr::resolve_fall(b, target, "displaced by a fall from above", 0, None);
    }
    true
}

/// The facing 0-5 from one hex to an adjacent one.
pub fn combat_dir(from_label: &str, to_label: &str) -> i64 {
    crate::combat::direction_facing(hex_geometry::parse_hex_label(from_label).unwrap(), hex_geometry::parse_hex_label(to_label).unwrap()).unwrap()
}
