"""
INTEGRATION__map_picker.py - choosing the battlefield (2026-10-28, Daniel:
"Wire in the map picker. Will need it for the next trick, making the program
easily accessible by a person, which is GUI work").

Two layers, so a GUI can reuse the first and replace the second:

  1. THE LIBRARY (no input, no printing - what a GUI calls):
       list_maps()              every board the program can load - the .board
                                files in data/ and the map pack data/maps.zip
                                - as MapInfo(name, group, width, height).
       resolve_board(name)      a path on disk for a map name (a pack map is
                                extracted once to a cache folder).
       playable(name)           [] if the simulator can play the map, else
                                what stops it (terrain_rules.prepare_board).
       compatible_maps(...)     the maps that fit a stitched grid slot (same
                                width down a column, same height along a row -
                                board_parser.stitch_boards' size rule).
       MapChoice / apply_choice the pick itself: board names, row-major, and
                                the grid shape; apply_choice writes it into
                                config (DEFAULT_BOARD_PATH, or STITCH_MAPS /
                                STITCH_BOARDS / STITCH_GRID_*).
       remembered_choice / remember_choice
                                last time's pick, kept with the file picker's
                                other remembered paths.
  2. THE CONSOLE MENU choose_map(ask=input, say=print): the questions a person
     is asked when config.PROMPT_FOR_MAP is on (orchestrator._load_map calls
     it once per run). ask / say are parameters so tests (and a GUI shim)
     can drive it.

A map name is the file name for a board in data/ ("16x17_Grassland_1.board")
and the path inside the zip for a pack map ("AGoAC Maps/16x17 Desert 2.board").
Config can name either one directly, with no prompt at all.
"""

import contextlib
import io
import os
import re
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from typing import Callable, List, Optional

import INTEGRATION__config as config
import INTEGRATION__file_picker as file_picker

_PACK = "maps.zip"                  # the MegaMek map pack, under config.DATA_DIR
_SIZE_LINE = re.compile(rb"^\s*size\s+(\d+)\s+(\d+)", re.MULTILINE)
_REMEMBER_AS = "map_choice"          # key in the file picker's remembered-paths store
_CACHE_DIR = os.path.join(tempfile.gettempdir(), "battletech_sim_maps")
_MENU_ROWS = 40                      # most maps listed at once before asking for a narrower filter


@dataclass(frozen=True)
class MapInfo:
    name: str          # what config and resolve_board() take
    group: str         # the pack's folder ("Battle of Tukayyid Pack"), or "data" for a loose file
    width: int
    height: int

    @property
    def size(self):
        return f"{self.width}x{self.height}"

    def describe(self):
        where = "" if self.group == "data" else f"  [{self.group}]"
        return f"{os.path.basename(self.name)}  {self.size}{where}"


@dataclass
class MapChoice:
    """The pick: board names row-major, and the grid they form (1 x 1 = one board)."""
    boards: List[str]
    cols: int = 1
    rows: int = 1

    def describe(self):
        if len(self.boards) == 1:
            return self.boards[0]
        return f"{self.cols} x {self.rows} stitched: " + ", ".join(os.path.basename(b) for b in self.boards)


# =============================================================================
# ===========================  THE LIBRARY  ===================================
# =============================================================================
def _pack_path():
    return config.data_path(_PACK)


def _size_of(raw):
    """(width, height) from the head of a board file's bytes."""
    found = _SIZE_LINE.search(raw)
    if not found:
        raise ValueError("no 'size W H' line")
    return int(found.group(1)), int(found.group(2))


def list_maps() -> List[MapInfo]:
    """Every loadable board, loose files first then the pack, each sorted by name."""
    maps = []
    for fname in sorted(os.listdir(config.DATA_DIR)):
        if fname.endswith(".board"):
            with open(os.path.join(config.DATA_DIR, fname), "rb") as f:
                width, height = _size_of(f.read(4096))
            maps.append(MapInfo(fname, "data", width, height))
    pack = _pack_path()
    if os.path.exists(pack):
        with zipfile.ZipFile(pack) as z:
            for member in sorted(z.namelist()):
                if member.endswith(".board"):
                    try:
                        width, height = _size_of(z.read(member)[:4096])
                    except ValueError:
                        continue                   # not a board the loader could read either
                    group = member.split("/")[0] if "/" in member else "pack"
                    maps.append(MapInfo(member, group, width, height))
    return maps


def resolve_board(name: str) -> str:
    """A path on disk for a map name: DATA_DIR's own file, an absolute path, or
    a pack map (extracted once into a cache folder)."""
    path = config.data_path(name)
    if os.path.exists(path):
        return path
    pack = _pack_path()
    if os.path.exists(pack):
        with zipfile.ZipFile(pack) as z:
            if name in z.namelist():
                out = os.path.join(_CACHE_DIR, *name.split("/"))
                if not os.path.exists(out):
                    os.makedirs(os.path.dirname(out), exist_ok=True)
                    with open(out, "wb") as f:
                        f.write(z.read(name))
                return out
    raise FileNotFoundError(f"No map called {name!r} (not in {config.DATA_DIR} nor in the {_PACK} pack).")


def playable(name: str) -> List[str]:
    """What stops the simulator from playing the map - [] if nothing. (Loads it
    like a battle would: board_parser, then terrain_rules.prepare_board.)"""
    import board_parser
    import terrain_rules
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            board = board_parser.parse_board_file(resolve_board(name))
            terrain_rules.prepare_board(board, passive_buildings=config.PASSIVE_BUILDINGS)
    except (ValueError, FileNotFoundError) as e:
        return [str(e)]
    return []


