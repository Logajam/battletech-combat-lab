//! Drawn routes (`drawn_route.rs`, Daniel 2026-11-24: "Follow the route as drawn"): a route a person draws through waypoints is the
//! route the unit walks, and a route round a hazard avoids it.
//! Inputs: the 2 v 2 mirror from engine/reference/scenarios.zip and the frozen answer key's boards (`python tools/unpack_answer_key.py`).
use btsim_core::battle::{Battle, UnitId};
use btsim_core::board_parser::{parse_board_file, Board};
use btsim_core::dice::PcgDice;
use btsim_core::drawn_route::*;
use btsim_core::gladiator_bots::GladiatorBots;
use btsim_core::human_bots::{Controller, HumanBots, PassThrough};
use btsim_core::orchestrator::{play_on, start_battle, PathGate};
use btsim_core::scenario::Scenario;
use btsim_core::terrain_rules::prepare_board;
use btsim_core::{hex_geometry, los};
use std::cell::RefCell;
use std::path::PathBuf;
use std::rc::Rc;

fn two_v_two(test: &str) -> Scenario {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("reference").join("scenarios.zip");
    let dir = std::env::temp_dir().join(format!("drawn_route_test_{}_{}", std::process::id(), test));
    let ok = std::process::Command::new("unzip").args(["-qo", root.to_str().unwrap(), "hy_2v2_grass/*", "-d", dir.to_str().unwrap()]).status().unwrap().success();
    assert!(ok, "unzip of the reference scenarios failed");
    Scenario::load(&dir.join("hy_2v2_grass"))
}

fn fixture_board(name: &str) -> Option<Board> {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../fixtures/_boards");
    let text = std::fs::read_to_string(dir.join(name)).expect("run python tools/unpack_answer_key.py");
    let mut out = String::new();
    let mut b = parse_board_file(name, &text, &mut out).ok()?;
    prepare_board(&mut b, true).ok()?;
    Some(b)
}

fn xy(b: &Board) -> Vec<(i64, i64)> {
    b.hexes.iter().filter(|(_, h)| !h.impassable && !h.building).filter_map(|(k, _)| hex_geometry::parse_hex_label(k).ok()).collect()
}

/// Puts unit 0 on `at` facing `facing` on `board` (the battle's own board is replaced).
fn place(b: &mut Battle, board: &Board, at: (i64, i64), facing: i64) {
    b.board = board.clone();
    b.board_changed();
    b.units[0].hex = Some(hex_geometry::hex_label(at.0, at.1).unwrap());
    b.units[0].facing = hex_geometry::facing_to_compass(facing).unwrap().to_string();
}

#[test]
fn a_route_round_a_hazard_avoids_it() {
    let sc = two_v_two("hazard");
    let mut b = sc.battle(Box::new(PcgDice::new(1)));
    let mut found = 0;
    let mut boards = 0;
    for name in ["Alien Worlds__32x17 Caustic Valley (Lava).board", "Battle of Tukayyid Pack__32x17 Devil's Bath (CSV) - magma option.board"] {
        let Some(board) = fixture_board(name) else { continue };
        boards += 1;
        let hexes = xy(&board);
        'search: for &s in hexes.iter().step_by(5) {
            place(&mut b, &board, s, 0);
            let Some(uw) = UnitWalk::of(&b, 0) else { continue };
            for &t in hexes.iter().filter(|&&t| (2..=4).contains(&los::hex_distance(s, t))) {
                // the cheapest way straight there crosses a hazard...
                let Ok(direct) = chain(&b, &uw, &[t]) else { continue };
                let Some((walked, _)) = replay(&b, &uw, &direct.path) else { continue };
                if walked.hazard == 0.0 {
                    continue;
                }
                // ...and a waypoint away from it gives a route that does not
                for &w in hexes.iter().filter(|&&w| los::hex_distance(s, w) <= 4 && los::hex_distance(w, t) <= 4 && w != s && w != t) {
                    let Ok(ch) = chain(&b, &uw, &[w, t]) else { continue };
                    let mode = btsim_core::combat::classify_movement_mode(ch.spent, uw.walk);
                    if ch.spent > uw.run || mode == "Stand Still" {
                        continue;
                    }
                    let Ok(d) = finish(&b, 0, &[w, t], ch.facing, mode) else { continue };
                    if d.hazard != 0.0 {
                        continue;
                    }
                    // the drawn route's own numbers are carried, and the route is the one the walker accepts
                    let steps = d.pick.route.clone().expect("a drawn pick carries its route");
                    let path = path_of_steps(&b, &uw, &steps).expect("the walker accepts the drawn route");
                    let (end, _) = replay(&b, &uw, &path).unwrap();
                    assert_eq!((end.forward_count, end.mp, end.hazard), (d.pick.fc, d.pick.mp_spent, 0.0));
                    assert_eq!(hex_geometry::hex_label(end.x, end.y).unwrap(), d.pick.hex);
                    assert!(d.hazard < walked.hazard, "round the hazard: {} against {} straight on", d.hazard, walked.hazard);
                    // it passes through the waypoint
                    let wl = hex_geometry::hex_label(w.0, w.1).unwrap();
                    assert!(path.iter().any(|(_, (x, y, _), _)| hex_geometry::hex_label(*x, *y).unwrap() == wl), "the route passes through its waypoint");
                    found += 1;
                    if found >= 3 {
                        break 'search;
                    }
                    continue 'search;
                }
            }
        }
    }
    assert!(boards > 0, "no hazard board could be loaded");
    assert!(found >= 1, "no straight-on route across a hazard with a way round was found on {} board(s)", boards);
    eprintln!("drawn_route: {} routes round a hazard found and checked", found);
}

