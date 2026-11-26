// Translated from pathfinder/terrain_rules.py (session 22).
//! What it costs to step into a hex, whether the step is allowed, and which terrain a loaded map may contain.
//! The only place BattleTech terrain-cost numbers live (Core Movement Costs Table, p.48; see the Python's docstring
//! for the rule cites). `terrain_cost` / `_woods_cost` / `_water_depth` return Python's ValueError text as Err; after
//! `prepare_board` has accepted a board none of them can fail, so `step_cost` and friends expect() it.

use std::collections::BTreeMap;

use crate::board_parser::{Board, Features, Hex};
use crate::pyfmt::{py_int, py_repr_str};

pub const BASE_ENTRY_COST: i64 = 1;
pub const ROUGH_COST: i64 = 1;
pub const RUBBLE_COST: i64 = 1;
pub const SWAMP_COST: i64 = 1;
pub const SAND_COST: i64 = 0;
pub const MUD_COST: i64 = 0;
pub const WOODS_LIGHT_COST: i64 = 1;
pub const WOODS_HEAVY_COST: i64 = 2;
pub const WATER_DEPTH_0_COST: i64 = 0;
pub const WATER_DEPTH_1_COST: i64 = 1;
pub const WATER_DEPTH_2_PLUS_COST: i64 = 2;
pub const ELEVATION_COST_PER_LEVEL: i64 = 1;
pub const MAX_LEVEL_CHANGE: i64 = 2;
pub const MAX_LEVEL_CHANGE_HIP_DESTROYED: i64 = 1;
pub const ROAD_LEVEL_CHANGE_DISCOUNT: i64 = 1;
pub const PAVED_FEATURES: [&str; 2] = ["road", "pavement"];
pub const WOODS_FEATURES: [&str; 2] = ["woods", "jungle"];
pub const ULTRA_HEAVY_DENSITY: &str = "3";
pub const MAGMA_CRUST: &str = "1";
pub const MAGMA_LIQUID: &str = "2";

/// (name, why) of terrain the simulator cannot play yet, in the Python dict's order.
pub const UNSUPPORTED_FEATURES: [(&str, &str); 3] = [
    ("bridge", "bridges (Core pp.53, 131) - need the full building rules (deferred)"),
    ("fuel_tank", "fuel tanks (TO:AR pp.132-134) - buildings: need the full building rules (deferred)"),
    ("elevator", "industrial elevators (TO:AR pp.135-136) - buildings: need the full building rules (deferred)"),
];

pub const SUPERHEAVY_DISCOUNT: i64 = 1;
pub const SUPERHEAVY_DISCOUNTED: [&str; 4] = ["rough", "rubble", "woods", "jungle"];

fn unsupported_reason(feature: &str) -> Option<&'static str> {
    UNSUPPORTED_FEATURES.iter().find(|(f, _)| *f == feature).map(|(_, why)| *why)
}

fn magma_cost(state: &str) -> Option<i64> {
    match state {
        MAGMA_CRUST => Some(0),
        MAGMA_LIQUID => Some(1),
        _ => None,
    }
}

fn woods_cost(feature: &str, params: &[String]) -> Result<i64, String> {
    if params.is_empty() {
        return Err(format!("'{}' feature present with no density param (expected 1 or 2).", feature));
    }
    match params[0].as_str() {
        "1" => Ok(WOODS_LIGHT_COST),
        "2" => Ok(WOODS_HEAVY_COST),
        d => Err(format!("Unsupported {} density {} (Core has 1 light, 2 heavy).", feature, py_repr_str(d))),
    }
}

fn water_depth(params: &[String]) -> Result<i64, String> {
    if params.is_empty() {
        return Err("'water' feature present with no depth param.".to_string());
    }
    let depth = match py_int(&params[0]) {
        Ok(d) => d,
        Err(_) => return Err(format!("Non-integer water depth param {}.", py_repr_str(&params[0]))),
    };
    if depth < 0 {
        return Err(format!("Invalid water depth {} (expected >= 0).", depth));
    }
    Ok(depth)
}

