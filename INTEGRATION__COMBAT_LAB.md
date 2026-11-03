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

- **Reference study: MWO Timber Wolf parts kit (Daniel, 2026-11-03). REVIEW PENDING (higher-level model).**
  Daniel uploaded a fan-made printable Timber Wolf (54 STL parts, scale about 130 mm tall, by a
  Thingiverse-style author; the files and the author's PDF stay OUTSIDE the repo, in session
  scratch only). Claude rendered each part from four angles with three.js in headless
  Chromium (a throwaway viewer, not committed) and read the shapes. What follows is words and
  rough ratios for the block library, not copied geometry. Caveats: it is a print-in-place
  articulated toy, so ball pins, slots and clearance gaps are print features, not design; the
  parts carry no assembly transform, so whole-mech proportions are not given.
  - **Torso (10 options, same body).** A teardrop / bullet shape: from above a round-nosed
    ovoid tapering forward; from the front a smooth dome like a cockpit canopy; from the side a
    low nose sloping down and forward over a flat underside. Daniel's "ovoid body" is right.
    Rear third: a squared-off deck carrying two rectangular bays, one per side, WIDER than the
    body (about 1.7x the body's width overall) and taller at the rear (about 1.4x the body's
    height), each with a face grid of missile cells or a plain panel (the options vary the cell
    count, 3 / 6 / 12 etc.). So the "shoulder racks" are box bays built into the rear wings,
    not pods hung over the shoulders. Plan = rounded nose to square rear with wings; profile =
    sloped nose, tall rear. Panel lines wrap the dome in long arcs.
  - **Legs.** Digitigrade in the kit's own anatomy: a thigh block bent like a banana with a
    disc joint at each end (big flat discs, like hip and knee covers); a chunky shin made of
    stacked chamfered slabs with a split fork at the knee end and a ball at the ankle; a foot
    hub with a flat chamfered plate and three toes (two front, one back), each toe a chamfered
    block with a hollow socket. Every edge is chamfered; there are almost no true curves except
    the joint discs and the dome.
  - **Arms.** The arm is mostly a GUN POD: the "hand" parts are long, narrow lozenges (leaf
    shaped in plan, hexagonal in section) with the weapon built into the front, a raised top
    spine with panel lines, a small clamp at the rear and a stub underneath. Interchangeable
    muzzles (twin round bores, open slot, quad slot) show a pod is a hull plus a muzzle choice.
    Upper arm = a chamfered box on a ball; one variant carries a hanging bracket frame.
    Elbow and forearm are blocky cubes with chamfered corners and a round cap.
  - **Weapons (separate barrels).** PPC / ER PPC: a smooth cylinder with a stepped muzzle collar
    and one fine groove line (ER is longer and thinner); Gauss: a triangular-section tube with
    chamfered nose; Ultra AC: a slim barrel with ribbed cooling grooves and a twin muzzle; LB-X:
    a thick cylinder with an underside rail; gatling: three barrels ringed by clamps. Each
    weapon class has a distinct section (round, triangle, twin, triple) - useful for reading the
    class from the front.
  - **Design language in short (candidate blocks):** chamfered everything; a smooth ovoid
    canopy-like torso; rectangular rack bays on the rear wings; lozenge gun-pod arms; stacked
    slab shins; disc joint covers; long arc panel lines.
  - **What it changes in the generator (not built):** a `canopy` torso block (round nose, dome
    front, sloped side, wings with box bays at the rear instead of racks over the shoulder), a
    `pod_arm` lozenge, chamfered leg slabs with disc covers, weapon sections by class (cylinder /
    triangle / twin / triple), and a `chamfer` parameter on every box.
  - **Built from the study (2026-11-03, same session): `data/token_blocks.json` lists the block
    library with status.** In `INTEGRATION__tokens.py`: a chamfer on every body box; the `canopy`
    torso (dome nose, rear deck, wing bays with missile cell grids; used by the Timber Wolf / Mad
    Cat override); the lozenge pod arm; knee disc covers; weapon sections by kind (PPC collar,
    Gauss triangle, Ultra AC twin, LB-X rail, rotary triple). Still ideas: stacked-slab shin,
    banana thigh, three-toe foot, bracket upper arm. `python tests/run_checks.py`: 43 of 43.
  - **Next:** more kits in the same style (Catapult, Hunchback, Atlas...) would let the block
    library be checked on other chassis; a whole assembled model would give proportions.

