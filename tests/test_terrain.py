"""
tests/test_terrain.py - map terrain added 2026-10-21 for MegaMek's map pack
(Daniel: "making sure more varied map functionality works"): MegaMek board
"option" lines, terrain costs and stacking (Core p.48, p.47), road travel
(p.53), the level-change limits (pp.46-47), jump landing height (p.50),
passive buildings (config.PASSIVE_BUILDINGS; pp.46, 50, 130, 134-135) and the
map check that refuses terrain the simulator can't play yet.

    python tests/test_terrain.py
"""

import os
import sys
import tempfile
import traceback

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402
import INTEGRATION__movement_attacks as movement_attacks  # noqa: E402
import board_parser  # noqa: E402
import terrain_rules  # noqa: E402
import combat  # noqa: E402
from hex_geometry import compass_to_facing, hex_label, parse_hex_label  # noqa: E402
from los import has_los  # noqa: E402
from pathfinder import build_movement_table, query_max_forward_count  # noqa: E402

config.VERBOSE = False

CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


def hexinfo(level=0, **features):
    """A hex dict as board_parser makes it: hexinfo(1, woods=["2"])."""
    return {"level": level, "features": {k: v for k, v in features.items()}, "impassable": False}


def board(changes=None, width=16, height=17):
    """A clear level-0 board with the given hexes changed: {label: hex dict}."""
    hexes = {f"{c:02d}{r:02d}": hexinfo() for c in range(1, width + 1) for r in range(1, height + 1)}
    hexes.update(changes or {})
    return {"width": width, "height": height, "hexes": hexes}


def reachable(terrain_map, start, compass="N", mp=6, level_limit=2):
    x, y = parse_hex_label(start)
    table = build_movement_table(x, y, compass_to_facing(compass), mp, terrain_map=terrain_map,
                                 level_limit=level_limit)
    return {hex_label(sx, sy) for (sx, sy, _f) in query_max_forward_count(table)}


@check
def board_option_lines():
    """MegaMek's "option exit_roads_to_pavement false" line (20 of the 16x17
    maps) used to stop the map loading."""
    text = 'size 2 1\noption exit_roads_to_pavement false\nhex 0101 0 "" ""\nhex 0201 0 "" ""\nend\n'
    with tempfile.NamedTemporaryFile("w", suffix=".board", delete=False) as f:
        f.write(text)
    try:
        b = board_parser.parse_board_file(f.name)
    finally:
        os.unlink(f.name)
    assert b["width"] == 2 and set(b["hexes"]) == {"0101", "0201"}


@check
def terrain_costs_and_stacking():
    """p.48 costs; p.122 depth-0 water is cosmetic; p.47 stacked terrain adds
    up (was: depth 0 and stacked costs raised)."""
    cost = terrain_rules.terrain_cost
    assert cost({}) == 0
    assert cost({"water": ["0"]}) == 0
    assert cost({"water": ["1"]}) == 1 and cost({"water": ["2"]}) == 2 and cost({"water": ["4"]}) == 2
    assert cost({"jungle": ["1"]}) == 1 and cost({"jungle": ["2", "18"]}) == 2
    assert cost({"rubble": ["1"]}) == 1 and cost({"swamp": ["1"]}) == 1
    assert cost({"sand": ["1"]}) == 0 and cost({"mud": ["1"]}) == 0
    assert cost({"pavement": ["1"]}) == 0
    assert cost({"rough": ["1"], "water": ["1"]}) == 2              # stacked
    assert cost({"swamp": ["1"], "water": ["1"]}) == 2
    assert cost({"woods": ["2"], "rough": ["1"]}) == 3


@check
def road_travel():
    """p.53: road to road pays only the base 1 MP, and a level change between
    road hexes costs 1 less; entering a road hex off the road pays its
    underlying terrain."""
    step = terrain_rules.step_cost
    road_woods = hexinfo(0, road=["1"], woods=["2"])
    assert step(hexinfo(0), road_woods) == 3                           # off-road: 1 + heavy woods 2
    assert step(hexinfo(0, road=["1"]), road_woods) == 1               # along the road
    assert step(hexinfo(0, pavement=["1"]), road_woods) == 1           # pavement counts as road
    assert step(hexinfo(0, road=["1"]), hexinfo(1, road=["1"])) == 1   # 1 level: 1 - 1 = 0 extra
    assert step(hexinfo(0, road=["1"]), hexinfo(2, road=["1"])) == 2   # 2 levels: 2 - 1 = 1 extra
    assert step(hexinfo(0), hexinfo(2, road=["1"])) == 3               # off-road: full level cost


