// Translated from INTEGRATION__movement_selection.py and INTEGRATION__future_damage.py: where Gladiator ends its
// Movement Phase. Objective, exposure, PSR costs, the two-ply look-ahead with its short-list / grid reply model, the
// closing fallback. Legate's view of the other enemies (INTEGRATION__legate) is not here (several-enemy battles).
use std::collections::{HashMap, HashSet};

use indexmap::IndexMap;

use crate::arcs;
use crate::battle::{Battle, UnitId};
use crate::damage_resolution::get_weapons;
use crate::hex_geometry;
use crate::los::hex_distance;
use crate::mech_state::*;
use crate::move_attacks::{self, Pose};
use crate::move_eval::{Candidate, MoveEvaluator};
use crate::move_options::{self, Opt, PathNotes, StateKey};
use crate::physical::{PhysPlanner, Worth};
use crate::ranged_combat::Pick;
use crate::structure_weight as sw;

pub const SIDES: [&str; 4] = ["front", "left", "right", "rear"];

fn side_ix(s: &str) -> usize {
    match s {
        "front" => 0,
        "left" => 1,
        "right" => 2,
        _ => 3,
    }
}

fn round_n(x: f64, n: usize) -> f64 {
    format!("{:.*}", n, x).parse().unwrap()
}

fn round9(x: f64) -> f64 {
    round_n(x, 9)
}

// =============================================================================================================
// future damage
// =============================================================================================================
/// The highest TMM the mech can earn (p.57): from its Running MP with any working MASC / supercharger, or its Jumping MP + 1.
pub fn best_tmm(b: &mut Battle, u: UnitId) -> i64 {
    let mult = crate::equipment_systems::boost_multiplier(b, u, false);
    let saved = b.units[u].run_mp_multiplier;
    b.units[u].run_mp_multiplier = mult;
    let run = compute_running_mp(&b.units[u]);
    b.units[u].run_mp_multiplier = saved;
    let mut tmm = crate::damage_resolution::tmm_from_mp(run);
    let jump = compute_jump_mp(&b.units[u]);
    if jump > 0 {
        tmm = tmm.max(crate::damage_resolution::tmm_from_mp(jump) + 1);
    }
    tmm
}

fn max_distance(b: &Battle, u: UnitId, weapons: &[usize]) -> i64 {
    let mut longest = 1;
    for &w in weapons {
        if let Some(r) = &b.units[u].items[w].weapon_range {
            longest = longest.max(r.long);
        }
    }
    longest.min(30)
}

/// _ranged_for: ranged(distance, held) = the best heat-limited expected damage at that distance with the target dead
/// ahead, in movement-score units.
struct RangedFor {
    attacker: UnitId,
    target: UnitId,
    cond: Option<(i64, HashSet<usize>, String)>,
    fixed: Option<(HashSet<usize>, i64)>,
    adjust: std::rc::Rc<crate::attack_resolution::Adjuster>,
    planner: crate::fire_modes::Planner<'static>,
    scale_on: bool,
    scales: Option<HashMap<usize, f64>>,
    memo: HashMap<(Vec<usize>, i64), f64>,
    move_heat: i64,
    pub amm: i64,
    pub tmm: i64,
    legs: Vec<(String, i64)>,
    extra_tn: i64,
    dissipation: i64,
    other: i64,
}

impl RangedFor {
    fn new(b: &mut Battle, attacker: UnitId, target: UnitId, extra_tn: i64) -> RangedFor {
        let mode = b.cfg.s("MOVEMENT_LIFETIME_ATTACKER_MODE").to_string();
        let amm = crate::combat::mode_to_amm(&mode);
        let move_heat = crate::heat::movement_heat(&b.units[attacker], &mode, 1);
        let tmm = best_tmm(b, target);
        let legs = arcs::leg_offsets(&b.units[attacker]);
        let cond = crate::attack_resolution::firing_conditions(b, attacker);
        let adjust = std::rc::Rc::new(crate::attack_resolution::tn_adjuster(b, attacker, target, None, 0));
        let planner = crate::fire_modes::Planner::new_shared(attacker, target, adjust.clone(), 0.0);
        let scale_on = b.cfg.f("MOVEMENT_STRUCTURE_WEIGHT") != 1.0;
        let dissipation = compute_heat_dissipation(&b.units[attacker]);
        let other = crate::heat::other_heat(b, attacker);
        RangedFor { attacker, target, cond, fixed: None, adjust, planner, scale_on, scales: None, memo: HashMap::new(), move_heat, amm, tmm, legs, extra_tn, dissipation, other }
    }

    fn ranged(&mut self, b: &mut Battle, distance: i64, held: &HashSet<usize>) -> f64 {
        let Some(cond) = self.cond.clone() else { return 0.0 };
        if self.fixed.is_none() {
            let target_xy = (0, 2 * distance);
            let key = arcs::key_for(&arcs::arcs_between((0, 0), target_xy), 0, &arcs::no_action(), &self.legs);
            let mut blocked: HashSet<usize> = cond.1.clone();
            blocked.extend(crate::ammo::unavailable_weapons(&b.units[self.attacker]));
            blocked.extend(crate::fire_modes::jammed_ids(&b.units[self.attacker]));
            blocked.extend(crate::weapon_profiles::array_gun_ids(b, self.attacker));
            blocked.extend(crate::attack_resolution::arc_unavailable(&b.units[self.attacker], &key));
            let a = &b.units[self.attacker];
            let pre = a.gunnery + self.amm + self.tmm + a.heat_fire_modifier + cond.0 + crate::advanced_weapons::own_attack_modifier(a, false);
            let pre_tn = crate::weapon_selection::PRE_TN_MIN.max(crate::weapon_selection::PRE_TN_MAX.min(pre + self.extra_tn));
            self.fixed = Some((blocked, pre_tn));
        }
        let (blocked, pre_tn) = self.fixed.clone().unwrap();
        let mut unavailable: Vec<usize> = blocked.union(held).copied().collect();
        unavailable.sort();
        let mk = (unavailable.clone(), distance);
        if let Some(v) = self.memo.get(&mk) {
            return *v;
        }
        if self.scale_on && self.scales.is_none() {
            let weapons = get_weapons(&b.units[self.attacker]);
            self.scales = Some(sw::multipliers(b, self.attacker, &weapons, self.target, "front").into_iter().collect());
        }
        let unavail: HashSet<usize> = unavailable.iter().copied().collect();
        let (min_heat, max_heat) = (b.units[self.attacker].min_heat, b.units[self.attacker].max_heat);
        let scale = if self.scale_on { self.scales.as_ref() } else { None };
        let adj = self.adjust.clone();
        let got = crate::weapon_selection::select_weapons_scaled(b, self.attacker, distance, pre_tn, min_heat, max_heat, self.dissipation, self.move_heat, self.other, Some(&*adj), &unavail, scale, Some(&mut self.planner)).1;
        self.memo.insert(mk, got);
        got
    }
}

