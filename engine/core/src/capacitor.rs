// Translated from INTEGRATION__capacitor.py (session 22): PPC capacitors (Core p.188).
use crate::battle::{Battle, UnitId};
use crate::equipment::{ItemId, Slot};
use crate::equipment_systems::norm;
use crate::mech_state::SlotInfo;

pub const CHARGE_HEAT: i64 = 5;
pub const CHARGE_DAMAGE: i64 = 5;

pub fn is_capacitor(b: &Battle, u: UnitId, id: ItemId) -> bool {
    norm(&b.units[u].items[id].name).contains("CAPACITOR")
}

pub fn set_charged(b: &mut Battle, u: UnitId, cap: ItemId, on: bool) {
    b.units[u].items[cap].charged = Some(on);
    let ppc = b.units[u].items[cap].linked_ppc.expect("linked ppc");
    let (bh, bd) = (b.units[u].items[ppc].base_heat.unwrap(), b.units[u].items[ppc].base_damage.unwrap());
    b.units[u].items[ppc].heat = Some(bh + if on { CHARGE_HEAT } else { 0 });
    b.units[u].items[ppc].damage_per_shot = Some(bd + if on { CHARGE_DAMAGE } else { 0 });
}

pub fn live(b: &Battle, u: UnitId, cap: ItemId) -> bool {
    let dead = crate::equipment_systems::destroyed_ids(&b.units[u]);
    let ppc = b.units[u].items[cap].linked_ppc.unwrap();
    !dead.contains(&cap) && !dead.contains(&ppc)
}

/// A critical hit to a capacitor or a linked PPC (p.188), called once the slot is marked destroyed.
pub fn crit_hit(b: &mut Battle, u: UnitId, location: &str, component: ItemId) {
    let cap = if is_capacitor(b, u, component) { Some(component) } else { b.units[u].items[component].capacitor };
    let cap = match cap {
        Some(c) if b.units[u].items[c].linked_ppc.is_some() && b.units[u].items[c].charged == Some(true) => c,
        _ => return,
    };
    let ppc = b.units[u].items[cap].linked_ppc.unwrap();
    if b.units[u].items[cap].firing == Some(true) {
        let n = b.units[u].items[ppc].name.clone();
        b.log(format!("      The {} was declared firing this phase - its capacitor doesn't count as charged (p.188).", n));
        return;
    }
    set_charged(b, u, cap, false);
    let locs: Vec<String> = b.units[u].crits.keys().cloned().collect();
    for loc in locs {
        let n = b.units[u].crits[&loc].len();
        for i in 0..n {
            let s = b.units[u].crits[&loc][i].clone();
            if s == Slot::Item(cap) || s == Slot::Item(ppc) {
                let id = if let Slot::Item(id) = s { id } else { unreachable!() };
                let name = b.units[u].items[id].name.clone();
                b.units[u].destroyed_slot_info.insert((loc.clone(), i), SlotInfo { name, instance_id: Some(id) });
                b.units[u].crits.get_mut(&loc).unwrap()[i] = Slot::name("DESTROYED");
            }
        }
    }
    let total = b.units[u].items[ppc].slots_occupied + b.units[u].items[cap].slots_occupied;
    b.units[u].items[cap].explosion_damage = 2 * total;
    let pn = b.units[u].items[ppc].name.clone();
    b.log(format!("      Charged PPC capacitor hit: the {} and its capacitor are destroyed (p.188).", pn));
    crate::damage_resolution::apply_explosion(b, u, cap, location);
}

fn pick_ppc(b: &Battle, u: UnitId, loc: &str, i: usize) -> Option<ItemId> {
    let m = &b.units[u];
    let taken: Vec<ItemId> = m.capacitors.iter().filter_map(|c| m.items[*c].linked_ppc).collect();
    let slots = &m.crits[loc];
    let ppcs: Vec<(usize, ItemId)> = slots
        .iter()
        .enumerate()
        .filter_map(|(j, s)| match s {
            Slot::Item(id) if m.items[*id].category.as_deref() == Some("weapon") && crate::equipment_systems::is_ppc(m, *id) && !taken.contains(id) => Some((j, *id)),
            _ => None,
        })
        .collect();
    if ppcs.is_empty() {
        return None;
    }
    let before: Vec<ItemId> = ppcs.iter().filter(|(j, _)| *j < i).map(|(_, s)| *s).collect();
    Some(before.last().copied().unwrap_or(ppcs[0].1))
}

