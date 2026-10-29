"""
INTEGRATION__princess_modern.py  (NEW 2026-10-27, Claude - the Princess bot, modern)

MegaMek's Princess as of main, commit fd2edfb (2026-10-26) - the movement
ranker a 'Mech uses (BasicPathRanker; Princess.getPathRanker gives every
'Mech the Basic ranker unless the "experimental" behavior is on). Daniel,
2026-10-27: "Clone the entire modern suit for Princess." The v0.50.07 clone
stays in INTEGRATION__princess (config.PRINCESS_VERSION picks); the hex
geometry (ConvexBoardArea, HexLine), the PSR odds and the bog-down factor are
shared from there. Fire control (modern: movement heat, TSM, crits by damage
on a hit) is INTEGRATION__princess_fire; the physical-attack choice
(PhysicalCalculator) did not change.

=== THE SCORE (BasicPathRanker.rankPath, modern) ===
    utility = - fallMod + braveryMod - aggressionMod + closeRangeIncentive
              - facingMod + positionHoldMod
  New since v0.50.07 (the rest as INTEGRATION__princess):
  - POSTURE (PostureResolver): ATTACK, or DEFEND while the enemy closes 0.5+
    hexes a round on the mean over the last 3 rounds (back to ATTACK once it
    closes 0.1 or less). Resolved once a round, at Princess's first move.
    DEFEND: no aggression pull while the enemy is within 15 hexes now; a
    held position's credit caps at 0.8 instead of 0.4.
  - CLOSE-RANGE INCENTIVE (calculateCloseRangeIncentive): inside 12 hexes, the
    'Mech's point-blank premium - (range-1 damage + floor(tons / 5) melee) -
    damage at the range it ends at - x (12 - distance) / 11.
  - FACING: a 'Mech pulled to close range with a melee attack squares up on
    the enemy (no armor bias, no tolerance).
  - POSITION HOLD (calculatePositionHoldMod): a spot it doesn't leave, within
    15 hexes: quality = P(success) x damage done x (water's sustained-fire
    boost) - damage taken; credit = min(cap x min(quality, 15 x aggression)
    + 5, 15 x aggression), cap 0.4 (ATTACK) / 0.8 (DEFEND).
  - ESTIMATES: an enemy still to move - my damage x the to-hit share my own
    movement leaves me (attackerMovementDamageDiscount: P(8 + AMM) / P(8)),
    its damage x the share my end hex's cover lets through
    (incomingFireTerrainDiscount: woods at a woods EDGE, depth-1 water). An
    enemy that has moved - its adjacent punch / kick / club as a THREAT
    (expected damage + 30 x criticals + 100 x pilot hits + 1000 x kill, no
    "hits more often than not" gate); mine its best plain expected damage
    (both punches, the kick, a club); my firing plan judged with the move's
    heat (FireControl.calcHeatTolerance with predicted movement heat).
  - WATER HAZARD: a breached location 50 (head / center torso 1000) - plus,
    for the locations a fall would put under, the chance of falling there;
    priced for every hex of the path (checkPathForHazards, 2026-10-28 -
    classic.path_hazards), and for the water a 'Mech standing still is in.
  Zero in a duel at the default sliders, not computed: mutual support,
  crowding, favor-higher-TMM, self-preservation / withdrawal (no crippled
  rules here yet), standoff (artillery / TAG spotters - none carry them in
  the reference matchups; a 'Mech that does still ranks as a line 'Mech),
  sprinting (TacOps), aerospace, unit orders, towns, formations.
"""

import math

