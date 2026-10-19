"""
tests/test_rules.py - checks the rules that replaced stubs (2026-10-19):
attack direction (Core p.73), cluster damage groupings, Streak and MRM
(pp.87, 181, 186-187), movement after standing up (p.51), and the later
additions listed in each check's docstring.

    python tests/test_rules.py

Dice are scripted as in tests/test_heat.py.
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
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
import INTEGRATION__attack_resolution as attack_resolution  # noqa: E402
import INTEGRATION__ranged_combat as ranged_combat  # noqa: E402
import INTEGRATION__weapon_rules as weapon_rules  # noqa: E402
import INTEGRATION__expected_damage as expected_damage  # noqa: E402
import hex_geometry  # noqa: E402
from mtf_parser import parse_mtf  # noqa: E402
from mech_state import clone_mech  # noqa: E402
from test_heat import ScriptedDice  # noqa: E402

config.VERBOSE = False
TERRAIN = orchestrator._load_map()
SYNTHETIC = parse_mtf(config.data_path("TEST_Synthetic_Loadout.mtf"))


def fresh(template=SYNTHETIC, hex_="0808", facing="N"):
    m = clone_mech(template)
    orchestrator._attach_mech_config(m, {"hex": hex_, "facing": facing, "gunnery": 4, "piloting": 5,
                                         "min_heat": 0, "max_heat": 30}, "Test")
    return m


def weapon(name, damage_type="Missile", rack=None, dps=1, heat=4):
    return SimpleNamespace(name=name, damage_type=damage_type, rack_size=rack, damage_per_shot=dps,
                           heat=heat, category="weapon")


CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


@check
def attack_direction():
    """p.73: front / rear one hexside each, sides two each, read off the
    hexside the LOS enters the target's hex through."""
    t = hex_geometry.parse_hex_label("0808")
    side = lambda a, f: attack_resolution.attack_side(hex_geometry.parse_hex_label(a), t,   # noqa: E731
                                                     hex_geometry.compass_to_facing(f), TERRAIN)
    assert side("0805", "N") == "front" and side("0811", "N") == "rear"
    assert side("1107", "N") == "right" and side("1109", "N") == "right"      # NE and SE hexsides
    assert side("0507", "N") == "left" and side("0509", "N") == "left"        # NW and SW hexsides
    assert side("0805", "S") == "rear" and side("1107", "NE") == "front"      # turns with the target


@check
def cluster_groupings():
    """pp.87, 181: SRM C2, LRM / MRM C5, ATM C6, default 5; leftover last."""
    assert weapon_rules.damage_groupings(weapon("ISSRM6", rack=6, dps=2), 12) == [2] * 6
    assert weapon_rules.damage_groupings(weapon("ISLRM15", rack=15), 12) == [5, 5, 2]
    assert weapon_rules.damage_groupings(weapon("ISMRM20", rack=20), 13) == [5, 5, 3]
    assert weapon_rules.damage_groupings(weapon("CLATM6", rack=6, dps=2), 8) == [6, 2]
    assert weapon_rules.damage_groupings(weapon("RL10", rack=10), 7) == [5, 2]


@check
def streak_and_mrm():
    """p.187: a Streak hit lands every missile (no cluster roll), a miss has
    no heat; p.186: MRM Cluster rolls -1."""
    streak = weapon("CLStreakSRM6", rack=6, dps=2)
    assert expected_damage.expected_damage_per_hit(streak) == 12
    assert weapon_rules.cluster_roll_modifier(weapon("ISMRM10", rack=10)) == -1
    assert expected_damage.expected_damage_per_hit(weapon("ISMRM10", rack=10)) == \
        expected_damage.expected_cluster_hits(10, -1)
    assert weapon_rules.cluster_roll_modifier(weapon("ISLRM10", rack=10)) == 0


@check
def standing_up_then_moving():
    """p.51: a mech that stands may face any way for free and spend its
    remaining MP in its declared mode (Run); a mech that began prone can't
    jump. With 0 MP left it can still pick any facing in its hex."""
    m = fresh()
    zero = list(ranged_combat.movement_options(m, TERRAIN, standup_mp=0))
    assert sorted(f for _, _, f, _, _, _ in zero) == list(range(6))
    assert {mode for *_, mode, _ in zero} == {"Run"} and {fc for _, _, _, fc, _, _ in zero} == {0}
    three = list(ranged_combat.movement_options(m, TERRAIN, standup_mp=3))
    assert max(fc for _, _, _, fc, _, _ in three) == 3
    assert all(mode == "Run" for *_, mode, _ in three)
    normal = list(ranged_combat.movement_options(m, TERRAIN))
    assert {mode for *_, mode, _ in normal} >= {"Stand Still", "Walk", "Run"}


