"""
Piloting Skill Roll (PSR) system - Daniel, 2026-07-16 design conversation.
See DESIGN_NOTES_mech.md#piloting_skill_rolls for the full design writeup
and the abridged/corrected PSR modifier table this module implements.

Two phases per turn, both driven from sim_runner.simulate_turn():

  MOVEMENT PHASE (resolve_movement_phase, called BEFORE the attack loop):
    - If the mech is prone, runs the stand-up retry loop (resolve_stand_up).
    - Otherwise, gets TMM + movement mode from damage_resolution.compute_tmm(),
      then runs check_movement_psr against that mode (leg actuator/gyro hit +
      jumping; Hip actuator/gyro hit + running - Daniel, 2026-07-16).
    Returns the TMM to use for this turn's attacks.

  ATTACK PHASE (resolve_attack_phase_psr, called AFTER the attack loop):
    - Diffs current state against pre_attack_phase_snapshot to find this-
      phase triggers (>=20 dmg, actuator destroyed, gyro hit, leg destroyed).
    - One accumulated roll per turn (not one per trigger) - all applicable
      modifiers (this-phase + preexisting + special-case) stack onto it.
    - A mech that's already prone can't fall further this phase (Daniel:
      "a mech that is prone can't fall over again unless attempting to
      stand") - skipped entirely if mech.prone is already True.

Fall damage + the "seatbelt check" (pilot-injury-avoidance roll) are shared
logic (resolve_fall) - called from all three PSR call sites (resolve_stand_up,
check_movement_psr, resolve_attack_phase_psr), per Daniel's explicit call
that this needed to be "its own script since this sequence is being used in
more than 1 place."

MOVEMENT MODE TRACKING (Daniel, 2026-07-16): damage_resolution.compute_tmm
now also sets mech.movement_mode_this_turn ("running"/"jump" - Mechanical
Jump Booster counts as "jump" if it wins) to whichever track produced the
winning TMM, switching only on strict '>' so a tie keeps "running" (Daniel:
"it has fewer triggers"). A mech that stood up from prone this turn never
runs through that comparison - resolve_stand_up sets the flag to "running"
directly, since only running MP is ever used to stand.

PILOT CONSCIOUSNESS (2026-07-17, Daniel/Claude): a THIRD checkpoint pair
plus an End Phase step, all driven from sim_runner.simulate_turn():
  - resolve_consciousness_checks(mech, "Movement Phase") - right after
    resolve_movement_phase() returns.
  - resolve_consciousness_checks(mech, "Attack Phase") - right after
    resolve_attack_phase_psr() returns.
  - resolve_end_phase_wakeup(mech) - once per turn, after the above.
mech.crew tracks each role's (pilot/gunner - tripod & quadvee only; single
"pilot" otherwise) unconscious/check_pending/went_out_this_turn state; see
mech_state.py's HELP(pilot_consciousness.crew_state) for the field-level
writeup and this module's HELP(pilot_consciousness.*) tags below for the
roll logic. All-crew-unconscious skips the Movement Phase entirely (TMM
-4) and auto-fails any Attack Phase PSR; a lone Pilot-unconscious (crew
NOT all out) instead adds +3 to every piloting roll via
special_case_modifier.

FLAGGED ASSUMPTIONS (not independently confirmed by Daniel - see design
notes tag above for the full list):
- Fall damage is applied as DamageType.PHYSICAL (matters only for Impact
  Resistant armor's dispatch in armor_rules.py - no other current armor
  type treats PHYSICAL differently from a flat 1:1 hit).
- A leg destroyed and its own actuator hits in the SAME phase are not
  double-counted (the +5 leg-destroyed value supersedes that leg's own
  this-phase actuator count) - extrapolated from Note 11's "ignore all
  other critical hit modifiers to that leg" (written for the preexisting-
  damage case) to the same-phase case, not independently confirmed.
- Gyro-destroyed automatic fall (+6 seatbelt modifier) is implemented per
  the table but is currently UNREACHABLE in this sim: mech_state.is_destroyed
  already kills the mech outright at 2 gyro hits, before this module would
  ever see a "destroyed but still fighting" gyro state. resolve_attack_phase_psr
  guards on is_destroyed(mech) at the top for exactly this reason - kept for
  correctness/future-proofing if that kill rule ever changes, not dead code
  removed outright.
- A mech that fails check_movement_psr during a normal (non-prone-at-start)
  turn returns tmm_from_mp(0) for the rest of that turn's TMM - same "fallen
  = 0" convention as the stood-up-then-fell-again path, not independently
  confirmed by Daniel.
- Cockpit-type (small/torso-mounted, +1) and AES-in-legs (-2) special cases
  are NOT implemented - Daniel: "skip special equipment for now" - neither
  is parsed anywhere in mtf_parser.py yet.
"""