import INTEGRATION__config as config
import INTEGRATION__movement_selection as movement_selection
import INTEGRATION__ranged_combat as ranged_combat
import INTEGRATION__weapon_selection as weapon_selection
import INTEGRATION__expected_damage as expected_damage
import INTEGRATION__weapon_rules as weapon_rules
import INTEGRATION__princess as classic
import INTEGRATION__princess_fire as princess_fire
import INTEGRATION__princess_group as princess_group
import INTEGRATION__forces as forces
import INTEGRATION__los_cache as geo_cache
import INTEGRATION__water as water
import INTEGRATION__arcs as arcs
import INTEGRATION__attack_resolution as attack_resolution
import INTEGRATION__timing as timing
from mech_state import is_immobile, compute_heat_dissipation, compute_walk_mp, is_superheavy  # noqa: E402 - MECHSIM
from damage_resolution import get_weapons  # noqa: E402 - MECHSIM
import hex_geometry  # noqa: E402 - PATHFINDER
import combat  # noqa: E402 - PATHFINDER
from combat import hit_probability  # noqa: E402 - PATHFINDER
from los import hex_distance, TARGET_WOODS_MODIFIER, _woods_density  # noqa: E402 - PATHFINDER

THREAT_CONTACT_RANGE = 15
TEMPO_REFERENCE_MP = 15.0
REPRESENTATIVE_TO_HIT = 8
ESTIMATE_NOISE_MARGIN = 5.0
HOLD_CREDIT_ATTACK_CAP_FACTOR = 0.4
HOLD_CREDIT_DEFEND_CAP_FACTOR = 0.8
CLOSE_RANGE_BAND = 12.0
CLOSE_RANGE_INCENTIVE_WEIGHT = 1.0
PHYSICAL_PILOT_HIT_WEIGHT = 100.0
PHYSICAL_CRIT_WEIGHT = 30.0
CLOSING_THRESHOLD_HEXES_PER_ROUND = 0.5
DEFEND_EXIT_THRESHOLD_HEXES_PER_ROUND = 0.1
CLOSING_WINDOW_ROUNDS = 3
ATTACK, DEFEND = "ATTACK", "DEFEND"

# ProbabilityCalculator's punch / kick location odds (Mek location order:
# head, CT, RT, LT, RA, LA, RL, LL); rear attacks use the front table.
PUNCH_ODDS = {"front": (1 / 6,) * 6 + (0, 0), "right": (1 / 6, 1 / 6, 2 / 6, 0, 2 / 6, 0, 0, 0),
              "left": (1 / 6, 1 / 6, 0, 2 / 6, 0, 2 / 6, 0, 0)}
KICK_ODDS = {"front": (0,) * 6 + (0.5, 0.5), "right": (0,) * 6 + (1.0, 0), "left": (0,) * 6 + (0, 1.0)}
PUNCH_ODDS["rear"], KICK_ODDS["rear"] = PUNCH_ODDS["front"], KICK_ODDS["front"]


# =============================================================================
# ===========================  POSTURE  =======================================
# =============================================================================
def posture(mover, other, units=None):
    """PostureResolver.resolve (AUTO) for `mover`'s team - once a round, from the enemy's mean distance to the
    centre of the team's force (INTEGRATION__princess_group.force_posture; kept in the team's memory,
    INTEGRATION__princess_memory). With two 'Mechs that is just the distance between them."""
    group = princess_group.Group(mover, other, units if units is not None else [mover, other], True)
    return princess_group.force_posture(mover, group)


# =============================================================================
# ===========================  HEX PROPERTIES  ================================
# =============================================================================
_HEX_PROPERTIES = {"board": None, "map": {}}


def hex_properties(terrain_map, label):
    """HexPropertiesMap.at: (concealment, concealment edge, partial cover,
    heat sink) - concealment is the target-in-woods modifier (p.66), an edge
    when an on-board neighbour has none; partial cover = depth-1 water; heat
    sink = depth 1+ water."""
    if _HEX_PROPERTIES["board"] is not terrain_map:
        _HEX_PROPERTIES["board"], _HEX_PROPERTIES["map"] = terrain_map, {}
    cache = _HEX_PROPERTIES["map"]
    got = cache.get(label)
    if got is None:
        hexes = terrain_map["hexes"]

        def concealment(lbl):
            return TARGET_WOODS_MODIFIER.get(_woods_density(hexes[lbl]["features"]), 0)
        conceal = concealment(label)
        edge = False
        if conceal > 0:
            xy = hex_geometry.parse_hex_label(label)
            for d in range(6):
                try:
                    n = hex_geometry.hex_label(*classic._neighbor(xy, d))
                except ValueError:
                    continue
                if n in hexes and concealment(n) == 0:
                    edge = True
                    break
        depth = water.depth_at(label, terrain_map)
        got = cache[label] = (conceal, edge, depth == 1, depth >= 1)
    return got


