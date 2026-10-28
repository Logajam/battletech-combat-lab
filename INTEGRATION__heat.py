"""
INTEGRATION__heat.py  (NEW 2026-10-18, Claude - Pile 2; Heat Scale effects added 2026-10-19;
                       heat equipment added 2026-10-19)

Every heat rule the battle loop uses, shared by movement scoring
(INTEGRATION__ranged_combat), Ranged Combat (INTEGRATION__attack_resolution)
and the turn loop (INTEGRATION__orchestrator). Kept out of the orchestrator
so ranged_combat can use them without a circular import. The equipment
behind several of these (stealth, coolant pods, radical heat sinks, TSM,
torso cockpit) is found and tracked by INTEGRATION__equipment_systems.

Source: BattleTech Core Rulebook, Heat chapter, pp.102-107, plus the
equipment entries it points to (Daniel's rules index, base/core-rules/;
errata v0.1 has no heat entries). Page numbers are cited next to each rule.
Daniel's own calls are marked "Daniel".

  - Movement heat (p.102): Stand Still 0, Walk 1, Run 2, Jump 1 per hex
    (min 3); Improved Jump Jets 1 per 2 hexes or part (min 3).
    XXL engine: Stand Still 2 / Walk 4 / Run 6, jump heat doubled (min 6);
    Improved JJ + XXL cancel out (1 per hex, min 3).
    Super-cooled myomer: no heat from ground movement; jumping normal.
    Destroyed radical heat sink system: +1 whenever the mech moves (p.209).
  - Engine critical hits (p.102): +5 per turn for the first hit, +10 total
    for the second. None while shut down. Daniel (2026-10-19): a hit taken
    this turn is charged in this turn's Heat Phase; from then on the mech
    knows it's coming and budgets its weapons around it.
  - Stealth systems (p.102): LPS 6, Null-Signature 10, stealth armor 10,
    Void-Signature 10 heat per turn while active (never while shut down).
  - Weapon heat budget per turn (Daniel) = max_heat + dissipation
    - current heat - movement heat - other heat (floored at 0), where other
    heat = engine + stealth (+1 if a destroyed radical system will add
    weapon heat) - this turn's planned radical cooling. max_heat caps the
    end-of-turn heat level. min_heat (Daniel, 2026-10-19) is the matching
    floor: the mech pads its fire to end the turn at min_heat or more.
  - Heat is saved state: current_heat carries over turn to turn (Daniel).

THE HEAT PHASE (resolve_heat_phase, pp.103-107), in the book's order:
  1. Adjust the Heat Scale: + movement + weapons + engine + stealth
     - dissipation - extra cooling, floor 0 (p.103). Heat above 30 is
     Overflow - kept, not capped. Extra cooling (start of the phase, p.208):
     the radical heat sink system on its cycle-on turn (Escalating Failure;
     +1 per working heat sink), otherwise one coolant pod if heat would
     still be above min_heat (+1 per active heat sink). Neither works while
     shut down (p.104: activated equipment is off).
  2. Shutdown effects first (p.104 "Heat Effect Order"):
       running mech at 14+: one 2D6 roll vs the highest Shutdown Avoid
       number reached (14: 4+, 18: 6+, 22: 8+, 26: 10+); automatic at 30+;
       only a conscious MechWarrior can override (p.104).
       mech shut down BEFORE this phase: restart attempt instead (p.105) -
       automatic below 14 (even if unconscious); otherwise a conscious
       MechWarrior rolls 2D6 vs the highest Shutdown Avoid number; never
       at 30+ (must be below 30 to restart).
  3. Ammunition effects (p.107): 19+ heat with live explosive ammo bins:
     one 2D6 roll vs the highest Ammo Avoid number (19: 4+, 23: 6+, 28: 8+);
     on a failure the bin with the most destructive ammo per shot explodes
     (internal explosion, p.95: MechWarrior takes 1 hit + consciousness roll).
     Gauss-type explosive components and one-shot weapons never explode
     from heat - only ammo bins are candidates.
     Inferno ammo (pp.107, 192) rolls its own set on the Inferno Ammo
     Explosion Table (10: 4+, 14: 6+, 19: 8+, 23: 10+, 28: 12); the normal
     roll then only covers the other bins. An exploding inferno bin adds 2
     heat per missile (max 30) at once; if that crosses a new shutdown,
     ammo or inferno threshold, those rolls are made again straight away.
  4. MechWarrior hits from a life support critical (p.107), resolved last:
     1 hit at heat 10-19, 2 hits at 20+ (torso-mounted cockpit, p.203:
     1 hit at 1-14, 2 at 15+).
  5. Set the effects that apply NEXT turn (p.103: "Other than ammo
     explosions, these effects begin at the start of the following turn"):
     Walking MP penalty (5: -1, 10: -2, 15: -3, 20: -4, 25: -5; Running MP
     recalculated, Jumping MP unaffected - p.104), ranged to-hit modifier
     (8: +1, 13: +2, 17: +3, 24: +4; ranged only - p.104), and triple-
     strength myomer (9+: +2 Walking MP, p.205). Stored on the mech as
     heat_mp_penalty / heat_fire_modifier / tsm_active.
  Only the highest effect of each type applies (p.104).

END PHASE (choose_heat_sink_deactivation, p.103; Daniel 2026-10-19): a mech
with min_heat > 0 switches off the heat sinks it doesn't need to reach
min_heat, judged on its most heat next turn (all weapons + its hottest
movement + engine/stealth). Switched-off sinks dissipate nothing until
switched back on in a later End Phase.

WHAT A SHUT-DOWN MECH DOES (p.104-105): immobile (skips movement; attacks
against it get the -4 immobile modifier and may be aimed shots), can't
attack, any PSR it must make while standing fails automatically, generates
no engine, weapon or stealth heat; heat sinks keep working. It can move and
fire the turn after it restarts.

Not modeled (the sim has no such terrain or decision yet - see
results.KNOWN_MISSING_RULES): snow/fire/extreme temperatures (water's
submerged heat sinks: INTEGRATION__water, 2026-10-21),
inferno missiles' heat on targets (launchers fire standard ammo),
voluntary shutdown.
"""

