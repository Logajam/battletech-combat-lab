//! Hydra, the third bot (INTEGRATION__HYDRA.md is the plan: read it first). One planner for a whole team; every
//! decision is scored in one currency, the PRICE of a point of damage, and prices come from a small forecast of how the
//! battle ends. The blocks below carry the plan's names: LEDGER -> FORECAST -> PRICES, then MOVER and FIRE PLAN, which
//! ask the engine (the EXCHANGE ORACLE, `MoveEvaluator` / `dry_declare_as`) what damage flows and multiply by prices.
//!
//! Rust only: there is no Python version of this bot and no exact-match test. It is judged by results (plan, Section 4).
//!
//! SWITCHES, all ON by default since 2026-11-12 (Daniel: "Leave them all on"; together they beat the first version, see
//! INTEGRATION__HYDRA.md Section 7 "All five together"). Each is turned OFF by `btsim --set` with the value in brackets:
//!   HYDRA_PLAYOUT          the S5a movement play-out             ["reply": the first version's single reply]
//!   HYDRA_MOVEMENT_ATTACKS S4 charges and death from above       [false]
//!   HYDRA_MOVE_ORDER       S3 least to lose first, deciders last ["index": the engine's move index]
//!   HYDRA_WAITING          a unit out ahead may decline a bad trade [false]
//!   HYDRA_ATTENTION        the Oracle's attention share          ["range": the range rule]
use crate::battle::{Battle, UnitId};
use crate::fasthash::HashMap;
use crate::hex_geometry;
use crate::los::hex_distance;
use crate::mech_state::{compute_walk_mp, is_immobile};
use crate::move_eval::MoveEvaluator;
use crate::move_options::{self, Opt};
use crate::move_select::{self, Side};
use crate::ranged_combat::Pick;

/// Hydra's memory for one battle (`Battle::hydra`).
#[derive(Default)]
pub struct HydraState {
    /// the most `guns` each unit has shown this battle (a shut-down unit keeps part of its worth)
    best_guns: HashMap<UnitId, f64>,
    /// this Weapon Attack Phase's plan, per team: attacker -> target (emptied when the phase starts)
    fire: HashMap<String, HashMap<UnitId, Option<UnitId>>>,
    /// this Weapon Attack Phase's spotting plan, per team: spotter -> (target, also fires) (emptied when the phase starts)
    spots: HashMap<String, HashMap<UnitId, (UnitId, bool)>>,
    /// S3 MOVE ORDER: this Movement Phase's (guns, price) per unit, per team (emptied when the phase starts)
    order: HashMap<String, HashMap<UnitId, (f64, f64)>>,
    /// WAITING: per unit, (the turn it last declined battle, how many turns in a row it has)
    waited: HashMap<UnitId, (i64, i64)>,
    /// C3: per networked Hydra unit, the expected damage of its planned shots this battle (with the network, without)
    c3_shots: HashMap<UnitId, (f64, f64)>,
}

impl HydraState {
    /// The Weapon Attack Phase begins: last turn's fire plans are void.
    pub fn start_fire_phase(&mut self) {
        self.fire.clear();
        self.spots.clear();
    }

    /// The Movement Phase begins: last turn's move-order prices are void.
    pub fn start_movement_phase(&mut self) {
        self.order.clear();
    }
}

// =============================================================================================================
// LEDGER: what every unit is worth right now
// =============================================================================================================
#[derive(Clone, Copy, Debug)]
pub struct Entry {
    pub unit: UnitId,
    /// damage it can still absorb
    pub life: f64,
    /// damage a turn it puts out when it has a shot (with its C3 network's bonus while the network works)
    pub guns: f64,
    /// its C3 network, if it is in a working one now (`Net`)
    pub net: Option<Net>,
}

/// A unit's C3 network in the ledger (2026-11-21, Daniel: Hydra should think about "how would I program the desired
/// outcome"). `bonus`: the part of its guns the network gives; `group`: the network (its lowest unit id); `anchor`: the
/// unit it depends on (a Slave's Master), if any. The Forecast takes the bonus away when the anchor is destroyed or no
/// partner is left (Core p.198), so a Master is priced for the bonuses its loss would end.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Net {
    pub bonus: f64,
    pub group: UnitId,
    pub anchor: Option<UnitId>,
    /// the anchor's life undamaged (its life now is in its own entry)
    pub anchor_full: f64,
}

/// What a network adds to a unit's shots before any of them is measured: 4%, the gain measured on Hydra's own C3 lance
/// (2026-11-21: Cyclops / Hatamoto-Chi / Centurion / Clint v Atlas / Awesome / Archer / Cataphract, 20 battles, 1,143
/// planned shots priced with and without the network: +3%, +6%, +3%, +0%). It also stands for an enemy's network, whose
/// shots Hydra does not plan.
pub const C3_PRIOR_GAIN: f64 = 0.04;
/// How much expected damage the prior counts for: a unit's own measurement takes over after a few turns of shots.
pub const C3_PRIOR_WEIGHT: f64 = 50.0;

/// The share a unit's network adds to its shots: its measured shots (with the network v without) blended with the prior.
fn c3_gain(b: &Battle, u: UnitId) -> f64 {
    let (on, off) = b.hydra.c3_shots.get(&u).copied().unwrap_or((0.0, 0.0));
    ((on - off) + C3_PRIOR_GAIN * C3_PRIOR_WEIGHT) / (off + C3_PRIOR_WEIGHT)
}

/// A unit that cannot fire this turn (shut down, no enemy to measure against) still counts for this much of its best.
const DORMANT_GUNS: f64 = 0.5;
/// No unit is worth less than this in guns (a disarmed 'Mech still kicks).
const MIN_GUNS: f64 = 1.0;

/// A unit's life in the ledger: armor + k x internal structure of the locations still standing. k is Hydra's own setting
/// HYDRA_LIFE_STRUCTURE_WEIGHT (S6 second pass, session 25); without it, Gladiator's MOVEMENT_STRUCTURE_WEIGHT through
/// `orchestrator::effective_hp` (the first version's life, shared with Gladiator).
fn life_of(b: &Battle, u: UnitId) -> f64 {
    if !b.cfg.has("HYDRA_LIFE_STRUCTURE_WEIGHT") {
        return crate::orchestrator::effective_hp(b, u);
    }
    let k = b.cfg.f("HYDRA_LIFE_STRUCTURE_WEIGHT");
    let mut sum = 0.0;
    for v in b.units[u].locations.values() {
        if !v.destroyed {
            sum += v.armor.f() + v.rear_armor.map_or(0.0, |r| r.f()) + k * v.structure.f();
        }
    }
    sum
}

/// A unit's life undamaged (`life_of` with every location at its full armor and structure): what a C3 Master's life is
/// measured against in the Forecast (`net_loss`).
fn full_life_of(b: &Battle, u: UnitId) -> f64 {
    let k = if b.cfg.has("HYDRA_LIFE_STRUCTURE_WEIGHT") { b.cfg.f("HYDRA_LIFE_STRUCTURE_WEIGHT") } else { b.cfg.f("MOVEMENT_STRUCTURE_WEIGHT") };
    let m = &b.units[u];
    let armor: i64 = m.max_armor.values().sum::<i64>() + m.max_rear_armor.values().sum::<i64>();
    let structure: i64 = m.max_structure.values().sum();
    armor as f64 + k * structure as f64
}

/// (my team's entries, the enemy's entries): every unit still fighting, on or off the board.
pub fn ledger(b: &mut Battle, me: UnitId) -> (Vec<Entry>, Vec<Entry>) {
    ledger_as(b, me, true)
}

/// `ledger`; with `remember` false it only reads (the best guns seen are used, not raised).
fn ledger_as(b: &mut Battle, me: UnitId, remember: bool) -> (Vec<Entry>, Vec<Entry>) {
    let team = b.units[me].team.clone();
    let alive = crate::forces::standing(b);
    let per_turn = b.cfg.f("MOVEMENT_LIFETIME_INITIATIVE");
    let (mut mine, mut theirs) = (Vec::new(), Vec::new());
    for &u in &alive {
        let foe = alive.iter().copied().find(|v| b.units[*v].team != b.units[u].team);
        let mut guns = match foe {
            Some(f) => move_select::future_damage(b, u, f) / if per_turn > 0.0 { per_turn } else { 1.0 },
            None => 0.0,
        };
        let best = if remember {
            let best = b.hydra.best_guns.entry(u).or_insert(0.0);
            if guns > *best {
                *best = guns;
            }
            *best
        } else {
            b.hydra.best_guns.get(&u).copied().unwrap_or(0.0).max(guns)
        };
        guns = guns.max(DORMANT_GUNS * best).max(MIN_GUNS);
        // C3: the network's share on top, kept apart so the Forecast can take it away when the network breaks
        let net = crate::c3::link(b, u).map(|(group, anchor)| Net { bonus: guns * c3_gain(b, u).max(0.0), group, anchor, anchor_full: anchor.map_or(0.0, |a| full_life_of(b, a)) });
        if let Some(n) = &net {
            guns += n.bonus;
        }
        let e = Entry { unit: u, life: life_of(b, u).max(1.0), guns, net };
        if b.units[u].team == team { mine.push(e) } else { theirs.push(e) }
    }
    (mine, theirs)
}

// =============================================================================================================
// FORECAST: how the battle ends from here, as pure attrition
// =============================================================================================================
/// The share of a side's `guns` that lands in one forecast step.
const STEP_FIRE: f64 = 0.5;
const MAX_STEPS: usize = 60;

/// One side's fire for a step, poured onto the other side's units in kill order (most guns removed per point of damage
/// first); what is left over after a kill carries on to the next.
fn pour(fire: f64, targets: &[(f64, f64)], hits: &mut [f64]) {
    let mut order: Vec<usize> = (0..targets.len()).filter(|i| targets[*i].0 > 0.0).collect();
    order.sort_by(|x, y| (targets[*y].1 / targets[*y].0).partial_cmp(&(targets[*x].1 / targets[*x].0)).unwrap().then(x.cmp(y)));
    let mut left = fire;
    for i in order {
        if left <= 0.0 {
            break;
        }
        let take = left.min(targets[i].0);
        hits[i] += take;
        left -= take;
    }
}

/// The Forecast's shape (S6 calibration, session 25; tools/hydra_calibrate.py fits it on finished battles):
/// FOCUS - the share of a side's fire poured in kill order; the rest is spread over the enemy in proportion to life left;
/// FADE  - a unit's guns shrink with its life, guns x (life / life at the start) ^ FADE (0: full guns until destroyed);
/// STEP  - the share of a side's guns that lands in one step.
/// Settings HYDRA_FORECAST_FOCUS / _FADE / _STEP. DEFAULT (calibrated, session 25): FOCUS 0, FADE 0, STEP 0.5. The fit on
/// 1,092 recorded battles (tools/hydra_calibrate.py): with 9+ units alive, spread fire describes real battles 20% better
/// than perfect focus (error 0.040 v 0.050); FADE only made it worse; STEP hardly matters. In battle (same seeds) the
/// six team match-ups went 176-145 -> 224-103 v Gladiator and 248-130 -> 266-110 v Princess; duels are unchanged (one
/// target: nothing to focus). `Shape::FIRST` (1, 0, 0.5) is the first version's (perfect focus).
#[derive(Clone, Copy, Debug)]
pub struct Shape {
    pub focus: f64,
    pub fade: f64,
    pub step: f64,
}

