//! Mechanical jump boosters (TO:AUE p.105): no heat, the facing is kept, no Death From Above, usable under water.
use btsim_core::dice::PcgDice;
use btsim_core::heat::movement_heat;
use btsim_core::mech_state::compute_mechanical_jump_booster_mp;
use btsim_core::move_options::{movement_options, PathNotes};
use btsim_core::scenario::Scenario;
use btsim_core::water;
use std::path::PathBuf;

fn battle(test: &str) -> btsim_core::battle::Battle {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("reference").join("scenarios.zip");
    let dir = std::env::temp_dir().join(format!("jump_boosters_test_{}_{}", std::process::id(), test));
    let ok = std::process::Command::new("unzip").args(["-qo", root.to_str().unwrap(), "hy_2v2_grass/*", "-d", dir.to_str().unwrap()]).status().unwrap().success();
    assert!(ok, "unzip of the reference scenarios failed");
    let mut b = Scenario::load(&dir.join("hy_2v2_grass")).battle(Box::new(PcgDice::new(1)));
    // unit 0 on a clear hex mid-board, facing south
    b.units[0].hex = Some("0808".to_string());
    b.units[0].facing = "S".to_string();
    b
}

#[test]
fn boosters_keep_the_facing_and_make_no_heat() {
    let mut b = battle("keep");
    b.units[0].base_jump_mp = 0; // no jets: the boosters are the only jump
    b.units[0].base_mechanical_jump_booster_mp = 3;
    assert_eq!(compute_mechanical_jump_booster_mp(&b.units[0]), 3);
    // not chosen this turn: no jump at all (the jets are 0)
    assert_eq!(water::jump_mp(&b, 0), 0);
    b.units[0].jump_boosters_on = true;
    assert_eq!(water::jump_mp(&b, 0), 3, "the booster MP is the jump budget");
    assert_eq!(movement_heat(&b.units[0], "Jump", 3), 0, "boosters make no heat");
    b.units[0].jump_boosters_on = false;
    assert!(movement_heat(&b.units[0], "Jump", 3) >= 3, "jets still heat");
    b.units[0].jump_boosters_on = true;
    let start = btsim_core::hex_geometry::state_from_label(b.units[0].hex.as_deref().unwrap(), &b.units[0].facing).unwrap();
    let mut notes = PathNotes::default();
    let jumps: Vec<_> = movement_options(&b, 0, None, None, false, &mut notes).into_iter().filter(|k| k.4 == "Jump").collect();
    assert!(!jumps.is_empty(), "boosters give jump options");
    assert!(jumps.iter().all(|k| k.2 == start.2), "every booster jump lands facing the way it took off");
    assert!(jumps.iter().any(|k| (k.0, k.1) != (start.0, start.1)), "and some go somewhere");
}

#[test]
fn a_destroyed_booster_system_gives_nothing() {
    let mut b = battle("dead");
    b.units[0].base_mechanical_jump_booster_mp = 3;
    b.units[0].mechanical_jump_booster_disabled = true;
    b.units[0].jump_boosters_on = true;
    assert_eq!(water::jump_mp(&b, 0), 0);
}
