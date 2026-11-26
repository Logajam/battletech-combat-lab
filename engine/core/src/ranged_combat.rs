// Translated from INTEGRATION__ranged_combat.py (session 22). Part 1 (the engine's): the ground path to a picked end
// state (`path_to`) and the terrain PSRs / hazard damage the search noted for it (`path_notes`), which gate the
// movement subphase. The scoring (MoveEvaluator, option lists) follows with the bots.
use crate::fasthash::HashSet;

use serde_json::Value;

use crate::battle::{Battle, UnitId};
use crate::combat::classify_movement_mode;
use crate::hex_geometry::{self, State};
use crate::mech_state::*;
use crate::pathfinder::{build_movement_table, Hex};
use crate::terrain_rules;

/// The picked end state: {"hex", "facing", "mode", "fc", "mp_spent"}.
#[derive(Clone, Debug, PartialEq)]
pub struct Pick {
    pub hex: String,
    pub facing: String,
    pub mode: String,
    pub fc: i64,
    pub mp_spent: i64,
    pub charge: bool,
    pub dfa: bool,
    /// A route drawn by a person (waypoints): the unit walks exactly these steps, rolling each PSR and hazard where the route puts it
    /// (`drawn_route.rs`, `orchestrator::walk_path`). None: the engine picks its own best route to the end state (every bot).
    pub route: Option<Vec<crate::step_walk::Step>>,
}

/// pathfinder._blocked_set(mover.blocked_hex): None, one (x, y), or a set of them.
pub fn blocked_set(v: &Option<Value>) -> HashSet<Hex> {
    let mut out = HashSet::default();
    match v {
        Some(Value::Array(a)) if !a.is_empty() => {
            if a[0].is_i64() {
                out.insert((a[0].as_i64().unwrap(), a[1].as_i64().unwrap()));
            } else {
                for p in a {
                    out.insert((p[0].as_i64().unwrap(), p[1].as_i64().unwrap()));
                }
            }
        }
        _ => {}
    }
    out
}

/// Minimum Movement (p.49): a 'Mech with at least 1 MP may run into the hex directly in front of it even without the
/// MP it would normally cost. Returns the (x, y, facing, fc, mode, mp_spent) state or None.
pub fn minimum_move(b: &Battle, u: UnitId, sx: i64, sy: i64, facing: i64, run_budget: i64, seen: &HashSet<(i64, i64, i64, i64, String, i64)>, level_limit: terrain_rules::GroundLimit) -> Option<(i64, i64, i64, i64, String, i64)> {
    if run_budget < 1 {
        return None;
    }
    let (dx, dy) = hex_geometry::FACING_DELTAS[facing as usize];
    let (fx, fy) = (sx + dx, sy + dy);
    let blocked = blocked_set(&b.units[u].blocked_hex);
    if blocked.contains(&(fx, fy)) {
        return None;
    }
    let label = hex_geometry::hex_label(fx, fy).ok()?;
    let info = b.board.hexes.get(&label)?;
    let here = &b.board.hexes[b.units[u].hex.as_deref().unwrap()];
    let cost = terrain_rules::step_cost(Some(here), info, level_limit, false)?;
    if cost <= run_budget {
        return None;
    }
    let key = (fx, fy, facing, 1, "Run".to_string(), run_budget);
    if seen.contains(&key) {
        return None;
    }
    Some(key)
}

/// The ground path to a picked end state: [(step, (x, y, facing), mp after)] - step "enter" (onto the board, first),
/// "forward", "backward" or "turn" - or None when no such path is found.
pub type TableCache = crate::fasthash::HashMap<(i64, i64, i64, i64, Option<i64>), crate::pathfinder::MovementTable>;

pub fn path_to(b: &Battle, u: UnitId, pick: &Pick, standup_mp: Option<i64>, entry_edge: Option<&[String]>) -> Option<Vec<(&'static str, State, i64)>> {
    path_to_cached(b, u, pick, standup_mp, entry_edge, &mut TableCache::default())
}

