//! COMBAT LAB CL1 (INTEGRATION__COMBAT_LAB_SPECS.md): a scenario built by Rust from settings alone must equal the one
//! the Python built. For every fixture, the settings that differ from engine/defaults/config.json are handed to
//! `Scenario::from_settings`; its units and board must equal the fixture's units.json and board.json exactly.
use std::fs;
use std::path::PathBuf;

use btsim_core::scenario::{Scenario, SetupPaths};
use serde_json::Value;

fn read_json(p: &PathBuf) -> Value {
    serde_json::from_str(&fs::read_to_string(p).unwrap()).unwrap()
}

/// The first place two JSON values differ, as a path.
fn first_diff(a: &Value, b: &Value, path: &str) -> Option<String> {
    match (a, b) {
        (Value::Object(x), Value::Object(y)) => {
            // fields are read by name, so their order inside an object does not matter (the roster's order does, and is
            // checked on its own below)
            if let Some(k) = x.keys().find(|k| !y.contains_key(*k)).or_else(|| y.keys().find(|k| !x.contains_key(*k))) {
                return Some(format!("{}/{}: in one and not the other", path, k));
            }
            x.iter().find_map(|(k, v)| first_diff(v, &y[k], &format!("{}/{}", path, k)))
        }
        (Value::Array(x), Value::Array(y)) if x.len() == y.len() => x.iter().zip(y).enumerate().find_map(|(i, (v, w))| first_diff(v, w, &format!("{}[{}]", path, i))),
        _ if a == b => None,
        _ => Some(format!("{}: rust {} python {}", path, a.to_string().chars().take(120).collect::<String>(), b.to_string().chars().take(120).collect::<String>())),
    }
}

#[test]
fn scenarios_built_from_settings_equal_the_python_ones() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().unwrap();
    let paths = SetupPaths::at(&root);
    let defaults = read_json(&paths.defaults);
    let fixtures = root.join("engine").join("fixtures");
    let mut dirs: Vec<PathBuf> = fs::read_dir(&fixtures).unwrap().filter_map(|e| e.ok()).map(|e| e.path()).filter(|p| p.join("units.json").exists() && p.join("config.json").exists()).collect();
    dirs.sort();
    let mut failures = Vec::new();
    for d in &dirs {
        let name = d.file_name().unwrap().to_string_lossy().to_string();
        let cfg = read_json(&d.join("config.json"));
        let mut settings = serde_json::Map::new();
        for (k, v) in cfg.as_object().unwrap() {
            if k != "_ACTIVE_RNG" && defaults.get(k) != Some(v) {
                settings.insert(k.clone(), v.clone());
            }
        }
        let built = match std::panic::catch_unwind(|| Scenario::from_settings(&Value::Object(settings.clone()), &paths)) {
            Ok(Ok(s)) => s,
            Ok(Err(e)) => {
                failures.push(format!("{}: {}", name, e));
                continue;
            }
            Err(_) => {
                failures.push(format!("{}: PANIC", name));
                continue;
            }
        };
        let want = read_json(&d.join("units.json"));
        let (rk, pk): (Vec<&String>, Vec<&String>) = (built.units.as_object().unwrap().keys().collect(), want.as_object().unwrap().keys().collect());
        if rk != pk {
            failures.push(format!("{}: roster order: rust {:?} python {:?}", name, rk, pk));
        } else if let Some(diff) = first_diff(&built.units, &want, "units") {
            failures.push(format!("{}: {}", name, diff));
        } else if let Some(diff) = first_diff(&built.board, &read_json(&d.join("board.json")), "board") {
            failures.push(format!("{}: {}", name, diff));
        }
    }
    for f in &failures {
        eprintln!("FAIL {}", f);
    }
    eprintln!("{} of {} fixtures built the same", dirs.len() - failures.len(), dirs.len());
    assert!(failures.is_empty());
}
