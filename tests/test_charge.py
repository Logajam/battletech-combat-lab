"""
tests/test_charge.py - checks charge attacks (2026-10-20): the numbers
(Core p.78), which spots can charge, the movement decision's gate, the
Physical-phase resolution (damage, displacement, PSRs, cancellation) and
falls of more than one level (p.115). INTEGRATION__charge has the rules.

    python tests/test_charge.py

Real units come from data/meks.zip (extracted to a temporary folder).
"""

import copy
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
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
import INTEGRATION__attack_resolution as attack_resolution  # noqa: E402
import INTEGRATION__movement_selection as movement_selection  # noqa: E402
import INTEGRATION__physical as physical  # noqa: E402
import INTEGRATION__charge as charge  # noqa: E402
from INTEGRATION__attack_resolution import SideReport  # noqa: E402
from INTEGRATION__rng import BattleRNG  # noqa: E402
import piloting_rolls  # noqa: E402
from mtf_parser import parse_mtf  # noqa: E402
from mech_state import clone_mech, is_destroyed  # noqa: E402
from test_heat import ScriptedDice  # noqa: E402

config.VERBOSE = False
with redirect_stdout(io.StringIO()):
    TERRAIN = orchestrator._load_map()
_TMP = tempfile.mkdtemp()


def unit(name):
    with zipfile.ZipFile(os.path.join(REPO_ROOT, "data", "meks.zip")) as z:
        path = z.extract(f"meks/3039u/{name}.mtf", _TMP)
    with redirect_stdout(io.StringIO()):
        return parse_mtf(path)


CHARGER = unit("Charger CGR-1A1")          # 80 t, 5/8, five small lasers - a born charger
ATLAS = unit("Atlas AS7-D")                # 100 t, 3/5
SYNTHETIC = parse_mtf(config.data_path("TEST_Synthetic_Loadout.mtf"))


def fresh(template, hex_, facing="N", name="Test", piloting=5):
    m = clone_mech(template)
    orchestrator._attach_mech_config(m, {"hex": hex_, "facing": facing, "gunnery": 4, "piloting": piloting,
                                         "min_heat": 0, "max_heat": 30}, name)
    m.charging = None
    return m


def charging(attacker, target, hex_, facing, mode="Run", fc=5):
    attacker.hex, attacker.facing = hex_, facing
    attacker.move_mode, attacker.move_fc, attacker.mp_spent = mode, fc, 8
    attacker.charging = target


class Dice:
    """Rolls by prompt: the charge roll, hit locations, PSRs and everything
    else each get their own number."""

    def __init__(self, charge=12, location=7, psr=12, other=2):
        self.values = (charge, location, psr, other)

    def __enter__(self):
        self.real = config.roll_2d6
        charge_roll, location, psr, other = self.values

        def roll(prompt=""):
            if "Charge attack" in prompt:
                return charge_roll
            if "location" in prompt:
                return location
            if "PSR" in prompt or "Seatbelt" in prompt or "consciousness" in prompt.lower():
                return psr
            return other
        config.roll_2d6 = roll
        return self

    def __exit__(self, *exc):
        config.roll_2d6 = self.real


def unarmed(template):
    """A copy of the unit with every weapon taken out of its crits."""
    m = clone_mech(template)
    for loc, slots in m.crits.items():
        m.crits[loc] = ["-Empty-" if getattr(x, "category", None) == "weapon" else x for x in slots]
    return m


CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


@check
def charge_numbers():
    """p.78: target takes ceil(tons / 5 x (TMM + 1)), attacker ceil(target
    tons / 10), both in 5-point groups; comparative Piloting modifier, an
    immobile target counting as Piloting 4."""
    a, t = fresh(CHARGER, "0808"), fresh(ATLAS, "0807", "S", piloting=3)
    assert charge.target_damage(a, 2) == 48 and charge.attacker_damage(t) == 10
    assert charge.target_damage(fresh(SYNTHETIC, "0101"), 1) == 20
    assert charge.groupings(48) == [5] * 9 + [3] and charge.groupings(10) == [5, 5]
    assert charge.comparative_modifier(a, t) == 2
    t.shutdown = True
    assert charge.comparative_modifier(a, t) == 1


