"""
INTEGRATION__arcs.py  (NEW 2026-10-19, Claude - Pile 3 rules; arc actions 2026-10-19)

Firing arcs (Core Rulebook p.60, Firing Arcs Diagram), torso twists, reversing
(flipping) arms and turrets (pp.61-62), tripod arcs and twists (pp.236-237).
Daniel supplied the diagram 2026-10-19; the rule text is in
rules/Battletech_Rule_Reference_Index.zip (combat-part1: CR-CMB1-FIRING-ARCS,
ARCS-TORSO-TWIST, TORSO-TWIST; appendices-a-c: tripods, quads).

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
Arcs do not change when the attacker is prone. Leg-mounted weapons use the
legs' forward arc (the mech's facing) - a tripod's left / right leg arcs start
two hexsides left / right of the front (p.236), its centre leg's at the front.
Turret-mounted weapons ("(T)" on the crit line, with a Quad Turret, p.205) fire
into the turret's forward arc, which may point at any hexside (p.61).

=== ARC ACTIONS: TWIST, FLIP, TURRET (pp.61-62, 236) ===
An ArcAction(twist, flip, turret) is what a mech declares at the start of
attack declaration in the Ranged or the Physical phase (p.61):
  - twist: hexsides the torso turns (+ = right / clockwise). One hexside left
    or right; a tripod may pick ANY hexside (p.236). Shifts head, torso and arm
    weapon arcs, punches, clubs and physical weapons (p.62); never leg weapons,
    kicks (except a tripod's, p.236), the mech's facing or how it is hit (p.73).
  - flip: reverse both arms - arm weapons then fire only into the rear arc,
    and the mech can't punch or use arm physical weapons. Only a design with
    neither hand nor lower arm actuators in BOTH arms and no weapon split
    between torso and arm (p.62; FAQ p.243: all or nothing). Losing actuators
    to damage doesn't qualify a mech; losing an arm doesn't disqualify it.
  - turret: hexsides the turret is turned from the front (None = no working
    turret). Rotated whenever twists are declared, any number of hexsides,
    independent of the once-a-turn limit (p.61). A critical hit on the Quad
    Turret slot locks it, for the rest of the game, at the direction it had in
    the phase it was hit (p.205) - `turret_last_offset`, the last declared one.
Once a turn: a twist OR a flip, not both (p.61). Once declared it stands for
the rest of the turn (`arc_action_locked`); a mech that declared neither in the
Ranged phase may still twist in the Physical phase (p.76). End Phase: torso
forward, arms back (pp.40, 62) - `end_turn`.
Prone mechs cannot twist or flip (pp.51, 62); quads cannot twist (p.238).
TAG designation (p.53) would also use up the twist / flip, but TAG never fires
yet (stubs.unconfirmed_weapon_data), so that case can't arise.

=== SHOULDER AND HEAD TURRETS (TO:AUE p.159, 2026-10-27) ===
A "(T)" weapon in a location with a Shoulder Turret, or anywhere on a 'Mech
with a Head Turret (and no turret in its own location), turns to any facing
like a vehicle turret - here: it bears on a target in any arc of the
(twisted) torso, except that a shoulder turret may not fire through the
'Mech's opposite-side hexsides (a left shoulder turret: not into the right
side arc; a right one: not into the left), and a quad's head turret, when it
also has a quad turret, not into the rear arc. A critical hit on the turret
slot locks it at the facing it last had (`mech_turret_dir`, the direction it
last fired, as hexsides from the 'Mech's facing - Claude's reading: the lock
ignores later torso twists); a locked turret's weapons fire only into the
forward arc of that direction (an extra leg_offsets entry, "turret:<loc>").

Claude's calls (not in the rules): a rear-mounted weapon in a flipped arm still
fires only to the rear; a "(T)" weapon with no turret of any kind on the
'Mech is treated as fixed forward.

Nothing here is a number: only geometry and the p.60 table.
"""

