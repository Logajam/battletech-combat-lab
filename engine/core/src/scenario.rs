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

#[derive(Clone)]
pub struct Scenario {
    pub config: Value,
    pub board: Value,
    pub units: Value,
    pub max_turns: i64,
    /// teams whose every unit is driven by Hydra, whatever units.json says (btsim --hydra TEAM[,TEAM])
    pub hydra_teams: Vec<String>,
    /// teams whose every unit is driven by CASPAR (btsim --caspar TEAM[,TEAM])
    pub caspar_teams: Vec<String>,
}

fn read(p: &Path) -> Value {
    serde_json::from_str(&fs::read_to_string(p).unwrap_or_else(|e| panic!("{}: {}", p.display(), e))).unwrap()
}

/// The standard game's turn cap (Daniel, 2026-11-12: "Set the standard game cap to 100 rounds"; it was 50). A battle that
/// reaches it ends with no winner. The Python answer key and its recorded fixtures keep their own cap (50).
pub const STANDARD_MAX_TURNS: i64 = 100;

/// Where `Scenario::from_settings` finds its files: the settings defaults (`engine/defaults/config.json`) and the
/// data folder its `DATA_DIR` setting is relative to (the repository root, as the Python ran).
pub struct SetupPaths {
    pub defaults: std::path::PathBuf,
    pub root: std::path::PathBuf,
    /// Files held in memory instead of on disk (the browser build, engine/wasm: there is no disk there). When set,
    /// the settings defaults come from `memory.defaults` and a data file `name` (a unit or board id) from
    /// `memory.files[name]`. `None` = read from `defaults` and `root/DATA_DIR` as always.
    pub memory: Option<MemoryFiles>,
}

/// The files a scenario needs, held in memory (see `SetupPaths::memory`).
#[derive(Clone, Default)]
pub struct MemoryFiles {
    /// engine/defaults/config.json's text
    pub defaults: String,
    /// unit and board files by the name the settings give them
    pub files: std::collections::HashMap<String, String>,
}

impl SetupPaths {
    /// The project folder this program runs from: BTSIM_ROOT, else the nearest folder at or above the running program
    /// that holds `engine/defaults/config.json` - the repository root for engine/target/release/btsim, and the
    /// unpacked folder itself for a packaged Combat Lab (CombatLab.exe beside data/ and engine/defaults/).
    pub fn find() -> SetupPaths {
        let root = std::env::var("BTSIM_ROOT").map(std::path::PathBuf::from).unwrap_or_else(|_| {
            std::env::current_exe()
                .ok()
                .and_then(|e| e.ancestors().skip(1).find(|p| p.join("engine").join("defaults").join("config.json").exists()).map(|p| p.to_path_buf()))
                .unwrap_or_else(|| std::path::PathBuf::from("."))
        });
        SetupPaths::at(&root)
    }

    /// From the repository root.
    pub fn at(root: &Path) -> SetupPaths {
        SetupPaths { defaults: root.join("engine").join("defaults").join("config.json"), root: root.to_path_buf(), memory: None }
    }

    /// The settings defaults' text (from memory or from the file).
    pub fn defaults_text(&self) -> Result<String, String> {
        match &self.memory {
            Some(m) => Ok(m.defaults.clone()),
            None => fs::read_to_string(&self.defaults).map_err(|e| format!("{}: {}", self.defaults.display(), e)),
        }
    }
}

