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
use crate::ranged_combat::{path_to, path_to_with_start, Pick};
use crate::results::{team_totals, BattleResult, SideStats};
use crate::terrain_rules;
use crate::{arcs, clubs, deployment, fire_modes, hazards, heat, smoke, tag, water};

/// The bots' choices (INTEGRATION__bots), one method per decision kind of the seam.
pub trait BotSet {
    /// The unit a meddle names for `phase` ("fire" / "phys"): its declaration comes first (human_bots.rs, timeline.rs). Default: none.
    fn declare_first(&self, _b: &Battle, _phase: &str) -> Option<UnitId> {
        None
    }
    fn choose_foe(&mut self, b: &mut Battle, mover: UnitId) -> Option<UnitId>;
    /// bots.choose_target: the one enemy a unit fires at in the Ranged phase
    fn choose_target(&mut self, b: &mut Battle, attacker: UnitId) -> Option<UnitId>;
    /// A person's further targets after the primary (split fire, p.64): None = not asked (a bot); see `RangedBot::next_secondary`.
    fn next_secondary(&mut self, _b: &mut Battle, _attacker: UnitId, _primary: UnitId, _done: &[UnitId]) -> Option<Option<UnitId>> {
        None
    }
    /// bots.fire_pick active? (Gladiator's firing order); then `fire_pick` chooses among the candidates
    fn fire_pick_active(&mut self, b: &mut Battle) -> bool;
    fn fire_pick(&mut self, b: &mut Battle, candidates: &[UnitId]) -> UnitId;
    /// Which of a side's units moves next, when the side's bot chooses (Hydra's S3); None = the engine's move index.
    /// Must only read the battle: it also forecasts the move queue.
    fn move_pick(&mut self, _b: &mut Battle, _candidates: &[UnitId]) -> Option<UnitId> {
        None
    }
    /// The same pick while the turn loop only FORECASTS the move queue (nothing is decided): a person is not asked. Default: as
    /// `move_pick`.
    fn move_pick_forecast(&mut self, b: &mut Battle, candidates: &[UnitId]) -> Option<UnitId> {
        self.move_pick(b, candidates)
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
    /// T16: the End Phase's heat-equipment review of the Princess-family units (MegaMek BotHeatEquipmentManager); runs before
    /// `end_of_turn`, as BotClient does. Default: nothing (Gladiator / Hydra units are never managed).
    fn manage_heat_equipment(&mut self, _b: &mut Battle) {}
    /// Spotting for indirect fire at the start of the Ranged Attack Phase: (target, it also fires) or None (spotting.rs).
    fn choose_spot(&mut self, b: &mut Battle, u: UnitId) -> Option<(UnitId, bool)> {
        crate::stubs::stub_spot(b, u)
    }
    fn assign_damage(&mut self, _b: &mut Battle, _attacker: UnitId, _target: UnitId, _dmg: f64) {}
    /// BattleROM: a unit is about to move (before it stands up, before MASC / a supercharger is rolled): a person's
    /// controller records the switches it sets here (player_choices.rs). Default: nothing.
    fn before_move(&mut self, _b: &mut Battle, _mover: UnitId) {}
    /// BattleROM: may a prone unit that can stand try to? A person may leave it prone. Default: yes (the engine always tried).
    /// Does the MechWarrior eject this Movement Phase instead of moving (TO:AR p.164-165)? Only a person is asked (their movement
    /// answer); bots never eject. Not a bot decision for the bridge.
    fn eject(&mut self, _b: &mut Battle, _mover: UnitId) -> bool {
        false
    }
    /// After a completed ground move (not a jump, charge or DFA): does the unit drop to the ground (Core p.51, 1 MP)? Only a
    /// person is asked (engine pass, 2026-11-24); bots keep standing. Not a bot decision for the bridge.
    fn drop_prone(&mut self, _b: &mut Battle, _mover: UnitId) -> bool {
        false
    }
    /// A unit that chose to stay prone may still change facing, 1 MP a hexside (Core p.51): the facing it turns to (compass), or None
    /// to stay as it lies. Asked only after `wants_stand_up` said no; the bots always try to stand, so only a person is asked
    /// (engine pass, 2026-11-24). Like `wants_stand_up`, not a bot decision: the bridge does not record it.
    fn prone_turn(&mut self, _b: &mut Battle, _mover: UnitId) -> Option<String> {
        None
    }
    fn wants_stand_up(&mut self, _b: &mut Battle, _mover: UnitId) -> bool {
        true
    }
    /// After a FAILED attempt to stand, or a fall partway through a move: does the player decide again (Daniel, 2026-11-26,
    /// INTEGRATION__UI_SYNC.md Section 14 G3: "Inform the player of the failure and consequences, and then allow them to plan what remains
    /// of their move from that state"; Core p.51: repeated attempts while the MP last)? Then each attempt is ONE roll and `wants_stand_up`
    /// is asked again with the MP left. Default: no, the engine tries again by itself (the bots). Not a bot decision for the bridge.
    fn decides_each_stand(&mut self, _b: &mut Battle, _mover: UnitId) -> bool {
        false
    }
    /// A unit that is going to stand: does it stand CAREFULLY (TO:AR p.22: one attempt, the whole Movement Phase, walked, -2 with more
    /// than 2 Walking MP)? Asked only after `wants_stand_up` said yes; only a person is asked, bots stand the normal way (2 MP).
    fn careful_stand(&mut self, _b: &mut Battle, _mover: UnitId) -> bool {
        false
    }
    /// BattleROM: the Heat Phase is about to start for this unit; `weapon_heat` is what its weapons added this turn. A
    /// person's controller sets coolant pod / radical heat sink / heat sink / Blue Shield / unjam switches here.
    fn end_phase(&mut self, _b: &mut Battle, _u: UnitId, _weapon_heat: i64) {}
    /// BattleROM: TAG designation before the Ranged Attack Phase (Core p.200). None = not a person's unit (the stubs decide);
    /// Some(None) = does not designate; Some(Some((target, "mech" | "hex"))) = designates.
    fn choose_tag(&mut self, _b: &mut Battle, _attacker: UnitId, _candidates: &[crate::tag::TagCandidate]) -> Option<Option<(UnitId, &'static str)>> {
        None
    }
}

/// mover.path_psrs[pick] / mover.path_hazard[pick] as the search left them.
#[derive(Clone, Copy, Debug, Default)]
pub struct PathGate {
    pub psrs: Option<i64>,
    pub hazard: Option<f64>,
}

struct RangedAdapter<'a, 'm> {
    bots: &'a mut dyn BotSet,
    marks: &'a mut (dyn FnMut(&mut Battle, i64, &str) + 'm),
    turn: i64,
}

