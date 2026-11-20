// Translated from INTEGRATION__advanced_weapons.py (session 22): TO:AUE / Interstellar Operations weapons - HVAC,
// Taser, TSEMP, iATM IMP, inferno missiles, nail guns, mortars.
// Not yet translated (they need modules that come with attack resolution): hvac_smoke (smoke, combat direction),
// nail_worth (expected_damage), and outside_heat's heat-dissipating-armor test (attack_resolution).
use crate::battle::{Battle, UnitId};
use crate::damage_resolution::{apply_explosion, get_weapons};
use crate::equipment::{ItemId, Slot};
use crate::mech_state::SlotInfo;
use crate::weapon_rules::canonical_name;

pub const TASER_INTERFERENCE: i64 = 2;
pub const TASER_HEAT: i64 = 5;
pub const TASER_MAX_TONNAGE: i64 = 100;
pub const MORTAR_DIRECT_MODIFIER: i64 = 3;
pub const MORTAR_INDIRECT_MODIFIER: i64 = 3;
pub const HVAC_MISFEED_ROLL: i64 = 2;
pub const TSEMP_INTERFERENCE: i64 = 2;
pub const TSEMP_HEAVY_TONS: i64 = 100;
pub const TSEMP_HEAVY_MODIFIER: i64 = -2;
pub const TSEMP_NO_EFFECT_TONS: i64 = 200;
pub const TSEMP_ICE_MODIFIER: i64 = -1;
pub const TSEMP_STACK_MAX: i64 = 4;
pub const TSEMP_MISFEED_ROLL: i64 = 2;
pub const IMP_PER_STEP: i64 = 3;
pub const IMP_MAX: i64 = 2;
pub const INFERNO_HEAT_PER_MISSILE: i64 = 2;
pub const NAIL_DIE: i64 = 6;
pub const NAIL_EXPECTED: f64 = 3.5;

fn taser_column_shutdown_roll(col: &str) -> i64 {
    if col == "BattleMech" { 11 } else { 8 }
}
fn taser_turns(col: &str) -> i64 {
    if col == "BattleMech" { 3 } else { 4 }
}
fn tsemp_table(col: &str) -> (i64, i64) {
    if col == "BattleMech" { (7, 9) } else { (6, 8) }
}

pub fn is_hvac(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    canonical_name(b, u, w).contains("HYPERVELOCITY")
}
pub fn is_mortar(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    canonical_name(b, u, w).contains("MORTAR")
}
pub fn is_taser(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    canonical_name(b, u, w).contains("TASER")
}
pub fn is_tsemp(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    canonical_name(b, u, w).contains("TSEMP")
}
pub fn is_nail_gun(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    let n = canonical_name(b, u, w);
    n.contains("NAIL") || n.contains("RIVET")
}

/// Fluid guns (water) and VGLs (fragmentation): no effect on 'Mechs.
pub fn no_effect_on_mechs(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    let n = canonical_name(b, u, w);
    n.contains("FLUIDGUN") || n.contains("GRENADELAUNCHER")
}

pub fn no_effect_ids(b: &mut Battle, u: UnitId) -> Vec<ItemId> {
    get_weapons(&b.units[u]).into_iter().filter(|w| no_effect_on_mechs(b, u, *w)).collect()
}

pub fn destroy_all_slots(b: &mut Battle, u: UnitId, weapon: ItemId) {
    let locs: Vec<String> = b.units[u].crits.keys().cloned().collect();
    for loc in locs {
        let n = b.units[u].crits[&loc].len();
        for i in 0..n {
            if b.units[u].crits[&loc][i] == Slot::Item(weapon) {
                let name = b.units[u].items[weapon].name.clone();
                b.units[u].destroyed_slot_info.insert((loc.clone(), i), SlotInfo { name, instance_id: Some(weapon) });
                b.units[u].crits.get_mut(&loc).unwrap()[i] = Slot::name("DESTROYED");
            }
        }
    }
}

/// p.97: one round's damage as an ammunition explosion in the HVAC's location, and every slot of the HVAC destroyed.
pub fn hvac_misfeed(b: &mut Battle, attacker: UnitId, weapon: ItemId, location: &str) {
    let (name, dmg) = (b.units[attacker].items[weapon].name.clone(), b.units[attacker].items[weapon].damage_per_shot);
    b.log(format!(
        "      {} MISFEEDS (to-hit roll 2, TO:AUE p.97): the round's propellant ignites in the barrel - {} internal explosion damage in {}.",
        name,
        dmg.map_or("None".to_string(), |d| d.to_string()),
        location
    ));
    destroy_all_slots(b, attacker, weapon);
    // the chambered round explodes like ammunition: a throw-away item in the arena
    let mut round = crate::equipment::Equipment::simple(&format!("{} round", name), 1, true, Some(dmg.unwrap_or(0)), true);
    round.category = Some("ammo".to_string());
    b.units[attacker].items.push(round);
    let id = b.units[attacker].items.len() - 1;
    apply_explosion(b, attacker, id, location);
}

