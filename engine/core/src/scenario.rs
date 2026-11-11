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
}

fn read(p: &Path) -> Value {
    serde_json::from_str(&fs::read_to_string(p).unwrap_or_else(|e| panic!("{}: {}", p.display(), e))).unwrap()
}

impl Scenario {
    pub fn load(dir: &Path) -> Scenario {
        let meta = read(&dir.join("meta.json"));
        Scenario { config: read(&dir.join("config.json")), board: read(&dir.join("board.json")), units: read(&dir.join("units.json")), max_turns: meta["max_turns"].as_i64().unwrap_or(50) }
    }

    /// Builds the battle (units, board, config) around a dice source.
    pub fn battle(&self, dice: Box<dyn Dice>) -> Battle {
        let cfg = Config::from_json(&self.config);
        let board = Board::from_json(&self.board);
        let names: Vec<String> = self.units.as_object().unwrap().keys().cloned().collect();
        let idx = |n: &str| names.iter().position(|x| x == n).unwrap();
        let units: Vec<Mech> = names.iter().map(|n| Mech::from_json(&self.units[n], &idx)).collect();
        Battle::new(cfg, board, units, dice)
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
