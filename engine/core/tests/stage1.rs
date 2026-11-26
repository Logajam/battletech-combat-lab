//! Stage 1 (INTEGRATION__RUST_PORT.md): hex geometry, board parser, terrain rules against the Python's answers.
//! Fixtures: `python tools/port_stage1.py` writes engine/fixtures/stage1 (git-ignored) from the Python.
use std::fs;
use std::path::PathBuf;

use btsim_core::board_parser::{parse_board_file, stitch_boards, Board};
use btsim_core::hex_geometry::*;
use btsim_core::los::hex_distance;
use btsim_core::terrain_rules::*;
use serde_json::Value;

fn fixtures() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../fixtures")
}

fn load(name: &str) -> Value {
    let p = fixtures().join("stage1").join(name);
    let text = fs::read_to_string(&p)
        .unwrap_or_else(|_| panic!("{} is missing - run `python tools/port_stage1.py` from the repo root", p.display()));
    serde_json::from_str(&text).unwrap()
}

fn board_text(file: &str) -> (String, String) {
    let display = format!("engine/fixtures/_boards/{}", file);
    let text = fs::read_to_string(fixtures().join("_boards").join(file)).unwrap();
    (display, text)
}

fn s(v: &Value) -> &str {
    v.as_str().unwrap()
}
fn i(v: &Value) -> i64 {
    v.as_i64().unwrap()
}

fn err_text(e: &str) -> String {
    format!("ValueError: {}", e)
}

#[test]
fn geometry_labels_roundtrip_like_python() {
    let g = load("geometry.json");
    for c in g["labels"].as_array().unwrap() {
        let (x, y) = parse_hex_label(s(&c[0])).unwrap();
        assert_eq!((x, y), (i(&c[1]), i(&c[2])), "parse {}", c[0]);
        assert_eq!(hex_label(x, y).unwrap(), s(&c[3]), "label of {} {}", x, y);
    }
    for c in g["bad_labels"].as_array().unwrap() {
        let got = match parse_hex_label(s(&c[0])) {
            Ok((x, y)) => serde_json::json!([x, y]),
            Err(e) => Value::String(err_text(&e)),
        };
        assert_eq!(got, c[1], "bad label {:?}", c[0]);
    }
    for c in g["bad_xy"].as_array().unwrap() {
        let got = match hex_label(i(&c[0]), i(&c[1])) {
            Ok(l) => Value::String(l),
            Err(e) => Value::String(err_text(&e)),
        };
        assert_eq!(got, c[2], "bad xy {:?}", c);
    }
    for c in g["compass"].as_array().unwrap() {
        let got = match compass_to_facing(s(&c[0])) {
            Ok(f) => serde_json::json!(f),
            Err(e) => Value::String(err_text(&e)),
        };
        assert_eq!(got, c[1], "compass {:?}", c[0]);
    }
    for c in g["facings"].as_array().unwrap() {
        let got = match facing_to_compass(i(&c[0])) {
            Ok(n) => Value::String(n.to_string()),
            Err(e) => Value::String(err_text(&e)),
        };
        assert_eq!(got, c[1], "facing {:?}", c[0]);
    }
}

#[test]
fn hex_distance_matches_python_on_100k_pairs() {
    let g = load("geometry.json");
    let rows = g["distance"].as_array().unwrap();
    assert_eq!(rows.len(), 100000);
    for c in rows {
        assert_eq!(hex_distance((i(&c[0]), i(&c[1])), (i(&c[2]), i(&c[3]))), i(&c[4]), "distance {:?}", c);
    }
}

/// Load + prepare a board the way the Python tool did; (board json or error text, warnings).
fn load_board(file: &str, passive: bool) -> (Result<Board, String>, String) {
    let (display, text) = board_text(file);
    let mut out = String::new();
    let result = parse_board_file(&display, &text, &mut out).and_then(|mut b| {
        prepare_board(&mut b, passive)?;
        Ok(b)
    });
    (result, out)
}

fn canon(v: &Value) -> String {
    serde_json::to_string(v).unwrap()
}

#[test]
fn every_board_loads_or_is_refused_like_python() {
    let boards = load("boards.json");
    let mut played = 0;
    for (name, entry) in boards.as_object().unwrap() {
        for (mode, passive) in [("passive", true), ("full", false)] {
            let want = &entry[mode];
            let (got, out) = load_board(s(&entry["file"]), passive);
            assert_eq!(out, s(&want["stdout"]), "{} ({}): warnings", name, mode);
            match (&got, want.get("board"), want.get("error")) {
                (Ok(b), Some(w), None) => {
                    assert_eq!(canon(&b.to_json()), canon(w), "{} ({}): board", name, mode);
                    if passive {
                        played += 1;
                    }
                }
                (Err(e), None, Some(w)) => assert_eq!(err_text(e), s(w), "{} ({}): refusal", name, mode),
                _ => panic!("{} ({}): Rust {:?} but Python {:?}", name, mode, got.as_ref().map(|_| "a board"), want),
            }
        }
    }
    assert!(played > 300, "only {} boards played", played);
}

