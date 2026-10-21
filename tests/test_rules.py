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
import INTEGRATION__arcs as arcs  # noqa: E402
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
    fwd, rear_arc = arcs.FORWARD, arcs.REAR
    assert names(attack_resolution.arc_unavailable(m, arcs.simple_key(m, fwd))) == {"ISMediumPulseLaser"}
    assert "ISMediumPulseLaser" not in names(attack_resolution.arc_unavailable(m, arcs.simple_key(m, rear_arc)))
    assert len(attack_resolution.arc_unavailable(m, arcs.simple_key(m, rear_arc))) == len(attack_resolution.get_weapons(m)) - 1
    # side arcs (p.60): only that side's arm weapons (and not the rear-mounted laser)
    assert names(attack_resolution.arc_unavailable(m, arcs.simple_key(m, arcs.LEFT))) == {"ISMediumPulseLaser", "ISLRM15", "ISSRM6", "ISAC5"}
    assert names(attack_resolution.arc_unavailable(m, arcs.simple_key(m, arcs.RIGHT))) == {"ISMediumPulseLaser", "ISLRM15", "ISSRM6",
                                                                      "ISLBXAC10", "ISUltraAC5"}


@check
def ammunition():
    """pp.72-73, 95-96, 180, 182: shots per ton per bin, one shot per firing
    from that weapon's own ammo, empty bins can't fire or explode, explosion
    base damage = shots x damage (the caps are apply_explosion's since
    2026-10-20), one-shots and rocket launchers fire once."""
    import INTEGRATION__ammo as ammo
    m = fresh()
    ws = {w.name: w for w in attack_resolution.get_weapons(m)}
    lrm, ac5, lbx = ws["ISLRM15"], ws["ISAC5"], ws["ISLBXAC10"]
    bins = ammo.bins_for(m, lrm)
    assert [b.shots_left for b in bins] == [8, 8] and all(b.explosion_damage == 8 * 15 for b in bins)
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


def _open_board(**changes):
    """A copy of the loaded board with every hex level 0 and clear, then the
    given hexes changed: label=(level, features)."""
    board = {k: v for k, v in TERRAIN.items() if k != "hexes"}
    board["hexes"] = {label: {"level": 0, "features": {}, "impassable": False} for label in TERRAIN["hexes"]}
    for label, (level, features) in changes.items():
        board["hexes"][label] = {"level": level, "features": features, "impassable": False}
    return board


@check
def target_in_woods_and_partial_cover():
    """2026-10-20 rules review. p.66 / pp.68-69: +1 if the target is in light
    woods, +2 heavy; the target's own hex never blocks LOS (p.57). p.66:
    partial cover needs an intervening hex one level up next to the target -
    never the attacker's own hex at range 1 - and the cover value is on the
    trace's last step, where callers read it."""
    from los import has_los, trace_los_path
    a, t = hex_geometry.parse_hex_label("0805"), hex_geometry.parse_hex_label("0808")
    assert has_los(a, t, _open_board()).modifier == 0
    assert has_los(a, t, _open_board(**{"0808": (0, {"woods": ["1"]})})).modifier == 1
    assert has_los(a, t, _open_board(**{"0808": (0, {"woods": ["2"]})})).modifier == 2
    # Two light woods between (2 points, not a block) + heavy woods on the target: LOS, +4.
    board = _open_board(**{"0806": (0, {"woods": ["1"]}), "0807": (0, {"woods": ["1"]}),
                           "0808": (0, {"woods": ["2"]})})
    los = has_los(a, t, board)
    assert los.los and los.modifier == 4, los
    # The attacker's own woods change nothing.
    assert has_los(a, t, _open_board(**{"0805": (0, {"woods": ["2"]})})).modifier == 0
    # Partial cover: a level-1 hex next to the target on the line.
    trace = trace_los_path(a, t, _open_board(**{"0807": (1, {})}))
    assert trace.result.modifier == 1 and trace.steps[-1].partial_cover == 1
    # Range 1 with the attacker one level up: no partial cover from its own hex.
    adj = hex_geometry.parse_hex_label("0807")
    trace = trace_los_path(adj, t, _open_board(**{"0807": (1, {})}))
    assert trace.result.modifier == 0 and trace.steps[-1].partial_cover == 0


