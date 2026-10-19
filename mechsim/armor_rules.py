"""
Armor-type x damage-type dispatch. This module owns "how much of an attack's
damage does armor actually absorb, and does the attack's own damage value
get reduced before that." It does NOT own the attack loop itself (that's
damage_resolution.apply_damage, which calls into this module) or mech
identity/state (mech_state.py).

Ported from the vehicle sim's damage_resolution.py (`_reduce_attack_damage_
for_armor` / `_consume_armor`) per the Vehicle Sim -> Mech Sim Gap Analysis,
Stage 2. This is a re-implementation against mech_state.py's shapes, not a
file copy - see that doc's "ground rule" note. Math is otherwise carried
over unchanged, including the vehicle sim's own flagged uncertainty on
Reflective vs. Energy damage (see _consume_armor's docstring below - not
resolved here, carried over as-is).

STAGE 3/4 (2026-07-12, Claude): Structure-type consumption (_consume_structure)
and the crit_roll_modifier (Hardened/Anti-Penetrative Ablation/Reinforced) are
now ported - see those functions' docstrings below. Anti-Penetrative Ablation's
damage math is still flat 1:1 (its only real mechanic IS the crit modifier,
which now has an effect). The zero-effective-damage crit gate (Ferro-Lamellor
reduced to 0 dmg skipping the crit roll) needed NO new code here - it was
already a side effect of damage_resolution.apply_damage only calling
check_critical when struct_dmg > 0, which is already 0 whenever
_consume_armor's overflow is 0. Explosion resolution (damage_resolution.
apply_explosion) still consumes structure flat 1:1, NOT through
_consume_structure - out of scope this pass, see that module's docstring.
"""

import math

from mech_state import ArmorType, DamageType, StructureType


