# Combat Lab - GUI wish list and functional spec

Source: Daniel's notes as summarized by GPT, added 2026-10-30 (session 15).
Two parts: PART A is the idea pile (keep the architecture ready, build nothing
yet); PART B is the spec to build. "Claude's notes" under each part are the
engineering read of the repo as it stands - they are not Daniel's decisions
and do not override Section 5 of the PROJECT_MAP. Nothing here is started.

---

# PART A - Combat Lab GUI: future ideas (brainstorm, not a build order)

**Philosophy.** The GUI is not just a launcher; it is a BattleTech AI
laboratory: build scenarios, run Monte Carlo batches, analyze finished
battles, replay games, compare AI decisions, branch a game into alternate
timelines, debug AI behavior.

**Replay philosophy.** The replay is interactive, not a video: it is
connected to the simulation engine, and every recorded state can start new
analysis. "What if the Atlas moved here?", "...the Awesome fired different
weapons?", "...initiative was reversed?", "...this unit was destroyed?" The
engine recalculates from that point. The original replay is never modified;
branches are created instead.

**AI comparison.** Several bots: the Monte Carlo bot (Gladiator / Legate),
Princess, future bots, a human. Given any board state, ask every bot what it
would do and compare decisions, evaluations, target priorities and movement
heat maps.

**Heat map overlays (possible).** Expected damage dealt / received; overall
movement score; threat map; weapon effectiveness; line of sight; enemy
prediction; cover quality; movement cost; search depth; confidence.

**Search visualization (optional debug overlay).** Every move considered,
best response, final evaluation, rejected branches. For AI development.

**Procedural unit tokens.** Generated from unit files instead of copyrighted
artwork: top-down token, front standee, rear standee. Long term: standees in
3D.

**MegaMek import (possible).** Savegames, replay logs, action logs: replay
MegaMek battles in Combat Lab, then evaluate those positions with Combat Lab
bots.

**AI plugin architecture.** Bots behind one adapter interface, so a new bot
needs no GUI change.

## Claude's notes on Part A

- **Most of this already has a seam in the code.** `INTEGRATION__bots`
  already puts Gladiator and Princess behind one interface (`config.BOT`,
  per-unit `MECH_*_CONFIG["bot"]`), so the "common adapter" is a tidy-up
  (add `evaluate(state)` / `explain(state)` beside `decide(state)`), not a
  rewrite. Heat maps mostly exist as internals: the movement evaluator's
  per-spot scores, Legate's estimate, Princess's rankPath and BV heat map.
  An overlay is "expose what the bot already computed for one state".
- **The big missing piece is a serializable full game state.** Today
  (`INTEGRATION__replay`) a recording is output only: both mechs' sheets and
  the log per step, "changes nothing in the battle". That is enough to
  *view*, not to *resume*. Branching, "ask every bot at this state" and
  "what if" all need a snapshot of everything a turn depends on: every unit
  (armor, structure, crits, ammo, heat, pilot, shutdown, prone, MASC / TSM
  timers, capacitor charge, Princess memory...), the board and its changing
  terrain, initiative and activation order, and the RNG stream position.
  That is the real cost of Part A, and Part B should build it once
  (below) so the ideas stay cheap later.
- **Determinism helps.** A seed already replays a battle exactly
  (`BattleResult.seed`), so "re-run to turn N, then diverge" is a fallback
  that works with no snapshot at all, at the price of re-simulating the
  first N turns. A branch whose edit changes later dice just forks the
  stream from that point; say so in the UI (a branch is a new random
  future, not the same dice).
- **Human as a bot** needs the decision points to be callable one at a time
  (movement spot, fire declaration, physical, TAG, munition...). PROJECT_MAP
  Section 6 is already the list of those decision points, which is a good
  starting inventory for the adapter.
- **MegaMek import is the largest item** (their save format, rules
  differences, unit-variant mapping onto our `.mtf` library). Park it last.
  It would also give a way to check our rules against MegaMek's, which is
  worth something on its own.
- **3D standees:** keep it as a Stage 2 that reuses the same state feed as
  the 2D board; no engine impact.
- **One question for Daniel (open):** the notes say BLK files. The
  simulator reads `.mtf` 'Mechs; in MegaMek, `.blk` is the format for
  vehicles, infantry and aerospace, which the sim does not model. Did you
  mean `.mtf` (almost surely), or is a non-'Mech unit type coming? Until
  answered the spec below says `.mtf`.

---

# PART B - Combat Lab GUI: functional specification (to implement)

**Working title:** Combat Lab. **Executable:** `CombatLab.exe`.

**Style.** Initially a deliberately plain Windows 3.x look. Priorities:
functional, fast, clean, no unnecessary graphics. Fancy graphics later.

**Launcher.** Launch simulator; select project folder; settings; exit.

**Main window.** Tabbed: Units, Map, Options, Results, Replay.