import functools
import math
from typing import NamedTuple, Optional

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


class ArcAction(NamedTuple):
    twist: int = 0                  # hexsides the torso is turned, + = right (clockwise)
    flip: bool = False              # arms reversed
    turret: Optional[int] = None    # hexsides the turret is turned from the front; None = no turret


NO_ACTION = ArcAction()

# Leg weapon arcs: hexside offset of each leg's forward arc from the mech's facing (p.236).
TRIPOD_LEG_OFFSETS = {"Left Leg": -2, "Center Leg": 0, "Right Leg": 2}


def _norm(name):
    return (name or "").replace(" ", "").replace("-", "").upper()


def has_quad_turret(mech):
    return any(_norm(getattr(s, "name", s)).endswith("QUADTURRET")
               for slots in mech.crits.values() for s in slots)


MECH_TURRET_NAMES = ("SHOULDERTURRET", "HEADTURRET")


def mech_turrets(mech):
    """{location: "shoulder" / "head"} for the 'Mech's shoulder and head
    turrets (TO:AUE p.159), whether working or locked. Shared and kept while no
    slot is lost (damage_resolution.derived, 2026-11-06): do not edit it."""
    from damage_resolution import derived        # (MECHSIM; imported here: this module sits below it)
    return derived(mech, "mech_turrets", _mech_turrets)


def _mech_turrets(mech):
    out = {}
    for loc, slots in mech.crits.items():
        for s in slots:
            n = _norm(getattr(s, "name", s))
            if n.endswith("SHOULDERTURRET"):
                out[loc] = "shoulder"
            elif n.endswith("HEADTURRET"):
                out[loc] = "head"
    for (loc, _), info in mech.destroyed_slot_info.items():
        n = _norm(info["name"] if isinstance(info, dict) else info[0])
        if n.endswith("SHOULDERTURRET"):
            out.setdefault(loc, "shoulder")
        elif n.endswith("HEADTURRET"):
            out.setdefault(loc, "head")
    return out


def mech_turret_locked(mech, loc):
    """A crit on a shoulder / head turret slot locks it (TO:AUE p.159)."""
    return any(l == loc and _norm(info["name"] if isinstance(info, dict) else info[0]).endswith(MECH_TURRET_NAMES)
               for (l, _), info in mech.destroyed_slot_info.items())


def mech_turret_of(mech, locations):
    """The location of the shoulder / head turret a "(T)" weapon in
    `locations` sits in - its own location's, else the head turret's - or None."""
    turrets = mech_turrets(mech)
    for loc in locations:
        if loc in turrets:
            return loc
    heads = [loc for loc, kind in turrets.items() if kind == "head"]
    return heads[0] if heads else None


def turret_locked(mech):
    """A crit on the Quad Turret slot locks it for the rest of the game (p.205)."""
    return any(_norm(info["name"] if isinstance(info, dict) else info[0]).endswith("QUADTURRET")
               for info in mech.destroyed_slot_info.values())


def can_flip_arms(mech):
    """p.62: neither hand nor lower arm actuators in both arms of the DESIGN
    (destroyed ones still count as present), and no weapon split between a
    torso and an arm. A lost arm doesn't stop the other one flipping."""
    if mech.mech_type in ("quad", "quadvee") or not all(a in mech.crits for a in ("Left Arm", "Right Arm")):
        return False
    for arm in ("Left Arm", "Right Arm"):
        present = {getattr(s, "name", s) for s in mech.crits[arm]}
        present |= {info["name"] if isinstance(info, dict) else info[0]
                    for (loc, _), info in mech.destroyed_slot_info.items() if loc == arm}
        if present & {"Hand Actuator", "Lower Arm Actuator"}:
            return False
    seen = {}
    for loc, slots in mech.crits.items():
        for s in slots:
            if hasattr(s, "name") and getattr(s, "category", None) == "weapon":
                seen.setdefault(id(s), set()).add(loc)
    arms = {"Left Arm", "Right Arm"}
    return not any(locs & arms and locs - arms for locs in seen.values())


