"""
INTEGRATION__princess.py  (NEW 2026-10-27, Claude - the Princess bot, part 2)

MegaMek's Princess bot (v0.50.07) - its movement: BasicPathRanker.rankPath
scores every place the 'Mech can end its move, and the best one wins
(PathRanker.getBestPath). Fire control and physical attacks are
INTEGRATION__princess_fire; the switch between bots is INTEGRATION__bots;
the settings are config.PRINCESS_BEHAVIOR (MegaMek's "DEFAULT" behavior).

=== THE SCORE (BasicPathRanker.rankPath) ===
    utility = - fallMod + braveryMod - aggressionMod - facingMod
  - fallMod = P(a piloting roll on the way fails) x fall shame (500 at the
    default slider; 1000 when a fall is certain).
  - braveryMod = P(success) x (my firing + my physical damage) x bravery
    (1.5) - expected damage taken (the enemy's + hazards).
  - aggressionMod = hexes to the enemy (0 counts 2) x hyper-aggression (2.5).
  - facingMod = 50 x (hexsides off the ideal facing - 1, at least 0)
    (FacingDiffCalculator): the ideal faces the enemy, turned one hexside to
    show the side (arm + leg + torso) with more armor left.
  Zero in a duel at the default sliders, so not computed: herding (no
  friends), movementMod (favor-higher-TMM 0), crowding (anti-crowding 0),
  self-preservation (only while withdrawing - this project has no forced
  withdrawal yet, Pick up here 5), off-board (aerospace).

=== DAMAGE ESTIMATES ===
  - Enemy already moved (or immobile) - evaluateMovedEnemy: both sides'
    best "guess" firing plan utility (INTEGRATION__princess_fire, guess
    mode, best twist) from the real positions - the project's to-hit, LOS,
    arcs and water, with Princess's plan choice and value; plus each side's
    kick (P(hit) x damage) when adjacent and the kick hits more often than
    not.
  - Enemy still to move - evaluateUnmovedEnemy: the hex of the area it can
    reach that is closest to my spot (ConvexBoardArea.getClosestCoordsTo -
    the convex hull of its reachable hexes, ported with its HexLine maths);
    at that range its summed weapon damage (no to-hit, cluster = rack size)
    x 0.25, plus ceil(tons / 5) x 0.25 if it can reach the hex behind me or
    a rear flank facing my side (canFlankAndKick); my damage the same way,
    x 0.25, only if its whole reachable area lies inside my firing wedge
    (isInMyLoS).

=== WHICH SPOTS (PathRanker.validatePaths) ===
Every reachable spot (the project's movement options, reduced as Gladiator's
are - Princess's numbers never prefer fewer hexes moved), then:
  - in range of the enemy now: drop spots out of my longest range; out of
    range: drop spots farther than I am now;
  - drop spots with P(success) under the fall tolerance (0.75 at the
    default slider: index / 20 + 0.5);
  - if nothing is left, use them all.
Ties keep the first spot found (MegaMek's TreeSet drops an equal rank).

Hazards (checkPathForHazards; every hex of the path since 2026-10-28 -
Daniel: "Need the change for an acurate replica"; was the end hex only): a
jump prices its landing hex; a ground move every hex its steps stand in
(ranged_combat.PathBook - the path the project's search found to that end
state), each once, the last as the end hex; standing still nothing. Per hex
(Terrains.HAZARDS): water (an unarmored submerged location 50, the head /
center torso 1000), swamp (calcSwampHazard - quicksand odds), mud (the
bog-down factor), magma (calcMagmaHazard / calcLavaHazard) and hazardous
liquid (calcHazardousLiquidHazard) - the same in v0.50.07 and MegaMek main.
Rubble is NOT a MegaMek hazard terrain (its calcRubbleHazard is never
reached); the clone priced it until 2026-10-28.
Not ported: charges and death from above (v0.50.07 Princess never
declares them), MASC odds in P(success) (the project rolls MASC before
the move), unjamming a rotary AC, forced withdrawal, the "move to contact"
re-rank when no spot deals damage (the spot list is the same here).
"""

