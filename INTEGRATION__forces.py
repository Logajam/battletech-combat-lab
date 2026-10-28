"""INTEGRATION__forces.py - who is on whose side, who acts when, and who
shoots whom (NEW 2026-10-28, Claude: multi-unit battles).

Daniel, 2026-10-28: "Multiple units that can be assigned to multiple teams.
The ideal ranges would probably be a 4 unit lance and a 12 unit company vs
like forces. But a 20 unit free for all or a 3 way battle between different
lances are also possibilities that need to be covered by the general
solution. For the moment we're just getting to the point where we can
unleash a group of bots to operate independently."

A battle is a list of live 'Mechs ("units"). Each has
  unit.side_name   its unique label in the logs and reports ("Red" when its
                   team has one unit, else "Red 1", "Red 2", ...)
  unit.team        the team it fights for ("Red"); a free for all is every
                   unit on a team of its own
  unit.moved_this_turn   set by the orchestrator once the unit has moved
Two units on different teams are enemies; there are no alliances.

This module holds the choices that only exist with more than two units:

  initiative_order   every team rolls 2D6 (Core p.39); the lowest roll acts
                     first. Ties re-roll among the tied teams only.
  activation_sequence  who takes the next movement selection / fire
                     selection: sides alternate, the side that lost
                     Initiative first, and a larger side takes more than one
                     unit at a time (UNEQUAL NUMBERS, p.41).
  move_index         which of a team's units takes its selection next
                     (Princess's index: far, slow units first).
  choose_foe         the one enemy a unit's bot plans its movement against.
  choose_target      the one enemy a unit fires and fights at this turn.

=== RULES THE BOOK ANSWERS ===
  - Initiative, sequence of play, alternating selections, the Unequal
    Numbers tally (shut down / unconscious units are left out; immobile ones
    too in the Movement Phase) and the 1:1 end of the process: pp.39-41.
  - A unit may be a primary target and secondary targets cost +1 (p.64):
    NOT USED YET - a unit shoots one enemy a turn (see choose_target).

=== RULES THE BOOK DOES NOT ANSWER (loud defaults, PROJECT_MAP Section 6) ===
  - Initiative and Unequal Numbers with THREE OR MORE sides. The book only
    says "the side with the higher result wins" and gives the 2-side table.
    Default here: sides act lowest roll first, and each side takes
    ceil(its eligible units / the smallest other side's eligible units)
    selections at a time - exactly the book's table for two sides.
  - Which of a side's units takes the next selection: a bot choice.
  - Whom a bot shoots when several enemies are in sight: a bot choice
    (config.FOE_CHOICE).
"""

import math
from typing import Callable, Dict, Iterator, List, Optional

import INTEGRATION__config as config
from mech_state import (is_destroyed, is_immobile, all_crew_unconscious, compute_running_mp,
                        compute_jump_mp)
import hex_geometry
from los import hex_distance


# =============================================================================
# ==========================  TEAMS  ==========================================
# =============================================================================
# The battle's units, for code that only has a mech in its hand (displacement
# into an occupied hex - INTEGRATION__domino). Set by the orchestrator, once a battle.
_BATTLE: list = []


def set_battle(units) -> None:
    _BATTLE[:] = list(units)


def battle() -> list:
    """The battle's units (set by the orchestrator), for a bot that has only its own mech in hand."""
    return list(_BATTLE)


def unit_in_hex(label, exclude=()):
    """The standing unit in hex `label`, other than those in `exclude`."""
    for u in _BATTLE:
        if u.hex == label and not is_destroyed(u) and all(u is not x for x in exclude):
            return u
    return None


def standing(units) -> list:
    """The units still in the battle (not destroyed)."""
    return [u for u in units if not is_destroyed(u)]


def team_names(units) -> List[str]:
    """Teams in order of first appearance."""
    seen: List[str] = []
    for u in units:
        if u.team not in seen:
            seen.append(u.team)
    return seen


def teams_standing(units) -> List[str]:
    """Teams with at least one unit left."""
    return team_names(standing(units))


def enemies_of(unit, units) -> list:
    """Standing units on other teams."""
    return [u for u in standing(units) if u.team != unit.team and u is not unit]


def any_enemy(unit, units):
    """An enemy of the unit, destroyed or not: the foe a unit still plans
    against when its last enemy fell earlier in the same phase."""
    return next((u for u in units if u.team != unit.team), None)


