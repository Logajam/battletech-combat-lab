//! BTTT, the fifth bot: a re-implementation of the computer opponent of BTTT: BattleTech TableTop by Raptor007 (Blair Sherman,
//! github.com/Raptor007/BTTT; credit in CREDITS.md). BTTT has NO LICENCE, so nothing here is copied: this is written from the bot's
//! algorithm and the rules it plays by, as studied (PROJECT_MAP P8), in this project's own code, on this project's engine. Daniel,
//! 2026-11-24 and 2026-11-25: "get a faithful version of BTTT up and running ... as faithful as possible. Give the bot every advantage
//! its creator intended." It is a BASELINE opponent: a one-turn greedy bot with no team play and no look-ahead.
//!
//! MOVEMENT. For each enemy in turn, walk the unit toward it one step at a time: an enemy behind it or in a side arc turns it that way,
//! otherwise it steps forward; a refused step tries to walk round (turn the way last turned, up to two sixths, then back the other way,
//! trying a step from each facing not yet tried). A turn the opposite way to the step before CANCELS that step and gives its MP back (BTTT's
//! own rule: it is what makes the walk-round work). EVERY position on the way, the start included, is valued; the best path over all enemies
//! wins and is walked exactly (the pick carries its route, so each piloting roll and hazard is taken where the path puts it).
//! SPEEDS (BTTT's `SpeedNeeded`, in its order): a path costing no more than the walking MP is a Walk, up to the running MP a Run, up to twice
//! the walking MP with a working MASC (or a supercharger) a Run on it, up to two and a half times with both; only when the path costs more than
//! all of those, and the HEX DISTANCE from where the move began is within the jump MP, is it a JUMP (so heavy terrain, turns and obstructions
//! push a unit into a jump; a jump costs its distance, its landing takes the best of six facings, and it carries no route). A path no speed
//! covers ends the walk. It never moves backward. The unit to move next is picked at random.
//! VALUE of a position against one enemy: the expected damage of the weapons it would fire (to-hit as 1 - (TN-2)/11, linear; TN above 12
//! cannot hit; damage x 0.6 of a missile rack's size, 0.8 with a working Artemis; an Ultra or Rotary at its top rate, a Narc launcher worth
//! 20 at an enemy not yet Narced and 0 at one that is), dropping the weapon with the least damage per heat until the shot's heat plus the
//! unit's net heat is under 5 (never the last weapon), the best torso twist of centre / left / right (arms flip, when the enemy is in the
//! rear arc and the torso is not twisted); divided by 1 + a quarter of the enemy's movement while that enemy has yet to move; times 1.5
//! behind an enemy that cannot move; plus twice a bonus: 0.1 a hex closer than the start, 0.01 a level of height, +1 or +2 for standing
//! in woods, +0.5 for partial cover from return fire (+1.25 once the enemy has moved), 0.0001 a degree of facing the enemy, the unit's own
//! movement modifier; less, for each damaged gyro or hip when running (and each damaged leg actuator too when jumping), BTTT's own PSR
//! modifiers plus the pilot's skill; less ten for each turn in a row the MASC (or supercharger) has been used when the path needs it.
//! FIRING. The enemy with the best value now is the target, with the best torso twist and the same weapon dropping. TAG: its own phase,
//! TAG weapons only (never in ordinary fire), the best enemy by the same value. SPOTTING: a unit with nothing to shoot spots, for the best
//! enemy it can see. PHYSICAL ATTACKS: the engine's Gladiator choice. A unit that must stand up spends its move standing, walking when
//! running would risk a roll with a damaged gyro or hip.
//!
//! WHERE IT DIFFERS FROM BTTT, on purpose or because the engine differs: every to-hit number is the engine's (this project's rules); a hex
//! another unit stands in is never entered (BTTT's own rule is not known); "random" unit order is a hash of the turn and the candidates
//! (replay-safe: a bot that draws dice cannot be replayed from recorded answers); facing arcs are the book's (120 front, 60 sides, rear
//! beyond 120); BTTT's Value counts a weapon it has dropped (an apparent bug in its code: the dropped weapon's shots go to 0 but its entry
//! stays) and this does not; an Ultra or Rotary is dropped whole (the engine's declaration carries no shot counts); MASC / supercharger
//! are used when the best path needs them (`wants_boost`, asked where the engine rolls them) and rolled by the engine's rules; a working
//! Artemis is any linked one; a unit entering the map from its edge uses Gladiator's move.
use crate::attack_resolution::{weapon_attack_tns, DeclChoice, DeclCtx};
use crate::battle::{Battle, UnitId};
use crate::damage_resolution::get_weapons;
use crate::drawn_route::UnitWalk;
use crate::equipment::ItemId;
use crate::equipment_systems::{boost_multiplier, run_multiplier_by_boosters, system_live};
use crate::fasthash::HashSet;
use crate::hex_geometry::{self, State, FACING_DELTAS};
use crate::los::{self, hex_distance};
use crate::mech_state::{compute_heat_dissipation, compute_jump_mp, compute_running_mp, compute_walk_mp, ArcAction, Mech};
use crate::pathfinder::Hex;
use crate::ranged_combat::Pick;
use crate::step_walk::{Step, WalkState, Walker};

