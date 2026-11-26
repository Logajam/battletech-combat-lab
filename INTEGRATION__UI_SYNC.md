# Play UI: sync document for the UI session (2026-11-26, written by Sonnet 5.5 for an Opus session)

Purpose: one place that says (1) what the play UI is today, (2) every design record that already exists, (3) the NEW concept
Daniel pasted on 2026-11-26 ("Yesterday the Map, Today the UI", GPT's summary, "many details technically wrong, but the concept of
layout and wiring is generally correct"), (4) where the new concept agrees with, extends or CONFLICTS with the earlier rulings,
(5) the engine and test facts a UI session needs, (6) the questions only Daniel can settle, and (7) a proposed build order.
Nothing in here is built by this file. Daniel owns scope and rules; Claude owns implementation and logistics (CLAUDE.md).

Daniel's standing words for this session (2026-11-25): "We won't push to live yet, just get the fixes in. Need an entire session
about the UI hopefully before the next push." Phone / layout polish was held for this session. DO NOT run
`tools/publish_public.py` or `tools/publish_web_lab.py` unless Daniel asks. Daniel's warning from 2026-11-24: moving the mockup
into the live game was "less than successful", so settle each home on paper, then build one home at a time, checked on a phone.

## 1. Read these first (the design record that already exists)

| File | What it holds | Status |
|---|---|---|
| `INTEGRATION__UI_DESIGN_NOTES.md` | Daniel's design principles (a Gemini summary, then a GPT summary, both second-hand): three layers of disclosure, "if information has a location, draw it on the map", intents pipeline, confirm loop, input handling | Principles, accepted |
| `INTEGRATION__BATTLEROM_UI.md` | Session 33 design record: vocabulary (title bar, enemy strip, placard, info bar, action cluster, detail sheet, unit strip, weapons panel, hex card), movement and fire rulings, looks, contrast, type floor 11 px, tap targets 32 px | Partly superseded (see Section 4) |
| `INTEGRATION__UI_DECISION_HOMES.md` | DRAFT 2: about 115 rows, every player action with a HOME; Section 10 lists the rulings Daniel still owes; Section 12 is what the MegaMek bridge expects; Section 11 says the order of work (rulings, rules audit, state diagram, only then code) | Draft, Daniel has ruled on some rows |
| `INTEGRATION__PLAYER_DECISIONS.md` | The decision audit; Section 24 is Daniel's bug list (items 9, 12, 14, 22, 23, 26-28 still open), Section 25 an audit list | Source for the homes table |
| `reference_art/battlerom_ui/` | Mockups (play v16, tabletop, isometric, holotable), `weapon_grid_sketch.html` (v3, the fire-overlay ruling), `parked_fire_screen_B6_B7_B8.patch` (parked fire-screen ideas) | PRIVATE, design only |
| `INTEGRATION__PROJECT_MAP.md` | P3, P3a (UI homes), P10 (3D tabletop, Section 0 notes), O1, the "Minor bug fixes (Daniel, 2026-11-25)" block | Backlog |

Note on a mistake of mine: earlier in this conversation I proposed to "put your summary in PROJECT_MAP as the UI plan". That was
before I had read the files above. The right home for the new concept is this file plus a row in the homes table, not a second
parallel plan.

## 2. The live play page today (engine/lab/web/play.html, play.js 1445 lines, mapview.js, tabletop.js, lab.css)

Tests that guard it: `tests/check_web_play.py` (478 lines, drives the page with policies, answers every engine question kind),
`check_web_tabletop.py`, `check_web_ui.py`, `check_web_lab.py`. `python tests/run_checks.py` picks them when `engine/lab/web` changes.

### 2.1 Permanent regions (play.html ids)

- `header`: title "BattleROM", `#phase` text, REC button (a stub card: "timeline and branching, not built"), `Unit` button
  (`#det-btn`, opens the dock's detail), `Menu` button.
- `#menu`: nested folders: Look (SL-HIS Dark / Light, Windows 95, Modern), View (colour-blind mode, range bands, ...), Tabletop
  looks (relief, glass, trees, skin), Game (Report, Back to the Lab). Looks and view prefs live in `localStorage` keys `bm_*`.
- `#estrip`: enemy chips, with a vertical "ENEMY" label (no "Current Target" line yet).
- `#mapwrap`: `#map` (SVG; in 3D mode `tabletop.js` draws underneath through `MapView`), `#zoom` (+, -, fit, tilt; top-right,
  already the "map controls in the upper-right corner"), `#wpanel` (the fire-phase weapon LIST, left, about 40% wide, hidden
  outside the fire phase), `#info` (the info bar: results or the focused weapon's detail), `#cluster` (the action cluster:
  readout + press-and-hold Move!/Fire! + Undo/Clear + context buttons such as jump toggle, drop prone), `#report` (combat report).
- `#strip`: friendly chips (the unit strip). Chip classes show moved / current.
- `#dock`: three sizes (`data-size` 0/1/2, size 2 is a 74% overlay), `#dockhead` (unit name, Report button `#rep-btn`, smaller /
  bigger), `#docksum`, `#docktabs` (TABS = Plan, Weapons, Stats, Armor), `#dockbody` (`#sheet` = the engine question's sheet,
  `#tabbody` = the data tabs). This is the permanent "record sheet" the new concept removes.
- `#card`: a floating card for the hex card, weapon card, attack card, REC stub, and the 3D fallback notice.

### 2.2 How the page is driven (important for any redesign)

- The ENGINE ASKS ONE QUESTION AT A TIME (`engine/core/src/play_session.rs`, `ask` / `ask_with`; request `kind`s: `deploy`,
  `move_order`, `stand_up`, `boost` (MASC / supercharger), `jump_boost` (mechanical jump boosters, new 2026-11-25), `spot`, `tag`,
  `movement`, `target`, `declaration`, `physical`, `end_phase`). The page polls (`play_poll`), runs `HANDLERS[kind]`, and sends an
  answer (`play_answer`). While a question waits it may also call `play_query` tools (route, reach, re-price a weapon, switches).
- So the UI is a set of question handlers, NOT a free-form state machine. A redesign that moves controls around (context widget,
  context actions) changes how each handler PRESENTS its question; it should not change what the engine asks. The mapping from
  "an engine question" to "the home it lives in" is exactly the homes table.
- `GROUP` / `SEC` in play.js (lines near 1284) map each question kind to a phase group and a report section; `jump_boost` was
  added there on 2026-11-25. Any new question kind must be added to both, to `inMovement`, to `check_web_play.py`'s policies, and
  (if it is a bot decision) to `bridge.rs` (CLAUDE.md).
- The movement flow: reach table from the engine, waypoints, `drawPath` / `drawTurnArrows` / `drawReach`, `holdFor()` hold-to-commit
  (about 650 ms, fill shows progress), `commitMove`, `undo`. Prone / stand-up has its own plan (`pronePlan`, `proneSheet`,
  `drawProneArrows`); the careful-stand button is `stand-careful`.
- The fire flow (`HANDLERS.target`, `declaration`): `S.fire` (per-weapon assignment, per-target lines, `tcur` = current target,
  `cycleTcur`, `lookAtTarget`), `declSheet` (grouped weapon rows, sorts, ammo bins, aimed-shot pick `strikePick`, `setAim`),
  `drawTargets`, `drawRings` (range bands of the focused weapon), `drawShotLine`, `tnCard`.
- Inspector today: `inspect(id)` sets `DOCK.unit` and opens the dock at size 2 on the Stats tab (long press on a unit,
  `HOLD_SLOP`). Hex long press -> `showHexCard`. Weapon long press -> `showWeaponCard`. Attack-line tap or long press -> `attackCard`.
- Attack lines drawn for BOTH sides (Daniel 2026-11-24); the report (`#report`) is sectioned (move / ranged / physical / heat)
  and released as questions are answered (`feedLog`, `releaseLog`).

### 2.3 What exists vs the new concept, region by region

| New concept | Live page | Gap |
|---|---|---|
| Title bar | `header` (phase text, REC, Unit, Menu) | Close. REC is a stub. |
| Enemy strip + "Current Target" line | `#estrip` chips; current target is `S.fire.tcur`, shown in `#info` and the TN card | Needs a target line tied to the strip |
| Big central map | `#mapwrap` (3D default since 2026-11-25) | Fine |
| Map controls upper-right | `#zoom` (+ - fit tilt) | Already there |
| Bottom-centre action row: Context action(s), Commit, Undo, Cancel | `#cluster` floats over the map: readout, hold-to-commit, Undo, Clear, jump toggle, drop prone | Exists but mixes readout and buttons; "Cancel" vs "Clear" semantics need defining |
| Friendly strip + "Active Unit" line with Report | `#strip` + `#dock` header (name + Report) | Same idea; the dock header is the Active Unit line |
| Inspector replaces the record sheet | The dock (Plan / Weapons / Stats / Armor tabs) IS the record sheet, permanent at size 1 | THE BIG CHANGE |
| Long-press any element opens THE RIGHT inspector section | Long press unit -> Stats tab only; hex card; weapon card | Needs a routing table (element -> section) |
| Inspector over the upper half of the map, pushing the target display down | Dock size 2 overlays the lower 74% | Opposite edge; see Section 5, Q3 |
| Peek drawers (left / right, configurable pages) | Not built. Left side is `#wpanel` (fire phase) | New |
| Phase-aware context widget next to Commit (movement info, then heat in combat) | `#cluster` readout is movement-only; heat is in `#docksum` / placard bars | New: heat tracker in combat |
| Context actions only when the state allows | Partly: Stand carefully, MASC / jump-boost questions, TAG, spot, aimed-shot pick, drop prone toggle | Pick up club, charge / DFA drag, push not as buttons |
| Rarely used always-legal actions (Go Prone) in the inspector | `dropRow` / `stand-careful` live in the sheet / cluster; Go Prone is a toggle in the movement cluster | Move to Inspector Movement section, optional peek page |

## 3. The new concept (Daniel's paste, 2026-11-26), restated without GPT's errors fixed (Daniel has not said which details are wrong)

Philosophy: progressive disclosure; the tactical map is always primary; permanent UI is minimal; information appears when relevant.

- Permanent layout (top to bottom): title bar; enemy strip with a "Current Target" line; map (controls upper-right); bottom-centre
  action row (context action buttons, Commit, Undo, Cancel); friendly strip with an "Active Unit" line that also holds the
  Report button (opens the game log).
- Inspector: replaces the traditional record sheet. Long-press ANY UI element to open the matching section: movement -> Movement,
  heat -> Heat / Engine, armor -> Armor, pilot indicator -> Pilot. It opens over the UPPER half of the map, pushing the active
  target display down, instead of replacing the tactical view.
- Peek drawers: left and right sliding drawers for quick glances. The player chooses what each shows and cycles pages (movement,
  heat, armor, pilot, weapon summary...). Deliberately redundant with the Inspector because open / close must be much faster.
- Context widget beside Commit: phase-aware. Movement: movement info and movement interactions (the Jump toggle). Combat: it
  becomes the heat tracker. Other phases: whatever matters then.
- Context actions: only actions made available by the state (Aimed Shot vs a prone target, Pick Up Club beside suitable woods,
  Stand Up after a fall). Always-legal rare actions (Go Prone) live in the Inspector and optionally a peek drawer.
- Design goal: three questions, three interaction levels. Main UI = "what decision do I need to make now?"; peek drawers = "what do
  I glance at repeatedly?"; Inspector = "the complete rules and record sheet information."

## 4. How the new concept relates to the earlier rulings (agree / extend / conflict)

AGREES (no new decision needed):
- Three layers of disclosure; long press for detail; context-only buttons; confirm before commit (hold-to-commit exists).
- The data sheet's job moves to the Inspector (Daniel, 2026-11-24).
- "Redundant control paths are fine if they call the same backend action" (UI_DESIGN_NOTES Section 6).

EXTENDS (new, consistent with the old):
- The phase-aware CONTEXT WIDGET (old plan: a fixed move readout in the action cluster, heat only on the placard).
- PEEK DRAWERS, with player-chosen pages (old plan had "collapsible or tabbed panels", flick a side panel closed, UI_DESIGN_NOTES
  Section 2; the homes table has no drawer row).
- "Current Target" and "Active Unit" lines tying each strip to one unit.
- Long-press routing BY ELEMENT to an Inspector SECTION (old plan: long press a unit opens the Inspector; sections proposed in
  homes table Section 1: Status, Criticals, Weapons, Movement, Settings, Debug).

CONFLICTS or OPEN (Daniel must rule; see Section 6):
1. EXPANDED PLACARD. The homes table (Section 10 item 1) asked whether the selected unit's placard grows to show Gunnery /
   Piloting, movement, heat, context buttons. The new concept puts that information in the context widget, peek drawers and
   strips instead. These are two different answers to the same question; the new concept is probably meant to replace the
   expanded placard. Not ruled.
2. FIRE-PHASE WEAPONS. Daniel's ruling of 2026-11-24 (homes table Section 10 item 2): the left-hand weapon list is REPLACED by a
   clear overlay on the map laid out like the critical table (five location columns by 12 slot rows, colour = state, target
   pinned in the centre column, drag-paint groups, drop on an enemy to split fire). The new concept does not mention it, and a
   LEFT peek drawer would sit where the old list / overlay's left columns are. The live page still has the old list (`#wpanel`);
   the overlay is not built (sketch only, `weapon_grid_sketch.html`; parked ideas B6-B8 in the patch). The two must be reconciled
   before either is built.
3. INSPECTOR POSITION. The new concept: over the upper half of the map. Old and live: bottom sheet. Consequence to think through:
   the enemy strip and the target line are at the top, so an upper-half inspector hides them unless they are pushed down; the
   concept says "pushing the active target display downward", which means the target display must be a movable element, not a
   fixed strip. On a phone in landscape the map is short already.
4. PERMANENT PLAN / WEAPONS TABS vs. NONE. Live: Plan, Weapons, Stats, Armor tabs always visible at size 1. New: nothing permanent
   except the two strips with their lines. Everything the tabs show must have a home (inspector section, peek page, or the
   context widget) before the dock is removed. The homes table Section 5 / 6 rows say where each decision lives; use it as the
   checklist.
5. "CANCEL". The action row names Undo and Cancel; the old record has Undo ("step back one waypoint or assignment", Esc) and
   Clear ("clear the whole plan"). Need to settle whether Cancel = Clear = leave the question without answering (the engine cannot
   skip a question, so Cancel can only discard the draft, not the decision).
6. REPORT BUTTON PLACE. Old: dock header (`#rep-btn`) plus Menu > Game > Report. New: the Active Unit line. Fine if the dock goes.

## 5. Opinions on the new concept (what I told Daniel, kept here so the Opus session can agree or push back)

- Build the context widget and the bottom action row first, then the Inspector with long-press routing, THEN decide on peek
  drawers after living with both. Reasons: drawers duplicate the Inspector, need a pages-and-settings UI, and on a phone their
  edge swipes collide with browser back-swipe and map panning.
- Q3 (inspector position): opening on the lower half keeps the target line visible; upper-half is what Daniel's concept says. Try
  both on a real phone before fixing it. Maybe: upper half on a tall portrait phone, a side panel in landscape.
- Long press as the only door to detail is hard to discover: keep one visible Unit button (exists: `#det-btn`) and show a hint the
  first time.
- Rarely used legal actions must stay one step from the unit, not buried (Go Prone, shutdown later, eject later).
- Lateral shifts and tripod facing changes (built 2026-11-25) have NO page control yet; they belong in the context widget during
  movement, shown only for mechs that can use them (`ground_limit` in `engine/core/src/mech_state.rs` already knows `lateral` and
  `free_facing`). Ground targeting (any weapon may target the ground, Daniel 2026-11-25, still open on the long press) fits the same
  pattern: long press on a hex gives "Fire at this hex" as a context action. Not built (engine side is large; see Section 7).

## 6. Questions that only Daniel can settle (collect these before building)

1. Which details of GPT's summary are "technically wrong"? (Daniel said some are. Ask for the list, or ask him to mark a copy.)
2. Expanded placard: dropped in favour of the context widget and peek drawers? (Section 4, item 1)
3. Weapons: does the 2026-11-24 map overlay (critical-table layout) still stand? If yes, where do the left peek drawer and the
   overlay meet? (Section 4, item 2)
4. Inspector position and sizing: upper half always, or by orientation? Does it pause the map's input while open?
5. Peek drawers now or later? If now: how many pages, are the choices remembered per device, per unit, or per phase?
6. What exactly does Cancel do (draft discard vs leave the question)? Is "stand still" a Move! with no path, or its own Done
   (homes table open item T4)?
7. Overlays (movement, firepower, LOS, heat): menu only, or a quick toggle near the context widget (homes table item G12)?
8. Hold-to-commit stays for all commits, including Fire!? Phone landscape layouts: same parts rearranged (old ruling) still holds?
9. Ground targeting: long press on a hex, as I recommended? Build it with fires, minefields and buildings (engine) or now for
   area-effect weapons only?
10. Mech base height (2 levels) in the 3D tabletop is a known minor bug (PROJECT_MAP, Minor bug fixes 2026-11-25). Fix in the UI
    session or its own pass?

## 7. Engine and test facts a UI session needs

- Engine questions and answers are documented at the top of `engine/core/src/play_session.rs` (request kinds and answers).
- New in 2026-11-25: `stand_up` answers `(stand, plan, facing, careful)` and its request has a `careful {available, tn, walk}`
  block; `jump_boost` is asked first in the movement phase when a unit has mechanical jump boosters; `equipment_json` carries
  `jump_boosters {has, mp, jets, on}`. The movement request's route steps include four lateral shifts (lateral_left, lateral_right,
  lateral_left_back, lateral_right_back) and tripod multi-hexside turns that cost 1 MP; drawn routes use the same names
  (`drawn_route.rs`, `step_walk.rs` `Step::ALL` has 11 steps). The page draws turn arrows for ONE hexside at a time; tripod 1-MP
  multi-hexside turns are untested in the page.
- Mech JSON must not gain a field the frozen fixtures lack (`jump_boosters_on` is transient and not serialized).
- The 3D map: `mapview.js` is the projection layer every `draw*` goes through; `tabletop.js` draws the board; default is 3D with
  2D as the fallback (`?view=top` forces flat). Gestures: tap select, drag move preview, long press inspect / hex card, right-drag
  orbits, pinch zoom. Mech bases are flat discs (`V.baseH = R * 0.22`), 2 levels wanted.
- Checks to run after UI changes: `python tests/run_checks.py` (it picks the website checks when `engine/lab/web` changes);
  `--full` before a merge only if code changed. The last FULL run predates the 2026-11-25 fixes and the BTTT restore; run it
  before merging. All 68 reference battles pass; `cargo test --test bttt` passes.
- Looks: layout, tap sizes and map are identical in all looks; type floor 11 px, tap targets at least 32 px; the colour-blind
  palette adds line patterns. A 4 px grid cleanup with an automated check was advised and wanted by Daniel once the layout is frozen.
- Looks and drawer / widget choices that are remembered per device use `localStorage` through `pref` / `setPref` (wrapped for
  private windows).

## 8. Git and process state (so the next session starts clean)

- Branch `claude/awesome-darwin-1zre0f`, latest commit `c15ec47` (BTTT restore) plus this document. NOT merged to `main`; `main`
  also lacks the earlier publish fix `d4e9701`. Merge path: pull request, full check run, merge (CLAUDE.md). NOTHING of the
  2026-11-25 batch is published.
- Open tasks outside the UI: ground targeting (not built), Forced Withdrawal (Daniel: on hold), the TO:AR moves, the
  Initiative Die wish. The 2026-11-25 batch (tripod / quad moves, careful stand, jump boosters) is REVIEW PENDING in the Change Record.

## 9. Proposed order of work for the UI session (Claude's proposal; Daniel rules)

0. Ask Daniel the questions in Section 6 (items 1-4 and 6 block the design; the rest can be defaults).
1. Update the homes table (`INTEGRATION__UI_DECISION_HOMES.md`) with the new concept: add rows for the context widget, peek
   drawer, Current Target and Active Unit lines; reroute the expanded-placard row; add the long-press routing table (element ->
   Inspector section). Add the Core Rulebook page column (homes table Next steps 2) and the lateral / tripod / careful-stand /
   jump-booster rows.
2. Write the interaction / state diagram (Idle, Unit selected, Planning move, Confirming hazards, Fire assigning, Declaring,
   Physical, End Phase, Inspecting, Drawer open) with one arrow per row. Daniel asked for this before graphics.
3. Build, one home at a time, checked on a phone-size and a landscape screenshot (headless Chromium is installed):
   a. bottom action row and the context widget (movement readout + Jump + lateral / tripod options; heat tracker in combat);
   b. Current Target and Active Unit lines;
   c. Inspector sections and the long-press routing; retire the dock's permanent tabs;
   d. context action buttons not yet present (club, charge / DFA, push, aimed shot);
   e. peek drawers, only if still wanted after a to c;
   f. the fire-phase weapon overlay (Daniel's 2026-11-24 ruling), once item 3 of Section 6 is answered.
4. After each step: `check_web_play.py` policies updated for any new action, a screenshot pass, a Change Record entry marked
   REVIEW PENDING, and a PROJECT_MAP Section 0 update. No push to the live site until Daniel says so.

## 10. Daniel's rulings on Section 6 (2026-11-26, recorded by the Opus UI session)

Process: the previous session is still pushing bug fixes to `main`. Before every merge from the UI branch, fetch `main` and merge
it in; never overwrite its work (Daniel: "an item on the checklist").

1. GPT's wrong details are rules guesses, e.g. "Aimed Shot vs a prone target" (not a rule; the engine allows aimed shots only at an
   immobile target, `bot_aimed_shots.rs`). Take the LAYOUT and WIRING from the concept, never its rules.
2. PLACARDS stay. Context widget = what the player needs to control the current action; placard = the unit's current state, and
   the anchor for conditional buttons ABOUT that unit (aimed shot, declare charge). New idea: the placard's BORDER becomes the
   armor and structure bars, so they stay visible when a distant placard shrinks to the unit's short code. The selected unit (or
   another target, such as a building) gets an EXPANDED placard; its contents are to be settled in this session.
