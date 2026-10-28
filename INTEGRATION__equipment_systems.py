"""
INTEGRATION__equipment_systems.py  (NEW 2026-10-19, Claude - Pile 2 rules, Pile 4 defaults)

Activated / Escalating Failure equipment that feeds heat, movement and
to-hit: stealth systems, coolant pods, radical heat sinks, MASC,
superchargers, triple-strength myomer, torso-mounted cockpits. The heat
side of these (stealth heat, extra cooling, TSM activation) is applied by
INTEGRATION__heat; this module finds the equipment, tracks its state and
holds the rules that aren't heat.

Source: BattleTech Core Rulebook (Daniel's rules index). Pages cited per
rule. Player choices are Daniel's defaults (2026-10-19): activated systems
are always on; radical heat sinks, MASC and superchargers run a 1-turn-on /
1-turn-off cycle (config.ESCALATING_CYCLE_ON_ODD_TURNS); TSM is driven by
min_heat (config.TSM_MIN_HEAT); coolant pods are used when heat would stay
above min_heat (see INTEGRATION__heat._extra_cooling).

  - Escalating Failure (p.180): roll 2D6 each turn of use against 3+ / 5+ /
    7+ / 10+ / 11+ for the 1st / 2nd / 3rd / 4th / 5th+ consecutive turn;
    each turn NOT used steps the count back one. On a 1-on/1-off cycle the
    count never passes 1, so every roll needs 3+.
  - Stealth systems (pp.202, 209), active unless shut down (p.104):
      Chameleon LPS: 6 heat; attacks against it +1 at medium range, +2 at long.
      Null-Signature System: 10 heat; +1 medium / +2 long (stacks with LPS).
      Stealth armor: 10 heat; +1 medium / +2 long; needs a working ECM suite.
      Void-Signature System: 10 heat; needs a working ECM suite; attacks
        against it +3 / +2 / +1 / +0 when it moved 0 / 1-2 / 3-5 / 6+ hexes
        (0 hexes but some MP spent counts as 1); its own ranged attacks +1.
    Any destroyed slot destroys LPS / Null / Void (stealth armor isn't
    destroyed by crits). The "as if in hostile ECM" side effects are in
    INTEGRATION__electronics (2026-10-20: the mech's own Artemis is blocked,
    and no stealth system but the LPS lets its ECM jam); C3 and probes have
    nothing to act on in this sim.
  - Coolant pod (p.208): one per turn, at the start of the Heat Phase, +1
    cooling per active heat sink; each pod once per game. A critical hit on
    an UNUSED pod is a 2-point explosion (equipment.json), so a used pod
    stops being explosive. No effect in a turn the radical system is used.
  - Radical heat sink system (pp.208-209): Escalating Failure, at the start
    of the Heat Phase; success +1 cooling per working heat sink. Failure:
    no bonus and the system takes a crit - destroyed. Once destroyed: +1
    heat every turn the mech moves, +1 every turn it fires any weapon.
  - MASC / supercharger (p.204): Escalating Failure, rolled when movement is
    declared, before moving. Success: Running MP = 2 x Walking MP (2.5x,
    round up, with both). Failure: a critical-hit check (8-9: 1, 10-11: 2,
    12: 3 crits; reinforced-structure modifier ignored) after movement -
    MASC crits all go to one random leg (Kick Location Table, front/rear
    column: 1-3 right, 4-6 left) and never transfer; supercharger crits go
    to the upper-most undamaged centre-torso Engine slots, and a failed
    supercharger is destroyed either way. PSRs from that damage follow.
  - Triple-strength myomer (p.205): heat 9+ at the end of a turn -> next
    turn +2 Walking MP (Running recalculated), before heat penalties.
    (Its physical-attack doubling waits on physical combat.)
  - Torso-mounted cockpit (p.203): life support hits at heat 1-14 (1 hit)
    and 15+ (2 hits) instead of 10-19 / 20+ (INTEGRATION__heat). Its other
    rules (2026-10-21, mech_state): +1 to every PSR (a small cockpit too), no
    MechWarrior hit from head hits, the head's loss isn't fatal (later head
    hits re-rolled), sensor hits +2 / +4 to ranged attacks
    (attack_resolution.sensor_modifier) and +4 to physical attacks and PSRs
    once both head sensors or 3+ sensors are hit.

Not modeled: shutting a system off by choice, MASC/supercharger crits taken
mid-move. (ECM itself - jamming Artemis and Narc - is INTEGRATION__electronics.)
"""

