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
