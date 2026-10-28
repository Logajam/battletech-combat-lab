"""
tests/test_hazards.py - the Tactical Operations: Advanced Rules hex types
wired in 2026-10-27 (Daniel: "wire in functionality of missing weapons,
equipment, and hex types already noted"): ultra-heavy woods, impassable,
fortified and planted-field hexes (pathfinder/terrain_rules.py, los.py) and
magma, hazardous liquid pools and bogging down (INTEGRATION__hazards).

    python tests/test_hazards.py

Dice are scripted the same way as tests/test_heat.py.
"""

import os
import sys
import traceback

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
import INTEGRATION__attack_resolution as attack_resolution  # noqa: E402
import INTEGRATION__hazards as hazards  # noqa: E402
import INTEGRATION__heat as heat  # noqa: E402
import INTEGRATION__water as water  # noqa: E402
import terrain_rules  # noqa: E402
from hex_geometry import parse_hex_label, hex_label, compass_to_facing  # noqa: E402
from los import has_los  # noqa: E402
from pathfinder import build_movement_table  # noqa: E402
from mech_state import clone_mech  # noqa: E402
from mtf_parser import parse_mtf  # noqa: E402
from test_heat import ScriptedDice  # noqa: E402

config.VERBOSE = False
ARCHER = parse_mtf(config.data_path("Archer ARC-2R.mtf"))

CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


def hexinfo(level=0, **features):
    return {"level": level, "features": dict(features), "impassable": False}


def board(changes=None):
    hexes = {f"{c:02d}{r:02d}": hexinfo() for c in range(1, 17) for r in range(1, 18)}
    hexes.update(changes or {})
    tm = terrain_rules.prepare_board({"width": 16, "height": 17, "hexes": hexes})
    water.set_board(tm)
    hazards.set_board(tm)
    return tm


def place(hex_, facing="N"):
    m = clone_mech(ARCHER)
    orchestrator._attach_mech_config(m, {"hex": hex_, "facing": facing, "gunnery": 4, "piloting": 5,
                                         "min_heat": 0, "max_heat": 30}, "Test")
    m.move_mode, m.move_fc, m.movement_heat = "Walk", 1, 1
    return m


def armor(m, loc, field="armor"):
    return m.locations[loc][field]


class D6:
    """Scripts config.pick_number (1D6 rolls and picks) in a ScriptedDice block."""
    def __init__(self, picks):
        self.picks = list(picks)

    def __enter__(self):
        self.saved = config.pick_number
        config.pick_number = lambda n, prompt="": self.picks.pop(0) if self.picks else 1
        return self

    def __exit__(self, *exc):
        config.pick_number = self.saved


@check
def map_setup():
    """prepare_board: ultra-heavy woods / jungle and impassable hexes can't be
    entered by 'Mechs (TO:AR p.30); fortified and planted-field hexes play;
    a pool off a water hex and fuel tanks are refused."""
    tm = board({"0505": hexinfo(woods=["3"]), "0506": hexinfo(jungle=["3"]), "0507": hexinfo(impassable=["1"]),
                "0508": hexinfo(fortified=["1"]), "0509": hexinfo(planted_fields=["2"])})
    h = tm["hexes"]
    assert h["0505"]["impassable"] and h["0506"]["impassable"] and h["0507"]["impassable"]
    assert not h["0508"]["impassable"] and not h["0509"]["impassable"]
    assert terrain_rules.step_cost(h["0504"], h["0505"]) is None
    assert terrain_rules.step_cost(h["0507"], h["0508"]) == 1          # fortified: no effect on 'Mechs
    assert terrain_rules.step_cost(h["0508"], h["0509"]) == 1          # planted fields +0 MP (p.30)
    for bad in ({"hazardous_liquid": ["0"]}, {"fuel_tank": ["1", "0"]}):
        try:
            board({"0808": hexinfo(**bad)})
        except ValueError:
            pass
        else:
            raise AssertionError(f"{bad} should be refused")


@check
def ultra_heavy_woods_block_los():
    """TO:AR p.38: one intervening ultra-heavy woods hex blocks LOS (light
    woods only add +1)."""
    xy = parse_hex_label
    tm = board({"0807": hexinfo(woods=["3"])})
    assert not has_los(xy("0809"), xy("0805"), tm).los
    tm = board({"0807": hexinfo(woods=["1"])})
    r = has_los(xy("0809"), xy("0805"), tm)
    assert r.los and r.modifier == 1