/// attacker's future damage per turn against target, in movement-score units.
pub fn future_damage(b: &mut Battle, attacker: UnitId, target: UnitId) -> f64 {
    if b.units[attacker].shutdown || is_immobile(&b.units[attacker]) {
        return 0.0;
    }
    let mut rf = RangedFor::new(b, attacker, target, 0);
    let weapons = get_weapons(&b.units[attacker]);
    let none = HashSet::new();
    let mut best = f64::NEG_INFINITY;
    for d in 1..=max_distance(b, attacker, &weapons) {
        let v = rf.ranged(b, d, &none);
        if v > best {
            best = v;
        }
    }
    if !b.units[attacker].prone {
        let pair = arcs::arcs_between((0, 0), (0, 2));
        let w = Worth::new(b, target, true);
        let mut planner = PhysPlanner::new(b, attacker, Some(w));
        let base = crate::physical::base_tn(&b.units[attacker], rf.amm, rf.tmm, 0, 0);
        let ranged_best = { let r1 = rf.ranged(b, 1, &none); if r1 > best { r1 } else { best } };
        let legs = rf.legs.clone();
        let mut f = |b: &mut Battle, _key: &arcs::ArcKey, held: &HashSet<usize>| rf.ranged(b, 1, held);
        best = crate::move_eval::with_physical(b, &mut planner, ranged_best, &[arcs::no_action()], &legs, &pair, 0, 0, false, base, "front", Some(&mut f), None, None, None);
    }
    b.cfg.f("MOVEMENT_LIFETIME_INITIATIVE") * best
}

// =============================================================================================================
// exposure, PSR costs, the objective
// =============================================================================================================
fn exposure_factors(b: &Battle, u: UnitId) -> [f64; 4] {
    if !b.cfg.b("MOVEMENT_EXPOSURE_WEIGHTING") {
        return [1.0; 4];
    }
    let m = &b.units[u];
    let vuln: Vec<f64> = SIDES.iter().map(|s| sw::vulnerability(m, &sw::hit_spread(m, s, None))).collect();
    let reference = vuln[0];
    if reference <= 0.0 {
        return [1.0; 4];
    }
    let (lo, hi) = (b.cfg.f("MOVEMENT_EXPOSURE_MIN"), b.cfg.f("MOVEMENT_EXPOSURE_MAX"));
    let mut f = [0.0; 4];
    for i in 0..4 {
        f[i] = lo.max(hi.min(vuln[i] / reference));
    }
    f[0] = 1.0;
    f
}

fn psr_costs(b: &Battle, u: UnitId) -> (f64, f64) {
    if !b.cfg.b("MOVEMENT_PSR_COST") {
        return (0.0, 0.0);
    }
    let m = &b.units[u];
    let mut out = [0.0, 0.0];
    for (i, (_, psr_mode)) in [("Run", "running"), ("Jump", "jump")].iter().enumerate() {
        let Some(target) = crate::piloting_rolls::movement_psr_target_number(m, psr_mode) else { continue };
        let p_stand = crate::combat::hit_probability(target).powf(crate::piloting_rolls::movement_psr_count(m, psr_mode) as f64);
        out[i] = (1.0 - p_stand) * crate::piloting_rolls::fall_damage(m) as f64;
    }
    (out[0], out[1])
}

fn terrain_psr_odds(b: &Battle, u: UnitId) -> Option<(f64, f64)> {
    if !b.cfg.b("MOVEMENT_PSR_COST") {
        return None;
    }
    let m = &b.units[u];
    let target = m.piloting + crate::piloting_rolls::preexisting_modifier(m) + crate::piloting_rolls::special_case_modifier(m);
    Some((1.0 - crate::combat::hit_probability(target), crate::piloting_rolls::fall_damage(m) as f64))
}

/// How a side scores its own spots (config.MOVEMENT_OBJECTIVE).
#[derive(Clone, Debug)]
pub enum Objective {
    Ratio,
    Lifetime { hp: f64, mine: f64, theirs: f64 },
}

pub struct Side {
    pub unit: UnitId,
    pub exposure: [f64; 4],
    psr_run: f64,
    psr_jump: f64,
    terrain: Option<(f64, f64)>,
    pub notes: PathNotes,
    pub objective: Objective,
    psr_terrain: bool,
    hazard_terrain: bool,
    eps: f64,
}

impl Side {
    pub fn new(b: &Battle, u: UnitId, psr_applies: bool) -> Side {
        let (psr_run, psr_jump) = if psr_applies { psr_costs(b, u) } else { (0.0, 0.0) };
        let terrain = if psr_applies { terrain_psr_odds(b, u) } else { None };
        let psr_terrain = crate::terrain_rules::has_psr_terrain(&b.board);
        let hazard_terrain = psr_terrain && crate::terrain_rules::has_hazard_terrain(&b.board);
        Side { unit: u, exposure: exposure_factors(b, u), psr_run, psr_jump, terrain, notes: PathNotes::default(), objective: Objective::Ratio, psr_terrain, hazard_terrain, eps: b.cfg.f("MOVEMENT_RATIO_EPSILON") }
    }

    pub fn exp(&self, side: &str) -> f64 {
        self.exposure[side_ix(side)]
    }

    /// spot_hazard: expected damage from hazardous terrain.
    pub fn spot_hazard(&self, b: &Battle, mode: &str, fc: i64, label: &str, facing: Option<&str>, mp: Option<i64>) -> f64 {
        if !self.hazard_terrain {
            return 0.0;
        }
        let Some(info) = b.board.hexes.get(label) else { return 0.0 };
        let legs = b.units[self.unit].leg_locations.len() as i64;
        let mut out = crate::terrain_rules::step_hazard(info, legs);
        if mode == "Jump" {
            out += crate::terrain_rules::step_hazard(info, legs);
        } else if (mode == "Walk" || mode == "Run") && facing.is_some() && mp.is_some() {
            let (x, y) = hex_geometry::parse_hex_label(label).unwrap();
            let f = hex_geometry::compass_to_facing(facing.unwrap()).unwrap();
            out += self.notes.hazard.get(&(x, y, f, fc, move_options::mode_str(mode), mp.unwrap())).copied().unwrap_or(0.0);
        }
        out
    }

    /// Expected fall damage from this move's PSRs.
    pub fn psr_cost(&self, b: &Battle, mode: &str, fc: i64, label: &str, facing: &str, mp: i64) -> f64 {
        let mut cost = 0.0;
        if mode == "Run" && fc >= 1 {
            cost = self.psr_run;
        } else if mode == "Jump" {
            cost = self.psr_jump;
        }
        cost += self.spot_hazard(b, mode, fc, label, Some(facing), Some(mp));
        let Some((fail, fall)) = self.terrain else { return cost };
        if mode == "Jump" {
            let depth = crate::water::depth_at(&b.board, Some(label));
            if depth >= 1 {
                cost += fail * fall * (depth + 1) as f64 / 2.0;
            }
            if b.board.hexes[label].features.has("rubble") {
                cost += fail * fall;
            }
        } else if mode == "Walk" || mode == "Run" {
            let (x, y) = hex_geometry::parse_hex_label(label).unwrap();
            let f = hex_geometry::compass_to_facing(facing).unwrap();
            let n = self.notes.psrs.get(&(x, y, f, fc, move_options::mode_str(mode), mp)).copied().unwrap_or(0);
            if n != 0 {
                cost += (1.0 - (1.0 - fail).powf(n as f64)) * fall;
            }
        }
        cost
    }

    pub fn psr_for_opt(&self, b: &Battle, o: &Opt) -> f64 {
        self.psr_cost(b, o.mode, o.fc, &o.label, o.facing_compass, o.mp_spent)
    }

    pub fn psr_for_cand(&self, b: &Battle, c: &Candidate) -> f64 {
        self.psr_cost(b, c.mode, c.fc, &c.hex, c.facing, c.mp_spent)
    }

    pub fn psr_for_pick(&self, b: &Battle, p: &Pick) -> f64 {
        self.psr_cost(b, &p.mode, p.fc, &p.hex, &p.facing, p.mp_spent)
    }