@check
def weapon_and_equipment_modifiers():
    """Weapon entries pp.184-189 and targeting computer p.200."""
    from equipment import Equipment
    cases = {"ISMediumPulseLaser": -2, "CLERMediumPulseLaser": -1, "ISMediumXPulseLaser": -2,
             "CLHeavyMediumLaser": 1, "CLImprovedHeavyMediumLaser": 0, "ISMediumReengineeredLaser": -1,
             "ISSBGR": -1, "RL10": 1, "ISMediumLaser": 0, "ISAC5": 0}
    for name, want in cases.items():
        assert weapon_rules.weapon_tn_modifier(weapon(name, damage_type="Energy"), "short") == want, name
    m, t = fresh(), fresh(hex_="0812")
    mpl = next(w for w in attack_resolution.get_weapons(m) if "Pulse" in w.name)
    lrm = next(w for w in attack_resolution.get_weapons(m) if "LRM" in w.name)
    assert attack_resolution.tn_adjuster(m, t)(mpl, "short") == -2
    m.crits["Left Torso"][-1] = Equipment("ISTargeting Computer", category="misc")
    adjust = attack_resolution.tn_adjuster(m, t)
    assert adjust(mpl, "short") == -3 and adjust(lrm, "short") == 0        # cluster: no TC


@check
def sensors_and_arm_crits():
    """p.98: sensors +2 then no fire (torso cockpit p.203: +2, +4, none);
    shoulder +4 / upper arm +1 for that arm's weapons."""
    m = fresh()
    assert attack_resolution.sensor_modifier(m) == 0
    m.destroyed_slot_info[("Head", 1)] = {"name": "Sensors", "instance_id": None}
    assert attack_resolution.sensor_modifier(m) == 2
    m.destroyed_slot_info[("Head", 4)] = {"name": "Sensors", "instance_id": None}
    assert attack_resolution.sensor_modifier(m) is None and attack_resolution.firing_conditions(m) is None
    m.torso_cockpit = True
    assert attack_resolution.sensor_modifier(m) == 4

    m = fresh()
    ac5 = next(w for w in attack_resolution.get_weapons(m) if w.name == "ISAC5")    # Right Arm
    locs = attack_resolution.weapon_locations(m)[id(ac5)]
    m.destroyed_slot_info[("Right Arm", 1)] = {"name": "Upper Arm Actuator", "instance_id": None}
    assert attack_resolution.arm_actuator_modifier(m, locs) == 1
    m.destroyed_slot_info[("Right Arm", 0)] = {"name": "Shoulder", "instance_id": None}
    assert attack_resolution.arm_actuator_modifier(m, locs) == 4
    assert attack_resolution.arm_actuator_modifier(m, {"Left Torso"}) == 0


@check
def prone_attacker_and_target():
    """p.66: prone target -2 adjacent / +1 farther. p.67: firing prone +2,
    prop arm (least damage) and legs can't fire. p.231: intact tripod +1,
    only leg weapons lost."""
    m = fresh()
    m.prone = True
    assert attack_resolution.prone_target_modifier(m, 1) == -2
    assert attack_resolution.prone_target_modifier(m, 2) == 1
    mod, out = attack_resolution.prone_fire(m)
    names = {w.name for w in attack_resolution.get_weapons(m) if id(w) in out}
    assert mod == 2 and names == {"ISAC5"}          # right arm (AC/5) props: less damage than LB-X + UAC
    m.locations["Left Arm"]["destroyed"] = m.locations["Right Arm"]["destroyed"] = True
    assert attack_resolution.prone_fire(m) is None   # no arm to prop on

    tripod = fresh(parse_mtf(config.data_path("Asymptote II iJ Mpulse.mtf")))
    tripod.prone = True
    mod, out = attack_resolution.prone_fire(tripod)
    assert mod == 1 and not out                       # its lasers are in the torsos and head
    assert attack_resolution.prone_fire(fresh()) == (0, frozenset())


@check
def rear_mounted_weapons():
    """p.60: only (R) weapons fire into the rear arc, and only there."""
    m = fresh()
    rear = {w.name for w in attack_resolution.get_weapons(m) if w.rear_mounted}
    assert rear == {"ISMediumPulseLaser"}
    names = lambda ids: {w.name for w in attack_resolution.get_weapons(m) if id(w) in ids}   # noqa: E731
    assert names(attack_resolution.arc_unavailable(m, False)) == {"ISMediumPulseLaser"}
    assert "ISMediumPulseLaser" not in names(attack_resolution.arc_unavailable(m, True))
    assert len(attack_resolution.arc_unavailable(m, True)) == len(attack_resolution.get_weapons(m)) - 1


