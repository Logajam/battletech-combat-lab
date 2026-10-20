# Mech-vs-Mech Integration — Project Map

Single source of truth. Replaces `INTEGRATION__PROJECT_MAP.md` (old),
`MECHSIM____BattleTech_Sim___Project_Map.md`, `PATHFINDER__PROJECT_MAP_movement.md`,
and both projects' `DESIGN_NOTES*`/`CALL_GRAPH*`/`CHANGE_RECORD_ARCHIVE*` files.
Those are superseded — don't consult them. History before 2026-08-28 is
archived, not carried forward here; this doc tracks current state and
open items only.

**Naming:** `MECHSIM__*` / `PATHFINDER__*` = source-project files, kept as
reference. `INTEGRATION__*` = new orchestrator files. Never let one
source project's file overwrite the other's same-named file.

---

## 0. WHERE WE ARE (2026-10-20) — read this first

**Hand-off for a new instance.** Daniel's goal: "beat the simulator into
shape." He is not a GitHub person - **Claude runs the logistics** (Daniel,
2026-10-20: "You're in charge of the logistics"): work on the session's
`claude/...` branch, commit, push, open a PR to `main`, and merge it once the
tests pass; tell Daniel in plain words what changed. Section 7 has the
standing instructions; the Change Record (Section 8, newest first) has every
change with page cites.

**It runs end to end.** `.mtf` in → turn-by-turn battle on a real board →
batch summary out:
```
git clone https://github.com/Logajam/battletech-monte-carlo-sim
cd battletech-monte-carlo-sim
python INTEGRATION__main.py
```
Needs Python 3 and NumPy (`pip install -r requirements.txt`). Settings (mech
files, board, seed, batch size, every knob) are in `INTEGRATION__config.py`.
Default: Asymptote II (a tripod) vs Asymptote II on 16x17 Grassland, seed
12345, 1 battle, verbose, home-edge deployment. Layout: `INTEGRATION__*.py`
at the top; `mechsim/` and `pathfinder/` hold the source-project modules;
`data/` the boards, test mechs and `meks.zip` (4,227 MegaMek units, 4,162
parse - unzip outside the repo to use one); `rules/` the rules library zip;
`reference_logs/` same-seed sample battles.

