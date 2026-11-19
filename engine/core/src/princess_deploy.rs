// MegaMek's bot deployment, for Princess and CASPAR units placed in a deployment zone (session 30; Daniel, 2026-11-19: "If both
// are supposed to use it in megamek, it should be ported for both. Its the only way to get authentic results from our captured
// bots."). Read from MegaMek main 0cc7d65:
//   BotClient.getStartingCoordsArray   every legal hex of the zone, shuffled, given a fitness and sorted best first;
//   Princess.getFirstValidCoords       (CASPAR: MutualSupportDeployment.prioritize reorders the list for the formation), then
//   Princess.rankDeploymentCoords      scans the front of the list: hexes grouped by their hazard, the scan stopping once a
//                                      group passes 20 hexes or there are more than 20 groups; of the safest group, the hex
//                                      with the best
//   Princess.rankKernelAroundCoords    "room to move": how many hexes it can reach with 3 MP, how far, through what hazards;
//   Princess.getDeploymentFacing       toward the first enemy on the board, else the board's middle (CASPAR: toward the
//                                      enemy zones' middle first, Caspar.facesEnemyZoneAtDeployment).
// Ported for 'Mechs (the only units here). Where MegaMek asks its own rules engine (to-hit, terrain costs, hazards), this asks
// this engine's: the to-hit of each weapon (`attack_resolution::weapon_attack_tns`), the step costs (`terrain_rules`), the
// Princess clone's hazards (`princess::hex_hazard`). Not ported, because nothing here has them: infantry, vehicle, ProtoMek and
// aerospace terms, C3 (x1.25 range), tow links, unit orders, bridges (MegaMek's bridge-top clusters), board-leveling costs (a
// building counts as levelable, impassable terrain as not). Deployment order: this engine places a team at a time (MegaMek
// interleaves by initiative), so "the enemies already on the board" are the teams placed before.
// Credit: MegaMek Team, GPL v3 or later (CREDITS.md).
use crate::fasthash::HashMap;

use crate::battle::{Battle, UnitId};
use crate::caspar::{mm_direction, mm_translated};
use crate::hex_geometry;
use crate::mech_state::*;
use crate::princess_memory::{cols_rows_to_label, label_to_cols_rows};
use crate::princess_geometry::mm_distance;
use crate::terrain_rules;

/// Princess.rankDeploymentCoords: the scan stops once a hazard group holds more than this many hexes (or there are more groups).
const SCAN_LIMIT: usize = 20;
/// Princess.rankDeploymentCoords: the "room to move" kernel's MP (RADIUS).
const KERNEL_RADIUS: i64 = 3;
/// BotClient.getStartingCoordsArray: only enemies closer than this count as attackers.
const ATTACKER_RANGE: i64 = 18;
/// BotClient.expectedHitsByRackSize (MegaMek's missile table, interpolated for odd sizes; index = rack size).
const EXPECTED_HITS_BY_RACK: [f32; 21] = [0.0, 1.0, 1.58, 2.0, 2.63, 3.17, 4.0, 4.49, 4.98, 5.47, 6.31, 7.23, 8.14, 8.59, 9.04, 9.5, 0.0, 0.0, 0.0, 0.0, 12.7];

/// Where a Princess-family unit deploys, and facing which way.
pub struct Placement {
    pub hex: String,
    pub facing: &'static str,
    pub note: String,
}

/// The cluster maps (BoardClusterTracker) a team's bot keeps: MegaMek builds them once per movement type, from the first unit
/// that asks, and keeps them for the game. One per team here, kept for the team's whole deployment.
#[derive(Default)]
pub struct Clusters {
    plain: Option<HashMap<(i64, i64), usize>>,
    leveled: Option<HashMap<(i64, i64), usize>>,
    sizes_plain: Vec<usize>,
    sizes_leveled: Vec<usize>,
    members_plain: Vec<Vec<(i64, i64)>>,
    members_leveled: Vec<Vec<(i64, i64)>>,
}