import math

import INTEGRATION__config as config
import INTEGRATION__movement_selection as movement_selection
import INTEGRATION__ranged_combat as ranged_combat
import INTEGRATION__weapon_selection as weapon_selection
import INTEGRATION__princess_fire as princess_fire
import INTEGRATION__los_cache as geo_cache
import INTEGRATION__water as water
import INTEGRATION__arcs as arcs
import INTEGRATION__attack_resolution as attack_resolution
import INTEGRATION__timing as timing
from mech_state import is_immobile, is_superheavy  # noqa: E402 - MECHSIM
import piloting_rolls  # noqa: E402 - MECHSIM
import hex_geometry  # noqa: E402 - PATHFINDER
import combat  # noqa: E402 - PATHFINDER
import terrain_rules  # noqa: E402 - PATHFINDER
from combat import hit_probability  # noqa: E402 - PATHFINDER
from los import hex_distance  # noqa: E402 - PATHFINDER

FACING_MOD_MULTIPLIER = 50
UNIT_DESTRUCTION_FACTOR = 1000
ALLOW_FACING_TOLERANCE = 1          # BehaviorSettings.DEFAULT_ALLOW_FACING_TOLERANCE
UNMOVED_DAMAGE_DISCOUNT = 0.25      # evaluateUnmovedEnemy's damageDiscount
KICK_THRESHOLD = 0.5                # calculate(My)KickDamagePotential: only if it hits more often than not


# =============================================================================
# ===========================  MEGAMEK HEX GEOMETRY  ==========================
# =============================================================================
# MegaMek's Coords are (column - 1, row - 1); odd columns sit half a hex lower.
# HexLine / ConvexBoardArea are ported as written, Java integer division included.
def _jdiv(a, b):
    """Java integer division (truncates toward zero)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def mm(xy):
    """Project internal (x, y) -> MegaMek Coords (x, y), on or off the board."""
    x, y = xy
    return x, -_jdiv(y - hex_geometry._row_parity_offset(x), 2)


def mm_distance(a, b):
    """Coords.distance (cube distance, odd columns shifted down)."""
    def cube(c):
        q = c[0]
        r = c[1] - (c[0] - (c[0] & 1)) // 2
        return q, r, -q - r
    (q1, r1, s1), (q2, r2, s2) = cube(a), cube(b)
    return max(abs(q1 - q2), abs(r1 - r2), abs(s1 - s2))


def _neighbor(xy, direction):
    dx, dy = hex_geometry.FACING_DELTAS[direction % 6]
    return xy[0] + dx, xy[1] + dy


def _intercept(c, d):
    """HexLine's intercept for a line through c in direction d."""
    x, y = c
    if d in (0, 3):
        return x
    if d in (1, 4):
        return y + _jdiv(x + 1, 2)
    return y - _jdiv(x, 2)


class HexLine:
    def __init__(self, c, d, intercept=None):
        self.d = d
        self.i = _intercept(c, d) if intercept is None else intercept

    def judge_point(self, c):
        other = _intercept(c, self.d)
        if other < self.i:
            return -1 if self.d < 3 else 1
        if other > self.i:
            return 1 if self.d < 3 else -1
        return 0

    def judge_area(self, area):
        flip = self.d > 2
        one, two = area.edges[self.d], area.edges[(self.d + 3) % 6]
        if one is None or two is None or one.i == self.i or two.i == self.i:
            return 0
        edge_one = (one.i < self.i) ^ flip
        edge_two = (two.i < self.i) ^ flip
        if edge_one and edge_two:
            return 1
        if not edge_one and not edge_two:
            return -1
        return 0

    def y_from_x(self, x):
        if self.d in (0, 3):
            return 0
        if self.d in (1, 4):
            return self.i - _jdiv(x + 1, 2)
        return self.i + _jdiv(x, 2)

    def intersection(self, other):
        if other.d % 3 == self.d % 3:
            return None
        if other.d == 0 or self.d == 2:
            return other.intersection(self)
        if self.d in (0, 3):
            return self.i, other.y_from_x(self.i)
        x = self.i - other.i
        return x, self.y_from_x(x)

    def closest_point(self, c):
        if self.d in (0, 3):
            return self.i, c[1]
        if self.d in (1, 4):
            x = int((-2.0 / 3.0) * (self.i - 0.5 - c[1] - 2.0 * c[0]))
        else:
            x = int((-5.0 / 3.0) * (self.i - c[1] - 2.0 * c[0]))
        return x, self.y_from_x(x)