import math

import config
from hit_location import resolve_hit_location
from mech_state import ArmorType, DamageType, is_destroyed, compute_running_mp, \
    mark_consciousness_check_pending, all_crew_unconscious, pilot_unconscious, consciousness_target_number
from damage_resolution import apply_damage, tmm_from_mp, compute_tmm

# HELP(piloting_skill_rolls.trigger_values)
# This-phase trigger modifiers (Daniel's abridged/corrected PSR table,
# 2026-07-16). Leg/gyro DESTROYED-this-phase are handled separately below
# (automatic fall, different modifier value) rather than through this dict.
DAMAGE_20_PLUS_MODIFIER = 1
LEG_ACTUATOR_DESTROYED_MODIFIER = 1
GYRO_HIT_MODIFIER = 2
GYRO_DESTROYED_SEATBELT_MODIFIER = 6   # Note 4 - currently unreachable, see module docstring
LEG_DESTROYED_SEATBELT_MODIFIER = 5    # Note 5

# Preexisting-damage modifiers (state at start of round) - same point values
# as their this-phase counterparts for actuators/gyro (table gives them the
# same number), but leg-already-destroyed uses the Note-5 value (+5), not
# the this-phase automatic-fall trigger - it's just a standing modifier here,
# no automatic fall (the mech didn't just fall this phase from it).
PREEXISTING_ACTUATOR_MODIFIER = 1
PREEXISTING_GYRO_HIT_MODIFIER = 2
PREEXISTING_LEG_DESTROYED_MODIFIER = 5


# HELP(piloting_skill_rolls.preexisting_snapshot)
def snapshot_preexisting_damage(mech):
    """Called once, at the very top of simulate_turn() (before the Movement
    Phase resolves) - captures the state PSR preexisting modifiers are
    computed from ("conditions that existed at the start of the round
    before damage was applied" - Daniel). Plain-value dict, no live
    references, so later mutation of mech.destroyed_leg_actuators etc. this
    turn can't retroactively change it."""
    mech.preexisting_damage_snapshot = {
        "gyro_hits": mech.gyro_hits,
        "destroyed_leg_actuators": dict(mech.destroyed_leg_actuators),
        "destroyed_legs": {loc for loc in mech.leg_locations if mech.locations[loc]["destroyed"]},
    }


# HELP(piloting_skill_rolls.pre_attack_snapshot)
def snapshot_pre_attack_phase(mech):
    """Called once per turn, after the Movement Phase resolves and BEFORE
    the Attack Phase's weapon-attack loop starts - source for the "20+
    damage this phase" delta and for detecting NEW-this-phase actuator/gyro/
    leg-destruction triggers (diffed against current state once the attack
    loop finishes, in resolve_attack_phase_psr)."""
    total_armor_structure = 0
    for loc, v in mech.locations.items():
        total_armor_structure += v.get("armor", 0) + v.get("rear_armor", 0) + v.get("structure", 0)

    mech.pre_attack_phase_snapshot = {
        "total_armor_structure": total_armor_structure,
        "gyro_hits": mech.gyro_hits,
        "destroyed_leg_actuators": dict(mech.destroyed_leg_actuators),
        "destroyed_legs": {loc for loc in mech.leg_locations if mech.locations[loc]["destroyed"]},
    }


def preexisting_modifier(mech):
    """Sum of every "Preexisting Damage" table row, off
    mech.preexisting_damage_snapshot. Applies to every PSR/stand-up/seatbelt
    roll made this turn, regardless of what triggered it (Daniel: "Preexisting
    damage will add their own modifiers to any roll however")."""
    snap = mech.preexisting_damage_snapshot
    if not snap:
        return 0

    total = snap["gyro_hits"] * PREEXISTING_GYRO_HIT_MODIFIER
    for loc in mech.leg_locations:
        if loc in snap["destroyed_legs"]:
            # Note 11: a leg already destroyed at start of round uses the
            # flat +5 in place of (not in addition to) that leg's own
            # actuator count.
            total += PREEXISTING_LEG_DESTROYED_MODIFIER
        else:
            total += snap["destroyed_leg_actuators"].get(loc, 0) * PREEXISTING_ACTUATOR_MODIFIER
    return total


