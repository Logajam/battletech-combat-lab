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
import time
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
    gyro_destroyed,
)
import piloting_rolls  # noqa: E402 - MECHSIM

# --- PATHFINDER side ---
PATHFINDER_DIR = os.environ.get(
    "PATHFINDER_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "pathfinder")
)
if PATHFINDER_DIR not in sys.path:
    sys.path.insert(0, PATHFINDER_DIR)
import board_parser  # noqa: E402 - PATHFINDER
import terrain_rules  # noqa: E402 - PATHFINDER
import hex_geometry  # noqa: E402 - PATHFINDER
import combat  # noqa: E402 - PATHFINDER; build_jump_states/classify_movement_mode/fc_to_tmm/MODE_TO_AMM

from INTEGRATION__rng import BattleRNG  # noqa: E402
import INTEGRATION__weapon_selection as weapon_selection  # noqa: E402
import INTEGRATION__heat as heat  # noqa: E402
import INTEGRATION__equipment_systems as equip  # noqa: E402
import INTEGRATION__ammo as ammo  # noqa: E402
import INTEGRATION__electronics as electronics  # noqa: E402
import INTEGRATION__fire_modes as fire_modes  # noqa: E402
import INTEGRATION__physical as physical  # noqa: E402
import INTEGRATION__movement_selection as movement_selection  # noqa: E402
import INTEGRATION__ranged_combat as ranged_combat  # noqa: E402
import INTEGRATION__stubs as stubs  # noqa: E402
import INTEGRATION__attack_resolution as attack_resolution  # noqa: E402
import INTEGRATION__arcs as arcs  # noqa: E402
import INTEGRATION__clubs as clubs  # noqa: E402
import INTEGRATION__replay as replay  # noqa: E402
import INTEGRATION__timing as timing  # noqa: E402
import INTEGRATION__water as water  # noqa: E402
import INTEGRATION__deployment as deployment  # noqa: E402
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
    # Refuses terrain the simulator can't play yet, and sets up buildings
    # (config.PASSIVE_BUILDINGS) - see pathfinder/terrain_rules.py.
    terrain_rules.prepare_board(terrain_map, passive_buildings=config.PASSIVE_BUILDINGS)
    buildings = sum(1 for info in terrain_map["hexes"].values() if info.get("building"))
    config.log(f"  Map loaded: {terrain_map['width']}x{terrain_map['height']}, "
               f"{len(terrain_map['hexes'])} hexes"
               + (f", {buildings} building hexes (passive)." if buildings else "."))
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
    # Movement search per side (2026-10-21): None = config.MOVEMENT_SEARCH /
    # MOVEMENT_ASSUMED_ENEMY_SEARCH (movement_selection.own_search / assumed_enemy_search).
    mech.move_search = cfg.get("search")
    mech.assumes_enemy_search = cfg.get("assumes_enemy_search")
    mech.current_heat = 0
    mech.shutdown = False
    mech.deactivated_heat_sinks = 0
    heat.attach_heat_traits(mech)
    ammo.attach_ammo(mech)
    electronics.attach(mech)          # Artemis links, ECM suites, Narc pods (2026-10-20)
    fire_modes.attach(mech)           # Apollo links, Rotary AC jams (2026-10-20)
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
    mech.deferred_end_of_move = None     # a charger's / DFA's end-of-movement PSRs (pp.78, 80)


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
        "jump": water.jump_mp(mech),             # leg jets in depth 1, none deeper (p.50)
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
    max_turns = min(walk, 1 if gyro_destroyed(mover) else 3)
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
    """One mech's movement, with the enemy's hex closed to its ground moves
    while it moves (p.48: "cannot enter a hex occupied by an enemy 'Mech
    unless that 'Mech is immobile"; 2026-10-21 - before, a path could pass
    through it, only ending there was excluded). Jumps pass over it."""
    mover.blocked_hex = (hex_geometry.parse_hex_label(other.hex)
                         if other.hex is not None and not is_immobile(other) else None)
    try:
        _move(mover, other, terrain_map, turn_number, battle_rng, moves_first)
    finally:
        mover.blocked_hex = None             # the modeled reply (movement_selection) never blocks