from contextlib import contextmanager

import INTEGRATION__config as config
import INTEGRATION__stubs as stubs
import INTEGRATION__advanced_equipment as adv_equip
from equipment import Equipment, is_crit_target
from damage_resolution import resolve_slot_hit

# =============================================================================
# ==========================  RULE TABLES  ====================================
# =============================================================================
ESCALATING_FAILURE_AVOID = {1: 3, 2: 5, 3: 7, 4: 10}   # p.180; 5+ consecutive turns: 11
ESCALATING_FAILURE_AVOID_MAX = 11
ESCALATING_SYSTEMS = ("masc", "supercharger", "radical")

STEALTH_HEAT = {"chameleon": 6, "null_signature": 10, "stealth_armor": 10, "void_signature": 10}
RANGE_STEALTH_SYSTEMS = ("chameleon", "null_signature", "stealth_armor")   # +1 medium / +2 long each
RANGE_STEALTH_BONUS = {"short": 0, "medium": 1, "long": 2}
VOID_BONUS_BY_HEXES = ((6, 0), (3, 1), (1, 2), (0, 3))                     # hexes moved -> TN
VOID_OWN_ATTACK_MODIFIER = 1

TSM_ACTIVE_HEAT = 9                                     # p.205 (the +2 Walking MP is in mech_state.compute_walk_mp)
RUN_MULTIPLIER_BY_BOOSTERS = {0: 1.5, 1: 2.0, 2: 2.5}   # p.45 / p.204

# 2D6 critical-hit check (p.90): roll -> crits; 12 = limb blown off, which
# MASC treats as 3 crits and a torso (supercharger) already counts as 3.
def crits_for_roll(roll):
    if roll < 8:
        return 0
    return 1 if roll < 10 else (2 if roll < 12 else 3)


# =============================================================================
# ==========================  DETECTION  ======================================
# =============================================================================
def _norm(name):
    return name.replace(" ", "").replace("-", "").upper()


def _kind(slot):
    """Which system an Equipment crit slot belongs to (name match, same
    approach as damage_resolution.is_jump_jet), or None."""
    if not isinstance(slot, Equipment) or slot.category == "ammo":
        return None
    n = _norm(slot.name)
    if "MASC" in n:
        return "masc"
    if "SUPERCHARGER" in n:
        return "supercharger"
    if "RADICALHEATSINK" in n:
        return "radical"
    if "COOLANTPOD" in n:
        return "coolant_pod"
    if "BLUESHIELD" in n:
        return "blue_shield"
    if "CHAMELEON" in n:
        return "chameleon"
    if "NULLSIGNATURE" in n:
        return "null_signature"
    if "VOIDSIGNATURE" in n:
        return "void_signature"
    if "ECM" in n:
        return "ecm"
    if n in ("ISSTEALTH", "ISSTEALTHARMOR"):
        return "stealth_armor"
    if ("TSM" in n or "TRIPLESTRENGTHMYOMER" in n) and "INDUSTRIAL" not in n:
        return "tsm"
    return None


