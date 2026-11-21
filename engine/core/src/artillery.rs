// On-board artillery (session 30; Daniel, 2026-11-20: "Artillery has to be on board with what the units can use"; no
// Battlefield Support strikes or Assets). Rust only: the Python answer key is frozen.
//
// THE RULES (Core Rulebook):
//   p.182 ARROW IV (and Thumper / Sniper launchers, which this project fires by the same rules: Daniel, RULES_REVIEW F55):
//     fired at a hex. Close (7-17 hexes): lands in the same phase (built before, attack_resolution). Distant (18 hexes or
//     more): announced in the Ranged Attack Phase with the target hex recorded, ammunition and heat spent that turn, the
//     attacker movement and indirect modifiers of that turn kept; it lands in the NEXT turn's Ranged Attack Phase. Base
//     Target Number Gunnery + 4 (+ indirect modifiers if applicable); never modified for range, target movement or an
//     immobile target. A miss scatters: 1D6 on the Scatter Diagram (p.155) for the direction, distance = the Margin of
//     Failure for a distant shot (half of it, rounded up, for a close one); never outside the launcher's firing arc (it
//     lands in the last hex of its path inside the arc). No aimed shot, no anti-missile systems.
//   pp.182-183 AREA EFFECT: the full damage strikes every unit in the hex it lands in and the splash every unit in the
//     hexes next to it - friend or foe, in 5-point groupings (p.181 AE).
//   The maximum ranges (TO:AR, in mapsheets: Arrow IV 8 / 9) are far beyond any board here, so a distant shot has no
//   upper limit on the board.
//
// WHO FIRES A DISTANT SHOT: a bot decision. STUB_DISTANT_ARTILLERY (default "never": the bots' own artillery targeting is
// built elsewhere - Princess / CASPAR from MegaMek's ArtilleryTargetingControl, which Hydra borrows (2026-11-21); Gladiator
// has none yet, Daniel 2026-11-20 "stub markers for features Gladiator and Hydra don't know how to do or use yet").
use crate::battle::{Battle, UnitId};
use crate::equipment::ItemId;
use crate::hex_geometry;
use crate::los::hex_distance;

/// Distant artillery fire starts here (p.182: 18 hexes or more).
pub const DISTANT_MIN: i64 = 18;
/// No upper limit on the board (the TO:AR maximums are 8+ mapsheets).
pub const DISTANT_REACH: i64 = 999;
/// The longest scatter path looked at when the firing arc is recorded.
const MAX_SCATTER: i64 = 40;

/// A distant shot in flight: announced on `fired_turn`, lands in the next turn's Ranged Attack Phase.
#[derive(Clone, Debug, PartialEq)]
pub struct PendingStrike {
    pub attacker: UnitId,
    pub weapon: ItemId,
    pub fired_turn: i64,
    /// the target hex, and where the launcher stood when it fired (the direction of the attack)
    pub impact: (i64, i64),
    pub from: (i64, i64),
    /// the Target Number, as announced (that turn's attacker movement and indirect modifiers included)
    pub tn: i64,
    pub damage: i64,
    pub splash: i64,
    /// how many hexes a scatter may go in each Scatter Diagram direction before it leaves the launcher's firing arc
    /// (recorded when it fired: the launcher may have moved since)
    pub arc_steps: [i64; 6],
}

fn hex_xy(b: &Battle, u: UnitId) -> Option<(i64, i64)> {
    b.units[u].hex.as_deref().and_then(|h| hex_geometry::parse_hex_label(h).ok())
}

/// How far a scatter may run from `impact` in each direction and stay in `weapon`'s firing arc now.
pub fn arc_steps(b: &Battle, attacker: UnitId, weapon: ItemId, impact: (i64, i64)) -> [i64; 6] {
    let mut out = [0; 6];
    for (d, slot) in out.iter_mut().enumerate() {
        let (dx, dy) = hex_geometry::FACING_DELTAS[d];
        let mut s = 0;
        while s < MAX_SCATTER && crate::attack_resolution::in_firing_arc(b, attacker, weapon, (impact.0 + dx * (s + 1), impact.1 + dy * (s + 1))) {
            s += 1;
        }
        *slot = s;
    }
    out
}

