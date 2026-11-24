//! COMBAT LAB CL2 (INTEGRATION__COMBAT_LAB_SPECS.md): a battle's full history, written by the Rust engine - what the
//! replay page draws. The same record the Python wrote for its replay pages (`INTEGRATION__replay.py`), key for key,
//! so `INTEGRATION__replay_viewer.html` shows a Rust battle unchanged:
//!
//! ```text
//! {"sim", "seed" (text: seeds pass JavaScript's exact-integer limit),
//!  "mechs": {label: {name, bot, tons, max_hp, locations, max: {loc: [armor, rear, structure]}}},
//!  "teams": {label: team}, "team_order": [team, ...],
//!  "board": {width, height, hexes: {label: {"l": level, "f": {feature: first param}, "b": 1 if a building}}},
//!  "steps": [{"turn", "phase", "state": {label: UNIT STATE}, "log": [lines since the last step]}],
//!  "result": {"winner", "turns", "causes": {label: cause of death or null}}}
//! UNIT STATE = {hex, facing, twist, prone, shutdown, destroyed, heat, hp, pilot_hits,
//!               locs: {loc: [armor, rear, structure, destroyed]}}
//! ```
//!
//! A step is one point of the turn (the orchestrator's `Marks`): "Deployment", each unit's "<label> moves", "Ranged
//! attacks", "Physical attacks", "Heat and end phase"; log lines written after the last of them go to a final
//! "Battle over" step. A battle is (setup, seed): the same pair always gives the same history, so the Lab keeps only
//! seeds and re-makes a history when one is asked for (`Scenario::run_history`).
//!
//! RECORDING CHANGES NOTHING: it only reads. Whether a unit is destroyed is asked of a copy (`mech_state::is_destroyed`
//! marks the unit it is asked about), so the battle draws the same dice with or without a history.
use serde_json::{json, Map, Value};

use crate::battle::Battle;
use crate::results::BattleResult;

/// A history being recorded: `mark` at every step, `finish` at the end.
pub struct History {
    data: Map<String, Value>,
    steps: Vec<Value>,
    /// one entry per step (Combat Lab, CL21): Princess's team heat maps and each unit's reach at that step
    heat: Vec<Value>,
    /// how many of the battle's log lines are in a step already
    logged: usize,
}

impl History {
    /// Starts the record of battle number `sim` (its place in the batch) on `seed`, before the battle starts.
    pub fn new(sim: u64, seed: u64) -> History {
        let mut data = Map::new();
        data.insert("sim".into(), json!(sim));
        data.insert("seed".into(), json!(seed.to_string()));
        History { data, steps: Vec::new(), heat: Vec::new(), logged: 0 }
    }

    /// The `Marks` hook: one step, the units as they are now and the log lines since the last step. The first step
    /// (Deployment) also writes the header: units, teams and board.
    pub fn mark(&mut self, b: &Battle, turn: i64, phase: &str) {
        if !self.data.contains_key("mechs") {
            self.header(b);
        }
        let mut state = Map::new();
        for u in 0..b.units.len() {
            state.insert(label(b, u), unit_state(b, u));
        }
        // config.log's lines only: a bare print went to the screen, not to the Python's replay record
        let lines: Vec<&String> = (self.logged..b.log.lines.len()).filter(|i| !b.log.printed.contains(i)).map(|i| &b.log.lines[i]).collect();
        self.logged = b.log.lines.len();
        self.steps.push(json!({"turn": turn, "phase": phase, "state": state, "log": lines}));
        self.heat.push(heat_now(b));
    }