// ---- BTTT's numbers, named ------------------------------------------------------------------------------------------------------
/// to-hit as a straight line: a number of 2 or less always hits, each point above costs 1/11 (BTTT's `(11 - max(0, TN - 2)) / 11`)
const HIT_SLOPE_FROM: i64 = 2;
const HIT_SLOPE_OVER: f64 = 11.0;
/// a weapon needing more than this cannot hit
const MAX_TN: i64 = 12;
/// weapons are dropped until the shot's heat plus net heat is under this
const HEAT_CAP: i64 = 5;
/// an enemy that has yet to move may walk away: value / (1 + this per hex it can move)
const ENEMY_MOVE_DISCOUNT: f64 = 0.25;
/// behind an enemy that cannot move
const BEHIND_BONUS: f64 = 1.5;
/// the position bonus counts twice
const BONUS_WEIGHT: f64 = 2.0;
const CLOSER_PER_HEX: f64 = 0.1;
const HEIGHT_PER_LEVEL: f64 = 0.01;
const FACING_PER_DEGREE: f64 = 0.0001;
const COVER_BEFORE_ENEMY_MOVES: f64 = 0.5;
const COVER_AFTER_ENEMY_MOVES: f64 = 1.25;
/// a missile rack counts this much of its size (0.8 with a working Artemis)
const CLUSTER_SHARE: f64 = 0.6;
const CLUSTER_SHARE_ARTEMIS: f64 = 0.8;
/// the worth of a Narc launcher at an enemy that carries no pod yet
const NARC_WORTH: f64 = 20.0;
/// the least damage a weapon counts for
const MIN_DAMAGE: f64 = 0.9;
/// each turn in a row a MASC or supercharger has been used costs this much of the position bonus
const BOOST_REPEAT_COST: f64 = 10.0;
/// shots of an Ultra and of a Rotary autocannon at their top rate
const ULTRA_SHOTS: i64 = 2;
const ROTARY_SHOTS: i64 = 6;
/// a path never grows past this many steps, nor costs more than this (the walker's own limit; BTTT's rules end the walk sooner)
const MAX_STEPS: usize = 100;
const WALK_BUDGET: i64 = 99;

// ---- geometry ---------------------------------------------------------------------------------------------------------------------
/// The direction of an (x, y) offset in degrees, on the board's real shape (columns 1.5 apart, a row step of 2 is the hex height).
fn angle_of(dx: i64, dy: i64) -> f64 {
    (dy as f64 * 0.866_025_4).atan2(dx as f64 * 1.5).to_degrees()
}

/// Degrees from a unit's facing to the direction of `to` seen from `from`: positive = to the right (a turn right, facing + 1).
fn relative_angle(from: Hex, facing: i64, to: Hex) -> f64 {
    let (fx, fy) = FACING_DELTAS[facing.rem_euclid(6) as usize];
    let mut d = angle_of(fx, fy) - angle_of(to.0 - from.0, to.1 - from.1);
    while d > 180.0 {
        d -= 360.0;
    }
    while d <= -180.0 {
        d += 360.0;
    }
    d
}

/// Which way to turn to face `to`: the target in a side arc or behind turns toward it, in front: no turn (0, -1 left, +1 right).
fn turn_toward(from: Hex, facing: i64, to: Hex) -> i64 {
    let d = relative_angle(from, facing, to);
    if d.abs() <= 60.0 + 1e-6 {
        0
    } else if d > 0.0 {
        1
    } else {
        -1
    }
}

/// Is `me` in the rear arc of `target` (beyond 120 degrees of where the target faces)?
fn behind(b: &Battle, me: Hex, target: UnitId) -> bool {
    let t = &b.units[target];
    let (Some(th), Ok(tf)) = (t.hex.as_deref().and_then(|h| hex_geometry::parse_hex_label(h).ok()), hex_geometry::compass_to_facing(&t.facing)) else { return false };
    relative_angle(th, tf, me).abs() > 120.0
}

fn xy(b: &Battle, u: UnitId) -> Option<Hex> {
    b.units[u].hex.as_deref().and_then(|h| hex_geometry::parse_hex_label(h).ok())
}

fn facing_of(b: &Battle, u: UnitId) -> i64 {
    hex_geometry::compass_to_facing(&b.units[u].facing).unwrap_or(0)
}

// ---- what-if placement ------------------------------------------------------------------------------------------------------------
/// Runs `f` with the unit placed as asked (position, facing, movement mode, hexes moved, MP spent) and its torso as asked, quietly (no log
/// lines, no events, no stub warnings), then puts every field back. The to-hit numbers the engine gives depend on exactly these.
fn what_if<T>(b: &mut Battle, u: UnitId, place: Option<(&WalkState, &str)>, action: Option<ArcAction>, f: impl FnOnce(&mut Battle) -> T) -> T {
    let m = &b.units[u];
    let saved = (m.hex.clone(), m.facing.clone(), m.move_mode.clone(), m.move_fc, m.mp_spent, m.arc_action.clone());
    if let Some((st, mode)) = place {
        let m = &mut b.units[u];
        m.hex = hex_geometry::hex_label(st.x, st.y).ok();
        m.facing = hex_geometry::facing_to_compass(st.facing).unwrap_or("N").to_string();
        m.move_mode = mode.to_string();
        m.move_fc = st.forward_count;
        m.mp_spent = st.mp;
    }
    if action.is_some() {
        b.units[u].arc_action = action;
    }
    b.log.quiet += 1;
    let r = f(b);
    b.log.quiet -= 1;
    let m = &mut b.units[u];
    (m.hex, m.facing, m.move_mode, m.move_fc, m.mp_spent, m.arc_action) = saved;
    r
}

// ---- weapons and a position's value -----------------------------------------------------------------------------------------------
/// One weapon that could fire from here: its engine id, what it is worth for the weapon-dropping ratio and for the position's value (each
/// already times BTTT's chance to hit), the number it needs, the heat of its shot, and whether it is a Streak launcher.
#[derive(Clone, Debug)]
pub struct W {
    pub id: ItemId,
    /// BTTT's `ChooseWeapons` value before it divides by heat: damage x chance to hit x the cluster share (a Streak counts every missile)
    pub ratio_dmg: f64,
    /// BTTT's `Value`: damage x the cluster share (0.8 with Artemis) x chance to hit
    pub value_dmg: f64,
    pub tn: i64,
    pub heat: i64,
    pub streak: bool,
}

impl W {
    /// A plain weapon (no cluster, not a Streak): the same worth for both, the chance to hit applied.
    pub fn simple(id: ItemId, dmg: f64, tn: i64, heat: i64) -> W {
        let v = dmg * hit_factor(tn);
        W { id, ratio_dmg: v, value_dmg: v, tn, heat, streak: false }
    }

    /// The heat of the shot BTTT counts (`ShotHeat`): a Streak's scaled by its chance to hit, each weapon's cut to a whole number.
    fn shot_heat(&self) -> i64 {
        let mut h = self.heat as f64;
        if self.streak {
            h *= (HIT_SLOPE_OVER - (self.tn - HIT_SLOPE_FROM).max(0) as f64) / 10.9;
        }
        h as i64
    }
}

