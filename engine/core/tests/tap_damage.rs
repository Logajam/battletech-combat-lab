//! damage_resolution + hit_location against the Python's own calls (python tools/port_tap.py damage).
mod common;
use btsim_core::damage_resolution::*;
use btsim_core::equipment::Slot;
use btsim_core::hit_location::resolve_hit_location;
use btsim_core::mech_state::DamageType;
use common::*;

fn item_id(b: &btsim_core::battle::Battle, u: usize, addr: &str) -> usize {
    b.units[u].items.iter().position(|e| e.addr.as_deref() == Some(addr)).unwrap_or_else(|| panic!("no item {}", addr))
}

#[test]
fn damage_functions_match_python() {
    let taps = load_taps("damage");
    assert!(taps.len() > 1000);
    let mut seen = std::collections::BTreeSet::new();
    for rec in &taps {
        let f = rec["fn"].as_str().unwrap();
        seen.insert(f.to_string());
        let (mut b, names) = make_battle(rec);
        let args: Vec<A> = rec["args"].as_array().unwrap().iter().map(decode).collect();
        let kw: btsim_core::fasthash::HashMap<String, A> = rec["kwargs"].as_object().unwrap().iter().map(|(k, v)| (k.clone(), decode(v))).collect();
        let get = |i: usize, name: &str| -> Option<A> { args.get(i).cloned().or_else(|| kw.get(name).cloned()) };
        let ret = decode(&rec["ret"]);
        match f {
            "damage_resolution.apply_damage" => {
                let u = unit_of(&names, args[0].unit());
                let af = get(3, "armor_field").map(|a| a.str().to_string()).unwrap_or("armor".into());
                let dtp = get(4, "damage_type").map(|a| DamageType::from_name(a.member())).unwrap_or(DamageType::Ballistic);
                apply_damage(&mut b, u, args[1].str(), args[2].num(), &af, dtp);
            }
            "damage_resolution.check_critical" => {
                let u = unit_of(&names, args[0].unit());
                let destroyed = get(2, "location_destroyed").map(|a| a.bool()).unwrap_or(false);
                let modifier = get(3, "modifier").map(|a| a.int()).unwrap_or(0);
                check_critical(&mut b, u, args[1].str(), destroyed, modifier);
            }
            "damage_resolution.resolve_critical" => {
                let u = unit_of(&names, args[0].unit());
                resolve_critical(&mut b, u, args[1].str(), get(2, "explosive_only").unwrap().bool(), get(3, "idx").unwrap().int(), get(4, "total").unwrap().int());
            }
            "damage_resolution.resolve_slot_hit" => {
                let u = unit_of(&names, args[0].unit());
                let slot = match &args[3] {
                    A::Item { addr, .. } => Slot::Item(item_id(&b, u, addr)),
                    A::Str(s) => Slot::Name(s.clone()),
                    o => panic!("{:?}", o),
                };
                resolve_slot_hit(&mut b, u, args[1].str(), args[2].int() as usize, &slot, args[4].int(), args[5].int());
            }
            "damage_resolution.apply_explosion" => {
                let u = unit_of(&names, args[0].unit());
                let id = match &args[1] { A::Item { addr, .. } => item_id(&b, u, addr), o => panic!("{:?}", o) };
                apply_explosion(&mut b, u, id, args[2].str());
            }
            "damage_resolution.mark_all_crits_destroyed" => {
                let u = unit_of(&names, args[0].unit());
                mark_all_crits_destroyed(&mut b, u, args[1].str());
            }
            "damage_resolution.cluster_hits_count" => {
                assert_eq!(cluster_hits_count(&b, args[0].int(), args[1].int()).unwrap(), ret.int());
            }
            "hit_location.resolve_hit_location" => {
                let u = unit_of(&names, args[1].unit());
                assert_eq!(resolve_hit_location(&mut b, u, args[0].int(), args[2].str()), ret.str());
            }
            other => panic!("{}", other),
        }
        check_after(rec, &b, &names, f);
    }
    assert!(seen.len() >= 8, "{:?}", seen);
}