def special_case_modifier(mech):
    """Unit-type/equipment modifiers that apply to EVERY PSR (Note 9).
    Hardened Armor, tripod, and quad/quadvee implemented (Daniel, 2026-07-16:
    tripod -2, quad -2, both confirmed values; quadvee shares the quad
    chassis so gets the same -2 - Daniel, 2026-07-17). Modifiers stack if
    more than one applies (e.g. a quad with Hardened Armor legs: -2 + 1 =
    -1). AES-in-legs (-2) and cockpit-type (+1) still deferred - Daniel:
    "skip special equipment for now" - neither is parsed anywhere in
    mtf_parser.py yet.

    Also includes the Pilot-role-unconscious +3 modifier (2026-07-17) - see
    pilot_consciousness.pilot_unconscious_modifier below."""
    total = 0
    if any(mech.armor_type.get(loc) == ArmorType.HARDENED for loc in mech.leg_locations):
        total += 1
    if mech.mech_type in ("tripod", "quad", "quadvee"):
        total -= 2
    # HELP(pilot_consciousness.pilot_unconscious_modifier)
    # Daniel, 2026-07-17: "Pilot: If unconscious +3 modifier to piloting
    # skill rolls." Only matters when the mech ISN'T already fully immobile
    # (all_crew_unconscious) - resolve_movement_phase/resolve_attack_phase_psr
    # skip/auto-fail entirely in that case, so this only has teeth for a
    # tripod/quadvee with Pilot out but Gunner still conscious.
    if pilot_unconscious(mech):
        total += 3
    return total


# HELP(piloting_skill_rolls.resolve_fall)
def resolve_fall(mech, seatbelt_modifier, cause=""):
    """Shared fall handler - called from resolve_attack_phase_psr (failed
    PSR or automatic gyro/leg-destroyed fall) and resolve_stand_up (failed
    stand attempt, or falling again immediately after a successful stand).
    Sets mech.prone = True, applies ceil(mass/10) falling damage in 5-point
    clusters (each independently rolled against the FRONT hit-location
    table - Daniel, 2026-07-16), then runs the seatbelt check (pilot-injury-
    avoidance roll) at config.PILOTING + seatbelt_modifier - the SAME
    accumulated modifier used for the roll that caused this fall (Daniel's
    worked example: leg destroyed +5, gyro hit +2, 20+ dmg +1 -> seatbelt TN
    is also 5+5+2+1=13, not a separate/lower baseline)."""
    mech.prone = True
    total_damage = math.ceil(mech.mass / 10)
    config.log(f"FALL{f' ({cause})' if cause else ''}: {mech.chassis} {mech.model} "
               f"takes {total_damage} falling damage (front table, 5-pt clusters).")

    remaining = total_damage
    while remaining > 0:
        cluster = min(5, remaining)
        loc_roll = config.roll_2d6(prompt="  Fall damage hit-location roll")
        loc = resolve_hit_location(loc_roll, mech, "front")
        config.log(f"  Fall cluster ({cluster} dmg): rolled {loc_roll} -> {loc}")
        apply_damage(mech, loc, cluster, armor_field="armor", damage_type=DamageType.PHYSICAL)
        remaining -= cluster
        if is_destroyed(mech):
            return

    needed = config.PILOTING + seatbelt_modifier
    roll = config.roll_2d6(prompt="  Seatbelt check roll")
    mod_note = f" (Piloting {config.PILOTING} + {seatbelt_modifier:+d})" if seatbelt_modifier else ""
    if roll < needed:
        mech.pilot_hits += 1
        mark_consciousness_check_pending(mech)
        config.log(f"  Seatbelt check: needs {needed}{mod_note}. Rolled {roll}. FAILED - "
                   f"pilot takes 1 hit ({mech.pilot_hits}/6).")
    else:
        config.log(f"  Seatbelt check: needs {needed}{mod_note}. Rolled {roll}. Pilot unharmed.")
    is_destroyed(mech)