class ConvexBoardArea:
    """The convex hull of a unit's reachable hexes (PathEnumerator's
    unitMovableAreas)."""

    def __init__(self, coords):
        self.edges = [None] * 6
        for c in coords:
            for i in range(6):
                if self.edges[i] is None or self.edges[i].judge_point(c) > 0:
                    self.edges[i] = HexLine(c, i)
        self._vertices = [None] * 6

    def contains(self, c):
        return self.edges[0] is not None and all(e.judge_point(c) <= 0 for e in self.edges)

    def vertex(self, i):
        if self._vertices[i] is None:
            self._vertices[i] = self.edges[i].intersection(self.edges[(i + 1) % 6])
        return self._vertices[i]

    def closest_to(self, c):
        closest, best = None, 0
        for i in range(6):
            edge = self.edges[i]
            if edge is None or edge.judge_point(c) <= 0:
                continue
            vert = self.vertex(i)
            if vert is not None:
                dist = mm_distance(vert, c)
                if closest is None or dist < best:
                    closest, best = vert, dist
            online = edge.closest_point(c)
            if self.contains(online):
                dist = mm_distance(online, c)
                if dist < best:
                    closest, best = online, dist
        return c if closest is None else closest


# =============================================================================
# ===========================  THE PIECES OF THE SCORE  =======================
# =============================================================================
def success_probability(mover, o, psr_applies):
    """getMovePathSuccessProbability: the chance every piloting roll this move
    forces succeeds - running / jumping with damage (piloting_rolls), the
    terrain rolls on the ground path (mover.path_psrs), a jump into water or
    rubble."""
    if not psr_applies:
        return 1.0
    p = 1.0
    psr_mode = "running" if (o.mode == "Run" and o.fc >= 1) else ("jump" if o.mode == "Jump" else None)
    if psr_mode is not None:
        tn = piloting_rolls.movement_psr_target_number(mover, psr_mode)
        if tn is not None:
            p *= hit_probability(tn) ** piloting_rolls.movement_psr_count(mover, psr_mode)
    target = mover.piloting + piloting_rolls.preexisting_modifier(mover) + piloting_rolls.special_case_modifier(mover)
    ok = hit_probability(target)
    if o.mode == "Jump":
        board = water.board()
        if water.depth_at(o.label) >= 1 or (board is not None and "rubble" in board["hexes"][o.label]["features"]):
            p *= ok
    elif o.mode in ("Walk", "Run"):
        n = getattr(mover, "path_psrs", {}).get((o.x, o.y, o.facing, o.fc, o.mode, o.mp_spent), 0)
        p *= ok ** n
    return p


def _bog_down_factor(pilot, modifier, end_hex, jump_landing):
    """calcBogDownFactor: 1 + chance to bog down + expected turns stuck."""
    odds = max(hit_probability(pilot + modifier), 0.0)
    bogged = 1.0 if (end_hex and jump_landing) else (1.0 - odds if not jump_landing else 0.0)
    turns = math.log10(0.10) / math.log10(1 - odds) if (1 - odds) < 1.0 and odds < 1.0 else UNIT_DESTRUCTION_FACTOR
    return 1.0 + bogged + turns


