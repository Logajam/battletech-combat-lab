# The order list: one record of what a person decided (P11 first slice, P15 step 2)

Daniel, 2026-11-24: "saving, sharing and branching for free is the winning combo". 2026-11-27: replaying a human game, saving a
game and branching timelines are ONE problem: keep track of what happened exactly.

## The idea

A game = (setup, seed, which teams are human) + the ORDER LIST. The list holds only what the person sent. The bots' own choices
(and their memory: Princess heat map, Legate estimates, see INTEGRATION__STATE.md) come out of the engine again by themselves,
because the engine is deterministic for a given setup, seed and engine version. Replaying a game = feeding the list back.
`engine/core/src/play_session.rs`: `RecordingLink` writes it, `ReplayLink` plays it back.

## Layout (order_format 1)

```json
{"order_format": 1, "engine": "<crate version>", "seed": "5", "human": ["Team A"],
 "events": [ {"post":   {"kind": "deploy", "unit": 0}},
             {"answer": {"hex": "0505", "facing": "N"}},
             {"post":   {"kind": "movement", "unit": 1}},
             {"query":  {"q": "path", "...": "..."}},
             {"answer": {"hex": "0807", "facing": "SE", "mode": "Walk"}} ] }
```

- `post`: a question the battle asked (kind, unit). On replay the battle must ask the SAME kind about the SAME unit at that point;
  if not, the replay stops with a message saying where ("out of step"). It never plays on silently different.
- `answer`: what the person sent, verbatim, in the play page's own shapes (module comment of `play_session.rs`: `deploy`,
  `move_order`, `movement`, `stand_up`, `boost`, `spot`, `tag`, `target`, `declaration`, `physical`, `end_phase`). An illegal answer
  (asked again with an "error") is in the list too, so the replay goes through the same refusals.
- `query`: a question the page put while one waited (a route, a weapon mode). Kept because some of them change the state of the
  question (`set`). Replies are not kept: the engine gives the same reply again.
- Unit ids are indexes into the scenario's unit list: valid only with the same setup. The save file must carry the setup.
- Raise `order_format` with every layout change and keep a reader for the old one.

## How this compares with the MegaMek bridge's shapes

The bridge answers (`pick_json`, `decl_json`, `phys_json`, `path_steps`, `bridge.rs`) are the ENGINE's picks for its bots: the
pick carries cost fields (fc, mp_spent), weapons go by address ("RT#3") and moves can go as MegaMek steps. The page's answers go
by weapon id and by hex label + facing + mode. They are not the same thing and need not be: the bridge format records what a bot
did (not needed: the bots replay by themselves), the order list records what a person did. A later job may convert a bridge game
into an order list; weapons by address (stable across a unit rebuilt from a dump) would then be the canonical form.

## The save file and Resume battle (built 2026-11-27)

- The play page keeps the list itself (it sees every question and sends every answer / query: `SAVE` in `play.js`) and writes the
  whole save file to this browser's `localStorage` key `bm_save` a moment after every answer and when the page is hidden or closed
  (`pagehide`, `visibilitychange`: phones skip `unload`). A finished game removes it. One slot: starting a new game replaces it.
- File: `{"combatlab_game": 1, "saved", "title", "setup" (the Lab's setup, the human team's bot still "human"), "seed", "orders": {...}}`.
  Menu > "Save game to a file" downloads it; the Lab's "Open game file" puts a file's game in `bm_save` and opens it.
- Lab: "Resume battle" appears when `bm_save` exists and opens `play.html?resume=1`.
- Engine: `ResumeLink` plays the list back, then hands the battle to the live link. The list's last unanswered question (and any
  queries after it) are cut off, so that question is asked live again. `Link::live()` is false during the playback so the first
  question the person sees carries the board and the whole log. `play_start` / `play_run` / `Game::start` / `play_blocking` take
  `resume` (the orders). Tests: `core/tests/play_session.rs` (five cut points, answer and question; same end, history and list as
  the uninterrupted game; the first live request has the board), `tests/check_web_play.py` check 6 (real pages: save, new page,
  same question and unit places, play on to the end, save dropped).
