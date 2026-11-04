# Combat Lab art - skeleton-and-shell model: build spec

Written 2026-11-04 (session 18, Claude) from Daniel's answers the same day. Daniel's decisions are marked
**(Daniel)**; everything else is Claude's proposal and may be changed by the builder if it says why in the
Change Record. Background: `INTEGRATION__COMBAT_LAB.md` (the block generator's history, the kit and model
studies), `data/token_dictionary.json` (`design_principles`, `hard_sf_pass`, `hard_sf_pass_2`),
`data/token_reference_tags.json` (per-chassis tags). Art only: nothing here touches a battle.

## 1. What is being built

- **It replaces every block (Daniel).** `INTEGRATION__tokens._build` (the block builder) is retired; the new
  builder produces the same kind of output (convex solids in a `B3`, tagged by class), so
  `INTEGRATION__token_mesh.py`, `tools/token_3d.py`, the viewer and `tools/token_audit.py` keep working.
- **The setting's construction (Daniel, `design_principles`):** a 'Mech is a SKELETON driven by MYOMER muscle;
  weapons and equipment mount on it; ARMOR is a SHELL built around it, some sections expanded for equipment or
  thicker armor. Myomer, not hydraulics (pistons opt-in only). Fusion powered (exhaust stacks opt-in only). An
  arm may be a trunk: muscle in an exoskeleton shell.
- **No exposed internals (Daniel):** "Mechs are designed for high intensity combat. Their internal bits need to
  be protected from shrapnel." The skeleton and myomer are NOT drawn as visible frame. They exist in the builder
  to place and size things; what the eye sees is armor. Joints are covered by armor too: overlapping plates,
  rolling covers, skirts and collars that would let the joint move, with no gap showing the inside. (This
  replaces the current visible myomer bundles at knees and hocks.)
