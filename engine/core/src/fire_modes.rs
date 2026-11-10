// Translated from INTEGRATION__fire_modes.py (session 22). First part: the ammunition-kind tables and the weapon
// predicates ammo needs; the shot plan / planner follow with electronics.
use crate::battle::{Battle, UnitId};
use crate::equipment::ItemId;
use crate::weapon_rules::canonical_name;

/// (damage per missile, grouping, range {min, short, medium, long})
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct KindRange {
    pub min: i64,
    pub short: i64,
    pub medium: i64,
    pub long: i64,
}

/// MML_KINDS: kind -> (damage per missile, grouping, range)
pub fn mml_kind(kind: &str) -> Option<(i64, i64, KindRange)> {
    match kind {
        "lrm" => Some((1, 5, KindRange { min: 6, short: 7, medium: 14, long: 21 })),
        "srm" => Some((2, 2, KindRange { min: 0, short: 3, medium: 6, long: 9 })),
        _ => None,
    }
}

/// MML_SHOTS[rack][kind]
pub fn mml_shots(rack: Option<i64>, kind: &str) -> Option<i64> {
    let (l, s) = match rack? {
        3 => (40, 33),
        5 => (24, 20),
        7 => (17, 14),
        9 => (13, 11),
        _ => return None,
    };
    match kind {
        "lrm" => Some(l),
        "srm" => Some(s),
        _ => None,
    }
}

/// ATM_KINDS: kind -> (damage per missile, range)
pub fn atm_kind(kind: &str) -> Option<(i64, KindRange)> {
    match kind {
        "standard" => Some((2, KindRange { min: 4, short: 5, medium: 10, long: 15 })),
        "er" => Some((1, KindRange { min: 4, short: 9, medium: 18, long: 27 })),
        "he" => Some((3, KindRange { min: 0, short: 3, medium: 6, long: 9 })),
        "imp" => Some((1, KindRange { min: 0, short: 3, medium: 6, long: 9 })),
        "iiw" => Some((0, KindRange { min: 4, short: 5, medium: 10, long: 15 })),
        _ => None,
    }
}

pub const LBX_CLUSTER_TN: i64 = -1;
pub const RAC_JAM_AT: [(i64, i64); 3] = [(6, 4), (4, 3), (2, 2)];
pub const UNJAM_TN_MODIFIER: i64 = 3;
pub const APOLLO_CLUSTER: i64 = 1;

pub fn is_ultra(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    canonical_name(b, u, w).contains("ULTRAAC")
}
pub fn is_rotary(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    canonical_name(b, u, w).contains("ROTARYAC")
}
pub fn is_lbx(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    canonical_name(b, u, w).contains("LBXAC")
}
pub fn is_mml(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    canonical_name(b, u, w).contains("MML")
}
pub fn is_mrm(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    canonical_name(b, u, w).starts_with("MRM")
}
pub fn max_shots(b: &mut Battle, u: UnitId, w: ItemId) -> i64 {
    if is_ultra(b, u, w) {
        2
    } else if is_rotary(b, u, w) {
        6
    } else {
        1
    }
}
