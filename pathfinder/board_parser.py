"""
board_parser.py — Parses MegaMek `.board` files into a per-hex lookup
structure. Schema-only: knows nothing about MP cost (see terrain_rules.py)
or the DP/pathfinding (see pathfinder.py). Also provides stitch_boards()
for combining multiple .board files into one grid-arranged terrain_map
(see its docstring).

File format (as seen in the reference sample, 16x17_Grassland_1.board):

    size W H
    hex CCRR LEVEL "feature1:param1[:param2];feature2:..." "theme"
    ...
    end

- CCRR matches the hex-label format built in hex_geometry.py.
- LEVEL is integer elevation.
- The features string is semicolon-separated; each feature is
  "name[:param[:param2...]]" (params optional, colon-separated).
- Lines starting with '#' are comments; 'tag "..."' lines are cosmetic
  metadata and are skipped. 'option NAME VALUE' lines (MegaMek board
  settings, e.g. "option exit_roads_to_pavement false" - how MegaMek draws
  road ends; added 2026-10-21) carry no Core Rulebook rule and are skipped.

Recognized feature names (per movement_pathfinder_handoff.md Section 4b,
widened 2026-10-21 after a pass over MegaMek's map pack): woods / jungle
(1=light, 2=heavy), rough, rubble, sand, mud, swamp, water (depth as param),
road, pavement, buildings (building / bldg_*), bridges (bridge / bridge_*),
the other MegaMek terrain the pack uses, and purely cosmetic ones (the
*fluff codes, foliage_elev). Which of them the simulator can PLAY is
terrain_rules.py's call (terrain_rules.prepare_board rejects the rest when
a map loads); this list only stops the parser warning about names it knows.

Anything else encountered gets a WARNING (recoverable, not fatal) — the
parser's job is to capture what's on the map, not to judge whether every
feature is currently *used* by cost logic. That judgment happens in
terrain_rules.py.
"""

import re
from typing import Dict, List, Tuple

# =============================================================================
# ============================  CONFIG  ======================================
# =============================================================================

# Feature names this parser has seen in reference material and won't warn
# about. Anything outside this set still gets parsed and stored (nothing is
# dropped) but triggers a WARNING so an unrecognized code doesn't silently
# slip through unnoticed.
KNOWN_FEATURE_NAMES = {
    "woods", "jungle", "rough", "rubble", "sand", "mud", "swamp", "water",
    "road", "pavement",
    "building", "bldg_elev", "bldg_cf", "bldg_class", "bldg_armor", "bldg_basement_type",
    "bridge", "bridge_cf", "bridge_elev",
    "fuel_tank", "fuel_tank_cf", "fuel_tank_elev", "fuel_tank_magn",
    "magma", "hazardous_liquid", "fortified", "impassable", "elevator", "planted_fields",
    "arms", "legs",                               # MegaMek: severed limbs lying in the hex
    "ground_fluff", "foliage_elev", "fluff", "bldg_fluff", "road_fluff",   # cosmetic
}

# =============================================================================
# ========================  END CONFIG  ======================================
# =============================================================================

_HEX_LINE_RE = re.compile(
    r'^hex\s+(\d{4})\s+(-?\d+)\s+"([^"]*)"\s+"([^"]*)"\s*$'
)
_SIZE_LINE_RE = re.compile(r'^size\s+(\d+)\s+(\d+)\s*$')


def _parse_features(features_str: str) -> Dict[str, List[str]]:
    """'woods:1;foliage_elev:2' -> {'woods': ['1'], 'foliage_elev': ['2']}"""
    features: Dict[str, List[str]] = {}
    if not features_str:
        return features
    for chunk in features_str.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split(":")
        name, params = parts[0], parts[1:]
        features[name] = params
        if name not in KNOWN_FEATURE_NAMES:
            print(
                f"WARNING: unrecognized terrain feature '{name}' in .board "
                f"file (params={params}) — stored as-is, but no cost/rules "
                f"logic currently recognizes it."
            )
    return features


