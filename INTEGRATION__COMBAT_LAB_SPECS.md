# Combat Lab: spec sheets (written 2026-11-11, session 24; nothing here is built)

Daniel, 2026-11-11: "write spec sheets for future you to follow to improve that side of the project."
What Daniel wants from the Lab is in `INTEGRATION__COMBAT_LAB.md` Part B (his functional spec) and
Part A (his wish list). This file turns Part B into jobs that can be picked up one at a time.

**What changed since Part B was written:** the engine is now the Rust one (`engine/`), the Python is
retired (Daniel, 2026-11-11), and there is a third bot (`INTEGRATION__HYDRA.md`). Part B's "Claude's
notes" assumed a Python `lab` module. Read those notes for the decisions (HTML front end behind
`CombatLab.exe`, JSON between GUI and engine, GUI separate from the simulation), and this file for
the build order.

Each sheet says: the job, why it comes where it does, what already exists, what to build (as blocks
and connections), how to know it is done, and the traps. "CHECK FIRST" marks something the writer
did not verify; look before relying on it.

## The order, and why

```
 CL1 scenario from files (Rust) ----+
                                    +--> CL3 Lab server --> CL4 setup + results pages --> CL5 replay page
 CL2 battle history (Rust) ---------+                                                        |
                                                                                             v
                                         CL6 battle from a saved state --> CL7 analysis overlays --> CL8 branching
```

CL1 and CL2 are the foundation: without them the Lab still needs the retired Python to start a battle
and to record one. CL6 is shared with Hydra's dice play-out (`INTEGRATION__HYDRA.md` Section 6, S5b:
SNAPSHOT and TURN CURSOR): build it once, for both.

| Sheet | Job | Suits | Size |
|---|---|---|---|
| CL1 | A battle set up from unit and board files, in Rust - DONE (session 25) | Sonnet | medium |
| CL2 | The battle's full history written by the Rust engine - DONE (session 25) | Sonnet | small |
| CL3 | The Lab server: one program, JSON in and out - DONE (session 25) | Sonnet | medium |
| CL4 | Setup and Results pages - DONE (session 25) | Sonnet | medium |
| CL5 | Replay page over the history - DONE (session 25) | Sonnet | medium |
| CL6 | A battle restarted from a saved state | Opus or higher | large |
| CL7 | Analysis overlays | Opus (design per overlay), Sonnet (drawing) | medium each |
| CL8 | Branching | Opus | medium, after CL6 |
| CL10 | Connect to MegaMek: play Combat Lab's bots in a MegaMek game (the bridge's B7) | Opus | large, after CL4 |
| CL9 | Art: the weapon-block stockpile | whoever Daniel reviews art with | open-ended |

---

**Since the sheets were written (session 25):** CL1 is done (`btsim --setup`). The MegaMek bridge built pieces CL6 needs:
`engine/core/src/bridge.rs` keeps a battle alive from snapshots and asks the bots for any decision at any moment (a
`Session`), with the COMPACT unit state (`UNIT_FIELDS` / `ITEM_FIELDS`, proven complete) - what a saved state of a unit
must hold. Daniel, 2026-11-12: the bridge is shelved; next is "something I can interact with as a normal person who
does not code" - CL2 to CL5.

