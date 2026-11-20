//! PER-TEAM BOT SETTINGS (backlog N5; Daniel, 2026-11-20: a "Configure team" window holding "the Princess/CASPAR control
//! sliders ... plus any other options or switches a bot may have", so they can leave the Options tab). Rust only.
//!
//! The settings file may carry TEAM_SETTINGS = {"<team>": {"<setting>": value, ...}, ...}: for each team, settings that
//! differ from the battle's own. The battle keeps one settings copy per such team (`Battle::team_cfgs`: the battle's
//! settings with the team's on top), and while a unit's bot decides (every `BotSet` choice made for one unit, the End
//! Phase heat-equipment review of each unit, Legate's estimate for each team) that copy stands in for `Battle::cfg`
//! (`with_unit` / `with_team`). So the many places a bot reads a setting need no change, and a team without overrides plays
//! exactly as before. The Combat Lab only puts bot settings there (the rules stay the same for everyone); the engine does
//! not stop other settings, and says so here rather than guess.
//!
//! Inside a decision, a bot also models its enemies (Gladiator's two-ply reply, Hydra's forecast): it does that with ITS
//! OWN team's settings, as a player would. Choices made for several units at once (the fire order `fire_pick`, Hydra's
//! move order `move_pick`) read the battle's settings.
use serde_json::Value;

use crate::battle::{Battle, UnitId};
use crate::config::Config;

/// The setting that holds the overrides.
pub const KEY: &str = "TEAM_SETTINGS";

/// The per-team copies for a battle's settings: (team, its settings).
pub fn build(cfg: &Config) -> Vec<(String, Option<Config>)> {
    if !cfg.has(KEY) {
        return Vec::new();
    }
    let Some(teams) = cfg.get(KEY).as_object() else { return Vec::new() };
    let mut out = Vec::new();
    for (team, over) in teams {
        let Some(over) = over.as_object() else { continue };
        if over.is_empty() {
            continue;
        }
        let mut values: serde_json::Map<String, Value> = cfg.values.iter().map(|(k, v)| (k.clone(), v.clone())).collect();
        for (k, v) in over {
            values.insert(k.clone(), v.clone());
        }
        out.push((team.clone(), Some(Config::from_json(&Value::Object(values)))));
    }
    out
}

/// Runs `f` with `team`'s settings standing in for the battle's (if it has its own and they are not already in place).
pub fn with_team<R>(b: &mut Battle, team: Option<&str>, f: impl FnOnce(&mut Battle) -> R) -> R {
    let slot = team.and_then(|t| b.team_cfgs.iter().position(|(n, c)| n == t && c.is_some()));
    let Some(i) = slot else { return f(b) };
    let mut theirs = b.team_cfgs[i].1.take().unwrap();
    std::mem::swap(&mut b.cfg, &mut theirs);
    let out = f(b);
    std::mem::swap(&mut b.cfg, &mut theirs);
    b.team_cfgs[i].1 = Some(theirs);
    out
}

/// Runs `f` with the settings of unit `u`'s team.
pub fn with_unit<R>(b: &mut Battle, u: UnitId, f: impl FnOnce(&mut Battle) -> R) -> R {
    let team = b.units[u].team.clone();
    with_team(b, team.as_deref(), f)
}