fn hit_factor(tn: i64) -> f64 {
    (HIT_SLOPE_OVER - (tn - HIT_SLOPE_FROM).max(0) as f64) / HIT_SLOPE_OVER
}

/// Has the enemy a Narc pod on it already (BTTT's `Narced`)?
fn narced(b: &Battle, target: UnitId) -> bool {
    !b.units[target].narc_pods.is_empty()
}

/// The weapons the unit could fire at `target` as it stands (position, torso, movement mode as set): in range, in arc, with a line of sight,
/// needing no more than 12, with known damage and heat; TAG weapons are not among them (they have their own phase). (BTTT's
/// `UpdateWeaponsInRange`.)
fn weapons_in_range(b: &mut Battle, u: UnitId, target: UnitId) -> Vec<W> {
    let listed = get_weapons(&b.units[u]);
    let all: Vec<ItemId> = listed.into_iter().filter(|w| !crate::tag::is_tag(b, u, *w)).collect();
    let Some((tns, _, _)) = weapon_attack_tns(b, u, target, &all, false) else { return vec![] };
    let target_narced = narced(b, target);
    let mut out = Vec::new();
    for (id, tn) in tns {
        if tn > MAX_TN {
            continue;
        }
        let (heat, dps, rack, artemis) = {
            let it = &b.units[u].items[id];
            (it.heat, it.damage_per_shot, it.rack_size, it.artemis.is_some())
        };
        let (Some(heat), Some(dps)) = (heat, dps) else { continue };
        let hit = hit_factor(tn);
        let streak = crate::weapon_rules::is_streak(b, u, id);
        let cluster = if crate::weapon_rules::is_cluster(b, u, id) { rack.unwrap_or(1).max(1) as f64 } else { 1.0 };
        let shots = if crate::fire_modes::is_rotary(b, u, id) {
            ROTARY_SHOTS
        } else if crate::fire_modes::is_ultra(b, u, id) {
            ULTRA_SHOTS
        } else {
            1
        };
        let ratio_share = if streak { cluster.max(1.0) } else { (cluster * CLUSTER_SHARE).max(1.0) };
        let value_share = (cluster * if artemis { CLUSTER_SHARE_ARTEMIS } else { CLUSTER_SHARE }).max(1.0);
        let (ratio_dmg, value_dmg);
        if crate::electronics::is_narc(b, u, id) {
            // worthless at an enemy already Narced, very valuable at one that is not
            let w = if target_narced { 0.0 } else { NARC_WORTH };
            ratio_dmg = w * hit * ratio_share;
            value_dmg = w * hit * value_share;
        } else {
            let base = (dps as f64).max(MIN_DAMAGE);
            let rapid = (shots as f64 * CLUSTER_SHARE).max(1.0);
            ratio_dmg = base * rapid * hit * ratio_share;
            value_dmg = base * value_share * rapid * hit;
        }
        out.push(W { id, ratio_dmg, value_dmg, tn, heat: heat * shots, streak });
    }
    out
}

/// BTTT's `ChooseWeapons`: fire everything, then drop the weapon worth least per point of heat until the shot's heat plus the unit's net heat
/// (heat now less what it sheds) is under 5; the last weapon is never dropped. Returns the indices still firing.
pub fn choose_weapons(b: &Battle, u: UnitId, ws: &[W]) -> Vec<usize> {
    let m = &b.units[u];
    let base_heat = m.current_heat - compute_heat_dissipation(m);
    let mut fire: Vec<usize> = (0..ws.len()).collect();
    loop {
        let shot: i64 = fire.iter().map(|&i| ws[i].shot_heat()).sum();
        if shot == 0 || shot + base_heat < HEAT_CAP || fire.len() <= 1 {
            break;
        }
        // the ratio divides by the weapon's heat, a Streak's scaled by its chance to hit
        let ratio = |i: usize| {
            let w = &ws[i];
            let heat = if w.streak { w.heat as f64 * hit_factor(w.tn) } else { w.heat as f64 };
            w.ratio_dmg / heat.max(0.01)
        };
        let mut worst = 0;
        for k in 1..fire.len() {
            if ratio(fire[k]) < ratio(fire[worst]) {
                worst = k;
            }
        }
        fire.remove(worst);
    }
    fire
}

/// What the weapons chosen are worth to the position: BTTT's `Value` (damage x cluster share x chance to hit, summed).
fn weapon_value(ws: &[W], fire: &[usize]) -> f64 {
    fire.iter().map(|&i| ws[i].value_dmg).sum()
}

/// What a unit with the torso where it is would do to `target` from where it stands: the value, the weapons and their data.
struct Aim {
    value: f64,
    ws: Vec<W>,
    fire: Vec<usize>,
}

/// The value of the unit's present position (placed by `what_if`) against `target` with its torso as set. `moving`: the movement phase
/// (the enemy's chance to walk away counts, and `bonus` is the position bonus); else the shooting phase.
fn aim_here(b: &mut Battle, u: UnitId, target: UnitId, moving: bool, bonus: f64) -> Aim {
    let ws = weapons_in_range(b, u, target);
    let fire = choose_weapons(b, u, &ws);
    let mut value = weapon_value(&ws, &fire);
    // the enemy may still move away: only while it has yet to move, and only in the movement phase
    let (walk_t, jump_t, moved) = {
        let t = &b.units[target];
        (compute_walk_mp(t), compute_jump_mp(t), t.moved_this_turn)
    };
    let can_move = if moving && !moved { walk_t.max(boosted_run(b, target)).max(jump_t) } else { 0 };
    if can_move > 0 {
        value /= 1.0 + ENEMY_MOVE_DISCOUNT * can_move as f64;
    }
    if can_move == 0 {
        if let Some(me) = xy(b, u) {
            if behind(b, me, target) {
                value *= BEHIND_BONUS;
            }
        }
    }
    value += bonus * BONUS_WEIGHT;
    Aim { value, ws, fire }
}