    /// The objective: score of (dealt, received) with their exposure multipliers and the PSR / extras term.
    pub fn obj(&self, dealt: f64, received: f64, dealt_mult: f64, received_mult: f64, extras: f64) -> f64 {
        match &self.objective {
            Objective::Ratio => (dealt * dealt_mult) / (received * received_mult + extras + self.eps),
            Objective::Lifetime { hp, mine, theirs } => {
                let left = hp - (received * received_mult + extras);
                dealt * dealt_mult + if left > 0.0 { left / theirs * mine } else { 0.0 }
            }
        }
    }

    pub fn note(&self, dealt: f64, received: f64, dealt_mult: f64, received_mult: f64, extras: f64, how: &str) -> String {
        match &self.objective {
            Objective::Ratio => {
                let score = self.obj(dealt, received, dealt_mult, received_mult, extras);
                format!("score {:.3} = dealt {:.2} x{:.2} / (received {:.2} x{:.2} + PSR {:.2} + {}) [{}]", score, dealt, dealt_mult, received, received_mult, extras, crate::pyfmt::py_float_str(self.eps), how)
            }
            Objective::Lifetime { hp, mine, theirs } => {
                let score = self.obj(dealt, received, dealt_mult, received_mult, extras);
                format!("score {:.3} = dealt {:.2} x{:.2} + (HP {:.1} - received {:.2} x{:.2} - PSR {:.2}) / enemy future {:.2} x my future {:.2} [{}]", score, dealt, dealt_mult, hp, received, received_mult, extras, theirs, mine, how)
            }
        }
    }
}

pub fn effective_hp(b: &Battle, u: UnitId) -> f64 {
    let k = b.cfg.f("MOVEMENT_STRUCTURE_WEIGHT");
    let mut sum = 0.0;
    for v in b.units[u].locations.values() {
        if v.destroyed {
            continue;
        }
        sum += v.armor.f() + v.rear_armor.map_or(0.0, |r| r.f()) + k * v.structure.f();
    }
    sum
}

/// battle_record: (HP the enemy has really lost, HP I have really lost, turns fought) so far.
fn battle_record(b: &Battle, me: UnitId, them: UnitId) -> (f64, f64, i64) {
    let (mine, theirs) = (b.units[me].hp_log.as_ref(), b.units[them].hp_log.as_ref());
    let (Some(mine), Some(theirs)) = (mine, theirs) else { return (0.0, 0.0, 0) };
    if mine.is_empty() || theirs.is_empty() {
        return (0.0, 0.0, 0);
    }
    let turns = mine.len().min(theirs.len()) as i64 - 1;
    let first = (1..=turns).find(|t| mine[*t as usize] < mine[*t as usize - 1] || theirs[*t as usize] < theirs[*t as usize - 1]);
    let fought = match first {
        None => 0,
        Some(f) => turns - f + 1,
    };
    (theirs[0] - theirs[turns as usize], mine[0] - mine[turns as usize], fought)
}

fn lifetime(b: &mut Battle, me: UnitId, them: UnitId) -> Objective {
    let floor = b.cfg.f("MOVEMENT_LIFETIME_FUTURE_FLOOR");
    let hp = effective_hp(b, me);
    let mut mine = future_damage(b, me, them);
    let mut theirs = future_damage(b, them, me);
    if let Some(k) = b.cfg.get("MOVEMENT_LIFETIME_HISTORY_K").as_f64() {
        let (dealt, taken, fought) = battle_record(b, me, them);
        let f = fought as f64;
        mine = (k * mine + dealt) / (k + f);
        theirs = (k * theirs + taken) / (k + f);
    }
    Objective::Lifetime { hp, mine: mine.max(floor), theirs: theirs.max(floor) }
}

/// _link: give both sides their objective for this pick.
pub fn link(b: &mut Battle, me: &mut Side, them: &mut Side) {
    match b.cfg.s("MOVEMENT_OBJECTIVE") {
        "lifetime" => {
            me.objective = lifetime(b, me.unit, them.unit);
            them.objective = lifetime(b, them.unit, me.unit);
        }
        "ratio" => {}
        o => panic!("Unknown MOVEMENT_OBJECTIVE {:?}", o),
    }
}

// =============================================================================================================
// tie-breaking randomness
// =============================================================================================================
/// The battle's seeded random pick for ties; a replay check passes the recorded pick instead (no dice are drawn).
pub struct Ties<'a> {
    pub recorded: Option<&'a Pick>,
    pub missed: bool,
}

impl Ties<'_> {
    fn pick(&mut self, b: &mut Battle, pool: &[&Opt]) -> usize {
        match self.recorded {
            None => (b.pick_number(pool.len() as i64) - 1) as usize,
            Some(r) => match pool.iter().position(|o| o.label == r.hex && o.facing_compass == r.facing && o.mode == r.mode && o.fc == r.fc && o.mp_spent == r.mp_spent) {
                Some(i) => i,
                None => {
                    // a recorded charge / DFA is not one of the ordinary pick's tied spots: nothing to compare there
                    if !(r.charge || r.dfa) {
                        self.missed = true;
                    }
                    0
                }
            },
        }
    }
}

fn nearest_to<'a>(b: &mut Battle, options: &'a [Opt], target_xy: (i64, i64), rng: Option<&mut Ties>) -> &'a Opt {
    let nearest = options.iter().map(|o| hex_distance(o.hex_xy(), target_xy)).min().unwrap();
    let pool: Vec<&Opt> = options.iter().filter(|o| hex_distance(o.hex_xy(), target_xy) == nearest).collect();
    match rng {
        Some(r) if pool.len() > 1 => pool[r.pick(b, &pool)],
        _ => pool[0],
    }
}

// =============================================================================================================
// closing fallback
// =============================================================================================================
fn weapon_ranges(b: &mut Battle, u: UnitId) -> Vec<(usize, crate::equipment::WeaponRange)> {
    let mut out = Vec::new();
    for w in get_weapons(&b.units[u]) {
        if let Some(r) = b.units[u].items[w].weapon_range.clone() {
            if !crate::weapon_rules::is_ams(b, u, w) {
                out.push((w, r));
            }
        }
    }
    out
}

fn max_range(b: &mut Battle, u: UnitId) -> i64 {
    weapon_ranges(b, u).iter().map(|(_, r)| r.long).max().unwrap_or(0)
}

fn bracket(distance: i64, r: &crate::equipment::WeaponRange) -> i64 {
    if distance <= r.short {
        0
    } else if distance <= r.medium {
        1
    } else if distance <= r.long {
        2
    } else {
        3
    }
}

/// _safest: the prepared states with the least hazard damage.
fn safest(b: &Battle, side: &Side, options: Vec<Opt>) -> Vec<Opt> {
    if options.is_empty() || !side.hazard_terrain {
        return options;
    }
    let priced: Vec<(f64, Opt)> = options.into_iter().map(|o| (round_n(side.spot_hazard(b, o.mode, o.fc, &o.label, Some(o.facing_compass), Some(o.mp_spent)), 6), o)).collect();
    let low = priced.iter().map(|(h, _)| *h).fold(f64::INFINITY, f64::min);
    priced.into_iter().filter(|(h, _)| *h == low).map(|(_, o)| o).collect()
}

