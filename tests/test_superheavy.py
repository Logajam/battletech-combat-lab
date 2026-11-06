"""
tests/test_superheavy.py - ultralight (10-15 ton) and superheavy (105-200
ton) 'Mechs, wired in 2026-10-28 (Daniel: "Go borrow from megamek to get
superheavy and ultra light mechs working"): MegaMek's structure table and
superheavy slots, and the Core Rulebook's superheavy appendix (pp.236,
240-241).

    python tests/test_superheavy.py

Real units come from data/meks.zip (extracted to a temporary folder). Dice
are scripted the same way as tests/test_heat.py.
"""

import io
import os
import sys
import tempfile
import traceback
import zipfile
from contextlib import redirect_stdout

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402
config.STATS = False  # event log + report off: not part of a test or battery (2026-11-06)
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
import INTEGRATION__attack_resolution as attack_resolution  # noqa: E402
import INTEGRATION__physical as physical  # noqa: E402
import INTEGRATION__water as water  # noqa: E402
import terrain_rules  # noqa: E402
from los import trace_los_path, mech_height  # noqa: E402
from hex_geometry import parse_hex_label  # noqa: E402
from mtf_parser import parse_mtf  # noqa: E402
from mech_state import clone_mech, is_superheavy, engine_hits_to_destroy, physical_attacker_modifier, \
    has_command_console, technical_officer_bonus  # noqa: E402
from damage_resolution import get_weapons, apply_explosion  # noqa: E402
from equipment import Equipment, is_crit_target  # noqa: E402
from test_heat import ScriptedDice  # noqa: E402

config.VERBOSE = False
_TMP = tempfile.mkdtemp()


def unit(path):
    with zipfile.ZipFile(os.path.join(REPO_ROOT, "data", "meks.zip")) as z:
        out = z.extract(f"meks/{path}.mtf", _TMP)
    with redirect_stdout(io.StringIO()):
        return parse_mtf(out)


OMEGA = unit("Jihad Final Reckoning/OMEGA SHP-4X")          # 150 t biped, double ammo slots
ARES = unit("3145/Republic/Ares ARS-V1 Zeus")                # 135 t superheavy tripod
EXO = unit("TRO Irregulars/Exo HMX-1 Haulermech")            # 10 t ultralight
CELERITY = unit("3145/Republic/Celerity CLR-03-O")           # 15 t ultralight quad
ATLAS = unit("3050U/Atlas AS7-S2")

CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


def place(template, hex_="0808", facing="N", side="Red"):
    m = clone_mech(template)
    with redirect_stdout(io.StringIO()):
        orchestrator._attach_mech_config(m, {"hex": hex_, "facing": facing, "gunnery": 4, "piloting": 5,
                                             "min_heat": 0, "max_heat": 30}, side)
    m.move_mode, m.move_fc, m.movement_heat, m.turn_number = "Walk", 1, 1, 1
    return m


def board(**hexes):
    out = {f"{c:02d}{r:02d}": {"level": 0, "features": {}, "impassable": False}
           for c in range(1, 17) for r in range(1, 18)}
    for key, spec in hexes.items():
        out[key[1:]] = dict({"level": 0, "features": {}, "impassable": False}, **spec)
    return {"width": 16, "height": 17, "hexes": out}


@check
def structure_from_megamek():
    """MegaMek's table: 10 / 15 tons, and 105-200 with a 4-point head."""
    assert EXO.locations["Center Torso"]["structure"] == 4 and EXO.locations["Left Arm"]["structure"] == 1
    assert CELERITY.locations["Center Torso"]["structure"] == 5
    assert OMEGA.locations["Head"]["structure"] == 4 and OMEGA.locations["Center Torso"]["structure"] == 45
    assert ARES.locations["Center Leg"]["structure"] == 28
    assert is_superheavy(OMEGA) and not is_superheavy(ATLAS)


@check
def superheavy_slots():
    """Items take half their slots (a Gauss rifle 4), and explode for 2 a slot
    they really fill (8, Core p.240); a slot's second ammo bin is never a
    critical hit target itself and goes up with the first - one MechWarrior hit."""
    m = place(OMEGA)
    gauss = [w for w in get_weapons(m) if "Gauss" in w.name]
    assert len(gauss) == 3 and all(w.slots_occupied == 4 and w.explosion_damage == 8 for w in gauss)
    bins = [s for s in m.crits["Left Arm"] if isinstance(s, Equipment) and s.category == "ammo"]   # LB 10-X ammo
    first = next(s for s in bins if getattr(s, "partner_of_slot", None) is None)
    second = first.partner
    assert second.partner_of_slot is first and not is_crit_target(second) and is_crit_target(first)
    before = m.pilot_hits
    real = config.roll_2d6
    config.roll_2d6 = lambda prompt="": 2       # the blast's critical-hit checks all miss: no second
    try:                                        # bin set off by chance (this check was flaky, 2026-10-29)
        with redirect_stdout(io.StringIO()):
            apply_explosion(m, first, "Left Arm")
    finally:
        config.roll_2d6 = real
    assert second.exploded and m.pilot_hits == before + 1


