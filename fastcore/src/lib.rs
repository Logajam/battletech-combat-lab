//! fastcore - compiled hot loops for the BattleTech Monte Carlo simulator (trial, 2026-11-03).
//!
//! Each function here is a copy of a Python function that must give EXACTLY the same answer
//! (the reference logs are compared byte for byte), including how ties are broken and the
//! order floating-point sums are taken in. The Python original stays in the code as the
//! fallback and the specification.

use pyo3::prelude::*;
use std::collections::HashMap;

/// Copy of INTEGRATION__weapon_selection._best_subset_python: the exact 0/1 knapsack of the
/// weapon choice (weight = heat, value = expected damage).
///
/// values / heats: one entry per candidate weapon, in order. Returns (best value, the heat it
/// uses, the indices of the chosen candidates). Same order of work as the Python:
///   - dp maps a heat level to (best value using exactly that heat, chosen set); it starts {0: (0.0, {})};
///   - each candidate in turn visits the heat levels present, highest first, and a STRICTLY
///     better value replaces the entry (a new level is added at the end of the insertion order);
///   - the answer is the first level, in insertion order, holding the highest value
///     (Python's max() over a dict keeps the first of equal values).
/// At most 64 candidates (the chosen set is a bit mask); the caller falls back to Python above that.
#[pyfunction]
fn best_subset(values: Vec<f64>, heats: Vec<i64>, heat_budget: i64) -> PyResult<(f64, i64, Vec<usize>)> {
    let (heat_of, value_of, mask_of) = solve(&values, &heats, heat_budget)?;
    // max(dp, key=value): the first entry in insertion order with the highest value.
    let mut best = 0;
    for k in 1..value_of.len() {
        if value_of[k] > value_of[best] {
            best = k;
        }
    }
    let mask = mask_of[best];
    let picked = (0..values.len()).filter(|&i| mask & (1u64 << i) != 0).collect();
    Ok((value_of[best], heat_of[best], picked))
}

/// Copy of INTEGRATION__weapon_selection.knapsack_levels: the same knapsack as best_subset,
/// returning every heat level it holds as (heat, value, chosen indices), in insertion order
/// (weapon_selection.FireTable answers every smaller heat budget from these).
#[pyfunction]
fn knapsack_levels(values: Vec<f64>, heats: Vec<i64>, heat_budget: i64) -> PyResult<Vec<(i64, f64, Vec<usize>)>> {
    let (heat_of, value_of, mask_of) = solve(&values, &heats, heat_budget)?;
    Ok((0..heat_of.len())
        .map(|k| (heat_of[k], value_of[k], (0..values.len()).filter(|&i| mask_of[k] & (1u64 << i) != 0).collect()))
        .collect())
}

/// The knapsack both functions share: (heat, value, chosen mask) per level, in insertion order.
fn solve(values: &[f64], heats: &[i64], heat_budget: i64) -> PyResult<(Vec<i64>, Vec<f64>, Vec<u64>)> {
    if values.len() != heats.len() || values.len() > 64 {
        return Err(pyo3::exceptions::PyValueError::new_err("knapsack: bad candidate lists"));
    }
    let mut heat_of: Vec<i64> = vec![0];
    let mut value_of: Vec<f64> = vec![0.0];
    let mut mask_of: Vec<u64> = vec![0];
    let mut slot: HashMap<i64, usize> = HashMap::with_capacity(32);
    slot.insert(0, 0);
    let mut levels: Vec<i64> = Vec::with_capacity(32);
    for (i, (&ed, &cost)) in values.iter().zip(heats.iter()).enumerate() {
        levels.clear();
        levels.extend_from_slice(&heat_of);
        levels.sort_unstable_by(|a, b| b.cmp(a));
        for &used in levels.iter() {
            let new_heat = used + cost;
            if new_heat > heat_budget {
                continue;
            }
            let from = slot[&used];
            let new_value = value_of[from] + ed;
            let new_mask = mask_of[from] | (1u64 << i);
            match slot.get(&new_heat) {
                None => {
                    slot.insert(new_heat, heat_of.len());
                    heat_of.push(new_heat);
                    value_of.push(new_value);
                    mask_of.push(new_mask);
                }
                Some(&at) => {
                    if new_value > value_of[at] {
                        value_of[at] = new_value;
                        mask_of[at] = new_mask;
                    }
                }
            }
        }
    }
    Ok((heat_of, value_of, mask_of))
}