impl Scenario {
    /// COMBAT LAB CL1 (INTEGRATION__COMBAT_LAB_SPECS.md; also the MegaMek bridge's start, B3): a scenario built in Rust from
    /// SETTINGS - a JSON object of the settings that differ from the defaults, under the Python's own names (`FORCES`,
    /// or `MECH_RED_MTF` / `MECH_BLUE_MTF` and their `_CONFIG`; `DEFAULT_BOARD_PATH` or `STITCH_MAPS` with
    /// `STITCH_BOARDS`; `DEPLOYMENT`; any other switch). No Python needed. The same steps as the Python's battle start:
    /// the roster (`setup::roster`), each unit parsed from its `.mtf` and given its settings (`attach_mech_config`),
    /// the board parsed (or stitched) and prepared (`terrain_rules::prepare_board`). Deployment is not done here: the
    /// battle does it on its own dice, as with a scenario folder. Err = what is wrong (a missing file, a bad board).
    /// Board names are files under DATA_DIR; maps packed in `data/maps.zip` must be unpacked first.
    pub fn from_settings(settings: &Value, paths: &SetupPaths) -> Result<Scenario, String> {
        use crate::battle::TapeDice;
        let text = paths.defaults_text()?;
        let mut config: Value = serde_json::from_str(&text).map_err(|e| format!("{}: {}", paths.defaults.display(), e))?;
        for (k, v) in settings.as_object().ok_or("the settings must be a JSON object")? {
            config[k.as_str()] = v.clone();
        }
        let cfg = Config::from_json(&config);
        let data = paths.root.join(cfg.s("DATA_DIR"));
        let read = |name: &str| -> Result<(String, String), String> {
            if let Some(m) = &paths.memory {
                return m.files.get(name).map(|t| (name.to_string(), t.clone())).ok_or_else(|| format!("{}: no such unit or board", name));
            }
            let p = data.join(name);
            let t = fs::read_to_string(&p).map_err(|e| format!("{}: {} (a map packed in data/maps.zip must be unpacked first)", p.display(), e))?;
            Ok((p.to_string_lossy().to_string(), t))
        };
        let mut out = String::new();
        let mut board = if cfg.b("STITCH_MAPS") {
            let names: Vec<String> = cfg.get("STITCH_BOARDS").as_array().ok_or("STITCH_BOARDS")?.iter().map(|n| n.as_str().unwrap().to_string()).collect();
            let files = names.iter().map(|n| read(n)).collect::<Result<Vec<_>, _>>()?;
            crate::board_parser::stitch_boards(&files, cfg.i("STITCH_GRID_COLS"), cfg.i("STITCH_GRID_ROWS"), &mut out)?
        } else {
            let (p, t) = read(cfg.s("DEFAULT_BOARD_PATH"))?;
            crate::board_parser::parse_board_file(&p, &t, &mut out)?
        };
        crate::terrain_rules::prepare_board(&mut board, cfg.b("PASSIVE_BUILDINGS"))?;
        let entries = crate::setup::roster(&cfg);
        let db = crate::equipment::EquipmentDb::load();
        let mut mechs = Vec::new();
        for (mtf, label, _) in &entries {
            let (_, t) = read(mtf)?;
            mechs.push(crate::mtf_parser::parse_mtf(&db, &t, &mut out).map_err(|e| format!("{} ({}): {}", label, mtf, e))?);
        }
        let board_json = board.to_json();
        let mut b = Battle::new(cfg, board, mechs, Box::new(TapeDice::new(vec![])));
        for (u, (_, label, setup)) in entries.iter().enumerate() {
            crate::setup::attach_mech_config(&mut b, u, setup, label);
        }
        for m in b.units.iter_mut() {
            m.assign_addresses();
        }
        let names: Vec<String> = entries.iter().map(|e| e.1.clone()).collect();
        let name_of = |i: usize| names[i].clone();
        let mut units = serde_json::Map::new();
        for (i, n) in names.iter().enumerate() {
            units.insert(n.clone(), b.units[i].to_json(&name_of));
        }
        config.as_object_mut().unwrap().remove("_ACTIVE_RNG");
        Ok(Scenario { hydra_teams: Vec::new(), caspar_teams: Vec::new(), config, board: board_json, units: Value::Object(units), max_turns: STANDARD_MAX_TURNS })
    }

