// Translated from INTEGRATION__princess_modern.py and the Group / posture parts of INTEGRATION__princess_group.py: the
// modern Princess's movement ranker (BasicPathRanker.rankPath) and what she knows because there is a battle around her.
use crate::fasthash::HashMap;

use crate::attack_resolution as ar;
use crate::battle::{Battle, UnitId};
use crate::combat::hit_probability;
use crate::hex_geometry;
use crate::los::hex_distance;
use crate::mech_state::*;
use crate::move_eval::MoveEvaluator;
use crate::move_options::{self, Opt};
use crate::physical::{self, PhysOption};
use crate::princess::{self, UNIT_DESTRUCTION_FACTOR};
use crate::princess_fire::{self, FireControl};
use crate::princess_memory::{cols_rows_to_label, label_to_cols_rows};
use crate::pyfmt::{py_float_str, Fx};
use crate::ranged_combat::Pick;

const THREAT_CONTACT_RANGE: i64 = 15;
const TEMPO_REFERENCE_MP: f64 = 15.0;
const REPRESENTATIVE_TO_HIT: i64 = 8;
const ESTIMATE_NOISE_MARGIN: f64 = 5.0;
const HOLD_CREDIT_ATTACK_CAP_FACTOR: f64 = 0.4;
const HOLD_CREDIT_DEFEND_CAP_FACTOR: f64 = 0.8;
const CLOSE_RANGE_BAND: f64 = 12.0;
const CLOSE_RANGE_INCENTIVE_WEIGHT: f64 = 1.0;
const PHYSICAL_PILOT_HIT_WEIGHT: f64 = 100.0;
const PHYSICAL_CRIT_WEIGHT: f64 = 30.0;
const CLOSING_THRESHOLD: f64 = 0.5;
const DEFEND_EXIT_THRESHOLD: f64 = 0.1;
const CLOSING_WINDOW_ROUNDS: i64 = 3;
const MUTUAL_SUPPORT_VALUES: [f64; 11] = [0.1, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0];
const DEFAULT_ENEMIES_TO_FACE: i64 = 4;
const ATTACK: &str = "ATTACK";
const DEFEND: &str = "DEFEND";

fn java_round(x: f64) -> i64 {
    (x + 0.5).floor() as i64
}

fn cols_rows(xy: (i64, i64)) -> (i64, i64) {
    label_to_cols_rows(&hex_geometry::hex_label(xy.0, xy.1).unwrap())
}

fn xy_of(col: i64, row: i64) -> (i64, i64) {
    hex_geometry::parse_hex_label(&cols_rows_to_label(col, row)).unwrap()
}

/// Coords.median: Weiszfeld's algorithm on (column, row), truncated to a hex.
fn geometric_median(points: &[(i64, i64)]) -> Option<(i64, i64)> {
    if points.is_empty() {
        return None;
    }
    if points.len() == 1 {
        return Some(points[0]);
    }
    let n = points.len() as f64;
    let mut cx = points.iter().map(|p| p.0 as f64).sum::<f64>() / n;
    let mut cy = points.iter().map(|p| p.1 as f64).sum::<f64>() / n;
    for _ in 0..1000 {
        let (mut num_x, mut num_y, mut den) = (0.0, 0.0, 0.0);
        for &(px, py) in points {
            let dist = ((px as f64 - cx).hypot(py as f64 - cy)) as f64;
            if dist < 1e-15 {
                return Some((px, py));
            }
            let w = 1.0 / dist;
            num_x += px as f64 * w;
            num_y += py as f64 * w;
            den += w;
        }
        let (new_x, new_y) = (num_x / den, num_y / den);
        let shift = (cx - new_x).hypot(cy - new_y);
        cx = new_x;
        cy = new_y;
        if shift < 1e-7 {
            break;
        }
    }
    Some((cx as i64, cy as i64))
}

/// The battle as one Princess unit sees it while it picks a move.
pub struct Group {
    pub mover: UnitId,
    pub other: Option<UnitId>,
    pub moves_first: bool,
    pub foes: Vec<UnitId>,
    pub friends: Vec<UnitId>,
    support_value: f64,
    anti_crowding: i64,
    enemies_to_face: i64,
    anchor: Option<(i64, i64)>,
    group_on: bool,
}

