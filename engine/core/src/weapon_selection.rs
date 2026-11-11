// Translated from INTEGRATION__weapon_selection.py (session 22). Part 1: the range terms and the heat budget; the
// knapsack and the candidate list come with the bots (they need the Planner and the fire-control hooks).
use crate::battle::{Battle, UnitId};
use crate::equipment::ItemId;

pub const RANGE_MOD_SHORT: i64 = 0;
pub const RANGE_MOD_MEDIUM: i64 = 2;
pub const RANGE_MOD_LONG: i64 = 4;
pub const PRE_TN_MIN: i64 = 0;
pub const PRE_TN_MAX: i64 = 16;

/// Minimum-range to-hit penalty: +1 for each hex the target is inside the weapon's minimum range.
pub fn min_range_penalty(minimum: i64, distance: i64) -> i64 {
    if minimum != 0 && distance <= minimum {
        minimum - distance + 1
    } else {
        0
    }
}

/// "short" / "medium" / "long" for firing `weapon` at `distance`, or None if out of range.
pub fn range_bracket(b: &Battle, u: UnitId, w: ItemId, distance: i64) -> Option<&'static str> {
    let wr = b.units[u].items[w].weapon_range.as_ref()?;
    if distance <= wr.short {
        Some("short")
    } else if distance <= wr.medium {
        Some("medium")
    } else if distance <= wr.long {
        Some("long")
    } else {
        None
    }
}

/// Range TN modifier for firing `weapon` at `distance`, or None if out of range.
pub fn weapon_range_mod(b: &Battle, u: UnitId, w: ItemId, distance: i64) -> Option<i64> {
    let wr = b.units[u].items[w].weapon_range.as_ref()?;
    let bracket = if distance <= wr.short {
        RANGE_MOD_SHORT
    } else if distance <= wr.medium {
        RANGE_MOD_MEDIUM
    } else if distance <= wr.long {
        RANGE_MOD_LONG
    } else {
        return None;
    };
    Some(bracket + min_range_penalty(wr.min.unwrap_or(0), distance))
}

/// (weapon heat budget, weapon heat the min_heat floor asks for)
pub fn heat_limits(current_heat: i64, min_heat: i64, max_heat: i64, dissipation: i64, movement_heat: i64, other_heat: i64) -> (i64, i64) {
    let heat_budget = 0.max(max_heat + dissipation - current_heat - movement_heat - other_heat);
    let min_weapon_heat = min_heat + dissipation - current_heat - movement_heat - other_heat;
    (heat_budget, min_weapon_heat)
}

// ---- the knapsack and the candidates ---------------------------------------------------------------------------------
use crate::fasthash::{HashMap, HashSet};

use crate::fasthash::IndexMap;

use crate::attack_resolution::table_value;
use crate::damage_resolution::get_weapons;
use crate::fire_modes::{self, Planner, TnAdjust};

/// (weapon, value, heat) of a weapon that can fire at this distance.
#[derive(Clone, Debug)]
pub struct Candidate {
    pub w: ItemId,
    pub value: f64,
    pub heat: i64,
}

/// Phase 1: the exact 0/1 knapsack (weight = heat, value = expected damage). Returns (best value, heat it uses, indices
/// of the chosen candidates). dp[h] = (best value using exactly heat h, chosen indices); ties go to the first heat level
/// reached (insertion order).
pub fn best_subset_python(values: &[f64], heats: &[i64], heat_budget: i64) -> (f64, i64, Vec<usize>) {
    let mut dp: IndexMap<i64, (f64, Vec<usize>)> = IndexMap::default();
    dp.insert(0, (0.0, vec![]));
    for (i, (ed, heat_cost)) in values.iter().zip(heats).enumerate() {
        let mut keys: Vec<i64> = dp.keys().copied().collect();
        keys.sort_by(|a, b| b.cmp(a));
        for used_heat in keys {
            let new_heat = used_heat + heat_cost;
            if new_heat > heat_budget {
                continue;
            }
            let new_value = dp[&used_heat].0 + ed;
            let better = match dp.get(&new_heat) {
                None => true,
                Some(e) => new_value > e.0,
            };
            if better {
                let mut set = dp[&used_heat].1.clone();
                set.push(i);
                dp.insert(new_heat, (new_value, set));
            }
        }
    }
    let mut best_h = *dp.keys().next().unwrap();
    for (h, (v, _)) in &dp {
        if *v > dp[&best_h].0 {
            best_h = *h;
        }
    }
    let (v, ids) = dp[&best_h].clone();
    (v, best_h, ids)
}

