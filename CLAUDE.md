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
   **The engine is Rust (`engine/`).** The Python engine was removed on
   2026-11-20 (Daniel: "dead code the python"; it is in git history). Its
   answers live on as the frozen answer key, `engine/answer_key.tar.xz`
   (`tools/unpack_answer_key.py` -> `engine/fixtures/`), which the Rust
   tests compare against: exact match or not done.
   `INTEGRATION__RUST_PORT.md` is the translation's story and rules;
   `INTEGRATION__STATE.md` says what a battle's state is.
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
- **Rules come from the library, never from memory.** The library is the
  PRIVATE repo `logajam/battletech-rules-index` (its own CLAUDE.md has the
  pipeline): attach it with `add_repo` and clone it OUTSIDE this repo (e.g.
  `/home/user/battletech-rules-index`). The Core Rulebook is in
  `base/core-rules/*.md` (a `[p.N]` marker comes before page N's text;
  `summary/core-rules/*.yaml` is the fast read); it also holds TO: Advanced
  Units & Equipment and TO: Advanced Rules. Cite the page in the code. If the
  library doesn't settle a rule, look at how MegaMek does it (its source;
  Daniel, 2026-10-28), and ask Daniel only if that still leaves a question.
  Interstellar Operations isn't indexed yet: its TSEMP / iATM rules came from
  Daniel's pastes, and stats no paste or table gives come from MegaMek's
  source at Daniel's word (cite "MegaMek" in the code). NEVER put rulebook
  text in this repo (Daniel, 2026-11-13: it is to be publicly viewable):
  cite pages and describe rules in our own words. The old copy
  (`rules/Battletech_Rule_Reference_Index.zip`) was removed that day.
- **Logistics are Claude's** (Daniel: "You're in charge of the logistics").
  Work on the session branch, commit, push, open a PR to `main`, and merge it
  once every test passes. Daniel doesn't use GitHub, so tell him in plain words
  what changed.
