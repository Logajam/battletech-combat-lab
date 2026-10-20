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

=== THE DECISION ===
INTEGRATION__movement_attacks (shared with death from above): the per-mode
gate (Daniel, 2026-10-20), then scored like any spot; the first mover's
two-ply anticipates it.

Not modeled: the +2 PSRs in the score; domino effects (no third mech);
minimum movement, buildings, water halving, lance / spikes / shields; partial
cover is ignored as the rule says, but woods still count.
"""

import math

import INTEGRATION__config as config
import INTEGRATION__attack_resolution as attack_resolution
import INTEGRATION__movement_attacks as movement_attacks
from INTEGRATION__movement_attacks import groupings, comparative_modifier, terrain_modifier
from mech_state import (DamageType, is_destroyed, is_immobile, all_crew_unconscious,
                        mark_consciousness_check_pending)
from damage_resolution import apply_damage
from hit_location import resolve_hit_location
import piloting_rolls
import hex_geometry
import combat

CHARGE_PSR_MODIFIER = 2         # p.78: both mechs, after a successful charge


# =============================================================================
# ==========================  NUMBERS  ========================================
# =============================================================================
def target_damage(attacker, attacker_tmm):
    return math.ceil(attacker.mass / 5 * (attacker_tmm + 1))


def attacker_damage(target):
    return math.ceil(target.mass / 10)


def to_hit(attacker, mode, target, a_xy, t_xy, terrain_map, target_tmm):
    return (attacker.piloting + combat.MODE_TO_AMM[mode] + target_tmm
            + terrain_modifier(a_xy, t_xy, terrain_map) + comparative_modifier(attacker, target))


def can_charge(mover, target, target_has_moved):
    return movement_attacks.can_be_attacked(target, target_has_moved) and not target.prone and mover.hex is not None


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
    movement_attacks.apply_groups(mech, damage, "standard", side, label)


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
    kind, new_label, drop = movement_attacks.displacement(target.hex, combat._direction_facing(a_hex, t_hex),
                                                          terrain_map)
    if kind == "off":
        target.destroyed, target.cause_of_death = True, "Displaced off the battlefield"
        config.log(f"    {target.side_name} is pushed off the battlefield - destroyed (p.113).")
        if not is_destroyed(attacker):
            attacker.hex = target.hex
        return triggers
    if kind == "blocked":
        config.log(f"    Displacement is prohibited (3+ levels up) - neither mech moves (p.113).")
        triggers[target.side_name].append(("charged", CHARGE_PSR_MODIFIER))
        return triggers
    old = target.hex
    target.hex = new_label
    if not is_destroyed(attacker):
        attacker.hex = old
    config.log(f"    {target.side_name} is displaced {old} -> {new_label}; {attacker.side_name} advances into {old}.")
    if drop >= 2:
        config.log(f"    {target.side_name} is displaced {drop} levels down - automatic fall (p.114).")
        piloting_rolls.resolve_fall(target, cause="displaced down", levels=drop)
    else:
        triggers[target.side_name].append(("charged", CHARGE_PSR_MODIFIER))
    return triggers
