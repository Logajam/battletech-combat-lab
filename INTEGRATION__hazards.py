"""INTEGRATION__hazards.py - terrain that burns, poisons or holds a 'Mech
(NEW 2026-10-27, Claude; Daniel: "wire in functionality of missing weapons,
equipment, and hex types already noted"). Rules: Tactical Operations:
Advanced Rules (TO:AR).

MAGMA (pp.30, 34-35; MegaMek "magma:1" crust, "magma:2" liquid):
  - Crust: each time a 'Mech enters one along the ground, 1D6: on a 6 the
    crust breaks and the hex is liquid magma for the rest of the battle; a
    jump LANDING in it breaks it on 4-6 (p.34). +1 to Piloting rolls made in
    it (p.30). Heat: +2 for each crust hex entered but not occupied in the
    Heat Phase, +5 for occupying one then (p.35).
  - Liquid: a 'Mech that starts its Movement Phase in one, or enters one,
    takes 2D6 to each exposed location (the legs, or every location if it
    has fallen - front and rear torsos both), one attack, a roll per
    location; starting AND ending a Movement Phase in liquid magma adds
    another 2D6 per exposed location (p.35). +1 MP to enter and +4 to
    Piloting rolls in it (p.30). Entering may bog the 'Mech down (p.30 fn 24,
    p.60): a Piloting roll at +4, failure = stuck (no fall); a 'Mech jumping
    in makes the same roll (p.35). Heat: +5 per liquid hex entered but not
    occupied in the Heat Phase, +10 for occupying one; magma heat is NOT held
    to the 15-point outside heat cap - the other outside heat is capped
    first, then all the magma heat is added (p.35).
  - Not built: eruptions (an optional rule, p.35 - "Advanced rules has a
    huge variety of options that are not worth adding at this time").

HAZARDOUS LIQUID POOLS (p.47; MegaMek puts "hazardous_liquid" on water
hexes): for movement, Piloting rolls and prohibition a pool IS a water hex
(INTEGRATION__water does all of that). Whenever a 'Mech enters a pool hex,
or begins its Movement Phase in one (rolled before it moves), roll 1D6 on
the Hazardous Liquid Pools Table: 1-2 nothing, 3 1D6/2, 4 1D6, 5 1D6+2,
6 2D6 (all rounded down). The damage goes in 5-point groupings, each to a
random location; a 'Mech standing in a depth 1 pool takes it on the legs
only. Claude's readings (Daniel may overrule): "random location" = a roll on
the front column of the 'Mech Hit Location Table; a 'Mech standing in depth
2+ or lying in the pool takes it anywhere (it is under the liquid). Flow and
eruptions (optional, need Water Flow / eruption rules) are not built.

BOGGING DOWN (pp.60-61, the rules liquid magma calls on):
  - stuck: may not move for the rest of the turn, may twist but not turn;
    attacks on it are at -2 (attack_resolution._target_tmm); no kicks.
  - At the start of each Movement Phase a Piloting roll (+4 in liquid magma)
    frees it. A 'Mech stuck after ground movement may instead simply jump
    out (it rolls first; failing, it may still jump).
  - A 'Mech that FALLS in such a hex is stuck automatically and needs three
    successful rolls: free itself from the stuck prone position (start of a
    Movement Phase), stand up (the normal stand-up roll), then free itself
    from the hex (the next Movement Phase's roll).

Movement scoring (Gladiator, INTEGRATION__movement_selection) prices the
EXPECTED DAMAGE of the hexes a path enters (terrain_rules.step_hazard, for a
standing biped: liquid magma 14, crust 14/6, pool 17.5/6) and of starting
next turn in the end hex; magma heat and the chance of bogging down are not
priced. Princess prices her end hex the way MegaMek does (calcMagmaHazard,
calcHazardousLiquidHazard - INTEGRATION__princess.hazards).

The battle's board is set once per battle (set_board), like
INTEGRATION__water; crust broken during a battle is put back when the next
battle starts, so battles in a batch don't leak into each other.
"""

from typing import Dict, List, Optional

import INTEGRATION__config as config
import INTEGRATION__los_cache  # noqa: F401 - puts PATHFINDER on sys.path
import terrain_rules  # noqa: E402 - PATHFINDER
from terrain_rules import MAGMA_CRUST, MAGMA_LIQUID, magma_state  # noqa: E402 - PATHFINDER
from damage_resolution import apply_damage  # noqa: E402 - MECHSIM
from hit_location import resolve_hit_location  # noqa: E402 - MECHSIM
from mech_state import is_destroyed  # noqa: E402 - MECHSIM

