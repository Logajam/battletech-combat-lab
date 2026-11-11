# Review brief for the Rust engine (written 2026-11-11, session 23; reviewed session 24)

**Session 24 review, in short** (Change Record "RUST ENGINE REVIEWED"): done - the batch panic hunt and an exact random-battle check
(`tools/port_fuzz.py`), the debug leftovers, the per-battle equipment load, the hashing, LOS and movement-table caches, name-fact memos. Both
`unsafe` sites were read and are sound as used (`path_to_cached`: each pointer is used before the next insert; `legate::proposals_for`: `units`
is not touched while the closure runs). What is still true below is marked; the rest is history.

Read first: `INTEGRATION__RUST_PORT.md` (plan and rules: the Python is the answer key, exact match or not done) and the Change
Record entry "RUST PORT STAGES 1-9 FIRST CUT". Branch `claude/zen-cerf-ngyndx`, no PR yet.

## What exists
- `engine/core` (`btsim_core`): the engine and bots. `engine/btsim`: batch runner (rayon). `tools/port_scenario.py`,
  `tools/port_stat_check.py`: scenario writer, two-engine statistics check. Fixtures: `python tools/port_fixtures.py` (git-ignored
  `engine/fixtures`, 63 battles).
- Where the bots live: `gladiator*.rs`, `move_*.rs`, `legate.rs`, `bot_targets.rs`, `princess*.rs`. The turn loop: `orchestrator.rs`.

## How to run the evidence
- Rust alone vs the Python's whole battles (no recorded decisions): `cd engine/core && BOTS=rust cargo test --release --test stage6_battles`
  (about 215 s). With recorded decisions: no env. Per-decision checks against the Python's choices:
  `CHECK=legate,move,declaration,physical,princess cargo test --release --test stage6_battles -- --nocapture`. `FIXTURES=a,b` limits.
- Function-level taps: `tap_*.rs`; units from .mtf: `stage6_attach`; BV: `bv_check`.
- Statistics: `python tools/port_stat_check.py FIXTURE_NAME 200 --seed 7` (Python and Rust batches, z-tests).
- Long runs: ALWAYS background them and read the output file; a 12 v 12 hang cost 20 minutes once.

## Where bugs are likely (paths the 63 fixtures never reach)
1. Anything a real batch reaches that a recorded battle did not. Three were found in the first batches (see the Change Record). Run
   many seeds of many scenarios (`btsim --battles 500`) and look for panics before anything else.
2. The `panic!`/`assert!` placeholders for untranslated switches (grep `not translated`). They must stay loud.
3. `unwrap()`s on data a real roster could vary (units with odd equipment, quads, tripods, superheavies, LAMs, infantry-pods).
4. Float order: the Python's summation order is copied; a "tidier" sum would break exact matches.
5. `legate.rs`: caches keyed by `moved` (a stale profile once broke a decision), `unsafe` in `proposals_for` (`units_ptr`).
6. `ranged_combat::path_to_cached`: raw pointer into a HashMap value; valid only while no later insert happens before use.

## Speed: where it stands after session 24, and what is left
- Measured on one core: 40 duels 4.3 s (was 21.6), two 4 v 4 4.7 s (was 17.9), two 12 v 12 of 10 turns 21 s (was 67). No `perf` in the cloud
  container: `valgrind --tool=callgrind` on a build with `CARGO_PROFILE_RELEASE_DEBUG=true` and LTO off, one battle, `callgrind_annotate
  --inclusive=yes`.
- Left, team battles first: `MoveEvaluator::evaluate` / `FireSide::score` / `select_weapons_scaled` (a third of a 4 v 4: the Python's `FireTable`
  idea - price each weapon per distance and TN once - is not built; an evaluator is still made per (unit, foe) by Legate); `Opt` carries its hex as
  a `String` and is cloned and hashed everywhere (make the label a small Copy value); `Classes::of`, `with_physical`, `arcs::key_for`;
  `Scenario::battle` re-reads units and board from JSON per battle.

## Optimisation leads as written in session 23 (most are done: see above)
- Rust is only ~2x the Python+fastcore. Obvious costs: `Battle::new` loads `equipment.json` per battle (`EquipmentDb::load`; make it a shared
  `OnceLock`); `Mech` clones in scoring loops (`options(...)` clones the whole unit); `FireSide::score` and `MoveEvaluator::evaluate`
  clone `Vec`/`HashSet` per call; `select_weapons_scaled` recomputes `get_weapons`/table values per call (the Python cached a table:
  `FireTable`); pair LOS is traced per hex per evaluator (Python had `los_cache`); `Legate` builds an evaluator per (unit, foe).
- Rules for speed changes (RUST_PORT Stage 9): one change at a time, all 63 fixtures still equal (`BOTS=rust`), caches only of pure functions.

## Known differences from the Python on purpose
- Dice: `PcgDice` is not NumPy's stream; compare engines by statistics only.
- Printed floats: `pyfmt::Fx` is Python's rounding; movement notes are compared to their printed precision in tests (1-ulp float differences).
