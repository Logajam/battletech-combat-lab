//! btsim SCENARIO_DIR [--battles N] [--seed S] [--threads T] [--log N] [--out FILE] [--hydra TEAM[,TEAM]] [--history N]
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

/// `btsim decide` (MegaMek bridge, INTEGRATION__MEGAMEK_BRIDGE.md): the decision process. Reads JSON lines on stdin -
/// `{"ping": true}` at any time is answered `{"pong": true, "started": ...}`; otherwise the first is the game's start (`bridge::Session::start`), each later one a call {"method", "args", "state"} - and
/// writes one JSON line per call on stdout: {"answer": ...}, or {"error": message} when the call could not be made (the
/// caller then lets its own bot decide). Stays alive until stdin closes, so the bots' memories carry through the game.
fn decide() {
    use std::io::{BufRead, Write};
    let stdin = std::io::stdin();
    let mut out = std::io::stdout();
    let mut session: Option<btsim_core::bridge::Session> = None;
    for line in stdin.lock().lines() {
        let line = line.expect("stdin");
        if line.trim().is_empty() {
            continue;
        }
        let reply = match serde_json::from_str::<Value>(&line) {
            Err(e) => json!({"error": format!("not JSON: {}", e)}),
            // {"ping": true} (any time): the process is alive; the Java side checks this when it starts
            Ok(v) if v.get("ping").is_some() => json!({"pong": true, "started": session.is_some()}),
            Ok(v) => match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| match session.as_mut() {
                None => {
                    session = Some(btsim_core::bridge::Session::start(&v));
                    json!({"started": true})
                }
                Some(s) => json!({"answer": s.handle(&v)}),
            })) {
                Ok(r) => r,
                Err(e) => json!({"error": e.downcast_ref::<String>().cloned().or_else(|| e.downcast_ref::<&str>().map(|m| m.to_string())).unwrap_or_else(|| "panic".into())}),
            },
        };
        writeln!(out, "{}", reply).unwrap();
        out.flush().unwrap();
    }
}

/// Writes one battle's history: its replay page, or the bare JSON record (`json`).
fn write_history(dir: &std::path::Path, record: &Value, json: bool) {
    let name = btsim_core::history::file_name(record);
    if json {
        std::fs::write(dir.join(name.replace(".html", ".json")), serde_json::to_string(record).unwrap()).unwrap();
    } else {
        std::fs::write(dir.join(name), btsim_core::history::page(record)).unwrap();
    }
}

