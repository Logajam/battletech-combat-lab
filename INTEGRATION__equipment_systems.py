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
    and 15+ (2 hits) instead of 10-19 / 20+ (INTEGRATION__heat). Its PSR
    and sensor rules are not modeled.

Not modeled: shutting a system off by choice, MASC/supercharger crits taken
mid-move. (ECM itself - jamming Artemis and Narc - is INTEGRATION__electronics.)
"""

import INTEGRATION__config as config
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


# =============================================================================
# ==========================  STEALTH  ========================================
# =============================================================================
def active_stealth(mech):
    """Stealth systems switched on and working right now (always on by
    default; nothing works while shut down - p.104)."""
    if mech.shutdown:
        return []
    active = [k for k in ("chameleon", "null_signature") if system_live(mech, k)]
    if mech.has_stealth_armor and ecm_live(mech):
        active.append("stealth_armor")
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
    """An active Void-Signature System adds +1 to its own mech's ranged attacks."""
    return VOID_OWN_ATTACK_MODIFIER if "void_signature" in active_stealth(attacker) else 0


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