def parse_board_file(filepath: str) -> Dict[str, object]:
    """
    Parse a .board file into:
      {
        "width": int,
        "height": int,
        "hexes": {
          "CCRR": {"level": int, "features": {name: [params]}, "impassable": bool}
        }
      }

    NOTE: 'impassable' is always False currently. This schema does not
    (yet) have a confirmed rule for which feature(s) mark a hex impassable
    — none appear in the reference sample. Not guessed/invented; flagged
    here and in PROJECT_MAP_movement.md Known Issues rather than silently
    defaulted to a behavior.
    """
    width = height = None
    hexes: Dict[str, Dict[str, object]] = {}
    seen_end = False

    with open(filepath, "r") as f:
        for line_num, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("tag ") or line.startswith("option "):
                continue
            if line == "end":
                seen_end = True
                break

            size_match = _SIZE_LINE_RE.match(line)
            if size_match:
                width, height = int(size_match.group(1)), int(size_match.group(2))
                continue

            hex_match = _HEX_LINE_RE.match(line)
            if hex_match:
                label, level_str, features_str, theme = hex_match.groups()
                if label in hexes:
                    print(f"WARNING: duplicate hex '{label}' at line {line_num} — overwriting previous entry.")
                hexes[label] = {
                    "level": int(level_str),
                    "features": _parse_features(features_str),
                    "impassable": False,  # see docstring note above
                }
                continue

            raise ValueError(
                f"Unrecognized line {line_num} in board file {filepath!r}: {raw_line!r} — "
                f"does not match 'size W H', 'hex CCRR LEVEL \"features\" \"theme\"', "
                f"a comment, a tag or option line, or 'end'. Out of scope for this parser as written; "
                f"extend _HEX_LINE_RE/_SIZE_LINE_RE deliberately if this is a new valid format, "
                f"don't silently skip it."
            )

    if width is None or height is None:
        raise ValueError(f"Board file {filepath!r} never had a 'size W H' line.")
    if not seen_end:
        raise ValueError(f"Board file {filepath!r} never had a terminating 'end' line.")

    return {"width": width, "height": height, "hexes": hexes}


# MegaMek's columnPaddingWidth default (BoardUtilities.combine): the blank
# columns after an odd-width board. Must be odd, so the next board keeps its
# column parity.
ODD_WIDTH_PADDING = 1


