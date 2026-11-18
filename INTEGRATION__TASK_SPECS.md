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
| T15 Low-poly reference models: the other 31 'Mechs | E3b | Opus | - (the AI sheets are in `reference_art/ai_sheets/`) |
| T11 The Rust translation | D1 | Sonnet (Opus for stages 0, 6, 8 if possible) | T8 decided; T1 built or parked |
| T14 MegaMek bridge (our bots in a live MegaMek game) | E4 | Sonnet; Opus for B1 | Daniel's OK to build and run MegaMek (B0) |
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

(a) SUPERSEDED (2026-11-13): the zip copy was removed; sessions read the rules repo itself (CLAUDE.md). (b) Interstellar Operations: the rules repo's own recipe (prep script,
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

## T12. Hydra, the third bot: the movement play-out (Opus or higher)

Plan and next stage: `INTEGRATION__HYDRA.md` Section 6 (S5a first). Trials: `tools/hydra_trial.py`.

## T13. Combat Lab on the Rust engine (CL1-CL9)

Spec sheets, one job each, with the order and which model suits: `INTEGRATION__COMBAT_LAB_SPECS.md`.

## T14. MegaMek bridge: our bots in a live MegaMek game (Sonnet; Opus for stage B1)

Daniel, 2026-11-12: "Bridge that allows our bots to connect to a live Megamek game"; specs first, then "give the
grunt work of the basic build to sonnet". The full spec, from a read of MegaMek's source: `INTEGRATION__MEGAMEK_BRIDGE.md`
(what MegaMek offers, the design, the request / answer JSON, records and fallbacks, stages B0-B7 each with a
check a script can run). Start with B0 (needs Daniel's OK to build and run MegaMek's downloaded code) and B1
(`btsim decide` and its parity check), which don't depend on each other.

## T15. Low-poly reference models: the other 31 'Mechs (Opus; the AI sheets are in)

Daniel, 2026-11-16 (session 27). Redraw each 'Mech of the TRO 3025 extract as a low-poly model: five orthographic views, one
A-stance, "roughly recognisable, even more removed from the original source". The models are REFERENCE: later, the block
dictionary (`data/token_blocks.json`) and the override list (`data/token_overrides.json`, `data/token_reference_tags.json`) are
built from them. Daniel is happy to cheat on the retro look (800 triangles, not the '95 400), "retro appearance while still happy
to use modern tools" (animation will need them). Everything is PRIVATE (`reference_art/` is on `publish_public.py`'s
`PRIVATE_PATHS`). Read `reference_art/README.md` first: it has the model format, the part kinds and the coordinate rules.

**REVISED ORDER (Daniel, 2026-11-16, later): BUILD THE BLOCKS FIRST.** The three test models were written from raw shapes
(box, wedge, bar, tube, hull, dome) BEFORE `reference_art/block_taxonomy.json` existed, so none of their parts is an instance of a
dictionary block: the same "slab boot" would be rebuilt from scratch on every 'Mech. Do not add the other 31 models that way. Order:
(1) T15a, the block library: each taxonomy type (22 parts, 88 types, common ones first: foot slab_boot, lower_leg
tapered_slab_shin, upper_leg tapered_slab_thigh, upper_torso boxy_chest_sloped_shoulders, shoulder_pod and shoulder_disc,
launcher_bay, lower_arm fist_arm and barrel_arm, hand fist, head dome_helmet and bubble_canopy) becomes a named, parametrised
GENERATOR. (2) Retrofit the three built models so every part is a block instance (`"block": "foot/slab_boot", "params": {...}`)
and `check` fails a part with no block. (3) T15b: the other 31, composed from blocks (new block types only where the taxonomy
has a gap, and then the taxonomy is updated).

**Design for T15a (Claude's recommendation, 2026-11-16; Daniel's idea: "a much higher polygon count for our blocks, then dumb down
the final build").**
- LEVELS OF DETAIL come from the generator, not from decimating a mesh. A block takes a `lod` argument and is DESIGNED at each
  level: LOD0 high (bevels, 16-24 sided tubes, 6-8 dome rings, tube mouths and plates as real geometry), LOD1 medium, LOD2 the
  reference level (what the three models are now: boxes, wedges, 6/8-sided tubes, hulls and domes). Decimating a detailed mesh
  gives unpredictable silhouettes and loses the hard-edged retro look; a generator keeps the look chosen. Daniel is happy to
  cheat on the '95 look: the retro look is a style, modern tools are allowed.
- BUDGETS: the whole model at LOD2 stays under 800 triangles (the rule now enforced by `check`). Suggested LOD1 about 3,000 and
  LOD0 about 15,000 per 'Mech; measure the Combat Lab at 12 v 12 before fixing them (the art specs' A2 trap: solid count multiplies).
