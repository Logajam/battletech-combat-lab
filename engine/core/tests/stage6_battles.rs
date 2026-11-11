//! Stage 6: whole battles, bots off. Each fixture battle is played by the Rust engine from units.json + dice.json with
//! the bots' answers read back from decisions.json; its state after every phase (trace.jsonl), its dice used and its log
//! (log.txt) must be the Python's, exactly. FIXTURES=a,b limits the run; first difference is reported.
//! Needs `python tools/port_fixtures.py` (engine/fixtures).
use std::fs;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;

use btsim_core::battle::{Battle, Replay, TapeDice};
use btsim_core::board_parser::Board;
use btsim_core::config::Config;
use btsim_core::mech_state::Mech;
use btsim_core::orchestrator::{play_on, start_battle};
use btsim_core::replay_bots::ReplayBots;
use serde_json::Value;

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
            for k in y.keys() {
                if !x.contains_key(k) {
                    return Some(format!("{}/{}: Python has it, Rust not", path, k));
                }
            }
            None
        }
        (Value::Array(x), Value::Array(y)) => {
            for (i, (v, w)) in x.iter().zip(y).enumerate() {
                if let Some(d) = first_diff(v, w, &format!("{}[{}]", path, i)) {
                    return Some(d);
                }
            }
            if x.len() != y.len() {
                return Some(format!("{} length {} v {}", path, x.len(), y.len()));
            }
            None
        }
        _ if a == b => None,
        _ => Some(format!("{}: rust {} python {}", path, a.to_string().chars().take(100).collect::<String>(), b.to_string().chars().take(100).collect::<String>())),
    }
}

fn read_json(p: &PathBuf) -> Value {
    serde_json::from_str(&fs::read_to_string(p).unwrap_or_else(|_| panic!("{} missing", p.display()))).unwrap()
}

/// The battle's own lines of log.txt: from after the SIMULATION header to the batch summary.
fn expected_log(dir: &PathBuf) -> (Vec<String>, Vec<String>) {
    let text = fs::read_to_string(dir.join("log.txt")).unwrap();
    let (out_part, err_part) = text.split_once("\n# stderr (stub warnings)\n").unwrap_or((text.as_str(), ""));
    let out_part = out_part.strip_prefix("# stdout\n").unwrap_or(out_part);
    let stderr: Vec<String> = err_part.lines().map(|s| s.to_string()).collect();
    let lines: Vec<&str> = out_part.split('\n').collect();
    let sim = lines.iter().position(|l| l.contains("=== SIMULATION 1/1 ===")).expect("simulation header");
    // the attach step's own lines (triple-strength myomer notes...) come first: the units here start attached
    let battle_start = lines[sim + 1..].iter().position(|l| l.starts_with("  Deployment:") || *l == "=== TURN 1 ===").expect("battle start") + sim + 1;
    let start = if lines[battle_start] == "=== TURN 1 ===" { battle_start - 2 } else { battle_start - 1 };
    let end = lines.iter().position(|l| l.starts_with("!!!!!!") || l.starts_with("######")).unwrap_or(lines.len());
    // the summary block is preceded by a blank line
    let mut body: Vec<String> = lines[start + 1..end].iter().map(|s| s.to_string()).collect();
    while body.last().map_or(false, |l| l.is_empty()) {
        body.pop();
    }
    (body, stderr)
}

/// Smoke that clears in one End Phase prints in hash order in Python (INTEGRATION__RUST_PORT.md "Found on the way" 1):
/// compare each run of those lines sorted.
fn normalize(lines: Vec<String>) -> Vec<String> {
    let is_clear = |l: &str| l.starts_with("  [End] The smoke at ") && l.ends_with(" clears.");
    let mut out: Vec<String> = Vec::new();
    let mut i = 0;
    while i < lines.len() {
        if is_clear(&lines[i]) {
            let mut j = i;
            while j < lines.len() && is_clear(&lines[j]) {
                j += 1;
            }
            let mut run = lines[i..j].to_vec();
            run.sort();
            out.extend(run);
            i = j;
        } else {
            out.push(lines[i].clone());
            i += 1;
        }
    }
    out
}