/// [(weapon, value, heat)] that can fire at this distance - in range, with confirmed heat data.
#[allow(clippy::too_many_arguments)]
pub fn fire_candidates(b: &mut Battle, attacker: UnitId, distance: i64, pre_tn: i64, tn_adjust: Option<&dyn TnAdjust>, unavailable: &HashSet<ItemId>, value_scale: Option<&HashMap<ItemId, f64>>, weapons: &[ItemId], mut planner: Option<&mut Planner>) -> Vec<Candidate> {
    let mut candidates = Vec::new();
    for &w in weapons {
        if unavailable.contains(&w) {
            continue;
        }
        if planner.is_some() && fire_modes::special(b, attacker, w) {
            if b.units[attacker].items[w].heat.is_none() && !fire_modes::has_profile(b, attacker, w) {
                continue;
            }
            let Some((value, heat_cost, _)) = planner.as_deref_mut().unwrap().plan_for(b, w, distance, pre_tn) else { continue };
            let v = match value_scale {
                None => value,
                Some(s) => value * s.get(&w).copied().unwrap_or(1.0),
            };
            candidates.push(Candidate { w, value: v, heat: heat_cost });
            continue;
        }
        let heat = b.units[attacker].items[w].heat;
        let mut tn = pre_tn;
        let Some(row_probe) = table_value(b, attacker, w, distance, 0) else { continue };
        let _ = row_probe;
        let Some(heat) = heat else { continue };
        if let Some(adj) = tn_adjust {
            let br = range_bracket(b, attacker, w, distance);
            tn = PRE_TN_MIN.max(PRE_TN_MAX.min(pre_tn + adj.adjust(b, w, br, None)));
        }
        let row = table_value(b, attacker, w, distance, tn).unwrap();
        let v = match value_scale {
            None => row,
            Some(s) => row * s.get(&w).copied().unwrap_or(1.0),
        };
        candidates.push(Candidate { w, value: v, heat });
    }
    candidates
}

/// Phase 1's pick (candidate indices) plus Phase 2's padding -> (weapons, expected damage, heat).
#[allow(clippy::too_many_arguments)]
pub fn finish_choice(b: &Battle, attacker: UnitId, candidates: &[Candidate], weapons: &[ItemId], best_value: f64, best_heat_used: i64, picked: &[usize], heat_budget: i64, min_heat: i64, min_weapon_heat: i64) -> (Vec<ItemId>, f64, i64) {
    let mut selected: HashSet<ItemId> = picked.iter().map(|i| candidates[*i].w).collect();
    let mut total_heat = best_heat_used;
    let mut total_ed = best_value;
    if min_heat > 0 && total_heat < min_weapon_heat {
        let remaining_budget = heat_budget - total_heat;
        let mut leftovers: Vec<(ItemId, f64)> = candidates
            .iter()
            .filter(|c| !selected.contains(&c.w) && b.units[attacker].items[c.w].damage_type.as_deref() == Some("Energy") && b.units[attacker].items[c.w].heat.unwrap() <= remaining_budget)
            .map(|c| (c.w, c.value))
            .collect();
        leftovers.sort_by(|a, c| c.1.partial_cmp(&a.1).unwrap()); // reverse=True, stable
        for (w, ed) in leftovers {
            if total_heat >= min_weapon_heat {
                break;
            }
            let h = b.units[attacker].items[w].heat.unwrap();
            if h > heat_budget - total_heat {
                continue;
            }
            selected.insert(w);
            total_heat += h;
            total_ed += ed;
        }
    }
    (weapons.iter().copied().filter(|w| selected.contains(w)).collect(), total_ed, total_heat)
}

/// Gladiator's weapon choice (select_weapons_to_fire with no other bot's fire control): the heat-constrained knapsack.
#[allow(clippy::too_many_arguments)]
pub fn select_weapons_to_fire(b: &mut Battle, attacker: UnitId, distance: i64, pre_tn: i64, min_heat: i64, max_heat: i64, dissipation: i64, movement_heat: i64, other_heat: i64, tn_adjust: Option<&dyn TnAdjust>, unavailable: &HashSet<ItemId>, planner: Option<&mut Planner>) -> (Vec<ItemId>, f64, i64) {
    select_weapons_scaled(b, attacker, distance, pre_tn, min_heat, max_heat, dissipation, movement_heat, other_heat, tn_adjust, unavailable, None, planner, None)
}

