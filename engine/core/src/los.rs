// Translated from pathfinder/los.py (session 22).
//! Line of sight between two hexes (Core pp.56-58, 66; TO:AR terrain; smoke p.124): the straight-line hex path
//! between their centers, and whether / how it blocks or degrades LOS. Plain (x, y) doubled coordinates, attacker
//! first. Every f64 operation is in the Python's order (RUST_PORT trap 4).

use crate::board_parser::{Board, Hex as HexInfo};
use crate::hex_geometry::hex_label;
use crate::pyfmt::py_round;

pub type Hex = (i64, i64);

/// Target-hex woods to-hit modifier by woods density (p.66).
pub fn target_woods_modifier(density: Option<&str>) -> i64 {
    match density {
        Some("1") => 1,
        Some("2") => 2,
        Some("3") => 3,
        _ => 0,
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct LOSResult {
    pub los: bool,
    pub modifier: i64,
    pub distance: i64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct LOSStep {
    pub index: i64,
    pub hex: Hex,
    pub other_candidate: Option<Hex>,
    pub level: i64,
    pub is_endpoint: bool,
    pub blocked: bool,
    pub woods_contrib: i64,
    pub partial_cover: i64,
    pub cumulative_modifier: i64,
    pub smoke_contrib: i64,
    pub after_block: bool,
}

impl LOSStep {
    fn new(index: i64, hex: Hex) -> LOSStep {
        LOSStep {
            index,
            hex,
            other_candidate: None,
            level: 0,
            is_endpoint: false,
            blocked: false,
            woods_contrib: 0,
            partial_cover: 0,
            cumulative_modifier: 0,
            smoke_contrib: 0,
            after_block: false,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct LOSTrace {
    pub steps: Vec<LOSStep>,
    pub result: LOSResult,
}

// ---- cube-coordinate line geometry -------------------------------------------------------------------------------

fn to_cube(h: Hex) -> (f64, f64, f64) {
    let (x, y) = h;
    let q = x as f64;
    let r = (y - x) as f64 / 2.0;
    let s = -q - r;
    (q, r, s)
}

fn from_cube(q: i64, r: i64, _s: i64) -> Hex {
    let x = q;
    let y = 2 * r + x; // round(2 * r + x) of ints
    (x, y)
}

/// Straight-line hex distance between two doubled-coordinate hexes.
pub fn hex_distance(a: Hex, b: Hex) -> i64 {
    let (aq, ar, as_) = to_cube(a);
    let (bq, br, bs) = to_cube(b);
    let mut m = (aq - bq).abs();
    let r = (ar - br).abs();
    if r > m {
        m = r;
    }
    let s = (as_ - bs).abs();
    if s > m {
        m = s;
    }
    py_round(m) as i64
}

fn cube_round(q: f64, r: f64, s: f64) -> (i64, i64, i64) {
    let (rq, rr, rs) = (py_round(q), py_round(r), py_round(s));
    let (dq, dr, ds) = ((rq as f64 - q).abs(), (rr as f64 - r).abs(), (rs as f64 - s).abs());
    if dq > dr && dq > ds {
        return (-rr - rs, rr, rs);
    }
    if dr > ds {
        return (rq, -rq - rs, rs);
    }
    (rq, rr, -rq - rr)
}

const NUDGE: (f64, f64, f64) = (1e-6, 2e-6, -3e-6);

fn cube_round_candidates(q: f64, r: f64, s: f64) -> Vec<(i64, i64, i64)> {
    let (nq, nr, ns) = NUDGE;
    let first = cube_round(q + nq, r + nr, s + ns);
    let second = cube_round(q - nq, r - nr, s - ns);
    if first == second {
        vec![first]
    } else {
        vec![first, second]
    }
}

/// The straight-line path of hexes between two hex centers, one entry per step (both hexes when the line runs exactly
/// along a shared edge). Worked out from (0, 0) to the offset and shifted onto `a`, as the Python does (its cache),
/// because the float arithmetic from a different origin can round differently.
pub fn hex_line(a: Hex, b: Hex) -> Vec<Vec<Hex>> {
    let (dx, dy) = (b.0 - a.0, b.1 - a.1);
    let shape = hex_line_direct((0, 0), (dx, dy));
    let (ax, ay) = a;
    shape.into_iter().map(|step| step.into_iter().map(|(x, y)| (ax + x, ay + y)).collect()).collect()
}

pub fn hex_line_direct(a: Hex, b: Hex) -> Vec<Vec<Hex>> {
    let n = hex_distance(a, b);
    let (aq, ar, as_) = to_cube(a);
    let (bq, br, bs) = to_cube(b);
    if n == 0 {
        return vec![vec![a]];
    }
    let mut path = Vec::new();
    for i in 0..=n {
        let t = i as f64 / n as f64;
        let q = aq + (bq - aq) * t;
        let r = ar + (br - ar) * t;
        let s = as_ + (bs - as_) * t;
        let candidates: Vec<Hex> = cube_round_candidates(q, r, s).into_iter().map(|(cq, cr, cs)| from_cube(cq, cr, cs)).collect();
        path.push(candidates);
    }
    path
}

// ---- LOS rules -----------------------------------------------------------------------------------------------------

pub const STANDING_HEIGHT: i64 = 2;
pub const PRONE_HEIGHT: i64 = 1;

/// A 'Mech's LOS height code: Python uses a plain int for a normal 'Mech and the `Height` namedtuple for a
/// superheavy (so their cache entries never share a key). `superheavy` false = the plain int `levels`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct Height {
    pub levels: i64,
    pub standing: bool,
    pub superheavy: bool,
}

pub const SUPERHEAVY_STANDING: Height = Height { levels: 3, standing: true, superheavy: true };
pub const SUPERHEAVY_PRONE: Height = Height { levels: 2, standing: false, superheavy: true };
pub const SUPERHEAVY_COVER_STEP: i64 = 2;

/// The LOS height code of a 'Mech (p.57; p.240).
pub fn mech_height(prone: bool, superheavy: bool) -> Height {
    if superheavy {
        return if prone { SUPERHEAVY_PRONE } else { SUPERHEAVY_STANDING };
    }
    let levels = if prone { PRONE_HEIGHT } else { STANDING_HEIGHT };
    Height { levels, standing: levels == STANDING_HEIGHT, superheavy: false }
}

pub const STANDING: Height = Height { levels: 2, standing: true, superheavy: false };

pub const WOODS_HEIGHT: i64 = 2;
pub const WOODS_BLOCK_POINTS: i64 = 3;
pub const WOODS_FEATURES: [&str; 2] = ["woods", "jungle"];
pub const ULTRA_HEAVY: &str = "3";
pub const ULTRA_HEAVY_HEIGHT: i64 = 3;
pub const FIELDS_HEIGHT: i64 = 1;
pub const FIELDS_PER_POINT: i64 = 2;
pub const FIELDS_BLOCK: i64 = 6;
pub const SMOKE_HEIGHT: i64 = 2;
pub const SMOKE_HEX_CAP: i64 = 2;

fn woods_points(density: &str) -> i64 {
    match density {
        "1" => 1,
        "2" => 2,
        _ => 0,
    }
}

fn smoke_points(density: &str) -> i64 {
    match density {
        "1" => 1,
        "2" => 2,
        other => panic!("KeyError: {}", other),
    }
}

/// What a hex's smoke adds to `woods_points`: never past 2 (Core p.124).
pub fn smoke_share(info: &HexInfo, woods_points: i64) -> i64 {
    match &info.smoke {
        None => 0,
        Some(sm) => 0.max(SMOKE_HEX_CAP.min(woods_points + smoke_points(&sm.density)) - woods_points),
    }
}

/// The first of woods / jungle present: its density text (None if present with no params).
pub fn woods_density(info: &HexInfo) -> Option<String> {
    for name in WOODS_FEATURES {
        if let Some(p) = info.features.get(name) {
            return p.first().cloned();
        }
    }
    None
}

fn hex_info<'a>(board: &'a Board, h: Hex) -> Option<&'a HexInfo> {
    board.info_xy(h.0, h.1)
}

fn fmt_hex(h: Hex) -> String {
    format!("({}, {})", h.0, h.1)
}

struct Walked {
    steps: Vec<LOSStep>,
    blocked_at: Option<i64>,
    modifier: i64,
    cover: i64,
}

fn evaluate(attacker_hex: Hex, target_hex: Hex, board: &Board, attacker_height: Height, target_height: Height) -> Result<LOSTrace, String> {
    let a_info = hex_info(board, attacker_hex);
    let b_info = hex_info(board, target_hex);
    let a_info = a_info.ok_or_else(|| format!("LOS attacker hex {} is not on the loaded board.", fmt_hex(attacker_hex)))?;
    let b_info = b_info.ok_or_else(|| format!("LOS target hex {} is not on the loaded board.", fmt_hex(target_hex)))?;

    let (a_level, b_level) = (a_info.level, b_info.level);
    let a_los = a_level + attacker_height.levels;
    let b_los = b_level + target_height.levels;

    let path = hex_line(attacker_hex, target_hex);
    let n = path.len() as i64 - 1;
    if n == 0 {
        let mut st = LOSStep::new(0, attacker_hex);
        st.level = a_level;
        st.is_endpoint = true;
        return Ok(LOSTrace { steps: vec![st], result: LOSResult { los: true, modifier: 0, distance: 0 } });
    }

    let intervenes = |top: i64, i: i64| -> bool { (top >= a_los && top >= b_los) || (i == 1 && top >= a_los) || (i == n - 1 && top >= b_los) };

    let mut sides: Vec<Vec<Hex>> = Vec::new();
    for pick in [0usize, 1] {
        let hexes_on: Vec<Hex> = (1..n).map(|i| {
            let c = &path[i as usize];
            if pick == 0 { c[0] } else { *c.last().unwrap() }
        }).collect();
        if hexes_on.iter().all(|h| hex_info(board, *h).is_some()) {
            sides.push(hexes_on);
        }
        if (1..n).all(|i| path[i as usize].len() == 1) {
            break;
        }
    }
    if sides.is_empty() {
        return Err(format!("LOS line {} -> {} runs off the loaded board.", fmt_hex(attacker_hex), fmt_hex(target_hex)));
    }

    let walk = |hexes_on: &Vec<Hex>| -> Walked {
        let mut steps: Vec<LOSStep> = Vec::new();
        let mut first = LOSStep::new(0, attacker_hex);
        first.level = a_level;
        first.is_endpoint = true;
        steps.push(first);
        let (mut woods, mut fields, mut blocked_at): (i64, i64, Option<i64>) = (0, 0, None);
        for (k, h) in hexes_on.iter().enumerate() {
            let i = k as i64 + 1;
            let info = hex_info(board, *h).unwrap();
            let level = info.level;
            let after = blocked_at.is_some();
            let (mut contrib, mut blocks, mut smoke) = (0i64, false, 0i64);
            if !after {
                blocks = intervenes(level, i);
                let density = woods_density(info);
                if !blocks && density.as_deref() == Some(ULTRA_HEAVY) {
                    blocks = intervenes(level + ULTRA_HEAVY_HEIGHT, i);
                } else if !blocks && density.is_some() && intervenes(level + WOODS_HEIGHT, i) {
                    contrib = woods_points(density.as_deref().unwrap());
                    woods += contrib;
                    blocks = woods >= WOODS_BLOCK_POINTS;
                }
                if !blocks && info.smoke.is_some() && intervenes(info.surface_level.unwrap_or(level) + SMOKE_HEIGHT, i) {
                    smoke = smoke_share(info, contrib);
                    contrib += smoke;
                    woods += smoke;
                    blocks = woods >= WOODS_BLOCK_POINTS;
                }
                if !blocks && info.features.has("planted_fields") && intervenes(level + FIELDS_HEIGHT, i) {
                    fields += 1;
                    contrib += if fields % FIELDS_PER_POINT == 0 { 1 } else { 0 };
                    blocks = fields >= FIELDS_BLOCK;
                }
                if blocks {
                    blocked_at = Some(i);
                }
            }
            let mut st = LOSStep::new(i, *h);
            st.level = level;
            st.blocked = blocks;
            st.woods_contrib = contrib;
            st.cumulative_modifier = woods + fields.div_euclid(FIELDS_PER_POINT);
            st.after_block = after;
            st.smoke_contrib = smoke;
            steps.push(st);
        }
        let mut cover = 0;
        if blocked_at.is_none() {
            if target_height.standing {
                let step = if target_height.superheavy { SUPERHEAVY_COVER_STEP } else { 1 };
                if n >= 2 {
                    let info = hex_info(board, *hexes_on.last().unwrap()).unwrap();
                    if info.level == b_level + step && info.depth.unwrap_or(0) == 0 && a_los <= b_los {
                        cover = 1;
                    }
                }
                let a_depth = a_info.depth.unwrap_or(0) - if attacker_height.superheavy { 1 } else { 0 };
                let a_submerged = a_depth >= 2 || (a_depth >= 1 && !attacker_height.standing);
                if b_info.depth == Some(step) && !a_submerged {
                    cover = 1;
                }
            }
            if n >= 2 {
                let last = steps.last_mut().unwrap();
                last.partial_cover = cover;
                last.cumulative_modifier = woods + fields.div_euclid(FIELDS_PER_POINT) + cover;
            }
        }
        Walked { steps, blocked_at, modifier: woods + fields.div_euclid(FIELDS_PER_POINT) + cover, cover }
    };

    let walked: Vec<Walked> = sides.iter().map(|h| walk(h)).collect();
    // The target's choice: a blocked line if it can, else the higher modifier (max keeps the first of equals).
    let mut best = 0usize;
    for k in 1..walked.len() {
        let key_k = (walked[k].blocked_at.is_some(), walked[k].modifier);
        let key_b = (walked[best].blocked_at.is_some(), walked[best].modifier);
        if key_k > key_b {
            best = k;
        }
    }
    let Walked { mut steps, blocked_at, mut modifier, cover } = walked.into_iter().nth(best).unwrap();
    if sides.len() > 1 {
        let other_side = &sides[1 - best];
        let count = steps.len().saturating_sub(1).min(other_side.len());
        for k in 0..count {
            if other_side[k] != steps[1 + k].hex {
                steps[1 + k].other_candidate = Some(other_side[k]);
            }
        }
    }

    let (mut target_woods, mut target_smoke) = (0, 0);
    if blocked_at.is_none() {
        target_woods = target_woods_modifier(woods_density(b_info).as_deref());
        target_smoke = smoke_share(b_info, target_woods);
        modifier += target_woods + target_smoke;
    }
    let mut last = LOSStep::new(n, target_hex);
    last.level = b_level;
    last.is_endpoint = true;
    last.woods_contrib = target_woods + target_smoke;
    last.smoke_contrib = target_smoke;
    last.partial_cover = cover;
    last.cumulative_modifier = modifier;
    last.after_block = blocked_at.is_some();
    steps.push(last);
    let los = blocked_at.is_none();
    Ok(LOSTrace { steps, result: LOSResult { los, modifier, distance: if los { n } else { blocked_at.unwrap() } } })
}

/// The to-hit modifier of the target's own hex alone (woods / jungle, smoke) - indirect fire with no spotter.
pub fn target_hex_modifier(target_hex: Hex, board: &Board) -> Result<i64, String> {
    let label = hex_label(target_hex.0, target_hex.1)?;
    let info = board.hexes.get(&label).ok_or_else(|| format!("KeyError: {}", label))?;
    let woods = target_woods_modifier(woods_density(info).as_deref());
    Ok(woods + smoke_share(info, woods))
}

pub fn has_los(attacker_hex: Hex, target_hex: Hex, board: &Board, attacker_height: Height, target_height: Height) -> Result<LOSResult, String> {
    Ok(evaluate(attacker_hex, target_hex, board, attacker_height, target_height)?.result)
}

/// Same evaluation as has_los(), with the full per-step trace.
pub fn trace_los_path(attacker_hex: Hex, target_hex: Hex, board: &Board, attacker_height: Height, target_height: Height) -> Result<LOSTrace, String> {
    evaluate(attacker_hex, target_hex, board, attacker_height, target_height)
}