import math

import INTEGRATION__config as config
import INTEGRATION__stubs as stubs
import INTEGRATION__equipment_systems as equip
import INTEGRATION__ammo as ammo
import INTEGRATION__water as water
import INTEGRATION__hazards as hazards
import INTEGRATION__advanced_weapons as adv
from mech_state import pilot_hit  # command console, p.203
from mech_state import compute_heat_dissipation, is_destroyed, pilot_unconscious, \
    mark_consciousness_check_pending, active_heat_sinks, working_heat_sinks, heat_sink_rate, \
    compute_walk_mp, compute_running_mp, compute_jump_mp
from equipment import Equipment, lookup_equipment
from damage_resolution import apply_explosion, get_weapons
import piloting_rolls

# =============================================================================
# ==========================  HEAT TABLES  ====================================
# =============================================================================
# Heat Data Table, Core Rulebook p.103: (heat level, effect) pairs, highest
# first. For each effect type only the highest level reached applies (p.104).
MP_PENALTY_BY_HEAT = ((25, 5), (20, 4), (15, 3), (10, 2), (5, 1))       # Walking MP lost
FIRE_MODIFIER_BY_HEAT = ((24, 4), (17, 3), (13, 2), (8, 1))             # ranged to-hit
SHUTDOWN_AVOID_BY_HEAT = ((26, 10), (22, 8), (18, 6), (14, 4))          # 2D6 to avoid
SHUTDOWN_AUTOMATIC_HEAT = 30                                            # can't avoid (p.104)
RESTART_MAX_HEAT = 29                                                   # must be below 30 (p.105)
AMMO_AVOID_BY_HEAT = ((28, 8), (23, 6), (19, 4))                        # 2D6 to avoid (p.107)
LIFE_SUPPORT_HITS_BY_HEAT = ((20, 2), (10, 1))                          # MechWarrior hits (p.107)
OVERFLOW_HEAT = 30                                                      # Heat Scale top (p.103)
OUTSIDE_HEAT_CAP = 15                                                   # outside heat a turn (p.102)