def attach_equipment(mech):
    """Once per battle per mech (via INTEGRATION__heat.attach_heat_traits):
    finds every system, keyed by kind -> list of Equipment instances."""
    found = {}
    seen = set()
    for slots in mech.crits.values():
        for slot in slots:
            kind = _kind(slot)
            if kind and id(slot) not in seen:
                seen.add(id(slot))
                found.setdefault(kind, []).append(slot)
    mech.equipment_systems = found
    mech.has_tsm = "tsm" in found or "TRIPLESTRENGTH" in _norm(getattr(mech, "myomer", "") or "")
    mech.has_stealth_armor = "stealth_armor" in found or "STEALTH" in _norm(getattr(mech, "armor_desc", "") or "")
    mech.torso_cockpit = "TORSO" in _norm(getattr(mech, "cockpit_type", "") or "")
    mech.escalating_turns = {k: 0 for k in ESCALATING_SYSTEMS}
    mech.systems_used_this_turn = set()
    mech.turn_number = 0
    mech.pfd_active = has_system(mech, "blue_shield") and stubs.stub_blue_shield(mech.side_name, "start")
    mech.pfd_turns_used, mech.pfd_failed = 0, False


def _destroyed_ids(mech):
    return {info["instance_id"] for info in mech.destroyed_slot_info.values() if info["instance_id"] is not None}


def has_system(mech, kind):
    return bool(mech.equipment_systems.get(kind))


def system_live(mech, kind):
    """True if the mech mounts `kind` and none of its slots is destroyed -
    a crit to any slot of the item destroys it (p.180)."""
    parts = mech.equipment_systems.get(kind)
    if not parts:
        return False
    dead = _destroyed_ids(mech)
    return not any(id(p) in dead for p in parts)


def ecm_live(mech):
    """A working ECM suite. equipment.json lists ECM suites as 1-slot items,
    so a 2-slot Guardian parses as two instances - treated as one system,
    like MASC, so losing either slot loses the suite (p.180)."""
    return system_live(mech, "ecm")


def destroy_system(mech, kind, why):
    """Mark the system's upper-most live slot destroyed (radical heat sink
    failure, failed supercharger) - recorded like any other destroyed slot."""
    parts = mech.equipment_systems.get(kind, [])
    for location, slots in mech.crits.items():
        for i, slot in enumerate(slots):
            if any(slot is p for p in parts):
                mech.destroyed_slot_info[(location, i)] = {"name": slot.name, "instance_id": id(slot)}
                slots[i] = "DESTROYED"
                config.log(f"    {mech.side_name}: {slot.name} in {location} destroyed ({why}).")
                return


# =============================================================================
# ==========================  ESCALATING FAILURE  =============================
# =============================================================================
def start_turn(mech, turn_number):
    mech.turn_number = turn_number
    mech.systems_used_this_turn = set()
    harjel_start_turn(mech)                    # HarJel II / III repair (p.208)


def cycle_on(mech, turn_number=None):
    """Daniel's 1-turn-on / 1-turn-off cycle for radical heat sinks, MASC
    and superchargers."""
    turn = mech.turn_number if turn_number is None else turn_number
    odd = turn % 2 == 1
    return odd if config.ESCALATING_CYCLE_ON_ODD_TURNS else not odd


def escalating_avoid_tn(consecutive_turns):
    return ESCALATING_FAILURE_AVOID.get(consecutive_turns, ESCALATING_FAILURE_AVOID_MAX)


def escalating_roll(mech, key, label):
    """One use of an Escalating Failure system (p.180). True = it works."""
    mech.escalating_turns[key] += 1
    mech.systems_used_this_turn.add(key)
    tn = escalating_avoid_tn(mech.escalating_turns[key])
    roll = config.roll_2d6(prompt=f"{label} escalating failure roll")
    ok = roll >= tn
    config.log(f"    {mech.side_name}: {label} (turn {mech.escalating_turns[key]} in a row) needs {tn}, "
               f"rolled {roll} - {'works' if ok else 'FAILS'}.")
    return ok


def end_turn(mech):
    """End Phase: every Escalating Failure system not used this turn steps
    its consecutive-use count back one (p.180)."""
    for key in ESCALATING_SYSTEMS:
        if key not in mech.systems_used_this_turn:
            mech.escalating_turns[key] = max(0, mech.escalating_turns[key] - 1)
    mech.systems_used_this_turn = set()
    harjel_end_turn(mech)                      # HarJel II / III repair (p.208)
    blue_shield_end_turn(mech)                 # Blue Shield failure check and switch (p.207)


