//! A LIVE GAME WITH A PERSON IN IT (BattleROM, first playable slice, steps E2-E6 and the server's half of S1;
//! INTEGRATION__PLAYER_DECISIONS.md Section 15). Not translated from the Python. Native only: the browser build cannot wait.
//!
//! `Game::start` plays a battle on its own thread with a `human_bots::HumanBots` whose controller (`Screen`) turns each
//! question to the person into a JSON request - the battle's units, the question's own data (hexes the unit can reach,
//! weapons with their TN, expected damage and heat, physical attacks) and the log lines since the last request - and
//! waits until `Game::answer` gives the reply. The battle has no clock: it simply does not go on until it has the answer.
//! Every other unit is played by the normal bots. The decision list the controller keeps (`HumanBots::log`) is what a
//! replay or a branch point is made from.
//!
//! Requests ("kind"): `move_order` {candidates}, `movement` {options}, `target` {enemies}, `declaration` {weapons,
//! arcs}, `physical` {kinds}. Answers: `{"unit": id}`, `{"hex","facing","mode"}` or `{"stay": true}`, `{"target": id|null}`,
//! `{"weapons": [ids]}`, `{"kind": "punch"|...|null}`. A request answered with something illegal is asked again, with an
//! "error" saying why.
#![cfg(not(target_arch = "wasm32"))]
use crate::fasthash::HashSet;
use std::sync::{Arc, Condvar, Mutex};
use std::time::Duration;

use serde_json::{json, Value};

use crate::attack_resolution::{arc_unavailable, DeclChoice, DeclCtx};
use crate::battle::{Battle, UnitId};
use crate::dice::PcgDice;
use crate::fire_modes::Planner;
use crate::gladiator_bots::GladiatorBots;
use crate::human_bots::{Controller, HumanBots, PhysicalChoice};
use crate::mech_state::ArcAction;
use crate::move_options::{self, PathNotes};
use crate::orchestrator::{play_on, start_battle, PathGate};
use crate::ranged_combat::Pick;
use crate::scenario::Scenario;

#[derive(Default)]
struct Slot {
    /// the question the battle is waiting on, and its number
    pending: Option<Value>,
    seq: u64,
    answer: Option<Value>,
    /// the battle's end: result, final units, log
    done: Option<Value>,
    /// the engine's own stop (a panic), as text
    failed: Option<String>,
}

pub struct Game {
    slot: Mutex<Slot>,
    cv: Condvar,
}

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
}

fn play(game: &Arc<Game>, sc: &Scenario, seed: u64, human_teams: &[String]) {
    let mut b = sc.battle(Box::new(PcgDice::new(seed)));
    let human: Vec<UnitId> = (0..b.units.len()).filter(|&u| b.units[u].team.as_deref().is_some_and(|t| human_teams.iter().any(|h| h == t))).collect();
    let mut marks = |_: &mut Battle, _: i64, _: &str| {};
    let mut play = start_battle(&mut b, sc.max_turns, &mut marks);
    let screen = Screen { game: game.clone(), sent_log: 0, first: true };
    let mut bots = HumanBots::new(screen, human);
    play_on(&mut b, &mut bots, &mut play, &mut marks);
    let r = &play.result;
    let end = json!({"winner": r.winner, "turns": r.turns_taken, "destroyed": r.destroyed, "units": units_json(&b), "log": new_log(&b, &mut bots.ctl.sent_log), "decisions": bots.log.len()});
    game.slot.lock().unwrap().done = Some(end);
    game.cv.notify_all();
}

