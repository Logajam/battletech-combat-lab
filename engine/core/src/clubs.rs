// Translated from INTEGRATION__clubs.py (session 22): where clubs come from, who can hold one, the bot's pick-up rule.
use crate::battle::{Battle, UnitId};
use crate::equipment::Slot;
use crate::mech_state::Mech;

pub const ARMS: [&str; 2] = ["Left Arm", "Right Arm"];
pub const LIMBS: [&str; 9] = ["Left Arm", "Right Arm", "Left Leg", "Right Leg", "Center Leg", "Front Left Leg", "Front Right Leg", "Rear Left Leg", "Rear Right Leg"];

fn part_ok(mech: &Mech, arm: &str, part: &str) -> bool {
    if mech.destroyed_slot_info.iter().any(|((loc, _), info)| loc == arm && info.name == part) {
        return false;
    }
    mech.crits.get(arm).into_iter().flatten().any(|s| match s {
        Slot::Name(n) => n == part,
        Slot::Item(i) => mech.items[*i].name == part,
    })
}

fn has_claw(mech: &Mech, arm: &str) -> bool {
    mech.crits.get(arm).into_iter().flatten().any(|s| matches!(s, Slot::Item(i) if mech.items[*i].name.replace(' ', "").to_uppercase().contains("CLAW")))
}

/// p.79: both hands (or claws) and both shoulders, none damaged.
pub fn can_wield(mech: &Mech) -> bool {
    if mech.mech_type == "quad" || mech.mech_type == "quadvee" {
        return false;
    }
    for arm in ARMS {
        if !mech.locations.contains_key(arm) || mech.locations[arm].destroyed {
            return false;
        }
        if !part_ok(mech, arm, "Shoulder") {
            return false;
        }
        if !(part_ok(mech, arm, "Hand Actuator") || has_claw(mech, arm)) {
            return false;
        }
    }
    true
}

/// The kinds of club the mech could pick up in its hex, best first.
pub fn found_here(b: &Battle, u: UnitId) -> Vec<&'static str> {
    let m = &b.units[u];
    let hex = m.hex.clone().unwrap_or_default();
    let features = b.board.hexes.get(&hex).map(|h| &h.features);
    let mut kinds = Vec::new();
    if b.limbs_on_ground.get(&hex).copied().unwrap_or(0) != 0 {
        kinds.push("limb");
    }
    let has = |names: &[&str]| features.is_some_and(|f| names.iter().any(|n| f.0.contains_key(*n)));
    if has(&["rubble"]) {
        kinds.push("girder");
    }
    if has(&["woods", "jungle"]) {
        kinds.push("tree");
    }
    kinds
}

/// Ranged phase, after declarations: the bot's pick-up rule. Returns the kind picked up, or None.
pub fn maybe_pick_up(b: &mut Battle, u: UnitId, fired_anything: bool) -> Option<&'static str> {
    if !b.cfg.b("CLUB_PICKUP") {
        return None;
    }
    let m = &b.units[u];
    if matches!(&m.club, Some(Some(_))) || fired_anything || m.prone || m.shutdown {
        return None;
    }
    if m.charging.is_some() || m.dfa.is_some() {
        return None;
    }
    if !can_wield(m) {
        return None;
    }
    let kinds = found_here(b, u);
    let kind = *kinds.first()?;
    let hex = b.units[u].hex.clone().unwrap();
    if kind == "limb" {
        *b.limbs_on_ground.get_mut(&hex).unwrap() -= 1;
    }
    b.units[u].club = Some(Some(kind.to_string()));
    let name = b.units[u].side_name.clone().unwrap_or_default();
    b.log(format!("  [Ranged] {} picks up a {} club in {} instead of firing (p.79).", name, kind, hex));
    Some(kind)
}

/// End of a phase: limbs this mech lost drop into its hex; a club it can no longer hold is dropped there too.
pub fn after_phase(b: &mut Battle, u: UnitId) {
    let lost = b.units[u].severed_limbs.clone().unwrap_or_default();
    if !lost.is_empty() && b.units[u].hex.is_some() {
        let hex = b.units[u].hex.clone().unwrap();
        let seen = b.units[u].severed_seen.get_or_insert_with(Vec::new);
        let mut new: Vec<String> = Vec::new();
        for loc in &lost {
            if LIMBS.contains(&loc.as_str()) && !seen.contains(loc) && !new.contains(loc) {
                new.push(loc.clone());
            }
        }
        seen.extend(new.iter().cloned());
        if !new.is_empty() {
            *b.limbs_on_ground.entry(hex).or_insert(0) += new.len() as i64;
        }
        b.units[u].severed_limbs = Some(Vec::new());
    }
    let club = match &b.units[u].club {
        Some(Some(c)) => Some(c.clone()),
        _ => None,
    };
    if let Some(club) = club {
        if !can_wield(&b.units[u]) {
            let m = &b.units[u];
            let line = format!("  {} drops its {} club in {} (p.79).", m.side_name.clone().unwrap_or_default(), club, m.hex.clone().unwrap_or_else(|| "None".into()));
            b.log(line);
            if club == "limb" && b.units[u].hex.is_some() {
                let hex = b.units[u].hex.clone().unwrap();
                *b.limbs_on_ground.entry(hex).or_insert(0) += 1;
            }
            b.units[u].club = Some(None);
        }
    }
}

/// A successful club attack: a tree breaks (p.79).
pub fn used(b: &mut Battle, u: UnitId) {
    if matches!(&b.units[u].club, Some(Some(c)) if c == "tree") {
        let name = b.units[u].side_name.clone().unwrap_or_default();
        b.log(format!("    {}'s tree club breaks.", name));
        b.units[u].club = Some(None);
    }
}