/// path_to, plus the facing the route starts from: for a unit standing up, the facing it chose as it stood (Core:
/// any facing, free), which the route's steps do not show (the MegaMek bridge sends it as turns after GET_UP).
pub fn path_to_with_start(b: &Battle, u: UnitId, pick: &Pick, standup_mp: Option<i64>) -> Option<(i64, Vec<(&'static str, State, i64)>)> {
    let m = &b.units[u];
    let (sx, sy, start_facing) = hex_geometry::state_from_label(m.hex.as_deref()?, &m.facing).ok()?;
    let path = path_to(b, u, pick, standup_mp, None)?;
    if standup_mp.is_none() {
        return Some((start_facing, path));
    }
    // which stand-up facing the route was found from: the one whose table holds the pick at that cost
    let blocked = blocked_set(&m.blocked_hex);
    let (x, y) = hex_geometry::parse_hex_label(&pick.hex).unwrap();
    let state: State = (x, y, hex_geometry::compass_to_facing(&pick.facing).unwrap());
    let level_limit = crate::mech_state::ground_limit(m);
    for f0 in 0..6 {
        let table = build_movement_table(sx, sy, f0, standup_mp.unwrap(), Some(&b.board), None, level_limit, true, &blocked).unwrap();
        if table.entries.get(&state).and_then(|c| c.get(&pick.mp_spent)) == Some(&pick.fc) {
            return Some((f0, path));
        }
    }
    Some((start_facing, path))
}

/// path_to with the searched tables kept in `cache` (PathBook): asking for many picks from one spot searches once.
pub fn path_to_cached(b: &Battle, u: UnitId, pick: &Pick, standup_mp: Option<i64>, entry_edge: Option<&[String]>, cache: &mut TableCache) -> Option<Vec<(&'static str, State, i64)>> {
    let m = &b.units[u];
    let blocked = blocked_set(&m.blocked_hex);
    let (x, y) = hex_geometry::parse_hex_label(&pick.hex).unwrap();
    let state: State = (x, y, hex_geometry::compass_to_facing(&pick.facing).unwrap());
    let (fc, mp) = (pick.fc, pick.mp_spent);
    let level_limit = crate::mech_state::ground_limit(m);
    let mut table_for = |x0: i64, y0: i64, f0: i64, budget: i64, backward_mp: Option<i64>| -> *const crate::pathfinder::MovementTable {
        let e = cache.entry((x0, y0, f0, budget, backward_mp)).or_insert_with(|| build_movement_table(x0, y0, f0, budget, Some(&b.board), backward_mp, level_limit, true, &blocked).unwrap());
        e as *const _
    };
    if let Some(edge) = entry_edge {
        let run = compute_running_mp(m);
        for label in edge {
            let info = b.board.hexes.get(label);
            let cost = info.and_then(|i| terrain_rules::step_cost(None, i, terrain_rules::max_level_change(false, false), false));
            let Some(cost) = cost.filter(|c| *c <= mp) else { continue };
            let (ex, ey) = hex_geometry::parse_hex_label(label).unwrap();
            if blocked.contains(&(ex, ey)) {
                // An enemy stands on this edge hex: nothing enters there (the options and path_notes skip it too).
                // The Python has no such check and raises ValueError here ("Start hex ... is not on the loaded
                // board") - found by a random batch, RUST_PORT "Found on the way" 9.
                continue;
            }
            for f0 in 0..6 {
                let table = unsafe { &*table_for(ex, ey, f0, run - cost, None) };
                if table.entries.get(&state).and_then(|c| c.get(&(mp - cost))) == Some(&(fc - 1)) {
                    let mut out = vec![("enter", (ex, ey, f0), cost)];
                    out.extend(table.path(state, mp - cost).into_iter().map(|(s, st, mm)| (s, st, mm + cost)));
                    return Some(out);
                }
            }
        }
        return None;
    }
    let (sx, sy, start_facing) = hex_geometry::state_from_label(m.hex.as_deref().unwrap(), &m.facing).unwrap();
    let (starts, budget, backward_mp): (Vec<i64>, i64, Option<i64>) = match standup_mp {
        None => {
            let walk = compute_walk_mp(m);
            (vec![start_facing], compute_running_mp(m), if walk > 0 { Some(walk) } else { None })
        }
        Some(s) => ((0..6).collect(), s, None),
    };
    if standup_mp.is_none() {
        let (dx, dy) = hex_geometry::FACING_DELTAS[start_facing as usize];
        if fc == 1 && pick.mode == "Run" && state == (sx + dx, sy + dy, start_facing) && mp == budget && minimum_move(b, u, sx, sy, start_facing, budget, &HashSet::default(), level_limit).is_some() {
            return Some(vec![("forward", state, mp)]);
        }
    }
    for f0 in starts {
        let table = unsafe { &*table_for(sx, sy, f0, budget, backward_mp) };
        if table.entries.get(&state).and_then(|c| c.get(&mp)) == Some(&fc) {
            return Some(table.path(state, mp));
        }
    }
    None
}

/// What the movement search noted for the pick's state: (terrain PSRs - the fewest over the searches that reach it, in
/// the pick's mode - and the hazard damage, the least). The orchestrator's movement subphase rolls them (`mover.
/// path_psrs[key]` / `mover.path_hazard[key]`, the Python's search tables).
pub fn path_notes(b: &Battle, u: UnitId, pick: &Pick, standup_mp: Option<i64>, entry_edge: Option<&[String]>) -> (Option<i64>, Option<f64>) {
    let m = &b.units[u];
    let blocked = blocked_set(&m.blocked_hex);
    let (x, y) = hex_geometry::parse_hex_label(&pick.hex).unwrap();
    let facing = hex_geometry::compass_to_facing(&pick.facing).unwrap();
    let level_limit = crate::mech_state::ground_limit(m);
    let (mut psrs, mut hazard): (Option<i64>, Option<f64>) = (None, None);
    let note = |psrs: &mut Option<i64>, hazard: &mut Option<f64>, a: i64, r: i64, hz: f64| {
        let n = a + if pick.mode == "Run" { r } else { 0 };
        if psrs.map_or(true, |o| n < o) {
            *psrs = Some(n);
        }
        if hz != 0.0 {
            if hazard.map_or(true, |o| hz < o) {
                *hazard = Some(hz);
            }
        } else if hazard.is_some() {
            *hazard = Some(0.0);
        }
    };
    if let Some(edge) = entry_edge {
        let (walk, run) = (compute_walk_mp(m), compute_running_mp(m));
        for label in edge {
            let Some(info) = b.board.hexes.get(label) else { continue };
            let (ex, ey) = hex_geometry::parse_hex_label(label).unwrap();
            if blocked.contains(&(ex, ey)) {
                continue;
            }
            let cost = terrain_rules::step_cost(None, info, terrain_rules::max_level_change(false, false), false);
            let Some(cost) = cost.filter(|c| *c <= run) else { continue };
            let (ea, er) = terrain_rules::step_psrs(None, info, false);
            let eh = terrain_rules::step_hazard(info, 2);
            for f0 in 0..6 {
                let table = b.movement_table(ex, ey, f0, run - cost, None, level_limit, &blocked);
                for ((sx, sy, sf), col) in &table.entries {
                    for (spent, fc) in col {
                        let total = spent + cost;
                        if (*sx, *sy, *sf) == (x, y, facing) && fc + 1 == pick.fc && classify_movement_mode(total, walk) == pick.mode && total == pick.mp_spent {
                            if let Some(p) = &table.psrs {
                                let (a, r) = p[&(*sx, *sy, *sf)][spent];
                                let hz = table.hazards.get(&(*sx, *sy, *sf)).and_then(|h| h.get(spent)).copied().unwrap_or(0.0);
                                note(&mut psrs, &mut hazard, a + ea, r + er, hz + eh);
                            }
                        }
                    }
                }
            }
        }
        return (psrs, hazard);
    }
    let (sx, sy, start_facing) = hex_geometry::state_from_label(m.hex.as_deref().unwrap(), &m.facing).unwrap();
    let (starts, run_budget, backward_mp, walk): (Vec<i64>, i64, Option<i64>, i64) = match standup_mp {
        None => {
            let walk = compute_walk_mp(m);
            (vec![start_facing], compute_running_mp(m), if walk > 0 { Some(walk) } else { None }, walk)
        }
        Some(s) => ((0..6).collect(), s, None, 0),
    };
    for f0 in starts {
        let table = b.movement_table(sx, sy, f0, run_budget, backward_mp, level_limit, &blocked);
        if let Some(col) = table.entries.get(&(x, y, facing)) {
            for (spent, fc) in col {
                let mode = if standup_mp.is_none() { classify_movement_mode(*spent, walk) } else { "Run" };
                if *fc == pick.fc && mode == pick.mode && *spent == pick.mp_spent {
                    if let Some(p) = &table.psrs {
                        let (a, r) = p[&(x, y, facing)][spent];
                        let hz = table.hazards.get(&(x, y, facing)).and_then(|h| h.get(spent)).copied().unwrap_or(0.0);
                        note(&mut psrs, &mut hazard, a, r, hz);
                    }
                }
            }
        }
    }
    // Minimum Movement's one step notes its own terrain PSRs (when the board has any)
    if standup_mp.is_none() && psrs.is_none() {
        if let Some(key) = minimum_move(b, u, sx, sy, start_facing, run_budget, &HashSet::default(), level_limit) {
            if key == (x, y, facing, pick.fc, pick.mode.clone(), pick.mp_spent) && terrain_rules::has_psr_terrain(&b.board) {
                let here = &b.board.hexes[m.hex.as_deref().unwrap()];
                let info = &b.board.hexes[&pick.hex];
                let (a, r) = terrain_rules::step_psrs(Some(here), info, false);
                note(&mut psrs, &mut hazard, a, r, terrain_rules::step_hazard(info, 2));
            }
        }
    }
    (psrs, hazard)
}
