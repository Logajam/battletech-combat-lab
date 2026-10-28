"""INTEGRATION__advanced_equipment.py - equipment from Tactical Operations:
Advanced Units & Equipment (TO:AUE) that needs rules (NEW 2026-10-27,
Claude; Daniel: "wire in functionality of missing weapons, equipment, and
hex types already noted"). Shoulder and head turrets are INTEGRATION__arcs'
(p.159).

MODULAR ARMOR (p.93; Advanced Armor Table: 10 points a ton, 1 slot, at
most one per location; a torso's is front or rear - "(R)" on the crit line
- and protects only that side; its points are Standard armor, p.92):
  - Damage to a location with a Modular Armor slot comes off the modular
    armor first; the rest goes on as a new attack against the location's
    own armor (damage_resolution.apply_damage calls absorb). Internal
    explosions bypass armor, so modular armor too. Penetrating criticals /
    armor-piercing weapons go by the underlying armor - nothing to do here.
  - A critical hit on the slot destroys all its remaining points
    (slot_hit); an empty slot is a destroyed item.
  - While ANY modular armor point remains on the 'Mech: +1 to every
    Piloting roll, -1 Walking MP (Running recalculated), -1 Jumping MP, and
    stealth armor doesn't work (active()). Penalties don't stack with more
    slots.
  - It can't be ejected in play.
"""

import INTEGRATION__config as config
from equipment import Equipment

MODULAR_POINTS = 10          # one slot = one ton = 10 points (TO:AUE pp.92-93, Advanced Armor Table)


def is_modular_armor(slot):
    return isinstance(slot, Equipment) and "MODULARARMOR" in (slot.name or "").replace(" ", "").upper()


def attach(mech):
    """Once per battle (fresh clone): fill each Modular Armor slot."""
    mech.modular_armor = []
    seen = set()
    for loc, slots in mech.crits.items():
        for s in slots:
            if is_modular_armor(s) and id(s) not in seen:
                seen.add(id(s))
                s.modular_points = MODULAR_POINTS
                s.modular_location = loc
                s.modular_field = "rear_armor" if getattr(s, "rear_mounted", False) else "armor"
                mech.modular_armor.append(s)


def active(mech) -> bool:
    """Any modular armor point left (p.93: the penalties last until ALL
    modular armor is gone)."""
    return any(s.modular_points > 0 for s in getattr(mech, "modular_armor", ()))


def absorb(mech, location, armor_field, damage):
    """Modular armor on `location`'s `armor_field` takes `damage` first;
    returns what is left for the location's own armor."""
    for s in getattr(mech, "modular_armor", ()):
        if s.modular_location == location and s.modular_field == armor_field and s.modular_points > 0:
            taken = min(damage, s.modular_points)
            s.modular_points -= taken
            config.log(f"  Modular armor on {location}{' (rear)' if armor_field == 'rear_armor' else ''} takes "
                       f"{taken} ({s.modular_points} left; TO:AUE p.93).")
            if s.modular_points == 0 and not active(mech):
                config.log(f"  {mech.side_name}'s last modular armor is gone - its penalties end (TO:AUE p.93).")
            return damage - taken
    return damage


def slot_hit(mech, slot):
    """A critical hit on a Modular Armor slot destroys all its points (p.93)."""
    if getattr(slot, "modular_points", 0) > 0:
        config.log(f"      Modular armor slot hit - its {slot.modular_points} points are destroyed (TO:AUE p.93).")
        slot.modular_points = 0
