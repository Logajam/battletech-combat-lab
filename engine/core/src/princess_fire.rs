// Translated from INTEGRATION__princess_fire.py: MegaMek's Princess fire control (firing-plan utility) and the damage map
// her friends have already declared. Handed to weapon_selection through `Battle::fire_ctl` (the `_FIRE_CONTROL` hook).
use crate::fasthash::{HashMap, HashSet};

use crate::battle::{Battle, UnitId};
use crate::damage_resolution::get_weapons;
use crate::equipment::ItemId;
use crate::mech_state::*;

pub const FALL_SHAME_VALUES: [f64; 11] = [10.0, 40.0, 80.0, 100.0, 160.0, 500.0, 500.0, 500.0, 500.0, 500.0, 500.0];
pub const SELF_PRESERVATION_VALUES: [f64; 11] = [2.5, 5.0, 7.5, 10.0, 12.5, 15.0, 17.5, 20.0, 22.5, 25.0, 30.0];
pub const BRAVERY_VALUES: [f64; 11] = [0.1, 0.3, 0.6, 0.9, 1.2, 1.5, 1.8, 2.1, 2.4, 2.7, 3.0];
pub const HYPER_AGGRESSION_VALUES: [f64; 11] = [0.25, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 10.0, 50.0, 500.0];

/// A slider's value from config.PRINCESS_BEHAVIOR (its index 0-10).
pub fn setting(b: &Battle, name: &str) -> f64 {
    let table = match name {
        "fall_shame" => &FALL_SHAME_VALUES,
        "bravery" => &BRAVERY_VALUES,
        "hyper_aggression" => &HYPER_AGGRESSION_VALUES,
        "self_preservation" => &SELF_PRESERVATION_VALUES,
        _ => panic!("slider {}", name),
    };
    let i = b.cfg.get("PRINCESS_BEHAVIOR")[name].as_i64().unwrap_or(5).clamp(0, 10);
    table[i as usize]
}

const DAMAGE_UTILITY: f64 = 1.0;
const CRITICAL_UTILITY: f64 = 10.0;
const KILL_UTILITY: f64 = 50.0;
const OVERHEAT_DISUTILITY: f64 = 5.0;
const TARGET_HP_FRACTION_DEALT_UTILITY: f64 = -30.0;
const TARGET_POTENTIAL_DAMAGE_UTILITY: f64 = 1.0;
const HEAT_TOLERANCE_BONUS: i64 = 5;
const ROLL_TWO: f64 = 0.028;
const EXPECTED_CRITICAL_HIT_COUNT: f64 = 0.611;
pub const ALREADY_DESTROYED_OVERKILL: f64 = 100.0;

const MEK_LOCATIONS: [&str; 8] = ["Head", "Center Torso", "Right Torso", "Left Torso", "Right Arm", "Left Arm", "Right Leg", "Left Leg"];

fn hit_odds(side: &str) -> [f64; 8] {
    let t: [f64; 8] = match side {
        "right" => [1.0, 5.0, 7.0, 4.0, 7.0, 3.0, 7.0, 3.0],
        "left" => [1.0, 5.0, 4.0, 7.0, 3.0, 7.0, 3.0, 7.0],
        _ => [1.0, 7.0, 5.0, 5.0, 5.0, 5.0, 4.0, 4.0],
    };
    let mut out = [0.0; 8];
    for i in 0..8 {
        out[i] = t[i] / 36.0;
    }
    out
}

fn location_name(m: &Mech, loc: &str) -> String {
    if m.mech_type == "quad" || m.mech_type == "quadvee" {
        match loc {
            "Right Arm" => return "Front Right Leg".into(),
            "Left Arm" => return "Front Left Leg".into(),
            "Right Leg" => return "Rear Right Leg".into(),
            "Left Leg" => return "Rear Left Leg".into(),
            _ => {}
        }
    }
    loc.to_string()
}

fn armor_of(m: &Mech, loc: &str, rear: bool) -> f64 {
    let e = &m.locations[loc];
    let v = if rear { e.rear_armor.unwrap_or(e.armor).f() } else { e.armor.f() };
    v.max(0.0)
}

/// Princess.damageMap, per team: the expected damage declared at each enemy this Ranged Attack Phase.
#[derive(Default)]
pub struct PrincessState {
    pub assigned: HashMap<(String, UnitId), f64>,
    /// bots.fire_pick's firepower cache for the phase
    pub guns: HashMap<UnitId, f64>,
    /// princess_memory: one TeamMemory per team, and the BV of each unit (as built, cached)
    pub teams: crate::fasthash::IndexMap<String, crate::princess_memory::TeamMemory>,
    pub bv: HashMap<UnitId, i64>,
}

