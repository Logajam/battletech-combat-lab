//! The step walker (`step_walk.rs`) against the movement DP (`pathfinder.rs`): the DP is the standard, the walker may not disagree.
//! Inputs are the frozen answer key's boards (`python tools/unpack_answer_key.py`), as in `stage2_pathfinder.rs`.
use btsim_core::board_parser::{parse_board_file, Board};
use btsim_core::fasthash::HashSet;
use btsim_core::pathfinder::*;
use btsim_core::step_walk::*;
use btsim_core::terrain_rules::{prepare_board, GroundLimit};
use std::collections::BTreeSet;
use std::fs;
use std::path::PathBuf;

/// The board, or None if the simulator cannot play it yet (bridges and the like are refused by `prepare_board`).
fn board(name: &str) -> Option<Board> {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../fixtures/_boards");
    let text = fs::read_to_string(dir.join(name)).expect("run python tools/unpack_answer_key.py");
    let mut out = String::new();
    let mut b = parse_board_file(name, &text, &mut out).ok()?;
    prepare_board(&mut b, true).ok()?;
    Some(b)
}

/// Four passable hexes spread over the board, as walk starts.
fn starts(b: &Board) -> Vec<(i64, i64)> {
    let open: Vec<(i64, i64)> = b.hexes.iter().filter(|(_, h)| !h.impassable && !h.building).filter_map(|(k, _)| btsim_core::hex_geometry::parse_hex_label(k).ok()).collect();
    (0..4).map(|i| open[open.len() * (2 * i + 1) / 8]).collect()
}

/// every (x, y, facing, last, used_back, mp) the walker reaches from the start, by walking the whole step graph
fn walker_reach(w: &Walker, start: &WalkState) -> BTreeSet<(i64, i64, i64, i64, bool, i64)> {
    let mut seen = BTreeSet::new();
    let mut todo = vec![start.clone()];
    while let Some(s) = todo.pop() {
        let k = (s.x, s.y, s.facing, s.last, s.used_back, s.mp);
        if !seen.insert(k) {
            continue;
        }
        for (_, n) in w.legal_steps(&s) {
            todo.push(n);
        }
    }
    seen
}

