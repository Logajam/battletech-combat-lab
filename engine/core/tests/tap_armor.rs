//! armor_rules against the Python's own calls in the fixture battles (python tools/port_tap.py armor).
mod common;
use btsim_core::armor_rules::*;
use btsim_core::mech_state::{ArmorType, DamageType, StructureType};
use common::*;

fn dt(a: &A) -> DamageType {
    DamageType::from_name(a.member())
}
fn at(a: &A) -> ArmorType {
    ArmorType::from_dump(&format!("ArmorType.{}", a.member()))
}

#[test]
fn armor_rules_match_python() {
    let taps = load_taps("armor");
    assert!(taps.len() > 1000);
    for rec in &taps {
        let fnname = rec["fn"].as_str().unwrap();
        let args: Vec<A> = rec["args"].as_array().unwrap().iter().map(decode).collect();
        let ret = decode(&rec["ret"]);
        match fnname {
            "armor_rules._reduce_attack_damage_for_armor" => {
                let got = reduce_attack_damage_for_armor(at(&args[0]), dt(&args[1]), args[2].num());
                assert_eq!(got.py_str(), ret.num().py_str(), "{} {:?}", fnname, args);
            }
            "armor_rules.effective_damage" => {
                let got = effective_damage(at(&args[0]), dt(&args[1]), args[2].num(), args[3].num());
                assert_eq!(got.py_str(), ret.num().py_str(), "{} {:?}", fnname, args);
            }
            "armor_rules._consume_armor" => {
                let (a, o) = consume_armor(at(&args[0]), dt(&args[1]), args[2].num(), args[3].num());
                let w = ret.list();
                assert_eq!((a.py_str(), o.py_str()), (w[0].num().py_str(), w[1].num().py_str()), "{} {:?}", fnname, args);
            }
            "armor_rules._consume_structure" => {
                let st = StructureType::from_dump(&format!("StructureType.{}", args[0].member()));
                let (a, o) = consume_structure(st, args[1].num(), args[2].num());
                let w = ret.list();
                assert_eq!((a.py_str(), o.py_str()), (w[0].num().py_str(), w[1].num().py_str()), "{} {:?}", fnname, args);
            }
            "armor_rules.crit_roll_modifier" => {
                let st = StructureType::from_dump(&format!("StructureType.{}", args[0].member()));
                let armor = rec["kwargs"].get("armor_type").map(|v| decode(v)).or_else(|| args.get(1).cloned());
                let armor = armor.filter(|a| !a.is_null()).map(|a| at(&a));
                let present = rec["kwargs"].get("armor_present").map(|v| decode(v).bool()).or_else(|| args.get(2).map(|a| a.bool())).unwrap_or(false);
                assert_eq!(crit_roll_modifier(st, armor, present), ret.int(), "{} {:?} {:?}", fnname, args, rec["kwargs"]);
            }
            other => panic!("{}", other),
        }
    }
}
