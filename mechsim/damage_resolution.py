"""
"What happens TO a mech" - damage application, critical hit resolution, and
explosions. Everything here takes a `mech` (a mech_state.BattleMech instance)
as an explicit first argument rather than being a method on the class - see
mech_state.py's module docstring for why.

This is the highest-churn module in the project going forward - the CASE
bug fix and all armor/damage-type work (Patchwork, Hardened, Reactive,
Modular Armor - see ARCHITECTURE_PROPOSAL.md sections 3-4) land here and in
the not-yet-built armor_rules.py, which this module will call into.

CASE FIX (2026-07-07, Claude): get_case_tier() previously did a literal
string check ("CASE" in slots / "CASE II" in slots) that only matched the
hardcoded fixture mech, which writes bare strings into its crit lists. Real
parsed mechs resolve CASE/CASE II/Prototype CASE through equipment.json's
alias map (see equipment.py's lookup_equipment()) and always get a real
Equipment instance instead, so the old check silently never fired - CASE
protection never applied to any real mech. Root-caused and confirmed via a
real .mtf file with "ISCASEII". Fixed by scanning for Equipment instances
and checking normalized .name against a hardcoded tier whitelist (Daniel's
call - not a new equipment.json field, same pattern as
PLAIN_STRING_CRIT_INELIGIBLE in equipment.py). No changes made to
equipment.py, mtf_parser.py, or equipment.json for this fix.

KNOWN FOLLOW-UP (not yet built): Clan mechs get CASE for free on every
location per RAW, without it ever appearing as a .mtf crit-slot line or a
tech_base field the parser currently reads. Needs mtf_parser.py to detect
Clan tech base and inject an implicit 13th-slot CASE II presence per
location - get_case_tier() as written will handle it fine once that
implicit Equipment instance (or equivalent flag) exists, no further change
needed here.

STAGE 3/4 (2026-07-12, Claude): apply_damage's structure-damage step now
routes through armor_rules._consume_structure (Reinforced/Composite) instead
of flat subtraction, and check_critical takes a `modifier` param
(Hardened/Anti-Penetrative Ablation/Reinforced - armor_rules.crit_roll_modifier).
apply_explosion's check_critical call only gets the blanket -1 Reinforced
component - explosion damage bypasses armor, so there's no well-defined
"this hit's own armor consumption" to gate the -2 against; left at 0 pending
further clarification rather than guessed. Explosion's structure consumption
itself is UNCHANGED - still flat 1:1, not routed through _consume_structure
(see armor_rules.py's docstring).

CORRECTED 2026-07-13 (Daniel/Claude): apply_damage's own struct-damage-
triggered check_critical call, and sim_runner.py's floating-TAC crit check,
both now gate the -2 armor component on this hit's POST-consumption armor
value, not the pre-hit value used in the original 2026-07-12 pass. Crits are
checked AFTER armor/structure consumption in this sim's sequencing, so a hit
that drains a location's last armor point no longer gets the -2 on its own
resulting crit check(s) - see armor_rules.crit_roll_modifier's docstring for
the corrected rule.

2026-07-14 (Claude, Daniel's request), two additions:
- Manual crit-slot picking: resolve_critical() now prints the eligible-slot
  pool and calls config.pick_number() to choose among them whenever there's
  more than one candidate (a pool of 1 still auto-picks it, nothing to
  choose). Same self-gating shape as MANUAL_ROLLS/roll_2d6() - random unless
  config.MANUAL_ROLLS is True. See config.py's HELP(manual_crit_pick).
- Destroyed-slot identity retention: resolve_slot_hit() and
  mark_all_crits_destroyed() now record each slot's name (and, for
  Equipment, its instance id - for shared-instance grouping) into
  mech.destroyed_slot_info BEFORE overwriting the cell with "DESTROYED".
  Display-only - sim_runner.print_record_sheet() reads this to show what a
  destroyed slot used to be instead of just the bare sentinel. No change to
  is_crit_target/resolve_critical's pool-building or any other logic that
  reads "DESTROYED" as a sentinel - see mech_state.py's HELP(record_sheet.destroyed_slot_info).
"""

import math

import re

import config
import armor_rules
from equipment import Equipment, is_crit_target
from mech_state import ArmorType, DamageType, display_crits, is_destroyed, \
    compute_walk_mp, compute_jump_mp, compute_mechanical_jump_booster_mp, \
    compute_running_mp, mark_consciousness_check_pending, compute_heat_dissipation

# HELP(leg_actuator.tracking)
# Bare-string crit-slot names (mtf_parser.py's ANATOMY_COMPONENTS, confirmed
# verbatim against a real .mtf export) that count as a "leg actuator" for
# TMM's walking-MP penalty (Daniel, 2026-07-12: Hip/Upper/Lower/Foot all
# apply a flat -1 each - no RAW Hip-halves-MP special case). Counted in
# resolve_slot_hit at the moment the slot is destroyed, into
# mech.destroyed_leg_actuators - see that field's docstring in mech_state.py
# for why this can't be done by re-scanning mech.crits after the fact.
LEG_ACTUATOR_NAMES = ("Hip", "Upper Leg Actuator", "Lower Leg Actuator", "Foot Actuator")

# ---------------------------------------------------------------------------
# TMM - Target Movement Modifier. Table itself is a direct, unchanged port
# from the vehicle sim's damage_resolution.tmm_from_mp (Daniel, 2026-07-12:
# "Tmm table is the same"). compute_tmm's INPUTS are entirely mech-specific
# (mech_state.compute_walk_mp/compute_jump_mp - leg-actuator/quad-rule walk
# MP and jump-jet-instance-loss jump MP - see those functions' docstrings),
# not a port of the vehicle sim's motive-damage-table-driven cruise_mp. No
# immobilized/-4 case here (unlike the vehicle sim) - this sim has no
# partial "alive but immobilized" mech state to represent; a fully leg-
# destroyed mech is already handled by is_destroyed.
# ---------------------------------------------------------------------------