# =============================================================================
# ==========================  STEALTH  ========================================
# =============================================================================
def active_stealth(mech):
    """Stealth systems switched on and working right now (always on by
    default; nothing works while shut down - p.104)."""
    if mech.shutdown or blue_shield_on(mech):
        return []                              # an active Blue Shield negates stealth (p.207)
    active = [k for k in ("chameleon", "null_signature") if system_live(mech, k)]
    if mech.has_stealth_armor and ecm_live(mech) and not adv_equip.active(mech):
        active.append("stealth_armor")        # modular armor stops it (TO:AUE p.93, 2026-10-27)
    if system_live(mech, "void_signature") and ecm_live(mech):
        active.append("void_signature")
    return active


def stealth_heat(mech):
    return sum(STEALTH_HEAT[k] for k in active_stealth(mech))


def range_stealth_bonus(target):
    """{bracket: TN bonus} for attacks against `target` - LPS, Null-Signature
    and stealth armor each add +1 at medium and +2 at long range."""
    count = sum(1 for k in active_stealth(target) if k in RANGE_STEALTH_SYSTEMS)
    return {bracket: count * bonus for bracket, bonus in RANGE_STEALTH_BONUS.items()}


def void_signature_modifier(target, hexes_moved=None, mp_spent=None):
    """TN bonus for every attack against a target with an active Void-
    Signature System, from how far it moved this turn (defaults: its actual
    move). 0 hexes with MP spent counts as 1."""
    if "void_signature" not in active_stealth(target):
        return 0
    hexes = target.move_fc if hexes_moved is None else hexes_moved
    spent = target.mp_spent if mp_spent is None else mp_spent
    if hexes == 0 and spent > 0:
        hexes = 1
    for threshold, bonus in VOID_BONUS_BY_HEXES:
        if hexes >= threshold:
            return bonus
    return 0


def own_attack_modifier(attacker):
    """An active Void-Signature System adds +1 to its own mech's ranged
    attacks; Taser interference +2 (TO:AUE p.158, 2026-10-27); TSEMP
    interference +2 and IMP missiles +1 / +2 (Interstellar Operations, 2026-10-28)."""
    import INTEGRATION__advanced_weapons as adv
    return ((VOID_OWN_ATTACK_MODIFIER if "void_signature" in active_stealth(attacker) else 0)
            + adv.own_attack_modifier(attacker))


# =============================================================================
# ==========================  COOLANT PODS / RADICAL  =========================
# =============================================================================
def unused_coolant_pods(mech):
    dead = _destroyed_ids(mech)
    return [p for p in mech.equipment_systems.get("coolant_pod", [])
            if id(p) not in dead and not getattr(p, "pod_used", False)]


def use_coolant_pod(mech):
    pod = unused_coolant_pods(mech)[0]
    pod.pod_used = True
    pod.is_explosive = False      # only an UNUSED pod explodes on a crit (p.208)
    pod.explosion_damage = 0
    return pod


def use_escalating(mech, label, turn_number=None, warn=False):
    """Whether the bot uses an Escalating Failure system this (or the given)
    turn - a STUB decision since 2026-10-20 (stubs.stub_escalating_use; its
    default is Daniel's cycle_on). warn=True only where the decision is made:
    movement declaration (MASC / supercharger) and the Heat Phase (radical)."""
    import INTEGRATION__stubs as stubs
    return stubs.stub_escalating_use(mech.side_name, label, cycle_on(mech, turn_number), warn=warn)


def radical_planned(mech, turn_number=None, warn=False):
    """The radical heat sink system will be engaged this (or the given) turn."""
    return (system_live(mech, "radical") and not mech.shutdown
            and use_escalating(mech, "radical heat sink system", turn_number, warn))


