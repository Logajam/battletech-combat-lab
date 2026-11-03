"""
INTEGRATION__saved_state.py - saved states: stop a battle, play on later (2026-11-03).

Daniel, 2026-11-03: "load the board, units, their states and positions, and probably a
count of how many rnd numbers have been used, and from there the engine will just continue
from there given the starting seed". A branch keeps the same dice from the branch point by
default, with a switch for fresh dice (his call, same day).

WHAT A SAVED STATE HOLDS (taken at the end of a turn, after the End Phase)
  - The battle (orchestrator.Battle): every unit with all of its state (position, facing,
    twist, prone, heat, damage, criticals, ammo in each bin, jams, pilot hits, pending
    PSRs, its HP history...), the board as it now stands (smoke, broken magma crust,
    damage), the running result and per-unit stats, and the turn reached.
  - The dice: the battle's one BattleRNG (config "ONE POOL OF DICE"). Its numpy
    generator's own state and its place in the current block of 2d6 rolls are saved,
    not a count of rolls used - the block refills and the separate crit-slot picks mix
    in between, so one count would not say where the stream is.
  - The bots' memories, which change what they do next: Princess's heat map and posture
    (INTEGRATION__princess_memory), Legate's cached team-fire damage, severed limbs lying
    on the board (clubs), the stub counts.
  - Every setting (config's UPPERCASE names): a battle played on runs under the rules
    it started with.
  Pure caches (weapon tables, kill curves, line of sight, path tables) are NOT saved:
  they are emptied on load and rebuild themselves to the same values.

THE FILE
  JSON, in two parts: a readable header (version, seed, turn, each unit's position,
  heat and armor - the replay's own unit summary) for people and for the GUI to come,
  and "engine": the exact state, packed (Python pickle, compressed, base64). The exact
  part is Python-only for now; a readable engine state goes with the engine interface
  for the faster-language port (PROJECT_MAP Pick up here 13).

THE CHECK
  `python tests/check_reference_logs.py --round-trip` plays every reference battle saving,
  reloading and playing on from the reloaded copy after EVERY turn: each log must match the
  battle that never stopped, byte for byte. Anything a save forgets shows up there.

USE
  config.SAVE_STATE_TURNS / SAVE_STATE_BATTLES / SAVE_STATE_DIR write files during a run.
  python INTEGRATION__saved_state.py <file> [--turns N] [--fresh-dice SEED]
  plays on from a file and prints the log (the same dice by default).

Not yet (next steps): saves inside a turn (after each phase or each unit's move), and the
replay of a battle played on from a save (it records from the load point only if started).
"""

import base64
import json
import os
import pickle
import sys
import zlib

import INTEGRATION__config as config
import INTEGRATION__orchestrator as orchestrator  # noqa: F401 - first: it puts MECHSIM / PATHFINDER on the path
import INTEGRATION__clubs as clubs
import INTEGRATION__forces as forces
import INTEGRATION__hazards as hazards
import INTEGRATION__kill_curve as kill_curve
import INTEGRATION__legate as legate
import INTEGRATION__princess_fire as princess_fire
import INTEGRATION__princess_memory as princess_memory
import INTEGRATION__replay as replay
import INTEGRATION__smoke as smoke
import INTEGRATION__stubs as stubs
import INTEGRATION__water as water
import INTEGRATION__weapon_selection as weapon_selection
from INTEGRATION__rng import BattleRNG

FORMAT = "battletech-monte-carlo-sim saved state"
VERSION = 1


# =============================================================================
# ==========================  UNITS BY NAME  ==================================
# =============================================================================
# Some bot memories are keyed by id(unit) - a number that changes when the units are
# rebuilt from a file. They are stored by the unit's side_name (unique in a battle)
# and turned back into the new ids on load.
def _ids_to_names(units):
    return {id(u): u.side_name for u in units}


def _names_to_ids(units):
    return {u.side_name: id(u) for u in units}


def _friend_dmg_keys(table, mapping):
    """legate._FRIEND_DMG: (id(unit), its state, id(enemy), enemy state) -> damage."""
    return {(mapping[k[0]], k[1], mapping[k[2]], k[3]): v for k, v in table.items()
            if k[0] in mapping and k[2] in mapping}


def _team_plans(plans, mapping):
    """legate._PLANS / _OWN: team -> {id(unit): estimated end state}."""
    return {team: {mapping[k]: v for k, v in by_unit.items() if k in mapping} for team, by_unit in plans.items()}