pub fn reset_assigned(b: &mut Battle) {
    b.princess.assigned.clear();
}

pub fn assigned_damage(b: &Battle, team: &str, target: UnitId) -> f64 {
    b.princess.assigned.get(&(team.to_string(), target)).copied().unwrap_or(0.0)
}

pub fn assign_damage(b: &mut Battle, team: &str, target: UnitId, damage: f64) {
    let cur = assigned_damage(b, team, target);
    b.princess.assigned.insert((team.to_string(), target), cur + damage);
}

pub fn overkill_fraction(existing: f64, expected: f64, hp: f64) -> f64 {
    if existing / hp >= 1.0 {
        return ALREADY_DESTROYED_OVERKILL;
    }
    let fraction = (existing + expected) / hp;
    if fraction >= 0.5 { fraction } else { 0.0 }
}

/// FireControl.getMaxDamageAtRange: the summed damage of every weapon in range at `distance`, no to-hit.
pub fn max_damage_at_range(b: &mut Battle, u: UnitId, distance: i64) -> i64 {
    let mut crippled: HashSet<ItemId> = crate::ammo::unavailable_weapons(&b.units[u]);
    crippled.extend(crate::fire_modes::jammed_ids(&b.units[u]));
    let mut total = 0;
    for w in get_weapons(&b.units[u]) {
        if crate::weapon_rules::is_ams(b, u, w) {
            continue;
        }
        let Some(r) = b.units[u].items[w].weapon_range.clone() else { continue };
        if crippled.contains(&w) || distance > r.long {
            continue;
        }
        let damage = if crate::weapon_rules::is_cluster(b, u, w) { b.units[u].items[w].rack_size.unwrap_or(0) } else { b.units[u].items[w].damage_per_shot.unwrap_or(0) };
        if damage > 0 {
            total += damage;
        }
    }
    total
}

/// Compute.getTargetTotalHP for a 'Mech: armor (front and rear) + structure.
pub fn total_hp(m: &Mech) -> f64 {
    let mut sum = 0.0;
    for e in m.locations.values() {
        if e.destroyed {
            continue;
        }
        sum += e.armor.f().max(0.0) + e.rear_armor.map_or(0.0, |r| r.f()).max(0.0) + e.structure.f().max(0.0);
    }
    sum
}

/// (expected criticals, kill chance) of one weapon with P(hit) p_hit against target from `side` - WeaponFireInfo.initDamage.
pub fn weapon_crits_and_kill(target: &Mech, side: &str, p_hit: f64, expected: f64, on_hit: Option<f64>, odds: Option<[f64; 8]>) -> (f64, f64) {
    let mut crits = ROLL_TWO * EXPECTED_CRITICAL_HIT_COUNT * p_hit;
    let mut kill = 0.0;
    let odds = odds.unwrap_or_else(|| hit_odds(if side.is_empty() { "front" } else { side }));
    let rear = side == "rear";
    for (i, base) in MEK_LOCATIONS.iter().enumerate() {
        let mut loc = location_name(target, base);
        if !target.locations.contains_key(&loc) {
            continue;
        }
        let mut skip = false;
        while target.locations[&loc].destroyed && loc != "Center Torso" {
            if loc == "Head" {
                skip = true;
                break;
            }
            match crate::damage_resolution::transfer_map(&loc) {
                Some(n) => loc = n.to_string(),
                None => {
                    skip = true;
                    break;
                }
            }
        }
        if skip {
            continue;
        }
        let p_loc = odds[i];
        if p_loc == 0.0 {
            continue;
        }
        let armor = armor_of(target, &loc, rear);
        let structure = target.locations[&loc].structure.f().max(0.0);
        let destroyed = match on_hit {
            Some(h) => h >= armor + structure,
            None => expected > armor + structure,
        };
        if destroyed {
            crits += p_loc * p_hit;
            if loc == "Center Torso" || (loc == "Head" && !has_torso_cockpit(target)) {
                kill += p_loc * p_hit;
            }
        } else if on_hit.unwrap_or(expected) > armor {
            crits += p_loc * p_hit * EXPECTED_CRITICAL_HIT_COUNT;
        }
    }
    (crits, kill)
}

const TSM_DESIRED_HEAT: i64 = 9;
const TSM_HEAT_CEILING: i64 = 13;
const TSM_ACTIVATION_UTILITY: f64 = 20.0;

