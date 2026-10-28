"""INTEGRATION__advanced_weapons.py - weapons from Tactical Operations:
Advanced Units & Equipment (TO:AUE) that need more than a table row
(NEW 2026-10-27, Claude; Daniel: "wire in functionality of missing weapons,
equipment, and hex types already noted"). Their table rows (damage, heat,
range, shots a ton) are in mechsim/equipment.json ("to_aue_pass").

HYPER-VELOCITY AUTOCANNON (HVAC, p.97): fires like a standard autocannon,
except -
  - Misfeed: a to-hit roll of 2 ignites the chambered round: internal
    explosion damage equal to one HVAC round, treated as an ammunition
    explosion (CASE applies), and every critical slot of the HVAC is
    destroyed (hvac_misfeed).
  - Smoke: the hex behind the firing unit (opposite the direction it fired)
    fills with heavy smoke, 2 levels high, until the start of the End Phase
    of the turn after it fired; if a hill or building fills those levels
    the smoke stays in the firer's own hex instead (hvac_smoke ->
    INTEGRATION__smoke). Wind and drift are an optional rule - not built.
    Claude's readings (Daniel may overrule): "behind" is the hex next to the
    firer on the far side from the target; "a hill occupies the elevations"
    = that hex is higher than the firer's.

'MECH MORTARS (pp.136, 185-186): operate like LRMs (Cluster Hits Table by
rack size). Ammunition: a mortar with no ammo type named fires armor-
piercing (shaped-charge) shells - every unit in data/meks.zip ("SC Mortar"
bins) - 2 damage a shell in 2-point groups (equipment.json; weapon_rules).
  - Fired directly: +3 to hit (weapon_rules.weapon_tn_modifier).
  - Fired indirectly (no LOS to the target, p.70 Core: an attacker with LOS
    can't fire indirectly): needs no spotter; the LRM indirect +1 plus +2
    for having no spotter - the same +3 - and only the target hex's own
    terrain modifiers count (Core p.70: no spotter LOS; partial cover
    ignored). Only the mortars fire (indirect_weapons).
  - AMS may not engage them (INTEGRATION__ams).
  Not built: the other shells (airburst, anti-personnel, flare, semi-
  guided, smoke) - no unit in data/meks.zip carries them.

BATTLEMECH TASER (pp.157-158): +1 to hit (weapon_rules), no targeting
computer bonus, not underwater, no effect on a unit over 100 tons. A hit
does 1 damage, then the attacker rolls 2D6 on the Taser Effects Table
(BattleMech column for a 'Mech target): 11+ shuts it down for 3 turns (an
immobile target); otherwise interference: +2 to its Piloting- and Gunnery-
related target numbers for 3 turns, and it makes 5 heat a turn while
affected. A later hit re-rolls (a shutdown target stays down) and restarts
the interference count; effects end in the End Phase of the last turn
(a hit in turn 1 lasts through turn 4, the p.158 example). A destroyed
Taser explodes for 6 (equipment.json); its ammo for 6 a shot (INTEGRATION__
ammo). The bot prices a hit's effect at config.TASER_EFFECT_WORTH -
a PLACEHOLDER until Daniel sets it (like TARGET_HEAT_WORTH).

NO EFFECT ON 'MECHS (left unfired, not "can't fire"):
  - Fluid guns (p.125) with water ammo - the default, and every fluid gun
    bin in data/meks.zip: no damage, and each hit COOLS the target by 1
    (p.175) - never worth firing at an enemy.
  - Vehicular grenade launchers (p.127) with fragmentation grenades - the
    default and every VGL in data/meks.zip: no damage to 'Mechs (p.175).
  The other fluid / grenade ammunition (corrosive, paint, oil, chaff, smoke,
  incendiary...) isn't carried by any unit - not built.
"""

import INTEGRATION__config as config
import INTEGRATION__weapon_rules as weapon_rules
from damage_resolution import apply_explosion, get_weapons
from mech_state import is_destroyed

# Taser Effects Table (p.158), the BattleMech Taser's columns for a 'Mech target.
TASER_SHUTDOWN_ROLL = {"BattleMech": 11, "IndustrialMech": 8}      # 2D6 needed
TASER_TURNS = {"BattleMech": 3, "IndustrialMech": 4}               # turns in parentheses
TASER_INTERFERENCE = 2                                              # +2 Piloting / Gunnery
TASER_HEAT = 5                                                      # heat a turn while interfered with
TASER_MAX_TONNAGE = 100                                             # no effect above 100 tons (p.157)

MORTAR_DIRECT_MODIFIER = 3          # p.136: fired directly
MORTAR_INDIRECT_MODIFIER = 3        # Core p.70 indirect +1, plus +2 without a spotter (TO:AUE p.136)
HVAC_MISFEED_ROLL = 2               # p.97


def _cn(weapon):
    return weapon_rules.canonical_name(weapon)


def is_hvac(weapon):
    return "HYPERVELOCITY" in _cn(weapon)


def is_mortar(weapon):
    return "MORTAR" in _cn(weapon)


def is_taser(weapon):
    return "TASER" in _cn(weapon)


def no_effect_on_mechs(weapon):
    """Fluid guns (water) and VGLs (fragmentation): see the module docstring."""
    n = _cn(weapon)
    return "FLUIDGUN" in n or "GRENADELAUNCHER" in n


def no_effect_ids(mech):
    return frozenset(id(w) for w in get_weapons(mech) if no_effect_on_mechs(w))