impl Shape {
    pub const FIRST: Shape = Shape { focus: 1.0, fade: 0.0, step: STEP_FIRE };
    /// the calibrated default
    pub const CALIBRATED: Shape = Shape { focus: 0.0, fade: 0.0, step: STEP_FIRE };

    pub fn of(b: &Battle) -> Shape {
        let get = |k: &str, d: f64| if b.cfg.has(k) { b.cfg.f(k) } else { d };
        let d = Shape::CALIBRATED;
        Shape { focus: get("HYDRA_FORECAST_FOCUS", d.focus), fade: get("HYDRA_FORECAST_FADE", d.fade), step: get("HYDRA_FORECAST_STEP", d.step) }
    }
}

/// Fire spread over the targets in proportion to the life each has left (the unfocused share of a side's fire).
fn spread(fire: f64, targets: &[(f64, f64)], hits: &mut [f64]) {
    let total: f64 = targets.iter().filter(|t| t.0 > 0.0).map(|t| t.0).sum();
    if total <= 0.0 {
        return;
    }
    for (i, t) in targets.iter().enumerate() {
        if t.0 > 0.0 {
            hits[i] += fire * t.0 / total;
        }
    }
}

/// The margin: what side A has left minus what side B has left once one of them is gone (each unit counted as guns x
/// life), as a share of what both began with. Each entry is (life, guns). The first version's shape (perfect focus).
pub fn forecast(a: &[(f64, f64)], b: &[(f64, f64)]) -> f64 {
    forecast_with(a, b, &Shape::FIRST)
}

/// `forecast` with a given shape. With `Shape::FIRST` it does exactly the first version's arithmetic.
pub fn forecast_with(a: &[(f64, f64)], b: &[(f64, f64)], shape: &Shape) -> f64 {
    forecast_net(a, b, &[], &[], shape)
}

/// One unit's C3 network in the Forecast (indices into its own side): (bonus, network, the unit it depends on and that
/// unit's life undamaged).
type NetIx = Option<(f64, UnitId, Option<(usize, f64)>)>;

/// How much of unit `i`'s network bonus is lost this step (Core p.198: a Slave drops out when its Master is destroyed; a
/// network with no partner left gives nothing). The Forecast is an expectation, not a play-out: in its calibrated shape
/// fire is spread by the life each unit has left, so a side's units all fall together and a hard "the Master is
/// destroyed" step would never single the Master out. So a Slave keeps its bonus in proportion to the life its Master
/// has left (the less of it stands, the likelier it is gone by the next turn), and loses it all when the Master or every
/// partner is down.
fn net_loss(s: &[(f64, f64)], nets: &[NetIx], i: usize) -> f64 {
    let Some(Some((bonus, group, anchor))) = nets.get(i) else { return 0.0 };
    let partners = nets.iter().enumerate().filter(|(j, n)| *j != i && s[*j].0 > 0.0 && n.is_some_and(|n| n.1 == *group)).count();
    if partners == 0 {
        return *bonus;
    }
    match anchor {
        Some((a, full)) if *full > 0.0 => bonus * (1.0 - (s[*a].0 / full).clamp(0.0, 1.0)),
        Some(_) => *bonus,
        None => 0.0,
    }
}

/// `forecast_with` with each side's C3 networks (`nets_a` / `nets_b`, one per unit, or empty for none): a unit's bonus
/// leaves its guns when its network breaks.
pub fn forecast_net(a: &[(f64, f64)], b: &[(f64, f64)], nets_a: &[NetIx], nets_b: &[NetIx], shape: &Shape) -> f64 {
    let (a0, b0) = (a.to_vec(), b.to_vec());
    let (mut a, mut b) = (a.to_vec(), b.to_vec());
    let worth = |s: &[(f64, f64)]| s.iter().map(|(l, g)| l.max(0.0) * g).sum::<f64>();
    let start = worth(&a) + worth(&b);
    if start <= 0.0 {
        return 0.0;
    }
    // a side's guns this step (FADE: shrunk with the life each unit has left)
    let guns = |s: &[(f64, f64)], s0: &[(f64, f64)], nets: &[NetIx]| -> f64 {
        let lost: f64 = if nets.is_empty() { 0.0 } else { (0..s.len()).filter(|i| s[*i].0 > 0.0).map(|i| net_loss(s, nets, i)).sum() };
        let full = if shape.fade == 0.0 {
            s.iter().filter(|u| u.0 > 0.0).map(|u| u.1).sum::<f64>()
        } else {
            s.iter().zip(s0).filter(|(u, _)| u.0 > 0.0).map(|(u, u0)| u.1 * (u.0 / u0.0).powf(shape.fade)).sum::<f64>()
        };
        full - lost
    };
    for _ in 0..MAX_STEPS {
        let fire_a: f64 = guns(&a, &a0, nets_a) * shape.step;
        let fire_b: f64 = guns(&b, &b0, nets_b) * shape.step;
        if fire_a <= 0.0 || fire_b <= 0.0 {
            break;
        }
        let (mut hits_b, mut hits_a) = (vec![0.0; b.len()], vec![0.0; a.len()]);
        if shape.focus >= 1.0 {
            pour(fire_a, &b, &mut hits_b);
            pour(fire_b, &a, &mut hits_a);
        } else {
            pour(fire_a * shape.focus, &b, &mut hits_b);
            spread(fire_a * (1.0 - shape.focus), &b, &mut hits_b);
            pour(fire_b * shape.focus, &a, &mut hits_a);
            spread(fire_b * (1.0 - shape.focus), &a, &mut hits_a);
        }
        for (u, h) in b.iter_mut().zip(&hits_b) {
            u.0 -= h;
        }
        for (u, h) in a.iter_mut().zip(&hits_a) {
            u.0 -= h;
        }
    }
    (worth(&a) - worth(&b)) / start
}

// =============================================================================================================
// PRICES: what one point of damage on each unit is worth
// =============================================================================================================
/// unit -> price. For an enemy: how far a point of damage on it moves the margin my way. For a friend: how far a point
/// of damage on it moves the margin against me.
pub fn prices(mine: &[Entry], theirs: &[Entry]) -> HashMap<UnitId, f64> {
    prices_with(mine, theirs, &Shape::FIRST)
}

/// `prices` with a given Forecast shape.
pub fn prices_with(mine: &[Entry], theirs: &[Entry], shape: &Shape) -> HashMap<UnitId, f64> {
    let a: Vec<(f64, f64)> = mine.iter().map(|e| (e.life, e.guns)).collect();
    let b: Vec<(f64, f64)> = theirs.iter().map(|e| (e.life, e.guns)).collect();
    // C3 networks, as indices into each side (none at all: the plain Forecast, as before networks existed)
    let ix = |side: &[Entry]| -> Vec<NetIx> {
        if side.iter().all(|e| e.net.is_none()) {
            return vec![];
        }
        side.iter().map(|e| e.net.map(|n| (n.bonus, n.group, n.anchor.and_then(|a| side.iter().position(|x| x.unit == a)).map(|i| (i, n.anchor_full))))).collect()
    };
    let (na, nb) = (ix(mine), ix(theirs));
    let forecast_with = |a: &[(f64, f64)], b: &[(f64, f64)], shape: &Shape| forecast_net(a, b, &na, &nb, shape);
    let base = forecast_with(&a, &b, shape);
    let total: f64 = a.iter().chain(b.iter()).map(|(l, g)| l * g).sum();
    let mut out = HashMap::default();
    for (side, entries) in [(0, mine), (1, theirs)] {
        for (i, e) in entries.iter().enumerate() {
            let bite = e.life.min((0.15 * e.life).max(10.0));
            let (mut a2, mut b2) = (a.clone(), b.clone());
            if side == 0 { a2[i].0 -= bite } else { b2[i].0 -= bite }
            let moved = (forecast_with(&a2, &b2, shape) - base).abs() / bite;
            // never free: at the least, the unit's own guns x the damage, on the margin's scale
            let floor = 0.25 * e.guns / total.max(1.0);
            out.insert(e.unit, moved.max(floor));
        }
    }
    // scaled so the mean price is 1: scores then read as points of damage
    let mean = out.values().sum::<f64>() / out.len().max(1) as f64;
    if mean > 0.0 {
        for v in out.values_mut() {
            *v /= mean;
        }
    }
    out
}

// =============================================================================================================
// MOVER: where one unit goes
// =============================================================================================================
/// How much of an enemy's attention a friend at `dist` hexes draws, next to a unit it has a clear shot at (the attention
/// share's rough alternative; replaceable by the oracle when the cost allows).
fn range_factor(dist: i64) -> f64 {
    if dist <= 9 { 1.0 } else if dist <= 15 { 0.6 } else if dist <= 21 { 0.3 } else { 0.0 }
}

/// ATTENTION SHARE: what else enemy `e` could be shooting at instead of the mover - the most (friend's price x damage
/// on that friend) over the mover's friends. Two estimates:
///   * the first version (default): the enemy's guns x `range_factor` of the distance, a rough range rule;
///   * HYDRA_ATTENTION = "oracle" (session 25): the EXCHANGE ORACLE's expected damage of `e` on the friend as both
///     stand (the engine's own to-hit, range, arcs, cover and line of sight), with `e` as a ghost if it has not moved
///     (in its hex, having walked, facing the friend) and the friend where it is now.
fn elsewhere_of(b: &mut Battle, memo: &mut AttentionMemo, e: UnitId, friends: &[UnitId], price: &HashMap<UnitId, f64>, guns: &HashMap<UnitId, f64>) -> f64 {
    let Some(e_xy) = xy(b, e) else { return 0.0 };
    let oracle = !(b.cfg.has("HYDRA_ATTENTION") && b.cfg.s("HYDRA_ATTENTION") == "range");
    let mut most = 0.0f64;
    for &f in friends {
        let Some(f_xy) = xy(b, f) else { continue };
        let dmg = if oracle { memo.damage(b, e, f, e_xy, f_xy) } else { guns.get(&e).copied().unwrap_or(0.0) * range_factor(hex_distance(e_xy, f_xy)) };
        most = most.max(price.get(&f).copied().unwrap_or(1.0) * dmg);
    }
    most
}

