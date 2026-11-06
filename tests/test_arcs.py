"""
tests/test_arcs.py - checks the arc actions (2026-10-19): torso twists in
both attack phases, reversing (flipping) arms, tripod twists and leg arcs,
quad turrets, the once-a-turn limit and the End Phase reset (Core pp.60-62,
76-83, 205, 236-238; INTEGRATION__arcs has the rules).

    python tests/test_arcs.py
"""

import os
import sys
import traceback
from types import SimpleNamespace

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402
config.STATS = False  # event log + report off: not part of a test or battery (2026-11-06)
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
import INTEGRATION__attack_resolution as attack_resolution  # noqa: E402
import INTEGRATION__arcs as arcs  # noqa: E402
import INTEGRATION__physical as physical  # noqa: E402
from INTEGRATION__attack_resolution import SideReport  # noqa: E402
import hex_geometry  # noqa: E402
from equipment import Equipment  # noqa: E402
from mtf_parser import parse_mtf, build_crit_list  # noqa: E402
from mech_state import clone_mech  # noqa: E402
from test_heat import ScriptedDice  # noqa: E402

config.VERBOSE = False
TERRAIN = orchestrator._load_map()
SYNTHETIC = parse_mtf(config.data_path("TEST_Synthetic_Loadout.mtf"))      # 50-ton biped, arm guns
TRIPOD = parse_mtf(config.data_path("Asymptote II iJ Mpulse.mtf"))         # 100-ton tripod, torso/head lasers
A = arcs.ArcAction


def fresh(template=SYNTHETIC, hex_="0808", facing="N"):
    m = clone_mech(template)
    orchestrator._attach_mech_config(m, {"hex": hex_, "facing": facing, "gunnery": 4, "piloting": 5,
                                         "min_heat": 0, "max_heat": 30}, "Test")
    return m


def xy(label):
    return hex_geometry.parse_hex_label(label)


def names(m, ids):
    return {w.name for w in attack_resolution.get_weapons(m) if id(w) in ids}


def flipper():
    """The synthetic biped with its hand and lower arm actuators taken out of
    the design (an UrbanMech-style arm), so it may reverse its arms."""
    m = fresh()
    for arm in ("Left Arm", "Right Arm"):
        m.crits[arm] = ["-Empty-" if s in ("Hand Actuator", "Lower Arm Actuator") else s for s in m.crits[arm]]
    return m


CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


@check
def twist_choices_by_mech_type():
    """p.62: one hexside left or right; tripods any hexside (p.236); prone
    mechs and quads none (pp.47, 238)."""
    assert arcs.twist_offsets(fresh()) == (0, -1, 1)
    assert sorted(arcs.twist_offsets(fresh(TRIPOD))) == [-2, -1, 0, 1, 2, 3]
    m = fresh()
    m.prone = True
    assert arcs.twist_offsets(m) == (0,) and arcs.arc_options(m) == (arcs.NO_ACTION,)
    quad = fresh()
    quad.mech_type = "quad"
    assert arcs.arc_options(quad) == (arcs.NO_ACTION,)


@check
def tripod_leg_arcs():
    """p.236: the left / right leg arcs start two hexsides left / right of the
    front, the centre leg's at the front; twists never move them."""
    m = fresh(TRIPOD, "0704", "N")
    legs = arcs.leg_offsets(m)
    behind_left, behind_right, ahead = xy("0605"), xy("0805"), xy("0702")
    key = lambda t, act=arcs.NO_ACTION: arcs.arc_keys(arcs.arcs_between(xy("0704"), t), 0, (act,), legs)[0][0]  # noqa: E731
    assert key(behind_left).legs_forward == {"Left Leg"}
    assert key(behind_right).legs_forward == {"Right Leg"}
    assert "Center Leg" in key(ahead).legs_forward and "Left Leg" not in key(ahead).legs_forward
    assert key(behind_left, A(twist=3)).legs_forward == {"Left Leg"}
    assert key(behind_left, A(twist=3)).torso_arc == arcs.FORWARD
    gun = SimpleNamespace(name="leg laser", rear_mounted=False)
    blocked = lambda k: arcs.unavailable(m, [gun], {id(gun): ("Left Leg",)}, k)  # noqa: E731
    assert not blocked(key(behind_left)) and blocked(key(behind_right))


