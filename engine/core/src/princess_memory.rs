// Translated from INTEGRATION__princess_memory.py: what Princess remembers - a heat map of where her team's units have
// stood (the anchor of mutual support) and her force's posture record. One map per TEAM; only Princess units add to it.
use crate::fasthash::IndexMap;

use crate::battle::{Battle, UnitId};
use crate::hex_geometry;
use crate::los::hex_distance;
use crate::mech_state::*;

const ACTIVITY_DECAY: i64 = -200;
const MAP_TRIM_THRESHOLD: f64 = 0.6;
const MAX_ENTRIES: usize = 100;
const MIN_WEIGHT: i64 = 0;

#[derive(Default)]
pub struct HeatMap {
    pub activity: IndexMap<String, i64>,
    pub last_known: IndexMap<UnitId, String>,
}

pub struct TeamMemory {
    pub heat: HeatMap,
    pub mean_distance_by_round: IndexMap<i64, f64>,
    pub posture: String,
    pub posture_round: Option<i64>,
}

impl Default for TeamMemory {
    fn default() -> Self {
        TeamMemory { heat: HeatMap::default(), mean_distance_by_round: IndexMap::default(), posture: "ATTACK".to_string(), posture_round: None }
    }
}

/// HeatMap.getTeamWeightAdjustment: max(BV - 100 x max(jump MP, walk MP), 1).
pub fn unit_weight(b: &mut Battle, u: UnitId) -> i64 {
    let bv = match b.princess.bv.get(&u) {
        Some(v) => *v,
        None => {
            let v = crate::battle_value::battle_value(b, u);
            b.princess.bv.insert(u, v);
            v
        }
    };
    let speed = compute_jump_mp(&b.units[u]).max(compute_walk_mp(&b.units[u]));
    (bv - 100 * speed).max(1)
}

fn trackable(b: &mut Battle, u: UnitId) -> bool {
    b.units[u].hex.is_some() && !b.is_destroyed(u)
}

pub fn team<'a>(b: &'a mut Battle, name: &str) -> &'a mut TeamMemory {
    b.princess.teams.entry(name.to_string()).or_default()
}

/// Princess.calculateMoveTurn: a Princess unit that moved credits its end hex.
pub fn unit_moved(b: &mut Battle, mech: UnitId, start_hex: Option<&str>) {
    if b.units[mech].bot != "princess" || b.units[mech].hex.is_none() {
        return;
    }
    let hex = b.units[mech].hex.clone().unwrap();
    if start_hex == Some(hex.as_str()) && b.units[mech].move_fc == 0 {
        return;
    }
    let w = unit_weight(b, mech);
    let t = b.units[mech].team.clone().unwrap_or_default();
    let heat = &mut team(b, &t).heat;
    *heat.activity.entry(hex.clone()).or_insert(0) += w;
    heat.last_known.insert(mech, hex);
}

/// Princess.endOfTurnProcessing -> updateFriendlyHeatMap, for each team that has a Princess unit.
pub fn end_of_turn(b: &mut Battle) {
    let n = b.units.len();
    let mut teams: Vec<String> = Vec::new();
    for u in 0..n {
        if b.units[u].bot == "princess" {
            let t = b.units[u].team.clone().unwrap_or_default();
            if !teams.contains(&t) {
                teams.push(t);
            }
        }
    }
    for name in teams {
        let mine: Vec<UnitId> = (0..n).filter(|u| b.units[*u].team.as_deref() == Some(name.as_str())).collect();
        // refresh_last_known: a unit that fell or was displaced is where it is now
        let known: Vec<UnitId> = mine.iter().copied().filter(|u| team(b, &name).heat.last_known.contains_key(u)).collect();
        for u in known {
            if trackable(b, u) {
                let h = b.units[u].hex.clone().unwrap();
                team(b, &name).heat.last_known.insert(u, h);
            }
        }
        // age: the activity map only
        let gone: Vec<UnitId> = mine.iter().copied().filter(|u| b.is_destroyed(*u)).collect();
        for u in gone {
            team(b, &name).heat.last_known.shift_remove(&u);
        }
        let mut held: crate::fasthash::HashSet<String> = crate::fasthash::HashSet::default();
        for u in &mine {
            let lk = team(b, &name).heat.last_known.get(u).cloned();
            if let Some(l) = lk {
                if trackable(b, *u) {
                    held.insert(l);
                }
            }
        }
        let heat = &mut team(b, &name).heat;
        let keys: Vec<String> = heat.activity.keys().cloned().collect();
        for label in keys {
            let mut weight = heat.activity[&label];
            if weight <= MIN_WEIGHT {
                continue;
            }
            if !held.contains(&label) {
                weight = weight.div_euclid(2).max(MIN_WEIGHT);
            } else {
                weight = (weight + ACTIVITY_DECAY).max(MIN_WEIGHT);
            }
            heat.activity.insert(label, weight);
        }
        heat.trim();
    }
}