def tmm_from_mp(mp):
    if mp <= 2:
        return 0
    elif mp <= 4:
        return 1
    elif mp <= 6:
        return 2
    elif mp <= 9:
        return 3
    elif mp <= 17:
        return 4
    else:
        return 5


def compute_tmm(mech):
    """TMM is the higher of the mech's Running-MP-derived value or its
    Jump-MP-derived value this turn (Daniel: "TMM is determined by whichever
    mode generates the highest value this turn") - same "take the max"
    pattern as the vehicle sim's flank-vs-jump comparison. Running MP comes
    from mech_state.compute_running_mp (walk MP * 1.5 rounded up, same
    convention as the vehicle sim's flank_mp, minus 1/floor 1 if Hardened
    armor is on any leg - see HELP(running_mp.hardened_leg_penalty)),
    computed fresh off compute_walk_mp's CURRENT (damage-adjusted) value each
    call, not base_walk_mp. Jumping gets the usual RAW +1 TMM bonus on top
    of its own MP-derived value, same as the vehicle sim's jump_mp floor.

    HELP(movement_mode.tracking) (Daniel, 2026-07-16): also sets
    mech.movement_mode_this_turn ("running"/"jump") to whichever track
    produced the winning TMM, for piloting_rolls.check_movement_psr's
    Movement Phase PSR trigger. Only switches on strict '>' at each
    comparison, so a tie always leaves "running" in place (Daniel: "it has
    fewer triggers"). Mechanical Jump Booster counts as "jump" if it wins,
    same as standard jump jets (Daniel's confirmation - still a jumping
    movement type for PSR purposes)."""
    running_mp = compute_running_mp(mech)
    tmm = tmm_from_mp(running_mp)
    mech.movement_mode_this_turn = "running"

    jump_mp = compute_jump_mp(mech)
    if jump_mp > 0:
        jump_tmm = tmm_from_mp(jump_mp) + 1
        if jump_tmm > tmm:
            tmm = jump_tmm
            mech.movement_mode_this_turn = "jump"

    # HELP(compute_tmm.mechanical_jump_booster)
    # Separate MP track (Daniel, 2026-07-13: standard jump jets and Mechanical
    # Jump Booster can both be present but never combine into one MP total -
    # each independently compared here, best value wins each round).
    # base_mechanical_jump_booster_mp == 0 skips this branch entirely for a
    # mech that doesn't have the system (Daniel's explicit ask - no per-round
    # cost when absent). Gets the same RAW "+1 for jumping this turn" TMM
    # bonus as standard jump MP - Daniel confirmed 2026-07-13.
    if mech.base_mechanical_jump_booster_mp > 0:
        booster_mp = compute_mechanical_jump_booster_mp(mech)
        if booster_mp > 0:
            booster_tmm = tmm_from_mp(booster_mp) + 1
            if booster_tmm > tmm:
                tmm = booster_tmm
                mech.movement_mode_this_turn = "jump"

    return tmm


# ---------------------------------------------------------------------------
# Cluster Hits Table - Multi-Attack Turn Phase (2026-07-14, Daniel/Claude).
# Table DATA lives in config.CLUSTER_HITS_TABLE (Daniel's source, see that
# module's HELP(cluster_hits_table) comment) - this is just the lookup used
# by sim_runner.resolve_weapon_attack() for each CLUSTER_TABLE=True
# ATTACK_TABLE row.
# ---------------------------------------------------------------------------

def cluster_hits_count(shots, roll):
    """Number of individual submunitions/shots that connect, given a weapon's
    Cluster Hits Table column (`shots` = TABLE_COLUMN from an ATTACK_TABLE row -
    HELP(attack_table.table_column) in config.py - NOT derived from MAX_DAMAGE //
    CLUSTER_SIZE; those are separate fields as of the 2026-07-17 cluster-math
    fix, see DESIGN_NOTES_mech.md#cluster_table_column) and the (already
    CLUSTER_HIT_MODIFIER-adjusted, clamped >=2) 2d6 cluster roll. Fails loudly -
    ValueError - if `shots` isn't one of config.CLUSTER_HITS_TABLE's columns
    (1-30, then 40) rather than guessing/interpolating; extend the table in
    config.py instead. Caller (sim_runner.resolve_weapon_attack) converts the
    returned count into damage groups - this function only does the table
    lookup."""
    row = config.CLUSTER_HITS_TABLE.get(roll)
    if row is None:
        raise ValueError(f"No Cluster Hits Table row for a roll of {roll} - table only covers rolls "
                          f"{sorted(config.CLUSTER_HITS_TABLE)}.")
    if shots not in row:
        raise ValueError(f"No Cluster Hits Table column for {shots} shots - table only covers "
                          f"{sorted(row)} shot-columns. Extend config.CLUSTER_HITS_TABLE rather than guessing.")
    return row[shots]


TRANSFER_MAP = {
    "Left Arm": "Left Torso", "Right Arm": "Right Torso",
    "Left Leg": "Left Torso", "Right Leg": "Right Torso",
    "Center Leg": "Center Torso",
    "Left Torso": "Center Torso", "Right Torso": "Center Torso",
    # Quad: all four legs transfer into their matching torso exactly like an
    # arm/leg would on a biped - same relationship, different location names.
    "Front Left Leg": "Left Torso", "Front Right Leg": "Right Torso",
    "Rear Left Leg": "Left Torso", "Rear Right Leg": "Right Torso",
}

