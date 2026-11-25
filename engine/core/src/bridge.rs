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
///
/// With `compact_base` (each unit's dump at the start), the units go as compact states ("compact_units"), not dumps.
pub fn state_json(b: &Battle, last_board: &mut Option<String>, compact_base: Option<&[Value]>) -> Value {
    state_json_mode(b, last_board, compact_base, false)
}

/// `state_json`, or with `view` the MegaMek views of the units (`megamek_view`), the turn and the dice only.
pub fn state_json_mode(b: &Battle, last_board: &mut Option<String>, compact_base: Option<&[Value]>, view: bool) -> Value {
    if view {
        // the battle's own turn counter is not kept up to date by the engine (b.turn); the units' is
        let turn = b.units.iter().map(|m| m.turn_number).max().unwrap_or(0);
        let mut v = json!({"turn": turn, "megamek_units": (0..b.units.len()).map(|u| megamek_view(b, u)).collect::<Vec<_>>(),
                           "move_queue": b.move_queue});
        if let Some(d) = b.dice.borrow().save() {
            v["dice"] = d;
        }
        return v;
    }
    let name = |i: usize| unit_name(b, i);
    let units: Vec<Value> = b.units.iter().map(|m| m.to_json(&name)).collect();
    let (key, units) = match compact_base {
        Some(base) => ("compact_units", units.iter().zip(base).map(|(d, b0)| compact_unit(d, b0)).collect()),
        None => ("units", units),
    };
    let mut v = json!({
        "turn": b.turn,
        key: units,
        "smoky": b.smoky.iter().collect::<Vec<_>>(),
        "broken_crust": b.broken_crust,
        "limbs_on_ground": b.limbs_on_ground.iter().map(|(k, n)| json!([k, n])).collect::<Vec<_>>(),
        "move_queue": b.move_queue,
        "pushed_this_phase": b.pushed_this_phase,
        "spots": b.spots.iter().map(|s| json!([s.spotter, s.target, s.fires, s.tag])).collect::<Vec<_>>(),
        "indirect_pairs": b.indirect_pairs.iter().map(|(a, t)| json!([a, t])).collect::<Vec<_>>(),
        "split_fire": b.split_fire.iter().map(|s| json!([s.attacker, s.primary, s.used, s.heat])).collect::<Vec<_>>(),
        "pending_artillery": b.pending_artillery.iter().map(|s| json!([s.attacker, s.weapon, s.fired_turn, [s.impact.0, s.impact.1], [s.from.0, s.from.1], s.tn, s.damage, s.splash, s.arc_steps])).collect::<Vec<_>>(),
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

/// Puts a `state_json` into a battle. The units are rebuilt from their dumps (or from `base`, each unit's dump at the
/// start, plus a compact state); a new board drops the remembered lines of sight and movement tables (they rebuild to
/// the same values).
pub fn load_state(b: &mut Battle, v: &Value, base: &[Value]) {
    // A MegaMek game sends its own view of each unit instead (B3): written into this battle's units, the rest kept.
    if let Some(views) = v.get("megamek_units") {
        for view in views.as_array().expect("megamek_units") {
            apply_megamek_view(b, view);
        }
        // A new turn: the start-of-turn bookkeeping the engine does in play_turn (each unit's turn number - Hydra's
        // Waiting counts turns with it - and the damage snapshot piloting rolls use). MegaMek's rounds count from 0,
        // our turns from 1 (GameView sends ours).
        if let Some(d) = v.get("dice") {
            *b.dice.borrow_mut() = Box::new(PcgDice::restore(d));
        }
        // the units still to move this phase, in order (Hydra's forecast reads it); MegaMek's turn order gives it
        if let Some(q) = v.get("move_queue").and_then(|q| q.as_array()) {
            b.move_queue = q.iter().filter_map(|u| u.as_u64().map(|u| u as UnitId)).collect();
        }
        if let Some(t) = v.get("turn").and_then(|t| t.as_i64()) {
            if t != b.turn {
                // each unit's HP history (Hydra's forecast reads it), kept as play_turn keeps it: the HP when the game
                // starts, then one entry at the end of every turn (here: when the next turn is first seen)
                for u in 0..b.units.len() {
                    let hp = crate::orchestrator::effective_hp(b, u);
                    if b.turn == 0 || b.units[u].hp_log.is_none() {
                        b.units[u].hp_log = Some(vec![hp]);
                    } else {
                        for _ in b.turn..t {
                            b.units[u].hp_log.get_or_insert_with(Vec::new).push(hp);
                        }
                    }
                }
                b.turn = t;
                for u in 0..b.units.len() {
                    crate::piloting_rolls::snapshot_preexisting_damage(&mut b.units[u]);
                    crate::equipment_systems::start_turn(b, u, t);
                }
            }
        }
        return;
    }
    let names: Vec<String> = (0..b.units.len()).map(|i| unit_name(b, i)).collect();
    let index = |n: &str| names.iter().position(|x| x == n).unwrap_or_else(|| panic!("bridge state: no unit {}", n));
    let dumps: Vec<Value> = match v.get("compact_units") {
        Some(c) => c.as_array().unwrap().iter().zip(base).map(|(c, b0)| apply_compact(b0, c)).collect(),
        None => v["units"].as_array().expect("bridge state: units").clone(),
    };
    assert_eq!(dumps.len(), b.units.len(), "bridge state: the roster changed size");
    b.units = dumps.iter().map(|u| Mech::from_json(u, &index)).collect();
    b.turn = v["turn"].as_i64().unwrap();
    b.smoky = v["smoky"].as_array().unwrap().iter().map(|h| h.as_str().unwrap().to_string()).collect();
    b.broken_crust = v["broken_crust"].as_array().unwrap().iter().map(|h| h.as_str().unwrap().to_string()).collect();
    b.limbs_on_ground = v["limbs_on_ground"].as_array().unwrap().iter().map(|p| (p[0].as_str().unwrap().to_string(), p[1].as_i64().unwrap())).collect();
    b.move_queue = v["move_queue"].as_array().unwrap().iter().map(|u| u.as_u64().unwrap() as UnitId).collect();
    b.pushed_this_phase = v.get("pushed_this_phase").and_then(|p| p.as_array()).map(|p| p.iter().map(|u| u.as_u64().unwrap() as UnitId).collect()).unwrap_or_default();
    b.spots = v.get("spots").and_then(|p| p.as_array()).map(|p| p.iter().map(|s| crate::spotting::Spot {
        spotter: s[0].as_u64().unwrap() as UnitId,
        target: s[1].as_u64().unwrap() as UnitId,
        fires: s[2].as_bool().unwrap(),
        tag: s[3].as_bool().unwrap(),
    }).collect()).unwrap_or_default();
    b.indirect_pairs = v.get("indirect_pairs").and_then(|p| p.as_array()).map(|p| p.iter().map(|x| (x[0].as_u64().unwrap() as UnitId, x[1].as_u64().unwrap() as UnitId)).collect()).unwrap_or_default();
    b.split_fire = v.get("split_fire").and_then(|p| p.as_array()).map(|p| p.iter().map(|s| crate::split_fire::SplitState {
        attacker: s[0].as_u64().unwrap() as UnitId,
        primary: s[1].as_u64().unwrap() as UnitId,
        used: s[2].as_array().unwrap().iter().map(|w| w.as_u64().unwrap() as usize).collect(),
        heat: s[3].as_i64().unwrap(),
    }).collect()).unwrap_or_default();
    b.pending_artillery = v.get("pending_artillery").and_then(|p| p.as_array()).map(|p| p.iter().map(|s| {
        let i = |k: usize| s[k].as_i64().unwrap();
        let xy = |k: usize| (s[k][0].as_i64().unwrap(), s[k][1].as_i64().unwrap());
        let mut arc = [0i64; 6];
        for (d, a) in arc.iter_mut().enumerate() {
            *a = s[8][d].as_i64().unwrap();
        }
        crate::artillery::PendingStrike { attacker: i(0) as UnitId, weapon: i(1) as usize, fired_turn: i(2), impact: xy(3), from: xy(4), tn: i(5), damage: i(6), splash: i(7), arc_steps: arc }
    }).collect()).unwrap_or_default();
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
// The COMPACT unit state (stage B3): only what changes during a battle
// =============================================================================================================
// A unit's full dump is ~18 KB, nearly all of it fixed by its .mtf (chassis, slots, every equipment object's stats). The
// compact state is just what a battle changes: the UNIT_FIELDS, the critical slots whose entry differs from the unit at
// the start (a destroyed slot), and the ITEM_FIELDS of each piece of equipment, by address. The lists were MEASURED
// (2026-11-12): every reference battle recorded, every field of every dump compared with its value at the battle's
// start; these are all that ever differed. Plus `home_edge` / `home_edge_row`, set when the units deploy (the side's
// deployment edge; the survey began after deployment, the compact-mode check found them), and `stuck` (stuck in
// terrain: first seen in the 8 v 8 battles, which the survey left out; found the same way). The parity check in compact mode (`--bridge-parity --bridge-compact`) proves
// the lists are enough: decided from compact states, every answer must still be the battle's. A field a later change
// makes move must be added here, or that check fails. This is what the Java side has to send per unit (and what a
// Combat Lab save of a unit's state needs).

/// The fields of a unit dump that change during a battle (everything else comes from the .mtf and the scenario).
pub const UNIT_FIELDS: &[&str] = &["_ams_used", "arc_action", "arc_action_locked", "armor_at_turn_start", "armored_slots", "arms_flipped", "autocannon_crits", "blocked_hex", "breached_locations", "breached_slot_set", "capacitor_heat", "capacitors", "cause_of_death", "charging", "club", "cockpit_hit", "crew", "current_heat", "deactivated_heat_sinks", "deferred_end_of_move", "destroyed", "destroyed_heat_sinks", "destroyed_hip_locations", "destroyed_jump_jet_ids", "destroyed_leg_actuators", "destroyed_slot_info", "dfa", "engine_hits", "equipment_systems", "escalating_turns", "explosions", "facing", "gyro_hits", "heat_fire_modifier", "heat_managed", "heat_mp_penalty", "hex", "home_edge", "home_edge_row", "hp_log", "jump_only", "locations", "magma_entered", "mech_turret_dir", "modular_armor", "move_fc", "move_mode", "moved_this_turn", "movement_heat", "mp_spent", "narc_pods", "other_unit_hexes", "outside_heat", "pfd_turns_used", "pilot_hits", "pre_attack_phase_snapshot", "preexisting_damage_snapshot", "prone", "radical_on", "round_capable", "run_mp_multiplier", "secondary_hits", "severed_limbs", "severed_seen", "shield_raised", "shutdown", "started_in_liquid", "stuck", "systems_off", "systems_used_this_turn", "tag_designated", "taser_interference_until", "taser_shutdown_until", "torso_twist", "tsemp_hits", "tsemp_interference_until", "tsm_active", "turn_number", "turret_last_offset", "unjamming", "weapons_fired_this_turn"];

/// The fields of an equipment object that change during a battle (shots, jams, explosions, capacitor charge...).
pub const ITEM_FIELDS: &[&str] = &["capacitor", "charged", "charging", "damage_per_shot", "exploded", "explosion_damage", "fired_once", "firing", "heat", "is_explosive", "jammed", "linked_ppc", "modular_points", "partner", "partner_of_slot", "pod_used", "shield_dc", "shots_left", "tsemp_recharge_until"];

/// Every equipment object in a dump (with an `_addr`), wherever it sits, for `f` - inner objects first, so values `f`
/// writes into an object (an item field can hold other items: `partner`, `linked_ppc`) are never walked into again.
fn each_item(v: &mut Value, f: &mut dyn FnMut(&mut serde_json::Map<String, Value>)) {
    match v {
        Value::Object(m) => {
            for x in m.values_mut() {
                each_item(x, f);
            }
            if m.get("_type").and_then(|t| t.as_str()) == Some("Equipment") && m.contains_key("_addr") {
                f(m);
            }
        }
        Value::Array(a) => {
            for x in a.iter_mut() {
                each_item(x, f);
            }
        }
        _ => {}
    }
}

/// Each equipment object's MAIN copy, by address: the one in a critical slot (a slot holds an item, or on a superheavy
/// a list of them). The same item can also appear nested inside other fields (`capacitors`, a weapon's `partner`),
/// where the dump writes a shallower copy with fewer fields; the main copy is the one to read.
fn main_items(dump: &Value) -> std::collections::HashMap<String, serde_json::Map<String, Value>> {
    let mut out: std::collections::HashMap<String, serde_json::Map<String, Value>> = Default::default();
    let mut take = |v: &Value| {
        if let Some(m) = v.as_object() {
            if let Some(a) = m.get("_addr").and_then(|a| a.as_str()) {
                out.entry(a.to_string()).or_insert_with(|| m.clone());
            }
        }
    };
    if let Some(crits) = dump["crits"].as_object() {
        for list in crits.values() {
            for entry in list.as_array().into_iter().flatten() {
                match entry.as_array() {
                    Some(inner) => inner.iter().for_each(&mut take),
                    None => take(entry),
                }
            }
        }
    }
    out
}

/// A unit's compact state against `base`, its dump at the start: {"fields": {...}, "absent": [...], "slots": {"Loc#i":
/// entry}, "items": {addr: {field: value}}}. Only items and slots that differ from the base are sent.
pub fn compact_unit(dump: &Value, base: &Value) -> Value {
    let mut fields = serde_json::Map::new();
    let mut absent = Vec::new();
    for k in UNIT_FIELDS {
        match dump.get(*k) {
            Some(v) => {
                fields.insert(k.to_string(), v.clone());
            }
            None => absent.push(*k),
        }
    }
    let mut slots = serde_json::Map::new();
    if let (Some(now), Some(then)) = (dump["crits"].as_object(), base["crits"].as_object()) {
        for (loc, list) in now {
            for (i, entry) in list.as_array().unwrap().iter().enumerate() {
                let was = then.get(loc).and_then(|l| l.get(i));
                let is_item = entry.get("_addr").is_some() && was.and_then(|w| w.get("_addr")) == entry.get("_addr");
                if !is_item && was != Some(entry) {
                    slots.insert(format!("{}#{}", loc, i), entry.clone());
                }
            }
        }
    }
    let base_items = main_items(base);
    let mut items = serde_json::Map::new();
    let mut now: Vec<(String, serde_json::Map<String, Value>)> = main_items(dump).into_iter().collect();
    now.sort_by(|a, b| a.0.cmp(&b.0));
    for (addr, m) in now {
        let was = base_items.get(&addr);
        let mut changed = serde_json::Map::new();
        for f in ITEM_FIELDS {
            if let Some(v) = m.get(*f) {
                if was.and_then(|w| w.get(*f)) != Some(v) {
                    changed.insert(f.to_string(), v.clone());
                }
            }
        }
        if !changed.is_empty() {
            items.insert(addr, Value::Object(changed));
        }
    }
    json!({"fields": fields, "absent": absent, "slots": slots, "items": items})
}

/// Where a unit rebuilt from its compact state differs from its real dump: the top-level fields, and inside `crits` the
/// slots / items (by address and field). Empty when the compact state carried everything (the check reports these).
pub fn rebuild_gaps(real: &Value, rebuilt: &Value) -> Vec<String> {
    let mut out = Vec::new();
    let (Some(a), Some(b)) = (real.as_object(), rebuilt.as_object()) else { return vec!["(not an object)".into()] };
    for k in a.keys().chain(b.keys().filter(|k| !a.contains_key(*k))) {
        if a.get(k) == b.get(k) {
            continue;
        }
        if k != "crits" {
            out.push(k.clone());
            continue;
        }
        let mut items = |v: &Value| {
            let mut t: std::collections::BTreeMap<String, serde_json::Map<String, Value>> = Default::default();
            each_item(&mut v.clone(), &mut |m| {
                t.entry(m["_addr"].as_str().unwrap().to_string()).or_insert_with(|| m.clone());
            });
            t
        };
        let (ia, ib) = (items(&a["crits"]), items(&b["crits"]));
        for (addr, m) in &ia {
            for (f, v) in m {
                if ib.get(addr).and_then(|x| x.get(f)) != Some(v) {
                    out.push(format!("item.{}", f));
                }
            }
        }
        if out.iter().all(|g| !g.starts_with("item.")) {
            out.push("crits (a slot)".into());
        }
    }
    out.sort();
    out.dedup();
    out
}

/// The full dump back from `base` (the unit at the start) and a compact state.
pub fn apply_compact(base: &Value, c: &Value) -> Value {
    let mut d = base.clone();
    let o = d.as_object_mut().unwrap();
    for (k, v) in c["fields"].as_object().unwrap() {
        o.insert(k.clone(), v.clone());
    }
    for k in c["absent"].as_array().unwrap() {
        o.remove(k.as_str().unwrap());
    }
    for (key, entry) in c["slots"].as_object().unwrap() {
        let (loc, i) = key.rsplit_once('#').unwrap();
        d["crits"][loc][i.parse::<usize>().unwrap()] = entry.clone();
    }
    // A changed item's MAIN copy (in its critical slot) gets every changed field, even one it did not have at the start
    // (`pod_used` appears when a pod is used); copies nested inside it (a `partner`...) get only the fields they have,
    // being shallower. Fields sent whole in "fields" (`capacitors`...) already hold their exact copies: not touched.
    let items = c["items"].as_object().unwrap();
    let mut nested = |m: &mut serde_json::Map<String, Value>| {
        if let Some(changed) = items.get(m["_addr"].as_str().unwrap()) {
            for (f, v) in changed.as_object().unwrap() {
                if let Some(slot) = m.get_mut(f) {
                    *slot = v.clone();
                }
            }
        }
    };
    let mut main = |v: &mut Value| {
        let Some(m) = v.as_object_mut() else { return };
        for x in m.values_mut() {
            each_item(x, &mut nested);
        }
        if let Some(changed) = m.get("_addr").and_then(|a| a.as_str()).and_then(|a| items.get(a)) {
            for (f, v) in changed.as_object().unwrap() {
                m.insert(f.clone(), v.clone());
            }
        }
    };
    if let Some(crits) = d["crits"].as_object_mut() {
        for list in crits.values_mut() {
            for entry in list.as_array_mut().into_iter().flatten() {
                match entry.as_array_mut() {
                    Some(inner) => inner.iter_mut().for_each(&mut main),
                    None => main(entry),
                }
            }
        }
    }
    d
}

// =============================================================================================================
// MegaMek's view of a unit (stage B3, Java half): what a MegaMek game knows, written into the session's own unit
// =============================================================================================================
// A MegaMek game cannot send our unit records: it sends what IT knows about each unit (btbridge.GameView writes it):
//   {"name", "hex" ("0905", null off the board), "facing" 0-5, "prone", "shutdown", "heat", "destroyed",
//    "locations": {"Left Torso": {"armor", "rear", "structure", "destroyed"}}, "destroyed_slots": [["Left Torso", 3]],
//    "ammo": {"Left Torso#0": shots}, "jammed": ["Right Arm#4"], "pilot_hits", "conscious",
//    "moved": "Walk" / "Run" / "Jump" / "Stand Still" (this turn, or null), "done" (has had its Movement Phase turn this round; optional), "mp_spent", "twist" (-1, 0, 1)}
// Everything else stays as the session's own copy of the unit has it (built from the .mtf when the game started).
// Destroyed slots go through the engine's own slot loss (`destroy_slot_quietly`), so engine / gyro / heat sink / jump
// jet counters follow; no explosion, MegaMek resolved it. Our own bookkeeping that MegaMek does not have (snapshots
// taken at phase starts, hp_log...) is NOT kept up to date this way: decisions in a MegaMek game are made on MegaMek's
// facts plus that approximation (spec Section 3c).

/// The MegaMek view of one of OUR units (what btbridge.GameView would send for it): the parity check's view mode
/// (`--bridge-view`) sends these instead of full records, to measure how often decisions made from MegaMek's facts
/// alone agree with decisions made from the whole record.
pub fn megamek_view(b: &Battle, u: UnitId) -> Value {
    let m = &b.units[u];
    let name = unit_name(b, u);
    if m.destroyed || m.hex.is_none() {
        return json!({"name": name, "destroyed": m.destroyed, "hex": m.hex, "home_edge": m.home_edge, "home_edge_row": m.home_edge_row});
    }
    let mut locations = serde_json::Map::new();
    for (loc, l) in &m.locations {
        let mut o = json!({"armor": l.armor.f() as i64, "structure": l.structure.f() as i64, "destroyed": l.destroyed});
        if let Some(r) = &l.rear_armor {
            o["rear"] = json!(r.f() as i64);
        }
        locations.insert(loc.clone(), o);
    }
    let mut slots = Vec::new();
    for (loc, list) in &m.crits {
        for (i, s) in list.iter().enumerate() {
            if s.is_name("DESTROYED") {
                slots.push(json!([loc, i]));
            }
        }
    }
    let (mut ammo, mut jammed) = (serde_json::Map::new(), Vec::new());
    for (id, addr) in m.item_addresses() {
        let it = &m.items[id];
        if it.category.as_deref() == Some("ammo") {
            if let Some(n) = it.shots_left {
                ammo.insert(addr.clone(), json!(n));
            }
        }
        if it.jammed == Some(true) {
            jammed.push(addr);
        }
    }
    json!({"name": name, "hex": m.hex, "facing": crate::hex_geometry::compass_to_facing(&m.facing).unwrap_or(0),
           "prone": m.prone, "shutdown": m.shutdown, "heat": m.current_heat, "destroyed": false,
           "locations": locations, "destroyed_slots": slots, "ammo": ammo, "jammed": jammed,
           "pilot_hits": m.pilot_hits, "conscious": !m.crew.get("pilot").is_some_and(|p| p.unconscious),
           "moved": if m.moved_this_turn { m.move_mode.clone() } else { "Stand Still".into() }, "done": m.moved_this_turn, "mp_spent": m.mp_spent,
           "hexes_moved": m.move_fc,
           "fired": m.weapons_fired_this_turn.as_ref().map(|f| { let a = m.item_addresses(); f.iter().filter_map(|id| a.get(id).cloned()).collect::<Vec<_>>() }),
           "twist": m.torso_twist.unwrap_or(0), "home_edge": m.home_edge, "home_edge_row": m.home_edge_row,
           "extra": view_extra(b, u)})
}

/// MEASUREMENT ONLY (the view-mode check): BRIDGE_VIEW_EXTRA=field,field adds those raw record fields to each view,
/// to find which of our own bookkeeping fields the decisions depend on (agreement rises when the right one is added).
/// A MegaMek game never sends these.
fn view_extra(b: &Battle, u: UnitId) -> Value {
    let Ok(list) = std::env::var("BRIDGE_VIEW_EXTRA") else { return Value::Null };
    let name = |i: usize| unit_name(b, i);
    let dump = b.units[u].to_json(&name);
    let mut out = serde_json::Map::new();
    for k in list.split(',').filter(|k| !k.is_empty()) {
        if let Some(v) = dump.get(k) {
            out.insert(k.to_string(), v.clone());
        }
    }
    Value::Object(out)
}

/// Writes one unit's MegaMek view into the battle (by its name).
pub fn apply_megamek_view(b: &mut Battle, v: &Value) {
    use crate::pyfmt::Num;
    let name = v["name"].as_str().expect("megamek view: name");
    let Some(u) = b.units.iter().position(|m| m.side_name.as_deref() == Some(name)) else { panic!("megamek view: no unit {}", name) };
    if let Some(locs) = v.get("locations").and_then(|l| l.as_object()) {
        for (loc, s) in locs {
            if let Some(l) = b.units[u].locations.get_mut(loc) {
                l.armor = Num::I(s["armor"].as_i64().unwrap_or(0));
                if l.rear_armor.is_some() {
                    l.rear_armor = s["rear"].as_i64().map(Num::I);
                }
                l.structure = Num::I(s["structure"].as_i64().unwrap_or(0));
                l.destroyed = s["destroyed"].as_bool().unwrap_or(false);
            }
        }
    }
    for d in v.get("destroyed_slots").and_then(|d| d.as_array()).into_iter().flatten() {
        crate::damage_resolution::destroy_slot_quietly(b, u, d[0].as_str().unwrap(), d[1].as_u64().unwrap() as usize);
    }
    let by_addr: std::collections::HashMap<String, usize> = b.units[u].item_addresses().into_iter().map(|(id, a)| (a, id)).collect();
    if let Some(ammo) = v.get("ammo").and_then(|a| a.as_object()) {
        for (addr, shots) in ammo {
            if let Some(id) = by_addr.get(addr) {
                b.units[u].items[*id].shots_left = shots.as_i64();
            }
        }
    }
    if let Some(jammed) = v.get("jammed").and_then(|j| j.as_array()) {
        let jammed: Vec<&str> = jammed.iter().filter_map(|x| x.as_str()).collect();
        for (addr, id) in &by_addr {
            let it = &mut b.units[u].items[*id];
            if it.jammed.is_some() || jammed.contains(&addr.as_str()) {
                it.jammed = Some(jammed.contains(&addr.as_str()));
            }
        }
    }
    let m = &mut b.units[u];
    m.hex = v.get("hex").and_then(|h| h.as_str()).map(|h| h.to_string());
    if let Some(f) = v.get("facing").and_then(|f| f.as_i64()) {
        m.facing = crate::hex_geometry::facing_to_compass(f.rem_euclid(6)).unwrap().to_string();
    }
    let flag = |k: &str, d: bool| v.get(k).and_then(|x| x.as_bool()).unwrap_or(d);
    m.prone = flag("prone", m.prone);
    m.shutdown = flag("shutdown", m.shutdown);
    m.destroyed = flag("destroyed", m.destroyed);
    if let Some(h) = v.get("heat").and_then(|h| h.as_i64()) {
        m.current_heat = h;
        // what the heat does this turn (Heat Scale: MP, to-hit, TSM): our engine sets these in its own Heat Phase
        // (heat::apply_heat_effects), which a MegaMek game never runs here. Without them our bots planned at full MP and
        // without the to-hit penalty when hot - routes MegaMek then refused ("would not take the route": a 4-MP backward
        // walk at heat 6-7, where MegaMek's walk is 3; session 30, Hydra v CASPAR).
        m.heat_mp_penalty = crate::heat::mp_penalty_for(h);
        m.heat_fire_modifier = crate::heat::fire_modifier_for(h);
        m.tsm_active = m.has_tsm && crate::equipment_systems::tsm_active_for(m, h);
    }
    if let Some(p) = v.get("pilot_hits").and_then(|p| p.as_i64()) {
        m.pilot_hits = p;
    }
    if let Some(c) = v.get("conscious").and_then(|c| c.as_bool()) {
        if let Some(pilot) = m.crew.get_mut("pilot") {
            pilot.unconscious = !c;
        }
    }
    if let Some(mode) = v.get("moved").and_then(|x| x.as_str()) {
        m.move_mode = mode.to_string();
        // "done" (2026-11-19, CASPAR's review): the unit has had its Movement Phase turn this round - MegaMek's Entity.isDone()
        // in the Movement Phase, true for every unit after it - which is what moved_this_turn means in our engine (a unit that
        // stood still has moved too). An older state line without it falls back to the movement mode, which missed a unit
        // that stood still (CASPAR's cover bonus counted it as unset, Hydra's forecast as still to move).
        m.moved_this_turn = v.get("done").and_then(|d| d.as_bool()).unwrap_or(mode != "Stand Still");
        m.mp_spent = v.get("mp_spent").and_then(|x| x.as_i64()).unwrap_or(0);
        // hexes moved: what the target movement modifier is figured from (combat::fc_to_tmm), and the movement heat
        m.move_fc = v.get("hexes_moved").and_then(|x| x.as_i64()).unwrap_or(0);
        m.movement_heat = crate::heat::movement_heat(m, mode, m.move_fc);
        match mode {
            "Run" => m.movement_mode_this_turn = "running".into(),
            "Jump" => m.movement_mode_this_turn = "jump".into(),
            _ => {}
        }
    }
    if let Some(t) = v.get("twist").and_then(|t| t.as_i64()) {
        m.torso_twist = Some(t);
        // the twist as our engine's declared action, locked for the turn once made (Core p.62: a 'Mech that twisted in the
        // Ranged Attack Phase keeps that twist for its physical attacks; only one not yet twisted may twist then). MegaMek
        // resets the twist in the End Phase, so a twist seen here was declared this turn. Session 30: only the number was
        // copied, so our engine re-twisted in the physical phase and MegaMek refused the punch.
        let flip = m.arms_flipped.unwrap_or(false);
        let turret = crate::arcs::current_action(m).turret;
        m.arc_action = Some(ArcAction { twist: t, flip, turret });
        m.arc_action_locked = Some(t != 0 || flip);
    }
    // the weapons fired this turn, by address (the physical attack choice reads them: what fired limits what punches)
    if let Some(f) = v.get("fired").and_then(|f| f.as_array()) {
        let fired: Vec<&str> = f.iter().filter_map(|x| x.as_str()).collect();
        m.weapons_fired_this_turn = Some(by_addr.iter().filter(|(a, _)| fired.contains(&a.as_str())).map(|(_, id)| *id).collect());
    }
    if let Some(extra) = v.get("extra").and_then(|e| e.as_object()).filter(|e| !e.is_empty()) {
        // measurement only (view_extra): the raw fields put back through the record
        let names: Vec<String> = (0..b.units.len()).map(|i| unit_name(b, i)).collect();
        let index = |n: &str| names.iter().position(|x| x == n).unwrap();
        let name_of = |i: usize| names[i].clone();
        let mut dump = b.units[u].to_json(&name_of);
        for (k, x) in extra {
            dump[k.as_str()] = x.clone();
        }
        b.units[u] = Mech::from_json(&dump, &index);
    }
    let m = &mut b.units[u];
    // the side's deployment edge, when the game has one (MegaMek's deployment zone; not sent by GameView yet: its games
    // start deployed, DEPLOYMENT fixed_hexes)
    let edge = |k: &str| v.get(k).and_then(|e| e.as_array()).map(|e| e.iter().filter_map(|x| x.as_str().map(|s| s.to_string())).collect::<Vec<_>>());
    if let Some(e) = edge("home_edge") {
        m.home_edge = Some(e);
    }
    if let Some(e) = edge("home_edge_row") {
        m.home_edge_row = Some(e);
    }
}

/// A picked move as MegaMek steps: "get_up", "turn_left", "turn_right", "forward", "backward" - or {"jump": true}
/// (MegaMek's own path finder takes a jump to its end hex) or null when no route is found.
fn path_steps(b: &Battle, mover: UnitId, pick: &Pick, standup_mp: Option<i64>) -> Value {
    if pick.charge {
        // A charge (Core p.78): the pick is the hex next to the target, facing it, with the MP and hexes of the last step
        // INTO the target counted. The steps are the route to that hex; the bridge adds MegaMek's CHARGE step (session 30).
        let Some(target) = crate::movement_attacks::neighbour(&pick.hex, crate::hex_geometry::compass_to_facing(&pick.facing).unwrap()) else { return Value::Null };
        let m = &b.units[mover];
        let level_limit = crate::terrain_rules::max_level_change(crate::mech_state::ground_level_limited(m), crate::mech_state::is_superheavy(m));
        let (Some(from), Some(into)) = (b.board.hexes.get(&pick.hex), b.board.hexes.get(&target)) else { return Value::Null };
        let Some(cost) = crate::terrain_rules::step_cost(Some(from), into, level_limit, false) else { return Value::Null };
        let route = Pick { fc: pick.fc - 1, mp_spent: pick.mp_spent - cost, charge: false, ..pick.clone() };
        let mut out = if route.fc == 0 && route.mp_spent == 0 {
            // charging from where it stands: if it stands up first it turns to face the target for free (Core p.51; free in
            // MegaMek right after GET_UP), so those turns go after GET_UP (session 30: they were left out - MegaMek's charge
            // went straight ahead and was refused)
            let mut steps: Vec<&str> = Vec::new();
            if standup_mp.is_some() {
                steps.push("get_up");
                let mut facing = crate::hex_geometry::compass_to_facing(&b.units[mover].facing).unwrap_or(0);
                let want = crate::hex_geometry::compass_to_facing(&pick.facing).unwrap_or(facing);
                while facing != want {
                    if (want - facing).rem_euclid(6) <= 3 {
                        steps.push("turn_right");
                        facing = (facing + 1).rem_euclid(6);
                    } else {
                        steps.push("turn_left");
                        facing = (facing + 5).rem_euclid(6);
                    }
                }
            }
            json!({"steps": steps})
        } else {
            path_steps(b, mover, &route, standup_mp)
        };
        if out.is_null() {
            return Value::Null;
        }
        out["charge"] = json!(target);
        return out;
    }
    if pick.mode == "Jump" {
        return json!({"jump": true});
    }
    if b.units[mover].prone && !crate::piloting_rolls::can_stand(&b.units[mover]) {
        // lying where it is, turning toward its foe (see "choose_movement"): only turns, the short way round
        let mut facing = crate::hex_geometry::compass_to_facing(&b.units[mover].facing).unwrap_or(0);
        let want = crate::hex_geometry::compass_to_facing(&pick.facing).unwrap_or(facing);
        let mut steps: Vec<&str> = Vec::new();
        while facing != want {
            if (want - facing).rem_euclid(6) <= 3 {
                steps.push("turn_right");
                facing = (facing + 1).rem_euclid(6);
            } else {
                steps.push("turn_left");
                facing = (facing + 5).rem_euclid(6);
            }
        }
        return json!({"steps": steps});
    }
    if pick.mode == "Stand Still" {
        return json!({"steps": if standup_mp.is_some() { vec!["get_up"] } else { vec![] }});
    }
    let Some((stood_facing, path)) = crate::ranged_combat::path_to_with_start(b, mover, pick, standup_mp) else { return Value::Null };
    let mut steps: Vec<&str> = Vec::new();
    let start = b.units[mover].hex.as_deref().and_then(|h| crate::hex_geometry::state_from_label(h, &b.units[mover].facing).ok());
    let mut facing = start.map(|s| s.2).unwrap_or(0);
    if standup_mp.is_some() {
        steps.push("get_up");
        // Core (Standing Up): a 'Mech that stands picks any facing at no cost. MegaMek keeps the prone facing, but a turn
        // made right after GET_UP costs nothing there (TurnStep: hasJustStood), so the chosen facing goes as turns here,
        // the short way round (Daniel, 2026-11-19: "stand up, turn to the facing you want as a separate step").
        let mut turn = (stood_facing - facing).rem_euclid(6);
        while turn != 0 {
            if turn <= 3 {
                steps.push("turn_right");
                facing = (facing + 1).rem_euclid(6);
            } else {
                steps.push("turn_left");
                facing = (facing + 5).rem_euclid(6);
            }
            turn = (stood_facing - facing).rem_euclid(6);
        }
    }
    for (step, (_, _, f), _) in path {
        match step {
            "turn" => {
                // the path's first state may already be a different facing (standing up facing anywhere)
                steps.push(if (f - facing).rem_euclid(6) == 1 { "turn_right" } else { "turn_left" });
                facing = f;
            }
            "forward" => steps.push("forward"),
            "backward" => steps.push("backward"),
            other => return json!({"unsupported_step": other}),
        }
    }
    json!({"steps": steps})
}

// =============================================================================================================
// Answers on the wire
// =============================================================================================================

fn pick_json(p: &Pick) -> Value {
    let mut v = json!({"hex": p.hex, "facing": p.facing, "mode": p.mode, "fc": p.fc, "mp_spent": p.mp_spent, "charge": p.charge, "dfa": p.dfa});
    // a pick that carries its route (BTTT's walk, a route drawn by a person): the steps, so a replayed answer walks the same route
    if let Some(r) = &p.route {
        v["route"] = json!(r.iter().map(|s| s.name()).collect::<Vec<_>>());
    }
    v
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
        Some((tn, opts, act)) => json!({"tn": tn, "names": opts.iter().map(|o| o.name.clone()).collect::<Vec<_>>(),
                                        "attacks": opts.iter().map(|o| format!("{:?}", o)).collect::<Vec<_>>(), "action": action_json(act)}),
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

/// The hexes other units stand in, set on a mover before it moves as `orchestrator::phase_movement` does (p.48: the
/// mobile enemies' hexes are closed to its ground moves) - when the state did not already carry them (a MegaMek game's
/// state does not; a recorded battle's does, and is left as it is).
///
/// Returns whether it set them: the caller clears them again after the question (`mover_done`), as phase_movement
/// does after the move - left in place, a unit's old list would block its own hex when it is later an opponent.
fn mover_sees_others(b: &mut Battle, mover: UnitId) -> bool {
    let unset = |v: &Option<Value>| v.as_ref().is_none_or(|x| x.is_null());
    if !unset(&b.units[mover].blocked_hex) {
        return false;
    }
    let blocked: Vec<Value> = crate::forces::blocked_xy(b, mover).into_iter().map(|(x, y)| json!([x, y])).collect();
    b.units[mover].blocked_hex = Some(Value::Array(blocked));
    let occ = crate::forces::occupied_labels(b, mover);
    b.units[mover].other_unit_hexes = Some(json!(occ));
    true
}

fn mover_done(b: &mut Battle, mover: UnitId, set: bool) {
    if set {
        b.units[mover].blocked_hex = Some(Value::Null);
        b.units[mover].other_unit_hexes = Some(Value::Null);
    }
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
        "manage_heat_equipment" => {
            bots.manage_heat_equipment(b);
            Value::Null
        }
        "choose_spot" => match bots.choose_spot(b, a["unit"].as_u64().unwrap() as UnitId) {
            Some((target, fires)) => json!([target, fires]),
            None => Value::Null,
        },
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
        "path_steps" => {
            let mover = a["mover"].as_u64().unwrap() as UnitId;
            let set = mover_sees_others(b, mover);
            let pick = pick_back(&a["pick"]);
            let steps = path_steps(b, mover, &pick, a["standup_mp"].as_i64());
            mover_done(b, mover, set);
            steps
        }
        "choose_physical" => phys_json(&bots.choose_physical(b, a["attacker"].as_u64().unwrap() as UnitId, a["target"].as_u64().unwrap() as UnitId)),
        "choose_movement" => {
            let mover = a["mover"].as_u64().unwrap() as UnitId;
            // No enemy left (MegaMek can run a few rounds after a side is gone before it declares the end): stand still.
            // Our engine never asks this - its battle ends first - and its movement search assumes a foe on the board
            // or entering it (it crashed here; session 30, Hydra v CASPAR game 2).
            if crate::forces::enemies_of(b, mover).is_empty() {
                if let Some(h) = b.units[mover].hex.clone() {
                    let stay = Pick { hex: h, facing: b.units[mover].facing.clone(), mode: "Stand Still".into(), fc: 0, mp_spent: 0, charge: false, dfa: false, route: None };
                    return json!({"pick": pick_json(&stay), "note": "no enemy left: stands still", "gate": Value::Null});
                }
            }
            // A prone 'Mech that cannot stand (gyro destroyed; a leg and both arms gone - Core p.51 / damage table): the Java
            // side offers a stand-up allowance whenever its 'Mech is prone, but our engine never tries to stand then; it turns
            // on the ground toward its foe, as the Movement Phase does (`turn_while_down`). Session 30: the bridge planned a
            // stand-up there and MegaMek refused it ("would not take the route", a GET_UP with the gyro gone).
            if a["standup_mp"].as_i64().is_some() && b.units[mover].prone && !crate::piloting_rolls::can_stand(&b.units[mover]) {
                let other = a["other"].as_u64().unwrap() as UnitId;
                let h = b.units[mover].hex.clone().unwrap_or_default();
                let (facing, turns) = match crate::orchestrator::turn_while_down_choice(b, mover, other) {
                    Some((f, t, _)) => (crate::hex_geometry::facing_to_compass(f).unwrap().to_string(), t),
                    None => (b.units[mover].facing.clone(), 0),
                };
                let mode = if turns > 0 { "Walk" } else { "Stand Still" };
                let pick = Pick { hex: h, facing, mode: mode.into(), fc: 0, mp_spent: turns, charge: false, dfa: false, route: None };
                return json!({"pick": pick_json(&pick), "note": "cannot stand: turns on the ground", "gate": Value::Null});
            }
            let set = mover_sees_others(b, mover);
            let edge: Option<Vec<String>> = a["entry_edge"].as_array().map(|e| e.iter().map(|x| x.as_str().unwrap().to_string()).collect());
            // MegaMek lets no 'Mech that began its move prone charge or make a death from above, even once it stands (MoveStep:
            // "initially prone meks can't charge"); the Core Rulebook has no such limit (p.78). In MegaMek's game its rule
            // stands, so Hydra plans this one move without movement attacks (session 30: such a charge was refused).
            let prone_start = a["standup_mp"].as_i64().is_some();
            let saved_attacks = b.cfg.has("HYDRA_MOVEMENT_ATTACKS").then(|| b.cfg.b("HYDRA_MOVEMENT_ATTACKS"));
            if prone_start {
                b.cfg.set("HYDRA_MOVEMENT_ATTACKS", json!(false));
            }
            let (pick, note, gate) = bots.choose_movement(
                b,
                a["mover"].as_u64().unwrap() as UnitId,
                a["other"].as_u64().unwrap() as UnitId,
                a["moves_first"].as_bool().unwrap(),
                a["standup_mp"].as_i64(),
                edge.as_deref(),
            );
            mover_done(b, mover, set);
            if prone_start {
                b.cfg.set("HYDRA_MOVEMENT_ATTACKS", json!(saved_attacks.unwrap_or(true)));
            }
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
    /// every unit's dump as the game started: what a compact state is applied to
    pub base: Vec<Value>,
    /// for a game started from MegaMek: what was set to match MegaMek's game options, and what cannot be followed
    pub rules_notes: Vec<String>,
}

/// MegaMek game options our engine has a switch for: (MegaMek's option name, our config key). Both booleans.
const MEGAMEK_SWITCHES: [(&str, &str); 1] = [("floating_crits", "FLOATING_CRITICALS")];
/// MegaMek options that change nothing our engine models (the client, saving, reports, the bridge's own settings).
const MEGAMEK_IGNORABLE: [&str; 3] = ["autosave_msg", "paranoid_autosave", "rules_system"];

/// A game started from MegaMek follows MegaMek's game options where our engine has the switch (session 30; Daniel: "see
/// what game options megamek is using, and then conform to them"): sets those in `config`, turns Daniel's own house rule
/// off (POOL_CLUSTER_DAMAGE: MegaMek has none), and returns one note per setting made and per option our engine cannot
/// follow - MegaMek's rule set if it is not Core Rules, and every other option changed from MegaMek's default.
pub fn conform_to_megamek(config: &mut Value, options: Option<&Value>) -> Vec<String> {
    let mut notes = Vec::new();
    if config.get("POOL_CLUSTER_DAMAGE").and_then(|x| x.as_bool()) == Some(true) {
        config["POOL_CLUSTER_DAMAGE"] = json!(false);
        notes.push("POOL_CLUSTER_DAMAGE off: a house rule MegaMek does not have".into());
    }
    let Some(options) = options.and_then(|o| o.as_object()) else {
        notes.push("NOT CHECKED: the start line carried no MegaMek game options".into());
        return notes;
    };
    for (option, key) in MEGAMEK_SWITCHES {
        if let Some(o) = options.get(option) {
            let on = o["value"].as_str() == Some("true");
            config[key] = json!(on);
            notes.push(format!("{} {}: MegaMek's {} is {}", key, if on { "on" } else { "off" }, option, on));
        }
    }
    let system = options.get("rules_system").and_then(|o| o["value"].as_str()).unwrap_or("");
    if system != "Core Rules" {
        notes.push(format!("NOT FOLLOWED: MegaMek plays '{}'; our engine plays the Core Rulebook (moves and rules can differ)", system));
    }
    for (name, o) in options {
        if MEGAMEK_SWITCHES.iter().any(|(n, _)| n == name) || MEGAMEK_IGNORABLE.contains(&name.as_str()) {
            continue;
        }
        if o["value"] != o["default"] {
            notes.push(format!("NOT FOLLOWED: MegaMek option {} = {} (default {})", name, o["value"].as_str().unwrap_or("?"), o["default"].as_str().unwrap_or("?")));
        }
    }
    notes
}

impl Session {
    /// The game's start: settings, board and units in a scenario's own form (config.json, board.json, units.json),
    /// plus the teams Hydra drives and the teams CASPAR drives ("caspar_teams", optional; added in CASPAR's review,
    /// 2026-11-19: before it a CASPAR team's units came back as their units.json bot). The dice are whatever the first line's state says. OR {"settings": {...},
    /// "hydra_teams", "seed"}: the scenario is built here from settings (`Scenario::from_settings`, Combat Lab CL1) -
    /// how the Java side starts a game: which .mtf on which team, at which hex and facing, the board.
    pub fn start(v: &Value) -> Session {
        if let Some(settings) = v.get("settings") {
            let s = crate::scenario::Scenario::from_settings(settings, &crate::scenario::SetupPaths::find()).unwrap_or_else(|e| panic!("bridge start: {}", e));
            let mut start = s.bridge_start(v["seed"].as_u64().unwrap_or(1));
            // MegaMek decides when a unit is out (the view's "destroyed"): our engine must not write one off early. With
            // FIGHT_TO_THE_DEATH off (Daniel's speed switch for our own battles) a 'Mech with its gyro or both legs gone
            // counts as destroyed here, while in MegaMek it lies there and shoots: our bots then ignored it - routes through
            // its hex (MegaMek refused them: "would not take the route"), no shots at it (session 30, Hydra v CASPAR).
            start["config"]["FIGHT_TO_THE_DEATH"] = json!(true);
            let mut notes = vec!["FIGHT_TO_THE_DEATH on: MegaMek decides when a unit is out".to_string()];
            notes.extend(conform_to_megamek(&mut start["config"], v.get("megamek_options")));
            if s.board.get("hexes").and_then(|h| h.as_object()).is_some_and(|h| h.values().any(|x| x["features"].get("building").is_some())) {
                notes.push("NOT FOLLOWED: the board has buildings - MegaMek plays the full building rules, our engine passive buildings".into());
            }
            start["hydra_teams"] = v.get("hydra_teams").cloned().unwrap_or(json!([]));
            start["caspar_teams"] = v.get("caspar_teams").cloned().unwrap_or(json!([]));
            let mut session = Session::start(&start);
            session.rules_notes = notes;
            return session;
        }
        let cfg = Config::from_json(&v["config"]);
        let board = Board::from_json(&v["board"]);
        let names: Vec<String> = v["units"].as_object().unwrap().keys().cloned().collect();
        let idx = |n: &str| names.iter().position(|x| x == n).unwrap();
        let mut units: Vec<Mech> = names.iter().map(|n| Mech::from_json(&v["units"][n], &idx)).collect();
        let hydra: Vec<String> = v["hydra_teams"].as_array().map(|t| t.iter().map(|x| x.as_str().unwrap().to_string()).collect()).unwrap_or_default();
        let caspar: Vec<String> = v["caspar_teams"].as_array().map(|t| t.iter().map(|x| x.as_str().unwrap().to_string()).collect()).unwrap_or_default();
        for m in units.iter_mut() {
            if m.team.as_ref().is_some_and(|t| hydra.contains(t)) {
                m.bot = "hydra".to_string();
            }
            if m.team.as_ref().is_some_and(|t| caspar.contains(t)) {
                m.bot = "caspar".to_string();
            }
        }
        let seed = v["seed"].as_u64().unwrap_or(1);
        let b = Battle::new(cfg, board, units, Box::new(PcgDice::new(seed)));
        let name = |i: usize| unit_name(&b, i);
        let base = b.units.iter().map(|m| m.to_json(&name)).collect();
        Session { b, bots: GladiatorBots, base, rules_notes: Vec::new() }
    }

    /// One line: {"method", "args", "state"} -> the answer (null for a signal).
    pub fn handle(&mut self, line: &Value) -> Value {
        load_state(&mut self.b, &line["state"], &self.base);
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
    /// compact mode: each unit's dump at the start (the checking session's own), units then go as compact states
    compact_base: Option<Vec<Value>>,
    /// view mode (`--bridge-view`): units go as MegaMek views; answers are counted, not required to be the same
    pub view: bool,
}

impl<'a> Recorder<'a> {
    /// `compact`: send the units as compact states, against the checking session's own start dumps.
    pub fn new(inner: &'a mut dyn BotSet, check: Option<Session>, keep: bool, compact: bool) -> Recorder<'a> {
        let compact_base = if compact { check.as_ref().map(|s| s.base.clone()) } else { None };
        Recorder { inner, lines: Vec::new(), keep, check, parity: Parity { calls: 0, decisions: 0, first_difference: None, rebuild_gaps: Default::default(), agree: Default::default() }, last_board: None, compact_base, view: false }
    }

    /// Records the state, makes the call through the same `call` the session uses, records the answer.
    fn run(&mut self, b: &mut Battle, method: &str, args: Value) -> Value {
        self.note_gaps(b);
        let state = state_json_mode(b, &mut self.last_board, self.compact_base.as_deref(), self.view);
        let answer = call(b, self.inner, method, &args);
        self.checked(json!({"method": method, "args": args, "state": state, "answer": answer}));
        answer
    }

    /// Compact mode: every unit rebuilt from its compact state is compared with its real dump; the fields it got wrong
    /// are counted (`Parity::rebuild_gaps`) - what UNIT_FIELDS / ITEM_FIELDS are missing, if anything. View mode: the
    /// session's units (as the MegaMek views left them, before it answers) against the real dumps - what a MegaMek game
    /// does not tell our engine, field by field.
    fn note_gaps(&mut self, b: &Battle) {
        if self.view {
            let Some(s) = self.check.as_mut() else { return };
            let mut last = None;
            let state = state_json_mode(b, &mut last, None, true);
            load_state(&mut s.b, &state, &s.base);
            let name = |i: usize| unit_name(b, i);
            for (i, m) in b.units.iter().enumerate() {
                let sname = |j: usize| unit_name(&s.b, j);
                for g in rebuild_gaps(&m.to_json(&name), &s.b.units[i].to_json(&sname)) {
                    *self.parity.rebuild_gaps.entry(g).or_insert(0) += 1;
                }
            }
            return;
        }
        let Some(base) = self.compact_base.as_ref() else { return };
        let name = |i: usize| unit_name(b, i);
        for (i, m) in b.units.iter().enumerate() {
            let real = m.to_json(&name);
            let rebuilt = apply_compact(&base[i], &compact_unit(&real, &base[i]));
            for g in rebuild_gaps(&real, &rebuilt) {
                *self.parity.rebuild_gaps.entry(g).or_insert(0) += 1;
            }
        }
    }

    /// A finished line: counted, handed to the session (until its first difference) and compared, kept if `keep`.
    fn checked(&mut self, line: Value) {
        self.parity.calls += 1;
        if !line["answer"].is_null() {
            self.parity.decisions += 1;
        }
        if self.view {
            // view mode: every call is answered and compared; the decisions' agreement is counted
            if let Some(s) = self.check.as_mut() {
                let got = s.handle(&line);
                if !line["answer"].is_null() {
                    // what is actually ORDERED is compared: the move (not its note), the weapons and twist (not the
                    // expected damage), the physical attacks; anything else whole
                    let ordered = |m: &str, a: &Value| -> Value {
                        match m {
                            "choose_movement" => a["pick"].clone(),
                            "choose_declaration" => json!([a["weapons"], a["action"], a["no_attack"]]),
                            "choose_physical" => json!([a["names"], a["action"]]),
                            _ => a.clone(),
                        }
                    };
                    let method = line["method"].as_str().unwrap();
                    let e = self.parity.agree.entry(method.to_string()).or_insert((0, 0));
                    e.1 += 1;
                    if ordered(method, &got) == ordered(method, &line["answer"]) {
                        e.0 += 1;
                    }
                }
            }
        } else if self.parity.first_difference.is_none() {
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
        route: v.get("route").and_then(|r| r.as_array()).map(|r| r.iter().filter_map(|s| s.as_str().and_then(crate::step_walk::Step::from_name)).collect()),
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
        self.note_gaps(b);
        let state = state_json_mode(b, &mut self.last_board, self.compact_base.as_deref(), self.view);
        let choice = self.inner.choose_declaration(b, ctx, planner, attacker, target);
        let answer = decl_json(b, attacker, &choice);
        self.checked(json!({"method": "choose_declaration", "args": {"attacker": attacker, "target": target}, "state": state, "answer": answer}));
        choice
    }
    fn choose_physical(&mut self, b: &mut Battle, attacker: UnitId, target: UnitId) -> Option<(i64, Vec<PhysOption>, ArcAction)> {
        self.note_gaps(b);
        let state = state_json_mode(b, &mut self.last_board, self.compact_base.as_deref(), self.view);
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
    fn manage_heat_equipment(&mut self, b: &mut Battle) {
        self.run(b, "manage_heat_equipment", json!({}));
    }
    fn choose_spot(&mut self, b: &mut Battle, u: UnitId) -> Option<(UnitId, bool)> {
        let a = self.run(b, "choose_spot", json!({"unit": u}));
        a.as_array().map(|x| (x[0].as_u64().unwrap() as UnitId, x[1].as_bool().unwrap()))
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
    /// compact mode: fields a unit rebuilt from its compact state got wrong, and how many calls each was wrong in
    pub rebuild_gaps: std::collections::BTreeMap<String, usize>,
    /// view mode: per decision kind, (answers the same, answers given)
    pub agree: std::collections::BTreeMap<String, (usize, usize)>,
}

/// Feeds a recorded battle's lines to a fresh session (built from the same start) and compares every answer.
pub fn parity(start: &Value, lines: &[Value]) -> Parity {
    let mut s = Session::start(start);
    let mut out = Parity { calls: 0, decisions: 0, first_difference: None, rebuild_gaps: Default::default(), agree: Default::default() };
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
