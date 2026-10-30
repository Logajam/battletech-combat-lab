"""
INTEGRATION__legate.py  (NEW 2026-10-28, Claude - Legate, the battlefield-keeping layer)

Daniel, 2026-10-28: "making gladiator less myopic ... a multi-unit bot layer at the start of the
movement phase. I call this layer 'Legate'; it's in charge of keeping tabs on the battlefield."
Gladiator (the project's own bot) plans a move against ONE foe. Legate gives it the rest of the
enemy force. Config: `config.LEGATE` (off = the old one-foe planning, byte for byte).

WHAT LEGATE DOES, each Movement Phase, for each side that has a Gladiator unit and 2+ enemies
  1. ESTIMATE (plan_turn). Daniel's IF/THEN run for every unit at once, up to config.LEGATE_ITERATIONS
     rounds. Round 0: everyone holds still. Each round the enemy units answer first, then the asking
     side's own units answer (the back and forth of the two-'Mech IF/THEN, many against many):
       - a unit looks at its reachable spots (the grid search, as a Gladiator's own search) and scores
         each with the PICKER score Gladiator uses (the "lifetime" objective), but against the WHOLE
         opposing force standing where it is estimated to be: damage taken = the SUM of what every
         opposing unit could deal to that spot, damage dealt = the MAX over the opposing units;
       - two units that want the same hex: the higher score keeps it, the other takes its next best
         choice, and that can displace a third unit that was sitting in it, and so on (a cascade, settled
         before the next round - `resolve`);
       - a unit that picks a hex it has already tried is in a loop: it is LOCKED at its best-scoring
         attempt and stays there, for everyone else's choices too.
     The enemy units' best attempts are the estimate of where they will move this turn.
  2. FOE (foe_for). A Gladiator plans against the enemy that would score highest against it - each
     enemy at its estimated spot (its real spot once it has moved), against this unit where it stands -
     among the enemies that have NOT moved yet; if all have, the most threatening of them.
  3. THE MOVE (movement_selection._choose_normal, through `Extras`). The unit runs its usual search
     against that foe, and each spot is also scored against every OTHER enemy at its estimated spot (its
     real spot once moved): damage taken adds up over all of them, damage dealt is the best over all.
  4. FIRE. Unchanged: INTEGRATION__forces.choose_target already looks at every enemy once positions are
     final (in sight, bears, nearest).

PLACEHOLDERS (Daniel: "This will change later"): the damage a single unit would really take THIS turn
when the enemy force concentrates fire is each enemy's damage times its share (now_share below). Its FUTURE share is estimated (fire_share,
config.LEGATE_FIRE_SPLIT, 2026-10-29): the old "every enemy shoots only me" made a unit's life look ~3
turns long against 12 enemies, so bad trades scored well and lights dived in alone (Change Record).
THIS turn's damage can take the same share (now_share, config.LEGATE_SPLIT_THIS_TURN, 2026-10-30).
TO DO (Daniel): Legate reads the map and finds tactically useful terrain; the concentrated-fire
estimate; a better score for the estimate (PROJECT_MAP Section 0, Pick up here).

Speed: estimates are cached per (unit, foe, foe's estimated spot), so once units settle later rounds
are cheap; timing sections "Legate estimate" and "Legate extras" show the cost.
"""

import contextlib
from typing import Dict, List, Optional, Tuple

import INTEGRATION__config as config
import INTEGRATION__forces as forces
import INTEGRATION__future_damage as future_damage
import INTEGRATION__movement_selection as movement_selection
import INTEGRATION__ranged_combat as ranged_combat
import INTEGRATION__timing as timing
import hex_geometry  # noqa: E402 - PATHFINDER
from los import hex_distance  # noqa: E402 - PATHFINDER
from mech_state import is_immobile  # noqa: E402 - MECHSIM

State = Tuple[str, str, int, str, int]            # hex label, facing compass, hexes moved, mode, MP spent

_PLANS: Dict[str, Dict[int, State]] = {}          # team -> {id(enemy unit): its estimated end state}
_OWN: Dict[str, Dict[int, State]] = {}            # team -> {id(own unit): its estimated end state} (herding)
_FRIEND_DMG: Dict[tuple, float] = {}              # (id(unit), its state, id(enemy), enemy state) -> damage on it
_RATES: Dict[Tuple[int, int], Tuple[float, float]] = {}   # (id(a), id(b)) -> (a's, b's) future damage rates
_SHARES: Dict[Tuple[int, int], float] = {}        # (id(foe), id(me)) -> this turn's share (now_share)


def reset() -> None:
    """A new battle: no plan, no cached rates."""
    _PLANS.clear()
    _OWN.clear()
    _RATES.clear()
    _SHARES.clear()
    _FRIEND_DMG.clear()


def end_phase() -> None:
    """The Movement Phase is over: the plans are spent (the rates are valid until the next heat phase's
    damage, so they go too)."""
    _PLANS.clear()
    _RATES.clear()
    _SHARES.clear()


def _key(o) -> Tuple[str, str, str, int, int]:
    return (o.label, o.facing_compass, o.mode, o.fc, o.mp_spent)


def _state_of(o) -> State:
    return (o.label, o.facing_compass, o.fc, o.mode, o.mp_spent)


