//! COMBAT LAB CL2: the Rust engine's battle history (`btsim_core::history`) of a fixture battle equals the Python's
//! replay record of the same battle (`replay.json`, written by `python tools/port_record.py --replay-data FIXTURE`),
//! step for step: the units' state, the log lines of each step, the header, the board and the result. Fixtures with no
//! replay.json are skipped (engine/fixtures is git-ignored and rebuilt by tools/port_fixtures.py; run --replay-data on
//! the ones to check). FIXTURES=a,b limits the run.
use std::fs;
use std::path::PathBuf;

use btsim_core::battle::{Battle, Replay, TapeDice};
use btsim_core::board_parser::Board;
use btsim_core::config::Config;
use btsim_core::history::History;
use btsim_core::mech_state::Mech;
use btsim_core::orchestrator::{play_on, start_battle};
use btsim_core::replay_bots::ReplayBots;
use serde_json::Value;

fn read_json(p: &PathBuf) -> Value {
    serde_json::from_str(&fs::read_to_string(p).unwrap_or_else(|_| panic!("{} missing", p.display()))).unwrap()
}

/// The first place two records differ, as a path, or None. Numbers compare as numbers (the Python writes 5.0 where the
/// Rust may write 5 for a whole float, and the other way round).
fn first_diff(a: &Value, b: &Value, path: &str) -> Option<String> {
    match (a, b) {
        (Value::Object(x), Value::Object(y)) => {
            for (k, v) in x {
                match y.get(k) {
                    None => return Some(format!("{}/{}: Rust has it, Python not", path, k)),
                    Some(w) => {
                        if let Some(d) = first_diff(v, w, &format!("{}/{}", path, k)) {
                            return Some(d);
                        }
                    }
                }
            }
            y.keys().find(|k| !x.contains_key(*k)).map(|k| format!("{}/{}: Python has it, Rust not", path, k))
        }
        (Value::Array(x), Value::Array(y)) => {
            for (i, (v, w)) in x.iter().zip(y).enumerate() {
                if let Some(d) = first_diff(v, w, &format!("{}[{}]", path, i)) {
                    return Some(d);
                }
            }
            (x.len() != y.len()).then(|| format!("{} length {} v {}", path, x.len(), y.len()))
        }
        (Value::Number(x), Value::Number(y)) if x.as_f64() == y.as_f64() => None,
        _ if a == b => None,
        _ => Some(format!("{}: rust {} python {}", path, a, b)),
    }
}

/// Smoke that clears in one End Phase prints in hash order in the Python (INTEGRATION__RUST_PORT.md "Found on the way"
/// 1; stage6_battles.rs does the same): each step's runs of those lines are compared sorted.
fn normalize(record: &mut Value) {
    let is_clear = |l: &Value| l.as_str().is_some_and(|l| l.starts_with("  [End] The smoke at ") && l.ends_with(" clears."));
    for step in record["steps"].as_array_mut().into_iter().flatten() {
        let lines = step["log"].as_array_mut().unwrap();
        let mut i = 0;
        while i < lines.len() {
            let j = (i..lines.len()).find(|&j| !is_clear(&lines[j])).unwrap_or(lines.len());
            lines[i..j].sort_by(|a, b| a.as_str().cmp(&b.as_str()));
            i = j.max(i + 1);
        }
    }
}

/// One fixture: its battle played from units.json + dice.json with the bots' answers read back (as stage 6), recorded.
fn history_of(dir: &PathBuf, sim: u64, seed: u64) -> Value {
    let over = read_json(&dir.join("overrides.json"));
    let max_turns = over["max_turns"].as_i64().unwrap();
    // the frozen Python answer key fires a unit's weapons in its own order (attack_resolution::finish_declaration)
    let mut cfg = Config::from_json(&read_json(&dir.join("config.json")));
    cfg.set("_FIRE_ORDER_LISTED", serde_json::Value::Bool(true));
    let board = Board::from_json(&read_json(&dir.join("board.json")));
    let units_json = read_json(&dir.join("units.json"));
    let names: Vec<String> = units_json.as_object().unwrap().keys().cloned().collect();
    let idx = |n: &str| names.iter().position(|x| x == n).unwrap();
    let units: Vec<Mech> = names.iter().map(|n| Mech::from_json(&units_json[n], &idx)).collect();
    let mut b = Battle::new(cfg, board, units, Box::new(TapeDice::from_json(&read_json(&dir.join("dice.json")))));
    b.replay = Some(Replay { records: read_json(&dir.join("decisions.json")).as_array().unwrap().clone(), cursor: 0 });
    let mut history = History::new(sim, seed);
    let mut marks = |b: &mut Battle, turn: i64, phase: &str| history.mark(b, turn, phase);
    let mut play = start_battle(&mut b, max_turns, &mut marks);
    let mut bots = ReplayBots::default();
    play_on(&mut b, &mut bots, &mut play, &mut marks);
    history.finish(&b, &play.result)
}

#[test]
fn rust_history_equals_python_replay() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("fixtures");
    let only: Option<Vec<String>> = std::env::var("FIXTURES").ok().map(|v| v.split(',').map(String::from).collect());
    let mut dirs: Vec<PathBuf> = fs::read_dir(&root).map(|r| r.filter_map(|e| e.ok()).map(|e| e.path()).collect()).unwrap_or_default();
    dirs.sort();
    let mut checked = 0;
    let mut failures = Vec::new();
    for dir in dirs {
        let name = dir.file_name().unwrap().to_string_lossy().to_string();
        if !dir.join("replay.json").exists() || only.as_ref().is_some_and(|o| !o.contains(&name)) {
            continue;
        }
        let mut want = read_json(&dir.join("replay.json"));
        let seed: u64 = want["seed"].as_str().and_then(|s| s.parse().ok()).unwrap_or(0);
        let mut got = history_of(&dir, want["sim"].as_u64().unwrap(), seed);
        normalize(&mut want);
        normalize(&mut got);
        if let Some(d) = first_diff(&got, &want, "") {
            failures.push(format!("{}: {}", name, d));
        }
        checked += 1;
    }
    eprintln!("CL2 history: {} fixture(s) checked", checked);
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}
