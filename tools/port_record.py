"""
tools/port_record.py - RUST PORT, STAGE 0 (INTEGRATION__RUST_PORT.md): record a battle as a fixture folder.

    python tools/port_record.py --reference Kontio_vs_Hammerhead_seed12345.txt OUT_DIR
    python tools/port_record.py --scenario NAME OUT_DIR                   # one of tools/port_scenarios.py
    python tools/port_record.py --overrides overrides.json OUT_DIR      # a JSON list of config statements
    python tools/port_record.py --replay FIXTURE_DIR OUT_DIR             # play it again from dice + decisions only

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
CACHE_ATTRS = {"_aes_cache",
               "path_psrs", "path_hazard",        # the move search's scratch tables (the pick's entries ride in the move decision)
               "_special", "_has_profile",        # Equipment memos set the first time fire_modes / weapon_profiles ask
               "_no_shields"}                     # a mech memo: set the first time shields are asked about

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
        if id(obj) in ids:
            d["_addr"] = ids[id(obj)]         # an Equipment's identity: the address of its first slot ("Right Arm#3")
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
# ==========================  DECISION CODECS  ================================
# =============================================================================
# One per kind of INTEGRATION__decisions.decide(): name(ctx) says what the choice is about, encode(value, ctx) makes
# the answer JSON, decode(raw, ctx) makes live objects of it again (for the Python self-replay). Units are
# written as their side_name, weapons as slot addresses ("Right Arm#3": the FIRST slot of the item).

def unit_named(name):
    import INTEGRATION__forces as forces
    for u in forces.battle():
        if u.side_name == name:
            return u
    raise KeyError(name)


def unit_name(u):
    return None if u is None else u.side_name


def weapon_by_address(mech, address):
    for w_id, a in id_table(mech).items():
        if a == address:
            return _object_by_id(mech, w_id)
    raise KeyError(f"{mech.side_name}: no item at {address}")


def _object_by_id(mech, w_id):
    for slots in mech.crits.values():
        for item in slots:
            if not isinstance(item, str) and id(item) == w_id:
                return item
    raise KeyError(w_id)


def address_of(mech, item):
    return id_table(mech)[id(item)]


class UnitCodec:
    """foe / target: a unit or None."""
    def name(self, ctx):
        return ctx[0].side_name

    def encode(self, value, ctx):
        return unit_name(value)

    def decode(self, raw, ctx):
        return None if raw is None else unit_named(raw)


def _find_class(name):
    for mod in list(sys.modules.values()):
        c = getattr(mod, name, None) if mod is not None else None
        if isinstance(c, type):
            return c
    raise KeyError(name)


def _live_units():
    import INTEGRATION__forces as forces
    return forces.battle()


def item_table(units):
    """{id(item): (address, side_name)} for every Equipment object on every unit's crit table."""
    out = {}
    for u in units:
        mem = ID_MEMORY.get(u.side_name, {})
        for i, a in id_table(u).items():
            out[i] = (mem.get(i, a), u.side_name)       # an item keeps the address it had when the battle started
    return out