impl Group {
    pub fn new(b: &mut Battle, mover: UnitId, other: Option<UnitId>, moves_first: bool) -> Group {
        let mut foes: Vec<UnitId> = crate::forces::enemies_of(b, mover).into_iter().filter(|f| b.units[*f].hex.is_some()).collect();
        if let Some(o) = other {
            if b.units[o].hex.is_some() && !foes.contains(&o) {
                foes.push(o);
            }
        }
        let standing = crate::forces::standing(b);
        let team = b.units[mover].team.clone();
        let friends: Vec<UnitId> = standing.into_iter().filter(|u| b.units[*u].team == team && *u != mover && b.units[*u].hex.is_some()).collect();
        let beh = b.cfg.get("PRINCESS_BEHAVIOR").clone();
        let support_value = MUTUAL_SUPPORT_VALUES[beh["mutual_support"].as_i64().unwrap_or(5).clamp(0, 10) as usize];
        let anti_crowding = beh["anti_crowding"].as_i64().unwrap_or(0);
        let enemies_to_face = beh["facing_enemies"].as_i64().unwrap_or(DEFAULT_ENEMIES_TO_FACE).max(1);
        let group_on = b.cfg.b("PRINCESS_GROUP");
        let mut g = Group { mover, other, moves_first, foes, friends, support_value, anti_crowding, enemies_to_face, anchor: None, group_on };
        g.anchor = g.find_anchor(b);
        g
    }

    /// Princess.evaluateAsMoved: the enemy has taken its movement this turn, or can't move.
    pub fn has_moved(&self, b: &Battle, foe: UnitId) -> bool {
        if Some(foe) == self.other {
            return !self.moves_first || is_immobile(&b.units[foe]);
        }
        b.units[foe].moved_this_turn || is_immobile(&b.units[foe])
    }

    fn adjusted(&self, b: &Battle, foe: UnitId, raw: i64) -> i64 {
        raw + if self.has_moved(b, foe) { 0 } else { compute_walk_mp(&b.units[foe]) }
    }

    fn foe_xy(b: &Battle, f: UnitId) -> (i64, i64) {
        hex_geometry::parse_hex_label(b.units[f].hex.as_deref().unwrap()).unwrap()
    }

    /// (enemy, raw distance) - PathRanker.findClosestEnemy.
    pub fn nearest(&self, b: &Battle, spot: (i64, i64), min_distance: i64) -> Option<(UnitId, i64)> {
        let mut best: Option<(i64, UnitId, i64)> = None;
        for &foe in &self.foes {
            let raw = hex_distance(spot, Self::foe_xy(b, foe));
            if raw < min_distance {
                continue;
            }
            let adj = self.adjusted(b, foe, raw);
            if best.map_or(true, |(a, _, _)| adj < a) {
                best = Some((adj, foe, raw));
            }
        }
        best.map(|(_, f, r)| (f, r))
    }

    pub fn distance_to_enemy(&self, b: &Battle, spot: (i64, i64)) -> Option<i64> {
        self.nearest(b, spot, 0).map(|g| g.1)
    }

    /// FacingDiffCalculator.selectOneCoordsToFace.
    pub fn face_target(&self, b: &Battle, spot: (i64, i64)) -> Option<(i64, i64)> {
        if let Some((f, raw)) = self.nearest(b, spot, 1) {
            if raw == 1 {
                return Some(Self::foe_xy(b, f));
            }
        }
        let mut ranked: Vec<UnitId> = self.foes.clone();
        ranked.sort_by_key(|f| self.adjusted(b, *f, hex_distance(spot, Self::foe_xy(b, *f))).max(0));
        let points: Vec<(i64, i64)> = ranked.iter().take(self.enemies_to_face as usize).map(|f| cols_rows(Self::foe_xy(b, *f))).collect();
        geometric_median(&points).map(|(c, r)| xy_of(c, r))
    }

    fn find_anchor(&self, b: &mut Battle) -> Option<(i64, i64)> {
        let mover = self.mover;
        let hex = b.units[mover].hex.clone()?;
        if !self.group_on {
            return None;
        }
        let team = b.units[mover].team.clone().unwrap_or_default();
        let spot = crate::princess_memory::team(b, &team).heat.hot_spot(&hex);
        if let Some(s) = spot {
            return Some(hex_geometry::parse_hex_label(&s).unwrap());
        }
        if self.friends.is_empty() {
            return None;
        }
        let cols: Vec<(i64, i64)> = self.friends.iter().map(|f| cols_rows(Self::foe_xy(b, *f))).collect();
        let n = cols.len() as f64;
        let col = java_round(cols.iter().map(|c| c.0 as f64).sum::<f64>() / n);
        let row = java_round(cols.iter().map(|c| c.1 as f64).sum::<f64>() / n);
        Some(xy_of(col, row))
    }

    /// BasicPathRanker.calculateMutualSupportMod.
    pub fn support_mod(&self, spot: (i64, i64)) -> f64 {
        match self.anchor {
            None => 0.0,
            Some(a) => hex_distance(spot, a) as f64 * self.support_value,
        }
    }

