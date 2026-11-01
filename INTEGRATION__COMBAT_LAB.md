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

- **Procedural tokens - Daniel's design (2026-10-31):**
  - **Look.** The unit's name is hashed to pick features and cosmetic detail
    (silhouette family from the chassis name so variants look related;
    cosmetics from the full model name). Weapon and equipment hardpoints come
    from the unit's real data, location by location. Tonnage and armor loadout
    set size and bulk.
  - **Overrides.** A named-unit override list beats the hash, e.g. "Timber Wolf:
    digitigrade legs, flexible arms, over-the-shoulder missile racks, ovoid
    body". Keep it a plain data file Daniel can read and edit.
  - **Outputs.** Top-down token, front standee, rear standee; 3D standees later.
  - **Art language.** Daniel wants the look to stay close to the MWO models
    and the Unit Recognition Guide posters; he will find reference material.
  - **Claude's notes.**
    - Build one parametric part model per unit (JSON: body, legs, arms,
      hardpoints, scale), then render it three ways: top-down, front, back (SVG,
      so it fits the HTML front end and scales cleanly); the later 3D view
      reads the same model. Overrides edit the part model, not the pictures.
    - Hardpoints are real data: the `.mtf` lists equipment by location, so
      arm, torso and head weapons can sit where the unit carries them.
    - MWO models and the poster art are copyrighted. Use them as reference
      for proportions and style only; the generator draws original shapes.
      Notes on a design's look go in the override file with the unit named.
    - Stage 1: plain shapes, correct footprint, readable facing. Detail comes
      after the pipeline works.

  - **Hardpoint placement (Daniel, 2026-10-31).** A unit file's critical
    location says only the coarse zone; slot order is not geometry (small
    weapons listed after a big rifle may be drawn on a shoulder turret). So:
    data gives the zone and rear-facing; weapon class, size and count pick a
    mount style (arm barrel, shoulder rack, torso pod, turret, aperture); the
    hash and overrides settle the arrangement. Each hardpoint in the part
    model keeps an overridable mount style.
  - **Option list first.** Draft a short parameter vocabulary (chassis, legs,
    torso, head, arms, shoulders, back, bulk), survey `data/meks.zip` with a
    contact sheet, add values only where a unit looks wrong; overrides are
    filled in later, by exception. Daniel is willing to spend cycles on this
    ground work (2026-10-31).

- **Unit library survey (2026-10-31, `tools/survey_mtf.py`; rough counts).**
  4,227 `.mtf` files (not 65). Config: biped 3,026 + biped omni 1,006, quad 148,
  LAM 23, tripod 11, QuadVee 13. Tonnage 20-100 mostly (30t 387, 50t 426,
  100t 134; a few 10t, 130t, 200t). Tech base: IS 1,893, Clan 641, mixed 134.
  Jump MP 0 on 1,618 (the rest 2-8). Weapons by zone: arms ~10,400, side
  torsos ~8,500, center torso 1,636, head 950, legs ~190; rear-facing only 35.
  Class: energy 13.5k, missile 4.3k, ballistic 3.0k.
  **Useful free signal: arm actuators.** Per arm: hand 3,548, lower arm only
  2,135, upper arm only 2,449 (upper-only = a gun-pod arm). So "hand / forearm /
  pod arm" comes from data, not the hash. Omnimechs (1,046) have pod-slot items,
  which suggests per-config looks. Findings: parameters needed beyond the first
  list are LAM / QuadVee transform modes and tripod (three legs); a handful of
  units carry no cockpit in the head (48), so head position can be read from data.

- **Token scale (Daniel, 2026-10-31).** The MWO scale-reference chart (labelled
  silhouettes, front + side, by weight class) is the art-language reference
  for proportions only; its own scale is unreliable. Rescale every reference
  silhouette to the curve below before using its proportions.
  **Drawn height matches the rules height (Daniel: in the art, so a 3D camera
  behind a mech sees what line of sight sees).** Rules (`pathfinder/los.py`,
  Core p.57, p.240): normal 'Mech 2 levels standing, 1 prone; superheavy
  (over 100t) 3 standing, 2 prone. Cube-square law inside each band, never
  above the rules height: normal = 2 x (tons/100)^(1/3) (20t 1.17, 35t 1.41,
  50t 1.59, 75t 1.82, 100t 2.00); superheavy = 3 x (tons/200)^(1/3) (105t 2.38,
  200t 3.00). Width and depth scale likewise; armor and loadout add bulk.
  **Decided (Daniel, 2026-10-31):** the STANDEE (card + base) is always the
  rules height - 2 levels, 3 for a superheavy - and the 'Mech drawn on it is
  scaled by the curve above (a light 'Mech is 1.15-ish levels tall on a 2-level
  card, empty above). Selection, hill clipping and LOS checks use the card;
  the figure is only the art. Quirk: behind a level-1 hill the camera shows a
  sliver of a light 'Mech where the rules say visible; mark it with an LOS line
  or highlight.

