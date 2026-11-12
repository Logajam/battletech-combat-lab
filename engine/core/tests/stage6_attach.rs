//! The attach step (`_attach_mech_config`): each fixture's units are parsed from their .mtf, given their settings and
//! equipment links, and must equal units.json - with the log lines and stub warnings the attaching printed.
use std::fs;
use std::path::PathBuf;

use btsim_core::battle::{Battle, TapeDice};
use btsim_core::board_parser::Board;
use btsim_core::config::Config;
use btsim_core::equipment::EquipmentDb;
use btsim_core::mech_state::Mech;
use btsim_core::mtf_parser::parse_mtf;
use btsim_core::setup::{attach_mech_config, roster};
use serde_json::Value;

fn read_json(p: &PathBuf) -> Value {
    serde_json::from_str(&fs::read_to_string(p).unwrap()).unwrap()
}

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

fn run_fixture(dir: &PathBuf) -> Result<(), String> {
    let name = dir.file_name().unwrap().to_string_lossy().to_string();
    let cfg = Config::from_json(&read_json(&dir.join("config.json")));
    let board = Board::from_json(&read_json(&dir.join("board.json")));
    let units_json = read_json(&dir.join("units.json"));
    let data = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../data");
    let db = EquipmentDb::load();
    let entries = roster(&cfg);
    let mut mechs: Vec<Mech> = Vec::new();
    for (mtf, _, _) in &entries {
        let path = data.join(mtf);
        let text = fs::read_to_string(&path).map_err(|e| format!("{}: {} ({})", name, e, path.display()))?;
        let mut out = String::new();
        mechs.push(parse_mtf(&db, &text, &mut out).map_err(|e| format!("{}: {}", name, e))?);
    }
    let mut b = Battle::new(cfg, board, mechs, Box::new(TapeDice::new(vec![])));
    for (u, (_, label, setup)) in entries.iter().enumerate() {
        attach_mech_config(&mut b, u, setup, label);
    }
    for u in 0..b.units.len() {
        b.units[u].assign_addresses();
    }
    let names: Vec<String> = entries.iter().map(|e| e.1.clone()).collect();
    let name_of = |i: usize| names[i].clone();
    for (i, n) in names.iter().enumerate() {
        let got = b.units[i].to_json(&name_of);
        if let Some(d) = first_diff(&got, &units_json[n], "") {
            return Err(format!("{}: unit {}: {}", name, n, d));
        }
    }
    // the attach step's own log lines and stub warnings lead the battle's in the Python's log
    let text = fs::read_to_string(dir.join("log.txt")).unwrap();
    let (out_part, err_part) = text.split_once("\n# stderr (stub warnings)\n").unwrap_or((text.as_str(), ""));
    let lines: Vec<&str> = out_part.split('\n').collect();
    let sim = lines.iter().position(|l| l.contains("=== SIMULATION 1/1 ===")).unwrap();
    let battle_start = lines[sim + 1..].iter().position(|l| l.starts_with("  Deployment:") || *l == "=== TURN 1 ===").unwrap() + sim + 1;
    let first_battle_line = if lines[battle_start] == "=== TURN 1 ===" { battle_start - 1 } else { battle_start };
    let want: Vec<&str> = lines[sim + 2..first_battle_line].iter().copied().filter(|l| !l.starts_with("=====") && !l.is_empty()).collect();
    let got: Vec<String> = b.log.lines.clone();
    if want.iter().map(|s| s.to_string()).collect::<Vec<_>>() != got {
        return Err(format!("{}: attach log differs: rust {:?} python {:?}", name, got, want));
    }
    let want_err: Vec<String> = err_part.lines().take(b.log.stderr.len()).map(|s| s.to_string()).collect();
    if want_err != b.log.stderr {
        return Err(format!("{}: attach stub warnings differ: rust {:?} python {:?}", name, b.log.stderr, want_err));
    }
    Ok(())
}

#[test]
fn units_attach_exactly() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../fixtures");
    let mut dirs: Vec<PathBuf> = fs::read_dir(&root).unwrap().filter_map(|e| e.ok()).map(|e| e.path()).filter(|p| p.join("units.json").exists() && p.join("config.json").exists() && p.join("decisions.json").exists()).collect();
    dirs.sort();
    let mut failures = Vec::new();
    for d in &dirs {
        match std::panic::catch_unwind(|| run_fixture(d)) {
            Ok(Ok(())) => {}
            Ok(Err(e)) => failures.push(e),
            Err(p) => failures.push(format!("{}: PANIC {}", d.display(), p.downcast_ref::<String>().cloned().or_else(|| p.downcast_ref::<&str>().map(|s| s.to_string())).unwrap_or_default())),
        }
    }
    for f in &failures {
        eprintln!("FAIL {}", f);
    }
    assert!(failures.is_empty(), "{} of {} fixtures differ", failures.len(), dirs.len());
}