def _hold(mech) -> State:
    return (mech.hex, mech.facing, 0, "Stand Still", 0)


def _real_state(mech) -> State:
    """Where a unit that has moved this turn really is."""
    return (mech.hex, mech.facing, mech.move_fc, mech.move_mode, mech.mp_spent)


def _xy(label):
    return hex_geometry.parse_hex_label(label)


def can_matter(mover, foe) -> bool:
    """Can this foe matter to the mover's move at all (the same shortcut Princess's group code uses)?"""
    import INTEGRATION__princess_group as princess_group
    return princess_group.can_matter(mover, foe)


# =============================================================================
# ===========================  THE PICKER SCORE  ==============================
# =============================================================================
def pair_rates(a, b) -> Tuple[float, float]:
    """(a's future damage on b, b's on a) per turn, blended with the battle so far - what
    movement_selection._Lifetime reads for a pair. Cached for the phase."""
    got = _RATES.get((id(a), id(b)))
    if got is None:
        mine, theirs = future_damage.future_damage(a, b), future_damage.future_damage(b, a)
        k = config.MOVEMENT_LIFETIME_HISTORY_K
        if k is not None:
            mine, theirs = movement_selection._blend_with_history(k, mine, theirs, a, b)
        got = _RATES[(id(a), id(b))] = (mine, theirs)
        _RATES[(id(b), id(a))] = (theirs, mine)
    return got


def fire_share(foe, me) -> float:
    """The share of `foe`'s future fire that lands on `me` (config.LEGATE_FIRE_SPLIT, 2026-10-29 -
    Daniel: Gladiator should know "the likelyhood that fire will be split by its rules"):
      "none"         - all of it (the original MultiLifetime: every enemy shoots only me);
      "proportional" - my slice of what the foe could deal across my team: its damage a turn on me
                       over the sum on every standing teammate it can matter to, me included. A
                       stand-in for the enemy's targeting rule (Princess takes the plan with the best
                       utility, mostly expected damage), so a unit the enemy hurts more draws more."""
    policy = config.LEGATE_FIRE_SPLIT
    if policy == "none":
        return 1.0
    if policy != "proportional":
        raise ValueError(f"Unknown LEGATE_FIRE_SPLIT {policy!r} ('proportional' or 'none')")
    mine = pair_rates(foe, me)[0]
    if mine <= 0:
        return 0.0
    team = [u for u in forces.standing(forces.battle()) if u.team == me.team and u.hex is not None
            and (u is me or can_matter(u, foe))]
    if not any(u is me for u in team):
        team.append(me)
    total = sum(pair_rates(foe, u)[0] for u in team)
    return mine / total if total > 0 else 1.0


def now_share(foe, me) -> float:
    """The share of `foe`'s fire THIS turn counted on `me` in a move score: fire_share with
    config.LEGATE_SPLIT_THIS_TURN (2026-10-30), else 1 (every enemy that can reach the spot shoots it).
    Cached for the phase."""
    if not config.LEGATE_SPLIT_THIS_TURN:
        return 1.0
    got = _SHARES.get((id(foe), id(me)))
    if got is None:
        got = _SHARES[(id(foe), id(me))] = fire_share(foe, me)
    return got


class MultiLifetime:
    """movement_selection._Lifetime against several foes (Daniel, 2026-10-28): the damage taken is the
    SUM over the foes and the damage dealt the MAX, so the future rates are too: my future damage is
    the best over the foes, theirs is the sum of every foe's - each foe's times the share of its fire
    I can expect to draw (fire_share; LEGATE_FIRE_SPLIT "none" = all of it). Called as
    objective(dealt, received, dealt_mult, received_mult, extras) like the others."""

    def __init__(self, me, foes):
        floor = config.MOVEMENT_LIFETIME_FUTURE_FLOOR
        self.hp = movement_selection.effective_hp(me)
        rates = [pair_rates(me, f) for f in foes]
        self.mine = max([floor] + [m for m, _ in rates])
        self.theirs = max(floor, sum(t * fire_share(f, me) for (_, t), f in zip(rates, foes)))

    def __call__(self, dealt, received, dealt_mult, received_mult, extras):
        left = self.hp - (received * received_mult + extras)
        return dealt * dealt_mult + (left / self.theirs * self.mine if left > 0 else 0.0)

    def note(self, dealt, received, dealt_mult, received_mult, extras, how):
        score = self(dealt, received, dealt_mult, received_mult, extras)
        return (f"score {score:.3f} = dealt {dealt:.2f} x{dealt_mult:.2f} + (HP {self.hp:.1f} - received "
                f"{received:.2f} x{received_mult:.2f} - PSR {extras:.2f}{' with the team term' if config.LEGATE_TEAM_VALUE else ''}) "
                f"/ enemies' future on me {self.theirs:.2f} "
                f"x my best future {self.mine:.2f} [{how}]")


def objective_for(me, foes):
    """The picker score for `me` (a movement_selection._Side) against a set of foe mechs."""
    if config.MOVEMENT_OBJECTIVE == "lifetime" and foes:
        return MultiLifetime(me.mech, foes)
    return movement_selection._RATIO


