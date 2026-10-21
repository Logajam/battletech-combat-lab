"""
tests/test_water.py - the water rules (2026-10-21, INTEGRATION__water;
Daniel: water "Also Yes as the next task"): depth as levels (pp.47, 51, 57),
partial cover in depth 1 (p.66), the water line and which weapons can fire
(pp.62, 67, 127), underwater ranges (p.127), heat sinks in water (p.103),
jump jets in water (p.50), running / jumping into water (pp.48, 50), falls
in water (p.115), physical attacks in water (p.77), hull breaches (p.127)
and drowning (p.117).

    python tests/test_water.py
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
import INTEGRATION__water as water  # noqa: E402
import terrain_rules  # noqa: E402
import piloting_rolls  # noqa: E402
from hex_geometry import parse_hex_label  # noqa: E402
from los import trace_los_path  # noqa: E402
from mech_state import clone_mech  # noqa: E402
from mtf_parser import parse_mtf  # noqa: E402
from test_heat import ScriptedDice  # noqa: E402

config.VERBOSE = False
ATLAS = parse_mtf(config.data_path("Atlas AS7-K.mtf"))             # 4 single heat sinks in its legs
BLACK_HAWK = parse_mtf(config.data_path("Black Hawk (Nova) F.mtf"))  # 4 of its 5 jump jets in its legs
ARCHER = parse_mtf(config.data_path("Archer ARC-2R.mtf"))

CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


def hexinfo(level=0, **features):
    return {"level": level, "features": dict(features), "impassable": False}


def lake():
    """Level-0 board: depth 1 at 0807, 0906, 0907 and 1006, depth 2 at 0806, depth 3 at 0805, depth 0 at 0809."""
    hexes = {f"{c:02d}{r:02d}": hexinfo() for c in range(1, 17) for r in range(1, 18)}
    hexes.update({"0807": hexinfo(water=["1"]), "0906": hexinfo(water=["1"]), "0907": hexinfo(water=["1"]), "1006": hexinfo(water=["1"]),
                  "0806": hexinfo(water=["2"]),
                  "0805": hexinfo(water=["3"]), "0809": hexinfo(water=["0"])})
    tm = terrain_rules.prepare_board({"width": 16, "height": 17, "hexes": hexes})
    water.set_board(tm)
    return tm


def place(template, hex_, facing="N"):
    m = clone_mech(template)
    orchestrator._attach_mech_config(m, {"hex": hex_, "facing": facing, "gunnery": 4, "piloting": 5,
                                         "min_heat": 0, "max_heat": 30}, "Test")
    m.move_mode, m.move_fc, m.movement_heat = "Walk", 1, 1
    return m


@check
def depth_is_level():
    """p.57: depth works as negative level from the surface (p.47); p.51: going
    in and out of water is a level change, on top of the water's own MP."""
    tm = lake()
    h = tm["hexes"]
    assert (h["0807"]["level"], h["0807"]["depth"], h["0807"]["surface_level"]) == (-1, 1, 0)
    assert h["0806"]["level"] == -2 and h["0809"]["level"] == 0 and "depth" not in h["0809"]
    assert terrain_rules.step_cost(h["0808"], h["0807"]) == 1 + 1 + 1     # base + depth-1 water + 1 level
    assert terrain_rules.step_cost(h["0807"], h["0806"]) == 1 + 2 + 1     # base + depth-2+ water + 1 level
    assert terrain_rules.step_cost(h["0808"], h["0806"]) == 1 + 2 + 2
    assert terrain_rules.step_cost(h["0808"], h["0805"]) is None           # 3 levels down: prohibited
    assert terrain_rules.step_cost(h["0807"], h["0808"]) == 1 + 1          # climbing out: 1 level
    assert terrain_rules.step_cost(h["0808"], h["0809"]) == 1              # depth 0: no effect (p.51)