NON_TORSO_LOCATIONS = ("Head", "Left Arm", "Right Arm", "Left Leg", "Right Leg", "Center Leg",
                       "Front Left Leg", "Front Right Leg", "Rear Left Leg", "Rear Right Leg")


def mark_all_crits_destroyed(mech, location):
    """Mark slots destroyed and count special components. Equipment slots
    just go inert here - any explosion chance was already resolved (or
    discarded) by the Step-5 crit roll before this gets called.

    JUMP JET FIX (2026-07-13, Claude): this sweep bypasses resolve_slot_hit
    entirely (it's a bulk "location destroyed, everything in it goes inert"
    pass, not a per-slot crit resolution), so it previously never checked
    Equipment slots for is_jump_jet() the way resolve_slot_hit does - a jump
    jet housed in a location that gets wiped via structure damage (or a
    roll-of-12 location-blown-off result) was marked "DESTROYED" without
    ever being added to mech.destroyed_jump_jet_ids, so compute_jump_mp()
    never reflected the loss. See DESIGN_NOTES_mech.md#jump_jet.location_wipe_gap."""
    if location not in mech.crits:
        return
    for i in range(len(mech.crits[location])):
        slot = mech.crits[location][i]
        if slot in ("DESTROYED", "-Empty-"):
            continue
        already_lost = (location, i) in breached_slots(mech)      # its effects already counted (a breach)
        # HELP(record_sheet.destroyed_slot_info)
        mech.destroyed_slot_info[(location, i)] = (
            {"name": slot.name, "instance_id": id(slot)} if isinstance(slot, Equipment)
            else {"name": slot, "instance_id": None})
        mech.crits[location][i] = "DESTROYED"
        if not already_lost:
            _slot_loss_effects(mech, location, slot, "destruction")
    config.log(f"  All critical slots in {location} marked DESTROYED.")


def breached_slots(mech):
    """{(location, slot index)} put out of action by a hull breach (Core p.127,
    2026-10-21): their effects are already counted, but the slot is still
    there - it can absorb critical hits, and ammunition in it can explode."""
    return mech.__dict__.setdefault("breached_slot_set", set())


def mark_location_nonfunctional(mech, location, why="breach"):
    """Hull breach (Core p.127, 2026-10-21): "All components in a breached
    location that can take critical hits become nonfunctional: apply the
    gameplay results of each slot in that location being destroyed ... these
    effects are not critical hits: explosive slots do not explode due to
    breaches, and nonfunctional slots can still absorb critical hits."
    Each slot is recorded in destroyed_slot_info (so weapons, actuators,
    sensors and ammo feeds read as lost) and its effects applied once, but the
    slot stays in mech.crits."""
    if location not in mech.crits:
        return
    for i, slot in enumerate(mech.crits[location]):
        if slot in ("DESTROYED", "-Empty-") or (location, i) in breached_slots(mech):
            continue
        mech.destroyed_slot_info[(location, i)] = (
            {"name": slot.name, "instance_id": id(slot)} if isinstance(slot, Equipment)
            else {"name": slot, "instance_id": None})
        breached_slots(mech).add((location, i))
        _slot_loss_effects(mech, location, slot, why)


def _slot_loss_effects(mech, location, slot, why):
    """The gameplay results of losing one slot (jump jets, heat sinks, jump
    boosters, partial wing, engine / gyro / cockpit, hip) - shared by a
    location's destruction and a hull breach."""
    if isinstance(slot, Equipment):
        if is_jump_jet(slot) and id(slot) not in mech.destroyed_jump_jet_ids:
            mech.destroyed_jump_jet_ids.add(id(slot))
            config.log(f"    Jump jet destroyed ({slot.name}) from {location} {why} - "
                       f"jump MP reduced (now {compute_jump_mp(mech)}).")
        if is_heat_sink(slot) and id(slot) not in mech.destroyed_heat_sinks:
            mech.destroyed_heat_sinks[id(slot)] = heat_sink_units(slot)
            config.log(f"    Heat sink destroyed ({slot.name}) from {location} {why} - "
                       f"heat dissipation reduced (now {compute_heat_dissipation(mech)}).")
        if is_mechanical_jump_booster(slot) and not mech.mechanical_jump_booster_disabled:
            mech.mechanical_jump_booster_disabled = True
            config.log(f"    Mechanical Jump Booster disabled (system-wide) from {location} "
                       f"{why} - jump booster MP now {compute_mechanical_jump_booster_mp(mech)}.")
        if is_partial_wing(slot) and mech.partial_wing_active:
            mech.partial_wing_active = False
            config.log(f"    Partial Wing disabled (system-wide) from {location} "
                       f"{why} - jump MP now {compute_jump_mp(mech)}.")
    elif slot == "Engine":
        mech.engine_hits += 1
        config.log(f"    Engine hit ({mech.engine_hits}/3) from {location} {why}.")
    elif slot == "Gyro":
        mech.gyro_hits += 1
        config.log(f"    Gyro hit ({mech.gyro_hits}/2) from {location} {why}.")
    elif slot == "Cockpit":
        mech.cockpit_hit = True
        config.log(f"    Cockpit destroyed from {location} {why}.")
    elif slot == "Hip" and location in mech.leg_locations:
        # HELP(hip_actuator.tracking) - mirrors the jump-jet location-wipe
        # gap fix: a bulk location wipe (structure destroyed / roll-of-12
        # limb-blown-off) must also flag the Hip loss, or the Movement
        # Phase running-mode PSR trigger silently misses it. NOTE: this
        # function does not increment destroyed_leg_actuators on a bulk
        # wipe (pre-existing gap, out of scope here) - harmless for PSR
        # purposes since a fully-destroyed leg already satisfies every
        # trigger/modifier check below via mech.locations[loc]["destroyed"].
        mech.destroyed_hip_locations.add(location)
        config.log(f"    Hip specifically destroyed at {location} from {location} {why}.")