# =============================================================================
# ===========================  ONE UNIT, MODELED  =============================
# =============================================================================
@contextlib.contextmanager
def _blocking(mech, units):
    """The mech's ground steps can't enter a mobile enemy's hex while its options are built (as in
    orchestrator._phase_movement)."""
    mech.blocked_hex = forces.blocked_xy(mech, units)
    try:
        yield
    finally:
        mech.blocked_hex = None


class _Unit:
    """One unit as the estimate sees it: its reachable spots, where it is estimated to end, and what
    it has tried."""

    def __init__(self, mech, units, terrain_map, lite=False, side=None):
        self.mech, self.terrain_map = mech, terrain_map
        self.side = side or movement_selection._Side(mech)
        if lite:                                       # only to score against / be scored against
            self.prepared = []
        else:
            with _blocking(mech, units):
                options = movement_selection._opponent_options(mech, terrain_map)
            self.prepared = ranged_combat.prepare_options(mech, options)
        self.state: State = _hold(mech)               # where it is taken to stand right now
        self.locked = False
        self.tried = set()                            # hexes it has picked in earlier rounds
        self.best: Optional[Tuple[float, State]] = None   # its best-scoring attempt
        self._evaluators: Dict[int, object] = {}
        self._rows: Dict[tuple, dict] = {}            # (id(foe), foe's state) -> {key: candidate or None}

    def evaluator(self, foe):
        ev = self._evaluators.get(id(foe))
        if ev is None:
            ev = self._evaluators[id(foe)] = ranged_combat.MoveEvaluator(self.mech, foe, self.terrain_map)
        return ev

    def rows(self, foe, foe_state: State, states) -> dict:
        """{state key: MovementCandidate} for each of `states` against `foe` standing at foe_state - a
        state with no line of sight is None. Remembered while the foe stays there."""
        memo = self._rows.setdefault((id(foe), foe_state), {})
        missing = [o for o in states if _key(o) not in memo]
        if missing:
            got = {(c.hex, c.facing, c.mode, c.fc, c.mp_spent): c
                   for c in self.evaluator(foe).evaluate(foe_state[0], foe_state[1], foe_state[2], foe_state[3],
                                                         foe_state[4], missing)}
            for o in missing:
                memo[_key(o)] = got.get(_key(o))
        return memo


def combine(me: "_Unit", entries, states, objective):
    """Score each of `states` for `me` against several foes: entries = [(foe _Unit-like with .side and
    .mech, foe state)]. Damage taken adds up over the foes, damage dealt is the best (both with the
    exposure factors); a state with no line of sight to any foe is left out. Rows (score, state, (dealt,
    received)) in the order of `states`."""
    per_foe = [(foe, me.rows(foe.mech, st, states)) for foe, st in entries]
    out = []
    for o in states:
        dealt = received = 0.0
        seen = False
        for foe, rows in per_foe:
            cand = rows.get(_key(o))
            if cand is None:
                continue
            seen = True
            dealt = max(dealt, cand.dealt * foe.side.exposure[cand.side_on_defender])
            received += cand.received * me.side.exposure[cand.side_on_mover] * now_share(foe.mech, me.mech)
        if seen:
            out.append((objective(dealt, received, 1.0, 1.0, me.side.psr_for(o)), o, (dealt, received)))
    return out


# =============================================================================
# ===========================  THE ESTIMATE  ==================================
# =============================================================================
def resolve(proposals: List[Tuple[object, list]], locked: Dict[object, str]) -> Dict[object, Tuple[float, object]]:
    """Give every unit a spot: proposals = [(unit, [(score, state), ...best first, one per hex])];
    locked = {unit: hex it is fixed at}. Two units that want a hex: the higher score keeps it (a tie:
    whoever was there first), the other goes down its list, and the one it displaces does the same -
    a cascade that ends because every list only moves forward. A unit with nothing left stays unplaced
    (not in the result). Returns {unit: (score, state)}."""
    reserved = set(locked.values())
    pointer = {id(u): 0 for u, _ in proposals}
    lists = {id(u): rows for u, rows in proposals}
    holder: Dict[str, object] = {}                     # hex -> unit
    placed: Dict[int, Tuple[float, object]] = {}
    pending = [u for u, _ in proposals]
    while pending:
        unit = pending.pop(0)
        rows = lists[id(unit)]
        while pointer[id(unit)] < len(rows):
            score, state = rows[pointer[id(unit)]]
            label = state.label
            if label in reserved:
                pointer[id(unit)] += 1
                continue
            current = holder.get(label)
            if current is None:
                holder[label] = unit
                placed[id(unit)] = (score, state)
                break
            if score > placed[id(current)][0]:
                holder[label] = unit
                placed[id(unit)] = (score, state)
                del placed[id(current)]
                pointer[id(current)] += 1
                pending.append(current)
                break
            pointer[id(unit)] += 1
    return {u: placed[id(u)] for u, _ in proposals if id(u) in placed}


