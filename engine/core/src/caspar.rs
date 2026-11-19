// CASPAR, the fourth bot (session 29). MegaMek's CASPAR is `class Caspar extends Princess` (megamek/client/bot/caspar/Caspar.java, MegaMek
// main 7fa46c5, read 2026-11-18): Princess with a few parts swapped. For 'Mechs the parts are
//   1. the MUTUAL SUPPORT movement ranker (MutualSupportPathRanker): a formation penalty in place of herding on the heat map, a
//      cover bonus for ending inside a set friend's range, a closing tempo counted in turns at the unit's own speed, and a
//      charge for a defending force that crosses water;
//   2. MUTUAL SUPPORT deployment (MutualSupportDeployment, FormationGeometry, SupportEnvelope): a force comes on as a formation;
//   3. deployment facing toward the middle of the enemy's zone (facesEnemyZoneAtDeployment).
// Everything else (target choice, fire control, physical attacks, memory, posture) is the Princess clone's, unchanged: the
// bot name "caspar" is accepted wherever "princess" is (`Mech::is_princess_family`). Not ported, because a simulation has none:
// aerospace doctrine and move order, takeoff / landing, player unit orders (`followsUnitOrders`), forced withdrawal (the clone
// has none; MegaMek exempts withdrawing units from the formation terms).
// Deliberate simplifications: the supporting-range curve is built from this engine's expected damage per weapon (DamageProfile
// ignores arcs and weapon-specific bonuses too); it is recomputed at each decision, not cached for the round as MegaMek does (so
// a weapon lost mid-movement shows at once and the decision stays a pure function of the battle state, which the bridge needs).
// The "same side of the water" line test counts a hex line that runs along an edge as crossing if EITHER hex is deep water.
// Credit: MegaMek Team, GPL v3 or later (CREDITS.md).
use crate::fasthash::HashMap;

use crate::battle::{Battle, UnitId};
use crate::combat::hit_probability;
use crate::hex_geometry;
use crate::los::hex_distance;
use crate::mech_state::*;
use crate::princess_modern::{cols_rows, java_round, xy_of, Group};

const THREAT_CONTACT_RANGE: i64 = 15;
const TEMPO_REFERENCE_MP: f64 = 15.0;
const COHESION_WEIGHT_CAP_FACTOR: f64 = 0.8;
const FORMATION_HOLD_FACTOR: f64 = 5.0;
const COVER_BONUS: f64 = 2.0;
const COVER_BONUS_MAX_FRIENDS: i64 = 2;
/// FormationGeometry.MINIMUM_SPACING_HEXES
pub const MINIMUM_SPACING_HEXES: i64 = 2;
/// FormationSide.SEPARATING_DEPTH: water this deep splits a formation; BankRegions uses any water (depth 1).
const SEPARATING_DEPTH: i64 = 2;
const SUPPORT_THRESHOLD_FRACTION: f64 = 0.5;

/// SupportEnvelope: the range where the unit's expected damage peaks, and the furthest range at which it still lands half of that.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Envelope {
    pub peak: i64,
    pub effective: i64,
}

pub const WEAPONLESS: Envelope = Envelope { peak: 0, effective: 0 };

