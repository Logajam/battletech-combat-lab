//! arcs against the Python's own calls (python tools/port_tap.py arcs).
mod common;
use btsim_core::arcs::*;
use btsim_core::mech_state::{ArcAction, Turret};
use common::*;
use std::collections::BTreeSet;

fn field(a: &A, k: &str) -> A {
    match a {
        A::Nt(_, fs) => fs.iter().find(|(n, _)| n == k).unwrap_or_else(|| panic!("no field {}", k)).1.clone(),
        o => panic!("not a namedtuple: {:?}", o),
    }
}

fn action(a: &A) -> ArcAction {
    let t = field(a, "turret");
    ArcAction { twist: field(a, "twist").int(), flip: field(a, "flip").bool(), turret: if t.is_null() { None } else { Some(Turret::Offset(t.int())) } }
}

fn same_action(got: &ArcAction, want: &A) -> bool {
    *got == action(want)
}

fn tuple_pair(a: &A) -> (i64, i64) {
    let l = a.list();
    (l[0].int(), l[1].int())
}

#[test]
fn arcs_match_python() {
    let taps = load_taps("arcs");
    assert!(taps.len() > 1000);
    for rec in &taps {
        let f = rec["fn"].as_str().unwrap();
        let (mut b, names) = make_battle(rec);
        let args: Vec<A> = rec["args"].as_array().unwrap().iter().map(decode).collect();
        let ret = decode(&rec["ret"]);
        match f {
            "arcs.arcs_between" => {
                let got = arcs_between(tuple_pair(&args[0]), tuple_pair(&args[1]));
                let want: Vec<i64> = ret.list().iter().map(|x| x.int()).collect();
                assert_eq!(got.to_vec(), want, "{:?}", args);
            }
            "arcs.key_for" => {
                let arcs: Vec<i64> = args[0].list().iter().map(|x| x.int()).collect();
                let arr = [arcs[0], arcs[1], arcs[2], arcs[3], arcs[4], arcs[5]];
                let legs: Vec<(String, i64)> = args[3].list().iter().map(|t| (t.list()[0].str().to_string(), t.list()[1].int())).collect();
                let k = key_for(&arr, args[1].int(), &action(&args[2]), &legs);
                let want_legs: BTreeSet<String> = match field(&ret, "legs_forward") { A::Fs(v) => v.iter().map(|x| x.str().to_string()).collect(), o => panic!("{:?}", o) };
                let tf = field(&ret, "turret_forward");
                assert_eq!((k.torso_arc, k.legs_forward, k.flip, k.turret_forward), (field(&ret, "torso_arc").int(), want_legs, field(&ret, "flip").bool(), if tf.is_null() { None } else { Some(tf.bool()) }));
            }
            _ => {
                let u = unit_of(&names, args[0].unit());
                match f {
                    "arcs.has_quad_turret" => assert_eq!(has_quad_turret(&b.units[u]), ret.bool()),
                    "arcs.twist_offsets" => assert_eq!(twist_offsets(&b.units[u]), ret.list().iter().map(|x| x.int()).collect::<Vec<_>>()),
                    "arcs.can_flip_arms" => assert_eq!(can_flip_arms(&b.units[u]), ret.bool()),
                    "arcs.arc_options" => {
                        let phase = args.get(1).map(|a| a.str().to_string()).or_else(|| rec["kwargs"].get("phase").map(|p| p.as_str().unwrap().to_string())).unwrap_or("ranged".into());
                        let got = arc_options(&b.units[u], &phase);
                        assert_eq!(got.len(), ret.list().len());
                        for (g, w) in got.iter().zip(ret.list()) {
                            assert!(same_action(g, w), "{:?} v {:?}", g, w);
                        }
                    }
                    "arcs.mech_turrets" => {
                        let got = mech_turrets(&b.units[u]);
                        let want: Vec<(String, String)> = match &ret { A::Map(m) => m.iter().map(|(k, v)| (k.clone(), v.str().to_string())).collect(), o => panic!("{:?}", o) };
                        assert_eq!(got.iter().map(|(k, v)| (k.clone(), v.to_string())).collect::<Vec<_>>(), want);
                    }
                    "arcs.leg_offsets" => {
                        let got = leg_offsets(&b.units[u]);
                        let want: Vec<(String, i64)> = ret.list().iter().map(|t| (t.list()[0].str().to_string(), t.list()[1].int())).collect();
                        assert_eq!(got, want);
                    }
                    "arcs.current_action" => assert!(same_action(&current_action(&b.units[u]), &ret)),
                    "arcs.declare" => declare(&mut b.units[u], action(&args[1])),
                    "arcs.end_turn" => end_turn(&mut b.units[u]),
                    "arcs.turret_locked" => assert_eq!(turret_locked(&b.units[u]), ret.bool()),
                    "arcs.mech_turret_locked" => assert_eq!(mech_turret_locked(&b.units[u], args[1].str()), ret.bool()),
                    other => panic!("{}", other),
                }
            }
        }
        check_after(rec, &b, &names, f);
    }
}
