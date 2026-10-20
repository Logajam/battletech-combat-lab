"""
INTEGRATION__clubs.py  (NEW 2026-10-20, Claude - Pile 2 rules, Pile 4 choice)

Clubs (Core Rulebook p.79). The attack itself is a physical option in
INTEGRATION__physical (_club_options); this module has where clubs come from,
who can hold one, and when the bot picks one up.

=== THE RULE ===
  - Finding a club: in the Ranged Attack Phase, IN PLACE OF any other action
    that phase, a mech in a woods / jungle hex uproots a tree, one in a rubble
    hex salvages a girder, and any mech can pick up an arm or leg lying in its
    hex (blown off by a crit, or fallen off with its side torso).
  - Holding one: two hand actuators (claws count as hands) and both shoulders,
    none damaged or missing; if one is damaged while holding a club, the club
    is dropped in the mech's hex at the end of that phase.
  - Attacking: the target in the forward arc (a torso twist turns it, p.62),
    no arm-mounted weapon fired that turn; Piloting - 1, +2 per damaged
    upper / lower arm actuator, +2 with any claws; ceil(tons / 5) damage
    (TSM doubles, p.205) on the standard Hit Location Table (the Kick / Punch
    table against a mech a level up / down); the target makes a PSR. A tree
    breaks after one successful attack.

=== THE BOT (pile 4) ===
OFF by default (config.CLUB_PICKUP = False, Daniel 2026-10-20): a club is
almost never worth giving up the arm / torso weapons for. Whether it is
depends on what the mech will be able to do on LATER turns - a decision for
the bot's future-capability planning (PROJECT_MAP Section 6, "Memo").
With CLUB_PICKUP on, the rule is Claude's placeholder: pick one up only on a
turn it fires nothing anyway (no line of sight, nothing in arc or in range),
standing, not charging or in a DFA, with free hands; a limb or girder (they
last) before a tree. Once held, the club is just another physical plan in
movement scoring and the attack phases.
Open rules question (Daniel, 2026-10-20, "IIRC"): does HOLDING a club stop
the arm / front-torso weapons firing? The rules library (Core p.79) only bars
arm-mounted weapons in the turn of a club attack; check Total Warfare.

Not modeled: rubble from destroyed buildings (no buildings yet - a board
"rubble" feature is honoured), limbs carried off by displacement, wading
into a hex to pick a club up as part of the movement plan.
"""

import INTEGRATION__config as config

ARMS = ("Left Arm", "Right Arm")
LIMBS = ("Left Arm", "Right Arm", "Left Leg", "Right Leg", "Center Leg",
         "Front Left Leg", "Front Right Leg", "Rear Left Leg", "Rear Right Leg")
TREE_FEATURES = ("woods", "jungle")
RUBBLE_FEATURES = ("rubble",)

_LIMBS_ON_GROUND = {}          # hex label -> number of severed limbs lying there (this battle)


def reset_battle():
    _LIMBS_ON_GROUND.clear()


def _part_ok(mech, arm, part):
    """The design has the part in that arm and it isn't destroyed."""
    if any(loc == arm and info["name"] == part for (loc, _), info in mech.destroyed_slot_info.items()):
        return False
    return any(getattr(s, "name", s) == part for s in mech.crits.get(arm, []))


def _has_claw(mech, arm):
    return any("CLAW" in (getattr(s, "name", "") or "").replace(" ", "").upper() for s in mech.crits.get(arm, []))


def can_wield(mech):
    """p.79: both hands (or claws) and both shoulders, none damaged."""
    if mech.mech_type in ("quad", "quadvee"):
        return False
    for arm in ARMS:
        if arm not in mech.locations or mech.locations[arm]["destroyed"]:
            return False
        if not _part_ok(mech, arm, "Shoulder"):
            return False
        if not (_part_ok(mech, arm, "Hand Actuator") or _has_claw(mech, arm)):
            return False
    return True


def found_here(mech, terrain_map):
    """The kinds of club the mech could pick up in its hex, best first."""
    info = terrain_map["hexes"].get(mech.hex, {})
    features = info.get("features", {})
    kinds = []
    if _LIMBS_ON_GROUND.get(mech.hex):
        kinds.append("limb")
    if any(f in features for f in RUBBLE_FEATURES):
        kinds.append("girder")
    if any(f in features for f in TREE_FEATURES):
        kinds.append("tree")
    return kinds


def maybe_pick_up(mech, terrain_map, fired_anything):
    """Ranged phase, after declarations: the bot's pick-up rule (module
    docstring). Returns the kind picked up, or None."""
    if not config.CLUB_PICKUP:
        return None                    # off by default (Daniel, 2026-10-20) - see config.CLUB_PICKUP
    if getattr(mech, "club", None) or fired_anything or mech.prone or mech.shutdown:
        return None
    if getattr(mech, "charging", None) is not None or getattr(mech, "dfa", None) is not None:
        return None
    if not can_wield(mech):
        return None
    kinds = found_here(mech, terrain_map)
    if not kinds:
        return None
    kind = kinds[0]
    if kind == "limb":
        _LIMBS_ON_GROUND[mech.hex] -= 1
    mech.club = kind
    config.log(f"  [Ranged] {mech.side_name} picks up a {kind} club in {mech.hex} instead of firing (p.79).")
    return kind


def after_phase(mech):
    """End of a phase: limbs this mech lost this phase drop into its hex; a
    club it can no longer hold is dropped there too (p.79)."""
    lost = getattr(mech, "severed_limbs", None)
    if lost and mech.hex is not None:
        seen = mech.__dict__.setdefault("severed_seen", set())      # an arm blown off, then its torso: one limb
        new = {loc for loc in lost if loc in LIMBS and loc not in seen}
        seen |= new
        if new:
            _LIMBS_ON_GROUND[mech.hex] = _LIMBS_ON_GROUND.get(mech.hex, 0) + len(new)
        mech.severed_limbs = []
    club = getattr(mech, "club", None)
    if club and not can_wield(mech):
        config.log(f"  {mech.side_name} drops its {club} club in {mech.hex} (p.79).")
        if club == "limb" and mech.hex is not None:
            _LIMBS_ON_GROUND[mech.hex] = _LIMBS_ON_GROUND.get(mech.hex, 0) + 1
        mech.club = None


def used(mech):
    """A successful club attack: a tree breaks (p.79)."""
    if getattr(mech, "club", None) == "tree":
        config.log(f"    {mech.side_name}'s tree club breaks.")
        mech.club = None