/// SupportEnvelope.of / DamageProfile: expected damage by range 1..=longest reach from the unit's working weapons at its own
/// gunnery (hit chance x expected damage per hit), peak ties going to the longer range.
pub fn envelope(b: &mut Battle, u: UnitId) -> Envelope {
    let gunnery = b.units[u].gunnery;
    let mut weapons: Vec<(f64, crate::equipment::WeaponRange, usize)> = Vec::new();
    for w in crate::damage_resolution::get_weapons(&b.units[u]) {
        if crate::weapon_rules::is_ams(b, u, w) {
            continue;
        }
        let Some(dps) = b.units[u].items[w].damage_per_shot else { continue };
        let Some(range) = b.units[u].items[w].weapon_range.clone() else { continue };
        // DamageProfile.WeaponContribution.of: a weapon that needs ammo and has no usable shot left adds nothing
        // (review of session 29: the first port counted dry weapons, so a spent launcher kept stretching the envelope)
        if crate::ams::shots_left(&b.units[u], w) <= 0.0 {
            continue;
        }
        weapons.push((profile_damage_per_hit(b, u, w, dps), range, w));
    }
    let reach = weapons.iter().map(|w| w.1.long).max().unwrap_or(0);
    if reach < 1 {
        return WEAPONLESS;
    }
    let mut curve = vec![0.0f64; reach as usize + 1];
    for range in 1..=reach {
        let mut total = 0.0;
        for (ed, _, w) in &weapons {
            if let Some(m) = crate::weapon_selection::weapon_range_mod(b, u, *w, range) {
                total += hit_probability(gunnery + m) * ed;
            }
        }
        curve[range as usize] = total;
    }
    let (mut peak, mut best) = (0i64, 0.0f64);
    for range in 1..=reach {
        if curve[range as usize] >= best {
            best = curve[range as usize];
            peak = range;
        }
    }
    let threshold = best * SUPPORT_THRESHOLD_FRACTION;
    let mut effective = peak;
    let mut range = reach;
    while range > peak {
        if curve[range as usize] >= threshold {
            effective = range;
            break;
        }
        range -= 1;
    }
    Envelope { peak, effective }
}

/// DamageProfile.WeaponContribution.resolve, damage per hit (before the hit chance): a missile rack is the plain Cluster
/// Hits Table average for its size (MegaMek's profile applies no Artemis / Apollo bonus, and prices a Streak like any rack),
/// an Ultra autocannon two shots and a Rotary six through the same table, anything else its damage. (Review of session 29:
/// the first port used the engine's own per-hit expectation, which gives a Streak its whole rack, adds Artemis and treats an
/// Ultra / Rotary as one shot.) A rack size the table cannot price falls back to the flat damage.
fn profile_damage_per_hit(b: &mut Battle, u: UnitId, w: usize, dps: i64) -> f64 {
    let shots = if crate::fire_modes::is_ultra(b, u, w) {
        2
    } else if crate::fire_modes::is_rotary(b, u, w) {
        6
    } else if crate::weapon_rules::is_cluster(b, u, w) {
        b.units[u].items[w].rack_size.unwrap_or(1)
    } else {
        1
    };
    if shots <= 1 {
        return dps as f64;
    }
    crate::expected_damage::expected_cluster_hits(b, shots, 0).map_or(dps as f64, |hits| dps as f64 * hits)
}

/// FormationGeometry.formationRadiusFor: half the mean effective range of the armed units, divided by the mutual support setting,
/// never under the minimum spacing.
pub fn formation_radius(effective_ranges: &[i64], support: f64) -> i64 {
    if effective_ranges.is_empty() || support <= 0.0 {
        return MINIMUM_SPACING_HEXES;
    }
    let mean = effective_ranges.iter().sum::<i64>() as f64 / effective_ranges.len() as f64;
    MINIMUM_SPACING_HEXES.max(java_round(mean / 2.0 / support))
}

/// The team's units standing on the board (getEntitiesOwned: positioned, not off-board).
fn owned(b: &mut Battle, team: &Option<String>) -> Vec<UnitId> {
    crate::forces::standing(b).into_iter().filter(|u| b.units[*u].team == *team && b.units[*u].hex.is_some()).collect()
}

pub fn mutual_support_setting(b: &Battle) -> f64 {
    crate::princess_modern::mutual_support_value(b)
}

/// FormationSide.sameSide: no hex of the straight line between the two is water SEPARATING_DEPTH deep. The line is
/// MegaMek's own (`mm_intervening`), so where it runs exactly along a hex edge it takes the one hex MegaMek takes. (The
/// first port used this engine's line and counted both hexes of such a pair; fixed in CASPAR's review, 2026-11-19.)
fn same_side(b: &Battle, from: (i64, i64), to: (i64, i64)) -> bool {
    if from == to {
        return true;
    }
    for (x, y) in mm_intervening(cols_rows(from), cols_rows(to)) {
        // FormationSide.isSeparatingWater: a hex off the board is not water
        if x < 0 || y < 0 {
            continue;
        }
        let label = crate::princess_memory::cols_rows_to_label(x, y);
        if b.board.hexes.contains_key(&label) && crate::water::depth_at(&b.board, Some(&label)) >= SEPARATING_DEPTH {
            return false;
        }
    }
    true
}

