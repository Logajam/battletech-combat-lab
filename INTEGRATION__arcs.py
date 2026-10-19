"""
INTEGRATION__arcs.py  (NEW 2026-10-19, Claude - Pile 3 rules)

Firing arcs (Core Rulebook p.60, Firing Arcs Diagram) and torso twists
(pp.61-62). Daniel supplied the diagram 2026-10-19; the rule text is in
rules/Battletech_Rule_Reference_Index.zip (combat-part1: CR-CMB1-FIRING-ARCS,
ARCS-TORSO-TWIST, TORSO-TWIST).

=== WHICH ARC A TARGET IS IN (read off the diagram, checked hex by hex) ===
Take the straight line from the attacker's hex centre to the target's hex
centre and measure its angle from the attacker's facing:
    within 60 degrees              FORWARD arc   (120 degrees wide)
    60-120 degrees, left / right   LEFT / RIGHT SIDE arc (60 degrees each)
    more than 120 degrees          REAR arc      (120 degrees wide)
A hex whose centre sits exactly on a boundary line goes to the forward arc
(against a side arc) or the side arc (against the rear arc) - that is how the
diagram colours 0903, 0905 and 0804 around the mech on 0704. Every one of the
diagram's labelled hexes is reproduced by tests/test_movement_selection.py.

!!! This REPLACES the old rule, "only the one hexside facing directly behind is
the rear arc (60 degrees)" (pathfinder/combat.py in_rear_arc, "Daniel,
corrected 2026-07-20"): the diagram's rear arc is 120 degrees wide, so hexes
like 0605 / 0805 (two hexes behind-and-aside of 0704) are in it. At range 1
the two agree (only the hex straight behind is rear).

=== WHICH WEAPONS CAN FIRE INTO AN ARC (p.60) ===
    forward  every weapon except rear-mounted ones
    left     left-arm weapons (and forward)      - a weapon whose slots are
    right    right-arm weapons (and forward)       split torso/arm is forward-only
    rear     rear-mounted weapons only
Arcs do not change when the attacker is prone. Leg-mounted weapons are not
moved by a torso twist.

=== TORSO TWIST (p.62) ===
Once per turn the torso turns one hexside left or right: the arcs of head,
torso and arm weapons shift with it (facing, and how the twisted mech is hit,
do not change); leg weapons keep the legs' forward arc. Prone mechs and quads
cannot twist. The attacker decides when declaring, so both the attack phase
(attack_resolution) and movement scoring (ranged_combat) try every twist and
keep the best.
Not modeled: reversing arms (p.62), tripod leg arcs / any-hexside twists
(p.236-237), turrets (p.61), a twist's effect on physical attacks.

Nothing here is a number: only geometry and the p.60 table. Twist direction:
+1 = right (clockwise), -1 = left.
"""

import functools
import math

FORWARD, LEFT, RIGHT, REAR = 0, 1, 2, 3
ARC_NAMES = {FORWARD: "forward", LEFT: "left side", RIGHT: "right side", REAR: "rear"}
_EPS = 1e-6


@functools.lru_cache(maxsize=None)
def arcs_between(a_hex, t_hex):
    """6-tuple: the arc t_hex is in for an attacker on a_hex facing 0..5
    (hex_geometry's facings: 0 = N, going clockwise). Hex coordinates are
    (column, doubled row) with +y toward north, so a column is 1.5 and a
    half-row sqrt(3)/2 centre-to-centre."""
    dx, dy = t_hex[0] - a_hex[0], t_hex[1] - a_hex[1]
    if dx == 0 and dy == 0:
        return (FORWARD,) * 6
    angle = math.degrees(math.atan2(math.sqrt(3) / 2 * dy, 1.5 * dx))
    out = []
    for facing in range(6):
        off = (angle - (90 - 60 * facing) + 180) % 360 - 180      # + = counter-clockwise (left) of facing
        size = abs(off)
        if size <= 60 + _EPS:
            out.append(FORWARD)
        elif size <= 120 + _EPS:
            out.append(LEFT if off > 0 else RIGHT)
        else:
            out.append(REAR)
    return tuple(out)


def twist_options(mech):
    """Torso twists the mech may declare: 0 (none), -1 (left), +1 (right)."""
    if mech.prone or mech.mech_type in ("quad", "quadvee"):
        return (0,)
    return (0, -1, 1)


@functools.lru_cache(maxsize=None)
def arc_keys(arcs, facing, twists):
    """Distinct (torso arc, legs see it forward?) pairs the mech can present
    to a target whose arcs-tuple is `arcs`, one per twist option."""
    legs_forward = arcs[facing] == FORWARD
    return tuple(dict.fromkeys((arcs[(facing + t) % 6], legs_forward) for t in twists))


def weapon_class(mech, weapon, locations):
    """'rear', 'leg', 'left_arm', 'right_arm' or 'torso' (head / torso /
    split-location: forward arc only, moved by a twist)."""
    if getattr(weapon, "rear_mounted", False):
        return "rear"
    locations = set(locations)
    if locations and locations <= set(mech.leg_locations):
        return "leg"
    if locations == {"Left Arm"}:
        return "left_arm"
    if locations == {"Right Arm"}:
        return "right_arm"
    return "torso"


def unavailable(mech, weapons, locations_by_weapon, torso_arc, legs_forward):
    """Ids of `weapons` that cannot fire at a target in `torso_arc` of the
    (possibly twisted) torso when the legs see it forward (`legs_forward`)."""
    blocked = set()
    for w in weapons:
        kind = weapon_class(mech, w, locations_by_weapon.get(id(w), ()))
        if kind == "rear":
            ok = torso_arc == REAR
        elif kind == "leg":
            ok = legs_forward
        elif kind == "left_arm":
            ok = torso_arc in (FORWARD, LEFT)
        elif kind == "right_arm":
            ok = torso_arc in (FORWARD, RIGHT)
        else:
            ok = torso_arc == FORWARD
        if not ok:
            blocked.add(id(w))
    return frozenset(blocked)