/// One decision's store of `attention_damage` figures (speed only, 2026-11-19: building a `MoveEvaluator` for every
/// enemy-friend pair, again for every play-out spot, was ~78% of a 12 v 12 Hydra battle). The play-out poses only a few
/// responders per spot, so most pairs stand exactly as they did for the last spot. A figure is reused when both units
/// stand as they did (hex, facing, how they moved, heat of moving, moved yet): the estimate reads nothing else that a pose
/// changes, with one exception - a push's worth asks whether the hex behind the target is taken (`physical.rs`,
/// `domino::occupant`), which only matters when the two are adjacent, so adjacent pairs are always worked out afresh.
/// Lives for one decision: damage, heat and ammo do not change inside it. Set BTSIM_HYDRA_MEMO_CHECK=1 to recompute
/// every reused figure and stop on any difference (the cross-check used to accept this).
type PoseSig = (Option<String>, String, String, i64, i64, i64, bool);

#[derive(Default)]
pub(crate) struct AttentionMemo {
    figures: HashMap<(UnitId, UnitId, PoseSig, PoseSig), f64>,
}

fn pose_sig(b: &Battle, u: UnitId) -> PoseSig {
    let m = &b.units[u];
    (m.hex.clone(), m.facing.clone(), m.move_mode.clone(), m.move_fc, m.mp_spent, m.movement_heat, m.moved_this_turn)
}

impl AttentionMemo {
    fn damage(&mut self, b: &mut Battle, e: UnitId, f: UnitId, e_xy: (i64, i64), f_xy: (i64, i64)) -> f64 {
        if hex_distance(e_xy, f_xy) <= 1 {
            return attention_damage(b, e, f, e_xy, f_xy);
        }
        let key = (e, f, pose_sig(b, e), pose_sig(b, f));
        if let Some(&v) = self.figures.get(&key) {
            if memo_check() {
                let fresh = attention_damage(b, e, f, e_xy, f_xy);
                assert!(fresh.to_bits() == v.to_bits(), "Hydra attention memo differs: {} on {}: kept {} fresh {}", e, f, v, fresh);
            }
            return v;
        }
        let v = attention_damage(b, e, f, e_xy, f_xy);
        self.figures.insert(key, v);
        v
    }
}

fn memo_check() -> bool {
    static CHECK: std::sync::OnceLock<bool> = std::sync::OnceLock::new();
    *CHECK.get_or_init(|| std::env::var("BTSIM_HYDRA_MEMO_CHECK").map_or(false, |v| v == "1"))
}

/// The Oracle's expected damage of enemy `e` on friend `f` this turn, both where they stand (see `elsewhere_of`).
fn attention_damage(b: &mut Battle, e: UnitId, f: UnitId, e_xy: (i64, i64), f_xy: (i64, i64)) -> f64 {
    // a friend out of every weapon's reach of the enemy, even after the enemy walks, draws nothing
    if hex_distance(e_xy, f_xy) > move_select::max_range(b, e) + compute_walk_mp(&b.units[e]).max(0) {
        return 0.0;
    }
    let fixed = b.units[e].moved_this_turn || is_immobile(&b.units[e]);
    let key: crate::move_options::StateKey = if fixed {
        let m = &b.units[e];
        let mode: &'static str = match m.move_mode.as_str() {
            "Walk" => "Walk",
            "Run" => "Run",
            "Jump" => "Jump",
            _ => "Stand Still",
        };
        (e_xy.0, e_xy.1, hex_geometry::compass_to_facing(&m.facing).unwrap_or(0), m.move_fc, mode, m.mp_spent)
    } else {
        let walked = compute_walk_mp(&b.units[e]).max(0);
        let facing = if e_xy == f_xy { 0 } else { crate::combat::direction_facing(e_xy, f_xy).unwrap_or(0).rem_euclid(6) };
        (e_xy.0, e_xy.1, facing, walked, if walked > 0 { "Walk" } else { "Stand Still" }, walked)
    };
    let mut ev = MoveEvaluator::new(b, e, f).with_c3(b);
    let prepared = ev.prepare(b, &[key]);
    if prepared.is_empty() {
        return 0.0;
    }
    let m = &b.units[f];
    let (label, facing, fc, mode, mp) = (m.hex.clone().unwrap(), m.facing.clone(), m.move_fc, m.move_mode.clone(), m.mp_spent);
    ev.evaluate(b, &label, &facing, fc, &mode, mp, &prepared, true).iter().map(|c| c.dealt).fold(0.0, f64::max)
}

/// WAITING (switch HYDRA_WAITING, session 25): a unit may decline battle at most this many turns in a row.
const MAX_WAITS: i64 = 2;

/// A friend this many hexes further from the enemy than the mover is still COMING (the mover is out ahead of it).
const BEHIND: i64 = 3;

/// Is a friend still COMING: not on the board yet, or on it, able to move, and at least BEHIND hexes further from its
/// nearest enemy than the mover is from its own (so the mover is out in front of its line)? Returns (any coming, the board
/// positions of those on the board). First try (out of every enemy's reach, `legate::can_matter`) never held in the mirror
/// match-ups: both forces enter together and all are in reach from the first turn.
fn coming_friends(b: &mut Battle, mover: UnitId, enemies: &[UnitId]) -> (bool, Vec<(i64, i64)>) {
    let nearest = |b: &Battle, p: (i64, i64)| enemies.iter().filter_map(|e| xy(b, *e)).map(|q| hex_distance(p, q)).min().unwrap_or(0);
    let Some(m) = xy(b, mover) else { return (false, Vec::new()) };
    let front = nearest(b, m);
    let mut any = false;
    let mut at = Vec::new();
    let friends: Vec<UnitId> = crate::forces::standing(b).into_iter().filter(|u| *u != mover && b.units[*u].team == b.units[mover].team).collect();
    for f in friends {
        match xy(b, f) {
            None => any = true,
            Some(p) => {
                if !is_immobile(&b.units[f]) && nearest(b, p) >= front + BEHIND {
                    any = true;
                    at.push(p);
                }
            }
        }
    }
    (any, at)
}

/// THE REPLY's budget: about this many "what would it answer" searches per move, shared out over the enemies weighed, and
/// never more than REPLY_MAX spots re-scored. Under 2 spots the reply is skipped (a big battle: the table speaks alone).
const REPLY_BUDGET: usize = 64;
const REPLY_MAX: usize = 64;


/// WHERE DAMAGE LANDS: the engine's exposure factors of a unit, in the order front / left / right / rear: how much worse
/// a hit from that side is than one from the front, from the armor and structure left there. Every damage figure in an
/// exchange is multiplied by the factor of the side it arrives on, so a unit turns its weak side away and seeks the
/// enemy's. (2026-11-11 trial, 2 v 2 and 4 v 4 woods, 80 battles each: 69-64 with it, 59-70 without.)
fn soft(e: [f64; 4]) -> [f64; 4] {
    e
}
fn side_ix(s: &str) -> usize {
    match s {
        "front" => 0,
        "left" => 1,
        "right" => 2,
        _ => 3,
    }
}

fn xy(b: &Battle, u: UnitId) -> Option<(i64, i64)> {
    b.units[u].hex.as_deref().and_then(|h| hex_geometry::parse_hex_label(h).ok())
}

/// The EXCHANGE ORACLE for one enemy: per prepared option, (damage I deal it, damage it deals me). An enemy that has
/// moved is taken where it stands (fixed pose); one that has not is a ghost: in its hex, having walked, turned to face
/// each option.
fn exchange(b: &mut Battle, mover: UnitId, enemy: UnitId, prepared: &[Opt], index: &HashMap<(String, &'static str, &'static str, i64), usize>, my_exp: &[f64; 4], its_exp: &[f64; 4]) -> Vec<(f64, f64)> {
    let mut out = vec![(0.0, 0.0); prepared.len()];
    let label = b.units[enemy].hex.clone().unwrap();
    let e_xy = hex_geometry::parse_hex_label(&label).unwrap();
    let mut ev = MoveEvaluator::new(b, mover, enemy).with_c3(b);
    let fixed = b.units[enemy].moved_this_turn || is_immobile(&b.units[enemy]);
    let mut put = |cands: Vec<crate::move_eval::Candidate>| {
        for c in cands {
            if let Some(&i) = index.get(&c.key4()) {
                out[i] = (c.dealt * its_exp[side_ix(c.side_on_defender)], c.received * my_exp[side_ix(c.side_on_mover)]);
            }
        }
    };
    if fixed {
        let (facing, fc, mode, mp) = (b.units[enemy].facing.clone(), b.units[enemy].move_fc, b.units[enemy].move_mode.clone(), b.units[enemy].mp_spent);
        put(ev.evaluate(b, &label, &facing, fc, &mode, mp, prepared, true));
    } else {
        let walked = compute_walk_mp(&b.units[enemy]).max(0);
        let mode = if walked > 0 { "Walk" } else { "Stand Still" };
        let mut groups: Vec<Vec<Opt>> = vec![Vec::new(); 6];
        for o in prepared {
            let f = if o.hex_xy() == e_xy { 0 } else { crate::combat::direction_facing(e_xy, o.hex_xy()).unwrap_or(0) };
            groups[(f.rem_euclid(6)) as usize].push(o.clone());
        }
        for (f, group) in groups.iter().enumerate() {
            if group.is_empty() {
                continue;
            }
            let compass = hex_geometry::facing_to_compass(f as i64).unwrap();
            put(ev.evaluate(b, &label, compass, walked, mode, walked, group, true));
        }
    }
    indirect_exchange(b, mover, enemy, prepared, &mut out, my_exp, its_exp);
    out
}

/// The modifier a spotter at `at` (height `h`, attacker movement modifier `amm`) adds to indirect fire on a target at
/// `t` (height `th`): +1 indirect, its movement, +1 as it is assumed to fire too, the terrain along its line (Core p.70).
/// None: it would not see the target.
fn spot_extra(b: &Battle, at: (i64, i64), h: crate::los::Height, amm: i64, t: (i64, i64), th: crate::los::Height) -> Option<i64> {
    let line = crate::move_eval::pair_info(b, at, t, h, th)?;
    line.los.los.then(|| crate::spotting::INDIRECT_MODIFIER + amm + crate::spotting::SPOTTER_ATTACKING_MODIFIER + line.los.modifier)
}

/// The best spotter's modifier among `spotters` (each where it stands; one that has moved this turn at its movement
/// modifier, one still to move at a walk's) for a target at `t`.
fn best_spot_extra(b: &Battle, spotters: &[UnitId], t: (i64, i64), th: crate::los::Height) -> Option<i64> {
    spotters
        .iter()
        .filter_map(|&f| {
            let at = xy(b, f)?;
            let amm = if b.units[f].moved_this_turn { crate::combat::mode_to_amm(&b.units[f].move_mode) } else { 1 };
            spot_extra(b, at, crate::attack_resolution::los_height(&b.units[f]), amm, t, th)
        })
        .min()
}