/// The torso actions BTTT tries against an enemy seen from `pos` facing `facing`: centre, left, right; with the arms flipped for the centre
/// when the enemy is in the rear arc and the unit can flip them (BTTT flips only when the torso is not twisted).
fn actions_vs(b: &Battle, u: UnitId, pos: Hex, facing: i64, goal: Hex) -> Vec<ArcAction> {
    let opts = crate::arcs::arc_options(&b.units[u], "ranged");
    let flip_ok = opts.iter().any(|a| a.flip && a.twist == 0 && a.turret.is_none());
    let rear = relative_angle(pos, facing, goal).abs() > 120.0;
    let mut tw: Vec<i64> = opts.iter().filter(|a| a.turret.is_none()).map(|a| a.twist).collect();
    tw.sort();
    tw.dedup();
    if tw.is_empty() {
        tw.push(0);
    }
    // centre first: it wins a tie
    tw.sort_by_key(|x| x.abs());
    tw.into_iter().map(|t| ArcAction { twist: t, flip: t == 0 && rear && flip_ok, turret: None }).collect()
}

/// The best torso action's aim (the unit placed as `what_if` left it): a twist must beat the centre outright to be chosen.
fn best_twist(b: &mut Battle, u: UnitId, target: UnitId, moving: bool, bonus: f64) -> (ArcAction, Aim) {
    let (Some(pos), Some(goal)) = (xy(b, u), xy(b, target)) else {
        return (ArcAction { twist: 0, flip: false, turret: None }, Aim { value: 0.0, ws: vec![], fire: vec![] });
    };
    let facing = facing_of(b, u);
    let mut best: Option<(ArcAction, Aim)> = None;
    for a in actions_vs(b, u, pos, facing, goal) {
        b.units[u].arc_action = Some(a.clone());
        let aim = aim_here(b, u, target, moving, bonus);
        if best.as_ref().map_or(true, |(_, x)| aim.value > x.value) {
            best = Some((a, aim));
        }
    }
    best.expect("an action")
}

// ---- a unit's pace ------------------------------------------------------------------------------------------------------------------
/// The running MP with the multiplier a working MASC / supercharger give (BTTT's `MASCDist` upper limit): what the unit could run at with them.
fn boosted_run(b: &mut Battle, u: UnitId) -> i64 {
    let mult = boost_multiplier(b, u, false);
    run_with(b, u, mult)
}

/// The running MP with `mult` as its multiplier.
fn run_with(b: &mut Battle, u: UnitId, mult: f64) -> i64 {
    let saved = b.units[u].run_mp_multiplier;
    b.units[u].run_mp_multiplier = mult;
    let r = compute_running_mp(&b.units[u]);
    b.units[u].run_mp_multiplier = saved;
    r
}

/// How far a move may go, in BTTT's terms (`SpeedNeeded`): the walking MP, the running MP without a booster, the running MP the unit may have
/// (with a MASC or supercharger it has switched on), and the jump MP.
struct Limits {
    walk: i64,
    base_run: i64,
    allowed: i64,
    jump: i64,
    start: Hex,
}

impl Limits {
    fn of(b: &mut Battle, u: UnitId, uw: &UnitWalk, allowed: Option<i64>) -> Limits {
        let (walk, jump) = {
            let m = &b.units[u];
            (compute_walk_mp(m), if m.prone { 0 } else { compute_jump_mp(m) })
        };
        let base_run = run_with(b, u, run_multiplier_by_boosters(0));
        let allowed = allowed.unwrap_or_else(|| compute_running_mp(&b.units[u]));
        Limits { walk, base_run, allowed, jump, start: (uw.start.0, uw.start.1) }
    }

    /// Is a path costing `cost` MP and ending at `pos` a move at all? A walk, a run, a boosted run - or, when it costs more than all of those,
    /// a jump to a hex within the jump MP of where the move began.
    fn valid(&self, cost: i64, pos: Hex) -> bool {
        cost <= self.allowed || (self.jump > 0 && hex_distance(self.start, pos) <= self.jump)
    }

    /// Is this position a jump (its path costs more than any walking speed)?
    fn jumping(&self, st: &WalkState) -> bool {
        st.mp > self.allowed
    }

    fn mode(&self, st: &WalkState) -> &'static str {
        if st.mp == 0 {
            "Stand Still"
        } else if self.jumping(st) {
            "Jump"
        } else {
            crate::combat::classify_movement_mode(st.mp, self.walk)
        }
    }
}

/// `st` as a jump landing: the hexes moved and the MP spent are the distance flown (a jump costs its distance), not the steps walked.
fn as_jump(start: Hex, st: &WalkState) -> WalkState {
    let d = hex_distance(start, (st.x, st.y));
    WalkState { forward_count: d, mp: d, ..st.clone() }
}

/// The engine's jump states for the unit (where it can land, any facing), when it has any jump MP at all.
type Jumps = Option<crate::fasthash::IndexMap<State, i64>>;

fn jump_states(b: &Battle, u: UnitId, uw: &UnitWalk) -> Jumps {
    let jump = if b.units[u].prone { 0 } else { compute_jump_mp(&b.units[u]) };
    if jump <= 0 {
        return None;
    }
    crate::combat::build_jump_states(&b.board, uw.start.0, uw.start.1, jump).ok()
}

// ---- BTTT's piloting modifiers --------------------------------------------------------------------------------------------------
/// BTTT's `PSRModifiers`: +3 for a damaged gyro (+6 for two hits), +2 for each leg with a damaged hip, +1 for each damaged leg actuator
/// (on a leg with a good hip), +5 when half the legs or more are gone.
pub fn psr_modifiers(m: &Mech) -> i64 {
    let mut mods = match m.gyro_hits {
        0 => 0,
        1 => 3,
        _ => 6,
    };
    let (mut legs, mut gone) = (0, 0);
    for l in &m.leg_locations {
        legs += 1;
        if m.locations.get(l).is_some_and(|x| x.destroyed) {
            gone += 1;
        } else if m.destroyed_hip_locations.contains(l) {
            mods += 2;
        } else {
            mods += m.destroyed_leg_actuators.get(l).copied().unwrap_or(0);
        }
    }
    if gone >= legs / 2 {
        mods += 5;
    }
    mods
}