def _reduce_attack_damage_for_armor(armor_type, damage_type, damage):
    """Armor-type effects that change the ATTACK's own damage value, applied
    BEFORE armor absorbs anything - as opposed to Reflective, which changes
    how armor is CONSUMED rather than the incoming damage (see
    _consume_armor). Only one of these ever applies, since armor_type is a
    single value per location - no stacking/ordering between them to worry
    about."""
    if armor_type == ArmorType.REACTIVE and damage_type in (DamageType.MISSILE, DamageType.AREA_EFFECT):
        return max(damage // 2, 1)
    if armor_type == ArmorType.BALLISTIC_REINFORCED and damage_type in (DamageType.MISSILE, DamageType.BALLISTIC):
        return max(damage // 2, 1)
    if armor_type == ArmorType.FERRO_LAMELLOR:
        return max(damage - math.ceil(damage / 5), 0)
    if armor_type == ArmorType.IMPACT_RESISTANT and damage_type == DamageType.PHYSICAL:
        return max(damage - math.ceil(damage / 3), 1)
    return damage


# HELP(consume_armor.hardened_reflective)
def _consume_armor(armor_type, damage_type, damage, armor_pool):
    """Returns (armor_pts_destroyed, damage_that_continues_to_structure).

    Hardened: each armor point absorbs 2 damage before being destroyed,
    applies to every damage type. Unlike Reflective (below), Hardened does
    NOT discard an odd half-point of damage - it's tracked as a fractional
    pool (e.g. 10 armor hit for 5 dmg -> 7.5 armor remaining is a valid
    state, not floored/rounded).

    Reflective changes the CONSUMPTION RATIO AND discards a leftover odd
    point rather than tracking it, and the ratio flips depending on damage
    type - carried over from the vehicle sim's own flagged uncertainty:
    Energy has an unconfirmed exhausted-armor edge case; Ballistic/Missile
    falls through to flat 1:1 below (unspecified in the source material).
    Not resolved here - if this edge case matters for a real run, confirm
    against Sarna/BattleMech Manual before relying on it."""
    if armor_type == ArmorType.HARDENED:
        destroyed = min(damage / 2, armor_pool)
        overflow = max(damage - armor_pool * 2, 0)
        return destroyed, overflow
    if armor_type == ArmorType.REFLECTIVE:
        if damage_type == DamageType.ENERGY:
            destroyed = min(damage // 2, armor_pool)
            if damage > 0 and destroyed == 0:
                destroyed = min(1, armor_pool)
            overflow = max(damage - armor_pool * 2, 0) if destroyed >= armor_pool else 0
            return destroyed, overflow
        if damage_type in (DamageType.PHYSICAL, DamageType.AREA_EFFECT):
            capacity_in_damage_points = math.ceil(armor_pool / 2)
            damage_absorbed_points = min(damage, capacity_in_damage_points)
            destroyed = min(damage_absorbed_points * 2, armor_pool)
            overflow = max(damage - damage_absorbed_points, 0)
            return destroyed, overflow
    consumed = min(damage, armor_pool)
    return consumed, max(damage - armor_pool, 0)


# HELP(consume_structure.reinforced_composite)
def _consume_structure(structure_type, damage, structure_pool):
    """Returns (structure_pts_destroyed, damage_overflow_beyond_this_pool).
    Same shape/ratios as _consume_armor's Hardened/Reflective math, one tier
    later in the pipeline - ported from the vehicle sim's damage_resolution.py
    (Gap Analysis Stage 3). Reinforced: each point absorbs 2 damage, tracked
    as a fractional pool (not floored/rounded) - same non-integer approach as
    Hardened armor. Composite: same ratio+discarded-remainder mechanic as
    Reflective armor vs. Physical/AE (2 structure points destroyed per 1
    damage point absorbed, capacity measured in whole damage points via
    ceil(), leftover odd point of damage is dropped, not carried to overflow).
    This is mech-wide (StructureType, not per-location like ArmorType), so
    unlike _consume_armor there's no damage_type branching here at all."""
    if structure_type == StructureType.REINFORCED:
        destroyed = min(damage / 2, structure_pool)
        overflow = max(damage - structure_pool * 2, 0)
        return destroyed, overflow
    if structure_type == StructureType.COMPOSITE:
        capacity_in_damage_points = math.ceil(structure_pool / 2)
        damage_absorbed_points = min(damage, capacity_in_damage_points)
        destroyed = min(damage_absorbed_points * 2, structure_pool)
        overflow = max(damage - damage_absorbed_points, 0)
        return destroyed, overflow
    consumed = min(damage, structure_pool)
    return consumed, max(damage - structure_pool, 0)


# HELP(crit_roll_modifier.location_gating)
def crit_roll_modifier(structure_type, armor_type=None, armor_present=False):
    """-2 if armor_type is Hardened/Anti-Penetrative Ablation AND armor_present
    is True; -1 blanket if structure_type is Reinforced (unconditional - a
    mech-wide property, not gated on any location's armor state). These stack.
    Ported from the vehicle sim's crit_roll_modifier (Gap Analysis Stage 4),
    but reshaped as a pure function taking explicit values rather than a
    (vehicle, location) pair - see DESIGN_NOTES.md#crit-roll-modifier-location-gating
    for the vehicle sim's original location-gating rule.

    CORRECTED 2026-07-13 (Daniel - supersedes the 2026-07-12 version of this
    docstring, which had the gating direction backwards): critical hits are
    checked AFTER damage has already been applied to armor and structure for
    that hit, per this sim's own damage_resolution.apply_damage sequencing.
    So the crit check - both the one apply_damage triggers internally off
    structure damage, and a separate floating-TAC crit check on the same
    location - always sees the location's POST-consumption armor value, never
    a "was armor present before this hit" snapshot. A hit that drains a
    location's last point of armor does NOT get the -2 on its own resulting
    crit check(s) - by the time any crit is rolled, that location's armor
    reads 0. Callers MUST pass armor_present using the armor pool value AFTER
    this hit's own armor consumption (e.g. apply_damage's loc[armor_key] after
    _consume_armor runs), never a pre-hit snapshot. Callers with no
    well-defined "this hit's own armor state" to check against (e.g. a bonus
    crit check not tied to a specific armor-consuming hit) should omit
    armor_type/armor_present entirely and take only the blanket structure
    component."""
    modifier = 0
    if armor_present and armor_type in (ArmorType.HARDENED, ArmorType.ANTI_PENETRATIVE_ABLATION):
        modifier -= 2
    if structure_type == StructureType.REINFORCED:
        modifier -= 1
    return modifier


def effective_damage(armor_type, damage_type, damage, armor_pool):
    """Pre-armor-CONSUMPTION effective damage: applies only the armor-type
    damage-REDUCING effects (Reactive, Ballistic-Reinforced, Ferro-Lamellor,
    Impact-Resistant - see _reduce_attack_damage_for_armor), not the actual
    armor-pool math (_consume_armor). Pure function - caller (damage_
    resolution.apply_damage) is responsible for resolving armor_type (incl.
    the REENGINEERED/Holy "treat as STANDARD" override) and armor_pool
    (the correct front/rear field for this hit) before calling in.

    Damage-reducing armor-type effects are a property of the armor ITSELF -
    once a location's armor is fully depleted there's nothing left to do the
    reducing, so raw damage passes through unmodified rather than keep
    getting the protective effect after the armor is gone. (Hardened doesn't
    need this gate: it degrades correctly on its own via _consume_armor,
    which naturally becomes full 1:1 pass-through once armor_pool hits 0.)"""
    if armor_pool > 0:
        return _reduce_attack_damage_for_armor(armor_type, damage_type, damage)
    return damage
