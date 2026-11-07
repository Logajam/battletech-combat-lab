"""
INTEGRATION__triage.py  (NEW 2026-11-07, Claude) - PERIL / TOUGHNESS TIERS (Daniel, 2026-11-07: "if you're in the top 10% of
peril / toughness, maybe you should move to minimize incoming damage"; and keep the team's units at a similar peril for their
toughness so the enemy splits its fire).

    config.TRIAGE = True               # default False
    config.TRIAGE_FRACTION = 0.25      # the share of the team in the hot tier, and the same share in the cool tier
    config.TRIAGE_HOT_RECEIVED = 2.0   # hot tier: the damage a spot would take counts this many times
    config.TRIAGE_COOL_DEALT = 1.5     # cool tier: the damage a spot would deal counts this many times

Each unit on the mover's team (the mover too, where it stands now) gets peril / toughness: the damage the enemy side could
bring to the hex it is on (INTEGRATION__peril, peak over every enemy's reachable spots, line of sight and cover applied)
divided by its effective HP (armor + rear armor + k x structure, the score's own units). Ranked across the team:
  HOT   the highest ratios (the top TRIAGE_FRACTION, at least one): in the most danger for how much it can take. Its move
        is scored with the damage taken multiplied by TRIAGE_HOT_RECEIVED: it moves to cut incoming damage first.
  COOL  the lowest ratios (the bottom TRIAGE_FRACTION): the safest for its toughness; its damage dealt is multiplied by
        TRIAGE_COOL_DEALT: it is the one to push in and take the fire.
  MID   everyone else: the score as it is.
Needs three or more units on the team (with fewer there is nothing to rank). A unit still off the board is MID.

THE MIRROR MAP (the other half, `reach_on`): what the mover's side could do to an ENEMY standing on each hex - the same
fields turned around (peril.team_field over our units against that enemy). Shown on the heat-map page ("Direction").
"""

import math

import INTEGRATION__config as config
import INTEGRATION__forces as forces
import INTEGRATION__movement_selection as movement_selection
import INTEGRATION__peril as peril
import INTEGRATION__vision as vision
import hex_geometry

HOT, MID, COOL = "hot", "mid", "cool"


def ratio(unit, enemies, terrain_map, vt):
    """peril / toughness for `unit` where it stands; None if it is off the board."""
    if unit.hex is None:
        return None
    xy = hex_geometry.parse_hex_label(unit.hex)
    peril_here = sum(peril.field_for(e, unit, terrain_map, vt=vt).at(xy, "peak") for e in enemies)
    return peril_here / max(1.0, movement_selection.effective_hp(unit))


def tier_of(mover, units, terrain_map):
    """HOT, MID or COOL for the mover among its team (see the module docstring)."""
    team = [u for u in forces.standing(units) if u.team == mover.team]
    if len(team) < 3 or mover.hex is None:
        return MID
    enemies = forces.enemies_of(mover, units)
    if not enemies:
        return MID
    vt = vision.table(terrain_map)
    scored = [(ratio(u, enemies, terrain_map, vt), id(u)) for u in team if u.hex is not None]
    if len(scored) < 3:
        return MID
    scored.sort(reverse=True)                                  # highest ratio first
    k = max(1, math.ceil(config.TRIAGE_FRACTION * len(scored)))
    order = [i for _, i in scored]
    rank = order.index(id(mover))
    if rank < k:
        return HOT
    if rank >= len(order) - k:
        return COOL
    return MID


def reach_on(friends, enemy, terrain_map, vt=None):
    """The mirror map: what `friends` could do to `enemy` standing on each hex (a peril.Field)."""
    return peril.team_field(friends, enemy, terrain_map, vt=vt)