def _odds_ratio(modifiers):
    """Compute.oddsAbove(8 + m) / oddsAbove(8)."""
    if modifiers <= 0:
        return 1.0
    return hit_probability(REPRESENTATIVE_TO_HIT + modifiers) / hit_probability(REPRESENTATIVE_TO_HIT)


def terrain_discount(terrain_map, label):
    """incomingFireTerrainDiscount: only cover a 'Mech can fight from - a woods
    edge, depth-1 water - counts."""
    conceal, edge, partial, _ = hex_properties(terrain_map, label)
    return _odds_ratio((conceal if edge else 0) + (1 if partial else 0))


# =============================================================================
# ===========================  PIECES OF THE SCORE  ===========================
# =============================================================================
def estimated_melee_damage(mech):
    """floor(tons / 5) for a standing 'Mech that can walk, else 0."""
    if mech.prone or compute_walk_mp(mech) <= 0:
        return 0
    return math.floor(mech.mass / 5.0)


def close_range_incentive(mech, dist, max_at=None):
    """max_at: an optional {range: max_damage_at_range} memo for one ranking (nothing changes the mech's
    weapons or ammo while its paths are ranked)."""
    if dist < 1 or dist >= CLOSE_RANGE_BAND:
        return 0.0

    def at(rng):
        if max_at is None:
            return princess_fire.max_damage_at_range(mech, rng)
        if rng not in max_at:
            max_at[rng] = princess_fire.max_damage_at_range(mech, rng)
        return max_at[rng]
    point_blank = at(1) + estimated_melee_damage(mech)
    premium = point_blank - at(int(math.ceil(dist)))
    if premium <= 0:
        return 0.0
    return premium * (CLOSE_RANGE_BAND - dist) / (CLOSE_RANGE_BAND - 1) * CLOSE_RANGE_INCENTIVE_WEIGHT


def facing_mod(o, face_xy, bias, square_up, closest_xy=None):
    """FacingDiffCalculator (modern): squaring up faces the closest enemy exactly (no armor bias, no tolerance);
    otherwise the unit faces face_xy - the closest enemy when it ends beside it, else the median of the closest few."""
    if square_up and closest_xy is not None:
        face_xy, bias, tolerance = closest_xy, 0, 0
    else:
        square_up, tolerance = False, classic.ALLOW_FACING_TOLERANCE
    want = classic.direction(o.hex_xy, face_xy)
    if not square_up:
        want = (want + bias) % 6
    diff = min((o.facing - want) % 6, (want - o.facing) % 6)
    return classic.FACING_MOD_MULTIPLIER * max(0, diff - tolerance)


def sustained_damage(mech, distance, capacity):
    """DamageProfile.sustainedDamage: at `distance`, the expected damage (at the
    pilot's gunnery + range modifier) of the weapons the heat sinks keep
    firing every turn - best damage per heat first."""
    firing = []
    for w in get_weapons(mech):
        if weapon_rules.is_ams(w) or w.damage_per_shot is None:
            continue
        mod = weapon_selection._weapon_range_mod(w, distance)
        if mod is None:
            continue
        dmg = hit_probability(mech.gunnery + mod) * expected_damage.expected_damage_per_hit(w)
        firing.append((dmg, w.heat or 0))
    firing.sort(key=lambda f: -(f[0] / f[1]) if f[1] > 0 else -float("inf"))
    total, budget = 0.0, capacity
    for dmg, heat in firing:
        if heat <= 0:
            total += dmg
        elif heat <= budget:
            total += dmg
            budget -= heat
    return total