def apply_damage(mech, location, damage, armor_field="armor", damage_type=DamageType.BALLISTIC):
    """damage_type drives armor_rules.py's damage-type x armor-type dispatch
    (Vehicle Sim -> Mech Sim Gap Analysis, Stage 1-2). Structure consumption
    stays flat 1:1 (Stage 3, out of scope this pass) - only the armor step
    below routes through armor_rules."""
    remaining = damage
    current = location
    current_armor_field = armor_field
    config.log(f"{damage} damage ({damage_type.name}) incoming to {location} ({armor_field}).")
    while remaining > 0 and current is not None:
        if mech.locations[current]["destroyed"]:
            nxt = TRANSFER_MAP.get(current)
            config.log(f"  {current} already destroyed - damage transfers to {nxt or 'nowhere (attack finished)'}.")
            current = nxt
            current_armor_field = "armor"
            continue

        loc = mech.locations[current]
        armor_key = current_armor_field if current_armor_field in loc else "armor"

        # Re-engineered (Holy) damage ignores armor-type properties entirely -
        # math proceeds as if this location's armor were STANDARD.
        armor_type = ArmorType.STANDARD if damage_type == DamageType.REENGINEERED \
            else mech.armor_type.get(current, ArmorType.STANDARD)
        incoming_dmg = remaining
        armor_pool_before = loc[armor_key]
        effective_dmg = armor_rules.effective_damage(armor_type, damage_type, incoming_dmg, armor_pool_before)
        armor_destroyed, struct_incoming = armor_rules._consume_armor(
            armor_type, damage_type, effective_dmg, armor_pool_before)
        loc[armor_key] = max(0, armor_pool_before - armor_destroyed)

        struct_before = loc["structure"]
        struct_dmg = 0
        struct_overflow = 0
        if struct_incoming > 0:
            struct_dmg, struct_overflow = armor_rules._consume_structure(
                mech.structure_type, struct_incoming, struct_before)
            loc["structure"] = max(0, struct_before - struct_dmg)
        remaining = struct_overflow

        reduced_note = f" (pre-armor damage reduced {incoming_dmg} -> {effective_dmg:g})" if effective_dmg != incoming_dmg else ""
        msg = (f"  [{armor_type.name}/{damage_type.name}]{reduced_note} {armor_destroyed:g} armor pts destroyed at "
               f"{armor_key} ({armor_pool_before:g} -> {loc[armor_key]:g} remaining).")
        if struct_dmg > 0:
            msg += (f" {struct_dmg:g} damage applied to structure [{mech.structure_type.name}] "
                    f"({struct_before:g} -> {loc['structure']:g}/{mech.max_structure[current]} remaining).")
        config.log(msg)

        destroyed_this_hit = False
        # HELP(zero_damage_crit_gate)
        if struct_dmg > 0:
            destroyed_this_hit = loc["structure"] <= 0
            # Gate uses loc[armor_key] (the armor this location has AFTER
            # this hit's own consumption, computed above), not
            # armor_pool_before - crits are checked after armor/structure
            # damage is applied, so a hit that uses up the location's last
            # point of armor does NOT get the -2 on its own resulting crit
            # check. See armor_rules.crit_roll_modifier's docstring
            # (Daniel, 2026-07-13 correction).
            modifier = armor_rules.crit_roll_modifier(
                mech.structure_type, armor_type, armor_present=loc[armor_key] > 0)
            check_critical(mech, current, destroyed_this_hit, modifier=modifier)

        # Hull breach check (2026-10-21, Core p.127): an underwater location that
        # takes damage rolls for a breach. The board's water is the integration's
        # (INTEGRATION__water); nothing is rolled on dry land.
        if not destroyed_this_hit and (armor_destroyed > 0 or struct_dmg > 0) and not is_destroyed(mech):
            import INTEGRATION__water as water
            water.check_breach(mech, current)

        if destroyed_this_hit:
            loc["structure"] = 0
            loc["destroyed"] = True
            config.log(f"  {current} DESTROYED!")
            mark_all_crits_destroyed(mech, current)
            child = mech.side_torso_child.get(current)
            if child:
                mech.locations[child]["destroyed"] = True
                mech.locations[child]["structure"] = 0
                config.log(f"  {child} also destroyed (side torso rule).")
                mech.__dict__.setdefault("severed_limbs", []).append(child)   # falls off: a club (p.79)
                mark_all_crits_destroyed(mech, child)
            nxt = TRANSFER_MAP.get(current)
            config.log(f"  {remaining} damage remains, transfers to {nxt or 'nowhere (attack finished)'}.")
            current = nxt
            current_armor_field = "armor"

        if is_destroyed(mech):
            return


def check_critical(mech, location, location_destroyed=False, modifier=0):
    """modifier: Hardened/Anti-Penetrative Ablation (-2, gated on this hit's
    pre-consumption armor - see armor_rules.crit_roll_modifier) and/or
    Reinforced structure (-1, blanket), stacking. Clamped so the modified
    roll never drops below 2 (2d6's own floor), same as the vehicle sim."""
    if location_destroyed:
        if not any(isinstance(s, Equipment) and s.is_explosive and not s.exploded
                   for s in mech.crits[location]):
            config.log(f"  {location} destroyed with no live explosive components - no critical roll.")
            return

    raw_roll = config.roll_2d6(prompt="  Critical hit roll")
    roll = max(2, raw_roll + modifier)
    mod_note = f" ({raw_roll} {modifier:+d})" if modifier else ""
    config.log(f"  Check for possible critical. Roll a {roll}{mod_note}.")
    if roll < 8:
        config.log(f"    No critical hit.")
        return

    if roll == 12 and not location_destroyed:
        if location in NON_TORSO_LOCATIONS and _armored_joint_absorbs(mech, location):
            return
        if location in NON_TORSO_LOCATIONS:
            config.log(f"    Roll of 12: {location} blown off / destroyed!")
            # 2026-10-20: a limb blown off lies in the mech's hex - a club (Core p.79, INTEGRATION__clubs)
            mech.__dict__.setdefault("severed_limbs", []).append(location)
            mech.locations[location]["destroyed"] = True
            mech.locations[location]["structure"] = 0
            mark_all_crits_destroyed(mech, location)
            return
        else:
            config.log(f"    Roll of 12 on torso: rolling 3 critical hits instead of destruction.")
            count = 3
    else:
        count = 1 if roll < 10 else (2 if roll < 12 else 3)

    config.log(f"    {count} critical hit(s).")
    for i in range(1, count + 1):
        resolve_critical(mech, location, explosive_only=location_destroyed, idx=i, total=count)