def _proposals(unit: _Unit, opposing: List[_Unit], taken: set, objective_cache) -> List[Tuple[float, object]]:
    """The unit's spots, best first, one per hex: the grid search scored against every opposing unit
    where it is estimated to stand (the unit that can't move offers only where it is)."""
    prepared = [o for o in unit.prepared if o.label not in taken]
    if not prepared:
        return []
    entries = [(f, f.state) for f in opposing if can_matter(unit.mech, f.mech)]
    rows: list = []
    if entries and len(prepared) > 1:
        objective = objective_cache(unit)
        rows = movement_selection._grid_search(
            prepared, lambda states: combine(unit, entries, states, objective),
            movement_selection._search_start(unit.mech, prepared), config.MOVEMENT_SEARCH_STARTS)
    if not any(r[2][0] > 0 for r in rows):
        # Nothing it can hit from any spot it looked at: it closes on the nearest opposing unit.
        if opposing:
            here = _xy(unit.mech.hex)
            target_xy = min((_xy(f.state[0]) for f in opposing), key=lambda xy: hex_distance(here, xy))
            ranked = sorted(prepared, key=lambda o: hex_distance(o.hex_xy, target_xy))
            rows = [(-1.0e6 - hex_distance(o.hex_xy, target_xy), o, (0.0, 0.0)) for o in ranked[:8]]
    best_by_hex: Dict[str, Tuple[float, object]] = {}
    for score, o, _ in rows:
        if o.label not in best_by_hex or score > best_by_hex[o.label][0]:
            best_by_hex[o.label] = (score, o)
    return sorted(best_by_hex.values(), key=lambda r: -r[0])


def _half_round(movers: List[_Unit], opposing: List[_Unit], objective_cache) -> None:
    """One side answers: every unit that is not locked picks a spot against the opposing side where it
    stands now; conflicts cascade (resolve); a unit that lands on a hex it has tried is locked at its best
    attempt (and the conflicts are settled again with that hex taken)."""
    taken = {f.state[0] for f in opposing}
    free = [u for u in movers if not u.locked]
    proposals = [(u, _proposals(u, opposing, taken, objective_cache)) for u in free]
    while True:
        locked = {u: u.state[0] for u in movers if u.locked}
        placed = resolve(proposals, locked)
        newly = []
        for u, (score, o) in placed.items():
            if o.label in u.tried:
                newly.append(u)
        if not newly:
            break
        for u in newly:
            u.locked = True
            u.state = u.best[1] if u.best is not None else u.state
        proposals = [(u, rows) for u, rows in proposals if not u.locked]
    for u, (score, o) in placed.items():
        u.tried.add(o.label)
        u.state = _state_of(o)
        if u.best is None or score > u.best[0]:
            u.best = (score, u.state)


def plan_turn(units, terrain_map) -> None:
    """The start of the Movement Phase: estimate where each side's enemies will end, for every team with a
    Gladiator unit that faces two or more enemies on the board. Stores the estimate (estimate_for)."""
    _PLANS.clear()
    _OWN.clear()
    if not config.LEGATE:
        return
    alive = forces.standing(units)
    on_board = [u for u in alive if u.hex is not None]
    if len(on_board) != len(alive):
        return                                          # somebody is still to enter the board: no plan
    for team in forces.team_names(alive):
        mine = [u for u in on_board if u.team == team]
        theirs = [u for u in on_board if u.team != team]
        if len(theirs) < 2 or not any(getattr(u, "bot", None) == "gladiator" for u in mine):
            continue
        with timing.section("Legate estimate"):
            _PLANS[team], _OWN[team] = _estimate(mine, theirs, units, terrain_map)


def _estimate(mine, theirs, units, terrain_map) -> Dict[int, State]:
    asking = [_Unit(m, units, terrain_map) for m in mine]
    enemy = [_Unit(m, units, terrain_map) for m in theirs]
    objectives: Dict[int, object] = {}

    def objective_cache(unit: _Unit):
        got = objectives.get(id(unit))
        if got is None:
            others = enemy if unit in asking else asking
            got = objectives[id(unit)] = objective_for(unit.side, [f.mech for f in others
                                                                  if can_matter(unit.mech, f.mech)])
        return got

    for _ in range(max(config.LEGATE_ITERATIONS, 0)):
        _half_round(enemy, asking, objective_cache)
        if all(u.locked for u in enemy):
            break
        _half_round(asking, enemy, objective_cache)
    # A unit that never settled takes its best attempt. (enemy estimate, own side's estimate)
    def ends(side):
        return {id(u.mech): (u.best[1] if u.best is not None else u.state) for u in side}
    return ends(enemy), ends(asking)


def friend_state(team: str, friend) -> State:
    """Where a teammate is taken to end this turn: its real spot if it has moved, else Legate's
    estimate of its own side, else where it stands."""
    if getattr(friend, "moved_this_turn", False):
        return _real_state(friend)
    return _OWN.get(team, {}).get(id(friend)) or _hold(friend)


def estimate_for(team: str, foe) -> Optional[State]:
    plan = _PLANS.get(team)
    return None if plan is None else plan.get(id(foe))


# =============================================================================
# ===========================  USING IT  ======================================
# =============================================================================
def foe_state(team: str, foe) -> State:
    """Where the mover should take this foe to be: its real spot if it has moved, else Legate's estimate,
    else where it stands."""
    if getattr(foe, "moved_this_turn", False):
        return _real_state(foe)
    return estimate_for(team, foe) or _hold(foe)


def active_for(mover, units) -> bool:
    return (config.LEGATE and getattr(mover, "bot", None) == "gladiator" and mover.team in _PLANS
            and len(forces.enemies_of(mover, units)) >= 2)


