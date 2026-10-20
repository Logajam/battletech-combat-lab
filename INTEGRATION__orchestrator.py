"""
INTEGRATION__orchestrator.py

The real Pile 1 turn-flow controller (Section 2's turn structure), driving
two independently-loaded BattleMech instances on a loaded board. This is
the file Section 5's "Outer batch-loop / turn-flow controller: new
orchestrator files, not either existing driver" decision names, and the
target of the 2026-08-30 Pile 1 reconciliation decision: logic gets
cannibalized in from PATHFINDER__combat_turn.py / MECHSIM__sim_runner.py
as each piece is wired for real; both files are then deleted from this
project (their own source projects are unaffected).

=== STATUS 2026-10-18 (Claude): FIRST END-TO-END PASS ===
input .mtf -> combat rounds -> results now runs. Every phase does
something; every placeholder is a loud, counted stub in
INTEGRATION__stubs.py (knobs in INTEGRATION__config.py's STUB SETTINGS).

  Turn start   snapshot_preexisting_damage (MECHSIM)                  REAL
  Initiative   roll_initiative() - 2d6, reroll ties, loser first      REAL (Daniel-confirmed 2026-08-31)
  Movement     loser then winner, _phase_movement():
                 (spot scoring is heat-aware since 2026-10-18: each spot's expected
                  dealt/received uses the real heat-limited weapon pick, including
                  that spot's own movement heat)
                 immobile (all crew unconscious, or shut down)
                   -> skip, TMM -4                                    REAL (MECHSIM convention; shutdown p.104)
                 prone -> piloting_rolls.resolve_stand_up()           REAL
                   ...leftover MP after standing                      STUB post_standup_movement
                 envelope + expected dealt/received per spot
                   (INTEGRATION__ranged_combat.MoveEvaluator)         REAL
                 picking one spot (INTEGRATION__movement_selection:
                   dealt / (received + PSR cost + 0.001), two-ply
                   for the first mover, exposure-weighted)           REAL (Daniel, 2026-10-19)
                 movement PSR (check_movement_psr, Run 1+ hex / Jump) REAL (Core p.111: none for Walk)
                 consciousness checks                                 REAL
  Ranged       INTEGRATION__attack_resolution.run_ranged_combat_phase REAL dice, LOS, TN (incl. heat
               to-hit modifier), weapon selection, hit location, damage, crits, explosions, PSRs,
               consciousness. Shut-down mechs don't fire.
               Stubs inside: unknown_damage_type,
               unconfirmed_weapon_data, ammo_data (weapons with no shots-per-ton data)
  Physical     INTEGRATION__physical.run_physical_phase               REAL punch / kick / physical weapons
               (Core pp.76-83); charge, DFA, push, club not built
  Heat         _phase_heat() -> INTEGRATION__heat.resolve_heat_phase  REAL (Core Rulebook pp.102-107,
               heat carries over turn to turn; + movement heat          2026-10-19)
               (Walk 1 / Run 2 / Jump, XXL / super-cooled myomer) + weapon heat + engine-hit heat
               - dissipation; then shutdown or restart, ammo explosion, life-support pilot hits,
               and next turn's MP / to-hit penalties
  End          resolve_end_phase_wakeup, crippled check, destruction  REAL
  Deployment   home edges (Core p.37) or fixed CONFIG hexes           REAL (config.DEPLOYMENT)

TMM everywhere comes from ACTUAL hexes moved this turn (combat.fc_to_tmm)
- Daniel 2026-10-18. MECHSIM's compute_tmm()/resolve_movement_phase()
(max-available-MP model) are not called by the integration.

Per-mech movement state set each Movement Phase and read by Ranged Combat:
  mech.move_mode  "Stand Still"/"Walk"/"Run"/"Jump"
  mech.move_fc    hexes moved (forward count) - feeds TMM
  mech.mp_spent

=== PILOTING SHIM ===
MECHSIM piloting_rolls.py reads one global config.PILOTING. Every call
into it from the integration goes through _with_piloting(mech, fn), which
sets config.PILOTING to that mech's own skill for the call.

=== CROSS-PROJECT IMPORTS ===
INTEGRATION__config is imported first (it puts MECHSIM_DIR on sys.path and
registers itself as the bare "config" module MECHSIM files import).
PATHFINDER_DIR then goes on sys.path once. None of the PATHFINDER modules
used here import `config` (verified 2026-09-01), so no purge dance
anywhere - the one in INTEGRATION__weapon_selection.py was REMOVED
2026-10-18 because it deleted config's registration (confirmed by a live
import failure). If a real same-name collision ever resurfaces, fix it
here, not with sys.modules purging.

=== STILL TO ABSORB BEFORE combat_turn.py / sim_runner.py CAN BE DELETED ===
  - sim_runner: _resolve_hit / resolve_weapon_attack are now absorbed
    (INTEGRATION__attack_resolution). Its summarize/record-sheet printing
    is not; nothing here needs it.
  - combat_turn: the two-ply look-ahead and closing-fallback logic are
    absorbed into INTEGRATION__movement_selection (2026-10-19); combat_turn.py
    itself is still reference only.
"""