@check
def planted_fields_los():
    """TO:AR p.36: fields rise 1 level - between standing 'Mechs on flat
    ground they don't intervene; between two prone 'Mechs (LOS level 1) they
    do: +1 per two full intervening field hexes, 6 block."""
    xy = parse_hex_label
    tm = board({f"08{r:02d}": hexinfo(planted_fields=["1"]) for r in range(3, 11)})
    assert has_los(xy("0812"), xy("0802"), tm).modifier == 0                        # standing: no effect
    assert not has_los(xy("0812"), xy("0802"), tm, 1, 1).los                         # 8 field hexes: blocked
    tm = board({f"08{r:02d}": hexinfo(planted_fields=["1"]) for r in range(3, 6)})   # 3 field hexes
    r = has_los(xy("0812"), xy("0802"), tm, 1, 1)
    assert r.los and r.modifier == 1, r                                              # two full -> +1


@check
def magma_costs_and_hazard_prices():
    """p.30: crust +0 MP, liquid +1; step_hazard: 2D6 a leg in liquid (7 each),
    a 1-in-6 crust, a pool's table average."""
    h = board({"0505": hexinfo(magma=["1"]), "0506": hexinfo(magma=["2"]),
               "0507": hexinfo(-1, water=["1"], hazardous_liquid=["0"])})["hexes"]
    assert terrain_rules.step_cost(h["0504"], h["0505"]) == 1
    assert terrain_rules.step_cost(h["0505"], h["0506"]) == 2
    assert terrain_rules.step_hazard(h["0506"]) == 14.0
    assert abs(terrain_rules.step_hazard(h["0505"]) - 14.0 / 6) < 1e-9
    assert terrain_rules.step_hazard(h["0507"], legs=4) == 17.5 / 6


@check
def path_avoids_lava():
    """The path search takes the least-hazard path first: a 'Mech going two
    hexes north through liquid magma or round it ends there with the safe
    path when both fit its MP."""
    tm = board({"0807": hexinfo(magma=["2"])})
    x, y = parse_hex_label("0808")
    table = build_movement_table(x, y, compass_to_facing("N"), 8, terrain_map=tm)
    tx, ty = parse_hex_label("0806")
    state = (tx, ty, compass_to_facing("N"))
    assert table.hazards[state][3] == 14.0                    # 2 hexes straight on: only through the lava (+1 MP)
    assert table.hazards[state][7] == 0.0                     # round it: 7 MP, no lava


@check
def movement_cache_sees_a_broken_crust():
    """Speed cache (2026-10-28): a magma crust that breaks mid-battle changes
    the hex's hazard; a table built afterwards must price it, not repeat the
    one built before."""
    tm = board({"0807": hexinfo(magma=["1"])})            # crust
    x, y = parse_hex_label("0808")
    north = compass_to_facing("N")
    cx, cy = parse_hex_label("0807")
    state = (cx, cy, north)                                 # one hex north: the crust hex
    crust = build_movement_table(x, y, north, 3, terrain_map=tm).hazards[state][1]
    tm["hexes"]["0807"]["features"]["magma"] = ["2"]      # the crust breaks: liquid
    liquid = build_movement_table(x, y, north, 3, terrain_map=tm).hazards[state][1]
    assert liquid > crust, (crust, liquid)


@check
def crust_breaks_and_liquid_burns():
    """p.34: entering a crust on the ground breaks it on a 6; then liquid
    magma: 2D6 a leg (p.35) and the bog-down roll at +4 (p.60)."""
    tm = board({"0807": hexinfo(magma=["1"])})
    m = place("0807")
    before = (armor(m, "Left Leg"), armor(m, "Right Leg"))
    with ScriptedDice([]):
        with D6([5]):
            assert hazards.enter_hex(m, "0807") is None
    assert tm["hexes"]["0807"]["features"]["magma"] == ["1"]
    with ScriptedDice([3, 4, 12]):                         # legs 3 and 4, bog-down roll 12 (needs 9)
        with D6([6]):
            assert hazards.enter_hex(m, "0807") is None
    assert tm["hexes"]["0807"]["features"]["magma"] == ["2"]
    assert (armor(m, "Left Leg"), armor(m, "Right Leg")) == (before[0] - 3, before[1] - 4)
    with ScriptedDice([2, 2, 5]):                          # bog-down roll 5: stuck
        assert hazards.enter_hex(m, "0807") == "stuck"
    assert hazards.is_stuck(m)
    hazards.set_board(tm)                                   # the next battle: the crust is mended
    assert tm["hexes"]["0807"]["features"]["magma"] == ["1"]