@check
def tripod_twists_to_shoot_behind():
    """A tripod with every gun in its torso and head fires at a target in its
    rear arc by twisting the torso round (p.236) - a biped can't."""
    m, t = fresh(TRIPOD, "0808", "N"), fresh(TRIPOD, "0811", "N")       # three hexes straight behind
    with ScriptedDice([], default=12):
        attack_resolution.declare_attacks(m, t, TERRAIN, SideReport())
    assert abs(m.torso_twist) >= 2 and m.arc_action_locked
    pair = arcs.arcs_between(xy("0808"), xy("0811"))
    keys = arcs.arc_keys(pair, 0, ((A(0), A(-1), A(1))), arcs.leg_offsets(m))
    assert all(len(attack_resolution.arc_unavailable(m, k)) == len(attack_resolution.get_weapons(m)) for k, _ in keys)


@check
def reversing_arms():
    """p.62: only a design with neither hand nor lower arm actuators in both
    arms and no torso/arm split weapon; arm weapons then fire only to the
    rear; losing actuators to damage doesn't qualify; prone can't."""
    assert not arcs.can_flip_arms(fresh())
    m = flipper()
    assert arcs.can_flip_arms(m)
    assert A(flip=True) in arcs.arc_options(m) and A(flip=True) not in arcs.arc_options(m, phase="physical")
    one_arm = fresh()
    one_arm.crits["Left Arm"] = ["-Empty-" if s in ("Hand Actuator", "Lower Arm Actuator") else s
                                 for s in one_arm.crits["Left Arm"]]
    assert not arcs.can_flip_arms(one_arm)                                   # all or nothing (p.243)
    shot_off = fresh()
    for arm in ("Left Arm", "Right Arm"):
        for i, s in enumerate(shot_off.crits[arm]):
            if s in ("Hand Actuator", "Lower Arm Actuator"):
                shot_off.destroyed_slot_info[(arm, i)] = {"name": s, "instance_id": None}
                shot_off.crits[arm][i] = "DESTROYED"
    assert not arcs.can_flip_arms(shot_off)
    flipped_rear = arcs.ArcKey(arcs.REAR, frozenset(), True, None)
    flipped_fwd = arcs.ArcKey(arcs.FORWARD, frozenset(m.leg_locations), True, None)
    arm_guns = {"ISLBXAC10", "ISUltraAC5", "ISAC5"}
    assert arm_guns.isdisjoint(names(m, attack_resolution.arc_unavailable(m, flipped_rear)))
    assert arm_guns <= names(m, attack_resolution.arc_unavailable(m, flipped_fwd))
    m.prone = True
    assert A(flip=True) not in arcs.arc_options(m)


@check
def flipping_to_shoot_behind():
    """The flipper with a target straight behind reverses its arms and fires
    its arm guns (the rear laser can fire too); it can't punch afterwards."""
    m, t = flipper(), fresh(hex_="0810", facing="N")
    with ScriptedDice([], default=12):
        rep = SideReport()
        attack_resolution.declare_attacks(m, t, TERRAIN, rep)
    assert m.arms_flipped and m.torso_twist == 0 and m.arc_action_locked
    fired = {x.weapon.name for x in rep.attacks_list}
    assert "ISAC5" in fired                                       # an arm gun, firing backwards
    adjacent = fresh(hex_="0807", facing="S")
    m.weapons_fired_this_turn = frozenset()
    opts = physical.attack_options(m, adjacent, TERRAIN)
    assert "punch" not in opts and "kick" in opts


@check
def physical_phase_uses_the_ranged_twist():
    """p.62: a Ranged-phase twist stands for the Physical phase - punches
    follow it, kicks don't - and no second twist is allowed."""
    m = fresh()
    arcs.declare(m, A(twist=1))
    assert arcs.arc_options(m, phase="physical") == (A(twist=1),)
    front_left = fresh(hex_="0708", facing="S")                    # front-left hexside of a mech on 0808 facing N
    opts = physical.attack_options(m, front_left, TERRAIN)
    assert [o["name"] for o in opts["punch"]] == ["punch (Left Arm)"]
    assert "kick" in opts
    choice = physical.choose_attack(m, front_left, TERRAIN)
    assert choice[2] == A(twist=1)