def rt_encode(obj, units, table=None):
    """A JSON form of obj that rt_decode turns back into the same Python value. Tagged where JSON cannot say what
    a thing is: {"_t": [...]} tuple, {"_fs": [...]} frozenset (sorted), {"_nt": "Name", field: ...} namedtuple,
    {"_enum": "Cls.NAME"}, {"_d": [[k, v], ...]} dict with non-text keys, {"_unit": name}, {"_item": addr,
    "of": unit} an Equipment object by its first slot, {"_ids": [addr, ...]} a set of id()s of such items."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, enum.Enum):
        return {"_enum": f"{type(obj).__name__}.{obj.name}"}
    if table is None:
        table = item_table(units)
    for u in units:
        if obj is u:
            return {"_unit": u.side_name}
    if id(obj) in table:
        return {"_item": table[id(obj)][0], "of": table[id(obj)][1]}
    if isinstance(obj, tuple) and hasattr(obj, "_fields"):
        d = {"_nt": type(obj).__name__}
        d.update({f: rt_encode(getattr(obj, f), units, table) for f in obj._fields})
        return d
    if isinstance(obj, tuple):
        return {"_t": [rt_encode(x, units, table) for x in obj]}
    if isinstance(obj, list):
        return [rt_encode(x, units, table) for x in obj]
    if isinstance(obj, frozenset):
        items = [rt_encode(x, units, table) for x in obj]
        return {"_fs": sorted(items, key=lambda x: json.dumps(x, sort_keys=True))}
    if isinstance(obj, dict):
        if all(isinstance(k, str) and not k.startswith("_") for k in obj):
            return {k: rt_encode(v, units, table) for k, v in obj.items()}
        return {"_d": [[rt_encode(k, units, table), rt_encode(v, units, table)] for k, v in obj.items()]}
    raise TypeError(f"rt_encode: {type(obj).__name__} {obj!r}")


def rt_decode(raw, units):
    if isinstance(raw, list):
        return [rt_decode(x, units) for x in raw]
    if not isinstance(raw, dict):
        return raw
    if "_unit" in raw:
        return next(u for u in units if u.side_name == raw["_unit"])
    if "_item" in raw:
        return weapon_by_address(next(u for u in units if u.side_name == raw["of"]), raw["_item"])
    if "_enum" in raw:
        cls, member = raw["_enum"].split(".")
        return getattr(_find_class(cls), member)
    if "_nt" in raw:
        cls = _find_class(raw["_nt"])
        return cls(**{f: rt_decode(raw[f], units) for f in cls._fields})
    if "_t" in raw:
        return tuple(rt_decode(x, units) for x in raw["_t"])
    if "_fs" in raw:
        return frozenset(rt_decode(x, units) for x in raw["_fs"])
    if "_d" in raw:
        return {_hashable(rt_decode(k, units)): rt_decode(v, units) for k, v in raw["_d"]}
    return {k: rt_decode(v, units) for k, v in raw.items()}


def _hashable(x):
    return tuple(_hashable(i) for i in x) if isinstance(x, list) else x


class RoundTripCodec:
    """move / physical / declaration: the answer as rt_encode writes it. The declaration's `held` set of weapon
    id()s is turned into items first (rt_encode names Equipment objects by address; a bare id() is not one)."""
    def __init__(self, name, prepare=None, restore=None):
        self._name, self._prepare, self._restore = name, prepare, restore

    def name(self, ctx):
        return self._name(ctx)

    def encode(self, value, ctx):
        units = _live_units()
        if self._prepare:
            value = self._prepare(value, ctx)
        return rt_encode(value, units)

    def decode(self, raw, ctx):
        value = rt_decode(raw, _live_units())
        return self._restore(value, ctx) if self._restore else value


# {side_name: {id(item): address}} for EVERY Equipment object a unit started the battle with, destroyed or not
# (weapon_locations() lists destroyed weapons' ids too, and `held` can name them). Filled by the Recorder at the
# start of the battle, in a recording and in a replay alike.
ID_MEMORY = {}


def _declaration_prepare(value, ctx):
    """(total, (weapons, exp, heat), key, action, phys_picks, phys_value, held ids) with the id() set turned into
    the slot addresses it names, sorted."""
    total, picked, key, action, phys_picks, phys_value, held = value
    memory = ID_MEMORY[ctx[0].side_name]
    return (total, (list(picked[0]), picked[1], picked[2]), key, action, phys_picks, phys_value,
            sorted(memory[i] for i in held))


def _declaration_restore(value, ctx):
    total, (weapons, exp, heat), key, action, phys_picks, phys_value, held = value
    by_address = {a: i for i, a in ID_MEMORY[ctx[0].side_name].items()}
    return (total, (weapons, exp, heat), key, action, phys_picks, phys_value,
            frozenset(by_address[a] for a in held))


def _pick_key(pick):
    import hex_geometry
    x, y = hex_geometry.parse_hex_label(pick["hex"])
    return (x, y, hex_geometry.compass_to_facing(pick["facing"]), pick["fc"], pick["mode"], pick["mp_spent"])


def _move_prepare(value, ctx):
    """(pick, note) -> (pick, note, psr count at the pick, hazard at the pick): the search leaves its scratch tables
    on the mover and _walk_path reads the pick's entry in them (orchestrator._walk_path)."""
    pick, note = value
    mover = ctx[0]
    n = h = None
    if pick is not None and pick["mode"] in ("Walk", "Run"):
        n = getattr(mover, "path_psrs", {}).get(_pick_key(pick))
        h = getattr(mover, "path_hazard", {}).get(_pick_key(pick))
    return (pick, note, n, h)


