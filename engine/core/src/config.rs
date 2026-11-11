// Translated from INTEGRATION__config.py (session 22): the settings.
//! One `Config`, loaded from the fixture's config.json (every UPPERCASE name of the Python, text kept), owned by the
//! battle. No statics (RUST_PORT trap 8). Settings are read by name through typed getters; hot ones get cached typed
//! fields in stage 9.

use crate::fasthash::IndexMap;
use serde_json::Value;

#[derive(Clone, Debug, Default)]
pub struct Config {
    pub values: IndexMap<String, Value>,
    /// CLUSTER_HITS_TABLE as numbers, (roll, shots) -> hits, read out of `values` on first use (speed only; `set`
    /// drops it)
    cluster: std::sync::OnceLock<crate::fasthash::HashMap<(i64, i64), i64>>,
}

impl Config {
    pub fn from_json(v: &Value) -> Config {
        Config { values: v.as_object().unwrap().iter().map(|(k, v)| (k.clone(), v.clone())).collect(), cluster: Default::default() }
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
        self.cluster = Default::default();
    }
    /// CLUSTER_HITS_TABLE[roll][shots], None when the table has no such row or column (or is not all numbers).
    pub fn cluster_hits(&self, roll: i64, shots: i64) -> Option<i64> {
        let table = self.cluster.get_or_init(|| {
            let mut out = crate::fasthash::HashMap::default();
            if let Some(rows) = self.values.get("CLUSTER_HITS_TABLE").and_then(|t| t.as_object()) {
                for (r_text, row) in rows {
                    for (c_text, v) in row.as_object().into_iter().flatten() {
                        // only keys the text lookup finds too ("7", never "07")
                        if let (Ok(r), Ok(c), Some(v)) = (r_text.parse::<i64>(), c_text.parse::<i64>(), v.as_i64()) {
                            if r.to_string() == *r_text && c.to_string() == *c_text {
                                out.insert((r, c), v);
                            }
                        }
                    }
                }
            }
            out
        });
        table.get(&(roll, shots)).copied()
    }
}
