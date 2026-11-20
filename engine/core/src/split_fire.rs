// Split fire: one 'Mech, several targets in a turn (session 30; Daniel, 2026-11-20: "split fire yes. Completeness and the
// wiring in place for when our bots expand their minds"). Rust only: the Python answer key is frozen.
//
// THE RULE (Core p.64, Multiple Targets Modifier): a 'Mech may engage as many targets as it has weapons. One is the
// primary target; if any declared target is in the forward arc (after the torso twist), the primary must be one of
// those. Every other target is a secondary target: +1 to every ranged attack on it. A 'Mech has one primary target a turn
// even with two forward arcs (a twist with leg weapons). A 'Mech with active stealth armor cannot be attacked as a
// secondary target (p.64, p.202). (A dedicated gunnery officer may take three primaries, p.? appendices - not built: no
// crew rules here.)
//
// HOW IT RUNS HERE. Attacks are declared unit by unit and rolled as declared (attack_resolution). A unit first declares
// on its primary target as before (its bot's `target_of`), which also fixes its torso twist / arm flip for the turn;
// then each secondary target in turn, with the weapons not yet used, the twist already chosen, the heat already
// committed counted, and +1. Every DeclaredAttack carries its own target, so anti-missile fire and damage go to the
// right 'Mech.
//
// WHO SPLITS FIRE: a bot decision. STUB_SPLIT_FIRE (default "never"). MegaMek's Princess and CASPAR fire an ordinary
// 'Mech at ONE target (their MultiTargetFireControl is only for Multi-Tasker / dedicated gunner crews and the Multi-Trac
// quirk, none of which this engine has), so "never" is also their faithful behaviour. Gladiator / Hydra do not know how
// to split fire yet (Daniel, 2026-11-20: "stub markers for features Gladiator and Hydra don't know how to do or use yet").
use crate::battle::{Battle, UnitId};
use crate::equipment::ItemId;

/// The +1 on every ranged attack on a secondary target (p.64).
pub const SECONDARY_MODIFIER: i64 = 1;

/// One attacker's declarations so far this Ranged Attack Phase.
#[derive(Clone, Debug, PartialEq)]
pub struct SplitState {
    pub attacker: UnitId,
    pub primary: UnitId,
    /// weapons already declared this phase (not available against another target)
    pub used: Vec<ItemId>,
    /// weapon heat already committed this phase
    pub heat: i64,
}

pub fn state_of(b: &Battle, attacker: UnitId) -> Option<&SplitState> {
    b.split_fire.iter().find(|s| s.attacker == attacker)
}

/// Is `target` a secondary target of `attacker` (it has declared on another primary this phase)?
pub fn is_secondary(b: &Battle, attacker: UnitId, target: UnitId) -> bool {
    state_of(b, attacker).is_some_and(|s| s.primary != target)
}

/// A declaration was made: the first one names the primary target; every one adds its weapons and heat.
pub fn record(b: &mut Battle, attacker: UnitId, target: UnitId, weapons: &[ItemId], heat: i64) {
    if let Some(s) = b.split_fire.iter_mut().find(|s| s.attacker == attacker) {
        s.used.extend_from_slice(weapons);
        s.heat += heat;
        return;
    }
    b.split_fire.push(SplitState { attacker, primary: target, used: weapons.to_vec(), heat });
}

/// Is the target in the attacker's forward arc as it stands now (after its declared twist), torso or forward legs?
pub fn in_forward_arc(b: &Battle, attacker: UnitId, target: UnitId) -> bool {
    let (Some(a), Some(t)) = (b.units[attacker].hex.as_deref(), b.units[target].hex.as_deref()) else { return false };
    let (Ok(a), Ok(t)) = (crate::hex_geometry::parse_hex_label(a), crate::hex_geometry::parse_hex_label(t)) else { return false };
    let m = &b.units[attacker];
    let facing = crate::hex_geometry::compass_to_facing(&m.facing).unwrap();
    let key = crate::arcs::key_for(&crate::arcs::arcs_between(a, t), facing, &crate::arcs::current_action(m), &crate::arcs::leg_offsets(m));
    key.torso_arc == crate::arcs::FORWARD || !key.legs_forward.is_empty()
}

/// Why `target` may not be a secondary target of `attacker` now (p.64), or None.
pub fn refusal(b: &Battle, attacker: UnitId, target: UnitId) -> Option<String> {
    let s = state_of(b, attacker)?;
    if crate::equipment_systems::active_stealth(&b.units[target]).contains(&"stealth_armor") {
        return Some("its active stealth armor means it can't be a secondary target (pp.64, 202)".to_string());
    }
    if in_forward_arc(b, attacker, target) && !in_forward_arc(b, attacker, s.primary) {
        return Some("it is in the forward arc and the primary target is not: the primary must be a forward-arc target (p.64)".to_string());
    }
    None
}