def _armored_joint_absorbs(mech, location):
    """Core p.207: an armored shoulder / hip that hasn't taken a hit yet stops
    a limb from being blown off - that slot just loses its component armor.
    Returns True if it did."""
    for slot_idx, slot in enumerate(mech.crits[location]):
        if slot in ("Shoulder", "Hip") and (location, slot_idx) in getattr(mech, "armored_slots", ()):
            mech.armored_slots.discard((location, slot_idx))
            config.log(f"    Roll of 12: {location} would be blown off - its armored {slot} stops it and "
                       f"loses its component armor (p.207).")
            return True
    return False


def resolve_critical(mech, location, explosive_only, idx, total):
    if explosive_only:
        pool = [i for i, s in enumerate(mech.crits[location])
                if isinstance(s, Equipment) and s.is_explosive and not s.exploded]
    else:
        pool = [i for i, s in enumerate(mech.crits[location]) if is_crit_target(s)]

    if pool:
        # HELP(manual_crit_pick)
        if len(pool) == 1:
            slot_idx = pool[0]
        else:
            if config.VERBOSE:
                print(f"  Critical hit pool at {location}:")
                for pick_num, candidate_idx in enumerate(pool, start=1):
                    candidate = mech.crits[location][candidate_idx]
                    display = candidate.name if isinstance(candidate, Equipment) else candidate
                    print(f"    {pick_num}: {display} (slot {candidate_idx + 1})")
            choice = config.pick_number(len(pool), prompt="  Pick slot to hit")
            slot_idx = pool[choice - 1]
        slot = mech.crits[location][slot_idx]
        if (location, slot_idx) in getattr(mech, "armored_slots", ()):
            # Armored component (Core p.207, 2026-10-21): the slot's armor absorbs the hit -
            # the item doesn't count as hit. Only attacks' crits come here (MASC /
            # supercharger crits call resolve_slot_hit directly: armor can't stop those).
            mech.armored_slots.discard((location, slot_idx))
            config.log(f"    {idx}/{total} Criticals: {getattr(slot, 'name', slot)} slot hit - its component "
                       f"armor absorbs it, no effect (p.207).")
            return
        resolve_slot_hit(mech, location, slot_idx, slot, idx, total)
        return

    if explosive_only:
        config.log(f"    {idx}/{total} Criticals: no live explosive component available - discarded.")
        return

    # Pool is empty right now. Whether that discards or transfers depends on whether
    # this location was ALREADY fully cratered at the START of this round (fixed
    # snapshot from mech_state.snapshot_round_capability(), not rechecked crit-by-crit).
    if mech.round_capable.get(location, True):
        config.log(f"    {idx}/{total} Criticals: {location} critical slots exhausted during this "
            f"round - discarded (no transfer).")
        return

    nxt = TRANSFER_MAP.get(location)
    config.log(f"    {idx}/{total} Criticals: {location} was already fully cratered at the start of "
        f"this round - transfers to {nxt or 'nowhere'}.")
    if nxt:
        resolve_critical(mech, nxt, explosive_only=False, idx=idx, total=total)


