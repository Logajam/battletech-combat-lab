// Translated from INTEGRATION__forces.py (session 22). Part 1: the roster lookups the engine rules need; the turn-order
// and target-choice parts follow with the orchestrator.
use crate::battle::{Battle, UnitId};

/// The standing unit in hex `label`, other than those in `exclude`.
pub fn unit_in_hex(b: &mut Battle, label: &str, exclude: &[UnitId]) -> Option<UnitId> {
    for u in 0..b.units.len() {
        if b.units[u].hex.as_deref() == Some(label) && !b.is_destroyed(u) && !exclude.contains(&u) {
            return Some(u);
        }
    }
    None
}