/// INDIRECT FIRE IN THE EXCHANGE (2026-11-21; Daniel: think about "how would I program the desired outcome"). The engine's
/// evaluator prices direct fire only, so a hex with no line of sight to `enemy` used to read 0 dealt and 0 received: a
/// hidden LRM boat did nothing, and hiding was perfectly safe even from enemy LRMs with a spotter. Here (Core p.70):
///   * DEALT from a hidden hex: the mover's indirect weapons, if a friend sees the enemy now (the best such spotter's
///     modifiers; it is assumed to spot, as Hydra's spot plan then decides by price);
///   * RECEIVED in a hidden hex: the enemy's indirect weapons, if one of its friends would see that hex;
///   * SPOTTING from a hex that sees the enemy: when no friend sees it now, the indirect damage this unit's line would
///     open for each hidden friend (one that sees no enemy at all where it stands: the LRM boat waiting for a spotter),
///     added to what the hex deals the enemy.
/// Friends and the enemy's friends are taken where they stand (as the rest of the Mover takes unmoved units). A unit
/// with no indirect weapons, or a battle with none, is untouched.
fn indirect_exchange(b: &mut Battle, mover: UnitId, enemy: UnitId, prepared: &[Opt], out: &mut [(f64, f64)], my_exp: &[f64; 4], its_exp: &[f64; 4]) {
    let Some(e_xy) = xy(b, enemy) else { return };
    let e_h = crate::attack_resolution::los_height(&b.units[enemy]);
    let m_h = crate::los::mech_height(false, crate::mech_state::is_superheavy(&b.units[mover]));
    let standing = crate::forces::standing(b);
    let team = b.units[mover].team.clone();
    let alive = |b: &Battle, u: UnitId| b.units[u].hex.is_some() && !b.units[u].shutdown;
    let friends: Vec<UnitId> = standing.iter().copied().filter(|&f| f != mover && b.units[f].team == team && alive(b, f)).collect();
    let their_friends: Vec<UnitId> = standing.iter().copied().filter(|&f| f != enemy && b.units[f].team == b.units[enemy].team && alive(b, f)).collect();
    let enemies: Vec<UnitId> = standing.iter().copied().filter(|&f| b.units[f].team != team && alive(b, f)).collect();
    // movement modifiers as the direct-fire evaluator takes them: the enemy where it stands at its move this turn (one
    // still to move at a walk, as the ghost pose has it); the mover's own per hex below
    let size = |b: &Battle, u: UnitId| crate::mech_state::target_size_modifier(&b.units[u]);
    let (e_tmm, e_amm) = if b.units[enemy].moved_this_turn || is_immobile(&b.units[enemy]) {
        let jump = b.units[enemy].move_mode == "Jump";
        (crate::combat::fc_to_tmm(b.units[enemy].move_fc, jump).unwrap_or(0) + size(b, enemy), crate::combat::mode_to_amm(&b.units[enemy].move_mode))
    } else {
        let walked = compute_walk_mp(&b.units[enemy]).max(0);
        (crate::combat::fc_to_tmm(walked, false).unwrap_or(0) + size(b, enemy), crate::combat::mode_to_amm(if walked > 0 { "Walk" } else { "Stand Still" }))
    };
    // the friend's spot of this enemy now (the same for every hidden hex of the mover)
    let our_spot = best_spot_extra(b, &friends, e_xy, e_h);
    let mut dealt_profiles: HashMap<i64, Option<crate::move_select::IndirectProfile>> = HashMap::default();
    // the hidden friends a spot of this enemy would serve (only when no friend sees it now)
    let mut hidden: Vec<(UnitId, i64)> = Vec::new();
    if our_spot.is_none() {
        for &f in &friends {
            let Some(f_xy) = xy(b, f) else { continue };
            let f_h = crate::attack_resolution::los_height(&b.units[f]);
            let sees_any = enemies.iter().any(|&e| xy(b, e).is_some_and(|p| crate::move_eval::pair_info(b, f_xy, p, f_h, crate::attack_resolution::los_height(&b.units[e])).is_some_and(|i| i.los.los)));
            if !sees_any && !crate::spotting::indirect_capable(b, f).is_empty() {
                hidden.push((f, hex_distance(f_xy, e_xy)));
            }
        }
    }
    let mut their_profiles: HashMap<(i64, i64), Option<crate::move_select::IndirectProfile>> = HashMap::default();
    let mut hidden_profiles: HashMap<(UnitId, i64), Option<crate::move_select::IndirectProfile>> = HashMap::default();
    let mut received_at: HashMap<String, Option<i64>> = HashMap::default();
    for (i, o) in prepared.iter().enumerate() {
        let o_xy = o.hex_xy();
        if o_xy == e_xy {
            continue;
        }
        let Some(line) = crate::move_eval::pair_info(b, o_xy, e_xy, m_h, e_h) else { continue };
        let d = hex_distance(o_xy, e_xy);
        if line.los.los {
            // a hex that sees the enemy: the spot it would give the hidden friends
            for &(f, fd) in &hidden {
                let extra = crate::spotting::INDIRECT_MODIFIER + o.amm + crate::spotting::SPOTTER_ATTACKING_MODIFIER + line.los.modifier;
                // the hidden friend at its move this turn (one still to move, standing still to fire)
                let f_amm = if b.units[f].moved_this_turn { crate::combat::mode_to_amm(&b.units[f].move_mode) } else { 0 };
                let p = hidden_profiles.entry((f, extra)).or_insert_with(|| crate::move_select::IndirectProfile::new(b, f, enemy, f_amm, e_tmm, extra));
                if let Some(p) = p.as_mut() {
                    out[i].0 += p.at(b, fd) * its_exp[0];
                }
            }
            continue;
        }
        // a hidden hex: indirect fire both ways
        if let Some(extra) = our_spot {
            let p = dealt_profiles.entry(o.amm).or_insert_with(|| crate::move_select::IndirectProfile::new(b, mover, enemy, o.amm, e_tmm, extra));
            if let Some(p) = p.as_mut() {
                out[i].0 += p.at(b, d) * its_exp[0];
            }
        }
        let extra = match received_at.get(&o.label) {
            Some(x) => *x,
            None => {
                let x = best_spot_extra(b, &their_friends, o_xy, m_h);
                received_at.insert(o.label.clone(), x);
                x
            }
        };
        if let Some(extra) = extra {
            let p = their_profiles.entry((extra, o.tmm)).or_insert_with(|| crate::move_select::IndirectProfile::new(b, enemy, mover, e_amm, o.tmm, extra));
            if let Some(p) = p.as_mut() {
                out[i].1 += p.at(b, d) * my_exp[0];
            }
        }
    }
}

// =============================================================================================================
// EDGE RISK (Daniel, 2026-11-17, after the WHM-6R v JVN-10F study: a third of the Hydra Warhammer's losses were a
// Javelin charging it off the map; a 'Mech displaced off the battlefield is destroyed, Core p.113)
// =============================================================================================================
/// An enemy that has not moved yet and could still charge or jump on this unit: (unit, where, running MP, jumping MP,
/// piloting). A charge needs the CHARGES setting, a death from above the DFA setting.
fn would_be_chargers(b: &mut Battle, enemies: &[UnitId]) -> Vec<(UnitId, (i64, i64), i64, i64, i64)> {
    let (charges, dfas) = (b.cfg.b("CHARGES"), b.cfg.b("DFA"));
    if !(charges || dfas) {
        return Vec::new();
    }
    let alive: Vec<UnitId> = enemies.iter().copied().filter(|e| !b.is_destroyed(*e)).collect();
    alive
        .into_iter()
        .filter(|e| {
            let m = &b.units[*e];
            m.hex.is_some() && !m.moved_this_turn && !m.prone && !m.shutdown && !is_immobile(m)
        })
        .map(|e| {
            let m = &b.units[e];
            let run = if charges { crate::mech_state::compute_running_mp(m).max(0) } else { -1 };
            let jump = if dfas { crate::mech_state::compute_jump_mp(m).max(0) } else { 0 };
            (e, xy(b, e).unwrap(), run, jump, m.piloting)
        })
        .collect()
}

/// The chance that standing at `o` this unit is charged or jumped on (DFA) off the map this turn: the best hit chance of
/// any would-be charger that can reach a hex next to `o` from which the attack's push (attacker's hex -> target's hex,
/// as `charge.rs` / `dfa.rs` displace) leads off the board. Reach is counted in hexes (terrain ignored: the threat is
/// taken at its largest); the hit chance is the attack's to-hit number at its simplest: piloting + the attacker's
/// movement modifier (running +2 for a charge, jumping +3 for a DFA) + this spot's TMM. 0 on a spot no push can clear.
fn edge_risk(b: &Battle, o: &Opt, chargers: &[(UnitId, (i64, i64), i64, i64, i64)]) -> f64 {
    if chargers.is_empty() {
        return 0.0;
    }
    let mut p: f64 = 0.0;
    for d in 0..6i64 {
        // the attacker would stand on the neighbour in direction d and push the other way, (d + 3) mod 6
        let Some(n) = crate::movement_attacks::neighbour(&o.label, d).filter(|n| b.board.hexes.contains_key(n)) else { continue };
        if crate::movement_attacks::displacement(b, &o.label, (d + 3).rem_euclid(6)).0 != "off" {
            continue;
        }
        let n_xy = hex_geometry::parse_hex_label(&n).unwrap();
        for (_, e_xy, run, jump, piloting) in chargers {
            let dist = hex_distance(*e_xy, n_xy);
            if *run >= 0 && dist <= *run {
                p = p.max(crate::combat::hit_probability(piloting + 2 + o.tmm));
            }
            if *jump > 0 && dist <= *jump {
                p = p.max(crate::combat::hit_probability(piloting + 3 + o.tmm));
            }
        }
    }
    p
}

/// The movement pick for a Hydra unit and the note the log prints. `other` is the foe the engine named (used only where
/// the engine's own helpers want one).
pub fn choose_movement(b: &mut Battle, mover: UnitId, other: UnitId, moves_first: bool, standup_mp: Option<i64>, entry_edge: Option<&[String]>) -> (Option<Pick>, String) {
    // HYDRA_CHECK (playout::Witness): thinking must leave the battle exactly as it found it - no dice, no log, no state.
    // Not around the hand-off before any enemy is on the board: that is Gladiator's march, whose tie-break is a real,
    // seeded random choice (move_select::Ties), not thinking.
    let any_enemy_here = crate::forces::enemies_of(b, mover).into_iter().any(|e| b.units[e].hex.is_some());
    let witness = if any_enemy_here { crate::playout::Witness::take(b) } else { None };
    let out = choose_movement_inner(b, mover, other, moves_first, standup_mp, entry_edge);
    if let Some(w) = witness {
        w.check(b, &format!("Hydra's move choice for {}", b.units[mover].side_name.clone().unwrap_or_default()));
    }
    out
}

