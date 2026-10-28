"""
INTEGRATION__princess_group.py  (NEW 2026-10-28, Claude - Princess's group behaviors)

What MegaMek's Princess does because it has FRIENDS and several ENEMIES, built
on the multi-unit battle (INTEGRATION__forces). A duel never needed any of it.
Daniel, 2026-10-28: items 1-5 of Pick up here 00, "As usual use Megamek as
source material where needed."

BUILT HERE
  Whom a unit fires at (Princess.getBestFiringPlan -> FireControl.
  getBestFiringPlan): MegaMek builds the best firing plan against EVERY enemy
  it can see (or can indirect-fire at) and takes the plan with the highest
  utility - so the choice of target is the plan's utility, not "nearest".
  That utility already holds the threat of the target (the log of its damage
  at range 1), the kill chance, and the OVERKILL term fed by the damage
  friends have already declared at the target (princess_fire.assigned_damage:
  a target friends are expected to destroy scores 100 x -30, so the unit turns
  to another enemy). Here: choose_target() runs each enemy through the same
  weapon choice the real declaration uses (attack_resolution.declare_attacks,
  dry=True) and keeps the best, first enemy winning a tie (MegaMek keeps the
  first plan it ranked). If no enemy can be hit, the project's usual pick
  (forces.choose_target) is returned so the log still says why nothing fires.

NOT HERE (MegaMek's own design): a plan has ONE target. Princess's ordinary
fire control never fires at secondary targets (Core p.64, +1) - that is
MultiTargetFireControl, used only for crews with multi-tasker / multi-trac,
which this project doesn't model. See PROJECT_MAP Section 6.
"""

import math

import INTEGRATION__config as config
import INTEGRATION__forces as forces
import INTEGRATION__princess_memory as princess_memory
import hex_geometry  # noqa: E402 - PATHFINDER
from los import hex_distance  # noqa: E402 - PATHFINDER
from mech_state import compute_walk_mp, compute_jump_mp, is_immobile  # noqa: E402 - MECHSIM


def candidates(attacker, units):
    """The enemies on the board, in roster order (FireControl.
    getTargetableEnemyEntities; the line of sight test is the dry run's)."""
    return [e for e in forces.enemies_of(attacker, units) if forces.distance(attacker, e) is not None]


def choose_target(attacker, units, terrain_map):
    """The enemy whose firing plan has the highest utility for this attacker
    now (None if no enemy is left on the board)."""
    import INTEGRATION__attack_resolution as attack_resolution
    foes = candidates(attacker, units)
    fallback = forces.choose_target(attacker, units, terrain_map)
    if len(foes) < 2:
        return fallback
    best = None
    for foe in foes:
        got = attack_resolution.declare_attacks(attacker, foe, terrain_map, attack_resolution.SideReport(), dry=True)
        if got is not None and (best is None or got[0] > best[0]):
            best = (got[0], foe)
    return best[1] if best else fallback


# =============================================================================
# ===========================  THE MOVEMENT PICTURE  ==========================
# =============================================================================
# What the movement ranker (BasicPathRanker.rankPath) knows because there is a
# battle around the unit, not just one enemy: every enemy on the board, the
# unit's friends, and where the force has been. With ONE enemy and no friends
# every number here is the old duel's - nothing changes for a duel except the
# remembered "hot spot" (see INTEGRATION__princess_memory).
MUTUAL_SUPPORT_VALUES = (0.1, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0)   # BehaviorSettings (both versions)
DEFAULT_ENEMIES_TO_FACE = 4                       # BehaviorSettings.DEFAULT_NUMBER_OF_ENEMIES_TO_CONSIDER_FACING


def _java_round(x):
    return int(math.floor(x + 0.5))


def _cols_rows(xy):
    return princess_memory.label_to_cols_rows(hex_geometry.hex_label(*xy))


def _xy(col, row):
    return hex_geometry.parse_hex_label(princess_memory.cols_rows_to_label(col, row))


def geometric_median(points):
    """Coords.median: Weiszfeld's algorithm on (column, row), truncated to a hex
    (one point is itself). points: [(col, row)]."""
    if not points:
        return None
    if len(points) == 1:
        return points[0]
    n = len(points)
    cx = sum(p[0] for p in points) / n
    cy = sum(p[1] for p in points) / n
    for _ in range(1000):
        num_x = num_y = den = 0.0
        for px, py in points:
            dist = math.hypot(px - cx, py - cy)
            if dist < 1e-15:
                return (px, py)
            w = 1.0 / dist
            num_x += px * w
            num_y += py * w
            den += w
        new_x, new_y = num_x / den, num_y / den
        shift = math.hypot(cx - new_x, cy - new_y)
        cx, cy = new_x, new_y
        if shift < 1e-7:
            break
    return (int(cx), int(cy))


