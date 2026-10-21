"""
Equipment identity + the external equipment.json database.

See ARCHITECTURE_PROPOSAL.md, section 7, for an illustrative (NOT literal)
example of equipment.json's shape. This module owns everything about "what
is this piece of gear" - it does NOT own combat resolution (that's
damage_resolution.py) or mech state (that's mech_state.py).

KNOWN BUG (documented in ARCHITECTURE_PROPOSAL.md section 3, not fixed in
this pass - this was a pure file-split, no logic changes): CASE/CASE II
identity is currently resolved by damage_resolution.get_case_tier() via a
literal string check against crit-slot contents, which only matches the
hardcoded stress-fixture mech (see mech_state.BattleMech.__init__) and NOT
real parsed mechs, where CASE/CASE II become Equipment instances instead of
bare strings. Confirmed bug via a real .mtf file with "ISCASEII". Planned
fix direction: add a `case_tier` field here on Equipment/equipment.json,
same pattern as crit_eligible, and have get_case_tier() read it off the
instance. Not yet built.
"""

import os
import json
import re


class Equipment:
    """A physical piece of gear that may occupy multiple crit slots.

    Identity is per-instance, never per-name: three lasers with the same
    display name are three separate objects, each tracking its own state.
    Slot count and explosiveness are attributes of the instance, so a Clan
    Gauss Rifle (6 slots) and an IS Gauss Rifle (7 slots) are just two
    differently-configured instances of the same concept.

    crit_eligible: can this slot be the RESULT of a random critical-hit roll
    (see is_crit_target below). damage_type: metadata only as of this split -
    nothing in damage_resolution.py reads it yet (see FOR LATER in the
    original v10 docstring, preserved in main.py). special_rules/
    special_rules_ref: flags that this item has real rules beyond what
    properties alone capture (e.g. Reactive Armor's secondary-roll mechanic,
    not yet modeled).
    """
    def __init__(self, name, slots_occupied=1, is_explosive=False, explosion_damage=None,
                 crit_eligible=True, damage_type=None, special_rules=False, special_rules_ref=None,
                 category=None, weapon_range=None, damage_per_shot=None, heat=None,
                 battle_value=None, tonnage=None, rack_size=None):
        self.name = name
        self.slots_occupied = slots_occupied
        self.is_explosive = is_explosive
        self.crit_eligible = crit_eligible
        self.damage_type = damage_type
        self.special_rules = special_rules
        self.special_rules_ref = special_rules_ref
        # Weapon-stat fields (2026-08-05, INTEGRATION Part A) - carried straight off
        # the equipment.json entry, once, at parse time (mtf_parser.build_crit_list),
        # not re-looked-up on the hot path. None for anything that isn't a weapon,
        # and None for weapon rows equipment.json hasn't confirmed yet (e.g. HAG
        # range, several Ultra AC damage_type rows) - callers must handle None,
        # not assume it's populated just because category == "weapon".
        # weapon_range mirrors equipment.json's "range" key ({"short","medium","long"}
        # dict or None) - named weapon_range here since `range` shadows the builtin.
        self.category = category
        self.weapon_range = weapon_range
        self.damage_per_shot = damage_per_shot
        self.heat = heat
        self.battle_value = battle_value
        self.tonnage = tonnage
        self.rack_size = rack_size
        # Default explosive yield is 2 damage per slot occupied (Core p.96: "unless specified
        # otherwise, a component explosion does 2 points of damage, multiplied by the number of slots").
        # Ammo bins override this with their own flat value (20, per the 2026 rule change).
        if explosion_damage is not None:
            self.explosion_damage = explosion_damage
        elif is_explosive:
            self.explosion_damage = 2 * slots_occupied
        else:
            self.explosion_damage = 0
        self.exploded = False
        # 2026-10-19: mounted facing the rear - "(R)" on its .mtf crit line
        # (Core p.60: fires only into the rear arc). Set by mtf_parser.
        self.rear_mounted = False
        self.turret_mounted = False   # 2026-10-19: "(T)" on its .mtf crit line (Core p.61)

    def __repr__(self):
        return f"<{self.name}>"


def equipment_slots(name, slots_occupied=1, is_explosive=False, explosion_damage=None,
                     crit_eligible=True, damage_type=None, special_rules=False, special_rules_ref=None,
                     category=None, weapon_range=None, damage_per_shot=None, heat=None,
                     battle_value=None, tonnage=None, rack_size=None):
    """Build a list of N slot entries that all share ONE Equipment instance,
    so destroying one slot doesn't affect the others' identity, but an
    explosion check on any of them refers to the same shared state."""
    e = Equipment(name, slots_occupied, is_explosive, explosion_damage,
                  crit_eligible, damage_type, special_rules, special_rules_ref,
                  category, weapon_range, damage_per_shot, heat, battle_value, tonnage, rack_size)
    return [e] * slots_occupied


