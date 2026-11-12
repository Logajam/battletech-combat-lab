//! MegaMek bridge, stage B1 (INTEGRATION__MEGAMEK_BRIDGE.md; Daniel, 2026-11-12: "Bridge that allows our bots to connect
//! to a live Megamek game"). Our bots deciding from SNAPSHOTS of a battle instead of from inside one of our own battles.
//!
//! THE IDEA. A decision process (`Session`, `btsim decide`) stays alive for a whole game and keeps its own `Battle`. It is
//! sent one JSON line per thing the engine would tell or ask the bots (the `BotSet` calls): the signals (a Movement Phase
//! starts, a unit moved, the turn ended, damage was declared at a target) and the decisions (which unit moves next, where
//! it moves, which enemy to fire at). Every line carries the battle's state at that moment (`state_json`): the units, the
//! turn, the board's changes, the dice. The session puts that state into its battle, then makes the same `BotSet` call
//! the engine would have. So the bots' memories (Legate's plans, Princess's heat map, Hydra's waits and fire plan) build
//! up in the session exactly as they do in a battle, and the only thing sent is what a game shows: where everything is.
//!
//! THE CHECK (`Recorder` with a session). An ordinary battle is played with a `Recorder` around the bots: every call
//! becomes a line, with the state before the call and the answer the bots gave, and a fresh `Session` running alongside
//! is handed each line as it is made and must give the same answer to every decision. Checking as the battle goes keeps
//! nothing in memory (a 12 v 12 battle's lines, every unit's full state at every call, ran out of memory when kept).
//! Run by `btsim SCENARIO --bridge-parity`; `parity` does the same for lines kept in a file.
//!
//! COVERED: every signal and every decision - move order, movement, the enemy a unit plans against (`choose_foe`), the
//! Ranged phase's target and firing order, the weapon declaration (`choose_declaration`: the session works out the
//! attack's inputs itself from the state, with `prepare_declaration` as the engine does) and the physical attack.
//! `records_declared_damage` is a read-only question asked inside the declaration; it is not a line of its own.
//! The answers of the two attack decisions are this check's own form (`decl_json`, `phys_json`); the wire form the
//! Java side reads (weapons by location and slot) is stage B4's.
use serde_json::{json, Value};

use crate::attack_resolution::{prepare_declaration, DeclChoice, DeclCtx, Prep};
use crate::battle::{Battle, Dice, UnitId};
use crate::board_parser::Board;
use crate::config::Config;
use crate::dice::PcgDice;
use crate::fire_modes::Planner;
use crate::gladiator_bots::GladiatorBots;
use crate::mech_state::{ArcAction, Mech};
use crate::orchestrator::{BotSet, PathGate};
use crate::physical::PhysOption;
use crate::ranged_combat::Pick;

// =============================================================================================================
// The state that goes with every line
// =============================================================================================================

/// The name a unit goes by on the wire: its side name ("Red", "Blue 2"...), the name its scenario gave it.
fn unit_name(b: &Battle, i: usize) -> String {
    b.units[i].side_name.clone().unwrap_or_else(|| format!("unit {}", i))
}

/// The battle's state now: every unit's full dump, the turn, the board's changes (smoke, broken magma crust, severed
/// limbs on the ground), the move order still to come, and the dice's place in their stream. The board itself is sent
/// only when it changed since `last_board` (the first line always has it).
pub fn state_json(b: &Battle, last_board: &mut Option<String>) -> Value {
    let name = |i: usize| unit_name(b, i);
    let units: Vec<Value> = b.units.iter().map(|m| m.to_json(&name)).collect();
    let mut v = json!({
        "turn": b.turn,
        "units": units,
        "smoky": b.smoky.iter().collect::<Vec<_>>(),
        "broken_crust": b.broken_crust,
        "limbs_on_ground": b.limbs_on_ground.iter().map(|(k, n)| json!([k, n])).collect::<Vec<_>>(),
        "move_queue": b.move_queue,
        "hazards_in_phase": b.hazards_in_phase,
        "piloting": b.piloting,
    });
    if let Some(d) = b.dice.borrow().save() {
        v["dice"] = d;
    }
    let board = b.board.to_json().to_string();
    if last_board.as_deref() != Some(board.as_str()) {
        v["board"] = serde_json::from_str(&board).unwrap();
        *last_board = Some(board);
    }
    v
}

