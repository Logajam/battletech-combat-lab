"""
INTEGRATION__battle_value.py  (NEW 2026-10-28, Claude - Battle Value)

Battle Value (BV 2.0) of a 'Mech: one number for how strong it is, from its
armor and structure, speed, weapons, ammunition and the pilot's skill. Daniel,
2026-10-28: "6 requires us to calculate BV, which is also doable and needed for
human integration ... As usual use Megamek as source material where needed."
Used here by Princess's group behaviors (the friendly "hot spot" it keeps
close to is weighted by BV - INTEGRATION__princess_memory) and, later, to pick
fair forces for a person.

SOURCE: MegaMek, `megamek/common/battleValue/` - BVCalculator (the steps),
MekBVCalculator (the 'Mech parts), HeatTrackingBVCalculator (weapons sorted by
heat), Engine / Mek / MiscType (the multipliers). The TechManual (where the
rules are printed) is not in the rules library, so MegaMek is the written
source (Daniel's standing instruction). Each item's own BV is read out of
MegaMek's classes by tools/build_equipment_bv.py into mechsim/equipment_bv.json.

THE STEPS (BVCalculator.processBaseBV)
  Defensive: armor points x 2.5 x the armor type's factor (+ the center torso
    twice for a torso-mounted cockpit) + internal structure x 1.5 x structure
    type x engine factor + weight x gyro factor + defensive equipment (AMS,
    ECM, active probes, shields...; AMS ammunition up to the AMS's own BV)
    - explosive gear (15 per slot where an explosion would kill or gut the
    'Mech - ammunition, mostly; 1 per slot for Gauss and a few others), at
    least 1; all x (1 + the best Target Movement Modifier / 10).
  Offensive: each weapon's BV (x1.25 with a Targeting Computer for direct fire,
    Artemis / Apollo links, a PPC capacitor, an Actuator Enhancement arm), the
    weaker of the front and rear sets halved (arm and turret weapons are never
    halved); weapons taken in order - heatless first, then by BV, highest first
    - and every weapon after the heat efficiency (6 + sinks - the movement
    heat, jump or run) is reached counts half; ammunition per kind, up to its
    weapons' BV ("excessive ammo"); physical weapons and other offensive gear;
    + the 'Mech's weight (x1.5 TSM); all x the speed factor
    (run MP + half the jump MP: (1 + (MP-5)/10) ^ 1.2); x0.9 for an industrial
    cockpit.
  Base BV = defensive + offensive (x0.95 small / torso-mounted cockpit, x1.3
    interface cockpit); rounded. Pilot skill factor from the gunnery / piloting
    table; rounded again.

MOVEMENT FOR BV (MPCalculationSetting.BV_CALCULATION): no heat, no gravity, no
MASC (an unarmed MASC counts for nothing), TSM counts as +1 walking MP, the
walk MP x1.5 rounded up is the run MP.

NOT MODELED (each is rare, and listed so the number is read with care):
armored components (+5 each), C3 / TAG network bonuses (a unit's BV alone),
Blue Shield, coolant-pod / RISC kit extras beyond the heat efficiency, LAMs,
the variable MiscType BVs other than physical weapons and the AES.
An item missing from equipment_bv.json counts 0 BV (the same as MegaMek's own
default) - missing_items() lists them for a unit.

battle_value(mech, current=False, skill=True) -> int
    current=False: the 'Mech as built (full armor and structure, nothing
    destroyed) - what MegaMek's "initial BV" is; current=True: as it stands now.
battle_value_report(mech, ...) -> (BV, [lines]) shows the sums.
"""

import functools
import json
import math
import os

from damage_resolution import TRANSFER_MAP  # noqa: E402 - MECHSIM
from equipment import Equipment, lookup_equipment  # noqa: E402 - MECHSIM
from mech_state import compute_heat_dissipation, ArmorType, StructureType  # noqa: E402 - MECHSIM

_BV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mechsim", "equipment_bv.json")

