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

=== VIBROBLADES (p.196) ===
-2 to hit. Declared activated or not (a choice - stubs.stub_vibroblade):
activated it deals a fixed 7 / 10 / 14 (small / medium / large) whatever the
actuators or TSM, and makes 3 / 5 / 7 heat when the attack is declared;
deactivated, 1 per 10 tons + 1 (actuators and TSM as normal), never more than
the activated damage before TSM.

=== SHIELDS (p.195) ===
Small / medium / large: Damage Absorbance 3 / 5 / 7, Damage Capacity 11 / 18 /
25 (mech_state.SHIELD_SIZES; the MP and jump costs are mech_state's). A
LOWERED shield protects its own arm; a RAISED one (declared at the start of a
phase - a choice, stubs.stub_raise_shield) also the centre torso and the
same-side torso and leg (a tripod: not its centre leg), and then nothing in
those locations attacks that phase (rear-mounted weapons aside) and their AMS
is off. Damage from outside (not into the rear hit zone, not falls or
explosions) to a protected location loses up to the shield's DA, which comes
off its Capacity; at 0 the shield is gone. Absorbed damage doesn't count for
the 20-point PSR. Shield bash: a punch with the shield arm +1 / +2 / +3.
A charger with a raised shield takes the charge's groupings on that arm.
Two shields: only one raised at a time.
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


# =============================================================================
# ==========================  VIBROBLADES  ====================================
# =============================================================================
VIBRO = {"SMALL": (7, 3), "MEDIUM": (10, 5), "LARGE": (14, 7)}     # (damage, heat), p.196 / p.249


def vibro_size(slot):
    n = _norm(slot.name)
    return next((size for size in VIBRO if size in n), "MEDIUM")


def vibro_attack(mech, slot, deactivated_damage, tsm):
    """(damage, heat, activated?) for a vibroblade attack; deactivated_damage =
    1 per 10 tons + 1 before TSM and actuator halving (the cap applies to it)."""
    damage, heat = VIBRO[vibro_size(slot)]
    if stubs.stub_vibroblade(mech.side_name, slot.name, warn=False):
        return damage, heat, True
    return min(deactivated_damage, damage) * (2 if tsm else 1), 0, False


# =============================================================================
# ==========================  SHIELDS  ========================================
# =============================================================================
SHIELD_BASH = {"SMALL": 1, "MEDIUM": 2, "LARGE": 3}       # p.195: + damage to a punch with that arm
SIDE_OF = {"Left Arm": ("Left Torso", "Left Leg"), "Right Arm": ("Right Torso", "Right Leg")}


def _capacity(shield, size):
    """The shield's Damage Capacity left (kept on the Equipment instance)."""
    from mech_state import SHIELD_SIZES
    if getattr(shield, "shield_dc", None) is None:
        shield.shield_dc = SHIELD_SIZES[size][1]
    return shield.shield_dc


def raised_arm(mech):
    """The arm whose shield is raised this phase, or None."""
    return getattr(mech, "shield_raised", None)


def covered(mech, arm):
    """Locations a RAISED shield on `arm` protects (p.195)."""
    torso, leg = SIDE_OF[arm]
    locs = {arm, "Center Torso", torso}
    if mech.mech_type != "tripod" or leg != "Center Leg":
        locs.add(leg)
    return locs & set(mech.locations)


def declare_raise(mech, phase):
    """Start of an attack phase: raise a shield? (stubs.stub_raise_shield.)
    Sets mech.shield_raised for this phase and returns it."""
    from mech_state import mech_shields
    mech.shield_raised = None
    shields = [(arm, s, size) for arm, s, size in mech_shields(mech) if _capacity(s, size) > 0]
    if shields and not mech.prone:
        arm = stubs.stub_raise_shield(mech.side_name, phase, [a for a, _, _ in shields])
        if arm:
            mech.shield_raised = arm
            config.log(f"  [{phase}] {mech.side_name} raises its {arm} shield (p.195).")
    return mech.shield_raised


def lower(mech):
    mech.shield_raised = None


def raised_blocks(mech):
    """Locations that can't attack this phase behind a raised shield (p.195)."""
    arm = raised_arm(mech)
    return covered(mech, arm) if arm else set()


def shield_absorb(target, loc, damage, side):
    """Damage from outside to `loc` after the target's shields (p.195).
    Rear-hit-zone attacks bypass them."""
    from mech_state import mech_shields, SHIELD_SIZES
    if damage <= 0 or side == "rear":
        return damage
    raised = raised_arm(target)
    for arm, shield, size in mech_shields(target):
        if loc != arm and not (raised == arm and loc in covered(target, arm)):
            continue
        dc = _capacity(shield, size)
        if dc <= 0:
            continue
        took = min(damage, SHIELD_SIZES[size][0], dc)
        shield.shield_dc = dc - took
        config.log(f"      {target.side_name}'s {size.lower()} shield ({arm}) absorbs {took} of {damage} at {loc} "
                   f"(capacity left {shield.shield_dc}, p.195).")
        if shield.shield_dc <= 0:
            _wreck(target, arm, shield)
        return damage - took
    return damage


def _wreck(mech, arm, shield):
    """A shield whose Damage Capacity is used up is gone (its slots destroyed)."""
    config.log(f"      {mech.side_name}'s {arm} shield is destroyed (capacity used up).")
    for idx, s in enumerate(mech.crits[arm]):
        if s is shield:
            mech.destroyed_slot_info[(arm, idx)] = {"name": shield.name, "instance_id": id(shield)}
            mech.crits[arm][idx] = "DESTROYED"
    if raised_arm(mech) == arm:
        mech.shield_raised = None


def shield_bash(mech, arm):
    """+damage to a punch with `arm` from its shield (p.195)."""
    from mech_state import mech_shields
    return sum(SHIELD_BASH[size] for a, _, size in mech_shields(mech) if a == arm)
