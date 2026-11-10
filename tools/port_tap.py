"""
tools/port_tap.py - RUST PORT stages 4-5: function-level fixtures, tapped from real battles.

    python tools/port_tap.py GROUP [--fixtures a,b,c] [--limit N]
    python tools/port_tap.py --list

A GROUP (see GROUPS) names engine functions. The tool replays recorded battles in Python (dice tape + decisions, bots
off - tools/port_record.py --replay) with a wrapper on each of those functions that records, for up to N calls each
(spread over the battle): the arguments, the state of every unit it was given BEFORE, the dice it drew (the slice of
the tape), what it returned, the state AFTER, the log lines it printed and the stub warnings it raised. The Rust tests
(engine/core/tests/tap_*.rs) rebuild each call's inputs, call the Rust function with a tape of exactly those dice, and
must reproduce the output, state and log - so a function is checked on real inputs, alone, before any whole battle.

Output: engine/fixtures/taps/GROUP.json, a list of call records:
  {"fn", "fixture", "args", "units": {side: dump} before, "dice": [[kind, n, result]...], "ret", "after": {...},
   "log": [...], "stubs": [[name, msg]...], "board": {...changes...}}
Arguments and results are rt-encoded (tools/port_record.rt_encode): units {"_unit": name}, items {"_item": addr,
"of": unit}, tuples {"_t": [...]}, enums {"_enum": "Cls.NAME"}, ...
"""
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))
os.chdir(REPO_ROOT)
os.environ.setdefault("INTEGRATION_DATA_DIR", "./data")

# group -> list of "module.function" (module = the Python file name without INTEGRATION__ / path)
GROUPS = {
    "armor": ["armor_rules.effective_damage", "armor_rules._consume_armor", "armor_rules._consume_structure",
              "armor_rules.crit_roll_modifier", "armor_rules._reduce_attack_damage_for_armor"],
    "state": ["mech_state.is_destroyed", "mech_state.is_crippled", "mech_state.compute_walk_mp",
              "mech_state.compute_running_mp", "mech_state.compute_jump_mp", "mech_state.compute_heat_dissipation",
              "mech_state.mech_shields", "mech_state.hip_effects", "mech_state.ground_level_limited",
              "mech_state.torso_cockpit_sensor_penalty", "mech_state.physical_attacker_modifier",
              "mech_state.is_immobile", "damage_resolution.compute_tmm", "damage_resolution.get_weapons"],
    "piloting": ["piloting_rolls.preexisting_modifier", "piloting_rolls.special_case_modifier",
                 "piloting_rolls.snapshot_preexisting_damage", "piloting_rolls.snapshot_pre_attack_phase",
                 "piloting_rolls.resolve_fall", "piloting_rolls.roll_psrs", "piloting_rolls.can_stand",
                 "piloting_rolls.movement_psr_trigger", "piloting_rolls.movement_psr_count",
                 "piloting_rolls.check_movement_psr", "piloting_rolls.resolve_stand_up",
                 "piloting_rolls.resolve_movement_phase", "piloting_rolls.resolve_attack_phase_psr",
                 "piloting_rolls.resolve_consciousness_checks", "piloting_rolls.resolve_end_phase_wakeup",
                 "piloting_rolls.movement_psr_target_number", "piloting_rolls.hd_gyro_jump_adjust",
                 "hazards.magma_burn", "hazards.pool_damage", "hazards.enter_hex", "hazards.free_roll",
                 "hazards.bog_down_roll", "hazards.start_of_movement", "hazards.end_of_movement",
                 "hazards.magma_heat", "hazards.after_fall", "water.check_breach", "water.auto_breaches",
                 "water.drowning", "water.dissipation_bonus", "water.jump_mp"],
    "damage": ["damage_resolution.apply_damage", "damage_resolution.check_critical", "damage_resolution.resolve_critical",
               "damage_resolution.resolve_slot_hit", "damage_resolution.apply_explosion",
               "damage_resolution.mark_all_crits_destroyed", "damage_resolution.cluster_hits_count",
               "hit_location.resolve_hit_location"],
    "ammo": ["ammo.parse_bin", "ammo.attach_ammo", "ammo.bins_for", "ammo.unavailable_weapons", "ammo.take",
             "ammo.inferno_heat", "ammo._update_explosion", "ammo.is_one_shot", "ammo.damage_per_shot"],
    "heat": ["heat.resolve_heat_phase", "heat.movement_heat", "heat.engine_heat", "heat.other_heat",
             "heat.weapon_heat_budget", "heat.choose_heat_sink_deactivation", "heat.apply_heat_effects",
             "heat.choose_exploding_bin", "heat.live_ammo_bins", "heat.max_movement_heat", "heat.max_weapon_heat",
             "heat.planned_cooling", "heat.weapon_fire_surcharge", "heat._extra_cooling", "heat._check_shutdown",
             "heat._try_restart", "heat._check_ammo_explosion", "heat._life_support_hits", "heat.attach_heat_traits"],
    "electronics": ["electronics.artemis_kind", "electronics.live_ecm", "electronics.hostile_field",
                    "electronics.angel_field", "electronics.as_if_jammed", "electronics.artemis_blocked",
                    "electronics.narc_blocked", "electronics.homing_working", "electronics.control_for",
                    "electronics.munitions", "electronics.attach_pod", "electronics.activate_pods",
                    "electronics.attach"],
}