# BVCalculator.bvMultipliers[gunnery][piloting] (0-8 each).
SKILL_TABLE = (
    (2.42, 2.31, 2.21, 2.10, 1.93, 1.75, 1.68, 1.59, 1.50),
    (2.21, 2.11, 2.02, 1.92, 1.76, 1.60, 1.54, 1.46, 1.38),
    (1.93, 1.85, 1.76, 1.68, 1.54, 1.40, 1.35, 1.28, 1.21),
    (1.66, 1.58, 1.51, 1.44, 1.32, 1.20, 1.16, 1.10, 1.04),
    (1.38, 1.32, 1.26, 1.20, 1.10, 1.00, 0.95, 0.90, 0.85),
    (1.31, 1.19, 1.13, 1.08, 0.99, 0.90, 0.86, 0.81, 0.77),
    (1.24, 1.12, 1.07, 1.02, 0.94, 0.85, 0.81, 0.77, 0.72),
    (1.17, 1.06, 1.01, 0.96, 0.88, 0.80, 0.76, 0.72, 0.68),
    (1.10, 0.99, 0.95, 0.90, 0.83, 0.75, 0.71, 0.68, 0.64),
)
ARMOR_FACTOR = 2.5
ARMOR_TYPE_MULTIPLIER = {                       # BVCalculator.armorMultiplier
    ArmorType.HARDENED: 2.0, ArmorType.REACTIVE: 1.5, ArmorType.REFLECTIVE: 1.5,
    ArmorType.BALLISTIC_REINFORCED: 1.5, ArmorType.FERRO_LAMELLOR: 1.2,
    ArmorType.ANTI_PENETRATIVE_ABLATION: 1.2, ArmorType.HEAT_DISSIPATING: 1.1,
}
ARMS = ("Left Arm", "Right Arm")
SIDE_TORSOS = ("Left Torso", "Right Torso")
# Explosive gear that costs 1 BV per slot instead of 15 (MekBVCalculator.processExplosiveEquipment).
LIGHT_EXPLOSIVES = {"F_GAUSS", "F_HVAC", "F_HYPER", "F_TSEMP", "F_TASER", "F_B_POD", "F_M_POD", "F_PPC"}
# Weapons whose ammunition rack is not "explosive equipment" in the BV sense (HeatTracking.countsAsExplosive):
# an autocannon itself doesn't explode - its ammunition does.
NON_EXPLOSIVE_WEAPON_AMMO = {"AC_ROTARY", "AC", "AC_IMP", "AC_PRIMITIVE", "PAC", "LAC"}


@functools.lru_cache(maxsize=1)
def _items():
    with open(_BV_PATH, encoding="utf-8") as f:
        return json.load(f)["items"]


def _key(entry):
    """equipment_bv.json is keyed like equipment.json: the canonical name, lower case."""
    return entry["canonical_name"].replace(" ", "").lower()


def _round(x):
    """Java's Math.round: halves round up."""
    return int(math.floor(x + 0.5))


def tmm(mp, jumped=False):
    """Compute.getTargetMovementModifier (no max-tech movement mods)."""
    if mp == 0 and not jumped:
        return 0
    base = 0
    for low, value in ((25, 6), (18, 5), (10, 4), (7, 3), (5, 2), (3, 1)):
        if mp >= low:
            base = value
            break
    return base + (1 if jumped else 0)


def skill_factor(gunnery, piloting):
    return SKILL_TABLE[max(0, min(8, gunnery))][max(0, min(8, piloting))]


class _Item:
    """One piece of equipment on the 'Mech: its crit-slot object plus what MegaMek knows of it."""

    def __init__(self, equip, location, slots_by_location, record, canonical=""):
        self.equip = equip
        self.canonical = canonical                # equipment.json's name for it, lower case ("" if unknown)
        self.location = location                  # the first location it occupies (Mounted.getLocation)
        self.slots_by_location = slots_by_location
        self.record = record or {}
        self.flags = set(self.record.get("flags", ()))
        self.kind = self.record.get("kind")
        self.bv = self.record.get("bv") or 0.0
        self.link = None                          # an Artemis / capacitor / Apollo working with this weapon

    @property
    def slots(self):
        return sum(self.slots_by_location.values())

    @property
    def rear(self):
        return bool(getattr(self.equip, "rear_mounted", False))

    @property
    def turret(self):
        return bool(getattr(self.equip, "turret_mounted", False))

    @property
    def name(self):
        return self.record.get("name") or self.equip.name


def _equipment(mech, current):
    """Every Equipment instance in the crit slots, once, in slot order."""
    destroyed = {info["instance_id"] for info in getattr(mech, "destroyed_slot_info", {}).values()
                 if info.get("instance_id") is not None} if current else set()
    seen, items = {}, []
    for location, slots in mech.crits.items():
        for slot in slots:
            if not isinstance(slot, Equipment):
                continue
            if id(slot) in destroyed:
                continue
            if id(slot) in seen:
                item = seen[id(slot)]
                item.slots_by_location[location] = item.slots_by_location.get(location, 0) + 1
                continue
            entry = lookup_equipment(slot.name or "")
            record = _items().get(_key(entry)) if entry else None
            item = _Item(slot, location, {location: 1}, record, entry["canonical_name"].lower() if entry else "")
            seen[id(slot)] = item
            items.append(item)
    return items