# Inferno Ammo Explosion Table, p.192 (also p.107). The p.192 text mentions
# rolls "at 19, 23, and 28" but the table starts at 10 - the table is used.
INFERNO_AVOID_BY_HEAT = ((28, 12), (23, 10), (19, 8), (14, 6), (10, 4))
INFERNO_HEAT_PER_MISSILE = 2
INFERNO_MAX_HEAT = 30
# Torso-mounted cockpit with a life support crit (p.203) - replaces the table above.
TORSO_COCKPIT_LIFE_SUPPORT_HITS_BY_HEAT = ((15, 2), (1, 1))

# Heat Point Table, p.102.
ENGINE_HEAT_BY_HITS = {0: 0, 1: 5, 2: 10}
WALK_HEAT = 1
RUN_HEAT = 2
JUMP_MIN_HEAT = 3
XXL_MOVE_HEAT = {"Stand Still": 2, "Walk": 4, "Run": 6}
XXL_JUMP_MIN_HEAT = 6
RADICAL_DESTROYED_EXTRA_HEAT = 1   # per turn moving, and per turn firing (p.209)


def _highest(table, level, default=0):
    """Value for the highest threshold in `table` that `level` reaches."""
    for threshold, value in table:
        if level >= threshold:
            return value
    return default


# Thresholds at which a new avoid roll is owed (highest first) - used to
# decide whether inferno heat crossed a NEW threshold (p.107).
SHUTDOWN_THRESHOLDS = (30, 26, 22, 18, 14)
AMMO_THRESHOLDS = tuple(t for t, _ in AMMO_AVOID_BY_HEAT)
INFERNO_THRESHOLDS = tuple(t for t, _ in INFERNO_AVOID_BY_HEAT)


def _threshold_reached(thresholds, level):
    """The highest of `thresholds` that `level` reaches, or 0."""
    return next((t for t in thresholds if level >= t), 0)


def mp_penalty_for(level):
    return _highest(MP_PENALTY_BY_HEAT, level)


def fire_modifier_for(level):
    return _highest(FIRE_MODIFIER_BY_HEAT, level)


def shutdown_avoid_tn(level):
    """2D6 target to avoid shutdown / to restart, or None below 14."""
    return _highest(SHUTDOWN_AVOID_BY_HEAT, level, None)


def ammo_avoid_tn(level):
    """2D6 target to avoid an ammo explosion, or None below 19."""
    return _highest(AMMO_AVOID_BY_HEAT, level, None)


def inferno_avoid_tn(level):
    """2D6 target to avoid an inferno ammo explosion, or None below 10."""
    return _highest(INFERNO_AVOID_BY_HEAT, level, None)


# =============================================================================
# ==========================  MECH HEAT TRAITS  ==============================
# =============================================================================
def has_improved_jump_jets(mech):
    """True if any crit slot (live or already destroyed) is an Improved Jump
    Jet. Checks bare strings too: with the mini equipment DB, 'IS Improved
    Jump Jet' isn't in equipment.json, so the parser leaves it as a plain
    string instead of an Equipment instance."""
    def is_ijj(name):
        return "IMPROVEDJUMPJET" in name.replace(" ", "").replace("-", "").upper()
    for slots in mech.crits.values():
        for s in slots:
            name = s if isinstance(s, str) else getattr(s, "name", "")
            if is_ijj(name):
                return True
    return any(is_ijj(info["name"]) for info in mech.destroyed_slot_info.values())


def has_xxl_engine(mech):
    """From the .mtf "Engine:" header (e.g. "300 XXL Engine(IS)")."""
    return "XXL" in (getattr(mech, "engine_desc", "") or "").upper()


def has_supercooled_myomer(mech):
    """From the .mtf "Myomer:" header (e.g. "Super-Cooled")."""
    return "SUPERCOOLED" in (getattr(mech, "myomer", "") or "").replace(" ", "").replace("-", "").upper()