- **Token sheet v1 review (Daniel, 2026-10-31; sheet = first pass, 26 units).**
  Verdict: "wooden block golems more than mechs"; Thunderbolt and Stalker came
  out surprisingly accurate, Jenner a nice design. Needed: more distinctive
  features and shapes.
  *Archetypes to build around:* humanoid, bird walker, dog, lizard, Martian
  (tripods are their own thing). "Brick wall is what we got in abundance."
  *Bugs found in v1:* left / right mirrored between the front view and the top
  view (Awesome: PPC on opposite arms); a weapon dot drawn at different sizes in
  different views; top view shows no weapon direction; a stray energy weapon on
  the Awesome's rear view; cockpit colour differs top v front; jump jets
  disagree between rear and side views (Wolverine) and the outermost need a
  firmer attachment; quad side view draws 8 limbs (Scorpion); arms drawn in
  front of and behind the legs at once (Cyclops); torso looks, top v side and
  front v rear, disagree (Mad Cat); an ovoid torso that is nearly a sphere
  breaks the joints (Griffin); the heat-sink fin bars on the rear read as
  nothing (the "double line": they were the fins, one bar per 6 sinks).
  *Proportion:* far too blocky and too deep from the side; legs too thick
  (Hunchback); humanly proportioned by default, skinny-and-deep only as an
  option; width must follow the weight class and chassis family (Flea and Locust
  should match; Zeus got too wide), not accumulate; side views look about to fall
  forward (centre of gravity not over the legs): give the limbs a dynamic pose,
  e.g. mid-step; squat and wide is an option (King Crab); a slim front with more
  depth is an option (Raven); weapon sizes should be fixed, so they look larger on
  smaller mechs.
  *Joints and head:* knees, elbows (general), a neck (Commando); head mount
  options: built into the torso (Flea), front, top, full head, plus an OFFSET
  modifier (especially with a large weapon in a side torso); different head
  shapes (Shadow Hawk).
  *Body and legs:* legs on the sides of the torso, or on a hips section the upper
  torso twists around; shoulders that extend outward before the arm; three torso
  patterns (left / centre / right torso are three locations to show).
  *Arms:* weapon-pod arms (Jenner, Catapult, Stalker: a small pod when the
  weapons are small; big arms only where there are hands, "for beating people");
  arms need not be symmetrical.
  *Weapons:* pods need not sit above the shoulder (also on hips, e.g. a narrow
  body with arms spread); missile pods read by salvo size (how many missiles
  at once); Atlas shows weapons need not go over the shoulder. Daniel's guess
  that hand units seldom carry over-the-shoulder weapons is ART, not data:
  survey of 4,043 non-quad units (2026-10-31): torso missiles on 35% of
  two-hand, 38% of one-hand and 33% of no-hand units; torso ballistics 15% / 7% /
  12%; torso energy 43% / 43% / 42%. So hands do not predict torso weapons in the
  files; any rule is a style choice.
  Plan: v2 = a vocabulary of archetypes, joints, head mounts and mount styles
  above; fix the bugs first; re-render the same 26 units for comparison.