/// Puts a `state_json` into a battle. The units are rebuilt from their dumps; a new board drops the remembered lines of
/// sight and movement tables (they rebuild to the same values).
pub fn load_state(b: &mut Battle, v: &Value) {
    let names: Vec<String> = (0..b.units.len()).map(|i| unit_name(b, i)).collect();
    let index = |n: &str| names.iter().position(|x| x == n).unwrap_or_else(|| panic!("bridge state: no unit {}", n));
    let units = v["units"].as_array().expect("bridge state: units");
    assert_eq!(units.len(), b.units.len(), "bridge state: the roster changed size");
    b.units = units.iter().map(|u| Mech::from_json(u, &index)).collect();
    b.turn = v["turn"].as_i64().unwrap();
    b.smoky = v["smoky"].as_array().unwrap().iter().map(|h| h.as_str().unwrap().to_string()).collect();
    b.broken_crust = v["broken_crust"].as_array().unwrap().iter().map(|h| h.as_str().unwrap().to_string()).collect();
    b.limbs_on_ground = v["limbs_on_ground"].as_array().unwrap().iter().map(|p| (p[0].as_str().unwrap().to_string(), p[1].as_i64().unwrap())).collect();
    b.move_queue = v["move_queue"].as_array().unwrap().iter().map(|u| u.as_u64().unwrap() as UnitId).collect();
    b.hazards_in_phase = v["hazards_in_phase"].as_bool().unwrap();
    b.piloting = v["piloting"].as_i64().unwrap();
    if let Some(d) = v.get("dice") {
        *b.dice.borrow_mut() = Box::new(PcgDice::restore(d));
    }
    if let Some(board) = v.get("board") {
        b.board = Board::from_json(board);
        b.board_changed();
    }
}

// =============================================================================================================
// Answers on the wire
// =============================================================================================================

fn pick_json(p: &Pick) -> Value {
    json!({"hex": p.hex, "facing": p.facing, "mode": p.mode, "fc": p.fc, "mp_spent": p.mp_spent, "charge": p.charge, "dfa": p.dfa})
}

fn action_json(a: &ArcAction) -> Value {
    json!({"twist": a.twist, "flip": a.flip, "turret": a.turret.as_ref().map(|t| t.to_json())})
}

/// An item of a unit by its ADDRESS, "location#first slot" (e.g. "RT#3"): fixed when the battle starts and the same in
/// every dump, unlike its number in the unit's equipment list, which a unit rebuilt from its dump may renumber. It is
/// also how the Java side finds the weapon in MegaMek (spec Section 5). An item with no address (none in a 'Mech's
/// critical slots) goes by its name and number.
fn item_name(b: &Battle, u: UnitId, id: usize) -> String {
    let it = &b.units[u].items[id];
    it.addr.clone().unwrap_or_else(|| format!("{} (item {})", it.name, id))
}

/// A weapon declaration: the weapons (by address), the expected damage and heat, the torso twist / arm flip / turret,
/// the physical attack planned alongside, the weapons held back for it.
fn decl_json(b: &Battle, attacker: UnitId, c: &DeclChoice) -> Value {
    let weapons: Vec<String> = c.weapons.iter().map(|w| item_name(b, attacker, *w)).collect();
    let mut held: Vec<String> = c.held.iter().map(|w| item_name(b, attacker, *w)).collect();
    held.sort();
    json!({"weapons": weapons, "exp_dmg": c.exp_dmg, "weapon_heat": c.weapon_heat, "key_torso_arc": c.key_torso_arc,
           "action": action_json(&c.action), "phys_names": c.phys_names, "phys_value": c.phys_value, "held": held})
}

/// A physical attack: (the to-hit number, the attacks chosen, the twist / flip it needs), or null for none.
fn phys_json(p: &Option<(i64, Vec<PhysOption>, ArcAction)>) -> Value {
    match p {
        None => Value::Null,
        Some((tn, opts, act)) => json!({"tn": tn, "attacks": opts.iter().map(|o| format!("{:?}", o)).collect::<Vec<_>>(), "action": action_json(act)}),
    }
}

fn gate_json(g: &PathGate) -> Value {
    json!({"psrs": g.psrs, "hazard": g.hazard})
}

