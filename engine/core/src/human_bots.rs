//! HUMAN CONTROLLER (BattleROM, first playable slice, step E1; INTEGRATION__PLAYER_DECISIONS.md Section 15). Not translated
//! from the Python.
//!
//! `HumanBots` is a `BotSet` that hands the decisions of the units a person controls to a `Controller` and lets every other
//! unit's decisions go to the normal bots (`GladiatorBots`, which routes to Princess / Hydra / CASPAR by the unit's own bot).
//! The engine has no clock: a controller call simply does not return until it has an answer, so a person (a channel to a
//! web page, a script) can take as long as it likes. Every answer a controller gives is written to `log`, the decision
//! list: replaying a game, going back to a point and changing one answer, or taking over a bot's unit mid-replay is
//! feeding that list back in.
//!
//! Nothing here changes a battle whose controller passes every question on to the normal bot
//! (`tests/human_bots.rs`: same log as a plain run).
use std::collections::HashSet;

use crate::attack_resolution::{DeclChoice, DeclCtx};
use crate::battle::{Battle, UnitId};
use crate::fire_modes::Planner;
use crate::gladiator_bots::GladiatorBots;
use crate::mech_state::ArcAction;
use crate::orchestrator::{BotSet, PathGate};
use crate::physical::PhysOption;
use crate::ranged_combat::Pick;

/// A physical attack answer: (worth, the attacks, the torso action) as `BotSet::choose_physical` gives it.
pub type PhysicalChoice = Option<(i64, Vec<PhysOption>, ArcAction)>;

/// One answer a controller gave: the unit it was about and what it chose.
#[derive(Clone, Debug)]
pub enum Decision {
    /// which unit of a side moves next
    MoveOrder { chosen: UnitId },
    /// a unit's finished move (None: stays where it is)
    Movement { unit: UnitId, pick: Option<Pick> },
    /// the one enemy a unit fires at (None: holds fire)
    Target { unit: UnitId, target: Option<UnitId> },
    /// the weapons, torso twist / arm flip and the physical attack planned beside them
    Declaration { unit: UnitId, target: UnitId, choice: DeclChoice },
    /// the physical attack after the ranged phase
    Physical { unit: UnitId, target: UnitId, choice: PhysicalChoice },
    /// any other answer (stand up, MASC, End Phase switches, TAG, spot): what it was about and the answer as text
    Choice { unit: UnitId, kind: &'static str, answer: String },
}

/// What answers for a person's units. Each method is called only for a unit the person controls and may take any time.
/// `inner` is the normal bot for the same question, for a controller that wants its advice or to pass a question on.
pub trait Controller {
    fn move_order(&mut self, b: &mut Battle, candidates: &[UnitId], inner: &mut GladiatorBots) -> UnitId;
    #[allow(clippy::too_many_arguments)]
    fn movement(&mut self, b: &mut Battle, mover: UnitId, other: UnitId, moves_first: bool, standup_mp: Option<i64>, entry_edge: Option<&[String]>, inner: &mut GladiatorBots) -> (Option<Pick>, String, PathGate);
    fn target(&mut self, b: &mut Battle, attacker: UnitId, inner: &mut GladiatorBots) -> Option<UnitId>;
    fn declaration(&mut self, b: &mut Battle, ctx: &DeclCtx, planner: &mut Planner, attacker: UnitId, target: UnitId, inner: &mut GladiatorBots) -> DeclChoice;
    fn physical(&mut self, b: &mut Battle, attacker: UnitId, target: UnitId, inner: &mut GladiatorBots) -> PhysicalChoice;
    /// A unit is about to move: MASC / supercharger and similar switches. Returns what was set, as text (None: nothing asked).
    fn before_move(&mut self, _b: &mut Battle, _mover: UnitId) -> Option<String> {
        None
    }
    /// May a prone unit that can stand try to?
    fn stand_up(&mut self, _b: &mut Battle, _mover: UnitId) -> bool {
        true
    }
    /// The Heat Phase is about to start for this unit.
    fn end_phase(&mut self, _b: &mut Battle, _u: UnitId, _weapon_heat: i64) -> Option<String> {
        None
    }
    /// TAG designation: None = does not designate.
    fn tag(&mut self, _b: &mut Battle, _attacker: UnitId, _cands: &[crate::tag::TagCandidate]) -> Option<(UnitId, &'static str)> {
        None
    }
    /// Spot for indirect fire.
    fn spot(&mut self, b: &mut Battle, u: UnitId, inner: &mut GladiatorBots) -> Option<(UnitId, bool)> {
        inner.choose_spot(b, u)
    }
}

pub struct HumanBots<C: Controller> {
    /// the normal bots, for every unit nobody controls
    pub inner: GladiatorBots,
    pub ctl: C,
    /// the units a person controls
    pub human: HashSet<UnitId>,
    /// the decision list, in the order the answers were given
    pub log: Vec<Decision>,
}

impl<C: Controller> HumanBots<C> {
    pub fn new(ctl: C, human: impl IntoIterator<Item = UnitId>) -> Self {
        HumanBots { inner: GladiatorBots, ctl, human: human.into_iter().collect(), log: Vec::new() }
    }
}

impl<C: Controller> BotSet for HumanBots<C> {
    fn choose_foe(&mut self, b: &mut Battle, mover: UnitId) -> Option<UnitId> {
        self.inner.choose_foe(b, mover)
    }