/// select_weapons_to_fire with value_scale (movement scoring): {weapon: multiplier} applied to each weapon's expected
/// damage before the choice, so the total is WORTH.
#[allow(clippy::too_many_arguments)]
pub fn select_weapons_scaled(b: &mut Battle, attacker: UnitId, distance: i64, pre_tn: i64, min_heat: i64, max_heat: i64, dissipation: i64, movement_heat: i64, other_heat: i64, tn_adjust: Option<&dyn TnAdjust>, unavailable: &HashSet<ItemId>, value_scale: Option<&HashMap<ItemId, f64>>, planner: Option<&mut Planner>, side: Option<&str>) -> (Vec<ItemId>, f64, i64) {
    if let Some(fc) = b.fire_ctl.take() {
        // another bot's fire control (weapon_selection._FIRE_CONTROL): it chooses from the same candidates
        let mut fc = fc;
        let r = other_fire_control(b, &mut fc, attacker, distance, pre_tn, dissipation, other_heat, tn_adjust, unavailable, planner, side.unwrap_or(""), movement_heat);
        b.fire_ctl = Some(fc);
        return r;
    }
    let weapons = get_weapons(&b.units[attacker]);
    let (heat_budget, min_weapon_heat) = heat_limits(b.units[attacker].current_heat, min_heat, max_heat, dissipation, movement_heat, other_heat);
    let candidates = fire_candidates(b, attacker, distance, pre_tn, tn_adjust, unavailable, value_scale, &weapons, planner);
    if std::env::var("BT_DEBUG").is_ok() {
        for c in &candidates {
            eprintln!("  cand {} value {:?} heat {}", b.units[attacker].items[c.w].name, c.value, c.heat);
        }
        eprintln!("  distance {} pre_tn {} budget {:?}", distance, pre_tn, heat_limits(b.units[attacker].current_heat, min_heat, max_heat, dissipation, movement_heat, other_heat));
    }
    let values: Vec<f64> = candidates.iter().map(|c| c.value).collect();
    let heats: Vec<i64> = candidates.iter().map(|c| c.heat).collect();
    let (best_value, best_heat_used, picked) = best_subset_python(&values, &heats, heat_budget);
    finish_choice(b, attacker, &candidates, &weapons, best_value, best_heat_used, &picked, heat_budget, min_heat, min_weapon_heat)
}

/// _other_fire_control: the candidates Gladiator's knapsack sees (in range, heat known, the planner pricing special weapons),
/// unscaled, each with its to-hit number, handed to the other bot's fire control to choose from.
#[allow(clippy::too_many_arguments)]
fn other_fire_control(b: &mut Battle, fc: &mut crate::princess_fire::FireControl, attacker: UnitId, distance: i64, pre_tn: i64, dissipation: i64, other_heat: i64, tn_adjust: Option<&dyn TnAdjust>, unavailable: &HashSet<ItemId>, mut planner: Option<&mut Planner>, side: &str, movement_heat: i64) -> (Vec<ItemId>, f64, i64) {
    let weapons = get_weapons(&b.units[attacker]);
    let mut candidates: Vec<(ItemId, f64, i64, i64)> = Vec::new();
    for &w in &weapons {
        if unavailable.contains(&w) {
            continue;
        }
        if planner.is_some() && fire_modes::special(b, attacker, w) {
            if b.units[attacker].items[w].heat.is_none() && !fire_modes::has_profile(b, attacker, w) {
                continue;
            }
            let Some((value, heat_cost, plan)) = planner.as_deref_mut().unwrap().plan_for(b, w, distance, pre_tn) else { continue };
            let tn = planner.as_deref_mut().unwrap().value(b, w, &plan, distance, pre_tn).unwrap().1;
            candidates.push((w, value, heat_cost, tn));
            continue;
        }
        let Some(_) = crate::attack_resolution::table_value(b, attacker, w, distance, 0) else { continue };
        let Some(heat) = b.units[attacker].items[w].heat else { continue };
        let mut tn = pre_tn;
        if let Some(adj) = tn_adjust {
            let br = range_bracket(b, attacker, w, distance);
            tn = PRE_TN_MIN.max(PRE_TN_MAX.min(pre_tn + adj.adjust(b, w, br, None)));
        }
        let value = crate::attack_resolution::table_value(b, attacker, w, distance, tn).unwrap();
        let rm = weapon_range_mod(b, attacker, w, distance).unwrap();
        candidates.push((w, value, heat, tn + rm));
    }
    let target = planner.as_ref().map(|p| p.target);
    fc.choose(b, attacker, &candidates, dissipation, other_heat, target, side, movement_heat)
}
