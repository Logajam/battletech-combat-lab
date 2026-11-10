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
        require_duel(b, mover, "choose_foe");
        crate::forces::choose_foe(b, mover)
    }

    fn choose_target(&mut self, b: &mut Battle, attacker: UnitId) -> Option<UnitId> {
        require_gladiator(b, attacker, "choose_target");
        require_duel(b, attacker, "choose_target");
        crate::forces::choose_target(b, attacker, true, false)
    }

    fn fire_pick_active(&mut self, b: &mut Battle) -> bool {
        // bots.fire_pick: None (roster order) unless a side has two Gladiators and the order is "big_guns_first"
        if b.cfg.s("GLADIATOR_FIRE_ORDER") == "roster" {
            return false;
        }
        let standing = crate::forces::standing(b);
        let teams: Vec<String> = standing.iter().filter(|u| b.units[**u].bot != "princess").map(|u| b.units[*u].team.clone().unwrap_or_default()).collect();
        !teams.iter().all(|t| teams.iter().filter(|x| *x == t).count() < 2)
    }

    fn fire_pick(&mut self, _b: &mut Battle, _candidates: &[UnitId]) -> UnitId {
        panic!("Gladiator's firing order (kill_curve.firepower) is not translated yet");
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
        require_duel(b, mover, "choose_movement");
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

    fn records_declared_damage(&self, _b: &Battle, _attacker: UnitId) -> bool {
        false // the damage map only matters to several-enemy targeting (not translated); nothing the engine prints depends on it
    }
}