fn choose_movement_inner(b: &mut Battle, mover: UnitId, other: UnitId, moves_first: bool, standup_mp: Option<i64>, entry_edge: Option<&[String]>) -> (Option<Pick>, String) {
    let enemies: Vec<UnitId> = crate::forces::enemies_of(b, mover).into_iter().filter(|e| b.units[*e].hex.is_some()).collect();
    if enemies.is_empty() {
        // nobody to weigh yet (the enemy has not entered): the engine's march toward its edge
        let mut ties = move_select::Ties { recorded: None, missed: false };
        return move_select::choose(b, mover, other, moves_first, standup_mp, entry_edge, &mut ties);
    }
    let mut me = Side::new(b, mover, standup_mp.is_none());
    let exclude = move_options::occupied_hexes(b, mover, other);
    let (options, notes) = move_options::reduced_options(b, mover, &exclude, standup_mp, entry_edge);
    me.notes = notes;
    let prepared = move_options::prepare_options(b, mover, &options);
    if prepared.is_empty() {
        return (None, "no reachable spot".into());
    }
    let mut index: HashMap<(String, &'static str, &'static str, i64), usize> = HashMap::default();
    for (i, o) in prepared.iter().enumerate() {
        index.insert((o.label.clone(), o.facing_compass, o.mode, o.fc), i);
    }

    let (mine, theirs) = ledger(b, mover);
    let price = prices_with(&mine, &theirs, &Shape::of(b));
    let my_price = price.get(&mover).copied().unwrap_or(1.0);
    let guns: HashMap<UnitId, f64> = theirs.iter().map(|e| (e.unit, e.guns)).collect();

    // only the enemies that can matter this turn are asked about; never none
    let mut relevant: Vec<UnitId> = enemies.iter().copied().filter(|e| b.units[mover].hex.is_none() || crate::legate::can_matter(b, mover, *e)).collect();
    if relevant.is_empty() {
        let near = enemies.iter().copied().min_by_key(|e| match (xy(b, mover), xy(b, *e)) {
            (Some(m), Some(t)) => hex_distance(m, t),
            _ => 0,
        });
        relevant.extend(near);
    }

    let n = prepared.len();
    let my_exp = soft(me.exposure);
    let friends: Vec<UnitId> = mine.iter().map(|e| e.unit).filter(|u| *u != mover && b.units[*u].hex.is_some()).collect();
    // one exchange table per enemy weighed: (enemy, its price, what else it could shoot at, per option (dealt, received))
    let mut tables: Vec<(UnitId, f64, f64, Vec<(f64, f64)>)> = Vec::new();
    let mut memo = AttentionMemo::default();
    for &e in &relevant {
        let its_exp = soft(Side::new(b, e, true).exposure);
        let table = exchange(b, mover, e, &prepared, &index, &my_exp, &its_exp);
        let p_e = price.get(&e).copied().unwrap_or(1.0);
        // what else this enemy could be shooting at: its best friend-target (the attention share)
        let elsewhere = elsewhere_of(b, &mut memo, e, &friends, &price, &guns);
        tables.push((e, p_e, elsewhere, table));
    }
    // (gain, the enemy it is on, cost) of option i; `instead` swaps one enemy's line of the table for a modeled reply
    let weigh = |i: usize, instead: Option<(UnitId, (f64, f64))>| -> (f64, Option<UnitId>, f64) {
        let (mut gain, mut on, mut cost) = (0.0f64, None, 0.0f64);
        for (e, p_e, elsewhere, table) in &tables {
            let (dealt, received) = match instead {
                Some((r, x)) if r == *e => x,
                _ => table[i],
            };
            let g = p_e * dealt;
            if g > gain {
                gain = g;
                on = Some(*e);
            }
            let hurt = my_price * received;
            if hurt > 0.0 {
                cost += hurt * hurt / (hurt + elsewhere);
            }
        }
        (gain, on, cost)
    };
    // risk = the fall chance of getting there, priced; plus the chance of being charged or jumped off the map from there by an
    // enemy still to move, times this unit's whole remaining strength, priced. ALWAYS ON (Daniel, 2026-11-17: "Avoiding the
    // edge should be mandatory for Hydra with no way to turn it off"; the HYDRA_EDGE_RISK switch of that morning is gone)
    let chargers = would_be_chargers(b, &enemies);
    let my_whole = crate::attack_resolution::total_hp(&b.units[mover]).f();
    let risks: Vec<f64> = prepared.iter().map(|o| my_price * (me.psr_for_opt(b, o) + edge_risk(b, o, &chargers) * my_whole)).collect();
    // THE SCORE of a spot: what it does to my team's rate of exchange over a typical turn,
    //     (d0 + gain) / (r0 + cost + risk)
    // d0 / r0 = what my whole team (this unit included) deals / takes in a typical turn, priced. In a big force one
    // unit's trade is small next to d0 and r0, and the score asks "is this trade better than the team's average?". In a
    // duel d0 and r0 are this unit's own typical turn, which keeps the score from chasing a tiny free shot over a solid
    // trade. A side that waits scores d0 / r0, so stalling never beats a fair trade.
    let mean = |side: &[Entry]| side.iter().map(|e| price.get(&e.unit).copied().unwrap_or(1.0)).sum::<f64>() / side.len().max(1) as f64;
    let d0 = STEP_FIRE * mean(&theirs) * mine.iter().map(|e| e.guns).sum::<f64>();
    let r0 = STEP_FIRE * mean(&mine) * theirs.iter().map(|e| e.guns).sum::<f64>();
    let rate = |g: f64, c: f64, risk: f64| (d0 + g) / (r0 + c + risk).max(1e-9);
    let mut scored: Vec<(f64, usize)> = Vec::new();
    let mut ranked: Vec<(f64, usize)> = Vec::new();
    let mut cost = vec![0.0f64; n];
    let mut gains = vec![0.0f64; n];
    for i in 0..n {
        let (g, _, c) = weigh(i, None);
        cost[i] = c;
        gains[i] = g;
        if g > 0.0 {
            scored.push((rate(g, c, risks[i]), i));
        }
        ranked.push((rate(g, c, risks[i]), i));
    }
    ranked.sort_by(|x, y| y.0.partial_cmp(&x.0).unwrap().then(x.1.cmp(&y.1)));
    scored.sort_by(|x, y| y.0.partial_cmp(&x.0).unwrap().then(x.1.cmp(&y.1)));

    // THE REPLY: an enemy that has not moved will answer this move. For the best few spots (one per hex), the unmoved
    // enemy that weighs most on them (the rival) is given its best answer, and the spots are scored again against it.
    let mut reply_note = String::new();
    let mut best: Option<(f64, usize, Option<(UnitId, (f64, f64))>)> = scored.first().map(|(s, i)| (*s, *i, None));
    // S5a: the judged lines of the chosen spot (per enemy (dealt, received), per enemy "elsewhere"), for the note
    let mut best_lines: Option<(HashMap<UnitId, (f64, f64)>, HashMap<UnitId, f64>)> = None;
    let unmoved: Vec<UnitId> = relevant.iter().copied().filter(|e| !(b.units[*e].moved_this_turn || is_immobile(&b.units[*e]))).collect();
    let depth = (REPLY_BUDGET / relevant.len().max(1)).min(REPLY_MAX);
    if !(b.cfg.has("HYDRA_PLAYOUT") && b.cfg.s("HYDRA_PLAYOUT") == "reply") {
        // S5a, THE MOVEMENT PLAY-OUT (INTEGRATION__HYDRA.md Section 6), in place of the reply below.
        if !scored.is_empty() || tables.iter().all(|t| t.2 <= 0.0) {
            let alone = tables.iter().all(|t| t.2 <= 0.0);
            // every spot in rank order, one per hex; the play-out keeps as many as its budget allows
            let mut short: Vec<usize> = Vec::new();
            for (_, i) in if alone { &ranked } else { &scored } {
                if !short.iter().any(|j| prepared[*j].hex_xy() == prepared[*i].hex_xy()) {
                    short.push(*i);
                    if short.len() == PLAYOUT_BUDGET {
                        break;
                    }
                }
            }
            let po = playout(b, &mut memo, mover, &friends, &prepared, &short, &tables, &price, &guns, my_price, &my_exp);
            if let Some((note, scored_short)) = po {
                best = None;
                for (i, lines, elsewhere) in scored_short {
                    let (g, _, c) = weigh_lines(&tables, &lines, &elsewhere, my_price, i);
                    let sc = rate(g, c, risks[i]);
                    if best.map_or(true, |(bs, _, _)| sc > bs) {
                        best = Some((sc, i, None));
                        best_lines = Some((lines, elsewhere));
                    }
                }
                reply_note = note;
            }
        }
    } else if !unmoved.is_empty() && depth >= 2 && !scored.is_empty() {
        let mut short: Vec<usize> = Vec::new();
        // a unit alone (no friend any weighed enemy could turn on) may also stand where it deals nothing
        let alone = tables.iter().all(|t| t.2 <= 0.0);
        for (_, i) in if alone { &ranked } else { &scored } {
            if !short.iter().any(|j| prepared[*j].hex_xy() == prepared[*i].hex_xy()) {
                short.push(*i);
                if short.len() == depth {
                    break;
                }
            }
        }
        let weight_of = |e: UnitId| -> f64 {
            let (_, p_e, _, table) = tables.iter().find(|t| t.0 == e).unwrap();
            short.iter().map(|i| p_e * table[*i].0 + my_price * table[*i].1).sum()
        };
        let rival = unmoved.iter().copied().max_by(|x, y| weight_of(*x).partial_cmp(&weight_of(*y)).unwrap().then(y.cmp(x))).unwrap();
        let p_r = price.get(&rival).copied().unwrap_or(1.0);
        let mut them = Side::new(b, rival, true);
        let rival_exp = soft(them.exposure);
        let replies = move_select::opponent_options(b, rival, &mut them);
        let mut ev2 = MoveEvaluator::new(b, rival, mover).with_c3(b);
        let prepared2 = ev2.prepare(b, &replies);
        best = None;
        for &i in &short {
            let o = &prepared[i];
            // the rival's answer: the most (damage on me at my price - damage on it at its price), seen from its seat
            let mut answer: Option<(f64, (f64, f64))> = None;
            for c in ev2.evaluate(b, &o.label, o.facing_compass, o.fc, o.mode, o.mp_spent, &prepared2, true) {
                let (hits_me, hits_it) = (c.dealt * my_exp[side_ix(c.side_on_defender)], c.received * rival_exp[side_ix(c.side_on_mover)]);
                let v = my_price * hits_me - p_r * hits_it;
                if answer.map_or(true, |(a, _)| v > a) {
                    answer = Some((v, (hits_it, hits_me)));
                }
            }
            let instead = Some((rival, answer.map_or((0.0, 0.0), |(_, x)| x)));
            let (g, _, c) = weigh(i, instead);
            let s = rate(g, c, risks[i]);
            if best.map_or(true, |(bs, _, _)| s > bs) {
                best = Some((s, i, instead));
            }
        }
        reply_note = format!("; {} spots re-scored against {}'s best answer", short.len(), b.units[rival].side_name.clone().unwrap_or_default());
    }
    // S4, MOVEMENT ATTACKS (switch HYDRA_MOVEMENT_ATTACKS, session 25): a charge or a death from above on an enemy that
    // has already moved (or cannot move; Core pp.78-79), priced like any other spot: its exchange with that enemy is the
    // attack's expected damage both ways (self-damage and a missed DFA's fall included, movement_attacks::values) plus
    // the ranged fire from the attack hex; every other weighed enemy's line is the Oracle's at the attack hex.
    if entry_edge.is_none() && !(b.cfg.has("HYDRA_MOVEMENT_ATTACKS") && !b.cfg.b("HYDRA_MOVEMENT_ATTACKS")) {
        let normal = best.map(|(s, _, _)| s);
        if let Some((sc, pick, note)) = movement_attack(b, mover, &mut me, standup_mp, &tables, my_price, &my_exp, d0, r0) {
            if normal.map_or(true, |ns| sc > ns) {
                return (Some(pick), format!("Hydra: {} - rate {:.3} beats {}", note, sc, normal.map_or("nothing".to_string(), |ns| format!("{:.3}", ns))));
            }
        }
    }
    // WAITING (switch HYDRA_WAITING, session 25): the Mover never refuses battle by default. With the switch, when the best
    // trade on offer is worse than the team's typical turn (its rate below d0 / r0) and a friend is still coming, the unit
    // may take a spot that deals nothing, scored like any other ((d0 + 0) / (r0 + cost + risk): only a spot no weighed
    // enemy can punish much beats the bad trade); among equals, the one nearest a coming friend. At most MAX_WAITS turns in
    // a row, so the battle still gets fought.
    if entry_edge.is_none() && !(b.cfg.has("HYDRA_WAITING") && !b.cfg.b("HYDRA_WAITING")) {
        if let Some((best_rate, _, _)) = best {
            let turn = b.units[mover].turn_number;
            let streak = match b.hydra.waited.get(&mover) {
                Some(&(t, k)) if t == turn => k - 1,
                Some(&(t, k)) if t == turn - 1 => k,
                _ => 0,
            };
            if best_rate < d0 / r0.max(1e-9) && streak < MAX_WAITS {
                let (coming, at) = coming_friends(b, mover, &enemies);
                if coming {
                    let near = |i: usize| at.iter().map(|p| hex_distance(prepared[i].hex_xy(), *p)).min().unwrap_or(0);
                    let mut hold: Option<(f64, i64, usize)> = None;
                    for i in 0..n {
                        if gains[i] > 0.0 {
                            continue;
                        }
                        let (r, d) = (rate(0.0, cost[i], risks[i]), near(i));
                        if hold.map_or(true, |(hr, hd, _)| r > hr + 1e-12 || ((r - hr).abs() <= 1e-12 && d < hd)) {
                            hold = Some((r, d, i));
                        }
                    }
                    if let Some((r, _, i)) = hold {
                        if r > best_rate {
                            b.hydra.waited.insert(mover, (turn, streak + 1));
                            let note = format!("Hydra: waits for its friends - rate {:.3} holding beats {:.3}, the best trade (team {:.1} / {:.1}; wait {} of {})", r, best_rate, d0, r0, streak + 1, MAX_WAITS);
                            return (Some(prepared[i].pick()), note);
                        }
                    }
                }
            }
        }
    }
    if let Some((score, i, instead)) = best {
        let o = &prepared[i];
        let (g, on, c) = match &best_lines {
            Some((lines, elsewhere)) => weigh_lines(&tables, lines, elsewhere, my_price, i),
            None => weigh(i, instead),
        };
        let on = on.map_or("nobody".to_string(), |e| b.units[e].side_name.clone().unwrap_or_default());
        let note = format!("Hydra: rate {:.3} = (team {:.1} + gain {:.2} on {}) / (team {:.1} + cost {:.2} + risk {:.2}) ({} of {} enemies weighed, {} spots{})", score, d0, g, on, r0, c, risks[i], relevant.len(), enemies.len(), n, reply_note);
        return (Some(o.pick()), note);
    }

    // no spot deals damage: close on the highest-priced enemy among the nearest, by the least costly route
    let m_xy = xy(b, mover);
    let goal = enemies
        .iter()
        .copied()
        .max_by(|x, y| {
            let key = |e: UnitId| price.get(&e).copied().unwrap_or(1.0) / (1.0 + m_xy.map_or(0, |m| hex_distance(m, xy(b, e).unwrap())) as f64);
            key(*x).partial_cmp(&key(*y)).unwrap().then(y.cmp(x))
        })
        .unwrap();
    let goal_xy = xy(b, goal).unwrap();
    let goal_name = b.units[goal].side_name.clone().unwrap_or_default();
    if let Some(o) = move_select::closing_fallback(b, mover, goal, &me, &prepared, goal_xy, &|_| 0.0, None) {
        return (Some(o.pick()), format!("Hydra: no spot deals damage - closes on {}", goal_name));
    }
    let mut pick: Option<(f64, usize)> = None;
    for i in 0..n {
        let o = &prepared[i];
        let v = -(hex_distance(o.hex_xy(), goal_xy) as f64) - cost[i] - my_price * me.psr_for_opt(b, o) + 0.01 * o.tmm as f64;
        if pick.map_or(true, |(s, _)| v > s) {
            pick = Some((v, i));
        }
    }
    let o = &prepared[pick.unwrap().1];
    (Some(o.pick()), format!("Hydra: no spot deals damage - nearest safe spot to {}", goal_name))
}