def _submerged_breaches(mover, depth, prone):
    """calcWaterHazard (v0.50.07): every submerged location with no armor
    left - 50, the head / center torso the destruction factor (Princess
    returns it for the water at once, the hex's other hazards still add)."""
    total = 0.0
    for loc, entry in mover.locations.items():
        if entry["destroyed"]:
            continue
        legs = loc in mover.leg_locations or loc in ("Front Left Leg", "Front Right Leg")
        if not (depth >= 2 or prone or legs) or entry["armor"] > 0:
            continue
        if loc in ("Head", "Center Torso"):
            return UNIT_DESTRUCTION_FACTOR
        total += 50
    return total


def swamp_hazard(mover, features, end_hex, jump_landing):
    """calcSwampHazard: the chance it is (1) or becomes (1 in 36) quicksand x
    the destruction factor / (1 + the 'Mech's height, 1), x the bog-down
    factor at +1 (+3 in quicksand - MegaMek's swamp level 2+)."""
    quicksand = int((features["swamp"][:1] or ["1"])[0] or 1) > 1
    chance = 1.0 if quicksand else 1 / 36.0
    hazard = chance * UNIT_DESTRUCTION_FACTOR / (1 + 1)
    return round(hazard * _bog_down_factor(mover.piloting, 3 if quicksand else 1, end_hex, jump_landing))


def hex_hazard(mover, label, terrain_map, end_hex, jump_landing, prone, water_fn=None):
    """checkHexForHazards for one hex (Terrains.HAZARDS the project's maps
    can hold: water, swamp, mud, magma, hazardous liquid - NOT rubble, which
    MegaMek's set leaves out; buildings can't be entered on the ground here).
    water_fn(label, depth, end_hex, prone): the modern waterHazard instead."""
    features = terrain_map["hexes"][label].get("features", {})
    total = 0.0
    depth = water.depth_at(label, terrain_map)
    if depth >= 1:
        total += water_fn(label, depth, end_hex, prone) if water_fn else _submerged_breaches(mover, depth, prone)
    if "swamp" in features:
        total += swamp_hazard(mover, features, end_hex, jump_landing)
    if "mud" in features:
        total += round(_bog_down_factor(mover.piloting, 0, end_hex, False))
    total += magma_hazard(mover, features, jump_landing, end_hex, prone)
    if "hazardous_liquid" in features:
        total += hazardous_liquid_hazard(mover, label, terrain_map, prone)
    return total


_HAZARD_FEATURES = ("swamp", "mud", "magma", "hazardous_liquid")


def _hazard_board(terrain_map):
    """Has the board any hex hex_hazard could price (depth 1+ water, swamp,
    mud, magma, hazardous liquid)? Cached on the board."""
    flag = terrain_map.get("_princess_hazards")
    if flag is None:
        flag = terrain_map["_princess_hazards"] = any(
            info.get("depth", 0) >= 1 or any(f in info["features"] for f in _HAZARD_FEATURES)
            for info in terrain_map["hexes"].values())
    return flag


def path_hazards(mover, o, terrain_map, paths, water_fn=None, stay_fn=None):
    """checkPathForHazards (2026-10-28, Daniel: "Need the change for an
    acurate replica"): a jump - its landing hex only; otherwise every hex
    its steps stand in, a hex once (repeats skipped), the last step's hex as
    the end hex. A move with no steps (standing still) - nothing, or
    stay_fn() (modern: the water it stays in). A 'Mech standing up first
    has a get-up step in the hex it lies in (MegaMek's GET_UP)."""
    if not _hazard_board(terrain_map):
        return 0.0                           # speed only: no hex here can price anything
    if o.mode == "Jump":
        return hex_hazard(mover, o.label, terrain_map, True, True, mover.prone, water_fn)
    moves = bool(o.fc or o.mp_spent)
    steps = paths.path(o) if (paths is not None and moves) else None
    if steps is None and moves:
        steps = [("forward", (o.x, o.y, o.facing), o.mp_spent)]     # no path found: the end hex alone
    if paths is not None and paths.standup_mp is not None and mover.hex is not None:
        sx, sy, sf = hex_geometry.state_from_label(mover.hex, mover.facing)
        steps = [("get up", (sx, sy, sf), 0)] + (steps or [])
    if not steps:
        return stay_fn() if stay_fn else 0.0
    total, previous = 0.0, None
    for n, (_, (x, y, _f), _) in enumerate(steps):
        if (x, y) == previous:
            continue
        total += hex_hazard(mover, hex_geometry.hex_label(x, y), terrain_map, n == len(steps) - 1, False, False,
                            water_fn)
        previous = (x, y)
    return total


