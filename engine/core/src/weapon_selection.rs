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
