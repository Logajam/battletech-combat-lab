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