@check
def ammunition():
    """pp.72-73, 95-96, 180, 182: shots per ton per bin, one shot per firing
    from that weapon's own ammo, empty bins can't fire or explode, explosion
    = shots x damage capped at 20, one-shots and rocket launchers fire once."""
    import INTEGRATION__ammo as ammo
    m = fresh()
    ws = {w.name: w for w in attack_resolution.get_weapons(m)}
    lrm, ac5, lbx = ws["ISLRM15"], ws["ISAC5"], ws["ISLBXAC10"]
    bins = ammo.bins_for(m, lrm)
    assert [b.shots_left for b in bins] == [8, 8] and all(b.explosion_damage == 20 for b in bins)
    ac5_bin = ammo.bins_for(m, ac5)[0]
    assert ac5_bin.shots_left == 20 and ammo.bins_for(m, lbx) == []           # no LB-X ammo aboard
    assert id(lbx) in ammo.unavailable_weapons(m) and id(ac5) not in ammo.unavailable_weapons(m)
    ac5_bin.shots_left = 3
    ammo._update_explosion(ac5_bin)
    assert ac5_bin.explosion_damage == 15                                     # 3 shots x 5
    for _ in range(3):
        ammo.spend(m, ac5)
    assert ac5_bin.shots_left == 0 and not ac5_bin.is_explosive
    assert id(ac5) in ammo.unavailable_weapons(m)
    ammo.spend(m, lrm)
    assert sorted(b.shots_left for b in bins) == [7, 8]                       # one bin drains first
    ammo.spend(m, lrm)
    assert sorted(b.shots_left for b in bins) == [6, 8]

    one_shot = SimpleNamespace(name="LRM 15 (OS)", damage_type="Missile", rack_size=15, damage_per_shot=1)
    rl = SimpleNamespace(name="RL10", damage_type="Missile", rack_size=10, damage_per_shot=1)
    assert ammo.is_one_shot(one_shot) and ammo.is_one_shot(rl) and not ammo.is_one_shot(lrm)


@check
def home_edge_deployment():
    """p.37: deployment-roll loser picks an edge, winner gets the opposite;
    a mech enters into any edge hex, any facing, MP counted from that hex."""
    assert orchestrator._edge_hexes(TERRAIN, "N") == [f"{c:02d}01" for c in range(1, 17)]
    assert orchestrator._edge_hexes(TERRAIN, "W") == [f"01{r:02d}" for r in range(1, 18)]
    a, b = fresh(), fresh()
    a.side_name, b.side_name = "Red", "Blue"
    from INTEGRATION__rng import BattleRNG
    orchestrator._deploy_home_edges(a, b, TERRAIN, BattleRNG(seed=1))
    edges = {a.home_edge[0][2:] == a.home_edge[-1][2:], b.home_edge[0][2:] == b.home_edge[-1][2:]}
    assert a.hex is None and b.hex is None and len(edges) == 1          # both N/S or both E/W
    assert set(a.home_edge).isdisjoint(b.home_edge)
    m = fresh()
    opts = list(ranged_combat.movement_options(m, TERRAIN, entry_edge=["0801"]))
    first = [o for o in opts if (o[0], o[1]) == hex_geometry.parse_hex_label("0801")]
    cheapest = min(first, key=lambda o: o[5])
    assert cheapest[3] == 1 and cheapest[5] == 1                        # entry hex: 1 hex moved, 1 MP (clear)
    assert max(fc for _, _, _, fc, _, _ in opts) <= 6 and all(mode in ("Walk", "Run") for *_, mode, _ in opts)


@check
def physical_attacks():
    """pp.76-83: adjacent only; punch 1/10 tons, kick 1/5 tons; actuator
    effects; fired arm weapons stop that arm punching; arcs; TSM doubles."""
    import INTEGRATION__physical as physical
    a = fresh(hex_="0808", facing="N")                         # 50-ton synthetic biped
    t = fresh(hex_="0807", facing="S")                         # directly in front
    opts = physical.attack_options(a, t, TERRAIN)
    assert {o["damage"] for o in opts["punch"]} == {5} and {o["damage"] for o in opts["kick"]} == {10}
    assert all(o["mod"] == -1 for o in opts["kick"])
    assert not physical.attack_options(a, fresh(hex_="0806"), TERRAIN)        # not adjacent

    a.weapons_fired_this_turn = frozenset(id(w) for w in attack_resolution.get_weapons(a) if w.name == "ISAC5")
    assert [o["name"] for o in physical.attack_options(a, t, TERRAIN)["punch"]] == ["punch (Left Arm)"]
    a.weapons_fired_this_turn = frozenset()

    a.destroyed_slot_info[("Left Arm", 2)] = {"name": "Lower Arm Actuator", "instance_id": None}
    left = next(o for o in physical.attack_options(a, t, TERRAIN)["punch"] if "Left" in o["name"])
    assert left["mod"] == -1 + 2 and left["damage"] == 2                      # +2, half damage (5 // 2)
    a.destroyed_slot_info[("Left Leg", 0)] = {"name": "Hip", "instance_id": None}
    a.destroyed_hip_locations.add("Left Leg")
    assert "kick" not in physical.attack_options(a, t, TERRAIN)               # a hip hit: no kicks

    b = fresh(hex_="0808", facing="N")
    behind = fresh(hex_="0809", facing="N")                                   # rear hexside
    assert not physical.attack_options(b, behind, TERRAIN)
    right_rear = fresh(hex_="0909", facing="N")                               # right-rear hexside: side arc
    side_opts = physical.attack_options(b, right_rear, TERRAIN)
    assert [o["name"] for o in side_opts["punch"]] == ["punch (Right Arm)"] and "kick" not in side_opts
    b.tsm_active = True
    assert {o["damage"] for o in physical.attack_options(b, t, TERRAIN)["kick"]} == {20}


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
    print(f"All {len(CHECKS)} rule checks passed." if not failed else f"{failed} of {len(CHECKS)} rule checks FAILED.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_all())
