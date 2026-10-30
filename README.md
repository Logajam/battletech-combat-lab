# BattleTech Monte Carlo Simulator

Headless batch simulator: two mechs (`.mtf` files) fight on a hex board,
turn by turn, many times over, and the results are summarized. Any number of
mechs on any number of teams can fight too (a lance against a lance, a company,
a free for all, a three-way battle): set `FORCES` in `INTEGRATION__config.py`.

## Run it

```
python INTEGRATION__main.py
```

Needs Python 3 and NumPy (`pip install -r requirements.txt`). All settings (which mechs,
board, seed, number of battles, stub knobs) are in `INTEGRATION__config.py`.
A batch runs one battle per CPU core at once (`WORKERS`; set it to 1 to run them
one after another) - the output is the same either way.

## Layout

| Path | What's there |
|---|---|
| `INTEGRATION__*.py` | The simulator: turn flow, combat, movement picking (`movement_selection`), firing arcs and torso twists (`arcs`), heat, results, stubs; Tactical Operations / Interstellar Operations gear and terrain (`advanced_weapons`, `advanced_equipment`, `hazards`, `smoke`); which bot drives each unit (`bots`: "gladiator", this project's, or "princess", a clone of MegaMek's Princess - modern in `princess_modern`, v0.50.07 in `princess`, fire control in `princess_fire`; its team behaviors in `princess_group` and `princess_memory`); Battle Value (`battle_value`, items from `mechsim/equipment_bv.json`); Legate (`legate`, `config.LEGATE`: the layer that lets a Gladiator plan against the whole enemy force) |
| `mechsim/` | Mech state, damage, crits, piloting rolls, `.mtf` parser, `equipment.json` (full equipment database) |
| `pathfinder/` | Hex geometry, board parser, movement, LOS, to-hit pieces |
| `data/` | `.board` maps (16x17 Grassland, 50x50 BigBlank) and `.mtf` mechs (test mechs, plus real units from `meks.zip` for the AMS / Artemis / Narc / ECM / weapon-use reference battles) |
| `data/maps.zip` | Daniel's MegaMek map pack (346 `.board` maps, 192 of them 16x17). `python tests/survey_maps.py` lists which ones the simulator can play and what stops the rest |
| `data/meks.zip` | 4,227 MegaMek `.mtf` units by source book (4,204 load - ultralights and superheavies since 2026-10-28; the 23 LAMs don't). Unzip outside the repo and point `INTEGRATION__config.py` at a file to try a unit |
| `tests/` | `run_checks.py` (everything below in one command), `check_reference_logs.py` (same-seed battles vs saved logs), `test_pathfinder.py` (hex geometry, movement, board parsing, terrain costs), `test_terrain.py` (map terrain: costs, roads, level limits, jump height, passive buildings, deployment depth / stuck terrain), `test_water.py` (water: depth, cover, the water line, underwater weapons, torpedoes, heat sinks, jump jets, PSRs, falls), `test_los.py` (line of sight per the Core Rulebook: heights, intervening terrain, woods, partial cover, prone, border lines), `survey_maps.py` (which maps in `data/maps.zip` play - not in run_checks), `test_weapon_range.py` (range modifiers), `test_heat.py` (Heat Scale), `test_equipment.py` (heat equipment), `test_rules.py` (stub replacements), `test_movement_selection.py` (movement picker), `test_arcs.py` (twists, arm flips, turrets), `test_special_attacks.py` (charges, DFA, pushes, clubs), `test_ams.py` (anti-missile systems), `test_electronics.py` (Artemis, Narc, ECM, ammo-bin names), `test_fire_modes.py` (rapid fire, ammunition kinds, Apollo, the weapon-use stubs, slot counts), `test_weapons.py` (variable-damage, HAG, M-pod, MG array, bombast, rifles, heat-causing, Arrow IV / artillery, Apollo saturation, pooled cluster damage, PPC capacitors, Thumper / Sniper, TAG and homing artillery), `test_multi_unit.py` (teams, Initiative and Unequal Numbers for any number of sides, foe / target choice, stacking, the domino effect, 3-way / lance / free-for-all battles), `test_parallel_batch.py` (parallel batches), `test_replay.py` (battle replays), `test_bots.py` (the bot switch and the Princess clone), `test_hazards.py` (TO:AR magma, hazardous pools, bogging down, hazards in path search and both bots), `test_advanced_gear.py` (TO:AUE HVAC, mortars, Taser, fluid guns / VGLs, turrets, modular armor, flail / chain whip, smoke and active probes, Gauss explosions), `test_intops.py` (Interstellar Operations TSEMP, iATM with IMP / IIW, inferno missiles, Improved weapons, nail / rivet gun), `test_superheavy.py` (ultralight and superheavy 'Mechs), `ab_batches.py` (the same seeds under several bot settings, side by side), `bot_agreement.py` (how often Princess's movement pick matches Gladiator's - not in run_checks), `legate_probe.py` + `legate_probe_report.py` (a diagnostic battery: Legate's estimate v truth, predicted v actual damage, the regret of each pick, cohesion, calibration - not in run_checks), `pick_quality.py` (every bot's movement pick priced on Perfect Knowledge's scale over 8 scenarios; `--pickers` runs only some, `--perfect-cache` reuses Perfect's prices - not in run_checks) |
| `rules/` | `Battletech_Rule_Reference_Index.zip`: the rules library (Core Rulebook in `base/core-rules/*.md`) that page cites in the code refer to. Unzip somewhere outside the repo to read it |
| `replays/` | Battle replay pages (made when `REPLAY_BATTLES` in `INTEGRATION__config.py` is above 0; open one in a browser). Not kept in git |
| `reference_logs/` | Same-seed sample logs (matchup and settings in the file name), for checking that a change didn't alter results |

After a change, from the repo root:
- `python tests/ab_batches.py 20 "Red.mtf" "Blue.mtf" --set knowledge --turns 50`: A/B batches - one matchup, the same seeds, under several bot settings (`--set` picks a `VARIANT_SETS` entry at its top: `objective`, `search`, `knowledge`, `grid-spin`, `baseline`; `--board`, `--seed` too). 20 battles a setting by default (Daniel)
- `python tests/run_checks.py`: **the clean-baseline check** - runs every test below and every reference battle side by side, one line each (`--bench` adds the benchmark)
- `python tests/check_reference_logs.py`: re-runs the reference battles and checks the results are unchanged
- `python tests/test_multi_unit.py`: checks multi-unit battles (Core Rulebook pp.39-41, 113-116): Initiative and the Unequal Numbers tables, who a unit fights, stacking, domino effects and accidental falls from above, and whole 3-way / lance / free-for-all battles - uses units from `data/meks.zip`
- `python tests/test_map_picker.py`: checks the map picker (listing the loose boards and the map pack, finding a map, which maps fit a stitched grid, the console menu with scripted answers, remembering the last pick)
- `python tests/test_princess_group.py`: checks Princess's team behaviors (the target choice with the damage friends already declared, the heat map and its hot spot, mutual support, crowding, the force's posture, a move against several enemies)
- `python tests/test_legate.py`: checks Legate (the hex-conflict cascade, the estimate, the foe choice, the other enemies' damage in a Gladiator's move score; off and in a duel nothing changes)
- `python tests/test_battle_value.py`: checks Battle Value (the four published values, skill, damage, the equipment data, every unit in the pack priced)
- `python tests/baseline_battery.py pp|pg|gg [battles] [--legate] [--fire-split ...] [--split-now] [--herding] [--cohesion SCALE] [--team-value ...] [--first N --last M] [--replay]`: the baseline battery - 12 v 12 mirrored forces on a 2 x 1 stitched field, Princess v Princess / Princess v Gladiator / Gladiator v Gladiator; prints winner, turns, units and HP left, seconds a battle (a yardstick: results recorded in PROJECT_MAP Section 8)
- `python tests/test_pathfinder.py`: checks the movement/map code
- `python tests/test_weapon_range.py`: checks range brackets and the minimum-range penalty
- `python tests/test_heat.py`: checks the Heat Scale rules (Core Rulebook pp.102-107) with scripted dice
- `python tests/test_equipment.py`: checks the heat/movement equipment (stealth, coolant pods, radical heat sinks, inferno, TSM, MASC, supercharger, aimed shots)
- `python tests/test_movement_selection.py`: checks the movement picker against brute-force scoring (reduction, two-ply reply, PSR cost, exposure, structure weighting, Void Signature, closing fallback, firing arcs and torso twists, physical attacks next to the enemy, determinism, the IF/THEN picker)
- `python tests/test_arcs.py`: checks torso twists (both attack phases, tripods), tripod leg arcs, reversing arms, Quad Turrets and the End Phase reset
- `python tests/test_special_attacks.py`: checks charges and death from above (damage, reach, the decision gate, the first mover anticipating them, displacement, PSRs, cancellation), pushes (when possible, off the board / down a cliff, the threat in movement scoring), clubs (holding, picking up, attacking, dropping) and multi-level falls - uses units from `data/meks.zip`
- `python tests/test_ams.py`: checks Anti-Missile Systems (Core Rulebook p.206: the engaged Cluster roll, Streaks, single missiles, arcs, the 2-a-turn limit, ammo, heat, crew / shutdown, expected damage in weapon choice and movement) - uses units from `data/meks.zip`
- `python tests/test_electronics.py`: checks Artemis IV / V, Narc / iNarc pods, ECM (Angel vs Streaks, stealth armor), munition choice and the ammo-bin names (Core Rulebook pp.186-188, 192-193, 197, 200) - uses units from `data/meks.zip`
- `python tests/test_fire_modes.py`: checks rapid fire (Ultra / Rotary AC, jams, unjamming), LB-X cluster rounds, ATM / MML ammunition, the Apollo FCS, the weapon-use and MASC stubs, and the slot-count / machine-gun data fixes - uses units from `data/meks.zip`
- `python tests/test_weapons.py`: checks the weapons that couldn't fire before (variable damage, HAG, M-pods, machine gun arrays, bombast lasers, rifles, flamer / plasma heat, Arrow IV, artillery cannons), Apollo saturation, pooled cluster damage and PPC capacitors - uses units from `data/meks.zip`
- `python tests/test_hazards.py`, `test_advanced_gear.py`, `test_intops.py`, `test_superheavy.py`: check the Tactical Operations terrain and gear, the Interstellar Operations weapons, and ultralight / superheavy 'Mechs (2026-10-27/28) - use units from `data/meks.zip`
- `python tests/test_parallel_batch.py`: checks that a batch prints the same output whether its battles run one at a time or in parallel, and each battle's own seed
- `python tests/benchmark_turns.py`: times the first 10 turns of the default battle (seed 12345) - for speed changes
- `python tests/test_rules.py`: checks the rules that replaced stubs (attack direction, cluster groupings, to-hit modifiers, ammo, deployment, physical attacks)

Anything not yet a real rule is a loud **stub**: it prints `STUB: ...` to
stderr and appears in the summary banner.

New to the project (or a new Claude session)? Start with `CLAUDE.md`, then Section 0 of `INTEGRATION__PROJECT_MAP.md`.

Project status, open items and decisions: `INTEGRATION__PROJECT_MAP.md` (torso twists and firing arcs: its Section 4a).
Core Rulebook vs code (fixed, gaps, questions for Daniel): `INTEGRATION__RULES_REVIEW.md`.
Import structure: `INTEGRATION__CALL_GRAPH.md`.
