"""
terrain_rules.py — what it costs to step into a hex, whether the step is
allowed at all, and which terrain a loaded map may contain. This is the only
place BattleTech terrain-cost numbers live. Per movement_pathfinder_handoff.md
Section 4c/6: do not add or change a numeric rule here from memory — check
the rules library and cite the page.

Costs (Core Rulebook Movement Costs Table, p.48; base cost to enter any hex
is 1, the rest are additions on top):
  - Rough +1, rubble +1, swamp +1 (p.127), sand +0, mud +0 for 'Mechs
  - Woods / jungle: light +1, heavy +2 (the table lists them together)
  - Water: depth 0 +0 (cosmetic for 'Mechs, p.122), depth 1 +1, depth 2+ +2
  - Pavement +0; a road hex entered off the road costs its underlying terrain
  - Level change +1 per level, up or down (p.46)
  - Stacked terrain: every modifier adds up (p.47, "Stacked Terrain")
Road travel (p.53): moving from one paved hex (road or pavement) to another
pays only the base 1 MP, and a level change between them costs 1 less (to a
minimum of 0).

Level-change limit (pp.46-47): ground movement may change at most 2 levels
per hex (1 with a destroyed hip actuator); a hex 3+ levels up is prohibited
terrain.

Buildings, PASSIVE version (Daniel, 2026-10-21, config.PASSIVE_BUILDINGS):
prepare_board() raises each building hex to its roof - its LOS level, the
hex's level plus the building's height (p.130) - so it blocks LOS like a
hill (p.135). Ground movement can't enter it from the ground (Daniel: "Can't
be entered"; p.46: a 'Mech can't move from the ground onto a roof); a 'Mech
can land on the roof by jumping (p.50). From a roof, ground movement may only
go to an adjacent roof at the same level or one lower, never higher and
never backward down a level, and never off the roof onto a non-building hex
(p.134); roofs are crossed as pavement (p.134). Not in the passive version:
forced entry, moving inside, damage, support limits / collapse (pp.132-136).

Not playable yet (prepare_board raises when a map has them, so a battle
never silently treats them as clear): bridges, ultra-heavy woods / jungle
(not in the Core Rulebook), and MegaMek terrain with no Core rule
(UNSUPPORTED_FEATURES).
"""

from typing import Dict, List, Optional

# =============================================================================
# ============================  CONFIG  ======================================
# =============================================================================

BASE_ENTRY_COST = 1  # cost to enter any hex before terrain/elevation additions (p.46)

# Terrain MP additions, Movement Costs Table (p.48).
ROUGH_COST = 1
RUBBLE_COST = 1
SWAMP_COST = 1           # p.127
SAND_COST = 0            # "+0 (+1)": the +1 is for wheeled Assets only
MUD_COST = 0             # "+0 (+1)": the +1 is for Assets only
WOODS_LIGHT_COST = 1     # woods and jungle share these rows
WOODS_HEAVY_COST = 2
WATER_DEPTH_0_COST = 0   # p.122: no rules effect for 'Mechs
WATER_DEPTH_1_COST = 1
WATER_DEPTH_2_PLUS_COST = 2
ELEVATION_COST_PER_LEVEL = 1   # p.46, up or down

# Ground-movement level-change limits (pp.46-47).
MAX_LEVEL_CHANGE = 2
MAX_LEVEL_CHANGE_HIP_DESTROYED = 1

# Road travel (p.53): the level-change cost between two paved hexes is this
# much lower, to a minimum of 0.
ROAD_LEVEL_CHANGE_DISCOUNT = 1

# Hexes a 'Mech travelling between them is "on the road" (p.53: "travelling
# on a road if it moves from one hex to the next on pavement").
PAVED_FEATURES = {"road", "pavement"}

# Woods / jungle density params the Core Rulebook has (1 light, 2 heavy).
# MegaMek's density 3 (ultra-heavy) is not in it.
WOODS_FEATURES = ("woods", "jungle")
CORE_WOODS_DENSITIES = {"1": WOODS_LIGHT_COST, "2": WOODS_HEAVY_COST}