def fixtures_dir():
    return os.path.join(REPO_ROOT, "engine", "fixtures")


def encode_args(args, kwargs, units):
    import port_record as pr
    table = pr.item_table(units)
    out = [pr.rt_encode(a, units, table) for a in args]
    kw = {k: pr.rt_encode(v, units, table) for k, v in kwargs.items()}
    return out, kw


class Tap:
    def __init__(self, targets, limit, fixture):
        self.targets, self.limit, self.fixture = targets, limit, fixture
        self.records = []
        self.counts = {}
        self.seen = {}
        self.depth = 0

    def install(self, rec, rng):
        import importlib
        import INTEGRATION__decisions as decisions
        import INTEGRATION__config as config
        import INTEGRATION__stubs as stubs
        import port_record as pr
        self.rec, self.rng = rec, rng
        self.undo = []
        for target in self.targets:
            modname, fname = target.rsplit(".", 1)
            module = None
            for cand in (f"INTEGRATION__{modname}", modname):
                try:
                    module = importlib.import_module(cand)
                    break
                except ImportError:
                    continue
            orig = getattr(module, fname)
            wrapper = self._wrap(target, orig)
            # replace the function wherever a module imported it by name
            for mod in list(sys.modules.values()):
                if mod is None:
                    continue
                for name, value in list(getattr(mod, "__dict__", {}).items()):
                    if value is orig:
                        setattr(mod, name, wrapper)
                        self.undo.append((mod, name, orig))

    def uninstall(self):
        for mod, name, orig in self.undo:
            setattr(mod, name, orig)

    def _wrap(self, target, orig):
        tap = self

        def wrapper(*args, **kwargs):
            n = tap.seen[target] = tap.seen.get(target, 0) + 1
            take = tap.counts.get(target, 0) < tap.limit and (n % tap.stride(target) == 0 or n <= 3)
            if not take:
                return orig(*args, **kwargs)
            return tap.record(target, orig, args, kwargs)
        return wrapper

    def stride(self, target):
        return 5

    def record(self, target, orig, args, kwargs):
        import port_record as pr
        import INTEGRATION__forces as forces
        import INTEGRATION__decisions as decisions
        import INTEGRATION__config as config
        import INTEGRATION__stubs as stubs
        units = forces.battle()
        names = {id(u): u.side_name for u in units}
        mechs = []
        owner = None
        for a in list(args) + list(kwargs.values()):
            if id(a) in names and a not in mechs:
                mechs.append(a)
            elif hasattr(a, "slots_occupied") and not any(m for m in mechs if any(
                    s is a for sl in m.crits.values() for s in sl)):
                if owner is None:       # an item given without its mech: the unit that carries it joins the call
                    owner = {id(s): u for u in units for sl in u.crits.values() for s in sl}
                u = owner.get(id(a))
                if u is not None and u not in mechs:
                    mechs.append(u)
        try:
            enc_args, enc_kw = encode_args(args, kwargs, units)
        except TypeError:
            return orig(*args, **kwargs)            # an argument the encoding cannot carry (a function, a context)
        board = pr.dump_board_changes()
        before = {m.side_name: pr.dump_unit(m, names, pr.ID_MEMORY.setdefault(m.side_name, pr.id_table(m))) for m in mechs}
        dice0 = self.rng.pos
        lines, warns = [], []
        log0, warn0 = config.log, stubs._warn

        def log(msg=""):
            if not config._quiet_depth:
                lines.append(msg)
            return log0(msg)

        def warn(name, msg):
            warns.append([name, msg])
            return warn0(name, msg)
        import builtins
        print0 = builtins.print
        flag = {"in_log": False}

        def log_flagged(msg=""):
            flag["in_log"] = True
            try:
                return log(msg)
            finally:
                flag["in_log"] = False

        def print_tap(*a, **kw):
            if not flag["in_log"] and kw.get("file") is None:
                lines.append(kw.get("sep", " ").join(str(x) for x in a))   # a bare print: part of stdout, never quiet
            return print0(*a, **kw)
        config.log, stubs._warn = log_flagged, warn
        builtins.print = print_tap
        try:
            ret = orig(*args, **kwargs)
        finally:
            config.log, stubs._warn = log0, warn0
            builtins.print = print0
        after = {m.side_name: pr.dump_unit(m, names, pr.ID_MEMORY.setdefault(m.side_name, pr.id_table(m))) for m in mechs}
        try:
            if isinstance(ret, frozenset) and ret and all(isinstance(x, int) for x in ret):
                table = pr.item_table(units)            # a set of id()s of items (ammo.unavailable_weapons)
                enc_ret = {"_fs": sorted(({"_item": table[i][0], "of": table[i][1]} for i in ret),
                                         key=lambda x: json.dumps(x, sort_keys=True))}
            elif isinstance(ret, frozenset) and not ret:
                enc_ret = {"_fs": []}
            else:
                enc_ret = pr.rt_encode(ret, units, None)
        except TypeError:
            enc_ret = {"_unencodable": type(ret).__name__}
        self.counts[target] = self.counts.get(target, 0) + 1
        self.records.append({"fn": target, "fixture": self.fixture, "args": enc_args, "kwargs": enc_kw, "units": before,
                             "dice": self.rng.calls[dice0:self.rng.pos], "ret": enc_ret, "after": after, "log": lines,
                             "stubs": warns, "board": board, "piloting": config.PILOTING, "roster": [u.side_name for u in units]})
        return ret