/// closing_fallback: the option the mover closes the range with, or None.
pub fn closing_fallback(b: &mut Battle, mover: UnitId, other: UnitId, side: &Side, options: &[Opt], enemy_xy: (i64, i64), dealt_for: &dyn Fn(&Opt) -> f64, exclude_xy: Option<(i64, i64)>) -> Option<Opt> {
    let ranges = weapon_ranges(b, mover);
    let mut longest: Option<&crate::equipment::WeaponRange> = None;
    for (_, r) in &ranges {
        if longest.map_or(true, |l| r.long > l.long) {
            longest = Some(r);
        }
    }
    let weapon = longest?.clone();
    let mover_xy = b.units[mover].hex.as_deref().map(|h| hex_geometry::parse_hex_label(h).unwrap());
    let initial_bracket = match mover_xy {
        Some(m) => bracket(hex_distance(m, enemy_xy), &weapon),
        None => 3,
    };
    let pool = safest(b, side, options.iter().filter(|o| Some(o.hex_xy()) != exclude_xy).cloned().collect());
    if max_range(b, mover) < max_range(b, other) || initial_bracket == 3 {
        let mut best: Option<(Opt, f64, i64)> = None;
        for o in &pool {
            let br = bracket(hex_distance(o.hex_xy(), enemy_xy), &weapon);
            if br >= initial_bracket {
                continue;
            }
            let denom = initial_bracket - br;
            let score = dealt_for(o) / denom as f64;
            let better = match &best {
                None => true,
                Some((_, bs, bd)) => score > *bs || (score == *bs && denom > *bd),
            };
            if better {
                best = Some((o.clone(), score, denom));
            }
        }
        return best.map(|(o, _, _)| o);
    }
    // Case B2: already in range, so LOS is the problem.
    let other_prone = b.units[other].prone;
    let mut seed: Option<((i64, i64), i64)> = None;
    let labels: Vec<String> = b.board.hexes.keys().cloned().collect();
    for label in labels {
        if b.board.hexes[&label].impassable {
            continue;
        }
        let cell = hex_geometry::parse_hex_label(&label).unwrap();
        if Some(cell) == mover_xy {
            continue;
        }
        if bracket(hex_distance(cell, enemy_xy), &weapon) < initial_bracket {
            continue;
        }
        let Ok(l) = crate::los::has_los(cell, enemy_xy, &b.board, crate::los::mech_height(false, false), crate::los::mech_height(other_prone, false)) else { continue };
        if !l.los {
            continue;
        }
        let dist = hex_distance(cell, mover_xy.unwrap());
        if seed.map_or(true, |(_, sd)| dist < sd) {
            seed = Some((cell, dist));
        }
    }
    let (seed_xy, _) = seed?;
    let mut best: Option<(Opt, i64)> = None;
    for o in &pool {
        if bracket(hex_distance(o.hex_xy(), enemy_xy), &weapon) < initial_bracket {
            continue;
        }
        let dist = hex_distance(o.hex_xy(), seed_xy);
        if best.as_ref().map_or(true, |(_, bd)| dist < *bd) {
            best = Some((o.clone(), dist));
        }
    }
    best.map(|(o, _)| o)
}

// =============================================================================================================
// searches
// =============================================================================================================
pub fn own_search(b: &Battle, u: UnitId) -> String {
    b.units[u].move_search.clone().unwrap_or_else(|| b.cfg.s("MOVEMENT_SEARCH").to_string())
}

pub fn assumed_enemy_search(b: &Battle, u: UnitId) -> String {
    b.units[u].assumes_enemy_search.clone().unwrap_or_else(|| b.cfg.s("MOVEMENT_ASSUMED_ENEMY_SEARCH").to_string())
}

/// Daniel's "guess and follow": the rows of a search over the reachable HEXES instead of every state.
#[allow(clippy::too_many_arguments)]
pub fn grid_search<R>(b: &mut Battle, prepared: &[Opt], score_hex: &mut dyn FnMut(&mut Battle, &[Opt]) -> Vec<(f64, R)>, start_xy: (i64, i64), starts: usize, target_xy: Option<(i64, i64)>) -> Vec<(f64, R)> {
    let mut by_hex: IndexMap<(i64, i64), Vec<Opt>> = IndexMap::new();
    for c in prepared {
        by_hex.entry(c.hex_xy()).or_default().push(c.clone());
    }
    let mut hex_best: IndexMap<(i64, i64), f64> = IndexMap::new();
    let mut scored: Vec<(f64, R)> = Vec::new();
    let mut look = |b: &mut Battle, h: (i64, i64), hex_best: &mut IndexMap<(i64, i64), f64>, scored: &mut Vec<(f64, R)>| {
        if hex_best.contains_key(&h) || !by_hex.contains_key(&h) {
            return;
        }
        let rows = score_hex(b, &by_hex[&h]);
        let best = rows.iter().map(|r| round9(r.0)).fold(f64::NEG_INFINITY, f64::max);
        scored.extend(rows);
        hex_best.insert(h, best);
    };
    let k: i64 = if b.cfg.s("MOVEMENT_GRID_SPIN") == "clockwise" { 3 } else { 5 };
    let colour = |h: (i64, i64)| -> i64 {
        let (q, r) = (h.0, (h.1 - h.0).div_euclid(2));
        (q + k * r).rem_euclid(7)
    };
    let net = colour(start_xy);
    let keys: Vec<(i64, i64)> = by_hex.keys().copied().collect();
    for h in &keys {
        if colour(*h) == net {
            look(b, *h, &mut hex_best, &mut scored);
        }
    }
    look(b, start_xy, &mut hex_best, &mut scored);
    if let Some(t) = target_xy {
        for (dx, dy) in hex_geometry::FACING_DELTAS {
            look(b, (t.0 + dx, t.1 + dy), &mut hex_best, &mut scored);
        }
    }
    if hex_best.is_empty() && !by_hex.is_empty() {
        look(b, *by_hex.keys().next().unwrap(), &mut hex_best, &mut scored);
    }
    let mut order: Vec<(i64, i64)> = hex_best.keys().copied().collect();
    order.sort_by(|x, y| (-hex_best[x]).partial_cmp(&(-hex_best[y])).unwrap());
    for mut h in order.into_iter().take(starts) {
        loop {
            let nbrs: Vec<(i64, i64)> = hex_geometry::FACING_DELTAS.iter().map(|(dx, dy)| (h.0 + dx, h.1 + dy)).collect();
            for n in &nbrs {
                look(b, *n, &mut hex_best, &mut scored);
            }
            let mut nxt: Option<(i64, i64)> = None;
            for n in &nbrs {
                if let Some(v) = hex_best.get(n) {
                    if nxt.map_or(true, |m| *v > hex_best[&m]) {
                        nxt = Some(*n);
                    }
                }
            }
            match nxt {
                Some(n) if hex_best[&n] > hex_best[&h] => h = n,
                _ => break,
            }
        }
    }
    scored
}

// =============================================================================================================
// the "simple short list"
// =============================================================================================================
fn damage_drops(b: &mut Battle, u: UnitId, count: usize) -> HashSet<i64> {
    let pre_tn = b.cfg.i("MOVEMENT_SHORT_LIST_PRE_TN");
    let weapons = get_weapons(&b.units[u]);
    let mut max_distance = 0;
    for &w in &weapons {
        if let Some(r) = &b.units[u].items[w].weapon_range {
            max_distance = max_distance.max(r.long);
        }
    }
    let mut by_distance: IndexMap<i64, f64> = IndexMap::new();
    for &w in &weapons {
        for d in 0..=max_distance {
            if let Some(v) = crate::attack_resolution::table_value(b, u, w, d, pre_tn) {
                *by_distance.entry(d).or_insert(0.0) += v;
            }
        }
    }
    if by_distance.is_empty() {
        return HashSet::new();
    }
    let top = *by_distance.keys().max().unwrap();
    let mut drops: Vec<(f64, i64)> = (1..=top).map(|d| (by_distance.get(&d).copied().unwrap_or(0.0) - by_distance.get(&(d + 1)).copied().unwrap_or(0.0), d)).collect();
    drops.sort_by(|x, y| y.partial_cmp(x).unwrap());
    drops.into_iter().take(count).filter(|(drop, _)| *drop > 0.0).map(|(_, d)| d).collect()
}

