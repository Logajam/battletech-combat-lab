// Translated from INTEGRATION__orchestrator.py (session 22): the turn loop. The bots' choices come through `BotSet`
// (Stage 6 plays them back from decisions.json: `replay_bots`; Stages 7-8 compute them). Observers the Python has
// (stats, replay pages, timing) are not here; the test hook `Marks` stands where `replay.mark(...)` is.
use crate::fasthash::IndexMap;

use crate::attack_resolution::{self as ar, DeclChoice, DeclCtx, RangedBot, SideReport};
use crate::battle::{Battle, UnitId};
use crate::equipment_systems as equip;
use crate::fire_modes::Planner;
use crate::forces;
use crate::hex_geometry;
use crate::mech_state::*;
use crate::physical::{PhysOption, PhysicalBot};
use crate::piloting_rolls as pr;
use crate::ranged_combat::{path_to, Pick};
use crate::results::{team_totals, BattleResult, SideStats};
use crate::terrain_rules;
use crate::{arcs, clubs, deployment, fire_modes, hazards, heat, smoke, tag, water};

/// The bots' choices (INTEGRATION__bots), one method per decision kind of the seam.
pub trait BotSet {
    fn choose_foe(&mut self, b: &mut Battle, mover: UnitId) -> Option<UnitId>;
    /// bots.choose_target: the one enemy a unit fires at in the Ranged phase
    fn choose_target(&mut self, b: &mut Battle, attacker: UnitId) -> Option<UnitId>;
    /// bots.fire_pick active? (Gladiator's firing order); then `fire_pick` chooses among the candidates
    fn fire_pick_active(&mut self, b: &mut Battle) -> bool;
    fn fire_pick(&mut self, b: &mut Battle, candidates: &[UnitId]) -> UnitId;
    /// Which of a side's units moves next, when the side's bot chooses (Hydra's S3); None = the engine's move index.
    /// Must only read the battle: it also forecasts the move queue.
    fn move_pick(&mut self, _b: &mut Battle, _candidates: &[UnitId]) -> Option<UnitId> {
        None
    }
    fn choose_declaration(&mut self, b: &mut Battle, ctx: &DeclCtx, planner: &mut Planner, attacker: UnitId, target: UnitId) -> DeclChoice;
    fn choose_physical(&mut self, b: &mut Battle, attacker: UnitId, target: UnitId) -> Option<(i64, Vec<PhysOption>, ArcAction)>;
    /// bots.choose_movement: (pick, note, the terrain PSRs / hazard the search noted for the pick)
    fn choose_movement(&mut self, b: &mut Battle, mover: UnitId, other: UnitId, moves_first: bool, standup_mp: Option<i64>, entry_edge: Option<&[String]>) -> (Option<Pick>, String, PathGate);
    fn records_declared_damage(&self, b: &Battle, attacker: UnitId) -> bool;
    fn reset_assigned(&mut self, _b: &mut Battle) {}
    /// The Movement Phase begins (legate.plan_turn) / ends (legate.end_phase)
    fn start_movement(&mut self, _b: &mut Battle) {}
    /// Princess's memory: a unit moved (princess_memory.unit_moved) / the turn's heat phase is over (end_of_turn)
    fn unit_moved(&mut self, _b: &mut Battle, _mover: UnitId, _start_hex: Option<&str>) {}
    fn end_of_turn(&mut self, _b: &mut Battle) {}
    fn end_movement(&mut self, _b: &mut Battle) {}
    fn assign_damage(&mut self, _b: &mut Battle, _attacker: UnitId, _target: UnitId, _dmg: f64) {}
}

/// mover.path_psrs[pick] / mover.path_hazard[pick] as the search left them.
#[derive(Clone, Copy, Debug, Default)]
pub struct PathGate {
    pub psrs: Option<i64>,
    pub hazard: Option<f64>,
}

struct RangedAdapter<'a> {
    bots: &'a mut dyn BotSet,
}

impl RangedBot for RangedAdapter<'_> {
    fn reset_assigned(&mut self, b: &mut Battle) {
        self.bots.reset_assigned(b);
    }
    fn target_of(&mut self, b: &mut Battle, attacker: UnitId) -> Option<UnitId> {
        self.bots.choose_target(b, attacker)
    }
    fn choose(&mut self, b: &mut Battle, ctx: &DeclCtx, planner: &mut Planner, attacker: UnitId, target: UnitId) -> DeclChoice {
        self.bots.choose_declaration(b, ctx, planner, attacker, target)
    }
    fn records_declared_damage(&self, b: &Battle, attacker: UnitId) -> bool {
        self.bots.records_declared_damage(b, attacker)
    }
    fn assign_damage(&mut self, b: &mut Battle, attacker: UnitId, target: UnitId, dmg: f64) {
        self.bots.assign_damage(b, attacker, target, dmg);
    }
}

struct PhysAdapter<'a> {
    bots: &'a mut dyn BotSet,
}

impl PhysicalBot for PhysAdapter<'_> {
    fn target_of(&mut self, b: &mut Battle, attacker: UnitId) -> Option<UnitId> {
        // declared = getattr(u, "charging", None) or getattr(u, "dfa", None); the attack the unit declared in Movement
        let declared = b.units[attacker].charging.or(b.units[attacker].dfa);
        declared.or_else(|| forces::choose_target(b, attacker, true, true))
    }
    fn choose_physical(&mut self, b: &mut Battle, attacker: UnitId, target: UnitId) -> Option<(i64, Vec<PhysOption>, ArcAction)> {
        self.bots.choose_physical(b, attacker, target)
    }
}

/// The test hook at `replay.mark(turn, label)`: called with the battle state at the end of each marked phase.
pub type Marks<'a> = &'a mut dyn FnMut(&mut Battle, i64, &str);

fn name(b: &Battle, u: UnitId) -> String {
    b.units[u].side_name.clone().unwrap_or_default()
}

pub fn reset_movement_state(m: &mut Mech) {
    equip::reset_movement_boost(m);
    m.move_mode = "Stand Still".into();
    m.move_fc = 0;
    m.mp_spent = 0;
    m.movement_heat = 0;
    m.charging = None;
    m.dfa = None;
    m.deferred_end_of_move = Some(serde_json::Value::Null);
}

