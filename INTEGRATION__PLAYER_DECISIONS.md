# Player decisions audit: what a human has to be asked (BattleROM, step 1)

Daniel, 2026-11-21: "Time to start making it real. Step 1. Need an audit of game mechanic choices that the UI needs an
interface for."

Method: every place the engine asks a bot, or a stub, to choose. Sources: `BotSet` in `engine/core/src/orchestrator.rs`
(the seam), the stubs registry (`stubs.rs`), PROJECT_MAP Section 6 (the decision index), the phase code in
`orchestrator.rs`, and a search of the engine source for choices the rulebook gives a player that nothing models.
Written from the code and the docs, not run. Companion: `INTEGRATION__BATTLEROM_UI.md` (the mockup and its vocabulary).

How to read the tables. **Who decides today**: Bot = a `BotSet` method; Stub = a placeholder in `stubs.rs` with a default;
Auto = the engine rolls or resolves it with no choice offered; None = the engine does not model it at all.
**Mockup** = does the 2026-11-21 mockup already have a control for it: Yes / Part / No.
**Pri**: 1 = the core loop is unplayable without it; 2 = common equipment or rules; 3 = rare or optional.

## 1. The seam: where a human plugs in

`BotSet` has 17 methods; about nine are real decisions. A human controller must answer these:

| Method | Asks | Notes for a human |
|---|---|---|
| `choose_movement` | the whole move of one unit: hex, facing, mode, charge / DFA flag | One call = one finished move. The mockup's waypoint builder produces exactly this (a `Pick`). It also carries `standup_mp` (prone units) and `entry_edge` (walk-on). |
| `move_pick` | which of a side's units moves next | Defaults to the engine's move index. A human normally picks (book: players choose the order; the engine's index is a bot heuristic). Must be read-only today. |
| `choose_target`, `choose_declaration` | the one target, then the weapons, torso twist / arm flip / turret and the physical attack planned beside it | Today the target is one per unit; the engine has split fire as a stub (Section 3). |
| `choose_physical` | attack type and limb after the ranged phase | |
| `choose_spot` | spot for indirect fire, and whether the spotter also fires | Start of the Ranged phase. |
| `manage_heat_equipment` | AMS on / off (Princess only today) | End Phase. |
| `fire_pick` | order in which a side's units declare | Gladiator's firing order. |
| `choose_foe`, `assign_damage`, `records_declared_damage`, `reset_assigned`, `start/end_movement`, `unit_moved`, `end_of_turn` | bot bookkeeping | No human equivalent. |

Plus a dozen stubs that are decisions the book gives to the player but the engine answers by default (Sections 2 to 5).

**Resume mechanism (Daniel, 2026-11-21, corrects my first draft).** The engine has no clock; it only knows which decision
comes next, so it can simply wait for the answer. Replay is the same decision list, recorded on the human's side, which is
what allows backtracking to a point and changing one answer. My earlier worry (synchronous calls) applies only to the
browser build, where the engine runs on the page's one thread and must not block it: run the engine in a Web Worker and
have it wait on a message from the page (not yet tried here). The native Combat Lab server can block a thread directly.

## 2. Setup (before turn 1)

| Choice | Who decides today | Mockup | Pri | UI needs |
|---|---|---|---|---|
| Map (board, stitched grid) | config | No | 1 | Picker + preview (Win95 list screens) |
| Forces: which units, pilot skills, team per unit | `FORCES` config | No | 1 | Unit browser, force builder, BV total |
| **Human or bot per force / per unit**, and which bot | `BOT`, per-unit "bot" | No | 1 | New. The switch that turns "simulate" into "play" |
| Home edge (deployment-roll loser picks) | `HOME_EDGE_CHOICE` (random) | No | 1 | Roll shown; loser picks an edge (N/E/S/W) |
| Walk-on versus placed starts; deployment zone and depth | `DEPLOYMENT`, `DEPLOYMENT_PLACED`, `_DEPTH` | No | 1 | Place units in the zone, or enter on turn 1. Known issue: Gladiator walk-on bug (PROJECT_MAP Section 4) |
| Rules options (153 settings in `config.json`; some are rules switches, most are bot tuning / render / debug; not yet sorted) | `config.json` | No | 2 | Two tiers: "Rules" (fight to the death, floating crits, domino dodge, club pickup, charges, DFA, passive buildings...) shown to players; bot tuning hidden under an Advanced folder |
| Seed / dice mode (shared seed, sealed, replayable) | `SEED` | No | 2 | Warning text when the seed makes dice readable (remote play) |
| Turn cap (100) and win rule | `MAX_TURNS` | No | 3 | |

## 3. Turn flow

| Choice | Who decides today | Mockup | Pri | UI needs |
|---|---|---|---|---|
| Initiative roll (2D6, lowest acts first; ties re-roll; 3+ sides) | Auto | No | 1 | Show the roll; "who moves first" banner |
| Unequal numbers: how many units a side moves at a time | Auto (book table; MegaMek rule for 3+ sides) | No | 1 | Show "you move 2 now" |
| **Which unit moves next** | `move_pick` / move index (bot heuristic) | Part (unit strip lets you pick) | 1 | Free choice among the units not yet moved; mark done |
| Order of ranged declarations | `fire_pick` / roster order | No | 2 | Free choice, or just "all declare, then resolve" (the engine declares both sides before damage lands) |
| Per-category "ask me / let the bot decide" | not present | No | 1 | **New setting.** Recommended so a player is not asked 14 questions a turn: ask for movement and targets always, pre-answer the rest with the stub defaults |

## 4. Movement phase (per unit)

| Choice | Who decides today | Mockup | Pri | UI needs |
|---|---|---|---|---|
| Path, waypoints, hex and facing at the end | `choose_movement` | Yes | 1 | Done in the mockup |
| Mode: Stand Still / Walk / Run / Jump | in the `Pick` | Yes | 1 | Done; colours match MegaMek |
| MASC / Supercharger / radical heat sinks on or off ("escalating failure" gear) | **Stub** `stub_escalating_use` (default: 1 turn on, 1 off) | Yes (MASC confirm) | 1 | Confirm shows the failure TN; supercharger and radical sinks have no control yet |
| Turning cost, backward moves, minimum move (p.49) | in the path search | Yes (turn MP) | 1 | Done; minimum move (a move with insufficient MP) not drawn |
| Entering the board (walk-on): entry edge hex and facing | `entry_edge` argument | Part | 1 | Pick the entry hex along the edge (engine: the edge, the bot picks the hex) |
| Stand up: try or stay prone (a Run-mode PSR); then move on with the remaining MP | Auto: `resolve_stand_up` tries whenever it can | No | 1 | "Stand up?" confirm with the TN; engine currently always tries when able |
| Prone and cannot stand: turn in place | `turn_while_down_choice` (bot) | No | 2 | Facing choice, 1 MP per hexside |
| Stuck / bogged in magma or swamp: jump out, or stay | Auto (jump out if able) | No | 3 | Confirm |
| Hazard confirms: movement PSRs, terrain damage, bog roll | Auto, gated by `PathGate` | Yes | 1 | Done: warning before commit |
| **Declare charge or death from above** (target; the move stops adjacent / in the air) | `Pick.charge / .dfa`, config `CHARGES`, `DFA` | No | 2 | Target pick from the move-end hex; the declared attack resolves in the Physical phase |
| Domino effect: step aside one hex (p.114) | `DOMINO_DODGE`, **off**: nobody steps aside | No | 3 | Prompt "step forward / back / stay" when the PSR passes |
| Fall during the move: where the unit ends | rules (Auto) | No | 3 | Report only |
| Stacking: end in an occupied hex | `blocked_hex` / `other_unit_hexes` | Yes (placeholder limits) | 2 | The real stacking rule is a placeholder in the mockup |

## 5. Ranged attack phase

| Choice | Who decides today | Mockup | Pri | UI needs |
|---|---|---|---|---|
| Spot for indirect fire: spot or fire, which enemy | `choose_spot`, **Stub** `stub_spot` (default: nobody spots) | No | 2 | "Spot for allies" toggle on the info bar; a spotter may still fire, at +1 (Core p.70) |
| TAG designation (before the phase) and aim: the 'Mech or its hex | **Stubs** `stub_fire_tag`, `stub_tag_aim` | No | 3 | Weapon-row mode "TAG: unit / hex" |
| Primary target (one) | `choose_target` | Yes | 1 | Done |
| Secondary targets (split fire, p.64: +1 each; the weapons not yet used) | **Stub** `stub_split_fire` (default never) | Yes (lines per target) | 1 | Done in the mockup; engine side is a stub that picks "spare weapons" |
| Each weapon: fire or hold | in `DeclChoice.weapons`; heat-constrained picker | Yes | 1 | Done; add the heat projection |
| Torso twist (L / R / centre), arm flip, turret turn | `declare_attacks` (most expected damage) | **No** | 1 | New: a twist / flip control on the unit; arcs redraw on the map. The arcs and range bands are drawn today but cannot be changed |
| Rear-mounted weapons and which arc the target sits in | derived | Part (arc coloured) | 1 | Show why a weapon is greyed out |
| Ammo bin per weapon (location, type, shots left) | `ammo.spend` (fewest shots first) | Yes | 1 | Done |
| **Munition kind per shot** (LB-X slug / cluster, ATM std / ER / HE, MML LRM / SRM, Artemis / Narc / standard, inferno, Apollo, bombast power, AC special rounds) | **Stub** `stub_munition_choice` (default greedy) | Part (LRM direct / indirect only) | 1 | The mode button needs to cover all of these; bin choice and kind are linked |
| Rate of fire: Ultra / Rotary single, double, rotary 3..6 | **Stub** `stub_rate_of_fire` (default max) | No | 1 | Mode button on the weapon row; shows heat and jam risk |
| Unjam a Rotary / Ultra AC | **Stub** `stub_unjam` (default: always try) | No | 2 | Weapon row state "JAMMED: unjam instead of firing" |
| Aimed shot at an immobile target: location | `AIMED_SHOT_LOCATION` (default centre torso) | No | 2 | Location picker on the target card (TN +; locations from the Armor tab) |
| Prone: which arm props the 'Mech (loses that arm's weapons) | `attack_resolution.prone_fire` | No | 2 | Arm choice on the unit when prone |
| PPC capacitor: charge instead of firing; start charged | **Stubs** `stub_capacitor_*` (never charge; start empty) | No | 3 | Weapon-row mode "Charge" |
| Raise a shield (start of phase) | **Stub** `stub_raise_shield` (never) | No | 3 | Toggle |
| Blue Shield on / off | **Stub** `stub_blue_shield` (on) | No | 3 | Toggle, Start and End Phase |
| Command console seat swap | **Stub** `stub_console_swap` | No | 3 | End Phase prompt |
| Distant artillery (Arrow IV, Thumper, Sniper): aim hex (not a unit), 18+ hexes | **Stub** `stub_distant_artillery`; `princess_artillery::distant_aim` for Princess-family | No | 2 | Hex-targeting mode: long-press a hex, "fire at hex"; shows the scatter / flight time |
| AMS: on / off per system; which incoming missile it engages | `manage_heat_equipment` (Princess); `ams::engage` (engine picks) | No | 3 | A switch; per-engagement choice can stay automatic |
| Narc pod type (homing / explosive); Narc worth | **Stub** (greedy) | No | 3 | Part of munition mode |
| Club pick-up (instead of firing) | `CLUB_PICKUP` (on) | No | 3 | Button on the unit when a club is in the hex |
| Hold weapons back for the physical attack that follows | `_physical_planner` | No | 2 | A "hold this arm for punches" mark, or let the bot's planner advise |
| Heat budget: how much heat to take this turn | bot weapon picker | Part | 1 | Heat bar projects after movement + weapons; warns at the shutdown / ammo-explosion thresholds |