**After any change, from the repo root:** every `tests/test_*.py` (9 files,
all must pass), `python tests/check_reference_logs.py` (must pass unless the
change is MEANT to alter results - then look at a fresh battle and run
`--update`; Daniel has OK'd regenerating them for intended changes), and for
anything on the hot path `python tests/benchmark_turns.py` (10 turns of the
default battle; ~11 s on Daniel's machine after the 2026-10-20 speed pass, an
estimate from this container's 21.5 s → 16.3 s; a pure speed change must keep
its HP totals). Batches run several battles at once, one per CPU core
(`config.WORKERS`); the output is identical to running them one at a time.

**What's built (all Core Rulebook, page-cited in the code):**
- Movement: `INTEGRATION__movement_selection.choose` scores every reachable
  spot by dealt / (received + movement-PSR cost + .001), exposure- and
  structure-weighted, TWO-PLY for the first mover (it scores each spot by the
  second mover's modeled reply). Closing fallback when nothing deals damage.
- Arcs and arc actions (`INTEGRATION__arcs`, Section 4a): firing arcs, torso
  twists in both attack phases, tripod any-hexside twists and leg arcs,
  reversing arms, quad turrets.
- Ranged combat: heat-limited weapon choice, to-hit modifiers, attack
  direction, cluster groupings, ammo, rear-mounted weapons, aimed shots.
  Next to the target the Ranged phase picks its twist and fire TOGETHER with
  the physical attack that will follow (holding back an arm weapon worth less
  than that arm's punch).
- Physical: all seven attack types - punches, kicks, physical weapons, clubs
  (`INTEGRATION__clubs`, pick-up OFF), pushes (valued by displacement: off the
  board = the target's whole HP, 2+ levels down = the fall), charges and death
  from above (`INTEGRATION__charge`, `INTEGRATION__dfa`, decided in movement by
  `INTEGRATION__movement_attacks`: gated per movement mode on beating the best
  ordinary attack, then scored like any spot; the first mover's two-ply
  anticipates them). Each weighted by its own hit table (`physical.Worth`).
- Heat (pp.102-107) and heat equipment (`INTEGRATION__heat`,
  `INTEGRATION__equipment_systems`), piloting rolls, falls (multi-level),
  displacement, deployment from home edges.
- Remaining loud stubs (`INTEGRATION__stubs.py`): weapon data gaps
  (`ammo_data`, `unconfirmed_weapon_data`, `unknown_damage_type` - weapons not
  in the Core tables) and `heat_explosion_bin` (a controller choice).

**Pick up here (open, roughly in Daniel's priority order):**
0. **Rules review** (`INTEGRATION__RULES_REVIEW.md`, started 2026-10-20):
   its "Gaps" list is Claude's to build (backward walking done 2026-10-20); its
   "for Daniel" list needs his calls; chapters still to review are listed
   at its top.
1. **The bot's future-capability planning** - Section 6 "Memo" (Daniel,
   2026-10-20). Needed for clubs, MASC, Rotary ACs and similar.
2. **Hanging back** (seen 2026-10-20): in Asymptote vs HeatGear sample
   battles the Asymptote spends turn after turn at range 5-9, outside its
   medium pulse lasers' reach, firing nothing (one battle hits the 50-turn
   cap). Daniel: "can wait" - other rules may fix it, or it goes with the bot
   thinking work (item 1). Likely suspects: the dealt / received ratio and
   the closing fallback.
3. Attack-caused PSRs (kick, club, push, charge, DFA, 20+ damage) aren't
   priced in movement scoring - Daniel's rule so far is "only Movement-phase
   PSRs count". Pricing them would make kicks / charges / pushes worth more.
4. Waiting on Daniel (Section 4): the Core-vs-MECHSIM piloting-roll
   questions; does HOLDING a club stop arm / torso weapons firing (Core p.79
   only bars arm weapons in the club-attack turn; check Total Warfare)?
5. Other follow-ups: terrain PSRs / mines in a spot's cost; structure
   weighting in the real Ranged weapon choice; HP awareness (the ratio ignores
   damage state, so tiny-damage / no-return-fire spots can win through the
   .001); domino effects (no third mech); turret crits lock at the last
   declared direction; weapon data gaps (stubs above); `PROMPT_FOR_MAP` /
   `STITCH_MAPS` not built.
6. Units for wider testing: `data/meks.zip`. LAMs, ultralights (< 20 t) and
   superheavies don't parse.

**Housekeeping:** reference logs regenerated 2026-10-20 (physical attacks,
then club pick-up off) and match the code. Speed history: 31.7 s → 11.8 s (speed pass) →
~14.5 s (all seven physical attacks) → about 25% less (2026-10-20 memo
sharing), plus parallel batches, for the 10-turn benchmark. Rules are
checked against `rules/Battletech_Rule_Reference_Index.zip` (Section 7) - the
`[p.N]` marker in its markdown PRECEDES page N's text.

---

## 1. SCOPE

Two fully-specified mechs (parsed `.mtf` + pilot skills) + one map →
repeated simulated battles, full turn-by-turn movement/positioning/LOS/
to-hit/per-location damage-crit-PSR resolution, until destruction or
turn-limit → reset, repeat, aggregate stats (win rate, survivor
condition, attacks-to-kill, cause-of-death).

Neither source project alone does this: PATHFINDER has real positioning/
to-hit but a flat-float placeholder HP pool; MECHSIM has real per-location
damage/crit/PSR but only fires an abstract table at one static mech (no
opponent, no positioning, no to-hit). **As of 2026-10-18 the integration
does both, with stubs where rules are missing.**

---

## 2. TURN STRUCTURE (Daniel, 2026-07-25 — build target)

1. Pick map, pick mechs.
2. **Initiative** — roll; loser acts first this turn.
3. **Movement** — turn 1: loser enters from their edge, winner from
   opposite edge; turn 2+: continue from position. Loser moves first both
   cases.
4. **Ranged Combat** — loser fires first, winner second; effects resolve
   simultaneously.
5. **Physical Combat** — if eligible. *(deferred — see Section 4)*
6. **Heat** — heat effects applied (Core Rulebook pp.102-107, 2026-10-19).
7. **End Phase** — cleanup. *(scoped to unconscious-pilot recovery roll only
   — see Section 4)*

| Phase | Where | Status (2026-10-18) |
|---|---|---|
| Deployment | `orchestrator._deploy_home_edges()` | **REAL (Core p.37):** deployment roll, loser picks a home edge (`config.HOME_EDGE_CHOICE`), winner opposite; mechs enter along it on turn 1. `config.DEPLOYMENT = "fixed_hexes"` keeps fixed starts. |
| Initiative | `orchestrator.roll_initiative()` | **REAL**, Daniel-confirmed 2026-08-31. |
| Movement | `orchestrator._phase_movement()` | **REAL:** damage- and heat-aware MP (TSM, MASC/supercharger), immobile (shut down / unconscious) skip, full Walk/Run/Jump envelope with expected dealt/received per spot (`INTEGRATION__ranged_combat.evaluate_going_second`), unconscious-skip, stand-up (`resolve_stand_up`) then move on with the remaining MP (p.51), movement PSR for Run 1+ hex / Jump (`check_movement_psr`; none for Walk, p.111), consciousness checks. The pick: `INTEGRATION__movement_selection.choose`. |
| Ranged Combat | `INTEGRATION__attack_resolution.py` | **REAL:** LOS, rear arc (only rear-mounted weapons fire into it), TN = gunnery + AMM + TMM(actual hexes moved; -4 if immobile) + LOS + range + heat + weapon / targeting computer / arm-crit / sensor / prone modifiers, shut-down mechs don't fire, heat- and ammo-constrained weapon selection, real to-hit rolls, attack direction from geometry, cluster table with Core groupings (Streak, MRM), hit location, damage, crits, explosions, floating TAC, head hits, aimed shots, ammo use, Attack Phase PSR, consciousness. Both sides declare before damage lands (simultaneous). **STUBS:** `unknown_damage_type`, `unconfirmed_weapon_data`, `ammo_data`. |
| Physical Combat | `INTEGRATION__physical.run_physical_phase()` | **REAL (Core pp.76-83):** all seven attack types - punches, kicks, physical weapons, clubs (`INTEGRATION__clubs`), pushes, charges and death from above (`INTEGRATION__charge` / `INTEGRATION__dfa`, declared in Movement via `INTEGRATION__movement_attacks`); bot picks the most expected damage, weighted by hit table. |
| Heat | `orchestrator._phase_heat()` → `INTEGRATION__heat.resolve_heat_phase()` | **REAL (2026-10-19, Core Rulebook pp.102-107):** heat carries over; += movement heat (Walk 1 / Run 2 / Jump, Improved JJ, XXL, super-cooled myomer) + weapon heat + engine-hit heat (5/10) + stealth heat − dissipation (+3 Partial Wing, radical heat sinks, coolant pods); then shutdown roll or restart, ammo and inferno explosion rolls (re-rolled after inferno heat), life-support pilot hits, and next turn's MP / to-hit / TSM effects. End Phase: heat sinks switched off to hold min_heat. **STUB:** `heat_explosion_bin` (bin tie-break needs shot counts). |
| End | `orchestrator._phase_end()` | **REAL:** wake-up rolls, crippled tracking, destruction check. |

Resolved 2026-10-18 (Daniel): TMM uses **actual hexes moved**
(`combat.fc_to_tmm`), not MECHSIM's max-available-MP `compute_tmm()`.

Open question, not decided: does "winner sees loser's result before their
own fire resolves" matter for a headless batch sim with no bot reading it
mid-phase? (Current build: no — both declare first, then both resolve.)

---

## 3. FOUR-PILE FRAMEWORK

1. **When in the turn** (turn-flow control)
2. **Who am I** (mech state)
3. **Where am I** (map/LOS/movement)
4. **What am I doing** (bot decisions — cross-cutting, not a module; see Section 6)

| Pile | Files |
|---|---|
| 1 | `INTEGRATION__orchestrator.py`, `INTEGRATION__results.py`, `INTEGRATION__stubs.py` (registry). Reference only, not imported: `PATHFINDER__combat_turn.py`, `MECHSIM__sim_runner.py` (see Section 5). |
| 2 | `INTEGRATION__heat.py`, `MECHSIM__mech_state.py`, `damage_resolution.py`, `armor_rules.py`, `piloting_rolls.py`, `hit_location.py`, `mtf_parser.py`, `equipment.py`/`.json`, `INTEGRATION__config.py`, `INTEGRATION__attack_resolution.py` (resolution half) |
| 3 | `PATHFINDER__hex_geometry.py`, `board_parser.py`, `terrain_rules.py`, `pathfinder.py`, `los.py`, `combat.py` (movement/rear-arc/TMM pieces) |
| 4 | Scattered — see Section 6, not a file |

---

## 4. OPEN ITEMS

**Movement-selection follow-ups (Daniel, 2026-10-19):**
- Terrain that forces a piloting roll on entry, and mine fields: add expected
  damage to the spot's cost (denominator), as the movement PSR already does.
- (Built 2026-10-19: internal-structure weighting, see Change Record.) Still
  open there: aimed shots at immobile targets, and using the same weighting in
  the real Ranged Combat weapon choice (movement scoring only for now).

**Stubs (all in `INTEGRATION__stubs.py`, knobs in `INTEGRATION__config.py` STUB SETTINGS).**
Each docstring carries a TODO naming what to check (MegaMek names in those
TODOs are from memory — grep before relying on them).

| Stub | What it does instead | Needs |
|---|---|---|
| `unknown_damage_type` | null damage_type → BALLISTIC | equipment.json curation (weapons not in the Core tables) |
| `unconfirmed_weapon_data` | Loud warning; weapon never fires | equipment.json curation - special-rules weapons (MG arrays, TAG, AMS, SRTs, HAG damage, MML modes, plasma, VSP damage...) |
| `ammo_data` | Unlimited ammo for a weapon with no shots_per_ton (HVAC, Improved AC - not in the Core tables) | shots_per_ton from Tactical Operations tables |
| `heat_explosion_bin` | Heat ammo explosion: bins still tied on damage value AND shots left picked at random; unknown-damage bins count as 0 | A controller policy (pile 4) |

Replaced by Core Rulebook rules 2026-10-19 (Change Record): `attack_direction`
(p.73), `cluster_grouping` (pp.87, 181), `post_standup_movement` (p.51),
`walk_movement_psr` (p.111), `to_hit_modifiers_not_applied` (pp.66-67, 97-98,
184-200), `rear_mounted_weapons` (p.60), `ammo` / `one_shot` (pp.72-73, 95,
180-182), `deployment` (p.37), `physical_combat` (pp.76-83, partly).

**Rules gaps with no runtime flag** (also printed in every summary):
shoulder / head turrets (not Core) and the twist / flip a TAG designation
uses up (TAG doesn't fire yet) - Section 4a; LB-X/Ultra/Rotary multi-shot math;
Artemis/HAG/ammo variants; heat sources with no terrain model yet (water,
snow, fire, extreme temperatures) and inferno missiles (bins aren't fired
from); heat decisions (cooldown, voluntary shutdown); stealth armor /
Void-Signature hostile-ECM side effects; torso-mounted cockpit PSR/sensor
rules; domino effects (no third mech); jumping onto the board at deployment;
tripod leg sub-roll uses Python `random` (seeded from SEED, not the
BattleRNG stream).

**Core Rulebook vs existing MECHSIM rules - Daniel to decide** (found
2026-10-19 while replacing stubs; MECHSIM left unchanged because these are
confirmed project rules, not stubs):
- Standing up (p.51, PSR table p.111): each attempt is a PSR at -1;
  `resolve_stand_up` uses no -1.
- Tripod with no leg destroyed: -1 to PSRs (p.111); MECHSIM uses -2.
- Preexisting leg destroyed: +4 (p.111, "jumped with leg destroyed +4");
  MECHSIM uses +5.
- Quads only need a PSR to stand if a leg is destroyed (p.231).
- Rear arc: Daniel's 2026-07-20 rule was one hexside (60 degrees); the p.60
  Firing Arcs Diagram (screenshot, 2026-10-19) shows 120 degrees, and
  `INTEGRATION__arcs.py` now follows the diagram (agrees at range 1).
  PATHFINDER's `combat.in_rear_arc` (not wired) still has the old rule.

**TODO noted in code:** a failed movement PSR drops the mech in its END hex;
in tabletop play it falls where the check was failed
(`orchestrator._phase_movement`).

**Other open items:**
- `config.PROMPT_FOR_MAP` picker not built — always loads `DEFAULT_BOARD_PATH`.
- `STITCH_MAPS` raises NotImplementedError (stitch_boards itself is ready).
- ~~Full `MECHSIM__equipment.json` not available (only the 14-entry
  mini)~~ RESOLVED 2026-10-19: the full DB is now `mechsim/equipment.json`
  (689 entries, 166 verified; 279 weapons, 144 with damage stats). Improved
  Jump Jets and Endo Steel are recognized; jump-jet crits now reduce jump MP.
  Its `_meta.entry_count` says 1086 - stale, the file holds 689.
- 2026-10-19 rulebook fill pass (see Change Record): 176/279 weapons now have
  damage + heat + range (was 144). ISLBXAC10 fires (as a flat slug - LB-X
  cluster mode still not modeled). Still unfilled, by design: special-rules
  weapons (ATM/iATM, HAG, MML, VSP, Heavy Gauss, Snub-Nose PPC, artillery,
  Narc, mortars, plasma, TSEMP, AMS, pods, MG arrays, Silver Bullet Gauss),
  footnoted damage cells (flamers, Nail/Rivet Gun), one-shot launchers
  (stats copied from base launchers 2026-10-19 - see Change Record),
  and items with no table row. `shots_per_ton` filled 2026-10-19 (107 weapons; ammo is tracked).
- ~~Minimum range not applied~~ RESOLVED 2026-10-19: penalty applied in
  `weapon_selection._weapon_range_mod` (+1 per hex inside minimum; missing
  `range.min` = 0). One-shot launchers carry their base launcher's stats;
  the fire-once limit is enforced since 2026-10-19 (`INTEGRATION__ammo`).
- Pile 1 reconciliation: `sim_runner._resolve_hit`/`resolve_weapon_attack`
  are absorbed (`INTEGRATION__attack_resolution`). `combat_turn`'s two-ply
  search and closing-fallback are NOT — don't delete `combat_turn.py` until
  movement selection replaces them or Daniel decides they're not wanted.

**Weapon data model gaps:** LB-X/Ultra/Rotary cluster math,
HAG range damage, Artemis, ammo variants (inferno effect on targets). The
one-shot fire-once limit is enforced since 2026-10-19.

**Cross-cutting hazard — RESOLVED 2026-10-18:** the
load-MECHSIM-then-purge-then-load-PATHFINDER workaround in
`INTEGRATION__weapon_selection.py` deleted `INTEGRATION__config`'s own
`config` registration and made the next `import config` fail (confirmed by
a live import test). Removed. Both directories now go on `sys.path` once.
No PATHFINDER module used by the battle loop imports `config`.

**Deferred by explicit scope call, not gaps:**
- End Phase beyond unconscious-pilot recovery (heat restarts happen in the
  Heat Phase, p.105; voluntary End Phase shutdown is a bot decision, not built).

**Source-project backlog** (not integration-blocking, real but unwired):
- MECHSIM: Clan free CASE auto-injection at parse time; Reactive Armor's
  full secondary crit roll (only flat halving is wired); Modular Armor;
  Shields (no spec); Superheavy/Compact engine 2-hit exception; LAM/exotic
  Config types; `equipment.json` curation (166/689 entries verified,
  rest generic padding); PSR special cases (quad-all-legs, AES-in-legs,
  Tripod, small/torso cockpit) specified but not implemented, cockpit-type/AES
  not parsed.
- PATHFINDER: impassable-hex detection (`.board` always reports `False`,
  no confirmed rule); bridge cost/elevation rules (`ValueError` on any
  bridge feature, unconfirmed); elevation cap on single-step movement
  (unenforced); LOS rule-6 tie-break is a placeholder pending a real
  evaluation function; closing-turn reweighting formula undesigned;
  persistent cross-call LOS/damage-EV cache (currently rebuilt per
  candidate); JSON export of search-state (deferred).

**Known Issues (unresolved):**
1. `equipment.json`'s `category` field only has `weapon`/`ammo`/`misc` —
   heat sinks are `misc`; finding them needs a name match, not a category
   filter.
2. Pathfinder's LOS tie-break is an explicit placeholder until a real
   move/attack evaluation function exists.
3. ~~MECHSIM's PSR system has only ever been smoke-tested against the
   hardcoded fixture mech~~ — 2026-10-18: now exercised against real parsed
   .mtf units (Attack Phase 20+ damage, leg actuator, hip-triggered movement
   PSR, falls, failed stand-up, consciousness) in live battles.
4. MegaMek export quirk: a location's armor-type crit slots can appear
   in a *different* location's crit list — always read armor type from
   the location's own header line, never infer from crit contents.

---

## 4a. TORSO TWISTING (and firing arcs)

*Everything about torso twists and arc changes in one place. Code:
`INTEGRATION__arcs.py` (its docstring is the rule summary with page cites);
rules text: `rules/Battletech_Rule_Reference_Index.zip`, combat-part1 entries
CR-CMB1-FIRING-ARCS, ARCS-TORSO-TWIST, TORSO-TWIST, REVERSING ARMS; appendices-a-c
(tripods, quads). Tests: `tests/test_arcs.py` (10 checks) plus the arc checks in
`tests/test_movement_selection.py`.*

**Firing arcs (p.60, Daniel's diagram):**
- The angle of the centre-to-centre line from the attacker's facing.
  Forward within 60 deg (120 wide), left/right side 60-120 deg (60 wide each),
  rear beyond 120 deg (120 wide). A hex on a boundary goes to the forward arc
  (vs a side arc) or the side arc (vs the rear arc). All 15 labelled hexes on
  the diagram are reproduced by `tests/test_movement_selection.py`.
- Weapons by arc: forward = everything but rear-mounted; left/right side =
  that side's arm weapons (a weapon split torso/arm is forward-only); rear =
  rear-mounted only. Prone doesn't change arcs.
- Leg weapons use the legs' forward arc (the facing). Tripods (p.236): the
  left / right leg arcs start two hexsides left / right of the front, the
  centre leg's at the front.

**Arc actions - what a mech declares at the start of attack declaration,
Ranged or Physical phase (p.61):** `arcs.ArcAction(twist, flip, turret)`.
- **Torso twist (p.62):** one hexside left or right; a **tripod any hexside**
  (p.236). Shifts head, torso and arm weapons, punches, clubs and physical
  weapons; never leg weapons, kicks, the facing, or how the mech is hit (p.73).
  Prone mechs and quads can't twist.
- **Reversing (flipping) arms (p.62):** only a design with neither hand nor
  lower arm actuators in BOTH arms and no torso/arm split weapon (all or
  nothing, FAQ p.243; losing actuators to damage doesn't qualify; losing an arm
  doesn't disqualify the other). Arm weapons then fire only into the rear arc;
  no punches or arm physical weapons. Not while prone.
- **Quad Turret (pp.61, 205):** weapons marked "(T)" on the crit line (now kept
  by `mtf_parser` as `Equipment.turret_mounted`) fire into the turret's forward
  arc, turned any number of hexsides at each declaration; this is separate from
  the once-a-turn twist/flip. A crit on the turret slot locks it at the
  direction it last had (`turret_last_offset`).
- **Once a turn:** a twist OR a flip, not both; once declared it stands for the
  rest of the turn (`arc_action_locked`). A mech that declared neither in the
  Ranged phase may twist in the Physical phase (p.76). End Phase: torso
  forward, arms back (`arcs.end_turn`, called from `orchestrator._phase_end`).

**Physical Attack Phase (`INTEGRATION__physical.py`, pp.76-83, 237):** arcs come
from `arcs.arcs_between` (the old nearest-hexside code is gone). Punches and arm
physical weapons use the twisted torso's forward / that arm's side arc; kicks the
legs' forward arc. Tripods attack physically only into the twisted torso's
forward arc, kicks included, never into a side arc.

**Who picks (bot choices, pile 4):**
- Ranged: `attack_resolution.declare_attacks` tries every legal action and keeps
  the one with the most expected damage; no change wins ties; if nothing fires,
  nothing is declared (so the Physical phase may still twist). Next to the
  target (2026-10-19) it scores each action together with each physical plan
  that can follow: ranged fire without the weapons in the punching / kicking
  limbs + the plan's expected damage, since the twist stands for both phases
  and a limb that attacks physically can't have fired (pp.62, 76, 82). The log
  says when weapons are held back for a punch.
- Physical: `physical.choose_attack` re-picks with what actually happened (fired
  weapons, falls): every twist still allowed x attack type, most expected damage.
- Movement scoring (`ranged_combat.MoveEvaluator`) takes each side's best
  action per spot, physical plans included for spots next to the enemy (both
  ways). That is the real rule: twists are declared at attack declaration,
  after movement (p.61). `physical.Planner` caches the options per reach case
  (cost: about 2.5 s a turn on the default battle, was ~1.9).

**Not modeled / not reachable:**
- TAG designation (p.53) uses up the turn's twist/flip, but TAG never fires
  yet (`stubs.unconfirmed_weapon_data`); `arcs.declare` is the hook if it does.
- Shoulder / head turrets are Tactical Operations equipment, not Core: their
  "(T)" weapons are treated as fixed forward.
- Primary target in the forward arc (p.64) and hidden-unit point-blank shots
  (p.230) need more than one enemy / hidden units - the sim has neither.
- Push (p.83) ignores twists - pushes aren't built.

**Claude's calls (not settled by the rules - Daniel may overrule):**
- A rear-mounted weapon in a flipped arm still fires only to the rear.
- The Physical phase never chooses to flip (it only takes punches away).
- Turrets: the locked direction is the last one declared before the crit.

**Gotchas:**
- The rear arc is now 120 deg. Daniel's 2026-07-20 one-hexside (60 deg) rule
  is superseded by the p.60 diagram (identical at range 1); PATHFINDER's
  `combat.in_rear_arc` (not wired) still has the old rule. Listed for Daniel
  under Section 4 "Core Rulebook vs existing MECHSIM rules".
- Attack DIRECTION (front/left/right/rear hit tables, p.73) is a different
  thing from firing arcs and is unaffected by twists.
- History: Change Record, 2026-10-19 entries "Firing arcs and torso twists"
  and "Arc actions".

---

## 5. DECISIONS LOG (Daniel's calls — implementation may not override)

- **Gunnery/piloting skill:** config-level input, not derived from `.mtf`.
- **HP scalar for scoring:** total remaining armor + structure. Adjustable later.
- **Weapon data model:** `equipment.json` is the single source once a
  mech's crit layout exists; no separate Pathfinder weapon dict.
  `Equipment` carries weapon/heat-sink stats extracted once at parse time
  (compute-once — see Section 7 performance rule), not re-queried per read.
- **Outer batch-loop / turn-flow controller:** new orchestrator files, not
  either existing driver. Old files stay as reference only, removed once
  new files are assembled.
- **Pile 1 reconciliation (2026-08-30):** `PATHFINDER__combat_turn.py` and
  `MECHSIM__sim_runner.py` are cannibalized into the integration then
  deleted from this project. Both remain intact in their own source projects.
- **Pile-4 extraction:** no dedicated bot module — logic lives in whichever
  file makes that decision; Section 6 is the tracking index.
- **RNG:** single `INTEGRATION__rng.BattleRNG` (NumPy `Generator`-backed,
  optional seed), owned by whatever drives a battle. Wired 2026-08-30;
  every dice roll in the battle loop now draws from it (except the tripod
  leg sub-roll, see Section 4). Same seed → byte-identical log (verified
  2026-10-18).
- **Heat-constrained weapon selection:** expected damage = P(hit) ×
  E[damage|hit]. `min_heat` = active goal, `max_heat` = hard ceiling.
  Two-phase selector. Built and tested; wired into Ranged Combat 2026-10-18.
- **Heat budget (2026-10-18):** "Max heat is dissipation + the set value" —
  weapon heat budget = max_heat + dissipation − current heat − movement
  heat, i.e. max_heat caps the end-of-turn heat level. Heat is saved state,
  carried turn to turn. Movement heat: Walk 1, Run 2, Jump
  max(3, Improved JJ ? ceil(hexes jumped/2) : hexes jumped).
- **Cooldown (2026-10-18):** when to hold fire and cool back to zero is bot
  logic — later. Currently a mech at max_heat stays there.
- **TMM source (2026-10-18):** actual hexes moved this turn
  (`combat.fc_to_tmm`, +1 if jumped). MECHSIM `compute_tmm()` not used.
- **Minimum range (2026-10-19):** +1 to-hit per hex inside minimum range,
  i.e. (min - range) + 1; a weapon with no listed minimum has minimum 0.
- **One-shot launchers (2026-10-19):** same range and damage stats as their
  primary launcher; they may only fire once (not enforced yet).
- **Engine-hit heat (2026-10-19, confirmed):** a hit taken this turn adds
  its heat in that turn's Heat Phase; after that the 5 (or 10) comes out of
  the weapon heat budget every turn.
- **Heat equipment defaults (2026-10-19):** player choices are "default on"
  for now - stealth systems always active, coolant pods used (Claude's
  reading of "on": when heat would stay above min_heat). Radical heat sinks,
  MASC and superchargers run a 1-turn-on / 1-turn-off cycle
  (`config.ESCALATING_CYCLE_ON_ODD_TURNS`). TSM is controlled by min_heat =
  9 (`config.TSM_MIN_HEAT`; Claude also raises max_heat to at least
  min_heat). Heat sinks are switched off in the End Phase from the mech's
  most possible heat (weapons + movement + damage) so min_heat can be
  reached.
- **min_heat (2026-10-19):** the floor on end-of-Heat-Phase heat (the mech
  "wants to sit at a minimum of" it), mirror of max_heat. Was: minimum
  weapon heat generated per turn.
- **Stub conventions (2026-10-18):** every placeholder is its own function in
  `INTEGRATION__stubs.py`, warns loudly every run, is counted into the
  results, keeps its knobs in config. (The movement stub is gone since
  2026-10-19.) Hit table default `mechsim_random`.
- **Movement selection (Daniel, 2026-10-19):** objective = damage dealt /
  (damage received + .001). Two-ply so both sides move intelligently. The old
  `combat_turn` closing fallback ported as-is ("working system first, improve
  later"). Armor-exposure weighting by the real hit direction (thin armor on
  a side makes shots on it count more, both ways). Partial cover is already in
  to-hit. Cooldown relies on max_heat. Expected damage from falling is added to
  the denominator, ONLY for Movement-Phase PSRs (not PSRs caused by damage);
  mines / lava / terrain PSRs are a future addition. Dropping `compute_score()`'s
  HP-awareness is fine for now. Internal-structure damage counts k = 2x
  armor damage, per weapon x hit-location table, no chaining
  (`MOVEMENT_STRUCTURE_WEIGHT`). A Void-Signature mech's low-movement spots
  get its TN bonus (it keeps every movement variant). Claude's choices inside
  that: the opponent's modeled reply uses the same rule (greedy, not
  searched); the PSR cost is P(fail) x ceil(mass/10) for Run (1+ hex) / Jump
  when a trigger exists; exposure factors clamp to [0.5, 3.0].
- **Movement attacks are anticipated (Daniel, 2026-10-20):** "First mover
  needs to anticipate being charged, or any other incorporated attacks."
  The two-ply modeled reply runs the same charge / DFA decision the real
  second mover does (gate, score, beat its best ordinary reply) against each
  first-mover spot; ranged fire and every physical attack (pushes included)
  were already in the reply's numbers.
- **Pushes (Daniel, 2026-10-20):** "It does no damage on its own, but can be
  used to push a mech off a cliff causing falling damage, or push a mech off
  the map, which should probably be evaluated as taking 100% damage. Its a
  case of the threat of it affects choices, and it will almost never be
  used." Implemented: value = P(hit) x (the target's remaining armor +
  structure off the board; the fall's worth 2+ levels down; else 0), a
  physical plan using both arms. The same displacement worth is added to
  charges and DFAs that hit.
- **Clubs (Claude's call, 2026-10-20):** picked up only on a turn the mech
  fires nothing anyway (it costs the whole Ranged phase); limb / girder before
  tree. Not planned for in movement (a mech doesn't walk into woods to fetch
  one).
- **Death from above (Claude's calls, 2026-10-20):** the jump must clear the
  target's LOS level (hex + 2 standing / 1 prone) within the jump MP; a
  DFA'er that fell in the Ranged phase lands without a second fall (the rule
  says resolve a failed DFA instead of the fall); on a miss the target steps
  to the open hex with the smallest drop.
- **Charges (Daniel, 2026-10-20):** "gate that decision tree to ask if a
  charge at this movement mode does more damage than normal attacks and
  physicals before thinking about it." Implemented: per movement mode, a charge
  is only scored if its expected worth beats the best ordinary (ranged +
  physical) dealt any spot in that mode offers; survivors are scored by the
  usual objective with the charger's return fire, the target's physical attacks
  and its own expected self-damage as received, and taken only if they beat
  the normal pick. Claude's calls: the attacker's self-damage lands on its
  front; the bot always aborts a TN 13+ charge; the charge PSRs (+2 both) and
  displacement aren't in the score. Note: the ratio objective punishes a
  charge's guaranteed self-damage, so a charge wins mostly when every ordinary
  spot takes return fire too (weak-gunned heavy chargers vs big targets).
- **Physical attacks weighted by hit table (Daniel, 2026-10-20):** punches and
  kicks "use different hit tables so would have different scoring modifiers".
  `physical.Worth`: the table's own armor exposure and structure bonus, in
  movement scoring and the Physical-phase choice; the Ranged-phase fire-or-punch
  choice stays raw like its gun side. Not moved into the weapon list: profiling
  showed no speed gain (Daniel's condition was "if it would speed up").
- **Firing arcs and torso twists (Daniel's p.60 diagram, 2026-10-19):** see
  `INTEGRATION__arcs.py`'s docstring - 120-degree forward and rear arcs,
  60-degree sides, boundary hexes to the non-rear arc; this supersedes the
  2026-07-20 one-hexside rear arc. Each side takes its best twist. Details
  and to-do: Section 4a.

---

## 6. PILE 4 — DECISION-MAKING INDEX (cross-cutting, not a module)

| Decision point | Lives in | Decides |
|---|---|---|
| Movement selection | `INTEGRATION__movement_selection.choose` | Spot (hex + facing + mode) maximizing dealt×exposure / (received×exposure + movement-PSR cost + .001); first mover scores each spot by the second mover's modeled reply (two-ply). Knobs: config MOVEMENT SETTINGS. |
| Movement-PSR cost | `movement_selection.psr_costs` | P(fail) × fall damage, only for Run / Jump with a Movement-Phase PSR trigger; damage-caused PSRs ignored (Daniel) |
| Armor-exposure weighting | `movement_selection.exposure_factors` | Per-side vulnerability from current armor + structure (front = 1.0, clamped) |
| No-LOS / out-of-range movement fallback | `movement_selection.closing_fallback` | Ported as-is from `combat_turn._closing_fallback` (cases A/B1/B2); nearest-to-enemy otherwise |
| Heat-constrained weapon selection | `INTEGRATION__weapon_selection.py` | Which weapons fire this turn, built and wired |
| Heat ammo explosion bin (controller's choice) | `INTEGRATION__stubs.stub_heat_explosion_bin` | **STUB.** Which of several equally destructive, equally full bins explodes (random). |
| Ammo bin to draw from | `INTEGRATION__ammo.spend` | The bin with the fewest shots left (empties bins sooner) |
| Prop arm when firing prone | `INTEGRATION__attack_resolution.prone_fire` | The arm whose weapons matter least |
| Physical attack type | `INTEGRATION__physical.choose_attack` | Twist (if still allowed) + attack type (punch / kick / physical weapon / club / push) with the most expected worth, weighted by hit table (`physical.Worth`) |
| Ranged fire vs the physical attack that follows | `attack_resolution.declare_attacks` (`_physical_planner`) | Next to the target: best (arc action, physical plan) by ranged expected damage without the attacking limbs' weapons + the plan's expected damage (raw on both sides) |
| Torso twist / arm flip / turret | `declare_attacks`, `physical.choose_attack`, `ranged_combat.MoveEvaluator` | Most expected damage; no change wins ties (Section 4a) |
| Charge / death from above | `movement_selection._movement_attack_pick`, `_modeled_reply`; `INTEGRATION__movement_attacks` | Gate per movement mode (beat the best ordinary attack), then the objective must beat the ordinary pick; both movers (two-ply) |
| Push value | `physical.push_option`, `movement_attacks.displacement_worth` | P(hit) x (target HP off the board / fall worth 2+ levels down / else 0) |
| Club pick-up | `INTEGRATION__clubs.maybe_pick_up` | OFF (`config.CLUB_PICKUP`); waits for the Memo below |
| DFA miss: where the target steps | `INTEGRATION__dfa.resolve` | The open hex with the smallest drop |
| Home edge | `config.HOME_EDGE_CHOICE` | Which edge the deployment-roll loser picks (default random) |
| Escalating Failure use (radical heat sinks, MASC, supercharger) | `INTEGRATION__equipment_systems.cycle_on` | 1-turn-on / 1-turn-off cycle (Daniel's default) |
| Coolant pod trigger | `INTEGRATION__heat._extra_cooling` | One pod when heat would stay above min_heat, not on a radical turn |
| Heat-sink switching | `INTEGRATION__heat.choose_heat_sink_deactivation` | End Phase: how many sinks stay on so min_heat can be reached |
| Aimed shot location | `config.AIMED_SHOT_LOCATION` | Where shots at immobile targets aim (default Center Torso) |
| Candidate reduction | `movement_selection.reduced_options` | Max FC (min MP) per (hex, facing, mode, fc>0); Void-Signature exempt |
| Best-reply selection | `movement_selection._modeled_reply` | Wired (two-ply) |
| `compute_score()` | `PATHFINDER__combat.py` | Not wired (reference; built on flat HP/weapon dicts) |
| LOS rule-6 tie-break | `PATHFINDER__los.py` | Placeholder, see Known Issues #2 |
| Closing-turn detection | `movement_selection.closing_fallback` | Wired (ported) |

### Memo: the bot must weigh how an action changes its FUTURE capabilities (Daniel, 2026-10-20)

Every decision so far is greedy for the current turn. Several need the bot to
ask what an action does to what it can do on later turns:
- **Clubs.** Picking up a tree costs the Ranged phase and (Daniel, "IIRC")
  the arm and front-torso weapons while it's held; "the question is if the
  utility of having a club is greater than the weapons you're armed with. The
  answer is almost always no - I've never seen anyone use a tree as a club."
  Pick-up is OFF (`config.CLUB_PICKUP`) until this exists.
- **MASC / superchargers.** Each use raises the failure target number and a
  failure wrecks the legs / engine; using them is a trade between this turn's
  MP and next turns' risk. Today: Daniel's 1-on / 1-off default cycle.
- **Rotary autocannons** (and Ultras): more shots now vs jams that take the
  weapon away later (multi-shot math isn't built yet either).
- Likely the same shape: radical heat sinks, coolant pods, ammo spending
  ("they'll need their own logic suite on if it's worth using up limited
  ammo"), heat build-up vs a shutdown later, and possibly the hanging-back
  movement problem (Section 0, "Pick up here" item 2).
Not designed yet - Daniel: "when we get to figuring out how the bot should
think." A natural shape is a value for the mech's state at the end of the
turn (weapons usable, heat, jam / failure risk, a club in hand) added to the
turn's score, so a decision sees what it gives up.

---

## 7. STANDING PROMPTS

- (Daniel, 2026-10-19: "nuke those standing instructions - Claude Code did
  good work with little to go on." The old "don't run code until told
  'compile'" and "one test pass" gates are retired: build, test and run freely;
  ask only when a real rules/scope call is Daniel's.)
- Never hardcode a BT numeric rule from memory — check the rules library
  (below) and cite the page; if the library doesn't settle it, ask Daniel.
- The rules library is `rules/Battletech_Rule_Reference_Index.zip` (Core
  Rulebook base layer in `base/core-rules/*.md`). Unzip it outside the repo
  and check rules against it; cite the page in the code.
- Keep source-project file prefixes; never let one overwrite the other.
- Name which pile new code belongs to; if it doesn't fit, say so.
- New pile-4 decision points get a Section 6 row.
- Section 4/5 items aren't Claude's to resolve by inference — stop and ask.
- Daniel owns BT rules/scope; Claude owns implementation (structure,
  naming, data shape, algorithm choice) — don't reflect ordinary
  implementation calls back as questions.
- Monte Carlo batches multiply per-call cost — default to compute-once/
  cache over recompute-on-every-read; name which shape a choice takes.
- Daniel reads code, doesn't write it — clean, explicit, commented over
  dense/clever. Don't "fix" a Known Issue without checking it's actually
  a bug first. Sign work in the Change Record below.
- Placeholders go in `INTEGRATION__stubs.py` as loud, counted stubs with
  config knobs — never as silent defaults.
- (Daniel, 2026-10-20) **Claude runs the GitHub logistics**: develop on the
  session branch, commit with clear messages, push, open a PR to `main` and
  merge it once every test passes - Daniel doesn't use GitHub. Tell him in
  plain words what changed; don't make him handle branches or PRs.
- (Daniel, 2026-10-20) A decision with a cheap test that rules most cases
  out goes FIRST in the decision tree ("gate that decision tree ... before
  thinking about it") - e.g. charges / DFAs only get scored if they beat the
  best ordinary attack in that movement mode.
- Measure speed on the fixed benchmark (`tests/benchmark_turns.py`) before and
  after; a change only for speed must leave every result identical.
- Reference logs: regenerate (`--update`) only for changes meant to alter
  results, and say so in the Change Record.

---

## 8. CHANGE RECORD

*(Starts fresh 2026-08-28 — prior history archived/removed, not carried forward.)*

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
