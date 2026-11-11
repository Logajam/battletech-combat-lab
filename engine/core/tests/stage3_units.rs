//! Stage 3: every unit of data/meks.zip parses like the Python (`python tools/port_stage3.py`).
use std::fs;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;

use btsim_core::equipment::EquipmentDb;
use btsim_core::mtf_parser::parse_mtf;
use serde_json::Value;

#[test]
fn every_unit_parses_like_python() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../fixtures");
    let f = fs::File::open(root.join("stage3/units.jsonl")).expect("run python tools/port_stage3.py");
    let db = EquipmentDb::load();
    let (mut ok, mut refused) = (0, 0);
    for line in BufReader::new(f).lines() {
        let e: Value = serde_json::from_str(&line.unwrap()).unwrap();
        let file = e["file"].as_str().unwrap();
        let bytes = fs::read(root.join("_mtf").join(file)).unwrap();
        let text = String::from_utf8_lossy(&bytes).to_string();
        let mut out = String::new();
        let got = parse_mtf(&db, &text, &mut out);
        assert_eq!(out, e["stdout"].as_str().unwrap(), "{}: printed text", file);
        match (got, e.get("unit"), e.get("error")) {
            (Ok(m), Some(w), None) => {
                let j = m.to_json(&|_| String::new());
                if j != *w {
                    // name the first differing key
                    for (k, v) in w.as_object().unwrap() {
                        assert_eq!(j.get(k), Some(v), "{}: field {}", file, k);
                    }
                    for k in j.as_object().unwrap().keys() {
                        assert!(w.get(k).is_some(), "{}: Rust has extra field {}", file, k);
                    }
                    panic!("{}: differs", file);
                }
                ok += 1;
            }
            (Err(msg), None, Some(w)) => {
                assert_eq!(format!("ValueError: {}", msg), w.as_str().unwrap(), "{}: refusal", file);
                refused += 1;
            }
            (g, _, _) => panic!("{}: Rust {:?}, Python {:?}", file, g.map(|_| "mech"), e),
        }
    }
    assert_eq!((ok, refused), (4204, 23));
}
