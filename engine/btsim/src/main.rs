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
        eprintln!("usage: btsim SCENARIO_DIR [--battles N] [--seed S] [--threads T] [--log N] [--out FILE] [--hydra TEAM[,TEAM]] [--set KEY=VALUE ...] [--ledger FILE] [--max-turns N] [--sims I,J,...] [--stream FILE]");
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
    // --max-turns N (session 25): the turn cap for this run, in place of the scenario's (scenario::STANDARD_MAX_TURNS, 100). A
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
    // --sims I,J,... (session 25): play only these battle numbers of the 1..=N set (each on its own seed, as in the full
    // set), e.g. the undecided ones of an earlier run, replayed with a higher --max-turns.
    let only: Option<Vec<u64>> = arg(&args, "--sims").map(|v| v.split(',').map(|x| x.parse().expect("--sims")).collect());
    // --stream FILE (session 25; Daniel, 2026-11-12: "the results of each run is recorded when its done. This lets you
    // quickly find crashes, and easily restart a set"): every battle is appended to FILE as one JSON line the moment it
    // ends - its result, or {"sim", "seed", "crashed": message} if the engine panicked (the set goes on). Battles
    // already in FILE are not played again: re-running the same command after a stop finishes only what is missing,
    // and the summary counts the earlier lines too.
    let stream = arg(&args, "--stream");
    let mut done: std::collections::BTreeMap<u64, Value> = std::collections::BTreeMap::new();
    if let Some(path) = &stream {
        if let Ok(text) = std::fs::read_to_string(path) {
            for line in text.lines().filter(|l| !l.trim().is_empty()) {
                // a line cut short by a stop is ignored (that battle is played again)
                if let Ok(v) = serde_json::from_str::<Value>(line) {
                    if let Some(sim) = v["sim"].as_u64() {
                        done.insert(sim, v);
                    }
                }
            }
        }
    }
    let writer = stream.as_ref().map(|p| std::sync::Mutex::new(std::fs::OpenOptions::new().create(true).append(true).open(p).expect("--stream FILE")));
    let sims: Vec<u64> = (1..=battles).filter(|s| only.as_ref().map_or(true, |o| o.contains(s))).filter(|s| !done.contains_key(s)).collect();
    let runs: Vec<(u64, Value, Vec<String>)> = sims
        .into_par_iter()
        .map(|sim| {
            let s = PcgDice::battle_seed(seed, sim);
            // a panic in one battle is that battle's result, not the end of the set
            let played = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| scenario.run(s, sim <= log_first)));
            let (v, log) = match played {
                Ok((r, log)) => (battle_json(sim, s, &r), log),
                Err(e) => {
                    let msg = e.downcast_ref::<String>().cloned().or_else(|| e.downcast_ref::<&str>().map(|m| m.to_string())).unwrap_or_else(|| "panic".into());
                    (json!({"sim": sim, "seed": s, "crashed": msg}), Vec::new())
                }
            };
            if let Some(w) = &writer {
                use std::io::Write;
                let mut f = w.lock().unwrap();
                writeln!(f, "{}", serde_json::to_string(&v).unwrap()).unwrap();
                f.flush().unwrap();
            }
            (sim, v, log)
        })
        .collect();
    let secs = started.elapsed().as_secs_f64();
    // every battle of the set: the earlier stream lines and the ones just played, in battle order
    let mut all: std::collections::BTreeMap<u64, Value> = done.into_iter().filter(|(sim, _)| only.as_ref().map_or(*sim <= battles, |o| o.contains(sim))).collect();
    for (sim, v, _) in &runs {
        all.insert(*sim, v.clone());
    }
    let (results, crashed): (Vec<Value>, Vec<Value>) = all.into_values().partition(|v| v.get("crashed").is_none());
    let mut wins: serde_json::Map<String, Value> = serde_json::Map::new();
    let (mut turns, mut capped) = (0i64, 0u64);
    for r in &results {
        let w = r["winner"].as_str().unwrap_or("Draw").to_string();
        let n = wins.get(&w).and_then(|v| v.as_u64()).unwrap_or(0);
        wins.insert(w, json!(n + 1));
        let t = r["turns"].as_i64().unwrap_or(0);
        turns += t;
        if t >= scenario.max_turns {
            capped += 1;
        }
    }
    for c in &crashed {
        eprintln!("btsim: battle {} (seed {}) CRASHED: {}", c["sim"], c["seed"], c["crashed"].as_str().unwrap_or(""));
    }
    let out = json!({
        "battles": battles,
        "seed": seed,
        "seconds": secs,
        "wins": wins,
        "mean_turns": turns as f64 / results.len().max(1) as f64,
        "hit_turn_cap": capped,
        "max_turns": scenario.max_turns,
        "crashed": crashed,
        "results": results,
        "logs": runs.iter().filter(|(_, _, l)| !l.is_empty()).map(|(sim, _, l)| json!({"sim": sim, "lines": l})).collect::<Vec<_>>(),
    });
    let text = serde_json::to_string_pretty(&out).unwrap();
    match arg(&args, "--out") {
        Some(p) => std::fs::write(p, text).unwrap(),
        None => println!("{}", text),
    }
}