import io
import multiprocessing
import os
import pickle
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from typing import List, Optional

import numpy as np

# --- MECHSIM side (see CROSS-PROJECT IMPORTS above) ---
import INTEGRATION__config as config  # noqa: E402 - self-registers as "config" for MECHSIM's internal imports
from mech_state import (  # noqa: E402 - MECHSIM, resolved via MECHSIM_DIR
    is_destroyed,
    is_crippled,
    clone_mech,
    compute_walk_mp,
    compute_running_mp,
    compute_jump_mp,
    all_crew_unconscious,
    is_immobile,
)
import piloting_rolls  # noqa: E402 - MECHSIM

# --- PATHFINDER side ---
PATHFINDER_DIR = os.environ.get(
    "PATHFINDER_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "pathfinder")
)
if PATHFINDER_DIR not in sys.path:
    sys.path.insert(0, PATHFINDER_DIR)
import board_parser  # noqa: E402 - PATHFINDER
import hex_geometry  # noqa: E402 - PATHFINDER
import combat  # noqa: E402 - PATHFINDER; build_jump_states/classify_movement_mode/fc_to_tmm/MODE_TO_AMM

from INTEGRATION__rng import BattleRNG  # noqa: E402
import INTEGRATION__weapon_selection as weapon_selection  # noqa: E402
import INTEGRATION__heat as heat  # noqa: E402
import INTEGRATION__equipment_systems as equip  # noqa: E402
import INTEGRATION__ammo as ammo  # noqa: E402
import INTEGRATION__physical as physical  # noqa: E402
import INTEGRATION__movement_selection as movement_selection  # noqa: E402
import INTEGRATION__ranged_combat as ranged_combat  # noqa: E402
import INTEGRATION__stubs as stubs  # noqa: E402
import INTEGRATION__attack_resolution as attack_resolution  # noqa: E402
import INTEGRATION__arcs as arcs  # noqa: E402
import INTEGRATION__clubs as clubs  # noqa: E402
from INTEGRATION__attack_resolution import _with_piloting, total_hp  # noqa: E402
from INTEGRATION__results import BattleResult, SideStats, summarize  # noqa: E402


# =============================================================================
# ==========================  MAP LOADING  ====================================
# =============================================================================
def _load_map():
    """Loads config.DEFAULT_BOARD_PATH (resolved under config.DATA_DIR) as a
    single board. config.PROMPT_FOR_MAP's interactive picker is still not
    built (needs a board-picking counterpart to file_picker.pick_files()).
    config.STITCH_MAPS raises rather than silently ignoring a multi-board
    setup it can't fulfill yet."""
    if config.STITCH_MAPS:
        raise NotImplementedError(
            "config.STITCH_MAPS is True, but _load_map() only wires the "
            "single-board DEFAULT_BOARD_PATH case. board_parser.stitch_boards() "
            "itself is ready - what's missing is picking/ordering the board "
            "files for it. Not built yet - ask before adding one."
        )
    path = config.data_path(config.DEFAULT_BOARD_PATH)
    config.log(f"\nLoading map: {path}")
    terrain_map = board_parser.parse_board_file(path)
    config.log(f"  Map loaded: {terrain_map['width']}x{terrain_map['height']}, "
               f"{len(terrain_map['hexes'])} hexes.")
    return terrain_map


