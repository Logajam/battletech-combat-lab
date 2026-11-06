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

#[pymodule]
fn fastcore(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(best_subset, m)?)?;
    m.add_function(wrap_pyfunction!(knapsack_levels, m)?)?;
    m.add_class::<FastTable>()?;
    Ok(())
}