# Terrain a map may carry that the simulator cannot play yet. prepare_board
# raises on any of them rather than letting a battle treat them as clear.
# (Bridges: pp.53, 131 - Daniel, 2026-10-21: "probably a pain"; the others
# have no Core Rulebook rule.)
UNSUPPORTED_FEATURES = {
    "bridge": "bridges (Core pp.53, 131) - not built yet",
    "fuel_tank": "fuel tanks (MegaMek terrain, no Core rule)",
    "magma": "magma (MegaMek terrain, no Core rule)",
    "hazardous_liquid": "hazardous liquid (MegaMek terrain, no Core rule)",
    "fortified": "fortified hexes (MegaMek terrain, no Core rule)",
    "impassable": "impassable hexes (MegaMek terrain, no Core rule)",
    "elevator": "elevators (MegaMek terrain, no Core rule)",
    "planted_fields": "planted fields (MegaMek terrain, no Core rule)",
}

# =============================================================================
# ========================  END CONFIG  ======================================
# =============================================================================


def _woods_cost(feature: str, params: List[str]) -> int:
    if not params:
        raise ValueError(f"'{feature}' feature present with no density param (expected 1 or 2).")
    density = params[0]
    if density not in CORE_WOODS_DENSITIES:
        raise ValueError(f"Unsupported {feature} density {density!r} (Core has 1 light, 2 heavy).")
    return CORE_WOODS_DENSITIES[density]


def _water_depth(params: List[str]) -> int:
    if not params:
        raise ValueError("'water' feature present with no depth param.")
    try:
        depth = int(params[0])
    except ValueError:
        raise ValueError(f"Non-integer water depth param {params[0]!r}.")
    if depth < 0:
        raise ValueError(f"Invalid water depth {depth} (expected >= 0).")
    return depth


def terrain_cost(features: Dict[str, List[str]]) -> int:
    """The hex's terrain MP addition (p.48), every terrain in it added up
    (p.47, Stacked Terrain). Road travel is handled by step_cost."""
    cost = 0
    if "rough" in features:
        cost += ROUGH_COST
    if "rubble" in features:
        cost += RUBBLE_COST
    if "swamp" in features:
        cost += SWAMP_COST
    if "sand" in features:
        cost += SAND_COST
    if "mud" in features:
        cost += MUD_COST
    for feature in WOODS_FEATURES:
        if feature in features:
            cost += _woods_cost(feature, features[feature])
    if "water" in features:
        depth = _water_depth(features["water"])
        cost += (WATER_DEPTH_0_COST if depth == 0 else
                 WATER_DEPTH_1_COST if depth == 1 else WATER_DEPTH_2_PLUS_COST)
    return cost


def is_paved(info: Dict[str, object]) -> bool:
    """Road, pavement, or a roof (p.134: crossed "as if the hex was pavement")."""
    return bool(info.get("building")) or any(f in info["features"] for f in PAVED_FEATURES)


def max_level_change(hip_destroyed: bool) -> int:
    """Most levels ground movement may climb or drop per hex (pp.46-47)."""
    return MAX_LEVEL_CHANGE_HIP_DESTROYED if hip_destroyed else MAX_LEVEL_CHANGE