/// Java's Double.compare (NaN equal to itself and above everything; -0.0 below 0.0): MegaMek sorts fitness with it, and a
/// unit with no weapons gets NaN everywhere (its average range is 0 / 0).
fn java_compare(a: f64, b: f64) -> std::cmp::Ordering {
    use std::cmp::Ordering::*;
    match (a.is_nan(), b.is_nan()) {
        (true, true) => Equal,
        (true, false) => Greater,
        (false, true) => Less,
        _ => a.partial_cmp(&b).unwrap().then_with(|| (a.to_bits() as i64 >= 0).cmp(&(b.to_bits() as i64 >= 0))),
    }
}

/// MegaMek's own (column, row) from 0 for a hex label.
fn mm(label: &str) -> (i64, i64) {
    label_to_cols_rows(label)
}

fn on_board(b: &Battle, c: (i64, i64)) -> Option<String> {
    if c.0 < 0 || c.1 < 0 {
        return None;
    }
    let l = cols_rows_to_label(c.0, c.1);
    b.board.hexes.contains_key(&l).then_some(l)
}

/// Hex.getLevel: the ground (a water hex's surface, a building's ground floor), as MegaMek's board keeps it.
fn mm_level(h: &crate::board_parser::Hex) -> i64 {
    h.surface_level.or(h.ground_level).unwrap_or(h.level)
}

/// Entity.isLocationProhibited for a 'Mech: terrain it may not enter at all (this engine's step cost from off the board).
fn prohibited(h: &crate::board_parser::Hex) -> bool {
    terrain_rules::step_cost(None, h, terrain_rules::max_level_change(false, false), false).is_none()
}

/// The building's current CF in a hex (bldg_cf), if it has one.
fn building_cf(h: &crate::board_parser::Hex) -> Option<i64> {
    if !h.features.has("building") {
        return None;
    }
    h.features.first_param("bldg_cf").and_then(|v| v.parse::<i64>().ok())
}

/// BoardClusterTracker.buildingPlowThroughRequired for a walking 'Mech: a building too weak for its weight.
fn plow_through(b: &Battle, u: UnitId, h: &crate::board_parser::Hex) -> bool {
    building_cf(h).is_some_and(|cf| b.units[u].mass.unwrap_or(0) > cf)
}

/// BoardEdgePathFinder.calculateUnitElevationInHex for a 'Mech: a building's roof, a water hex's floor, else the ground -
/// this engine's `level` is already exactly that.
fn unit_elevation(h: &crate::board_parser::Hex) -> i64 {
    h.level
}

/// BoardClusterTracker.generateClusters for a walking 'Mech: hexes it can stand in, joined where the level change between
/// neighbours is within its limit. `leveled`: the destruction-aware version (a building it would have to plow through counts
/// as passable, MegaMek's "terrain reduction"). Returns (cluster of each hex, members of each cluster).
fn generate_clusters(b: &Battle, u: UnitId, leveled: bool) -> (HashMap<(i64, i64), usize>, Vec<Vec<(i64, i64)>>) {
    let limit = terrain_rules::max_level_change(ground_level_limited(&b.units[u]), is_superheavy(&b.units[u])).value;
    let mut of: HashMap<(i64, i64), usize> = HashMap::default();
    let mut members: Vec<Vec<(i64, i64)>> = Vec::new();
    for x in 0..b.board.width {
        for y in 0..b.board.height {
            let c = (x, y);
            let Some(l) = on_board(b, c) else { continue };
            let h = &b.board.hexes[&l];
            // (prohibited or plow-through) and not (destruction aware and levelable): impassable is never levelable here,
            // a building always is
            if prohibited(h) || (plow_through(b, u, h) && !leveled) {
                continue;
            }
            let mine = unit_elevation(h);
            let mut join: Vec<(i64, i64)> = Vec::new();
            let mut biggest: Option<usize> = None;
            for d in 0..6 {
                let n = mm_translated(c, d);
                let Some(&nc) = of.get(&n) else { continue };
                let nh = &b.board.hexes[&on_board(b, n).unwrap()];
                if (unit_elevation(nh) - mine).abs() > limit || plow_through(b, u, nh) {
                    continue;
                }
                join.push(n);
                if biggest.map_or(true, |bc| members[nc].len() > members[bc].len()) {
                    biggest = Some(nc);
                }
            }
            match biggest {
                None => {
                    of.insert(c, members.len());
                    members.push(vec![c]);
                }
                Some(bc) => {
                    members[bc].push(c);
                    of.insert(c, bc);
                    for n in join {
                        let old = of[&n];
                        if old == bc {
                            continue;
                        }
                        let moved = std::mem::take(&mut members[old]);
                        for m in moved {
                            of.insert(m, bc);
                            members[bc].push(m);
                        }
                    }
                }
            }
        }
    }
    (of, members)
}

