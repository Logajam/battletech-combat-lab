//! heat and electronics against the Python's own calls (python tools/port_tap.py heat / electronics).
mod common;
use btsim_core::electronics as el;
use btsim_core::heat::*;
use common::*;
use std::collections::BTreeSet;

fn item_id(b: &btsim_core::battle::Battle, u: usize, addr: &str) -> usize {
    b.units[u].items.iter().position(|e| e.addr.as_deref() == Some(addr)).unwrap_or_else(|| panic!("no item {}", addr))
}

fn items(b: &btsim_core::battle::Battle, a: &A) -> Vec<usize> {
    a.list().iter().map(|x| match x { A::Item { unit, addr } => item_id(b, b.unit_index(unit), addr), o => panic!("{:?}", o) }).collect()
}

fn arg<'a>(args: &'a [A], kw: &'a std::collections::HashMap<String, A>, i: usize, name: &str) -> Option<&'a A> {
    args.get(i).or_else(|| kw.get(name))
}

#[test]
fn heat_matches_python() {
    let taps = load_taps("heat");
    assert!(taps.len() > 1000);
    let mut seen = BTreeSet::new();
    for rec in &taps {
        let f = rec["fn"].as_str().unwrap();
        seen.insert(f.to_string());
        let (mut b, names) = make_battle(rec);
        b.piloting = rec["piloting"].as_i64().unwrap();
        let args: Vec<A> = rec["args"].as_array().unwrap().iter().map(decode).collect();
        let kw: std::collections::HashMap<String, A> = rec["kwargs"].as_object().unwrap().iter().map(|(k, v)| (k.clone(), decode(v))).collect();
        let ret = decode(&rec["ret"]);
        let u = unit_of(&names, args[0].unit());
        match f {
            "heat.movement_heat" => assert_eq!(movement_heat(&b.units[u], args[1].str(), args[2].int()), ret.int()),
            "heat.engine_heat" => assert_eq!(engine_heat(&b.units[u]), ret.int()),
            "heat.weapon_fire_surcharge" => assert_eq!(weapon_fire_surcharge(&b.units[u]), ret.int()),
            "heat.planned_cooling" => assert_eq!(planned_cooling(&mut b, u), ret.int()),
            "heat.other_heat" => assert_eq!(other_heat(&mut b, u), ret.int()),
            "heat.weapon_heat_budget" => assert_eq!(weapon_heat_budget(&mut b, u, args[1].int()), ret.int()),
            "heat._extra_cooling" => {
                let (e, how) = extra_cooling(&mut b, u, args[1].int());
                assert_eq!((e, how), (ret.list()[0].int(), ret.list()[1].str()));
            }
            "heat._check_shutdown" => check_shutdown(&mut b, u),
            "heat._life_support_hits" => life_support_hits(&mut b, u),
            "heat.apply_heat_effects" => apply_heat_effects(&mut b, u),
            "heat.resolve_heat_phase" => resolve_heat_phase(&mut b, u, args[1].int()),
            "heat.choose_heat_sink_deactivation" => {
                let nt = arg(&args, &kw, 1, "next_turn").filter(|a| !a.is_null()).map(|a| a.int());
                choose_heat_sink_deactivation(&mut b, u, nt)
            }
            "heat.live_ammo_bins" => {
                let inf = kw.get("inferno").map(|a| a.bool()).or_else(|| args.get(1).map(|a| a.bool()));
                let got = live_ammo_bins(&b.units[u], inf);
                assert_eq!(got.len(), ret.list().len());
                for ((loc, id), w) in got.iter().zip(ret.list()) {
                    let w = w.list();
                    assert_eq!(loc, w[0].str());
                    assert_eq!(*id, items(&b, &A::List(vec![w[1].clone()]))[0]);
                }
            }
            "heat._check_ammo_explosion" => {
                let inf = arg(&args, &kw, 1, "inferno").unwrap().bool();
                assert_eq!(check_ammo_explosion(&mut b, u, inf), ret.bool());
            }
            "heat.max_weapon_heat" => assert_eq!(max_weapon_heat(&mut b, u), ret.int()),
            "heat.max_movement_heat" => assert_eq!(max_movement_heat(&b.units[u]), ret.int()),
            "heat._try_restart" => try_restart(&mut b, u),
            "heat.choose_exploding_bin" => {
                let bins: Vec<(String, usize)> = args[1].list().iter().map(|t| { let t = t.list(); (t[0].str().to_string(), items(&b, &A::List(vec![t[1].clone()]))[0]) }).collect();
                let (loc, id) = choose_exploding_bin(&mut b, u, &bins);
                let w = ret.list();
                assert_eq!((loc.as_str(), id), (w[0].str(), items(&b, &A::List(vec![w[1].clone()]))[0]));
            }
            other => panic!("{}", other),
        }
        check_after(rec, &b, &names, f);
    }
    eprintln!("heat taps: {} calls, {:?}", taps.len(), seen);
}

