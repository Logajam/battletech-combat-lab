# Play UI: every player action and its home (DRAFT 1, 2026-11-24, Claude's proposals)

Goal (Daniel, 2026-11-24): list every action a player can take and say where it lives on screen, on paper, before any more
UI is built ("moving the mockup to the active game was less than successful"). This is P3a in PROJECT_MAP Section 0.
Nothing here is built by this file. Daniel rules on the rows marked **?**.

Sources: the decision audit in `INTEGRATION__PLAYER_DECISIONS.md` (Sections 2-9 tables, 12-14 Daniel's answers: his answers
win), the vocabulary in `INTEGRATION__BATTLEROM_UI.md` Section 2, and the design summaries in
`INTEGRATION__UI_DESIGN_NOTES.md`. I did not re-read the rulebook for this draft; the rules audit (does every legal
action have a control?) is step 2, from the library with pages cited.

## 1. The homes (the places a decision can live)

| Code | Home | What goes there |
|---|---|---|
| MAP | Map gesture | Tap, drag, tap-hex waypoints, pinch / pan. Anything that is "pick a place or a unit". |
| MAPBTN | Map button | A button that appears beside the unit or target only when the action is legal (Stand, Charge, DFA, Spot, Club, Aimed Shot). Opens away from the finger. |
| ACT | Action cluster | Commit (Move! / Fire!), Undo, Clear, move readout. The commit button is press-and-hold. |
| PLC | Placard | The small label on each unit: name and bars. The expanded form (selected unit) is **?** (see 4). |
| WPN | Weapons panel | Fire phase only: one row per weapon (assign, mode, ammo), target arrows, Strike button. Stays on screen. |
| INS | Inspector | Long press on a unit. Replaces the on-screen data sheet (Daniel, 2026-11-24). Everything rare or detailed. Sections below. |
| HEX | Hex card | Long press on an empty hex: terrain, cost, risks, contents. |
| POP | Confirm popup | One question, Yes / No: hazards, MASC, charge description, stand-up TN. |
| BAN | Banner / info bar | Report only: initiative, "you move 2 now", short results, the focused weapon's detail. |
| RPT | Combat report | Popup after resolution, re-openable from the menu. |
| MENU | Menu | Looks, colour-blind mode, overlays on / off, combat report, save, quit. |
| SET | Setup screens | Win95-style list screens before turn 1 (kept list-based, Daniel). |
| AUTO | No control | The engine decides; the UI may report it. |

