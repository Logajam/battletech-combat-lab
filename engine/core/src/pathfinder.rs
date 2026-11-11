// Translated from pathfinder/pathfinder.py (session 22). No caches yet (RUST_PORT trap 9): `_BoardCache`, the
// finished-table cache and `forget_board` are speed only and come back in stage 9.
//! The DP engine: the table of (x, y, facing, mp_spent) -> most forward moves achievable landing in that state.

use crate::fasthash::HashSet;

use crate::fasthash::IndexMap;

use crate::board_parser::Board;
use crate::hex_geometry::{hex_label, State, FACING_DELTAS};
use crate::terrain_rules::{self, GroundLimit};

pub type Hex = (i64, i64);

/// state -> {mp_spent: max forward_count}, in the Python dict's insertion order. With `psrs` set it is a PathTable.
#[derive(Clone, Debug, Default)]
pub struct MovementTable {
    pub entries: IndexMap<State, IndexMap<i64, i64>>,
    /// PathTable: psrs[state][mp] = (always, run_only)
    pub psrs: Option<IndexMap<State, IndexMap<i64, (i64, i64)>>>,
    /// PathTable: expected damage of the hexes entered
    pub hazards: IndexMap<State, IndexMap<i64, f64>>,
    /// PathTable with keep_parents: {(search key, mp): (previous key, previous mp, step)}
    pub parents: Option<IndexMap<(SearchKey, i64), (SearchKey, i64, &'static str)>>,
    /// PathTable: {(state, mp): the search key that won the table entry}
    pub best_keys: IndexMap<(State, i64), SearchKey>,
}

/// (x, y, facing, last direction (0 none, +1 forward, -1 backward), moved backward yet)
pub type SearchKey = (i64, i64, i64, i64, bool);

fn record(table: &mut MovementTable, state: State, mp: i64, forward_count: i64) {
    let col = table.entries.entry(state).or_default();
    match col.get(&mp) {
        Some(&old) if forward_count <= old => {}
        _ => {
            col.insert(mp, forward_count);
        }
    }
}

/// Phase 1: uniform 1-MP layered sweep, unbounded plane.
fn build_flat(start_x: i64, start_y: i64, start_facing: i64, mp_budget: i64) -> MovementTable {
    let mut table = MovementTable::default();
    let start_state = (start_x, start_y, start_facing);
    record(&mut table, start_state, 0, 0);
    let mut layer: IndexMap<State, i64> = IndexMap::default();
    layer.insert(start_state, 0);
    for mp in 0..mp_budget {
        let mut next_layer: IndexMap<State, i64> = IndexMap::default();
        let mut push = |state: State, forward_count: i64, next_layer: &mut IndexMap<State, i64>| match next_layer.get(&state) {
            Some(&e) if forward_count <= e => {}
            _ => {
                next_layer.insert(state, forward_count);
            }
        };
        for (&(x, y, facing), &fc) in layer.iter() {
            let (dx, dy) = FACING_DELTAS[facing as usize];
            push((x + dx, y + dy, facing), fc + 1, &mut next_layer);
            push((x, y, (facing - 1).rem_euclid(6)), fc, &mut next_layer);
            push((x, y, (facing + 1).rem_euclid(6)), fc, &mut next_layer);
        }
        for (&state, &fc) in next_layer.iter() {
            record(&mut table, state, mp + 1, fc);
        }
        layer = next_layer;
    }
    table
}

/// `hex_info(x, y)`: None for a blocked hex or one off the board.
fn hex_info<'a>(board: &'a Board, blocked: &HashSet<Hex>, x: i64, y: i64) -> Option<&'a crate::board_parser::Hex> {
    if blocked.contains(&(x, y)) {
        return None;
    }
    board.info_xy(x, y)
}

fn start_label(x: i64, y: i64) -> Result<String, String> {
    Ok(crate::pyfmt::py_repr_str(&hex_label(x, y)?))
}

