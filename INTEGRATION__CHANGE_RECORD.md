# Change Record (newest first)

Was Section 8 of `INTEGRATION__PROJECT_MAP.md`; moved to its own file on 2026-11-10 (Daniel: "clean up the
project map"), word for word. New entries go at the TOP of the list, signed and dated, with page cites.
An entry marked "REVIEW PENDING (higher-level model)" is waiting in PROJECT_MAP Section 0's REVIEW QUEUE.

*(Starts fresh 2026-08-28 — prior history archived/removed, not carried forward.)*

- **2026-11-18 (Claude, session 28), HD MODELS; THE CATAPULT IN HD. Art only. REVIEW PENDING (higher-level model).** Daniel:
  "Don't worry about polygon count. This will be the HD version that gets simplified later." `tools/lowpoly_hd.py` builds HD
  models into `reference_art/models_hd/` (`"detail": "hd"`: `lowpoly_ref.check` skips the 800-triangle budget, every other check
  stays; `tests/test_lowpoly_ref.py` checks them). The Catapult HD (8,272 triangles), from the same grid measurements: a rounded
  teardrop body in slices with panel seams, framed cockpit panes, the chin box with vents and the centre lasers, striped intakes,
  the hatch deck with its X, launcher arms with all 15 tube mouths, ribs and top hatches on ringed shoulder discs, side-torso
  lasers, belled jump-jet nozzles, the hip block with vents and ringed hip discs, rounded thighs to a rear knee cap, plated and
  vented shins, ankle joints, three-toed feet splayed 18 degrees. Its sheet: `reference_art/sheets/Catapult CPLT-C1 HD.png`. The
  800-triangle model is now noted as its simplification (`simplified_to`).

- **2026-11-18 (Claude, session 28), CATAPULT CPLT-C1 REFERENCE MODEL FROM THE AI FIVE-VIEW SHEET. Art only. REVIEW PENDING
  (higher-level model).** Daniel: "Using the 5 fold view of the catapult, build a model that matches its appearance ... the art is
  accurate enough, though you may need to compensate for it being art and not a technical drawing." `reference_art/models/Catapult
  CPLT-C1.json` (792 triangles, passes `lowpoly_ref.py check`: weapons and jump-jet locations as the record sheet), measured on a
  grid of the sheet: body sections from the side (heights) and top (half-widths) views; the LRM 15 arms on shoulder discs over the
  back third; lower-torso discs, hip block and hip discs; reverse-knee legs (knee 1.68 behind the hip); long feet splayed 18
  degrees; the hatch deck between the launchers. Compensations (in `art_vs_unit_file`): each view scaled to its own body-top
  height (the side view is drawn ~10 % taller); the raised launcher built level; medium lasers and jump jets, not drawn, placed
  where the record sheet's locations allow. Sheets: `reference_art/sheets/Catapult CPLT-C1.png`, `compare_Catapult CPLT-C1.png`.

- **2026-11-18 (Claude, session 28), ITERATION 4: THE RECORD SHEET BUILDS THE ARMS; BIRD KNEES BACKWARD; MEASURED PROPORTIONS.
  Art only. REVIEW PENDING (higher-level model).** Daniel, after the Catapult four-way comparison: "Where does the record sheet say
  the missiles are located?" (in the arms: the launchers ARE the arms); bird legs bend backward; legs / hip / lower torso / upper
  torso out of proportion; the Hunchback's arms off their shoulder sockets, arm weapons in line with the limb, the cannon built back
  over the legs. His principles, with their reasons, are now `reference_art/blocks/ASSEMBLY_PRINCIPLES.md` (read before changing
  the assembler). Rules (ITERATION 4 in `tools/lowpoly_assemble.py`): `lowpoly_ref.read_mtf` now returns every critical slot
  (`crits`); `arm_plan` builds each arm from its actuators (no lower arm: launcher -> it stands on the shoulder socket, gun -> a gun
  arm on a short upper arm, small weapons -> in line with the upper arm, empty -> a small pod; lower arm: launcher -> pod, gun
  without hand -> gun arm, else a forearm, a hand if the hand actuator is there, its weapons in line); the record sheet overrides
  the survey for arms; jump jets where the record sheet puts them (torso -> a back pack, legs -> packs on the shins); bird knees
  behind the hip; hip height = everything above it (1.0x light, 0.9x assault), pelvis 0.38x the chest, slung bodies 1.7x their
  height; arms on the shoulder socket (iteration 3's outward shift removed); in-line weapons sized by the limb's width; the cannon
  hump level and centred over the hips. All 136 builds one piece.

- **2026-11-18 (Claude, session 28), ITERATION 3: THE PROBLEMS THE ITERATIVE PASS LEFT OPEN. Art only. REVIEW PENDING
  (higher-level model).** Daniel: "Work on fixing those problems you listed." Rules in `tools/lowpoly_assemble.py` (ITERATION 3),
  table in `reference_art/blocks/comparison_pass1.md`: hose limbs keep their girth; slung bodies get 2x leg length; hips spaced by
  leg width (pelvis widened); a centre-torso launcher becomes the back rack (Jenner); launcher bays set 55 % into the chest
  (Javelin); heavy hunch chests wider and lower per ton, legs from the default chest height (Atlas, Charger, Cyclops, Zeus); arms
  hang from the shoulder block's outer part (clear of the body from above); armless slung bodies carry their arm launchers in
  side racks sized by them (Catapult, Stalker). All 136 builds still one piece. Open: the Stalker's body is small for its legs.

- **2026-11-18 (Claude, session 28), ITERATIVE PASS: THE 34 MODELS AGAINST THEIR DRAWINGS, AND THE ASSEMBLY RULES THAT CAME OF IT.
  Art only. REVIEW PENDING (higher-level model).** Daniel: "For each generated model, compare it to its original art. Make a list
  where they do not match. Use that list to improve the rules for how models are put together." The list, the patterns and the rule
  each became: `reference_art/blocks/comparison_pass1.md`. Rules in `tools/lowpoly_assemble.py` (ITERATION 1 / 2): legs from the
  chest (`leg_ratio(tons)`: 1.8 x chest height at 20 t to 1.35 at 100 t) and arms from the chest; limb thickness clamped below and
  growing with tonnage (legs tons^0.45); each arm's kind from the unit file's weapons in it (gun / missile pod / fist), a side the
  drawing names kept; torso blocks only on the sides the unit file arms, launcher grids sized by tube count, the cannon hump by the
  gun; the drawings build fills silent slots with the commonest block, not the name hash; shoulders <= 0.45 and heads <= 0.34 of the
  chest's height; forward gun arms 20 degrees down and <= 1.35 x a forearm. All 136 builds still one piece. Left for block or
  survey work (listed in the file): the Stalker's legs, the Jenner's back rack, the Javelin's chest bays, wide heavy chests,
  shoulder width from above.

- **2026-11-18 (Claude, session 28), WHOLE 'MECHS ON A SOCKET SKELETON; THE OLD ART PROJECT'S 3D VIEWER. Art only. REVIEW PENDING
  (higher-level model).** Daniel: "the Catapult render you showed has disconnected pieces. Any final render must have a socket
  system so that every block connects to the correct 'Bone'. Also blocks must sit flush to the surface they're on ... the Catapult's
  cockpit needs to be tangent to the surface it sits on ... steal the unit viewer from the original art project and render the
  mechs from this pass, plus their hashed appearance."
  - `tools/lowpoly_assemble.py`: a skeleton (hip-knee-ankle, shoulder-elbow-wrist, waist-neck; straight or bird legs, the pose from
    the shin) whose joints come from the blocks' own sockets. Blocks are placed three ways: FIT (a limb's solid spans its bone plus
    0.08 into each neighbour; it stretches along the bone, its thickness follows only up to 1.25x), PLUG (one socket on a joint),
    SEAT (a ray onto the host block: the anchor on the hit point, the mounting face turned to the surface normal: canopies tangent,
    heads, shoulders, knee and ankle discs, bays, racks, packs, antennas, fins, belly plates, arm guns). Stacked blocks SETTLE onto
    the real top of the block below. Two builds per unit: from the drawings (the taxonomy's seen_on; the most distinctive type when
    several; the name hash where the drawings are silent; no arms only on a slung body with no forearm drawn, as the Catapult) and
    name hash only (sha256 per slot, as INTEGRATION__shell_facet.pick). A jump-jet pack when the unit file jumps.
  - Fixed on the way: the skirt pelvis's waist socket was above its top (every torso on it floated); the drum foot's LOW had no
    ankle socket; the first fit left gaps at knees (blocks stop short of their anchors); stubby limbs swelled into drums.
  - CHECK: all 34 units x 2 builds x HIGH/LOW are ONE connected piece (solid-box contact graph), stand on y = 0, and every seat hit
    its surface; in tests/test_lowpoly_ref.py. The Catapult (drawings) is now one piece, its canopy tangent on its body.
  - VIEWER: tools/token_3d_template.html copied to tools/lowpoly_viewer_template.html (`lowpoly_assemble.py template` makes it:
    variant buttons From the drawings / Name hash / both at LOW, a new header and legend); the bones are a Skeleton layer (X-ray
    armor shows them). `lowpoly_assemble.py viewer OUT.html` writes the page (34 units, about 13 MB). tools/lowpoly_groups.py is
    superseded for whole 'Mechs (it placed some parts by hand).

- **2026-11-17 (Claude, session 28), BLOCK LIBRARY SECOND BATCH: THE REST OF THE TAXONOMY (46 BLOCKS), JUDGED FROM ABOVE TOO.
  Art only (reference_art/, private). REVIEW PENDING (higher-level model).** Daniel: "More reference material. Its from Megamek so
  technically it could be used, but I'd prefer not to to avoid confusion between our program and theirs. The main thought is that
  silhouette from above is just as important as from the front and back. ... use the same process to build the remaining blocks."
  - REFERENCE FROM ABOVE: his two zips of MegaMek top-down unit sprites (about 3,500). Only the base sprite of each cited unit is kept
    (`reference_art/megamek_sprites/`, 36 files, README says reference only, never our art, CC BY-NC-SA credit). Every block now
    carries `top_reference`, and its sheet shows the sprite beside the block's top view.
  - BLOCKS: 46 new (every type of `prune_1` that is a block, except hand/claw_clamp: no drawing shows one; recorded under
    `not_built` for Daniel). New generators: ski_plate, pedestal_block, three_toe_claw, drum_foot, bird_shin, barrel_limb (ribbed
    shin, barrel thigh, cylinder torso), joint_disc (knee disc, hip drum, ankle wheels, belly plate), ball_joint, guard_plate,
    thin_bar_thigh, pelvis_box (box and belt ring), skirt_wedge, slim_waist, turret_ring (waist ring and neck collar), faceted_belly,
    transverse_cylinder, dome_chest, slung_lozenge, hunch_block, wing_rack, cannon_hump, box_canopy, mask_skull, fighter_canopy,
    box_pauldron, limb_bar, heavy_sleeve, pod_arm, cuff, jump_jet_pack, rear_rack, long_barrel (single and twin), whip (whip and
    mast dish), fin_plate; modifiers on old ones: shin `greave` / `louvre` (greave and pillar shins), thigh `guard`, barrel arm
    `fin` / `muzzle_sides` (the Dragon's gun arm). References: 16 TRO drawings, the Dark Crow picture, and ONE AI sheet (the jump-jet
    pack: the drawings show no backs; marked provisional). Reworked after the first look (each verdict says why): three-toe claw
    (splayed spikes -> parallel blades), greave shin, bird shin, ribbed tube (rings -> vertical staves), knee disc (spokes), guarded
    thigh, transverse cylinder, mask skull (box -> egg head), fighter canopy, gun arm, belly plate (cross), ski plate. Crops moved
    for the box canopy, slim waist, whip and plain upper arm; the box pelvis's reference moved from the Spider to the Clint.
  - FROM ABOVE, THE FIRST DOZEN RE-JUDGED: the chest was a plain rectangle from above; it now has a prow (`prow` param), as the
    Commando's sprite. The others hold.
  - LOW: 14 blocks first failed the outline check (their LOW dropped a rib, lip or cap); fixed so LOW keeps what makes the outline.
    Thin parts (whip, dish, fin) carry their own minimum with a reason (`outline_min`). New LOW budgets = their count rounded to 8.
  - GROUPS: the upper arm and pelvis stand-ins are now real blocks; two new figures (a heavy, Atlas / Hunchback kit; a bird-legged,
    Catapult kit). LOW totals: Commando kit 750, Javelin kit 950 (OVER the 800 limit: the scaled shoulders, two bays and the gun
    arm), heavy 536, bird 550. Budgets need a pass before whole models.
  - The review page's images are JPEG now (the PNGs passed the 16 MB page limit).

- **2026-11-17 (Claude, session 28), BLOCK LIBRARY FIRST PASS (T15a): THE TAXONOMY PRUNED, THE COMMON DOZEN BUILT. Art only
  (reference_art/, private); no battle changes. REVIEW PENDING (higher-level model).** Daniel: "Begin a first pass at creating
  'Lego blocks' ... you must be able to show the exact image you used as reference material. After each block is made, compare
  your work to the reference material and decide if its close enough"; "Stick to the information in that branch" (session 27's
  `reference_art/`, merged into main with this work; the earlier token / shell art is on the back burner). His choices: Claude
  prunes and he checks; HIGH + LOW; the plan's common dozen.
  - PRUNE (`block_taxonomy.json` `prune_1`): every type gets form / preset / modifiers, or `merged_into` (20: duplicates such as
    foot/ankle_disc = ankle/ankle_disc and shoulder/fin_wing = fins_spars_wings/fin_plate; settings such as thin_rod = the limb bar,
    thinner; modifiers such as vented_belly = belly + vents). 93 types -> 60 blocks in 38 presets (slab 28, drum 17, bar 5, dome 5,
    wedge 2, claw 2, hull 1), 9 "no part", 4 one-unit specials, 36 modifiers + 15 settings. The drum family is one generator (the
    pod and the disc are its two settings). Nothing deleted.
  - BLOCKS (`tools/lowpoly_blocks.py`, `reference_art/blocks/library.json`): slab_boot, tapered_slab_shin, tapered_slab_thigh,
    boxy_chest_sloped_shoulders, shoulder_pod, shoulder_disc, launcher_bay, fist_arm, barrel_arm, fist, dome_helmet, bubble_canopy.
    References: Commando (7), Javelin (3), Dragon, Clint; each crop box recorded. HIGH 220-1,040 triangles, LOW 24-92; the LOW
    outline matches HIGH's by 0.87-0.99 (intersection over union, front / side / top; minimum 0.85). All twelve judged close
    enough; EIGHT were not on the first try and were reworked (boot, shin, thigh, chest, disc, bay, forearm, fist: each verdict
    says what was wrong). Rendering: a depth buffer (the face sort hid tube mouths behind their panel) and outlines only at
    creases, part edges and the silhouette (a faceted dome had read as a golf ball).
  - CHECKS: `tests/test_lowpoly_ref.py` runs the block check; `run_checks.py`'s art level now includes it.
  - CONNECTED GROUPS (Daniel: "So far I like the art. Can you take the separate pieces and show examples of connected
    groups of them?"): `tools/lowpoly_groups.py` snaps blocks at their anchors (`Assembly.add`: a block's anchor put on a world
    point, mirrored for the right side) into seven groups in `reference_art/blocks/groups/`: a leg, a fist arm, a gun arm, the
    Commando-kit and Javelin-kit upper bodies, and two whole figures. The upper arm and the pelvis have no block yet: drawn as
    plain light STAND-INS and named on each sheet. Per-body-part scales (`SCALE`, a first guess by eye) fit the pieces measured
    on different units together. Whole figure at LOW: 594 (Commando kit) and 794 (Javelin kit, two bays and a gun arm) triangles
    without the stand-ins, against the 800 limit: the Javelin kit is at the edge, so LOW budgets need a look before the rest.

- **2026-11-17 (Claude, session 28), HYDRA'S MAP-EDGE RISK MADE MANDATORY. Two Hydra reference logs re-recorded, one removed.
  REVIEW PENDING (higher-level model).** Daniel: "Avoiding the edge should be mandatory for Hydra with no way to turn it off."
  `hydra.rs`: the `HYDRA_EDGE_RISK` switch is gone; `would_be_chargers` / `edge_risk` always run. `check_rust_reference.py`:
  `FIRST_VERSION` no longer sets it, so the two first-version Hydra battles (`hydra_first_red__hy_4v4_lance_woods`,
  `hydra_first_blue__hy_8v8_valley`) now play the first version WITH the edge risk and were re-recorded (the 8 v 8 now goes to
  Red in 31 turns, was Blue in 37); `hydra_noedge_red__hy_duel_griffin` (the switch's OFF path) removed: 86 reference battles.
  The trial records `2026-11-17_hydra_trial_edge_off.jsonl` stay as the measurement of the change. Every other log unchanged.

- **2026-11-17 (Claude, session 28), HYDRA PRICES THE MAP EDGE; BACKLOG AUDIT; THE CHECKS PRUNED. Hydra battles change (meant to); 10 Hydra reference logs re-recorded, 1 added. REVIEW PENDING (higher-level model).**
  (1) HYDRA (Daniel: "you are allowed to fix your bot and update Hydra"): `hydra::would_be_chargers` / `edge_risk`, switch
  HYDRA_EDGE_RISK (on). For each spot, the best hit chance of an enemy still to move that can reach a neighbour from which its
  charge / DFA would push this unit off the board, times the unit's whole remaining strength, priced, is added to the spot's
  risk (INTEGRATION__HYDRA.md Section 7, "The map edge"). WHM v JVN, 100 battles a seating: Hydra Warhammer v Gladiator Javelin
  73 -> 82 wins (off-the-map losses 9 -> 0), v Hydra Javelin 68 -> 70 (10 -> 0); other seatings within noise. Team battles
  (`hydra_trial.py`, all 9 hy_ scenarios, 40 battles a seating, same seeds): Hydra v Gladiator 438 - 264 with it, 437 - 256
  without (per scenario +-6, noise). Reference logs: the 10 Hydra battles re-recorded; the two first-version Hydra battles
  set HYDRA_EDGE_RISK=false and are unchanged (only their header line lists the setting); new `hydra_noedge_red__hy_duel_griffin`.
  (2) BACKLOG AUDIT (Daniel: "see if anything else was fixed but not documented"), PROJECT_MAP Section 0: A8's "pushed off the
  board edge" was stale for Gladiator (priced since 2026-10-20: own push / charge / DFA by `displacement_worth`, the enemy's
  push in `move_eval`, the enemy's charge / DFA in the two-ply reply); C5's zip refresh obsolete (zip removed 2026-11-13); E2's
  next items (start positions, side swap, BV by skills) done; E2a item (1) the unit editor done; E4 "nothing built" wording
  fixed; E7 (a) save / open a run done in the Lab (btsim cannot open one; the file names no Lab version), (b) crashed battles
  are listed with seed and message, but their replay does not yet play up to the crash.
  (3) THE CHECKS PRUNED (Daniel's list of five): `tests/run_checks.py` picks checks by what changed since origin/main (docs ->
  none, art -> token tests, Lab pages -> website + Lab server, Python -> Python tests + Python reference battles, engine ->
  Rust + website + Lab server; `--list` explains; `--full` before every merge; `--python` weekly). Idea 1 (one battle run
  serving both the reference and the bridge parity check) was BUILT AND MEASURED, NOT KEPT as the default:
  `check_rust_reference.py --parity` (`btsim --bridge-parity --log N` now also gives each battle's result and log;
  `Scenario::run_bridge_checked` returns the log) took 434 s on a quiet 4-core machine, against 71 s for the plain reference
  run + 108 s for `check_bridge_parity.py --quick`: the parity replay of every full battle (8 v 8, 12 v 12 included) is the
  cost. It stays as a thorough option. Lab server 8 -> 4 battles a setup. The heavy checks run one at a time (they fought
  over the cores before). `--full` on a quiet 4-core machine: 239 s (reference 71, bridge quick 105, cargo tests 1, Lab server 10, website 53), all
  pass; the old run_checks took about 500 s with the Python included. The Python set passed this session (weekly run done).
  CLAUDE.md and PROJECT_MAP updated.

- **2026-11-17 (Claude, session 28), WHM v JVN: CAUSES OF DEATH BY BOT - HYDRA IS CHARGED OFF THE MAP EDGE. No code changes.**
  Daniel: "Did you look at the cause of death breakdown for each unit by bot?" (not at first). The same 900 battles through the Lab
  (identical results). The Warhammer's deaths by its bot (v the Gladiator Javelin): Gladiator - CT 10, head 5, legs 4...; Princess -
  CT 30, GYRO 11 (the rear hits above), engine 6...; Hydra - DISPLACED OFF THE BATTLEFIELD 9, CT 9... Off-the-map losses: Hydra
  Warhammer 9 of 27 (v Gladiator JVN) and 10 of 32 (v Hydra JVN); Gladiator Warhammer 1, Princess 3. The rule is right (Core p.113
  and the charge / DFA / push rules: a 'Mech displaced off the battlefield is destroyed): in battle 2 (Hydra v Gladiator) a nearly
  whole Warhammer (238 of 267) on the east edge is charged from the west for 6 damage and is gone. Both the Gladiator and Hydra
  Warhammers end 15-21% of their turns on an edge hex, but the Gladiator one is charged off once in 100 battles and the Hydra one
  8-9 times (almost all by a charge): Hydra's mover does not price being charged or pushed off the map (backlog A8 lists the same
  gap for Gladiator's scoring; its two-ply look-ahead seems to cover it in practice). The Javelin dies by head hits in 14-18% of
  battles (plausible: a PPC or a punch to its head is fatal). For Daniel: whether to price the board edge in Hydra's mover (Hydra
  is COMPLETE, 2026-11-12, so this reopens it).

- **2026-11-17 (Claude, session 28), COMBAT LAB ROUND: FULL POWER, CANCEL, WIDER TEAMS, MAP PAGE, WALK-ON ZONES, WEB MAPS; WHM v JVN STUDY. Battle results change only for walk-on starting zones (Lab zone modes; no reference battle uses them). REVIEW PENDING (higher-level model).**
  Daniel's list. (1) FULL POWER: a box beside CPU threads (Options > Run) = every core, with the warning "turns the rest of your
  computer into a potato"; it greys the threads box (`full_power` in the setup; `runs::threads_for(.., full_power)`, `engine.js`
  `autoThreads`). (2) CANCEL RUN: beside the progress bar (renamed) and in the status bar beside the battle counter (shown while a
  run plays). In the browser it now stops AT ONCE: the workers are ended mid-battle (`Player.stop`) and fresh ones start for the next
  run; a battle cut off is not counted. The desktop stops dealing new battles (those under way finish, under a second each). (3)
  TEAM COLUMNS WIDEN: grips between the team columns and the Unit Browser, dragged sideways (kept in the layout; double-click or
  Reset layout clears). (4) NAME SEARCH: "jav r" already listed only names holding every word; now covered by the test. (5) WEB
  MAPS: boards with bridges, fuel tanks or elevators (or a terrain name the reader does not know) are left out of the website (18
  boards); the 50x50 BigBlank is added (`tools/build_web_lab.py`). (6) MAP PAGE: one click on a board previews it ("Previewing ...,
  double-click to choose"), a double-click chooses it; a board added to the map list goes on TOP (so the preview shows it; Random map
  too); the map list is a table, so its up / down / remove buttons line up. (7) WALK-ON ZONES (ENGINE, `deployment.rs`
  `entry_segments` / `zone_entry_band`): a side box (N, E, S, W) enters from that whole edge; a corner box from the two edges meeting
  there, each to its half-way point (the middle hex of an odd length in both); the centre from nowhere. Before, a box entered only
  from the border inside its own third. The map preview now draws exactly those hexes: the DEPLOYMENT_DEPTH band solid, the extra rows
  out to DEPLOYMENT_STUCK_DEPTH faint and dashed ("only for a unit stuck in the first rows"), with a legend; placed zones still shade
  their boxes. `engine/core/tests/zone_entry.rs` (in run_checks). (8) IDEAS LIST (no action): dynamic maps (elevators), water
  movement - PROJECT_MAP C7. TESTS: `check_web_ui.py` 65 checks (Full power at 5 core counts, "jav r", web boards, preview v choose,
  map list order and alignment, entry hexes, the grip, Cancel from the status bar mid-run); `check_lab_server.py` checks automatic
  and full-power threads. All 61 checks pass.
  SIDEQUEST (Daniel: WHM-6R v JVN-10F, ~100 battles a seating, the three bots): `round_robin.py`, Grassland 1, home edges, 100-turn
  cap, Warhammer always Red. Warhammer wins / Javelin wins by (WHM bot, JVN bot): G-G 75-24, G-P 79-20, G-H 72-28, P-G 41-59, P-P 74-26,
  P-H 54-45, H-G 73-21, H-P 83-17, H-H 68-29. ANOMALY: with Princess driving the Warhammer, Gladiator's Javelin WINS (59%). In those
  battles 43% of the Warhammer's volleys are at range 1 (its PPCs' minimum range; Gladiator / Hydra Warhammers: 6%), it fires 1.96
  weapons a volley (others 2.5), the Javelin sits in its side or rear arc (its left side 429 times v right 30, so the torso guns
  cannot fire), and 32% of the Javelin's hits land on its rear armor (others 13-15%). Princess's movement score for the Warhammer
  carries a "close range" bonus of ~17 and a facing term that is 0 in 1,352 of 1,356 moves. Not changed: the Princess clone follows
  MegaMek; whether real Princess plays a PPC boat this way is a question for the MegaMek bridge (E4). No engine fault seen.

- **2026-11-17 (Claude, session 28), COMBAT LAB: CAUSE OF DEATH -> ITS BATTLES; CORES LEFT FREE AND LOWER PRIORITY; A TEST SUITE FOR THE WEBSITE. No battle result changes. REVIEW PENDING (higher-level model).**
  Daniel (browser version first): (1) "If we need a test suite go ahead and make it." NEW `tests/check_web_ui.py`: headless
  Chromium clicks through the website as a person would (41 checks: tabs, Unit Browser search, two unit sheets from the eyes, map
  preview, Options search, a batch from the Run button, the cause-of-death click checked battle by battle against the run's own
  record, Survived, Show all, a replay, the core rule at 1 / 2 / 4 / 8 / 16 reported cores; no page errors). It rebuilds `web_lab/`
  when any of its sources is newer. `run_checks.py` now runs it and then `check_web_lab.py --battles 4` (browser = desktop) as one
  "web" line; exit 77 (no node / Playwright / wasm32 target) is a NOTE, not a failure. (2) "If you click on a mech's cause of death
  in results it filters to those battles": each row of a unit's "How it ended" table (Results > Unit statistics) is a link; a click
  puts one unit condition in the Find battles form (that unit, destroyed, that cause; or survived for the Survived row) and the
  list and statistics show only those battles. The match is EXACT (new `cause_is` in the filter, `runs::matches` and the demo's
  `demoMatches`), so "Engine Destroyed" never also picks a longer cause containing those words; editing the cause text by hand goes
  back to the old every-word match. (3) "The number of cores it uses needs to conform to normal windows program priority
  management instead of being purely greedy" (City of Heroes crashed when a run started). The threads box's 0 now means
  AUTOMATIC: every core but a quarter of them, at least one left free (16 -> 12, 8 -> 6, 4 -> 3, 2 -> 1), in the browser
  (`engine.js` `autoThreads`) and the desktop Lab (`runs::threads_for`, batch and estimate); a typed number is used as before, up
  to the core count. The DESKTOP Lab also asks Windows to run it at below-normal priority (`main.rs` `lower_priority`:
  `SetPriorityClass(BELOW_NORMAL_PRIORITY_CLASS)`, every battle thread inherits it; `nice +10` elsewhere; no new library), so
  other programs get the processor first. A web page cannot lower its own priority; leaving cores free is what it can do.
  Checked: `cargo check --target x86_64-pc-windows-gnu` builds; on Linux the Lab runs at nice 10; all 61 checks pass. The
  Combat Lab website artifact (claude.ai/artifact/TxziRWUqF5gU96Bof16r3p) is updated; the public GitHub Pages copy is NOT (E6:
  Daniel's call), and no new Windows download was packaged.

- **2026-11-17 (Claude, session 28), REVIEW OF SESSION 27 (2026-11-15: unit browser, Units page, unit sheet and editor stages 1-3, website unit filter). No code changes.**
  Every check passes on `main` (60 of 60, incl. the 86 Rust reference battles and the bridge parity check). ENGINE PARTS, judged
  safe: (1) `mtf_parser.rs` `normalize_type_text` (letters and digits only) and the new spellings (Standard Armor, Light / Heavy
  Ferro-Fibrous, Ferro-Fibrous Prototype, Stealth Armor, Endo Steel Prototype) read as Standard, as their old spellings did; Stealth
  armor keeps its effects (BV and heat read `armor_desc`, not the type). (2) The `LA IS:17` structure lines: none of the 4,227 library
  files has a key the reader could mistake for one (scanned); the editor writes every location at once, so the 200 t fallback rows
  are never used for a location left out. NOTES, not bugs: (a) the editor's construction numbers (engine sinks = rating / 25, the 10-sink
  minimum, armor up to 2 x structure, head 9, double heat sink sizes 3 / 2, MASC size) are from memory, not the library; they only
  raise warnings, the TechManual is not indexed, and TO:AUE's patchwork-armor example agrees on the 2 x structure maximum. Treat them
  as placeholders until the TechManual is in. (b) The website filter drops only units the PARSER warns about; units whose equipment
  loads but runs on a loud stub (TAG, C3...) stay listed: Daniel's call whether those count as "unmodeled". (c) `tests/check_web_lab.py`
  is not part of `run_checks.py` (it needs the wasm32 target); run it by hand after any change to `engine/wasm` or `describe.rs`.
  (d) The Python parser does not know the new spellings or the IS lines (Python retired; no effect on the Rust answer key). (e) These
  nine entries had never been put in the REVIEW QUEUE; marked reviewed here. The low-poly reference work (branch
  `claude/youthful-euler-vv1pfc`, not merged) stays queued: its own check passes; the likeness is Daniel's to judge.

- **2026-11-16 (Claude, session 27), LOW-POLY REFERENCE MODELS: TOOL, INDEX AND A TEST BATCH OF THREE. REVIEW PENDING (higher-level model).**
  Daniel: redraw the TRO 3025 'Mech art as strict low-poly models (boxes, wedges, 6/8-sided prisms, under 400 triangles, one neutral
  A-stance) as reference for the Combat Lab's block dictionary and override list; models go straight to 3D, no image-generator step.
  (1) The 34 drawings were pulled from the PDF (one per odd page) into `reference_art/originals/`; `units.json` names each from its
  title bar and ties it to its exact unit file (all 34 exist in `data/meks.zip`) with weapons and jump jets from the file. (2)
  `tools/lowpoly_ref.py`: the primitives (box, wedge, bar, tube), the five-view renderer (front, rear, left, right, top, one scale; `--iso`
  adds a 3/4 review panel) and `check`, which tests each model against its unit file (every weapon in its location, jump-jet locations,
  mass, triangle budget, the required assemblies, feet on the ground). `tests/test_lowpoly_ref.py` runs it. (3) Three models built:
  Commando COM-2D, Javelin JVN-10N, Spider SDR-5V (336-352 triangles each); each carries `features` in the field names of
  `data/token_reference_tags.json` (so the override list can take them as they are) and notes where the drawing and the unit file
  differ. (4) PRIVACY: `reference_art/` is on `publish_public.py`'s `PRIVATE_PATHS`; its tree check compared whole trees, which a
  private folder in `main` would break, so it now compares the files outside the private paths (`public_files`). Known limits:
  the renderer sorts faces by depth (fine for separate convex parts, may mis-order where parts interlock); the likeness is by eye
  from one drawing per unit (side and rear views are inferred). Art only: no engine code touched; only the art checks were run.
  UPDATE same day (after Daniel compared Gemini sheets): Daniel, "perfectly happy to cheat on that '95 look" (retro look, modern
  tools, animation later), so the triangle limit is 800 (was 400) and `tools/lowpoly_ref.py` gained two part kinds, `hull` (convex
  hull of points: sloped plates) and `dome` (ellipsoid or flat-based cap: round chests, canopies, helmets). The Spider (dome chest,
  large fins, from Gemini's reading), Commando (chest plate, heavy forearms, dome helmet) and Javelin (leaning hull chest, big
  canopy dome) were reworked: 370-442 triangles.
  LATER SAME DAY: (a) Javelin rebuilt twice (zoomed reading found the two chest missile bays; Daniel's good AI views added the skirt
  plate, brimmed canopy and dish): 706 triangles. (b) The AI turnaround sheets for all 34 units are filed in `reference_art/ai_sheets/`
  (Daniel's note: good for silhouette and the ways a part can be drawn, unreliable for exact detail); per-unit faults are in
  `units.json` `ai_sheet_caveats`. (c) `reference_art/block_taxonomy.json`: a survey of the block types per body part (22 parts, 88
  types, 10 WTF items), all WTF items answered by Daniel. (d) `compare` command in `tools/lowpoly_ref.py`. (e) Hand-off T15 in
  `INTEGRATION__TASK_SPECS.md`. (f) DECISION: build the block library BEFORE the other 31 models, with levels of detail from the
  generators (LOD0 high, LOD2 the 800-triangle reference): the three built models are raw shapes, not dictionary blocks.
  END OF SESSION 27 (2026-11-16/17): (g) The taxonomy now has 93 types over 22 body parts (Daniel's 16 parts plus neck collar, ankle,
  back deck, weapon mount, antenna, fins/spars/wings); his rulings on the ten WTF items are applied (the round side disc is the
  shoulder; the Stalker's head is a fighter canopy on top of the torso; the UrbanMech's head is the dome over a cylindrical torso;
  Jenner and Cicada have small weapon pods for arms; the Quickdraw's wheels are ankle discs; the Hunchback's ribbed barrels are lower
  legs; the Catapult is a bird leg; the Dragon's big barrel is a gun arm). (h) MOUNT POINTS: every block is to carry weapon,
  equipment and greeble mounts (Daniel: the JagerMech's shoulder blade is a greeble), fixed or hinged, in `mount_points` and
  `greebles`. (i) The DARK CROW (a modern David White picture, `reference_art/extra_art/`; unit file: the base Dark Crow) added five
  types and showed that the block hierarchy must be a default, not a law (its arms mount on the lower torso, its side torsos carry
  hinged guards). (j) PRUNING POLICY (`pruning_policy`): types as form x preset x modifiers, an admission test (a different
  silhouette AND 3+ units, or named iconic by Daniel), core / candidate tiers (80 / 13), about six presets per part, new art
  classified against the presets with only the residual logged for Daniel to prune; Daniel: the 400+ pieces are TRO PDFs and the
  real bottleneck is generating Gemini turnaround sheets, so the plan is to classify from the originals first and use Gemini only
  where the residual is large (a five-unit pilot would test that). (k) DATING (`dating`): unit year (the unit file's `era:`, on all 4,227
  files), tech base and art source as three separate tags; `years_seen` computed on each type; NOT used to pick blocks yet because
  the 34 units span 2475-2898 but share one book's art. (l) SOURCE BOOK: TRO 3025 and 3026 were merged into TRO 3039 (Daniel), so
  both names are right; the README says so (an earlier draft here wrongly called "3039" a mistake for a while). NOT DONE: no PR to
  `main` (the work is on the session branch, pushed); the block library and the other 31 models (task T15); the prune of the drum
  and slab families; `publish_public.py` not run since the private-path change.

  Daniel: "any units with unmodeled equipment should be removed from the website version... They will be built eventually", and a
  checkpoint (merge to main, update the actual website). `tools/build_web_lab.py` now leaves out every unit the engine warns about
  for equipment it does not model (`warnings` from `describe.rs`: an unknown component, an unmodeled armor or structure type, or
  special rules only partly modeled): 324 units, on top of the 23 the engine cannot play, so the website lists 3,905 of 4,252 units.
  The desktop Lab keeps them all. To put a class of unit back, change `UNMODELED` in that file. `check_web_lab.py` passes on the
  new build. The sheet editor in the browser still lists the whole equipment catalogue (a unit built in the editor from unmodeled
  equipment is the user's own doing).

- **2026-11-15 (Claude, session 27), WEBSITE: UNITS WITH UNMODELED EQUIPMENT LEFT OUT; CHECKPOINT. REVIEWED 2026-11-17 (see the review entry above).**
- **2026-11-15 (Claude, session 27), EDITOR ROUND 3: EYE PREVIEWS, "NEEDS A PLACE" TRAY, DHS FIX, THE SPELLING WITCH HUNT. REVIEWED 2026-11-17 (see the review entry above).**
  (1) BUG: the heat sink warning counted each slot of a double heat sink (the equipment database lists one as 1 slot);
  `itemsOf` now gives a heat sink item its real size (inner sphere double 3, clan double 2). (2) EYE COLUMN: the Preview button is
  gone; a fixed eye column in the Unit Browser opens that unit's sheet (read only); several can be open at once to compare (each
  sheet is its own window with its own state, `createSheetWindow`; previews are 720 px wide and open against the right edge so the
  eyes stay clickable). The fixed `#sheet` window is gone. (3) "NEEDS A PLACE" TRAY (Daniel: items that still need a place, to be
  dragged where you want them): chips in a tray under the slots; equipment can be sent there from the picker; choosing MASC puts its
  slots there, and choosing an armor or structure type puts the Endo / Ferro slots it asks for there (one chip with a count);
  drag a chip into an empty slot (it must have room in a row), drag a placed item to another slot or back into the tray (fixed
  parts and actuators cannot be dragged); a "still need a place" warning stays until the tray is empty. PLACEHOLDER, LOUD: the MASC
  slot count (tons / 20 inner sphere, tons / 25 clan, rounded) is from memory and shown as a placeholder in the sheet; replace it
  when the TechManual is indexed. Armor changes only add the Endo / Ferro slots so far (no per-location armor types, no
  slot-taking special armors). (4) WITCH HUNT (Daniel: "random spaces, capitalization"). The two "Hardened Clan" entries were the
  Advanced search lists comparing exact text ("Hardened(Clan)" 6 units v "Hardened (Clan)" 1); the engine already ignored spaces,
  hyphens and capitals. The lists now fold spellings together (`uniqueTypes`, `typeKey`). The engine now reports its own
  complaints per unit (`warnings` in `describe_unit`; `tools/unit_witch_hunt.py` groups them): 811 of 4,252 units warned; 685 had an
  armor type text it did not recognise (`Standard Armor` 237, Light / Heavy Ferro-Fibrous 235, Stealth Armor 13...) and 184 a
  structure type; they all read as Standard, as the recognised spellings do. `mtf_parser.rs` `normalize_type_text` now keeps letters
  and digits only (fixes `Standard((Unknown Technology Base))`) and `Standard Armor`, Light / Heavy Ferro-Fibrous, Ferro-Fibrous
  Prototype, Stealth Armor and Endo Steel Prototype are named: same result (standard), no warning. Warnings left: 329 units,
  chiefly types the sim does NOT model (Industrial / Heavy Industrial / Commercial / Primitive armor, Industrial structure: they
  read as Standard) and 285 units with a component the equipment database does not know (e.g. IS Wrecking Ball). Open for Daniel:
  whether those should be built, and the remaining spelling splits in the files themselves (Endo-Steel / Endo Steel, 4 armor
  groups) that the lists now hide.

- **2026-11-15 (Claude, session 27), UNIT EDITOR IN THE BROWSER BUILD, AND CONFIG. REVIEWED 2026-11-17 (see the review entry above).**
  Daniel: quirks, role and omni pods are fluff (not built); CONFIG matters; nothing extra for the BV-v-win-rate research (the user
  does it with the editor). (1) Config: a Biped / Quad / Tripod list converts the location blocks (arms <-> front legs with
  shoulder = hip ... hand = foot, legs <-> rear legs, the centre leg added or removed), the armor and structure line keys, and
  the Config line (an Omni suffix is kept); refused when a slot that would be lost holds equipment. A quad Locust played 3 battles.
  (2) THE BROWSER (WASM) VERSION HAS THE EDITOR. It was never impossible: this container only lacked the wasm32 target
  (`rustup target add wasm32-unknown-unknown` works through the proxy; an earlier note here that it could not be built was wrong).
  `describe_unit`, `equipment_list` and `unit_structure` moved to `engine/lab/src/describe.rs`, shared by the desktop Lab and
  `engine/wasm`; the wasm module answers `unit_eval` and `equipment_list`, holds a setup's modified units under `_modified/<hash>.mtf`
  in its memory files (`plan_of`), and `engine.js` answers `unit_text` from the data block; `unit_eval` goes through a worker
  (`worker.js` "eval") so a text that crashes the engine stops only that instance. `tests/check_web_lab.py` has a "modified unit
  (text in the setup)" battle set (browser = desktop, battle for battle) and 5 editor checks; all pass. The published website
  artifact was rebuilt and updated (data block as base64, the host serves no .gz).

- **2026-11-15 (Claude, session 27), UNIT EDITOR STAGE 2: A .MTF EDITOR, MODIFIED UNITS ARE TEMPORARY. REVIEWED 2026-11-17 (see the review entry above).**
  Daniel's notes on stage 1. DESIGN: this is an editor for fun and research, not a designer; legality is never checked, the aim
  is only that anything it makes plays in the engine (Daniel: "an Atlas that moves at 6/9... does the BV increase equal a change in
  win rate?"). CHANGED: (A) no Download .mtf and no unit file is ever written: "Use this design" puts a MODIFIED unit in the team
  carrying its whole text (`mtf` in the team entry, `mtf_text` in the setup, named "<name> (modified)"); the engine reads it from a
  scratch file `data/_modified/<hash>.mtf` (emptied at start, git-ignored, never in the unit list); a saved run file carries the
  text, so saving the run is the only way to keep one (`runs.rs`, `catalog.rs scratch_unit`, `main.rs save_run`); `add_unit`'s
  overwrite option from stage 1 is gone. (B) Every popup window goes on top when it opens or is clicked (`raiseWindow`, one counter
  shared with the floating panels). (C) Heat sinks, jump jets and structure slots (Endo Steel, Ferro-Fibrous) are never forced:
  too few in the slots is a warning with a "Place N" button; Override is gone. The only hard rule is that equipment fits the
  slots. (D) Heat sinks and the other items can be taken out; only shoulder, hip, upper arm / leg, lower leg, foot, sensors, life
  support, cockpit, engine and gyro cannot; the lower arm and hand actuators are check boxes in their slots. Engine, gyro and cockpit
  are lists (engine: Fusion, XL, XL Clan, Light, XXL, XXL Clan, Compact, ICE, Fuel Cell) that rebuild their slots, with the counts read
  off the unit files; no room = refused with the reason. (E) Head and legs show 6 slots (the files pad them to 12). (F) The paper
  layout: head on top; left arm, left torso, centre torso, right torso, right arm; left leg (centre leg), right leg. (G) Equipment
  is picked from folders: Energy, Ballistic, Missile, Physical, Other, and Ammo, which lists only the ammo of weapons on the unit
  ("Show all ammo" overrides). Also editable: chassis, model, tonnage (cap 200 t, Daniel: "if the engine doesn't like units over 200,
  cap it"), tech base, structure / armor / myomer type, internal structure by hand. "Use tonnage" rounds the tonnage up to a
  multiple of 5 and fills in the table row of the nearest tonnage (10-200). ENGINE: `mtf_parser.rs` reads optional `LA IS:17` lines
  (one per location) before the tonnage table, so a tonnage between the table's steps plays (102 t); a file without them reads
  as before and nothing over 200 t plays. Also fixed: a comment had swallowed the restore of the thread count and turn cap in
  `restore()`. TESTS: `check_lab_server.py` (inline unit runs and stays out of the list; 102 t refused without / read with the
  lines; 250 t refused). NOT YET: quirks, role, config (biped / quad), omni pods, per-location armor types, ammo counts; the engine /
  gyro / cockpit slot layouts cover the common types only; the equipment list has no tech-base filter; the browser (wasm) version.
  RULES TO CHECK in the library: engine-held sinks = rating / 25, the 10-sink minimum, armor = 2 x structure (head 9).

- **2026-11-15 (Claude, session 27), UNIT SHEET AND EDITOR, STAGE 1 (superseded by stage 2 above where they differ: no file is written) (Daniel's list item 1). REVIEWED 2026-11-17 (see the review entry above).**
  Daniel: a unit in the browser shows its stats; on a team the values become editable with mild construction limits and an
  override; the one hard rule is that equipment must fit the critical slots; BV follows the design; custom units without a file
  download; "for science", illegal designs welcome. BUILT: (Rust, `engine/lab/src`) three calls, `unit_text` (a unit's file),
  `unit_eval` (the engine's reading of an edited text: BV, whether it plays, each location's internal structure; it reuses
  `describe_unit`, so the BV is the one a battle uses) and `equipment_list` (699 items: slot name, kind, tech, slots, tons, heat,
  damage, BV, every spelling the engine resolves); `add_unit` takes `overwrite`, allowed only on a file the editor made (it
  carries "Edited in Combat Lab"), never on a published design. (Page, `lab.js` "unit sheet and editor") what is edited is the
  unit's own .mtf text, changed line by line so nothing the page does not understand is lost. The Unit Browser's Preview opens the
  sheet read only (header, movement and heat, armor with internal structure and maximum, every location's critical slots,
  equipment totals). The pencil on a team row opens it editable: Walk MP (the engine rating follows: Walk x tons), Jump MP, heat
  sinks and their kind, armor front and rear, equipment placed by choosing an item and clicking an empty slot (multi-slot items
  need that many empty slots in a row; clicking a placed item takes it out). Heat sinks beyond what the engine holds
  (rating / 25) and jump jets (one per MP) are items in the slots, placed and removed automatically; with no room the change is
  refused unless "Override construction limits" is on, which sets the number anyway. Checks shown: sinks v slots, fewer than 10
  sinks, jets v Jump MP, rating over 400, armor over twice the internal structure (head 9). Weight is NOT checked. "Use this
  design" saves a new unit file (model name + " (custom)", changeable) in the project's unit folder, which also puts it in the
  unit list, and swaps it into the team keeping the pilot skills; "Download .mtf" gives the file. Checked: in a real browser
  (preview, edit sinks / jump / a weapon, refused 150 sinks, save into the team; BV 2175 -> 2433 -> 2472), an edited Atlas played 4
  battles with no crash, `check_lab_server.py` has 6 new checks. NOT YET: the browser (wasm) version has no editor (its
  `engine.js` says so; it needs the same three calls in `engine/wasm`); the demo shows the sheet and editor for a few units but
  cannot recalculate BV; no from-scratch "new unit" and no tonnage / structure-type / engine-type editing; Clan-versus-IS item
  filtering; quirks, omni pods and armored components are left as the file has them; the 23 LAMs do not load. RULES TO CHECK against
  the library (not yet cited in the code): engine-held sinks = rating / 25, the 10-sink minimum, armor = 2 x structure (head 9).

- **2026-11-15 (Claude, session 27), DEMO MAP PREVIEWS. REVIEWED 2026-11-17 (see the review entry above).** Daniel: the Map tab shows no
  previews. Demo only: it had no answer for the "board" request. `tools/make_lab_demo.py` now embeds every board's text
  (`board_texts`, about 4 MB; the page is 7.7 MB) and `lab.js` `demoApi` answers "board" from it. The real Lab was fine.

- **2026-11-15 (Claude, session 27), UNITS PAGE ROUND 2: SIZES, COLUMNS, TRIANGLES, TIDIER BROWSER. REVIEWED 2026-11-17 (see the review entry above).**
  Daniel's notes after the first look. Pages only (`lab.js`, `lab.css`, `index.html`) plus `tools/make_lab_demo.py`. Narrow
  (phone) screens: the browser is one screenful (80% of the height, 640 px at most) and its list scrolls inside it. Docked team
  panels pull taller or shorter by their bottom corner (height kept in the layout; double-click the title to clear it; floating
  panels already resized). Browser: Clear selection beside Weight class, Advanced search beside From file, the unit count at the
  bottom. The list fills the window to the bottom of the screen and stays so until its bottom corner is pulled; then it keeps that
  height (kept in the layout; Reset layout clears it). Team lists: half a line under the last unit. The start line shrinks its
  text (down to 7 px) to stay on one line, wrapping only below that. Every column header can be resized by dragging its right
  edge (double-click resets; widths kept per table kind; a resized table is fixed-layout and may scroll sideways). A sorted
  header shows an up / down triangle. The "walk from 1 shows no units" report was the DEMO only: `make_lab_demo.py` kept just a few
  fields per unit (no walk, jump, armor, role...), so every search on the others matched nothing; it now keeps them all; the real
  Lab matched 4,229 units. Checked in a real browser at 1920x1080 and 420x800; no page errors. Daniel's longer list (unit
  editor, TacOps options, Total Warfare ground units, unit icons) is recorded in PROJECT_MAP E2a.

- **2026-11-15 (Claude, session 27), UNITS PAGE: SCROLLING, DYNAMIC COLUMNS, LESS CLUTTER ON THE TEAM PANELS. REVIEWED 2026-11-17 (see the review entry above).**
  Daniel's list items 4, 7 and 5. Pages only (`lab.js`, `lab.css`, `index.html`; no engine change). (4) Teams 3 and up could not be
  reached: the side columns squeezed the team panels instead of scrolling; `.col > .win { flex: none }` keeps each panel its height
  and the column scrolls. (7) The Unit Browser table always shows Unit, Tons and BV; the other columns (`COLS` in `lab.js`: Move,
  Armor, Sinks, Year, Role, Type, Rules, Tech, Armor type, Structure, Book, and a Weapons count) appear only while the advanced
  search uses them, and a sort on a column that went away falls back to the name. Heat sinks is a new column. (5) The team panel is
  now colour / name / bot, the zone line and the unit list. Adding moved into the Unit Browser, MegaMek style: an "Add to" team
  box, "Add selected (n)", "From file...", and a double-click on a unit adds it to that team (dragging onto a panel and dropping
  a .mtf file on one still work). The panels' "Quick add" search is gone (the browser's name box does that). The starting zone on a
  team panel is a line of text and checkboxes ("Start: NW N NE W C E SW S SE, Walk on"); the Map page's grid is unchanged.
  Checked in a real browser (6 teams scroll; columns appear with the search; add, double-click and the zone boxes work, no page
  errors). `tests/check_web_lab.py` could not run here (no wasm32 build target in this container); `check_lab_server.py` passes.

- **2026-11-15 (Claude, session 27), UNIT BROWSER SHOWED ARMOR 0 - FIXED. REVIEWED 2026-11-17 (see the review entry above).**
  Daniel: "Unit browser is showing units with armor 0?" Cause: `engine/lab/src/catalog.rs` `describe_unit` summed only
  `"<loc> Armor:N"` lines (capital A), but 1,557 of the library's 'Mechs write `"LA armor:N"` in lower case, so they summed to 0.
  Now one case-insensitive sum of every `"<location> armor"` line (front and rear; the bare `armor:` type header is still left
  out). Results for capital-A files are unchanged. Catalog only, no engine change. `tests/check_lab_server.py` now fails if any
  listed unit has no armor. `check_lab_server.py` passes.

- **2026-11-14 (Claude, session 26), A NEW STARTING SEED EACH RUN BY DEFAULT. REVIEW PENDING (higher-level model).**
  Daniel: "Starter seed + time used to generate the seeds is a more random plan." Pages only (`lab.js` `freshSeed`, `index.html`):
  the Options page's seed box now starts empty ("new each run"); an empty box makes each run a new starting seed (random bits
  mixed with the clock, under 2^52) that is written into the run's setup, so the saved file and every replay still use the exact
  number; the Results progress line shows it. A typed seed is used as it is. Old saved settings holding the old default 1 become
  empty. The engine is untouched (`PcgDice::battle_seed` as before; every reference battle and `btsim` run keeps its fixed seed).
  NOT PUBLISHED (Daniel: not yet): the public site still has the old default of 1.
- **2026-11-14 (Claude, session 26), COMBAT LAB WEB BUILD PUBLISHED AS A WEBSITE; ALPHA LABEL. REVIEW PENDING (higher-level model).**
  Daniel: put the web version on the public repository as a public website, and call the program alpha. Added `tools/publish_web_lab.py`
  (the build as the one commit of the public repo's `gh-pages` branch for GitHub Pages; checks: only the expected files, no email
  address), "ALPHA" in the title bar, a banner and About text (lab.js / index.html), a README note with the site address, and
  `engine.js` now accepts a data pack a host already decompressed. See INTEGRATION__COMBAT_LAB_WEB.md "Publishing".
- **2026-11-14 (Claude, session 26), SUGGESTION / BUG REPORT BUTTON AND A REPLAY-FIRST RUN FILE. REVIEW PENDING (higher-level model).**
  Daniel: a report button that flashes when a run fails and opens the open repository's issue page with instructions to post
  the run's save file; the save file "more about the exact setup and seed ... especially the seeds for failed runs";
  one button for suggestions and bugs. Done: `runs.rs::export` now leads with `build` (git hash, `COMBATLAB_BUILD`, stamped by
  `tools/build_web_lab.py`), `platform`, `batch_seed`, `seed_rule` (battle n's seed; battle 1 = the batch seed), `setup`,
  `crashed` (sim, seed, message, board, zones) and `capped` (battles that hit the turn cap), then the statistics (`lines`);
  old files still open (same keys). `lab.js` / `index.html` / `lab.css`: status-bar button "Suggestion / bug report", flashing
  while the open run has crashes (steady red under reduced motion), a dialog with the steps and two links to
  `github.com/Logajam/battletech-combat-lab/issues/new` (constant `ISSUES_URL`) prefilled with the setup, batch seed and up to
  ten crash seeds; the run file now saves as `.json.txt` (GitHub issues accept .txt, not .json). Checked: `check_lab_server.py`
  and `check_web_lab.py` pass; the flash, the link text and the new keys were looked at in the browser build with a faked crash
  (no real crash was available). NOT CHECKED: that Issues is switched on for the public repository; `package_lab.py` does not
  set `COMBATLAB_BUILD` yet (desktop files say "unknown").
- **2026-11-14 (Claude, session 26), COMBAT LAB IN THE BROWSER (WebAssembly; the visitor's computer plays the battles). REVIEW PENDING (higher-level model).**
  Daniel: "Front load it so that the users computer is the one actually doing the work ... prune out all the maps that aren't
  standard 16x17 ... any other simplifications that would make it lighter." Built: `engine/wasm` (crate `combatlab_wasm`, the
  engine plus `lab/src/runs.rs` by path as one `.wasm`, plain exports, no wasm-bindgen), `engine/wasm/web` (`engine.js` = the
  page's end of the Lab's api: coordinator instance for the statistics + one Web Worker per core; `worker.js`; `wasmio.js`),
  `tools/build_web_lab.py` (-> `web_lab/`, static), `tests/check_web_lab.py`, `INTEGRATION__COMBAT_LAB_WEB.md`.
  ENGINE CHANGES (results identical, full suite 60 of 60 incl. the 86 Rust reference battles): `SetupPaths.memory` /
  `MemoryFiles` / `defaults_text()` in `core/src/scenario.rs` (files from memory instead of disk; desktop path untouched);
  `runs.rs`: `Run::external` / `add` / `finish`, `play_one`, the clock and rayon parts compiled only off wasm32; `lab.js`: two
  `window.LAB_WASM` hooks (api, replay page). PRUNED: boards to 16x17 only (356 -> 200), unit-file fluff lines (18.6 -> 11.9 MB),
  units the engine cannot play; all in one 0.84 MB gzip block; the module is 1.7 MB gzipped. CHECKED in headless Chromium: four
  setups (Gladiator 2 v 2; Princess v Hydra with a packed unit; two boards stitched; a shuffled map list with random zones)
  give every battle identical to the desktop Lab (seed, winner, turns, damage, causes of death); replay page builds. SPEED:
  browser about 1.8x slower than native (9.4 s v 5.1 s for 20 battles on 4 cores). NOT DONE: dropping a unit file in
  (`add_unit`; needs `describe_unit` out of the desktop-only `catalog.rs`); not in `run_checks.py` (needs a browser).
- **2026-11-14 (Claude, session 26), SESSION LOCKED IN AND COMBAT LAB ALPHA-2 PACKAGED.** Daniel: "lock everything down so its saved in house ...
  regenerate the program and give me a download link ... send it to Opus for review before pushing it to the public repo." The
  session branch was merged to `main` of this private repo (pull request 224); nothing went to the public repo. `tools/package_lab.py
  --version alpha-2` built `CombatLab-alpha-2.zip` (4.6 MB, Windows exe cross-built with MinGW; the packaged data was checked by
  running the Linux build inside the unpacked folder: 4,252 units, a battle with zones, statistics, options.json and availability.json
  served; the Windows exe itself was not run, there is no Wine here). Put on the `downloads` branch beside alpha-1 (README updated).
  What alpha-2 holds is every CL11-CL21 entry above. Open for Opus: CL18's live conditions; the review of everything marked REVIEW PENDING.
- **2026-11-14 (Claude, session 26), REPLAY HEAT MAPS: PRINCESS'S MEMORY, BY TEAM AND BY UNIT (CL21, Princess first). REVIEW PENDING (higher-level model).**
  Daniel: "Replay is built from the seed rerunning that game. For any given step, the heat map can be recalculated from the
  state of that game at that step"; per unit, "princess's heat map limited by the potential movement range of that unit".
  Done exactly so, with nothing saved: the history is itself produced by playing the battle again from its seed, and
  `history.rs::heat_now` reads Princess's team memory (`princess_memory.rs`: the BV-weighted record of where her team's
  units have stood, decayed each turn) at every step into a separate `heat` list beside `steps` (same length; written
  only when a team has Princess units; the Python-record test drops it). Each entry also carries each standing unit's
  reach: its run MP, or jump MP when larger, as a straight hex distance (terrain ignored). The Replay has a "Heat map" box:
  Off / a team (its whole map) / one of its units (the team map limited to the hexes within that unit's reach, with a dashed
  circle). Orange, stronger = more weight. Checked on a 2 v 2 Princess battle: the box lists both teams and their units, a unit
  share shows only its reachable part. NOT DONE: Gladiator's move score and Hydra's price per hex (need CL6/CL7); reach
  does not follow terrain or facing costs, so a unit's share can include hexes it could not actually reach.
- **2026-11-14 (Claude, session 26), COMBAT LAB RESULTS: CAUSES, ARMOR AND STRUCTURE APART, UNIT STATISTICS, SAVE / OPEN A RUN FILE (CL18 standard parts, CL19, CL20). REVIEW PENDING (higher-level model).**
  NOT DONE, saved for Opus (Daniel: "may be a save for Opus to think about"): CL18's live conditions - the user builds a
  condition before the run ("3+ gyros lost in one turn") that triggers as battles happen; the sheet in
  INTEGRATION__COMBAT_LAB_V2_TASKS.md says what it must settle (condition language and builder, evaluation per turn in the
  engine without slowing the hot path or touching dice, how a hit is stored so it replays, what a condition may see).
  ENGINE (results only; no rules touched; reference logs and all 60 checks unchanged): `Battle.tally` (`battle.rs`) counts per
  unit and weapon the shots, hits, damage to the target's armor + structure, and the turns it fired in (`run_ranged_phase`
  around each resolved attack), kills by weapon fire (a unit destroyed while that attack resolved), and turns standing at
  the start of each turn; `SideStats` (`results.rs`) gets armor and structure apart (rear armor counts as armor), per
  location now / at the start, kills, turns alive and the weapon table, filled in `start_battle` / `finish`. Not counted:
  physical attacks, charges, falls, pushes (no weapon, no kill credit); pooled cluster damage (POOL_CLUSTER_DAMAGE, off).
  LAB SERVER (`runs.rs`, `main.rs`): battle lines carry the armor / structure pairs and each unit's detail; the battle
  list sends them slim; `results` returns `causes` (every cause of death and how many units, "Pushed off the battlefield"
  among them: it answers Daniel's pushes question) and, on `unit_stats: true`, per unit: how it ended as a share of
  battles, armor and structure left per location (average and share), kills, per weapon shots a battle, accuracy, damage
  a turn (over every turn the unit stood) and use (share of standing turns it fired in). `save_run` writes one file (setup,
  every battle line, crashes with seed, map, zones, and the .mtf files the setup used that are not in the packs);
  `load_run` reads it back as a finished run (replays are played again from the seeds). A battle that crashes replays into
  the same crash and says so in words.
  PAGES: team statistics show Armor left and Structure left as two figures; the finder's cause box lists the causes seen;
  a "Unit statistics" folder (team > unit > tables) under the statistics; Save run / Open a run file buttons at the top of
  Results (opening offers to put the run's setup back into the Units, Map and Options pages); crashed battles listed with
  seed, map, zones and a Replay button. Checked: 20-battle runs through the API and the page; a saved run reloads with an
  identical summary and replays battle 3. Limits: every battle line holds its units' detail in memory (a 100,000-battle run
  is large: the file too); loose boards are not put in the file (map-pack boards are); a crash's partial log is lost.
- **2026-11-14 (Claude, session 26), REPLAY LOG READS ONE UNIT AT A TIME, ONE WEAPON AT A TIME (CL17). REVIEW PENDING (higher-level model).**
  Presentation only (`INTEGRATION__replay_viewer.html`, `regroupRanged`; no engine change, results identical). The engine
  writes a firing phase in its resolution order (every unit's to-hit rolls, then every hit's damage, then the piloting rolls).
  The Replay now regroups that step as people read it (Daniel: "declare fire, roll fire, apply damage one unit at a time"; the
  flow follows MegaMek's own game log as he described it; MegaMek's log was not opened): the first unit to fire, each weapon
  in the order it fires with its roll, and under a hit the hit's whole result (location, damage, armor / structure, crits,
  cluster groups) before the next weapon and then the next unit; at the end, "[End of the phase: piloting rolls and what
  failed ones did]" lists each unit's PSR trigger, roll, result and the fall damage in turn. Firing stays simultaneous: it is
  the same recorded lines re-sorted, nothing replayed. A checkbox ("one unit at a time, one weapon at a time", on by default)
  switches to the engine's order. Safety: each declared hit must pair with the next damage block of the same weapon; if
  anything does not pair, the step is shown as the engine wrote it. Checked on 81 ranged-phase steps of four 3 v 3 battles
  (Gladiator and Princess): every step with an attack regrouped (the only non-regrouped steps had no attack lines). Not
  done: the Physical phase and the Results page's text logs are not regrouped.
- **2026-11-14 (Claude, session 26), RULES-OF-PLAY: A SALVO FIRES BIGGEST HIT FIRST (CL16). RESULTS CHANGE; REFERENCE LOGS UPDATED. REVIEW PENDING (higher-level model).**
  Daniel: "fire the weapons that deal the most damage to one location first, then in descending order of cluster size - the
  AC/20 before the SRM-6 even if the unit lists the SRM-6 first" and, when asked about a switch, "Its just the correct order":
  so it is the rule, with no setting. `attack_resolution.rs::finish_declaration` now sorts a declaration's weapons before
  their to-hit rolls are made and their hits applied: key 1 = the most damage one hit puts into one location (a missile
  rack's grouping: SRM 2, LRM 5; any other weapon its whole damage per shot), key 2 = the cluster (rack) size, both larger
  first, equal keys keep the unit's listed order (`salvo_key`). The attack stays one simultaneous salvo; only the order of
  rolls and applications moves. Every bot is covered (Gladiator, Princess, Hydra share the path); a changed order is
  logged ("[Ranged] Red fires in order: [...]"). The frozen Python answer key keeps the listed order, so its fixtures are
  marked with a hidden `_FIRE_ORDER_LISTED` (the cargo tests' fixture loaders: `tests/common/mod.rs`, `cl2_history.rs`,
  `stage6_battles.rs`); `Scenario::load` and the Lab do not set it. `check_rust_reference.py --update` was run (Daniel: "If
  we have to rerun the reference battles so be it"): 86 battles, over all of them mean length 24.6 -> 23.8 turns, hit
  rate 38.5% -> 40.2% (one seed each: a feel, not a study; `ab_batches.py` has no switch to compare, so a before/after
  needs the old binary). THE BRIDGE PARITY CHECK found a real gap on the way: `armored_slots` (changed by crits) was missing
  from `bridge.rs` UNIT_FIELDS; added (cov_hvac now passes). Not changed: Gladiator's declaration search still chooses
  WHICH weapons by expected damage as before; this only orders the chosen ones.
- **2026-11-14 (Claude, session 26), COMBAT LAB: MAP TAB - PREVIEW, HEIGHT COLOURS, STARTING ZONES, MAP LIST (CL14). REVIEW PENDING (higher-level model; the engine part is the one to look at).**
  PAGES: whole-map preview under the chosen board (a `board` request returns the file's text; the page draws it), heights
  in a MegaMek-style colour ramp (dark green low, yellow, brown, white high) with water / woods / road / rough / building
  laid over; stitched maps previewed whole. Starting zones: a 3 x 3 grid per team (NW N NE / W C E / SW S SE; Edge = the 8
  outer boxes, Anywhere = all 9, Clear), a Walk on check box (Centre and Walk on switch each other off), a small copy of
  the grid on every team panel (same state), and one dropdown for the run: Core Rulebook (initiative roll; the default,
  nothing changes) / Fixed / Rotating / Random. Rotating: battle k, team i takes the whole zone setup (boxes + walk-on) of
  team i-(k-1), wrapping (2 teams swap every battle). Random: one box drawn from the team's highlighted ones, fresh each
  battle. "Keep teams opposite" (random, 2 teams only: greyed with a tag for 3+): team 2 gets the mirror box (k -> 8-k). Map
  list: boards the battles cycle through, "Playlist order" or "Shuffle" (a fresh order each pass); the battle list shows
  each battle's map and zones; "Load by seed" has a Battle number box (rotation and the map list depend on it).
  ENGINE (`deployment.rs`, `orchestrator.rs::deploy_zones`, `scenario.rs` Scenario now Clone): a new path used ONLY when the
  setup has a DEPLOY_ZONES setting; without it a battle starts exactly as before (all 60 checks pass, the 86 Rust
  reference battles unchanged). Walk-on: entry hexes = the border bands (DEPLOYMENT_DEPTH deep) inside the zone's boxes, a hex
  must be able to reach the centre box (the old "stuck" rule, widened to DEPLOYMENT_STUCK_DEPTH). Placed: a free enterable
  hex of the zone, spread so no two units touch where possible, facing the middle of the board, one dice pick per unit. Lab
  server (`runs.rs`): a `Plan` builds one scenario per map of the list and, per battle, the zone assignment (the Lab's own
  splitmix64, a pure function of the setup, battle number and seed, so a battle replays); battle lines and crash records
  carry `board` and `zones`. Checked end to end through the API: 4 battles, rotating zones, two maps, replay shows
  "placed at 1310 in zone E" / "walks on in zone W (6 entry hexes)". `tests/check_lab_server.py` passes.
  Known gaps for the reviewer: no per-zone minimum separation or bot-chosen placement (placed units are drawn at random);
  placed units of different teams may share a zone and are spread by the same rule; a 'Mech that cannot get out of its zone
  stops the battle with a panic (caught as a crash record); no results filter on map or zone yet (CL18).
- **2026-11-14 (Claude, session 26), COMBAT LAB: UNIT BROWSER FILTERS (CL13). REVIEW PENDING (higher-level model).**
  The Advanced search popup now has Mekbay-style filters: number ranges (tons, BV, walk, jump, armor points, heat sinks,
  year introduced), tech base, armor type, structure, unit set, source book, configuration / role / rules level boxes,
  weapons carried (name and a minimum count, several at once), a "Playable only" switch, Clear all, and named saved
  searches (kept in the browser). New table columns: Move (walk/run/jump), Armor, Role. The catalog
  (`engine/lab/src/catalog.rs`, cache version bumped) now reads those details from each .mtf's header and weapon list
  (no engine call). FACTION AND YEAR: `tools/make_availability.py` reduces MegaMek's RAT-generator data (mm-data
  `data/forcegenerator` + `data/universe/factions`; attached read-only, public) to `engine/lab/web/availability.json`
  (47 PLAYABLE factions x 39 era tables; 3,409 'Mechs; 750 KB; built into combatlab), following `RATGenerator.java`:
  own entry, else parent faction(s), else General; rating 0 = unavailable. Simplifications, all stated in the tool:
  a game year uses the nearest earlier era table (MegaMek interpolates), the + / - rating shifts and an entry's start
  year are ignored, only 'Mechs listed by MegaMek can match a faction filter (3,025 of 4,252 of ours). CREDITS.md has
  the entry. Checked: Atlas AS7-K appears for DC in 3067 and not in 2700; DC 3025 = 280 units, 3067 = 1,048; the Lab server
  check passes. Engine untouched. Not done: weapon names are the file's ids made readable by a rule, not the engine's own
  names; "Omnimech/OmniMek" configuration spellings are separate boxes; no faction-rating (A-F) filter.
- **2026-11-14 (Claude, session 26), COMBAT LAB: OPTIONS TAB (CL15). REVIEW PENDING (higher-level model).**
  Options tab = sub-tabs (Game setup, Bot features), folders inside them (Run, Deployment, Rules, Placeholders,
  Technical; one folder per bot: Gladiator, Princess, Legate, Hydra), a search box over all of it (each sub-tab shows
  its hit count, folders with hits open), a "changed" tag and per-option Reset, and Reset all. The list is generated:
  `tools/make_options_registry.py` reads engine/defaults/config.json plus the comments in INTEGRATION__config.py and
  writes `engine/lab/web/options.json` (built into combatlab: rerun it and rebuild when settings are added). A setting is
  ACTIVE when the Rust engine reads it by name; the rest are listed greyed with a "not active yet" tag (about 60 of 125,
  mostly Python-only: kill curve, stack, peril blend, cohesion, rendering, debug). Hydra's switches are Rust constants,
  not settings, so its four are listed greyed. The Lab server (`runs.rs::apply_options`) lays a setup's `"options"` over the
  defaults for the run, refusing an unknown name, one the Lab sets itself (seed, turn cap...) and a wrong kind of value
  (it would panic a worker); `tests/check_lab_server.py` has four new checks (passes). Engine code untouched, results
  identical with no options. Known roughness: choice-type text options are free text (valid values are in the
  description); the "not read by the Rust engine" test is by name, so a setting read through a built-up name would be
  wrongly greyed (none found).
- **2026-11-14 (Claude, session 26), COMBAT LAB: WINDOWS AND THE UNITS TAB REBUILT (CL11, CL12). REVIEW PENDING (higher-level model).**
  Pages only (`engine/lab/web`); no engine code touched, so only the Lab's own check ran (`tests/check_lab_server.py`,
  all passed) plus screenshots at 1400 and 600 px. The page no longer scrolls: each column and tab page scrolls its own
  content. Units tab: Battle / Estimated runtime / Run Simulation in a row across the top; odd teams left, even right,
  the Unit Browser permanently open in the centre; advanced search is a movable popup. Each team's Add selected /
  From file / quick add sit above its list (they no longer move as units are added; Add selected greys instead of
  hiding). Weight-class icons (original inline SVG) with a grip mark on every unit row. Any panel floats when its title
  bar is dragged (resize at the corner, double-click the title to dock, Reset layout button; kept in the browser); a
  narrow screen stays docked in one column. Three unit files with no chassis/model line showed blank names: they now
  show the file name. Not yet: zone grids (CL14), the rest of the Mekbay filters (CL13), the other tabs as windows.
- **2026-11-13 (Claude, session 26), RULES: PUSHES CHECKED (Core p.83). One reference battle changes (team_12v12_princess_v_gladiator, updated). REVIEW PENDING (higher-level model).**
  Daniel: "Think pushes might need a double check. Can't target a Charge or DFA. Can be mutual. But if both succeed they
  cancel out" - the displacement, not the fall check ("Succeed but are not canceled out for the fall check") - "And they
  recieve bonus damage to the score function if the target would fall off a cliff." Checked against p.83:
  (1) a push target that is charging or making a DFA: already refused (`physical::push_option`). OK.
  (2) MUTUAL PUSH - BUG: `resolve_pushes` cancelled whenever exactly two pushes succeeded in the phase, whoever they were.
  Now only a pair pushing each other cancels: neither moves, both still make the push PSR; any other push resolves as
  usual. (3) ONE CHARGE, DFA OR PUSH PER TARGET A TURN (p.83) - NOT ENFORCED: two 'Mechs could charge (or DFA) one target, a
  charged 'Mech could be pushed, two 'Mechs could push one target. Now `movement_attacks::already_charged_or_dfad` (in
  `can_be_attacked` and `push_option`) and `Battle::pushed_this_phase` (filled as pushes are declared, emptied at the start
  and end of the Physical Attack Phase; carried in the bridge state) refuse a second one. The changed reference battle was
  exactly this: Blue 5 and Blue 9 both pushed Red 11, and the old code took it for a mutual push; now Blue 9 kicks.
  (4) Pushes also follow p.76's "already displaced" rule (an earlier push moved one of its 'Mechs: no displacement, the
  target's PSR stands). (5) Score: a push is worth the target's whole armor + structure off the board, the fall damage
  2+ levels down (p.115: 10% of tonnage, rounded up, x (levels + 1)), else 0 - already so (`displacement_worth`). OK.
  NEW tests in `engine/core/tests/charge_targets.rs` (4 in all). `resolve_pushes` made public for them.
  Daniel's Asymptote set (seed 2, 100 battles) re-run: no crash; Red 93, Blue 7 (was 92 / 8); 23 battles changed
  (four Asymptotes often gang up on one target with pushes and charges, which the one-per-target rule now limits).

- **2026-11-13 (Claude, session 26), RULES: DISPLACEMENT WAITS UNTIL EVERY PHYSICAL ATTACK IS MADE (Core p.76). Battle results change where a phase has a charge or DFA with another displacement (none of the 86 reference battles; 5 of Daniel's 100 Asymptote battles). REVIEW PENDING (higher-level model).**
  Daniel: "please bring it in line". Core p.76: all physical attacks are made at the same time, so a charge's, DFA's or
  push's displacement happens only after every attack of the phase is resolved; a 'Mech about to be displaced still makes
  and receives its attacks. Ours displaced as each attack resolved (pushes, then each charge's damage + displacement, then
  each DFA's). NOW: `charge::resolve_damage` / `dfa::resolve_damage` deal every charge's and DFA's damage from where the
  'Mechs stood, and only then `resolve_pushes`, `charge::resolve_displacement`, `dfa::resolve_displacement` move anyone
  (`physical::run_physical_units`; the order among displacements is unchanged: pushes, charges, DFAs, each in declaration
  order). The book does not say what a displacement does when an earlier one already moved one of its 'Mechs: a charge
  then displaces nobody, the target still makes its +2 PSR, and the charger (if it was not itself moved) advances into the
  hex it charged - MegaMek's handling of a charge target that is no longer there (`TWGameManager.resolveChargeAttack`); a
  DFA's target is not displaced / does not step aside again, and the attacker still lands in that hex. Both logged
  ("... was already displaced this phase ... (p.76)"). NEW test in `engine/core/tests/charge_targets.rs`. Daniel's set
  (seed 2, 100 battles) re-run: no crash; Red 92, Blue 8 (was 93 / 7); battles 21, 30 (Red -> Blue), 35, 71, 73 changed.
  The Python (retired) keeps the old order.

- **2026-11-13 (Claude, session 26), FIX: TWO 'MECHS COULD CHARGE EACH OTHER (Combat Lab crash). Battle results change only where this happened (none of the 86 reference battles). REVIEW PENDING (higher-level model).**
  Daniel's report: a 100-battle Lab run (12 Inner Sphere 'Mechs, Hydra, v 4 Asymptote IIC iJ Mpulse, Hydra; 16x17 Desert
  Hills; base seed 2; Red listed first) crashed in battle 73 (seed 5376118808176116898): "index out of bounds: the len is 1
  but the index is 18446744073709551615" at `attack_resolution.rs:113` (`attack_side`). Cause: Blue 2 and Red 4 had each
  declared a charge on the other. Blue 2's charge resolved first, pushed Red 4 off the board and moved Blue 2 into Red 4's
  hex; Red 4's charge on Blue 2 then had both 'Mechs in one hex, so no line of sight to take a direction from. The rule
  (Core p.78): a charge is declared in the Movement Phase and the charger's movement ends only in the Physical Attack
  Phase, so a 'Mech making a charge or DFA can't be the target of one; a charge target must have finished moving (Daniel:
  "2 units can't charge each other. Only units that have completed their movement are valid charge targets"). Our check
  counted a charger as "moved". FIX: `movement_attacks::can_be_attacked` (the one check behind every charge / DFA target:
  Hydra, Gladiator's move_select, `charge::can_charge`) refuses a target whose `charging` or `dfa` is set. NEW
  `engine/core/tests/charge_targets.rs` (in run_checks). Daniel's set re-run with btsim: no crash; battles 1-3, 72, 74 equal his
  list; battle 73 now Blue in 28 turns (Red 93, Blue 7). The Python (retired) is not changed. Seen in passing (not
  changed): Core p.76 says charge / DFA / push displacement waits until every physical attack of the phase is resolved,
  while ours displaces as each one resolves; with this fix two of them can no longer involve the same pair, but a charge
  on a 'Mech that another 'Mech's charge displaces is still resolved after the move. Noted for Daniel.

- **2026-11-13 (Claude, session 25), COMBAT LAB: BV FOLLOWS THE PILOT'S SKILLS. No battle result changes. REVIEW PENDING (higher-level model).**
  Daniel: "BV should update when piloting and gunnery change"; and "Lets refine before making it too public" (the public
  download link waits for a refined version, PROJECT_MAP E6). The unit list's BV is the gunnery 4 / piloting 5 value; the
  server sends the engine's skill table (`battle_value::SKILL_TABLE`, now public) and the page shows each unit's BV for its
  pilot, floor(BV(4/5) x factor + 0.5), and the team's total, updating as a skill changes. NEW
  `engine/core/tests/bv_skills.rs`: that equals the engine's own battle_value for every unit file in data/ at every
  gunnery and piloting 0-8 (in run_checks).

- **2026-11-13 (Claude, session 25), THE PUBLIC COPY: tools/publish_public.py. No code changes. REVIEW PENDING (higher-level model).**
  Daniel made the public repository github.com/Logajam/battletech-combat-lab and said the real work stays in this private
  one. NEW `tools/publish_public.py [--push]`: this repo's full main history, rewritten with git filter-repo (the `rules/`
  path out of every version; any non-public author / committer email -> Daniel's GitHub no-reply address), checked (no
  private path, no private email, latest files identical to main), then pushed. Dry run: 645 commits, all checks pass, and
  the same result as a hand-made rewrite (deterministic, so later publishes add on top). First push waits on the Claude
  GitHub App's access to the new repository (Daniel).

- **2026-11-13 (Claude, session 25), RULEBOOK TEXT REMOVED; TOWARD A PUBLIC REPOSITORY. No code changes. REVIEW PENDING (higher-level model).**
  Daniel: "Make sure it does exist in the rules repo before nuking it, but otherwise remove it and sanitize the combatlab repo
  so we can make the repo publicly viewable." Checked first: all 73 files of `rules/Battletech_Rule_Reference_Index.zip` are in
  `logajam/battletech-rules-index` main (70 word for word; the other 3, storage-map / pipeline workflow / index manifest, are
  only longer there). Removed the zip; CLAUDE.md, PROJECT_MAP, README, RULES_REVIEW, TASK_SPECS T9 now point at the rules
  repo, cloned outside this one, with a standing rule: no rulebook text in this repo. Audit of the rest (every version): no
  keys or passwords; no other rulebook text (page cites and our own summaries; Daniel's IO pastes were summarised); no PDFs or
  images ever; files deleted over time are our own. The equipment tables are now credited to MegaMek in CREDITS.md. Daniel's
  personal email is on 9 commits. Going public: PROJECT_MAP E6.

- **2026-11-13 (Claude, session 25), LICENCE AND CREDITS. No code behaviour changes. REVIEW PENDING (higher-level model).**
  Daniel: "Go ahead and add it to the project" (GPL v3, recommended against his criteria: no work to use, protects the people
  whose work we used, no one can claim it and block others, reverse engineering welcome). NEW `LICENSE` (GNU GPL v3 text,
  identical to MegaMek's LICENSE.code), `CREDITS.md`, `licenses/CC-BY-NC-SA-4.0.txt` (from MegaMek's release, for the data),
  `THIRD_PARTY_LICENSES.txt` + `tools/third_party_licenses.py` (46 Rust libraries, all MIT / Apache-2.0 / similar), `license =
  "GPL-3.0-or-later"` in the three Cargo.toml, the About box in the Lab, the files in the Combat Lab package, a README row.
  MegaMek's licensing guide was read for what it asks (credit, non-commercial data, its trademark and fan-project notices).

- **2026-11-13 (Daniel), COMBAT LAB STAGE 1 REACHED.** Daniel ran CombatLab-alpha-1 on his own Windows PC: "That seems to work.
  There will be so many small tweaks needed to polish it, but we have achieved stage 1, It works." Speed, measured the same day:
  the Lab plays a batch as fast as btsim (Atlas v 12 Wasps, 20 battles on 4 cores: 63 s v 58 s, identical results).

- **2026-11-13 (Claude, session 25), COMBAT LAB ALPHA FOR WINDOWS. No battle result changes. REVIEW PENDING (higher-level model).**
  Daniel: "get it from Demo to Alpha status to something I can download and use" (he wanted to try 1 Atlas v 12 Wasps). NEW
  `tools/package_lab.py OUT_DIR --version V`: cross-builds `CombatLab.exe` (target x86_64-pc-windows-gnu, MinGW; only Windows
  system DLLs), and zips it with engine/defaults/config.json, data/ (*.mtf, *.board, maps.zip) and the unit pack as ONE xz block
  (`data/meks.pack.xz`, 0.77 MB against meks.zip's 7.6 MB; `catalog::unpack_solid` makes meks.zip from it on the first start;
  crate `lzma-rs`): 4.3 MB. `SetupPaths::find` now takes the nearest folder at or above the program that holds
  engine/defaults/config.json (the repository root, or the unpacked package). Tested under Wine: the package starts, unpacks
  4,227 pack units (4,252 in all), serves the pages, plays 1 Atlas AS7-D v 12 Wasp WSP-1A (the Wasps won 20 of 20, about 2 lost).
  Daniel's next-version notes (start positions per team, a side swap for N/S v E/W balance, BV following the skills) are in
  `INTEGRATION__COMBAT_LAB.md` Part A.

- **2026-11-13 (Claude, session 25), COMBAT LAB SECOND PASS: DANIEL'S NOTES AFTER TRYING IT. No battle result changes. REVIEW PENDING (higher-level model).**
  Daniel tried the demo page: deleting a team's units was a dead end (the File button opens the computer's file picker, which the demo
  refused); "Number of teams ... 64 as a minimum cap"; pick colours; a unit filter with drag-and-drop into teams; stitched maps; a
  10,000-battle list must not be one long list; a results filter. Built: teams uncapped with a colour picker (colours reach the replay:
  the viewer reads the record's `colours`); the Unit Browser window (filters, sort, drag onto a team, "Add selected"); the demo reads
  dropped files; stitched maps (`runs::scenario_of` takes a board grid); `results` filters (winner, turn cap, turns, a unit destroyed /
  survived and its cause) with statistics of the matches, and returns the battle list in ranges (the page nests it). Checked in a
  browser: drag from the browser, 8 teams, a stitched map, 250 battles nested and filtered; a 12-team free-for-all plays. His later
  ideas are in `INTEGRATION__COMBAT_LAB.md` Part A ("Daniel's notes after trying the first Lab pages").

- **2026-11-12 (Claude, session 25), COMBAT LAB CL2-CL5: A LAB PROGRAM WITH PAGES - SET UP TEAMS, RUN, SEE RESULTS, WATCH ANY BATTLE. No battle result changes. REVIEW PENDING (higher-level model).**
  Daniel: "Go ahead and begin working on CombatLab" (after "something I can interact with as a normal person who does not code").
  CL2: NEW `history.rs` - a battle's full history in the replay viewer's own format (`btsim --history N`, `Scenario::run_history`,
  `history::page` builds the viewer page from it); equals the Python's replay record for all 63 fixture battles
  (`tests/cl2_history.rs`; `port_record.py --replay-data`, written by port_fixtures.py); recording changes nothing (same results,
  byte-identical repeats). `Log::printed` marks bare prints, which the Python's record left out. CL3: NEW crate `engine/lab`
  (`combatlab`): a local server (standard library, 127.0.0.1 only) answering the pages' JSON requests - the unit list (data/ and
  data/meks.zip, 4,252 units with Battle Value) and board list (356, data/maps.zip included), estimate from pilot battles, batches
  on their own threads with progress / cancel / results, any battle's history, a dropped unit file copied into data/. Check
  `tests/check_lab_server.py`: its battles equal btsim's for the same setup and seed (in run_checks). CL4: the pages
  (`engine/lab/web`, Windows 3.x look per Part B): Units (2-6 teams, bot per team, unit search, skills, estimate, Run), Map,
  Options, Results (win bar, statistics, battle list). CL5: the Replay tab is the viewer over CL2's history, by battle or by
  seed; smooth at 12 v 12. Demo page for Daniel: `tools/make_lab_demo.py`. Spec sheet notes: COMBAT_LAB_SPECS "CL2-CL5 as built".

- **2026-11-12 (Claude, session 25), MEGAMEK BRIDGE B3-B5: OUR ENGINE PLAYS IN MEGAMEK. No battle result changes in our engine. REVIEW PENDING (higher-level model).**
  Daniel: "Work until the task is complete." Java: `GameView` (the game's start as settings; each unit as MegaMek knows it), `HydraBridge` now
  asks our engine for move order, the move (steps from the new `path_steps` call, else MegaMek's own path finder; standing up with GET_UP), the
  target and weapons (by address -> MegaMek's mounted item; torso twist), punches and kicks; everything else a counted fallback to Princess.
  `DecisionProcess`: a transcript of every line per game and a 120 s answer limit. `BridgeLauncher`: standings saved during the game (MegaMek
  resets a finished game), the winner by Battle Value left. `tools/megamek_bridge_games.py`: N games, one MegaMek start each, a stalled start
  played again, a summary. Rust (`bridge.rs`): `apply_megamek_view` (destroyed slots through the new `damage_resolution::destroy_slot_quietly`),
  start-of-turn bookkeeping and `hp_log` kept by the decision process, the mover's blocked / occupied hexes set and cleared as the engine does,
  the move queue read from the state. MEASURED with the new view mode (`--bridge-parity --bridge-view`, `BRIDGE_VIEW_EXTRA` to probe): decisions
  from MegaMek's facts alone order the same as the battle's - Hydra duel movement 96% / weapons 100%, Hydra 4 v 4 movement 90% / weapons 100% /
  physical 90%, Princess 4 v 4 80% / 99% / 85%. Found on the way: a mover's blocked-hex list left in place (a crash in 4 v 4s), hexes moved,
  `hp_log`, the move queue, weapons fired this turn - each now carried or kept. Games (Hunchback duel, Hydra as Red): v MegaMek's Princess 2 wins,
  4 draws of 6, every decision our engine's; draws are standoffs (MegaMek's bots hold their start hex; Hydra waits at the edge of range - MegaMek
  agrees on the line of sight and range, logged side by side). Spec Section 3d.

- **2026-11-12 (Claude, session 25), COMBAT LAB CL1: A SCENARIO BUILT BY RUST FROM SETTINGS, NO PYTHON (also the MegaMek bridge's start). No battle result changes. REVIEW PENDING (higher-level model).**
  Daniel: "Continue with the build" (and "a lot of this is needed for CombatLab"). NEW `Scenario::from_settings` + `SetupPaths` (scenario.rs),
  `engine/defaults/config.json` (the Python's settings, dumped as the fixtures were), `setup::roster` (moved from tests/stage6_attach.rs),
  `btsim --setup FILE [--write-scenario DIR]`, and the bridge's start line takes `{"settings": ...}`. Check `engine/core/tests/cl1_setup.rs`: all
  fixtures built from their settings equal their Python-built units.json and board.json (in run_checks). Daniel asked about the "background
  planner" the bridge bot needed: MegaMek's Precognition, a thread that works out every unit's reachable hexes and ECM while the opponent moves
  so Princess answers at once; a speed device, not a decision - our clone computes the same tables when it decides.

- **2026-11-12 (Claude, session 25), MEGAMEK BRIDGE B2 (THE JAVA SIDE) AND THE RUST HALF OF B3 (COMPACT UNIT STATE). No battle result changes. REVIEW PENDING (higher-level model).**
  Daniel: "Continue with the build at your discretion" (and: "a lot of this is needed for CombatLab"). NEW `megamek_bridge/` (Java, GPL v3, built
  against the unchanged MegaMek 0.51.01.7 release by `build.sh`): `HydraBridge extends Princess` (starts `btsim decide`, every decision a counted
  FALLBACK for now), `DecisionProcess`, `BridgeLauncher` (one game of an `.mms`, our bot on named players, every bot fighting to the end, one JSON
  record line). Three duels v CASPAR finished. Found: `startPrecognition()` must be called on a new Princess or it hangs. `btsim decide` answers
  `{"ping": true}`. COMPACT STATE (`bridge.rs` UNIT_FIELDS 78, ITEM_FIELDS 19, `compact_unit` / `apply_compact` / `rebuild_gaps`): a unit is its
  start record plus what a battle changes, measured over every reference battle; `--bridge-compact` sends only that and the check
  (`tests/check_bridge_parity.py`, now always compact) requires every unit rebuilt field for field and every answer the same. It found
  `home_edge` / `home_edge_row` and `stuck` missing from the measured list, and an endless loop when an equipment field holds other equipment
  (`partner`): fixed by walking inner objects first. Spec Section 3c.

- **2026-11-12 (Claude, session 25), MEGAMEK BRIDGE B1: OUR BOTS DECIDE FROM SNAPSHOTS (`btsim decide`), CHECKED AGAINST EVERY REFERENCE BATTLE. No battle result changes. REVIEW PENDING (higher-level model).**
  Daniel: "Go ahead and continue." NEW `engine/core/src/bridge.rs`: a decision process (`Session`) keeps its own battle for a whole game and is
  sent one JSON line per bot call the engine makes - the signals (phase start / end, a unit moved, end of turn, damage declared) and every
  decision (move order, movement, foe, target, firing order, weapon declaration, physical attack) - each with the battle's state (every unit's
  dump, turn, board changes, dice). So the bots' memories build up as in a battle and need no JSON of their own. `btsim decide` runs it on stdin /
  stdout. CHECK: `btsim SCENARIO --bridge-parity` plays a battle with a `Recorder` around its bots and a fresh session alongside, which must give
  every answer the same; `tests/check_bridge_parity.py` runs it on all 86 reference battles and pipes a recorded battle through a real `btsim
  decide` (`--quick`, in run_checks: no 8 v 8 / 12 v 12, turn 15, about 1 min). Result: every answer the same (12 v 12 with Hydra: ~24,000
  decisions in four battles). The first run found weapons named by their number in the unit's equipment list, which a rebuilt unit may renumber:
  weapons are now named by address ("RT#3", location and first slot), the form the Java side will use. NEW `Dice::save` / `PcgDice::restore`.
  Spec Section 3b: the wire as built, and B3 changed (the Java side sends a compact state; Rust rebuilds the full dump from the `.mtf`).
  Daniel's question (replay a Princess v Princess match on a matching seed): not possible whole-game (MegaMek's dice are unseeded and, even seeded,
  the two engines roll in different orders); decision-by-decision agreement through this process is the comparison that works (spec 3b).

- **2026-11-12 (Claude, session 25), SPEC: MEGAMEK BRIDGE (task T14, backlog E4). Documents only, no code. REVIEW PENDING (higher-level model).**
  Daniel: "Bridge that allows our bots to connect to a live Megamek game?" ... "Read the source and get a feel for the specs of what we need."
  Read MegaMek main at `c743b3f`: a bot is a client (`BotClient`); CASPAR is `Caspar extends Princess` with a few parts swapped, the pattern
  the bridge copies (`HydraBridge extends Princess`, Rust deciding through a `btsim decide` subprocess, Princess as the loud, counted fallback);
  MegaMek has its own headless bot-v-bot runner (`AIMatchRunner`, bots named by an `ai:` key); same `.mtf` / `.board` formats and facing
  numbers as ours; GPL v3. NEW `INTEGRATION__MEGAMEK_BRIDGE.md` (stages B0-B7, each with a script check; B1's is a parity check: a
  snapshot fed to `btsim decide` must give the choice the battle made). Building MegaMek here was refused by the session's safety
  check (downloaded build code): B0 needs Daniel's OK.
  B0 DONE the same day (Daniel: "Go ahead"): the 0.51.01.7 release (580 MB) runs here headless and holds CASPAR; 5 Hunchback duels,
  Princess v CASPAR: 2 played out, 2 stalled in round 0 (MegaMek errors), 1 misread after a unit fled. Bridge spec Section 1b: one game per
  process, retry a round-0 stall, check every result, MegaMek bots' flee behaviour off.
- **2026-11-12 (Claude, session 25), RULE FIX: A WALKING FALL IN A HEX HOLDING ANOTHER 'MECH SETS OFF A DOMINO EFFECT, BOTH ENGINES; TRIALS RECORD EACH BATTLE AS IT ENDS AND SURVIVE CRASHES; 400-BATTLE CHECKS. REVIEW PENDING (higher-level model).**
  Daniel: "Cast a wider net for both the hunchback and the heavies. Maybe 400 games each." Both were flukes: Hunchback duel v Gladiator 190 - 187
  (first version 182 - 195), heavies v Princess 282 - 116 (279 - 118). The first-version Hunchback run CRASHED (battle 8, seed 101): a Hunchback
  walked backward through the hex of an immobile enemy (legal, Core p.48), failed the backward level change PSR and fell in the hex it was leaving
  (p.115), on top of the enemy; next turn's movement table could not start from a blocked hex. The book does not cover a fall in an occupied hex
  one passes through; MegaMek (TWGameManager.doEntityFallsInto) resolves the faller's fall, then a domino effect on the 'Mech already there,
  heading the faller's way, or 1D6 when the fall is in the hex it was in. NEW `domino.fell_into_occupied` (INTEGRATION__domino.py,
  engine/core/src/domino.rs), called from the walk (`walk_path`) after a fall. No reference log changed (Python 57 of 57, Rust 86 of 86).
  RECORDING AS IT GOES (Daniel: "the results of each run is recorded when its done. This lets you quickly find crashes, and easilly restart a
  set"): `btsim --stream FILE` appends each battle the moment it ends, a panic is caught and recorded as {"sim", "seed", "crashed"} and the set
  goes on, and the same command again plays only the missing battles; `hydra_trial.py` / `round_robin.py` stream every batch to
  `trial_records/progress/` (git-ignored), print crashes, keep them in the records line, and never write a batch twice.
- **2026-11-12 (Claude, session 25), HYDRA: ALL FIVE SWITCHES ON BY DEFAULT; RUST TURN CAP 100; PER-BATTLE TRIAL RECORDS. Hydra's and capped battles' results change (meant to). REVIEW PENDING (higher-level model).**
  Daniel: "Leave them all on. Set the standard game cap to 100 rounds." All five on (S5a play-out, S4 charges / DFA, S3 move order, Waiting,
  Oracle attention; each turned off with its OFF value, listed at the top of `hydra.rs`). Measured with the cap at 150, same seeds: v Gladiator 397 -
  219 - 8 (first version 369 - 243 - 12), v Princess 447 - 161 - 16 (438 - 176 - 10); big battles 86 - 30 v 75 - 47; 4 v 4 heavies v Princess worse.
  NEW `scenario::STANDARD_MAX_TURNS` = 100 for every Rust scenario (a meta.json's 50 is no longer read; the Python answer key and its fixtures keep
  50). `btsim --max-turns N`, `--sims I,J` and a `max_turns` field in its output. Trial records (Daniel: "we need to keep records of results per
  individual game seed"): `tools/trial_records.py`, always on in `hydra_trial.py` / `round_robin.py`, files in `trial_records/`;
  `tools/replay_undecided.py` replays only the capped battles. Reference battles: the old switch variants became "one switch off" variants plus
  two "first version" battles (86 in all). Before re-saving, the only non-Hydra battles that differed were the six that had hit the 50-turn cap
  (Daniel: "you only need to run the stalled out games"); now 2 of 86 reach the cap (the Asymptote mirror, and the first-version Hydra in the
  lance woods). Python 57 of 57.
- **2026-11-12 (Claude, session 25), HYDRA WAITING AND ATTENTION SHARE, BUILT AS SWITCHES, MEASURED, BOTH OFF BY DEFAULT. REVIEW PENDING (higher-level model).**
  Daniel: "Go ahead and process the last 2 items on the list." WAITING (`HYDRA_WAITING`; `coming_friends`, `MAX_WAITS` 2, `BEHIND` 3,
  `HydraState::waited`): a unit out ahead of its line may take a spot that deals nothing when the best trade is worse than the team's typical turn,
  at most two turns in a row. ATTENTION (`HYDRA_ATTENTION = "oracle"`; `elsewhere_of`, `attention_damage`): the Oracle's expected damage replaces
  guns x `range_factor` in "what else could this enemy shoot at", in the Mover and the S5a judge. Same seeds: Waiting v Gladiator 335 - 195, v
  Princess 426 - 179 (first version 333 - 203, 434 - 174); Attention 329 - 213 and 441 - 165 - level, but the 8 v 8 + 12 v 12 went 71 - 41 -> 80 -
  31 and the 4 v 4s v Gladiator got worse. Both off; a confirming big-battle run is the next step for Attention. Four reference battles added (90).
- **2026-11-12 (Claude, session 25), HYDRA S3: MOVE ORDER, BUILT AS A SWITCH, MEASURED, OFF BY DEFAULT. REVIEW PENDING (higher-level model).**
  Daniel: "Lets move onto move order then. We'll just keep moving down Fable's wish list until done." NEW socket question `BotSet::move_pick`
  (default None = the engine's move index; `orchestrator` asks it inside the Movement Phase pick, so the S5a move queue uses it too) and
  `hydra::move_pick`: least to lose first, deciders last - each unit's STAKE is the priced damage that can flow through it this turn (enemy guns x my
  price + my guns x enemy price, by `range_factor` of the distance left after its best move); smallest first. Prices once per team per Movement Phase
  (`HydraState::order`, cleared in `start_movement`), from `ledger_as` (read-only). Switch `HYDRA_MOVE_ORDER = "stake"` (default unset). Same seeds:
  v Gladiator 331 - 204 (without 333 - 203), v Princess 410 - 195 (without 434 - 174; worse in the 4 v 4 woods / heavies); duels identical. So off.
  Two reference battles added (86); no other log changed. Python 57 of 57.
- **2026-11-12 (Claude, session 25), HYDRA S6 SECOND PASS: SPREAD FIRE CONFIRMED; STRUCTURE WEIGHT TESTED, KEPT; NO DEFAULT CHANGED. REVIEW PENDING (higher-level model).**
  Daniel: "Go for second calibration pass." The ledger snapshot now also records raw armor and structure (`scenario::snapshot`); `tools/hydra_calibrate.py
  fit2` (structure weight x fire spread for small / big battles, scored by log-loss on the winner); NEW Hydra-only setting `HYDRA_LIFE_STRUCTURE_WEIGHT`
  (`hydra::life_of`; without it the first version's life, `effective_hp` with Gladiator's MOVEMENT_STRUCTURE_WEIGHT - set to 2 it is identical). 1,092
  fresh battles with the calibrated Hydra (seed 12): spread fire confirmed; a size-dependent spread adds nothing; weight 1 predicts slightly better but
  plays level (v Gladiator 333 - 203 at 2 v 330 - 216 at 1; v Princess 434 - 174 v 442 - 165), so 2 stays. The duel's under-prediction cannot change a
  choice (two prices scaled to a mean of 1). Daniel asked whether Hydra copied his homework: its life is his structure-weight rule and its guns and
  Oracle are Gladiator's (`future_damage`, `MoveEvaluator`) - written down in `INTEGRATION__HYDRA.md`. No reference log changed.
- **2026-11-12 (Claude, session 25), HYDRA S6: THE FORECAST CALIBRATED ON 1,092 BATTLES; SPREAD FIRE (FOCUS 0) IS THE DEFAULT. Hydra's results change (meant to). REVIEW PENDING (higher-level model).**
  Daniel: "go for the calibration run". NEW `scenario::run_recorded` + `btsim --ledger FILE` (life and guns of every unit at each turn's end; reads
  only: five batches identical with and without it) and `tools/hydra_calibrate.py` (collect / fit). The Forecast got three settings, `hydra::Shape`
  (`HYDRA_FORECAST_FOCUS` / `_FADE` / `_STEP`; `forecast` / `prices` keep the first version's shape, `Shape::FIRST`, for tests). Fit: the first version
  is sound (correlation 0.81, scale 0.98, leader wins 93% above a 0.35 margin); overall the shape hardly matters, FADE hurts; with 9+ units alive spread
  fire fits 20% better. In battle on the earlier tables' seeds, FOCUS 0: v Gladiator 176 - 145 -> 224 - 103 over the six team match-ups (heavies 42 - 25
  -> 69 - 7), v Princess 248 - 130 -> 266 - 110; duels identical. DEFAULT now FOCUS 0 (`Shape::CALIBRATED`). The 9 Hydra team reference battles
  re-saved (meant to change); everything else matches. Python 57 of 57. Plan Section 7 has the table and what is left.
- **2026-11-12 (Claude, session 25), RULE FIX: A CHARGE OR DFA MAY NOT STOP ON ANOTHER UNIT'S HEX (Core p.49), BOTH ENGINES. REVIEW PENDING (higher-level model).**
  Found by Hydra's S4 trial (a crash) and confirmed for Gladiator at Daniel's request ("check if gladiator has the same bug"; "just say 'No, that's not a
  legal move'"). The stop lists for charges (`MoverIndex.charge_states`) and death from above (`dfa_states`) did not look at other units, so a charge
  could end next to its target on a FRIEND's hex - against "no 'Mech can deliberately violate" the stacking limit (p.49). Gladiator listed such a stop
  52 times in 200 team battles (37 times as its best charge) and took one in 3 of them (`hy_4v4_lance_grass` 2, `hy_8v8_valley` 1, seed 7); Hydra's
  next unit then crashed planning from the shared hex. FIX in `INTEGRATION__movement_attacks.py` (`_held_hexes`) and `engine/core/src/move_attacks.rs`
  (`held_hexes`), from the unit's `other_unit_hexes`: those stops are not offered. Hydra's own guard removed (the list now refuses them). Checks: Python
  57 of 57, no reference log changed; the 63 fixtures re-recorded from the fixed Python and the Rust matches all (`BOTS=rust`); Rust reference 84 of 84.
- **2026-11-12 (Claude, session 25), HYDRA S4: CHARGES AND DEATH FROM ABOVE, BUILT AS A SWITCH, MEASURED LEVEL, OFF BY DEFAULT. REVIEW PENDING (higher-level model).**
  Daniel: "keep working on its list of improvements. Stop after each feature is added in." `hydra::movement_attack`: every charge / DFA stop on a
  weighed enemy that has moved or cannot (Core pp.78-79) priced in Hydra's currency (the attack's expected damage both ways from `move_attacks::values`
  plus the ranged exchange from the attack hex; the other enemies' lines from the Oracle there; PSR risk), taken when it beats the best ordinary spot.
  Switch `HYDRA_MOVEMENT_ATTACKS` (default false). Stops on an occupied hex are skipped (the first trial crashed on one). v Gladiator 291 - 244 (without
  285 - 245); v Princess 407 - 202 (without 416 - 194; worse at 8 v 8 / 12 v 12); the duels unchanged (no attack chosen). Two reference battles added
  (84). Likely flaw, written in `INTEGRATION__HYDRA.md` Section 7: the attack is scored against the enemies as they stand, not through the reply.
- **2026-11-12 (Claude, session 25), ROUND ROBIN OF THE THREE BOTS; S5a PLAY-OUT BUILT AS A SWITCH (MEASURED LEVEL, DEFAULT UNCHANGED); BOT TIMINGS. REVIEW PENDING (higher-level model).**
  Daniel: "First Lets get round robin stats for that set of matchups ... bot vs it self is also a category", "Then build S5a and run it against each
  opponent", "what the time spent per bot per game is". (1) NEW `tools/round_robin.py` (every bot v every bot and itself, units' bots rewritten in a copy
  of the scenario; same dice per seating; reproduces `hydra_trial.py` exactly). Nine mirror match-ups: Hydra v Princess 416 - 194, Hydra v Gladiator
  285 - 245, Gladiator v Princess 331 - 240; self-play Gladiator 118 - 126 - 68 (most draws: backlog A1), Hydra 145 - 148, Princess 168 - 125 (Red edge).
  (2) S5a, `hydra::playout` + `weigh_lines`, switch `HYDRA_PLAYOUT` ("reply" default / "s5a"); `btsim --set KEY=VALUE`; `--set` passed by `hydra_trial.py`
  and `round_robin.py`. v Gladiator 309 - 218 (reply 285 - 245), v Princess 398 - 203 (reply 416 - 194): level overall, so the default stays "reply". A first
  cut with 8 spots flat lost the Griffin duel (28 - 33); the spots now share a budget of 64. (3) Timings, one core, self-play: ms a turn - duel G 25 / P 7 /
  H 38 / H+S5a 39; 4 v 4 G 164 / P 49 / H 79 / H+S5a 182; 12 v 12 G 335 / P 237 / H 231 / H+S5a 472. Tables: `INTEGRATION__HYDRA.md` Sections 5-6.
  Checks: Rust reference 82 (3 new S5a battles; witness on); default path unchanged (the 79 earlier logs match).
- **2026-11-12 (Claude, session 25), HYDRA v PRINCESS MEASURED; S5a GROUNDWORK BUILT (MOVE QUEUE, POSE, WITNESS). REVIEW PENDING (higher-level model).**
  Daniel: "Lets set up the Hydra Vs Princess runs. And set up the ground work for S5a". (1) Hydra v Princess on the mirror set, 40 battles a seating
  (16 for 8 v 8 / 12 v 12): 416 - 194 over nine, ahead in every match-up (table in `INTEGRATION__HYDRA.md` Section 5); `tools/hydra_trial.py --btsim
  PATH` added so a long trial can use a copy of the program while the engine is rebuilt. (2) NEW `engine/core/src/playout.rs`: the move queue
  (`Battle::move_queue`, set by the movement loop in `orchestrator.rs` from a copy of the activation state; `forces::Activation` is now Clone), the
  pose stack (`Pose`, `Poses`), and the witness (`Witness`, on with HYDRA_CHECK; always on in `tests/check_rust_reference.py`), wrapped around
  `hydra::choose_movement`. No result changes: Rust reference 79 of 79, `BOTS=rust` stage 6 63 of 63; new tests `engine/core/tests/playout.rs`
  (3). The witness's first run found one die drawn inside a Hydra move: Gladiator's march, which Hydra hands the move to before any enemy is on
  the board, breaks exact ties with a seeded random pick (the battle's own dice, so the seed covers it - not a loose die); the witness now skips
  that hand-off. The S5a responder and judge are not built (plan Section 6).
- **2026-11-11 (Claude, session 25), RUST REFERENCE BATTLES: THE RUST CHECKS ITSELF. New test tool and data; no engine change. REVIEW PENDING (higher-level model).**
  Daniel: "Go ahead and start the battery of Rust reference battles" (after: the Python is "effectively dead code now"). NEW
  `tests/check_rust_reference.py`: 79 battles played by `btsim` on its own dice (seed 1), each compared byte for byte with its saved log in
  `engine/reference/logs/` (a result block - winner, turns, each team's armor + structure left, hits, damage - then the battle log). Inputs: the
  72 port scenarios (15 reference, 6 team, 42 coverage, 9 Hydra mirrors) frozen into `engine/reference/scenarios.zip` (1.2 MB) so the Python is
  no longer needed to make them; plus 7 plays with Hydra on one or both sides (Hydra had no answer key at all). `run_checks.py` runs it as one
  line when cargo is installed (57 checks). Two runs agree (79 of 79). 8 reach the 50-turn cap: the Asymptote mirror (as in the Python),
  `cov_magma_board`, `cov_melee_mace_sword`, three Hydra mirror scenarios with Gladiator on both sides (4 v 4 woods, 8 v 8, 12 v 12) and two with Hydra
  on Red (4 v 4 woods, 12 v 12). Two runs take about 40 s on 4 cores.
- **2026-11-11 (Claude, session 25), SESSION 25 TIDY-UP: THE LOOKAHEAD NO LONGER ROLLS BATTLE DICE; SIX CREW HITS BY THE BOOK; HYDRA TABLE RE-RUN; WARNINGS; SECTION 0. REVIEW PENDING (higher-level model).**
  Daniel: "lets see what you can tidy up on its todo list" and "there was a free floating dice outside of the seed". (1) LOOKAHEAD DICE, both
  engines (`INTEGRATION__structure_weight.hit_spread`, `engine/core/src/structure_weight.rs`): a bot estimating hits on a torso-cockpit 'Mech
  whose head is gone used to re-roll head results with the battle's dice and print the re-rolls (Core p.203); it now takes that re-roll's exact
  average - Head rows dropped, the rest scaled by 1 / (1 - P(head)) - no dice, no log lines. `hit_location::resolve_hit_location_shared` and
  `Battle::lookahead_log` removed. Python 56 of 56 (no reference log changed); Rust 63 of 63 fixtures with Rust bots; the two random battles that
  used to differ (`port_fuzz exact 240`, `7054 --tag c`) now match, and 17 new ones (`exact 9100 20 --tag s`; 3 drew bridge maps, which neither engine plays). (2) SIX CREW HITS (`piloting_rolls.rs`):
  the `crew_six_hits` stub replaced by the book - six hits is "Dead" on the Consciousness table (p.117), so no roll; the console's secondary
  warrior takes over (p.203). (3) HYDRA's whole mirror table re-run (Fable's second pass left five rows stale): 285 - 245 over nine match-ups,
  `INTEGRATION__HYDRA.md` Section 5. (4) Ten Rust compiler warnings fixed (unused imports, needless `mut`; no behaviour change). (5) PROJECT_MAP
  Section 0: date, Rust engine and Hydra rows, D1 rewritten (the port is done), review-queue letters made unique (the session 22-24 items are now
  (s), (t), (u); older Change Record text calling the Rust review "queue item (p)" means (t)).
- **2026-11-11 (Claude, session 24), HYDRA SECOND PASS: where damage lands, a lone unit may hide, reply budget 64. REVIEW PENDING (higher-level model).**
  Daniel: "Improve Hydra." `engine/core/src/hydra.rs` only (Hydra units only; no other bot or rule touched). (1) exchange figures are multiplied
  by the engine's exposure factor of the side the damage arrives on (`Side::exposure`); (2) when moving first with no friend in any weighed
  enemy's reach, the reply also looks at spots that deal nothing; (3) REPLY_BUDGET / REPLY_MAX 32 -> 64. Mirror trials, Hydra - Gladiator - none,
  before -> after: Griffin duel 33-34-13 -> 38-26-16; Hunchback woods duel 23-47-10 -> 29-38-13; 2 v 2 32-45-3 -> 34-34-12; 4 v 4 woods
  41-28-11 -> 35-30-15. The rest of the table and the speed were NOT re-run (time ran out). Four ideas tried and dropped, and the finding that the
  gap is in moving first, are in `INTEGRATION__HYDRA.md` Section 5 "Second pass". Checks: engine tests as before (73 reference battles exact, the same 2 known lookahead-dice cases differ); Hydra unit tests pass.
- **2026-11-11 (Claude, session 24), COMBAT LAB ART: ADVICE ON INTERCHANGEABLE ARMS AND TORSOS (sheet A9). Document only.**
  Daniel: "advice you could give future you on how to create arms and torsos that are interchangeable, and contain a known variety of weapon and
  equipment slots?" `INTEGRATION__COMBAT_LAB_ART_SPECS.md` A9: design the joins and the bays first and the shape last - a socket standard with size
  classes, one owner per joint cover, a bay table per block as data (the "known variety", published as a catalogue), worst-case loads as a test,
  bays that grow with the shell laid after, a few named layouts, rear mounts, right-hand parts mirrored, and an every-pair test.
- **2026-11-11 (Claude, session 24), COMBAT LAB ART: A DIAGNOSIS AND SPEC SHEETS A1-A8. Documents only; nothing built, no code changed.**
  Daniel: "they're still just shaped blocks stacked on each other ... Do what you can to help there." `INTEGRATION__COMBAT_LAB_ART_SPECS.md`: six
  reasons the models read as blocks (all bulging lumps with no hollows; parts touch and do not interlock; one size of detail; variants that do not
  change the outline; no taper or shared angles; one material in flat light), from one lineup picture of an Atlas, and eight jobs in order: A1
  materials and light, A2 dark under-body with armor plates and gaps, A3 silhouette check and proportion table, A4 taper and shared angles, A5
  interlock at joints, A6 small-detail kit, A7 weapons, A8 paint. Each ends with pages published for Daniel's eye. Linked from PROJECT_MAP E3a.
- **2026-11-11 (Claude, session 24), COMBAT LAB SPEC SHEETS. Documents only; nothing built, no code changed.**
  Daniel: "write spec sheets for future you to follow to improve that side of the project." `INTEGRATION__COMBAT_LAB_SPECS.md`: Part B of
  `INTEGRATION__COMBAT_LAB.md` turned into nine jobs on the Rust engine (CL1 a battle set up from files in Rust, CL2 the battle history, CL3 the
  Lab server, CL4 setup and results pages, CL5 replay page, CL6 a battle restarted from a saved state - shared with Hydra's dice play-out, CL7
  analysis overlays, CL8 branching, CL9 art pointer), each with what exists, what to build, how to know it is done, and the traps. Items the
  writer did not verify are marked CHECK FIRST. Linked from PROJECT_MAP E2 and TASK_SPECS T12 / T13.
- **2026-11-11 (Claude, session 24), HYDRA: A THIRD BOT, DESIGNED FROM FIRST PRINCIPLES, FIRST VERSION BUILT; THE PLAY-OUT STAGE PLANNED. Rust only (Daniel: "Rust only. Python will be effectively retired from here on out"). REVIEW PENDING (higher-level model).**
  Daniel: "start from first principles on your own bot - entirely envisioned and designed by you ... effective from 1 on 1 to large force engagements
  12 on 12 or possibly higher", and "the plan of what its supposed to do may be more important then the details". THE PLAN is `INTEGRATION__HYDRA.md`
  (blocks and how they connect; read it before the code). THE IDEA: one planner per team; every point of damage is priced by how far it moves a small
  forecast of how the battle ends (Ledger -> Forecast -> Prices); the Mover and the team Fire Plan ask the engine what damage flows and multiply by
  prices. BUILT: `engine/core/src/hydra.rs` (all blocks, first version), routed by the unit's bot name "hydra" in `gladiator_bots.rs`, memory in
  `Battle::hydra`; `btsim --hydra TEAM`; `tools/hydra_scenarios.py` (mirror match-ups, same 'Mechs both sides) and `tools/hydra_trial.py` (three
  batches a scenario, head-to-head line). RESULTS v Gladiator on the mirror set (Hydra - Gladiator - no winner; plan Section 5): duels 33-34-13 /
  23-47-10 / 47-33-0, 2 v 2 32-45-3, 4 v 4 41-29-10 / 41-28-11 / 51-24-5, 8 v 8 15-7-10, 12 v 12 14-15-3. So: ahead at 4 v 4 and 8 v 8, level at 12 v 12,
  behind in a short-range duel and the 2 v 2; about twice as fast as Gladiator from 4 v 4 up. Not tried v Princess. Three scoring rules were measured;
  the plan records the two dropped. PLANNED, NOT BUILT: the play-out stage (plan Section 6): S5a plays out the rest of the Movement Phase with no dice
  and no copy of the battle, S5b is the dice version. ENGINE FIX on the way: a unit with several crew could reach 6 crew hits while still standing and
  the consciousness check then crashed (the Python raised there too): now that crew member is out, no roll, with a loud stub `crew_six_hits`
  (PROJECT_MAP Section 4: Daniel to rule). `scenario.rs`: meta.json optional. `bv_check` test skips folders without a recording. TESTS: with no Hydra
  unit every fixture matches as before (73 ok; the 2 that differ are the known lookahead-dice cases); Python 56 of 56.
- **2026-11-11 (Claude, session 24, the higher-level review of queue item (p)), RUST ENGINE REVIEWED: 3 TO 5 TIMES FASTER, TWO ENGINE BUGS FIXED, A RANDOM-BATTLE CHECK ADDED. Rust and tools only; the Python is unchanged (56 of 56 checks).**
  Daniel: "check over the work, bug hunt, and optimize the code." SPEED (one core, results IDENTICAL to before on the same seeds, all 63 fixtures still
  equal with the Rust bots alone): 40 Atlas v Archer duels 21.6 s -> 4.3 s; two 4 v 4 Princess v Gladiator battles 17.9 s -> 4.7 s; two 12 v 12 (10 turns)
  67 s -> 21 s. The same 40 duels take the Python 45 s. Found with callgrind, one change at a time: hexes looked up by a (column, row) grid instead of a
  formatted label and a string hash (`Board::info_xy`, `hex_label` without the formatter); FxHash for every map and set (`fasthash.rs`; SipHash was a
  sixth of the time); mimalloc in `btsim`; equipment.json parsed once a process (`EquipmentDb::shared`); name-only weapon facts kept on the item
  (`Equipment::memo`: special, has_profile, TN modifier, AMS, TC-eligible) and the canonical name shared (`Arc<str>`); AES / shield scans without building
  strings (`norm_ascii`); lines of sight remembered until the board changes (`Battle::los_memo`, the Python's `los_cache`); finished movement tables and
  the board-wide terrain scans likewise (`Battle::movement_table`, `Board::psr_terrain`; `Battle::board_changed` empties them on smoke and a broken
  crust); the cluster table read once; the reply model lends its tables instead of copying them per spot; terrain features found by a short scan.
  BUG HUNT: NEW `tools/port_fuzz.py` - `exact`: a random match-up (any units of meks.zip, any 16x17 map, either bot) is recorded by the Python and replayed
  by the Rust with its own bots, state / dice / log equal; `crash`: `btsim` batches of random match-ups, twice, for panics and repeatability. Run so far:
  about 775 duels and 2 v 2s and 55 3 v 3 / 4 v 4s match exactly; 524 match-ups x 6 battles x 2 without a repeatability failure. FIXED IN THE RUST:
  (1) an active Void Signature System's +1 on its own ranged attacks was missing from the declared attack and the TAG attack (`attack_resolution`
  called the Taser / TSEMP / IMP-only modifier, not `equipment_systems.own_attack_modifier`); (2) a panic when a unit enters the board while an enemy
  stands on one of its entry-edge hexes (`ranged_combat::path_to_cached`); (3) the state dump left out the command console's second warrior
  (`secondary_hits`, `console_lost`, `primary_dead`), `imp_mp` and an ammo bin's None attributes, so those were never compared; (4) Python's `sum()` of
  floats is compensated summation since 3.12 - the Rust added plainly, the source of the "last digit" differences (`pyfmt::py_sum` / `py_sum_num`
  at every float `sum()`; Daniel, same day: past the 12th decimal is noise - kept because it was done and makes those lines equal); (5) the function-tap
  tests no longer compiled (dice behind a RefCell); (6) debugging leftovers in the bots' hot loops (`std::env::var("BT_...")` with hard-coded unit
  names) removed. FOUND IN THE PYTHON, NOT CHANGED (it is frozen; Daniel's call - PROJECT_MAP Section 4, RUST_PORT "Found on the way" 7-11): a bot's
  lookahead rolls real dice and prints log lines for a unit with a destroyed head and a torso cockpit (the two engines then draw different counts: the
  only exact-check failures left, 2 of about 830); two crashes on particular units (a profile weapon with no heat value in the min-heat padding; a PPC
  capacitor on a PPC with no damage value); the same entry-edge crash as (2); the LOS cache for prone heights is not emptied when smoke changes.
  All Rust tests pass (stage 1-3, taps, attach, BV, stage 6 with recorded and with Rust bots). STILL OPEN: the untranslated switches (unchanged list);
  `config.ENGINE` switch; retiring `fastcore/`; further speed leads in `engine/REVIEW_BRIEF.md` (team battles: the fire scoring per (unit, foe)).

- **2026-11-11 (Claude, session 23), RUST PORT STAGES 1-9 FIRST CUT: THE WHOLE ENGINE AND ALL DEFAULT BOTS IN RUST; BATCH RUNNER; STATISTICS CHECK UNDER WAY. New Rust crates and tools; the Python is unchanged. REVIEW PENDING (higher-level model).**
  Daniel: "Continue until done" and, on the extras, "We'll convert that list of extras later if they come up." `engine/core` (`btsim_core`, ~30,000 lines)
  now holds the rules engine (stages 1-6) and the bots with their default settings: Gladiator movement (`move_options` / `move_eval` / `move_select` /
  `move_attacks`), Legate with triage tiers and the peril peak (`legate`), Gladiator's firing order and several-enemy targeting (`bot_targets`), the modern
  Princess (`princess_modern` ranker + group, `princess_fire` fire control and physical choice, `princess_memory`, `princess`, `princess_geometry`) and Battle
  Value (`battle_value`). EVIDENCE: (1) every recorded bot decision of all 63 fixtures is reproduced (`CHECK=legate,move,declaration,physical,princess cargo
  test --release --test stage6_battles`); (2) `BOTS=rust cargo test --release --test stage6_battles` plays all 63 fixture battles with NO recorded decisions -
  state after every phase, dice used, log and stub warnings equal the Python's (about 215 s); (3) `tests/bv_check.rs`: BV equals the Python's on 45 units. Floats
  are compared to 1e-12 relative and movement-note numbers to their printed precision (Daniel: 20th-decimal differences are float error); `pyfmt::Fx` prints
  Python's `{x:.nf}` (Rust rounds exact ties the other way). STAGE 9: `PcgDice` (PCG64, own stream: the engines are compared on statistics, not seeds),
  `btsim` (`engine/btsim`, rayon, one battle a thread), `tools/port_scenario.py` (writes a scenario from config overrides), `tools/port_stat_check.py` (N battles on
  each engine, z-tests on wins, turns, damage, HP). A 60-battle duel check: same game (all |z| < 1.5). BUGS FOUND BY BATCHES: a unit whose last enemy fell
  mid-phase panicked (now `any_enemy`); a destroyed torso-cockpit head in a bot's lookahead draws dice in the Python (translated, dice behind a RefCell);
  Princess re-searched every path for every spot (12 v 12 never finished; path tables now cached per ranking). NOT TRANSLATED (loud panic if asked; none is
  in the fixtures): PRINCESS_VERSION "0.50.07", MOVE_ORDER "tiered", LEGATE_HERDING / COHESION / TEAM_VALUE, STACK, PERIL other than off, STUB_GLADIATOR_TARGET
  "kill_curve", MOVEMENT_SEARCH "if_then". OPEN: the larger statistics runs (200 + 200 + 12 v 12); SPEED (Rust is only ~2x the Python+fastcore so far:
  per-battle equipment-database load, cloning in the scoring loops); `config.ENGINE` switch in `INTEGRATION__main.py`; retiring `fastcore/`. Review brief: `engine/REVIEW_BRIEF.md`.

- **2026-11-10 (Claude, session 22), RUST PORT STAGE 0 DONE: THE COMPARISON TOOLS. New tools and tests; a pass-through seam in two engine files; no behaviour change. REVIEW PENDING (higher-level model).**
  Daniel: "Its time to convert the monte carlo into rust" and "Go ahead. This is a work until its done project." Built, per `INTEGRATION__RUST_PORT.md` stage 0:
  NEW `tools/port_record.py` (plays battle 1 under a scenario with read-only hooks; writes config / units / board / dice tape / decisions / per-phase state
  trace / log; `--replay` plays it back from dice + decisions with every bot switched off), `tools/port_diff.py` (first differing line, unit and field, with the
  dice drawn; `normalize_log`), `tools/port_scenarios.py` (63 fixture battles: the 15 reference, 6 team - 4 v 4 and 12 v 12, Princess / Gladiator mixes, a 3-way -
  and 42 coverage battles of units unpacked from data/meks.zip), `tools/port_fixtures.py` (records every scenario and replays it in Python: trace, dice position,
  stdout and stub warnings must be identical), `tools/port_coverage.py` (coverage.py over the fixtures; per-scenario data kept, so a new scenario costs one run),
  `tests/test_port_record.py` (14 checks; the self-replay of four fixtures). NEW `INTEGRATION__decisions.py`: the decision seam - `decide(kind, ctx, compute)` is a
  plain call of `compute()` in normal play. ENGINE EDITS (behaviour-neutral, all 56 checks and the benchmark 501 / 495 identical): `INTEGRATION__bots.py` routes
  `choose_movement`, `choose_foe`, `choose_target`, the firing-order pick and `choose_physical` through it; `INTEGRATION__attack_resolution._declare` wraps the
  weapon / twist choice (`choose_declaration`, same code moved into a local function). RESULT: all 63 fixtures replay exactly. Coverage: 182 of 1,327 engine
  functions are not reached; `engine/COVERAGE_GAPS.md` sorts them (experiments T8 would archive 50; entry points, dead code and glue 47; rules the bots rarely
  trigger - DFA, domino, bogging, harjel and similar - 71, to be covered by scripted function-level fixtures in stages 4-5; Princess branches 14). FOUND ON THE WAY
  (RUST_PORT "Found on the way"): smoke-clear lines print in set order; Gladiator's bot draws dice; the engine reads the move search's PSR table; dead code in
  `pathfinder/combat.py`. The fixture format is written up in RUST_PORT "The fixture format". Open for Daniel before stage 1: T8 (archive the experiments).

- **2026-11-10 (Claude, session 21), PLANS SAVED FOR LOWER MODELS: THE RUST TRANSLATION, THE BATTLE STATE, THE MOVE SCORE. Documents only. REVIEW PENDING (higher-level model).**
  Daniel: "Go ahead and save your recommendations ... your Fable form is only temporary, So I'll probably be making do with lower models. For my next trick. Going
  to have Sonnet translate the monte carlo into rust. Just bite the bullet and remove translation as a source of slowdown." NEW `INTEGRATION__RUST_PORT.md`: the
  Python stays untouched as the answer key; stage 0 builds the comparison tools first (a dice tape instead of re-creating NumPy's generator, a list of every bot
  and stub decision, a state dump after every phase, a first-difference finder, a Python self-replay test that proves the decision list complete); stages 1-6 the
  engine, proven by replaying recorded decisions byte for byte with the bots off; 7 Princess, 8 Gladiator (same decisions as the Python); 9 cut over and speed.
  Ten traps (dice, dict order, ties, floats, printing, globals, dynamic attributes, settings, caches, stubs). Output pages and art stay Python. NEW
  `INTEGRATION__STATE.md` (task T5 done): true state v phase scratch v pure caches for every module-level table, names instead of `id()`, the Battle shape, the
  engine boundary. `INTEGRATION__TASK_SPECS.md`: models re-assigned for work without the top model; T1 written out in full - the "race" score = lifetime with a
  per-turn discount (the clock), a cap at the enemy's remaining HP with left-over life at a reduced weight, and a delay for spots out of range; with neutral
  settings it must reproduce the reference logs byte for byte (the wiring test). T6 only if the port is dropped; T11 = the port. Advice recorded: decide T8 and
  build or park T1 before the port freezes the Python.

- **2026-11-10 (Claude, session 21), TOP-LEVEL REVIEW; THE PROJECT MAP CLEANED UP; TASK SPECS. Documents only, no code. REVIEW PENDING (higher-level model).**
  Daniel: "Please review the monte carlo project ... what could be improved about it, and if you have any ideas for problems currently in the basket", then
  "Please clean up the project map" and "write up the spec sheet". REVIEW (run_checks: 55 of 55 before any change): the end-game stand-off, the mirror stall and
  the cap draws look like ONE flaw in the move score (`movement_selection._Lifetime`, `legate.MultiLifetime`): no enemy HP in it (a kill earns only its damage
  points), no clock (a spot that deals nothing keeps the whole future term), no cost for being out of range - so a unit engages only when this turn's trade beats
  its average future trade, and two Gladiators never both want to. Not built; spec T1. Also noted: 20-battle win counts are inside the noise (judge by a
  per-battle margin, T2); one roster / field / opponent (T3); the physical-value gap may be the knife-edge of range 1 against a 2.7-hex estimate error
  (hypothesis, T4); about 300 `id()` keys (T5 / T6); 148 settings with lost experiments still in `legate.Extras.adjust` (T8); no automatic checks (T10).
  MAP: `INTEGRATION__PROJECT_MAP.md` 4,837 -> about 1,160 lines. Section 0 rewritten as state + backlog (A-E, each with its old "Pick up here" label) + REVIEW
  QUEUE; the old Section 0 moved WORD FOR WORD to `INTEGRATION__HISTORY.md`; Section 8 moved word for word to this file. Sections 1-7 untouched except four
  cross-references. Stale lines dropped from the new Section 0 (Legate "off by default", "23 test files"). The Peril line had no REVIEW QUEUE entry: added as (p).
  NEW: `INTEGRATION__TASK_SPECS.md` - which model suits what, and ten task write-ups. CLAUDE.md, BOTS.md, RULES_REVIEW.md, README: pointers updated.

- **2026-11-08 (Claude), TRIAGE IS NOW THE DEFAULT (`config.TRIAGE = True`; Daniel: "Turn them on"). REVIEW PENDING (higher-level model).**
  Basis: the 100-battle comparison at a 100-turn cap (51 v 42 wins, 'Mechs left 2.32 v 1.62; entry above). Only acts for Gladiator + Legate in team battles of 3+ units; 55 / 55 checks pass, reference logs unchanged.
  `tests/baseline_battery.py`: `--no-triage` runs the old baseline (key without the `_triage-` tag); a default run now carries the triage tag. The NEW DEFAULT BASELINE is the five triage sets in run_stats/baseline/saved (seeds 12345,
  2468, 1357, 8642, 9753; 100-turn cap). Use `--turns 100` from now on (Daniel). Pick up here 000000 lists what is left of the Peril line.

- **2026-11-08 (Claude), TRIAGE: THE 100-BATTLE COMPARISON AT A 100-TURN CAP (five seed sets of 20). REVIEW PENDING (higher-level model).**
  Princess (Red) v Gladiator + Legate (Blue); battles that ended inside 50 turns are identical at either cap, so only the baseline's / triage's cap-draws were re-played at 100.
  Seed sets (Blue wins / Red / draws, 'Mechs left Blue / Red), baseline then tiers: 12345: 8 / 11 / 1, 1.90 / 2.50 then 9 / 10 / 1, 2.30 / 2.05; 2468: 8 / 12 / 0, 1.05 / 2.65 then 11 / 9 / 0, 2.60 / 2.25;
  1357: 9 / 10 / 1, 1.85 / 1.95 then 11 / 9 / 0, 2.45 / 2.20; 8642: 10 / 10 / 0, 2.30 / 2.35 then 10 / 9 / 1, 2.30 / 2.60; 9753: 7 / 13 / 0, 1.00 / 3.45 then 10 / 10 / 0, 1.95 / 2.85.
  ALL 100: BASELINE 42 / 56 / 2, left 1.62 / 2.58, dealt 1338 / 1546, 42.3 turns; TIERS (25%, hot x2, cool x1.5) 51 / 47 / 2, left 2.32 / 2.39, dealt 1392 / 1493, 43.1 turns.
  Tiers win more in 4 of 5 sets (one level) and Blue keeps more 'Mechs in 4 of 5 (one level). +9 wins in 100 is about 1.3 standard deviations (not proven on wins alone); the 'Mechs-left and damage shifts are the steadier
  signal. This is the DEEP BASELINE for the new default (Daniel, 2026-11-08: "get a deep baseline for what will become the new default if it wins"). Default still off pending Daniel's go-ahead.
  Knobs untried: fraction, weights, peak v mean ratio. Daniel's note: the end-game stand-off is a picker problem (not closing in when winning), not a special mode.

- **2026-11-08 (Claude), TRIAGE: THE 40-BATTLE COMPARISON AT A 100-TURN CAP. REVIEW PENDING (higher-level model).**
  Princess (Red) v Gladiator + Legate (Blue); two sets of 20 battles (seeds 12345 and 2468), 100-turn cap (battles that ended inside 50 turns are identical at either cap, so only the draws were re-played at 100).
  BASELINE (triage off): seed 12345 8 / 11 / 1 (Blue wins / Red / draws); seed 2468 8 / 12 / 0; BOTH 16 / 23 / 1, 'Mechs left 1.48 / 2.58, damage dealt 1359 / 1557, 43.3 turns.
  TRIAGE both halves (25%, hot x2, cool x1.5): seed 12345 9 / 10 / 1; seed 2468 11 / 9 / 0; BOTH 20 / 19 / 1, 'Mechs left 2.45 / 2.15, damage 1440 / 1490, 43.6 turns.
  Blue's wins 16 -> 20 of 40 and the 'Mechs-left balance turns round (Blue 1.48 -> 2.45, Red 2.58 -> 2.15); the same direction in both seed sets. 20 v 16 wins is inside the noise of 40 battles (so is any
  win-count difference this size); the 'Mechs-left and damage figures move more clearly. First setting of anything in the peril / stack / triage line that beats the baseline. Default is still off (Daniel's call to
  turn it on); knobs untried: the fraction (25%), the two weights, peak v mean in the ratio. Next candidates: more battles (another 40 of each at 100 turns), the "finish the last enemy" mode.

- **2026-11-08 (Claude), TRIAGE RE-RUN (tie-break fixed) AND THE 100-TURN CAP. REVIEW PENDING (higher-level model).**
  Bug found and fixed: `triage.tier_of` broke ties between equal peril / toughness (several far-off units at 0) by `id()`, a memory address, so the same battle gave different results depending on what ran before it
  in the process (battle 10: 4 v 4 left in a 6-10 batch, 5 v 2 alone). Now roster order; a test covers it; batch and alone runs agree. The first triage tables (5/8/7 etc.) used the bad tie-break and were discarded
  (kept in run_stats/baseline/old_triage_tiebreak/, not in git). Re-run, 20 battles, 50-turn cap (Blue wins / Red / draws, left Blue / Red, dealt): baseline 8 / 11 / 1, 1.95 / 2.55, 1345 / 1508;
  both halves (hot x2, cool x1.5) 7 / 8 / 5, 2.70 / 2.40, 1431 / 1493; hot only 4 / 12 / 4, 1.00 / 3.45; cool only 5 / 12 / 3, 1.40 / 3.75.
  The draws re-played at a 100-turn cap: both halves' five draws (battles 2, 8, 10, 14, 18) finished Blue at turn 54, Red at 83, still a draw at 100 (Red 1 v Blue 2 left), Blue at 67, Red at 51, so the both-halves arm is
  9 / 10 / 1 against the baseline's 8 / 11 / 1 (its one draw, battle 11, is still a draw at 100 turns, Red 1 v Blue 2 left): a slight edge in wins, inside the noise of 20 battles, and the best 'Mechs-left
  and damage balance of anything tried (Blue now ends ahead on 'Mechs). Default stays off. Both unresolved-at-100 battles (10 and baseline 11) are the SAME shape: 1 v 2 left, a kiting stand-off
  (Legate is off with one enemy, so each Gladiator plays its own duel at range) - the "finish the last enemy" candidate above. Open: 40 battles of both halves at a 100-turn cap against a 100-turn baseline.

- **2026-11-07 (Claude), PERIL / TOUGHNESS TIERS (`config.TRIAGE`, `TRIAGE_FRACTION`, `TRIAGE_HOT_RECEIVED`, `TRIAGE_COOL_DEALT`; `INTEGRATION__triage`) AND THE MIRROR MAP (`triage.reach_on`, shown by the heat-map page); default off. REVIEW PENDING (higher-level model).**
  Per unit: peril (peak damage from every enemy's reachable spots at its hex) / effective HP, ranked over the team; the top 25% HOT (damage taken x2), the bottom 25% COOL (damage dealt x1.5); needs 3+ units.
  `tests/test_triage.py` (3 checks); 55 / 55 pass. First A/B, same 20 battles (Blue wins / Red / draws, 'Mechs left Blue / Red, dealt, turns): baseline 8 / 11 / 1, 1.95 / 2.55, 1345 / 1508, 36.5;
  both halves (hot x2, cool x1.5) 5 / 8 / 7, 2.45 / 2.65, 1414 / 1525, 42.1; hot only (x2) 4 / 12 / 4, 1.00 / 3.45, 1282 / 1614, 40.0; cool only (x1.5) 5 / 13 / 2, 1.35 / 3.90, 1295 / 1576, 36.3.
  Both halves together make the closest fight (left 2.45 v 2.65, damage 1414 v 1525, a third of the battles drawn at the cap) but win fewer battles than the baseline; either half alone is worse. Default stays off.
  Open: the fraction (25%), the weights, peak v mean in the ratio, and 40 battles of the both-halves arm to see if the draw pile is a real shift.

- **2026-11-07 (Claude), STACKED COVERAGE (Daniel's "stack the damage maps on a target's movement profile up to what kills it"; `config.STACK`, `STACK_WEIGHT`, `STACK_QUANTILE`; `INTEGRATION__stack`; default off) AND ITS FIRST A/B. REVIEW PENDING (higher-level model).**
  Built: per enemy, the teammates' peak damage fields summed over the enemy's footprint, capped at its effective HP ("full kill", Daniel), read as the mean (or a quantile) over the footprint;
  a candidate spot earns STACK_WEIGHT x the coverage it adds, joined to its damage dealt. `tests/test_stack.py` (3 checks); 54 / 54 pass, reference logs unchanged (default off).
  First A/B, same 20 battles (Blue = Gladiator + Legate wins / Red / draws, 'Mechs left Blue / Red, turns): baseline 8 / 11 / 1, 1.95 / 2.55, 36.5; stack 1.0 mean 6 / 13 / 1, 0.95 / 3.55, 27.6;
  stack 1.0 at the 25th percentile 8 / 12 / 0, 2.00 / 3.10, 25.6; stack 3.0 mean 8 / 12 / 0, 1.50 / 3.55, 23.1. No gain in wins, Red keeps more 'Mechs, but battles end 10+ turns sooner (draws gone):
  the term makes Blue commit harder, not smarter. Default stays off. Next: the mirror-image map as its own piece, peril / toughness tiers (Pick up here 000000 NEXT list), and a look at WHY (inspector on a stack battle).

- **2026-11-07 (Claude), PERIL HEAT MAP IN LEGATE'S MOVE SCORE: FIRST A/B (stage 6; `config.PERIL` off / peak / mean, `PERIL_BLEND`; default off). REVIEW PENDING (higher-level model).**
  The field replaces the damage taken from the OTHER enemies (not the foe) in `legate.Extras.adjust`; `peril.field_for` caches footprints and fields for the phase. Princess (Red) v Gladiator + Legate (Blue), the baseline's first 20 battles, seed 12345:
  baseline 8 / 11 / 1 draw (Blue wins / Red / draws), left 1.95 / 2.55, dealt 1345 / 1508; peak x1.0: 5 / 13 / 2, left 1.10 / 3.45; mean x1.0: 7 / 11 / 2, left 1.45 / 3.15;
  peak x0.5: 6 / 10 / 4, left 1.50 / 3.15. None beats the baseline (all a little worse, within the noise of 20 battles); peak is worst. Default stays off. Likely reasons to look at
  next: the field ignores which side of the unit is hit and each enemy's real chance of ending on a spot (peak assumes the worst spot, mean a flat spread); it replaces only the
  other enemies, so the foe term and the field disagree on scale. Not yet tried: weighting the spots (closer to Legate's estimate), arcs, a 40-battle run of the best arm.

- **2026-11-07 (Claude), PERIL HEAT MAP: STAGES 1-4 (visibility table, exact Peril field, tests, picture). REVIEW PENDING (higher-level model).**
  New `INTEGRATION__vision.py`: per-board N x N arrays (seen, to-hit modifier clipped 0..3, distance) from `los_cache.pair_info`, built once per board
  (ordered pairs: the modifier differs with direction on ~14% of pairs, line of sight does not). New `INTEGRATION__peril.py`: for each attacker, its
  `future_damage.range_profile` per modifier class laid over its `tiers.footprint` spots and filtered by the table; `peak` (worst case from any reachable
  spot) and `mean` per hex; `team_field` adds them. Arcs ignored (a mover chooses its facing). `tests/test_peril.py` (5 checks, in run_checks: 53 / 53 pass,
  reference logs unchanged: nothing in the battle uses it yet) and `tests/peril_picture.py` (the heat map of a saved battle turn as a page, pick the target
  and the attacker). Nothing is wired into Legate yet (stage 6).

- **2026-11-07 (Claude), PERIL HEAT MAP: DESIGN AND FIRST STEP (Pick up here 000000). REVIEW PENDING (higher-level model).** Daniel let
  the tiered order rest and chose the top-down peril heat map. First step done: `INTEGRATION__future_damage._ranged_for` and
  `range_profile(attacker, target, extra_tn)` (the damage at every distance, with a to-hit modifier option) split out of
  `future_damage` with no change in results (52 / 52 checks, reference logs identical). The rest of the plan, the reasoning on
  Daniel's two refinements, and the cost figures are in Pick up here 000000.

- **2026-11-07 (Claude), TIERED MOVEMENT ORDER. REVIEW PENDING (higher-level model).** Daniel's design (Ideas phase, same day):
  "units whose movement footprint is completely outside the enemies' ... move first; may intersect ... second; can not
  escape ... last"; slower first; units that will stand still first, farthest first; the tiers also on entering the
  battlefield; tiers 2 and 3 plan their two-ply against the highest-threat unit that could flank them; "not gaming
  winning on its own, but game losing if it is not there against a good opponent". `INTEGRATION__tiers` (module
  docstring has the full rule), `config.MOVE_ORDER = "tiered"` (default "index"), Gladiator units only (Princess keeps the
  move index), `baseline_battery.py --move-order tiered`, `tests/test_tiers.py` (8 checks; 52 of 52 pass, default and
  reference logs unchanged). Footprint = every hex `movement_options` gives; enemy footprint = the union over the enemy
  side; "could flank" = the enemy's footprint reaches a hex next to one the unit could end on. FIRST RESULT (40 battles,
  Princess v Gladiator, seeds 12345 and 2468, v the baseline on the same seeds; Princess / draws / Gladiator): 20 / 8 / 12
  against 20 / 5 / 15, 'Mechs left 3.48 / 1.52 against 2.70 / 1.75, Gladiator damage 1288 against 1349 (seed 12345 4 wins
  v 8, seed 2468 8 v 7): NOT BETTER, inside the noise. Gladiator units lost in turns 1-6 (seed 2468): 2.8 a battle v 2.2;
  units with no friend within 4 hexes about the same. WHY (one battle, Blue's tiers by turn): turn 1 25% safe / 75% may be
  flanked; turns 2-10 about 35% stand still, 50-56% may be flanked, 0-4% safe, 9-12% trapped - the union of twelve enemy
  footprints covers nearly the whole field, so the tiers barely separate units and the order falls back to slowest first.
  The two parts (order, flanker foe) were not tested apart. Next: refine the footprint rule (per enemy, or by how many
  enemies reach), then test order-only and foe-only. Future (Daniel): teach Legate to read the battlefield for good terrain; hold back until most of the
  combat power can engage at once.

- **2026-11-07 (Claude), TURN INSPECTOR; THE "25% HIGH" DAMAGE ESTIMATE SETTLED; MOVE ORDER AND TEAM VALUE RESULTS. REVIEW PENDING
  (higher-level model).** (1) `tests/turn_inspector.py <pp|pg|gg> <battle> <turn> [--unit NAME] [--set NAME=VALUE]
  [--json FILE]` (Daniel: "select a turn in a match, and get a read back of all the math ... a feature and for trouble
  shooting"): plays battle N of the baseline battery to the end of turn T-1 once and keeps the saved state
  (`run_stats/inspector/`), then loads it and plays only turn T with the recorders on - same dice, so the turn is exact
  (checked: battle 1 turn 12, all 24 units' HP and hexes and all 29 shots identical to the batch) and repeatable in
  seconds, or under a changed setting (a one-turn A/B). Prints Legate's estimate v where units ended, each move's
  predicted v real-spot score and regret, each attack's movement-model value v the fire phase's dry run v the ranged
  and physical damage that landed, every shot and physical attack, HP before / after. The recorders moved from
  `legate_probe.py` into `tests/probe_hooks.py` (same output: battle 6 compared turn by turn). (2) The "Gladiator
  rates its own damage ~25% high" item (Pick up here 0000): NOT an error in the damage math (see INTEGRATION__BOTS.md
  Next steps): the ~25% compared structure-weighted points with raw ones, and on 13 battles the model is within a few
  percent at range 2+; the gap is attacks from an adjacent hex (the physical attack that follows, ordinary value about
  2x the real 3 points, and pushes valued at the target's whole HP). Also found: the battle log's damage counters read
  0 for a push that removes the target off the board, and `damage_dealt` counts ranged fire only. (3) Movement order
  (20 battles, Princess v Gladiator): index 11 / 1 / 8, random 10 / 2 / 8, reverse 9 / 6 / 5 - order alone barely
  matters; Daniel wants the tiered order (stand-still first, then out-of-footprint, may-intersect, cannot-escape) built as
  a switch to guard against a strong opponent. (4) Team value re-test: none beats the baseline (BOTS.md). Also
  `baseline_battery.py --exchange / --stats`, `tests/battery_stats.py`.

- **2026-11-07 (Claude), RESUMABLE BATTERIES + MOVEMENT-ORDER SWITCH. REVIEW PENDING (higher-level model).** Daniel: "write the
  driver and make it standard equipment". The sandbox restarted twice during the first movement-order batteries and killed
  them mid-run. `tests/baseline_battery.py` now saves every finished battle at once (whole file, then rename, so never a
  half file) under `run_stats/baseline/saved/<setup, Legate, target, settings, seed, turn cap>/battle_NNN.json` and skips
  a saved battle when the same command is run again (a battle's seed depends only on its number, so saved and fresh are
  interchangeable; `--fresh` ignores them). `tests/battery_summary.py` prints one line a set (wins, draws, 'Mechs left,
  damage dealt, turns) and can read old console logs (`--log`). Also `config.MOVE_ORDER` ("index" default = Princess's
  move index; "random" = a deterministic shuffle seeded from the units' names and hexes, never the battle dice;
  "reverse" = lowest index first) and `baseline_battery.py --move-order`, to measure how much the order within a side
  matters (Daniel's tiered-order ideas, 2026-11-07, are Ideas phase). Default behaviour unchanged: all 51 checks pass. `--stats` (same day, Daniel: "record everything and generate end of game stats for every unit") saves each battle's INTEGRATION__stats event log in its saved file; `tests/battery_stats.py <name>` builds the per-unit statistics page from them (no measurable time cost: 4.85 v 4.88 s a turn on a 3-turn Gladiator v Gladiator test).

- **2026-11-06 (Claude, session 20), DECISION (Daniel): speed work stops here; "maybe go for the full rebuild next week".**
  His reading: the time now lost is translating between the two codes - which the measurements back (the Python /
  Rust boundary, MovementCandidate objects, per-option passes: see the entry below). If the full Rust rebuild is
  taken up, design it so that nothing crosses per option: units, options, hex rows, arc classes and the fire tables all
  live in Rust, and Python (the bots' decisions, config, reports) calls it once per question with whole batches.
  Where things stand: `fastcore/` holds the weapon choice table (+ missile pricing), the movement search, line of
  sight and hex distance, all with the Python as fallback and specification; 12 v 12, 5 turns: 59 s -> 19 s, same battle.

- **2026-11-06 (Claude, session 20), RUST EVALUATE LOOP: TRIED, MEASURED, NOT KEPT. REVIEW PENDING (higher-level model).**
  Daniel: "Go for it" (the `evaluate` rewrite). Built `fastcore.EvalCore`: the per-option arithmetic of
  `MoveEvaluator.evaluate` (to-hit numbers, the best-twist memo, the max over an arc class's FastTables) in Rust on a
  dry board with no AMS, Python keeping the hex rows, arc classes and results (two passes over the options). It gave the
  same battle (reference logs identical, 51 of 51) and NO speedup: 12 v 12, 5 turns, 19.2 s before and 20.0 s with it.
  Reverted (no code kept). Why, measured in real time (not cProfile) on 838,000 options in 4 turns of 12 v 12:
  `evaluate` is 8.7 s of an 18 s run, ~10 us an option, and the Rust-able part (memo + fire-table calls) is only ~1.7 s of
  it; the rest is Python that stays when only the arithmetic moves: building the 627,000 MovementCandidates
  (~0.8 s), 221,000 hex rows (1.3 s), registering ~18,000 scorer groups (1.85 s), the adjacent-hex physical attacks
  (0.9 s, 43,000 calls), and the two passes over the options themselves (~2.5 s). Also tried and dropped (no gain):
  one tuple of scorers per arc class; calling the Rust fire table straight from `score`. What would still help is
  not another kernel: keep each mover's options, hex rows and arc classes alive in Rust between calls (a persistent
  option set), so Python never touches an option per call - a redesign of `evaluate`, Legate's `rows` / `combine` and
  the consumers of MovementCandidate together (movement_selection, Legate, Princess, movement_attacks), estimated
  at <= 1.3x for several million tokens. Running more battles at once (cores / sessions) scales better.

- **2026-11-06 (Claude, session 20), RUST PORT STEP 6: SCORER CONTEXT, AND A CORRECTED CEILING. REVIEW PENDING (higher-level
  model).** Daniel: "Go for it" (the `evaluate` / Legate `combine` rewrite). Speed only: 51 of 51 checks, reference logs
  identical. `ranged_combat._ScorerContext`: the firer's dissipation, weapons, damage table, other heat and the two
  units' `fire_state`s are read once per (firer, target) pair instead of once per scorer (~20,000 scorers in a 4-turn
  12 v 12); `weapon_selection.shared_fire_table` takes the states. 12 v 12, 5 turns: 20.1 -> 19.2 s.
  CORRECTION to the estimate given when asking for the go-ahead ("a second 2.9x"): the region the rewrite would replace
  (`evaluate`, the scorer memo calls, `_hex_row`, Legate `rows` / `combine`) is ~44% of the profiled time (24 of 55 s);
  even a 10x faster Rust version of all of it leaves 33 s of 55: at most ~1.7x more, and only after moving the
  results (MovementCandidate objects, Legate's rows) into flat arrays too. What remains outside it is spread over
  ~40 functions of 1-4% each. So the rewrite is a large, risky change for <= 1.7x; not started - Daniel's call.

- **2026-11-06 (Claude, session 20), RUST PORT STEP 5: MORE CACHES, AND WHERE THE TIME IS NOW. REVIEW PENDING (higher-level
  model).** Speed only: 51 of 51 checks with and without the Rust built, every reference log identical, benchmark
  501 / 495.
  - `damage_resolution.derived` (the `get_weapons` cache's sibling: kept while a battle is played and no slot is lost)
    for `attack_resolution.weapon_locations` and `arcs.mech_turrets`; `future_damage` works out its arc key, blocked
    set and to-hit base once, not at each of ~30 distances; `weapon_selection.fire_state` uses its own cheaper copy of
    the damage signature (`_damage_state`; `kill_curve._signature` itself is untouched - its text seeds the kill
    curve's dice).
  - Honest total, 12 v 12 Gladiator v Gladiator (Legate on), same battle (HP identical), 5 turns, one core:
    59 s before this session's Rust work (main at the statistics PR) -> 20 s now = 2.9x. (Daniel's hope was ~30x: a
    full port; a handful of sections gives ~3x because the time is spread thin.)
  - Where the time is now (4-turn cProfile, 59 s profiled): `evaluate` + Legate `combine` ~49% (its own loop 5%, the
    scorer memo calls ~18%, `_with_physical` 6%, `_hex_row` 5%, the Rust fire table itself ~5%), `fire_state` keys ~5%,
    `future_damage` ~6%, `reduced_options` ~4%. Nothing above 10% is left that has a clean boundary: what is left is
    Python plumbing around many small calls, so the next gain is moving whole loops (the `evaluate` per-option loop with
    its memos, Legate's `combine`) with their data flat in Rust - a rewrite of those two, not another kernel.

- **2026-11-06 (Claude, session 20), RUST PORT STEP 4: LINE OF SIGHT, HEX DISTANCE, AND THREE PYTHON CACHES. REVIEW
  PENDING (higher-level model).** Speed only: 51 of 51 checks with and without the Rust built, every reference log
  identical, benchmark 501 / 495.
  - `fastcore.LosBoard` (Rust): a copy of `pathfinder/los._evaluate` (Core pp.56-58, 66, 124, 240; TO:AR pp.29, 36, 38)
    for `los_cache.pair_info` - the hex line (from (0, 0), the same float operations, Python's round half to even), both
    sides of a border line, woods / ultra-heavy / smoke / fields, partial cover, the target's woods. Python hands it a
    snapshot of the board (`los_cache._build_rust_los`); `INTEGRATION__smoke` drops it whenever the smoke changes (a
    trace reads the live board). `config.FASTCORE_LOS`. `los.hex_distance` is the Rust function when built.
  - `damage_resolution.get_weapons` keeps its answer while the mech's `destroyed_slot_info` keeps its length (every
    writer of `crits` / `destroyed_slot_info` adds an entry), only while a battle is played (`play_on` switches it on:
    tests that edit `mech.crits` by hand outside a battle see their edit). `config.WEAPONS_CACHE_VERIFY` compares every
    cached answer with a fresh scan (on in `tests/test_fire_tables.py`).
  - `structure_weight.multipliers` kept per (weapons and their damage, target's armor / structure, side, k), emptied each
    turn; `movement_selection.spot_hazard` / `_safest` return 0.0 at once on a board with no hazard hex
    (`terrain_rules.has_hazard_terrain`).
  - Checks: `tests/test_fastcore.py` compares Rust v Python line of sight on 7 boards x with / without smoke x 4 height
    codes (14,000 pairs: results, entry directions, distances, arcs, off-board errors) and `hex_distance` on 50,000 pairs.
  - Result, 12 v 12 Gladiator (Legate on), 5 turns: 62.2 s (no Rust, no caches) -> 36.5 s (steps 1-3) -> 23.3 s (now),
    the same battle: 63% less, 2.7x. Left, by the profile: the `evaluate` loop and Legate's `combine` (Python plumbing
    around the scorers, ~40%), `future_damage` (~9%), `arcs` (~4%).

- **2026-11-06 (Claude, session 20), RUST PORT STEP 3: THE REACHABLE-SPOT SEARCH (`fastcore.PathBoard`). REVIEW PENDING
  (higher-level model).** Daniel: "Go ahead and do all three" (evaluate loop, reachable spots / movement table, Legate
  future damage). This is the second. Speed only: 51 of 51 checks with and without the Rust built, every reference log
  identical, benchmark 501 / 495.
  - `fastcore.PathBoard` (Rust): a copy of `pathfinder._build_terrain_psr` (the Dial's-algorithm sweep: same buckets
    in the same insertion order, the same "strictly better (forward count, fewer PSRs) replaces" rule) plus the state
    lists `ranged_combat._movement_options` builds from it: `walk_states` (a mover walking from its own hex) and
    `entry_states` (turn 1, entering from the edge: every edge hex x 6 facings). Python gives it the board's step data
    once per board and level-limit class (`ranged_combat._rust_board`, kept on the board's cache so `forget_board` drops
    it); finished tables are cached in the Rust like `board.tables`. Boards with no PSR terrain use the same search (a
    backward step only onto the same level, no PSR counts, as `_build_terrain_aware`). Boards with live hazards (magma
    crust), `standup_mp` and `keep_parents` paths stay in Python. `config.FASTCORE_MOVEMENT` (on) switches it off.
  - A quirk the Rust copies on purpose: while a mech ENTERS the board `_note_psrs` runs as each state is yielded and the
    reduction (`movement_selection.reduced_options`) reads the PSR count then, so a state reached again by a way with
    fewer PSRs is read with its FIRST count and holds the fewest only afterwards. The first version returned the final
    counts and changed one reference battle (LargeLakes1: 92 v 93 spots); `entry_states` now returns both.
  - Checks: `tests/test_fastcore.py` `the_rust_movement_search_matches_the_python_on_real_boards` (6 boards, 5 'Mechs,
    random starts / facings / blocked hexes / destroyed hips: states, order, PSR counts, entry states, and the reduced
    states the picker reads, Rust v Python). It did not catch the entry-order quirk by itself (a mutation test
    passed); the LargeLakes1 reference battle does.
  - Result, 12 v 12 Gladiator (Legate on): 2 turns 21.1 -> 15.0 s (turn 1 is the entry search); 5 turns 62.2 s with no
    Rust at all -> 36.5 s with all three Rust steps (41% less), same battle. Next: the rest of `evaluate`, Legate.

- **2026-11-06 (Claude, session 20), RUST PORT STEP 2: MISSILE / SPECIAL WEAPON PRICING IN THE RUST TABLE. REVIEW
  PENDING (higher-level model).** Speed only: 51 of 51 checks with and without the Rust built, reference logs
  identical, benchmark 501 / 495. `fire_modes.Planner.price_spec` describes a special weapon in numbers when it has
  ONE shot plan (a single ammunition kind) and is an ordinary attack: the range modifier and bracket by distance,
  the TN change and the hit worth (`Planner._hit_worth`, split out of `value()` unchanged) by bracket, and the
  heat. `FastTable` kind 3 then prices the (distance, pre-TN) rows itself: hit_probability(TN) x worth, the same
  float operations as `value()`. An Ultra / Rotary AC is covered too when `STUB_RATE_OF_FIRE` is "max" (default) or
  "single" (the rate does not depend on the row); "greedy" asks the planner row by row. Still asked row by row
  (kind 2): LB-X with two ammunition kinds, Narc beacons, MML / ATM with several kinds, anything with more than one
  plan. `config.FASTCORE_PRICING` (on) switches the step off. Checks: `FIRE_TABLE_VERIFY` compares every Rust
  answer with Python's; `the_rust_fire_table_is_really_used_when_built` also fails if no weapon was priced in Rust.
  Result, 12 v 12 Gladiator, 2 turns: 24.0 s -> 21.1 s; with step 1, 29.3 s -> 21.1 s (28% less) in all. Planner
  callbacks 135k -> 36k. Next by the profile: the rest of `evaluate` (the per-spot loop and its memos, ~25% of a run),
  `reduced_options` and the movement table (~25%), Legate future damage (~9%).

- **2026-11-06 (Claude, session 20), RUST PORT STEP 1: THE WEAPON CHOICE TABLE (`fastcore.FastTable`). REVIEW PENDING
  (higher-level model).** Daniel: "Lets start with weapon pricing. See how much of an improvement we can get."
  Speed only: 51 of 51 checks with and without the Rust built, every reference log identical, benchmark 501 / 495.
  - `fastcore/src/lib.rs`: `FastTable`, a copy of `weapon_selection.FireTable.choose` - candidates in weapon order,
    value = table value x the side's structure-weight scale, the row cache, the knapsack levels solved again only at
    a larger budget, Phase 2 padding. Same sums in the same order, so the same answer to the last bit. Plain weapons
    are priced from flat grids (`build_expected_damage_table` now keeps one per weapon, `table["flat"]`); missiles
    and other special weapons call back into the Python planner (`fire_modes.Planner`) for their value and heat -
    that part is NOT ported yet.
  - `weapon_selection.FireTable.choose_value` (what the movement scorer reads - the value only) builds the
    FastTable on first use (`_build_fast`; falls back to Python when not built, `config.USE_FASTCORE` off, a
    non-integer heat, more than 64 weapons, or a planner heat the Rust can't take). `ranged_combat` `score()` calls it.
  - Checks: `config.FIRE_TABLE_VERIFY` now also compares the Rust answer (value, heat, chosen weapons) with
    Python's on every call (`tests/test_fire_tables.py`, all 3717 tables of a 12 v 12 matched);
    `the_rust_fire_table_is_really_used_when_built` fails if the tables silently fall back to Python.
  - Result, 12 v 12 Gladiator (Legate on), 2 turns: 29.3 s -> 24.0 s (18% less), same battle. What is left of weapon
    pricing in the profile: the planner callbacks (135k in those 2 turns, ~16% of a profiled run); to port them
    the planner's per-weapon constants (bracket TN offsets, expected hit worth per bracket) go over once per table
    and the Rust prices the (distance, pre-TN) grid and picks the munition / rate itself (stubs' policy: best
    value, ties to the plain kind; rate: STUB_RATE_OF_FIRE).
  - `tests/test_hazards.py` `magma_heat_is_uncapped` failed ~3 runs in 100 with no code change (a heat-phase
    ammo-explosion roll at 30+ heat was unseeded); it now scripts the dice.
  - Build: `cd fastcore && maturin build --release && pip install --force-reinstall target/wheels/*.whl`
    (needs `pip install maturin`; `tests/test_fastcore.py` skips when not built).

- **2026-11-06 (Claude, session 20), RUST PORT - PROFILE AND PLAN. REVIEW PENDING (higher-level model).** Daniel:
  20 battles an hour (the 12 v 12 baseline battery, ~3 min a battle on one core) is too slow to iterate on bot
  logic; "Go for stage 2 [the compiled scoring]. If nothing else, slowly port over to rust one section at a time."
  No code changed yet. Profile (cProfile, 12 v 12 Gladiator, Legate on, 3 turns, 176 s; real time is ~half):
  `evaluate` 50% cumulative (88 s) of which the weapon choice (`FireTable.choose` 46 s, `fire_candidates` 34 s,
  fire_modes planner 25 s, knapsack 6 s) is most; `reduced_options` / `_movement_options` 15% (27 s);
  `build_movement_table` + `_build_terrain_psr` 11% (19 s); LOS (`los.walk`, `hex_distance`) ~5%; Legate
  `future_damage` ~9%. The spread is FLAT: no section is over ~26%, so one section alone gains 1.1-1.4x (Amdahl);
  the 30x Daniel hopes for needs most of the engine in Rust. CORRECTION to the 2026-11-06 estimate "20 battles in
  well under 10 minutes from stage 2 alone": that held for the exhaustive search, not the grid default.
  Section order, easiest boundary first (each one keeps the reference logs byte-identical, Python stays the
  fallback and the spec, as `fastcore/` does): (1) pathfinder movement table (flat data: step costs per hex /
  direction in, table out; ~11%); (2) LOS and hex distance (~5%); (3) weapon pricing: per-weapon rows, fire table,
  knapsack (~26%; the fire_modes planner for missiles is the hard part); (4) reduced_options / spot hazards;
  (5) Legate future damage; then the movement score itself. Estimate: ~6-10M tokens for all of it.

- **2026-11-06 (Claude, session 20), BATTLE STATISTICS - REVIEW PENDING (higher-level model).** Daniel asked what
  the Monte Carlo should output; he and Claude sorted three AIs' lists (his answers: Section 5 "Battle statistics").
  Built (stages 1-3 of 5):
  - `INTEGRATION__stats.py`, the COLLECTOR: a per-battle event log (one row per ranged shot with range, TN, roll,
    hit and damage; one per physical attack, charge and DFA; every unit's state at each turn's end - HP, hex,
    heat, prone, shutdown, locations lost, engine / gyro / cockpit hits, explosions, pilot hits; the turn, phase
    and cause of each death; who landed each killing blow). It rides on `BattleResult.stats`. It only reads.
  - `INTEGRATION__stats_report.py`, the ANALYSIS: outcome (win / draw with a 95% Wilson interval, how draws
    ended, battle length, the running win rate, shortest / longest battles with seeds), per unit (survival,
    death turn / cause / phase, killer, damage dealt and taken as mean / median / p10 / p90, kills per game,
    damage by weapon and by physical attack, shots and hit % by range, locations lost, criticals, heat, prone and
    shutdown turns), per team (units standing and force remaining by turn with a p10-p90 band, survivors at the
    end, first / second kill turn, focus fire, spread, each unit's share of the team's damage), and curves by
    turn. `INTEGRATION__stats_viewer.html` draws it (inline SVG, no libraries, light / dark); the page and its
    JSON go to `stats/` (git-ignored) at the end of every batch (`config.STATS`, `STATS_DIR`).
  - Hooks: `attack_resolution.run_ranged_phase` (every shot, and pooled cluster lumps), `physical.run_physical_units`
    (every physical attack), the orchestrator (turn snapshots, deaths by phase, start / finish). 30 test files
    set `config.STATS = False` (they compare output or run batteries); `check_reference_logs.py` and
    `test_parallel_batch.py` add it to their scenario code. New: `tests/test_stats.py` (logging changes nothing;
    the log agrees with the result; a 2 v 2 batch analyzes; the page carries the analysis).
  - Checks: `python tests/run_checks.py --bench`: 51 of 51 pass, every reference log identical (no `--update`),
    the benchmark's "resolving hits and damage" unchanged at 0.0 s. A 30-battle Kontio v Hammerhead batch (6.5 s
    a battle, 8 workers) and a 16-battle 2 v 2 batch both write a page that loads with no errors and no sideways
    scroll at 400 px.
  - LEFT (stages 4-5): wasted damage / overkill and critical slots (need a hook inside `apply_damage`); PSR
    counts; BV-weighted force value by turn; paired comparisons with a confidence interval (`ab_batches.py`);
    initiative advantage; matchup and terrain tables; the bots' predicted v actual (calibration, regret) in the
    report (`legate_probe` has the data); outliers linked to replays. Pushes show in the turn totals, not as a
    damage row.

- **2026-11-06 (Claude), REVIEW QUEUE CLEARED: LEGATE, SAVED STATES, COMBAT LAB ART.** Review of queue items
  (d), (e), (f), (h), (g), (k), (l) by the higher-level model (Daniel: "clear the rest of the review board").
  - (d) / (f) Legate team options: `fire_share` / `now_share`, `MultiLifetime`, `_Herd`, `_Cohesion`,
    `brackets`, `_TeamFire` read through; the team-value arithmetic checked (the score comes out as dealt +
    the team's future damage, as documented; with the exchange, as documented). Two fixes:
    (1) `_FRIEND_DMG` (team fire, LEGATE_TEAM_VALUE - off by default) is now emptied every Movement Phase:
    keyed by positions only, a teammate standing where it stood on an earlier turn reused damage worked out
    before either unit was hurt. (2) BOT CHANGE: `Extras.adjust` left out the fire of an enemy whose
    ESTIMATED end hex is the spot being scored, so those spots looked safer than they are; that enemy now
    shoots from where it stands (it will end somewhere else). About 1% of Gladiator moves (2 of 198 in a
    probe battle). A/B, same 20 seeds, baseline battery (Princess wins / draws / Gladiator wins; 'Mechs left
    P / G; damage dealt P / G; turns; battles at the cap): without 11 / 1 / 8, 2.60 / 1.75, 1529 / 1378, 37.6,
    2; with 11 / 1 / 8, 2.55 / 1.95, 1508 / 1345, 36.5, 1 (7 battles identical) - level within the noise,
    kept as the correct score. These are also the first battery numbers on the MegaMek-seam field (32 x 17):
    the new BASELINE (the older ones, 8 / 4 / 8 and before, were on 33 x 17).
  - (e) The probe battery's monkeypatches (wrappers that record and pass the original answer through):
    battle 1 with `--calib` gives exactly the battery's battle 1 (Red after 40 turns, 4 left, 1750 / 1177
    dealt). One harmless quirk: `--calib`'s raw (k = 1.0) pass can reuse a physical-attack Worth built under
    the configured weight (`movement_attacks._WORTH` keys by unit and HP, not the weight) - the diagnostic's
    raw column only, never the battle.
  - (h) Saved states: the round-trip check passes (every reference battle saved, reloaded and played on
    after every turn, byte for byte); module caches not emptied on a load (`_WORTH`, the LOS / hex-property
    boards) key by an object they hold or compare, so a reused id can't hit them. Nothing to fix.
  - (g) / (k) / (l) Combat Lab art (art checks only, Section 7): the workbench is safe (codes are JSON, a
    unit name only matches a file in the library, the Windows starter binds 127.0.0.1); the argmin guard
    covers the reported crash; pyflakes clean; 300 random library units built in all three bodies with no
    failure. Fixed: `tokens.read_unit` skipped PATCHWORK armor lines ("LA armor:IS Reactive(Inner
    Sphere):8"), drawing those units (e.g. the Spindrift SDT-1) with no armor - the points are now read after
    the last colon. Found: `tests/test_token_shell.py` prints PASS but SKIPS its geometry checks when scipy /
    trimesh are missing - they were missing in this container; `requirements.txt` now lists them (art only).
  - Checks: 50 of 50, reference logs identical, the round trip identical.

- **2026-11-06 (Claude), REVIEW: KILL CURVE, RUST, FIRE TABLES; MEGAMEK MAP SEAMS.** Review of queue items
  (c), (i), (j) by the higher-level model, and Daniel's map-seam call. 50 of 50 checks, every reference log
  identical, benchmark 501 / 495 - with the Rust built and without.
  - MAP SEAMS (Daniel: "It should follow Megamek's conventions"; MegaMek BoardUtilities.combine, master):
    stitched boards now ABUT - no gap between rows, none after an even-width board (16-wide sheets keep
    their column parity and join up as drawn). Only after an odd-width board (the pack has 15- and 45-wide
    maps) one blank column, MegaMek's default padding, restores the parity. MegaMek fills that column with
    terrain blended from both sides (random woods / rough); ours stays blank. A 2 x 1 field is now 32 x 17
    (was 33 x 17: `tests/baseline_battery.py`'s field is one column narrower, so its battles change). Test:
    `test_terrain.stitched_map_loads_and_crosses_the_seam` checks every hex of the second and third boards
    sits exactly 16 columns / 17 rows on, and the odd-width padding.
  - (c) Sound: the kill curve's own dice (every roll in the damage path goes through config.roll_2d6 /
    pick_number, looked up at call time; mechsim's `config` is the same module), its trials write nothing
    outside their copy (quiet() also silences the replay's sink), the fire director's dry run changes
    nothing, `fire_pick`'s ranking, the advance-into-an-occupied-hex fix, and `princess.direction`'s 5 for
    the same hex (checked against MegaMek's Coords.radian: equal x and y give 1.5 pi, / (pi/3) = 4.5, Java
    rounds to 5). Fixed (no result change): the kill-curve cache outlives a battle and is keyed by
    `id(mech)`, which Python reuses; the state signature can't tell armor types apart (hardened armor has no
    slots), so a freed unit's id reused by another design could have found its curve - the armor and
    structure types are now in the key. Doc fix: the trials' seed has no design name in it (a 'Mech has no
    `name`), only the side and the damage state.
  - (i) Sound: the Rust knapsack is the Python's step for step (levels visited high to low, strictly better
    replaces, new levels at the end, first highest wins, the same float sums). Built here and compared on
    60,000 random knapsacks (heavy ties, zero-heat weapons, up to 64 candidates): the same winner, heat and
    weapons, and the same `knapsack_levels` in the same order. The one difference (a sorted list v a Python
    set of indices, which isn't always in ascending order) can't matter: every caller turns it into a set of
    weapons and walks the weapons in their own order. The `special` / `has_profile` caches read only the
    weapon's name and fixed data (missile, Ultra / Rotary, profiles, flamers / plasma by name), so a cached
    answer can't go stale. Fixed (latent crash, no result change): `knapsack_levels` sent a non-integer heat
    budget to the Rust, which raises TypeError there (`best_subset` catches it; this one didn't) - it now
    checks the budget first.
  - (j) Sound: solving once at the largest budget and filtering gives exactly a smaller budget's answer
    (levels at or below a budget are built only from lower ones, in the same insertion order, when no heat
    cost is negative - the table checks that) - also run against fresh solves at every budget in the
    60,000 cases above. The shared table's key covers what the first caller's tn_adjust / Planner / scale
    read: attacker and target state (`fire_state`, incl. active stealth, which ECM positions can change in
    mid-movement - it is in the key each time a scorer is made), aim, AMS count, water, unavailable weapons
    (ammo, jams, arcs, held limbs), the weighting switch, and the role; cleared every turn and on a load.
    Nothing missing found.

- **2026-11-06 (Claude), BV REVIEW ITEM (b) CLOSED** (Daniel: "the BV difference was a non issue. Calculated value matches Mordel"). Crusader CRD-3R stays at 1317; review item (b) removed from the queue. Docs only.

- **2026-11-05 (Claude), session 18 - WORKBENCH: SHAREABLE CODES; A CRASH GUARD** (Daniel: "error: attempt to get argmin of an
  empty sequence" - a Clan LB 20-X on an arm with no lower arm or hand actuator; "as a feature, a copyable code that I can paste so
  you can plug it back in and see what I'm doing"). REVIEW PENDING (higher-level model). Art only; the art checks pass.
  - Not reproduced here (360 combinations of tonnage, body, arm block, side and rail on that gun all built), so the cause is
    unconfirmed. Guarded: `Solid.hit` returns the start point when no face can be left through (a zero direction made the
    argmin empty); `_arm_grid` does not seat a block centred on the arm along a direction it does not have.
  - Codes: `token_workbench.encode` / `decode` (the page's whole setting, JSON, zlib, URL-safe base64, prefix "CLW1."). The page
    has "Copy code" and "Load pasted code"; a failed build puts its code in the box. `python -I tools/token_workbench.py --code
    <code>` rebuilds a pasted code here with the checks. The server prints the full error of a failed build.

- **2026-11-05 (Claude), session 18 - THE ARM HARDPOINT GRID; WEAPONS BLOCK WEAPONS** (Daniel, from a workbench test: an Atlas
  with 8 medium lasers pinned to one rail of its right arm showed "6 in line with each other, most of which shots would be blocked
  by the one in front of it and a 7th off on its own. No idea where laser 8 is." His fix: "a 6x6 grid laid over the end of the
  arm. The inner 4 squares tend to be reserved for the hand, the middle ring of 12 are the normal weapon slots and the outer ring
  of 18 are virtual slots that give space for bulky weapons to expand into. Groups of squares can be combined to use their average
  center of gravity as a hard point. (For example on a mech with no hands the 4 center squares would be merged into one bigger
  square to fit a single weapon.)"; also equipment hardpoints facing other directions - shields, electronics, turret pods such as
  the Catapult's box launchers on its shoulders). REVIEW PENDING (higher-level model). Art only; the art checks pass.
  - Cause: the clear-muzzle check only tested against the body, never against other weapons, and line rails queued weapons one
    behind another.
  - `INTEGRATION__shell_facet._arm_grid` / `_arm_grid_geom`: the grid over the end of each forearm, the four centre cells the
    forearm's own section (the hand, or with no hand one big port), the middle ring of 12 around the outside of the forearm, the
    outer ring of 18 for bulky weapons. Each weapon takes a block of cells sized to its cross-section, as near its preferred ring
    position as the free cells allow (bulky weapons first); its hardpoint is the block's centre. Ring weapons are pulled in along
    their own direction until they seat on the forearm; one wholly in the outer ring gets a mounting bracket. An arm now has 12
    "rails" (`shell_items.rail_count`): the ring positions, which the workbench's rail menu pins. Brackets show the 12 and the
    centre (H = hand, C = centre port).
  - Weapons count as obstacles in the clear-muzzle check (`Sink.items`); line rails place their items SIDE BY SIDE.
  - New missile mount "post" for the humanoid (launcher pods on top of the side torsos: the Catapult). Shields and electronics
    facing other directions are not built yet.
  - Daniel's test now: 8 medium lasers with a hand ring the wrist; without a hand they make a grid of ports over the arm's end;
    0 floating, 0 clipping, 0 blocked muzzles (also 3 large lasers, 2 PPCs, an AC/20).

- **2026-11-05 (Claude), session 18 - WORKBENCH BUNDLE FOR A WINDOWS DESKTOP** (Daniel: "So? no link to it?" - the cloud
  preview never reached him; "D:\Claude\Model viewer. You have permission to push the required files into that folder"). This
  cloud session cannot reach his computer (no folder shared), so the workbench ships as a zip he unzips there.
  REVIEW PENDING (higher-level model). Art only.
  - `tools/make_workbench_bundle.py <out.zip>`: the workbench, the ten modules it imports, the token data, equipment.json,
    meks.zip, and `tools/workbench_windows/` (start_workbench.bat: finds Python, installs numpy / scipy / trimesh / python-fcl,
    starts the server on 127.0.0.1:8765, opens the browser; README.txt). Tested unzipped on Linux; the .bat is untested.
  - `token_workbench.py --host` (127.0.0.1 on a desktop; 0.0.0.0 stays the default for the cloud preview).

- **2026-11-04 (Claude), session 18 - COMBAT LAB WORKBENCH** (Daniel: "a viewer that lets me manually set what blocks are being
  used. Sliders for tonnage and mobility, and drop down menus for weapon loadouts with the ability to control which mounts they
  use. Basically full control over any combination. Which will let me systematically do testing."). REVIEW PENDING
  (higher-level model). Art only; the shell test passes.
  - `tools/token_workbench.py` (a small web server, stdlib only) + `tools/token_workbench.html`: start with
    `python -I tools/token_workbench.py --port 8765 [--meks <unzipped meks folder>]`, open the port (in a cloud session the app's
    preview). Each change rebuilds the 'Mech with the real faceted builder. Controls: tonnage, walk and jump MP, armor level,
    engine and cockpit type, body (humanoid / bird), head mount, reference tags on / off, arm actuators; a menu per block slot
    (auto = tag or name hash; the page shows what each slot resolved to and why); a loadout table (any of 686 items, its
    location, its rail or auto); load any of 4,225 unit files and change it; layers, X-ray, edges, mounting brackets; "Run
    checks" (volume by location against its budget, floating, below ground, clipping, blocked muzzles). Not an Artifact on
    purpose: a published page cannot run the Python builder.
  - `INTEGRATION__shell_items.place_items` honours `unit["force_rails"]` ({zone: {item index: rail}}) for the workbench's rail
    pins; the shuffle is unchanged otherwise.

- **2026-11-04 (Claude), session 18 - TEST RANGE FACETED FROM THE NAME HASH; PER-SLOT HASH FIX** (Daniel: "go ahead and generate
  our smaller test batch's hash values as faceted"). REVIEW PENDING (higher-level model). Art only; the three art checks pass.
  - The viewer gets a fifth variant, "Faceted, name hash" (`tools/token_3d.py --range`, `facet_hash`): each range chassis built
    with no reference tags, as an untagged unit would be.
  - BUG found and fixed: `pick` read the slot's block from a byte of the 8-byte name hash, so every slot after the eighth always
    took its first block (every name-hash unit had prism legs, drum knees, heel-and-toe feet, a box head, box pauldrons, octagon
    forearms). Each slot now hashes the unit's name with the slot's name. Tagged slots are unchanged; untagged slots of tagged
    units change look too.
  - Heads are fitted to the Head budget as a whole (glass, canopy and ears included: the bubble head was 1.7x over); the bird
    body's nose cockpit may scale 0.6-1.6 (the Locust's was capped short).
  - Seen, not changed (for Daniel): the name-hash Archer has a missile rack standing at an odd angle off its round torso's top
    edge; the name-hash JagerMech (a bird body) shows an amber plate on its canopy.

- **2026-11-04 (Claude), session 18 - BLOCK VARIANTS FOR EVERY BODY PART** (Daniel: "systematically add variant blocks for each
  body part. Lets try to build up the dictionary before regenerating the full list of mechs. I will want to look at each set of
  parts as seperate pieces."). REVIEW PENDING (higher-level model). Art only; the three art checks pass.
  - New blocks: legs box / tapered; knees spike / twin; feet claw / pad; pauldrons fin / shell; forearms hex / tapered. New slots:
    hand (fist / block / claw / ball, sized within the forearm so arm guns fire past) and waist (drum / ring / column).
    `data/token_dictionary.json` `shell_mapping.facet_blocks` lists every block and the tag that forces it.
  - Lineups of all 13 slots (tools/token_lineup.py): every block passes joined / ground / clip / clear-muzzle. Fixed on the way:
    the claw foot's hub sat below the ground; a ball or block hand blocked guns lying along the forearm.
  - The 47 chart chassis are NOT regenerated yet (Daniel: build the dictionary first).

- **2026-11-04 (Claude), session 18 - BAY HOUSINGS, ATTACHED SHOULDERS, PART LINEUP TOOL** (Daniel: "Doors on the atlas are
  overshadowed by the missile launchers clipping. Archers arms are also not attatched and the missiles are still clipping";
  "I will want to look at each set of parts as seperate pieces. Parts that have mounting brackets should indicate where those
  are."). REVIEW PENDING (higher-level model). Art only; the three art checks pass.
  - Missile bays get a HOUSING: a flat-fronted box set into the side torso's upper front, aimed forward and about 20 degrees up,
    its volume booked to the side torso; the racks sit flush in its face, each door hinged at its top edge and raised (`_bay`).
    The racks no longer poke out of curved or sloped torsos.
  - Shoulders: the side torso's outer face is found AT shoulder height (a round body narrows up top), the arm hangs clear of the
    torso's widest point below it (bay housings included), and the shoulder drum reaches in to the face, so the arm is held.
  - New `tools/token_lineup.py` (replaces token_heads.py): every block of a slot on one 'Mech, the slot's locations drawn alone,
    with the MOUNTING BRACKETS marked (green: joint sockets; orange: hardpoint rails, numbered) and the checks per block.
    The brackets come from `_record_brackets` (model["_brackets"]).

- **2026-11-04 (Claude), session 18 - HEAD BLOCK LIBRARY** (Daniel: "Start a pass of designing a group of heads blocks. Think we'll
  tackle one location at a time and build a library of interchangeable blocks."). REVIEW PENDING (higher-level model). Art only;
  the three art checks pass.
  - `INTEGRATION__shell_facet.head_block`: box, skull, dome, wedge, bubble, visor, turret, hood (`BLOCKS["head"]`, sizes
    `HEAD_SIZE`, mount depth `HEAD_DROP`); tags pick them (head_mount built_in -> hood; head_shape -> its block), else the name
    hash. `pick` honours `model["force_blocks"]` for lineups and tests.
  - New `tools/token_heads.py`: every block of a slot on one 'Mech, 3/4 front and rear close-ups, with the joined / ground / clip /
    clear-muzzle checks per block (all eight heads pass on the Atlas). Its renderer sorts all faces in one collection (thin glass
    plates vanished under the head otherwise).
  - Seen on the way, not changed: the Atlas's left side torso missile-bay door stands up in front of its head.

- **2026-11-04 (Claude), session 18 - CT DEPTH RATIO, ROUND TORSO, CLEAR MUZZLES** (Daniel: keep the centre torso within a ratio
  of the side torsos' depth "otherwise we could see a distinct cross shape from overhead"; "Archer needs a geometry pass. Could put
  negative space in front of weapons to prevent them from being blocked by clipping ... Solution might be the Round blocks used on
  the 'Old blocks' variant of the urbanmech"). REVIEW PENDING (higher-level model). Art only; the three art checks pass.
  - `torso_pieces`: the centre torso's depth is at most `CT_RATIO` (1.25) x the shallower side torso's; when the shoulder rule
    thins a side torso, the centre gets shallower and wider to keep its volume (`_torso_parts`, up to 4 rounds).
  - Torso block `round` (a faceted ovoid, the old blocks' UrbanMech body) replaces `dome`; tags torso dome / ovoid, profile dome,
    kit round_blocks pick it.
  - Negative space in front of every weapon: `_muzzle_blocked` tests the bore line 1.2 m ahead against the body's solids
    (`Sink.body`); a blocked weapon slides forward (up to 0.7 of its length), then tries the location's other rails; one still
    blocked is drawn and counted (`model["blocked_muzzles"]`, which tests/test_token_shell.py requires to be 0). All eight range
    chassis: 0.

- **2026-11-04 (Claude), session 18 - SHOULDERS OUT, WAIST AND PELVIS, FORWARD MISSILE BAYS** (Daniel: "shoulder joints should
  generally be farther out then the hip joints ... inflating the torso to push the arms back out will have the added benefit of
  reducing the 'Sandwich mounted sideways on legs' look"; "missiles tend to point towards enemy in battletech. Sometimes they're
  angled upwards"; "the ability to torso twist has been visually lost. we're using twin hip blocks, and are missing the Hips to
  waist actuator system"; and: run only the art checks for art work, Section 7). REVIEW PENDING (higher-level model). Art only;
  the three art checks pass.
  - `INTEGRATION__shell_facet`: `_hips` builds a pelvis block between the hips (two halves meeting at the centre line, sized by
    the hip actuators) with a hip joint drum at each side; `_waist` adds a vertical drum on the pelvis (the torso-twist
    actuator, part of the centre torso) that the torso stands on; bird body too.
  - Shoulder rule in `torso_pieces(min_outer)`: each side torso reaches far enough that the shoulder joint sits at least 1.22
    times the hip's outer edge out (tiny arms excepted), and thins its depth to keep its volume. Shoulder joints now 1.7 to 2.8
    times the hip joints' distance from the centre line.
  - `_bay`: racks in the side torso's upper front, aimed forward and about 20 degrees up, each under a door hinged at the top of
    its opening and swung up.

- **2026-11-04 (Claude), session 18 - LEG MYOMER FACTOR** (Daniel: "Give them a factor. This is where paying attention to the
  myomers would matter. Legs would tend to have more of them to support the entire mass of the mech."). REVIEW PENDING
  (higher-level model). Art only, 50 of 50 checks, reference logs identical.
  - `bulk_rule.leg_factor` 1.6 (data/token_densities.json): each leg's structure points count 1.6 times in the bulk share, as the
    head's count 1.5. Calibrated on the MWO Atlas kit (each leg with half the pelvis about 22 m3, each arm about 10: ours 19.4
    and 9.9). Volume below half height v the Syllogy (MWO) kits: Hunchback 36 v 35 percent, JagerMech 38 v 45, Archer 38 v 43,
    UrbanMech 33 v 49, Locust 25 v 43 (the Locust's long legs are a bird-body shape question, not a budget one).
  - The myomer layer shows it: six thicker bundles round each leg segment, four on the arms (`build_layers`).
  - Fixes the factor exposed: racks in a missile bay sit inside the side torso, so their volume goes back to the torso block
    (it was taken out twice); the gun housing never takes more than 45 percent of its side torso.

- **2026-11-04 (Claude), session 18 - BULK BY STRUCTURE POINTS, THREE-PART TORSO** (Daniel: "sometimes the torso feels like its
  just the center torso. The torso of any mech should have 3 parts that fit together. The relative bulk, before considering
  weapons and equipment also in that location should be based on the number of structural points in that location (Head counts
  at 1.5 its structure). This will probably require more depth"; test candidates JagerMech, Atlas, Hunchback). REVIEW PENDING
  (higher-level model). Art only, 50 of 50 checks, reference logs identical.
  - `INTEGRATION__shell_items.budgets`: rule `structure_points` (data/token_densities.json `bulk_rule`, head factor 1.5; rule
    `parts` keeps the old per-part budgets). The 'Mech's base volume is kept and shared by structure points; each location's
    parts keep their proportions (the hip still builds the pelvis). Atlas: side torsos 12.2 / 8.7 -> 19.0 / 15.5 m3, legs 21.4
    -> 14.6, head 4.9 -> 3.6. Applies to both looks.
  - `INTEGRATION__shell_facet.torso_pieces`: three blocks per torso (`TORSO_PARTS`), the centre forward, the sides set back, cut
    edges so the seams show, each fitted to its own budget; depth 0.36 of the height. The dome stays one solid cut in three.
  - Measured against the Syllogy (MWO) kits: JagerMech depth 0.73 (kit 0.73), width 0.54 (0.73); Hunchback depth 0.44 (0.54),
    width 0.50 (0.85). Legs now hold less of the volume than the kits' (JagerMech 30 percent below half height v the kit's 45):
    the structure-point rule gives the legs a smaller share than the actuator calibration did.

- **2026-11-04 (Claude), session 18 - FACETED BLOCKS: POSE, TORSO, HOUSING, MISSILE BAY, STRAIGHT GUN ARM** (Daniel, after the
  Syllogy kit comparison - Syllogy's models are MWO's: "Archer does not have launchers above the head. Those are the protective
  doors for the launchers in the torso in a raised position"; "Jagermech: the guns simply line up with the upper arm coming
  straight from the shoulder"; yes to pose, deeper torsos, a torso slot; "Hunchback only gets a bigger hump if it becomes a
  standard block. I'd prefer to minimize one off custom solutions."). REVIEW PENDING (higher-level model). Art only, 50 of 50.
  - New slots in `INTEGRATION__shell_facet.BLOCKS`: pose (stride / ready / crouch; legs per side via `pose_joints`, the upper body
    leans about the hip line, `lean_pts`), torso (v_chest / box / slab / wedge / dome: ONE solid 0.30 of the height deep, cut into
    the three locations by `clip_x` / `split_x` so each piece holds its budget), housing (the hump as a standard block, sized by
    the side torso's heaviest gun), missiles (face / bay: racks in the torso top under raised doors, `_bay`), arm (pod /
    straight). The bird body uses the pose slot too. The old per-section chest and the one-off hump are gone.
  - All eight range chassis within the volume band, 0 floating, nothing below ground, clip 0. Against the Syllogy (MWO) kits:
    depth up (JagerMech 0.69 v the kit's 0.73, Hunchback 0.37 v 0.54), poses now bent and leaning. Still narrower and less bulky
    than the medium / heavy kits (Hunchback width 0.52 v 0.85, bulk 0.067 v 0.107); since the kits are MWO's and the MWO Atlas /
    Timber Wolf matched our budgets, the remaining gap is either our volume budgets or our height curve against MWO's heights:
    Daniel's call.

- **2026-11-04 (Claude), session 18 - FACETED BLOCK LIBRARY** (Daniel: "Go ahead" on giving the humanoids their own identities).
  REVIEW PENDING (higher-level model). Art only, 50 of 50 checks.
  - `INTEGRATION__shell_facet.py`: `BLOCKS` per slot (leg prism / slab / pillar / greave; knee drum / cap / guard; foot heel_toe /
    wedge / three_toe; pauldron box / slant / drum / collar; forearm octagon / square / round), `TAG_PICKS` (tags that force a
    block), `pick` (tag, else a byte of the name hash per slot; recorded in `model["blocks"]`, shown in the viewer's info panel).
    The mapping is in `data/token_dictionary.json` `shell_mapping.facet_blocks`. `build_model` records `hash_only`.
  - All eight range chassis still within the volume band, 0 floating, nothing below ground, clip 0 (tests/test_token_shell.py).
  - Next: blocks for the torso (the UrbanMech's dome reads as a box from the front), heads and the bird body; then the 47 chart
    chassis (phase 2).

- **2026-11-04 (Claude), session 18 - FACETED LOOK ON THE WHOLE TEST RANGE** (Daniel: "what about extending this style to the
  other models?"; on the Atlas chest width: "similar, not perfect"). REVIEW PENDING (higher-level model). Art only, 50 of 50 checks.
  - `INTEGRATION__shell_facet.py` now builds all eight range chassis (`FACET_RANGE` = `SHELL_RANGE`). New tag-driven blocks in
    the humanoid body: chest profile from `profile` (dome, bell, prow, ... else the V-chest), `tall_slab` / slab torsos taller,
    a HUMP block for `hunch` / `stepped` on the side torso with the heaviest guns (its face rail takes the heaviest gun, rail
    `prefer="heavy"`), launcher POSTS for `kit` tall_launchers / launchers, GUN-POD forearms for any arm without a hand
    actuator (length by contents; `long_barrel` x1.2), head position by `head_mount` (top, built_in, front, notch), antennas,
    rounder arms for `round_blocks`, squat legs under a dome torso. The bird body: `narrow` torsos, antennas.
  - The ribs are clamped inside the side torsos (`build_layers`; the faceted Atlas had them running into the arms).
  - `tests/test_token_shell.py` now checks the faceted builds too (32 models: volume band, height, plate minimum, and the joined /
    ground / clip audit for the faceted ones). The viewer has a "Faceted (experiment)" variant on every range chassis.
  - Known: the humanoids still share one leg, foot and pauldron set (the block library would give them choices).

- **2026-11-04 (Claude), session 18 - FACETED LOOK: ATLAS, HARDPOINT RAILS** (Daniel: "Core shape is good, the length of those
  arms could easily be made a variable based on how much stuff is in them ... where all the hard point spots on that model would
  be located to deal with other configurations. And certainly go ahead with the Atlas."). REVIEW PENDING (higher-level model).
  Art only, 50 of 50 checks.
  - `INTEGRATION__shell_facet.py` restructured: a body per archetype (`body_bird` for the Mad Cat, new `body_humanoid` for the
    Atlas), each declaring its HARDPOINT RAILS (`FRail`: face, line or post; the same rail counts per location as the plated
    builder, so the shuffled `place_items` plan drives any loadout), one placement step (`mount_rails`): a face rail lays its guns
    out as a grid centred on the face, a line rail as a run centred along the part, a post rail puts every missile rack in one
    launcher on a post (a chassis with posts always uses them). Vents, nozzles and domes keep the plated builder's spots.
  - Mad Cat gun-pod length follows the arm's fullest rail (0.17 of the height + 0.4 m a slot, at most 0.40).
  - Atlas: straight legs on big knee drums, heel-and-toe feet, a V-shaped chest whose side torsos stand taller than the centre
    (the head's notch), a skull with two eye slots and a jaw, box pauldrons over the shoulders, forearms with fists, guns under
    the forearms. Every location within 10 percent of its budget (name hash within 10 of 0.90), 0 floating, nothing below
    ground, clip 0. Still narrower in the chest than the kit (convex sections at the budget's volume).
  - `build_layers`: torso myomer sized from each section's own box (it floated out of the Mad Cat's small side blocks).

- **2026-11-04 (Claude), session 18 - FACETED-LOOK EXPERIMENT, MAD CAT** (Daniel: "Lets experiment with the madcat. See if its
  worth pursuing", after a low-poly Mad Cat print). REVIEW PENDING (higher-level model). Art only, 50 of 50 checks.
  - New `INTEGRATION__shell_facet.py`, used only for the Mad Cat / Timber Wolf and only when `build_model(..., style="facet")`:
    one faceted solid per part (octagonal prisms with chamfered ends, drums across the knee, hock, hip, shoulder and elbow, a
    teardrop canopy torso with the cockpit nose as the Head location, side blocks, gun-pod forearms aimed forward, claw feet),
    launchers on posts over the side torsos, a forward-pitched body and wide stance. 35 body solids against about 140 in the
    plated builder. Shares the budgets, hardpoints, layers and rules height; every location within 10 percent of its budget, 0
    floating, nothing below ground, clip 0 (tagged and name-hash builds). Viewer: a "Faceted (experiment)" variant on the
    Timber Wolf, edges drawn by default.
  - Fix found on the way: Clan weapons whose canonical name keeps the tech prefix (`CLMG`) were classed "misc", not weapons
    (`shell_items._classify` now reads the family from the cleaned name).
  - Not covered by tests yet (the experiment is not in `tests/test_token_shell.py`); Daniel decides whether it replaces the plated look.

- **2026-11-04 (Claude), session 18 - SHELL BUILDER: KIT CALIBRATION, NO STEPPED PLATES** (Daniel sent the MWO Atlas and
  Timber Wolf kit models: "skinny legs that are almost all bone, with mini ziggurats built up on their faces ... looks like it was
  built in minecraft"). REVIEW PENDING (higher-level model). Art only, 50 of 50 checks, reference logs identical.
  - Measured both kits at scale (STL volumes): our torsos and arms matched, legs were half the kits', the pelvis a fifth. Cause:
    actuators had no mass in the budgets. Now `data/token_densities.json` `actuator_tons` (art mass per actuator, calibrated on
    the two kits; the hip's volume builds the pelvis). Atlas now 112 m3 v the kit's 112, Timber Wolf 90 v 80.
  - One plate per face (`n_layers` = 1); thick armor shows as a thicker plate. Legs deeper than wide (both kits), lower legs nearly
    as big as thighs, legs 0.52 / 0.53 of the height, feet a heel block with two toes, a pelvis block per hip, faceted box
    pauldrons in place of the domes, torso section widths balanced against their own budgets.
  - Daniel then sent a low-poly Mad Cat print that reads better than this: the next step is his call (see the reply that day).

- **2026-11-04 (Claude), session 18 - SKELETON-AND-SHELL BUILDER, PHASE 1 (TEST RANGE)** (spec:
  `INTEGRATION__COMBAT_LAB_SKELETON.md`). REVIEW PENDING (higher-level model). Art only: no engine code, every reference
  log identical, 50 of 50 checks. STOPPED for Daniel's verdict on the look before phase 2.
  - **Built:** `INTEGRATION__shell_items.py` (the data half: every crit line becomes an item with kind, slots, tons from
    `mechsim/equipment.json` with a flagged fallback, volume = tons / density; hardpoint capacity read from `unit["slots"]`;
    the name-hash shuffle onto rails; location volume budgets from items, structure, armor, engine, gyro, cockpit),
    `INTEGRATION__shell.py` (skeleton joints from the rules height, location envelopes sized from the budgets, bevelled armor
    plates of real thickness layered by armor ratio, joint covers that overlap so no gap shows, shoulder sockets, visible
    mounts: weapons on rails, heat-sink vents, jump-jet nozzles, sensor domes, real-scale missile tubes),
    `data/token_densities.json` (art densities with a reason each, slot length 0.4 m, 5 cm plate minimum),
    `tests/test_token_shell.py`, a clip measure in `tools/token_audit.py`, the dictionary mapping
    (`data/token_dictionary.json` `shell_mapping`: every tag term expressed, approximated or FLAGGED), a third "Old blocks"
    variant in the viewer.
  - **Layers (Daniel's follow-up, same day):** every part carries a layer (`shell.LAYER_OF`): armor (core, plates, covers),
    equipment (visible mounts plus the unseen engine, gyro, cockpit, ammo and other items drawn INSIDE the shell), myomer
    (spindle bundles round each bone and the torso) and skeleton (bones and ball joints). The viewer has a switch per layer,
    presets (all / armor / equipment / myomer / skeleton only) and an X-ray armor option; the default view (armor + equipment)
    is unchanged, so no internals are exposed. `unit_mesh` parts carry `ly`. Skeleton and myomer are placement geometry:
    their volume is not part of any location's budget (the spine, hip, shoulder and rib bars count to no location).
  - **Range (phase 1):** Atlas, Mad Cat / Timber Wolf, Locust, Hunchback, Archer, JagerMech, UrbanMech, and Wendigo (a
    torso-mounted cockpit, weapon and ammo in the head; name hash only). `tokens.build_model(..., shell=True)` routes them to the
    shell builder; every other unit still uses the old block builder `_build` until phase 2, which is why `_build` and
    `calibrate` are not yet deleted (the spec's "retire" lands with the last phase).
  - **Checks:** hardpoints over all 4,227 unit files (115,951 items placed once each, none over capacity, shuffle stable);
    location volume within a band of its budget (spec 25 percent; tuned to **30 percent**: the pelvis plates and clamped
    narrow side torsos need it); height on the rules curve (3 percent); no plate under 5 cm; 0 floating blocks, nothing below
    the ground, arm / torso and leg / leg clip 0 on 16 models. `test_token_volume.py` skips the old density law for shell models.
  - **2D from 3D:** for shell models the 2D tokens already project the very convex solids the mesh hulls, so they cannot
    disagree; the old 2D path stays for old-builder units until phase 2.
  - **Not done / for Daniel's eye:** the look. Known weak points (FLAGGED in the dictionary mapping): no Hunchback hump, no
    Archer tall launcher boxes, no Atlas notch, no Mad Cat wing bays, plates read stepped on steep limbs, physical weapons,
    martian / quad / tripod skeletons (phase 3). Weapon masses with no table value use the fallback list
    (`INTEGRATION__shell_items.FALLBACKS`: mostly ammo and heat sinks).

- **2026-11-04 (Claude), session 18 - COMBAT LAB 3D - REVIEW PASS (Daniel: "a higher tier pass at the combat lab 3d
  assets; see what problems you can find and fix").** REVIEW PENDING (higher-level model). Art only: no engine code, every
  reference log identical, 49 of 49 checks.
  - **Measured, not eyeballed:** new `tools/token_audit.py` builds every chart unit and measures the meshes the viewer
    shows: exact distances between the convex blocks (python-fcl), so a block that touches nothing joined to the body is
    FLOATING, named by the builder line that made it; parts below the ground; mirror symmetry. Before: 368 floating parts
    over the 48 reference-tag models, 351 more on the name-hash models (the look every untagged unit in the library gets).
    After: 0 and 0. New `tests/test_token_joined.py` (12 models that each had a different fault; it fails on the old code).
  - **Bugs found and fixed** (`INTEGRATION__tokens.py`): (1) clamped arm guns hung 2-3 cm clear of the forearm (166
    parts): each gun is now built on the forearm's axis and slid out until it seats on the forearm (or on the gun before
    it), with a clamp block; side-by-side guns touch instead of sitting 8 px apart whatever their size. (2) Wing-bay tube
    mouths (Mad Cat, Stalker) were laid on a vertical plane in front of the bay's slanted face (92 parts): they follow the
    face and start inside it. (3) Things on the back (fins, brackets, jump jets) used the centre torso's depth, but the side
    torsos are 0.96 deep. (4) A "stepped" panel set builds the centre torso 0.03 taller, but every lookup of the front face
    used the shorter height: chest vents, plates and guns stood off sloped chests (`pv`, and `side=True` for side-torso
    mounts). (5) Gauss rifles: `B3.prism` never applied the width fit to x / y, so every Gauss barrel stood off its mount.
    (6) Box / wedge / visor heads ignored their mount depth (`extrude` had no `cy`): every "front" or "boom" head was built
    at the torso centre, sunk in it, with its glass floating out front (the Locust's wedge head now stands out front, as
    tagged). (7) ARM PLACEMENT: the old formula scaled the whole torso half-width by the top taper, but each section
    tapers about its own centre: arms beside top-wide torsos (narrow, winged) hung in the air, beside top-narrow ones
    (ovoid) clipped in - likely the root of the JagerMech clipping. Now the side torso's real outer face, and a shoulder gap
    that grows with the arm's girth (a fixed 5.8 cm put every heavy upper arm inside the torso): arm-into-torso
    penetration 6 of 94 models (up to 3.5 cm) to 0. (8) Shoulders, heads, antennas, cockpit blisters, turrets, ECM / probe /
    C3, fins and shoulder-barrel cradles were placed at `ztop` even where the top leans or curves: they now sit on the real
    top (`top_at`, `sit`; ellipsoid surfaces for dome / canopy torsos). (9) Martian, quad and tripod legs ended 6 mm above
    the foot. (10) Smaller: chest bolts off wedge-plan faces, a hatchet spike and sword tip off their shafts, ear pods
    beside top-narrow torsos.
  - **Viewer (semi-realistic look):** sRGB output with a filmic (ACES) tone map (light paint schemes such as arctic no
    longer blow out to white), an image-based studio environment so metal reflects, a warm key / cool fill / rim light
    set, 2048 shadows, materials by class (satin painted plate, darker reflective frame and weapon metal, glass cockpit,
    matte panel lines), the black outline on every block off by default (an "Edges" button turns it back on: it made the
    models read as toys), and a `<meta charset>` (the badge showed "Â·").
  - **Visible changes:** arms move a little in or out on most units, the shoulders of leaning torsos are lower, heads on
    front / boom mounts move forward, arm guns sit against the forearm. Volume calibration still within 8 percent.
  - **Still open (not done here):** the skeleton-and-shell rebuild of torsos and limbs (still boxes) remains the biggest
    step toward "military hardware"; surfaces are flat-shaded convex hulls with no bevels or decals; the audit counts
    floating, not ugly overlaps between non-arm blocks.

- **2026-11-03 (Claude), session 17 - WEAPON-CHOICE LOOKUP TABLES (Daniel's design).** REVIEW PENDING
  (higher-level model). Daniel: "Choice should be: 'For that target, what is the base TN, and what is
  the range' After that it should just be a look up table to find the precomputed best mix of weapons
  for that situation. And that Cache is only refreshed if the mech takes battle damage that changes its
  options." Speed only: 47 of 47 checks, every reference log identical (also --round-trip), the 12 v 12
  log hash unchanged, benchmark 501 / 495.
  - `weapon_selection.FireTable`: per (distance, pre-TN, side) the candidates and the knapsack's levels;
    a query's movement heat only filters them (`knapsack_levels` + `best_within` - the same answer and
    tie-break as solving at that budget, `tests/test_fire_tables.py`). `select_weapons_to_fire` split into
    `heat_limits` / `fire_candidates` / `_finish_choice` (unchanged behaviour). Rust `knapsack_levels`
    in `fastcore` (default on, Daniel).
  - Shared across scorers: `shared_fire_table`, keyed by both units' `fire_state` (damage incl. every
    slot and bin, heat, prone / shutdown, TAG, Narc pods, stealth, TSEMP / IMP, sinks switched off) plus
    the weapons that can't fire, dissipation, other heat and the scorer's role (aimed / unaimed / future
    damage, AMS, water). Emptied every turn and on a saved-state load. `config.FIRE_TABLE_VERIFY` (test
    switch) recomputes every answer fresh and keeps the tables across turns - leaving the target's state
    out of the key fails it (tried); leaving the unit's own state out does not (the other parts changed
    with it in those battles) - kept in anyway.
  - Measured (12 v 12 Gladiator + Legate, 2 turns, CPU seconds, a noisy shared machine): weapon choice
    in movement scoring ~11.5 s (28%) -> ~9 s (24%); the battle ~41 -> ~39 s (~5%). Why not more: of
    565,648 scoring queries, 283,101 miss the scorers' own memos and need 152,829 different
    (distance, pre-TN, side) rows - the situations really are that many (range 1-30, pre-TN, 4 sides
    with structure weighting on, the arcs' weapon sets). Tried and dropped: solving each row at the
    largest budget up front (bigger knapsacks cost more); tables per scorer without sharing are SLOWER
    than before (13.5 s) - the sharing is what pays. `fire_state` costs ~84 us (1.4 s a 12 v 12 2-turn
    run): a cheaper signature is the next small win.
  - Lesson for the Rust port: the cost is in building ~150k candidate rows (planner, to-hit, tables per
    weapon), i.e. the per-weapon pricing - that is the loop to move as a whole, over flat per-weapon data.

- **2026-11-03 (Claude), session 17 - RUST TRIAL + WEAPON-KIND CACHES.** REVIEW PENDING (higher-level
  model). Daniel: "Move on to testing if rust will give us any extra speed" (long run: Rust or C; keep
  Python's modularity for now). Speed only: 46 of 46 checks, every reference log identical, benchmark
  501 / 495.
  - Profile, 12 v 12 Gladiator v Gladiator (Legate on), 4 turns under cProfile (~2x slower than real):
    Legate estimate 51%, movement 43% (two-ply 27%, reachable spots 8%); by function, the weapon choice
    `select_weapons_to_fire` 43% cumulative (618k calls; the bots dry-run what they would fire from each
    spot). Inside it the arithmetic is small; the time is plumbing: `canonical_name` 31M calls,
    `fire_modes.special` 1.3M calls (47 s cumulative), `get_weapons` rebuilt 351k times, the Planner.
  - Rust: `fastcore/` (PyO3 + maturin crate) with `best_subset`, the weapon choice's 0/1 knapsack, now
    pulled out of `select_weapons_to_fire` as `weapon_selection._best_subset_python` (the spec; ties and
    sum order copied exactly). Same answer on all 124,680 knapsacks of a 4 v 4 and on 20,000 random ones
    (`tests/test_fastcore.py`; skips when not built). Per call 0.85 us v 2.89 us (3.4x; most of the 0.85
    is turning Python lists into Rust ones). But the knapsack is 5.7% of a battle, so a 4 v 4 gained ~1%
    (inside the run-to-run noise). `config.USE_FASTCORE` (on; not built = Python).
  - Python: `fire_modes.special` / `has_profile` cached on the weapon (they depend only on its kind, as
    `canonical_name` already was): 4 v 4 3 turns ~22 -> ~20 s, 12 v 12 2 turns 45.5 -> 41.9 s (~8%),
    logs identical.
  - Lesson (Pick up here 13): Rust pays only for a big piece of work done in one call on flat data -
    a kernel this small saves less than its boundary costs matter. Next candidates, in order: more
    weapon-kind caching and per-turn flat weapon descriptors in Python (cheap, ~same results check),
    then the per-spot scoring (to-hit + weapon choice for plain weapons) in Rust over those descriptors.

- **2026-11-03 (Claude), session 17 - PYPY TRIED: NO GAIN (no code changed).** Daniel: "Test PyPy" (long
  run: Rust or C, keeping Python's modularity for now). PyPy 7.3.20 (Python 3.11) + numpy 2.4.6, in the
  scratchpad only. The dice are identical (same stream hash as CPython). Speed: the 10-turn benchmark
  8.0-8.4 s v 2.5-3.1 s under CPython 3.13 (same result, 501 / 495); the reference battles 51 s v 20 s;
  a 50-turn Asymptote mirror in one process, seconds per 10 turns PyPy 7.4 / 4.3 / 3.7 / 2.8 / 3.0 v
  CPython 2.5 / 3.3 / 2.8 / 2.3 / 3.0 - once warm it only ties. Its JIT log: 30% of the run compiling,
  255 loops + 733 bridges (very branchy code, few tight loops), 6 traces too long. Results: 12 of 15
  reference logs identical; 3 differ only in a printed rounding (7.375 -> "7.37" v "7.38": a last-bit
  float difference, same moves and scores). Verdict: not worth it. The lesson for the compiled path:
  the time is spread over branchy object code, so a port pays only where a loop is reshaped into
  flat-data work (Pick up here 13).

- **2026-11-03 (Claude), session 17 - SAVED STATES (end of turn).** REVIEW PENDING (higher-level
  model). Daniel: "load the board, units, their states and positions, and probably a count of how many
  rnd numbers have been used, and from there the engine will just continue"; a branch keeps the same
  dice by default, with a switch for fresh dice. Built:
  - `orchestrator`: `run_skirmish` split into `Battle` (units, board, dice, result, stats, turns done),
    `_start_battle`, `play_on` (turns from `battle.turn + 1`), `_play_turn` (the old turn body,
    unchanged) and `_finish`; `after_turn(battle)` hook (may hand back a reloaded copy to play on).
  - `INTEGRATION__saved_state.py`: `capture` / `restore`, `save` / `load`, `play_on_from`, a command
    line. Saves the battle (units with all their state, the board as it stands, the dice - the numpy
    generator's own state and the place in its block of rolls, not a roll count), the bots' memories
    (Princess's team heat maps / posture, Legate's plans and team-fire cache, severed limbs, stub
    counts) and every setting. Memories keyed by id(unit) are stored by unit name; caches are emptied
    on load and rebuild themselves. Found by the round-trip check: `destroyed_slot_info`'s
    `instance_id` is id(component), so a reload revived destroyed ECM / Artemis / ammo bins; the save
    keeps each named component beside its record and re-points it on load.
  - `config.SAVE_STATE_TURNS` / `SAVE_STATE_BATTLES` / `SAVE_STATE_DIR` / `SAVE_STATE_ROUND_TRIP`
    (test switch); `saved_states/` git-ignored.
  - Checks: `check_reference_logs.py --round-trip` (all 15 reference battles saved and reloaded after
    every turn: byte-identical); `tests/test_saved_state.py` (a 2 v 2 Gladiator + Legate v Princess
    team reloaded every turn, again with Legate's team-fire / herding / cohesion options on; a file
    played on; same dice repeat, fresh dice branch; settings restored; bad files refused). Leaving out
    Princess's memory or the component re-pointing makes them fail (tried); leaving out Legate's
    team-fire cache does not (it recomputes the same values - saved anyway).
  - Size / speed: a 12 v 12 save is 57 KB and takes under 10 ms to write or read.
  Engine results unchanged: 45 of 45 checks, every reference log identical, benchmark 501 / 495.

- **2026-11-03 (Claude), session 17 - RNG CLEAN-UP: ONE POOL OF DICE.** REVIEW PENDING (higher-level
  model). Daniel: "Do a clean up pass" (first step of the saved states). Every roll of a battle already
  came from its `BattleRNG`; the leftovers are gone: the orchestrator's `random.seed` (nothing drew from
  it since the tripod fix of 2026-10-21; its comment was stale), config's fallbacks to Python's `random` /
  numpy's global generator (now `config.active_rng()`: the battle's pool, or a private unseeded
  `BattleRNG` for rolls outside a battle), and Pathfinder's dead `resolve_combat_roll` /
  `_roll_weapon_damage` (their caller, combat_turn.py, was deleted long ago) with `BattleRNG.random()`.
  New `tests/test_rng.py`: real battles (a duel; a 2v2 with Gladiator + Legate + kill curve v Princess,
  tripods) with Python's `random` and numpy's global generator booby-trapped (shown to catch a planted
  draw). Speed-only change: 44 of 44 checks, every reference log identical, benchmark 501 / 495.

- **2026-11-03 (Claude), session 17 - ARCHER BV CONFIRMED.** Daniel pasted a BV breakdown for the
  Archer ARC-2R: 1,477 (defensive 786.6, offensive 689.92), the same as `INTEGRATION__battle_value`.
  The 2026-10-29 review's recalled 1,415 was wrong; review item (b) now holds only the Crusader
  CRD-3R. New check in `tests/test_battle_value.py`. No engine change.

- **2026-11-03 (Claude), session 16 (cont.) - FASTCORE GUARD FIX; REFERENCE TAGS FROM 3D STUDIES.** REVIEW PENDING
  (higher-level model). In a fresh checkout without the Rust wheel, `import fastcore` found the repo's own
  `fastcore/` crate folder and imported it as an empty package, so the "not built = Python" fallback never
  ran and every battle crashed (`AttributeError: ... knapsack_levels`; 37 of 47 checks failed). Both the guard
  in `INTEGRATION__weapon_selection.py` and `tests/test_fastcore.py` now treat a `fastcore` without the Rust
  functions as not built. Python path unchanged, results identical; 47 of 47 pass. Also: Combat Lab reference
  tags for eight chassis from whole-model / part-kit studies (`INTEGRATION__COMBAT_LAB.md` round 3).

- **2026-11-03 (Claude), session 16 (later) - FLAKY TEST NOTED.** REVIEW PENDING (higher-level model).
  `tests/test_hazards.py` `magma_heat_is_uncapped` failed in 2 of 4 consecutive `run_checks.py` runs on the same
  code (art-only commits, nothing in the engine changed) and passed the rest. Not diagnosed: the assertion
  compares `current_heat` with `15 + 5 + 10 - sinks + heat.engine_heat(m)`, so something in the heat or
  placement setup is not deterministic. Worth a look before anyone trusts a red or green on it.

- **2026-11-03 (Claude), session 16 - COMBAT LAB TOKENS v4 + BLOCK LIBRARY.** REVIEW PENDING
  (higher-level model). Tokens (output only, no engine change; `python tests/run_checks.py` 43 of 43):
  `plan` / `profile` / `hips` features (so top and side differ), armor thinning per location (thinner
  when under-armored, never thicker; Daniel 2026-11-01), the `read_unit` armor-parser fix (it never
  matched, so armor bulk had been constant), mounts for shoulder racks, then a block library from a
  study of a fan-made MWO Timber Wolf parts kit Daniel uploaded (files kept out of the repo, only
  descriptions and original shapes committed): chamfered boxes, `canopy` torso with wing bays, lozenge
  pod arm, knee disc covers, weapon sections by kind. Notes: `INTEGRATION__COMBAT_LAB.md`; vocabulary:
  `data/token_blocks.json`; sheet republished (claude.ai artifact CS8cdEG8rBR2jU5o3t1Y8a).

- **2026-10-31 (Claude) - DOCS: COMBAT LAB FRONT END = HTML; COMPILED PHYSICS CORE QUEUED.** REVIEW PENDING
  (higher-level model). Daniel chose the HTML front end (local `.exe` + browser, offline) and asked that
  condensing the physics core into a faster language go on next week's list, bots staying in Python
  (pick-up items 12-13). No code changed.

- **2026-10-30 (Claude), session 15 (cont.) - COMBAT LAB GUI WISH LIST FILED (docs only).** REVIEW PENDING
  (higher-level model). Daniel's notes (as summarized by GPT) split into
  `INTEGRATION__COMBAT_LAB.md`: Part A future ideas, Part B functional spec, each with Claude's notes
  (state snapshot is the foundation; tkinter v. HTML and `.blk` v. `.mtf` questions for Daniel).
  Pick-up item 12 added. No code changed.

- **2026-10-30 (Claude), session 15 (cont.) - COHESION REWARD BUILT (OFF): IT GROUPS THE FORCE BUT
  DOESN'T WIN BATTLES.** REVIEW PENDING (higher-level model). Daniel: "Reward staying within a range
  braket of its allies, stronger at short, much weaker at long. And how many allies are in mutual
  support range." `legate._Cohesion` (`config.LEGATE_COHESION`, off): per teammate (at its estimated /
  real end spot) a spot in its short / medium / long bracket earns `LEGATE_COHESION_REWARD` 2 / 1 /
  0.25 damage points, mutual support `LEGATE_COHESION_MUTUAL` 1 more, times `LEGATE_COHESION_SCALE`,
  taken off the damage taken. Refinements: `LEGATE_COHESION_MAX_ALLIES` (best N teammates count);
  `LEGATE_COHESION_THREATENED_ONLY` (a spot no enemy can reach needs no support - counts as fully
  supported; the first build gave it ZERO, which pulled units into the enemy's reach: 15 / 2 / 3, a
  bug, fixed); `LEGATE_COHESION_PAIRING` "either" (Daniel: "A fire support unit in the back will feel
  like its out of position because its not in cohesion with a short ranged back stabber up front. The
  back stabber however will feel fine since it has covering fire" - the pair is judged by whichever
  unit covers the other; support inside either support range). `baseline_battery.py --cohesion
  SCALE`. Battery, same 20 seeds, on the current default (Princess wins / draws / Gladiator wins;
  'Mechs left P / G; Gladiator units with no friend within 4 hexes, turns 11+): no cohesion 8 / 4 / 8
  (2.65 / 2.1; 45%); "ally" pairing x0.5 9 / 6 / 5 (3.65 / 2.15; 10%), x1 11 / 4 / 5 (4.2 / 1.5; 6%),
  x2 12 / 5 / 3 (3.65 / 1.4; 4%) - the force balls up; "either" + 3 allies + threatened only x0.5
  8 / 6 / 6 (2.8 / 1.95; 20%, Princess 21%), x1 13 / 4 / 3 (4.35 / 1.4; 16%). Best is "either" x0.5,
  level with no cohesion within 20 battles' noise; stronger is worse. Default stays off. Replay of an
  "ally" x0.5 battle published for Daniel. Reference logs unchanged; 43/43 checks.
- **2026-10-30 (Claude), session 15 - LEGATE DIAGNOSIS: DANIEL'S FIVE SUSPECTS MEASURED; THE
  FIRE SPLIT NOW COVERS THIS TURN TOO, AND IS THE DEFAULT.** REVIEW PENDING (higher-level model).
  Daniel's suspects: the IF/THEN estimate leads units astray; units model their move off the wrong
  unit; weights; a systemic error; poor cohesion - and "measure not just how wrong the prediction
  was, but to the degree it was wrong". New probe battery `tests/legate_probe.py` (report:
  `tests/legate_probe_report.py`; same results as the battery, so the probes don't perturb): it
  re-scores every Gladiator move at the end of the Movement Phase with the enemies at their TRUE end
  spots (the damage the estimate missed, and the regret of the pick), and with `--calib` checks the
  movement model's expected damage pair by pair with everyone at their real spots. Findings (20
  battles, baseline):
  (1) Estimate: off by 2.7 hexes a unit (within 2 hexes about half the time) - WORSE in hexes than
  "everyone stands still" (2.0), but closer in damage terms (4.5 points off a move v 5.4), and the
  pick it led to was within 2.5% of the best in hindsight (half the picks were the best). Swapping
  it for "stands still" (`--estimate hold`): 11 / 5 / 4 (3.9 / 1.3 left) - no better. Not the cause.
  (2) Wrong unit: the primary foe (the two-ply one) fired at the mover 45% of the time and is ~1/3
  of the predicted damage; small.
  (4) SYSTEMIC ERROR, FOUND: a move score counts every enemy that can reach the spot as shooting it
  THIS turn - 4.8 enemies a move, 1.1 really fired; predicted damage taken 2.3x the actual. The fire
  split (2026-10-29) shared only the FUTURE fire, so it made HP worth more while this turn's damage
  stayed ~4x too high: the stall. Fixed by `config.LEGATE_SPLIT_THIS_TURN` (`legate.now_share`: the
  same share on this turn's damage, in the move score and the estimate). Calibration (3 battles, raw
  points, the pairs that fired, everyone at their real spots): incoming fire is right (model 6.9 a
  Princess attack, actual 7.0); Gladiator's own is ~25% high (5.8 v 4.6; the fire phase's own dry
  run says 5.0) - a smaller bias, open (Section 0 Pick up here 0000).
  (3) Weights: not swept; (5) Cohesion, CONFIRMED: Gladiator units with no friend within 4 hexes,
  turns 1-3 / 4-10 / 11+: 19% / 26% / 47% (Princess 9% / 12% / 22%); alone AND ahead of their team
  21% late (Princess 9%). Herding at its placeholder weight barely moves it (42%).
  Battery, same 20 seeds (Princess wins / draws / Gladiator wins; 'Mechs left P / G): baseline
  8 / 8 / 4 (3.3 / 1.9); estimate replaced by "stands still" 11 / 5 / 4 (3.9 / 1.3); fire split with
  this turn too 8 / 4 / 8 (2.65 / 2.1) - the best yet; + herding 9 / 4 / 7 (3.1 / 2.25). DEFAULTS NOW
  `LEGATE_FIRE_SPLIT = "proportional"` and `LEGATE_SPLIT_THIS_TURN = True` (Daniel's rule: defaults
  match the best measured). Reference logs unchanged (duels; Legate needs 2+ enemies). 43/43 checks.
- **2026-10-29 (Claude), session 14 (cont.) - TEAM AWARENESS: FIRE SPLIT, HERDING,
  TEAM VALUE, EXCHANGE - BUILT AS OPTIONS, NONE BEATS THE BASELINE YET.** REVIEW
  PENDING (higher-level model). Daniel's designs (Pick up here 0000), all in
  `INTEGRATION__legate`, all off by default: `LEGATE_FIRE_SPLIT` (fire_share),
  `LEGATE_HERDING` (_Herd), `LEGATE_TEAM_VALUE` "sum" / "product" (_TeamFire: the
  enemy's fire this turn distributed over the team, greedy "most hurt, not
  already doomed"; the team's future damage with kill curves), and
  `LEGATE_TEAM_EXCHANGE` (our fire on the enemy by the same rule; the enemy's
  future damage removed counts too). Battery, same 20 seeds, Legate, target stub,
  big guns first (Princess wins / draws / Gladiator wins; 'Mechs left P / G):
  baseline 8 / 8 / 4 (3.3 / 1.9); fire split 4 / 16 / 0 (5.55 / 3.35 - stops the
  light dive, then both sides go passive); herding 8 / 8 / 4 (3.25 / 2.0 - half
  the battles end differently, the totals don't move); split + herding 1 / 19 / 0
  (5.3 / 3.25); + team value "sum" 12 / 4 / 4 (4.45 / 1.5); + "product" 17 / 3 / 0
  (5.75 / 0.45); + "sum" + exchange 18 / 1 / 1 (5.4 / 0.25). Reading (not yet
  checked in replays): each mover scores its spot with its teammates at their
  ESTIMATED spots and the enemy shooting whoever it hurts most, so it can count on
  a teammate to draw the fire (and, with the exchange, to finish its kills) - and
  every teammate reasons the same way at once: the force over-commits. Next:
  check that in replays; then let a mover count the teammates yet to move at
  their own best spots / their own risk (a coordination step), before tuning
  weights. Also fixed: the long-flaky check (`test_superheavy` superheavy_slots,
  live dice in an ammo blast's critical rolls, ~1 run in 20). Battery flags:
  `--fire-split`, `--herding`, `--team-value`, `--fire-order`.
- **2026-10-29 (Claude), session 14 - KILL CURVE, FIRE DIRECTOR, BIG GUNS FIRST;
  TWO CRASH FIXES; WHY GLADIATOR LOSES.** REVIEW PENDING (higher-level model).
  Summary for Daniel and the next session: `INTEGRATION__BOTS.md`.
  - `INTEGRATION__kill_curve` (Daniel: "a function that takes incoming damage and
    converts it into a % chance of mission kill ... rule of thumb ... 5 point
    clusters"): 100 trials of 5-point groups through `attack_resolution.
    _resolve_hit` on a pickled copy, own dice (config's roll functions swapped),
    cached per unit / side / damage state; ~0.05-0.1 s a curve. Mission kill:
    STUB_MISSION_KILL ("destroyed" default; "no_ranged_weapons"), after Daniel
    ruled out the book's Crippled ("that pilot should run") and noted spotting
    has no worth yet.
  - Fire director (STUB_GLADIATOR_TARGET "kill_curve", not the default): worth x
    (kill chance added on top of friends' declared fire + KILL_CURVE_PROGRESS_WEIGHT
    x useful damage / damage still needed). The softening term came from Daniel:
    "are units taking long shots to marginally increase a kill vs a hurt unit
    instead of applying stronger damage vs a unit that needs to be softened
    first?" - they were (a 1% gain beat a full volley 100 to 1).
  - Big guns first (GLADIATOR_FIRE_ORDER, default; Daniel's rule).
  - Speed only: `mech_state.mech_shields` remembers a 'Mech with no shield.
  - Crash fixes (both reproduced, tests added): a charger / pusher / DFA
    attacker advancing into its target's old hex goes through the domino code
    when a fall from above (p.116) put another 'Mech there (MegaMek's
    doEntityDisplacement; two enemies had ended up stacked); Princess's facing
    to a point in its own hex is MegaMek's Coords.direction, 5.
  - Battery, same 20 seeds, + Legate: stub 7 / 9 / 4 (Princess / draw /
    Gladiator); fire director with list-order firing 15 / 5 / 0; fire director +
    big guns first 9 / 8 / 3, 'Mechs left 4.3 / 1.3 (replays of all 20, run on
    the fixed code). Analysis (scratch scripts over the replays): Gladiator lost
    53 units in turns 1-6 v Princess's 29; 46 of the 53 were lights that dived
    ahead alone on turn 2. Cause: Legate's MultiLifetime divides HP by ALL
    enemies' damage a turn, so a unit's life looks ~3 turns long and bad trades
    score well (Pick up here 000 "how much fire a single unit would take").
    Also: no cohesion pull (heavies' nearest friend 6.4 hexes v Princess's 4.2
    on entry). Daniel's question "is it starting positions?": the first movers
    see ~2 enemies on turn 1 but end further back than Princess's, not worse.
  - Daniel's next topics are Pick up here 0000; ammo conservation is item 3.
- **2026-10-29 (Claude), session 14 - BATTERY RE-RUN WITH THE PRINCESS FIX; KILL-
  CURVE IDEA.** Daniel: "Rerun the 20 battle set with the corrected princess.
  Mostly for curiosity." Same 20 seeds, stub + Legate (both defaults), after the
  `max_damage_at_range` fix below: Princess 7 wins / 9 draws / Gladiator 4 wins
  (unchanged from before the fix); damage dealt Gladiator 1274 / Princess 1601
  a battle (was 1235 / 1543); 'Mechs left Princess 3.2 / Gladiator 1.8 (was
  3.65 / 2.10); 249 s a battle. Rows in `run_stats/baseline/pg_legate_princess_plan_
  seed12345_*`. Ammo conservation for Gladiator added to Pick up here 3.
  Daniel's next idea (discussion, nothing built): a 'Mech's "vulnerability" as
  the curve f(N) = P(destroyed after N more damage) from its current state, by
  damage grouping; target value = expected output / vulnerability; a hit's
  worth = how much it shortens the damage still needed. A scratch prototype
  (`_resolve_hit` in fixed-size groups, front table, no damage PSRs) gave an
  Atlas AS7-D an expected 170 / 254 / 223 damage to destroy in 1- / 5- / 20-point
  groups (1-point: 83% die of 6 pilot hits, p.117; 20-point: 33% head kills), and
  a Commando 45 / 51 / 38. From fresh (255 left, 5-point groups) 10 into the left
  arm was worth ~0, 10 into the centre torso 13, 10 into the head 116.

- **2026-10-29 (Claude), session 14 - AMMO RUNS OUT; PRINCESS'S QUICK ESTIMATE FIX.**
  Daniel: "did that emperor in battle 10 still have ammo by that point, and if it
  didnt, was it still acting like it did?" Battle 10 re-run (same seed) with
  every bin read at each end phase. Gladiator's Emperor fired its two Rotary
  AC/5s at `STUB_RATE_OF_FIRE = "max"` (6 shots each a turn): 120 rounds, 36 left
  at turn 10, dry by turn 20; from then on it fired its ER large lasers only, and
  its movement scoring knew (ranged_combat / future_damage drop empty weapons).
  Princess's Emperor still had 54-78 rounds (MegaMek's own fire control). And by
  turns 30-40 nearly every ammo weapon on the field was empty on both sides
  (every LRM 20 / 15, both Gauss Rifles, Ultra and LB-X ACs): the LRM carriers
  are left with medium lasers - another stall cause (they hang back at LRM range
  with nothing that reaches). BUG FIXED (MegaMek parity):
  `princess_fire.max_damage_at_range` (FireControl.getMaxDamageAtRange) counted
  weapons that are out of ammo, jammed or a spent one-shot; MegaMek skips them
  (`weapon.isCrippled()`). It feeds Princess's close-range pull (modern), the
  v0.50.07 estimate against an enemy yet to move, and the target-threat term of
  the firing-plan utility - so Princess planned with empty guns and read an
  enemy's empty guns as a threat. Now skipped; `close_range_incentive` memoizes
  it per ranking (45 us a call). No reference log changed (no Princess battle
  in them runs dry). OPEN, Daniel's (a research stub): Gladiator's
  rate-of-fire policy ("max" empties an Emperor in ~10 turns of fire).

- **2026-10-29 (Claude), session 14 - WHY 12 v 12 BATTLES STALL (diagnosis, no code).**
  Daniel: "Based on the game records can you get a feel for why the games are
  stalling out?" Four of the 9 cap draws of the stub + Legate run (battles 2, 9,
  10, 18) re-run with replays and read turn by turn. Three causes:
  (1) THE CAP IS TIGHT FOR 24 UNITS: battles 2 and 18 were mop-ups (Gladiator's
  last 1-2 'Mechs at 138-165 HP, 2-4 more turns at the late damage rate);
  battle 9 a slugfest still trading (~20 more turns). Decisive battles end at
  turns 16-49. (2) BOTH BOTS PARK: about half of all moves are Stand Still, in
  every stage of the battle, both bots; the nearest enemy sits ~10 hexes off
  and the late damage rate is 10-60 HP a turn a side against 1000-1800 HP left.
  Battle 10 is a standoff: Princess's Atlas and Emperor at full HP stood still
  all of turns 35-50 at 18-20 hexes, firing nothing worth it most turns;
  Gladiator's Emperor stood still 16 of 16 turns. Suspects: Princess modern's
  position-hold credit (and its DEFEND posture, which is not logged), and
  Gladiator's lifetime objective, which prices a long-range trade as good
  enough. (3) NOBODY HUNTS A STRAGGLER: battle 2, six Princess 'Mechs took 11
  turns over one Gladiator Cataphract; one Princess Awesome sat 22-24 hexes off
  with no line of sight for 11 of 12 turns. Analysis scripts were in the session
  scratchpad (per-turn and per-unit tables from replay JSON).

- **2026-10-29 (Claude), session 14 - LEGATE ON BY DEFAULT.** Daniel: "Legate on
  by default in multi unit games." `config.LEGATE = True` (it only acts with 2+
  enemies on the board, so duels and every reference log are unchanged);
  `baseline_battery.py` follows the config (`--no-legate` for the old Gladiator).

- **2026-10-29 (Claude), session 14 - GLADIATOR TARGET CHOICE STUB.** Daniel:
  "a good test to stub in until we teach gladiator how to focus fire and account
  for target saturation." `config.STUB_GLADIATOR_TARGET` (default
  "princess_plan", "nearest" = the old pick), `stubs.stub_gladiator_target`: a
  Gladiator unit with 2+ enemies on the board takes Princess's target choice
  (`princess_group.choose_target`, scored through Princess's fire control while
  `bots.princess_eyes` is on - so friends' declared damage counts and an enemy
  they are expected to kill scores low), then picks its own weapons as before;
  its declaration goes into the team's damage map (`bots.records_declared_damage`)
  for the teammates after it. Duels unchanged (all reference logs match).
  `baseline_battery.py --target`. Test: `test_princess_group.py`
  `gladiator_borrows_princess_target_choice_and_spreads_its_fire`.
  RESULT, Princess (Red) v Gladiator (Blue), 12 v 12, the same 20 seeds, no
  Legate (stub / the recorded "nearest" run): Princess won 14 / 14, draws 6 / 6,
  Gladiator 0 / 0, Gladiator wiped out in 14 / 14; turns 37.2 / 36.7; Princess
  'Mechs left 6.1 / 7.0, HP left 2156 / 2295; damage Gladiator dealt 898 / 772
  (+16%); damage Princess dealt 1691 / 1674; Gladiator 'Mechs left 0.70 / 0.75;
  133 / 143 s a battle. Reading: better targeting buys about two-thirds of
  Legate's damage gain (+24%) at no time cost, but wins nothing and Princess's
  damage to Gladiator is unchanged - Gladiator still takes about twice what it
  deals. Target choice is part of the gap, not most of it: the rest is where
  Gladiator stands (movement) and how much fire it soaks.
  STUB + LEGATE (Daniel: "Stub plus legate. Go."), same 20 seeds (stub+Legate /
  Legate alone, recorded 2026-10-28): Princess won 7 / 15, draws 9 / 5,
  GLADIATOR WON 4 / 0 (battles 1, 13, 15, 20 - its first wins in a 12 v 12);
  Gladiator wiped out in 7 / 15; turns 42.8 / 39.6; Princess 'Mechs left 3.65 /
  5.6, HP left 1776 / 2068; damage Gladiator dealt 1235 / 959 (+29%); damage
  Princess dealt 1543 / 1721; Gladiator 'Mechs left 2.10 / 0.35; 260 / 259 s a
  battle. Reading: the two together are far more than either alone (stub alone
  +16% damage, Legate alone +24%, both +60% over the plain bot, 772 -> 1235) -
  Legate's positioning puts several Gladiators in range of the same enemies,
  and the shared target choice turns that into kills. The damage ratio went
  from about 1 : 2.2 to 1 : 1.25. 9 cap draws now: the anti-stall item matters
  more.

- **2026-10-29 (Claude), session 14 - REVIEW OF SESSIONS 12-13 (Sonnet's work).**
  Daniel: "quickly review the work done by Sonnet models. If they're kosher we
  can clear their 'review this' flags." Read against the Core Rulebook and
  MegaMek's source (main 4f22bf6): (1) multi-unit battles - Unequal Numbers
  reproduces both p.41 tables (18 v 10, 14 v 5); the domino effect and the
  accidental fall from above follow pp.113-116, and the fall damage's
  "target's height" matches MegaMek's Core rules (a standing 'Mech 1, prone 0):
  OK. (2) Map picker: OK (minor: a pack map extracted to the temp folder is never
  refreshed if the pack changes). Map stitching: the seam-parity question is
  Daniel's (Section 0 REVIEW QUEUE (a)). (3) Movement cache: BUG FIXED - a magma
  crust that breaks becomes liquid (+1 MP, TO:AR p.30), but `_BoardCache` kept
  the crust's step cost for the rest of the battle; `test_hazards.py`'s cache
  check only passed because it read the stale 1 MP entry. Now
  `INTEGRATION__hazards` drops the board's cache (`pathfinder.forget_board`)
  when a crust breaks or is mended, and the check breaks a crust for real and
  wants the 2 MP entry (it fails on the old code). No reference log changed.
  (4) Princess group: mutual support, the ally centre and the posture's closing
  test and hysteresis match MegaMek's Java. Battle Value: REVIEW QUEUE (b).
  (5) Legate: the cascade / lock rules do what the docstring says; minor: in
  `Extras.adjust` a spot where another enemy is estimated to stand skips that
  enemy (a slight pull toward its hex - harmless while it is only an estimate).
  42 of 42 checks pass.

- **2026-10-28 (Claude), session 13 - LEGATE (first version).** **REVIEWED 2026-10-29 (higher-level model; see the review entry).** Daniel: "making gladiator less myopic ... a multi-unit
  bot layer at the start of the movement phase ... I call this layer Legate; it's
  in charge of keeping tabs on the battlefield", then his answers: the IF/THEN
  runs 12 rounds; ties in a round go by picker score and can cascade; a unit
  locks only when its own choices loop; the score is Gladiator's picker score
  with damage taken the sum over all enemies and damage dealt the max; the foe
  is the most threatening enemy yet to move; fire at the weapons phase goes to
  the enemy it can hurt most once positions are final. New `INTEGRATION__legate`
  (design in its docstring and the Section 6 row), `config.LEGATE` (OFF by
  default) / `LEGATE_ITERATIONS` 12, `bots.choose_foe`, `Extras` hook in
  `movement_selection._choose_normal` / `_static_scores`, `legate.plan_turn` /
  `end_phase` / `reset` in the orchestrator, `tests/test_legate.py` (12 checks),
  `baseline_battery.py --legate`. With it off, or in a duel, nothing changes: 42
  of 42 checks pass, reference logs untouched. Fire choice needed no change
  (`forces.choose_target` already picks among all enemies once positions are
  final). RESULTS (12 v 12 battery, seed 12345, 1 core each, 3 battles, Legate on
  for every Gladiator): Gladiator v Gladiator: Draw (cap), Draw (cap), Red; 50/50/44
  turns; 241/292/206 s (4.7-5.8 s a turn, was 2.2-2.9: about 2x; the estimate is
  ~45% of it). Princess (Red) v Gladiator: Princess won 2 and drew 1 (was 3
  wins); Gladiator had 0/3/0 'Mechs left (was 0/0/0); 34/50/39 turns; 233/289/276
  s (was 123-152). Three battles say little about strength; Legate costs about 2x
  at this size. To do (Pick up here 000): map reading, concentrated-fire estimate,
  speed, on-by-default decision.
  20-BATTLE RUN (Daniel: "a battery of 20 tests"), Princess (Red) v Legate
  Gladiator (Blue), seed 12345, 4 cores x 5 battles, about 25 minutes: Red
  (Princess) won 15, 5 draws at the 50-turn cap, Gladiator won none; Gladiator
  was wiped out in 15 of them and kept 1-3 'Mechs in the draws; 23-50 turns;
  168-351 s a battle. (The earlier 3-battle no-Legate Princess v Gladiator run
  was 3 Princess wins; a matching 20-battle no-Legate run was not made.)
  `baseline_battery.py` gained `--first/--last` (split over cores) and `--replay`.
  MATCHING 20 WITHOUT LEGATE (same seeds): Princess won 14, 6 draws, Gladiator
  none; Gladiator wiped out in 14. Averages over 20 (Legate / no Legate):
  turns 39.6 / 36.7; Princess 'Mechs left 5.6 / 7.0; Princess HP left 2068 /
  2295; damage Princess dealt 1721 / 1674; damage Gladiator dealt 959 / 772
  (+24%); Gladiator 'Mechs left 0.35 / 0.75; seconds a battle 259 / 143 (1.8x).
  Reading: Legate makes Gladiator hurt Princess more (about 10% more of
  Princess's HP lost, 1.4 more 'Mechs lost, 24% more damage dealt) but not win
  more: no Gladiator wins either way, and the draws are stragglers at the cap
  (5 v 6), the anti-stall item. Princess still wins every decisive battle.

- **2026-10-28 (Claude), session 13 - BASELINE TEST BATTERY.** **REVIEWED 2026-10-29 (higher-level model; see the review entry).** Daniel: "4 maps stitched together, 12 mechs vs 12
  mechs, mixed but mirrored (3 assault, 3 heavy, 3 medium, 3 light); Princess vs
  Princess, Princess vs Gladiator, Gladiator vs Gladiator. Mostly seeing if it
  works and how long it takes. Results will be recorded as a yard stick." Then,
  after the first try (2 x 2 boards, 404 s, 50 turns, a draw): "drop down to a
  2x1 map size." `tests/baseline_battery.py pp|pg|gg N` (field: Grassland 1 +
  Desert Hills stitched 2 x 1, 33 x 17; each side Atlas AS7-K, Emperor EMP-6D,
  Awesome AWS-8Q, Archer ARC-2R, Cataphract CTF-3D, Catapult CPLT-C1, Kintaro
  KTO-19, Griffin GRF-1N, Hunchback HBK-4G, Jenner JR7-D, Commando COM-2D, Locust
  LCT-1V; gunnery 4 / piloting 5; 50-turn cap; seed 12345, battle n uses
  battle_seed). YARDSTICK, each battle on ONE core (the three batteries ran at
  once on a 4-core box - Daniel: that is the 1-core baseline and keeps the
  yardstick the same size every time), code at the group-behaviors merge (PR #98):
  | setup | results (3 battles) | turns | seconds a battle (a turn) |
  |---|---|---|---|
  | Gladiator v Gladiator | Red, draw (cap), Red | 44 / 50 / 30 | 96 / 143 / 75 (2.2-2.9) |
  | Princess (Red) v Gladiator | Red x3 (Gladiator 0 left each time) | 24 / 45 / 34 | 123 / 152 / 147 (3.4-5.1) |
  | Princess v Princess | Blue, draw (cap), Blue | 35 / 50 / 27 | 243 / 417 / 257 (6.9-9.5) |
  The 2 x 2 first try (Princess v Princess, 1 battle): draw at the cap, 404 s
  (8.1 s a turn). FINDING: a Princess battle costs 2-3x a Gladiator one at 12 v
  12 (movement is 98% of the time; "Princess path ranking" ~110 s of 243 s) -
  the multi-enemy movement (every enemy evaluated per move) outweighs Gladiator's
  one-foe two-ply search; a speed pass on it is the obvious next step. 3 battles
  a setup is a yardstick, not statistics.

- **2026-10-28 (Claude), session 13 - PRINCESS FOR TEAMS + BATTLE VALUE.**
  **REVIEWED 2026-10-29 (higher-level model; see the review entry).** Daniel: "I think 1-5 are do able. 6
  requires us to calculate BV ... As usual use Megamek as source material where
  needed." Source: MegaMek main 7205e4d (a newer commit than the fd2edfb the
  modern clone was made from; the group code is the same in v0.50.07 where it
  exists - `BasicPathRanker`, `PathRanker`, `HeatMap`, `FireControl`,
  `PostureResolver`, `Coords.median`). Built: (1) `princess_fire`: the damage
  map and the overkill term (a team stops piling on an enemy it expects to
  kill); (2) `attack_resolution.declare_attacks(dry=True)` + `config.quiet()` -
  a dry run of the real weapon choice for each enemy, so Princess's target is
  the best firing plan (`princess_group.choose_target`, `bots.choose_target`);
  `run_ranged_phase` picks each unit's target when its turn comes (Gladiator's
  pick is pure, so nothing changes for it); (3) `princess_group.Group` and
  `princess_memory`: movement against every enemy, the closest enemy by
  adjusted distance, the median of the 4 closest to face, the force's posture,
  mutual support with the BV-weighted heat map, anti-crowding (default off);
  wired for both Princess versions; the orchestrator credits moves
  (`princess_memory.unit_moved`), fades the map each turn (`end_of_turn`) and
  resets it with the battle; (4) `INTEGRATION__battle_value` (BV 2.0) with
  `tools/build_equipment_bv.py` reading MegaMek's equipment classes into
  `mechsim/equipment_bv.json` (640 of the 699 items; every weapon and ammo bin
  of all 4,204 playable units in the pack is priced); `mtf_parser` now keeps
  `structure_desc` and `tech_base`. Checked: BV exact on the four published values
  and 1 off a fifth (Mad Cat Prime 2,737 vs the TRO's 2,738); a Warhammer
  1,299, Griffin 1,272, Shadow Hawk 1,064 and Awesome 1,605 land on the
  readouts too. `tests/test_princess_group.py` (17) and `tests/test_battle_value.py`
  (7). A duel with `PRINCESS_GROUP` off is hash-identical to before, both
  versions; the reference logs (no Princess) are unchanged. Duel A/B (20
  battles, Kontio v Hammerhead, `ab_batches.py --set princess-group`): Princess
  vs Gladiator, group off Red 7 / Blue 10 / Draw 3 -> on 5 / 13 / 2; Princess vs
  Princess 12 / 7 / 1 both ways. Left out on purpose: secondary targets (MegaMek's
  ordinary Princess fires at one target), the highest-BV cluster anchor
  (artillery / TAG standoff only), formations (CASPAR's ranker). OPEN FOR THE
  REVIEWER: the 7205e4d Java was read, not run (building MegaMek was not
  allowed here), so BV was checked against published values rather than against
  MegaMek's own output.

- **2026-10-28 (Claude), session 12 - MAP PICKER.** **REVIEWED 2026-10-29 (higher-level model; see the review entry).** Daniel: "Wire in the map picker. Will need it for the
  next trick, making the program easily accessible by a person, which is GUI
  work." `INTEGRATION__map_picker` in two layers so the GUI can reuse the
  first: the library (`list_maps` - the loose boards in data/ plus the
  356-board `maps.zip` pack, by name, pack folder and size; `resolve_board`;
  `playable` - what `prepare_board` refuses, e.g. bridges; `compatible_maps` -
  the stitch size rule per grid slot; `MapChoice` / `apply_choice` /
  `remember_choice`) and the console menu `choose_map(ask, say)` (last time's
  pick offered first; one board or a columns x rows grid up to 12; numbered
  list with a text filter; an unplayable map is refused with the reason).
  `config.PROMPT_FOR_MAP = True` makes `orchestrator._load_map` ask once per
  run and write the answer into config; with no keyboard it keeps the
  configured map. Config may now name a pack map directly
  ("AGoAC Maps/16x17 Desert 2.board") - `_load_map` resolves every name
  through the picker. Tests: `tests/test_map_picker.py` (8 checks, scripted
  answers). 39 of 39 checks pass, reference logs unchanged. GUI notes: call
  `list_maps()` for the list, `playable()` on demand (about 0.1 s a map, so not
  for all 356 at once), `compatible_maps()` per slot, `apply_choice()` to set.
- **2026-10-28 (Claude), session 12 - MAP STITCHING + OFFICIAL NAME.**
  **REVIEWED 2026-10-29 (higher-level model; see the review entry).** Daniel: "Short Grid is the official
  name now. Map stitching up and running." The name is recorded (the
  "placeholder" notes are gone). `config.STITCH_MAPS` works: `STITCH_BOARDS`
  (board files, row-major), `STITCH_GRID_COLS` x `STITCH_GRID_ROWS`;
  `orchestrator._load_map` calls the existing `board_parser.stitch_boards`
  (blank hex row / column at each seam, Daniel 2026-07-20; same-size rule), then
  `prepare_board` as for one board; a list that doesn't fill the grid is
  refused. Home edges, deployment, LOS, the movement cache and the replay
  viewer need nothing special (a 6v6 on two stitched 16x17 maps, 33x17, ran 14
  turns and replayed without console errors). Test:
  `test_terrain.stitched_map_loads_and_crosses_the_seam`. Not built: a map
  picker (built the same day, next entry); Section 6 gap: on a stitched board the home
  edges are the outer edges of the whole field, so long fields mean long
  approach marches. 38 of 38 checks pass, reference logs unchanged.
- **2026-10-28 (Claude), session 12 - MOVEMENT TABLE CACHE (speed only).**
  **REVIEWED 2026-10-29 (higher-level model; see the review entry).**
  Daniel's idea: compute only the hexes inside a unit's movement footprint
  and share them between units and turns. `pathfinder._BoardCache` (one per
  loaded board, filled on demand): hex info by (x, y); step cost, terrain
  PSRs and hazard per (from, to, backward, level limit incl. superheavy);
  facing-change PSRs; and finished movement tables keyed by (start, facing,
  MP, backward MP, level limit, blocked hexes within reach). Callers must treat
  a returned table as read-only. A loaded map must not be edited in place
  (test_pathfinder test 9 now edits a copy). A/B against the previous code,
  same seed, battle logs byte-identical: 4v4 grass 18.6 -> 13.9 s, 4v4
  scattered woods 16.0 -> 15.2, 4v4 hazardous badlands 8.9 -> 8.0, 12v12 grass
  (2 turns) 26.5 -> 12.5; 1v1 benchmark 2.6 s both (HP 501 / 495). Gains
  are biggest on the entry turn and big forces; battles that end early or on
  PSR boards gain little. 38 of 38 checks pass, reference logs unchanged.
  Caught in review before it shipped further: magma crust breaks mid-battle,
  so hazards are read live and a board with a hazard feature shares no
  finished tables (`_BoardCache.hazardous`; test
  `movement_cache_sees_a_broken_crust`, which fails without it). Smoke also
  lives on hex infos but nothing the search reads.
- **2026-10-28 (Claude), session 12 - MULTI-UNIT BATTLES.**
  **REVIEWED 2026-10-29 (higher-level model; see the review entry).** Daniel: units on
  teams, a lance / company against like forces, a free for all, a 3-way battle
  - "unleash a group of bots to operate independently". The two-'Mech battle
  is the same code with two units: every battle in the 15 reference logs
  plays out identically (benchmark HP 501 / 495); the logs were regenerated
  (`--update`) only because the results banner no longer lists "domino effects
  (no third mech)" as missing - 30 banner lines, nothing else. Built:
  - `config.FORCES` (list of `{team, mtf, count, name, gunnery, ...}`; None =
    Red vs Blue as before), `config.load_roster`, `FORCE_DEFAULTS`,
    `FOE_CHOICE`, `DOMINO_DODGE`. Labels: a team's only unit is called by the
    team ("Red"), else "Red 1", "Red 2"; a free for all = one team per unit.
  - `INTEGRATION__forces`: teams / enemies / stacking sets; `initiative_order`
    (any number of sides, ties re-roll among the tied); `activation_sequence`
    = Core p.41 Unequal Numbers (reproduces the book's 18 v 10 and 14 v 5
    tables - `tests/test_multi_unit.py`) generalized to 3+ sides like MegaMek's
    `TurnOrdered`; `move_index` (Princess's, for both bots); `choose_foe`,
    `choose_target` (Section 6 rows).
  - `orchestrator.run_skirmish` (and `run_battle` as its two-'Mech form):
    per-unit movement against the unit's foe with every mobile enemy's hex
    closed (`mover.blocked_hex` is now a set; `pathfinder._blocked_set`) and
    no ending in any other unit's hex (`reduced_options` takes a set; both
    Princess rankers too), TAG / ranged / physical phases over the whole force
    (`tag.designation_units`, `attack_resolution.run_ranged_phase`,
    `physical.run_physical_units`; the two-'Mech functions wrap them), AMS
    engagements shared by every attacker on a target (p.206, `_ams_used`),
    home edges for any number of teams, the battle ends when one team or none
    is left (p.41: last 'Mechs destroyed together = draw).
  - `INTEGRATION__domino`: a charge, push or DFA displacing a 'Mech into an
    occupied hex - domino effect (PSR, forced on a hex, fall on a failure,
    chains, destroyed with nowhere to go) and the accidental fall from above
    (TN 7 attack, damage, random neighbour) per pp.113-116; the old "domino
    effects (no third mech)" gap is closed. Not modeled: a submerged target's
    halved damage.
  - Results: `BattleResult.teams` / `.units`, `summarize_teams`; `.red` /
    `.blue` keep working for the teams of those names. Replay: any number of
    units and teams (colour per team, numbered markers, record sheets fold up
    past four units, click a marker for its sheet).
  - Not built (loud, Pick up here 00): any group behavior (mutual support,
    fire distribution, secondary targets p.64, a threat picture), Gladiator's movement
    scoring seeing more than one enemy. Timing: a 4v4 Kontio / Hammerhead
    battle ~40 s for 13 turns, ~0.5 s a unit a turn, the entry turn the
    slowest (`DEPLOYMENT_DEPTH` > 0 multiplies the entry search).
  Tests: `tests/test_multi_unit.py` (20 checks).
- **2026-10-28 (Claude):** Full pick-quality battery for the latest IF/THEN
  (hold still first + neighbour climb), against the recorded 2026-10-27/28
  runs: 8 scenarios x 20 battles, same seeds (Short Grid reproduced its
  recorded numbers exactly). `tests/pick_quality.py --perfect-cache FILE`
  (Daniel: "since Perfect is slow to generate, but once generated..."):
  Perfect's prices are saved per decision and reused while the battle
  follows the recorded path - scenarios 1-6 ran ~2x faster from the cache
  (`run_stats/`, git-ignored, lost with the session). FIRST MOVER (2,716
  decisions; % of range / got best / rank pct / hexes off / closer / ms):
    Perfect               100.0 / 100% / 100% / 0.00 / +0.00 / 1269
    Short Grid             96.1 /  49% /  95% / 2.47 / -0.11 /  196
    IF/THEN + climb        93.7 /  36% /  92% / 3.25 / +0.88 /  177
    IF/THEN 12 + climb     94.5 /  39% /  93% / 3.21 / +0.87 /  198
    (recorded) Short-Short 91.0 /  26% /  88% / 3.39 / +0.87 /   93
    (recorded) IF/THEN first version 85.1 / 18% / 73% / 3.94 / +1.98 / 102
    (recorded) Princess modern 75.7 / 9% / 61% / 4.31 / +2.82 / 45
  Per scenario, IF/THEN 12 + climb 91.2-95.7% (Short Grid 92.9-98.5); it
  beats Short Grid only on Atlas vs Archer (95.2 vs 94.2). Holds still on 20%
  of first-mover picks (Short Grid 18%, Perfect 11%). Moving second it is
  Perfect (every spot). One 'Mech against one, it costs about Short Grid's
  time - its saving is meant for multi-unit play (Section 5).
- **2026-10-28 (Claude):** IF/THEN neighbour climb (Daniel: "I like option
  2"), `config.MOVEMENT_IF_THEN_NEIGHBOUR_CLIMB` (on): after the back and
  forth, from the best attempt's hex score every state of that hex and its 6
  neighbours by the two-ply score, move to the best neighbour while it
  beats the current hex (`movement_selection._neighbour_climb`); test
  `if_then_neighbour_climb_ends_on_a_local_best`. `tests/pick_quality.py
  --pickers` (only the named pickers; Perfect always runs). Quick read
  (Daniel: "general feel, not full stats"): Catapult vs Jenner and Kontio vs
  Hammerhead, 8 battles each, FIRST MOVER (% of range / got best / rank pct /
  hexes off / closer / ms - ms run beside the test suite, so high):
    Perfect             100.0 / 100% / 100% / 0.00 / +0.00 / 2678
    Short Grid           97.3 /  45% /  96% / 3.16 / -0.45 /  321
    IF/THEN 12 steps     88.5 /  18% /  76% / 4.32 / +1.84 /  222
    IF/THEN + climb      93.3 /  29% /  89% / 4.29 / +1.59 /  293
    IF/THEN 12 + climb   94.5 /  34% /  91% / 4.20 / +1.48 /  325
  The climb is worth ~5-6 points of range for ~100 ms; the lean in shrinks
  but stays (+1.5 hexes).
- **2026-10-28 (Claude):** IF/THEN fixed steps, `config.MOVEMENT_IF_THEN_STEPS`
  (Daniel: "run like 10 to 15 steps, with an early stop if it lands on the
  same hex again. Then pick the best"): 0 = the climb (default), N = up to N
  attempts whatever they score, early stop on a hex already tried, the
  best-scoring attempt is the pick. Pick-quality picker "IF/THEN 12 steps";
  test `if_then_fixed_steps_keep_the_best`. Two worst scenarios, 20 battles
  each, same seeds, FIRST MOVER (% of range / got best / rank pct / hexes off
  / closer / holds still / ms):
    Perfect           100.0 / 100% / 100% / 0.00 / +0.00 /  8% / 2309
    Short Grid         97.1 /  42% /  96% / 3.19 / -0.40 / 12% /  281
    Short-Short        91.9 /  20% /  88% / 4.14 / +1.12 / 21% /  139
    IF/THEN (climb)    84.0 /  14% /  67% / 4.43 / +2.17 / 34% /  150
    IF/THEN 12 steps   88.9 /  19% /  78% / 4.36 / +1.87 / 29% /  198
  Catapult vs Jenner 86.6 -> 91.2, Kontio vs Hammerhead 80.2 -> 85.6.
  Traced (12 battles, 198 picks): it lands on a hex already tried after
  ~4-5 attempts (12 attempts in 4% of picks); the best attempt is #1 in 31%,
  #2 28%, #3 15%, #4+ 26%.
- **2026-10-28 (Claude):** IF/THEN's first attempt is now holding still
  (Daniel: "Its first step is 'If I hold still then...'" - to remove the lean
  from a high score against a stationary target, and to lock in quickly when
  holding still is best); without a Stand Still state (standing up, entering)
  it starts from the best spot against the enemy where it stands, as before.
  Rerun of the two worst scenarios (20 battles each, same seeds), FIRST MOVER,
  old -> new (% of range / got best / hexes off Perfect / closer / ms):
    Catapult vs Jenner   82.6 -> 86.6 / 18 -> 20% / 3.94 -> 3.64 / +2.29 -> +1.66 / 137 -> 147
    Kontio vs Hammerhead 80.0 -> 80.2 /  6 ->  5% / 6.59 -> 5.57 / +4.67 -> +2.92 / 150 -> 149
    both                 81.5 -> 84.0 / 13 -> 14% / 5.02 -> 4.43 / +3.26 -> +2.17
  (Short Grid 97.1 / 42% / 3.19 / -0.40 / 277 ms on the same picks.) The lean
  in shrinks by a third but a new lean appears: it holds still on 34% of
  first-mover picks (old 14%, Perfect 8%, Short Grid 12%). Traced (12
  battles, 192 picks): hold still kept 44%, 2 attempts 39%, 3+ 17%; stops on a
  lower score 168, repeat / no answer 24. The answer step still assumes the
  enemy stands frozen at its reply, so the answer's honest score usually comes
  in lower than the attempt before and the climb stops there.
- **2026-10-28 (Claude):** Daniel's IF/THEN first-mover picker ("IF I don't
  move, where will the enemy end up ... If the Second mover would move there,
  where should I go ... until the first mover generates a lower score than its
  previous attempt ... or until it picks the same location twice").
  `config.MOVEMENT_SEARCH` / `MECH_*_CONFIG["search"]` = "if_then" - an
  option, the default is unchanged (all reference logs identical).
  `movement_selection._if_then_search`: attempt 1 = the best spot (every
  reachable spot) against the enemy where it stands (Daniel: "Project its
  own move vs the 2nd movers static position first"); each attempt is scored
  by its modeled reply (`MOVEMENT_ASSUMED_ENEMY_SEARCH`, short list by
  default), the next attempt is the best spot against that reply; stops when
  an attempt doesn't score higher (keeps the one before), repeats a spot, or
  has no reply. Daniel declined hedging against several replies and extra
  seeds ("measure the best it can do"). A second mover with "if_then" scores
  every spot (it already knows where the enemy stands). Also
  `tests/pick_quality.py` pickers "IF/THEN" and "IF/THEN perfect" (exhaustive
  reply model), `tests/ab_batches.py --set if-then`, test
  `if_then_climbs_by_its_rule`. Pick quality, same 8 scenarios x 20 battles
  and seeds as 2026-10-27 (the old pickers' numbers reproduce exactly), FIRST
  MOVER (2,716 decisions; % of range / got best / rank pct / hexes off /
  closer / ms):
    Perfect          100.0 / 100% / 100% / 0.00 / +0.00 / 1218 ms
    Short Grid        96.1 /  49% /  95% / 2.47 / -0.11 /  174 ms
    Short-Short       91.0 /  26% /  88% / 3.39 / +0.87 /   93 ms
    IF/THEN           85.1 /  18% /  73% / 3.94 / +1.98 /  102 ms
    IF/THEN perfect   84.6 /  17% /  73% / 3.95 / +2.12 /  128 ms
    Princess modern   75.7 /   9% /  61% / 4.31 / +2.82 /   45 ms
  Moving second IF/THEN = Perfect (every spot). Per scenario (first mover):
  best on Atlas vs Archer (95.6-97.0% of range, beats Short Grid), worst on
  Catapult vs Jenner (88%) and Kontio vs Hammerhead (90%, +1.8 to +2.9 hexes
  closer). Why (24 battles traced, 397 first-mover picks): the climb is
  short - 1 attempt kept in 52%, 2 in 32%, 3+ in 12%; it stopped on a lower
  score 303 times, a repeated spot 90, no reply 4. The best spot against a
  fixed enemy hex is usually close in (the enemy "holds still"), and the
  honest score of the next answer is usually lower, so it mostly keeps the
  static best's answer - a lean in. A perfect reply model doesn't help.
- **2026-10-28 (Claude):** Ultralight and superheavy 'Mechs (Daniel: "Go
  borrow from megamek to get superheavy and ultra light mechs working").
  RULES_REVIEW F70-F71. From MegaMek: the structure table for 10-15 and
  105-200 tons (a superheavy head 4), superheavy slots - an item takes half
  its slots, rounded up, and one slot may hold two ammo bins / heat sinks
  ("A|B": the second is appended after the 12 slots as `partner_of_slot`,
  never itself a critical hit target; `clone_mech` re-points the pairs).
  From the Core appendix (pp.236, 240-241): Large target -1
  (`_target_tmm`, movement scoring), +1 to its own physical attacks
  (`physical_attacker_modifier`), 1 MP less into rough / rubble / woods /
  jungle (`terrain_rules.GroundLimit` carries the flag through the path
  search), 3 levels tall / 2 prone (`los.Height` - partial cover next to a
  hex 2 levels up or in depth 2; none prone), water one level deeper and
  the depth-1 `water.WADING` state, its own Different Levels table
  (`physical._superheavy_options`, kicks two levels down), a slot's two
  ammo bins explode together for one MechWarrior hit, a compact engine
  dies at 2 hits, a superheavy tripod's technical officer (command console
  benefits, +2 to avoid heat shutdown / ammo explosions). Also fixed: a
  quad's cached reach lost its mule kick (`physical._FixedReach.mule_ok`) -
  a crash when a quad was scored next to an enemy. Not built: buildings
  (deferred), foliage (no such terrain), friendly-unit hex rules (no
  allies). Reference logs: only the summary's gap-list text changed;
  benchmark unchanged (HP 501 / 495). New tests/test_superheavy.py (9
  checks).
- **2026-10-28 (Claude):** Industrial tools deferred (Daniel: "Defering
  industrial tools") - Pick up here 10, the summary's gap list. Section 4's
  stale "rules gaps" paragraph refreshed. Reference logs regenerated (gap
  text only).
- **2026-10-28 (Claude):** Interstellar Operations weapons from Daniel's
  pasted rules (TSEMP pp.88-91, iATM, IMP and IIW rounds) and MegaMek's
  values for what the pastes don't give (Daniel: "There should either be a
  weapons table to look up, or megamek's values to use. Borrow from megamek
  for the nail gun too"; "Build what could be used. Custom units are and
  will be a thing"). RULES_REVIEW F66-F69. `INTEGRATION__advanced_weapons`:
  TSEMP effects / interference / shutdown / recharge / Repeating misfeed,
  IMP effects, inferno heat (Core p.192), nail gun; hooks in
  attack_resolution, fire_modes (IMP / IIW kinds, inferno munition,
  pricing), ammo (inferno bins fire; Improved and iATM IMP / IIW bins link;
  a recharging TSEMP is unavailable), electronics (as if jammed), mech_state
  (IMP -MP), equipment_systems / physical / charge / dfa (to-hit),
  weapon_rules (an iATM is a Streak), mtf_parser (`is_industrial` - also
  fixes the Taser's IndustrialMech column, which was never used).
  equipment.json "intops_pass": TSEMP rows (slots 5 / 3 / 7 - each slot
  had been read as its own TSEMP), iATM rows, Improved weapons' slots
  (Improved AC/5, SRM 6, LRM 15 / 20 had been doubled or quadrupled) and
  shots, Improved Gauss explosive (Daniel), nail gun range / heat / shots,
  nail ammo not explosive. Placeholders `TSEMP_EFFECT_WORTH` 5,
  `IMP_EFFECT_WORTH` 2 (Pick up here 3). Reference logs regenerated: only
  the summary's gap-list text and new munition-choice stub lines (the
  HeatGear test 'Mech's SRM inferno bins are now an option - the greedy
  stub keeps firing standard); no battle result moved. Benchmark unchanged
  (HP 501 / 495). New tests/test_intops.py (8 checks).
- **2026-10-28 (Claude):** Daniel's answers to the TO questions. (1) Princess
  prices hazards like MegaMek's checkPathForHazards: every hex her ground
  path stands in (`ranged_combat.PathBook` - the path the project's search
  found, the searches shared per pick), each once, the last as the end
  hex; a jump its landing hex; standing still nothing (modern: the water it
  stands in); a stand-up's GET_UP step in its own hex. Checking MegaMek's
  Terrains.HAZARDS (v0.50.07 and main alike) showed swamp is a hazard
  (calcSwampHazard - now ported) and rubble is not (its calcRubbleHazard is
  never reached) - the clone had priced rubble and missed swamp. Princess
  no longer walks through lava (Caustic Valley battles, both versions).
  Speed: a board with no hazard terrain skips it (`_hazard_board`). (2)
  Every Gauss rifle explodes when hit (Core p.184): Light, Heavy, Improved
  Heavy, Silver Bullet, AP Gauss and the HAGs were marked non-explosive.
  (3) `TASER_EFFECT_WORTH` joins the research pile (Pick up here 3); UMUs
  and the chain whip grapple deferred (Pick up here 10). Reference logs
  unchanged except the summary's gap-list text. Tests: tests/test_hazards.py
  princess_prices_the_whole_path, tests/test_advanced_gear.py
  every_gauss_rifle_explodes.
- **2026-10-28 (Claude):** Tactical Operations weapons, equipment and hex
  types (Daniel: "wire in functionality of missing weapons, equipment, and
  hex types already noted"; rules from the TO:AUE / TO:AR summary layers of
  `logajam/battletech-rules-index`, page-cited in the code). RULES_REVIEW
  F57-F64. New modules `INTEGRATION__hazards`, `INTEGRATION__smoke`,
  `INTEGRATION__advanced_weapons`, `INTEGRATION__advanced_equipment`; new
  tests `tests/test_hazards.py`, `tests/test_advanced_gear.py`; maps
  `data/32x17_Caustic_Valley_Lava.board`,
  `data/16x17_Badlands_2_Hazardous_Liquid.board`. equipment.json
  "to_aue_pass" (shots, damage types, slot counts; Mek Taser and fluid gun
  ammo rows). Path search: the least hazard damage wins first, then hexes
  moved (unchanged when a board has no hazards). Reference logs regenerated: only the summary's gap-list text changed
  (no battle result moved - none of their 'Mechs or boards carry the new items). Found, not fixed
  (Core data, out of scope): Light / Heavy / Improved Heavy Gauss rows are
  not marked explosive, though Core p.184's Gauss rule covers every Gauss
  rifle. Not built, for Daniel: 'Mech UMUs, the chain whip's grapple,
  Princess checking every path hex for hazards (MegaMek does; the clone
  prices the end hex - on lava maps she can walk through lava).
- **2026-10-27 (Claude):** Two questions from the pick-quality battery (Daniel:
  "why was princess hiding? Also it seems gladiator is blood thirsty. I
  wonder if there is a case where it will break off an attack to preserve
  itself"). Scratch study (not in the repo): the 8 pick-quality scenarios x
  20 battles, Gladiator driving both sides; at every second-mover decision
  modern Princess's ranker was asked too, with each spot's score parts.
  PRINCESS HIDES on 487 of 2,739 second-mover decisions (18%; 10% Large
  Lakes - 28% Scattered Woods) - by her own rules, not a bug: an enemy that
  has moved can't shoot a spot it can't see, so hiding scores 0 on the trade,
  and her trade is 1.5 x my damage - its damage (both as firing-plan
  utility, its punches / kicks at their threat weights). Her best spot WITH
  line of sight averaged 3.6 dealt vs 8.6 taken; in 60% of the hidden picks
  that spot traded below zero (1.5 x 3.6 < 8.6). The term that tipped it:
  the trade 53%, aggression 28% (the hidden spot is NEARER - 7.1 vs 7.8
  hexes: round a corner, behind woods), facing 10% (the line-of-sight spot
  faced badly), the close-range pull 8%. Gladiator can't do it when moving
  second: it only takes a spot with line of sight while one deals damage.
  GLADIATOR BREAKS OFF, but not to save itself: moving first it chose a
  spot with no exchange (its modeled reply can't shoot and nor can it) on
  27% of 2,729 decisions and opened the range on 51%; moving second it chose
  a line-of-sight spot that deals nothing on 14.5% and opened the range on
  16%. The rates DON'T rise as it gets hurt (moving first: 27.6% above 80%
  HP, 27.2% at 50-80%, 25.9% below 50%) - the lifetime objective compares
  dealt with received x (my future damage / its future damage), and HP left
  scales both options alike, so being damaged doesn't make it more careful.
  It disengages when the exchange is bad, not when it is in danger. A
  self-preservation pull when crippled would be new bot logic - it goes
  with forced withdrawal (Pick up here 5, and Princess's own withdrawal,
  item 00) - Daniel's call.
- **2026-10-27 (Claude):** Do the short list's rules of thumb hold up? (Daniel:
  "Set up a battery of tests using a diversified set of combatants across a
  range of maps. At least one set should be a faster unit with longer range
  that wants to kite ... For each turn's board state take a measurement of"
  Perfect, Short-Grid, Short-Short-Grid, Princess classic / modern "... what
  average percentage of score is earned compared to perfect knowledge ...
  And How many hexes away on average the pick is"). New
  `tests/pick_quality.py` and `movement_selection.SCORE_SINK` (studies only,
  off by default: Perfect's run prices every reachable spot and charge / DFA
  with the objective). 8 scenarios x 20 battles, Gladiator (Short Grid)
  driving both sides, 30-turn cap, scenarios one after another, battles in
  parallel: Dervish vs Hunchback (Grassland, kite), Griffin vs Hunchback
  (Scattered Woods, kite), Catapult vs Jenner (Rolling Hills, LRM vs fast
  brawler), Kontio vs Hammerhead (Grassland), Atlas vs Archer (Hilltops),
  Awesome vs Griffin (Military Base, Griffin kites), Locust vs Commando
  (Desert Hills), Black Hawk vs Cataphract (Large Lakes). Added to data/: 4
  boards (Rolling Hills 1, Scattered Woods, Hilltops 1, Desert Hills) and 8
  'Mechs (Dervish DV-6M, Hunchback HBK-4G, Griffin GRF-1N, Catapult CPLT-C1,
  Jenner JR7-D, Awesome AWS-8Q, Locust LCT-1V, Commando COM-2D).
  Scale: best / worst / rank over the spots Perfect chooses among (moving
  second: only spots with line of sight; a no-LOS pick is priced at most at
  the best); decisions where nothing deals damage (Perfect's closing
  fallback) left out. "% of best" reads 95-100% for everyone (the lifetime
  objective is mostly HP left); "% of range" = (pick - worst) / (best -
  worst) is the sharper one. 5,116 decisions; % of best / % of range / got
  the best spot / hexes from Perfect's pick / closer to the enemy than
  Perfect / ms a decision:
    Perfect          100.0 / 100.0 / 100% / 0.00 / +0.00 / 680 ms
    Short Grid        99.6 /  94.2 /  57% / 2.23 / -0.13 / 116 ms
    Short-Short       98.8 /  86.7 /  30% / 3.01 / +0.44 /  70 ms
    Princess 0.50.07  95.9 /  77.5 /  22% / 3.71 / +2.61 /  40 ms
    Princess modern   96.6 /  79.7 /  20% / 3.50 / +2.12 /  52 ms
  First mover: Short Grid 96.1% of range, Short-Short 91.0, Princess 70-76
  (+2.8 to +3.4 hexes closer). Second mover: Short Grid 91.9, Short-Short
  81.8, Princess 84-86 (+1.3 to +1.7 closer; 15-17% of its picks hide out of
  line of sight). Kiters only (1,634 decisions): Short Grid 94.4% of range,
  +0.05 hexes closer - no closing bias; Short-Short 88.2, +0.56; Princess
  75-78, +2.5 to +2.8 - Princess closes when it doesn't have to. Per scenario
  Short Grid stays 92.5-96.1% of range everywhere (worst Military Base),
  Short-Short 82.9-91.8 (worst Military Base, best Hilltops). Verdict: the
  rules of thumb hold up - the short-list look-ahead (in Short Grid, the
  default) loses ~6% of the score range and has no closing bias; picking
  your own spot from the short list too (Short-Short) costs another ~7%
  and adds a slight lean in (strongest moving first, +0.9 hexes) for ~40%
  less time.
- **2026-10-27 (Claude):** The MODERN Princess (Daniel: "Clone the entire
  modern suit for Princess. Do a sanity check vs the results of one of the
  previous runs thats already recorded, see if she improves"). MegaMek main
  at fd2edfb (2026-10-26): new `INTEGRATION__princess_modern.py` (posture,
  close-range incentive, squaring up, position hold with the water sustain
  boost, attacker-movement and cover discounts, physical threat weights, the
  modern water hazard) and modern FireControl in `INTEGRATION__princess_fire`
  (movement heat and the TSM ceiling in the tolerance, the TSM heat
  incentive, crits / kills by damage on a hit). `config.PRINCESS_VERSION`
  ("modern" DEFAULT, "0.50.07"); orchestrator sets `mover.turn_number`;
  `ab_batches.py --set bots-classic`; `tests/test_bots.py` checks the modern
  fire control, the posture and both versions' battles. The classic version
  reproduces its recorded 20-battle Kontio-Hammerhead run exactly (5-15-0 /
  17-2-1 / 7-13-0); Gladiator unchanged (all reference logs identical).
  Sanity check against the recorded 100-battle runs (same seeds; wins of the
  side Princess plays, classic -> modern, with both-Gladiator for scale):
  Kontio-Hammerhead - Princess Red 14 -> 40 (Gladiator 63), off-board deaths
  48 -> 25; Princess Blue 14 -> 11 (Gladiator 31); both Princess Red 44 -> 68.
  Atlas-Archer - Princess Red 73 -> 81 (Gladiator 92); Princess Blue 0 -> 2
  (Gladiator 7); both Princess 94-6 -> 97-2. Battles last longer (Kontio
  6-7 -> 7-8 turns, Atlas 9-11 -> 10-14). Modern Princess is better, most
  of all as the faster brawler (the close-range pull, squaring up); it still
  trails Gladiator in every seat, and is still pushed off the board often.
- **2026-10-27 (Claude):** Short-Short, best few states + grid prune (Daniel:
  "Keep only the best few states. Also wonder if short list hexes tend to be
  continuous. If so then a grid search prune on them would reduce the total
  that need to be checked"). `movement_selection.own_short_list`: per
  short-list hex and movement mode, one state - most hexes moved (least MP
  on a tie), then the facing nearest the enemy - always a reachable state.
  New `config.MOVEMENT_SHORT_LIST_GRID` (default False): the grid search
  ("guess and follow") over those hexes instead of all of them.
  Contiguity (Short-Short, 10 battles each, Kontio-Hammerhead, Atlas-Archer,
  Cataphract-Emperor; 740 decisions): reachable 412 states / 60 hexes ->
  short list 25 hexes, 48 states kept; 1.9 connected groups a decision, the
  largest holding 85% of the hexes, 0.3 lone hexes - mostly continuous.
  A/B, 20 battles, wins Red-Blue-draw, ms a turn (Short Grid -> Short-Short
  -> + grid prune): Kontio-Hammerhead 13-5-2 / 14-6-0 / 12-8-0, 127 / 125 /
  104 ms; Atlas-Archer 19-1-0 / 20-0-0 / 20-0-0, 36 / 29 / 28 ms;
  Cataphract-Emperor 2-17-1 / 1-19-0 / 1-19-0, 98 / 105 / 73 ms. Results
  within noise; Short-Short battles end sooner (9-10 turns vs 16-18 on two
  matchups). Default unchanged; all checks pass.
- **2026-10-27 (Claude):** "Short-Short" for Gladiator, BEGUN (Daniel: "second
  mover only tests its short list vs the opponent's short list to pick a
  movement option"; Daniel near his usage limit). `MOVEMENT_SEARCH` /
  `"search"` = "short_list": the second mover scores only the reachable
  states in its own hex and at the short-list distances from the enemy
  (`short_list_distances`); CORRECTED the same day (Daniel: "I want the
  First mover to only evaluate against its own short list vs the 2nd movers
  short list. Basically both sides are only picking from their own short
  lists"): the first mover too scores only its own hex and the hexes at the
  short-list distances from the enemy's current hex, each against the second
  mover's short list (the look-ahead). Kontio-Hammerhead, 20 battles: Short
  Grid 13-5-2 (17.6 turns), Short-Short 14-6-0 (10.4 turns, same winner
  15/20); 53 s vs 47 s - every state in the short-list hexes gets the full
  look-ahead, where the grid search checks only part of the board. With the
  default look-ahead ("short_list") that is Short-Short. `ab_batches.py
  --set short-short`. First check, Kontio-Hammerhead, 20 battles: Short Grid
  13-5-2, Short-Short 13-7-0 (34 s vs 40 s, same winner 10/20). Default
  unchanged. Open: wider A/B, a speed and agreement row (bot_agreement),
  Daniel's confirmation that this is the reading he meant.
- **2026-10-27 (Claude):** Princess vs Gladiator SPEED (Daniel: "how fast is
  princess compared to gladiator? Either in terms of operations to reach a
  decision, or just measure how long its turns take"). `tests/bot_agreement.py`
  now times each picker on the same positions and counts its operations -
  the (my spot, enemy spot) pairs it scores. 8 matchups x 20 battles, 2,272
  movement decisions, 4 workers, mean / median ms a decision, mean pairs:
  Princess 36 / 25 ms, 385 pairs; Short Grid 115 / 80 ms, 2,039 pairs (3.2x
  Princess); Perfect 556 / 102 ms (max 7.8 s), 89,153 pairs (15.6x). Moving
  first: Princess 23 ms, Short Grid 177 ms (7.8x), Perfect 1,046 ms (46x) -
  the look-ahead is Gladiator's cost (Princess has none). Moving second, all
  three are about the same (49 / 54 / 62 ms; Short Grid scores fewer pairs,
  110 vs 388). Whole turns, 10 battles, both sides the same bot, 1 worker
  (s a turn, Gladiator -> Princess): Kontio-Hammerhead 0.388 -> 0.275,
  Atlas-Archer 0.118 -> 0.041, Cataphract-Emperor 0.186 -> 0.081. Movement
  is 90-98% of a turn for both; the weapon choice is ~1.5-3.3 ms and the
  physical choice ~0.3-0.5 ms a call for either bot. (Princess's Kontio
  turns stay slow: a fast 'Mech has ~1,500 spots, all ranked with its fire
  control's heat plans.)
- **2026-10-27 (Claude):** Princess vs Gladiator, longer and wider (Daniel:
  "Longer and wider comparison runs. Also get a sense for how often princes's
  top pick matches the 'Perfect Knowledge' and the current default setting
  (Needs a nick name.) if it were gladiator"). Nickname used for now: the
  default Gladiator = **"Short Grid"** (grid search + short-list look-ahead,
  after Daniel's "Simple Short Grid") - made the official name 2026-10-28;
  "Perfect" = exhaustive own search and look-ahead.
  A/B, `ab_batches.py 100 ... --set bots --turns 50`, 100 battles a setting,
  wins of the side Princess takes over (baseline both Gladiator -> that side
  Princess): Kontio-Hammerhead Red 63->14, Blue 31->14; Atlas-Archer Red
  92->73, Blue 7->0; Kintaro-Atlas Red 11->4, Blue 87->58; Cataphract-Emperor
  Red 6->5, Blue 92->83; Akuma-Highlander IIC Red 11->15, Blue 88->64;
  Bombardier 14K-Black Hawk F Red 21->19, Blue 76->27; Black Hawk-Cataphract
  Military Base Red 81->48, Blue 17->15; same on Large Lakes Red 75->53, Blue
  25->10. Overall Princess won 502 of 1,600 battles in the seat where
  Gladiator won 783 - Gladiator is worse in only one case (Akuma Red, +4,
  noise). Pushed off the board: up to 48 of 100 with Princess on a side (it
  ignores edges). Princess battles last 6-10 turns against Gladiator's 12-19.
  Agreement, new `tests/bot_agreement.py` (20 battles per matchup, the 8
  above, Princess vs Gladiator alternating sides; at every movement decision
  Princess, Short Grid and Perfect each pick from the same position, only the
  'Mech's own bot's pick is played - checked: the battle is unchanged):
  2,272 decisions - same spot (hex, facing, mode) / same hex / avg hexes
  apart: Princess vs Perfect 14% / 23% / 2.7; Princess vs Short Grid 13% /
  22% / 2.7; Short Grid vs Perfect 53% / 55% / 1.6. Moving first (enemy still
  to move): Princess vs Perfect 4% / 9% / 3.6, Short Grid vs Perfect 39%;
  moving second: 24% / 37% / 1.8, Short Grid vs Perfect 68%. Least agreement
  on the terrain boards (7-9% same spot), most Akuma-Highlander (~20%).
- **2026-10-27 (Claude):** The Princess clone (Daniel: "I would like to
  make a clone of Megamek's Princess bot to compare it against"; "work until
  the task is complete"). New `INTEGRATION__princess.py` (BasicPathRanker:
  the path utility, both enemy estimates, ConvexBoardArea / HexLine ported
  with Java integer maths, fall tolerance and range filters, end-hex hazards)
  and `INTEGRATION__princess_fire.py` (FireControl's plan utility and heat
  plans; PhysicalCalculator's attack choice). Hooks: `weapon_selection.
  fire_control` (a context: inside it, `select_weapons_to_fire` hands its
  candidates - now with each one's to-hit number - to another bot's chooser;
  `side` passed through from `MoveEvaluator`'s scorers), `bots.fire_control`
  around `declare_attacks`' arc loop (Princess plans no physical with its
  fire), `bots.choose_physical` in `run_physical_phase`. `config.
  PRINCESS_BEHAVIOR`; `ab_batches.py --set bots`; `tests/test_bots.py` now
  checks the geometry port, the plan utility, that the fire-control hook
  stays scoped, and a repeatable Princess battle. Gladiator unchanged: every
  reference log identical, all checks pass.
  A/B, 20 battles a setting, same seeds, 50-turn cap (wins Red-Blue-draw):
  Kontio vs Hammerhead - Gladiator both 13-5-2; Princess Red 5-15-0 (8
  off-board deaths); Princess Blue 17-2-1; Princess both 7-13-0. Atlas AS7-K
  vs Archer ARC-2R - Gladiator both 19-1-0; Princess Red 12-7-1 (7 off-board:
  the Atlas stands on its edge row and the Archer pushes it off); Princess
  Blue 20-0-0; Princess both 18-2-0. Princess battles are shorter (6-9 turns
  against 14-18) and its turns are a little faster (no look-ahead).
  Replays now record each side's bot (`"bot"` in the mech header) and show it
  in the title ("Kontio (Princess) vs Hammerhead (Gladiator)").
- **2026-10-27 (Claude):** Bots per unit, stage 1 (Daniel: "The ability to
  select what type of bot each unit uses. The current system ... shall be
  called 'Gladiator'"). New `INTEGRATION__bots.py`: `config.BOT` (default
  "gladiator") and an optional `"bot"` key in each `MECH_*_CONFIG`; the
  orchestrator attaches `mech.bot` and asks `bots.choose_movement` for the
  Movement Phase pick. "princess" is registered but refused at load time
  until built (Section 6, "Princess clone", has the port plan from MegaMek
  v0.50.07). New `tests/test_bots.py`. Results unchanged: every reference
  log identical, 33 of 33 checks pass.

- **2026-10-24 (Claude):** Daniel's "simple short list" two-ply look-ahead,
  the DEFAULT (`MOVEMENT_ASSUMED_ENEMY_SEARCH = "short_list"`; Daniel: "we
  push 'Simple Short list' for the first movers evaluation"; both movers keep
  the grid search for their own spots). Research first (Daniel's theory: "the
  move second side ... will consistently tend to pick a spot from a more
  limited selection of locations"): 30 full-fidelity battles (both sides
  exhaustive; 5 matchups, 3 boards, ~156k modeled replies). In one decision
  the reply lands on 5-63 distinct hexes for 125-800 first-mover spots; 89%
  hit the first mover's side or rear, 31% stand next to it (Kontio 86%,
  mostly behind); stand-off replies sit at range-bracket ends (Atlas 44% at
  7, Cataphract at 6, Black Hawk one past the Cataphract's brackets). The
  rule of thumb (`movement_selection.short_list_distances`): next to the
  first mover, the replier's own hex, the replier's `MOVEMENT_SHORT_LIST_DROPS`
  = 2 biggest damage drops and one past the first mover's (rough damage by
  range at pre-TN 6); ~80% of exact replies. Each listed hex is scored once
  per movement mode at its best TMM, facing the first mover (Daniel:
  "Location, best tmm of any move to that hex per movement type. Expected
  incoming damage as if its facing you"; the facing isn't checked as
  reachable, and the first mover's return fire counts as front hits - "The
  first mover can never control its targets facing anyways unless its
  immobile"; an immobile or prone replier keeps the full model). Same-state
  A/B over 191 decisions: same pick 46%, score lost 0.20% on average (worst
  3.5%) vs 0.45% (worst 6.6%) for the grid reply - picks change but among
  near-ties. Per turn (ab_batches `--set short-list`, 8 battles, 15 turns):
  ~1.5x faster than the grid reply (Kontio 244 -> 168 ms, Atlas 54 -> 43,
  Black Hawk 111 -> 69). Short-grid vs perfect knowledge, one per side
  (`--set short-vs-perfect`, 12 battles, 25 turns): Atlas / Archer and Black
  Hawk / Cataphract within noise; Kontio / Hammerhead both perfect 5-5,
  Hammerhead short-grid vs Kontio perfect 2-8, both short-grid 9-2 - an
  isolation run (20 battles, both grid for own spots) gave grid reply 12-5,
  short-list 13-3, so the lean is the grid search's (already the default),
  not the short list's. Benchmark ~3.5 s -> 2.1 s (HP 501 / 495). New:
  `ranged_combat.turned_option`; tests short_list_reply_follows_its_rule,
  damage_drops_sit_on_bracket_ends; test_replay reads the outcome from the
  result instead of pinning it. Reference logs updated (all 15 - intended).
- **2026-10-21 (Claude):** Daniel's answers: Thumper 20 shots a ton / 5
  heat, Sniper 10 / 10 (equipment.json; no more unlimited-ammo stub); homing
  rounds' 5 AE hits every other unit in the hex; TAG can designate the
  ground (`STUB_TAG_AIM`, Section 6; homing then 5 AE to the 'Mech there).
  The Uni ATAE-70 is an illegal design; the split-item join in a shared
  location is a Section 4 cleanup-sweep item (code left as is).
  test_weapons updated. Reference logs unchanged.
- **2026-10-21 (Claude):** TAG and homing artillery (RULES_REVIEW F56, pp.53,
  190, 200), new `INTEGRATION__tag`: a designation step before the Ranged
  Attack Phase (`STUB_FIRE_TAG`, Section 6); Arrow IV / Thumper / Sniper
  homing rounds parsed and fired at a designated target (2D6 4+: 20 / 10 / 5
  direct-fire, else 5 AE). Smoke and active probes left as G34 (no smoke
  source yet). test_weapons tag_and_homing_artillery. Reference logs
  updated: the Asymptote mounts TAG, so the new stub's lines and the
  known-missing wording - battle results unchanged.
- **2026-10-21 (Claude):** Thumper / Sniper artillery as Arrow IV (Daniel's
  wiring; RULES_REVIEW F55): their own damage (15/5, 20/10), slots fixed
  (15, 20), the parser joins a three-location split; homing damage recorded
  for TAG. Open for Daniel: shots per ton (unlimited, loud stub) and heat.
  test_weapons thumper_and_sniper_artillery. Reference logs updated: the
  known-missing note's wording only.
- **2026-10-21 (Claude):** Torpedo launchers (RULES_REVIEW F54, pp.127,
  187): all torpedo names parse (as their LRM / SRM launcher), fire only
  underwater along an all-water line, and use only torpedo rounds. Before,
  "LRT 5"-style names fired on land as LRMs and "CLLRT15" didn't parse (26
  units). test_water torpedoes. Reference logs unchanged; the benchmark too.
- **2026-10-21 (Claude):** PPC capacitors (RULES_REVIEW F53, p.188), new
  `INTEGRATION__capacitor`: links, charging / holding heat, +5 damage and heat
  when fired charged, the explosion on a crit. Both choices are stubs, off by
  default (`STUB_CAPACITOR_START` / `STUB_CAPACITOR_CHARGE`, Section 6).
  `weapon_selection`'s table cache key now includes the charges.
  test_weapons ppc_capacitor. Reference logs updated: only the known-missing
  note's wording (capacitor charging is now a stub, off by default).
- **2026-10-21 (Claude):** Blue Shield particle field damper (RULES_REVIEW
  F52, pp.180, 207); on / off is a stub (`STUB_BLUE_SHIELD`, Section 6).
  test_equipment blue_shield. Reference logs unchanged.
- **2026-10-21 (Claude):** APDS (RULES_REVIEW F51, p.206) - Core after all;
  engages like an AMS and stacks with one. test_ams apds. Reference logs
  unchanged.
- **2026-10-21 (Claude):** Cockpit command console (RULES_REVIEW F50, p.203);
  the End Phase seat swap is a stub (`STUB_CONSOLE_SWAP`, Section 6).
  test_rules command_console. Reference logs unchanged.
- **2026-10-21 (Claude):** HarJel I / II / III (RULES_REVIEW F49, p.208).
  test_water harjel. Reference logs unchanged.
- **2026-10-21 (Claude):** Quad kicks - front kick and mule kick (RULES_REVIEW
  F48, p.238). test_special_attacks quad_kicks. Reference logs unchanged.
- **2026-10-21 (Claude):** Shields and vibroblades (RULES_REVIEW F47); raising a
  shield and activating a vibroblade are stubs (`STUB_RAISE_SHIELD` never,
  `STUB_VIBROBLADE` on - Section 6). test_special_attacks shields,
  vibroblades. Reference logs and benchmark unchanged.
- **2026-10-21 (Claude):** Talons on DFA, spikes, lance armor-piercing checks
  (RULES_REVIEW F46, new `INTEGRATION__physical_gear`), the charge-spikes
  declaration as a stub (`STUB_CHARGE_SPIKES`, Section 6). Bug fixed: a
  multi-slot physical weapon was one item per slot (one crit didn't wreck
  it). test_special_attacks talons_spikes_and_lances. Reference logs
  unchanged.
- **2026-10-21 (Claude):** Heat-dissipating armor (RULES_REVIEW F45, p.202):
  flamer / plasma damage to it halved, no outside heat. test_weapons
  heat_dissipating_armor. Reference logs unchanged.
- **2026-10-21 (Claude):** Heavy-duty gyro (RULES_REVIEW F44, p.204): 4 hits to
  destroy, +1 a hit, no PSR from its hits or from running, +2 to jump with
  hits; the .mtf gyro type is now read. Chemical laser ammo checked - already
  right (G31). test_rules heavy_duty_gyro. Reference logs unchanged.
- **2026-10-21 (Claude):** To-do list refilled (Daniel: "Are there any weapons
  or equipment that don't have rules implemented yet"): a survey of every
  unit in `data/meks.zip` against the Core Rulebook's Weapons & Equipment
  chapter - RULES_REVIEW G23-G33 (Pick up here 7a), plus the list of items
  with no effect in a duel and non-Core items.
- **2026-10-21 (Claude):** Clubs (Daniel): holding one never blocks fire
  (the code already let it fire), firing an arm weapon rules out the club
  attack that turn (already so, p.79); `CLUB_PICKUP` now on - a mech that
  fires nothing picks up a club in its hex. PPC capacitors noted for their
  own session (Pick up here 8). Reference logs regenerated where clubs got
  picked up.
- **2026-10-21 (Claude):** "Follow the rules, not my calls" (Daniel). Quads'
  leg damage by the book (RULES_REVIEW F43, pp.238-239): lost legs -1
  Walking MP / +1 PSR each for the first two, three = a biped with one leg
  lost (still mobile), four = immobile (was: destroyed at three, Walking MP
  1 at two); the first hip hit has no MP / PSR / running-PSR / level-limit
  effect, later ones do; two lost legs bring a hip hit's effects.
  `mech_state.hip_effects` / `ground_level_limited` (the level limit now
  goes through it everywhere). `POOL_CLUSTER_DAMAGE` default False. Sweep
  of other "Daniel's rule" spots: the 2-per-slot component explosion is the
  book's (p.96) - comment fixed; `FIGHT_TO_THE_DEATH` briefly flipped on,
  then back off at Daniel's word (speed). Reference logs regenerated: 12
  changed by the pooling default; one winner flipped (Bombardier 14K vs
  Black Hawk: Blue -> Red). test_rules quad_leg_damage_by_the_book.
- **2026-10-21 (Claude):** PSR special cases cleared from the rules
  (RULES_REVIEW F42): stand-up -1, leg destroyed +4 (was +5), tripod -1 with
  no leg lost (was -2) plus the dedicated pilot -1 / +2 disabled (PSRs and
  physical attacks) and the gunnery officer's +2 to ranged attacks when
  disabled, quad -2 only with all legs, +1 per lost leg (first two), no PSR
  to stand, one lost leg forces no run / jump PSR. test_rules
  psr_modifiers_by_the_book. Reference logs regenerated (13 changed in the
  detail, 3 in the result, same winners). Found on the way: Daniel's quad
  leg-loss MP / destruction house rule differs from p.238 - left, asked
  (Section 4).
- **2026-10-21 (Claude):** Line of sight rebuilt to the Core Rulebook (Daniel:
  "make sure the LOS rules match those in the rules and fix prone mechs";
  RULES_REVIEW F41, D8 decided, G7 built). `pathfinder/los.py`: LOS levels
  with heights (standing 2, prone 1), the p.57 intervening test, hills /
  buildings block, woods and jungle points (3 block), partial cover with the
  height and prone conditions, border lines on one side for the whole line
  (the target's pick). Heights passed from `declare_attacks` / `attack_side`
  and the movement-scoring cache (`los_cache.board(map, a_height,
  t_height)`). New `tests/test_los.py` (the rulebook's examples).
  Reference logs regenerated: 8 changed; Large Lakes 1 now draws at the cap
  - the Cataphract sits fully under water where nobody can fire (p.62), a
  bot stall (Pick up here 0), not an LOS fault; the others keep their
  winners. Benchmark 495 / 495, ~4 s.
- **2026-10-21 (Claude):** BUG FIXED (RULES_REVIEW F40, p.94): Inner Sphere
  endo-steel / ferro-fibrous / stealth / reactive / reflective / ballistic-
  reinforced slots are written as plain names that don't match
  equipment.json, and any plain name counted as a crit target - on ~1,090
  units those 7-28 filler slots soaked critical hits meant for real
  components. Now inapplicable (`equipment.is_structure_or_armor_slot`).
  Found by a parse survey of all 4,227 units for unrecognized components
  (the rest are non-Core gear: cargo, backhoes, torpedoes...). 3 reference
  battles changed, same winners. test_rules
  structure_and_armor_slots_take_no_crits.
- **2026-10-21 (Claude):** Cockpits (RULES_REVIEW F39, p.203): small and
  torso-mounted cockpits +1 to every PSR (205 + 34 units in meks.zip);
  torso-mounted - no pilot hit from head hits, the head's loss isn't fatal
  (later head hits re-rolled), sensor hits +4 to physical attacks and PSRs
  (both head sensors, or 3+). The tripod leg sub-roll now draws from the
  battle's dice (was Python's random - a seed didn't replay it): the 5
  Asymptote reference battles changed, same winners. test_rules
  cockpit_types.
- **2026-10-21 (Claude):** Movement options (RULES_REVIEW G5, G8 -> F38):
  jumping into the mech's own hex for 1 MP (p.50 - any facing, +1 TMM, 3
  heat) and Minimum Movement (p.49 - run one hex straight ahead without the
  MP it costs, as the whole move). Reference logs regenerated: 10 changed
  (jump-capable mechs), same winners; the Asymptote mirror still hits the
  cap but trades more (6 / 6 damage -> 15 / 27). Benchmark 495 / 495. Not
  built: G12 (a charge after a backward step - the charge planner's paths
  are forward-only; a bot option). G7 (prone LOS height) waits for Daniel
  with D8 - `pathfinder/los.py` is his ruleset ("don't change without
  asking").
- **2026-10-21 (Claude):** Armored components (RULES_REVIEW G14 -> F37),
  and a parser bug found on the way: MegaMek's "(armored)" tag wasn't
  stripped, so on the 37 units carrying it an armored engine / gyro /
  cockpit / actuator was inert padding (crits did nothing) and an armored
  weapon never fired. Now parsed (`mech.armored_slots`); each armored slot
  absorbs one attack crit (p.207), not MASC / supercharger ones; an armored
  hip / shoulder stops a limb blown off once. test_rules armored_components.
  Reference logs unchanged (no armored unit in them).
- **2026-10-21 (Claude):** Water leftovers (RULES_REVIEW G6 -> F36): hits on
  a 'Mech standing in depth 1 from a leg weapon in depth 1, or any weapon of
  a fully submerged 'Mech, use the Kick Location Table (legs only, no
  partial cover, pp.67, 127); an energy weapon firing from under water uses
  the next bracket for its damage too (p.127, Snub-Nose PPC / VSP). New
  checks in test_water (18). Reference logs regenerated for the known-
  missing-rules text only (no battle changed).
- **2026-10-21 (Claude):** Rules gaps, physics first (Daniel: "I'm basically
  after getting the environment and physics of the game correct before
  worrying too much about the bots behavior"). (1) G20 "damage PSRs fall in
  the END hex" is the RULE (p.113: movement-mode PSRs are made at the end of
  movement) - TODO removed. But a charger's / DFA's movement only ends in the
  Physical phase (pp.78, 80): its end-of-movement PSRs now wait until then,
  joined by a PSR for the hex a successful charger advances into (rubble,
  sand, water when running) or a DFA lands in (water, rubble)
  (`movement_attacks.end_of_movement_triggers`); a DFA mech no longer rolls a
  landing PSR for the hex it hangs over (RULES_REVIEW F34). (2) G4: a mech
  can't pass through a mobile enemy's hex on the ground (p.48, F35;
  `pathfinder.build_movement_table(blocked=...)`). Reference logs
  regenerated: all 15 (the known-missing-rules text), 4 with different
  moves - Atlas S2 vs Kintaro, Kintaro vs Atlas, Bombardier 05A vs
  Cataphract, Black Hawk vs Cataphract (Military Base) - same winners.
  Benchmark unchanged (495 / 495). New checks: test_special_attacks
  charge_end_of_movement_psrs, test_pathfinder 9b.
- **2026-10-21 (Claude):** Daniel's two known issues fixed (Daniel: "Start
  with known issues"). (1) Scatter vs the firing arc (pp.182-183): a missed
  Arrow IV / artillery cannon now walks its scatter path hex by hex and
  stops at the last hex its launcher's firing arc still covers
  (`attack_resolution._in_firing_arc`: facing + declared twist / flip /
  turret); held all the way back it lands on the target's hex for the full
  area-effect damage. Artillery cannons without splash now roll the
  direction too (needed to know whether the arc holds the shell on the
  target). (2) Machine gun array ammo: guns sharing a bin each counted the
  whole bin, so 1 round left fired all 3 guns; the rounds are now counted
  once (`fire_modes.mga_firing_guns`, `take_array_rounds`). New checks in
  `tests/test_weapons.py` (14 now). `run_checks.py`: 31 of 31, every
  reference log unchanged (neither case arose in them).
- **2026-10-21 (Claude):** Session 6 wrap-up (Daniel: "Good session. Wrap it
  up. make sure everything is updated and ready to go for the next
  session."). Section 0 rewritten for session 6 (summary, the speed item's
  status and open follow-ups); Section 6's movement row names the new
  search settings; README's A/B line updated. Clean baseline at hand-off:
  `run_checks.py --bench` 31 of 31 in 60 s, benchmark 495 / 495 in 3.5 s.
- **2026-10-21 (Claude):** Knowledge A/B (Daniel: "If Red moves perfectly,
  and thinks Blue will move perfectly But blue moves using the fast method
  ... See how much of an advantage perfect knowledge is vs close enough").
  `tests/ab_batches.py --set knowledge`, 20 battles a setting, same seeds,
  50-turn cap. "Perfect" = exhaustive search; "expects" = the search it
  assumes for the enemy's reply. Wins of the side named (all fast = 0):
  Kontio (R) 11 vs Hammerhead (B) 8: R perfect +1 / +3 (expecting perfect /
  fast), B perfect 0 / -2; a fast side expecting perfect: R -2, B -2.
  Kintaro (R) 6 vs Atlas (B) 13: R perfect 0 / +1, B perfect +5 / +6;
  expecting perfect: R -1, B +1. Bombardier (R) 6 vs Black Hawk (B) 13: R
  perfect -2 / 0, B perfect +6 / +4; expecting perfect: R -5, B +3.
  Cataphract (R) 1 vs Emperor (B) 19: R perfect +2 / -1, B perfect 0 / -1
  (at the ceiling); expecting perfect: R -1, B +1. Dice noise at 20 battles
  is about +-2 wins. Reading: searching perfectly helped the side already
  winning (Atlas, Black Hawk ~ +5, Kontio +1 to +3) and not the underdog;
  what a side assumes about the enemy's search made no consistent
  difference. A perfect side runs 0.3-0.6x the default's speed. Output:
  `run_stats/ab_knowledge_2026-10-21.txt`.
- **2026-10-21 (Claude):** The grid search is the DEFAULT (Daniel: "I think it
  should become the default"), and each side can have its own search
  (Daniel: "See how much of an advantage perfect knowledge is vs close
  enough"). `config.MOVEMENT_SEARCH` (how a mech picks its own spot - the
  first mover's two-ply candidates, the second mover's real pick) and
  `MOVEMENT_ASSUMED_ENEMY_SEARCH` (how a first mover assumes the reply
  picks) replace MOVEMENT_TWO_PLY_SEARCH / MOVEMENT_REPLY_SEARCH; both
  "grid". Per side: `MECH_RED_CONFIG` / `MECH_BLUE_CONFIG` "search",
  "assumes_enemy_search" (`orchestrator._attach_mech_config`,
  `movement_selection.own_search` / `assumed_enemy_search`). The movement
  note says "N of M spots (grid search) x K replies (grid search)". All 15
  reference logs regenerated (intended); the Asymptote mirror still hits
  the 50-turn cap. Benchmark 501 / 495 (14.5 s) -> 495 / 495 (~3.5 s); both
  "exhaustive" settings, globally or per side, still give 501 / 495.
  `run_checks.py` 186 s -> ~60 s. Two movement checks that prove the
  perfect search finds the best spot now pin "exhaustive"; new check
  per_side_search_settings. `tests/ab_batches.py`: settings "DICT.key" set
  one key of a config dict; sets "search" (all fast vs all perfect) and
  "knowledge" (one side perfect, expecting perfect or fast...).
  **Bug fix found by the new battles:** an aimed shot (p.70) applied
  `weapon.damage_per_shot` instead of the shot's damage
  (`fire_modes.damage_per`), so an aimed Heavy Gauss Rifle shot (variable
  damage, no listed figure) crashed the Atlas AS7-S2 vs Kintaro battle;
  `_resolve_aimed_hit` now takes the damage (`tests/test_equipment.py`).
- **2026-10-21 (Claude):** Grid spin A/B (Daniel: "clockwise vs counter
  clockwise grid spin ... no more then a single set of 20 sims").
  `config.MOVEMENT_GRID_SPIN`: the two mirror-image 1-in-7 nets, cube
  (q + 3r) or (q + 5r) mod 7 - range-3 net hexes "2 out, then 1 turning
  clockwise / counter-clockwise"; default "clockwise" (the net so far).
  Kontio vs Hammerhead, 20 battles, both movers on the grid
  (`--set grid-spin`): clockwise 11 / 8 / 1 draw, 14.7 turns, dealt 42.0 /
  44.0; counter-clockwise 12 / 7 / 1, 18.2 turns, 47.4 / 48.0 - no
  difference beyond dice noise; kept clockwise. Defaults unchanged.
- **2026-10-21 (Claude):** Always-checks for the grid search (Daniel: "add a
  short list of always checks. Your starting position for standing still,
  the targets position for charging. And the 6 hexes around it for melee";
  then "Always checks wouldn't help the first mover"). `_grid_search` always
  looks at the mover's own hex and, for the SECOND mover only (the modeled
  reply and its real pick), the 6 hexes around the enemy; the first mover's
  enemy moves after it. Charging into the target's hex needed nothing new:
  charges / DFAs are scored apart, over every charge state, in any search
  mode. Defaults unchanged (reference logs, benchmark 501 / 495). A/B, 20
  battles x 6 matchups (`--set search-always`): first mover only - the same
  numbers as before (own hex was already a net hex); both movers - all six
  within noise of the exhaustive baseline. Kontio vs Hammerhead, 100 battles
  (the case that looked off): Kontio 61 / Hammerhead 34 / 5 draws (baseline
  57 / 41 / 2; without the always-checks 38 / 61 / 1), 3.5x faster than the
  baseline batch; 5 battles hit the 50-turn cap (baseline 1) - watch.
  Benchmark with both grids on: 3.4 s (exhaustive ~14 s).
- **2026-10-21 (Claude):** Guess-and-follow two-ply search (Daniel: "check a
  sample of all the places you could end up, pick the best ranking one and
  then check the hexes around it. If a better choice exists follow it"), as
  switches, default OFF - every reference log and the benchmark (501 / 495)
  unchanged. `config.MOVEMENT_TWO_PLY_SEARCH` = "grid": the first mover looks
  at a 1-in-7 net of its reachable hexes (cube (q + 3r) mod 7 - the hex
  grid's own spacing: every hex is a net hex or next to exactly one), then
  climbs from the best `MOVEMENT_SEARCH_STARTS` net hexes to better
  neighbours (`movement_selection._grid_search`; a hex looked at scores all
  its facings / modes). `config.MOVEMENT_REPLY_SEARCH` = "grid" does the
  same for the second mover, in the modeled reply and in its real pick
  (Daniel: "what happens if second mover uses the same picker formula").
  Offline first (230 recorded two-ply decisions, 14 matchups): ~5 local
  peaks among ~58 hexes a decision; grid 1/7 + climb = 28% of the work,
  exact best 52%, within 2 points 78%; sparser nets lose accuracy but save
  little more (the climb dominates). A/B (`tests/ab_batches.py --set search`,
  same seeds, 50-turn cap; 100 battles Kontio vs Hammerhead, 60 the rest):
  first mover on the grid - winners within dice noise in all 6 matchups
  (Kontio 57 -> 63 / 54 with best 3; Bombardier vs Black Hawk 6 -> 11 / 11
  of 60, borderline), battles a little shorter with slightly more hits a
  turn, batches 1.4x (Atlas, slow) to 3.3x faster. A yardstick run on other
  seeds (`--set baseline --seed 777`) moved hits a turn by up to 0.09 by dice
  alone. Both movers on the grid (`--set search-both`): 20 battles each,
  close in five matchups, but Kontio vs Hammerhead 6 / 20 (baseline 11 / 20);
  100 battles confirmed it - Kontio 38 wins (baseline 57), the Hammerhead's
  CT / engine deaths 35 -> 16. Likely: the Kontio's best spots are narrow
  (the right adjacent hex and facing for its claws), the hardest kind of
  peak for a sparse net to find. Benchmark with both on: ~14 s -> 3.0 s.
  Also: `ab_batches.py` gained --set / --turns / --board / --seed, damage /
  HP / identical-battle / speed columns; Daniel's 20-battle rule (Section 7);
  `tests/test_movement_selection.py` grid_search_net_and_follow. Output:
  `run_stats/ab_search_2026-10-21.txt`, `ab_noise_...`, `ab_both_...`.
- **2026-10-21 (Claude):** Speed pass (session 6; Daniel: "Back to trying to
  speed up a simulation run"). Speed only - every reference log and the
  benchmark's 501 / 495 are unchanged. Benchmark ~17.9 s -> ~13.4 s (about
  25% less, averaged over 3 runs each in this container). (1)
  `movement_selection._modeled_reply`: the reply spots' PSR costs don't
  depend on the first mover's spot, so `_psr_by_state` works them out once
  per pick instead of ~2 million times. (2) `MoveEvaluator.evaluate`: what
  depends only on the mover's hex (LOS rows, side hit, the defender's arc
  class, the to-hit bases, water) is worked out once per hex per call
  (`_hex_row`), the facing-dependent parts once per (hex, facing); candidates
  are built positionally. (3) `movement_attacks.scored_options` accepts a
  function for `best_by_mode`, so the reply's per-mode table is built only
  when a charge / DFA state exists. (4) `pathfinder/los.hex_line` works each
  line's shape out once per hex offset and shifts it (a 16x17 board has
  ~74k hex pairs but ~1,000 offsets) - checked equal to the direct line for
  every pair on 16x17 and 50x50 boards; `tests/test_pathfinder.py`
  test_10 keeps the 16x17 check. What's left (profile): the two-ply is
  still ~95% of a turn because it is exhaustive - every first-mover spot
  (313-629 in the benchmark) x every reply spot (396-634), up to ~400k
  pairs a pick, at about 3 memo lookups each; the one-time LOS fill is
  ~25% of a cold 10-turn benchmark but is paid once per worker in a batch.
  Further big gains need fewer pairs (a bot change - Daniel's call) or a
  compiled hot path (Pick up here 1).
- **2026-10-21 (Claude):** Session 5 wrap-up (Daniel: "Go ahead and wrap
  this one up. All files up to date. List of future problems to solve
  updated. Workspace cleaned up for the next session."). Section 0 rewritten
  for session 5; Pick up here item 7 reorganized (map leftovers; breach-risk
  pricing G21 noted but NOT to be built yet; full building rules G22
  deferred); the breach plan saved in the Section 6 Memo; Section 5 records
  Daniel's calls. No code change.

- **2026-10-21 (Claude):** The movement subphase (Daniel's design, Section 5;
  RULES_REVIEW F32; G11, G19 done).
  - `terrain_rules`: `step_psrs` / `turn_psrs` / `step_psr_causes`
    (rubble, sand with a level change, water when running, mud facing
    changes when running, backward level changes), `PSR_MODIFIER`,
    `has_psr_terrain` (cached on the board); backward level changes of one
    level allowed in `step_cost` (not with a destroyed hip, not on a roof).
  - `pathfinder`: `_build_terrain_psr` -> `PathTable` (PSR counts per entry,
    `path()` with `keep_parents`), used only on boards with PSR terrain or
    any level change - the flat boards keep `_build_terrain_aware` (results
    identical there).
  - `ranged_combat.movement_options` records `mover.path_psrs` (cleared per
    pick in `movement_selection.reduced_options`, which keeps a fewer-PSR
    variant unless dominated); `path_to()` rebuilds the path for a pick.
  - `movement_selection._Side.psr_cost` / `psr_for`: terrain PSRs priced as
    P(fall) x fall damage (`terrain_psr_odds`); jumps landing in water or
    rubble. Replaces the end-hex water pricing.
  - `orchestrator._walk_path` (roll each PSR in its hex; fall there) and
    `_after_fall_midmove` (stand with the MP left - `piloting_rolls.
    resolve_stand_up(mp_available=)` - and re-pick, repeatedly; hexes and MP
    add up, mode kept); `_landing_psr` (jumps: water, rubble) replaces
    `_water_psr`; a prone mech skips the end-of-move damage PSR.
  - Tests: `test_water.py` 16 (the subphase, terrain PSRs, backward level
    changes). Reference logs: Military Base 1 (backward level changes) and
    Large Lakes 1 (PSRs per water hex, two falls) regenerated; the others
    changed only in KNOWN_MISSING_RULES. Hill boards ~5-10% slower.

- **2026-10-21 (Claude):** Deployment depth and stuck terrain; water
  leftovers (Daniel's calls, Section 5; RULES_REVIEW F31, G20).
  - New `INTEGRATION__deployment.py`: `start_hexes(mech, board, edge)` -
    hexes 0..`config.DEPLOYMENT_DEPTH` (default 0) in from the home edge
    that the mech can enter (roofs too: `terrain_rules.step_cost(None, roof)`
    now allowed - "a mech's level before it enters is undefined") and from
    which it is not stuck (walking / jumping can reach a hex within 3 of the
    far edge); none -> `config.DEPLOYMENT_STUCK_DEPTH` (3). The deployment
    log line is unchanged for a plain edge. `mech.home_edge_row` keeps the
    edge for "head for the enemy's edge".
  - Hull breaches (`damage_resolution.mark_location_nonfunctional`, shared
    `_slot_loss_effects`): slots stay, still soak crits (effects not counted
    twice), breached ammo still explodes, breached gear that explodes only
    when working doesn't (p.127).
  - Scoring: `water.physical_value_factor` - physical damage to underwater
    locations counted at half in movement scoring (`physical.Planner`
    t_water), the Physical phase's pick and charge / DFA values (p.77).
  - Tests: `test_terrain.py` 11 (deployment, no start hex), `test_water.py`
    14. All reference logs unchanged. Benchmark 501 / 495 (17.2-17.6 s vs
    17.9-18.3 s for the pre-water code on the same machine).

- **2026-10-21 (Claude):** MAPS, part 3 - water rules, part 2 (RULES_REVIEW
  F30; `INTEGRATION__water`).
  - Physical attacks in water (p.77): `water.physical_allowed` filters the
    attack kinds in `physical.attack_options`, the Ranged phase's look-ahead
    (`attack_resolution._physical_planner`), movement scoring
    (`physical.Planner` / `ranged_combat._with_physical` take `allowed`) and
    charge / DFA planning (`movement_attacks`). `water.physical_damage`
    halves damage to underwater locations (punches, kicks, clubs, charges,
    DFAs).
  - Hull breaches (p.127): `damage_resolution.apply_damage` calls
    `water.check_breach` for each underwater location a grouping damages (2-4
    breaches); `orchestrator._after_phase` breaches armorless locations under
    water (`water.auto_breaches`); `water.breach` marks the slots destroyed,
    a leg as destroyed, a side torso's arm with it.
  - Drowning (p.117): `orchestrator._phase_end` - life support crit + fully
    submerged = 1 MechWarrior hit.
  - `tests/test_water.py` 9 -> 12 checks. The Large Lakes reference battle
    regenerated (breach rolls change its dice); every other reference log
    changed only in KNOWN_MISSING_RULES' water line. Benchmark 501 / 495.
    Sweep: 64 water maps x 2 seeds, 128 battles, no errors.

- **2026-10-21 (Claude):** MAPS, part 2 - water rules, part 1 (Daniel: water
  "Also Yes as the next task"). New `INTEGRATION__water.py` (page cites in
  each function); RULES_REVIEW F29, G6 is now part 2.
  - `terrain_rules.prepare_board`: a depth 1+ water hex's `level` becomes
    its floor (surface - depth, p.57), with `depth` and `surface_level` kept
    - so moving in / out is a level change (p.51; a depth-3 lake can't be
    walked into from its shore), jumps start / land at the floor (p.50), a
    'Mech in water stands on the bottom for LOS, and falls into water add
    the depth (p.115).
  - `los.py`: partial cover for a target standing in depth 1 (p.66), not
    against a fully submerged attacker; a water hex is never the "hill" that
    gives cover.
  - `attack_resolution.declare_attacks`: no attack across the water line
    (p.62); weapons the water stops (Underwater Attacks Table, pp.67, 127);
    underwater range +1 bracket, no long range (p.127, via the TN adjuster);
    submerged heat sinks in the heat budget.
  - Heat (`heat.py`, `ams.py`): submerged sinks dissipate double, at most +6
    (p.103); the Heat log shows "- water N".
  - Jumping MP in water (p.50): `water.jump_mp` (movement options, charges,
    the budget line).
  - PSRs: `orchestrator._water_psr` - running (Run, 1+ hex) or jumping into
    depth 1+ water, a failed jump falls the depth (pp.48, 50); END hex only
    (no paths kept). `piloting_rolls.resolve_fall` halves damage in water
    (p.115).
  - Movement scoring (`ranged_combat.MoveEvaluator`, `movement_selection`):
    each spot's water case (weapons stopped, range shift, heat sink bonus,
    the water line) and the water PSR's expected fall damage. Boards with no
    water take exactly the old path - every older reference log and the
    benchmark (501 / 495) are unchanged apart from the summary's
    KNOWN_MISSING_RULES text (water part 2 listed; all logs regenerated for
    that line only).
  - Replay viewer shows a water hex's surface level. `tests/test_water.py`
    (9 checks); reference battle Black Hawk F vs Cataphract CTF-3D on
    `data/16x17_Large_Lakes_1.board` (seed 1: jumps and runs into water, a
    halved fall, fire held across the water line, submerged sinks).

- **2026-10-21 (Claude):** MAPS, part 1 (Daniel, after the survey of
  MegaMek's 192 16x17 maps: "1. Yes ... 3. set an option (Set to on) to
  treat buildings as passive terrain"). Before: 31 maps played correctly, 29
  crashed (depth-0 water, bridges, ultra-heavy woods, stacked costs), 20
  didn't load (MegaMek "option" lines), and on the rest buildings, cliffs
  and most water rules were silently ignored. Now 165 play.
  - `pathfinder/board_parser.py`: skips "option" lines; knows MegaMek's
    terrain names (no warnings for building / pavement / fluff codes).
  - `pathfinder/terrain_rules.py` rewritten around `step_cost(from, to,
    level_limit, backward)` (MP or None = not allowed): Movement Costs Table
    p.48 with jungle / rubble / swamp / sand / mud / depth-0 water; stacked
    terrain adds up (p.47); road travel only road to road (p.53 - a road hex
    entered off the road now pays its terrain, CHANGED from always +0); the
    2-level limit, 1 with a destroyed hip (pp.46-47); passive buildings
    (pp.46, 134). `prepare_board()` runs when a map loads: refuses terrain not
    built yet with a list (bridges, ultra-heavy woods, MegaMek-only terrain)
    and turns building hexes into roofs (level = hex level + height, p.130).
    `transition_cost` kept for simple callers / old tests.
  - `pathfinder/pathfinder.py` (`level_limit`), `ranged_combat.movement_options`
    (hip limit; board entry can't land on a roof), `pathfinder/combat.py`
    (jump landing height, p.50), `movement_attacks` (charge's last step uses
    step_cost; a push from the ground into a building is blocked).
  - Option `config.PASSIVE_BUILDINGS` (default True; False refuses maps with
    buildings until the full rules are built).
  - Bug fix (`orchestrator.run_battle`): a mech that can't enter the
    battlefield (destroyed, p.37) left the battle running into the Ranged
    phase with no hex and crashed; the battle now ends there. Found on the
    Solaris arenas (Hartford Gardens, Scrapyard), whose east / west edges are
    solid walls.
  - Replay viewer draws buildings (B3 = roof level 3), roads / pavement,
    rough / rubble, water depth.
  - `data/maps.zip` (Daniel's map pack), `tests/survey_maps.py` (which maps
    play), `tests/test_terrain.py` (10 checks), new reference battle Black
    Hawk F vs Cataphract CTF-3D on `data/16x17_Military_Base_1.board` (seed 1,
    3 roof landings). The other reference logs are unchanged (flat board).
    Published replay: https://claude.ai/artifact/HcWk2ESA5zT4YKGc8MGfem
  - RULES_REVIEW F24-F28 (G2, G3 done), G6 now the water rules, new G19
    (terrain PSRs mid-move). Section 4: "Map terrain waiting on rules".

- **2026-10-21 (Claude):** Session 4 wrap-up (Daniel: "Cap the test battles
  length to 50 ... Anti-stall rule for the bot is added to the future tasks
  list ... the work space is set for the next instance"). Reference battles
  run with `config.MAX_TURNS = 50` (`check_reference_logs.TEST_BATTLE_MAX_TURNS`);
  one that reaches it prints "NOTE: reached the 50-turn cap ... a possible
  flaw" (also in `run_checks.py`), and every batch summary flags battles that
  hit their turn cap (`BattleResult.turn_cap`, summary "turn_cap_reached").
  Only the Asymptote mirror hits it (the stall); its log regenerated (the
  others end before turn 50 and are unchanged). run_checks ~12 min -> ~3 min.
  New `tests/ab_batches.py` (the A/B harness used this session: same seeds,
  several settings side by side). Section 0 rewritten for the next instance;
  RULES_REVIEW F21-F23 (AES, LOS on the border of two hexes, hardened armor);
  Section 7 notes (50-turn cap; a parallel instance). Benchmark 501 / 495.

- **2026-10-21 (Claude):** New default movement objective: "lifetime" with
  the history blend, K = 3 (Daniel: "Switch this system to the new default").
  `tests/test_movement_selection.py`'s brute-force helpers now score with the
  configured objective (they used the ratio formula directly). All reference
  logs regenerated (intended). Benchmark 477 / 468 -> 501 / 495 (15.3 s).
  FINDING for Daniel: mirror matches stall. The Asymptote mirror reference
  battle went from ~100 turns to 488 (cap 500): shots fired in only 55 of 488
  turns, up to 33 turns in a row with none; it ended on a head hit. Equal
  future damage on both sides means each fights only when this turn's trade
  beats 1:1, so neither commits. That one battle makes run_checks.py take
  ~12 min (was ~1.5). Options for Daniel: an anti-stall rule, or a turn cap
  for that reference battle.

- **2026-10-21 (Claude):** Time tracker (Daniel: "put a tracker on them to see
  where they're spending their time. We still need more speed"). New
  `INTEGRATION__timing.py`: `timing.section(name)` timers that nest (movement >
  picking a spot > two-ply look-ahead > reply scoring ...), each battle's
  totals carried back on `BattleResult.timing` (parallel workers included),
  and a "WHERE THE TIME WENT" table after every batch and in
  `tests/benchmark_turns.py`. `config.TIMING` (default True),
  `config.PROFILE_FUNCTIONS` = N lists the top N functions by own time
  (cProfile, ~2x slower; `BattleResult.profile`). Sections in the orchestrator
  (movement, ranged, physical, heat, end), movement_selection (reachable
  spots, scoring vs the enemy where it stands, future damage, two-ply, reply
  scoring, reply charges / DFA, charges / DFA) and attack_resolution
  (choosing weapons, resolving hits). The reference battles and the tests
  that compare printed output switch TIMING off. No result changes
  (benchmark 477 / 468). First reading (benchmark, ratio objective): the
  two-ply look-ahead is ~97% of the time - reply scoring ~74%, the per-reply
  candidate loop ~18%, reply charges / DFA ~5%; ranged, physical, heat and End
  Phase together under 0.2%.

- **2026-10-21 (Claude):** A/B batches for the history blend (same seeds as
  the ratio / lifetime batches below). Kontio vs Hammerhead, 100: lifetime +
  history K=3 Kontio 58 / Hammerhead 41 / draw 1 (ratio 59 / 39 / 2, plain
  lifetime 68 / 32 / 0), 19.3 turns (12.8 / 23.9), 13 off-board deaths
  (45 / 12); K=1: 55 / 45 / 0, 20.4 turns, 15 off-board - K 1 vs 3 is within
  the dice noise. Atlas AS7-K vs Archer ARC-2R, 40: 37 / 3 / 0, 15.8 turns
  (ratio 11.1, lifetime 21.7), same winner as ratio on 37 of 40. Cataphract
  CTF-3D vs Emperor EMP-6D: 3 / 37, 19.0 turns (12.4 / 24.6), same winner 34
  of 40. Replays, seed 766213648170853994 (pushed off turn 8 under ratio, wins
  turn 16 with history): https://claude.ai/artifact/C1ZBQWqzZmAnkp3tJfun5w
  (ratio), https://claude.ai/artifact/44yfKRLbr1XDTatWiBDCX9 (history K=3).
  Waiting on Daniel: make lifetime + history K=3 the default?

- **2026-10-21 (Claude):** History blend for the lifetime objective (Daniel:
  "We can't predict the future. But we can record the past"; "go with History
  blended K for now"; no destruction filter - "Works for pushes. Doesn't work
  elsewhere"; "I'm willing for a desperate mech to take chances later in the
  match"). `config.MOVEMENT_LIFETIME_HISTORY_K` (None = off): each future
  damage per turn = (K x estimate + damage really done) / (K + turns fought).
  The orchestrator records each mech's effective HP at deployment and every
  End Phase (`movement_selection.record_hp`, `mech.hp_log`); damage done =
  the other mech's real HP loss (falls and explosions included); turns fought
  start at the first turn either mech lost HP (`battle_record`). New check
  `history_blend_math`. Default unchanged (ratio; K None): reference logs
  match, benchmark 477 / 468.

- **2026-10-21 (Claude):** A/B batches, MOVEMENT_OBJECTIVE "ratio" vs
  "lifetime", same seeds (12345 batches), after the LOS and booster fixes. No
  code change. Kontio vs Hammerhead, 100 each: ratio Kontio 59 / Hammerhead
  39 / draw 2, 12.8 turns, 45 off-board deaths; lifetime 68 / 32 / 0, 23.9
  turns, 12 off-board deaths; same winner on 56 of 100. The Hammerhead's
  hits per turn halve (0.51 -> 0.26): its fight-or-not bar (my future / the
  enemy's future, ~0.6 against the faster, stealthier Kontio) is rarely met,
  so it backs off - but the Kontio reaches it anyway and shoots its back.
  Atlas AS7-K vs Archer ARC-2R, 40 each: 38 / 1 / 1 vs 37 / 3 / 0, 11.1 ->
  21.7 turns, same winner 35 of 40. Cataphract CTF-3D vs Emperor EMP-6D: 3 /
  37 both, 12.4 -> 24.6 turns, same winner 34 of 40. Replays of seed
  6507740548082236446 (Hammerhead wins turn 19 under ratio, dies turn 4
  under lifetime): https://claude.ai/artifact/7bjL7ePCNvjvWtF7dHb2M9 (ratio),
  https://claude.ai/artifact/5aWrPwb9mXCLkznRnpZaHV (lifetime). Waiting on
  Daniel: keep / adjust / drop the lifetime option.

- **2026-10-20 (Claude):** The two-ply look-ahead models MASC / supercharger
  speed. The modeled second mover's moves were built before its booster roll
  (Running MP x1.5), so a supercharged Kontio was predicted to run 9 and
  really ran 12 to push the Hammerhead off the board (A/B seed
  3486141480966086336, turn 3). New `equipment_systems.boost_multiplier`
  (the bot's own use decision without the stub warning, the 3+ roll counted
  as a success) and `modeled_boost`; `movement_selection._opponent_options`
  builds the reply's moves at that speed (the rule Daniel set: the reply is
  chosen "by the same rule the real second mover uses"), and
  `future_damage.best_tmm` counts a working booster (BEST TMM). Affects both
  objectives. Reference log `Asymptote_vs_HeatGear_seed5` regenerated (its
  test mech has MASC + a supercharger); benchmark unchanged (477 / 468).

- **2026-10-20 (Claude):** LOS between two hexes (Core p.56: "If LOS falls
  exactly on the line between two hexes, the target 'Mech's controller
  chooses which hex LOS passes through"). Two bugs in `pathfinder/los.py`,
  found when an A/B batch crashed (Atlas AS7-K vs Archer ARC-2R: "Intervening
  LOS hex (5, 1) is not on the loaded board"): (1) the edge test rounded both
  tied cube coordinates with Python's round-half-to-even, which often sent
  both to the SAME hex, so the second hex of a hexside line was missed - its
  woods / blocking terrain ignored (`_cube_round_candidates` now rounds the
  point nudged a hair to each side); (2) along the board edge one of the two
  hexes is off the board - the line now passes through the on-board one
  (Claude's reading of p.56: there is no off-board hex to choose) instead of
  raising. Every one of the 73,712 hex pairs on the 16x17 board now traces
  (24,120 have a two-hex step). Before, movement scoring silently skipped the
  spots that raised; a battle that reached one in the Ranged phase crashed.
  Reference logs regenerated (intended: fewer "spots with LOS" where the
  missed hex had woods); benchmark 458 / 466 -> 477 / 468.

- **2026-10-20 (Claude):** Movement objective option "lifetime" (Daniel's
  design, Section 5 "Movement objective option"). New
  `INTEGRATION__future_damage.py` (future damage per turn; `best_tmm` reads
  Running / Jumping MP without compute_tmm's side effect);
  `movement_selection._Ratio` / `_Lifetime` objects, one per side per pick
  (`_link`), used by the static scores, the two-ply and its modeled reply, and
  the charge / DFA scoring; `effective_hp` = armor + rear + k x structure.
  Config `MOVEMENT_OBJECTIVE` ("ratio" default), `MOVEMENT_LIFETIME_INITIATIVE`,
  `MOVEMENT_LIFETIME_ATTACKER_MODE`, `MOVEMENT_LIFETIME_FUTURE_FLOOR`. Three new
  checks in `tests/test_movement_selection.py`. Default unchanged: reference
  logs match, benchmark 458 / 466.

- **2026-10-20 (Claude):** Battle replays (Daniel: "build outputs both text
  and visual you can share from battles you run so I can see whats going on
  without me having to download the current version and run it myself").
  New `INTEGRATION__replay.py` (recorder + page writer) and
  `INTEGRATION__replay_viewer.html` (the page: hex map, record sheets, step
  log; no libraries). `config.REPLAY_BATTLES` / `REPLAY_DIR`;
  `config.set_log_sink` lets the recorder copy every log line, VERBOSE or
  not; `orchestrator.run_battle` marks the steps; `BattleResult.replay` carries
  the data back from parallel workers and `run_batch` writes the pages.
  Seeds are stored as text (they pass JavaScript's exact-integer limit). New
  `tests/test_replay.py` (recording changes nothing; step structure; page
  data round-trips). Default off: no result changes, benchmark 458 / 466.
  Also logged the movement-objective finding (Section 4, Pick up here 0).

- **2026-10-20 (Claude):** Actuator Enhancement System, Core p.206 (Daniel:
  "if AES is the only thing not built in this test, lets get that fixed").
  `mech_state.arm_aes_working` / `leg_aes_working` (cached per mech, refreshed
  on a crit): leg AES -2 in `piloting_rolls.special_case_modifier`, -1 to
  kicks (`physical._kick_options`) and charges (`charge.to_hit`, shown in the
  charge log line); arm AES -1 to that arm's ranged weapons
  (`attack_resolution.arm_aes_modifier`, in `tn_adjuster`, so movement
  scoring sees it too; split arm / torso weapons excluded) and its punches,
  claws and physical weapons; clubs and pushes -1 only with AES in both arms.
  Crits: any leg AES slot hit ends the leg effects; an arm only its own.
  DFA isn't named by p.206, so no change there. Tests: two new checks in
  `tests/test_equipment.py` (Hammerhead legs; Vindicator VND-3LD (Dao) arms).
  Reference logs regenerated: only the known-missing-rules AES line goes
  (the default battle ends on turn 1, before any PSR). Benchmark unchanged
  (458 / 466). Hardened armor checked against p.202 at the same time - all
  four effects were already built (2 points per pip, -2 TAC while armor
  remains, +1 PSR, -1 Running MP).

- **2026-10-20 (Claude):** New default matchup (Daniel: "Asymptote is an
  uninteresting match"; "kontio vs hammerhead ... Because its the example in
  the game's starter set"). `data/Kontio.mtf` and `data/Hammerhead.mtf`
  (from `meks.zip`, RG21 / RG05 - the only version of each) are
  `MECH_RED_MTF` / `MECH_BLUE_MTF`. Every gear item fires or applies except
  the Hammerhead's leg AES (not built - Section 4, and a new line in the
  report's known-missing rules). New reference battle
  `Kontio_vs_Hammerhead_seed12345` (the Kontio runs behind the Hammerhead on
  turn 1 and burns through its 5-point rear CT). The Asymptote reference
  battles and the benchmark now name the Asymptote explicitly (four
  scenarios had left Red to the default). Reference logs regenerated: the
  only change to the old ones is the AES line. Benchmark unchanged (458 / 466).

- **2026-10-20 (Claude):** One-command baseline (Daniel: "probably need to
  establish a briefer way to get a clean baseline. I sense that test bloat
  has taken hold."). New `tests/run_checks.py`: every test file and every
  reference battle run side by side (one per CPU core), one line each, a
  one-line verdict, `--bench` adds the benchmark. `check_reference_logs.py`
  runs its battles side by side too (its `compare` is shared). Cloud
  container: ~5 min one at a time -> ~1.6 min. No checks removed, no result
  changes (logs regenerate byte-identical; benchmark 458 / 466).

- **2026-10-20 (Claude):** Session 3 wrap-up (Daniel: "Good pass. Clean
  up."). Section 0 rewritten for the next instance; Section 4 "Known issues to
  fix later" (scatter vs firing arc; MG array ammo check); Section 5 session-3
  decisions; Section 7 three standing notes. Dead code removed
  (`fire_modes.mml_size`, `weapon_rules.is_laser_ams`). No result changes.

- **2026-10-20 (Claude):** Non-functional weapons (Daniel: "Fixing non
  functional weapons just became top priority"; review F18-F20). New
  `INTEGRATION__weapon_profiles.py`, read by `fire_modes`: variable damage by
  bracket (heavy Gauss 25/20/10, Snub-Nose PPC 10/8/5, VSP 5/4/3, 9/7/5,
  11/9/7 - Daniel), HAG (C5 on the 20/30/40 column, +2 short / -2 long),
  M-pods (15/10/5 column, C1), machine gun arrays (p.185: +2, the guns'
  column, one location; guns linked per location), bombast lasers (8/12/16
  at +0/+1/+2, heat 6/9/12 - a munition-stub choice), rifles (-3 vs 'Mechs),
  flamer / plasma heat on the target (`heat.resolve_heat_phase` outside
  heat, cap 15, p.102), Arrow IV (hex attack 7-17 hexes, Gunnery + 4, 20 AE,
  scatter MOF/2, 10 next door) and artillery cannons (AE, no immobile -4,
  scatter, Long Tom splash 10). Apollo saturation mode (Daniel's hex-attack
  ruling: `Planner(hex_offset=)` drops the target's TMM / immobile / prone /
  Void modifiers). MML LRM grouping 5 (Daniel: table typo). New optional
  rule `POOL_CLUSTER_DAMAGE` (default True, Daniel): an attacker's cluster
  damage of one grouping size (and damage type) is summed per phase, then
  grouped. New knob `TARGET_HEAT_WORTH` (placeholder 0.5). equipment.json:
  Clan flamers, plasma rifle / cannon, M-pod, B-pod, Snub-Nose PPC type,
  heavy MGA rows filled; IS MGA, three rifles, rifle ammo, bombast laser,
  Clan Arrow IV (12 slots; IS 15) added; artillery cannon damage / slots;
  chemical laser shots per ton (ammo now used). Ammo: Arrow IV standard bins
  feed; glued "...Ammo" names. 617 units had a Core weapon that couldn't
  fire; now only non-Core weapons are left (TSEMP, iATM, mortars,
  full-size artillery, fluid gun...). New `tests/test_weapons.py` (12
  checks); new reference battles `Bombardier_BMB-14K_vs_Black_Hawk_F_seed4`,
  `Bombardier_BMB-05A_vs_Cataphract_CTF-3LL_seed4`. Reference logs
  regenerated (pooled cluster damage changes missile battles; banner text).
  Benchmark unchanged (458 / 466).

- **2026-10-20 (Claude):** Weapon-use options with stub decisions (Daniel:
  "Work on including the functionality of choice, but use a stub for the
  actual decision"; review F14-F15). New `INTEGRATION__fire_modes.py`:
  Ultra (1-2) / Rotary (1-6) AC rapid fire (pp.182-183: heat and ammo per
  shot, one attack roll, Cluster Hits on the shots column, each shot its own
  location; no aimed rapid fire); Rotary jams (2-3 shots on 2, 4-5 on 3-, 6
  on 4-) and unjamming (declared in the Movement Phase - stand still / walk
  only - Gunnery + 3 at the end of the Ranged phase); LB-X cluster rounds
  (p.192: -1, rating column, 1-point pellets, no TC); ATM ER / HE and MML
  LRM / SRM ammunition (pp.186, 250, 252: damage, ranges, groupings, MML
  shots per ton); Apollo standard-fire mode (p.197, linked like Artemis:
  no MRM -1). `ShotPlan` per shot (`DeclaredAttack.fire`) wraps the
  electronics guidance; `Planner` prices special weapons for the knapsack
  (`weapon_selection` `planner=`, replacing the AMS / fire-control value
  factors and `bonus_per_hit`) and movement scoring, and makes the decision
  at declaration. New stubs (all loud at the decision): `munition_choice`,
  `rate_of_fire`, `unjam`, `escalating_use` (MASC / supercharger / radical,
  `equipment_systems.use_escalating`; default = Daniel's cycle, results
  unchanged). Ammo: `parse_bin` returns (weapon, munition, kind); LB-X
  cluster / ATM ER-HE / MML bins now feed their weapons; " - Half" bins hold
  half; `take` draws a chosen kind. Data: IS machine gun (p.248) and IS MG
  ammo rows added - IS machine guns never fired; "(Split)" crit lines are
  read. `heat.max_weapon_heat` counts full rapid fire. Tests:
  `tests/test_fire_modes.py` (10 checks), `test_ams` / `test_electronics`
  moved to the Planner API. New reference battles
  `Cataphract_CTF-3D_vs_Emperor_EMP-6D_seed1.txt`,
  `Akuma_AKU-2XK_vs_Highlander_IIC_2_seed1.txt` (units copied into `data/`).
  Reference logs regenerated: outcomes unchanged except where these rules
  act; the rest only log text (stub lines, the summary banner, split heavy
  Gauss now one weapon that can't fire yet). Benchmark unchanged (458 / 466).

- **2026-10-20 (Claude):** Weapon slot counts (review F16). equipment.json
  listed many multi-slot weapons with too few slots (every Ultra / Rotary /
  LB-X AC, ATM, MRM, MML, Streak LRM, heavy / VSP / X-pulse lasers, HAG,
  heavy Gauss...) and some Clan ones with the IS count (Clan ER large laser,
  ER PPC, LRMs, SRM 6). The parser groups crit lines by that count, so a
  5-slot Ultra AC/5 became five Ultra AC/5s and two adjacent Clan ER large
  lasers one. 103 rows fixed from the Core tables (pp.248-254, cited per
  row), 11 non-Core rows from the MegaMek files' crit-line runs; 1,893 of
  4,162 units had a wrong weapon count. `mtf_parser._join_split_items`: a
  weapon split between two locations is one item.

- **2026-10-20 (Claude):** Artemis, Narc and ECM (Daniel: "Artemis and Narc.
  Since they both affect Missiles and are affected by ECM in similar ways";
  review F11-F13). New `INTEGRATION__electronics.py`: Artemis IV / V FCS
  linked to launchers (p.197: +2 Cluster; V -1 to hit, +3; needs the
  matching Artemis-equipped missiles; ATM built-in +2, p.186); Narc / iNarc
  beacons (pp.188, 193: homing pods by location roll, working from the next
  phase, -1 / +2 for Narc-capable missiles, lost with the location;
  explosive pods 4 / 6); ECM (p.200: an enemy's working Guardian / Clan /
  Angel / Watchdog blocks Artemis and the pods; Angel unlocks Streaks;
  off when shut down or with a stealth system other than the LPS, p.209;
  stealth armor / Void-Signature jam their own mech's Artemis, pp.202, 209).
  `FireControl` per shot (`DeclaredAttack.fire`) carries the munition and
  bonuses into to-hit (`tn_adjuster`), resolution, the AMS (`ams.
  expected_damage_engaged` / `damage_factors` take it) and movement scoring
  (`MoveEvaluator` - same factors). Pod value per Daniel (Section 6, readings
  in Section 4); AMS engages pods for half of it. **Ammo-bin fix** (F10):
  `ammo.parse_bin` reads the munition off the bin name and finds the weapon
  via the bin's equipment.json ammo row - 1,541 units had bins that fed
  nothing (Gauss, AC/x, Artemis- / Narc-capable, Narc pods), so those
  weapons never fired; half-ton "(100)" bins hold their own count;
  `ammo.take` draws a chosen munition. `weapon_selection` gains
  `bonus_per_hit` (the beacon's worth). Data fixes (equipment.json):
  Narc / iNarc beacons damage 0 (was null, so they never fired), IS Narc 2
  slots, iNarc 3, Artemis V 2, Guardian / Angel / Watchdog 2 (p.250-254;
  each 2-slot item had parsed as two). `tests/test_equipment.py` updated
  (one Guardian instance, not two). New `tests/test_electronics.py` (10
  checks); new reference battles `Kintaro_KTO-19_vs_Atlas_AS7-K_seed2.txt`
  and `Atlas_AS7-S2_vs_Kintaro_KTO-19_seed1.txt` (units copied into
  `data/`). Reference logs regenerated: the Atlas AS7-K battle changed for
  real (its Gauss rifle fires now and it wins); the Asymptote logs only by
  the summary banner's known-missing-rules text. Benchmark unchanged
  (458 / 466).

- **2026-10-20 (Claude):** Anti-Missile Systems (Core p.206; review G13 ->
  F9), Daniel: "AMS functionality will be implemented". New
  `INTEGRATION__ams.py`: once both sides have declared, each defender's live
  AMS engage the missile (Type M) hits on it from inside their location's
  firing arc (INTEGRATION__arcs, with the declared twist / flip), at most 2
  per AMS per turn, one AMS per attack; 1 ammo + 1 heat each (laser AMS: no
  ammo, 7 heat IS / 5 Clan), the heat added to the defender's weapon heat;
  not while shut down (p.104) or with the whole crew unconscious.
  Resolution (`attack_resolution._resolve_one_attack`, `DeclaredAttack.ams`):
  the Cluster roll takes -4 on top of the weapon's own modifier and a
  result below 2 destroys every missile; an engaged Streak counts as a 7; a
  single missile (Thunderbolt) is destroyed on 1D6 4+. An AMS no longer
  fires as a 2-damage, range-1 weapon (`weapon_selection` leaves it off the
  table; the closing fallback and the prone prop-arm choice ignore it).
  Expected damage: `ams.damage_factors` (value_scale) in the Ranged-phase
  weapon choice and in `ranged_combat.MoveEvaluator` (scorers and best-twist
  memos keyed by the engagements the other side's AMS can make from that
  spot - `ams.Coverage`). Bot choices in Section 6; readings for Daniel in
  Section 4 ("AMS readings"); new knob `config.AMS_HEAT_LIMIT` (13). Data
  fix: equipment.json IS laser AMS takes 2 critical slots (p.250), not 1 -
  units with one had two separate laser AMS. New `tests/test_ams.py` (10
  checks); new reference battle `Atlas_AS7-K_vs_Archer_ARC-2R_seed2.txt`
  (both units copied from `data/meks.zip` into `data/`). The other reference
  logs and the benchmark (458 / 466) are unchanged - none of those mechs
  carries an AMS.

- **2026-10-20 (Claude):** Rules review, first pass complete
  (`INTEGRATION__RULES_REVIEW.md`: Playing the Game, the rest of Combat,
  Weapons and Equipment, The Battlefield). Fixed: an autocannon's first
  critical hit no longer destroys it (Core p.183; `damage_resolution.
  is_autocannon` / `_autocannon_shrugs_off` - the slot is used up, a second
  crit to another slot destroys it); internal explosions (p.96) - ammo bins
  now carry the UNCAPPED base damage (`INTEGRATION__ammo._update_explosion`,
  shots x Damage Value), and `apply_explosion` applies the 20 cap, strips the
  armor (torso: rear) of the location that took the 20th point when the base
  was over 20, vents CASE / CASE II excess into the (rear) armor up to 10, and
  gives CASE II's explosion crit checks -1. New gaps listed: AMS (G13),
  armored components (G14), ECM (G15). Tests: `test_rules.py`
  (autocannon_first_critical, explosions_and_case; ammunition updated).
  Reference logs regenerated (explosion log wording and the uncapped base
  damage in the log line; no battle outcome changed).

- **2026-10-20 (Claude):** Daniel's calls on rules review D1-D7 (Section 5).
  New OPTIONAL RULES section in `INTEGRATION__config.py`:
  `FLOATING_CRITICALS` (default True; False = the standard Through-Armor
  Critical, Core p.91: damage stays on the torso the 2 hit, plus one crit
  check there, following the damage transfer if that torso is gone) and
  `FIGHT_TO_THE_DEATH` (default False = Daniel's rule, a mech rendered
  immobile for good - destroyed gyro, both legs - is destroyed; True = rules
  as written: a destroyed gyro falls and can't stand (p.98), both legs gone
  is immobile (pp.49, 90; `mech_state.is_immobile` now includes it), and an
  immobile mech with no ranged weapons is destroyed (p.99); a prone mech that
  can't stand turns toward the enemy - `orchestrator._turn_while_down`, one
  hexside a turn with a destroyed gyro). Rules as written now
  (`mechsim/piloting_rolls.py`): one PSR per trigger at the sum of all the
  phase's modifiers, stopping at the first failure, one per leg (p.110;
  `roll_psrs`, `movement_psr_count` - movement scoring prices 1 - P^rolls);
  seatbelt check at Piloting + levels fallen only, automatic hit when
  immobile or over 12 (p.117); falls roll 1D6 for the side, 1 = rear (p.115).
  `resolve_fall` lost its `seatbelt_modifier` argument; `can_stand` (pp.51,
  98). Tests in `tests/test_rules.py` (5 checks). RESULT CHANGE: two
  reference logs regenerated (falls).

- **2026-10-20 (Claude):** Backward walking (Core pp.45-46, TMM p.63;
  rules review G1). `pathfinder.build_movement_table(backward_mp=...)`: a
  walking mech may step into the hex directly behind it, facing unchanged,
  same entry cost; a path that has moved backward never spends more than
  Walking MP (only walking mechs move backward); the forward count (TMM)
  restarts at 1 when the mech reverses direction. The search state carries
  (last direction, moved backward yet); without backward_mp the table is
  exactly as before. `ranged_combat.movement_options(backward=True)` passes
  Walking MP (not after standing up, not when entering the board); the charge
  index uses forward-only states. Same-level backward steps only - a backward
  level change needs a mid-move PSR the scoring can't price yet (review G11).
  The battle log marks moves that need a backward step (VERBOSE only). Test 9
  in `tests/test_pathfinder.py`. RESULT CHANGE: reference logs regenerated.
  Benchmark 17.1 s (the Asymptote gains ~30 end states at Walking MP 3).

- **2026-10-20 (Claude):** Rules review, first pass - new
  `INTEGRATION__RULES_REVIEW.md` (Core Rulebook vs code: fixed items, gaps,
  and Core-vs-project-rule questions for Daniel, all page-cited). Fixed: the
  target-in-woods to-hit modifier (+1 light / +2 heavy, Core p.66 / pp.68-69)
  was missing - added to the LOS result in `pathfinder/los.py`, so every attack
  and the movement scoring see it (DFA ignores terrain as before); partial
  cover was stored one step before the trace's last step that aimed shots and
  charges read (always 0); partial cover could come from the attacker's own
  hex at range 1 (p.57); an ordinary leg hit on a target in partial cover now
  strikes the cover (pp.66, 73); a floating-critical re-roll onto the Head now
  costs the pilot a hit (p.117). Tests in `tests/test_rules.py`. RESULT
  CHANGE: all five reference logs regenerated - the woods modifier changes
  where mechs stand (the default board has 30 woods hexes). Benchmark battle
  changed too (HP 458 / 466).

- **2026-10-20 (Claude):** Speed pass 2 (Pile 1 batch loop + Pile 4 movement
  scoring; no rules touched). (1) **Parallel batches**: `run_batch` runs
  `config.WORKERS` battles at once (0 = one per CPU core, the default; 1 = one
  after another; MANUAL_ROLLS always 1). Each battle now has its OWN seed
  (`orchestrator.battle_seed`: battle 1 = SEED, later battles a SeedSequence
  mix of (SEED, battle number)) instead of one dice stream shared by the
  whole batch, so a battle's dice don't depend on which battles ran before
  it. Workers capture their logs and the parent prints them in battle order,
  so the output is byte-identical for any worker count
  (`tests/test_parallel_batch.py`). `BattleResult.seed` records each
  battle's seed (SEED = it, NUM_SIMULATIONS = 1 replays that battle).
  RESULT CHANGE, batches only: battles 2+ of a batch differ from before
  (different dice, same statistics); one-battle runs and every reference log
  are unchanged. 4 cores here: an 8-battle batch went 78 s → 26 s.
  (2) **Memo sharing in `ranged_combat.MoveEvaluator`**: the best-twist memo is
  keyed on the set of arc keys a spot sees (`_ArcClasses`) instead of the
  exact geometry, and heat-limited scorers are shared by every (arc key,
  held weapons) that blocks the same weapons. The knapsack runs went
  246k → 32k on the benchmark. `MovementCandidate` uses slots; the spot-free
  parts of each pre_tn are added once per call. Results identical (reference
  logs match, benchmark HP 460 / 450); benchmark 21.5 s → 16.3 s in this
  container. Also measured: the LOS traces (~15% of a cold benchmark) are
  cached per board for the life of a worker, so they amortize in a batch.
  Language switch deferred (Daniel agreed: get it right in Python first).

- **2026-10-20 (Claude):** Club pick-up switched OFF (`config.CLUB_PICKUP =
  False`, Daniel) - the rules stay; the decision waits for the
  future-capability Memo (Section 6). Section 0 rewritten as a hand-off for a
  new instance; `CLAUDE.md` added (points here); `tests/benchmark_turns.py`
  added (the fixed 10-turn speed benchmark). Two reference logs regenerated
  (Asymptote vs HeatGear seeds 2 and 5: the Asymptote had picked up a tree,
  and holding it changed its later movement scores; it never clubbed).

- **2026-10-20 (Claude):** The remaining physical attacks and anticipation.
  New `INTEGRATION__movement_attacks.py` (target poses, a once-per-decision
  index of the mover's reachable states, charge / DFA options and values incl.
  displacement worth, the gate and scoring - used by the second mover's pick
  AND the first mover's two-ply reply), `INTEGRATION__dfa.py` (pp.79-80:
  Punch-table hit, Kick-table self-damage, landing, p.80 displacement order,
  a miss = 2-level rear fall), pushes in `INTEGRATION__physical.py` (p.83,
  valued by displacement; mutual pushes; prohibited hexes),
  `INTEGRATION__clubs.py` (p.79: trees in woods / jungle, girders in rubble,
  severed limbs left in their hex - `damage_resolution` records
  `severed_limbs`; holding needs both hands / shoulders; club attacks in
  `physical._club_options`, a PSR for the target, a tree breaks after one
  hit, dropped on hand / shoulder damage). `piloting_rolls.resolve_fall`
  takes `side`. `MoveEvaluator.evaluate(physical_reply=False)` for a mech in
  the air. `config.DFA` switches DFAs off. `tests/test_charge.py` became
  `tests/test_special_attacks.py` (20 checks). Default battle ~1.45 s a turn.
  Reference logs regenerated (pushes' threat moves mechs off board edges).

- **2026-10-20 (Claude):** Charge attacks (Core p.78; displacement pp.113-114;
  falls p.115). New `INTEGRATION__charge.py`: who can be charged (standing,
  finished moving or immobile - the second mover's option), the charge states
  (adjacent, facing, MP left to enter; TMM counts the target's hex), the gate
  and score in `movement_selection._charge_pick`, no ranged fire for the
  charger, resolution in the Physical phase (comparative Piloting, partial
  cover ignored, ceil(tons/5 x (TMM+1)) / ceil(target tons/10) in 5-point
  groups, displacement - off board destroyed, 3+ up prohibited, 2+ down an
  automatic fall - then +2 PSRs; cancelled if the target fell / was destroyed
  or TN 13+, a miss if the charger fell). `piloting_rolls.resolve_fall` takes
  `levels` (x(levels+1) damage). `config.CHARGES` switches it off. New
  `tests/test_special_attacks.py` (10 checks; a Charger CGR-1A1 vs Atlas AS7-D battle
  charges). Not modeled: charge PSRs / displacement in the score, the first
  mover anticipating a charge, domino effects, buildings, water, lance /
  spikes / shields.
- **2026-10-20 (Claude):** Physical attacks weighted by their hit table
  (`physical.Worth`, `structure_weight.hit_spread(rolls=)`, `vulnerability`,
  `spread_worth`): a kick at stripped legs or a punch at a thin upper body /
  head counts for more, in movement scoring and the Physical phase.
- **2026-10-20 (Claude):** Speed: 31.7 s -> 11.8 s for the default battle's
  first 10 turns (seed 12345), identical results - the heat-limited scorer
  passes its weapon list / damage table to select_weapons_to_fire, the
  evaluator memoizes the best-twist ranged value, physical scoring collapses
  identical arc actions and stops at the first plan that can't win.
  Physical attacks were NOT folded into the weapon list: profiling showed the
  physical layer at ~20% before / ~4% after these changes, and a combined
  list would need a second to-hit axis (Piloting) in the weapon tables.
- **2026-10-20 (Claude):** `data/meks.zip`: 4,227 MegaMek `.mtf` units (Daniel's
  upload); 4,162 parse (ultralights < 20 t, superheavies, LAMs don't).

- **2026-10-19 (Claude):** Physical attacks in the movement picker and the
  Ranged-phase twist (Daniel: "add physical attacks to the location picker,
  which may affect the ranged phase twist"). Spots next to the enemy now
  score the best arc action x physical plan (punch with one / both arms,
  kick, physical weapon) as ranged fire without that limb's weapons + the
  plan's expected damage, for both the mover and the enemy's reply
  (`ranged_combat._with_physical`, `physical.Planner`). The Ranged phase makes
  the same joint choice, so it twists for a punch and holds back an arm
  weapon worth less than that arm's punch; the Physical phase re-picks after.
  `physical.options_at` / `base_tn` / `plans` take explicit positions.
  Not counted: structure weighting of physical damage, kick PSR falls,
  charges / DFA / pushes / clubs (not built). Reference logs regenerated.

- **2026-10-19 (Claude):** Reference logs regenerated (`--update`, Daniel's
  go-ahead) - they now reflect movement selection, firing arcs and arc actions.

- **2026-10-19 (Claude):** Arc actions - the rest of the torso-twist rules
  (Core pp.61-62, 76, 205, 236-238). `INTEGRATION__arcs.ArcAction(twist, flip,
  turret)` replaces the bare twist: tripods twist to any hexside and their leg
  weapons use the p.236 leg arcs; arms reverse for designs with no hand / lower
  arm actuators in both arms and no split arm weapon; Quad Turret "(T)" weapons
  turn freely, a turret crit locks it; one twist OR flip a turn, kept for the
  rest of the turn and reset in the End Phase. The Physical Attack Phase now
  uses `arcs.arcs_between` with the twist (punches / arm weapons follow it,
  kicks don't, tripods only attack into the torso's forward arc, reversed arms
  can't punch) and may twist there if the Ranged phase didn't.
  `arc_unavailable(attacker, key)` now takes an `arcs.ArcKey`;
  `arc_keys(arcs, facing, actions, legs)` returns (key, action) pairs.
  New `tests/test_arcs.py` (10 checks). Reference logs differ again (the
  default tripods now twist further).

- **2026-10-19 (Claude):** Firing arcs and torso twists (Core pp.60-62), from
  Daniel's Firing Arcs Diagram screenshot. New `INTEGRATION__arcs.py`: the arc
  a target is in = angle of the centre-to-centre line from the attacker's
  facing (forward within 60 deg, side 60-120, rear beyond 120; boundary hexes
  go to the non-rear arc - all 15 hexes labelled on the diagram reproduce).
  **The rear arc is now 120 deg, replacing the 60-deg single-hexside rule of
  2026-07-20** (identical at range 1). Weapons by arc: forward = all but
  rear-mounted; side = that side's arm weapons (split torso/arm weapons are
  forward-only); rear = rear-mounted only. Torso twist (one hexside, none for
  prone/quad): shifts head/torso/arm weapon arcs, not legs, facing or how the
  mech is hit; the attack phase picks the twist with the most expected damage
  (`attacker.torso_twist`), and movement scoring takes each side's best twist.
  `los_cache` now caches the 6-facing arcs tuple (was a direction facing);
  `arc_unavailable(attacker, torso_arc, legs_forward)` replaces the rear-arc
  boolean. Not modeled: reversing arms, tripod leg arcs and any-hexside tripod
  twists, turrets, twist -> Physical Attack Phase. Reference logs differ again.
  Cost: roughly 1.5-2x per turn (~1.1 s) from scoring up to 3 twists per side.
- **2026-10-19 (Claude):** Structure-damage weighting for movement scoring
  (Daniel's design: per weapon x hit-location table, no chaining). New
  `INTEGRATION__structure_weight.py`: for each weapon (cluster weapons per
  grouping), each hit-table roll on the attack side counts the part of a hit
  that gets past armor into structure at `config.MOVEMENT_STRUCTURE_WEIGHT`
  (default 2.0; 1.0 = off, identical to before) and anything transferred past
  a destroyed location at 1.0. `weapon_selection.select_weapons_to_fire` takes
  an optional `value_scale` (used by movement scoring only; the attack phase is
  untouched); `MoveEvaluator` builds per-side multipliers for both mechs, so
  `dealt`/`received` are now WORTH. `_vulnerability` (exposure) shares the
  table walk (`hit_spread`). Exposure and structure weighting overlap a
  little (thin armor raises both); both stay on. 16 tests; ~16 s per battle.
- **2026-10-19 (Claude):** Void-Signature fix to movement selection: its TN
  bonus falls as hexes moved rise (+3 / +2 / +1 / 0), so the Section 5c
  reduction (keep max hexes moved) is unsafe for it. `reduced_options` now
  keeps every (forward count, MP) variant for a mech with a live Void-
  Signature System (Daniel's call); new test. Logged as open (Daniel, not yet
  built): (1) terrain that forces a PSR on entry and mine fields should add
  expected damage to the movement cost like the movement PSR does; (2)
  internal-structure damage should count for more than armor damage in the
  objective (Daniel suggested ~2x, value to be picked).
- **2026-10-19 (Claude):** Movement selection built (replaces
  `stub_select_movement`). New `INTEGRATION__movement_selection.py` and
  `INTEGRATION__los_cache.py` (compute-once LOS / entry-direction / distance
  cache); `ranged_combat` gained `MoveEvaluator` (pinned-position scoring that
  reuses weapon scorers; `evaluate_going_second` is now a wrapper, output
  byte-identical on 5 reference logs before wiring); `piloting_rolls` gained
  `movement_psr_trigger`, `movement_psr_target_number`, `fall_damage`.
  Daniel's decisions: objective = dealt / (received + .001); two-ply so both
  sides move intelligently; closing fallback ported as-is; armor-exposure
  weighting by actual hit direction; movement-phase PSR expected damage added
  to the denominator (damage-caused PSRs ignored); dropping `compute_score`'s
  HP-awareness is fine for now. Known limits: ratio ignores damage state
  (epsilon dominance by tiny-damage/no-return-fire spots), seatbelt/prone PSR
  aftermath unscored, tripod exposure uses the raw hit table, prone/immobile
  enemy modeled as staying put, modeled replies greedy not adversarial.
  New tests in `tests/test_movement_selection.py` (14 checks). ~15 s per
  40-turn battle. Reference logs differ by design - NOT updated.
- **2026-08-28 (Claude):** Consolidated `INTEGRATION__PROJECT_MAP.md` +
  both source projects' project maps/design notes/call graphs/change-record
  archives into this single doc. No code touched.
- **2026-08-30 (Daniel):** Resolved Pile 1 reconciliation — `combat_turn.py`
  / `sim_runner.py` cannibalized into the orchestrator then deleted from
  this project (source projects unaffected).
- **2026-08-30 (Claude):** Built `INTEGRATION__orchestrator.py` skeleton —
  map loading, RNG wiring, config attachment, initiative, Section-2 turn
  loop with Movement/Ranged as stubs, End Phase wired, `run_batch()`.
- **2026-08-31 (Daniel):** Confirmed initiative procedure — both sides
  roll 2d6, both reroll on ties, high roll wins and moves second.
- **2026-08-31 (Claude):** Wired confirmed initiative; wired damage-aware
  MP into `_phase_movement()` via `_compute_available_mp()`.
- **2026-09-02 / 09-05 (Claude):** Movement envelope
  (`_build_movement_envelope`); `INTEGRATION__ranged_combat.evaluate_going_second()`
  (unreduced, unranked candidate list with real weapon tables).
- **2026-10-18 (Daniel):** TMM from actual hexes moved; stub defaults
  approved; loud warnings fine; "hammer out something with the semblance
  of working."
- **2026-10-18 (Claude): first end-to-end run.**
  - Fixed: `INTEGRATION__weapon_selection.py` purge workaround removed (it
    deleted the `config` registration — live-confirmed ImportError).
  - Fixed: `piloting_rolls.py` reads a global `config.PILOTING` that didn't
    exist — `INTEGRATION__config.PILOTING` added; every call wrapped by
    `_with_piloting(mech, fn)` so each mech uses its own skill.
  - Fixed: `INTEGRATION__main.py` imported a non-existent bare `config` —
    now calls `orchestrator.run_batch()`.
  - Fixed: `INTEGRATION__config.py` imported bare `file_picker` — now
    `INTEGRATION__file_picker`.
  - Added headless mech paths (`MECH_RED_MTF`/`MECH_BLUE_MTF`), `SEED`,
    `DATA_DIR` path resolution, STUB SETTINGS block.
  - Added `INTEGRATION__stubs.py` (13 stubs + registry),
    `INTEGRATION__attack_resolution.py` (Ranged Combat with real dice;
    absorbs `sim_runner._resolve_hit`/`resolve_weapon_attack`),
    `INTEGRATION__results.py` (BattleResult moved here + batch summary +
    stub banner), `INTEGRATION__make_run_dir.py` (prefixed files → run layout).
  - Orchestrator: movement phase wired (envelope → stub pick → apply →
    movement PSR → consciousness), Ranged/Physical/Heat/End wired, per-battle
    stub reset and weapon-table cache reset (id(mech) reuse hazard),
    `random.seed(SEED)` for the tripod sub-roll.
  - Tested: Asymptote vs Asymptote (93 turns, Blue engine destroyed),
    Asymptote vs synthetic missile/AC/LB-X/rear-mount test loadout (8 turns,
    and a quiet 5-battle batch). Same seed → byte-identical stdout and
    stderr. Builder round-trip → identical output. Tests ran against
    test copies of the MECHSIM/PATHFINDER files transcribed from this
    Project (logic verbatim, docstrings trimmed) and a test equipment.json
    with the mini DB's stats.
- **2026-10-18 (Daniel):** Heat rules — max_heat is dissipation + the set
  value; movement heat Walk 1 / Run 2 / Jump max(3, hexes, or ceil(hexes/2)
  with Improved JJ); heat is saved state across turns; cooldown logic later.
- **2026-10-18 (Claude):** Wired the heat rules. `weapon_selection.select_weapons_to_fire`
  takes `dissipation`/`movement_heat`, budget = max_heat + dissipation −
  current − movement. `orchestrator`: `movement_heat()`, Improved-JJ
  detection (also matches unparsed crit strings, for the mini DB), real
  `_phase_heat()` accumulation. `stub_heat_phase` + `STUB_HEAT_MODE` replaced
  by `stub_heat_effects` (Heat Scale / engine-hit heat still missing).
  Tested: Asymptote mirror 22 turns (5-laser alphas, heat stays 0 vs 22
  sinks); synthetic mech climbs 0→7→8 and holds at max_heat 8; movement
  heat formula unit-checked; same seed → identical log.
- **2026-10-18 (Daniel):** Movement scoring should be heat-aware.
- **2026-10-18 (Claude):** `INTEGRATION__ranged_combat.evaluate_going_second`
  now scores each spot's dealt/received with `select_weapons_to_fire` (the
  same heat-limited pick Ranged Combat uses), with the spot's own movement
  heat in the mover's budget and the defender's movement heat in its
  return-fire budget; memoized per call. Was: sum over all in-range weapons
  (alpha assumption). New `INTEGRATION__heat.py` holds movement heat,
  Improved-JJ detection and the budget formula (moved out of the
  orchestrator to avoid a circular import). Tested: for every second mover
  (opponent's position final) the pick's expected damage equals what the
  combat phase then fires — 22/22 turns mirror, 7/7 synthetic; a 3-heat
  jump under a 19-heat budget scores 4 lasers (14.00) instead of 5 (17.50).
- **2026-10-19 (Daniel):** Moved the project to GitHub
  (`Logajam/battletech-monte-carlo-sim`). Retire the prefixed
  PATHFINDER/MECHSIM source files except ones that still hold context for
  useful features.
- **2026-10-19 (Claude):** Repo laid out as the run folder (the one
  `make_run_dir.py` used to build). `INTEGRATION__make_run_dir.py` removed:
  nothing left to convert. Prefixed `MECHSIM__*`/`PATHFINDER__*` copies
  retired; the live modules are `mechsim/` and `pathfinder/`. Reference
  files stay in the claude.ai Project, not the repo (Daniel):
  `PATHFINDER__combat_turn.py` (two-ply look-ahead, closing fallback),
  `PATHFINDER__report.py` / `terrain_colors.py` / `MECHSIM__sim_runner.py`'s
  record-sheet printing (output/visual helpers, for a future GUI shell),
  `PATHFINDER__validation.py` (test suite for the pathfinder modules;
  imports an absent `simulate`). Verified: a run from the repo
  matches `reference_logs/Asymptote_vs_Asymptote_seed12345.txt`
  except for file paths, stdout and stderr both.
- **2026-10-19 (Claude):** From Daniel's `battletech-monte-carlo.zip`
  (a parallel repo package, all code identical to this repo): added
  `data/BigBlank.board` (50x50, parses), `requirements.txt`, its
  `.gitignore`, and its sample logs, which use repo-relative paths and name
  the settings (`Asymptote_vs_Synthetic_maxheat8_seed777.txt` = Asymptote vs
  TEST_Synthetic_Loadout, max_heat 8, seed 777). Its README, docs and
  `make_run_dir.py` not taken.
- **2026-10-19 (Claude):** `PATHFINDER__validation.py` rebuilt as
  `tests/test_pathfinder.py` (Daniel asked). Same tests and expected
  values; paths point at `pathfinder/` and `data/`; old test 5 removed (it
  needed the absent `simulate.py`, whose import blocked every test); runs
  all tests and exits non-zero on any failure. Result: 8/8 pass. Sanity
  check: setting heavy-woods cost to 3 in a scratch copy fails test 7.
- **2026-10-19 (Daniel):** Full equipment DB goes in the repo, replacing the
  14-entry mini.
- **2026-10-19 (Claude):** `mechsim/equipment.json` replaced with the full DB.
  The mini's 14 entries have identical stats in it (only alias lists grew).
  Effect on the reference battles: Asymptote mirror now records jump-jet
  crits as "jump MP reduced (now 4)" and Endo Steel crit slots as real
  components - still 22 turns, Red wins; Synthetic battle unchanged except
  the "unrecognized component" notes are gone. Both reference logs
  regenerated. Added `tests/check_reference_logs.py` (re-runs both
  reference battles and compares; `--update` rewrites them) so the check
  works on Windows without diff tools.
- **2026-10-19 (Daniel):** Fill the equipment DB's missing weapon stats from
  his rulebook table rips (Total Warfare, Tactical Operations: AUE,
  Interstellar Operations).
- **2026-10-19 (Claude):** Rulebook fill pass on `mechsim/equipment.json`.
  Parsed all three tables; matched entries by canonical name/aliases + tech
  base; validated against already-filled entries first (368/372 values
  agree). Filled only null fields: 210 fields across 103 weapons
  (damage_type 95, damage 38, range 38, heat 36, rack_size 7); every
  changed entry's `notes` names the table row. One correction: Extended LRM
  5/10/15/20 range 7/14/21 -> 12/22/38 (the old value was inherited from the
  LRM base class and marked "Not confirmed"; TO:AUE says 12/22/38). Clan
  Heavy MG range set 1/2/2, following the IS Heavy MG entry's existing
  long = medium convention for "no long range". `verified` flags unchanged.
  Effect: Asymptote mirror unchanged; Synthetic battle now fires its LB
  10-X AC and ends turn 4 (was 8); its reference log regenerated.
- **2026-10-19 (Daniel):** One-shot launchers: thought removed from the JSON
  (they aren't - 41 OS/IOS entries are present); add their stats someday.
  Missing minimum range is a problem that needs to be corrected.
- **2026-10-19 (Claude):** Added `range.min` to 170 weapon entries from the
  rulebook tables: 161 by name match whose short/medium/long equal the
  table row exactly, 7 more by word-order match under the same equal-range
  check, plus both Heavy MGs (row has no long range; min cell 0). A dash in
  the min cell (7 rows) is stored as 0. No other field changed; battles are
  unchanged because nothing reads `range.min` yet.
- **2026-10-19 (Daniel):** Confirmed the minimum-range rule ((min - range) + 1
  per hex inside), missing minimum = 0, and OS launchers = base launcher's
  range/damage stats with a fire-once limit.
- **2026-10-19 (Claude):** Minimum-range penalty wired into
  `weapon_selection._weapon_range_mod` (so both weapon selection's
  expected-damage table and the to-hit roll use it). New
  `tests/test_weapon_range.py` (15 cases). 45 OS/I-OS entries given their
  base launcher's damage_type/damage/heat/range/rack_size where null
  (150+ fields; no existing OS value disagreed with its base); 204/279
  weapons can now fire. New `stub_one_shot` (replaces the ammo stub for
  one-shots) warns each time one fires. Summary banner: min-range line
  removed, LB-X line updated. Effect: Asymptote mirror unchanged except the
  banner; Synthetic battle now ends turn 7 (its LRM 15 takes +1 at range 6
  and is dropped for a laser at range 1; UAC/5 and AC/5 take +2/+3 at range
  1). Both reference logs regenerated.
- **2026-10-19 (Daniel):** "Get heat fully wired in", from his rules index
  (`Battletech Rule Reference Index`, Core Rulebook Heat chapter pp.102-107;
  errata v0.1 has no heat entries).
- **2026-10-19 (Claude):** Heat Scale wired; `stub_heat_effects` removed.
  - `INTEGRATION__heat.py`: Heat Data Table (p.103), engine-hit heat
    (+5 / +10 total, none while shut down), XXL and super-cooled-myomer
    movement heat (p.102), and `resolve_heat_phase()` in the book's order:
    adjust scale (Overflow kept) → shutdown roll (14: 4+ … 26: 10+,
    automatic at 30, no override with an unconscious MechWarrior) or, for a
    mech already shut down, restart (automatic below 14, roll otherwise,
    never at 30+) → ammo-explosion roll at 19/23/28 (4+/6+/8+; bin with the
    highest damage value per turn of shots explodes, Gauss/one-shots never)
    → life-support MechWarrior hits (1 at 10-19, 2 at 20+) → next turn's
    MP penalty (5/10/15/20/25) and ranged to-hit modifier (8/13/17/24).
  - Shut-down mechs: skip movement, don't fire, give attackers the -4
    immobile modifier, auto-fail standing PSRs (`piloting_rolls`), no engine
    or weapon heat; sinks keep working.
  - MECHSIM edits: `mech_state` gains `shutdown`/`heat_mp_penalty`/
    `heat_fire_modifier`/`myomer` and `is_immobile()`; `compute_walk_mp`
    subtracts the heat penalty after the damage floor (may reach 0, p.104);
    Hardened running floor skipped at 0 MP; `compute_heat_dissipation` adds
    +3 for a working Partial Wing (p.103). `mtf_parser` reads `Myomer:`.
  - **Claude's reading, for Daniel to confirm:** engine-hit heat comes out
    of the weapon heat budget (`select_weapons_to_fire(engine_heat=...)`),
    so max_heat still caps the end-of-turn level. Shutdown override /
    restart use the "pilot" crew role's consciousness (multi-crew mechs).
  - Side effect of the immobile rule: movement scoring
    (`ranged_combat.evaluate_going_second`) now scores an unconscious
    defender at the -4 immobile TMM, matching the combat phase (it used
    actual hexes moved before).
  - New `stub_heat_explosion_bin` (shots-left tie-break needs shot counts;
    controller's choice is random). New `tests/test_heat.py` (14 checks,
    scripted dice; fails when a threshold or the shut-down engine-heat rule
    is broken). New reference battle
    `Asymptote_vs_Synthetic_maxheat30_seed2.txt` (shutdown, heat ammo
    explosion, auto-failed PSR while shut down, automatic restart).
  - Effect: Asymptote mirror diverges at turn 8, right after Blue's first
    engine hit (+5 heat a turn, later +10, cutting its fire and giving it
    -1 MP / +1 to-hit at times); now 18 turns (was 22), Red still wins.
    Synthetic (max_heat 8) diverges at turn 2 (heat 5 after turn 1 -> -1
    Walking MP; at 8 it fires at +1); now ends turn 8 (was 7). Both
    regenerated. 300 quiet battles at max_heat 30: no crashes.
- **2026-10-19 (Daniel):** Engine-hit heat confirmed (charged in the Heat
  Phase of the turn the hit lands, then budgeted). Heat work goes straight
  to `main` - QC later, once he starts playing with it. Add stealth, coolant
  pods, radical heat sinks, inferno extra rolls, TSM, torso-mounted cockpit
  life support, aimed shots at shut-down mechs, MASC, superchargers, and
  End Phase heat-sink switching; player choices default on (radical/MASC/
  supercharger: 1 turn on, 1 off); TSM via min_heat 9.
- **2026-10-19 (Claude):** Heat equipment wired.
  - New `INTEGRATION__equipment_systems.py`: equipment detection by crit
    name, Escalating Failure (p.180, consecutive-turn count steps back on an
    unused turn), the on/off cycle, stealth systems (heat, +1/+2 medium/long,
    Void-Signature by hexes moved and +1 to its own attacks, ECM needed for
    stealth armor and Void), coolant pods (used pods stop being explosive),
    radical heat sink state, MASC/supercharger (Running MP x2 / x2.5,
    failure crits after moving: MASC to one random leg via the Kick table,
    never transferring; supercharger to the top centre-torso Engine slots,
    and destroyed), TSM activation.
  - `INTEGRATION__heat.py`: stealth heat; extra cooling at the start of the
    Heat Phase (radical on cycle turns, else a coolant pod); destroyed
    radical +1 movement / +1 firing heat; inferno bins roll the p.192 table
    separately and an inferno explosion's +30 heat re-triggers any newly
    crossed shutdown / ammo / inferno rolls; torso-cockpit life support
    (1-14: 1 hit, 15+: 2); TSM effect; `choose_heat_sink_deactivation`
    (End Phase, also at deployment). Weapon budget uses `other_heat` =
    engine + stealth + radical surcharge - planned radical cooling.
  - `weapon_selection`: `other_heat` replaces `engine_heat`; per-weapon
    `tn_adjust` (stealth range bonus, aimed shots); `range_bracket()`;
    min_heat is now the end-of-turn floor (no padding when it's 0).
  - `attack_resolution`: stealth TN terms, aimed shots (p.70: no cluster
    weapons; head +7 vs the -4; partial cover not applied and legs behind it
    rerolled; 1D6 4+), radical weapon surcharge. `ranged_combat` scores
    moves with the same terms.
  - MECHSIM: `mech_state` gains `tsm_active`, `deactivated_heat_sinks`,
    `run_mp_multiplier`, `heat_sink_rate()`/`working_heat_sinks()`/
    `active_heat_sinks()`; `mtf_parser` keeps the Cockpit:/Armor: header
    text and maps "Stealth" armor to Standard (no damage-math change).
  - `equipment.json`: `coolantpod` was category "ammo" (so it would have
    been a heat-explosion candidate with the 20-point ammo default) - now
    misc, 2-point explosion (p.208).
  - **Claude's readings, for Daniel to confirm:** the p.192 inferno text says
    rolls "at 19, 23, and 28" but its table starts at 10 - the table is
    used. Inferno heat is always the 30 cap (bins are never empty).
    Coolant pods / radical heat sinks don't work while shut down (p.104's
    "activated equipment" rule). Radical cooling on an on-turn is counted
    in the weapon budget; coolant pods aren't (used only when needed).
    ECM suites, like MASC, are one system however many slots they parse to.
  - New `data/TEST_Heat_Gear.mtf` (every new system on one mech), new
    `tests/test_equipment.py` (12 checks, scripted dice; catches broken
    escalating / TSM / inferno / Void / MASC values), two new reference
    battles (`Asymptote_vs_HeatGear_seed5`, `..._maxheat30_seed2`). The three
    older reference battles: log wording changed ("other" heat), and the
    maxheat30 battle now has aimed shots at the shut-down synthetic mech
    (ends turn 7, was 8). 300 quiet gear-mech battles: no crashes; failed
    escalating rolls ~1 in 36 as the 3+ table predicts.
- **2026-10-19 (Daniel):** Engine-hit heat confirmed. "Search for stubs
  that have answers in the rules and correct them." Keep files up to date
  (commit to main as I go).
- **2026-10-19 (Claude):** Every stub with a rules answer replaced, from
  the Core Rulebook (one commit per batch on main):
  - Attack direction (p.73): hexside the LOS enters, read against the
    target's facing (`attack_resolution.attack_side`).
  - Cluster groupings (pp.87, 181): SRM 2, LRM/MRM 5, ATM 6, default 5;
    Streaks hit with every missile, no heat or ammo on a miss (p.187); MRM
    cluster rolls -1 (p.186). New `INTEGRATION__weapon_rules.py`.
  - Standing up (p.51): free facing, remaining MP spent normally (Run).
  - Walking never forces a PSR; running only after 1+ hex (p.111).
  - To-hit (pp.66-67, 97-98, 184-200): per-weapon modifiers (pulse -2,
    ER pulse -1, X-pulse -2, VSP, heavy +1, re-engineered -1, silver bullet
    -1, RL +1, M-pod -1), targeting computer -1, shoulder +4 / upper arm +1,
    sensors (+2 / no fire; torso cockpit +2/+4/none), prone target -2/+1,
    prone attacker +2 with a prop arm (tripod/quad p.231).
  - Rear-mounted weapons (p.60): parser keeps "(R)"; only they fire into
    the rear arc, and only there. Side arcs and torso twists: see Change Record
    2026-10-19 (`INTEGRATION__arcs.py`).
  - Ammunition (pp.72-73, 95-96, 180-182): shots_per_ton from the Core
    tables (107 weapons; 125 heat values cross-checked, all agree), bins
    linked by exact ammo type, one shot per firing, fewest-shots bin first,
    empty bins don't fire or explode, explosion = shots x damage capped 20,
    one-shots and rocket launchers fire once, heat-explosion tie-break on
    shots left, real inferno heat. Inferno bins aren't fired from. New
    `INTEGRATION__ammo.py`.
  - Weapon data (pp.248-254): 62 null fields filled (types, ATM stats,
    heat/range); 209/279 weapons can fire (was 204).
  - Deployment (p.37): deployment roll, home edges, entry on turn 1.
  - Physical attacks (pp.76-83): punches, kicks, physical weapons, TSM and
    talons; kick PSRs via `resolve_attack_phase_psr(forced_triggers=...)`.
    New `INTEGRATION__physical.py`.
  - New `tests/test_rules.py` (11 checks). All five reference battles
    regenerated after each batch (results change: real attack direction,
    pulse -2, ammo limits, home-edge starts, punches).
  - Effects worth knowing: the synthetic test mech carries no LB-X or Ultra
    AC ammo, so those never fire now; the IS Machine Gun has no
    equipment.json entry at all (only Light/Heavy/Clan MGs).
  - Open for Daniel: Core-vs-MECHSIM PSR differences and the firing-arc
    diagram (Section 4).
- **2026-10-19 (Claude):** Added the rules library zip to the repo as
  `rules/Battletech_Rule_Reference_Index.zip` so later sessions can read it.
