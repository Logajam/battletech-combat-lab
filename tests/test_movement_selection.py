"""
tests/test_movement_selection.py - checks INTEGRATION__movement_selection
(Daniel, 2026-10-19: dealt / (received + PSR cost + 0.001), two-ply, exposure
weighting, ported closing fallback) and the geometry cache and evaluator it
sits on.

    python tests/test_movement_selection.py

Most checks compare the picker against a brute-force version that skips every
shortcut (the candidate reduction, the evaluator's reuse, the cache) - so a
mistake in a shortcut can't hide.
"""

import io
import math
import os
import random
import sys
import traceback
from contextlib import redirect_stdout

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
import INTEGRATION__attack_resolution as attack_resolution  # noqa: E402
import INTEGRATION__ranged_combat as ranged_combat  # noqa: E402
import INTEGRATION__movement_selection as ms  # noqa: E402
import INTEGRATION__los_cache as geo_cache  # noqa: E402
import INTEGRATION__arcs as arcs  # noqa: E402
from INTEGRATION__rng import BattleRNG  # noqa: E402
import hex_geometry  # noqa: E402
import combat  # noqa: E402
import los  # noqa: E402
import piloting_rolls  # noqa: E402
from mtf_parser import parse_mtf  # noqa: E402
from mech_state import clone_mech  # noqa: E402

config.VERBOSE = False
config.TIMING = False      # same-seed checks compare printed output; run times differ
TERRAIN = orchestrator._load_map()
ASYMPTOTE = parse_mtf(config.data_path("Asymptote II iJ Mpulse.mtf"))
TOL = 1e-9


def fresh(hex_, facing="N", template=ASYMPTOTE, name="Test", max_heat=4):
    m = clone_mech(template)
    orchestrator._attach_mech_config(m, {"hex": hex_, "facing": facing, "gunnery": 4, "piloting": 5,
                                         "min_heat": 0, "max_heat": max_heat}, name)
    return m


def xy(label):
    return hex_geometry.parse_hex_label(label)


CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


def objective_of(cand, me, them):
    """The picker's objective for one MovementCandidate (mover = me) - whichever
    config.MOVEMENT_OBJECTIVE is set (full_scores links the sides)."""
    return me.objective(cand.dealt, cand.received, them.exposure[cand.side_on_defender],
                        me.exposure[cand.side_on_mover], me.psr_cost(cand.mode, cand.fc))


def full_scores(mover, other, standup_mp=None):
    """Every UNREDUCED state of `mover` scored against `other` where it stands."""
    me, them = ms._Side(mover), ms._Side(other)
    ms._link(me, them)
    cands = ranged_combat.evaluate_going_second(
        mover, other, TERRAIN, defender_state={"fc": other.move_fc, "mode": other.move_mode}, standup_mp=standup_mp)
    return me, them, cands


# -----------------------------------------------------------------------------
@check
def geometry_cache_matches_the_game_code():
    """los_cache must give exactly what los.has_los, attack_resolution.attack_side
    and arcs.arcs_between give - it only remembers their answers."""
    geo_cache.reset()
    rng = random.Random(7)
    labels = rng.sample(sorted(TERRAIN["hexes"]), 40)
    n = 0
    for a in labels:
        for t in labels:
            if a == t:
                continue
            ah, th = xy(a), xy(t)
            try:
                want = los.has_los(ah, th, TERRAIN)
            except ValueError:
                try:
                    geo_cache.pair_info(ah, th, TERRAIN)
                    raise AssertionError("cache accepted a line los.py rejects")
                except ValueError:
                    continue
            res, entry_dir, dist, a_to_t = geo_cache.pair_info(ah, th, TERRAIN)
            assert (res.los, res.modifier, res.distance) == (want.los, want.modifier, want.distance), (a, t)
            assert dist == los.hex_distance(ah, th)
            assert a_to_t == arcs.arcs_between(ah, th), (a, t)
            for f in range(6):
                if want.los:
                    relative = (entry_dir - f) % 6
                    assert attack_resolution._SIDE_BY_RELATIVE_HEXSIDE[relative] == \
                        attack_resolution.attack_side(ah, th, f, TERRAIN), (a, t, f)
            again = geo_cache.pair_info(ah, th, TERRAIN)
            assert again is geo_cache.pair_info(ah, th, TERRAIN)         # remembered, not recomputed
            n += 1
    assert n > 1000, n


@check
def firing_arcs_match_the_diagram():
    """Every hex labelled on the Core p.60 Firing Arcs Diagram (mech on 0704
    facing north), including the hexes sitting exactly on a boundary line, and
    mirror symmetry / rotation for the other facings."""
    centre = xy("0704")
    diagram = {"0702": arcs.FORWARD, "0602": arcs.FORWARD, "0802": arcs.FORWARD, "0503": arcs.FORWARD,
               "0903": arcs.FORWARD, "0504": arcs.LEFT, "0604": arcs.LEFT, "0505": arcs.LEFT,
               "0904": arcs.RIGHT, "0804": arcs.RIGHT, "0905": arcs.RIGHT,
               "0705": arcs.REAR, "0605": arcs.REAR, "0805": arcs.REAR, "0706": arcs.REAR}
    for label, arc in diagram.items():
        assert arcs.arcs_between(centre, xy(label))[0] == arc, (label, arcs.ARC_NAMES[arc])
    # turning the mech one facing clockwise turns each arc with it
    for label in TERRAIN["hexes"]:
        t = xy(label)
        if t == centre:
            continue
        a = arcs.arcs_between(centre, t)
        swap = {arcs.LEFT: arcs.RIGHT, arcs.RIGHT: arcs.LEFT}
        mirrored = arcs.arcs_between(centre, (2 * centre[0] - t[0], t[1]))      # mirror across the column
        assert [swap.get(v, v) for v in a] == [mirrored[(-f) % 6] for f in range(6)], label
        counts = {k: sum(1 for v in a if v == k) for k in (arcs.FORWARD, arcs.LEFT, arcs.RIGHT, arcs.REAR)}
        assert counts[arcs.FORWARD] in (2, 3) and sum(counts.values()) == 6, (label, a)