/// The hex's terrain MP addition (p.48), every terrain in it added up (p.47). Superheavy (p.240): rough, rubble,
/// woods and jungle each cost 1 less.
pub fn terrain_cost(features: &Features, superheavy: bool) -> Result<i64, String> {
    if superheavy {
        let base = terrain_cost(features, false)?;
        let mut cut = 0;
        for f in SUPERHEAVY_DISCOUNTED {
            if let Some(params) = features.get(f) {
                let mut alone = Features::default();
                alone.0.insert(f.to_string(), params.clone());
                let a = terrain_cost(&alone, false)?;
                cut += SUPERHEAVY_DISCOUNT.min(a);
            }
        }
        return Ok(base - cut);
    }
    let mut cost = 0;
    if features.has("rough") {
        cost += ROUGH_COST;
    }
    if features.has("rubble") {
        cost += RUBBLE_COST;
    }
    if features.has("swamp") {
        cost += SWAMP_COST;
    }
    if features.has("sand") {
        cost += SAND_COST;
    }
    if features.has("mud") {
        cost += MUD_COST;
    }
    for feature in WOODS_FEATURES {
        if let Some(params) = features.get(feature) {
            if params.first().map(|s| s.as_str()) != Some(ULTRA_HEAVY_DENSITY) {
                cost += woods_cost(feature, params)?; // ultra-heavy: impassable (prepare_board)
            }
        }
    }
    if features.has("magma") {
        // MAGMA_COST[magma_state(features)]: a KeyError in Python for anything but "1" / "2"
        let state = magma_state(features);
        cost += state.and_then(magma_cost).unwrap_or_else(|| panic!("KeyError: magma state {:?}", state));
    }
    if let Some(params) = features.get("water") {
        let depth = water_depth(params)?;
        cost += if depth == 0 {
            WATER_DEPTH_0_COST
        } else if depth == 1 {
            WATER_DEPTH_1_COST
        } else {
            WATER_DEPTH_2_PLUS_COST
        };
    }
    Ok(cost)
}

/// MAGMA_CRUST / MAGMA_LIQUID text for a hex's features, None if no magma (or no param).
pub fn magma_state(features: &Features) -> Option<&str> {
    if !features.has("magma") {
        return None;
    }
    features.first_param("magma")
}

/// Road, pavement, or a roof (p.134).
pub fn is_paved(info: &Hex) -> bool {
    info.building || PAVED_FEATURES.iter().any(|f| info.features.has(f))
}

/// A mover's level limit that also says whether the mover is a superheavy (Python's GroundLimit(int)).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct GroundLimit {
    pub value: i64,
    pub superheavy: bool,
    /// May shift sideways without turning (Core p.236 tripods, p.238 quads, no leg destroyed): a step into one of the four hexes that are
    /// neither directly ahead nor directly behind, +1 MP, the facing kept. The two rear ones count as backward movement (walking only).
    pub lateral: bool,
    /// May change facing any number of hexsides for 1 MP (Core p.237, tripods with no leg destroyed).
    pub free_facing: bool,
}

/// Most levels ground movement may climb or drop per hex (pp.46-47).
pub fn max_level_change(hip_destroyed: bool, superheavy: bool) -> GroundLimit {
    GroundLimit { value: if hip_destroyed { MAX_LEVEL_CHANGE_HIP_DESTROYED } else { MAX_LEVEL_CHANGE }, superheavy, lateral: false, free_facing: false }
}

/// MP for a ground step from `from_info`'s hex into `to_info`'s, or None if not allowed. from None = entering the
/// board from off it (deployment, p.37).
pub fn step_cost(from_info: Option<&Hex>, to_info: &Hex, level_limit: GroundLimit, backward: bool) -> Option<i64> {
    if to_info.impassable {
        return None;
    }
    let to_roof = to_info.building;
    let from_roof = from_info.map_or(false, |f| f.building);
    let to_level = to_info.level;
    let from_level = from_info.map_or(to_level, |f| f.level);
    let change = to_level - from_level;

    if to_roof && from_info.is_some() && !from_roof {
        return None;
    }
    if from_roof && !to_roof {
        return None;
    }
    if from_roof && to_roof && change != 0 && change != -1 {
        return None;
    }
    if change.abs() > level_limit.value {
        return None;
    }
    if backward && change != 0 && (change.abs() != 1 || level_limit.value < MAX_LEVEL_CHANGE || from_roof) {
        return None;
    }
    let on_road = from_info.map_or(false, |f| is_paved(f) && is_paved(to_info));
    let cost = if on_road {
        BASE_ENTRY_COST + (change.abs() - ROAD_LEVEL_CHANGE_DISCOUNT).max(0) * ELEVATION_COST_PER_LEVEL
    } else {
        BASE_ENTRY_COST
            + terrain_cost(&to_info.features, level_limit.superheavy).expect("a prepared board")
            + change.abs() * ELEVATION_COST_PER_LEVEL
    };
    assert!(cost >= 1, "step_cost produced {} < 1 - violates the DP's load-bearing invariant.", cost);
    Some(cost)
}

