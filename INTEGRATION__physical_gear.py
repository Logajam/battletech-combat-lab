"""
INTEGRATION__physical_gear.py  (NEW 2026-10-21, Claude - Pile 2 rules, Pile 4 choices as stubs)

Physical-combat equipment beyond the Physical Weapon Attacks Table (Core
Rulebook pp.194-196; Daniel, 2026-10-21: "Continue with the rulebook items.
Wire in equipment that requires choice ... but defer the actual bot decision
making for later"). INTEGRATION__physical, _charge and _dfa call in here.

=== TALONS (p.196) ===
Kick and death-from-above damage x1.5 (rounding normally). A biped needs
talons on both legs for a DFA, a tripod / quad two; a kick needs them on the
kicking leg (INTEGRATION__physical). A critical hit to the talons or to the
foot actuator in their leg destroys them.

=== SPIKES (p.196) ===
Defensive: a physical attack's damage to a spiked location is cut by 4 (to a
minimum of 1; before ferro-lamellor); unless the attack used a club or a
physical weapon, the attacker takes 2 damage, split evenly over the body
locations that delivered it (charge: centre torso; punch: that arm; kick:
that leg; DFA: both legs, 1 each). Offensive: a charging 'Mech with spikes in
its torsos may DECLARE their use (a choice - stubs.stub_charge_spikes): +2
damage per torso spike cluster, and each time a spiked location of the
attacker takes damage from that charge it rolls 1D6 - on a 1 that cluster is
destroyed.

=== LANCE (p.194) ===
A lance attack that damages only armor makes an armor-piercing check: 2D6
9+ deals 1 point of internal structure damage (not changed by TSM) and so a
critical-hit check. A 'Mech with a lance that hits with a charge makes the
same check, at 5+, on the first location the charge damages if it still has
armor afterwards. Two lances: one damage instance, two checks.
"""

import INTEGRATION__config as config
import INTEGRATION__stubs as stubs
from equipment import Equipment

SPIKE_REDUCTION = 4               # p.196: per physical damage instance to a spiked location
SPIKE_RETALIATION = 2             # p.196: to the attacker's delivering location(s)
SPIKE_CHARGE_BONUS = 2            # p.196: per torso spike cluster, offensive charge
TALON_MULTIPLIER = 1.5            # p.196
LANCE_AP_TN = 9                   # p.194: a lance attack that damaged only armor
LANCE_CHARGE_AP_TN = 5            # p.194: the first location a lance-charge damaged
TORSOS = ("Left Torso", "Right Torso", "Center Torso")


def _norm(name):
    return (name or "").replace(" ", "").replace("-", "").upper()


def _live(mech, loc, fragment):
    """Live Equipment in `loc` whose name holds `fragment`, one per instance."""
    seen = {}
    for s in mech.crits.get(loc, []):
        if isinstance(s, Equipment) and fragment in _norm(s.name):
            seen[id(s)] = s
    return list(seen.values())


def _foot_lost(mech, leg):
    return any(l == leg and info["name"] == "Foot Actuator" for (l, _), info in mech.destroyed_slot_info.items())


# =============================================================================
# ==========================  TALONS  =========================================
# =============================================================================
def talon_legs(mech):
    """Legs still on the 'Mech with working talons (p.196: a hit to the talons
    or the leg's foot actuator destroys them)."""
    return [leg for leg in mech.leg_locations
            if not mech.locations[leg]["destroyed"] and _live(mech, leg, "TALONS") and not _foot_lost(mech, leg)]


def dfa_talons(mech):
    """p.196 / p.80: a DFA gets the talon bonus with talons on both legs - a
    tripod or quad needs only two."""
    need = 2 if len(mech.leg_locations) > 2 else len(mech.leg_locations)
    return len(talon_legs(mech)) >= need


def with_talons(damage):
    return int(damage * TALON_MULTIPLIER + 0.5)      # rounding normally (.5 up)


