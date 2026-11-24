//! A LIVE GAME WITH A PERSON IN IT (BattleROM, first playable slice, steps E2-E6 and the server's half of S1;
//! INTEGRATION__PLAYER_DECISIONS.md Section 15). Not translated from the Python.
//!
//! The battle waits for the person through a `Link`. The desktop Lab's link is `Game` (below: the battle on its own
//! thread, a Mutex and a Condvar). The browser build has no threads, so engine/wasm gives it a link whose "wait" blocks the
//! page's play worker (an Atomics wait on a shared buffer; INTEGRATION__PLAYER_DECISIONS.md Section 18): `play_blocking`
//! plays the whole battle on the caller's stack, asking through that link.
//!
//! `Game::start` plays a battle on its own thread with a `human_bots::HumanBots` whose controller (`Screen`) turns each
//! question to the person into a JSON request - the battle's units, the question's own data (hexes the unit can reach,
//! weapons with their TN, expected damage and heat, physical attacks) and the log lines since the last request - and
//! waits until `Game::answer` gives the reply. The battle has no clock: it simply does not go on until it has the answer.
//! Every other unit is played by the normal bots. The decision list the controller keeps (`HumanBots::log`) is what a
//! replay or a branch point is made from.
//!
//! Requests ("kind") and their answers:
//!   `move_order` {candidates}            -> {"unit": id}
//!   `stand_up` {tn, prone_turns}         -> {"stand": bool} (+ "plan": a movement answer after the stand; or, staying prone, "facing")
//!   `boost` {systems}                    -> {"use": bool}  (MASC / supercharger this turn)
//!   `movement` {options, attacks}        -> {"hex","facing","mode"} | {"stay": true} | {"attack": {"kind","target","hex","facing"}}
//!   `spot` {candidates}                  -> {"target": id|null, "fires": bool}
//!   `tag` {candidates}                   -> {"target": id|null, "aim": "mech"|"hex"}
//!   `target` {enemies}                   -> {"target": id|null}
//!   `declaration` {weapons, breakdown}   -> {"weapons": [ids], "modes","shots","bins","charge","aim"}
//!   `physical` {kinds}                   -> {"kind": "punch"|...|null}
//!   `end_phase` {equipment, heat}        -> {"switches": {...}} (or {})
//! While a question waits the page may also send a QUERY (`Game::query`): "path" (a move's route), "set" (a weapon's mode /
//! ammunition, answered with the weapon table afresh), "switches" / "equipment" (equipment switches, any time). A request
//! answered with something illegal is asked again, with an "error" saying why.
use std::sync::Arc;
#[cfg(not(target_arch = "wasm32"))]
use std::sync::{Condvar, Mutex};
#[cfg(not(target_arch = "wasm32"))]
use std::time::Duration;

use serde_json::{json, Value};

use crate::attack_resolution::{arc_unavailable, DeclChoice, DeclCtx};
use crate::battle::{Battle, UnitId};
use crate::dice::PcgDice;
use crate::equipment::ItemId;
use crate::equipment_systems as equip;
use crate::fasthash::HashSet;
use crate::fire_modes::Planner;
use crate::gladiator_bots::GladiatorBots;
use crate::human_bots::{Controller, HumanBots, PhysicalChoice};
use crate::mech_state as ms;
use crate::mech_state::ArcAction;
use crate::move_options::{self, PathNotes};
use crate::orchestrator::{play_on, start_battle_with, with_move_context, BotSet, PathGate};
use crate::ranged_combat::Pick;
use crate::scenario::Scenario;

const BOOST_LABEL: &str = "MASC / supercharger";
const RADICAL_LABEL: &str = "radical heat sink system";

/// What the battle gets back while it waits: the person's answer, or a question about the waiting question's data.
pub enum Incoming {
    Answer(Value),
    Query(Value),
}

/// How a waiting battle reaches the person (see the module comment): `post` shows a question, `wait` blocks until the page
/// answers it or asks something about it, `reply` answers such a query.
pub trait Link {
    fn post(&self, request: &Value);
    fn wait(&self) -> Incoming;
    fn reply(&self, reply: Value);
}

#[cfg(not(target_arch = "wasm32"))]
#[derive(Default)]
struct Slot {
    /// the question the battle is waiting on, and its number
    pending: Option<Value>,
    seq: u64,
    answer: Option<Value>,
    /// a query from the page while a question waits, and the reply
    query: Option<Value>,
    query_reply: Option<Value>,
    /// the battle's end: result, final units, log
    done: Option<Value>,
    /// the engine's own stop (a panic), as text
    failed: Option<String>,
}

#[cfg(not(target_arch = "wasm32"))]
pub struct Game {
    slot: Mutex<Slot>,
    cv: Condvar,
}

#[cfg(not(target_arch = "wasm32"))]
impl Link for Game {
    fn post(&self, request: &Value) {
        let mut s = self.slot.lock().unwrap();
        s.seq += 1;
        s.pending = Some(request.clone());
        s.answer = None;
        s.query = None;
        self.cv.notify_all();
    }
    fn wait(&self) -> Incoming {
        let mut s = self.slot.lock().unwrap();
        s = self.cv.wait_while(s, |s| s.answer.is_none() && s.query.is_none()).unwrap();
        match s.answer.take() {
            Some(a) => Incoming::Answer(a),
            None => Incoming::Query(s.query.take().unwrap()),
        }
    }
    fn reply(&self, reply: Value) {
        self.slot.lock().unwrap().query_reply = Some(reply);
        self.cv.notify_all();
    }
}

#[cfg(not(target_arch = "wasm32"))]
impl Game {
    /// Start a battle on `seed`; the units of `human_teams` are the person's. Returns at once.
    pub fn start(scenario: Arc<Scenario>, seed: u64, human_teams: Vec<String>) -> Arc<Game> {
        let game = Arc::new(Game { slot: Mutex::new(Slot::default()), cv: Condvar::new() });
        let g = game.clone();
        std::thread::Builder::new()
            .name("battlerom-game".into())
            .stack_size(64 << 20)
            .spawn(move || {
                let g2 = g.clone();
                let r = std::panic::catch_unwind(std::panic::AssertUnwindSafe(move || play(&g2, &scenario, seed, &human_teams)));
                if let Err(e) = r {
                    let msg = e.downcast_ref::<String>().cloned().or_else(|| e.downcast_ref::<&str>().map(|m| m.to_string())).unwrap_or_else(|| "the engine stopped".into());
                    g.slot.lock().unwrap().failed = Some(msg);
                    g.cv.notify_all();
                }
            })
            .expect("start the game thread");
        game
    }

    /// The question now waiting (or the end, or the engine's failure), waiting up to `wait` for one.
    pub fn poll(&self, wait: Duration) -> Value {
        let mut s = self.slot.lock().unwrap();
        if s.pending.is_none() && s.done.is_none() && s.failed.is_none() {
            s = self.cv.wait_timeout_while(s, wait, |s| s.pending.is_none() && s.done.is_none() && s.failed.is_none()).unwrap().0;
        }
        if let Some(f) = &s.failed {
            return json!({"state": "failed", "error": f});
        }
        if let Some(d) = &s.done {
            return json!({"state": "done", "end": d});
        }
        match &s.pending {
            Some(p) => json!({"state": "pending", "seq": s.seq, "request": p}),
            None => json!({"state": "waiting"}),
        }
    }

    /// Answer question `seq`.
    pub fn answer(&self, seq: u64, answer: Value) -> Result<(), String> {
        let mut s = self.slot.lock().unwrap();
        if s.pending.is_none() || s.seq != seq {
            return Err("that question is not the one waiting".into());
        }
        s.pending = None;
        s.answer = Some(answer);
        self.cv.notify_all();
        Ok(())
    }

    /// Ask the waiting question's own data something (a route, a weapon's mode) or set switches; the battle answers while it
    /// waits. {"error"} when no question is waiting.
    pub fn query(&self, q: Value, wait: Duration) -> Value {
        let mut s = self.slot.lock().unwrap();
        if s.pending.is_none() || s.query.is_some() {
            return json!({"error": "no question is waiting"});
        }
        s.query = Some(q);
        s.query_reply = None;
        self.cv.notify_all();
        let (mut s, _) = self.cv.wait_timeout_while(s, wait, |s| s.query_reply.is_none()).unwrap();
        s.query_reply.take().unwrap_or_else(|| json!({"error": "the engine did not answer"}))
    }
}