## 6. Physical attack phase

| Choice | Who decides today | Mockup | Pri | UI needs |
|---|---|---|---|---|
| Target (adjacent, or the declared charge / DFA target) | `PhysAdapter.target_of` | No | 1 | Whole phase has no screen yet |
| Attack type: punch (each arm), kick, club, physical weapon (hatchet, sword, lance, flail...), push | `choose_physical` (most expected damage) | No | 1 | List with TN and damage, like the weapon panel, one row per option |
| Charge / DFA resolution | declared in Movement | No | 2 | Declaration at move end; resolution report |
| Charge with spikes: declare, or not | **Stub** `stub_charge_spikes` (always) | No | 3 | Toggle |
| Vibroblade on / off | **Stub** `stub_vibroblade` (on) | No | 3 | Toggle with heat note |
| DFA miss: where the target steps | `dfa.resolve` (smallest drop) | No | 3 | Prompt for the defender |
| Torso twist before physical (p.76) | `physical.choose_attack` | No | 2 | Same control as Section 5 |
| Push displacement hex | rules | No | 3 | Report |

## 7. Heat, End Phase

| Choice | Who decides today | Mockup | Pri | UI needs |
|---|---|---|---|---|
| Heat sinks: how many stay on (to hold a minimum heat) | `heat.choose_heat_sink_deactivation` | No | 2 | End Phase panel; usually leave automatic |
| Coolant pod: use this turn | `heat._extra_cooling` (one pod when above min heat) | No | 2 | A button with a count |
| Voluntary shutdown at the End Phase | None (PROJECT_MAP: "a bot decision, not built") | No | 2 | Needs an engine option first |
| Ammo explosion: which bin goes when several tie | **Stub** `stub_heat_explosion_bin` (random) | No | 3 | Controller's choice in the book; prompt only if tied |
| Shutdown avoid roll, ammo roll | Auto (dice) | Part | 1 | Roll result display (combat report) |
| Wake-up rolls, crippled flag, destruction | Auto | Part | 1 | Report |

