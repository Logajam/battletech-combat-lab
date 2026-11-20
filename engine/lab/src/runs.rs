//! Batches of battles for the Lab: a SETUP (what the pages send) made into engine settings, run on its own threads
//! (the server keeps answering while it runs), counted as it goes, stoppable, and summed up at the end.
//!
//! SETUP (JSON):
//! ```text
//! {"teams": [{"name": "Red", "bot": "gladiator" | "princess" | "hydra" | "caspar",
//!             "units": [{"unit": "Atlas AS7-K.mtf", "gunnery": 4, "piloting": 5}, ...]}, ...],
//!  "board": "16x17_Grassland_1.board",            (a board's id from list_boards)
//!  "battles": 20, "seed": 1, "threads": 0 (= automatic: a quarter of the cores left free), "max_turns": 100 (optional)}
//! ```
//! Battle n of a batch is played on `PcgDice::battle_seed(seed, n)`, as `btsim` does, so a battle of the Lab is the
//! same battle `btsim` plays for the same settings and seed - and any one can be played again, with its full history,
//! from (setup, seed) alone (`history`).
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
// The browser build (engine/wasm) shares this file: no threads and no std clock there (the page's workers play the
// battles, and the clock is the page's, `host_now_ms`), so those parts are compiled only for the desktop.
#[cfg(not(target_arch = "wasm32"))]
use std::time::Instant;
#[cfg(target_arch = "wasm32")]
use wasm_clock::Instant;

#[cfg(target_arch = "wasm32")]
pub mod wasm_clock {
    extern "C" {
        /// milliseconds from the page (performance.now())
        fn host_now_ms() -> f64;
    }
    /// std::time::Instant's two uses here, on the page's clock.
    #[derive(Clone, Copy)]
    pub struct Instant(f64);
    impl Instant {
        pub fn now() -> Instant {
            Instant(unsafe { host_now_ms() })
        }
        pub fn elapsed(&self) -> std::time::Duration {
            std::time::Duration::from_secs_f64(((unsafe { host_now_ms() }) - self.0).max(0.0) / 1000.0)
        }
    }
}

use btsim_core::dice::PcgDice;
use btsim_core::results::BattleResult;
use btsim_core::scenario::{Scenario, SetupPaths};
#[cfg(not(target_arch = "wasm32"))]
use rayon::prelude::*;
use serde_json::{json, Value};

use crate::catalog::Catalog;

pub const BOTS: [&str; 4] = ["gladiator", "princess", "hydra", "caspar"];

/// The engine settings and the turn cap for a setup (one board, one zone assignment), the packed units and board unpacked.
/// Err = what is wrong with it, in words for the page.
fn scenario_one(setup: &Value, catalog: &Catalog, paths: &SetupPaths, zones: Option<&Value>) -> Result<Scenario, String> {
    let teams = setup["teams"].as_array().ok_or("no teams")?;
    if teams.len() < 2 {
        return Err("a battle needs at least two teams".into());
    }
    let mut forces = Vec::new();
    let mut hydra_teams = Vec::new();
    // each team's own bot settings (the Configure team window, N5): TEAM_SETTINGS (team_settings.rs)
    let mut team_settings = serde_json::Map::new();
    let mut names: Vec<&str> = Vec::new();
    for t in teams {
        let name = t["name"].as_str().filter(|n| !n.trim().is_empty()).ok_or("every team needs a name")?;
        if names.contains(&name) {
            return Err(format!("two teams are called '{}'", name));
        }
        names.push(name);
        let bot = t["bot"].as_str().unwrap_or("gladiator").to_lowercase();
        if !BOTS.contains(&bot.as_str()) {
            return Err(format!("team {}: unknown bot '{}'", name, bot));
        }
        if bot == "hydra" {
            hydra_teams.push(name.to_string());
        }
        if let Some(own) = t["settings"].as_object().filter(|o| !o.is_empty()) {
            let defaults: Value = serde_json::from_str(&paths.defaults_text()?).map_err(|e| e.to_string())?;
            for (key, value) in own {
                check_option(&defaults, key, value).map_err(|e| format!("team {}: {}", name, e))?;
            }
            team_settings.insert(name.to_string(), Value::Object(own.clone()));
        }
        let units = t["units"].as_array().filter(|u| !u.is_empty()).ok_or_else(|| format!("team {} has no units", name))?;
        for u in units {
            // a unit edited on the page (Daniel, 2026-11-15) carries its whole file text in the setup, so it lives and dies with the
            // setup: it is saved only with the run's file. The engine reads it from a scratch file named by the text's hash
            // under data/_modified/ (emptied each time the Lab starts); it never enters the unit list or the unit folder.
            let inline_id;
            let id = if let Some(text) = u["mtf_text"].as_str() {
                inline_id = catalog.scratch_unit(text)?;
                inline_id.as_str()
            } else {
                let id = u["unit"].as_str().ok_or_else(|| format!("team {}: a unit with no file", name))?;
                catalog.ensure(id)?;
                id
            };
            let skill = |k: &str, d: i64| u[k].as_i64().unwrap_or(d).clamp(0, 8);
            let mut entry = json!({"team": name, "mtf": id, "bot": bot, "gunnery": skill("gunnery", 4), "piloting": skill("piloting", 5)});
            // the ammunition chosen per bin in the Configure unit window ({"<location>:<slot>": "<munition>"}; setup.rs)
            if let Some(ammo) = u["ammo"].as_object().filter(|a| !a.is_empty()) {
                if ammo.values().any(|v| !v.is_string()) {
                    return Err(format!("team {}: an ammunition choice must be a word", name));
                }
                entry["ammo"] = Value::Object(ammo.clone());
            }
            forces.push(entry);
        }
    }
    // the board: one board's id, or {"grid": [[id, ...], ...]} - boards stitched together, row by row (the engine's
    // STITCH_MAPS: boards in a row share a height, boards in a column a width)
    let mut settings = json!({"FORCES": forces, "DEPLOYMENT": "home_edge"});
    if !team_settings.is_empty() {
        settings[btsim_core::team_settings::KEY] = Value::Object(team_settings);
    }
    match &setup["board"] {
        Value::String(board) => {
            catalog.ensure(board)?;
            settings["DEFAULT_BOARD_PATH"] = json!(board);
        }
        Value::Object(o) => {
            let rows: Vec<Vec<String>> = o.get("grid").and_then(|g| g.as_array()).ok_or("no boards chosen")?
                .iter()
                .map(|r| r.as_array().map(|c| c.iter().filter_map(|x| x.as_str().map(String::from)).collect()).unwrap_or_default())
                .collect();
            let cols = rows.first().map_or(0, |r| r.len());
            if rows.is_empty() || cols == 0 || rows.iter().any(|r| r.len() != cols) {
                return Err("every place in the board grid needs a board".into());
            }
            for id in rows.iter().flatten() {
                catalog.ensure(id)?;
            }
            settings["STITCH_MAPS"] = json!(true);
            settings["STITCH_BOARDS"] = json!(rows.concat());
            settings["STITCH_GRID_COLS"] = json!(cols);
            settings["STITCH_GRID_ROWS"] = json!(rows.len());
        }
        _ => return Err("no board chosen".into()),
    }
    if let Some(z) = zones {
        settings["DEPLOY_ZONES"] = z.clone();
    }
    apply_options(&mut settings, &setup["options"], paths)?;
    let mut s = Scenario::from_settings(&settings, paths)?;
    s.hydra_teams = hydra_teams;
    if let Some(cap) = setup["max_turns"].as_i64().filter(|c| *c > 0) {
        s.max_turns = cap;
    }
    Ok(s)
}