    fn choose_target(&mut self, b: &mut Battle, attacker: UnitId) -> Option<UnitId> {
        if !self.human.contains(&attacker) {
            return self.inner.choose_target(b, attacker);
        }
        let target = self.ctl.target(b, attacker, &mut self.inner);
        self.log.push(Decision::Target { unit: attacker, target });
        target
    }

    fn fire_pick_active(&mut self, b: &mut Battle) -> bool {
        self.inner.fire_pick_active(b)
    }

    fn fire_pick(&mut self, b: &mut Battle, candidates: &[UnitId]) -> UnitId {
        self.inner.fire_pick(b, candidates)
    }

    /// A side with a person's unit among the units still to move lets the person choose which moves next.
    fn move_pick(&mut self, b: &mut Battle, candidates: &[UnitId]) -> Option<UnitId> {
        if !candidates.iter().any(|u| self.human.contains(u)) {
            return self.inner.move_pick(b, candidates);
        }
        let chosen = self.ctl.move_order(b, candidates, &mut self.inner);
        assert!(candidates.contains(&chosen), "a controller must choose among the units still to move");
        self.log.push(Decision::MoveOrder { chosen });
        Some(chosen)
    }

    /// The forecast of the move queue never asks a person: the engine's own order stands in.
    fn move_pick_forecast(&mut self, b: &mut Battle, candidates: &[UnitId]) -> Option<UnitId> {
        if candidates.iter().any(|u| self.human.contains(u)) {
            return None;
        }
        self.inner.move_pick(b, candidates)
    }

    fn choose_declaration(&mut self, b: &mut Battle, ctx: &DeclCtx, planner: &mut Planner, attacker: UnitId, target: UnitId) -> DeclChoice {
        if !self.human.contains(&attacker) {
            return self.inner.choose_declaration(b, ctx, planner, attacker, target);
        }
        let choice = self.ctl.declaration(b, ctx, planner, attacker, target, &mut self.inner);
        self.log.push(Decision::Declaration { unit: attacker, target, choice: choice.clone() });
        choice
    }

    fn choose_physical(&mut self, b: &mut Battle, attacker: UnitId, target: UnitId) -> PhysicalChoice {
        if !self.human.contains(&attacker) {
            return self.inner.choose_physical(b, attacker, target);
        }
        let choice = self.ctl.physical(b, attacker, target, &mut self.inner);
        self.log.push(Decision::Physical { unit: attacker, target, choice: choice.clone() });
        choice
    }

    fn choose_movement(&mut self, b: &mut Battle, mover: UnitId, other: UnitId, moves_first: bool, standup_mp: Option<i64>, entry_edge: Option<&[String]>) -> (Option<Pick>, String, PathGate) {
        if !self.human.contains(&mover) {
            return self.inner.choose_movement(b, mover, other, moves_first, standup_mp, entry_edge);
        }
        let answer = self.ctl.movement(b, mover, other, moves_first, standup_mp, entry_edge, &mut self.inner);
        self.log.push(Decision::Movement { unit: mover, pick: answer.0.clone() });
        answer
    }

    fn records_declared_damage(&self, b: &Battle, attacker: UnitId) -> bool {
        self.inner.records_declared_damage(b, attacker)
    }

    fn reset_assigned(&mut self, b: &mut Battle) {
        self.inner.reset_assigned(b);
    }