@check
def physical_phase_twist_when_none_declared():
    """p.76: a mech that didn't twist in the Ranged phase may twist at the
    start of its physical declaration - here to punch with both arms."""
    m = fresh()
    right_rear = fresh(hex_="0909", facing="N")                    # right-rear hexside: right side arc
    assert [o["name"] for o in physical.attack_options(m, right_rear, TERRAIN)["punch"]] == ["punch (Right Arm)"]
    base, picks, action = physical.choose_attack(m, right_rear, TERRAIN)
    assert action == A(twist=1) and len(picks) == 2
    with ScriptedDice([], default=2):
        physical.run_physical_phase(m, right_rear, TERRAIN, {})
    assert m.torso_twist == 1 and m.arc_action_locked


@check
def tripod_physical_attacks_follow_the_torso():
    """p.236: a tripod attacks physically only into its torso's forward arc -
    kicks included - so it twists to kick a mech behind it, and never punches
    into a side arc."""
    m = fresh(TRIPOD, "0808", "N")
    behind = fresh(TRIPOD, "0809", "N")
    assert not physical.attack_options(m, behind, TERRAIN)
    choice = physical.choose_attack(m, behind, TERRAIN)
    assert choice is not None and choice[2].twist in (-2, 2, 3)
    right_rear = fresh(TRIPOD, "0909", "N")
    assert not physical.attack_options(m, right_rear, TERRAIN)     # side arc: nothing without a twist


@check
def end_phase_resets_and_unlocks():
    """pp.40, 62: the torso turns forward and the arms come back in the End
    Phase, and next turn may twist again."""
    m = fresh()
    arcs.declare(m, A(twist=-1))
    arcs.end_turn(m)
    assert m.torso_twist == 0 and not m.arms_flipped and not m.arc_action_locked
    assert arcs.arc_options(m) == (A(0), A(-1), A(1))


@check
def quad_turret():
    """p.61 / p.205: a Quad Turret's "(T)" weapons fire into the turret's
    forward arc, turned any number of hexsides each declaration; a crit on the
    turret locks it at the direction it last had."""
    crit = build_crit_list(["ISMediumLaser (T)"])
    assert crit[0].turret_mounted and not crit[0].rear_mounted
    m = fresh()
    m.mech_type = "quad"
    m.crits["Center Torso"][-1] = Equipment("ISQuadTurret")
    gun = next(w for w in attack_resolution.get_weapons(m) if w.name == "ISMediumPulseLaser")   # the rear laser
    gun.turret_mounted, gun.rear_mounted = True, False
    opts = arcs.arc_options(m)
    assert sorted(a.turret for a in opts) == [-2, -1, 0, 1, 2, 3] and all(a.twist == 0 for a in opts)
    pair = arcs.arcs_between(xy("0808"), xy("0810"))                # straight behind
    key = lambda act: arcs.arc_keys(pair, 0, (act,), arcs.leg_offsets(m))[0][0]  # noqa: E731
    assert id(gun) in attack_resolution.arc_unavailable(m, key(A(turret=0)))
    assert id(gun) not in attack_resolution.arc_unavailable(m, key(A(turret=3)))
    arcs.declare(m, A(turret=2))
    assert not getattr(m, "arc_action_locked", False)                 # turning a turret isn't a twist
    m.destroyed_slot_info[("Center Torso", len(m.crits["Center Torso"]) - 1)] = {"name": "ISQuadTurret",
                                                                                 "instance_id": None}
    arcs.end_turn(m)
    assert arcs.arc_options(m) == (A(turret=2),)


def run_all():
    failed = 0
    for fn in CHECKS:
        try:
            with ScriptedDice([], default=7):
                fn()
            print(f"PASS  {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print()
    if failed:
        print(f"{failed} of {len(CHECKS)} arc checks FAILED.")
        sys.exit(1)
    print(f"All {len(CHECKS)} arc checks passed.")


if __name__ == "__main__":
    run_all()
