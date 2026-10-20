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
import INTEGRATION__movement_attacks as movement_attacks  # noqa: E402
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
HIGHLANDER = unit("Highlander HGN-733")    # 90 t, jumps 3
COMMANDO = unit("Commando COM-2D")         # 25 t, 6/9
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
            if "Charge attack" in prompt or "DFA attack" in prompt:
                return charge_roll
            if "location" in prompt:
                return location
            if "PSR" in prompt or "Seatbelt" in prompt or "consciousness" in prompt.lower():
                return psr
            return other
        self.real_pick = config.pick_number
        config.roll_2d6 = roll
        config.pick_number = lambda n, prompt="": min(n, 3)
        return self

    def __exit__(self, *exc):
        config.roll_2d6, config.pick_number = self.real, self.real_pick


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
    states = movement_attacks.MoverIndex(a, TERRAIN).charge_states(movement_attacks.pose_of(t))
    assert states
    run = 8
    for s in states:
        assert s["mode"] in ("Walk", "Run") and s["charge"]
        assert movement_attacks.hex_distance(charge.hex_geometry.parse_hex_label(s["hex"]),
                                             charge.hex_geometry.parse_hex_label(t.hex)) == 1
        assert s["mp_spent"] <= run and s["fc"] >= 1
    straight = [s for s in states if s["hex"] == "0807" and s["facing"] == "N"]
    assert straight and max(s["fc"] for s in straight) == 6          # 5 hexes up the column + the target's


@check
def the_gate_and_the_pick():
    """The decision (INTEGRATION__movement_attacks): a Charger five hexes
    from a standing Atlas has charges that pass the gate; the best is picked
    when it beats the ordinary pick's score and not when it doesn't; the gate
    stops every charge when an ordinary attack in its mode does more. A
    charge pick sets `charging` in the Movement Phase, and the charger then
    holds its fire."""
    a, t = fresh(CHARGER, "0811", "N", "Red"), fresh(ATLAS, "0806", "S", "Blue")
    ctx_static = []
    me, them = movement_selection._Side(a), movement_selection._Side(t)
    import INTEGRATION__ranged_combat as ranged_combat
    ev = ranged_combat.MoveEvaluator(a, t, TERRAIN)
    low = movement_selection._movement_attack_pick(a, t, TERRAIN, None, 1e-9, ev, me, them, ctx_static)
    assert low is not None and low[0].get("charge"), low
    assert movement_selection._movement_attack_pick(a, t, TERRAIN, None, 1e9, ev, me, them, ctx_static) is None
    real = movement_selection.choose
    movement_selection.choose = lambda *args, **kw: (low[0], "test")
    try:
        orchestrator._phase_movement(a, t, TERRAIN, 1, BattleRNG(1), moves_first=False)
    finally:
        movement_selection.choose = real
    assert a.charging is t and a.hex == low[0]["hex"] and a.move_fc == low[0]["fc"]
    import INTEGRATION__ranged_combat as ranged_combat
    a, t = fresh(CHARGER, "0811", "N", "Red"), fresh(ATLAS, "0806", "S", "Blue")
    index, pose = movement_attacks.MoverIndex(a, TERRAIN), movement_attacks.pose_of(t)
    ev = ranged_combat.MoveEvaluator(a, t, TERRAIN)
    me, them = movement_selection._Side(a), movement_selection._Side(t)
    args = (t.hex, t.facing, t.move_fc, t.move_mode, t.mp_spent)
    run = lambda best: movement_attacks.scored_options(a, t, pose, index, ev, me.exposure, them.exposure,  # noqa: E731
                                                       me.psr_cost, best, args, movement_selection._objective)
    assert run({}) and not run({"Walk": 1e9, "Run": 1e9})


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


def dfa_ing(attacker, target, stop, facing, jumped=3):
    attacker.hex, attacker.facing = stop, facing
    attacker.move_mode, attacker.move_fc, attacker.mp_spent = "Jump", jumped, jumped
    attacker.dfa = target