def _engine(mech):
    """(side-torso engine slots, fusion engine?) from the header text (Engine.getSideTorsoCriticalSlots)."""
    desc = (mech.engine_desc or "").upper()
    tech = (getattr(mech, "tech_base", "") or "").upper()
    clan_chassis = tech.startswith("CLAN") or "MIXED (CLAN" in tech
    if "(CLAN)" in desc:
        clan = True
    elif "(IS)" in desc or "(INNER SPHERE)" in desc:
        clan = False
    else:
        clan = clan_chassis
    superheavy = mech.mass > 100
    if "XXL" in desc:
        sides = 2 if superheavy else (4 if clan else 6)
    elif "XL" in desc:
        sides = (1 if clan else 2) if superheavy else (2 if clan else 3)
    elif "LIGHT" in desc:
        sides = 1 if superheavy else 2
    else:
        sides = 0
    fusion = not any(word in desc for word in ("ICE", "I.C.E", "FUEL", "FISSION"))
    return sides, fusion, clan


def _engine_multiplier(sides):
    if sides >= 6:
        return 0.25
    if sides >= 3:
        return 0.5
    if sides == 2:
        return 0.75
    if sides == 1:
        return 0.825
    return 1.0


class _Calc:
    def __init__(self, mech, current, skill):
        self.mech, self.current, self.skill = mech, current, skill
        self.lines = []
        self.items = _equipment(mech, current)
        self.engine_sides, self.fusion, self.clan_engine = _engine(mech)
        self.biped_like = mech.mech_type in ("biped", "tripod", "lam", "quadvee_biped")
        self.quad = mech.mech_type in ("quad", "quadvee")
        tech = (getattr(mech, "tech_base", "") or "").upper()
        self.clan_mech = tech.startswith("CLAN") or "MIXED (CLAN" in tech
        structure = (getattr(mech, "structure_desc", "") or "").upper()
        self.clan_structure = self.clan_mech and not structure.startswith("IS ")
        self._link_equipment()
        self.defensive = 0.0
        self.offensive = 0.0
        self._setup_movement()

    # ------------------------------------------------------------------ helpers
    def note(self, text, value=None):
        self.lines.append(text if value is None else f"{text:<44}{value}")

    def _flag(self, flag, location=None):
        return any(flag in i.flags and (location is None or location in i.slots_by_location) for i in self.items)

    def _has(self, flag):
        return any(flag in i.flags for i in self.items)

    def _link_equipment(self):
        """Artemis, Apollo and PPC capacitors work with a weapon in their own location
        (the first one of the right family still without a link)."""
        for linker in self.items:
            if linker.kind != "misc":
                continue
            wants = None
            if {"F_ARTEMIS", "F_ARTEMIS_PROTO", "F_ARTEMIS_V"} & linker.flags:
                wants = lambda w: "F_ARTEMIS_COMPATIBLE" in w.flags           # noqa: E731
            elif "F_APOLLO" in linker.flags:
                wants = lambda w: w.record.get("ammo_type") == "MRM"          # noqa: E731
            elif "F_PPC_CAPACITOR" in linker.flags:
                wants = lambda w: "F_PPC" in w.flags                           # noqa: E731
            if wants is None:
                continue
            for weapon in self.items:
                if (weapon.kind == "weapon" and weapon.link is None and linker.location in weapon.slots_by_location
                        and wants(weapon)):
                    weapon.link = linker
                    break

    def _setup_movement(self):
        mech = self.mech
        walk = mech.base_walk_mp
        tsm = any("F_TSM" in i.flags for i in self.items)
        legs_ok = True                                         # BV is for the 'Mech as built
        if tsm and legs_ok:
            walk += 1                                          # BipedMek.getWalkMP: forceTSM + ignoreHeat = +1
        run = int(math.ceil(walk * 1.5))
        if any(t == ArmorType.HARDENED for t in mech.armor_type.values()):
            run = max(0, run - 1)                              # Mek.hardenedArmorMPReduction
        jump = mech.base_jump_mp
        if jump and getattr(mech, "partial_wing_active", False):
            jump += 1 if mech.mass >= 60 else 2
        jump = max(jump, getattr(mech, "base_mechanical_jump_booster_mp", 0) or 0)
        self.walk, self.run, self.jump = walk, run, jump
        self.umu = sum(1 for i in self.items if "F_UMU" in i.flags)
        self.improved_jets = any("improvedjumpjet" in i.canonical for i in self.items)

    # ------------------------------------------------------------------ DEFENSE
    def armor(self):
        mech = self.mech
        total = 0.0
        for loc, entry in mech.locations.items():
            front = max(0, entry["armor"] if self.current else mech.max_armor.get(loc, entry["armor"]))
            rear = 0
            if "rear_armor" in entry:
                rear = max(0, entry["rear_armor"] if self.current
                           else mech.max_rear_armor.get(loc, entry["rear_armor"]))
            points = front + rear
            if loc == "Center Torso" and "TORSO-MOUNTED" in (mech.cockpit_type or "").upper():
                points += front + rear                        # MekBVCalculator.addTorsoMountedCockpit
            total += points * ARMOR_TYPE_MULTIPLIER.get(mech.armor_type.get(loc), 1.0)
        value = total * ARMOR_FACTOR
        self.defensive += value
        self.note(f"Armor: {total:g} x {ARMOR_FACTOR}", f"= {self.defensive:.2f}")

    def structure(self):
        mech = self.mech
        internal = sum(max(0, e["structure"] if self.current else mech.max_structure.get(loc, e["structure"]))
                       for loc, e in mech.locations.items())
        structure_text = (getattr(mech, "structure_desc", "") or "").upper()
        multiplier = 1.0
        if "INDUSTRIAL" in structure_text or "COMPOSITE" in structure_text:
            multiplier = 0.5                                   # (Endo-Composite is the lighter structure: 0.5 too)
        elif "REINFORCED" in structure_text:
            multiplier = 2.0
        engine = _engine_multiplier(self.engine_sides)
        self.defensive += internal * 1.5 * multiplier * engine
        self.note(f"Internal structure: {internal} x 1.5 x {multiplier:g} x {engine:g}", f"= {self.defensive:.2f}")
        gyro = (mech.gyro_type or "").upper()
        if "HEAVY" in gyro:
            gyro_mult = 1.0
        elif gyro == "NONE" and "INTERFACE" not in (mech.cockpit_type or "").upper():
            gyro_mult = 0.0                                    # Mek.getGyroMultiplier: no gyro, no gyro BV
        else:
            gyro_mult = 0.5
        self.defensive += mech.mass * gyro_mult
        self.note(f"Gyro: {mech.mass} x {gyro_mult:g}", f"= {self.defensive:.2f}")

    def defensive_equipment(self):
        ams_bv = ams_ammo_bv = 0.0
        for item in self.items:
            if item.kind == "ammo" and item.record.get("ammo_type") in ("AMS", "APDS"):
                ams_ammo_bv += item.bv
        defensive_flags = {"F_ECM", "F_BAP", "F_VIRAL_JAMMER_DECOY", "F_VIRAL_JAMMER_HOMING", "F_AP_POD", "F_MASS",
                           "F_HEAVY_BRIDGE_LAYER", "F_MEDIUM_BRIDGE_LAYER", "F_LIGHT_BRIDGE_LAYER", "F_BULLDOZER",
                           "F_CHAFF_POD", "F_HARJEL_II", "F_HARJEL_III", "F_SPIKES", "F_MINESWEEPER", "F_SHIELD"}
        for item in self.items:
            counts = False
            if item.kind == "weapon":
                counts = bool({"F_AMS", "F_M_POD", "F_B_POD"} & item.flags)
            elif item.kind == "misc":
                counts = bool(defensive_flags & item.flags)
            if not counts:
                continue
            self.defensive += item.bv
            self.note(f"+ {item.name} ({item.location})", f"= {self.defensive:.2f}")
            if item.kind == "weapon" and "F_AMS" in item.flags:
                ams_bv += item.bv
        if ams_ammo_bv > 0:
            self.defensive += min(ams_bv, ams_ammo_bv)
            self.note("+ AMS ammunition (up to the AMS)", f"= {self.defensive:.2f}")

    def _location_case(self, loc):
        return self._flag("F_CASE", loc) or self._flag("F_CASEP", loc) or (self.clan_mech and self.clan_structure)

    def _explosion_penalty_applies(self, loc):
        if self._flag("F_CASEII", loc):
            return False
        if loc in ARMS and not self.quad:
            side = TRANSFER_MAP.get(loc)
            return (not self._location_case(loc)) and self._explosion_penalty_applies(side)
        if loc in SIDE_TORSOS:
            return (not self._location_case(loc)) or self.engine_sides >= 3
        return True

    def explosive_equipment(self):
        for item in self.items:
            equip = item.equip
            if not getattr(equip, "is_explosive", False):
                continue
            if item.kind == "weapon":
                ammo_type = item.record.get("ammo_type")
                if ammo_type in NON_EXPLOSIVE_WEAPON_AMMO:
                    continue
                if "F_PPC" in item.flags and item.link is None:
                    continue
            if not self._explosion_penalty_applies(item.location):
                continue
            subtract = 15
            if item.kind == "weapon" and (LIGHT_EXPLOSIVES & item.flags
                                          or ("F_LASER" in item.flags and "S_IMPROVED" in item.flags)):
                subtract = 1
            if item.kind == "misc" and ({"F_PPC_CAPACITOR", "F_RISC_LASER_PULSE_MODULE", "F_EMERGENCY_COOLANT_SYSTEM",
                                         "F_JUMP_JET"} & item.flags):
                subtract = 1
            if item.kind == "ammo" and item.record.get("ammo_type") == "COOLANT_POD":
                subtract = 1
            slots = 1 if "F_HVAC" in item.flags else item.slots      # an HVAC is -1 whatever its size
            self.defensive -= subtract * slots
            self.note(f"- explosive {item.name} ({item.location})", f"= {self.defensive:.2f}")
        if self.defensive < 1:
            self.defensive = 1.0

    def defensive_factor(self):
        best = max(tmm(self.run), tmm(self.jump, True) if self.jump else 0, tmm(self.umu) if self.umu else 0)
        desc = (self.mech.armor_desc or "").upper()
        if "STEALTH" in desc or any("STEALTH" in (getattr(i.equip, "name", "") or "").upper() for i in self.items):
            best += 2
        if any("nullsignature" in i.canonical for i in self.items):
            best += 2
        if any("chameleon" in i.canonical for i in self.items):
            best += 2
        if any("voidsignature" in i.canonical for i in self.items):
            if best < 3:
                best = 3
            elif best == 3:
                best += 1
        factor = 1 + best / 10.0
        self.defensive *= factor
        self.note(f"x {factor:g} (TMM {best}: run {self.run}, jump {self.jump})", f"= {self.defensive:.2f}")

    # ------------------------------------------------------------------ OFFENSE
    def _offensive_weapon(self, item):
        if item.kind != "weapon":
            return False
        if {"F_AMS", "F_B_POD", "F_M_POD"} & item.flags:
            return False
        return item.bv > 0 or "F_MGA" in item.flags

    def _is_arm(self, item):
        return item.location in ARMS and not self.quad

    def _arm_aes(self, location):
        return any("F_ACTUATOR_ENHANCEMENT_SYSTEM" in i.flags and location in i.slots_by_location for i in self.items)

    def _weapon_bv(self, item, rear_set):
        bv = item.bv
        if "F_MGA" in item.flags:
            linked = [i for i in self.items if i.kind == "weapon" and i.location == item.location
                      and "F_MGA" not in i.flags and i.record.get("ammo_type") == "MG"]
            bv = sum(i.bv for i in linked) * 0.67
        if self._arm_aes(item.location) and item.location in ARMS:
            bv *= 1.25
        if rear_set and item in rear_set:
            bv /= 2
        link = item.link
        if link is not None:
            flags = link.flags
            if "F_PPC_CAPACITOR" in flags:
                bv += link.bv if link.bv else self._capacitor_bv(item)
            elif "F_ARTEMIS" in flags:
                bv *= 1.2
            elif "F_ARTEMIS_PROTO" in flags:
                bv *= 1.1
            elif "F_ARTEMIS_V" in flags:
                bv *= 1.3
            elif "F_RISC_LASER_PULSE_MODULE" in flags or "F_APOLLO" in flags:
                bv *= 1.15
        if "F_DIRECT_FIRE" in item.flags and self.has_tc:
            bv *= 1.25
        return bv

    @staticmethod
    def _capacitor_bv(weapon):
        """MiscType.getBV for a capacitor: by the PPC it charges."""
        internal = (weapon.record.get("internal") or "").upper()
        table = {"ISLIGHTPPC": 44, "ISPPC": 88, "ISHEAVYPPC": 53, "ISSNUBNOSEPPC": 87, "ISERPPC": 114, "CLERPPC": 136}
        return table.get(internal.replace(" ", ""), 0)

    def _weapon_heat(self, item):
        record = item.record
        heat = record.get("heat") or 0.0
        if "F_ONE_SHOT" in item.flags:
            heat /= 4
        ammo_type = record.get("ammo_type")
        if ammo_type in ("AC_ULTRA", "AC_ULTRA_THB"):
            heat *= 2
        elif ammo_type == "AC_ROTARY":
            heat *= 6
        heat += record.get("heat_adjust") or 0.0
        if "F_LASER" in item.flags and item.link is not None:
            if "F_RISC_LASER_PULSE_MODULE" in item.link.flags:
                heat += 2
            elif "F_LASER_INSULATOR" in item.link.flags:
                heat = max(1, heat - 1)
        if ammo_type in ("SRM_STREAK", "LRM_STREAK", "IATM"):
            heat *= 0.5
        if "F_PPC" in item.flags and item.link is not None:
            heat += 5
        return heat

    def heat_efficiency(self):
        mech = self.mech
        capacity = compute_heat_dissipation(mech) if self.current else self._built_dissipation()
        efficiency = 6 + capacity
        pods = [i for i in self.items if i.kind == "ammo" and i.record.get("ammo_type") == "COOLANT_POD"]
        if pods:
            efficiency += int(math.ceil(mech.base_heat_sinks * len(pods) / 5.0))
        if self._has("F_EMERGENCY_COOLANT_SYSTEM"):
            efficiency += 4
        xxl = "XXL" in (mech.engine_desc or "").upper()
        run_heat = 6 if xxl and self.fusion else 2                # Engine.getRunHeat
        if getattr(mech, "is_industrial", False) or "INDUSTRIAL" in (mech.cockpit_type or "").upper():
            run_heat = 0                                           # an IndustrialMek takes no movement heat (TW p.158)
        if any("supercooledmyomer" in i.canonical for i in self.items):
            run_heat = 0                                           # a working SCM (hasSCM)
        move_heat = run_heat
        if self.jump > 0:
            jump_mp = self.jump
            if self.improved_jets:
                jump_mp = jump_mp // 2 + jump_mp % 2
            jump_heat = max(6, jump_mp * 2) if xxl else max(3, jump_mp)
            if jump_heat > run_heat:
                move_heat = jump_heat
        efficiency -= move_heat
        if "STEALTH" in (mech.armor_desc or "").upper():
            efficiency -= 10
        if any("chameleon" in i.canonical for i in self.items):
            efficiency -= 6
        if any("nullsignature" in i.canonical for i in self.items):
            efficiency -= 10
        if any("voidsignature" in i.canonical for i in self.items):
            efficiency -= 10
        if self.current:
            efficiency -= 5 * getattr(mech, "engine_hits", 0)
        return efficiency

    def _built_dissipation(self):
        mech = self.mech
        rate = 2 if any(w in mech.heat_sink_type.replace(" ", "").upper() for w in ("DOUBLE", "LASER")) else 1
        return mech.base_heat_sinks * rate + (3 if getattr(mech, "partial_wing_active", False) else 0)

    def weapons(self):
        self.has_tc = self._has("F_TARGETING_COMPUTER") or any(
            "targetingcomputer" in i.canonical for i in self.items)
        weapons = [i for i in self.items if self._offensive_weapon(i)]
        # Front vs rear (MekBVCalculator.frontWeaponFilter / rearWeaponFilter): arm and turret weapons
        # are in neither - never halved.
        front = [w for w in weapons if not self._is_arm(w) and not w.turret and not w.rear]
        rear = [w for w in weapons if not self._is_arm(w) and not w.turret and w.rear]
        front_bv = sum(self._weapon_bv(w, None) for w in front)
        rear_bv = sum(self._weapon_bv(w, None) for w in rear)
        switch = front_bv < rear_bv
        nominal_rear = set(w for w in weapons if (switch ^ (w in rear)) and not self._is_arm(w) and not w.turret)
        if switch:
            self.note("(more BV faces rear: front and rear swap)")
        records = []
        for w in weapons:
            records.append((w, self._weapon_bv(w, nominal_rear), self._weapon_heat(w)))

        def order(a, b):
            ha, hb = a[2], b[2]
            if ha == 0 and hb > 0:
                return -1
            if ha > 0 and hb == 0:
                return 1
            if ha == 0 and hb == 0:
                return 0
            if a[1] == b[1]:
                return (ha > hb) - (ha < hb)
            return (b[1] > a[1]) - (b[1] < a[1])

        records.sort(key=functools.cmp_to_key(order))
        efficiency = self.heat_efficiency()
        self.note(f"Heat efficiency {efficiency}")
        exceeded = efficiency <= 0
        heat_sum = 0.0
        total = 0.0
        for w, bv, heat in records:
            heat_sum += heat
            value = bv / 2 if exceeded else bv
            total += value
            self.offensive += value
            self.note(f"+ {w.name} ({w.location}){' (R)' if w in nominal_rear else ''}"
                      f"{' half: over heat' if exceeded else ''}  heat {heat:g}", f"= {self.offensive:.2f}")
            if heat_sum >= efficiency:
                exceeded = True

    def ammunition(self):
        ammo_bv, weapon_bv = {}, {}
        for item in self.items:
            if item.kind != "ammo":
                continue
            ammo_type = item.record.get("ammo_type")
            if ammo_type in ("AMS", "APDS", "SCREEN_LAUNCHER") or "F_ONE_SHOT" in item.flags:
                continue
            key = f"{ammo_type}:{int(item.record.get('rack_size') or 0)}"
            ammo_bv[key] = ammo_bv.get(key, 0.0) + item.bv
        for item in self.items:
            if item.kind != "weapon" or {"F_B_POD", "F_M_POD"} & item.flags:
                continue
            ammo_type = item.record.get("ammo_type")
            energy = "F_ENERGY" in item.flags and ammo_type not in ("PLASMA", "VEHICLE_FLAMER", "HEAVY_FLAMER",
                                                                    "CHEMICAL_LASER")
            if energy or "F_ONE_SHOT" in item.flags or "F_INFANTRY" in item.flags or ammo_type in (None, "NA"):
                continue
            key = f"{ammo_type}:{int(item.record.get('rack_size') or 0)}"
            weapon_bv[key] = weapon_bv.get(key, 0.0) + item.bv
        for key, value in ammo_bv.items():
            if key not in weapon_bv:
                if key == "COOLANT_POD:1":
                    self.offensive += value
                continue
            counted = min(value, weapon_bv[key])
            self.offensive += counted
            self.note(f"+ ammo {key}: {value:g}{' (excessive: capped at ' + format(weapon_bv[key], 'g') + ')' if value > weapon_bv[key] else ''}",
                      f"= {self.offensive:.2f}")

    def _tsm_multiplier(self):
        return 2 if self._has("F_TSM") else 1

    def _misc_bv(self, item):
        """MiscType.getBV for the variable physical weapons, else its listed BV."""
        flags, weight = item.flags, self.mech.mass
        if item.record.get("bv") is not None:
            return item.bv
        tsm = self._tsm_multiplier()
        if "F_CLUB" in flags and "S_HATCHET" in flags:
            return math.ceil(weight / 5.0) * 1.5 * tsm
        if "F_CLUB" in flags and "S_SWORD" in flags:
            return math.ceil(weight / 10.0 + 1) * 1.725 * tsm
        if "F_CLUB" in flags and "S_LANCE" in flags:
            return math.ceil(weight / 5.0) * tsm
        if "F_CLUB" in flags and "S_MACE" in flags:
            return math.ceil(weight / 4.0) * tsm
        if "F_CLUB" in flags and "S_RETRACTABLE_BLADE" in flags:
            return math.ceil(weight / 10.0) * 1.725 * tsm
        if "F_HAND_WEAPON" in flags and "S_CLAW" in flags:
            return math.ceil(weight / 7.0) * 1.275 * tsm
        if "F_TALON" in flags:
            return _round(math.floor(weight / 5.0) * 0.5) * tsm
        if "F_RAM_PLATE" in flags:
            damage = int(weight * self.run * 0.1) // 2
            return round(damage * 1.1, 3)
        return 0.0

    def offensive_equipment(self):
        skip = {"F_AP_POD", "F_VIRAL_JAMMER_DECOY", "F_VIRAL_JAMMER_HOMING", "F_LIGHT_BRIDGE_LAYER",
                "F_MEDIUM_BRIDGE_LAYER", "F_HEAVY_BRIDGE_LAYER", "F_CHAFF_POD", "F_BULLDOZER", "F_BAP",
                "F_TARGETING_COMPUTER", "F_SPIKES", "F_MINESWEEPER", "F_HARJEL_II", "F_HARJEL_III", "F_MASS",
                "F_MINE", "F_SHIELD"}
        for item in self.items:
            if item.kind != "misc":
                continue
            flags = item.flags
            if "F_ECM" in flags and "F_WATCHDOG" not in flags:
                continue
            if skip & flags:
                continue
            bv = self._misc_bv(item)
            if bv == 0:
                continue
            if ("F_CLUB" in flags or "F_HAND_WEAPON" in flags) and self._arm_aes(item.location):
                bv *= 1.25
            elif "F_WATCHDOG" in flags:
                bv = 7
            self.offensive += bv
            self.note(f"+ {item.name} ({item.location})", f"= {self.offensive:.2f}")

    def weight(self):
        mech = self.mech
        aes = 1.0
        for loc in ARMS:
            if self._arm_aes(loc):
                aes += 0.1
        legs = [i for i in self.items if "F_ACTUATOR_ENHANCEMENT_SYSTEM" in i.flags
                and any("Leg" in loc for loc in i.slots_by_location)]
        if legs:
            aes += 0.4 if self.quad else 0.2
        weight = mech.mass * aes
        if any("F_TSM" in i.flags and "F_INDUSTRIAL_TSM" not in i.flags for i in self.items):
            self.offensive += weight * 1.5
        elif self._has("F_INDUSTRIAL_TSM"):
            self.offensive += weight * 1.15
        else:
            self.offensive += weight
        self.note(f"Weight: {mech.mass}{' x ' + format(aes, 'g') + ' (AES)' if aes != 1 else ''}",
                  f"= {self.offensive:.2f}")

    def speed_factor(self):
        mp = self.run + _round(max(self.jump, self.umu) / 2.0)
        factor = round(math.pow(1 + (mp - 5) / 10.0, 1.2) * 100.0) / 100.0
        self.offensive *= factor
        self.note(f"x speed factor {factor:g} (MP {mp})", f"= {self.offensive:.2f}")

    def type_modifier(self):
        if "INDUSTRIAL" in (self.mech.cockpit_type or "").upper() and "AFC" not in (self.mech.cockpit_type or "").upper():
            self.offensive *= 0.9
            self.note("x 0.9 (industrial fire control)", f"= {self.offensive:.2f}")

    # ------------------------------------------------------------------ TOTAL
    def run_all(self):
        self.armor()
        self.structure()
        self.defensive_equipment()
        self.explosive_equipment()
        self.defensive_factor()
        self.weapons()
        self.ammunition()
        self.offensive_equipment()
        self.weight()
        self.speed_factor()
        self.type_modifier()
        base = self.defensive + self.offensive
        self.note(f"Defensive {self.defensive:.2f} + offensive {self.offensive:.2f}", f"= {base:.2f}")
        cockpit = (self.mech.cockpit_type or "").upper()
        if "SMALL" in cockpit or "TORSO-MOUNTED" in cockpit:
            base *= 0.95
            self.note("x 0.95 (cockpit)", f"= {base:.2f}")
        elif "INTERFACE" in cockpit:
            base *= 1.3
            self.note("x 1.3 (interface cockpit)", f"= {base:.2f}")
        elif self._has("F_DRONE_OPERATING_SYSTEM"):
            base *= 0.95
        adjusted = _round(base)
        if self.skill:
            gunnery = getattr(self.mech, "gunnery", 4)
            piloting = getattr(self.mech, "piloting", 5)
            factor = skill_factor(gunnery, piloting)
            adjusted = _round(adjusted * factor)
            self.note(f"x pilot skill {factor:g} (gunnery {gunnery}, piloting {piloting})", f"= {adjusted}")
        return adjusted


def battle_value(mech, current=False, skill=True):
    """The 'Mech's Battle Value (see the module docstring). current=False: as built;
    skill=False: before the pilot's skill factor (MegaMek's "base BV")."""
    return _Calc(mech, current, skill).run_all()


def battle_value_report(mech, current=False, skill=True):
    calc = _Calc(mech, current, skill)
    bv = calc.run_all()
    return bv, calc.lines


def missing_items(mech):
    """Names of the 'Mech's weapons and ammunition that equipment_bv.json has no record of (counted
    as 0 BV). Other gear without a record has no BV line in MegaMek either (heat sinks, structure...)."""
    return [item.equip.name for item in _equipment(mech, False)
            if not item.record and getattr(item.equip, "category", None) in ("weapon", "ammo")]