// ---- movement phase ---------------------------------------------------------------------------------------------------
/// A prone mech that can't stand may still change facing: 1 MP per hexside (p.98).
fn turn_while_down(b: &mut Battle, mover: UnitId, other: UnitId) {
    if b.units[other].hex.is_none() || b.units[mover].hex.is_none() {
        return;
    }
    let walk = compute_walk_mp(&b.units[mover]);
    let max_turns = walk.min(if gyro_destroyed(&b.units[mover]) { 1 } else { 3 });
    if max_turns < 1 {
        return;
    }
    let me = hex_geometry::parse_hex_label(b.units[mover].hex.as_deref().unwrap()).unwrap();
    let them = hex_geometry::parse_hex_label(b.units[other].hex.as_deref().unwrap()).unwrap();
    let seen_as = arcs::arcs_between(me, them);
    let facing = hex_geometry::compass_to_facing(&b.units[mover].facing).unwrap();
    let rank = |f: i64| -> i64 {
        if seen_as[f as usize] == arcs::FORWARD {
            0
        } else if seen_as[f as usize] != arcs::REAR {
            1
        } else {
            2
        }
    };
    let (mut best, mut best_turns) = (facing, 0);
    for turns in 1..=max_turns {
        for f in [(facing + turns).rem_euclid(6), (facing - turns).rem_euclid(6)] {
            if rank(f) < rank(best) {
                best = f;
                best_turns = turns;
            }
        }
    }
    if best_turns == 0 {
        return;
    }
    let compass = hex_geometry::facing_to_compass(best).unwrap().to_string();
    b.units[mover].facing = compass.clone();
    b.units[mover].move_mode = "Walk".into();
    b.units[mover].mp_spent = best_turns;
    let line = format!(
        "  [Movement] {}: can't stand - turns {} hexside(s) on the ground to face {} ({} arc on {}; Walk, {} MP).",
        name(b, mover),
        best_turns,
        compass,
        arcs::arc_name(seen_as[best as usize]),
        name(b, other),
        best_turns
    );
    b.log(line);
}

/// One mech's movement, with the mobile enemies' hexes closed to its ground moves while it moves (p.48).
pub fn phase_movement(b: &mut Battle, bots: &mut dyn BotSet, mover: UnitId, other: UnitId, turn_number: i64, moves_first: bool) {
    let blocked: Vec<serde_json::Value> = forces::blocked_xy(b, mover).into_iter().map(|(x, y)| serde_json::json!([x, y])).collect();
    b.units[mover].blocked_hex = Some(serde_json::Value::Array(blocked));
    let occ = forces::occupied_labels(b, mover);
    b.units[mover].other_unit_hexes = Some(serde_json::json!(occ));
    hazards::start_of_movement(b, mover);
    if !b.is_destroyed(mover) {
        do_move(b, bots, mover, other, turn_number, moves_first);
    }
    b.units[mover].blocked_hex = Some(serde_json::Value::Null);
    b.units[mover].other_unit_hexes = Some(serde_json::Value::Null);
    b.units[mover].jump_only = Some(false);
    hazards::end_of_movement(b, mover);
}

fn move_budget(b: &Battle, u: UnitId) -> (i64, i64, i64) {
    (compute_walk_mp(&b.units[u]), compute_running_mp(&b.units[u]), water::jump_mp(b, u))
}