def _move_restore(value, ctx):
    pick, note, n, h = value
    mover = ctx[0]
    mover.path_psrs, mover.path_hazard = {}, {}
    if pick is not None and pick["mode"] in ("Walk", "Run"):
        if n is not None:
            mover.path_psrs[_pick_key(pick)] = n
        if h is not None:
            mover.path_hazard[_pick_key(pick)] = h
    return (pick, note)


def _fire_pick_name(ctx):
    return ">".join(u.side_name for u in ctx[0])


CODECS = {
    "foe": UnitCodec(),
    "target": UnitCodec(),
    "fire_pick": UnitCodec(),
    "move": RoundTripCodec(lambda ctx: ctx[0].side_name, _move_prepare, _move_restore),
    "physical": RoundTripCodec(lambda ctx: f"{ctx[0].side_name}>{ctx[1].side_name}"),
    "declaration": RoundTripCodec(lambda ctx: f"{ctx[0].side_name}>{ctx[1].side_name}",
                                  _declaration_prepare, _declaration_restore),
}
CODECS["fire_pick"].name = lambda ctx: ">".join(u.side_name for u in ctx[0])


# =============================================================================
# ==========================  THE RECORDER  ===================================
# =============================================================================

class Recorder:
    def __init__(self):
        self.tape = Tape()
        self.trace = []
        self.battle = None
        self.start = {}
        self.phase = "start"
        ID_MEMORY.clear()
        self.id_memory = ID_MEMORY       # {side_name: {id(equipment): 'Location#slot'}}
        self._keep = []           # the Equipment objects themselves, so no id() is reused while recording

    def install(self):
        import INTEGRATION__orchestrator as orchestrator
        import INTEGRATION__replay as replay
        self.tape.install()
        rec = self
        import INTEGRATION__decisions as decisions
        import INTEGRATION__config as config
        decisions.reset()
        decisions.MODE = "record"
        decisions.CODECS.update(CODECS)
        decisions.HOOKS.update({"dice_count": lambda: len(rec.tape.calls), "phase": lambda: rec.phase})
        log = config.log

        def _log(msg=""):
            if not config._quiet_depth:
                decisions.capture_log(msg)
            return log(msg)
        config.log = _log
        import INTEGRATION__stubs as stubs
        warn = stubs._warn

        def _warn(name, msg):
            decisions.capture_stub(name, msg)
            return warn(name, msg)
        stubs._warn = _warn

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
        self._undo = [(orchestrator, "_start_battle", start_battle), (replay, "mark", mark), (config, "log", log), (stubs, "_warn", warn)]

    def uninstall(self):
        import INTEGRATION__decisions as decisions
        self.decisions = list(decisions.RECORDS)
        decisions.reset()
        self.tape.uninstall()
        for mod, name, fn in self._undo:
            setattr(mod, name, fn)

    def snapshot(self, turn, phase):
        self.phase = f"turn {turn} after {phase}"
        if self.battle is None:
            return
        self.trace.append({"turn": turn, "phase": phase, "dice_used": len(self.tape.calls),
                           "units": dump_units(self.battle.units, self.id_memory), "board": dump_board_changes()})


# =============================================================================
# ==========================  THE PYTHON SELF-REPLAY  =========================
# =============================================================================

class TapeMismatch(Exception):
    pass


