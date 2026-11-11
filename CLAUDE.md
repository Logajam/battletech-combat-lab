# CLAUDE.md

BattleTech Monte Carlo simulator: two mechs (`.mtf`) fight on a hex board under
the Core Rulebook, many times over, and the results are summarized. Daniel owns
the BattleTech rules and scope calls; Claude owns the implementation and the
GitHub logistics.

## Start here

1. Read `INTEGRATION__PROJECT_MAP.md` **Section 0** ("read this first"): what's
   built, how to run and test, the backlog of open work and the REVIEW QUEUE.
   Keep it short: finished work goes to the Change Record, not into Section 0.
2. Section 7 of the same file holds Daniel's standing instructions. Section 5
   holds his decisions (implementation may not override them). Section 6 lists
   every bot decision point and the future-capability Memo.
   `INTEGRATION__CHANGE_RECORD.md` is the Change Record, newest first (new
   entries at the top). `INTEGRATION__HISTORY.md` is the session history and
   the old "Pick up here" list, word for word (code comments that cite "Pick
   up here N" mean that list). `INTEGRATION__TASK_SPECS.md` holds task
   write-ups and which model each suits.
   **Working on the Rust translation?** `INTEGRATION__RUST_PORT.md` is the
   plan and its rules (the Python is the answer key and is frozen; exact
   match or not done); `INTEGRATION__STATE.md` says what a battle's state is.
3. `INTEGRATION__RULES_REVIEW.md` is the Core Rulebook vs code review: fixed
   items, the gap list to build, and open questions for Daniel.
4. `INTEGRATION__CALL_GRAPH.md` shows the import structure, and `README.md` the
   layout and test commands. `INTEGRATION__BOTS.md` explains how Gladiator and
   Princess decide, and what the latest battery says.

## Working rules (details in PROJECT_MAP Section 7)

- **The rulebook beats house rules** (Daniel, 2026-10-21: "Follow the rules,
  not my calls"): where the Core Rulebook answers it and an earlier call of
  Daniel's differs, follow the book and say so. Exception: switches kept for
  speed, like `FIGHT_TO_THE_DEATH` off ("it saves time when the situation is
  hopeless").
- **Rules come from the library, never from memory.** Use
  `rules/Battletech_Rule_Reference_Index.zip`, unzipped OUTSIDE the repo. The
  Core Rulebook is in `base/core-rules/*.md`, and a `[p.N]` marker comes before
  page N's text. Cite the page in the code. If the library doesn't settle a
  rule, look at how MegaMek does it (its source; Daniel, 2026-10-28), and ask
  Daniel only if that still leaves a question. The zip is a snapshot of the private repo
  `logajam/battletech-rules-index` (its own CLAUDE.md has the pipeline);
  that repo also holds TO: Advanced Units & Equipment and TO: Advanced Rules
  (2026-10), which the zip predates (session 10 read them from a clone of
  that repo). Interstellar Operations isn't indexed yet: its TSEMP / iATM
  rules came from Daniel's pastes, and stats no paste or table gives come
  from MegaMek's source at Daniel's word (cite "MegaMek" in the code).
  Attach it with `add_repo` when a rule needs a newer book,
  and refresh the zip when Daniel wants that book used here.
- **Logistics are Claude's** (Daniel: "You're in charge of the logistics").
  Work on the session branch, commit, push, open a PR to `main`, and merge it
  once every test passes. Daniel doesn't use GitHub, so tell him in plain words
  what changed.
- **Combat Lab art (visual assets only):** run only the art checks
  (`tests/test_token_shell.py`, `test_token_joined.py`, `test_token_volume.py`),
  not the whole suite (Daniel, 2026-11-04: "We're not messing with the core
  code, we're messing with visual assets ... Run only checks that are related").
  A change that touches engine code still runs everything below.
- **After every change:**
  - Run `python tests/run_checks.py` (about 1 min): every `tests/test_*.py`
    plus every reference battle, side by side, one line each. All must pass.
    Reference battles stop at 50 turns; one that hits the cap prints a NOTE
    (Daniel: "a possible flaw").
  - A reference log that differs: if the change was meant to alter results, run
    `python tests/check_reference_logs.py --update` and record that in the
    Change Record.
  - Add `--bench` (the 10-turn benchmark) for anything on the hot path. A
    speed-only change must keep the results identical. It prints where the time
    went (`INTEGRATION__timing`), as every batch does.
- **Bot changes:** compare settings on the same seeds with
  `python tests/ab_batches.py`, and show Daniel the numbers. 20 battles a
  setting by default (Daniel); longer only if something looks very off, or
  to build a baseline during down time.
- **Two bots:** each unit is driven by "gladiator" (this project's) or
  "princess" (a MegaMek clone, modern or v0.50.07) - `INTEGRATION__bots`,
  `config.BOT` / `MECH_*_CONFIG["bot"]`, PROJECT_MAP Section 6 "Princess
  clone". Bot-vs-bot studies: `ab_batches.py --set bots`,
  `tests/pick_quality.py` (`--pickers`, `--perfect-cache`),
  `tests/bot_agreement.py`; `tests/legate_probe.py` (+ `_report`) measures Legate's estimate,
  predicted v actual damage, regret, cohesion and calibration in a battery. Legate (`config.LEGATE`, on by default;
  `INTEGRATION__legate`) gives Gladiator the whole enemy force: a
  start-of-phase IF/THEN estimate, a threat-ordered foe, the other enemies'
  damage in the move score (PROJECT_MAP Section 6 "Legate"). A battery split
  over cores: `python tests/baseline_battery.py pg 20 [--legate] --first 1
  --last 5`, four of them side by side. Princess in a team battle: target by
  firing-plan utility with friends' damage counted, movement against every enemy, mutual
  support off the BV-weighted heat map (`config.PRINCESS_GROUP`,
  `INTEGRATION__princess_group` / `_memory`; Battle Value is
  `INTEGRATION__battle_value`). Daniel wants "general feel, not full stats":
  only the interesting series, few battles, unless he asks for a full run.
- **Three bots now:** "hydra" (Rust only, session 24) is Claude's own design: one planner per team, damage priced
  by a forecast of how the battle ends. `INTEGRATION__HYDRA.md` is its plan (read before the code), with results
  and the next stage (play-outs). Trials: `tools/hydra_scenarios.py`, `tools/hydra_trial.py`, `btsim --hydra TEAM`.
- **Movement searches:** Short Grid is the default; Daniel's IF/THEN
  (`MOVEMENT_SEARCH = "if_then"`) is an option meant for multi-unit threat
  estimates, not a single 'Mech's default (PROJECT_MAP Section 5).
- **Show Daniel battles as replays.** Set `REPLAY_BATTLES` in
  `INTEGRATION__config.py`, run, and publish the page from `replays/` with the
  Artifact tool; give him the link (he doesn't run the code himself).
- **Optional rules** (where the rulebook offers a choice, or Daniel's rule
  differs from it) are switches in `INTEGRATION__config.py`'s OPTIONAL RULES
  section, with the rules-as-written version available.
- **Label work for review** (Daniel, 2026-10-28, standing order): at the end
  of every session, list what you built in PROJECT_MAP Section 0's REVIEW
  QUEUE and mark its Change Record entries "REVIEW PENDING (higher-level
  model)", so a stronger model can review it when there are spare cycles.
- **Keep going.** Don't pause at natural checkpoints. Stop only for a rules or
  scope call that is Daniel's.
- **Placeholders** are loud, counted stubs in `INTEGRATION__stubs.py`, never
  silent defaults. New bot decisions get a Section 6 row. A decision Daniel
  calls "research" (rate of fire, MASC, ammo kind...) is built as options
  plus a stub that picks.
- **Known issues** Daniel names go in PROJECT_MAP Section 4 ("Known issues to
  fix later").
- **Code style:** Daniel reads the code but doesn't write it. Keep it clean,
  explicit and commented to match the surrounding files, and sign changes in
  the Change Record.
- **File names:** keep the `INTEGRATION__` / `mechsim/` / `pathfinder/` split.