# =============================================================================
# ======================  MECH CONFIG ATTACHMENT  ============================
# =============================================================================
def _attach_mech_config(mech, cfg, side_name):
    """Attaches the config-level scenario inputs onto a loaded BattleMech
    instance as plain attributes. None of these come out of
    mtf_parser.parse_mtf(); per Section 5, gunnery/piloting are config-level
    input. Called fresh on each sim's cloned mech so nothing leaks between
    Monte Carlo iterations. The config hex/facing is the starting position
    when config.DEPLOYMENT is "fixed_hexes"; with "home_edge" run_battle
    takes the mech off the board again (_deploy_home_edges)."""
    mech.side_name = side_name
    mech.hex, mech.facing = cfg["hex"], cfg["facing"]
    mech.home_edge = None
    mech.gunnery = cfg["gunnery"]
    mech.piloting = cfg["piloting"]
    mech.min_heat = cfg["min_heat"]
    mech.max_heat = cfg["max_heat"]
    mech.current_heat = 0
    mech.shutdown = False
    mech.deactivated_heat_sinks = 0
    heat.attach_heat_traits(mech)
    ammo.attach_ammo(mech)
    if mech.has_tsm:
        # TSM is driven by min_heat (Daniel, 2026-10-19); max_heat must allow it.
        mech.min_heat = max(mech.min_heat, config.TSM_MIN_HEAT)
        mech.max_heat = max(mech.max_heat, mech.min_heat)
        config.log(f"  {side_name}: triple-strength myomer - min_heat {mech.min_heat}, max_heat {mech.max_heat}.")
    heat.apply_heat_effects(mech)
    _reset_movement_state(mech)
    heat.choose_heat_sink_deactivation(mech, next_turn=1)  # may start the game with sinks off (p.103)


def _reset_movement_state(mech):
    equip.reset_movement_boost(mech)
    mech.move_mode = "Stand Still"
    mech.move_fc = 0
    mech.mp_spent = 0
    mech.movement_heat = 0
    mech.charging = None                 # the mech it declared a charge against (Core p.78)
    mech.dfa = None                      # ... or a death from above against (pp.79-80)


# Heat rules (movement heat, Improved-JJ detection, budget) live in
# INTEGRATION__heat.py (Daniel, 2026-10-18) - shared with movement scoring.


# =============================================================================
# ==========================  INITIATIVE  =====================================
# =============================================================================
def roll_initiative(battle_rng: BattleRNG) -> str:
    """Both sides roll 2d6 via the shared BattleRNG; both reroll on a tie
    until a winner emerges. Higher roll wins initiative and moves second;
    lower roll loses and moves first. Returns the LOSING side's name.
    CONFIRMED (Daniel, 2026-08-31)."""
    while True:
        red_roll = battle_rng.roll_2d6()
        blue_roll = battle_rng.roll_2d6()
        if red_roll != blue_roll:
            break
    return "Red" if red_roll < blue_roll else "Blue"


# =============================================================================
# ==========================  CURRENT MP  =====================================
# =============================================================================
def _compute_available_mp(mech):
    """{"walk", "run", "jump"} - CURRENT damage-adjusted budget from
    MECHSIM__mech_state.compute_*_mp(). Fresh each call: leg-actuator/jump-jet
    damage can change turn to turn."""
    return {
        "walk": compute_walk_mp(mech),
        "run": compute_running_mp(mech),
        "jump": compute_jump_mp(mech),
    }


# =============================================================================
# ==========================  MOVEMENT PHASE  =================================
# =============================================================================
_MODE_TO_PSR = {"Run": "running", "Jump": "jump"}


def _needs_backward_move(mover, pick, terrain_map, standup_mp, entry_edge):
    """Log helper (2026-10-20): True if the picked Walk end state can only be
    reached with a backward move (Core p.46) - it isn't among the forward-only
    states. Only called with VERBOSE on, so batches don't pay for it."""
    if pick["mode"] != "Walk" or standup_mp is not None or entry_edge is not None or pick.get("charge"):
        return False
    x, y = hex_geometry.parse_hex_label(pick["hex"])
    state = (x, y, hex_geometry.compass_to_facing(pick["facing"]), pick["fc"], pick["mode"], pick["mp_spent"])
    return state not in set(ranged_combat.movement_options(mover, terrain_map, backward=False))