- CHECK: the silhouette of LOD1 and LOD2 must stay within a set share of LOD0's (render all three from the same camera and compare
  the black shapes; the art specs' A3 variant check is the pattern). A scripted check can do this; the look is still Daniel's.
- ANCHORS: each block states its attachment points (a foot has `ankle`; a shin `knee` and `ankle`; a shoulder `arm` and `torso`),
  so blocks snap together and a model is a list of block instances with sizes, not coordinates. This is also what makes the
  override list work: an override names blocks and params.
- UNITS: sizes in the model's own units (figure height about 10); a block's params are shares of the part it sits on, so a block
  scales with tonnage.
- MOUNTS (Daniel, 2026-11-16: "blocks also need mounting points for weapons, equipment, and greebles. Like that blade coming off the
  shoulder of the JagerMech, that's a greeble"). Every block carries mount points of three kinds: WEAPON (by family, with slot
  capacity, tied to a unit-file location so the .mtf's items land on the right block), EQUIPMENT (jump-jet nozzles, heat-sink vents,
  ECM and probe domes, AMS...), GREEBLE (decorative: blade fins, ear pods, antennas, dishes, vent grilles, hazard panels, hose ribs,
  glazing bands, decals). The spec is in `reference_art/block_taxonomy.json` under `mount_points` and `greebles`. Mount points are the
  same at every level of detail (a mount must not move when the detail changes). A per-unit override can name a greeble outright
  (the JagerMech's shoulder blade); the rest are shuffled by the unit's name hash as in the Skeleton spec, with that spec's hardpoint
  counts. The greeble class names reuse the `kit` vocabulary of `data/token_reference_tags.json`.
- KEEP THE TYPES IN HAND (Daniel, 2026-11-16: one extra 'Mech added five types; there may be 400+ pictures to come). Policy in
  `reference_art/block_taxonomy.json` `pruning_policy`: build blocks as FORM x PRESET x MODIFIERS (about 8 forms, named presets per body
  part, composable modifiers), not one type per shape; admit a new preset only if its silhouette is more than a set share different
  AND it is on 3+ units (or Daniel names it); everything else is a per-unit special; a soft cap of about six presets per part;
  classify new art against the existing presets and log only the residual as candidates for Daniel to prune in batches. Do the first
  prune (merge the drum family and the slab families) BEFORE writing generators, so the library is built on the pruned set.
- DATING (Daniel, 2026-11-17: tag blocks with a date, then build a unit from blocks of its own era). Three SEPARATE tags in the
  taxonomy's `dating` block: unit year (the unit file's `era:`, present on all 4,227 files), tech base (IS / Clan), art source (book
  and artist). Computed `years_seen` is on every type. Do NOT choose blocks by year yet: the 34 'Mechs span 2475-2898 but share one
  book's art style, so the year says nothing about the look until there is art from three or more books or periods. Make the
  generator accept the tags now (cheap) and switch the selection on later.
- WHERE: new files under `reference_art/` (a `blocks/` folder and a loader in `tools/lowpoly_ref.py`), still private; the existing
  `data/token_blocks.json` and the generator are NOT touched until Daniel says the dictionary is ready.

**T15a first pass (Claude, session 28, 2026-11-17): DONE for the common dozen.** Daniel's choices that day: Claude prunes and he checks (`prune_1` in the taxonomy: nothing deleted, merges marked `merged_into`); HIGH and LOW only (MEDIUM later); the twelve named above first. Built: `tools/lowpoly_blocks.py` (generators, anchors and mounts identical at both levels, a depth-buffer renderer that outlines only creases, the LOW-v-HIGH outline match, `check`, `sheets`, `page`) and `reference_art/blocks/` (`library.json`: per block the exact crop of the TRO drawing it was built from, the camera matching the drawing, params, LOW budget, verdict; `sheets/`: crop | HIGH | LOW | front / side / top). Eight of the twelve were NOT close enough on the first try and were reworked (each verdict says what changed). Next: the remaining presets of `prune_1`, the modifiers' own generators, a MEDIUM level, then retrofit the three models onto blocks.

**State.** Built and checked: Commando COM-2D, Javelin JVN-10N, Spider SDR-5V (three test models, Daniel reviewed the look: "much
finer detail" is what the other AI gets right). Not built: the other 31 (`units.json`, `"status": "not built"`). The tool, index,
unit-file check and test exist and need no change to start: `tools/lowpoly_ref.py` (`check`, `render [--iso]`, `mtf`),
`tests/test_lowpoly_ref.py`.

**Inputs per unit.** (1) The TRO drawing: `reference_art/originals/NN <Unit>.jpg`. (2) The turnaround sheet(s) Daniel got from other AIs (Gemini and Google), one or
two per unit for ALL 34, in `reference_art/ai_sheets/<Unit>/` (`gemini_1.*`, `batch2_<n>.*`; the source of each is not recorded). More sheets
from Daniel go in the same folder as `<source>_<n>.<ext>`. (3) The unit file's equipment, already in
`units.json` and enforced by `check`.

**How to build one unit (do them in batches of about five, in the order of `units.json`; show Daniel each batch):**
1. ZOOM. Crop the drawing into pieces (head, chest, each arm, pelvis, each leg) and look at each at full size before writing a
   part. The Javelin's two missile bays were missed at page size: a drum on the shoulder was read as a launcher.
2. Read the AI sheet for SHAPES only (a round dome chest, big fins, knee discs, claw feet); it is a hint, never the geometry.
3. Write `reference_art/models/<Unit>.json` (copy a built one). Put the unit file's weapons where the drawing shows them
   (`art_vs_unit_file` says what you decided where they disagree or the drawing is silent), jump jets where the drawing or the unit
   file's location says. Fill `features` in the vocabulary of `data/token_reference_tags.json`.
4. `python -I tools/lowpoly_ref.py check "<model>"`, then `render --iso`, then `compare "<model>"` (the drawing left, the model's 3/4
   panel right, in `reference_art/sheets/compare_<unit>.png`) and fix what is wrong.
5. Add the unit to `status` in `units.json` (change "not built" to "built"), run `tests/test_lowpoly_ref.py`, commit.

**What the AI sheets are and are not (Daniel, 2026-11-16, on seeing the full set: "unreliable for exact details; pretty good for the silhouette and for describing all the different ways you can render body parts"; his plan is the sheets plus the source drawings together).** Measured on his first three: Good: they find the shapes (the Spider's dome chest and
fins, the Commando's chest plate and heavy forearms). Bad: their five views often disagree (different pelvises, arms and
backs between views), they are far over the triangle budget, and one of three (the Javelin) was badly wrong. So: the sheet
suggests, the TRO drawing decides, the unit file fixes the equipment. When Daniel has several AIs' sheets for one unit, favour a
shape that two of them agree on.

**Daniel's rulings on the art (2026-11-16, in `reference_art/block_taxonomy.json`, `wtf`).** The round side disc is the SHOULDER; the Stalker's head is a fighter-style canopy on TOP of the torso (its AI sheet is fairly accurate except for extra weapon pods on the sides of the arms in the front and rear views: ignore those); the UrbanMech's head is the dome and its torso the cylinder below; Jenner and Cicada have small weapon pods for arms; the Quickdraw's wheels are ankle discs; the Hunchback's ribbed 'beer barrels' are its lower legs. Also: the Catapult is a bird leg (its claws are the three-toe foot); the Dragon's big barrel is a GUN ARM (the AI sheet's top-down view shows it). All the WTF items are answered. Per-unit AI-sheet faults (Victor's head turned away, Awesome's side views, Charger's floating figure, Stalker's extra pods, the Javelin) are in `units.json` under `ai_sheet_caveats`: read them before using a sheet.

**Known gaps in the three built models (the first thing to improve).** Legs and feet are plain tapered bars and boxes: the AI sheets
show knee discs, armored shins, clawed or three-toed feet and reverse-knee bird legs. The Javelin lacks the brow over the bays, the
hatched vents under them and the faceted belly band. The Commando's six-tube SRM 6 is a plain box (give it tube mouths as on the
Javelin). The stance is one A-stance for all (Daniel: "keep the same stance for now"), so a mid-stride drawing is straightened.

**Done when.** All 34 are `built`, `tests/test_lowpoly_ref.py` passes, Daniel has seen every sheet. A scripted check cannot judge
likeness (it checks the triangle budget, the required assemblies, feet on the ground and the unit file's weapons and jump-jet
locations): the likeness is Daniel's eye. NEXT STAGE (not this task): read the repeated shapes off the models into new blocks in
`data/token_blocks.json` and per-unit entries in the override list; Daniel wants these kept separate from the token generator until
then.

**Traps.** The renderer sorts faces by depth (fine for separate convex parts, may mis-order where parts interlock): look at the
picture, do not trust a clean `check`. A part carries one role (`weapon:<LOC>:<name>`): give only the housing the role and leave
its decorative tube mouths without one, or the weapon count is wrong. Tube parts take their cross-section axes from the way they
point (the module docstring says which). Do not put the TRO drawings or the models anywhere outside `reference_art/`.

## T15c. Every 'Mech the Catapult's way: the systematic pipeline (Opus; Daniel, 2026-11-18)

Daniel, after the HD Catapult: "What lessons were learned and how can they be applied to the rest of the project in a systematic
fashion?" Then: "Yep. Also implement item D." The principles (with their reasons) are `reference_art/blocks/ASSEMBLY_PRINCIPLES.md`
(21 of them); READ THEM FIRST.

**Lessons (short).** (1) Each source is authority for one thing: the record sheet for structure and placement (what an arm IS, where
weapons and jets go), the TRO drawing for shape, the AI five-view sheet for proportion and measurement, the sprite for the outline
from above. (2) Measure, don't guess: the Catapult came right only when measured from its five-view sheet. (3) Every shape is FOR
something: say what it houses or turns before adding it. (4) Design the joints first, as if it must articulate; the pivots come free.
(5) Machines catch what eyes skim: floating parts, lines of fire, the record sheet, the ground. (6) HD first, simplify later.
(7) Plausible beats perfect. (8) Review loop: five-view comparison -> Daniel's reasons -> a written principle the same day.

**The pipeline, per unit.**
1. RECORD-SHEET PLAN (automatic): `lowpoly_assemble.arm_plan` (arm structure from the actuators), weapon and jump-jet locations.
2. MEASURE (built 2026-11-18): `python -I tools/lowpoly_measure.py find "<unit>"` numbers the views on its AI sheet; put the front,
   side and top boxes in `reference_art/views.json`; `measure "<unit>"` writes `reference_art/measure/<unit>.json` + `.png`
   (crotch, shoulders, torso width, leg widths, feet; body length and leg reach from the side; plan ratio from the top; each view
   on its own scale). A person checks the landmark lines on the .png.
3. BUILD HD from blocks sized by the measurements (`tools/lowpoly_hd.py`, one builder per unit until the HD blocks of item B exist).
   Checks (automatic): one piece (no floating parts), every line of fire clear, feet on the ground, weapons and jets as the record
   sheet, jets near the centre of mass.
4. SELF-REVIEW against the principles' checklist BEFORE Daniel sees it: what does every round shape turn? joints built out? legs
   splay? cockpit wraps or cuts? turning roots inside their parents? every record-sheet weapon housed?
5. FIVE-VIEW COMPARISON to Daniel (the sheet's views beside the model's); every new principle into ASSEMBLY_PRINCIPLES.md the same day.
6. SIMPLIFY to the 800-triangle model from the HD one, with the outline check against it.

**B. HD blocks from the Catapult.** Turn its parts into library blocks with sockets, pivots, mounts and line-of-fire holes: the
torso tilt hinge, the waist (octagon tower + pyramid, ball root, cowl), ringed joint caps, the flared ankle housing, the weapon jowl,
the launcher arm, the wrapped cockpit (`conformal_glass`), flank jet vents. The Stalker, Jenner and Cicada start from them.

**C. Order: one per archetype**, each teaching what the next needs: a humanoid light (Commando), a humanoid assault (Atlas: its
views are already in views.json and measured), the Hunchback (torso gun, balance), the UrbanMech (turret). Expect 2-3 review rounds
each, not the Catapult's ten.
  Checked 2026-11-18 (Daniel: "Atlas is the unit with the next highest commonality with other units?"): by the block choices the
  assembler makes for the 34 units (`lowpoly_assemble.drawings_build`), the Commando and Catapult already cover 310 of the 496
  block uses; the unit that adds the most uses still uncovered is the Atlas (+58), then the Centurion (+44), the Hunchback (+23),
  the Whitworth (+18), the Spider (+10). The Atlas is NOT itself a common unit (29th of 34 for shared choices; the Trebuchet is
  1st), but it brings the most blocks the others still need. The UrbanMech (turret) is not in the top five.

**D. Keep the checks fast (DONE 2026-11-18).** The assembly check had grown to 4.5 minutes; profiling showed 90 % in the brute-force
convex hull (fourth power of the point count; a 200-point dome took 18 s). `lowpoly_ref._hull` now uses Qhull (identical vertices,
faces and triangle counts on random sets and the models; the brute force stays for degenerate sets), and the check runs the units
in parallel (one core left free): 4.5 min -> 21 s; the HD Catapult builds in 10 s. `tests/test_lowpoly_ref.py` times the check
against a 90 s budget and prints SLOW over it (profile before it grows).