def _move(mover, other, terrain_map, turn_number, battle_rng, moves_first):
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
    with timing.section("picking a spot"):
        pick, why = movement_selection.choose(mover, other, terrain_map, battle_rng, moves_first,
                                              standup_mp=standup_mp, entry_edge=entry_edge)
    if pick is None and entry_edge is not None:
        # "A unit must move onto the battlefield ... If it cannot, it is destroyed." (p.37)
        mover.destroyed, mover.cause_of_death = True, "Could Not Enter Battlefield"
        config.log(f"  [Movement] {name}: can't enter the battlefield - destroyed.")
        return
    config.log(f"  [Movement select] {name}: {why}")

    fell = None
    if pick is not None:
        start = "off the board" if entry_edge is not None else f"{mover.hex} {mover.facing}"
        backward = config.VERBOSE and _needs_backward_move(mover, pick, terrain_map, standup_mp, entry_edge)
        # The movement subphase (Daniel, 2026-10-21): walk the planned path; a
        # terrain PSR failed on the way drops the mech there, and it re-plans.
        fell = _walk_path(mover, pick, terrain_map, standup_mp, entry_edge)
    if pick is not None and fell is not None:
        budget = standup_mp if standup_mp is not None else (mp["run"] if pick["mode"] == "Run" else mp["walk"])
        _after_fall_midmove(mover, other, pick, fell, budget, terrain_map, battle_rng, moves_first, start)
    elif pick is not None:
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
    if (psr_mode == "running" and mover.move_fc < 1) or mover.prone:
        psr_mode = None                      # a prone mech (it fell on the way) makes no PSRs (p.51)
    # These are rolled "at the end of a 'Mech's movement" (p.113), so a
    # failure falls in the END hex - the rule, not a simplification (checked
    # 2026-10-21). A mech that declared a charge or a DFA hasn't finished
    # moving: it rolls them (and any PSR for the hex it enters or lands in)
    # in the Physical Attack Phase, after the attack (pp.78, 80) -
    # INTEGRATION__movement_attacks.end_of_movement_triggers.
    if mover.charging is not None or mover.dfa is not None:
        mover.deferred_end_of_move = {"mode": psr_mode, "from_hex": mover.hex}
        if psr_mode is not None and piloting_rolls.movement_psr_trigger(mover, psr_mode):
            config.log(f"  [Movement] {name}'s end-of-movement PSRs wait for the Physical Attack Phase "
                       f"(its movement ends with the {'charge' if mover.charging is not None else 'DFA'}, pp.78, 80).")
    else:
        if psr_mode is not None:
            _with_piloting(mover, piloting_rolls.check_movement_psr, psr_mode)
        _landing_psr(mover)
    if booster_failures and not is_destroyed(mover):
        # Failed MASC / supercharger: damage, then any PSR it forces, at the
        # end of movement (p.204) - the PSR uses the damage-this-phase triggers.
        piloting_rolls.snapshot_pre_attack_phase(mover)
        equip.apply_booster_failures(mover, booster_failures)
        _with_piloting(mover, piloting_rolls.resolve_attack_phase_psr)
    piloting_rolls.resolve_consciousness_checks(mover, "Movement Phase")


def _landing_psr(mover):
    """A jump that lands in depth 1+ water forces a PSR with no modifier for
    the depth, and a failure falls the hex's depth in levels to the bottom
    (p.50); landing in rubble forces its +0 PSR (p.48 - "any PSR-related
    effects for the hex it lands in are applied", p.50). Falls in water take
    half damage (p.115, piloting_rolls.resolve_fall). Ground moves roll their
    terrain PSRs hex by hex in _walk_path."""
    if mover.prone or is_destroyed(mover) or mover.hex is None or mover.move_mode != "Jump":
        return
    info = water.board()["hexes"][mover.hex] if water.board() is not None else None
    depth = water.depth_at(mover.hex)
    modifier = piloting_rolls.preexisting_modifier(mover) + piloting_rolls.special_case_modifier(mover)
    checks = []
    if depth >= 1:
        checks.append((f"Jumped into water (depth {depth})", depth))
    if info is not None and "rubble" in info["features"]:
        checks.append(("Landed in rubble", 0))

    def roll(mech):
        for what, levels in checks:
            if mech.prone:
                return
            if not piloting_rolls.roll_psrs(mech, 1, modifier, f"{what} PSR"):
                piloting_rolls.resolve_fall(mech, cause=f"{what.lower()}, failed PSR", levels=levels)
    if checks:
        _with_piloting(mover, roll)