# HELP(piloting_skill_rolls.check_movement_psr)
def check_movement_psr(mech, mode, cause=None):
    """Movement Phase PSR trigger (Daniel, 2026-07-16) - the original table's
    "Mech's Actions" rows, previously deferred (see module docstring history),
    now implemented as their own independent check separate from both
    resolve_attack_phase_psr's this-phase-diff triggers and the stand-up
    roll itself:
      - mode == "jump": ANY leg actuator destroyed, OR a fully destroyed leg
        (implies every actuator in it including Hip is gone too), OR a gyro
        hit.
      - mode == "running": Hip actuator destroyed SPECIFICALLY (not any leg
        actuator - Daniel: "its only hip and gyro hits that would trigger
        it since its only running MP being used"), OR a fully destroyed leg
        (implies Hip gone), OR a gyro hit.
    No trigger condition met -> no roll at all, mech just remains standing.
    Same roll mechanics as every other PSR in this module (Daniel: "Special
    modifiers apply to every piloting skill roll... mechanics should be the
    same") - config.PILOTING + preexisting_modifier + special_case_modifier,
    one roll, fail -> resolve_fall.

    Shared by two call sites with different GATES to reach this same check
    (Daniel: "The triggers and definitions should be the same, just
    different gates to get to the resolution"):
      - resolve_movement_phase: normal turn, mode = mech.movement_mode_this_turn
        (set by compute_tmm).
      - resolve_stand_up: stood up from prone this turn, mode forced
        "running" (only running MP is ever used to stand), additionally
        gated on remaining running_mp > 0 by the caller.

    Returns True if the mech remains standing (no trigger, or the roll
    succeeded), False if it fell (resolve_fall already ran)."""
    if mech.gyro_hits > 0:
        trigger_desc = "gyro hit"
    elif mode == "jump" and any(
        mech.locations[loc]["destroyed"] or mech.destroyed_leg_actuators.get(loc, 0) > 0
        for loc in mech.leg_locations
    ):
        trigger_desc = "leg actuator/leg destroyed while jumping"
    elif mode == "running" and any(
        mech.locations[loc]["destroyed"] or loc in mech.destroyed_hip_locations
        for loc in mech.leg_locations
    ):
        trigger_desc = "Hip/leg destroyed while running"
    else:
        return True  # no trigger condition met - no roll, remains standing

    modifier = preexisting_modifier(mech) + special_case_modifier(mech)
    needed = config.PILOTING + modifier
    roll = config.roll_2d6(prompt=f"Movement Phase PSR roll ({mode} mode)")
    config.log(f"Movement Phase PSR ({mode} mode, {trigger_desc}): needs {needed} "
               f"(Piloting {config.PILOTING} + {modifier:+d}). Rolled {roll}.")
    if roll < needed:
        config.log("  Failed - falls.")
        resolve_fall(mech, seatbelt_modifier=modifier,
                     cause=cause or f"failed Movement Phase PSR ({mode})")
        return False

    config.log("  Succeeded - remains standing.")
    return True