@check
def partial_cover_in_depth_one():
    """p.66: a 'Mech standing in depth 1 water has partial cover (+1), even at
    range 1 and from higher attackers - not against a fully submerged
    attacker (p.67); a shallower water hex is not a hill."""
    tm = lake()
    xy = parse_hex_label
    assert trace_los_path(xy("0811"), xy("0807"), tm).steps[-1].partial_cover == 1
    assert trace_los_path(xy("0808"), xy("0807"), tm).steps[-1].partial_cover == 1       # range 1
    assert trace_los_path(xy("0806"), xy("0807"), tm).steps[-1].partial_cover == 0       # from depth 2
    assert trace_los_path(xy("0811"), xy("0806"), tm).steps[-1].partial_cover == 0       # 0807 (-1) is no hill


@check
def which_weapons_fire():
    """pp.62, 67, 127: the Underwater Attacks Table and energy-only from a
    submerged location."""
    mech = SimpleNamespace(leg_locations=["Left Leg", "Right Leg"],
                           locations={"Left Leg": {}, "Right Leg": {}, "Left Arm": {}, "Center Torso": {}})
    laser_arm = SimpleNamespace(damage_type="Energy")
    ac_arm = SimpleNamespace(damage_type="Ballistic")
    laser_leg = SimpleNamespace(damage_type="Energy")
    srm_leg = SimpleNamespace(damage_type="Missile")
    weapons = [laser_arm, ac_arm, laser_leg, srm_leg]
    locs = {id(laser_arm): {"Left Arm"}, id(ac_arm): {"Left Arm"}, id(laser_leg): {"Left Leg"},
            id(srm_leg): {"Right Leg"}}
    G, P, S = water.GROUND, water.PARTIAL, water.SUBMERGED
    ids = lambda *ws: frozenset(id(w) for w in ws)            # noqa: E731
    assert water.blocked_weapon_ids(mech, weapons, locs, G, G) == frozenset()
    assert water.blocked_weapon_ids(mech, weapons, locs, G, P) == frozenset()
    assert water.blocked_weapon_ids(mech, weapons, locs, G, S) is None          # the water line
    assert water.blocked_weapon_ids(mech, weapons, locs, S, G) is None
    assert water.blocked_weapon_ids(mech, weapons, locs, P, G) == ids(laser_leg, srm_leg)   # no leg weapons
    assert water.blocked_weapon_ids(mech, weapons, locs, P, P) == ids(srm_leg)  # submerged legs: energy only
    assert water.blocked_weapon_ids(mech, weapons, locs, P, S) == ids(laser_arm, ac_arm, srm_leg)
    assert water.blocked_weapon_ids(mech, weapons, locs, S, S) == ids(ac_arm, srm_leg)
    assert water.blocked_weapon_ids(mech, weapons, locs, S, P) == ids(ac_arm, srm_leg)


@check
def underwater_ranges():
    """p.127: a submerged energy weapon uses the next bracket (+2 TN at short
    and medium) and can't fire at long range."""
    base = lambda w, bracket, plan=None: 0                   # noqa: E731
    mech = SimpleNamespace(leg_locations=["Left Leg"], locations={"Left Leg": {}, "Left Arm": {}})
    leg, arm = SimpleNamespace(), SimpleNamespace()
    locs = {id(leg): {"Left Leg"}, id(arm): {"Left Arm"}}
    assert water.range_adjuster(mech, locs, water.GROUND, base) is base
    partial = water.range_adjuster(mech, locs, water.PARTIAL, base)
    assert partial(leg, "short") == 2 and partial(leg, "medium") == 2 and partial(leg, "long") >= 13
    assert partial(arm, "short") == 0
    under = water.range_adjuster(mech, locs, water.SUBMERGED, base)
    assert under(arm, "medium") == 2


