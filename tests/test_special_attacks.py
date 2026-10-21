"""
tests/test_special_attacks.py - checks the special physical attacks
(2026-10-20): charges (Core p.78) and death from above (pp.79-80) - the
numbers, who can reach, the movement decision's gate, the first mover
anticipating them, the Physical-phase resolution (damage, displacement,
PSRs, cancellation) - pushes (p.83) and their threat in movement scoring,
clubs (p.79), and falls of more than one level (p.115).

    python tests/test_special_attacks.py

Real units come from data/meks.zip (extracted to a temporary folder).
"""

import copy
import math
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
import INTEGRATION__clubs as clubs  # noqa: E402
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
def charge_end_of_movement_psrs():
    """pp.78, 113 (2026-10-21): a charger's movement ends in the Physical
    phase, so its end-of-movement PSRs (running with a gyro hit) wait until
    then - even when the charge misses - plus a PSR for the hex it advances
    into (rubble) when the charge hits."""
    a, t = fresh(CHARGER, "0807", "N", "Red"), fresh(ATLAS, "0806", "S", "Blue")
    charging(a, t, "0807", "N")
    a.gyro_hits = 1
    a.deferred_end_of_move = {"mode": "running", "from_hex": "0807"}
    with Dice(charge=2, psr=2):                                       # misses; every PSR fails
        physical.run_physical_phase(a, t, TERRAIN, {})
    assert a.hex == "0807" and a.prone and not t.prone                # fell in its own hex: the gyro PSR
    rubble = copy.deepcopy(TERRAIN)
    rubble["hexes"]["0806"]["features"] = dict(rubble["hexes"]["0806"]["features"], rubble=[])
    a, t = fresh(CHARGER, "0807", "N", "Red"), fresh(ATLAS, "0806", "S", "Blue")
    charging(a, t, "0807", "N")
    a.gyro_hits = 1
    a.deferred_end_of_move = {"mode": "running", "from_hex": "0807"}
    a.hex = "0806"                                                    # as after a successful charge
    got = movement_attacks.end_of_movement_triggers(a, rubble)
    assert [r for r, _ in got] == ["entered rubble at 0806", "end of movement (running, gyro hit)"], got
    assert a.deferred_end_of_move is None and movement_attacks.end_of_movement_triggers(a, rubble) == []


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


WOODS = next(label for label, info in sorted(TERRAIN["hexes"].items()) if "woods" in info["features"])
CLEAR = next(label for label, info in sorted(TERRAIN["hexes"].items()) if not info["features"] and label > "0300")


def broken(mech, arm, part):
    for i, slot in enumerate(mech.crits[arm]):
        if getattr(slot, "name", slot) == part:
            mech.destroyed_slot_info[(arm, i)] = {"name": part, "instance_id": None}
            mech.crits[arm][i] = "DESTROYED"
            return


@check
def who_can_hold_a_club():
    """p.79: two hands (claws count) and both shoulders, none damaged; quads can't."""
    assert clubs.can_wield(fresh(ATLAS, "0808"))
    m = fresh(ATLAS, "0808")
    broken(m, "Left Arm", "Hand Actuator")
    assert not clubs.can_wield(m)
    m = fresh(ATLAS, "0808")
    broken(m, "Right Arm", "Shoulder")
    assert not clubs.can_wield(m)
    q = fresh(ATLAS, "0808")
    q.mech_type = "quad"
    assert not clubs.can_wield(q)


@check
def picking_up_a_club():
    """On by default since 2026-10-21 (config.CLUB_PICKUP; Daniel: "May as
    well have mechs pick them up if they have nothing better to do"): in
    woods, a mech with nothing to shoot uproots a tree instead of firing; one
    that fired doesn't; a limb lying in a hex can be picked up by another
    mech standing there later. Switched off, nothing is picked up."""
    clubs.reset_battle()
    m = fresh(ATLAS, WOODS)
    assert config.CLUB_PICKUP
    config.CLUB_PICKUP = False
    try:
        assert clubs.maybe_pick_up(m, TERRAIN, fired_anything=False) is None
    finally:
        config.CLUB_PICKUP = True
    _picking_up(m)


