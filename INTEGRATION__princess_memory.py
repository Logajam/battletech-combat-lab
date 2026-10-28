"""
INTEGRATION__princess_memory.py  (NEW 2026-10-28, Claude - what Princess remembers)

MegaMek's Princess keeps a "heat map" of where its own force has been: every
time one of its ground units moves, the hex it ends in is credited with that
unit's weight; the credits fade each turn. The hottest spot - the place the
force has stood in strength - is the anchor of MUTUAL SUPPORT: a unit is pulled
toward it, its pull growing with the distance. With no hot spot yet, the anchor
is the average position of the unit's friends. Source, both Princess versions
(v0.50.07 and main 7205e4d, identical here): `HeatMap.java`, `PathRanker.rankPaths`
(allyCenter), `PathRanker.calcAllyCenter`, `Princess.updateFriendlyHeatMap`,
`Princess.calculateMoveTurn`.

  weight of a unit      max(BV - 100 x max(jump MP, walk MP), 1)
                        (HeatMap.getTeamWeightAdjustment: a fast, light unit
                        counts for less than a slow, valuable one; BV from
                        INTEGRATION__battle_value, as built, with pilot skill)
  a unit moves          its end hex gets +weight (HeatMap.updateTrackers(path));
                        a unit that stays where it is adds nothing
  end of every turn     (Princess.endOfTurnProcessing -> updateFriendlyHeatMap):
                        a hex with none of the force on it halves (rounded
                        down); a hex with one of the force on it loses 200;
                        a hex at 0 stays; once 60% of the hexes are at 0 they
                        are all dropped, and the map never keeps more than 100
  hot spot              each hex is rated by the weights of all the hexes
                        weighted by how near they are to it - the hexes of the
                        top rating are the hot spots, and the one nearest the
                        unit asking is the answer (HeatMap.getHotSpot(position,
                        true)); none while the whole map is at 0

One map per TEAM (a Princess bot is one player's units; the team is that
here). Only Princess-driven units add to it. Enemy heat maps (where the enemy
was last seen) are not kept: this project's bots see every unit on the board.

reset() starts a battle clean (the orchestrator calls it when a battle begins).
"""

from typing import Dict, List, Optional

import INTEGRATION__battle_value as battle_value
import hex_geometry  # noqa: E402 - PATHFINDER
from los import hex_distance  # noqa: E402 - PATHFINDER
from mech_state import compute_walk_mp, compute_jump_mp, is_destroyed  # noqa: E402 - MECHSIM

ACTIVITY_DECAY = -200            # Princess.initFriendlyHeatMap: setActivityDecay(-200)
MAP_TRIM_THRESHOLD = 0.6         # setMapTrimThreshold(0.6)
MAX_ENTRIES = 100                # HeatMap.MAX_TRACKER_ENTRIES
MIN_WEIGHT = 0


def unit_weight(mech) -> int:
    """HeatMap.getTeamWeightAdjustment (weightScaling 1.0)."""
    cached = getattr(mech, "_bv_built", None)
    if cached is None:
        cached = mech._bv_built = battle_value.battle_value(mech)
    speed = max(compute_jump_mp(mech), compute_walk_mp(mech))
    return max(cached - 100 * speed, 1)