impl RangedBot for RangedAdapter<'_, '_> {
    fn reset_assigned(&mut self, b: &mut Battle) {
        self.bots.reset_assigned(b);
    }
    fn declare_first(&self, b: &Battle) -> Option<UnitId> {
        self.bots.declare_first(b, "fire")
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
    fn choose_spot(&mut self, b: &mut Battle, u: UnitId) -> Option<(UnitId, bool)> {
        self.bots.choose_spot(b, u)
    }
    fn next_secondary(&mut self, b: &mut Battle, attacker: UnitId, primary: UnitId, done: &[UnitId]) -> Option<Option<UnitId>> {
        self.bots.next_secondary(b, attacker, primary, done)
    }
    fn step_done(&mut self, b: &mut Battle, label: &str) {
        (self.marks)(b, self.turn, label);
    }
}

struct PhysAdapter<'a, 'm> {
    bots: &'a mut dyn BotSet,
    marks: &'a mut (dyn FnMut(&mut Battle, i64, &str) + 'm),
    turn: i64,
}

impl PhysicalBot for PhysAdapter<'_, '_> {
    fn declare_first(&self, b: &Battle) -> Option<UnitId> {
        self.bots.declare_first(b, "phys")
    }
    fn target_of(&mut self, b: &mut Battle, attacker: UnitId) -> Option<UnitId> {
        // declared = getattr(u, "charging", None) or getattr(u, "dfa", None); the attack the unit declared in Movement
        let declared = b.units[attacker].charging.or(b.units[attacker].dfa);
        declared.or_else(|| forces::choose_target(b, attacker, true, true))
    }
    fn choose_physical(&mut self, b: &mut Battle, attacker: UnitId, target: UnitId) -> Option<(i64, Vec<PhysOption>, ArcAction)> {
        self.bots.choose_physical(b, attacker, target)
    }
    fn step_done(&mut self, b: &mut Battle, label: &str) {
        (self.marks)(b, self.turn, label);
    }
}

/// The test hook at `replay.mark(turn, label)`: called with the battle state at the end of each marked phase.
pub type Marks<'a> = &'a mut dyn FnMut(&mut Battle, i64, &str);

fn name(b: &Battle, u: UnitId) -> String {
    b.units[u].side_name.clone().unwrap_or_default()
}

