// Translated from INTEGRATION__smoke.py (session 22): smoke on the board, and active probes seeing through it.
use crate::battle::{Battle, UnitId};
use crate::board_parser::Smoke;
use crate::los::LOSTrace;
use crate::mech_state::Mech;

pub const LIGHT: &str = "1";
pub const HEAVY: &str = "2";
pub const ECM_RADIUS: i64 = 6;
const PROBE_RANGES: [(&str, i64); 6] = [("BLOODHOUND", 8), ("BEAGLE", 4), ("CLLIGHTACTIVEPROBE", 3), ("LIGHTACTIVEPROBE", 3), ("WATCHDOG", 5), ("ACTIVEPROBE", 5)];

/// Smoke in `label` until the End Phase of turn `until`.
pub fn add(b: &mut Battle, label: &str, density: &str, until: i64, source: &str) {
    let Some(info) = b.board.hexes.get_mut(label) else { return };
    let old = info.smoke.clone();
    let new = match &old {
        None => Smoke { density: density.to_string(), until },
        Some(o) => Smoke { density: HEAVY.to_string(), until: o.until.max(until) },
    };
    info.smoke = Some(new.clone());
    b.smoky.insert(label.to_string());
    if Some(&new) == old.as_ref() {
        return;
    }
    b.log(format!("      {} smoke fills {} (from {}; until the End Phase of turn {}).", if new.density == HEAVY { "Heavy" } else { "Light" }, label, source, new.until));
}

/// Clouds whose time is up blow away (printed sorted by label: the Python's set order is hash order).
pub fn end_phase(b: &mut Battle, turn: i64) {
    let mut gone: Vec<String> = b.smoky.iter().filter(|l| b.board.hexes[l.as_str()].smoke.as_ref().unwrap().until <= turn).cloned().collect();
    gone.sort();
    for label in gone {
        b.board.hexes.get_mut(&label).unwrap().smoke = None;
        b.smoky.shift_remove(&label);
        b.log(format!("  [End] The smoke at {} clears.", label));
    }
}

fn norm(name: &str) -> String {
    name.replace(' ', "").replace('-', "").to_uppercase()
}

/// (range, is_bloodhound) of the 'Mech's working active probe, or None.
pub fn probe(mech: &Mech) -> Option<(i64, bool)> {
    let dead: std::collections::HashSet<usize> = mech.destroyed_slot_info.values().filter_map(|i| i.instance_id).collect();
    let mut best: Option<(i64, bool)> = None;
    for slots in mech.crits.values() {
        for s in slots {
            let crate::equipment::Slot::Item(id) = s else { continue };
            if dead.contains(id) || mech.items[*id].category.as_deref() == Some("ammo") {
                continue;
            }
            let n = norm(&mech.items[*id].name);
            for (key, rng) in PROBE_RANGES {
                if n.contains(key) {
                    if best.map_or(true, |b| rng > b.0) {
                        best = Some((rng, key == "BLOODHOUND"));
                    }
                    break;
                }
            }
        }
    }
    best
}

fn jammed(b: &Battle, attacker: UnitId, target: UnitId, distance: i64, bloodhound: bool) -> bool {
    use crate::electronics as el;
    if el::as_if_jammed(&b.units[attacker]) {
        return true;
    }
    if !el::hostile_field(&b.units[target]) {
        return false;
    }
    if bloodhound && !el::angel_field(&b.units[target]) {
        return false;
    }
    distance <= ECM_RADIUS
}

/// The smoke to-hit points the attacker's probe ignores on this line.
pub fn probe_relief(b: &Battle, attacker: UnitId, target: UnitId, trace: &LOSTrace, distance: i64) -> i64 {
    if b.units[attacker].shutdown || !trace.result.los {
        return 0;
    }
    let Some((rng, bloodhound)) = probe(&b.units[attacker]) else { return 0 };
    if !trace.steps.iter().any(|s| s.smoke_contrib != 0) {
        return 0;
    }
    if jammed(b, attacker, target, distance, bloodhound) {
        return 0;
    }
    trace.steps.iter().filter(|s| 0 < s.index && s.index <= rng).map(|s| s.smoke_contrib).sum()
}