**Inspector sections** (proposed; this is where the old data sheet's tabs go): **Status** (armor and structure silhouette,
pilot, heat detail), **Criticals** (full slot table; equipment switches live here, as in MegaMek), **Weapons** (full cards:
ranges, ammo bins, modes, per-weapon TN), **Movement** (manual turning, prone, rare moves, hazards list), **Settings** (this
unit's "ask me / bot decides", auto-eject, personality text), **Debug**.

Frequency: **T** every turn, **S** sometimes, **R** rare. Rule used to pick a home: T -> MAP / ACT / WPN; S -> MAPBTN or POP
(appears only when relevant); R -> INS or MENU. If a decision has a place, it is drawn on the map (design rule).

## 2. Always-available actions (any phase)

| # | Action | Freq | Home | Notes |
|---|---|---|---|---|
| G1 | Select one of my units | T | MAP (tap sprite or placard) and the unit strip | Strip stays for picking a unit that is covered or off-screen. |
| G2 | Select an enemy / pick a target | T | MAP (tap) and the enemy strip | Nearest is pre-picked in the fire phase (Daniel). |
| G3 | Deselect | T | MAP (tap empty) and Esc | Esc is undo first, deselect when nothing to undo (Daniel). |
| G4 | Undo / step back one waypoint or assignment | T | ACT, Esc | |
| G5 | Clear the whole plan | T | ACT | |
| G6 | Commit the plan (Move! / Fire!) | T | ACT, press-and-hold | Nothing is decided before this. |
| G7 | Pan the map | T | MAP (drag empty terrain; two fingers; right-drag on desktop) | Drag with a unit selected is a move preview, so pan needs empty terrain or two fingers. |
| G8 | Zoom, reset zoom | T | MAP (pinch, wheel) and zoom buttons | |
| G9 | Inspect a unit (everything rare) | S | INS (long press unit) | Also long press a placard. |
| G10 | Inspect a hex | S | HEX (long press empty hex) | |
| G11 | Warning mark on a unit (pilot hit, critical, extra detail) | S | PLC mark; tapping it opens INS | |
| G12 | Toggle overlays (movement, firepower, LOS, heat, threat), several at once | S | MENU folder, plus a quick toggle on the expanded placard **?** | One colour scale and a legend. Today only range outlines and arcs exist. |
| G13 | Re-open the combat report | S | MENU | |
| G14 | Look (SL-HIS Dark / Light / Win95 ...), colour-blind mode, text size | R | MENU | |
| G15 | Save the game | R | MENU | Needs saved state (P2, "spare compute"). |
| G16 | Quit / abandon | R | MENU, POP confirm | |
| G17 | Camera: top-down / tilted view, rotate, tilt | S | MAP gestures; corner reset button; presets in MENU | P10, later. |
| G18 | Turn the personality text on / off, pick a theme | R | INS Settings (per unit) and MENU (global) | Cosmetic only. |

## 3. Setup (before turn 1; all SET unless noted)

| # | Action | Freq | Home | Engine today / notes |
|---|---|---|---|---|
| S1 | Pick the map | once | SET | config; picker with preview |
| S2 | Build the forces: units, pilot skills, team per unit; load a custom unit (P1) | once | SET | unit browser and force builder exist in the Lab |
| S3 | Human or bot per force / unit, which bot | once | SET | the switch that makes "Run simulation" into "Play" |
| S4 | Home edge (the roll loser picks N / E / S / W) | once | SET, roll shown in BAN | random today (`HOME_EDGE_CHOICE`) |
| S5 | Walk-on or placed start, zone and depth | once | SET; placing units is MAP drag in the zone | |
| S6 | Rules options (every option is player-facing, Daniel) | once | SET Options tab | 153 settings; sorting them is later |
| S7 | Seed and dice mode | once | SET | warning text when dice are readable (remote play) |
| S8 | Declaration style: simultaneous or take turns | once | SET | verify the book first (PLAYER_DECISIONS Section 11) |
| S9 | Per-category "ask me / bot decides" | once, changeable | SET and INS Settings | default asks only: movement, targets, weapons, physical attack |
| S10 | Turn cap, win rule | once | SET | |
| S11 | Save the starting conditions to a file / load one (P2) | S | SET | units bundled in the file |

## 4. Turn flow

| # | Action | Freq | Home | Notes |
|---|---|---|---|---|
| T1 | See the initiative roll and who moves first | T | BAN | report only (Daniel) |
| T2 | See how many units my side moves now | T | BAN | |
| T3 | Choose which unit moves next | T | MAP / unit strip (G1) | any unmoved unit; moved ones greyed |
| T4 | Mark a unit done (Stand Still, no further action) | T | ACT (Move! with no path = stand still) **?** | one button, or a separate "Done"? |
| T5 | Choose declaration order | S | AUTO until two-player work (Daniel) | |
| T6 | Take control of a bot's unit during a replay | R | INS on that unit ("take control" box) | Daniel: skip for now |

## 5. Movement phase

| # | Action | Freq | Home | Engine today / notes |
|---|---|---|---|---|
| M1 | Plan a path: drag the unit, or tap hexes for waypoints | T | MAP | waypoint steering: engine auto-routes (known issue, Section 4) |
| M2 | Choose final facing | T | MAP: ring of turn arrows around the end hex | colored by mode, MP cost (mockup) |
| M3 | Choose mode: Walk / Run / Jump / Stand Still | T | Implied by the path (color); override in ACT readout | Dark grey = illegal, commit greys out |
| M4 | See MP, TMM, running cost | T | ACT readout | |
| M5 | MASC / supercharger on | S | POP (shows failure TN) | stub: 1 on, 1 off |
| M6 | Radical heat sinks on | S | MAPBTN appears when expected end heat > 0 (Daniel); switch in INS Criticals | |
| M7 | Accept hazards (piloting rolls, lava, mines, bog) | S | POP before commit | a jump checks only the landing hex |
| M8 | Stand up from prone | S | MAPBTN beside the unit | moving to another hex auto-attempts it |
| M9 | Turn in place while prone and unable to stand | R | INS Movement | |
| M10 | Go prone voluntarily; other odd moves | R | INS Movement ("normally hidden") | going prone not built |
| M11 | Declare Charge | S | MAP: waypoint on an enemy, path goes black; MAPBTN if legal; POP describes it | Daniel's flow. Yes = commit, No = back up one waypoint |
| M12 | Declare Death From Above | S | same as M11 | |
| M13 | Entering the board: pick entry hex along the edge | S | MAP | engine picks the hex today |
| M14 | Step aside in a domino effect | R | POP | option `DOMINO_DODGE` is off; AUTO until on |
| M15 | Jump out of bog / stay | R | POP | |
| M16 | Eject; voluntary shutdown | R | INS Criticals / cockpit | known shortfall, not built |
| M17 | Manual turning / override the auto-pathfinder | R | INS Movement | Daniel's escape hatch |
| M18 | Stacking: end in a shared hex | S | MAP | the real rule is a placeholder |
| M19 | Backward / minimum-move (p.49) | S | MAP | minimum move not drawn yet |

## 6. Ranged attack phase

| # | Action | Freq | Home | Engine today / notes |
|---|---|---|---|---|
| F1 | Pick the primary target | T | MAP / enemy strip / WPN arrows | |
| F2 | Cycle targets in range | T | WPN header arrows | |
| F3 | Pick secondary targets (split fire, +1 TN each) | S | MAP: tap another enemy; each target gets its own line | stub picks spare weapons |
| F4 | Focus a weapon (see its arcs and bands) | T | WPN (tap the name) | selecting must never fire it |
| F5 | Assign a weapon to the target | T | WPN (target symbol) | groups by name, arc, bin, mode, TN |
| F6 | Fire or hold each weapon | T | WPN | shows heat projection |
| F7 | Strike escalation: smart, everything at target, all targets | T | WPN Strike button | one tap per step; personality text |
| F8 | Weapon mode: LRM direct / indirect, rate of fire, charge, TAG aim | S | WPN row mode button | rate of fire, capacitor are stubs |
| F9 | Munition kind (LB-X, ATM, MML, Artemis, Narc, inferno, AC specials) | S | WPN row ammo button | bin and kind are linked |
| F10 | Ammo bin choice | R | WPN ammo button -> picker; automatic order CT, side torsos, arms, legs, head | engine draws fewest-shots-first today (small change) |
| F11 | Unjam Rotary / Ultra AC | S | WPN row state "JAMMED: unjam" | stub always tries |
| F12 | Aimed shot (immobile target): location | S | MAPBTN on the target -> location picker | |
| F13 | Torso twist, arm flip, turret turn | S | AUTO (Daniel); manual override INS Weapons | the arcs redraw on the map |
| F14 | Prone: which arm props | S | INS Movement or POP when prone | |
| F15 | Spot for indirect fire | S | MAPBTN beside a selected target | warn when it changes TNs after assigning |
| F16 | TAG designation and aim ('Mech or hex) | R | its own short phase before Ranged; WPN mode | skipped if nobody needs spotting |
| F17 | Distant artillery: aim at a hex | R | MAP: long press a hex -> "fire at hex" | |
| F18 | Club pick-up | S | MAPBTN when a club is in the hex | |
| F19 | Hold an arm back for the physical phase | S | INS Weapons or leave to bot advice | |
| F20 | Raise a shield | R | INS Criticals | stub never |
| F21 | AMS on / off | R | INS Criticals | per-engagement choice stays AUTO |
| F22 | See why a weapon is greyed out (arc, range, ammo, jam) | T | WPN row tooltip / info bar | |
| F23 | Heat budget: see projected heat and shutdown / explosion thresholds | T | PLC heat bar, WPN header | |
| F24 | Narc pod type | R | part of F9 | |
| F25 | Defender's choice of line of sight on a hex edge | R | AUTO now; POP when declarations take turns | Daniel: Q5 |

## 7. Physical attack phase

| # | Action | Freq | Home | Notes |
|---|---|---|---|---|
| P1 | Pick the target (adjacent, or the declared charge / DFA target) | T | MAP / enemy strip | whole phase has no screen yet |
| P2 | Pick the attack: punch (each arm), kick, club, physical weapon, push | T | a list like WPN: target, attack, TN, damage | Daniel's decision |
| P3 | Resolve a declared Charge / DFA | T | RPT | declared in Movement (M11, M12) |
| P4 | Torso twist for physical (p.76) | S | AUTO; override INS | |
| P5 | Charge with spikes; vibroblade on / off | R | INS Criticals toggles | stubs: on |
| P6 | DFA miss: where the target steps | R | POP to the defender | |

## 8. Heat, End Phase

| # | Action | Freq | Home | Notes |
|---|---|---|---|---|
| H1 | Heat sinks on / off (how many stay on) | R | INS Criticals | sticks until changed |
| H2 | Coolant pod use | S | MAPBTN when expected end heat > 0 (Daniel) | automatic unless picked |
| H3 | Voluntary shutdown | R | INS Criticals | not built |
| H4 | Ammo explosion: which bin when tied | R | POP, only on a tie | |
| H5 | Auto-eject on / off | R | INS Settings | warning when head ammo and auto eject is off |
| H6 | Blue Shield on / off; command console seat swap | R | INS Criticals; POP at End Phase | |
| H7 | See shutdown, ammo, wake-up, crippled, destroyed rolls | T | RPT | rolls with a report, no choice |

## 9. Cosmetic and meta

| # | Action | Home |
|---|---|---|
| X1 | Confirm hold-to-commit sensitivity, tap targets | MENU |
| X2 | Replay speed, step through a battle | MENU / ACT (replay is the same screen) |
| X3 | Branch an alternate timeline from an earlier turn (P4) | MENU, then a timeline screen |
| X4 | Share a run (P2) | MENU |

## 10. Rulings Daniel needs to make (the conflicts and gaps this table exposes)

1. **Expanded placard under the selected unit: keep it?** With the data sheet gone to the Inspector, the question is what a
   selected unit shows on screen. My proposal: the placard grows a little (Gunnery / Piloting, movement, heat, the
   context buttons), nothing else; all else is in the Inspector.
2. **Weapons panel: stays on screen in the fire phase?** I assumed yes (the weapons list is the heart of that phase and has
   grouping, sort, per-weapon TN). The summaries' "weapons arranged around the target by body location" would replace it.
   My view: keep the list for assigning, and show body location as a column in the Inspector's Weapons card.
3. **Long press:** unit -> Inspector, empty hex -> hex card, weapon row -> that weapon's card, placard warning mark ->
   Inspector. Any conflict with drag-to-move: a long press needs to be still, a drag cancels it (summary's rule).
4. **T4:** is "stand still" a Move! with no path, or its own Done button?
5. **G12:** where overlay toggles live (menu only, or a quick toggle on the placard).
6. **Decisions with no home yet:** voluntary shutdown, eject, going prone (not built in the engine; Daniel: later).
7. **Declaration style:** needs the book's rule from the library before it gets a control.

## 11. Next steps

1. Daniel rules on Section 10. 2. Add a column with the page of the Core Rulebook that creates each decision, and add any
legal action this list missed (the rules audit; from the library, never memory). 3. Turn the table into the interaction /
state diagram (states: Idle, Unit selected, Planning move, Confirming, Fire assigning, ...; one arrow per row here).
4. Only then change `play.html` / `play.js`, one home at a time, checked on a phone.

## 12. The MegaMek bridge: what MegaMek expects a player to send (added 2026-11-24, Daniel: "any action that megamek would
## expect to be sent to it needs to be listed too")

Why it matters: the Lab as a player in a live MegaMek game (P7; bridge spec `INTEGRATION__MEGAMEK_BRIDGE.md`, stage B7)
means a person's taps must become the same packets MegaMek's own GUI sends. So every row above that a MegaMek game would
need must end as one of these messages. I checked this draft against the bridge's own docs and `bridge.rs`, **not against
MegaMek's source**. Items marked **verify** are from my general knowledge of MegaMek and must be confirmed in its source
(`MovePath.MoveStepType`, `WeaponAttackAction`, `PhysicalOption`, the server's packet handlers) in step 2.

**How the bridge talks today.** MegaMek asks the bridge bot, and our engine answers through these calls (`bridge.rs`
`call`): `move_pick`, `choose_foe`, `choose_movement`, `path_steps`, `choose_target`, `choose_declaration`,
`fire_pick` / `fire_pick_active`, `choose_physical`, `choose_spot`, `manage_heat_equipment`, plus signals `start_movement`,
`unit_moved`, `end_movement`, `reset_assigned`, `end_of_turn`, `assign_damage`. **For a human these are exactly the
decisions the UI must supply**, so each maps to a row above (right-hand column). The answer shapes are Section 5 of the
bridge spec (move with steps, fire with twist and shots, physical, move_order, fallback).

| MegaMek phase | What MegaMek expects | Our row(s) | Bridge today |
|---|---|---|---|
| Lobby | add / remove units, set pilot skills, team, deployment edge, board, game options, "ready" | S1-S8 | Not built (B7c forces). Games start from an `.mms` file today. |
| Deployment | place each unit: hex and facing | S5, M13 | Not built (B7d). Scenarios use fixed hexes. |
| Initiative | the server rolls; a player only acknowledges (**verify**) | T1, T2 | Nothing to send. |
| Movement: order | which unit to move next (`move_order`) | T3 | Wired (`move_pick`). |
| Movement: path | `MovePath` steps: forward, backward, turn left / right, get up | M1, M2, M19 | Wired (`path_steps`). MegaMek's own path finder is the fallback. |
| Movement: jump | start jump, then hexes, final facing | M3 | Wired, via the path finder. |
| Movement: charge, death from above | final step is a charge / DFA step on a target | M11, M12 | **Not wired** (FALLBACK). |
| Movement: MASC / supercharger, radical heat sinks | activation carried on the path or as a step (**verify**) | M5, M6 | Not wired as a choice. |
| Movement: go prone, hull down | steps (**verify**) | M10 | Not wired; hull-down not modelled in the engine. |
| Movement: shut down / start up, eject | steps or commands (**verify**) | M16, H3 | Not wired; not built in the engine. |
| Movement: "Done" | end the unit's turn | T4 | Implied by sending the move. |
| Firing: torso twist | a `TorsoTwistAction` first | F13 | Wired. |
| Firing: arm flip | a flip action | F13 | **Not wired** (FALLBACK). |
| Firing: weapon at a target | one `WeaponAttackAction` per weapon: weapon, target unit, **ammo bin**, weapon **mode** (rate of fire, LRM direct / indirect, capacitor, TAG, etc.) | F1-F11 | Weapons wired by (location, slot). Ammo bin: MegaMek's default unless our engine chose one. Modes: not wired (**verify** how MegaMek sets them). |
| Firing: aimed shot | attack carries aimed location and mode (**verify**) | F12 | Not wired. |
| Firing: spot, TAG | spotting is a consequence of attacking or not; TAG is a weapon attack (**verify**) | F15, F16 | `choose_spot` exists on our side; sending it is not wired. |
| Firing: indirect, artillery | attack on a hex; MegaMek has a separate offboard / targeting phase for artillery (**verify**) | F17 | Not wired; our engine has no separate targeting phase. |
| Firing: unjam, club pick-up, raise shield, AMS mode, capacitor charge, clear minefield | each its own action (**verify**) | F11, F18, F20, F21 | Not wired. |
| Firing: friends' declared damage | not sent to MegaMek; a signal into our bot | F3 | `assign_damage` signal not sent yet. |
| Physical: punch, kick | `PhysicalOption` (one punch, both, one kick) | P2 | Wired for those only. |
| Physical: club, push, hatchet / sword, trip, brush off | `PhysicalOption` kinds | P2 | **Not wired** (FALLBACK). Anything with a twist also falls back. |
| Physical: charge / DFA resolution | resolved by the server from the declaration | P3 | Follows the movement gap. |
| End / Heat | heat sinks, eject confirmation, ammo explosion choices are server rules with prompts (**verify**) | H1-H6 | `manage_heat_equipment` call exists (AMS and similar); nothing human-facing. |
| Every phase | "Done" / end turn; chat; resign or vote (**verify**) | G6, G16 | Implied by the answers. |

**What this adds to the table above.** Rows that matter for the bridge and must stay in the list even if the Lab UI never
shows them: arm flip (F13 is AUTO in the Lab, but MegaMek wants it sent), weapon mode per attack (F8), ammo bin per attack
(F10), aimed location (F12), the artillery target phase (F17), and the lobby and deployment steps (S1-S5). Charge, DFA,
clubs, pushes and flips are the known wiring gaps, and they are the same rows the Lab's own physical phase has not built
(P1-P6, M11, M12), so one build serves both. Non-'Mech units, hull-down, minefields, searchlights and swarm attacks are
outside the engine today (PLAYER_DECISIONS Section 9) and stay Daniel scope calls.

**Step 2 (rules audit) gets a MegaMek column**: for each row, the MegaMek class or packet that carries it, read from its
source (attach it as the bridge work does; MegaMek is never edited, Daniel).