def _walk_path(mover, pick, terrain_map, standup_mp, entry_edge):
    """The movement subphase (Daniel, 2026-10-21: "There is a difference
    between planning where you want to go which the picker does. And actually
    getting there, which is needed when piloting skill rolls are required for
    entering terrain"): walk the ground path to the pick (ranged_combat.
    path_to) hex by hex, making each terrain PSR where it happens - rubble,
    sand with a level change, water when running, a backward level change
    (terrain_rules.step_psr_causes), a facing change in mud when running
    (-1, p.124). Returns None when the mech gets there (or no roll was
    needed), else (hex, facing, MP spent, hexes moved) where it fell - a
    backward level change falls in the lower of the two hexes (p.46)."""
    if pick["mode"] not in ("Walk", "Run") or not terrain_rules.has_psr_terrain(terrain_map):
        return None
    x, y = hex_geometry.parse_hex_label(pick["hex"])
    key = (x, y, hex_geometry.compass_to_facing(pick["facing"]), pick["fc"], pick["mode"], pick["mp_spent"])
    if not getattr(mover, "path_psrs", {}).get(key):
        return None                          # nothing on the way forces a roll
    path = ranged_combat.path_to(mover, terrain_map, pick, standup_mp, entry_edge)
    if path is None:
        config.log(f"  [Movement] {mover.side_name}: path to {pick['hex']} not found - moved there without "
                   f"terrain PSRs.")
        return None
    hexes = terrain_map["hexes"]
    running = pick["mode"] == "Run"
    base = piloting_rolls.preexisting_modifier(mover) + piloting_rolls.special_case_modifier(mover)
    here, facing, moved = mover.hex, mover.facing, 0
    for step, (sx, sy, sf), mp_after in path:
        label, facing = hex_geometry.hex_label(sx, sy), hex_geometry.facing_to_compass(sf)
        if step == "turn":
            causes = ["mud"] if running and "mud" in hexes[here]["features"] else []
            fall_at = here
        else:
            from_info = None if step == "enter" else hexes[here]
            causes = terrain_rules.step_psr_causes(from_info, hexes[label], step == "backward", running)
            fall_at = label
            if step == "backward" and from_info is not None and from_info["level"] < hexes[label]["level"]:
                fall_at = here                # p.46: the lower of the two hexes
            here, moved = label, moved + 1
        for cause in causes:
            modifier = base + terrain_rules.PSR_MODIFIER[cause]

            def roll(mech, cause=cause, modifier=modifier, label=label):
                return piloting_rolls.roll_psrs(mech, 1, modifier, f"[Movement] {mech.side_name}: {cause} PSR "
                                                                   f"at {label}")
            if not _with_piloting(mover, roll):
                mover.hex, mover.facing = fall_at, facing
                _with_piloting(mover, piloting_rolls.resolve_fall, cause=f"failed {cause} PSR at {fall_at}")
                return fall_at, facing, mp_after, moved
    return None