3. WEAPONS: the overlay spread around the target in the ACTIVE unit's critical-table layout stands (it also shows which unit is
   active). Player options may turn it into a list on one side, or into a peek drawer.
   DRAWERS: very wide, short arrows with their base on the screen edge; press or flick to open; a drawer comes out half way and
   covers its half of the screen, its arrow reversed to close it. Both open = map covered; opening one a second time covers the
   whole screen ("a quick glance at the armor diagram" vs "see it in detail"). Drawers are wanted: faster than a long press.
4. INSPECTOR: the same pages as the drawers, but opened by a long press and more contextual. Covers the TOP half of the screen
   (title, strip and target bars); the active target becomes the inspector's own header. Flick down = full screen; flick up or
   touch the map = close. Contents and order are to be settled in this session.
5. CANCEL: Clear/Cancel, and go back one step. STAND STILL is a committed move with no steps. The Commit button changes its label
   with the state ("Stand still" -> "Walk" -> "Run"), coloured by movement mode.
   GENERAL PRINCIPLE: the same buttons, contextual. Commit is always the same spot; common mode options are always the same spot;
   a long press or a drawer ("wing") shows the other options. Any plan can be made and cancelled before committing. A plan with an
   element of chance gets a warning first. If the chance fails (a failed stand, say) the player is told and decides again from
   that point.