# =============================================================================
# ==========================  HVAC  ===========================================
# =============================================================================
def hvac_misfeed(attacker, weapon, location):
    """p.97: one round's damage as an ammunition explosion in the HVAC's
    location, and every slot of the HVAC destroyed."""
    config.log(f"      {weapon.name} MISFEEDS (to-hit roll 2, TO:AUE p.97): the round's propellant ignites in the "
               f"barrel - {weapon.damage_per_shot} internal explosion damage in {location}.")
    for loc, slots in attacker.crits.items():
        for i, s in enumerate(slots):
            if s is weapon:                  # every slot destroyed - not a critical hit, so no AC "first crit" grace
                attacker.destroyed_slot_info[(loc, i)] = {"name": weapon.name, "instance_id": id(weapon)}
                slots[i] = "DESTROYED"
    apply_explosion(attacker, _Round(weapon), location)


class _Round:
    """The chambered HVAC round, exploding like ammunition (p.97)."""
    category = "ammo"
    is_explosive = True

    def __init__(self, weapon):
        self.name = f"{weapon.name} round"
        self.explosion_damage = weapon.damage_per_shot or 0


def hvac_smoke(attacker, target, terrain_map, turn):
    """Heavy smoke in the hex behind the firer (module docstring)."""
    import INTEGRATION__smoke as smoke
    import hex_geometry
    import combat
    a_xy, t_xy = hex_geometry.parse_hex_label(attacker.hex), hex_geometry.parse_hex_label(target.hex)
    away = combat._direction_facing(t_xy, a_xy)              # from the target through the firer
    dx, dy = hex_geometry.FACING_DELTAS[away]
    here = terrain_map["hexes"][attacker.hex]
    label = attacker.hex
    try:
        behind = hex_geometry.hex_label(a_xy[0] + dx, a_xy[1] + dy)
    except ValueError:
        behind = None
    info = terrain_map["hexes"].get(behind) if behind else None
    if info is not None and info["level"] <= here["level"]:
        label = behind
    elif info is None:
        return                                                # behind is off the board: drifts away
    smoke.add(label, smoke.HEAVY, turn + 1, f"{attacker.side_name}'s HVAC fire")


# =============================================================================
# ==========================  TASER  ==========================================
# =============================================================================
def _taser_column(target):
    return "IndustrialMech" if getattr(target, "is_industrial", False) else "BattleMech"


def taser_hit(attacker, target, turn):
    """A Taser hit (pp.157-158) - after its 1 point of damage."""
    if is_destroyed(target):
        return
    if (getattr(target, "mass", 0) or 0) > TASER_MAX_TONNAGE:
        config.log(f"      Taser: no effect on a unit over {TASER_MAX_TONNAGE} tons (TO:AUE p.157).")
        return
    column = _taser_column(target)
    need, turns = TASER_SHUTDOWN_ROLL[column], TASER_TURNS[column]
    roll = config.roll_2d6(prompt="Taser effect roll")
    until = turn + turns                       # ends in that turn's End Phase (p.157 example)
    if roll >= need:
        if not target.shutdown:
            target.shutdown = True
            target.taser_shutdown_until = until
            config.log(f"      Taser effect roll {roll} (needs {need}): {target.side_name} SHUTS DOWN through "
                       f"turn {until} (TO:AUE p.158).")
        else:
            config.log(f"      Taser effect roll {roll}: {target.side_name} is already shut down.")
        return
    target.taser_interference_until = until
    config.log(f"      Taser effect roll {roll} (shutdown needs {need}): interference - +{TASER_INTERFERENCE} to "
               f"{target.side_name}'s Piloting and Gunnery target numbers and {TASER_HEAT} heat a turn "
               f"through turn {until} (TO:AUE p.158).")


def interference(mech):
    """The Taser's +2 to Piloting- and Gunnery-related target numbers."""
    return TASER_INTERFERENCE if getattr(mech, "taser_interference_until", None) is not None else 0


def taser_heat(mech):
    """5 heat a turn while interfered with (p.158 footnote)."""
    return TASER_HEAT if interference(mech) else 0


def end_phase(mech, turn):
    """Taser effects end in the End Phase of their last turn. A Taser
    shutdown ends then; if the heat scale would keep the 'Mech down (14+),
    the next Heat Phase's restart roll decides as usual."""
    if getattr(mech, "taser_interference_until", None) is not None and turn >= mech.taser_interference_until:
        mech.taser_interference_until = None
        config.log(f"  [End] {mech.side_name}: Taser interference ends.")
    until = getattr(mech, "taser_shutdown_until", None)
    if until is not None and turn >= until:
        mech.taser_shutdown_until = None
        if mech.current_heat < 14:
            mech.shutdown = False
            config.log(f"  [End] {mech.side_name}: the Taser shutdown ends - it powers up.")
        else:
            config.log(f"  [End] {mech.side_name}: the Taser shutdown ends; heat {mech.current_heat} - "
                       f"it must restart as normal.")


def held_down(mech):
    """Still shut down by a Taser: no heat restart before the effect ends."""
    return getattr(mech, "taser_shutdown_until", None) is not None


# =============================================================================
# ==========================  MORTARS: INDIRECT FIRE  =========================
# =============================================================================
def indirect_weapons(mech):
    """Weapons that may fire indirectly with no spotter: 'Mech mortars (p.136)."""
    return [w for w in get_weapons(mech) if is_mortar(w)]
