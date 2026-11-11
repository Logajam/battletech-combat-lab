// Gladiator's choices (INTEGRATION__bots -> attack_resolution.choose_declaration, physical.choose_attack ...), computed.
// Each is checked against the recorded decision (decisions.json) in tests/stage8_*.rs.
use crate::fasthash::{HashMap, HashSet};

use crate::arcs;
use crate::attack_resolution::{arc_unavailable, DeclChoice, DeclCtx};
use crate::battle::{Battle, UnitId};
use crate::equipment::ItemId;
use crate::fire_modes::Planner;
use crate::hex_geometry;
use crate::mech_state::*;
use crate::physical::{self, Plan};
use crate::weapon_selection::select_weapons_to_fire;

/// attack_resolution._physical_planner: the physical attacks that can follow the ranged fire, for an adjacent target
/// (nothing fired yet). None if the attacker can't make one (prone, immobile).
pub struct PhysPlans {
    base: i64,
    a_hex: (i64, i64),
    a_facing: i64,
    a_level: i64,
    t_hex: (i64, i64),
    t_level: i64,
    allowed: Option<Vec<&'static str>>,
    t_water: &'static str,
    push: Vec<Plan>,
}

pub fn physical_planner(b: &mut Battle, attacker: UnitId, target: UnitId) -> Option<PhysPlans> {
    if b.units[attacker].prone || is_immobile(&b.units[attacker]) {
        return None;
    }
    let base = physical::base_tn_for(b, attacker, target);
    let (ah, th) = (b.units[attacker].hex.clone().unwrap(), b.units[target].hex.clone().unwrap());
    let a_hex = hex_geometry::parse_hex_label(&ah).unwrap();
    let t_hex = hex_geometry::parse_hex_label(&th).unwrap();
    let a_facing = hex_geometry::compass_to_facing(&b.units[attacker].facing).unwrap();
    let (a_level, t_level) = (b.board.hexes[&ah].level, b.board.hexes[&th].level);
    let t_water = crate::water::state(b, target);
    let allowed = crate::water::physical_allowed(crate::water::state(b, attacker), t_water);
    let mut value = |b: &mut Battle, label: &str, direction: i64| crate::movement_attacks::displacement_worth(b, target, label, direction).f();
    let fired: HashSet<ItemId> = HashSet::default();
    let mut push: Vec<Plan> = Vec::new();
    if let Some(mut o) = physical::push_option(b, attacker, a_hex, a_facing, a_level, target, &th, t_level, &fired, &mut value) {
        o.damage = crate::movement_attacks::displacement_worth(b, target, &th, a_facing);
        let v = physical::expected_damage_of(b, base, std::slice::from_ref(&o), None, "front");
        if v > 0.0 {
            push = vec![Plan { value: v, limbs: physical::ARMS.iter().map(|s| s.to_string()).collect(), picks: vec![o] }];
        }
    }
    if let Some(al) = &allowed {
        if !al.contains(&"push") {
            push = vec![];
        }
    }
    Some(PhysPlans { base, a_hex, a_facing, a_level, t_hex, t_level, allowed, t_water, push })
}

impl PhysPlans {
    /// plans_for(action): [(value, limbs, picks)] best first (never empty).
    pub fn plans_for(&self, b: &mut Battle, attacker: UnitId, target: UnitId, action: &ArcAction) -> Vec<Plan> {
        let diff = self.t_level - self.a_level;
        let sup = is_superheavy(&b.units[target]);
        let mut got: Vec<Plan> = Vec::new();
        if physical::reachable(diff, sup) && crate::los::hex_distance(self.a_hex, self.t_hex) == 1 {
            let pair = arcs::arcs_between(self.a_hex, self.t_hex);
            let rel = physical::Reach::new(&b.units[attacker], self.a_facing, action, &pair);
            let none: HashSet<ItemId> = HashSet::default();
            let mut options = physical::options(b, attacker, &rel, diff, b.units[target].prone, &none, sup);
            options = physical::water_filter(options, self.allowed.as_deref());
            if self.t_water != crate::water::GROUND {
                let quad = b.units[target].mech_type == "quad" || b.units[target].mech_type == "quadvee";
                for (_, opts) in options.iter_mut() {
                    for o in opts.iter_mut() {
                        o.damage = crate::pyfmt::Num::F(o.damage.f() * crate::water::physical_value_factor_q(quad, self.t_water, &o.table, "front"));
                    }
                }
            }
            got = physical::plans(b, &options, self.base, None, "front");
        }
        if got.is_empty() {
            got = vec![Plan { value: 0.0, limbs: vec![], picks: vec![] }];
        }
        if !self.push.is_empty() && !action.flip {
            got.extend(self.push.iter().cloned());
        }
        got
    }
}

