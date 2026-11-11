//! attack_resolution (resolution parts), physical_gear, smoke.probe and physical._location against the Python's own
//! calls (python tools/port_tap.py attack).
mod common;
use btsim_core::attack_resolution as ar;
use btsim_core::attack_resolution::Cover;
use btsim_core::mech_state::DamageType;
use btsim_core::physical_gear as gear;
use btsim_core::smoke;
use common::*;
use btsim_core::fasthash::{HashMap};
use std::collections::{BTreeSet};

fn item_id(b: &btsim_core::battle::Battle, u: usize, addr: &str) -> usize {
    b.units[u].items.iter().position(|e| e.addr.as_deref() == Some(addr)).unwrap_or_else(|| panic!("no item {}", addr))
}

fn cover(a: &A) -> Cover {
    match a {
        A::Bool(false) => Cover::No,
        A::Bool(true) => Cover::Partial,
        A::Str(s) if s == "kick" => Cover::Kick,
        o => panic!("{:?}", o),
    }
}

fn dt(a: &A) -> DamageType {
    DamageType::from_name(a.member())
}

fn opt_int(a: &A) -> Option<i64> {
    if a.is_null() { None } else { Some(a.int()) }
}

#[test]
fn attack_parts_match_python() {
    let taps = load_taps("attack");
    assert!(taps.len() > 1000);
    let mut seen = BTreeSet::new();
    for rec in &taps {
        let f = rec["fn"].as_str().unwrap();
        if f == "smoke.add" || f == "smoke.end_phase" {
            continue; // they change the board, which a tap does not carry back; covered by whole battles
        }
        seen.insert(f.to_string());
        let (mut b, names) = make_battle(rec);
        let args: Vec<A> = rec["args"].as_array().unwrap().iter().map(decode).collect();
        let kw: HashMap<String, A> = rec["kwargs"].as_object().unwrap().iter().map(|(k, v)| (k.clone(), decode(v))).collect();
        let get = |i: usize, name: &str| -> Option<A> { args.get(i).cloned().or_else(|| kw.get(name).cloned()) };
        let ret = decode(&rec["ret"]);
        let uidx = |a: &A| unit_of(&names, a.unit());
        let items = |b: &btsim_core::battle::Battle, u: usize, a: &A| -> Vec<usize> {
            let mut v: Vec<usize> = a.list().iter().map(|x| match x { A::Item { addr, .. } => item_id(b, u, addr), o => panic!("{:?}", o) }).collect();
            v.sort();
            v
        };
        match f {
            "attack_resolution.total_hp" => assert_eq!(ar::total_hp(&b.units[uidx(&args[0])]).py_str(), ret.num().py_str()),
            "attack_resolution._target_tmm" => assert_eq!(ar::target_tmm(&b.units[uidx(&args[0])]), ret.int()),
            "attack_resolution.sensor_modifier" => assert_eq!(ar::sensor_modifier(&b.units[uidx(&args[0])]), opt_int(&ret)),
            "attack_resolution.has_targeting_computer" => assert_eq!(ar::has_targeting_computer(&b.units[uidx(&args[0])]), ret.bool()),
            "attack_resolution.prone_target_modifier" => assert_eq!(ar::prone_target_modifier(&b.units[uidx(&args[0])], args[1].int()), ret.int()),
            "attack_resolution.has_heat_dissipating_armor" => assert_eq!(ar::has_heat_dissipating_armor(&b.units[uidx(&args[0])]), ret.bool()),
            "attack_resolution.prone_fire" => {
                let u = uidx(&args[0]);
                let got = ar::prone_fire(&mut b, u);
                match (&got, &ret) {
                    (None, A::Null) => {}
                    (Some((m, set)), A::Tuple(w)) => {
                        assert_eq!(*m, w[0].int());
                        let mut g: Vec<usize> = set.iter().copied().collect();
                        g.sort();
                        assert_eq!(g, items(&b, u, &w[1]));
                    }
                    o => panic!("{:?}", o),
                }
            }
            "attack_resolution.firing_conditions" => {
                let u = uidx(&args[0]);
                let got = ar::firing_conditions(&mut b, u);
                match (&got, &ret) {
                    (None, A::Null) => {}
                    (Some((m, set, note)), A::Tuple(w)) => {
                        assert_eq!((*m, note.as_str()), (w[0].int(), w[2].str()));
                        let mut g: Vec<usize> = set.iter().copied().collect();
                        g.sort();
                        assert_eq!(g, items(&b, u, &w[1]));
                    }
                    o => panic!("{:?}", o),
                }
            }
            "attack_resolution.shielded_weapon_ids" => {
                let u = uidx(&args[0]);
                let mut g: Vec<usize> = ar::shielded_weapon_ids(&b.units[u]).into_iter().collect();
                g.sort();
                assert_eq!(g, items(&b, u, &ret));
            }
            "attack_resolution._heat_armor_damage" | "attack_resolution._protected" => {
                // not public: exercised through resolve_hit
                continue;
            }
            "attack_resolution._resolve_hit" => {
                let u = uidx(&args[0]);
                let tag = get(4, "tag").map(|a| a.str().to_string()).unwrap_or_default();
                let reroll = get(5, "reroll_legs").map(|a| a.bool()).unwrap_or(false);
                let cv = get(6, "cover").map(|a| cover(&a)).unwrap_or(Cover::No);
                let hw = get(7, "heat_weapon").map(|a| a.bool()).unwrap_or(false);
                let got = ar::resolve_hit(&mut b, u, args[1].int(), dt(&args[2]), args[3].str(), &tag, reroll, cv, hw);
                assert_eq!(got, if ret.is_null() { None } else { Some(ret.str().to_string()) });
            }
            "attack_resolution._apply_groups" => {
                let u = uidx(&args[0]);
                let label = get(6, "label").map(|a| a.str().to_string()).unwrap_or_default();
                ar::apply_groups(&mut b, u, args[1].int(), args[2].int(), dt(&args[3]), args[4].str(), cover(&args[5]), &label);
            }
            "attack_resolution._resolve_area" => {
                let u = uidx(&args[0]);
                ar::resolve_area(&mut b, u, args[1].int(), args[2].str(), cover(&args[3]));
            }
            "attack_resolution._tac_check" => {
                let u = uidx(&args[0]);
                let destroyed = get(4, "location_destroyed").unwrap().bool();
                ar::tac_check(&mut b, u, args[1].str(), args[2].str(), dt(&args[3]), destroyed);
            }
            "attack_resolution._target_heat" => {
                let t = uidx(&args[0]);
                let (au, w) = match &args[1] { A::Item { unit, addr } => { let a = unit_of(&names, unit); (a, item_id(&b, a, addr)) } o => panic!("{:?}", o) };
                ar::target_heat(&mut b, t, au, w);
            }
            "physical_gear.declare_raise" => {
                let u = uidx(&args[0]);
                gear::declare_raise(&mut b, u, args[1].str());
            }
            "physical_gear.lower" => gear::lower(&mut b.units[uidx(&args[0])]),
            "physical_gear.raised_blocks" => {
                let u = uidx(&args[0]);
                let _ = gear::raised_blocks(&b.units[u]);
            }
            "physical_gear.covered" => {
                let u = uidx(&args[0]);
                let _ = gear::covered(&b.units[u], args[1].str());
            }
            "physical_gear.shield_absorb" => {
                let u = uidx(&args[0]);
                assert_eq!(gear::shield_absorb(&mut b, u, args[1].str(), args[2].int(), args[3].str()), ret.int());
            }
            "physical_gear.shield_bash" => assert_eq!(gear::shield_bash(&b.units[uidx(&args[0])], args[1].str()), ret.int()),
            "physical_gear.talon_legs" => {
                let got = gear::talon_legs(&b.units[uidx(&args[0])]);
                assert_eq!(got, ret.list().iter().map(|x| x.str().to_string()).collect::<Vec<_>>());
            }
            "physical_gear.dfa_talons" => assert_eq!(gear::dfa_talons(&b.units[uidx(&args[0])]), ret.bool()),
            "physical_gear.spike_reduce" => {
                let u = uidx(&args[0]);
                let label = get(3, "label").map(|a| a.str().to_string()).unwrap_or_default();
                let (d, s) = gear::spike_reduce(&mut b, u, args[1].str(), args[2].int(), &label);
                assert_eq!((d, s), (ret.list()[0].int(), ret.list()[1].bool()));
            }
            "physical_gear.spike_retaliation" => {
                let u = uidx(&args[0]);
                let locs: Vec<String> = args[1].list().iter().map(|x| x.str().to_string()).collect();
                let l: Vec<&str> = locs.iter().map(|s| s.as_str()).collect();
                gear::spike_retaliation(&mut b, u, &l);
            }
            "physical_gear.spike_wear" => {
                let u = uidx(&args[0]);
                gear::spike_wear(&mut b, u, args[1].str());
            }
            "physical_gear.lance_ap_check" => {
                let u = uidx(&args[0]);
                gear::lance_ap_check(&mut b, u, args[1].str(), args[2].int(), args[3].str());
            }
            "physical_gear.use_spikes_in_charge" => {
                let u = uidx(&args[0]);
                assert_eq!(gear::use_spikes_in_charge(&mut b, u), ret.bool());
            }
            "physical_gear.snapshot" => {
                let (a, s) = gear::snapshot(&b.units[uidx(&args[0])], args[1].str());
                assert_eq!((a.py_str(), s.py_str()), (ret.list()[0].num().py_str(), ret.list()[1].num().py_str()));
            }
            "physical_gear.armor_only" => {
                let u = uidx(&args[0]);
                let bf = args[2].list();
                assert_eq!(gear::armor_only(&b.units[u], args[1].str(), (bf[0].num(), bf[1].num())), ret.bool());
            }
            "smoke.probe" => {
                let got = smoke::probe(&b.units[uidx(&args[0])]);
                match (&got, &ret) {
                    (None, A::Null) => {}
                    (Some((r, bh)), A::Tuple(w)) => assert_eq!((*r, *bh), (w[0].int(), w[1].bool())),
                    o => panic!("{:?}", o),
                }
            }
            "physical._location" => {
                let u = unit_of(&names, args[2].unit());
                assert_eq!(btsim_core::physical::location(&mut b, args[0].str(), args[1].str(), u), ret.str());
            }
            other => panic!("{}", other),
        }
        check_after(rec, &b, &names, f);
    }
    eprintln!("attack taps: {} calls, {:?}", taps.len(), seen);
}