@check
def heat_sinks_in_water():
    """p.103: submerged sinks dissipate double, at most 6 more; depth 1 only
    the leg sinks (Atlas: 4 single), deeper or prone in water all of them."""
    lake()
    atlas = place(ATLAS, "0808")
    assert water.dissipation_bonus(atlas) == 0
    atlas.hex = "0807"
    assert water.dissipation_bonus(atlas) == 4
    atlas.prone = True
    assert water.dissipation_bonus(atlas) == 6                   # 20 sinks, capped at 6
    atlas.prone, atlas.hex = False, "0806"
    assert water.dissipation_bonus(atlas) == 6
    archer = place(ARCHER, "0807")                               # no leg sinks
    assert water.dissipation_bonus(archer) == 0


@check
def jump_jets_in_water():
    """p.50: leg jump jets don't fire in depth 1; no jumping at depth 2+."""
    lake()
    hawk = place(BLACK_HAWK, "0808")
    assert water.jump_mp(hawk) == 5
    hawk.hex = "0807"
    assert water.jump_mp(hawk) == 1
    hawk.hex = "0806"
    assert water.jump_mp(hawk) == 0


@check
def falls_and_psrs_in_water():
    """p.115: falls in water do half damage; pp.48, 50: running or jumping
    into depth 1+ water forces a PSR, and a failed jump into water falls the
    depth in levels."""
    lake()
    atlas = place(ATLAS, "0807")                  # 100 t: 10 a level
    hp = attack_resolution.total_hp(atlas)
    with ScriptedDice([], default=8):
        piloting_rolls.resolve_fall(atlas, levels=0)
    assert attack_resolution.total_hp(atlas) == hp - 5
    hawk = place(BLACK_HAWK, "0806")              # 50 t: 5 a level; depth 2
    hawk.move_mode, hawk.move_fc = "Jump", 3
    hp = attack_resolution.total_hp(hawk)
    with ScriptedDice([2], default=8):            # the PSR fails; the rest (locations, seatbelt) don't matter
        orchestrator._water_psr(hawk)
    assert hawk.prone and attack_resolution.total_hp(hawk) == hp - 7        # 5 x (2 + 1) // 2
    runner = place(ARCHER, "0807")
    runner.move_mode, runner.move_fc = "Run", 2
    with ScriptedDice([12]):
        orchestrator._water_psr(runner)
    assert not runner.prone
    walker = place(ARCHER, "0807")                # walking in: no roll
    with ScriptedDice([]):
        orchestrator._water_psr(walker)


@check
def attacks_across_the_water_line():
    """p.62: no attack from land at a fully submerged 'Mech, or back."""
    tm = lake()
    atlas, archer = place(ATLAS, "0809", "N"), place(ARCHER, "0806", "S")
    reports = {"Test": attack_resolution.SideReport()}
    attack_resolution.declare_attacks(atlas, archer, tm, reports["Test"])
    assert reports["Test"].attacks == 0
    archer.hex = "0807"                                          # depth 1: fair game
    attack_resolution.declare_attacks(atlas, archer, tm, reports["Test"])
    assert reports["Test"].attacks > 0


@check
def movement_scoring_sees_the_water_line():
    """The bot's scoring (ranged_combat.MoveEvaluator): from land it can't hurt
    a fully submerged 'Mech, nor be hurt by it."""
    tm = lake()
    atlas, archer = place(ATLAS, "0811", "N"), place(ARCHER, "0806", "S")
    ev = ranged_combat.MoveEvaluator(atlas, archer, tm)
    options = [(*parse_hex_label("0811"), 0, 0, "Walk", 0), (*parse_hex_label("1006"), 5, 1, "Walk", 4)]
    cands = {c.hex: c for c in ev.evaluate("0806", "S", 0, "Walk", 0, ev.prepare(options))}
    assert cands["0811"].dealt == 0.0 and cands["0811"].received == 0.0
    # From depth 1 (1006, 2 hexes away), only leg weapons can fire at a submerged target
    # (p.127) - the Atlas has none.
    assert cands["1006"].dealt == 0.0
    # The same spots against a target on land: full fire from land, arm / torso weapons from depth 1.
    cands = {c.hex: c for c in ev.evaluate("0808", "S", 0, "Walk", 0, ev.prepare(options))}
    assert cands["0811"].dealt > 0.0 and cands["1006"].dealt > 0.0