    /// BasicPathRanker.calculateCrowdingTolerance (default 0 = off).
    pub fn crowding_mod(&self, b: &Battle, spot: (i64, i64), max_range: i64) -> f64 {
        let anti = self.anti_crowding;
        if anti == 0 || !self.group_on {
            return 0.0;
        }
        let factor = 10.0 / (11 - anti) as f64;
        let friend_distance = (anti as f64 * 1.3).ceil() as i64;
        let closing_distance = (3.0f64).max(max_range as f64 * 0.6).ceil() as i64;
        let mut crowd_friends = self.friends.iter().filter(|f| hex_distance(spot, Self::foe_xy(b, **f)) <= friend_distance).count();
        if hex_distance(spot, Self::foe_xy(b, self.mover)) <= friend_distance {
            crowd_friends += 1;
        }
        let crowd_enemies = self.foes.iter().filter(|f| hex_distance(spot, Self::foe_xy(b, **f)) <= closing_distance).count();
        factor * (crowd_friends + crowd_enemies) as f64
    }
}

/// PostureResolver.resolveAuto: one call a round (the first Princess unit to move) decides for the whole team.
pub fn force_posture(b: &mut Battle, mover: UnitId, group: &Group) -> String {
    let team = b.units[mover].team.clone().unwrap_or_default();
    let round = b.units[mover].turn_number;
    {
        let memory = crate::princess_memory::team(b, &team);
        if memory.posture_round == Some(round) {
            return memory.posture.clone();
        }
        memory.posture_round = Some(round);
    }
    let standing = crate::forces::standing(b);
    let own: Vec<UnitId> = standing.into_iter().filter(|u| b.units[*u].team.as_deref() == Some(team.as_str()) && b.units[*u].hex.is_some()).collect();
    if own.is_empty() || group.foes.is_empty() {
        crate::princess_memory::team(b, &team).posture = ATTACK.to_string();
        return ATTACK.to_string();
    }
    let cols: Vec<(i64, i64)> = own.iter().map(|u| cols_rows(Group::foe_xy(b, *u))).collect();
    let n = cols.len() as f64;
    let centre = xy_of(java_round(cols.iter().map(|c| c.0 as f64).sum::<f64>() / n), java_round(cols.iter().map(|c| c.1 as f64).sum::<f64>() / n));
    let distances: Vec<f64> = group.foes.iter().map(|f| hex_distance(centre, Group::foe_xy(b, *f)) as f64).collect();
    let mean = distances.iter().sum::<f64>() / distances.len() as f64;
    let memory = crate::princess_memory::team(b, &team);
    memory.mean_distance_by_round.insert(round, mean);
    let old: Vec<i64> = memory.mean_distance_by_round.keys().copied().filter(|r| *r < round - CLOSING_WINDOW_ROUNDS).collect();
    for r in old {
        memory.mean_distance_by_round.shift_remove(&r);
    }
    let baseline = (round - CLOSING_WINDOW_ROUNDS..round).find(|r| memory.mean_distance_by_round.contains_key(r)).unwrap_or(round);
    if baseline == round {
        memory.posture = ATTACK.to_string();
        return ATTACK.to_string();
    }
    let closing = (memory.mean_distance_by_round[&baseline] - mean) / (round - baseline) as f64;
    memory.posture = if memory.posture == DEFEND {
        if closing > DEFEND_EXIT_THRESHOLD { DEFEND } else { ATTACK }
    } else if closing >= CLOSING_THRESHOLD {
        DEFEND
    } else {
        ATTACK
    }
    .to_string();
    memory.posture.clone()
}

// =============================================================================================================
// hex properties, discounts, pieces of the score
// =============================================================================================================
/// HexPropertiesMap.at: (concealment, concealment edge, partial cover, heat sink).
fn hex_properties(b: &Battle, label: &str) -> (i64, bool, bool, bool) {
    let hexes = &b.board.hexes;
    let concealment = |l: &str| crate::los::target_woods_modifier(crate::los::woods_density(&hexes[l]).as_deref());
    let conceal = concealment(label);
    let mut edge = false;
    if conceal > 0 {
        let xy = hex_geometry::parse_hex_label(label).unwrap();
        for d in 0..6 {
            let Ok(n) = hex_geometry::hex_label(princess_neighbor(xy, d).0, princess_neighbor(xy, d).1) else { continue };
            if hexes.contains_key(&n) && concealment(&n) == 0 {
                edge = true;
                break;
            }
        }
    }
    let depth = crate::water::depth_at(&b.board, Some(label));
    (conceal, edge, depth == 1, depth >= 1)
}

fn princess_neighbor(xy: (i64, i64), d: i64) -> (i64, i64) {
    crate::princess_geometry::neighbor(xy, d)
}

fn odds_ratio(modifiers: i64) -> f64 {
    if modifiers <= 0 {
        return 1.0;
    }
    hit_probability(REPRESENTATIVE_TO_HIT + modifiers) / hit_probability(REPRESENTATIVE_TO_HIT)
}

fn terrain_discount(b: &Battle, label: &str) -> f64 {
    let (conceal, edge, partial, _) = hex_properties(b, label);
    odds_ratio((if edge { conceal } else { 0 }) + if partial { 1 } else { 0 })
}

fn estimated_melee_damage(m: &Mech) -> i64 {
    if m.prone || compute_walk_mp(m) <= 0 {
        return 0;
    }
    (m.mass.unwrap_or(0) as f64 / 5.0).floor() as i64
}