def friends_of(unit, units) -> list:
    """Standing units on the same team (not the unit itself)."""
    return [u for u in standing(units) if u.team == unit.team and u is not unit]


def is_enemy(a, b) -> bool:
    return a.team != b.team


def hex_xy(unit):
    return hex_geometry.parse_hex_label(unit.hex) if unit.hex is not None else None


def distance(a, b) -> Optional[int]:
    """Hexes between two units on the board, None if either is still off it."""
    if a.hex is None or b.hex is None:
        return None
    return hex_distance(hex_xy(a), hex_xy(b))


def occupied_labels(unit, units) -> frozenset:
    """Hex labels of every OTHER standing unit on the board: the hexes this
    unit can't end its movement in (stacking, Core p.49)."""
    return frozenset(u.hex for u in standing(units) if u is not unit and u.hex is not None)


def blocked_xy(unit, units) -> frozenset:
    """(x, y) of every mobile enemy on the board: no ground step may enter
    them (p.48 - an immobile enemy can be moved through)."""
    return frozenset(hex_xy(u) for u in enemies_of(unit, units) if u.hex is not None and not is_immobile(u))


# =============================================================================
# ==========================  INITIATIVE  =====================================
# =============================================================================
def initiative_order(teams: List[str], battle_rng, rolls: Optional[Dict[str, int]] = None) -> List[str]:
    """Every team rolls 2D6 for Initiative (p.39); returns the teams LOWEST
    roll first (the side that lost acts first). Teams that tie re-roll among
    themselves until they separate ("Reroll all ties", p.39 - read as: only
    the tied teams roll again; with two teams that is the book's reroll).
    Rolls are drawn in team order, so two teams draw exactly as the two-'Mech
    battle always did. `rolls`, if given, is filled with each team's last
    (deciding) roll for the log."""
    def settle(group):
        if len(group) == 1:
            return list(group)
        thrown = {t: battle_rng.roll_2d6() for t in group}
        if rolls is not None:
            rolls.update(thrown)
        ordered: List[str] = []
        for value in sorted(set(thrown.values())):
            tied = [t for t in group if thrown[t] == value]
            ordered.extend(settle(tied) if len(tied) > 1 else tied)
        return ordered

    return settle(list(teams))


# =============================================================================
# ==========================  WHO ACTS NEXT  ==================================
# =============================================================================
def move_index(unit, units) -> float:
    """Which of a team's units takes its selection next: the higher index
    first. Princess's move index (MegaMek Princess.calculateMoveIndex, the
    distance to the nearest enemy over the unit's fastest move; "faster units
    that are closer to the enemy should move later") - a bot decision, used
    for every bot (PROJECT_MAP Section 6, 'Activation order'). A unit that
    hasn't entered the board yet goes first."""
    near = [d for d in (distance(unit, e) for e in enemies_of(unit, units)) if d is not None]
    if unit.hex is None or not near:
        return float("inf")
    fastest = max(compute_running_mp(unit), compute_jump_mp(unit))
    total = min(near) * 2 if fastest == 0 else min(near) / fastest
    return total * (1.1 if unit.prone else 1.0)


def activation_sequence(units, teams_in_order: List[str], can_select: Callable[[object], bool],
                        pick: Optional[Callable[[list], object]] = None) -> Iterator[object]:
    """Yields the units one at a time in the order they take their selection
    this phase - sides alternate, the side that lost Initiative first, and a
    side with more eligible units than the smallest other side takes
    ceil(n / smallest) selections at a time (UNEQUAL NUMBERS, p.41). A side
    that has nobody left to take a selection while another does takes
    nothing; a side whose opponents have run out takes all its units at once.

    can_select(unit): the unit counts toward the tally (not shut down, no
    unconscious pilot; for movement not immobile either, p.41). A unit that
    can't is yielded too - the phase still has to log it and apply what it
    does - but ahead of its side's first selection and without costing one.

    The generator reads the live units between yields, so a caller that
    moves each unit before asking for the next sees the board as it is.
    pick(candidates) returns the candidate that goes next (default: roster
    order)."""
    live = standing(units)
    eligible = {t: [u for u in live if u.team == t and can_select(u)] for t in teams_in_order}
    idle = {t: [u for u in live if u.team == t and not can_select(u)] for t in teams_in_order}
    pick = pick or (lambda candidates: candidates[0])
    while any(eligible[t] or idle[t] for t in teams_in_order):
        # Each round's selections are worked out from the tallies as the round
        # begins (the book's tables, p.41, and MegaMek's TurnOrdered both do).
        tally = {t: len(eligible[t]) for t in teams_in_order}
        for t in teams_in_order:
            while idle[t]:
                yield idle[t].pop(0)
            n = len(eligible[t])
            if n == 0:
                continue
            others = [tally[o] for o in teams_in_order if o != t and tally[o]]
            take = n if not others else max(1, math.ceil(tally[t] / min(others)))
            for _ in range(min(take, n)):
                unit = pick(eligible[t])
                eligible[t].remove(unit)
                yield unit


