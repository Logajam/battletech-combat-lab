//! Stage 9: a scenario (what `tools/port_scenario.py` writes: config.json, units.json, board.json, meta.json) and the
//! batch runner. One battle is built and played inside the thread that runs it, on its own `PcgDice` seed.
use std::fs;
use std::path::Path;

use serde_json::Value;

use crate::battle::{Battle, Dice};
use crate::board_parser::Board;
use crate::config::Config;
use crate::dice::PcgDice;
use crate::gladiator_bots::GladiatorBots;
use crate::mech_state::Mech;
use crate::orchestrator::{play_on, start_battle};
use crate::results::BattleResult;

pub struct Scenario {
    pub config: Value,
    pub board: Value,
    pub units: Value,
    pub max_turns: i64,
    /// teams whose every unit is driven by Hydra, whatever units.json says (btsim --hydra TEAM[,TEAM])
    pub hydra_teams: Vec<String>,
}

fn read(p: &Path) -> Value {
    serde_json::from_str(&fs::read_to_string(p).unwrap_or_else(|e| panic!("{}: {}", p.display(), e))).unwrap()
}

/// The standard game's turn cap (Daniel, 2026-11-12: "Set the standard game cap to 100 rounds"; it was 50). A battle that
/// reaches it ends with no winner. The Python answer key and its recorded fixtures keep their own cap (50).
pub const STANDARD_MAX_TURNS: i64 = 100;

impl Scenario {
    pub fn load(dir: &Path) -> Scenario {
        // THE TURN CAP: STANDARD_MAX_TURNS for every scenario (btsim --max-turns changes it for a run). A meta.json's
        // max_turns is the Python's old 50 (config.MAX_TURNS, written by the export) and is not read.
        Scenario { hydra_teams: Vec::new(), config: read(&dir.join("config.json")), board: read(&dir.join("board.json")), units: read(&dir.join("units.json")), max_turns: STANDARD_MAX_TURNS }
    }

    /// Builds the battle (units, board, config) around a dice source.
    pub fn battle(&self, dice: Box<dyn Dice>) -> Battle {
        let cfg = Config::from_json(&self.config);
        let board = Board::from_json(&self.board);
        let names: Vec<String> = self.units.as_object().unwrap().keys().cloned().collect();
        let idx = |n: &str| names.iter().position(|x| x == n).unwrap();
        let mut units: Vec<Mech> = names.iter().map(|n| Mech::from_json(&self.units[n], &idx)).collect();
        for m in units.iter_mut() {
            if m.team.as_ref().is_some_and(|t| self.hydra_teams.contains(t)) {
                m.bot = "hydra".to_string();
            }
        }
        Battle::new(cfg, board, units, dice)
    }

    /// One battle on `seed`, with a LEDGER SNAPSHOT at the end of every turn and once more when the battle is over
    /// (S6 calibration of Hydra's Forecast, session 25; INTEGRATION__HYDRA.md Section 7). A snapshot is
    /// {"turn", "units": [[unit, team, life, guns, armor, structure], ...]}: life = `effective_hp` (0 once destroyed), guns = the
    /// unit's `future_damage` on the first standing enemy a turn (0 once destroyed or with no enemy left) - the raw
    /// figures Hydra's ledger is built from (its "dormant" and "minimum" rules are applied by the fitting tool).
    /// Recording only reads; tests/check_rust_reference.py-style runs show the battle is the same with or without it.
    pub fn run_recorded(&self, seed: u64) -> (BattleResult, Vec<Value>) {
        let mut b = self.battle(Box::new(PcgDice::new(seed)));
        let mut snaps: Vec<Value> = Vec::new();
        let mut marks = |b: &mut Battle, turn: i64, label: &str| {
            if label == "Heat and end phase" {
                snaps.push(snapshot(b, turn));
            }
        };
        let mut play = start_battle(&mut b, self.max_turns, &mut marks);
        let mut bots = GladiatorBots;
        play_on(&mut b, &mut bots, &mut play, &mut marks);
        let last = play.result.turns_taken;
        snaps.push(snapshot(&mut b, last));
        (play.result, snaps)
    }

    /// One battle on `seed`: the result and its log (when `want_log`).
    pub fn run(&self, seed: u64, want_log: bool) -> (BattleResult, Vec<String>) {
        let mut b = self.battle(Box::new(PcgDice::new(seed)));
        let mut marks = |_: &mut Battle, _: i64, _: &str| {};
        let mut play = start_battle(&mut b, self.max_turns, &mut marks);
        let mut bots = GladiatorBots;
        play_on(&mut b, &mut bots, &mut play, &mut marks);
        let log = if want_log { b.log.lines.clone() } else { vec![] };
        (play.result, log)
    }
}

/// The ledger's raw figures for every unit now (see `Scenario::run_recorded`).
fn snapshot(b: &mut Battle, turn: i64) -> Value {
    let alive = crate::forces::standing(b);
    let per_turn = b.cfg.f("MOVEMENT_LIFETIME_INITIATIVE");
    let mut rows = Vec::new();
    for u in 0..b.units.len() {
        let team = b.units[u].team.clone().unwrap_or_default();
        // raw armor (front + rear) and internal structure of the locations still standing (second pass: lets the fitting
        // tool try other structure weights than MOVEMENT_STRUCTURE_WEIGHT)
        let (mut armor, mut structure) = (0.0, 0.0);
        if alive.contains(&u) {
            for v in b.units[u].locations.values() {
                if !v.destroyed {
                    armor += v.armor.f() + v.rear_armor.map_or(0.0, |r| r.f());
                    structure += v.structure.f();
                }
            }
        }
        let (life, guns) = if alive.contains(&u) {
            let foe = alive.iter().copied().find(|v| b.units[*v].team != b.units[u].team);
            let guns = match foe {
                Some(f) => crate::move_select::future_damage(b, u, f) / if per_turn > 0.0 { per_turn } else { 1.0 },
                None => 0.0,
            };
            (crate::orchestrator::effective_hp(b, u), guns)
        } else {
            (0.0, 0.0)
        };
        rows.push(serde_json::json!([u, team, life, guns, armor, structure]));
    }
    serde_json::json!({"turn": turn, "units": rows})
}