fn unit_list(v: &Value) -> Vec<UnitId> {
    v.as_array().unwrap().iter().map(|u| u.as_u64().unwrap() as UnitId).collect()
}

fn opt_unit(v: &Value) -> Option<UnitId> {
    v.as_u64().map(|u| u as UnitId)
}

/// Makes the `BotSet` call a line names, on a battle already holding that line's state; returns the answer as JSON
/// (null for a signal).
fn call(b: &mut Battle, bots: &mut dyn BotSet, method: &str, a: &Value) -> Value {
    match method {
        "start_movement" => {
            bots.start_movement(b);
            Value::Null
        }
        "end_movement" => {
            bots.end_movement(b);
            Value::Null
        }
        "end_of_turn" => {
            bots.end_of_turn(b);
            Value::Null
        }
        "reset_assigned" => {
            bots.reset_assigned(b);
            Value::Null
        }
        "unit_moved" => {
            bots.unit_moved(b, a["mover"].as_u64().unwrap() as UnitId, a["start_hex"].as_str());
            Value::Null
        }
        "assign_damage" => {
            bots.assign_damage(b, a["attacker"].as_u64().unwrap() as UnitId, a["target"].as_u64().unwrap() as UnitId, a["dmg"].as_f64().unwrap());
            Value::Null
        }
        "move_pick" => json!(bots.move_pick(b, &unit_list(&a["candidates"]))),
        "choose_foe" => json!(bots.choose_foe(b, a["mover"].as_u64().unwrap() as UnitId)),
        "choose_target" => json!(bots.choose_target(b, a["attacker"].as_u64().unwrap() as UnitId)),
        "fire_pick_active" => json!(bots.fire_pick_active(b)),
        "fire_pick" => json!(bots.fire_pick(b, &unit_list(&a["candidates"]))),
        "records_declared_damage" => json!(bots.records_declared_damage(b, a["attacker"].as_u64().unwrap() as UnitId)),
        "choose_declaration" => {
            // the attack's inputs, worked out from the state as the engine does before asking (dry: no stub warning)
            let (attacker, target) = (a["attacker"].as_u64().unwrap() as UnitId, a["target"].as_u64().unwrap() as UnitId);
            let Prep::Ready(ctx) = prepare_declaration(b, attacker, target, true) else { return json!({"no_attack": true}) };
            let mut planner = Planner::new(attacker, target, &ctx.adjust, ctx.ams_share, ctx.pod_values.clone(), Some(ctx.hex_offset));
            let choice = bots.choose_declaration(b, &ctx, &mut planner, attacker, target);
            decl_json(b, attacker, &choice)
        }
        "choose_physical" => phys_json(&bots.choose_physical(b, a["attacker"].as_u64().unwrap() as UnitId, a["target"].as_u64().unwrap() as UnitId)),
        "choose_movement" => {
            let edge: Option<Vec<String>> = a["entry_edge"].as_array().map(|e| e.iter().map(|x| x.as_str().unwrap().to_string()).collect());
            let (pick, note, gate) = bots.choose_movement(
                b,
                a["mover"].as_u64().unwrap() as UnitId,
                a["other"].as_u64().unwrap() as UnitId,
                a["moves_first"].as_bool().unwrap(),
                a["standup_mp"].as_i64(),
                edge.as_deref(),
            );
            json!({"pick": pick.as_ref().map(pick_json), "note": note, "gate": gate_json(&gate)})
        }
        other => panic!("bridge: no call {}", other),
    }
}

// =============================================================================================================
// The decision process
// =============================================================================================================

/// One game's decision process: its own battle, kept for the whole game, and the bots.
pub struct Session {
    pub b: Battle,
    bots: GladiatorBots,
}

