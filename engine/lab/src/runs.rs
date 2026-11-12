//! Batches of battles for the Lab: a SETUP (what the pages send) made into engine settings, run on its own threads
//! (the server keeps answering while it runs), counted as it goes, stoppable, and summed up at the end.
//!
//! SETUP (JSON):
//! ```text
//! {"teams": [{"name": "Red", "bot": "gladiator" | "princess" | "hydra",
//!             "units": [{"unit": "Atlas AS7-K.mtf", "gunnery": 4, "piloting": 5}, ...]}, ...],
//!  "board": "16x17_Grassland_1.board",            (a board's id from list_boards)
//!  "battles": 20, "seed": 1, "threads": 0 (= every core), "max_turns": 100 (optional)}
//! ```
//! Battle n of a batch is played on `PcgDice::battle_seed(seed, n)`, as `btsim` does, so a battle of the Lab is the
//! same battle `btsim` plays for the same settings and seed - and any one can be played again, with its full history,
//! from (setup, seed) alone (`history`).
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Instant;

use btsim_core::dice::PcgDice;
use btsim_core::results::BattleResult;
use btsim_core::scenario::{Scenario, SetupPaths};
use rayon::prelude::*;
use serde_json::{json, Value};

use crate::catalog::Catalog;

pub const BOTS: [&str; 3] = ["gladiator", "princess", "hydra"];

/// The engine settings and the turn cap for a setup, the packed units and board unpacked. Err = what is wrong with it,
/// in words for the page.
pub fn scenario_of(setup: &Value, catalog: &Catalog, paths: &SetupPaths) -> Result<Scenario, String> {
    let teams = setup["teams"].as_array().ok_or("no teams")?;
    if teams.len() < 2 {
        return Err("a battle needs at least two teams".into());
    }
    let mut forces = Vec::new();
    let mut hydra_teams = Vec::new();
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
        let units = t["units"].as_array().filter(|u| !u.is_empty()).ok_or_else(|| format!("team {} has no units", name))?;
        for u in units {
            let id = u["unit"].as_str().ok_or_else(|| format!("team {}: a unit with no file", name))?;
            catalog.ensure(id)?;
            let skill = |k: &str, d: i64| u[k].as_i64().unwrap_or(d).clamp(0, 8);
            forces.push(json!({"team": name, "mtf": id, "bot": bot, "gunnery": skill("gunnery", 4), "piloting": skill("piloting", 5)}));
        }
    }
    let board = setup["board"].as_str().ok_or("no board chosen")?;
    catalog.ensure(board)?;
    let settings = json!({"FORCES": forces, "DEFAULT_BOARD_PATH": board, "DEPLOYMENT": "home_edge"});
    let mut s = Scenario::from_settings(&settings, paths)?;
    s.hydra_teams = hydra_teams;
    if let Some(cap) = setup["max_turns"].as_i64().filter(|c| *c > 0) {
        s.max_turns = cap;
    }
    Ok(s)
}

/// One battle's line in the battle list.
fn battle_line(sim: u64, seed: u64, r: &BattleResult, seconds: f64) -> Value {
    let teams: serde_json::Map<String, Value> = r
        .teams
        .iter()
        .map(|(k, s)| (k.clone(), json!({"units": s.units, "units_lost": s.units_lost, "damage_dealt": s.damage_dealt, "max_hp": s.max_hp, "final_hp": s.final_hp, "attacks": s.attacks, "hits": s.hits})))
        .collect();
    // the seed as text: seeds pass JavaScript's exact-integer limit
    json!({"sim": sim, "seed": seed.to_string(), "winner": r.winner, "turns": r.turns_taken, "seconds": seconds, "capped": r.turn_cap.is_some_and(|c| r.turns_taken >= c && r.winner == "Draw"), "teams": teams})
}