    fn start_movement(&mut self, b: &mut Battle) {
        self.inner.start_movement(b);
    }

    fn unit_moved(&mut self, b: &mut Battle, mover: UnitId, start_hex: Option<&str>) {
        self.inner.unit_moved(b, mover, start_hex);
    }

    fn end_of_turn(&mut self, b: &mut Battle) {
        self.inner.end_of_turn(b);
    }

    fn end_movement(&mut self, b: &mut Battle) {
        self.inner.end_movement(b);
    }

    fn manage_heat_equipment(&mut self, b: &mut Battle) {
        self.inner.manage_heat_equipment(b);
    }

    fn choose_spot(&mut self, b: &mut Battle, u: UnitId) -> Option<(UnitId, bool)> {
        if !self.human.contains(&u) {
            return self.inner.choose_spot(b, u);
        }
        let r = self.ctl.spot(b, u, &mut self.inner);
        self.log.push(Decision::Choice { unit: u, kind: "spot", answer: format!("{:?}", r) });
        r
    }

    fn before_move(&mut self, b: &mut Battle, mover: UnitId) {
        if self.human.contains(&mover) {
            if let Some(a) = self.ctl.before_move(b, mover) {
                self.log.push(Decision::Choice { unit: mover, kind: "before_move", answer: a });
            }
        }
    }

    fn wants_stand_up(&mut self, b: &mut Battle, mover: UnitId) -> bool {
        if !self.human.contains(&mover) {
            return true;
        }
        let r = self.ctl.stand_up(b, mover);
        self.log.push(Decision::Choice { unit: mover, kind: "stand_up", answer: r.to_string() });
        r
    }

    fn end_phase(&mut self, b: &mut Battle, u: UnitId, weapon_heat: i64) {
        if self.human.contains(&u) {
            if let Some(a) = self.ctl.end_phase(b, u, weapon_heat) {
                self.log.push(Decision::Choice { unit: u, kind: "end_phase", answer: a });
            }
        }
    }

    fn choose_tag(&mut self, b: &mut Battle, attacker: UnitId, cands: &[crate::tag::TagCandidate]) -> Option<Option<(UnitId, &'static str)>> {
        if !self.human.contains(&attacker) {
            return None;
        }
        let r = self.ctl.tag(b, attacker, cands);
        self.log.push(Decision::Choice { unit: attacker, kind: "tag", answer: format!("{:?}", r) });
        Some(r)
    }

    fn assign_damage(&mut self, b: &mut Battle, attacker: UnitId, target: UnitId, dmg: f64) {
        self.inner.assign_damage(b, attacker, target, dmg);
    }
}

/// A controller that passes every question to the normal bot: the stand-in for a person in tests, and the reference
/// that a person's units behave as bots until the person answers differently.
pub struct PassThrough;

impl Controller for PassThrough {
    fn move_order(&mut self, b: &mut Battle, candidates: &[UnitId], inner: &mut GladiatorBots) -> UnitId {
        inner.move_pick(b, candidates).unwrap_or_else(|| {
            // the engine's own move index (orchestrator::play_turn)
            let mut best = candidates[0];
            let mut best_v = crate::forces::move_index(b, best);
            for &u in &candidates[1..] {
                let v = crate::forces::move_index(b, u);
                if v > best_v {
                    best = u;
                    best_v = v;
                }
            }
            best
        })
    }
    fn movement(&mut self, b: &mut Battle, mover: UnitId, other: UnitId, moves_first: bool, standup_mp: Option<i64>, entry_edge: Option<&[String]>, inner: &mut GladiatorBots) -> (Option<Pick>, String, PathGate) {
        inner.choose_movement(b, mover, other, moves_first, standup_mp, entry_edge)
    }
    fn target(&mut self, b: &mut Battle, attacker: UnitId, inner: &mut GladiatorBots) -> Option<UnitId> {
        inner.choose_target(b, attacker)
    }
    fn declaration(&mut self, b: &mut Battle, ctx: &DeclCtx, planner: &mut Planner, attacker: UnitId, target: UnitId, inner: &mut GladiatorBots) -> DeclChoice {
        inner.choose_declaration(b, ctx, planner, attacker, target)
    }
    fn physical(&mut self, b: &mut Battle, attacker: UnitId, target: UnitId, inner: &mut GladiatorBots) -> PhysicalChoice {
        inner.choose_physical(b, attacker, target)
    }
}