- **Reference tags from the MWO chart (Claude's reading, 2026-10-31).**
  `data/token_reference_tags.json`: 32 chart units tagged in the token vocabulary
  (archetype, torso, head mount and shape, shoulders, note, confidence). Coarse:
  the chart's silhouettes are about 100 px tall, so most are "low" or "med"
  confidence. NOT applied as overrides yet; they are a vocabulary check (which
  values are missing) and a candidate override list for Daniel to correct.
  Features the vocabulary lacks: shoulder hump (Hunchback), gun pod on the shoulder
  (Rifleman), shoulder boxes (Catapult), squat wide body (Stalker, King Crab),
  forward wedge head (Jenner), claw arms (Crab), raised shoulders (Centurion),
  flared hips (Spider), thick legs (Atlas), deep slim torso (Raven).

- **Token sheet v2 review (Daniel, 2026-10-31; reference-tag and hash-only rows).**
  Wins: Spider (hashed) close to the ideal; the Jenner D v K pair shows hash-by-name
  works (same silhouette, different loadouts); the Archer reference version could
  be an Archer; Urbanmech partly right. *Structural findings:*
  1. **The views are technical drawings of ONE object** from different angles; the
     measurements must match. v2 draws each view separately, so top is out of
     proportion, a sloped front does not slope from the side, and the side view of
     the Panther head is "funny". Fix: one 3D part model (boxes / limbs with x, y,
     z) projected orthographically to top, front, rear and side.
  2. **Never draw outside the standee**; the standee is hard-capped to its base
     (Scorpion). Clip and size to the base.
  3. **Weight must look right** (the Scorpion looks massive for its tonnage).
  4. **Do not over-represent weapons from top and side** (Archer: a rack just
     painted on the arm in the side view). Weapons that cannot be seen from a
     direction stay out of that view.
  5. **Color:** 3 or 4 tones, with greebling lines that separate left / centre /
     right torso (legs ran into torso stripes on the Spider).
  6. **Shape variety:** arm and leg segments are all still blocks; hips need
     their own section (a wedge body only works on a separate hips section,
     otherwise it is a skirt); torsos flaring out like a bell (Urbanmech) read as
     not war-fighting equipment.
  *Rules to add:* dog and lizard apply to QUADS only (dog: knees under the body;
  lizard: legs angle out from the body, knees away from it); bipeds are
  humanoid / bird / Martian. Legs differ across models (they all look alike now).
  Digitigrade legs with claw or hoof feet. Tripods: stand over none of their
  legs, bent knees. Chicken legs with more knee bend and a higher hip pivot
  (Stalker). Arms may go above the mech (Catapult: ovoid body on a hips section,
  missile boxes rising above like ears). Jump jets by LOCATION from the file
  (Jenner: 2 right torso, 2 left torso, 1 centre). Weapon mount follows the arm:
  with a lower actuator the weapon sits in line with the forearm; with only an
  upper actuator the arm is a turret mounted at the side, not a right-angle stub.
  Boom shoulders need connective tissue. The neck is too thin. The head may sit
  in the centre torso on a boom neck (Jenner). Visual size threshold: how big a
  weapon must be before the head is displaced (Raven: SRM could be in the torso).
  Pod versus built in: odds to be settled (omni units mark pods in the file).
  Do not mount the Mad Cat's missile boxes on the sides: the area is dense and they
  clip; they are shoulder box launchers. Orion got pod-happy for no reason.
  Missile scale: real masses (SRM about 10 kg a missile, LRM 25 kg for 3) give small
  missiles; add an artistic fudge factor so they do not disappear. Greebling can
  offset features (Warhammer: a shoulder searchlight balances the SRMs).
  Flea in the source's words: a torso on a separate hips section, legs under
  the body joined to the hips from the side, digitigrade, claw or hoof feet,
  cockpit upper front, torso tilted back (fighter or attack-helicopter feel),
  angular, arms like turrets / gun barrels on the torso.
  *Sprite study:* Daniel recommends studying MegaMek's sprites (top-down
  especially) to build a dictionary of shapes. Their art is copyrighted: describe
  shapes in words and tags, never trace or copy the images.

- **Chart resolution (measured 2026-11-01).** The MWO chart image is 2000 x 746 px;
  its front / side figures measure about 59-77 px (light), 74-91 (medium), 80-98
  (heavy), 91-107 (assault) tall and the top-down views only 36-54 px. Enough for
  proportion and silhouette, not for knees, elbows, hands or seam lines. The
  reference tags (`data/token_reference_tags.json`) are therefore coarse, the light
  units most of all. A larger chart or per-unit recognition-guide images are wanted.