def heat_sink_boost(mech, o, dist, terrain_map):
    """heatSinkSustainBoost: standing in water, how much more it can keep
    firing at this range than on dry ground (1 if not more)."""
    if not hex_properties(terrain_map, o.label)[3]:
        return 1.0
    rng = max(1, int(math.ceil(dist)))
    dry_capacity = compute_heat_dissipation(mech)
    wet_capacity = dry_capacity + water.dissipation_bonus(mech, water.state_at(o.label, mech.prone, terrain_map, is_superheavy(mech)))
    dry = sustained_damage(mech, rng, dry_capacity)
    wet = sustained_damage(mech, rng, wet_capacity)
    return wet / dry if dry > 0 and wet > dry else 1.0


def water_hazard(mover, label, depth, end_hex, prone, fall_odds, moving=True):
    """waterHazard (modern) for one hex: each submerged location with no
    armor left - 50, the head / center torso 1000; and, along a move (a
    MovePath), the locations only a fall would put under, x the chance of
    falling as it enters (running into water forces a roll here - the
    project's terrain PSR)."""
    def submerged(down):
        out = set()
        for loc, entry in mover.locations.items():
            if entry["destroyed"]:
                continue
            legs = loc in mover.leg_locations or loc in ("Front Left Leg", "Front Right Leg")
            if depth >= 2 or down or legs:
                out.add(loc)
        return out

    def weight(loc):
        return classic.UNIT_DESTRUCTION_FACTOR if loc in ("Head", "Center Torso") else 50.0
    now, if_down = submerged(prone), submerged(True)
    total = 0.0
    for loc in now:
        if mover.locations[loc]["armor"] <= 0:
            if weight(loc) == classic.UNIT_DESTRUCTION_FACTOR:
                return classic.UNIT_DESTRUCTION_FACTOR
            total += weight(loc)
    if moving:
        for loc in if_down - now:
            if mover.locations[loc]["armor"] <= 0:
                total += fall_odds * weight(loc)
    return total


def hazards(mover, o, terrain_map, fall_odds, paths=None):
    """checkPathForHazards (modern): classic.path_hazards with waterHazard;
    a move with no steps prices the water it stays in (a 'Mech in water)."""
    p_fall = fall_odds if o.mode == "Run" else 0.0

    def water_fn(label, depth, end_hex, prone):
        return water_hazard(mover, label, depth, end_hex, prone, p_fall)

    def stay_fn():
        depth = water.depth_at(mover.hex, terrain_map) if mover.hex is not None else 0
        return water_hazard(mover, mover.hex, depth, True, mover.prone, 0.0, moving=False) if depth >= 1 else 0.0
    return classic.path_hazards(mover, o, terrain_map, paths, water_fn, stay_fn)


# =============================================================================
# ===========================  PHYSICAL ESTIMATES  ============================
# =============================================================================
def _physical_options(attacker, a_xy, a_label, a_facing, a_amm, target, t_xy, t_label, t_facing, target_tmm,
                      target_prone, terrain_map):
    """(base TN, options by kind, side hit on the target) for a physical attack
    between two given positions - the project's rules (reach, actuators,
    levels, hit tables)."""
    import INTEGRATION__physical as physical
    levels = terrain_map["hexes"]
    opts = physical.options_at(attacker, a_xy, a_facing, levels[a_label]["level"], t_xy, levels[t_label]["level"],
                               target_prone, frozenset(), arcs.current_action(attacker),
                               is_superheavy(target))
    if not opts:
        return None, {}, "front"
    los_mod = geo_cache.los(a_xy, t_xy, terrain_map, 2, 1 if target_prone else 2).modifier
    base = physical.base_tn(attacker, a_amm, target_tmm, los_mod,
                            attack_resolution.prone_target_modifier(target, 1) if target_prone else 0)
    side = attack_resolution.attack_side(a_xy, t_xy, t_facing, terrain_map)
    return base, opts, side


def _one(opts, kind, limb=None):
    """The option of `kind` (for a limb if given): RIGHT_KICK is the right leg."""
    for o in opts.get(kind, ()):
        if limb is None or o.get("limb") == limb:
            return o
    return None