/// Phase 2: bucket-queue (Dial's algorithm) sweep, board-edge bounded; backward moves when `backward_mp` is given.
fn build_terrain_aware(
    start_x: i64,
    start_y: i64,
    start_facing: i64,
    mp_budget: i64,
    board: &Board,
    backward_mp: Option<i64>,
    level_limit: GroundLimit,
    blocked: &HashSet<Hex>,
) -> Result<MovementTable, String> {
    let mut table = MovementTable::default();
    let start_info = match hex_info(board, blocked, start_x, start_y) {
        Some(i) => i,
        None => {
            return Err(format!(
                "Start hex {} is not on the loaded board \u{2014} can't build a movement table from an off-board start.",
                start_label(start_x, start_y)?
            ))
        }
    };
    if start_info.impassable {
        return Err(format!("Start hex {} is marked impassable.", start_label(start_x, start_y)?));
    }
    let start_key: SearchKey = (start_x, start_y, start_facing, 0, false);
    let mut buckets: IndexMap<i64, IndexMap<SearchKey, i64>> = IndexMap::default();
    buckets.entry(0).or_default().insert(start_key, 0);

    fn push(buckets: &mut IndexMap<i64, IndexMap<SearchKey, i64>>, mp: i64, key: SearchKey, fc: i64) {
        let b = buckets.entry(mp).or_default();
        if *b.get(&key).unwrap_or(&-1) < fc {
            b.insert(key, fc);
        }
    }

    for mp in 0..=mp_budget {
        let bucket = match buckets.get(&mp) {
            Some(b) if !b.is_empty() => b.clone(),
            _ => continue,
        };
        for (&(x, y, facing, last, used_back), &fc) in bucket.iter() {
            record(&mut table, (x, y, facing), mp, fc);
            let budget = if used_back { backward_mp.unwrap_or(mp_budget) } else { mp_budget };
            let current_info = match hex_info(board, blocked, x, y) {
                Some(i) => i,
                None => continue,
            };
            let (dx, dy) = FACING_DELTAS[facing as usize];

            // 1. Forward move
            if let Some(dest) = hex_info(board, blocked, x + dx, y + dy) {
                let _ = dest;
                let cost = terrain_rules::step_cost(board.info_xy(x, y), board.info_xy(x + dx, y + dy).unwrap(), level_limit, false);
                if let Some(cost) = cost {
                    if mp + cost <= budget {
                        push(&mut buckets, mp + cost, (x + dx, y + dy, facing, 1, used_back), if last >= 0 { fc + 1 } else { 1 });
                    }
                }
            }
            // 2. Backward move (walking only, same level only)
            if let Some(bmp) = backward_mp {
                if let Some(dest) = hex_info(board, blocked, x - dx, y - dy) {
                    if dest.level == current_info.level {
                        let cost = terrain_rules::step_cost(board.info_xy(x, y), dest, level_limit, true);
                        if let Some(cost) = cost {
                            if mp + cost <= bmp {
                                push(&mut buckets, mp + cost, (x - dx, y - dy, facing, -1, true), if last <= 0 { fc + 1 } else { 1 });
                            }
                        }
                    }
                }
            }
            // 3. / 4. Turning
            if mp + 1 <= budget {
                for new_facing in [(facing - 1).rem_euclid(6), (facing + 1).rem_euclid(6)] {
                    push(&mut buckets, mp + 1, (x, y, new_facing, last, used_back), fc);
                }
            }
        }
    }
    Ok(table)
}

type PsrValue = (f64, i64, i64, i64, i64); // (-hazard, forward_count, -total PSRs, always, run_only)