@check
def weapons_bear_by_arc_and_twist():
    """p.60-62 on the Synthetic mech (rear laser CT, LRM15 LT, SRM6 RT, LB-X10 +
    UAC5 left arm, AC5 right arm): left-arm guns reach the left side arc, a
    twist left brings a left-side target into the torso's forward arc (all
    non-rear weapons bear), leg weapons never follow a twist, prone / quad can't twist."""
    synthetic = parse_mtf(config.data_path("TEST_Synthetic_Loadout.mtf"))
    m = fresh("0808", "N", template=synthetic)
    name = lambda ids: {w.name for w in ms.get_weapons(m) if id(w) in ids}              # noqa: E731
    assert name(attack_resolution.arc_unavailable(m, arcs.simple_key(m, arcs.LEFT))) == {"ISMediumPulseLaser", "ISLRM15", "ISSRM6", "ISAC5"}
    here = xy("0808")
    behind = next(xy(l) for l in sorted(TERRAIN["hexes"]) if arcs.arcs_between(here, xy(l))[0] == arcs.REAR)
    pair = arcs.arcs_between(here, behind)
    keys = [k for k, _ in arcs.arc_keys(pair, 0, arcs.arc_options(m), arcs.leg_offsets(m))]
    assert any(k.torso_arc == arcs.REAR and not k.legs_forward for k in keys) and len(keys) >= 2  # torso turns, legs don't
    side_target = next(xy(l) for l in sorted(TERRAIN["hexes"])                         # a left-side-arc hex a left twist makes forward
                       if arcs.arcs_between(here, xy(l))[0] == arcs.LEFT and arcs.arcs_between(here, xy(l))[5] == arcs.FORWARD)
    pair = arcs.arcs_between(here, side_target)
    assert any(k.torso_arc == arcs.FORWARD and not k.legs_forward
               for k, _ in arcs.arc_keys(pair, 0, arcs.arc_options(m), arcs.leg_offsets(m)))
    assert arcs.twist_options(m) == (0, -1, 1)
    m.prone = True
    assert arcs.twist_options(m) == (0,)
    m.prone = False
    quad = fresh("0808", "N")
    quad.mech_type = "quad"
    assert arcs.twist_options(quad) == (0,)


@check
def twisting_never_lowers_expected_damage_and_helps_somewhere():
    """The evaluator lets each side take its best twist, so with twisting
    allowed, dealt is never below the no-twist value, and is higher for a spot
    that has the enemy in a side arc of the mover's arm weapons' blind side."""
    synthetic = parse_mtf(config.data_path("TEST_Synthetic_Loadout.mtf"))
    mover, other = fresh("0808", "N", template=synthetic), fresh("0611", "N")
    with_twist = {(c.hex, c.facing, c.mode, c.fc): c.dealt
                  for c in ranged_combat.evaluate_going_second(mover, other, TERRAIN)}
    real = arcs.arc_options
    arcs.arc_options = lambda mech, phase="ranged": (arcs.NO_ACTION,)
    try:
        ev = ranged_combat.MoveEvaluator(mover, other, TERRAIN)
        no_twist = {(c.hex, c.facing, c.mode, c.fc): c.dealt
                    for c in ev.evaluate(other.hex, other.facing, 0, "Stand Still", 0,
                                         ev.prepare(ranged_combat.movement_options(mover, TERRAIN)))}
    finally:
        arcs.arc_options = real
    assert no_twist.keys() == with_twist.keys()
    assert all(with_twist[k] >= no_twist[k] - TOL for k in no_twist)
    assert any(with_twist[k] > no_twist[k] + 1e-6 for k in no_twist), "twisting never helped anywhere"


@check
def adjacent_spots_count_physical_attacks():
    """Spots next to the enemy add the expected punch / kick damage (pp.76-83)
    both ways; every other spot is unchanged, and none scores lower."""
    import INTEGRATION__physical as physical
    mover, other = fresh("0808", "N", template=parse_mtf(config.data_path("TEST_Synthetic_Loadout.mtf"))), \
        fresh("0611", "N")

    def scores():
        ev = ranged_combat.MoveEvaluator(mover, other, TERRAIN)
        return {(c.hex, c.facing, c.mode, c.fc): (c.distance, c.dealt, c.received)
                for c in ev.evaluate(other.hex, other.facing, 0, "Stand Still", 0,
                                     ev.prepare(ranged_combat.movement_options(mover, TERRAIN)))}
    with_physical = scores()
    real = physical.Planner.plans_in_case
    physical.Planner.plans_in_case = lambda self, *a, **k: []
    try:
        without = scores()
    finally:
        physical.Planner.plans_in_case = real
    assert with_physical.keys() == without.keys()
    for k, (dist, dealt, received) in with_physical.items():
        d0, r0 = without[k][1], without[k][2]
        if dist != 1:
            assert (dealt, received) == (d0, r0), k
        assert dealt >= d0 - TOL and received >= r0 - TOL, k
    assert any(v[1] > without[k][1] + 1e-6 for k, v in with_physical.items() if v[0] == 1)
    assert any(v[2] > without[k][2] + 1e-6 for k, v in with_physical.items() if v[0] == 1)