fn close_range_incentive(b: &mut Battle, u: UnitId, dist: i64, max_at: &mut HashMap<i64, i64>) -> f64 {
    if dist < 1 || dist as f64 >= CLOSE_RANGE_BAND {
        return 0.0;
    }
    let mut at = |b: &mut Battle, rng: i64| -> i64 {
        if let Some(v) = max_at.get(&rng) {
            return *v;
        }
        let v = princess_fire::max_damage_at_range(b, u, rng);
        max_at.insert(rng, v);
        v
    };
    let point_blank = at(b, 1) + estimated_melee_damage(&b.units[u]);
    let premium = point_blank - at(b, dist);
    if premium <= 0 {
        return 0.0;
    }
    premium as f64 * (CLOSE_RANGE_BAND - dist as f64) / (CLOSE_RANGE_BAND - 1.0) * CLOSE_RANGE_INCENTIVE_WEIGHT
}

fn facing_mod(o: &Opt, face_xy: (i64, i64), bias_in: i64, square_up_in: bool, closest_xy: Option<(i64, i64)>) -> f64 {
    let (face, bias, square_up, tolerance) = if square_up_in && closest_xy.is_some() { (closest_xy.unwrap(), 0, true, 0) } else { (face_xy, bias_in, false, princess::ALLOW_FACING_TOLERANCE) };
    let mut want = princess::direction(o.hex_xy(), face);
    if !square_up {
        want = (want + bias).rem_euclid(6);
    }
    let diff = (o.facing - want).rem_euclid(6).min((want - o.facing).rem_euclid(6));
    princess::FACING_MOD_MULTIPLIER * (0.max(diff - tolerance)) as f64
}

/// DamageProfile.sustainedDamage: at `distance`, the expected damage of the weapons the heat sinks keep firing every turn.
fn sustained_damage(b: &mut Battle, u: UnitId, distance: i64, capacity: i64) -> f64 {
    let mut firing: Vec<(f64, i64)> = Vec::new();
    for w in crate::damage_resolution::get_weapons(&b.units[u]) {
        if crate::weapon_rules::is_ams(b, u, w) || b.units[u].items[w].damage_per_shot.is_none() {
            continue;
        }
        let Some(m) = crate::weapon_selection::weapon_range_mod(b, u, w, distance) else { continue };
        let ed = crate::expected_damage::expected_damage_per_hit(b, u, w, 0).unwrap().f();
        let dmg = hit_probability(b.units[u].gunnery + m) * ed;
        firing.push((dmg, b.units[u].items[w].heat.unwrap_or(0)));
    }
    let key = |f: &(f64, i64)| if f.1 > 0 { -(f.0 / f.1 as f64) } else { f64::NEG_INFINITY };
    firing.sort_by(|a, c| key(a).partial_cmp(&key(c)).unwrap());
    let (mut total, mut budget) = (0.0, capacity);
    for (dmg, heat) in firing {
        if heat <= 0 {
            total += dmg;
        } else if heat <= budget {
            total += dmg;
            budget -= heat;
        }
    }
    total
}

fn heat_sink_boost(b: &mut Battle, u: UnitId, o: &Opt, dist: i64) -> f64 {
    if !hex_properties(b, &o.label).3 {
        return 1.0;
    }
    let rng = dist.max(1);
    let dry_capacity = compute_heat_dissipation(&b.units[u]);
    let state = crate::water::state_at(&b.board, Some(&o.label), b.units[u].prone, is_superheavy(&b.units[u]));
    let wet_capacity = dry_capacity + crate::water::dissipation_bonus(b, u, Some(state));
    let dry = sustained_damage(b, u, rng, dry_capacity);
    let wet = sustained_damage(b, u, rng, wet_capacity);
    if dry > 0.0 && wet > dry { wet / dry } else { 1.0 }
}

/// waterHazard (modern) for one hex.
fn water_hazard(b: &Battle, mover: UnitId, depth: i64, prone: bool, fall_odds: f64, moving: bool) -> f64 {
    let m = &b.units[mover];
    let submerged = |down: bool| -> Vec<&String> {
        m.locations
            .iter()
            .filter(|(loc, e)| {
                if e.destroyed {
                    return false;
                }
                let legs = m.leg_locations.contains(loc) || *loc == "Front Left Leg" || *loc == "Front Right Leg";
                depth >= 2 || down || legs
            })
            .map(|(l, _)| l)
            .collect()
    };
    let weight = |loc: &str| if loc == "Head" || loc == "Center Torso" { UNIT_DESTRUCTION_FACTOR } else { 50.0 };
    let now = submerged(prone);
    let if_down = submerged(true);
    let mut total = 0.0;
    for loc in &now {
        if m.locations[*loc].armor.f() <= 0.0 {
            if weight(loc) == UNIT_DESTRUCTION_FACTOR {
                return UNIT_DESTRUCTION_FACTOR;
            }
            total += weight(loc);
        }
    }
    if moving {
        for loc in if_down.iter().filter(|l| !now.contains(l)) {
            if m.locations[*loc].armor.f() <= 0.0 {
                total += fall_odds * weight(loc);
            }
        }
    }
    total
}

