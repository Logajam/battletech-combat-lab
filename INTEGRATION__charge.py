"""
INTEGRATION__charge.py  (NEW 2026-10-20, Claude - Pile 2 rules, Pile 4 choice)

Charge attacks (Core Rulebook p.78; displacement pp.113-114; falls p.115).

=== THE RULE ===
  - Declared in the Movement Phase, resolved in the Physical Attack Phase.
    Only against a STANDING mech that has finished its movement this turn
    (or is immobile) - in a two-mech battle, the second mover (or anyone
    against an immobile enemy). The attacker must not jump.
  - Movement: the attacker ends in a hex adjacent to the target, FACING it,
    with enough MP left to enter the target's hex (its terrain / level cost;
    no more than 2 levels up or down). It stops there; its TMM counts the
    move into the target's hex too (one more hex moved).
  - The charger can't make ranged attacks that turn (it can be shot) and makes
    no other physical attack. The target can still attack it.
  - To-hit: Piloting + AMM + target TMM + terrain (partial cover ignored) +
    the comparative modifier, attacker Piloting - target Piloting (an immobile
    target counts as Piloting 4 and takes the usual -4).
  - Hit: target takes ceil(attacker tons / 5 x (attacker TMM + 1)), attacker
    takes ceil(target tons / 10), both in 5-point groupings on the standard
    table (the target by attack direction; the attacker on its front - Claude's
    call, the rule doesn't name a side). Then displacement: the attacker
    advances into the target's hex and the target is pushed one hex straight
    on (the direction of the charge). Off the board = destroyed; 3+ levels up
    = prohibited, nobody moves; 2+ levels down = automatic fall of that many
    levels (no PSR). A mech destroyed by the charge isn't displaced. Then both
    make a PSR at +2 (joined to the phase's other PSR triggers).
  - Miss: both stay where they are, no PSR.
  - Cancelled (the charger may then make another physical attack): the target
    fell or was destroyed before the Physical phase, or the TN is 13+ (the bot
    always aborts). The charge misses outright if the charger fell, was
    destroyed or its pilot is unconscious.

=== THE DECISION (pile 4, Daniel 2026-10-20) ===
Gate first: for each movement mode, a charge is only looked at if its expected
damage beats the best ordinary attack (ranged + physical) any spot in that
mode offers. A charge that passes is scored like any spot: dealt (charge worth)
/ (return fire and physical attacks on the charger at its hex + the charger's
own expected self-damage + movement PSR cost), and taken only if that beats
the ordinary pick's score. Damage is weighted by armor exposure and structure
like every other number in the picker (INTEGRATION__physical.Worth).

Not modeled: the +2 PSRs and the displacement (falls, a push off the board)
in the score; a first mover anticipating being charged (the two-ply reply
doesn't charge); domino effects (no third mech); minimum movement, buildings,
water halving, lance / spikes / shields; partial cover is ignored as the rule
says, but woods still count.
"""

import math

import INTEGRATION__config as config
import INTEGRATION__attack_resolution as attack_resolution
import INTEGRATION__physical as physical
from mech_state import (DamageType, is_destroyed, is_immobile, all_crew_unconscious, compute_walk_mp,
                        compute_running_mp, mark_consciousness_check_pending)
from damage_resolution import apply_damage
from hit_location import resolve_hit_location
import piloting_rolls
import hex_geometry
import combat
import terrain_rules
from los import hex_distance, trace_los_path

CHARGE_PSR_MODIFIER = 2         # p.78: both mechs, after a successful charge
IMMOBILE_COMPARATIVE_PILOTING = 4


# =============================================================================
# ==========================  NUMBERS  ========================================
# =============================================================================
def target_damage(attacker, attacker_tmm):
    return math.ceil(attacker.mass / 5 * (attacker_tmm + 1))


def attacker_damage(target):
    return math.ceil(target.mass / 10)


