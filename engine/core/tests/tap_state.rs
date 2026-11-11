//! mech_state queries and compute_tmm / get_weapons against the Python's calls (python tools/port_tap.py state).
mod common;
use btsim_core::damage_resolution::*;
use btsim_core::mech_state::*;
use common::*;
use serde_json::json;

#[test]
fn state_queries_match_python() {
    let taps = load_taps("state");
    assert!(taps.len() > 300);
    let mut seen = std::collections::BTreeSet::new();
    for rec in &taps {
        let f = rec["fn"].as_str().unwrap();
        seen.insert(f.to_string());
        let (mut b, names) = make_battle(rec);
        let args: Vec<A> = rec["args"].as_array().unwrap().iter().map(decode).collect();
        let u = unit_of(&names, args[0].unit());
        let ret = decode(&rec["ret"]);
        match f {
            "mech_state.is_destroyed" => {
                assert_eq!(b.is_destroyed(u), ret.bool(), "{}", f);
            }
            "mech_state.is_crippled" => assert_eq!(is_crippled(&b.units[u]), ret.bool()),
            "mech_state.compute_walk_mp" => assert_eq!(compute_walk_mp(&b.units[u]), ret.int()),
            "mech_state.compute_running_mp" => assert_eq!(compute_running_mp(&b.units[u]), ret.int()),
            "mech_state.compute_jump_mp" => assert_eq!(compute_jump_mp(&b.units[u]), ret.int()),
            "mech_state.compute_heat_dissipation" => assert_eq!(compute_heat_dissipation(&b.units[u]), ret.int()),
            "mech_state.hip_effects" => assert_eq!(hip_effects(&b.units[u]), ret.int()),
            "mech_state.ground_level_limited" => assert_eq!(ground_level_limited(&b.units[u]), ret.bool()),
            "mech_state.torso_cockpit_sensor_penalty" => assert_eq!(torso_cockpit_sensor_penalty(&b.units[u]), ret.int()),
            "mech_state.physical_attacker_modifier" => assert_eq!(physical_attacker_modifier(&b.units[u]), ret.int()),
            "mech_state.is_immobile" => assert_eq!(is_immobile(&b.units[u]), ret.bool()),
            "damage_resolution.compute_tmm" => assert_eq!(compute_tmm(&mut b.units[u]), ret.int()),
            "damage_resolution.get_weapons" => {
                let got: Vec<String> = get_weapons(&b.units[u]).iter().map(|i| b.units[u].item_json(*i, 1)["_addr"].as_str().unwrap().to_string()).collect();
                let want: Vec<String> = ret.list().iter().map(|a| match a { A::Item { addr, .. } => addr.clone(), o => panic!("{:?}", o) }).collect();
                assert_eq!(got, want);
            }
            "mech_state.mech_shields" => {
                let got = mech_shields(&b.units[u]).len();
                assert_eq!(got, ret.list().len());
            }
            other => panic!("{}", other),
        }
        let _ = json!(null);
        check_after(rec, &b, &names, f);
    }
    assert!(seen.len() >= 12, "{:?}", seen);
}
