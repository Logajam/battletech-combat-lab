// MegaMek's straight line between two hex centres (Coords.intervening, Coords.nextHex, IdealHex), ported as written on MegaMek's
// coordinates: (column, row) from 0, odd columns half a hex lower - this engine's `cols_rows` / `princess_memory::label_to_cols_rows`.
// Moved here from caspar.rs (session 30) when line of sight began to use it: the Core Rulebook defines LOS as the straight line
// from the attacker's hex centre to the target's (p.56), and every hex that line passes through intervenes; the old sampled
// line (`los::hex_line_sampled`, one point per hex step) skipped hexes the line clips and took a line CROSSING an edge for one
// running ALONG it (Daniel, 2026-11-19: "a Tier 1 bug"). Checked against MegaMek 0.51.01.7 on every pair of an 11 x 11 board.
// Credit: MegaMek Team, GPL v3 or later (CREDITS.md).

/// Java's Math.round on a double, exactly (ties up): floor(x + 0.5) rounds 0.49999999999999994 up.
fn java_round_f64(x: f64) -> i64 {
    let f = x.floor();
    if x - f >= 0.5 { f as i64 + 1 } else { f as i64 }
}

/// Coords.degree: the angle from a to b in whole degrees, clockwise from north.
pub fn mm_degree(a: (i64, i64), b: (i64, i64)) -> i64 {
    java_round_f64(180.0 / std::f64::consts::PI * mm_radian(a, b))
}

/// The line of sight between two hexes as STEPS: one hex per step, or two where the line runs along the edge between them
/// (Core p.56: the target 'Mech's controller picks which; `los::trace_los_path` walks both sides). On MegaMek's coordinates.
/// A line at 30 degrees off a hexside direction (MegaMek: whole degrees % 60 == 30) runs along edges all the way: MegaMek's
/// split list [src, left, right, centre, left, right, centre, ..., dest] (LosEffects.losDivided reads it in threes). Any other
/// line: every hex it passes through, one by one, the hexes it only clips included.
pub fn los_steps(src: (i64, i64), dest: (i64, i64)) -> Vec<Vec<(i64, i64)>> {
    if src == dest {
        return vec![vec![src]];
    }
    if mm_degree(src, dest) % 60 != 30 {
        return mm_intervening(src, dest).into_iter().map(|h| vec![h]).collect();
    }
    let hexes = mm_intervening_split(src, dest, true);
    let mut steps = vec![vec![hexes[0]]];
    let last = hexes.len() - 1;
    let mut i = 1;
    while i < last {
        if i % 3 == 0 {
            steps.push(vec![hexes[i]]);
            i += 1;
        } else if i + 1 < last {
            steps.push(vec![hexes[i], hexes[i + 1]]);
            i += 2;
        } else {
            steps.push(vec![hexes[i]]);
            i += 1;
        }
    }
    steps.push(vec![hexes[last]]);
    steps
}

const X_CONST: f64 = 0.577_350_269_189_625_7; // Math.tan(Math.PI / 6.0), as Java prints it
const HEX_SIDE: f64 = std::f64::consts::PI / 3.0;

/// IdealHex: the hex's corners (x[0..6], y[0..6]) and centre in MegaMek's unit layout.
struct IdealHex {
    x: [f64; 6],
    y: [f64; 6],
    cx: f64,
    cy: f64,
}

impl IdealHex {
    fn of(c: (i64, i64)) -> IdealHex {
        let ox = c.0 as f64 * X_CONST * 3.0;
        let oy = c.1 as f64 * 2.0 + if c.0 & 1 == 1 { 1.0 } else { 0.0 };
        let (cx, cy) = (ox + X_CONST * 2.0, oy + 1.0);
        let x = [ox + X_CONST, ox + X_CONST * 3.0, ox + X_CONST * 4.0, ox + X_CONST * 3.0, ox + X_CONST, ox];
        let y = [oy, oy, cy, oy + 2.0, oy + 2.0, cy];
        IdealHex { x, y, cx, cy }
    }

