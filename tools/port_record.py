"""
tools/port_record.py - RUST PORT, STAGE 0 (INTEGRATION__RUST_PORT.md): record a battle as a fixture folder.

    python tools/port_record.py --reference Kontio_vs_Hammerhead_seed12345.txt OUT_DIR
    python tools/port_record.py --overrides overrides.json OUT_DIR      # a JSON list of config statements

The Python is the answer key for the Rust translation. This tool plays ONE battle (battle number 1 of the
batch, the way run_batch plays it) with recorder hooks that only READ, and writes into OUT_DIR:

    config.json     every UPPERCASE setting in force when the battle started
    units.json      each unit as it stood after deployment-free loading (before turn 1): the full mech state
    board.json      the parsed board: every hex's level and terrain (before turn 1)
    dice.json       the dice tape: every roll_2d6() / pick_number(n) result, in call order (RUST_PORT trap 1)
    decisions.json  every choice a bot or stub made, in order (see the DECISIONS section)
    trace.jsonl     after EVERY phase of every turn, one line: turn, phase, dice used, every unit's full state
    log.txt         the battle log exactly as run_checks prints it (stdout, then stderr)

Nothing here may change a battle: tests/test_port_record.py plays the same battle with and without the
recorder and compares the logs.

State is dumped by reflection (`dump`): every attribute of every mech, recursively, so a field some module hangs
on a mech later (RUST_PORT trap 7) is in the trace without anyone having to remember it. Memory addresses
(`id()` keys and values) are replaced by names (a slot address like "Right Arm#3") so two runs give the same text.
"""

import enum
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))

# =============================================================================
# ==========================  DUMPING STATE  ==================================
# =============================================================================

# Attributes that are caches (RUST_PORT trap 9 / STATE.md kind 3): a fresh computation gives the same value.
CACHE_ATTRS = {"_aes_cache"}

ID_FLOOR = 1 << 32            # an int this large is a memory address (CPython ids are ~1e14), never a game number


def id_table(mech):
    """{id(object): 'Location#slot'} for every Equipment object on the mech's crit table (its FIRST slot), so the
    id()s the engine stores (weapons_fired_this_turn, destroyed_slot_info) can be printed as names."""
    table = {}
    for loc, slots in mech.crits.items():
        for i, item in enumerate(slots):
            if not isinstance(item, str) and id(item) not in table:
                table[id(item)] = f"{loc}#{i}"
    return table


def dump(obj, ids, units_by_id, path="", depth=0):
    """A JSON-ready copy of obj. ids: the mech's id_table; units_by_id: {id(mech): side_name}."""
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, enum.Enum):
        return f"{type(obj).__name__}.{obj.name}"
    if isinstance(obj, int):
        if abs(obj) >= ID_FLOOR:
            return ids.get(obj, f"id:{obj}") if obj in ids else f"ADDRESS?{obj}"
        return obj
    if isinstance(obj, float):
        return obj if obj == obj and abs(obj) != float("inf") else repr(obj)
    if id(obj) in units_by_id:
        return {"_unit": units_by_id[id(obj)]}
    if depth > 12:
        return {"_deep": type(obj).__name__}
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, int) and abs(k) >= ID_FLOOR:
                key = ids.get(k, f"ADDRESS?{k}")
            elif isinstance(k, str):
                key = k
            elif isinstance(k, enum.Enum):
                key = f"{type(k).__name__}.{k.name}"
            else:
                key = repr(k)
            out[key] = dump(v, ids, units_by_id, f"{path}/{key}", depth + 1)
        return out
    if isinstance(obj, (set, frozenset)):
        items = [dump(x, ids, units_by_id, path, depth + 1) for x in obj]
        return sorted(items, key=lambda x: json.dumps(x, sort_keys=True, default=str))
    if isinstance(obj, tuple) and hasattr(obj, "_fields"):             # a namedtuple
        d = {"_type": type(obj).__name__}
        d.update({f: dump(getattr(obj, f), ids, units_by_id, f"{path}/{f}", depth + 1) for f in obj._fields})
        return d
    if isinstance(obj, (list, tuple)):
        return [dump(x, ids, units_by_id, path, depth + 1) for x in obj]
    if hasattr(obj, "__dict__"):
        d = {"_type": type(obj).__name__}
        for k, v in vars(obj).items():
            if k in CACHE_ATTRS:
                continue
            d[k] = dump(v, ids, units_by_id, f"{path}/{k}", depth + 1)
        return d
    return {"_repr": f"{type(obj).__name__}:{obj!r}"}