def can_select_move(unit) -> bool:
    """Counts toward the Movement Phase tally (p.41): not shut down, pilot
    conscious, not immobile."""
    return not (unit.shutdown or all_crew_unconscious(unit) or is_immobile(unit))


def can_select_fire(unit) -> bool:
    """Counts toward the attack phases' tally (p.41): not shut down, pilot
    conscious."""
    return not (unit.shutdown or all_crew_unconscious(unit))


def movement_order(units, teams_in_order) -> Iterator[object]:
    """The Movement Phase's selections, one unit at a time (see
    activation_sequence); each side's next unit is its highest move_index."""
    return activation_sequence(units, teams_in_order, can_select_move,
                               pick=lambda c: max(c, key=lambda u: move_index(u, units)))


def fire_order(units, teams_in_order) -> List[object]:
    """The attack phases' declaration / resolution order (p.39): fixed at
    the start of the phase, since nobody's position changes in it."""
    return list(activation_sequence(units, teams_in_order, can_select_fire))


# =============================================================================
# ==========================  WHOM A UNIT FIGHTS  =============================
# =============================================================================
def choose_foe(mover, units):
    """The enemy this unit's bot plans its movement against (the `other` of
    the two-'Mech movement code): the nearest standing enemy on the board
    (config.FOE_CHOICE "nearest"; ties by roster order), else the first
    standing enemy still off it (the bot heads for its home edge). None when
    no enemy is left. In a two-'Mech battle this is always the other 'Mech.

    The units' other enemies are NOT modeled by the bot's movement scoring:
    it weighs the foe alone (independent bots, 2026-10-28 - the group
    behaviors, mutual support and fire distribution, are Pick up here 00)."""
    foes = enemies_of(mover, units)
    if not foes:
        return None
    if len(foes) == 1:
        return foes[0]
    if config.FOE_CHOICE not in ("nearest",):
        raise ValueError(f"Unknown FOE_CHOICE {config.FOE_CHOICE!r} - choose 'nearest'.")
    on_board = [(distance(mover, f), i, f) for i, f in enumerate(foes) if distance(mover, f) is not None]
    if on_board:
        return min(on_board, key=lambda row: row[:2])[2]
    return foes[0]


def choose_target(attacker, units, terrain_map=None, adjacent_only=False):
    """The one enemy this unit attacks in an attack phase (bot choice,
    PROJECT_MAP Section 6 'Target choice'). Among the standing enemies on the
    board: one the unit has a line of sight to beats one it hasn't, then one
    a weapon can bear on (firing arcs, with any torso twist) beats one none
    can, then the nearest, then roster order. adjacent_only (physical
    attacks): only enemies in the next hex. None when there is no enemy to
    attack. With one enemy to choose from it is always that enemy."""
    candidates = []
    for i, e in enumerate(enemies_of(attacker, units)):
        d = distance(attacker, e)
        if d is None or (adjacent_only and d != 1):
            continue
        candidates.append((d, i, e))
    if not candidates:
        return None
    if len(candidates) == 1 or terrain_map is None:
        return min(candidates, key=lambda row: row[:2])[2]
    import INTEGRATION__attack_resolution as attack_resolution       # attack_resolution imports config only
    from los import trace_los_path

    def rank(row):
        d, i, e = row
        trace = trace_los_path(hex_xy(attacker), hex_xy(e), terrain_map,
                               attack_resolution.los_height(attacker), attack_resolution.los_height(e))
        no_los = 0 if trace.result.los else 1
        cannot_bear = 0 if (adjacent_only or attack_resolution.weapons_can_bear(attacker, e)) else 1
        return (no_los, cannot_bear, d, i)

    return min(candidates, key=rank)[2]