#[cfg(not(target_arch = "wasm32"))]
fn play(game: &Arc<Game>, sc: &Scenario, seed: u64, human_teams: &[String]) {
    let end = play_blocking(game.clone(), sc, seed, human_teams);
    game.slot.lock().unwrap().done = Some(end);
    game.cv.notify_all();
}

/// Play the whole battle on this stack, asking the person through `link`; returns the end (winner, turns, final units,
/// the log's last lines, how many decisions the person made).
pub fn play_blocking(link: Arc<dyn Link>, sc: &Scenario, seed: u64, human_teams: &[String]) -> Value {
    let mut b = sc.battle(Box::new(PcgDice::new(seed)));
    let human: Vec<UnitId> = (0..b.units.len()).filter(|&u| b.units[u].team.as_deref().is_some_and(|t| human_teams.iter().any(|h| h == t))).collect();
    for &u in &human {
        let n = b.units[u].side_name.clone().unwrap_or_default();
        b.player.unit_mut(&n); // a unit a person controls has an entry: the stubs look there first
    }
    let mut marks = |_: &mut Battle, _: i64, _: &str| {};
    let screen = Screen { link, sent_log: 0, first: true, plan: None, stand_plan: None, prone_facing: None };
    let mut bots = HumanBots::new(screen, human);
    // a person's units are placed by the person when the deployment rules place units before turn 1 (walk-on units enter during movement)
    let mut play = start_battle_with(&mut b, sc.max_turns, &mut marks, &mut |b, u, good| bots.deploy(b, u, good));
    play_on(&mut b, &mut bots, &mut play, &mut marks);
    let r = &play.result;
    json!({"winner": r.winner, "turns": r.turns_taken, "destroyed": r.destroyed, "units": units_json(&b, false), "log": new_log(&b, &mut bots.ctl.sent_log), "decisions": bots.log.len()})
}

fn name(b: &Battle, u: UnitId) -> String {
    b.units[u].side_name.clone().unwrap_or_default()
}

fn units_json(b: &Battle, with_names: bool) -> Value {
    Value::Array(
        (0..b.units.len())
            .map(|u| {
                let m = &b.units[u];
                let mut s = crate::history::unit_state(b, u);
                s["id"] = json!(u);
                s["name"] = json!(m.side_name);
                s["mech"] = json!(format!("{} {}", m.chassis, m.model).trim());
                s["team"] = json!(m.team);
                s["tons"] = json!(m.mass);
                s["walk"] = json!(ms::compute_walk_mp(m));
                s["run"] = json!(ms::compute_running_mp(m));
                s["jump"] = json!(ms::compute_jump_mp(m));
                s["max_heat"] = json!(m.max_heat);
                s["move_mode"] = json!(m.move_mode);
                s["gunnery"] = json!(m.gunnery);
                s["piloting"] = json!(m.piloting);
                // critical slots: which are destroyed now (and, once, their names)
                let alive: serde_json::Map<String, Value> = m.crits.iter().map(|(loc, slots)| (loc.clone(), json!(slots.iter().map(|sl| !sl.is_name("DESTROYED")).collect::<Vec<_>>()))).collect();
                s["crit_alive"] = Value::Object(alive);
                if with_names {
                    let names: serde_json::Map<String, Value> = m.crits.keys().map(|loc| (loc.clone(), json!(ms::display_crits(m, loc)))).collect();
                    s["crit_names"] = Value::Object(names);
                    // the unit's weapons for the detail sheet's Weapons tab (read-only for an enemy): where, damage, heat, ranges
                    let locs = crate::attack_resolution::weapon_locations(m);
                    let ws: Vec<Value> = m.items.iter().enumerate().filter(|(_, it)| it.category.as_deref() == Some("weapon")).map(|(i, it)| {
                        json!({"id": i, "name": it.name, "loc": locs.get(&i), "heat": it.heat, "damage": it.damage_per_shot, "rack": it.rack_size, "rear": it.rear_mounted,
                               "ranges": it.weapon_range.as_ref().map(|r| json!({"min": r.min, "short": r.short, "medium": r.medium, "long": r.long}))})
                    }).collect();
                    s["weapons"] = Value::Array(ws);
                }
                s["equipment"] = equipment_json(b, u);
                s
            })
            .collect(),
    )
}

fn new_log(b: &Battle, sent: &mut usize) -> Vec<String> {
    let lines = b.log.lines[(*sent).min(b.log.lines.len())..].to_vec();
    *sent = b.log.lines.len();
    lines
}

// ---------------------------------------------------------------------------------------------------------------------
// Equipment switches (the critical hit table's switches, as MegaMek has them): what a unit has, what is set, what changes
// ---------------------------------------------------------------------------------------------------------------------
fn escalating_tn(m: &ms::Mech, key: &str) -> i64 {
    equip::escalating_avoid_tn(m.escalating_turns.get(key).copied().unwrap_or(0) + 1)
}

fn equipment_json(b: &Battle, u: UnitId) -> Value {
    let m = &b.units[u];
    let n = name(b, u);
    let ch = b.player.unit(&n);
    let on = |label: &str| ch.and_then(|c| c.escalating.get(label)).copied().unwrap_or(false);
    let mut ams = Vec::new();
    let mut jammed = Vec::new();
    let mut ppcs = Vec::new();
    for w in crate::damage_resolution::get_weapons(m) {
        let it = &m.items[w];
        if it.memo.is_ams == Some(true) || it.name.to_uppercase().contains("AMS") || it.name.to_uppercase().contains("ANTI-MISSILE") {
            ams.push(json!({"id": w, "name": it.name, "off": m.systems_off.contains(&crate::bot_heat_equipment::ams_key(w))}));
        }
        if it.jammed == Some(true) {
            jammed.push(json!({"id": w, "name": it.name, "unjam": ch.is_some_and(|c| c.unjam.contains(&it.name))}));
        }
        if it.capacitor.is_some() {
            ppcs.push(json!({"id": w, "name": it.name, "charge": ch.is_some_and(|c| c.charge.contains(&it.name))}));
        }
    }
    json!({
        "masc": equip::system_live(m, "masc"), "supercharger": equip::system_live(m, "supercharger"),
        "boost": {"has": equip::system_live(m, "masc") || equip::system_live(m, "supercharger"), "on": on(BOOST_LABEL), "tn": escalating_tn(m, if equip::system_live(m, "masc") { "masc" } else { "supercharger" })},
        "radical": {"has": equip::has_system(m, "radical"), "live": equip::system_live(m, "radical"), "on": on(RADICAL_LABEL), "tn": escalating_tn(m, "radical")},
        "coolant": {"pods": equip::unused_coolant_pods(m).len(), "mode": match ch.and_then(|c| c.coolant) { None => "auto", Some(false) => "hold", Some(true) => "now" }},
        "sinks": {"working": ms::working_heat_sinks(m), "off": ch.and_then(|c| c.sinks_off).unwrap_or(m.deactivated_heat_sinks), "chosen": ch.is_some_and(|c| c.sinks_off.is_some())},
        "ams": ams, "jammed": jammed, "capacitors": ppcs,
        "blue_shield": {"has": equip::has_system(m, "blue_shield"), "on": ch.and_then(|c| c.blue_shield).unwrap_or(false)},
        // ejection is not built (a known shortfall); the switch is kept so the screen has a place for it
        "auto_eject": {"built": false},
    })
}