**Units tab.**
- Centre panel: *Number of Teams*, *Number of Simulations*; display the
  estimated runtime.
- Left and right: dynamic team panels. Raising the team count creates
  further panels. Each team has a team colour, a bot selection and a unit
  list.
- Add units by dragging a unit file into the panel, or by searching the unit
  database. A dropped file is copied into the project's Mech folder if it is
  not already there.
- Bottom centre: a large **Run Simulation** button.

**Map tab.** Random map; load map; terrain type; map size; random seed.
Expandable later.

**Options tab.** CPU threads; save battle logs; random seed; debug output;
optional AI debug recording.

**Results tab.** After a run: overall statistics (wins, losses, draws,
average turns, average damage, average heat, runtime) and a battle list
(battle number, RNG seed, winner, turns, duration). Selecting a battle opens
the Replay tab.

**Replay tab.** Load by selecting a battle from Results, or by entering a
seed. Shows: top-down battlefield, timeline, turn controls, playback
controls, selected-unit information. Controls: play, pause, next / previous
phase, next / previous turn, jump to turn.

**Replay analysis.** At any recorded state the engine can generate live
analysis (threat maps, damage maps, movement scores, weapon evaluations,
enemy predictions), computed dynamically from the current state.

**Branching.** At any replay state: *Create Branch*. The user may modify unit
movement, facing, weapon selection, heat, terrain, initiative and unit
status, then continue the simulation from that point. The original replay
stays unchanged.

**Stage 1 graphics.** Simple top-down board; terrain colour-coded with
symbols for clarity; simple unit icons; graphics modular so they can be
replaced.

**Stage 2 graphics.** A 3D tabletop replay view: rotate, pan, zoom, free
camera. Preferred look: tabletop miniatures; paper standees on plastic bases
are acceptable and may become the default.

**Architecture requirements.**
- The GUI is separate from the simulation logic.
- The replay system stores the complete battle state history.
- The replay window asks the engine for analysis as needed.
- The engine owns AI calculations, heat maps, what-if analysis and
  continuing battles from modified states.
- The GUI owns display, user interaction, requesting analysis and drawing
  overlays.
- Additional AI engines (Princess, future bots) plug in to analyze the same
  recorded state without GUI changes: the replay is a general-purpose
  BattleTech AI analysis environment, not just a viewer.

## Claude's notes on Part B (how I would build it, and what to confirm)

1. **Build order, smallest useful first.**
   (1) *Engine API, no GUI*: a `lab` module with `run_batch(setup) ->
   results`, `load_battle(seed) -> history`, and `analyze(state, bot)`;
   the console flow (`INTEGRATION__map_picker`, `file_picker`) becomes its
   first client. (2) *Full-state history*: a snapshot per phase, recording
   still changing nothing in the battle (`tests/test_replay.py` style
   check, plus a round-trip test: restore a snapshot, play on, get the same
   battle). (3) Units / Map / Options / Results tabs. (4) Replay tab over
   the history. (5) Analysis overlays, one bot-exposed map at a time.
   (6) Branching. Steps 1-2 are the foundation for Part A too.
2. **Toolkit.** The Windows 3.x look fits tkinter (already used by
   `file_picker`, no new dependency, easy `.exe` with PyInstaller). The cost:
   I cannot show a tkinter window to you from this cloud session, whereas the
   current replay viewer is an HTML page I publish as a link. The
   alternative is the same Lab as a local web page (engine behind a small
   local server), which I can publish screenshots / artifacts of while
   building and which makes Stage 2's 3D (WebGL) natural. **Decided (Daniel, 2026-10-31): HTML front end**, like MekBay: click
   `CombatLab.exe`, it starts a local server and opens the browser; works
   offline. The engine may become a compiled core later (PROJECT_MAP item 13), so
   keep the GUI-to-engine API coarse and language-neutral (JSON).
3. **Estimated runtime** is feasible: `INTEGRATION__timing` already measures
   where the time goes; per-battle time from a few pilot battles, scaled by
   simulations / CPU threads.
4. **Drag-and-drop** of unit files is OS-specific in tkinter (needs the
   `tkinterdnd2` add-on); a file-picker button stays as the fallback.
5. **Unit database search** reads `data/meks.zip` (about 65+ units there
   today); the Mech folder copy follows the existing loader.
6. **Teams:** the engine already supports 3+ sides (Section 6, initiative
   and home edges), so "number of teams" needs no engine change.
7. **Branch limits to state up front:** editable fields are limited to what
   the engine can legally take mid-turn (heat, status, terrain, facing,
   position yes; forcing a specific roll outcome is a debug option). A branch
   made mid-phase resumes at that phase's start.
8. **Rules rule still holds:** a "human" or edited move is checked against
   the same legality code as a bot's move, so a branch cannot break the book.
9. **Add a `Section 6` row** for each new bot-facing hook (the adapter's
   `evaluate` / `explain`), per the placeholder rule in CLAUDE.md.
