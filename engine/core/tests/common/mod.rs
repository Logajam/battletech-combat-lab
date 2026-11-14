//! Shared by the function-level tests (tap_*.rs): rebuild a recorded call's Battle, decode its arguments, compare the
//! state, the dice used, the log and the stub warnings. Fixtures: `python tools/port_tap.py GROUP`.
#![allow(dead_code)]
use btsim_core::fasthash::HashMap;
use std::fs;
use std::path::PathBuf;

use btsim_core::battle::{Battle, TapeDice};
use btsim_core::board_parser::Board;
use btsim_core::config::Config;
use btsim_core::mech_state::Mech;
use btsim_core::pyfmt::Num;
use btsim_core::fasthash::IndexMap;
use serde_json::Value;

pub fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../fixtures")
}

pub fn load_taps(group: &str) -> Vec<Value> {
    let p = root().join("taps").join(format!("{}.json", group));
    let text = fs::read_to_string(&p).unwrap_or_else(|_| panic!("{} missing - run `python tools/port_tap.py {}`", p.display(), group));
    serde_json::from_str(&text).unwrap()
}

/// A decoded rt-encoded argument or result (tools/port_record.rt_encode).
#[derive(Clone, Debug, PartialEq)]
pub enum A {
    Null,
    Bool(bool),
    Int(i64),
    Float(f64),
    Str(String),
    Unit(String),
    Item { unit: String, addr: String },
    Tuple(Vec<A>),
    List(Vec<A>),
    Fs(Vec<A>),
    Enum(String, String),
    Nt(String, Vec<(String, A)>),
    Dict(Vec<(A, A)>),
    Map(Vec<(String, A)>),
}

pub fn decode(v: &Value) -> A {
    match v {
        Value::Null => A::Null,
        Value::Bool(b) => A::Bool(*b),
        Value::Number(n) => {
            if n.is_i64() {
                A::Int(n.as_i64().unwrap())
            } else {
                A::Float(n.as_f64().unwrap())
            }
        }
        Value::String(s) => A::Str(s.clone()),
        Value::Array(a) => A::List(a.iter().map(decode).collect()),
        Value::Object(o) => {
            if let Some(n) = o.get("_unit") {
                A::Unit(n.as_str().unwrap().to_string())
            } else if let Some(a) = o.get("_item") {
                A::Item { unit: o["of"].as_str().unwrap().to_string(), addr: a.as_str().unwrap().to_string() }
            } else if let Some(t) = o.get("_t") {
                A::Tuple(t.as_array().unwrap().iter().map(decode).collect())
            } else if let Some(t) = o.get("_fs") {
                A::Fs(t.as_array().unwrap().iter().map(decode).collect())
            } else if let Some(e) = o.get("_enum") {
                let (c, m) = e.as_str().unwrap().split_once('.').unwrap();
                A::Enum(c.to_string(), m.to_string())
            } else if let Some(n) = o.get("_nt") {
                A::Nt(n.as_str().unwrap().to_string(), o.iter().filter(|(k, _)| *k != "_nt").map(|(k, x)| (k.clone(), decode(x))).collect())
            } else if let Some(d) = o.get("_d") {
                A::Dict(d.as_array().unwrap().iter().map(|p| (decode(&p[0]), decode(&p[1]))).collect())
            } else {
                A::Map(o.iter().map(|(k, x)| (k.clone(), decode(x))).collect())
            }
        }
    }
}

impl A {
    pub fn num(&self) -> Num {
        match self {
            A::Int(i) => Num::I(*i),
            A::Float(f) => Num::F(*f),
            A::Bool(b) => Num::I(*b as i64),
            other => panic!("not a number: {:?}", other),
        }
    }
    pub fn int(&self) -> i64 {
        match self {
            A::Int(i) => *i,
            other => panic!("not an int: {:?}", other),
        }
    }
    pub fn str(&self) -> &str {
        match self {
            A::Str(s) => s,
            other => panic!("not a str: {:?}", other),
        }
    }
    pub fn bool(&self) -> bool {
        match self {
            A::Bool(b) => *b,
            other => panic!("not a bool: {:?}", other),
        }
    }
    pub fn is_null(&self) -> bool {
        matches!(self, A::Null)
    }
    pub fn unit(&self) -> &str {
        match self {
            A::Unit(n) => n,
            other => panic!("not a unit: {:?}", other),
        }
    }
    pub fn member(&self) -> &str {
        match self {
            A::Enum(_, m) => m,
            other => panic!("not an enum: {:?}", other),
        }
    }
    pub fn list(&self) -> &Vec<A> {
        match self {
            A::List(l) | A::Tuple(l) | A::Fs(l) => l,
            other => panic!("not a list: {:?}", other),
        }
    }
}

thread_local! {
    static CONFIGS: std::cell::RefCell<HashMap<String, Config>> = std::cell::RefCell::new(HashMap::default());
    static BOARDS: std::cell::RefCell<HashMap<String, Value>> = std::cell::RefCell::new(HashMap::default());
}