// =============================================================================================================
// physical estimates
// =============================================================================================================
const PUNCH_FRONT: [f64; 8] = [1.0 / 6.0, 1.0 / 6.0, 1.0 / 6.0, 1.0 / 6.0, 1.0 / 6.0, 1.0 / 6.0, 0.0, 0.0];
const PUNCH_RIGHT: [f64; 8] = [1.0 / 6.0, 1.0 / 6.0, 2.0 / 6.0, 0.0, 2.0 / 6.0, 0.0, 0.0, 0.0];
const PUNCH_LEFT: [f64; 8] = [1.0 / 6.0, 1.0 / 6.0, 0.0, 2.0 / 6.0, 0.0, 2.0 / 6.0, 0.0, 0.0];
const KICK_FRONT: [f64; 8] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.5];
const KICK_RIGHT: [f64; 8] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0];
const KICK_LEFT: [f64; 8] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0];

fn std_odds(side: &str) -> [f64; 8] {
    let t: [f64; 8] = match side {
        "right" => [1.0, 5.0, 7.0, 4.0, 7.0, 3.0, 7.0, 3.0],
        "left" => [1.0, 5.0, 4.0, 7.0, 3.0, 7.0, 3.0, 7.0],
        _ => [1.0, 7.0, 5.0, 5.0, 5.0, 5.0, 4.0, 4.0],
    };
    let mut o = [0.0; 8];
    for i in 0..8 {
        o[i] = t[i] / 36.0;
    }
    o
}

type Opts = crate::fasthash::IndexMap<&'static str, Vec<PhysOption>>;

#[allow(clippy::too_many_arguments)]
fn physical_options(b: &mut Battle, attacker: UnitId, a_xy: (i64, i64), a_label: &str, a_facing: i64, a_amm: i64, target: UnitId, t_xy: (i64, i64), t_label: &str, t_facing: i64, target_tmm: i64, target_prone: bool) -> Option<(i64, Opts, &'static str)> {
    let (a_level, t_level) = (b.board.hexes[a_label].level, b.board.hexes[t_label].level);
    let action = crate::arcs::current_action(&b.units[attacker]);
    let sup = is_superheavy(&b.units[target]);
    let opts = physical::options_at(b, attacker, a_xy, a_facing, a_level, t_xy, t_level, target_prone, &crate::fasthash::HashSet::default(), &action, sup);
    if opts.is_empty() {
        return None;
    }
    let los_mod = crate::los::has_los(a_xy, t_xy, &b.board, crate::los::mech_height(false, false), crate::los::mech_height(target_prone, false)).unwrap().modifier;
    let base = physical::base_tn(&b.units[attacker], a_amm, target_tmm, los_mod, if target_prone { ar::prone_target_modifier(&b.units[target], 1) } else { 0 });
    let h = ar::standing();
    let side = ar::attack_side(b, a_xy, t_xy, t_facing, h, h);
    Some((base, opts, side))
}

fn one<'a>(opts: &'a Opts, kind: &str, limb: Option<&str>) -> Option<&'a PhysOption> {
    opts.get(kind)?.iter().find(|o| limb.map_or(true, |l| o.limb.len() == 1 && o.limb[0] == l))
}

fn physical_info(o: &PhysOption, base: i64, target: &Mech, side: &str) -> (f64, f64, f64, f64) {
    let p = hit_probability(base + o.mod_);
    let damage = o.damage.f();
    let odds = match o.table.as_str() {
        "punch" => match side {
            "right" => PUNCH_RIGHT,
            "left" => PUNCH_LEFT,
            _ => PUNCH_FRONT,
        },
        "kick" => match side {
            "right" => KICK_RIGHT,
            "left" => KICK_LEFT,
            _ => KICK_FRONT,
        },
        _ => std_odds(side),
    };
    let (crits, kill) = princess_fire::weapon_crits_and_kill(target, side, p, p * damage, Some(damage), Some(odds));
    (p * damage, crits, odds[0] * p, kill)
}