/// (the count that makes running risky, the count that makes jumping risky) as BTTT counts them: gyro hits plus damaged hips, and with every
/// damaged leg actuator besides for a jump.
pub fn psr_counts(m: &Mech) -> (i64, i64) {
    let run = m.gyro_hits + m.destroyed_hip_locations.len() as i64;
    let actuators: i64 = m.destroyed_leg_actuators.values().sum();
    (run, run + actuators)
}

/// How much of the position bonus a MASC / supercharger the path needs has cost: ten for each turn in a row it has been used (BTTT's
/// `MASCTurns` / `SuperchargerTurns`). The order is BTTT's: MASC alone up to twice the walking MP, a supercharger alone up to the same,
/// both up to two and a half times.
fn boost_penalty(m: &Mech, lim: &Limits, cost: i64) -> f64 {
    if cost <= lim.base_run {
        return 0.0;
    }
    let turns = |k: &str| m.escalating_turns.get(k).copied().unwrap_or(0) as f64;
    let (masc, sc) = (system_live(m, "masc"), system_live(m, "supercharger"));
    if cost <= lim.walk * 2 {
        if masc {
            return BOOST_REPEAT_COST * turns("masc");
        }
        if sc {
            return BOOST_REPEAT_COST * turns("supercharger");
        }
        return 0.0;
    }
    if masc && sc {
        return BOOST_REPEAT_COST * (turns("masc") + turns("supercharger"));
    }
    0.0
}

// ---- a position's bonus ----------------------------------------------------------------------------------------------------------
/// The position bonus of the unit standing at `st` (BTTT's `ValueBonus` in the movement phase), before it is doubled.
fn position_bonus(b: &mut Battle, u: UnitId, target: UnitId, lim: &Limits, st: &WalkState, mode: &'static str) -> f64 {
    let pos = (st.x, st.y);
    let Some(there) = xy(b, target) else { return 0.0 };
    let mut bonus = CLOSER_PER_HEX * (hex_distance(lim.start, there) - hex_distance(pos, there)) as f64;
    if let Some(h) = hex_geometry::hex_label(st.x, st.y).ok().and_then(|l| b.board.hexes.get(&l)) {
        bonus += h.level as f64 * HEIGHT_PER_LEVEL;
        // woods: the level (1 light, 2 heavy) of the standing hex
        for f in crate::terrain_rules::WOODS_FEATURES {
            if let Some(p) = h.features.get(f) {
                bonus += p.first().and_then(|x| x.parse::<f64>().ok()).unwrap_or(1.0);
            }
        }
    }
    // partial cover from the enemy's return fire
    let (me_h, t_h) = (crate::attack_resolution::los_height(&b.units[u]), crate::attack_resolution::los_height(&b.units[target]));
    if let Ok(trace) = los::trace_los_path(there, pos, &b.board, t_h, me_h) {
        if trace.result.los && trace.steps.last().is_some_and(|s| s.partial_cover != 0) {
            bonus += if b.units[target].moved_this_turn { COVER_AFTER_ENEMY_MOVES } else { COVER_BEFORE_ENEMY_MOVES };
        }
    }
    // a hundredth of a degree-fraction for facing the enemy (mostly decides the landing of a jump)
    bonus += (180.0 - relative_angle(pos, st.facing, there).abs()) * FACING_PER_DEGREE;
    // the unit's own movement modifier: moving far enough is worth something
    if let Some(o) = crate::move_options::prepare_options(b, u, &[(st.x, st.y, st.facing, st.forward_count, mode, st.mp)]).into_iter().next() {
        bonus += o.tmm as f64;
    }
    // running or jumping with damaged gyro, hips or leg actuators risks a fall each time: BTTT's penalty per damage is its PSR modifiers
    // plus the pilot's skill
    let m = &b.units[u];
    let (run_psr, jump_psr) = psr_counts(m);
    let per = psr_modifiers(m) + m.piloting;
    if mode == "Jump" && jump_psr > 0 {
        bonus -= (jump_psr * per) as f64;
    } else if (mode == "Run" || mode == "Jump") && run_psr > 0 && !m.prone {
        bonus -= (run_psr * per) as f64;
    }
    // a MASC or supercharger used turn after turn
    if mode == "Run" {
        bonus -= boost_penalty(m, lim, st.mp);
    }
    bonus
}

// ---- movement ---------------------------------------------------------------------------------------------------------------------
/// The value of landing at `st` (a position and facing) by a jump from where the move began, or 0 where the engine does not let the unit land.
fn jump_value(b: &mut Battle, u: UnitId, target: UnitId, lim: &Limits, jumps: &Jumps, st: &WalkState) -> f64 {
    let Some(j) = jumps else { return 0.0 };
    if !j.contains_key(&st.state()) {
        return 0.0;
    }
    let st = as_jump(lim.start, st);
    what_if(b, u, Some((&st, "Jump")), None, |b| {
        let bonus = position_bonus(b, u, target, lim, &st, "Jump");
        best_twist(b, u, target, true, bonus).1.value
    })
}

/// The value of standing at `st` against `target`: the best torso action, the position bonus counted.
fn value_at(b: &mut Battle, u: UnitId, target: UnitId, lim: &Limits, jumps: &Jumps, st: &WalkState) -> f64 {
    if lim.jumping(st) {
        return jump_value(b, u, target, lim, jumps, st);
    }
    let mode = lim.mode(st);
    what_if(b, u, Some((st, mode)), None, |b| {
        let bonus = position_bonus(b, u, target, lim, st, mode);
        best_twist(b, u, target, true, bonus).1.value
    })
}

/// One walk toward one enemy: the cursor and the steps taken, moving on together.
struct Walk<'a> {
    uw: &'a UnitWalk,
    blocked: &'a HashSet<Hex>,
    lim: &'a Limits,
    start: WalkState,
    cur: WalkState,
    steps: Vec<Step>,
}