fn do_move(b: &mut Battle, bots: &mut dyn BotSet, mover: UnitId, other: UnitId, turn_number: i64, moves_first: bool) {
    b.units[mover].turn_number = turn_number;
    let nm = name(b, mover);
    reset_movement_state(&mut b.units[mover]);

    if is_immobile(&b.units[mover]) {
        let m = &b.units[mover];
        let why = if m.shutdown { "shut down" } else if all_crew_unconscious(m) { "all crew unconscious" } else { "legs destroyed" };
        b.log(format!("  [Movement] {}: {} - skips movement (immobile).", nm, why));
        return;
    }
    let stuck = match &b.units[mover].stuck {
        Some(Some(s)) => Some(s.clone()),
        _ => None,
    };
    if let Some(s) = &stuck {
        if !b.units[mover].prone && s.stand_only != Some(true) {
            if hazards::can_jump_out(&b.units[mover]) && water::jump_mp(b, mover) > 0 {
                b.units[mover].jump_only = Some(true);
            } else {
                let h = b.units[mover].hex.clone().unwrap_or_default();
                b.log(format!("  [Movement] {}: stuck at {} - stays put.", nm, h));
                let (mode, fc) = (b.units[mover].move_mode.clone(), b.units[mover].move_fc);
                b.units[mover].movement_heat = heat::movement_heat(&b.units[mover], &mode, fc);
                return;
            }
        }
        if b.units[mover].prone && s.prone_stage {
            let h = b.units[mover].hex.clone().unwrap_or_default();
            b.log(format!("  [Movement] {}: stuck prone at {} - can't stand this turn.", nm, h));
            let (mode, fc) = (b.units[mover].move_mode.clone(), b.units[mover].move_fc);
            b.units[mover].movement_heat = heat::movement_heat(&b.units[mover], &mode, fc);
            return;
        }
    }
    let mut standup_mp: Option<i64> = None;
    let mut booster_failures: Vec<&'static str> = Vec::new();
    if b.units[mover].prone {
        let m = &b.units[mover];
        let tries = pr::can_stand(m) && m.pilot_hits < 5 && compute_running_mp(m) > 0;
        let remaining = b.with_piloting(mover, |b| pr::resolve_stand_up(b, mover, None));
        if tries {
            b.units[mover].move_mode = "Run".into();
        }
        if b.units[mover].prone && !b.is_destroyed(mover) && !pr::can_stand(&b.units[mover]) {
            turn_while_down(b, mover, other);
        }
        if b.units[mover].prone || b.is_destroyed(mover) {
            let h = b.units[mover].hex.clone().unwrap_or_default();
            b.log(format!("  [Movement] {}: still prone at {}.", nm, h));
            let (mode, fc) = (b.units[mover].move_mode.clone(), b.units[mover].move_fc);
            b.units[mover].movement_heat = heat::movement_heat(&b.units[mover], &mode, fc);
            pr::resolve_consciousness_checks(b, mover, "Movement Phase");
            return;
        }
        if stuck.is_some() {
            let h = b.units[mover].hex.clone().unwrap_or_default();
            b.log(format!("  [Movement] {}: stood up, still stuck at {} (TO:AR p.61).", nm, h));
            let (mode, fc) = (b.units[mover].move_mode.clone(), b.units[mover].move_fc);
            b.units[mover].movement_heat = heat::movement_heat(&b.units[mover], &mode, fc);
            pr::resolve_consciousness_checks(b, mover, "Movement Phase");
            return;
        }
        standup_mp = Some(remaining);
    } else {
        booster_failures = equip::resolve_movement_boosters(b, mover);
    }
    let (walk, run, jump) = move_budget(b, mover);
    let entry_edge: Option<Vec<String>> = if b.units[mover].hex.is_none() { b.units[mover].home_edge.clone() } else { None };
    let (pick, why, gate) = bots.choose_movement(b, mover, other, moves_first, standup_mp, entry_edge.as_deref());
    if pick.is_none() && entry_edge.is_some() {
        b.units[mover].destroyed = true;
        b.units[mover].cause_of_death = Some("Could Not Enter Battlefield".into());
        b.log(format!("  [Movement] {}: can't enter the battlefield - destroyed.", nm));
        return;
    }
    b.log(format!("  [Movement select] {}: {}", nm, why));

    let mut fell: Option<(String, String, i64, i64, &'static str)> = None;
    let mut start = String::new();
    let mut backward = false;
    if let Some(p) = &pick {
        start = if entry_edge.is_some() { "off the board".to_string() } else { format!("{} {}", b.units[mover].hex.clone().unwrap(), b.units[mover].facing) };
        backward = b.cfg.b("VERBOSE") && needs_backward_move(b, mover, p, standup_mp, entry_edge.as_deref());
        fell = walk_path(b, mover, p, standup_mp, entry_edge.as_deref(), gate);
    }
    match (&pick, &fell) {
        (Some(p), Some(f)) if f.4 != "fell" => {
            let (label, facing, used, moved, why) = f.clone();
            b.units[mover].hex = Some(label.clone());
            b.units[mover].facing = facing.clone();
            b.units[mover].move_mode = p.mode.clone();
            b.units[mover].move_fc = moved;
            b.units[mover].mp_spent = used;
            let (mode, fc) = (p.mode.clone(), moved);
            b.units[mover].movement_heat = heat::movement_heat(&b.units[mover], &mode, fc);
            b.log(format!("  [Movement] {}: {} -> {} {}, {} after {} MP ({} hexes) of a planned {} to {} {}.", nm, start, label, facing, why, used, moved, p.mode, p.hex, p.facing));
        }
        (Some(p), Some(f)) => {
            let budget = standup_mp.unwrap_or(if p.mode == "Run" { run } else { walk });
            after_fall_midmove(b, bots, mover, other, p, f, budget, moves_first, &start);
        }
        (Some(p), None) => {
            b.units[mover].hex = Some(p.hex.clone());
            b.units[mover].facing = p.facing.clone();
            b.units[mover].move_mode = p.mode.clone();
            b.units[mover].move_fc = p.fc;
            b.units[mover].mp_spent = p.mp_spent;
            let (mode, fc) = (p.mode.clone(), p.fc);
            b.units[mover].movement_heat = heat::movement_heat(&b.units[mover], &mode, fc);
            if p.charge {
                b.units[mover].charging = Some(other);
                let line = format!("  [Movement] {} declares a CHARGE against {} (stops adjacent; {} hexes counting the target's hex).", nm, name(b, other), b.units[mover].move_fc);
                b.log(line);
            }
            if p.dfa {
                b.units[mover].dfa = Some(other);
                let line = format!("  [Movement] {} declares DEATH FROM ABOVE on {} (in the air next to it; jumped {} hexes).", nm, name(b, other), b.units[mover].move_fc);
                b.log(line);
            }
            let m = &b.units[mover];
            let line = format!(
                "  [Movement] {}: {} -> {} {}, {} ({} MP, {} hexes, {} heat; budget walk {} / run {} / jump {}{}){}",
                nm,
                start,
                m.hex.clone().unwrap(),
                m.facing,
                m.move_mode,
                m.mp_spent,
                m.move_fc,
                m.movement_heat,
                walk,
                run,
                jump,
                standup_mp.map_or(String::new(), |s| format!("; stood up with {} MP left", s)),
                if backward { " - includes a backward move" } else { "" }
            );
            b.log(line);
        }
        (None, _) => {
            let (mode, fc) = (b.units[mover].move_mode.clone(), b.units[mover].move_fc);
            b.units[mover].movement_heat = heat::movement_heat(&b.units[mover], &mode, fc);
        }
    }

    if standup_mp.is_some() {
        pr::resolve_consciousness_checks(b, mover, "Movement Phase");
        return;
    }
    let mut psr_mode: Option<&str> = match b.units[mover].move_mode.as_str() {
        "Run" => Some("running"),
        "Jump" => Some("jump"),
        _ => None,
    };
    if (psr_mode == Some("running") && b.units[mover].move_fc < 1) || b.units[mover].prone {
        psr_mode = None;
    }
    if b.units[mover].charging.is_some() || b.units[mover].dfa.is_some() {
        let mode = psr_mode.map(|s| s.to_string());
        b.units[mover].deferred_end_of_move = Some(serde_json::json!({"mode": mode, "from_hex": b.units[mover].hex}));
        if let Some(pm) = psr_mode {
            if pr::movement_psr_trigger(&b.units[mover], pm).is_some() {
                let what = if b.units[mover].charging.is_some() { "charge" } else { "DFA" };
                b.log(format!("  [Movement] {}'s end-of-movement PSRs wait for the Physical Attack Phase (its movement ends with the {}, pp.78, 80).", nm, what));
            }
        }
    } else {
        if let Some(pm) = psr_mode {
            b.with_piloting(mover, |b| pr::check_movement_psr(b, mover, pm, None));
        }
        landing_psr(b, mover);
    }
    if !booster_failures.is_empty() && !b.is_destroyed(mover) {
        pr::snapshot_pre_attack_phase(&mut b.units[mover]);
        equip::apply_booster_failures(b, mover, &booster_failures);
        b.with_piloting(mover, |b| pr::resolve_attack_phase_psr(b, mover, &[]));
    }
    pr::resolve_consciousness_checks(b, mover, "Movement Phase");
}

/// Log helper: True if the picked Walk end state can only be reached with a backward move (Core p.46): it isn't among
/// the forward-only states. (Only asked with VERBOSE on.)
fn needs_backward_move(b: &Battle, mover: UnitId, pick: &Pick, standup_mp: Option<i64>, entry_edge: Option<&[String]>) -> bool {
    if pick.mode != "Walk" || standup_mp.is_some() || entry_edge.is_some() || pick.charge {
        return false;
    }
    let m = &b.units[mover];
    let (x, y) = hex_geometry::parse_hex_label(&pick.hex).unwrap();
    let facing = hex_geometry::compass_to_facing(&pick.facing).unwrap();
    let (sx, sy, start_facing) = hex_geometry::state_from_label(m.hex.as_deref().unwrap(), &m.facing).unwrap();
    let level_limit = terrain_rules::max_level_change(ground_level_limited(m), is_superheavy(m));
    let blocked = crate::ranged_combat::blocked_set(&m.blocked_hex);
    let table = b.movement_table(sx, sy, start_facing, compute_running_mp(m), None, level_limit, &blocked);
    let in_forward = table.entries.get(&(x, y, facing)).and_then(|c| c.get(&pick.mp_spent)) == Some(&pick.fc);
    !in_forward
}

/// A jump that lands in depth 1+ water forces a PSR; landing in rubble forces its +0 PSR (p.50).
fn landing_psr(b: &mut Battle, mover: UnitId) {
    if b.units[mover].prone || b.is_destroyed(mover) || b.units[mover].hex.is_none() || b.units[mover].move_mode != "Jump" {
        return;
    }
    hazards::jumped_out(b, mover);
    let hexl = b.units[mover].hex.clone().unwrap();
    if hazards::enter_hex(b, mover, &hexl, true, None, false).is_some() || b.units[mover].prone || b.is_destroyed(mover) {
        return;
    }
    let depth = water::depth_at(&b.board, Some(&hexl));
    let modifier = pr::preexisting_modifier(&b.units[mover]) + pr::special_case_modifier(&b.units[mover]) + hazards::psr_modifier(b, Some(&hexl));
    let mut checks: Vec<(String, i64)> = Vec::new();
    if depth >= 1 {
        checks.push((format!("Jumped into water (depth {})", depth), depth));
    }
    if b.board.hexes[&hexl].features.has("rubble") {
        checks.push(("Landed in rubble".to_string(), 0));
    }
    if !checks.is_empty() {
        b.with_piloting(mover, |b| {
            for (what, levels) in &checks {
                if b.units[mover].prone {
                    return;
                }
                if !pr::roll_psrs(b, 1, modifier, &format!("{} PSR", what)) {
                    pr::resolve_fall(b, mover, &format!("{}, failed PSR", what.to_lowercase()), *levels, None);
                }
            }
        });
    }
}

type Fell = (String, String, i64, i64, &'static str);

/// The movement subphase: walk the ground path to the pick hex by hex, making each terrain PSR where it happens.
/// None when the mech gets there (or no roll was needed), else (hex, facing, MP spent, hexes moved, why).
fn walk_path(b: &mut Battle, mover: UnitId, pick: &Pick, standup_mp: Option<i64>, entry_edge: Option<&[String]>, gate: PathGate) -> Option<Fell> {
    if !(pick.mode == "Walk" || pick.mode == "Run") || !terrain_rules::has_psr_terrain(&b.board) {
        return None;
    }
    if gate.psrs.unwrap_or(0) == 0 && gate.hazard.unwrap_or(0.0) == 0.0 {
        return None;
    }
    let nm = name(b, mover);
    let Some(path) = path_to(b, mover, pick, standup_mp, entry_edge) else {
        b.log(format!("  [Movement] {}: path to {} not found - moved there without terrain PSRs.", nm, pick.hex));
        return None;
    };
    let running = pick.mode == "Run";
    let base = pr::preexisting_modifier(&b.units[mover]) + pr::special_case_modifier(&b.units[mover]);
    let mut here = b.units[mover].hex.clone();
    let mut moved = 0;
    for (step, (sx, sy, sf), mp_after) in path {
        let label = hex_geometry::hex_label(sx, sy).unwrap();
        let facing = hex_geometry::facing_to_compass(sf).unwrap().to_string();
        let causes: Vec<&'static str>;
        let mut fall_at: String;
        let mut fall_dir: Option<i64>;
        if step == "turn" {
            let h = here.clone().unwrap();
            causes = if running && b.board.hexes[&h].features.has("mud") { vec!["mud"] } else { vec![] };
            fall_at = h;
            fall_dir = None;
        } else {
            let from_info = if step == "enter" { None } else { Some(b.board.hexes[here.as_deref().unwrap()].clone()) };
            causes = terrain_rules::step_psr_causes(from_info.as_ref(), &b.board.hexes[&label], step == "backward", running);
            fall_at = label.clone();
            // the way it was heading into `label` (a domino it sets off by falling there goes on that way)
            fall_dir = here.as_deref().filter(|h| b.board.hexes.contains_key(*h)).map(|h| crate::domino::combat_dir(h, &label));
            if step == "backward" {
                if let Some(f) = &from_info {
                    if f.level < b.board.hexes[&label].level {
                        fall_at = here.clone().unwrap();
                        fall_dir = None; // fell in the hex it was in: no heading (a domino goes a 1D6 way)
                    }
                }
            }
            here = Some(label.clone());
            moved += 1;
            let got = hazards::enter_hex(b, mover, &label, false, None, false);
            if got.is_some() || b.is_destroyed(mover) {
                return Some((label, facing, mp_after, moved, if b.is_destroyed(mover) { "destroyed" } else { "bogged down (stuck)" }));
            }
            if b.units[mover].prone {
                b.units[mover].hex = Some(label.clone());
                b.units[mover].facing = facing.clone();
                return Some((label, facing, mp_after, moved, "fell"));
            }
        }
        for cause in causes {
            let modifier = base + terrain_rules::psr_modifier(cause) + hazards::psr_modifier(b, Some(&fall_at));
            let ok = b.with_piloting(mover, |b| pr::roll_psrs(b, 1, modifier, &format!("[Movement] {}: {} PSR at {}", nm, cause, label)));
            if !ok {
                b.units[mover].hex = Some(fall_at.clone());
                b.units[mover].facing = facing.clone();
                let c = format!("failed {} PSR at {}", cause, fall_at);
                b.with_piloting(mover, |b| pr::resolve_fall(b, mover, &c, 0, None));
                // a hex it was passing through, with an immobile 'Mech in it (2026-11-12, domino::fell_into_occupied)
                crate::domino::fell_into_occupied(b, mover, fall_dir);
                return Some((fall_at, facing, mp_after, moved, "fell"));
            }
        }
    }
    None
}

/// A terrain PSR failed partway through the move: the mech lies where it fell with the MP it hasn't spent; it may try
/// to stand with them, and if it stands with MP to spare it picks a new spot from there - again and again.
#[allow(clippy::too_many_arguments)]
fn after_fall_midmove(b: &mut Battle, bots: &mut dyn BotSet, mover: UnitId, other: UnitId, pick: &Pick, fell: &Fell, budget: i64, moves_first: bool, start: &str) {
    let nm = name(b, mover);
    let (label, facing, used, moved, _) = fell.clone();
    b.units[mover].move_mode = pick.mode.clone();
    b.units[mover].move_fc = moved;
    b.units[mover].mp_spent = used;
    b.log(format!("  [Movement] {}: {} -> fell at {} {} after {} MP ({} hexes) of a planned {} to {} {}.", nm, start, label, facing, used, moved, pick.mode, pick.hex, pick.facing));
    while !b.is_destroyed(mover) && b.units[mover].prone {
        let remaining = budget - b.units[mover].mp_spent;
        if remaining <= 0 || !pr::can_stand(&b.units[mover]) || b.units[mover].pilot_hits >= 5 {
            break;
        }
        let left = b.with_piloting(mover, |b| pr::resolve_stand_up(b, mover, Some(remaining)));
        b.units[mover].mp_spent = if !b.units[mover].prone { budget - left } else { budget };
        if b.units[mover].prone || b.is_destroyed(mover) || left <= 0 {
            break;
        }
        let (pick2, why, gate) = bots.choose_movement(b, mover, other, moves_first, Some(left), None);
        b.log(format!("  [Movement select] {} (stood up again, {} MP left): {}", nm, left, why));
        let Some(pick2) = pick2 else { break };
        let fell2 = walk_path(b, mover, &pick2, Some(left), None, gate);
        match fell2 {
            None => {
                b.units[mover].hex = Some(pick2.hex.clone());
                b.units[mover].facing = pick2.facing.clone();
                b.units[mover].move_fc += pick2.fc;
                b.units[mover].mp_spent += pick2.mp_spent;
                break;
            }
            Some((label, facing, used2, moved2, why)) => {
                b.units[mover].move_fc += moved2;
                b.units[mover].mp_spent += used2;
                b.log(format!("  [Movement] {}: {} at {} {}.", nm, if why == "fell" { "fell again" } else { why }, label, facing));
                if why != "fell" {
                    b.units[mover].hex = Some(label);
                    b.units[mover].facing = facing;
                    break;
                }
            }
        }
    }
    let (mode, fc) = (b.units[mover].move_mode.clone(), b.units[mover].move_fc);
    b.units[mover].movement_heat = heat::movement_heat(&b.units[mover], &mode, fc);
    let m = &b.units[mover];
    let line = format!(
        "  [Movement] {}: ends at {} {}{}, {} ({} MP, {} hexes, {} heat).",
        nm,
        m.hex.clone().unwrap_or_default(),
        m.facing,
        if m.prone { " (prone)" } else { "" },
        m.move_mode,
        m.mp_spent,
        m.move_fc,
        m.movement_heat
    );
    b.log(line);
}

// ---- other phases ---------------------------------------------------------------------------------------------------
fn phase_heat(b: &mut Battle, reports: &[(UnitId, SideReport)]) {
    for u in 0..b.units.len() {
        if b.is_destroyed(u) {
            continue;
        }
        let wh = reports.iter().find(|(x, _)| *x == u).map_or(0, |(_, r)| r.weapon_heat);
        heat::resolve_heat_phase(b, u, wh);
    }
}

fn console_swap(b: &mut Battle, u: UnitId) {
    if b.is_destroyed(u) || !console_active(&b.units[u]) {
        return;
    }
    let m = &b.units[u];
    let primary_dead = m.primary_dead.unwrap_or(false);
    let pilot_out = primary_dead || m.crew["pilot"].unconscious;
    let (hits, sec) = (m.pilot_hits, m.secondary_hits.unwrap_or(0));
    let nm = name(b, u);
    if primary_dead || crate::stubs::stub_console_swap(b, &nm, hits, sec, pilot_out) {
        swap_warriors(&mut b.units[u]);
        let ph = b.units[u].pilot_hits;
        b.log(format!("  [End] {}: the pilot and the command console's warrior swap seats (pilot now {} hits, p.203).", nm, ph));
    }
}

fn phase_end(b: &mut Battle, turn: i64, stats: &mut IndexMap<String, SideStats>) {
    for u in 0..b.units.len() {
        console_swap(b, u);
        if !b.is_destroyed(u) {
            let ls = heat::has_life_support_hit(&b.units[u]);
            water::drowning(b, u, ls);
        }
        pr::resolve_end_phase_wakeup(b, u);
        heat::choose_heat_sink_deactivation(b, u, Some(turn + 1));
        equip::end_turn(b, u);
        crate::advanced_weapons::end_phase(b, u, turn);
        arcs::end_turn(&mut b.units[u]);
        let nm = name(b, u);
        if stats[&nm].crippled_at.is_none() && !b.is_destroyed(u) && is_crippled(&b.units[u]) {
            stats.get_mut(&nm).unwrap().crippled_at = Some(turn);
            b.log(format!("  [End] {} is now CRIPPLED (BattleMech Manual definition).", nm));
        }
    }
}

fn status_line(b: &mut Battle, u: UnitId) -> String {
    let mut flags: Vec<String> = Vec::new();
    let m = &b.units[u];
    if m.shutdown {
        flags.push("SHUT DOWN".into());
    }
    if m.prone {
        flags.push("PRONE".into());
    }
    if all_crew_unconscious(m) {
        flags.push("UNCONSCIOUS".into());
    }
    if b.is_destroyed(u) {
        flags.push(format!("DESTROYED ({})", b.units[u].cause_of_death.clone().unwrap_or_else(|| "None".into())));
    }
    let m = &b.units[u];
    let hp = match ar::total_hp(m) {
        crate::pyfmt::Num::I(i) => i as f64,
        crate::pyfmt::Num::F(f) => f,
    };
    format!(
        "{} @ {} {}: HP {}, pilot hits {}, engine {}, gyro {}, heat {}{}",
        m.side_name.clone().unwrap_or_default(),
        m.hex.clone().unwrap_or_else(|| "None".into()),
        m.facing,
        crate::pyfmt::py_fmt_g(hp),
        m.pilot_hits,
        m.engine_hits,
        m.gyro_hits,
        m.current_heat,
        if flags.is_empty() { String::new() } else { format!(" [{}]", flags.join(", ")) }
    )
}

// ---- deployment -------------------------------------------------------------------------------------------------------
fn edge_hexes(b: &Battle, edge: &str) -> Vec<String> {
    let (w, h) = (b.board.width, b.board.height);
    let labels: Vec<String> = if edge == "N" || edge == "S" {
        let row = if edge == "N" { 1 } else { h };
        (1..=w).map(|c| format!("{:02}{:02}", c, row)).collect()
    } else {
        let col = if edge == "W" { 1 } else { w };
        (1..=h).map(|r| format!("{:02}{:02}", col, r)).collect()
    };
    labels.into_iter().filter(|l| b.board.hexes.contains_key(l)).collect()
}

fn edges_for_teams(first_edge: &str, count: usize) -> Vec<&'static str> {
    let start = deployment::EDGE_NAMES.iter().position(|e| *e == first_edge).unwrap();
    let e = deployment::EDGE_NAMES;
    let cycle = [e[start], deployment::opposite_edge(e[start]), e[(start + 1) % 4], deployment::opposite_edge(e[(start + 1) % 4])];
    (0..count).map(|i| cycle[i % 4]).collect()
}

/// Default deployment (Core p.37): the sides roll 2D6; the loser chooses a home edge, the winner takes the opposite.
fn deploy_teams(b: &mut Battle) {
    let all: Vec<UnitId> = (0..b.units.len()).collect();
    let teams = forces::team_names(b, &all);
    let mut rolls: IndexMap<String, i64> = IndexMap::default();
    let order = forces::initiative_order(b, &teams, Some(&mut rolls));
    let choice = b.cfg.s("HOME_EDGE_CHOICE").to_string();
    let edge: &str = if choice == "random" {
        deployment::EDGE_NAMES[(b.pick_number(4) - 1) as usize]
    } else if deployment::EDGE_NAMES.contains(&choice.as_str()) {
        deployment::EDGE_NAMES.iter().find(|e| **e == choice).unwrap()
    } else {
        panic!("Unknown HOME_EDGE_CHOICE {:?}", choice);
    };
    let edges = edges_for_teams(edge, order.len());
    for (i, team) in order.iter().enumerate() {
        let e = edges[i];
        let members: Vec<UnitId> = all.iter().copied().filter(|u| b.units[*u].team.as_deref() == Some(team.as_str())).collect();
        for u in members {
            let start = deployment::start_hexes(b, u, e);
            b.units[u].home_edge = Some(start.hexes.clone());
            b.units[u].home_edge_row = Some(edge_hexes(b, e));
            b.units[u].hex = None;
            b.units[u].facing = "N".into();
            let nm = name(b, u);
            let he = start.hexes.clone();
            if start.depth == 0 && start.stuck.is_empty() && he == edge_hexes(b, e) {
                b.log(format!("  Deployment: {} home edge {} ({}-{}).", nm, e, he[0], he[he.len() - 1]));
            } else {
                let dd = b.cfg.i("DEPLOYMENT_DEPTH");
                let over = if start.depth != dd { " (stuck-terrain override)" } else { "" };
                let left = if !start.stuck.is_empty() { format!(", {} stuck hexes left out", start.stuck.len()) } else { String::new() };
                b.log(format!("  Deployment: {} home edge {}, starting up to {} hexes in{}: {} start hexes{}.", nm, e, start.depth, over, he.len(), left));
            }
        }
    }
    let parts: Vec<String> = teams.iter().map(|t| format!("{} {}", t, rolls[t])).collect();
    b.log(format!("  Deployment roll: {} - {} chose its edge.", parts.join(", "), order[0]));
}

/// Zone deployment (Combat Lab): DEPLOY_ZONES = {team: {"boxes": [9 bools], "walk_on": bool}}. A walk-on unit starts off the
/// board with the zone's border hexes as its entry hexes (as the home edge does); a placed unit starts on a free hex of the
/// zone, facing the middle of the board. The dice are drawn only for placed units (one pick each).
fn deploy_zones(b: &mut Battle) {
    let zones = b.cfg.get("DEPLOY_ZONES").clone();
    let all: Vec<UnitId> = (0..b.units.len()).collect();
    let teams = forces::team_names(b, &all);
    for team in &teams {
        let z = &zones[team.as_str()];
        let mut boxes = [true; 9];
        if let Some(arr) = z["boxes"].as_array() {
            for (i, v) in arr.iter().take(9).enumerate() {
                boxes[i] = v.as_bool().unwrap_or(false);
            }
        }
        let walk_on = z["walk_on"].as_bool().unwrap_or(true);
        let members: Vec<UnitId> = all.iter().copied().filter(|u| b.units[*u].team.as_deref() == Some(team.as_str())).collect();
        let label: String = ["NW", "N", "NE", "W", "Centre", "E", "SW", "S", "SE"].iter().enumerate().filter(|(i, _)| boxes[*i]).map(|(_, n)| *n).collect::<Vec<_>>().join("+");
        if walk_on {
            let row = deployment::zone_edge_row(b, &boxes);
            for u in members {
                let start = deployment::zone_walk_on(b, u, &boxes);
                b.units[u].home_edge = Some(start.hexes.clone());
                b.units[u].home_edge_row = Some(row.clone());
                b.units[u].hex = None;
                b.units[u].facing = "N".into();
                let nm = name(b, u);
                b.log(format!("  Deployment: {} walks on in zone {} ({} entry hexes, up to {} hexes in).", nm, label, start.hexes.len(), start.depth));
            }
        } else {
            let zone = deployment::zone_hexes(b, &boxes);
            let centre: crate::fasthash::HashSet<String> = deployment::zone_hexes(b, &[false, false, false, false, true, false, false, false, false]).into_iter().collect();
            let mut taken: Vec<String> = all.iter().filter_map(|u| b.units[*u].hex.clone()).collect();
            for u in members {
                let mut cache = Default::default();
                let mut good: Vec<String> = zone.iter().filter(|l| !taken.contains(l)
                    && terrain_rules::step_cost(None, &b.board.hexes[*l], terrain_rules::max_level_change(false, false), false).is_some()).cloned().collect();
                // keep to hexes the unit can get out of into the middle of the board; if none can, take any enterable one
                let free: Vec<String> = good.iter().filter(|l| deployment::reaches(b, u, l, &centre, &mut cache)).cloned().collect();
                if !free.is_empty() { good = free; }
                // spread out: prefer hexes not touching a hex already taken
                let spread: Vec<String> = good.iter().filter(|l| !taken.iter().any(|t| deployment::hexes_touch(l, t))).cloned().collect();
                if !spread.is_empty() { good = spread; }
                let hex = good.get((b.pick_number(good.len().max(1) as i64) - 1) as usize).cloned();
                let nm = name(b, u);
                match hex {
                    Some(h) => {
                        b.units[u].facing = deployment::facing_to_centre(b, &h).into();
                        b.units[u].hex = Some(h.clone());
                        b.units[u].home_edge = None;
                        b.units[u].home_edge_row = None;
                        taken.push(h.clone());
                        b.log(format!("  Deployment: {} placed at {} in zone {}.", nm, h, label));
                    }
                    None => panic!("deployment: no free hex in zone {} for {}", label, nm),
                }
            }
        }
    }
}

fn after_phase(b: &mut Battle) {
    for u in 0..b.units.len() {
        clubs::after_phase(b, u);
        if !b.is_destroyed(u) {
            water::auto_breaches(b, u);
        }
    }
}

// ---- one battle ---------------------------------------------------------------------------------------------------------
/// Everything a battle carries from one turn to the next beside the Battle itself.
pub struct Play {
    pub max_turns: i64,
    pub result: BattleResult,
    pub team_list: Vec<String>,
    pub unit_stats: IndexMap<String, SideStats>,
    pub turn: i64,
    pub over: bool,
}

/// movement_selection.effective_hp: armor + rear armor + MOVEMENT_STRUCTURE_WEIGHT x structure.
pub fn effective_hp(b: &Battle, u: UnitId) -> f64 {
    let k = b.cfg.f("MOVEMENT_STRUCTURE_WEIGHT");
    let f = |n: crate::pyfmt::Num| match n {
        crate::pyfmt::Num::I(i) => i as f64,
        crate::pyfmt::Num::F(x) => x,
    };
    let mut sum = 0.0;
    for v in b.units[u].locations.values() {
        if !v.destroyed {
            sum += f(v.armor) + f(v.rear_armor.unwrap_or(crate::pyfmt::Num::I(0))) + k * f(v.structure);
        }
    }
    sum
}

pub fn start_battle(b: &mut Battle, max_turns: i64, marks: Marks) -> Play {
    b.limbs_on_ground.clear();
    b.smoky.clear();
    if b.cfg.has("DEPLOY_ZONES") {
        deploy_zones(b);
    } else if b.cfg.s("DEPLOYMENT") == "home_edge" {
        deploy_teams(b);
    } else if b.cfg.s("DEPLOYMENT") != "fixed_hexes" {
        panic!("Unknown DEPLOYMENT");
    }
    for u in 0..b.units.len() {
        b.units[u].hp_log = Some(vec![]);
        let hp = effective_hp(b, u);
        b.units[u].hp_log.as_mut().unwrap().push(hp);
    }
    marks(b, 0, "Deployment");
    let all: Vec<UnitId> = (0..b.units.len()).collect();
    let team_list = forces::team_names(b, &all);
    let mut unit_stats = IndexMap::default();
    for u in 0..b.units.len() {
        let m = &b.units[u];
        let hp = match ar::total_hp(m) {
            crate::pyfmt::Num::I(i) => i as f64,
            crate::pyfmt::Num::F(f) => f,
        };
        let mut st = SideStats::new(format!("{} ({} {})", m.side_name.clone().unwrap_or_default(), m.chassis, m.model), hp);
        let num = |n: crate::pyfmt::Num| match n { crate::pyfmt::Num::I(i) => i as f64, crate::pyfmt::Num::F(f) => f };
        for (loc, v) in m.locations.iter() {
            let (a, s) = (num(v.armor + v.rear_armor.unwrap_or(crate::pyfmt::Num::I(0))), num(v.structure));
            st.max_armor += a;
            st.max_structure += s;
            st.locations.insert(loc.to_string(), [a, a, s, s]);
        }
        // every weapon appears in the tallies from the start, so one that never fired shows as zero
        let mut zero: IndexMap<String, [f64; 4]> = IndexMap::default();
        for w in crate::damage_resolution::get_weapons(m) {
            zero.entry(m.items[w].name.clone()).or_insert([0.0; 4]);
        }
        st.weapons = zero;
        unit_stats.insert(m.side_name.clone().unwrap_or_default(), st);
    }
    Play { max_turns, result: BattleResult::new(Some(max_turns)), team_list, unit_stats, turn: 0, over: false }
}

pub fn play_on(b: &mut Battle, bots: &mut dyn BotSet, play: &mut Play, marks: Marks) {
    while !play.over && play.turn < play.max_turns {
        let turn = play.turn + 1;
        play.over = play_turn(b, bots, play, turn, marks);
        play.turn = turn;
    }
    finish(b, play);
}

fn log_initiative(b: &mut Battle, order: &[String]) {
    if order.len() == 2 {
        b.log(format!("  Initiative: {} lost the roll, moves first.", order[0]));
    } else {
        b.log(format!("  Initiative order (acts first to last): {}.", order.join(", ")));
    }
}

/// One turn, Initiative to End Phase. True = the battle is over.
fn play_turn(b: &mut Battle, bots: &mut dyn BotSet, play: &mut Play, turn: i64, marks: Marks) -> bool {
    b.tally.fit(b.units.len());
    for u in 0..b.units.len() {
        if !b.is_destroyed(u) {
            b.tally.alive[u] += 1;
        }
    }
    b.log(format!("\n=== TURN {} ===", turn));
    let alive = forces::standing(b);
    for u in 0..b.units.len() {
        pr::snapshot_preexisting_damage(&mut b.units[u]);
        equip::start_turn(b, u, turn);
    }
    let alive_teams = forces::team_names(b, &alive);
    let order = forces::initiative_order(b, &alive_teams, None);
    log_initiative(b, &order);
    let in_order: Vec<UnitId> = order.iter().flat_map(|t| alive.iter().copied().filter(|m| b.units[*m].team.as_deref() == Some(t.as_str())).collect::<Vec<_>>()).collect();

    for u in 0..b.units.len() {
        reset_movement_state(&mut b.units[u]);
        b.units[u].moved_this_turn = false;
    }
    for &m in &in_order {
        fire_modes::declare_unjams(b, m);
    }
    bots.start_movement(b);
    // the movement phase: MOVE_ORDER "index" (forces.movement_order; "tiered" is Gladiator's, stage 8)
    assert!(b.cfg.s("MOVE_ORDER") == "index", "MOVE_ORDER other than 'index' needs the tiers module (stage 8)");
    let mut act = forces::Activation::new(b, &order, forces::can_select_move);
    loop {
        let mut pick = |b: &mut Battle, c: &[UnitId]| -> UnitId {
            if let Some(u) = bots.move_pick(b, c) {
                return u;
            }
            let mut best = c[0];
            let mut best_v = forces::move_index(b, best);
            for &u in &c[1..] {
                let v = forces::move_index(b, u);
                if v > best_v {
                    best = u;
                    best_v = v;
                }
            }
            best
        };
        let Some(mover) = act.next(b, &mut pick) else { break };
        // THE MOVE QUEUE (session 25, Hydra's S5a): who moves after this unit, from a copy of the activation state and
        // the same pick rule. Pure: the pick only reads positions, and the copy is thrown away.
        b.move_queue = {
            let mut ahead = act.clone();
            let mut queue = Vec::new();
            while let Some(u) = ahead.next(b, &mut pick) {
                queue.push(u);
            }
            queue
        };
        let foe = bots.choose_foe(b, mover).expect("a foe to plan against");
        let moves_first = !b.units[foe].moved_this_turn;
        let start_hex = b.units[mover].hex.clone();
        phase_movement(b, bots, mover, foe, turn, moves_first);
        b.units[mover].moved_this_turn = true;
        bots.unit_moved(b, mover, start_hex.as_deref());
        let label = format!("{} moves", name(b, mover));
        marks(b, turn, &label);
    }

    b.move_queue.clear();
    bots.end_movement(b);
    if (0..b.units.len()).any(|u| b.units[u].hex.is_none()) && forces::teams_standing(b).len() < 2 {
        play.result.turns_taken = turn;
        conclude(b, play);
        let text = over_text(&play.result);
        b.log(format!("\n>>> Battle over on turn {}: {} (couldn't enter the battlefield). <<<", turn, text));
        return true;
    }

    after_phase(b);
    let mut fighters = forces::fire_order(b, &order, &mut |_b, c| c[0]);
    {
        let mut target_of = |b: &mut Battle, u: UnitId| forces::choose_target(b, u, true, false);
        tag::designation_units(b, &fighters, &mut target_of);
    }
    if bots.fire_pick_active(b) {
        let mut pick = |b: &mut Battle, c: &[UnitId]| bots.fire_pick(b, c);
        fighters = forces::fire_order(b, &order, &mut pick);
    }
    let mut reports = {
        let mut adapter = RangedAdapter { bots };
        ar::run_ranged_phase(b, &fighters, &mut adapter)
    };
    after_phase(b);
    marks(b, turn, "Ranged attacks");
    for (i, &u) in fighters.iter().enumerate() {
        let s = play.unit_stats.get_mut(&name(b, u)).unwrap();
        s.attacks += reports[i].attacks;
        s.hits += reports[i].hits;
        s.damage_dealt += reports[i].damage_dealt;
    }

    let scrappers = forces::fire_order(b, &order, &mut |_b, c| c[0]);
    // reports parallel to `scrappers`: the physical phase reads each unit's ranged report (weapons fired, heat)
    let mut phys_reports: Vec<SideReport> = scrappers.iter().map(|u| fighters.iter().position(|f| f == u).map_or_else(SideReport::default, |i| std::mem::take(&mut reports[i]))).collect();
    {
        let mut adapter = PhysAdapter { bots };
        crate::physical::run_physical_units(b, &scrappers, &mut phys_reports, &mut adapter);
    }
    after_phase(b);
    marks(b, turn, "Physical attacks");
    let heat_reports: Vec<(UnitId, SideReport)> = scrappers.iter().copied().zip(phys_reports).collect();
    phase_heat(b, &heat_reports);
    after_phase(b);
    bots.end_of_turn(b);
    phase_end(b, turn, &mut play.unit_stats);
    smoke::end_phase(b, turn);

    for u in 0..b.units.len() {
        let line = format!("  -- end of turn {}: {}", turn, status_line(b, u));
        b.log(line);
    }
    for u in 0..b.units.len() {
        let hp = effective_hp(b, u);
        b.units[u].hp_log.get_or_insert_with(Vec::new).push(hp);
    }
    marks(b, turn, "Heat and end phase");

    play.result.turns_taken = turn;
    if forces::teams_standing(b).len() < 2 {
        conclude(b, play);
        let text = over_text(&play.result);
        b.log(format!("\n>>> Battle over on turn {}: {}. <<<", turn, text));
        return true;
    }
    false
}

fn finish(b: &mut Battle, play: &mut Play) {
    for u in 0..b.units.len() {
        let nm = name(b, u);
        let destroyed = b.is_destroyed(u);
        let hp = match ar::total_hp(&b.units[u]) {
            crate::pyfmt::Num::I(i) => i as f64,
            crate::pyfmt::Num::F(f) => f,
        };
        let (mut armor, mut structure) = (0.0, 0.0);
        let num = |n: crate::pyfmt::Num| match n { crate::pyfmt::Num::I(i) => i as f64, crate::pyfmt::Num::F(f) => f };
        let mut locs: IndexMap<String, [f64; 4]> = IndexMap::default();
        for (loc, v) in b.units[u].locations.iter() {
            let a = num(v.armor + v.rear_armor.unwrap_or(crate::pyfmt::Num::I(0)));
            let st = num(v.structure);
            armor += a;
            structure += st;
            locs.insert(loc.to_string(), [a, 0.0, st, 0.0]);
        }
        b.tally.fit(b.units.len());
        let s = play.unit_stats.get_mut(&nm).unwrap();
        for (loc, now) in locs.iter() {
            let at_start = s.locations.get(loc).copied().unwrap_or([0.0; 4]);
            s.locations.insert(loc.clone(), [now[0], at_start[1], now[2], at_start[3]]);
        }
        s.final_armor = armor;
        s.final_structure = structure;
        s.kills = b.tally.kills[u];
        s.turns_alive = b.tally.alive[u];
        for (w, v) in b.tally.weapons[u].iter() {
            s.weapons.insert(w.clone(), [v[0], v[1], v[2], v[3]]);
        }
        s.final_hp = hp;
        s.destroyed = destroyed;
        s.units_lost = if destroyed { 1 } else { 0 };
        s.cause_of_death = if destroyed { b.units[u].cause_of_death.clone() } else { None };
        s.final_hex = b.units[u].hex.clone();
    }
    play.result.units = play.unit_stats.clone();
    let mut teams = IndexMap::default();
    for t in &play.team_list {
        let members: Vec<SideStats> = (0..b.units.len()).filter(|u| b.units[*u].team.as_deref() == Some(t.as_str())).map(|u| play.unit_stats[&name(b, u)].clone()).collect();
        teams.insert(t.clone(), team_totals(t, &members));
    }
    play.result.teams = teams;
}

/// Who won: the one team left standing, else a draw.
fn conclude(b: &mut Battle, play: &mut Play) {
    let left = forces::teams_standing(b);
    let gone: Vec<String> = play.team_list.iter().filter(|t| !left.contains(t)).cloned().collect();
    let tl = &play.team_list;
    let two = tl.len() == 2 && tl.contains(&"Red".to_string()) && tl.contains(&"Blue".to_string());
    play.result.destroyed = Some(if two {
        if gone.len() == 2 { "Both".to_string() } else { gone[0].clone() }
    } else if left.is_empty() {
        "All".to_string()
    } else {
        gone.join("+")
    });
    play.result.winner = if left.len() == 1 { left[0].clone() } else { "Draw".to_string() };
}

fn over_text(r: &BattleResult) -> String {
    let d = r.destroyed.clone().unwrap_or_default();
    if r.winner != "Draw" {
        if d == "Red" || d == "Blue" { format!("{} destroyed", d) } else { format!("{} wins ({} destroyed)", r.winner, d) }
    } else if d == "Both" {
        "Both destroyed".to_string()
    } else {
        "everyone destroyed".to_string()
    }
}