- **Where the tokens stand (2026-11-01).** `INTEGRATION__tokens.py` (v3: one 3D part
  model per unit, projected to top / front / rear / side; mass fit; standee and hex
  caps; jump jets by location; forearm-line weapons; seam lines; four tones; dog and
  lizard for quads only), `tools/token_sheet.py` + template (the contact sheet, each
  unit drawn with reference tags and hash only), `data/token_overrides.json`,
  `data/token_reference_tags.json`. Published sheet: claude.ai artifact
  CS8cdEG8rBR2jU5o3t1Y8a (private). Next: wider part shapes (limbs are still uniform
  tubes), Flea-style hips / tilt / claw feet, Catapult ears, Warhammer searchlight,
  Jenner boom head, a visual-size threshold for head displacement, shading, the
  tripod look, and a check that the Spider's arms show in the top view. Then Daniel
  reviews whether the four views read as one object.

- **Goal restated and "blocks" source (Daniel, 2026-11-01).** Ultimate goal:
  simplified models in the MWO design language, so a viewer thinks "that looks like
  BattleTech", with detail from the name hash and the real `.mtf` stats; a location
  bulks out when it carries more armor. Daniel's ideal: find a source of the "blocks"
  the 3D models are built from.
  - **Claude's findings.** `gamemodels3d.com/games/mechwarrior` is a viewer for
    game-extracted MWO models (about 130 'Mechs by nation and class). Its pages expose
    only names: no parts, tags, images or downloads reachable by fetch. The game's
    meshes are copyrighted, so extracting them is out (same rule as the chart and the
    posters: reference for proportions and style only). No public source of a clean,
    reusable block set was found.
  - **Plan: build our own block library.** A small set of original primitives named
    for the design language (chamfered armor plate, wedge, boom, ovoid, hips ring,
    digitigrade leg, pod arm, shoulder box, ear...), each with a few parameters
    (size, chamfer, taper, panel-line style). Values are written in words and tags
    from reference viewing; the generator draws its own shapes. Adding a new unit
    means choosing blocks, not tracing a model.
  - **Armor bulk per location (not built).** `INTEGRATION__tokens.py` uses one global
    `bulk` (armor per ton, clamped 0.96-1.08). Wanted: each location's thickness from
    its own armor points relative to the location's structure maximum (so a 2x-armored
    side torso swells and a bare rear/leg stays slim), with a clamp so the standee cap
    and the rules height still hold.
  - **Open (Daniel):** may Claude view model renders (screenshots of the viewer,
    never extracted files) to write block tags? Otherwise tags come from the chart and
    posters at lower confidence.

- **Token pass v4 (2026-11-01, session 16) - top and side now differ. REVIEW PENDING (higher-level model).**
  - **Poster references:** none of the Recognition Guide posters or MWO renders are in the repo or
    this session (Daniel's connection is too slow to send renders), so the new tags are Claude's
    reading from general knowledge of the silhouettes, in words, `confidence` low: each is a
    candidate for Daniel to correct. Nothing was traced or copied.
  - **New features** (`INTEGRATION__tokens.py`, `FEATURE_KEYS`, hashed by default, overridable in
    `data/token_reference_tags.json`): `plan` = the torso from ABOVE (`block`, `wedge` narrows to the
    front, `flare` widens to it; a plan warp in `B3.box`); `profile` = the torso from the SIDE
    (`upright`, `sloped` front face leans back with the rear upright, `lean` pitches forward,
    `hunch` adds a hump behind the head and moves the head forward); `hips` (`plain`, `flare`).
    Tagged now: 32 chart units (plan / profile for all; hips flare for Spider, Flea, Catapult).
  - **Armor thinness (Daniel's rule: thinner when under-armored, never thicker).** Per location,
    armor against its maximum (twice the structure from `mechsim.mech_state`, head 9) maps to
    0.78-1.00 of the plain size; applied to the three torso pieces, arms, legs and head. The global
    `bulk` is now fixed at 1.0. **Bug fixed:** `read_unit` never read any armor (it tested
    `" Armor"`, the files say `armor`), so the old bulk hint was constant; the parser now keeps
    `armor_by` per zone (rear armor ignored).
  - Shoulder racks get a mount or stalk so they no longer float (Griffin, Catapult).
  - Still open: the hump and wedge barely show in the 120 px top token (the arms dominate the
    plan), tripod look, Flea hips / claw feet, head displacement threshold, shading, Catapult ears
    as true boxes. `python tests/run_checks.py`: 43 of 43 pass (tokens are output only).

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