def radical_destroyed(mech):
    return has_system(mech, "radical") and not system_live(mech, "radical")


# =============================================================================
# ==========================  MASC / SUPERCHARGER  ============================
# =============================================================================
def reset_movement_boost(mech):
    mech.run_mp_multiplier = RUN_MULTIPLIER_BY_BOOSTERS[0]


def boost_multiplier(mech, planned=True):
    """The Running MP multiplier the mech's working MASC / supercharger give
    (p.204), counting the roll as a success (3+ on Daniel's 1-on / 1-off cycle).
    planned=True: only if the bot will use them this turn (the same decision
    resolve_movement_boosters makes, without its stub warning); False: whenever
    they work (the mech's BEST speed). For modeling a mech that hasn't moved
    yet - added 2026-10-20 (Claude): the two-ply look-ahead modeled a
    supercharged Kontio at its unboosted speed, and it then ran further than
    predicted and pushed the Hammerhead off the board."""
    live = sum(1 for kind in ("masc", "supercharger") if system_live(mech, kind))
    if not live or (planned and not use_escalating(mech, "MASC / supercharger", warn=False)):
        return RUN_MULTIPLIER_BY_BOOSTERS[0]
    return RUN_MULTIPLIER_BY_BOOSTERS[live]


@contextmanager
def modeled_boost(mech, multiplier):
    """Running MP computed with this multiplier inside the block (restored after)."""
    saved = mech.run_mp_multiplier
    mech.run_mp_multiplier = multiplier
    try:
        yield
    finally:
        mech.run_mp_multiplier = saved


def resolve_movement_boosters(mech):
    """Called when the mech declares its movement (before the envelope is
    built). On a cycle-on turn, rolls each working MASC / supercharger;
    successes set the Running MP multiplier. Returns the systems that
    failed, for apply_booster_failures after the mech has moved."""
    reset_movement_boost(mech)
    if not (system_live(mech, "masc") or system_live(mech, "supercharger")):
        return []
    if not use_escalating(mech, "MASC / supercharger", warn=True):
        return []
    worked, failed = 0, []
    for kind, label in (("masc", "MASC"), ("supercharger", "Supercharger")):
        if system_live(mech, kind):
            if escalating_roll(mech, kind, label):
                worked += 1
            else:
                failed.append(kind)
    mech.run_mp_multiplier = RUN_MULTIPLIER_BY_BOOSTERS[worked]
    return failed


def _random_leg(mech):
    """Kick Location Table, front/rear column (p.81): 1-3 right leg, 4-6 left
    leg. Non-biped mechs pick any leg."""
    if "Right Leg" in mech.leg_locations and "Left Leg" in mech.leg_locations and len(mech.leg_locations) == 2:
        return "Right Leg" if config.pick_number(6, prompt="MASC damage leg (1D6)") <= 3 else "Left Leg"
    return mech.leg_locations[config.pick_number(len(mech.leg_locations), prompt="MASC damage leg") - 1]


def apply_booster_failures(mech, failed):
    """End of movement: damage from a failed MASC / supercharger roll."""
    for kind in failed:
        roll = config.roll_2d6(prompt=f"{kind} failure critical check")
        count = crits_for_roll(roll)
        config.log(f"    {mech.side_name}: {kind} failure - critical check {roll}: {count} critical hit(s).")
        if kind == "masc":
            _masc_crits(mech, count)
        else:
            _supercharger_crits(mech, count)
            destroy_system(mech, "supercharger", "failed activation")


def _masc_crits(mech, count):
    if not count:
        return
    leg = _random_leg(mech)
    for i in range(1, count + 1):
        if mech.locations[leg]["destroyed"]:
            config.log(f"      {leg} already destroyed - MASC critical {i}/{count} lost (never transfers).")
            continue
        pool = [j for j, s in enumerate(mech.crits[leg]) if is_crit_target(s)]
        if not pool:
            config.log(f"      No critical slots left in {leg} - MASC critical {i}/{count} lost (never transfers).")
            continue
        idx = pool[config.pick_number(len(pool), prompt="MASC critical slot") - 1]
        resolve_slot_hit(mech, leg, idx, mech.crits[leg][idx], i, count)


