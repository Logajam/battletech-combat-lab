// Translated from INTEGRATION__physical.py (session 22). Part 1: the location tables; the Physical Attack Phase follows.
use crate::battle::{Battle, UnitId};
use crate::hit_location::resolve_hit_location;
use crate::mech_state::has_torso_cockpit;

/// (1-3, 4-6), p.81
pub fn kick_table(side: &str) -> (&'static str, &'static str) {
    match side {
        "left" => ("Left Leg", "Left Leg"),
        "right" => ("Right Leg", "Right Leg"),
        "front" | "rear" => ("Right Leg", "Left Leg"),
        other => panic!("KeyError: {}", other),
    }
}

pub fn punch_table(side: &str) -> [&'static str; 6] {
    match side {
        "left" => ["Left Torso", "Left Torso", "Center Torso", "Left Arm", "Left Arm", "Head"],
        "right" => ["Right Torso", "Right Torso", "Center Torso", "Right Arm", "Right Arm", "Head"],
        "front" | "rear" => ["Right Arm", "Right Torso", "Center Torso", "Left Torso", "Left Arm", "Head"],
        other => panic!("KeyError: {}", other),
    }
}

/// The location a physical attack's hit strikes: the standard table (2D6), or the kick / punch table (1D6).
pub fn location(b: &mut Battle, table: &str, side: &str, target: UnitId) -> String {
    if table == "standard" {
        let roll = b.roll_2d6();
        return resolve_hit_location(b, target, roll, side);
    }
    let die = b.pick_number(6);
    let mut loc: String;
    if table == "kick" {
        let k = kick_table(side);
        loc = (if die <= 3 { k.0 } else { k.1 }).to_string();
    } else {
        loc = punch_table(side)[(die - 1) as usize].to_string();
        while loc == "Head" && b.units[target].locations["Head"].destroyed && has_torso_cockpit(&b.units[target]) {
            let die = b.pick_number(6);
            loc = punch_table(side)[(die - 1) as usize].to_string();
        }
    }
    let t = &b.units[target];
    if t.mech_type == "quad" || t.mech_type == "quadvee" {
        loc = match loc.as_str() {
            "Left Arm" => "Front Left Leg".to_string(),
            "Right Arm" => "Front Right Leg".to_string(),
            "Left Leg" => if side == "rear" { "Rear Left Leg" } else { "Front Left Leg" }.to_string(),
            "Right Leg" => if side == "rear" { "Rear Right Leg" } else { "Front Right Leg" }.to_string(),
            _ => loc,
        };
    }
    loc
}
