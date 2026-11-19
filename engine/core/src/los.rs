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

#[derive(Clone, Copy, Debug, PartialEq)]
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

/// LINE OF SIGHT's line (Core p.56): the straight line from hex centre to hex centre, one entry per hex it passes through,
/// both hexes where it runs exactly along the edge between them (the target's controller picks one). MegaMek's trace
/// (`mm_line::los_steps`). Session 30 (Daniel, 2026-11-19: "a Tier 1 bug"): it was `hex_line_sampled`, which skipped hexes
/// the line clips and took a line crossing an edge at a sample point for one running along it - e.g. 0209 -> 0610 on
/// Scattered Woods crosses heavy 0409 AND light 0410 (blocked), where the sampled line let the target pick one.
pub fn hex_line(a: Hex, b: Hex) -> Vec<Vec<Hex>> {
    // this engine's internal (x, y) <-> MegaMek's (column, row) from 0, the arithmetic of hex_label / parse_hex_label
    // without the text (speed: line of sight is on the hot path)
    let to_mm = |h: Hex| -> Option<(i64, i64)> {
        let off = crate::hex_geometry::row_parity_offset(h.0);
        ((h.1 - off).rem_euclid(2) == 0).then(|| (h.0, -(h.1 - off).div_euclid(2)))
    };
    let (Some(ma), Some(mb)) = (to_mm(a), to_mm(b)) else { return hex_line_sampled(a, b) };
    let back = |c: (i64, i64)| -> Hex { (c.0, -2 * c.1 + crate::hex_geometry::row_parity_offset(c.0)) };
    // A line's shape depends only on the offset and on whether it starts in an odd column (MegaMek's odd columns sit half a
    // hex lower): traced once per shape from (parity, 0) and moved by an even number of columns (speed only, session 30).
    thread_local! {
        static SHAPES: std::cell::RefCell<crate::fasthash::HashMap<(i64, i64, i64), Vec<Vec<(i64, i64)>>>> = Default::default();
    }
    let parity = ma.0 & 1;
    let key = (parity, mb.0 - ma.0, mb.1 - ma.1);
    let shape = SHAPES.with(|c| {
        c.borrow_mut().entry(key).or_insert_with(|| crate::mm_line::los_steps((parity, 0), (parity + key.1, key.2))).clone()
    });
    let (sx, sy) = (ma.0 - parity, ma.1);
    shape.into_iter().map(|step| step.into_iter().map(|(x, y)| (x + sx, y + sy)).map(back).collect()).collect()
}

/// The old line: one sampled point per hex step from centre to centre (cube interpolation, from the Python), both hexes
/// where a sample falls on an edge. Kept where a path must step from hex to ADJACENT hex (jump paths, a death from above's
/// last hex); line of sight uses `hex_line`. Worked out from (0, 0) to the offset and shifted onto `a`, as the Python does
/// (its cache), because the float arithmetic from a different origin can round differently.
pub fn hex_line_sampled(a: Hex, b: Hex) -> Vec<Vec<Hex>> {
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

    // woods and hills next to the attacker or the target count at their height (p.57): ADJACENT, not the first / last step,
    // since the true line can clip a hex that touches neither (session 30)
    let intervenes = |top: i64, h: Hex| -> bool { (top >= a_los && top >= b_los) || (hex_distance(h, attacker_hex) == 1 && top >= a_los) || (hex_distance(h, target_hex) == 1 && top >= b_los) };

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
                blocks = intervenes(level, *h);
                let density = woods_density(info);
                if !blocks && density.as_deref() == Some(ULTRA_HEAVY) {
                    blocks = intervenes(level + ULTRA_HEAVY_HEIGHT, *h);
                } else if !blocks && density.is_some() && intervenes(level + WOODS_HEIGHT, *h) {
                    contrib = woods_points(density.as_deref().unwrap());
                    woods += contrib;
                    blocks = woods >= WOODS_BLOCK_POINTS;
                }
                if !blocks && info.smoke.is_some() && intervenes(info.surface_level.unwrap_or(level) + SMOKE_HEIGHT, *h) {
                    smoke = smoke_share(info, contrib);
                    contrib += smoke;
                    woods += smoke;
                    blocks = woods >= WOODS_BLOCK_POINTS;
                }
                if !blocks && info.features.has("planted_fields") && intervenes(level + FIELDS_HEIGHT, *h) {
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
    // the range in hexes (the line itself can have more steps than that: it lists every hex it passes through)
    Ok(LOSTrace { steps, result: LOSResult { los, modifier, distance: if los { hex_distance(attacker_hex, target_hex) } else { blocked_at.unwrap() } } })
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
