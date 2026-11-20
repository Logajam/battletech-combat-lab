//! PRINCESS / CASPAR DISTANT ARTILLERY (backlog N2; Daniel, 2026-11-20: "Princess needs its artillery code"). The aim and
//! the fire-or-hold choice of MegaMek's `ArtilleryTargetingControl` (MegaMek main 3f9f2fd), for the engine's distant shot
//! (Arrow IV / Thumper / Sniper at 18+ hexes, lands next turn; Core p.182; artillery.rs). Rust only.
//!
//! WHAT IS PORTED (auto mode; MegaMek's player-ordered fire missions, counter-battery, ADA and air targets, strategic
//! buildings and special munitions have no counterpart here):
//!   * the CANDIDATE HEXES around the enemy (`buildTargetList`): its hex led to where it is predicted to be when the round
//!     lands (`predictEnemyAdvance`: toward the BV-weighted centre of our force, by the mean of its walking and fastest MP
//!     times the flight time, 1 turn for a distant shot, stopping 2 hexes short of that centre), and every board hex
//!     within 2 of that (`addHexDonuts`, MAX_ARTILLERY_BLAST_RADIUS);
//!   * the DAMAGE VALUE of a hit on a hex (`calculateDamageValue`): over the blast (radius ceil(damage / 10) - 1, the
//!     damage falling 10 a hex from the centre), each unit in a hex adds damage x 1 / (run MP + 1) x (+1 an enemy, -2 a
//!     friend); a led hex also counts its enemy's current hex; a hex a teammate's distant shot already aims at is worth
//!     COVERAGE_OVERLAP_DISCOUNT (0.2) of that;
//!   * the PICK: the highest value (times the hit odds, the same for every hex here), held if it is not above 0 or if
//!     fewer than MIN_AUTO_CLUSTER_UNITS (2) enemies stand within 2 hexes of the enemy's hex (`clusterSizeNear`).
//! WHAT DIFFERS: MegaMek plans this in a separate Targeting Phase over EVERY enemy; the engine offers a distant shot
//! inside the unit's weapon choice against its chosen target, so the candidates are built around that target only, and
//! the Target Number is the one the engine works out for that target. MegaMek breaks a tie at random among the first
//! five; this keeps the first (the choice is priced many times while the weapons are picked, and a draw each time would
//! change the battle's dice). Homing rounds onto a TAG stay with the engine's homing plan (fire_modes).
use crate::battle::{Battle, UnitId};
use crate::equipment::ItemId;
use crate::hex_geometry::{hex_label, parse_hex_label, FACING_DELTAS};
use crate::los::hex_distance;

/// MegaMek ArtilleryTargetingControl.MAX_ARTILLERY_BLAST_RADIUS
pub const MAX_BLAST_RADIUS: i64 = 2;
/// MegaMek ArtilleryTargetingControl.MIN_AUTO_CLUSTER_UNITS
pub const MIN_AUTO_CLUSTER_UNITS: usize = 2;
/// MegaMek ArtilleryTargetingControl.COVERAGE_OVERLAP_DISCOUNT
pub const COVERAGE_OVERLAP_DISCOUNT: f64 = 0.2;
/// MegaMek's friendly multiplier in calculateDamageValueForHex ("disincentivize hitting friendlies strongly")
pub const FRIENDLY_MULTIPLIER: f64 = -2.0;
/// The distant shot lands next turn (p.182): MegaMek's flight time for the lead.
const FLIGHT_TURNS: i64 = 1;

fn xy(b: &Battle, u: UnitId) -> Option<(i64, i64)> {
    b.units[u].hex.as_deref().and_then(|h| parse_hex_label(h).ok())
}

fn on_board(b: &Battle, h: (i64, i64)) -> bool {
    hex_label(h.0, h.1).is_ok_and(|l| b.board.hexes.contains_key(&l))
}