    /// IdealHex.turns: 1 left, -1 right, 0 straight (within 1e-6).
    fn turns(x0: f64, y0: f64, x1: f64, y1: f64, x2: f64, y2: f64) -> i64 {
        let cross = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0);
        if cross > 0.000001 { 1 } else if cross < -0.000001 { -1 } else { 0 }
    }

    /// IdealHex.isIntersectedBy: does the line through (x0, y0) and (x1, y1) touch this hex?
    fn is_intersected_by(&self, x0: f64, y0: f64, x1: f64, y1: f64) -> bool {
        let side1 = Self::turns(x0, y0, x1, y1, self.x[0], self.y[0]);
        if side1 == 0 {
            return true;
        }
        (1..6).any(|i| {
            let j = Self::turns(x0, y0, x1, y1, self.x[i], self.y[i]);
            j == 0 || j != side1
        })
    }
}

/// Coords.radian: the angle from a to b, clockwise from north.
fn mm_radian(a: (i64, i64), b: (i64, i64)) -> f64 {
    let (src, dst) = (IdealHex::of(a), IdealHex::of(b));
    if src.cy == dst.cy {
        return if src.cx < dst.cx { std::f64::consts::PI / 2.0 } else { std::f64::consts::PI * 1.5 };
    }
    // Java's Math.atan is fdlibm's (StrictMath); the system atan can differ in the last bit, which moves a 30-degree line
    let mut r = libm::atan((dst.cx - src.cx) / (src.cy - dst.cy));
    if src.cy < dst.cy {
        r = (r + std::f64::consts::PI) % (std::f64::consts::PI * 2.0);
    }
    if r < 0.0 {
        r += std::f64::consts::PI * 2.0;
    }
    r
}

/// Coords.direction: (int) Math.round(radian / HEX_SIDE) % 6. Java's Math.round is exact (ties up): floor(x + 0.5) would
/// round 0.49999999999999994 up, which happens on the 30-degree lines.
pub fn mm_direction(a: (i64, i64), b: (i64, i64)) -> i64 {
    let x = mm_radian(a, b) / HEX_SIDE;
    let f = x.floor();
    (if x - f >= 0.5 { f as i64 + 1 } else { f as i64 }) % 6
}

/// Coords.translated(dir) (xInDir / yInDir at distance 1).
pub fn mm_translated(c: (i64, i64), dir: i64) -> (i64, i64) {
    let (x, y) = c;
    let odd = x & 1;
    match dir {
        0 => (x, y - 1),
        1 => (x + 1, y - (2 - odd) / 2),
        2 => (x + 1, y + (1 + odd) / 2),
        3 => (x, y + 1),
        4 => (x - 1, y + (1 + odd) / 2),
        _ => (x - 1, y - (2 - odd) / 2),
    }
}

/// Coords.intervening(src, dest) (split = false): src, every hex the centre line passes through, dest. Where the line runs
/// along an edge, Coords.nextHex tries the side directions (centre + 1, then centre + 5) before the centre one and keeps the
/// first the line touches.
pub fn mm_intervening(src: (i64, i64), dest: (i64, i64)) -> Vec<(i64, i64)> {
    mm_intervening_split(src, dest, false)
}

