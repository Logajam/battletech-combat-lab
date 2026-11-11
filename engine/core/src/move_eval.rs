// Translated from INTEGRATION__ranged_combat.py: MoveEvaluator (what a mover's end states are worth against a defender
// pinned at any hex), the heat-limited scorer it uses, and _with_physical. The Python's FireTable / scorer sharing and
// speed memos are caches of pure functions: here one memo per side stands in for them.
use crate::fasthash::{HashMap, HashSet};
use std::rc::Rc;

use crate::arcs::{self, ArcKey};
use crate::attack_resolution::{self as ar, Adjuster};
use crate::battle::{Battle, UnitId};
use crate::damage_resolution::get_weapons;
use crate::equipment::ItemId;
use crate::fire_modes::{self, Planner};
use crate::hex_geometry;
use crate::los::{self, hex_distance, Height};
use crate::mech_state::*;
use crate::move_options::Opt;
use crate::physical::{self, PhysOption, PhysPlanner, Reach, Worth};
use crate::water;

pub const IMMOBILE_TMM: i64 = -4;
const PRE_TN_MIN: i64 = crate::weapon_selection::PRE_TN_MIN;
const PRE_TN_MAX: i64 = crate::weapon_selection::PRE_TN_MAX;

/// One (hex, facing, mode) state a mover could reach, with expected damage in both directions (MovementCandidate).
#[derive(Clone, Debug)]
pub struct Candidate {
    pub hex: String,
    pub facing: &'static str,
    pub mode: &'static str,
    pub fc: i64,
    pub mp_spent: i64,
    pub distance: i64,
    pub dealt: f64,
    pub received: f64,
    pub movement_heat: i64,
    pub side_on_defender: &'static str,
    pub side_on_mover: &'static str,
    pub attack: &'static str,
}

impl Candidate {
    pub fn key4(&self) -> (String, &'static str, &'static str, i64) {
        (self.hex.clone(), self.facing, self.mode, self.fc)
    }
}

/// The water case of one firing line: None = dry (the old path); Blocked = no attack crosses the water line.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum Wet {
    Dry,
    Blocked,
    Case(usize),
}

struct WetCase {
    state: &'static str,
    blocked: Vec<ItemId>,
    bonus: i64,
}

type Memo = HashMap<(Vec<ItemId>, i64, &'static str, i64, i64, i64, i64, &'static str), f64>;

/// scorer_getter + _make_heat_limited_scorer for one (firer, target) pair.
struct FireSide {
    who: UnitId,
    target: UnitId,
    base_adjust: Adjuster,
    blocked: HashSet<ItemId>,
    scale_on: bool,
    usable: Vec<ItemId>,
    torpedoes: HashSet<ItemId>,
    w_locs: crate::water::WeaponLocs,
    dissipation: i64,
    other: i64,
    planners: HashMap<(i64, &'static str), (Rc<Adjuster>, Planner<'static>)>,
    scales: HashMap<&'static str, HashMap<ItemId, f64>>,
    memo: Memo,
    unavail: HashMap<(ArcKey, Vec<ItemId>, Wet), Vec<ItemId>>,
}

impl FireSide {
    fn new(b: &mut Battle, who: UnitId, target: UnitId, adjust: Adjuster, blocked: HashSet<ItemId>, scale_on: bool) -> FireSide {
        let weapons = get_weapons(&b.units[who]);
        let usable: Vec<ItemId> = weapons.iter().copied().filter(|w| !blocked.contains(w)).collect();
        let torpedoes: HashSet<ItemId> = usable.iter().copied().filter(|w| crate::weapon_rules::is_torpedo(&b.units[who], *w)).collect();
        let w_locs = ar::weapon_locations(&b.units[who]);
        let dissipation = compute_heat_dissipation(&b.units[who]);
        let other = crate::heat::other_heat(b, who);
        FireSide { who, target, base_adjust: adjust, blocked, scale_on, usable, torpedoes, w_locs, dissipation, other, planners: HashMap::default(), scales: HashMap::default(), memo: HashMap::default(), unavail: HashMap::default() }
    }