pub fn heat_tolerance(b: &Battle, u: UnitId, dissipation: i64, unavoidable: i64) -> i64 {
    let mut tolerance = dissipation - unavoidable + HEAT_TOLERANCE_BONUS;
    if b.units[u].has_tsm {
        tolerance = tolerance.max(dissipation - unavoidable + TSM_HEAT_CEILING);
    }
    tolerance
}

fn tsm_heat_bonus(m: &Mech, dissipation: i64, unavoidable: i64, weapon_heat: i64) -> f64 {
    if !m.has_tsm || weapon_heat <= 0 {
        return 0.0;
    }
    let projected = (unavoidable + weapon_heat - dissipation).max(0);
    if projected <= 0 {
        return 0.0;
    }
    if projected < TSM_DESIRED_HEAT {
        return TSM_ACTIVATION_UTILITY * projected as f64 / TSM_DESIRED_HEAT as f64;
    }
    let band = (TSM_HEAT_CEILING - TSM_DESIRED_HEAT).max(1);
    TSM_ACTIVATION_UTILITY * (0.0f64).max(1.0 - (projected - TSM_DESIRED_HEAT) as f64 / band as f64)
}

/// Princess's firing-plan choice. guess=true: the movement ranker's estimate (alpha strike when within the heat limit);
/// false: the real attack (best plan by utility). One object per decision - it caches each target's multiplier and HP.
pub struct FireControl {
    pub guess: bool,
    pub self_mech: Option<UnitId>,
    target: HashMap<UnitId, (f64, f64)>,
    pub last: Option<(f64, f64)>,
}

type Plan = (HashSet<ItemId>, f64, f64, f64, i64);

impl FireControl {
    pub fn new(guess: bool, self_mech: Option<UnitId>) -> FireControl {
        FireControl { guess, self_mech, target: HashMap::default(), last: None }
    }

    fn target_terms(&mut self, b: &mut Battle, target: UnitId) -> (f64, f64) {
        if let Some(t) = self.target.get(&target) {
            return *t;
        }
        let potential = max_damage_at_range(b, target, 1);
        let scale = SELF_PRESERVATION_VALUES[10] / setting(b, "self_preservation");
        let mult = if potential == 0 { 1.0 } else { (TARGET_POTENTIAL_DAMAGE_UTILITY * scale * potential as f64 + 10.0).log10() };
        let got = (mult, total_hp(&b.units[target]).max(1.0));
        self.target.insert(target, got);
        got
    }

    /// (utility tolerance, alpha-strike heat limit, unavoidable heat).
    fn limits(&self, b: &Battle, mech: UnitId, dissipation: i64, other_heat: i64, movement_heat: i64) -> (i64, i64, i64) {
        let cur = b.units[mech].current_heat;
        if !self.guess {
            let unavoidable = cur + movement_heat + other_heat;
            let tolerance = heat_tolerance(b, mech, dissipation, unavoidable);
            return (tolerance, tolerance, unavoidable);
        }
        if Some(mech) == self.self_mech {
            let tolerance = heat_tolerance(b, mech, dissipation, cur + other_heat);
            let limit = heat_tolerance(b, mech, dissipation, cur + other_heat + movement_heat);
            return (tolerance, limit, cur + other_heat + movement_heat);
        }
        let unavoidable = cur + movement_heat + other_heat;
        (heat_tolerance(b, mech, dissipation, unavoidable), dissipation - cur + HEAT_TOLERANCE_BONUS, unavoidable)
    }