def resolve_slot_hit(mech, location, slot_idx, slot, idx, total):
    if (location, slot_idx) in breached_slots(mech):
        # A breached slot (Core p.127) still absorbs the hit: its effects were
        # counted at the breach; ammunition in it still explodes, other
        # explosive gear doesn't ("only explode if active").
        mech.crits[location][slot_idx] = "DESTROYED"
        config.log(f"    {idx}/{total} Criticals: {getattr(slot, 'name', slot)} slot hit (already breached).")
        if isinstance(slot, Equipment) and slot.category == "ammo" and slot.is_explosive and not slot.exploded:
            slot.exploded = True
            apply_explosion(mech, slot, location)
        return
    if isinstance(slot, Equipment):
        component = slot
        if _autocannon_shrugs_off(mech, location, slot_idx, component, idx, total):
            return
        # HELP(record_sheet.destroyed_slot_info)
        mech.destroyed_slot_info[(location, slot_idx)] = {"name": component.name, "instance_id": id(component)}
        mech.crits[location][slot_idx] = "DESTROYED"
        config.log(f"    {idx}/{total} Criticals: {component.name} slot hit.")
        config.log(f"      Current crit slots in {location}: {display_crits(mech, location)}")
        if is_jump_jet(component) and id(component) not in mech.destroyed_jump_jet_ids:
            mech.destroyed_jump_jet_ids.add(id(component))
            config.log(f"      Jump jet destroyed ({component.name}) - jump MP reduced "
                       f"(now {compute_jump_mp(mech)}).")
        if is_heat_sink(component) and id(component) not in mech.destroyed_heat_sinks:
            mech.destroyed_heat_sinks[id(component)] = heat_sink_units(component)
            config.log(f"      Heat sink destroyed ({component.name}) - heat dissipation "
                       f"reduced (now {compute_heat_dissipation(mech)}).")
        if is_mechanical_jump_booster(component) and not mech.mechanical_jump_booster_disabled:
            mech.mechanical_jump_booster_disabled = True
            config.log(f"      Mechanical Jump Booster disabled (system-wide, all-or-nothing) "
                       f"- jump booster MP now {compute_mechanical_jump_booster_mp(mech)}.")
        if is_partial_wing(component) and mech.partial_wing_active:
            mech.partial_wing_active = False
            config.log(f"      Partial Wing disabled (system-wide, all-or-nothing) "
                       f"- jump MP now {compute_jump_mp(mech)}.")
        if component.is_explosive and not component.exploded:
            component.exploded = True
            apply_explosion(mech, component, location)
        elif component.is_explosive and component.exploded:
            config.log(f"      {component.name} already exploded - this slot destroyed, no further effect.")
    else:
        mech.destroyed_slot_info[(location, slot_idx)] = {"name": slot, "instance_id": None}
        mech.crits[location][slot_idx] = "DESTROYED"
        config.log(f"    {idx}/{total} Criticals: {slot} hit.")
        config.log(f"      Current crit slots in {location}: {display_crits(mech, location)}")
        if slot == "Engine":
            mech.engine_hits += 1
            config.log(f"      Engine hit ({mech.engine_hits}/3).")
        elif slot == "Gyro":
            mech.gyro_hits += 1
            config.log(f"      Gyro hit ({mech.gyro_hits}/2).")
        elif slot == "Cockpit":
            mech.cockpit_hit = True
            config.log(f"      Cockpit hit - instant kill condition set.")
        elif slot in LEG_ACTUATOR_NAMES and location in mech.leg_locations:
            mech.destroyed_leg_actuators[location] = mech.destroyed_leg_actuators.get(location, 0) + 1
            config.log(f"      Leg actuator hit at {location} "
                       f"({mech.destroyed_leg_actuators[location]} destroyed there) - "
                       f"walk MP now {compute_walk_mp(mech)}.")
            # HELP(hip_actuator.tracking)
            if slot == "Hip":
                mech.destroyed_hip_locations.add(location)
                config.log(f"      Hip specifically destroyed at {location} - "
                           f"running-mode Movement Phase PSR trigger now active.")


# Autocannon names (2026-10-20): AC, LB-X, Ultra, Rotary, Light and ProtoMech
# autocannons as MegaMek / equipment.json spell them ("ISAC5", "CLLBXAC10",
# "ISUltraAC5", "ISRotaryAC2", "ISLAC2", "CLProtoMechAC4", "Autocannon/10").
# Also the long forms some .mtf files use ("Clan LB 10-X AC", "Ultra AC/5").
_AUTOCANNON_NAME = re.compile(r"^(IS|CL|CLAN)?((LBX|ULTRA|ROTARY|PROTOMECH|LIGHT|L)?AC|AUTOCANNON)\d+P?$"
                              r"|^(IS|CL|CLAN)?LB\d+XAC$")


def is_autocannon(component):
    name = re.sub(r"\(.*?\)|[\s\-/]", "", component.name or "").upper()
    return bool(_AUTOCANNON_NAME.match(name))


def _autocannon_shrugs_off(mech, location, slot_idx, component, idx, total):
    """Core p.183 (2026-10-20): the first critical hit to an autocannon of any
    class does not destroy it - the slot is marked and can't take another crit,
    and a second crit to any OTHER slot of the weapon disables it. A one-slot
    autocannon needs two hits to that slot. Returns True if this crit was that
    first, harmless one (nothing else happens)."""
    if component.category != "weapon" or not is_autocannon(component):
        return False
    first_crits = mech.__dict__.setdefault("autocannon_crits", set())
    if id(component) in first_crits:
        return False                                  # second crit: destroyed as normal
    first_crits.add(id(component))
    if component.slots_occupied > 1:
        # The slot is used up, but the weapon is not (instance_id None: get_weapons still counts it).
        mech.destroyed_slot_info[(location, slot_idx)] = {"name": component.name, "instance_id": None}
        mech.crits[location][slot_idx] = "DESTROYED"
    config.log(f"    {idx}/{total} Criticals: {component.name} slot hit - an autocannon's first critical hit "
               f"doesn't destroy it (p.183); it still fires.")
    return True


# HELP(jump_jet.hardcoded_name_match)
def is_jump_jet(component):
    """Is this Equipment instance a jump jet (standard or Improved)? Same
    hardcoded-name-match approach as get_case_tier below - not a new
    equipment.json field, since Equipment.name holds the RAW .mtf text
    (post cosmetic-suffix-stripping, e.g. "Improved Jump Jet" or
    "ISJumpJet"), not a canonical form, and MegaMek's spelling varies by
    tech base/prefix. A normalized substring check on "JUMPJET" catches
    every variant seen so far ("Jump Jet", "ISJumpJet", "Improved Jump
    Jet", "ISImprovedJumpJet", ...) without needing to enumerate them."""
    normalized = component.name.replace(" ", "").replace("-", "").upper()
    return "JUMPJET" in normalized


# HELP(mechanical_jump_booster.detection)
def is_mechanical_jump_booster(component):
    """Normalized-substring match, same approach as is_jump_jet. Checked
    against "MECHANICALJUMPBOOSTER" - confirmed no collision with
    is_jump_jet's "JUMPJET" substring despite both containing "JUMP"
    (...BOOSTER never spells out ...JET)."""
    normalized = component.name.replace(" ", "").replace("-", "").upper()
    return "MECHANICALJUMPBOOSTER" in normalized