6. Side drawers: yes (see 3).
7. Overlay toggles: in a menu. Heat map option: tap a unit to show its map; tap a force's title bar to show the whole force's.
   The weapon-overlay layout choice is a player menu option.
8. Hold-to-commit for Fire! too.
9. Ground: a long press on the ground opens the inspector, with "target the ground" as an option. In the fire phase, tapping the
   same hex again cycles its targets: first enemy unit, then a second enemy unit there, then the ground. An empty hex needs two
   taps to target the ground (so a pan's tap does not target).
10. Mech bases 2 levels tall: on hold, Sonnet work, not this session.

Found while recording (to settle with Daniel): the engine retries a failed stand by itself until it stands or runs out of MP
(`piloting_rolls.rs` `resolve_stand_up`); under ruling 5 the player should be asked after each failure. That is an engine change
(a new question, or a repeat of `stand_up`, plus `bridge.rs` if it is a bot decision).

### 10a. Further rulings (Daniel, 2026-11-26, second message)

- "A button lives on the thing it acts on" (the Opus proposal: actions about a unit on its placard, actions about yourself in the
  bottom row) is accepted as the concept.
- AIMED SHOTS: at an immobile target, a contextual button on that target's placard. With a targeting computer it needs a MODE
  SWITCH; mode switches most likely live on a tab in the inspector.
- WINGS (drawers) remember which page they showed in which PHASE, so a wing can show one page in the Movement Phase and another in
  the Weapon Attack Phase.
- The INSPECTOR opens on "what is in this hex, and what special actions may be available" (the hex page), not on the long-pressed
  element's own page (this replaces the Opus proposal for question 4's first page).

