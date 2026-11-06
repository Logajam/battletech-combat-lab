"""
tests/test_map_picker.py - the map picker (INTEGRATION__map_picker, 2026-10-28):
the library a GUI will call (listing, resolving, playable check, grid fit,
applying and remembering a pick) and the console menu, driven by scripted
answers.

    python tests/test_map_picker.py
"""

import os
import sys
import tempfile
import traceback

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402 - registers bare "config" first
config.STATS = False  # event log + report off: not part of a test or battery (2026-11-06)
import INTEGRATION__file_picker as file_picker  # noqa: E402
import INTEGRATION__map_picker as map_picker  # noqa: E402
import INTEGRATION__orchestrator as orchestrator  # noqa: E402

config.VERBOSE = False
file_picker._STATE_PATH = os.path.join(tempfile.mkdtemp(), "state.json")      # never touch the real remembered paths
CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


def scripted(*answers):
    """An `ask` that returns the answers in turn (and fails if it runs dry), and the prompts it saw."""
    left, seen = list(answers), []

    def ask(prompt):
        seen.append(prompt)
        assert left, f"asked more than expected: {prompt!r}"
        return left.pop(0)
    ask.seen, ask.left = seen, left
    return ask


def quiet(_text):
    pass


MAPS = map_picker.list_maps()
BY_NAME = {m.name: m for m in MAPS}


@check
def library_lists_loose_boards_and_the_pack():
    assert len(MAPS) > 300, len(MAPS)
    grass = BY_NAME["16x17_Grassland_1.board"]
    assert (grass.width, grass.height, grass.group) == (16, 17, "data")
    assert BY_NAME["32x17_Caustic_Valley_Lava.board"].size == "32x17"
    packed = [m for m in MAPS if m.group != "data"]
    assert packed and all("/" in m.name for m in packed)


@check
def resolve_reads_data_and_pack():
    assert os.path.exists(map_picker.resolve_board("16x17_Grassland_1.board"))
    pack_map = next(m for m in MAPS if m.group != "data" and m.size == "16x17")
    path = map_picker.resolve_board(pack_map.name)
    assert os.path.exists(path) and path.endswith(".board")
    try:
        map_picker.resolve_board("no such map.board")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("a missing map was resolved")


@check
def playable_says_what_stops_a_map():
    assert map_picker.playable("16x17_Grassland_1.board") == []
    problems = map_picker.playable("AGoAC Maps/16x17 Grassland 2 (Low Bridges).board")
    assert problems and "bridges" in problems[0], problems


@check
def stitched_slots_only_offer_boards_that_fit():
    a = BY_NAME["16x17_Grassland_1.board"]
    wide = BY_NAME["32x17_Caustic_Valley_Lava.board"]
    # 2 columns x 2 rows: slot 1 (right of a) must be as tall as a; slot 2 (below a) as wide as a.
    assert wide in map_picker.compatible_maps(MAPS, [a], 2, 1)          # 17 tall, like a
    assert wide not in map_picker.compatible_maps(MAPS, [a, a], 2, 2)   # 32 wide, a column of 16
    assert all(m.width == 16 for m in map_picker.compatible_maps(MAPS, [a, a], 2, 2))
    assert all(m.height == 17 for m in map_picker.compatible_maps(MAPS, [a], 2, 1))


@check
def console_menu_picks_one_board():
    ask = scripted("", "grassland_1", "1")          # one board; filter; take the first match
    choice = map_picker.choose_map(ask, quiet, MAPS)
    assert choice.boards == ["16x17_Grassland_1.board"] and (choice.cols, choice.rows) == (1, 1), choice
    assert not ask.left


@check
def console_menu_stitches_and_refuses_unplayable_boards():
    # 2x1; board 1: filter "lakes", take 1; board 2: filter "low bridges" (unplayable - refused), then "scattered".
    ask = scripted("2x1", "large_lakes", "1", "low bridges", "1", "scattered_woods", "1")
    choice = map_picker.choose_map(ask, quiet, MAPS)
    assert choice.boards == ["16x17_Large_Lakes_1.board", "16x17_Scattered_Woods.board"], choice.boards
    assert (choice.cols, choice.rows) == (2, 1)