def twist_offsets(mech):
    """Torso twists the mech may declare: 0 (none), -1 (left), +1 (right);
    a tripod any hexside (p.236). Prone mechs and quads: none."""
    if mech.prone or mech.mech_type in ("quad", "quadvee"):
        return (0,)
    if mech.mech_type == "tripod":
        return (0, -1, 1, -2, 2, 3)
    return (0, -1, 1)


def current_action(mech):
    return getattr(mech, "arc_action", NO_ACTION)


def arc_options(mech, phase="ranged"):
    """Every ArcAction the mech may declare now, no change first (so ties keep
    the torso forward). After a twist or flip this turn only that one stands;
    the turret still turns unless it is locked."""
    turret_offsets = (None,)
    if has_quad_turret(mech):
        turret_offsets = ((getattr(mech, "turret_last_offset", 0),) if turret_locked(mech)
                          else (0, -1, 1, -2, 2, 3))
    if getattr(mech, "arc_action_locked", False):
        base = [current_action(mech)]
    else:
        base = [ArcAction(t) for t in twist_offsets(mech)]
        # Flipping in the Physical phase only takes punches and arm weapons away.
        if phase == "ranged" and not mech.prone and can_flip_arms(mech):
            base.append(ArcAction(flip=True))
    return tuple(a._replace(turret=t) for a in base for t in turret_offsets)


def twist_options(mech):
    """Back-compat view: the twists alone (see arc_options)."""
    return twist_offsets(mech)


def leg_offsets(mech):
    """(leg location, offset of its forward arc from the facing), in the
    mech's leg order - plus ("turret:<loc>", offset) for each LOCKED shoulder
    / head turret, whose forward arc is fixed the same way."""
    if mech.mech_type == "tripod":
        out = tuple((leg, TRIPOD_LEG_OFFSETS.get(leg, 0)) for leg in mech.leg_locations)
    else:
        out = tuple((leg, 0) for leg in mech.leg_locations)
    if getattr(mech, "mech_turret_dir", None) is not None or any(mech_turrets(mech)):
        dirs = getattr(mech, "mech_turret_dir", {}) or {}
        out += tuple((f"turret:{loc}", dirs.get(loc, 0)) for loc in mech_turrets(mech)
                     if mech_turret_locked(mech, loc))
    return out


class ArcKey(NamedTuple):
    """What decides which weapons bear on one target (scorer cache key)."""
    torso_arc: int                  # target's arc as seen by the (twisted) torso
    legs_forward: frozenset         # leg locations whose forward arc holds the target
    flip: bool
    turret_forward: Optional[bool]  # None = no turret


def simple_key(mech, torso_arc, legs_forward=True):
    """ArcKey for an untwisted, unflipped mech with the target in `torso_arc`
    (all legs see it forward or none do)."""
    return ArcKey(torso_arc, frozenset(mech.leg_locations) if legs_forward else frozenset(), False, None)


def key_for(arcs, facing, action, legs):
    """The ArcKey a target with arcs-tuple `arcs` presents to a mech facing
    `facing` that declared `action`, `legs` = leg_offsets(mech)."""
    return ArcKey(arcs[(facing + action.twist) % 6],
                  frozenset(leg for leg, off in legs if arcs[(facing + off) % 6] == FORWARD), action.flip,
                  None if action.turret is None else arcs[(facing + action.turret) % 6] == FORWARD)


@functools.lru_cache(maxsize=None)
def arc_keys(arcs, facing, actions, legs):
    """((ArcKey, first ArcAction giving it), ...) for a target whose
    arcs-tuple is `arcs`, one per distinct key among `actions`
    (arc_options), `legs` = leg_offsets(mech)."""
    out = {}
    for a in actions:
        out.setdefault(key_for(arcs, facing, a, legs), a)
    return tuple(out.items())