// ---------------------------------------------------------------------------------------------
// FastTable (2026-11-06, session 20): a Rust copy of weapon_selection.FireTable.choose.
//
// Python builds one per FireTable from flat per-weapon data (see weapon_selection._build_fast) and
// asks it for the weapon choice at (distance, pre-TN, side, movement heat). What it does is exactly
// weapon_selection.fire_candidates -> knapsack (levels cached per row, solved again only at a larger
// budget) -> _finish_choice (Phase 2 padding), step for step, so the answer is the Python's to the
// last bit: candidates in weapon order, values = table value x the side's scale, the same sums in the
// same order, the same ties.
//   kind: 0 = never a candidate, 1 = a plain weapon (priced from its grid), 2 = a special weapon,
//   priced by the Python planner through `special(i, distance, pre_tn) -> None | (value, heat)`,
//   3 = a special weapon the planner could describe in numbers (fire_modes.Planner.price_spec): priced here as
//   hit_probability(pre_tn + range modifier + TN change) x its hit worth.
// ---------------------------------------------------------------------------------------------
const STRIDE: usize = 17; // pre-TN 0..=16 (weapon_selection.PRE_TN_MIN / MAX)

/// fire_modes.Planner.price_spec: range modifier and bracket number by distance, then by bracket
/// (short, medium, long) the TN change and the hit worth, and the heat.
struct Spec {
    rm: Vec<Option<i64>>,
    bracket: Vec<u8>,
    tn_change: [i64; 3],
    hit: [f64; 3],
    heat: i64,
}

/// combat.hit_probability: P(2d6 >= tn); tn <= 2 always hits, tn > 12 never; `at_least[tn - 3]` for 3..=12.
fn hit_probability(at_least: &[f64], tn: i64) -> f64 {
    if tn <= 2 { 1.0 } else if tn > 12 { 0.0 } else { at_least[(tn - 3) as usize] }
}

struct Row {
    cand: Vec<usize>,          // weapon index of each candidate, in weapon order
    values: Vec<f64>,
    heats: Vec<i64>,
    has_negative: bool,
    levels: Vec<(i64, f64, u64)>,
    budget: i64,
}

#[pyclass]
struct FastTable {
    kind: Vec<u8>,
    heat: Vec<i64>,            // weapon.heat (a plain weapon's cost; Phase 2 pads with it for every kind)
    energy: Vec<bool>,
    ranges: Vec<[i64; 3]>,     // short, medium, long
    adj: Vec<[i64; 3]>,        // tn_adjust(weapon, bracket) for short, medium, long
    adjust: bool,              // False: tn_adjust was None
    grids: Vec<Vec<f64>>,      // value[distance * 17 + pre_tn], NaN = no row at that distance
    max_distance: i64,
    current_heat: i64,
    min_heat: i64,
    max_heat: i64,
    dissipation: i64,
    other_heat: i64,
    special: Option<Py<PyAny>>,
    specs: Vec<Option<Spec>>,
    at_least: Vec<f64>,
    scales: Vec<Option<Vec<f64>>>, // by side id; id 0 = no scale
    rows: HashMap<(i64, i64, u32), Row>,
}

