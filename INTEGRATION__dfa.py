"""
INTEGRATION__dfa.py  (NEW 2026-10-20, Claude - Pile 2 rules)

Death from above (Core Rulebook pp.79-80; displacement pp.113-114; falls
p.115). The movement decision is INTEGRATION__movement_attacks (shared with
charges); this module has the numbers and the Physical-phase resolution.

=== THE RULE ===
  - Declared in the Movement Phase, resolved in the Physical Attack Phase,
    against a mech that has finished moving (or is immobile), standing or
    prone. The attacker jumps: it needs the Jumping MP to land on the target's
    hex (distance, a clear path) and to clear the target's LOS level (its
    hex's level + 2 standing / 1 prone). It stops in the hex next to the
    target along its path, facing it, and keeps the jump's TMM.
  - The attacker makes no ranged attacks and can't be attacked physically
    (it is in the air) unless the DFA is cancelled.
  - To-hit: Piloting + 3 (jumping) + target TMM + the comparative modifier
    (attacker Piloting - target Piloting; 4 for an immobile target); terrain
    ignored. TN 13+ misses - a DFA can't be aborted.
  - Hit: target takes ceil(tons / 10 x 3) on the Punch table (a prone target:
    the standard table's rear column), from the stop hex's direction; the
    attacker takes ceil(tons / 5) on the Kick table's front column. Both in
    5-point groupings. The attacker lands in the target's hex; the target is
    displaced one hex straight on - off the board destroyed, 2+ levels down an
    automatic fall; a prohibited hex (3+ up) moves it to the open hex nearest
    that hexside (both sides of it, then the back ones); nowhere open = the
    target is destroyed. Then, unless the displacement was a fall, both PSR +2.
  - Miss: the attacker lands in the target's hex and falls 2 levels (damage
    to the rear); the target moves to an adjacent hex of its choice (the bot:
    the safest - no drop, on the board); nowhere = the attacker is destroyed.
  - Cancelled: the target destroyed before the Physical phase (the attacker
    lands in its hex and may make another physical attack), or the attacker
    destroyed. A miss outright: the attacker fell in the Ranged phase (here:
    it is already down - it lands in the target's hex without a second fall,
    an approximation of "resolve as a failed DFA instead of falling"), or its
    pilot is unconscious.
Talons x1.5 and the target's spikes: INTEGRATION__physical_gear (2026-10-21).
Not modeled: wind, water, a third mech in the displacement hex.
"""

import math

import INTEGRATION__config as config
import INTEGRATION__hazards as hazards  # magma / hazardous liquid on displacement (TO:AR, 2026-10-27)
import INTEGRATION__physical_gear as gear
from INTEGRATION__movement_attacks import comparative_modifier, displacement, apply_groups
from mech_state import is_destroyed, all_crew_unconscious, torso_cockpit_sensor_penalty, tripod_pilot_modifier
import piloting_rolls
import hex_geometry
import combat

DFA_PSR_MODIFIER = 2
JUMP_MODIFIER = 3               # p.80: "+3 TN modifier for using Jumping movement"
MISS_FALL_LEVELS = 2


def target_damage(attacker):
    """ceil(tons / 10 x 3); x1.5 (rounding normally) with talons on both legs -
    a tripod / quad: two (p.196, 2026-10-21; was not modeled)."""
    damage = math.ceil(attacker.mass / 10 * 3)
    return gear.with_talons(damage) if gear.dfa_talons(attacker) else damage


def attacker_damage(attacker):
    return math.ceil(attacker.mass / 5)


def miss_fall_damage(attacker):
    return math.ceil(attacker.mass / 10) * (MISS_FALL_LEVELS + 1)


def to_hit(attacker, target, target_tmm):
    import INTEGRATION__advanced_weapons as adv
    return (attacker.piloting + JUMP_MODIFIER + target_tmm + comparative_modifier(attacker, target)
            + adv.own_attack_modifier(attacker, physical=True)                                   # Taser (TO:AUE p.158), IMP (IO)
            + torso_cockpit_sensor_penalty(attacker) + tripod_pilot_modifier(attacker))   # pp.203, 236


def _land(attacker, label):
    """The attacker lands in the target's hex, facing as it was (p.80)."""
    if not is_destroyed(attacker):
        attacker.hex = label
        hazards.enter_hex(attacker, label, jumped=True, in_phase=True)     # magma / pools (TO:AR, 2026-10-27)


