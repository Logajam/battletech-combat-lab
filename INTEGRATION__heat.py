"""
INTEGRATION__heat.py  (NEW 2026-10-18, Claude - Pile 2; Heat Scale effects added 2026-10-19)

Every heat rule the battle loop uses, shared by movement scoring
(INTEGRATION__ranged_combat), Ranged Combat (INTEGRATION__attack_resolution)
and the turn loop (INTEGRATION__orchestrator). Kept out of the orchestrator
so ranged_combat can use them without a circular import.

Source: BattleTech Core Rulebook, Heat chapter, pp.102-107 (Daniel's rules
index, base/core-rules/heat.md; errata v0.1 has no heat entries). Page
numbers are cited next to each rule. Daniel's own calls (2026-10-18) are
marked "Daniel".

  - Movement heat (p.102): Stand Still 0, Walk 1, Run 2, Jump 1 per hex
    (min 3); Improved Jump Jets 1 per 2 hexes or part (min 3).
    XXL engine: Stand Still 2 / Walk 4 / Run 6, jump heat doubled (min 6);
    Improved JJ + XXL cancel out (1 per hex, min 3).
    Super-cooled myomer: no heat from ground movement; jumping normal.
  - Engine critical hits (p.102): +5 per turn for the first hit, +10 total
    for the second. None while shut down.
  - Weapon heat budget per turn (Daniel) = max_heat + dissipation - current
    heat - movement heat - engine heat (floored at 0): max_heat caps the
    end-of-turn heat level, so heat the mech will generate anyway (engine
    hits) comes out of the weapon budget too.
  - Heat is saved state: current_heat carries over turn to turn (Daniel).

THE HEAT PHASE (resolve_heat_phase, pp.103-107), in the book's order:
  1. Adjust the Heat Scale: + movement + weapons + engine - dissipation,
     floor 0 (p.103). Heat above 30 is Overflow - kept, not capped.
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
  4. MechWarrior hits from a life support critical (p.107), resolved last:
     1 hit at heat 10-19, 2 hits at 20+.
  5. Set the effects that apply NEXT turn (p.103: "Other than ammo
     explosions, these effects begin at the start of the following turn"):
     Walking MP penalty (5: -1, 10: -2, 15: -3, 20: -4, 25: -5; Running MP
     recalculated, Jumping MP unaffected - p.104) and ranged to-hit
     modifier (8: +1, 13: +2, 17: +3, 24: +4; ranged only - p.104). Stored
     on the mech as heat_mp_penalty / heat_fire_modifier; read by
     mech_state.compute_walk_mp and the to-hit sums.
  Only the highest effect of each type applies (p.104).

WHAT A SHUT-DOWN MECH DOES (p.104-105): immobile (skips movement; attacks
against it get the -4 immobile modifier), can't attack, any PSR it must
make while standing fails automatically, generates no engine or weapon
heat; heat sinks keep working. It can move and fire the turn after it
restarts.

Not modeled (the sim has no such terrain/equipment/decision yet - see
results.KNOWN_MISSING_RULES): water/snow/fire/extreme temperatures, stealth
systems, coolant pods, radical heat sinks, inferno ammo's extra rolls,
torso-mounted cockpit life support, triple-strength myomer, voluntary
shutdown and heat-sink deactivation (both bot decisions).
"""

import math

import INTEGRATION__config as config
import INTEGRATION__stubs as stubs
from mech_state import compute_heat_dissipation, is_destroyed, pilot_unconscious, \
    mark_consciousness_check_pending
from equipment import Equipment, lookup_equipment
from damage_resolution import apply_explosion
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

# Heat Point Table, p.102.
ENGINE_HEAT_BY_HITS = {0: 0, 1: 5, 2: 10}
WALK_HEAT = 1
RUN_HEAT = 2
JUMP_MIN_HEAT = 3
XXL_MOVE_HEAT = {"Stand Still": 2, "Walk": 4, "Run": 6}
XXL_JUMP_MIN_HEAT = 6