def _turn_while_down(mover, other):
    """A prone mech that can't stand (config.FIGHT_TO_THE_DEATH: destroyed
    gyro, or legs / arms lost - pp.51, 98) may still change facing: 1 MP per
    hexside, and only one hexside per turn with a destroyed gyro (p.98).
    Bot decision (2026-10-20, PROJECT_MAP Section 6): the fewest turns that
    put the enemy in its forward arc, else in a side arc; no turn if nothing
    improves (turning makes it a Walk: AMM +1 and 1 heat). Its ranged weapons
    fire as if standing with that facing (p.67)."""
    if other.hex is None or mover.hex is None:
        return
    walk = compute_walk_mp(mover)
    max_turns = min(walk, 1 if mover.gyro_hits >= 2 else 3)
    if max_turns < 1:
        return
    me, them = hex_geometry.parse_hex_label(mover.hex), hex_geometry.parse_hex_label(other.hex)
    seen_as = arcs.arcs_between(me, them)           # the arc the enemy is in, per facing
    facing = hex_geometry.compass_to_facing(mover.facing)
    rank = lambda f: 0 if seen_as[f] == arcs.FORWARD else (1 if seen_as[f] != arcs.REAR else 2)   # noqa: E731
    best, best_turns = facing, 0
    for turns in range(1, max_turns + 1):
        for f in ((facing + turns) % 6, (facing - turns) % 6):
            if rank(f) < rank(best):
                best, best_turns = f, turns
    if best_turns == 0:
        return
    mover.facing = hex_geometry.facing_to_compass(best)
    mover.move_mode, mover.mp_spent = "Walk", best_turns
    config.log(f"  [Movement] {mover.side_name}: can't stand - turns {best_turns} hexside(s) on the ground to "
               f"face {mover.facing} ({arcs.ARC_NAMES[seen_as[best]]} arc on {other.side_name}; Walk, "
               f"{best_turns} MP).")