/// Coords.intervening(src, dest, split). With `split` (MegaMek's LOS for a line running along hex edges, LosEffects.
/// losDivided) the centre direction is MegaMek's own "left before right" form - `Math.round(radian + 0.0001 / HEX_SIDE)
/// % 6`, ported as written - so the hexes either side of the edge come as left, right, then the hex the line meets next.
pub fn mm_intervening_split(src: (i64, i64), dest: (i64, i64), split: bool) -> Vec<(i64, i64)> {
    let (i_src, i_dest) = (IdealHex::of(src), IdealHex::of(dest));
    let centre = if split { java_round_f64(mm_radian(src, dest) + 0.0001 / HEX_SIDE) % 6 } else { mm_direction(src, dest) };
    let directions = [(centre + 1) % 6, (centre + 5) % 6, centre];
    let mut hexes = vec![src];
    let mut current = src;
    // a near-edge line can zig-zag through up to about twice the distance in hexes; the bound only guards against a loop
    let limit = 4 * (crate::princess_geometry::mm_distance(src, dest) + 2);
    while current != dest && (hexes.len() as i64) <= limit {
        let next = directions.iter().map(|d| mm_translated(current, *d)).find(|t| IdealHex::of(*t).is_intersected_by(i_src.cx, i_src.cy, i_dest.cx, i_dest.cy));
        match next {
            Some(t) => {
                current = t;
                hexes.push(t);
            }
            None => break, // MegaMek throws here ("Couldn't find the next hex!"); it does not happen on a straight line
        }
    }
    hexes
}


#[cfg(test)]
mod tests {
    use super::{los_steps, mm_intervening, mm_intervening_split};

    /// Line of sight's steps (session 30, the Tier 1 bug). 0209 -> 0610 (Scattered Woods) crosses the 0409 / 0410 edge in
    /// its middle: both hexes, one after the other (the sampled line had put them as one "pick one" step). 0101 -> 0304 runs
    /// along hex edges (30 degrees): the pairs either side are the target's choice, as MegaMek's split list gives them.
    #[test]
    fn los_steps_cross_and_run_along() {
        assert_eq!(los_steps((1, 8), (5, 9)), vec![vec![(1, 8)], vec![(2, 9)], vec![(3, 8)], vec![(3, 9)], vec![(4, 9)], vec![(5, 9)]]);
        assert_eq!(los_steps((0, 0), (2, 3)), vec![vec![(0, 0)], vec![(1, 0), (0, 1)], vec![(1, 1)], vec![(2, 2), (1, 2)], vec![(2, 3)]]);
    }

    /// Lines as MegaMek 0.51.01.7's own Coords.intervening gives them (CASPAR's review, 2026-11-19: the port matched it on
    /// every pair of an 11 x 11 board, 14,641 lines). These cover edge-runs, 30-degree lines (the fdlibm atan) and zig-zags.
    #[test]
    fn hex_line_matches_megamek() {
        let cases: [(&str, &str); 6] = [
            ("0,0 1,10", "0,0 0,1 0,2 0,3 1,3 0,4 1,4 0,5 1,5 0,6 1,6 0,7 1,7 1,8 1,9 1,10"),
            ("0,0 4,6", "0,0 1,0 0,1 1,1 2,2 1,2 2,3 3,3 2,4 3,4 4,5 3,5 4,6"),
            ("0,6 4,0", "0,6 1,5 0,5 1,4 2,4 1,3 2,3 3,2 2,2 3,1 4,1 3,0 4,0"),
            ("3,3 7,9", "3,3 4,4 3,4 4,5 5,5 4,6 5,6 6,7 5,7 6,8 7,8 6,9 7,9"),
            ("5,5 5,0", "5,5 5,4 5,3 5,2 5,1 5,0"),
            ("10,0 0,10", "10,0 9,0 9,1 8,2 7,2 7,3 6,4 5,4 5,5 4,6 3,6 3,7 2,8 1,8 1,9 0,10"),
        ];
        let xy = |s: &str| -> (i64, i64) {
            let (a, b) = s.split_once(',').unwrap();
            (a.parse().unwrap(), b.parse().unwrap())
        };
        for (ends, want) in cases {
            let (a, b) = ends.split_once(' ').unwrap();
            let _ = mm_intervening_split;
            let got: Vec<String> = mm_intervening(xy(a), xy(b)).iter().map(|(x, y)| format!("{},{}", x, y)).collect();
            assert_eq!(got.join(" "), want, "line {}", ends);
        }
    }
}