// ---- MegaMek's hex line (Coords.intervening with split = false, Coords.nextHex, IdealHex), on MegaMek's coordinates:
// (column, row) from 0, odd columns half a hex lower - this engine's `cols_rows`. Ported as written, Java rounding included.
const X_CONST: f64 = 0.577_350_269_189_625_7; // Math.tan(Math.PI / 6.0), as Java prints it
const HEX_SIDE: f64 = std::f64::consts::PI / 3.0;

/// IdealHex: the hex's corners (x[0..6], y[0..6]) and centre in MegaMek's unit layout.
struct IdealHex {
    x: [f64; 6],
    y: [f64; 6],
    cx: f64,
    cy: f64,
}

impl IdealHex {
    fn of(c: (i64, i64)) -> IdealHex {
        let ox = c.0 as f64 * X_CONST * 3.0;
        let oy = c.1 as f64 * 2.0 + if c.0 & 1 == 1 { 1.0 } else { 0.0 };
        let (cx, cy) = (ox + X_CONST * 2.0, oy + 1.0);
        let x = [ox + X_CONST, ox + X_CONST * 3.0, ox + X_CONST * 4.0, ox + X_CONST * 3.0, ox + X_CONST, ox];
        let y = [oy, oy, cy, oy + 2.0, oy + 2.0, cy];
        IdealHex { x, y, cx, cy }
    }

    /// IdealHex.turns: 1 left, -1 right, 0 straight (within 1e-6).
    fn turns(x0: f64, y0: f64, x1: f64, y1: f64, x2: f64, y2: f64) -> i64 {
        let cross = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0);
        if cross > 0.000001 { 1 } else if cross < -0.000001 { -1 } else { 0 }
    }

    /// IdealHex.isIntersectedBy: does the line through (x0, y0) and (x1, y1) touch this hex?
    fn is_intersected_by(&self, x0: f64, y0: f64, x1: f64, y1: f64) -> bool {
        let side1 = Self::turns(x0, y0, x1, y1, self.x[0], self.y[0]);
        if side1 == 0 {
            return true;
        }
        (1..6).any(|i| {
            let j = Self::turns(x0, y0, x1, y1, self.x[i], self.y[i]);
            j == 0 || j != side1
        })
    }
}

/// Coords.radian: the angle from a to b, clockwise from north.
fn mm_radian(a: (i64, i64), b: (i64, i64)) -> f64 {
    let (src, dst) = (IdealHex::of(a), IdealHex::of(b));
    if src.cy == dst.cy {
        return if src.cx < dst.cx { std::f64::consts::PI / 2.0 } else { std::f64::consts::PI * 1.5 };
    }
    // Java's Math.atan is fdlibm's (StrictMath); the system atan can differ in the last bit, which moves a 30-degree line
    let mut r = libm::atan((dst.cx - src.cx) / (src.cy - dst.cy));
    if src.cy < dst.cy {
        r = (r + std::f64::consts::PI) % (std::f64::consts::PI * 2.0);
    }
    if r < 0.0 {
        r += std::f64::consts::PI * 2.0;
    }
    r
}

/// Coords.direction: (int) Math.round(radian / HEX_SIDE) % 6. Java's Math.round is exact (ties up): floor(x + 0.5) would
/// round 0.49999999999999994 up, which happens on the 30-degree lines.
pub(crate) fn mm_direction(a: (i64, i64), b: (i64, i64)) -> i64 {
    let x = mm_radian(a, b) / HEX_SIDE;
    let f = x.floor();
    (if x - f >= 0.5 { f as i64 + 1 } else { f as i64 }) % 6
}

