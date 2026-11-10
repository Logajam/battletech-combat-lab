//! The bots of a replay (Stage 6): every choice is read back from decisions.json (the Python's own answers), so the
//! engine runs alone. `Battle::decide` checks the kind and who each one is about and re-prints what the thinking printed.
use serde_json::Value;

use crate::attack_resolution::{DeclChoice, DeclCtx};
use crate::battle::{Battle, UnitId};
use crate::equipment::ItemId;
use crate::fire_modes::Planner;
use crate::mech_state::{ArcAction, Turret};
use crate::orchestrator::{BotSet, PathGate};
use crate::physical::PhysOption;
use crate::pyfmt::Num;
use crate::ranged_combat::Pick;

/// Replays the recorded decisions; with the `check_*` switches on it ALSO computes that decision with the Rust bot and
/// notes every difference from the recorded answer in `mismatches` (then carries on with the recorded answer, so one
/// battle reports all its differences).
/// Daniel (2026-11-10): last-digit float differences are not worth chasing; compare to 1e-12 relative.
fn close(a: f64, b: f64) -> bool {
    a == b || (a - b).abs() <= 1e-12 * a.abs().max(b.abs()).max(1.0)
}

#[derive(Default)]
pub struct ReplayBots {
    pub check_gladiator_declaration: bool,
    pub check_gladiator_physical: bool,
    pub check_simple_foe_target: bool,
    pub check_gladiator_move: bool,
    pub checked: std::collections::BTreeMap<String, (usize, usize)>,
    pub mismatches: Vec<String>,
}

impl ReplayBots {
    fn decode_declaration(b: &Battle, attacker: UnitId, v: &Value) -> DeclChoice {
        let t = t_list(v);
        let picked = t_list(&t[1]);
        let weapons: Vec<ItemId> = picked[0].as_array().unwrap().iter().map(|w| item_ref(b, w)).collect();
        let held = t[6].as_array().unwrap().iter().map(|a| item_at(b, attacker, a.as_str().unwrap())).collect();
        DeclChoice {
            weapons,
            exp_dmg: picked[1].as_f64().unwrap(),
            weapon_heat: picked[2].as_i64().unwrap(),
            key_torso_arc: t[2]["torso_arc"].as_i64().unwrap(),
            action: action_of(&t[3]),
            phys_names: t[4].as_array().unwrap().iter().map(|o| o["name"].as_str().unwrap().to_string()).collect(),
            phys_value: t[5].as_f64().unwrap(),
            held,
        }
    }

    fn note(&mut self, kind: &str, ok: bool, what: String) {
        let e = self.checked.entry(kind.to_string()).or_insert((0, 0));
        e.0 += 1;
        if !ok {
            e.1 += 1;
            if self.mismatches.len() < 40 {
                self.mismatches.push(what);
            }
        }
    }
}

/// The notes of a move decision print numbers to 2-3 places: two notes agree when their text is the same and every
/// number is within one unit of the last place printed (a 1-ulp float difference can tip a rounding, Daniel 2026-11-10).
fn notes_agree(a: &str, b: &str) -> bool {
    let split = |s: &str| -> (String, Vec<(f64, usize)>) {
        let mut skel = String::new();
        let mut nums = Vec::new();
        let chars: Vec<char> = s.chars().collect();
        let mut i = 0;
        while i < chars.len() {
            let c = chars[i];
            if c.is_ascii_digit() {
                let mut j = i;
                while j < chars.len() && (chars[j].is_ascii_digit() || chars[j] == '.') {
                    j += 1;
                }
                let t: String = chars[i..j].iter().collect();
                if t.contains('.') {
                    nums.push((t.parse::<f64>().unwrap(), t.len() - t.find('.').unwrap() - 1));
                    skel.push('#');
                } else {
                    skel.push_str(&t);
                }
                i = j;
            } else {
                skel.push(c);
                i += 1;
            }
        }
        (skel, nums)
    };
    let ((sa, na), (sb, nb)) = (split(a), split(b));
    sa == sb && na.len() == nb.len() && na.iter().zip(&nb).all(|((x, dx), (y, dy))| (x - y).abs() <= 1.01 * 10f64.powi(-(*dx.min(dy) as i32)))
}

fn nm(b: &Battle, u: UnitId) -> String {
    b.units[u].side_name.clone().unwrap_or_default()
}