#[test]
fn electronics_matches_python() {
    let taps = load_taps("electronics");
    assert!(taps.len() > 1000);
    for rec in &taps {
        let f = rec["fn"].as_str().unwrap();
        let (mut b, names) = make_battle(rec);
        let args: Vec<A> = rec["args"].as_array().unwrap().iter().map(decode).collect();
        let ret = decode(&rec["ret"]);
        let u = unit_of(&names, args[0].unit());
        let item = |a: &A| match a { A::Item { unit, addr } => item_id(&b, unit_of(&names, unit), addr), o => panic!("{:?}", o) };
        match f {
            "electronics.artemis_kind" => assert_eq!(el::artemis_kind(&b.units[u], item(&args[1])), if ret.is_null() { None } else { Some(ret.int()) }),
            "electronics.live_ecm" => assert_eq!(el::live_ecm(&b.units[u]), items(&b, &ret)),
            "electronics.hostile_field" => assert_eq!(el::hostile_field(&b.units[u]), ret.bool()),
            "electronics.angel_field" => assert_eq!(el::angel_field(&b.units[u]), ret.bool()),
            "electronics.as_if_jammed" => assert_eq!(el::as_if_jammed(&b.units[u]), ret.bool()),
            "electronics.artemis_blocked" => assert_eq!(el::artemis_blocked(&b.units[u], &b.units[unit_of(&names, args[1].unit())]), ret.bool()),
            "electronics.narc_blocked" => assert_eq!(el::narc_blocked(&b.units[u]), ret.bool()),
            "electronics.homing_working" => assert_eq!(el::homing_working(&b.units[u], &b.units[unit_of(&names, args[1].unit())]), ret.bool()),
            "electronics.control_for" => {
                let t = unit_of(&names, args[2].unit());
                let w = item(&args[1]);
                let fc = el::control_for(&mut b, u, w, t, args[3].str());
                let want = match &ret { A::Nt(_, fs) => fs.clone(), o => panic!("{:?}", o) };
                let get = |k: &str| want.iter().find(|(n, _)| n == k).unwrap().1.clone();
                assert_eq!((fc.munition.as_str(), fc.tn, fc.cluster, fc.streak_lock, fc.note.as_str()), (get("munition").str(), get("tn").int(), get("cluster").int(), get("streak_lock").bool(), get("note").str()));
            }
            "electronics.activate_pods" => el::activate_pods(&mut b.units[u]),
            "electronics.attach_pod" => el::attach_pod(&mut b.units[u], args[1].str(), args[2].str()),
            "electronics.munitions" => {
                let got: std::collections::BTreeSet<String> = el::munitions(&b.units[u], item(&args[1])).into_iter().collect();
                let want: std::collections::BTreeSet<String> = ret.list().iter().map(|x| x.str().to_string()).collect();
                assert_eq!(got, want);
            }
            other => panic!("{}", other),
        }
        check_after(rec, &b, &names, f);
    }
}