fn taser_column(b: &Battle, target: UnitId) -> &'static str {
    if b.units[target].is_industrial.unwrap_or(false) { "IndustrialMech" } else { "BattleMech" }
}

/// A Taser hit (pp.157-158) - after its 1 point of damage.
pub fn taser_hit(b: &mut Battle, _attacker: UnitId, target: UnitId, turn: i64) {
    if b.is_destroyed(target) {
        return;
    }
    if b.units[target].mass.unwrap_or(0) > TASER_MAX_TONNAGE {
        b.log(format!("      Taser: no effect on a unit over {} tons (TO:AUE p.157).", TASER_MAX_TONNAGE));
        return;
    }
    let column = taser_column(b, target);
    let (need, turns) = (taser_column_shutdown_roll(column), taser_turns(column));
    let roll = b.roll_2d6();
    let until = turn + turns;
    let name = b.units[target].side_name.clone().unwrap_or_default();
    if roll >= need {
        if !b.units[target].shutdown {
            b.units[target].shutdown = true;
            b.units[target].taser_shutdown_until = Some(Some(until));
            b.log(format!("      Taser effect roll {} (needs {}): {} SHUTS DOWN through turn {} (TO:AUE p.158).", roll, need, name, until));
        } else {
            b.log(format!("      Taser effect roll {}: {} is already shut down.", roll, name));
        }
        return;
    }
    b.units[target].taser_interference_until = Some(Some(until));
    b.log(format!(
        "      Taser effect roll {} (shutdown needs {}): interference - +{} to {}'s Piloting and Gunnery target numbers and {} heat a turn through turn {} (TO:AUE p.158).",
        roll, need, TASER_INTERFERENCE, name, TASER_HEAT, until
    ));
}

pub fn interference(m: &crate::mech_state::Mech) -> i64 {
    if matches!(m.taser_interference_until, Some(Some(_))) { TASER_INTERFERENCE } else { 0 }
}

pub fn taser_heat(m: &crate::mech_state::Mech) -> i64 {
    if interference(m) != 0 { TASER_HEAT } else { 0 }
}

/// Taser / TSEMP / IMP effects end in the End Phase of their last turn.
pub fn end_phase(b: &mut Battle, u: UnitId, turn: i64) {
    let name = b.units[u].side_name.clone().unwrap_or_default();
    if let Some(Some(until)) = b.units[u].taser_interference_until {
        if turn >= until {
            b.units[u].taser_interference_until = Some(None);
            b.log(format!("  [End] {}: Taser interference ends.", name));
        }
    }
    tsemp_end_phase(b, u, turn);
    imp_end_phase(b, u, turn);
    for (key, what) in [("taser_shutdown_until", "Taser"), ("tsemp_shutdown_until", "TSEMP")] {
        let until = if key == "taser_shutdown_until" { b.units[u].taser_shutdown_until } else { b.units[u].tsemp_shutdown_until };
        let until = match until {
            Some(Some(t)) => t,
            _ => continue,
        };
        if turn < until {
            continue;
        }
        if key == "taser_shutdown_until" {
            b.units[u].taser_shutdown_until = Some(None);
        } else {
            b.units[u].tsemp_shutdown_until = Some(None);
        }
        if held_down(&b.units[u]) {
            b.log(format!("  [End] {}: the {} shutdown ends; another effect still holds it down.", name, what));
        } else if b.units[u].current_heat < 14 {
            b.units[u].shutdown = false;
            b.log(format!("  [End] {}: the {} shutdown ends - it powers up.", name, what));
        } else {
            let h = b.units[u].current_heat;
            b.log(format!("  [End] {}: the {} shutdown ends; heat {} - it must restart as normal.", name, what, h));
        }
    }
}

/// Still shut down by a Taser or a TSEMP.
pub fn held_down(m: &crate::mech_state::Mech) -> bool {
    matches!(m.taser_shutdown_until, Some(Some(_))) || matches!(m.tsemp_shutdown_until, Some(Some(_)))
}