    pub fn load(dir: &Path) -> Scenario {
        // THE TURN CAP: STANDARD_MAX_TURNS for every scenario (btsim --max-turns changes it for a run). A meta.json's
        // max_turns is the Python's old 50 (config.MAX_TURNS, written by the export) and is not read.
        Scenario { hydra_teams: Vec::new(), caspar_teams: Vec::new(), config: read(&dir.join("config.json")), board: read(&dir.join("board.json")), units: read(&dir.join("units.json")), max_turns: STANDARD_MAX_TURNS }
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
            if m.team.as_ref().is_some_and(|t| self.caspar_teams.contains(t)) {
                m.bot = "caspar".to_string();
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

    /// The MegaMek bridge's start line for this scenario (`bridge::Session::start`): settings, board, units, Hydra's and
    /// CASPAR's teams.
    pub fn bridge_start(&self, seed: u64) -> Value {
        serde_json::json!({"config": self.config, "board": self.board, "units": self.units, "hydra_teams": self.hydra_teams, "caspar_teams": self.caspar_teams, "seed": seed})
    }

    /// One battle on `seed` with the bots inside a `bridge::Recorder` and a fresh `bridge::Session` checked alongside
    /// (MegaMek bridge B1): the result, what the check found, and every line when `keep`. `compact`: the units go to the
    /// session as compact states (B3), which must be enough for every answer. The battle is the same as `run`
    /// on that seed (the recorder only reads and passes calls on).
    /// The fourth value is the battle's log (the same lines `run` gives: recording only reads), so one run can serve both the
    /// bridge's parity check and the reference-log check (tests/check_rust_reference.py --parity, 2026-11-17).
    pub fn run_bridge_checked(&self, seed: u64, keep: bool, compact: bool, view: bool) -> (BattleResult, crate::bridge::Parity, Vec<Value>, Vec<String>) {
        let mut b = self.battle(Box::new(PcgDice::new(seed)));
        let mut marks = |_: &mut Battle, _: i64, _: &str| {};
        let mut play = start_battle(&mut b, self.max_turns, &mut marks);
        let mut inner = GladiatorBots;
        let session = crate::bridge::Session::start(&self.bridge_start(seed));
        let mut rec = crate::bridge::Recorder::new(&mut inner, Some(session), keep, compact);
        rec.view = view;
        play_on(&mut b, &mut rec, &mut play, &mut marks);
        let (parity, lines) = (rec.parity, rec.lines);
        (play.result, parity, lines, b.log.lines.clone())
    }

    /// COMBAT LAB CL2: one battle on `seed` (battle number `sim` of its batch) with its full history (`history.rs`, the
    /// replay page's record). The battle is the same as `run` on that seed: recording only reads.
    pub fn run_history(&self, sim: u64, seed: u64) -> (BattleResult, Value) {
        let mut b = self.battle(Box::new(PcgDice::new(seed)));
        let mut history = crate::history::History::new(sim, seed);
        let mut marks = |b: &mut Battle, turn: i64, label: &str| history.mark(b, turn, label);
        let mut play = start_battle(&mut b, self.max_turns, &mut marks);
        let mut bots = GladiatorBots;
        play_on(&mut b, &mut bots, &mut play, &mut marks);
        let record = history.finish(&b, &play.result);
        (play.result, record)
    }

    /// One battle on `seed` with the caller's bots (BattleROM: a `human_bots::HumanBots`). With `GladiatorBots` it is `run`.
    pub fn run_with(&self, seed: u64, bots: &mut dyn crate::orchestrator::BotSet, want_log: bool) -> (BattleResult, Vec<String>) {
        let mut b = self.battle(Box::new(PcgDice::new(seed)));
        let mut marks = |_: &mut Battle, _: i64, _: &str| {};
        let mut play = start_battle(&mut b, self.max_turns, &mut marks);
        play_on(&mut b, bots, &mut play, &mut marks);
        let log = if want_log { b.log.lines.clone() } else { vec![] };
        (play.result, log)
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