def _supercharger_crits(mech, count):
    ct = mech.crits["Center Torso"]
    for i in range(1, count + 1):
        engines = [j for j, s in enumerate(ct) if s == "Engine"]
        if not engines:
            config.log(f"      No undamaged centre-torso Engine slot - supercharger critical {i}/{count} lost.")
            continue
        resolve_slot_hit(mech, "Center Torso", engines[0], "Engine", i, count)


# =============================================================================
# ==========================  TSM  ============================================
# =============================================================================
def tsm_active_for(mech, heat_level):
    return mech.has_tsm and heat_level >= TSM_ACTIVE_HEAT


# =============================================================================
# ==========================  HARJEL  (p.208, 2026-10-21)  ====================
# =============================================================================
# HarJel I: no hull-breach check for its location while that location has any
# armor (a breach is still automatic once all its armor is gone); a critical
# hit to it breaches the location. HarJel II / III: +2 to the location's
# breach checks while it has armor, and each turn the location takes armor
# damage it gets up to 2 / 4 armor back in the End Phase (never above its
# starting armor; a torso's split front / rear as evenly as possible); a
# critical hit to it forces an immediate extra critical-hit check there.
HARJEL_REPAIR = {2: 2, 3: 4}
HARJEL_BREACH_BONUS = 2


def harjel_kind(mech, location):
    """1, 2 or 3 for a working HarJel (I / II / III) in `location`, else 0."""
    best = 0
    for s in mech.crits.get(location, []):
        n = (getattr(s, "name", "") or "").replace(" ", "").upper() if isinstance(s, Equipment) else ""
        if "HARJEL" in n:
            best = max(best, 3 if "HARJELIII" in n else 2 if "HARJELII" in n else 1)
    return best


def _armor(mech, location):
    v = mech.locations[location]
    return v.get("armor", 0) + v.get("rear_armor", 0)


def harjel_breach_check(mech, location):
    """(skip the breach check?, bonus to the roll) for an underwater location
    that took damage (INTEGRATION__water.check_breach)."""
    kind = harjel_kind(mech, location)
    if not kind or _armor(mech, location) <= 0:
        return False, 0
    return (True, 0) if kind == 1 else (False, HARJEL_BREACH_BONUS)


def harjel_hit(mech, location, slot):
    """A critical hit to a HarJel slot (p.208): HarJel I - the gel leaks and
    the location counts as breached; II / III - an extra critical-hit check."""
    n = (getattr(slot, "name", "") or "").replace(" ", "").upper()
    if "HARJELII" in n:
        config.log(f"      {slot.name} hit: gel leak - an immediate extra critical-hit check at {location} (p.208).")
        from damage_resolution import check_critical
        check_critical(mech, location)
    else:
        import INTEGRATION__water as water
        config.log(f"      {slot.name} hit: gel leak - {location} counts as breached (p.208).")
        water.breach(mech, location)


def harjel_start_turn(mech):
    mech.armor_at_turn_start = {loc: (v.get("armor", 0), v.get("rear_armor", 0)) for loc, v in mech.locations.items()}


