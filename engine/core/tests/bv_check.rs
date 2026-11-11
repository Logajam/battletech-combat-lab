//! BV of units as built (INTEGRATION__battle_value) against the `_bv_built` the Python cached on units in the fixtures.
use std::fs;
use std::path::PathBuf;

use btsim_core::battle::{Battle, TapeDice};
use btsim_core::board_parser::Board;
use btsim_core::config::Config;
use btsim_core::mech_state::Mech;
use serde_json::Value;

#[test]
fn battle_value_matches_the_python() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../fixtures");
    let (mut checked, mut wrong) = (0, Vec::new());
    for e in fs::read_dir(&root).unwrap() {
        let dir = e.unwrap().path();
        if !dir.join("units.json").exists() || !dir.join("config.json").exists() {
            continue;
        }
        let units_json: Value = serde_json::from_str(&fs::read_to_string(dir.join("units.json")).unwrap()).unwrap();
        let cfg = Config::from_json(&serde_json::from_str(&fs::read_to_string(dir.join("config.json")).unwrap()).unwrap());
        let board = Board::from_json(&serde_json::from_str(&fs::read_to_string(dir.join("board.json")).unwrap()).unwrap());
        let names: Vec<String> = units_json.as_object().unwrap().keys().cloned().collect();
        let idx = |n: &str| names.iter().position(|x| x == n).unwrap();
        let units: Vec<Mech> = names.iter().map(|n| Mech::from_json(&units_json[n], &idx)).collect();
        let dice = TapeDice::from_json(&serde_json::from_str(&fs::read_to_string(dir.join("dice.json")).unwrap()).unwrap());
        let b = Battle::new(cfg, board, units, Box::new(dice));
        // the Python computed BV during play: `_bv_built` shows in the states of the trace
        let mut built: std::collections::HashMap<String, i64> = Default::default();
        if let Ok(text) = fs::read_to_string(dir.join("trace.jsonl")) {
            for line in text.lines() {
                let v: Value = serde_json::from_str(line).unwrap();
                if let Some(us) = v["units"].as_object() {
                    for (n, u) in us {
                        if let Some(x) = u.get("_bv_built").and_then(|x| x.as_i64()) {
                            built.insert(n.clone(), x);
                        }
                    }
                }
            }
        }
        for (i, n) in names.iter().enumerate() {
            if let Some(want) = built.get(n).copied() {
                let got = btsim_core::battle_value::battle_value(&b, i);
                checked += 1;
                if got != want {
                    wrong.push(format!("{} {}: rust {} python {}", dir.file_name().unwrap().to_string_lossy(), n, got, want));
                }
            }
        }
    }
    eprintln!("{} BVs checked, {} wrong", checked, wrong.len());
    assert!(wrong.is_empty(), "{:?}", &wrong[..wrong.len().min(10)]);
    assert!(checked > 0, "no _bv_built in the fixtures");
}
