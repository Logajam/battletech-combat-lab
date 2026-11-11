//! Every unit state in every recorded battle (units.json, and trace lines) reads into a Mech and writes back out
//! identically: the Rust data model holds every attribute the Python ever gives a 'Mech.
//! Needs `python tools/port_fixtures.py --no-replay` (engine/fixtures).
use std::fs;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;

use btsim_core::mech_state::Mech;
use serde_json::Value;

/// path and both values (cut short) of the first difference
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
        _ => Some(format!("{}: rust {} python {}", path, a.to_string().chars().take(80).collect::<String>(), b.to_string().chars().take(80).collect::<String>())),
    }
}

static SEEN: std::sync::Mutex<Vec<(String, String)>> = std::sync::Mutex::new(Vec::new());

fn check(file: &str, label: &str, units: &serde_json::Map<String, Value>) -> usize {
    let names: Vec<String> = units.keys().cloned().collect();
    let idx = |n: &str| names.iter().position(|x| x == n).unwrap();
    let name_of = |i: usize| names[i].clone();
    let mut n = 0;
    for (side, dump) in units {
        let mech = Mech::from_json(dump, &idx);
        let back = mech.to_json(&name_of);
        if back != *dump {
            let d = first_diff(&back, dump, "").unwrap_or_else(|| "differs".into());
            let key: String = d.split(':').next().unwrap().chars().filter(|c| !c.is_ascii_digit()).collect();
            let mut seen = SEEN.lock().unwrap();
            if !seen.iter().any(|(k, _)| *k == key) {
                seen.push((key, format!("{} {} {}: {}", file, label, side, d)));
            }
        }
        n += 1;
    }
    n
}

#[test]
fn every_recorded_unit_state_round_trips() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../fixtures");
    let mut total = 0;
    let mut dirs: Vec<_> = fs::read_dir(&root)
        .expect("run python tools/port_fixtures.py --no-replay")
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.join("trace.jsonl").exists())
        .collect();
    dirs.sort();
    assert!(dirs.len() >= 60, "only {} fixtures", dirs.len());
    for d in dirs {
        let name = d.file_name().unwrap().to_string_lossy().to_string();
        let units: Value = serde_json::from_str(&fs::read_to_string(d.join("units.json")).unwrap()).unwrap();
        total += check(&name, "units.json", units.as_object().unwrap());
        let f = fs::File::open(d.join("trace.jsonl")).unwrap();
        for (i, line) in BufReader::new(f).lines().enumerate() {
            // every line of a small battle, every 7th of a big one
            let line = line.unwrap();
            if line.len() > 3_000_000 && i % 7 != 0 {
                continue;
            }
            let t: Value = serde_json::from_str(&line).unwrap();
            total += check(&name, &format!("trace line {}", i + 1), t["units"].as_object().unwrap());
        }
    }
    let seen = SEEN.lock().unwrap();
    if !seen.is_empty() {
        panic!("{} kinds of difference:\n{}", seen.len(), seen.iter().map(|(_, d)| d.clone()).collect::<Vec<_>>().join("\n"));
    }
    assert!(total > 2000, "{} states", total);
}