# HELP(piloting_skill_rolls.resolve_stand_up)
def resolve_stand_up(mech):
    """Movement Phase stand-up retry loop (Daniel, 2026-07-16): each attempt
    spends 2 running MP (floored at 0) toward this turn's TMM regardless of
    outcome. First attempt only needs running MP > 0 (minimum movement
    rule); every attempt after that needs remaining MP >= 2. Stops on
    success, insufficient MP, or pilot_hits reaching 5 (Daniel: "A pilot
    with 5 hits will remain prone rather than risk death by failing to
    stand" - checked before EVERY attempt, not just the first, since a
    failed attempt's seatbelt check can itself push pilot_hits to 5).

    On success: if MP remains, immediately re-checks for falling over again
    from preexisting damage (Daniel's Movement Phase flow) - a second
    failure here does NOT re-enter the retry loop ("will not attempt to
    stand again this round").

    Returns the running MP to use for this turn's TMM (0 if the mech ends
    the Movement Phase still prone)."""
    if mech.pilot_hits >= 5:
        config.log("Pilot has 5+ hits - remaining prone rather than risk a stand attempt.")
        return 0

    running_mp = compute_running_mp(mech)
    if running_mp <= 0:
        config.log("No running MP available - cannot attempt to stand (minimum movement rule). "
                   "Remains prone.")
        return 0

    attempt = 0
    while True:
        attempt += 1
        if attempt > 1:
            if running_mp < 2:
                config.log("Insufficient MP (<2) remaining for another stand attempt. Remains prone.")
                return 0
            if mech.pilot_hits >= 5:
                config.log("Pilot reached 5 hits from a failed stand attempt - stopping, remains prone.")
                return 0

        running_mp = max(0, running_mp - 2)
        modifier = preexisting_modifier(mech) + special_case_modifier(mech)
        needed = config.PILOTING + modifier
        roll = config.roll_2d6(prompt=f"Stand-up attempt {attempt} roll")
        config.log(f"Stand attempt {attempt}: needs {needed} (Piloting {config.PILOTING} "
                   f"+ {modifier:+d}). Rolled {roll}.")

        if roll < needed:
            config.log("  Failed to stand.")
            resolve_fall(mech, seatbelt_modifier=modifier, cause="failed to stand")
            if is_destroyed(mech):
                return 0
            continue  # loop re-checks stopping conditions at the top

        mech.prone = False
        config.log(f"  Success - {mech.chassis} {mech.model} is standing "
                   f"(remaining running MP {running_mp}).")

        if running_mp > 0:
            mech.movement_mode_this_turn = "running"  # only running MP is ever used to stand
            if not check_movement_psr(mech, "running", cause="fell again after standing"):
                config.log("  Will not attempt to stand again this round.")
                return 0

        return running_mp


# HELP(piloting_skill_rolls.resolve_movement_phase)
def resolve_movement_phase(mech):
    """Called once per turn, at the very top, BEFORE the attack loop. If the
    mech is prone, runs the stand-up loop and returns TMM off whatever
    running MP survives it (jump TMM is NOT available at all this turn,
    win or lose - Daniel: "Jump TMM is not available at all" while
    resolving a prone flag). Otherwise, this is a normal turn - gets TMM and
    movement mode from damage_resolution.compute_tmm() (running vs. jump vs.
    Mechanical Jump Booster, whichever's highest - see that function's
    docstring), then runs check_movement_psr against the winning mode.

    FLAGGED ASSUMPTION: a mech that fails this check falls (resolve_fall
    already ran inside check_movement_psr) - returns tmm_from_mp(0) rather
    than the TMM it would have had, same "fallen = 0" convention already
    used by the stood-up-then-fell-again path below. Not independently
    confirmed by Daniel; flag if a fallen mech should carry some other TMM
    value this turn.

    PILOT CONSCIOUSNESS (Daniel, 2026-07-17): if every tracked crew member
    is unconscious (mech_state.all_crew_unconscious), the Movement Phase is
    skipped entirely (Daniel: "an unconscious mech skips the Movement
    phase") - no stand-up attempt, no TMM computation - this turn's TMM is
    a flat -4 instead. Checked first, before the prone branch, so a mech
    that's both prone AND fully unconscious doesn't attempt to stand."""
    if all_crew_unconscious(mech):
        config.log("All crew unconscious - Movement Phase skipped, TMM -4.")
        return -4

    if mech.prone:
        remaining_mp = resolve_stand_up(mech)
        return tmm_from_mp(remaining_mp)

    tmm = compute_tmm(mech)
    if not check_movement_psr(mech, mech.movement_mode_this_turn):
        return tmm_from_mp(0)
    return tmm