    /// scorer(key, held, ams_k, wet)(distance, pre_tn, move_heat, side) -> expected damage (worth) of the weapons the
    /// heat-limited choice would fire.
    #[allow(clippy::too_many_arguments)]
    fn score(&mut self, b: &mut Battle, cases: &[WetCase], key: &ArcKey, held: &HashSet<ItemId>, ams_k: i64, wet: Wet, distance: i64, pre_tn: i64, move_heat: i64, side: &'static str) -> f64 {
        let mut held_sorted: Vec<ItemId> = held.iter().copied().collect();
        held_sorted.sort();
        let uk = (key.clone(), held_sorted, wet);
        let unavailable: Vec<ItemId> = match self.unavail.get(&uk) {
            Some(u) => u.clone(),
            None => {
                let mut set: HashSet<ItemId> = self.blocked.clone();
                set.extend(ar::arc_unavailable(&b.units[self.who], key));
                set.extend(held.iter().copied());
                match wet {
                    Wet::Case(i) => set.extend(cases[i].blocked.iter().copied()),
                    _ => set.extend(self.torpedoes.iter().copied()),
                }
                let mut v: Vec<ItemId> = set.into_iter().collect();
                v.sort();
                self.unavail.insert(uk, v.clone());
                v
            }
        };
        let (w_state, bonus) = match wet {
            Wet::Case(i) => (cases[i].state, cases[i].bonus),
            _ => (water::GROUND, 0),
        };
        let mk = (unavailable.clone(), ams_k, w_state, bonus, distance, pre_tn, move_heat, side);
        if let Some(v) = self.memo.get(&mk) {
            return *v;
        }
        // the planner of this (AMS count, water state)
        let pk = (ams_k, w_state);
        if !self.planners.contains_key(&pk) {
            let adj = ar::with_range_adjuster(self.base_adjust.clone(), &b.units[self.who], w_state);
            let adj = Rc::new(adj);
            let share = fire_modes::ams_share(b, self.who, ams_k, &self.usable);
            let planner = Planner::new_shared(self.who, self.target, adj.clone(), share);
            self.planners.insert(pk, (adj, planner));
        }
        if self.scale_on && !self.scales.contains_key(side) {
            let weapons = get_weapons(&b.units[self.who]);
            let s: HashMap<ItemId, f64> = crate::structure_weight::multipliers(b, self.who, &weapons, self.target, side).into_iter().collect();
            self.scales.insert(side, s);
        }
        let scale = if self.scale_on { self.scales.get(side) } else { None };
        let (adj, planner) = self.planners.get_mut(&pk).unwrap();
        let adj: Rc<Adjuster> = adj.clone();
        let unavail_set: HashSet<ItemId> = unavailable.iter().copied().collect();
        let (min_heat, max_heat) = (b.units[self.who].min_heat, b.units[self.who].max_heat);
        let got = crate::weapon_selection::select_weapons_scaled(b, self.who, distance, pre_tn, min_heat, max_heat, self.dissipation + bonus, move_heat, self.other, Some(&*adj), &unavail_set, scale, Some(planner), Some(side)).1;
        self.memo.insert(mk, got);
        got
    }
}

/// The LOS facts of one line a -> t: (LOS result, entry hexside at t, distance, the arcs of a -> t).
#[derive(Clone, Debug)]
pub struct PairInfo {
    pub los: los::LOSResult,
    pub entry_dir: i64,
    pub distance: i64,
    pub arcs: [i64; 6],
}

pub fn pair_info(b: &Battle, a: (i64, i64), t: (i64, i64), ah: Height, th: Height) -> Option<PairInfo> {
    let trace = los::trace_los_path(a, t, &b.board, ah, th).ok()?;
    let steps = &trace.steps;
    let entry_dir = if steps.len() >= 2 { crate::combat::direction_facing(t, steps[steps.len() - 2].hex).unwrap() } else { 0 };
    Some(PairInfo { los: trace.result.clone(), entry_dir, distance: hex_distance(a, t), arcs: arcs::arcs_between(a, t) })
}

