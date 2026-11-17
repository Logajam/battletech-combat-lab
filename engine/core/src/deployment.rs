// Translated from INTEGRATION__deployment.py (session 22): where a mech may start its movement when it enters from its
// home edge.
use crate::fasthash::{HashMap, HashSet};
use std::collections::{VecDeque};

use crate::battle::{Battle, UnitId};
use crate::hex_geometry;
use crate::mech_state::*;
use crate::terrain_rules;
use crate::water;

pub const EDGE_NAMES: [&str; 4] = ["N", "E", "S", "W"];

pub fn opposite_edge(e: &str) -> &'static str {
    match e {
        "N" => "S",
        "S" => "N",
        "E" => "W",
        _ => "E",
    }
}

/// Hex labels 0..depth hexes in from `edge`, edge row first.
pub fn band(b: &Battle, edge: &str, depth: i64) -> Vec<String> {
    let (w, h) = (b.board.width, b.board.height);
    let mut labels: Vec<String> = Vec::new();
    for k in 0..=depth {
        if edge == "N" || edge == "S" {
            let row = if edge == "N" { 1 + k } else { h - k };
            if 1 <= row && row <= h {
                labels.extend((1..=w).map(|c| format!("{:02}{:02}", c, row)));
            }
        } else {
            let col = if edge == "W" { 1 + k } else { w - k };
            if 1 <= col && col <= w {
                labels.extend((1..=h).map(|r| format!("{:02}{:02}", col, r)));
            }
        }
    }
    labels.into_iter().filter(|l| b.board.hexes.contains_key(l)).collect()
}

fn jump_mp_at(b: &Battle, u: UnitId, label: &str) -> i64 {
    let m = &b.units[u];
    let st = water::state_at(&b.board, Some(label), false, is_superheavy(m));
    match water::jump_mp_lost(b, u, Some(st)) {
        None => 0,
        Some(lost) => 0.max(compute_jump_mp(m) - lost),
    }
}

fn neighbours(b: &Battle, label: &str) -> Vec<String> {
    let (x, y) = hex_geometry::parse_hex_label(label).unwrap();
    hex_geometry::FACING_DELTAS.iter().filter_map(|(dx, dy)| hex_geometry::hex_label(x + dx, y + dy).ok()).filter(|n| b.board.hexes.contains_key(n)).collect()
}

fn moves(b: &Battle, u: UnitId, label: &str, level_limit: terrain_rules::GroundLimit, jumping: bool) -> HashSet<String> {
    let info = &b.board.hexes[label];
    let mut out = HashSet::default();
    for n in neighbours(b, label) {
        if terrain_rules::step_cost(Some(info), &b.board.hexes[&n], level_limit, false).is_some() {
            out.insert(n);
        }
    }
    let jump = if jumping { jump_mp_at(b, u, label) } else { 0 };
    if jump > 0 {
        let (x, y) = hex_geometry::parse_hex_label(label).unwrap();
        for (sx, sy, _f) in crate::combat::build_jump_states(&b.board, x, y, jump).unwrap().keys() {
            out.insert(hex_geometry::hex_label(*sx, *sy).unwrap());
        }
    }
    out
}

/// Can this unit get from `start` to any hex in `goal`, over as many turns as it likes?
pub fn reaches(b: &Battle, u: UnitId, start: &str, goal: &HashSet<String>, cache: &mut HashMap<(String, bool), HashSet<String>>) -> bool {
    let m = &b.units[u];
    let level_limit = terrain_rules::max_level_change(ground_level_limited(m), is_superheavy(m));
    for jumping in [false, true] {
        if jumping && compute_jump_mp(m) <= 0 {
            break;
        }
        let mut seen: HashSet<String> = HashSet::default();
        seen.insert(start.to_string());
        let mut queue: VecDeque<String> = VecDeque::new();
        queue.push_back(start.to_string());
        while let Some(here) = queue.pop_front() {
            if goal.contains(&here) {
                return true;
            }
            let key = (here.clone(), jumping);
            if !cache.contains_key(&key) {
                cache.insert(key.clone(), moves(b, u, &here, level_limit, jumping));
            }
            for nxt in cache[&key].iter() {
                if seen.insert(nxt.clone()) {
                    queue.push_back(nxt.clone());
                }
            }
        }
    }
    false
}

