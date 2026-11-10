//! Stage 2a: line of sight against the Python (`python tools/port_stage2.py` after `python tools/port_stage1.py`).
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;

use btsim_core::board_parser::{parse_board_file, Board, Smoke};
use btsim_core::los::*;
use btsim_core::terrain_rules::prepare_board;
use serde_json::Value;

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../fixtures")
}

fn load_json(rel: &str) -> Value {
    let p = root().join(rel);
    serde_json::from_str(&fs::read_to_string(&p).unwrap_or_else(|_| panic!("{} missing - run tools/port_stage1.py and tools/port_stage2.py", p.display()))).unwrap()
}

fn board(name: &str) -> Board {
    let text = fs::read_to_string(root().join("_boards").join(name)).unwrap();
    let mut out = String::new();
    let mut b = parse_board_file(&format!("engine/fixtures/_boards/{}", name), &text, &mut out).unwrap();
    prepare_board(&mut b, true).unwrap();
    b
}

fn hex(v: &Value) -> Hex {
    (v[0].as_i64().unwrap(), v[1].as_i64().unwrap())
}

#[test]
fn hex_line_matches_python() {
    let d = load_json("stage2/los.json");
    for c in d["lines"].as_array().unwrap() {
        let got = hex_line(hex(&c[0]), hex(&c[1]));
        let got_json: Vec<Vec<Vec<i64>>> = got.iter().map(|s| s.iter().map(|h| vec![h.0, h.1]).collect()).collect();
        assert_eq!(serde_json::to_value(&got_json).unwrap(), c[2], "hex_line {:?} -> {:?}", c[0], c[1]);
    }
}

fn step_json(s: &LOSStep) -> Value {
    serde_json::json!([s.index, [s.hex.0, s.hex.1], s.other_candidate.map(|h| vec![h.0, h.1]), s.level, s.is_endpoint,
        s.blocked, s.woods_contrib, s.partial_cover, s.cumulative_modifier, s.smoke_contrib, s.after_block])
}

#[test]
fn line_of_sight_traces_match_python() {
    let d = load_json("stage2/los.json");
    let mut smoke_by_board: HashMap<String, Value> = HashMap::new();
    for b in d["boards"].as_array().unwrap() {
        smoke_by_board.insert(b[0].as_str().unwrap().to_string(), b[1].clone());
    }
    let mut cache: HashMap<(String, bool), Board> = HashMap::new();
    let mut n = 0;
    for c in d["los"].as_array().unwrap() {
        let name = c[0].as_str().unwrap().to_string();
        let with_smoke = c[1].as_bool().unwrap();
        let b = cache.entry((name.clone(), with_smoke)).or_insert_with(|| {
            let mut b = board(&name);
            if with_smoke {
                for (label, sm) in smoke_by_board[&name].as_object().unwrap() {
                    b.hexes.get_mut(label).unwrap().smoke =
                        Some(Smoke { density: sm["density"].as_str().unwrap().to_string(), until: sm["until"].as_i64().unwrap() });
                }
            }
            b
        });
        let h = |v: &Value| mech_height(v[0].as_bool().unwrap(), v[1].as_bool().unwrap());
        let (a, t) = (hex(&c[2]), hex(&c[3]));
        let got = trace_los_path(a, t, b, h(&c[4]), h(&c[5]));
        let want = &c[6];
        match (got, want.get("ok"), want.get("error")) {
            (Ok(tr), Some(w), None) => {
                if w.is_boolean() {
                    assert_eq!(Value::Bool(tr.result.los), *w, "{:?}", c);
                } else {
                    let res = serde_json::json!([tr.result.los, tr.result.modifier, tr.result.distance]);
                    assert_eq!(res, w[0], "result of {:?}", c);
                    let steps: Vec<Value> = tr.steps.iter().map(step_json).collect();
                    assert_eq!(Value::Array(steps), w[1], "steps of {:?}", c);
                }
            }
            (Err(e), None, Some(w)) => assert_eq!(format!("ValueError: {}", e), w.as_str().unwrap(), "{:?}", c),
            (g, _, _) => panic!("{:?}: Rust {:?} Python {:?}", c, g.map(|_| "trace"), want),
        }
        n += 1;
    }
    assert!(n > 38000, "{} cases", n);
}

#[test]
fn target_hex_modifier_matches_python() {
    let d = load_json("stage2/los.json");
    let mut smoke_by_board: HashMap<String, Value> = HashMap::new();
    for b in d["boards"].as_array().unwrap() {
        smoke_by_board.insert(b[0].as_str().unwrap().to_string(), b[1].clone());
    }
    for c in d["target_mod"].as_array().unwrap() {
        let name = c[0].as_str().unwrap();
        let mut b = board(name);
        if c[1].as_bool().unwrap() {
            for (label, sm) in smoke_by_board[name].as_object().unwrap() {
                b.hexes.get_mut(label).unwrap().smoke =
                    Some(Smoke { density: sm["density"].as_str().unwrap().to_string(), until: sm["until"].as_i64().unwrap() });
            }
        }
        let (x, y) = btsim_core::hex_geometry::parse_hex_label(c[2].as_str().unwrap()).unwrap();
        assert_eq!(target_hex_modifier((x, y), &b).unwrap(), c[3].as_i64().unwrap(), "{:?}", c);
    }
}
