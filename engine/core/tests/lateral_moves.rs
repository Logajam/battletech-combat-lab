//! Tripod facing changes and lateral shifts (Core p.236-237), quad lateral shifts (p.238), through the real movement search.
use btsim_core::board_parser::parse_board_file;
use btsim_core::dice::PcgDice;
use btsim_core::drawn_route::*;
use btsim_core::hex_geometry;
use btsim_core::movement_attacks::neighbour;
use btsim_core::scenario::Scenario;
use btsim_core::terrain_rules::prepare_board;
use std::path::PathBuf;

/// The Asymptote II mirror (a tripod, walk 3, run 4) on clear desert ground, unit 0 facing south at the returned hex.
fn setup() -> (btsim_core::battle::Battle, String) {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../fixtures");
    let mut b = Scenario::load(&root.join("ref_Asymptote_vs_Asymptote_seed12345")).battle(Box::new(PcgDice::new(1)));
    let name = "AGoAC Maps__16x17 Desert 2.board";
    let text = std::fs::read_to_string(root.join("_boards").join(name)).unwrap();
    let mut out = String::new();
    let mut board = parse_board_file(name, &text, &mut out).unwrap();
    prepare_board(&mut board, true).unwrap();
    b.board = board;
    b.board_changed();
    // a hex with level ground round it: the start, and the hexes SW, S, SW-then-S of it
    let start = b
        .board
        .hexes
        .keys()
        .find(|k| {
            let mut hexes = vec![k.to_string()];
            for d in [4i64, 3, 2, 1, 0, 5] {
                match neighbour(k, d) {
                    Some(n) => hexes.push(n),
                    None => return false,
                }
            }
            match neighbour(&hexes[1], 3) {
                Some(n) => hexes.push(n),
                None => return false,
            }
            hexes.iter().all(|h| b.board.hexes.get(h).is_some_and(|x| !x.impassable && !x.building && x.level == 0))
        })
        .cloned()
        .expect("a clear start");
    b.units[0].hex = Some(start.clone());
    b.units[0].facing = "S".to_string();
    (b, start)
}

fn xy(l: &str) -> (i64, i64) {
    hex_geometry::parse_hex_label(l).unwrap()
}

#[test]
fn a_tripod_shifts_sideways_then_ahead_for_three() {
    let (b, start) = setup();
    let sw = neighbour(&start, 4).unwrap();
    let s2 = neighbour(&sw, 3).unwrap();
    let uw = UnitWalk::of(&b, 0).unwrap();
    // SW (a lateral shift: 1 + 1) then S (1): 3 MP = the tripod's walk, facing kept
    let ch = chain(&b, &uw, &[xy(&sw), xy(&s2)]).unwrap();
    assert_eq!((ch.spent, ch.facing), (3, 3), "route {:?}", ch.path);
    let d = finish(&b, 0, &[xy(&sw), xy(&s2)], 3, "Walk").expect("a walk");
    assert_eq!((d.pick.mp_spent, d.pick.mode.as_str()), (3, "Walk"));
    // the route is steps the walker accepts: a lateral shift first
    let steps = d.pick.route.clone().unwrap();
    assert_eq!(steps[0].name(), "lateral_right", "facing S, SW is the right-hand front diagonal: {:?}", steps);
}

#[test]
fn a_tripod_turns_any_number_of_hexsides_for_one_mp() {
    let (b, start) = setup();
    let uw = UnitWalk::of(&b, 0).unwrap();
    // facing S, to stand where it is facing N (three hexsides) costs 1 MP
    let t = btsim_core::pathfinder::build_movement_table(uw.start.0, uw.start.1, uw.start.2, 3, Some(&b.board), None, btsim_core::mech_state::ground_limit(&b.units[0]), false, &Default::default()).unwrap();
    assert_eq!(t.entries[&(uw.start.0, uw.start.1, 0)].keys().min(), Some(&1), "{}", start);
    // a biped needs three
    let (mut biped, _) = setup();
    biped.units[0].mech_type = "biped".to_string();
    let t2 = btsim_core::pathfinder::build_movement_table(uw.start.0, uw.start.1, uw.start.2, 3, Some(&biped.board), None, btsim_core::mech_state::ground_limit(&biped.units[0]), false, &Default::default()).unwrap();
    assert_eq!(t2.entries[&(uw.start.0, uw.start.1, 0)].keys().min(), Some(&3));
}

#[test]
fn a_quad_shifts_sideways_but_turns_normally() {
    let (mut b, start) = setup();
    b.units[0].mech_type = "quad".to_string();
    let sw = neighbour(&start, 4).unwrap();
    let uw = UnitWalk::of(&b, 0).unwrap();
    let ch = chain(&b, &uw, &[xy(&sw)]).unwrap();
    assert_eq!((ch.spent, ch.facing), (2, 3), "a quad's lateral shift costs 1 more than a step: {:?}", ch.path);
    // no free turning for a quad: three hexsides cost three
    let t = btsim_core::pathfinder::build_movement_table(uw.start.0, uw.start.1, uw.start.2, 4, Some(&b.board), None, btsim_core::mech_state::ground_limit(&b.units[0]), false, &Default::default()).unwrap();
    assert_eq!(t.entries[&(uw.start.0, uw.start.1, 0)].keys().min(), Some(&3));
}

#[test]
fn a_destroyed_leg_takes_the_shift_away() {
    let (mut b, start) = setup();
    let sw = neighbour(&start, 4).unwrap();
    b.units[0].destroyed_hip_locations.clear();
    let before = btsim_core::mech_state::ground_limit(&b.units[0]);
    assert!(before.lateral && before.free_facing);
    // a leg destroyed: no shift, no free turn (the Core text says "no destroyed legs")
    let m = &mut b.units[0];
    m.locations.get_mut("Left Leg").unwrap().destroyed = true;
    let after = btsim_core::mech_state::ground_limit(&b.units[0]);
    assert!(!after.lateral && !after.free_facing);
    let _ = sw;
}