pub const PSR_TERRAIN_FEATURES: [&str; 4] = ["rubble", "sand", "mud", "water"];

/// (always, run_only) PSRs a ground step into to_info forces.
pub fn step_psrs(from_info: Option<&Hex>, to_info: &Hex, backward: bool) -> (i64, i64) {
    let mut always = 0;
    let mut run_only = 0;
    let features = &to_info.features;
    if features.has("rubble") {
        always += 1;
    }
    let changes_level = from_info.map_or(false, |f| f.level != to_info.level);
    if features.has("sand") && changes_level {
        always += 1;
    }
    if to_info.depth.unwrap_or(0) >= 1 {
        run_only += 1;
    }
    if backward && changes_level {
        always += 1;
    }
    (always, run_only)
}

/// (always, run_only) PSRs a facing change in this hex forces: mud, -1, if running (p.124).
pub fn turn_psrs(info: &Hex) -> (i64, i64) {
    if info.features.has("mud") {
        (0, 1)
    } else {
        (0, 0)
    }
}

/// PSR modifier for each trigger: all +0 except mud's -1.
pub fn psr_modifier(cause: &str) -> i64 {
    match cause {
        "rubble" | "sand" | "water" | "backward level change" => 0,
        "mud" => -1,
        other => panic!("KeyError: {}", other),
    }
}

/// The triggers step_psrs counts, as names, for the mode actually used.
pub fn step_psr_causes(from_info: Option<&Hex>, to_info: &Hex, backward: bool, running: bool) -> Vec<&'static str> {
    let mut causes = Vec::new();
    let features = &to_info.features;
    if features.has("rubble") {
        causes.push("rubble");
    }
    let changes_level = from_info.map_or(false, |f| f.level != to_info.level);
    if features.has("sand") && changes_level {
        causes.push("sand");
    }
    if running && to_info.depth.unwrap_or(0) >= 1 {
        causes.push("water");
    }
    if backward && changes_level {
        causes.push("backward level change");
    }
    causes
}

pub const HAZARD_FEATURES: [&str; 2] = ["magma", "hazardous_liquid"];
pub const MAGMA_DAMAGE_PER_LEG: f64 = 7.0;
pub const POOL_EXPECTED_DAMAGE: f64 = 17.5 / 6.0;

/// Expected damage a standing 'Mech with `legs` legs takes entering (or starting its Movement Phase in) this hex.
pub fn step_hazard(info: &Hex, legs: i64) -> f64 {
    let features = &info.features;
    if !HAZARD_FEATURES.iter().any(|f| features.has(f)) {
        return 0.0;
    }
    let mut out = 0.0;
    let state = magma_state(features);
    if state == Some(MAGMA_LIQUID) {
        out += MAGMA_DAMAGE_PER_LEG * legs as f64;
    } else if state == Some(MAGMA_CRUST) {
        out += MAGMA_DAMAGE_PER_LEG * legs as f64 / 6.0;
    }
    if features.has("hazardous_liquid") {
        out += POOL_EXPECTED_DAMAGE;
    }
    out
}

/// Does any hex of this board carry a hazard feature? (Answered once per board, as the Python caches it.)
pub fn has_hazard_terrain(board: &Board) -> bool {
    *board.hazard_terrain.get_or_init(|| board.hexes.values().any(|info| HAZARD_FEATURES.iter().any(|f| info.features.has(f))))
}

/// Can any step on this board force a terrain PSR, or hurt? (Answered once per board.)
pub fn has_psr_terrain(board: &Board) -> bool {
    *board.psr_terrain.get_or_init(|| psr_terrain_scan(board))
}

fn psr_terrain_scan(board: &Board) -> bool {
    let mut levels: Vec<i64> = board.hexes.values().map(|h| h.level).collect();
    levels.sort();
    levels.dedup();
    levels.len() > 1
        || board.hexes.values().any(|info| {
            info.depth.unwrap_or(0) >= 1
                || ["rubble", "sand", "mud"].iter().chain(HAZARD_FEATURES.iter()).any(|f| info.features.has(f))
        })
}