def foe_for(mover, units, terrain_map):
    """The enemy this Gladiator plans against: the one expected to score highest against it (each at
    its estimated or real spot, against the mover where it stands), among the enemies yet to move; if all
    have moved, the most threatening of them. None when Legate has nothing to say (the caller then uses
    forces.choose_foe)."""
    if not active_for(mover, units) or mover.hex is None:
        return None
    foes = [f for f in forces.enemies_of(mover, units) if f.hex is not None]
    waiting = [f for f in foes if not f.moved_this_turn]
    pool = waiting or foes
    if not pool:
        return None
    with timing.section("Legate foe choice"):
        best = None
        hold = ranged_combat.prepare_options(mover, [(*_xy(mover.hex), hex_geometry.compass_to_facing(mover.facing),
                                                      0, "Stand Still", 0)])
        side = movement_selection._Side(mover)
        for index, f in enumerate(pool):
            threat = _threat(mover, f, foe_state(mover.team, f), hold, side, terrain_map)
            rank = (-threat, forces.distance(mover, f) or 0, index)
            if best is None or rank < best[0]:
                best = (rank, f)
    return best[1]


def _threat(mover, foe, state: State, hold, side, terrain_map) -> float:
    """The foe's picker score against the mover standing still: what the foe would deal the mover and
    take back from where it is estimated to stand."""
    ev = ranged_combat.MoveEvaluator(mover, foe, terrain_map)
    got = ev.evaluate(state[0], state[1], state[2], state[3], state[4], hold)
    if not got:
        return 0.0
    cand = got[0]
    foe_side = movement_selection._Side(foe)
    dealt = cand.received * side.exposure[cand.side_on_mover]          # what the foe deals the mover
    taken = cand.dealt * foe_side.exposure[cand.side_on_defender]       # what it takes back
    mine, theirs = pair_rates(foe, mover)
    floor = config.MOVEMENT_LIFETIME_FUTURE_FLOOR
    if config.MOVEMENT_OBJECTIVE == "lifetime":
        left = movement_selection.effective_hp(foe) - taken
        return dealt + (left / max(theirs, floor) * max(mine, floor) if left > 0 else 0.0)
    return dealt / (taken + config.MOVEMENT_RATIO_EPSILON)


class Extras:
    """What a Gladiator's move scoring adds for the enemies other than its foe (movement_selection
    hooks `adjust`): each other enemy where it is believed to stand - its real spot once it has moved,
    else Legate's estimate - and the mover's picker score against all of them together."""

    def __init__(self, mover, primary, units, terrain_map, me_side):
        self.mover, self.terrain_map = mover, terrain_map
        self.others = [f for f in forces.enemies_of(mover, units)
                       if f is not primary and f.hex is not None and can_matter(mover, f)]
        self.entries = [(_Unit(f, units, terrain_map, lite=True), foe_state(mover.team, f)) for f in self.others]
        self.unit = _Unit(mover, units, terrain_map, lite=True, side=me_side)
        self.count = len(self.entries)
        self.herd = _Herd(mover, units, terrain_map) if config.LEGATE_HERDING else None
        self.cohesion = _Cohesion(mover, units) if config.LEGATE_COHESION else None
        self.primary = primary
        self.team = (_TeamFire(mover, primary, self.others, units, terrain_map, me_side)
                     if config.LEGATE_TEAM_VALUE and config.MOVEMENT_OBJECTIVE == "lifetime" else None)
        self._team_cost: Dict[tuple, float] = {}

    def objective(self, primary, me_side):
        return objective_for(me_side, [primary] + self.others)

    def prefetch(self, states) -> None:
        """Score a batch of states against every other enemy in one go (the evaluator is per foe)."""
        with timing.section("Legate extras"):
            for foe, st in self.entries:
                self.unit.rows(foe.mech, st, states)

    def adjust(self, o, dealt, received, dealt_mult, received_mult):
        """The mover's dealt / received at state o against its foe, with the other enemies added: damage
        taken adds up, damage dealt is the best of all. Returned already multiplied by the exposure
        factors, with multipliers of 1.0."""
        with timing.section("Legate extras"):
            d, r = dealt * dealt_mult, received * received_mult
            on_me = {id(self.primary): r}                  # (unshared: _TeamFire distributes the fire itself)
            r *= now_share(self.primary, self.mover)       # LEGATE_SPLIT_THIS_TURN, else 1                  # each enemy's damage on the mover at o
            on_them = {id(self.primary): d}                # the mover's damage on each enemy at o
            for foe, st in self.entries:
                if st[0] == o.label:
                    continue
                cand = self.unit.rows(foe.mech, st, [o]).get(_key(o))
                if cand is None:
                    continue
                d = max(d, cand.dealt * foe.side.exposure[cand.side_on_defender])
                taken = cand.received * self.unit.side.exposure[cand.side_on_mover]
                r += taken * now_share(foe.mech, self.mover)
                on_me[id(foe.mech)] = taken
                on_them[id(foe.mech)] = cand.dealt * foe.side.exposure[cand.side_on_defender]
            if self.team is not None:
                # LEGATE_TEAM_VALUE: the damage the mover actually draws when the enemy's fire is
                # distributed over the whole team, and the team's future damage carried as a cost.
                r, cost = self.team.evaluate(on_me, on_them, d)
                self._team_cost[_key(o)] = cost
            if self.herd is not None:
                r += self.herd.penalty(o.hex_xy)
            if self.cohesion is not None:
                r -= self.cohesion.reward(o.hex_xy, o.mode == "Stand Still")
        return d, r, 1.0, 1.0

    def team_cost(self, o) -> float:
        """The team term for state o (after adjust), in the mover's own HP - added to the PSR cost the
        objective subtracts from HP left, so the score comes out as dealt + the team's future damage
        (see _TeamFire). 0 without LEGATE_TEAM_VALUE."""
        return self._team_cost.get(_key(o), 0.0)