@check
def ranged_fire_holds_an_arm_for_a_better_punch():
    """Next to the target, the Ranged phase scores fire + the physical attack
    that can follow (pp.76, 82). With kicks ruled out (a hip hit), the
    synthetic mech's right-arm AC5 inside its minimum range (TN 7 for 5,
    2.9 expected) is worth less than that arm's punch (TN 4 for 5, 4.6), so
    it holds the AC5 and punches with both arms; with a hopeless pilot (TN 11
    punches) the AC5 fires instead. A free kick (no leg weapons) is planned
    without holding anything back."""
    import INTEGRATION__physical as physical
    from INTEGRATION__attack_resolution import SideReport
    from test_heat import ScriptedDice
    synthetic = parse_mtf(config.data_path("TEST_Synthetic_Loadout.mtf"))
    for piloting, hip_hit, holds in ((5, True, True), (12, True, False), (5, False, False)):
        m, t = fresh("0808", "N", template=synthetic, max_heat=30), fresh("0807", "S")
        m.piloting = piloting
        if hip_hit:
            m.destroyed_hip_locations.add("Left Leg")
        rep = SideReport()
        with ScriptedDice([], default=12):
            attack_resolution.declare_attacks(m, t, TERRAIN, rep)
        fired = {x.weapon.name for x in rep.attacks_list}
        assert {"ISLRM15", "ISSRM6"} <= fired
        assert ("ISAC5" not in fired) == holds, (piloting, hip_hit, fired)
        if holds:
            m.weapons_fired_this_turn = frozenset(id(x.weapon) for x in rep.attacks_list)
            assert len(physical.choose_attack(m, t, TERRAIN)[1]) == 2                 # both arms punch


@check
def hit_tables_steer_punch_or_kick():
    """A 50-ton mech's two punches and its kick have the same raw expected
    damage (2 x 5 vs 10 at TN 4); the hit tables break the tie (p.81): a
    target with stripped legs gets kicked, one with a stripped upper body
    gets punched. The punch table's 1-in-6 head chance counts too."""
    import INTEGRATION__physical as physical
    synthetic = parse_mtf(config.data_path("TEST_Synthetic_Loadout.mtf"))
    kinds = []
    for stripped in (("Left Leg", "Right Leg"), ("Left Arm", "Right Arm", "Left Torso", "Right Torso", "Center Torso")):
        m, t = fresh("0808", "N", template=synthetic), fresh("0807", "S", template=synthetic)
        for loc in stripped:
            t.locations[loc]["armor"] = 0
        base, picks, _ = physical.choose_attack(m, t, TERRAIN)
        kinds.append("kick" if picks[0].get("kick") else "punch")
        w = physical.Worth(t)
        assert (w.factor("kick", "front", 10) > w.factor("punch", "front", 5)) == (kinds[-1] == "kick")
    assert kinds == ["kick", "punch"]
    fresh_target = fresh("0807", "S", template=synthetic)
    w = physical.Worth(fresh_target)
    assert w.factor("punch", "front", 5) > w.factor("standard", "front", 5)       # the head is on the punch table


@check
def candidate_sides_match_attack_side():
    """The side the evaluator reports for each candidate is attack_side's answer
    for the actual attacker / target / target facing."""
    mover, other = fresh("0808", "N"), fresh("0812", "NE")
    cands = ranged_combat.evaluate_going_second(mover, other, TERRAIN)
    assert len(cands) > 100
    for c in random.Random(3).sample(cands, 60):
        a = xy(c.hex)
        assert c.side_on_defender == attack_resolution.attack_side(
            a, xy("0812"), hex_geometry.compass_to_facing("NE"), TERRAIN), c
        assert c.side_on_mover == attack_resolution.attack_side(
            xy("0812"), a, hex_geometry.compass_to_facing(c.facing), TERRAIN), c


@check
def reduction_keeps_the_best_spot():
    """The Section 5c reduction drops only dominated states: the best objective
    over the reduced set equals the best over every state."""
    for mover_hex, mover_f, other_hex, other_f, damage in [
        ("0808", "N", "0812", "S", False), ("0505", "SE", "0709", "N", False),
        ("1010", "NW", "0706", "SW", False), ("0808", "N", "0812", "S", True),
    ]:
        mover, other = fresh(mover_hex, mover_f), fresh(other_hex, other_f)
        if damage:
            mover.gyro_hits = 1
            mover.locations["Center Torso"]["rear_armor"] = 2
            mover.locations["Left Torso"]["armor"] = 3
            piloting_rolls.snapshot_preexisting_damage(mover)
        me, them, full = full_scores(mover, other)
        assert full
        best_full = max(objective_of(c, me, them) for c in full)
        reduced = ms.reduced_options(mover, TERRAIN, exclude_hex=other.hex)
        ev = ranged_combat.MoveEvaluator(mover, other, TERRAIN)
        red = ev.evaluate(other.hex, other.facing, 0, "Stand Still", 0, ev.prepare(reduced))
        best_red = max(objective_of(c, me, them) for c in red)
        assert abs(best_full - best_red) < TOL, (mover_hex, best_full, best_red)
        assert len(reduced) < len(list(ranged_combat.movement_options(mover, TERRAIN)))


