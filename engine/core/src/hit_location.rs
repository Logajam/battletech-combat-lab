// Translated from mechsim/hit_location.py (session 22).
//! Facing / hit-location resolution (the Total Warfare tables).

use crate::battle::{Battle, UnitId};

pub const HIT_TABLE_FRONT_REAR: [(i64, &str); 11] = [
    (2, "Center Torso"), (3, "Right Arm"), (4, "Right Arm"), (5, "Right Leg"), (6, "Right Torso"), (7, "Center Torso"),
    (8, "Left Torso"), (9, "Left Leg"), (10, "Left Arm"), (11, "Left Arm"), (12, "Head"),
];
pub const HIT_TABLE_LEFT_SIDE: [(i64, &str); 11] = [
    (2, "Left Torso"), (3, "Left Leg"), (4, "Left Arm"), (5, "Left Arm"), (6, "Left Leg"), (7, "Left Torso"),
    (8, "Center Torso"), (9, "Right Torso"), (10, "Right Arm"), (11, "Right Leg"), (12, "Head"),
];
pub const HIT_TABLE_RIGHT_SIDE: [(i64, &str); 11] = [
    (2, "Right Torso"), (3, "Right Leg"), (4, "Right Arm"), (5, "Right Arm"), (6, "Right Leg"), (7, "Right Torso"),
    (8, "Center Torso"), (9, "Left Torso"), (10, "Left Arm"), (11, "Left Leg"), (12, "Head"),
];

pub fn table_for(facing: &str) -> &'static [(i64, &'static str); 11] {
    match facing {
        "left" => &HIT_TABLE_LEFT_SIDE,
        "right" => &HIT_TABLE_RIGHT_SIDE,
        _ => &HIT_TABLE_FRONT_REAR,
    }
}

fn lookup(table: &[(i64, &'static str); 11], roll: i64) -> &'static str {
    table.iter().find(|(r, _)| *r == roll).map_or("Center Torso", |(_, l)| l)
}

fn tripod_subroll(facing: &str, sub: i64) -> &'static str {
    match facing {
        "right" => match sub {
            0..=2 => "Right Leg",
            3 | 4 => "Center Leg",
            5 => "Left Leg",
            _ => panic!("KeyError: {}", sub),
        },
        "left" => match sub {
            2 => "Right Leg",
            3 | 4 => "Center Leg",
            5..=7 => "Left Leg",
            _ => panic!("KeyError: {}", sub),
        },
        _ => match sub {
            1 | 2 => "Right Leg",
            3 | 4 => "Center Leg",
            5 | 6 => "Left Leg",
            _ => panic!("KeyError: {}", sub),
        },
    }
}

fn resolve_hit_location_once(b: &mut Battle, u: UnitId, loc_roll: i64, facing: &str) -> String {
    let table = table_for(facing);
    let mut loc = lookup(table, loc_roll).to_string();
    let mech_type = b.units[u].mech_type.clone();
    if mech_type == "tripod" && (loc == "Left Leg" || loc == "Right Leg") {
        let base_roll = b.pick_number(6);
        let sub_roll = match facing {
            "right" => base_roll - 1,
            "left" => base_roll + 1,
            _ => base_roll,
        };
        loc = tripod_subroll(facing, sub_roll).to_string();
        b.log(format!("  Tripod leg sub-roll ({}): base {} -> {} -> {}", facing, base_roll, sub_roll, loc));
    } else if (mech_type == "quad" || mech_type == "quadvee") && matches!(loc.as_str(), "Left Arm" | "Right Arm" | "Left Leg" | "Right Leg") {
        loc = match loc.as_str() {
            "Left Arm" => "Front Left Leg",
            "Right Arm" => "Front Right Leg",
            "Left Leg" => "Rear Left Leg",
            _ => "Rear Right Leg",
        }
        .to_string();
    }
    loc
}

pub fn head_gone_torso_cockpit(b: &Battle, u: UnitId) -> bool {
    let m = &b.units[u];
    m.locations.get("Head").map_or(false, |h| h.destroyed) && m.cockpit_type.as_deref().unwrap_or("").to_uppercase().contains("TORSO")
}

/// The location a 2D6 hit-location roll strikes (a torso-mounted cockpit's destroyed head: re-rolled, p.203).
pub fn resolve_hit_location(b: &mut Battle, u: UnitId, loc_roll: i64, facing: &str) -> String {
    let mut loc = resolve_hit_location_once(b, u, loc_roll, facing);
    while loc == "Head" && head_gone_torso_cockpit(b, u) {
        let roll = b.roll_2d6();
        b.log(format!("  Head already destroyed (torso-mounted cockpit) - re-rolled {}.", roll));
        loc = resolve_hit_location_once(b, u, roll, facing);
    }
    loc
}

/// One hit-location lookup with no dice: the table row, quad leg names translated (a bot's lookahead uses it).
pub fn once_pure(b: &Battle, u: UnitId, loc_roll: i64, facing: &str) -> String {
    let loc = lookup(table_for(facing), loc_roll).to_string();
    let t = &b.units[u].mech_type;
    if (t == "quad" || t == "quadvee") && matches!(loc.as_str(), "Left Arm" | "Right Arm" | "Left Leg" | "Right Leg") {
        return match loc.as_str() {
            "Left Arm" => "Front Left Leg",
            "Right Arm" => "Front Right Leg",
            "Left Leg" => "Rear Left Leg",
            _ => "Rear Right Leg",
        }
        .to_string();
    }
    loc
}