impl Walk<'_> {
    fn walker<'b>(&'b self, b: &'b Battle) -> Walker<'b> {
        Walker { board: &b.board, blocked: self.blocked, level_limit: self.uw.level_limit, budget: WALK_BUDGET, backward_mp: None }
    }

    /// Takes a step if BTTT's rules let the move go on: a turn the opposite way to the step before CANCELS it (and gives its MP back); any
    /// other step must leave the position a valid move (a speed covers it). False: refused, nothing changed.
    fn take(&mut self, b: &Battle, s: Step) -> bool {
        let opposite = match s {
            Step::TurnLeft => Some(Step::TurnRight),
            Step::TurnRight => Some(Step::TurnLeft),
            _ => None,
        };
        if opposite.is_some() && self.steps.last().copied() == opposite {
            self.steps.pop();
            let steps = self.steps.clone();
            let replayed = self.walker(b).walk(&self.start, &steps);
            if let Ok(states) = replayed {
                self.cur = states.last().cloned().unwrap_or_else(|| self.start.clone());
            }
            return true;
        }
        let next = self.walker(b).step(&self.cur, s);
        match next {
            Ok(next) if self.lim.valid(next.mp, (next.x, next.y)) => {
                self.cur = next;
                self.steps.push(s);
                true
            }
            _ => false,
        }
    }
}

/// BTTT's walk toward one enemy: every position on the way is valued, the best one's steps are returned with its value.
fn walk_toward(b: &mut Battle, u: UnitId, target: UnitId, uw: &UnitWalk, blocked: &HashSet<Hex>, lim: &Limits, jumps: &Jumps) -> (f64, Vec<Step>) {
    let Some(goal) = xy(b, target) else { return (0.0, vec![]) };
    let start = {
        let w0 = Walker { board: &b.board, blocked, level_limit: uw.level_limit, budget: WALK_BUDGET, backward_mp: None };
        w0.start(uw.start.0, uw.start.1, uw.start.2)
    };
    let Ok(start) = start else { return (0.0, vec![]) };
    let mut walk = Walk { uw, blocked, lim, start: start.clone(), cur: start, steps: Vec::new() };
    let (mut best_value, mut best_steps) = (0.0_f64, Vec::<Step>::new());
    let mut turning = 0_i64;
    while walk.steps.len() < MAX_STEPS {
        let v = value_at(b, u, target, lim, jumps, &walk.cur);
        if v > best_value {
            best_value = v;
            best_steps = walk.steps.clone();
        }
        let (cx, cy, cf) = (walk.cur.x, walk.cur.y, walk.cur.facing);
        let turn = turn_toward((cx, cy), cf, goal);
        if turn != 0 {
            // out of MP (or unable to turn): the walk ends
            if !walk.take(b, if turn > 0 { Step::TurnRight } else { Step::TurnLeft }) {
                break;
            }
            turning = turn;
        } else if !walk.take(b, Step::Forward) {
            // walk round the obstruction: turn the way last turned (twice), then back the other way, trying a step from each new facing
            if turning == 0 {
                turning = if relative_angle((cx, cy), cf, goal) >= 0.0 { 1 } else { -1 };
            }
            let mut stepped = false;
            for i in 0..7 {
                let t = if i <= 1 { turning } else { -turning };
                if !walk.take(b, if t > 0 { Step::TurnRight } else { Step::TurnLeft }) {
                    break;
                }
                // the two turns back cancel the two out: those facings were tried on the way out
                if i == 2 || i == 3 {
                    continue;
                }
                let v = value_at(b, u, target, lim, jumps, &walk.cur);
                if v > best_value {
                    best_value = v;
                    best_steps = walk.steps.clone();
                }
                if walk.take(b, Step::Forward) {
                    stepped = true;
                    break;
                }
            }
            if !stepped {
                break;
            }
        }
    }
    (best_value, best_steps)
}

/// The best move found against every enemy: its value, steps, the enemy it goes toward and where it ends.
struct Plan {
    value: f64,
    steps: Vec<Step>,
    target: Option<UnitId>,
    end: WalkState,
    jump: bool,
}

fn plan_move(b: &mut Battle, mover: UnitId, uw: &UnitWalk, lim: &Limits) -> Option<Plan> {
    let jumps = jump_states(b, mover, uw);
    // a hex any other unit stands in is never entered
    let mut blocked: HashSet<Hex> = uw.blocked.clone();
    for l in crate::forces::occupied_labels(b, mover) {
        if let Ok(h) = hex_geometry::parse_hex_label(&l) {
            blocked.insert(h);
        }
    }
    let enemies: Vec<UnitId> = crate::forces::enemies_of(b, mover).into_iter().filter(|e| xy(b, *e).is_some()).collect();
    let (mut best_value, mut best_steps, mut best_target) = (0.0_f64, Vec::<Step>::new(), None);
    for e in enemies {
        let (v, steps) = walk_toward(b, mover, e, uw, &blocked, lim, &jumps);
        if v > best_value {
            (best_value, best_steps, best_target) = (v, steps, Some(e));
        }
    }
    let (start, walked) = {
        let w = Walker { board: &b.board, blocked: &blocked, level_limit: uw.level_limit, budget: WALK_BUDGET, backward_mp: None };
        let start = w.start(uw.start.0, uw.start.1, uw.start.2).ok()?;
        let walked = w.walk(&start, &best_steps).ok().and_then(|s| s.last().cloned());
        (start, walked)
    };
    let mut end = walked.unwrap_or(start);
    let jump = lim.jumping(&end);
    if jump {
        // a JUMP: the unit flies to where the path ended. It takes the best of its six facings, as BTTT does (it turns right six times and keeps a
        // facing only when it beats the value so far)
        let target = best_target?;
        let mut best_v = best_value;
        let arrival = end.clone();
        for k in 1..=6 {
            let f = WalkState { facing: (arrival.facing + k).rem_euclid(6), ..arrival.clone() };
            let v = jump_value(b, mover, target, lim, &jumps, &f);
            if v > best_v {
                best_v = v;
                end = f;
            }
        }
        best_value = best_v;
    }
    Some(Plan { value: best_value, steps: best_steps, target: best_target, end, jump })
}

