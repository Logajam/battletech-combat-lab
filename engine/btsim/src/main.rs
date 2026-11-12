//! btsim SCENARIO_DIR [--battles N] [--seed S] [--threads T] [--log N] [--out FILE] [--hydra TEAM[,TEAM]]
//! Plays N battles of a scenario (tools/port_scenario.py writes one) in parallel, one battle a thread, each on its own seed
//! (battle 1 on S, later ones mixed from S and the number), and prints a JSON summary: wins per team, turns, damage.
use std::path::PathBuf;

use btsim_core::dice::PcgDice;
use btsim_core::results::BattleResult;
use btsim_core::scenario::Scenario;
use rayon::prelude::*;
use serde_json::{json, Value};

/// The engine makes millions of small, short-lived allocations a battle: mimalloc handles those much faster than the
/// system allocator, above all with several battles running side by side.
#[global_allocator]
static ALLOC: mimalloc::MiMalloc = mimalloc::MiMalloc;

fn arg(args: &[String], name: &str) -> Option<String> {
    args.iter().position(|a| a == name).and_then(|i| args.get(i + 1)).cloned()
}

fn battle_json(sim: u64, seed: u64, r: &BattleResult) -> Value {
    let teams: serde_json::Map<String, Value> = r
        .teams
        .iter()
        .map(|(k, s)| (k.clone(), json!({"name": s.name, "max_hp": s.max_hp, "final_hp": s.final_hp, "destroyed": s.destroyed, "attacks": s.attacks, "hits": s.hits, "damage_dealt": s.damage_dealt, "units": s.units})))
        .collect();
    json!({"sim": sim, "seed": seed, "turns": r.turns_taken, "winner": r.winner, "destroyed": r.destroyed, "teams": teams})
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let Some(dir) = args.first().filter(|a| !a.starts_with("--")) else {
        eprintln!("usage: btsim SCENARIO_DIR [--battles N] [--seed S] [--threads T] [--log N] [--out FILE] [--hydra TEAM[,TEAM]] [--set KEY=VALUE ...] [--ledger FILE] [--max-turns N]");
        std::process::exit(2);
    };
    let battles: u64 = arg(&args, "--battles").map_or(1, |v| v.parse().expect("--battles"));
    let seed: u64 = arg(&args, "--seed").map_or(1, |v| v.parse().expect("--seed"));
    let log_first: u64 = arg(&args, "--log").map_or(0, |v| v.parse().expect("--log"));
    if let Some(t) = arg(&args, "--threads") {
        rayon::ThreadPoolBuilder::new().num_threads(t.parse().expect("--threads")).build_global().unwrap();
    }
    let mut scenario = Scenario::load(&PathBuf::from(dir));
    // --set KEY=VALUE (any number; session 25): a setting changed for this run, e.g. --set HYDRA_PLAYOUT=s5a. VALUE is read
    // as JSON when it parses (numbers, true / false), else as text.
    for (i, a) in args.iter().enumerate() {
        if a == "--set" {
            let kv = args.get(i + 1).expect("--set KEY=VALUE");
            let (k, v) = kv.split_once('=').expect("--set KEY=VALUE");
            let value: Value = serde_json::from_str(v).unwrap_or_else(|_| Value::String(v.to_string()));
            scenario.config.as_object_mut().unwrap().insert(k.to_string(), value);
        }
    }
    // --max-turns N (session 25): the turn cap for this run, in place of the scenario's (meta max_turns, default 50). A
    // battle is the same as under the old cap up to it (same seed, same dice), so a raised cap only plays draws on.
    if let Some(n) = arg(&args, "--max-turns") {
        scenario.max_turns = n.parse().expect("--max-turns");
    }
    // --hydra TEAM[,TEAM]: those teams are driven by Hydra (INTEGRATION__HYDRA.md)
    if let Some(t) = arg(&args, "--hydra") {
        scenario.hydra_teams = t.split(',').map(|x| x.to_string()).collect();
    }
    // --ledger FILE (session 25, S6 calibration): every battle also records a ledger snapshot at the end of each turn;
    // written as one JSON line per battle {sim, seed, winner, turns, snapshots}. Results are the same as without it.
    if let Some(path) = arg(&args, "--ledger") {
        let started = std::time::Instant::now();
        let runs: Vec<(u64, u64, BattleResult, Vec<Value>)> = (1..=battles)
            .into_par_iter()
            .map(|sim| {
                let s = PcgDice::battle_seed(seed, sim);
                let (r, snaps) = scenario.run_recorded(s);
                (sim, s, r, snaps)
            })
            .collect();
        let mut text = String::new();
        for (sim, s, r, snaps) in &runs {
            text.push_str(&serde_json::to_string(&json!({"sim": sim, "seed": s, "winner": r.winner, "turns": r.turns_taken, "snapshots": snaps})).unwrap());
            text.push('\n');
        }
        std::fs::write(path, text).unwrap();
        let out = json!({"battles": battles, "seed": seed, "seconds": started.elapsed().as_secs_f64(), "results": runs.iter().map(|(sim, s, r, _)| battle_json(*sim, *s, r)).collect::<Vec<_>>()});
        println!("{}", serde_json::to_string_pretty(&out).unwrap());
        return;
    }
    let started = std::time::Instant::now();
    let runs: Vec<(u64, u64, BattleResult, Vec<String>)> = (1..=battles)
        .into_par_iter()
        .map(|sim| {
            let s = PcgDice::battle_seed(seed, sim);
            let (r, log) = scenario.run(s, sim <= log_first);
            (sim, s, r, log)
        })
        .collect();
    let secs = started.elapsed().as_secs_f64();
    let mut wins: serde_json::Map<String, Value> = serde_json::Map::new();
    let (mut turns, mut capped) = (0i64, 0u64);
    for (_, _, r, _) in &runs {
        let n = wins.get(&r.winner).and_then(|v| v.as_u64()).unwrap_or(0);
        wins.insert(r.winner.clone(), json!(n + 1));
        turns += r.turns_taken;
        if r.turn_cap.is_some_and(|c| r.turns_taken >= c) {
            capped += 1;
        }
    }
    let out = json!({
        "battles": battles,
        "seed": seed,
        "seconds": secs,
        "wins": wins,
        "mean_turns": turns as f64 / battles as f64,
        "hit_turn_cap": capped,
        "results": runs.iter().map(|(sim, s, r, _)| battle_json(*sim, *s, r)).collect::<Vec<_>>(),
        "logs": runs.iter().filter(|(_, _, _, l)| !l.is_empty()).map(|(sim, _, _, l)| json!({"sim": sim, "lines": l})).collect::<Vec<_>>(),
    });
    let text = serde_json::to_string_pretty(&out).unwrap();
    match arg(&args, "--out") {
        Some(p) => std::fs::write(p, text).unwrap(),
        None => println!("{}", text),
    }
}