#[pymethods]
impl FastTable {
    #[new]
    #[pyo3(signature = (kind, heat, energy, ranges, adj, adjust, grids, max_distance, current_heat, min_heat, max_heat, dissipation, other_heat, special, specs, at_least))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        kind: Vec<u8>, heat: Vec<i64>, energy: Vec<bool>, ranges: Vec<[i64; 3]>, adj: Vec<[i64; 3]>, adjust: bool,
        grids: Vec<Vec<f64>>, max_distance: i64, current_heat: i64, min_heat: i64, max_heat: i64,
        dissipation: i64, other_heat: i64, special: Option<Py<PyAny>>,
        specs: Vec<Option<(Vec<Option<i64>>, Vec<u8>, [i64; 3], [f64; 3], i64)>>, at_least: Vec<f64>,
    ) -> PyResult<Self> {
        let n = kind.len();
        if n > 64 || heat.len() != n || energy.len() != n || ranges.len() != n || adj.len() != n || grids.len() != n
            || specs.len() != n || at_least.len() != 10 {
            return Err(pyo3::exceptions::PyValueError::new_err("FastTable: bad weapon lists"));
        }
        Ok(FastTable {
            kind, heat, energy, ranges, adj, adjust, grids, max_distance, current_heat, min_heat, max_heat,
            dissipation, other_heat, special, scales: vec![None], rows: HashMap::new(), at_least,
            specs: specs.into_iter().map(|o| o.map(|(rm, bracket, tn_change, hit, heat)| Spec { rm, bracket, tn_change, hit, heat })).collect(),
        })
    }

    /// Register the per-weapon multipliers of a side (structure weighting); returns its id (>= 1).
    fn add_scale(&mut self, scale: Vec<f64>) -> PyResult<u32> {
        if scale.len() != self.kind.len() {
            return Err(pyo3::exceptions::PyValueError::new_err("FastTable: bad scale list"));
        }
        self.scales.push(Some(scale));
        Ok((self.scales.len() - 1) as u32)
    }

    /// The expected damage of the weapon choice (what the movement scorer reads).
    fn choose_value(&mut self, py: Python<'_>, distance: i64, pre_tn: i64, side: u32, movement_heat: i64) -> PyResult<f64> {
        Ok(self.choose_inner(py, distance, pre_tn, side, movement_heat)?.0)
    }

    /// (expected damage, heat, chosen weapon indices in weapon order) - for the equality checks.
    fn choose_full(&mut self, py: Python<'_>, distance: i64, pre_tn: i64, side: u32, movement_heat: i64)
        -> PyResult<(f64, i64, Vec<usize>)> {
        let (v, h, mask) = self.choose_inner(py, distance, pre_tn, side, movement_heat)?;
        Ok((v, h, (0..self.kind.len()).filter(|&i| mask & (1u64 << i) != 0).collect()))
    }
}

impl FastTable {
    fn build_row(&self, py: Python<'_>, distance: i64, pre_tn: i64, side: u32) -> PyResult<Row> {
        let scale = self.scales[side as usize].as_ref();
        let mut row = Row { cand: vec![], values: vec![], heats: vec![], has_negative: false, levels: vec![], budget: -1 };
        for i in 0..self.kind.len() {
            let (value, heat) = match self.kind[i] {
                0 => continue,
                2 => {
                    let cb = self.special.as_ref().ok_or_else(|| {
                        pyo3::exceptions::PyValueError::new_err("FastTable: a special weapon with no planner")
                    })?;
                    let got = cb.call1(py, (i, distance, pre_tn))?;
                    if got.is_none(py) {
                        continue;
                    }
                    let (v, h): (f64, i64) = got.extract(py)?;
                    (match scale { Some(s) => v * s[i], None => v }, h)
                }
                3 => {
                    let sp = self.specs[i].as_ref().ok_or_else(|| {
                        pyo3::exceptions::PyValueError::new_err("FastTable: kind 3 with no spec")
                    })?;
                    if distance < 0 || distance as usize >= sp.rm.len() {
                        continue;
                    }
                    let rm = match sp.rm[distance as usize] { Some(r) => r, None => continue };
                    let b = sp.bracket[distance as usize] as usize;
                    let tn = pre_tn + rm + sp.tn_change[b];
                    let v = hit_probability(&self.at_least, tn) * sp.hit[b];
                    (match scale { Some(sc) => v * sc[i], None => v }, sp.heat)
                }
                _ => {
                    if distance < 0 || distance > self.max_distance {
                        continue;
                    }
                    let [short, medium, long] = self.ranges[i];
                    let b = if distance <= short { 0 } else if distance <= medium { 1 } else if distance <= long { 2 } else { continue };
                    let mut tn = pre_tn;
                    if self.adjust {
                        tn = (pre_tn + self.adj[i][b]).clamp(0, (STRIDE - 1) as i64);
                    }
                    if tn < 0 || tn >= STRIDE as i64 {
                        return Err(pyo3::exceptions::PyValueError::new_err("FastTable: pre-TN out of range"));
                    }
                    let v = self.grids[i][distance as usize * STRIDE + tn as usize];
                    if v.is_nan() {
                        continue; // no row at this distance
                    }
                    (match scale { Some(s) => v * s[i], None => v }, self.heat[i])
                }
            };
            row.cand.push(i);
            row.values.push(value);
            row.heats.push(heat);
            if heat < 0 {
                row.has_negative = true;
            }
        }
        Ok(row)
    }