# Magma (TO:AR pp.34-35).
CRUST_BREAKS_GROUND = 6          # 1D6 on entering a crust along the ground: 6 breaks it (p.34)
CRUST_BREAKS_JUMP = 4            # a jump landing breaks it on 4, 5 or 6 (p.34)
MAGMA_PSR_MODIFIER = {MAGMA_CRUST: 1, MAGMA_LIQUID: 4}   # Expanded Movement Costs Table (p.30)
MAGMA_HEAT_ENTERED = {MAGMA_CRUST: 2, MAGMA_LIQUID: 5}   # each hex entered, not occupied in the Heat Phase
MAGMA_HEAT_OCCUPIED = {MAGMA_CRUST: 5, MAGMA_LIQUID: 10}  # the hex occupied in the Heat Phase

# Hazardous Liquid Pools Table (p.47): 1D6 -> damage (rounded down).
POOL_GROUPING = 5                # 5-point Damage Value groupings (p.47)

# Bog Down Rules (p.60).
STUCK_TO_HIT = -2                # attacks against a stuck unit

_BOARD: Optional[dict] = None
_BROKEN: List[dict] = []         # hex infos whose crust broke this battle (put back by set_board)


def set_board(terrain_map):
    """The battle's board (orchestrator.run_battle, once per battle). Crust
    broken in an earlier battle on this board is mended first."""
    global _BOARD
    for info in _BROKEN:
        info["features"]["magma"] = [MAGMA_CRUST]
    _BROKEN.clear()
    _BOARD = terrain_map


def _info(label):
    if _BOARD is None or label is None:
        return None
    return _BOARD["hexes"].get(label)


def magma_at(label) -> Optional[str]:
    info = _info(label)
    return magma_state(info["features"]) if info else None


def pool_at(label) -> bool:
    info = _info(label)
    return bool(info) and "hazardous_liquid" in info["features"]


def psr_modifier(label) -> int:
    """The hex's Piloting modifier (p.30): magma crust +1, liquid +4."""
    return MAGMA_PSR_MODIFIER.get(magma_at(label), 0)


def is_stuck(mech) -> bool:
    return bool(getattr(mech, "stuck", None))


def bogs_down(label) -> bool:
    """Can entering this hex bog a 'Mech down? Liquid magma (p.30 fn 24)."""
    return magma_at(label) == MAGMA_LIQUID


# =============================================================================
# ==========================  DAMAGE  =========================================
# =============================================================================
def _d6(what):
    return config.pick_number(6, prompt=what)


def _exposed(mech, prone):
    """Locations liquid magma reaches (p.35): the legs, or all of them once
    fallen - each torso front AND rear. (location, armor field) pairs."""
    out = []
    for loc, entry in mech.locations.items():
        if entry["destroyed"]:
            continue
        if not prone and loc not in mech.leg_locations:
            continue
        out.append((loc, "armor"))
        if prone and "rear_armor" in entry:
            out.append((loc, "rear_armor"))
    return out


def _with_damage_psr(mech, apply):
    """Damage outside the attack phases (like a failed MASC, equipment_
    systems.apply_booster_failures): it counts toward the 20-point and the
    damage-triggered Piloting rolls, resolved straight after."""
    import piloting_rolls
    from INTEGRATION__attack_resolution import _with_piloting
    if mech.prone or _IN_PHASE:
        apply()                              # prone: can't fall again (p.110); in a phase: its own rolls
        return
    piloting_rolls.snapshot_pre_attack_phase(mech)
    apply()
    if not is_destroyed(mech):
        _with_piloting(mech, piloting_rolls.resolve_attack_phase_psr)


def magma_burn(mech, why):
    """2D6 to each exposed location, one attack (p.35)."""
    spots = _exposed(mech, mech.prone)
    if not spots or is_destroyed(mech):
        return

    def apply():
        rolls = []
        for loc, field in spots:
            if is_destroyed(mech) or mech.locations[loc]["destroyed"]:
                continue
            dmg = config.roll_2d6(prompt=f"Liquid magma damage to {loc}")
            rolls.append(f"{loc}{' (rear)' if field == 'rear_armor' else ''} {dmg}")
            apply_damage(mech, loc, dmg, armor_field=field)
        config.log(f"    {mech.side_name}: {why} - liquid magma burns {', '.join(rolls)} (2D6 each, TO:AR p.35).")
    _with_damage_psr(mech, apply)