def dump_unit(mech, units_by_id, ids=None):
    ids = ids if ids is not None else id_table(mech)
    out = {}
    for k, v in vars(mech).items():
        if k in CACHE_ATTRS:
            continue
        out[k] = dump(v, ids, units_by_id, k)
    return out


def dump_units(units, id_memory=None):
    """id_memory: {side_name: {id: name}} kept across calls by the Recorder - a destroyed slot no longer holds its
    Equipment object, but destroyed_slot_info still stores its id(), so the names are remembered from before."""
    by_id = {id(u): u.side_name for u in units}
    out = {}
    for u in units:
        ids = None
        if id_memory is not None:
            ids = id_memory.setdefault(u.side_name, {})
            ids.update({k: v for k, v in id_table(u).items() if k not in ids})
        out[u.side_name] = dump_unit(u, by_id, ids)
    return out


def dump_board_changes():
    """The board's changed hexes (STATE.md kind 1): smoke, severed limbs on the ground, broken magma crust."""
    import INTEGRATION__smoke as smoke
    import INTEGRATION__clubs as clubs
    import INTEGRATION__hazards as hazards
    broken = []
    for info in hazards._BROKEN:
        broken.append(dump(info, {}, {}))
    return {"smoke": sorted(smoke._SMOKY), "limbs_on_ground": dict(sorted(clubs._LIMBS_ON_GROUND.items())),
            "broken_crust": broken}


def dump_board(terrain_map):
    return dump(terrain_map, {}, {})


def dump_config():
    import INTEGRATION__config as config
    out = {}
    for name, value in vars(config).items():
        if not name.isupper():
            continue
        try:
            json.dumps(value)
            out[name] = value
        except TypeError:
            out[name] = dump(value, {}, {})
    return out


# =============================================================================
# ==========================  THE DICE TAPE  ==================================
# =============================================================================

class Tape:
    """The dice tape: [kind, n, result] per call, kind 'r' = roll_2d6 (n 0), 'p' = pick_number(n)."""

    def __init__(self):
        self.calls = []

    def install(self):
        """Wrap BattleRNG's two draw methods on the CLASS (every instance, so a battle reloaded mid-run is still
        taped). Reads the result only."""
        from INTEGRATION__rng import BattleRNG
        self._roll, self._pick = BattleRNG.roll_2d6, BattleRNG.pick_number
        tape = self

        def roll_2d6(rng):
            v = tape._roll(rng)
            tape.calls.append(["r", 0, v])
            return v

        def pick_number(rng, n):
            v = tape._pick(rng, n)
            tape.calls.append(["p", n, v])
            return v
        BattleRNG.roll_2d6, BattleRNG.pick_number = roll_2d6, pick_number

    def uninstall(self):
        from INTEGRATION__rng import BattleRNG
        BattleRNG.roll_2d6, BattleRNG.pick_number = self._roll, self._pick


# =============================================================================
# ==========================  THE RECORDER  ===================================
# =============================================================================

