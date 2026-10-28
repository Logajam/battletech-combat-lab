"""INTEGRATION__domino.py - displacement into an occupied hex (NEW 2026-10-28, Claude).

A charge, a push or a death from above can force a 'Mech into a hex where
another 'Mech stands. With only two 'Mechs that never happened; with a third
unit on the board it does (Daniel, 2026-10-28: multi-unit battles). Core
Rulebook pp.113-116 (read from the rules library):

  Displacement (p.113-114): displaced into a hex of the same level, or one or
    two levels higher, that holds another 'Mech -> DOMINO EFFECT. One level
    lower and occupied -> domino too. Two or more levels lower and occupied
    -> ACCIDENTAL FALL FROM ABOVE. Empty hex: the action's own rules
    (charge / push / DFA code), not this module.
  Domino effect (p.114): the 'Mech already in the hex makes a PSR at once.
    Fail: it is displaced into the hex opposite the hexside the intruder
    entered by (the intruder's direction of travel) and falls there. Pass: it
    may dodge by stepping one hex directly forward or back, if standing,
    mobile, the hex is free and legal (the intruder's origin counts as
    occupied; no backward step after running); a pass that doesn't dodge is
    still forced into that next hex but doesn't fall. Another 'Mech there ->
    another domino, and so on; the last 'Mech with nowhere to go is destroyed.
  Accidental fall from above (p.116): the falling 'Mech attacks with TN 7 +
    the target's movement and terrain modifiers. A miss: it lands in a hex
    next to the target's, as close as possible to the hex it fell from
    (random among equals, empty hexes first) and falls normally. A hit:
    ceil(tons / 10) x max(1, levels fallen - target height) damage in
    5-point groupings (punch table if the target stands, hit table if
    prone); the falling 'Mech takes its normal fall damage on its rear; the
    target is displaced to a random neighbouring legal hex (even if prone)
    and makes a PSR at +2 or falls there. A 'Mech with no legal hex is
    destroyed.

Decisions that are the bot's: stepping aside from a domino (config.DOMINO_DODGE,
off - MegaMek's bots never do; BotClient answers the request with "no
action"). Not modeled: a submerged target's halved damage (p.116).
"""

import math

import INTEGRATION__config as config
import INTEGRATION__forces as forces
import INTEGRATION__hazards as hazards
from mech_state import is_destroyed, is_immobile
import hex_geometry
import combat
import piloting_rolls
import terrain_rules

def _ma():
    """INTEGRATION__movement_attacks (it imports the physical modules that import this one)."""
    import INTEGRATION__movement_attacks as movement_attacks
    return movement_attacks


def _ar():
    import INTEGRATION__attack_resolution as attack_resolution
    return attack_resolution


ACCIDENTAL_FALL_TN = 7           # p.116
ACCIDENTAL_TARGET_PSR = 2        # p.116: the displaced target's PSR modifier
DOMINO_PSR = 0                   # p.114: a plain Piloting Skill Roll


def occupant(label, exclude=()):
    """The 'Mech standing in `label` besides those in `exclude`, or None."""
    return forces.unit_in_hex(label, exclude)


def _psr(mech, modifier, what):
    """One PSR for `mech` (its own piloting skill); True if it passes."""
    base = piloting_rolls.preexisting_modifier(mech) + piloting_rolls.special_case_modifier(mech)

    def roll(m):
        return piloting_rolls.roll_psrs(m, 1, base + modifier, what)
    return _ar()._with_piloting(mech, roll)