/// Coords.translated(dir) (xInDir / yInDir at distance 1).
pub(crate) fn mm_translated(c: (i64, i64), dir: i64) -> (i64, i64) {
    let (x, y) = c;
    let odd = x & 1;
    match dir {
        0 => (x, y - 1),
        1 => (x + 1, y - (2 - odd) / 2),
        2 => (x + 1, y + (1 + odd) / 2),
        3 => (x, y + 1),
        4 => (x - 1, y + (1 + odd) / 2),
        _ => (x - 1, y - (2 - odd) / 2),
    }
}

/// Coords.intervening(src, dest) (split = false): src, every hex the centre line passes through, dest. Where the line runs
/// along an edge, Coords.nextHex tries the side directions (centre + 1, then centre + 5) before the centre one and keeps the
/// first the line touches.
pub fn mm_intervening(src: (i64, i64), dest: (i64, i64)) -> Vec<(i64, i64)> {
    let (i_src, i_dest) = (IdealHex::of(src), IdealHex::of(dest));
    let centre = mm_direction(src, dest);
    let directions = [(centre + 1) % 6, (centre + 5) % 6, centre];
    let mut hexes = vec![src];
    let mut current = src;
    // a near-edge line can zig-zag through up to about twice the distance in hexes; the bound only guards against a loop
    let limit = 4 * (crate::princess_geometry::mm_distance(src, dest) + 2);
    while current != dest && (hexes.len() as i64) <= limit {
        let next = directions.iter().map(|d| mm_translated(current, *d)).find(|t| IdealHex::of(*t).is_intersected_by(i_src.cx, i_src.cy, i_dest.cx, i_dest.cy));
        match next {
            Some(t) => {
                current = t;
                hexes.push(t);
            }
            None => break, // MegaMek throws here ("Couldn't find the next hex!"); it does not happen on a straight line
        }
    }
    hexes
}

/// BankRegions: every dry hex labelled with its connected dry region; wet hexes (any water) are not on a bank.
fn bank_regions(b: &Battle) -> HashMap<String, i64> {
    let mut regions: HashMap<String, i64> = HashMap::default();
    let mut next = 0;
    let mut labels: Vec<&String> = b.board.hexes.keys().collect();
    labels.sort();
    let wet = |l: &str| crate::water::depth_at(&b.board, Some(l)) >= 1;
    for start in labels {
        if regions.contains_key(start) || wet(start) {
            continue;
        }
        regions.insert(start.clone(), next);
        let mut frontier = vec![start.clone()];
        while let Some(cur) = frontier.pop() {
            let xy = hex_geometry::parse_hex_label(&cur).unwrap();
            for d in 0..6 {
                let n = crate::princess_geometry::neighbor(xy, d);
                let Ok(label) = hex_geometry::hex_label(n.0, n.1) else { continue };
                if b.board.hexes.contains_key(&label) && !regions.contains_key(&label) && !wet(&label) {
                    regions.insert(label.clone(), next);
                    frontier.push(label);
                }
            }
        }
        next += 1;
    }
    regions
}

/// What MutualSupportPathRanker needs to score one mover's candidate hexes, built once per decision.
pub struct Doctrine {
    own_peak: i64,
    speed: i64,
    support: f64,
    radius: i64,
    has_friends: bool,
    centre: Option<(i64, i64)>,
    /// (hex, effective range) of each friend that has already moved this turn: the set bases of fire
    set_friends: Vec<((i64, i64), i64)>,
    /// DEFEND only: the dry-region labels and the mover's own bank
    banks: Option<(HashMap<String, i64>, i64)>,
}