### 10b. Third round (Daniel, 2026-11-26)

PLACARD (feedback needed once it is drawn; Daniel expects it may confuse):
- Top / bottom border = armor / structure (the existing bars are double-sided: left side / right side damage). Left side = a heat
  scale. Right side = a small white box with the base to-hit number and the range, or two coloured squares.
- Ideas for the "one location nearly gone" problem: a segmented location bar (green / yellow / red), one vertical bar per location
  side by side, a colour-coded 'Mech-shaped armor diagram in the expanded view (MegaMek's record-sheet layout and art, if the
  licence allows; check its files and CREDITS before reuse), or a jewel / light that warns of critical armor.
- Expanded placard: base to-hit and range are what matter (how the unit moved, not much). Weapons: a condensed "#x Weapon" list or a
  drop-down button inside the placard; to be decided by seeing it.

LAYOUT: more vertical space. Menu and enemy information move to the LEFT side, friendly information to the RIGHT; the centre is a 1:1
square play area with no header or footer.

INSPECTOR: flick on the header, content scrolls, a touch on the map only closes it: agreed; a working model is needed to feel it.

TARGET CYCLE: units, then buildings, then the ground. Consideration: make the ground easier to target when the targeting unit has
area-effect weapons (consistency vs utility, not ruled).

TABS AND PAGES: one set, organised as tabs that contain pages, shown in the drawers and the inspector.

UNDO and CLEAR: TWO buttons (starting over is the most common act; no back-tracking or long press to get it). The corner has room;
it may also hold the context widget (itself a button) and the mode button.

CONTEXT WIDGET, MOVEMENT PHASE: MP remaining and current TMM; press = switch to jumping; long press = more movement commands through the
inspector. Movement mode is shown by the Commit button's colour and title. Commit gets a WARNING SYMBOL when a known hazard is in the
plan (hidden hazards such as mines give no warning until they trigger). Heat: a small "heat generated (total heat capacity)" on the
side of the widget, red when the capacity is exceeded.

CONTEXT WIDGET, FIRE PHASE: tracks heat. Long press = straight to the heat tab (which has an option for a unit's heat limit for the
fire button). Over the cap it becomes a button offering a coolant pod or the radical heat sink (coolant pods in the standard ammo
order unless chosen on the heat tab with a long press). The engine already has these switches (`play_session.rs`, "coolant" auto /
hold / now, "radical" on).

DRAWERS: no hints. Only TWO drawers (left and right); once open, flick up / down or pick a tab to change what it shows, and it stays.

HEAT MAPS: two main ones: where this unit can move, and where it can shoot; both on = a combined threat envelope.

DEFAULT DRAWER TABS: Movement Phase: left = more move options (go prone, climb ...), right = the current unit's status page. Weapon
Attack Phase: left = the current target's armor diagram, right = weapon modes and ammo feeds.

INSPECTOR ORDER: as proposed for now (hex page first, ruling 10a); expected to change with use.

## 11. Frame mockup v1 and its FEATURE LIST (2026-11-26)

`reference_art/battlerom_ui/battlerom_frame_mockup.html` (published privately for Daniel as "BattleROM Frame Mockup"). Sample data;
the map is a flat stand-in for the 3D tabletop; every number is a stand-in.

WHY THIS LIST EXISTS (Daniel, 2026-11-26): the last mockup went wrong in the move to the live game because it "got rebuilt with
features missing" instead of being implemented exactly. So: the live build is checked against this list ITEM BY ITEM, and an item
is only dropped by Daniel's word. Each item names what to see or do. When the mockup changes, this list changes in the same commit.

Layout
- F1. Landscape: enemy column left, 1:1 map square centre (no header, no footer), friendly column right.
- F2. Upright phone: the same parts as a band above (enemy) and below (friendly) the square.
- F3. Left column: Menu button and "Turn N · Phase" at the top; enemy force title bar; enemy strip; Current Target line at the bottom.
- F4. Right column: friendly force title bar ("N to move / to fire"); friendly strip; Active Unit line with the Report button.
- F5. Strip chips: code, variant and name, small armor / structure / heat bars, TN|range box on enemies, a check on units that are
  done this phase, "prone" / "off" marks; outline for the active unit (blue) and the target (red).