impl Clusters {
    fn ensure(&mut self, b: &Battle, u: UnitId) {
        if self.plain.is_none() {
            let (of, members) = generate_clusters(b, u, false);
            self.sizes_plain = members.iter().map(|m| m.len()).collect();
            self.plain = Some(of);
            self.members_plain = members;
            let (of, members) = generate_clusters(b, u, true);
            self.sizes_leveled = members.iter().map(|m| m.len()).collect();
            self.leveled = Some(of);
            self.members_leveled = members;
        }
    }

    /// getBoardClusterSize (no terrain reduction): the size of the area the unit can walk to from a hex.
    fn size_at(&self, c: (i64, i64)) -> usize {
        self.plain.as_ref().unwrap().get(&c).map_or(0, |i| self.sizes_plain[*i])
    }

    /// getDestinationCoords(edge): does the hex's cluster reach the edge?
    fn reaches_edge(&self, b: &Battle, c: (i64, i64), edge: char, leveled: bool) -> bool {
        let (of, members) = if leveled { (self.leveled.as_ref().unwrap(), &self.members_leveled) } else { (self.plain.as_ref().unwrap(), &self.members_plain) };
        let Some(i) = of.get(&c) else { return false };
        members[*i].iter().any(|(x, y)| match edge {
            'N' => *y == 0,
            'S' => *y == b.board.height - 1,
            'E' => *x == b.board.width - 1,
            _ => *x == 0,
        })
    }
}

/// BoardUtilities.determineOppositeEdge: the far edge from a zone that is a whole board edge (MegaMek's N / S / E / W start),
/// otherwise from the edge nearest the hex (getClosestEdge: vertical wins a tie).
fn opposite_edge(b: &Battle, boxes: &[bool; 9], c: (i64, i64)) -> char {
    let only = |set: [usize; 3]| (0..9).all(|i| boxes[i] == set.contains(&i));
    if only([0, 1, 2]) {
        return 'S';
    }
    if only([6, 7, 8]) {
        return 'N';
    }
    if only([0, 3, 6]) {
        return 'E';
    }
    if only([2, 5, 8]) {
        return 'W';
    }
    let (w, e, n, s) = (c.0, b.board.width - c.0, c.1, b.board.height - c.1);
    let closest = if w.min(e) < n.min(s) { if w < e { 'W' } else { 'E' } } else if n < s { 'N' } else { 'S' };
    match closest {
        'W' => 'E',
        'E' => 'W',
        'N' => 'S',
        _ => 'N',
    }
}

/// BotClient.getDeployDamage: a weapon's expected damage from where the shooter stands, by this engine's to-hit. A missile rack
/// (MegaMek's damage-by-cluster-table weapons) needs ammo and uses MegaMek's table (a Streak its whole rack, a 30 or 40 rack
/// twice the table at half size); anything else its damage.
fn deploy_damage(b: &mut Battle, shooter: UnitId, w: usize, tn: i64) -> f64 {
    if tn > 12 {
        return 0.0;
    }
    let chance = crate::combat::hit_probability(tn) as f32;
    let Some(dps) = b.units[shooter].items[w].damage_per_shot else { return 0.0 };
    let damage = if crate::weapon_rules::is_cluster(b, shooter, w) {
        if crate::ams::shots_left(&b.units[shooter], w) <= 0.0 {
            return 0.0;
        }
        let rack = b.units[shooter].items[w].rack_size.unwrap_or(0);
        let hits = if crate::weapon_rules::is_streak(b, shooter, w) {
            rack as f32
        } else if rack == 40 || rack == 30 {
            2.0 * EXPECTED_HITS_BY_RACK[(rack / 2) as usize]
        } else {
            EXPECTED_HITS_BY_RACK.get(rack as usize).copied().unwrap_or(0.0)
        };
        hits * dps as f32
    } else {
        dps as f32
    };
    (damage * chance) as f64
}

