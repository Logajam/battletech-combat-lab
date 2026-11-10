// Translated from INTEGRATION__orchestrator._attach_mech_config (session 22): the scenario inputs attached to a freshly
// parsed unit, and the equipment links made once per battle.
use crate::battle::{Battle, UnitId};
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
        m.current_heat = 0;
        m.shutdown = false;
        m.deactivated_heat_sinks = 0;
    }
    heat::attach_heat_traits(b, u);
    ammo::attach_ammo(b, u);
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