@check
def structure_damage_counts_for_more():
    """worth(): armor 1.0, structure k, transfer overflow 1.0. A hand case: a
    10-point hit on a location with 4 armor and 3 structure left is
    4 + 2*3 + 3 = 13 at k = 2. A weapon's multiplier is the hit-table average of
    that, over its damage; full armor everywhere is exactly 1.0; stripping a
    side raises it; k = 1 is exactly 1.0 and leaves dealt/received unchanged."""
    sw = ms.structure_weight
    assert sw.worth(10, 4, 3, 2.0) == 13 and sw.worth(3, 4, 3, 2.0) == 3 and sw.worth(5, 0, 9, 2.0) == 10
    assert sw.worth(10, 4, 3, 1.0) == 10
    other, target = fresh("0812", "S"), fresh("0808", "N")
    weapons = ms.get_weapons(other)
    full = sw.multipliers(weapons, target, "left")
    assert all(abs(v - 1.0) < TOL for v in full.values()), full
    for loc in ("Left Arm", "Left Torso", "Left Leg", "Center Torso", "Right Arm"):
        target.locations[loc]["armor"] = 0
    stripped = sw.multipliers(weapons, target, "left")
    assert all(v >= 1.0 for v in stripped.values()) and max(stripped.values()) > 1.0, stripped
    # recompute one weapon by hand from the hit table
    w = weapons[0]
    groups = sw.weapon_groups(w)
    want = sum(p * sw.worth(d, st[ak], st["structure"], config.MOVEMENT_STRUCTURE_WEIGHT)
               for d in groups for p, st, ak in sw.hit_spread(target, "left")) / sum(groups)
    want += 1.0 - sum(p for p, _, _ in sw.hit_spread(target, "left"))
    assert abs(stripped[id(w)] - want) < TOL, (stripped[id(w)], want)

    # the evaluator: stripped target -> dealt rises vs k = 1; k = 1 equals the unweighted numbers
    mover = fresh("0808", "N")
    def dealt_at(k):
        old = config.MOVEMENT_STRUCTURE_WEIGHT
        config.MOVEMENT_STRUCTURE_WEIGHT = k
        try:
            return {(c.hex, c.facing, c.mode, c.fc): c.dealt
                    for c in ranged_combat.evaluate_going_second(mover, target_enemy, TERRAIN)}
        finally:
            config.MOVEMENT_STRUCTURE_WEIGHT = old
    target_enemy = fresh("0811", "S")
    for loc in ("Left Arm", "Left Torso", "Left Leg", "Center Torso", "Right Arm", "Right Torso", "Right Leg"):
        target_enemy.locations[loc]["armor"] = 0
    d1, d2 = dealt_at(1.0), dealt_at(2.0)
    assert d1.keys() == d2.keys() and all(d2[k] >= d1[k] - TOL for k in d1)
    assert any(d2[k] > d1[k] + 1e-6 for k in d1), "structure weighting changed nothing against a stripped target"


@check
def void_signature_mech_keeps_every_movement_variant():
    """A live Void-Signature System's bonus falls as hexes moved rise, so the
    reduction (which keeps the most hexes) is skipped for it: it keeps several
    forward counts per (hex, facing, mode), and the best reduced objective
    still equals the best over the full list."""
    from INTEGRATION__equipment_systems import active_stealth
    from equipment import Equipment
    heat_gear = parse_mtf(config.data_path("TEST_Heat_Gear.mtf"))
    mover = fresh("0808", "N", template=heat_gear)
    other = fresh("0812", "S")
    mover.equipment_systems["void_signature"] = [Equipment("Void Signature System", category="misc")]
    assert "void_signature" in active_stealth(mover)
    reduced = ms.reduced_options(mover, TERRAIN, exclude_hex=other.hex)
    per_spot = {}
    for x, y, facing, fc, mode, mp in reduced:
        per_spot.setdefault((x, y, facing, mode), set()).add(fc)
    assert any(len(v) > 1 for v in per_spot.values()), "reduction was applied to a Void-Signature mech"
    plain = fresh("0808", "N", template=heat_gear)
    assert len(ms.reduced_options(plain, TERRAIN, exclude_hex=other.hex)) < len(reduced)
    me, them, full = full_scores(mover, other)
    best_full = max(objective_of(c, me, them) for c in full)
    ev = ranged_combat.MoveEvaluator(mover, other, TERRAIN)
    red = ev.evaluate(other.hex, other.facing, 0, "Stand Still", 0, ev.prepare(reduced))
    assert abs(best_full - max(objective_of(c, me, them) for c in red)) < TOL