fn run_fixture(dir: PathBuf) -> Result<usize, String> {
    let name = dir.file_name().unwrap().to_string_lossy().to_string();
    let over = read_json(&dir.join("overrides.json"));
    let max_turns = over["max_turns"].as_i64().unwrap();
    let cfg = Config::from_json(&read_json(&dir.join("config.json")));
    let board = Board::from_json(&read_json(&dir.join("board.json")));
    let units_json = read_json(&dir.join("units.json"));
    let names: Vec<String> = units_json.as_object().unwrap().keys().cloned().collect();
    let idx = |n: &str| names.iter().position(|x| x == n).unwrap();
    let units: Vec<Mech> = names.iter().map(|n| Mech::from_json(&units_json[n], &idx)).collect();
    let dice = TapeDice::from_json(&read_json(&dir.join("dice.json")));
    let mut b = Battle::new(cfg, board, units, Box::new(dice));
    let own_bots = std::env::var("BOTS").map_or(false, |v| v == "rust");
    if own_bots {
        // the Rust Gladiator plays alone: duels between Gladiators only (the rest is not translated yet)
        let duel_of_gladiators = b.units.iter().all(|u| u.bot == "gladiator");
        if !duel_of_gladiators {
            return Ok(0);
        }
    } else {
        b.replay = Some(Replay { records: read_json(&dir.join("decisions.json")).as_array().unwrap().clone(), cursor: 0 });
    }

    let trace: Vec<Value> = BufReader::new(fs::File::open(dir.join("trace.jsonl")).unwrap()).lines().map(|l| serde_json::from_str(&l.unwrap()).unwrap()).collect();
    let seen_c = std::cell::Cell::new(0usize);
    let failure_c: std::cell::RefCell<Option<String>> = std::cell::RefCell::new(None);
    let checked_c: std::cell::RefCell<(std::collections::BTreeMap<String, (usize, usize)>, Vec<String>)> = Default::default();
    let nms = names.clone();
    {
        let mut marks = |b: &mut Battle, turn: i64, phase: &str| {
            if failure_c.borrow().is_some() {
                return;
            }
            let want = &trace[seen_c.get()];
            seen_c.set(seen_c.get() + 1);
            let seen = seen_c.get();
            let mut failure = |m: String| *failure_c.borrow_mut() = Some(m);
            let name_of = |i: usize| nms[i].clone();
            if want["turn"].as_i64().unwrap() != turn || want["phase"].as_str().unwrap() != phase {
                failure(format!("mark {}: turn {} {:?} v trace turn {} {:?}", seen, turn, phase, want["turn"], want["phase"]));
                return;
            }
            if want["dice_used"].as_u64().unwrap() as usize != b.dice.used() {
                failure(format!("after {} turn {}: dice used {} v {}", phase, turn, b.dice.used(), want["dice_used"]));
                return;
            }
            for (i, n) in nms.iter().enumerate() {
                let got = b.units[i].to_json(&name_of);
                let mut w = want["units"][n].clone();
                w.as_object_mut().unwrap().remove("_bv_built"); // the bots' battle-value cache (stage 7)
                // the bots' scratch attribute: the Python's movement scoring leaves `blocked_hex` = None on units it modeled
                if w.get("blocked_hex") == Some(&Value::Null) && got.get("blocked_hex").is_none() {
                    w.as_object_mut().unwrap().remove("blocked_hex");
                }
                if let Some(d) = first_diff(&got, &w, "") {
                    failure(format!("after {} turn {} (unit {}): {}", phase, turn, n, d));
                    return;
                }
            }
        };
        let mut play = start_battle(&mut b, max_turns, &mut marks);
        if failure_c.borrow().is_none() {
            let check = std::env::var("CHECK").unwrap_or_default();
            let mut gbots = btsim_core::gladiator_bots::GladiatorBots;
            let mut bots = ReplayBots { check_gladiator_declaration: check.contains("declaration"), check_gladiator_physical: check.contains("physical"), check_simple_foe_target: check.contains("simple"), check_gladiator_move: check.contains("move"), check_legate: check.contains("legate"), ..Default::default() };
            if own_bots {
                play_on(&mut b, &mut gbots, &mut play, &mut marks);
            } else {
                play_on(&mut b, &mut bots, &mut play, &mut marks);
            }
            checked_c.replace((bots.checked.clone(), bots.mismatches.clone()));
        }
    }
    let failure = failure_c.into_inner();
    let (checked, mismatches) = checked_c.into_inner();
    if !checked.is_empty() {
        eprintln!("{} checked (decisions, wrong): {:?}", name, checked);
    }
    if !mismatches.is_empty() {
        return Err(format!("{}: {} decision(s) differ; first: {}", name, mismatches.len(), mismatches[0]));
    }
    let seen = seen_c.get();
    let (want_log, want_err) = expected_log(&dir);
    let want_log = normalize(want_log);
    let got_log: Vec<String> = normalize(b.log.lines.join("\n").split('\n').map(|s| s.to_string()).collect());
    // smoke-clearing lines of one turn print in hash order in Python: compare them sorted
    if let Some(f) = failure {
        // show the first log difference as well: it usually names the cause
        let d = got_log.iter().zip(&want_log).position(|(a, b2)| a != b2);
        return Err(format!("{}: {}\n  first log difference: {:?}", name, f, d.map(|i| (i, got_log[i].clone(), want_log[i].clone()))));
    }
    if seen != trace.len() {
        return Err(format!("{}: {} marks played, the trace has {}", name, seen, trace.len()));
    }
    // movement notes print scores to 2-3 places: a 1-ulp float difference (Daniel, 2026-11-10: not worth chasing) can tip
    // the last digit, so those lines agree when their numbers are within one unit of the last place printed
    let same_line = |a: &String, b2: &String| a == b2 || (a.contains("[Movement select]") && btsim_core::replay_bots::notes_agree(a, b2));
    if let Some(i) = got_log.iter().zip(&want_log).position(|(a, b2)| !same_line(a, b2)) {
        return Err(format!("{}: log line {}:\n  rust:   {}\n  python: {}", name, i + 1, got_log[i], want_log[i]));
    }
    if got_log.len() != want_log.len() {
        return Err(format!("{}: log has {} lines, Python's {}", name, got_log.len(), want_log.len()));
    }
    let got_err: Vec<String> = b.log.stderr.clone();
    let want_err: Vec<String> = want_err.into_iter().filter(|l| !l.is_empty()).collect();
    // the attach step's stub warnings (capacitor start, ...) come first in Python: the units here start attached
    if !want_err.ends_with(&got_err) {
        return Err(format!("{}: stub warnings differ: rust {} lines, python {}", name, got_err.len(), want_err.len()));
    }
    Ok(trace.len())
}