@check
def level_change_limits():
    """pp.46-47: ground movement climbs or drops at most 2 levels a hex (a hex
    3+ up is prohibited), 1 with a destroyed hip; was: any height for 1 MP a
    level."""
    step = terrain_rules.step_cost
    assert step(hexinfo(0), hexinfo(2)) == 3
    assert step(hexinfo(0), hexinfo(3)) is None
    assert step(hexinfo(3), hexinfo(0)) is None
    assert step(hexinfo(0), hexinfo(2), level_limit=1) is None
    assert step(hexinfo(0), hexinfo(1), level_limit=1) == 2
    assert terrain_rules.max_level_change(False) == 2 and terrain_rules.max_level_change(True) == 1
    # A 3-level cliff north of 0808 (0807): plenty of MP, but no way up it.
    tm = board({"0807": hexinfo(3)})
    assert "0807" not in reachable(tm, "0808", mp=8)
    tm = board({"0807": hexinfo(2)})
    assert "0807" in reachable(tm, "0808", mp=8)
    assert "0807" not in reachable(tm, "0808", mp=8, level_limit=1)


@check
def jump_landing_height():
    """p.50: a jump can't land in a hex higher than the start level + Jumping
    MP (was: only the hexes passed over were checked)."""
    tm = board({"0806": hexinfo(3), "0805": hexinfo(4)})
    x, y = parse_hex_label("0808")
    lands = {hex_label(sx, sy) for (sx, sy, _f) in combat.build_jump_states(x, y, 3, tm)}
    assert "0806" in lands and "0805" not in lands


@check
def map_check_refuses_unplayable_terrain():
    """terrain_rules.prepare_board: bridges, fuel tanks and elevators (the full
    building rules) stop the map loading with a list, instead of being played
    as clear (bridges used to crash mid-battle). Ultra-heavy woods and magma
    play since 2026-10-27 (tests/test_hazards.py); a magma param MegaMek
    doesn't write is still refused."""
    for bad in ({"bridge": ["2", "18"], "bridge_cf": ["40"], "bridge_elev": ["0"]},
                {"fuel_tank": ["1", "0"]}, {"elevator": ["3", "2"]}, {"magma": ["7"]}):
        try:
            terrain_rules.prepare_board(board({"0505": hexinfo(0, **bad)}))
        except ValueError as e:
            assert "can't play yet" in str(e)
        else:
            raise AssertionError(f"{bad} should have been refused")
    terrain_rules.prepare_board(board({"0505": hexinfo(0, water=["0"], rough=["1"])}))   # fine


def city():
    """Level-0 board with a 3-level building (two hexes, 0806-0807) north of
    0808, a 2-level one at 0805, and a 1-level one at 1008."""
    b = board({
        "0806": hexinfo(0, building=["2", "9"], bldg_elev=["3"], bldg_cf=["40"]),
        "0807": hexinfo(0, building=["2", "9"], bldg_elev=["3"], bldg_cf=["40"]),
        "0805": hexinfo(0, building=["2", "9"], bldg_elev=["2"], bldg_cf=["40"]),
        "1008": hexinfo(0, building=["1", "9"], bldg_elev=["1"], bldg_cf=["15"]),
    })
    return terrain_rules.prepare_board(b, passive_buildings=True)


@check
def passive_buildings_setup():
    """Daniel, 2026-10-21: buildings as passive terrain. The hex's level
    becomes the roof's LOS level (hex level + building height, p.130); the
    full rules (PASSIVE_BUILDINGS False) refuse to load."""
    tm = city()
    assert tm["hexes"]["0807"]["level"] == 3 and tm["hexes"]["0807"]["ground_level"] == 0
    assert tm["hexes"]["0807"]["building"] and not tm["hexes"]["0808"].get("building")
    try:
        terrain_rules.prepare_board(board({"0505": hexinfo(0, building=["1"], bldg_elev=["1"])}),
                                    passive_buildings=False)
    except ValueError as e:
        assert "PASSIVE_BUILDINGS" in str(e)
    else:
        raise AssertionError("full building rules aren't built - the map should be refused")