def harjel_end_turn(mech):
    """End Phase repair for HarJel II / III locations that took armor damage."""
    start = getattr(mech, "armor_at_turn_start", None)
    if not start:
        return
    for loc, (front0, rear0) in start.items():
        kind = harjel_kind(mech, loc)
        v = mech.locations[loc]
        if kind < 2 or v["destroyed"]:
            continue
        front, rear = v.get("armor", 0), v.get("rear_armor", 0)
        if front >= front0 and rear >= rear0:
            continue                                   # no armor damage here this turn
        budget = HARJEL_REPAIR[kind]
        room_f = max(0, mech.max_armor.get(loc, 0) - front)
        room_r = max(0, mech.max_rear_armor.get(loc, 0) - rear) if "rear_armor" in v else 0
        got_f = got_r = 0
        while budget and (room_f > got_f or room_r > got_r):   # alternate - as evenly as possible
            if room_f > got_f and (got_f <= got_r or room_r <= got_r):
                got_f += 1
            elif room_r > got_r:
                got_r += 1
            budget -= 1
        if got_f or got_r:
            v["armor"] = front + got_f
            if got_r:
                v["rear_armor"] = rear + got_r
            config.log(f"  [End] {mech.side_name}'s HarJel {'II' if kind == 2 else 'III'} restores {got_f + got_r} "
                       f"armor at {loc}{f' ({got_f} front, {got_r} rear)' if got_r else ''} (p.208).")


# =============================================================================
# ==========================  BLUE SHIELD PFD  (p.207, 2026-10-21)  ===========
# =============================================================================
# Activated (p.180 - on or off from the start, switched in the End Phase: a
# choice, stubs.stub_blue_shield). While on: damage from every PPC type is
# halved (round down, minimum 1); the 'Mech's stealth systems are negated.
# Escalating Failure, but only once it has been on for 6 turns (consecutive
# or not): End Phase of the 6th turn of use, roll at the 1st interval (3+);
# each later turn of use, one interval higher - never lower. A failure: off
# for the rest of the battle. A critical hit to one of its slots while on: a
# 5-point component explosion there, and off for good.
PFD_FAILURE_AFTER = 6
PFD_EXPLOSION = 5


def blue_shield_on(mech):
    return (getattr(mech, "pfd_active", False) and not getattr(mech, "pfd_failed", False)
            and not mech.shutdown and system_live(mech, "blue_shield"))


def is_ppc(weapon):
    n = _norm(getattr(weapon, "name", ""))
    return "PPC" in n and "CAPACITOR" not in n


def blue_shield_damage(target, weapon, damage):
    """A PPC hit's damage after the target's Blue Shield (p.207)."""
    if damage and is_ppc(weapon) and blue_shield_on(target):
        cut = max(1, damage // 2)
        config.log(f"      {target.side_name}'s Blue Shield halves the {weapon.name}: {damage} -> {cut} (p.207).")
        return cut
    return damage


def blue_shield_end_turn(mech):
    if not has_system(mech, "blue_shield") or mech.pfd_failed:
        return
    if blue_shield_on(mech):
        mech.pfd_turns_used += 1
        if mech.pfd_turns_used >= PFD_FAILURE_AFTER:
            interval = mech.pfd_turns_used - PFD_FAILURE_AFTER + 1
            tn = escalating_avoid_tn(interval)
            roll = config.roll_2d6(prompt="Blue Shield escalating failure roll")
            config.log(f"  [End] {mech.side_name}'s Blue Shield ({mech.pfd_turns_used} turns on) needs {tn}, "
                       f"rolled {roll} - {'holds' if roll >= tn else 'FAILS: off for the rest of the battle'} (p.207).")
            if roll < tn:
                mech.pfd_failed, mech.pfd_active = True, False
                return
    if system_live(mech, "blue_shield") and not mech.pfd_failed:
        mech.pfd_active = stubs.stub_blue_shield(mech.side_name, "end phase")


def blue_shield_hit(mech, location, slot):
    """A critical hit to a Blue Shield slot (p.207): while on, a 5-point
    component explosion there and the PFD is off for good. The slot is
    already marked destroyed by now, so "was it on" reads the switch rather
    than system_live (an earlier slot hit already set pfd_failed)."""
    if not getattr(mech, "pfd_active", False) or mech.pfd_failed or mech.shutdown:
        return
    from damage_resolution import apply_explosion
    mech.pfd_failed, mech.pfd_active = True, False
    slot.explosion_damage = PFD_EXPLOSION
    config.log(f"      Blue Shield hit while active: a {PFD_EXPLOSION}-point explosion (p.207).")
    apply_explosion(mech, slot, location)
