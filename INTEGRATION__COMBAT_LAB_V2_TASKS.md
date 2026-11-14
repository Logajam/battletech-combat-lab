# Combat Lab round 2 - Daniel's improvement list as tasks (2026-11-14, session 26)

Source: Daniel's message of 2026-11-14 (Lab walk-through). Sheets continue the CL numbering of
`INTEGRATION__COMBAT_LAB_SPECS.md`. Pages live in `engine/lab/web` (index.html, lab.css, lab.js; ~1,000 lines),
the server in `engine/lab/src` (main.rs, catalog.rs, runs.rs).

**Tier tags.** `[S]` Sonnet can build it from this sheet. `[O]` Opus (design judgement while building).
`[TOP]` recommend a higher-tier model look at it: it touches engine results, a rules call, or a design whose
mistakes would stay hidden. Art/page-only work follows CLAUDE.md's "visual assets" rule (run only the lab's own
checks); anything touching `engine/core` runs everything (`python tests/run_checks.py`).

`OPEN Q` = waiting on Daniel (questions are listed at the bottom).

## Suggested order

1. CL16 (weapon firing order) first and alone: it changes engine results, so it needs its own reference-log
   update and a review before the rest piles on. `[TOP]`
2. CL17 (firing-phase log rewrite) next: same engine area, and Results/Replay both read it.
3. CL11-CL15 (Lab pages: window, units, filters, map, options): page work, little engine risk, can run in parallel.
4. CL18-CL20 (Results, unit stats, save file), then CL21 (heat maps, needs CL6/CL7 first).

---

## Lab pages

### CL11. Lab behaves like a normal window  `[S]`  OPEN Q1
A browser tab can't be dragged or resized by a page; the browser owns it. Options: (a) launch the Lab in its own
app-style window (`combatlab` opens Chrome/Edge `--app=URL`, or `window.open` with `resizable`), which the user
can move and resize like any program; (b) make the layout fully responsive so any size works; (c) Windows 3.x style
floating, resizable panels inside the page. Plan: do (a)+(b) now, (c) only if Daniel wants panels he can arrange.
Done when: the page is usable from ~900 px to full screen with no horizontal scroll, and `combatlab` opens it in an
app window where a browser is found (falls back to a tab).

### CL12. Units tab rebuild  `[S]`  OPEN Q2
- Unit Browser buttons (Add selected, From file, and the other action buttons) move to the TOP of the list so they
  don't shift as units are added.
- Top row across the Units tab: Battle (number of sims), Estimated Runtime, Run Simulation.
- Three-column layout: odd teams (1, 3, 5...) on the right, even teams (2, 4...) on the left, the Unit Browser in
  the centre. Needs a rule for 3+ teams (stack within each side); the page must never assume Red and Blue.
- Weight-class icons (Light, Medium, Heavy, Assault) beside every listed unit, in the browser and in the team
  lists, as a "handle" to grab; drag from browser to team (drag and drop already specified in CL4).
- Visual assets: icons drawn as small inline SVG (no rulebook art; original shapes only).

### CL13. Unit Browser filters on par with Mekbay  `[O]`  OPEN Q3
Mekbay-style filtering: text search, unit type, tech base, era / year, rules level, source book, weight class and
tonnage range, BV range, walk/run/jump MP, armor and structure points, heat sinks, role, weapon and equipment
filters (has / count / min damage), sort by any column, saved filters. Work: (1) list which fields the `.mtf` files
and `catalog.rs` already carry, (2) extend `catalog.rs`'s index (built once at server start) with the missing ones,
(3) the filter UI. Faction / availability filters need data the `.mtf` does not hold (see Q3).

### CL14. Map tab  `[O]` (UI `[S]`)  OPEN Q4 Q5
1. **Full-map preview** under the board chooser (small canvas of the whole board).
2. **Elevation colour contrast** like MegaMek (ramp by level; water/woods/buildings keep their own overlay).
   Drawn by the same function for the preview and the replay board.
3. **Starting zones.** Per team: a 3x3 clickable grid (N NE E SE S SW W NW + Center). Highlighting the 8 outer
   boxes = Edge; all 9 = Anywhere; any subset = those zones (Random picks one of the chosen zones per team).
   Center and Walk-on (a check box beside the grid) switch each other off.
4. **Placement method** per team: Placed on board / Walk on.
5. **Zone assignment** (set-wide dropdown): Fixed (a team keeps its own zone every battle), Rotating (battle k:
   team i takes the zone of team i-(k-1), wrapping; 2 teams: swap each battle), Random.
6. **Map cycle list:** an ordered list of boards; battle k uses board ((k-1) mod length). Single board = today.
Engine side: scenario setup must accept per-team zone set, walk-on flag, and per-battle board; the chosen board and
zone go into the battle's record (CL18). `[TOP]` reviews the engine part: deployment and walk-on entry touch
battle start for every set, and the reference battles must stay identical with the defaults.

### CL15. Options tab: folders, search, greyed-out future features  `[S]`
- Sub-tabs or collapsible folders: **Game setup** | **Bot features**, and under Bot features one folder per bot
  (Gladiator, Princess, Hydra, Legate).
- Every option gets a registry entry: name, description, bot, `implemented: true/false`. Unimplemented ones are
  listed greyed out with a "not active yet" tag and can't be toggled.
- A search box filters options across all folders (matches name, description, bot) and opens the folders that
  match.
- Source of truth: the OPTIONAL RULES section of the config plus the bot feature switches (PROJECT_MAP Section 6);
  generate the registry rather than typing it twice.