# =============================================================================
# ===========================  HERDING  =======================================
# =============================================================================
def _ranged_weapons(mech):
    import INTEGRATION__ammo as ammo
    import INTEGRATION__weapon_rules as weapon_rules
    from damage_resolution import get_weapons
    out = ammo.unavailable_weapons(mech)
    return [w for w in get_weapons(mech) if id(w) not in out and not weapon_rules.is_ams(w)
            and w.weapon_range and w.weapon_range.get("long") is not None]


def support_range(mech, standing_still) -> int:
    """How far a unit can support a friend (Daniel, 2026-10-29: "Mech A has a 7/14/21 range bracket,
    Mech B wants to be within 14 hexes of A ... IF a mech stands still its range of support should
    increase"): the end of its medium bracket, or of its long bracket when it stands still (Claude's
    reading of "should increase": standing still instead of walking is the to-hit points of one
    range bracket, AMM 0 v +1 / +2, Core p.57 - so it reaches one bracket further). The best of its
    weapons that can still fire; 0 with none."""
    key = "long" if standing_still else "medium"
    return max((w.weapon_range[key] for w in _ranged_weapons(mech)), default=0)


def reach(mech) -> int:
    """The farthest any of its weapons that can still fire reaches (long bracket)."""
    return max((w.weapon_range["long"] for w in _ranged_weapons(mech)), default=0)


class _Herd:
    """The herding penalty for one Gladiator's spots (config.LEGATE_HERDING; Daniel, 2026-10-29:
    "Herding shape should be something like a penalty for being past medium range of any unit in the
    force ... Somehow LOS should be involved. You can't support a mech if you can't see its enemies.")
    A spot s is threatened by the enemies (where Legate believes they will end) whose weapons reach
    s. A teammate A (where it will end: friend_state) supports s if it can see one of those enemies
    (LOS from its spot to the enemy's) - its support then reaches support_range(A) hexes (standing
    still: further). The spot's gap is the fewest hexes it lies beyond the support of any such
    teammate; no teammate sees a threat: LEGATE_HERD_UNSEEN_GAP. Not threatened: no gap. The
    penalty, LEGATE_HERD_WEIGHT x gap, counts as extra damage taken (it sits beside the damage the
    other enemies would deal). Chains work by themselves: C supported by B, B by A."""

    def __init__(self, mover, units, terrain_map):
        import INTEGRATION__los_cache as los_cache
        self.terrain_map = terrain_map
        enemies = [f for f in forces.enemies_of(mover, units) if f.hex is not None]
        self.threats = []                                      # (enemy xy, its reach)
        for f in enemies:
            st = foe_state(mover.team, f)
            self.threats.append((_xy(st[0]), reach(f)))
        self.friends = []                                      # (friend xy, support range, {threat index it sees})
        for u in forces.standing(units):
            if u is mover or u.team != mover.team or u.hex is None:
                continue
            st = friend_state(mover.team, u)
            xy = _xy(st[0])
            seen = set()
            for i, (exy, _) in enumerate(self.threats):
                try:
                    if los_cache.los(xy, exy, terrain_map).los:
                        seen.add(i)
                except ValueError:
                    pass
            self.friends.append((xy, support_range(u, st[3] == "Stand Still"), seen))
        self._memo: Dict[Tuple[int, int], float] = {}

    def gap(self, xy) -> float:
        threats = {i for i, (exy, r) in enumerate(self.threats) if hex_distance(xy, exy) <= r}
        if not threats:
            return 0.0
        best = None
        for fxy, rng, seen in self.friends:
            if seen & threats:
                g = max(0, hex_distance(xy, fxy) - rng)
                best = g if best is None else min(best, g)
        return float(config.LEGATE_HERD_UNSEEN_GAP if best is None else best)

    def penalty(self, xy) -> float:
        got = self._memo.get(xy)
        if got is None:
            got = self._memo[xy] = config.LEGATE_HERD_WEIGHT * self.gap(xy)
        return got


def brackets(mech) -> Tuple[int, int, int]:
    """The ends of its short, medium and long brackets - the best of its weapons that can still fire
    for each (0, 0, 0 with none)."""
    weapons = _ranged_weapons(mech)
    return tuple(max((w.weapon_range[k] or 0 for w in weapons), default=0) for k in ("short", "medium", "long"))