# HELP(partial_wing.detection)
def is_partial_wing(component):
    """Normalized-substring match, same approach as is_jump_jet/
    is_mechanical_jump_booster. Checked against "PARTIALWING" - confirmed no
    collision with "JUMPJET"/"MECHANICALJUMPBOOSTER". Used both for parse-
    time presence detection (mtf_parser.parse_mtf, scanning mech.crits after
    they're built) and for the all-or-nothing disable check at hit-time
    (below, and mark_all_crits_destroyed)."""
    normalized = component.name.replace(" ", "").replace("-", "").upper()
    return "PARTIALWING" in normalized


# HELP(heat_sink.hardcoded_name_match)
def is_heat_sink(component):
    """Normalized-substring match, same approach as is_jump_jet. Checked
    against "HEATSINK" - catches Heat Sink, ISDouble Heat Sink/CLDouble
    Heat Sink, 1/2 Compact Heat Sink(s), Laser Heat Sink, all without
    enumerating them.

    Radical Heat Sink System is explicitly EXCLUDED despite matching the
    "HEATSINK" substring (Daniel, 2026-08-04): despite its name it isn't a
    passive dissipation source - it's activatable equipment with its own
    risk mechanic, closer to a coolant pod. Not wired in at all yet, so it
    must not be picked up here as a side effect of the substring check."""
    normalized = component.name.replace(" ", "").replace("-", "").upper()
    return "HEATSINK" in normalized and "RADICAL" not in normalized


# HELP(heat_sink.hardcoded_name_match)
def heat_sink_units(component):
    """How many physical heat sinks does this ONE Equipment instance
    represent, for destroyed_heat_sinks bookkeeping? Always 1, except the
    bundled equipment.json "2 Compact Heat Sinks" entry, which is 2
    physical heat sinks packed into a single instance (Daniel, 2026-08-04:
    2 Compact Heat Sinks fit in 1 critical slot). Substring check on
    "2COMPACT" rather than an exact name match, same normalization
    approach as is_heat_sink."""
    normalized = component.name.replace(" ", "").replace("-", "").upper()
    return 2 if "2COMPACT" in normalized else 1


# HELP(weapon_list.partial_destruction)
def get_weapons(mech):
    """Every live weapon Equipment instance on this mech, right now - dedup'd
    by id() so a 2-slot weapon (e.g. Large Laser) isn't double-counted just
    because it appears twice in mech.crits[location].

    Partial-destruction subtlety (2026-08-05, found while building this):
    resolve_slot_hit() only overwrites the ONE hit slot index with the string
    "DESTROYED" - it does not touch the other slot indices still holding the
    same shared Equipment instance. So a naive scan of mech.crits would see a
    multi-slot weapon with 1 of 2 slots destroyed as still "alive" (found via
    its surviving slot), which is wrong - per BT rules a hit on ANY crit slot
    of a weapon destroys the whole weapon. mech.destroyed_slot_info already
    records {"name", "instance_id": id(component)} for every destroyed slot
    (see resolve_slot_hit), so this cross-checks every live-looking instance's
    id() against that record before counting it as a real weapon this turn -
    no change to damage_resolution's destruction mechanics needed, this just
    reads existing bookkeeping correctly.

    Returns a plain list of Equipment instances (category == "weapon" only).
    Does not distinguish ammo state, heat-scale effects, or anything else -
    just "which weapon objects can still theoretically fire.\""""
    destroyed_ids = {info["instance_id"] for info in mech.destroyed_slot_info.values()
                      if info["instance_id"] is not None}
    seen_ids = set()
    weapons = []
    for location in mech.crits:
        for slot in mech.crits[location]:
            if not isinstance(slot, Equipment):
                continue  # "DESTROYED" / "-Empty-" sentinel strings
            if slot.category != "weapon":
                continue
            if id(slot) in seen_ids:
                continue  # already counted this instance via an earlier slot
            seen_ids.add(id(slot))
            if id(slot) in destroyed_ids:
                continue  # some OTHER slot of this same instance was hit
            weapons.append(slot)
    return weapons


# HELP(case_tier.hardcoded_whitelist)
def get_case_tier(mech, location):
    """CASE/CASE II identity comes from the Equipment instance's .name (raw
    .mtf text, resolved via equipment.json's alias map - see equipment.py's
    lookup_equipment()), not a bare string. Real mechs never hit the
    PLAIN_STRING_CRIT_INELIGIBLE path in equipment.py; that path is
    fixture-only. Hardcoded whitelist here per Daniel's call - not a new
    equipment.json field. CASE II checked first (takes priority within a
    location) whether it's a single 13th-slot component or (once the Clan
    free-CASE parser change lands) an implicit component with no .mtf line
    at all. Prototype CASE (ISCASEPrototype) rules identically to standard
    CASE - same cap, folded into CASE_NAMES rather than given its own tier."""
    CASE_II_NAMES = {"ISCASEII", "CLCASEII", "IS CASE II", "CLAN CASE II"}
    CASE_NAMES = {"ISCASE", "CLCASE", "IS CASE", "CLAN CASE",
                  "ISCASEPROTOTYPE", "PROTOTYPE CASE"}

    slots = mech.crits[location]
    found_case = False
    for slot in slots:
        if not isinstance(slot, Equipment):
            continue
        name = slot.name.strip().upper()
        if name in CASE_II_NAMES:
            return "CASE II"
        if name in CASE_NAMES:
            found_case = True
    return "CASE" if found_case else None


EXPLOSION_IS_CAP = 20                              # Core p.96, no CASE
CASE_IS_CAP = {"CASE": 10, "CASE II": 1}           # p.96
CASE_ARMOR_CAP = 10                                # p.96: excess to (rear) armor, at most 10
CASE_II_CRIT_MODIFIER = -1                         # p.96: crit checks from the explosion