def _trait(mech, attr, detect):
    """Cached per mech: the orchestrator sets these once per battle
    (_attach_mech_config); fall back to detecting if it hasn't."""
    flag = getattr(mech, attr, None)
    if flag is None:
        flag = detect(mech)
        setattr(mech, attr, flag)
    return flag


def attach_heat_traits(mech):
    """Called once per battle per mech by the orchestrator."""
    mech.has_improved_jump_jets = has_improved_jump_jets(mech)
    mech.has_xxl_engine = has_xxl_engine(mech)
    mech.has_supercooled_myomer = has_supercooled_myomer(mech)
    equip.attach_equipment(mech)


def improved_jump_jets(mech):
    return _trait(mech, "has_improved_jump_jets", has_improved_jump_jets)


def _radical_destroyed(mech):
    """equip.radical_destroyed, tolerating a bare test object with no equipment table."""
    return hasattr(mech, "equipment_systems") and equip.radical_destroyed(mech)


# =============================================================================
# ==========================  HEAT GENERATED  ================================
# =============================================================================
def movement_heat(mech, mode, hexes_moved):
    """Heat generated by one turn's movement (p.102). hexes_moved for a jump
    is the straight-line hexes jumped (the jump's forward count from
    combat.build_jump_states)."""
    extra = RADICAL_DESTROYED_EXTRA_HEAT if mode != "Stand Still" and _radical_destroyed(mech) else 0
    ijj = improved_jump_jets(mech)
    xxl = _trait(mech, "has_xxl_engine", has_xxl_engine)
    if mode == "Jump":
        if xxl and not ijj:
            return extra + max(XXL_JUMP_MIN_HEAT, 2 * hexes_moved)
        if ijj and not xxl:
            return extra + max(JUMP_MIN_HEAT, math.ceil(hexes_moved / 2))
        return extra + max(JUMP_MIN_HEAT, hexes_moved)  # standard jets, or IJJ + XXL cancelling out
    if _trait(mech, "has_supercooled_myomer", has_supercooled_myomer):
        return extra  # no heat from ground movement, standing still included
    if xxl:
        return extra + XXL_MOVE_HEAT[mode]
    return extra + {"Walk": WALK_HEAT, "Run": RUN_HEAT}.get(mode, 0)  # Stand Still 0


def engine_heat(mech):
    """Heat from engine critical hits this turn (p.102): 5 for one hit, 10
    total for two (a third destroys the mech). None while shut down (p.104)."""
    if mech.shutdown:
        return 0
    return ENGINE_HEAT_BY_HITS[min(mech.engine_hits, 2)]


def weapon_fire_surcharge(mech):
    """+1 to a turn's weapon heat if any weapon fires with a destroyed radical
    heat sink system (p.209)."""
    return RADICAL_DESTROYED_EXTRA_HEAT if _radical_destroyed(mech) else 0


def planned_cooling(mech):
    """Extra cooling the mech counts on this turn: the radical system on its
    cycle-on turn, +1 per working heat sink. (Coolant pods are used only when
    needed, so they are not counted on in advance.)"""
    return active_heat_sinks(mech) if equip.radical_planned(mech) else 0


def other_heat(mech):
    """Heat this turn besides movement and weapons, net of planned extra
    cooling: engine + stealth + the destroyed-radical weapon surcharge
    - planned radical cooling. Can be negative."""
    return engine_heat(mech) + equip.stealth_heat(mech) + weapon_fire_surcharge(mech) - planned_cooling(mech)


def weapon_heat_budget(mech, move_heat):
    """max_heat + dissipation - current heat - movement heat - other heat,
    floored at 0. Same formula weapon_selection.select_weapons_to_fire
    applies internally; exposed here for logging."""
    return max(0, mech.max_heat + compute_heat_dissipation(mech) + water.dissipation_bonus(mech)
               - mech.current_heat - move_heat - other_heat(mech))