def _picking_up(m):
    assert clubs.maybe_pick_up(m, TERRAIN, fired_anything=True) is None and not getattr(m, "club", None)
    assert clubs.maybe_pick_up(m, TERRAIN, fired_anything=False) == "tree" and m.club == "tree"
    loser = fresh(ATLAS, CLEAR)
    loser.severed_limbs = ["Left Arm"]
    clubs.after_phase(loser)
    clubs.after_phase(loser)                                         # counted once
    finder = fresh(ATLAS, CLEAR)                                      # (the Charger has no left hand)
    assert clubs.found_here(finder, TERRAIN) == ["limb"]
    assert clubs.maybe_pick_up(finder, TERRAIN, fired_anything=False) == "limb"
    assert clubs.found_here(fresh(ATLAS, CLEAR), TERRAIN) == []
    a, t = fresh(unarmed(ATLAS), WOODS, "N", "Red"), fresh(CHARGER, "0101", "S", "Blue")
    a.club = None
    with ScriptedDice([], default=7):
        attack_resolution.run_ranged_combat_phase(a, t, TERRAIN, BattleRNG(1))
    assert a.club == "tree"


@check
def club_attacks():
    """p.79: forward arc of the twisted torso, Piloting - 1, ceil(tons / 5)
    on the standard table, a PSR for the target; no arm weapon fired that
    turn; a damaged arm actuator +2; a tree breaks after one hit; a club
    that can't be held any more is dropped."""
    a, t = fresh(ATLAS, "0808", "N", "Red"), fresh(CHARGER, "0807", "S", "Blue")
    a.club = "tree"
    club = physical.attack_options(a, t, TERRAIN)["club"][0]
    assert club["damage"] == 20 and club["mod"] == -1 and club["table"] == "standard"
    side = fresh(CHARGER, "0909", "N")                                 # right side arc: needs a twist
    assert "club" not in physical.attack_options(a, side, TERRAIN)
    assert "club" in physical.attack_options(a, side, TERRAIN, arcs_twist(1))
    a.weapons_fired_this_turn = frozenset(id(w) for w in attack_resolution.get_weapons(a)
                                          if attack_resolution.weapon_locations(a)[id(w)] & {"Left Arm", "Right Arm"})
    assert "club" not in physical.attack_options(a, t, TERRAIN)
    a.weapons_fired_this_turn = frozenset()
    broken(a, "Left Arm", "Lower Arm Actuator")
    assert physical.attack_options(a, t, TERRAIN)["club"][0]["mod"] == 1
    a, t = fresh(ATLAS, "0808", "N", "Red"), fresh(CHARGER, "0807", "S", "Blue")
    a.club = "tree"
    before = attack_resolution.total_hp(t)
    real = physical.choose_attack
    physical.choose_attack = lambda att, tgt, tm: (real(att, tgt, tm) if att is not a else
                                                   (physical._base_tn(att, tgt, tm),
                                                    physical.attack_options(att, tgt, tm)["club"],
                                                    physical.arcs.current_action(att)))
    try:
        with Dice(other=12, psr=12):
            physical.run_physical_phase(a, t, TERRAIN, {})
    finally:
        physical.choose_attack = real
    assert before - attack_resolution.total_hp(t) >= 20 and a.club is None
    a.club = "girder"
    broken(a, "Right Arm", "Hand Actuator")
    clubs.after_phase(a)
    assert a.club is None


def arcs_twist(n):
    return physical.arcs.ArcAction(twist=n)


@check
def falls_of_several_levels():
    """p.115: falling damage x (levels + 1)."""
    m = fresh(ATLAS, "0808")
    before = attack_resolution.total_hp(m)
    with ScriptedDice([], default=7):
        piloting_rolls.resolve_fall(m, levels=2)
    assert before - attack_resolution.total_hp(m) == 30