impl Session {
    /// The game's start: settings, board and units in a scenario's own form (config.json, board.json, units.json),
    /// plus the teams Hydra drives. The dice are whatever the first line's state says.
    pub fn start(v: &Value) -> Session {
        let cfg = Config::from_json(&v["config"]);
        let board = Board::from_json(&v["board"]);
        let names: Vec<String> = v["units"].as_object().unwrap().keys().cloned().collect();
        let idx = |n: &str| names.iter().position(|x| x == n).unwrap();
        let mut units: Vec<Mech> = names.iter().map(|n| Mech::from_json(&v["units"][n], &idx)).collect();
        let hydra: Vec<String> = v["hydra_teams"].as_array().map(|t| t.iter().map(|x| x.as_str().unwrap().to_string()).collect()).unwrap_or_default();
        for m in units.iter_mut() {
            if m.team.as_ref().is_some_and(|t| hydra.contains(t)) {
                m.bot = "hydra".to_string();
            }
        }
        let seed = v["seed"].as_u64().unwrap_or(1);
        Session { b: Battle::new(cfg, board, units, Box::new(PcgDice::new(seed))), bots: GladiatorBots }
    }

    /// One line: {"method", "args", "state"} -> the answer (null for a signal).
    pub fn handle(&mut self, line: &Value) -> Value {
        load_state(&mut self.b, &line["state"]);
        call(&mut self.b, &mut self.bots, line["method"].as_str().unwrap(), &line["args"])
    }
}

// =============================================================================================================
// The recorder (the parity check's first half)
// =============================================================================================================

/// Around the bots of an ordinary battle: every call is made into a line {"method", "args", "state", "answer"}, handed to
/// the checking session if there is one (and compared), and kept in `lines` only when `keep` is set.
pub struct Recorder<'a> {
    pub inner: &'a mut dyn BotSet,
    pub lines: Vec<Value>,
    pub keep: bool,
    /// the session checked alongside, and what it found so far
    pub check: Option<Session>,
    pub parity: Parity,
    last_board: Option<String>,
}