Corners of the square
- F6. Top right: zoom in, zoom out, fit.
- F7. Bottom left: Clear and Undo, two buttons (Clear = drop the whole plan; Undo = one step back). Disabled when there is nothing.
- F8. Bottom left, above them: the mode button, shown only when the active unit has a mode to switch (demo: "Aim: Normal /
  Targeting computer" in the fire phase).
- F9. Bottom right: the context widget beside Commit.
Commit
- F10. Commit is HOLD to commit (fill shows progress, about 650 ms); a short tap says "Hold to commit". Fire! too.
- F11. Movement labels follow the plan: Stand still / Stay prone / Stand up / Walk / Run / Jump / Charge / Death from above /
  Careful stand; colour by mode (still grey, walk cyan, run yellow, jump orange). Second line: MP the plan costs, "then prone".
- F12. A ⚠ on Commit when the plan holds a KNOWN chance (water, standing, charge, DFA); its title lists them. Hidden hazards
  (the demo's minefield in 0913) give no warning and report when they trigger.
- F13. Fire phase: "Hold fire" (grey) with nothing assigned, "Fire!" (red) with N weapons and the aimed location; ⚠ when the
  projected heat is over the unit's heat limit.
- F14. A plan with a chance that fails is reported and the player decides again from that point (demo: a failed stand leaves the
  unit prone with its MP reduced and the same unit still to move). ENGINE CHANGE NEEDED (Section 10, "Found while recording").
Context widget
- F15. Movement: MP left of max, TMM of the plan, a small "heat N (capacity)" at the side (red over capacity), a hint line.
  Tap = Jump on / off (or Stand up for a prone unit). Long press = the inspector on the Move tab.
- F16. Fire: projected heat (capacity), heat now, spare or over. Over capacity it turns red and, with a coolant pod, offers
  "use coolant pod?" (tap toggles). Long press = the inspector on the Heat tab.
Placards
- F17. Border bars: top = armor, bottom = structure, each split at the centre (the unit's left side on the left half, right on
  the right), wearing in from the outer edge. Left edge = a heat scale. Right box = base to-hit number and range, on EVERY size.
- F18. Jewel at the top-right corner: red when any location's armor is gone or its structure is hit, amber when a location's armor
  is low.
- F19. Sizes: small (code only) and medium (code and variant) follow the zoom (world-size placards with a floor so they stay
  tappable); the selected unit gets an EXPANDED placard at a fixed screen size: name, how it moved, pilot G/P and hits, heat,
  condensed weapons ("2x ML"), the 'Mech-shaped armor diagram, and the buttons about that unit.
- F20. The TN|range box uses the active unit's PLANNED end hex and movement mode during the Movement Phase, so it updates as a
  move is drawn.
- F21. Buttons on placards (actions ABOUT that unit): Charge, Death from above (movement, in reach); Aimed shot on an immobile
  target, then a row of locations; with the targeting-computer mode on, the location row directly.
- F22. While the weapon ring is up, the target's placard docks as a compact card at the top of the square (the ring and an
  expanded placard do not fit together on a phone).
Targeting (fire phase)
- F23. Tap an enemy to target it. Repeated taps on one hex cycle: its enemy units in turn, then a building, then the ground, then
  round again. An empty hex needs two taps to target the ground (the first marks it). A toast says "target n of m".
- F24. A building or ground target gets its own card (hex, terrain, CF, TN|range) and a crosshair on the hex.
- F25. Long press a hex = the inspector on the Hex tab with "Target this hex" / "Target the building" / "Target <unit>".
Weapon ring
- F26. Weapon chips around the target in the ACTIVE unit's critical-table layout: LA, LT, (HD above / CT below), RT, RA columns.
  Chip: short name, location, TN, heat; green edge in range, dimmed out of range, red when assigned here, dashed yellow with
  "→ CODE" when assigned to another target.
- F27. Tap a chip = assign / unassign to the current target. Drag a chip onto another enemy (or a building) = split fire.
  Long press a chip = the inspector on the Weapons tab.
- F28. Menu option: weapons around the target / as a list on the left / drawer only (the Weapons tab has a Fire column).
Drawers ("wings")
- F29. Two drawers only, left and right: a wide, short arrow at the middle of each side edge; tap or flick it to open.
- F30. A drawer covers its half of the screen; its inner edge holds the reversed arrow (close) and a small forward arrow (cover the
  whole screen). Flick toward the edge closes, away from it covers all.
- F31. A tab row at the top; tap a tab, or flick the tab row up / down, to change the page; it stays on that page.
- F32. Each drawer remembers its page PER PHASE (saved on the device). Defaults: Movement: left Move, right Status. Weapon
  Attack: left Target, right Weapons.
Inspector
- F33. Long press (anything: a hex, a unit, a placard, a strip chip, the target line, the widget, a weapon chip) opens it over the
  TOP half of the screen, covering the columns' tops; its header is the Current Target line plus what was pressed.
- F34. It opens on the Hex tab ("what is in this hex, and what special actions may be available"), except the widget (Move or
  Heat), a weapon chip (Weapons) and the target line (Target).
- F35. Flick the header down = full screen; flick it up = close; a touch on the uncovered map ONLY closes it (no move, no target);
  × closes; Esc closes.
- F36. Report button = the inspector full screen on the Report tab.
Pages (one set of tabs for drawers and inspector)
- F37. Hex, Status, Move, Weapons, Heat, Target, Crits, Report. Status / Target: the armor diagram (armor, rear, structure; red
  outline = structure hit), pilot, heat, MP, state, weapons. Move: Jump, Go prone at the end, Stand up, Careful stand, Lateral
  shift (disabled: quads and tripods), Hull down (not built). Weapons: ranges, heat, mode selector, Fire column, ammo feeds with
  "feeds first". Heat: the scale with marks, the heat limit for Fire!, coolant pods, radical heat sink. Crits: the critical table.
Heat maps
- F38. Menu: "Where it can move", "Where it can shoot"; tap a unit for its map, a force's title bar for the whole force; both on =
  one combined threat envelope.
Menu
- F39. Look (System / SL-HIS Dark / SL-HIS Light), weapons display, heat maps, "Name every part" (labels each region), phase
  switch, phone-size frames (844×390, 390×844), reset.
Map gestures
- F40. Tap, long press (500 ms), one-finger pan, two-finger pinch, mouse wheel zoom; the browser's double-tap zoom is off.

Known tensions to judge on a phone (Claude's notes, not rulings):
- The ring covers much of a 390 px square; other enemies under it are reached through the enemy strip or by dragging a chip.
- Upright, the bands have spare height; it could go to a second chip row or a bigger square.
- The drawer arrows overlap the square's edges when upright.

## 12. The LAYOUT TABLE (Daniel's rulings, 2026-11-26, later the same day) — supersedes Section 11's layout items

Course correction (Daniel): mockup v1 "looks too much like a fresh rebuild". Start from the CURRENT play page and modify it. The MAP LAYER
TAKES THE WHOLE SCREEN; the UI goes on top of it, keeping the central 1:1 area clear unless a wing or the inspector covers it. The mockup
needs no real code (sample data, a stand-in map); the real map must work the same once the new UI is laid over it. Process: table ->
Daniel rules -> build exactly that -> screenshots -> only then fix tests against the agreed layout. (An attempt to run the real page in an
artifact and re-lay it out was scrapped by Daniel: "a blind alley".)

Sideways: enemy side = left panel, your side = right panel. Upright: bands above (enemy) and below (yours).

| # | Part | Sideways | Upright | Behaviour |
|---|---|---|---|---|
| 1 | Title bar | top of the left panel | top band | "BattleROM" drops out first. No Unit button. REC stays (live once time travel is built). Menu: tap = menu, long press = game options in the inspector |
| 2 | Menu | drops from the title bar | same | pop-up |
| 3 | Enemy strip | left panel | top band | arrows at both ends step the selection one unit along |
| 4 | LAST-CLICKED line | under the enemy strip | under the enemy strip | the last thing clicked (usually a hex or an enemy unit), with a button that opens the inspector on it (balances Report) |
| 5 | Zoom | top-right corner | right end of the top band | first to hide when space runs out |
| 6 | Weapons (fire) | around the target in the active unit's critical layout (default) | same | see below |
| 7 | Commit (Move! / Fire!) | bottom-right corner | bottom centre | hold to commit; label and colour follow the plan |
| 8 | Undo / Clear | on top of Commit | right of Commit | |
| 9 | MP / heat display | bottom-left | bottom-left | tap = Jump toggle; a second button beside it (room permitting) or a long press = the inspector with more actions (go prone ...); fire phase: the heat tracker |
| 9.5 | ACTIVE UNIT line | above your unit strip | above your unit strip | your active unit, and the Report button |
| 10 | Unit strip | right panel | bottom band | arrows at both ends; long press = the inspector on that unit's actions (heat maps ...) |
| 11 | Unit sheet (dock) | GONE | GONE | "This is what I'm trying to kill": the inspector and the wings show only when needed |
| 12 | Report | full screen over everything | same | |
| 13 | Context actions | on the target's placard (Aimed shot, Pick up club) | same | actions about yourself (Stand up) beside the MP display; only when legal |
| 14 | Attack arrows | map | map | active unit -> target: dashed / see-through while considering, solid when the attack is made; after commit it stays, muted, unless the attacker or target is selected; long press = the inspector with that attack's weapons and to-hit numbers |
| 15 | Wings | left and right edges | same | "still necessary" (rulings of Section 10) |
| 16 | Inspector | top half | same | Section 10 |

WEAPONS (row 6): default = the boxes around the target in the active unit's critical-table layout; they disappear when a hex is selected
but not targeted. NO fire toggles, NO select or mode buttons: tap a weapon = on / off. Colour = firing state: glowing green = ready,
glowing red = fired (set to fire), grey = out of range. The box is mostly transparent. Each box shows the ACCURATE current to-hit number
against the current target. Long press the weapon = the inspector on modes and ammo (or the fire-phase wing default shows it); long press
the to-hit number = the inspector with the exact to-hit calculation. A tint may show the range bracket. Option: the same boxes as a
scrollable list on the left.

Mockup of this table: `reference_art/battlerom_ui/battlerom_frame_mockup.html` version 2 (2026-11-26), the holotable mockup (v3.1) with
its play page replaced by this layout; published for Daniel at the same link as version 1. Its demo control "Name every part" labels each
region with its row number above. Waiting for Daniel's review before anything moves into the live page.

### 12a. Round 2 on the mockup (Daniel, 2026-11-26) — built into mockup version 2.1

- Action buttons (MP / heat, the extra button, Commit, Undo / Clear) are smaller, and may float over the map just above the Active unit
  line. Built: upright they float there; sideways they stay in the panels' bottom corners, smaller (Claude's reading; to confirm).
- WEAPONS have FIXED places on the screen (round the middle of the clear area), whatever the map is looking at. When one is turned on,
  the map scrolls to centre on the target being shot at. No location text on the boxes: their place says it.
- PHYSICAL ATTACKS work the same way: punches and pushes in the arm sections, kicks in the legs (built: legs under the side torsos;
  Push, a both-arms attack, is shown in the left arm column — to confirm).
- The map controls go to the upper left of the map area (they float there), which frees the central spot and moves the Active line back
  up a line.

### 12b. Round 3 on the mockup (Daniel, 2026-11-26) — built into mockup version 2.2

- Turn information goes to the upper right corner of the map area; Menu and REC are split out of the title bar, so the whole line moves
  up into the camera controls' line (built: one line along the top of the map area: camera controls, the turn box, REC, Menu; REC and
  Menu as icon buttons the size of the camera buttons so the line fits a 390 px phone). The title bar is gone.