/// The standard attack TN of each weapon of `shooter` at `target` (None = no attack possible at all).
fn tns(b: &mut Battle, shooter: UnitId, target: UnitId) -> Vec<(usize, i64)> {
    let weapons: Vec<usize> = crate::damage_resolution::get_weapons(&b.units[shooter]).into_iter().filter(|w| !crate::weapon_rules::is_ams(b, shooter, *w)).collect();
    crate::attack_resolution::weapon_attack_tns(b, shooter, target, &weapons, false).map_or(Vec::new(), |r| r.0)
}

/// The unit's average long range for the ideal height (BotClient.getStartingCoordsArray): every weapon's long range but an
/// ATM's, plus each ATM bin as 15 (HE -6, ER +12), each over the weapon count; an MML bin SETS the sum to 9 (LRM) or 21 (SRM),
/// as MegaMek's code does.
fn average_range(b: &mut Battle, u: UnitId) -> f64 {
    let (mut sum, mut count) = (0.0f64, 0i64);
    for w in crate::damage_resolution::get_weapons(&b.units[u]) {
        let name = b.units[u].items[w].name.to_uppercase().replace([' ', '-'], "");
        if name.contains("ATM") && !name.contains("IATM") {
            continue;
        }
        sum += b.units[u].items[w].weapon_range.as_ref().map_or(0, |r| r.long) as f64;
        count += 1;
    }
    let bins: Vec<String> = b.units[u].items.iter().filter(|it| it.category.as_deref() == Some("ammo")).map(|it| it.name.to_uppercase()).collect();
    for name in bins {
        let flat = name.replace([' ', '-'], "");
        if flat.contains("ATM") && !flat.contains("IATM") {
            count += 1;
            sum += 15.0;
            if flat.contains("HE") {
                sum -= 6.0;
            }
            if flat.contains("ER") {
                sum += 12.0;
            }
        } else if flat.contains("MML") {
            count += 1;
            sum = if flat.contains("LRM") { 9.0 } else { 21.0 };
        }
    }
    sum / count as f64
}