class _Cohesion:
    """The cohesion reward for one Gladiator's spots (config.LEGATE_COHESION; Daniel, 2026-10-30:
    "Reward staying within a range braket of its allies, stronger at short, much weaker at long. And how
    many allies are in mutual support range."). Each standing teammate A, where it will end
    (friend_state): a spot within A's short bracket earns LEGATE_COHESION_REWARD["short"], else within
    its medium or long bracket that bracket's reward (A's own brackets: how well A covers the spot). A
    spot within mutual support of A - inside both support_range(A) and the mover's own support_range
    there (medium; long if it stands still at the spot) - earns LEGATE_COHESION_MUTUAL more. Summed over
    the teammates, times LEGATE_COHESION_SCALE, in damage points (taken off the damage the spot is
    expected to take). No LOS test (herding has one)."""

    def __init__(self, mover, units):
        self.mine = (support_range(mover, False), support_range(mover, True))
        self.friends = []                                      # (friend xy, its brackets, its support range)
        for u in forces.standing(units):
            if u is mover or u.team != mover.team or u.hex is None:
                continue
            st = friend_state(mover.team, u)
            self.friends.append((_xy(st[0]), brackets(u), support_range(u, st[3] == "Stand Still")))
        self._memo: Dict[tuple, float] = {}

    def reward(self, xy, standing_still=False) -> float:
        key = (xy, standing_still)
        got = self._memo.get(key)
        if got is None:
            rewards, mine = config.LEGATE_COHESION_REWARD, self.mine[1 if standing_still else 0]
            total = 0.0
            for fxy, (short, medium, long_), support in self.friends:
                d = hex_distance(xy, fxy)
                if d <= short:
                    total += rewards["short"]
                elif d <= medium:
                    total += rewards["medium"]
                elif d <= long_:
                    total += rewards["long"]
                if d <= min(mine, support):
                    total += config.LEGATE_COHESION_MUTUAL
            got = self._memo[key] = total * config.LEGATE_COHESION_SCALE
        return got


# =============================================================================
# ===========================  THE TEAM'S FIRE  ===============================
# =============================================================================
def _prepared(mech, state: State):
    """The prepared movement option for a unit standing at `state`."""
    x, y = _xy(state[0])
    return ranged_combat.prepare_options(mech, [(x, y, hex_geometry.compass_to_facing(state[1]), state[2],
                                                 state[3], state[4])])[0]