def _phase_movement(mover, other, terrain_map, turn_number, battle_rng, moves_first):
    """One mech's movement. See the module docstring table for which parts
    are real and which are stubs. `other` is the opponent: for the first
    mover it hasn't moved yet this turn (its current hex is a projection);
    for the second mover it has (its real end position). `moves_first` tells
    INTEGRATION__movement_selection which of the two this mech is."""
    name = mover.side_name
    _reset_movement_state(mover)

    if is_immobile(mover):
        why = ("shut down" if mover.shutdown else "all crew unconscious" if all_crew_unconscious(mover)
               else "legs destroyed")
        config.log(f"  [Movement] {name}: {why} - skips movement (immobile).")
        return

    standup_mp = None
    booster_failures = []
    if mover.prone:
        # A prone mech declares its mode, then tries to stand (Core p.51).
        # MECHSIM stands with running MP, so the declared mode is Run - it
        # costs Run heat and AMM even if the mech stays down.
        tries = (piloting_rolls.can_stand(mover) and mover.pilot_hits < 5
                 and compute_running_mp(mover) > 0)                     # resolve_stand_up's own gates
        remaining = _with_piloting(mover, piloting_rolls.resolve_stand_up)
        if tries:
            mover.move_mode = "Run"
        if mover.prone and not is_destroyed(mover) and not piloting_rolls.can_stand(mover):
            _turn_while_down(mover, other)
        if mover.prone or is_destroyed(mover):
            config.log(f"  [Movement] {name}: still prone at {mover.hex}.")
            mover.movement_heat = heat.movement_heat(mover, mover.move_mode, mover.move_fc)
            piloting_rolls.resolve_consciousness_checks(mover, "Movement Phase")
            return
        # Stood up: any facing for free, then the remaining MP as normal (p.51).
        standup_mp = remaining
    else:
        booster_failures = equip.resolve_movement_boosters(mover)   # MASC / supercharger (p.204)
    mp = _compute_available_mp(mover)
    entry_edge = mover.home_edge if mover.hex is None else None   # entering the battlefield (p.37)
    pick, why = movement_selection.choose(mover, other, terrain_map, battle_rng, moves_first,
                                          standup_mp=standup_mp, entry_edge=entry_edge)
    if pick is None and entry_edge is not None:
        # "A unit must move onto the battlefield ... If it cannot, it is destroyed." (p.37)
        mover.destroyed, mover.cause_of_death = True, "Could Not Enter Battlefield"
        config.log(f"  [Movement] {name}: can't enter the battlefield - destroyed.")
        return
    config.log(f"  [Movement select] {name}: {why}")

    if pick is not None:
        start = "off the board" if entry_edge is not None else f"{mover.hex} {mover.facing}"
        backward = config.VERBOSE and _needs_backward_move(mover, pick, terrain_map, standup_mp, entry_edge)
        mover.hex, mover.facing = pick["hex"], pick["facing"]
        mover.move_mode, mover.move_fc, mover.mp_spent = pick["mode"], pick["fc"], pick["mp_spent"]
        mover.movement_heat = heat.movement_heat(mover, mover.move_mode, mover.move_fc)
        if pick.get("charge"):
            mover.charging = other
            config.log(f"  [Movement] {name} declares a CHARGE against {other.side_name} "
                       f"(stops adjacent; {mover.move_fc} hexes counting the target's hex).")
        if pick.get("dfa"):
            mover.dfa = other
            config.log(f"  [Movement] {name} declares DEATH FROM ABOVE on {other.side_name} "
                       f"(in the air next to it; jumped {mover.move_fc} hexes).")
        config.log(f"  [Movement] {name}: {start} -> {mover.hex} {mover.facing}, {mover.move_mode} "
                   f"({mover.mp_spent} MP, {mover.move_fc} hexes, {mover.movement_heat} heat; budget "
                   f"walk {mp['walk']} / run {mp['run']} / jump {mp['jump']}"
                   f"{f'; stood up with {standup_mp} MP left' if standup_mp is not None else ''})"
                   f"{' - includes a backward move' if backward else ''}")
    else:
        # stays put: Stand Still, which still generates heat with an XXL engine (p.102)
        mover.movement_heat = heat.movement_heat(mover, mover.move_mode, mover.move_fc)

    if standup_mp is not None:
        # resolve_stand_up already made the running-mode PSR for moving on
        # after standing ("fell again after standing").
        piloting_rolls.resolve_consciousness_checks(mover, "Movement Phase")
        return

    # Movement-mode PSRs (Core p.111): running at least one hex, or jumping,
    # with the damage check_movement_psr looks for. Walking and standing
    # still never force one.
    psr_mode = _MODE_TO_PSR.get(mover.move_mode)
    if psr_mode == "running" and mover.move_fc < 1:
        psr_mode = None
    if psr_mode is not None:
        # TODO (rule check): a failed PSR currently drops the mech in its
        # END hex - in tabletop play it falls where the check was failed.
        # Check MegaMek movement processing for where the fall happens.
        _with_piloting(mover, piloting_rolls.check_movement_psr, psr_mode)
    if booster_failures and not is_destroyed(mover):
        # Failed MASC / supercharger: damage, then any PSR it forces, at the
        # end of movement (p.204) - the PSR uses the damage-this-phase triggers.
        piloting_rolls.snapshot_pre_attack_phase(mover)
        equip.apply_booster_failures(mover, booster_failures)
        _with_piloting(mover, piloting_rolls.resolve_attack_phase_psr)
    piloting_rolls.resolve_consciousness_checks(mover, "Movement Phase")


# =============================================================================
# ==========================  OTHER PHASES  ===================================
# =============================================================================
def _phase_heat(mech_red, mech_blue, reports):
    """Heat Phase for both mechs (Core Rulebook pp.102-107): heat is saved
    state (Daniel, 2026-10-18); INTEGRATION__heat.resolve_heat_phase adds
    this turn's movement/weapon/engine heat, subtracts dissipation, then
    resolves shutdown/restart, ammo explosion and life-support hits, and
    sets next turn's MP/to-hit penalties. A mech already destroyed this
    turn is skipped."""
    for m in (mech_red, mech_blue):
        if is_destroyed(m):
            continue
        heat.resolve_heat_phase(m, reports[m.side_name].weapon_heat)


def _phase_end(mech_red, mech_blue, turn_number, stats):
    """Unconscious-pilot recovery (Section 2 scope) plus bookkeeping:
    first turn each mech meets MECHSIM's is_crippled()."""
    for m in (mech_red, mech_blue):
        piloting_rolls.resolve_end_phase_wakeup(m)
        heat.choose_heat_sink_deactivation(m, next_turn=turn_number + 1)
        equip.end_turn(m)
        arcs.end_turn(m)                     # torso forward, arms back (Core pp.40, 62)
        s = stats[m.side_name]
        if s.crippled_at is None and not is_destroyed(m) and is_crippled(m):
            s.crippled_at = turn_number
            config.log(f"  [End] {m.side_name} is now CRIPPLED (BattleMech Manual definition).")