@check
def second_mover_takes_the_best_scoring_spot():
    """With the enemy's position final (second mover), choose() returns a spot
    scoring the maximum objective over the full unreduced list."""
    rng = BattleRNG(seed=11)
    for mover_hex, other_hex, other_f in [("0808", "0813", "N"), ("0404", "0808", "SW"), ("1212", "0910", "SE")]:
        mover, other = fresh(mover_hex, "N"), fresh(other_hex, other_f)
        pick, why = ms.choose(mover, other, TERRAIN, rng, moves_first=False)
        me, them, full = full_scores(mover, other)
        best = max(objective_of(c, me, them) for c in full)
        if not any(c.dealt > 0 for c in full):
            continue                                   # nothing deals damage: the closing fallback picks
        match = [c for c in full if (c.hex, c.facing, c.mode, c.fc) == (pick["hex"], pick["facing"], pick["mode"], pick["fc"])]
        assert match, (pick, why)
        assert abs(objective_of(match[0], me, them) - best) < TOL, (pick, why, best)


@check
def first_mover_scores_a_spot_by_the_real_replys_numbers():
    """For sampled first-mover spots, the modeled reply's objective equals what
    a brute force finds: put the first mover physically at the spot, score the
    second mover's UNREDUCED envelope with a fresh evaluate_going_second, take
    the best. (Proves pinning, evaluator reuse, the cache and the reduction.)"""
    mover, other = fresh("0808", "N"), fresh("0911", "NW")
    me, them = ms._Side(mover), ms._Side(other)
    spots = ms.reduced_options(mover, TERRAIN, exclude_hex=other.hex)
    ev1 = ranged_combat.MoveEvaluator(mover, other, TERRAIN)
    prepared1 = ev1.prepare(spots)
    ev2 = ranged_combat.MoveEvaluator(other, mover, TERRAIN)
    prepared2 = ev2.prepare(ms._opponent_options(other, TERRAIN))
    compared = 0
    for c in random.Random(5).sample(prepared1, 25):
        reply = ms._modeled_reply(c, ev2, prepared2, them, me, other, c.hex_xy, TERRAIN)

        # brute force: really move the first mover there
        pinned = clone_mech(mover)
        pinned.hex, pinned.facing = c.label, c.facing_compass
        pinned.move_mode, pinned.move_fc, pinned.mp_spent = c.mode, c.fc, c.mp_spent
        brute = ranged_combat.evaluate_going_second(
            other, pinned, TERRAIN, defender_state={"fc": c.fc, "mode": c.mode})
        scored = [ms._objective(b.dealt, b.received, me.exposure[b.side_on_defender],
                                them.exposure[b.side_on_mover], them.psr_cost(b.mode, b.fc)) for b in brute]
        if not brute or not any(b.dealt > 0 for b in brute):
            continue                       # closing-fallback case: covered by its own check
        assert reply is not None
        got = ms._objective(reply.dealt, reply.received, me.exposure[reply.side_on_defender],
                            them.exposure[reply.side_on_mover], them.psr_cost(reply.mode, reply.fc))
        assert abs(got - max(scored)) < TOL, (c.label, got, max(scored))
        compared += 1
    assert compared >= 5, compared


@check
def two_ply_changes_the_pick_it_should():
    """A spot only the first mover can see the enemy from (the enemy will have
    moved away) must not be scored as if the enemy stayed: two-ply and static
    picks differ somewhere across a few positions, and the static score of the
    two-ply pick is never better than the static pick's own."""
    differ = 0
    for mover_hex, other_hex in [("0808", "0813"), ("0505", "0911"), ("0310", "0910"), ("0606", "0609")]:
        picks = {}
        for two_ply in (True, False):
            config.MOVEMENT_TWO_PLY = two_ply
            mover, other = fresh(mover_hex, "N"), fresh(other_hex, "N")
            picks[two_ply], _ = ms.choose(mover, other, TERRAIN, BattleRNG(seed=2), moves_first=True)
        config.MOVEMENT_TWO_PLY = True
        if picks[True] != picks[False]:
            differ += 1
    assert differ >= 1, "two-ply never changed a pick - is the lookahead doing anything?"


@check
def psr_cost_prices_the_fall():
    """Only a damaged mech has a Movement Phase PSR; its cost is P(fail) x fall
    damage, from piloting_rolls' own target number."""
    m = fresh("0808")
    assert ms.psr_costs(m) == {"Run": 0.0, "Jump": 0.0}
    m.gyro_hits = 1
    piloting_rolls.snapshot_preexisting_damage(m)
    target = m.piloting + piloting_rolls.preexisting_modifier(m) + piloting_rolls.special_case_modifier(m)
    assert target == piloting_rolls.movement_psr_target_number(m, 'Run'), target        # skill + gyro hit + this mech's own special-case modifier
    assert target == m.piloting + piloting_rolls.PREEXISTING_GYRO_HIT_MODIFIER + piloting_rolls.special_case_modifier(m)
    p_pass = sum(n for roll, n in ((2, 1), (3, 2), (4, 3), (5, 4), (6, 5), (7, 6), (8, 5), (9, 4), (10, 3), (11, 2), (12, 1))
                 if roll >= target) / 36
    expected = (1 - p_pass) * math.ceil(m.mass / 10)
    costs = ms.psr_costs(m)
    assert abs(costs["Run"] - expected) < TOL and abs(costs["Jump"] - expected) < TOL, (costs, expected)
    side = ms._Side(m)
    assert side.psr_cost("Walk", 3) == 0 and side.psr_cost("Stand Still", 0) == 0     # walking never rolls (p.111)
    assert side.psr_cost("Run", 0) == 0 and side.psr_cost("Run", 2) == costs["Run"]    # Run needs 1+ hex moved
    assert ms._Side(m, psr_applies=False).psr_cost("Run", 4) == 0                      # a stand-up already rolled it

    # trigger rules differ by mode: a destroyed leg actuator matters only when jumping
    m2 = fresh("0808")
    m2.destroyed_leg_actuators["Left Leg"] = 1
    piloting_rolls.snapshot_preexisting_damage(m2)
    c2 = ms.psr_costs(m2)
    assert c2["Run"] == 0 and c2["Jump"] > 0, c2

    config.MOVEMENT_PSR_COST = False
    try:
        assert ms.psr_costs(m) == {"Run": 0.0, "Jump": 0.0}
    finally:
        config.MOVEMENT_PSR_COST = True