    /// The choice from candidates (weapon, expected damage, heat, to-hit number) -> (weapons, utility, heat).
    #[allow(clippy::too_many_arguments)]
    pub fn choose(&mut self, b: &mut Battle, mech: UnitId, candidates: &[(ItemId, f64, i64, i64)], dissipation: i64, other_heat: i64, target: Option<UnitId>, side: &str, movement_heat: i64) -> (Vec<ItemId>, f64, i64) {
        let (tolerance, limit, unavoidable) = self.limits(b, mech, dissipation, other_heat, movement_heat);
        let (mult, hp) = match target {
            Some(t) => self.target_terms(b, t),
            None => (1.0, 1.0),
        };
        let existing = if self.guess || target.is_none() { 0.0 } else { assigned_damage(b, b.units[mech].team.as_deref().unwrap_or(""), target.unwrap()) };
        let mut infos: Vec<(ItemId, f64, i64, f64, f64)> = Vec::new();
        // AMMO CONSERVATION (N3; MegaMek Princess.calcAmmoConservation, applied in getFullFiringPlan - the plan she
        // declares, not the guesses she prices moves with): a weapon fires only above its to-hit threshold
        let conserve = !self.guess && b.units[mech].is_princess_family();
        for &(w, expected, heat, tn) in candidates {
            let p = if tn <= 12 { crate::combat::hit_probability(tn) } else { 0.0 };
            let threshold = if conserve { ammo_conservation(b, mech, w) } else { 0.0 };
            if p <= threshold || expected <= 0.0 {
                continue;
            }
            let (crits, kill) = match target {
                None => (0.0, 0.0),
                Some(t) => weapon_crits_and_kill(&b.units[t], side, p, expected, Some(expected / p), None),
            };
            infos.push((w, expected, heat, crits, kill));
        }
        let utility = |plan: &Plan| -> f64 {
            let (_, ed, crits, survive, heat) = plan;
            let mut u = (DAMAGE_UTILITY * ed + CRITICAL_UTILITY * crits + KILL_UTILITY * (1.0 - survive)) * mult;
            u += TARGET_HP_FRACTION_DEALT_UTILITY * overkill_fraction(existing, *ed, hp);
            u - OVERHEAT_DISUTILITY * ((*heat - tolerance).max(0)) as f64
        };
        let add = |plan: &Plan, info: &(ItemId, f64, i64, f64, f64)| -> Plan {
            let mut ids = plan.0.clone();
            ids.insert(info.0);
            (ids, plan.1 + info.1, plan.2 + info.3, plan.3 * (1.0 - info.4), plan.4 + info.2)
        };
        let empty: Plan = (HashSet::default(), 0.0, 0.0, 1.0, 0);
        let mut alpha = empty.clone();
        for info in &infos {
            alpha = add(&alpha, info);
        }
        if self.guess && alpha.4 <= limit {
            let u = utility(&alpha);
            return self.result(b, mech, &alpha, u);
        }
        let mut plans: Vec<Plan> = vec![empty.clone()];
        for info in &infos {
            if info.2 == 0 {
                plans[0] = add(&plans[0], info);
            }
        }
        let nonzero: Vec<&(ItemId, f64, i64, f64, f64)> = infos.iter().filter(|i| i.2 != 0).collect();
        for level in 1..=alpha.4.max(0) {
            let mut best = plans[(level - 1) as usize].clone();
            let mut best_u = utility(&best);
            for info in &nonzero {
                let left = level - info.2;
                if left >= 0 && !plans[left as usize].0.contains(&info.0) {
                    let test = add(&plans[left as usize], info);
                    let u = utility(&test);
                    if u > best_u {
                        best = test;
                        best_u = u;
                    }
                }
            }
            plans.push(best);
        }
        let tsm = !self.guess;
        let bonus = |plan: &Plan, m: &Mech| -> f64 { if tsm { tsm_heat_bonus(m, dissipation, unavoidable, plan.4) } else { 0.0 } };
        let mut chosen = empty.clone();
        let mut chosen_u = bonus(&empty, &b.units[mech]);
        for plan in &plans {
            let u = utility(plan) + bonus(plan, &b.units[mech]);
            if u > chosen_u {
                chosen = plan.clone();
                chosen_u = u;
            }
        }
        self.result(b, mech, &chosen, chosen_u)
    }

    fn result(&mut self, b: &Battle, mech: UnitId, plan: &Plan, u: f64) -> (Vec<ItemId>, f64, i64) {
        self.last = Some((plan.1, u));
        (get_weapons(&b.units[mech]).into_iter().filter(|w| plan.0.contains(w)).collect(), u, plan.4)
    }
}

// =============================================================================================================
// PHYSICAL ATTACKS (PhysicalCalculator.getBestPhysicalAttack)
// =============================================================================================================
fn armor_named(m: &Mech, name: &str, rear: bool) -> f64 {
    let loc = location_name(m, name);
    if m.locations.contains_key(&loc) { armor_of(m, &loc, rear) } else { 0.0 }
}