/// `_build_terrain_aware` on a board where steps can force terrain PSRs; entries carry PSR counts, hazards, and
/// (keep_parents) the path.
fn build_terrain_psr(
    start_x: i64,
    start_y: i64,
    start_facing: i64,
    mp_budget: i64,
    board: &Board,
    backward_mp: Option<i64>,
    level_limit: GroundLimit,
    keep_parents: bool,
    blocked: &HashSet<Hex>,
) -> Result<MovementTable, String> {
    let hazardous = terrain_rules::has_hazard_terrain(board);
    let board_hazard = |x: i64, y: i64| -> f64 {
        if hazardous {
            terrain_rules::step_hazard(board.info_xy(x, y).unwrap(), 2)
        } else {
            0.0
        }
    };
    // (cost, always, run_only) of the step; cost None if it isn't allowed
    let board_extra = |fx: i64, fy: i64, tx: i64, ty: i64, backward: bool| -> (Option<i64>, i64, i64) {
        let (here, there) = (board.info_xy(fx, fy), board.info_xy(tx, ty).unwrap());
        let cost = terrain_rules::step_cost(here, there, level_limit, backward);
        match cost {
            None => (None, 0, 0),
            Some(c) => {
                let (a, r) = terrain_rules::step_psrs(here, there, backward);
                (Some(c), a, r)
            }
        }
    };

    let mut table = MovementTable::default();
    table.psrs = Some(IndexMap::default());
    if keep_parents {
        table.parents = Some(IndexMap::default());
    }
    if hex_info(board, blocked, start_x, start_y).is_none() {
        return Err(format!("Start hex {} is not on the loaded board.", start_label(start_x, start_y)?));
    }
    let start_key: SearchKey = (start_x, start_y, start_facing, 0, false);
    let mut buckets: IndexMap<i64, IndexMap<SearchKey, PsrValue>> = IndexMap::default();
    buckets.entry(0).or_default().insert(start_key, (0.0, 0, 0, 0, 0));

    #[allow(clippy::too_many_arguments)]
    fn push(
        buckets: &mut IndexMap<i64, IndexMap<SearchKey, PsrValue>>,
        parents: &mut Option<IndexMap<(SearchKey, i64), (SearchKey, i64, &'static str)>>,
        mp: i64,
        key: SearchKey,
        value: PsrValue,
        prev_key: SearchKey,
        prev_mp: i64,
        step: &'static str,
    ) {
        let b = buckets.entry(mp).or_default();
        let better = match b.get(&key) {
            None => true,
            Some(old) => (value.0, value.1, value.2) > (old.0, old.1, old.2) && cmp3_greater(&value, old),
        };
        if better {
            b.insert(key, value);
            if let Some(p) = parents.as_mut() {
                p.insert((key, mp), (prev_key, prev_mp, step));
            }
        }
    }
    // Python compares the tuples value[:3] > old[:3]: lexicographic on (f64, i64, i64)
    fn cmp3_greater(a: &PsrValue, b: &PsrValue) -> bool {
        if a.0 != b.0 {
            return a.0 > b.0;
        }
        if a.1 != b.1 {
            return a.1 > b.1;
        }
        a.2 > b.2
    }

    for mp in 0..=mp_budget {
        let bucket = match buckets.get(&mp) {
            Some(b) if !b.is_empty() => b.clone(),
            _ => continue,
        };
        for (&key, &value) in bucket.iter() {
            let (x, y, facing, last, used_back) = key;
            let (hz, fc, neg, always, run_only) = value;
            let state = (x, y, facing);
            let col = table.entries.entry(state).or_default();
            let replace = match col.get(&mp) {
                None => true,
                Some(&col_fc) => {
                    let old_hz = -table.hazards[&state][&mp];
                    let old_neg = {
                        let (a, r) = table.psrs.as_ref().unwrap()[&state][&mp];
                        -(a + r)
                    };
                    // (hz, fc, neg) > (old_hz, col_fc, old_neg), tuple comparison
                    if hz != old_hz {
                        hz > old_hz
                    } else if fc != col_fc {
                        fc > col_fc
                    } else {
                        neg > old_neg
                    }
                }
            };
            if replace {
                table.entries.get_mut(&state).unwrap().insert(mp, fc);
                table.psrs.as_mut().unwrap().entry(state).or_default().insert(mp, (always, run_only));
                table.hazards.entry(state).or_default().insert(mp, if hz != 0.0 { -hz } else { 0.0 });
                table.best_keys.insert((state, mp), key);
            }
            let budget = if used_back { backward_mp.unwrap_or(mp_budget) } else { mp_budget };
            let _current_info = hex_info(board, blocked, x, y);
            let (dx, dy) = FACING_DELTAS[facing as usize];

            // 1. Forward move.
            if hex_info(board, blocked, x + dx, y + dy).is_some() {
                let (cost, a, r) = board_extra(x, y, x + dx, y + dy, false);
                if let Some(cost) = cost {
                    if mp + cost <= budget {
                        push(
                            &mut buckets,
                            &mut table.parents,
                            mp + cost,
                            (x + dx, y + dy, facing, 1, used_back),
                            (hz - board_hazard(x + dx, y + dy), if last >= 0 { fc + 1 } else { 1 }, neg - a - r, always + a, run_only + r),
                            key,
                            mp,
                            "forward",
                        );
                    }
                }
            }
            // 2. Backward move (walking only; a level change costs a PSR).
            if let Some(bmp) = backward_mp {
                if hex_info(board, blocked, x - dx, y - dy).is_some() {
                    let (cost, a, r) = board_extra(x, y, x - dx, y - dy, true);
                    if let Some(cost) = cost {
                        if mp + cost <= bmp {
                            push(
                                &mut buckets,
                                &mut table.parents,
                                mp + cost,
                                (x - dx, y - dy, facing, -1, true),
                                (hz - board_hazard(x - dx, y - dy), if last <= 0 { fc + 1 } else { 1 }, neg - a - r, always + a, run_only + r),
                                key,
                                mp,
                                "backward",
                            );
                        }
                    }
                }
            }
            // 3. / 4. Turning (mud: a PSR if running, p.124).
            if mp + 1 <= budget {
                let (a, r) = terrain_rules::turn_psrs(board.info_xy(x, y).unwrap());
                for new_facing in [(facing - 1).rem_euclid(6), (facing + 1).rem_euclid(6)] {
                    push(
                        &mut buckets,
                        &mut table.parents,
                        mp + 1,
                        (x, y, new_facing, last, used_back),
                        (hz, fc, neg - a - r, always + a, run_only + r),
                        key,
                        mp,
                        "turn",
                    );
                }
            }
        }
    }
    Ok(table)
}

impl MovementTable {
    /// PathTable.path: [(step, (x, y, facing), mp after)] from the start to `state` at `mp` (needs keep_parents).
    pub fn path(&self, state: State, mp: i64) -> Vec<(&'static str, State, i64)> {
        let parents = self.parents.as_ref().expect("keep_parents");
        let mut key = self.best_keys[&(state, mp)];
        let mut mp = mp;
        let mut out = Vec::new();
        while let Some(&(prev_key, prev_mp, step)) = parents.get(&(key, mp)) {
            out.push((step, (key.0, key.1, key.2), mp));
            key = prev_key;
            mp = prev_mp;
        }
        out.reverse();
        out
    }
}

/// `build_movement_table`: `blocked` = hexes no ground step may enter (a mobile enemy's), `board` None = the flat
/// plane. Python caches finished tables; this does not (stage 9).
#[allow(clippy::too_many_arguments)]
pub fn build_movement_table(
    start_x: i64,
    start_y: i64,
    start_facing: i64,
    mp_budget: i64,
    board: Option<&Board>,
    backward_mp: Option<i64>,
    level_limit: GroundLimit,
    keep_parents: bool,
    blocked: &HashSet<Hex>,
) -> Result<MovementTable, String> {
    if !(0..=5).contains(&start_facing) {
        return Err(format!("start_facing must be 0-5, got {}", start_facing));
    }
    if mp_budget < 0 {
        return Err("mp_budget must be non-negative".to_string());
    }
    let board = match board {
        None => return Ok(build_flat(start_x, start_y, start_facing, mp_budget)),
        Some(b) => b,
    };
    if keep_parents {
        return build_terrain_psr(start_x, start_y, start_facing, mp_budget, board, backward_mp, level_limit, true, blocked);
    }
    if terrain_rules::has_psr_terrain(board) {
        build_terrain_psr(start_x, start_y, start_facing, mp_budget, board, backward_mp, level_limit, false, blocked)
    } else {
        build_terrain_aware(start_x, start_y, start_facing, mp_budget, board, backward_mp, level_limit, blocked)
    }
}

/// Every (x, y, facing) reachable at all.
pub fn query_envelope(table: &MovementTable) -> Vec<State> {
    table.entries.keys().cloned().collect()
}

/// For each reachable (x, y, facing), the highest forward-count achievable across all mp_spent values.
pub fn query_max_forward_count(table: &MovementTable) -> IndexMap<State, i64> {
    table.entries.iter().map(|(s, col)| (*s, *col.values().max().unwrap())).collect()
}