def hazards(mover, o, terrain_map, paths=None):
    """checkPathForHazards (v0.50.07) for prepared state o."""
    return path_hazards(mover, o, terrain_map, paths)


# MegaMek's leg locations for calcLavaHazard / calcHazardousLiquidHazard's
# exposed armor: a quad's four legs (Mek.LOC_LEFT_ARM / RIGHT_ARM are its front legs).
def _leg_armor(mover):
    return sum(max(0, mover.locations[l]["armor"]) for l in mover.leg_locations)


def _total_armor(mover):
    return sum(max(0, e["armor"]) + max(0, e.get("rear_armor", 0)) for e in mover.locations.values())


def lava_hazard(mover, jump_landing, end_hex=True, prone=None):
    """calcLavaHazard: heat (10 in the end hex, 5 passing through), plus the
    destruction factor x expected damage / exposed armor (biped 14 on its
    legs, tripod 21, quad 28; prone 7 a location on all its armor), all x
    the bog-down factor when jumping in (PSR +4)."""
    prone = mover.prone if prone is None else prone
    psr_factor = 1.0
    if jump_landing and end_hex:
        odds = hit_probability(mover.piloting + 4)
        bogged = 1.0 - odds
        turns = math.log10(0.10) / math.log10(bogged) if 0.0 < bogged < 1.0 else 0.0
        psr_factor = 1.0 + bogged + turns
    value = 10.0 if end_hex else 5.0
    if prone:
        dmg, exposed = 7 * len(mover.locations), _total_armor(mover)
    else:
        dmg, exposed = 7 * len(mover.leg_locations), _leg_armor(mover)
    value += UNIT_DESTRUCTION_FACTOR * (dmg / max(exposed, 1))
    return round(value * psr_factor)


def magma_hazard(mover, features, jump_landing, end_hex=True, prone=None):
    """calcMagmaHazard: liquid = lava_hazard; a crust = lava_hazard x the
    chance it breaks (1/2 jumping, 0.1667 walking), rounded, plus the heat
    (5 in the end hex, 2 passing) x the chance it holds."""
    state = terrain_rules.magma_state(features)
    if state == terrain_rules.MAGMA_LIQUID:
        return lava_hazard(mover, jump_landing, end_hex, prone)
    if state == terrain_rules.MAGMA_CRUST:
        breaks = 0.5 if jump_landing else 0.1667
        return round(lava_hazard(mover, jump_landing, end_hex, prone) * breaks) + (5 if end_hex else 2) * (1 - breaks)
    return 0.0


def hazardous_liquid_hazard(mover, label, terrain_map, prone=None):
    """calcHazardousLiquidHazard: 3 average damage x the destruction factor
    / exposed armor - the legs, or all of it when prone or in water deeper
    than 1."""
    dmg = max(3.0, 2.0 / 3.0)
    if (mover.prone if prone is None else prone) or water.depth_at(label, terrain_map) > 1:
        exposed = _total_armor(mover)
    else:
        exposed = _leg_armor(mover)
    return round(UNIT_DESTRUCTION_FACTOR * (dmg / max(exposed, 1)))


def _armor_bias(mech):
    """FacingDiffCalculator.getBiasTowardsFacing: +1 if the left side (arm,
    leg, torso) has more armor left, -1 if the right does."""
    def side(names):
        total = 0
        for name in names:
            loc = princess_fire._location_name(mech, name)
            if loc in mech.locations and not mech.locations[loc]["destroyed"]:
                total += max(0, mech.locations[loc]["armor"])
        return total
    left = side(("Left Arm", "Left Leg", "Left Torso"))
    right = side(("Right Arm", "Right Leg", "Right Torso"))
    return 1 if left > right else (-1 if right > left else 0)