# =============================================================================
# ==========================  HEAT PHASE  =====================================
# =============================================================================
def resolve_heat_phase(mech, weapon_heat):
    """One mech's Heat Phase - steps 1-5 in the module docstring. weapon_heat
    already includes any destroyed-radical surcharge (added when it fired)."""
    name = mech.side_name
    was_shut_down = mech.shutdown
    eng = engine_heat(mech)
    stealth = equip.stealth_heat(mech)
    sinks = compute_heat_dissipation(mech)
    water_bonus = water.dissipation_bonus(mech)     # submerged sinks dissipate double (p.103, 2026-10-21)
    dissipation = sinks + water_bonus
    before = mech.current_heat
    # Outside heat (2026-10-20, p.102): hits by heat-causing weapons this turn, at most 15.
    outside = min(OUTSIDE_HEAT_CAP, getattr(mech, "outside_heat", 0))
    mech.outside_heat = 0
    cap = getattr(mech, "capacitor_heat", 0)        # PPC capacitors charging / held (p.188, 2026-10-21)
    mech.capacitor_heat = 0
    magma = hazards.magma_heat(mech)                # magma: added AFTER the outside cap (TO:AR p.35, 2026-10-27)
    taser = adv.taser_heat(mech)                    # Taser interference: 5 a turn (TO:AUE p.158, 2026-10-27)
    generated = mech.movement_heat + weapon_heat + eng + stealth + outside + cap + magma + taser
    extra, how = _extra_cooling(mech, before + generated - dissipation)
    mech.current_heat = max(0, before + generated - dissipation - extra)
    overflow = mech.current_heat - OVERFLOW_HEAT
    config.log(f"  [Heat] {name}: {before} + movement {mech.movement_heat} + weapons {weapon_heat} "
               f"+ engine {eng}{f' + stealth {stealth}' if stealth else ''}{f' + outside {outside}' if outside else ''}"
               f"{f' + capacitors {cap}' if cap else ''}{f' + magma {magma}' if magma else ''}{f' + Taser {taser}' if taser else ''}"
               f" - sinks {sinks}{f' - water {water_bonus}' if water_bonus else ''}"
               f"{f' - {how} {extra}' if how else ''} -> {mech.current_heat}"
               f"{f' (overflow {overflow})' if overflow > 0 else ''}")

    _overheat_checks(mech, was_shut_down)
    if is_destroyed(mech):
        return

    _life_support_hits(mech)
    if is_destroyed(mech):
        return
    piloting_rolls.resolve_consciousness_checks(mech, "Heat Phase (life support)")

    apply_heat_effects(mech)


def _extra_cooling(mech, projected):
    """Step 1's extra cooling: (points, label). `projected` is the heat
    level after normal dissipation."""
    if mech.shutdown:
        return 0, ""
    if equip.radical_planned(mech, warn=True):
        if equip.escalating_roll(mech, "radical", "Radical heat sink system"):
            return active_heat_sinks(mech), "radical heat sinks"
        equip.destroy_system(mech, "radical", "failed activation")
        return 0, ""
    if projected > mech.min_heat and equip.unused_coolant_pods(mech):
        pod = equip.use_coolant_pod(mech)
        config.log(f"    {mech.side_name}: {pod.name} triggered.")
        return active_heat_sinks(mech), "coolant pod"
    return 0, ""


def apply_heat_effects(mech):
    """Step 5: MP, to-hit and TSM effects for the coming turn, off the
    current Heat Scale level."""
    mech.heat_mp_penalty = mp_penalty_for(mech.current_heat)
    mech.heat_fire_modifier = fire_modifier_for(mech.current_heat)
    mech.tsm_active = getattr(mech, "has_tsm", False) and equip.tsm_active_for(mech, mech.current_heat)
    if mech.heat_mp_penalty or mech.heat_fire_modifier or mech.tsm_active:
        config.log(f"  [Heat] {mech.side_name}: heat {mech.current_heat} -> next turn "
                   f"-{mech.heat_mp_penalty} Walking MP, +{mech.heat_fire_modifier} to ranged attacks"
                   f"{', TSM active (+2 Walking MP)' if mech.tsm_active else ''}.")


