// Translated from INTEGRATION__tag.py (session 22): TAG designation before the Ranged Attack Phase (Core p.200).
use crate::attack_resolution::single_attack_tn;
use crate::battle::{Battle, UnitId};
use crate::damage_resolution::get_weapons;
use crate::fire_modes::bin_kinds;
use crate::mech_state::all_crew_unconscious;
use crate::weapon_profiles::is_arrow;
use crate::weapon_rules::canonical_name;

pub fn is_tag(b: &mut Battle, u: UnitId, w: usize) -> bool {
    canonical_name(b, u, w).ends_with("TAG")
}

pub fn tags(b: &mut Battle, u: UnitId) -> Vec<usize> {
    get_weapons(&b.units[u]).into_iter().filter(|w| is_tag(b, u, *w)).collect()
}

/// The 'Mech can use its own designation: a launcher with homing rounds.
pub fn uses_designation(b: &mut Battle, u: UnitId) -> bool {
    for w in get_weapons(&b.units[u]) {
        if is_arrow(b, u, w) && bin_kinds(&b.units[u], w).contains(&("homing".to_string(), String::new())) {
            return true;
        }
    }
    false
}

/// TAG designation for any number of units, in initiative order; `target_of(unit)` is the enemy it designates.
pub fn designation_units(b: &mut Battle, order: &[UnitId], target_of: &mut dyn FnMut(&mut Battle, UnitId) -> Option<UnitId>) {
    for &m in order {
        b.units[m].tag_designated = None;
    }
    for &attacker in order {
        if let Some(target) = target_of(b, attacker) {
            designate(b, attacker, target);
        }
    }
}

fn designate(b: &mut Battle, attacker: UnitId, target: UnitId) {
    let live = tags(b, attacker);
    if live.is_empty()
        || b.is_destroyed(attacker)
        || b.is_destroyed(target)
        || b.units[attacker].shutdown
        || all_crew_unconscious(&b.units[attacker])
        || b.units[attacker].charging.is_some()
        || b.units[attacker].dfa.is_some()
    {
        return;
    }
    let a_name = b.units[attacker].side_name.clone().unwrap_or_default();
    let t_name = b.units[target].side_name.clone().unwrap_or_default();
    let useful = uses_designation(b, attacker);
    if !crate::stubs::stub_fire_tag(b, &a_name, useful) {
        return;
    }
    let at_mech = single_attack_tn(b, attacker, target, &live, false);
    let at_hex = single_attack_tn(b, attacker, target, &live, true);
    if at_mech.is_none() && at_hex.is_none() {
        b.log(format!("  [TAG] {} can't designate {} (no LOS, range or arc).", a_name, t_name));
        return;
    }
    let aim = crate::stubs::stub_tag_aim(b, &a_name, at_mech.as_ref().map(|x| x.0), at_hex.as_ref().map(|x| x.0));
    let (tn, weapon, note) = if aim == "hex" { at_hex.unwrap() } else { at_mech.unwrap() };
    let roll = b.roll_2d6();
    if roll >= tn && b.units[target].tag_designated.as_deref() != Some("mech") {
        b.units[target].tag_designated = Some(aim.to_string());
    }
    let what = if aim == "hex" { format!("{}'s hex", t_name) } else { t_name };
    let wn = b.units[attacker].items[weapon].name.clone();
    b.log(format!("  [TAG] {}'s {} -> {}: needs {} ({}), rolled {} -> {}", a_name, wn, what, tn, note, roll, if roll >= tn { "DESIGNATED for this turn (p.200)" } else { "miss" }));
}