# HELP(piloting_skill_rolls.resolve_attack_phase_psr)
def resolve_attack_phase_psr(mech):
    """Called once per turn, AFTER the attack loop finishes. Skips entirely
    if the mech is already destroyed (nothing to resolve for a dead mech -
    also the guard that makes the gyro-destroyed automatic-fall branch
    below unreachable, see module docstring) or already prone (Daniel: "a
    mech that is prone can't fall over again unless attempting to stand").

    Diffs current state against mech.pre_attack_phase_snapshot to find
    this-phase triggers, accumulates ALL applicable modifiers (this-phase +
    preexisting + special-case) into ONE roll (Daniel: "1 accumulated roll
    after all attacks have been made"). Leg-destroyed-this-phase and
    (unreachable) gyro-destroyed-this-phase are automatic falls - no roll
    to prevent the fall itself, but the seatbelt check still uses the full
    accumulated modifier (Note 4/5 values in place of the lesser hit-level
    values).

    PILOT CONSCIOUSNESS (Daniel, 2026-07-17): if a trigger fires and every
    tracked crew member is unconscious (mech_state.all_crew_unconscious),
    the roll itself is skipped - auto-fail straight to resolve_fall, same
    accumulated modifier. See resolve_consciousness_checks/
    resolve_end_phase_wakeup below for where crew go unconscious/wake up."""
    if is_destroyed(mech) or mech.prone:
        return

    snap = mech.pre_attack_phase_snapshot
    if not snap:
        return  # nothing to diff against - shouldn't happen post-snapshot_pre_attack_phase, safe no-op

    modifier = 0
    triggered = False
    automatic_fall = False

    current_total = sum(v.get("armor", 0) + v.get("rear_armor", 0) + v.get("structure", 0)
                         for v in mech.locations.values())
    damage_this_phase = snap["total_armor_structure"] - current_total
    if damage_this_phase >= 20:
        modifier += DAMAGE_20_PLUS_MODIFIER
        triggered = True
        config.log(f"PSR trigger: {damage_this_phase} armor+structure lost this phase (>=20) "
                   f"-> {DAMAGE_20_PLUS_MODIFIER:+d}.")

    newly_destroyed_legs = set()
    for loc in mech.leg_locations:
        if loc in snap["destroyed_legs"]:
            continue  # already destroyed before this phase - preexisting_modifier() covers it
        if mech.locations[loc]["destroyed"]:
            newly_destroyed_legs.add(loc)
            automatic_fall = True
            modifier += LEG_DESTROYED_SEATBELT_MODIFIER
            config.log(f"PSR trigger: {loc} destroyed this phase -> automatic fall "
                       f"(seatbelt {LEG_DESTROYED_SEATBELT_MODIFIER:+d}).")

    for loc in mech.leg_locations:
        if loc in snap["destroyed_legs"] or loc in newly_destroyed_legs:
            continue  # Note 11 extrapolation - don't double-count a leg destroyed this same phase
        new_actuators = mech.destroyed_leg_actuators.get(loc, 0) - snap["destroyed_leg_actuators"].get(loc, 0)
        if new_actuators > 0:
            modifier += new_actuators * LEG_ACTUATOR_DESTROYED_MODIFIER
            triggered = True
            config.log(f"PSR trigger: {new_actuators} leg actuator(s) destroyed at {loc} this phase "
                       f"-> {new_actuators * LEG_ACTUATOR_DESTROYED_MODIFIER:+d}.")

    new_gyro_hits = mech.gyro_hits - snap["gyro_hits"]
    if new_gyro_hits > 0:
        if mech.gyro_hits >= 2:
            # Currently unreachable - is_destroyed() already returns True at 2 gyro
            # hits and this function returns at the top. Kept for correctness/
            # future-proofing, see module docstring.
            automatic_fall = True
            modifier += GYRO_DESTROYED_SEATBELT_MODIFIER
            config.log(f"PSR trigger: Gyro destroyed this phase -> automatic fall "
                       f"(seatbelt {GYRO_DESTROYED_SEATBELT_MODIFIER:+d}).")
        else:
            modifier += new_gyro_hits * GYRO_HIT_MODIFIER
            triggered = True
            config.log(f"PSR trigger: Gyro hit this phase -> {new_gyro_hits * GYRO_HIT_MODIFIER:+d}.")

    if not (triggered or automatic_fall):
        return

    modifier += preexisting_modifier(mech) + special_case_modifier(mech)

    if automatic_fall:
        config.log(f"Automatic fall this phase - seatbelt check only (accumulated modifier {modifier:+d}).")
        resolve_fall(mech, seatbelt_modifier=modifier, cause="automatic fall")
        return

    # HELP(pilot_consciousness.attack_phase_auto_fail)
    # Daniel, 2026-07-17: "any subsequent piloting skill rolls will
    # automatically fail" once every crew member is unconscious - no roll,
    # straight to resolve_fall at the same accumulated modifier a normal
    # roll would have used.
    if all_crew_unconscious(mech):
        config.log(f"All crew unconscious - Attack Phase PSR auto-fails (accumulated modifier {modifier:+d}).")
        resolve_fall(mech, seatbelt_modifier=modifier, cause="auto-fail (all crew unconscious)")
        return

    needed = config.PILOTING + modifier
    roll = config.roll_2d6(prompt="Attack Phase PSR roll")
    config.log(f"Attack Phase PSR: needs {needed} (Piloting {config.PILOTING} + {modifier:+d}). "
               f"Rolled {roll}.")
    if roll < needed:
        config.log("  Failed - falls.")
        resolve_fall(mech, seatbelt_modifier=modifier, cause="failed Attack Phase PSR")
    else:
        config.log("  Succeeded - remains standing.")