- **Look:** semi-realistic future military hardware (Daniel's goal). Plates with real thickness and edges,
  layered where armor is thick, shaped by the chassis tags; not plain boxes.
- **2D is rendered from 3D (Daniel).** The contact sheet's top / front / side / rear tokens become projections
  of the 3D meshes, so the two can never disagree. The old 2D polygon path goes.

## 2. Layers of the builder

1. **Skeleton.** Per archetype (humanoid, bird / digitigrade, martian, reverse-knee, quad dog / lizard,
   tripod): a list of joints and bones (pelvis, spine / torso core, neck, shoulders, elbows, wrists, hips,
   knees, hocks, ankles, feet), bone lengths from the rules height (2 x (tons/100)^(1/3) levels, 3 x
   (tons/200)^(1/3) superheavy; 1 level = 6 m), the stance (mid-step, crouch tag) and the leg / arm tags.
   Actuators missing from the file change the skeleton (no hand actuator = no hand; no lower arm = a
   weapon arm), as now.
2. **Location volumes.** Each of the eight locations (head, CT, LT, RT, arms, legs) gets an internal volume
   budget from what its critical slots hold (section 3) plus its structure, and an envelope around its bones
   that holds that volume.
3. **Hardpoints** (section 3): the mounting points of the location, filled by its weapons and equipment.
4. **Shell.** Armor plates laid over each location's envelope. Thickness follows the location's armor points
   (`unit["armor_by"]`) against what a location of that size could carry; thick armor = more layers or a
   heavier plate, thin armor = a lighter shell (the current `armor_thinness` idea). Plate shapes, plan and
   profile come from the reference tags (section 5). Sections holding a lot of equipment bulge (the
   "expanded" sections).
5. **Visible mounts.** Weapons at their hardpoints (the existing weapon models: laser, PPC, AC family, Gauss,
   missiles at real tube scale, etc.), jump jets, electronics (ECM, probe, C3, AMS), cockpit glass (blue),
   heat-sink vents.

## 3. Hardpoints and sizing (Daniel)

- **Every location has enough hardpoints to mount ANY combination its critical slots allow.** Daniel's
  numbers, which match the record sheet's free slots: arms 8-10 (12 minus the actuators present), side
  torsos 12, centre torso 2 normally and up to 7 (small engines / gyros), legs 2, head up to 4 (a
  torso-mounted cockpit frees the head). The builder reads the real count per unit from `unit["slots"]`
  (the `.mtf` critical table: everything that is not an actuator, engine, gyro, cockpit, life support or
  sensors is a mountable item).
- **Items take hardpoints by their critical slots.** A 3-slot weapon fills 3 hardpoint positions. Every
  crit-holding item is placed, and none is placed twice.
- **Not weapons only (Daniel: "ideally yes").** Heat sinks, ammo, jump jets, CASE, ECM and the rest also take
  hardpoints. Equipment that is not seen from outside (ammo, CASE, internal heat sinks) takes volume inside the
  shell and makes that section bulge; equipment with a face (heat-sink vents, jump-jet nozzles, ECM domes,
  probes, AMS) is drawn.
- **Placement is shuffled, not sorted (Daniel).** The order in the file is ignored, and so is any fixed
  heaviest-first rule. The unit's name hash shuffles the placement order so units don't all look alike.
  Allowed and encouraged (Daniel): heat-sink vents and similar go to the rear or the sides to avoid clutter;
  large weapons may extend past the location's nominal rear to keep the centre of gravity.
- **Sizing (Daniel: "let's go for it").** A mounted item's LENGTH (along its mount: barrel axis, rack depth)
  follows its critical slots; its CROSS-SECTION follows its mass per slot (density). A dense 1-slot item is
  short and thick, a light many-slot item long and slim. Volume = mass / density.
- **Densities by kind (Daniel: different equipment may have different densities).** One table,
  `data/token_densities.json`, with a density (tons per cubic metre at 6 m a level) for each kind: weapon
  families, ammo, heat sinks (single / double), jump jets, engine, gyro, cockpit, actuators, structure,
  armor. These are art values (Claude's choice, each with a one-line reason), not rules. A note in the file
  says so.
- **Masses:** `mechsim/equipment.json` (all 699 entries have `slots`; 202 have `tonnage`). Where it has no
  tonnage, use MegaMek's source (CLAUDE.md: stats no table gives come from MegaMek at Daniel's word; cite
  "MegaMek") and keep `INTEGRATION__tokens.weapon_tons` only as the last fallback, flagged.

## 4. Volume: a sanity check, not a calibration (Daniel)

Daniel: "volume is more of a sanity check to prevent different blocks from getting wildly off spec." The
current `INTEGRATION__token_mesh.calibrate` (which rescales width and depth until the volume is exact) is
removed. Instead the model's volume comes from its parts (section 3 densities, plus structure and armor),
and a test checks each LOCATION's drawn volume against its mass budget. It fails any location outside a
band and names it. Starting band: +-25 percent (Claude's guess; Daniel doesn't have a number). Tune it on
the test range and record the choice. Height stays on the rules curve (a hard check).

## 5. Reference tags: keep the vocabulary (Daniel)

The tags describe how each chassis should look, read from the kits and models Daniel supplied (the Timber
Wolf and Atlas kits, the Syllogy whole models: Mauler, Awesome, Archer, King Crab, Raven, Wolverine,
JagerMech, Rifleman, Highlander, Cyclops) and the MWO scale chart. They are descriptive and stay. Every term
(archetype, torso, plan, profile, head_mount, head_shape, shoulders, legs, arm_style, hands, kit, feet,
crouch, asym, antennas, surface, back, girth / bodyd / bodyh / legscale / armscale ...) gets a written
mapping onto the new builder's parameters, in `data/token_dictionary.json` beside its meaning. A term the new
system can't express is flagged for Daniel. It is never dropped silently.

## 6. Phases (Daniel: "go for a test range and then expand")

1. **Test range** (Claude's proposal, about 8 chassis covering the archetypes and the hardest cases): Atlas
   (humanoid, plated, skull head, slab legs), Mad Cat / Timber Wolf (digitigrade, canopy torso, trunk arms,
   wing bays), Locust (light, no hands, pod arms), Hunchback (one big AC in a hump), Archer (tall launchers),
   JagerMech (weapon arms, shoulder guns), Urbanmech (small dome), and one torso-mounted-cockpit unit (head
   full of hardpoints). Publish the viewer for Daniel after this phase and wait for his verdict.
2. **All chart bipeds** (the 47 tagged chassis), then the name-hash path for untagged units.
3. **Quads, tripods, superheavies**, then anything left in `data/meks.zip` (LAMs are out of scope until
   Daniel says so).

## 7. Acceptance checks (all scripted, `python tests/run_checks.py`)

- `tests/test_token_joined.py` / `tools/token_audit.py`: 0 floating blocks, nothing below the ground
  (reference tags and name hash).
- A new hardpoint test over every unit in `data/meks.zip` that loads: every crit-holding item placed, no
  location over capacity, the shuffle stable for one name (same unit, same look).
- The volume band (section 4) per location; height on the rules curve.
- Real scale: missile tubes as now (`tube_px`); no shell plate thinner than a set minimum.
- Arm / torso and leg / leg penetration: 0 (the clip measure from the 2026-11-04 review; add it to
  `token_audit.py`).
- Engine results untouched: every reference log identical.
- Page size of the viewer stays publishable (under 16 MB; today about 7.5 MB).

## 8. Left to Daniel's eye (not scriptable)

Whether it reads as military hardware; shuffle variety vs chassis identity (a Hunchback must still read as a
Hunchback); plate thickness and layering; how the joint covers look.

## 9. Status (2026-11-04, end of phase 1)

Phase 1 is built and published for Daniel's review (Change Record "SKELETON-AND-SHELL BUILDER, PHASE 1"). Departures from this
spec, all recorded there: the volume band is 30 percent (25 failed on the pelvis plates and narrow side torsos); the old `_build`
and `calibrate` stay for units outside the range until phase 2; the 2D tokens of shell models project the same convex solids
the mesh uses. Phase 2 waits for Daniel's verdict.