def _status_line(m):
    flags = []
    if m.shutdown:
        flags.append("SHUT DOWN")
    if m.prone:
        flags.append("PRONE")
    if all_crew_unconscious(m):
        flags.append("UNCONSCIOUS")
    if is_destroyed(m):
        flags.append(f"DESTROYED ({m.cause_of_death})")
    return (f"{m.side_name} @ {m.hex} {m.facing}: HP {total_hp(m):g}, pilot hits {m.pilot_hits}, "
            f"engine {m.engine_hits}, gyro {m.gyro_hits}, heat {m.current_heat}"
            f"{' [' + ', '.join(flags) + ']' if flags else ''}")


# =============================================================================
# ==========================  ONE BATTLE  =====================================
# =============================================================================
EDGE_NAMES = ("N", "E", "S", "W")
OPPOSITE_EDGE = {"N": "S", "S": "N", "E": "W", "W": "E"}


def _edge_hexes(terrain_map, edge):
    """Hex labels along one edge of the board (CCRR: column 1-width, row 1-height)."""
    w, h = terrain_map["width"], terrain_map["height"]
    if edge in ("N", "S"):
        row = 1 if edge == "N" else h
        labels = [f"{c:02d}{row:02d}" for c in range(1, w + 1)]
    else:
        col = 1 if edge == "W" else w
        labels = [f"{col:02d}{r:02d}" for r in range(1, h + 1)]
    return [lab for lab in labels if lab in terrain_map["hexes"]]


def _deploy_home_edges(mech_red, mech_blue, terrain_map, battle_rng):
    """Default deployment (Core p.37): both sides roll 2D6 (rerolling ties);
    the loser chooses a home edge, the winner takes the one opposite. Each
    mech starts off the board and enters along its home edge in its first
    Movement Phase. Which edge the loser picks is a bot choice
    (config.HOME_EDGE_CHOICE)."""
    while True:
        red, blue = battle_rng.roll_2d6(), battle_rng.roll_2d6()
        if red != blue:
            break
    loser, winner = (mech_red, mech_blue) if red < blue else (mech_blue, mech_red)
    if config.HOME_EDGE_CHOICE == "random":
        edge = EDGE_NAMES[battle_rng.pick_number(len(EDGE_NAMES)) - 1]
    elif config.HOME_EDGE_CHOICE in EDGE_NAMES:
        edge = config.HOME_EDGE_CHOICE
    else:
        raise ValueError(f"Unknown HOME_EDGE_CHOICE {config.HOME_EDGE_CHOICE!r}")
    for mech, e in ((loser, edge), (winner, OPPOSITE_EDGE[edge])):
        mech.home_edge = _edge_hexes(terrain_map, e)
        mech.hex, mech.facing = None, "N"
        config.log(f"  Deployment: {mech.side_name} home edge {e} ({mech.home_edge[0]}-{mech.home_edge[-1]}).")
    config.log(f"  Deployment roll: Red {red}, Blue {blue} - {loser.side_name} chose its edge.")


def _after_phase(*mechs):
    """Severed limbs fall into their mech's hex; clubs that can't be held
    any more are dropped (INTEGRATION__clubs, Core p.79)."""
    for m in mechs:
        clubs.after_phase(m)