impl Doctrine {
    pub fn new(b: &mut Battle, mover: UnitId, group: &Group, stance: &str) -> Doctrine {
        let support = mutual_support_setting(b);
        let team = b.units[mover].team.clone();
        let own_peak = envelope(b, mover).peak;
        let speed = 1.max(compute_running_mp(&b.units[mover]).max(compute_jump_mp(&b.units[mover])));
        // the formation radius: from every unit of the force on the board (the mover too, if it is on it)
        let mut ranges = Vec::new();
        for u in owned(b, &team) {
            let e = envelope(b, u).effective;
            if e > 0 {
                ranges.push(e);
            }
        }
        let radius = formation_radius(&ranges, support);
        let mover_xy = b.units[mover].hex.as_deref().map(|h| hex_geometry::parse_hex_label(h).unwrap());
        // the formation centre: the friends on the mover's side of any deep water
        let mut cols: Vec<(i64, i64)> = Vec::new();
        let mut set_friends = Vec::new();
        for &f in &group.friends {
            let fxy = hex_geometry::parse_hex_label(b.units[f].hex.as_deref().unwrap()).unwrap();
            if b.units[f].moved_this_turn {
                set_friends.push((fxy, envelope(b, f).effective));
            }
            if mover_xy.map_or(true, |m| same_side(b, m, fxy)) {
                cols.push(cols_rows(fxy));
            }
        }
        let centre = if cols.is_empty() {
            None
        } else {
            let n = cols.len() as f64;
            Some(xy_of(java_round(cols.iter().map(|c| c.0 as f64).sum::<f64>() / n), java_round(cols.iter().map(|c| c.1 as f64).sum::<f64>() / n)))
        };
        let banks = match (stance == "DEFEND", b.units[mover].hex.clone()) {
            (true, Some(h)) => {
                let regions = bank_regions(b);
                let mine = regions.get(&h).copied().unwrap_or(-1);
                Some((regions, mine))
            }
            _ => None,
        };
        Doctrine { own_peak, speed, support, radius, has_friends: !group.friends.is_empty(), centre, set_friends, banks }
    }

    /// calculateAggressionMod: the gap still to close to the unit's own peak range, in turns at its own speed, priced at one
    /// turn of advance a turn (TEMPO_REFERENCE_MP x aggression). `dist`: the path's end hex to the nearest enemy.
    pub fn tempo(&self, dist: i64, aggression: f64) -> f64 {
        let gap = (dist - self.own_peak).max(0) as f64;
        gap / self.speed as f64 * TEMPO_REFERENCE_MP * aggression
    }

    /// calculateMutualSupportMod: out-of-formation penalty (bounded by one turn's advance x 0.8) - cover bonus + posture charge.
    pub fn support_mod(&self, spot: (i64, i64), dist: i64, aggression: f64, turn_of_advance: f64) -> f64 {
        let posture = match &self.banks {
            Some((regions, mine)) if *mine != -1 => {
                let here = hex_geometry::hex_label(spot.0, spot.1).ok().and_then(|l| regions.get(&l).copied()).unwrap_or(-1);
                if here != *mine { turn_of_advance } else { 0.0 }
            }
            _ => 0.0,
        };
        if !self.has_friends {
            return posture;
        }
        let mut penalty = 0.0;
        if let Some(c) = self.centre {
            let out = hex_distance(c, spot) - self.radius;
            if out > 0 {
                let cohesion = self.support.min(aggression * COHESION_WEIGHT_CAP_FACTOR);
                penalty = (out as f64 * cohesion * FORMATION_HOLD_FACTOR).min(TEMPO_REFERENCE_MP * aggression * COHESION_WEIGHT_CAP_FACTOR);
            }
        }
        let mut cover = 0.0;
        if (0..=THREAT_CONTACT_RANGE).contains(&dist) {
            let covering = self.set_friends.iter().filter(|(f, eff)| hex_distance(*f, spot) <= *eff).count() as i64;
            cover = covering.min(COVER_BONUS_MAX_FRIENDS) as f64 * COVER_BONUS;
        }
        penalty - cover + posture
    }
}

