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
    b.log.quiet += 1;
    let r = (|| {
        let Prep::Ready(ctx) = prepare_declaration(b, attacker, target, true) else { return None };
        let mut planner = Planner::new(attacker, target, &ctx.adjust, ctx.ams_share, ctx.pod_values.clone(), Some(ctx.hex_offset));
        let choice = crate::gladiator::choose_declaration_princess(b, &ctx, &mut planner, attacker, target);
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