/// Does the unit want its MASC / supercharger this turn? BTTT uses one when the path it walks needs it (costs more than the plain running
/// MP and not more than the boosted). Asked where the engine rolls the systems (`equipment_systems::resolve_movement_boosters`), before the
/// move is chosen: plans the move with the boosted MP and says yes if that best path needs it.
pub fn wants_boost(b: &mut Battle, u: UnitId) -> bool {
    if b.units[u].prone || b.units[u].hex.is_none() {
        return false;
    }
    let Some(uw) = UnitWalk::of(b, u) else { return false };
    let boosted = boosted_run(b, u);
    let base = run_with(b, u, run_multiplier_by_boosters(0));
    if boosted <= base {
        return false;
    }
    b.log.quiet += 1;
    let lim = Limits::of(b, u, &uw, Some(boosted));
    let plan = plan_move(b, u, &uw, &lim);
    b.log.quiet -= 1;
    plan.is_some_and(|p| !p.jump && p.end.mp > lim.base_run && p.end.mp <= lim.allowed)
}

/// The move BTTT's bot makes: Some((the pick, a note)), or None for a move this bot does not make itself (a unit entering the map: the
/// caller uses Gladiator's).
pub fn choose_movement(b: &mut Battle, mover: UnitId, standup_mp: Option<i64>, entry_edge: Option<&[String]>) -> Option<(Option<Pick>, String)> {
    if entry_edge.is_some() {
        return None;
    }
    if standup_mp.is_some() || b.units[mover].prone {
        // standing up is its whole move: running, unless that would risk a roll with a damaged gyro or hip and it could walk (BTTT's own rule)
        let m = &b.units[mover];
        let (run_psr, _) = psr_counts(m);
        if compute_walk_mp(m) >= 2 && run_psr > 0 {
            b.units[mover].move_mode = "Walk".to_string();
        }
        return Some((None, "BTTT: standing up is its whole move".to_string()));
    }
    let uw = UnitWalk::of(b, mover)?;
    let lim = Limits::of(b, mover, &uw, None);
    let plan = plan_move(b, mover, &uw, &lim)?;
    let name = b.units[mover].side_name.clone().unwrap_or_default();
    let end = &plan.end;
    let (mode, fc, mp, route) = if plan.jump {
        let flown = as_jump(lim.start, end);
        ("Jump", flown.forward_count, flown.mp, None)
    } else {
        (lim.mode(end), end.forward_count, end.mp, Some(plan.steps.clone()))
    };
    let pick = Pick {
        hex: hex_geometry::hex_label(end.x, end.y).ok()?,
        facing: hex_geometry::facing_to_compass(end.facing).ok()?.to_string(),
        mode: mode.to_string(),
        fc,
        mp_spent: mp,
        charge: false,
        dfa: false,
        route,
    };
    let note = match plan.target {
        Some(t) if plan.jump => format!("BTTT: jumps {} hexes toward {} (value {:.2})", mp, b.units[t].side_name.clone().unwrap_or_default(), plan.value),
        Some(t) => format!("BTTT: {} steps toward {} (value {:.2}), {} {} MP", plan.steps.len(), b.units[t].side_name.clone().unwrap_or_default(), plan.value, mode, mp),
        None => format!("BTTT: {} finds nothing worth moving for and stays", name),
    };
    Some((Some(pick), note))
}

// ---- who moves next ---------------------------------------------------------------------------------------------------------------
/// BTTT picks the unit to move at random. A hash of the turn and the candidates (a dice draw could not be replayed from recorded
/// answers): the same position always gives the same pick.
pub fn move_pick(b: &Battle, candidates: &[UnitId]) -> Option<UnitId> {
    if candidates.is_empty() || !candidates.iter().all(|u| b.units[*u].bot == "bttt") {
        return None;
    }
    let mut h: u64 = 0xcbf2_9ce4_8422_2325;
    let mut mix = |x: u64| {
        h ^= x;
        h = h.wrapping_mul(0x0000_0100_0000_01b3);
        h ^= h >> 29;
    };
    mix(b.units[candidates[0]].turn_number as u64);
    for &u in candidates {
        mix(u as u64);
        for byte in b.units[u].hex.as_deref().unwrap_or("").bytes() {
            mix(byte as u64);
        }
    }
    Some(candidates[(h % candidates.len() as u64) as usize])
}

// ---- firing, TAG and spotting ----------------------------------------------------------------------------------------------------
/// The enemy with the best value as the unit stands now (the shooting phase: no movement discount, no position bonus), if it has any
/// weapon to fire at it.
pub fn choose_target(b: &mut Battle, attacker: UnitId) -> Option<UnitId> {
    let enemies: Vec<UnitId> = crate::forces::enemies_of(b, attacker).into_iter().filter(|e| xy(b, *e).is_some()).collect();
    let mut best: Option<(f64, i64, UnitId)> = None;
    for e in enemies {
        let (value, heat, any) = what_if(b, attacker, None, None, |b| {
            let (_, a) = best_twist(b, attacker, e, false, 0.0);
            (a.value, a.fire.iter().map(|&i| a.ws[i].shot_heat()).sum::<i64>(), !a.fire.is_empty())
        });
        if !any {
            continue;
        }
        // best value; on a tie the cooler shot
        if best.as_ref().map_or(true, |(v, h, _)| value > *v + 1e-12 || ((value - *v).abs() <= 1e-12 && heat < *h)) {
            best = Some((value, heat, e));
        }
    }
    best.map(|(_, _, e)| e)
}

/// The weapons and the torso action BTTT declares against `target`: the best of centre / left / right (arms flipped for a rear target with
/// no twist), with the heat-limited weapons.
pub fn choose_declaration(b: &mut Battle, ctx: &DeclCtx, attacker: UnitId, target: UnitId) -> DeclChoice {
    let rear = relative_angle(ctx.a_hex, ctx.a_facing, ctx.t_hex).abs() > 120.0;
    let flip_ok = ctx.arc_choices.iter().any(|(_, a)| a.flip && a.twist == 0 && a.turret.is_none());
    let mut best: Option<(f64, Aim, crate::arcs::ArcKey, ArcAction)> = None;
    for (key, action) in ctx.arc_choices.iter().filter(|(_, a)| a.turret.is_none() && a.flip == (a.twist == 0 && rear && flip_ok)) {
        let aim = what_if(b, attacker, None, Some(action.clone()), |b| aim_here(b, attacker, target, false, 0.0));
        if best.as_ref().map_or(true, |(v, ..)| aim.value > *v) {
            best = Some((aim.value, aim, key.clone(), action.clone()));
        }
    }
    let (_, aim, key, action) = best.unwrap_or_else(|| {
        let (k, a) = ctx.arc_choices[0].clone();
        (0.0, Aim { value: 0.0, ws: vec![], fire: vec![] }, k, a)
    });
    DeclChoice {
        weapons: aim.fire.iter().map(|&i| aim.ws[i].id).collect(),
        exp_dmg: weapon_value(&aim.ws, &aim.fire),
        weapon_heat: aim.fire.iter().map(|&i| aim.ws[i].shot_heat()).sum(),
        key_torso_arc: key.torso_arc,
        action,
        phys_names: vec![],
        phys_value: 0.0,
        held: Default::default(),
    }
}