def _highest(table, level, default=0):
    """Value for the highest threshold in `table` that `level` reaches."""
    for threshold, value in table:
        if level >= threshold:
            return value
    return default


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


def improved_jump_jets(mech):
    return _trait(mech, "has_improved_jump_jets", has_improved_jump_jets)


# =============================================================================
# ==========================  HEAT GENERATED  ================================
# =============================================================================
def movement_heat(mech, mode, hexes_moved):
    """Heat generated by one turn's movement (p.102). hexes_moved for a jump
    is the straight-line hexes jumped (the jump's forward count from
    combat.build_jump_states)."""
    ijj = improved_jump_jets(mech)
    xxl = _trait(mech, "has_xxl_engine", has_xxl_engine)
    if mode == "Jump":
        if xxl and not ijj:
            return max(XXL_JUMP_MIN_HEAT, 2 * hexes_moved)
        if ijj and not xxl:
            return max(JUMP_MIN_HEAT, math.ceil(hexes_moved / 2))
        return max(JUMP_MIN_HEAT, hexes_moved)  # standard jets, or IJJ + XXL cancelling out
    if _trait(mech, "has_supercooled_myomer", has_supercooled_myomer):
        return 0  # no heat from ground movement, standing still included
    if xxl:
        return XXL_MOVE_HEAT[mode]
    return {"Walk": WALK_HEAT, "Run": RUN_HEAT}.get(mode, 0)  # Stand Still 0


def engine_heat(mech):
    """Heat from engine critical hits this turn (p.102): 5 for one hit, 10
    total for two (a third destroys the mech). None while shut down (p.104)."""
    if mech.shutdown:
        return 0
    return ENGINE_HEAT_BY_HITS[min(mech.engine_hits, 2)]


def weapon_heat_budget(mech, move_heat):
    """max_heat + dissipation - current heat - movement heat - engine heat,
    floored at 0. Same formula weapon_selection.select_weapons_to_fire
    applies internally; exposed here for logging."""
    return max(0, mech.max_heat + compute_heat_dissipation(mech) - mech.current_heat
               - move_heat - engine_heat(mech))


# =============================================================================
# ==========================  HEAT PHASE  =====================================
# =============================================================================
def resolve_heat_phase(mech, weapon_heat):
    """One mech's Heat Phase - steps 1-5 in the module docstring."""
    name = mech.side_name
    was_shut_down = mech.shutdown
    eng = engine_heat(mech)
    dissipation = compute_heat_dissipation(mech)
    before = mech.current_heat
    mech.current_heat = max(0, before + mech.movement_heat + weapon_heat + eng - dissipation)
    overflow = mech.current_heat - OVERFLOW_HEAT
    config.log(f"  [Heat] {name}: {before} + movement {mech.movement_heat} + weapons {weapon_heat} "
               f"+ engine {eng} - sinks {dissipation} -> {mech.current_heat}"
               f"{f' (overflow {overflow})' if overflow > 0 else ''}")

    if was_shut_down:
        _try_restart(mech)
    else:
        _check_shutdown(mech)

    _check_ammo_explosion(mech)
    if is_destroyed(mech):
        return
    piloting_rolls.resolve_consciousness_checks(mech, "Heat Phase (ammo explosion)")

    _life_support_hits(mech)
    if is_destroyed(mech):
        return
    piloting_rolls.resolve_consciousness_checks(mech, "Heat Phase (life support)")

    apply_heat_effects(mech)