@check
def leg_hits_in_partial_cover_and_floating_head_hit():
    """2026-10-20 rules review. pp.66, 73: a leg hit on a target in partial
    cover strikes the cover - no damage. p.95 / p.117: a floating-critical
    re-roll that lands on the head still costs the MechWarrior a hit."""
    m = fresh()
    leg = m.locations["Right Leg"]["armor"]
    with ScriptedDice([5]):                               # 5 on the front table: right leg
        attack_resolution._resolve_hit(m, 5, attack_resolution.DamageType.ENERGY, "front", cover=True)
    assert m.locations["Right Leg"]["armor"] == leg
    with ScriptedDice([5]):
        attack_resolution._resolve_hit(m, 5, attack_resolution.DamageType.ENERGY, "front")
    assert m.locations["Right Leg"]["armor"] == leg - 5

    m = fresh()
    head = m.locations["Head"]["armor"]
    with ScriptedDice([2, 12, 2]):                        # TAC, floating re-roll: head; crit check 2
        attack_resolution._resolve_hit(m, 2, attack_resolution.DamageType.ENERGY, "front")
    assert m.pilot_hits == 1 and m.locations["Head"]["armor"] == head - 2


class FallSide:
    """Sets config.pick_number (the fall-side 1D6) to always give `die`."""
    def __init__(self, die):
        self.die = die

    def __enter__(self):
        self.saved = config.pick_number
        config.pick_number = lambda n, prompt="": self.die

    def __exit__(self, *exc):
        config.pick_number = self.saved