# HELP(pilot_consciousness.resolve_checks)
def resolve_consciousness_checks(mech, phase_label):
    """Called TWICE per turn from sim_runner.simulate_turn (Daniel,
    2026-07-17): once right after resolve_movement_phase() returns, and
    once right after resolve_attack_phase_psr() returns - "This will
    trigger once after the Prone/still standing (Movement Phase) loop. And
    once again after the Damage/potential piloting skill loop."

    For every crew member with check_pending set (mark_consciousness_check_
    pending was called from every mech.pilot_hits += 1 site this phase),
    rolls against mech_state.consciousness_target_number(mech.pilot_hits).
    Success -> stays conscious, check_pending cleared. Failure -> marked
    unconscious, went_out_this_turn=True (feeds the wake-up roll's 1-turn
    decay), check_pending cleared. A crew member who's already unconscious
    never gets flagged pending in the first place (mark_consciousness_
    check_pending's own guard), so this naturally never re-rolls someone
    already out - "no need to make further consciousness checks when the
    pilot is unconscious."

    phase_label is a log-only string ("Movement Phase"/"Attack Phase") so
    the two call sites' rolls are distinguishable in the log."""
    if is_destroyed(mech):
        return

    for role, state in mech.crew.items():
        if not state["check_pending"]:
            continue
        state["check_pending"] = False

        needed = consciousness_target_number(mech.pilot_hits)
        roll = config.roll_2d6(prompt=f"{phase_label} consciousness check ({role})")
        config.log(f"{phase_label} consciousness check ({role}, {mech.pilot_hits} pilot hits): "
                   f"needs {needed}. Rolled {roll}.")
        if roll < needed:
            state["unconscious"] = True
            state["went_out_this_turn"] = True
            config.log(f"  {role.capitalize()} knocked unconscious.")
        else:
            config.log(f"  {role.capitalize()} stays conscious.")


# HELP(pilot_consciousness.resolve_end_phase_wakeup)
def resolve_end_phase_wakeup(mech):
    """Called once per turn, after resolve_attack_phase_psr's consciousness
    check (Daniel, 2026-07-17: "wake up happens after the attack/psr phase.
    (Technically the end phase in game.)"). For every crew member who is
    unconscious AND did NOT go out this same turn (1-turn decay - Daniel:
    "If the state was changed this turn then the 'Am I awake' check is not
    made until the end of the next turn"), rolls to wake up against the
    same Consciousness Number table used for the initial check. Resets
    EVERY crew member's went_out_this_turn to False at the end, regardless
    of outcome, so next turn's hits (if any) are evaluated fresh and a
    still-unconscious crew member gets another wake-up attempt next turn.

    Worked example confirmed by Daniel (2 crew): Pilot knocked out turn 1
    (went_out_this_turn=True that turn, no wake attempt turn 1's End Phase).
    Gunner knocked out turn 2 - that same End Phase, Pilot (unchanged since
    turn 1) DOES attempt to wake (and may take further damage from turn 2's
    attacks without a fresh consciousness check, since Pilot was already
    unconscious all of turn 2), while Gunner does not (just went out this
    turn). Turn 3's End Phase: Gunner's first wake attempt; Pilot's next
    attempt if still out."""
    if is_destroyed(mech):
        return

    for role, state in mech.crew.items():
        if state["unconscious"] and not state["went_out_this_turn"]:
            needed = consciousness_target_number(mech.pilot_hits)
            roll = config.roll_2d6(prompt=f"End Phase wake-up roll ({role})")
            config.log(f"End Phase wake-up check ({role}, {mech.pilot_hits} pilot hits): "
                       f"needs {needed}. Rolled {roll}.")
            if roll >= needed:
                state["unconscious"] = False
                config.log(f"  {role.capitalize()} wakes up.")
            else:
                config.log(f"  {role.capitalize()} remains unconscious.")

    for state in mech.crew.values():
        state["went_out_this_turn"] = False
