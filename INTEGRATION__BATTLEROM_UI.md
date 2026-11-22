# BattleROM play screen: design record (2026-11-21, session 33)

"BattleROM: Record, Observe, Meddle" is Daniel's working name for the program (Daniel, 2026-11-21; it will need a new
GitHub repo so the website address comes out right: not decided). This file keeps what was designed in the long
soundboarding session of 2026-11-21 so it is not lost with the chat. The interactive mockup is
`reference_art/battlerom_ui/battlerom_play_mockup.html` (version 16; README there). It is a design reference, not
engine code: all numbers in it are sample data, and rules come from the library (CLAUDE.md), never from the mockup.

Daniel owns the scope and rules calls; "(D)" marks his words or calls, "(C)" Claude's proposals he accepted by building on
them. Items under 7 are IDEAS FOR LATER, not scheduled.

## 1. What it is

- A phone-first play screen: the hex map fills the screen; everything else floats over it. "Phone first. Its harder to
  pull off." (D) Wide and phone-landscape layouts are the same parts rearranged.
- A force whose commander is set to Human changes "Run simulation" to **Play** (D). The replay screen is the feature; play
  is a replay with live input. Nothing is decided until the commit button (Move! / Fire!) is pressed. Undo for nearly
  everything. **Esc is undo** (MegaMek habit; D) and falls through to "deselect" when there is nothing to undo.
- Setup screens stay list-based in the Win95 look (D: "Game set up which is more list based I would like to keep"). Not
  built yet. The play screen is "modern retro".

## 2. Vocabulary (use these words; the mockup's Anatomy button outlines them)

| Name | What it is |
|---|---|
| Title bar | top strip: BattleROM menu button, turn and phase, REC |
| Enemy strip | row of enemy chips under it (pick an enemy without hunting for it) |
| Map | the hex board: hex, hex number, hex base (tinted hex under a unit), sprite (unit art), placard, leader line |
| Placard | floating label per unit: name and three bars (armor, structure, heat), joined to its unit by a leader line; carries the TN pill in the fire phase |
| Info bar | box at the top of the map: short results, or in the fire phase the focused weapon's attack detail |
| Zoom buttons | + / - / reset, right side |
| Range outline | movement limit border; with path, waypoint (numbered), step count (running MP), turn arrows |
| Action cluster | move readout (MP, TMM), commit button, undo, clear |
| Detail sheet | bottom semi-transparent panel: handle, summary line, tabs (Plan/Move, Weapons, Stats, Armor), tab content |
| Unit strip | your force chips along the bottom |
| Weapons panel | the weapon list floating on the left in the fire phase (docked in the right column in landscape) |
| Hex card | long-press detail for a hex |
| Combat report | popup after fire resolves; re-open from the menu |

## 3. Movement (D unless marked)

- Waypoint system: tap a hex inside the range, the range re-lights from there with the MP left; the engine takes the
  cheapest path through all waypoints. MP for turning is part of the cost (1 per hexside) and shows in the range, the step
  counts and the readout. Illegal paths are drawn dark grey and the commit button greys out.
- **Turn arrows** are a hex ring of arrows hugging the unit (about an eighth of the hex's radius inside, a quarter outside),
  none on the side it already faces; each is coloured by the movement mode that turn would need (D).
- **Colours are MegaMek's**, so both programs share a visual language (D). RGB read from MegaMek's `GUIPreferences.java`
  (DEFAULT_YELLOW 216,200,0 / RED 225,51,51 / ORANGE 248,140,0 / PINK 228,20,147 / DARK_GRAY 64,64,64). Walk = cyan, run =
  yellow, MASC = orange, jump = red, illegal = dark grey. NOT VERIFIED (came from a summary of the file): that walk is
  `Color.CYAN`, and which movement type uses which constant; check against the running game.
- **Range display** in MegaMek's style (D, "for commonality"): per `MovementEnvelopeSprite.java`, a dashed line on the outer
  limit (width 2, dash 5/3) plus a translucent band just inside it (thickness 10, opacity 60/255); not an interior tint.
  Colour per mode and nesting (walk inside run inside MASC) are Claude's extension: the code that picks MegaMek's colours was
  not found. No outline around units or the start hex. The unit is not drawn again at the end of a plan: waypoints are
  highlighted hexes, with the path and the turn ring.
- A tap inside the range is a move even if friends are in the hex (stacking limits apply: one 'Mech, up to three others;
  placeholders). Pick a unit from its chip, placard or sprite. Stacks shrink the sprites: a 'Mech keeps at least half the hex.
- **Hazards** (lava, minefields, anything calling for a piloting roll): a confirm like the MASC one, listing each, before the
  move commits. A jump only checks where it lands. TMM is shown next to MP. MASC / supercharger: confirm with the TN; the
  lower TN goes first unless the player picks.
- Hex card on long press: terrain, cost, risks, what else is in the hex (blown-off arms, buildings, mines, smoke).

## 4. Fire phase

- Left weapon list, no more than about 38% of a phone's width, one line per weapon: **fire control** (target symbol, left of
  the name), name, mode button, ammo button (a pile-of-ammo symbol; opens a picker by location and type). The symbol changes
  colour when pressed (assigned); a fired weapon shows a red target on a black row (D).