@check
def a_damaged_mech_scores_running_below_walking():
    """With a gyro hit, the same spot scores lower for Run than the objective
    would without the PSR term - the term reaches the score."""
    m = fresh("0808")
    m.gyro_hits = 1
    piloting_rolls.snapshot_preexisting_damage(m)
    side = ms._Side(m)
    base = ms._objective(10.0, 4.0, 1.0, 1.0, 0.0)
    assert ms._objective(10.0, 4.0, 1.0, 1.0, side.psr_cost("Run", 3)) < base
    assert ms._objective(10.0, 4.0, 1.0, 1.0, side.psr_cost("Walk", 3)) == base


@check
def exposure_follows_current_armor():
    """Front counts 1.0; thin rear armor makes rear hits count more; stripping
    a side's armor raises that side; the knob turns it all off; destroyed
    locations transfer inward instead of failing."""
    m = fresh("0808")
    f = ms.exposure_factors(m)
    assert f["front"] == 1.0 and all(config.MOVEMENT_EXPOSURE_MIN <= f[s] <= config.MOVEMENT_EXPOSURE_MAX for s in f)
    assert abs(sum(ms._P_2D6.values()) - 1.0) < TOL
    for loc in ("Center Torso", "Left Torso", "Right Torso"):
        m.locations[loc]["rear_armor"] = 1
    f2 = ms.exposure_factors(m)
    assert f2["rear"] > f["rear"], (f, f2)

    m3 = fresh("0808")
    before = ms.exposure_factors(m3)
    for loc in ("Left Arm", "Left Torso", "Left Leg"):
        m3.locations[loc]["armor"] = 1
    after = ms.exposure_factors(m3)
    assert after["left"] > before["left"], (before, after)

    m4 = fresh("0808")
    m4.locations["Left Arm"]["destroyed"] = True               # a hit there transfers to the Left Torso
    assert all(math.isfinite(v) for v in ms.exposure_factors(m4).values())

    config.MOVEMENT_EXPOSURE_WEIGHTING = False
    try:
        assert ms.exposure_factors(m) == dict.fromkeys(ms.SIDES, 1.0)
    finally:
        config.MOVEMENT_EXPOSURE_WEIGHTING = True


@check
def a_stripped_side_is_turned_away():
    """Behavior check: given a mech with its left side nearly gone, among spots
    otherwise identical in range, the picker's received-damage weight is higher
    when the enemy's shot arrives on the left than when it arrives on the front."""
    m = fresh("0808")
    for loc in ("Left Arm", "Left Torso", "Left Leg"):
        m.locations[loc]["armor"] = 0
        m.locations[loc]["structure"] = 2
    f = ms.exposure_factors(m)
    assert f["left"] > f["front"] and f["left"] > f["right"], f


@check
def closing_fallback_cases():
    """Case A/B1 picks the spot that closes the range most (all ties at zero
    damage); finds nothing when no spot can close it; Case B2 heads for the
    nearest LOS hex that isn't closer in bracket."""
    # --- B1: mover out of range, enemy 12 hexes off: spots within range 9 exist
    mover, other = fresh("0801"), fresh("0817")                  # 16 apart: out of the 15-hex long range
    prepared = ranged_combat.prepare_options(mover, ms.reduced_options(mover, TERRAIN, exclude_hex=other.hex))
    weapon = ms._longest_range_weapon(mover)
    enemy = xy(other.hex)
    pick = ms.closing_fallback(mover, other, prepared, enemy, lambda o: 0.0, TERRAIN)
    assert pick is not None
    brackets = [ms._bracket(los.hex_distance(o.hex_xy, enemy), weapon) for o in prepared]
    assert ms._bracket(los.hex_distance(pick.hex_xy, enemy), weapon) == min(brackets) < 3

    # --- B1 edge: nothing reachable -> no override
    assert ms.closing_fallback(mover, other, [], enemy, lambda o: 0.0, TERRAIN) is None

    # --- B2: already in range (distance 5), so LOS is the problem. Only hexes at
    # distance >= 5 east of the enemy "have LOS" (patched); the mover should head
    # for the nearest such hex.
    mover, other = fresh("0808"), fresh("0813")
    enemy = xy(other.hex)
    prepared = ranged_combat.prepare_options(mover, ms.reduced_options(mover, TERRAIN, exclude_hex=other.hex))
    real_los = geo_cache.los

    class FakeLos:
        def __init__(self, ok):
            self.los = ok

    def fake_los(cell, target, terrain):
        return FakeLos(cell[0] > enemy[0] and los.hex_distance(cell, enemy) >= 5)

    geo_cache.los = fake_los
    try:
        pick = ms.closing_fallback(mover, other, prepared, enemy, lambda o: 0.0, TERRAIN)
    finally:
        geo_cache.los = real_los
    assert pick is not None
    mover_xy = xy(mover.hex)
    seeds = [xy(label) for label in TERRAIN["hexes"]
             if xy(label) != mover_xy and xy(label)[0] > enemy[0] and los.hex_distance(xy(label), enemy) >= 5]
    nearest_seed = min(seeds, key=lambda c: los.hex_distance(c, mover_xy))
    d_seed = lambda o: los.hex_distance(o.hex_xy, nearest_seed)                       # noqa: E731
    in_bracket = [o for o in prepared if ms._bracket(los.hex_distance(o.hex_xy, enemy), ms._longest_range_weapon(mover))
                  >= ms._bracket(los.hex_distance(mover_xy, enemy), ms._longest_range_weapon(mover))]
    assert d_seed(pick) == min(d_seed(o) for o in in_bracket)