/// Weapons that may fire indirectly with no spotter: 'Mech mortars (p.136).
pub fn indirect_weapons(b: &mut Battle, u: UnitId) -> Vec<ItemId> {
    get_weapons(&b.units[u]).into_iter().filter(|w| is_mortar(b, u, *w)).collect()
}

fn engine_text(m: &crate::mech_state::Mech) -> String {
    m.engine_desc.as_deref().unwrap_or("").to_uppercase()
}

pub fn ice_engine(m: &crate::mech_state::Mech) -> bool {
    engine_text(m).replace('(', " ").split_whitespace().any(|w| w == "ICE")
}

pub fn fusion_engine(m: &crate::mech_state::Mech) -> bool {
    let t = engine_text(m);
    !["ICE", "FUEL CELL", "FUELCELL", "FISSION", "STEAM", "BATTERY", "SOLAR", "NONE"].iter().any(|k| t.contains(k))
}

pub fn tsemp_repeating(b: &mut Battle, u: UnitId, w: ItemId) -> bool {
    canonical_name(b, u, w).contains("REPEATING")
}

pub fn tsemp_interference(m: &crate::mech_state::Mech) -> i64 {
    if matches!(m.tsemp_interference_until, Some(Some(_))) { TSEMP_INTERFERENCE } else { 0 }
}

fn interfere(b: &mut Battle, u: UnitId, turn: i64, why: &str) {
    let cur = match b.units[u].tsemp_interference_until {
        Some(Some(t)) => t,
        _ => 0,
    };
    b.units[u].tsemp_interference_until = Some(Some((turn + 1).max(cur)));
    let name = b.units[u].side_name.clone().unwrap_or_default();
    b.log(format!("      {}: TSEMP interference on {} through turn {} - +{} to hit with weapons, as if inside hostile ECM (IO p.91).", why, name, turn + 1, TSEMP_INTERFERENCE));
}

/// A TSEMP fires (at its attack roll, hit or miss). Returns False if a Repeating TSEMP blew up on a roll of 2.
pub fn tsemp_fired(b: &mut Battle, attacker: UnitId, weapon: ItemId, roll: i64, turn: i64, location: &str) -> bool {
    let wname = b.units[attacker].items[weapon].name.clone();
    if tsemp_repeating(b, attacker, weapon) && roll == TSEMP_MISFEED_ROLL {
        b.log(format!("      {}: attack roll 2 - the effects of a critical hit (IO p.88): it explodes, no effect on the target.", wname));
        destroy_all_slots(b, attacker, weapon);
        b.units[attacker].items[weapon].exploded = true;
        apply_explosion(b, attacker, weapon, location);
        return false;
    }
    if b.units[attacker].items[weapon].one_shot == Some(true) {
        b.units[attacker].items[weapon].is_explosive = false;
        b.units[attacker].items[weapon].explosion_damage = 0;
    } else if !tsemp_repeating(b, attacker, weapon) {
        b.units[attacker].items[weapon].tsemp_recharge_until = Some(Some(turn + 1));
    }
    let an = b.units[attacker].side_name.clone().unwrap_or_default();
    interfere(b, attacker, turn, &format!("{} fired its {}", an, wname));
    true
}

pub fn recharging(m: &crate::mech_state::Mech, w: ItemId) -> bool {
    matches!(m.items[w].tsemp_recharge_until, Some(Some(_)))
}

/// A TSEMP hit (IO pp.90-91): the Effects roll.
pub fn tsemp_hit(b: &mut Battle, _attacker: UnitId, target: UnitId, turn: i64) {
    if b.is_destroyed(target) {
        return;
    }
    let mass = b.units[target].mass.unwrap_or(0);
    let name = b.units[target].side_name.clone().unwrap_or_default();
    if mass >= TSEMP_NO_EFFECT_TONS {
        b.log(format!("      TSEMP: no effect on a unit of {} tons or more (IO p.91).", TSEMP_NO_EFFECT_TONS));
        return;
    }
    let (seen_turn, count) = match &b.units[target].tsemp_hits {
        Some(v) if v.len() == 2 => (Some(v[0]), v[1]),
        _ => (None, 0),
    };
    let count = if seen_turn == Some(turn) { count + 1 } else { 1 };
    b.units[target].tsemp_hits = Some(vec![turn, count]);
    let mut mods: Vec<(i64, String)> = Vec::new();
    if mass >= TSEMP_HEAVY_TONS {
        mods.push((TSEMP_HEAVY_MODIFIER, "100+ tons".to_string()));
    }
    if ice_engine(&b.units[target]) {
        mods.push((TSEMP_ICE_MODIFIER, "ICE engine".to_string()));
    }
    if count > 1 {
        mods.push(((count - 1).min(TSEMP_STACK_MAX), format!("TSEMP hit {} this turn", count)));
    }
    let raw = b.roll_2d6();
    let result = 2.max(raw + mods.iter().map(|(m, _)| m).sum::<i64>());
    let column = taser_column(b, target);
    let (interfere_at, shutdown_at) = tsemp_table(column);
    let modtext: String = mods.iter().map(|(m, why)| format!(" {:+} ({})", m, why)).collect();
    let note = format!("TSEMP effects roll {}{} = {} ({})", raw, modtext, result, column);
    if result >= shutdown_at {
        let cur = match b.units[target].tsemp_shutdown_until {
            Some(Some(t)) => t,
            _ => 0,
        };
        b.units[target].tsemp_shutdown_until = Some(Some((turn + 1).max(cur)));
        b.units[target].shutdown = true;
        b.log(format!("      {}: {} SHUTS DOWN through turn {} (IO p.91).", note, name, turn + 1));
    } else if result >= interfere_at {
        b.log(format!("      {}: interference.", note));
        interfere(b, target, turn, "TSEMP hit");
    } else {
        b.log(format!("      {}: no effect.", note));
    }
}