@check
def physical_attacks_in_water():
    """p.77: no physical attack on a fully submerged 'Mech from above the water
    (from depth 1 only a kick, its legs being under water); none from under
    water at a 'Mech on land; half damage to underwater locations."""
    import INTEGRATION__physical as physical
    G, P, S = water.GROUND, water.PARTIAL, water.SUBMERGED
    assert water.physical_allowed(G, G) is None and water.physical_allowed(G, P) is None
    assert water.physical_allowed(G, S) == frozenset() and water.physical_allowed(S, G) == frozenset()
    assert water.physical_allowed(P, S) == frozenset({"kick"}) and water.physical_allowed(S, S) is None
    assert water.physical_allowed(S, P) is None
    tm = lake()
    atlas, archer = place(ATLAS, "0807", "N"), place(ARCHER, "0806", "S")       # depth 1 next to depth 2
    assert set(physical.attack_options(atlas, archer, tm)) <= {"kick"}
    land = place(ATLAS, "0707", "NE")                                          # land, adjacent to 0806
    assert physical.attack_options(land, archer, tm) == {}
    assert water.physical_damage(archer, "Center Torso", 9) == 4               # all of a submerged 'Mech
    assert water.physical_damage(atlas, "Left Leg", 9) == 4                    # depth 1: the legs
    assert water.physical_damage(atlas, "Center Torso", 9) == 9


@check
def hull_breaches():
    """p.127: an underwater location that takes damage breaches on 2-4; a
    breached leg counts as destroyed; a breached side torso breaches its arm;
    a location with no armor left breaches as soon as it is under water."""
    lake()
    atlas = place(ATLAS, "0807")                                    # depth 1: legs under water
    with ScriptedDice([5]):
        attack_resolution.apply_damage(atlas, "Left Leg", 2)
    assert not water.breached(atlas)
    with ScriptedDice([4]):
        attack_resolution.apply_damage(atlas, "Left Leg", 2)
    assert water.breached(atlas) == {"Left Leg"} and atlas.locations["Left Leg"]["destroyed"]
    with ScriptedDice([]):                                          # above the water: no roll
        attack_resolution.apply_damage(atlas, "Left Torso", 2)
    deep = place(ATLAS, "0806")                                     # depth 2: everything under water
    with ScriptedDice([2]):
        attack_resolution.apply_damage(deep, "Right Torso", 2)
    assert {"Right Torso", "Right Arm"} <= water.breached(deep)
    stripped = place(ARCHER, "0808")
    stripped.locations["Left Arm"]["armor"] = 0
    water.auto_breaches(stripped)
    assert not water.breached(stripped)                             # on land
    stripped.hex = "0806"
    water.auto_breaches(stripped)
    assert "Left Arm" in water.breached(stripped)


@check
def drowning():
    """p.117: a life support critical and fully submerged in the End Phase -
    the MechWarrior takes a hit."""
    lake()
    atlas = place(ATLAS, "0806")
    water.drowning(atlas, has_life_support_hit=False)
    assert atlas.pilot_hits == 0
    water.drowning(atlas, has_life_support_hit=True)
    assert atlas.pilot_hits == 1
    atlas.hex = "0807"                                              # depth 1, standing: not submerged
    water.drowning(atlas, has_life_support_hit=True)
    assert atlas.pilot_hits == 1


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
    water.set_board(None)
    print()
    if failed:
        print(f"{len(failed)} of {len(CHECKS)} water checks FAILED: {', '.join(failed)}")
        return 1
    print(f"All {len(CHECKS)} water checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