/// Apply equipment switches from the page to unit `u` (they stay until changed).
fn apply_switches(b: &mut Battle, u: UnitId, sw: &Value) {
    let n = name(b, u);
    if let Some(v) = sw.get("coolant").and_then(|v| v.as_str()) {
        b.player.unit_mut(&n).coolant = match v { "hold" => Some(false), "now" => Some(true), _ => None };
    }
    if let Some(v) = sw.get("radical").and_then(|v| v.as_bool()) {
        b.player.unit_mut(&n).escalating.insert(RADICAL_LABEL.to_string(), v);
    }
    if let Some(v) = sw.get("boost").and_then(|v| v.as_bool()) {
        b.player.unit_mut(&n).escalating.insert(BOOST_LABEL.to_string(), v);
    }
    if sw.get("sinks_off").is_some() {
        b.player.unit_mut(&n).sinks_off = sw["sinks_off"].as_i64();
    }
    if let Some(v) = sw.get("blue_shield").and_then(|v| v.as_bool()) {
        b.player.unit_mut(&n).blue_shield = Some(v);
    }
    if let Some(list) = sw.get("ams_off").and_then(|v| v.as_array()) {
        b.units[u].systems_off.retain(|k| !k.starts_with("ams:"));
        for id in list.iter().filter_map(|v| v.as_u64()) {
            b.units[u].systems_off.push(crate::bot_heat_equipment::ams_key(id as usize));
        }
    }
    if let Some(list) = sw.get("unjam").and_then(|v| v.as_array()) {
        let names: HashSet<String> = list.iter().filter_map(|v| v.as_str().map(String::from)).collect();
        b.player.unit_mut(&n).unjam = names;
    }
    if let Some(list) = sw.get("charge").and_then(|v| v.as_array()) {
        let names: HashSet<String> = list.iter().filter_map(|v| v.as_str().map(String::from)).collect();
        b.player.unit_mut(&n).charge = names;
    }
}

/// Queries every question answers: equipment switches.
fn common_tools(b: &mut Battle, q: &Value) -> Option<Value> {
    let u = q["unit"].as_u64()? as usize;
    if u >= b.units.len() || !b.player.is_player(&name(b, u)) {
        return Some(json!({"error": "not your unit"}));
    }
    match q["q"].as_str()? {
        "switches" => {
            apply_switches(b, u, &q["switches"]);
            Some(json!({"equipment": equipment_json(b, u)}))
        }
        "equipment" => Some(json!({"equipment": equipment_json(b, u)})),
        _ => None,
    }
}

// ---------------------------------------------------------------------------------------------------------------------
// The controller that talks to the page
// ---------------------------------------------------------------------------------------------------------------------
struct Screen {
    link: Arc<dyn Link>,
    sent_log: usize,
    first: bool,
    /// a move the person planned while choosing the unit to move (`move_order`'s "plan"): the unit and the movement answer, used
    /// when that unit's movement question comes
    plan: Option<(UnitId, Value)>,
    /// a move the person planned together with standing up (`stand_up`'s "plan", bug A2): used by that unit's movement question
    /// right after a successful stand; dropped if the stand fails (no movement question follows) or anything else moves first
    stand_plan: Option<(UnitId, Value)>,
    /// the facing a person chose for a unit that stays prone (the stand_up answer's "facing"; p.51)
    prone_facing: Option<(UnitId, String)>,
}

/// Everything the movement question and its queries need about one unit's possible moves.
struct MoveView {
    req: Value,
    opts: Vec<move_options::Opt>,
    best: std::collections::BTreeMap<(String, String, String), (usize, i64)>,
    attacks: Vec<(Value, Pick)>,
}

/// The unit's possible moves now (in its movement context): the reach table, the charge / death-from-above stops, and the request that
/// shows them. Used for the unit being asked to move and, in `move_order`, for any unit that has not moved yet.
fn move_view(b: &mut Battle, mover: UnitId, standup_mp: Option<i64>, entry_edge: Option<&[String]>) -> MoveView {
    let mut notes = PathNotes::default();
    let mut states = move_options::movement_options(b, mover, standup_mp, entry_edge, true, &mut notes);
    // a unit may pass through a friend's hex but not end there (the bots exclude these hexes the same way)
    let occupied = move_options::occupied_hexes(b, mover, mover);
    states.retain(|st| !occupied.contains(&(st.0, st.1)));
    let opts = move_options::prepare_options(b, mover, &states);
    // the cheapest way to each (hex, facing, mode); the screen draws reach from these
    let mut best: std::collections::BTreeMap<(String, String, String), (usize, i64)> = Default::default();
    for (i, o) in opts.iter().enumerate() {
        let k = (o.label.clone(), o.facing_compass.to_string(), o.mode.to_string());
        match best.get(&k) {
            Some((_, mp)) if *mp <= o.mp_spent => {}
            _ => {
                best.insert(k, (i, o.mp_spent));
            }
        }
    }
    let list: Vec<Value> = best
        .values()
        .map(|(i, _)| {
            let o = &opts[*i];
            let k = o.key();
            json!({"hex": o.label, "facing": o.facing_compass, "mode": o.mode, "mp": o.mp_spent, "hexes": o.fc, "heat": o.move_heat, "tmm": o.tmm,
                   "psrs": notes.psrs.get(&k).copied().unwrap_or(0), "hazard": notes.hazard.get(&k).copied().unwrap_or(0.0)})
        })
        .collect();
    // charges and death from above (Core pp.78-80): the stops next to an enemy that has moved (or cannot), with the numbers
    let mut attacks: Vec<(Value, Pick)> = Vec::new();
    if entry_edge.is_none() && standup_mp.is_none() && !b.units[mover].prone && (b.cfg.b("CHARGES") || b.cfg.b("DFA")) {
        let mut n2 = PathNotes::default();
        let index = crate::move_attacks::MoverIndex::new(b, mover, standup_mp, &mut n2);
        for t in crate::forces::enemies_of(b, mover) {
            let moved = b.units[t].moved_this_turn;
            if b.units[t].hex.is_none() || !crate::move_attacks::can_be_attacked(b, t, moved) {
                continue;
            }
            let pose = crate::move_attacks::pose_of(b, t);
            let mut picks: Vec<Pick> = Vec::new();
            if b.cfg.b("CHARGES") && !pose.prone {
                picks.extend(index.charge_states(b, &pose));
            }
            if b.cfg.b("DFA") {
                picks.extend(index.dfa_states(b, &pose));
            }
            for p in picks {
                let (_, _, hit, tn, dmg, _side, _) = crate::move_attacks::values(b, mover, t, &pose, &p);
                let self_dmg = if p.charge { crate::charge::attacker_damage(&b.units[t]) } else { crate::dfa::attacker_damage(&b.units[mover]) };
                let kind = if p.charge { "charge" } else { "dfa" };
                attacks.push((json!({"kind": kind, "target": t, "target_name": name(b, t), "hex": p.hex, "facing": p.facing, "mode": p.mode, "mp": p.mp_spent, "hexes": p.fc, "tn": tn, "hit": hit, "damage": dmg, "self_damage": self_dmg}), p));
            }
        }
    }
    let m = &b.units[mover];
    let req = json!({"kind": "movement", "unit": mover, "name": name(b, mover), "hex": m.hex, "facing": m.facing, "standup_mp": standup_mp,
                     "entry": entry_edge.is_some(), "walk": ms::compute_walk_mp(m), "run": ms::compute_running_mp(m),
                     "jump": ms::compute_jump_mp(m), "options": list, "attacks": attacks.iter().map(|a| a.0.clone()).collect::<Vec<_>>()});
    MoveView { req, opts, best, attacks }
}