- Coming back: opening play.html again with nothing to start (a dropped tab, a phone switched off) resumes the unfinished game by itself, straight to its question (`boot`; checked in check_web_play check 6).
- ENGINE UPDATES BREAK OLD SAVES, ON PURPOSE (Daniel, 2026-11-27: "They break when the game engine is updated. Its updated because we want it to be more accurate, which means old games are inaccurate."): no version pinning. Do not build it unless Daniel changes his mind. A save the new engine cannot follow stops with an "out of step" message; a save whose steps still match but whose results changed plays on with the new rules, which is what he wants.
- Size: a scripted 13-turn 2v2 game is 232 events, about 8 KB of JSON (test `a_recorded_game_replays_to_the_same_battle` prints it). Real players' moves with drawn routes and plans are larger; tens of KB for a big battle, far inside localStorage's few MB.
- Resume point: the last ENGINE question answered (one unit's move, one unit's target and declaration, one unit's physical attack...). A plan not yet committed (weapons ticked, a route drawn) is not kept.
- Limits: Storage is per site and may be cleared (iPhone Safari after about a week unused):
  the file export is the backup. The desktop Lab starts the game itself, so it does not save yet.

## Time travel: a new timeline (built 2026-11-27, P4)

Daniel, 2026-11-19: "A timeline branch activates a new rng seed, which is recorded for that timeline." 2026-11-27: "Time to start on the ability to meddle."

- The list gets a fourth event, `{"reseed": "<n>"}`, always just before a question's `post`. The battle asks its link for a reseed first thing in
  every question (`Link::take_reseed`, `Screen::ask_with`): if one is there the dice start afresh from seed n (`PcgDice::new`), and the
  `RecordingLink` writes the event into the new list. A branched game's list is therefore complete on its own: played back with `ReplayLink` it
  gives the same battle (test `a_branched_timeline_keeps_its_past_and_replays_exactly`).
- A branch = the list cut just before a question + a reseed. The past before the cut is kept word for word; the question is asked again;
  everything after has new dice. Bots replay by themselves up to the cut, so their memory is right at the cut without snapshots.
- Page: the REC button (and "Go back in time" on the Battle over card) lists the game's questions, newest first, with turn, phase and unit;
  "Go back here" writes the branch to `bm_save` and reloads into it. The save file carries `marks` (each question's place in the list and
  its label), `parent` (the game left behind) and `child` (the later timeline, once you have gone back). Menu: "Back to the earlier timeline" /
  "On to the later timeline" swap between the two; each carries the other once (no cycles). One pair is kept, not a tree: branching again from
  the earlier timeline replaces the later one (the branch is lost unless "Save game to a file" was used first).
- The page's `pagehide` save is frozen the moment it hands over to another timeline (it once overwrote the new branch with the old game).
- Not yet: a tree of timelines with names; taking over a bot's unit in a replay ("meddle" in the other direction); branching on the desktop Lab;
  a branch from a game that was only ever a recorded history (no list).

## Branches by step, control and meddle (built 2026-11-27, REC layer Phase A)

The reseed above sits at a QUESTION, so it can only cut where a person was asked. A bot's move, or a fire step nobody was asked about, needs a
cut addressed by STEP. So the list may also hold a DECLARATIVE event, read before the battle starts and applied by a step counter
(`engine/core/src/timeline.rs`; its position in the list does not matter; ReplayLink / ResumeLink skip it; RecordingLink writes it first in the list):

```json
{"branch": {"after_step": 12, "reseed": "98765",
            "control": [{"team": "Blue", "by": "human" | "gladiator" | "princess"}],
            "meddle":  {"team": "Blue", "phase": "move" | "fire" | "phys", "unit": "Blue 1"}}}
```

- A STEP is one `history::History` mark: Deployment, the turn's INITIATIVE throw (`k: "init"`, so a cut at the turn's first move comes after it and a new seed does not throw it again), each unit's move (`k: "move"`), EACH ATTACKER'S RESOLVED FIRE in declaration order (`k: "fire"`,
  unit, target), each physical attack (`k: "phys"`), then the old phase-end marks (`fire_end`, `phys_end`, `heat`), `over`. (Daniel, 2026-11-27:
  "Ranged and physical attacks will have to be split by declaration order to achieve the subphase accuracy I want.") Every step carries `k`, `unit`,
  `target`, `turn`, `phase`, `orders` (flow events recorded so far) and `ev` (its slice of the event records). After a cut BEFORE step j:
  `after_step = j` and the flow events kept are `steps[j-1].orders` (0 for j = 0).