/// PhysicalCalculator.punchThroughMod: 1 + a bonus for every location in the arc whose armor `damage`, taken in hits of
/// `group`, would get through - halved for each further pass.
pub fn punch_through_mod(target: &Mech, table: &str, side: &str, damage: f64, group: f64) -> f64 {
    if damage <= 0.0 || group <= 0.0 {
        return 1.0;
    }
    let a = |n: &str, rear: bool| armor_named(target, n, rear);
    let rear = side != "front";
    let values: Vec<f64> = match table {
        "standard" => vec![a("Head", false), a("Center Torso", rear), a("Right Torso", rear), a("Left Torso", rear), a("Right Arm", false), a("Left Arm", false), a("Right Leg", false), a("Right Leg", false)],
        "punch" => match side {
            "right" => vec![a("Head", false), a("Center Torso", false), a("Right Torso", false), a("Right Arm", false)],
            "left" => vec![a("Head", false), a("Center Torso", false), a("Left Torso", false), a("Left Arm", false)],
            _ => {
                let r = side == "rear";
                vec![a("Head", false), a("Center Torso", r), a("Right Torso", r), a("Left Torso", r), a("Right Arm", false), a("Left Arm", false)]
            }
        },
        _ => {
            let mut v = vec![];
            if matches!(side, "front" | "rear" | "right") {
                v.push(a("Right Leg", false));
            }
            if matches!(side, "front" | "rear" | "left") {
                v.push(a("Left Leg", false));
            }
            v
        }
    };
    let (mut multiplier, mut base, mut hit_total) = (1.0, 0.5, 0.0);
    while hit_total <= damage {
        hit_total += group;
        multiplier += base * values.iter().filter(|v| hit_total > **v).count() as f64;
        base /= 2.0;
    }
    multiplier
}

/// PhysicalCalculator.calculateFallingDamage: p x P(failing its piloting roll) x a tenth of its tonnage.
pub fn falling_damage(p: f64, m: &Mech) -> f64 {
    let tn = m.piloting + crate::piloting_rolls::preexisting_modifier(m);
    p * (1.0 - crate::combat::hit_probability(tn)) * m.mass.unwrap_or(0) as f64 * 0.1
}

fn mobility(m: &Mech, floor: f64) -> f64 {
    let walk = compute_walk_mp(m);
    let jump = compute_jump_mp(m);
    if walk > 0 { (1.0 / walk as f64 + jump as f64).sqrt() } else { floor.max((jump as f64).sqrt()) }
}

fn push_worth(b: &Battle, attacker: UnitId, target: UnitId, p: f64) -> f64 {
    let a_xy = crate::hex_geometry::parse_hex_label(b.units[attacker].hex.as_deref().unwrap()).unwrap();
    let t_xy = crate::hex_geometry::parse_hex_label(b.units[target].hex.as_deref().unwrap()).unwrap();
    let (dx, dy) = crate::hex_geometry::FACING_DELTAS[crate::combat::direction_facing(a_xy, t_xy).unwrap() as usize];
    let label = crate::hex_geometry::hex_label(t_xy.0 + dx, t_xy.1 + dy).ok();
    let t = &b.units[target];
    let hexes = &b.board.hexes;
    let Some(label) = label.filter(|l| hexes.contains_key(l)) else {
        return t.locations.values().map(|e| e.armor.f().max(0.0) + e.rear_armor.map_or(0.0, |r| r.f()).max(0.0)).sum::<f64>() * p;
    };
    let drop = (hexes[t.hex.as_deref().unwrap()].level - hexes[&label].level).max(0);
    let dmg = falling_damage(p, t) * (1.0 + drop as f64);
    let mut breach = punch_through_mod(t, "standard", "front", dmg, dmg.min(5.0));
    if breach > 1.0 && crate::water::depth_at(&b.board, Some(&label)) >= 1 {
        breach *= 2.0;
    }
    dmg * mobility(t, 1.0) * breach
}