fn unit_named(b: &Battle, name: &Value) -> Option<UnitId> {
    name.as_str().map(|n| b.unit_index(n))
}

fn item_at(b: &Battle, unit: UnitId, addr: &str) -> ItemId {
    b.units[unit].items.iter().position(|e| e.addr.as_deref() == Some(addr)).unwrap_or_else(|| panic!("no item {} on unit {}", addr, nm(b, unit)))
}

fn item_ref(b: &Battle, v: &Value) -> ItemId {
    let u = b.unit_index(v["of"].as_str().unwrap());
    item_at(b, u, v["_item"].as_str().unwrap())
}

fn t_list(v: &Value) -> &Vec<Value> {
    v["_t"].as_array().unwrap_or_else(|| panic!("not a tuple: {}", v))
}

fn action_of(v: &Value) -> ArcAction {
    let t = &v["turret"];
    ArcAction { twist: v["twist"].as_i64().unwrap(), flip: v["flip"].as_bool().unwrap(), turret: if t.is_null() { None } else { Turret::from_json(t) } }
}

fn num(v: &Value) -> Num {
    if let Some(i) = v.as_i64() { Num::I(i) } else { Num::F(v.as_f64().unwrap()) }
}

fn phys_option(v: &Value) -> PhysOption {
    let flag = |k: &str| v.get(k).and_then(|x| x.as_bool()).unwrap_or(false);
    let limb: Vec<String> = match &v["limb"] {
        Value::String(s) => vec![s.clone()],
        Value::Object(_) => t_list(&v["limb"]).iter().map(|x| x.as_str().unwrap().to_string()).collect(),
        _ => vec![],
    };
    PhysOption {
        name: v["name"].as_str().unwrap().to_string(),
        mod_: v["mod"].as_i64().unwrap(),
        damage: num(&v["damage"]),
        table: v["table"].as_str().unwrap().to_string(),
        limb,
        kick: flag("kick"),
        club: flag("club"),
        weapon: flag("weapon"),
        lance: flag("lance"),
        heat: v.get("heat").and_then(|x| x.as_i64()).unwrap_or(0),
        blade: v.get("blade").and_then(|x| x.as_str()).map(|s| s.to_string()),
        flail: flag("flail"),
        whip: flag("whip"),
        push: flag("push"),
        fumble: false,
        tn: None,
    }
}

impl BotSet for ReplayBots {
    fn choose_foe(&mut self, b: &mut Battle, mover: UnitId) -> Option<UnitId> {
        let who = nm(b, mover);
        let v = b.decide("foe", &who);
        let rec = unit_named(b, &v);
        if self.check_simple_foe_target && crate::forces::enemies_of(b, mover).len() == 1 {
            let mine = crate::forces::choose_foe(b, mover);
            self.note("foe(1 enemy)", mine == rec, format!("{}: {:?} v {:?}", who, mine, rec));
        }
        rec
    }

    fn choose_target(&mut self, b: &mut Battle, attacker: UnitId) -> Option<UnitId> {
        let who = nm(b, attacker);
        let v = b.decide("target", &who);
        let rec = unit_named(b, &v);
        if self.check_simple_foe_target && crate::forces::enemies_of(b, attacker).len() == 1 {
            let mine = crate::forces::choose_target(b, attacker, true, false);
            self.note("target(1 enemy)", mine == rec, format!("{}: {:?} v {:?}", who, mine, rec));
        }
        rec
    }

    fn fire_pick_active(&mut self, b: &mut Battle) -> bool {
        // bots.fire_pick: None (roster order) unless a side has two Gladiators and the order is "big_guns_first"
        if b.cfg.s("GLADIATOR_FIRE_ORDER") == "roster" {
            return false;
        }
        let standing = crate::forces::standing(b);
        let teams: Vec<String> = standing.iter().filter(|u| b.units[**u].bot != "princess").map(|u| b.units[*u].team.clone().unwrap_or_default()).collect();
        !teams.iter().all(|t| teams.iter().filter(|x| *x == t).count() < 2)
    }

    fn fire_pick(&mut self, b: &mut Battle, candidates: &[UnitId]) -> UnitId {
        let who: Vec<String> = candidates.iter().map(|u| nm(b, *u)).collect();
        let v = b.decide("fire_pick", &who.join(">"));
        unit_named(b, &v).expect("a fire pick")
    }