/// BotClient.getStartingCoordsArray: the candidate hexes shuffled, each given its fitness, sorted best first (stable).
fn starting_coords(b: &mut Battle, u: UnitId, candidates: Vec<String>, boxes: &[bool; 9], clusters: &mut Clusters) -> Vec<String> {
    let mut valid = candidates;
    // Collections.shuffle: from the last place down, swap with a random place at or before it
    for i in (1..valid.len()).rev() {
        let j = (b.pick_number(i as i64 + 1) - 1) as usize;
        valid.swap(i, j);
    }
    let levels: Vec<i64> = valid.iter().map(|l| mm_level(&b.board.hexes[l])).collect();
    let (highest, lowest) = (levels.iter().copied().max().unwrap_or(0) as f64, levels.iter().copied().min().unwrap_or(0) as f64);
    let av_range = average_range(b, u);
    let m = &b.units[u];
    let mut ideal = if compute_jump_mp(m) == 0 && compute_walk_mp(m) > 5 { lowest + (highest - lowest) / 3.0 } else { lowest + (av_range / 18.0) * (highest - lowest) };
    if ideal > highest {
        ideal = highest;
    }
    let cannot_move = compute_walk_mp(m) == 0 && compute_jump_mp(m) == 0;
    let enemies: Vec<UnitId> = crate::forces::enemies_of(b, u).into_iter().filter(|e| b.units[*e].hex.is_some()).collect();
    let (saved_hex, saved_facing) = (b.units[u].hex.clone(), b.units[u].facing.clone());
    // the unit is not deployed yet: MegaMek stands it in each hex facing its starting facing, north
    b.units[u].facing = "N".into();
    let mut fitness: Vec<f64> = Vec::with_capacity(valid.len());
    for (i, label) in valid.iter().enumerate() {
        let c = mm(label);
        let mut f = -(ideal - levels[i] as f64).abs();
        b.units[u].hex = Some(label.clone());
        let attackers: Vec<UnitId> = enemies.iter().copied().filter(|e| mm_distance(c, mm(b.units[*e].hex.as_deref().unwrap())) < ATTACKER_RANGE).collect();
        let mut taken = 0.0;
        for &e in &attackers {
            for (w, tn) in tns(b, e, u) {
                taken += deploy_damage(b, e, w, tn);
            }
        }
        f -= taken / 10.0;
        let mut given: HashMap<usize, f64> = HashMap::default();
        for &e in &attackers {
            for (w, tn) in tns(b, u, e) {
                let d = deploy_damage(b, u, w, tn);
                let best = given.entry(w).or_insert(0.0);
                if d > *best {
                    *best = d;
                }
            }
        }
        let mut weapons: Vec<usize> = given.keys().copied().collect();
        weapons.sort();
        f += weapons.iter().map(|w| given[w]).sum::<f64>() / 10.0;
        // 'Mech terrain: woods tall enough to hide in, deep water, a building that could hurt it
        let h = &b.board.hexes[label];
        let foliage = h.features.first_param("foliage_elev").and_then(|v| v.parse::<i64>().ok()).unwrap_or(if h.features.first_param("woods") == Some("3") { 3 } else { 2 });
        if h.features.has("woods") && foliage > 1 {
            f += 1.0;
        }
        if h.depth.unwrap_or(0) > 1 {
            f -= h.depth.unwrap() as f64;
        }
        if let Some(cf) = building_cf(h) {
            let fails = 1.0 - crate::combat::hit_probability(b.units[u].piloting);
            f -= ((cf as f64) / 10.0).ceil() * fails;
        }
        // calculateEdgeAccessFitness: a dead end - no way to the far edge (-100), or only by levelling terrain (-50)
        if !cannot_move {
            clusters.ensure(b, u);
            let edge = opposite_edge(b, boxes, c);
            if !clusters.reaches_edge(b, c, edge, false) {
                f += if clusters.reaches_edge(b, c, edge, true) { -50.0 } else { -100.0 };
            }
        }
        fitness.push(f);
    }
    b.units[u].hex = saved_hex;
    b.units[u].facing = saved_facing;
    // every hex a dead end: prefer the biggest area the unit can reach
    let highest_fitness = fitness.iter().copied().filter(|f| !f.is_nan()).fold(-5000.0f64, f64::max);
    if highest_fitness < -10.0 && !cannot_move {
        clusters.ensure(b, u);
        for (i, label) in valid.iter().enumerate() {
            fitness[i] += clusters.size_at(mm(label)) as f64;
        }
    }
    let mut order: Vec<usize> = (0..valid.len()).collect();
    order.sort_by(|a, c| java_compare(fitness[*c], fitness[*a]));
    order.into_iter().map(|i| valid[i].clone()).collect()
}

/// checkPathForHazards for a unit standing in (or landing in) one hex, as the deployment scan and the kernel ask it.
fn hazard(b: &Battle, u: UnitId, label: &str, end_hex: bool, jump_landing: bool) -> f64 {
    let water = move |bb: &Battle, _l: &str, depth: i64, _end: bool, prone: bool| -> f64 { crate::princess_modern::water_hazard(bb, u, depth, prone, 0.0, true) };
    crate::princess::hex_hazard(b, u, label, end_hex, jump_landing, false, Some(&water))
}

