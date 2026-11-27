//! THE TIMELINE CONTROL (REC layer, INTEGRATION__TIMELINE_SYNC.md Section 4, INTEGRATION__ORDER_FORMAT.md "Branches by step").
//!
//! A game is its order list; the list may also hold DECLARATIVE `branch` events, which say where in the game's replay steps a new
//! timeline starts and what changes there. Unlike `reseed` (which sits at a question), a branch is addressed by STEP: the number of
//! replay steps (`history::History` marks: each unit's move, each attacker's resolved fire, each physical attack, the phase ends) the
//! battle has completed. That is what lets a branch start where nobody is asked anything (a bot's move):
//!
//! ```text
//! {"branch": {"after_step": 12, "reseed": "98765",
//!             "control": [{"team": "Blue", "by": "human" | "gladiator" | "princess"}],
//!             "meddle":  {"team": "Blue", "phase": "move" | "fire" | "phys", "unit": "Blue 1"}}}
//! ```
//!
//! * `reseed`: the dice start afresh from that seed once `after_step` steps are done (Daniel, 2026-11-19: a branch gets its own seed).
//! * `control`: from then on the team is that bot, or asks the person (the team's setting for the rest of the game).
//! * `meddle`: the team's NEXT decision in that phase is asked of the person whoever the team's owner is; after that unit's step the team
//!   goes back to its owner. With `unit` (a unit's label) only that unit's decisions are the person's: firing and physical attacks are all
//!   declared before any is resolved, so a cut at the start of the phase must name WHICH unit the person takes over. (Daniel, 2026-11-27: "That phase's choices are overwritten regardless of the original controller.")
//!
//! Everything is read from the list BEFORE the battle starts and applied by the step counter, so no position in the list matters and a
//! branch replays exactly. Recording changes nothing: a game with no branch event never touches any of this.
use std::collections::HashMap;

use serde_json::Value;

use crate::battle::Battle;
use crate::dice::PcgDice;

#[derive(Clone, Debug, Default)]
pub struct Branch {
    pub after_step: usize,
    pub reseed: Option<u64>,
    pub control: Vec<(String, String)>,
    pub meddle: Option<(String, String, Option<String>)>,
}

/// The branches of a list and where the battle is among them.
#[derive(Default, Debug)]
pub struct Control {
    /// replay steps completed so far (`on_mark` counts them)
    pub steps_done: usize,
    branches: Vec<Branch>,
    next: usize,
    /// team -> "human" or a bot name, set by a `control` entry
    team_by: HashMap<String, String>,
    /// (team, phase "move" | "fire" | "phys", unit label) waiting for its one decision
    meddle: Option<(String, String, Option<String>)>,
}

/// The `branch` events of an order list (in the order they stand), whatever their place in it.
pub fn branches_of(orders: &Value) -> Vec<Branch> {
    let mut out: Vec<Branch> = Vec::new();
    for e in orders["events"].as_array().into_iter().flatten() {
        let Some(br) = e.get("branch") else { continue };
        let num = |v: &Value| v.as_u64().or_else(|| v.as_str().and_then(|t| t.parse().ok()));
        let control = br["control"].as_array().into_iter().flatten().filter_map(|c| Some((c["team"].as_str()?.to_string(), c["by"].as_str()?.to_string()))).collect();
        let meddle = br["meddle"].as_object().and_then(|m| Some((m.get("team")?.as_str()?.to_string(), m.get("phase")?.as_str()?.to_string(), m.get("unit").and_then(|u| u.as_str()).map(String::from))));
        out.push(Branch { after_step: br["after_step"].as_u64().unwrap_or(0) as usize, reseed: num(&br["reseed"]), control, meddle });
    }
    out.sort_by_key(|b| b.after_step); // stable: branches at the same step keep their order
    out
}

impl Control {
    pub fn from_orders(orders: Option<&Value>) -> Control {
        Control { branches: orders.map(branches_of).unwrap_or_default(), ..Control::default() }
    }

    pub fn is_empty(&self) -> bool {
        self.branches.is_empty()
    }

    /// Apply every branch whose step has come (also called once before the battle starts, for `after_step` 0).
    pub fn apply_due(&mut self, b: &mut Battle) {
        while self.next < self.branches.len() && self.branches[self.next].after_step <= self.steps_done {
            let br = self.branches[self.next].clone();
            self.next += 1;
            if let Some(seed) = br.reseed {
                *b.dice.borrow_mut() = Box::new(PcgDice::new(seed));
            }
            for (team, by) in &br.control {
                self.team_by.insert(team.clone(), by.clone());
                self.give_team(b, team, by);
            }
            if let Some((team, phase, unit)) = br.meddle {
                // the team's units get a (default) entry among the person's choices, as a person's own units have (play_session)
                self.give_team(b, &team, "human");
                self.meddle = Some((team, phase, unit));
            }
        }
    }

    /// A team handed to a bot: its units' bot is that bot; handed to the person: each unit has an entry among the person's choices.
    fn give_team(&self, b: &mut Battle, team: &str, by: &str) {
        for u in 0..b.units.len() {
            if b.units[u].team.as_deref() != Some(team) {
                continue;
            }
            if by == "human" {
                let n = b.units[u].side_name.clone().unwrap_or_default();
                b.player.unit_mut(&n);
            } else {
                b.units[u].bot = by.to_string();
            }
        }
    }

    /// One replay step was marked. `info` is the step's `Battle::step_info` ({"k","unit","target"}).
    pub fn on_mark(&mut self, b: &mut Battle, info: &Option<Value>) {
        self.steps_done += 1;
        // the meddle is spent when the step of that phase by one of that team's units has been made
        if let (Some((team, phase, only)), Some(i)) = (&self.meddle, info) {
            let k = i["k"].as_str().unwrap_or("");
            let who = i["unit"].as_u64().and_then(|u| b.units.get(u as usize));
            let team_ok = who.and_then(|m| m.team.as_deref()) == Some(team.as_str());
            let unit_ok = only.as_ref().is_none_or(|l| who.and_then(|m| m.side_name.as_deref()) == Some(l.as_str()));
            if k == phase && team_ok && unit_ok {
                self.meddle = None;
            }
        }
        self.apply_due(b);
    }

    /// The unit a meddle in `phase` ("fire" / "phys") names: its declaration is made FIRST of the phase, so the person meets it at once
    /// instead of after their own units (Daniel, 2026-11-27: "the next state I saw was my own unit's turn to fire"). None: no such meddle.
    pub fn meddle_first(&self, b: &Battle, phase: &str) -> Option<usize> {
        let (_, p, only) = self.meddle.as_ref()?;
        let label = only.as_deref().filter(|_| p == phase)?;
        (0..b.units.len()).find(|&u| b.units[u].side_name.as_deref() == Some(label))
    }

    /// Does the person decide for unit `u` in `phase` ("move", "fire", "phys")? `base` is the answer without any branch (the person's units).
    pub fn is_human(&self, b: &Battle, u: usize, phase: &str, base: bool) -> bool {
        let Some(team) = b.units[u].team.as_deref() else { return base };
        if let Some((t, p, only)) = &self.meddle {
            if t == team && p == phase && only.as_ref().is_none_or(|l| b.units[u].side_name.as_deref() == Some(l.as_str())) {
                return true;
            }
        }
        match self.team_by.get(team) {
            Some(by) => by == "human",
            None => base,
        }
    }
}
