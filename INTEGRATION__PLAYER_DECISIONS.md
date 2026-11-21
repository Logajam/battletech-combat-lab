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

**Structural problem to settle before any UI work.** These calls are synchronous: the orchestrator calls a bot and gets the
answer back immediately. A human answers in seconds, and in the browser build (WASM, one thread) nothing can block. The
engine already has a way round this: `ReplayBots` plays a battle back from recorded decisions, and the engine is
deterministic from the seed. So a human turn can be "re-run from the start with every decision recorded so far; stop at
the first decision with no answer and ask for it". That fits "the game records decisions" and the branching idea
(truncate the list, change one answer). It costs replay time that grows with game length (fine for a 20-turn game; to be
measured), and it is the easiest of the options. The alternative, turning the orchestrator into a resumable state machine,
is a large rewrite. This is my reading of the code, not a tested design. **Decision for Daniel / next session, before step 2.**

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

1. Players choose the order units move in (the book), instead of the engine's move index? Same for the order of declarations?
2. Human versus bot in the same battle: does the bot see the human's declaration before it declares (sequential), or do both
   declare blind and then resolve (the engine's current simultaneous rule, which also matches the book)?
3. The rules-switch list: which of the 153 settings are player-facing? I can draft the sort for you to correct.
4. Which Section 9 items, if any, are wanted for the first playable version (ejection and voluntary shutdown are the
   likeliest)?
5. Line of sight between two hexes: leave as "worse for the shooter" or build the defender's pick?
