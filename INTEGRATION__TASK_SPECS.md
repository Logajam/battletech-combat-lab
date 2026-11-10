# Task specs - work written up so any model can pick it up

Written 2026-11-10 (session 21) after the top-level review. Each task says which model it suits, what to do, the
files, and what "done" means. Backlog letters (A1, D2...) are PROJECT_MAP Section 0's. Before starting any task:
read `CLAUDE.md` and PROJECT_MAP Sections 0 and 7. When a task is finished: Change Record entry at the top of
`INTEGRATION__CHANGE_RECORD.md` marked "REVIEW PENDING (higher-level model)", a REVIEW QUEUE line, strike the task
here, and tell Daniel in plain words what changed.

## Which model for what

| Model | Use it for | Why |
|---|---|---|
| **Fable** (most capable, costs the most) | A problem whose CAUSE is unknown ("it groups but doesn't win", "it won't close in"); a design that is costly to get wrong and that other work builds on (the move score, the battle-state object, the engine boundary); the REVIEW QUEUE; deciding what an A/B result means | One right diagnosis saves many batteries. The peril line took a week of builds and 20-battle sets around a flaw that is in one formula |
| **Opus** | Building from a written spec where judgement is still needed: new probes and tools, rules built from the rulebook with page cites, refactors that must keep every reference log identical, MegaMek clone work | The checks (55, byte-identical logs) catch its mistakes; the spec carries the thinking |
| **Sonnet** | Running batteries and filling in tables, documents, small mechanical edits, the GitHub check, the rules-index pipeline (its own CLAUDE.md already says helpers on Sonnet) | The work is mostly waiting and copying numbers; nothing to decide |

Rule of thumb: Fable writes the spec and reads the result; Opus or Sonnet does what is in between. A task that
turns out to need a rules or scope call stops and asks Daniel, whatever the model.

| Task | Backlog | Model | Needs first |
|---|---|---|---|
| T1 Move score: enemy HP, clock, walk back | A1 | Fable (design + first build) | - |
| T2 Per-battle margin in the battery tools | A9 | Opus | - |
| T3 Scenario suite | A9 | Opus | T2 |
| T4 Physical-value probe | A3 | Opus | - |
| T5 Battle-state object: the design | D2 | Fable | - |
| T6 Stable unit numbers: the change | D2 | Opus | T5 |
| T7 Triage knob A/Bs | A2 | Sonnet | T1, T2 |
| T8 Archive the experiments that lost | D4 | Opus | Daniel's OK |
| T9 Rules zip refresh; Interstellar Operations | C5 | Sonnet | Daniel's go |
| T10 Automatic checks on GitHub | D5 | Sonnet | - |
| Review queue (m), (n), (o), (p) | - | Fable | - |

---

## T1. Move score: enemy HP, a clock, the walk back (Fable)

**Problem.** `movement_selection._Lifetime` and `legate.MultiLifetime` score a spot as
`dealt + (HP left / enemy's rate) x my rate`. Three things are missing: (1) the enemy's HP - a kill is worth only
its damage points, and "damage in the rest of my life" is never capped by what the enemy has left; (2) time - a
spot that deals nothing keeps the whole future term, so waiting is free and a draw at the turn cap costs nothing;
(3) distance - a spot 20 hexes out of range has the same future as one that fires next turn. A unit therefore
engages only when this turn's trade beats its average future trade (dealt / received > my rate / their rate);
between two Gladiators what is good for one is bad for the other, so neither moves in. Seen as: the Asymptote
mirror (488 turns, shots in 55), cap draws, 1 v 2 left at 100 turns.