def displace_into_occupied(mover, label, direction, drop, terrain_map, cause):
    """`mover` is being displaced from its hex into `label` (heading `direction`),
    one `drop` levels down (negative: up), and another 'Mech stands there. Resolves
    the domino effect or the accidental fall from above and leaves `mover` in its
    final hex - already fallen if it fell (the caller must not roll its fall again).
    Returns True when `mover` fell here."""
    origin = mover.hex
    other = occupant(label, exclude=(mover,))
    if other is None:
        mover.hex = label
        return False
    if drop >= 2:
        return _fall_from_above(mover, other, origin, label, drop, terrain_map, cause)
    config.log(f"    {mover.side_name} is displaced into {label}, where {other.side_name} stands: "
               f"DOMINO EFFECT (p.114).")
    mover.hex = label
    _push_out(other, direction, origin, terrain_map)
    return False


def _legal_dodges(mech, origin, direction, terrain_map):
    """Hexes `mech` may step into to dodge a domino: directly forward or back
    (its own facing), free, legal ground moves; none backward if it ran."""
    facing = hex_geometry.compass_to_facing(mech.facing)
    hexes = terrain_map["hexes"]
    options = []
    for step, backward in ((facing, False), ((facing + 3) % 6, True)):
        label = _ma().neighbour(mech.hex, step)
        if label is None or label not in hexes or label == origin or occupant(label, exclude=(mech,)):
            continue
        if backward and mech.move_mode == "Run":
            continue
        if terrain_rules.step_cost(hexes[mech.hex], hexes[label], backward=backward) is None:
            continue
        options.append(label)
    return options


def _push_out(other, direction, origin, terrain_map):
    """The domino effect on `other` (p.114): an intruder just entered its hex
    heading `direction` from `origin`."""
    name = other.side_name
    passed = _psr(other, DOMINO_PSR, f"[Domino] {name} PSR")
    if passed and config.DOMINO_DODGE and not other.prone and not is_immobile(other):
        dodges = _legal_dodges(other, origin, direction, terrain_map)
        if dodges:
            config.log(f"    {name} steps out of the way to {dodges[0]} (p.114).")
            other.hex = dodges[0]
            hazards.enter_hex(other, other.hex, why="stepped out of a domino effect", in_phase=True)
            return
    kind, label, drop = _ma().displacement(other.hex, direction, terrain_map)
    if kind == "off":
        other.destroyed, other.cause_of_death = True, "Displaced off the battlefield"
        config.log(f"    {name} is forced off the battlefield - destroyed (p.113).")
        return
    if kind == "blocked":
        other.destroyed, other.cause_of_death = True, "No room to be displaced (domino)"
        config.log(f"    {name} has no legal hex to be displaced into - destroyed (p.114).")
        return
    fell = False
    if occupant(label, exclude=(other,)) is not None:
        fell = displace_into_occupied(other, label, direction, drop, terrain_map, "a domino effect")
    else:
        old, other.hex = other.hex, label
        config.log(f"    {name} is forced {old} -> {label}{'' if passed else ' and falls'} (p.114).")
        hazards.enter_hex(other, label, why=f"forced into {label}", in_phase=True)
    if is_destroyed(other) or fell:
        return
    if drop >= 2:
        config.log(f"    {name} is displaced {drop} levels down - automatic fall (p.114).")
        piloting_rolls.resolve_fall(other, cause="domino effect, displaced down", levels=drop)
    elif not passed:
        piloting_rolls.resolve_fall(other, cause="failed the domino effect PSR")


def _neighbours(label, terrain_map):
    hexes = terrain_map["hexes"]
    out = []
    for d in range(6):
        n = _ma().neighbour(label, d)
        if n is not None and n in hexes:
            out.append((d, n))
    return out


