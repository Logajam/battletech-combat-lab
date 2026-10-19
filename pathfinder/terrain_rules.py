"""
terrain_rules.py — transition_cost(): the MP cost to enter a given
destination hex from a given current elevation. This is the only place
BattleTech terrain-cost numbers live. Per movement_pathfinder_handoff.md
Section 4c/6: do not add or change a numeric rule here from memory or
partial/uncertain search results — confirm with Daniel first, every time.

Costs confirmed directly by Daniel (not researched):
  - Rough: +1
  - Light woods (woods:1): +1
  - Heavy woods (woods:2): +2
  - Elevation change: +1 per level of difference
  - Road: +0, overrides underlying terrain cost
  - Water depth 1: +1
  - Water depth 2+: +2
  (base cost to enter any hex is 1; the above are all *additions* on top)

Bridges (bridge / bridge_cf / bridge_elev) are parsed by board_parser.py
but their cost/elevation-override interaction is NOT confirmed — any hex
carrying a bridge feature raises ValueError here rather than guessing.
"""

from typing import Dict, List

# =============================================================================
# ============================  CONFIG  ======================================
# =============================================================================

ROUGH_COST = 1
WOODS_LIGHT_COST = 1
WOODS_HEAVY_COST = 2
ELEVATION_COST_PER_LEVEL = 1
WATER_DEPTH_1_COST = 1
WATER_DEPTH_2_PLUS_COST = 2
BASE_ENTRY_COST = 1  # cost to enter any hex before terrain/elevation additions

# Features that add a terrain-cost component on top of BASE_ENTRY_COST.
# Only one of these is expected per hex; if more than one is present, the
# stacking rule isn't confirmed, so transition_cost() raises rather than
# guessing how to combine them.
COST_BEARING_FEATURES = {"rough", "woods", "water"}

# Road overrides whatever terrain-cost feature is also present (it doesn't
# remove elevation cost).
ROAD_FEATURE = "road"

# Not confirmed — flagged, not guessed. See module docstring.
UNRESOLVED_FEATURES = {"bridge", "bridge_cf", "bridge_elev"}

# =============================================================================
# ========================  END CONFIG  ======================================
# =============================================================================


def _terrain_cost(dest_features: Dict[str, List[str]]) -> int:
    if ROAD_FEATURE in dest_features:
        return 0  # overrides underlying terrain cost

    present = [f for f in dest_features if f in COST_BEARING_FEATURES]
    if len(present) > 1:
        raise ValueError(
            f"Destination hex has multiple cost-bearing terrain features "
            f"{present} — how these stack is not a confirmed BT rule in "
            f"this project. Flag for Daniel rather than guessing a sum/max."
        )
    if not present:
        return 0  # clear

    feature = present[0]
    params = dest_features[feature]

    if feature == "rough":
        return ROUGH_COST

    if feature == "woods":
        if not params:
            raise ValueError("'woods' feature present with no density param (expected 1 or 2).")
        density = params[0]
        if density == "1":
            return WOODS_LIGHT_COST
        if density == "2":
            return WOODS_HEAVY_COST
        raise ValueError(f"Unrecognized woods density {density!r} (expected '1' or '2').")

    if feature == "water":
        if not params:
            raise ValueError("'water' feature present with no depth param.")
        try:
            depth = int(params[0])
        except ValueError:
            raise ValueError(f"Non-integer water depth param {params[0]!r}.")
        if depth <= 0:
            raise ValueError(f"Invalid water depth {depth} (expected >= 1).")
        return WATER_DEPTH_1_COST if depth == 1 else WATER_DEPTH_2_PLUS_COST

    raise ValueError(f"Unhandled cost-bearing feature {feature!r} — add a case above.")


def transition_cost(
    current_level: int,
    dest_level: int,
    dest_features: Dict[str, List[str]],
) -> int:
    """
    MP cost to enter the destination hex, given the current hex's
    elevation and the destination hex's elevation + terrain features.

    Invariant this depends on (see handoff Section 4a): this must always
    return >= 1. If it could ever return 0, a state could be re-added to
    an already-finalized bucket in the DP sweep, breaking the
    process-each-layer-once guarantee build_movement_table relies on.
    """
    unresolved_present = UNRESOLVED_FEATURES & dest_features.keys()
    if unresolved_present:
        raise ValueError(
            f"Destination hex has unresolved terrain feature(s) "
            f"{sorted(unresolved_present)} — bridge cost/elevation-override "
            f"rules are not confirmed in this project (see "
            f"movement_pathfinder_handoff.md Section 4c/6). Ask Daniel "
            f"before adding a cost for these, don't guess."
        )

    cost = BASE_ENTRY_COST
    cost += _terrain_cost(dest_features)
    cost += abs(dest_level - current_level) * ELEVATION_COST_PER_LEVEL

    assert cost >= 1, f"transition_cost produced {cost} < 1 — violates the DP's load-bearing invariant."
    return cost