def _after_fall_midmove(mover, other, pick, fell, budget, terrain_map, battle_rng, moves_first, start):
    """A terrain PSR failed partway through the move (Daniel, 2026-10-21: "A
    failure and subsequent results would cause that mech to recalculate its
    movement starting from its current state"): the mech lies where it fell
    with the MP it hasn't spent; it may try to stand with them (p.51 - "as
    long as it has enough MP left and did not jump"), and if it stands with
    MP to spare it picks a new spot from there, walked the same way - again
    and again, until it gets there, runs out of MP or stays down. The move
    keeps its declared mode; its hexes and MP add up."""
    label, facing, used, moved = fell
    mover.move_mode, mover.move_fc, mover.mp_spent = pick["mode"], moved, used
    config.log(f"  [Movement] {mover.side_name}: {start} -> fell at {label} {facing} after {used} MP "
               f"({moved} hexes) of a planned {pick['mode']} to {pick['hex']} {pick['facing']}.")
    while not is_destroyed(mover) and mover.prone:
        remaining = budget - mover.mp_spent
        if remaining <= 0 or not piloting_rolls.can_stand(mover) or mover.pilot_hits >= 5:
            break
        left = _with_piloting(mover, piloting_rolls.resolve_stand_up, mp_available=remaining)
        mover.mp_spent = budget - left if not mover.prone else budget
        if mover.prone or is_destroyed(mover) or left <= 0:
            break
        pick2, why = movement_selection.choose(mover, other, terrain_map, battle_rng, moves_first, standup_mp=left)
        config.log(f"  [Movement select] {mover.side_name} (stood up again, {left} MP left): {why}")
        if pick2 is None:
            break
        fell2 = _walk_path(mover, pick2, terrain_map, left, None)
        if fell2 is None:
            mover.hex, mover.facing = pick2["hex"], pick2["facing"]
            mover.move_fc += pick2["fc"]
            mover.mp_spent += pick2["mp_spent"]
            break
        label, facing, used2, moved2 = fell2
        mover.move_fc += moved2
        mover.mp_spent += used2
        config.log(f"  [Movement] {mover.side_name}: fell again at {label} {facing}.")
    mover.movement_heat = heat.movement_heat(mover, mover.move_mode, mover.move_fc)
    config.log(f"  [Movement] {mover.side_name}: ends at {mover.hex} {mover.facing}{' (prone)' if mover.prone else ''}, "
               f"{mover.move_mode} ({mover.mp_spent} MP, {mover.move_fc} hexes, {mover.movement_heat} heat).")


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
        if not is_destroyed(m):
            water.drowning(m, heat.has_life_support_hit(m))     # p.117 (2026-10-21)
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
        # Where it may start its movement: config.DEPLOYMENT_DEPTH hexes in, roofs
        # included, never a stuck hex - the override goes deeper (INTEGRATION__deployment,
        # Daniel 2026-10-21).
        start = deployment.start_hexes(mech, terrain_map, e)
        mech.home_edge = start["hexes"]
        mech.home_edge_row = _edge_hexes(terrain_map, e)          # where an enemy heads before it has entered
        mech.hex, mech.facing = None, "N"
        if start["depth"] == 0 and not start["stuck"] and mech.home_edge == _edge_hexes(terrain_map, e):
            config.log(f"  Deployment: {mech.side_name} home edge {e} ({mech.home_edge[0]}-{mech.home_edge[-1]}).")
        else:
            override = " (stuck-terrain override)" if start["depth"] != config.DEPLOYMENT_DEPTH else ""
            left_out = f", {len(start['stuck'])} stuck hexes left out" if start["stuck"] else ""
            config.log(f"  Deployment: {mech.side_name} home edge {e}, starting up to {start['depth']} hexes in"
                       f"{override}: {len(mech.home_edge)} start hexes{left_out}.")
    config.log(f"  Deployment roll: Red {red}, Blue {blue} - {loser.side_name} chose its edge.")


def _after_phase(*mechs):
    """Severed limbs fall into their mech's hex; clubs that can't be held
    any more are dropped (INTEGRATION__clubs, Core p.79); a location with no
    armor left under water is breached (INTEGRATION__water, p.127)."""
    for m in mechs:
        clubs.after_phase(m)
        if not is_destroyed(m):
            water.auto_breaches(m)