@check
def modeled_replies_follow_the_real_movement_rules():
    """The modeled second mover mirrors _phase_movement: immobile and prone mechs
    don't move."""
    other = fresh("0808", "SE")
    other.shutdown = True
    (state,) = ms._opponent_options(other, TERRAIN)
    assert state[:2] == xy("0808") and state[4] == "Stand Still" and state[3] == 0
    other = fresh("0808", "SE")
    other.prone = True
    (state,) = ms._opponent_options(other, TERRAIN)
    assert state[4] == "Run"                                   # declares Run to try standing (resolve_stand_up)
    assert len(ms._opponent_options(fresh("0808"), TERRAIN)) > 50


@check
def entering_the_board():
    """With no enemy on the board the mover heads for its home edge; entering
    from an edge works and lands on a reachable hex."""
    mover, other = fresh("0101"), fresh("0101")
    mover.hex, other.hex = None, None
    mover.home_edge = orchestrator._edge_hexes(TERRAIN, "N")
    other.home_edge = orchestrator._edge_hexes(TERRAIN, "S")
    pick, why = ms.choose(mover, other, TERRAIN, BattleRNG(seed=4), moves_first=True, entry_edge=mover.home_edge)
    assert pick is not None and "home edge" in why, (pick, why)
    row = int(pick["hex"][2:])
    assert row <= 1 + combat_run_hexes(mover), (pick, row)
    # second mover entering with the first already on the board: plain single-ply
    first = fresh("0808")
    mover2 = fresh("0101")
    mover2.hex = None
    mover2.home_edge = orchestrator._edge_hexes(TERRAIN, "S")
    pick2, _ = ms.choose(mover2, first, TERRAIN, BattleRNG(seed=4), moves_first=False, entry_edge=mover2.home_edge)
    assert pick2 is not None


def combat_run_hexes(mech):
    from mech_state import compute_running_mp
    return compute_running_mp(mech)


@check
def same_seed_same_battle():
    """A short quiet battle twice with one seed: identical results (the lookahead
    must not consume the battle's random stream differently from run to run)."""
    out = []
    for _ in range(2):
        config.VERBOSE = False
        buf = io.StringIO()
        with redirect_stdout(buf):
            results = orchestrator.run_batch(num_simulations=1, seed=99, max_turns=4)
        r = results[0]
        out.append((r.turns_taken, r.red.final_hp, r.blue.final_hp, r.red.final_hex, r.blue.final_hex, buf.getvalue()))
    assert out[0] == out[1]


@check
def lifetime_objective_math():
    """config.MOVEMENT_OBJECTIVE = "lifetime" (2026-10-20): dealt + (HP left /
    enemy future) x my future. HP 100, my future 10, the enemy's 20."""
    obj = object.__new__(ms._Lifetime)
    obj.hp, obj.mine, obj.theirs = 100.0, 10.0, 20.0
    hide = obj(0, 0, 1, 1, 0)
    assert abs(hide - 50.0) < TOL                         # 100 / 20 x 10
    assert obj(30, 120, 1, 1, 0) == 30                    # destroyed here: only what it deals now
    # A fight beats deal-nothing-take-nothing when its trade beats mine / theirs = 0.5.
    assert obj(6, 10, 1, 1, 0) > hide > obj(4, 10, 1, 1, 0)
    # What it takes still counts when it deals nothing (the ratio scored both 0).
    assert obj(0, 1, 1, 1, 0) > obj(0, 20, 1, 1, 0)
    # Exposure and the PSR cost come off the HP like damage received.
    assert abs(obj(0, 10, 1, 2, 5) - obj(0, 25, 1, 1, 0)) < TOL


@check
def history_blend_math():
    """MOVEMENT_LIFETIME_HISTORY_K (2026-10-21): rates = (K x estimate + damage
    really done) / (K + turns fought); turns fought start at the first turn
    either mech lost HP."""
    class M:
        pass
    me, them = M(), M()
    me.hp_log = [300, 300, 300, 290, 280]          # deployment, end of turns 1-4
    them.hp_log = [250, 250, 250, 220, 190]        # first loss: turn 3
    assert ms.battle_record(me, them) == (60, 20, 2)
    mine, theirs = ms._blend_with_history(3.0, 10.0, 8.0, me, them)
    assert abs(mine - (3 * 10 + 60) / 5) < TOL     # 18: doing well - its future rises
    assert abs(theirs - (3 * 8 + 20) / 5) < TOL    # 8.8
    # Before anyone is hit (or without a record) it is all estimate.
    me.hp_log, them.hp_log = [300, 300], [250, 250]
    assert ms._blend_with_history(3.0, 10.0, 8.0, me, them) == (10.0, 8.0)
    assert ms.battle_record(M(), them) == (0.0, 0.0, 0)


