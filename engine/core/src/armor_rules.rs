// Translated from mechsim/armor_rules.py (session 22).
//! Armor-type x damage-type dispatch: how much of an attack's damage armor absorbs, and what continues to structure.
//! Damage and pools are `Num` (int or float): the Python's `/` makes floats, `//` keeps ints.

use crate::mech_state::{ArmorType, DamageType, StructureType};
use crate::pyfmt::{py_max, py_min, Num};

fn ceil_div(damage: Num, n: f64) -> i64 {
    (damage.f() / n).ceil() as i64
}

/// Armor-type effects that change the ATTACK's own damage value, applied BEFORE armor absorbs anything.
pub fn reduce_attack_damage_for_armor(armor_type: ArmorType, damage_type: DamageType, damage: Num) -> Num {
    if armor_type == ArmorType::Reactive && matches!(damage_type, DamageType::Missile | DamageType::AreaEffect) {
        return py_max(damage.floordiv(Num::I(2)), Num::I(1));
    }
    if armor_type == ArmorType::BallisticReinforced && matches!(damage_type, DamageType::Missile | DamageType::Ballistic) {
        return py_max(damage.floordiv(Num::I(2)), Num::I(1));
    }
    if armor_type == ArmorType::FerroLamellor {
        return py_max(damage - Num::I(ceil_div(damage, 5.0)), Num::I(0));
    }
    if armor_type == ArmorType::ImpactResistant && damage_type == DamageType::Physical {
        return py_max(damage - Num::I(ceil_div(damage, 3.0)), Num::I(1));
    }
    damage
}

/// (armor points destroyed, damage that continues to structure).
pub fn consume_armor(armor_type: ArmorType, damage_type: DamageType, damage: Num, armor_pool: Num) -> (Num, Num) {
    if armor_type == ArmorType::Hardened {
        let destroyed = py_min(damage.div(Num::I(2)), armor_pool);
        let overflow = py_max(damage - armor_pool * Num::I(2), Num::I(0));
        return (destroyed, overflow);
    }
    if armor_type == ArmorType::Reflective {
        if damage_type == DamageType::Energy {
            let mut destroyed = py_min(damage.floordiv(Num::I(2)), armor_pool);
            if damage > Num::I(0) && destroyed == Num::I(0) {
                destroyed = py_min(Num::I(1), armor_pool);
            }
            let overflow = if destroyed >= armor_pool { py_max(damage - armor_pool * Num::I(2), Num::I(0)) } else { Num::I(0) };
            return (destroyed, overflow);
        }
        if matches!(damage_type, DamageType::Physical | DamageType::AreaEffect) {
            let capacity_in_damage_points = Num::I(ceil_div(armor_pool, 2.0));
            let damage_absorbed_points = py_min(damage, capacity_in_damage_points);
            let destroyed = py_min(damage_absorbed_points * Num::I(2), armor_pool);
            let overflow = py_max(damage - damage_absorbed_points, Num::I(0));
            return (destroyed, overflow);
        }
    }
    let consumed = py_min(damage, armor_pool);
    (consumed, py_max(damage - armor_pool, Num::I(0)))
}

/// (structure points destroyed, damage overflowing beyond this pool).
pub fn consume_structure(structure_type: StructureType, damage: Num, structure_pool: Num) -> (Num, Num) {
    if structure_type == StructureType::Reinforced {
        let destroyed = py_min(damage.div(Num::I(2)), structure_pool);
        let overflow = py_max(damage - structure_pool * Num::I(2), Num::I(0));
        return (destroyed, overflow);
    }
    if structure_type == StructureType::Composite {
        let capacity_in_damage_points = Num::I(ceil_div(structure_pool, 2.0));
        let damage_absorbed_points = py_min(damage, capacity_in_damage_points);
        let destroyed = py_min(damage_absorbed_points * Num::I(2), structure_pool);
        let overflow = py_max(damage - damage_absorbed_points, Num::I(0));
        return (destroyed, overflow);
    }
    let consumed = py_min(damage, structure_pool);
    (consumed, py_max(damage - structure_pool, Num::I(0)))
}

/// -2 if armor is Hardened / Anti-Penetrative Ablation AND present; -1 blanket if structure is Reinforced.
pub fn crit_roll_modifier(structure_type: StructureType, armor_type: Option<ArmorType>, armor_present: bool) -> i64 {
    let mut modifier = 0;
    if armor_present && matches!(armor_type, Some(ArmorType::Hardened) | Some(ArmorType::AntiPenetrativeAblation)) {
        modifier -= 2;
    }
    if structure_type == StructureType::Reinforced {
        modifier -= 1;
    }
    modifier
}

/// Pre-armor-CONSUMPTION effective damage: the damage-reducing armor effects, only while armor is left.
pub fn effective_damage(armor_type: ArmorType, damage_type: DamageType, damage: Num, armor_pool: Num) -> Num {
    if armor_pool > Num::I(0) {
        reduce_attack_damage_for_armor(armor_type, damage_type, damage)
    } else {
        damage
    }
}