## 8. Choices the book gives "the controller" that the engine takes for itself

- **Line of sight exactly between two hexes (p.56):** the engine always takes the more obstructive line (documented in
  Section 6). A human defender is meant to choose. Low frequency; keep automatic and say so in the UI.
- **Ammo explosion bin tie-break, DFA miss displacement, domino step:** listed above.
- **Which of two equal weapons goes at which target:** the mockup groups by name + arc + TN to expose this; the engine
  splits per weapon already.

## 9. Not modeled in the engine (search of `engine/core/src` found no code)

Voluntary shutdown, forced withdrawal and crippled-unit retreat (PROJECT_MAP backlog C1: "not started"), ejection,
hull-down, building entry and climbing (buildings are deferred; "passive buildings" is a config switch), minefields,
searchlights, skidding, swarm / leg attacks, vehicles and infantry as playable units. The mockup shows a foot platoon and
tanks as placeholders; the engine is BattleMech-only so far (my reading of Section 1 and the unit loader; confirm). Each
of these is a **Daniel scope call** before it gets a control.

## 10. What I would do with this (recommendations)

1. **Priority 1 first**: the screens that do not exist yet are setup / force builder, the initiative
   and activation banner, the twist / flip control, rate of fire, munition kinds (generalised mode button), the stand-up
   confirm, the Physical phase list, and the heat / End Phase panel. The mockup already covers movement, targeting, weapon
   assignment, ammo and the report.
2. **Per-category "Ask me / Bot decides"** (Section 3): ships with the stub defaults, so a first playable build asks only
   for movement, targets, weapons, twist, physical attack. Everything marked Pri 2 / 3 stays on its stub until built.
3. **Settle the resume mechanism** (Section 1) before step 2.
4. **Park the Section 9 items** in PROJECT_MAP Section 4 as "not modelled, needs a Daniel scope call", not in this build.

## 11. Open questions for Daniel

Answered 2026-11-21 (Section 12). Still open: (a) the book's rule on declaration order, to verify in the library;
(b) MegaMek's simultaneous-firing behaviour and the exact LOS split code, to verify from source.

## 12. Daniel's answers, 2026-11-21 (these override the tables above where they differ)

**Play model.** A force set to Human in the Combat Lab force builder (which already exists) runs the battle slowly,
waiting at each human decision, instead of Monte Carlo speed. During a replay a checkbox on a unit ("take control") makes
that unit's turn the viewer's own from then on; the Firing phase needs sub-steps that stay hidden until the box is ticked.
Mid-game option changes are decisions too and are recorded in the decision list so a replay reproduces them.

**Order.** Initiative is a report only. In Movement the bots move and the human may move any unit not yet moved, when
it is their side's turn (Q1: yes). Declaration order is an option at setup: simultaneous declaration (default) or players
taking turns declaring. Q2: Daniel is fairly sure the book has players take turns declaring fire; **to verify in the
library before building** (the engine today declares both sides blind and resolves together).