def any_unit(path):
    with zipfile.ZipFile(os.path.join(REPO_ROOT, "data", "meks.zip")) as z:
        out = z.extract(f"meks/{path}.mtf", _TMP)
    with redirect_stdout(io.StringIO()):
        return parse_mtf(out)


@check
def talons_spikes_and_lances():
    """2026-10-21, Core pp.194-196 (INTEGRATION__physical_gear): talons on
    both legs make a DFA x1.5 (lost with a foot actuator); spikes cut a
    physical hit on their location by 4 (minimum 1) and give the attacker 2
    back; a lance that only dented armor makes a 9+ armor-piercing check -
    1 point of internal structure."""
    import INTEGRATION__dfa as dfa
    import INTEGRATION__physical_gear as gear
    caesar = fresh(any_unit("3145/NTNU RS/NTNU/Caesar CES-5D"), "0808")
    assert gear.dfa_talons(caesar)
    plain = math.ceil(caesar.mass / 10 * 3)
    assert dfa.target_damage(caesar) == int(plain * 1.5 + 0.5)
    caesar.destroyed_slot_info[(caesar.leg_locations[0], 0)] = {"name": "Foot Actuator", "instance_id": None}
    assert not gear.dfa_talons(caesar) and dfa.target_damage(caesar) == plain

    porc = fresh(any_unit("XTRs/Caveat Emptor/Porcupine PRC-3N"), "0808")
    spiked = next(loc for loc in porc.locations if gear.spike_clusters(porc, loc))
    assert gear.spike_reduce(porc, spiked, 10) == (6, True) and gear.spike_reduce(porc, spiked, 3) == (1, True)
    a = fresh(ATLAS, "0807")
    before = a.locations["Right Arm"]["armor"]
    gear.spike_retaliation(a, ["Right Arm"])
    assert a.locations["Right Arm"]["armor"] == before - 2

    t = fresh(ATLAS, "0806")
    s_before = t.locations["Center Torso"]["structure"]
    with ScriptedDice([9]):
        gear.lance_ap_check(t, "Center Torso", gear.LANCE_AP_TN, "test")
    assert t.locations["Center Torso"]["structure"] == s_before - 1
    with ScriptedDice([8]):
        gear.lance_ap_check(t, "Center Torso", gear.LANCE_AP_TN, "test")
    assert t.locations["Center Torso"]["structure"] == s_before - 1
    hachi = fresh(any_unit("3055U/Hachiwara HCA-6P"), "0808")
    assert len(gear.lances(hachi)) == 1


@check
def vibroblades():
    """p.196 (2026-10-21): activated (STUB_VIBROBLADE "on") a large vibroblade
    hits for a fixed 14 and makes 7 heat when declared; deactivated, 1 per 10
    tons + 1, capped at 14 before TSM."""
    import INTEGRATION__physical_gear as gear
    knight = fresh(any_unit("XTRs/Most Wanted/Black Knight BL-X-KNT 'Red Reaper'"), "0808")
    blade = next(s for loc in ("Left Arm", "Right Arm") for s in knight.crits[loc] if "Vibroblade" in getattr(s, "name", ""))
    assert gear.vibro_size(blade) in ("LARGE", "MEDIUM", "SMALL")
    damage, heat = gear.VIBRO[gear.vibro_size(blade)]
    assert gear.vibro_attack(knight, blade, 99, False) == (damage, heat, True)
    saved = config.STUB_VIBROBLADE
    try:
        config.STUB_VIBROBLADE = "off"
        assert gear.vibro_attack(knight, blade, 99, False) == (damage, 0, False)          # capped
        assert gear.vibro_attack(knight, blade, 4, True) == (8, 0, False)                 # TSM after the cap
    finally:
        config.STUB_VIBROBLADE = saved