@check
def stuck_target_and_freeing():
    """p.60: -2 to hit a stuck unit; at the start of the Movement Phase a
    roll (+4 in liquid magma) frees it; no kicks while stuck (p.61)."""
    board({"0807": hexinfo(magma=["2"])})
    m = place("0807")
    m.move_fc = 0
    m.stuck = {"rolls": 1, "prone_stage": False, "by_jump": False}
    assert attack_resolution._target_tmm(m) == -2
    with ScriptedDice([2, 2, 8]):                           # starts in liquid: legs 2, 2; free roll 8
        hazards.start_of_movement(m)
    assert hazards.is_stuck(m)                               # needed 9
    with ScriptedDice([2, 2, 9]):
        hazards.start_of_movement(m)
    assert not hazards.is_stuck(m)


@check
def magma_heat_is_uncapped():
    """p.35: 10 for occupying liquid magma in the Heat Phase, 5 for each
    liquid hex entered and left, 2 for a crust; added after the 15 cap."""
    board({"0807": hexinfo(magma=["2"]), "0806": hexinfo(magma=["2"]), "0805": hexinfo(magma=["1"])})
    m = place("0807")
    m.magma_entered = [("0805", "1"), ("0806", "2"), ("0807", "2")]
    assert hazards.magma_heat(m) == 2 + 5 + 10
    m.magma_entered = [("0806", "2")]
    m.outside_heat = 40
    m.movement_heat, m.current_heat = 0, 0
    heat.resolve_heat_phase(m, 0)
    sinks = heat.compute_heat_dissipation(m)
    assert m.current_heat == max(0, 15 + 5 + 10 - sinks + heat.engine_heat(m)), m.current_heat


@check
def pool_hits_legs_in_depth_one():
    """p.47: a 'Mech standing in a depth 1 pool takes the damage on its legs,
    5-point groupings; a roll of 1-2 does nothing."""
    board({"0807": hexinfo(-1, water=["1"], hazardous_liquid=["0"])})
    m = place("0807")
    legs = armor(m, "Left Leg") + armor(m, "Right Leg")
    with D6([2]):
        hazards.pool_damage(m, "test")
    assert armor(m, "Left Leg") + armor(m, "Right Leg") == legs
    with ScriptedDice([9]):                                # deadly: 2D6 = 9 -> 5 + 4, both to the first leg
        with D6([6, 1, 1]):
            hazards.pool_damage(m, "test")
    assert armor(m, "Left Leg") + armor(m, "Right Leg") == legs - 9


@check
def princess_prices_the_whole_path():
    """MegaMek's checkPathForHazards (2026-10-28): every hex a ground path
    stands in, not just the end hex; rubble is not one of its hazards."""
    import INTEGRATION__princess as princess
    import INTEGRATION__ranged_combat as ranged_combat
    tm = board({"0807": hexinfo(magma=["2"]), "0806": hexinfo(rubble=["1"])})
    m = place("0808")
    m.facing = "N"
    x, y = parse_hex_label("0806")
    through, = ranged_combat.prepare_options(m, [(x, y, compass_to_facing("N"), 2, "Walk", 4)])
    paths = ranged_combat.PathBook(m, tm)
    assert [hex_label(px, py) for _, (px, py, _f), _ in paths.path(through)] == ["0807", "0806"]
    assert princess.hazards(m, through, tm, None) == 0               # the end hex (rubble) alone: nothing
    assert princess.hazards(m, through, tm, paths) == princess.lava_hazard(m, False, end_hex=False) > 0
    stay, = ranged_combat.prepare_options(m, [(*parse_hex_label("0808"), compass_to_facing("N"), 0, "Stand Still", 0)])
    assert princess.hazards(m, stay, tm, paths) == 0


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
    hazards.set_board(None)
    water.set_board(None)
    print()
    if failed:
        print(f"{len(failed)} of {len(CHECKS)} hazard checks FAILED: {', '.join(failed)}")
        return 1
    print(f"All {len(CHECKS)} hazard checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