- Weapon names: smaller font. Open: the longest abbreviation still recognisable (Claude: 5 characters covers LB10X, GAUSS, LRM20, ERPPC).
- Undo and Clear: icon buttons the size of the map control buttons.
- Action buttons look like buttons: rounded, raised, shiny; Commit has the "big red shiny button" feel.
- Weapon buttons must hold their own over a placard under them; placards step back when they are not the centre of attention (built:
  others at half strength, all of them faint while the weapons are up).
- Art: the hex bases' front side is marked (built: a light panel with a chevron on the front side, a white notch on the top edge).
- Heat display: no "spare" line; the format is "current heat (total dissipation): end of heat phase total", without labels.
- Wing tabs: open question whether they sit on the screen's sides or the map area's sides; they should look like the multiple-line
  grip art of the Lab's window sizing (built: line-grip tabs on the map area's edges).

### 12c. Round 4 on the mockup (Daniel, 2026-11-26) — built into mockup version 2.3

- The strip beside the phone's notch cannot be used by a page (the phone draws its status bar there), so Menu and REC get their own line
  ABOVE THE ENEMY ROSTER, with the BattleROM name. The turn information stays at the upper right of the map area.
- The heat display is labelled "Heat".
- Commit's label must contrast with its colour (built: dark on the light colours, white with a dark edge on red and orange).
- Sideways action buttons: fine where they are (the panels' bottom corners).
- PHYSICAL ATTACKS (rules checked in the library, Core Rulebook): one type of physical attack a turn, except that a 'Mech may punch with
  one or both arms (p.77, Multiple Physical Attacks); push needs both arms and no arm-mounted weapon fired that turn, against a 'Mech
  directly in front (p.83, and the errata clarification); an arm that fired a weapon that turn cannot punch (p.82); a kick uses one chosen
  leg whose weapons did not fire (p.81); only club, DFA, kick and physical weapon attacks reach a prone 'Mech at the same level (p.77).
  Built: Push shows in both arm sections and either lights both; choosing one type greys out the others (a second punch may join the
  first; a kick uses one leg); attacks that cannot be made are blacked out with the reason on a tap.
  OPEN: Daniel thought two punches cannot go to two targets. The library does not say so: punches are resolved separately, and a target
  in a side arc can only be punched by that side's arm (p.82), which implies the two arms may punch different targets. To check against
  MegaMek's source if Daniel wants it settled.

### 12d. Round 5 (Daniel, 2026-11-26) — built into mockup version 2.4

- PUNCHES: selecting one activates both. A secondary target is allowed: turn one punch off, choose the other target, and turn it on again
  there. Built generally: every weapon or physical attack remembers its own target; one aimed at another target shows dashed yellow
  with "-> NAME" and its own to-hit number, and a tap brings it to the current target; Commit records one attack per target. (Arcs are
  not modelled in the mockup: the real page must only offer the side-arc target to that side's arm, Core p.82.)
- Title line: Menu on the left, BattleROM in the centre, REC on the right.

### 12e. Round 6 (Daniel, 2026-11-26) — built into mockup version 2.5

- Commit's letters get a stronger border (built: a hard outline, dark letters with a white edge on the light colours, white letters with
  a black edge on red and orange).
- The white hex grid lines fade as the map zooms out (built: by the size of a hex on the screen).
- The open wing's grip matches the closed tab (the line grip, with a small arrow for the way it goes).
- The mockup's source is kept in `reference_art/battlerom_ui/frame_build/` (README there).

## 13. Next ideas (Daniel, 2026-11-26): NOT in the mockup, to settle before or after the build

- FEEDBACK: sounds and vibration (Daniel asked for an opinion; see Claude's note below).
- ATTENTION FOCUSING, enemy movement: the camera centres on (or at least tilts toward) an enemy unit as it moves; the move plays step by
  step with a trail behind it; then the camera returns to where the player had it. Purpose: the player sees what the other side does and
  keeps their bearings. Speed: Daniel's first thought ".2 to .25 hexes moved per second" (Claude reads it as 0.2-0.25 SECONDS per hex,
  4-5 hexes a second; to confirm).
- ATTENTION FOCUSING, firing: the shooting enemy is focused, then the attack arrow is followed to its target, and a brief pop-up on the
  map says what was fired and the to-hit numbers.
- ATTACK PATH: the hexes along an attack's line that change the to-hit number (woods, water, etc.) are highlighted.
Claude's notes: vibration works on Android browsers but not on iPhones (Safari has no vibration call); sounds can be made in the page
(Web Audio, no sound files to license) and must start off or after the first tap; keep them few (commit, hit, miss, fall), with a Menu
switch. The enemy-turn replay should be skippable (a tap fast-forwards) and its speed a Menu option.

### 13a. Saved to the to-do list (Daniel, 2026-11-26): NOT in the first build
- VIBRATION and SOUNDS (feedback; see Claude's note above).
- REPLAY SPEED, VARIABLE: longer movements spend less time per hex.
- MOVEMENT ANIMATION: the hex base actually moves: it hops from hex to hex along the path, and jumps over the map when the unit jumps.
- TO-HIT TERRAIN ON THE ATTACK PATH: the hexes along an attack line that change the to-hit number are highlighted.
- (Still on the list from Section 13: attention focusing on enemy moves and shots, the shot pop-up with the to-hit numbers.)

## 14. FEATURE CHECKLIST: frame mockup version 2.5 -> the live play page (2026-11-26)

THE BUILD TARGET. Daniel, 2026-11-26: "make a checklist of every feature we currently have in place" before building it for real.
Source: `reference_art/battlerom_ui/battlerom_frame_mockup.html` version 2.5 (published link: claude.ai/artifact/G2EzAvnfzpbV4cvLNHKULo;
source in `reference_art/battlerom_ui/frame_build/`). The live build is checked against this list ITEM BY ITEM (screenshots upright
844x390 / 390x844 and desktop); an item is only dropped or changed by Daniel's word; a change to the mockup changes this list in the same
commit. Where the mockup used sample data or stand-in numbers, the live page uses the ENGINE's (its questions, its to-hit lists, its
heat table). Supersedes Section 11's F-list (mockup version 1). Section 12 is the layout table these items come from.

### A. Layout
- [x] A1. The map layer fills the whole screen; everything else lies on top of it.
- [x] A2. Sideways: your enemy's side in a panel on the LEFT, yours on the RIGHT; each panel (long side - short side) / 2 wide, at least
      168 px; the square between them is the clear area.
- [x] A3. Upright: a band ABOVE (enemy side) as tall as its parts, a band BELOW (your side); the action buttons float over the map just
      above the Active line; the clear area is between.
- [x] A4. The camera's fit and focus frame the CLEAR area (not the whole screen); when the bands differ in height the image centre is
      moved to the clear area's centre (the 3D camera's view offset), so taps and drawings still line up.