# --- Steps 2-3 with re-checks after inferno heat (p.107) ----------------------
def _overheat_checks(mech, was_shut_down):
    if was_shut_down:
        _try_restart(mech)
    else:
        _check_shutdown(mech)
    done = {"shutdown": _threshold_reached(SHUTDOWN_THRESHOLDS, mech.current_heat), "ammo": 0, "inferno": 0}
    inferno_blew = _ammo_step(mech, done)
    while inferno_blew and not is_destroyed(mech):
        level = mech.current_heat
        reached = _threshold_reached(SHUTDOWN_THRESHOLDS, level)
        if not mech.shutdown and reached > done["shutdown"]:
            config.log(f"  [Heat] {mech.side_name}: inferno heat crossed a new shutdown threshold - rolling again.")
            _check_shutdown(mech)
        done["shutdown"] = max(done["shutdown"], reached)
        inferno_blew = _ammo_step(mech, done)


def _ammo_step(mech, done):
    """Normal and inferno ammo rolls for every threshold not yet rolled for.
    True if an inferno bin exploded (heat went up - re-check)."""
    level = mech.current_heat
    if _threshold_reached(AMMO_THRESHOLDS, level) > done["ammo"]:
        done["ammo"] = _threshold_reached(AMMO_THRESHOLDS, level)
        _check_ammo_explosion(mech, inferno=False)
        if is_destroyed(mech):
            return False
        piloting_rolls.resolve_consciousness_checks(mech, "Heat Phase (ammo explosion)")
    if _threshold_reached(INFERNO_THRESHOLDS, level) > done["inferno"]:
        done["inferno"] = _threshold_reached(INFERNO_THRESHOLDS, level)
        blew = _check_ammo_explosion(mech, inferno=True)
        if is_destroyed(mech):
            return False
        piloting_rolls.resolve_consciousness_checks(mech, "Heat Phase (inferno explosion)")
        return blew
    return False


def _check_shutdown(mech):
    level = mech.current_heat
    name = mech.side_name
    if level >= SHUTDOWN_AUTOMATIC_HEAT:
        _shut_down(mech, f"heat {level} (30+: automatic)")
        return
    tn = shutdown_avoid_tn(level)
    if tn is None:
        return
    if pilot_unconscious(mech):
        _shut_down(mech, f"heat {level}, MechWarrior unconscious - can't override")
        return
    roll = config.roll_2d6(prompt="Shutdown avoid roll")
    if roll >= tn:
        config.log(f"  [Heat] {name}: shutdown avoid roll at heat {level}: needs {tn}, rolled {roll} - avoided.")
    else:
        _shut_down(mech, f"heat {level}, shutdown avoid roll needs {tn}, rolled {roll}")


def _shut_down(mech, why):
    mech.shutdown = True
    config.log(f"  [Heat] {mech.side_name}: SHUT DOWN ({why}).")


def _try_restart(mech):
    level = mech.current_heat
    name = mech.side_name
    if adv.held_down(mech):
        config.log(f"  [Heat] {name}: shut down by a Taser - no restart before the effect ends (TO:AUE p.158).")
        return
    tn = shutdown_avoid_tn(level)
    if tn is None:
        mech.shutdown = False
        config.log(f"  [Heat] {name}: heat {level} is below 14 - power plant restarts automatically.")
        return
    if level > RESTART_MAX_HEAT:
        config.log(f"  [Heat] {name}: heat {level} - must be below 30 to restart; stays shut down.")
        return
    if pilot_unconscious(mech):
        config.log(f"  [Heat] {name}: MechWarrior unconscious - no restart attempt at heat {level}; stays shut down.")
        return
    roll = config.roll_2d6(prompt="Restart roll")
    if roll >= tn:
        mech.shutdown = False
        config.log(f"  [Heat] {name}: restart roll at heat {level}: needs {tn}, rolled {roll} - RESTARTED.")
    else:
        config.log(f"  [Heat] {name}: restart roll at heat {level}: needs {tn}, rolled {roll} - stays shut down.")


# --- Ammunition (p.107) -------------------------------------------------------
def is_inferno_bin(bin_):
    return "INFERNO" in bin_.name.upper()