@check
def passive_buildings_movement():
    """Can't walk into a building, even a 1-level one (p.46: no ground move
    onto a roof); roof to roof at the same level or one lower, never up
    (pp.46, 134); not off a roof onto the ground (p.134); a jump can land on
    a roof it can reach (p.50); a push from the ground into a building is
    blocked like a wall."""
    tm = city()
    h = tm["hexes"]
    assert terrain_rules.step_cost(h["0808"], h["1008"]) is None
    assert not {"0807", "0806", "0805", "1008"} & reachable(tm, "0808", mp=10)
    assert terrain_rules.step_cost(None, h["0807"]) == 1             # entering the board: onto a roof is fine
                                                                     # (Daniel, 2026-10-21 - no level before it enters)
    assert terrain_rules.step_cost(h["0807"], h["0806"]) == 1         # roof to roof, same level (as pavement)
    assert terrain_rules.step_cost(h["0806"], h["0805"]) == 1         # one lower: road discount makes it +0
    assert terrain_rules.step_cost(h["0805"], h["0806"]) is None      # never up
    assert terrain_rules.step_cost(h["0806"], h["0805"], backward=True) is None   # no backward level change
    assert terrain_rules.step_cost(h["0807"], h["0808"]) is None      # can't walk off a roof
    on_roof = reachable(tm, "0807", compass="N", mp=6)
    assert on_roof == {"0807", "0806", "0805"}, on_roof
    x, y = parse_hex_label("0808")
    lands = {hex_label(sx, sy) for (sx, sy, _f) in combat.build_jump_states(x, y, 3, tm)}
    assert {"0807", "0806", "1008"} <= lands
    lands = {hex_label(sx, sy) for (sx, sy, _f) in combat.build_jump_states(x, y, 2, tm)}
    assert "0807" not in lands and "1008" in lands
    assert movement_attacks.displacement("0808", compass_to_facing("N"), tm)[0] == "blocked"
    assert movement_attacks.displacement("0807", compass_to_facing("S"), tm) == ("moved", "0808", 3)


@check
def passive_buildings_block_los():
    """p.135: building hexes block LOS like hills of their roof level."""
    tm = city()
    assert not has_los(parse_hex_label("0808"), parse_hex_label("0804"), tm).los   # 0807 / 0806 in the way
    open_map = board()
    assert has_los(parse_hex_label("0808"), parse_hex_label("0804"), open_map).los


def _mechs():
    import INTEGRATION__orchestrator as orchestrator
    from mech_state import clone_mech
    from mtf_parser import parse_mtf
    out = []
    for name, side in (("Kontio.mtf", "Red"), ("Hammerhead.mtf", "Blue"), ("Black Hawk (Nova) F.mtf", "Red")):
        m = clone_mech(parse_mtf(config.data_path(name)))
        orchestrator._attach_mech_config(m, config.MECH_RED_CONFIG, side)
        out.append(m)
    return out


@check
def deployment_start_hexes():
    """Daniel, 2026-10-21: a mech may start its movement up to
    DEPLOYMENT_DEPTH hexes in (default 0), roofs included, but never where it
    would be stuck (no path to the far side for this unit); with no such hex,
    the override lets it start DEPLOYMENT_STUCK_DEPTH (3) hexes in."""
    import INTEGRATION__deployment as deployment
    walls = {f"{c:02d}{r:02d}": hexinfo(0, building=["4"], bldg_elev=["5"])
             for c in (1, 16) for r in range(1, 18)}                # a Solaris-style walled arena
    tm = terrain_rules.prepare_board(board(walls))
    kontio, _, hawk = _mechs()
    assert deployment.band(tm, "W", 0) == [f"01{r:02d}" for r in range(1, 18)]
    assert len(deployment.band(tm, "W", 3)) == 4 * 17
    start = deployment.start_hexes(kontio, tm, "W")                 # no jump jets: stuck on the wall
    assert start["depth"] == 3 and len(start["stuck"]) == 17
    assert set(start["hexes"]) == {f"{c:02d}{r:02d}" for c in (2, 3, 4) for r in range(1, 18)}
    start = deployment.start_hexes(hawk, tm, "W")                   # jumps down off the wall: fine
    assert start["depth"] == 0 and len(start["hexes"]) == 17 and not start["stuck"]
    start = deployment.start_hexes(kontio, board(), "N")            # open board: the edge, as before
    assert start["depth"] == 0 and start["hexes"] == deployment.band(board(), "N", 0)