def _physical_info(option, base, target, side):
    """PhysicalInfo: (expected damage, criticals, pilot hits, kill chance)."""
    p = hit_probability(base + option["mod"])
    damage = option["damage"]
    table = option["table"]
    odds = (PUNCH_ODDS if table == "punch" else KICK_ODDS if table == "kick" else princess_fire.HIT_ODDS)[side]
    crits, kill = princess_fire.weapon_crits_and_kill(target, side, p, p * damage, on_hit=damage, odds=odds)
    return p * damage, crits, odds[0] * p, kill


def physical_threat(attacker, a_xy, a_label, a_facing, a_amm, target, t_xy, t_label, t_facing, target_tmm,
                    terrain_map):
    """calculateEnemyPhysicalThreat: the best of its kick, both punches and a
    physical weapon / club, each valued as damage + 30 x criticals + 100 x
    pilot hits + 1000 x kill."""
    base, opts, side = _physical_options(attacker, a_xy, a_label, a_facing, a_amm, target, t_xy, t_label, t_facing,
                                         target_tmm, False, terrain_map)
    if base is None:
        return 0.0

    def value(option):
        if option is None:
            return 0.0
        ed, crits, pilot, kill = _physical_info(option, base, target, side)
        return (ed + crits * PHYSICAL_CRIT_WEIGHT + pilot * PHYSICAL_PILOT_HIT_WEIGHT
                + kill * classic.UNIT_DESTRUCTION_FACTOR)
    kick = value(_one(opts, "kick", "Right Leg") or _one(opts, "kick"))
    punches = value(_one(opts, "punch", "Left Arm")) + value(_one(opts, "punch", "Right Arm"))
    weapon = max((value(o) for kind in ("weapon", "club") for o in opts.get(kind, ())), default=0.0)
    return max(weapon, kick, punches)


def my_physical(attacker, a_xy, a_label, a_facing, a_amm, target, t_xy, t_label, t_facing, target_tmm,
                target_prone, terrain_map):
    """calculateMyPhysicalDamagePotential: plain expected damage, the best of
    the kick, both punches and a physical weapon / club."""
    base, opts, side = _physical_options(attacker, a_xy, a_label, a_facing, a_amm, target, t_xy, t_label, t_facing,
                                         target_tmm, target_prone, terrain_map)
    if base is None:
        return 0.0

    def value(option):
        return 0.0 if option is None else hit_probability(base + option["mod"]) * option["damage"]
    kick = value(_one(opts, "kick", "Right Leg") or _one(opts, "kick"))
    punches = value(_one(opts, "punch", "Left Arm")) + value(_one(opts, "punch", "Right Arm"))
    weapon = max((value(o) for kind in ("weapon", "club") for o in opts.get(kind, ())), default=0.0)
    return max(weapon, kick, punches)


# =============================================================================
# ===========================  THE CHOICE  ====================================
# =============================================================================
def choose(mover, other, terrain_map, battle_rng, moves_first, standup_mp=None, entry_edge=None):
    """Modern Princess's end-of-movement pick. Same arguments and return as
    movement_selection.choose: (pick, note). `other` is the nearest enemy; the unit weighs every enemy on the
    board (BasicPathRanker.rankPath loops over all of them: my best damage on any one, the damage of all of
    them to me), its force's posture, and its friends (INTEGRATION__princess_group)."""
    if other.hex is None:
        return movement_selection.choose(mover, other, terrain_map, battle_rng, moves_first,
                                         standup_mp=standup_mp, entry_edge=entry_edge)
    group = princess_group.Group(mover, other, forces.battle() or [mover, other], moves_first)
    stance = princess_group.force_posture(mover, group)
    with timing.section("reachable spots"):
        options = movement_selection.reduced_options(mover, terrain_map,
                                                     exclude_hex=movement_selection.occupied_hexes(mover, other),
                                                     standup_mp=standup_mp, entry_edge=entry_edge)
    moved = group.has_moved(other)
    prepared, estimate = None, None
    with timing.section("Princess path ranking"), \
            weapon_selection.fire_control(princess_fire.FireControl(guess=True, self_mech=mover)):
        for foe in group.foes:
            if not princess_group.can_matter(mover, foe):
                continue                                          # too far for either side to reach the other
            ev = ranged_combat.MoveEvaluator(mover, foe, terrain_map)
            ev.mover_physical = ev.defender_physical = False      # physical attacks are priced below
            if prepared is None:
                prepared = ev.prepare(options)
                if not prepared:
                    return None, "no reachable spot"
            got = (_moved_estimates(mover, foe, prepared, ev, terrain_map) if group.has_moved(foe)
                   else _unmoved_estimates(mover, foe, prepared, terrain_map))
            estimate = got if estimate is None else princess_group.combine_estimates(estimate, got)
        if prepared is None:                                      # every enemy out of reach: the options still rank
            prepared = ranged_combat.prepare_options(mover, options)
            if not prepared:
                return None, "no reachable spot"
            estimate = {classic._key(o): (0.0, 0.0, 0.0) for o in prepared}
    paths = ranged_combat.PathBook(mover, terrain_map, standup_mp, entry_edge)
    return _rank(mover, group, prepared, estimate, terrain_map, standup_mp is None, moved, stance, paths)