class TapeRNG:
    """A BattleRNG that plays a dice tape back. A draw of a different kind, or a different n, than the tape holds
    raises with the call number: the first-difference detector for dice (RUST_PORT trap 1)."""

    def __init__(self, calls):
        self.calls = calls
        self.pos = 0
        self.seed = None

    def roll_2d6(self):
        c = self._next("r", 0)
        return c[2]

    def pick_number(self, n):
        return self._next("p", n)[2]

    def _next(self, kind, n):
        if self.pos >= len(self.calls):
            raise TapeMismatch(f"dice call {self.pos + 1}: asked for ({kind}, {n}) but the tape has ended")
        c = self.calls[self.pos]
        if c[0] != kind or c[1] != n:
            raise TapeMismatch(f"dice call {self.pos + 1}: asked for ({kind}, {n}), tape has ({c[0]}, {c[1]})")
        self.pos += 1
        return c

    def skip(self, count):
        """Dice a bot drew while thinking (its decision was recorded, so it does not think now)."""
        self.pos += count

    def __repr__(self):
        return f"<TapeRNG at {self.pos}/{len(self.calls)}>"


def replay_fixture(fixture_dir, out_dir=None):
    """Plays the fixture's battle again from dice.json + decisions.json alone (decisions.MODE "replay": no bot
    computes anything). Returns (log text, trace lines). Same settings as the recording (overrides.json)."""
    with open(os.path.join(fixture_dir, "overrides.json"), encoding="utf-8") as f:
        meta = json.load(f)
    with open(os.path.join(fixture_dir, "dice.json"), encoding="utf-8") as f:
        calls = json.load(f)
    with open(os.path.join(fixture_dir, "decisions.json"), encoding="utf-8") as f:
        records = json.load(f)
    import INTEGRATION__decisions as decisions
    import INTEGRATION__orchestrator as orchestrator
    rec = Recorder()
    rec.install()                          # for the trace; its tape is replaced below
    decisions.MODE = "replay"
    decisions.RECORDS[:] = records
    rng = TapeRNG(calls)
    rec.tape.calls = _PosView(rng)         # "dice used" in the trace is the tape position
    decisions.HOOKS["skip_dice"] = rng.skip
    original = orchestrator.BattleRNG
    orchestrator.BattleRNG = lambda seed=None: rng
    try:
        log, _ = run_battle(meta["overrides"], rec, meta["max_turns"])
        if rng.pos != len(calls) or decisions._cursor != len(records):
            raise TapeMismatch(f"replay ended with {rng.pos}/{len(calls)} dice and {decisions._cursor}/"
                               f"{len(records)} decisions used")
    finally:
        orchestrator.BattleRNG = original
        rec.uninstall()
    return log, rec.trace


class _PosView:
    """len() of this is the tape position (the recorder reads len(tape.calls))."""
    def __init__(self, rng):
        self.rng = rng

    def __len__(self):
        return self.rng.pos


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
    put("overrides.json", {"overrides": statements, "max_turns": max_turns})
    put("units.json", rec.start["units"])
    put("board.json", rec.start["board"])
    put("dice.json", rec.tape.calls, indent=None)
    with open(os.path.join(out_dir, "decisions.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write("[\n" + ",\n".join(json.dumps(d) for d in rec.decisions) + "\n]\n")
    with open(os.path.join(out_dir, "trace.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        for line in rec.trace:
            f.write(json.dumps(line, sort_keys=True) + "\n")
    with open(os.path.join(out_dir, "log.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(log)
    return result


def main(argv):
    if argv and argv[0] == "--replay":
        log, trace = replay_fixture(argv[1])
        out = argv[2]
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "trace.jsonl"), "w", encoding="utf-8", newline="\n") as f:
            for line in trace:
                f.write(json.dumps(line, sort_keys=True) + "\n")
        with open(os.path.join(out, "log.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write(log)
        return
    if len(argv) < 3 or argv[0] not in ("--reference", "--scenario", "--overrides"):
        raise SystemExit(__doc__)
    if argv[0] == "--reference":
        import check_reference_logs
        statements = check_reference_logs.SCENARIOS[argv[1]]
        max_turns = check_reference_logs.TEST_BATTLE_MAX_TURNS
    elif argv[0] == "--scenario":
        sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
        import port_scenarios
        statements, max_turns = port_scenarios.SCENARIOS[argv[1]]
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