def apply_explosion(mech, component, location):
    """Internal explosion (Core pp.95-96, rewritten 2026-10-20): ammo bins
    (base damage = shots left x Damage Value, INTEGRATION__ammo) and explosive
    components (2 x slots) both come through here.

    Without CASE: damage goes to internal structure, bypassing armor, and
    transfers to the next location's structure; at most 20 structure damage in
    all, the rest negated. If the base damage was over 20, the location that
    took the 20th point, if it survived, loses all its armor (a torso: its rear
    armor).
    CASE / CASE II in the location the explosion starts in, or transfers into
    (handled as if it started there): at most 10 / 1 structure damage; if the
    damage reaching it is over that and the location survives, the excess goes
    to its armor (a torso: rear armor), at most 10; the rest is negated and
    nothing transfers. CASE II gives the explosion's crit checks -1.
    The MechWarrior takes 1 hit (p.117) either way."""
    mech.explosions += 1
    mech.pilot_hits += 1
    mark_consciousness_check_pending(mech)
    base = component.explosion_damage
    config.log(f"    {component.name} destroyed at {location} - EXPLOSION ({base} dmg)! "
        f"Pilot takes 1 hit ({mech.pilot_hits}/6).")

    remaining = min(base, EXPLOSION_IS_CAP)     # structure damage still to place (no-CASE cap)
    incoming = base                             # what reaches the current location (for CASE)
    current = location
    last_hit = None                             # the location that took the last point
    while remaining > 0 and current is not None:
        if mech.locations[current]["destroyed"]:
            nxt = TRANSFER_MAP.get(current)
            config.log(f"    {current} already destroyed - explosion transfers to {nxt or 'nowhere'}.")
            current = nxt
            continue

        loc = mech.locations[current]
        case_tier = get_case_tier(mech, current)
        if case_tier:
            _case_contains(mech, current, case_tier, incoming)
            return

        config.log(f"    Explosion reaches {current}. No CASE present - {remaining} damage to structure.")
        struct_dmg = min(remaining, loc["structure"])
        destroyed_this_hit = _explosion_structure(mech, current, struct_dmg, crit_modifier=0)
        if struct_dmg > 0:
            last_hit = current
        remaining -= struct_dmg
        incoming = remaining
        if is_destroyed(mech):
            return
        if remaining > 0 and destroyed_this_hit:
            nxt = TRANSFER_MAP.get(current)
            config.log(f"    {remaining} explosion damage remains, transfers to {nxt or 'nowhere'}.")
            current = nxt

    if base > EXPLOSION_IS_CAP and remaining == 0 and last_hit is not None \
            and not mech.locations[last_hit]["destroyed"]:
        _strip_armor(mech, last_hit, None, "base damage over 20 (p.96)")


def _case_contains(mech, location, case_tier, incoming):
    """CASE / CASE II in `location` (p.96): see apply_explosion."""
    loc = mech.locations[location]
    is_cap = CASE_IS_CAP[case_tier]
    struct_dmg = min(incoming, is_cap, loc["structure"])
    config.log(f"    Explosion reaches {location}. {case_tier} present - at most {is_cap} structure damage.")
    destroyed = _explosion_structure(mech, location, struct_dmg,
                                     crit_modifier=CASE_II_CRIT_MODIFIER if case_tier == "CASE II" else 0)
    excess = incoming - is_cap
    if excess > 0 and not destroyed and not is_destroyed(mech):
        _strip_armor(mech, location, min(excess, CASE_ARMOR_CAP), f"{case_tier} vents the excess")
    config.log(f"    {case_tier} contains the explosion. No further transfer.")


def _explosion_structure(mech, location, struct_dmg, crit_modifier):
    """Explosion damage to `location`'s internal structure, its crit check
    and destruction. Returns True if the location was destroyed."""
    loc = mech.locations[location]
    loc["structure"] -= struct_dmg
    destroyed_this_hit = loc["structure"] <= 0
    config.log(f"    {struct_dmg} structure damage taken ({loc['structure']}/{mech.max_structure[location]} remaining).")
    if struct_dmg > 0:
        # Structure-only modifier (blanket -1 if Reinforced). Armor
        # component intentionally omitted: explosion damage bypasses
        # armor entirely, so there's no "this hit's own armor
        # consumption" to gate the -2 against the way apply_damage's
        # own struct-damage path can - see armor_rules.crit_roll_modifier's
        # docstring. Flagged, not silently assumed either way.
        # HELP(crit_roll_modifier.explosion_omission)
        modifier = armor_rules.crit_roll_modifier(mech.structure_type) + crit_modifier
        check_critical(mech, location, destroyed_this_hit, modifier=modifier)
    if destroyed_this_hit:
        loc["structure"] = 0
        loc["destroyed"] = True
        config.log(f"    {location} DESTROYED! (explosion)")
        mark_all_crits_destroyed(mech, location)
        child = mech.side_torso_child.get(location)
        if child:
            mech.locations[child]["destroyed"] = True
            mech.locations[child]["structure"] = 0
            config.log(f"  {child} also destroyed (side torso rule).")
            mech.__dict__.setdefault("severed_limbs", []).append(child)   # falls off: a club (p.79)
            mark_all_crits_destroyed(mech, child)
    return destroyed_this_hit


def _strip_armor(mech, location, amount, why):
    """Explosion damage to armor (p.96): a torso's REAR armor, otherwise its
    armor. amount None = all of it."""
    loc = mech.locations[location]
    field = "rear_armor" if "rear_armor" in loc else "armor"
    lost = loc[field] if amount is None else min(amount, loc[field])
    loc[field] -= lost
    config.log(f"    {why}: {location} loses {lost} {field.replace('_', ' ')} ({loc[field]} left).")