def live_ammo_bins(mech, inferno=None):
    """[(location, bin)] for every explosive ammo bin that hasn't exploded or
    been destroyed; an empty bin isn't explosive (INTEGRATION__ammo). Only
    ammo bins: explosive components such as Gauss rifles, and
    one-shot weapons, never explode from heat (p.107). inferno=True/False
    keeps only inferno / non-inferno bins; None keeps both."""
    destroyed_ids = {info["instance_id"] for info in mech.destroyed_slot_info.values()
                     if info["instance_id"] is not None}
    seen = set()
    bins = []
    for location, slots in mech.crits.items():
        for slot in slots:
            if (isinstance(slot, Equipment) and slot.category == "ammo" and slot.is_explosive
                    and not slot.exploded and id(slot) not in seen and id(slot) not in destroyed_ids):
                seen.add(id(slot))
                if inferno is None or is_inferno_bin(slot) == inferno:
                    bins.append((location, slot))
    return bins


def ammo_bin_damage_value(bin_):
    """Damage Value of one turn's worth of shots from this bin (p.107): a
    missile launcher's rack size x damage per missile (LRM 15 -> 15, SRM 6
    -> 12), otherwise the weapon's damage (AC/5 -> 5; Rapid-Fire weapons
    count one shot). None if the bin's weapon or its damage is unknown."""
    return ammo.damage_per_shot(ammo.weapon_entry_for_ammo(bin_.name))


def choose_exploding_bin(mech, bins):
    """The bin with the most destructive ammo per shot explodes (p.107);
    ties go to the bin with the most shots left (INTEGRATION__ammo), then
    the controller's choice (stubs.stub_heat_explosion_bin)."""
    scored = []
    unknown = []
    for location, b in bins:
        dv = ammo_bin_damage_value(b)
        if dv is None:
            unknown.append(b.name)
            dv = 0
        shots = getattr(b, "shots_left", None)
        scored.append((dv, float("inf") if shots is None else shots, location, b))
    best = max((dv, shots) for dv, shots, _, _ in scored)
    tied = [(location, b) for dv, shots, location, b in scored if (dv, shots) == best]
    if unknown or len(tied) > 1:
        return stubs.stub_heat_explosion_bin(mech.side_name, tied, best[0], unknown)
    return tied[0]


def _check_ammo_explosion(mech, inferno):
    """One avoid roll for the normal (or inferno) bins at the current heat.
    Returns True if an inferno bin exploded."""
    level = mech.current_heat
    tn = inferno_avoid_tn(level) if inferno else ammo_avoid_tn(level)
    if tn is None:
        return False
    bins = live_ammo_bins(mech, inferno=inferno)
    if not bins:
        return False
    name = mech.side_name
    kind = "inferno ammo" if inferno else "ammo"
    roll = config.roll_2d6(prompt=f"{kind} explosion avoid roll")
    if roll >= tn:
        config.log(f"  [Heat] {name}: {kind} explosion avoid roll at heat {level}: needs {tn}, "
                   f"rolled {roll} - avoided.")
        return False
    location, bin_ = choose_exploding_bin(mech, bins)
    config.log(f"  [Heat] {name}: {kind} explosion avoid roll at heat {level}: needs {tn}, rolled {roll} - "
               f"{bin_.name} in {location} EXPLODES.")
    _destroy_bin_slots(mech, bin_)
    bin_.exploded = True
    apply_explosion(mech, bin_, location)
    if not inferno:
        return False
    # 2 heat per missile left in the bin, max 30 (p.192).
    burn = ammo.inferno_heat(bin_)
    mech.current_heat += burn
    config.log(f"  [Heat] {name}: inferno ammo burns - +{burn} heat at once -> {mech.current_heat}.")
    return True


def _destroy_bin_slots(mech, bin_):
    """The exploded bin's crit slots are gone - recorded the same way
    damage_resolution.resolve_slot_hit records a destroyed slot."""
    for location, slots in mech.crits.items():
        for i, slot in enumerate(slots):
            if slot is bin_:
                mech.destroyed_slot_info[(location, i)] = {"name": bin_.name, "instance_id": id(bin_)}
                slots[i] = "DESTROYED"


