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
    #[allow(unused)]
    fn choose_foe(&mut self, b: &mut Battle, mover: UnitId) -> Option<UnitId> {
        if b.units[mover].bot == "gladiator" {
            if let Some(f) = crate::legate::foe_for(b, mover) {
                return Some(f);
            }
        }
        // forces.choose_foe(...) or forces.any_enemy(...): the foe a unit still plans against when its last enemy fell earlier in
        // the same phase (destroyed or not)
        crate::forces::choose_foe(b, mover).or_else(|| (0..b.units.len()).find(|u| b.units[*u].team != b.units[mover].team))
    }

    #[allow(unused)]
    fn choose_target(&mut self, b: &mut Battle, attacker: UnitId) -> Option<UnitId> {
        if b.units[attacker].is_princess_family() {
            return crate::bot_targets::princess_choose_target(b, attacker);
        }
        if b.units[attacker].bot == "hydra" {
            return crate::hydra::choose_target(b, attacker);
        }
        crate::bot_targets::gladiator_choose_target(b, attacker)
    }

    fn fire_pick_active(&mut self, b: &mut Battle) -> bool {
        crate::bot_targets::fire_pick_active(b)
    }

    fn fire_pick(&mut self, b: &mut Battle, candidates: &[UnitId]) -> UnitId {
        crate::bot_targets::fire_pick(b, candidates)
    }

    fn move_pick(&mut self, b: &mut Battle, candidates: &[UnitId]) -> Option<UnitId> {
        crate::hydra::picks_move_order(b, candidates).then(|| crate::hydra::move_pick(b, candidates))
    }

    #[allow(unused)]
    fn choose_declaration(&mut self, b: &mut Battle, ctx: &DeclCtx, planner: &mut Planner, attacker: UnitId, target: UnitId) -> DeclChoice {
        if b.units[attacker].is_princess_family() {
            return crate::gladiator::choose_declaration_princess(b, ctx, planner, attacker, target);
        }
        crate::gladiator::choose_declaration(b, ctx, planner, attacker, target)
    }

    #[allow(unused)]
    fn choose_physical(&mut self, b: &mut Battle, attacker: UnitId, target: UnitId) -> Option<(i64, Vec<PhysOption>, ArcAction)> {
        if b.units[attacker].is_princess_family() {
            return crate::princess_fire::choose_physical(b, attacker, target);
        }
        crate::physical::choose_attack(b, attacker, target)
    }

    #[allow(unused)]
    fn choose_movement(&mut self, b: &mut Battle, mover: UnitId, other: UnitId, moves_first: bool, standup_mp: Option<i64>, entry_edge: Option<&[String]>) -> (Option<Pick>, String, PathGate) {
        let mut ties = Ties { recorded: None, missed: false };
        let (pick, note) = if b.units[mover].bot == "hydra" {
            crate::hydra::choose_movement(b, mover, other, moves_first, standup_mp, entry_edge)
        } else if b.units[mover].is_princess_family() {
            // CASPAR = Princess's whole movement ranker with the Mutual Support doctrine swapped in (caspar.rs)
            crate::princess_modern::choose_as(b, mover, other, moves_first, standup_mp, entry_edge, &mut ties, b.units[mover].bot == "caspar")
        } else {
            move_select::choose(b, mover, other, moves_first, standup_mp, entry_edge, &mut ties)
        };
        let gate = match &pick {
            Some(p) => {
                let (psrs, hazard) = crate::ranged_combat::path_notes(b, mover, p, standup_mp, entry_edge);
                PathGate { psrs, hazard }
            }
            None => PathGate::default(),
        };
        (pick, note, gate)
    }

    fn unit_moved(&mut self, b: &mut Battle, mover: UnitId, start_hex: Option<&str>) {
        crate::princess_memory::unit_moved(b, mover, start_hex);
    }

    fn end_of_turn(&mut self, b: &mut Battle) {
        crate::princess_memory::end_of_turn(b);
    }

    #[allow(unused)]
    fn start_movement(&mut self, b: &mut Battle) {
        b.hydra.start_movement_phase();
        crate::legate::plan_turn(b);
        // T16: Princess-family units start to be managed before the first Heat Phase
        crate::bot_heat_equipment::begin_battle(b);
    }

    fn manage_heat_equipment(&mut self, b: &mut Battle) {
        crate::bot_heat_equipment::manage_owned_units(b);
    }

    fn choose_spot(&mut self, b: &mut Battle, u: UnitId) -> Option<(UnitId, bool)> {
        if !b.units[u].is_princess_family() {
            return crate::stubs::stub_spot(b, u); // Gladiator / Hydra: the stub (Daniel: stub markers for what they can't do yet)
        }
        // Princess / CASPAR price their own firing plan first (MegaMek FireControl.getSpotAction takes the plan): her
        // target and her weapon choice, worked out dry (no stub warning, no log line) as the bridge does
        let plan = match self.choose_target(b, u) {
            None => None,
            Some(target) => {
                b.log.quiet += 1;
                let damage = match crate::attack_resolution::prepare_declaration(b, u, target, true) {
                    crate::attack_resolution::Prep::Ready(ctx) => {
                        let mut planner = crate::fire_modes::Planner::new(u, target, &ctx.adjust, ctx.ams_share, ctx.pod_values.clone(), Some(ctx.hex_offset));
                        let choice = self.choose_declaration(b, &ctx, &mut planner, u, target);
                        if choice.weapons.is_empty() { None } else { Some(choice.exp_dmg) }
                    }
                    _ => None,
                };
                b.log.quiet -= 1;
                damage
            }
        };
        crate::spotting::princess_spot(b, u, plan)
    }

    fn end_movement(&mut self, b: &mut Battle) {
        crate::legate::end_phase(b);
    }

    fn records_declared_damage(&self, b: &Battle, attacker: UnitId) -> bool {
        // bots.records_declared_damage: Princess always; a Gladiator when it borrows Princess's target choice or runs the
        // kill-curve director
        b.units[attacker].is_princess_family() || matches!(b.cfg.s("STUB_GLADIATOR_TARGET"), "princess_plan" | "kill_curve")
    }

    fn reset_assigned(&mut self, b: &mut Battle) {
        crate::princess_fire::reset_assigned(b);
        b.hydra.start_fire_phase();
    }

    fn assign_damage(&mut self, b: &mut Battle, attacker: UnitId, target: UnitId, dmg: f64) {
        let team = b.units[attacker].team.clone().unwrap_or_default();
        crate::princess_fire::assign_damage(b, &team, target, dmg);
    }
}