- Header: previous / next target arrows (cycle targets in range) and a sort button. The nearest target is picked on entering
  the phase or choosing an attacker (D, "sure"). The map centres on the target.
- **Tap a name = focus** (see its arcs and bands, its detail in the info bar); the **target symbol = assign**. Selecting a
  weapon must never fire it (D: "mismatch ... it just shoots because you selected it").
- **Grouping rule** (D's caveat): weapons share a row only if name, firing arc, ammo bin, mode and the TN against the current
  target all match. Same-name weapons with different arcs or TNs stay apart. Every weapon carries a location and an arc
  (data the mockup invented; real data from the unit files). A tap adds one weapon of the group to the target; a tap when
  full clears them. The count shows as n/m.
- **Info bar in the fire phase** (D): target, range, current heat (and heat if the assigned weapons fire); for the focused
  weapon: name and locations, damage, heat, ranges as Min/S/M/L with no spaces and no labels (a dash for no minimum), mode,
  ammo bin; then the TN with its breakdown and odds. No firing arc (redundant), no "Mounted" line.
- **Arcs and range bands** for the focused weapon are drawn on the map: solid white short, dashed yellow medium, dotted
  orange long, cut to the weapon's arc (D).
- Each target in use gets its own line with the range and the number of weapons (D).
- **Strike** button cycles Strike / Alpha Strike / ALPHA STRIKE! (heat-efficient guess / everything in range / everything at
  any available target); a missiles-only unit reads Missiles / More Missiles / All the missiles (D).
- **Sorting** (D): mount order, range (long to short or reverse), damage (high to low or reverse), heat; plus a
  "group identical weapons" switch. Set in the Weapons tab, which has more detail per weapon; the panel mirrors it and its
  sort button cycles the same setting. Remembered on the device. Press and hold a weapon row for its full card.
- LRMs have a Direct / Indirect mode (sample: indirect adds +1 to the TN). Ammo choice per weapon is remembered between turns
  (D: "absolutely").
- Enemy weapons and stats are visible but read-only (D).
- **Combat report**: after Fire! a popup lists each shot (weapon, target, TN, roll, hit or miss, location, damage, any
  critical). MegaMek uses a popup; Claude kept it and made it re-openable (menu, Combat report). Fire resolves only after all
  fire is declared. (A line of Daniel's message about this was cut off: "Weapons fire is not actually figured out until
  after the turn. It would be a small document". Read as: resolution comes after declaration, and the report is short.
  Confirm.)

## 5. Detail sheet, placards, looks

- Detail sheet is semi-transparent, with larger up and down arrows, and flicks up and down (a flick down inside the content
  counts only when it is scrolled to the top). Tabs: Plan (Move in the fire phase), Weapons, Stats (equipment order, ammo,
  the full critical slot table), Armor.
- **Armor tab**: a generic 'Mech silhouette split into hit locations; armor pips outside (white), structure pips inside
  (grey); damage turns pips red from the outside in (torsos and head from the top, arms and legs from the outer side, so
  structure sits next to the body). Rear armor is not drawn yet. Placard bars wear in from the left and right edges so the
  damaged side shows. Critical slot layouts in the mockup are stand-ins.
- Looks (switch in the BattleROM menu, folder Look; remembered per device): **SL-HIS 7.2 Dark is the default** (D: "Will
  probably make it the standard for the website"), SL-HIS 7.2 Light, Win95, Modern, Terminal, Amber. SL-HIS (the Star
  League Human Interface Standard, ComStar's refined Win95; spec from a side discussion with ChatGPT, kept to its palette,
  1px bevels, flat tabs, thin focus outlines, Inter type): slate blue `#516C88` title bars and selection; dark values
  `#12161B` page, `#1A1F26` panel, `#252C35` control face, `#E6EBF0` text, `#3F5F80` title, `#6D7A88` border. Win95 "fits
  annoyingly well" (D); Modern "looks perfectly function and lacks soul" (D). Layout, tap sizes and the map (its terrain
  and MegaMek movement colours) are identical in every look (D: bright map inside dark controls, as in Modern).