class Recorder:
    def __init__(self):
        self.tape = Tape()
        self.trace = []
        self.battle = None
        self.start = {}
        self.id_memory = {}       # {side_name: {id(equipment): 'Location#slot'}}
        self._keep = []           # the Equipment objects themselves, so no id() is reused while recording

    def install(self):
        import INTEGRATION__orchestrator as orchestrator
        import INTEGRATION__replay as replay
        self.tape.install()
        rec = self

        # the battle object, once deployment has happened: units and board for the first dump
        start_battle = orchestrator._start_battle

        def _start_battle(battle):
            rec.battle = battle
            rec.start = {"units": dump_units(battle.units, rec.id_memory), "board": dump_board(battle.terrain_map)}
            rec._keep = [item for u in battle.units for slots in u.crits.values() for item in slots
                         if not isinstance(item, str)]
            start_battle(battle)
        orchestrator._start_battle = _start_battle

        # a line after every phase: replay.mark is called by the orchestrator at each phase end
        mark = replay.mark

        def _mark(turn, phase):
            rec.snapshot(turn, phase)
            return mark(turn, phase)
        replay.mark = _mark
        self._undo = [(orchestrator, "_start_battle", start_battle), (replay, "mark", mark)]

    def uninstall(self):
        self.tape.uninstall()
        for mod, name, fn in self._undo:
            setattr(mod, name, fn)

    def snapshot(self, turn, phase):
        if self.battle is None:
            return
        self.trace.append({"turn": turn, "phase": phase, "dice_used": len(self.tape.calls),
                           "units": dump_units(self.battle.units, self.id_memory), "board": dump_board_changes()})


# =============================================================================
# ==========================  RUNNING ONE BATTLE  =============================
# =============================================================================

def apply_overrides(statements):
    import INTEGRATION__config as config  # noqa: F401 - the statements name it
    scope = {"config": config}
    for s in statements:
        exec(s, scope)


def run_battle(statements, recorder=None, max_turns=50):
    """Plays battle 1 of a one-battle batch under `statements` (config overrides) the way run_batch does, and
    returns (log text, BattleResult). With a recorder installed, its hooks fill in."""
    import io
    from contextlib import redirect_stdout, redirect_stderr
    import INTEGRATION__config as config
    config.TIMING = False
    config.STATS = False
    config.MAX_TURNS = max_turns
    apply_overrides(statements)
    import INTEGRATION__orchestrator as orchestrator
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        results = orchestrator.run_batch()
    return f"# stdout\n{out.getvalue()}\n# stderr (stub warnings)\n{err.getvalue()}", results[0]


def write_fixture(out_dir, statements, max_turns=50):
    os.makedirs(out_dir, exist_ok=True)
    rec = Recorder()
    rec.install()
    try:
        log, result = run_battle(statements, rec, max_turns)
    finally:
        rec.uninstall()
    cfg = dump_config()

    def put(name, data, indent=1):
        with open(os.path.join(out_dir, name), "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=indent)
    put("config.json", cfg)
    put("units.json", rec.start["units"])
    put("board.json", rec.start["board"])
    put("dice.json", rec.tape.calls, indent=None)
    with open(os.path.join(out_dir, "trace.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        for line in rec.trace:
            f.write(json.dumps(line, sort_keys=True) + "\n")
    with open(os.path.join(out_dir, "log.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(log)
    return result


def main(argv):
    if len(argv) < 3 or argv[0] not in ("--reference", "--overrides"):
        raise SystemExit(__doc__)
    if argv[0] == "--reference":
        import check_reference_logs
        statements = check_reference_logs.SCENARIOS[argv[1]]
        max_turns = check_reference_logs.TEST_BATTLE_MAX_TURNS
    else:
        with open(argv[1], encoding="utf-8") as f:
            statements = json.load(f)
        max_turns = 50
    os.environ.setdefault("INTEGRATION_DATA_DIR", "./data")
    write_fixture(argv[2], statements, max_turns)


if __name__ == "__main__":
    os.chdir(REPO_ROOT)
    os.environ.setdefault("INTEGRATION_DATA_DIR", "./data")
    main(sys.argv[1:])
