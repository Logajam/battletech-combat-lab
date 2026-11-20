// Spotting and indirect fire (session 30; Daniel, 2026-11-20: "Lets start with functionality that princess probably
// needs. Split fire, indirect fire, and artillery."). Rust only: the Python answer key is frozen.
//
// THE RULES (Core Rulebook):
//   p.70 INDIRECT FIRE: some weapons (LRM and Thunderbolt launchers...) may attack a target the attacker has no line of
//     sight to; an attacker WITH line of sight may not fire indirectly at that target. A friendly 'Mech with line of sight
//     to the target is the spotter. Modifiers, on top of the standard ones: +1 indirect fire; +1 if the spotter also
//     attacks this phase (and +1 to the spotter's own attacks); terrain counted along the spotter's line, not the firer's;
//     plus the spotter's attacker movement modifier. No aimed shots, no Artemis bonus; partial cover is ignored (unless
//     it comes from a building or water - NOT BUILT: the engine has no building partial cover, and water partial cover
//     is ignored too; a known gap, Change Record). Narc: Narc-equipped missiles may fire indirectly at a Narc-pod
//     target with no spotter (NOT BUILT yet: listed in the Change Record). TAG: a 'Mech that TAGs a target spots it
//     and ignores the spotter-attacking modifier; it may not spot a different target that turn.
//   p.62 SPOTTING: the spotter is declared with the indirect attack; it may not have declared a charge or a death from
//     above; it spots one target a turn; any number of 'Mechs may fire indirectly at that target.
//   pp.182-183: Arrow IV (and Thumper / Sniper, Daniel's wiring, RULES_REVIEW F55) adds the indirect modifiers "if
//     applicable"; artillery cannons may be fired indirectly. TO:AUE p.136: 'Mech mortars may fire indirectly with no
//     spotter (+2 more); with a spotter they follow the standard rules.
//
// HOW IT RUNS HERE. Attacks in this engine are rolled as each unit declares, so the spotters are settled FIRST, at the
// start of the Ranged Attack Phase (`declare_spotting`, in initiative order): each unit that will spot names its target
// and whether it also fires (the +1 then applies to its own attacks and to the indirect attacks it spots for). A TAG hit
// earlier in the turn is a spot of the TAG's target with no attacking penalty. The firer, when it has no line of sight,
// takes the friendly spotter of that target that gives it the lowest modifier (`best_spotter`; the rules let the firer
// choose, and the lowest is simply the best legal pick). Who spots is a bot decision: STUB_SPOT for every bot until
// the MegaMek bots get their own rule (TASK_SPECS / PROJECT_MAP backlog B); Gladiator and Hydra keep the stub (Daniel:
// "Be sure to have stub markers for features Gladiator and Hydra don't know how to do or use yet").
use crate::battle::{Battle, UnitId};
use crate::equipment::ItemId;
use crate::hex_geometry::parse_hex_label;
use crate::los::hex_distance;
use crate::mech_state::all_crew_unconscious;

pub const INDIRECT_MODIFIER: i64 = 1;
pub const SPOTTER_ATTACKING_MODIFIER: i64 = 1;

/// One spot this turn: `spotter` spots `target`; `fires`: it also attacks this phase; `tag`: the spot is a TAG hit
/// (no spotter-attacking modifier, p.70).
#[derive(Clone, Debug, PartialEq)]
pub struct Spot {
    pub spotter: UnitId,
    pub target: UnitId,
    pub fires: bool,
    pub tag: bool,
}

/// The spotter an indirect attack uses and what it adds to the Target Number.
#[derive(Clone, Debug)]
pub struct SpotterUse {
    pub spotter: UnitId,
    /// terrain along the spotter's line of sight (replaces the firer's LOS modifier)
    pub los_modifier: i64,
    /// +1 indirect, + the spotter's movement modifier, + 1 if it also attacks (not for a TAG spot)
    pub extra: i64,
    pub note: String,
}

/// Can this weapon fire indirectly (with a spotter)? LRM launchers of every kind but the Streak LRM (it needs a lock),
/// MML (its LRM rounds), Thunderbolt, 'Mech mortars, Arrow IV / Thumper / Sniper, artillery cannons.
pub fn can_fire_indirect(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    let n = crate::weapon_rules::canonical_name(b, u, w);
    (n.contains("LRM") && !n.contains("STREAK"))
        || n.contains("MML")
        || n.contains("THUNDERBOLT")
        || crate::advanced_weapons::is_mortar(b, u, w)
        || crate::weapon_profiles::is_arrow(b, u, w)
        || crate::weapon_profiles::is_art_cannon(b, u, w)
}

/// The unit's weapons that can fire indirectly.
pub fn indirect_capable(b: &mut Battle, u: UnitId) -> Vec<ItemId> {
    crate::damage_resolution::get_weapons(&b.units[u]).into_iter().filter(|w| can_fire_indirect(b, u, *w)).collect()
}

fn hex_of(b: &Battle, u: UnitId) -> Option<(i64, i64)> {
    b.units[u].hex.as_deref().and_then(|h| parse_hex_label(h).ok())
}

/// Line of sight from `from` to `to` now: (has LOS, terrain modifier along it).
pub fn sight(b: &Battle, from: UnitId, to: UnitId) -> Option<(bool, i64)> {
    let (a, t) = (hex_of(b, from)?, hex_of(b, to)?);
    let h = (crate::attack_resolution::los_height(&b.units[from]), crate::attack_resolution::los_height(&b.units[to]));
    let trace = crate::los::trace_los_path(a, t, &b.board, h.0, h.1).ok()?;
    Some((trace.result.los, trace.result.modifier))
}