// =============================================================================================================
// S4: MOVEMENT ATTACKS (charge, death from above)
// =============================================================================================================
/// The best charge or death from above of this move, in Hydra's currency: (rate, the pick, a note). None when no
/// weighed enemy can be attacked or no attack deals anything. The rate is the Mover's own score,
/// (d0 + gain) / (r0 + cost + risk), with the target's line replaced by the attack's exchange.
#[allow(clippy::too_many_arguments)]
fn movement_attack(b: &mut Battle, mover: UnitId, me: &mut Side, standup_mp: Option<i64>, tables: &[(UnitId, f64, f64, Vec<(f64, f64)>)], my_price: f64, my_exp: &[f64; 4], d0: f64, r0: f64) -> Option<(f64, Pick, String)> {
    if !(b.cfg.b("CHARGES") || b.cfg.b("DFA")) {
        return None;
    }
    let targets: Vec<UnitId> = tables.iter().map(|t| t.0).filter(|e| {
        let moved = b.units[*e].moved_this_turn;
        crate::move_attacks::can_be_attacked(b, *e, moved)
    }).collect();
    if targets.is_empty() {
        return None;
    }
    let mut index = crate::move_attacks::MoverIndex::new(b, mover, standup_mp, &mut me.notes);
    let mut best: Option<(f64, Pick, String)> = None;
    for &t in &targets {
        let pose = crate::move_attacks::pose_of(b, t);
        let t_exp = soft(Side::new(b, t, true).exposure);
        let target_args = (b.units[t].hex.clone().unwrap(), b.units[t].facing.clone(), b.units[t].move_fc, b.units[t].move_mode.clone(), b.units[t].mp_spent);
        let mut ev = MoveEvaluator::new(b, mover, t).with_c3(b);
        // no gate: every attack state is priced in full (the gate is Gladiator's "beats its best ordinary shot")
        let options = crate::move_attacks::scored_options(b, mover, t, &pose, &index, &mut ev, my_exp, &t_exp, &|_: &Battle, _: &str, _: i64, _: &str, _: &str, _: i64| 0.0, crate::move_attacks::BestMode::Lazy(&[], t_exp), &target_args, &|_: f64, _: f64, _: f64, _: f64, _: f64| 0.0, &["charge", "dfa"]);
        for (_, cand, state, what) in options {
            // the attack's line with its target, damage multiplied by where it lands (as `exchange` does)
            let dealt = cand.dealt * t_exp[side_ix(cand.side_on_defender)];
            let received = cand.received * my_exp[side_ix(cand.side_on_mover)];
            let mut lines: HashMap<UnitId, (f64, f64)> = HashMap::default();
            lines.insert(t, (dealt, received));
            // every other weighed enemy, seen from the attack hex
            let (x, y) = hex_geometry::parse_hex_label(&state.hex).unwrap();
            let key: crate::move_options::StateKey = (x, y, hex_geometry::compass_to_facing(&state.facing).unwrap(), state.fc, crate::move_options::mode_str(&state.mode), state.mp_spent);
            let one = move_options::prepare_options(b, mover, &[key]);
            if one.is_empty() {
                continue;
            }
            let mut idx: HashMap<(String, &'static str, &'static str, i64), usize> = HashMap::default();
            idx.insert((one[0].label.clone(), one[0].facing_compass, one[0].mode, one[0].fc), 0);
            for (e, _, _, _) in tables {
                if *e == t {
                    continue;
                }
                let e_exp = soft(Side::new(b, *e, true).exposure);
                let line = exchange(b, mover, *e, &one, &idx, my_exp, &e_exp);
                lines.insert(*e, line[0]);
            }
            let (g, _, c) = weigh_lines_only(tables, &lines, my_price);
            let risk = my_price * me.psr_for_pick(b, &state);
            let sc = (d0 + g) / (r0 + c + risk).max(1e-9);
            if best.as_ref().map_or(true, |(bs, _, _)| sc > *bs) {
                let name = b.units[t].side_name.clone().unwrap_or_default();
                best = Some((sc, state.clone(), format!("{} on {} (gain {:.2}, cost {:.2}, risk {:.2})", what, name, g, c, risk)));
            }
        }
    }
    index.release();
    best
}

/// (gain, cost) of a spot from a full set of lines (one per weighed enemy), the tables' own "elsewhere" kept.
fn weigh_lines_only(tables: &[(UnitId, f64, f64, Vec<(f64, f64)>)], lines: &HashMap<UnitId, (f64, f64)>, my_price: f64) -> (f64, Option<UnitId>, f64) {
    let (mut gain, mut on, mut cost) = (0.0f64, None, 0.0f64);
    for (e, p_e, els, _) in tables {
        let (dealt, received) = lines.get(e).copied().unwrap_or((0.0, 0.0));
        let g = p_e * dealt;
        if g > gain {
            gain = g;
            on = Some(*e);
        }
        let hurt = my_price * received;
        if hurt > 0.0 {
            cost += hurt * hurt / (hurt + els);
        }
    }
    (gain, on, cost)
}

// =============================================================================================================
// S5a: THE MOVEMENT PLAY-OUT (INTEGRATION__HYDRA.md Section 6; groundwork in playout.rs)
// =============================================================================================================
/// Candidate spots of the mover played out (the top K, one per hex): K = PLAYOUT_BUDGET / responders, so a duel (one
/// responder) looks as wide as the old reply and a crowded move about as costly. (First cut K = 8 flat lost the
/// Griffin duel 28 - 33 where the reply's 64 spots won 38 - 26.)
const PLAYOUT_BUDGET: usize = 64;
/// Responders: units still to move that can matter, nearest to the mover first, at most this many.
const PLAYOUT_RESPONDERS: usize = 3;