fn units_json(b: &Battle) -> Value {
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
                s["walk"] = json!(crate::mech_state::compute_walk_mp(m));
                s["run"] = json!(crate::mech_state::compute_running_mp(m));
                s["jump"] = json!(crate::mech_state::compute_jump_mp(m));
                s["max_heat"] = json!(m.max_heat);
                s["move_mode"] = json!(m.move_mode);
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

/// The controller that talks to the page.
struct Screen {
    game: Arc<Game>,
    sent_log: usize,
    first: bool,
}

impl Screen {
    /// Send `request` (units and log added) and wait for the answer; `check` turns an answer into the engine's choice or an
    /// error text, in which case the person is asked again.
    fn ask<T>(&mut self, b: &Battle, mut request: Value, mut check: impl FnMut(&Value) -> Result<T, String>) -> T {
        request["units"] = units_json(b);
        request["log"] = json!(new_log(b, &mut self.sent_log));
        if self.first {
            request["board"] = crate::history::board(b);
            self.first = false;
        }
        loop {
            {
                let mut s = self.game.slot.lock().unwrap();
                s.seq += 1;
                s.pending = Some(request.clone());
                s.answer = None;
                self.game.cv.notify_all();
                s = self.game.cv.wait_while(s, |s| s.answer.is_none()).unwrap();
                let a = s.answer.take().unwrap();
                drop(s);
                match check(&a) {
                    Ok(t) => return t,
                    Err(e) => {
                        request["error"] = json!(e);
                        request["log"] = json!([]);
                        request.as_object_mut().unwrap().remove("board");
                    }
                }
            }
        }
    }
}

fn name(b: &Battle, u: UnitId) -> String {
    b.units[u].side_name.clone().unwrap_or_default()
}

impl Controller for Screen {
    fn move_order(&mut self, b: &mut Battle, candidates: &[UnitId], _inner: &mut GladiatorBots) -> UnitId {
        let cands: Vec<UnitId> = candidates.to_vec();
        let req = json!({"kind": "move_order", "candidates": cands});
        // a person moves a unit of its own; any other candidate is not offered (bots move theirs by the engine's order)
        self.ask(b, req, |a| {
            let u = a["unit"].as_u64().ok_or("which unit?")? as usize;
            if cands.contains(&u) { Ok(u) } else { Err("that unit is not waiting to move".to_string()) }
        })
    }

    fn movement(&mut self, b: &mut Battle, mover: UnitId, other: UnitId, moves_first: bool, standup_mp: Option<i64>, entry_edge: Option<&[String]>, inner: &mut GladiatorBots) -> (Option<Pick>, String, PathGate) {
        let mut notes = PathNotes::default();
        let mut states = move_options::movement_options(b, mover, standup_mp, entry_edge, true, &mut notes);
        // a unit may pass through a friend's hex but not end there (the bots exclude these hexes the same way)
        let occupied = move_options::occupied_hexes(b, mover, other);
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
        let m = &b.units[mover];
        let req = json!({"kind": "movement", "unit": mover, "name": name(b, mover), "hex": m.hex, "facing": m.facing, "standup_mp": standup_mp,
                         "entry": entry_edge.is_some(), "walk": crate::mech_state::compute_walk_mp(m), "run": crate::mech_state::compute_running_mp(m),
                         "jump": crate::mech_state::compute_jump_mp(m), "options": list});
        let chosen: Option<usize> = self.ask(b, req, |a| {
            if a["stay"].as_bool() == Some(true) {
                if entry_edge.is_some() {
                    return Err("the unit has not entered the map yet: choose a hex on its edge".to_string());
                }
                return Ok(None);
            }
            let k = (a["hex"].as_str().unwrap_or("").to_string(), a["facing"].as_str().unwrap_or("").to_string(), a["mode"].as_str().unwrap_or("").to_string());
            best.get(&k).map(|(i, _)| Some(*i)).ok_or_else(|| format!("{} {} ({}) is not a legal end of move", k.0, k.1, k.2))
        });
        let _ = (other, moves_first, &inner);
        match chosen {
            Some(i) => {
                let pick = opts[i].pick();
                let (psrs, hazard) = crate::ranged_combat::path_notes(b, mover, &pick, standup_mp, entry_edge);
                (Some(pick), "chosen by the player".into(), PathGate { psrs, hazard })
            }
            None => {
                // stay put: the option the engine lists as Stand Still, if it lists one
                match opts.iter().find(|o| o.mode == "Stand Still") {
                    Some(o) => (Some(o.pick()), "player stays put".into(), PathGate::default()),
                    None => (None, "player stays put".into(), PathGate::default()),
                }
            }
        }
    }

    fn target(&mut self, b: &mut Battle, attacker: UnitId, _inner: &mut GladiatorBots) -> Option<UnitId> {
        let enemies: Vec<UnitId> = crate::forces::enemies_of(b, attacker).into_iter().filter(|&e| b.units[e].hex.is_some() && !b.is_destroyed(e)).collect();
        if enemies.is_empty() {
            return None;
        }
        let list: Vec<Value> = enemies.iter().map(|&e| json!({"id": e, "name": name(b, e), "distance": crate::forces::distance(b, attacker, e)})).collect();
        let req = json!({"kind": "target", "unit": attacker, "name": name(b, attacker), "enemies": list});
        self.ask(b, req, |a| match a["target"].as_u64() {
            None => Ok(None),
            Some(t) if enemies.contains(&(t as usize)) => Ok(Some(t as usize)),
            Some(_) => Err("that is not an enemy you can target".to_string()),
        })
    }

    fn declaration(&mut self, b: &mut Battle, ctx: &DeclCtx, planner: &mut Planner, attacker: UnitId, target: UnitId, _inner: &mut GladiatorBots) -> DeclChoice {
        let weapons = crate::damage_resolution::get_weapons(&b.units[attacker]);
        // the weapons that can fire at this range (and their expected damage and heat), as the weapon picker sees them
        let cands = crate::weapon_selection::fire_candidates(b, attacker, ctx.distance, ctx.sel_pre_tn, Some(&ctx.adjust), &ctx.unavailable, None, &weapons, Some(planner));
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
        let mut rows: Vec<Value> = Vec::new();
        for &w in &weapons {
            let (iname, iheat) = { let it = &b.units[attacker].items[w]; (it.name.clone(), it.heat) };
            let cand = cands.iter().find(|c| c.w == w);
            let bracket = crate::weapon_selection::range_bracket(b, attacker, w, ctx.distance);
            let tn = cand.map(|_| {
                let adj = crate::fire_modes::TnAdjust::adjust(&ctx.adjust, b, w, bracket, None);
                (ctx.sel_pre_tn + adj).clamp(crate::weapon_selection::PRE_TN_MIN, crate::weapon_selection::PRE_TN_MAX)
            });
            rows.push(json!({"id": w, "name": iname, "loc": ctx.w_locs.get(&w), "heat": cand.map(|c| c.heat).or(iheat), "ev": cand.map(|c| c.value),
                             "tn": tn, "range": bracket, "in_range": cand.is_some(), "needs_twist": cand.is_some() && per_action.first().is_some_and(|u| u.contains(&w))}));
        }
        let u = &b.units[attacker];
        let req = json!({"kind": "declaration", "unit": attacker, "name": name(b, attacker), "target": target, "target_name": name(b, target), "distance": ctx.distance,
                         "base_tn": ctx.sel_pre_tn, "weapons": rows, "heat": u.current_heat, "move_heat": u.movement_heat, "dissipation": ctx.dissipation,
                         "max_heat": u.max_heat, "indirect": ctx.indirect, "secondary": ctx.secondary});
        let ids: Vec<usize> = self.ask(b, req, |a| {
            let ids: Vec<usize> = a["weapons"].as_array().ok_or("which weapons?")?.iter().filter_map(|v| v.as_u64().map(|x| x as usize)).collect();
            for id in &ids {
                if !cands.iter().any(|c| c.w == *id) {
                    return Err(format!("weapon {} cannot fire at this target", id));
                }
            }
            Ok(ids)
        });
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
        let pick: Option<String> = self.ask(b, req, |a| match a["kind"].as_str() {
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
}