/// ams.Coverage: how many attacks one mech's AMS could engage from a shooter in each arc.
pub struct Coverage {
    ams: Vec<ItemId>,
    locs: HashMap<ItemId, Vec<String>>,
    legs: Vec<(String, i64)>,
    action: crate::mech_state::ArcAction,
    memo: HashMap<([i64; 6], i64), i64>,
    mech: UnitId,
}

impl Coverage {
    pub fn new(b: &mut Battle, u: UnitId) -> Coverage {
        let ams = if crate::ams::can_engage(&b.units[u]) { crate::ams::systems(b, u) } else { vec![] };
        let locs: HashMap<ItemId, Vec<String>> = if ams.is_empty() { HashMap::default() } else { ar::weapon_locations(&b.units[u]).into_iter().collect() };
        Coverage { ams, locs, legs: arcs::leg_offsets(&b.units[u]), action: arcs::current_action(&b.units[u]), memo: HashMap::default(), mech: u }
    }
    pub fn any(&self) -> bool {
        !self.ams.is_empty()
    }
    pub fn engagements(&mut self, b: &Battle, shooter_arcs: &[i64; 6], facing: i64) -> i64 {
        if self.ams.is_empty() {
            return 0;
        }
        let k = (*shooter_arcs, facing);
        if let Some(v) = self.memo.get(&k) {
            return *v;
        }
        let key = arcs::key_for(shooter_arcs, facing, &self.action, &self.legs);
        let blocked = arcs::unavailable(&b.units[self.mech], &self.ams, &self.locs, &key);
        let usable: Vec<ItemId> = self.ams.iter().copied().filter(|w| !blocked.contains(w)).collect();
        let got = crate::ams::engagement_capacity(&b.units[self.mech], &usable);
        self.memo.insert(k, got);
        got
    }
}