/// Draws one move through a waypoint off the engine's own cheapest route, then lets every question go to the bots.
struct Drawer {
    pass: PassThrough,
    /// the route text the first drawn move must show in its MOVE_PATH event, and the pick's hex and MP
    drawn: Rc<RefCell<Option<(String, String, i64)>>>,
}

impl Controller for Drawer {
    fn move_order(&mut self, b: &mut Battle, c: &[UnitId], inner: &mut GladiatorBots) -> UnitId {
        self.pass.move_order(b, c, inner)
    }
    fn movement(&mut self, b: &mut Battle, mover: UnitId, other: UnitId, mf: bool, standup_mp: Option<i64>, edge: Option<&[String]>, inner: &mut GladiatorBots) -> (Option<btsim_core::ranged_combat::Pick>, String, PathGate) {
        if self.drawn.borrow().is_none() && standup_mp.is_none() && edge.is_none() && !b.units[mover].prone {
            if let Some(uw) = UnitWalk::of(b, mover) {
                let start = (uw.start.0, uw.start.1);
                let xy: Vec<(i64, i64)> = b.board.hexes.keys().filter_map(|k| hex_geometry::parse_hex_label(k).ok()).collect();
                for &w in xy.iter().filter(|&&w| (2..=3).contains(&los::hex_distance(start, w))) {
                    let Ok(c1) = chain(b, &uw, &[w]) else { continue };
                    for e in reach(b, &uw, &c1).iter().filter(|e| e.mode == "Walk" && e.state.0 != w.0 && (2..=3).contains(&los::hex_distance(w, (e.state.0, e.state.1)))) {
                        let t = (e.state.0, e.state.1);
                        let Ok(d) = finish(b, mover, &[w, t], e.state.2, "Walk") else { continue };
                        // a route other than the engine's own cheapest way to the same end hex
                        let Ok(direct) = chain(b, &uw, &[t]) else { continue };
                        let Some((_, direct_steps)) = replay(b, &uw, &direct.path) else { continue };
                        if direct_steps == *d.pick.route.as_ref().unwrap() {
                            continue;
                        }
                        let path = path_of_steps(b, &uw, d.pick.route.as_ref().unwrap()).unwrap();
                        let text = btsim_core::step_walk::route_text(&path, uw.start.2);
                        *self.drawn.borrow_mut() = Some((text, d.pick.hex.clone(), d.pick.mp_spent));
                        let gate = PathGate { psrs: Some(d.psrs), hazard: Some(d.hazard) };
                        return (Some(d.pick), "drawn by the test".into(), gate);
                    }
                }
            }
        }
        self.pass.movement(b, mover, other, mf, standup_mp, edge, inner)
    }
    fn target(&mut self, b: &mut Battle, a: UnitId, inner: &mut GladiatorBots) -> Option<UnitId> {
        self.pass.target(b, a, inner)
    }
    fn declaration(&mut self, b: &mut Battle, ctx: &btsim_core::attack_resolution::DeclCtx, p: &mut btsim_core::fire_modes::Planner, a: UnitId, t: UnitId, inner: &mut GladiatorBots) -> btsim_core::attack_resolution::DeclChoice {
        self.pass.declaration(b, ctx, p, a, t, inner)
    }
    fn physical(&mut self, b: &mut Battle, a: UnitId, t: UnitId, inner: &mut GladiatorBots) -> btsim_core::human_bots::PhysicalChoice {
        self.pass.physical(b, a, t, inner)
    }
}

#[test]
fn the_unit_walks_the_route_as_drawn() {
    let sc = two_v_two("walk");
    let drawn = Rc::new(RefCell::new(None));
    let mut human = HumanBots::new(Drawer { pass: PassThrough, drawn: drawn.clone() }, [0usize, 2]);
    let mut b = sc.battle(Box::new(PcgDice::new(7)));
    b.events_on();
    let mut marks = |_: &mut Battle, _: i64, _: &str| {};
    let mut play = start_battle(&mut b, sc.max_turns, &mut marks);
    play_on(&mut b, &mut human, &mut play, &mut marks);
    let (text, hex, mp) = drawn.borrow().clone().expect("a route was drawn");
    let events = btsim_core::events::events_json(&b);
    let events = events.as_array().unwrap();
    let at = events.iter().position(|e| e["k"] == "MOVE_PATH" && e["w"].as_str() == Some(text.as_str())).expect("the engine's MOVE_PATH shows the route that was drawn, step for step");
    let mv = &events[at - 1];
    assert_eq!((mv["k"].as_str(), mv["w"].as_str(), mv["n"].as_i64()), (Some("MOVE"), Some(hex.as_str()), Some(mp)), "the unit ended where the drawn route ends, having spent its MP");
    eprintln!("drawn_route: the drawn route {} was walked", text);
}