**Build** as `config.MOVEMENT_OBJECTIVE = "race"` (default stays "lifetime" until A/B'd), in both classes:
- `turns_i_live = HP left / enemy's rate`; `turns_left = config.MAX_TURNS (or the battery's cap) - turn now`;
  `delay` = turns of walking from the spot to the nearest hex within my longest range of the foe (0 if the spot
  can fire; `hex distance beyond range / walking MP`, rounded up).
- `future = my rate x max(0, min(turns_i_live, turns_left) - delay)`, capped at the enemy's remaining effective
  HP minus `dealt` (in a team battle: the summed HP of the enemies that can matter).
- `+ survival`: when the cap binds (I am expected to kill them first), add `weight x HP I would have left at
  that point` - so winning with more left scores higher. `config.MOVEMENT_RACE_SURVIVAL` (start at 1.0, HP
  counted in damage points through my rate / their rate so the units match).
- The orchestrator must tell the picker the turn number and the cap (today neither reaches it).
- Daniel's ruling: no special "last enemy" mode - this must come out of the one score.

**Measure.** (a) Asymptote mirror reference battle: turns to a result, turns with shots. (b) `ab_batches.py` on
three duels incl. Kontio v Hammerhead, 20 battles. (c) Battery `pg 20 --legate --turns 100`, the five seed sets,
against the triage row: wins, draws, 'Mechs left, turns, and the T2 margin if built. (d) `gg` mirror battery:
draws at the cap.

**Done when:** the switch exists with tests (`tests/test_movement_selection.py`: a spot that hides scores below
one that fires when I am ahead; a kill within reach beats an equal trade); numbers reported to Daniel; default
changed only on his word (then `--update` the reference logs).

## T2. Per-battle margin in the battery tools (Opus)

**Why.** Win counts need ~100 battles to separate two settings; several defaults were picked from 20. A margin
per battle uses the same battles better.

**Build.** In `tests/battery_summary.py` (reads `run_stats/baseline/saved/<settings>/battle_NNN.json`):
- per battle `margin = Blue's share left - Red's share left`, share = HP left / HP at start (already in the saved
  rows; also a BV-weighted version with `INTEGRATION__battle_value` if the per-unit rows allow it);
- per set: mean margin and its 95% interval;
- `--compare A B`: battles paired by number (same seed), the mean of the differences and its 95% interval, the
  count of battles better / worse, and one plain line: "B is better / worse / can't tell at this size".
Nothing in the engine changes; no reference log moves. Add `tests/test_battery_summary.py` with made-up rows.

**Done when:** the triage v no-triage sets (100 battles each, already saved if `run_stats/` survives; else re-run
one seed set of each) print a comparison, and README's battery line mentions `--compare`.

## T3. Scenario suite for bot A/Bs (Opus; after T2)

**Why.** Nearly every bot default was tuned on one roster, one 32 x 17 field, one opponent.

**Build.** `tests/scenario_suite.py`: a named list of scenarios, each = two rosters, a board (or stitched pair),
bots, cap. Start with nine: three rosters (the current 12 v 12; a 4 v 4 lance of mixed weights; a fast / light 8 v
8 - units from `data/`, ask Daniel if he wants particular lances) x three fields (the baseline field; a hilly or
wooded stitched pair; one with water) - all Princess v Gladiator - plus two Gladiator v Gladiator mirrors as the
stall check. Reuse `baseline_battery.py`'s runner and saving (same flags pass through; results under
`run_stats/suite/<scenario>/<settings>/`), resumable, splittable over cores. Summary through T2's tool: one row a
scenario and a total.

**Done when:** `python tests/scenario_suite.py --battles 5` runs all eleven with defaults and prints the table;
the default numbers are recorded in `INTEGRATION__BOTS.md` as the suite's baseline. Not part of run_checks.

## T4. Physical-value probe (Opus)

**Why.** The move score credits about 6 raw points of kick / punch per adjacent attack; about 3 land (BOTS.md,
2026-11-07). Hypothesis to test, not a finding: a kick needs exactly range 1 and Legate's estimate of the
enemy's end hex is off 2.7 hexes on average, so the move score counts kicks against a spot the enemy never
takes; and / or the physical phase declines or loses kicks the move score counted (target fell or died in the
ranged phase, a better plan, the attacker fell).