    /// The finished record. Log lines written after the last step (the battle's end) make a "Battle over" step.
    pub fn finish(mut self, b: &Battle, result: &BattleResult) -> Value {
        if (self.logged..b.log.lines.len()).any(|i| !b.log.printed.contains(&i)) {
            self.mark(b, result.turns_taken, "Battle over");
        }
        let causes: Map<String, Value> = result.units.iter().map(|(k, s)| (k.clone(), json!(s.cause_of_death))).collect();
        self.data.insert("steps".into(), Value::Array(self.steps));
        // the heat maps ride beside the steps (a separate list, same length), only when some team has Princess units
        if self.heat.iter().any(|h| !h["maps"].as_object().is_none_or(|m| m.is_empty())) {
            self.data.insert("heat".into(), Value::Array(self.heat));
        }
        // the event records (events.rs), for the replay page's search; a record made before they existed has no "events"
        if b.log.ev.on {
            self.data.insert("events_version".into(), json!(crate::events::EVENT_VERSION));
            self.data.insert("events".into(), crate::events::events_json(b));
        }
        self.data.insert("result".into(), json!({"winner": result.winner, "turns": result.turns_taken, "causes": causes}));
        Value::Object(self.data)
    }

    fn header(&mut self, b: &Battle) {
        let mut mechs = Map::new();
        let mut teams = Map::new();
        let mut team_order: Vec<String> = Vec::new();
        for u in 0..b.units.len() {
            let m = &b.units[u];
            let side = label(b, u);
            let max: Map<String, Value> = m
                .locations
                .keys()
                .map(|loc| {
                    let get = |t: &crate::fasthash::IndexMap<String, i64>| t.get(loc).copied().unwrap_or(0);
                    (loc.clone(), json!([get(&m.max_armor), get(&m.max_rear_armor), get(&m.max_structure)]))
                })
                .collect();
            mechs.insert(
                side.clone(),
                json!({
                    "name": format!("{} {}", m.chassis, m.model).trim(),
                    "bot": m.bot,
                    "tons": m.mass,
                    "max_hp": crate::attack_resolution::total_hp(m).to_json(),
                    "locations": m.locations.keys().collect::<Vec<_>>(),
                    "max": max,
                }),
            );
            let team = m.team.clone().unwrap_or_else(|| side.clone());
            if !team_order.contains(&team) {
                team_order.push(team.clone());
            }
            teams.insert(side, json!(team));
        }
        self.data.insert("mechs".into(), Value::Object(mechs));
        self.data.insert("teams".into(), Value::Object(teams));
        self.data.insert("team_order".into(), json!(team_order));
        self.data.insert("board".into(), board(b));
    }
}

/// What Princess's heat map looks like right now (CL21): {"maps": {team: {hex label: weight}}, "reach": {unit label: hexes}}.
/// The map is the BV-weighted record of where her team's units have stood (INTEGRATION__princess_memory), recomputed by the
/// replay itself from the seed, so any step shows what her memory held at that step. "reach" is how far each standing
/// unit could move this turn (its run MP, or jump MP when larger), by straight hex distance: the Replay masks a unit's
/// share of the team map with it (terrain is ignored).
fn heat_now(b: &Battle) -> Value {
    let mut maps = Map::new();
    for (team, mem) in b.princess.teams.iter() {
        let live: Map<String, Value> = mem.heat.activity.iter().filter(|(_, w)| **w > 0).map(|(k, w)| (k.clone(), json!(w))).collect();
        if !live.is_empty() {
            maps.insert(team.clone(), Value::Object(live));
        }
    }
    let mut reach = Map::new();
    if !maps.is_empty() {
        for u in 0..b.units.len() {
            let m = &b.units[u];
            if m.hex.is_none() || m.destroyed {
                continue;
            }
            let walk = crate::mech_state::compute_walk_mp(m);
            let run = (walk as f64 * 1.5).ceil() as i64;
            reach.insert(label(b, u), json!(run.max(crate::mech_state::compute_jump_mp(m))));
        }
    }
    json!({"maps": maps, "reach": reach})
}

fn label(b: &Battle, u: usize) -> String {
    b.units[u].side_name.clone().unwrap_or_default()
}