- **Reference study: MWO Atlas parts kit (Daniel, 2026-11-03). REVIEW PENDING (higher-level model).**
  Second kit from the same fan author (28 STL parts, about 140 mm tall, files kept out of the repo).
  Same caveats as the Timber Wolf kit: a print-in-place articulated toy (ball pins, slots and gaps
  are print features), parts have no assembly positions. Read from renders; words and rough ratios only.
  - **Contrast with the Timber Wolf:** the Wolf is smooth and curved (teardrop body, cylinders);
    the Atlas is ANGULAR and plated: every surface a stack of flat armor plates with chamfered edges,
    visible bolt heads, louvre vents and diagonal seam lines. Same chamfer rule, different surface
    language. Suggests a per-chassis `surface` option (smooth / plated).
  - **Torso (3 options, same body).** A broad block (about 62 wide x 46 deep x 50 tall) with
    shoulder plates that flare up and outward at the top corners, louvre grilles across the lower
    front, bolt heads at the corners. The HEAD is a large faceted dome with a face mask (brow and eye
    slits, the "death's head" look) seated in a notch at the top front, standing proud of the torso
    in plan and rising above the deck. On one side a round socket disc takes the AC20 mount; the
    options add a 6-cell missile box on the chest-shoulder.
  - **Pelvis.** A wide flat OVAL plate on top (chamfered rim, flat top), a short skirt below, and a
    narrow hanging apron down the front centre: from the front it reads as a T or anvil (wide flange,
    narrow hanging centre). Big round hip sockets face outward on the sides.
  - **Legs (humanoid, not digitigrade).** Upper leg a tall chamfered box with a diagonal slash
    line and a ball at the hip; the knee a clamshell block with a fork; the lower leg a tall slab
    with vent slits and a narrow spur at the back; the foot LOW (about 14 mm tall against 42 long):
    a flat sole with a sloped heel, a big cylindrical ankle drum on top, chamfered wedge toes.
  - **Arms.** The shoulder is a big faceted dome (like a helmet, hexagonal facets) with a rim flange
    below it, wider than the upper arm; the upper arm a plain chamfered box; the lower arm a long
    slab ending in a fist of stacked finger plates; add-ons are small gun stubs (a block with a
    muzzle face and tiny port dots).
  - **Weapons.** AC20: a boxy receiver with a raised top rail and cooling holes, an underside
    stub, and a long round barrel; variants change the muzzle only (plain, ringed, a multi-ring brake).
    SRM-6: a chamfered box with six round tube mouths (2 x 3) on the face, a small mount stub under it.
  - **Candidate blocks (not built):** `skull_head` (faceted dome with a mask, in a front notch),
    `dome_pauldron` (faceted dome with a rim flange), `oval_pelvis` with an apron, `fist_hand`,
    `ac_receiver` (box with rail and holes, long barrel, muzzle options), `srm_box` (box with a tube
    grid), `louvre` and `bolt` surface details, and a `surface` option (smooth / plated).