def can_matter(mover, foe):
    """False when the enemy is so far off that neither side could move and shoot at the other: its estimates
    would be all zero (a speed shortcut; the enemy still counts for distances and facing)."""
    import INTEGRATION__movement_selection as movement_selection
    reach_mover = max(compute_jump_mp(mover), int(math.ceil(compute_walk_mp(mover) * 1.5))) \
        + movement_selection._max_range(mover)
    reach_foe = max(compute_jump_mp(foe), int(math.ceil(compute_walk_mp(foe) * 1.5))) \
        + movement_selection._max_range(foe)
    if mover.hex is None or foe.hex is None:
        return True
    gap = hex_distance(hex_geometry.parse_hex_label(mover.hex), hex_geometry.parse_hex_label(foe.hex))
    return gap <= reach_mover + reach_foe + 2


def combine_estimates(a, b):
    """BasicPathRanker.rankPath over several enemies: of my firing damage and of my physical damage the best
    (a unit may kick one enemy and shoot another); the damage taken adds up over all of them."""
    return {k: (max(a[k][0], b[k][0]), max(a[k][1], b[k][1]), a[k][2] + b[k][2]) for k in a}


class Group:
    """The battle as one Princess unit sees it while it picks a move."""

    def __init__(self, mover, other, units, moves_first):
        self.mover, self.units = mover, units
        foes = [f for f in forces.enemies_of(mover, units) if f.hex is not None]
        if other is not None and other.hex is not None and all(f is not other for f in foes):
            foes.append(other)
        self.foes = foes
        self.other, self.moves_first = other, moves_first
        self.friends = [f for f in forces.friends_of(mover, units) if f.hex is not None]
        behavior = config.PRINCESS_BEHAVIOR
        self.support_value = MUTUAL_SUPPORT_VALUES[max(0, min(10, int(behavior.get("mutual_support", 5))))]
        self.anti_crowding = int(behavior.get("anti_crowding", 0))
        self.enemies_to_face = max(1, int(behavior.get("facing_enemies", DEFAULT_ENEMIES_TO_FACE)))
        self._anchor = self._find_anchor()
        self.group_on = config.PRINCESS_GROUP

    # ------------------------------------------------------------------ who has moved
    def has_moved(self, foe):
        """Princess.evaluateAsMoved: the enemy has taken its movement this turn, or can't move."""
        if foe is self.other:
            return (not self.moves_first) or is_immobile(foe)
        return bool(getattr(foe, "moved_this_turn", False)) or is_immobile(foe)

    def _adjusted(self, foe, raw):
        """findClosestEnemy: an enemy still to move is counted as farther, by its walking MP."""
        return raw + (0 if self.has_moved(foe) else compute_walk_mp(foe))

    # ------------------------------------------------------------------ the nearest enemy
    def nearest(self, spot_xy, min_distance=0):
        """(enemy, raw distance) - PathRanker.findClosestEnemy; None if there is none."""
        best = None
        for foe in self.foes:
            raw = hex_distance(spot_xy, hex_geometry.parse_hex_label(foe.hex))
            if raw < min_distance:
                continue
            adjusted = self._adjusted(foe, raw)
            if best is None or adjusted < best[0]:
                best = (adjusted, foe, raw)
        return None if best is None else (best[1], best[2])

    def distance_to_enemy(self, spot_xy):
        got = self.nearest(spot_xy)
        return None if got is None else got[1]

    def face_target(self, spot_xy):
        """FacingDiffCalculator.selectOneCoordsToFace: the closest enemy if the spot is next to it, else the
        median of the closest few enemies, else (no enemy) None."""
        got = self.nearest(spot_xy, min_distance=1)
        if got is not None and got[1] == 1:
            return hex_geometry.parse_hex_label(got[0].hex)
        ranked = sorted(self.foes, key=lambda f: max(0, self._adjusted(
            f, hex_distance(spot_xy, hex_geometry.parse_hex_label(f.hex)))))
        points = [_cols_rows(hex_geometry.parse_hex_label(f.hex)) for f in ranked[:self.enemies_to_face]]
        median = geometric_median(points)
        return None if median is None else _xy(*median)

    # ------------------------------------------------------------------ mutual support
    def _find_anchor(self):
        """PathRanker.rankPaths: the force's hot spot nearest the mover, else the friends' average position
        (calcAllyCenter - none when there are no friends)."""
        mover = self.mover
        if mover.hex is None or not config.PRINCESS_GROUP:
            return None
        spot = princess_memory.team(mover.team).heat.hot_spot(mover.hex)
        if spot is not None:
            return hex_geometry.parse_hex_label(spot)
        if not self.friends:
            return None
        cols = [_cols_rows(hex_geometry.parse_hex_label(f.hex)) for f in self.friends]
        col = _java_round(sum(c for c, _ in cols) / len(cols))
        row = _java_round(sum(r for _, r in cols) / len(cols))
        return _xy(col, row)

    def support_mod(self, spot_xy):
        """BasicPathRanker.calculateMutualSupportMod: the distance to the anchor x the mutual support value."""
        if self._anchor is None:
            return 0.0
        return hex_distance(spot_xy, self._anchor) * self.support_value

    # ------------------------------------------------------------------ crowding
    def crowding_mod(self, spot_xy, max_range):
        """BasicPathRanker.calculateCrowdingTolerance (default 0 = off): units of both sides near the spot."""
        anti = self.anti_crowding
        if anti == 0 or not config.PRINCESS_GROUP:
            return 0.0
        factor = 10.0 / (11 - anti)
        friend_distance = math.ceil(anti * 1.3)
        closing_distance = math.ceil(max(3.0, max_range * 0.6))
        # getFriendEntities includes the moving unit itself, standing where it started
        crowd_friends = sum(1 for f in self.friends + [self.mover]
                            if hex_distance(spot_xy, hex_geometry.parse_hex_label(f.hex)) <= friend_distance)
        crowd_enemies = sum(1 for f in self.foes
                            if hex_distance(spot_xy, hex_geometry.parse_hex_label(f.hex)) <= closing_distance)
        return factor * (crowd_friends + crowd_enemies)