**Automated in the UI, no prompt:** torso twist and arm flip (target something that needs one and it happens: one arm's
target twists, the other arm's target flips); hex-edge LOS for a bot; ammo bin order unless the player opens the picker.

**Buttons and modes (no new screens):**
- Rate of fire, unjam, capacitor Charge (lightning icon), munition kind: all through the weapon row's existing mode / ammo
  buttons. The ammo button exists even for weapons with one kind.
- Stand up: a button beside a prone 'Mech on the map. Moving to another hex makes the stand-up attempt automatic; the
  warning screen still shows.
- Charge / DFA: put a waypoint on an enemy; the path goes black; a map button appears if the attack is possible; pressing
  it recolours the path and opens a confirm popup describing the attack. Yes = same as the Move button; No = back up one
  waypoint. Physical attacks otherwise: a list like the weapons list (target, attack type, TN, damage).
- Going prone and other odd movement options: a button in the movement plan section, normally hidden.
- Spot: select a target and a Spot button appears beside it. Spotting after weapons are assigned warns that TNs change.
- TAG: an attack with its own short phase before the Ranged Attack Phase, skipped when no friendly side needs spotting.
- Artillery: targets hexes (already planned).
- Shut down: an option on the engine in the unit's critical stats page. Eject: an option on the cockpit.
- Most remaining choices are toggles that stay set, or a warning the player accepts.

**Setup.** Options tab: every option is player-facing ("its their game to set up"); organising it comes later.
Declaration style (simultaneous / take turns) is a setup option.

**Line of sight between two hexes (Q5).** Defender's choice: a human defender picks when declarations take turns; a bot
defender picks defensively unless it wants to shoot back. MegaMek, from a partial source read (**NOT VERIFIED**: most of
`LosEffects.java` came back as a model summary, the firing-phase server code was not reachable): `losDivided()` is called
when the angle falls on a hex edge, its comment says the situation resolves in favour of the defender, and it picks the
side with the larger to-hit modifier automatically; no player choice. MegaMek's options `simultaneous_firing`,
`simultaneous_targeting`, `simultaneous_physical` all default to off; what they change was not confirmed.

**Known shortfalls (Daniel: leave out for now, record that they are missing):** ejection and voluntary shutdown. Their
solution is recorded above; the UI controls come later. Other unit types: later.

## 13. Heat Phase and End Phase decisions (Daniel asked)

Heat is mostly rolls. The real choices, from the code (`heat.rs`, `orchestrator.rs` `phase_end`):

| Choice | When | Suggested control |
|---|---|---|
| Heat sinks on / off, how many stay on, so heat can fall to a minimum next turn | End Phase | Toggle on the heat bar; sticks until changed |
| Use a coolant pod this turn | Heat Phase | Button with a count on the heat bar |
| AMS on / off per system | End Phase | Toggle on the equipment page; sticks |
| Blue Shield on / off | Start and End Phase | Toggle on the equipment page; sticks |
| Command console: swap pilot and console warrior | End Phase | Toggle / button when a console exists |
| Which ammo bin explodes when several tie | During the Heat Phase | A prompt only on a tie (book: the controller chooses) |
| Voluntary shutdown | End Phase | Not built (known shortfall) |

Everything else in those phases (shutdown and ammo-explosion avoid rolls, restart, life-support damage, wake-ups, crippled
and destroyed checks) is a roll with a report, no choice. Radical heat sinks / MASC / supercharger are decided in
Movement, not here.

## 14. More decisions from Daniel, 2026-11-21 (later the same day)

- **Equipment switches live in the critical hit tables**, as in MegaMek: coolant pods, AMS, Blue Shield, radical heat sinks,
  heat sinks and the other after-physical-phase equipment. A switch set before the Heat or End Phase counts from next turn.
  Radical heat sinks and coolant pods also get a **button that appears when the unit's expected end-of-turn heat is above 0**.
- **Ammo and coolant pod use are automatic** unless the player picks bins by hand. Automatic order: Center Torso, side
  torsos, arms, legs, head. (The engine today draws from the bin with the fewest shots left, `ammo.spend`; the human's
  units need this order, a small engine change.)
- **Auto eject** switches itself on when an ammo explosion could destroy the Center Torso, and is on when the only ammo is in
  the head; a warning shows when there is head ammo and auto eject is off. Ejection is not built (Section 12), so only the
  switch and the warning can exist until it is.
- **Simultaneous / declaration-order options wait until one player works.** They matter in two-player games. When built:
  an explicit declaration order, and the bots must react to it (a bot that knows a unit yet to fire is about to be
  destroyed has no reason to hold back its own firepower for heat).
- **Priority: a working model, issues and all, cleaned up later.** Use the engine's own choices (simultaneous declaration,
  the stub defaults) to get running.

## 15. First playable slice (proposed; "one player in the game")

Scope: one human controls one or more units against bots, in the desktop Combat Lab (a native server can block a thread
while it waits for the human; the browser build cannot, see below). Engine stubs for everything not listed. No declaration
order, no mid-game option changes, no take-control during replay, no spotting / TAG / artillery yet.

| Part | Work |
|---|---|
| E1 | `HumanBots`: a `BotSet` that hands a human unit's decisions to a controller (a channel) and waits; every other unit goes to its normal bot. Every human answer is written to a decision list (the basis for replay, branching, take-control). |
| E2 | Movement queries: what a unit can reach per mode with turn MP, hazards and stacking along a waypoint path; build the `Pick` from a confirmed path. |
| E3 | Fire queries: per target and weapon, the TN with its parts, legality (arc, range, ammo), ammo bins, modes. |
| E4 | Build a `DeclChoice` from the player's assignments (the torso twist / arm flip chosen automatically, Section 12). |
| E5 | The physical attack list (type, TN, damage) and `choose_physical` from the player's pick. |
| E6 | A battle-state snapshot and event stream for the screen (reuse `history.rs`). |
| S1 | Lab server endpoints: start a game, get the state, wait for / submit a decision. |
| F1-F4 | Wire the mockup to real data: map and placards, move, fire, physical; the End Phase switches page. |