def _moved_estimates(mover, other, prepared, ev, terrain_map):
    """{option key: (my firing, my physical, their damage)} - evaluateMovedEnemy (modern)."""
    cands = {(c.hex, c.facing, c.mode, c.fc): c
             for c in ev.evaluate(other.hex, other.facing, other.move_fc, other.move_mode, other.mp_spent, prepared)}
    enemy_xy = hex_geometry.parse_hex_label(other.hex)
    other_facing = hex_geometry.compass_to_facing(other.facing)
    other_tmm = attack_resolution._target_tmm(other)
    other_amm = combat.MODE_TO_AMM[other.move_mode]
    attacks_back = not (other.shutdown or other.prone or is_immobile(other))
    can_attack = not (mover.shutdown or is_immobile(mover))
    out = {}
    for o in prepared:
        c = cands.get((o.label, o.facing_compass, o.mode, o.fc))
        mine, theirs = (c.dealt, c.received) if c is not None else (0.0, 0.0)
        physical_mine = 0.0
        if hex_distance(o.hex_xy, enemy_xy) <= 1:
            if attacks_back:
                theirs += physical_threat(other, enemy_xy, other.hex, other_facing, other_amm,
                                          mover, o.hex_xy, o.label, o.facing, o.tmm, terrain_map)
            if can_attack:
                physical_mine = my_physical(mover, o.hex_xy, o.label, o.facing, o.amm,
                                            other, enemy_xy, other.hex, other_facing, other_tmm, other.prone,
                                            terrain_map)
        out[classic._key(o)] = (mine, physical_mine, theirs)
    return out


def _unmoved_estimates(mover, other, prepared, terrain_map):
    """evaluateUnmovedEnemy (modern): the v0.50.07 estimate with my damage x
    attackerMovementDamageDiscount and its weapons x incomingFireTerrainDiscount
    (the flank kick isn't discounted)."""
    out = {}
    for k, (mine, theirs, flank) in classic.unmoved_parts(mover, other, prepared, terrain_map).items():
        out[k] = (mine, 0.0, theirs, flank)
    by_key = {classic._key(o): o for o in prepared}
    return {k: (mine * _odds_ratio(by_key[k].amm), 0.0,
                theirs * terrain_discount(terrain_map, by_key[k].label) + flank)
            for k, (mine, _, theirs, flank) in out.items()}


def _foes_note(group, moved):
    """"enemy moved" for a duel (the form of every earlier log), "3 enemies, nearest still to move" for a battle."""
    state = "moved" if moved else "still to move"
    return f"enemy {state}" if len(group.foes) == 1 else f"{len(group.foes)} enemies, nearest {state}"