/// attack_resolution.choose_declaration for Gladiator: the (twist / flip / turret, weapons, physical attack) with the most
/// expected damage; no change wins ties.
pub fn choose_declaration(b: &mut Battle, ctx: &DeclCtx, planner: &mut Planner, attacker: UnitId, target: UnitId) -> DeclChoice {
    choose_declaration_with(b, ctx, planner, attacker, target, true)
}

/// The same choice with Princess's fire control picking the weapons (bots.fire_control / princess_eyes): her plan's
/// utility stands in for expected damage, and the physical attack is not planned together with the fire (she throws it in
/// the Physical phase).
pub fn choose_declaration_princess(b: &mut Battle, ctx: &DeclCtx, planner: &mut Planner, attacker: UnitId, target: UnitId) -> DeclChoice {
    b.fire_ctl = Some(crate::princess_fire::FireControl::new(false, None));
    let r = choose_declaration_with(b, ctx, planner, attacker, target, false);
    b.fire_ctl = None;
    r
}

fn choose_declaration_with(b: &mut Battle, ctx: &DeclCtx, planner: &mut Planner, attacker: UnitId, target: UnitId, plans_physical: bool) -> DeclChoice {
    let plans_for = if ctx.distance == 1 && plans_physical { physical_planner(b, attacker, target) } else { None };
    let actions: Vec<ArcAction> = if plans_for.is_some() { arcs::arc_options(&b.units[attacker], "ranged") } else { ctx.arc_choices.iter().map(|(_, a)| a.clone()).collect() };
    let legs = arcs::leg_offsets(&b.units[attacker]);
    let mut cache: HashMap<(arcs::ArcKey, Vec<ItemId>), (Vec<ItemId>, f64, i64)> = HashMap::default();
    let mut best: Option<(f64, (Vec<ItemId>, f64, i64), arcs::ArcKey, ArcAction, Plan, Vec<ItemId>)> = None;
    for action in actions {
        let key = arcs::key_for(&ctx.pair_arcs, ctx.a_facing, &action, &legs);
        let plans: Vec<Plan> = match &plans_for {
            Some(p) => p.plans_for(b, attacker, target, &action),
            None => vec![Plan { value: 0.0, limbs: vec![], picks: vec![] }],
        };
        for plan in plans {
            let mut held: Vec<ItemId> = if plan.limbs.is_empty() { vec![] } else { physical::limb_weapon_ids(&b.units[attacker], &plan.limbs).into_iter().collect() };
            held.sort();
            let ck = (key.clone(), held.clone());
            let picked = match cache.get(&ck) {
                Some(p) => p.clone(),
                None => {
                    let mut unavail = ctx.unavailable.clone();
                    unavail.extend(arc_unavailable(&b.units[attacker], &key));
                    unavail.extend(held.iter().copied());
                    let p = crate::weapon_selection::select_weapons_scaled(b, attacker, ctx.distance, ctx.sel_pre_tn, b.units[attacker].min_heat, b.units[attacker].max_heat, ctx.dissipation, b.units[attacker].movement_heat, ctx.other, Some(&ctx.adjust), &unavail, None, Some(planner), Some(&ctx.side));
                    cache.insert(ck, p.clone());
                    p
                }
            };
            let total = picked.1 + plan.value;
            if best.as_ref().map_or(true, |x| total > x.0 + 1e-12) {
                best = Some((total, picked, key.clone(), action.clone(), plan, held));
            }
        }
    }
    let (_, (weapons, exp, heat), key, action, plan, held) = best.unwrap();
    DeclChoice {
        weapons,
        exp_dmg: exp,
        weapon_heat: heat,
        key_torso_arc: key.torso_arc,
        action,
        phys_names: plan.picks.iter().map(|o| o.name.clone()).collect(),
        phys_value: plan.value,
        held: held.into_iter().collect(),
    }
}