@check
def large_target_and_physical():
    """Every attack on a superheavy -1 (Large); its own physical attacks +1."""
    o, a = place(OMEGA), place(ATLAS)
    assert attack_resolution._target_tmm(o) == attack_resolution._target_tmm(a) - 1
    assert physical_attacker_modifier(o) == 1 and physical_attacker_modifier(a) == 0
    assert physical_attacker_modifier(place(ARES)) == 1 - 1      # a tripod's dedicated pilot -1 too


@check
def terrain_discount():
    """1 MP less into woods, jungle, rough, rubble (Core p.240)."""
    heavy = {"level": 0, "features": {"woods": ["2"]}}
    rough = {"level": 0, "features": {"rough": []}}
    flat = {"level": 0, "features": {}}
    normal, big = terrain_rules.max_level_change(False), terrain_rules.max_level_change(False, True)
    assert terrain_rules.step_cost(flat, heavy, normal) == 3 and terrain_rules.step_cost(flat, heavy, big) == 2
    assert terrain_rules.step_cost(flat, rough, big) == 1 and big == 2


@check
def water_one_level_deeper():
    """Partial in depth 2, submerged in depth 3 (prone: 2); depth 1 'wading' -
    no attacks at a partly / fully submerged target, and attacks from
    submerged locations on it use the Kick table (Core p.240)."""
    tm = board(h0808={"level": -1, "depth": 1}, h0809={"level": -2, "depth": 2},
               h0810={"level": -3, "depth": 3})
    st = lambda label, prone=False: water.state_at(label, prone, tm, True)    # noqa: E731
    assert (st("0808"), st("0809"), st("0810"), st("0809", True)) == (
        water.WADING, water.PARTIAL, water.SUBMERGED, water.SUBMERGED)
    assert water.state_at("0809", False, tm) == water.SUBMERGED                # a normal 'Mech
    o, a = place(OMEGA), place(ATLAS)
    ws = get_weapons(o)
    assert water.blocked_weapon_ids(o, ws, attack_resolution.weapon_locations(o), water.WADING,
                                    water.PARTIAL) is None
    aw = get_weapons(a)
    assert water.kick_table_weapon_ids(a, aw, attack_resolution.weapon_locations(a), water.SUBMERGED,
                                       water.WADING) == frozenset(id(w) for w in aw)
    assert water.physical_allowed(water.WADING, water.SUBMERGED) == frozenset()


@check
def los_height_and_cover():
    """3 levels tall: partial cover only next to a hex 2 levels higher; none
    prone; a hill 1 level higher doesn't cover it (Core p.240)."""
    a, t = parse_hex_label("0808"), parse_hex_label("0804")
    tall = mech_height(False, True)
    one_up = board(h0805={"level": 1})
    two_up = board(h0805={"level": 2})
    assert trace_los_path(a, t, one_up).steps[-1].partial_cover == 1                     # a normal 'Mech
    assert trace_los_path(a, t, one_up, 2, tall).steps[-1].partial_cover == 0
    assert trace_los_path(a, t, two_up, 2, tall).steps[-1].partial_cover == 1
    assert trace_los_path(a, t, two_up, 2, mech_height(True, True)).steps[-1].partial_cover == 0
    deep = board(h0804={"level": -2, "depth": 2})
    assert trace_los_path(a, t, deep, 2, tall).steps[-1].partial_cover == 1             # standing in depth 2


@check
def different_levels_table():
    """Core p.240: a standing superheavy two levels down can be kicked (Punch
    table); one level down, punches use their own table; prone two down: none."""
    assert physical.reachable(-2, True) and not physical.reachable(-2, False)
    a = place(ATLAS)
    rel = physical._FixedReach((True, True, True, False, False))
    two_down = physical._options(a, rel, -2, False, frozenset(), True)
    assert set(two_down) == {"kick"} and two_down["kick"][0]["table"] == "punch"
    one_down = physical._options(a, rel, -1, False, frozenset(), True)
    assert {"punch", "kick"} <= set(one_down) and one_down["punch"][0]["table"] == "punch"
    assert physical._options(a, rel, -2, True, frozenset(), True) == {}


@check
def compact_engine_and_technical_officer():
    """A superheavy's compact engine dies at 2 hits; a superheavy tripod's
    technical officer is a command console and +2 against heat (p.236)."""
    o = place(OMEGA)
    assert engine_hits_to_destroy(o) == 3
    o.engine_desc = "400 Compact Engine"
    assert engine_hits_to_destroy(o) == 2
    r = place(ARES)
    assert has_command_console(r) and technical_officer_bonus(r) == 2
    assert not has_command_console(place(ATLAS))


@check
def ultralight_quad_scores_its_kicks():
    """A quad's cached reach keeps its mule kick (the cache had lost it - a
    crash when an ultralight quad was scored next to an enemy)."""
    rel = physical._FixedReach((False, False, False, False, True))
    assert rel.mule_ok


def run_all():
    failed = []
    for fn in CHECKS:
        try:
            with redirect_stdout(io.StringIO()):
                fn()
            print(f"  {fn.__name__}: PASS")
        except Exception:
            failed.append(fn.__name__)
            print(f"  {fn.__name__}: FAILED")
            traceback.print_exc()
    print(f"{len(CHECKS) - len(failed)} of {len(CHECKS)} checks passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_all())