/// A history's log, every step's lines in order (what --log keeps).
fn lines_of(record: &Value) -> Vec<String> {
    record["steps"].as_array().into_iter().flatten().flat_map(|s| s["log"].as_array().into_iter().flatten().filter_map(|l| l.as_str().map(String::from))).collect()
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.first().map(|a| a.as_str()) == Some("decide") {
        decide();
        return;
    }
    // --setup FILE (Combat Lab CL1, session 25): the scenario is built in Rust from a settings file (the settings that
    // differ from engine/defaults/config.json, under the Python's names: FORCES, DEFAULT_BOARD_PATH...) in place of a
    // scenario folder. The repository root (for the defaults and data/) is BTSIM_ROOT, else three folders above this
    // binary (engine/target/release/btsim). --write-scenario DIR also saves the built scenario as a folder.
    let setup = arg(&args, "--setup");
    let dir_arg = args.first().filter(|a| !a.starts_with("--")).cloned().or_else(|| setup.as_ref().map(|_| String::new()));
    let Some(dir) = dir_arg.as_ref() else {
        eprintln!("usage: btsim (SCENARIO_DIR | --setup SETTINGS.json [--write-scenario DIR]) [--battles N] [--seed S] [--threads T] [--log N] [--out FILE] [--hydra TEAM[,TEAM]] [--set KEY=VALUE ...] [--ledger FILE] [--max-turns N] [--sims I,J,...] [--stream FILE] [--history N [--history-dir DIR] [--history-json]]");
        std::process::exit(2);
    };
    let battles: u64 = arg(&args, "--battles").map_or(1, |v| v.parse().expect("--battles"));
    let seed: u64 = arg(&args, "--seed").map_or(1, |v| v.parse().expect("--seed"));
    let log_first: u64 = arg(&args, "--log").map_or(0, |v| v.parse().expect("--log"));
    if let Some(t) = arg(&args, "--threads") {
        rayon::ThreadPoolBuilder::new().num_threads(t.parse().expect("--threads")).build_global().unwrap();
    }
    let mut scenario = match &setup {
        None => Scenario::load(&PathBuf::from(dir)),
        Some(file) => {
            let settings: Value = serde_json::from_str(&std::fs::read_to_string(file).unwrap_or_else(|e| panic!("{}: {}", file, e))).unwrap_or_else(|e| panic!("{}: {}", file, e));
            let s = Scenario::from_settings(&settings, &btsim_core::scenario::SetupPaths::find()).unwrap_or_else(|e| {
                eprintln!("btsim: {}", e);
                std::process::exit(2)
            });
            if let Some(out) = arg(&args, "--write-scenario") {
                std::fs::create_dir_all(&out).unwrap();
                for (name, v) in [("config.json", &s.config), ("units.json", &s.units), ("board.json", &s.board)] {
                    std::fs::write(PathBuf::from(&out).join(name), serde_json::to_string_pretty(v).unwrap()).unwrap();
                }
                std::fs::write(PathBuf::from(&out).join("meta.json"), "{}").unwrap();
            }
            s
        }
    };
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
    // --bridge-parity (MegaMek bridge B1): each battle is played with its bots' calls recorded, then a fresh decision
    // process (`btsim decide`'s Session) is fed the recording and must give the same answer to every decision. One JSON
    // line per battle; exit code 1 if any battle differed. --bridge-dump FILE also writes battle 1's recording.
    if args.iter().any(|a| a == "--bridge-parity") {
        // --bridge-compact (B3): the units go as compact states (bridge::UNIT_FIELDS / ITEM_FIELDS), not whole dumps
        let compact = args.iter().any(|a| a == "--bridge-compact");
        // --bridge-view: the units go as MegaMek VIEWS (what a MegaMek game tells our engine); every answer is compared and
        // the agreement counted per decision kind ("agree"), instead of stopping at the first difference
        let view = args.iter().any(|a| a == "--bridge-view");
        let runs: Vec<Value> = (1..=battles)
            .into_par_iter()
            .map(|sim| {
                let s = PcgDice::battle_seed(seed, sim);
                let keep = sim == 1 && arg(&args, "--bridge-dump").is_some();
                let (r, p, lines) = scenario.run_bridge_checked(s, keep, compact, view);
                if keep {
                    if let Some(p) = arg(&args, "--bridge-dump") {
                        let start = scenario.bridge_start(s);
                        let mut text = format!("{}\n", start);
                        for l in &lines {
                            text.push_str(&format!("{}\n", l));
                        }
                        std::fs::write(p, text).unwrap();
                    }
                }
                json!({"sim": sim, "seed": s, "turns": r.turns_taken, "winner": r.winner, "calls": p.calls, "decisions": p.decisions,
                       "same": p.first_difference.is_none(), "rebuild_gaps": p.rebuild_gaps, "agree": p.agree,
                       "first_difference": p.first_difference.map(|(n, m, want, got)| json!({"line": n, "method": m, "battle": want, "session": got}))})
            })
            .collect();
        let bad = runs.iter().filter(|r| !r["same"].as_bool().unwrap()).count();
        for r in &runs {
            println!("{}", r);
        }
        eprintln!("bridge parity: {} of {} battles the same", runs.len() - bad, runs.len());
        std::process::exit(if bad == 0 { 0 } else { 1 });
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
    // --history N [--history-dir DIR] [--history-json] (Combat Lab CL2): battles 1..N of the set also write their full
    // history (btsim_core::history), each as a replay page (INTEGRATION__replay_viewer.html with the battle inside;
    // opens in any browser) in DIR (default "replays"), or as the bare JSON record with --history-json. The battles
    // are the same as without it: recording only reads.
    let history_first: u64 = arg(&args, "--history").map_or(0, |v| v.parse().expect("--history"));
    let history_dir = PathBuf::from(arg(&args, "--history-dir").unwrap_or_else(|| "replays".into()));
    let history_json = args.iter().any(|a| a == "--history-json");
    if history_first > 0 {
        std::fs::create_dir_all(&history_dir).expect("--history-dir");
    }
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
            // --history N: battles 1..N also write their full history as a replay page (Combat Lab CL2)
            let played = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                if sim <= history_first {
                    let (r, record) = scenario.run_history(sim, s);
                    write_history(&history_dir, &record, history_json);
                    let log = if sim <= log_first { lines_of(&record) } else { vec![] };
                    (r, log)
                } else {
                    scenario.run(s, sim <= log_first)
                }
            }));
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
