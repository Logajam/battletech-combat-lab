//! Walk-on starting zones (Combat Lab; Daniel, 2026-11-17): a side box (N, E, S, W) enters from that WHOLE edge; a corner box
//! from the two edges that meet there, each up to its half-way point; the centre from nowhere. The Lab's map preview draws
//! the same hexes (engine/lab/web/lab.js `entryHexes`).
use btsim_core::deployment::zone_entry_band;
use btsim_core::dice::PcgDice;
use btsim_core::scenario::Scenario;
use std::path::PathBuf;

/// The reference 2 v 2 on Grassland (16 x 17).
fn battle(test: &str) -> btsim_core::battle::Battle {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("reference").join("scenarios.zip");
    let dir = std::env::temp_dir().join(format!("zone_entry_test_{}_{}", std::process::id(), test));
    let ok = std::process::Command::new("unzip").args(["-qo", root.to_str().unwrap(), "hy_2v2_grass/*", "-d", dir.to_str().unwrap()]).status().unwrap().success();
    assert!(ok, "unzip of the reference scenarios failed");
    Scenario::load(&dir.join("hy_2v2_grass")).battle(Box::new(PcgDice::new(1)))
}

fn boxes(on: &[usize]) -> [bool; 9] {
    let mut b = [false; 9];
    for k in on {
        b[*k] = true;
    }
    b
}

fn cols_rows(hexes: &[String]) -> Vec<(i64, i64)> {
    let mut v: Vec<(i64, i64)> = hexes.iter().map(|l| (l[0..2].parse().unwrap(), l[2..4].parse().unwrap())).collect();
    v.sort();
    v
}

#[test]
fn a_side_box_enters_from_the_whole_edge() {
    let b = battle("side");
    let (w, h) = (b.board.width, b.board.height);
    assert_eq!((w, h), (16, 17));
    // N, depth 0: the whole north row
    let n = cols_rows(&zone_entry_band(&b, &boxes(&[1]), 0));
    assert_eq!(n, (1..=w).map(|c| (c, 1)).collect::<Vec<_>>());
    // W, depth 2: the three west columns, every row
    let west = zone_entry_band(&b, &boxes(&[3]), 2);
    assert_eq!(west.len() as i64, 3 * h);
    assert!(cols_rows(&west).iter().all(|(c, _)| *c <= 3));
}

#[test]
fn a_corner_box_enters_from_two_half_edges() {
    let b = battle("corner");
    // NW, depth 0: north row columns 1-8 (half of 16) and west column rows 1-9 (17 is odd: the middle row 9 is in both halves)
    let nw = cols_rows(&zone_entry_band(&b, &boxes(&[0]), 0));
    let mut want: Vec<(i64, i64)> = (1..=8).map(|c| (c, 1)).chain((2..=9).map(|r| (1, r))).collect();
    want.sort();
    assert_eq!(nw, want);
    // SE, depth 0: south row columns 9-16, east column rows 9-17
    let se = cols_rows(&zone_entry_band(&b, &boxes(&[8]), 0));
    let mut want: Vec<(i64, i64)> = (9..=16).map(|c| (c, 17)).chain((9..=16).map(|r| (16, r))).collect();
    want.sort();
    assert_eq!(se, want);
}

#[test]
fn the_centre_has_no_entry_and_boxes_do_not_double_count() {
    let b = battle("centre");
    assert!(zone_entry_band(&b, &boxes(&[4]), 3).is_empty());
    // N + NE + NW = the north edge once (the corners also add their west / east halves)
    let top = zone_entry_band(&b, &boxes(&[0, 1, 2]), 0);
    let mut uniq = top.clone();
    uniq.sort();
    uniq.dedup();
    assert_eq!(uniq.len(), top.len());
}