    fn choose_declaration(&mut self, b: &mut Battle, ctx: &DeclCtx, planner: &mut Planner, attacker: UnitId, target: UnitId) -> DeclChoice {
        let who = format!("{}>{}", nm(b, attacker), nm(b, target));
        let v = b.decide("declaration", &who);
        let recorded = Self::decode_declaration(b, attacker, &v);
        if self.check_gladiator_declaration && b.units[attacker].bot == "gladiator" {
            let mine = crate::gladiator::choose_declaration(b, ctx, planner, attacker, target);
            let same = mine.weapons == recorded.weapons
                && close(mine.exp_dmg, recorded.exp_dmg)
                && mine.weapon_heat == recorded.weapon_heat
                && mine.key_torso_arc == recorded.key_torso_arc
                && mine.action == recorded.action
                && mine.phys_names == recorded.phys_names
                && close(mine.phys_value, recorded.phys_value)
                && mine.held == recorded.held;
            let what = format!("turn {} {}: rust {:?} v python {:?}", b.units[attacker].turn_number, who, mine, recorded);
            self.note("declaration", same, what);
        }
        recorded
    }

    fn choose_physical(&mut self, b: &mut Battle, attacker: UnitId, target: UnitId) -> Option<(i64, Vec<PhysOption>, ArcAction)> {
        let who = format!("{}>{}", nm(b, attacker), nm(b, target));
        let v = b.decide("physical", &who);
        let recorded = if v.is_null() {
            None
        } else {
            let t = t_list(&v);
            Some((t[0].as_i64().unwrap(), t[1].as_array().unwrap().iter().map(phys_option).collect::<Vec<PhysOption>>(), action_of(&t[2])))
        };
        if self.check_gladiator_physical && b.units[attacker].bot == "gladiator" {
            let mine = crate::physical::choose_attack(b, attacker, target);
            let same = match (&mine, &recorded) {
                (None, None) => true,
                (Some(m), Some(r)) => m.0 == r.0 && m.2 == r.2 && m.1.len() == r.1.len() && m.1.iter().zip(&r.1).all(|(x, y)| x.name == y.name && x.mod_ == y.mod_ && x.table == y.table && x.limb == y.limb && close(x.damage.f(), y.damage.f())),
                _ => false,
            };
            self.note("physical", same, format!("{}: rust {:?} v python {:?}", who, mine, recorded));
        }
        recorded
    }

    fn choose_movement(&mut self, b: &mut Battle, mover: UnitId, other: UnitId, moves_first: bool, standup_mp: Option<i64>, entry_edge: Option<&[String]>) -> (Option<Pick>, String, PathGate) {
        let who = nm(b, mover);
        let v = b.decide("move", &who);
        let t = t_list(&v);
        let pick = if t[0].is_null() {
            None
        } else {
            let p = &t[0];
            Some(Pick {
                hex: p["hex"].as_str().unwrap().to_string(),
                facing: p["facing"].as_str().unwrap().to_string(),
                mode: p["mode"].as_str().unwrap().to_string(),
                fc: p["fc"].as_i64().unwrap(),
                mp_spent: p["mp_spent"].as_i64().unwrap(),
                charge: p.get("charge").and_then(|x| x.as_bool()).unwrap_or(false),
                dfa: p.get("dfa").and_then(|x| x.as_bool()).unwrap_or(false),
            })
        };
        if self.check_gladiator_move && b.units[mover].bot == "gladiator" && crate::forces::enemies_of(b, mover).len() == 1 {
            let saved = b.stub_counts.clone();
            let mut ties = crate::move_select::Ties { recorded: pick.as_ref(), missed: false };
            let (mine, note) = crate::move_select::choose(b, mover, other, moves_first, standup_mp, entry_edge, &mut ties);
            b.stub_counts = saved;
            let same = mine == pick && notes_agree(&note, t[1].as_str().unwrap()) && !ties.missed;
            let what = format!("turn {} {}: rust {:?} {:?} v python {:?} {:?}", b.units[mover].turn_number, who, mine, note, pick, t[1].as_str().unwrap());
            self.note("move", same, what);
        }
        let gate = PathGate { psrs: t[2].as_i64(), hazard: t[3].as_f64() };
        (pick, t[1].as_str().unwrap().to_string(), gate)
    }

    fn records_declared_damage(&self, _b: &Battle, _attacker: UnitId) -> bool {
        false // Princess's damage map is the bot's own state; nothing the engine prints depends on it
    }
}
