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

/// An enemy a unit could designate with TAG and the to-hit number for the 'Mech and for its hex (None: not possible).
#[derive(Clone, Debug)]
pub struct TagCandidate {
    pub target: UnitId,
    pub tn_mech: Option<i64>,
    pub tn_hex: Option<i64>,
}

/// Can this unit designate at all this turn (it has a working TAG and is able to act)?
fn can_designate(b: &mut Battle, attacker: UnitId) -> bool {
    !(tags(b, attacker).is_empty()
        || b.is_destroyed(attacker)
        || b.units[attacker].shutdown
        || all_crew_unconscious(&b.units[attacker])
        || b.units[attacker].charging.is_some()
        || b.units[attacker].dfa.is_some())
}

/// The enemies `attacker` could TAG now, with their to-hit numbers (for a person's choice).
pub fn candidates(b: &mut Battle, attacker: UnitId) -> Vec<TagCandidate> {
    if !can_designate(b, attacker) {
        return Vec::new();
    }
    let live = tags(b, attacker);
    let mut out = Vec::new();
    for t in crate::forces::enemies_of(b, attacker) {
        if b.is_destroyed(t) || b.units[t].hex.is_none() {
            continue;
        }
        let m = single_attack_tn(b, attacker, t, &live, false).map(|x| x.0);
        let h = single_attack_tn(b, attacker, t, &live, true).map(|x| x.0);
        if m.is_some() || h.is_some() {
            out.push(TagCandidate { target: t, tn_mech: m, tn_hex: h });
        }
    }
    out
}

/// TAG designation for any number of units, in initiative order; `target_of(unit)` is the enemy it designates. `chosen` lets a
/// person decide for their own units (None: not theirs, the stubs decide as before).
pub fn designation_units(b: &mut Battle, order: &[UnitId], target_of: &mut dyn FnMut(&mut Battle, UnitId) -> Option<UnitId>, chosen: &mut dyn FnMut(&mut Battle, UnitId, &[TagCandidate]) -> Option<Option<(UnitId, &'static str)>>) {
    for &m in order {
        b.units[m].tag_designated = None;
    }

    // a new turn's spots start here: TAG hits below are the first (spotting.rs; p.70)
    b.spots.clear();
    for &attacker in order {
        let cands = candidates(b, attacker);
        if !cands.is_empty() {
            if let Some(choice) = chosen(b, attacker, &cands) {
                if let Some((target, aim)) = choice {
                    designate_with(b, attacker, target, aim);
                }
                continue;
            }
        }
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
    roll_designation(b, attacker, target, aim, at_mech, at_hex);
}

/// A person's designation: `aim` "mech" or "hex" of `target`.
fn designate_with(b: &mut Battle, attacker: UnitId, target: UnitId, aim: &'static str) {
    let live = tags(b, attacker);
    let at_mech = single_attack_tn(b, attacker, target, &live, false);
    let at_hex = single_attack_tn(b, attacker, target, &live, true);
    if (aim == "hex" && at_hex.is_none()) || (aim != "hex" && at_mech.is_none()) {
        return;
    }
    roll_designation(b, attacker, target, aim, at_mech, at_hex);
}

fn roll_designation(b: &mut Battle, attacker: UnitId, target: UnitId, aim: &'static str, at_mech: Option<(i64, usize, String)>, at_hex: Option<(i64, usize, String)>) {
    let a_name = b.units[attacker].side_name.clone().unwrap_or_default();
    let t_name = b.units[target].side_name.clone().unwrap_or_default();
    let (tn, weapon, note) = if aim == "hex" { at_hex.unwrap() } else { at_mech.unwrap() };
    let roll = b.roll_2d6();
    // the number's parts, as the ranged attack lines show theirs (bug B16, Daniel 2026-11-22: "TAG's to-hit number is not expanded";
    // a known change from the answer key, stage6_battles.rs `known_changes`); read only, after the roll
    let parts = crate::attack_resolution::weapon_attack_parts(b, attacker, target, weapon, aim == "hex").unwrap_or_default();
    // written as the [Ranged] lines write theirs: "AMM 1 [Walk]" (the label's bracket goes after the number)
    let parts = parts
        .iter()
        .map(|(k, v)| match k.split_once(' ') {
            Some((name, note)) if note.starts_with('[') => format!("{} {} {}", name, v, note),
            _ => format!("{} {}", k, v),
        })
        .collect::<Vec<_>>()
        .join(" + ");
    if roll >= tn && b.units[target].tag_designated.as_deref() != Some("mech") {
        b.units[target].tag_designated = Some(aim.to_string());
    }
    if roll >= tn {
        // p.70: a 'Mech that hits a target with TAG also spots it for indirect fire (no spotter-attacking modifier)
        crate::spotting::tag_spot(b, attacker, target);
    }
    let what = if aim == "hex" { format!("{}'s hex", t_name) } else { t_name };
    let wn = b.units[attacker].items[weapon].name.clone();
    b.log(format!("  [TAG] {}'s {} -> {}: needs {} ({}; {}), rolled {} -> {}", a_name, wn, what, tn, note, parts, roll, if roll >= tn { "DESIGNATED for this turn (p.200)" } else { "miss" }));
    b.ev("TAG_DESIGNATE").unit(attacker).other(target).sub(if aim == "hex" { "hex" } else { "mech" }).what(&wn).tn(tn).roll(roll).ok(roll >= tn).emit(b);
}