- Contrast (calculated 2026-11-21, dark): text on panel 13.8:1, muted 7.7:1, white on slate 6.7:1, error 5.4:1, warning 7.7:1,
  disabled and out-of-range text raised to 5.4:1 (was 3.6:1; light mode was 2.6:1, now 5.4:1). Not checked: a colour-blind
  simulation of warning versus error, or of the weapon icon's assigned / part-assigned / assigned-elsewhere states (they use
  colour and border style).
- Type floor 11 px for anything read at a glance; tap targets at least 32 px (boxes are drawn about 25 px inside a 32 x 34 px
  tap area). Text size S / M / L (10 / 11.5 / 13 px) for the weapon list and info bar is a mockup test control.
- Colour-blind mode (D: "certainly needs to be included in our own options"): a second palette plus line patterns and a
  letter on each range band. MegaMek's own option was not looked up.
- Menu is nested folders (D): Look (SL-HIS Dark, Light, Other looks, Colour-blind mode), Demo controls (phase and layout
  switches; scaffolding only).
- Landscape: the weapon list docks in the right column (an "i" button or the Panel tab swaps it with unit details); it
  switches on by itself when a phone is turned sideways.
- A 4 px grid (8 px preferred step; Material-style) is a good idea to enforce, as a cleanup pass once the layout is frozen,
  with an automated check that measures real elements (D asked; Claude advised). Icons: pictograms, no icon set (D).
  No status LEDs (D).

## 6. What the engine would have to give the front end

A legal-moves query (reachable hexes by mode with MP cost including turns, and the path through waypoints); stacking limits;
hazards and their rolls; TN with its breakdown per weapon and target (movement, range band, terrain, heat, secondary
target, minimum range, indirect); firing arcs and weapon locations from the unit files; ammo bins by location and type;
modes; heat projection; critical slot tables from the `.mtf`; per-location armor and structure; the combat report as data;
the state needed to save and resume (INTEGRATION__PROJECT_MAP.md Section 0, backlog item "player-controlled forces").
MegaMek sprites (D, "bite the bullet") would sit on translucent hex bases; their licence carries over (CC BY-NC-SA, no
commercial use; Daniel agrees), so check each image set before committing any (the repo goes public in part).

## 7. Ideas for later (Daniel: "ideas for later pile", do not nag)

- Attack animation; replaying a whole turn with movement and fire together; a "what if" take-over of a bot's choice during
  replay; branching a battle from an earlier phase with a fresh seed (both players agree in a remote game) and a timeline
  screen for it.
- Remote play between two browsers: WebRTC data channel; a short room code plus a short authentication phrase both players
  confirm by voice (D's "two factor"); STUN (cheap) and a TURN relay only if needed; lockstep from a shared seed versus a
  host that holds the state; "remote host mode" for the downloadable build; dice choices (shared seed = replayable and
  readable, sealed = unpredictable, commit-reveal as a middle road). Only suits friendly games unless sealed.
- The setup-style list screens in the Win95 look; a night-map option; SL-HIS status wording; hex bases under MegaMek sprites.
- A short "archive entry" wording for the ComStar look (off by default).

## 8. Open questions for Daniel

1. The cut-off line about fire resolving after the turn (section 4).
2. Which looks stay in the menu long term (the menu keeps all six for now).
3. Does BattleROM rename the repo and the public site, or only add a new public repo?
4. Whether the two weapon-icon states that share a colour family (assigned, assigned elsewhere) need a stronger cue.