@check
def future_damage_follows_evasion():
    """INTEGRATION__future_damage: the target's best TMM sets the to-hit, so
    the same gunfire is worth less against a faster mech; the estimate never
    touches either mech."""
    import INTEGRATION__future_damage as fd
    kontio = fresh("0505", template=parse_mtf(config.data_path("Kontio.mtf")), max_heat=30)
    hammer = fresh("0508", template=parse_mtf(config.data_path("Hammerhead.mtf")), max_heat=30)
    assert fd.best_tmm(kontio) == 4 and fd.best_tmm(hammer) == 3      # Run 11 -> +4, Run 8 (hardened) -> +3
    fast = fd.future_damage(hammer, kontio)
    kontio.base_walk_mp = 2                                           # Walk 2 / Run 3: TMM +1
    before = (kontio.movement_mode_this_turn if hasattr(kontio, "movement_mode_this_turn") else None, kontio.hex)
    slow = fd.future_damage(hammer, kontio)
    assert fd.best_tmm(kontio) == 1 and slow > fast > 0
    after = (kontio.movement_mode_this_turn if hasattr(kontio, "movement_mode_this_turn") else None, kontio.hex)
    assert before == after


@check
def lifetime_option_runs_and_is_deterministic():
    """A short battle under the lifetime objective twice: identical results."""
    saved = config.MOVEMENT_OBJECTIVE
    config.MOVEMENT_OBJECTIVE = "lifetime"
    try:
        out = []
        for _ in range(2):
            buf = io.StringIO()
            with redirect_stdout(buf):
                r = orchestrator.run_batch(num_simulations=1, seed=7, max_turns=2)[0]
            out.append((r.turns_taken, r.red.final_hp, r.blue.final_hp, buf.getvalue()))
        assert out[0] == out[1]
    finally:
        config.MOVEMENT_OBJECTIVE = saved


@check
def grid_search_net_and_follow():
    """config.MOVEMENT_TWO_PLY_SEARCH = "grid" (Daniel's guess and follow,
    2026-10-21): the 1-in-7 net covers the board (every hex is a net hex or
    touches exactly one), the mover's own hex is a net hex, the search follows
    a single hill to its top, every state in a looked-at hex is scored once,
    and the same input gives the same answer."""
    import types
    hexes = [hex_geometry.parse_hex_label(f"{c:02d}{r:02d}") for c in range(1, 17) for r in range(1, 18)]
    q_r = lambda h: (h[0], (h[1] - h[0]) // 2)                       # noqa: E731
    colour = lambda h: (q_r(h)[0] + 3 * q_r(h)[1]) % 7               # noqa: E731
    deltas = hex_geometry.FACING_DELTAS.values()
    for h in hexes:
        near = [colour((h[0] + dx, h[1] + dy)) for dx, dy in deltas]
        assert sorted(near + [colour(h)]) == list(range(7)), h      # a hex and its 6 neighbours: all 7 colours
    # Two states (facings) per hex; one smooth hill peaking at hex 1210.
    peak = hex_geometry.parse_hex_label("1210")
    states = [types.SimpleNamespace(hex_xy=h, facing=f) for h in hexes for f in (0, 3)]
    calls = []

    def score_spot(c):
        calls.append(c)
        d = max(abs(c.hex_xy[0] - peak[0]), (abs(c.hex_xy[0] - peak[0]) + abs(c.hex_xy[1] - peak[1])) // 2)
        return (100.0 - d + 0.1 * c.facing, c, None)

    start = hex_geometry.parse_hex_label("0303")
    scored = ms._grid_search(states, lambda sts: [score_spot(c) for c in sts], start, 1)
    assert max(scored, key=lambda t: t[0])[1].hex_xy == peak
    assert len(calls) == len({id(c) for c in calls}) == len(scored)   # each state scored once
    assert start in {c.hex_xy for c in calls}                         # the mover's own hex is in the net
    assert len(scored) < len(states) / 3                              # far fewer than every state
    # The always-checks (Daniel, 2026-10-21): the 6 hexes around the enemy are looked at.
    calls.clear()
    enemy = hex_geometry.parse_hex_label("0315")
    ms._grid_search(states, lambda sts: [score_spot(c) for c in sts], start, 1, target_xy=enemy)
    looked = {c.hex_xy for c in calls}
    assert all((enemy[0] + dx, enemy[1] + dy) in looked for dx, dy in deltas)
    again = ms._grid_search(states, lambda sts: [score_spot(c) for c in sts], start, 1)
    assert [(s, c.hex_xy, c.facing) for s, c, _ in again] == [(s, c.hex_xy, c.facing) for s, c, _ in scored]


if __name__ == "__main__":
    failures = 0
    for fn in CHECKS:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print()
    if failures:
        print(f"{failures} of {len(CHECKS)} movement-selection checks FAILED.")
        sys.exit(1)
    print(f"All {len(CHECKS)} movement-selection checks passed.")