**Browser build.** `wasm/src/lib.rs` is one request, one answer, and a WASM call cannot wait. Two ways to get a human into it
later: replay-from-the-decision-list (deterministic engine; re-run to the first unanswered decision, ask, repeat; costs
replay time per decision), or a worker that blocks on the page (needs cross-origin isolation headers, which a static host may
not give). The decision list from E1 is what both need, so the native slice does not block the browser.

## 16. Status of the first playable slice (2026-11-21, end of the day)

Built and tested: **one person plays one or more teams against bots in the desktop Combat Lab, through a phone-sized page.**
Set a team's bot to Human on the Lab's team panel, press Play (next to Run Simulation); a new page (`play.html`) opens and the
battle waits for each of the person's decisions. Tested by `core/tests/human_bots.rs` (pass-through = same log as a plain run),
`core/tests/play_session.rs` (a scripted player plays a battle; an illegal answer is asked again), `tests/check_play.py` (the
Lab's calls; same seed and same answers = same battle, which replay needs), and `tests/play_page_e2e.js` (a whole battle played by
tapping the real controls at 390 x 780; not in `run_checks.py`).

| Part | State |
|---|---|
| E1 `HumanBots` + decision list | Done (`core/src/human_bots.rs`) |
| E2 movement query | Done: every end state (hex, facing, mode) with MP, hexes moved, TMM, heat, piloting rolls and hazard damage; hexes a friend occupies are not offered. The engine finds the path itself (a waypoint path is not sent) |
| E3 fire query | Done: per weapon, TN, expected damage, heat, range band, in range or not, whether it needs a torso twist |
| E4 declaration from the player's weapons | Done; torso twist / arm flip chosen automatically (first arc action that lets every picked weapon fire) |
| E5 physical attack list | Done in a simple form: the attack kinds the engine offers now (no twist choice for physical attacks) |
| E6 state for the screen | Done: units (hex, facing, damage by location, heat, prone, shut down), the board, new log lines with each question |
| S1 Lab calls | Done: `play_start`, `play_poll` (waits), `play_answer`; a Human team cannot go into a batch run or estimate (refused in words) |
| F1-F4 page | Done as a NEW lean page in the SL-HIS Dark look, not the mockup ported: pan / zoom, reach tint with only the outer border, facing arrows, weapon table with Alpha strike, heat projection, physical list, report, unit chips with damage and heat |

