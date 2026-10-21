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
    - One roll per trigger (2026-10-20, Core p.110 - was one accumulated
      roll), every roll at the sum of all applicable modifiers (this-phase +
      preexisting + special-case); the first failure is a fall.
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
  double-counted (leg destruction replaces that leg's actuator effects,
  Core p.90).
- Gyro-destroyed automatic fall: reachable only with
  config.FIGHT_TO_THE_DEATH (otherwise mech_state.is_destroyed kills the
  mech at 2 gyro hits first).
- Seatbelt checks follow Core p.117 since 2026-10-20 (Piloting + levels
  fallen only; see resolve_fall).
- A mech that fails check_movement_psr during a normal (non-prone-at-start)
  turn returns tmm_from_mp(0) for the rest of that turn's TMM - same "fallen
  = 0" convention as the stood-up-then-fell-again path, not independently
  confirmed by Daniel.
- Cockpit type (small / torso-mounted, +1, p.203): built 2026-10-21 (was
  deferred - Daniel: "skip special equipment for now"). AES-in-legs (-2)
  since 2026-10-20 (mech_state.leg_aes_working).
"""

import math

import config
from hit_location import resolve_hit_location
from mech_state import has_small_cockpit, has_torso_cockpit, torso_cockpit_sensor_penalty, \
    destroyed_leg_count, tripod_pilot_modifier, is_quad, live_hip_legs, hip_effects
from mech_state import ArmorType, DamageType, is_destroyed, compute_running_mp, leg_aes_working, \
    mark_consciousness_check_pending, all_crew_unconscious, pilot_unconscious, consciousness_target_number, \
    is_immobile
from damage_resolution import apply_damage, tmm_from_mp, compute_tmm

# HELP(piloting_skill_rolls.trigger_values)
# This-phase trigger modifiers (Daniel's abridged/corrected PSR table,
# 2026-07-16). Leg/gyro DESTROYED-this-phase are handled separately below
# (automatic fall, different modifier value) rather than through this dict.
DAMAGE_20_PLUS_MODIFIER = 1
LEG_ACTUATOR_DESTROYED_MODIFIER = 1
GYRO_HIT_MODIFIER = 2

# Preexisting-damage modifiers (state at start of round) - same point values
# as their this-phase counterparts for actuators/gyro (table gives them the
# same number), but leg-already-destroyed uses the Note-5 value (+5), not
# the this-phase automatic-fall trigger - it's just a standing modifier here,
# no automatic fall (the mech didn't just fall this phase from it).
PREEXISTING_ACTUATOR_MODIFIER = 1
PREEXISTING_GYRO_HIT_MODIFIER = 2
PREEXISTING_LEG_DESTROYED_MODIFIER = 4   # p.111 (2026-10-21; MECHSIM had 5)
QUAD_LEG_DESTROYED_MODIFIER = 1          # p.238: a quad's 1st and 2nd destroyed legs, +1 each
STAND_UP_MODIFIER = -1                   # p.51, PSR table p.111: each attempt to stand
QUAD_PSR_MODIFIER = -2                   # p.239 (errata): a quad with no leg destroyed
TRIPOD_PSR_MODIFIER = -1                 # p.237: a tripod with no leg destroyed (MECHSIM had -2)
COCKPIT_PSR_MODIFIER = 1                 # small or torso-mounted cockpit, every PSR (p.203)


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
        "hip_legs": set(mech.destroyed_hip_locations),
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
        "hip_legs": set(mech.destroyed_hip_locations),
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
        if loc not in snap["destroyed_legs"]:
            total += snap["destroyed_leg_actuators"].get(loc, 0) * PREEXISTING_ACTUATOR_MODIFIER
    # A leg already destroyed at the start of the round: +4 in place of (not in
    # addition to) that leg's own actuator hits (p.111 note 14). A quad (p.238):
    # +1 for each of its first two lost legs; a third makes it a biped with one
    # leg lost (+4); its first hip hit has no PSR modifier (p.239). (Was
    # MECHSIM's +5 for any leg.)
    lost = len(snap["destroyed_legs"])
    if is_quad(mech):
        total += lost * QUAD_LEG_DESTROYED_MODIFIER if lost <= 2 else PREEXISTING_LEG_DESTROYED_MODIFIER
        if live_hip_legs(mech, snap["destroyed_legs"], snap.get("hip_legs", set())):
            total -= PREEXISTING_ACTUATOR_MODIFIER
    else:
        total += lost * PREEXISTING_LEG_DESTROYED_MODIFIER
    return total


def special_case_modifier(mech):
    """Unit-type/equipment modifiers that apply to EVERY PSR (Note 9).
    Hardened Armor +1; quad / quadvee -2 and tripod -1, each only while no
    leg is destroyed, plus a tripod's dedicated pilot -1 (+2 if disabled)
    (Core pp.236-239; 2026-10-21, Daniel: "Stand up, tripod, jumping, 4
    legged mechs should all have answers in the rules" - was MECHSIM's -2
    for both, legs or not). Modifiers stack if more than one applies (e.g. a
    quad with Hardened Armor legs: -2 + 1 = -1). AES in all legs: a fixed -2 (Core p.206; added 2026-10-20, Daniel:
    "if AES is the only thing not built in this test, lets get that fixed"),
    lost if any leg AES slot is hit. Small / torso-mounted cockpit +1 and a
    torso-mounted cockpit's sensor hits +4 (p.203, 2026-10-21).

    Also includes the Pilot-role-unconscious +3 modifier (2026-07-17; a
    QuadVee's - a tripod uses the rulebook's +2 above) - see
    pilot_consciousness.pilot_unconscious_modifier below."""
    total = 0
    if any(mech.armor_type.get(loc) == ArmorType.HARDENED for loc in mech.leg_locations):
        total += 1
    # Four and three legs: -2 / -1 only while no leg is destroyed (pp.237, 239;
    # 2026-10-21 - was -2 for both, legs or not). A tripod's dedicated pilot -1,
    # +2 if disabled (p.236, mech_state.tripod_pilot_modifier).
    if mech.mech_type in ("quad", "quadvee") and not destroyed_leg_count(mech):
        total += QUAD_PSR_MODIFIER
    if mech.mech_type == "tripod" and not destroyed_leg_count(mech):
        total += TRIPOD_PSR_MODIFIER
    total += tripod_pilot_modifier(mech)
    if leg_aes_working(mech):
        total -= 2                                  # AES in all legs, p.206
    # Small or torso-mounted cockpit: +1 to every PSR (p.203; 2026-10-21 - was
    # deferred, "skip special equipment for now"), and a torso-mounted
    # cockpit's sensor hits +4 (mech_state.torso_cockpit_sensor_penalty).
    if has_small_cockpit(mech) or has_torso_cockpit(mech):
        total += COCKPIT_PSR_MODIFIER
    total += torso_cockpit_sensor_penalty(mech)
    # HELP(pilot_consciousness.pilot_unconscious_modifier)
    # Daniel, 2026-07-17: "Pilot: If unconscious +3 modifier to piloting
    # skill rolls." Only matters when the mech ISN'T already fully immobile
    # (all_crew_unconscious) - resolve_movement_phase/resolve_attack_phase_psr
    # skip/auto-fail entirely in that case, so this only has teeth for a
    # tripod/quadvee with Pilot out but Gunner still conscious.
    if pilot_unconscious(mech) and mech.mech_type != "tripod":     # tripods: tripod_pilot_modifier
        total += 3
    return total


# HELP(piloting_skill_rolls.resolve_fall)
def resolve_fall(mech, cause="", levels=0, side=None):
    """Shared fall handler - called from resolve_attack_phase_psr (failed
    PSR or automatic gyro/leg-destroyed fall), check_movement_psr and
    resolve_stand_up, and the displacement / DFA code. Sets mech.prone =
    True, applies the falling damage in 5-point clusters, then makes the
    seatbelt check.

    Rules as written since 2026-10-20 (Daniel: "Follow the rules as written";
    "Add that functionality"):
      - Damage (p.115): ceil(tonnage / 10) x (levels fallen + 1), in 5-point
        groupings, a Hit Location roll for each.
      - Side (p.115): "roll 1D6: on a 1, all damage is applied to the rear,
        otherwise it is applied to the front". side= skips the roll when a
        rule names the side ("rear" for a failed death from above, p.80).
      - Seatbelt check (p.117): Piloting + 1 per level fallen above 0, and
        no other modifier; the MechWarrior takes 1 hit on a failure, or
        automatically if the 'Mech is immobile or the target number is over
        12. (Was: the fall's whole PSR modifier, Daniel's 2026-07-16 rule.)
    levels: levels fallen - a mech displaced two or more levels down falls
    automatically (2026-10-20, Core p.115).
    Water (2026-10-21, p.115): damage halved (rounded down) when the mech's
    hex is depth 1+ water."""
    mech.prone = True
    if side is None:
        die = config.pick_number(6, prompt="  Fall side 1D6 (1 = rear)")
        side = "rear" if die == 1 else "front"
        side_note = f"1D6 {die}: {side}"
    else:
        side_note = side
    total_damage = fall_damage(mech) * (levels + 1)
    # Water (2026-10-21, Core p.115): a fall in depth 1+ water does half damage,
    # rounded down. The board's depth is the integration's (INTEGRATION__water).
    import INTEGRATION__water as water
    divisor = water.fall_damage_divisor(mech)
    total_damage //= divisor
    config.log(f"FALL{f' ({cause})' if cause else ''}: {mech.chassis} {mech.model} "
               f"takes {total_damage} falling damage{' (halved: water, p.115)' if divisor > 1 else ''} "
               f"({side_note} table, 5-pt clusters).")

    remaining = total_damage
    while remaining > 0:
        cluster = min(5, remaining)
        loc_roll = config.roll_2d6(prompt="  Fall damage hit-location roll")
        loc = resolve_hit_location(loc_roll, mech, side)
        config.log(f"  Fall cluster ({cluster} dmg): rolled {loc_roll} -> {loc}")
        apply_damage(mech, loc, cluster, armor_field="rear_armor" if side == "rear" else "armor",
                     damage_type=DamageType.PHYSICAL)
        remaining -= cluster
        if is_destroyed(mech):
            return

    needed = config.PILOTING + levels
    level_note = f" (Piloting {config.PILOTING} + {levels} levels)" if levels else ""
    if is_immobile(mech) or needed > 12:
        mech.pilot_hits += 1
        mark_consciousness_check_pending(mech)
        why = "immobile" if is_immobile(mech) else f"needs {needed}"
        config.log(f"  Seatbelt check: {why} - pilot takes 1 hit automatically ({mech.pilot_hits}/6).")
    else:
        roll = config.roll_2d6(prompt="  Seatbelt check roll")
        if roll < needed:
            mech.pilot_hits += 1
            mark_consciousness_check_pending(mech)
            config.log(f"  Seatbelt check: needs {needed}{level_note}. Rolled {roll}. FAILED - "
                       f"pilot takes 1 hit ({mech.pilot_hits}/6).")
        else:
            config.log(f"  Seatbelt check: needs {needed}{level_note}. Rolled {roll}. Pilot unharmed.")
    is_destroyed(mech)


def roll_psrs(mech, count, modifier, what):
    """p.110 Multiple Rolls (2026-10-20, rules as written): `count` PSRs made
    one at a time, each at Piloting + `modifier` (every modifier applies to
    every roll); the first failure means a fall and the rest are not rolled.
    Returns True if every roll succeeded. Does not resolve the fall."""
    needed = config.PILOTING + modifier
    for i in range(1, count + 1):
        roll = config.roll_2d6(prompt=f"{what} roll {i}/{count}")
        config.log(f"{what}{f' {i}/{count}' if count > 1 else ''}: needs {needed} "
                   f"(Piloting {config.PILOTING} + {modifier:+d}). Rolled {roll}.")
        if roll < needed:
            config.log("  Failed - falls." + (f" ({count - i} more not rolled.)" if i < count else ""))
            return False
    config.log("  Succeeded - remains standing.")
    return True


def can_stand(mech):
    """Whether a prone mech may try to stand at all (2026-10-20): not with a
    destroyed gyro (p.98), two destroyed legs, or one destroyed leg and two
    destroyed arms (p.51). Only reachable with config.FIGHT_TO_THE_DEATH -
    otherwise the first two are kills."""
    if mech.gyro_hits >= 2:
        return False
    legs_lost = sum(1 for loc in mech.leg_locations if mech.locations[loc]["destroyed"])
    arms_lost = sum(1 for loc in ("Left Arm", "Right Arm") if loc in mech.locations
                    and mech.locations[loc]["destroyed"])
    if is_quad(mech):
        return legs_lost < 4                 # three lost = a biped with one leg (p.238)
    return legs_lost < 2 and not (legs_lost == 1 and arms_lost == 2)


def movement_psr_trigger(mech, mode):
    """Which Movement Phase PSR trigger applies to `mech` moving in `mode`
    ("running" / "jump"), as the description check_movement_psr logs - or None
    when no roll is forced. Split out of check_movement_psr (2026-10-19,
    Claude) so movement selection can price a PSR before choosing a move;
    the conditions are unchanged. Walking and standing still never reach
    this (Core p.111) - callers gate those."""
    if mech.gyro_hits > 0:
        return "gyro hit"
    if is_quad(mech):
        return _quad_trigger(mech, mode)
    if mode == "jump" and any(
        mech.destroyed_leg_actuators.get(loc, 0) > 0 or mech.locations[loc]["destroyed"]
        for loc in mech.leg_locations
    ):
        return "leg actuator/leg destroyed while jumping"
    if mode == "running" and any(
        loc in mech.destroyed_hip_locations or mech.locations[loc]["destroyed"]
        for loc in mech.leg_locations
    ):
        return "Hip/leg destroyed while running"
    return None


def _is_quad(mech):
    return is_quad(mech)


def _quad_counts(mech, mode):
    """Movement-mode PSRs a quad's leg damage forces (pp.238-239, 2026-10-21):
    running - one per hip hit with its standard effects (two lost legs count
    as one), one more from the third lost leg; jumping - one per leg still on
    the 'Mech with an actuator hit (its free first hip aside), one from two or
    more lost legs. One lost leg forces none ("can still run and jump")."""
    lost = destroyed_leg_count(mech)
    if mode == "running":
        return hip_effects(mech) + (1 if lost >= 3 else 0)
    live = [l for l in mech.leg_locations if not mech.locations[l]["destroyed"]]
    hips = live_hip_legs(mech)
    # legs with an actuator hit other than the hip, then legs whose only hit is the hip -
    # the free first hip taken from those (Claude's call: hits aren't kept in order)
    damaged = [l for l in live if mech.destroyed_leg_actuators.get(l, 0) > (1 if l in hips else 0)]
    hip_only = [l for l in hips if l not in damaged]
    return len(damaged) + max(0, len(hip_only) - 1) + (1 if lost >= 2 else 0)


def _quad_trigger(mech, mode):
    if mode in ("running", "jump") and _quad_counts(mech, mode):
        return "a quad's leg damage"
    return None


def movement_psr_count(mech, mode):
    """How many Movement Phase PSRs moving in `mode` forces (2026-10-20,
    rules as written, p.111 "each" and p.110 Leg Damage): one for a gyro hit,
    plus one per leg with damage that triggers in this mode (running: a
    destroyed leg or hip; jumping: a destroyed leg or any destroyed leg
    actuator) - never more than one per leg. 0 when movement_psr_trigger is
    None."""
    if movement_psr_trigger(mech, mode) is None:
        return 0
    count = 1 if mech.gyro_hits > 0 else 0
    if _is_quad(mech):
        return count + _quad_counts(mech, mode)
    for loc in mech.leg_locations:
        if mech.locations[loc]["destroyed"]:
            count += 1
        elif mode == "jump" and mech.destroyed_leg_actuators.get(loc, 0) > 0:
            count += 1
        elif mode == "running" and loc in mech.destroyed_hip_locations:
            count += 1
    return count


def movement_psr_target_number(mech, mode):
    """Target number (2d6, roll under it fails) of the Movement Phase PSR this
    mech would have to make moving in `mode`, or None if none is forced.
    Same arithmetic check_movement_psr uses: the mech's own piloting skill +
    preexisting-damage and special-case modifiers. Read-only."""
    if movement_psr_trigger(mech, mode) is None:
        return None
    return mech.piloting + preexisting_modifier(mech) + special_case_modifier(mech)


def fall_damage(mech):
    """Falling damage in points: ceil(mass / 10) (see resolve_fall)."""
    return math.ceil(mech.mass / 10)


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
    one roll per trigger (movement_psr_count, 2026-10-20), fail -> resolve_fall.

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
    trigger_desc = movement_psr_trigger(mech, mode)
    if trigger_desc is None:
        return True  # no trigger condition met - no roll, remains standing

    modifier = preexisting_modifier(mech) + special_case_modifier(mech)
    count = movement_psr_count(mech, mode)
    if not roll_psrs(mech, count, modifier, f"Movement Phase PSR ({mode} mode, {trigger_desc})"):
        resolve_fall(mech, cause=cause or f"failed Movement Phase PSR ({mode})")
        return False
    return True


# HELP(piloting_skill_rolls.resolve_stand_up)
def resolve_stand_up(mech, mp_available=None):
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
    the Movement Phase still prone).

    mp_available (2026-10-21, Daniel's movement subphase): the MP the mech
    has left after falling partway through its move (p.51: it "can attempt
    to stand in the same Movement Phase that it fell, as long as it has
    enough MP left"); None = its full running MP."""
    if not can_stand(mech):
        config.log("Cannot stand (destroyed gyro, or too many legs / arms lost - pp.51, 98). Remains prone.")
        return 0
    if mech.pilot_hits >= 5:
        config.log("Pilot has 5+ hits - remaining prone rather than risk a stand attempt.")
        return 0

    running_mp = compute_running_mp(mech) if mp_available is None else mp_available
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
        if mech.mech_type in ("quad", "quadvee") and not destroyed_leg_count(mech):
            # p.238: a quad with all four legs stands without a PSR (2026-10-21).
            config.log(f"Stand attempt {attempt}: a quad with no leg destroyed stands without a PSR (p.238).")
            roll, needed = None, None
        else:
            # p.51 / p.111: each attempt is a PSR at -1 (2026-10-21; MECHSIM had no -1).
            modifier = preexisting_modifier(mech) + special_case_modifier(mech) + STAND_UP_MODIFIER
            needed = config.PILOTING + modifier
            roll = config.roll_2d6(prompt=f"Stand-up attempt {attempt} roll")
            config.log(f"Stand attempt {attempt}: needs {needed} (Piloting {config.PILOTING} "
                       f"+ {modifier:+d}, incl. -1 for standing). Rolled {roll}.")

        if roll is not None and roll < needed:
            config.log("  Failed to stand.")
            resolve_fall(mech, cause="failed to stand")
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
def resolve_attack_phase_psr(mech, forced_triggers=()):
    """Called after each attack phase. Skips entirely if the mech is already
    destroyed or already prone (Daniel: "a mech that is prone can't fall
    over again unless attempting to stand"; Core p.110).

    Diffs current state against mech.pre_attack_phase_snapshot to find
    this-phase triggers. Since 2026-10-20 (Daniel: rules as written, Core
    p.110): one PSR per trigger, each at the sum of ALL applicable modifiers
    (this-phase + preexisting + special-case), stopping at the first
    failure; leg damage forces at most one roll per leg. A leg (or, with
    config.FIGHT_TO_THE_DEATH, the gyro) destroyed this phase is an
    automatic fall - no roll. Was: one accumulated roll (Daniel, 2026-07-16).

    PILOT CONSCIOUSNESS (Daniel, 2026-07-17): if a trigger fires and every
    tracked crew member is unconscious (mech_state.all_crew_unconscious),
    the rolls are skipped - auto-fail straight to resolve_fall. See
    resolve_consciousness_checks/resolve_end_phase_wakeup below for where
    crew go unconscious/wake up.

    forced_triggers (2026-10-19, INTEGRATION__physical): extra (reason,
    modifier) PSR triggers from this phase that aren't damage - kicked,
    missed a kick (Core p.111, both +0), charged. Each is one more roll."""
    if is_destroyed(mech) or mech.prone:
        return

    snap = mech.pre_attack_phase_snapshot
    if not snap:
        return  # nothing to diff against - shouldn't happen post-snapshot_pre_attack_phase, safe no-op

    # Rules as written since 2026-10-20 (Daniel: "Follow the rules as written"):
    # one PSR per trigger, each made at the SUM of every modifier this phase
    # (plus preexisting damage and special cases), the first failure is a fall
    # and ends the sequence (p.110 Multiple Rolls). Leg damage forces at most
    # one roll per leg, whatever number of actuators it lost (p.110 Leg Damage).
    # A leg or gyro destroyed this phase is an automatic fall (p.111) - no roll.
    modifier = 0
    rolls = 0
    automatic_fall = False

    current_total = sum(v.get("armor", 0) + v.get("rear_armor", 0) + v.get("structure", 0)
                         for v in mech.locations.values())
    damage_this_phase = snap["total_armor_structure"] - current_total
    if damage_this_phase >= 20:
        modifier += DAMAGE_20_PLUS_MODIFIER
        rolls += 1
        config.log(f"PSR trigger: {damage_this_phase} armor+structure lost this phase (>=20) "
                   f"-> {DAMAGE_20_PLUS_MODIFIER:+d}.")

    newly_destroyed_legs = set()
    for loc in mech.leg_locations:
        if loc in snap["destroyed_legs"]:
            continue  # already destroyed before this phase - preexisting_modifier() covers it
        if mech.locations[loc]["destroyed"]:
            newly_destroyed_legs.add(loc)
            automatic_fall = True
            config.log(f"PSR trigger: {loc} destroyed this phase -> automatic fall.")

    for loc in mech.leg_locations:
        if loc in snap["destroyed_legs"] or loc in newly_destroyed_legs:
            continue  # leg destruction replaces that leg's actuator effects (p.90)
        new_actuators = mech.destroyed_leg_actuators.get(loc, 0) - snap["destroyed_leg_actuators"].get(loc, 0)
        if (is_quad(mech) and new_actuators > 0 and loc in mech.destroyed_hip_locations
                and loc not in snap.get("hip_legs", ()) and len(live_hip_legs(mech)) == 1):
            new_actuators -= 1               # a quad's first hip hit: none of the standard effects (p.239)
        if new_actuators > 0:
            modifier += new_actuators * LEG_ACTUATOR_DESTROYED_MODIFIER
            rolls += 1                                   # one roll per leg (p.110)
            config.log(f"PSR trigger: {new_actuators} leg actuator(s) destroyed at {loc} this phase "
                       f"-> {new_actuators * LEG_ACTUATOR_DESTROYED_MODIFIER:+d}, one roll.")

    new_gyro_hits = mech.gyro_hits - snap["gyro_hits"]
    if new_gyro_hits > 0:
        if mech.gyro_hits >= 2:
            # Reachable only with config.FIGHT_TO_THE_DEATH (otherwise is_destroyed()
            # returned True at the top): gyro destroyed -> automatic fall (p.98).
            automatic_fall = True
            config.log("PSR trigger: Gyro destroyed this phase -> automatic fall.")
        else:
            modifier += GYRO_HIT_MODIFIER
            rolls += 1
            config.log(f"PSR trigger: Gyro hit this phase -> {GYRO_HIT_MODIFIER:+d}.")

    for reason, mod in forced_triggers:
        modifier += mod
        rolls += 1
        config.log(f"PSR trigger: {reason} -> {mod:+d}.")

    if not (rolls or automatic_fall):
        return

    modifier += preexisting_modifier(mech) + special_case_modifier(mech)

    if automatic_fall:
        config.log("Automatic fall this phase.")
        resolve_fall(mech, cause="automatic fall")
        return

    # HELP(pilot_consciousness.attack_phase_auto_fail)
    # Daniel, 2026-07-17: "any subsequent piloting skill rolls will
    # automatically fail" once every crew member is unconscious - no roll.
    # Shutdown (2026-10-19, Core Rulebook p.105): "Any PSR required of a
    # standing shutdown 'Mech fails automatically" - same auto-fail path.
    if all_crew_unconscious(mech) or mech.shutdown:
        why = "shut down" if mech.shutdown else "all crew unconscious"
        config.log(f"{why.capitalize()} - Attack Phase PSR auto-fails.")
        resolve_fall(mech, cause=f"auto-fail ({why})")
        return

    if not roll_psrs(mech, rolls, modifier, "Attack Phase PSR"):
        resolve_fall(mech, cause="failed Attack Phase PSR")


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