/// May this unit spot at all this turn (p.62: not after declaring a charge or a death from above)?
pub fn can_spot(b: &mut Battle, u: UnitId) -> bool {
    let m = &b.units[u];
    if m.hex.is_none() || m.shutdown || all_crew_unconscious(m) || m.charging.is_some() || m.dfa.is_some() {
        return false;
    }
    !b.is_destroyed(u)
}

/// The spot `u` declared this turn, if any.
pub fn spot_of(b: &Battle, u: UnitId) -> Option<&Spot> {
    b.spots.iter().find(|s| s.spotter == u)
}

/// The +1 a spotter's OWN attacks take this phase (p.70), with the note for the log.
pub fn own_attack_modifier(b: &Battle, u: UnitId) -> i64 {
    match spot_of(b, u) {
        Some(s) if s.fires && !s.tag => SPOTTER_ATTACKING_MODIFIER,
        _ => 0,
    }
}

/// The best friendly spotter for `attacker`'s indirect attack on `target` (lowest added modifier; ties: roster order).
pub fn best_spotter(b: &mut Battle, attacker: UnitId, target: UnitId) -> Option<SpotterUse> {
    let team = b.units[attacker].team.clone();
    let spots: Vec<Spot> = b.spots.iter().filter(|s| s.target == target && s.spotter != attacker).cloned().collect();
    let mut best: Option<SpotterUse> = None;
    for s in spots {
        if b.units[s.spotter].team != team || !can_spot(b, s.spotter) {
            continue;
        }
        let Some((true, los_modifier)) = sight(b, s.spotter, target) else { continue };
        let amm = crate::combat::mode_to_amm(&b.units[s.spotter].move_mode);
        let attacking = if s.fires && !s.tag { SPOTTER_ATTACKING_MODIFIER } else { 0 };
        let extra = INDIRECT_MODIFIER + amm + attacking;
        if best.as_ref().map_or(true, |x| los_modifier + extra < x.los_modifier + x.extra) {
            let name = b.units[s.spotter].side_name.clone().unwrap_or_default();
            let note = format!(
                "indirect +{}, spotter {}{} AMM +{} [{}]{}, terrain from the spotter +{}",
                INDIRECT_MODIFIER,
                name,
                if s.tag { " (TAG)" } else { "" },
                amm,
                b.units[s.spotter].move_mode,
                if attacking > 0 { format!(", spotter also attacks +{}", attacking) } else { String::new() },
                los_modifier
            );
            best = Some(SpotterUse { spotter: s.spotter, los_modifier, extra, note });
        }
    }
    best
}

/// The Ranged Attack Phase's first step: who spots what this turn. TAG hits (made before the phase) are spots already;
/// every other unit, in `order`, may declare one (STUB_SPOT for now). `tag_spots` = (TAG designator, its target).
pub fn declare_spotting(b: &mut Battle, order: &[UnitId]) {
    let tagged: Vec<Spot> = b.spots.iter().filter(|s| s.tag).cloned().collect();
    b.spots = tagged;
    for &u in order {
        if spot_of(b, u).is_some() || !can_spot(b, u) {
            continue;
        }
        if let Some((target, fires)) = crate::stubs::stub_spot(b, u) {
            let (a_name, t_name) = (b.units[u].side_name.clone().unwrap_or_default(), b.units[target].side_name.clone().unwrap_or_default());
            b.log(format!(
                "  [Spot] {} spots {} for indirect fire (p.70){}.",
                a_name,
                t_name,
                if fires { format!("; it also fires (+{} to its own attacks and to the indirect fire it spots for)", SPOTTER_ATTACKING_MODIFIER) } else { " and holds its own fire".to_string() }
            ));
            b.spots.push(Spot { spotter: u, target, fires, tag: false });
        }
    }
}

/// A TAG hit spots its target for indirect fire (p.70), with no spotter-attacking modifier.
pub fn tag_spot(b: &mut Battle, designator: UnitId, target: UnitId) {
    b.spots.retain(|s| s.spotter != designator);
    b.spots.push(Spot { spotter: designator, target, fires: true, tag: true });
}

/// The enemies `u` could usefully spot now: ones it sees that a friend can't see but could hit indirectly (an
/// indirect-capable weapon within its long range), with how many such friends. For the spotting stub.
pub fn spot_candidates(b: &mut Battle, u: UnitId) -> Vec<(UnitId, usize, i64)> {
    let team = b.units[u].team.clone();
    let friends: Vec<UnitId> = (0..b.units.len()).filter(|&f| f != u && b.units[f].team == team && b.units[f].hex.is_some()).collect();
    let mut out = Vec::new();
    for e in crate::forces::enemies_of(b, u) {
        if b.units[e].hex.is_none() {
            continue;
        }
        let Some((true, _)) = sight(b, u, e) else { continue };
        let mut helped = 0;
        for &f in &friends {
            if b.is_destroyed(f) || b.units[f].shutdown {
                continue;
            }
            if !matches!(sight(b, f, e), Some((false, _))) {
                continue;
            }
            let d = match (hex_of(b, f), hex_of(b, e)) {
                (Some(x), Some(y)) => hex_distance(x, y),
                _ => continue,
            };
            let ws = indirect_capable(b, f);
            if ws.iter().any(|&w| crate::weapon_selection::range_bracket(b, f, w, d).is_some()) {
                helped += 1;
            }
        }
        if helped > 0 {
            let d = match (hex_of(b, u), hex_of(b, e)) {
                (Some(x), Some(y)) => hex_distance(x, y),
                _ => continue,
            };
            out.push((e, helped, d));
        }
    }
    out
}