/// WAYPOINTS (Daniel, 2026-11-22: "so long as the final destination and movement mode that the waypoint method selects is the same,
/// letting the auto route figure out how to get there while maximizing TMM is fine"; a known issue, not a bug): the cost of getting to the
/// last of `waypoints` through all the others, and what can be reached from there with the points left. Ground moves only. Returns
/// {"reach": [{hex, facing, mode, mp}], "legs": [{hex, mp}...]} - the legs are the route through the waypoints (the drawn line); the unit,
/// when it moves, takes its own best route to the destination, so its line may differ.
fn way_query(b: &Battle, mover: UnitId, q: &Value) -> Value {
    let hexes: Vec<(i64, i64)> = match q["waypoints"].as_array().map(|a| a.iter().map(|h| h.as_str().and_then(hex_geometry_parse)).collect::<Option<Vec<_>>>()) {
        Some(Some(h)) => h,
        _ => return json!({"error": "which waypoints?"}),
    };
    let m = &b.units[mover];
    let Some(label) = m.hex.as_deref() else { return json!({"error": "waypoints need a unit on the map"}) };
    let Ok((sx, sy, f0)) = crate::hex_geometry::state_from_label(label, &m.facing) else { return json!({"error": "no start"}) };
    let (walk, run) = (ms::compute_walk_mp(m), ms::compute_running_mp(m));
    let blocked = crate::ranged_combat::blocked_set(&m.blocked_hex);
    let level_limit = crate::terrain_rules::max_level_change(ms::ground_level_limited(m), ms::is_superheavy(m));
    // where we stand at each stage: facing -> (points spent, the route so far as (hex, points))
    type Route = Vec<(String, i64)>;
    let mut at = (sx, sy);
    let mut cur: std::collections::BTreeMap<i64, (i64, Route)> = Default::default();
    cur.insert(f0, (0, vec![]));
    let table = |x: i64, y: i64, f: i64, budget: i64| crate::pathfinder::build_movement_table(x, y, f, budget, Some(&b.board), None, level_limit, true, &blocked);
    for &(wx, wy) in &hexes {
        let mut next: std::collections::BTreeMap<i64, (i64, Route)> = Default::default();
        for (f, (spent, route)) in &cur {
            let Ok(t) = table(at.0, at.1, *f, run - spent) else { continue };
            for f2 in 0..6 {
                let state = (wx, wy, f2);
                let Some(col) = t.entries.get(&state) else { continue };
                let Some(&mp) = col.keys().min() else { continue };
                if next.get(&f2).is_some_and(|(have, _)| *have <= spent + mp) {
                    continue;
                }
                let mut r = route.clone();
                r.extend(t.path(state, mp).into_iter().map(|(_, st, mm)| (crate::hex_geometry::hex_label(st.0, st.1).unwrap_or_default(), spent + mm)));
                next.insert(f2, (spent + mp, r));
            }
        }
        if next.is_empty() {
            return json!({"error": "that hex cannot be reached through the waypoints with the points you have"});
        }
        cur = next;
        at = (wx, wy);
    }
    // what is reachable from the last waypoint: the cheapest points per (hex, facing, mode)
    let mut best: std::collections::BTreeMap<(i64, i64, i64, &'static str), i64> = Default::default();
    for (f, (spent, _)) in &cur {
        let Ok(t) = table(at.0, at.1, *f, run - spent) else { continue };
        for (&(x, y, f2), col) in &t.entries {
            for &mp in col.keys() {
                let total = spent + mp;
                let mode = crate::combat::classify_movement_mode(total, walk);
                let e = best.entry((x, y, f2, mode)).or_insert(i64::MAX);
                *e = (*e).min(total);
            }
        }
    }
    let reach: Vec<Value> = best
        .iter()
        .filter_map(|(&(x, y, f, mode), &mp)| Some(json!({"hex": crate::hex_geometry::hex_label(x, y).ok()?, "facing": crate::hex_geometry::facing_to_compass(f).ok()?, "mode": mode, "mp": mp})))
        .collect();
    // the drawn route: the cheapest way to arrive at the last waypoint (any facing)
    let legs = cur.values().min_by_key(|(sp, _)| *sp).map(|(_, r)| r.iter().map(|(h, mp)| json!({"k": "forward", "hex": h, "mp": mp})).collect::<Vec<_>>()).unwrap_or_default();
    json!({"reach": reach, "legs": legs})
}

fn hex_geometry_parse(label: &str) -> Option<(i64, i64)> {
    crate::hex_geometry::parse_hex_label(label).ok()
}

impl MoveView {
    /// The route the engine will walk to a chosen end (or to a charge / DFA stop): the "path" query's answer.
    fn route(&self, b: &mut Battle, mover: UnitId, q: &Value, standup_mp: Option<i64>, entry_edge: Option<&[String]>) -> Option<Value> {
        let pick = if let Some(a) = q.get("attack").filter(|a| a.is_object()) {
            // a charge's cost includes the step into the target's hex, which the route tables do not hold: the route to
            // the stop is the cheapest ordinary way to end there (a jump for death from above)
            let jump = a["kind"] == "dfa";
            self.opts.iter().filter(|o| o.label == a["hex"].as_str().unwrap_or("") && o.facing_compass == a["facing"].as_str().unwrap_or("") && (o.mode == "Jump") == jump).min_by_key(|o| o.mp_spent).map(|o| o.pick())
        } else {
            let k = (q["hex"].as_str().unwrap_or("").to_string(), q["facing"].as_str().unwrap_or("").to_string(), q["mode"].as_str().unwrap_or("").to_string());
            self.best.get(&k).map(|(i, _)| self.opts[*i].pick())
        }?;
        let steps = crate::ranged_combat::path_to(b, mover, &pick, standup_mp, entry_edge)?;
        let list: Vec<Value> = steps
            .iter()
            .map(|(kind, (x, y, f), mp)| json!({"k": kind, "hex": crate::hex_geometry::hex_label(*x, *y).unwrap_or_default(), "facing": crate::hex_geometry::facing_to_compass(*f).unwrap_or(""), "mp": mp}))
            .collect();
        Some(json!({"path": list}))
    }
}

impl Screen {
    /// Send `request` (units and log added) and wait for the answer, serving the page's queries meanwhile. `check` turns an
    /// answer into the engine's choice or an error text, in which case the person is asked again.
    fn ask<T>(&mut self, b: &mut Battle, request: Value, tools: impl FnMut(&mut Battle, &Value) -> Option<Value>, check: impl FnMut(&mut Battle, &Value) -> Result<T, String>) -> T {
        self.ask_with(b, request, None, tools, check)
    }

    /// `ask` with an answer the person gave ahead of time (a move planned while choosing the unit): used if `check` accepts it,
    /// else the question is asked and says why it was not.
    fn ask_with<T>(&mut self, b: &mut Battle, mut request: Value, preset: Option<Value>, mut tools: impl FnMut(&mut Battle, &Value) -> Option<Value>, mut check: impl FnMut(&mut Battle, &Value) -> Result<T, String>) -> T {
        if let Some(a) = preset {
            match check(b, &a) {
                Ok(t) => return t,
                Err(e) => request["error"] = json!(format!("The move you planned is no longer possible ({}). Plan it again.", e)),
            }
        }
        request["units"] = units_json(b, self.first);
        request["log"] = json!(new_log(b, &mut self.sent_log));
        if self.first {
            request["board"] = crate::history::board(b);
            self.first = false;
        }
        loop {
            self.link.post(&request);
            let answer = loop {
                match self.link.wait() {
                    Incoming::Answer(a) => break a,
                    Incoming::Query(q) => {
                        let reply = tools(b, &q).or_else(|| common_tools(b, &q)).unwrap_or_else(|| json!({"error": "unknown query"}));
                        self.link.reply(reply);
                    }
                }
            };
            match check(b, &answer) {
                Ok(t) => return t,
                Err(e) => {
                    request["error"] = json!(e);
                    request["log"] = json!([]);
                    request["units"] = units_json(b, false);
                    request.as_object_mut().unwrap().remove("board");
                }
            }
        }
    }
}

fn hex_of(label: &str) -> Option<(i64, i64)> {
    crate::hex_geometry::parse_hex_label(label).ok()
}

/// The weapon table for a declaration, priced now (after any mode / ammunition choice): rows, and the candidates the engine
/// would let fire (weapon, expected damage, heat).
/// The queries the target question (the first, or a secondary one) answers while it waits: `preview` and `set`.
fn target_query(b: &mut Battle, attacker: UnitId, enemies: &[UnitId], q: &Value, default_primary: Option<UnitId>) -> Option<Value> {
    let primary = q["primary"].as_u64().map(|p| p as usize).filter(|p| enemies.contains(p)).or(default_primary);
    match q["q"].as_str() {
        Some("preview") => Some(target_preview(b, attacker, enemies, primary)),
        // a mode / ammunition / rate change made on the fire screen before the target is chosen (the settings belong to the unit)
        Some("set") => {
            let t = q["target"].as_u64().map(|t| t as usize).filter(|t| enemies.contains(t)).unwrap_or(enemies[0]);
            apply_weapon_settings(b, attacker, t, q);
            Some(target_preview(b, attacker, enemies, primary))
        }
        _ => None,
    }
}

/// The declaration question's body for one attacker and target: the to-hit number in its parts (the weapon rows add the range band and
/// the weapon's own modifiers on top), the weapon rows, heat and the rest. The target step's preview builds the same for every enemy.
fn decl_req_json(b: &Battle, ctx: &DeclCtx, rows: Vec<Value>, attacker: UnitId, target: UnitId) -> Value {
    let u = &b.units[attacker];
    let listed = u.gunnery + ctx.amm + ctx.tmm + ctx.los_modifier + ctx.cover + ctx.heat_mod + ctx.prone_mod + ctx.stealth_mod;
    let breakdown = json!({"gunnery": u.gunnery, "attacker_movement": ctx.amm, "attacker_mode": u.move_mode, "target_movement": ctx.tmm, "line_of_sight": ctx.los_modifier, "cover": ctx.cover,
                           "heat": ctx.heat_mod, "target_prone": ctx.prone_mod, "stealth": ctx.stealth_mod, "other": ctx.sel_pre_tn - listed, "base": ctx.sel_pre_tn,
                           "secondary": ctx.secondary, "indirect": ctx.indirect, "note": ctx.cond_note});
    json!({"kind": "declaration", "unit": attacker, "name": name(b, attacker), "target": target, "target_name": name(b, target), "distance": ctx.distance,
           "base_tn": ctx.sel_pre_tn, "breakdown": breakdown, "weapons": rows, "heat": u.current_heat, "move_heat": u.movement_heat,
           "dissipation": ctx.dissipation, "max_heat": u.max_heat, "indirect": ctx.indirect, "secondary": ctx.secondary,
           "target_hex": b.units[target].hex, "actions": ctx.arc_choices.len()})
}

/// The target question's `preview` query (and the answer to a `set` there): everything the fire screen needs to plan a whole turn's fire
/// before any question is answered (Daniel, 2026-11-22: pick weapons and targets, then Fire!). For every enemy, the declaration's body as
/// it would be asked (weapon rows with their real numbers); the arcs once. `primary`: the enemy the first weapons go at, so the others
/// are worked out as secondary targets (+1, p.64). A quiet dry run: nothing is changed or logged.
fn target_preview(b: &mut Battle, attacker: UnitId, enemies: &[UnitId], primary: Option<UnitId>) -> Value {
    b.log.quiet += 1;
    let saved = b.split_fire.clone();
    if let Some(p) = primary {
        crate::split_fire::record(b, attacker, p, &[], 0);
    }
    let mut arcs = serde_json::Map::new();
    let mut targets: Vec<Value> = Vec::new();
    for &t in enemies {
        let forward = crate::split_fire::in_forward_arc(b, attacker, t);
        let refusal = if primary.is_some() && primary != Some(t) { crate::split_fire::refusal(b, attacker, t) } else { None };
        let ready = if refusal.is_none() { crate::attack_resolution::prepare_declaration(b, attacker, t, true) } else { crate::attack_resolution::Prep::Done };
        let crate::attack_resolution::Prep::Ready(ctx) = ready else {
            targets.push(json!({"id": t, "req": Value::Null, "forward": forward, "why": refusal}));
            continue;
        };
        let mut planner = Planner::new(attacker, t, &ctx.adjust, ctx.ams_share, ctx.pod_values.clone(), Some(ctx.hex_offset));
        let (mut rows, ..) = weapon_rows(b, &ctx, &mut planner, attacker);
        for r in rows.iter_mut() {
            if let Some(o) = r.as_object_mut() {
                let (a1, a2) = (o.remove("arc"), o.remove("arc_twist"));
                arcs.entry(r["id"].to_string()).or_insert_with(|| json!({"arc": a1, "arc_twist": a2}));
            }
        }
        targets.push(json!({"id": t, "req": decl_req_json(b, &ctx, rows, attacker, t), "forward": forward, "why": Value::Null}));
    }
    b.split_fire = saved;
    b.log.quiet -= 1;
    json!({"targets": targets, "arcs": arcs})
}

fn weapon_rows(b: &mut Battle, ctx: &DeclCtx, planner: &mut Planner, attacker: UnitId) -> (Vec<Value>, Vec<crate::weapon_selection::Candidate>, Vec<HashSet<usize>>) {
    planner.forget();
    // TAG is not a weapon of the Ranged Attack Phase: its attack is its own step before that phase, and designating is all it
    // does (Core p.200; bug B11, Daniel 2026-11-22). The person is asked about it in the TAG question, never in the weapon list.
    // (The bots never pick it here either: it does no damage.)
    let weapons: Vec<ItemId> = crate::damage_resolution::get_weapons(&b.units[attacker]).into_iter().filter(|w| !crate::tag::is_tag(b, attacker, *w)).collect();
    let cands = crate::weapon_selection::fire_candidates(b, attacker, ctx.distance, ctx.sel_pre_tn, Some(&ctx.adjust), &ctx.unavailable, None, &weapons, Some(&mut *planner));
    // each arc action's unavailable weapons; the first is "no change" (the engine's tie order)
    let per_action: Vec<HashSet<usize>> = ctx
        .arc_choices
        .iter()
        .map(|(key, _)| {
            let mut u = ctx.unavailable.clone();
            u.extend(arc_unavailable(&b.units[attacker], key));
            u
        })
        .collect();
    let pname = name(b, attacker);
    let mut rows: Vec<Value> = Vec::new();
    for &w in &weapons {
        let (iname, iheat, jammed, cap, rear) = {
            let it = &b.units[attacker].items[w];
            (it.name.clone(), it.heat, it.jammed == Some(true), it.capacitor.is_some(), it.rear_mounted)
        };
        let cand = cands.iter().find(|c| c.w == w);
        let bracket = crate::weapon_selection::range_bracket(b, attacker, w, ctx.distance);
        let tn = cand.map(|_| {
            let adj = crate::fire_modes::TnAdjust::adjust(&ctx.adjust, b, w, bracket, None);
            (ctx.sel_pre_tn + adj).clamp(crate::weapon_selection::PRE_TN_MIN, crate::weapon_selection::PRE_TN_MAX)
        });
        // modes: the shot options (ammunition kind / guidance) and the rates of fire
        let mut modes: Vec<Value> = Vec::new();
        let mut rates: Vec<Value> = Vec::new();
        let mut mode_now = Value::Null;
        let mut shots_now = Value::Null;
        if let Some((_, _, plan)) = planner.plan_for(b, w, ctx.distance, ctx.sel_pre_tn) {
            mode_now = json!(plan.label());
            let kinds = planner.kinds(b, w);
            if kinds.len() > 1 {
                for k in &kinds {
                    let v = planner.value(b, w, k, ctx.distance, ctx.sel_pre_tn);
                    modes.push(json!({"label": k.label(), "ev": v.map(|x| x.0), "tn": v.map(|x| x.1), "selected": k.label() == plan.label()}));
                }
            }
            let ro = crate::fire_modes::rate_options(b, attacker, w, &plan);
            if ro.len() > 1 {
                shots_now = json!(plan.shots);
                for n in ro {
                    let mut p = plan.clone();
                    p.shots = n;
                    rates.push(json!({"shots": n, "ev": planner.value(b, w, &p, ctx.distance, ctx.sel_pre_tn).map(|x| x.0), "selected": n == plan.shots}));
                }
            }
        }
        // ammunition bins this weapon can draw from, and which it will
        let bins_all = crate::ammo::bins_for(&b.units[attacker], w);
        let mut bins: Vec<Value> = Vec::new();
        if !bins_all.is_empty() {
            let counted: Vec<ItemId> = bins_all.iter().copied().filter(|i| b.units[attacker].items[*i].shots_left.is_some()).collect();
            let forced = b.player.unit(&pname).and_then(|c| c.bin.get(&w)).copied().filter(|i| bins_all.contains(i));
            let drawn = forced.or_else(|| if counted.is_empty() { None } else { Some(crate::ammo::auto_bin(&b.units[attacker], &counted)) });
            for i in &bins_all {
                let e = &b.units[attacker].items[*i];
                bins.push(json!({"id": i, "name": e.name, "loc": crate::ammo::bin_location(&b.units[attacker], *i), "munition": e.munition, "shots": e.shots_left, "selected": Some(*i) == drawn, "chosen": Some(*i) == forced}));
            }
        }
        // the hexes this weapon can bear on: as the unit stands (no twist) and with any torso twist / arm flip it may declare
        let (arc_now, arc_twist) = {
            let m = &b.units[attacker];
            let legs = crate::arcs::leg_offsets(m);
            let now = crate::arcs::current_action(m);
            let (mut a1, mut a2): (Vec<String>, Vec<String>) = (Vec::new(), Vec::new());
            for label in b.board.hexes.keys() {
                let Some(h) = hex_of(label) else { continue };
                if h == ctx.a_hex {
                    continue;
                }
                let pair = crate::arcs::arcs_between(ctx.a_hex, h);
                let bears = |action: &ArcAction| {
                    let key = crate::arcs::key_for(&pair, ctx.a_facing, action, &legs);
                    !crate::arcs::unavailable(m, &[w], &ctx.w_locs, &key).contains(&w)
                };
                if bears(&now) {
                    a1.push(label.clone());
                    a2.push(label.clone());
                } else if ctx.arc_choices.iter().any(|(_, act)| bears(act)) {
                    a2.push(label.clone());
                }
            }
            (a1, a2)
        };
        let charge = cap && b.player.unit(&pname).is_some_and(|c| c.charge.contains(&iname));
        rows.push(json!({"id": w, "name": iname, "loc": ctx.w_locs.get(&w), "heat": cand.map(|c| c.heat).or(iheat), "ev": cand.map(|c| c.value),
                         "tn": tn, "adj": tn.map(|t| t - ctx.sel_pre_tn), "range": bracket, "damage": b.units[attacker].items[w].damage_per_shot, "rack": b.units[attacker].items[w].rack_size, "in_range": cand.is_some(), "jammed": jammed,
                         "needs_twist": cand.is_some() && per_action.first().is_some_and(|u| u.contains(&w)),
                         "modes": modes, "mode": mode_now, "rates": rates, "shots": shots_now, "bins": bins,
                         "chargeable": cap, "charge": charge, "rear": rear, "arc": arc_now, "arc_twist": arc_twist,
                         "ranges": b.units[attacker].items[w].weapon_range.as_ref().map(|r| json!({"min": r.min, "short": r.short, "medium": r.medium, "long": r.long}))}));
    }
    (rows, cands, per_action)
}

/// Apply the weapon settings in a declaration query / answer (modes, shots, bins, charge, artillery aim hexes).
fn apply_weapon_settings(b: &mut Battle, attacker: UnitId, target: UnitId, a: &Value) {
    let n = name(b, attacker);
    let by_weapon = |k: &str| -> Vec<(usize, Value)> { a.get(k).and_then(|v| v.as_object()).map(|o| o.iter().filter_map(|(w, v)| w.parse::<usize>().ok().map(|w| (w, v.clone()))).collect()).unwrap_or_default() };
    for (w, v) in by_weapon("modes") {
        if let Some(l) = v.as_str() {
            b.player.unit_mut(&n).munition.insert(w, l.to_string());
        }
    }
    for (w, v) in by_weapon("shots") {
        if let Some(s) = v.as_i64() {
            b.player.unit_mut(&n).shots.insert(w, s);
        }
    }
    for (w, v) in by_weapon("bins") {
        match v.as_u64() {
            Some(i) => {
                b.player.unit_mut(&n).bin.insert(w, i as usize);
            }
            None => {
                b.player.unit_mut(&n).bin.remove(&w);
            }
        }
    }
    if let Some(list) = a.get("charge").and_then(|v| v.as_array()) {
        b.player.unit_mut(&n).charge = list.iter().filter_map(|v| v.as_str().map(String::from)).collect();
    }
    for (w, v) in by_weapon("aim") {
        let from = crate::forces::hex_xy(b, attacker);
        let at = crate::forces::hex_xy(b, target);
        let turn = b.units[attacker].turn_number;
        b.distant_aims.retain(|x| !(x.shooter == attacker && x.weapon == w && x.target == target && x.turn == turn));
        if let Some(hex) = v.as_str().and_then(hex_of) {
            b.distant_aims.push(crate::princess_artillery::Aim { shooter: attacker, weapon: w, target, turn, from, at, aim: Some(hex) });
        }
    }
}

impl Controller for Screen {
    fn move_order(&mut self, b: &mut Battle, candidates: &[UnitId], _inner: &mut GladiatorBots) -> UnitId {
        let cands: Vec<UnitId> = candidates.to_vec();
        let req = json!({"kind": "move_order", "candidates": cands});
        // While the person looks over the candidates the page may ask for any of them: "reach" (what the unit could do, in the
        // movement question's own form) and "path" (a route). The answer may carry the move chosen for the unit ("plan").
        let mut views: std::collections::HashMap<UnitId, (MoveView, Option<Vec<String>>)> = Default::default();
        let (unit, plan) = self.ask(
            b,
            req,
            |b, q| {
                let kind = q["q"].as_str()?;
                if kind != "reach" && kind != "path" && kind != "way" {
                    return None;
                }
                let u = q["unit"].as_u64()? as usize;
                if !cands.contains(&u) {
                    return Some(json!({"error": "that unit is not waiting to move"}));
                }
                if b.units[u].prone {
                    return Some(json!({"error": "this unit is prone: it stands up first, and then you choose its move"}));
                }
                if !views.contains_key(&u) {
                    let edge = if b.units[u].hex.is_none() { b.units[u].home_edge.clone() } else { None };
                    let v = with_move_context(b, u, |b| move_view(b, u, None, edge.as_deref()));
                    views.insert(u, (v, edge));
                }
                let (v, edge) = &views[&u];
                if kind == "reach" {
                    return Some(json!({"view": v.req}));
                }
                if kind == "way" {
                    return Some(if edge.is_some() { json!({"error": "waypoints are not available for this move"}) } else { with_move_context(b, u, |b| way_query(b, u, q)) });
                }
                let r = with_move_context(b, u, |b| v.route(b, u, q, None, edge.as_deref()));
                Some(r.unwrap_or_else(|| json!({"error": "no route"})))
            },
            |_, a| {
                let u = a["unit"].as_u64().ok_or("which unit?")? as usize;
                if cands.contains(&u) { Ok((u, a.get("plan").filter(|p| p.is_object()).cloned())) } else { Err("that unit is not waiting to move".to_string()) }
            },
        );
        self.plan = plan.map(|p| (unit, p));
        unit
    }

    fn stand_up(&mut self, b: &mut Battle, mover: UnitId) -> bool {
        let tn = b.with_piloting(mover, |b| {
            let m = &b.units[mover];
            b.piloting + crate::piloting_rolls::preexisting_modifier(m) + crate::piloting_rolls::special_case_modifier(m) + crate::piloting_rolls::STAND_UP_MODIFIER
        });
        let m = &b.units[mover];
        let run = ms::compute_running_mp(m);
        let req = json!({"kind": "stand_up", "unit": mover, "name": name(b, mover), "tn": tn, "run": run, "pilot_hits": m.pilot_hits, "hex": m.hex});
        // Standing is part of the move (bug A2, Daniel 2026-11-22: "I should be able to undo a plan of stand"): while this question
        // waits the page may ask "reach" / "path" for the moves the unit would have after standing at the first attempt (2 MP spent,
        // p.51; any facing free, the engine's start facings), and answer with the stand and the move together ("plan"). Nothing is
        // rolled until that answer comes, so the plan can be undone freely. If the stand takes more attempts the plan may no longer
        // fit the MP left: the movement question then says so and asks again (ask_with's preset).
        let view = move_view(b, mover, Some((run - 2).max(0)), None);
        self.stand_plan = None;
        self.prone_facing = None;
        // the facings it could turn to if it stays prone, with their cost (1 MP a hexside, p.51)
        let turns: Vec<Value> = ["N", "NE", "SE", "S", "SW", "NW"]
            .iter()
            .filter_map(|f| crate::orchestrator::prone_turn_cost(&b.units[mover], f).map(|(mp, mode)| json!({"facing": f, "mp": mp, "mode": mode})))
            .collect();
        let mut req = req;
        req["prone_turns"] = json!(turns);
        let (stand, plan, facing) = self.ask(
            b,
            req,
            |b, q| match q["q"].as_str() {
                Some("reach") if q["unit"].as_u64().is_none_or(|u| u as usize == mover) => Some(json!({"view": view.req})),
                Some("path") => Some(view.route(b, mover, q, Some((run - 2).max(0)), None).unwrap_or_else(|| json!({"error": "no route"}))),
                _ => None,
            },
            |b, a| {
                let stand = a["stand"].as_bool().ok_or_else(|| "stand up, or stay prone?".to_string())?;
                // staying prone, it may turn (p.51)
                let facing = match a["facing"].as_str().filter(|_| !stand) {
                    Some(f) if f != b.units[mover].facing => {
                        crate::orchestrator::prone_turn_cost(&b.units[mover], f).ok_or_else(|| format!("it cannot turn to face {} on the ground this turn", f))?;
                        Some(f.to_string())
                    }
                    _ => None,
                };
                Ok((stand, a.get("plan").filter(|p| stand && p.is_object()).cloned(), facing))
            },
        );
        self.stand_plan = plan.map(|p| (mover, p));
        self.prone_facing = facing.map(|f| (mover, f));
        stand
    }

    fn prone_turn(&mut self, _b: &mut Battle, mover: UnitId) -> Option<String> {
        match self.prone_facing.take() {
            Some((u, f)) if u == mover => Some(f),
            _ => None,
        }
    }

    fn before_move(&mut self, b: &mut Battle, mover: UnitId) -> Option<String> {
        let m = &b.units[mover];
        if m.prone || !(equip::system_live(m, "masc") || equip::system_live(m, "supercharger")) {
            return None;
        }
        let req = json!({"kind": "boost", "unit": mover, "name": name(b, mover), "equipment": equipment_json(b, mover)});
        let on: bool = self.ask(b, req, |_, _| None, |b, a| {
            let on = a["use"].as_bool().ok_or("use it this turn?")?;
            apply_switches(b, mover, &json!({"boost": on}));
            Ok(on)
        });
        Some(format!("MASC / supercharger {}", if on { "on" } else { "off" }))
    }

    fn movement(&mut self, b: &mut Battle, mover: UnitId, other: UnitId, moves_first: bool, standup_mp: Option<i64>, entry_edge: Option<&[String]>, inner: &mut GladiatorBots) -> (Option<Pick>, String, PathGate) {
        let _ = (moves_first, other, &inner);
        let MoveView { req, opts, best, attacks } = move_view(b, mover, standup_mp, entry_edge);
        // a move planned while the unit was being chosen
        let stand_plan = self.stand_plan.take();
        let preset = match self.plan.take() {
            Some((u, p)) if u == mover => Some(p),
            // the move planned with the stand (only right after this unit stood up)
            _ => stand_plan.filter(|(u, _)| *u == mover && standup_mp.is_some()).map(|(_, p)| p),
        };
        enum Chosen {
            Stay,
            End(usize),
            Attack(Pick),
        }
        let chosen = {
            let best_ref = &best;
            let attacks_ref = &attacks;
            let view = MoveView { req: Value::Null, opts: opts.clone(), best: best.clone(), attacks: Vec::new() };
            self.ask_with(
                b,
                req,
                preset,
                |b, q| {
                    if q["q"].as_str() == Some("way") {
                        return Some(if standup_mp.is_some() || entry_edge.is_some() { json!({"error": "waypoints are not available for this move"}) } else { way_query(b, mover, q) });
                    }
                    if q["q"].as_str() != Some("path") {
                        return None;
                    }
                    view.route(b, mover, q, standup_mp, entry_edge)
                },
                |_, a| {
                    if let Some(at) = a.get("attack").filter(|x| x.is_object()) {
                        return attacks_ref
                            .iter()
                            .find(|(j, _)| j["target"] == at["target"] && j["kind"] == at["kind"] && j["hex"] == at["hex"] && j["facing"] == at["facing"])
                            .map(|(_, p)| Chosen::Attack(p.clone()))
                            .ok_or_else(|| "that charge or death from above is not possible".to_string());
                    }
                    if a["stay"].as_bool() == Some(true) {
                        if entry_edge.is_some() {
                            return Err("the unit has not entered the map yet: choose a hex on its edge".to_string());
                        }
                        return Ok(Chosen::Stay);
                    }
                    let k = (a["hex"].as_str().unwrap_or("").to_string(), a["facing"].as_str().unwrap_or("").to_string(), a["mode"].as_str().unwrap_or("").to_string());
                    best_ref.get(&k).map(|(i, _)| Chosen::End(*i)).ok_or_else(|| format!("{} {} ({}) is not a legal end of move", k.0, k.1, k.2))
                },
            )
        };
        let pick = match chosen {
            Chosen::End(i) => Some((opts[i].pick(), "chosen by the player")),
            Chosen::Attack(p) => Some((p, "charge / death from above, chosen by the player")),
            Chosen::Stay => match opts.iter().find(|o| o.mode == "Stand Still") {
                // stay put: the option the engine lists as Stand Still, if it lists one
                Some(o) => Some((o.pick(), "player stays put")),
                None => None,
            },
        };
        match pick {
            Some((pick, note)) => {
                let (psrs, hazard) = crate::ranged_combat::path_notes(b, mover, &pick, standup_mp, entry_edge);
                (Some(pick), note.into(), PathGate { psrs, hazard })
            }
            None => (None, "player stays put".into(), PathGate::default()),
        }
    }

    fn deploy(&mut self, b: &mut Battle, u: UnitId, good: &[String]) -> Option<(String, String)> {
        const FACINGS: [&str; 6] = ["N", "NE", "SE", "S", "SW", "NW"];
        let hexes: Vec<String> = good.to_vec();
        let req = json!({"kind": "deploy", "unit": u, "name": name(b, u), "hexes": hexes, "facing": b.units[u].facing});
        Some(self.ask(b, req, |_, _| None, |_, a| {
            let h = a["hex"].as_str().ok_or("which hex?")?;
            let f = a["facing"].as_str().unwrap_or("N");
            if !hexes.iter().any(|x| x == h) {
                return Err(format!("{} is not in your deployment area (or is taken)", h));
            }
            if !FACINGS.contains(&f) {
                return Err("which way does it face?".to_string());
            }
            Ok((h.to_string(), f.to_string()))
        }))
    }

    fn spot(&mut self, b: &mut Battle, u: UnitId, inner: &mut GladiatorBots) -> Option<(UnitId, bool)> {
        let cands = crate::spotting::spot_candidates(b, u);
        if cands.is_empty() {
            return inner.choose_spot(b, u);
        }
        let list: Vec<Value> = cands.iter().map(|(t, friends, dist)| json!({"id": t, "name": name(b, *t), "friends": friends, "distance": dist})).collect();
        let req = json!({"kind": "spot", "unit": u, "name": name(b, u), "candidates": list});
        let ids: Vec<UnitId> = cands.iter().map(|c| c.0).collect();
        self.ask(b, req, |_, _| None, |_, a| match a["target"].as_u64() {
            None => Ok(None),
            Some(t) if ids.contains(&(t as usize)) => Ok(Some((t as usize, a["fires"].as_bool().unwrap_or(true)))),
            Some(_) => Err("that enemy cannot be spotted".to_string()),
        })
    }

    fn tag(&mut self, b: &mut Battle, attacker: UnitId, cands: &[crate::tag::TagCandidate]) -> Option<(UnitId, &'static str)> {
        let list: Vec<Value> = cands.iter().map(|c| json!({"id": c.target, "name": name(b, c.target), "tn_mech": c.tn_mech, "tn_hex": c.tn_hex, "distance": crate::forces::distance(b, attacker, c.target)})).collect();
        let req = json!({"kind": "tag", "unit": attacker, "name": name(b, attacker), "candidates": list});
        let cs: Vec<(UnitId, bool, bool)> = cands.iter().map(|c| (c.target, c.tn_mech.is_some(), c.tn_hex.is_some())).collect();
        self.ask(b, req, |_, _| None, |_, a| match a["target"].as_u64() {
            None => Ok(None),
            Some(t) => {
                let aim = if a["aim"].as_str() == Some("hex") { "hex" } else { "mech" };
                match cs.iter().find(|c| c.0 == t as usize) {
                    Some(c) if (aim == "hex" && c.2) || (aim == "mech" && c.1) => Ok(Some((t as usize, aim))),
                    _ => Err("TAG cannot designate that".to_string()),
                }
            }
        })
    }

    fn target(&mut self, b: &mut Battle, attacker: UnitId, _inner: &mut GladiatorBots) -> Option<UnitId> {
        let enemies: Vec<UnitId> = crate::forces::enemies_of(b, attacker).into_iter().filter(|&e| b.units[e].hex.is_some() && !b.is_destroyed(e)).collect();
        if enemies.is_empty() {
            return None;
        }
        let list: Vec<Value> = enemies.iter().map(|&e| json!({"id": e, "name": name(b, e), "distance": crate::forces::distance(b, attacker, e)})).collect();
        let req = json!({"kind": "target", "unit": attacker, "name": name(b, attacker), "enemies": list});
        // the page may look at the weapons (their arcs and range bands) and the real to-hit numbers before it picks (Daniel, 2026-11-22)
        self.ask(b, req, |b, q| target_query(b, attacker, &enemies, q, None), |_, a| match a["target"].as_u64() {
            None => Ok(None),
            Some(t) if enemies.contains(&(t as usize)) => Ok(Some(t as usize)),
            Some(_) => Err("that is not an enemy you can target".to_string()),
        })
    }

    /// Further targets after the primary: asked again as a target question marked `secondary` until the person answers no target.
    fn secondary(&mut self, b: &mut Battle, attacker: UnitId, primary: UnitId, done: &[UnitId], _inner: &mut GladiatorBots) -> Option<UnitId> {
        let all: Vec<UnitId> = crate::forces::enemies_of(b, attacker).into_iter().filter(|&e| b.units[e].hex.is_some() && !b.is_destroyed(e)).collect();
        let open: Vec<UnitId> = all.iter().copied().filter(|e| !done.contains(e) && crate::split_fire::refusal(b, attacker, *e).is_none()).collect();
        if open.is_empty() {
            return None;
        }
        let list: Vec<Value> = open.iter().map(|&e| json!({"id": e, "name": name(b, e), "distance": crate::forces::distance(b, attacker, e)})).collect();
        let req = json!({"kind": "target", "secondary": true, "primary": primary, "unit": attacker, "name": name(b, attacker), "enemies": list});
        self.ask(b, req, |b, q| target_query(b, attacker, &all, q, Some(primary)), |_, a| match a["target"].as_u64() {
            None => Ok(None),
            Some(t) if open.contains(&(t as usize)) => Ok(Some(t as usize)),
            Some(_) => Err("that is not a target you can still fire at".to_string()),
        })
    }

    fn declaration(&mut self, b: &mut Battle, ctx: &DeclCtx, planner: &mut Planner, attacker: UnitId, target: UnitId, _inner: &mut GladiatorBots) -> DeclChoice {
        let (rows, ..) = weapon_rows(b, ctx, planner, attacker);
        let req = decl_req_json(b, ctx, rows, attacker, target);
        let result: (Vec<usize>, Vec<crate::weapon_selection::Candidate>, Vec<HashSet<usize>>) = {
            let planner_cell = std::cell::RefCell::new(planner);
            self.ask(
                b,
                req,
                |b, q| {
                    if q["q"].as_str() != Some("set") {
                        return None;
                    }
                    apply_weapon_settings(b, attacker, target, q);
                    let mut p = planner_cell.borrow_mut();
                    let (rows, ..) = weapon_rows(b, ctx, &mut p, attacker);
                    Some(json!({"weapons": rows}))
                },
                |b, a| {
                    apply_weapon_settings(b, attacker, target, a);
                    let mut p = planner_cell.borrow_mut();
                    let (_, cands, per_action) = weapon_rows(b, ctx, &mut p, attacker);
                    let ids: Vec<usize> = a["weapons"].as_array().ok_or("which weapons?")?.iter().filter_map(|v| v.as_u64().map(|x| x as usize)).collect();
                    for id in &ids {
                        if !cands.iter().any(|c| c.w == *id) {
                            return Err(format!("weapon {} cannot fire at this target", id));
                        }
                    }
                    Ok((ids, cands, per_action))
                },
            )
        };
        let (ids, cands, per_action) = result;
        // the twist / flip happens by itself (Daniel): the first arc action that lets every chosen weapon fire; if none does,
        // the one that lets most fire, and the rest are dropped
        let mut best = (0usize, usize::MAX);
        for (i, un) in per_action.iter().enumerate() {
            let lost = ids.iter().filter(|w| un.contains(w)).count();
            if lost < best.1 {
                best = (i, lost);
            }
        }
        let (key, action) = ctx.arc_choices[best.0].clone();
        let fired: Vec<usize> = ids.into_iter().filter(|w| !per_action[best.0].contains(w)).collect();
        let exp: f64 = fired.iter().filter_map(|w| cands.iter().find(|c| c.w == *w)).map(|c| c.value).sum();
        let heat: i64 = fired.iter().filter_map(|w| cands.iter().find(|c| c.w == *w)).map(|c| c.heat).sum();
        DeclChoice { weapons: fired, exp_dmg: exp, weapon_heat: heat, key_torso_arc: key.torso_arc, action, phys_names: vec![], phys_value: 0.0, held: HashSet::default() }
    }

    fn physical(&mut self, b: &mut Battle, attacker: UnitId, target: UnitId, _inner: &mut GladiatorBots) -> PhysicalChoice {
        if b.is_destroyed(attacker) || b.is_destroyed(target) || b.units[attacker].hex == b.units[target].hex {
            return None;
        }
        let groups = crate::physical::attack_options(b, attacker, target, None);
        if groups.is_empty() {
            return None;
        }
        let base = crate::physical::base_tn_for(b, attacker, target);
        let kinds: Vec<Value> = groups
            .iter()
            .map(|(k, opts)| {
                json!({"kind": k, "options": opts.iter().map(|o| json!({"name": o.name, "tn": base + o.mod_, "damage": o.damage.f(), "table": o.table, "heat": o.heat})).collect::<Vec<_>>()})
            })
            .collect();
        let req = json!({"kind": "physical", "unit": attacker, "name": name(b, attacker), "target": target, "target_name": name(b, target), "base_tn": base, "kinds": kinds});
        let pick: Option<String> = self.ask(b, req, |_, _| None, |_, a| match a["kind"].as_str() {
            None => Ok(None),
            Some(k) if groups.contains_key(k) => Ok(Some(k.to_string())),
            Some(k) => Err(format!("no '{}' attack is possible", k)),
        });
        let k = pick?;
        let opts = groups.get(k.as_str())?.clone();
        // punches may use both arms; any other kind swings once (the best of its options by damage)
        let chosen = if k == "punch" { opts } else { vec![opts.iter().max_by(|x, y| x.damage.f().partial_cmp(&y.damage.f()).unwrap()).unwrap().clone()] };
        Some((base, chosen, ArcAction { ..crate::arcs::current_action(&b.units[attacker]) }))
    }

    fn end_phase(&mut self, b: &mut Battle, u: UnitId, weapon_heat: i64) -> Option<String> {
        if b.is_destroyed(u) || b.units[u].shutdown {
            return None;
        }
        let m = &b.units[u];
        let projected = (m.current_heat + m.movement_heat + weapon_heat - ms::active_heat_sinks(m)).max(0);
        let eq = equipment_json(b, u);
        let pods = eq["coolant"]["pods"].as_i64().unwrap_or(0);
        let radical = eq["radical"]["live"].as_bool().unwrap_or(false);
        let jam = eq["jammed"].as_array().is_some_and(|j| !j.is_empty());
        // asked only when there is something to decide: expected heat with coolant pods or radical sinks to answer it, a jam
        if !((projected > 0 && (pods > 0 || radical)) || jam) {
            return None;
        }
        let req = json!({"kind": "end_phase", "unit": u, "name": name(b, u), "equipment": eq,
                         "heat": {"now": m.current_heat, "movement": m.movement_heat, "weapons": weapon_heat, "sinks": ms::active_heat_sinks(m), "projected": projected}});
        self.ask(b, req, |_, _| None, |b, a| {
            if let Some(sw) = a.get("switches") {
                apply_switches(b, u, sw);
            }
            Ok(())
        });
        Some(format!("projected heat {}", projected))
    }
}