- `reseed`: when `after_step` steps are done the dice start afresh from that seed. `control`: from then on the team is that bot, or asks the person,
  until the end. `meddle`: the team's NEXT decision in that phase is the person's whoever owns the team, spent when a step of that phase by that
  team's unit is marked (Daniel: "That phase's choices are overwritten regardless of the original controller. Once the Meddle is committed the game
  proceeds normally from that point with whoever the currently assigned controller at the wheel.").
- `meddle.unit` (a unit's label): only that unit's decisions are the person's. Fire and physical attacks are all DECLARED before any is resolved, so the cut for a fire / physical step is at the start of that phase (before its first fire / phys step) and the meddle names which unit the person takes over. A move is one decision: the cut is just before it and no unit is named (the person picks any unit of the team still to move).
- Several branches may stand in a list (a branch of a branch); they apply in `after_step` order. Step numbers refer to the timeline as it replays.
- `{"q": "history"}`: a query the page may send while a question waits; the reply is `{"history": the replay record so far, "partial": true}`. It reads only
  and is NOT written into the list. The record's steps are the REC layer's slider.
- Bots a team may be handed mid-game: gladiator and princess (a unit's `bot` is switched). Hydra, caspar and bttt need per-team structures built at
  the start of the battle: not offered yet (PROJECT_MAP Section 4).
- Tests (`core/tests/play_session.rs`): `steps_say_what_they_are_and_the_record_can_be_read_while_parked`, `a_branch_by_step_keeps_its_past_and_replays_exactly`,
  `control_changes_hand_a_team_to_a_bot_or_to_the_person`, `a_meddle_asks_once_and_gives_the_team_back`.

## The candidate timeline on the page (built 2026-11-27, REC layer Phase C)

"Meddle here" (Log tab) and "Apply from here" (Teams tab) do not touch the game being played. They build the branch (the list cut at the step's `orders`
count, a fresh reseed, the `meddle` or `control` entry, the old game as `parent`), store it as `localStorage["bm_try"]` and reload the page into it
(`play.html?resume=try`). `bm_save` stays exactly as it was. In the candidate (`SAVE.candidate`): nothing is written to the save; the REC layer opens by
itself; the commit button reads "Meddle"; the first answer sent (`send` -> `TT.commitCandidate`) writes `bm_save` = the new timeline and drops `bm_try`.
Live, or closing REC, drops `bm_try` and reloads into `bm_save` (`?resume=1`): the first game, at the question it was waiting on. A candidate whose game
ends without asking anything (a team handed to a bot) shows Keep this timeline / Back to the earlier one. The page follows the question's team
(`TT.followTeam`): after a meddle the question may be the other team's. Not done without a reload (a second game in the worker) because a reload makes
the original impossible to overwrite by mistake; the cost is a visible reload.

## Not done yet (next)

1. (dropped by Daniel: no version pinning.)
2. Snapshots (battle state + `BotMemory`) so resuming a long game does not replay all of it; the list stays the truth.
3. Branching (P4): cut the list at an event, new seed from there on (Daniel, 2026-11-19), play on.
4. Typed answers: the answers are still free JSON checked by the engine when it reads them; a schema file per kind.
5. Desktop Lab saving.