pub struct StartHexes {
    pub hexes: Vec<String>,
    pub depth: i64,
    pub stuck: Vec<String>,
}

pub fn start_hexes(b: &Battle, u: UnitId, edge: &str) -> StartHexes {
    let dd = b.cfg.i("DEPLOYMENT_DEPTH");
    let sd = b.cfg.i("DEPLOYMENT_STUCK_DEPTH");
    let far: HashSet<String> = band(b, opposite_edge(edge), sd.max(dd)).into_iter().collect();
    let mut good_cache: HashMap<String, bool> = HashMap::default();
    let mut moves_cache: HashMap<(String, bool), HashSet<String>> = HashMap::default();
    let mut usable = |depth: i64| -> (Vec<String>, Vec<String>) {
        let (mut ok, mut stuck) = (Vec::new(), Vec::new());
        for label in band(b, edge, depth) {
            if terrain_rules::step_cost(None, &b.board.hexes[&label], terrain_rules::max_level_change(false, false), false).is_none() {
                continue;
            }
            if !good_cache.contains_key(&label) {
                let g = reaches(b, u, &label, &far, &mut moves_cache);
                good_cache.insert(label.clone(), g);
            }
            if good_cache[&label] {
                ok.push(label);
            } else {
                stuck.push(label);
            }
        }
        (ok, stuck)
    };
    let mut depth = dd;
    let (mut ok, mut stuck) = usable(depth);
    if ok.is_empty() && sd > depth {
        depth = sd;
        let r = usable(depth);
        ok = r.0;
        stuck = r.1;
    }
    StartHexes { hexes: ok, depth, stuck }
}

// ---- zone deployment (Combat Lab starting zones, session 26; Daniel 2026-11-14) -----------------------------------------
// The board is cut into a 3 x 3 grid of boxes, 0 = north-west ... 8 = south-east (row by row), 4 = the centre. A team's
// zone is any set of boxes; its units either WALK ON (enter from the board's border hexes inside the zone, as the home
// edge deployment does) or are PLACED on hexes of the zone before turn 1. Used only when the setup has a DEPLOY_ZONES
// setting; without it the battle starts exactly as before (initiative roll, home edge).

/// The box (0-8) a hex label falls in: the same thirds the Lab's map preview draws.
pub fn zone_box(b: &Battle, label: &str) -> usize {
    let (w, h) = (b.board.width.max(1), b.board.height.max(1));
    let col: i64 = label[0..2].parse().unwrap_or(1);
    let row: i64 = label[2..4].parse().unwrap_or(1);
    ((((row - 1) * 3 / h).min(2)) * 3 + (((col - 1) * 3 / w).min(2))) as usize
}

/// Every hex of the board that lies in one of the chosen boxes, in board order.
pub fn zone_hexes(b: &Battle, boxes: &[bool; 9]) -> Vec<String> {
    b.board.hexes.keys().filter(|l| boxes[zone_box(b, l)]).cloned().collect()
}

/// The stretches of the border a walk-on zone enters from (Daniel, 2026-11-17: "NEWS should allow entry from that entire side
/// of the map. Corner locations would allow entry up to the half way point of the edge"): a side box (N, E, S, W) = that
/// whole edge; a corner box = the two edges that meet there, each from the corner to its half-way point (on an odd length
/// the middle hex belongs to both halves); the centre box = none. (edge, part): part 0 = the whole edge, 1 = the half with
/// the low hex numbers (north / west end), 2 = the other half.
pub fn entry_segments(boxes: &[bool; 9]) -> Vec<(&'static str, u8)> {
    const BY_BOX: [&[(&str, u8)]; 9] = [
        &[("N", 1), ("W", 1)], &[("N", 0)], &[("N", 2), ("E", 1)],
        &[("W", 0)], &[], &[("E", 0)],
        &[("S", 1), ("W", 2)], &[("S", 0)], &[("S", 2), ("E", 2)],
    ];
    let mut out = Vec::new();
    for (k, on) in boxes.iter().enumerate() {
        if *on {
            out.extend(BY_BOX[k].iter().copied());
        }
    }
    out
}