    fn choose_inner(&mut self, py: Python<'_>, distance: i64, pre_tn: i64, side: u32, movement_heat: i64)
        -> PyResult<(f64, i64, u64)> {
        let others = self.current_heat + movement_heat + self.other_heat;
        let heat_budget = std::cmp::max(0, self.max_heat + self.dissipation - others);
        let min_weapon_heat = self.min_heat + self.dissipation - others;
        let key = (distance, pre_tn, side);
        if !self.rows.contains_key(&key) {
            let row = self.build_row(py, distance, pre_tn, side)?;
            self.rows.insert(key, row);
        }
        let row = self.rows.get_mut(&key).unwrap();
        // Phase 1: the knapsack (FireTable.choose).
        let (mut total_ed, mut total_heat, picked): (f64, i64, u64);
        if row.has_negative {
            let (heat_of, value_of, mask_of) = solve(&row.values, &row.heats, heat_budget)?;
            let mut best = 0;
            for k in 1..value_of.len() {
                if value_of[k] > value_of[best] {
                    best = k;
                }
            }
            total_ed = value_of[best];
            total_heat = heat_of[best];
            picked = mask_of[best];
        } else {
            if heat_budget > row.budget {
                let (heat_of, value_of, mask_of) = solve(&row.values, &row.heats, heat_budget)?;
                row.levels = (0..heat_of.len()).map(|k| (heat_of[k], value_of[k], mask_of[k])).collect();
                row.budget = heat_budget;
            }
            // best_within: the first level, in insertion order, with the highest value within the budget.
            let mut best: Option<(i64, f64, u64)> = None;
            for &(h, v, m) in row.levels.iter() {
                if h <= heat_budget && (best.is_none() || v > best.unwrap().1) {
                    best = Some((h, v, m));
                }
            }
            let (h, v, m) = best.unwrap_or((0, 0.0, 0));
            total_ed = v;
            total_heat = h;
            picked = m;
        }
        // The chosen candidates' weapon bits (picked is a mask over candidates).
        let mut selected: u64 = 0;
        for (c, &w) in row.cand.iter().enumerate() {
            if picked & (1u64 << c) != 0 {
                selected |= 1u64 << w;
            }
        }
        // Phase 2: pad toward the min_heat floor with unfired energy weapons (_finish_choice).
        if self.min_heat > 0 && total_heat < min_weapon_heat {
            let remaining = heat_budget - total_heat;
            let mut leftovers: Vec<(usize, f64)> = Vec::new();
            for (c, &w) in row.cand.iter().enumerate() {
                if selected & (1u64 << w) == 0 && self.energy[w] && self.heat[w] <= remaining {
                    leftovers.push((w, row.values[c]));
                }
            }
            // sort(key=ed, reverse=True) is stable: equal values keep their candidate order.
            leftovers.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
            for (w, ed) in leftovers {
                if total_heat >= min_weapon_heat {
                    break;
                }
                if self.heat[w] > heat_budget - total_heat {
                    continue;
                }
                selected |= 1u64 << w;
                total_heat += self.heat[w];
                total_ed += ed;
            }
        }
        Ok((total_ed, total_heat, selected))
    }
}


// ---------------------------------------------------------------------------------------------
// PathBoard (2026-11-06, session 20): a Rust copy of pathfinder._build_terrain_psr (the movement table
// of a board where steps can force terrain PSRs) plus the walking states ranged_combat._movement_options
// builds from it. Python hands over the board's step data once per mover level-limit class (cost and
// PSR counts of stepping from each hex in each of the 6 directions, forward and backward, and the PSRs
// of turning in each hex); the search is the Dial's-algorithm sweep of the Python, step for step: the
// same buckets in the same insertion order, the same "strictly better (hazard, forward count, -PSRs)
// replaces" rule, so the table, its order and every tie are the Python's. Boards with live hazards
// (magma crust) and paths that must be kept (keep_parents) stay in Python.
// ---------------------------------------------------------------------------------------------
const FACING: [(i32, i32); 6] = [(0, 2), (1, 1), (1, -1), (0, -2), (-1, -1), (-1, 1)];

type SKey = (i32, i32, u8, i8, bool); // x, y, facing, last direction (0 / +1 / -1), moved backward yet

#[derive(Clone, Copy)]
struct SVal {
    fc: i32,
    neg: i32,
    always: i32,
    run_only: i32,
}

#[derive(Default)]
struct Bucket {
    keys: Vec<SKey>,
    vals: Vec<SVal>,
    index: HashMap<SKey, usize>,
}

impl Bucket {
    /// pathfinder's push: a strictly better (forward count, then fewer PSRs) value replaces the old one in place.
    fn push(&mut self, key: SKey, val: SVal) {
        match self.index.get(&key) {
            None => {
                self.index.insert(key, self.keys.len());
                self.keys.push(key);
                self.vals.push(val);
            }
            Some(&at) => {
                let old = self.vals[at];
                if (val.fc, val.neg) > (old.fc, old.neg) {
                    self.vals[at] = val;
                }
            }
        }
    }
}

/// The finished table: states in first-seen order, each with its (mp, forward count, always, run-only) columns in order.
struct Table {
    states: Vec<(i32, i32, u8)>,
    cols: Vec<Vec<(i32, i32, i32, i32)>>,
}

#[pyclass]
struct PathBoard {
    xmin: i32,
    ymin: i32,
    height: i32,
    width: i32,
    present: Vec<bool>,
    fwd: Vec<[i32; 3]>,  // [idx * 6 + facing] -> cost (-1 = not allowed), always, run-only
    bwd: Vec<[i32; 3]>,
    turn: Vec<[i32; 2]>, // [idx] -> always, run-only
    tables: HashMap<(i32, i32, u8, i32, i32, Vec<(i32, i32)>), std::sync::Arc<Table>>,
}

impl PathBoard {
    fn idx(&self, x: i32, y: i32) -> Option<usize> {
        let (cx, cy) = (x - self.xmin, y - self.ymin);
        if cx < 0 || cy < 0 || cx >= self.width || cy >= self.height {
            return None;
        }
        let i = (cx * self.height + cy) as usize;
        if self.present[i] { Some(i) } else { None }
    }