/// (gain, the enemy it is on, cost) of option `i`, with judged lines where the play-out gave them: `lines` replaces an
/// enemy's (dealt, received) at its final pose, `elsewhere` its "what else it could shoot at" from the final picture.
fn weigh_lines(tables: &[(UnitId, f64, f64, Vec<(f64, f64)>)], lines: &HashMap<UnitId, (f64, f64)>, elsewhere: &HashMap<UnitId, f64>, my_price: f64, i: usize) -> (f64, Option<UnitId>, f64) {
    let (mut gain, mut on, mut cost) = (0.0f64, None, 0.0f64);
    for (e, p_e, els, table) in tables {
        let (dealt, received) = lines.get(e).copied().unwrap_or(table[i]);
        let g = p_e * dealt;
        if g > gain {
            gain = g;
            on = Some(*e);
        }
        let hurt = my_price * received;
        if hurt > 0.0 {
            let els = elsewhere.get(e).copied().unwrap_or(*els);
            cost += hurt * hurt / (hurt + els);
        }
    }
    (gain, on, cost)
}

/// One responder, prepared once per decision: its reachable spots, seen against its counterpart (an enemy answers the
/// mover; a friend answers the weighed enemy nearest it).
struct Responder {
    unit: UnitId,
    enemy: bool,
    counterpart: UnitId,
    ev: MoveEvaluator,
    spots: Vec<Opt>,
    exp: [f64; 4],
}

/// THE PLAY-OUT. For each candidate spot of the mover: the responders, in the order they will move (Battle::move_queue),
/// each pick their best answer against the picture so far and are POSED there; the POSITION JUDGE then reads the final
/// picture: an enemy responder's line is the exchange with the mover from where it ended, and every weighed enemy's
/// "elsewhere" (the friend it could shoot instead) is worked out again from the final positions - so a friend arriving
/// near draws fire. Every pose is undone before the next spot. None when nobody is left to respond.
/// Returns the note and, per candidate spot: (option index, judged lines, judged "elsewhere").
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn playout(b: &mut Battle, memo: &mut AttentionMemo, mover: UnitId, friends: &[UnitId], prepared: &[Opt], short: &[usize], tables: &[(UnitId, f64, f64, Vec<(f64, f64)>)], price: &HashMap<UnitId, f64>, guns: &HashMap<UnitId, f64>, my_price: f64, my_exp: &[f64; 4]) -> Option<(String, Vec<(usize, HashMap<UnitId, (f64, f64)>, HashMap<UnitId, f64>)>)> {
    let weighed: Vec<UnitId> = tables.iter().map(|t| t.0).collect();
    let m_xy = xy(b, mover)?;
    // THE RESPONDERS: still to move, on the board, free to move (prone, immobile, stuck: fixed, never a responder)
    let queue: Vec<UnitId> = crate::playout::move_queue(b).to_vec();
    let mut chosen: Vec<(i64, usize, UnitId, bool)> = Vec::new();
    for (pos, &u) in queue.iter().enumerate() {
        let m = &b.units[u];
        if u == mover || m.hex.is_none() || m.moved_this_turn || m.prone || is_immobile(m) || matches!(m.stuck, Some(Some(_))) {
            continue;
        }
        let enemy = weighed.contains(&u);
        let is_friend = m.team == b.units[mover].team;
        if !enemy && !is_friend {
            continue; // an enemy that cannot matter to this move
        }
        if is_friend && !weighed.iter().any(|e| crate::legate::can_matter(b, u, *e)) {
            continue;
        }
        let d = hex_distance(m_xy, xy(b, u).unwrap());
        chosen.push((d, pos, u, enemy));
    }
    chosen.sort_by_key(|c| (c.0, c.1));
    chosen.truncate(PLAYOUT_RESPONDERS);
    if chosen.is_empty() {
        return None;
    }
    chosen.sort_by_key(|c| c.1); // back to the order they move in
    let mut responders: Vec<Responder> = Vec::new();
    for &(_, _, u, enemy) in &chosen {
        let counterpart = if enemy {
            mover
        } else {
            let f_xy = xy(b, u).unwrap();
            *weighed.iter().min_by_key(|e| (hex_distance(f_xy, xy(b, **e).unwrap()), **e)).unwrap()
        };
        let mut side = Side::new(b, u, true);
        let exp = soft(side.exposure);
        let options = move_select::opponent_options(b, u, &mut side);
        let ev = MoveEvaluator::new(b, u, counterpart).with_c3(b);
        let spots = ev.prepare(b, &options);
        responders.push(Responder { unit: u, enemy, counterpart, ev, spots, exp });
    }
    let names: Vec<String> = responders.iter().map(|r| b.units[r.unit].side_name.clone().unwrap_or_default()).collect();

    let spots = (PLAYOUT_BUDGET / responders.len()).max(2);
    let short = &short[..short.len().min(spots)];
    let mut out = Vec::new();
    for &i in short {
        let o = &prepared[i];
        let mut poses = crate::playout::Poses::new();
        let mut lines: HashMap<UnitId, (f64, f64)> = HashMap::default();
        for r in responders.iter_mut() {
            // where the counterpart stands in the picture so far
            let (c_label, c_facing, c_fc, c_mode, c_mp, c_exp, p_c) = if r.enemy {
                (o.label.clone(), o.facing_compass.to_string(), o.fc, o.mode.to_string(), o.mp_spent, *my_exp, my_price)
            } else {
                let c = &b.units[r.counterpart];
                (c.hex.clone().unwrap(), c.facing.clone(), c.move_fc, c.move_mode.clone(), c.mp_spent, soft(Side::new(b, r.counterpart, true).exposure), price.get(&r.counterpart).copied().unwrap_or(1.0))
            };
            let p_r = price.get(&r.unit).copied().unwrap_or(1.0);
            // hexes taken: other units where they stand now, the poses so far, and the mover's candidate spot
            let taken: Vec<String> = (0..b.units.len()).filter(|u| *u != r.unit && *u != mover).filter_map(|u| b.units[u].hex.clone()).chain(std::iter::once(o.label.clone())).collect();
            let mut answer: Option<(f64, crate::move_eval::Candidate, (f64, f64))> = None;
            for c in r.ev.evaluate(b, &c_label, &c_facing, c_fc, &c_mode, c_mp, &r.spots, true) {
                if taken.contains(&c.hex) {
                    continue;
                }
                // (damage it deals its counterpart, damage it takes), each where it lands
                let deals = c.dealt * c_exp[side_ix(c.side_on_defender)];
                let takes = c.received * r.exp[side_ix(c.side_on_mover)];
                let v = p_c * deals - p_r * takes;
                if answer.as_ref().map_or(true, |(a, _, _)| v > *a) {
                    answer = Some((v, c, (deals, takes)));
                }
            }
            if let Some((_, c, (deals, takes))) = answer {
                if r.enemy {
                    // the mover's line with this enemy: (what I deal it, what it deals me)
                    lines.insert(r.unit, (takes, deals));
                }
                let pose = crate::playout::Pose { hex: Some(c.hex.clone()), facing: c.facing.to_string(), move_mode: c.mode.to_string(), move_fc: c.fc, mp_spent: c.mp_spent, movement_heat: c.movement_heat, moved_this_turn: true };
                poses.pose(b, r.unit, &pose);
            }
        }
        // THE POSITION JUDGE: every weighed enemy's "what else could it shoot at", from the final picture
        let mut elsewhere: HashMap<UnitId, f64> = HashMap::default();
        for &e in &weighed {
            let els = elsewhere_of(b, memo, e, friends, price, guns);
            elsewhere.insert(e, els);
        }
        poses.restore(b);
        out.push((i, lines, elsewhere));
    }
    let note = format!("; play-out of {} spots, responders {}", short.len(), names.join(", "));
    Some((note, out))
}

// =============================================================================================================
// S3 MOVE ORDER: which of a Hydra side's units moves next (switch HYDRA_MOVE_ORDER = "stake", session 25)
// =============================================================================================================
/// The engine asks a side for one unit at a time (Core p.41: sides alternate, the side that lost Initiative first). The
/// rule: LEAST TO LOSE FIRST, DECIDERS LAST. A unit's STAKE this turn is the priced damage that can flow through it:
///     sum over enemies on the board of  reach x (enemy guns x my price + my guns x enemy price)
/// where reach is `range_factor` of the distance left after the unit's own best move (running or jumping MP). A unit far
/// from everything has little to lose or win wherever it goes, so it commits first; the units in the thick of it move
/// last, when the most enemies have shown where they stand. A unit not on the board has no stake and goes first (as in
/// the engine's own rule). Ties: the earlier candidate (roster order). Only reads the battle: guns are the ledger's
/// without raising the best seen, and prices are worked out once per team per Movement Phase.
pub fn move_pick(b: &mut Battle, candidates: &[UnitId]) -> UnitId {
    let team = b.units[candidates[0]].team.clone().unwrap_or_default();
    if !b.hydra.order.contains_key(&team) {
        let (mine, theirs) = ledger_as(b, candidates[0], false);
        let price = prices_with(&mine, &theirs, &Shape::of(b));
        let worth: HashMap<UnitId, (f64, f64)> = mine.iter().chain(theirs.iter()).map(|e| (e.unit, (e.guns, price.get(&e.unit).copied().unwrap_or(1.0)))).collect();
        b.hydra.order.insert(team.clone(), worth);
    }
    let enemies: Vec<UnitId> = crate::forces::enemies_of(b, candidates[0]).into_iter().filter(|e| b.units[*e].hex.is_some()).collect();
    let worth = &b.hydra.order[&team];
    let stake = |u: UnitId| -> f64 {
        let Some(at) = xy(b, u) else { return 0.0 };
        let reach = crate::mech_state::compute_running_mp(&b.units[u]).max(crate::mech_state::compute_jump_mp(&b.units[u]));
        let (my_guns, my_price) = worth.get(&u).copied().unwrap_or((MIN_GUNS, 1.0));
        let mut sum = 0.0;
        for &e in &enemies {
            let Some(there) = xy(b, e) else { continue };
            let (its_guns, its_price) = worth.get(&e).copied().unwrap_or((MIN_GUNS, 1.0));
            let r = range_factor((hex_distance(at, there) - reach).max(0));
            sum += r * (its_guns * my_price + my_guns * its_price);
        }
        sum
    };
    let mut best = candidates[0];
    let mut best_v = stake(best);
    for &u in &candidates[1..] {
        let v = stake(u);
        if v < best_v {
            best = u;
            best_v = v;
        }
    }
    best
}

/// Is S3 on for this side's pick? Every candidate is Hydra's and the switch says "stake".
pub fn picks_move_order(b: &Battle, candidates: &[UnitId]) -> bool {
    !(b.cfg.has("HYDRA_MOVE_ORDER") && b.cfg.s("HYDRA_MOVE_ORDER") == "index") && candidates.iter().all(|u| b.units[*u].bot == "hydra")
}

// =============================================================================================================
// FIRE PLAN: who shoots whom, for the whole team at once
// =============================================================================================================
/// Damage past this multiple of a target's remaining life counts for nothing (dice are dice: aim a little over).
const OVERKILL: f64 = 1.5;