**CL2-CL5 as built (session 25, 2026-11-12).**
- CL2: `engine/core/src/history.rs` writes the Python replay viewer's own record (option (a) of CL5: the viewer's format is
  a small subset of the full state, so the history IS the viewer's data; 0.5-0.8 MB a 4 v 4 battle, 2.5 MB a 12 v 12, no
  packing needed). `btsim --history N [--history-dir DIR] [--history-json]`; `Scenario::run_history`. Checked against the
  Python's own replay record of every fixture battle (63, 12 v 12s included): `engine/core/tests/cl2_history.rs`, answer key
  `python tools/port_record.py --replay-data FIXTURE` (port_fixtures.py writes it). Results with and without history equal;
  the same seed gives a byte-identical file. Bare prints (VERBOSE's crit-pool lines) stay out, as in the Python (`Log::printed`).
- CL3: `engine/lab` (binary `combatlab`): standard library HTTP on 127.0.0.1 (port 8765 up, or `--port`), the pages built
  in (`--web DIR` to serve them from disk), requests `info`, `list_units` (every unit of data/ and data/meks.zip parsed once,
  with Battle Value; 4,252, 0.5 s; cached in `lab_cache/`), `list_boards` (data/ and data/maps.zip, 356), `estimate`, `run`,
  `progress`, `results`, `cancel`, `history`, `add_unit`; `GET /replay?run=R&sim=S`. Packed units / boards are unpacked to the
  same path under data/ when first used (git-ignored). One crate added: `zip` (deflate only, pure Rust). Check:
  `tests/check_lab_server.py` (a 2 v 2 through the server equals btsim's battles for the same setup and seed; in run_checks).
- CL4: `engine/lab/web` (index.html, lab.css, lab.js), the Windows 3.x look. Units: 2-6 team panels (name, colour, bot,
  units with skills, search over the whole unit list, drop or pick a .mtf file = copied into data/), number of simulations,
  Estimate, Run Simulation. Map: search, size filter, random map. Options: threads, seed, turn cap. Results: progress and
  Cancel, win bar, per-team and overall statistics, battle list. Demo for Daniel: `tools/make_lab_demo.py OUT.html` (the
  pages with answers recorded from a real run).
- CL5: the Replay tab shows the viewer page (`/replay`), by battle or by seed (the current setup on that seed). 12 v 12:
  about 10 ms a step in the browser, no lag.
- NOT YET: a Windows `CombatLab.exe` package (the program finds the project folder from BTSIM_ROOT or three folders above
  itself); stats the engine does not total yet (average heat); debug output options; team colours are not passed to the viewer.

## CL10. Connect to MegaMek (Daniel, 2026-11-12; after CL4)

Combat Lab's bots in a MegaMek game Daniel hosts, his forces set up in MegaMek, Combat Lab's in Combat Lab. A page that
looks like MegaMek's own connect / lobby section - Daniel: possibly drawn as that part of MegaMek's start screen "being
bolted and taped on" - with host and port (internet connections as MegaMek allows). The engine side is the shelved
MegaMek bridge, B7a-B7d in `INTEGRATION__MEGAMEK_BRIDGE.md` Section 8b (Daniel's corrections and wishes there).

## CL1. A battle set up from unit and board files, in Rust

**DONE 2026-11-12 (session 25; built for the MegaMek bridge's start too).** `Scenario::from_settings` (engine/core/src/
scenario.rs): a SETTINGS file (a JSON object of the settings that differ from the defaults, under the Python's names) ->
the scenario. DEFAULTS: `engine/defaults/config.json`, the Python's settings dumped as the fixtures were (`STATS`,
`TIMING` off, `MAX_TURNS` 50 as the recorder set them; it equals every fixture's config.json but for the keys the fixture
overrode). ROSTER BUILDER: `setup::roster` (moved from the attach test, which already proved it). `btsim --setup FILE
[--write-scenario DIR]`. Check: `engine/core/tests/cl1_setup.rs` - every fixture built from its own differing settings
gives its units.json and board.json exactly (roster order included; key order inside an object is not compared, fields
are read by name); in `tests/run_checks.py`. A 200-battle batch from a settings file ran with no Python. NOT done:
maps packed in data/maps.zip (unpack first; the Rust has no zip reader), the map prompt and random board choice
(Python-only, interactive). Deployment needs nothing here: the battle deploys on its own dice, as before.

**Job.** Given a list of teams (each: unit files, bot, count), a board file and the settings, build
the starting battle in Rust. Today the starting battle is built by the Python and handed to Rust as
JSON (`tools/port_scenario.py` writes `config.json`, `units.json`, `board.json`).

**Exists.** `engine/core/src/mtf_parser.rs` (`parse_mtf`), `board_parser.rs` (`parse_board_file`,
`stitch_boards`), `setup.rs` (`attach_mech_config`), `deployment.rs` (start hexes), and
`scenario.rs` (`Scenario::load` from the three JSON files). The stage 1-3 tests already prove the
parsers match the Python on every data file.

**Build.**
- SETUP FILE: one JSON file a person or the GUI can write: teams, units, bots, board, seed, number
  of battles, and any settings that differ from the defaults.
- DEFAULTS: the settings the Python kept in `INTEGRATION__config.py`, as a file the Rust reads
  (CHECK FIRST: whether a full `config.json` from any fixture can serve as the defaults file as is).
- ROSTER BUILDER: setup file -> units (parse each unit file, attach its team / bot / skills, name it
  "Red 1", "Blue 2" as the Python does).
- `Scenario::from_setup(file)` beside `Scenario::load(dir)`; `btsim` accepts either.

**Done when.** For every fixture that has `overrides.json`, the scenario built by Rust from the same
choices equals the Python-built one: `units.json` and `board.json` identical. Then one batch run from
a setup file with no Python on the machine.

**Traps.** Unit naming and order decide dice order (a different roster order is a different battle).
Random-board and board-stitching choices draw from the seed: copy the order of draws exactly
(CHECK FIRST: where the Python picks a random board and start hexes, `INTEGRATION__map_picker` and
the deployment code). Pilot skills and per-unit config overrides (`MECH_*_CONFIG`).

## CL2. The battle's full history written by the Rust engine

**Job.** The Rust engine writes, for a chosen battle, everything the replay page needs: the state of
every unit after every step, and the log lines of that step.

**Exists.** The turn loop already calls a hook at every step (`Marks` in
`engine/core/src/orchestrator.rs`: "Red 1 moves", "Ranged attacks", "Physical attacks", "Heat and end
phase"). `Mech::to_json` (`mech_json.rs`) writes a unit's whole state. The fixtures' `trace.jsonl` is
this same record made by the Python, and the stage 6 test compares against it, so the format is
proven. `btsim --log N` already keeps the log text of the first N battles.

**Build.**
- HISTORY WRITER: a `Marks` hook that appends {turn, step label, every unit's state, log lines since
  the last step} to a list.
- `btsim --history N` (or by seed): write that list for the chosen battles, one file each.
- A battle is identified by (setup, seed): the same pair must always give the same history, so a
  history can be re-made on demand instead of stored. Store only the seed in the results list.

**Done when.** For three fixtures, the Rust-written history equals the fixture's `trace.jsonl`
states step for step. A second run of the same seed gives a byte-identical file.

**Traps.** Recording must change nothing: the battle with and without `--history` must draw the
same dice (check `dice_used` equal). Size: a 12 v 12 writes 24 units a step; write compactly or only
what changed since the last step (decide after measuring one).

## CL3. The Lab server: one program, JSON in and out

**Job.** One program the GUI talks to. Daniel's decision (2026-10-31): `CombatLab.exe` starts a
local server and opens the browser; works offline.

**Build.** A third crate in `engine/` (`lab`), using `btsim_core`. It serves the page files and
answers these requests (all JSON, coarse on purpose so the GUI never needs engine detail):
- `list_units`, `list_boards`: what is in the project folder (name, tonnage, Battle Value).
- `estimate(setup)`: seconds for the batch, from a few pilot battles scaled by battles / threads.
- `run(setup)`: starts a batch; `progress`: battles done; `results`: the statistics and the battle
  list (number, seed, winner, turns, duration).
- `history(seed)`: CL2's record for one battle.
- later: `analyze` (CL7), `branch` (CL8).

**Done when.** A script (no browser) sets up a 2 v 2, runs 20 battles, reads the results, asks for
battle 3's history, and gets the same numbers `btsim` gives for the same setup and seed.

**Traps.** Windows is the target (`CombatLab.exe`): no Unix-only calls; choose a free port; a batch
must be cancellable and must not block the server (run it on its own threads). Keep the server to
the standard library plus one small HTTP crate (CHECK FIRST: what the build environment's package
access allows). Nothing leaves the machine: bind to localhost only.

## CL4. Setup and Results pages

**Job.** Part B's Units, Map, Options and Results tabs.

**Build.** Plain HTML and script, no framework, the "Windows 3.x" look Daniel asked for. Units tab:
team panels (colour, bot: gladiator / princess / hydra, unit list), number of teams, number of
simulations, estimated runtime, Run Simulation. Map tab: board, size, seed. Options tab: threads,
keep logs, seed. Results tab: totals and the battle list; choosing a battle opens Replay.

**Done when.** Daniel can see it: publish the page as an Artifact with canned server answers
(CLAUDE.md: he does not run the code himself). Then against the real server: the script test of
CL3 done by hand through the pages.

**Traps.** Drag-and-drop of a unit file must copy it into the project's Mech folder (Part B). The
unit search needs the unit list fast: build the index once at server start. Three or more teams:
the engine supports it; the page must not assume Red and Blue.

## CL5. Replay page over the history

**Job.** Part B's Replay tab: top-down board, timeline, turn and phase controls, selected-unit
panel.

**Exists.** `INTEGRATION__replay_viewer.html` already does this for the Python's recording: a
self-contained page with the battle's data in a `replay-data` block. `INTEGRATION__replay.py`
shows what that data holds.

**Build.** Reuse the viewer. Either (a) have CL2 write the viewer's own format, or (b) a small
adapter in the page from CL2's history to what the viewer draws. Prefer (a) if the viewer's format
is a subset of the full state (CHECK FIRST: compare one `replays/` page's data with a
`trace.jsonl` line). Add "load by seed".

**Done when.** One battle recorded by the Python viewer path and the same battle from the Rust
history look the same step for step (publish both to Daniel as Artifacts). Works at 12 v 12
without lag (the Python viewer was built for two units: CHECK FIRST).

## CL6. A battle restarted from a saved state (shared with Hydra S5b)

**Job.** Take any step of a history and make a live battle from it that can be played on. This is
the foundation of Analysis (CL7), Branching (CL8) and Hydra's dice play-outs.

**Exists.** `Mech::from_json` rebuilds a unit from its saved state (the stage 6 test uses it).
What cannot be restarted today: the place in the turn (the turn loop keeps it in local variables),
the dice, and the bots' memories (Legate, Princess, Hydra).

**Build.** Exactly the two blocks specified in `INTEGRATION__HYDRA.md` Section 6, S5b:
- SNAPSHOT: everything that carries forward, copyable and saveable: units, smoke, broken crust,
  limbs on the ground, turn number, the bots' memories, the dice state.
- TURN CURSOR: where in the turn the battle is; one function advances a battle from a cursor to a
  stopping point, and the normal battle runs through the same function.
`INTEGRATION__STATE.md` lists what a battle's state is; use it as the checklist.

**Done when.** (1) Every fixture still matches exactly with the turn run through the cursor.
(2) Round trip: play a battle to step N, save, restore into a fresh battle, play on: the rest of the
battle (log, dice, result) is identical to the unbroken one. Do this at every step kind
(mid-movement, after fire, after heat) on three fixtures including a team battle.

**Traps.** Anything forgotten in the snapshot shows up as a late, hard-to-find difference: that is
why the round-trip test must compare the whole rest of the battle. The speed caches
(`los_memo`, `table_memo`) are not state: rebuild them empty.

## CL7. Analysis overlays

**Job.** Part B's "Replay analysis": at any recorded step, the engine shows what a bot sees (threat
maps, damage maps, movement scores, weapon evaluations, enemy predictions), computed on demand
from the state, for any bot, with no GUI change per bot.

**Build.**
- One request: `analyze(seed, step, unit, bot, what)` -> a map (a number per hex) or a table, plus a
  short text. Needs CL6 (a live battle at that step).
- Each bot exposes what it already computes. First overlays, cheapest first:
  1. Hydra: the price of every unit (a table), and for the selected unit the Mover's gain, cost and
     score per hex (`hydra.rs` already has all three per spot).
  2. Gladiator: the move score per hex and the modeled reply (the notes it logs today).
  3. Any bot: the Exchange Oracle's "damage I deal / take from here" per hex against one enemy.
- The page draws any map the same way (a colour ramp over hexes, the value on hover).

**Done when.** For one fixture step, the hex the overlay marks best is the hex the bot actually
chose at that step in the recorded battle (for each bot that has an overlay).

**Traps.** Analysis must not change the battle or draw its dice. Each new bot-facing hook gets a
PROJECT_MAP Section 6 row (CLAUDE.md placeholder rule).

## CL8. Branching

**Job.** Part B: at any replay step, Create Branch: change movement, facing, weapons, heat,
terrain, initiative or status, then continue the simulation. The original replay stays unchanged.

**Build.** On CL6: restore the step into a new battle, apply the edits, give it its own seed, play
on, return a new history. Edits go through the same legality checks as a bot's move (Part B notes,
item 8). A branch made mid-phase resumes at that phase's start (item 7).

**Done when.** A branch with no edits and the original's dice state reproduces the original from
that step. A branch with one edit (a unit moved to another legal hex) plays to the end without a
panic, on three fixtures.

**Open for Daniel.** Which edits come first; whether a human may pick every move of one side (a
"human bot"), which this makes nearly free.

## CL9. Art: the weapon-block stockpile

Spec sheets for the art (why the models read as stacked blocks, and jobs A1-A8): `INTEGRATION__COMBAT_LAB_ART_SPECS.md`.
The rest of this section is the pointer written before those existed. The art has its own spec and status: `INTEGRATION__COMBAT_LAB_SKELETON.md`
(Section 10: "Next on the 3D side (Daniel, 2026-11-06): a stockpile of weapon blocks. Phase 2 (the
47 chart chassis) waits until the block dictionary is built up") and PROJECT_MAP Section 0 item E3.
The art code is Python (`INTEGRATION__tokens.py`, `_shell*.py`, `tools/token_*`) and is not part of
the Rust move: it only produces pictures and models, so it can stay Python. Art changes run only
the art checks (CLAUDE.md). The look is judged by Daniel's eye, so every art job ends with pages
published for him, not with a test.

One connection to plan for: Stage 2 graphics (the 3D tabletop replay) will want each unit's model
from the art side and its position from CL2's history. Keep unit identity the same in both: the
unit file's name.