/// The Options tab's changes ("options": {SETTING: value}) laid over the defaults. Only a setting that exists, that the Lab
/// does not set itself, and whose value has the default's kind is accepted: a wrong kind would crash a battle's worker
/// (`Config::b` and friends panic), so it is refused here in words instead.
fn apply_options(settings: &mut Value, options: &Value, paths: &SetupPaths) -> Result<(), String> {
    let Some(options) = options.as_object().filter(|o| !o.is_empty()) else { return Ok(()) };
    let text = paths.defaults_text()?;
    let defaults: Value = serde_json::from_str(&text).map_err(|e| e.to_string())?;
    for (key, value) in options {
        if settings.get(key).is_some() {
            return Err(format!("option {}: the Lab sets this one itself", key));
        }
        check_option(&defaults, key, value)?;
        settings[key.as_str()] = value.clone();
    }
    Ok(())
}

/// One setting from the page (the Options tab, or a team's own in the Configure team window): it must exist, not be one the
/// Lab sets itself, and have the default's kind (a wrong kind would crash a battle's worker: `Config::b` and friends panic).
fn check_option(defaults: &Value, key: &str, value: &Value) -> Result<(), String> {
    {
        let Some(default) = defaults.get(key) else { return Err(format!("option {}: no such setting", key)) };
        if key.starts_with('_') || ["SEED", "MAX_TURNS", "WORKERS", "NUM_SIMULATIONS", "BOT", "FORCES", "TEAM_SETTINGS"].contains(&key) {
            return Err(format!("option {}: the Lab sets this one itself", key));
        }
        let same_kind = match default {
            Value::Bool(_) => value.is_boolean(),
            Value::Number(_) => value.is_number(),
            Value::String(_) => value.is_string(),
            Value::Array(_) => value.is_array(),
            Value::Object(_) => value.is_object(),
            _ => true,
        };
        if !same_kind {
            return Err(format!("option {}: wrong kind of value (expected {})", key, match default { Value::Bool(_) => "on/off", Value::Number(_) => "a number", Value::String(_) => "text", Value::Array(_) => "a list", _ => "a table" }));
        }
    }
    Ok(())
}