#[allow(clippy::too_many_arguments)]
fn physical_value(b: &mut Battle, attacker: UnitId, a_xy: (i64, i64), a_label: &str, a_facing: i64, a_amm: i64, target: UnitId, t_xy: (i64, i64), t_label: &str, t_facing: i64, target_tmm: i64, target_prone: bool, threat: bool) -> f64 {
    let Some((base, opts, side)) = physical_options(b, attacker, a_xy, a_label, a_facing, a_amm, target, t_xy, t_label, t_facing, target_tmm, target_prone) else { return 0.0 };
    let t = &b.units[target];
    let value = |o: Option<&PhysOption>| -> f64 {
        let Some(o) = o else { return 0.0 };
        if threat {
            let (ed, crits, pilot, kill) = physical_info(o, base, t, side);
            ed + crits * PHYSICAL_CRIT_WEIGHT + pilot * PHYSICAL_PILOT_HIT_WEIGHT + kill * UNIT_DESTRUCTION_FACTOR
        } else {
            hit_probability(base + o.mod_) * o.damage.f()
        }
    };
    let kick = value(one(&opts, "kick", Some("Right Leg")).or_else(|| one(&opts, "kick", None)));
    let punches = value(one(&opts, "punch", Some("Left Arm"))) + value(one(&opts, "punch", Some("Right Arm")));
    let mut weapon = 0.0f64;
    let mut first = true;
    for kind in ["weapon", "club"] {
        if let Some(os) = opts.get(kind) {
            for o in os {
                let v = value(Some(o));
                if first || v > weapon {
                    weapon = v;
                    first = false;
                }
            }
        }
    }
    weapon.max(kick).max(punches)
}