- [x] A5. Panels are see-through enough to show the map behind them.
- [x] A6. Room for the phone's notch / status bar and home bar (upright: top; sideways: the notch side).
- [x] A7. NO UNIT SHEET (the dock is gone): its jobs are in the inspector and the wings.
### B. Title line (above the enemy roster)
- [x] B1. Menu on the LEFT, "BattleROM" in the CENTRE, REC on the RIGHT.
- [x] B2. Menu: tap = a drop-down under it (weapons layout, heat maps, Report, game options); long press = the inspector on Options.
- [x] B3. REC: a live-looking button that says time travel is not built yet (until it is).
### C. Enemy side
- [x] C1. Enemy strip: one chip per enemy (short name, condition %, a shut-down mark); outline for the last clicked and for the target;
      scrolls sideways; ARROWS at both ends step the selection one unit along (attack phases: the target; Movement: the Last line).
- [x] C2. LAST line under the enemy strip: the last thing clicked (a unit: name, model, to-hit, range, state; a hex: number, level,
      terrain, "targeted"); an INSPECT button opens the inspector on it.
- [x] C3. Sideways only: the MP / heat display and the extra button at the bottom of the left panel; the weapon LIST option fills the
      left panel's middle.
### D. The map's top line (over the map)
- [x] D1. Camera controls at the top LEFT of the map area: zoom in, zoom out, fit, tilt.
- [x] D2. Turn information at the top RIGHT: "Turn N · Phase · n to move / fire / attack".
### E. Your side
- [x] E1. ACTIVE line above your unit strip: the active unit (name, model, prone) and the REPORT button (full-screen combat report).
- [x] E2. Unit strip: one chip per unit (name, model, prone, a condition bar, a check when done this phase), outline on the active one,
      done ones dimmed; ARROWS at both ends step through the units not yet done.
- [x] E3. Long press a chip (either strip) = the inspector on that unit (Unit tab: heat map switches and other unit actions).
- [x] E4. Sideways: Undo and Clear above Commit, bottom right of the right panel.
### F. Action buttons
- [x] F1. Upright: one floating row over the map, just above the Active line: MP / heat display and the extra button (left), COMMIT in
      the CENTRE, Undo and Clear (right). Sideways: the panels' bottom corners (MP / heat bottom left, Commit bottom right).
- [x] F2. They look like buttons: rounded, raised, glossy, pressed in when tapped; Commit is the "big shiny button".
- [x] F3. COMMIT is HOLD to commit (about 650 ms, a fill shows progress); a short tap says "Hold to commit". Labels follow the plan:
      Movement: Stand still / Stay prone / Stand up / Stand + Walk|Run / Walk / Run / Jump / Charge; Weapon Attack: Hold fire / Fire!;
      Physical Attack: No attack / Attack!; after: Moved / Fired / Attacked (disabled). Second line: the MP the plan costs, or how many
      weapons / attacks (and the aimed location).
- [x] F4. Commit colours: grey (stand still), cyan (walk, stand up), yellow (run, charge), orange (jump), red (fire, attack). The label
      has a hard outline: dark letters with a white edge on the light colours, white letters with a black edge on red and orange.