/// A distant shot is announced (p.182): ammunition and heat are already spent by the caller; this records it.
/// The impact hex is the target's, unless Princess aimed the shot at another hex (princess_artillery.rs).
pub fn announce(b: &mut Battle, attacker: UnitId, weapon: ItemId, target: UnitId, tn: i64, damage: i64, splash: i64) {
    let turn = b.units[attacker].turn_number;
    let aimed = crate::princess_artillery::aimed_hex(b, attacker, weapon, target);
    let (Some(from), Some(impact)) = (hex_xy(b, attacker), aimed.or_else(|| hex_xy(b, target))) else { return };
    let arc = arc_steps(b, attacker, weapon, impact);
    let wname = b.units[attacker].items[weapon].name.clone();
    let label = hex_geometry::hex_label(impact.0, impact.1).unwrap_or_default();
    b.log(format!(
        "    {} fires DISTANT at hex {} ({} hexes; lands next turn, needs {} then; p.182).",
        wname,
        label,
        hex_distance(from, impact),
        tn
    ));
    b.pending_artillery.push(PendingStrike { attacker, weapon, fired_turn: turn, impact, from, tn, damage, splash, arc_steps: arc });
}

/// The distant shots landing in this Ranged Attack Phase: those announced on an earlier turn.
pub fn resolve_pending(b: &mut Battle, turn: i64) {
    let (due, keep): (Vec<PendingStrike>, Vec<PendingStrike>) = std::mem::take(&mut b.pending_artillery).into_iter().partition(|s| s.fired_turn < turn);
    b.pending_artillery = keep;
    for s in due {
        let wname = b.units[s.attacker].items[s.weapon].name.clone();
        let a_name = b.units[s.attacker].side_name.clone().unwrap_or_default();
        let label = hex_geometry::hex_label(s.impact.0, s.impact.1).unwrap_or_default();
        let roll = b.roll_2d6();
        if roll >= s.tn {
            b.log(format!("  [Artillery] {}'s distant {} lands on hex {}: needs {}, rolled {} -> HIT (p.182).", a_name, wname, label, s.tn, roll));
            area_strike(b, s.from, s.impact, s.damage, s.splash, None);
            continue;
        }
        // p.182: a distant miss scatters its full Margin of Failure, held inside the launcher's arc as it fired
        let mof = s.tn - roll;
        let direction = b.pick_number(6) - 1;
        let steps = mof.min(s.arc_steps[direction as usize]);
        let (dx, dy) = hex_geometry::FACING_DELTAS[direction as usize];
        let land = (s.impact.0 + dx * steps, s.impact.1 + dy * steps);
        let land_label = hex_geometry::hex_label(land.0, land.1).ok();
        let on_board = land_label.as_ref().is_some_and(|l| b.board.hexes.contains_key(l));
        b.log(format!(
            "  [Artillery] {}'s distant {} at hex {}: needs {}, rolled {} -> miss by {}; scatters {} hex{} (direction {}){} to {}{}.",
            a_name,
            wname,
            label,
            s.tn,
            roll,
            mof,
            mof,
            if mof == 1 { "" } else { "es" },
            direction + 1,
            if steps < mof { format!(", held to {} by the firing arc", steps) } else { String::new() },
            land_label.clone().unwrap_or_else(|| "off the board".to_string()),
            if on_board { "" } else { " - off the board, no effect" }
        ));
        if on_board {
            area_strike(b, s.from, land, s.damage, s.splash, None);
        }
    }
}

/// Area-effect damage landing on `impact` (pp.182-183): `damage` to every unit standing in the hex, `splash` to every unit
/// in the six hexes next to it, friend or foe, roster order. The hit-location side is taken from `from` (the launcher)
/// for the impact hex and from the impact hex for its ring. `skip`: a unit the caller has already dealt with.
pub fn area_strike(b: &mut Battle, from: (i64, i64), impact: (i64, i64), damage: i64, splash: i64, skip: Option<UnitId>) {
    for u in 0..b.units.len() {
        if Some(u) == skip || b.is_destroyed(u) {
            continue;
        }
        let Some(xy) = hex_xy(b, u) else { continue };
        let d = hex_distance(impact, xy);
        let (amount, origin, where_) = match d {
            0 => (damage, from, "in the impact hex"),
            1 => (splash, impact, "next to the impact"),
            _ => continue,
        };
        if amount <= 0 || origin == xy {
            continue;
        }
        let name = b.units[u].side_name.clone().unwrap_or_default();
        let facing = hex_geometry::compass_to_facing(&b.units[u].facing).unwrap();
        let side = crate::attack_resolution::attack_side(b, origin, xy, facing, crate::attack_resolution::standing(), crate::attack_resolution::standing());
        b.log(format!("      {} is {}: {} area-effect damage.", name, where_, amount));
        crate::attack_resolution::resolve_area(b, u, amount, side, crate::attack_resolution::Cover::No);
    }
}
