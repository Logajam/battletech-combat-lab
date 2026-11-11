//! Stage 2b: the movement DP against the Python (`python tools/port_stage2.py`).
use btsim_core::fasthash::HashSet;
use std::fs;
use std::path::PathBuf;

use btsim_core::board_parser::{parse_board_file, Board};
use btsim_core::pathfinder::*;
use btsim_core::terrain_rules::{prepare_board, GroundLimit};
use serde_json::{json, Value};

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../fixtures")
}

fn board(name: &str) -> Board {
    let text = fs::read_to_string(root().join("_boards").join(name)).unwrap();
    let mut out = String::new();
    let mut b = parse_board_file(&format!("engine/fixtures/_boards/{}", name), &text, &mut out).unwrap();
    prepare_board(&mut b, true).unwrap();
    b
}

fn table_json(t: &MovementTable) -> Value {
    let entries: Vec<Value> = t
        .entries
        .iter()
        .map(|(st, col)| json!([[st.0, st.1, st.2], col.iter().map(|(mp, fc)| json!([mp, fc])).collect::<Vec<_>>()]))
        .collect();
    let mut m = serde_json::Map::new();
    m.insert("entries".into(), Value::Array(entries));
    if let Some(psrs) = &t.psrs {
        let p: Vec<Value> = psrs
            .iter()
            .map(|(st, col)| json!([[st.0, st.1, st.2], col.iter().map(|(mp, v)| json!([mp, [v.0, v.1]])).collect::<Vec<_>>()]))
            .collect();
        m.insert("psrs".into(), Value::Array(p));
        let h: Vec<Value> = t
            .hazards
            .iter()
            .map(|(st, col)| json!([[st.0, st.1, st.2], col.iter().map(|(mp, v)| json!([mp, v])).collect::<Vec<_>>()]))
            .collect();
        m.insert("hazards".into(), Value::Array(h));
    }
    Value::Object(m)
}

#[test]
fn movement_tables_match_python() {
    let p = root().join("stage2/pathfinder.json");
    let d: Value = serde_json::from_str(&fs::read_to_string(&p).expect("run python tools/port_stage2.py")).unwrap();
    let mut n = 0;
    let mut with_psr = 0;
    let mut with_paths = 0;
    for group in d.as_array().unwrap() {
        let name = group[0].as_str().unwrap();
        if name == "flat" {
            for c in group[1].as_array().unwrap() {
                let st = &c[0];
                let t = build_movement_table(st[0].as_i64().unwrap(), st[1].as_i64().unwrap(), st[2].as_i64().unwrap(), c[1].as_i64().unwrap(),
                    None, None, GroundLimit { value: 2, superheavy: false }, false, &HashSet::default()).unwrap();
                assert_eq!(table_json(&t), c[2], "flat {:?}", c);
                n += 1;
            }
            continue;
        }
        let b = board(name);
        for c in group[1].as_array().unwrap() {
            let st = &c["start"];
            let blocked: HashSet<(i64, i64)> = c["blocked"].as_array().unwrap().iter().map(|h| (h[0].as_i64().unwrap(), h[1].as_i64().unwrap())).collect();
            let limit = GroundLimit { value: c["limit"][0].as_i64().unwrap(), superheavy: c["limit"][1].as_bool().unwrap() };
            let got = build_movement_table(st[0].as_i64().unwrap(), st[1].as_i64().unwrap(), st[2].as_i64().unwrap(),
                c["budget"].as_i64().unwrap(), Some(&b), c["backward"].as_i64(), limit, c["keep"].as_bool().unwrap(), &blocked);
            match (got, c.get("table"), c.get("error")) {
                (Ok(t), Some(w), None) => {
                    assert_eq!(table_json(&t), *w, "{} {:?}", name, c);
                    if t.psrs.is_some() {
                        with_psr += 1;
                    }
                    if let Some(paths) = c.get("paths") {
                        for pth in paths.as_array().unwrap() {
                            let s = &pth[0];
                            let got: Vec<Value> = t.path((s[0].as_i64().unwrap(), s[1].as_i64().unwrap(), s[2].as_i64().unwrap()), pth[1].as_i64().unwrap())
                                .iter().map(|(step, s2, m)| json!([step, [s2.0, s2.1, s2.2], m])).collect();
                            assert_eq!(Value::Array(got), pth[2], "path {} {:?}", name, pth[0]);
                        }
                        with_paths += 1;
                    }
                }
                (Err(e), None, Some(w)) => assert_eq!(format!("ValueError: {}", e), w.as_str().unwrap(), "{} {:?}", name, c),
                (g, _, _) => panic!("{} {:?}: Rust {:?}", name, c, g.map(|_| "table")),
            }
            n += 1;
        }
    }
    assert!(n > 700 && with_psr > 100 && with_paths > 20, "n {} psr {} paths {}", n, with_psr, with_paths);
}