def stitch_boards(board_paths: List[str], cols: int, rows: int) -> Dict[str, object]:
    """
    Combine multiple .board files into a single terrain_map, arranged in a
    cols x rows grid (X x Y), picked/ordered row-major (left to right, then
    down): for a 2x3 grid, board_paths[0..1] are row 1, [2..3] are row 2,
    [4..5] are row 3. The upper-left board (grid position 0,0) keeps its
    native CCRR numbering; every other board is renumbered with a column/row
    offset so the whole thing forms one continuous coordinate space.

    Seams follow MegaMek's convention (Daniel, 2026-11-06: "It should follow
    Megamek's conventions"; MegaMek BoardUtilities.combine, master 2026-11):
    boards ABUT - no gap between grid rows, and none between grid columns
    whose board width is even (a 16-wide sheet keeps the next board's column
    parity, so its terrain joins up as drawn). Only after a column of ODD
    width is one padding column inserted (MegaMek's default columnPaddingWidth
    of 1, kept odd), which restores the parity an odd width would flip.
    (Before this, Daniel's 2026-07-20 rule put a blank row / column at EVERY
    seam: 16 + 1 = 17 flipped every second board half a hex.)
    Difference from MegaMek: it fills the padding column with terrain blended
    from both neighbours (interpolated level and water, a random pick of
    their woods / rough...); here the padding is blank (level 0, no
    features), since that fill uses dice outside the battle's.

    Size rule (Daniel, 2026-07-20): every board in the same grid ROW must
    share the same height (they sit side by side and must align top/bottom);
    every board in the same grid COLUMN must share the same width (they
    stack vertically and must align left/right). Mismatched sizes raise
    ValueError rather than padding -- Daniel confirmed "throw an error",
    stitching same-sized maps only.

    board_paths: ordered list of file paths, row-major (see above).
    cols, rows: grid shape (X, Y) -- must satisfy len(board_paths) == cols*rows.

    Returns an in-memory dict, same shape as parse_board_file()'s return:
      {"width": int, "height": int, "hexes": {"CCRR": {level, features, impassable}}}
    No .board file is written to disk (Daniel confirmed in-memory only).
    """
    if len(board_paths) != cols * rows:
        raise ValueError(
            f"stitch_boards got {len(board_paths)} board path(s) but cols*rows "
            f"= {cols}*{rows} = {cols * rows} -- these must match exactly."
        )

    parsed = [parse_board_file(p) for p in board_paths]

    grid: Dict[Tuple[int, int], Dict[str, object]] = {}
    for i, board in enumerate(parsed):
        grid_row, grid_col = i // cols, i % cols
        grid[(grid_row, grid_col)] = board

    # --- Size validation: same row -> same height, same column -> same width ---
    row_heights: Dict[int, int] = {}
    for grid_row in range(rows):
        heights_in_row = {grid[(grid_row, c)]["height"] for c in range(cols)}
        if len(heights_in_row) > 1:
            raise ValueError(
                f"Grid row {grid_row} has mismatched board heights {sorted(heights_in_row)} -- "
                f"all boards in the same grid row must share the same height. Padding is not "
                f"supported; use same-sized maps."
            )
        row_heights[grid_row] = heights_in_row.pop()

    col_widths: Dict[int, int] = {}
    for grid_col in range(cols):
        widths_in_col = {grid[(r, grid_col)]["width"] for r in range(rows)}
        if len(widths_in_col) > 1:
            raise ValueError(
                f"Grid column {grid_col} has mismatched board widths {sorted(widths_in_col)} -- "
                f"all boards in the same grid column must share the same width. Padding is not "
                f"supported; use same-sized maps."
            )
        col_widths[grid_col] = widths_in_col.pop()

    # --- Offsets (MegaMek seams): rows abut; a column abuts the next unless its
    #     width is odd, which adds ODD_WIDTH_PADDING blank columns after it ---
    def _pad_after(grid_col: int) -> int:
        if grid_col == cols - 1:
            return 0
        return ODD_WIDTH_PADDING if col_widths[grid_col] % 2 else 0

    col_offset: Dict[int, int] = {}
    running = 0
    for grid_col in range(cols):
        col_offset[grid_col] = running
        running += col_widths[grid_col] + _pad_after(grid_col)
    total_width = running

    row_offset: Dict[int, int] = {}
    running = 0
    for grid_row in range(rows):
        row_offset[grid_row] = running
        running += row_heights[grid_row]
    total_height = running

    if total_width > 99 or total_height > 99:
        print(
            f"WARNING: stitched board is {total_width}x{total_height}, exceeding the 2-digit "
            f"CCRR convention (max 99x99) -- resulting hex labels will be 5+ characters and "
            f"won't round-trip through hex_geometry.parse_hex_label()."
        )

    # --- Canvas: every hex starts blank (BigBlank.board style), then boards overwrite their cells ---
    hexes: Dict[str, Dict[str, object]] = {}
    for col in range(1, total_width + 1):
        for row in range(1, total_height + 1):
            hexes[f"{col:02d}{row:02d}"] = {"level": 0, "features": {}, "impassable": False}

    for (grid_row, grid_col), board in grid.items():
        c_off = col_offset[grid_col]
        r_off = row_offset[grid_row]
        for label, info in board["hexes"].items():
            local_col, local_row = int(label[:2]), int(label[2:])
            new_label = f"{c_off + local_col:02d}{r_off + local_row:02d}"
            hexes[new_label] = info

    return {"width": total_width, "height": total_height, "hexes": hexes}