class HeatMap:
    """One team's activity map: {hex label: weight}, in the order hexes were first credited."""

    def __init__(self):
        self.activity: Dict[str, int] = {}
        self.last_known: Dict[int, str] = {}                 # id(unit) -> the hex it was last credited at

    # ------------------------------------------------------------------ updates
    def unit_moved(self, mech, label: str) -> None:
        """HeatMap.updateTrackers(MovePath): the end hex gets the unit's weight."""
        self.activity[label] = self.activity.get(label, 0) + unit_weight(mech)
        self.last_known[id(mech)] = label

    def refresh_last_known(self, units) -> None:
        """HeatMap.refreshLastKnownCache: a unit that fell or was displaced is where it is now."""
        for unit in units:
            if id(unit) in self.last_known and trackable(unit):
                self.last_known[id(unit)] = unit.hex

    def age(self, units) -> None:
        """HeatMap.ageMaps (the activity map only)."""
        gone = {id(u) for u in units if is_destroyed(u)}
        for key in [k for k in self.last_known if k in gone]:
            del self.last_known[key]                          # trimLastKnownPositions
        held = {self.last_known[id(u)] for u in units if id(u) in self.last_known and trackable(u)}
        for label, weight in list(self.activity.items()):
            if weight <= MIN_WEIGHT:
                continue
            if label not in held:
                weight = max(weight // 2, MIN_WEIGHT)         # no unit of ours there: halves
            else:
                weight = max(weight + ACTIVITY_DECAY, MIN_WEIGHT)
            self.activity[label] = weight
        self._trim()

    def _trim(self) -> None:
        if self.activity:
            low = sum(1 for w in self.activity.values() if w <= MIN_WEIGHT)
            if low / len(self.activity) >= MAP_TRIM_THRESHOLD:
                self.activity = {k: w for k, w in self.activity.items() if w > MIN_WEIGHT}
        while len(self.activity) > MAX_ENTRIES:
            lowest = min(self.activity.values())
            self.activity = {k: w for k, w in self.activity.items() if w != lowest}

    # ------------------------------------------------------------------ the hot spot
    def _rating(self, label: str) -> int:
        """HeatMap.getHotSpotRating."""
        if len(self.activity) == 1:
            return next(iter(self.activity.values()))
        here = hex_geometry.parse_hex_label(label)
        distances = {k: hex_distance(here, hex_geometry.parse_hex_label(k)) for k in self.activity}
        longest = max(distances.values())
        total = sum(w * (longest - distances[k]) / longest for k, w in self.activity.items())
        return int(total // 1)

    def hot_spot(self, label: str) -> Optional[str]:
        """HeatMap.getHotSpot(position, topOnly=true): of the hexes with the top rating, the nearest to
        `label` (the first listed on a tie); None while nothing is above 0."""
        live = [k for k, w in self.activity.items() if w > MIN_WEIGHT]
        if not live:
            return None
        ratings = {k: self._rating(k) for k in live}
        top = max(ratings.values())
        here = hex_geometry.parse_hex_label(label)
        best, best_distance = None, None
        for k in live:
            if ratings[k] != top:
                continue
            d = hex_distance(here, hex_geometry.parse_hex_label(k))
            if best_distance is None or d < best_distance:
                best, best_distance = k, d
        return best


def trackable(unit) -> bool:
    """HeatMap.isTrackable (a friendly team): on the board and standing."""
    return unit.hex is not None and not is_destroyed(unit)


class TeamMemory:
    """Everything one team's Princess carries from turn to turn."""

    def __init__(self):
        self.heat = HeatMap()
        self.mean_distance_by_round: Dict[int, float] = {}    # PostureResolver's closing-rate record
        self.posture = "ATTACK"
        self.posture_round: Optional[int] = None


_TEAMS: Dict[str, TeamMemory] = {}


def reset() -> None:
    """A new battle: nothing remembered."""
    _TEAMS.clear()


def team(name: str) -> TeamMemory:
    return _TEAMS.setdefault(name, TeamMemory())


def unit_moved(mech, start_hex: Optional[str]) -> None:
    """Princess.calculateMoveTurn: a Princess unit that moved credits its end hex."""
    if getattr(mech, "bot", None) != "princess" or mech.hex is None:
        return
    if start_hex == mech.hex and not getattr(mech, "move_fc", 0):
        return                                                 # it stayed: an empty path adds nothing
    team(mech.team).heat.unit_moved(mech, mech.hex)


def end_of_turn(units) -> None:
    """Princess.endOfTurnProcessing -> updateFriendlyHeatMap, for each team that has a Princess unit."""
    teams = {u.team for u in units if getattr(u, "bot", None) == "princess"}
    for name in teams:
        mine = [u for u in units if u.team == name]
        heat = team(name).heat
        heat.refresh_last_known(mine)
        heat.age(mine)


def label_to_cols_rows(label: str):
    """"0807" -> (7, 6): MegaMek's Coords (column, row), counted from 0."""
    return int(label[:2]) - 1, int(label[2:]) - 1


def cols_rows_to_label(col: int, row: int) -> str:
    return f"{col + 1:02d}{row + 1:02d}"