/// BTTT's TAG phase: only TAG weapons fire, each at the enemy with the best value (a TAG is worth the least damage a weapon counts, times the
/// chance to hit, times 1.5 from behind); no torso twist. Some(None): no TAG this unit can make; never at the ground.
pub fn choose_tag(b: &mut Battle, attacker: UnitId, cands: &[crate::tag::TagCandidate]) -> Option<Option<(UnitId, &'static str)>> {
    let mut best: Option<(f64, i64, UnitId)> = None;
    for c in cands {
        let Some(tn) = c.tn_mech else { continue };
        if tn > MAX_TN {
            continue;
        }
        let mut v = MIN_DAMAGE * hit_factor(tn);
        if let (Some(me), true) = (xy(b, attacker), b.units[c.target].hex.is_some()) {
            if behind(b, me, c.target) {
                v *= BEHIND_BONUS;
            }
        }
        let d = crate::forces::distance(b, attacker, c.target).unwrap_or(99);
        // the best value; on a tie the nearer enemy
        if best.as_ref().map_or(true, |(bv, bd, _)| v > *bv + 1e-12 || ((v - *bv).abs() <= 1e-12 && d < *bd)) {
            best = Some((v, d, c.target));
        }
    }
    Some(best.map(|(_, _, t)| (t, "mech")))
}

/// BTTT's spotting: a unit with nothing to shoot spots (for indirect fire) for the best enemy it can see, the nearest when none is worth more
/// than another; a unit with a shot spots for no one.
pub fn choose_spot(b: &mut Battle, u: UnitId) -> Option<(UnitId, bool)> {
    if choose_target(b, u).is_some() {
        return None;
    }
    let mut c = crate::spotting::spot_candidates(b, u);
    c.sort_by(|x, y| x.2.cmp(&y.2));
    c.first().map(|x| (x.0, false))
}

/// Used by tests: the (x, y, facing) state a pick ends in.
pub fn end_state(p: &Pick) -> Option<State> {
    let (x, y) = hex_geometry::parse_hex_label(&p.hex).ok()?;
    Some((x, y, hex_geometry::compass_to_facing(&p.facing).ok()?))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn to_hit_is_a_straight_line_and_a_number_of_two_or_less_always_hits() {
        assert_eq!(hit_factor(2), 1.0);
        assert_eq!(hit_factor(-3), 1.0);
        assert!((hit_factor(7) - 6.0 / 11.0).abs() < 1e-12);
        assert!((hit_factor(12) - 1.0 / 11.0).abs() < 1e-12);
    }

    #[test]
    fn a_target_behind_or_to_the_side_turns_the_unit_toward_it_one_in_front_does_not() {
        // facing 0 looks along (0, +2): straight ahead is (0, +4); the neighbours at 60 degrees are (+-1, +1) away from the middle
        let me = (5, 10);
        assert_eq!(turn_toward(me, 0, (5, 14)), 0, "straight ahead");
        assert_eq!(turn_toward(me, 0, (6, 11)), 0, "the front-right neighbour is on the front arc's edge: front");
        // behind: either way round is as short; it must turn (and consistently)
        let t = turn_toward(me, 0, (5, 6));
        assert!(t == 1 || t == -1);
        // a target to the right of a unit facing 0 (positive x is clockwise from facing 0) turns it right, to the left turns it left
        assert_eq!(turn_toward(me, 0, (8, 8)), 1, "right and behind-ish: right");
        assert_eq!(turn_toward(me, 0, (2, 8)), -1, "left and behind-ish: left");
        // every facing: the target straight along that facing needs no turn
        for f in 0..6 {
            let (dx, dy) = FACING_DELTAS[f as usize];
            assert_eq!(turn_toward(me, f, (me.0 + 3 * dx, me.1 + 3 * dy)), 0, "facing {}", f);
        }
    }

    #[test]
    fn the_rear_arc_is_beyond_120_degrees() {
        // a unit facing 0 at (5, 10): the hex straight behind it is directly in its rear; the hex beside it (a side hexside) is not
        let d_back = relative_angle((5, 10), 0, (5, 6)).abs();
        let d_side = relative_angle((5, 10), 0, (6, 9)).abs();
        assert!(d_back > 120.0 && d_side <= 120.0, "behind {} side {}", d_back, d_side);
    }

    #[test]
    fn speeds_follow_bttts_order_and_a_jump_needs_the_distance_not_the_cost() {
        // a unit that walks 4, runs 6 (no booster), may run 8 with one, and jumps 5 from (10, 10)
        let lim = Limits { walk: 4, base_run: 6, allowed: 8, jump: 5, start: (10, 10) };
        let st = |mp: i64| WalkState { x: 10, y: 14, facing: 0, mp, last: 0, used_back: false, forward_count: 0, always_psrs: 0, run_psrs: 0, hazard: 0.0 };
        assert!(lim.valid(8, (10, 14)) && !lim.jumping(&st(8)), "up to the (boosted) running MP is a run");
        // a path past every walking speed is a jump only if the hex is within the jump MP of the start: (10, 14) is 2 hexes away, (10, 26) is 8
        assert!(lim.valid(11, (10, 14)) && lim.jumping(&st(11)), "11 MP of turns and woods, but only 2 hexes: a jump");
        assert!(!lim.valid(11, (10, 26)), "11 MP and 8 hexes: no speed covers it");
        // no jump MP: past the running MP ends the walk
        let walker = Limits { jump: 0, ..lim };
        assert!(!walker.valid(9, (10, 14)));
    }
}
