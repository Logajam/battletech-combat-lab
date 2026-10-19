# Call Graph

Structural doc, separate from `INTEGRATION__PROJECT_MAP.md`. Tracks what
imports what, at module granularity. Update when wiring changes (new
import/call added, a file gets absorbed/retired). Not updated for
read-only investigation, and not a place for narrative or dated entries
— that stays in the Change Record.

Regenerated 2026-10-18 by grepping every `import`/`from ... import` line
in the INTEGRATION files after the first end-to-end wiring pass. MECHSIM/
PATHFINDER edges unchanged from the 2026-08-28 grep (those files weren't
edited).

---

## 1. EDGES

**Pile 1 / integration (`INTEGRATION__*`)**
- `main.py` → `orchestrator`
- `orchestrator.py` → `config` (imported first; self-registers as bare
  `config`), MECHSIM `mech_state` (is_destroyed, is_crippled, clone_mech,
  compute_*_mp, compute_heat_dissipation, all_crew_unconscious),
  `piloting_rolls`; PATHFINDER `board_parser`, `hex_geometry`,
  `pathfinder.build_movement_table`, `combat` (build_jump_states,
  classify_movement_mode); INTEGRATION `rng`, `weapon_selection`, `heat`,
  `ranged_combat`, `stubs`, `attack_resolution`, `results`
- `attack_resolution.py` (NEW) → `config`, `stubs`, `weapon_selection`;
  MECHSIM `mech_state`, `armor_rules`, `hit_location`, `damage_resolution`
  (apply_damage, check_critical, cluster_hits_count, get_weapons),
  `piloting_rolls`; PATHFINDER `hex_geometry`, `combat` (fc_to_tmm,
  MODE_TO_AMM, in_rear_arc), `los` (has_los, hex_distance)
- `stubs.py` (NEW) → `config`; MECHSIM `mech_state`, `hit_location`
  (FACING_CHOICES); PATHFINDER `hex_geometry`, `los` (local imports inside
  stub_select_movement)
- `results.py` (NEW) → stdlib only. Leaf.
- `ranged_combat.py` → `config` (registration only), MECHSIM `mech_state`
  (compute_*_mp, compute_heat_dissipation); PATHFINDER `hex_geometry`,
  `pathfinder`, `los`, `combat`; `weapon_selection` (select_weapons_to_fire),
  `heat`. (No longer imports `damage_resolution` directly.)
- `heat.py` (NEW 2026-10-18) → MECHSIM `mech_state.compute_heat_dissipation`
- `weapon_selection.py` → `config` (registration only), `expected_damage`,
  MECHSIM `damage_resolution.get_weapons`, PATHFINDER `combat.hit_probability`.
  **Purge/reload dance removed 2026-10-18** — plain imports now.
- `expected_damage.py` → bare `config` (= INTEGRATION__config via its
  self-registration)
- `config.py` → `file_picker` (INTEGRATION__file_picker), MECHSIM `mtf_parser`
- `rng.py` → `numpy` only
- `file_picker.py` → stdlib/`tkinter` only. Leaf. Only used when
  `MECH_*_MTF` is None.

**Pile 2 / mech state (`MECHSIM__*`)** — unchanged
- `armor_rules.py` → `mech_state`
- `damage_resolution.py` → `config`, `armor_rules`, `equipment`, `mech_state`
- `equipment.py` → stdlib only. Leaf (data loader; reads `equipment.json` next to itself).
- `hit_location.py` → `config` (also uses stdlib `random` directly for the tripod sub-roll)
- `mech_state.py` → `equipment`
- `mtf_parser.py` → `config`, `equipment`, `mech_state`, `damage_resolution`
- `piloting_rolls.py` → `config` (reads `config.PILOTING`), `hit_location`, `mech_state`, `damage_resolution`
- `sim_runner.py` → (reference only, NOT imported) `config`, `armor_rules`,
  `run_statistics` (absent), `piloting_rolls`, `equipment`, `hit_location`,
  `damage_resolution`, `mech_state`, `mtf_parser`

**Pile 3 / map (`PATHFINDER__*`)** — unchanged
- `board_parser.py` → stdlib only. Leaf.
- `combat.py` → `hex_geometry`, `pathfinder`, `los`
- `combat_turn.py` → (reference only, NOT imported) `hex_geometry`, `pathfinder`, `los`, `combat`
- `hex_geometry.py` → stdlib only. Leaf.
- `los.py` → `hex_geometry`
- `pathfinder.py` → `hex_geometry`, `terrain_rules`
- `report.py` → (not imported) `hex_geometry`, `pathfinder`, `combat`, `combat_turn`, `los`
- `terrain_colors.py` → stdlib only. Leaf, not imported.
- `terrain_rules.py` → stdlib only. Leaf.
- `validation.py` → (not imported) `hex_geometry`, `pathfinder`, `simulate` (absent), `board_parser`, `terrain_rules`

---

## 2. REACHABLE FROM THE ENTRY POINT (`INTEGRATION__main.py`)

```
main.py
└─ orchestrator.py
   ├─ config.py ── file_picker.py, mtf_parser ── equipment, mech_state, damage_resolution ── armor_rules
   ├─ mech_state, piloting_rolls ── hit_location, damage_resolution
   ├─ board_parser, hex_geometry, pathfinder ── terrain_rules, combat ── los
   ├─ rng.py
   ├─ weapon_selection.py ── expected_damage.py
   ├─ heat.py
   ├─ ranged_combat.py ── heat.py
   ├─ stubs.py
   ├─ attack_resolution.py
   └─ results.py
```

**Reachable:** every INTEGRATION file; MECHSIM
`config`(=INTEGRATION), `equipment`, `mech_state`, `damage_resolution`,
`armor_rules`, `hit_location`, `piloting_rolls`, `mtf_parser`; PATHFINDER
`board_parser`, `hex_geometry`, `terrain_rules`, `pathfinder`, `los`, `combat`.

**Not reachable (reference only):** `PATHFINDER__combat_turn.py` (two-ply
look-ahead / closing fallback, to be kept as reference). Retired
2026-10-19 and not in the repo: `MECHSIM__sim_runner.py`, `report.py`,
`validation.py`, `terrain_colors.py`.

---

## 3. KNOWN GAPS IN THIS GRAPH

- **MECHSIM's and PATHFINDER's own `config.py` are retired.** Every bare
  `import config` resolves to `INTEGRATION__config` via its
  self-registration — so `INTEGRATION__config` must be imported before
  any MECHSIM module. The orchestrator and `weapon_selection` both do this.
- **Two dangling imports** (only matter if run standalone, not reachable
  from main): `sim_runner.py` → `run_statistics`; `validation.py` →
  `simulate`. Neither file is in the Project.
- **Viz files** (`heatmap.py`, `combat_viz.py`, `los_viz.py`,
  `turn_viz.py`) and `compare_runs.py`/`build_equipment_db.py` absent;
  nothing imports them.

---

## 4. MAINTENANCE RULE

Update this doc when an actual import/call edge changes — new wiring,
a file absorbed or retired. Don't update it for files being temporarily
out of view; that's a session-level choice, not a structural fact.