# Coords.direction from a hex to itself: radian() returns 1.5 pi when the two centres share a y, which rounds
# to direction 5 (NW). Our facings are numbered as MegaMek's (0 = N, clockwise).
SAME_HEX_DIRECTION = 5


def direction(from_xy, to_xy):
    """MegaMek Coords.direction: the facing from one hex toward another; SAME_HEX_DIRECTION when they are
    the same hex (2026-10-29: a spot on the enemies' median point raised here before)."""
    return SAME_HEX_DIRECTION if from_xy == to_xy else combat._direction_facing(from_xy, to_xy)


def facing_diff(o, enemy_xy, bias):
    desired = (direction(o.hex_xy, enemy_xy) + bias) % 6
    diff = min((o.facing - desired) % 6, (desired - o.facing) % 6)
    return max(0, diff - ALLOW_FACING_TOLERANCE)


def _kick_potential(attacker, a_xy, a_label, a_facing, a_amm, target, t_xy, t_label, target_tmm, target_prone,
                    terrain_map):
    """calculateKickDamagePotential: P(hit) x damage of a kick (the first leg
    the project offers), if it hits more often than not, else 0."""
    import INTEGRATION__physical as physical
    levels = terrain_map["hexes"]
    opts = physical.options_at(attacker, a_xy, a_facing, levels[a_label]["level"], t_xy, levels[t_label]["level"],
                               target_prone, frozenset(), arcs.current_action(attacker),
                               is_superheavy(target))
    kicks = opts.get("kick")
    if not kicks:
        return 0.0
    los_mod = geo_cache.los(a_xy, t_xy, terrain_map, 2, 1 if target_prone else 2).modifier
    base = physical.base_tn(attacker, a_amm, target_tmm, los_mod,
                            attack_resolution.prone_target_modifier(target, 1) if target_prone else 0)
    kick = kicks[-1]                               # PhysicalAttackType.RIGHT_KICK: the right leg if it can
    p = hit_probability(base + kick["mod"])
    return p * kick["damage"] if p > KICK_THRESHOLD else 0.0


# =============================================================================
# ===========================  THE CHOICE  ====================================
# =============================================================================
def choose(mover, other, terrain_map, battle_rng, moves_first, standup_mp=None, entry_edge=None):
    """Princess's end-of-movement pick. Same arguments and return as
    movement_selection.choose: (pick, note). `other` is the nearest enemy; as in BasicPathRanker.rankPath the
    unit weighs every enemy on the board and its friends (INTEGRATION__princess_group)."""
    import INTEGRATION__princess_group as princess_group
    import INTEGRATION__forces as forces
    if other.hex is None:
        # No enemy on the board yet: Princess would rank toward the board center; this
        # project heads for the enemy's home edge, as Gladiator does.
        return movement_selection.choose(mover, other, terrain_map, battle_rng, moves_first,
                                         standup_mp=standup_mp, entry_edge=entry_edge)
    group = princess_group.Group(mover, other, forces.battle() or [mover, other], moves_first)
    with timing.section("reachable spots"):
        options = movement_selection.reduced_options(mover, terrain_map,
                                                     exclude_hex=movement_selection.occupied_hexes(mover, other),
                                                     standup_mp=standup_mp, entry_edge=entry_edge)
    moved = group.has_moved(other)                            # evaluateAsMoved
    fire_control = princess_fire.FireControl(guess=True)
    prepared, estimate = None, None
    with timing.section("Princess path ranking"), weapon_selection.fire_control(fire_control):
        for foe in group.foes:
            if not princess_group.can_matter(mover, foe):
                continue                                          # too far for either side to reach the other
            ev = ranged_combat.MoveEvaluator(mover, foe, terrain_map)
            ev.mover_physical = ev.defender_physical = False      # kicks are priced below, Princess's way
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
            estimate = {_key(o): (0.0, 0.0, 0.0) for o in prepared}
    paths = ranged_combat.PathBook(mover, terrain_map, standup_mp, entry_edge)
    return _rank(mover, group, prepared, estimate, terrain_map, standup_mp is None, moved, paths)


