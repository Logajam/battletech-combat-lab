//! Combat Lab's page works a unit's Battle Value out for any pilot from its gunnery 4 / piloting 5 value:
//! floor(BV(4/5) x SKILL_TABLE[g][p] + 0.5) (engine/lab/web/lab.js, unitBv). This checks that equals the engine's own
//! `battle_value` for every unit file in data/ at every gunnery and piloting from 0 to 8.
use std::fs;
use std::path::PathBuf;

use btsim_core::battle::{Battle, TapeDice};
use btsim_core::battle_value::{battle_value, SKILL_TABLE};
use btsim_core::board_parser::Board;
use btsim_core::config::Config;
use btsim_core::equipment::EquipmentDb;
use btsim_core::mtf_parser::parse_mtf;

#[test]
fn page_bv_equals_engine_bv_at_every_skill() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..");
    let defaults: serde_json::Value = serde_json::from_str(&fs::read_to_string(root.join("engine/defaults/config.json")).unwrap()).unwrap();
    let cfg = Config::from_json(&defaults);
    let board = || Board::from_json(&serde_json::json!({"width": 1, "height": 1, "hexes": {}}));
    let (mut checked, mut wrong) = (0, Vec::new());
    for e in fs::read_dir(root.join("data")).unwrap() {
        let p = e.unwrap().path();
        if p.extension().is_none_or(|x| x != "mtf") {
            continue;
        }
        let mut out = String::new();
        let Ok(m) = parse_mtf(EquipmentDb::shared(), &fs::read_to_string(&p).unwrap(), &mut out) else { continue };
        let bv_at = |g: i64, pl: i64| {
            let mut m = m.clone();
            m.gunnery = g;
            m.piloting = pl;
            battle_value(&Battle::new(cfg.clone(), board(), vec![m], Box::new(TapeDice::new(vec![]))), 0)
        };
        let base = bv_at(4, 5);
        for g in 0..=8 {
            for pl in 0..=8 {
                let page = (base as f64 * SKILL_TABLE[g as usize][pl as usize] + 0.5).floor() as i64;
                let engine = bv_at(g, pl);
                checked += 1;
                if page != engine {
                    wrong.push(format!("{} {}/{}: page {} engine {}", p.file_name().unwrap().to_string_lossy(), g, pl, page, engine));
                }
            }
        }
    }
    eprintln!("{} unit-skill pairs checked", checked);
    assert!(checked > 1000, "too few units read");
    assert!(wrong.is_empty(), "{:?}", &wrong[..wrong.len().min(10)]);
}