@check
def who_can_be_charged():
    """p.78: a standing target that has finished moving (or is immobile)."""
    a, t = fresh(CHARGER, "0808"), fresh(ATLAS, "0805", "S")
    assert charge.can_charge(a, t, target_has_moved=True)
    assert not charge.can_charge(a, t, target_has_moved=False)
    t.prone = True
    assert not charge.can_charge(a, t, target_has_moved=True)
    t.prone, t.shutdown = False, True
    assert charge.can_charge(a, t, target_has_moved=False)


@check
def charge_states_end_adjacent_facing_with_mp_to_enter():
    """Movement (p.78): end next to the target facing it, with MP left to
    enter its hex; hexes moved count the target's hex; never a jump."""
    a, t = fresh(CHARGER, "0812"), fresh(ATLAS, "0806", "S")
    states = charge.charge_states(a, t, TERRAIN)
    assert states
    run = 8
    for s in states:
        assert s["mode"] in ("Walk", "Run") and s["charge"]
        assert charge.hex_distance(charge.hex_geometry.parse_hex_label(s["hex"]),
                                   charge.hex_geometry.parse_hex_label(t.hex)) == 1
        assert s["mp_spent"] <= run and s["fc"] >= 1
    straight = [s for s in states if s["hex"] == "0807" and s["facing"] == "N"]
    assert straight and max(s["fc"] for s in straight) == 6          # 5 hexes up the column + the target's


@check
def the_gate_and_the_pick():
    """In a real battle (Charger CGR-1A1 vs Atlas AS7-D, seed 3, 20 turns) the
    Charger charges - its five small lasers are weak against 100 tons; with
    CHARGES off it never does. A charge never gets past the gate when an
    ordinary attack in that mode does more."""
    import re
    counts = []
    for on in (True, False):
        config.CHARGES = on
        config.MECH_RED_MTF = os.path.join(_TMP, "meks", "3039u", "Charger CGR-1A1.mtf")
        config.MECH_BLUE_MTF = os.path.join(_TMP, "meks", "3039u", "Atlas AS7-D.mtf")
        config.VERBOSE = True
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                orchestrator.run_batch(num_simulations=1, seed=3, max_turns=20)
        finally:
            config.CHARGES, config.VERBOSE = True, False
            config.MECH_RED_MTF = config.MECH_BLUE_MTF = "Asymptote II iJ Mpulse.mtf"
        log = buf.getvalue()
        counts.append(log.count("declares a CHARGE"))
        if on:
            assert re.search(r"CHARGE needs \d+", log)
            assert "no ranged attacks this turn" in log
    assert counts[0] >= 1 and counts[1] == 0, counts
    a, t = fresh(CHARGER, "0811", "N", "Red"), fresh(ATLAS, "0806", "S", "Blue")
    # the gate itself: no charge state passes when ordinary attacks are worth more in every mode
    big = {"Walk": 1e9, "Run": 1e9}
    real = charge.expected_dealt
    seen = []
    charge.expected_dealt = lambda *args: (seen.append(1), real(*args))[1]
    try:
        ev1, me, them = None, None, None
        class Fake:                                         # noqa: E306 - a static list with huge damage
            def __init__(self, mode):
                self.dealt, self.side_on_defender, self.mode = big[mode], "front", mode
        out = movement_selection._charge_pick(a, t, TERRAIN, None, 0.5, ev1,
                                              movement_selection._Side(a), movement_selection._Side(t),
                                              [Fake("Walk"), Fake("Run")])
    finally:
        charge.expected_dealt = real
    assert out is None and seen


the_gate_and_the_pick.real_dice = True    # a real battle: its own seeded dice


@check
def charger_holds_its_fire():
    """p.78: a charging mech makes no ranged attacks."""
    a, t = fresh(CHARGER, "0807", "N"), fresh(ATLAS, "0806", "S")
    charging(a, t, "0807", "N")
    rep = SideReport()
    with ScriptedDice([], default=12):
        attack_resolution.declare_attacks(a, t, TERRAIN, rep)
    assert not rep.attacks_list


@check
def successful_charge_damages_both_and_displaces():
    """Hit: 48 to the Atlas, 10 to the Charger, the Atlas pushed one hex on
    in the charge's direction, the Charger into its hex, then both PSRs at +2."""
    a, t = fresh(CHARGER, "0807", "N", "Red"), fresh(ATLAS, "0806", "S", "Blue")
    charging(a, t, "0807", "N", mode="Run", fc=5)                    # TMM 2
    before_a, before_t = attack_resolution.total_hp(a), attack_resolution.total_hp(t)
    with Dice():                                                      # hits, the Atlas's fists miss, PSRs pass
        physical.run_physical_phase(a, t, TERRAIN, {})
    assert before_t - attack_resolution.total_hp(t) == 48
    assert before_a - attack_resolution.total_hp(a) == 10
    assert t.hex == "0805" and a.hex == "0806"
    assert not t.prone and not a.prone