def _rank(mover, group, prepared, estimate, terrain_map, psr_applies, moved, stance, paths=None):
    fall_shame = princess_fire.setting("fall_shame")
    bravery = princess_fire.setting("bravery")
    aggression = princess_fire.setting("hyper_aggression")
    bias = classic._armor_bias(mover)
    melee = estimated_melee_damage(mover) > 0
    tolerance = config.PRINCESS_BEHAVIOR["fall_shame"] / 20.0 + 0.50
    max_range = movement_selection._max_range(mover)
    # validatePaths: the closest enemy now, and from each end spot
    start = group.distance_to_enemy(hex_geometry.parse_hex_label(mover.hex)) if mover.hex is not None else None
    in_range = start is not None and max_range >= start
    no_pull = stance == DEFEND and start is not None and start <= THREAT_CONTACT_RANGE
    odds = movement_selection.terrain_psr_odds(mover)
    fall_odds = odds.get("fail", 0.0) if psr_applies else 0.0
    success = {classic._key(o): classic.success_probability(mover, o, psr_applies) for o in prepared}
    valid = []
    for o in prepared:
        if start is not None:
            d = group.distance_to_enemy(o.hex_xy)
            if (in_range and d > max_range) or (not in_range and d > start):
                continue
        if success[classic._key(o)] < tolerance:
            continue
        valid.append(o)
    pool = valid or prepared
    turn_of_advance = TEMPO_REFERENCE_MP * aggression
    cap = HOLD_CREDIT_DEFEND_CAP_FACTOR if stance == DEFEND else HOLD_CREDIT_ATTACK_CAP_FACTOR
    best = None
    max_at = {}                                  # close_range_incentive's memo for this ranking
    for o in pool:
        k = classic._key(o)
        p = success[k]
        mine, physical_mine, theirs = estimate[k]
        done = mine + physical_mine
        taken = theirs + hazards(mover, o, terrain_map, fall_odds, paths)
        fail = 1.0 - p
        fall_mod = fail * (classic.UNIT_DESTRUCTION_FACTOR if fail == 1 else fall_shame)
        bravery_mod = p * done * bravery - taken
        dist = group.distance_to_enemy(o.hex_xy)
        aggression_mod = 0.0 if no_pull else (dist if dist else 2) * aggression
        close = close_range_incentive(mover, dist, max_at)
        face_xy = group.face_target(o.hex_xy)
        near = group.nearest(o.hex_xy, min_distance=1)
        face = facing_mod(o, face_xy, bias, square_up=close > 0 and melee and dist >= 1,
                          closest_xy=hex_geometry.parse_hex_label(near[0].hex) if near else None)
        support = group.support_mod(o.hex_xy)
        crowd = group.crowding_mod(o.hex_xy, max_range)
        hold = 0.0
        if o.fc == 0 and dist <= THREAT_CONTACT_RANGE:
            quality = p * done * heat_sink_boost(mover, o, dist, terrain_map) - taken
            if quality > 0:
                hold = min(cap * min(quality, turn_of_advance) + ESTIMATE_NOISE_MARGIN, turn_of_advance)
        utility = -fall_mod + bravery_mod - aggression_mod + close - support - crowd - face + hold
        if best is None or utility > best[0]:
            best = (utility, o, fall_mod, bravery_mod, p, done, taken, aggression_mod, close, face, hold, support, crowd)
    utility, o, fall_mod, bravery_mod, p, done, taken, aggression_mod, close, face, hold, support, crowd = best
    group_note = (f" - mutual support {support:.2f}" if support else "") + (f" - crowding {crowd:.2f}" if crowd else "")
    note = (f"Princess (modern, {stance.lower()}): utility {utility:.2f} = -fall {fall_mod:.2f} + bravery "
            f"{bravery_mod:.2f} [{p:.2f} x {done:.2f} x {bravery} - taken {taken:.2f}] - aggression "
            f"{aggression_mod:.2f} + close range {close:.2f}{group_note} - facing {face:.0f} + hold {hold:.2f} "
            f"[{len(pool)} of {len(prepared)} spots; {_foes_note(group, moved)}]")
    return {"hex": o.label, "facing": o.facing_compass, "mode": o.mode, "fc": o.fc, "mp_spent": o.mp_spent}, note