**Not built yet (known gaps, in the order I would take them):**
1. Waypoint building, the black path for a charge / DFA, the Charge / DFA button, a stand-up button; `Pick` has charge / DFA flags, nothing sets them.
2. Weapon modes and ammo: the engine's own defaults decide (rate of fire, munition kind, bin order). The automatic bin order of Section 14 is not in.
3. The equipment switches in the critical-hit tables, the End Phase heat button, auto eject (ejection itself is a known shortfall).
4. Spot, TAG, artillery hexes (the engine's stubs stay in charge), the Charge mode on a PPC capacitor.
5. Take-control checkbox during replay; declaration order and simultaneous / turn-taking options; recording option changes mid-game.
6. The mockup's look and features (MegaMek sprites on hex bases, placards, long-press cards, detail sheet tabs, colour-blind mode, other looks).
7. The browser (WASM) build: nothing of this is in it; a Human team there needs the replay-from-the-decision-list route (Section 1).
8. A game is held in memory by the Lab: closing the Lab ends it. Saving and resuming a game is not built (the decision list exists in memory only).
9. The to-hit shown is the weapon's TN from the engine's weapon picker; cover, secondary-target and similar modifiers are inside it, but the page does not itemise them.

## 17. Second pass (2026-11-21, evening): what was added to the first slice, and what is still missing

Daniel: "Skip 5 and 7. Work on getting everything else working." (5 = take-control checkbox, declaration order, option changes
mid-game; 7 = the browser build. Saving and resuming a game is "if we have spare compute".) Built and tested, in the order of
Section 16's gap list:

| Gap | Now |
|---|---|
| 1. Charge / DFA, stand-up, path | **Charge / death from above:** the movement question lists the stops next to an enemy that has moved (or cannot), with to-hit, damage and the damage you take; tap an enemy, the stops go black, pick one, the route turns to colour, a confirm popup says what the attack is, Yes = the move, No = back up. A real charge was played in a test game. **Stand up:** asked before the roll with its target number (stand up, or stay prone); the engine always stood a unit up before. **Route preview:** a query returns the route the engine will walk (with the MP at each step) and the page draws it. |
| 2. Weapon modes and ammo | The weapon table has, per weapon: **Mode** (ammunition kind / guidance, incl. distant artillery), **rate of fire** (Ultra / Rotary), **Ammo** (which bin it draws from, shots left), **Charge** (PPC capacitor, lightning icon). Choices stay until changed (`core/src/player_choices.rs`; read by the stubs only for a person's units, so every simulated battle is unchanged: the 91 reference battles still match). A person's unit draws ammunition in the order Center Torso, side torsos, arms, legs, head (fewest shots first inside a location) unless a bin is picked. |
| 3. Equipment switches, End Phase | **Unit sheet > Equipment** (any time a question waits): heat sinks left off, coolant pods (automatic / hold / use), radical heat sinks, MASC / supercharger, each AMS, Blue Shield, jammed weapons (try to clear next turn), capacitors. **Before the Heat Phase** a question appears when expected end-of-turn heat is above 0 and the unit has coolant pods or radical sinks, or when a weapon is jammed. **MASC / supercharger** is asked at the start of each move (the roll is made before the move). Auto eject: only a note and a head-ammo warning; ejection is not built. |
| 4. Spot, TAG, artillery, capacitor | **Spot** (`spot` question at the start of the Ranged phase, listing enemies a friend without line of sight could then hit). **TAG** (its own question before the Ranged phase: target, 'Mech or hex, with to-hit numbers). **Artillery:** the distant shot shows as a Mode on the weapon; the aim hex is set by tapping the map (tested through the Lab calls, not tapped in a browser). **Capacitor:** the Charge button (not played in a test game). |
| 6. Look and features | Detail sheet (Summary, Armor, Criticals, Equipment); press-and-hold a hex or a weapon for a card; range bands and the **firing arc** of the weapon in focus on the map (shaded = outside its arc, dashed = in its arc only after a torso twist / arm flip; rear-mounted weapons show the rear arc); placards under each token (name, armour + structure bar, heat bar); nested menu with Look (SL-HIS Dark / Light, Windows 95, Modern), colour-blind mode (second palette, line patterns, letters on the range bands), view switches; the choices are remembered on the device. |
| (new) To-hit parts | The declaration lists the parts of the base number (gunnery, your movement, target's movement, line of sight, cover, heat, prone target, stealth, other), and each weapon's own modifier on hover. |

Also fixed on the way: the move-order question was being asked during the engine's forecast of the move queue (about 4 times a
move); a person is no longer asked in a forecast (`BotSet::move_pick_forecast`).

**Still missing (honest list):**
- **Waypoint steering.** The engine chooses the route to the end hex itself (cheapest, avoiding hazards); the page shows that route but you cannot steer it with waypoints. Needs an engine change (a path through given hexes).
- **Going prone** (and other odd movement options): the engine has no voluntary prone move.
- **Ejection and voluntary shutdown** (known shortfalls); auto eject has only a warning.
- **Spot and TAG are questions at the start of their phases**, not a Spot button next to the chosen target (the engine decides them before targeting). Hex-only artillery targeting is not possible: an enemy must be the target, and the aim hex can be changed.
- **Placards can overlap** each other and units (no placement pass like the mockup's); no MegaMek sprites (licence and art not checked); the Win95 list screens and the timeline screen; the combat report is the raw log, not a formatted popup.
- **Not tried on a real phone**; only a 390 x 800 headless browser. Colour-blind palettes not checked with a simulator.
- Not built by choice: 5 (take-control checkbox, declaration order, option changes), 7 (browser build), saving and resuming a game (spare compute).

## 18. BattleROM in the browser (2026-11-22; Daniel: "Getting the browser version built and pushed to the public website")

Item 7 (the browser build), which Daniel had skipped, built. REVIEW PENDING (higher-level model).

**The problem.** The browser's engine module has no threads and cannot wait, but a human battle must stop at every question
until the person answers. **How it works.** One Web Worker plays the whole battle (`engine/wasm/web/playworker.js`) and
simply BLOCKS inside the engine's call: the question goes out to the page (`host_play_post`), and the engine then calls
`host_play_wait`, which sleeps on a shared buffer (`Atomics.wait`) until the page writes the answer, or a query (a route,
a weapon's mode), into it. The engine code is the same as the desktop's: `play_session.rs` now reaches the person through
a small `Link` trait (the desktop's is `Game`, the battle on its own thread; the browser's is `PageLink` in
`engine/wasm/src/lib.rs`), and `play_blocking` plays the battle on the caller's stack. `engine/wasm/web/engine.js` keeps what the
desktop server keeps (the question waiting and its number, the end, the query in flight), so `play.js` and `lab.js` use the
same `play_poll` / `play_answer` / `play_query` calls in both builds.

**Cross-origin isolation.** A shared buffer needs the page to be "cross-origin isolated", which means two response headers a
static host such as GitHub Pages cannot send. `coi-sw.js` (a small service worker) adds them; `coi.js` installs it and reloads
the page once. After that first visit the pages are isolated. A browser that refuses service workers (some private windows)
gets a plain sentence from Play saying so; the batch runs do not need any of this.

**How a game starts in the browser.** The Lab page checks the setup (`play_check`: the same mistakes-in-words check a batch
makes), leaves it in `localStorage` (`bm_play_setup`) and opens `play.html`, which starts the battle in a worker of its own.
Closing the play tab ends the game (saving and resuming is still the spare-compute item, Section 17).

**Checked** (`tests/check_web_play.py`, in `run_checks.py`'s website group): the same scripted player, same setup and seed, on
the desktop Lab and in the browser gives the same 109 answers to the same questions and the same battle (winner, turns,
final units); queries work while a question waits; a Human team in a batch run, and Play without a Human team, are refused in
words; on a plain static server the service worker isolates the page by itself; the real play page plays a whole battle by taps
in a phone-sized window with no page error.

**Not done / to watch.** Not tried on a real phone. iPhone Safari needs the service worker too (supported since iOS 15.2).
The play tab holds the battle in memory only. A panic in the engine during a human game ends it ("the engine stopped"), as on the desktop.

## 19. First impressions from Daniel (2026-11-22) and what was done

Daniel, after trying the browser version: (1) cycle through the 'Mechs checking movement options before committing one: it locked
you into the first unit selected; (2) the player has control during deployment too, within the game's deployment rules; (3) the
map should be the same map as in the replay and the map browser; (4) the turn button did not work when another unit was in the
hex you wanted to turn towards; (5) most of the functionality of the art demo (the mockup) is missing.

| # | Now |
|---|---|
| 1 | The move-order question is the movement screen. Tap any of your units (map or strip) to see its reach, plan its move (hex, turn, mode) and press Move!: the answer carries the unit and the planned move (`move_order` answer {unit, plan}), and that unit's movement question is then answered from the plan (`Screen::plan`, `ask_with`). New queries while the question waits: `reach` {unit} (the movement question's own view for any unit that has not moved) and `path` {unit, ...}. A prone unit cannot be previewed (it stands up first). If boosting (MASC) or anything else changes what is legal between planning and moving, the movement question is asked normally with a sentence saying the plan no longer works. |
| 2 | A `deploy` question (`orchestrator::start_battle_with` / `DeployHook`, `Controller::deploy`): where the rules place units before turn 1 (home edge row up to the deployment depth, or a placed zone), the person's units are placed by the person, taking turns with the bots as the engine already does. Green hexes are the legal ones; tap one, tap an arrow to face, Place here. Units that walk on instead (the rulebook's walk-on, or a walk-on zone) are still chosen in the movement question. |
| 3 | `engine/lab/web/boardart.js` is the one painter of a map's hexes; the Lab's map preview and the play page both call it (the play page draws it once into an image under the interactive layer), so a map looks the same. The replay page (`INTEGRATION__replay_viewer.html`) still has its own, simpler painter: not changed. |
| 4 | The turn arrows are rebuilt: a ring of triangles hugging the hex, one per facing the unit could end in, none on the side it faces, coloured by the mode that facing needs, on the top layer with a big tap area. Tested with a friend standing in the hex an arrow points at (`tests/check_web_play.py`, a real mouse click). I could not reproduce the old failure exactly (the old arrows were also drawn above units); the new ring cannot be covered by a unit. If it still fails for you, tell me what you tapped. |
| 5 | Added from the mockup: the enemy strip (chips with % left and a red top), your force strip below the map, the info bar as an overlay on the map, sprites on tinted hex bases, placards with the three bars (A armour, S structure, H heat) placed so they do not cover each other with leader lines, the action cluster over the map (MP used / allowed, TMM, the big Move! button, the x for undo, Esc), the first view zoomed on your own units. |

**Still missing from the mockup (honest list):** waypoint steering (numbered waypoints, step counts per waypoint; the engine always
walks its own cheapest route, so showing waypoints would be a lie until the engine can walk a chosen one); the left weapons
panel (fire-control target symbols, grouping, sort, the Strike / Alpha Strike cycle, previous / next target arrows: the weapon table
is still a table in the sheet, and the target is still picked in its own question before the weapons); the detail sheet with
the flick, tabs Plan / Weapons / Stats / Armor and the armour silhouette with pips (the current sheet has Summary, Armor, Criticals,
Equipment); the formatted combat report popup; hazard confirm popups; MegaMek sprites (licence unchecked; the sprite is a plain
silhouette); landscape and wide layouts, the Terminal and Amber looks, text size S / M / L, the REC button and the Anatomy overlay;
the dashed-outline-plus-band range display (reach is still tinted hexes with a dashed border).