#[test]
fn battles_replay_exactly() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../fixtures");
    let only: Option<Vec<String>> = std::env::var("FIXTURES").ok().map(|s| s.split(',').map(|x| x.to_string()).collect());
    let mut dirs: Vec<PathBuf> = fs::read_dir(&root)
        .unwrap()
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.join("decisions.json").exists())
        .filter(|p| only.as_ref().map_or(true, |o| o.contains(&p.file_name().unwrap().to_string_lossy().to_string())))
        .collect();
    dirs.sort();
    let mut failures = Vec::new();
    let mut ok = 0;
    for d in dirs {
        let r = std::panic::catch_unwind(|| run_fixture(d.clone()));
        match r {
            Ok(Ok(n)) => {
                ok += 1;
                eprintln!("ok  {} ({} marks)", d.file_name().unwrap().to_string_lossy(), n);
            }
            Ok(Err(e)) => failures.push(e),
            Err(p) => failures.push(format!("{}: PANIC {}", d.file_name().unwrap().to_string_lossy(), p.downcast_ref::<String>().cloned().or_else(|| p.downcast_ref::<&str>().map(|s| s.to_string())).unwrap_or_default())),
        }
    }
    for f in &failures {
        eprintln!("FAIL {}", f);
    }
    assert!(failures.is_empty(), "{} fixtures differ ({} ok)", failures.len(), ok);
}