- **Combat Lab art (visual assets only):** run only the art checks
  (`tests/test_token_shell.py`, `test_token_joined.py`, `test_token_volume.py`),
  not the whole suite (Daniel, 2026-11-04: "We're not messing with the core
  code, we're messing with visual assets ... Run only checks that are related").
  A change that touches engine code still runs the engine level below
  (`run_checks.py` picks the level by itself).
- **After every change:**
  - Run `python tests/run_checks.py`: it picks the checks from the files
    changed since origin/main (Daniel, 2026-11-17: "prune down the suite"):
    docs only -> nothing; art -> the three token tests; Lab pages
    (`engine/lab/web`, `engine/wasm/web`) -> the website checks
    (`check_web_ui.py`, `check_web_lab.py`) + `check_lab_server.py`; anything
    else (the engine) -> the Rust checks + the website + the Lab server. The Rust reference
    battles (91, `tests/check_rust_reference.py`; `--update` for a Rust
    change meant to alter results) and the MegaMek bridge's parity check
    (`tests/check_bridge_parity.py --quick`) run one after the other
    (`check_rust_reference.py --parity` does both in one run, every battle
    in full: thorough, but 2.5x slower). `--list` shows the choice and why. **Before a merge: `--full`**
    (every Rust and website check) **only if code changed**; a merge of docs, records or
    task write-ups alone runs nothing (Daniel, 2026-11-20: "only run the suite if the code
    changed"). All must pass. A new bot call (`BotSet`
    method) must be added to `bridge.rs` too, or the parity check misses it.
    Reference battles stop at the turn cap, 100 (the standard game since
    2026-11-12, `scenario::STANDARD_MAX_TURNS`); one that hits the cap prints a
    NOTE (Daniel: "a possible flaw").
  - Every trial battle is kept in `trial_records/` (`tools/trial_records.py`),
    written as each battle ends (`btsim --stream`): a crash is recorded with
    its seed and the set goes on, and re-running a stopped command plays only
    the missing battles. `tools/replay_undecided.py` replays only a trial's
    capped battles.
  - **Long sets survive a container restart (SOP, Daniel 2026-11-20).** Any set
    longer than a few minutes: run it through a tool that writes each battle
    the moment it ends (`btsim --stream` into `trial_records/progress/`, or a
    tool's own progress file there, e.g. `tools/fair_duels.py`) and resumes by
    re-running the SAME command. The plan of a set (which pairs, seeds,
    opponents) must come only from FINISHED records, never from a half-played
    run, or a resumed run picks different battles. Start it in the background
    with its log in the scratchpad. When a restart notice arrives: re-run the
    identical command at once, read its fresh "already recorded" count (not
    the old log) before saying anything, and tell Daniel what survived.
    `progress/` is git-ignored, so it lives through a restart but not a
    replaced container: commit the records file at every stage's end.
  - A reference log that differs: if the change was meant to alter results, run
    `python tests/check_rust_reference.py --update` and record that in the
    Change Record. A speed-only change must keep the results identical.
- **Bot changes:** compare settings on the same seeds with btsim
  (`--set KEY=VALUE`, `tools/round_robin.py`, `tools/hydra_trial.py`), and
  show Daniel the numbers. 20 battles a setting by default (Daniel); longer
  only if something looks very off, or to build a baseline during down time.
- **The bots:** each unit is driven by "gladiator" (this project's),
  "princess" (a MegaMek clone; the v0.50.07 clone is being removed, backlog
  N4), "hydra" or "caspar" (below) - `config.rs`, a unit's "bot", PROJECT_MAP
  Section 6. Legate (on by default) gives Gladiator the whole enemy force
  (PROJECT_MAP Section 6 "Legate"). Princess in a team battle: target by
  firing-plan utility with friends' damage counted, movement against every
  enemy, mutual support off the BV-weighted heat map; Battle Value is
  `battle_value.rs`. The old Python study tools (`ab_batches.py`,
  `baseline_battery.py`, `pick_quality.py`, `bot_agreement.py`,
  `legate_probe.py`) went with the Python engine. Daniel wants "general
  feel, not full stats": only the interesting series, few battles, unless he
  asks for a full run.
- **Four bots now:** "caspar" (Rust only, session 29, Daniel 2026-11-18) is MegaMek's CASPAR: the Princess clone with the Mutual Support
  movement ranker and zone deployment swapped in (`engine/core/src/caspar.rs`, `princess_modern::choose_as`; `btsim --caspar TEAM`; in
  the Lab / website team bot list). Anywhere that asks "is this Princess?" uses `Mech::is_princess_family`. Reviewed against MegaMek's
  source 2026-11-19 (Change Record) and merged; four reference battles play it (`caspar_*` in `check_rust_reference.py`). A/B: `tools/round_robin.py --bots princess,caspar`.
- **Three bots now:** "hydra" (Rust only, session 24) is Claude's own design: one planner per team, damage priced
  by a forecast of how the battle ends. COMPLETE (Daniel, 2026-11-12; reopened once, 2026-11-17, for the map edge); `INTEGRATION__HYDRA.md` is its plan and
  results (read before the code). Trials: `tools/hydra_scenarios.py`, `tools/hydra_trial.py`, `tools/round_robin.py`,
  `btsim --hydra TEAM`.
- **MegaMek bridge** (session 25; `INTEGRATION__MEGAMEK_BRIDGE.md`, `megamek_bridge/README.md`): our bots play as
  players in a live MegaMek game (MegaMek is never edited, Daniel). `tools/megamek_bridge_games.py SCENARIO.mms
  --megamek DIR --bridge Red` plays games and keeps records; `btsim decide` is the decision process.
- **Combat Lab** (session 25; `INTEGRATION__COMBAT_LAB_SPECS.md`): `engine/target/release/combatlab` starts the Lab (a
  local server, pages in `engine/lab/web`; `--no-browser --port N --web DIR`). `btsim --history N` writes replay pages from
  the Rust engine (use these to show Daniel battles now that the Python is retired). `tools/make_lab_demo.py` makes the
  pages into one demo page to publish for Daniel.
- **Low-poly reference models** (session 27, Daniel 2026-11-16): `reference_art/` (README there) holds the TRO 3025 drawings and
  low-poly models redrawn from them, the source for the Combat Lab's block dictionary and override list. PRIVATE (on
  `publish_public.py`'s `PRIVATE_PATHS`; redrawn images and models never go public). `tools/lowpoly_ref.py`, art checks only.
  The block library (T15a) is `tools/lowpoly_blocks.py` + `reference_art/blocks/`: every block names the exact drawing crop it
  came from and carries a verdict. The older token / shell art is on the back burner (Daniel, 2026-11-17). Whole 'Mechs:
  `tools/lowpoly_assemble.py` (every block on a bone socket or seated flush; one connected piece, checked; `viewer` = the 3D page).
  Daniel's assembly principles, WITH their reasons: `reference_art/blocks/ASSEMBLY_PRINCIPLES.md` (read first; add each new one).
  The per-unit pipeline (measure the five-view sheet with `tools/lowpoly_measure.py`, build HD, checks, five-view review): T15c.
  Before showing Daniel a model: `tools/lowpoly_checklist.py UNIT` (every correction he has made, as checks).
- **Movement searches:** Short Grid is the default; Daniel's IF/THEN
  (`MOVEMENT_SEARCH = "if_then"`) is an option meant for multi-unit threat
  estimates, not a single 'Mech's default (PROJECT_MAP Section 5).
- **Show Daniel battles as replays.** `btsim ... --history N`, then publish
  the page from `replays/` with the Artifact tool; give him the link (he
  doesn't run the code himself).
- **Optional rules** (where the rulebook offers a choice, or Daniel's rule
  differs from it) are switches in `engine/defaults/config.json` (their words
  in `engine/defaults/config_notes.json`; `tools/make_options_registry.py`
  puts them on the Lab's Options tab), with the rules-as-written version
  available.
- **Label work for review** (Daniel, 2026-10-28, standing order): at the end
  of every session, list what you built in PROJECT_MAP Section 0's REVIEW
  QUEUE and mark its Change Record entries "REVIEW PENDING (higher-level
  model)", so a stronger model can review it when there are spare cycles.
- **Keep going.** Don't pause at natural checkpoints. Stop only for a rules or
  scope call that is Daniel's.
- **Placeholders** are loud, counted stubs in `engine/core/src/stubs.rs`, never
  silent defaults. New bot decisions get a Section 6 row. A decision Daniel
  calls "research" (rate of fire, MASC, ammo kind...) is built as options
  plus a stub that picks.
- **Known issues** Daniel names go in PROJECT_MAP Section 4 ("Known issues to
  fix later").
- **Code style:** Daniel reads the code but doesn't write it. Keep it clean,
  explicit and commented to match the surrounding files, and sign changes in
  the Change Record.
- **Licence** (Daniel, 2026-11-13): the project is GNU GPL v3 or later (`LICENSE`, `CREDITS.md`). Credit borrowed work in
  `CREDITS.md` (MegaMek's data is CC BY-NC-SA 4.0: keep each file's header); never put rulebook text in the repo; after a
  change of Rust libraries run `python tools/third_party_licenses.py`. A download for anyone but Daniel needs its source
  with it (PROJECT_MAP E5).
- **Public copy** (Daniel, 2026-11-13): work happens HERE (private). `github.com/Logajam/battletech-combat-lab` is the
  public face, updated only with `python tools/publish_public.py --push` (it strips `rules/` and personal emails from all
  history and checks before pushing); never push to it by hand. Publish when Daniel asks (PROJECT_MAP E6).
- **File names:** the project's docs and the Combat Lab art modules keep the
  `INTEGRATION__` prefix; `mechsim/` now holds only the equipment tables the
  Rust engine reads (`equipment.json`, `equipment_bv.json`).
