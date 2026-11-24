# BattleTech Monte Carlo Simulator

Headless batch simulator: two mechs (`.mtf` files) fight on a hex board,
turn by turn, many times over, and the results are summarized. Any number of
mechs on any number of teams can fight too (a lance against a lance, a company,
a free for all, a three-way battle): set them up in the Combat Lab, or in a settings file for `btsim`.

**Status: alpha.** An early, unfinished version: expect bugs, and treat results as work in progress.
**Try Combat Lab in your browser** (your own computer plays the battles; nothing is sent anywhere):
https://logajam.github.io/battletech-combat-lab/ . Bugs and ideas: the issue page of this repository, or the
"Suggestion / bug report" button inside Combat Lab.

## Run it

The engine is Rust (`engine/`; needs a Rust toolchain):

```
cd engine && cargo build --release
engine/target/release/combatlab                       # the Combat Lab: set up teams, run batches, watch battles
engine/target/release/btsim --setup SETTINGS.json --battles 100   # a batch from the command line
```

Settings and their defaults: `engine/defaults/config.json` (what each one does: `engine/defaults/config_notes.json`, also
shown on the Lab's Options tab). The original Python engine was retired in November 2026 and removed on 2026-11-20 (it is
in this repository's history); its recorded answers are kept as the frozen answer key (`engine/answer_key.tar.xz`), now only input (units, boards, settings) for a few tests, no longer the standard: the engine's guard is the reference list (`engine/reference/battles.txt`).

## Layout

| Path | What's there |
|---|---|
| `mechsim/` | The equipment tables the engine reads (`equipment.json`, `equipment_bv.json`) |
| `data/` | `.board` maps (16x17 Grassland, 50x50 BigBlank) and `.mtf` mechs (test mechs, plus real units from `meks.zip` for the AMS / Artemis / Narc / ECM / weapon-use reference battles) |
| `data/maps.zip` | Daniel's MegaMek map pack (346 `.board` maps, 192 of them 16x17). |
| `data/meks.zip` | 4,227 MegaMek `.mtf` units by source book (4,204 load - ultralights and superheavies since 2026-10-28; the 23 LAMs don't). Pick any of them in the Combat Lab |
| (rules) | The page cites in the code refer to the BattleTech rulebooks (Catalyst Game Labs). Their text is not in this repository: the project reads them from a separate private rules library |
| `engine/` | The Rust engine (sessions 22-25): `btsim` plays batches of a scenario folder (`engine/target/release/btsim SCENARIO_DIR --battles N`, or `--setup SETTINGS.json` to build the scenario in Rust from settings; `--hydra TEAM`, `--caspar TEAM`, `--set KEY=VALUE`, `--max-turns`, `--stream FILE`) . Four bots: Gladiator (this project's), Princess (a MegaMek clone); Hydra, the third bot, is Rust only (`INTEGRATION__HYDRA.md`); so is CASPAR, the fourth (MegaMek's Mutual Support bot, `engine/core/src/caspar.rs`, `INTEGRATION__BOTS.md` "CASPAR"). Its own reference battles: `engine/reference/` (`python tests/check_rust_reference.py`). MegaMek bridge (`INTEGRATION__MEGAMEK_BRIDGE.md`): `btsim decide`, the bots deciding from snapshots of a game, checked by `python tests/check_bridge_parity.py`. `--history N` writes battles 1..N as replay pages (`replays/`). `--events` records each battle's events (`INTEGRATION__EVENTS.md`), searched with `tools/search_events.py` or the replay page's Search events panel |
| `engine/lab/` | Combat Lab (`INTEGRATION__COMBAT_LAB_SPECS.md` CL3-CL5): `engine/target/release/combatlab` starts a local server and opens the Lab in the browser - set up teams from every unit in `data/` and `data/meks.zip`, pick a board, run a batch, read the results, watch any battle. Checked by `python tests/check_lab_server.py` |
| `engine/wasm/` | Combat Lab in the browser (`INTEGRATION__COMBAT_LAB_WEB.md`): the engine as WebAssembly, played by Web Workers on the visitor's own computer. `python tools/build_web_lab.py` makes the static site `web_lab/`; checked by `python tests/check_web_lab.py` (needs node + Playwright) |
| `trial_records/` | Every bot-trial battle (`tools/hydra_trial.py`, `tools/round_robin.py`): one JSON line per batch with each battle's seed and result, written as the battles end (`tools/trial_records.py`; `tools/replay_undecided.py` plays the capped ones on) |
| `LICENSE`, `CREDITS.md` | The project's licence (GNU GPL v3 or later) and its credits: Daniel and Claude, the MegaMek Team (units and boards under CC BY-NC-SA 4.0, `licenses/`), BattleTech's owners. `THIRD_PARTY_LICENSES.txt`: the Rust libraries' licences (`tools/third_party_licenses.py`) |
| `tools/` | Helpers that drive the engine (trials: `hydra_trial.py`, `round_robin.py`, `fair_duels.py`; `hydra_scenarios.py`; `make_options_registry.py`; `unpack_answer_key.py`; `build_web_lab.py`...) and the Combat Lab art (`token_sheet.py`, `token_3d.py`, `token_audit.py`, the low-poly `lowpoly_*.py`; the art modules are `INTEGRATION__tokens.py` / `_shell*.py` / `_token_mesh.py` / `_structure_table.py`; need `pip install scipy trimesh python-fcl`) |
| `tests/` | `run_checks.py` (the checks a change needs, in one command), `check_rust_reference.py` (the engine's reference battles), `check_bridge_parity.py` (the MegaMek bridge), `check_events.py` (the event records and their search), `check_bv_megamek.py` (Battle Value v MegaMek), `check_lab_server.py`, `check_web_ui.py`, `check_web_lab.py` (the Lab and the website), and the art tests (`test_token_*.py`, `test_lowpoly_ref.py`) |

After a change, from the repo root: `python tests/run_checks.py` (it picks the checks from what changed; `--full` runs them
all, `--list` says what it would run).

Anything not yet a real rule is a loud **stub**: it prints `STUB: ...` to
stderr and appears in the summary banner.

New to the project (or a new Claude session)? Start with `CLAUDE.md`, then Section 0 of `INTEGRATION__PROJECT_MAP.md`.

Project status, open items and decisions: `INTEGRATION__PROJECT_MAP.md`. Every change, newest first: `INTEGRATION__CHANGE_RECORD.md`. Session history: `INTEGRATION__HISTORY.md`. Task write-ups for later sessions: `INTEGRATION__TASK_SPECS.md`.
Core Rulebook vs code (fixed, gaps, questions for Daniel): `INTEGRATION__RULES_REVIEW.md`.
