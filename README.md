# BattleTech Monte Carlo Simulator

Headless batch simulator: two mechs (`.mtf` files) fight on a hex board,
turn by turn, many times over, and the results are summarized.

## Run it

```
python INTEGRATION__main.py
```

Needs Python 3 and NumPy (`pip install -r requirements.txt`). All settings (which mechs,
board, seed, number of battles, stub knobs) are in `INTEGRATION__config.py`.

## Layout

| Path | What's there |
|---|---|
| `INTEGRATION__*.py` | The simulator: turn flow, combat, movement picking (`movement_selection`), firing arcs and torso twists (`arcs`), heat, results, stubs |
| `mechsim/` | Mech state, damage, crits, piloting rolls, `.mtf` parser, `equipment.json` (full equipment database) |
| `pathfinder/` | Hex geometry, board parser, movement, LOS, to-hit pieces |
| `data/` | `.board` maps (16x17 Grassland, 50x50 BigBlank) and `.mtf` mechs |
| `tests/` | `check_reference_logs.py` (same-seed battles vs saved logs), `test_pathfinder.py` (hex geometry, movement, board parsing, terrain costs), `test_weapon_range.py` (range modifiers), `test_heat.py` (Heat Scale), `test_equipment.py` (heat equipment), `test_rules.py` (stub replacements), `test_movement_selection.py` (movement picker) |
| `rules/` | `Battletech_Rule_Reference_Index.zip`: the rules library (Core Rulebook in `base/core-rules/*.md`) that page cites in the code refer to. Unzip somewhere outside the repo to read it |
| `reference_logs/` | Same-seed sample logs (matchup and settings in the file name), for checking that a change didn't alter results |

After a change, from the repo root:
- `python tests/check_reference_logs.py`: re-runs the reference battles and checks the results are unchanged
- `python tests/test_pathfinder.py`: checks the movement/map code
- `python tests/test_weapon_range.py`: checks range brackets and the minimum-range penalty
- `python tests/test_heat.py`: checks the Heat Scale rules (Core Rulebook pp.102-107) with scripted dice
- `python tests/test_equipment.py`: checks the heat/movement equipment (stealth, coolant pods, radical heat sinks, inferno, TSM, MASC, supercharger, aimed shots)
- `python tests/test_movement_selection.py`: checks the movement picker against brute-force scoring (reduction, two-ply reply, PSR cost, exposure, structure weighting, Void Signature, closing fallback, firing arcs and torso twists, determinism)
- `python tests/test_rules.py`: checks the rules that replaced stubs (attack direction, cluster groupings, to-hit modifiers, ammo, deployment, physical attacks)

Anything not yet a real rule is a loud **stub**: it prints `STUB: ...` to
stderr and appears in the summary banner.

Project status, open items and decisions: `INTEGRATION__PROJECT_MAP.md`.
Import structure: `INTEGRATION__CALL_GRAPH.md`.