impl HeatMap {
    fn trim(&mut self) {
        if !self.activity.is_empty() {
            let low = self.activity.values().filter(|w| **w <= MIN_WEIGHT).count();
            if low as f64 / self.activity.len() as f64 >= MAP_TRIM_THRESHOLD {
                self.activity = self.activity.iter().filter(|(_, w)| **w > MIN_WEIGHT).map(|(k, w)| (k.clone(), *w)).collect();
            }
        }
        while self.activity.len() > MAX_ENTRIES {
            let lowest = *self.activity.values().min().unwrap();
            self.activity = self.activity.iter().filter(|(_, w)| **w != lowest).map(|(k, w)| (k.clone(), *w)).collect();
        }
    }

    /// HeatMap.getHotSpotRating.
    fn rating(&self, label: &str) -> i64 {
        if self.activity.len() == 1 {
            return *self.activity.values().next().unwrap();
        }
        let here = hex_geometry::parse_hex_label(label).unwrap();
        let distances: Vec<(i64, i64)> = self.activity.iter().map(|(k, w)| (*w, hex_distance(here, hex_geometry::parse_hex_label(k).unwrap()))).collect();
        let longest = distances.iter().map(|d| d.1).max().unwrap();
        // Python: sum(...) of floats
        let total = crate::pyfmt::py_sum(distances.iter().map(|(w, d)| *w as f64 * (longest - d) as f64 / longest as f64));
        total.floor() as i64
    }

    /// HeatMap.getHotSpot(position, topOnly=true): of the hexes with the top rating, the nearest to `label` (the first
    /// listed on a tie); None while nothing is above 0.
    pub fn hot_spot(&self, label: &str) -> Option<String> {
        let live: Vec<&String> = self.activity.iter().filter(|(_, w)| **w > MIN_WEIGHT).map(|(k, _)| k).collect();
        if live.is_empty() {
            return None;
        }
        let ratings: Vec<i64> = live.iter().map(|k| self.rating(k)).collect();
        let top = *ratings.iter().max().unwrap();
        let here = hex_geometry::parse_hex_label(label).unwrap();
        let mut best: Option<(&String, i64)> = None;
        for (k, r) in live.iter().zip(&ratings) {
            if *r != top {
                continue;
            }
            let d = hex_distance(here, hex_geometry::parse_hex_label(k).unwrap());
            if best.map_or(true, |(_, bd)| d < bd) {
                best = Some((k, d));
            }
        }
        best.map(|(k, _)| k.clone())
    }
}

/// "0807" -> (7, 6): MegaMek's Coords (column, row), counted from 0.
pub fn label_to_cols_rows(label: &str) -> (i64, i64) {
    (label[..2].parse::<i64>().unwrap() - 1, label[2..].parse::<i64>().unwrap() - 1)
}

pub fn cols_rows_to_label(col: i64, row: i64) -> String {
    format!("{:02}{:02}", col + 1, row + 1)
}