def apply_heat_effects(mech):
    """Step 5: MP and to-hit effects for the coming turn, off the current
    Heat Scale level."""
    mech.heat_mp_penalty = mp_penalty_for(mech.current_heat)
    mech.heat_fire_modifier = fire_modifier_for(mech.current_heat)
    if mech.heat_mp_penalty or mech.heat_fire_modifier:
        config.log(f"  [Heat] {mech.side_name}: heat {mech.current_heat} -> next turn "
                   f"-{mech.heat_mp_penalty} Walking MP, +{mech.heat_fire_modifier} to ranged attacks.")


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
def live_ammo_bins(mech):
    """[(location, bin)] for every explosive ammo bin that hasn't exploded or
    been destroyed. Ammo is unlimited (stubs.stub_ammo), so no bin is ever
    empty. Only ammo bins: explosive components such as Gauss rifles, and
    one-shot weapons, never explode from heat (p.107)."""
    destroyed_ids = {info["instance_id"] for info in mech.destroyed_slot_info.values()
                     if info["instance_id"] is not None}
    seen = set()
    bins = []
    for location, slots in mech.crits.items():
        for slot in slots:
            if (isinstance(slot, Equipment) and slot.category == "ammo" and slot.is_explosive
                    and not slot.exploded and id(slot) not in seen and id(slot) not in destroyed_ids):
                seen.add(id(slot))
                bins.append((location, slot))
    return bins


def _weapon_entry_for_ammo(bin_name):
    """equipment.json entry of the weapon a bin feeds, found by name: drop a
    " - Variant" suffix and the word "Ammo" ("ISLRM15 Ammo" -> "ISLRM15").
    None if the name doesn't resolve to a weapon."""
    base = bin_name.split(" - ")[0]
    base = " ".join(w for w in base.split() if w.lower() != "ammo")
    entry = lookup_equipment(base)
    return entry if entry is not None and entry.get("category") == "weapon" else None


def ammo_bin_damage_value(bin_):
    """Damage Value of one turn's worth of shots from this bin (p.107): a
    missile launcher's rack size x damage per missile (LRM 15 -> 15, SRM 6
    -> 12), otherwise the weapon's damage (AC/5 -> 5; Rapid-Fire weapons
    count one shot). None if the bin's weapon or its damage is unknown."""
    entry = _weapon_entry_for_ammo(bin_.name)
    if entry is None or entry.get("damage_per_shot") is None:
        return None
    if entry.get("damage_type") == "Missile" and entry.get("rack_size"):
        return entry["damage_per_shot"] * entry["rack_size"]
    return entry["damage_per_shot"]


def choose_exploding_bin(mech, bins):
    """The bin with the most destructive ammo per shot explodes (p.107).
    Ties on that go to the bin with the most shots left, then the
    controller's choice - neither is available here (shot counts aren't
    tracked), so stubs.stub_heat_explosion_bin picks among the tie."""
    scored = []
    unknown = []
    for location, b in bins:
        dv = ammo_bin_damage_value(b)
        if dv is None:
            unknown.append(b.name)
            dv = 0
        scored.append((dv, location, b))
    best = max(dv for dv, _, _ in scored)
    tied = [(location, b) for dv, location, b in scored if dv == best]
    if unknown or len(tied) > 1:
        return stubs.stub_heat_explosion_bin(mech.side_name, tied, best, unknown)
    return tied[0]


def _check_ammo_explosion(mech):
    level = mech.current_heat
    tn = ammo_avoid_tn(level)
    if tn is None:
        return
    bins = live_ammo_bins(mech)
    if not bins:
        return
    name = mech.side_name
    roll = config.roll_2d6(prompt="Ammo explosion avoid roll")
    if roll >= tn:
        config.log(f"  [Heat] {name}: ammo explosion avoid roll at heat {level}: needs {tn}, "
                   f"rolled {roll} - avoided.")
        return
    location, bin_ = choose_exploding_bin(mech, bins)
    config.log(f"  [Heat] {name}: ammo explosion avoid roll at heat {level}: needs {tn}, rolled {roll} - "
               f"{bin_.name} in {location} EXPLODES.")
    _destroy_bin_slots(mech, bin_)
    bin_.exploded = True
    apply_explosion(mech, bin_, location)


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
    hits = _highest(LIFE_SUPPORT_HITS_BY_HEAT, mech.current_heat)
    if not hits:
        return
    mech.pilot_hits += hits
    mark_consciousness_check_pending(mech)
    config.log(f"  [Heat] {mech.side_name}: life support destroyed, heat {mech.current_heat} - "
               f"MechWarrior takes {hits} hit(s) ({mech.pilot_hits}/6).")
    is_destroyed(mech)