/// A batch: started by `start`, read by `progress` / `results`.
pub struct Run {
    pub id: u64,
    pub setup: Value,
    pub scenario: Arc<Scenario>,
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
    /// Starts the batch on its own thread and returns at once.
    pub fn start(id: u64, setup: Value, scenario: Scenario) -> Arc<Run> {
        let battles = setup["battles"].as_u64().unwrap_or(20).clamp(1, 100_000);
        let seed = setup["seed"].as_u64().unwrap_or(1);
        let threads = setup["threads"].as_u64().unwrap_or(0) as usize;
        let run = Arc::new(Run {
            id,
            setup,
            scenario: Arc::new(scenario),
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
                    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| r.scenario.run(s, false))) {
                        Ok((result, _)) => r.lines.lock().unwrap().push(battle_line(sim, s, &result, t.elapsed().as_secs_f64())),
                        Err(e) => {
                            let msg = e.downcast_ref::<String>().cloned().or_else(|| e.downcast_ref::<&str>().map(|m| m.to_string())).unwrap_or_else(|| "panic".into());
                            r.crashed.lock().unwrap().push(json!({"sim": sim, "seed": s.to_string(), "crashed": msg}));
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

    pub fn progress(&self) -> Value {
        let elapsed = self.seconds.lock().unwrap().unwrap_or_else(|| self.started.elapsed().as_secs_f64());
        json!({"run": self.id, "done": self.done.load(Ordering::Relaxed), "battles": self.battles, "finished": self.finished.load(Ordering::SeqCst), "cancelled": self.cancel.load(Ordering::Relaxed), "seconds": elapsed})
    }

    /// The statistics and the battle list (so far, while the batch runs).
    pub fn results(&self) -> Value {
        let mut lines = self.lines.lock().unwrap().clone();
        lines.sort_by_key(|l| l["sim"].as_u64());
        let n = lines.len().max(1) as f64;
        let mut teams: Vec<String> = Vec::new();
        for t in self.setup["teams"].as_array().into_iter().flatten() {
            teams.push(t["name"].as_str().unwrap_or("").to_string());
        }
        let mut per_team = serde_json::Map::new();
        for t in &teams {
            let wins = lines.iter().filter(|l| l["winner"] == t.as_str()).count();
            let mean = |k: &str| lines.iter().map(|l| l["teams"][t.as_str()][k].as_f64().unwrap_or(0.0)).sum::<f64>() / n;
            let (attacks, hits) = lines.iter().fold((0.0, 0.0), |(a, h), l| (a + l["teams"][t.as_str()]["attacks"].as_f64().unwrap_or(0.0), h + l["teams"][t.as_str()]["hits"].as_f64().unwrap_or(0.0)));
            let hit_rate = if attacks > 0.0 { hits / attacks } else { 0.0 };
            per_team.insert(t.clone(), json!({"wins": wins, "win_rate": wins as f64 / n, "mean_damage_dealt": mean("damage_dealt"), "mean_units_lost": mean("units_lost"), "mean_hp_left": mean("final_hp"), "max_hp": mean("max_hp"), "hit_rate": hit_rate}));
        }
        let draws = lines.iter().filter(|l| l["winner"] == "Draw").count();
        let capped = lines.iter().filter(|l| l["capped"] == true).count();
        let turns = lines.iter().map(|l| l["turns"].as_f64().unwrap_or(0.0)).sum::<f64>() / n;
        let battle_secs = lines.iter().map(|l| l["seconds"].as_f64().unwrap_or(0.0)).sum::<f64>() / n;
        json!({
            "progress": self.progress(),
            "summary": {"battles": lines.len(), "teams": per_team, "draws": draws, "hit_turn_cap": capped, "max_turns": self.scenario.max_turns, "mean_turns": turns, "mean_battle_seconds": battle_secs},
            "battles": lines,
            "crashed": self.crashed.lock().unwrap().clone(),
        })
    }
}

/// Seconds a batch of `battles` will take on `threads` threads (0 = every core), from a few pilot battles played side
/// by side now (on seeds the batch itself does not use first).
pub fn estimate(scenario: &Scenario, battles: u64, threads: usize) -> Value {
    let cores = std::thread::available_parallelism().map_or(1, |n| n.get());
    let threads = if threads == 0 { cores } else { threads.min(cores) };
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