fn tsemp_end_phase(b: &mut Battle, u: UnitId, turn: i64) {
    if let Some(Some(until)) = b.units[u].tsemp_interference_until {
        if turn >= until {
            b.units[u].tsemp_interference_until = Some(None);
            let name = b.units[u].side_name.clone().unwrap_or_default();
            b.log(format!("  [End] {}: TSEMP interference ends.", name));
        }
    }
    for w in get_weapons(&b.units[u]) {
        if let Some(Some(until)) = b.units[u].items[w].tsemp_recharge_until {
            if turn >= until {
                b.units[u].items[w].tsemp_recharge_until = Some(None);
            }
        }
    }
}

/// TSEMP Cannons that fired last turn (can't fire this turn).
pub fn recharging_ids(b: &Battle, u: UnitId) -> Vec<ItemId> {
    get_weapons(&b.units[u]).into_iter().filter(|w| recharging(&b.units[u], *w)).collect()
}

/// Inferno missiles that strike (Core p.192): 2 heat each, no damage. Needs `has_heat_dissipating_armor`.
pub fn inferno_hit(b: &mut Battle, target: UnitId, missiles: i64, source: &str, heat_dissipating_armor: bool) {
    b.log(format!("      {} inferno missile{}: no damage, {} heat each (p.192).", missiles, if missiles != 1 { "s" } else { "" }, INFERNO_HEAT_PER_MISSILE));
    outside_heat(b, target, INFERNO_HEAT_PER_MISSILE * missiles, source, heat_dissipating_armor);
}

/// Outside heat on a 'Mech, applied in its Heat Phase (at most 15 a turn); none with heat-dissipating armor (p.202).
pub fn outside_heat(b: &mut Battle, target: UnitId, amount: i64, source: &str, heat_dissipating_armor: bool) {
    if amount <= 0 {
        return;
    }
    let name = b.units[target].side_name.clone().unwrap_or_default();
    if heat_dissipating_armor {
        b.log(format!("      {}: heat-dissipating armor - no heat to {} (p.202).", source, name));
        return;
    }
    let cur = b.units[target].outside_heat.unwrap_or(0);
    b.units[target].outside_heat = Some(cur + amount);
    b.log(format!("      {}: +{} heat to {} (outside heat, p.103).", source, amount, name));
}

/// The IMP effect now: +this to hit, -this Walking / Jumping MP.
pub fn imp_level(m: &crate::mech_state::Mech) -> i64 {
    if matches!(m.imp_until, Some(Some(_))) { m.imp_level.unwrap_or(0) } else { 0 }
}