fn plan_fire(b: &mut Battle, team: &str) -> HashMap<UnitId, Option<UnitId>> {
    let shooters: Vec<UnitId> = crate::forces::standing(b).into_iter().filter(|u| b.units[*u].team.as_deref() == Some(team) && b.units[*u].bot == "hydra" && b.units[*u].hex.is_some()).collect();
    let mut plan: HashMap<UnitId, Option<UnitId>> = HashMap::default();
    let Some(&first) = shooters.first() else { return plan };
    let (mine, theirs) = ledger(b, first);
    let price = prices_with(&mine, &theirs, &Shape::of(b));
    let mut room: HashMap<UnitId, f64> = theirs.iter().map(|e| (e.unit, OVERKILL * e.life)).collect();
    // the oracle: each shooter's expected damage on each enemy it can hit
    let mut shots: Vec<(UnitId, Vec<(UnitId, f64)>)> = Vec::new();
    for &u in &shooters {
        let mut row = Vec::new();
        for e in crate::bot_targets::candidates(b, u) {
            if let Some((_, dmg, _)) = crate::bot_targets::dry_declare_as(b, u, e, false) {
                if dmg > 0.0 {
                    row.push((e, dmg));
                }
            }
        }
        shots.push((u, row));
    }
    // the biggest priced bite first; each takes room off its target, so spare guns move on
    let mut open: Vec<usize> = (0..shots.len()).collect();
    while !open.is_empty() {
        let mut best: Option<(f64, usize, UnitId, f64)> = None;
        for &s in &open {
            for &(e, dmg) in &shots[s].1 {
                let counted = dmg.min(room.get(&e).copied().unwrap_or(0.0).max(0.0));
                let v = price.get(&e).copied().unwrap_or(1.0) * (counted + 0.01 * dmg);
                if best.map_or(true, |(bv, _, _, _)| v > bv) {
                    best = Some((v, s, e, dmg));
                }
            }
        }
        match best {
            Some((_, s, e, dmg)) => {
                // C3: what the network added to this shot (the same declaration without it), for the ledger's bonus
                let u = shots[s].0;
                if crate::c3::link(b, u).is_some() {
                    let off = crate::c3::without(|| crate::bot_targets::dry_declare_as(b, u, e, false)).map_or(0.0, |x| x.1);
                    let tally = b.hydra.c3_shots.entry(u).or_insert((0.0, 0.0));
                    tally.0 += dmg;
                    tally.1 += off;
                }
                plan.insert(shots[s].0, Some(e));
                *room.entry(e).or_insert(0.0) -= dmg;
                open.retain(|x| *x != s);
            }
            None => {
                // nothing to hit: the engine's default (the nearest enemy), so the phase's bookkeeping still runs
                for &s in &open {
                    let u = shots[s].0;
                    let t = crate::forces::choose_target(b, u, true, false);
                    plan.insert(u, t);
                }
                open.clear();
            }
        }
    }
    plan
}

/// The enemy a Hydra unit fires at this phase: its line of the team's plan (made at the first ask of the phase).
pub fn choose_target(b: &mut Battle, attacker: UnitId) -> Option<UnitId> {
    let team = b.units[attacker].team.clone().unwrap_or_default();
    if !b.hydra.fire.contains_key(&team) {
        let plan = plan_fire(b, &team);
        b.hydra.fire.insert(team.clone(), plan);
    }
    match b.hydra.fire[&team].get(&attacker) {
        Some(t) => *t,
        None => crate::forces::choose_target(b, attacker, true, false),
    }
}

/// SPOTTING (Core p.70; spotting.rs; 2026-11-21, Daniel: "Update Hydra to incorporate the new rules"). Hydra plans the
/// team's spots together, as it plans the team's fire (`plan_fire`), and prices them the same way: by the damage the team
/// deals, each point at its target's price.
///   * every Hydra unit's best priced shot is known (`best_shot`: the engine's own dry declaration, against each enemy);
///   * a spot of enemy E by unit U is worth: U's best shot with the spotter's +1 on it (or nothing, if U holds its fire),
///     less U's best shot now; plus, for each Hydra friend with no line of sight to E, how much better E, now hit
///     indirectly (the +1 on that fire too when U also fires), is than that friend's best shot now;
///   * the best spot is added, the shots it changes are updated, and the next is sought, until no spot gains more
///     than 1% of the spotter's own shot (so a tie never costs a shot). A friend whose best shot a spot has already
///     raised gains nothing from a second spot of the same target unless that one gives it a lower modifier.
/// The spots are put in `b.spots` for the asking and taken out again; the engine declares them in initiative order
/// (`spotting::declare_spotting` asks each unit; `choose_spot` answers from the plan). Only Hydra friends are counted:
/// theirs is the fire plan this feeds (a friend of another bot picks its own target).
fn plan_spots(b: &mut Battle, team: &str) -> HashMap<UnitId, (UnitId, bool)> {
    let mut plan: HashMap<UnitId, (UnitId, bool)> = HashMap::default();
    let units: Vec<UnitId> = crate::forces::standing(b).into_iter().filter(|&u| b.units[u].team.as_deref() == Some(team) && b.units[u].bot == "hydra" && b.units[u].hex.is_some()).collect();
    // who could spot whom (an enemy it sees that a friend without line of sight could hit indirectly)
    let mut options: Vec<(UnitId, UnitId)> = Vec::new();
    for &u in &units {
        if crate::spotting::spot_of(b, u).is_some() || !crate::spotting::can_spot(b, u) {
            continue; // a TAG spot already, or it may not spot
        }
        for c in crate::spotting::spot_candidates(b, u) {
            options.push((u, c.0));
        }
    }
    if options.is_empty() {
        return plan;
    }
    let (mine, theirs) = ledger(b, units[0]);
    let price = prices_with(&mine, &theirs, &Shape::of(b));
    let worth = |e: UnitId| price.get(&e).copied().unwrap_or(1.0);
    // each unit's best priced shot among its targets now (what the team fire plan could get from it)
    let best_shot = |b: &mut Battle, who: UnitId| -> f64 {
        let mut best = 0.0f64;
        for e in crate::bot_targets::candidates(b, who) {
            if let Some((_, dmg, _)) = crate::bot_targets::dry_declare_as(b, who, e, false) {
                best = best.max(worth(e) * dmg);
            }
        }
        best
    };
    let mut shot: HashMap<UnitId, f64> = HashMap::default();
    for &u in &units {
        let v = best_shot(b, u);
        shot.insert(u, v);
    }
    let added_before = b.spots.len();
    loop {
        // (gain, spotter, target, fires, the friends' new best shots)
        let mut best: Option<(f64, UnitId, UnitId, bool, Vec<(UnitId, f64)>)> = None;
        for &(u, e) in &options {
            if plan.contains_key(&u) {
                continue;
            }
            for fires in [true, false] {
                b.spots.push(crate::spotting::Spot { spotter: u, target: e, fires, tag: false });
                let own = if fires { best_shot(b, u) } else { 0.0 };
                let mut gain = own - shot[&u];
                let mut raised = Vec::new();
                for &f in &units {
                    if f == u || plan.get(&f).is_some_and(|s| !s.1) || !matches!(crate::spotting::sight(b, f, e), Some((false, _))) {
                        continue; // itself, a friend holding fire to spot, or one that sees E (it fires directly)
                    }
                    if let Some((_, dmg, _)) = crate::bot_targets::dry_declare_as(b, f, e, false) {
                        let v = worth(e) * dmg;
                        if v > shot[&f] {
                            gain += v - shot[&f];
                            raised.push((f, v));
                        }
                    }
                }
                b.spots.pop();
                if gain > 0.01 * shot[&u].max(1e-9) && best.as_ref().map_or(true, |x| gain > x.0) {
                    best = Some((gain, u, e, fires, raised));
                }
            }
        }
        let Some((_, u, e, fires, raised)) = best else { break };
        plan.insert(u, (e, fires));
        b.spots.push(crate::spotting::Spot { spotter: u, target: e, fires, tag: false });
        shot.insert(u, if fires { best_shot(b, u) } else { 0.0 });
        for (f, v) in raised {
            shot.insert(f, v);
        }
    }
    b.spots.truncate(added_before);
    plan
}

/// The spot a Hydra unit declares this phase, if any: its line of the team's spotting plan (made at the first ask).
pub fn choose_spot(b: &mut Battle, u: UnitId) -> Option<(UnitId, bool)> {
    let team = b.units[u].team.clone().unwrap_or_default();
    if !b.hydra.spots.contains_key(&team) {
        let plan = plan_spots(b, &team);
        b.hydra.spots.insert(team.clone(), plan);
    }
    b.hydra.spots[&team].get(&u).copied()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn forecast_is_even_for_equal_sides_and_favors_the_stronger() {
        let a = [(100.0, 20.0), (100.0, 20.0)];
        assert!(forecast(&a, &a).abs() < 1e-9);
        let weak = [(100.0, 20.0)];
        assert!(forecast(&a, &weak) > 0.0);
        assert!(forecast(&weak, &a) < 0.0);
    }

    #[test]
    fn a_c3_master_is_priced_for_the_network_it_carries() {
        // four equal 'Mechs, a 20% network bonus each; unit 0 is the Master the three Slaves depend on
        let net = |anchor| Some(Net { bonus: 4.0, group: 0, anchor, anchor_full: 100.0 });
        let mine = [
            Entry { unit: 0, life: 100.0, guns: 24.0, net: net(None) },
            Entry { unit: 1, life: 100.0, guns: 24.0, net: net(Some(0)) },
            Entry { unit: 2, life: 100.0, guns: 24.0, net: net(Some(0)) },
            Entry { unit: 3, life: 100.0, guns: 24.0, net: net(Some(0)) },
        ];
        // a stronger enemy, so the Forecast has a winner (with even sides both fall in the same step and every margin is 0)
        let theirs: Vec<Entry> = (4..8).map(|u| Entry { unit: u, life: 140.0, guns: 24.0, net: None }).collect();
        for shape in [Shape::FIRST, Shape::CALIBRATED] {
            let p = prices_with(&mine, &theirs, &shape);
            assert!(p[&0] > p[&1], "{:?} {:?}", shape, p);
        }
        // and with no network the four are priced alike
        let plain: Vec<Entry> = mine.iter().map(|e| Entry { net: None, guns: 20.0, ..*e }).collect();
        let p = prices_with(&plain, &theirs, &Shape::CALIBRATED);
        assert!((p[&0] - p[&1]).abs() < 1e-9, "{:?}", p);
    }

    #[test]
    fn the_nearly_dead_big_gun_is_priced_highest() {
        let e = |unit, life, guns| Entry { unit, life, guns, net: None };
        let mine = [e(0, 100.0, 20.0), e(1, 100.0, 20.0)];
        let theirs = [e(2, 100.0, 20.0), e(3, 20.0, 30.0)];
        let p = prices(&mine, &theirs);
        assert!(p[&3] > p[&2], "{:?}", p);
    }
}