# ---- External equipment database - equipment.json must sit next to main.py ----
EQUIPMENT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "equipment.json")


def load_equipment_db(path=EQUIPMENT_DB_PATH):
    try:
        with open(path, "r", encoding="utf-8") as f:
            db = json.load(f)
        return db.get("entries", {}), db.get("alias_map", {})
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"WARNING: could not load equipment.json ({e}). Falling back to an "
              f"empty database - ALL equipment will be treated as unrecognized "
              f"generic padding. Expected at: {path}")
        return {}, {}


EQUIPMENT_ENTRIES, EQUIPMENT_ALIAS_MAP = load_equipment_db()


def lookup_equipment(raw_name):
    """Normalize a raw .mtf equipment name the same way build_equipment_db.py
    normalized MegaMek's names (lowercase, whitespace stripped), then resolve it
    through the alias map to a canonical entry. Returns None if nothing matches -
    caller falls back to generic-padding treatment."""
    key = re.sub(r"\s+", "", raw_name.strip().lower())
    canon = EQUIPMENT_ALIAS_MAP.get(key)
    if canon is None:
        return None
    return EQUIPMENT_ENTRIES.get(canon)


# Anatomy terms that are real mech structure but NOT in MegaMek's equipment
# database at all (they're not "equipment"), so they'd otherwise show up as a
# false "unrecognized" warning every single time.
ANATOMY_COMPONENTS = ("CASE", "CASE II", "Sensors", "Life Support", "Heat Sink",
                      "Shoulder", "Upper Arm Actuator", "Lower Arm Actuator", "Hand Actuator",
                      "Hip", "Upper Leg Actuator", "Lower Leg Actuator", "Foot Actuator")

ENGINE_NAMES = ("Fusion Engine", "XL Engine", "Light Engine", "Compact Engine", "ICE Engine", "Engine")

# Plain-string sentinels that can't be a crit-roll TARGET even though they're not
# Equipment instances - only used by the hardcoded stress-test fixture mech, which
# still writes bare "CASE"/"CASE II" strings into its crit lists (see
# mech_state.BattleMech.__init__). Real parsed mechs get this from equipment.json's
# crit_eligible field instead - see is_crit_target() below, which checks both paths.
# HELP(crit_target.dead_code_plain_string)
PLAIN_STRING_CRIT_INELIGIBLE = ("CASE", "CASE II")


# Structure / armor filler slots (Core p.94, 2026-10-21): "slots for CASE, TSM,
# endo-steel and other structure, ferro-fibrous and other armor" can't take
# critical damage - a hit there is rolled again. MegaMek writes them as plain
# names ("Endo Steel", "Ferro-Fibrous", "Stealth", "IS Ballistic-Reinforced"...)
# that don't resolve against equipment.json, so before this they stayed plain
# strings that is_crit_target counted as targets - an endo / ferro 'Mech's 7-28
# filler slots soaked critical hits that belong to its real components.
STRUCTURE_ARMOR_SLOT_WORDS = ("ENDOSTEEL", "ENDOCOMPOSITE", "FERROFIBROUS", "FERROLAMELLOR", "STEALTH",
                              "REACTIVE", "REFLECTIVE", "BALLISTICREINFORCED")


def is_structure_or_armor_slot(name):
    """True for a structure / armor filler slot name (STRUCTURE_ARMOR_SLOT_WORDS)."""
    norm = "".join(c for c in str(name).upper() if c.isalpha())
    return any(word in norm for word in STRUCTURE_ARMOR_SLOT_WORDS)


def is_crit_target(slot):
    """Can this crit-slot entry be the RESULT of a random critical-hit roll?
    Respects Equipment.crit_eligible (data-driven, from equipment.json) - e.g.
    Reactive Armor is crit-ineligible for the same reason CASE is: per RAW,
    landing on it is a "roll again" result, and we skip that roundtrip for speed
    rather than actually re-rolling."""
    if slot in ("DESTROYED", "-Empty-") or slot in PLAIN_STRING_CRIT_INELIGIBLE:
        return False
    if isinstance(slot, Equipment):
        return slot.crit_eligible
    return not is_structure_or_armor_slot(slot)
