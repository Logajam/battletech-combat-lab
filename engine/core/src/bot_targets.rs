// Translated from INTEGRATION__bots.choose_target and INTEGRATION__princess_group.choose_target / candidates: whom a
// unit fires at. Princess takes the enemy whose firing plan has the highest utility (friends' declared damage counted);
// a Gladiator with two or more enemies borrows that choice (config.STUB_GLADIATOR_TARGET "princess_plan").
use crate::attack_resolution::{plan_damage, prepare_declaration, Prep};
use crate::battle::{Battle, UnitId};
use crate::fire_modes::Planner;

/// The enemies on the board, in roster order.
pub fn candidates(b: &mut Battle, attacker: UnitId) -> Vec<UnitId> {
    crate::forces::enemies_of(b, attacker).into_iter().filter(|e| crate::forces::distance(b, attacker, *e).is_some()).collect()
}

/// declare_attacks(dry=True) with Princess's fire control: (the choice's value, expected damage, the side of the target
/// it lands on), or None when nothing can fire at it. Changes nothing and logs nothing.
pub fn dry_declare(b: &mut Battle, attacker: UnitId, target: UnitId) -> Option<(f64, f64, String)> {
    dry_declare_as(b, attacker, target, true)
}

/// `princess`: Princess's fire control chooses (princess_eyes); else the unit's own bot (Gladiator's knapsack).
pub fn dry_declare_as(b: &mut Battle, attacker: UnitId, target: UnitId, princess: bool) -> Option<(f64, f64, String)> {
    b.log.quiet += 1;
    let r = (|| {
        let Prep::Ready(ctx) = prepare_declaration(b, attacker, target, true) else { return None };
        let mut planner = Planner::new(attacker, target, &ctx.adjust, ctx.ams_share, ctx.pod_values.clone(), Some(ctx.hex_offset));
        let choice = if princess || b.units[attacker].bot == "princess" {
            crate::gladiator::choose_declaration_princess(b, &ctx, &mut planner, attacker, target)
        } else {
            crate::gladiator::choose_declaration(b, &ctx, &mut planner, attacker, target)
        };
        if choice.weapons.is_empty() {
            return None;
        }
        let dmg = plan_damage(b, attacker, &choice.weapons, &mut planner, ctx.distance, ctx.sel_pre_tn);
        Some((choice.exp_dmg, dmg, ctx.side.clone()))
    })();
    b.log.quiet -= 1;
    r
}

/// princess_group.choose_target: the enemy whose firing plan has the highest utility for this attacker now.
pub fn princess_choose_target(b: &mut Battle, attacker: UnitId) -> Option<UnitId> {
    let foes = candidates(b, attacker);
    let fallback = crate::forces::choose_target(b, attacker, true, false);
    if foes.len() < 2 {
        return fallback;
    }
    let mut best: Option<(f64, UnitId)> = None;
    for foe in foes {
        if let Some(got) = dry_declare(b, attacker, foe) {
            if best.map_or(true, |(v, _)| got.0 > v) {
                best = Some((got.0, foe));
            }
        }
    }
    best.map(|(_, f)| f).or(fallback)
}

/// bots._choose_target for a Gladiator.
pub fn gladiator_choose_target(b: &mut Battle, attacker: UnitId) -> Option<UnitId> {
    let policy = b.cfg.s("STUB_GLADIATOR_TARGET").to_string();
    match policy.as_str() {
        "kill_curve" => panic!("STUB_GLADIATOR_TARGET kill_curve is not translated yet"),
        "princess_plan" => {
            let enemies = candidates(b, attacker).len();
            if enemies >= 2 {
                let target = princess_choose_target(b, attacker);
                let name = b.units[attacker].side_name.clone().unwrap_or_default();
                let tname = target.map_or("nobody".to_string(), |t| b.units[t].side_name.clone().unwrap_or_default());
                b.warn_stub("gladiator_target", &format!("{}: {} enemies on the board -> fires at {} (Princess's firing-plan utility)", name, enemies, tname));
                return target;
            }
        }
        "nearest" => {}
        o => panic!("Unknown STUB_GLADIATOR_TARGET {:?}", o),
    }
    crate::forces::choose_target(b, attacker, true, false)
}

/// kill_curve.firepower: the most expected damage this unit could deal any one enemy now (the dry run of its own weapon
/// choice) - Gladiator's firing order ranks by it.
pub fn firepower(b: &mut Battle, attacker: UnitId) -> f64 {
    let mut best = 0.0f64;
    for foe in candidates(b, attacker) {
        if let Some(got) = dry_declare_as(b, attacker, foe, false) {
            best = best.max(got.1);
        }
    }
    best
}

/// bots.fire_pick active? (None = roster order unless a side has two Gladiators and the order is "big_guns_first"). Starts
/// the phase's firepower cache.
pub fn fire_pick_active(b: &mut Battle) -> bool {
    b.princess.guns.clear();
    if b.cfg.s("GLADIATOR_FIRE_ORDER") == "roster" {
        return false;
    }
    let standing = crate::forces::standing(b);
    let teams: Vec<String> = standing.iter().filter(|u| b.units[**u].bot != "princess").map(|u| b.units[*u].team.clone().unwrap_or_default()).collect();
    if teams.iter().all(|t| teams.iter().filter(|x| *x == t).count() < 2) {
        return false;
    }
    assert!(b.cfg.s("GLADIATOR_FIRE_ORDER") == "big_guns_first", "Unknown GLADIATOR_FIRE_ORDER");
    true
}

/// The pick function of fire_pick: the candidate with the biggest guns (first of equals: roster order); Princess units rank
/// last. Logs the choice when it is a Gladiator among several.
pub fn fire_pick(b: &mut Battle, candidates: &[UnitId]) -> UnitId {
    let mut best: Option<(UnitId, (i64, f64))> = None;
    for &u in candidates {
        let rank = if b.units[u].bot == "princess" {
            (0, 0.0)
        } else {
            let g = match b.princess.guns.get(&u) {
                Some(g) => *g,
                None => {
                    let g = firepower(b, u);
                    b.princess.guns.insert(u, g);
                    g
                }
            };
            (1, g)
        };
        if best.map_or(true, |(_, r)| rank > r) {
            best = Some((u, rank));
        }
    }
    let (u, _) = best.unwrap();
    if b.units[u].bot != "princess" && candidates.len() > 1 {
        let name = b.units[u].side_name.clone().unwrap_or_default();
        let g = b.princess.guns[&u];
        b.log(format!("  [Ranged] Firing order: {} declares next (big guns first: expected {}).", name, crate::pyfmt::Fx(g, 1)));
    }
    u
}