/// MP to enter a hex with dest_features at dest_level from a non-road hex at current_level (no limits applied).
pub fn transition_cost(current_level: i64, dest_level: i64, dest_features: &Features) -> Result<i64, String> {
    let unsupported: Vec<&str> = {
        let mut v: Vec<&str> = dest_features.0.keys().map(|s| s.as_str()).filter(|f| unsupported_reason(f).is_some()).collect();
        v.sort();
        v
    };
    if !unsupported.is_empty() {
        let names = format!("[{}]", unsupported.iter().map(|s| py_repr_str(s)).collect::<Vec<_>>().join(", "));
        let why = unsupported.iter().map(|f| unsupported_reason(f).unwrap()).collect::<Vec<_>>().join("; ");
        return Err(format!("Destination hex has unsupported terrain {}: {}.", names, why));
    }
    let cost = BASE_ENTRY_COST + terrain_cost(dest_features, false)? + (dest_level - current_level).abs() * ELEVATION_COST_PER_LEVEL;
    assert!(cost >= 1, "transition_cost produced {} < 1 - violates the DP's load-bearing invariant.", cost);
    Ok(cost)
}

/// Checks a parsed board for terrain the simulator can't play yet and sets up water and buildings; call once when a
/// map loads. Err = Python's ValueError text.
pub fn prepare_board(board: &mut Board, passive_buildings: bool) -> Result<(), String> {
    let mut problems: BTreeMap<String, i64> = BTreeMap::new(); // sorted(problems.items()) = key order, so a BTreeMap
    let mut building_hexes = 0;
    for (_label, info) in board.hexes.iter_mut() {
        let features = info.features.clone();
        for f in features.0.keys() {
            if let Some(why) = unsupported_reason(f) {
                *problems.entry(why.to_string()).or_insert(0) += 1;
            }
        }
        for f in WOODS_FEATURES {
            let density: Option<String> =
                if features.has(f) { Some(features.first_param(f).unwrap_or("?").to_string()) } else { None };
            match density.as_deref() {
                Some(ULTRA_HEAVY_DENSITY) => info.impassable = true,
                Some(d) if d != "1" && d != "2" => {
                    *problems.entry(format!("{} density {} (not a TO:AR density)", f, d)).or_insert(0) += 1;
                }
                _ => {}
            }
        }
        if features.has("impassable") {
            info.impassable = true;
        }
        if features.has("magma") && magma_state(&features).and_then(magma_cost).is_none() {
            let params = py_list(features.get("magma").unwrap());
            *problems.entry(format!("magma {} (MegaMek writes 1 crust, 2 liquid)", params)).or_insert(0) += 1;
        }
        if features.has("hazardous_liquid") && !features.has("water") {
            *problems
                .entry("hazardous liquid off a water hex (TO:AR p.47: a pool is a water hex)".to_string())
                .or_insert(0) += 1;
        }
        if features.has("water") && info.depth.is_none() {
            let depth = water_depth(features.get("water").unwrap())?;
            if depth >= 1 {
                info.surface_level = Some(info.level);
                info.depth = Some(depth);
                info.level -= depth;
            }
        }
        if features.has("building") {
            building_hexes += 1;
            if passive_buildings && !info.building {
                let params = features.get("bldg_elev");
                let first = match params {
                    Some(p) if !p.is_empty() => p[0].clone(),
                    _ => "0".to_string(),
                };
                let height = py_int(&first)?;
                info.ground_level = Some(info.level);
                info.level += height;
                info.building = true;
            }
        }
    }
    if building_hexes > 0 && !passive_buildings {
        *problems
            .entry("buildings with the full Core rules (pp.130-136) - not built; set config.PASSIVE_BUILDINGS = True".to_string())
            .or_insert(0) += building_hexes;
    }
    if !problems.is_empty() {
        let listing = problems.iter().map(|(what, n)| format!("  - {}: {} hex(es)", what, n)).collect::<Vec<_>>().join("\n");
        return Err(format!("This map has terrain the simulator can't play yet:\n{}", listing));
    }
    Ok(())
}

fn py_list(items: &[String]) -> String {
    format!("[{}]", items.iter().map(|s| py_repr_str(s)).collect::<Vec<_>>().join(", "))
}