@check
def shields():
    """p.195 (2026-10-21): a medium shield absorbs 5 of each hit to its own
    arm (lowered) - to the CT and that side too when raised - until its 18
    capacity is gone; rear hits bypass it; -1 Walking MP; a large one also
    stops jumping; a punch with the shield arm +2 (medium); nothing behind a
    raised shield attacks (weapons or limbs)."""
    import INTEGRATION__physical_gear as gear
    from mech_state import mech_shields, compute_walk_mp, compute_jump_mp
    knight = fresh(any_unit("3145/Davion/Black Knight BLK-NT-4D"), "0808")
    [(arm, shield, size)] = mech_shields(knight)
    assert size == "MEDIUM"
    assert compute_walk_mp(knight) == knight.base_walk_mp - 1
    assert gear.shield_absorb(knight, arm, 8, "front") == 3                  # lowered: its own arm
    assert gear.shield_absorb(knight, "Center Torso", 8, "front") == 8        # not the CT
    knight.shield_raised = arm
    assert gear.shield_absorb(knight, "Center Torso", 8, "front") == 3        # raised: the CT too
    assert gear.shield_absorb(knight, "Center Torso", 8, "rear") == 8         # rear hits bypass it
    assert attack_resolution.shielded_weapon_ids(knight) or not any(
        attack_resolution.weapon_locations(knight).get(id(w), set()) & gear.covered(knight, arm)
        for w in attack_resolution.get_weapons(knight))
    assert gear.shield_absorb(knight, "Center Torso", 20, "front") == 15      # 18 - 5 - 5 = 8 left: takes 5
    assert gear.shield_absorb(knight, "Center Torso", 20, "front") == 17      # the last 3
    assert not mech_shields(knight) and gear.raised_arm(knight) is None       # used up: gone
    assert compute_walk_mp(knight) == knight.base_walk_mp
    red = fresh(any_unit("XTRs/Most Wanted/Black Knight BL-X-KNT 'Red Reaper'"), "0808")
    assert any(size == "LARGE" for _, _, size in mech_shields(red)) and compute_jump_mp(red) == 0
    bk = fresh(any_unit("3145/Davion/Black Knight BLK-NT-4D"), "0808")
    assert gear.shield_bash(bk, arm) == 2 and gear.shield_bash(bk, "Left Arm" if arm == "Right Arm" else "Right Arm") == 0


@check
def quad_kicks():
    """p.238 (2026-10-21): a quad kicks forward with its front legs (front
    hips only needed), mule-kicks into its rear arc with its rear legs (rear
    hips, and both front legs still on); a hip hit stops kicks in its arc."""
    goliath = fresh(any_unit("3039u/Goliath GOL-1H"), "0808", "N")
    xy = charge.hex_geometry.parse_hex_label
    opts = lambda m, t: physical.options_at(m, xy("0808"), 0, 0, xy(t), 0, False, frozenset(),  # noqa: E731
                                            physical.arcs.NO_ACTION).get("kick", [])
    assert sorted(o["limb"] for o in opts(goliath, "0807")) == ["Front Left Leg", "Front Right Leg"]
    mule = opts(goliath, "0809")
    assert sorted(o["limb"] for o in mule) == ["Rear Left Leg", "Rear Right Leg"] and "mule" in mule[0]["name"]
    goliath.destroyed_hip_locations.add("Rear Left Leg")
    assert not opts(goliath, "0809") and opts(goliath, "0807")       # a rear hip: no mule kick, front still
    g2 = fresh(any_unit("3039u/Goliath GOL-1H"), "0808", "N")
    g2.locations["Front Left Leg"]["destroyed"] = True
    assert not opts(g2, "0809")                                      # a lost front leg: no mule kick


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
        print(f"{failed} of {len(CHECKS)} special-attack checks FAILED.")
        sys.exit(1)
    print(f"All {len(CHECKS)} special-attack checks passed.")


if __name__ == "__main__":
    run_all()