def _moved_estimates(mover, other, prepared, ev, terrain_map):
    """{option key: (my firing, my physical, their damage)} - evaluateMovedEnemy."""
    cands = {(c.hex, c.facing, c.mode, c.fc): c
             for c in ev.evaluate(other.hex, other.facing, other.move_fc, other.move_mode, other.mp_spent, prepared)}
    enemy_xy = hex_geometry.parse_hex_label(other.hex)
    other_facing = hex_geometry.compass_to_facing(other.facing)
    other_tmm = attack_resolution._target_tmm(other)
    kicks_back = not (other.shutdown or other.prone or is_immobile(other))
    out = {}
    for o in prepared:
        c = cands.get((o.label, o.facing_compass, o.mode, o.fc))
        mine, theirs = (c.dealt, c.received) if c is not None else (0.0, 0.0)
        physical_mine = 0.0
        if hex_distance(o.hex_xy, enemy_xy) <= 1:
            if kicks_back:
                theirs += _kick_potential(other, enemy_xy, other.hex, other_facing, combat.MODE_TO_AMM[other.move_mode],
                                          mover, o.hex_xy, o.label, o.tmm, False, terrain_map)
            physical_mine = _kick_potential(mover, o.hex_xy, o.label, o.facing, o.amm, other, enemy_xy, other.hex,
                                            other_tmm, other.prone, terrain_map)
        out[_key(o)] = (mine, physical_mine, theirs)
    return out


def _unmoved_estimates(mover, other, prepared, terrain_map):
    """{option key: (my firing, my physical, their damage)} - evaluateUnmovedEnemy."""
    return {k: (mine, 0.0, theirs + flank) for k, (mine, theirs, flank) in
            unmoved_parts(mover, other, prepared, terrain_map).items()}


def unmoved_parts(mover, other, prepared, terrain_map):
    """{option key: (my damage, its weapon damage, its flank kick)} - the parts
    of evaluateUnmovedEnemy (the modern ranker discounts the first two)."""
    reach = movement_selection._opponent_options(other, terrain_map)
    area = ConvexBoardArea([mm((x, y)) for x, y, *_ in reach])
    potential = {(mm((x, y)), f) for x, y, f, *_ in reach}
    can_twist = len(arcs.twist_offsets(mover)) > 1           # canChangeSecondaryFacing
    kick = math.ceil(other.mass / 5.0) * UNMOVED_DAMAGE_DISCOUNT
    mine_at, theirs_at = {}, {}
    out = {}
    for o in prepared:
        here = mm(o.hex_xy)
        f = o.facing
        rng = mm_distance(area.closest_to(here), here)
        if rng not in mine_at:
            mine_at[rng] = princess_fire.max_damage_at_range(mover, rng) * UNMOVED_DAMAGE_DISCOUNT
            theirs_at[rng] = princess_fire.max_damage_at_range(other, rng) * UNMOVED_DAMAGE_DISCOUNT
        behind = mm(_neighbor(o.hex_xy, f + 3))
        left_flank = mm(_neighbor(o.hex_xy, f + 2))
        right_flank = mm(_neighbor(o.hex_xy, f + 4))
        spread = (2, 4) if can_twist else (1, 5)
        left = HexLine(behind, (f + spread[0]) % 6)
        right = HexLine(behind, (f + spread[1]) % 6)
        mine = mine_at[rng] if (left.judge_area(area) > 0 and right.judge_area(area) < 0) else 0.0
        theirs = theirs_at[rng]
        flank_kick = 0.0
        flank = ((behind, f), (behind, (f + 1) % 6), (behind, (f + 5) % 6),
                 (left_flank, f), (left_flank, (f + 4) % 6), (left_flank, (f + 5) % 6),
                 (right_flank, f), (right_flank, (f + 1) % 6), (right_flank, (f + 2) % 6))
        if any(combo in potential for combo in flank):
            flank_kick = kick
        out[_key(o)] = (mine, theirs, flank_kick)
    return out


