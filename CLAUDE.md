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
    (`check_web_ui.py`, `check_web_lab.py`) + `check_lab_server.py`; the
    Python -> its tests and 15 reference battles; anything else (the engine)
    -> the Rust checks + the website + the Lab server. The Rust reference
    battles (86, `tests/check_rust_reference.py`; `--update` for a Rust
    change meant to alter results) and the MegaMek bridge's parity check
    (`tests/check_bridge_parity.py --quick`) run one after the other
    (`check_rust_reference.py --parity` does both in one run, every battle
    in full: thorough, but 2.5x slower). `--list` shows the choice and why. **Before a merge: always
    `--full`** (every Rust and website check). The retired Python runs only
    when a Python file changed or with `--python`: run that once a week (the
    first session of the week). All must pass. A new bot call (`BotSet`
    method) must be added to `bridge.rs` too, or the parity check misses it.
    Reference battles stop at the turn cap: 50 in the Python, 100 in the Rust
    (the standard game since 2026-11-12, `scenario::STANDARD_MAX_TURNS`); one
    that hits the cap prints a NOTE (Daniel: "a possible flaw").
  - Every trial battle is kept in `trial_records/` (`tools/trial_records.py`),
    written as each battle ends (`btsim --stream`): a crash is recorded with
    its seed and the set goes on, and re-running a stopped command plays only
    the missing battles. `tools/replay_undecided.py` replays only a trial's
    capped battles.
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
  came from and carries a verdict. The older token / shell art is on the back burner (Daniel, 2026-11-17).
- **Movement searches:** Short Grid is the default; Daniel's IF/THEN
  (`MOVEMENT_SEARCH = "if_then"`) is an option meant for multi-unit threat
  estimates, not a single 'Mech's default (PROJECT_MAP Section 5).
- **Show Daniel battles as replays.** `btsim ... --history N` (Rust; or
  `REPLAY_BATTLES` in `INTEGRATION__config.py` for the Python), then publish
  the page from `replays/` with the Artifact tool; give him the link (he
  doesn't run the code himself).
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
- **Licence** (Daniel, 2026-11-13): the project is GNU GPL v3 or later (`LICENSE`, `CREDITS.md`). Credit borrowed work in
  `CREDITS.md` (MegaMek's data is CC BY-NC-SA 4.0: keep each file's header); never put rulebook text in the repo; after a
  change of Rust libraries run `python tools/third_party_licenses.py`. A download for anyone but Daniel needs its source
  with it (PROJECT_MAP E5).
- **Public copy** (Daniel, 2026-11-13): work happens HERE (private). `github.com/Logajam/battletech-combat-lab` is the
  public face, updated only with `python tools/publish_public.py --push` (it strips `rules/` and personal emails from all
  history and checks before pushing); never push to it by hand. Publish when Daniel asks (PROJECT_MAP E6).
- **File names:** keep the `INTEGRATION__` / `mechsim/` / `pathfinder/` split.