def tap_fixture(fixture_dir, targets, limit):
    """Replay one fixture with the tap installed; returns its records."""
    import port_record as pr
    import INTEGRATION__decisions as decisions
    import INTEGRATION__orchestrator as orchestrator
    name = os.path.basename(fixture_dir)
    with open(os.path.join(fixture_dir, "overrides.json"), encoding="utf-8") as f:
        meta = json.load(f)
    with open(os.path.join(fixture_dir, "dice.json"), encoding="utf-8") as f:
        calls = json.load(f)
    with open(os.path.join(fixture_dir, "decisions.json"), encoding="utf-8") as f:
        records = json.load(f)
    rec = pr.Recorder()
    rec.install()
    decisions.MODE = "replay"
    decisions.RECORDS[:] = records
    rng = pr.TapeRNG(calls)
    decisions.HOOKS["skip_dice"] = rng.skip
    rec.tape.calls = pr._PosView(rng)
    tap = Tap(targets, limit, name)
    original = orchestrator.BattleRNG
    orchestrator.BattleRNG = lambda seed=None: rng
    tap.install(rec, rng)
    try:
        pr.run_battle(meta["overrides"], rec, meta["max_turns"])
    finally:
        tap.uninstall()
        orchestrator.BattleRNG = original
        rec.uninstall()
    return tap.records


def main(argv):
    if not argv or argv[0] == "--list":
        for g, fns in GROUPS.items():
            print(g, fns)
        return
    group = argv[0]
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 25
    root = fixtures_dir()
    targets = GROUPS[group]
    if "--one" in argv:                                   # one fixture in this process; records to --out
        recs = tap_fixture(os.path.join(root, argv[argv.index("--one") + 1]), targets, limit)
        with open(argv[argv.index("--out") + 1], "w", encoding="utf-8", newline="\n") as f:
            json.dump(recs, f)
        return
    if "--fixtures" in argv:
        names = argv[argv.index("--fixtures") + 1].split(",")
    else:
        names = sorted(n for n in os.listdir(root) if os.path.exists(os.path.join(root, n, "decisions.json"))
                       and not n.startswith("team_12"))
    import subprocess
    import tempfile
    from concurrent.futures import ThreadPoolExecutor
    tmp = tempfile.mkdtemp(prefix="port_tap_")

    def one(n):
        out = os.path.join(tmp, n + ".json")
        proc = subprocess.run([sys.executable, "tools/port_tap.py", group, "--one", n, "--out", out, "--limit", str(limit)],
                              cwd=REPO_ROOT, capture_output=True, text=True,
                              env=dict(os.environ, PYTHONHASHSEED="0", INTEGRATION_DATA_DIR="./data"))
        if proc.returncode:
            return n, None, proc.stderr[-300:]
        with open(out, encoding="utf-8") as f:
            return n, json.load(f), ""
    result = []
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 1) as pool:
        for n, recs, err in pool.map(one, names):
            if recs is None:
                print(f"  {n}: FAILED {err}")
                continue
            result += recs
            print(f"  {n}: {len(recs)} calls")
    os.makedirs(os.path.join(root, "taps"), exist_ok=True)
    path = os.path.join(root, "taps", group + ".json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f)
    from collections import Counter
    print(f"{len(result)} calls written to {path}: {dict(Counter(r['fn'] for r in result))}")


if __name__ == "__main__":
    main(sys.argv[1:])
