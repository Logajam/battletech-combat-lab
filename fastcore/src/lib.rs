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

#[pymodule]
fn fastcore(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(best_subset, m)?)?;
    m.add_function(wrap_pyfunction!(knapsack_levels, m)?)?;
    Ok(())
}