/// The units standing in a hex (`alive`: not destroyed, worked out once a pick).
fn units_at(b: &Battle, alive: &[bool], h: (i64, i64)) -> Vec<UnitId> {
    (0..b.units.len()).filter(|&u| alive[u] && xy(b, u) == Some(h)).collect()
}

/// calculateDamageValueForHex: damage x 1 / (run MP + 1) x (+1 enemy, -2 friend), summed over the units in the hex.
fn hex_value(b: &Battle, alive: &[bool], shooter: UnitId, damage: i64, h: (i64, i64)) -> f64 {
    let team = b.units[shooter].team.clone();
    units_at(b, alive, h)
        .into_iter()
        .map(|u| {
            let run = crate::mech_state::compute_running_mp(&b.units[u]);
            let side = if b.units[u].team == team { FRIENDLY_MULTIPLIER } else { 1.0 };
            damage as f64 / (run + 1) as f64 * side
        })
        .sum()
}

/// calculateDamageValue: the centre hex plus each ring of the blast, the damage less 10 a ring.
fn blast_value(b: &Battle, alive: &[bool], shooter: UnitId, damage: i64, centre: (i64, i64)) -> f64 {
    let radius = ((damage as f64) / 10.0).ceil() as i64 - 1;
    let mut total = hex_value(b, alive, shooter, damage, centre);
    if radius >= 1 {
        for (label, _) in b.board.hexes.iter() {
            let Ok(h) = parse_hex_label(label) else { continue };
            let d = hex_distance(centre, h);
            if d >= 1 && d <= radius {
                total += hex_value(b, alive, shooter, damage - 10 * d, h);
            }
        }
    }
    total
}

/// friendlyForceCentre: the Battle-Value-weighted centre of the enemy's enemies (the shooter's side), as a board hex.
fn force_centre(b: &Battle, alive: &[bool], enemy: UnitId) -> Option<(i64, i64)> {
    let (mut w, mut cx, mut cy) = (0.0, 0.0, 0.0);
    for u in 0..b.units.len() {
        if !alive[u] || b.units[u].team == b.units[enemy].team {
            continue;
        }
        let Some(h) = xy(b, u) else { continue };
        let Some((col, row)) = crate::hex_geometry::col_row(h.0, h.1) else { continue };
        let weight = (crate::battle_value::battle_value(b, u) as f64).max(b.units[u].mass.unwrap_or(1) as f64).max(1.0);
        w += weight;
        cx += col as f64 * weight;
        cy += row as f64 * weight;
    }
    if w == 0.0 {
        return None;
    }
    parse_hex_label(&format!("{:02}{:02}", (cx / w).round() as i64, (cy / w).round() as i64)).ok()
}

/// predictEnemyAdvance: the enemy's hex led toward our force for the flight time.
fn predict_advance(b: &Battle, alive: &[bool], enemy: UnitId) -> Option<(i64, i64)> {
    let pos = xy(b, enemy)?;
    let Some(anchor) = force_centre(b, alive, enemy) else { return Some(pos) };
    let m = &b.units[enemy];
    let fast = crate::mech_state::compute_running_mp(m).max(crate::mech_state::compute_jump_mp(m));
    let rate = ((crate::mech_state::compute_walk_mp(m) + fast) as f64 / 2.0).round() as i64;
    let lead = (rate * FLIGHT_TURNS).min((hex_distance(pos, anchor) - MAX_BLAST_RADIUS).max(0));
    if lead <= 0 || anchor == pos {
        return Some(pos);
    }
    let Ok(dir) = crate::combat::direction_facing(pos, anchor) else { return Some(pos) };
    let (dx, dy) = FACING_DELTAS[dir as usize];
    let mut out = pos;
    for _ in 0..lead {
        let next = (out.0 + dx, out.1 + dy);
        if !on_board(b, next) {
            break;
        }
        out = next;
    }
    Some(out)
}

