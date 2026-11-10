//! ammo against the Python's own calls (python tools/port_tap.py ammo).
mod common;
use btsim_core::ammo::*;
use common::*;
use std::collections::BTreeSet;

fn item_id(b: &btsim_core::battle::Battle, u: usize, addr: &str) -> usize {
    b.units[u].items.iter().position(|e| e.addr.as_deref() == Some(addr)).unwrap_or_else(|| panic!("no item {}", addr))
}

fn want_items(b: &btsim_core::battle::Battle, u: usize, a: &A) -> Vec<usize> {
    a.list().iter().map(|x| match x { A::Item { addr, .. } => item_id(b, u, addr), o => panic!("{:?}", o) }).collect()
}

#[test]
fn ammo_matches_python() {
    let taps = load_taps("ammo");
    assert!(taps.len() > 1000);
    let mut seen = BTreeSet::new();
    for rec in &taps {
        let f = rec["fn"].as_str().unwrap();
        seen.insert(f.to_string());
        let (mut b, names) = make_battle(rec);
        let args: Vec<A> = rec["args"].as_array().unwrap().iter().map(decode).collect();
        let kw: std::collections::HashMap<String, A> = rec["kwargs"].as_object().unwrap().iter().map(|(k, v)| (k.clone(), decode(v))).collect();
        let ret = decode(&rec["ret"]);
        let unit_item = |a: &A| match a { A::Item { unit, addr } => { let u = unit_of(&names, unit); (u, item_id(&b, u, addr)) } o => panic!("{:?}", o) };
        match f {
            "ammo.parse_bin" => {
                let got = parse_bin(&b, args[0].str());
                let w = ret.list();
                match (&got, &w[0]) {
                    (None, A::Null) => assert!(w[1].is_null() && w[2].is_null()),
                    (Some((e, m, k)), A::Map(ent)) => {
                        let cn = ent.iter().find(|(k, _)| k == "canonical_name").map(|(_, v)| v.str().to_string()).unwrap();
                        assert_eq!(e["canonical_name"].as_str().unwrap(), cn, "parse_bin {:?}", args);
                        assert_eq!((m.as_str(), k.as_str()), (w[1].str(), w[2].str()), "parse_bin {:?}", args);
                    }
                    other => panic!("parse_bin {:?}: {:?}", args, other),
                }
            }
            "ammo.damage_per_shot" => {
                let entry = &rec["args"][0];
                let want = if ret.is_null() { None } else { Some(ret.int()) };
                assert_eq!(if entry.is_null() { None } else { damage_per_shot(entry) }, want, "{:?}", rec["args"][0]);
            }
            "ammo.bins_for" => {
                let (u, w) = unit_item(&args[1]);
                let _ = &args[0];
                assert_eq!(bins_for(&b.units[u], w), want_items(&b, u, &ret));
            }
            "ammo.unavailable_weapons" => {
                let u = unit_of(&names, args[0].unit());
                let mut want = want_items(&b, u, &ret);
                want.sort();
                let mut got: Vec<usize> = unavailable_weapons(&b.units[u]).into_iter().collect();
                got.sort();
                assert_eq!(got, want);
            }
            "ammo.take" => {
                let u = unit_of(&names, args[0].unit());
                let (_, w) = unit_item(&args[1]);
                let get = |i: usize, n: &str| args.get(i).cloned().or_else(|| kw.get(n).cloned()).filter(|a| !a.is_null());
                let (m, k) = (get(2, "munition"), get(3, "kind"));
                let (note, mun) = take(&mut b, u, w, m.as_ref().map(|a| a.str()), k.as_ref().map(|a| a.str()));
                assert_eq!((note.as_str(), mun.as_str()), (ret.list()[0].str(), ret.list()[1].str()));
            }
            "ammo._update_explosion" => {
                let (u, w) = unit_item(&args[0]);
                update_explosion(&mut b.units[u].items[w]);
            }
            other => panic!("{}", other),
        }
        check_after(rec, &b, &names, f);
    }
    eprintln!("ammo taps: {} calls, {:?}", taps.len(), seen);
}
