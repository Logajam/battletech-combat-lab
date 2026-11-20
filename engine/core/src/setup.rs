// Translated from INTEGRATION__orchestrator._attach_mech_config (session 22): the scenario inputs attached to a freshly
// parsed unit, and the equipment links made once per battle.
use serde_json::Value;

use crate::battle::{Battle, UnitId};
use crate::config::Config;
use crate::equipment_systems as equip;
use crate::orchestrator::reset_movement_state;
use crate::{advanced_equipment, ammo, capacitor, electronics, fire_modes, heat};

/// One side's settings (the keys of MECH_*_CONFIG plus "team"; a FORCES entry with the defaults filled in).
#[derive(Clone, Debug)]
pub struct UnitSetup {
    pub team: String,
    pub hex: Option<String>,
    pub facing: String,
    pub gunnery: i64,
    pub piloting: i64,
    pub min_heat: i64,
    pub max_heat: i64,
    pub search: Option<String>,
    pub assumes_enemy_search: Option<String>,
    /// "gladiator" / "princess" (config.BOT when the entry names none)
    pub bot: String,
    /// ammunition chosen per bin (FORCES "ammo": {"<location>:<slot>": "<munition>"}, slot counted from 0; N5): (location,
    /// slot, munition)
    pub ammo: Vec<(String, usize, String)>,
    /// C3 (FORCES "c3": {"parent": "<side name of its Master>"} or {"net": "<C3i network>"}; N6, c3.rs)
    pub c3_parent: Option<String>,
    pub c3_net: Option<String>,
}

pub fn attach_mech_config(b: &mut Battle, u: UnitId, cfg: &UnitSetup, side_name: &str) {
    {
        let m = &mut b.units[u];
        m.attached = true;
        m.side_name = Some(side_name.to_string());
        m.team = Some(cfg.team.clone());
        m.moved_this_turn = false;
        m.hex = cfg.hex.clone();
        m.facing = cfg.facing.clone();
        m.home_edge = None;
        m.gunnery = cfg.gunnery;
        m.piloting = cfg.piloting;
        m.min_heat = cfg.min_heat;
        m.max_heat = cfg.max_heat;
        m.move_search = cfg.search.clone();
        m.assumes_enemy_search = cfg.assumes_enemy_search.clone();
        m.bot = cfg.bot.clone();
        m.c3_parent = cfg.c3_parent.clone();
        m.c3_net = cfg.c3_net.clone();
        m.current_heat = 0;
        m.shutdown = false;
        m.deactivated_heat_sinks = 0;
    }
    heat::attach_heat_traits(b, u);
    ammo::attach_ammo(b, u);
    for (loc, slot, munition) in &cfg.ammo {
        ammo::choose_bin_munition(b, u, loc, *slot, munition);
    }
    electronics::attach(b, u);
    fire_modes::attach(b, u);
    capacitor::attach(b, u);
    advanced_equipment::attach(b, u);
    b.units[u].tag_designated = None;
    if b.units[u].has_tsm {
        let tsm = b.cfg.i("TSM_MIN_HEAT");
        let m = &mut b.units[u];
        m.min_heat = m.min_heat.max(tsm);
        m.max_heat = m.max_heat.max(m.min_heat);
        let line = format!("  {}: triple-strength myomer - min_heat {}, max_heat {}.", side_name, m.min_heat, m.max_heat);
        b.log(line);
    }
    heat::apply_heat_effects(b, u);
    reset_movement_state(&mut b.units[u]);
    heat::choose_heat_sink_deactivation(b, u, Some(1));
    let _ = equip::reset_movement_boost;
}

/// (mtf file name, label, settings) in roster order, as config.load_roster builds them: MECH_RED_* / MECH_BLUE_* for a
/// duel, else every FORCES entry `count` times, each named by its team ("Red", or "Red 2"... when a team has several)
/// unless it names itself, with FORCE_DEFAULTS under its own keys. (Moved here from tests/stage6_attach.rs for CL1,
/// session 25: that test proves it against every fixture.)
pub fn roster(cfg: &Config) -> Vec<(String, String, UnitSetup)> {
    let g = |c: &Value, k: &str| c.get(k).and_then(|x| x.as_i64()).unwrap();
    let s = |c: &Value, k: &str| c.get(k).and_then(|x| x.as_str()).map(|x| x.to_string());
    let default_bot = cfg.s("BOT").to_string();
    let setup = |c: &Value, team: &str| UnitSetup {
        team: team.to_string(),
        hex: s(c, "hex"),
        facing: s(c, "facing").unwrap(),
        gunnery: g(c, "gunnery"),
        piloting: g(c, "piloting"),
        min_heat: g(c, "min_heat"),
        max_heat: g(c, "max_heat"),
        search: s(c, "search"),
        assumes_enemy_search: s(c, "assumes_enemy_search"),
        bot: s(c, "bot").unwrap_or_else(|| default_bot.clone()).to_lowercase(),
        ammo: c.get("ammo").and_then(|a| a.as_object()).map_or(Vec::new(), |a| {
            a.iter()
                .filter_map(|(k, v)| {
                    let (loc, slot) = k.rsplit_once(':')?;
                    Some((loc.to_string(), slot.parse().ok()?, v.as_str()?.to_string()))
                })
                .collect()
        }),
        c3_parent: c.get("c3").and_then(|x| x.get("parent")).and_then(|x| x.as_str()).map(|x| x.to_string()),
        c3_net: c.get("c3").and_then(|x| x.get("net")).and_then(|x| x.as_str()).map(|x| x.to_string()),
    };
    if cfg.get("FORCES").is_null() {
        return vec![
            (cfg.s("MECH_RED_MTF").to_string(), "Red".to_string(), setup(cfg.get("MECH_RED_CONFIG"), "Red")),
            (cfg.s("MECH_BLUE_MTF").to_string(), "Blue".to_string(), setup(cfg.get("MECH_BLUE_CONFIG"), "Blue")),
        ];
    }
    let mut specs: Vec<Value> = Vec::new();
    for e in cfg.get("FORCES").as_array().unwrap() {
        for _ in 0..e.get("count").and_then(|c| c.as_i64()).unwrap_or(1) {
            specs.push(e.clone());
        }
    }
    let mut per_team: Vec<(String, i64)> = Vec::new();
    for e in &specs {
        let t = e["team"].as_str().unwrap().to_string();
        match per_team.iter_mut().find(|(x, _)| *x == t) {
            Some((_, n)) => *n += 1,
            None => per_team.push((t, 1)),
        }
    }
    let mut numbers: Vec<(String, i64)> = Vec::new();
    let mut out = Vec::new();
    for e in &specs {
        let team = e["team"].as_str().unwrap().to_string();
        let n = match numbers.iter_mut().find(|(x, _)| *x == team) {
            Some((_, n)) => {
                *n += 1;
                *n
            }
            None => {
                numbers.push((team.clone(), 1));
                1
            }
        };
        let of_team = per_team.iter().find(|(x, _)| *x == team).unwrap().1;
        let label = match e.get("name").and_then(|x| x.as_str()) {
            Some(nm) if !nm.is_empty() => nm.to_string(),
            _ => if of_team == 1 { team.clone() } else { format!("{} {}", team, n) },
        };
        // FORCE_DEFAULTS then the entry's keys
        let mut merged = cfg.get("FORCE_DEFAULTS").clone();
        for (k, v) in e.as_object().unwrap() {
            if !["count", "mtf", "name"].contains(&k.as_str()) {
                merged[k] = v.clone();
            }
        }
        out.push((e["mtf"].as_str().unwrap().to_string(), label, setup(&merged, &team)));
    }
    out
}