def pool_damage(mech, why):
    """One roll on the Hazardous Liquid Pools Table (p.47), damage in
    5-point groupings to random locations (module docstring)."""
    if is_destroyed(mech):
        return
    roll = _d6("Hazardous liquid pool class (1D6)")
    if roll <= 2:
        dmg, what = 0, "Class 0: normal"
    elif roll == 3:
        dmg, what = _d6("Class 1 damage (1D6/2)") // 2, "Class 1: slightly hazardous"
    elif roll == 4:
        dmg, what = _d6("Class 2 damage (1D6)"), "Class 2: hazardous"
    elif roll == 5:
        dmg, what = _d6("Class 3 damage (1D6+2)") + 2, "Class 3: extreme danger"
    else:
        dmg, what = config.roll_2d6(prompt="Deadly pool damage (2D6)"), "deadly"
    config.log(f"    {mech.side_name}: {why} - hazardous liquid roll {roll} ({what}): {dmg} damage (TO:AR p.47).")
    if dmg <= 0:
        return
    import INTEGRATION__water as water
    legs_only = water.state_at(mech.hex, mech.prone) == water.PARTIAL      # standing in depth 1

    def apply():
        left = dmg
        while left > 0 and not is_destroyed(mech):
            group = min(POOL_GROUPING, left)
            left -= group
            if legs_only:
                legs = [l for l in mech.leg_locations if not mech.locations[l]["destroyed"]]
                if not legs:
                    return
                loc = legs[config.pick_number(len(legs), prompt="Hazardous liquid: which leg") - 1]
            else:
                loc = resolve_hit_location(config.roll_2d6(prompt="Hazardous liquid hit location"), mech, "front")
            apply_damage(mech, loc, group)
    _with_damage_psr(mech, apply)


# =============================================================================
# ==========================  ENTERING A HEX  =================================
# =============================================================================
def enter_hex(mech, label, jumped=False, why=None, in_phase=False) -> Optional[str]:
    """A 'Mech has just entered `label` - a ground step, a jump landing
    (jumped=True) or a displacement. Breaks magma crust, burns, rolls the
    pool, notes the heat and makes the bog-down roll. Returns "stuck" when
    it bogs down, else None. in_phase: entered during an attack phase (a
    push, charge or DFA) - the damage counts toward that phase's own
    Piloting rolls instead of rolling them here."""
    global _IN_PHASE
    _IN_PHASE = in_phase
    try:
        return _enter_hex(mech, label, jumped, why)
    finally:
        _IN_PHASE = False


_IN_PHASE = False


def _enter_hex(mech, label, jumped, why):
    if _BOARD is None or is_destroyed(mech):
        return None
    info = _info(label)
    if info is None:
        return None
    why = why or (f"landed in {label}" if jumped else f"entered {label}")
    state = magma_state(info["features"])
    if state == MAGMA_CRUST:
        roll = _d6("Magma crust (1D6)")
        if roll >= (CRUST_BREAKS_JUMP if jumped else CRUST_BREAKS_GROUND):
            info["features"]["magma"] = [MAGMA_LIQUID]
            _BROKEN.append(info)
            state = MAGMA_LIQUID
            config.log(f"    {mech.side_name}: the magma crust at {label} breaks (1D6 {roll}) - liquid magma "
                       f"for the rest of the battle (TO:AR p.34).")
    if state is not None:
        mech.__dict__.setdefault("magma_entered", []).append((label, state))
    if state == MAGMA_LIQUID:
        magma_burn(mech, why)
        if not is_destroyed(mech) and not mech.prone and not is_stuck(mech):
            if bog_down_roll(mech, label, "entering liquid magma"):
                return "stuck"
    if "hazardous_liquid" in info["features"]:
        pool_damage(mech, why)
    return None


def bog_down_roll(mech, label, what) -> bool:
    """The Piloting roll on entering a bog hex (p.60), at the hex's
    modifier (liquid magma +4). True = stuck (it doesn't fall)."""
    import piloting_rolls
    from INTEGRATION__attack_resolution import _with_piloting
    modifier = (piloting_rolls.preexisting_modifier(mech) + piloting_rolls.special_case_modifier(mech)
                + psr_modifier(label))

    def roll(m):
        return piloting_rolls.roll_psrs(m, 1, modifier, f"[Movement] {m.side_name}: bog-down roll, {what} at {label}")
    if _with_piloting(mech, roll):
        return False
    mech.stuck = {"rolls": 1, "prone_stage": False, "by_jump": mech.move_mode == "Jump"}
    config.log(f"    {mech.side_name} is STUCK in {label} (bogged down, TO:AR p.60): no more movement this turn.")
    return True


def after_fall(mech):
    """A 'Mech fell (piloting_rolls.resolve_fall): in liquid magma every
    location is exposed (p.35, the p.36 example), and a fall in a bog hex
    sticks it automatically - three rolls to get free (p.61)."""
    if is_destroyed(mech) or magma_at(mech.hex) != MAGMA_LIQUID:
        return
    magma_burn(mech, f"fell in liquid magma at {mech.hex}")
    if not is_destroyed(mech):
        mech.stuck = {"rolls": 1, "prone_stage": True, "by_jump": False}
        config.log(f"    {mech.side_name} fell in liquid magma - STUCK (TO:AR p.61: free the prone 'Mech, "
                   f"stand, then free it from the hex).")