/// One remembered pick: who fires which weapon at whom, from where, at whom where, on which turn -> the hex, or None to hold.
/// The positions are part of the key: Princess prices her fire from every hex she weighs moving to (move_eval).
#[derive(Clone, Debug, PartialEq)]
pub struct Aim {
    pub shooter: UnitId,
    pub weapon: ItemId,
    pub target: UnitId,
    pub turn: i64,
    pub from: Option<(i64, i64)>,
    pub at: Option<(i64, i64)>,
    pub aim: Option<(i64, i64)>,
}

/// The hex a distant shot announced now goes to (artillery::announce), if Princess aimed it.
pub fn aimed_hex(b: &Battle, shooter: UnitId, weapon: ItemId, target: UnitId) -> Option<(i64, i64)> {
    let (turn, from, at) = (b.units[shooter].turn_number, xy(b, shooter), xy(b, target));
    b.distant_aims.iter().find(|a| a.shooter == shooter && a.weapon == weapon && a.target == target && a.turn == turn && a.from == from && a.at == at).and_then(|a| a.aim)
}

/// Princess's aim for a distant shot of `weapon` (`damage` a hit) offered against `target`: the hex to fire at, or None
/// to hold (see the module comment). Remembered for the turn in `Battle::distant_aims`, so the weapon choice can price it
/// many times and the announcement uses the same hex.
pub fn distant_aim(b: &mut Battle, shooter: UnitId, weapon: ItemId, target: UnitId, damage: i64) -> Option<(i64, i64)> {
    let (turn, from, at) = (b.units[shooter].turn_number, xy(b, shooter), xy(b, target));
    if let Some(a) = b.distant_aims.iter().find(|a| a.shooter == shooter && a.weapon == weapon && a.target == target && a.turn == turn && a.from == from && a.at == at) {
        return a.aim;
    }
    let alive: Vec<bool> = (0..b.units.len()).map(|u| !b.is_destroyed(u)).collect();
    let aim = pick(b, &alive, shooter, target, damage);
    b.distant_aims.retain(|a| a.turn == turn);
    b.distant_aims.push(Aim { shooter, weapon, target, turn, from, at, aim });
    aim
}

fn pick(b: &Battle, alive: &[bool], shooter: UnitId, target: UnitId, damage: i64) -> Option<(i64, i64)> {
    let original = xy(b, target)?;
    let from = xy(b, shooter)?;
    // clusterSizeNear: enemies within the largest blast radius of the enemy's own hex
    let near = (0..b.units.len())
        .filter(|&u| alive[u] && b.units[u].team != b.units[shooter].team)
        .filter(|&u| xy(b, u).is_some_and(|h| hex_distance(h, original) <= MAX_BLAST_RADIUS))
        .count();
    if near < MIN_AUTO_CLUSTER_UNITS {
        return None;
    }
    let lead = predict_advance(b, alive, target).unwrap_or(original);
    let team = b.units[shooter].team.clone();
    let covered: Vec<(i64, i64)> = b.pending_artillery.iter().filter(|s| b.units[s.attacker].team == team).map(|s| s.impact).collect();
    let mut candidates = vec![lead];
    for radius in 1..=MAX_BLAST_RADIUS {
        let mut ring: Vec<(i64, i64)> = b.board.hexes.keys().filter_map(|l| parse_hex_label(l).ok()).filter(|h| hex_distance(lead, *h) == radius).collect();
        ring.sort();
        candidates.extend(ring);
    }
    let mut best: Option<((i64, i64), f64)> = None;
    for h in candidates {
        // a distant shot only: 18 hexes or more (p.182)
        if hex_distance(from, h) < crate::artillery::DISTANT_MIN {
            continue;
        }
        let mut v = blast_value(b, alive, shooter, damage, h);
        if h == lead && lead != original {
            v += blast_value(b, alive, shooter, damage, original);
        }
        if covered.contains(&h) {
            v *= COVERAGE_OVERLAP_DISCOUNT;
        }
        if best.map_or(true, |(_, bv)| v > bv) {
            best = Some((h, v));
        }
    }
    best.filter(|(_, v)| *v > 0.0).map(|(h, _)| h)
}
