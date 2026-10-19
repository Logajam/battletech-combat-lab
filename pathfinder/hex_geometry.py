"""
hex_geometry.py — Doubled-coordinate hex grid, facing, and BT hex-label
conversion. This is the flat-terrain-agnostic geometry layer: nothing in
this module knows about MP cost, terrain, or boards. Terrain/board concerns
live in board_parser.py / terrain_rules.py / pathfinder.py.

CONFIG block below holds the only convention/calibration constants you
should need to touch (facing vectors, compass labels, hex-label offset
direction). Everything else in this module is mechanical.
"""

from typing import Dict, Tuple

# =============================================================================
# ============================  CONFIG  ======================================
# =============================================================================

# --- 1. Facing vectors -------------------------------------------------------
# Doubled-coordinate movement vector for each of the 6 facings. This is a
# project-specific coordinate scheme, NOT cross-checked against any other
# hex representation elsewhere (e.g. a separate mech-sim project). Confirm
# whether an established convention already exists before wiring this into
# anything else, and remap this dict to match if so.
FACING_DELTAS: Dict[int, Tuple[int, int]] = {
    0: (0, 2),
    1: (1, 1),
    2: (1, -1),
    3: (0, -2),
    4: (-1, -1),
    5: (-1, 1),
}

# --- 2. Compass labels for each facing --------------------------------------
# Standard BT movement facings, 0-indexed to match FACING_DELTAS (0=N,
# clockwise). Assumes facing 0 == north, i.e. +y is "up the board" and +x
# is "toward higher-numbered columns."
COMPASS_BY_FACING: Dict[int, str] = {
    0: "N",
    1: "NE",
    2: "SE",
    3: "S",
    4: "SW",
    5: "NW",
}

# --- 3. Hex-label column/row offset direction -------------------------------
# BT hex labels are the standard 4-digit "CCRR" format (2-digit column,
# 2-digit row, both 1-indexed, e.g. "0508" = column 5, row 8).
#
# CALIBRATED against ground truth Daniel provided directly: 0101 is the NW
# corner, the N-most row is all 0X01, and the first SE move from 0101 lands
# on 0201. These are locked-in regression tests in validation.py — if a
# real mapsheet ever disagrees, it means FACING_DELTAS/COMPASS_BY_FACING
# above don't match this project's actual compass convention, not that
# this offset is wrong.
ODD_INTERNAL_X_IS_SHIFTED = True  # internal x is 0-indexed; x odd <-> BT column is even

# =============================================================================
# ========================  END CONFIG  ======================================
# =============================================================================

FACING_BY_COMPASS: Dict[str, int] = {v: k for k, v in COMPASS_BY_FACING.items()}

State = Tuple[int, int, int]  # (x, y, facing)


def _row_parity_offset(x: int) -> int:
    is_shifted = (x % 2 == 1) if ODD_INTERNAL_X_IS_SHIFTED else (x % 2 == 0)
    return -1 if is_shifted else 0


def hex_label(x: int, y: int) -> str:
    """Internal doubled coords -> BT-style 'CCRR' hex label."""
    offset = _row_parity_offset(x)
    if (y - offset) % 2 != 0:
        raise ValueError(
            f"({x}, {y}) is not a valid hex center under the current "
            f"offset convention (ODD_INTERNAL_X_IS_SHIFTED="
            f"{ODD_INTERNAL_X_IS_SHIFTED}) — check for a coordinate bug."
        )
    col = x + 1
    row = 1 - (y - offset) // 2
    if col < 1 or row < 1:
        raise ValueError(f"({x}, {y}) maps to non-positive col/row ({col}, {row})")
    return f"{col:02d}{row:02d}"


def parse_hex_label(label: str) -> Tuple[int, int]:
    """BT-style 'CCRR' hex label -> internal doubled coords (x, y)."""
    label = label.strip()
    if len(label) != 4 or not label.isdigit():
        raise ValueError(f"Expected a 4-digit 'CCRR' hex label, got {label!r}")
    col, row = int(label[:2]), int(label[2:])
    x = col - 1
    offset = _row_parity_offset(x)
    y = 2 * (1 - row) + offset
    return x, y


def facing_to_compass(facing: int) -> str:
    if facing not in COMPASS_BY_FACING:
        raise ValueError(f"facing must be 0-5, got {facing}")
    return COMPASS_BY_FACING[facing]


def compass_to_facing(compass: str) -> int:
    compass = compass.strip().upper()
    if compass not in FACING_BY_COMPASS:
        raise ValueError(f"compass must be one of {sorted(FACING_BY_COMPASS)}, got {compass!r}")
    return FACING_BY_COMPASS[compass]


def describe_state(x: int, y: int, facing: int) -> str:
    """Human-readable 'hex label + facing' for a state, e.g. '0508 facing NE'."""
    return f"{hex_label(x, y)} facing {facing_to_compass(facing)}"


def state_from_label(hex_label_str: str, compass: str) -> State:
    """Convenience: 'CCRR' + compass string -> internal (x, y, facing) State."""
    x, y = parse_hex_label(hex_label_str)
    return (x, y, compass_to_facing(compass))