#[test]
fn walker_and_dp_agree() {
    // hills, rough ground, water and lava between them; a board the simulator cannot play yet is skipped
    let boards = [
        "Clan Invasion Boxset__16x17 Hilltops 1.board",
        "Clan Invasion Boxset__16x17 Rolling Hills 2 (Clan Invasion).board",
        "AGoAC Maps__16x17 Desert 2.board",
        "Alien Worlds__32x17 Caustic Valley (Water).board",
        "Alien Worlds__32x17 Caustic Valley (Lava).board",
        "Battle of Tukayyid Pack__32x17 Devil's Bath (CSV) - magma option.board",
    ];
    let (mut states, mut routes, mut with_back, mut with_psr, mut loaded, mut hazard_boards, mut psr_boards, mut hazard_routes) = (0, 0, 0, 0, 0, 0, 0, 0);
    for name in boards {
        let Some(b) = board(name) else { continue };
        loaded += 1;
        hazard_boards += btsim_core::terrain_rules::has_hazard_terrain(&b) as i32;
        psr_boards += btsim_core::terrain_rules::has_psr_terrain(&b) as i32;
        let blocked: HashSet<(i64, i64)> = HashSet::default();
        for (i, (sx, sy)) in starts(&b).into_iter().enumerate() {
            let f = (i as i64 * 2 + 1) % 6;
            // a biped, a quad (lateral shifts) and a tripod (lateral shifts, one-MP facing changes)
            for &(budget, backward, lateral, free_facing) in &[(5, None, false, false), (6, Some(3), false, false), (8, Some(4), false, false), (10, None, false, false), (6, Some(3), true, false), (5, None, true, false), (6, Some(4), true, true), (5, None, true, true)] {
                let limit = GroundLimit { value: 2, superheavy: false, lateral, free_facing };
                let table = build_movement_table(sx, sy, f, budget, Some(&b), backward, limit, true, &blocked).unwrap();
                let w = Walker { board: &b, blocked: &blocked, level_limit: limit, budget, backward_mp: backward };
                let start = w.start(sx, sy, f).unwrap();

                // 1. every route the DP can rebuild, walked step by step, ends where the DP says with the DP's totals
                for (&state, col) in table.entries.iter() {
                    for (&mp, &fc) in col.iter() {
                        let path = table.path(state, mp);
                        let steps = steps_of_path(f, &path);
                        let walked = w.walk(&start, &steps).unwrap_or_else(|(i, e)| panic!("{} {:?} mp {}: step {} refused: {}", name, state, mp, i, e));
                        let end = walked.last().cloned().unwrap_or_else(|| start.clone());
                        assert_eq!((end.state(), end.mp), (state, mp), "{} route to {:?}", name, state);
                        assert_eq!(end.forward_count, fc, "{} forward count to {:?} at {}", name, state, mp);
                        if let Some(psrs) = &table.psrs {
                            let (a, r) = psrs[&state][&mp];
                            assert_eq!((end.always_psrs, end.run_psrs), (a, r), "{} PSRs to {:?} at {}", name, state, mp);
                            assert!((end.hazard - table.hazards[&state][&mp]).abs() < 1e-9, "{} hazard to {:?} at {}", name, state, mp);
                            if a + r > 0 {
                                with_psr += 1;
                            }
                            if end.hazard > 0.0 {
                                hazard_routes += 1;
                            }
                        }
                        if steps.contains(&Step::Backward) {
                            with_back += 1;
                        }
                        routes += 1;
                    }
                }

                // 2. the walker reaches exactly the (hex, facing, MP) the DP does: nothing the DP lacks, nothing it has that
                //    the walker cannot walk
                let from_walker: BTreeSet<_> = walker_reach(&w, &start).into_iter().map(|(x, y, fc, _, _, mp)| (x, y, fc, mp)).collect();
                let from_dp: BTreeSet<_> = table.entries.iter().flat_map(|(&(x, y, fc), col)| col.keys().map(move |&mp| (x, y, fc, mp))).collect();
                assert_eq!(from_walker, from_dp, "{} start ({}, {}, {}) budget {} backward {:?}", name, sx, sy, f, budget, backward);
                states += from_dp.len();
            }
        }
    }
    eprintln!("step_walk: {} boards ({} with PSR terrain, {} with hazards), {} DP routes replayed ({} with a backward step, {} with PSRs, {} through hazards), {} (hex, facing, MP) states compared", loaded, psr_boards, hazard_boards, routes, with_back, with_psr, hazard_routes, states);
    assert!(loaded >= 3 && psr_boards >= 2 && hazard_boards >= 1, "boards loaded {} with PSR terrain {} with hazards {}", loaded, psr_boards, hazard_boards);
    assert!(routes > 2000 && states > 2000 && with_back > 50 && with_psr > 50 && hazard_routes > 0, "routes {} states {} backward {} psr {} hazard {}", routes, states, with_back, with_psr, hazard_routes);
}

#[test]
fn refusals_say_why() {
    let b = board("AGoAC Maps__16x17 Desert 2.board").expect("a playable board");
    let limit = GroundLimit { value: 2, superheavy: false, lateral: false, free_facing: false };
    // a hex of open ground whose neighbour straight ahead (facing 0) is also open: block it
    let empty: HashSet<(i64, i64)> = HashSet::default();
    let (sx, sy) = starts(&b)
        .into_iter()
        .chain(b.hexes.keys().filter_map(|k| btsim_core::hex_geometry::parse_hex_label(k).ok()))
        .find(|&(x, y)| {
            let w = Walker { board: &b, blocked: &empty, level_limit: limit, budget: 6, backward_mp: None };
            w.start(x, y, 0).is_ok_and(|s| w.step(&s, Step::Forward).is_ok())
        })
        .expect("some open hex with an open hex ahead");
    let mut blocked: HashSet<(i64, i64)> = HashSet::default();
    blocked.insert((sx, sy + 2));
    let w = Walker { board: &b, blocked: &blocked, level_limit: limit, budget: 6, backward_mp: None };
    let start = w.start(sx, sy, 0).unwrap();
    assert_eq!(w.step(&start, Step::Forward), Err(StepError::Blocked));
    // no backward budget: no backward step
    assert_eq!(w.step(&start, Step::Backward), Err(StepError::NoBackward));
    // out of MP: spin until the budget is gone
    let mut s = start.clone();
    for _ in 0..6 {
        s = w.step(&s, Step::TurnRight).unwrap();
    }
    assert!(matches!(w.step(&s, Step::TurnLeft), Err(StepError::OutOfMp { needed: 1, left: 0 })));
    // a start off the board is an error, not a panic
    assert!(w.start(-5, -5, 0).is_err() && w.start(sx, sy, 7).is_err());
    // names round-trip
    for st in Step::ALL {
        assert_eq!(Step::from_name(st.name()), Some(st));
    }
}