@check
def dfa_numbers_and_reach():
    """pp.79-80: ceil(tons/10 x 3) to the target, ceil(tons/5) to the
    attacker, a miss falls 2 levels (x3); to-hit Piloting + 3 + TMM +
    comparative, no terrain. Reach: jump distance, and clearing the target's
    LOS level (its hex + 2)."""
    import INTEGRATION__dfa as dfa
    h, t = fresh(HIGHLANDER, "0809", "N"), fresh(ATLAS, "0806", "S", piloting=4)
    assert (dfa.target_damage(h), dfa.attacker_damage(h), dfa.miss_fall_damage(h)) == (27, 18, 27)
    assert dfa.to_hit(h, t, 1) == 5 + 3 + 1 + 1
    index = movement_attacks.MoverIndex(h, TERRAIN)
    states = index.dfa_states(movement_attacks.pose_of(t))
    assert [(s["hex"], s["facing"], s["mode"], s["fc"]) for s in states] == [("0807", "N", "Jump", 3)]
    t.hex = "0805"                                                    # 4 hexes: too far
    assert not index.dfa_states(movement_attacks.pose_of(t))
    hill = copy.deepcopy(TERRAIN)
    hill["hexes"]["0806"]["level"] = 2                                # LOS level 4 > 3 jump MP
    t.hex = "0806"
    assert not movement_attacks.MoverIndex(h, hill).dfa_states(movement_attacks.pose_of(t))


@check
def dfa_hit_and_miss():
    """Hit: 27 to the Atlas (Punch table), 18 to the Highlander, which lands
    in the Atlas's hex; the Atlas is pushed on; the Atlas can't punch the
    Highlander in the air. Miss: the Atlas steps aside, the Highlander falls
    2 levels in its hex (27, rear)."""
    a, t = fresh(HIGHLANDER, "0807", "N", "Red"), fresh(ATLAS, "0806", "S", "Blue")
    dfa_ing(a, t, "0807", "N")
    before_a, before_t = attack_resolution.total_hp(a), attack_resolution.total_hp(t)
    with Dice(other=12):                                              # the Atlas would hit anything it tried
        physical.run_physical_phase(a, t, TERRAIN, {})
    assert before_t - attack_resolution.total_hp(t) == 27 and before_a - attack_resolution.total_hp(a) == 18
    assert a.hex == "0806" and t.hex == "0805" and not a.prone and not t.prone
    a, t = fresh(HIGHLANDER, "0807", "N", "Red"), fresh(ATLAS, "0806", "S", "Blue")
    dfa_ing(a, t, "0807", "N")
    before_a, before_t = attack_resolution.total_hp(a), attack_resolution.total_hp(t)
    with Dice(charge=2):
        physical.run_physical_phase(a, t, TERRAIN, {})
    assert a.hex == "0806" and a.prone and t.hex != "0806"
    assert before_a - attack_resolution.total_hp(a) == 27 and attack_resolution.total_hp(t) == before_t


@check
def dfa_holds_fire_and_cancels():
    """No ranged fire while in a DFA; a target destroyed before the Physical
    phase cancels it - the attacker lands in its hex."""
    a, t = fresh(HIGHLANDER, "0807", "N", "Red"), fresh(ATLAS, "0806", "S", "Blue")
    dfa_ing(a, t, "0807", "N")
    rep = SideReport()
    with ScriptedDice([], default=12):
        attack_resolution.declare_attacks(a, t, TERRAIN, rep)
    assert not rep.attacks_list
    t.destroyed = True
    with Dice():
        physical.run_physical_phase(a, t, TERRAIN, {})
    assert a.dfa is None and a.hex == "0806"


@check
def first_mover_anticipates_movement_attacks():
    """Two-ply: the first mover's modeled reply includes the second mover's
    charges (the same gate and score the real second mover uses), so some
    spots are scored against a charge; with CHARGES off none are."""
    seen = {}
    real = movement_selection._modeled_reply
    for on in (True, False):
        config.CHARGES = on
        replies = []

        def spy(*args, **kw):
            r = real(*args, **kw)
            replies.append(r)
            return r
        movement_selection._modeled_reply = spy
        try:
            first, second = fresh(COMMANDO, "0806", "S", "Blue"), fresh(CHARGER, "0811", "N", "Red")
            movement_selection.choose(first, second, TERRAIN, BattleRNG(1), moves_first=True)
        finally:
            movement_selection._modeled_reply = real
            config.CHARGES = True
        seen[on] = sum(1 for r in replies if r is not None and r.attack == "charge")
    assert seen[True] > 0 and seen[False] == 0, seen