impl<'a> Recorder<'a> {
    pub fn new(inner: &'a mut dyn BotSet, check: Option<Session>, keep: bool) -> Recorder<'a> {
        Recorder { inner, lines: Vec::new(), keep, check, parity: Parity { calls: 0, decisions: 0, first_difference: None }, last_board: None }
    }

    /// Records the state, makes the call through the same `call` the session uses, records the answer.
    fn run(&mut self, b: &mut Battle, method: &str, args: Value) -> Value {
        let state = state_json(b, &mut self.last_board);
        let answer = call(b, self.inner, method, &args);
        self.checked(json!({"method": method, "args": args, "state": state, "answer": answer}));
        answer
    }

    /// A finished line: counted, handed to the session (until its first difference) and compared, kept if `keep`.
    fn checked(&mut self, line: Value) {
        self.parity.calls += 1;
        if !line["answer"].is_null() {
            self.parity.decisions += 1;
        }
        if self.parity.first_difference.is_none() {
            if let Some(s) = self.check.as_mut() {
                let got = s.handle(&line);
                if got != line["answer"] {
                    self.parity.first_difference = Some((self.parity.calls, line["method"].as_str().unwrap().to_string(), line["answer"].clone(), got));
                }
            }
        }
        if self.keep {
            self.lines.push(line);
        }
    }
}

fn unit_back(v: &Value) -> UnitId {
    v.as_u64().unwrap() as UnitId
}

fn pick_back(v: &Value) -> Pick {
    Pick {
        hex: v["hex"].as_str().unwrap().to_string(),
        facing: v["facing"].as_str().unwrap().to_string(),
        mode: v["mode"].as_str().unwrap().to_string(),
        fc: v["fc"].as_i64().unwrap(),
        mp_spent: v["mp_spent"].as_i64().unwrap(),
        charge: v["charge"].as_bool().unwrap(),
        dfa: v["dfa"].as_bool().unwrap(),
    }
}

impl BotSet for Recorder<'_> {
    fn choose_foe(&mut self, b: &mut Battle, mover: UnitId) -> Option<UnitId> {
        opt_unit(&self.run(b, "choose_foe", json!({"mover": mover})))
    }
    fn choose_target(&mut self, b: &mut Battle, attacker: UnitId) -> Option<UnitId> {
        opt_unit(&self.run(b, "choose_target", json!({"attacker": attacker})))
    }
    fn fire_pick_active(&mut self, b: &mut Battle) -> bool {
        self.run(b, "fire_pick_active", json!({})).as_bool().unwrap()
    }
    fn fire_pick(&mut self, b: &mut Battle, candidates: &[UnitId]) -> UnitId {
        unit_back(&self.run(b, "fire_pick", json!({"candidates": candidates})))
    }
    fn move_pick(&mut self, b: &mut Battle, candidates: &[UnitId]) -> Option<UnitId> {
        opt_unit(&self.run(b, "move_pick", json!({"candidates": candidates})))
    }
    fn choose_declaration(&mut self, b: &mut Battle, ctx: &DeclCtx, planner: &mut Planner, attacker: UnitId, target: UnitId) -> DeclChoice {
        // the engine's own inputs go to the bots; the session rebuilds them from the state (see `call`)
        let state = state_json(b, &mut self.last_board);
        let choice = self.inner.choose_declaration(b, ctx, planner, attacker, target);
        let answer = decl_json(b, attacker, &choice);
        self.checked(json!({"method": "choose_declaration", "args": {"attacker": attacker, "target": target}, "state": state, "answer": answer}));
        choice
    }
    fn choose_physical(&mut self, b: &mut Battle, attacker: UnitId, target: UnitId) -> Option<(i64, Vec<PhysOption>, ArcAction)> {
        let state = state_json(b, &mut self.last_board);
        let choice = self.inner.choose_physical(b, attacker, target);
        self.checked(json!({"method": "choose_physical", "args": {"attacker": attacker, "target": target}, "state": state, "answer": phys_json(&choice)}));
        choice
    }
    fn choose_movement(&mut self, b: &mut Battle, mover: UnitId, other: UnitId, moves_first: bool, standup_mp: Option<i64>, entry_edge: Option<&[String]>) -> (Option<Pick>, String, PathGate) {
        let a = self.run(b, "choose_movement", json!({"mover": mover, "other": other, "moves_first": moves_first, "standup_mp": standup_mp, "entry_edge": entry_edge}));
        let pick = if a["pick"].is_null() { None } else { Some(pick_back(&a["pick"])) };
        let gate = PathGate { psrs: a["gate"]["psrs"].as_i64(), hazard: a["gate"]["hazard"].as_f64() };
        (pick, a["note"].as_str().unwrap().to_string(), gate)
    }
    fn records_declared_damage(&self, b: &Battle, attacker: UnitId) -> bool {
        // a read-only question (&self): asked straight, not recorded
        self.inner.records_declared_damage(b, attacker)
    }
    fn reset_assigned(&mut self, b: &mut Battle) {
        self.run(b, "reset_assigned", json!({}));
    }
    fn start_movement(&mut self, b: &mut Battle) {
        self.run(b, "start_movement", json!({}));
    }
    fn unit_moved(&mut self, b: &mut Battle, mover: UnitId, start_hex: Option<&str>) {
        self.run(b, "unit_moved", json!({"mover": mover, "start_hex": start_hex}));
    }
    fn end_of_turn(&mut self, b: &mut Battle) {
        self.run(b, "end_of_turn", json!({}));
    }
    fn end_movement(&mut self, b: &mut Battle) {
        self.run(b, "end_movement", json!({}));
    }
    fn assign_damage(&mut self, b: &mut Battle, attacker: UnitId, target: UnitId, dmg: f64) {
        self.run(b, "assign_damage", json!({"attacker": attacker, "target": target, "dmg": dmg}));
    }
}

// =============================================================================================================
// The parity check
// =============================================================================================================

/// What `parity` found for one battle.
pub struct Parity {
    pub calls: usize,
    pub decisions: usize,
    /// the first decision the session answered differently: (call number from 1, method, the battle's answer, the session's)
    pub first_difference: Option<(usize, String, Value, Value)>,
}

/// Feeds a recorded battle's lines to a fresh session (built from the same start) and compares every answer.
pub fn parity(start: &Value, lines: &[Value]) -> Parity {
    let mut s = Session::start(start);
    let mut out = Parity { calls: 0, decisions: 0, first_difference: None };
    for line in lines {
        out.calls += 1;
        let answer = s.handle(line);
        if !line["answer"].is_null() {
            out.decisions += 1;
        }
        if answer != line["answer"] {
            out.first_difference = Some((out.calls, line["method"].as_str().unwrap().to_string(), line["answer"].clone(), answer));
            break;
        }
    }
    out
}

/// Keeps `Dice` in use from this module (state_json reads `save` through the trait).
fn _uses(_: &dyn Dice) {}