/// IMP missiles strike a 'Mech: their damage is dealt as normal; this applies the effects.
pub fn imp_hit(b: &mut Battle, target: UnitId, missiles: i64, turn: i64, heat_dissipating_armor: bool) {
    if b.is_destroyed(target) {
        return;
    }
    let started = b.units[target].imp_started.flatten();
    let effect = !(matches!(b.units[target].imp_until, Some(Some(_))) && started != Some(turn));
    let (seen_turn, before0) = b.units[target].imp_missiles.unwrap_or((None, 0));
    let before = if seen_turn == Some(turn) { before0 } else { 0 };
    let total = before + missiles;
    b.units[target].imp_missiles = Some((Some(turn), total));
    let name = b.units[target].side_name.clone().unwrap_or_default();
    let fusion = fusion_engine(&b.units[target]);
    if effect {
        let level = IMP_MAX.min(crate::pyfmt::py_floordiv(total, IMP_PER_STEP));
        if level != 0 {
            b.units[target].imp_level = Some(level);
            b.units[target].imp_until = Some(Some(turn + 1));
            b.units[target].imp_started = Some(Some(turn));
            b.units[target].imp_mp = Some(if fusion { level } else { 0 });
            let mp = if fusion { format!("-{}", level) } else { "no (not fusion-powered)".to_string() };
            b.log(format!("      IMP: {} missiles this turn - {} as if inside hostile ECM, +{} to hit and {} Walking / Jumping MP through turn {} (IO).", total, name, level, mp, turn + 1));
        }
    } else {
        b.log(format!("      IMP: {} is already affected - damage only.", name));
    }
    if fusion {
        let heat = crate::pyfmt::py_floordiv(total, IMP_PER_STEP) - crate::pyfmt::py_floordiv(before, IMP_PER_STEP);
        outside_heat(b, target, heat, "IMP missiles", heat_dissipating_armor);
    }
}

fn imp_end_phase(b: &mut Battle, u: UnitId, turn: i64) {
    if let Some(Some(until)) = b.units[u].imp_until {
        if turn >= until {
            b.units[u].imp_until = Some(None);
            b.units[u].imp_level = Some(0);
            b.units[u].imp_started = Some(None);
            b.units[u].imp_mp = Some(0);
            let name = b.units[u].side_name.clone().unwrap_or_default();
            b.log(format!("  [End] {}: the IMP effects end.", name));
        }
    }
}

/// TSEMP interference / IMP: treated as inside a hostile ECM field.
pub fn as_if_jammed(m: &crate::mech_state::Mech) -> bool {
    tsemp_interference(m) != 0 || imp_level(m) != 0
}

/// To-hit added to this unit's attacks: Taser interference (all), TSEMP (weapon attacks only), IMP (all).
pub fn own_attack_modifier(m: &crate::mech_state::Mech, physical: bool) -> i64 {
    interference(m) + if physical { 0 } else { tsemp_interference(m) } + imp_level(m)
}


/// Expected damage of a nail gun hit: 3.5 times the chance the hit lands on a location with no armor left.
pub fn nail_worth(target: &crate::mech_state::Mech, side: &str) -> f64 {
    let table: &[(i64, &str)] = match side {
        "left" => &crate::hit_location::HIT_TABLE_LEFT_SIDE,
        "right" => &crate::hit_location::HIT_TABLE_RIGHT_SIDE,
        _ => &crate::hit_location::HIT_TABLE_FRONT_REAR,
    };
    let rear = side == "rear";
    let mut bare = 0.0;
    for (roll, p) in crate::expected_damage::p_2d6_exact() {
        let Some((_, loc)) = table.iter().find(|(k, _)| *k == roll) else { continue };
        if let Some(info) = target.locations.get(*loc) {
            let armor = if rear { info.rear_armor.unwrap_or(info.armor) } else { info.armor };
            if !info.destroyed && armor <= crate::pyfmt::Num::I(0) {
                bare += p;
            }
        }
    }
    NAIL_EXPECTED * bare
}

/// Heavy smoke in the hex behind the firer (module docstring).
pub fn hvac_smoke(b: &mut Battle, attacker: UnitId, target: UnitId, turn: i64) {
    use crate::hex_geometry as hg;
    let ahex = b.units[attacker].hex.clone().unwrap();
    let a_xy = hg::parse_hex_label(&ahex).unwrap();
    let t_xy = hg::parse_hex_label(b.units[target].hex.as_deref().unwrap()).unwrap();
    let away = crate::combat::direction_facing(t_xy, a_xy).unwrap();
    let (dx, dy) = hg::FACING_DELTAS[away as usize];
    let here_level = b.board.hexes[&ahex].level;
    let mut label = ahex.clone();
    let behind = hg::hex_label(a_xy.0 + dx, a_xy.1 + dy).ok();
    let info_level = behind.as_ref().and_then(|l| b.board.hexes.get(l)).map(|i| i.level);
    match (&behind, info_level) {
        (Some(bl), Some(lv)) if lv <= here_level => label = bl.clone(),
        (_, None) => return,
        _ => {}
    }
    let name = b.units[attacker].side_name.clone().unwrap_or_default();
    crate::smoke::add(b, &label, crate::smoke::HEAVY, turn + 1, &format!("{}'s HVAC fire", name));
}