// ---- deployment (MutualSupportDeployment) -----------------------------------------------------------------------------------
/// MutualSupportDeployment.prioritize / orderByFormation: the legal hexes in formation order - least out of the formation band
/// first, then least crowding - a stable sort, so hexes that tie keep the order they came in (Princess's terrain fitness order;
/// `princess_deploy`, which then scans the front of the list as MegaMek does). `anchor` = the centre of the force's deployed
/// units, or the middle of the candidates when none is down yet. (Session 30: the first port kept only the leading ties and
/// picked among them at random.)
pub fn prefer_formation(b: &mut Battle, unit: UnitId, candidates: Vec<String>) -> Vec<String> {
    if candidates.len() < 2 {
        return candidates;
    }
    let team = b.units[unit].team.clone();
    let friends: Vec<(i64, i64)> = owned(b, &team).into_iter().filter(|u| *u != unit).map(|u| hex_geometry::parse_hex_label(b.units[u].hex.as_deref().unwrap()).unwrap()).collect();
    let pts: Vec<(i64, i64)> = if friends.is_empty() { candidates.iter().map(|c| hex_geometry::parse_hex_label(c).unwrap()).collect() } else { friends.clone() };
    let cr: Vec<(i64, i64)> = pts.iter().map(|p| cols_rows(*p)).collect();
    let n = cr.len() as f64;
    let anchor = xy_of(java_round(cr.iter().map(|c| c.0 as f64).sum::<f64>() / n), java_round(cr.iter().map(|c| c.1 as f64).sum::<f64>() / n));
    let support = mutual_support_setting(b);
    let team_units = owned(b, &team);
    let mut ranges = Vec::new();
    for u in team_units {
        let e = envelope(b, u).effective;
        if e > 0 {
            ranges.push(e);
        }
    }
    let radius = formation_radius(&ranges, support);
    let key = |c: &String| -> (i64, i64) {
        let xy = hex_geometry::parse_hex_label(c).unwrap();
        let out = (hex_distance(anchor, xy) - radius).max(0);
        let crowd = friends.iter().map(|f| MINIMUM_SPACING_HEXES - hex_distance(xy, *f)).max().unwrap_or(0).max(0);
        (out, crowd)
    };
    let mut ordered = candidates;
    ordered.sort_by_key(|c| key(c));
    ordered
}

#[cfg(test)]
mod tests {
    use super::mm_intervening;

    /// Lines as MegaMek 0.51.01.7's own Coords.intervening gives them (CASPAR's review, 2026-11-19: the port matched it on
    /// every pair of an 11 x 11 board, 14,641 lines). These cover edge-runs, 30-degree lines (the fdlibm atan) and zig-zags.
    #[test]
    fn hex_line_matches_megamek() {
        let cases: [(&str, &str); 6] = [
            ("0,0 1,10", "0,0 0,1 0,2 0,3 1,3 0,4 1,4 0,5 1,5 0,6 1,6 0,7 1,7 1,8 1,9 1,10"),
            ("0,0 4,6", "0,0 1,0 0,1 1,1 2,2 1,2 2,3 3,3 2,4 3,4 4,5 3,5 4,6"),
            ("0,6 4,0", "0,6 1,5 0,5 1,4 2,4 1,3 2,3 3,2 2,2 3,1 4,1 3,0 4,0"),
            ("3,3 7,9", "3,3 4,4 3,4 4,5 5,5 4,6 5,6 6,7 5,7 6,8 7,8 6,9 7,9"),
            ("5,5 5,0", "5,5 5,4 5,3 5,2 5,1 5,0"),
            ("10,0 0,10", "10,0 9,0 9,1 8,2 7,2 7,3 6,4 5,4 5,5 4,6 3,6 3,7 2,8 1,8 1,9 0,10"),
        ];
        let xy = |s: &str| -> (i64, i64) {
            let (a, b) = s.split_once(',').unwrap();
            (a.parse().unwrap(), b.parse().unwrap())
        };
        for (ends, want) in cases {
            let (a, b) = ends.split_once(' ').unwrap();
            let got: Vec<String> = mm_intervening(xy(a), xy(b)).iter().map(|(x, y)| format!("{},{}", x, y)).collect();
            assert_eq!(got.join(" "), want, "line {}", ends);
        }
    }
}
