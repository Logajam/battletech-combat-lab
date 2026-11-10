//! piloting_rolls, hazards and the water functions against the Python's own calls (python tools/port_tap.py piloting).
mod common;
use btsim_core::hazards;
use btsim_core::piloting_rolls as pr;
use btsim_core::water;
use common::*;

#[test]
fn piloting_hazards_water_match_python() {
    let taps = load_taps("piloting");
    assert!(taps.len() > 5000);
    let mut seen = std::collections::BTreeSet::new();
    for rec in &taps {
        let f = rec["fn"].as_str().unwrap();
        seen.insert(f.to_string());
        let (mut b, names) = make_battle(rec);
        b.piloting = rec["piloting"].as_i64().unwrap();
        let args: Vec<A> = rec["args"].as_array().unwrap().iter().map(decode).collect();
        let kw: std::collections::HashMap<String, A> = rec["kwargs"].as_object().unwrap().iter().map(|(k, v)| (k.clone(), decode(v))).collect();
        let get = |i: usize, name: &str| -> Option<A> { args.get(i).cloned().or_else(|| kw.get(name).cloned()) };
        let u = unit_of(&names, args[0].unit());
        let ret = decode(&rec["ret"]);
        match f {
            "piloting_rolls.preexisting_modifier" => assert_eq!(pr::preexisting_modifier(&b.units[u]), ret.int()),
            "piloting_rolls.special_case_modifier" => assert_eq!(pr::special_case_modifier(&b.units[u]), ret.int()),
            "piloting_rolls.snapshot_preexisting_damage" => pr::snapshot_preexisting_damage(&mut b.units[u]),
            "piloting_rolls.snapshot_pre_attack_phase" => pr::snapshot_pre_attack_phase(&mut b.units[u]),
            "piloting_rolls.resolve_fall" => {
                let cause = get(1, "cause").map(|a| a.str().to_string()).unwrap_or_default();
                let levels = get(2, "levels").map(|a| a.int()).unwrap_or(0);
                let side = get(3, "side").filter(|a| !a.is_null()).map(|a| a.str().to_string());
                pr::resolve_fall(&mut b, u, &cause, levels, side.as_deref());
            }
            "piloting_rolls.roll_psrs" => assert_eq!(pr::roll_psrs(&mut b, args[1].int(), args[2].int(), args[3].str()), ret.bool()),
            "piloting_rolls.can_stand" => assert_eq!(pr::can_stand(&b.units[u]), ret.bool()),
            "piloting_rolls.movement_psr_trigger" => {
                let got = pr::movement_psr_trigger(&b.units[u], args[1].str());
                match &ret { A::Null => assert!(got.is_none()), r => assert_eq!(got, Some(r.str())) }
            }
            "piloting_rolls.movement_psr_count" => assert_eq!(pr::movement_psr_count(&b.units[u], args[1].str()), ret.int()),
            "piloting_rolls.movement_psr_target_number" => {
                let got = pr::movement_psr_target_number(&b.units[u], args[1].str());
                match &ret { A::Null => assert!(got.is_none()), r => assert_eq!(got, Some(r.int())) }
            }
            "piloting_rolls.hd_gyro_jump_adjust" => assert_eq!(pr::hd_gyro_jump_adjust(&b.units[u], args[1].str()), ret.int()),
            "piloting_rolls.check_movement_psr" => {
                let cause = get(2, "cause").filter(|a| !a.is_null()).map(|a| a.str().to_string());
                assert_eq!(pr::check_movement_psr(&mut b, u, args[1].str(), cause.as_deref()), ret.bool());
            }
            "piloting_rolls.resolve_stand_up" => {
                let mp = get(1, "mp_available").filter(|a| !a.is_null()).map(|a| a.int());
                assert_eq!(pr::resolve_stand_up(&mut b, u, mp), ret.int());
            }
            "piloting_rolls.resolve_movement_phase" => assert_eq!(pr::resolve_movement_phase(&mut b, u), ret.int()),
            "piloting_rolls.resolve_attack_phase_psr" => {
                let forced: Vec<(String, i64)> = get(1, "forced_triggers").map(|a| a.list().iter().map(|t| (t.list()[0].str().to_string(), t.list()[1].int())).collect()).unwrap_or_default();
                pr::resolve_attack_phase_psr(&mut b, u, &forced);
            }
            "piloting_rolls.resolve_consciousness_checks" => pr::resolve_consciousness_checks(&mut b, u, args[1].str()),
            "piloting_rolls.resolve_end_phase_wakeup" => pr::resolve_end_phase_wakeup(&mut b, u),
            "hazards.magma_burn" => hazards::magma_burn(&mut b, u, args[1].str()),
            "hazards.pool_damage" => hazards::pool_damage(&mut b, u, args[1].str()),
            "hazards.enter_hex" => {
                let jumped = get(2, "jumped").map(|a| a.bool()).unwrap_or(false);
                let why = get(3, "why").filter(|a| !a.is_null()).map(|a| a.str().to_string());
                let in_phase = get(4, "in_phase").map(|a| a.bool()).unwrap_or(false);
                let got = hazards::enter_hex(&mut b, u, args[1].str(), jumped, why.as_deref(), in_phase);
                match &ret { A::Null => assert!(got.is_none()), r => assert_eq!(got, Some(r.str())) }
            }
            "hazards.free_roll" => hazards::free_roll(&mut b, u),
            "hazards.bog_down_roll" => assert_eq!(hazards::bog_down_roll(&mut b, u, args[1].str(), args[2].str()), ret.bool()),
            "hazards.start_of_movement" => hazards::start_of_movement(&mut b, u),
            "hazards.end_of_movement" => hazards::end_of_movement(&mut b, u),
            "hazards.magma_heat" => assert_eq!(hazards::magma_heat(&mut b, u), ret.int()),
            "hazards.after_fall" => hazards::after_fall(&mut b, u),
            "water.check_breach" => water::check_breach(&mut b, u, args[1].str()),
            "water.auto_breaches" => water::auto_breaches(&mut b, u),
            "water.drowning" => water::drowning(&mut b, u, args[1].bool()),
            "water.dissipation_bonus" => {
                let st = get(1, "water_state").filter(|a| !a.is_null()).map(|a| a.str().to_string());
                assert_eq!(water::dissipation_bonus(&b, u, st.as_deref()), ret.int());
            }
            "water.jump_mp" => assert_eq!(water::jump_mp(&b, u), ret.int()),
            other => panic!("{}", other),
        }
        check_after(rec, &b, &names, f);
    }
    assert!(seen.len() >= 25, "{:?}", seen);
}