# --- Life support (p.107) -----------------------------------------------------
def has_life_support_hit(mech):
    return any(info["name"] == "Life Support" for info in mech.destroyed_slot_info.values())


def _life_support_hits(mech):
    if not has_life_support_hit(mech):
        return
    table = TORSO_COCKPIT_LIFE_SUPPORT_HITS_BY_HEAT if getattr(mech, "torso_cockpit", False) \
        else LIFE_SUPPORT_HITS_BY_HEAT
    hits = _highest(table, mech.current_heat)
    if not hits:
        return
    pilot_hit(mech, hits, head=True)          # heat hurts a command console's second warrior too (p.203)
    config.log(f"  [Heat] {mech.side_name}: life support destroyed"
               f"{' (torso-mounted cockpit)' if getattr(mech, 'torso_cockpit', False) else ''}, "
               f"heat {mech.current_heat} - MechWarrior takes {hits} hit(s) ({mech.pilot_hits}/6).")
    is_destroyed(mech)


# =============================================================================
# ==========================  END PHASE: HEAT SINKS  ==========================
# =============================================================================
def max_movement_heat(mech):
    """The most heat next turn's movement could make: running (or walking,
    standing) on the ground, or a full-length jump."""
    if compute_running_mp(mech) > 0:
        best = movement_heat(mech, "Run", compute_running_mp(mech))
    elif compute_walk_mp(mech) > 0:
        best = movement_heat(mech, "Walk", compute_walk_mp(mech))
    else:
        best = movement_heat(mech, "Stand Still", 0)
    jump = compute_jump_mp(mech)
    if jump > 0:
        best = max(best, movement_heat(mech, "Jump", jump))
    return best


def max_weapon_heat(mech):
    """Heat of every weapon that could fire next turn (ammo permitting; an
    Ultra / Rotary AC at its full rate of fire, 2026-10-20)."""
    import INTEGRATION__fire_modes as fire_modes      # fire_modes -> ams -> heat
    out = ammo.unavailable_weapons(mech)
    import INTEGRATION__weapon_profiles as wp
    return sum((w.heat or 0) * fire_modes.max_shots(w) + (max(h for _, _, h in wp.BOMBAST.values()) if wp.is_bombast(w) else 0)
               for w in get_weapons(mech) if id(w) not in out)


def choose_heat_sink_deactivation(mech, next_turn):
    """End Phase (p.103; Daniel 2026-10-19): with min_heat > 0, keep only as
    many heat sinks on as the mech can afford while still being able to end
    next turn at min_heat - judged on its MOST heat next turn: current heat
    + every weapon + its hottest movement + engine + stealth (+ a destroyed
    radical's +1). Everything else is switched off. min_heat 0 switches
    every working sink back on."""
    working = working_heat_sinks(mech)
    if mech.min_heat <= 0 or is_destroyed(mech):
        wanted_off = 0
    else:
        weapons = max_weapon_heat(mech)
        potential = (mech.current_heat + max_movement_heat(mech) + weapons + ENGINE_HEAT_BY_HITS[min(mech.engine_hits, 2)]
                     + sum(equip.STEALTH_HEAT[k] for k in _stealth_next_turn(mech))
                     + (weapon_fire_surcharge(mech) if weapons else 0))
        fixed_cooling = 3 if mech.partial_wing_active else 0
        per_sink = heat_sink_rate(mech) + (1 if equip.radical_planned(mech, next_turn) else 0)
        keep_on = max(0, min(working, (potential - mech.min_heat - fixed_cooling) // per_sink))
        wanted_off = working - keep_on
    if wanted_off != mech.deactivated_heat_sinks:
        config.log(f"  [End] {mech.side_name}: heat sinks switched off {mech.deactivated_heat_sinks} -> "
                   f"{wanted_off} of {working} (min_heat {mech.min_heat}).")
    mech.deactivated_heat_sinks = wanted_off


def _stealth_next_turn(mech):
    """Stealth systems that will run next turn (as if not shut down)."""
    saved, mech.shutdown = mech.shutdown, False
    try:
        return equip.active_stealth(mech)
    finally:
        mech.shutdown = saved