## Results and recording

### CL16. Weapon firing order  `[TOP]`  OPEN Q6
Daniel: bots fire weapons in listed order; they should fire the weapon dealing the most damage to one location
first, then descending by cluster size (AC-20 before SRM-6 even if the unit lists the SRM-6 first).
First CHECK how the engine orders a unit's attacks (candidates: `attack_resolution.rs`, `orchestrator.rs`,
`bot_targets.rs`; the Python is frozen, the Rust is the standard). Then implement a sort key: (damage that lands
in one location per hit, desc), then (cluster size / number of hits, desc), then listed order as the tie-break.
Because order changes which locations die first, it changes results everywhere: reference logs get `--update`d,
recorded in the Change Record, and an A/B on the same seeds (`ab_batches.py`) goes to Daniel. A new bot decision
gets a PROJECT_MAP Section 6 row, and it must reach `bridge.rs`. Higher tier because a wrong order key is a quiet
bias in every battle ever run.

### CL17. Firing phase log rewritten, MegaMek style  `[O]`  OPEN Q6
Order: first unit to fire; each weapon in firing order; on a hit, the hit's result immediately (location, damage,
armor/structure gone, crits, transfers) before the next weapon; then the next unit. At the END of the phase, the
PSRs one by one: unit, reason, target number, roll, result, and the consequence of each failed roll (fall, damage,
pilot damage). Needs the engine to record events in resolution order (history.rs) and the Replay log panel to read
them; Results' text logs (`keep logs`) use the same lines. Check: a fixture's total damage per unit is unchanged by
the rewrite (log-only change); only CL16 changes results.

### CL18. Results: causes, filters, and a query builder  `[TOP]` for the design, `[S]` for the UI  OPEN Q7
- Add a **cause list** to outcomes, with Push (off-map by push) among them; current causes audited from the engine
  (destroyed, retreated, pushed off map, ejected, shutdown, etc.).
- **Query builder:** chain conditions, e.g. "3+ units suffered a gyro hit in the same turn" = event `gyro_hit`,
  grouped by turn, count >= 3, scope any turn. Needs a compact **event table** recorded for every battle (turn, phase,
  unit, event kind, detail), so a query is a filter over data already kept and nothing new has to be re-run.
- Armor % and structure % reported separately (per unit and per team) everywhere they show now as one number.
- Entry point and map recorded per battle and filterable (needs CL14).
- Higher tier because the event catalog is the thing nobody can fix after the run: an event not recorded is gone.

### CL19. Individual unit statistics  `[S]`
Results gets expandable folders: team > unit (by name + slot) > numbers (survival, damage dealt and taken, armor %
and structure % left, kills, weapons fired and hit rate, heat, falls, crits taken). Aggregated across the set, with
the per-battle values behind a second expand.

### CL20. Save and share a run as a file  `[S]`  
"Save run" writes one file (zip: setup JSON, per-battle results, seeds, crash records, event tables, optionally
histories; never rulebook text) and "Open run" loads it. Meant for sending to Claude for bug hunting. Crashed
battles keep their seed and the situation (setup + seed + turn) so they can be replayed from the file, and show in
Results with a "replay crash" button (builds on `trial_records/`, which already keeps crashes by seed).

### CL21. Replay heat maps of bot thinking  `[TOP]`  OPEN Q8
Selecting a team shows the combined map; selecting a unit shows only that unit's share. Needs CL6 (battle restored
from a saved state, `Opus or higher`) and CL7 (analysis overlays, `analyze(seed, step, unit, bot, what)`), then the
drawing. Which bot map first is Daniel's call (Q8). Analysis must not change or draw dice from the battle. Not
started until CL6/CL7 exist; scoped here so Daniel can see the dependency.

---

## Questions for Daniel

1. **Window (CL11).** A browser tab can't be dragged or resized by a page. Do you mean (a) the Lab opens in its own
   program-style window you can move and resize (my pick), (b) just resizes sensibly, or (c) windows inside the page
   you arrange yourself?
2. **Units layout (CL12).** Odd teams on the right and even on the left, as written (so Team 1 on the right, Team 2
   on the left)? And does the centre Unit Browser stay open all the time, or open when you press a team's Add?
3. **Filters (CL13).** Mekbay can filter by faction and era availability, which the `.mtf` files don't hold. Is
   filtering by the era/year/tech base/rules level written in the file enough, or do you want faction availability
   too (MegaMek has that data; I would pull it from its source and credit it)?
4. **Starting zones (CL14).** Is the zone set per team (each team has its own 3x3 grid), with the placement method
   per team, and only the Fixed / Rotating / Random dropdown set-wide? And does Random re-pick every battle?
5. **Map cycle (CL14).** Cycle in list order, or also a random-from-list option?
6. **Firing (CL16-17).** The Core Rulebook has all of a phase's fire resolve at once; MegaMek resolves it one weapon
   at a time with a result per weapon. I'll follow MegaMek's order for the log and for who dies first. Is that right,
   and should a unit destroyed earlier in the phase still fire (simultaneous, as the book) or not (as MegaMek's order
   would allow)? Tell me which.
7. **Event recording (CL18).** I'd rather record a standard catalog of events for every battle (cheap, small) than
   ask you to pick what to watch before each run. Okay? Names you want from day one: push off map, gyro hit,
   engine hit, cockpit hit, fall, PSR failed, ammo explosion, limb lost, shutdown, ejected.
8. **Heat maps (CL21).** Which first: Princess's team heat map, Gladiator's move score per hex, or Hydra's price per
   hex?