fn short_list_distances(b: &mut Battle, replier: UnitId, first_mover: UnitId) -> HashSet<i64> {
    let count = b.cfg.i("MOVEMENT_SHORT_LIST_DROPS") as usize;
    let mut out: HashSet<i64> = HashSet::new();
    out.insert(1);
    out.extend(damage_drops(b, replier, count));
    out.extend(damage_drops(b, first_mover, count).into_iter().map(|d| d + 1));
    out
}

fn own_short_list(b: &mut Battle, mover: UnitId, other: UnitId, prepared: &[Opt], enemy_xy: (i64, i64)) -> Vec<Opt> {
    let distances = short_list_distances(b, mover, other);
    let my_hex = b.units[mover].hex.clone();
    let mut best: IndexMap<(String, &'static str), ((i64, i64, i64), Opt)> = IndexMap::new();
    for o in prepared {
        if Some(&o.label) != my_hex.as_ref() && !distances.contains(&hex_distance(o.hex_xy(), enemy_xy)) {
            continue;
        }
        let want = if o.hex_xy() != enemy_xy { crate::combat::direction_facing(o.hex_xy(), enemy_xy).unwrap() } else { o.facing };
        let turn = (o.facing - want).rem_euclid(6).min((want - o.facing).rem_euclid(6));
        let rank = (o.fc, -o.mp_spent, -turn);
        let k = (o.label.clone(), o.mode);
        if !best.contains_key(&k) || rank > best[&k].0 {
            best.insert(k, (rank, o.clone()));
        }
    }
    let kept: Vec<Opt> = best.into_values().map(|(_, o)| o).collect();
    if kept.is_empty() { prepared.to_vec() } else { kept }
}

fn search_start(b: &Battle, mover: UnitId, prepared: &[Opt]) -> (i64, i64) {
    match &b.units[mover].hex {
        Some(h) if !h.is_empty() => hex_geometry::parse_hex_label(h).unwrap(),
        _ => prepared[0].hex_xy(),
    }
}

/// One look-ahead's cache for the short-list reply model (_SHORT_LIST): rebuilt for each look-ahead.
#[derive(Default)]
struct ShortListCache {
    best: Vec<Opt>,
    turned: HashMap<(String, &'static str, i64), Opt>,
    distances: HashSet<i64>,
    built: bool,
}

/// short_list_states: the reply states the first mover looks at when it ends at state c.
fn short_list_states(b: &mut Battle, cache: &mut ShortListCache, c: &Opt, prepared2: &[Opt], other: UnitId, first_mover: UnitId, them: &Side, psr: &mut HashMap<(String, &'static str, &'static str, i64, i64), f64>) -> Vec<Opt> {
    if !cache.built {
        let mut best: IndexMap<(String, &'static str), Opt> = IndexMap::new();
        for o in prepared2 {
            let k = (o.label.clone(), o.mode);
            if !best.contains_key(&k) || (o.fc, -o.mp_spent) > (best[&k].fc, -best[&k].mp_spent) {
                best.insert(k, o.clone());
            }
        }
        cache.best = best.into_values().collect();
        cache.turned.clear();
        cache.distances = short_list_distances(b, other, first_mover);
        cache.built = true;
    }
    let other_hex = b.units[other].hex.clone();
    let mut states = Vec::new();
    for o in cache.best.clone() {
        if o.hex_xy() == c.hex_xy() {
            continue;
        }
        if Some(&o.label) != other_hex.as_ref() && !cache.distances.contains(&hex_distance(o.hex_xy(), c.hex_xy())) {
            continue;
        }
        let facing = crate::combat::direction_facing(o.hex_xy(), c.hex_xy()).unwrap();
        let key = (o.label.clone(), o.mode, facing);
        let state = match cache.turned.get(&key) {
            Some(s) => s.clone(),
            None => {
                let s = move_options::turned_option(&o, facing);
                cache.turned.insert(key, s.clone());
                psr.insert((s.label.clone(), s.facing_compass, s.mode, s.fc, s.mp_spent), them.psr_for_opt(b, &s));
                s
            }
        };
        states.push(state);
    }
    states
}

// =============================================================================================================
// the choice
// =============================================================================================================
type PsrMap = HashMap<(String, &'static str, &'static str, i64, i64), f64>;

fn psr_by_state(b: &Battle, side: &Side, prepared: &[Opt]) -> PsrMap {
    prepared.iter().map(|o| ((o.label.clone(), o.facing_compass, o.mode, o.fc, o.mp_spent), side.psr_for_opt(b, o))).collect()
}

fn cand_psr_key(c: &Candidate) -> (String, &'static str, &'static str, i64, i64) {
    (c.hex.clone(), c.facing, c.mode, c.fc, c.mp_spent)
}

/// _opponent_options: the reachable states a modeled second mover could end in. Fills `them.notes`.
fn opponent_options(b: &mut Battle, other: UnitId, them: &mut Side) -> Vec<StateKey> {
    let (x, y, facing) = hex_geometry::state_from_label(b.units[other].hex.as_deref().unwrap(), &b.units[other].facing).unwrap();
    if is_immobile(&b.units[other]) || matches!(b.units[other].stuck, Some(Some(_))) {
        return vec![(x, y, facing, 0, "Stand Still", 0)];
    }
    if b.units[other].prone {
        let tries = crate::piloting_rolls::can_stand(&b.units[other]) && b.units[other].pilot_hits < 5 && compute_running_mp(&b.units[other]) > 0;
        return vec![(x, y, facing, 0, if tries { "Run" } else { "Stand Still" }, 0)];
    }
    let mult = crate::equipment_systems::boost_multiplier(b, other, true);
    let saved = b.units[other].run_mp_multiplier;
    b.units[other].run_mp_multiplier = mult;
    let (opts, notes) = move_options::reduced_options(b, other, &HashSet::new(), None, None);
    b.units[other].run_mp_multiplier = saved;
    them.notes = notes;
    opts
}

/// The best candidate of a set of scored rows, ties to the nearer state (first seen otherwise): the modeled reply.
struct ReplyCtx {
    ev2: MoveEvaluator,
    prepared2: Vec<Opt>,
    index2: Option<move_attacks::MoverIndex>,
    reply_psr: PsrMap,
    cache: ShortListCache,
}

#[allow(clippy::too_many_arguments)]
fn modeled_reply(b: &mut Battle, c: &Opt, rc: &mut ReplyCtx, them: &mut Side, me: &Side, mover: UnitId, other: UnitId, terrain_xy: (i64, i64)) -> Option<Candidate> {
    // `me` is the first mover, `them` the second: here the second mover is the one choosing.
    let assumed = assumed_enemy_search(b, mover);
    let other_flag = b.units[other].prone || is_immobile(&b.units[other]);
    let mut cands: Vec<Candidate>;
    let mut rows: Vec<(f64, Candidate)> = Vec::new();
    let defender = rc.ev2.defender;
    let _ = defender;
    {
        let reply_rows = |b: &mut Battle, ev2: &mut MoveEvaluator, them: &Side, me: &Side, states: &[Opt], psr: &PsrMap| -> Vec<(f64, Candidate)> {
            let mut rows = Vec::new();
            for cand in ev2.evaluate(b, &c.label, c.facing_compass, c.fc, c.mode, c.mp_spent, states, true) {
                let p = psr[&cand_psr_key(&cand)];
                rows.push((them.obj(cand.dealt, cand.received, me.exp(cand.side_on_defender), them.exp(cand.side_on_mover), p), cand));
            }
            rows
        };
        if assumed == "short_list" && !rc.prepared2.is_empty() && !other_flag {
            let prepared2 = rc.prepared2.clone();
            let mut psr = rc.reply_psr.clone();
            let states = short_list_states(b, &mut rc.cache, c, &prepared2, other, mover, them, &mut psr);
            rc.reply_psr = psr.clone();
            rows = reply_rows(b, &mut rc.ev2, them, me, &states, &psr);
        } else if assumed == "grid" && !rc.prepared2.is_empty() {
            let prepared2 = rc.prepared2.clone();
            let start = hex_geometry::parse_hex_label(b.units[other].hex.as_deref().unwrap()).unwrap();
            let starts = b.cfg.i("MOVEMENT_SEARCH_STARTS") as usize;
            let psr = rc.reply_psr.clone();
            let ev2 = &mut rc.ev2;
            let them_ref: &Side = them;
            let mut f = |b: &mut Battle, states: &[Opt]| reply_rows(b, ev2, them_ref, me, states, &psr);
            rows = grid_search(b, &prepared2, &mut f, start, starts, Some(c.hex_xy()));
        } else {
            let prepared2 = rc.prepared2.clone();
            let psr = rc.reply_psr.clone();
            rows = reply_rows(b, &mut rc.ev2, them, me, &prepared2, &psr);
        }
    }
    cands = rows.iter().map(|(_, c)| c.clone()).collect();
    let mut best_score: Option<f64> = None;
    let mut best: Option<Candidate> = None;
    let mut any_damage = false;
    for (score, cand) in &rows {
        if cand.dealt > 0.0 {
            any_damage = true;
        }
        let key = round9(*score);
        if best.is_none() || key > best_score.unwrap() {
            best_score = Some(key);
            best = Some(cand.clone());
        } else if key == best_score.unwrap() && cand.distance < best.as_ref().unwrap().distance {
            best = Some(cand.clone());
        }
    }
    if rc.index2.is_some() {
        // The first mover has finished moving at c, so the second may charge or DFA it.
        let pose = move_attacks::pose_at(b, &c.label, c.facing_compass, c.fc, c.mode, Some(other_target(&rc.ev2)));
        let target_args = (c.label.clone(), c.facing_compass.to_string(), c.fc, c.mode.to_string(), c.mp_spent);
        let me_exp = me.exposure;
        let special = move_attacks::scored_options(b, other, rc.ev2.defender, &pose, rc.index2.as_ref().unwrap(), &mut rc.ev2, &them.exposure, &me_exp, &|bb: &Battle, mode: &str, fc: i64, hex: &str, facing: &str, mp: i64| them.psr_cost(bb, mode, fc, hex, facing, mp), BestMode::Lazy(&cands, me_exp), &target_args, &|d: f64, r: f64, dm: f64, rm: f64, e: f64| them.obj(d, r, dm, rm, e), &["charge", "dfa"]);
        if let Some(first) = special.into_iter().next() {
            if !any_damage || round9(first.0) > best_score.unwrap() {
                return Some(first.1);
            }
        }
    }
    if any_damage {
        return best;
    }
    // Nothing deals damage from here: the second mover would fall back to closing.
    let mut by_key: HashMap<(String, &'static str, &'static str, i64), Candidate> = HashMap::new();
    for c2 in &cands {
        by_key.insert(c2.key4(), c2.clone());
    }
    let prepared2 = rc.prepared2.clone();
    let fb = closing_fallback(b, other, rc.ev2.defender, them, &prepared2, terrain_xy, &|_| 0.0, Some(terrain_xy));
    let fb = match fb {
        Some(f) => f,
        None => {
            let pool: Vec<Opt> = prepared2.iter().filter(|o| o.hex_xy() != terrain_xy).cloned().collect();
            if pool.is_empty() {
                return None;
            }
            nearest_to(b, &pool, terrain_xy, None).clone()
        }
    };
    let mut hit = by_key.get(&(fb.label.clone(), fb.facing_compass, fb.mode, fb.fc)).cloned();
    if hit.is_none() && cands.len() < rc.prepared2.len() {
        // A grid search didn't look at the fallback's spot: score it now (None without LOS, as before).
        hit = rc.ev2.evaluate(b, &c.label, c.facing_compass, c.fc, c.mode, c.mp_spent, std::slice::from_ref(&fb), true).into_iter().next();
    }
    cands.clear();
    hit
}

fn other_target(ev: &MoveEvaluator) -> UnitId {
    ev.defender
}

pub use move_attacks::BestMode;

/// The result of choosing: the pick and its one-line note.
pub struct Choice {
    pub pick: Option<Pick>,
    pub note: String,
}

fn pick_text(p: &Opt) -> Pick {
    p.pick()
}

fn fallback_pick(b: &mut Battle, mover: UnitId, other: UnitId, me: &Side, prepared: &[Opt], enemy_xy: (i64, i64), dealt_for: &dyn Fn(&Opt) -> f64, why: &str, ties: &mut Ties) -> (Pick, String) {
    let fb = closing_fallback(b, mover, other, me, prepared, enemy_xy, dealt_for, None);
    if let Some(f) = fb {
        return (pick_text(&f), format!("{} - closing fallback", why));
    }
    let pool = safest(b, me, prepared.to_vec());
    let o = nearest_to(b, &pool, enemy_xy, Some(ties)).clone();
    (pick_text(&o), format!("{} - closing fallback found nothing; nearest reachable spot to the enemy", why))
}

/// The score rows of the first mover: (score, state, (dealt, received, dm, rm, extras, reply)).
type Payload = (f64, f64, f64, f64, f64, Option<Candidate>);

fn best_by_score<R: Clone>(b: &mut Battle, scored: &[(f64, Opt, R)], enemy_xy: (i64, i64), ties: &mut Ties) -> (Opt, R) {
    let top = scored.iter().map(|(s, _, _)| round9(*s)).fold(f64::NEG_INFINITY, f64::max);
    let tied: Vec<&(f64, Opt, R)> = scored.iter().filter(|(s, _, _)| round9(*s) == top).collect();
    let nearest = tied.iter().map(|t| hex_distance(t.1.hex_xy(), enemy_xy)).min().unwrap();
    let tied: Vec<&(f64, Opt, R)> = tied.into_iter().filter(|t| hex_distance(t.1.hex_xy(), enemy_xy) == nearest).collect();
    let i = if tied.len() > 1 {
        let pool: Vec<&Opt> = tied.iter().map(|t| &t.1).collect();
        ties.pick(b, &pool)
    } else {
        0
    };
    (tied[i].1.clone(), tied[i].2.clone())
}

fn spots_text(checked: usize, total: usize, search: &str) -> String {
    if search == "if_then" {
        return format!("IF/THEN, {} spot{} scored of {}", checked, if checked != 1 { "s" } else { "" }, total);
    }
    if checked == total { format!("{} spots", total) } else { format!("{} of {} spots (grid search)", checked, total) }
}

/// choose: the mover's end-of-movement state - (pick, note).
#[allow(clippy::too_many_arguments)]
pub fn choose(b: &mut Battle, mover: UnitId, other: UnitId, moves_first: bool, standup_mp: Option<i64>, entry_edge: Option<&[String]>, ties: &mut Ties) -> (Option<Pick>, String) {
    let (pick, note, score, ctx) = choose_normal(b, mover, other, moves_first, standup_mp, entry_edge, ties);
    if let Some(mut ctx) = ctx {
        if entry_edge.is_none() && (b.cfg.b("CHARGES") || b.cfg.b("DFA")) && move_attacks::can_be_attacked(b, other, !moves_first) {
            if let Some(special) = movement_attack_pick(b, mover, other, standup_mp, score, &mut ctx) {
                return special;
            }
        }
    }
    (pick, note)
}

/// What a normal pick leaves for the charge decision: (ev1, me, them, static candidates).
pub struct NormalCtx {
    ev1: MoveEvaluator,
    me: Side,
    them: Side,
    static_cands: Vec<Candidate>,
}

fn movement_attack_pick(b: &mut Battle, mover: UnitId, other: UnitId, standup_mp: Option<i64>, normal_score: Option<f64>, ctx: &mut NormalCtx) -> Option<(Option<Pick>, String)> {
    let mut index = move_attacks::MoverIndex::new(b, mover, standup_mp, &mut ctx.me.notes);
    let pose = move_attacks::pose_of(b, other);
    let target_args = (b.units[other].hex.clone().unwrap(), b.units[other].facing.clone(), b.units[other].move_fc, b.units[other].move_mode.clone(), b.units[other].mp_spent);
    let me = &ctx.me;
    let them = &ctx.them;
    let static_cands = ctx.static_cands.clone();
    let options = move_attacks::scored_options(b, mover, other, &pose, &index, &mut ctx.ev1, &me.exposure, &them.exposure, &|bb: &Battle, mode: &str, fc: i64, hex: &str, facing: &str, mp: i64| me.psr_cost(bb, mode, fc, hex, facing, mp), BestMode::Lazy(&static_cands, them.exposure), &target_args, &|d: f64, r: f64, dm: f64, rm: f64, e: f64| me.obj(d, r, dm, rm, e), &["charge", "dfa"]);
    index.release();
    if options.is_empty() {
        return None;
    }
    let (score, cand, state, what) = options[0].clone();
    if let Some(ns) = normal_score {
        if score <= ns {
            return None;
        }
    }
    let beats = match normal_score {
        None => "nothing".to_string(),
        Some(ns) => format!("{:.3}", ns),
    };
    let other_name = b.units[other].side_name.clone().unwrap_or_default();
    let psr = me.psr_for_pick(b, &state);
    let note = if !matches!(me.objective, Objective::Ratio) {
        format!("{} on {}: {} beats {}", what, other_name, me.note(cand.dealt, cand.received, them.exp(cand.side_on_defender), me.exp(cand.side_on_mover), psr, "incl. self-damage"), beats)
    } else {
        format!("{} on {}: score {:.3} = dealt {:.2} x{:.2} / (received {:.2} incl. self-damage x{:.2} + PSR {:.2}) beats {}", what, other_name, score, cand.dealt, them.exp(cand.side_on_defender), cand.received, me.exp(cand.side_on_mover), psr, beats)
    };
    Some((Some(state), note))
}

#[allow(clippy::too_many_arguments)]
fn choose_normal(b: &mut Battle, mover: UnitId, other: UnitId, moves_first: bool, standup_mp: Option<i64>, entry_edge: Option<&[String]>, ties: &mut Ties) -> (Option<Pick>, String, Option<f64>, Option<NormalCtx>) {
    let mut me = Side::new(b, mover, standup_mp.is_none());
    let exclude = move_options::occupied_hexes(b, mover, other);
    let (options, notes) = move_options::reduced_options(b, mover, &exclude, standup_mp, entry_edge);
    me.notes = notes;

    if b.units[other].hex.is_none() {
        // The enemy hasn't entered the board: nothing to shoot or to model. Head for its home edge.
        let edge_row = b.units[other].home_edge_row.clone().filter(|r| !r.is_empty()).or_else(|| b.units[other].home_edge.clone()).unwrap();
        let enemy_label = edge_row[edge_row.len() / 2].clone();
        let enemy_xy = hex_geometry::parse_hex_label(&enemy_label).unwrap();
        let prepared = move_options::prepare_options(b, mover, &options);
        if prepared.is_empty() {
            return (None, "no reachable spot".into(), None, None);
        }
        let fb = closing_fallback(b, mover, other, &me, &prepared, enemy_xy, &|_| 0.0, None);
        let pick = match &fb {
            Some(f) => f.clone(),
            None => nearest_to(b, &prepared, enemy_xy, Some(ties)).clone(),
        };
        return (Some(pick.pick()), format!("no enemy on the board yet - heads for its home edge near {}{}", enemy_label, if fb.is_some() { " (closing fallback)" } else { "" }), None, None);
    }

    let mut them = Side::new(b, other, true);
    link(b, &mut me, &mut them);
    let enemy_label = b.units[other].hex.clone().unwrap();
    let enemy_xy = hex_geometry::parse_hex_label(&enemy_label).unwrap();
    let mut ev1 = MoveEvaluator::new(b, mover, other);
    let prepared1 = ev1.prepare(b, &options);
    if prepared1.is_empty() {
        return (None, "no reachable spot".into(), None, None);
    }
    let mut prepared_by_key: HashMap<(String, &'static str, &'static str, i64), usize> = HashMap::new();
    for (i, o) in prepared1.iter().enumerate() {
        prepared_by_key.insert((o.label.clone(), o.facing_compass, o.mode, o.fc), i);
    }
    let (o_facing, o_fc, o_mode, o_mp) = (b.units[other].facing.clone(), b.units[other].move_fc, b.units[other].move_mode.clone(), b.units[other].mp_spent);
    let own = own_search(b, mover);
    let starts = b.cfg.i("MOVEMENT_SEARCH_STARTS") as usize;
    let static_cands: Vec<Candidate>;
    {
        let mut static_rows = |b: &mut Battle, states: &[Opt], ev1: &mut MoveEvaluator, me: &Side, them: &Side| -> Vec<(f64, Candidate)> {
            ev1.evaluate(b, &enemy_label, &o_facing, o_fc, &o_mode, o_mp, states, true).into_iter().map(|cand| (me.obj(cand.dealt, cand.received, them.exp(cand.side_on_defender), me.exp(cand.side_on_mover), me.psr_for_cand(b, &cand)), cand)).collect()
        };
        if !moves_first && own == "short_list" {
            let states = own_short_list(b, mover, other, &prepared1, enemy_xy);
            if b.cfg.b("MOVEMENT_SHORT_LIST_GRID") {
                let start = search_start(b, mover, &states);
                let (mem, tem) = (&me, &them);
                let ev = &mut ev1;
                let mut f = |b: &mut Battle, s: &[Opt]| static_rows(b, s, ev, mem, tem);
                static_cands = grid_search(b, &states, &mut f, start, starts, Some(enemy_xy)).into_iter().map(|(_, c)| c).collect();
            } else {
                static_cands = ev1.evaluate(b, &enemy_label, &o_facing, o_fc, &o_mode, o_mp, &states, true);
            }
        } else if !moves_first && own == "grid" {
            let start = search_start(b, mover, &prepared1);
            let (mem, tem) = (&me, &them);
            let ev = &mut ev1;
            let mut f = |b: &mut Battle, s: &[Opt]| static_rows(b, s, ev, mem, tem);
            static_cands = grid_search(b, &prepared1, &mut f, start, starts, Some(enemy_xy)).into_iter().map(|(_, c)| c).collect();
        } else {
            static_cands = ev1.evaluate(b, &enemy_label, &o_facing, o_fc, &o_mode, o_mp, &prepared1, true);
        }
    }
    if std::env::var("BT_DUMP_STATIC").is_ok() {
        for c in &static_cands {
            eprintln!("STATIC {} {} {} {} {} {:?} {:?}", c.hex, c.facing, c.mode, c.fc, c.mp_spent, c.dealt, c.received);
        }
    }
    let static_dealt: HashMap<(String, &'static str, &'static str, i64), f64> = static_cands.iter().map(|c| (c.key4(), c.dealt)).collect();
    let dealt_for = move |o: &Opt| static_dealt.get(&(o.label.clone(), o.facing_compass, o.mode, o.fc)).copied().unwrap_or(0.0);

    let two_ply = moves_first && b.cfg.b("MOVEMENT_TWO_PLY");
    let other_name = b.units[other].side_name.clone().unwrap_or_default();

    if !two_ply {
        let scored: Vec<(f64, Opt, Candidate)> = static_cands
            .iter()
            .map(|cand| {
                let o = prepared1[prepared_by_key[&cand.key4()]].clone();
                let psr = me.psr_for_cand(b, cand);
                (me.obj(cand.dealt, cand.received, them.exp(cand.side_on_defender), me.exp(cand.side_on_mover), psr), o, cand.clone())
            })
            .collect();
        if !scored.is_empty() && scored.iter().any(|(_, _, c)| c.dealt > 0.0) {
            let (o, cand) = best_by_score(b, &scored, enemy_xy, ties);
            let psr = me.psr_for_cand(b, &cand);
            let score = me.obj(cand.dealt, cand.received, them.exp(cand.side_on_defender), me.exp(cand.side_on_mover), psr);
            let note = me.note(cand.dealt, cand.received, them.exp(cand.side_on_defender), me.exp(cand.side_on_mover), psr, &format!("enemy held at {}; {} spots with LOS", enemy_label, scored.len()));
            let ctx = NormalCtx { ev1, me, them, static_cands };
            return (Some(o.pick()), note, Some(score), Some(ctx));
        }
        let (p, n) = fallback_pick(b, mover, other, &me, &prepared1, enemy_xy, &dealt_for, "no spot deals damage", ties);
        let ctx = NormalCtx { ev1, me, them, static_cands };
        return (Some(p), n, None, Some(ctx));
    }

    // --- two-ply: score every spot by the second mover's modeled reply ---
    let mut ev2 = MoveEvaluator::new(b, other, mover);
    let opp = opponent_options(b, other, &mut them);
    let prepared2 = ev2.prepare(b, &opp);
    let mut index2 = None;
    if (b.cfg.b("CHARGES") || b.cfg.b("DFA")) && !(b.units[other].prone || is_immobile(&b.units[other])) {
        index2 = Some(move_attacks::MoverIndex::new(b, other, None, &mut them.notes));
    }
    let reply_psr = psr_by_state(b, &them, &prepared2);
    let mut rc = ReplyCtx { ev2, prepared2, index2, reply_psr, cache: ShortListCache::default() };
    let n_replies = rc.prepared2.len();
    let own_s = own.as_str();
    let scored: Vec<(f64, Opt, Payload)>;
    {
        let mut score_spot = |b: &mut Battle, c: &Opt, me: &Side, them: &mut Side, rc: &mut ReplyCtx| -> (f64, Opt, Payload) {
            let reply = modeled_reply(b, c, rc, them, me, mover, other, c.hex_xy());
            let (dealt, received, dealt_mult, received_mult);
            match &reply {
                None => {
                    dealt = 0.0;
                    received = 0.0;
                    dealt_mult = 1.0;
                    received_mult = 1.0;
                }
                Some(r) => {
                    dealt = r.received;
                    received = r.dealt;
                    dealt_mult = them.exp(r.side_on_mover);
                    received_mult = me.exp(r.side_on_defender);
                }
            }
            let psr = me.psr_for_opt(b, c);
            (me.obj(dealt, received, dealt_mult, received_mult, psr), c.clone(), (dealt, received, dealt_mult, received_mult, psr, reply))
        };
        if own_s == "short_list" {
            let states = own_short_list(b, mover, other, &prepared1, enemy_xy);
            if b.cfg.b("MOVEMENT_SHORT_LIST_GRID") {
                let start = search_start(b, mover, &states);
                let mut f = |b: &mut Battle, group: &[Opt]| group.iter().map(|c| score_spot(b, c, &me, &mut them, &mut rc)).map(|(s, o, p)| (s, (o, p))).collect::<Vec<_>>();
                scored = grid_search(b, &states, &mut f, start, starts, None).into_iter().map(|(s, (o, p))| (s, o, p)).collect();
            } else {
                scored = states.iter().map(|c| score_spot(b, c, &me, &mut them, &mut rc)).collect();
            }
        } else if own_s == "if_then" {
            panic!("MOVEMENT_SEARCH if_then is not translated yet");
        } else if own_s == "grid" {
            let start = search_start(b, mover, &prepared1);
            let mut f = |b: &mut Battle, group: &[Opt]| group.iter().map(|c| score_spot(b, c, &me, &mut them, &mut rc)).map(|(s, o, p)| (s, (o, p))).collect::<Vec<_>>();
            scored = grid_search(b, &prepared1, &mut f, start, starts, None).into_iter().map(|(s, (o, p))| (s, o, p)).collect();
        } else {
            scored = prepared1.iter().map(|c| score_spot(b, c, &me, &mut them, &mut rc)).collect();
        }
    }
    let any_dealt = scored.iter().any(|(_, _, p)| p.0 > 0.0);
    if any_dealt {
        let (o, (dealt, received, dm, rm, extras, reply)) = best_by_score(b, &scored, enemy_xy, ties);
        let reply_txt = match &reply {
            Some(r) => format!("; modeled reply {} -> {} {} {}{}", other_name, r.hex, r.facing, r.mode, if r.attack.is_empty() { String::new() } else { format!(" ({})", r.attack.to_uppercase()) }),
            None => "; modeled reply: none with LOS".to_string(),
        };
        let reply_search = match assumed_enemy_search(b, mover).as_str() {
            "grid" => " (grid search)",
            "short_list" => " (short list)",
            _ => "",
        };
        let how = format!("two-ply, {} x {} replies{}{}", spots_text(scored.len(), prepared1.len(), own_s), n_replies, reply_search, reply_txt);
        let note = me.note(dealt, received, dm, rm, extras, &how);
        let score = me.obj(dealt, received, dm, rm, extras);
        let ctx = NormalCtx { ev1, me, them, static_cands };
        return (Some(o.pick()), note, Some(score), Some(ctx));
    }
    let (p, n) = fallback_pick(b, mover, other, &me, &prepared1, enemy_xy, &dealt_for, &format!("no spot deals damage even before the reply (two-ply, {} spots)", prepared1.len()), ties);
    let ctx = NormalCtx { ev1, me, them, static_cands };
    (Some(p), n, None, Some(ctx))
}