# A destroyed critical slot's record (mech.destroyed_slot_info, MECHSIM damage_resolution) names
# the destroyed component by id(component): ECM, Artemis, ammo bins, heat sinks, shields... are
# "dead" when their id is in that table. The round-trip check found it (2026-11-03): reloaded,
# every id is new, so a destroyed Artemis FCS came back to life. The save keeps the component
# itself beside each record (found by walking the unit's objects) and points the record at the
# rebuilt component on load.
def _objects_by_id(root):
    """{id(obj): obj} for every object reachable from `root` (attributes, lists, dicts, sets)."""
    found, stack = {}, [root]
    while stack:
        obj = stack.pop()
        if id(obj) in found or isinstance(obj, (str, int, float, bool, bytes, type(None))):
            continue
        found[id(obj)] = obj
        if isinstance(obj, dict):
            stack.extend(obj.keys())
            stack.extend(obj.values())
        elif isinstance(obj, (list, tuple, set, frozenset)):
            stack.extend(obj)
        elif hasattr(obj, "__dict__"):
            stack.extend(vars(obj).values())
    return found


def _dead_components(units):
    """[(side_name, slot key, the component the record names)] for every destroyed slot with an id."""
    out = []
    for u in units:
        records = [(k, info["instance_id"]) for k, info in getattr(u, "destroyed_slot_info", {}).items()
                   if info.get("instance_id") is not None]
        if not records:
            continue
        reachable = _objects_by_id(u)
        for key, ident in records:
            # Not reachable any more: the id named a component nothing holds - keep a stand-in
            # that never matches a live component, as the old id could not.
            out.append((u.side_name, key, reachable.get(ident, _GONE)))
    return out


class _Gone:
    """A destroyed component no longer held by its unit (see _dead_components)."""


_GONE = _Gone()


def _repoint_dead_components(units, dead):
    by_name = {u.side_name: u for u in units}
    for name, key, component in dead:
        by_name[name].destroyed_slot_info[key]["instance_id"] = id(component)


# =============================================================================
# ==========================  CAPTURE AND RESTORE  ============================
# =============================================================================
def _module_state(battle):
    """The per-battle state that lives in modules, not on the units."""
    names = _ids_to_names(battle.units)
    teams = {}
    for team, memory in princess_memory._TEAMS.items():
        memory_copy = pickle.loads(pickle.dumps(memory))          # keep the live one untouched
        memory_copy.heat.last_known = {names[k]: v for k, v in memory.heat.last_known.items() if k in names}
        teams[team] = memory_copy
    return {
        "stubs": dict(stubs._ACTIVE),
        "limbs_on_ground": dict(clubs._LIMBS_ON_GROUND),
        "legate": {"plans": _team_plans(legate._PLANS, names), "own": _team_plans(legate._OWN, names),
                   "friend_dmg": _friend_dmg_keys(legate._FRIEND_DMG, names)},
        "princess_teams": teams,
        "broken_crust": list(hazards._BROKEN),    # hex infos inside the board: pickled with it, so they stay its own
        "smoky": set(smoke._SMOKY),
        "dead_components": _dead_components(battle.units),   # pickled with the battle: the same objects
    }


def _restore_modules(battle, state):
    units, board = battle.units, battle.terrain_map
    ids = _names_to_ids(units)
    # Pure caches: emptied, so no entry keyed by an old object's id can be hit by a new object.
    weapon_selection.reset_table_cache()
    kill_curve._CACHE.clear()
    princess_fire.reset_assigned()
    legate.reset()
    # The battle's board and units, as _start_battle sets them - without its fresh-battle resets.
    forces.set_battle(units)
    water.set_board(board)
    hazards._BOARD = board
    hazards._BROKEN[:] = state["broken_crust"]
    smoke._BOARD = board
    smoke._SMOKY.clear()
    smoke._SMOKY.update(state["smoky"])
    config.set_active_rng(battle.battle_rng)
    _repoint_dead_components(units, state["dead_components"])
    # Memories.
    stubs._ACTIVE.clear()
    stubs._ACTIVE.update(state["stubs"])
    clubs._LIMBS_ON_GROUND.clear()
    clubs._LIMBS_ON_GROUND.update(state["limbs_on_ground"])
    legate._PLANS.update(_team_plans(state["legate"]["plans"], ids))
    legate._OWN.update(_team_plans(state["legate"]["own"], ids))
    legate._FRIEND_DMG.update(_friend_dmg_keys(state["legate"]["friend_dmg"], ids))
    princess_memory.reset()
    for team, memory in state["princess_teams"].items():
        memory.heat.last_known = {ids[k]: v for k, v in memory.heat.last_known.items() if k in ids}
        princess_memory._TEAMS[team] = memory


def _settings():
    """config's UPPERCASE settings that can be saved (orchestrator's worker snapshot)."""
    return orchestrator._config_snapshot()