@check
def failed_charge_and_failed_psr():
    """A miss: nobody moves, no charge damage. A hit with failed +2 PSRs:
    both fall."""
    a, t = fresh(CHARGER, "0807", "N", "Red"), fresh(ATLAS, "0806", "S", "Blue")
    charging(a, t, "0807", "N")
    with Dice(charge=2):
        physical.run_physical_phase(a, t, TERRAIN, {})
    assert a.hex == "0807" and t.hex == "0806"
    a2, t2 = fresh(CHARGER, "0807", "N", "Red"), fresh(ATLAS, "0806", "S", "Blue")
    charging(a2, t2, "0807", "N")
    with Dice(psr=2):
        physical.run_physical_phase(a2, t2, TERRAIN, {})
    assert a2.prone and t2.prone


@check
def pushed_off_the_board_or_down_a_cliff():
    """p.113: displaced off the board = destroyed; 3+ levels up = nobody
    moves; 2+ levels down = automatic fall of that many levels (p.115)."""
    edge = TERRAIN
    a, t = fresh(CHARGER, "0802", "N", "Red"), fresh(ATLAS, "0801", "S", "Blue")
    charging(a, t, "0802", "N")
    with Dice():
        physical.run_physical_phase(a, t, edge, {})
    assert is_destroyed(t) and t.cause_of_death == "Displaced off the battlefield"

    cliff = copy.deepcopy(TERRAIN)
    cliff["hexes"]["0805"]["level"] = -2
    a, t = fresh(CHARGER, "0807", "N", "Red"), fresh(ATLAS, "0806", "S", "Blue")
    charging(a, t, "0807", "N")
    before = attack_resolution.total_hp(t)
    with Dice():
        physical.run_physical_phase(a, t, cliff, {})
    assert t.prone and t.hex == "0805"
    assert before - attack_resolution.total_hp(t) == 48 + 10 * 3     # charge + a 2-level fall (10 x 3)

    wall = copy.deepcopy(TERRAIN)
    wall["hexes"]["0805"]["level"] = 3
    a, t = fresh(CHARGER, "0807", "N", "Red"), fresh(ATLAS, "0806", "S", "Blue")
    charging(a, t, "0807", "N")
    with Dice():
        physical.run_physical_phase(a, t, wall, {})
    assert t.hex == "0806" and a.hex == "0807"


@check
def cancelled_charges():
    """p.78: a target that fell before the Physical phase cancels the charge,
    and the charger may kick instead; a charger that fell misses."""
    a, t = fresh(CHARGER, "0807", "N", "Red"), fresh(ATLAS, "0806", "S", "Blue")
    charging(a, t, "0807", "N")
    t.prone = True
    with Dice():
        physical.run_physical_phase(a, t, TERRAIN, {})
    assert a.charging is None and a.hex == "0807"
    a, t = fresh(CHARGER, "0807", "N", "Red"), fresh(ATLAS, "0806", "S", "Blue")
    charging(a, t, "0807", "N")
    a.prone = True
    before = attack_resolution.total_hp(t)
    with Dice():
        physical.run_physical_phase(a, t, TERRAIN, {})
    assert attack_resolution.total_hp(t) == before


@check
def falls_of_several_levels():
    """p.115: falling damage x (levels + 1)."""
    m = fresh(ATLAS, "0808")
    before = attack_resolution.total_hp(m)
    with ScriptedDice([], default=7):
        piloting_rolls.resolve_fall(m, 0, levels=2)
    assert before - attack_resolution.total_hp(m) == 30


def run_all():
    failed = 0
    for fn in CHECKS:
        try:
            if getattr(fn, "real_dice", False):
                with redirect_stdout(io.StringIO()):
                    fn()
            else:
                with ScriptedDice([], default=7), redirect_stdout(io.StringIO()):
                    fn()
            print(f"PASS  {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print()
    if failed:
        print(f"{failed} of {len(CHECKS)} charge checks FAILED.")
        sys.exit(1)
    print(f"All {len(CHECKS)} charge checks passed.")


if __name__ == "__main__":
    run_all()