/// One unit's state now (`_mech_state` of INTEGRATION__replay.py).
pub fn unit_state(b: &Battle, u: usize) -> Value {
    let m = &b.units[u];
    let ttd = b.cfg.has("FIGHT_TO_THE_DEATH") && b.cfg.b("FIGHT_TO_THE_DEATH");
    // asked of a copy: is_destroyed marks the unit it decides about (recording must change nothing)
    let destroyed = m.destroyed || crate::mech_state::is_destroyed(&mut m.clone(), ttd);
    let locs: Map<String, Value> = m
        .locations
        .iter()
        .map(|(loc, l)| (loc.clone(), json!([l.armor.to_json(), l.rear_armor.map_or(json!(0), |r| r.to_json()), l.structure.to_json(), l.destroyed])))
        .collect();
    json!({
        "hex": m.hex,
        "facing": m.facing,
        "twist": crate::arcs::current_action(m).twist,
        "prone": m.prone,
        "shutdown": m.shutdown,
        "destroyed": destroyed,
        "heat": m.current_heat,
        "hp": crate::attack_resolution::total_hp(m).to_json(),
        "pilot_hits": m.pilot_hits,
        "locs": locs,
    })
}

/// Width, height and each hex's level and terrain features (`_board`): a water hex shows its surface, a building its
/// roof ("b": 1).
pub fn board(b: &Battle) -> Value {
    let mut hexes = Map::new();
    for (label, h) in &b.board.hexes {
        let feats: Map<String, Value> = h
            .features
            .0
            .iter()
            .filter(|(k, _)| k.as_str() != "foliage_elev")
            .map(|(k, v)| (k.clone(), v.first().map_or(json!([]), |p| json!(p))))
            .collect();
        let mut hex = json!({"l": h.surface_level.unwrap_or(h.level), "f": feats});
        if h.building {
            hex["b"] = json!(1);
        }
        hexes.insert(label.clone(), hex);
    }
    json!({"width": b.board.width, "height": b.board.height, "hexes": hexes})
}

// =====================================================================================================================
// THE REPLAY PAGE: INTEGRATION__replay_viewer.html with a history inside (INTEGRATION__replay.py's render / file_name)
// =====================================================================================================================

/// The viewer page, built into the program (it opens in any browser with no other file).
const VIEWER: &str = include_str!("../../../INTEGRATION__replay_viewer.html");
const DATA_PLACEHOLDER: &str = "__REPLAY_JSON__";

/// The battle's sides as the page names them: a team of one unit by its mech ("Kontio"), a force by its team name and
/// size ("Red 4 units").
fn sides(record: &Value) -> Vec<String> {
    let mechs = record["mechs"].as_object().cloned().unwrap_or_default();
    let teams: Vec<String> = match record["team_order"].as_array() {
        Some(t) if !t.is_empty() => t.iter().filter_map(|x| x.as_str().map(String::from)).collect(),
        _ => mechs.keys().cloned().collect(),
    };
    teams
        .iter()
        .map(|t| {
            let members: Vec<&String> = mechs.keys().filter(|s| record["teams"][s.as_str()].as_str().unwrap_or(s) == t).collect();
            if members.len() == 1 {
                mechs[members[0].as_str()]["name"].as_str().unwrap_or("").to_string()
            } else {
                format!("{} {} units", t, members.len())
            }
        })
        .collect()
}

/// The page's file name: "<side>_vs_<side>_battle<N>_seed<S>.html", anything but letters, digits, "_", "." and "-"
/// made "_".
pub fn file_name(record: &Value) -> String {
    let stem = format!("{}_battle{}_seed{}", sides(record).join("_vs_"), record["sim"], record["seed"].as_str().unwrap_or(""));
    let mut out = String::new();
    let mut in_bad = false;
    for c in stem.chars() {
        if c.is_ascii_alphanumeric() || c == '_' || c == '.' || c == '-' {
            out.push(c);
            in_bad = false;
        } else if !in_bad {
            out.push('_');
            in_bad = true;
        }
    }
    out + ".html"
}

/// The viewer page with this battle's history inside it.
pub fn page(record: &Value) -> String {
    // "</" would end the <script> holding the data early
    let payload = serde_json::to_string(record).unwrap().replace("</", "<\\/");
    let title = format!("{}, battle {}", sides(record).join(" vs "), record["sim"]);
    let title = title.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;").replace('"', "&quot;").replace('\'', "&#x27;");
    VIEWER.replacen("<title>Battle Replay</title>", &format!("<title>{}</title>", title), 1).replacen(DATA_PLACEHOLDER, &payload, 1)
}
