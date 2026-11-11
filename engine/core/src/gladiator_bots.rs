// INTEGRATION__bots.py for Gladiator duels: the bots' choices computed by the Rust bots instead of read back from
// decisions.json. Several enemies (Legate, kill-curve targeting), Princess and the other research layers are not
// translated yet: asking for one of them is a loud panic naming what is missing, never a quiet default.
use crate::attack_resolution::{DeclChoice, DeclCtx};
use crate::battle::{Battle, UnitId};
use crate::fire_modes::Planner;
use crate::mech_state::ArcAction;
use crate::move_select::{self, Ties};
use crate::orchestrator::{BotSet, PathGate};
use crate::physical::PhysOption;
use crate::ranged_combat::Pick;

#[derive(Default)]
pub struct GladiatorBots;

fn require_gladiator(b: &Battle, u: UnitId, what: &str) {
    if b.units[u].bot != "gladiator" {
        panic!("{} for a {} unit is not translated yet", what, b.units[u].bot);
    }
}

fn require_duel(b: &mut Battle, u: UnitId, what: &str) {
    let n = crate::forces::enemies_of(b, u).len();
    if n > 1 {
        panic!("{} against {} enemies (Legate / kill-curve targeting) is not translated yet", what, n);
    }
}

impl BotSet for GladiatorBots {
    fn choose_foe(&mut self, b: &mut Battle, mover: UnitId) -> Option<UnitId> {
        require_gladiator(b, mover, "choose_foe");
        crate::legate::foe_for(b, mover).or_else(|| crate::forces::choose_foe(b, mover))
    }

    fn choose_target(&mut self, b: &mut Battle, attacker: UnitId) -> Option<UnitId> {
        require_gladiator(b, attacker, "choose_target");
        crate::bot_targets::gladiator_choose_target(b, attacker)
    }

    fn fire_pick_active(&mut self, b: &mut Battle) -> bool {
        crate::bot_targets::fire_pick_active(b)
    }

    fn fire_pick(&mut self, b: &mut Battle, candidates: &[UnitId]) -> UnitId {
        crate::bot_targets::fire_pick(b, candidates)
    }

    fn choose_declaration(&mut self, b: &mut Battle, ctx: &DeclCtx, planner: &mut Planner, attacker: UnitId, target: UnitId) -> DeclChoice {
        require_gladiator(b, attacker, "choose_declaration");
        crate::gladiator::choose_declaration(b, ctx, planner, attacker, target)
    }

    fn choose_physical(&mut self, b: &mut Battle, attacker: UnitId, target: UnitId) -> Option<(i64, Vec<PhysOption>, ArcAction)> {
        require_gladiator(b, attacker, "choose_physical");
        crate::physical::choose_attack(b, attacker, target)
    }

    fn choose_movement(&mut self, b: &mut Battle, mover: UnitId, other: UnitId, moves_first: bool, standup_mp: Option<i64>, entry_edge: Option<&[String]>) -> (Option<Pick>, String, PathGate) {
        require_gladiator(b, mover, "choose_movement");
        let mut ties = Ties { recorded: None, missed: false };
        let (pick, note) = move_select::choose(b, mover, other, moves_first, standup_mp, entry_edge, &mut ties);
        let gate = match &pick {
            Some(p) => {
                let (psrs, hazard) = crate::ranged_combat::path_notes(b, mover, p, standup_mp, entry_edge);
                PathGate { psrs, hazard }
            }
            None => PathGate::default(),
        };
        (pick, note, gate)
    }

    fn start_movement(&mut self, b: &mut Battle) {
        crate::legate::plan_turn(b);
    }

    fn end_movement(&mut self, b: &mut Battle) {
        crate::legate::end_phase(b);
    }

    fn records_declared_damage(&self, b: &Battle, attacker: UnitId) -> bool {
        // bots.records_declared_damage: Princess always; a Gladiator when it borrows Princess's target choice or runs the
        // kill-curve director
        b.units[attacker].bot == "princess" || matches!(b.cfg.s("STUB_GLADIATOR_TARGET"), "princess_plan" | "kill_curve")
    }

    fn reset_assigned(&mut self, b: &mut Battle) {
        crate::princess_fire::reset_assigned(b);
    }

    fn assign_damage(&mut self, b: &mut Battle, attacker: UnitId, target: UnitId, dmg: f64) {
        let team = b.units[attacker].team.clone().unwrap_or_default();
        crate::princess_fire::assign_damage(b, &team, target, dmg);
    }
}