def weapon_class(mech, weapon, locations):
    """'turret', 'rear', 'leg', 'left_arm', 'right_arm' or 'torso' (head /
    torso / split-location: forward arc only, moved by a twist)."""
    if getattr(weapon, "turret_mounted", False) and has_quad_turret(mech) and mech_turret_of(mech, locations) is None:
        return "turret"
    if getattr(weapon, "turret_mounted", False):
        loc = mech_turret_of(mech, locations)
        if loc is not None:
            return f"turret:{loc}"                     # shoulder / head turret (TO:AUE p.159)
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


def unavailable(mech, weapons, locations_by_weapon, key):
    """Ids of `weapons` that cannot fire at a target seen as `key` (ArcKey)."""
    blocked = set()
    torso_arc = key.torso_arc
    for w in weapons:
        locs = locations_by_weapon.get(id(w), ())
        kind = weapon_class(mech, w, locs)
        if kind == "turret":
            ok = bool(key.turret_forward)
        elif kind.startswith("turret:"):
            ok = _mech_turret_bears(mech, kind[len("turret:"):], torso_arc, key)
        elif kind == "rear":
            ok = torso_arc == REAR
        elif kind == "leg":
            ok = all(l in key.legs_forward for l in locs)
        elif kind in ("left_arm", "right_arm") and key.flip:
            ok = torso_arc == REAR
        elif kind == "left_arm":
            ok = torso_arc in (FORWARD, LEFT)
        elif kind == "right_arm":
            ok = torso_arc in (FORWARD, RIGHT)
        else:
            ok = torso_arc == FORWARD
        if not ok:
            blocked.add(id(w))
    return frozenset(blocked)


def _mech_turret_bears(mech, loc, torso_arc, key):
    """A shoulder / head turret's weapons on a target in `torso_arc` (TO:AUE
    p.159, module docstring)."""
    if mech_turret_locked(mech, loc):
        return f"turret:{loc}" in key.legs_forward
    if mech_turrets(mech).get(loc) == "head":
        return not (has_quad_turret(mech) and torso_arc == REAR)
    side = "Left" if loc.startswith("Left") else "Right" if loc.startswith("Right") else None
    return not ((side == "Left" and torso_arc == RIGHT) or (side == "Right" and torso_arc == LEFT))


def note_mech_turret_fire(mech, weapon, locations, target_offset):
    """Remember where a working shoulder / head turret last pointed - the
    target's direction, hexsides from the 'Mech's facing - for a later lock."""
    kind = weapon_class(mech, weapon, locations)
    if kind.startswith("turret:") and not mech_turret_locked(mech, kind[len("turret:"):]):
        mech.__dict__.setdefault("mech_turret_dir", {})[kind[len("turret:"):]] = target_offset % 6


def declare(mech, action):
    """Record the ArcAction declared this phase. A twist or flip uses up the
    turn's one change (p.61); the turret direction is remembered for a lock."""
    mech.arc_action = action
    mech.torso_twist = action.twist
    mech.arms_flipped = action.flip
    if action.twist or action.flip:
        mech.arc_action_locked = True
    if action.turret is not None:
        mech.turret_last_offset = action.turret


def end_turn(mech):
    """End Phase: the torso turns forward and reversed arms return (pp.40, 62)."""
    mech.arc_action = NO_ACTION._replace(turret=current_action(mech).turret)
    mech.torso_twist = 0
    mech.arms_flipped = False
    mech.arc_action_locked = False


def describe(action):
    parts = []
    if action.twist:
        parts.append(f"twists its torso {abs(action.twist)} hexside{'s' if abs(action.twist) > 1 else ''} "
                     f"{'right' if action.twist > 0 else 'left'}")
    if action.flip:
        parts.append("reverses its arms")
    if action.turret:
        parts.append(f"turns its turret {abs(action.turret)} {'right' if action.turret > 0 else 'left'}")
    return " and ".join(parts)
