// Translated from INTEGRATION__config.py (session 22): the settings.
//! One `Config`, loaded from the fixture's config.json (every UPPERCASE name of the Python, text kept), owned by the
//! battle. No statics (RUST_PORT trap 8). Settings are read by name through typed getters; hot ones get cached typed
//! fields in stage 9.

use indexmap::IndexMap;
use serde_json::Value;

#[derive(Clone, Debug, Default)]
pub struct Config {
    pub values: IndexMap<String, Value>,
}

impl Config {
    pub fn from_json(v: &Value) -> Config {
        Config { values: v.as_object().unwrap().iter().map(|(k, v)| (k.clone(), v.clone())).collect() }
    }
    pub fn get(&self, name: &str) -> &Value {
        self.values.get(name).unwrap_or_else(|| panic!("config has no setting {}", name))
    }
    pub fn has(&self, name: &str) -> bool {
        self.values.contains_key(name)
    }
    pub fn b(&self, name: &str) -> bool {
        self.get(name).as_bool().unwrap_or_else(|| panic!("config {} is not a bool", name))
    }
    pub fn i(&self, name: &str) -> i64 {
        self.get(name).as_i64().unwrap_or_else(|| panic!("config {} is not an int", name))
    }
    pub fn f(&self, name: &str) -> f64 {
        self.get(name).as_f64().unwrap_or_else(|| panic!("config {} is not a number", name))
    }
    pub fn s(&self, name: &str) -> &str {
        self.get(name).as_str().unwrap_or_else(|| panic!("config {} is not a string", name))
    }
    pub fn set(&mut self, name: &str, v: Value) {
        self.values.insert(name.to_string(), v);
    }
}