def run_battle(mech_red, mech_blue, terrain_map, battle_rng: BattleRNG,
               max_turns: Optional[int] = None) -> BattleResult:
    """Section 2's turn structure for up to max_turns turns, or until a mech
    is destroyed (checked after End Phase each turn)."""
    max_turns = max_turns if max_turns is not None else config.MAX_TURNS
    result = BattleResult()
    stats = {
        "Red": SideStats(name=f"Red ({mech_red.chassis} {mech_red.model})", max_hp=total_hp(mech_red)),
        "Blue": SideStats(name=f"Blue ({mech_blue.chassis} {mech_blue.model})", max_hp=total_hp(mech_blue)),
    }
    by_name = {"Red": mech_red, "Blue": mech_blue}
    clubs.reset_battle()
    if config.DEPLOYMENT == "home_edge":
        _deploy_home_edges(mech_red, mech_blue, terrain_map, battle_rng)
    elif config.DEPLOYMENT != "fixed_hexes":
        raise ValueError(f"Unknown DEPLOYMENT {config.DEPLOYMENT!r}")

    for turn in range(1, max_turns + 1):
        config.log(f"\n=== TURN {turn} ===")
        for m in (mech_red, mech_blue):
            piloting_rolls.snapshot_preexisting_damage(m)
            equip.start_turn(m, turn)

        loser_name = roll_initiative(battle_rng)
        winner_name = "Blue" if loser_name == "Red" else "Red"
        mover_first, mover_second = by_name[loser_name], by_name[winner_name]
        config.log(f"  Initiative: {loser_name} lost the roll, moves first.")

        for m in (mech_red, mech_blue):
            _reset_movement_state(m)
        _phase_movement(mover_first, mover_second, terrain_map, turn, battle_rng, moves_first=True)
        _phase_movement(mover_second, mover_first, terrain_map, turn, battle_rng, moves_first=False)

        _after_phase(mech_red, mech_blue)
        reports = attack_resolution.run_ranged_combat_phase(mover_first, mover_second, terrain_map, battle_rng)
        _after_phase(mech_red, mech_blue)
        for side, rep in reports.items():
            stats[side].attacks += rep.attacks
            stats[side].hits += rep.hits
            stats[side].damage_dealt += rep.damage_dealt

        physical.run_physical_phase(mover_first, mover_second, terrain_map, reports)
        _after_phase(mech_red, mech_blue)
        _phase_heat(mech_red, mech_blue, reports)
        _after_phase(mech_red, mech_blue)
        _phase_end(mech_red, mech_blue, turn, stats)

        config.log(f"  -- end of turn {turn}: {_status_line(mech_red)}")
        config.log(f"  -- end of turn {turn}: {_status_line(mech_blue)}")

        result.turns_taken = turn
        red_dead = is_destroyed(mech_red)
        blue_dead = is_destroyed(mech_blue)
        if red_dead or blue_dead:
            result.destroyed = "Both" if (red_dead and blue_dead) else ("Red" if red_dead else "Blue")
            config.log(f"\n>>> Battle over on turn {turn}: {result.destroyed} destroyed. <<<")
            break

    for side, m in by_name.items():
        s = stats[side]
        s.final_hp = total_hp(m)
        s.destroyed = is_destroyed(m)
        s.cause_of_death = m.cause_of_death if s.destroyed else None
        s.final_hex = m.hex
    result.red, result.blue = stats["Red"], stats["Blue"]
    if result.destroyed == "Red":
        result.winner = "Blue"
    elif result.destroyed == "Blue":
        result.winner = "Red"
    else:
        result.winner = "Draw"
    return result


# =============================================================================
# ==========================  BATCH LOOP  =====================================
# =============================================================================
# Parallel batches (2026-10-20, Claude - Pile 1; speed only, no rule here).
# Battles don't affect each other, so a batch can run several at once, one per
# CPU core (config.WORKERS). Two things make the output the same whatever the
# worker count:
#   - Each battle has its OWN seed (battle_seed below), so its dice don't depend
#     on which battles ran before it or where. Battle 1 uses SEED itself, so a
#     one-battle run is the same as before this change; battles 2+ of a batch
#     differ from the old single shared stream (statistically the same).
#   - A worker captures its battle's printed log (stdout and the stderr stub
#     lines) and the parent prints the logs in battle order.
# Workers are started with "spawn" on every platform (Windows can't do anything
# else), so each one re-imports the code: the parent hands each worker its
# settings (config's UPPERCASE names - including any changed at run time), the
# map and the two parsed mechs, so nothing is re-read from disk.

def battle_seed(seed: Optional[int], sim: int) -> Optional[int]:
    """The seed for battle number `sim` (1-based) of a batch seeded with `seed`.
    Battle 1 uses `seed` itself; later battles get a number mixed from (seed,
    sim) by numpy's SeedSequence, so batches with nearby seeds (5, 6, ...) don't
    share battles. None (fresh entropy) stays None."""
    if seed is None:
        return None
    if sim == 1:
        return seed
    return int(np.random.SeedSequence([seed, sim]).generate_state(1, np.uint64)[0] >> 1)