#[test]
fn stitched_boards_match_python() {
    let cases = load("stitched.json");
    for c in cases.as_array().unwrap() {
        let files: Vec<(String, String)> = c["files"].as_array().unwrap().iter().map(|f| board_text(s(f))).collect();
        let mut out = String::new();
        let got = stitch_boards(&files, i(&c["cols"]), i(&c["rows"]), &mut out);
        assert_eq!(out, s(&c["stdout"]), "stitch warnings for {:?}", c["files"]);
        match (got, c.get("board"), c.get("error")) {
            (Ok(b), Some(w), None) => assert_eq!(canon(&b.to_json()), canon(w), "stitched {:?}", c["files"]),
            (Err(e), None, Some(w)) => assert_eq!(err_text(&e), s(w), "stitch refusal {:?}", c["files"]),
            (g, _, _) => panic!("stitch {:?}: Rust {:?}, Python {:?}", c["files"], g.map(|_| "board"), c),
        }
    }
}

#[test]
fn terrain_rules_match_python() {
    let t = load("terrain.json");
    let boards = load("boards.json");
    let mut cache: btsim_core::fasthash::HashMap<String, Board> = btsim_core::fasthash::HashMap::default();
    let mut get = |name: &str| -> Board {
        cache
            .entry(name.to_string())
            .or_insert_with(|| load_board(s(&boards[name]["file"]), true).0.unwrap())
            .clone()
    };
    for c in t["flags"].as_array().unwrap() {
        let b = get(s(&c[0]));
        assert_eq!(has_hazard_terrain(&b), c[1].as_bool().unwrap(), "hazard flag {}", c[0]);
        assert_eq!(has_psr_terrain(&b), c[2].as_bool().unwrap(), "psr flag {}", c[0]);
    }
    for c in t["cost"].as_array().unwrap() {
        let b = get(s(&c[0]));
        let got = terrain_cost(&b.hexes[s(&c[1])].features, c[2].as_bool().unwrap()).unwrap();
        assert_eq!(got, i(&c[3]), "terrain_cost {:?}", c);
    }
    for c in t["hazard"].as_array().unwrap() {
        let b = get(s(&c[0]));
        for (k, legs) in [1, 2, 3, 4].iter().enumerate() {
            let want = c[2][k].as_f64().unwrap();
            assert_eq!(step_hazard(&b.hexes[s(&c[1])], *legs).to_bits(), want.to_bits(), "step_hazard {:?} legs {}", c, legs);
        }
    }
    let mut steps = 0;
    for c in t["step"].as_array().unwrap() {
        let b = get(s(&c[0]));
        let from = if c[1].is_null() { None } else { Some(&b.hexes[s(&c[1])]) };
        let to = &b.hexes[s(&c[2])];
        let limit = GroundLimit { value: i(&c[3]), superheavy: c[4].as_bool().unwrap(), lateral: false, free_facing: false };
        let got = step_cost(from, to, limit, c[5].as_bool().unwrap());
        let want = if c[6].is_null() { None } else { Some(i(&c[6])) };
        assert_eq!(got, want, "step_cost {:?}", c);
        steps += 1;
    }
    assert!(steps > 50000, "only {} step cases", steps);
    for c in t["psr"].as_array().unwrap() {
        let b = get(s(&c[0]));
        if c.as_array().unwrap().len() == 3 {
            let (a, r) = turn_psrs(&b.hexes[s(&c[1])]);
            assert_eq!(serde_json::json!([a, r]), c[2], "turn_psrs {:?}", c);
        } else {
            let from = &b.hexes[s(&c[1])];
            let to = &b.hexes[s(&c[2])];
            for (k, bw) in [false, true].iter().enumerate() {
                let (a, r) = step_psrs(Some(from), to, *bw);
                assert_eq!(serde_json::json!([a, r]), c[3][k], "step_psrs {:?}", c);
            }
            let mut k = 0;
            for bw in [false, true] {
                for run in [false, true] {
                    let causes = step_psr_causes(Some(from), to, bw, run);
                    assert_eq!(serde_json::json!(causes), c[4][k], "step_psr_causes {:?}", c);
                    k += 1;
                }
            }
        }
    }
}