- **Reference study round 3: whole-model and part kits (Daniel, 2026-11-03). REVIEW PENDING (higher-level model).**
  Eight more uploads, files kept out of the repo (session scratch only): MWO-style part kits for the
  Marauder and Hunchback (same print-articulated style as the Timber Wolf and Atlas kits), and six
  single-file WHOLE miniatures by another author (Jenner JR7-F, Orion ON1-V, Locust LCT-1V, Flea
  FLE-4, Stalker STK-3F, Catapult CPLT-C1): the first sources with real whole-mech proportions.
  Read from renders in four or five views; words and rough ratios only. Caveat: they are posed
  miniatures (crouched, arms out), so bounding boxes include the pose.
  - **Bounding ratios, width : depth : height, as posed (rough):** Jenner 0.66 : 0.71 : 1,
    Locust 0.64 : 0.70 : 1, Flea 0.70 : 0.90 : 1, Stalker 0.59 : 0.66 : 1, Catapult 0.66 : 0.72 : 1,
    Orion 0.84 : 0.60 : 1 (arms out). Light and medium units are about two thirds as wide as tall,
    the Flea nearly as deep as tall (a horizontal body); torso is roughly the top 40 percent of
    the height on every unit, legs the lower 55.
  - **Shape language per chassis (now in `data/token_reference_tags.json`, confidence high for
    the whole models):**
    - *Jenner:* chicken legs; a long wedge torso slung forward; a cockpit beak at the front; tall
      box pods on the outer sides; two long antennas; small arms tucked under.
    - *Locust:* small wedge torso slung forward; wing-like shoulder plates swept up at the sides;
      thin gun arms; two antennas; thin chicken legs with big claw feet.
    - *Flea:* a flat, wide slab torso almost horizontal on thin legs; gun pods forward under the
      front edge; deep knee bend.
    - *Orion:* a broad faceted chest with a vent grille; the head sunk between big rounded
      shoulders; thick arms, a big cannon on one; straight legs with big knee blocks.
    - *Stalker:* a long snout-nosed body (a cockpit cone) with big box missile bays flanking the
      rear (cell grids on the face), an antenna, chunky chicken legs, wide flat feet, small arms.
      This is the same shape as the Timber Wolf's canopy torso, so Stalker now uses `canopy`.
    - *Catapult:* an ovoid body with tall box missile pods rising like ears on both sides (cell
      grids face front), a tiny dome head, small arms, long-striding chicken legs.
    - *Hunchback (part kit):* a tall deep box torso with a big hump on top carrying the gun, the
      head low inside the hump; forearm slab ending in a fist of finger plates; low wedge feet.
    - *Marauder (part kit):* a long low arrowhead hull torso (narrow nose, wide rear tabs), a boxy
      waist block with a big round hub, a flat foot with two long forward toes.
  - **Generator changes:** the reference tags above (plan, profile, torso, head, hips) replaced the
    earlier guesses for these eight; `torso: canopy` now also applies to the Stalker.
  - **Still not built:** a taller whole-mech check (compare drawn proportions against these
    ratios), a `ears` torso (Catapult) and `snout` variants, stacked-slab shins, three-toe claw feet,
    and the shading step. Chicken legs and forward-slung wedge torsos recur on the light chassis, so
    they are the next most useful shapes.