def _run_one_battle(sim, num_simulations, seed, max_turns, template_red, template_blue, terrain_map):
    """One battle of a batch with its own BattleRNG, fresh mech copies and
    per-battle caches reset. Returns the BattleResult."""
    config.log("\n" + "=" * 70)
    config.log(f"=== SIMULATION {sim}/{num_simulations} ===")
    config.log("=" * 70)

    sim_seed = battle_seed(seed, sim)
    battle_rng = BattleRNG(seed=sim_seed)
    config.set_active_rng(battle_rng)
    if sim_seed is not None:
        # MECHSIM hit_location.py's tripod leg sub-roll uses Python's random
        # module directly. Seeding it keeps same-seed runs identical (it still
        # isn't drawn from the BattleRNG stream - noted in KNOWN_MISSING_RULES).
        random.seed(sim_seed)

    stubs.reset_battle_stubs()
    weapon_selection.reset_table_cache()

    mech_red = clone_mech(template_red)
    mech_blue = clone_mech(template_blue)
    _attach_mech_config(mech_red, config.MECH_RED_CONFIG, "Red")
    _attach_mech_config(mech_blue, config.MECH_BLUE_CONFIG, "Blue")

    result = run_battle(mech_red, mech_blue, terrain_map, battle_rng, max_turns)
    result.active_stubs = stubs.active_stubs()
    result.seed = sim_seed
    return result


# What one worker process keeps between battles (set by _worker_init).
_WORKER = {}


def _config_snapshot():
    """config's UPPERCASE settings that can be sent to a worker process."""
    snap = {}
    for name, value in vars(config).items():
        if name.isupper():
            try:
                pickle.dumps(value)
            except Exception:
                continue        # e.g. a module or a function - not a setting
            snap[name] = value
    return snap


def _worker_init(settings, template_red, template_blue, terrain_map):
    for name, value in settings.items():
        setattr(config, name, value)
    _WORKER.update(red=template_red, blue=template_blue, terrain_map=terrain_map)


def _worker_battle(args):
    """Runs one battle in a worker; returns (result, its stdout, its stderr)."""
    sim, num_simulations, seed, max_turns = args
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        result = _run_one_battle(sim, num_simulations, seed, max_turns,
                                 _WORKER["red"], _WORKER["blue"], _WORKER["terrain_map"])
    return result, out.getvalue(), err.getvalue()


def worker_count(num_simulations: int) -> int:
    """How many battles run at once: config.WORKERS (0 = one per CPU core),
    never more than the batch size; 1 with MANUAL_ROLLS (it asks for input)."""
    if config.MANUAL_ROLLS or num_simulations <= 1:
        return 1
    workers = config.WORKERS if config.WORKERS > 0 else (os.cpu_count() or 1)
    return max(1, min(workers, num_simulations))


def run_batch(num_simulations: Optional[int] = None, seed: Optional[int] = None,
              max_turns: Optional[int] = None) -> List[BattleResult]:
    """Loads the map and both mechs ONCE, then runs num_simulations battles,
    each on fresh clone_mech() copies (compute-once rule, Section 7), in
    parallel when worker_count() > 1. Prints the batch summary
    (INTEGRATION__results.summarize) and returns the raw List[BattleResult]
    in battle order."""
    num_simulations = num_simulations if num_simulations is not None else config.NUM_SIMULATIONS
    max_turns = max_turns if max_turns is not None else config.MAX_TURNS
    seed = seed if seed is not None else config.SEED

    terrain_map = _load_map()
    template_red, template_blue, red_path, blue_path = config.load_two_mechs()

    results: List[BattleResult] = []
    workers = worker_count(num_simulations)
    if workers == 1:
        for sim in range(1, num_simulations + 1):
            results.append(_run_one_battle(sim, num_simulations, seed, max_turns,
                                           template_red, template_blue, terrain_map))
    else:
        jobs = [(sim, num_simulations, seed, max_turns) for sim in range(1, num_simulations + 1)]
        context = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=workers, mp_context=context, initializer=_worker_init,
                                 initargs=(_config_snapshot(), template_red, template_blue, terrain_map)) as pool:
            # map() hands results back in battle order, so the logs print in order.
            for result, out, err in pool.map(_worker_battle, jobs):
                sys.stdout.write(out)
                sys.stdout.flush()
                sys.stderr.write(err)
                sys.stderr.flush()
                results.append(result)

    summarize(results,
              f"{template_red.chassis} {template_red.model}",
              f"{template_blue.chassis} {template_blue.model}")
    return results


if __name__ == "__main__":
    run_batch()