/// Princess.rankKernelAroundCoords: lower is better. The 24 hexes 4 away, less the hexes the unit can reach from `c` with 3 MP
/// (never below 0), less the hexes moved on the cheapest path to each, plus each path's hazards. A unit with jump MP is
/// started jumping (MegaMek's START_JUMP): every hex within its jump, at most 3 away, by the straight line.
fn kernel_rank(b: &Battle, u: UnitId, start: &str) -> f64 {
    let c = mm(start);
    let jump = compute_jump_mp(&b.units[u]);
    let enemy_at: Vec<(i64, i64)> = b.units.iter().enumerate().filter(|(i, m)| m.team != b.units[u].team && m.hex.is_some() && !m.destroyed && *i != u).map(|(_, m)| mm(m.hex.as_deref().unwrap())).collect();
    let mut paths: Vec<(i64, f64)> = Vec::new(); // (hexes moved, hazard) of the cheapest path to each reachable hex
    if jump > 0 {
        let reach = jump.min(KERNEL_RADIUS);
        for x in (c.0 - reach)..=(c.0 + reach) {
            for y in (c.1 - reach - 1)..=(c.1 + reach + 1) {
                let d = mm_distance(c, (x, y));
                if d > reach {
                    continue;
                }
                let Some(l) = on_board(b, (x, y)) else { continue };
                if d > 0 && (prohibited(&b.board.hexes[&l]) || enemy_at.contains(&(x, y))) {
                    continue;
                }
                paths.push((d, hazard(b, u, &l, true, true)));
            }
        }
    } else {
        // the cheapest walk to every (hex, facing) with 3 MP: forward steps at this engine's terrain cost, turns at 1 MP
        let limit = terrain_rules::max_level_change(ground_level_limited(&b.units[u]), is_superheavy(&b.units[u]));
        let facing0 = 0i64; // the unit stands facing north, as it was ranked (MegaMek's undeployed facing)
        let mut best: HashMap<((i64, i64), i64), (i64, u64)> = HashMap::default();
        let mut came: HashMap<((i64, i64), i64), ((i64, i64), i64)> = HashMap::default();
        let mut heap = std::collections::BinaryHeap::new();
        let mut seq = 0u64;
        best.insert((c, facing0), (0, seq));
        heap.push(std::cmp::Reverse((0i64, seq, c, facing0)));
        while let Some(std::cmp::Reverse((mp, s, pos, f))) = heap.pop() {
            if best.get(&(pos, f)).map_or(true, |v| v.1 != s) {
                continue;
            }
            let here = on_board(b, pos).unwrap();
            let mut next: Vec<(i64, (i64, i64), i64)> = vec![(mp + 1, pos, (f + 1) % 6), (mp + 1, pos, (f + 5) % 6)];
            let ahead = mm_translated(pos, f);
            if let Some(l) = on_board(b, ahead) {
                if !enemy_at.contains(&ahead) {
                    if let Some(cost) = terrain_rules::step_cost(Some(&b.board.hexes[&here]), &b.board.hexes[&l], limit, false) {
                        next.push((mp + cost, ahead, f));
                    }
                }
            }
            for (nmp, npos, nf) in next {
                if nmp > KERNEL_RADIUS {
                    continue;
                }
                if best.get(&(npos, nf)).map_or(true, |v| nmp < v.0) {
                    seq += 1;
                    best.insert((npos, nf), (nmp, seq));
                    came.insert((npos, nf), (pos, f));
                    heap.push(std::cmp::Reverse((nmp, seq, npos, nf)));
                }
            }
        }
        // per hex the cheapest facing (the lowest facing on a tie, MegaMek's Collections.min over the facings in order)
        let mut hexes: Vec<(i64, i64)> = best.keys().map(|k| k.0).collect();
        hexes.sort();
        hexes.dedup();
        for h in hexes {
            let f = (0..6).filter(|f| best.contains_key(&(h, *f))).min_by_key(|f| best[&(h, *f)].0).unwrap();
            // walk the path back: its hexes, start first
            let mut states = vec![(h, f)];
            while let Some(p) = came.get(states.last().unwrap()) {
                states.push(*p);
            }
            states.reverse();
            let mut cells: Vec<(i64, i64)> = Vec::new();
            for (p, _) in &states {
                if cells.last() != Some(p) {
                    cells.push(*p);
                }
            }
            let moved = cells.len() as i64 - 1;
            let n = cells.len();
            let hz: f64 = cells.iter().enumerate().map(|(i, p)| hazard(b, u, &on_board(b, *p).unwrap(), i == n - 1, false)).sum();
            paths.push((moved, hz));
        }
    }
    let kernel = 6 * (KERNEL_RADIUS + 1);
    let mut rank = (kernel - paths.len() as i64).max(0) as f64;
    for (moved, hz) in paths {
        rank -= moved as f64;
        rank += hz;
    }
    rank
}