# =============================================================================
# ==========================  SPIKES  =========================================
# =============================================================================
def spike_clusters(mech, loc):
    return len(_live(mech, loc, "SPIKES"))


def torso_spike_clusters(mech):
    return sum(spike_clusters(mech, t) for t in TORSOS if t in mech.locations)


def spike_reduce(target, loc, damage, label=""):
    """p.196: a physical attack's damage to a spiked location -4, minimum 1.
    Returns (damage, spiked?)."""
    if damage <= 0 or not spike_clusters(target, loc):
        return damage, False
    cut = max(1, damage - SPIKE_REDUCTION)
    config.log(f"      Spikes at {target.side_name}'s {loc}: {damage} -> {cut}{f' ({label})' if label else ''} (p.196).")
    return cut, True


def spike_retaliation(attacker, delivered_by):
    """p.196: the attacker takes 2 damage split evenly over the location(s)
    that delivered the attack (a list: one arm, one leg, the centre torso or
    both legs). Front of each, physical damage."""
    from damage_resolution import apply_damage
    from mech_state import DamageType, is_destroyed
    locs = [l for l in delivered_by if l in attacker.locations]
    if not locs:
        return
    share = SPIKE_RETALIATION // len(locs)
    for loc in locs:
        if is_destroyed(attacker):
            return
        config.log(f"      Spikes: {attacker.side_name} takes {share} to its {loc} (p.196).")
        apply_damage(attacker, loc, share, damage_type=DamageType.PHYSICAL)


def use_spikes_in_charge(attacker):
    """The declared choice (p.196) - only a 'Mech with torso spikes has it."""
    clusters = torso_spike_clusters(attacker)
    if not clusters:
        return False
    return stubs.stub_charge_spikes(attacker.side_name, clusters)


def charge_spike_bonus(attacker, used):
    return SPIKE_CHARGE_BONUS * torso_spike_clusters(attacker) if used else 0


def spike_wear(attacker, loc):
    """p.196: offensive spikes - each time a spiked location takes damage from
    the charge, 1D6: on a 1 one cluster there is destroyed."""
    clusters = _live(attacker, loc, "SPIKES")
    if not clusters:
        return
    die = config.pick_number(6, prompt="Spike cluster 1D6")
    if die == 1:
        from damage_resolution import resolve_slot_hit
        spike = clusters[0]
        idx = attacker.crits[loc].index(spike)
        config.log(f"      Spikes at {attacker.side_name}'s {loc}: 1D6 1 - the cluster is destroyed (p.196).")
        resolve_slot_hit(attacker, loc, idx, spike, 1, 1)


# =============================================================================
# ==========================  LANCE  ==========================================
# =============================================================================
def lances(mech):
    return [w for arm in ("Left Arm", "Right Arm") for w in _live(mech, arm, "LANCE")]


def lance_ap_check(target, loc, tn, why):
    """p.194: 2D6 >= tn deals 1 point of internal structure damage to `loc`
    (no TSM) and so a critical-hit check."""
    from damage_resolution import _explosion_structure
    from mech_state import is_destroyed
    if is_destroyed(target) or target.locations[loc]["destroyed"]:
        return
    roll = config.roll_2d6(prompt="Lance armor-piercing check")
    if roll < tn:
        config.log(f"      Lance armor-piercing check ({why}): needs {tn}, rolled {roll} - no effect (p.194).")
        return
    config.log(f"      Lance armor-piercing check ({why}): needs {tn}, rolled {roll} - 1 point to "
               f"{target.side_name}'s {loc} internal structure (p.194).")
    _explosion_structure(target, loc, 1, 0)


def armor_only(target, loc, before):
    """True if a hit on `loc` took armor but no internal structure:
    `before` = (armor + rear armor, structure) before the hit."""
    v = target.locations[loc]
    armor_now = v.get("armor", 0) + v.get("rear_armor", 0)
    return armor_now < before[0] and v["structure"] == before[1]


def snapshot(target, loc):
    v = target.locations[loc]
    return v.get("armor", 0) + v.get("rear_armor", 0), v["structure"]