- [x] F5. A ⚠ on Commit when the plan holds a KNOWN chance (a stand, water and other Piloting rolls on the path; fire: heat over the
      unit's heat limit); hidden hazards give no warning.
- [x] F6. MP / heat display, Movement: "MP left / max", TMM, "Heat current (dissipation): end-of-heat-phase total", a hint line (not in
      the floating row); TAP = Jump on / off (a jump-capable unit that is not prone); LONG PRESS = the inspector on Move.
- [x] F7. MP / heat display, attack phases: "Heat current (dissipation): end total" (labelled Heat, no other labels); over capacity it
      turns red and a tap offers a coolant pod; LONG PRESS = the inspector on Heat.
- [x] F8. The extra button (⋯) beside it opens the inspector with more actions (Move; Weapons in the attack phases). For a PRONE unit
      in Movement it is the context action "Stand up" (a toggle).
- [x] F9. UNDO (↶) and CLEAR (✕): icon buttons the size of the camera buttons; disabled when there is nothing to undo; Undo = one step
      back (the last waypoint, the stand, the jump; the last weapon turned on); Clear = the whole plan / every weapon. Esc: closes the
      inspector or a wing, otherwise Undo.
### G. Movement
- [x] G1. Tap a lit hex = a waypoint (walk / run / jump reach coloured; route, facing arrows) - the engine's reach and route.
- [x] G2. A prone unit: tapping a hex adds Stand up first (and says so).
- [x] G3. A plan with a chance that FAILS is reported and the player decides again from that point (a failed stand: the unit stays
      prone with fewer MP and is still the one to move). ENGINE CHANGE NEEDED (Section 10, "Found while recording").
- [x] G4. Charge and Death from above: buttons by the last-clicked enemy when it is in reach (actions ABOUT that unit live by it);
      they plan the move and Commit says Charge.
- [x] G5. Go prone at the end of the move (inspector Move tab).
### H. Targeting (attack phases)
- [x] H1. Tap an enemy (on the map, its card or its chip) = the target; the camera frames the attacker and the target.
- [~] H2. TAP CYCLE on one hex: its enemy units in turn, then a building, then the ground, then round again ("target n of m").
- [~] H3. An empty hex needs TWO taps to target the ground; the first only selects it (the Last line) and the weapons step aside.
- [~] H4. Long press a hex = the inspector on Hex with "Target this hex" / "Target the building" / "Target <unit>".
- [x] H5. When an attack phase starts, the target is the nearest enemy.
### I. Weapons (Weapon Attack Phase)
- [x] I1. FIXED PLACES on the screen round the middle of the clear area, whatever the map is looking at, in the ACTIVE unit's
      critical-table layout: LA, LT, head above / centre torso below, RT, RA; leg weapons under the side torsos.
- [x] I2. Each box: a short name (5 characters at most) and the accurate to-hit number; NO location text; nearly solid so it reads over
      a placard; colour = state: glowing GREEN ready, glowing RED on, GREY out of range, dashed YELLOW "-> NAME" when aimed at another
      target; a tint for the range bracket (medium amber, long red).
- [x] I3. TAP = on / off (no other buttons); turning one ON scrolls the map to centre on its target.
- [x] I4. LONG PRESS the box = the inspector on modes and ammo; LONG PRESS the to-hit number = the inspector with the exact to-hit
      calculation.
- [x] I5. Each weapon keeps ITS target (split fire); a tap on one aimed elsewhere brings it to the current target.
- [x] I6. Menu option: the same boxes as a list on the left (sideways: the left panel; upright: above the Active line).
- [x] I7. AIMED SHOT: a button under the boxes when the target is immobile (weapon fire only); then a row of locations; Commit shows
      the aimed location. (A targeting computer's aimed shot is a mode switch on an inspector tab.)
- [x] I8. Commit makes one attack per target.
### J. Physical attacks (Physical Attack Phase), the same boxes
- [x] J1. Punch in each arm section, Push in BOTH arm sections, Kick in each leg place.
- [x] J2. One TYPE a turn (Core p.77): picking another type clears the rest; the others grey out. Selecting one PUNCH activates both;
      turning one off turns off only that arm; a punch may go at a SECONDARY target (off, pick the other target, on again). Push lights
      both arms. A kick is one leg.
- [x] J3. Attacks that cannot be made are BLACKED OUT, and a tap says why: an arm that fired a weapon cannot punch (p.82); push after
      any arm-mounted weapon fired (p.83); a leg that fired cannot kick (p.81); punch and push cannot reach a prone 'Mech at the same
      level (p.77); a hex is no physical target. (Live page: the engine's arcs too; a side-arc target only for that side's arm, p.82.)
### K. Attack lines
- [x] K1. Active unit -> target: DASHED and see-through while considering, SOLID once anything is on.
- [x] K2. Committed attacks stay on the field, MUTED, unless the attacker or the target is the one selected (then highlighted).
- [x] K3. A label on the line (the range; "▸ n" on a committed one): LONG PRESS = the inspector with that attack's weapons and to-hit
      numbers.
### L. Map pieces
- [x] L1. Placards step back when they are not the centre of attention (active unit, target, last clicked): half strength; all faint
      while the weapons are up.
- [x] L2. Tap a placard = select that unit; LONG PRESS = the inspector on its hex.
- [x] L3. The hex base's FRONT side is marked: a light panel with a chevron, and a white notch on its top edge.
- [x] L4. The hex grid lines FADE as the map zooms out.
- [x] L5. A long press anywhere on the map (a unit or a hex) = the inspector on that hex.
- [x] L6. In the attack phases, every enemy shows its to-hit number over it.
### M. Wings (the side drawers)
- [x] M1. Two wings, left and right; their tabs sit on the MAP AREA's edges at mid height, drawn as the Lab's line grip with a small
      arrow.
- [x] M2. Tap or flick the tab = the wing opens over half the screen; its inner edge has the same grip: the reversed arrow closes, the
      small one covers the whole screen; a flick toward the edge closes, away from it covers all; from full, a tap steps back to half.
- [x] M3. A row of tabs; tap one, or flick the row up / down, to change the page; it stays. Each wing remembers its page PER PHASE.
      Defaults: Movement left Move, right Unit; Weapon Attack left Target, right Weapons; Physical Attack left Target, right Attack.
- [x] M4. Opening a wing closes the inspector.
### N. Inspector
- [x] N1. Covers the TOP HALF (title line and strips included); its header is the current target line (attack phases: target, to-hit,
      range) or the last clicked; a second line says what it shows and what opened it.
- [x] N2. Opens on the HEX tab ("what is in this hex, and what special actions may be available"), except: MP / heat display -> Move or
      Heat; weapon -> Weapons; to-hit number -> To-hit; strip chip -> Unit; Menu (long press) -> Options; Inspect -> Unit or Hex; an
      attack label -> Attack.
- [x] N3. Flick the header DOWN = full screen; flick UP = close; a touch on the uncovered map ONLY closes it (no move, no target); ×
      closes; Esc closes.
- [x] N4. Tabs (one set, shared with the wings): Hex, Unit, Target, Move, Weapons, To-hit, Attack, Heat, Options. Hex: level, terrain,
      range, what is in it, special actions (target this hex / the building / a unit; plan a move here). Unit / Target: tons, MP, heat,
      state, armor and structure by side; Unit adds the heat map switches. Move: Jump, Go prone at the end, Stand up, Careful stand
      (shown when legal), lateral shift / hull down / climb when legal. Weapons: modes, ammo feeds ("feeds first"). To-hit: every
      modifier and the total. Attack: the planned or a committed attack's weapons and to-hit numbers. Heat: now / this turn, the heat
      scale, the heat limit for Fire!, coolant pods. Options: game options (weapons layout, heat maps, the rest of the real page's
      options).
### O. Report, menu, messages, phases
- [x] O1. The combat report covers the whole screen; Close.
- [x] O2. Short messages (toasts) at the top of the clear area.
- [x] O3. Movement -> Weapon Attack -> Physical Attack, each unit in turn; the next unit becomes active on its own.
### Build status (2026-11-26, Claude, session 37): BUILT on the live play page
Built in `engine/lab/web/play.html`, `play.js`, `mapview.js`, `tabletop.js`; [x] = built and seen working in screenshots (upright 390x844,
sideways 844x390, desktop 1280x800) and in the website check that plays a whole battle by taps (`tests/check_web_play.py`). [~] = built as
far as the engine allows:
- H2 / H3 / H4: the tap cycle steps through the enemy units in a hex, an empty hex needs two taps, the Hex page offers "Target this hex" /
  "the building", BUT the engine cannot attack a hex or a building yet (no building damage, no hex targets): the second tap and those
  buttons say so. A rules feature for Daniel to call (backlog).
Engine changes the build needed (human units only; the 68 reference battles are unchanged):
- G3: a person's failed stand is ONE roll; the stand question comes back with the MP left ("again", "spent"); after a fall partway
  through a move the person is asked whether to stand (Core p.51). `BotSet::decides_each_stand`, `piloting_rolls::resolve_stand_attempt`,
  `orchestrator::stand_deciding` / `prone_mp_left`.
- J: the physical question lists every adjacent enemy's attacks (`attacks`, with limbs) and the usual ones that cannot be made with the
  reason (`blocked`, pp.77, 81-83); the answer `{"attacks": [{kind, name, target}]}` may send a punch at a secondary target
  (`PhysOption::target`). One type a turn except punching (p.77) is checked.
- I7: a person's aimed shot at an immobile target (`PlayerChoices::aimed`, `attack_resolution::person_aim`; the preview says `aimable`).
- The unit list carries `sinks` (heat dissipation) for the heat display.
Choices made in building (not rulings; Daniel may change them): the heat limit for Fire!'s warning starts at 4 (the heat scale's first
effect is at 5); questions with words and no place on the map (MASC, spotting, TAG, End Phase switches, deployment, battle over) show in
a small question box at the top of the clear area; the hazard confirmation card is gone (the warning on Commit plus the hold replace it;
a tap on Commit lists the chances).

### Mockup only (NOT to build)
Demo controls, "Name every part" labels, sample forces and the demo set-ups (a prone 'Mech, a shut-down enemy, a second enemy in reach),
stand-in to-hit numbers and heat marks, the phone frames, the heat map switches that draw nothing.