# =============================================================================
# ==========================  MOVEMENT PHASE  =================================
# =============================================================================
def start_of_movement(mech) -> None:
    """Start of the 'Mech's Movement Phase: liquid magma and pools hurt a
    'Mech that begins it in them (pp.35, 47); a stuck 'Mech tries to get
    free (p.60). Records where it started for the start-and-end rule."""
    mech.magma_entered = []
    mech.started_in_liquid = magma_at(mech.hex) == MAGMA_LIQUID
    if mech.hex is None or is_destroyed(mech):
        return
    if mech.started_in_liquid:
        magma_burn(mech, f"starts its Movement Phase in liquid magma at {mech.hex}")
    if pool_at(mech.hex) and not is_destroyed(mech):
        pool_damage(mech, f"starts its Movement Phase in a hazardous liquid pool at {mech.hex}")
    if is_stuck(mech) and not is_destroyed(mech):
        free_roll(mech)


def free_roll(mech):
    """The roll to break free (p.60), at the hex's modifier. A 'Mech stuck
    after a fall first frees itself from the stuck prone position; it then
    stands as normal and still needs one more roll, next Movement Phase."""
    import piloting_rolls
    from INTEGRATION__attack_resolution import _with_piloting
    stuck = mech.stuck
    if stuck["prone_stage"] and not mech.prone:
        stuck["prone_stage"] = False         # it stood up some other way: only the last roll is left
    modifier = (piloting_rolls.preexisting_modifier(mech) + piloting_rolls.special_case_modifier(mech)
                + psr_modifier(mech.hex))
    what = "free itself from the stuck prone position" if stuck["prone_stage"] else "break free"

    def roll(m):
        return piloting_rolls.roll_psrs(m, 1, modifier, f"[Movement] {m.side_name}: roll to {what} at {m.hex}")
    if not _with_piloting(mech, roll):
        config.log(f"    {mech.side_name} stays stuck at {mech.hex} (TO:AR p.60; no fall).")
        return
    if stuck["prone_stage"]:
        stuck["prone_stage"] = False
        stuck["stand_only"] = True           # may now try to stand, but stays in the hex this turn
        config.log(f"    {mech.side_name} frees itself from the stuck prone position - it may stand, "
                   f"then must still break free next turn.")
        return
    mech.stuck = None
    config.log(f"    {mech.side_name} breaks free at {mech.hex}.")


def can_ground_move(mech) -> bool:
    """A stuck 'Mech may not move along the ground (or turn) this turn."""
    return not is_stuck(mech)


def can_jump_out(mech) -> bool:
    """p.60: stuck after non-jumping movement - it may jump out instead."""
    stuck = getattr(mech, "stuck", None)
    return bool(stuck) and not stuck.get("by_jump") and not stuck.get("prone_stage") and not mech.prone


def end_of_movement(mech) -> None:
    """Started AND ended the Movement Phase in liquid magma: another 2D6 to
    each exposed location (p.35). A jump out of a bog frees the 'Mech."""
    if mech.hex is None or is_destroyed(mech):
        return
    stuck = getattr(mech, "stuck", None)
    if stuck and stuck.get("stand_only") and not mech.prone:
        stuck.pop("stand_only")              # stood up: the last roll comes next Movement Phase
    if getattr(mech, "started_in_liquid", False) and magma_at(mech.hex) == MAGMA_LIQUID:
        magma_burn(mech, f"starts and ends its Movement Phase in liquid magma ({mech.hex})")


def jumped_out(mech):
    """A stuck 'Mech jumped: it is free (p.60)."""
    if is_stuck(mech) and mech.move_mode == "Jump":
        mech.stuck = None
        config.log(f"    {mech.side_name} jumps clear of the bog.")


# =============================================================================
# ==========================  HEAT PHASE  =====================================
# =============================================================================
def magma_heat(mech) -> int:
    """This turn's magma heat (p.35): each magma hex entered but not
    occupied now, plus the hex occupied now. Not held to the outside heat
    cap (INTEGRATION__heat adds it after the cap)."""
    if is_destroyed(mech) or mech.hex is None:
        return 0
    here = magma_at(mech.hex)
    total = sum(MAGMA_HEAT_ENTERED[state] for label, state in getattr(mech, "magma_entered", [])
                if label != mech.hex)
    if here is not None:
        total += MAGMA_HEAT_OCCUPIED[here]
    mech.magma_entered = []
    return total


# =============================================================================
# ==========================  MOVEMENT SCORING  ===============================
# =============================================================================
def stay_damage(mech, label) -> float:
    """Expected damage of STARTING next turn's Movement Phase in `label`
    (pp.35, 47) - priced by movement scoring for the hex a move ends in."""
    info = _info(label)
    if info is None:
        return 0.0
    return terrain_rules.step_hazard(info, legs=len(mech.leg_locations))