    fn search(&self, sx: i32, sy: i32, facing: u8, budget: i32, backward_mp: Option<i32>, blocked: &[(i32, i32)])
        -> PyResult<Table> {
        let usable = |x: i32, y: i32| -> Option<usize> {
            if blocked.contains(&(x, y)) { None } else { self.idx(x, y) }
        };
        if usable(sx, sy).is_none() {
            return Err(pyo3::exceptions::PyValueError::new_err("PathBoard: start hex is not on the board"));
        }
        let mut buckets: Vec<Bucket> = (0..=budget.max(0)).map(|_| Bucket::default()).collect();
        buckets[0].push((sx, sy, facing, 0, false), SVal { fc: 0, neg: 0, always: 0, run_only: 0 });
        let mut states: Vec<(i32, i32, u8)> = Vec::new();
        let mut cols: Vec<Vec<(i32, i32, i32, i32)>> = Vec::new();
        let mut state_at: HashMap<(i32, i32, u8), usize> = HashMap::new();
        for mp in 0..=budget {
            let n = buckets[mp as usize].keys.len();
            for k in 0..n {
                let key = buckets[mp as usize].keys[k];
                let val = buckets[mp as usize].vals[k];
                let (x, y, f, last, used_back) = key;
                // the table entry (a strictly better path to the same state and MP replaces the earlier one)
                let st = (x, y, f);
                let si = *state_at.entry(st).or_insert_with(|| {
                    states.push(st);
                    cols.push(Vec::new());
                    states.len() - 1
                });
                match cols[si].iter().position(|c| c.0 == mp) {
                    None => cols[si].push((mp, val.fc, val.always, val.run_only)),
                    Some(at) => {
                        let old = cols[si][at];
                        if (val.fc, val.neg) > (old.1, -(old.2 + old.3)) {
                            cols[si][at] = (mp, val.fc, val.always, val.run_only);
                        }
                    }
                }
                let limit = if used_back { backward_mp.unwrap_or(budget) } else { budget };
                let here = match self.idx(x, y) { Some(i) => i, None => continue };
                let (dx, dy) = FACING[f as usize];
                // 1. forward
                if usable(x + dx, y + dy).is_some() {
                    let [cost, a, r] = self.fwd[here * 6 + f as usize];
                    if cost >= 0 && mp + cost <= limit {
                        buckets[(mp + cost) as usize].push(
                            (x + dx, y + dy, f, 1, used_back),
                            SVal { fc: if last >= 0 { val.fc + 1 } else { 1 }, neg: val.neg - a - r,
                                   always: val.always + a, run_only: val.run_only + r });
                    }
                }
                // 2. backward (walking only)
                if let Some(bm) = backward_mp {
                    if usable(x - dx, y - dy).is_some() {
                        let [cost, a, r] = self.bwd[here * 6 + f as usize];
                        if cost >= 0 && mp + cost <= bm {
                            buckets[(mp + cost) as usize].push(
                                (x - dx, y - dy, f, -1, true),
                                SVal { fc: if last <= 0 { val.fc + 1 } else { 1 }, neg: val.neg - a - r,
                                       always: val.always + a, run_only: val.run_only + r });
                        }
                    }
                }
                // 3. / 4. turning
                if mp + 1 <= limit {
                    let [a, r] = self.turn[here];
                    for nf in [((f as i32 + 5) % 6) as u8, ((f as i32 + 1) % 6) as u8] {
                        buckets[(mp + 1) as usize].push(
                            (x, y, nf, last, used_back),
                            SVal { fc: val.fc, neg: val.neg - a - r, always: val.always + a, run_only: val.run_only + r });
                    }
                }
            }
        }
        Ok(Table { states, cols })
    }
}

#[pymethods]
impl PathBoard {
    #[new]
    #[allow(clippy::too_many_arguments)]
    fn new(xmin: i32, ymin: i32, width: i32, height: i32, present: Vec<bool>, fwd: Vec<[i32; 3]>, bwd: Vec<[i32; 3]>,
           turn: Vec<[i32; 2]>) -> PyResult<Self> {
        let n = (width * height) as usize;
        if present.len() != n || fwd.len() != n * 6 || bwd.len() != n * 6 || turn.len() != n {
            return Err(pyo3::exceptions::PyValueError::new_err("PathBoard: bad board lists"));
        }
        Ok(PathBoard { xmin, ymin, height, width, present, fwd, bwd, turn, tables: HashMap::new() })
    }