pub fn reset_movement_state(m: &mut Mech) {
    equip::reset_movement_boost(m);
    m.jump_boosters_on = false;
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
/// The facing a prone 'Mech that cannot stand turns to on the ground, and how many hexsides (Core: one a turn with a destroyed
/// gyro, else up to its walking MP, at most 3): toward the foe's forward arc, then any side arc. None = no turn worth making.
/// Shared by the Movement Phase and the MegaMek bridge (session 30).
pub fn turn_while_down_choice(b: &Battle, mover: UnitId, other: UnitId) -> Option<(i64, i64, [i64; 6])> {
    if b.units[other].hex.is_none() || b.units[mover].hex.is_none() {
        return None;
    }
    let walk = compute_walk_mp(&b.units[mover]);
    let max_turns = walk.min(if gyro_destroyed(&b.units[mover]) { 1 } else { 3 });
    if max_turns < 1 {
        return None;
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
    (best_turns > 0).then_some((best, best_turns, seen_as))
}

/// What turning to `to` while prone costs (1 MP a hexside, the short way round; p.51), and whether the unit has the MP: (hexsides,
/// mode) where the mode is Walk if it fits the walking MP, else Run (a prone 'Mech declares walk or run first, p.51). None: no
/// such facing, no turn needed, or not enough MP.
pub fn prone_turn_cost(m: &crate::mech_state::Mech, to: &str) -> Option<(i64, &'static str)> {
    let (from, to) = (hex_geometry::compass_to_facing(&m.facing).ok()?, hex_geometry::compass_to_facing(to).ok()?);
    let d = (to - from).rem_euclid(6);
    let sides = d.min(6 - d);
    let walk = compute_walk_mp(m);
    if sides == 0 || sides > prone_mp_left(m) {
        return None;
    }
    // after a failed stand or a fall the mode is already declared (p.51); before anything, Walk if the turn fits the walking MP
    if m.mp_spent > 0 && m.move_mode != "Stand Still" {
        return Some((sides, if m.move_mode == "Walk" { "Walk" } else { "Run" }));
    }
    Some((sides, if sides <= walk { "Walk" } else { "Run" }))
}

/// The MP a prone unit has left this Movement Phase: its running MP before it has done anything; after a failed attempt to stand, or a fall
/// partway through a move, what its declared mode leaves (G3).
pub fn prone_mp_left(m: &crate::mech_state::Mech) -> i64 {
    let budget = match m.move_mode.as_str() {
        "Walk" => compute_walk_mp(m),
        "Jump" => 0,
        _ => crate::mech_state::compute_running_mp(m),
    };
    (budget - m.mp_spent).max(0)
}

/// Can `m` drop to the ground now, and in what mode: it has 1 MP left (walking if its move fits, else running) and did not jump.
pub fn drop_cost(m: &crate::mech_state::Mech) -> Option<&'static str> {
    if m.prone || m.move_mode == "Jump" {
        return None;
    }
    let (walk, run) = (compute_walk_mp(m), crate::mech_state::compute_running_mp(m));
    let mp = m.mp_spent + 1;
    if mp <= walk && m.move_mode != "Run" {
        Some("Walk")
    } else if mp <= run {
        Some("Run")
    } else {
        None
    }
}

/// EJECTION (TO:AR p.164-165; engine pass 2026-11-24, a person's choice in the Movement Phase instead of moving). The MechWarrior
/// lands in the hex behind the 'Mech and makes a piloting roll modified by that hex's terrain (clear -2, water -1, rough / rubble
/// 0, light woods +2, heavy +3, ultra +4, +1 a building level), +5 for a prone 'Mech, +3 for an unconscious pilot and +1 a point of
/// head internal structure lost; a failure costs hits equal to the margin of failure halved (rounded down). The engine has no
/// infantry, so the MechWarrior on foot is not played on; the abandoned 'Mech leaves the battle. Planetary conditions are not modelled.
fn eject_pilot(b: &mut Battle, mover: UnitId) {
    let nm = name(b, mover);
    let m = &b.units[mover];
    let here = m.hex.clone().unwrap_or_default();
    let behind_dir = (hex_geometry::compass_to_facing(&m.facing).unwrap_or(0) + 3).rem_euclid(6);
    let landing = crate::movement_attacks::neighbour(&here, behind_dir).filter(|h| b.board.hexes.contains_key(h)).unwrap_or(here.clone());
    let info = &b.board.hexes[&landing];
    let woods = crate::los::woods_density(info);
    let terrain = if info.building {
        (info.level - info.ground_level.unwrap_or(info.level)).max(1)
    } else if let Some(d) = woods.as_deref() {
        match d { "1" => 2, "2" => 3, _ => 4 }
    } else if info.depth.unwrap_or(0) > 0 {
        -1
    } else if info.features.has("rough") || info.features.has("rubble") {
        0
    } else {
        -2
    };
    let prone = if m.prone { 5 } else { 0 };
    let out = if crate::mech_state::pilot_unconscious(m) { 3 } else { 0 };
    let head_lost = m.locations.get("Head").map_or(0, |v| (m.max_structure.get("Head").copied().unwrap_or(0) - v.structure.as_int()).max(0));
    let tn = m.piloting + terrain + prone + out + head_lost;
    let roll = b.roll_2d6();
    let mut line = format!("  [Movement] {}: the MechWarrior EJECTS (TO:AR p.164) and lands in {}: needs {} (piloting {} + landing {:+} + prone {} + unconscious {} + head damage {}), rolled {}", nm, landing, tn, b.units[mover].piloting, terrain, prone, out, head_lost, roll);
    if roll < tn {
        let hits = (tn - roll) / 2;
        if hits > 0 {
            crate::mech_state::pilot_hit(&mut b.units[mover], hits, false);
            b.pilot_hit_ev(mover, "hard landing");
        }
        line += &format!(" - a hard landing: {} hit(s).", hits);
    } else {
        line += " - lands safely.";
    }
    b.log(line);
    b.units[mover].destroyed = true;
    b.units[mover].cause_of_death = Some("Abandoned (the MechWarrior ejected)".into());
    let line = format!("  [Movement] {}: abandoned - out of the battle (the MechWarrior on foot is not played on).", nm);
    b.log(line);
}

/// The unit drops to the ground (p.51): 1 MP, no falling damage, the same facing, prone from now on.
fn drop_to_ground(b: &mut Battle, mover: UnitId) {
    let Some(mode) = drop_cost(&b.units[mover]) else {
        let line = format!("  [Movement] {}: no MP left to drop to the ground (1 MP, p.51).", name(b, mover));
        b.log(line);
        return;
    };
    let m = &mut b.units[mover];
    m.prone = true;
    m.mp_spent += 1;
    m.move_mode = mode.into();
    let (md, fc) = (m.move_mode.clone(), m.move_fc);
    m.movement_heat = heat::movement_heat(m, &md, fc);
    let line = format!("  [Movement] {}: drops to the ground at {} facing {} ({} MP in all, {}; p.51) - prone.", name(b, mover), b.units[mover].hex.clone().unwrap_or_default(), b.units[mover].facing, b.units[mover].mp_spent, mode);
    b.log(line);
}

/// A PERSON'S STAND (Daniel, 2026-11-26; INTEGRATION__UI_SYNC.md Section 14 G3): one attempt; a failure is reported (the log says the roll and
/// the fall) and, while the 'Mech still has the 2 MP an attempt costs (Core p.51), its player is asked again: stand again, or stay prone and
/// perhaps turn on the ground with the MP left. `wants_stand_up` was already answered yes for the first attempt; when `mp` is given (a fall
/// partway through a move) the player is asked first. Returns the running MP left after standing (0 while prone).
fn stand_deciding(b: &mut Battle, bots: &mut dyn BotSet, mover: UnitId, mp: Option<i64>) -> i64 {
    let nm = name(b, mover);
    if mp.is_some() && !bots.wants_stand_up(b, mover) {
        if let Some(to) = bots.prone_turn(b, mover) {
            prone_turn(b, mover, &to);
        }
        return 0;
    }
    let mut avail = mp.unwrap_or_else(|| crate::mech_state::compute_running_mp(&b.units[mover]));
    loop {
        let (left, stood) = b.with_piloting(mover, |b| pr::resolve_stand_attempt(b, mover, Some(avail)));
        if stood || b.is_destroyed(mover) {
            return left;
        }
        // the attempt cost 2 MP; a 'Mech that tries to stand at the start of its move runs (p.51). The MP spent are set so that the MP
        // left to the declared mode (prone_mp_left, which the next question offers) are exactly those the attempts leave.
        if mp.is_none() {
            b.units[mover].move_mode = "Run".into();
        }
        let budget = prone_mp_left(&b.units[mover]) + b.units[mover].mp_spent;
        b.units[mover].mp_spent = (budget - left).max(0);
        if left < 2 || !pr::can_stand(&b.units[mover]) || b.units[mover].pilot_hits >= 5 {
            return 0;
        }
        b.log(format!("  [Movement] {}: did not stand, {} MP left: its player decides again (p.51).", nm, left));
        if !bots.wants_stand_up(b, mover) {
            if let Some(to) = bots.prone_turn(b, mover) {
                prone_turn(b, mover, &to);
            }
            return 0;
        }
        avail = left;
    }
}

/// A person's unit that stays prone turns to `to` (p.51).
fn prone_turn(b: &mut Battle, mover: UnitId, to: &str) {
    let Some((sides, mode)) = prone_turn_cost(&b.units[mover], to) else { return };
    b.units[mover].facing = to.to_string();
    b.units[mover].move_mode = mode.into();
    b.units[mover].mp_spent += sides;
    let line = format!("  [Movement] {}: turns {} hexside(s) on the ground to face {} ({}, {} MP; p.51).", name(b, mover), sides, to, mode, sides);
    b.log(line);
}

fn turn_while_down(b: &mut Battle, mover: UnitId, other: UnitId) {
    let Some((best, best_turns, seen_as)) = turn_while_down_choice(b, mover, other) else { return };
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

/// Runs `f` with `mover`'s movement context set the way `phase_movement` sets it (the mobile enemies' hexes closed to its
/// ground moves, the occupied hexes), then cleared. BattleROM uses it to show what a unit that has not moved yet could do.
pub fn with_move_context<R>(b: &mut Battle, mover: UnitId, f: impl FnOnce(&mut Battle) -> R) -> R {
    let blocked: Vec<serde_json::Value> = forces::blocked_xy(b, mover).into_iter().map(|(x, y)| serde_json::json!([x, y])).collect();
    b.units[mover].blocked_hex = Some(serde_json::Value::Array(blocked));
    let occ = forces::occupied_labels(b, mover);
    b.units[mover].other_unit_hexes = Some(serde_json::json!(occ));
    let r = f(b);
    b.units[mover].blocked_hex = Some(serde_json::Value::Null);
    b.units[mover].other_unit_hexes = Some(serde_json::Value::Null);
    r
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
    bots.before_move(b, mover);
    let mut standup_mp: Option<i64> = None;
    let mut booster_failures: Vec<&'static str> = Vec::new();
    if b.units[mover].prone {
        let m = &b.units[mover];
        let tries = pr::can_stand(m) && m.pilot_hits < 5 && compute_running_mp(m) > 0;
        // BattleROM: a person may leave the unit prone (a bot always tries)
        let stays = tries && !bots.wants_stand_up(b, mover);
        if stays {
            b.log(format!("  [Movement] {}: stays prone (chosen).", nm));
            if let Some(to) = bots.prone_turn(b, mover) {
                prone_turn(b, mover, &to);
            }
        }
        // careful stand (TO:AR p.22): a person may spend the whole phase on one better-odds attempt; the unit counts as having walked
        let careful = tries && !stays && bots.careful_stand(b, mover);
        let remaining = if stays {
            0
        } else if careful {
            // one attempt, no MP left either way (a failed roll is a fall, and `prone` stays set for the checks below)
            b.with_piloting(mover, |b| pr::resolve_careful_stand(b, mover));
            0
        } else if bots.decides_each_stand(b, mover) {
            stand_deciding(b, bots, mover, None)
        } else {
            b.with_piloting(mover, |b| pr::resolve_stand_up(b, mover, None))
        };
        let tries = tries && !stays;
        if tries {
            b.units[mover].move_mode = if careful { "Walk" } else { "Run" }.into();
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
    if let Some(p) = &pick {
        b.ev("MOVE_CHOSEN").unit(mover).sub(&p.mode.to_lowercase()).what(&p.hex).n(p.mp_spent).emit(b);
    }
    let from_hex = b.units[mover].hex.clone();
    // the route, for the MOVE_PATH event: found BEFORE the unit moves (the search starts from where it stands) and only when events are on
    let route = if b.ev("MOVE_PATH").live() { move_route(b, mover, pick.as_ref(), standup_mp, entry_edge.as_deref()) } else { None };

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
            b.ev("MOVE").unit(mover).sub(&p.mode.to_lowercase()).what(&label).n(used).emit(b);
            emit_move_path(b, mover, &p.mode, route, Some((&label, used)));
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
            let (hexl, mp) = (b.units[mover].hex.clone().unwrap_or_default(), b.units[mover].mp_spent);
            b.ev("MOVE").unit(mover).sub(&p.mode.to_lowercase()).what(&hexl).n(mp).emit(b);
            emit_move_path(b, mover, &p.mode, route, None);
        }
        (None, _) => {
            let (mode, fc) = (b.units[mover].move_mode.clone(), b.units[mover].move_fc);
            b.units[mover].movement_heat = heat::movement_heat(&b.units[mover], &mode, fc);
        }
    }
    move_terrain_events(b, mover, from_hex.as_deref());

    // EJECTION (TO:AR p.164-165): the person chose to eject instead of moving (the unit stood still)
    if bots.eject(b, mover) {
        eject_pilot(b, mover);
        return;
    }
    // DROPPING TO THE GROUND (Core p.51): after a finished ground move, if not jumping this turn; 1 MP, no damage, same facing
    if matches!((&pick, &fell), (Some(p), None) if !p.charge && !p.dfa && p.mode != "Jump") && standup_mp.is_none() && bots.drop_prone(b, mover) {
        drop_to_ground(b, mover);
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
    let level_limit = crate::mech_state::ground_limit(m);
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
/// The route of a picked ground move as MOVE_PATH text (`step_walk::route_text`), or None: no pick, a jump (no route: it goes to its
/// end hex), a charge (its pick counts the target's hex too), no route found, or no step to take. Reads only.
fn move_route(b: &Battle, mover: UnitId, pick: Option<&Pick>, standup_mp: Option<i64>, entry_edge: Option<&[String]>) -> Option<String> {
    let p = pick?;
    if p.mode == "Jump" || p.charge || p.dfa {
        return None;
    }
    let text = if let (Some(steps), None, None) = (&p.route, standup_mp, entry_edge) {
        // the route the person drew: the steps it carries
        let uw = crate::drawn_route::UnitWalk::of(b, mover)?;
        crate::step_walk::route_text(&crate::drawn_route::path_of_steps(b, &uw, steps)?, uw.start.2)
    } else if entry_edge.is_some() {
        crate::step_walk::route_text(&path_to(b, mover, p, standup_mp, entry_edge)?, 0)
    } else {
        let (start_facing, path) = path_to_with_start(b, mover, p, standup_mp)?;
        crate::step_walk::route_text(&path, start_facing)
    };
    (!text.is_empty()).then_some(text)
}

/// MOVE_PATH, written right after the MOVE it belongs to. `stopped`: the hex and MP where the unit actually ended when it did not
/// finish the planned route (bogged down, destroyed by a hazard): the route is cut there, and left out if it never passes through that
/// hex at that cost (never a wrong route).
fn emit_move_path(b: &mut Battle, mover: UnitId, mode: &str, route: Option<String>, stopped: Option<(&str, i64)>) {
    let Some(text) = route else { return };
    let mut steps: Vec<&str> = text.split(' ').collect();
    if let Some((hex, mp)) = stopped {
        let Some(at) = steps.iter().position(|s| {
            let mut f = s.split('/');
            f.next() == Some(hex) && f.nth(1).and_then(|m| m.parse::<i64>().ok()) == Some(mp)
        }) else {
            return;
        };
        steps.truncate(at + 1);
    }
    b.ev("MOVE_PATH").unit(mover).sub(&mode.to_lowercase()).what(&steps.join(" ")).n(steps.len() as i64).emit(b);
}

/// WATER_ENTER / BUILDING_ENTER / BUILDING_LEAVE, from where the move began and where it ended (events.rs; a hex passed through
/// is not seen: only the two ends of the move are compared).
fn move_terrain_events(b: &mut Battle, mover: UnitId, from: Option<&str>) {
    if !b.ev("MOVE").live() {
        return;
    }
    let (Some(from), Some(to)) = (from, b.units[mover].hex.clone()) else { return };
    if from == to || !b.board.hexes.contains_key(from) || !b.board.hexes.contains_key(&to) {
        return;
    }
    let (d0, d1) = (water::depth_at(&b.board, Some(from)), water::depth_at(&b.board, Some(&to)));
    let (b0, b1) = (b.board.hexes[from].building, b.board.hexes[&to].building);
    if d1 > 0 && d0 == 0 {
        b.ev("WATER_ENTER").unit(mover).n(d1).what(&to).emit(b);
    }
    if b1 && !b0 {
        b.ev("BUILDING_ENTER").unit(mover).what(&to).emit(b);
    }
    if b0 && !b1 {
        b.ev("BUILDING_LEAVE").unit(mover).what(from).emit(b);
    }
}

/// None when the mech gets there (or no roll was needed), else (hex, facing, MP spent, hexes moved, why).
fn walk_path(b: &mut Battle, mover: UnitId, pick: &Pick, standup_mp: Option<i64>, entry_edge: Option<&[String]>, gate: PathGate) -> Option<Fell> {
    if !(pick.mode == "Walk" || pick.mode == "Run") || !terrain_rules::has_psr_terrain(&b.board) {
        return None;
    }
    if gate.psrs.unwrap_or(0) == 0 && gate.hazard.unwrap_or(0.0) == 0.0 {
        return None;
    }
    let nm = name(b, mover);
    // a route drawn by a person is walked exactly as drawn (drawn_route.rs); any other pick takes the search's best route to its end state
    let found = match (&pick.route, standup_mp, entry_edge) {
        (Some(steps), None, None) => crate::drawn_route::UnitWalk::of(b, mover).and_then(|uw| crate::drawn_route::path_of_steps(b, &uw, steps)),
        _ => path_to(b, mover, pick, standup_mp, entry_edge),
    };
    let Some(path) = found else {
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
            // a lateral shift is a step into that hex (the rear ones backward moves, Core pp.236, 238)
            let step_back = step == "backward" || step.ends_with("_back");
            causes = terrain_rules::step_psr_causes(from_info.as_ref(), &b.board.hexes[&label], step_back, running);
            fall_at = label.clone();
            // the way it was heading into `label` (a domino it sets off by falling there goes on that way)
            fall_dir = here.as_deref().filter(|h| b.board.hexes.contains_key(*h)).map(|h| crate::domino::combat_dir(h, &label));
            if step_back {
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
    let person = bots.decides_each_stand(b, mover);
    while !b.is_destroyed(mover) && b.units[mover].prone {
        let remaining = budget - b.units[mover].mp_spent;
        if remaining <= 0 || !pr::can_stand(&b.units[mover]) || b.units[mover].pilot_hits >= 5 {
            break;
        }
        let left = if person {
            // a person's unit: the fall is reported and its player decides whether to stand (G3)
            b.log(format!("  [Movement] {}: fell, {} MP left: its player decides (p.51).", nm, remaining));
            let l = stand_deciding(b, bots, mover, Some(remaining));
            if b.units[mover].prone {
                break;
            }
            l
        } else {
            b.with_piloting(mover, |b| pr::resolve_stand_up(b, mover, Some(remaining)))
        };
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
fn phase_heat(b: &mut Battle, bots: &mut dyn BotSet, reports: &[(UnitId, SideReport)]) {
    for u in 0..b.units.len() {
        if b.is_destroyed(u) {
            continue;
        }
        let wh = reports.iter().find(|(x, _)| *x == u).map_or(0, |(_, r)| r.weapon_heat);
        bots.end_phase(b, u, wh);
        heat::resolve_heat_phase(b, u, wh);
        if b.ev("HEAT_LEVEL").live() {
            let h = b.units[u].current_heat;
            let bracket = crate::events::HEAT_BRACKETS.iter().rev().find(|t| **t <= h).copied().unwrap_or(0);
            b.ev("HEAT_LEVEL").unit(u).n(h).sub(&bracket.to_string()).emit(b);
        }
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

/// BattleROM: asked where a unit stands when its turn to place comes (the unit, the free hexes it may take); `Some((hex, facing))`
/// is a person's choice, `None` leaves the placement to the engine. Bot battles pass a hook that always says None.
pub type DeployHook<'a> = &'a mut dyn FnMut(&mut Battle, UnitId, &[String]) -> Option<(String, String)>;

/// Default deployment (Core p.37): the sides roll 2D6; the loser chooses a home edge, the winner takes the opposite.
fn deploy_teams(b: &mut Battle, deploy: DeployHook) {
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
    // Placed (the default, Daniel 2026-11-19: "that formation logic is supposed to be standard kit") or walking on (Core p.37 as
    // written; DEPLOYMENT_PLACED false). Placed units stand in hexes of their home-edge row (up to DEPLOYMENT_DEPTH in) before turn 1,
    // taking turns as MegaMek's players do (place_in_turns); a unit with no free hex still walks on.
    let placed_mode = !b.cfg.has("DEPLOYMENT_PLACED") || b.cfg.b("DEPLOYMENT_PLACED");
    let mut zones = serde_json::Map::new();
    for (i, team) in order.iter().enumerate() {
        zones.insert(team.clone(), serde_json::json!({"boxes": edge_boxes(edges[i]).to_vec()}));
    }
    let zones = serde_json::Value::Object(zones);
    let mut parts: Vec<Placing> = Vec::new();
    for (i, team) in order.iter().enumerate() {
        let members: Vec<UnitId> = all.iter().copied().filter(|u| b.units[*u].team.as_deref() == Some(team.as_str())).collect();
        if placed_mode {
            let enemy_zone = crate::princess_deploy::enemy_zone_centre(b, &zones, team);
            parts.push(Placing { members, boxes: edge_boxes(edges[i]), spots: Spots::Edge(edges[i]), label: String::new(), enemy_zone, clusters: Default::default() });
            continue;
        }
        for u in members {
            walk_on_edge(b, u, edges[i], true);
        }
    }
    if placed_mode {
        for (i, u) in place_in_turns(b, parts, deploy) {
            let nm = name(b, u);
            b.log(format!("  Deployment: {} has no free hex on its home edge and walks on.", nm));
            walk_on_edge(b, u, edges[i], false);
        }
    }
    let parts: Vec<String> = teams.iter().map(|t| format!("{} {}", t, rolls[t])).collect();
    b.log(format!("  Deployment roll: {} - {} chose its edge.", parts.join(", "), order[0]));
}

/// Core p.37 walk-on for one unit: it will enter along `e` during its Movement Phase (hex None). `log_edge` writes the
/// "home edge" line (place_in_turns writes its own for a placed unit).
fn walk_on_edge(b: &mut Battle, u: UnitId, e: &str, log_edge: bool) {
    let start = deployment::start_hexes(b, u, e);
    if log_edge {
        log_home_edge(b, u, e, &start);
    }
    b.units[u].home_edge = Some(start.hexes.clone());
    b.units[u].home_edge_row = Some(edge_hexes(b, e));
    b.units[u].hex = None;
    b.units[u].facing = "N".into();
}

fn log_home_edge(b: &mut Battle, u: UnitId, e: &str, start: &deployment::StartHexes) {
    let nm = name(b, u);
    let he = &start.hexes;
    if start.depth == 0 && start.stuck.is_empty() && *he == edge_hexes(b, e) {
        b.log(format!("  Deployment: {} home edge {} ({}-{}).", nm, e, he[0], he[he.len() - 1]));
    } else {
        let dd = b.cfg.i("DEPLOYMENT_DEPTH");
        let over = if start.depth != dd { " (stuck-terrain override)" } else { "" };
        let left = if !start.stuck.is_empty() { format!(", {} stuck hexes left out", start.stuck.len()) } else { String::new() };
        b.log(format!("  Deployment: {} home edge {}, starting up to {} hexes in{}: {} start hexes{}.", nm, e, start.depth, over, he.len(), left));
    }
}

/// Where a team's placed units may stand: the hexes of a deployment zone, or its home edge's row.
enum Spots {
    Zone(Vec<String>),
    Edge(&'static str),
}

/// One team waiting to place its units (place_in_turns).
struct Placing {
    members: Vec<UnitId>,
    boxes: [bool; 9],
    spots: Spots,
    label: String,
    enemy_zone: Option<(i64, i64)>,
    /// Princess and CASPAR build the team's board-area maps once
    clusters: crate::princess_deploy::Clusters,
}

/// MegaMek's start of the game (Daniel, 2026-11-19: "Players take turns putting their units on the board within the starting
/// zone limits. Once all units are placed, the game actually starts"): the teams place one unit at a time, in `parts` order (the
/// deployment roll's loser first), a team with more units taking proportionally more turns (its units / the smallest team's, as
/// MegaMek's even turn order spreads them), each seeing the units already on the board. Returns (index in `parts`, unit) for
/// every unit that found no free hex.
fn place_in_turns(b: &mut Battle, mut parts: Vec<Placing>, deploy: DeployHook) -> Vec<(usize, UnitId)> {
    let centre: crate::fasthash::HashSet<String> = deployment::zone_hexes(b, &[false, false, false, false, true, false, false, false, false]).into_iter().collect();
    let mut taken: Vec<String> = (0..b.units.len()).filter_map(|u| b.units[u].hex.clone()).collect();
    let smallest = parts.iter().map(|p| p.members.len()).filter(|n| *n > 0).min().unwrap_or(1);
    let per_round: Vec<usize> = parts.iter().map(|p| (p.members.len() / smallest).max(1)).collect();
    let mut next = vec![0usize; parts.len()];
    let mut unplaced = Vec::new();
    loop {
        let mut any = false;
        for i in 0..parts.len() {
            for _ in 0..per_round[i] {
                if next[i] >= parts[i].members.len() {
                    break;
                }
                any = true;
                let u = parts[i].members[next[i]];
                next[i] += 1;
                let nm = name(b, u);
                let good: Vec<String> = match &parts[i].spots {
                    Spots::Zone(zone) => zone.iter().filter(|l| !taken.contains(l)
                        && terrain_rules::step_cost(None, &b.board.hexes[*l], terrain_rules::max_level_change(false, false), false).is_some()).cloned().collect(),
                    Spots::Edge(e) => {
                        let start = deployment::start_hexes(b, u, e);
                        log_home_edge(b, u, e, &start);
                        start.hexes.iter().filter(|l| !taken.contains(l)).cloned().collect()
                    }
                };
                let (boxes, enemy_zone) = (parts[i].boxes, parts[i].enemy_zone);
                // a person's unit is placed where they say (among `good`); everyone else by the engine
                let chosen = if good.is_empty() { None } else { deploy(b, u, &good) };
                let placed = match chosen {
                    Some((h, f)) => Some((h, f, String::new())),
                    None => place_unit(b, u, good, &boxes, enemy_zone, &mut parts[i].clusters, &centre, &taken),
                };
                match placed {
                    Some((h, facing, note)) => {
                        b.units[u].facing = facing;
                        b.units[u].hex = Some(h.clone());
                        b.units[u].home_edge = None;
                        b.units[u].home_edge_row = None;
                        taken.push(h.clone());
                        let place = if parts[i].label.is_empty() { String::new() } else { format!(" in zone {}", parts[i].label) };
                        if note.is_empty() {
                            b.log(format!("  Deployment: {} placed at {}{}.", nm, h, place));
                        } else {
                            b.log(format!("  Deployment: {} placed at {} facing {}{}{}.", nm, h, b.units[u].facing, place, note));
                        }
                    }
                    None => unplaced.push((i, u)),
                }
            }
        }
        if !any {
            return unplaced;
        }
    }
}

/// Where one PLACED unit stands and faces, out of `good` (the free hexes it may take). Princess and CASPAR choose as MegaMek's
/// bots do (princess_deploy: fitness, hazard scan, room to move, formation, facing); everyone else keeps the shared placement:
/// hexes it can get out of into the middle of the board (`centre`), not touching a hex already taken, picked by the dice, facing
/// the middle. Returns (hex, facing, log note), None when `good` is empty. Used by zone deployment (`deploy_zones`) and by the
/// default home-edge deployment (`deploy_teams`, Daniel 2026-11-19: the formation logic is standard kit).
fn place_unit(b: &mut Battle, u: UnitId, mut good: Vec<String>, boxes: &[bool; 9], enemy_zone: Option<(i64, i64)>,
              clusters: &mut crate::princess_deploy::Clusters, centre: &crate::fasthash::HashSet<String>, taken: &[String]) -> Option<(String, String, String)> {
    if b.units[u].is_princess_family() {
        return crate::princess_deploy::choose(b, u, good, boxes, enemy_zone, clusters).map(|p| (p.hex, p.facing.to_string(), format!(" ({})", p.note)));
    }
    let mut cache = Default::default();
    // keep to hexes the unit can get out of into the middle of the board; if none can, take any enterable one
    let free: Vec<String> = good.iter().filter(|l| deployment::reaches(b, u, l, centre, &mut cache)).cloned().collect();
    if !free.is_empty() { good = free; }
    // spread out: prefer hexes not touching a hex already taken
    let spread: Vec<String> = good.iter().filter(|l| !taken.iter().any(|t| deployment::hexes_touch(l, t))).cloned().collect();
    if !spread.is_empty() { good = spread; }
    let hex = good.get((b.pick_number(good.len().max(1) as i64) - 1) as usize).cloned();
    hex.map(|h| { let f = deployment::facing_to_centre(b, &h).to_string(); (h, f, String::new()) })
}

/// The 3 x 3 zone boxes that make up a home edge (N: the top row of boxes ... W: the left column), what the Princess deployment
/// reads to know which side of the board a team stands on.
fn edge_boxes(edge: &str) -> [bool; 9] {
    let on: [usize; 3] = match edge { "N" => [0, 1, 2], "S" => [6, 7, 8], "W" => [0, 3, 6], _ => [2, 5, 8] };
    let mut boxes = [false; 9];
    for i in on { boxes[i] = true; }
    boxes
}

/// Zone deployment (Combat Lab): DEPLOY_ZONES = {team: {"boxes": [9 bools], "walk_on": bool}}. A walk-on unit starts off the
/// board with the zone's border hexes as its entry hexes (as the home edge does); a placed unit starts on a free hex of the
/// zone, facing the middle of the board. The dice are drawn only for placed units (one pick each).
fn deploy_zones(b: &mut Battle, deploy: DeployHook) {
    let zones = b.cfg.get("DEPLOY_ZONES").clone();
    let all: Vec<UnitId> = (0..b.units.len()).collect();
    let teams = forces::team_names(b, &all);
    let mut parts: Vec<(String, Placing)> = Vec::new();
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
            let enemy_zone = crate::princess_deploy::enemy_zone_centre(b, &zones, team);
            parts.push((team.clone(), Placing { members, boxes, spots: Spots::Zone(deployment::zone_hexes(b, &boxes)), label, enemy_zone, clusters: Default::default() }));
        }
    }
    if parts.is_empty() {
        return;
    }
    // the teams that place take turns, the deployment roll's loser first (a lone team needs no roll)
    if parts.len() > 1 {
        let names: Vec<String> = parts.iter().map(|(t, _)| t.clone()).collect();
        let mut rolls: IndexMap<String, i64> = IndexMap::default();
        let order = forces::initiative_order(b, &names, Some(&mut rolls));
        let shown: Vec<String> = names.iter().map(|t| format!("{} {}", t, rolls[t])).collect();
        b.log(format!("  Deployment roll: {} - {} places first.", shown.join(", "), order[0]));
        parts.sort_by_key(|(t, _)| order.iter().position(|o| o == t).unwrap());
    }
    let labels: Vec<String> = parts.iter().map(|(_, p)| p.label.clone()).collect();
    let unplaced = place_in_turns(b, parts.into_iter().map(|(_, p)| p).collect(), deploy);
    if let Some((i, u)) = unplaced.first() {
        let nm = name(b, *u);
        panic!("deployment: no free hex in zone {} for {}", labels[*i], nm);
    }
}

fn after_phase(b: &mut Battle) {
    for u in 0..b.units.len() {
        clubs::after_phase(b, u);
        if !b.is_destroyed(u) {
            water::auto_breaches(b, u);
        }
    }
    b.sweep_destroyed();
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
    start_battle_with(b, max_turns, marks, &mut |_, _, _| None)
}

/// `start_battle` with a hook that may place a person's units (BattleROM); see `DeployHook`.
pub fn start_battle_with(b: &mut Battle, max_turns: i64, marks: Marks, deploy: DeployHook) -> Play {
    b.limbs_on_ground.clear();
    b.smoky.clear();
    crate::ammo::narc_homing_for_force(b);
    crate::c3::check_networks(b);
    if b.cfg.has("DEPLOY_ZONES") {
        deploy_zones(b, deploy);
    } else if b.cfg.s("DEPLOYMENT") == "home_edge" {
        deploy_teams(b, deploy);
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
            let (f, r, s) = (num(v.armor), num(v.rear_armor.unwrap_or(crate::pyfmt::Num::I(0))), num(v.structure));
            st.max_armor += f + r;
            st.max_structure += s;
            st.locations.insert(loc.to_string(), [f, f, s, s, r, r]);
        }
        // every critical slot by name, all working at the start (the end of the battle marks the lost ones)
        for loc in m.locations.keys() {
            if m.crits.contains_key(loc.as_str()) {
                let names = crate::mech_state::display_crits(m, loc);
                st.crit_alive.insert(loc.to_string(), vec![true; names.len()]);
                st.crit_names.insert(loc.to_string(), names);
            }
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

/// The turn's Initiative line, with the dice (Daniel, 2026-11-24: "The dice rolls to determine initiative every turn should be
/// shown"; a known change from the answer key, whose test `stage6_battles.rs` was removed 2026-11-24): each team's 2D6, then any tie re-rolls (p.39).
fn log_initiative(b: &mut Battle, order: &[String]) {
    let text = |round: &Vec<(String, i64)>| round.iter().map(|(t, v)| format!("{} {}", t, v)).collect::<Vec<_>>().join(", ");
    let dice = match b.initiative_throws.split_first() {
        Some((first, rest)) => format!(" (rolled {}{})", text(first), rest.iter().map(|r| format!("; tie re-rolled {}", text(r))).collect::<String>()),
        None => String::new(),
    };
    if b.ev("INITIATIVE_ROLL").live() {
        let throws = b.initiative_throws.clone();
        for (i, round) in throws.iter().enumerate() {
            for (team, v) in round {
                b.ev("INITIATIVE_ROLL").sub(team).roll(*v).n(i as i64 + 1).emit(b);
            }
        }
    }
    if order.len() == 2 {
        b.log(format!("  Initiative: {} lost the roll, moves first{}.", order[0], dice));
    } else {
        b.log(format!("  Initiative order (acts first to last): {}{}.", order.join(", "), dice));
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
    b.event_phase(turn, "initiative");
    let alive = forces::standing(b);
    for u in 0..b.units.len() {
        pr::snapshot_preexisting_damage(&mut b.units[u]);
        equip::start_turn(b, u, turn);
    }
    let alive_teams = forces::team_names(b, &alive);
    let order = forces::initiative_order(b, &alive_teams, None);
    log_initiative(b, &order);
    // a replay step of its own (REC layer): a cut at the turn's first move must come AFTER the Initiative throw, or a new seed would throw it again
    if b.log.ev.on {
        b.step_info = Some(serde_json::json!({"k": "init"}));
    }
    marks(b, turn, "Initiative");
    b.event_phase(turn, "movement");
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
            let mut forecast = |b: &mut Battle, c: &[UnitId]| -> UnitId {
                if let Some(u) = bots.move_pick_forecast(b, c) {
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
            while let Some(u) = ahead.next(b, &mut forecast) {
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
        // statistics only: how far the unit went this turn (straight-line hexes from where it started)
        if let (Some(a), Some(z)) = (start_hex.as_deref().and_then(|h| hex_geometry::parse_hex_label(h).ok()), forces::hex_xy(b, mover)) {
            b.tally.fit(b.units.len());
            b.tally.track[mover][0] += crate::los::hex_distance(a, z) as f64;
            b.tally.track[mover][1] += 1.0;
        }
        let label = format!("{} moves", name(b, mover));
        if b.log.ev.on {
            b.step_info = Some(serde_json::json!({"k": "move", "unit": mover}));
        }
        marks(b, turn, &label);
    }

    b.move_queue.clear();
    bots.end_movement(b);
    // statistics only: spacing once everyone has moved (nearest enemy; mean distance to living allies)
    {
        b.tally.fit(b.units.len());
        let on_board: Vec<UnitId> = (0..b.units.len()).filter(|&u| !b.is_destroyed(u) && b.units[u].hex.is_some()).collect();
        for &u in &on_board {
            let team = b.units[u].team.clone();
            let (mut near, mut ally_sum, mut allies) = (i64::MAX, 0i64, 0i64);
            for &o in &on_board {
                if o == u { continue; }
                let Some(d) = forces::distance(b, u, o) else { continue };
                if b.units[o].team != team { near = near.min(d); } else { ally_sum += d; allies += 1; }
            }
            let t = &mut b.tally.track[u];
            if near != i64::MAX { t[2] += near as f64; t[3] += 1.0; }
            if allies > 0 { t[6] += ally_sum as f64 / allies as f64; t[7] += 1.0; }
        }
    }
    if (0..b.units.len()).any(|u| b.units[u].hex.is_none()) && forces::teams_standing(b).len() < 2 {
        play.result.turns_taken = turn;
        conclude(b, play);
        let text = over_text(&play.result);
        b.log(format!("\n>>> Battle over on turn {}: {} (couldn't enter the battlefield). <<<", turn, text));
        return true;
    }

    after_phase(b);
    b.event_phase(turn, "ranged");
    let mut fighters = forces::fire_order(b, &order, &mut |_b, c| c[0]);
    {
        let mut target_of = |b: &mut Battle, u: UnitId| forces::choose_target(b, u, true, false);
        let mut chosen = |b: &mut Battle, u: UnitId, c: &[tag::TagCandidate]| bots.choose_tag(b, u, c);
        tag::designation_units(b, &fighters, &mut target_of, &mut chosen);
    }
    if bots.fire_pick_active(b) {
        let mut pick = |b: &mut Battle, c: &[UnitId]| bots.fire_pick(b, c);
        fighters = forces::fire_order(b, &order, &mut pick);
    }
    let mut reports = {
        let mut adapter = RangedAdapter { bots, marks: &mut *marks, turn };
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

    b.event_phase(turn, "physical");
    let scrappers = forces::fire_order(b, &order, &mut |_b, c| c[0]);
    // reports parallel to `scrappers`: the physical phase reads each unit's ranged report (weapons fired, heat)
    let mut phys_reports: Vec<SideReport> = scrappers.iter().map(|u| fighters.iter().position(|f| f == u).map_or_else(SideReport::default, |i| std::mem::take(&mut reports[i]))).collect();
    {
        let mut adapter = PhysAdapter { bots, marks: &mut *marks, turn };
        crate::physical::run_physical_units(b, &scrappers, &mut phys_reports, &mut adapter);
    }
    after_phase(b);
    marks(b, turn, "Physical attacks");
    b.event_phase(turn, "heat");
    let heat_reports: Vec<(UnitId, SideReport)> = scrappers.iter().copied().zip(phys_reports).collect();
    phase_heat(b, bots, &heat_reports);
    after_phase(b);
    bots.manage_heat_equipment(b);
    bots.end_of_turn(b);
    b.event_phase(turn, "end");
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
        let mut locs: IndexMap<String, [f64; 6]> = IndexMap::default();
        for (loc, v) in b.units[u].locations.iter() {
            let (f, r) = (num(v.armor), num(v.rear_armor.unwrap_or(crate::pyfmt::Num::I(0))));
            let st = num(v.structure);
            armor += f + r;
            structure += st;
            locs.insert(loc.to_string(), [f, 0.0, st, 0.0, r, 0.0]);
        }
        b.tally.fit(b.units.len());
        let s = play.unit_stats.get_mut(&nm).unwrap();
        for (loc, now) in locs.iter() {
            let at_start = s.locations.get(loc).copied().unwrap_or([0.0; 6]);
            s.locations.insert(loc.clone(), [now[0], at_start[1], now[2], at_start[3], now[4], at_start[5]]);
        }
        // which critical slots still work: a slot the game turned into "DESTROYED" is lost (a whole location's when it goes)
        for (loc, slots) in b.units[u].crits.iter() {
            if let Some(alive) = s.crit_alive.get_mut(loc.as_str()) {
                for (i, slot) in slots.iter().enumerate() {
                    if i < alive.len() && slot.is_name("DESTROYED") { alive[i] = false; }
                }
            }
        }
        s.track = b.tally.track[u];
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