/// getBestPhysicalAttack: (base TN, [options], arc action) of the attack with the most expected worth, or None.
pub fn choose_physical(b: &mut Battle, attacker: UnitId, target: UnitId) -> Option<(i64, Vec<crate::physical::PhysOption>, ArcAction)> {
    if b.is_destroyed(attacker) || b.is_destroyed(target) || b.units[attacker].hex == b.units[target].hex {
        return None;
    }
    let options = crate::physical::attack_options(b, attacker, target, None);
    if options.is_empty() {
        return None;
    }
    let base = crate::physical::base_tn_for(b, attacker, target);
    let a_xy = crate::hex_geometry::parse_hex_label(b.units[attacker].hex.as_deref().unwrap()).unwrap();
    let t_xy = crate::hex_geometry::parse_hex_label(b.units[target].hex.as_deref().unwrap()).unwrap();
    let h = crate::attack_resolution::standing();
    let side = crate::attack_resolution::attack_side(b, a_xy, t_xy, crate::hex_geometry::compass_to_facing(&b.units[target].facing).unwrap(), h, h);
    let p = |o: &crate::physical::PhysOption| crate::combat::hit_probability(base + o.mod_);
    let t = &b.units[target];
    let at = &b.units[attacker];
    let mut scored: Vec<(f64, Vec<crate::physical::PhysOption>)> = Vec::new();
    let punches = options.get("punch").cloned().unwrap_or_default();
    for o in &punches {
        let d = p(o) * o.damage.f();
        scored.push((d * punch_through_mod(t, &o.table, side, d, d), vec![o.clone()]));
    }
    if punches.len() == 2 {
        let d: f64 = crate::pyfmt::py_sum(punches.iter().map(|o| p(o) * o.damage.f()));
        scored.push((d * punch_through_mod(t, &punches[0].table, side, d, d / 2.0), punches.clone()));
    }
    for o in options.get("kick").cloned().unwrap_or_default() {
        let mut d = p(&o) * o.damage.f();
        d *= punch_through_mod(t, &o.table, side, d, d);
        let target_falls = falling_damage(p(&o), t);
        let self_falls = falling_damage(1.0 - p(&o), at) * mobility(at, 0.0);
        scored.push((d + target_falls - self_falls, vec![o]));
    }
    for kind in ["club", "weapon"] {
        for o in options.get(kind).cloned().unwrap_or_default() {
            let d = p(&o) * o.damage.f();
            scored.push((d * punch_through_mod(t, &o.table, side, d, d), vec![o]));
        }
    }
    for o in options.get("push").cloned().unwrap_or_default() {
        scored.push((push_worth(b, attacker, target, p(&o)), vec![o]));
    }
    let mut best: Option<(f64, Vec<crate::physical::PhysOption>)> = None;
    for (worth, picks) in scored {
        if worth > 0.0 && best.as_ref().map_or(true, |x| worth > x.0) {
            best = Some((worth, picks));
        }
    }
    let (_, picks) = best?;
    Some((base, picks, crate::arcs::current_action(&b.units[attacker])))
}

/// MegaMek Princess.calcAmmoConservation (main 3f9f2fd; backlog N3, Daniel 2026-11-20: "Need AMS on/off and ammo
/// conservation for princess"): the chance to hit a weapon must BEAT to be fired. A weapon without ammunition: 0.01 (any
/// roll of 12 or less). A one-shot weapon: (35 - 2 x hyper aggression) / 100 (fires on a 10 / 9 / 8 at aggression
/// 10 / 5 / 0). Otherwise, with n = the shots left in its bins shared out over the launchers drawing on them (rounded
/// up): max(0.01, 0.6 / (8a + 4) + 4 / (4 n^2 (a + 2) + 4 / (a + 1))), a = the hyper aggression slider (0-10). MegaMek's
/// own notes: with 7 / 3 / 1 rounds left it fires on 10, 9, 7 at aggression 0; 12, 11, 10 at 5; 12, 12, 10 at 10.
pub fn ammo_conservation(b: &Battle, mech: UnitId, w: ItemId) -> f64 {
    let m = &b.units[mech];
    let aggro = b.cfg.get("PRINCESS_BEHAVIOR")["hyper_aggression"].as_i64().unwrap_or(5).clamp(0, 10) as f64;
    let it = &m.items[w];
    if it.one_shot.unwrap_or(false) {
        return (35.0 - 2.0 * aggro) / 100.0;
    }
    if !it.needs_ammo.unwrap_or(false) {
        return 0.01;
    }
    let bins = crate::ammo::bins_for(m, w);
    if bins.iter().any(|i| m.items[*i].shots_left.is_none()) {
        return 0.01; // unknown shots: treated as plenty
    }
    let pooled: i64 = bins.iter().map(|i| m.items[*i].shots_left.unwrap_or(0)).sum();
    let sharing = crate::damage_resolution::get_weapons(m)
        .into_iter()
        .filter(|o| m.items[*o].needs_ammo.unwrap_or(false) && !m.items[*o].one_shot.unwrap_or(false) && m.items[*o].ammo_key.is_some() && m.items[*o].ammo_key == it.ammo_key)
        .count()
        .max(1) as i64;
    let n = ((pooled + sharing - 1) / sharing) as f64;
    (0.6 / (8.0 * aggro + 4.0) + 4.0 / (4.0 * n * n * (aggro + 2.0) + 4.0 / (aggro + 1.0))).max(0.01)
}