// =============================================================================================================
// the choice
// =============================================================================================================
type Key5 = (String, i64, &'static str, i64, i64);
type Est = (f64, f64, f64);

fn key_of(o: &Opt) -> Key5 {
    (o.label.clone(), o.facing, o.mode, o.fc, o.mp_spent)
}

fn moved_estimates(b: &mut Battle, mover: UnitId, other: UnitId, prepared: &[Opt], ev: &mut MoveEvaluator) -> HashMap<Key5, Est> {
    let (olabel, ofacing, ofc, omode, omp) = (b.units[other].hex.clone().unwrap(), b.units[other].facing.clone(), b.units[other].move_fc, b.units[other].move_mode.clone(), b.units[other].mp_spent);
    let cands: HashMap<(String, &'static str, &'static str, i64), crate::move_eval::Candidate> = ev.evaluate(b, &olabel, &ofacing, ofc, &omode, omp, prepared, true).into_iter().map(|c| (c.key4(), c)).collect();
    let enemy_xy = hex_geometry::parse_hex_label(&olabel).unwrap();
    let other_facing = hex_geometry::compass_to_facing(&ofacing).unwrap();
    let other_tmm = ar::target_tmm(&b.units[other]);
    let other_amm = crate::combat::mode_to_amm(&omode);
    let attacks_back = !(b.units[other].shutdown || b.units[other].prone || is_immobile(&b.units[other]));
    let can_attack = !(b.units[mover].shutdown || is_immobile(&b.units[mover]));
    let other_prone = b.units[other].prone;
    let mut out = HashMap::default();
    for o in prepared {
        let c = cands.get(&(o.label.clone(), o.facing_compass, o.mode, o.fc));
        let (mine, mut theirs) = c.map_or((0.0, 0.0), |c| (c.dealt, c.received));
        let mut physical_mine = 0.0;
        if hex_distance(o.hex_xy(), enemy_xy) <= 1 {
            if attacks_back {
                theirs += physical_value(b, other, enemy_xy, &olabel, other_facing, other_amm, mover, o.hex_xy(), &o.label, o.facing, o.tmm, false, true);
            }
            if can_attack {
                physical_mine = physical_value(b, mover, o.hex_xy(), &o.label, o.facing, o.amm, other, enemy_xy, &olabel, other_facing, other_tmm, other_prone, false);
            }
        }
        out.insert(key_of(o), (mine, physical_mine, theirs));
    }
    out
}

fn unmoved_estimates(b: &mut Battle, mover: UnitId, other: UnitId, prepared: &[Opt]) -> HashMap<Key5, Est> {
    let parts = princess::unmoved_parts(b, mover, other, prepared);
    let by_key: HashMap<Key5, &Opt> = prepared.iter().map(|o| (key_of(o), o)).collect();
    let mut out = HashMap::default();
    for (k, (mine, theirs, flank)) in parts {
        let o = by_key[&k];
        out.insert(k, (mine * odds_ratio(o.amm), 0.0, theirs * terrain_discount(b, &o.label) + flank));
    }
    out
}

fn combine_estimates(a: &HashMap<Key5, Est>, c: &HashMap<Key5, Est>) -> HashMap<Key5, Est> {
    a.iter().map(|(k, x)| (k.clone(), (x.0.max(c[k].0), x.1.max(c[k].1), x.2 + c[k].2))).collect()
}

fn foes_note(group: &Group, moved: bool) -> String {
    let state = if moved { "moved" } else { "still to move" };
    if group.foes.len() == 1 { format!("enemy {}", state) } else { format!("{} enemies, nearest {}", group.foes.len(), state) }
}

/// Modern Princess's end-of-movement pick: (pick, note).
pub fn choose(b: &mut Battle, mover: UnitId, other: UnitId, moves_first: bool, standup_mp: Option<i64>, entry_edge: Option<&[String]>, ties: &mut crate::move_select::Ties) -> (Option<Pick>, String) {
    if b.units[other].hex.is_none() {
        return crate::move_select::choose(b, mover, other, moves_first, standup_mp, entry_edge, ties);
    }
    let group = Group::new(b, mover, Some(other), moves_first);
    let stance = force_posture(b, mover, &group);
    let exclude = move_options::occupied_hexes(b, mover, other);
    let (options, notes) = move_options::reduced_options(b, mover, &exclude, standup_mp, entry_edge);
    let moved = group.has_moved(b, other);
    let mut prepared: Option<Vec<Opt>> = None;
    let mut estimate: Option<HashMap<Key5, Est>> = None;
    b.fire_ctl = Some(FireControl::new(true, Some(mover)));
    for &foe in &group.foes {
        if !crate::legate::can_matter(b, mover, foe) {
            continue;
        }
        let mut ev = MoveEvaluator::new(b, mover, foe);
        ev.mover_physical = false;
        ev.defender_physical = false;
        if prepared.is_none() {
            let p = ev.prepare(b, &options);
            if p.is_empty() {
                b.fire_ctl = None;
                return (None, "no reachable spot".into());
            }
            prepared = Some(p);
        }
        let prep = prepared.clone().unwrap();
        let got = if group.has_moved(b, foe) { moved_estimates(b, mover, foe, &prep, &mut ev) } else { unmoved_estimates(b, mover, foe, &prep) };
        estimate = Some(match estimate {
            None => got,
            Some(e) => combine_estimates(&e, &got),
        });
    }
    if prepared.is_none() {
        let p = move_options::prepare_options(b, mover, &options);
        if p.is_empty() {
            b.fire_ctl = None;
            return (None, "no reachable spot".into());
        }
        estimate = Some(p.iter().map(|o| (key_of(o), (0.0, 0.0, 0.0))).collect());
        prepared = Some(p);
    }
    b.fire_ctl = None;
    rank(b, mover, &group, &prepared.unwrap(), &estimate.unwrap(), standup_mp, entry_edge, &notes, moved, &stance)
}

#[allow(clippy::too_many_arguments)]
fn rank(b: &mut Battle, mover: UnitId, group: &Group, prepared: &[Opt], estimate: &HashMap<Key5, Est>, standup_mp: Option<i64>, entry_edge: Option<&[String]>, notes: &move_options::PathNotes, moved: bool, stance: &str) -> (Option<Pick>, String) {
    let psr_applies = standup_mp.is_none();
    let fall_shame = princess_fire::setting(b, "fall_shame");
    let bravery = princess_fire::setting(b, "bravery");
    let aggression = princess_fire::setting(b, "hyper_aggression");
    let bias = princess::armor_bias(&b.units[mover]);
    let melee = estimated_melee_damage(&b.units[mover]) > 0;
    let tolerance = b.cfg.get("PRINCESS_BEHAVIOR")["fall_shame"].as_f64().unwrap_or(5.0) / 20.0 + 0.50;
    let max_range = crate::move_select::max_range(b, mover);
    let start = b.units[mover].hex.as_deref().and_then(|h| group.distance_to_enemy(b, hex_geometry::parse_hex_label(h).unwrap()));
    let in_range = start.map_or(false, |s| max_range >= s);
    let no_pull = stance == DEFEND && start.map_or(false, |s| s <= THREAT_CONTACT_RANGE);
    let fall_odds = if psr_applies { crate::move_select::terrain_psr_odds(b, mover).map_or(0.0, |t| t.0) } else { 0.0 };
    let success: HashMap<Key5, f64> = prepared.iter().map(|o| (key_of(o), princess::success_probability(b, mover, o, psr_applies, notes))).collect();
    let mut valid: Vec<&Opt> = Vec::new();
    for o in prepared {
        if let Some(s) = start {
            let d = group.distance_to_enemy(b, o.hex_xy()).unwrap();
            if (in_range && d > max_range) || (!in_range && d > s) {
                continue;
            }
        }
        if success[&key_of(o)] < tolerance {
            continue;
        }
        valid.push(o);
    }
    let pool: Vec<&Opt> = if valid.is_empty() { prepared.iter().collect() } else { valid };
    let turn_of_advance = TEMPO_REFERENCE_MP * aggression;
    let cap = if stance == DEFEND { HOLD_CREDIT_DEFEND_CAP_FACTOR } else { HOLD_CREDIT_ATTACK_CAP_FACTOR };
    let hazard_board = princess::hazard_board(b);
    let mover_hex = b.units[mover].hex.clone();
    let mut max_at: HashMap<i64, i64> = HashMap::default();
    let mut tables = crate::ranged_combat::TableCache::default();
    #[allow(clippy::type_complexity)]
    let mut best: Option<(f64, &Opt, f64, f64, f64, f64, f64, f64, f64, f64, f64, f64, f64)> = None;
    for o in &pool {
        let k = key_of(o);
        let p = success[&k];
        let (mine, physical_mine, theirs) = estimate[&k];
        let done = mine + physical_mine;
        let hazard = if hazard_board { path_hazard(b, mover, o, fall_odds, standup_mp, entry_edge, mover_hex.as_deref(), &mut tables) } else { 0.0 };
        let taken = theirs + hazard;
        let fail = 1.0 - p;
        let fall_mod = fail * if fail == 1.0 { UNIT_DESTRUCTION_FACTOR } else { fall_shame };
        let bravery_mod = p * done * bravery - taken;
        let dist = group.distance_to_enemy(b, o.hex_xy()).unwrap();
        let aggression_mod = if no_pull { 0.0 } else { (if dist != 0 { dist } else { 2 }) as f64 * aggression };
        let close = close_range_incentive(b, mover, dist, &mut max_at);
        let face_xy = group.face_target(b, o.hex_xy()).unwrap();
        let near = group.nearest(b, o.hex_xy(), 1);
        let closest = near.map(|(f, _)| hex_geometry::parse_hex_label(b.units[f].hex.as_deref().unwrap()).unwrap());
        let face = facing_mod(o, face_xy, bias, close > 0.0 && melee && dist >= 1, closest);
        let support = group.support_mod(o.hex_xy());
        let crowd = group.crowding_mod(b, o.hex_xy(), max_range);
        let mut hold = 0.0;
        if o.fc == 0 && dist <= THREAT_CONTACT_RANGE {
            let quality = p * done * heat_sink_boost(b, mover, o, dist) - taken;
            if quality > 0.0 {
                hold = (cap * quality.min(turn_of_advance) + ESTIMATE_NOISE_MARGIN).min(turn_of_advance);
            }
        }
        let utility = -fall_mod + bravery_mod - aggression_mod + close - support - crowd - face + hold;
        if best.map_or(true, |x| utility > x.0) {
            best = Some((utility, *o, fall_mod, bravery_mod, p, done, taken, aggression_mod, close, face, hold, support, crowd));
        }
    }
    let (utility, o, fall_mod, bravery_mod, p, done, taken, aggression_mod, close, face, hold, support, crowd) = best.unwrap();
    let group_note = format!("{}{}", if support != 0.0 { format!(" - mutual support {}", Fx(support, 2)) } else { String::new() }, if crowd != 0.0 { format!(" - crowding {}", Fx(crowd, 2)) } else { String::new() });
    let note = format!(
        "Princess (modern, {}): utility {} = -fall {} + bravery {} [{} x {} x {} - taken {}] - aggression {} + close range {}{} - facing {} + hold {} [{} of {} spots; {}]",
        stance.to_lowercase(),
        Fx(utility, 2),
        Fx(fall_mod, 2),
        Fx(bravery_mod, 2),
        Fx(p, 2),
        Fx(done, 2),
        py_float_str(bravery),
        Fx(taken, 2),
        Fx(aggression_mod, 2),
        Fx(close, 2),
        group_note,
        Fx(face, 0),
        Fx(hold, 2),
        pool.len(),
        prepared.len(),
        foes_note(group, moved)
    );
    (Some(o.pick()), note)
}

/// hazards (modern): classic.path_hazards with waterHazard; a move with no steps prices the water it stays in.
fn path_hazard(b: &mut Battle, mover: UnitId, o: &Opt, fall_odds: f64, standup_mp: Option<i64>, entry_edge: Option<&[String]>, mover_hex: Option<&str>, cache: &mut crate::ranged_combat::TableCache) -> f64 {
    let p_fall = if o.mode == "Run" { fall_odds } else { 0.0 };
    let moves = o.fc != 0 || o.mp_spent != 0;
    let steps: Option<Vec<(i64, i64)>> = if moves && o.mode != "Jump" {
        crate::ranged_combat::path_to_cached(b, mover, &o.pick(), standup_mp, entry_edge, cache).map(|s| s.into_iter().map(|(_, st, _)| (st.0, st.1)).collect())
    } else {
        None
    };
    let standup_hex = if standup_mp.is_some() { mover_hex.map(|h| {
        let (sx, sy, _) = hex_geometry::state_from_label(h, &b.units[mover].facing).unwrap();
        (sx, sy)
    }) } else { None };
    let water_fn = move |bb: &Battle, _label: &str, depth: i64, _end: bool, prone: bool| -> f64 { water_hazard(bb, mover, depth, prone, p_fall, true) };
    let stay = move |bb: &Battle| -> f64 {
        let depth = bb.units[mover].hex.as_deref().map_or(0, |h| crate::water::depth_at(&bb.board, Some(h)));
        if depth >= 1 { water_hazard(bb, mover, depth, bb.units[mover].prone, 0.0, false) } else { 0.0 }
    };
    princess::path_hazards(b, mover, o, steps, standup_hex, Some(&water_fn), Some(&stay))
}
