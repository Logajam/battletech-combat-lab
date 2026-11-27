# Timeline sync: saved games, time travel and the REC / Replay redesign (2026-11-27)

Hand-off for the next model (written for Opus to turn into a detailed build prompt). Read `CLAUDE.md` and PROJECT_MAP Section 0 first.
Daniel owns scope and the rules; the implementer owns the code and GitHub logistics. Everything below is on branch
`claude/nice-edison-j49qdl` (commits a5e92b1 .. fb702d7), pushed, NO pull request opened, nothing merged to `main`, nothing published.
All of it is marked REVIEW PENDING in the Change Record.

## 1. The goal (Daniel's words and decisions)

One problem: **keep track of what happened in a game exactly**, so that three features fall out of it:
1. replay a human-played game, 2. close the page / turn the phone off and come back to the same game, 3. go back in time and change history on a branch.
(PROJECT_MAP P15, P11, P2, P4, E2 (6).)

Decisions already made (do not reopen):
- A game = (setup, seed, which teams are human) + the ORDER LIST of what the person decided. Bots re-derive their own choices (and their memory) from the
  engine, which is deterministic. (Daniel 2026-11-24: "saving, sharing and branching for free is the winning combo".)
- A branch gets a NEW dice seed, recorded in its list (Daniel 2026-11-19: "A timeline branch activates a new rng seed, which is recorded for that timeline").
- **Engine updates break old saves, on purpose.** (Daniel 2026-11-27: "They break when the game engine is updated. Its updated because we want it to be more
  accurate, which means old games are inaccurate.") NO engine-version pinning. Do not build it.
- Peer to peer (P6) will require both players online at the same time. **Play by email is dropped for now and stays on the wish list.**
- Closing the page is only a temporary setback: opening the play page again must put the player right back where they were.
- Final end goal of the whole UI: the public browser build (no CDN), 3D tabletop default, 2D fallback (memory note / PROJECT_MAP P10).
- Doing the desktop Lab version "is next" after the browser one (Daniel asked; not yet started, see Section 6).

## 2. What is BUILT (browser build; the engine part also serves the desktop Lab)

Engine (`engine/core/src/play_session.rs`, plus `history.rs`, `lab/src/main.rs`, `wasm/src/lib.rs`, wasm `engine.js` / `playworker.js`):
- `play_blocking` records a `history::History` while a human plays (`b.events_on()`, a mark per step). The end JSON carries `replay` (record), `replay_html`
  (viewer page), `orders` (the order list). `Game::start` and `play_blocking` take team `colours` and an optional `resume`.
- `RecordingLink` wraps the page's `Link`; writes every question (`post`: kind, unit) and every `answer` / `query` the person sent. `ReplayLink` plays a list
  back and PANICS "out of step" if the battle asks something the list did not record. `ResumeLink` plays a list back and then hands over to the live link;
  it cuts a trailing unanswered `post` (and queries) so that question is asked live again. `Link::live()` is false during playback so the first live request
  carries the board and the whole log. `ORDER_FORMAT = 1`.
- **Reseed event** `{"reseed": "<n>"}` in the list, just before a `post`: `Link::take_reseed`, polled first thing in `Screen::ask_with`, swaps `b.dice` for
  `PcgDice::new(n)`; `RecordingLink` writes it into the new list.
- Spec and layout: `INTEGRATION__ORDER_FORMAT.md` (read it; it is current).

Page (`engine/lab/web/play.js`, `lab.js`, `index.html`):
- The page keeps the list itself (`SAVE`: events, marks, parent, child) and writes the save file to `localStorage["bm_save"]` a moment after every answer and on
  `pagehide` / `visibilitychange`. A finished game drops it. ONE slot. File layout: `{combatlab_game: 1, saved, title, setup, seed, orders, marks, parent, child}`.
- Menu > "Save game to a file" (download); Lab: "Resume battle" (when a save exists) and "Open game file". `play.html?resume=1` resumes; **play.html opened with
  nothing to start resumes an unfinished game by itself** (a dropped tab / phone restart goes straight to the question).
- "Watch replay" button on the Battle over card: the viewer page in an overlay iframe (`watchReplay`).
- **Time travel (first slice):** the REC button (and "Go back in time" on the Battle over card) opens a CARD listing every question, newest first
  (turn, phase, unit, kind); "Go back here" writes a branch (list cut before that question + a reseed) to `bm_save` and reloads into it. The old game is kept
  as the branch's `parent`; Menu: "Back to the earlier timeline" / "On to the later timeline" (`child`). One pair only, not a tree. The page's `pagehide` save
  is frozen at hand-over (`SAVE.frozen`; a real bug the browser check caught).

Tests (all pass; full `python tests/run_checks.py`: 12 of 12):
- `engine/core/tests/play_session.rs`: scripted game recorded and replayed to the identical battle; saved at five cut points (after an answer and at a post)
  and continued to the same end / history / list; first live request has the board; branch keeps its past word for word, holds the reseed, replays exactly,
  differs from the original and from another seed.
- `tests/check_web_play.py` checks 6 and 7 (real pages, Playwright): save part-way, resume in a new page at the same question and unit places, bare
  `play.html` resumes, play on to the end and the save is dropped; time travel list, branch, Back to the earlier timeline, On to the later timeline.
- NOTE: `check_web_play.py` serves `web_lab/`, which is rebuilt only with `--rebuild`; a page-only change tested without `--rebuild` tests the OLD page.

Measured: a scripted 13-turn 2v2 game's list is 232 events, about 8 KB. Real play (drawn routes, plans) will be larger; far inside localStorage.

## 3. Known limits of what is built

- One parent / child pair, not a tree. Branching again from the earlier timeline replaces the later one (lost unless saved to a file first).
- The reseed takes effect at the first question after it, so dice drawn between the previous answer and that question come from the old stream.
- Browser only. The desktop Lab starts games itself (`play_start` / `Game`), so it does not save, resume or branch yet (the engine part works there).
- Resuming replays the whole game (no snapshots yet). Browser storage may be cleared (iPhone Safari after about a week unused): the file export is the backup.
- Unconfirmed plans are not kept (weapons ticked, a route drawn but not committed): the resume point is the last ENGINE question answered.
- Time-travel card: labels are rough ("Turn 5 · Fire · Red (tag)", "who moves next"), the combat report pop-up can cover the card, no preview of where
  units stood.
- Not tried by hand on a real phone; only automated page tests.
- A bad `resume` list makes `play_blocking` return `{"error": ...}` as the end; the page does not handle that nicely.

## 4. The redesign Daniel has settled on in conversation (BUILT 2026-11-27 in the browser build, REC layer Phases A-D: see the Change Record; the desktop Lab is Phase F; originally NOT built; this is what the next prompt should specify)

**Two surfaces, one core.**
- **In-game REC** (the existing REC button, replacing today's card): a panel over the live board. Pressing it sends the CURRENT SAVE to a replay view that
  opens over the game, reading the list and reconstructing the game from it, "at the least up to the point the save ends". It stops there because the engine
  is parked waiting for the next question (same state as a human's turn): **the replay does not need to run to the end**. This needs the History record to be
  readable WHILE the game is parked (today it is only returned when the game finishes; `History::finish` consumes it, so add a non-consuming snapshot).
- Layout (Daniel): the Inspector takes over the TOP HALF of the screen with the replay's playback bar and a LOG of exactly what happened during the phase.
  The camera focuses on the event being looked at. Movement paths highlighted. Attack arrows highlighted showing both units, and the results of the fire
  displayed. The replay is "a different UI on top of the board graphic's layer": it must reuse the tabletop renderer (`tabletop.js`, `mapview.js`), not the
  old separate 2D `INTEGRATION__replay_viewer.html`. (This is also P10's standing goal: "Replay viewer should share the same renderer".)
- Play buttons let you view slices of the timeline; the Log says what happened. Select a slice and RE-ENTER the timeline from there = cut the list there and
  branch (the engine part exists).
- **Replay TAB** (the Lab's existing one) stays its own tab, becoming "more of an actual replay / wide-field stat analysis area" for any finished battle (bot or
  human), with a **"Play from here"** button that opens a game at that point; once in the game, REC is available again for further meddling. Keep the Replay
  tab small until in-game REC works (watch, find, play from here); the event records already support analysis later (`INTEGRATION__EVENTS.md`).
- Both surfaces must SHARE: the recorded steps and events, the tabletop renderer, and the one operation "cut here and continue". Do not fork the renderer.

**Meddling with ONE unit for ONE phase.** (Daniel's design.) The replay shows what a unit's move was; you pick a different move and apply; the engine
REGENERATES the game from that change. To also change where that unit fires, step to the next regenerated slice (that unit's fire phase) and change it too.
If a HUMAN is in the loop, the regenerated replay stops at their question and waits; the player must re-enter the time stream there, OR assign a bot to
take their place. Hence a **per-team "Bot setting" toggle before re-entering** (Human is one option), plus a scope for how long a change of control lasts,
returning control to the original owner afterwards. Implementer's proposal, agreed in principle (the details are open, Section 5):
- an OVERRIDE order event: "at this unit's movement (or fire) question, use this answer" (bots' own answers are not in the list, so this is new);
- a CONTROL event: team X is Human / bot Y from this point for a scope (this unit's move only, the rest of this phase, this turn, the rest of the game);
- both in the list like the reseed (`take_*` hooks on `Link`, applied deterministically at fixed call sites, recorded by `RecordingLink`), so a branch with a
  one-off meddle replays exactly. Control changes for BOT units need a hook at the `HumanBots` entry points (`choose_target`, `move_pick`, ...), not only in
  `Screen::ask_with`, because a bot-controlled unit never asks a question.

**The key new engine piece:** "Play from here" on a BOT-ONLY battle (and any slice picked in the replay) cannot cut by list position: bots never ask, so the list
holds no questions. The cut must be addressable by **(turn, phase, unit)** (or by a step number the History records: store, per History step, how many
order-list events had been recorded so far, and the unit/phase). The engine runs the battle to that point, then hands the chosen team to a human or another
bot. This one mechanism covers both human games and bot battles.

## 5. Open questions / decisions still Daniel's (ask, or choose and say so)

- Scope menu for a change of control: is {this unit's move | rest of phase | rest of turn | rest of game} the right set? How does a player end a scope early?
- Seed on an override-only meddle: reseed every time, or keep the old dice stream when only one answer changes (dice after the change will differ anyway once
  consequences differ)? Daniel's 2026-11-19 ruling says a branch activates a new seed; confirm it also holds for a one-unit override.
- Timelines: stay at one parent / child pair, or become a named tree (needs storage beyond one `localStorage` slot; IndexedDB or files)?
- Slow regeneration: every edit replays the game up to the cut. Acceptable for now; snapshots (Section 6) are the fix. How long a game must it stay quick for?
- Where the Replay tab's wide-field analysis should stop for now.

## 6. Suggested build order (the implementer's, Daniel agreed with the direction; Opus may refine)

1. Make the History readable while the engine is parked; REC sends the current save to a replay overlay (reconstruct up to the end of the list).
2. Rebuild that overlay on the tabletop renderer: playback bar, phase log, camera focus, highlighted paths, attack arrows with results (events: `MOVE`,
   `MOVE_PATH`, `ATTACK`, `PHYS_*`, damage by location; `engine/core/src/events.rs`, `INTEGRATION__EVENTS.md`).
3. The cut addressed by (turn, phase, unit) with a per-step "orders so far" count; branch from the overlay (replaces today's card list).
4. OVERRIDE / CONTROL events, the per-team Bot setting and scope on re-entry.
5. "Play from here" from the Replay tab (bot-only battles included).
6. Then: the desktop Lab version (save / resume / branch in `lab/src/main.rs`; the page logic is shared, the server must start a game from `{setup, seed,
   resume}`: `play_start` already accepts `resume`), snapshots (per-phase battle state + `BotMemory`, INTEGRATION__STATE.md: Princess / Caspar heat map and
   posture, Legate's estimate and friends' declared damage, tiers, fire control; the list stays the truth, a snapshot is a checkpoint; test = resume from a
   snapshot gives the identical rest of the battle, on the 62 reference battles), typed answer schemas, a timeline tree.
   Daniel's snapshot idea: "save the aggregate of that tracking per phase" so loading is fast.

## 7. Constraints to keep (from CLAUDE.md and decisions)

- Run `python tests/run_checks.py` after every change (it picks the checks); the 62 reference battles must not change unless the change is meant to; a
  recording-only change must keep every result identical (so far none changed).
- Cite the rulebook page in code for rules; never put rulebook text in the repo.
- New decision points get a PROJECT_MAP Section 6 row; new bot calls go in `bridge.rs` too. (None added so far.)
- Do not touch the old Python viewer's role beyond what the redesign needs; the engine is Rust, the Python engine is gone.
- Label work for review (Section 0 REVIEW QUEUE + "REVIEW PENDING (higher-level model)" in the Change Record) at the end of a session.
- Tell Daniel in plain words what changed (he does not use GitHub). Commit on the session branch and push; open a pull request only when asked.
- Long runs: SOP in CLAUDE.md (progress files, re-run the identical command after a restart). Browser play checks take several minutes each.

## 8. Where to look

| What | Where |
|---|---|
| Order list spec, save file, time travel, limits | `INTEGRATION__ORDER_FORMAT.md` |
| Backlog item | PROJECT_MAP `P15` (and P11, P2, P4, P6, P1, E2 (6)) |
| Change Record entries | `INTEGRATION__CHANGE_RECORD.md`, 2026-11-27 (four entries, newest first) |
| Live play session, links, reseed | `engine/core/src/play_session.rs` |
| History record / replay page | `engine/core/src/history.rs`, `INTEGRATION__replay_viewer.html` |
| Events (moves with routes, attacks, damage) | `engine/core/src/events.rs`, `INTEGRATION__EVENTS.md` |
| Bot memory that snapshots must carry | `INTEGRATION__STATE.md` |
| Play page, REC card, save code | `engine/lab/web/play.js` (`SAVE`, `timeTravelCard`, `branchFrom`, `boot`) |
| Tests | `engine/core/tests/play_session.rs`, `tests/check_web_play.py` (checks 6, 7) |
| Tabletop renderer the replay must reuse | `engine/lab/web/tabletop.js`, `mapview.js` |
