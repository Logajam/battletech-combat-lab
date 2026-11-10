# What a battle's state is - design note (task T5, done 2026-11-10 by the top-level review)

For: the Rust translation (`INTEGRATION__RUST_PORT.md`, trap 6), saves inside a turn (backlog D3), the Combat
Lab. It answers one question: when a battle is stopped at any point, what has to be carried to continue it
exactly? Today the answer is spread over the `orchestrator.Battle` object, fields hung on each mech, and about
40 module-level tables, many keyed by a unit's memory address (`id()`). Two real bugs came from that (a reload
revived destroyed equipment; a tie-break by address made a battle depend on what ran before it).

## The three kinds of thing

**1. TRUE STATE - must be saved, must be in the Rust `Battle`.**

| What | Where it lives in the Python today |
|---|---|
| Units, in roster order: everything on a mech (position, facing, twist, prone, heat, armor / structure per location, crit slots and what is destroyed, ammo per bin, jams, capacitor charge, pilot hits / consciousness, shutdown, pending PSRs, movement this turn, `hp_log`, its config: team, bot, skills, search settings) | `mechsim/mech_state.py` objects in `battle.units`; extra fields added by other modules with `mech.x = ...` / `getattr(mech, "x", default)` - grep them all (RUST_PORT trap 7) |
| The board as it now stands | `battle.terrain_map`; changes tracked in `hazards._BROKEN` (magma crust), `smoke._SMOKY`, `clubs._LIMBS_ON_GROUND`; `hazards._BOARD`, `smoke._BOARD`, `water._BOARD` are pointers to the same board |
| The dice | `battle.battle_rng` (`config._ACTIVE_RNG` points at it) - generator state AND the place in the current block |
| Turn and progress | `battle.turn`, `battle.over`, `battle.max_turns`; INSIDE a turn (not saved today): the phase, the Initiative order, who has moved / declared, declared attacks not yet resolved, this phase's reports |
| Results so far | `battle.result`, `battle.unit_stats`; `stubs` counters; `stats._active` / `replay._active` recorders |
| Bot memory that changes later choices | `princess_memory._TEAMS` (heat map, posture); `princess_fire._assigned` (damage friends declared this phase); `legate._PLANS`, `_OWN` (this phase's estimate), `legate._FRIEND_DMG`; `tiers._TIERS`; `bots._PRINCESS_EYES`; `weapon_selection._FIRE_CONTROL` (whose weapon choice is in force) |
| Settings | every UPPERCASE name in `INTEGRATION__config.py` |

**2. PHASE SCRATCH - valid for one phase, rebuilt at its start; never saved, but must be CLEARED at the right
moment.** `legate._RATES`, `_SHARES`; `peril._FIELDS`, `_FOOT`; `movement_attacks._WORTH`; `forces._BATTLE` (the
unit list in force). In Rust: fields of a `PhaseScratch` struct created at the start of the phase and dropped
at its end - so "forgot to clear it" cannot happen.

**3. PURE CACHES - a fresh computation gives the same value; never state.** `expected_damage.
_EXPECTED_CLUSTER_HITS_CACHE`, `kill_curve._CACHE`, `los_cache._RUST_LOS` / `_BOARDS`, `los._LINE_SHAPES`,
`pathfinder._BOARDS`, `vision._TABLES`, `structure_weight._MULTIPLIERS`, `weapon_selection._TABLE_CACHE` /
`_SHARED_TABLES`, `damage_resolution._DERIVED` / `_WEAPONS`. In Rust: left out of the first translation
(RUST_PORT trap 9), added back in stage 9 as fields of a `Caches` struct owned by the `Battle` (per-board ones
by the `Board`), keyed by `UnitId`, each with the event that empties it written beside it.

Not battle state at all: `timing._totals` / `_stack`, `orchestrator._WORKER` (process bookkeeping).

## Names instead of addresses

- `UnitId` = the unit's index in the roster (`battle.units`), fixed for the battle; destroyed units keep their
  number. Printed names stay `side_name`.
- A location = an enum (HD, CT, LT, RT, LA, RA, LL, RL, and the quad / tripod / superheavy forms as the Python
  names them). A critical slot = `(UnitId, location, slot index)`. A weapon or item = the slot address of its
  FIRST slot; a split item lists all its slot addresses. An ammo bin = its slot address.
- A hex = `(column, row)` as `hex_geometry` uses them; the label ("0507") is for printing.
- Wherever the Python keys a table by `id(mech)`, `id(weapon)` or `id(terrain_map)`, the Rust keys by these.
- Ties are broken by roster order (already the Python's rule since the triage fix) - never by anything else.

## The shape (Rust; the Python can adopt the same shape later if it lives on)

    Battle { config, board, units: Vec<Mech>, dice, turn, phase: PhaseProgress, result, unit_stats,
             stub_counts, memory: BotMemory, caches: Caches }
    PhaseProgress { phase, initiative_order, moved: Vec<UnitId>, declared: Vec<Attack>, reports }
    BotMemory { princess: per-team heat map + posture, legate: this phase's estimate, tiers, assigned damage }
    PhaseScratch { rates, shares, peril fields, footprints, worth }      // lives for one phase only

A save = `Battle` minus `caches`, written as JSON. A save inside a turn is then the same thing with
`PhaseProgress` filled in - which is what backlog D3 (a) needs and the pickle cannot give.

## The engine boundary (for the Combat Lab and any other front end)

Three calls are enough: `new_battle(config, units, board, seed) -> Battle`; `step(&mut Battle) -> Event list`
(advance to the next decision point or the end of the phase); `decide(&mut Battle, Decision)` (supply a move /
attack from outside, e.g. a human or a different bot - the same `Decision` records `tools/port_record.py`
writes in RUST_PORT stage 0). The built-in bots are just callers of `decide`. Bots score MANY spots per call
inside the engine; nothing crosses the Python / Rust line per spot.

## If the Rust translation goes ahead

Do not refactor the Python to this shape first (task T6 is then dropped): the translation builds the right
shape directly and the Python is frozen as the answer key. If the translation is abandoned, T6 stands: change
the Python one module group per commit in this order - phase scratch (Legate, peril, tiers), bot memory, board
changes, pure caches - with all 55 checks, the benchmark and `check_reference_logs.py --round-trip` identical
at each step.