class _TeamFire:
    """The expected distribution of the enemy's fire over the mover's whole team this turn, and what it
    costs the team in future damage (config.LEGATE_TEAM_VALUE; Daniel, 2026-10-29: "A unit should be
    aware of the expected distribution of enemy fire at the start of its turn. It can then plot its
    move based not only how much damage it will take, but how that distribution changed across its
    entire force, and the expected loss of future damage that might entail.")

    Positions: the enemies where Legate believes they end (foe_state; the mover's foe as the move score
    has it), the mover's teammates where they end (friend_state), the mover at the spot being scored.
    dmg[e][u]: what enemy e is expected to deal unit u there (the movement evaluator, with u's
    exposure factors) - for teammates worked out once a phase, for the mover per spot.

    Whom each enemy shoots (LEGATE_TEAM_FIRE_MODEL "greedy", a stand-in for the enemy's rules - Princess
    takes its best firing plan with its team's damage map counted): the enemies in order of their
    biggest damage, each at the unit it hurts most among those not already expected to be destroyed by
    the fire assigned before it (assigned >= effective HP), else the one it hurts most. D[u] is the
    damage each unit draws.

    The team's future damage (TV) at that distribution, each unit i with its own life-left rates
    (MultiLifetime: mine_i, theirs_i with the fire split), HP_i = effective HP and Pk_i = its kill curve
    (INTEGRATION__kill_curve, front table) at D[i]:
        "sum"     - sum_i (1 - Pk_i) x (HP_i - D[i]) / theirs_i x mine_i
        "product" - Daniel's shape, SUM(future damage) x SUM(future vulnerability):
                    (sum_i (1 - Pk_i) x mine_i) x (sum_i (HP_i - D[i]) / theirs_i) / N
                    (divided by the team's size N to keep the scale of one unit's - Daniel: "at what
                    scale it goes into the picker I'm not really sure").
    In a duel both are the old lifetime term times the chance of living through the turn. The move
    score becomes dealt + TV (minus the PSR cost); the cost evaluate() returns carries TV in the mover's
    HP units: (HP_me - D_me) - TV x theirs_me / mine_me."""

    def __init__(self, mover, primary, others, units, terrain_map, me_side):
        self.mover = mover
        self.enemies = [primary] + list(others)
        team = mover.team
        self.me = objective_for(me_side, self.enemies)
        self.units = []                                   # (unit, MultiLifetime, {id(enemy): damage on it})
        self.deals: Dict[int, Dict[int, float]] = {}      # id(teammate) -> {id(enemy): damage it deals it}
        self._sides: Dict[int, object] = {}
        for u in forces.standing(units):
            if u is mover or u.team != team or u.hex is None:
                continue
            foes = [e for e in self.enemies if can_matter(u, e)]
            if not foes:
                continue
            st = friend_state(team, u)
            side = movement_selection._Side(u)
            obj = objective_for(side, foes)
            if not isinstance(obj, MultiLifetime):
                continue
            dmg, deals = {}, {}
            with timing.section("Legate team fire"):
                o = None
                for e in foes:
                    est = foe_state(team, e)
                    key = (id(u), st, id(e), est)
                    got = _FRIEND_DMG.get(key)
                    if got is None:
                        if o is None:
                            o = _prepared(u, st)
                        unit = _Unit(u, units, terrain_map, lite=True, side=side)
                        cand = unit.rows(e, est, [o]).get(_key(o)) if est[0] != st[0] else None
                        got = _FRIEND_DMG[key] = ((cand.received * side.exposure[cand.side_on_mover],
                                                   cand.dealt * self._side(e).exposure[cand.side_on_defender])
                                                  if cand is not None else (0.0, 0.0))
                    dmg[id(e)], deals[id(e)] = got
            self.units.append((u, obj, dmg))
            self.deals[id(u)] = deals
        # The enemy side, for LEGATE_TEAM_EXCHANGE: each enemy's own life-left rates against our team.
        ours = [mover] + [u for u, _, _ in self.units]
        self.foes = []                                    # (enemy, its MultiLifetime against our team)
        if config.LEGATE_TEAM_EXCHANGE:
            for e in self.enemies:
                obj = objective_for(self._side(e), [u for u in ours if can_matter(e, u)] or ours)
                if isinstance(obj, MultiLifetime):
                    self.foes.append((e, obj))

    def _side(self, mech):
        got = self._sides.get(id(mech))
        if got is None:
            got = self._sides[id(mech)] = movement_selection._Side(mech)
        return got

    @staticmethod
    def _greedy(table, hp):
        """table: {shooter: {target: damage}}; hp: {target: effective HP}. The shooters in order of their
        biggest damage, each at the target it hurts most among those not already doomed by the fire
        assigned before it (assigned >= HP), else the one it hurts most. {target: damage drawn}."""
        drawn = dict.fromkeys(hp, 0.0)
        for shooter in sorted(table, key=lambda k: -max(table[k].values(), default=0.0)):
            row = {t: v for t, v in table[shooter].items() if t in drawn}
            live = {t: v for t, v in row.items() if v > 0 and drawn[t] < hp[t]}
            pool = live or {t: v for t, v in row.items() if v > 0}
            if pool:
                t = max(pool, key=pool.get)
                drawn[t] += row[t]
        return drawn

    def distribute(self, on_me):
        """{id(unit): damage drawn} for the mover (on_me: {id(enemy): its damage on the mover}) and the
        teammates - the enemy's fire (LEGATE_TEAM_FIRE_MODEL "greedy")."""
        if config.LEGATE_TEAM_FIRE_MODEL != "greedy":
            raise ValueError(f"Unknown LEGATE_TEAM_FIRE_MODEL {config.LEGATE_TEAM_FIRE_MODEL!r} ('greedy')")
        hp = {id(self.mover): self.me.hp}
        hp.update({id(u): obj.hp for u, obj, _ in self.units})
        table = {}
        for e in self.enemies:
            row = {id(self.mover): on_me.get(id(e), 0.0)}
            row.update({id(u): dmg.get(id(e), 0.0) for u, _, dmg in self.units})
            table[id(e)] = row
        return self._greedy(table, hp)

    def our_fire(self, on_them):
        """{id(enemy): damage drawn} under our team's fire, the same greedy rule (on_them: {id(enemy): the
        mover's damage on it at the spot being scored})."""
        hp = {id(e): obj.hp for e, obj in self.foes}
        table = {id(self.mover): dict(on_them)}
        table.update({uid: deals for uid, deals in self.deals.items()})
        return self._greedy(table, hp)

    @staticmethod
    def _team_value(rows, drawn):
        """LEGATE_TEAM_VALUE of a side: rows [(unit, its MultiLifetime)], drawn {id(unit): damage}."""
        import INTEGRATION__kill_curve as kill_curve
        mine, life, total = 0.0, 0.0, 0.0
        for u, obj in rows:
            d = drawn.get(id(u), 0.0)
            alive = 1.0 - kill_curve.chance(u, "front", d)
            left = max(obj.hp - d, 0.0) / obj.theirs
            total += alive * left * obj.mine
            mine += alive * obj.mine
            life += left
        if config.LEGATE_TEAM_VALUE == "sum":
            return total
        if config.LEGATE_TEAM_VALUE == "product":
            return mine * life / max(len(rows), 1)
        raise ValueError(f"Unknown LEGATE_TEAM_VALUE {config.LEGATE_TEAM_VALUE!r} (None, 'sum' or 'product')")

    def evaluate(self, on_me, on_them=None, dealt=0.0):
        """(the damage the mover draws, the team cost in the mover's HP units) for one spot. The score
        the objective then gives is dealt + TV_ours, or with LEGATE_TEAM_EXCHANGE
        TV_ours + LEGATE_TEAM_EXCHANGE_WEIGHT x (TV_theirs untouched - TV_theirs under our fire): the
        enemy's future damage this move helps take off the board, in place of the mover's own dealt
        (which is part of our fire)."""
        with timing.section("Legate team fire"):
            drawn = self.distribute(on_me)
            rows = [(self.mover, self.me)] + [(u, obj) for u, obj, _ in self.units]
            tv = self._team_value(rows, drawn)
            if self.foes:
                theirs0 = self._team_value(self.foes, {})
                theirs = self._team_value(self.foes, self.our_fire(on_them or {}))
                tv += config.LEGATE_TEAM_EXCHANGE_WEIGHT * (theirs0 - theirs) - dealt
            d_me = drawn[id(self.mover)]
            return d_me, (self.me.hp - d_me) - tv * self.me.theirs / self.me.mine