/// The hexes up to `depth` in from the zone's entry stretches (`entry_segments`), each once, in edge order.
pub fn zone_entry_band(b: &Battle, boxes: &[bool; 9], depth: i64) -> Vec<String> {
    let mut seen: HashSet<String> = HashSet::default();
    let mut out = Vec::new();
    for (edge, part) in entry_segments(boxes) {
        let len = if edge == "N" || edge == "S" { b.board.width } else { b.board.height };
        for label in band(b, edge, depth) {
            // the place along the edge: the column on the north / south edge, the row on the east / west edge
            let along: i64 = if edge == "N" || edge == "S" { label[0..2].parse().unwrap_or(1) } else { label[2..4].parse().unwrap_or(1) };
            let inside = match part { 1 => along * 2 <= len + 1, 2 => along * 2 >= len + 1, _ => true };
            if inside && seen.insert(label.clone()) {
                out.push(label);
            }
        }
    }
    out
}

/// The hexes a unit may walk on from: the zone's entry band (`zone_entry_band`, DEPLOYMENT_DEPTH hexes deep). The depth is widened to DEPLOYMENT_STUCK_DEPTH when nothing within the first depth lets the unit
/// out into the middle of the board (the same "stuck" rule as the home edge). `reach` = the hexes it must be able to get to.
pub fn zone_walk_on(b: &Battle, u: UnitId, boxes: &[bool; 9]) -> StartHexes {
    let dd = b.cfg.i("DEPLOYMENT_DEPTH");
    let sd = b.cfg.i("DEPLOYMENT_STUCK_DEPTH");
    let goal: HashSet<String> = zone_hexes(b, &[false, false, false, false, true, false, false, false, false]).into_iter().collect();
    let mut good_cache: HashMap<String, bool> = HashMap::default();
    let mut moves_cache: HashMap<(String, bool), HashSet<String>> = HashMap::default();
    let mut usable = |depth: i64| -> (Vec<String>, Vec<String>) {
        let (mut ok, mut stuck) = (Vec::new(), Vec::new());
        for label in zone_entry_band(b, boxes, depth) {
            if terrain_rules::step_cost(None, &b.board.hexes[&label], terrain_rules::max_level_change(false, false), false).is_none() {
                continue;
            }
            let g = *good_cache.entry(label.clone()).or_insert_with(|| reaches(b, u, &label, &goal, &mut moves_cache));
            if g { ok.push(label); } else { stuck.push(label); }
        }
        (ok, stuck)
    };
    let mut depth = dd;
    let (mut ok, mut stuck) = usable(depth);
    if ok.is_empty() && sd > depth {
        depth = sd;
        let r = usable(depth);
        ok = r.0;
        stuck = r.1;
    }
    StartHexes { hexes: ok, depth, stuck }
}

/// The border hexes (edge row only) of the zone's entry stretches: what `home_edge_row` holds for a walk-on team.
pub fn zone_edge_row(b: &Battle, boxes: &[bool; 9]) -> Vec<String> {
    zone_entry_band(b, boxes, 0)
}

/// The compass facing that points from a hex toward the middle of the board.
pub fn facing_to_centre(b: &Battle, label: &str) -> &'static str {
    let px = |c: f64, r: f64| (1.5 * c, 3f64.sqrt() * r + if (c as i64) % 2 == 0 { 3f64.sqrt() / 2.0 } else { 0.0 });
    let col: f64 = label[0..2].parse().unwrap_or(1.0);
    let row: f64 = label[2..4].parse().unwrap_or(1.0);
    let (x, y) = px(col, row);
    let (cx, cy) = px(((b.board.width + 1) / 2) as f64, ((b.board.height + 1) / 2) as f64);
    // screen angle of each facing: N up, then clockwise in 60 degree steps
    let angle = (cy - y).atan2(cx - x).to_degrees();
    let mut best = ("N", f64::MAX);
    for (name, a) in [("N", -90.0), ("NE", -30.0), ("SE", 30.0), ("S", 90.0), ("SW", 150.0), ("NW", -150.0)] {
        let mut diff = (angle - a).abs() % 360.0;
        if diff > 180.0 { diff = 360.0 - diff; }
        if diff < best.1 { best = (name, diff); }
    }
    best.0
}

/// Do two hex labels touch (neighbours)?
pub fn hexes_touch(a: &str, b: &str) -> bool {
    let (Ok((ax, ay)), Ok((bx, by))) = (hex_geometry::parse_hex_label(a), hex_geometry::parse_hex_label(b)) else { return false };
    hex_geometry::FACING_DELTAS.iter().any(|(dx, dy)| ax + dx == bx && ay + dy == by)
}
