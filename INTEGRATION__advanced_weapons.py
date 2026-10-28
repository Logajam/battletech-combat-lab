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

INTERSTELLAR OPERATIONS (2026-10-28; Daniel pasted the rules - "IO" below -
and, for stats a paste doesn't give, "megamek's values to use"; Daniel:
"Build what could be used. Custom units are and will be a thing."):

TSEMP CANNON / ONE-SHOT (IO pp.90-91) and REPEATING TSEMP (IO p.88):
  - Fires as a direct-fire energy weapon (heat 10, range 5/10/15, slots 5 /
    3 / 7 - MegaMek's values); no damage. A hit: the attacker rolls 2D6 on
    the TSEMP Effects Table - -2 if the target weighs 100 tons or more, -1 for
    an ICE engine (-2 steam: no 'Mech has one); +1 for each earlier TSEMP hit
    on that target this turn (at most +4); a result below 2 counts as 2. No
    effect on a unit of 200 tons or more (the table's "200+ tons NA" - the
    text says "no more than 200 tons"; MegaMek follows the table).
      BattleMech: 7-8 interference, 9+ shutdown; IndustrialMech: 6-7 / 8+.
  - Interference: +2 to hit for all its weapon attacks (not physical attacks
    - MegaMek too) and it is treated as inside a hostile ECM field
    (electronics.as_if_jammed). Multiple interference results don't stack.
  - Shutdown: shut down. Either effect lasts until the End Phase of the turn
    after the hit (end_phase).
  - The firing unit suffers interference itself, the same way (whether or
    not it hit).
  - The TSEMP Cannon can't fire in consecutive turns (it recharges); the
    One-Shot fires once; the Repeating TSEMP may fire every turn.
  - Critical hit: an internal explosion treated like a Gauss explosion, never
    from heat - 2 points a slot (Core p.96; Daniel: the Core rule overrides
    IO's 10): 10 / 6 / 14 (equipment.json). A fired One-Shot can't explode.
  - Repeating TSEMP: an unmodified attack roll of 2 has the effects of a
    critical hit on it (it explodes) and delivers no effect to the target.
  Battle armor, vehicles, infantry etc.: no such units here.

iATM (IO; INTEGRATION__fire_modes / weapon_rules.is_streak): an ATM that,
fired directly, works as a Streak launcher: no lock (a missed attack roll)
aborts the shot - no heat, no ammo - and a hit lands every missile, no
Cluster roll. Ammunition: standard, ER, HE (as ATM), plus IMP and IIW:
  - IMP (improved magnetic pulse): HE range, 1 damage a missile; for every 3
    IMP missiles that strike a 'Mech it is treated as inside a hostile
    standard ECM field, +1 to all its attack rolls (at most +2) and -1
    Walking and Jumping MP (at most -2; Running from the reduced Walking);
    +1 heat for every 3 (outside heat, Core p.103). Until the End Phase of
    the following turn; strikes while it lasts do their damage but add no
    to-hit or MP effect (imp_hit). A 'Mech not powered by a fusion engine
    ignores the MP and heat effects.
  - IIW (improved inferno): standard ATM range; resolved by the inferno rules.
  Indirect fire (as an LRM) needs a spotter (Core p.70) - none in a duel.
INFERNO MISSILES (Core p.192, built 2026-10-28 for IIW and any unit's inferno
bins): no damage, no hit location; each missile that strikes deals 2 heat,
applied in that turn's Heat Phase (outside heat, at most 15 a turn - p.103;
none with heat-dissipating armor - p.202).

NAIL / RIVET GUN (MegaMek's rule - Daniel: "Borrow from megamek for the
nail gun too"): range 1, no heat, 1D6 a hit, no damage to a location that
still has armor (MegaMek: armor of BAR 5 or more - every 'Mech armor here);
damage that would transfer into an armored location is lost (nail_damage,
attack_resolution._resolve_nail).
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


def is_tsemp(weapon):
    return "TSEMP" in _cn(weapon)


def is_nail_gun(weapon):
    n = _cn(weapon)
    return "NAIL" in n or "RIVET" in n


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
    _destroy_all_slots(attacker, weapon)
    apply_explosion(attacker, _Round(weapon), location)


def _destroy_all_slots(mech, weapon):
    for loc, slots in mech.crits.items():
        for i, s in enumerate(slots):
            if s is weapon:                  # every slot destroyed - not a critical hit, so no AC "first crit" grace
                mech.destroyed_slot_info[(loc, i)] = {"name": weapon.name, "instance_id": id(weapon)}
                slots[i] = "DESTROYED"


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
    _tsemp_end_phase(mech, turn)
    _imp_end_phase(mech, turn)
    for key, what in (("taser_shutdown_until", "Taser"), ("tsemp_shutdown_until", "TSEMP")):
        until = getattr(mech, key, None)
        if until is None or turn < until:
            continue
        setattr(mech, key, None)
        if held_down(mech):
            config.log(f"  [End] {mech.side_name}: the {what} shutdown ends; another effect still holds it down.")
        elif mech.current_heat < 14:
            mech.shutdown = False
            config.log(f"  [End] {mech.side_name}: the {what} shutdown ends - it powers up.")
        else:
            config.log(f"  [End] {mech.side_name}: the {what} shutdown ends; heat {mech.current_heat} - "
                       f"it must restart as normal.")


def held_down(mech):
    """Still shut down by a Taser or a TSEMP: no heat restart before the effect ends."""
    return (getattr(mech, "taser_shutdown_until", None) is not None
            or getattr(mech, "tsemp_shutdown_until", None) is not None)


# =============================================================================
# ==========================  MORTARS: INDIRECT FIRE  =========================
# =============================================================================
def indirect_weapons(mech):
    """Weapons that may fire indirectly with no spotter: 'Mech mortars (p.136)."""
    return [w for w in get_weapons(mech) if is_mortar(w)]


# =============================================================================
# ==========================  TSEMP  ==========================================
# =============================================================================
TSEMP_TABLE = {"BattleMech": (7, 9), "IndustrialMech": (6, 8)}    # IO p.91: (interference at least, shutdown at least)
TSEMP_INTERFERENCE = 2              # +2 to hit, weapon attacks
TSEMP_HEAVY_TONS, TSEMP_HEAVY_MODIFIER = 100, -2
TSEMP_NO_EFFECT_TONS = 200
TSEMP_ICE_MODIFIER = -1             # -2 steam: no 'Mech has a steam engine
TSEMP_STACK_MAX = 4
TSEMP_MISFEED_ROLL = 2              # Repeating TSEMP (IO p.88)


def _engine_text(mech):
    return (getattr(mech, "engine_desc", "") or "").upper()


def ice_engine(mech):
    return "ICE" in _engine_text(mech).replace("(", " ").split()


def fusion_engine(mech):
    """Fission, fuel cell, ICE (and steam, battery...) aren't fusion; every
    other 'Mech engine (standard, XL, XXL, light, compact) is."""
    return not any(k in _engine_text(mech) for k in ("ICE", "FUEL CELL", "FUELCELL", "FISSION", "STEAM",
                                                       "BATTERY", "SOLAR", "NONE"))


def tsemp_repeating(weapon):
    return "REPEATING" in _cn(weapon)


def tsemp_interference(mech):
    return TSEMP_INTERFERENCE if getattr(mech, "tsemp_interference_until", None) is not None else 0


def _interfere(mech, turn, why):
    mech.tsemp_interference_until = max(turn + 1, getattr(mech, "tsemp_interference_until", None) or 0)
    config.log(f"      {why}: TSEMP interference on {mech.side_name} through turn {turn + 1} - +{TSEMP_INTERFERENCE} "
               f"to hit with weapons, as if inside hostile ECM (IO p.91).")


def tsemp_fired(attacker, weapon, roll, turn, location):
    """A TSEMP fires (at its attack roll, hit or miss). Returns False if a
    Repeating TSEMP blew up on a roll of 2 - no effect on the target."""
    if tsemp_repeating(weapon) and roll == TSEMP_MISFEED_ROLL:
        config.log(f"      {weapon.name}: attack roll 2 - the effects of a critical hit (IO p.88): it explodes, "
                   f"no effect on the target.")
        _destroy_all_slots(attacker, weapon)
        weapon.exploded = True
        apply_explosion(attacker, weapon, location)
        return False
    if getattr(weapon, "one_shot", False):
        weapon.is_explosive, weapon.explosion_damage = False, 0      # a fired One-Shot can't explode (IO p.91)
    elif not tsemp_repeating(weapon):
        weapon.tsemp_recharge_until = turn + 1       # no firing next turn (IO p.91)
    _interfere(attacker, turn, f"{attacker.side_name} fired its {weapon.name}")
    return True


def recharging(weapon):
    return getattr(weapon, "tsemp_recharge_until", None) is not None


def tsemp_hit(attacker, target, turn):
    """A TSEMP hit (IO pp.90-91): the Effects roll."""
    if is_destroyed(target):
        return
    mass = getattr(target, "mass", 0) or 0
    if mass >= TSEMP_NO_EFFECT_TONS:
        config.log(f"      TSEMP: no effect on a unit of {TSEMP_NO_EFFECT_TONS} tons or more (IO p.91).")
        return
    seen_turn, count = getattr(target, "tsemp_hits", (None, 0))
    count = count + 1 if seen_turn == turn else 1
    target.tsemp_hits = (turn, count)
    mods = []
    if mass >= TSEMP_HEAVY_TONS:
        mods.append((TSEMP_HEAVY_MODIFIER, "100+ tons"))
    if ice_engine(target):
        mods.append((TSEMP_ICE_MODIFIER, "ICE engine"))
    if count > 1:
        mods.append((min(TSEMP_STACK_MAX, count - 1), f"TSEMP hit {count} this turn"))
    raw = config.roll_2d6(prompt="TSEMP effects roll")
    result = max(2, raw + sum(m for m, _ in mods))
    column = _taser_column(target)
    interfere_at, shutdown_at = TSEMP_TABLE[column]
    note = f"TSEMP effects roll {raw}{''.join(f' {m:+d} ({why})' for m, why in mods)} = {result} ({column})"
    if result >= shutdown_at:
        target.tsemp_shutdown_until = max(turn + 1, getattr(target, "tsemp_shutdown_until", None) or 0)
        target.shutdown = True
        config.log(f"      {note}: {target.side_name} SHUTS DOWN through turn {turn + 1} (IO p.91).")
    elif result >= interfere_at:
        config.log(f"      {note}: interference.")
        _interfere(target, turn, "TSEMP hit")
    else:
        config.log(f"      {note}: no effect.")


def _tsemp_end_phase(mech, turn):
    until = getattr(mech, "tsemp_interference_until", None)
    if until is not None and turn >= until:
        mech.tsemp_interference_until = None
        config.log(f"  [End] {mech.side_name}: TSEMP interference ends.")
    for w in get_weapons(mech):
        if recharging(w) and turn >= w.tsemp_recharge_until:
            w.tsemp_recharge_until = None


def recharging_ids(mech):
    """TSEMP Cannons that fired last turn (can't fire this turn)."""
    return frozenset(id(w) for w in get_weapons(mech) if recharging(w))


# =============================================================================
# ==========================  iATM IMP / INFERNOS  ============================
# =============================================================================
IMP_PER_STEP = 3                    # every 3 IMP missiles
IMP_MAX = 2                         # at most +2 to hit / -2 MP
INFERNO_HEAT_PER_MISSILE = 2        # Core p.192


def outside_heat(target, amount, source):
    """Outside heat on a 'Mech, applied in its Heat Phase (Core p.103, at most 15
    a turn - INTEGRATION__heat); none with heat-dissipating armor (p.202)."""
    from INTEGRATION__attack_resolution import has_heat_dissipating_armor     # it imports this module
    if amount <= 0:
        return
    if has_heat_dissipating_armor(target):
        config.log(f"      {source}: heat-dissipating armor - no heat to {target.side_name} (p.202).")
        return
    target.outside_heat = getattr(target, "outside_heat", 0) + amount
    config.log(f"      {source}: +{amount} heat to {target.side_name} (outside heat, p.103).")


def inferno_hit(target, missiles, source):
    """Inferno missiles that strike (Core p.192): 2 heat each, no damage."""
    config.log(f"      {missiles} inferno missile{'s' if missiles != 1 else ''}: no damage, "
               f"{INFERNO_HEAT_PER_MISSILE} heat each (p.192).")
    outside_heat(target, INFERNO_HEAT_PER_MISSILE * missiles, source)


def imp_level(mech):
    """The IMP effect now: +this to hit, -this Walking / Jumping MP."""
    return getattr(mech, "imp_level", 0) if getattr(mech, "imp_until", None) is not None else 0


def imp_hit(target, missiles, turn):
    """IMP missiles strike a 'Mech (module docstring): their damage is dealt as
    normal; this applies the effects."""
    if is_destroyed(target):
        return
    started = getattr(target, "imp_started", None)
    if getattr(target, "imp_until", None) is not None and started != turn:
        effect = False                       # already affected: damage only (no new to-hit / MP effects)
    else:
        effect = True
    seen_turn, before = getattr(target, "imp_missiles", (None, 0))
    before = before if seen_turn == turn else 0
    total = before + missiles
    target.imp_missiles = (turn, total)
    if effect:
        level = min(IMP_MAX, total // IMP_PER_STEP)
        if level:
            target.imp_level, target.imp_until, target.imp_started = level, turn + 1, turn
            target.imp_mp = level if fusion_engine(target) else 0    # read by mech_state's Walking / Jumping MP
            config.log(f"      IMP: {total} missiles this turn - {target.side_name} as if inside hostile ECM, "
                       f"+{level} to hit and {'-' + str(level) if fusion_engine(target) else 'no (not fusion-powered)'} "
                       f"Walking / Jumping MP through turn {turn + 1} (IO).")
    else:
        config.log(f"      IMP: {target.side_name} is already affected - damage only.")
    if fusion_engine(target):
        heat = total // IMP_PER_STEP - before // IMP_PER_STEP
        outside_heat(target, heat, "IMP missiles")


def _imp_end_phase(mech, turn):
    until = getattr(mech, "imp_until", None)
    if until is not None and turn >= until:
        mech.imp_until, mech.imp_level, mech.imp_started, mech.imp_mp = None, 0, None, 0
        config.log(f"  [End] {mech.side_name}: the IMP effects end.")


def as_if_jammed(mech):
    """TSEMP interference / IMP: treated as inside a hostile ECM field."""
    return bool(tsemp_interference(mech) or imp_level(mech))


def own_attack_modifier(mech, physical=False):
    """To-hit added to this unit's attacks: Taser interference (all), TSEMP
    interference (weapon attacks only), IMP (all attack rolls)."""
    return interference(mech) + (0 if physical else tsemp_interference(mech)) + imp_level(mech)


# =============================================================================
# ==========================  NAIL / RIVET GUN  ===============================
# =============================================================================
NAIL_DIE = 6
NAIL_EXPECTED = 3.5


def nail_worth(target, side):
    """Expected damage of a nail gun hit: 3.5 times the chance the hit lands
    on a location with no armor left (bot pricing)."""
    import hit_location
    from INTEGRATION__expected_damage import _2D6_EXACT as ROLL_ODDS
    table = (hit_location.HIT_TABLE_LEFT_SIDE if side == "left" else hit_location.HIT_TABLE_RIGHT_SIDE
             if side == "right" else hit_location.HIT_TABLE_FRONT_REAR)
    field = "rear_armor" if side == "rear" else "armor"
    bare = 0.0
    for roll, p in ROLL_ODDS.items():
        loc = table.get(roll)
        info = target.locations.get(loc)
        if info is not None and not info["destroyed"] and info.get(field, info["armor"]) <= 0:
            bare += p
    return NAIL_EXPECTED * bare