def declare(attacker, target, terrain_map):
    """Physical phase: (TN, hit) for a DFA that goes ahead, None if cancelled
    (attacker.dfa cleared; it may make another physical attack)."""
    import INTEGRATION__attack_resolution as attack_resolution
    a_name, t_name = attacker.side_name, target.side_name
    if is_destroyed(attacker):
        attacker.dfa = None
        return None
    if is_destroyed(target):
        config.log(f"  [Physical] {a_name}'s DFA is cancelled: {t_name} is destroyed - it lands in {target.hex} (p.80).")
        _land(attacker, target.hex)
        attacker.dfa = None
        return None
    tn = to_hit(attacker, target, attack_resolution._target_tmm(target))
    if attacker.prone or all_crew_unconscious(attacker):
        config.log(f"  [Physical] {a_name}'s DFA misses: it is {'down' if attacker.prone else 'unconscious'} (p.79).")
        return tn, False
    roll = config.roll_2d6(prompt="DFA attack roll")
    hit = tn <= 12 and roll >= tn
    config.log(f"  [Physical] {a_name} -> {t_name}: DEATH FROM ABOVE needs {tn} (piloting {attacker.piloting} "
               f"+ jump {JUMP_MODIFIER} + TMM {attack_resolution._target_tmm(target)} + comparative "
               f"{comparative_modifier(attacker, target):+d}), rolled {roll} -> {'HIT' if hit else 'miss'}")
    return tn, hit


def _open_hexes(target, direction, terrain_map):
    """Displacement candidates nearest `direction` first (p.80): straight on,
    the two beside it, the two behind those, then straight back."""
    order = [direction, (direction - 1) % 6, (direction + 1) % 6, (direction - 2) % 6, (direction + 2) % 6,
             (direction + 3) % 6]
    out = []
    for d in order:
        kind, label, drop = displacement(target.hex, d, terrain_map)
        if kind != "blocked":
            out.append((d, kind, label, drop))
    return out


def _displace(target, kind, label, drop, triggers, cause):
    """Move the target; returns True if it fell automatically."""
    if kind == "off":
        target.destroyed, target.cause_of_death = True, "Displaced off the battlefield"
        config.log(f"    {target.side_name} is pushed off the battlefield - destroyed (p.113).")
        return True
    old, target.hex = target.hex, label
    config.log(f"    {target.side_name} is displaced {old} -> {label}.")
    hazards.enter_hex(target, label, why=f"displaced into {label}", in_phase=True)
    if drop >= 2:
        config.log(f"    {target.side_name} is displaced {drop} levels down - automatic fall (p.114).")
        piloting_rolls.resolve_fall(target, cause=cause, levels=drop)
        return True
    return False


def resolve(attacker, target, hit, terrain_map):
    """Damage, landing and displacement (p.80). Returns PSR triggers
    {side_name: [(reason, modifier)]}."""
    import INTEGRATION__attack_resolution as attack_resolution
    triggers = {attacker.side_name: [], target.side_name: []}
    a_xy, t_xy = hex_geometry.parse_hex_label(attacker.hex), hex_geometry.parse_hex_label(target.hex)
    direction = combat._direction_facing(a_xy, t_xy)
    target_hex = target.hex
    if hit:
        side = attack_resolution.attack_side(a_xy, t_xy, hex_geometry.compass_to_facing(target.facing), terrain_map)
        table, t_side = ("standard", "rear") if target.prone else ("punch", side)
        config.log(f"    DFA: {target.side_name} takes {target_damage(attacker)} ({table} table, {t_side}), "
                   f"{attacker.side_name} takes {attacker_damage(attacker)} (kick table).")
        hits = apply_groups(target, target_damage(attacker), table, t_side,
                            "DFA" + (" (talons x1.5, p.196)" if gear.dfa_talons(attacker) else ""))
        if any(spiked for _, spiked in hits):
            gear.spike_retaliation(attacker, [l for l in attacker.leg_locations
                                              if not attacker.locations[l]["destroyed"]][:2])   # p.196: both legs
        apply_groups(attacker, attacker_damage(attacker), "kick", "front", "DFA (attacker)")
        fell = False
        if not is_destroyed(target):
            options = _open_hexes(target, direction, terrain_map)
            if not options:
                target.destroyed, target.cause_of_death = True, "Nowhere to be displaced (DFA)"
                config.log(f"    {target.side_name} can't be displaced anywhere - destroyed (p.81).")
            else:
                _, kind, label, drop = options[0]
                fell = _displace(target, kind, label, drop, triggers, "displaced by a DFA")
        _land(attacker, target_hex)
        if not fell:
            for m, why in ((target, "hit by a DFA"), (attacker, "DFA (attacker)")):
                if not is_destroyed(m):
                    triggers[m.side_name].append((why, DFA_PSR_MODIFIER))
        return triggers
    # Miss: the target steps aside (its choice - the safest open hex), the attacker falls 2 levels.
    options = [o for o in _open_hexes(target, direction, terrain_map) if o[1] == "moved"]
    if not options:
        attacker.destroyed, attacker.cause_of_death = True, "Failed DFA with nowhere to land"
        config.log(f"    {target.side_name} has nowhere to step aside - {attacker.side_name} is destroyed (p.81).")
        return triggers
    _, _, label, drop = min(options, key=lambda o: (max(o[3], 0), o[0] != direction))
    _displace(target, "moved", label, drop, triggers, "stepping aside from a DFA")
    _land(attacker, target_hex)
    if not attacker.prone and not is_destroyed(attacker):
        config.log(f"    {attacker.side_name} misses and falls {MISS_FALL_LEVELS} levels in {target_hex} (rear, p.80).")
        piloting_rolls.resolve_fall(attacker, cause="failed DFA", levels=MISS_FALL_LEVELS,
                                    side="rear")
    return triggers
