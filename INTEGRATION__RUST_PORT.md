# The Rust translation - plan for the model that does it

Written 2026-11-10 (session 21) by the top-level review, for Daniel's decision the same day: "have Sonnet
translate the monte carlo into rust. Just bite the bullet and remove translation as a source of slowdown."
This file is the plan and the rules of the road. It is written so a smaller model can follow it one stage at a
time, a fresh session per stage. Read `CLAUDE.md` first, then all of this, then only the stage you are on.

## The one idea that makes this safe

**The Python stays, untouched, as the answer key.** Every stage ends with the Rust producing EXACTLY what the
Python produces for the same input - not "close", not "the same winner": the same text, the same numbers. A
translation by a smaller model will contain mistakes; the plan does not depend on avoiding them, it depends on
FINDING them, and on finding the first one, not the thousandth symptom. So the comparison tools (stage 0) come
before any translation, and no stage is "done" on the translator's say-so - only on the comparison.

Three rules follow, and they are not negotiable:
1. **Translate, don't improve.** Same steps in the same order, the same names, the page cites and comments
   carried over. A cleverer algorithm, a tidier structure, a "fix" for something that looks wrong in the Python:
   NOT during the port. If the Python looks wrong, write it in "Found on the way" at the bottom of this file and
   copy its behaviour anyway. (Speed comes after the port passes - stage 9.)
2. **No change to the Python's behaviour while the port runs.** Bot work, rule fixes and new equipment wait, or
   the answer key moves under the translator. The only Python changes allowed are the stage 0 recorders, which
   must leave all 55 checks and every reference log identical.
3. **When the comparison fails, find the first difference and fix that.** Never adjust the Rust until the final
   numbers happen to match, never loosen a comparison, never regenerate the Python's logs to match the Rust.

## What gets translated and what stays Python

About 34,500 lines of Python (tests and tools not counted):

| Part | Lines | Goes to Rust? |
|---|---|---|
| Rules engine: `pathfinder/`, `mechsim/`, and the `INTEGRATION__` rules modules (orchestrator, attack_resolution, ranged_combat, physical, heat, water, hazards, arcs, ammo, ams, electronics, fire_modes, weapon_profiles / _rules, advanced_*, equipment_systems, capacitor, charge, dfa, clubs, domino, deployment, forces, smoke, tag, expected_damage, structure_weight, stubs, rng, config) | ~20,000 | Yes - stages 1-6 |
| Bots: Gladiator (`movement_selection`, `weapon_selection`, `future_damage`, `movement_attacks`, `legate`, `triage`, `tiers`, `kill_curve`, `vision`, `peril`), Princess (`princess*`, `battle_value`), `bots` | ~7,000 | Yes - stages 7-8. This is where the run time is |
| Output: results, stats, replay, saved state, timing, the two pickers, main | ~2,000 | No. Rust writes JSON; these read it (stage 6 / 9) |
| Combat Lab art: tokens, shell, token_mesh, `tools/token_*` | ~5,000 | No. Never touched by the port |
| Tests | ~14,000 | Not translated. The comparison tools replace them for the Rust; the Python tests keep guarding the answer key |

Before stage 1, shrink the job: get Daniel's word on `INTEGRATION__TASK_SPECS.md` T8 (archive the experiments
that lost: Peril in the move score, stack, herding, cohesion, team value, exchange). Anything archived is not
translated. `config.FIGHT_TO_THE_DEATH` and the other OPTIONAL RULES switches ARE translated, both settings.

## Layout

A new Cargo workspace `engine/` beside `fastcore/` (which stays as it is until stage 9):

    engine/
      Cargo.toml                 workspace
      core/                      the library: one Rust module per Python module, SAME NAME
        src/hex_geometry.rs      <- pathfinder/hex_geometry.py
        src/damage_resolution.rs <- mechsim/damage_resolution.py
        src/attack_resolution.rs <- INTEGRATION__attack_resolution.py   (drop the INTEGRATION__ prefix)
        ...
      cli/                       `btsim`: runs battles / batches from a JSON settings file, prints the log
      py/                        PyO3 wrapper (maturin), so Python tools and tests can call the Rust
      tests/                     the comparison tests (read files under engine/fixtures/)
      fixtures/                  recorded by Python in stage 0 (git-ignored if large; a small set committed)

No `unsafe`. No clever generics. `cargo clippy` clean is nice, not required. Each Rust file starts with a
comment naming the Python file and commit it was translated from.