@check
def when_a_push_is_possible():
    """p.83: target standing straight ahead of the pusher's feet at the same
    level, both arms, no arm weapon fired; the bot only values a push that
    puts the target off the board or 2+ levels down."""
    a = fresh(CHARGER, "0802", "N")
    off_edge = fresh(ATLAS, "0801", "S")
    opt = physical.attack_options(a, off_edge, TERRAIN)
    assert opt.get("push") and opt["push"][0]["damage"] == attack_resolution.total_hp(off_edge)
    a2, mid = fresh(CHARGER, "0808", "N"), fresh(ATLAS, "0807", "S")
    assert "push" not in physical.attack_options(a2, mid, TERRAIN)            # nothing to push it into
    cliff = copy.deepcopy(TERRAIN)
    cliff["hexes"]["0806"]["level"] = -2
    assert physical.attack_options(a2, mid, cliff)["push"][0]["damage"] > 0
    a2.facing = "NE"
    assert "push" not in physical.attack_options(a2, mid, cliff)               # not straight ahead
    a2.facing = "N"
    a2.weapons_fired_this_turn = frozenset(id(w) for w in attack_resolution.get_weapons(a2)
                                           if attack_resolution.weapon_locations(a2)[id(w)] & {"Left Arm", "Right Arm"})
    if a2.weapons_fired_this_turn:
        assert "push" not in physical.attack_options(a2, mid, cliff)
    a2.weapons_fired_this_turn = frozenset()
    mid.prone = True
    assert "push" not in physical.attack_options(a2, mid, cliff)


@check
def push_off_the_board_and_off_a_cliff():
    """A push at a mech with its back to the board edge destroys it; one at
    a mech with a 2-level drop behind it makes it fall (10 x 3 for 100 t)."""
    a, t = fresh(CHARGER, "0802", "N", "Red"), fresh(ATLAS, "0801", "S", "Blue")
    t.piloting = 12
    base, picks, _ = physical.choose_attack(a, t, TERRAIN)
    assert picks[0].get("push")
    with Dice(other=12):
        physical.run_physical_phase(a, t, TERRAIN, {})
    assert is_destroyed(t) and t.cause_of_death == "Pushed off the battlefield" and a.hex == "0801"
    cliff = copy.deepcopy(TERRAIN)
    cliff["hexes"]["0806"]["level"] = -2
    a, t = fresh(CHARGER, "0808", "N", "Red"), fresh(ATLAS, "0807", "S", "Blue")
    t.piloting = 12
    before = attack_resolution.total_hp(t)
    with Dice(other=12):
        physical.run_physical_phase(a, t, cliff, {})
    assert t.hex == "0806" and t.prone and a.hex == "0807" and before - attack_resolution.total_hp(t) == 30


@check
def the_threat_of_a_push_is_scored():
    """Movement scoring: standing with your back to the board edge while the
    enemy can get straight in front of you prices in being pushed off
    (Daniel: "the threat of it affects choices")."""
    import INTEGRATION__ranged_combat as ranged_combat
    mover, pusher = fresh(ATLAS, "0805", "N"), fresh(CHARGER, "0802", "N")
    ev = ranged_combat.MoveEvaluator(mover, pusher, TERRAIN)
    x, y = charge.hex_geometry.parse_hex_label("0801")
    edge = ev.evaluate("0802", "N", 0, "Stand Still", 0, ev.prepare([(x, y, 3, 4, "Walk", 4)]))
    x2, y2 = charge.hex_geometry.parse_hex_label("0803")
    inside = ev.evaluate("0802", "S", 0, "Stand Still", 0, ev.prepare([(x2, y2, 0, 2, "Walk", 2)]))
    assert edge[0].received > inside[0].received + 0.5 * attack_resolution.total_hp(mover) * 0.5, (edge, inside)


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
