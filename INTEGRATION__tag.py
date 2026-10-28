"""
INTEGRATION__tag.py  (NEW 2026-10-21, Claude - Pile 2 rules, Pile 4 choice as a stub)

Target Acquisition Gear (Core Rulebook p.200; TAG designation p.53).
Daniel, 2026-10-21: "Active probes and TAG could have a use in a 1 on 1
fight when smoke and homing ammo is included".

=== THE RULE ===
  - TAG attacks come after the Movement Phase and before the Ranged Attack
    Phase, in initiative order. The TN is a standard ranged attack's (no
    targeting computer). It counts as a ranged attack but not toward the
    targets engaged in the Ranged Attack Phase, and doesn't stop physical
    attacks.
  - A hit designates the target for that turn's Ranged Attack Phase (no hit
    location, no damage). Any number of attacks can use it - the TAG 'Mech's
    own too. Light TAG is TAG with a shorter range.
  - Uses in this simulator: Arrow IV / Thumper / Sniper homing rounds (p.190,
    INTEGRATION__fire_modes kind "homing"). Semi-guided missiles and
    Copperhead strikes also use it - no unit in data/meks.zip carries
    semi-guided rounds, and there are no off-board strikes in a duel.

=== THE DECISION ===
Whether to fire TAG is a stub (stubs.stub_fire_tag, default: when the 'Mech
has homing rounds to use it), and so is its aim (stubs.stub_tag_aim): the
enemy 'Mech, or the ground it stands on (Daniel, 2026-10-21: "if you aim at
the ground with the TAG so the splash damage hits the mech. (Ground is an
easier and thus better target some times. But that's a bot logic
question.)") - a hex attack, none of the 'Mech's own modifiers. A
designated hex: homing rounds deal the 5 AE to the 'Mech in it, hit or miss.
target.tag_designated: False, "mech" or "hex".

Not modeled: the torso twist / arm flip a 'Mech may make just before firing
TAG (it then can't twist again that turn) - TAG fires as the 'Mech faces;
spotting for indirect fire (no indirect fire in a duel).
"""

import INTEGRATION__config as config
import INTEGRATION__stubs as stubs
import INTEGRATION__weapon_rules as weapon_rules
import INTEGRATION__weapon_profiles as weapon_profiles
import INTEGRATION__fire_modes as fire_modes
import INTEGRATION__attack_resolution as attack_resolution
from damage_resolution import get_weapons
from mech_state import is_destroyed, all_crew_unconscious


def is_tag(weapon):
    """TAG or Light TAG (ISTAG, CLTAG, CLLightTAG)."""
    return weapon_rules.canonical_name(weapon).endswith("TAG")


def tags(mech):
    return [w for w in get_weapons(mech) if is_tag(w)]


def uses_designation(mech):
    """The 'Mech can use its own designation: a launcher with homing rounds."""
    return any(weapon_profiles.is_arrow(w) and ("homing", "") in fire_modes.bin_kinds(mech, w)
               for w in get_weapons(mech))


def designation_phase(first, second, terrain_map):
    """Between the Movement and Ranged Attack Phases, in initiative order
    (two mechs; designation_units is the general one)."""
    foe = {id(first): second, id(second): first}
    designation_units([first, second], lambda unit: foe[id(unit)], terrain_map)


def designation_units(order, target_of, terrain_map):
    """TAG designation for any number of units, in initiative order;
    target_of(unit) is the enemy it designates (None: nobody)."""
    for m in order:
        m.tag_designated = False
    for attacker in order:
        target = target_of(attacker)
        if target is not None:
            _designate(attacker, target, terrain_map)


def _designate(attacker, target, terrain_map):
    live = tags(attacker)
    if (not live or is_destroyed(attacker) or is_destroyed(target) or attacker.shutdown
            or all_crew_unconscious(attacker) or getattr(attacker, "charging", None) is not None
            or getattr(attacker, "dfa", None) is not None):
        return
    if not stubs.stub_fire_tag(attacker.side_name, uses_designation(attacker)):
        return
    at_mech = attack_resolution.single_attack_tn(attacker, target, terrain_map, live)
    at_hex = attack_resolution.single_attack_tn(attacker, target, terrain_map, live, at_hex=True)
    if at_mech is None and at_hex is None:
        config.log(f"  [TAG] {attacker.side_name} can't designate {target.side_name} (no LOS, range or arc).")
        return
    aim = stubs.stub_tag_aim(attacker.side_name, at_mech and at_mech[0], at_hex and at_hex[0])
    tn, weapon, note = at_hex if aim == "hex" else at_mech
    roll = config.roll_2d6(prompt=f"TAG roll ({weapon.name})")
    if roll >= tn and target.tag_designated != "mech":
        target.tag_designated = aim
    what = f"{target.side_name}'s hex" if aim == "hex" else target.side_name
    config.log(f"  [TAG] {attacker.side_name}'s {weapon.name} -> {what}: needs {tn} ({note}), rolled "
               f"{roll} -> {'DESIGNATED for this turn (p.200)' if roll >= tn else 'miss'}")
