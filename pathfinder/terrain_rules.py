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
  - Level change +1 per level, up or down (p.46); water depth counts as
    levels (p.51) because prepare_board puts a water hex's level at its floor
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
can land on the roof by jumping (p.50), or start its movement on one when it
enters the battlefield (Daniel, 2026-10-21 - INTEGRATION__deployment). From a roof, ground movement may only
go to an adjacent roof at the same level or one lower, never higher and
never backward down a level, and never off the roof onto a non-building hex
(p.134); roofs are crossed as pavement (p.134). Not in the passive version:
forced entry, moving inside, damage, support limits / collapse (pp.132-136).

Tactical Operations: Advanced Rules terrain (2026-10-27, Daniel: "wire in
functionality of missing ... hex types already noted"):
  - Ultra-heavy woods / jungle (MegaMek density 3, TO:AR pp.29-30, 38):
    prohibited to 'Mechs (Expanded Movement Costs Table, p.30), so
    prepare_board marks the hex impassable; LOS: pathfinder/los.py.
  - Impassable hexes (MegaMek "impassable"): no unit may enter them. No
    rulebook text - the name is the rule (Claude's reading).
  - Fortified hexes (MegaMek "fortified"): a trench / fieldworks hex, whose
    only effect is the "digging in" bonus for infantry (TO:AUE p.153, TO:AR
    p.106) - no effect on 'Mechs, so the hex plays as its other terrain.
  - Planted fields: +0 MP and PSR (p.30); LOS and to-hit in los.py (p.36).
  - Magma (MegaMek 1 = crust, 2 = liquid, TO:AR pp.30, 34-35): crust +0 MP,
    liquid +1 MP (p.30); the damage, heat, crust breaking and bogging down
    are INTEGRATION__hazards'. Eruptions are an optional rule, not built.
  - Hazardous liquid pools (TO:AR p.47): "a water hex" for movement, PSRs
    and prohibition - MegaMek puts them on water hexes; the damage roll is
    INTEGRATION__hazards'.

Not playable yet (prepare_board raises when a map has them, so a battle
never silently treats them as clear): bridges, fuel tanks and industrial
elevators - all three lean on the full building rules (Core pp.53, 131;
TO:AR pp.132-136), which Daniel deferred (UNSUPPORTED_FEATURES).
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
# MegaMek's density 3 is ultra-heavy (TO:AR p.38): prohibited to 'Mechs.
WOODS_FEATURES = ("woods", "jungle")
CORE_WOODS_DENSITIES = {"1": WOODS_LIGHT_COST, "2": WOODS_HEAVY_COST}
ULTRA_HEAVY_DENSITY = "3"

# Magma (TO:AR p.30, Expanded Movement Costs Table): MegaMek's param 1 is a
# crust, 2 liquid magma. MP addition and the Piloting modifier of each.
MAGMA_CRUST, MAGMA_LIQUID = "1", "2"
MAGMA_COST = {MAGMA_CRUST: 0, MAGMA_LIQUID: 1}

# Terrain a map may carry that the simulator cannot play yet. prepare_board
# raises on any of them rather than letting a battle treat them as clear.
# (Bridges: pp.53, 131 - Daniel, 2026-10-21: "probably a pain"; fuel tanks
# and industrial elevators are buildings too (TO:AR pp.132-136), and the
# full building rules are deferred - Daniel, 2026-10-21.)
UNSUPPORTED_FEATURES = {
    "bridge": "bridges (Core pp.53, 131) - need the full building rules (deferred)",
    "fuel_tank": "fuel tanks (TO:AR pp.132-134) - buildings: need the full building rules (deferred)",
    "elevator": "industrial elevators (TO:AR pp.135-136) - buildings: need the full building rules (deferred)",
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


SUPERHEAVY_DISCOUNT = 1   # Core p.240: a superheavy pays 1 less to enter these terrains
SUPERHEAVY_DISCOUNTED = ("rough", "rubble", "woods", "jungle")   # (and foliage - no such terrain here)


def terrain_cost(features: Dict[str, List[str]], superheavy: bool = False) -> int:
    """The hex's terrain MP addition (p.48), every terrain in it added up
    (p.47, Stacked Terrain). Road travel is handled by step_cost.
    superheavy (2026-10-28, Core p.240): rough, rubble, woods and jungle each
    cost it 1 MP less (never below nothing)."""
    if superheavy:
        base = terrain_cost(features)
        cut = 0
        for f in SUPERHEAVY_DISCOUNTED:
            if f in features:
                alone = terrain_cost({f: features[f]})
                cut += min(SUPERHEAVY_DISCOUNT, alone)
        return base - cut
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
        if feature in features and (features[feature][:1] or [None])[0] != ULTRA_HEAVY_DENSITY:
            cost += _woods_cost(feature, features[feature])     # ultra-heavy: impassable (prepare_board)
    if "magma" in features:
        cost += MAGMA_COST[magma_state(features)]                # TO:AR p.30
    if "water" in features:
        depth = _water_depth(features["water"])
        cost += (WATER_DEPTH_0_COST if depth == 0 else
                 WATER_DEPTH_1_COST if depth == 1 else WATER_DEPTH_2_PLUS_COST)
    return cost


def magma_state(features) -> Optional[str]:
    """MAGMA_CRUST / MAGMA_LIQUID for a hex's features, None if no magma.
    MegaMek writes "magma:1" (crust) or "magma:2" (liquid); anything else is
    refused by prepare_board."""
    if "magma" not in features:
        return None
    return (features["magma"][:1] or [None])[0]


def is_paved(info: Dict[str, object]) -> bool:
    """Road, pavement, or a roof (p.134: crossed "as if the hex was pavement")."""
    return bool(info.get("building")) or any(f in info["features"] for f in PAVED_FEATURES)


class GroundLimit(int):
    """A mover's level limit (an int, as before) that also says whether the
    mover is a superheavy - so step_cost can give it its terrain discount
    (Core p.240) without a new argument through every path search."""
    superheavy = False

    def __new__(cls, value, superheavy=False):
        limit = int.__new__(cls, value)
        limit.superheavy = superheavy
        return limit


def max_level_change(hip_destroyed: bool, superheavy: bool = False) -> int:
    """Most levels ground movement may climb or drop per hex (pp.46-47);
    a GroundLimit carrying the superheavy flag (2026-10-28)."""
    return GroundLimit(MAX_LEVEL_CHANGE_HIP_DESTROYED if hip_destroyed else MAX_LEVEL_CHANGE, superheavy)


def step_cost(
    from_info: Optional[Dict[str, object]],
    to_info: Dict[str, object],
    level_limit: int = MAX_LEVEL_CHANGE,
    backward: bool = False,
) -> Optional[int]:
    """
    MP for a ground-movement step from from_info's hex into to_info's, or
    None if the step isn't allowed. from_info None = entering the board from
    off it (deployment, p.37): no level change, no road travel - and a roof
    may be entered (Daniel, 2026-10-21: "a mech's level before it enters is
    undefined. So it can enter on top of those level 5 walls"; whether it
    would be stuck there is INTEGRATION__deployment's check).

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

    if to_roof and from_info is not None and not from_roof:
        return None                      # can't move from the ground onto a roof (p.46)
    if from_roof and not to_roof:
        return None                      # nor off a roof without jumping (p.134)
    if from_roof and to_roof and change not in (0, -1):
        return None                      # roof to roof: same level or one lower (pp.46, 134)
    if abs(change) > level_limit:
        return None                      # pp.46-47: 2 levels (1 with a destroyed hip)
    if backward and change != 0:
        # Backward level change (p.46, 2026-10-21): one level only, a PSR each
        # time (step_psrs), never with a destroyed hip (p.47) nor on a roof (p.134).
        if abs(change) != 1 or level_limit < MAX_LEVEL_CHANGE or from_roof:
            return None

    on_road = from_info is not None and is_paved(from_info) and is_paved(to_info)
    if on_road:
        cost = BASE_ENTRY_COST + max(0, abs(change) - ROAD_LEVEL_CHANGE_DISCOUNT) * ELEVATION_COST_PER_LEVEL
    else:
        cost = (BASE_ENTRY_COST + terrain_cost(to_info["features"], getattr(level_limit, "superheavy", False))
                + abs(change) * ELEVATION_COST_PER_LEVEL)

    assert cost >= 1, f"step_cost produced {cost} < 1 — violates the DP's load-bearing invariant."
    return cost


# Terrain PSRs (Movement Costs Table p.48; Daniel's movement subphase,
# 2026-10-21): what a step or a facing change forces. Two counts - "always"
# (whatever the movement mode) and "run" (only if the move uses Running MP) -
# because the pathfinder doesn't know the move's mode until it ends.
PSR_TERRAIN_FEATURES = ("rubble", "sand", "mud", "water")


def step_psrs(from_info, to_info, backward=False):
    """(always, run_only) PSRs a ground step into to_info forces:
    rubble +0 (p.48); sand +0 only with a level change by ground movement
    (p.122); water depth 1+ +0 only with Running MP (p.48 fn 8, p.51); a
    backward level change +0 (p.46). from_info None = entering the board."""
    always = run_only = 0
    features = to_info["features"]
    if "rubble" in features:
        always += 1
    changes_level = from_info is not None and from_info["level"] != to_info["level"]
    if "sand" in features and changes_level:
        always += 1
    if to_info.get("depth", 0) >= 1:
        run_only += 1
    if backward and changes_level:
        always += 1
    return always, run_only


def turn_psrs(info):
    """(always, run_only) PSRs a facing change in this hex forces: mud, -1, if
    running (p.124)."""
    return (0, 1) if "mud" in info["features"] else (0, 0)


# PSR modifier for each trigger (p.48 / p.124): all +0 except mud's -1.
PSR_MODIFIER = {"rubble": 0, "sand": 0, "water": 0, "backward level change": 0, "mud": -1}


def step_psr_causes(from_info, to_info, backward, running):
    """The triggers step_psrs counts, as names (PSR_MODIFIER keys), for the
    mode actually used - the movement subphase rolls one PSR each."""
    causes = []
    features = to_info["features"]
    if "rubble" in features:
        causes.append("rubble")
    changes_level = from_info is not None and from_info["level"] != to_info["level"]
    if "sand" in features and changes_level:
        causes.append("sand")
    if running and to_info.get("depth", 0) >= 1:
        causes.append("water")
    if backward and changes_level:
        causes.append("backward level change")
    return causes


# Terrain that hurts a 'Mech entering it (TO:AR pp.34-35, 47 - INTEGRATION__
# hazards): the path-aware search also tracks it, so a board with any takes
# that search.
HAZARD_FEATURES = ("magma", "hazardous_liquid")


# Expected damage to a standing 'Mech entering such a hex (TO:AR): liquid
# magma 2D6 a leg (p.35); a crust breaks on 1 in 6 (p.34) and is then liquid;
# a pool's table averages (0 + 0 + 1.5 + 3.5 + 5.5 + 7) / 6 (p.47; 1D6/2
# rounded down averages 1.5). Movement scoring prices paths with it.
MAGMA_DAMAGE_PER_LEG = 7.0
POOL_EXPECTED_DAMAGE = 17.5 / 6


def step_hazard(info, legs: int = 2) -> float:
    """Expected damage a standing 'Mech with `legs` legs takes entering (or
    starting its Movement Phase in) this hex - INTEGRATION__hazards' rules.
    Bogging down and magma heat aren't priced."""
    features = info["features"]
    if not any(f in features for f in HAZARD_FEATURES):
        return 0.0
    out = 0.0
    state = magma_state(features)
    if state == MAGMA_LIQUID:
        out += MAGMA_DAMAGE_PER_LEG * legs
    elif state == MAGMA_CRUST:
        out += MAGMA_DAMAGE_PER_LEG * legs / 6
    if "hazardous_liquid" in features:
        out += POOL_EXPECTED_DAMAGE
    return out


def has_hazard_terrain(terrain_map) -> bool:
    """Does any hex of this board carry a hazard feature (magma, hazardous liquid)? Cached on the board;
    without one every step_hazard is 0.0 (2026-11-06, speed: movement scoring asks per spot)."""
    flag = terrain_map.get("_hazard_terrain")
    if flag is None:
        flag = terrain_map["_hazard_terrain"] = any(
            f in info["features"] for info in terrain_map["hexes"].values() for f in HAZARD_FEATURES)
    return flag


def has_psr_terrain(terrain_map) -> bool:
    """Can any step on this board force a terrain PSR - rubble, sand, mud,
    depth 1+ water, or a level change (a backward level change)? Or hurt -
    magma, hazardous liquid (2026-10-27)? Cached on the board. Without any,
    movement takes the plain (faster) search."""
    flag = terrain_map.get("_psr_terrain")
    if flag is None:
        hexes = terrain_map["hexes"].values()
        levels = {info["level"] for info in hexes}
        flag = len(levels) > 1 or any(
            info.get("depth", 0) >= 1 or any(f in info["features"] for f in ("rubble", "sand", "mud") + HAZARD_FEATURES)
            for info in hexes)
        terrain_map["_psr_terrain"] = flag
    return flag


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

    Water (2026-10-21): a water hex of depth 1+ keeps its surface level as
    "surface_level", its depth as "depth", and its "level" becomes the floor
    (surface - depth) - see INTEGRATION__water.

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
            density = (features[f][:1] or ["?"])[0] if f in features else None
            if density == ULTRA_HEAVY_DENSITY:
                info["impassable"] = True        # 'Mechs may not enter (TO:AR p.30); LOS: los.py
            elif density is not None and density not in CORE_WOODS_DENSITIES:
                key = f"{f} density {density} (not a TO:AR density)"
                problems[key] = problems.get(key, 0) + 1
        if "impassable" in features:
            info["impassable"] = True            # MegaMek's "impassable" (module docstring)
        if "magma" in features and magma_state(features) not in MAGMA_COST:
            key = f"magma {features['magma']} (MegaMek writes 1 crust, 2 liquid)"
            problems[key] = problems.get(key, 0) + 1
        if "hazardous_liquid" in features and "water" not in features:
            key = "hazardous liquid off a water hex (TO:AR p.47: a pool is a water hex)"
            problems[key] = problems.get(key, 0) + 1
        # Water (2026-10-21): the hex's level becomes the water's floor - the
        # surface level minus the depth (p.57: "a hex at Depth 2 ... is at
        # Level -2"; p.47: the printed level is the surface). A 'Mech in it
        # stands on the bottom, so level changes in and out (p.51), jumps
        # (p.50), LOS and falls (p.115) all see the depth. "depth" keeps it.
        if "water" in features and "depth" not in info:
            depth = _water_depth(features["water"])
            if depth >= 1:
                info["surface_level"] = info["level"]
                info["depth"] = depth
                info["level"] = info["level"] - depth
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