def capture(battle) -> dict:
    """The saved state of `battle` (an orchestrator.Battle at the end of a turn), as a
    JSON-ready dict. Taking it changes nothing in the battle."""
    engine = {"battle": battle, "modules": _module_state(battle), "settings": _settings()}
    packed = base64.b64encode(zlib.compress(pickle.dumps(engine, pickle.HIGHEST_PROTOCOL), 6)).decode("ascii")
    return {
        "format": FORMAT,
        "version": VERSION,
        "seed": battle.battle_rng.seed,
        "turn": battle.turn,
        "max_turns": battle.max_turns,
        "teams": battle.team_list,
        "units": {u.side_name: dict(replay._mech_header(u), team=u.team, **replay._mech_state(u))
                  for u in battle.units},
        "engine": packed,
    }


def restore(saved: dict, apply_settings=True, fresh_dice=None):
    """An orchestrator.Battle rebuilt from capture()'s dict, with every module set to play on.
    apply_settings: put the saved settings back into config (False keeps today's - a
    "what if" under other settings). fresh_dice: None = the same dice as the battle that
    was saved; an int = a new pool seeded with it from here on."""
    if saved.get("format") != FORMAT:
        raise ValueError("not a saved state")
    if saved.get("version") != VERSION:
        raise ValueError(f"saved state version {saved.get('version')}, this code reads {VERSION}")
    engine = pickle.loads(zlib.decompress(base64.b64decode(saved["engine"])))
    if apply_settings:
        for name, value in engine["settings"].items():
            setattr(config, name, value)
    battle = engine["battle"]
    if fresh_dice is not None:
        battle.battle_rng = BattleRNG(seed=fresh_dice)
    _restore_modules(battle, engine["modules"])
    return battle


def round_trip(battle):
    """Saved to text and loaded back (the --round-trip check): the copy to play on with."""
    return restore(json.loads(json.dumps(capture(battle))), apply_settings=False)


# =============================================================================
# ==========================  FILES  ==========================================
# =============================================================================
def save(battle, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(capture(battle), f, indent=1)
    return path


def load(path, apply_settings=True, fresh_dice=None):
    with open(path, "r", encoding="utf-8") as f:
        return restore(json.load(f), apply_settings=apply_settings, fresh_dice=fresh_dice)


def wants_save(turn) -> bool:
    turns = config.SAVE_STATE_TURNS
    return turns == "all" or (bool(turns) and turn in turns)


def file_name(sim, seed, turn):
    folder = config.SAVE_STATE_DIR
    if not os.path.isabs(folder):
        folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), folder)
    return os.path.join(folder, f"battle{sim}_seed{seed}_turn{turn:03d}.json")


def after_turn_hook(sim, seed):
    """The orchestrator's after_turn for battle `sim`: saves files where asked and,
    with SAVE_STATE_ROUND_TRIP, plays on from a reloaded copy. None if neither applies."""
    saving = sim <= config.SAVE_STATE_BATTLES and bool(config.SAVE_STATE_TURNS)
    if not saving and not config.SAVE_STATE_ROUND_TRIP:
        return None

    def hook(battle):
        if saving and wants_save(battle.turn):
            save(battle, file_name(sim, seed, battle.turn))
        if config.SAVE_STATE_ROUND_TRIP:
            return round_trip(battle)
        return None
    return hook


def play_on_from(path, turns=None, fresh_dice=None):
    """Loads a saved state and plays on (up to `turns` more turns, else to its cap); returns the result."""
    battle = load(path, fresh_dice=fresh_dice)
    if turns is not None:
        battle.max_turns = min(battle.max_turns, battle.turn + turns)
        battle.result.turn_cap = battle.max_turns
    config.log(f"=== PLAYING ON from {os.path.basename(path)} (after turn {battle.turn}"
               f"{', fresh dice seed ' + str(fresh_dice) if fresh_dice is not None else ', same dice'}) ===")
    return orchestrator.play_on(battle)


def _main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    path, turns, fresh = argv[0], None, None
    rest = argv[1:]
    while rest:
        flag = rest.pop(0)
        if flag == "--turns":
            turns = int(rest.pop(0))
        elif flag == "--fresh-dice":
            fresh = int(rest.pop(0))
        else:
            raise SystemExit(f"unknown option {flag!r}")
    result = play_on_from(path, turns, fresh)
    print(f"\nWinner: {result.winner} after {result.turns_taken} turns")
    for name, s in result.units.items():
        print(f"  {name}: {s.final_hp:g} / {s.max_hp:g} HP{' - destroyed' if s.destroyed else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