def _fall_from_above(falling, target, origin, label, levels, terrain_map, cause):
    """p.116: `falling` is displaced `levels` down into `label`, where `target`
    stands. Returns True (the fall is resolved here)."""
    config.log(f"    {falling.side_name} is displaced {levels} levels down into {label}, where "
               f"{target.side_name} stands: ACCIDENTAL FALL FROM ABOVE (p.116).")
    a_xy, t_xy = hex_geometry.parse_hex_label(origin), hex_geometry.parse_hex_label(label)
    tmm = _ar()._target_tmm(target)
    terrain = _ma().terrain_modifier(a_xy, t_xy, terrain_map)
    tn = ACCIDENTAL_FALL_TN + tmm + terrain
    roll = config.roll_2d6(prompt="Accidental fall from above attack roll")
    hit = tn <= 12 and roll >= tn
    config.log(f"    Attack roll: needs {tn} (7 + TMM {tmm} + terrain {terrain}), rolled {roll} -> "
               f"{'HIT' if hit else 'miss'}")
    hexes = terrain_map["hexes"]
    if not hit:
        ring = _neighbours(label, terrain_map)
        if not ring:
            falling.destroyed, falling.cause_of_death = True, "Nowhere to land (fall from above)"
            return True
        dist = {n: hex_geometry_distance(origin, n) for _, n in ring}
        closest = min(dist.values())
        near = [n for _, n in ring if dist[n] == closest]
        free = [n for n in near if occupant(n, exclude=(falling,)) is None] or near
        landing = free[config.pick_number(len(free), prompt="Fall from above landing hex") - 1]
        falling.hex = landing
        config.log(f"    {falling.side_name} misses and lands in {landing} (p.116).")
        hazards.enter_hex(falling, landing, why=f"landed in {landing}", in_phase=True)
        lands_levels = max(0, hexes[origin]["level"] - hexes[landing]["level"])
        piloting_rolls.resolve_fall(falling, cause="accidental fall from above, missed", levels=lands_levels)
        if occupant(landing, exclude=(falling,)) is not None:
            _push_out(occupant(landing, exclude=(falling,)), movement_attacks_direction(label, landing),
                      label, terrain_map)
        return True
    height = _ar().los_height(target) - 1          # a standing 'Mech is 1 level tall, a prone one 0
    damage = math.ceil(falling.mass / 10) * max(1, levels - height)
    side = _ar().attack_side(a_xy, t_xy, hex_geometry.compass_to_facing(target.facing), terrain_map)
    table = "standard" if target.prone else "punch"
    config.log(f"    {falling.side_name} lands on {target.side_name}: {damage} damage ({table} table, {side}).")
    _ma().apply_groups(target, damage, table, side, "Fall from above")
    falling.hex = label
    piloting_rolls.resolve_fall(falling, cause="accidental fall from above", levels=levels, side="rear")
    if is_destroyed(target):
        return True
    options = [n for _, n in _neighbours(label, terrain_map)
               if terrain_rules.step_cost(None, hexes[n]) is not None
               and hexes[n]["level"] - hexes[label]["level"] < 3]
    if not options:
        target.destroyed, target.cause_of_death = True, "No legal hex to be displaced into (fall from above)"
        config.log(f"    {target.side_name} has no legal hex to be displaced into - destroyed (p.116).")
        return True
    new = options[config.pick_number(len(options), prompt="Fall from above displacement hex") - 1]
    d = movement_attacks_direction(label, new)
    target.hex = new
    config.log(f"    {target.side_name} is displaced to {new}.")
    hazards.enter_hex(target, new, why=f"displaced into {new}", in_phase=True)
    nxt = occupant(new, exclude=(target,))
    if nxt is not None:
        _push_out(nxt, d, label, terrain_map)
    if not _psr(target, ACCIDENTAL_TARGET_PSR, f"[Fall from above] {target.side_name} PSR"):
        piloting_rolls.resolve_fall(target, cause="displaced by a fall from above")
    return True


def hex_geometry_distance(a_label, b_label):
    return combat_distance(hex_geometry.parse_hex_label(a_label), hex_geometry.parse_hex_label(b_label))


def combat_distance(a_xy, b_xy):
    from los import hex_distance
    return hex_distance(a_xy, b_xy)


def movement_attacks_direction(from_label, to_label):
    """The facing 0-5 from one hex to an adjacent one."""
    return combat._direction_facing(hex_geometry.parse_hex_label(from_label), hex_geometry.parse_hex_label(to_label))