// ---------------------------------------------------------------- what varies from battle to battle (CL14)
/// splitmix64: a small, fixed generator for the Lab's own choices (which board, which zone), so a battle's variant is a
/// pure function of the setup, its number and its seed, and can be played again.
fn mix(mut x: u64) -> u64 {
    x = x.wrapping_add(0x9E37_79B9_7F4A_7C15);
    x = (x ^ (x >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    x = (x ^ (x >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    x ^ (x >> 31)
}
const BOX_NAMES: [&str; 9] = ["NW", "N", "NE", "W", "Centre", "E", "SW", "S", "SE"];

fn zone_of(team: &Value, i: usize) -> ([bool; 9], bool) {
    // a team with no zone of its own: team 1 the west side, 2 east, 3 north, 4 south, the rest anywhere
    let default = [3usize, 5, 1, 7].get(i).copied();
    let mut boxes = [false; 9];
    match (team["zone"]["boxes"].as_array(), default) {
        (Some(a), _) => (0..9).for_each(|k| boxes[k] = a.get(k).and_then(|v| v.as_bool()).unwrap_or(false)),
        (None, Some(d)) => boxes[d] = true,
        (None, None) => boxes = [true; 9],
    }
    let walk_on = team["zone"]["walk_on"].as_bool().unwrap_or(true);
    (boxes, walk_on)
}

/// "N+NE (walks on)" for the results.
fn zone_label(boxes: &[bool; 9], walk_on: bool) -> String {
    let n = boxes.iter().filter(|b| **b).count();
    let names = if n == 9 { "Anywhere".to_string() } else if n == 8 && !boxes[4] { "Edge".to_string() } else { (0..9).filter(|k| boxes[*k]).map(|k| BOX_NAMES[k]).collect::<Vec<_>>().join("+") };
    format!("{} ({})", names, if walk_on { "walks on" } else { "placed" })
}

/// A run's whole plan: one built scenario per board of the board list, and for each battle the board and the starting
/// zones it gets. No team with a "zone" in the setup = the old deployment (initiative roll, home edge), untouched.
pub struct Plan {
    pub setup: Value,
    pub max_turns: i64,
    seed: u64,
    boards: Vec<(String, Arc<Scenario>)>,
    shuffle: bool,
    cache: Mutex<HashMap<String, Arc<Scenario>>>,
}

pub fn scenario_of(setup: &Value, catalog: &Catalog, paths: &SetupPaths) -> Result<Plan, String> {
    let has_zones = setup["teams"].as_array().is_some_and(|t| t.iter().any(|x| x.get("zone").is_some_and(|z| !z.is_null())));
    let first_zones = if has_zones { Some(Plan::zones(setup, 1, 1)) } else { None };
    let mut boards = Vec::new();
    let mut shuffle = false;
    if let Some(list) = setup["board"]["playlist"].as_array() {
        if list.is_empty() {
            return Err("the map list is empty".into());
        }
        shuffle = setup["board"]["order"].as_str() == Some("shuffle");
        for id in list {
            let id = id.as_str().ok_or("a map in the list has no name")?;
            let mut one = setup.clone();
            one["board"] = json!(id);
            boards.push((id.to_string(), Arc::new(scenario_one(&one, catalog, paths, first_zones.as_ref().map(|z| &z.0))?)));
        }
    } else {
        let label = setup["board"].as_str().map(String::from).unwrap_or_else(|| "stitched map".into());
        boards.push((label, Arc::new(scenario_one(setup, catalog, paths, first_zones.as_ref().map(|z| &z.0))?)));
    }
    let max_turns = boards[0].1.max_turns;
    Ok(Plan { setup: setup.clone(), max_turns, seed: setup["seed"].as_u64().unwrap_or(1), boards, shuffle, cache: Mutex::new(HashMap::new()) })
}

impl Plan {
    /// Each team's zone in battle `sim` (1-based), seed `seed`: (DEPLOY_ZONES for the engine, {team: label} for the results).
    /// Fixed: every team keeps its own. Rotating: team i takes the zone setup of team i-(sim-1), wrapping (two teams swap
    /// every battle; battle 3 of 3 teams gives team 3 team 1's). Random: one of the team's chosen boxes, fresh each battle.
    fn zones(setup: &Value, sim: u64, seed: u64) -> (Value, Value) {
        let teams = setup["teams"].as_array().cloned().unwrap_or_default();
        let n = teams.len().max(1);
        let mode = setup["zone_mode"].as_str().unwrap_or("fixed");
        let (mut zones, mut labels) = (serde_json::Map::new(), serde_json::Map::new());
        for (i, t) in teams.iter().enumerate() {
            let (mut boxes, mut walk_on) = match mode {
                "rotating" => zone_of(&teams[(i + n - ((sim as usize - 1) % n)) % n], (i + n - ((sim as usize - 1) % n)) % n),
                _ => zone_of(t, i),
            };
            if mode == "random" && setup["zone_opposite"].as_bool() == Some(true) && n == 2 {
                // two teams kept on opposite sides: team 1 draws, team 2 takes the mirror box (through the centre: k -> 8-k)
                let (b0, _) = zone_of(&teams[0], 0);
                let chosen0: Vec<usize> = (0..9).filter(|k| b0[*k]).collect();
                let p0 = if chosen0.is_empty() { 4 } else { chosen0[(mix(seed ^ mix(1)) % chosen0.len() as u64) as usize] };
                boxes = [false; 9];
                boxes[if i == 0 { p0 } else { 8 - p0 }] = true;
            } else if mode == "random" {
                let chosen: Vec<usize> = (0..9).filter(|k| boxes[*k]).collect();
                if chosen.len() > 1 {
                    let pick = chosen[(mix(seed ^ mix(i as u64 + 1)) % chosen.len() as u64) as usize];
                    boxes = [false; 9];
                    boxes[pick] = true;
                }
            }
            if boxes[4] && boxes.iter().filter(|b| **b).count() == 1 {
                walk_on = false; // the centre is not on an edge
            }
            let name = t["name"].as_str().unwrap_or("").to_string();
            zones.insert(name.clone(), json!({"boxes": boxes, "walk_on": walk_on}));
            labels.insert(name, json!(zone_label(&boxes, walk_on)));
        }
        (Value::Object(zones), Value::Object(labels))
    }

    /// The scenario for battle `sim` on `seed`, and what varied: {"board": id, "zones": {team: label}} (zones only when
    /// the setup uses them).
    pub fn scenario_for(&self, sim: u64, seed: u64) -> (Arc<Scenario>, Value) {
        let n = self.boards.len() as u64;
        let pos = (sim - 1) % n;
        let idx = if self.shuffle && n > 1 {
            // a fresh order of the whole list for every pass through it (Fisher-Yates from the run's seed and the pass number)
            let mut order: Vec<u64> = (0..n).collect();
            let pass = (sim - 1) / n;
            for k in (1..n as usize).rev() {
                order.swap(k, (mix(self.seed ^ mix(pass + 1) ^ mix(k as u64)) % (k as u64 + 1)) as usize);
            }
            order[pos as usize]
        } else {
            pos
        } as usize;
        let (board_id, base) = &self.boards[idx];
        let mut variant = json!({"board": board_id});
        if !self.setup["teams"].as_array().is_some_and(|t| t.iter().any(|x| x.get("zone").is_some_and(|z| !z.is_null()))) {
            return (base.clone(), variant);
        }
        let (zones, labels) = Plan::zones(&self.setup, sim, seed);
        variant["zones"] = labels;
        let key = format!("{}|{}", idx, zones);
        let mut cache = self.cache.lock().unwrap();
        let s = cache.entry(key).or_insert_with(|| {
            let mut s = (**base).clone();
            s.config["DEPLOY_ZONES"] = zones;
            Arc::new(s)
        });
        (s.clone(), variant)
    }
}

/// One battle's line in the battle list.
fn battle_line(sim: u64, seed: u64, r: &BattleResult, seconds: f64, variant: &Value) -> Value {
    let teams: serde_json::Map<String, Value> = r
        .teams
        .iter()
        .map(|(k, s)| (k.clone(), json!({"units": s.units, "units_lost": s.units_lost, "damage_dealt": s.damage_dealt, "max_hp": s.max_hp, "final_hp": s.final_hp, "attacks": s.attacks, "hits": s.hits,
            "armor": [s.final_armor, s.max_armor], "structure": [s.final_structure, s.max_structure]})))
        .collect();
    // the seed as text: seeds pass JavaScript's exact-integer limit
    // each unit: destroyed or not, and how (what the results filter asks about)
    let units: serde_json::Map<String, Value> = r.units.iter().map(|(k, s)| (k.clone(), json!({"name": s.name, "destroyed": s.destroyed, "cause": s.cause_of_death,
        "armor": [s.final_armor, s.max_armor], "structure": [s.final_structure, s.max_structure], "kills": s.kills, "alive": s.turns_alive,
        "locs": s.locations, "weapons": s.weapons, "track": s.track,
        // every critical slot: its name, and 1 / 0 for working / lost at the end (one text per location, the slot order of the unit file)
        "crits": s.crit_names.iter().map(|(l, n)| (l.clone(), json!({"names": n.join("|"),
            "alive": s.crit_alive.get(l).map(|a| a.iter().map(|x| if *x { '1' } else { '0' }).collect::<String>()).unwrap_or_default()}))).collect::<serde_json::Map<String, Value>>()}))).collect();
    json!({"sim": sim, "seed": seed.to_string(), "winner": r.winner, "turns": r.turns_taken, "seconds": seconds, "capped": r.turn_cap.is_some_and(|c| r.turns_taken >= c && r.winner == "Draw"), "teams": teams, "units": units, "board": variant["board"], "zones": variant["zones"]})
}

/// A battle line without its per-unit detail (what the battle list needs).
fn slim(line: &Value) -> Value {
    let mut l = line.clone();
    if let Some(units) = l["units"].as_object_mut() {
        for u in units.values_mut() {
            if let Some(o) = u.as_object_mut() {
                for k in ["locs", "weapons", "armor", "structure", "kills", "alive"] { o.remove(k); }
            }
        }
    }
    l
}

/// Every cause of death seen, with how many units died of it: [[cause, count], ...] most common first (the finder's list).
fn causes_of(lines: &[&Value]) -> Value {
    let mut c: std::collections::BTreeMap<String, u64> = Default::default();
    for l in lines {
        for u in l["units"].as_object().into_iter().flat_map(|o| o.values()) {
            if u["destroyed"] == true { *c.entry(u["cause"].as_str().unwrap_or("unknown").to_string()).or_insert(0) += 1; }
        }
    }
    let mut v: Vec<(String, u64)> = c.into_iter().collect();
    v.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
    json!(v)
}

/// A batch: started by `start`, read by `progress` / `results`.
pub struct Run {
    pub id: u64,
    pub setup: Value,
    pub plan: Arc<Plan>,
    pub battles: u64,
    pub seed: u64,
    pub done: AtomicU64,
    pub cancel: AtomicBool,
    pub finished: AtomicBool,
    pub started: Instant,
    pub seconds: Mutex<Option<f64>>,
    pub lines: Mutex<Vec<Value>>,
    pub crashed: Mutex<Vec<Value>>,
}

impl Run {
    #[allow(dead_code)]
    /// A batch whose battles are played elsewhere (the browser build: the page's workers) and handed in with
    /// `push_line` / `push_crash` / `finish`.
    pub fn external(id: u64, setup: Value, plan: Plan) -> Arc<Run> {
        let battles = setup["battles"].as_u64().unwrap_or(20).clamp(1, 100_000);
        Arc::new(Run {
            id,
            seed: setup["seed"].as_u64().unwrap_or(1),
            setup,
            plan: Arc::new(plan),
            battles,
            done: AtomicU64::new(0),
            cancel: AtomicBool::new(false),
            finished: AtomicBool::new(false),
            started: Instant::now(),
            seconds: Mutex::new(None),
            lines: Mutex::new(Vec::new()),
            crashed: Mutex::new(Vec::new()),
        })
    }

    /// Battles played elsewhere, handed in (the browser build): their lines and crashes, counted as done.
    #[allow(dead_code)]
    pub fn add(&self, lines: Vec<Value>, crashed: Vec<Value>) {
        self.done.fetch_add((lines.len() + crashed.len()) as u64, Ordering::Relaxed);
        self.lines.lock().unwrap().extend(lines);
        self.crashed.lock().unwrap().extend(crashed);
    }

    /// The elsewhere-played batch is over: its time (the page's, else ours so far).
    #[allow(dead_code)]
    pub fn finish(&self, seconds: Option<f64>) {
        *self.seconds.lock().unwrap() = Some(seconds.unwrap_or_else(|| self.started.elapsed().as_secs_f64()));
        self.finished.store(true, Ordering::SeqCst);
    }

    /// Starts the batch on its own thread and returns at once.
    #[cfg(not(target_arch = "wasm32"))]
    pub fn start(id: u64, setup: Value, plan: Plan) -> Arc<Run> {
        let battles = setup["battles"].as_u64().unwrap_or(20).clamp(1, 100_000);
        let seed = setup["seed"].as_u64().unwrap_or(1);
        let cores = std::thread::available_parallelism().map_or(1, |n| n.get());
        let threads = threads_for(setup["threads"].as_u64().unwrap_or(0) as usize, cores, setup["full_power"].as_bool().unwrap_or(false));
        let run = Arc::new(Run {
            id,
            setup,
            plan: Arc::new(plan),
            battles,
            seed,
            done: AtomicU64::new(0),
            cancel: AtomicBool::new(false),
            finished: AtomicBool::new(false),
            started: Instant::now(),
            seconds: Mutex::new(None),
            lines: Mutex::new(Vec::new()),
            crashed: Mutex::new(Vec::new()),
        });
        let r = run.clone();
        std::thread::spawn(move || {
            let pool = rayon::ThreadPoolBuilder::new().num_threads(threads).build().expect("thread pool");
            pool.install(|| {
                (1..=r.battles).into_par_iter().for_each(|sim| {
                    if r.cancel.load(Ordering::Relaxed) {
                        return;
                    }
                    let s = PcgDice::battle_seed(r.seed, sim);
                    let t = Instant::now();
                    // a panic in one battle is that battle's line, not the end of the batch
                    let (scenario, variant) = r.plan.scenario_for(sim, s);
                    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| scenario.run(s, false))) {
                        Ok((result, _)) => r.lines.lock().unwrap().push(battle_line(sim, s, &result, t.elapsed().as_secs_f64(), &variant)),
                        Err(e) => {
                            let msg = e.downcast_ref::<String>().cloned().or_else(|| e.downcast_ref::<&str>().map(|m| m.to_string())).unwrap_or_else(|| "panic".into());
                            r.crashed.lock().unwrap().push(json!({"sim": sim, "seed": s.to_string(), "crashed": msg, "board": variant["board"], "zones": variant["zones"]}));
                        }
                    }
                    r.done.fetch_add(1, Ordering::Relaxed);
                });
            });
            *r.seconds.lock().unwrap() = Some(r.started.elapsed().as_secs_f64());
            r.finished.store(true, Ordering::SeqCst);
        });
        run
    }

    /// A finished run read back from a saved file (CL20): its battle lines, crashes and setup; the battles themselves are
    /// played again from their seeds when one is replayed (a pure function of the setup, the battle number and its seed).
    pub fn restore(id: u64, setup: Value, plan: Plan, lines: Vec<Value>, crashed: Vec<Value>, seconds: f64) -> Arc<Run> {
        let battles = setup["battles"].as_u64().unwrap_or(lines.len() as u64).clamp(1, 100_000);
        Arc::new(Run {
            id,
            seed: setup["seed"].as_u64().unwrap_or(1),
            setup,
            plan: Arc::new(plan),
            battles,
            done: AtomicU64::new((lines.len() + crashed.len()) as u64),
            cancel: AtomicBool::new(false),
            finished: AtomicBool::new(true),
            started: Instant::now(),
            seconds: Mutex::new(Some(seconds)),
            lines: Mutex::new(lines),
            crashed: Mutex::new(crashed),
        })
    }

    /// Everything a saved file needs (see main.rs `save_run`, which adds the unit files). The file leads with what is
    /// needed to PLAY THE BATTLES AGAIN (build, setup, batch seed, the seeds of the crashed and the turn-capped battles:
    /// what a bug report wants); the per-battle statistics (`lines`, what "Open a run file" shows) come after.
    pub fn export(&self, unit_files: serde_json::Map<String, Value>) -> Value {
        let mut lines = self.lines.lock().unwrap().clone();
        lines.sort_by_key(|l| l["sim"].as_u64());
        let mut crashed = self.crashed.lock().unwrap().clone();
        crashed.sort_by_key(|l| l["sim"].as_u64());
        let capped: Vec<Value> = lines.iter().filter(|l| l["capped"] == true).map(|l| json!({"sim": l["sim"], "seed": l["seed"], "board": l["board"], "zones": l["zones"]})).collect();
        json!({"combatlab_run": 1, "version": env!("CARGO_PKG_VERSION"),
               "build": option_env!("COMBATLAB_BUILD").unwrap_or("unknown"),
               "platform": if cfg!(target_arch = "wasm32") { "browser" } else { "desktop" },
               "replay_with": "the setup below and the batch seed play the same battles again, on any machine with the same build",
               "seed_rule": "battle n is played on battle_seed(batch_seed, n): battle 1 on the batch seed itself, the others on a fixed mix of the batch seed and n. Each battle's own seed is its `seed` in `lines`, `crashed` and `capped`.",
               "batch_seed": self.seed, "battles": self.battles, "setup": self.setup,
               "crashed": crashed, "capped": capped,
               "seconds": self.seconds.lock().unwrap().unwrap_or(0.0), "lines": lines,
               "unit_files": unit_files})
    }

    pub fn progress(&self) -> Value {
        let elapsed = self.seconds.lock().unwrap().unwrap_or_else(|| self.started.elapsed().as_secs_f64());
        json!({"run": self.id, "done": self.done.load(Ordering::Relaxed), "battles": self.battles, "finished": self.finished.load(Ordering::SeqCst), "cancelled": self.cancel.load(Ordering::Relaxed), "seconds": elapsed})
    }

    /// The statistics and the battle list, so far while the batch runs. Request: {run, filter?, from?, to?, bucket?}.
    /// FILTER keeps the battles that match it (see `matches`); the statistics are those of the battles kept, and of all.
    /// The list is long for a big batch, so it comes in pieces: `battles` = the kept battles numbered from..=to (at most
    /// 500), and with `bucket` = B, `buckets` = how many kept battles each run of B battle numbers in from..=to holds
    /// (the page shows a long list as nested ranges: "Battles 1-100 (37)").
    pub fn results(&self, req: &Value) -> Value {
        let mut lines = self.lines.lock().unwrap().clone();
        lines.sort_by_key(|l| l["sim"].as_u64());
        let filter = &req["filter"];
        let kept: Vec<&Value> = lines.iter().filter(|l| matches(l, filter)).collect();
        let from = req["from"].as_u64().unwrap_or(1);
        let to = req["to"].as_u64().unwrap_or(self.battles);
        let in_range: Vec<&&Value> = kept.iter().filter(|l| (from..=to).contains(&l["sim"].as_u64().unwrap_or(0))).collect();
        let mut out = json!({
            "progress": self.progress(),
            "all": self.summary(&lines.iter().collect::<Vec<_>>()),
            "summary": self.summary(&kept),
            "matching": kept.len(),
            "in_range": in_range.len(),
            "battles": in_range.iter().take(500).map(|l| slim(l)).collect::<Vec<_>>(),
            "causes": causes_of(&lines.iter().collect::<Vec<_>>()),
            "units": lines.first().map_or(json!({}), |l| l["units"].as_object().map(|u| u.iter().map(|(k, v)| (k.clone(), v["name"].clone())).collect::<serde_json::Map<_, _>>()).map_or(json!({}), Value::Object)),
            "crashed": self.crashed.lock().unwrap().clone(),
        });
        if req["unit_stats"] == true {
            out["unit_stats"] = self.unit_stats(&kept);
        }
        if let Some(b) = req["bucket"].as_u64().filter(|b| *b > 0) {
            let mut counts: Vec<u64> = vec![0; ((to + 1 - from.min(to + 1)) as f64 / b as f64).ceil() as usize];
            for l in &in_range {
                let i = ((l["sim"].as_u64().unwrap_or(from) - from) / b) as usize;
                if i < counts.len() {
                    counts[i] += 1;
                }
            }
            out["buckets"] = json!(counts);
        }
        out
    }

    /// Per unit, over these battles (the Results page's expandable unit folders): how often it survived, the percentage
    /// breakdown of how it died, the armor and structure left (and as a share of the start), per location, kills, and per
    /// weapon the damage a turn, accuracy and how often it was used. Returns {team: {unit label: {...}}}.
    fn unit_stats(&self, lines: &[&Value]) -> Value {
        let mut out = serde_json::Map::new();
        let sum = |f: &dyn Fn(&Value) -> Option<f64>| lines.iter().filter_map(|l| f(l)).sum::<f64>();
        let _ = sum;
        // every unit label, in the order the first battle lists them
        let mut labels: Vec<String> = Vec::new();
        for l in lines {
            for k in l["units"].as_object().into_iter().flat_map(|o| o.keys()) {
                if !labels.contains(k) { labels.push(k.clone()); }
            }
        }
        for label in labels {
            let rows: Vec<&Value> = lines.iter().filter_map(|l| l["units"].get(&label)).collect();
            let n = rows.len().max(1) as f64;
            let get = |r: &Value, path: &[&str]| path.iter().fold(r, |v, k| &v[*k]).as_f64().unwrap_or(0.0);
            let destroyed = rows.iter().filter(|r| r["destroyed"] == true).count();
            let mut causes: std::collections::BTreeMap<String, usize> = Default::default();
            for r in rows.iter().filter(|r| r["destroyed"] == true) {
                *causes.entry(r["cause"].as_str().unwrap_or("unknown").to_string()).or_insert(0) += 1;
            }
            let pair = |k: &str| (rows.iter().map(|r| r[k][0].as_f64().unwrap_or(0.0)).sum::<f64>() / n, rows.iter().map(|r| r[k][1].as_f64().unwrap_or(0.0)).sum::<f64>() / n);
            let mut locs = serde_json::Map::new();
            let loc_names: Vec<String> = rows.first().and_then(|r| r["locs"].as_object()).map(|o| o.keys().cloned().collect()).unwrap_or_default();
            for loc in &loc_names {
                let m = |i: usize| rows.iter().map(|r| r["locs"][loc][i].as_f64().unwrap_or(0.0)).sum::<f64>() / n;
                // armor = FRONT armor; rear apart (Daniel, 2026-11-20); rows from older run files have no rear (0)
                locs.insert(loc.clone(), json!({"armor": m(0), "armor_max": m(1), "structure": m(2), "structure_max": m(3), "rear": m(4), "rear_max": m(5)}));
            }
            // movement and spacing: the mean per turn it counted over (a ratio of sums, so a unit that died early is not diluted)
            let tr = |i: usize| rows.iter().map(|r| r["track"][i].as_f64().unwrap_or(0.0)).sum::<f64>();
            let per = |sum: f64, k: f64| if k > 0.0 { json!(sum / k) } else { Value::Null };
            let track = json!({"hexes_moved": per(tr(0), tr(1)), "nearest_enemy": per(tr(2), tr(3)), "target": per(tr(4), tr(5)), "allies": per(tr(6), tr(7))});
            // critical slots: the share of battles each slot was still working at the end
            let mut crits = serde_json::Map::new();
            if let Some(first) = rows.first().and_then(|r| r["crits"].as_object()) {
                for (loc, v) in first {
                    let names = v["names"].as_str().unwrap_or("");
                    let alive: Vec<f64> = (0..names.split('|').count()).map(|i| {
                        rows.iter().map(|r| if r["crits"][loc]["alive"].as_str().and_then(|a| a.as_bytes().get(i)) == Some(&b'1') { 1.0 } else { 0.0 }).sum::<f64>() / n
                    }).collect();
                    crits.insert(loc.clone(), json!({"names": names.split('|').collect::<Vec<_>>(), "survival": alive}));
                }
            }
            let alive: f64 = rows.iter().map(|r| get(r, &["alive"])).sum();
            let mut weapons = serde_json::Map::new();
            let wnames: Vec<String> = rows.first().and_then(|r| r["weapons"].as_object()).map(|o| o.keys().cloned().collect()).unwrap_or_default();
            for w in &wnames {
                let t = |i: usize| rows.iter().map(|r| r["weapons"][w][i].as_f64().unwrap_or(0.0)).sum::<f64>();
                let (fired, hits, dmg, turns) = (t(0), t(1), t(2), t(3));
                weapons.insert(w.clone(), json!({"fired_per_battle": fired / n, "accuracy": if fired > 0.0 { hits / fired } else { 0.0 },
                    "damage_per_turn": if alive > 0.0 { dmg / alive } else { 0.0 }, "damage_per_battle": dmg / n, "utilization": if alive > 0.0 { turns / alive } else { 0.0 }}));
            }
            let (a, am) = pair("armor");
            let (s, sm) = pair("structure");
            let team = label.split(' ').next().unwrap_or("").to_string();
            let entry = out.entry(team).or_insert_with(|| json!({}));
            entry[&label] = json!({"name": rows.first().map_or(Value::Null, |r| r["name"].clone()), "battles": rows.len(), "survived": rows.len() - destroyed,
                "causes": causes, "armor_left": a, "armor_max": am, "structure_left": s, "structure_max": sm, "kills": rows.iter().map(|r| get(r, &["kills"])).sum::<f64>() / n,
                "turns_alive": alive / n, "locations": locs, "weapons": weapons, "track": track, "crits": crits});
        }
        Value::Object(out)
    }

    /// Wins, losses, damage, units lost... over these battles.
    fn summary(&self, lines: &[&Value]) -> Value {
        let n = lines.len().max(1) as f64;
        let mut per_team = serde_json::Map::new();
        for t in self.setup["teams"].as_array().into_iter().flatten() {
            let t = t["name"].as_str().unwrap_or("");
            let wins = lines.iter().filter(|l| l["winner"] == t).count();
            let mean = |k: &str| lines.iter().map(|l| l["teams"][t][k].as_f64().unwrap_or(0.0)).sum::<f64>() / n;
            let mean_pair = |k: &str, i: usize| lines.iter().map(|l| l["teams"][t][k][i].as_f64().unwrap_or(0.0)).sum::<f64>() / n;
            let (attacks, hits) = lines.iter().fold((0.0, 0.0), |(a, h), l| (a + l["teams"][t]["attacks"].as_f64().unwrap_or(0.0), h + l["teams"][t]["hits"].as_f64().unwrap_or(0.0)));
            let hit_rate = if attacks > 0.0 { hits / attacks } else { 0.0 };
            per_team.insert(t.to_string(), json!({"wins": wins, "win_rate": wins as f64 / n, "mean_damage_dealt": mean("damage_dealt"), "mean_units_lost": mean("units_lost"), "mean_hp_left": mean("final_hp"), "max_hp": mean("max_hp"), "hit_rate": hit_rate,
                "mean_armor_left": mean_pair("armor", 0), "max_armor": mean_pair("armor", 1), "mean_structure_left": mean_pair("structure", 0), "max_structure": mean_pair("structure", 1)}));
        }
        let draws = lines.iter().filter(|l| l["winner"] == "Draw").count();
        let capped = lines.iter().filter(|l| l["capped"] == true).count();
        let turns = lines.iter().map(|l| l["turns"].as_f64().unwrap_or(0.0)).sum::<f64>() / n;
        let battle_secs = lines.iter().map(|l| l["seconds"].as_f64().unwrap_or(0.0)).sum::<f64>() / n;
        json!({"battles": lines.len(), "teams": per_team, "draws": draws, "hit_turn_cap": capped, "max_turns": self.plan.max_turns, "mean_turns": turns, "mean_battle_seconds": battle_secs})
    }
}

/// Whether a battle's line passes the results filter: {"winner": team or "Draw", "capped": true / false,
/// "min_turns", "max_turns", "units": [{"unit": label, "state": "destroyed" | "survived", "cause": text}]} - every part
/// given must hold; a unit's cause is matched as words inside its cause of death ("Center Torso", "Head"...).
pub fn matches(line: &Value, f: &Value) -> bool {
    if let Some(w) = f["winner"].as_str().filter(|w| !w.is_empty()) {
        if line["winner"] != w {
            return false;
        }
    }
    if let Some(c) = f["capped"].as_bool() {
        if line["capped"].as_bool() != Some(c) {
            return false;
        }
    }
    let turns = line["turns"].as_i64().unwrap_or(0);
    if f["min_turns"].as_i64().is_some_and(|m| turns < m) || f["max_turns"].as_i64().is_some_and(|m| turns > m) {
        return false;
    }
    for c in f["units"].as_array().into_iter().flatten() {
        let u = &line["units"][c["unit"].as_str().unwrap_or("")];
        let destroyed = u["destroyed"].as_bool().unwrap_or(false);
        match c["state"].as_str() {
            Some("destroyed") if !destroyed => return false,
            Some("survived") if destroyed => return false,
            _ => {}
        }
        // `cause_is`: exactly this cause, as the unit statistics list it ("unknown" when the line has none); set by a click on
        // a "How it ended" row (Daniel, 2026-11-17). `cause` below is the typed form: every word must appear.
        if let Some(exact) = c["cause_is"].as_str() {
            if !destroyed || u["cause"].as_str().unwrap_or("unknown") != exact {
                return false;
            }
        }
        if let Some(text) = c["cause"].as_str().filter(|t| !t.trim().is_empty()) {
            let cause = u["cause"].as_str().unwrap_or("").to_lowercase();
            if !text.to_lowercase().split_whitespace().all(|w| cause.contains(w)) {
                return false;
            }
        }
    }
    true
}

/// The threads a batch plays on. `asked` 0 = automatic: every core but a quarter of them (at least one), so other programs
/// keep room to run (Daniel, 2026-11-17: a game crashed when a run took every cycle). A number typed in is used as it is, up to
/// the core count. `full_power` (the Options page's "Full power" box, Daniel 2026-11-17) = every core, whatever was typed.
/// The browser build (engine/wasm/web/engine.js `autoThreads`) uses the same rule.
#[cfg_attr(target_arch = "wasm32", allow(dead_code))]
pub fn threads_for(asked: usize, cores: usize, full_power: bool) -> usize {
    let cores = cores.max(1);
    if full_power { cores } else if asked == 0 { (cores - (cores / 4).max(1)).max(1) } else { asked.min(cores) }
}

/// Seconds a batch of `battles` will take on `threads` threads (0 = automatic, `threads_for`), from a few pilot battles played side
/// by side now (on seeds the batch itself does not use first).
#[cfg(not(target_arch = "wasm32"))]
pub fn estimate(scenario: &Scenario, battles: u64, threads: usize, full_power: bool) -> Value {
    let cores = std::thread::available_parallelism().map_or(1, |n| n.get());
    let threads = threads_for(threads, cores, full_power);
    let pilots = threads.clamp(1, 4) as u64;
    let started = Instant::now();
    let times: Vec<f64> = (0..pilots)
        .into_par_iter()
        .map(|i| {
            let t = Instant::now();
            let _ = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| scenario.run(PcgDice::battle_seed(0xC0FFEE, 1000 + i), false)));
            t.elapsed().as_secs_f64()
        })
        .collect();
    let per_battle = times.iter().sum::<f64>() / times.len() as f64;
    let waves = (battles as f64 / threads as f64).ceil();
    json!({"seconds": per_battle * waves, "per_battle": per_battle, "threads": threads, "pilot_battles": pilots, "pilot_seconds": started.elapsed().as_secs_f64()})
}

/// Plays battle `sim` of a batch (seed `run_seed`) and returns its line for the battle list, or what a crash would
/// record. The browser build calls this in its workers (the desktop's `Run::start` does the same inline).
/// Returns (is a crash, the line).
#[allow(dead_code)]
pub fn play_one(plan: &Plan, run_seed: u64, sim: u64) -> (bool, Value) {
    let s = PcgDice::battle_seed(run_seed, sim);
    let t = Instant::now();
    let (scenario, variant) = plan.scenario_for(sim, s);
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| scenario.run(s, false))) {
        Ok((result, _)) => (false, battle_line(sim, s, &result, t.elapsed().as_secs_f64(), &variant)),
        Err(e) => {
            let msg = e.downcast_ref::<String>().cloned().or_else(|| e.downcast_ref::<&str>().map(|m| m.to_string())).unwrap_or_else(|| "panic".into());
            (true, json!({"sim": sim, "seed": s.to_string(), "crashed": msg, "board": variant["board"], "zones": variant["zones"]}))
        }
    }
}