struct HexRow {
    atk_to_def: PairInfo,
    def_to_atk: PairInfo,
    distance: i64,
    a_to_d: [i64; 6],
    d_to_a: [i64; 6],
    side_on_def: &'static str,
    dealt_hex: i64,
    received_hex: i64,
    r_keys: Rc<Vec<ArcKey>>,
    r_cls: usize,
    k_def: i64,
    wet_dealt: Wet,
    wet_received: Wet,
    by_facing: [Option<(&'static str, Rc<Vec<ArcKey>>, usize, i64)>; 6],
    entry_at_atk: i64,
}

/// What `evaluate` returns plus nothing else; kept as a struct so the first/second mover roles read alike.
pub struct MoveEvaluator {
    pub mover: UnitId,
    pub defender: UnitId,
    defender_immobile: bool,
    mover_cond: Option<(i64, HashSet<ItemId>, String)>,
    defender_cond: Option<(i64, HashSet<ItemId>, String)>,
    mover_side: FireSide,
    defender_side: FireSide,
    water_depths: Option<crate::fasthash::IndexMap<String, i64>>,
    wet_cases: Vec<WetCase>,
    wet_index: HashMap<(bool, i64, bool, i64, bool, bool), Wet>,
    mover_arcs: (Vec<ArcAction>, Vec<(String, i64)>),
    defender_arcs: (Vec<ArcAction>, Vec<(String, i64)>),
    pub mover_physical: bool,
    pub defender_physical: bool,
    mover_planner: PhysPlanner,
    defender_planner: PhysPlanner,
    best_dealt: HashMap<(usize, i64, i64, i64, &'static str, i64, Wet), f64>,
    best_received: HashMap<(usize, i64, i64, i64, &'static str, i64, Wet), f64>,
    mover_classes: Classes,
    defender_classes: Classes,
    mover_own: i64,
    defender_own: i64,
    mover_ams: Coverage,
    defender_ams: Coverage,
}

/// _ArcClasses: sorts (target arcs, facing) pairs by the set of ArcKeys they give.
#[derive(Default)]
struct Classes {
    by_keys: HashMap<Vec<ArcKey>, (usize, Rc<Vec<ArcKey>>)>,
}

impl Classes {
    fn of(&mut self, actions: &[ArcAction], legs: &[(String, i64)], target_arcs: &[i64; 6], facing: i64) -> (usize, Rc<Vec<ArcKey>>) {
        let keys: Vec<ArcKey> = arcs::arc_keys(target_arcs, facing, actions, legs).into_iter().map(|(k, _)| k).collect();
        let n = self.by_keys.len();
        let e = self.by_keys.entry(keys.clone()).or_insert_with(|| (n, Rc::new(keys)));
        (e.0, e.1.clone())
    }
}

fn clamp_tn(t: i64) -> i64 {
    if t > PRE_TN_MAX { PRE_TN_MAX } else if t < PRE_TN_MIN { PRE_TN_MIN } else { t }
}

impl MoveEvaluator {
    pub fn new(b: &mut Battle, mover: UnitId, defender: UnitId) -> MoveEvaluator {
        let defender_immobile = is_immobile(&b.units[defender]);
        let mover_cond = ar::firing_conditions(b, mover);
        let defender_cond = ar::firing_conditions(b, defender);
        let mover_blocked: HashSet<ItemId> = mover_cond.as_ref().map(|c| c.1.clone()).unwrap_or_default().into_iter().chain(crate::ammo::unavailable_weapons(&b.units[mover])).chain(fire_modes::jammed_ids(&b.units[mover])).chain(crate::weapon_profiles::array_gun_ids(b, mover)).collect();
        let defender_blocked: HashSet<ItemId> = defender_cond.as_ref().map(|c| c.1.clone()).unwrap_or_default().into_iter().chain(crate::ammo::unavailable_weapons(&b.units[defender])).chain(fire_modes::jammed_ids(&b.units[defender])).chain(crate::weapon_profiles::array_gun_ids(b, defender)).collect();
        let mover_aim = ar::aimed_shot_location(b, defender, false);
        let mover_adjust = ar::tn_adjuster(b, mover, defender, mover_aim.as_deref(), 0);
        let defender_adjust = ar::tn_adjuster(b, defender, mover, None, 0);
        let weighting = b.cfg.f("MOVEMENT_STRUCTURE_WEIGHT") != 1.0;
        let mover_side = FireSide::new(b, mover, defender, mover_adjust, mover_blocked, weighting);
        let defender_side = FireSide::new(b, defender, mover, defender_adjust, defender_blocked, weighting);
        let water_depths = {
            let d = water::hexes_by_depth(&b.board);
            if d.is_empty() { None } else { Some(d) }
        };
        let mover_arcs = (arcs::arc_options(&b.units[mover], "ranged"), arcs::leg_offsets(&b.units[mover]));
        let defender_arcs = (arcs::arc_options(&b.units[defender], "ranged"), arcs::leg_offsets(&b.units[defender]));
        let mover_physical = !(b.units[mover].shutdown || is_immobile(&b.units[mover]));
        let defender_physical = !(b.units[defender].shutdown || b.units[defender].prone || defender_immobile);
        let mw = Worth::new(b, defender, true);
        let dw = Worth::new(b, mover, true);
        let mover_planner = PhysPlanner::new(b, mover, Some(mw));
        let defender_planner = PhysPlanner::new(b, defender, Some(dw));
        let mover_own = crate::equipment_systems::own_attack_modifier(&b.units[mover]);
        let defender_own = crate::equipment_systems::own_attack_modifier(&b.units[defender]);
        let mover_ams = Coverage::new(b, mover);
        let defender_ams = Coverage::new(b, defender);
        MoveEvaluator {
            mover,
            defender,
            defender_immobile,
            mover_cond,
            defender_cond,
            mover_side,
            defender_side,
            water_depths,
            wet_cases: vec![],
            wet_index: HashMap::default(),
            mover_arcs,
            defender_arcs,
            mover_physical,
            defender_physical,
            mover_planner,
            defender_planner,
            best_dealt: HashMap::default(),
            best_received: HashMap::default(),
            mover_classes: Classes::default(),
            defender_classes: Classes::default(),
            mover_own,
            defender_own,
            mover_ams,
            defender_ams,
        }
    }

    /// _wet: the water case of `firer` at f_label shooting `target` at t_label.
    #[allow(clippy::too_many_arguments)]
    fn wet(&mut self, b: &Battle, firer_is_mover: bool, f_label: &str, f_prone: bool, t_label: &str, t_prone: bool) -> Wet {
        let depths = self.water_depths.as_ref().unwrap();
        let (f_depth, t_depth) = (depths.get(f_label).copied().unwrap_or(0), depths.get(t_label).copied().unwrap_or(0));
        if f_depth == 0 && t_depth == 0 {
            return Wet::Dry;
        }
        let (firer, target) = if firer_is_mover { (self.mover, self.defender) } else { (self.defender, self.mover) };
        let line = f_depth > 0 && t_depth > 0 && get_weapons(&b.units[firer]).iter().any(|w| crate::weapon_rules::is_torpedo(&b.units[firer], *w)) && water::water_line(&b.board, f_label, t_label);
        let key = (firer_is_mover, f_depth, f_prone, t_depth, t_prone, line);
        if let Some(c) = self.wet_index.get(&key) {
            return *c;
        }
        let f_state = water::state_at(&b.board, Some(f_label), f_prone, is_superheavy(&b.units[firer]));
        let t_state = water::state_at(&b.board, Some(t_label), t_prone, is_superheavy(&b.units[target]));
        let weapons = get_weapons(&b.units[firer]);
        let locs = ar::weapon_locations(&b.units[firer]);
        let case = match water::blocked_weapon_ids(&b.units[firer], &weapons, &locs, f_state, t_state, line) {
            None => Wet::Blocked,
            Some(blocked) => {
                let mut bl: Vec<ItemId> = blocked.into_iter().collect();
                bl.sort();
                self.wet_cases.push(WetCase { state: f_state, blocked: bl, bonus: water::dissipation_bonus(b, firer, Some(f_state)) });
                Wet::Case(self.wet_cases.len() - 1)
            }
        };
        self.wet_index.insert(key, case);
        case
    }

    /// _physical_water: (the physical attack kinds water allows - None = all, the target's water state - None = land).
    fn physical_water(&self, b: &Battle, a_label: &str, a_prone: bool, t_label: &str, t_prone: bool, a_sup: bool, t_sup: bool) -> (Option<Vec<&'static str>>, Option<&'static str>) {
        if self.water_depths.is_none() {
            return (None, None);
        }
        let t_state = water::state_at(&b.board, Some(t_label), t_prone, t_sup);
        (water::physical_allowed(water::state_at(&b.board, Some(a_label), a_prone, a_sup), t_state), if t_state == water::GROUND { None } else { Some(t_state) })
    }

    pub fn prepare(&self, b: &Battle, options: &[crate::move_options::StateKey]) -> Vec<Opt> {
        crate::move_options::prepare_options(b, self.mover, options)
    }

    /// Every prepared state with LOS to a defender standing at (def_hex_label, def_facing_compass) having moved
    /// def_mode / def_fc hexes / def_mp_spent MP.
    #[allow(clippy::too_many_arguments)]
    pub fn evaluate(&mut self, b: &mut Battle, def_hex_label: &str, def_facing_compass: &str, def_fc: i64, def_mode: &str, def_mp_spent: i64, prepared: &[Opt], physical_reply: bool) -> Vec<Candidate> {
        let (mover, defender) = (self.mover, self.defender);
        let def_hex = hex_geometry::parse_hex_label(def_hex_label).unwrap();
        let def_facing = hex_geometry::compass_to_facing(def_facing_compass).unwrap();
        let (defender_tmm, def_move_heat);
        if self.defender_immobile {
            defender_tmm = IMMOBILE_TMM + target_size_modifier(&b.units[defender]);
            def_move_heat = 0;
        } else {
            defender_tmm = crate::combat::fc_to_tmm(def_fc, def_mode == "Jump").unwrap() + target_size_modifier(&b.units[defender]);
            def_move_heat = crate::heat::movement_heat(&b.units[defender], def_mode, def_fc);
        }
        let def_amm = crate::combat::mode_to_amm(def_mode);
        let dealt_stealth = crate::equipment_systems::void_signature_modifier(&b.units[defender], Some(def_fc), Some(def_mp_spent)) + self.mover_own;
        let no_return_fire = b.units[defender].shutdown || self.defender_cond.is_none();
        let dealt_base = match &self.mover_cond {
            None => 0,
            Some(c) => b.units[mover].gunnery + defender_tmm + b.units[mover].heat_fire_modifier + dealt_stealth + c.0,
        };
        let received_base = if no_return_fire { 0 } else { b.units[defender].gunnery + def_amm + b.units[defender].heat_fire_modifier + self.defender_own + self.defender_cond.as_ref().unwrap().0 };
        let prone_def = b.units[defender].prone;
        let d_height = los::mech_height(prone_def, is_superheavy(&b.units[defender]));
        let m_height = los::mech_height(false, is_superheavy(&b.units[mover]));
        let mover_ams_on = self.mover_ams.any();
        let defender_ams_on = self.defender_ams.any();
        let mut results: Vec<Candidate> = Vec::new();
        let mut per_hex: HashMap<String, Option<HexRow>> = HashMap::default();
        let mover_actions = self.mover_arcs.0.clone();
        let mover_legs = self.mover_arcs.1.clone();
        let defender_actions = self.defender_arcs.0.clone();
        let defender_legs = self.defender_arcs.1.clone();
        for o in prepared {
            if !per_hex.contains_key(&o.label) {
                let row = self.hex_row(b, o, def_hex, def_hex_label, def_facing, dealt_base, received_base, prone_def, defender_ams_on, no_return_fire, m_height, d_height, &defender_actions, &defender_legs);
                per_hex.insert(o.label.clone(), row);
            }
            let Some(h) = per_hex.get_mut(&o.label).unwrap().as_mut() else { continue };
            if h.by_facing[o.facing as usize].is_none() {
                let side = ar::side_by_relative_hexside((h.entry_at_atk - o.facing).rem_euclid(6));
                let (cls, keys) = self.mover_classes.of(&mover_actions, &mover_legs, &h.a_to_d, o.facing);
                let k = if mover_ams_on { self.mover_ams.engagements(b, &h.a_to_d, o.facing) } else { 0 };
                h.by_facing[o.facing as usize] = Some((side, keys, cls, k));
            }
            let (side_on_mover, keys, cls, k_mov) = h.by_facing[o.facing as usize].clone().unwrap();
            let (distance, side_on_def, k_def, wet_dealt, wet_received) = (h.distance, h.side_on_def, h.k_def, h.wet_dealt, h.wet_received);
            let mut pre_tn = 0;
            let mut dealt;
            if self.mover_cond.is_none() || wet_dealt == Wet::Blocked {
                dealt = 0.0;
            } else {
                pre_tn = clamp_tn(h.dealt_hex + o.amm);
                let mk = (cls, distance, pre_tn, o.move_heat, side_on_def, k_def, wet_dealt);
                dealt = match self.best_dealt.get(&mk) {
                    Some(v) => *v,
                    None => {
                        let mut best = f64::NEG_INFINITY;
                        for key in keys.iter() {
                            let v = self.mover_side.score(b, &self.wet_cases, key, &HashSet::default(), k_def, wet_dealt, distance, pre_tn, o.move_heat, side_on_def);
                            if v > best {
                                best = v;
                            }
                        }
                        self.best_dealt.insert(mk, best);
                        best
                    }
                };
            }
            let mut pre_tn2 = 0;
            let mut received;
            if no_return_fire || wet_received == Wet::Blocked {
                received = 0.0;
            } else {
                pre_tn2 = clamp_tn(h.received_hex + o.tmm + o.void_mod);
                let mk = (h.r_cls, distance, pre_tn2, def_move_heat, side_on_mover, k_mov, wet_received);
                received = match self.best_received.get(&mk) {
                    Some(v) => *v,
                    None => {
                        let mut best = f64::NEG_INFINITY;
                        for key in h.r_keys.iter() {
                            let v = self.defender_side.score(b, &self.wet_cases, key, &HashSet::default(), k_mov, wet_received, distance, pre_tn2, def_move_heat, side_on_mover);
                            if v > best {
                                best = v;
                            }
                        }
                        self.best_received.insert(mk, best);
                        best
                    }
                };
            }
            if distance == 1 {
                let (a_level, d_level) = (b.board.hexes[&o.label].level, b.board.hexes[def_hex_label].level);
                let (a_to_d, d_to_a, atk_mod, def_mod) = (h.a_to_d, h.d_to_a, h.atk_to_def.los.modifier, h.def_to_atk.los.modifier);
                if self.mover_physical {
                    let base = physical::base_tn(&b.units[mover], o.amm, defender_tmm, atk_mod, ar::prone_target_modifier(&b.units[defender], 1));
                    let push = self.mover_planner.push_plan(b, (o.x, o.y), o.facing, a_level, defender, def_hex_label, d_level, base, side_on_def);
                    let (allowed, t_water) = self.physical_water(b, &o.label, false, def_hex_label, prone_def, is_superheavy(&b.units[mover]), is_superheavy(&b.units[defender]));
                    let ranged = self.mover_cond.is_some() && wet_dealt != Wet::Blocked;
                    let side = &mut self.mover_side;
                    let cases = &self.wet_cases;
                    let (mh, mv) = (o.move_heat, pre_tn);
                    let mut ranged_for = |b: &mut Battle, key: &ArcKey, held: &HashSet<ItemId>| side.score(b, cases, key, held, k_def, wet_dealt, distance, mv, mh, side_on_def);
                    dealt = with_physical(b, &mut self.mover_planner, dealt, &mover_actions, &mover_legs, &a_to_d, o.facing, d_level - a_level, prone_def, base, side_on_def, if ranged { Some(&mut ranged_for) } else { None }, push, allowed, t_water);
                }
                if self.defender_physical && physical_reply {
                    let base = physical::base_tn(&b.units[defender], def_amm, o.tmm, def_mod, 0);
                    let push = self.defender_planner.push_plan(b, def_hex, def_facing, d_level, mover, &o.label, a_level, base, side_on_mover);
                    let (allowed, t_water) = self.physical_water(b, def_hex_label, prone_def, &o.label, false, is_superheavy(&b.units[defender]), is_superheavy(&b.units[mover]));
                    let ranged = !no_return_fire && wet_received != Wet::Blocked;
                    let side = &mut self.defender_side;
                    let cases = &self.wet_cases;
                    let (dh, dv) = (def_move_heat, pre_tn2);
                    let mut ranged_for = |b: &mut Battle, key: &ArcKey, held: &HashSet<ItemId>| side.score(b, cases, key, held, k_mov, wet_received, distance, dv, dh, side_on_mover);
                    received = with_physical(b, &mut self.defender_planner, received, &defender_actions, &defender_legs, &d_to_a, def_facing, a_level - d_level, false, base, side_on_mover, if ranged { Some(&mut ranged_for) } else { None }, push, allowed, t_water);
                }
            }
            results.push(Candidate { hex: o.label.clone(), facing: o.facing_compass, mode: o.mode, fc: o.fc, mp_spent: o.mp_spent, distance, dealt, received, movement_heat: o.move_heat, side_on_defender: side_on_def, side_on_mover, attack: "" });
        }
        results
    }

    /// _hex_row: what depends on the mover's hex alone; None when the hex cannot be used.
    #[allow(clippy::too_many_arguments)]
    fn hex_row(&mut self, b: &Battle, o: &Opt, def_hex: (i64, i64), def_hex_label: &str, def_facing: i64, dealt_base: i64, received_base: i64, prone_def: bool, defender_ams_on: bool, no_return_fire: bool, m_height: Height, d_height: Height, defender_actions: &[ArcAction], defender_legs: &[(String, i64)]) -> Option<HexRow> {
        let atk_hex = o.hex_xy();
        if atk_hex == def_hex {
            return None;
        }
        let atk_to_def = pair_info(b, atk_hex, def_hex, m_height, d_height)?;
        let def_to_atk = pair_info(b, def_hex, atk_hex, d_height, m_height)?;
        if !atk_to_def.los.los {
            return None;
        }
        let distance = atk_to_def.distance;
        let side_on_def = ar::side_by_relative_hexside((atk_to_def.entry_dir - def_facing).rem_euclid(6));
        let (mut wet_dealt, mut wet_received) = (Wet::Dry, Wet::Dry);
        if self.water_depths.is_some() {
            wet_dealt = self.wet(b, true, &o.label, false, def_hex_label, prone_def);
            wet_received = self.wet(b, false, def_hex_label, prone_def, &o.label, false);
        }
        let dealt_hex = dealt_base + atk_to_def.los.modifier + if prone_def { ar::prone_target_modifier(&b.units[self.defender], distance) } else { 0 };
        let received_hex = received_base + def_to_atk.los.modifier;
        let (r_cls, r_keys) = if no_return_fire { (0, Rc::new(vec![])) } else { self.defender_classes.of(defender_actions, defender_legs, &def_to_atk.arcs, def_facing) };
        let k_def = if defender_ams_on { self.defender_ams.engagements(b, &def_to_atk.arcs, def_facing) } else { 0 };
        Some(HexRow {
            a_to_d: atk_to_def.arcs,
            d_to_a: def_to_atk.arcs,
            entry_at_atk: def_to_atk.entry_dir,
            atk_to_def,
            def_to_atk,
            distance,
            side_on_def,
            dealt_hex,
            received_hex,
            r_keys,
            r_cls,
            k_def,
            wet_dealt,
            wet_received,
            by_facing: Default::default(),
        })
    }
}

/// _with_physical: best expected damage from a spot next to the enemy counting the Physical phase too.
#[allow(clippy::too_many_arguments)]
pub fn with_physical(b: &mut Battle, planner: &mut PhysPlanner, ranged_best: f64, actions: &[ArcAction], legs: &[(String, i64)], pair_arcs: &[i64; 6], facing: i64, diff: i64, target_prone: bool, base: i64, side: &str, mut ranged_for: Option<&mut dyn FnMut(&mut Battle, &ArcKey, &HashSet<ItemId>) -> f64>, push: Option<(f64, PhysOption)>, allowed: Option<Vec<&'static str>>, t_water: Option<&'static str>) -> f64 {
    let mut best = ranged_best;
    if !physical::reachable(diff, planner.target_superheavy) {
        return best;
    }
    let push = if allowed.as_ref().is_some_and(|a| !a.contains(&"push")) { None } else { push };
    for (key, reach) in planner.cases(b, pair_arcs, facing, actions, legs) {
        let plans = planner.plans_in_case(b, reach, diff, target_prone, base, side, &allowed, t_water);
        for plan in plans {
            if plan.limbs.is_empty() || plan.value <= 0.0 {
                continue;
            }
            if plan.value + ranged_best <= best {
                break; // plans are best first; ranged can't beat ranged_best
            }
            let total = match ranged_for.as_deref_mut() {
                None => plan.value,
                Some(f) => {
                    let held = planner.held(b, &plan.limbs);
                    f(b, &key, &held) + plan.value
                }
            };
            if total > best {
                best = total;
            }
        }
    }
    if let Some((value, o)) = push {
        let limbs: Vec<String> = physical::ARMS.iter().map(|s| s.to_string()).collect();
        let _ = o;
        let total = match ranged_for.as_deref_mut() {
            None => value,
            Some(f) => {
                let held = planner.held(b, &limbs);
                f(b, &arcs::key_for(pair_arcs, facing, &actions[0], legs), &held) + value
            }
        };
        if total > best {
            best = total;
        }
    }
    best
}

/// A state's pick dict is in move_options::Opt::pick; the reach signature type is re-exported for the callers.
pub type ReachSig = Reach;