def compatible_maps(maps, chosen, cols, slot) -> List[MapInfo]:
    """Maps that fit grid slot `slot` (row-major index) given the boards already
    chosen (a list of MapInfo for slots 0..slot-1): same width as the boards
    above it in its column, same height as the boards beside it in its row."""
    row, col = divmod(slot, cols)
    widths = {chosen[r * cols + col].width for r in range(row)}
    heights = {chosen[row * cols + c].height for c in range(col)}
    return [m for m in maps if (not widths or m.width in widths) and (not heights or m.height in heights)]


def apply_choice(choice: MapChoice) -> None:
    """Write the pick into config, the way a person would have set it by hand."""
    if len(choice.boards) != choice.cols * choice.rows:
        raise ValueError(f"{len(choice.boards)} boards for a {choice.cols} x {choice.rows} grid")
    if len(choice.boards) == 1:
        config.STITCH_MAPS = False
        config.DEFAULT_BOARD_PATH = choice.boards[0]
    else:
        config.STITCH_MAPS = True
        config.STITCH_BOARDS = list(choice.boards)
        config.STITCH_GRID_COLS, config.STITCH_GRID_ROWS = choice.cols, choice.rows


def remember_choice(choice: MapChoice) -> None:
    file_picker._remember(_REMEMBER_AS, {"boards": choice.boards, "cols": choice.cols, "rows": choice.rows})


def remembered_choice() -> Optional[MapChoice]:
    saved = file_picker._remembered_path(_REMEMBER_AS)
    try:
        choice = MapChoice(list(saved["boards"]), int(saved["cols"]), int(saved["rows"]))
        for name in choice.boards:
            resolve_board(name)                       # still there?
        return choice if len(choice.boards) == choice.cols * choice.rows else None
    except (TypeError, KeyError, ValueError, FileNotFoundError):
        return None


# =============================================================================
# ===========================  THE CONSOLE MENU  ==============================
# =============================================================================
def _pick_one(maps, prompt, ask, say) -> MapInfo:
    """Numbered menu with a text filter: a number picks, any other text narrows
    the list (matches name, pack or size - "32x17", "tukayyid", "lake"), Enter
    clears the filter."""
    text = ""
    while True:
        shown = [m for m in maps if text.lower() in f"{m.name} {m.group} {m.size}".lower()]
        if not shown:
            say(f"  Nothing matches {text!r}.")
            text, shown = "", maps
        for i, m in enumerate(shown[:_MENU_ROWS], 1):
            say(f"  {i:3d}. {m.describe()}")
        if len(shown) > _MENU_ROWS:
            say(f"  ... {len(shown) - _MENU_ROWS} more - type part of a name, a pack or a size to narrow the list.")
        answer = ask(f"{prompt} [number, or text to filter]: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= min(len(shown), _MENU_ROWS):
            return shown[int(answer) - 1]
        text = answer


def _ask_grid(ask, say):
    while True:
        answer = ask("How many boards? Enter = one board; or columns x rows, like 2x1 or 3x2: ").strip().lower()
        if not answer:
            return 1, 1
        found = re.fullmatch(r"(\d+)\s*[x*,]\s*(\d+)", answer)
        if found and 1 <= int(found.group(1)) * int(found.group(2)) <= 12:
            return int(found.group(1)), int(found.group(2))
        say("  Say it as columns x rows, up to 12 boards in all.")


def choose_map(ask: Callable[[str], str] = input, say: Callable[[str], None] = print,
               maps: Optional[List[MapInfo]] = None) -> MapChoice:
    """Ask a person for the battlefield and return the pick (nothing is applied
    or remembered here - see prompt_and_apply). Offers last time's pick first,
    then a grid shape, then each board in turn with only the boards that fit
    the grid (and a playable check before it is taken)."""
    maps = maps if maps is not None else list_maps()
    say("\n" + "=" * 60 + "\nMAP SELECTION\n" + "=" * 60)
    last = remembered_choice()
    if last is not None:
        if ask(f"Last time: {last.describe()}\nUse it again? [Y/n]: ").strip().lower() not in ("n", "no"):
            return last
    cols, rows = _ask_grid(ask, say)
    chosen: List[MapInfo] = []
    for slot in range(cols * rows):
        row, col = divmod(slot, cols)
        label = "the map" if cols * rows == 1 else f"board {slot + 1} of {cols * rows} (column {col + 1}, row {row + 1})"
        fits = compatible_maps(maps, chosen, cols, slot)
        if not fits:
            raise ValueError(f"No map fits {label} - the boards chosen so far have sizes no board matches.")
        while True:
            pick = _pick_one(fits, f"Pick {label}", ask, say)
            problems = playable(pick.name)
            if not problems:
                break
            say(f"  {pick.describe()} can't be played yet: {problems[0]}")
        chosen.append(pick)
    return MapChoice([m.name for m in chosen], cols, rows)


def prompt_and_apply(ask: Optional[Callable[[str], str]] = None,
                     say: Callable[[str], None] = print) -> Optional[MapChoice]:
    """What orchestrator._load_map calls when config.PROMPT_FOR_MAP is on: with
    no person at the keyboard (a script, a pipe) keep the configured map; else
    ask, apply the pick to config and remember it. `ask` defaults to input()."""
    if ask is None:
        if not sys.stdin.isatty():
            say("PROMPT_FOR_MAP is on but there is no keyboard - keeping the configured map.")
            return None
        ask = input
    choice = choose_map(ask, say)
    apply_choice(choice)
    remember_choice(choice)
    say(f"  Map: {choice.describe()}")
    return choice
