# Task specs - work written up so any model can pick it up

Written 2026-11-10 (session 21) after the top-level review. Each task says which model it suits, what to do, the
files, and what "done" means. Backlog letters (A1, D2...) are PROJECT_MAP Section 0's. Before starting any task:
read `CLAUDE.md` and PROJECT_MAP Sections 0 and 7. When a task is finished: Change Record entry at the top of
`INTEGRATION__CHANGE_RECORD.md` marked "REVIEW PENDING (higher-level model)", a REVIEW QUEUE line, strike the task
here, and tell Daniel in plain words what changed.

## Which model for what

(2026-11-10, later the same day: Daniel - the top model is only on loan, "I'll probably be making do with lower
models". So the two design tasks were done or written out in full here, and every task below can be built by
Opus or Sonnet from its write-up.)

| Model | Use it for | Why |
|---|---|---|
| **The top model, when on hand** | A problem whose CAUSE is unknown ("it groups but doesn't win"); the REVIEW QUEUE; reading what an A/B result means; a second look at a spec before a long build | One right diagnosis saves many batteries |
| **Opus** | Building from a written spec where judgement is still needed: the move score (T1), new probes and tools, the Rust port's comparison tools (stage 0) and its two hardest stages (6, 8), rules built from the rulebook with page cites, MegaMek clone work | The checks (55, byte-identical logs) catch its mistakes; the spec carries the thinking |
| **Sonnet** | Module-by-module translation against an exact answer key (the Rust port's other stages), running batteries and filling in tables, documents, small mechanical edits, the GitHub check, the rules-index pipeline | Safe wherever a script, not the model, decides whether the work is right |

Without the top model: never accept "it looks right" - every task below names a check a script can run. A task
that turns out to need a rules or scope call stops and asks Daniel, whatever the model.

**Suggested order.** (1) Decide T8 (what to archive) - it shrinks the Rust job. (2) EITHER build T1 now, before
the port starts (the port freezes the Python's behaviour for its whole length), OR leave T1 until the port is
done and build it in Rust. Recommended: T1 first - it is small, it is the bot's biggest known flaw, and the port
then copies the better bot. T2 and T4 can ride along. (3) T11, the Rust port. (4) Everything else after it.

| Task | Backlog | Model | Needs first |
|---|---|---|---|
| T1 Move score: the clock, the cap, the walk back | A1 | Opus | - |
| T2 Per-battle margin in the battery tools | A9 | Opus or Sonnet | - |
| T3 Scenario suite | A9 | Opus | T2 |
| T4 Physical-value probe | A3 | Opus | - |
| T5 Battle-state object: the design | D2 | DONE - `INTEGRATION__STATE.md` | - |
| T6 Stable unit numbers in the Python | D2 | Opus | only if T11 is dropped |
| T7 Triage knob A/Bs | A2 | Sonnet | T1, T2 |
| T8 Archive the experiments that lost | D4 | Opus or Sonnet | Daniel's OK |
| T9 Rules zip refresh; Interstellar Operations | C5 | Sonnet | Daniel's go |
| T10 Automatic checks on GitHub | D5 | Sonnet | - |
| T11 The Rust translation | D1 | Sonnet (Opus for stages 0, 6, 8 if possible) | T8 decided; T1 built or parked |
| Review queue (m), (o), (p) | - | the top model when on hand; (n) lapses when the port's stage 9 retires `fastcore/` | - |

---

## T1. Move score: the clock, the cap, the walk back (Opus; written out in full so no design is left)

**Problem.** `movement_selection._Lifetime` and `legate.MultiLifetime` score a spot as

    score = dealt + (HP left / T) x M        T = the enemy's damage on me a turn, M = mine on them

i.e. "damage now + damage in the rest of my life". Three things are wrong with the second term:
1. **No clock.** A point of damage twenty turns from now counts the same as one now, so a spot that deals nothing
   and takes nothing keeps the whole term: waiting is free. A unit engages only if this turn's trade beats its
   average future trade (dealt / received > M / T). Between two Gladiators a trade good for one is bad for the
   other, so neither goes in: the Asymptote mirror ran 488 turns with shots in 55; cap draws; 1 v 2 left at 100.
2. **No cap.** "The rest of my life" can be worth more damage than the enemy has HP left to lose. HP I would
   still have after everything is dead is priced as if there were more enemies to shoot.
3. **No walk back.** A spot 20 hexes out of range has the same future as one that fires next turn.
Daniel's ruling stands (2026-11-08): no special "last enemy" mode - the one score must see it.

**The new score** - `config.MOVEMENT_OBJECTIVE = "race"`; "lifetime" stays the default until Daniel has seen
the numbers. All quantities in the units the score already uses (`effective_hp`, structure weighted).

    hp_left    = HP - (received x received_mult + extras)          # as today; if <= 0: score = dealt x dealt_mult
    d          = dealt x dealt_mult
    enemy_left = max(0, E - d)             # E: effective_hp of the foe; with Legate, the SUM over every enemy
                                           # that can matter (the same list MultiLifetime's rates use)
    g          = config.MOVEMENT_RACE_DISCOUNT        # worth of damage one turn later, e.g. 0.9
    w          = config.MOVEMENT_RACE_SURPLUS         # worth of life left over after the last kill, e.g. 0.25
    delay      = turns before I can fire again from this spot (below); 0 if d > 0
    horizon    = max(0, turns_left - delay)           # turns_left: the cap minus the turn now; None = no cap
    t_live     = hp_left / T                          # T, M exactly as today (floors, history blend, fire share)
    t_kill     = enemy_left / M
    n          = min(t_live, t_kill, horizon)         # turns of future fire that count
    G(n)       = n                         if g == 1
                 g x (1 - g^n) / (1 - g)   otherwise  # damage on turns 1..n, each worth g, g^2, ... (n is a float)
    future     = M x g^delay x G(n)
    surplus    = max(0, hp_left - T x t_kill) x (M / T) x g^(delay + t_kill)   if t_kill <= min(t_live, horizon)
                 0                                                              otherwise
    score      = d + future + w x surplus

**The proof it is wired right (must be a test):** with `g = 1`, `w = 1`, delay forced to 0 and no turn cap,
`score` equals the "lifetime" score exactly - then future + surplus = M x t_live. So the first thing to do is run
`python tests/run_checks.py` with `MOVEMENT_OBJECTIVE = "race"` and those neutral settings: all 15 reference
logs must match byte for byte. (If floats differ in the last digit, compute the neutral case through the old
expression `hp_left / T x M` when g == 1 and w == 1 and say so.) Only then try other values.

**delay.** `0` if the spot's `dealt > 0`. Otherwise `ceil(max(0, distance from the spot to the foe - my longest
weapon range) / max(1, my walking MP))`, at least 1 (I did not fire this turn). With Legate use the nearest
enemy that can matter. Distance is hex distance, not a path - good enough, and say so in the comment. The enemy
is assumed not to shoot me during the delay (same assumption for both sides).

**turns_left.** The picker does not know the turn today. `orchestrator.Battle` has `turn` and `max_turns`: put
both where the picker can read them (the simplest: `forces.set_clock(turn, max_turns)` called at the start of
each Movement Phase beside the existing `forces` set-up, `forces.turns_left()` returning `None` outside a
battle). `config.MOVEMENT_RACE_HORIZON = True/False` switches the horizon term.

**Where.** `INTEGRATION__movement_selection.py`: a `_Race` class beside `_Lifetime` (same constructor, plus E
and the mover's range / walking MP for delay; `__call__` needs the spot's distance, which `_objective`'s
signature does not carry - pass delay through `extras`' neighbour: add an optional keyword `delay=0` to the
objective call sites, 4 of them, grep `objective(`), and `_link`. `INTEGRATION__legate.py`: `MultiRace` beside
`MultiLifetime`, `objective_for`, and `_threat` (uses the same formula for a foe). The modeled second mover in
the two-ply gets the same objective for its own side, as today. Settings in `INTEGRATION__config.py` beside
`MOVEMENT_LIFETIME_*`, with the note() text extended so a verbose log shows the parts.

**Tests** (`tests/test_movement_selection.py`, plain numbers, no battle needed): neutral settings = lifetime
score; with g < 1 a spot that fires (d > 0, small received) beats "hide" (d = 0, received = 0) when I am ahead;
with w < 1 and the enemy nearly dead, finishing it beats an equal trade that leaves it alive; a far spot scores
below a near spot with the same d = 0; hp_left <= 0 keeps only d.

**Measure, in this order, and show Daniel the table** (g in 0.85 / 0.9 / 0.95, w in 0.25 / 0.5; start with
g 0.9, w 0.25 and vary one at a time):
(a) the Asymptote mirror reference battle: turns to a result, turns with shots (today: the 50-turn cap);
(b) `python tests/ab_batches.py 20` on Kontio v Hammerhead and two more duels: wins, turns, cap hits;
(c) the battery `pg 20 --legate --turns 100`, five seed sets, against the triage default row (BOTS.md): wins,
    draws, 'Mechs left, turns - and T2's margin if built;
(d) a `gg` mirror battery, 20 battles: draws at the cap.
What good looks like: (a) ends well inside 50 turns; (d) few draws; (c) not worse than 51 / 47 / 2 within the
noise, with fewer long battles. What bad looks like: Gladiator's lights diving in alone again (units lost in
turns 1-6, BOTS.md) - then g is too low.

**Done when:** switch, tests and table exist; the default changes only on Daniel's word (then
`check_reference_logs.py --update` and a Change Record line). New Section 6 row for the settings.

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

## T5. The battle-state object: the design - DONE

`INTEGRATION__STATE.md` (2026-11-10): what a battle's state is, table by table; names instead of memory
addresses; the shape; the engine boundary.

## T6. Stable unit numbers in the Python (Opus) - ONLY if the Rust translation is dropped

The Rust translation builds the right shape directly (RUST_PORT trap 6) and freezes the Python, so this is not
done in that case. Otherwise follow the order at the end of `INTEGRATION__STATE.md`, one module group per commit.
Each step: `python tests/run_checks.py --bench` identical (logs byte for byte, HP 501 / 495),
`check_reference_logs.py --round-trip` passes, timing within 3%. Never mix a behaviour change into these commits.
**Done when** no engine or bot table is keyed by `id()` of a unit, weapon or slot (the art modules
`INTEGRATION__shell*` are out of scope) and `tests/test_saved_state.py` no longer needs the re-pointing step.

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

## T11. The Rust translation (Sonnet; Opus for stages 0, 6 and 8 if possible)

Daniel, 2026-11-10: "have Sonnet translate the monte carlo into rust. Just bite the bullet and remove
translation as a source of slowdown." The whole plan is `INTEGRATION__RUST_PORT.md`: the Python stays as the
answer key, comparison tools first (stage 0), then nine stages each ending in an exact match, a stage log to
keep up to date. One stage (or part of one) per session. Read that file before anything else.