def groupings(damage):
    return [5] * (damage // 5) + ([damage % 5] if damage % 5 else [])


def comparative_modifier(attacker, target):
    return attacker.piloting - (IMMOBILE_COMPARATIVE_PILOTING if is_immobile(target) else target.piloting)


def terrain_modifier(a_hex, t_hex, terrain_map):
    """The LOS terrain modifier without partial cover (p.78: ignored)."""
    trace = trace_los_path(a_hex, t_hex, terrain_map)
    cover = trace.steps[-1].partial_cover if trace.steps else 0
    return trace.result.modifier - cover


def to_hit(attacker, mode, target, a_hex, t_hex, terrain_map, target_tmm):
    return (attacker.piloting + combat.MODE_TO_AMM[mode] + target_tmm
            + terrain_modifier(a_hex, t_hex, terrain_map) + comparative_modifier(attacker, target))


def worth(damage, target, side):
    """Expected-damage-equivalent worth of `damage` in 5-point groups on the
    standard table (armor exposure x structure bonus, physical.Worth)."""
    w = physical.Worth(target)
    return sum(g * w.factor("standard", side, g) for g in groupings(damage))


# =============================================================================
# ==========================  MOVEMENT PHASE  =================================
# =============================================================================
def can_charge(mover, target, target_has_moved):
    return (target.hex is not None and mover.hex is not None and not target.prone and not is_destroyed(target)
            and (target_has_moved or is_immobile(target)))


def charge_states(mover, target, terrain_map, standup_mp=None):
    """Every way the mover can charge the target this turn: [{hex, facing,
    mode, fc, mp_spent}] with fc / mp_spent INCLUDING the move into the
    target's hex. For each (hex, facing, mode) only the most hexes moved
    (then least MP) is kept - more hexes means more damage and TMM."""
    import INTEGRATION__ranged_combat as ranged_combat      # it imports physical, which this module needs first
    t_xy = hex_geometry.parse_hex_label(target.hex)
    t_info = terrain_map["hexes"][target.hex]
    walk = compute_walk_mp(mover)
    budget = compute_running_mp(mover) if standup_mp is None else standup_mp
    best = {}
    for x, y, facing, fc, mode, mp in ranged_combat.movement_options(mover, terrain_map, standup_mp=standup_mp):
        if mode == "Jump" or (x, y) == t_xy or hex_distance((x, y), t_xy) != 1:
            continue
        if combat._direction_facing((x, y), t_xy) != facing:
            continue                                   # must face the target and enter it moving forward
        label = hex_geometry.hex_label(x, y)
        a_level = terrain_map["hexes"][label]["level"]
        if abs(t_info["level"] - a_level) > 2:
            continue
        total = mp + terrain_rules.transition_cost(a_level, t_info["level"], t_info["features"])
        if total > budget:
            continue
        charge_mode = "Run" if standup_mp is not None else combat.classify_movement_mode(total, walk)
        key = (label, facing, charge_mode)
        cand = (fc + 1, -total)
        if key not in best or cand > best[key]:
            best[key] = cand
    return [{"hex": label, "facing": hex_geometry.facing_to_compass(facing), "mode": mode,
             "fc": fc, "mp_spent": -neg_mp, "charge": True}
            for (label, facing, mode), (fc, neg_mp) in best.items()]


def expected_dealt(mover, target, state, terrain_map):
    """(worth to the target, P(hit), raw damage, TN) of charging from state."""
    a_hex, t_hex = hex_geometry.parse_hex_label(state["hex"]), hex_geometry.parse_hex_label(target.hex)
    tmm = combat.fc_to_tmm(state["fc"], jumped=False)
    tn = to_hit(mover, state["mode"], target, a_hex, t_hex, terrain_map, attack_resolution._target_tmm(target))
    p = combat.hit_probability(tn) if tn <= 12 else 0.0
    dmg = target_damage(mover, tmm)
    side = attack_resolution.attack_side(a_hex, t_hex, hex_geometry.compass_to_facing(target.facing), terrain_map)
    return p * worth(dmg, target, side), p, dmg, tn


def self_damage_worth(mover, target, p_hit):
    return p_hit * worth(attacker_damage(target), mover, "front")


# =============================================================================
# ==========================  PHYSICAL PHASE  =================================
# =============================================================================
def declare(attacker, target, terrain_map):
    """Physical phase: the charge's (TN, hit) if it goes ahead, None if it was
    cancelled (attacker.charging cleared - it may make another physical
    attack), or "miss" when it misses outright."""
    a_name, t_name = attacker.side_name, target.side_name
    if is_destroyed(target) or target.prone:
        config.log(f"  [Physical] {a_name}'s charge is cancelled: {t_name} "
                   f"{'is destroyed' if is_destroyed(target) else 'fell'} (p.78).")
        attacker.charging = None
        return None
    if attacker.prone or is_destroyed(attacker) or all_crew_unconscious(attacker):
        config.log(f"  [Physical] {a_name}'s charge misses: it is "
                   f"{'down' if attacker.prone else 'unconscious' if not is_destroyed(attacker) else 'destroyed'} (p.78).")
        return "miss"
    a_hex, t_hex = hex_geometry.parse_hex_label(attacker.hex), hex_geometry.parse_hex_label(target.hex)
    tn = to_hit(attacker, attacker.move_mode, target, a_hex, t_hex, terrain_map, attack_resolution._target_tmm(target))
    if tn > 12:
        config.log(f"  [Physical] {a_name} aborts its charge (needs {tn}) (p.78).")
        attacker.charging = None
        return None
    roll = config.roll_2d6(prompt="Charge attack roll")
    hit = roll >= tn
    config.log(f"  [Physical] {a_name} -> {t_name}: CHARGE needs {tn} (piloting {attacker.piloting} + AMM "
               f"{combat.MODE_TO_AMM[attacker.move_mode]} + TMM {attack_resolution._target_tmm(target)} + terrain "
               f"{terrain_modifier(a_hex, t_hex, terrain_map)} + comparative {comparative_modifier(attacker, target):+d}), "
               f"rolled {roll} -> {'HIT' if hit else 'miss'}")
    return tn, hit


def _apply(mech, damage, side, label):
    for g in groupings(damage):
        if is_destroyed(mech):
            return
        loc = resolve_hit_location(config.roll_2d6(prompt=f"{label} hit location"), mech, side)
        config.log(f"    {label}: {g} to {mech.side_name}'s {loc}.")
        if loc == "Head":
            mech.pilot_hits += 1
            mark_consciousness_check_pending(mech)
        apply_damage(mech, loc, g, armor_field="rear_armor" if side == "rear" else "armor",
                     damage_type=DamageType.PHYSICAL)


def resolve_hit(attacker, target, terrain_map):
    """Damage both ways, then displacement (p.78, pp.113-115). Returns the PSR
    triggers {side_name: [(reason, modifier)]}."""
    a_hex, t_hex = hex_geometry.parse_hex_label(attacker.hex), hex_geometry.parse_hex_label(target.hex)
    side = attack_resolution.attack_side(a_hex, t_hex, hex_geometry.compass_to_facing(target.facing), terrain_map)
    dealt, taken = target_damage(attacker, combat.fc_to_tmm(attacker.move_fc, jumped=False)), attacker_damage(target)
    config.log(f"    Charge: {target.side_name} takes {dealt} ({side}), {attacker.side_name} takes {taken}.")
    _apply(target, dealt, side, "Charge")
    _apply(attacker, taken, "front", "Charge (attacker)")

    triggers = {attacker.side_name: [], target.side_name: []}
    if not is_destroyed(attacker):
        triggers[attacker.side_name].append(("charged (attacker)", CHARGE_PSR_MODIFIER))
    if is_destroyed(target):
        if not is_destroyed(attacker):
            attacker.hex = target.hex
        return triggers
    direction = combat._direction_facing(a_hex, t_hex)
    dx, dy = hex_geometry.FACING_DELTAS[direction]
    try:
        new_label = hex_geometry.hex_label(t_hex[0] + dx, t_hex[1] + dy)
    except ValueError:
        new_label = None
    hexes = terrain_map["hexes"]
    if new_label not in hexes:
        target.destroyed, target.cause_of_death = True, "Displaced off the battlefield"
        config.log(f"    {target.side_name} is pushed off the battlefield - destroyed (p.113).")
        if not is_destroyed(attacker):
            attacker.hex = target.hex
        return triggers
    drop = hexes[target.hex]["level"] - hexes[new_label]["level"]
    if drop <= -3:
        config.log(f"    Displacement into {new_label} is prohibited (3+ levels up) - neither mech moves (p.113).")
        triggers[target.side_name].append(("charged", CHARGE_PSR_MODIFIER))
        return triggers
    old = target.hex
    target.hex = new_label
    if not is_destroyed(attacker):
        attacker.hex = old
    config.log(f"    {target.side_name} is displaced {old} -> {new_label}; {attacker.side_name} advances into {old}.")
    if drop >= 2:
        config.log(f"    {target.side_name} is displaced {drop} levels down - automatic fall (p.114).")
        piloting_rolls.resolve_fall(target, seatbelt_modifier=0, cause="displaced down", levels=drop)
    else:
        triggers[target.side_name].append(("charged", CHARGE_PSR_MODIFIER))
    return triggers