- **3D model pipeline (Daniel chose it over more flat-shape work, 2026-11-03). REVIEW PENDING (higher-level model).**
  The art is now its own project (to be merged with the simulator later). New files:
  `INTEGRATION__token_mesh.py` (each part of a unit's part model becomes a convex 3D solid; world
  units are levels, glTF axes: X left, Y up, Z forward; `unit_mesh()` for JSON, `write_glb()` for a
  binary glTF), `tools/token_3d.py` + `tools/token_3d_template.html` (builds the viewer page: three.js
  r128 from cdnjs, flat-shaded lit models with edge lines and a soft shadow, orbit / pinch zoom,
  six preset views, orthographic switch, the standee card and the hex footprint, reference tags
  against name hash only; `--glb <folder>` also writes one `.glb` per unit). Needs numpy, scipy and
  trimesh (art tools only; the simulator does not import them).
  - **Limbs and joints are chamfered slabs in 3D** (a chamfered-cube cap on every limb segment and
    joint), not tubes; weapon barrels keep round caps. This one change removed most of the
    "capsule doll" look. The 2D drawings are unchanged.
  - **Result:** 33 units (32 chart chassis plus the Timber Wolf), about 2.4 MB of page, a few
    thousand triangles per unit. Views are renders of one object, so top, side and front agree.
  - **Mad Cat review (Daniel, 2026-11-03) and the fixes:** (1) side torsos and hips were rectangular
    blocks: the canopy body is now ONE convex teardrop (`B3.blob`, a hull of ellipsoids) and the
    pelvis a hexagonal plate with cut corners and a front apron (all non-quad units); the missile
    bays are tapered, canted and chamfered. (2) Arms did not line up with the side torsos: the
    shoulder socket is now on the side torso's outer surface (canopy torsos). (3) "The centre
    torso shape includes all three sections": the teardrop spans the full torso width (two wide rear
    lobes are the side torsos, the narrow dome nose the centre torso), with seam lines between the
    thirds; the bays sit ON the side torsos. (4) Weapons not connected: barrels now start inside the
    part they mount on (`embed`), flank weapons use the lobe's real front surface, chest weapons
    poke from the nose, the visor sits on the dome. Other torsos (box, slab...) keep their old
    mounts; the same embedding for them is not done.
  - **Torso side profiles (Daniel, 2026-11-03: "you keep using a parallelogram for torsos").** The
    cause was a sheared box (`tilt`) on every non-canopy torso. Replaced by real side profiles
    (`PROFILES` in `INTEGRATION__tokens.py`): upright, sloped, lean, wedge_up, bell, shoulder, prow,
    dome, stepped (two solids), hunch (hump); each is a convex polygon extruded across the width
    (`B3.extrude`), so the side view IS the polygon. The hash picks from twelve (weighted), reference
    tags name them per chassis (several reassigned; low confidence, Claude's reading). Weapons and
    heads now mount on the profile's real front face (`front_y`). The `profile` tag in the reference
    file may now hold any of those names.
  - **Arm clipping (Daniel, 2026-11-03, JagerMech).** The shoulder was anchored at the torso's
    nominal edge, ignoring the arm's own thickness and the torso's taper / flare at the height the arm
    hangs, so the arm's inner edge sat inside the torso. The shoulder x is now the torso's real
    half-width (max over the shoulder and the lowest point of the arm beside the torso, taper, flare
    and plan included) plus the arm's half-width and a gap; canopy sockets moved out the same way.
    Checked by eye on JagerMech, Mad Cat and Orion; not measured on all 33 units.
  - **JagerMech arms still clipping, "pointing at a point in front" (Daniel, 2026-11-03).** Real
    cause: the pod arm's plan taper (narrower toward the muzzle) was applied about the FIGURE'S centre
    line (`B3.box plan`), so each pod's front corners were pulled inward toward the torso: the arms
    converged and clipped. `plan` now takes an optional centre x (the pod tapers about its own centre).
    The same flaw sat in the torso extrude (wedge plans pulled only the section edges, not the side
    sections' centres): the plan factor now scales the whole torso about the centre line. The shoulder
    connector is shortened to torso edge to joint. Checked by eye (top and front) on JagerMech,
    Locust, Commando, Orion, Flea, Hunchback.
  - **Scale chart re-read with the kit vocabulary (Daniel, 2026-11-03). REVIEW PENDING (higher-level model).**
    The MWO scale chart came back (2000 x 746; the copy that reached the session is 165 KB, not the 2.7 MB
    original). Read at 3x, row by row, against everything the kits taught: all 47 chart chassis now have
    tags (32 existed; 15 new: Vindicator, Enforcer, Kintaro, Quickdraw, Dragon, Cataphract, Grasshopper,
    Black Knight, Victor, Zeus, Battlemaster, Cyclops, Highlander, Mauler, Banshee) and about 30 existing
    ones were re-read (the whole-model units stay as the 3D studies set them). Files:
    `data/token_reference_tags.json` (tags plus a `new` list of unbuilt features per chassis),
    `data/token_dictionary.json` (the dictionary: plan / profile / torso / shoulder / arm / leg / detail
    terms, each with what it means in words, which chassis show it, and whether the generator has it),
    `data/token_chart_proportions.json` (measured: front W/H, side D/H, top W/D and chart height per
    chassis, from segmenting the silhouettes). CORRECTION (2026-11-03): the chart cell first read as "Linesman" is the MAULER; the earlier
    "no unit file" remark was my misreading, and the library has Maulers.
  - **Measured findings:** chart heights grow with tonnage as about tons^0.49, not the cube root (0.33) the
    generator uses (the chart's own scale is unreliable per Daniel; his rule keeps the cube-square curve);
    heavier 'Mechs are proportionally WIDER: front W/H averages 0.63 light, 0.68 medium, 0.70 heavy, 0.81
    assault, and side D/H falls from 0.53 to 0.42. The generator's width factor (`wf`) should follow this.
  - **Missing blocks, ranked by how many chassis show them** (all `idea` in the dictionary): arms forward
    past the body / long barrel arms (7: Blackjack, Rifleman, JagerMech, Warhammer, Griffin, Wolfhound,
    Mauler), pillar legs (6: Atlas, Banshee, Highlander, Zeus, Awesome, Orion), round dome torso (5),
    arrow plan (5), slung wedge profile (4), shoulder corner pods (4), tiny arms under big boxes (3), tall
    slab profile (3), round arm blocks (3), swept shoulder fins (3), ears (3). Seen in the viewer: the 47
    units render but many still look alike, because the generator cannot yet say these.
  - **Missing blocks built (2026-11-03, in the dictionary's ranked order).** New reference-tag keys:
    `legs` (pillar, barrel, heavy), `arm_style` (long_barrel, ball, claw, a_frame, tiny, shoulder_pod),
    `kit` (corner_pods, fins, ears, round_blocks, posts, pylons, spar, tent); plan `arrow`; profiles
    `slung_wedge` and `tall_slab`; torso `dome` (one rounded mass with seams and the glass on its
    front). Heavier 'Mechs are also drawn wider (width factor 0.90 at 0 t to 1.14 at 100 t on top of the
    mass fit, after the chart's W/H 0.63 light to 0.81 assault). Applied by tag to the chassis that show
    each term (`data/token_reference_tags.json`); `data/token_dictionary.json` statuses updated. Checked by
    eye in the viewer on about 30 units: silhouettes now differ (long barrels, ball fists, swept horns, spar,
    tent antenna, dome torsos, pillar legs, the King Crab's low wedge). Not built: oval disc plan, crouched
    stance, triple hump, V chest, reverse-bent lower leg, heel thrusters, asymmetry, a second antenna.
  - **Details and options added (2026-11-03, session 16, continued).** Chicken legs rebuilt (high hock,
    claw toes: every bird-archetype chassis changes); option `surface` (plated / smooth: vents, bolts,
    panel lines on the torso, armor bands on humanoid legs; plated by default from 60 t, otherwise by
    the name hash); plan `oval` (Atlas); kit `humps` (Kintaro); legs `reverse` (Shadow Hawk, Highlander,
    with a heel); `feet: thrusters` (Quickdraw); `asym` (one arm 1.32x, the other 0.80x: Vindicator,
    Dragon); `antennas` count 0-3 (the single head mast is replaced by masts on the torso top);
    `crouch` (legs 16 percent shorter, knees pushed forward: Crab, King Crab; the torso does not pitch yet).
    Bug caught: a limb segment's cap is a cube sized by its radius, so a short fat "band" came out as a
    big block; bands are now thin boxes. Still not built: the Mauler's hexagonal chest plate, pitching
    the torso in a crouch, second and third antennas of different heights per chassis, panel lines on the
    legs and arms, a camo / team-color option.
  - **Crouch pitch, limb panel lines, team color, cockpit scale (2026-11-03, session 16, continued).**
    `crouch` now pitches the whole upper body (everything built after the legs) 20 degrees forward about
    the hips. Dark panel lines run down the front of thigh, shin and forearm. Parts of class `tm` (chest
    stripe, shoulder plates, canopy bay tops) take a team color in the viewer (none / red / blue / green /
    gold; the armor tints 9 percent); the `.glb` files keep the neutral plate color. **Cockpit scale
    (Daniel: a cockpit is a fixed ~3 t, so it is a bigger share of a light 'Mech):** head and glass scale
    with the cube root of cockpit tons over total tons (x1.36 at 20 t, 1.0 at 50 t, 0.79 at 100 t, 0.64 at
    200 t); the weights by cockpit type come from the construction rules, which are not in the indexed
    Core, so small 2 / torso-mounted 4 / primitive 5 are Claude's recall (flagged in code) and affect art only.
  - **Skull head, dome pauldrons, stacked-slab legs (2026-11-03, session 16, continued).** The skull head
    (faceted dome, brow ridge, glowing eye slits, nose bridge, jaw mask plate, seated in a front notch of the
    torso: `head_mount: notch`, `head_shape: skull`) is the ATLAS ONLY, by named tag, never from the hash
    (Daniel: unique to the Atlas). Kit `pauldrons` (a faceted dome over each shoulder with a rim flange):
    Atlas, Orion. Legs `slab` (two stacked chamfered slabs on the thigh, three tapering on the shin, a
    clamshell knee, wide block foot): Atlas, Banshee, Battlemaster, Victor. Checked by eye on the Atlas,
    Orion, Banshee and Flea (unchanged).
  - **Weapon models and mech-like parts (Daniel, 2026-11-03: "enhanced weapon models that fit", "replace
    blocks for something that looks like it would be on an actual mech").** `weapon_fam` reads each weapon's
    family and size from its name; `weapon_barrel` builds laser (housing, fin plate, lens, pulse = two lenses),
    PPC (coil rings, forked muzzle), AC / Ultra / LB-X (receiver, side feed, barrel, brake, rail), Gauss
    (coil rings), machine gun, flamer, rotary; `_pod` missile racks have a lid line and tube mouths as dark
    recesses with a colored rim. All receivers are buried in the mount. Also replaced: fists (palm, three
    finger plates, thumb), feet (heel block plus two toe wedges), heads (side profile extruded; dome a
    blob), shoulder caps (not balls), jump-jet nozzles. Fixed on the way: leg armor bands were too dark.
    (The chart chassis I misread as "Linesman" is the Mauler; see the correction above.)
    Page size 5.9 MB (blob samples cut to 64). Checked by eye on 12 units. Not built: AMS dome, TAG /
    probe / ECM housings, artillery tubes, swiveling turrets.
  - **Mauler model (Daniel, 2026-11-03).** A whole Syllogy MAL-1R miniature settled the misreading above.
    Read from renders: small head sunk between two huge slanted-top missile boxes at the shoulders (cell
    grids forward, tall rear wings), a hexagonal chest plate, one long arm cannon and one slab arm with a
    flat armor panel, thick plated pillar legs with clamshell knees, stacked-plate shins, block feet with
    toes. Tagged `mauler` (kit launchers, legs slab, long-barrel arms, asym left); the generator's ears are
    smaller than the Mauler's launchers, so the Mauler uses the new `launchers` kit (huge slanted-top
    missile boxes with a forward cell grid and a tall rear wing).
  - **Ten more whole models (Daniel, 2026-11-03; files outside the repo):** Awesome (8Q and Pretty Baby),
    Archer, King Crab, Raven, Wolverine, JagerMech, Rifleman, Highlander, Cyclops (Syllogy miniatures).
    **Corrections to my chart-only guesses:** the Archer's big feature is two huge UPRIGHT launcher boxes
    at the back of the shoulders (not barrel shins; its legs are plated slabs); the Wolverine has a BOXY
    torso with shoulder pods and digitigrade-style legs (not a dome); the JagerMech and Rifleman carry
    gun pods with long twin barrels on the SHOULDERS in addition to ordinary hanging arms (I had tagged
    them as long-barrel arms); the Awesome has one big PPC arm and one fist, with tall blade fins; the
    Cyclops has a domed hood head, a tent antenna and big fists; the King Crab and Raven confirm the
    crouch and the delta-wing hull. Built: kits `tall_launchers` and `shoulder_guns`, and several kits
    may now be named at once ("shoulder_guns,spar"). Tags updated for all ten (confidence high). Checked by
    eye on nine units. Not done: the Raven's raised tail fin, the Awesome's grille chest, and the
    King Crab's pincer hands.
  - **The three leftovers from the ten-model batch, built (2026-11-03).** Kit `tail_fin` (a tall swept
    fin and two small ones at the rear of the hull: Raven); kit `grille` (a recessed chest grille, a frame
    and seven dark slats: Awesome, named together with the fins: `fins,grille`); a new `hands` key
    (`pincer`: two jaws with angled tips on a palm, King Crab and Crab; `ball` moved here from `arm_style`,
    which still works). The King Crab's pincers are partly hidden behind its arm barrels from the front.
  - **Three hard-SF critique passes (Daniel, 2026-11-03: "pretend you are a gamer into hard SF models; could
    you see this as real military hardware?").** Pass 1 (baseline: looked like an unpainted toy): weapon
    barrels were bright red / yellow / blue pills; one flat blue-grey; knees were blocks on tubes; no waist
    joint; no heat rejection. Fixed: gunmetal weapons with the class color only as a marking; paint schemes
    (steel / desert / olive / urban / arctic / navy, auto per unit) with weathering; a dark waist ring; a
    finned back radiator; knee hydraulics. Pass 2 (front and side): the new waist ring overhung like a belt,
    the pelvis apron hung between the legs, heavy 'Mechs had noodle arms, small feet for the mass, no plating
    breakup. Fixed: ring sized to the pelvis, a flush front skirt plate, arm girth and hands and feet grow
    with tonnage, chest plate seams. Pass 3 (rear, top, close-up): chest seams stuck out past the torso like
    whiskers, the waist ring showed as a black slab under dome / canopy bodies, hands tiny against the arms.
    Fixed: seams limited to the torso's width at that height, no ring on dome / canopy, hands scale with the
    arm. Viewer: a Paint selector (with the Team selector). Still open (the dictionary's `hard_sf_pass`):
    cockpit hatch and frame, sensor clusters, handrails and access hatches, unit markings and decals, plating
    breakup on the limbs.
  - **Second hard-SF review (Daniel, 2026-11-03): "fancy toy blocks" to "the Pentagon would fund this".** His
    list: knees are cubes with the corners cut off; missile boxes stuck out of the chest; the back plate is a
    copy-pasted striped board that does not fit all torsos; the Banshee's legs are stacked blocks. Claude's audit
    found the root: every joint was a chamfered cube cap on a tube, the launchers were free cubes, the back plate
    one stamped panel. Built: `B3.obox` (an oriented tapered armor block; legs and arms are made of these),
    cylinder joints (hips, knees, ankles, hocks, elbows), a mesh builder that makes each limb segment a faceted
    cylinder along its own axis, armored legs (thigh plate, pointed kneecap, calf bulge, lapped shin plates on
    slab legs), recessed launchers behind a bezel, five rear modules sized by heat sinks and fitted to the
    torso (fins, reactor dome, twin stacks, engine cowl, framed vent), chest armor plates, cut torso edges.
    Critique rounds on the way fixed: knee housings that read as wheels, a dark stack that looked like a slot,
    a hatch that looked like a gun port. Honest state: much closer to hardware, still not research-grade: torsos
    are boxy, arms are blocks, heads have no canopy frame, no decals, flat lighting. See `hard_sf_pass_2` in the
    dictionary for the open list.
  - **Daniel's unit-by-unit review (2026-11-03) and a design philosophy. REVIEW PENDING (higher-level model).**
    Principles (also in `data/token_dictionary.json` `design_principles`): a 'Mech is a SKELETON driven by MYOMER
    muscle with weapons and a SHELL of armor on top, some sections expanded for equipment; so not "blocky"; an arm
    can be an elephant's trunk (pure muscle in an exoskeleton); fusion powered, so exhaust stacks are a choice;
    pistons are disliked (they imply hydraulics) but expected on heavy machinery, so they are an option.
    **Root bug found:** the unit files write weapons as "1 ISSRM6", "2 ISStreakSRM2", "ISERLargeLaser"; my parser read
    the leading count as the weapon's size, so every SRM-6 was a one-tube launcher (Kintaro and Blackjack "missing
    missiles") and `er` / pulse detection missed. `clean_weapon_name` now normalizes names ("SRM 6", "ER Large
    Laser"); hand weapons (sword, hatchet, mace, claw...) are split out into `unit["physical"]`.
    **Done (checked by eye on about 16 units unless noted):** exhaust stacks tag-only; myomer bundles instead of
    pistons (`pistons: true` for the old look); cockpits blue and VISIBLE on every chassis (a blister with a glass
    band; the Mauler and Cataphract, domes put the glass on the surface); missiles violet; weapon bulk by mass
    (Commando's large laser, all large weapons); PPC with a three-way (120 degree) muzzle; Ultra AC twin bores in ONE
    shroud (King Crab); plasma rifle (Catapult); ER laser focusing ring, pulse two lenses; SRM / LRM / MRM racks each
    with their own pod and tube layout by rack size (Thunderbolt, Griffin, Dragon); weapons built along the forearm's
    axis (Cyclops arms hang down, so their guns point down); hardpoint SLOTS on arms (centre, below, above: Rifleman,
    Dragon's off-centre Gauss); hand arms carry the gun on the outside of the forearm, clamped (Battlemaster);
    weapon arms (JagerMech, Rifleman, Marauder, Highlander) have a housing sized by the gun, no stub arm, no hand;
    weapons from the file, not a fixed kit; trunk arms (Timber Wolf / Mad Cat); body proportions by tag (`girth`,
    `bodyd`, `bodyh`, `legscale`, `armscale`): Victor bigger than Awesome, Black Knight bigger, Stalker long and
    low, Locust tall and thin against the Flea's flat slab, Grasshopper pauldrons and slimmer arms; speed lengthens
    legs and slims arms (Wolfhound); jump jets on the back of the calf (Grasshopper), IMPROVED jump jets with a
    bigger nozzle and fairing (Firestarter); electronics (ECM dome, probe dish, C3 mast); rear-facing weapons
    drawn on the back (Quickdraw's rear laser, Firestarter's rear flamer); hand weapons (Vindicator's sword,
    hatchet, mace, claw); head turret weapons (Quickdraw's PPC); Stealth armor read from the file (Quickdraw
    QKD-8X is shown, dark paint); chest plates cut from the torso's own profile so they no longer float (Crab,
    Jenner); a neck between head and body (Spider); the Archer's launcher boxes use the file's rack count.
    **Not done / open:** the skeleton-and-shell rebuild of torsos and limbs (still boxes); the spherical
    turret option (Cyclops); the Battlemaster's shoulder-to-arm imbalance; Trebuchet and Raven clipping;
    the Archer's exposed launchers; the Firestarter arm-to-weapon scale; the Warhammer, Urbanmech and Cataphract
    were praised and left alone; the Cicada's rabbit face and the Black Knight's `.__.` face are kept on purpose
    (Daniel: funnier intentional) but the Black Knight's was not specifically drawn; the Mad Cat trunk reads as
    chunky armor, not a trunk. The contact sheets I used squashed some images, which cost me one wrong turn.
  - **Scaling law: equal mass, equal volume (Daniel, 2026-11-03).** His Awesome-v-Victor note was about this, and
    Claude first misread it as a request for bulk (added `girth` tags, which made it worse). Measured on the 47
    chart units (union volume of the body parts, weapons excluded): volume per ton varied 0.15 to 0.69 (4x), and
    fell from light to assault. A second violation: the base cap shrank heavy 'Mechs (the Atlas was drawn 1.36
    levels tall against its curve of 2.0). Fix: `INTEGRATION__token_mesh.calibrate` scales width and depth so that
    body volume = DENSITY (0.0037 levels^3 per ton, the old median) x tons, with the height on the rules curve
    and the base cap off for 3D. Result: all 47 within 3.47-4.01e-3 per ton (2.3 percent spread), none clamped
    (fit 0.61-1.54); Awesome and Victor (80 t) 0.297 and 0.299. New: `tests/test_token_volume.py` (skips without
    numpy / scipy / trimesh). The chart's finding that heavier 'Mechs are wider (W/H 0.63 to 0.81) is no longer
    applied (width and depth scale together, so volume wins); shaping it at constant volume would need separate
    width and depth factors. Side effects: heavy 'Mechs now look taller and slimmer; the Locust and the Flea
    (both 20 t, same volume) still look alike. The 2D sheets keep the older estimate.
  - **Next art steps (not built):** chicken legs (done above); stacked-slab shins with a high hock; the forward-slung wedge torso;
    the Catapult's "ears" torso; stacked-slab shins; three-toe claw feet; skull head and dome
    pauldron for the Atlas; panel-line and vent detail; team colors; more chassis (the part kits
    cover Atlas, Marauder, Hunchback in detail); a `surface` option (smooth / plated).

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