/// Once per battle: link each capacitor to a PPC and set it charged or empty (a stub).
pub fn attach(b: &mut Battle, u: UnitId) {
    b.units[u].capacitors = Vec::new();
    b.units[u].capacitor_heat = 0;
    let mut seen: Vec<ItemId> = Vec::new();
    let locs: Vec<String> = b.units[u].crits.keys().cloned().collect();
    for loc in locs {
        let n = b.units[u].crits[&loc].len();
        for i in 0..n {
            let Slot::Item(s) = b.units[u].crits[&loc][i].clone() else { continue };
            if !is_capacitor(b, u, s) || seen.contains(&s) {
                continue;
            }
            seen.push(s);
            let Some(ppc) = pick_ppc(b, u, &loc, i) else {
                let line = format!("  WARNING: {}'s {} in {} has no PPC to link to - unused.", b.units[u].side_name.clone().unwrap_or_default(), b.units[u].items[s].name, loc);
                b.log(line);
                continue;
            };
            b.units[u].items[s].linked_ppc = Some(ppc);
            b.units[u].items[ppc].capacitor = Some(s);
            if b.units[u].items[ppc].base_heat.is_none() {
                b.units[u].items[ppc].base_heat = b.units[u].items[ppc].heat;
                b.units[u].items[ppc].base_damage = b.units[u].items[ppc].damage_per_shot;
            }
            b.units[u].items[s].firing = Some(false);
            b.units[u].items[s].charging = Some(false);
            b.units[u].capacitors.push(s);
            let name = b.units[u].side_name.clone().unwrap_or_default();
            let ppc_name = b.units[u].items[ppc].name.clone();
            let on = crate::stubs::stub_capacitor_start(b, &name, &ppc_name);
            set_charged(b, u, s, on);
        }
    }
}

/// After weapons are declared: a charged PPC that fires uses its charge; an idle one with an empty capacitor may charge.
pub fn declare(b: &mut Battle, u: UnitId, firing_weapons: &[ItemId], can_act: bool) {
    let caps = b.units[u].capacitors.clone();
    for cap in caps {
        let ppc = b.units[u].items[cap].linked_ppc.unwrap();
        let charged = b.units[u].items[cap].charged == Some(true);
        b.units[u].items[cap].firing = Some(charged && firing_weapons.contains(&ppc));
        b.units[u].items[cap].charging = Some(false);
        if can_act && !charged && live(b, u, cap) && !firing_weapons.contains(&ppc) {
            let name = b.units[u].side_name.clone().unwrap_or_default();
            let ppc_name = b.units[u].items[ppc].name.clone();
            if crate::stubs::stub_capacitor_charge(b, &name, &ppc_name) {
                b.units[u].items[cap].charging = Some(true);
                b.log(format!("  {} charges the {}'s capacitor instead of firing it (+{} heat, p.188).", name, ppc_name, CHARGE_HEAT));
            }
        }
    }
}

/// End of the Ranged Attack Phase: this turn's capacitor heat and the charges spent or stored.
pub fn end_phase(b: &mut Battle, u: UnitId) {
    let mut heat = 0;
    let caps = b.units[u].capacitors.clone();
    for cap in caps {
        let it = &b.units[u].items[cap];
        let (firing, charging, charged) = (it.firing == Some(true), it.charging == Some(true), it.charged == Some(true));
        if firing {
            set_charged(b, u, cap, false);
        } else if charging {
            set_charged(b, u, cap, true);
            heat += CHARGE_HEAT;
        } else if charged && live(b, u, cap) {
            heat += CHARGE_HEAT;
        } else if charged {
            set_charged(b, u, cap, false);
        }
        b.units[u].items[cap].firing = Some(false);
        b.units[u].items[cap].charging = Some(false);
    }
    b.units[u].capacitor_heat = heat;
}