## The traps (read before writing any Rust)

Each of these silently breaks exact matching. Stage 0's tools find them; knowing them saves days.

1. **Dice.** `INTEGRATION__rng.BattleRNG` is NumPy's generator: blocks of 10,000 2d6 sums, plus single
   `pick_number(n)` draws mixed in between. Do NOT try to re-create NumPy's generator in Rust. Stage 0 records a
   **dice tape** for each fixture battle: the result of every `roll_2d6()` and `pick_number(n)` call, in call
   order, with `n`. The Rust `Dice` trait has two implementations: `TapeDice` (replays the tape; panics with the
   call number if asked for a different kind of draw or a different `n` than the tape holds - that panic IS the
   first-difference detector) and, from stage 9, `PcgDice` (its own generator). Same seed giving the same battle
   in Python and Rust is NOT a goal after the port; same rules and same decisions on the same dice is.
2. **Dictionary and set order.** Python dicts keep insertion order and much of the code relies on it (which unit
   is first, which location is hit first, which tie wins). Use `indexmap::IndexMap` / `IndexSet` wherever the
   Python uses a dict or set that is ever looped over; `Vec` where order is positional. Never `HashMap` for
   anything iterated. Python `set` iteration order is arbitrary but stable in a run - where the Python loops over
   a set and the result depends on the order, note it under "Found on the way" and match what the Python does on
   the fixtures (usually via a sort that should have been there).
3. **Ties.** `max()` and `min()` keep the FIRST best item; `sorted()` is stable. Rust's `max_by` keeps the LAST
   of equals - write the loop out (`if score > best`) exactly as the Python's comparison reads (`>` v `>=`).
   `sort_by` is stable; `sort_unstable*` is forbidden.
4. **Floats.** Rust `f64` and Python floats are the same numbers IF the operations are the same in the same
   order. So: keep the order of additions and multiplications as written (no "simplifying" `a*b + a*c`); `sum()`
   adds left to right from 0.0; no `mul_add`; `x ** 0.5` -> `sqrt()`, other powers -> `powf` (check on
   fixtures); `round()` in Python rounds half to EVEN (`fastcore` already has this for hex distance) - Rust's
   `round()` rounds half away from zero, so write a `py_round`. Integer division `//` and `%` floor toward
   negative infinity in Python: use `div_euclid` / `rem_euclid` or a `py_floordiv`, and check every use with a
   negative operand. Python ints do not overflow: use `i64`.