pub fn fixture_config(fixture: &str) -> Config {
    CONFIGS.with(|c| {
        c.borrow_mut()
            .entry(fixture.to_string())
            .or_insert_with(|| {
                // the frozen Python answer key fires a unit's weapons in its own order (attack_resolution::finish_declaration)
                let mut c = Config::from_json(&serde_json::from_str(&fs::read_to_string(root().join(fixture).join("config.json")).unwrap()).unwrap());
                c.set("_FIRE_ORDER_LISTED", serde_json::Value::Bool(true));
                c
            })
            .clone()
    })
}

pub fn fixture_board(fixture: &str) -> Board {
    BOARDS.with(|b| {
        let v = b
            .borrow_mut()
            .entry(fixture.to_string())
            .or_insert_with(|| serde_json::from_str(&fs::read_to_string(root().join(fixture).join("board.json")).unwrap()).unwrap())
            .clone();
        Board::from_json(&v)
    })
}

/// The Battle a recorded call ran in: its units (as they stood before), the fixture's board and config, and a dice
/// tape of exactly the draws the call made. Also the unit names in roster order.
pub fn make_battle(rec: &Value) -> (Battle, Vec<String>) {
    let fixture = rec["fixture"].as_str().unwrap();
    let units = rec["units"].as_object().unwrap();
    let names: Vec<String> = rec["roster"].as_array().unwrap().iter().map(|n| n.as_str().unwrap().to_string()).collect();
    let idx = |n: &str| names.iter().position(|x| x == n).unwrap();
    // the whole roster, in battle order; units the call did not touch are placeholders
    let mechs: Vec<Mech> = names
        .iter()
        .map(|n| match units.get(n) {
            Some(d) => Mech::from_json(d, &idx),
            None => Mech::new("biped"),
        })
        .collect();
    let b = Battle::new(fixture_config(fixture), fixture_board(fixture), mechs, Box::new(TapeDice::from_json(&rec["dice"])));
    (b, names)
}

pub fn unit_of(names: &[String], n: &str) -> usize {
    names.iter().position(|x| x == n).unwrap_or_else(|| panic!("unit {} not in the call", n))
}

/// path of the first difference between two JSON values (values cut short)
pub fn first_diff(a: &Value, b: &Value, path: &str) -> Option<String> {
    match (a, b) {
        (Value::Object(x), Value::Object(y)) => {
            for (k, v) in x {
                match y.get(k) {
                    None => return Some(format!("{}/{}: Rust has it, Python not", path, k)),
                    Some(w) => {
                        if let Some(d) = first_diff(v, w, &format!("{}/{}", path, k)) {
                            return Some(d);
                        }
                    }
                }
            }
            for k in y.keys() {
                if !x.contains_key(k) {
                    return Some(format!("{}/{}: Python has it, Rust not", path, k));
                }
            }
            None
        }
        (Value::Array(x), Value::Array(y)) => {
            for (i, (v, w)) in x.iter().zip(y).enumerate() {
                if let Some(d) = first_diff(v, w, &format!("{}[{}]", path, i)) {
                    return Some(d);
                }
            }
            if x.len() != y.len() {
                return Some(format!("{} length {} v {}", path, x.len(), y.len()));
            }
            None
        }
        _ if a == b => None,
        _ => Some(format!("{}: rust {} python {}", path, a.to_string().chars().take(100).collect::<String>(), b.to_string().chars().take(100).collect::<String>())),
    }
}

/// After the call: every unit's state, the dice used, the log lines and the stub warnings must be the Python's.
pub fn check_after(rec: &Value, b: &Battle, names: &[String], what: &str) {
    let name_of = |i: usize| names.get(i).cloned().unwrap_or_default();
    for (i, n) in names.iter().enumerate() {
        if rec["after"].get(n).is_none() {
            continue;
        }
        let got = b.units[i].to_json(&name_of);
        if let Some(d) = first_diff(&got, &rec["after"][n], "") {
            panic!("{} [{}] unit {}: {}", what, rec["fixture"], n, d);
        }
    }
    assert_eq!(b.dice.borrow().used(), rec["dice"].as_array().unwrap().len(), "{} [{}]: dice used", what, rec["fixture"]);
    let want_log: Vec<String> = rec["log"].as_array().unwrap().iter().map(|x| x.as_str().unwrap().to_string()).collect();
    assert_eq!(b.log.lines, want_log, "{} [{}]: log", what, rec["fixture"]);
    let want_err: Vec<String> = rec["stubs"].as_array().unwrap().iter().map(|s| format!("STUB: {} - {}", s[0].as_str().unwrap(), s[1].as_str().unwrap())).collect();
    assert_eq!(b.log.stderr, want_err, "{} [{}]: stub warnings", what, rec["fixture"]);
}

pub fn _unused(_: IndexMap<String, i64>) {}