def run_battle(mech_red, mech_blue, terrain_map, battle_rng: BattleRNG,
               max_turns: Optional[int] = None) -> BattleResult:
    """Section 2's turn structure for up to max_turns turns, or until a mech
    is destroyed (checked after End Phase each turn)."""
    max_turns = max_turns if max_turns is not None else config.MAX_TURNS
    result = BattleResult(turn_cap=max_turns)
    stats = {
        "Red": SideStats(name=f"Red ({mech_red.chassis} {mech_red.model})", max_hp=total_hp(mech_red)),
        "Blue": SideStats(name=f"Blue ({mech_blue.chassis} {mech_blue.model})", max_hp=total_hp(mech_blue)),
    }
    by_name = {"Red": mech_red, "Blue": mech_blue}
    clubs.reset_battle()
    water.set_board(terrain_map)          # heat sinks, falls, jump jets read the hex's depth (2026-10-21)
    if config.DEPLOYMENT == "home_edge":
        _deploy_home_edges(mech_red, mech_blue, terrain_map, battle_rng)
    elif config.DEPLOYMENT != "fixed_hexes":
        raise ValueError(f"Unknown DEPLOYMENT {config.DEPLOYMENT!r}")
    for m in (mech_red, mech_blue):
        m.hp_log = []
        movement_selection.record_hp(m)      # the history blend's record (config.MOVEMENT_LIFETIME_HISTORY_K)
    replay.mark(0, "Deployment")

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
        for m in (mover_first, mover_second):
            fire_modes.declare_unjams(m)     # Rotary AC unjam attempts are declared in the Movement Phase (p.183)
        with timing.section("movement"):
            _phase_movement(mover_first, mover_second, terrain_map, turn, battle_rng, moves_first=True)
        replay.mark(turn, f"{loser_name} moves")
        with timing.section("movement"):
            _phase_movement(mover_second, mover_first, terrain_map, turn, battle_rng, moves_first=False)
        replay.mark(turn, f"{winner_name} moves")

        if mech_red.hex is None or mech_blue.hex is None:
            # A mech that couldn't enter the battlefield is destroyed (p.37) and
            # never got a hex - e.g. a Solaris arena whose home edge is all wall
            # (2026-10-21). Nothing else can happen this turn.
            result.turns_taken = turn
            red_dead, blue_dead = is_destroyed(mech_red), is_destroyed(mech_blue)
            result.destroyed = "Both" if (red_dead and blue_dead) else ("Red" if red_dead else "Blue")
            config.log(f"\n>>> Battle over on turn {turn}: {result.destroyed} destroyed "
                       f"(couldn't enter the battlefield). <<<")
            break

        _after_phase(mech_red, mech_blue)
        with timing.section("ranged attacks"):
            reports = attack_resolution.run_ranged_combat_phase(mover_first, mover_second, terrain_map, battle_rng)
        _after_phase(mech_red, mech_blue)
        replay.mark(turn, "Ranged attacks")
        for side, rep in reports.items():
            stats[side].attacks += rep.attacks
            stats[side].hits += rep.hits
            stats[side].damage_dealt += rep.damage_dealt

        with timing.section("physical attacks"):
            physical.run_physical_phase(mover_first, mover_second, terrain_map, reports)
        _after_phase(mech_red, mech_blue)
        replay.mark(turn, "Physical attacks")
        with timing.section("heat phase"):
            _phase_heat(mech_red, mech_blue, reports)
        _after_phase(mech_red, mech_blue)
        with timing.section("end phase"):
            _phase_end(mech_red, mech_blue, turn, stats)

        config.log(f"  -- end of turn {turn}: {_status_line(mech_red)}")
        config.log(f"  -- end of turn {turn}: {_status_line(mech_blue)}")
        for m in (mech_red, mech_blue):
            movement_selection.record_hp(m)
        replay.mark(turn, "Heat and end phase")

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

    recording = sim <= config.REPLAY_BATTLES
    if recording:
        replay.start(mech_red, mech_blue, terrain_map, sim_seed, sim)
    timing.take()                          # nothing carried over from outside this battle
    prof = timing.start_profile()
    with timing.section("battle"):
        result = run_battle(mech_red, mech_blue, terrain_map, battle_rng, max_turns)
    result.profile = timing.stop_profile(prof)
    result.timing = timing.take() if config.TIMING else None
    result.active_stubs = stubs.active_stubs()
    result.seed = sim_seed
    if recording:
        result.replay = replay.finish(result)
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

    started = time.perf_counter()
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
    if config.TIMING:
        timing.report(results, time.perf_counter() - started, workers)
    for result in results:
        if result.replay is not None:
            print(f"Replay saved: {replay.write(result.replay)}")
    return results


if __name__ == "__main__":
    run_batch()