/// Princess.getDeploymentFacing (+ DeploymentPlanner.deploymentFacing for CASPAR): CASPAR faces the middle of the enemy zones
/// when there is one and it is not this hex; otherwise both face the first enemy already on the board, else the board's middle.
fn deployment_facing(b: &Battle, u: UnitId, hex: &str, enemy_zone_centre: Option<(i64, i64)>) -> &'static str {
    let c = mm(hex);
    if b.units[u].bot == "caspar" {
        if let Some(z) = enemy_zone_centre.filter(|z| *z != c) {
            return hex_geometry::COMPASS_BY_FACING[mm_direction(c, z) as usize];
        }
    }
    for (i, m) in b.units.iter().enumerate() {
        if i != u && m.team != b.units[u].team && !m.destroyed {
            if let Some(h) = m.hex.as_deref() {
                return hex_geometry::COMPASS_BY_FACING[mm_direction(c, mm(h)) as usize];
            }
        }
    }
    hex_geometry::COMPASS_BY_FACING[mm_direction(c, (b.board.width / 2, b.board.height / 2)) as usize]
}

/// EnemyDeploymentZone.center: each enemy team's zone middle (the mean of its hexes, Java integer division, on MegaMek's
/// coordinates), and the mean of those.
pub fn enemy_zone_centre(b: &Battle, zones: &serde_json::Value, me: &str) -> Option<(i64, i64)> {
    let (mut tx, mut ty, mut n) = (0i64, 0i64, 0i64);
    for (name, z) in zones.as_object()? {
        if name == me {
            continue;
        }
        let mut boxes = [true; 9];
        if let Some(arr) = z["boxes"].as_array() {
            for (i, v) in arr.iter().take(9).enumerate() {
                boxes[i] = v.as_bool().unwrap_or(false);
            }
        }
        let hexes = crate::deployment::zone_hexes(b, &boxes);
        if hexes.is_empty() {
            continue;
        }
        let pts: Vec<(i64, i64)> = hexes.iter().map(|h| mm(h)).collect();
        let k = pts.len() as i64;
        tx += pts.iter().map(|p| p.0).sum::<i64>() / k;
        ty += pts.iter().map(|p| p.1).sum::<i64>() / k;
        n += 1;
    }
    (n > 0).then(|| (tx / n, ty / n))
}

/// The whole choice for one Princess or CASPAR unit: `candidates` = the zone's hexes it may stand in (free, enterable).
pub fn choose(b: &mut Battle, u: UnitId, candidates: Vec<String>, boxes: &[bool; 9], enemy_zone: Option<(i64, i64)>, clusters: &mut Clusters) -> Option<Placement> {
    if candidates.is_empty() {
        return None;
    }
    let mut ordered = starting_coords(b, u, candidates, boxes, clusters);
    if b.units[u].bot == "caspar" {
        ordered = crate::caspar::prefer_formation(b, u, ordered);
    }
    // rankDeploymentCoords: group the front of the list by hazard until a group passes the limit
    let mut groups: Vec<(f64, Vec<String>)> = Vec::new();
    for dest in &ordered {
        let key = -hazard(b, u, dest, true, false);
        match groups.iter_mut().find(|(k, _)| k.to_bits() == key.to_bits()) {
            Some(g) => g.1.push(dest.clone()),
            None => groups.push((key, vec![dest.clone()])),
        }
        let longest = groups.iter().map(|g| g.1.len()).max().unwrap_or(0);
        if longest > SCAN_LIMIT || groups.len() > SCAN_LIMIT {
            break;
        }
    }
    let best_rank = groups.iter().map(|g| g.0).fold(f64::NEG_INFINITY, f64::max);
    let group = groups.iter().find(|g| g.0 == best_rank).map(|g| g.1.clone()).unwrap_or_default();
    let cannot_move = compute_walk_mp(&b.units[u]) == 0 && compute_jump_mp(&b.units[u]) == 0;
    let (mut pick, mut score) = (None, f64::MIN);
    for c in &group {
        let current = best_rank - if cannot_move { 0.0 } else { kernel_rank(b, u, c) };
        if current > score {
            score = current;
            pick = Some(c.clone());
        }
    }
    let hex = pick.unwrap_or_else(|| ordered[0].clone());
    let facing = deployment_facing(b, u, &hex, enemy_zone);
    let note = format!("{} of {} hexes scanned, {} in the safest group, room-to-move score {}", groups.iter().map(|g| g.1.len()).sum::<usize>(), ordered.len(), group.len(), crate::pyfmt::Fx(score, 2));
    Some(Placement { hex, facing, note })
}