5. **Printing.** The battle log is the answer key, so number formatting must match: `f"{x:.2f}"` ->
   `format!("{:.2}", x)` agrees for ordinary values; `str(float)` / `repr` (shortest round-trip, `1.0`, `1e-05`)
   needs a `py_float_str` helper (the `ryu` crate plus Python's rules for when to use an exponent). `True` /
   `False` / `None` print capitalised. Write `engine/core/src/pyfmt.rs` once, test it against a file of values
   Python printed, use it everywhere.
6. **State that lives outside the units.** The Python keeps battle state in module-level tables (list in
   `INTEGRATION__STATE.md`). In Rust there are NO globals: one `Battle` struct owns the units, the board, the
   dice and those tables; functions take `&mut Battle` or the parts they need. Units are referred to by a
   `UnitId(usize)` (index in `battle.units`), weapons by `(UnitId, slot index)` - never by reference or pointer.
   This also removes the Python's `id()` traps instead of translating them.
7. **Dynamic attributes.** The Python hangs fields on a mech as it goes (`mech.hp_log`, `getattr(mech, "x",
   default)`). Before translating `mech_state.py`, grep every `getattr(` / `setattr(` / `hasattr(` and every
   `mech.<name> =` outside it, and put them all in the Rust `Mech` struct as `Option<...>` or with the default.
   `INTEGRATION__saved_state.py`'s docstring and its pickle of a Battle are the full list of what state exists.
8. **Settings.** `INTEGRATION__config.py` is ~150 module variables that code reads live, and tests change them
   mid-run. In Rust: one `Config` struct, loaded from JSON (stage 0 writes `config.json` from the Python's
   values, UPPERCASE names kept as snake_case fields), owned by the `Battle`. No statics.
9. **Caches.** Many Python caches exist only for speed (weapon tables, LOS lines, path tables, kill curves) and
   are designed to return the value a fresh computation would. Translate the computation FIRST with no cache;
   add a cache only in stage 9, and only if the comparison still passes. Exception: a "cache" whose stale value
   the Python actually uses is state, not a cache - if results differ without it, that is a finding to write
   down, then copy.
10. **Stubs and warnings.** `INTEGRATION__stubs.py` prints loud warnings and counts them; those lines are in the
    log. Translate them as they are.

## Stage 0 - the comparison tools (Python only; Opus if available, else Sonnet with care)

The whole port rests on this stage. It changes no behaviour: all 55 checks and the benchmark must be identical
afterwards.

Build `tools/port_record.py`, which runs a battle from a settings file and writes a fixture folder:
- `config.json` - every UPPERCASE setting in force; `units.json` - each unit as parsed (the full mech state after
  loading, as JSON: locations, armor, structure, crit slots, weapons, ammo bins, MPs, skills); `board.json` - the
  parsed board (every hex's level and terrain);
- `dice.json` - the dice tape (trap 1);
- `decisions.json` - **every choice a bot or stub made, in order**: the move picked (unit, hex, facing, mode,
  path, MP), the foe / target chosen, the weapons fired with mode / ammo / aimed location, twist or arm flip, the
  physical attack, every stub's answer (rate of fire, munition, MASC, unjam, capacitor, shield, TAG, heat
  explosion bin...), the order units moved and declared in. Each record carries a running number and the phase;
- `trace.jsonl` - after EVERY phase of every turn, one line: turn, phase, and a full dump of every unit's state
  (position, facing, heat, every location's armor / structure, crit slots hit, ammo left, pilot hits, prone,
  shutdown, pending PSRs...) plus the board's changed hexes (smoke, broken crust), plus how many dice have been
  used. Keys sorted, floats printed with `repr`;
- `log.txt` - the battle log as printed today.
To get the decisions and state out, add recorder hooks the way `INTEGRATION__stats` and `tests/probe_hooks.py`
already do (hooks that only read). Add `tests/test_port_record.py`: recording changes nothing (same log with and
without), and a recorded battle REPLAYED IN PYTHON from `decisions.json` + `dice.json` with both bots switched
off gives the same `trace.jsonl` - this proves the decision list is complete before any Rust exists. If it does
not replay, a decision is missing from the list: find it.

Fixtures to record: the 15 reference battles; 6 team battles (4 v 4 and 12 v 12; Princess v Gladiator, Gladiator
v Gladiator, Princess v Princess; one 3-way); and a **coverage set**: short battles (10 turns) picked so that
between them every weapon family, every equipment module, water, magma, buildings, a fall, an ammo explosion, a
shutdown, a charge, a DFA, a push, a club, AMS, ECM / Narc / Artemis, TAG / Arrow IV, a superheavy, a quad, a
tripod all happen at least once. Check coverage by running the set under `coverage.py` on the engine modules
and listing the functions never reached; add battles (or tiny scripted set-ups from the existing tests) until
the list is short and explained. A function the fixtures never reach is a function whose translation is
unchecked - list those in this file.

Also build `tools/port_diff.py <python trace> <rust trace>`: prints the FIRST line that differs - turn, phase,
unit, field, both values - and the last decision and dice call before it. This is the tool the translator lives in.

**Done when:** fixtures recorded, the Python self-replay test passes on all of them, the coverage list is in this
file, 55 checks identical.

## The fixture format (what stage 0 built - the Rust tests read this)

`python tools/port_fixtures.py` writes one folder per scenario of `tools/port_scenarios.py` under `engine/fixtures/`
(git-ignored; recording is byte-for-byte repeatable, so any session rebuilds it; run with `PYTHONHASHSEED=0`, which the
tool sets). Units that are not in `data/` are unpacked from `data/meks.zip` into `engine/fixtures/_units/`.

| File | Holds |
|---|---|
| `overrides.json` | the config statements and turn cap the battle ran under (replay reads this) |
| `config.json` | every UPPERCASE setting in force (the Rust `Config` is loaded from this) |
| `units.json` | each unit as loaded, before turn 1: EVERY attribute of the Python mech, by reflection, in insertion order. Equipment objects are `{"_type": "Equipment", ...}`; ids are written as slot addresses |
| `board.json` | the parsed board (after `prepare_board`) |
| `dice.json` | the dice tape: `["r", 0, sum]` = `roll_2d6`, `["p", n, k]` = `pick_number(n)`, in call order |
| `decisions.json` | every bot decision, in order (below) |
| `trace.jsonl` | one line per phase mark (Deployment, each unit's move, Ranged attacks, Physical attacks, Heat and end phase): turn, phase, `dice_used`, every unit's full state, the board's changes (smoke, severed limbs, broken crust). Keys sorted |
| `log.txt` | `# stdout`, the log, then `# stderr (stub warnings)`; the same layout as `reference_logs/` |

**Locations and slot addresses.** A critical slot / item / weapon is written `"<Location>#<slot index>"`, the FIRST
slot holding the item ("Right Arm#3"). Units are written as their `side_name`.

**Decision records** (`decisions.json`, a list): `{"n", "kind", "who", "phase", "dice_before", "dice_drawn", "log",
"stubs", "value"}`. Kinds: `foe` (a unit name), `target` (unit name or null), `fire_pick` (the unit that declares next
among the candidates), `move` ((pick, note, psr count at the pick, hazard at the pick)), `physical` (the physical attack
or null), `declaration` (the ranged declaration: value, (weapons, expected damage, weapon heat), arc key, arc action,
the physical plan declared alongside, the limbs' weapons held back as slot addresses). `dice_drawn` is the number of dice
the BOT itself drew while deciding (Gladiator's tie-breaks do: `pick_number` in `movement_selection`); those dice are on
the tape at that place, so the Rust bot must draw them at the same place (stage 8). `log` and `stubs` are the log
lines and stub warnings printed while deciding: a replay prints them again. Only the OUTERMOST decision is recorded
(a bot's dry runs inside it are its own thinking).

**Value encoding (`rt_encode`)**: JSON has no tuple, set or enum, so: `{"_t": [...]}` tuple, `{"_fs": [...]}` frozenset
(sorted), `{"_nt": "ArcAction", field: ...}` namedtuple, `{"_enum": "Cls.NAME"}`, `{"_d": [[k, v], ...]}` a dict with
non-text keys, `{"_unit": name}`, `{"_item": address, "of": unit}` an Equipment object.

**The seam**: `INTEGRATION__decisions.decide(kind, ctx, compute)` wraps those decisions in the engine (`bots.py`, and the
declaration inside `attack_resolution._declare`). In normal play it only calls `compute()`; the recorder sets
`decisions.MODE = "record"`, `tools/port_record.py --replay DIR OUT` sets `"replay"` (nothing computes; recorded
answers, dice and the lines printed are played back). Bot SCRATCH that the engine reads afterwards rides in the
decision: the move search's `path_psrs` / `path_hazard` tables are kept out of the trace (the pick's entries are in the
`move` record). Equipment and mech memos set on first use (`_special`, `_has_profile`, `_no_shields`, `_aes_cache`)
are not dumped.

**Not recorded because the engine re-computes them from state**: stub answers (rate of fire, munition, MASC use, unjam,
capacitor, shields, TAG, heat-explosion bin...) are pure functions of state and config - the Rust translates the stubs
themselves; their warnings are in the log. Decisions a unit's bot makes only when `config.LEGATE`, `TIERS` or the Princess
group switches ask (Legate's estimate, tiers, memory) are bot-internal: they matter in stages 7-8.

## Stages 1-8 (each: translate, compare, commit; a fresh session per stage or per module group)

For every module: read the Python file fully; translate top to bottom; `cargo build`; write a comparison test
that feeds the Rust the SAME inputs as recorded from Python and checks the outputs. Where a stage has no whole-
battle comparison yet, record function-level fixtures: a small Python script calls the function on a few
thousand inputs (taken from real battles, not made up) and writes input / output pairs as JSON for the Rust
test to replay. `fastcore`'s `tests/test_fastcore.py` is the model for this.

| Stage | Translate | Compared against | Done when |
|---|---|---|---|
| 1 Geometry and board | DONE (session 22): `engine/` workspace, crate `btsim_core`: `pyfmt`, `hex_geometry`, `los::hex_distance`, `board_parser` (incl. stitching), `terrain_rules`. `cargo test --release` (from `engine/`) after `python tools/port_stage1.py`: all 356 boards load or are refused with the Python's exact message and warnings (passive and full buildings), 100k label round trips and 100k hex distances, 20 stitched grids and refusals, 60k terrain-rule cases (step_cost, psrs, hazards) identical | session 22, 2026-11-10 | |
| 2 Sight and movement | `los`, `los_cache` logic (no cache), `pathfinder`, `combat` (movement pieces), `ranged_combat._movement_options`, `water` / `hazards` movement parts, `deployment` | LOS result for every hex pair on 10 boards; reachable-state tables for 2,000 recorded (unit, hex, MP) requests | identical sets, same order |
| 3 Units | PARSE DONE (session 22): `equipment`, `mech_state` (the `Mech` struct with an Equipment arena + every pure state query), `mtf_parser`, `config`, `damage_resolution::get_weapons`. `cargo test --release --test stage3_units` (after `python tools/port_stage3.py`): all 4,204 units of data/meks.zip dump identically to the Python, and the 23 LAMs are refused with the same message; printed warnings identical. NOT YET: `structure_weight`, the battle-start attach steps (`ammo`, `electronics`, `equipment_systems`, `capacitor`, `_attach_mech_config`) - they come with their stages | session 22, 2026-11-10 | |
| 4 Damage and piloting | IN PROGRESS (session 22). DONE and checked on tapped Python calls (`python tools/port_tap.py GROUP` then `cargo test --release --test tap_GROUP`): `armor_rules` (2,202 calls), `mech_state` queries + `compute_tmm` + `get_weapons` (10,034), `damage_resolution` + `hit_location` (1,898), `piloting_rolls` + `hazards` + `water` (9,386), plus `advanced_equipment`, `capacitor` (crit_hit), `equipment_systems` and `stubs` (translated, tapped when heat/attacks use them). TO DO: `heat` (read; needs `ammo`, `advanced_weapons`, `fire_modes`, `weapon_profiles` - the `ammo` regexes need the `fancy-regex` crate because of lookaheads), `rng` is `TapeDice`, `domino`, `capacitor` attach/declare/end_phase, `structure_weight`, falls in `domino` | session 22 | The tap tool replays a fixture in Python with a wrapper on named functions and records each call's inputs, dice, outputs, state and log; the Rust test rebuilds and compares (`engine/core/tests/common/mod.rs`) |
| 5 Attacks | `expected_damage`, `weapon_profiles`, `weapon_rules`, `fire_modes`, `ams`, `electronics`, `arcs`, `advanced_weapons`, `advanced_equipment`, `capacitor`, `tag`, `smoke`, `attack_resolution`; then `physical`, `physical_gear`, `clubs`, `charge`, `dfa`, `movement_attacks` (the resolution parts) | per-phase: state before a phase + that phase's decisions + dice -> `trace.jsonl` line after it | identical for every recorded phase |
| 6 The turn loop, bots off | `orchestrator`, `forces`, `stubs`, `config`, the log text, `results` as JSON; `cli` replays `decisions.json` | **whole battles**: `trace.jsonl` and `log.txt` for every fixture | every fixture byte for byte. THE ENGINE IS NOW PROVEN |
| 7 Princess | `princess_fire`, `princess`, `princess_modern`, `princess_group`, `princess_memory`, `battle_value`, `bots` | bots ON for Princess units: the Rust must make the SAME decisions as `decisions.json` at every point (compare decision by decision; on the first mismatch dump both score lists) | Princess v Princess fixtures match with no decision file |
| 8 Gladiator | `weapon_selection`, `future_damage`, `ranged_combat.MoveEvaluator`, `movement_selection` (all searches), `kill_curve`, `vision`, `peril`, `triage`, `tiers`, `legate` | as stage 7. Float order matters most here (trap 4): on a mismatch compare the two spots' score PARTS, find the first term that differs | every fixture plays from settings + dice alone and matches byte for byte |

Stage 7 before 8 because Princess is simpler and has no look-ahead; it shakes out the decision plumbing.
The 23 LAMs and anything `prepare_board` refuses are refused the same way in Rust (same message).

## Stage 9 - cut over, then speed (only after stage 8 passes)

1. `PcgDice`; `btsim` runs batches in parallel (`rayon`, one battle a thread, each battle its own seed as
   `orchestrator.battle_seed` does) and writes results / stats / replay data as JSON in the shapes the Python
   output modules read. `INTEGRATION__main.py` gains `config.ENGINE = "python" | "rust"`.
2. A statistical check that the two engines are the same game on their own dice: 200 battles each of two duels
   and one 12 v 12; wins, turns, damage dealt must agree within the T2 margin tool's interval.
3. Measure. Then, and only then, speed work, one change at a time with every fixture still matching: the caches
   the Python had (trap 9), flat arrays for board and unit data, no cloning in the scoring loops. The scoring
   of spots (`MoveEvaluator.evaluate`, the reply look-ahead, Legate's estimate) is where the time is.
4. Retire `fastcore/` (its code is now inside `engine/`). The Python engine stays in the repo as the reference
   until Daniel says otherwise; new rules and bot work then happen in Rust, with the Python frozen.

## How to work (for the translating model)

- One stage, or one module group of a stage, per session. Start by reading this file and the stage row; end
  with a commit, a Change Record entry and the stage table below updated. Do not start the next stage in the
  same session if context is more than half used.
- Order inside a stage: follow `INTEGRATION__CALL_GRAPH.md` - a module is translated after everything it imports.
- A file over ~800 lines (`attack_resolution`, `orchestrator`, `movement_selection`, `mech_state`, `ranged_combat`,
  `physical`, `damage_resolution`) is translated in pieces, section banner by section banner, building as you go.
- When a comparison fails: run `tools/port_diff.py`, read the Python for that exact step, read your Rust for
  that step, fix. If three attempts on the same difference fail, stop and write what you found under "Found on
  the way" - do not work around it.
- Never mark a stage done with a comparison skipped, shortened or made approximate. A stage that is 95%
  matching is not done; say exactly which fixtures fail and where.
- Rules questions do not arise in a translation: the Python is the rule. If something looks like a rules error,
  write it down for Daniel; do not fix it on either side.
- The Python's 55 checks must still pass at the end of every session (nothing but stage 0 touches the Python).

## What to expect (estimates, not measurements)

- **Speed.** Faithful Rust of this kind of code usually runs some tens of times faster than Python before any
  tuning; how much here is unknown until stage 8 - the bots' scoring loops lean on dictionaries and small
  objects, which translate to slower Rust than flat arrays would. Stage 9's tuning is where most of the gain
  over the current Python-plus-fastcore build will come from. Measure, don't promise.
- **Size.** ~27,000 lines of Python to translate. Stages 5, 6 and 8 are the big ones.
- **Risk.** The likely failure is not a stage that cannot be done; it is a stage declared done that is not.
  The whole-battle comparison at stages 6 and 8 is the protection - keep it exact.


## Where the translation stands and how to continue (written session 22, 2026-11-10)

Rust crate: `engine/core` (`btsim_core`). Run everything from `engine/`: `cargo test --release`. The tests read
`engine/fixtures/` (git-ignored): `python tools/port_fixtures.py --no-replay` (63 battles), `python tools/port_stage1.py`,
`python tools/port_stage2.py`, `python tools/port_stage3.py`, and `python tools/port_tap.py GROUP` for the function-level
groups (`armor state damage piloting`; add groups in `tools/port_tap.py` `GROUPS`).

Design that every module follows (see `battle.rs`): NO globals. `Battle` owns config, dice (`Dice` trait; `TapeDice`
replays a recorded tape), log (`Log`: stdout lines + stub warnings), the board, `units: Vec<Mech>` and the tables the Python
keeps in modules. Functions are `fn f(b: &mut Battle, u: UnitId, ...)`. A mech owns its Equipment arena (`items`, `ItemId`);
slots are `Slot::Name | Slot::Item(id)`. Armor / structure / damage are `pyfmt::Num` (Python int-or-float, printed like
Python). Log text must match the Python exactly (`b.log(...)`; a bare `print` is `b.print(...)`, never quiet). A dry run
is `b.log.quiet += 1`.

Translated and checked (function taps match the Python on every recorded call): pyfmt, hex_geometry, board_parser,
terrain_rules, los, pathfinder, equipment, mtf_parser, mech_state (+ `mech_json`: every attribute, round-trips every recorded
state), armor_rules, damage_resolution, hit_location, piloting_rolls, hazards, water, advanced_equipment, capacitor (crit_hit),
equipment_systems, ammo (`fancy-regex`), heat, electronics, arcs, attack_resolution (the resolution parts: hits, TAC, groupings,
conditions), physical_gear, smoke.probe, physical._location. Taps: `armor state damage piloting ammo heat electronics arcs
attack` (`python tools/port_tap.py GROUP [--limit N]`; keep a group's JSON under ~400 MB or the Rust test runs out of memory:
`attack` uses `--limit 8`); a Rust test per group in `engine/core/tests/tap_*.rs`.
Compiled but NOT yet checked against the Python: stubs (partial), weapon_rules, weapon_profiles, advanced_weapons,
fire_modes (shot plan, options, `Planner`), expected_damage, combat (hit_probability, fc_to_tmm, direction_facing), ams,
attack_resolution (`prepare_declaration` / `finish_declaration` / `run_ranged_phase`, the weapon CHOICE is a `RangedBot`),
clubs, capacitor (attach / declare / end_phase), domino, charge, dfa, movement_attacks (displacement, groupings),
physical (options, push, `run_physical_units`; the choice is a `PhysicalBot`), forces (`unit_in_hex` only), weapon_selection
(range terms, heat limits). These are checked by Stage 6's whole-battle comparison (the first-difference tool says where).

Next, in order (each: read the Python module fully, translate, add its functions to a tap GROUP when it takes only
encodable arguments, run the Rust test):
1. Stage 6 pieces: `forces` (initiative, movement / fire order, team lists, blocked hexes), `deployment`, `tag`, `results`,
   `ranged_combat` (`movement_options`, `path_to`: the engine walks the bot's pick), the remaining `equipment_systems` /
   `hazards` calls the orchestrator makes, then `orchestrator` itself (`_play_turn`, `_move`, `_walk_path`,
   `_after_fall_midmove`, `_phase_heat`, `_phase_end`, `_finish`), a `Replayer` that reads `decisions.json` (kind, who, value,
   dice_drawn to skip, log lines and stub warnings to re-emit), and a test per fixture comparing `log.txt` and `trace.jsonl`.
2. Bot side (stages 7-8): `weapon_selection` (knapsack, fire candidates), `structure_weight`, the rest of `physical`
   (`Worth`, `Planner`, `choose_attack`), `movement_attacks` (`MoverIndex`, `scored_options`, `displacement_worth`), the rest of
   `pathfinder/combat.py` that the movement scoring uses, `ranged_combat` scoring, `movement_selection`, princess*, bots,
   legate, tiers, peril, stack, kill_curve, battle_value, future_damage.

## Where it stands at the end of session 22 (2026-11-10, later)

DONE and checked against the Python: everything the engine does with the bots' answers given - `cargo test --release --test
stage6_battles` replays all 63 fixture battles exactly (state after every phase, dice used, log, stub warnings) and
`--test stage6_attach` rebuilds every fixture's units from their .mtf (parse + attach) equal to units.json. All function
taps pass (`armor state damage piloting ammo heat electronics arcs attack`).

CHECKED bot side (session 22, end): Gladiator's declaration (`gladiator.rs`, `weapon_selection.rs` knapsack,
`structure_weight.rs`) and physical choice (`physical::choose_attack`, `Worth`, plans) equal decisions.json in ALL fixtures;
foe / target equal when there is a single enemy. Floats are compared to 1e-12 relative (Daniel, 2026-11-10: last-digit
differences are float noise, not worth chasing; the old 1-ulp ISLRM5 mystery is closed that way). Check with
`CHECK=declaration,physical,simple cargo test --release --test stage6_battles -- --nocapture` (computes the Rust decision, compares it with
the recorded one, carries on with the recorded one).

DONE (session 23): Gladiator movement (`move_options.rs`, `move_eval.rs`, `move_select.rs`, `move_attacks.rs`) matches every recorded move decision in all 63 fixtures (`CHECK=move`). `gladiator_bots.rs` is a Rust-only Gladiator (no decisions.json): `BOTS=rust cargo test --release --test stage6_battles` plays every Gladiator-v-Gladiator duel from the dice tape alone and matches state, dice, log and stub warnings (movement-note numbers compared to their printed precision: a 1-ulp float difference in a 3.375 tie, per Daniel). Use `pyfmt::Fx` for every Python `{:.Nf}` (Rust rounds exact ties the other way). Notes: `reduced_options` reads each state's PSR count at the moment it is yielded (entering the board reaches states twice).
DONE (session 23, later): Legate (`legate.rs`: plan, foe, extras, triage tiers, peril peak), Gladiator firing order and several-enemy targeting (`bot_targets.rs`), Princess modern (`princess_fire.rs` fire control + physical, `princess_modern.rs` ranker and group, `princess_memory.rs`, `princess.rs`, `princess_geometry.rs`) and Battle Value (`battle_value.rs`, checked on 45 units, `tests/bv_check.rs`). `BOTS=rust cargo test --release --test stage6_battles` plays ALL 63 fixture battles with no recorded decisions and matches the Python (214 s). Checks against decisions.json: `CHECK=legate,move,declaration,physical,princess`. Path tables are cached per ranking (`ranged_combat::path_to_cached`): without it a 12v12 Princess battle never finished.
NOT STARTED: the v0.50.07 Princess (PRINCESS_VERSION '0.50.07'), MOVE_ORDER 'tiered', the research switches left off by default (peril blending, stack, herding, cohesion, team value/exchange, kill_curve targeting), `if_then` movement search; Stage 9: PcgDice, rayon batches, ENGINE switch, results/summary printing, statistical check, speed work.
Princess: princess_fire; move: movement_selection + ranged_combat scoring (Gladiator), princess_modern / princess (Princess)),
battle_value, peril, stack, herding, cohesion, tiers, future_damage; Stage 9 (PcgDice, rayon batches, ENGINE switch, results
printing, statistical check, speed work, retiring `fastcore/`). Each bot decision is checked the same way: add a `check_*`
switch to `replay_bots.rs`, compute with the Rust bot, compare with the recorded answer.

## Stage log (update as stages finish)

| Stage | State | Session / date | Notes |
|---|---|---|---|
| T8 archive decision | DECIDED by Daniel 2026-11-10: NOTHING is archived - Peril, stack, herding, cohesion, team value, exchange, kill curve, tiers stay ("active research into bot logic") and are translated like everything else | session 22 | |
| 0 Comparison tools | DONE (session 22, 2026-11-10): 63 fixtures (15 reference, 6 team, 42 coverage) record and replay in Python exactly (trace, dice position, stdout, stub warnings); 182 of 1,327 engine functions are not reached - listed and sorted in `engine/COVERAGE_GAPS.md`. 56 of 56 checks, benchmark 501 / 495 unchanged | session 22, 2026-11-10 | `python tools/port_fixtures.py` rebuilds `engine/fixtures/` (git-ignored, about 0.5 GB, several minutes on 4 cores) |
| 1 Geometry and board | not started | | |
| 2 Sight and movement | not started | | parts exist in `fastcore/` (PathBoard, LosBoard, hex_distance) - reuse after checking against the fixtures |
| 3 Units | not started | | |
| 4 Damage and piloting | not started | | |
| 5 Attacks | not started | | |
| 6 Turn loop, bots off | DONE (session 22, 2026-11-10): `cargo test --release --test stage6_battles` plays 62 of the 63 fixture battles (all but the 12 v 12 ones, as in the taps) from units.json + dice.json with the bots' answers read from decisions.json (`replay_bots`); every phase's state, the dice used, the log and the stub warnings equal the Python's. Test normalizations: smoke-clear lines sorted; the bots' `_bv_built` / `blocked_hex` scratch attributes ignored; the attach step's own log lines and stub warnings not compared (units start attached) | session 22 | the step between: `_attach_mech_config` from the parsed .mtf (compare with units.json) |
| 7 Princess | not started | | |
| 8 Gladiator | not started | | |
| 9 Cut over, speed | not started | | |

## Found on the way (Python behaviour that looked wrong, or order-dependent; copied as is)

1. **Smoke clears in hash order** (`smoke.end_phase` loops over a `set` of labels). Two clouds that end the same turn print
   their "[End] The smoke at XXXX clears." lines in either order from one process to the next (string hashing). State
   is unaffected. The Rust prints them sorted by label; `tools/port_diff.normalize_log` sorts such runs before comparing.
2. **Gladiator's bot draws dice** for tie-breaks (`movement_selection` lines ~489 and ~499, `rng.pick_number`): the
   decision records say how many (`dice_drawn`). The dice tape position after a move depends on it.
3. **The move search's tables are read by the engine** (`mover.path_psrs` / `path_hazard`: `orchestrator._walk_path`
   asks the search's table whether the walk has terrain PSRs or hazards). The Rust engine should derive that from the
   path itself (stage 2), and must give the same answer as the search's table at the picked state.
4. **`hp_log`, `armor_at_turn_start` and `preexisting_damage_snapshot`** live on the mech and feed bot scoring; they are
   in the unit dump, so the Rust `Mech` carries them.
5. **Dead code in `pathfinder/combat.py`**: `compute_score`, `evaluate_combat_hexes`, `validate_profiles` and the legacy
   evaluator are not called by the integrated engine (the file's movement pieces are). Not translated.
6. **A mixed-in `weapon_locations` quirk**: it lists destroyed weapons' instance ids too (`destroyed_slot_info`), and the
   ranged declaration's "held" set can name them; the decision records write them as the slot addresses the items had.