def _key(o):
    return o.label, o.facing, o.mode, o.fc, o.mp_spent


def _foes_note(group, moved):
    """"enemy moved" for a duel (the form of every earlier log), "3 enemies, nearest still to move" for a battle."""
    state = "moved" if moved else "still to move"
    return f"enemy {state}" if len(group.foes) == 1 else f"{len(group.foes)} enemies, nearest {state}"


def _rank(mover, group, prepared, estimate, terrain_map, psr_applies, moved, paths=None):
    fall_shame = princess_fire.setting("fall_shame")
    bravery = princess_fire.setting("bravery")
    aggression = princess_fire.setting("hyper_aggression")
    bias = _armor_bias(mover)
    # validatePaths: stay in (or get into) range of the closest enemy; skip too-likely falls.
    tolerance = config.PRINCESS_BEHAVIOR["fall_shame"] / 20.0 + 0.50
    max_range = movement_selection._max_range(mover)
    start = group.distance_to_enemy(hex_geometry.parse_hex_label(mover.hex)) if mover.hex is not None else None
    in_range = start is not None and max_range >= start
    success = {_key(o): success_probability(mover, o, psr_applies) for o in prepared}
    valid = []
    for o in prepared:
        if start is not None:
            d = group.distance_to_enemy(o.hex_xy)
            if (in_range and d > max_range) or (not in_range and d > start):
                continue
        if success[_key(o)] < tolerance:
            continue
        valid.append(o)
    pool = valid or prepared
    best = None
    for o in pool:
        p = success[_key(o)]
        mine, physical_mine, theirs = estimate[_key(o)]
        taken = theirs + hazards(mover, o, terrain_map, paths)
        fail = 1.0 - p
        fall_mod = fail * (UNIT_DESTRUCTION_FACTOR if fail == 1 else fall_shame)
        bravery_mod = p * (mine + physical_mine) * bravery - taken
        dist = group.distance_to_enemy(o.hex_xy)
        aggression_mod = (dist if dist else 2) * aggression
        near = group.nearest(o.hex_xy, min_distance=1)
        face_xy = (hex_geometry.parse_hex_label(near[0].hex) if near is not None and near[1] == 1
                   else group.face_target(o.hex_xy))
        facing_mod = FACING_MOD_MULTIPLIER * facing_diff(o, face_xy, bias)
        herding = group.support_mod(o.hex_xy)
        crowd = group.crowding_mod(o.hex_xy, max_range)
        utility = -fall_mod + bravery_mod - aggression_mod - herding - crowd - facing_mod
        if best is None or utility > best[0]:
            best = (utility, o, fall_mod, bravery_mod, p, mine + physical_mine, taken, aggression_mod, facing_mod,
                    herding, crowd)
    utility, o, fall_mod, bravery_mod, p, done, taken, aggression_mod, facing_mod, herding, crowd = best
    group_note = (f" - herding {herding:.2f}" if herding else "") + (f" - crowding {crowd:.2f}" if crowd else "")
    note = (f"Princess: utility {utility:.2f} = -fall {fall_mod:.2f} + bravery {bravery_mod:.2f} "
            f"[{p:.2f} x {done:.2f} x {bravery} - taken {taken:.2f}] - aggression {aggression_mod:.2f}"
            f"{group_note} - facing {facing_mod:.0f} [{len(pool)} of {len(prepared)} spots; "
            f"{_foes_note(group, moved)}]")
    return {"hex": o.label, "facing": o.facing_compass, "mode": o.mode, "fc": o.fc, "mp_spent": o.mp_spent}, note