@check
def falls_and_seatbelt_checks():
    """2026-10-20, Daniel: rules as written. p.115: 1D6 for the side - 1 =
    rear, else front. p.117: seatbelt check at Piloting + levels fallen only;
    automatic hit when immobile or the target number is over 12."""
    import piloting_rolls
    config.PILOTING = 5
    m = fresh()
    dmg = piloting_rolls.fall_damage(m)                # ceil(tons / 10)
    groups = -(-dmg // 5)
    front, rear = m.locations["Center Torso"]["armor"], m.locations["Center Torso"]["rear_armor"]
    assert dmg <= rear                                  # stays in the rear armor: no critical check
    with ScriptedDice([7] * groups + [4]), FallSide(1):   # every group to the CT; seatbelt 4 < 5
        piloting_rolls.resolve_fall(m)
    assert m.locations["Center Torso"]["rear_armor"] == rear - dmg and m.pilot_hits == 1
    assert m.locations["Center Torso"]["armor"] == front
    m = fresh()
    with ScriptedDice([7] * groups + [5]), FallSide(4):
        piloting_rolls.resolve_fall(m)
    assert m.locations["Center Torso"]["armor"] == front - dmg and m.pilot_hits == 0
    m = fresh()
    with ScriptedDice(([6, 8] * 3 * groups)[:3 * groups] + [7]), FallSide(4):   # 2 levels: x3 damage, spread over
        piloting_rolls.resolve_fall(m, levels=2)                    # the side torsos; needs 5 + 2 = 7
    assert m.pilot_hits == 0
    m = fresh()
    with ScriptedDice(([6, 8] * 3 * groups)[:3 * groups] + [6]), FallSide(4):
        piloting_rolls.resolve_fall(m, levels=2)
    assert m.pilot_hits == 1
    m = fresh()
    m.shutdown = True                                  # immobile: the hit is automatic, no roll
    with ScriptedDice([7] * groups), FallSide(4):
        piloting_rolls.resolve_fall(m)
    assert m.pilot_hits == 1


@check
def one_psr_per_trigger():
    """2026-10-20, Daniel: rules as written. p.110: one PSR per trigger, each
    at the sum of all the phase's modifiers, stopping at the first failure;
    one roll per leg however many actuators it lost. p.111: running with a
    gyro hit and a destroyed hip = two rolls."""
    import piloting_rolls
    config.PILOTING = 5
    m = fresh()
    piloting_rolls.snapshot_preexisting_damage(m)
    piloting_rolls.snapshot_pre_attack_phase(m)
    m.locations["Center Torso"]["armor"] -= 20                    # 20+ damage: +1, one roll
    m.destroyed_leg_actuators["Left Leg"] = 2                     # two actuators, one leg: +2, one roll
    with ScriptedDice([8, 8]):                                     # both at 5 + 3 = 8: stands
        piloting_rolls.resolve_attack_phase_psr(m)
    assert not m.prone
    m = fresh()
    piloting_rolls.snapshot_preexisting_damage(m)
    piloting_rolls.snapshot_pre_attack_phase(m)
    m.locations["Center Torso"]["armor"] -= 20
    m.destroyed_leg_actuators["Left Leg"] = 1
    with ScriptedDice([6, 7, 7, 7]), FallSide(4):                 # first roll fails (needs 7): no second
        piloting_rolls.resolve_attack_phase_psr(m)                # roll; 10 fall damage + seatbelt
    assert m.prone

    m = fresh()
    m.gyro_hits = 1
    m.destroyed_hip_locations = {"Left Leg"}
    assert piloting_rolls.movement_psr_count(m, "running") == 2
    assert piloting_rolls.movement_psr_count(fresh(), "running") == 0


@check
def fight_to_the_death():
    """2026-10-20, Daniel's option. False (default): a destroyed gyro or both
    legs destroyed is a kill. True, the rules as written: a destroyed gyro
    can't stand but isn't destroyed (p.98); both legs gone = immobile (pp.49,
    90); immobile with no ranged weapons = destroyed (p.99)."""
    import piloting_rolls
    from mech_state import is_destroyed, is_immobile
    saved = config.FIGHT_TO_THE_DEATH
    try:
        for to_the_death in (False, True):
            config.FIGHT_TO_THE_DEATH = to_the_death
            m = fresh()
            m.gyro_hits = 2
            assert is_destroyed(m) == (not to_the_death)
            assert not piloting_rolls.can_stand(m)
            m = fresh()
            m.locations["Left Leg"]["destroyed"] = m.locations["Right Leg"]["destroyed"] = True
            assert is_immobile(m) and is_destroyed(m) == (not to_the_death)
        m = fresh()
        m.locations["Left Leg"]["destroyed"] = m.locations["Right Leg"]["destroyed"] = True
        m.destroyed_slot_info = {i: {"name": w.name, "instance_id": id(w)}
                                 for i, w in enumerate(attack_resolution.get_weapons(m))}
        assert is_destroyed(m) and m.cause_of_death == "Immobile, No Ranged Weapons"
        m = fresh()                                      # one leg and both arms gone: can't stand (p.51)
        for loc in ("Left Leg", "Left Arm", "Right Arm"):
            m.locations[loc]["destroyed"] = True
        assert not piloting_rolls.can_stand(m)
    finally:
        config.FIGHT_TO_THE_DEATH = saved


@check
def turning_while_down():
    """2026-10-20: a prone mech that can't stand turns toward the enemy on
    the ground - one hexside per turn with a destroyed gyro (p.98)."""
    saved = config.FIGHT_TO_THE_DEATH
    try:
        config.FIGHT_TO_THE_DEATH = True
        m, enemy = fresh(hex_="0808", facing="N"), fresh(hex_="0811", facing="N")   # enemy straight behind
        m.prone, m.gyro_hits = True, 2
        orchestrator._turn_while_down(m, enemy)
        assert m.facing in ("NE", "NW") and m.mp_spent == 1 and m.move_mode == "Walk", (m.facing, m.mp_spent)
        m = fresh(hex_="0808", facing="N")             # enemy already in the forward arc: no turn
        m.prone, m.gyro_hits = True, 2
        m.move_mode, m.mp_spent = "Stand Still", 0
        orchestrator._turn_while_down(m, fresh(hex_="0805", facing="S"))
        assert m.facing == "N" and m.mp_spent == 0
    finally:
        config.FIGHT_TO_THE_DEATH = saved


@check
def autocannon_first_critical():
    """2026-10-20, Core p.183: an autocannon's first critical hit doesn't
    destroy it (the slot is used up); a second crit to another of its slots
    does. A one-slot autocannon takes two hits to that slot."""
    import damage_resolution as dr
    m = fresh()
    ac5 = next(w for w in attack_resolution.get_weapons(m) if w.name == "ISAC5")
    loc = next(l for l, slots in m.crits.items() if ac5 in slots)
    first, second = [i for i, s in enumerate(m.crits[loc]) if s is ac5][:2]
    dr.resolve_slot_hit(m, loc, first, ac5, 1, 1)
    assert ac5 in attack_resolution.get_weapons(m) and m.crits[loc][first] == "DESTROYED"
    dr.resolve_slot_hit(m, loc, second, ac5, 1, 1)
    assert ac5 not in attack_resolution.get_weapons(m)
    laser = next(w for w in attack_resolution.get_weapons(m) if "Laser" in w.name or "LRM" in w.name)
    loc = next(l for l, slots in m.crits.items() if laser in slots)
    i = m.crits[loc].index(laser)
    dr.resolve_slot_hit(m, loc, i, laser, 1, 1)                 # anything else: destroyed at once
    assert laser not in attack_resolution.get_weapons(m)


@check
def armored_components():
    """2026-10-21, Core p.207: MegaMek's "(armored)" tag is read (before, an
    armored engine / gyro was inert padding); each armored slot absorbs one
    critical hit from an attack with no effect; MASC / supercharger crits
    (resolve_slot_hit called directly) ignore it; an armored hip not yet hit
    stops a limb blown off; ammunition is never armored."""
    import tempfile
    import zipfile
    import damage_resolution as dr
    with zipfile.ZipFile(os.path.join(REPO_ROOT, "data", "meks.zip")) as z:
        path = z.extract("meks/XTRs/Phantoms/Grand Titan Vengeance T-IT-N14R.mtf", tempfile.mkdtemp())
    m = fresh(parse_mtf(path))
    ct = m.crits["Center Torso"]
    assert ct[:5] == ["Engine", "Engine", "Engine", "Gyro", "Gyro"] and m.crits["Head"][2] == "Cockpit"
    assert {("Center Torso", i) for i in range(8)} <= m.armored_slots and ("Head", 2) in m.armored_slots
    assert not any(getattr(s, "category", None) == "ammo" for loc, i in m.armored_slots for s in [m.crits[loc][i]])
    real = config.pick_number
    try:
        config.pick_number = lambda n, prompt="": 1                       # the first slot in the pool: Engine
        dr.resolve_critical(m, "Center Torso", explosive_only=False, idx=1, total=1)
        assert m.engine_hits == 0 and ct[0] == "Engine" and ("Center Torso", 0) not in m.armored_slots
        dr.resolve_critical(m, "Center Torso", explosive_only=False, idx=1, total=1)
        assert m.engine_hits == 1 and ct[0] == "DESTROYED"                 # its armor is spent
        dr.resolve_slot_hit(m, "Center Torso", 1, "Engine", 1, 1)          # a supercharger's crit: no armor
        assert m.engine_hits == 2
    finally:
        config.pick_number = real
    leg = fresh()
    hip = leg.crits["Left Leg"].index("Hip")
    leg.armored_slots = {("Left Leg", hip)}
    with ScriptedDice([12, 12]):
        dr.check_critical(leg, "Left Leg")
        assert not leg.locations["Left Leg"]["destroyed"] and not leg.armored_slots
        dr.check_critical(leg, "Left Leg")
        assert leg.locations["Left Leg"]["destroyed"]


@check
def explosions_and_case():
    """2026-10-20, Core p.96: no CASE - at most 20 structure damage, and when
    the base damage was over 20 the location that took the 20th point loses
    its (rear) armor; CASE - at most 10 structure, the excess (at most 10) to
    the (rear) armor, no transfer; CASE II - 1 structure, excess to armor."""
    import damage_resolution as dr
    from types import SimpleNamespace as Bin
    saved = dr.get_case_tier
    try:
        for tier, structure, rear_lost in ((None, 20, "all"), ("CASE", 10, 10), ("CASE II", 1, 10)):
            dr.get_case_tier = lambda mech, loc, tier=tier: tier
            m = fresh()
            m.locations["Center Torso"]["structure"] = 40       # big enough to survive
            m.max_structure["Center Torso"] = 40
            rear = m.locations["Center Torso"]["rear_armor"]
            front = m.locations["Center Torso"]["armor"]
            with ScriptedDice([], default=2):                  # crit checks: no critical
                dr.apply_explosion(m, Bin(name="Test Ammo", explosion_damage=60), "Center Torso")
            loc = m.locations["Center Torso"]
            assert loc["structure"] == 40 - structure, (tier, loc["structure"])
            assert loc["rear_armor"] == (0 if rear_lost == "all" else max(0, rear - rear_lost)), (tier, loc)
            assert loc["armor"] == front
    finally:
        dr.get_case_tier = saved


@check
def standard_through_armor_critical():
    """2026-10-20, Daniel's option. config.FLOATING_CRITICALS False (p.91): a
    hit-location 2 hits the center torso as rolled, plus one critical-hit
    check there. True (p.95, default): the location is re-rolled."""
    saved = config.FLOATING_CRITICALS
    try:
        config.FLOATING_CRITICALS = False
        m = fresh()
        ct = m.locations["Center Torso"]["armor"]
        with ScriptedDice([2, 7]):                        # location 2: CT; TAC check 7: no critical
            attack_resolution._resolve_hit(m, 5, attack_resolution.DamageType.ENERGY, "front")
        assert m.locations["Center Torso"]["armor"] == ct - 5
        config.FLOATING_CRITICALS = True
        m = fresh()
        ra = m.locations["Right Arm"]["armor"]
        with ScriptedDice([2, 3, 7]):                     # 2, re-roll 3: right arm; TAC check 7
            attack_resolution._resolve_hit(m, 5, attack_resolution.DamageType.ENERGY, "front")
        assert m.locations["Right Arm"]["armor"] == ra - 5
    finally:
        config.FLOATING_CRITICALS = saved


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
