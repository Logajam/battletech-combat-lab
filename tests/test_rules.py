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