# =============================================================================
# ===========================  POSTURE (the force's, once a round)  ===========
# =============================================================================
CLOSING_THRESHOLD_HEXES_PER_ROUND = 0.5
DEFEND_EXIT_THRESHOLD_HEXES_PER_ROUND = 0.1
CLOSING_WINDOW_ROUNDS = 3
ATTACK, DEFEND = "ATTACK", "DEFEND"


def force_posture(mover, group):
    """PostureResolver.resolveAuto: one call a round (the first Princess unit to move) decides for the whole
    team - from the enemy's mean distance to the centre of the team's own force, against where it stood a few
    rounds ago. Kept in the team's memory."""
    memory = princess_memory.team(mover.team)
    round_ = getattr(mover, "turn_number", 0)
    if memory.posture_round == round_:
        return memory.posture
    memory.posture_round = round_
    own = [u for u in forces.standing(group.units) if u.team == mover.team and u.hex is not None]
    foes = group.foes
    if not own or not foes:
        memory.posture = ATTACK
        return ATTACK
    cols = [_cols_rows(hex_geometry.parse_hex_label(u.hex)) for u in own]
    centre = _xy(_java_round(sum(c for c, _ in cols) / len(cols)), _java_round(sum(r for _, r in cols) / len(cols)))
    distances = [hex_distance(centre, hex_geometry.parse_hex_label(f.hex)) for f in foes]
    mean = sum(distances) / len(distances)
    by_round = memory.mean_distance_by_round
    by_round[round_] = mean
    for old in [r for r in by_round if r < round_ - CLOSING_WINDOW_ROUNDS]:
        del by_round[old]
    baseline = next((r for r in range(round_ - CLOSING_WINDOW_ROUNDS, round_) if r in by_round), round_)
    if baseline == round_:
        memory.posture = ATTACK
        return ATTACK
    closing = (by_round[baseline] - mean) / (round_ - baseline)
    if memory.posture == DEFEND:
        memory.posture = DEFEND if closing > DEFEND_EXIT_THRESHOLD_HEXES_PER_ROUND else ATTACK
    else:
        memory.posture = DEFEND if closing >= CLOSING_THRESHOLD_HEXES_PER_ROUND else ATTACK
    return memory.posture