**Build.** With `tests/probe_hooks.py` / `turn_inspector.py`: for every Gladiator move whose chosen spot's score
included a physical part, record (1) the physical value counted and against which enemy at which hex, (2) whether
that enemy really ended adjacent, (3) what the physical phase then chose and its expected value, (4) what landed.
Report over ~13 battles of the battery: the share of counted value lost at each step.

**Done when:** a table and a one-paragraph reading in `INTEGRATION__BOTS.md`. No fix in this task - the fix
depends on the answer (e.g. weight the physical part by the odds the enemy is where Legate says).

## T5. The battle-state object: design (Fable)

**Why.** State lives in module-level tables keyed by `id()` (about 300 uses; `_RATES`, `_SHARES` in Legate, the
weapon caches, the stubs' counters...). Two real bugs came from it (a reload revived destroyed equipment; a
tie-break by memory address made one battle depend on what ran before it). Saves inside a turn, the Combat Lab
and any Rust port all need the same answer to "what is a battle's state".

**Deliver** a design note (`INTEGRATION__STATE.md`), no code: the list of what a battle's state is (board, units,
dice, phase progress, per-phase caches v true state); a stable unit number and item number scheme; which module
tables become fields of one `Battle` object and which are pure caches that can be rebuilt; the order to change
them in so every step keeps the reference logs identical; what the engine boundary for a compiled core would be
(score many spots per call).

## T6. Stable unit numbers: the change (Opus; after T5)

Follow T5's order, one module group per commit. Each step: `python tests/run_checks.py --bench` identical (logs
byte for byte, HP 501 / 495), `check_reference_logs.py --round-trip` passes, timing within 3%. Never mix a
behaviour change into these commits. **Done when** no engine or bot cache is keyed by `id()` of a unit, weapon or
slot (art modules `INTEGRATION__shell*` are out of scope) and `tests/test_saved_state.py` no longer needs the
re-pointing step.

## T7. Triage knob A/Bs (Sonnet; after T1 and T2)

Run, don't design. For each knob, one change at a time against the triage default, five seed sets x 20 at
`--turns 100` (four cores, `--first / --last`): `--triage` share 0.15 / 0.35; `--triage-hot` 1.5 / 3;
`--triage-cool` 1.25 / 2; peak v mean in the ratio (needs a small flag in `INTEGRATION__triage.ratio` - ask Opus
if it is not a one-line switch). Table through `battery_summary.py --compare`. Report the table to Daniel; change
no default.

## T8. Archive the experiments that lost (Opus; only after Daniel says which)

Candidates, all OFF by default after A/Bs showed no gain: Peril in the move score (`config.PERIL`), stacked
coverage (`STACK`), herding, cohesion, team value, exchange (`LEGATE_*`). They are Daniel's designs - ask him
which to keep as live options. For each one he releases: remove its branch from `legate.Extras.adjust`, its
settings, its battery flags and tests; keep the module file under `archive/` with a note of the Change Record
entry that holds its numbers. Checks identical before and after (they are off, so nothing may move).

## T9. Rules library (Sonnet helpers, per `battletech-rules-index/CLAUDE.md`; on Daniel's go)

(a) Rebuild `rules/Battletech_Rule_Reference_Index.zip` from the rules repo's `main` so TO:AUE and TO:AR are in
it; update CLAUDE.md's rules paragraph. (b) Interstellar Operations: the rules repo's own recipe (prep script,
chapter map, base rip one helper at a time, errata v1.21 and IOAE v3.01, summary, index), about 4M helper tokens
for a ~230-page book - IntOps is 394 pages, so budget about 7M and split over days.

## T10. Automatic checks on GitHub (Sonnet)

`.github/workflows/checks.yml`: on every push and pull request - Python 3.13, `pip install -r requirements.txt`,
build `fastcore` with maturin (README has the commands; `tests/test_fastcore.py` skips when it is not built, so
the build must be a hard step), `python tests/run_checks.py`. No secrets, no deploy. **Done when** the run is
green on the branch and CLAUDE.md's logistics line says "merge once the checks on GitHub are green". Check first
that Actions minutes are available on the private repo (free tier: 2,000 a month; a run is about 3 minutes).