    /// ranged_combat._movement_options for a mover that walks from its own hex: the end states
    /// (x, y, facing, forward count, mode, MP spent) in the Python's order and, in the same order, the
    /// terrain PSRs of the way there (_note_psrs: always + run-only for a Run).
    fn walk_states(&mut self, sx: i32, sy: i32, facing: u8, run_budget: i32, backward_mp: Option<i32>,
                   blocked: Vec<(i32, i32)>, walk: i32, want_psrs: bool)
        -> PyResult<(Vec<(i32, i32, i32, i32, &'static str, i32)>, Vec<i32>)> {
        let mut near: Vec<(i32, i32)> = blocked.iter().copied()
            .filter(|b| (b.0 - sx).abs() <= run_budget && (b.1 - sy).abs() <= 2 * run_budget).collect();
        near.sort();
        near.dedup();
        let key = (sx, sy, facing, run_budget, backward_mp.unwrap_or(-1), near.clone());
        let table = match self.tables.get(&key) {
            Some(t) => t.clone(),
            None => {
                let t = std::sync::Arc::new(self.search(sx, sy, facing, run_budget, backward_mp, &near)?);
                if self.tables.len() >= 600 {
                    self.tables.clear();
                }
                self.tables.insert(key, t.clone());
                t
            }
        };
        let mut keys = Vec::new();
        let mut psrs = Vec::new();
        for (st, col) in table.states.iter().zip(table.cols.iter()) {
            for &(mp, fc, always, run_only) in col.iter() {
                let mode: &'static str = if mp == 0 { "Stand Still" } else if mp <= walk { "Walk" } else { "Run" };
                keys.push((st.0, st.1, st.2 as i32, fc, mode, mp));
                if want_psrs {
                    psrs.push(always + if mode == "Run" { run_only } else { 0 });
                }
            }
        }
        Ok((keys, psrs))
    }

    /// ranged_combat._entry_options: a mech entering the board from its home edge. `starts` lists the edge hexes it can
    /// step onto as (x, y, entry cost, entry always-PSRs, entry run-only PSRs), in the Python's order; each is searched
    /// from all 6 facings with the MP left, and a state reached more than once keeps its first place in the order and
    /// its fewest PSRs (_note_psrs). Returns the states (x, y, facing, forward count + 1, mode, total MP), the PSR count of
    /// each when it was FIRST reached (the Python notes a state's PSRs as it yields it, and the reduction reads them then),
    /// and the fewest over all the ways to reach it (what the dict holds in the end).
    fn entry_states(&mut self, starts: Vec<(i32, i32, i32, i32, i32)>, run: i32, walk: i32, blocked: Vec<(i32, i32)>,
                    want_psrs: bool) -> PyResult<(Vec<(i32, i32, i32, i32, &'static str, i32)>, Vec<i32>, Vec<i32>)> {
        let mut keys: Vec<(i32, i32, i32, i32, &'static str, i32)> = Vec::new();
        let mut psrs: Vec<i32> = Vec::new();
        let mut first: Vec<i32> = Vec::new();
        let mut at: HashMap<(i32, i32, i32, i32, &'static str, i32), usize> = HashMap::new();
        for &(ex, ey, cost, ea, er) in starts.iter() {
            for f0 in 0..6u8 {
                let budget = run - cost;
                let mut near: Vec<(i32, i32)> = blocked.iter().copied()
                    .filter(|b| (b.0 - ex).abs() <= budget && (b.1 - ey).abs() <= 2 * budget).collect();
                near.sort();
                near.dedup();
                let key = (ex, ey, f0, budget, -1, near.clone());
                let table = match self.tables.get(&key) {
                    Some(t) => t.clone(),
                    None => {
                        let t = std::sync::Arc::new(self.search(ex, ey, f0, budget, None, &near)?);
                        if self.tables.len() >= 600 {
                            self.tables.clear();
                        }
                        self.tables.insert(key, t.clone());
                        t
                    }
                };
                for (st, col) in table.states.iter().zip(table.cols.iter()) {
                    for &(spent, fc, always, run_only) in col.iter() {
                        let total = spent + cost;
                        let mode: &'static str = if total == 0 { "Stand Still" } else if total <= walk { "Walk" } else { "Run" };
                        let k = (st.0, st.1, st.2 as i32, fc + 1, mode, total);
                        let n = (always + ea) + if mode == "Run" { run_only + er } else { 0 };
                        match at.get(&k) {
                            None => {
                                at.insert(k, keys.len());
                                keys.push(k);
                                if want_psrs { psrs.push(n); first.push(n); }
                            }
                            Some(&i) => {
                                if want_psrs && n < psrs[i] { psrs[i] = n; }
                            }
                        }
                    }
                }
            }
        }
        Ok((keys, first, psrs))
    }
}

#[pymodule]
fn fastcore(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(best_subset, m)?)?;
    m.add_function(wrap_pyfunction!(knapsack_levels, m)?)?;
    m.add_class::<FastTable>()?;
    m.add_class::<PathBoard>()?;
    Ok(())
}