def step_cost(
    from_info: Optional[Dict[str, object]],
    to_info: Dict[str, object],
    level_limit: int = MAX_LEVEL_CHANGE,
    backward: bool = False,
) -> Optional[int]:
    """
    MP for a ground-movement step from from_info's hex into to_info's, or
    None if the step isn't allowed. from_info None = entering the board from
    off it (deployment, p.37): no level change, no road travel.

    Invariant the pathfinder depends on (handoff Section 4a): an allowed step
    always costs >= 1, so a state can't be re-added to an already-finalized
    bucket in the DP sweep.
    """
    if to_info.get("impassable"):
        return None
    to_roof = bool(to_info.get("building"))
    from_roof = from_info is not None and bool(from_info.get("building"))
    to_level = to_info["level"]
    from_level = to_level if from_info is None else from_info["level"]
    change = to_level - from_level

    if to_roof and not from_roof:
        return None                      # can't move from the ground onto a roof (p.46)
    if from_roof and not to_roof:
        return None                      # nor off a roof without jumping (p.134)
    if from_roof and to_roof and change not in (0, -1):
        return None                      # roof to roof: same level or one lower (pp.46, 134)
    if abs(change) > level_limit:
        return None                      # pp.46-47: 2 levels (1 with a destroyed hip)
    if backward and change != 0:
        return None                      # backward level changes need a PSR mid-move - not offered (G11)

    on_road = from_info is not None and is_paved(from_info) and is_paved(to_info)
    if on_road:
        cost = BASE_ENTRY_COST + max(0, abs(change) - ROAD_LEVEL_CHANGE_DISCOUNT) * ELEVATION_COST_PER_LEVEL
    else:
        cost = BASE_ENTRY_COST + terrain_cost(to_info["features"]) + abs(change) * ELEVATION_COST_PER_LEVEL

    assert cost >= 1, f"step_cost produced {cost} < 1 — violates the DP's load-bearing invariant."
    return cost


def transition_cost(
    current_level: int,
    dest_level: int,
    dest_features: Dict[str, List[str]],
) -> int:
    """MP to enter a hex with dest_features at dest_level from a non-road hex
    at current_level (terrain + level change, no limits applied). Kept for
    the original tests and simple callers; movement uses step_cost."""
    unsupported = [f for f in dest_features if f in UNSUPPORTED_FEATURES]
    if unsupported:
        raise ValueError(f"Destination hex has unsupported terrain {sorted(unsupported)}: "
                         f"{'; '.join(UNSUPPORTED_FEATURES[f] for f in sorted(unsupported))}.")
    cost = BASE_ENTRY_COST + terrain_cost(dest_features) + abs(dest_level - current_level) * ELEVATION_COST_PER_LEVEL
    assert cost >= 1, f"transition_cost produced {cost} < 1 — violates the DP's load-bearing invariant."
    return cost


def prepare_board(terrain_map: Dict[str, object], passive_buildings: bool = True) -> Dict[str, object]:
    """
    Checks a parsed board for terrain the simulator can't play yet and sets up
    buildings; call once when a map loads. Raises ValueError naming every
    unsupported terrain (with hex counts) rather than letting a battle treat
    it as clear.

    Buildings (passive_buildings, Daniel 2026-10-21): each building hex keeps
    its ground level as "ground_level", its "level" becomes the roof's LOS
    level (hex level + bldg_elev, p.130), and "building" is set True - see the
    module docstring for what that allows. passive_buildings False (the full
    building rules, pp.130-136) isn't built yet and raises for a map that has
    buildings.

    Modifies terrain_map in place and returns it.
    """
    problems: Dict[str, int] = {}
    building_hexes = 0
    for label, info in terrain_map["hexes"].items():
        features = info["features"]
        for f in features:
            if f in UNSUPPORTED_FEATURES:
                key = UNSUPPORTED_FEATURES[f]
                problems[key] = problems.get(key, 0) + 1
        for f in WOODS_FEATURES:
            if f in features and (features[f][:1] or ["?"])[0] not in CORE_WOODS_DENSITIES:
                key = f"{f} density {(features[f][:1] or ['?'])[0]} (ultra-heavy; not in the Core Rulebook)"
                problems[key] = problems.get(key, 0) + 1
        if "building" in features:
            building_hexes += 1
            if passive_buildings and not info.get("building"):
                height = int((features.get("bldg_elev") or ["0"])[0])
                info["ground_level"] = info["level"]
                info["level"] = info["level"] + height
                info["building"] = True

    if building_hexes and not passive_buildings:
        problems["buildings with the full Core rules (pp.130-136) - not built; "
                 "set config.PASSIVE_BUILDINGS = True"] = building_hexes
    if problems:
        listing = "\n".join(f"  - {what}: {n} hex(es)" for what, n in sorted(problems.items()))
        raise ValueError(f"This map has terrain the simulator can't play yet:\n{listing}")
    return terrain_map