@check
def no_start_hex_ends_the_battle():
    """p.37: a mech that can't move onto the battlefield is destroyed. A wall
    of buildings right across the board leaves a mech without jump jets no
    start hex from which it could reach the far side, at any depth: the
    battle ends on turn 1 with both destroyed (it used to crash in the
    Ranged phase with mechs that had no hex)."""
    import INTEGRATION__orchestrator as orchestrator
    from INTEGRATION__rng import BattleRNG
    wall = {f"{c:02d}09": hexinfo(0, building=["4"], bldg_elev=["5"]) for c in range(1, 17)}
    tm = terrain_rules.prepare_board(board(wall))
    red, blue, _ = _mechs()
    blue.side_name = "Blue"
    saved = config.HOME_EDGE_CHOICE
    config.HOME_EDGE_CHOICE = "N"
    try:
        result = orchestrator.run_battle(red, blue, tm, BattleRNG(seed=1), max_turns=3)
    finally:
        config.HOME_EDGE_CHOICE = saved
    assert result.turns_taken == 1 and result.destroyed == "Both", (result.turns_taken, result.destroyed)


@check
def stitched_map_loads_and_crosses_the_seam():
    """Map stitching (2026-10-28): config.STITCH_MAPS lays STITCH_BOARDS out
    row-major; seams follow MegaMek (Daniel, 2026-11-06): 16-wide boards abut
    with no gap (column parity kept, so each board sits as drawn), rows abut,
    and only an odd-width board gets one blank column after it. It keeps the
    first board's numbering, and a 'Mech can walk across the seam."""
    import INTEGRATION__orchestrator as orchestrator
    saved = (config.STITCH_MAPS, config.STITCH_BOARDS, config.STITCH_GRID_COLS, config.STITCH_GRID_ROWS)
    try:
        config.STITCH_MAPS, config.STITCH_GRID_COLS, config.STITCH_GRID_ROWS = True, 2, 2
        config.STITCH_BOARDS = ["16x17_Grassland_1.board", "16x17_Scattered_Woods.board",
                                "16x17_Hilltops_1.board", "16x17_Grassland_1.board"]
        tm = orchestrator._load_map()
        assert (tm["width"], tm["height"]) == (32, 34), (tm["width"], tm["height"])
        single = board_parser.parse_board_file(config.data_path("16x17_Grassland_1.board"))
        woods = board_parser.parse_board_file(config.data_path("16x17_Scattered_Woods.board"))
        hills = board_parser.parse_board_file(config.data_path("16x17_Hilltops_1.board"))
        assert tm["hexes"]["0305"]["level"] == single["hexes"]["0305"]["level"]   # first board: native labels
        # No seam column or row: every hex of boards 2 and 3 sits exactly 16 columns / 17 rows on.
        for c in range(1, 17):
            for r in range(1, 18):
                for got, want in ((tm["hexes"][f"{16 + c:02d}{r:02d}"], woods["hexes"][f"{c:02d}{r:02d}"]),
                                  (tm["hexes"][f"{c:02d}{17 + r:02d}"], hills["hexes"][f"{c:02d}{r:02d}"])):
                    assert (got["features"], got["impassable"]) == (want["features"], want["impassable"]), (c, r)
        # An odd width (MegaMek): one blank column after the board keeps the next one's parity.
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            odd = os.path.join(d, "odd.board")
            with open(odd, "w") as f:
                f.write("size 15 3\n" + "".join(f'hex {c:02d}{r:02d} 1 "" ""\n' for c in range(1, 16) for r in range(1, 4)) + "end\n")
            tm_odd = board_parser.stitch_boards([odd, odd], 2, 1)
            assert (tm_odd["width"], tm_odd["height"]) == (31, 3), (tm_odd["width"], tm_odd["height"])
            assert tm_odd["hexes"]["1602"]["level"] == 0 and tm_odd["hexes"]["1702"]["level"] == 1
        # Walk east across the seam on row 5.
        x, y = parse_hex_label("1405")
        table = build_movement_table(x, y, compass_to_facing("NE"), 6, terrain_map=tm)
        assert any(sx >= parse_hex_label("1805")[0] for sx, _, _ in table), "never crossed the seam"
        # Wrong number of boards: refused, not guessed.
        config.STITCH_BOARDS = ["16x17_Grassland_1.board"]
        try:
            orchestrator._load_map()
        except ValueError:
            pass
        else:
            raise AssertionError("a board list that doesn't fill the grid was accepted")
    finally:
        config.STITCH_MAPS, config.STITCH_BOARDS, config.STITCH_GRID_COLS, config.STITCH_GRID_ROWS = saved


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
    print()
    if failed:
        print(f"{len(failed)} of {len(CHECKS)} terrain checks FAILED: {', '.join(failed)}")
        return 1
    print(f"All {len(CHECKS)} terrain checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