@check
def apply_remember_and_ask_again():
    saved = (config.STITCH_MAPS, config.STITCH_BOARDS, config.STITCH_GRID_COLS, config.STITCH_GRID_ROWS,
             config.DEFAULT_BOARD_PATH)
    try:
        choice = map_picker.MapChoice(["16x17_Hilltops_1.board", "16x17_Scattered_Woods.board"], 2, 1)
        map_picker.apply_choice(choice)
        assert config.STITCH_MAPS and config.STITCH_BOARDS == choice.boards and config.STITCH_GRID_COLS == 2
        single = map_picker.MapChoice(["16x17_Hilltops_1.board"])
        map_picker.apply_choice(single)
        assert not config.STITCH_MAPS and config.DEFAULT_BOARD_PATH == "16x17_Hilltops_1.board"
        map_picker.remember_choice(choice)
        assert map_picker.remembered_choice() == choice
        again = scripted("")                                 # Enter = use it again
        assert map_picker.choose_map(again, quiet, MAPS) == choice and not again.left
        different = scripted("n", "", "grassland_1", "1")    # no; one board
        assert map_picker.choose_map(different, quiet, MAPS).boards == ["16x17_Grassland_1.board"]
        try:
            map_picker.apply_choice(map_picker.MapChoice(["16x17_Hilltops_1.board"], 2, 1))
        except ValueError:
            pass
        else:
            raise AssertionError("a pick that doesn't fill its grid was applied")
    finally:
        (config.STITCH_MAPS, config.STITCH_BOARDS, config.STITCH_GRID_COLS, config.STITCH_GRID_ROWS,
         config.DEFAULT_BOARD_PATH) = saved
        file_picker._save_state({})


@check
def load_map_asks_once_and_loads_the_pick():
    import builtins
    saved = (config.PROMPT_FOR_MAP, config.STITCH_MAPS, config.DEFAULT_BOARD_PATH)
    real_input, real_isatty = builtins.input, sys.stdin.isatty
    try:
        # No keyboard: the configured map is kept and nothing is asked.
        config.PROMPT_FOR_MAP = True
        config.DEFAULT_BOARD_PATH = "16x17_Hilltops_1.board"
        sys.stdin.isatty = lambda: False
        tm = orchestrator._load_map()
        assert (tm["width"], tm["height"]) == (16, 17) and config.DEFAULT_BOARD_PATH == "16x17_Hilltops_1.board"
        assert config.PROMPT_FOR_MAP is False                # asked (or skipped) once for the run
        # A person at the keyboard picks a pack map; it is applied and loaded.
        config.PROMPT_FOR_MAP = True
        sys.stdin.isatty = lambda: True
        ask = scripted("", "agoac maps/16x17 desert 2", "1")
        builtins.input = ask
        tm = orchestrator._load_map()
        assert config.DEFAULT_BOARD_PATH == "AGoAC Maps/16x17 Desert 2.board" and (tm["width"], tm["height"]) == (16, 17)
        assert not ask.left and config.PROMPT_FOR_MAP is False
    finally:
        builtins.input, sys.stdin.isatty = real_input, real_isatty
        config.PROMPT_FOR_MAP, config.STITCH_MAPS, config.DEFAULT_BOARD_PATH = saved
        file_picker._save_state({})


def run_all():
    failed = []
    for fn in CHECKS:
        try:
            fn()
            print(f"  {fn.__name__}: PASS")
        except Exception:
            failed.append(fn.__name__)
            print(f"  {fn.__name__}: FAILED")
            traceback.print_exc()
    if failed:
        print(f"\n{len(failed)} of {len(CHECKS)} map picker checks FAILED: {', '.join(failed)}")
        return 1
    print(f"\nAll {len(CHECKS)} map picker checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
